"""Email notification service for alerts."""

import asyncio
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class EmailConfig:
    """Email configuration."""
    smtp_server: str = ""
    smtp_port: int = 587
    sender_email: str = ""
    sender_password: str = ""  # App password for Gmail
    recipient_emails: List[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "EmailConfig":
        """Load configuration from environment variables."""
        recipients_str = os.getenv("RECIPIENT_EMAILS", "")
        recipients = [e.strip() for e in recipients_str.split(",") if e.strip()]

        return cls(
            smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            sender_email=os.getenv("SENDER_EMAIL", ""),
            sender_password=os.getenv("SENDER_PASSWORD", ""),
            recipient_emails=recipients,
        )


class NotificationService:
    """Service for sending notifications."""

    def __init__(self, config: EmailConfig = None):
        self.config = config or EmailConfig()
        self._enabled = bool(self.config.sender_email and self.config.sender_password)

    def is_enabled(self) -> bool:
        """Check if email notifications are enabled."""
        return self._enabled

    async def send_email(
        self,
        subject: str,
        html_content: str,
        recipient: str = None
    ) -> bool:
        """Send an email notification."""
        if not self._enabled:
            print("Email notifications not configured")
            return False

        recipients = [recipient] if recipient else self.config.recipient_emails
        if not recipients:
            print("No recipients configured")
            return False

        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.config.sender_email
            message["To"] = ", ".join(recipients)

            # Add HTML content
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)

            # Send email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.config.sender_email, self.config.sender_password)
                server.sendmail(
                    self.config.sender_email,
                    recipients,
                    message.as_string()
                )

            print(f"Email sent to {', '.join(recipients)}")
            return True

        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    async def send_restock_alert(
        self,
        product_name: str,
        brand: str,
        platform: str,
        price: float,
        url: str
    ) -> bool:
        """Send a restock notification."""
        subject = f"🎉 补货提醒: {brand} {product_name}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #00d4ff, #00ff88); color: #000; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .product {{ background: #f9f9f9; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .price {{ font-size: 2em; color: #00aa55; font-weight: bold; }}
                .btn {{ display: inline-block; background: #00d4ff; color: #000; padding: 15px 30px; text-decoration: none; border-radius: 25px; font-weight: bold; margin-top: 20px; }}
                .footer {{ background: #333; color: #888; padding: 20px; text-align: center; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🐟 补货提醒</h1>
                </div>
                <div class="content">
                    <h2>好消息！您关注的产品已补货</h2>
                    <div class="product">
                        <h3>{brand}</h3>
                        <p><strong>{product_name}</strong></p>
                        <p class="price">S${price:.2f}</p>
                        <p>平台: {platform}</p>
                    </div>
                    <a href="{url}" class="btn">立即购买 →</a>
                </div>
                <div class="footer">
                    <p>Grocery Manager 库存监控系统</p>
                    <p>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self.send_email(subject, html_content)

    async def send_price_drop_alert(
        self,
        product_name: str,
        brand: str,
        platform: str,
        old_price: float,
        new_price: float,
        url: str
    ) -> bool:
        """Send a price drop notification."""
        discount = ((old_price - new_price) / old_price) * 100
        subject = f"💰 降价提醒: {brand} {product_name} 降价{discount:.0f}%"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #ff6b6b, #feca57); color: #000; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .product {{ background: #f9f9f9; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .price-old {{ font-size: 1.2em; color: #999; text-decoration: line-through; }}
                .price-new {{ font-size: 2em; color: #ff6b6b; font-weight: bold; }}
                .discount {{ background: #ff6b6b; color: #fff; padding: 5px 15px; border-radius: 15px; font-weight: bold; }}
                .btn {{ display: inline-block; background: #ff6b6b; color: #fff; padding: 15px 30px; text-decoration: none; border-radius: 25px; font-weight: bold; margin-top: 20px; }}
                .footer {{ background: #333; color: #888; padding: 20px; text-align: center; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>💰 降价提醒</h1>
                </div>
                <div class="content">
                    <h2>您关注的产品降价了！</h2>
                    <div class="product">
                        <h3>{brand}</h3>
                        <p><strong>{product_name}</strong></p>
                        <p class="price-old">S${old_price:.2f}</p>
                        <p class="price-new">S${new_price:.2f} <span class="discount">-{discount:.0f}%</span></p>
                        <p>平台: {platform}</p>
                    </div>
                    <a href="{url}" class="btn">立即购买 →</a>
                </div>
                <div class="footer">
                    <p>Grocery Manager 库存监控系统</p>
                    <p>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self.send_email(subject, html_content)

    async def send_weekly_summary(
        self,
        available_products: List[dict],
        unavailable_products: List[dict],
        total_cost: float
    ) -> bool:
        """Send weekly shopping summary."""
        subject = f"📋 每周采购清单 - {datetime.now().strftime('%Y-%m-%d')}"

        available_html = ""
        for p in available_products:
            available_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">{p['brand']} {p['name']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">{p['quantity']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">{p['platform']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">S${p['price']:.2f}</td>
            </tr>
            """

        unavailable_html = ""
        for p in unavailable_products:
            unavailable_html += f"<li>{p['brand']} {p['name']}</li>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
                .container {{ max-width: 700px; margin: 0 auto; background: #fff; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: #00d4ff; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #00d4ff; color: #000; padding: 12px; text-align: left; }}
                .total {{ font-size: 1.5em; color: #00aa55; font-weight: bold; text-align: right; margin-top: 20px; }}
                .unavailable {{ background: #fff3cd; padding: 15px; border-radius: 10px; margin-top: 20px; }}
                .footer {{ background: #333; color: #888; padding: 20px; text-align: center; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🐟 每周采购清单</h1>
                    <p>{datetime.now().strftime('%Y年%m月%d日')}</p>
                </div>
                <div class="content">
                    <h2>可购买产品</h2>
                    <table>
                        <tr>
                            <th>产品</th>
                            <th>数量</th>
                            <th>平台</th>
                            <th>价格</th>
                        </tr>
                        {available_html}
                    </table>
                    <p class="total">总计: S${total_cost:.2f}</p>

                    {f'<div class="unavailable"><h3>⚠️ 缺货产品</h3><ul>{unavailable_html}</ul></div>' if unavailable_products else ''}
                </div>
                <div class="footer">
                    <p>Grocery Manager 库存监控系统</p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self.send_email(subject, html_content)


# Global notification service instance (loads from environment)
notification_service = NotificationService(EmailConfig.from_env())


def configure_email(
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
    sender_email: str = "",
    sender_password: str = "",
    recipient_emails: List[str] = None
):
    """Configure email notifications."""
    global notification_service
    config = EmailConfig(
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        sender_email=sender_email,
        sender_password=sender_password,
        recipient_emails=recipient_emails or []
    )
    notification_service = NotificationService(config)
    return notification_service


def reload_config():
    """Reload configuration from environment variables."""
    global notification_service
    notification_service = NotificationService(EmailConfig.from_env())
    return notification_service
