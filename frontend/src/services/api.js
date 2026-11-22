
import { API_BASE_URL } from "../config";

const REQUEST_TIMEOUT = 15000;

export class ApiError extends Error {
  constructor(message, status = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiRequest(path, options = {}) {
  if (!API_BASE_URL) {
    throw new ApiError("API base URL is not configured.");
  }

  const controller = new AbortController();

  const timeoutId = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      signal: controller.signal,
    });

    const responseText = await response.text();

    let data = null;

    if (responseText) {
      try {
        data = JSON.parse(responseText);
      } catch {
        throw new ApiError("Server returned an invalid JSON response.");
      }
    }

    if (!response.ok) {
      throw new ApiError(
        `Request failed with status ${response.status}.`,
        response.status
      );
    }

    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    if (error.name === "AbortError") {
      throw new ApiError("Request timed out. Please try again.");
    }

    throw new ApiError("Unable to connect to the server.");
  } finally {
    clearTimeout(timeoutId);
  }
}
