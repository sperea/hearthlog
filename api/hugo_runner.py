import subprocess
import logging

logger = logging.getLogger(__name__)

HUGO_SOURCE = "/blog-content"


def rebuild_site(_container_name: str = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["hugo", "--minify", "--source", HUGO_SOURCE],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("Hugo build success")
            return True, result.stdout
        logger.error("Hugo build failed: %s", result.stderr)
        return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Hugo build timed out after 60s"
    except FileNotFoundError:
        return False, "hugo binary not found"
    except Exception as e:
        return False, str(e)
