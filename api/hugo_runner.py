import subprocess
import logging

logger = logging.getLogger(__name__)


def rebuild_site(container_name: str = "hugo-generator") -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "hugo", "--minify"],
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
        return False, "docker CLI not found in container"
    except Exception as e:
        return False, str(e)
