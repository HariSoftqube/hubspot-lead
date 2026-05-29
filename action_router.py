"""
Action Router for HubSpot Lead Capture Machine
Routes actions to appropriate handlers and returns standardized responses.
Maps 'fetch_new_leads' and 'get_lead_by_id' actions to lead_actions functions.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from hubspot_client import initialize_client, HubSpotClient, HubSpotAPIError, handle_api_error
from lead_actions import (
    fetch_new_leads,
    get_lead_details,
    filter_leads_by_status,
    add_engagement_data
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supported actions
SUPPORTED_ACTIONS = {
    'fetch_new_leads': 'Fetch new leads from HubSpot',
    'get_lead_by_id': 'Get details for a specific lead',
    'fetch_filtered_leads': 'Fetch leads with status filter',
    'fetch_leads_with_engagement': 'Fetch leads with engagement data'
}

# Required parameters for each action
ACTION_REQUIRED_PARAMS = {
    'fetch_new_leads': [],
    'get_lead_by_id': ['lead_id'],
    'fetch_filtered_leads': [],
    'fetch_leads_with_engagement': []
}

# Optional parameters for each action
ACTION_OPTIONAL_PARAMS = {
    'fetch_new_leads': ['fetch_new_leads_since_days', 'max_leads_per_fetch', 'include_contact_properties'],
    'get_lead_by_id': ['include_contact_properties'],
    'fetch_filtered_leads': ['fetch_new_leads_since_days', 'max_leads_per_fetch', 'include_contact_properties', 'lead_status_filter'],
    'fetch_leads_with_engagement': ['fetch_new_leads_since_days', 'max_leads_per_fetch', 'include_contact_properties', 'include_engagement_data']
}


def validate_action_params(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate action parameters before execution.
    
    Args:
        action: The action to validate
        params: Parameters dictionary to validate
    
    Returns:
        Dictionary with validation status and cleaned parameters
    
    Raises:
        ValueError: If validation fails
    """
    if not action:
        raise ValueError("Action is required but not provided")
    
    action = action.strip().lower()
    
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported action: {action}. Supported actions: {list(SUPPORTED_ACTIONS.keys())}")
    
    # Check required parameters
    required = ACTION_REQUIRED_PARAMS.get(action, [])
    missing_params = []
    
    for param in required:
        if param not in params or not params[param]:
            missing_params.append(param)
    
    if missing_params:
        raise ValueError(f"Missing required parameters for action '{action}': {missing_params}")
    
    # Validate and clean parameters
    cleaned_params = {}
    
    # Handle common parameters
    if 'hubspot_api_key' in params:
        api_key = str(params['hubspot_api_key']).strip()
        if not api_key:
            raise ValueError("HubSpot API key is required but empty")
        cleaned_params['hubspot_api_key'] = api_key
    
    if 'fetch_new_leads_since_days' in params:
        try:
            days = int(params['fetch_new_leads_since_days']) if params['fetch_new_leads_since_days'] else 7
            cleaned_params['fetch_new_leads_since_days'] = max(0, days)
        except (ValueError, TypeError):
            cleaned_params['fetch_new_leads_since_days'] = 7
    
    if 'max_leads_per_fetch' in params:
        try:
            max_leads = int(params['max_leads_per_fetch']) if params['max_leads_per_fetch'] else 100
            cleaned_params['max_leads_per_fetch'] = min(max(1, max_leads), 10000)
        except (ValueError, TypeError):
            cleaned_params['max_leads_per_fetch'] = 100
    
    if 'include_contact_properties' in params:
        properties = params['include_contact_properties']
        if isinstance(properties, list):
            cleaned_params['include_contact_properties'] = [str(p).strip() for p in properties if p]
        elif isinstance(properties, str) and properties.strip():
            cleaned_params['include_contact_properties'] = [p.strip() for p in properties.split(',') if p.strip()]
        else:
            cleaned_params['include_contact_properties'] = []
    
    if 'lead_status_filter' in params:
        cleaned_params['lead_status_filter'] = str(params['lead_status_filter']).strip() if params['lead_status_filter'] else ''
    
    if 'include_engagement_data' in params:
        cleaned_params['include_engagement_data'] = bool(params.get('include_engagement_data', False))
    
    if 'lead_id' in params:
        lead_id = str(params['lead_id']).strip()
        if not lead_id:
            raise ValueError("Lead ID is required for get_lead_by_id action")
        cleaned_params['lead_id'] = lead_id
    
    return {
        'valid': True,
        'action': action,
        'params': cleaned_params
    }


def route_action(action: str, params: Dict[str, Any], client: HubSpotClient) -> Dict[str, Any]:
    """
    Route the action to the appropriate handler and return standardized response.
    
    Args:
        action: The action to execute
        params: Parameters for the action
        client: Initialized HubSpot client
    
    Returns:
        Standardized response dictionary with results or error information
    """
    try:
        # Validate action and parameters
        validation_result = validate_action_params(action, params)
        action = validation_result['action']
        cleaned_params = validation_result['params']
        
        logger.info(f"Routing action: {action}")
        
        # Execute the appropriate action
        if action == 'fetch_new_leads':
            since_days = cleaned_params.get('fetch_new_leads_since_days', 7)
            max_leads = cleaned_params.get('max_leads_per_fetch', 100)
            properties = cleaned_params.get('include_contact_properties', [])
            
            leads = fetch_new_leads(client, since_days, max_leads, properties)
            
            return {
                'success': True,
                'action': action,
                'data': {
                    'leads': leads,
                    'count': len(leads),
                    'parameters': {
                        'since_days': since_days,
                        'max_leads': max_leads,
                        'properties_included': properties if properties else 'default'
                    }
                },
                'timestamp': datetime.utcnow().isoformat()
            }
        
        elif action == 'get_lead_by_id':
            lead_id = cleaned_params['lead_id']
            properties = cleaned_params.get('include_contact_properties', [])
            
            lead_details = get_lead_details(client, lead_id, properties)
            
            return {
                'success': True,
                'action': action,
                'data': {
                    'lead': lead_details,
                    'lead_id': lead_id,
                    'properties_included': properties if properties else 'default'
                },
                'timestamp': datetime.utcnow().isoformat()
            }
        
        elif action == 'fetch_filtered_leads':
            since_days = cleaned_params.get('fetch_new_leads_since_days', 7)
            max_leads = cleaned_params.get('max_leads_per_fetch', 100)
            properties = cleaned_params.get('include_contact_properties', [])
            status_filter = cleaned_params.get('lead_status_filter', '')
            
            leads = fetch_new_leads(client, since_days, max_leads, properties)
            
            if status_filter:
                leads = filter_leads_by_status(leads, status_filter)
            
            return {
                'success': True,
                'action': action,
                'data': {
                    'leads': leads,
                    'count': len(leads),
                    'parameters': {
                        'since_days': since_days,
                        'max_leads': max_leads,
                        'status_filter': status_filter if status_filter else 'none',
                        'properties_included': properties if properties else 'default'
                    }
                },
                'timestamp': datetime.utcnow().isoformat()
            }
        
        elif action == 'fetch_leads_with_engagement':
            since_days = cleaned_params.get('fetch_new_leads_since_days', 7)
            max_leads = cleaned_params.get('max_leads_per_fetch', 100)
            properties = cleaned_params.get('include_contact_properties', [])
            include_engagement = cleaned_params.get('include_engagement_data', False)
            
            leads = fetch_new_leads(client, since_days, max_leads, properties)
            
            if include_engagement:
                leads = add_engagement_data(client, leads)
            
            return {
                'success': True,
                'action': action,
                'data': {
                    'leads': leads,
                    'count': len(leads),
                    'parameters': {
                        'since_days': since_days,
                        'max_leads': max_leads,
                        'engagement_data_included': include_engagement,
                        'properties_included': properties if properties else 'default'
                    }
                },
                'timestamp': datetime.utcnow().isoformat()
            }
        
        else:
            raise ValueError(f"Action '{action}' is not implemented")
    
    except HubSpotAPIError as e:
        logger.error(f"HubSpot API error during action '{action}': {str(e)}")
        return {
            'success': False,
            'action': action,
            'error': {
                'type': 'api_error',
                'message': str(e),
                'details': handle_api_error(e)
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    except ValueError as e:
        logger.error(f"Validation error during action '{action}': {str(e)}")
        return {
            'success': False,
            'action': action,
            'error': {
                'type': 'validation_error',
                'message': str(e)
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Unexpected error during action '{action}': {str(e)}")
        return {
            'success': False,
            'action': action,
            'error': {
                'type': 'system_error',
                'message': f"An unexpected error occurred: {str(e)}"
            },
            'timestamp': datetime.utcnow().isoformat()
        }