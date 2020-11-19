"""Test the Kostal Plenticore Solar Inverter config flow."""
from homeassistant import config_entries, setup
from homeassistant.components.kostal_plenticore.const import DOMAIN

from tests.async_mock import patch

from kostal.plenticore import PlenticoreAuthenticationException
from asyncio.exceptions import TimeoutError as AsyncIOTimeoutError


async def test_form(hass):
    """Test we get the form."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.kostal_plenticore.config_flow.test_connection",
        return_value=("scb", "123456789"),
    ), patch(
        "homeassistant.components.kostal_plenticore.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.kostal_plenticore.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "password": "test-password",
            },
        )

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Plenticore"
    assert result2["data"] == {
        "name": "Plenticore",
        "host": "1.1.1.1",
        "password": "test-password",
    }
    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_invalid_auth(hass):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.kostal_plenticore.config_flow.test_connection",
        side_effect=PlenticoreAuthenticationException(404, "invalid user"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "password": "test-password",
            },
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"password": "invalid_auth"}


async def test_form_cannot_connect(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.kostal_plenticore.config_flow.test_connection",
        side_effect=AsyncIOTimeoutError(),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "password": "test-password",
            },
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"host": "cannot_connect"}


async def test_already_configured(hass):
    """Test we handle already configured error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.kostal_plenticore.config_flow.configured_instances",
        return_value=set(["1.1.1.1"]),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "password": "test-password",
            },
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "already_configured"}
