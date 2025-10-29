"""Simple text processing integration."""

from __future__ import annotations

import logging
from typing import Literal

import asyncio

import aiohttp.web
from homeassistant.components import conversation, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.network import get_url
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.util import ulid

# Constants
DOMAIN = "home_assistant_node_red_conversation"
DEFAULT_NAME = "Home Assistant Node Red Conversation"
EVENT_CONVERSATION_FINISHED = "home_assistant_node_red_conversation.conversation.finished"

# Configuration keys
CONF_WEBHOOK_SEND_ID = "webhook_send_id"
CONF_WEBHOOK_RECEIVE_ID = "webhook_receive_id"
CONF_TIMEOUT = "timeout"
CONF_ERROR_MESSAGE = "error_message"

# Defaults
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_ERROR_MESSAGE = "Error"
DEFAULT_WEBHOOK_SEND_ID = "noderedsend"
DEFAULT_WEBHOOK_RECEIVE_ID = "noderedreceive"

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    # Store for pending webhook responses
    hass.data.setdefault(DOMAIN, {})["pending_responses"] = {}
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Get receive webhook ID from config
    webhook_receive_id = entry.options.get(CONF_WEBHOOK_RECEIVE_ID, DEFAULT_WEBHOOK_RECEIVE_ID)
    
    # Register webhook receiver if configured
    if webhook_receive_id:
        async def handle_webhook(hass, webhook_id, request):
            """Handle incoming webhook response."""
            try:
                # Parse JSON data from webhook
                data = await request.json()
                
                request_id = data.get("request_id")
                response_text = data.get("response", "").strip()
                
                if request_id and response_text and DOMAIN in hass.data:
                    hass.data[DOMAIN].setdefault("pending_responses", {})[request_id] = response_text
                    _LOGGER.info(f"Received webhook response for {request_id}: {response_text}")
                    # Return success response
                    return aiohttp.web.json_response({"status": "ok"})
                else:
                    _LOGGER.warning(f"Invalid webhook data: request_id={request_id}, response={response_text}")
                    return aiohttp.web.json_response({"status": "error", "message": "Invalid data"}, status=400)
            except Exception as e:
                _LOGGER.error(f"Error handling webhook: {e}")
                return aiohttp.web.json_response({"status": "error", "message": str(e)}, status=500)
        
        webhook.async_register(
            hass,
            DOMAIN,
            "Webhook Receiver",
            webhook_receive_id,
            handle_webhook,
        )
    
    agent = SimpleTextAgent(hass, entry)

    data = hass.data.setdefault(DOMAIN, {})
    data[entry.entry_id] = agent

    conversation.async_set_agent(hass, entry, agent)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload integration."""
    hass.data[DOMAIN].pop(entry.entry_id)
    conversation.async_unset_agent(hass, entry)
    return True


class SimpleTextAgent(conversation.AbstractConversationAgent):
    """Simple text processing agent with webhook support."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry
        self._pending_requests: dict[str, asyncio.Event] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process user input via webhook."""
        conversation_id = user_input.conversation_id or ulid.ulid()
        user_input.conversation_id = conversation_id

        # Get configuration
        webhook_send_id = self.entry.options.get(CONF_WEBHOOK_SEND_ID, DEFAULT_WEBHOOK_SEND_ID)
        webhook_receive_id = self.entry.options.get(CONF_WEBHOOK_RECEIVE_ID, DEFAULT_WEBHOOK_RECEIVE_ID)
        timeout = self.entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        error_message = self.entry.options.get(CONF_ERROR_MESSAGE, DEFAULT_ERROR_MESSAGE)

        response_text = error_message

        if webhook_send_id:
            try:
                # Generate unique request ID
                request_id = ulid.ulid()
                
                # Send to webhook
                _LOGGER.info(f"Sending webhook request {request_id} to {webhook_send_id}")
                
                # Build webhook URL
                base_url = get_url(self.hass, prefer_external=False)
                webhook_url = f"{base_url}/api/webhook/{webhook_send_id}"
                
                # POST to webhook using httpx client
                client = get_async_client(self.hass)
                
                # Prepare webhook payload
                webhook_payload = {
                    "request_id": request_id,
                    "message": user_input.text,
                    "conversation_id": conversation_id,
                }
                
                # Add satellite_id (always included, null if not available)
                satellite_id = None
                if hasattr(user_input, 'context') and user_input.context is not None:
                    satellite_id = getattr(user_input.context, 'satellite_id', None)
                webhook_payload["satellite_id"] = satellite_id
                
                resp = await client.post(
                    webhook_url,
                    json=webhook_payload,
                )
                _LOGGER.info(f"Webhook response status: {resp.status_code}")
                
                # Wait for response on receive webhook with timeout
                if webhook_receive_id:
                    pending = self.hass.data[DOMAIN].get("pending_responses", {})
                    start_time = asyncio.get_event_loop().time()
                    
                    while asyncio.get_event_loop().time() - start_time < timeout:
                        if request_id in pending:
                            response_text = pending.pop(request_id)
                            _LOGGER.info(f"Received response for {request_id}: {response_text}")
                            break
                        await asyncio.sleep(0.1)
                    else:
                        _LOGGER.warning(f"Timeout waiting for webhook response {request_id}")
                    
            except Exception as err:
                _LOGGER.error(f"Webhook error: {err}")
        
        # Fire event
        self.hass.bus.async_fire(
            EVENT_CONVERSATION_FINISHED,
            {
                "response": response_text,
                "user_input": user_input.text,
            },
        )

        # Create intent response
        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response_text)
        
        return conversation.ConversationResult(
            response=intent_response, conversation_id=conversation_id
        )
