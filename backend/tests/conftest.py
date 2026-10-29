import os
import tempfile

# Settings are read at import time, so point DATA_DIR somewhere disposable first.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="wmr-test-"))
os.environ.setdefault("MAX_UPLOAD_MB", "1")
