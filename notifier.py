"""Notification handlers: Telegram and Email."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiohttp

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram Bot API."""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.url = self.API_URL.format(token=bot_token)

    async def send(self, post: dict) -> bool:
        """Send a single post notification."""
        message = self._format_post(post)
        return await self._send_message(message)

    async def send_summary(self, new_count: int, total_count: int) -> bool:
        """Send a run summary."""
        from datetime import datetime

        message = (
            f"<b>Scraping Complete</b>\n\n"
            f"New listings: <b>{new_count}</b>\n"
            f"Total in database: {total_count}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        if new_count == 0:
            message += "\n\nNo new matching posts found this run."
        return await self._send_message(message)

    async def send_error(self, error_msg: str) -> bool:
        """Send an error notification."""
        message = f"<b>Scraper Error</b>\n\n{error_msg}"
        return await self._send_message(message)

    async def _send_message(self, text: str) -> bool:
        """Send a message via Telegram Bot API."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    body = await resp.text()
                    logger.error(f"Telegram API error {resp.status}: {body}")
                    return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def _format_post(self, post: dict) -> str:
        """Format a post into a readable Telegram message."""
        location = post.get("location", "Unknown")
        price = post.get("price")
        price_str = f"₹{price:,}/month" if price else "Not mentioned"
        contact = post.get("contact", "Not available")
        bhk = post.get("bhk_type", "")
        description = post.get("description", "")
        post_url = post.get("post_url", "")
        group = post.get("group_name", "")
        score = post.get("relevance_score", 0)

        # Truncate description
        if len(description) > 300:
            description = description[:300] + "..."

        lines = [
            "🏠 <b>New Flat Listing Found!</b>",
            "",
            f"📍 Location: <b>{location}</b>",
            f"💰 Price: <b>{price_str}</b>",
        ]
        if bhk:
            lines.append(f"🏗 Type: {bhk}")
        if contact:
            lines.append(f"📞 Contact: {contact}")
        lines.append(f"📊 Relevance: {score:.0%}")
        if group:
            lines.append(f"👥 Group: {group}")
        lines.append("")
        lines.append(f"📝 {description}")
        if post_url:
            lines.append("")
            lines.append(f"🔗 <a href='{post_url}'>View Post</a>")

        return "\n".join(lines)


class EmailNotifier:
    """Send notifications via email (SMTP)."""

    def __init__(self, smtp_config: dict):
        self.host = smtp_config["smtp_host"]
        self.port = smtp_config["smtp_port"]
        self.email = smtp_config["smtp_email"]
        self.password = smtp_config["smtp_password"]
        self.recipient = smtp_config["notify_email"]

    async def send(self, post: dict) -> bool:
        """Send a post notification via email."""
        subject = f"Flat Alert: {post.get('location', 'Hyderabad')} - ₹{post.get('price', 'N/A')}"
        body = self._format_html(post)
        return self._send_email(subject, body)

    async def send_summary(self, new_count: int, total_count: int) -> bool:
        """Send run summary via email."""
        subject = f"Flat Finder: {new_count} new listings found"
        body = f"<p>New listings: <strong>{new_count}</strong></p><p>Total: {total_count}</p>"
        return self._send_email(subject, body)

    async def send_error(self, error_msg: str) -> bool:
        """Send error notification via email."""
        return self._send_email("Flat Finder Error", f"<p>{error_msg}</p>")

    def _send_email(self, subject: str, html_body: str) -> bool:
        """Send an HTML email."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email
            msg["To"] = self.recipient
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.sendmail(self.email, self.recipient, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    def _format_html(self, post: dict) -> str:
        """Format post as HTML email body."""
        price = post.get("price")
        price_str = f"₹{price:,}" if price else "Not mentioned"
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2 style="color: #2c3e50;">New Flat Listing</h2>
            <table style="border-collapse: collapse; width: 100%;">
                <tr><td style="padding: 8px; font-weight: bold;">Location:</td>
                    <td style="padding: 8px;">{post.get('location', 'Unknown')}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Price:</td>
                    <td style="padding: 8px;">{price_str}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Contact:</td>
                    <td style="padding: 8px;">{post.get('contact', 'N/A')}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Group:</td>
                    <td style="padding: 8px;">{post.get('group_name', '')}</td></tr>
            </table>
            <p style="margin-top: 16px;">{post.get('description', '')[:500]}</p>
            <p><a href="{post.get('post_url', '#')}">View on Facebook</a></p>
        </div>
        """


def get_notifiers(env_config: dict) -> list:
    """Factory: create available notifiers based on configured credentials."""
    notifiers = []

    if env_config.get("telegram_bot_token") and env_config.get("telegram_chat_id"):
        notifiers.append(
            TelegramNotifier(env_config["telegram_bot_token"], env_config["telegram_chat_id"])
        )
        logger.info("Telegram notifier enabled")

    if (
        env_config.get("smtp_host")
        and env_config.get("smtp_email")
        and env_config.get("smtp_password")
        and env_config.get("notify_email")
    ):
        notifiers.append(EmailNotifier(env_config))
        logger.info("Email notifier enabled")

    if not notifiers:
        logger.warning("No notification channels configured")

    return notifiers
