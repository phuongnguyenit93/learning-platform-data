# Querying Resources with Azure Resource Graph

## 1. What Problem Does Azure Resource Graph Solve?

In a Microsoft Azure environment, resources are often spread across multiple subscriptions, resource groups, and regions. As the number of virtual machines, storage accounts, databases, virtual networks, and other services grows, opening each resource group one by one to take inventory becomes slow and error-prone. Operators need to answer broad-scope questions such as:

- How many virtual machines does the organization have, and which regions are they in?
- Which resources are missing an owner or environment tag?
- Which storage accounts do not yet have HTTPS requirement enabled?
- Which resource types are inside a given resource group?
- Which managed disks are not attached to any virtual machine?

**Azure Resource Graph (ARG)** is a query service that helps explore Azure resource information at scale. ARG indexes the metadata of resources managed through Azure Resource Manager (ARM), then allows querying with a Kusto Query Language (KQL)-style language. You can query across multiple subscriptions at once, depending on the selected scope and your account's access permissions.

ARG is especially useful for inventory, governance, configuration checks, reporting, and resource discovery. Query results only provide information for analysis; ARG is not a tool for executing configuration changes on resources.

## 2. How Does ARG Work?

When resources are created or modified through Azure, their metadata is ingested into Resource Graph's indexing system. When a query is submitted, ARG evaluates the statement against the indexed data and returns the records the user has permission to view within the query scope.

General workflow:

~~~mermaid
flowchart TD
    A[Azure resources] --> B[Azure Resource Manager]
    B --> C[Resource Graph index]
    D[Operator] --> E[Portal, Azure CLI, or PowerShell]
    E --> F[KQL query]
    C --> F
    F --> G[Results by scope and RBAC]
    G --> H[Inventory, reporting, governance checks]
~~~

ARG is optimized for querying resource metadata, not as an analytics system for all data generated inside applications. Make this distinction:

| Need | Suitable tool |
|---|---|
| Finding VMs, storage accounts, networks, tags, regions, and resource properties | Azure Resource Graph |
| Analyzing application logs, platform logs, and collected log data | Azure Monitor Logs / Log Analytics |
| Tracking CPU, memory, request rate, and metrics over time | Azure Monitor Metrics |
| Deploying or modifying resource configurations | ARM/Bicep, Azure CLI, PowerShell, or an appropriate deployment tool |

ARG is a read-only query service. Indexed data can lag slightly behind a recent change on a resource. Therefore, when you need to confirm the immediate state of a newly deployed change, inspect the resource directly or call the relevant service API.

## 3. Query Scope and Access Permissions

### 3.1. Scope

When opening Resource Graph Explorer or running queries from command-line tools, you choose the scope of resources to inspect. The scope can include one or multiple subscriptions; in the Azure Portal, users can select subscriptions or management groups they have permission to access.

Querying across multiple subscriptions enables centralized reporting. For example, an operations team can count all virtual machines across development, testing, and production environments without opening each subscription individually.

### 3.2. RBAC filters results

Azure Resource Graph enforces access control based on Azure role-based access control (RBAC). Users only see resources within scopes where they hold read permissions. If a subscription or resource group does not appear in the results, check the selected scope and account permissions before concluding the resource does not exist.

In practice, the Reader role at an appropriate scope is commonly used to read resources. Organizations can also assign dedicated roles for Resource Graph querying per their policies. ARG query permissions and resource read permissions must satisfy the environment's requirements; results never bypass existing RBAC permissions.

A query running successfully does not prove the user sees every resource in the tenant. An inventory report is only complete once the subscription/management group scope and access permissions have been verified.

## 4. Resource Graph Explorer in Azure Portal

Resource Graph Explorer is a visual interface for writing, running, and viewing query results.

Basic workflow:

1. Sign into the Azure Portal with an account that has read permissions on the subscriptions to inspect.
2. Open **Resource Graph Explorer** from the Portal search bar.
3. Select the supported subscriptions or scopes you want to query.
4. Write the KQL statement in the editor area.
5. Select **Run query** to execute.
6. Review the results table, refine the query, and save useful queries for reuse if needed.

Example querying all resources in the selected scope:

~~~kusto
Resources
| project name, type, resourceGroup, location, subscriptionId
| order by type asc, name asc
~~~

**Resources** is the table containing metadata of Azure resources within the user's readable scope. Each row generally represents one resource. Some commonly used columns:

| Column | Meaning |
|---|---|
| id | Full Resource ID of the resource |
| name | Resource name |
| type | Resource type, typically formatted as namespace/type |
| resourceGroup | Resource group containing the resource |
| subscriptionId | Subscription ID |
| location | Region of the resource, if the resource type has a location property |
| tags | Tags attached to the resource |
| properties | Detailed properties exposed by the resource provider |
| sku | SKU information, if the resource has this field |

Not every resource type populates all columns with the same meaning. For example, global resources may lack a location; a resource type may not expose sku or a specific field inside properties.

## 5. Common KQL Syntax

ARG uses KQL-style query syntax. A basic query typically starts with a table name, followed by operators chained with the | character. ARG supports a subset of KQL capabilities tailored to resource metadata; do not assume every function or operator from Azure Data Explorer can be used in Resource Graph.

Commonly encountered operators:

| Operator | Purpose |
|---|---|
| where | Filter rows by condition |
| project | Select columns to display |
| extend | Create computed columns from existing data |
| summarize | Group and compute aggregations such as count() |
| order by | Sort results |
| take | Limit the number of rows returned |
| join | Combine data from multiple tables or result sets |

### 5.1. Filtering by resource type

For example, retrieving only Azure virtual machines:

~~~kusto
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project name, resourceGroup, location, subscriptionId
| order by name asc
~~~

The **=~** operator performs case-insensitive string comparison. Using this operator is helpful when comparing type values, since casing can vary across queries or input data.

### 5.2. Filtering by resource group or region

~~~kusto
Resources
| where resourceGroup =~ 'rg-production'
| project name, type, location, id
| order by type asc
~~~

Filtering resources in a region:

~~~kusto
Resources
| where location =~ 'southeastasia'
| project name, type, resourceGroup, location
| order by resourceGroup asc, name asc
~~~

Region names in the data usually use identifier format such as southeastasia. Inspect the actual values in the location column if results are not as expected.

### 5.3. Counting resources by type

~~~kusto
Resources
| summarize total = count() by type
| order by total desc
~~~

This query produces a summary report of total resources per type. You can use the same pattern to aggregate by region:

~~~kusto
Resources
| summarize total = count() by location
| order by total desc
~~~

If you need counts by both region and type:

~~~kusto
Resources
| summarize total = count() by location, type
| order by location asc, total desc
~~~

### 5.4. Querying tags

Tags are commonly used to classify resources by environment, owner, cost center, or application. Because tags are dynamic data, cast values to strings when explicit comparison is needed:

~~~kusto
Resources
| extend environment = tostring(tags['environment'])
| where environment =~ 'production'
| project name, type, resourceGroup, environment
| order by resourceGroup asc
~~~

Finding resources missing the owner tag:

~~~kusto
Resources
| where isempty(tostring(tags['owner']))
| project name, type, resourceGroup, subscriptionId
| order by subscriptionId asc, resourceGroup asc
~~~

The output of the second query can serve as an action list during a tag standardization effort. ARG only detects and lists resources missing tags; adding tags must be done through a governance workflow or tools with appropriate write permissions.

### 5.5. Checking storage account configuration

Example listing several common security properties of storage accounts:

~~~kusto
Resources
| where type =~ 'microsoft.storage/storageaccounts'
| project name,
          resourceGroup,
          location,
          httpsOnly = properties.supportsHttpsTrafficOnly,
          minimumTlsVersion = properties.minimumTlsVersion
| order by name asc
~~~

This query lets you quickly audit properties indexed by Resource Graph. If a column returns an empty value, determine whether that property is exposed by the resource provider for that resource type and point in time. Do not automatically interpret an empty value as a secure or insecure configuration.

### 5.6. Finding managed disks not attached to a virtual machine

A managed disk's managedBy property indicates the virtual machine resource managing or using that disk. You can filter disks lacking this value for further investigation:

~~~kusto
Resources
| where type =~ 'microsoft.compute/disks'
| where isempty(managedBy)
| project name, resourceGroup, location, diskSizeGB = properties.diskSizeGB, id
| order by resourceGroup asc, name asc
~~~

A disk without managedBy may be unattached to any VM, but you should not delete it immediately based solely on this output. The disk may be intentionally retained for backup, recovery, migration, or pending attachment to another workload. Verify the owner, usage history, and retention policy before taking action.

### 5.7. Joining Resources and ResourceContainers

ARG provides the **ResourceContainers** table to query containers such as subscriptions and resource groups. For example, retrieving the list of resource groups:

~~~kusto
ResourceContainers
| where type =~ 'microsoft.resources/subscriptions/resourcegroups'
| project name, subscriptionId, location, tags
| order by subscriptionId asc, name asc
~~~

You can combine virtual machine details with subscription names:

~~~kusto
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project vmName = name, resourceGroup, subscriptionId, location
| join kind=leftouter (
    ResourceContainers
    | where type =~ 'microsoft.resources/subscriptions'
    | project subscriptionId, subscriptionName = name
) on subscriptionId
| project vmName, subscriptionName, resourceGroup, location
| order by subscriptionName asc, vmName asc
~~~

The **join** operator matches records on the subscriptionId key. Using **leftouter** keeps virtual machines from the left side even if a matching subscription record is not found in the queried dataset.

## 6. Running Queries with Azure CLI

Azure CLI provides the az graph query command via the Resource Graph extension. If your machine does not have the extension yet, install it with:

~~~bash
az extension add --name resource-graph
~~~

Sign in and select the appropriate subscription:

~~~bash
az login
az account set --subscription '<subscription-id>'
~~~

Run a query and display results in table format:

~~~bash
az graph query --graph-query "Resources | where type =~ 'microsoft.compute/virtualmachines' | project name, resourceGroup, location, subscriptionId" --output table
~~~

You can specify multiple subscriptions in the --subscriptions parameter when the account has access:

~~~bash
az graph query --graph-query "Resources | summarize total = count() by type | order by total desc" --subscriptions '<subscription-id-1>' '<subscription-id-2>' --output table
~~~

When writing long queries, save the statement in a file or shell variable for readability and reuse. JSON output is helpful when passing data into downstream processing scripts; --output table is suitable for quick terminal checks.

## 7. Running Queries with Azure PowerShell

If your operational workflow uses PowerShell, install the Resource Graph module:

~~~powershell
Install-Module -Name Az.ResourceGraph -Scope CurrentUser
~~~

Sign into Azure and set the subscription:

~~~powershell
Connect-AzAccount
$subscriptionId = '<subscription-id>'
Set-AzContext -Subscription $subscriptionId
~~~

Then run the query:

~~~powershell
$query = @'
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project name, resourceGroup, location, subscriptionId
| order by name asc
'@

Search-AzGraph -Query $query -Subscription $subscriptionId
~~~

Search-AzGraph returns records matching the query and specified scope. For large result sets, check the documentation for your installed module version regarding pagination and row-count parameters; do not assume a single call always returns all data from a large environment.

## 8. Working with Large Result Sets and Optimizing Queries

A query across multiple subscriptions can return substantial data. To keep results readable and reduce unnecessary data:

- Filter early with where, especially on type, subscriptionId, resourceGroup, or location.
- Select only needed columns with project; avoid pulling entire properties objects into reports unnecessarily.
- Use summarize when the goal is aggregate numbers rather than a detailed item list.
- Use take during experimentation to inspect data structure before expanding the query.
- Pick the subscription or management group scope that fits the question being answered.
- When a query spans multiple pages, use the pagination mechanism of the tool or API in use to fetch subsequent pages.

Example previewing just 20 virtual machines:

~~~kusto
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project name, resourceGroup, location
| take 20
~~~

take helps quickly inspect data shape, but it does not guarantee a representative sample of the entire environment. When producing formal reports, remove test limits or apply proper pagination logic.

## 9. Limitations and Caveats When Interpreting Results

ARG is very useful for inventory, but you must understand its data source and limits:

1. **Data is indexed metadata.** A change just applied may not appear immediately in results. Do not use ARG as sole proof of the immediate state of an operation.
2. **Results depend on RBAC and scope.** Resources outside your read permission scope will not appear, even though they exist in the tenant.
3. **Not all properties are present.** Properties structures vary across resource providers and resource types; a field may be empty or not indexed as expected.
4. **ARG uses a subset of KQL.** Some operators, functions, or query patterns available in Azure Data Explorer may be unsupported or restricted in Resource Graph.
5. **Size and row-count limits exist.** Large-scale queries require pagination according to the Portal, CLI, PowerShell, or API mechanism; do not rely solely on the first page of results.
6. **ARG does not replace logs and metrics.** Performance data, time-series events, and log contents must be collected and analyzed with appropriate Azure Monitor services.
7. **Results are not remediation commands.** A result row indicates a configuration to review; modifications must go through deployment tools or controlled operational processes.

## 10. Practical Workflow for Inventorying a Subscription

Suppose you have just taken over a new subscription and need to produce an initial report. You can follow this workflow:

1. Confirm the subscription to inspect and ensure your account has read permissions on resources.
2. Open Resource Graph Explorer, select the right subscription, and run a query listing name, type, resourceGroup, location, and id.
3. Run a summarize query to count resources by type and location.
4. Check owner and environment tags; produce a list of resources missing governance metadata.
5. Inspect several critical configurations, such as HTTPS/TLS properties of storage accounts.
6. Cross-check anomalous findings against the Portal or the resource's direct configuration before drawing conclusions.
7. Export or save the report per internal procedures, noting the query timestamp and selected scope.
8. Convert findings into tasks with an owner and due date; apply changes only after verifying impact and having appropriate permissions.

A good report clearly states the query used, execution timestamp, list of subscriptions in scope, and access permission boundaries. This helps readers understand which part of the environment the data reflects.

## 11. Common Errors

- **az graph not found.** Check whether the resource-graph extension is installed in Azure CLI.
- **No results.** Check the subscription scope, RBAC permissions, table name, where conditions, and how the type value is written.
- **Missing some subscriptions.** Confirm the account has read permissions on those subscriptions and that they were selected in the scope.
- **Properties return empty.** Check the resource type's schema; not all resource providers expose the same properties.
- **KQL query rejected.** Verify whether the operator/function is within the feature set supported by Resource Graph.
- **Report omits newly created resources.** Wait for the index to update or inspect the resource directly to confirm the latest state.
- **Deleting resources based on a single query.** Use results as investigation input, confirming owners and dependencies before executing impactful actions.

## 12. Key Takeaways

Azure Resource Graph enables querying Azure resource metadata across multiple subscriptions using KQL syntax, making it well suited for inventory, search, aggregation, and governance checks. Start with the Resources table to query resources and ResourceContainers to query subscriptions or resource groups. Choose the right scope, understand RBAC limits, filter early, and project only needed columns. Results reflect indexed data and user permissions; cross-check with the Portal, ARM, or dedicated monitoring tools when you need to confirm immediate state, logs, metrics, or perform modifications.
