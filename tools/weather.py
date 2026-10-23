import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from langchain_core.tools import tool
from objprint import op
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


OPEN_WEATHER_API_KEY = os.getenv("OPEN_WEATHER_API_KEY")


class CurrentWeatherParams(BaseModel):
    latitude: float = Field(
        description="The latitude of the location for which to retrieve current weather information."
    )
    longitude: float = Field(
        description="The longitude of the location for which to retrieve current weather information."
    )


@tool(args_schema=CurrentWeatherParams, description="Retrieve current weather information for a specific location")
def get_current_weather(latitude: float, longitude: float) -> dict:
    """
    Queries OpenWeatherMap's current weather endpoint for a specific location.

    Units options:
    - "metric" (Celsius, meters/sec)
    - "imperial" (Fahrenheit, miles/hour)
    - "standard" (Kelvin, meters/sec - Default if omitted)
    """
    # The actual REST API base endpoint for current weather
    base_url = "https://api.openweathermap.org/data/2.5/weather"

    # Map out the exact query parameters the API expects
    params = {"lat": latitude, "lon": longitude, "appid": OPEN_WEATHER_API_KEY, "units": "metric"}

    try:
        response = requests.get(base_url, params=params)

        # Automatically catches HTTP errors like 401 (invalid key) or 404 (wrong location)
        response.raise_for_status()

        # Parse the JSON payload directly into a Python dictionary
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        if response.status_code == 401:
            print("👉 Tip: Your API key might be missing, invalid, or still activating.")
        elif response.status_code == 404:
            print("👉 Tip: Location not found. Double-check the spelling or formatting.")
    except Exception as err:  # noqa: BLE001
        print(f"An unexpected error occurred: {err}")

    return None


if __name__ == "__main__":
    weather_payload = get_current_weather.invoke(
        {"latitude": 51.3396, "longitude": 12.3764}
    )  # Coordinates for Leipzig, Germany

    if weather_payload:
        op(weather_payload)
