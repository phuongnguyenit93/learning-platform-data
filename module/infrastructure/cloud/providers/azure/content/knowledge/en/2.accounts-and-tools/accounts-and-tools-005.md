# Managing Azure with Azure PowerShell

Azure PowerShell is a PowerShell command set used to sign into Azure, view and manage resources, deploy infrastructure, inspect operations, and automate operational tasks. This tool is well suited when you want to combine Azure operations with PowerShell's data processing capabilities, variables, loops, functions, and scripting.

In the Microsoft Azure ecosystem, you will work with a Microsoft Entra ID tenant, subscriptions, resource groups, and many types of resources such as virtual networks, virtual machines, storage accounts, and data services. Azure PowerShell provides a consistent way to interact with those components, though execution permissions still depend on the identity and roles assigned in Azure.

After this lesson, you will be able to:

- Install and verify Azure PowerShell.
- Sign in with an appropriate account and select the right tenant and subscription.
- Query resource groups and resources within your permitted scope.
- Create resource groups, apply tags, and prepare resource deployments.
- Use scripts to automate operations in a controlled manner.
- Apply fundamental security, monitoring, and cost principles when managing Azure.

## 1. How Does Azure PowerShell Work?

Azure PowerShell is a collection of PowerShell modules. The main module typically installed is `Az`; this module aggregates service-specific modules, such as:

| Module | Common scope |
|---|---|
| `Az.Accounts` | Sign-in, accounts, tenant, and subscription context |
| `Az.Resources` | Resource groups, resources, template deployments, and tags |
| `Az.Compute` | Virtual machines and compute resources |
| `Az.Network` | Virtual networks, subnets, network interfaces, and network configurations |
| `Az.Storage` | Storage accounts and storage operations |
| `Az.Monitor` | Monitoring information and metrics |

Azure commands typically follow the `Verb-AzNoun` pattern, such as `Get-AzResourceGroup`, `New-AzResourceGroup`, and `Get-AzVM`. The `Az` prefix identifies commands belonging to the Azure module suite. Familiar PowerShell verbs have consistent meanings: `Get` to read, `New` to create, `Set` to update, `Remove` to delete, and `Update` to perform partial updates depending on the cmdlet.

When you run a cmdlet, Azure PowerShell sends a request to the Azure management API or the corresponding service's data API. Therefore, whether a command can run depends on multiple factors: installed modules, active connection, subscription context, RBAC permissions, resource state, and the type of API the command calls.

### Distinguishing Azure PowerShell, Azure CLI, and Azure Cloud Shell

- **Azure PowerShell** provides cmdlets and deep integration with the PowerShell language. It is a convenient choice when you need to manipulate objects, write functions, or integrate with Windows administration tools.
- **Azure CLI** provides the `az` command and usually returns JSON output. This tool fits cross-platform scripts and workflows already using the CLI.
- **Azure Cloud Shell** is a shell environment running in the Azure Portal. Cloud Shell can provide both Bash and PowerShell along with a convenient sign-in context. It is a command execution environment, not a replacement command set for Azure PowerShell.

All three tools can manage the same Azure resources. Choose the tool aligned with your environment and team standards, and avoid mixing multiple authentication methods within the same script without a clear reason.

## 2. Installing and Verifying Azure PowerShell

You can use PowerShell 7 on Windows, macOS, or Linux. PowerShell 7 is usually the preferred choice for new environments. Some Windows machines still have Windows PowerShell 5.1; check the environment's version and policies before installing modules.

Open PowerShell and check the version:

```powershell
$PSVersionTable.PSVersion
```

Install the `Az` module for the current account:

```powershell
Install-Module -Name Az -Repository PSGallery -Scope CurrentUser
```

If PowerShell prompts to confirm installation from PowerShell Gallery, verify the source and confirm in accordance with your organization's policy. On enterprise-managed machines, you may need to use an internal repository or ask an administrator to configure allowed module sources.

Check installed modules:

```powershell
Get-InstalledModule -Name Az -AllVersions
Get-Module -Name Az -ListAvailable
```

Import the module when needed:

```powershell
Import-Module Az
Get-Command -Module Az.Accounts
```

`Az` is a meta-module made up of many submodules. If a machine only needs to manage a few services, an organization may choose to install only the required submodules to reduce dependency scope. When using submodules, ensure the module corresponding to the cmdlet is installed.

To update a version installed via PowerShell Gallery:

```powershell
Update-Module -Name Az
```

In a shared work environment, standardize module versions, test changes before updating machines running critical tasks, and follow your organization's software management process.

## 3. Signing In to Azure

### Interactive sign-in

On a personal workstation, the simplest method is:

```powershell
Connect-AzAccount
```

PowerShell launches Microsoft's sign-in flow. Sign in with an account belonging to a tenant granted access to the subscription you need to manage. If your organization requires selecting a specific tenant, you can specify the tenant ID:

```powershell
$tenantId = "00000000-0000-0000-0000-000000000000"
Connect-AzAccount -TenantId $tenantId
```

The value above is only a format example. Replace it with the tenant ID provided by your organization. Do not put credentials or tokens into source code.

In environments where a browser window cannot be opened, you can use device code sign-in:

```powershell
Connect-AzAccount -UseDeviceAuthentication
```

The command will instruct you to open a sign-in page and enter the provided code. Only enter the code during a sign-in session you initiated yourself.

### Verifying identity and subscription

After signing in, inspect the current context:

```powershell
Get-AzContext
```

The context indicates the account, tenant, and subscription that Azure cmdlets will use by default. List the subscriptions the account can access:

```powershell
Get-AzSubscription |
    Select-Object Name, Id, TenantId, State
```

An account may access multiple tenants or subscriptions. Do not assume the currently selected subscription is the one you intend to operate on.

Select a subscription by ID:

```powershell
$subscriptionId = "11111111-1111-1111-1111-111111111111"
Set-AzContext -SubscriptionId $subscriptionId
```

Confirm again before continuing:

```powershell
$context = Get-AzContext
$context | Format-List Account, Tenant, Subscription, Environment
```

If you need to view saved contexts:

```powershell
Get-AzContext -ListAvailable
```

An incorrect context can cause commands to read the wrong environment or create resources in an unintended subscription. For operations affecting cost or data, verify the context right before running them.

### Working in automation environments

For scripts running on servers or pipelines, avoid depending on interactive sign-in prompts. Prefer managed identities, workload identity federation, or service principals configured per security policy.

For example, on an Azure resource with system-assigned managed identity enabled:

```powershell
Connect-AzAccount -Identity
```

For a user-assigned managed identity, you can specify the client ID:

```powershell
$managedIdentityClientId = "22222222-2222-2222-2222-222222222222"
Connect-AzAccount -Identity -AccountId $managedIdentityClientId
```

A certificate-based service principal is another option for automation:

```powershell
$tenantId = "00000000-0000-0000-0000-000000000000"
$appId = "33333333-3333-3333-3333-333333333333"
$thumbprint = "CERTIFICATE_THUMBPRINT"

Connect-AzAccount `
    -ServicePrincipal `
    -TenantId $tenantId `
    -ApplicationId $appId `
    -CertificateThumbprint $thumbprint
```

The certificate must be installed in a certificate store accessible to the process. The service principal must be granted appropriate permissions at the exact Azure scope. Protect private keys, limit certificate lifetimes and usage permissions, and rotate certificates according to organizational procedures.

Do not store client secrets, passwords, access tokens, or private certificate contents in `.ps1` files, Git repositories, pipeline logs, or documentation guides. If secrets are needed, use a managed secret store such as Azure Key Vault along with an appropriate identity mechanism.

## 4. Understanding Management Scopes: Tenant, Subscription, and Resource Group

These scopes serve different roles:

| Component | Role |
|---|---|
| Microsoft Entra tenant | Directory of identities, applications, and groups; supports authentication and identity management |
| Subscription | Scope for managing and billing Azure resources; contains resource groups |
| Resource group | Logical grouping of resources with related lifecycles or management purposes |
| Resource | A specific component such as a virtual network, VM, storage account, or database |

Azure RBAC allows assigning roles at different scopes, and permissions can be inherited down to child scopes. Signing in successfully only proves the identity was authenticated; it does not mean the account has permission to create, modify, or delete every resource.

## 5. Viewing and Creating Resource Groups

List resource groups in the current subscription:

```powershell
Get-AzResourceGroup |
    Select-Object ResourceGroupName, Location, ProvisioningState
```

View details of a resource group:

```powershell
$rgName = "rg-learning-dev"
Get-AzResourceGroup -Name $rgName
```

Create a new resource group:

```powershell
$rgName = "rg-learning-dev"
$location = "southeastasia"
$tags = @{
    environment = "dev"
    owner       = "platform-team"
    purpose     = "learning"
}

New-AzResourceGroup -Name $rgName -Location $location -Tag $tags
```

`Location` is the Azure region storing the resource group's metadata. Resources inside may have their own location rules; when designing architecture, choose a region allowed by your organization that meets latency, availability, data residency, and cost requirements.

A tag is a key-value pair attached to a resource or resource group. Tags such as `environment`, `owner`, `costCenter`, and `application` help classify resources, filter reports, and allocate costs. Tags on a resource group do not automatically guarantee every child resource has the same tags; check your organization's inheritance policies or tagging mechanisms.

To avoid creating duplicate resource groups in a script, you can check first:

```powershell
$rgName = "rg-learning-dev"
$location = "southeastasia"
$rg = Get-AzResourceGroup -Name $rgName -ErrorAction SilentlyContinue

if ($null -eq $rg) {
    New-AzResourceGroup -Name $rgName -Location $location
}
else {
    Write-Output "Resource group already exists: $rgName"
}
```

This is an example of an operation that is safer to rerun: the script checks the current state before creating. For complex resources, each step needs to be designed so reruns do not create duplicates or accidentally overwrite configurations.

## 6. Querying Azure Resources

List resources in a resource group:

```powershell
Get-AzResource -ResourceGroupName $rgName |
    Sort-Object ResourceType, Name |
    Select-Object Name, ResourceType, Location, ResourceGroupName
```

Filter by resource type, for example storage accounts:

```powershell
Get-AzResource `
    -ResourceGroupName $rgName `
    -ResourceType "Microsoft.Storage/storageAccounts"
```

Service-specific cmdlets typically return objects with properties and methods better tailored to each service:

```powershell
# Virtual machines in the resource group
Get-AzVM -ResourceGroupName $rgName

# Virtual networks in the resource group
Get-AzVirtualNetwork -ResourceGroupName $rgName

# Storage accounts in the resource group
Get-AzStorageAccount -ResourceGroupName $rgName
```

You can use the PowerShell pipeline to filter and format output:

```powershell
Get-AzResource -ResourceGroupName $rgName |
    Where-Object ResourceType -eq "Microsoft.Network/virtualNetworks" |
    Select-Object Name, Location, ResourceId
```

When you need to query resources across multiple subscriptions or filter a large volume of resources, Azure Resource Graph is the right tool. Install the module if the environment does not have it yet:

```powershell
Install-Module -Name Az.ResourceGraph -Scope CurrentUser
```

Example querying the name, type, and region of a set of resources:

```powershell
Search-AzGraph -Query @"
Resources
| project name, type, location, resourceGroup, subscriptionId
| limit 20
"@
```

Query results only include resources within the scope the current identity can read. If results are missing, check the subscription context, read permissions, and query scope.

## 7. Deploying Infrastructure with Azure PowerShell

Azure PowerShell can invoke individual resource-creation cmdlets or deploy declarative infrastructure using ARM templates and Bicep. For systems with many interconnected resources, describe infrastructure in templates so it can be reviewed, version-controlled, and deployed repeatedly.

Example deploying a Bicep file into the created resource group:

```powershell
$rgName = "rg-learning-dev"
$templateFile = ".\main.bicep"
$parameterFile = ".\dev.parameters.json"

New-AzResourceGroupDeployment `
    -ResourceGroupName $rgName `
    -TemplateFile $templateFile `
    -TemplateParameterFile $parameterFile `
    -WhatIf
```

`-WhatIf` previews expected changes for your review before deployment. After reviewing the template, parameters, subscription context, and access permissions, rerun the command without `-WhatIf` to perform the deployment:

```powershell
New-AzResourceGroupDeployment `
    -ResourceGroupName $rgName `
    -TemplateFile $templateFile `
    -TemplateParameterFile $parameterFile
```

`-WhatIf` helps detect unexpected changes, but it does not replace reviewing template contents, input data, permissions, and operational impact. Some operation types or resource providers may reflect predicted changes to varying degrees.

If deploying at the subscription scope, Azure PowerShell also provides subscription deployment cmdlets such as `New-AzDeployment`. Choose the right deployment scope because resource group deployments and subscription deployments serve different purposes.

## 8. Managing Common Services

After selecting the context and resource group, you can use service-specific modules to view status and configuration.

### Compute

```powershell
Get-AzVM -ResourceGroupName $rgName |
    Select-Object Name, Location, HardwareProfile, ProvisioningState
```

VM-specific cmdlets let you inspect virtual machine configurations. When changing sizes, power state, or disks, check the impact on applications, downtime, and cost before acting.

### Networking

```powershell
Get-AzVirtualNetwork -ResourceGroupName $rgName |
    Select-Object Name, Location, AddressSpace, Subnets
```

When managing virtual networks, understand the relationships among virtual networks, subnets, network security groups, route tables, public IPs, and network connectivity. Modifying address ranges or security rules can affect connectivity across many workloads.

### Storage

```powershell
Get-AzStorageAccount -ResourceGroupName $rgName |
    Select-Object StorageAccountName, Location, Sku, Kind, ProvisioningState
```

A storage account is a resource managed at the control plane. Operations on blobs, files, queues, or tables are data-plane operations and may require separate permissions. Therefore, permission to view a storage account does not mean permission to read or modify the data inside.

### Data and applications

For database services or application platforms, use the corresponding Az module and check cmdlet documentation for the installed version. Distinguish resource configuration management permissions from data access permissions, connection strings, and application permissions. Never output connection strings or credentials to command output or logs.

## 9. Controlled Script Automation

An Azure management script should make four things explicit: which identity is running, which context is selected, which resources will be affected, and what result must be verified.

Example script that checks connectivity, confirms the subscription, and lists resources in a resource group:

```powershell
$ErrorActionPreference = "Stop"

$subscriptionId = "11111111-1111-1111-1111-111111111111"
$rgName = "rg-learning-dev"

try {
    $context = Get-AzContext
    if ($null -eq $context) {
        throw "No Azure context found. Please sign in before running the script."
    }

    Set-AzContext -SubscriptionId $subscriptionId | Out-Null

    $context = Get-AzContext
    if ($context.Subscription.Id -ne $subscriptionId) {
        throw "Subscription context does not match the expected value."
    }

    $resourceGroup = Get-AzResourceGroup -Name $rgName
    Get-AzResource -ResourceGroupName $resourceGroup.ResourceGroupName |
        Select-Object Name, ResourceType, Location
}
catch {
    Write-Error "Unable to complete Azure operation: $($_.Exception.Message)"
    throw
}
```

Key points to note:

- `$ErrorActionPreference = "Stop"` converts default non-terminating errors from many cmdlets into terminating errors that can be handled in `catch`.
- The script explicitly selects the subscription and re-verifies the context before accessing the resource group.
- `try/catch` centralizes error reporting; do not catch an error and continue as if the operation succeeded.
- The ID value in the example must be replaced with the ID of an environment you are permitted to manage.

For scheduled scripts, log enough detail to trace the timestamp, executing identity, subscription, affected resources, and outcome. Never log tokens, passwords, secret keys, or sensitive data. Set timeouts, handle transient errors safely, and avoid running concurrent sessions that modify the same resource.

## 10. Security and Governance

Azure PowerShell uses the identity and permissions of the current sign-in session. Apply these principles:

1. **Least privilege:** assign only the Azure RBAC roles required for the task at the smallest appropriate scope. Avoid assigning broad Owner or Contributor roles to scripts that only read data.
2. **Dedicated identities for automation:** use managed identities or separate service principals per workload; do not use personal user accounts to run long-term background tasks.
3. **Strong authentication:** follow your organization's MFA, Conditional Access, and authentication policies. For automation, prefer mechanisms that do not require storing long-lived passwords.
4. **Verify context:** confirm tenant, subscription, and cloud environment before create, update, or delete operations.
5. **Protect authentication data:** do not share profiles, token caches, or private certificates between users; manage secret lifecycles in an approved vault.
6. **Track changes:** use Activity Log, Azure Monitor, and change control processes to identify who did what, where, and when.

If a cmdlet reports `AuthorizationFailed` or `Forbidden`, check the identity in `Get-AzContext`, resource scope, RBAC roles, and permission propagation delay. Signing in again does not grant extra permissions on its own.

## 11. Monitoring and Cost Control

Azure PowerShell supports querying resources and operational metadata; Azure Monitor and Cost Management provide dedicated data for monitoring and costs.

Example reading the Activity Log of a resource group over the last 24 hours:

```powershell
$endTime = Get-Date
$startTime = $endTime.AddHours(-24)

Get-AzActivityLog `
    -ResourceGroupName $rgName `
    -StartTime $startTime `
    -EndTime $endTime
```

The Activity Log lets you view management events such as resource creation, updates, or deletions. To monitor application performance, configure appropriate metrics, logs, alerts, and workspaces in Azure Monitor; merely listing resources does not tell you whether an application is healthy.

To control costs:

- Tag resources by environment, owning team, application, and cost center.
- Check SKUs, sizes, deployment regions, and resource counts before creating resources.
- Track usage and costs in Cost Management; configure budgets and alerts following your organization's workflow.
- Shut down or decommission test resources when no longer needed, after confirming no data or dependencies must be preserved.
- Periodically review unused resources, storage capacity, snapshots, public IPs, and continuously billed services.

Permission to read resources does not necessarily include permission to view cost details. If you cannot access Cost Management data, request an appropriate role at the subscription or billing account scope per organizational policy.

## 12. Troubleshooting Common Issues

| Symptom | Possible cause | How to check |
|---|---|---|
| `Connect-AzAccount` fails to run | Missing module or version issue; incompatible browser or authentication method | Check `$PSVersionTable`, `Get-Module -ListAvailable Az.Accounts`, and try a sign-in method allowed by your organization |
| Subscription not visible | Signed into wrong tenant or account lacks permissions | Inspect `Get-AzContext` and `Get-AzSubscription`; confirm tenant ID with an administrator |
| `ResourceGroupNotFound` | Wrong name, wrong subscription context, or resource group was deleted | Check `Get-AzContext` then list with `Get-AzResourceGroup` |
| `AuthorizationFailed` | Missing role or permissions at the target scope | Confirm principal, scope, and role assignment; wait for new permissions to propagate if recently changed |
| Cmdlet not recognized | Corresponding module not installed or not loaded | Use `Get-Command <CmdletName> -All` and check required Az modules |
| Deployment failed | Issue with template, parameters, quota, region, or resource provider | Read deployment operation details and resource provider errors; check quotas and input parameters |
| Can read resource but cannot read data | Has control-plane permissions but lacks data-plane permissions | Check authentication mechanism and data roles on the specific service |

When troubleshooting, save the error message, timestamp, cmdlet, tenant, subscription, and relevant resource ID. Strip out tokens, passwords, and sensitive data before sharing logs for support.

## 13. Deleting Resources and Cleaning Up Test Environments

Deleting a resource group removes the resources inside it and can cause data loss or service disruption. Before deleting, confirm the environment, owner, dependencies, retention policies, and backups.

You can preview the impact using `-WhatIf`:

```powershell
Remove-AzResourceGroup -Name $rgName -WhatIf
```

Only after verifying the exact resource group and receiving authorization to proceed, run the actual delete command:

```powershell
Remove-AzResourceGroup -Name $rgName -Force
```

`-Force` skips interactive confirmation prompts; it does not make the operation safer and does not replace verification steps. Do not include delete commands in automated scripts targeting critical environments without proper approvals and safeguards.

## 14. Lab Exercise

Complete this exercise in a test subscription you are permitted to use:

1. Open PowerShell and check the version.
2. Install or confirm the `Az` module is present.
3. Sign into Azure, list subscriptions, and select the right test subscription.
4. Create resource group `rg-learning-dev` in an organization-approved region, attaching tags `environment=dev` and `owner=learning`.
5. Use `Get-AzResourceGroup` to inspect the resource group and `Get-AzResource` to list resources inside the group.
6. Run `Get-AzContext` once more and record the currently selected tenant and subscription.
7. Use `-WhatIf` to preview the cleanup operation. Only delete the resource group if it is a test environment you created and has no data to preserve.

Example verification commands at the end of the exercise:

```powershell
Get-AzContext
Get-AzResourceGroup -Name "rg-learning-dev"
Get-AzResource -ResourceGroupName "rg-learning-dev"
```

You have completed the lab when you can explain which identity is signed in, which subscription the context points to, which region the resource group belongs to, what the tags are used for, and how to check impact before deleting resources.

## 15. Takeaways

Azure PowerShell helps manage Azure with cmdlets that can be combined into scripts and automation workflows. To use it safely, install the right modules, authenticate with an approved identity, select and verify the tenant and subscription context, understand RBAC scopes, use templates for multi-component infrastructure, and preview critical changes beforehand. Combine resource queries with Azure Monitor and Cost Management to manage both the operational state and cost of your architecture.
