from datetime import datetime
from urllib.parse import urljoin

import requests
from aiohttp import ClientSession

from core.logger import get_configured_logger
from core.settings import settings


class AWPLRestClient(requests.Session):
    api_url = settings.AWPL_REST_API_URL
    api_token = settings.AWPL_REST_API_TOKEN

    @classmethod
    def _get_jwt_token(cls) -> str:
        # TODO: Replace with AWPL REST API token request.
        # For now, we use token from settings
        return cls.api_token

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.jwt_token = None
        self.retrieving_jwt_token = False

        self.logger = get_configured_logger(self.__class__.__name__)

    def request(self, method, resource, **kwargs):
        try:
            if not self.jwt_token and not self.retrieving_jwt_token:
                self.retrieving_jwt_token = True
                try:
                    self.jwt_token = self._get_jwt_token()
                except Exception as e:
                    raise e
                finally:
                    self.retrieving_jwt_token = False
            if self.jwt_token:
                self.headers.update({"Authorization": f"Bearer {self.jwt_token}"})
            url = urljoin(self.api_url, resource)
            response = super().request(method, url, **kwargs)
            if response.status_code == 401:
                # Token expired or invalid → re-authenticate
                self.jwt_token = self._get_jwt_token()
                self.headers.update({"Authorization": f"Bearer {self.jwt_token}"})
                return super().request(method, url, **kwargs)
            self.logger.debug(f'AWPL REST client: method={method}, url={url}, kwargs={kwargs}')
            return response
        except Exception as e:
            self.logger.exception(e)
            raise e

    @classmethod
    async def _get_jwt_token_async(cls):
        # TODO: Replace with AWPL REST API token request.
        # For now, we use token from settings
        return cls.api_token

    async def _request_async(
        self,
        session,
        method,
        resource,
        **kwargs
    ):
        try:
            if not self.jwt_token:
                self.jwt_token = await self._get_jwt_token_async()
            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {self.jwt_token}"
            url = urljoin(self.api_url, resource)
            response = await session.request(method, url, headers=headers, **kwargs)
            if response.status == 401:
                # expired
                self.jwt_token = await self._get_jwt_token_async()
                headers["Authorization"] = f"Bearer {self.jwt_token}"
                response = await session.request(method, url, headers=headers, **kwargs)
            self.logger.debug(f'AWPL REST client: method={method}, url={url}, kwargs={kwargs}')
            response.raise_for_status()
        except Exception:
            self.logger.exception(f'API {method} Request error. Url: {resource}. Params {kwargs}')
            return None

        data = await response.json()
        return data

    async def submit_workflow_async(
        self,
        id: int,
        name: str,
        uuid_name: str,
        created_at: datetime,
        awpl: dict
    ) -> dict:
        async with ClientSession() as session:
            resp = await self._request_async(
                session=session,
                method='POST',
                resource='deployments',
                json={
                    "id": id,
                    "name": name,
                    "uuid_name": uuid_name,
                    "created_at": f'{created_at.isoformat()}',
                    "awpl": awpl,
                },
            )
        resp.raise_for_status()
        data = await resp.json()
        return data

    def submit_workflow(
        self,
        id: int,
        name: str,
        uuid_name: str,
        created_at: datetime,
        awpl: dict
    ) -> dict:
        self.logger.info(f'AWPL REST client: submit_workflow')
        resp = self.request(
            'POST',
            'deployments',
            json={
                "id": id,
                "name": name,
                "uuid_name": uuid_name,
                "created_at": f'{created_at.isoformat()}',
                "awpl": awpl,
            },
        )
        self.logger.info(f'AWPL REST client: submit_workflow status={resp.status_code}')
        resp.raise_for_status()
        data = resp.json()
        return data
