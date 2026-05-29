"""
HubSpot Lead-Specific Operations
Implements lead fetching, detail retrieval, and JSON formatting for HubSpot contacts.
Handles pagination, date filtering, and property selection.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from contextlib import contextmanager

# Import from dependency files
from hubspot_client import HubSpotClient, HubSpotAPIError, handle_api_error

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HubSpot API constants
CONTACTS_ENDPOINT = "/crm/v3/objects/contacts"
SEARCH_ENDPOINT = f"{CONTACTS_ENDPOINT}/search"
ENGAGEMENTS_ENDPOINT = "/crm/v3/objects/engagements"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100

# Default contact properties to fetch if none specified
DEFAULT_CONTACT_PROPERTIES = [
    "firstname", "lastname", "email", "phone", "company",
    "jobtitle", "lifecyclestage", "lead_status", "createdate",
    "lastmodifieddate", "hs_lead_status", "hubspot_owner_id"
]


def fetch_new_leads(client: HubSpotClient, since_days: int = 7, 
                   max_leads: int = 100, properties: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Fetch new leads created within the specified number of days.
    
    Args:
        client: Initialized HubSpot client
        since_days: Number of days to look back for new leads
        max_leads: Maximum number of leads to fetch
        properties: List of contact properties to include
    
    Returns:
        List of lead dictionaries with requested properties
    """
    if not isinstance(client, HubSpotClient):
        raise ValueError("Invalid HubSpot client provided")
    
    # Validate and sanitize inputs
    since_days = max(0, int(since_days)) if since_days else 7
    max_leads = min(max(1, int(max_leads)), 10000) if max_leads else 100
    
    # Use default properties if none specified
    if not properties or not isinstance(properties, list):
        properties = DEFAULT_CONTACT_PROPERTIES
    else:
        # Sanitize and validate property names
        properties = [str(prop).strip() for prop in properties if prop]
        if not properties:
            properties = DEFAULT_CONTACT_PROPERTIES
    
    # Calculate the date filter
    since_date = datetime.utcnow() - timedelta(days=since_days)
    since_timestamp = int(since_date.timestamp() * 1000)  # HubSpot uses milliseconds
    
    # Build search query for new leads
    search_body = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": str(since_timestamp)
                    }
                ]
            }
        ],
        "properties": properties,
        "limit": min(max_leads, MAX_PAGE_SIZE),
        "after": 0
    }
    
    all_leads = []
    total_fetched = 0
    after_token = 0
    
    try:
        while total_fetched < max_leads:
            # Update pagination token
            if after_token:
                search_body["after"] = after_token
            
            # Adjust limit for last page if needed
            remaining = max_leads - total_fetched
            search_body["limit"] = min(remaining, MAX_PAGE_SIZE)
            
            # Make API request
            response = client.make_request(
                endpoint=SEARCH_ENDPOINT,
                method="POST",
                json_data=search_body
            )
            
            if not response or "results" not in response:
                logger.warning("No results found in HubSpot response")
                break
            
            # Process results
            results = response.get("results", [])
            if not results:
                break
            
            for contact in results:
                if total_fetched >= max_leads:
                    break
                    
                lead_data = _extract_contact_data(contact, properties)
                all_leads.append(lead_data)
                total_fetched += 1
            
            # Check for more pages
            paging = response.get("paging", {})
            next_page = paging.get("next", {})
            after_token = next_page.get("after")
            
            if not after_token:
                break
                
        logger.info(f"Successfully fetched {len(all_leads)} new leads from last {since_days} days")
        return all_leads
        
    except HubSpotAPIError as e:
        logger.error(f"HubSpot API error while fetching leads: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while fetching leads: {e}")
        raise


def get_lead_details(client: HubSpotClient, lead_id: Union[str, int], 
                    properties: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Get detailed information for a specific lead by ID.
    
    Args:
        client: Initialized HubSpot client
        lead_id: HubSpot contact ID
        properties: List of contact properties to include
    
    Returns:
        Dictionary containing lead details with requested properties
    """
    if not isinstance(client, HubSpotClient):
        raise ValueError("Invalid HubSpot client provided")
    
    # Validate and sanitize lead_id
    lead_id = str(lead_id).strip()
    if not lead_id or not lead_id.isdigit():
        raise ValueError(f"Invalid lead ID: {lead_id}")
    
    # Use default properties if none specified
    if not properties or not isinstance(properties, list):
        properties = DEFAULT_CONTACT_PROPERTIES
    else:
        # Sanitize property names
        properties = [str(prop).strip() for prop in properties if prop]
        if not properties:
            properties = DEFAULT_CONTACT_PROPERTIES
    
    try:
        # Build endpoint with properties query parameter
        endpoint = f"{CONTACTS_ENDPOINT}/{lead_id}"
        params = {
            "properties": ",".join(properties)
        }
        
        # Make API request
        response = client.make_request(
            endpoint=endpoint,
            method="GET",
            params=params
        )
        
        if not response:
            raise ValueError(f"No data returned for lead ID: {lead_id}")
        
        # Extract and format lead data
        lead_data = _extract_contact_data(response, properties)
        
        logger.info(f"Successfully retrieved details for lead ID: {lead_id}")
        return lead_data
        
    except HubSpotAPIError as e:
        logger.error(f"HubSpot API error while getting lead details: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while getting lead details: {e}")
        raise


def format_lead_json(hubspot_contact: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format HubSpot contact data into a standardized JSON structure.
    
    Args:
        hubspot_contact: Raw HubSpot contact object
    
    Returns:
        Formatted lead dictionary with consistent structure
    """
    if not hubspot_contact or not isinstance(hubspot_contact, dict):
        return {
            "id": None,
            "properties": {},
            "created_at": None,
            "updated_at": None,
            "archived": False
        }
    
    # Extract core fields
    formatted_lead = {
        "id": hubspot_contact.get("id"),
        "properties": {},
        "created_at": hubspot_contact.get("createdAt"),
        "updated_at": hubspot_contact.get("updatedAt"),
        "archived": hubspot_contact.get("archived", False)
    }
    
    # Process properties
    properties = hubspot_contact.get("properties", {})
    if isinstance(properties, dict):
        for prop_name, prop_value in properties.items():
            # Clean and normalize property values
            if prop_value is not None:
                formatted_lead["properties"][prop_name] = _normalize_property_value(prop_value)
    
    # Add computed fields
    if "firstname" in properties and "lastname" in properties:
        first = properties.get("firstname", "")
        last = properties.get("lastname", "")
        formatted_lead["full_name"] = f"{first} {last}".strip()
    
    # Add email as top-level field if present
    if "email" in properties:
        formatted_lead["email"] = properties.get("email")
    
    # Add lifecycle stage as top-level field if present
    if "lifecyclestage" in properties:
        formatted_lead["lifecycle_stage"] = properties.get("lifecyclestage")
    
    # Add lead status as top-level field if present
    for status_field in ["lead_status", "hs_lead_status"]:
        if status_field in properties:
            formatted_lead["lead_status"] = properties.get(status_field)
            break
    
    return formatted_lead


def _extract_contact_data(contact: Dict[str, Any], 
                          properties: List[str]) -> Dict[str, Any]:
    """
    Extract and structure contact data from HubSpot response.
    
    Args:
        contact: Raw contact object from HubSpot
        properties: List of properties to extract
    
    Returns:
        Structured contact dictionary
    """
    if not contact or not isinstance(contact, dict):
        return {}
    
    # Use format_lead_json for consistent formatting
    formatted = format_lead_json(contact)
    
    # Filter to only requested properties if specified
    if properties and properties != DEFAULT_CONTACT_PROPERTIES:
        filtered_props = {}
        for prop in properties:
            if prop in formatted.get("properties", {}):
                filtered_props[prop] = formatted["properties"][prop]
        formatted["properties"] = filtered_props
    
    return formatted


def _normalize_property_value(value: Any) -> Any:
    """
    Normalize property values for consistent output.
    
    Args:
        value: Raw property value from HubSpot
    
    Returns:
        Normalized value
    """
    if value is None:
        return None
    
    # Handle string values
    if isinstance(value, str):
        value = value.strip()
        # Convert empty strings to None
        if not value:
            return None
        # Try to parse dates
        if "T" in value and ("Z" in value or "+" in value):
            try:
                # Attempt to parse ISO format dates
                return value  # Keep as string for JSON compatibility
            except:
                pass
        return value
    
    # Handle numeric values
    if isinstance(value, (int, float)):
        return value
    
    # Handle boolean values
    if isinstance(value, bool):
        return value
    
    # Handle list/array values
    if isinstance(value, list):
        return [_normalize_property_value(item) for item in value]
    
    # Handle dict/object values
    if isinstance(value, dict):
        return {k: _normalize_property_value(v) for k, v in value.items()}
    
    # Default: convert to string
    return str(value)


def filter_leads_by_status(leads: List[Dict[str, Any]], 
                          status_filter: str) -> List[Dict[str, Any]]:
    """
    Filter leads by their status value.
    
    Args:
        leads: List of lead dictionaries
        status_filter: Status value to filter by
    
    Returns:
        Filtered list of leads matching the status
    """
    if not status_filter or not isinstance(status_filter, str):
        return leads
    
    status_filter = status_filter.strip().lower()
    if not status_filter:
        return leads
    
    filtered_leads = []
    for lead in leads:
        lead_status = lead.get("lead_status", "")
        if not lead_status:
            # Check in properties
            props = lead.get("properties", {})
            lead_status = props.get("lead_status") or props.get("hs_lead_status") or ""
        
        if lead_status and str(lead_status).strip().lower() == status_filter:
            filtered_leads.append(lead)
    
    return filtered_leads


def add_engagement_data(client: HubSpotClient, 
                       leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add engagement data to leads if requested.
    
    Args:
        client: Initialized HubSpot client
        leads: List of lead dictionaries
    
    Returns:
        Leads with engagement data added
    """
    if not leads or not isinstance(client, HubSpotClient):
        return leads
    
    for lead in leads:
        lead_id = lead.get("id")
        if not lead_id:
            continue
        
        try:
            # Fetch engagements for this contact
            endpoint = f"{ENGAGEMENTS_ENDPOINT}/search"
            search_body = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "associations.contact",
                                "operator": "EQ",
                                "value": str(lead_id)
                            }
                        ]
                    }
                ],
                "limit": 10
            }
            
            response = client.make_request(
                endpoint=endpoint,
                method="POST",
                json_data=search_body
            )
            
            engagements = response.get("results", [])
            lead["engagement_count"] = len(engagements)
            lead["recent_engagements"] = engagements[:5]  # Keep only 5 most recent
            
        except Exception as e:
            logger.warning(f"Failed to fetch engagement data for lead {lead_id}: {e}")
            lead["engagement_count"] = 0
            lead["recent_engagements"] = []
    
    return leads