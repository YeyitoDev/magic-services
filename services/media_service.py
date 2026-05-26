"""
Media Service - File ID based (zero storage)
=============================================
Uses Telegram file_id for all images/videos. No local files needed.

How it works:
1. Upload media once → get file_id from Telegram
2. Store file_id in media_config.json
3. Send using file_id → no files on disk, no LFS, no Docker issues

To update a file_id: just edit media_config.json

Usage:
    from services.media_service import MediaService
    media = MediaService()
    await media.send_photo(context, chat_id, "stake_pricing", caption="...")
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

MEDIA_CONFIG_PATH = "media_config.json"


class MediaService:
    """Sends media using Telegram file_id instead of local files."""

    def __init__(self):
        self._config = self._load_config()

    def _load_config(self) -> dict:
        if os.path.exists(MEDIA_CONFIG_PATH):
            with open(MEDIA_CONFIG_PATH) as f:
                return json.load(f)
        return {"photos": {}, "videos": {}, "updated_at": None}

    def _get_file_id(self, name: str, media_type: str = "photos") -> Optional[str]:
        return self._config.get(media_type, {}).get(name)

    async def send_photo(self, context, chat_id: str, name: str, caption: str = "", parse_mode: str = "HTML") -> bool:
        """Send a photo by its file_id name (e.g., 'stake_pricing', 'vip_pricing')."""
        file_id = self._get_file_id(name, "photos")
        if not file_id:
            logger.error(f"File ID not found for photo '{name}'")
            return False
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption,
                parse_mode=parse_mode,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send photo '{name}': {e}")
            return False

    async def send_video(self, context, chat_id: str, name: str, caption: str = "", parse_mode: str = "HTML") -> bool:
        """Send a video by its file_id name (e.g., 'grupo_vip_explicacion')."""
        file_id = self._get_file_id(name, "videos")
        if not file_id:
            logger.error(f"File ID not found for video '{name}'")
            return False
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=file_id,
                caption=caption,
                parse_mode=parse_mode,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send video '{name}': {e}")
            return False

    def get_file_ids_status(self) -> dict:
        """Returns which file_ids are configured."""
        return {
            "photos_configured": list(self._config.get("photos", {}).keys()),
            "videos_configured": list(self._config.get("videos", {}).keys()),
            "total_photos": len(self._config.get("photos", {})),
            "total_videos": len(self._config.get("videos", {})),
        }


# Global instance
media_service = MediaService()
