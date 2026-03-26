from urllib.parse import urljoin

import requests

from core.logger import get_configured_logger
from core.settings import settings


class ChatRestClient(requests.Session):
    api_url = settings.CHAT_APP_URL
    api_token = settings.CHAT_APP_TOKEN

    @classmethod
    def _get_jwt_token(cls) -> str | None:
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
            url = urljoin(self.api_url + '/', resource)
            response = super().request(method, url, **kwargs)
            if response.status_code == 401:
                self.jwt_token = self._get_jwt_token()
                self.headers.update({"Authorization": f"Bearer {self.jwt_token}"})
                return super().request(method, url, **kwargs)
            self.logger.debug(f'Chat REST client: method={method}, url={url}, kwargs={kwargs}')
            return response
        except Exception as e:
            self.logger.exception(e)
            raise e

    def send_message(self, messages: list[dict], workspace_id: int) -> dict:
        resp = self.request(
            'POST',
            'chat',
            json={"messages": messages, "workspace_id": workspace_id},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()
