"""
HubSpot API Client Wrapper
Handles authentication, base request construction, and response parsing for HubSpot API operations.
"""

import json
import time
import logging
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urljoin, urlencode
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HubSpot API Constants
HUBSPOT_API_BASE_URL = "https://api.hubapi.com"
API_VERSION = "/crm/v3"
CONTACTS_ENDPOINT = f"{API_VERSION}/objects/contacts"
ENGAGEMENTS_ENDPOINT = f"{API_VERSION}/objects/engagements"
SEARCH_ENDPOINT = f"{CONTACTS_ENDPOINT}/search"

# Rate limiting constants
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.0
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
REQUEST_TIMEOUT = 30


class HubSpotAPIError(Exception):
    """Custom exception for HubSpot API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)


class HubSpotClient:
    """Lightweight HubSpot API client with authentication and request handling"""
    
    def __init__(self, api_key: str):
        """Initialize the HubSpot client with API key"""
        if not api_key or not isinstance(api_key, str):
            raise ValueError("Valid HubSpot API key is required")
        
        self.api_key = api_key.strip()
        self.base_url = HUBSPOT_API_BASE_URL
        self.session = self._create_session()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy"""
        session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    @contextmanager
    def _request_context(self):
        """Context manager for handling requests with proper cleanup"""
        try:
            yield
        finally:
            # Ensure connection cleanup
            pass
    
    def validate_api_key(self) -> bool:
        """Validate the API key by making a test request"""
        try:
            endpoint = f"{CONTACTS_ENDPOINT}?limit=1"
            response = self.session.get(
                urljoin(self.base_url, endpoint),
                headers=self.headers,
                timeout=REQUEST_TIMEOUT
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"API key validation failed: {str(e)}")
            return False
    
    def make_request(self, endpoint: str, method: str = "GET", 
                    params: Optional[Dict[str, Any]] = None,
                    data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an API request with proper error handling and retries"""
        with self._request_context():
            url = urljoin(self.base_url, endpoint)
            
            # Sanitize and validate inputs
            method = method.upper().strip()
            if method not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                raise ValueError(f"Invalid HTTP method: {method}")
            
            # Prepare request parameters
            request_kwargs = {
                "headers": self.headers,
                "timeout": REQUEST_TIMEOUT
            }
            
            if params:
                # Sanitize parameters
                sanitized_params = {
                    str(k): str(v) if v is not None else ""
                    for k, v in params.items()
                }
                request_kwargs["params"] = sanitized_params
            
            if data and method in ["POST", "PUT", "PATCH"]:
                request_kwargs["json"] = data
            
            try:
                response = self.session.request(method, url, **request_kwargs)
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    # Retry the request
                    response = self.session.request(method, url, **request_kwargs)
                
                response.raise_for_status()
                
                # Parse response
                if response.content:
                    return response.json()
                return {}
                
            except requests.exceptions.HTTPError as e:
                error_body = {}
                try:
                    error_body = e.response.json() if e.response.content else {}
                except:
                    pass
                
                raise HubSpotAPIError(
                    message=f"HubSpot API error: {str(e)}",
                    status_code=e.response.status_code if e.response else None,
                    response_body=error_body
                )
            
            except requests.exceptions.RequestException as e:
                raise HubSpotAPIError(f"Request failed: {str(e)}")
            
            except Exception as e:
                raise HubSpotAPIError(f"Unexpected error: {str(e)}")
    
    def close(self):
        """Close the session and cleanup resources"""
        if self.session:
            self.session.close()


def initialize_client(api_key: str) -> HubSpotClient:
    """Initialize and return a HubSpot client instance"""
    if not api_key:
        raise ValueError("HubSpot API key is required")
    
    # Sanitize API key
    api_key = str(api_key).strip()
    
    client = HubSpotClient(api_key)
    
    # Validate the API key
    if not client.validate_api_key():
        client.close()
        raise HubSpotAPIError("Invalid HubSpot API key or authentication failed")
    
    return client


def make_api_request(endpoint: str, method: str = "GET", 
                    params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make an API request using the initialized client"""
    # This function expects the client to be initialized externally
    # and passed through context or stored in a module-level variable
    raise NotImplementedError(
        "This function requires an initialized client. "
        "Use client.make_request() directly after initializing with initialize_client()"
    )


def handle_api_error(response: Union[Dict, requests.Response, Exception]) -> Dict[str, Any]:
    """Handle and format API errors consistently"""
    error_info = {
        "error": True,
        "message": "Unknown error occurred",
        "status_code": None,
        "details": {}
    }
    
    if isinstance(response, HubSpotAPIError):
        error_info["message"] = response.message
        error_info["status_code"] = response.status_code
        error_info["details"] = response.response_body or {}
    
    elif isinstance(response, requests.Response):
        error_info["status_code"] = response.status_code
        error_info["message"] = f"HTTP {response.status_code}: {response.reason}"
        try:
            error_body = response.json()
            error_info["details"] = error_body
            if "message" in error_body:
                error_info["message"] = error_body["message"]
        except:
            error_info["details"] = {"raw": response.text[:500] if response.text else ""}
    
    elif isinstance(response, dict):
        error_info["message"] = response.get("message", "API error occurred")
        error_info["status_code"] = response.get("status_code")
        error_info["details"] = response.get("details", response)
    
    elif isinstance(response, Exception):
        error_info["message"] = str(response)
        error_info["details"] = {"exception_type": type(response).__name__}
    
    logger.error(f"API Error: {error_info['message']}")
    return error_info