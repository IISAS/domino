import os.path
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin

import jwt
import requests
from aiohttp import ClientSession

from core.logger import get_configured_logger
from core.settings import settings
from schemas.exceptions.base import ResourceNotFoundException


class AirflowRestClient(requests.Session):
    def __init__(self, *args, **kwargs):
        super(AirflowRestClient, self).__init__(*args, **kwargs)

        self.base_url = settings.AIRFLOW_API_SERVER_HOST
        if not self.base_url.endswith('/'):
            self.base_url += '/'
        self.username = settings.AIRFLOW_ADMIN_CREDENTIALS.get('username')
        self.password = settings.AIRFLOW_ADMIN_CREDENTIALS.get('password')
        self.jwt_token = None
        self.logger = get_configured_logger(self.__class__.__name__)

        self.max_page_size = 100
        self.min_page_size = 1
        self.min_page = 0


    def _is_jwt_token_expired(self, jwt_token):
        if not jwt_token:
            return True
        try:
            header = jwt.get_unverified_header(jwt_token)
            alg = header['alg']
            decoded = jwt.decode_complete(jwt_token, algorithms=[alg], options={"verify_signature": False})
            payload = decoded['payload']
            return payload['exp'] < datetime.now(timezone.utc).timestamp()
        except:
            return True


    def _get_jwt_token(self) -> str:
        jwt_token = None
        try:
            url = urljoin(self.base_url, "auth/token")
            resp = self.post(url, json={
                "username": self.username,
                "password": self.password
            })
            resp.raise_for_status()
            jwt_token = resp.json().get("access_token")
            self.logger.info("Obtained JWT token.")
        except Exception as e:
            self.logger.exception(f"Failed to obtain JWT token: {e}")
        finally:
            return jwt_token


    def _validate_pagination_params(self, page, page_size):
        page = max(page, self.min_page)
        page_size = max(self.min_page_size, min(page_size, self.max_page_size))

        return page, page_size


    def request(self, method, resource, **kwargs):
        try:
            if self._is_jwt_token_expired(self.jwt_token):
                self.jwt_token = self._get_jwt_token()
            if not self.jwt_token:
                raise Exception(f'Could not obtain JWT token')
            self.headers.update({"Authorization": f"Bearer {self.jwt_token}"})
            url = urljoin(self.base_url, resource)
            return super(AirflowRestClient, self).request(method, url, **kwargs)
        except Exception as e:
            self.logger.exception(e)
            raise e


    async def _get_jwt_token_async(self) -> str:
        jwt_token = None
        url = urljoin(self.base_url, "auth/token")
        async with ClientSession() as session:
            try:
                resp = await session.post(url, json={
                    "username": self.username,
                    "password": self.password
                })
                resp.raise_for_status()
                data = await resp.json()
                jwt_token = data.get("access_token")
                self.logger.info("Obtained JWT token (async).")
            except Exception as e:
                self.logger.exception(f"Failed to obtain JWT token (async): {e}")
                raise
            finally:
                return jwt_token


    async def _request_async(self, session, method, resource, **kwargs):
        """
        Request method
        Args:
            session (aiohttp.ClientSession): aiohttp session instance
        Returns:
            data (dict): data returned by the API
        """
        try:
            if self._is_jwt_token_expired(self.jwt_token):
                self.jwt_token = await self._get_jwt_token_async()
            if not self.jwt_token:
                raise Exception(f'Could not obtain JWT token')
            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {self.jwt_token}"
            url = urljoin(self.base_url, resource)
            response = await session.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
        except Exception:
            self.logger.exception(f'API {method} Request error. Url: {resource}. Params {kwargs}')
            return None

        data = await response.json()
        return data

    def run_dag(self, dag_id):
        resource = f"api/v2/dags/{dag_id}/dagRuns"
        dag_run_uuid = str(uuid.uuid4())
        payload = {
            "dag_run_id": f"rest-client-{dag_run_uuid}",
            "logical_date": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        }
        response = self.request(
            method="post",
            resource=resource,
            json=payload
        )
        return response

    def delete_dag(self, dag_id):
        resource = f"api/v2/dags/{dag_id}"
        response = self.request(
            method="delete",
            resource=resource,
        )
        return response

    def update_dag(self, dag_id, payload):
        resource = f"api/v2/dags/{dag_id}"
        response = self.request(
            method='patch',
            resource=resource,
            json=payload
        )
        return response

    def get_dag_by_id(self, dag_id):
        resource = f"api/v2/dags/{dag_id}"
        response = self.request(
            method='get',
            resource=resource,
        )
        return response

    async def get_dag_by_id_async(self, session, dag_id):
        resource = f"api/v2/dags/{dag_id}"
        response = await self._request_async(session, 'GET', resource)
        return {
            'dag_id': dag_id,
            'response': response
        }

    def get_all_dag_tasks(self, dag_id):
        resource = f"api/v2/dags/{dag_id}/tasks"
        response = self.request(
            method='get',
            resource=resource,
        )
        return response

    def list_import_errors(self, limit: int = 100, offset: int = 0):
        resource = "api/v2/importErrors"
        response = self.request(
            method='get',
            resource=resource,
            params={
                'limit': limit,
                'offset': offset
            }
        )
        return response

    def get_all_workflow_runs(self, dag_id: str, page: int, page_size: int, descending: bool = False):
        page, page_size = self._validate_pagination_params(page, page_size)
        offset = page * page_size
        order_by = "-logical_date" if descending else "logical_date"
        resource = f"api/v2/dags/{dag_id}/dagRuns?limit={page_size}&offset={offset}&order_by={order_by}"
        response = self.request(
            method='get',
            resource=resource,
        )
        return response

    def get_all_run_tasks_instances(self, dag_id: str, dag_run_id: str, page: int, page_size: int):
        page, page_size = self._validate_pagination_params(page, page_size)
        offset = page * page_size
        resource = f"api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances?limit={page_size}&offset={offset}"
        response = self.request(
            method='get',
            resource=resource,
        )
        return response

    def get_task_logs(self, dag_id: str, dag_run_id: str, task_id: str, task_try_number: int):
        resource = f"/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{task_try_number}"
        response = self.request(
            method='get',
            resource=resource,
        )
        if response.status_code == 404:
            raise ResourceNotFoundException("Task result not found.")
        return response

    def get_task_result(self, dag_id: str, dag_run_id: str, task_id: str, task_try_number: int):
        # ref: https://airflow.apache.org/docs/apache-airflow/stable/stable-rest-api-ref.html#operation/get_xcom_entries
        resource = f"/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/xcomEntries/return_value"
        response = self.request(
            method='get',
            resource=resource,
        )
        if response.status_code == 404:
            raise ResourceNotFoundException("Task result not found.")
        if response.status_code != 200:
            raise BaseException("Error while trying to get task result base64_content")
        response_dict = response.json()["value"]
        # Get base64_content and file_type
        result_dict = dict()
        if "display_result" in response_dict:
            result_dict["base64_content"] = response_dict["display_result"].get("base64_content", None)
            file_type = response_dict["display_result"].get("file_type", None)
            file_path = response_dict["display_result"].get("file_path", None)
            if file_path and file_type == "image":
                ext = os.path.splitext(file_path)[1].lstrip(".").lower()
                file_type = ext if len(ext) > 1 else file_type
            result_dict["file_type"] = file_type
        return result_dict

