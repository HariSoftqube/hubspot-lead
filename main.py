import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from quantum.CoreEngine import CoreEngine
from hubspot_client import initialize_client, handle_api_error, HubSpotAPIError
from lead_actions import fetch_new_leads, get_lead_details, format_lead_json, filter_leads_by_status, add_engagement_data
from action_router import route_action, validate_action_params

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MyMachine(CoreEngine):
    input_data = {}
    dependent_machine_data = {}

    def receiving(self, input_data, dependent_machine_data, callback):
        data = {}
        error_list = []
        try:
            data = self.get_final_data() or {}
            error_list = self.get_error_list() or []
            self.input_data = input_data
            self.dependent_machine_data = dependent_machine_data
            
            # Store input parameters for HubSpot lead capture
            self.hubspot_api_key = self.input_data.get("hubspot_api_key", "")
            self.action = self.input_data.get("action", "")
            self.fetch_new_leads_since_days = self.input_data.get("fetch_new_leads_since_days", 7)
            self.include_contact_properties = self.input_data.get("include_contact_properties", [])
            self.max_leads_per_fetch = self.input_data.get("max_leads_per_fetch", 100)
            self.lead_status_filter = self.input_data.get("lead_status_filter", "")
            self.include_engagement_data = self.input_data.get("include_engagement_data", False)
            
            # Store raw input for reference
            data["input_parameters"] = {
                "action": self.action,
                "fetch_new_leads_since_days": self.fetch_new_leads_since_days,
                "include_contact_properties": self.include_contact_properties,
                "max_leads_per_fetch": self.max_leads_per_fetch,
                "lead_status_filter": self.lead_status_filter,
                "include_engagement_data": self.include_engagement_data,
                "api_key_provided": bool(self.hubspot_api_key)
            }
            
            # Check for dependent machine data if needed
            if self.dependent_machine_data:
                data["dependent_data_received"] = True
                # Extract any HubSpot configuration from parent machines
                for machine_key, machine_data in self.dependent_machine_data.items():
                    if isinstance(machine_data, dict):
                        # Check if parent machine provides API key
                        if not self.hubspot_api_key and "hubspot_api_key" in machine_data:
                            self.hubspot_api_key = machine_data["hubspot_api_key"]
                            data["api_key_source"] = f"dependent_machine_{machine_key}"
            
            self.machine_logger.info(f"Received action: {self.action}")
            
        except Exception as e:
            error_list.append(f"Error in receiving: {str(e)}")
            logger.error(f"Receiving error: {str(e)}")
        finally:
            callback(data, error_list)

    def pre_processing(self, callback):
        data = {}
        error_list = []
        try:
            data = self.get_final_data() or {}
            error_list = self.get_error_list() or []
            
            # Validate HubSpot API key
            if not self.hubspot_api_key:
                error_list.append("HubSpot API key is required but not provided")
                data["validation_status"] = "failed"
                data["validation_errors"] = ["Missing API key"]
                callback(data, error_list)
                return
            
            # Validate action parameter
            if not self.action:
                error_list.append("Action parameter is required but not provided")
                data["validation_status"] = "failed"
                data["validation_errors"] = ["Missing action"]
                callback(data, error_list)
                return
            
            # Normalize action to lowercase for consistent routing
            self.action = str(self.action).strip().lower()
            
            # Validate action is supported
            supported_actions = ["fetch_new_leads", "get_lead_by_id", "fetch_all_leads", "get_lead_details"]
            if self.action not in supported_actions:
                error_list.append(f"Unsupported action: {self.action}. Supported actions: {', '.join(supported_actions)}")
                data["validation_status"] = "failed"
                data["validation_errors"] = [f"Unsupported action: {self.action}"]
                callback(data, error_list)
                return
            
            # Prepare action parameters based on selected action
            action_params = {}
            
            if self.action in ["fetch_new_leads", "fetch_all_leads"]:
                # Parameters for fetching leads
                action_params["since_days"] = max(0, int(self.fetch_new_leads_since_days)) if self.fetch_new_leads_since_days else 7
                action_params["max_leads"] = min(max(1, int(self.max_leads_per_fetch)), 10000) if self.max_leads_per_fetch else 100
                action_params["properties"] = self.include_contact_properties if isinstance(self.include_contact_properties, list) else []
                action_params["status_filter"] = str(self.lead_status_filter).strip() if self.lead_status_filter else ""
                action_params["include_engagement"] = bool(self.include_engagement_data)
                
            elif self.action in ["get_lead_by_id", "get_lead_details"]:
                # Parameters for getting specific lead
                lead_id = self.input_data.get("lead_id", "")
                if not lead_id:
                    error_list.append("Lead ID is required for get_lead_by_id action")
                    data["validation_status"] = "failed"
                    data["validation_errors"] = ["Missing lead_id parameter"]
                    callback(data, error_list)
                    return
                action_params["lead_id"] = str(lead_id).strip()
                action_params["properties"] = self.include_contact_properties if isinstance(self.include_contact_properties, list) else []
            
            # Store validated parameters
            data["validated_action"] = self.action
            data["action_parameters"] = action_params
            data["validation_status"] = "success"
            
            self.machine_logger.info(f"Pre-processing complete. Action: {self.action}, Parameters: {action_params}")
            
        except Exception as e:
            error_list.append(f"Error in pre-processing: {str(e)}")
            logger.error(f"Pre-processing error: {str(e)}")
            data["validation_status"] = "failed"
        finally:
            callback(data, error_list)

    def processing(self, callback):
        data = {}
        error_list = []
        client = None
        try:
            data = self.get_final_data() or {}
            error_list = self.get_error_list() or []
            
            # Skip processing if validation failed
            if data.get("validation_status") == "failed":
                self.machine_logger.warning("Skipping processing due to validation failure")
                callback(data, error_list)
                return
            
            # Initialize HubSpot client
            try:
                client = initialize_client(self.hubspot_api_key)
                data["client_initialized"] = True
                self.machine_logger.info("HubSpot client initialized successfully")
            except Exception as e:
                error_list.append(f"Failed to initialize HubSpot client: {str(e)}")
                data["client_initialized"] = False
                data["api_error"] = handle_api_error(e)
                callback(data, error_list)
                return
            
            # Validate API key by making test request
            try:
                if not client.validate_api_key():
                    error_list.append("Invalid HubSpot API key")
                    data["api_key_valid"] = False
                    callback(data, error_list)
                    return
                data["api_key_valid"] = True
            except Exception as e:
                error_list.append(f"API key validation failed: {str(e)}")
                data["api_key_valid"] = False
                data["api_error"] = handle_api_error(e)
                callback(data, error_list)
                return
            
            # Execute the selected action using the router
            action = data.get("validated_action", "")
            action_params = data.get("action_parameters", {})
            
            self.machine_logger.info(f"Executing action: {action}")
            
            try:
                # Route action through action_router
                result = route_action(action, action_params, client)
                
                if result.get("success"):
                    data["action_result"] = result
                    data["execution_status"] = "success"
                    
                    # Extract leads data based on action type
                    if action in ["fetch_new_leads", "fetch_all_leads"]:
                        leads = result.get("data", {}).get("leads", [])
                        data["leads"] = leads
                        data["lead_count"] = len(leads)
                        data["fetch_metadata"] = result.get("data", {}).get("metadata", {})
                        
                        # Apply status filter if specified
                        if action_params.get("status_filter"):
                            filtered_leads = filter_leads_by_status(leads, action_params["status_filter"])
                            data["filtered_leads"] = filtered_leads
                            data["filtered_count"] = len(filtered_leads)
                            self.machine_logger.info(f"Filtered {len(filtered_leads)} leads by status: {action_params['status_filter']}")
                        
                        # Add engagement data if requested
                        if action_params.get("include_engagement"):
                            leads_with_engagement = add_engagement_data(client, leads)
                            data["leads"] = leads_with_engagement
                            data["engagement_data_added"] = True
                            self.machine_logger.info("Added engagement data to leads")
                        
                    elif action in ["get_lead_by_id", "get_lead_details"]:
                        lead_details = result.get("data", {}).get("lead", {})
                        data["lead_details"] = lead_details
                        data["lead_found"] = bool(lead_details)
                        
                        # Add engagement data for single lead if requested
                        if action_params.get("include_engagement") and lead_details:
                            leads_with_engagement = add_engagement_data(client, [lead_details])
                            if leads_with_engagement:
                                data["lead_details"] = leads_with_engagement[0]
                                data["engagement_data_added"] = True
                    
                    self.machine_logger.info(f"Action {action} executed successfully")
                    
                else:
                    error_list.append(f"Action execution failed: {result.get('error', 'Unknown error')}")
                    data["execution_status"] = "failed"
                    data["action_error"] = result.get("error_details", {})
                    
            except Exception as e:
                error_list.append(f"Error executing action {action}: {str(e)}")
                data["execution_status"] = "failed"
                data["action_error"] = handle_api_error(e)
                logger.error(f"Action execution error: {str(e)}")
            
        except Exception as e:
            error_list.append(f"Error in processing: {str(e)}")
            logger.error(f"Processing error: {str(e)}")
            data["execution_status"] = "failed"
        finally:
            # Clean up client connection
            if client:
                try:
                    client.close()
                    self.machine_logger.info("HubSpot client connection closed")
                except Exception as e:
                    logger.warning(f"Error closing client: {str(e)}")
            callback(data, error_list)

    def post_processing(self, callback):
        data = {}
        error_list = []
        try:
            data = self.get_final_data() or {}
            error_list = self.get_error_list() or []
            
            # Skip post-processing if execution failed
            if data.get("execution_status") == "failed":
                self.machine_logger.warning("Skipping post-processing due to execution failure")
                callback(data, error_list)
                return
            
            # Format and clean up lead data
            action = data.get("validated_action", "")
            
            if action in ["fetch_new_leads", "fetch_all_leads"]:
                # Process multiple leads
                leads = data.get("leads", [])
                if data.get("filtered_leads"):
                    leads = data.get("filtered_leads", [])
                
                # Ensure all leads are properly formatted
                formatted_leads = []
                for lead in leads:
                    if isinstance(lead, dict):
                        # Already formatted by lead_actions
                        formatted_leads.append(lead)
                    else:
                        # Format if needed
                        formatted_leads.append(format_lead_json(lead))
                
                data["formatted_leads"] = formatted_leads
                data["total_leads_processed"] = len(formatted_leads)
                
                # Generate summary statistics
                data["summary"] = {
                    "total_leads": len(formatted_leads),
                    "action_executed": action,
                    "filters_applied": {
                        "days_back": data.get("action_parameters", {}).get("since_days", 7),
                        "status_filter": data.get("action_parameters", {}).get("status_filter", ""),
                        "max_leads": data.get("action_parameters", {}).get("max_leads", 100)
                    },
                    "properties_included": data.get("action_parameters", {}).get("properties", []),
                    "engagement_data_included": data.get("engagement_data_added", False),
                    "processing_timestamp": datetime.utcnow().isoformat()
                }
                
            elif action in ["get_lead_by_id", "get_lead_details"]:
                # Process single lead
                lead_details = data.get("lead_details", {})
                if lead_details:
                    # Ensure lead is properly formatted
                    if not lead_details.get("formatted"):
                        lead_details = format_lead_json(lead_details)
                    
                    data["formatted_lead"] = lead_details
                    data["lead_id"] = lead_details.get("id", "")
                    data["summary"] = {
                        "lead_found": True,
                        "lead_id": lead_details.get("id", ""),
                        "action_executed": action,
                        "properties_included": data.get("action_parameters", {}).get("properties", []),
                        "engagement_data_included": data.get("engagement_data_added", False),
                        "processing_timestamp": datetime.utcnow().isoformat()
                    }
                else:
                    data["summary"] = {
                        "lead_found": False,
                        "action_executed": action,
                        "requested_lead_id": data.get("action_parameters", {}).get("lead_id", ""),
                        "processing_timestamp": datetime.utcnow().isoformat()
                    }
            
            # Clean up intermediate data
            keys_to_remove = ["action_result", "action_parameters", "validated_action", 
                             "client_initialized", "api_key_valid", "execution_status",
                             "leads", "lead_details", "filtered_leads"]
            for key in keys_to_remove:
                data.pop(key, None)
            
            self.machine_logger.info("Post-processing completed successfully")
            
        except Exception as e:
            error_list.append(f"Error in post-processing: {str(e)}")
            logger.error(f"Post-processing error: {str(e)}")
        finally:
            callback(data, error_list)

    def packaging_shipping(self, callback):
        data = {}
        error_list = []
        try:
            data = self.get_final_data() or {}
            error_list = self.get_error_list() or []
            
            # Package data for output.json
            output_data = {
                "success": len(error_list) == 0,
                "timestamp": datetime.utcnow().isoformat(),
                "machine_name": "HubSpot_Lead",
                "action": self.action
            }
            
            # Add appropriate data based on action
            if self.action in ["fetch_new_leads", "fetch_all_leads"]:
                output_data["leads"] = data.get("formatted_leads", [])
                output_data["total_count"] = data.get("total_leads_processed", 0)
                output_data["metadata"] = data.get("summary", {})
                
            elif self.action in ["get_lead_by_id", "get_lead_details"]:
                output_data["lead"] = data.get("formatted_lead", {})
                output_data["metadata"] = data.get("summary", {})
            
            # Add error information if any
            if error_list:
                output_data["errors"] = error_list
                output_data["error_count"] = len(error_list)
            
            # Add input parameters for reference
            output_data["input_parameters"] = data.get("input_parameters", {})
            
            # Final data assignment for output.json
            data = output_data
            
            self.machine_logger.info(f"Packaging completed. Output contains {len(data.get('leads', []))} leads" 
                                   if 'leads' in data else "Packaging completed for single lead")
            
        except Exception as e:
            error_list.append(f"Error in packaging: {str(e)}")
            logger.error(f"Packaging error: {str(e)}")
            data["success"] = False
            data["errors"] = error_list
        finally:
            callback(data, error_list)

if __name__ == '__main__':
    machine = MyMachine()
    machine.start()