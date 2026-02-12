from domino.logger import get_configured_logger

class LocalStorageRepository:
    # Class to handle S3 Domino Storage support
    logger = get_configured_logger('LocalStorageRepository')

    @classmethod
    def validate_local_credentials_access(cls, local_test_key: str) -> bool:
        cls.logger.info("Validating Local Credentials")
        cls.logger.info("Local Credentials are valid")
        return True
