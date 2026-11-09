import os
import httpx


class OllamaError(Exception):
    """Raised when the Ollama server can't be reached or returns an error."""


class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None, timeout: float = 120.0):
        # Config comes from environment variables, with safe defaults
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.timeout = timeout

    def is_available(self) -> bool:
        """Return True if the Ollama server is running."""
        try:
            return httpx.get(self.host, timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        """Send a prompt to Ollama and return the model's text response."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        try:
            resp = httpx.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama request failed: {e}") from e

        return resp.json()["response"]


if __name__ == "__main__":
    client = OllamaClient()
    email = "Welcome to ShopX! Enjoy 10% off your first order with code WELCOME10."
    print(client.generate(
        prompt=(
            "Classify this email as welcome, cart_abandonment, or campaign. "
            'Reply as JSON like {"type": "...", "confidence": 0.0}.\n\n'
            f"Email: {email}"
        ),
        json_mode=True,
    ))