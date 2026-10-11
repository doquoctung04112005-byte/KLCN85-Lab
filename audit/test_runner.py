import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test.runner import DiscoverRunner


class AuditIsolatedDiscoverRunner(DiscoverRunner):
    """Keep automated audit events out of the web server's persistent JSONL log."""

    def setup_test_environment(self, **kwargs):
        self._original_audit_log_file = settings.AUDIT_LOG_FILE
        self._audit_test_directory = TemporaryDirectory(prefix="klcn85-audit-tests-")
        settings.AUDIT_LOG_FILE = Path(self._audit_test_directory.name) / "audit.jsonl"
        self._close_audit_handler()
        super().setup_test_environment(**kwargs)

    def teardown_test_environment(self, **kwargs):
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            self._close_audit_handler()
            settings.AUDIT_LOG_FILE = self._original_audit_log_file
            self._audit_test_directory.cleanup()

    @staticmethod
    def _close_audit_handler():
        logger = logging.getLogger("audit.events")
        handler = getattr(logger, "_audit_file_handler", None)
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()
            del logger._audit_file_handler
        if hasattr(logger, "_audit_handler_configured"):
            del logger._audit_handler_configured
