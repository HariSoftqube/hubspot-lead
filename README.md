# HubSpot Lead Capture Machine

## Overview
This Quantum Machine Node connects to your HubSpot CRM to automatically capture and retrieve lead information. It enables seamless integration of HubSpot lead data into your ETL workflows, supporting both bulk lead fetching and individual lead retrieval with customizable data enrichment options.

## Key Features
• **Automated Lead Capture** - Fetch new inbound leads based on creation date with configurable lookback periods
• **Flexible Data Retrieval** - Choose specific contact properties to include and filter leads by status
• **Engagement Tracking** - Optionally include complete engagement history and activity data for each lead
• **Scalable Processing** - Built-in pagination handling for large lead volumes with configurable batch sizes

## Configuration Guide
To configure this machine in your workflow, you'll need to provide the following parameters:

**HubSpot API Key** - Your private app key from HubSpot for authentication with the CRM system

**Action Selection** - Choose between "fetch_new_leads" to retrieve multiple leads or "get_lead_by_id" for specific lead lookup

**New Leads Lookback Period** - Number of days to look back when fetching new leads (e.g., 7 for the past week)

**Contact Properties** - List of specific HubSpot contact fields you want to include in the output data

**Maximum Leads Per Fetch** - Set a limit on how many leads to retrieve in a single operation (0 for no limit)

**Lead Status Filter** - Optional filter to retrieve only leads with specific statuses like 'new', 'qualified', or 'customer'

**Include Engagement Data** - Toggle to include or exclude detailed engagement history for each lead

## Expected Output
This machine generates structured JSON data containing an array of lead objects with all requested contact information and properties. The output includes a status indicator, the total count of leads retrieved, and a flag indicating if additional leads are available for pagination. Each lead record contains the HubSpot contact ID, creation timestamp, and all specified contact properties formatted for downstream processing in your workflow pipeline.