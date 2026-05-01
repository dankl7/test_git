"""Telegram Ingestion Service"""
import asyncio
import structlog
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from common.models import RawMessage
from common.config import settings

logger = structlog.get_logger(__name__)

class TelegramIngestionService:
    def __init__(self, parser_service=None):
        self.parser_service = parser_service
        self.client = None
        self.monitors = {}
        self.messages_sent = 0
        self.messages_parsed = 0
        self._running = False
        self._scan_in_progress = False

    async def initialize(self):
        """Initialize Telegram client"""
        try:
            self.client = TelegramClient('wol_session', settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
            await self.client.start(phone=settings.TELEGRAM_PHONE)
            logger.info("✅ Telegram client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telegram: {e}")
            raise

    async def start_monitoring(self):
        """Start monitoring channels"""
        logger.info("📱 Starting monitoring...")
        self._running = True
        
        # Scan history first
        await self.scan_history()
        
        # Then listen for new messages
        await self.client.run_until_disconnected()

    async def scan_history(self):
        """Scan history for all monitored channels"""
        if self._scan_in_progress:
            return

        self._scan_in_progress = True
        logger.info("📚 Starting full history scan...")

        for key, monitor in self.monitors.items():
            try:
                logger.info(f"📚 Scanning history for {monitor.username}")

                # Get all messages
                all_messages = []
                async for message in self.client.iter_messages(monitor.chat_id, limit=None):
                    all_messages.append(message)

                processed_count = 0
                skipped_count = 0

                # Process messages
                for message in all_messages:
                    if message.id not in monitor.processed_message_ids:
                        await self._process_single_message(message, monitor)
                        monitor.processed_message_ids.add(message.id)
                        if message.id > monitor.last_message_id:
                            monitor.last_message_id = message.id
                        processed_count += 1
                    else:
                        skipped_count += 1

                monitor.scan_complete = True
                logger.info(
                    f"✅ Scan complete for {monitor.username}",
                    total=len(all_messages),
                    processed=processed_count,
                    skipped=skipped_count,
                    sent=self.messages_sent,
                    parsed=self.messages_parsed
                )

            except Exception as e:
                logger.error(f"❌ Error scanning history for {monitor.username}: {e}")

        self._scan_in_progress = False

    async def _process_single_message(self, message, monitor):
        """Process single message"""
        if not message.text or len(message.text.strip()) < 5:
            return

        try:
            chat = await message.get_chat()
            channel_username = getattr(chat, 'username', None) or str(getattr(chat, 'id', 'unknown'))
            message_link = f"https://t.me/{channel_username}/{message.id}"

            raw_message = RawMessage(
                id=f"msg_{message.id}",
                text=message.text,
                timestamp=message.date,
                channel_id=str(monitor.chat_id),
                message_link=message_link
            )

            logger.debug(
                f"📩 Message processed: {message.id}",
                channel=monitor.chat_id,
                has_text=bool(message.text),
                text_len=len(message.text) if message.text else 0
            )

            # Parse message
            if self.parser_service:
                await self.parser_service.parse_raw_message(raw_message)
                self.messages_sent += 1

        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}")

    async def add_channel(self, link, title=None):
        """Add channel to monitor"""
        try:
            entity = await self.client.get_entity(link)
            chat_id = entity.id
            username = getattr(entity, 'username', None) or str(chat_id)

            if chat_id not in self.monitors:
                self.monitors[chat_id] = type('obj', (object,), {
                    'chat_id': chat_id,
                    'username': username,
                    'title': title or username,
                    'last_message_id': 0,
                    'processed_message_ids': set(),
                    'scan_complete': False
                })
                logger.info(f"✅ Channel added: {username} ({chat_id})")
                return True
            else:
                logger.info(f"⏭️ Channel already exists: {username}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to add channel {link}: {e}")
            return False

    async def remove_channel(self, link):
        """Remove channel from monitoring"""
        try:
            entity = await self.client.get_entity(link)
            chat_id = entity.id

            if chat_id in self.monitors:
                del self.monitors[chat_id]
                logger.info(f"✅ Channel removed: {link}")
                return True
            else:
                logger.warning(f"⚠️ Channel not found: {link}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to remove channel {link}: {e}")
            return False

    def get_monitored_channels(self):
        """Get list of monitored channels"""
        return [
            {
                'id': m.chat_id,
                'username': m.username,
                'title': m.title,
                'scan_complete': m.scan_complete
            }
            for m in self.monitors.values()
        ]

    async def stop(self):
        """Stop monitoring"""
        self._running = False
        if self.client:
            await self.client.disconnect()
        logger.info("🛑 Monitoring stopped")
