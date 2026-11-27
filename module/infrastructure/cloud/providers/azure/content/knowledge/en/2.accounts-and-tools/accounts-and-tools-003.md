# Using Azure Portal and Cloud Shell

In the **Accounts and Tools** chapter, Azure Portal and Azure Cloud Shell are two ways to work directly with Microsoft Azure resources. The Portal provides a graphical interface to explore services, configure settings, and observe status. Cloud Shell provides a browser-based terminal to query, execute commands, and prepare repeatable operations.

When learning the Azure ecosystem, what matters is not just finding the button to create a resource. You need to know which identity you are using, which tenant you are in, which subscription you are operating on, what permissions you have, and where the result is verified. Those skills will be reused when deploying virtual networks, compute services, storage, databases, and application monitoring.

This lesson combines explanation with a small lab: creating a dedicated resource group in the Portal, inspecting it with Cloud Shell, updating a tag, and then cleaning up. The lab does not require creating a VM, database, or storage account for an application. The commands are guidelines for learners to proactively execute in a lab subscription where they have appropriate permissions.

## Learning Objectives

After this lesson, you will be able to:

- Locate resources and key management pages in the Azure Portal.
- Distinguish between tenant, subscription, and permission scopes before acting.
- Launch Cloud Shell with Bash or PowerShell and choose the appropriate file persistence mode.
- Inspect context using Azure CLI or Azure PowerShell.
- Cross-check the same resource group between the GUI and command line.
- Distinguish shell session data from Azure resources, while knowing how to check related errors and costs.

## 1. What Are Portal and Cloud Shell Used For?

**Azure Portal** is the unified web interface for creating, managing, and monitoring Azure resources. You access it at [Azure Portal](https://portal.azure.com/), sign in, and search for the service or resource you want to work with. See [Azure Portal overview](https://learn.microsoft.com/en-us/azure/azure-portal/azure-portal-overview).

**Azure Cloud Shell** is an Azure-managed, browser-accessible command-line environment with preinstalled tools and integrated authentication for your account. It can be opened from the Portal toolbar or at [Cloud Shell](https://shell.azure.com/). See [Cloud Shell overview](https://learn.microsoft.com/en-us/azure/cloud-shell/overview).

| Task | Portal | Cloud Shell |
| --- | --- | --- |
| Exploring a new service | Convenient for viewing configuration sections | Convenient once you know the required command group |
| Inspecting a resource | Reading Overview, Properties, and status pages | Retrieving specific properties, filtering output |
| Initial configuration creation | Wizard guiding required input fields | Commands show parameters explicitly, can be saved as scripts |
| Inventorying multiple resources | Using lists and filters | Using queries or controlled loops |
| Troubleshooting deployments | Viewing messages and operation details | Reading error codes, command outputs, and matching IDs |
| Preparing automation | Helps understand required configurations | Serves as the stepping stone to scripts and Infrastructure as Code |

Both tools interact with the same Azure resource system under the permissions of the active identity. A change executed successfully via the command line can be seen in the Portal after refreshing the data.

Having permission to open Cloud Shell does not grant extra administrative permissions. Every API call still goes through authentication, authorization, and the governance rules applied at the target scope.

## 2. Understanding Identity and Working Scope

Before every create, update, or delete operation, answer four questions:

1. **Account:** which account am I signed in with?
2. **Tenant/directory:** which directory are the identity and subscription attached to?
3. **Subscription:** which subscription do the resources and costs belong to?
4. **Scope:** does the operation target the subscription, a resource group, or a specific resource?

### Tenant, subscription, and resource group

A **Microsoft Entra tenant** is an organization's identity management boundary. A **Subscription** is the scope containing Azure resources and is tied to billing mechanisms, quotas, and related policies. A **Resource group** is a management grouping of related resources, usually sharing a similar lifecycle.

One account can access multiple tenants and multiple subscriptions. Subscription names can be very similar; when practicing, cross-check the **subscription ID** to confirm the target.

Example of a resource group identifier:

```text
/subscriptions/<subscription-id>/resourceGroups/rg-portal-shell-lab-01
```

The full identifier helps distinguish groups that share the same name across different subscriptions.

### Authentication and authorization are two different things

Signing in successfully proves that the system recognizes the identity. The ability to read or modify a resource still depends on permissions at the exact scope.

For example:

- The Reader role at an appropriate scope is typically used to view management resources.
- A role that allows managing resources does not necessarily allow granting permissions to others.
- Permission to manage a storage account does not automatically grant permission to read all blob data.
- Directory admin roles and Azure RBAC roles on a subscription serve different scopes.

When encountering a permission error, identify the specific denied action and its corresponding scope. Requesting a broader role without knowing where permissions are missing makes the system harder to govern.

## 3. Navigating Azure Portal Methodically

The interface may change depending on the service, display language, and Portal version. Search by function and service name rather than memorizing the position of a button.

### Frequently used components

| Component | How to use |
| --- | --- |
| Global search | Search for services like Resource groups, Virtual networks, Storage accounts, or resources by name |
| Portal menu and All services | Browse the service catalog |
| Home and Recent resources | Return to resources you recently worked on |
| Notifications | View progress or alerts from recent operations |
| Settings | Adjust appearance, directory, and subscription filters |
| Cloud Shell | Open the terminal inside the UI |
| Service/resource menu | Access pages specific to a service or resource |
| Breadcrumb | Return to the previous scope in the navigation flow |

When searching, distinguish between a **service** result and a **specific resource**. Opening the Resource groups service takes you to the list of groups; opening a group's name takes you to that specific group.

### Checking directory and subscription filters

In Portal settings, **Directories + subscriptions** lets you view the current directory, switch directories, and adjust subscription filters. Filters can cause a subscription to be hidden from regular lists. See [Portal settings and subscription filters](https://learn.microsoft.com/en-us/azure/azure-portal/set-preferences).

When an expected resource is missing, check in this order:

1. Is the sign-in account correct?
2. Is the current directory correct?
3. Is the subscription included in the filter?
4. Is the list filtering by a specific name, type, region, or resource group?
5. Does the identity have read permissions at the required scope?

Filters adjust display visibility. They do not change RBAC permissions and do not prevent command-line tools from operating on another subscription.

## 4. Reading a Resource Page in the Portal

When opening a resource, do not start by changing its configuration. First, verify its name, resource type, subscription, resource group, region, and identifier.

Common sections include:

| Section | Question answered |
| --- | --- |
| Overview | Which resource am I viewing and what is its overall status? |
| Properties or JSON view | What are the exact properties and identifiers? |
| Activity log | Which management operations have been recorded at this scope? |
| Access control (IAM) | How are Azure RBAC permissions assigned here? |
| Tags | What management metadata is attached to the resource? |
| Locks | Are there management locks affecting updates or deletion? |
| Deployments | Are there ARM/Bicep deployments at the supported scope? |
| Monitoring | What metrics, logs, and alerts apply to the service? |

Not every resource type has all of the sections above.

### Activity log is not application log

The Activity log records management operations, such as creations, updates, deletions, or deployment failures. It does not replace business logs, data access logs, or application diagnostics. Those log types must be viewed from their proper sources and may require configuring collection. See [Activity log in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log).

When inspecting an error, record the timestamp, scope, operation, error code, and correlation ID if present. A generic message like "deployment failed" usually requires opening details to see which sub-operation actually failed.

The Activity log has display latency. Not finding an event immediately is not enough to conclude the operation did not occur. Requests rejected before a management operation begins may also not generate a record here.

### A successful deployment must be verified against the resource

A deployment records the configuration rollout process. Even after it succeeds, you still need to check the resulting resource and expected behavior.

For example, "creating a web app succeeded" does not prove the app can reach the database or handle user requests. In this lab, what needs to be checked is simpler: right resource group, right subscription, and right tags.

## 5. Where Does Cloud Shell Run and How Is It Authenticated?

Cloud Shell runs on a temporary host provisioned by Azure for the user's session. The tool supports Bash and PowerShell; the host environment is Linux, even when you choose PowerShell. Tools such as Azure CLI and Azure PowerShell are preinstalled by the service environment. See [Cloud Shell features](https://learn.microsoft.com/en-us/azure/cloud-shell/features).

Therefore:

- Local machine paths such as `C:\Projects\app` do not automatically appear in Cloud Shell.
- Choosing PowerShell does not mean using Windows PowerShell on a Windows machine.
- Installing extra packages or changing host state does not guarantee those changes persist in the next session.
- Cloud Shell is suited for interactive administration; long-running background jobs should use an appropriate execution service.

Cloud Shell has integrated authentication for Azure CLI and Azure PowerShell. Under normal circumstances, you do not need to start by running a login command again. However, you must still check the target tenant and subscription before running management commands.

### Shell sessions and Azure resources have different lifecycles

| Object | When closing or ending the Cloud Shell session |
| --- | --- |
| Shell variables and running processes | Should not be expected to remain alive |
| Files in an ephemeral session | Not retained for the next session |
| Files in configured persistent storage | Can be retained according to storage configuration |
| Resource groups, VMs, databases created in Azure | Continue to exist until modified or deleted |
| Storage resources used by Cloud Shell | Continue to exist unless cleaned up separately |

Closing the terminal window does not undo resource creation commands and does not stop billing for existing resources.

## 6. Launching Cloud Shell and Choosing File Storage

### Prerequisites to prepare

You need a valid Azure account, an appropriate subscription, permission to use the relevant resources, and browser connectivity that meets your organization's requirements.

Cloud Shell startup documentation requires the `Microsoft.CloudShell` resource provider to be registered in the subscription. You can check this at **Subscriptions → target subscription → Resource providers**. If it is not registered and you lack permission to do so, an administrator responsible for the subscription needs to handle it. See [start an ephemeral session](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/ephemeral).

### Opening your first session

1. Sign into the Portal and verify your account and directory.
2. Select the Cloud Shell icon on the toolbar.
3. Choose Bash or PowerShell.
4. Select the subscription to use for Cloud Shell setup.
5. Choose whether to attach storage or not, then complete the displayed steps.
6. Wait for the command prompt to appear before operating.

Two file storage modes serve different needs:

| Mode | Suitable when | Things to remember |
| --- | --- | --- |
| Ephemeral, no storage account required | Quick queries or labs that do not need to retain files | Session files are not saved across subsequent uses |
| Persistent, mounted Azure Files storage | Needing to keep scripts, configs, or working files | Requires suitable storage, access permissions, and storage costs |

For the resource group lab in this lesson, ephemeral mode can suffice because the main operations do not require keeping files across sessions.

### When persistent storage is needed

You can choose to create new storage or use existing storage via the flow supported by Cloud Shell. Clearly select the subscription, resource group, and location of the storage resource. See [get started with persistent storage](https://learn.microsoft.com/en-us/azure/cloud-shell/quickstart).

When persistent storage is configured, Cloud Shell uses Azure Files to store supported content, including an image of your home directory and a file share mounted at `clouddrive`. Files outside the persisted scope do not automatically survive into the next session. See [how Cloud Shell persists files](https://learn.microsoft.com/en-us/azure/cloud-shell/persisting-shell-storage).

Do not place Cloud Shell storage inside a lab resource group that you plan to delete at the end of the session. If you delete the group containing this storage, you may lose your saved shell data as well.

The location of Cloud Shell storage, the location of the host running the shell session, and the region of application resources are separate decisions. Opening a shell in one location does not automatically force VMs or databases to be created in that same location.

## 7. Choosing Bash or PowerShell

The choice of shell should be based on the tools and syntax you want to use:

| Item | Bash with Azure CLI | PowerShell with Az module |
| --- | --- | --- |
| Common Azure tool | `az` | Cmdlets such as `Get-AzResourceGroup` |
| Creating variables | `labName="demo"` | `$labName = "demo"` |
| Reading variables | `"$labName"` | `$labName` |
| Azure output | Azure CLI typically outputs JSON or a chosen format | PowerShell objects |
| Filtering data | Azure CLI `--query` or suitable processing tools | `Where-Object`, `Select-Object` |
| Selecting a subscription | `az account set` | `Set-AzContext` |
| Checking context | `az account show` | `Get-AzContext` |

Azure CLI can also run inside PowerShell. The **shell** and the **Azure management tool** are two different layers. Switching to PowerShell does not automatically turn every `az` command into an Az cmdlet.

For example, the following Bash syntax is not PowerShell variable assignment syntax:

```bash
labResourceGroup="rg-portal-shell-lab-01"
```

In PowerShell, the corresponding syntax is:

```powershell
$labResourceGroup = "rg-portal-shell-lab-01"
```

To avoid confusion when starting out, follow either the Bash/CLI branch or the PowerShell/Az branch completely for an operation, and then compare the two approaches.

## 8. Checking and Selecting Context in Azure CLI

The examples in this section use Bash. Values inside `<...>` are placeholders to replace with your lab subscription details.

### Viewing the subscription list and current context

```bash
az account list --query "[].{Name:name,Id:id,Tenant:tenantId,Default:isDefault}" --output table
az account show --query "{Name:name,Id:id,Tenant:tenantId}" --output json
```

Cross-check `Id` and `Tenant` against the information in the Portal. The Portal filtering a subscription is not proof that Azure CLI has that same subscription selected.

### Selecting a subscription by ID

```bash
labSubscriptionId="<subscription-id>"
az account set --subscription "$labSubscriptionId"
az account show --query "{Name:name,Id:id,Tenant:tenantId}" --output json
```

Only continue if the context selection command succeeds and the output matches the target. If the command returns an error, stop that workflow branch to resolve the root cause.

For management commands in the lab, the lesson continues passing `--subscription "$labSubscriptionId"` to state the target explicitly, even when a default context is already set.

### Choosing output formats

- `--output table`: convenient for viewing a short set of fields.
- `--output json`: convenient for inspecting structure and nested properties.
- `--output tsv`: suitable when extracting simple values for further processing.
- `--query`: filters or transforms output using JMESPath expressions.

Example reading only resource group names and locations:

```bash
az group list --subscription "$labSubscriptionId" --query "[].{Name:name,Region:location}" --output table
```

`--query` changes the displayed output; it does not modify resource groups or grant additional permissions.

## 9. Checking and Selecting Context in Azure PowerShell

If you choose PowerShell/Az, use the Az module's context:

```powershell
Get-AzSubscription | Select-Object Name, Id, TenantId
Get-AzContext
```

Next, select the lab subscription:

```powershell
$labSubscriptionId = "<subscription-id>"
$labContext = Set-AzContext -SubscriptionId $labSubscriptionId -ErrorAction Stop

$labContext.Subscription | Select-Object Name, Id
$labContext.Tenant | Select-Object Id
```

`-ErrorAction Stop` ensures a PowerShell error halts the execution branch instead of continuing as if context selection succeeded. Verify the subscription and tenant before steps that modify resources.

Azure PowerShell uses contexts to hold subscription and authentication details. See [Azure PowerShell context](https://learn.microsoft.com/en-us/powershell/azure/context-persistence).

When using both `az` and Az cmdlets in one shell, you must check the context of **each tool**. `az account set` does not replace `Set-AzContext`, and switching directories in the Portal is not a verification step for the context of either tool.

Example reading resource groups using the verified context:

```powershell
Get-AzResourceGroup -DefaultProfile $labContext |
    Select-Object ResourceGroupName, Location
```

Do not rely on the context name to infer all properties. Check the actual subscription ID and tenant ID contained in the context.

## 10. Lab: Creating a Resource Group in the Portal

### Preparing the lab target

Use a subscription permitted for practice and a new resource group not used for other work.

| Item | Illustrative value |
| --- | --- |
| Subscription | Lab subscription whose ID you verified |
| Resource group | `rg-portal-shell-lab-01` |
| Metadata region | `Southeast Asia`, if policy permits |
| Environment tag | `Environment=Lab` |
| Purpose tag | `Purpose=PortalCloudShell` |

If the group name already exists in the target subscription, pick another lab name and use it consistently across all steps. Do not reuse an existing group whose contents you do not know.

A resource group is a management container. Creating an empty group does not create billable VMs, databases, or compute services. If you choose persistent Cloud Shell, the storage resource serving the shell is a separate item to monitor.

### Creating and verifying the result

In the Portal, search for **Resource groups**, select **Create**, fill in the subscription, group name, and region. Add the two lab tags if the interface supports them at that step; if not, add them via the Tags section after the group is created. Review the summary and submit the creation request.

Once the operation completes:

- Open the group and verify the subscription ID, name, region, and tags.
- Record the resource ID for cross-checking.
- Verify the group does not contain any application resources yet.
- Check Notifications and the Activity log when you need to find operation details.

The resource group's region is where the group's metadata is stored. Resources created inside the group later have their own location properties depending on each service's availability. See [manage resource groups in the Portal](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal).

If you were only granted permissions on an existing resource group, you might not have permission to create groups at the subscription level. In that case, a properly prepared lab environment is needed before performing the group creation and deletion steps.

## 11. Lab: Inspecting and Updating via Cloud Shell

Choose **one** tool branch below. Both work on the group already created in the Portal and do not require creating another group.

### Branch A: Bash with Azure CLI

Restore or declare variables for the current session and verify context as in section 8:

```bash
labSubscriptionId="<subscription-id>"
labResourceGroup="rg-portal-shell-lab-01"

az account set --subscription "$labSubscriptionId"
az account show --query "{Name:name,Id:id,Tenant:tenantId}" --output json
```

After confirming the right subscription with no errors, read the group:

```bash
az group show --subscription "$labSubscriptionId" --name "$labResourceGroup" --query "{Name:name,Id:id,Region:location,Tags:tags}" --output json
```

The output should include the group name, resource ID containing the target subscription, and the two initial tags. Region formatting in the API is usually a programmatic name such as `southeastasia`, which may differ from how the Portal displays the name.

To practice a small change, add the tag `VerifiedBy=CloudShell`:

```bash
az group update --subscription "$labSubscriptionId" --name "$labResourceGroup" --set tags.VerifiedBy=CloudShell --output json
```

Read the tags back with a separate command:

```bash
az group show --subscription "$labSubscriptionId" --name "$labResourceGroup" --query tags --output json
```

Re-reading is the step that verifies state after an update, rather than relying only on the terminal showing no error message. Refer to the [Azure CLI resource group command group](https://learn.microsoft.com/en-us/cli/azure/group?view=azure-cli-latest).

### Branch B: PowerShell with the Az module

Create a context using the lab subscription as in section 9:

```powershell
$labSubscriptionId = "<subscription-id>"
$labResourceGroup = "rg-portal-shell-lab-01"

$labContext = Set-AzContext -SubscriptionId $labSubscriptionId -ErrorAction Stop
$labContext.Subscription | Select-Object Name, Id
$labContext.Tenant | Select-Object Id
```

After confirming the right target, retrieve the group and read its properties:

```powershell
$labGroup = Get-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop
$labGroup | Select-Object ResourceGroupName, Location, ResourceId
$labGroup.Tags
```

The `Get-AzResourceGroup` cmdlet returns an object that can be processed further in PowerShell. See [Get-AzResourceGroup documentation](https://learn.microsoft.com/en-us/powershell/module/az.resources/get-azresourcegroup).

Add the tag using a merge operation to preserve existing tags:

```powershell
$labTagUpdate = @{ VerifiedBy = "CloudShell" }
Update-AzTag -ResourceId $labGroup.ResourceId -Operation Merge -Tag $labTagUpdate -DefaultProfile $labContext -ErrorAction Stop

(Get-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop).Tags
```

`Merge` adds new keys or updates keys with the same name; `Replace` replaces the entire tag set. Do not treat these two operations as equivalent. See [Update-AzTag documentation](https://learn.microsoft.com/en-us/powershell/module/az.resources/update-aztag).

### Cross-checking back in the Portal

Return to the exact resource group and use Refresh or reopen the Tags section. Verify:

```text
Environment = Lab
Purpose     = PortalCloudShell
VerifiedBy  = CloudShell
```

If you do not see the new tag yet, verify the resource ID before concluding the update failed. Then check refreshed data, scope, and any error messages.

Tags are text metadata suitable for classifying purpose, environment, or owning unit. Do not store secrets in tags. Child resources do not automatically inherit a group's tags just by residing in that group. See [Azure resource tagging guide](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources).

### Lab completion evidence

| What to prove | Evidence |
| --- | --- |
| Portal and shell target the same scope | Subscription ID and resource ID match |
| Correct group was read | Name, region, and tags returned accurately |
| Change was applied | Read-back command shows `VerifiedBy=CloudShell` |
| Portal reflects the change | Tags section displays the same values after Refresh |
| Lab scope remains clean | Group only contains what you intentionally created |

This evidence distinguishes "a command was entered" from "the target state is actually correct."

## 12. Working with Files and the Editor

Cloud Shell has a built-in editor. You can use the Editor button or the command:

```bash
code .
```

To open a specific file:

```bash
code lab-notes.txt
```

This is Cloud Shell's in-browser editor. The command does not open a VS Code window on your local computer. See [using the Cloud Shell editor](https://learn.microsoft.com/en-us/azure/cloud-shell/use-cloud-shell-editor).

A practical file workflow:

1. Check the current working directory.
2. Create or open the needed file.
3. Save the file before executing or downloading.
4. Verify the file is in a storage scope matching the session mode.
5. Download or commit to an approved version control repository if long-term retention is needed.

You can use Cloud Shell's upload/download controls to exchange files with your local machine. Uploading does not automatically turn a file into an Azure Resource Manager resource.

### Checking your current location

In Bash:

```bash
pwd
ls
```

In PowerShell:

```powershell
Get-Location
Get-ChildItem
```

When using persistent storage, only select the `clouddrive` directory after verifying the share has mounted successfully. When using ephemeral mode, export files you want to keep before ending the session.

If PowerShell is currently positioned on the `Azure:` drive, that is a provider-supplied view for navigating resource data, not a regular application file directory. Switch back to the home directory with `Set-Location ~` when you need to work with files.

### Distinguishing source data, outputs, and sensitive information

Scripts and notes with sensitive data stripped out can be saved for reuse. For command outputs, select only the necessary fields instead of exporting entire configurations.

Credentials, tokens, private keys, connection strings, and secrets must be managed according to organizational mechanisms. A file in persistent home storage or shell history may survive longer than you expect. Do not treat a browser-based terminal as a default secret store.

## 13. Costs, Session Timeouts, and Practice Limits

The Cloud Shell session host is provided at no charge under the service model, but persistent storage and Azure resources you create still carry their own charges. See the pricing section of the [Cloud Shell overview](https://learn.microsoft.com/en-us/azure/cloud-shell/overview).

Three categories must be kept distinct:

| Category | Example | How to control |
| --- | --- | --- |
| Shell environment | Temporary host for interactive sessions | Use strictly for administrative purposes |
| Long-term shell data | Azure Files and related storage | Know the location, access permissions, and data retention need |
| Managed resources | VMs, disks, databases, application storage | Check SKU, lifecycle, and costs in the target subscription |

Some resources continue incurring costs even after you close the Portal or Cloud Shell. Cleanup must be verified against the actual resource state, not based on closing the browser window.

Cloud Shell is built for interactive use and times out on inactivity. Do not rely on keeping the terminal open as a guarantee that a long-running task will complete. See [Cloud Shell FAQ and troubleshooting](https://learn.microsoft.com/en-us/azure/cloud-shell/faq-troubleshooting).

For asynchronous Azure operations, the terminal session may disconnect after the platform has accepted the request. Upon returning, query the resource or operation status before re-submitting an operation with side effects.

## 14. Troubleshooting Common Errors

### 14.1. Subscription or resource group not visible

Do not immediately recreate a group with the same name in another subscription. First check the account, tenant, Portal filters, and tool context.

In Azure CLI:

```bash
az account list --output table
az account show --output json
```

In PowerShell/Az:

```powershell
Get-AzSubscription
Get-AzContext
```

If the Portal sees the resource but the shell does not, compare full IDs. Both views may be subject to different filters or contexts.

### 14.2. AuthorizationFailed or denied operation

Read the message to identify the principal, action, and scope. Possible causes to examine include:

- Missing permissions at the target scope.
- Using the wrong identity or tenant.
- Newly granted permissions not yet reflected in the current session.
- Another operation blocked by a policy, lock, or corresponding governance condition.

These causes are not the same error. For instance, `RequestDisallowedByPolicy` indicates you need to inspect the relevant policy; escalating RBAC permissions does not bypass a policy.

If you need help from an administrator, provide the verified operation and scope along with the error message with secrets removed.

### 14.3. Cannot start or mount storage

Check the conditions relevant to your session mode one by one:

1. Is the `Microsoft.CloudShell` provider registered?
2. Is the subscription active and usable?
3. Do you have the required permissions to create or use the selected storage?
4. Is Azure Policy blocking the region, resource type, or storage configuration?
5. Is the storage network configuration compatible with the Cloud Shell option being used?
6. Is the browser, corporate network, or access policy interrupting the session?

Do not pick another storage account at random just to get past an error. You must know who owns the storage and what data it holds before using or changing its configuration.

### 14.4. Valid command fails with syntax error

Check the selected shell, variable declaration syntax, quotes, and parameters. A common mistake is pasting Bash syntax into PowerShell or vice versa.

Azure CLI has built-in help:

```bash
az group --help
az group show --help
```

PowerShell can look up cmdlets:

```powershell
Get-Help Get-AzResourceGroup -Examples
Get-Command Update-AzTag
```

When running Azure CLI inside PowerShell, it is still the `az` executable; exit code handling for external programs differs from cmdlet errors. Do not attach `-ErrorAction Stop` to an `az` command expecting it to behave like an Az cmdlet.

### 14.5. Cannot connect to a resource using a private endpoint

Having permission to manage a resource does not prove there is a network path to reach its data endpoint. Standard Cloud Shell does not sit inside your application's VNet.

You need to inspect DNS, routing, and private access designs supported by your organization. Azure offers a virtual-network-integrated Cloud Shell option for appropriate needs. Do not open public access on a resource merely to mask an undiagnosed connectivity issue. Distinguishing network errors from authorization errors helps pick the right fix.

### 14.6. Files disappear after opening a new session

Determine whether the previous session was ephemeral or persistent, where the files were located, and whether the storage still exists. Also distinguish files in the shell's filesystem from Azure resources created by commands.

A lost script does not mean the resources that script created have disappeared. Inventory the target subscription or group before rerunning anything.

## 15. Cleaning Up the Lab Within Scope

The lab in this lesson only requires a resource group and tags. Before deleting, open the right group, verify the subscription ID, resource ID, and the list of resources inside.

If the group contains other resources, identify their origin and purpose before proceeding. In particular, do not delete a group containing persistent Cloud Shell storage if that data still needs to be kept.

### Cleaning up via Azure Portal

Open the right lab group, select **Delete resource group**, review the deletion scope, and complete the Portal confirmation step. Deleting a resource group also deletes the resources inside it; this does not merely remove the group name.

After the request finishes, reload the list to verify the group is gone. If the operation fails, inspect the error details and related locks rather than assuming all resources were cleaned up.

### Cleaning up via Azure CLI

Use the lab variables verified in the current session. Read back the target and contents first:

```bash
az group show --subscription "$labSubscriptionId" --name "$labResourceGroup" --query "{Name:name,Id:id,Tags:tags}" --output json
az resource list --subscription "$labSubscriptionId" --resource-group "$labResourceGroup" --query "[].{Name:name,Type:type,Id:id}" --output json
```

Only when the output matches the lab scope and all resources inside are safe to delete, execute:

```bash
az group delete --subscription "$labSubscriptionId" --name "$labResourceGroup"
```

The example keeps the CLI confirmation prompt. When the operation completes successfully, verify:

```bash
az group exists --subscription "$labSubscriptionId" --name "$labResourceGroup"
```

The expected result is `false` when querying the right subscription with no errors. If the result or command produces an error, there is insufficient evidence to conclude cleanup is complete.

### Cleaning up via Azure PowerShell

If following the Az branch, read back the group and list resources first:

```powershell
Get-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop
Get-AzResource -ResourceGroupName $labResourceGroup -DefaultProfile $labContext -ErrorAction Stop |
    Select-Object Name, ResourceType, ResourceId
```

After verifying the deletion scope:

```powershell
Remove-AzResourceGroup -Name $labResourceGroup -DefaultProfile $labContext -Confirm -ErrorAction Stop
```

You can return to the Portal and Refresh to verify the result. Only choose one deletion method; do not run all three methods consecutively.

Cleaning up the lab group does not automatically clean up a separate storage account used for Cloud Shell. Those resources must be kept or cleaned up based on decisions about shell data, independently of the lab.

## 16. From Interactive Operations to Repeatable Workflows

The Portal is helpful for understanding options and inspecting results. Cloud Shell helps express operations as commands. When a workflow is used repeatedly, explicit parameters should be moved into version-controlled scripts or Infrastructure as Code.

A good practice cycle is:

```text
Identify target and permissions
→ Observe initial state
→ Execute a clearly scoped change
→ Read back state via API or tool
→ Compare against expected behavior
→ Record results and clean up lab resources
```

When preparing a script, do not take your entire terminal history and rerun it blindly. History can contain trial-and-error commands, delete operations, or assumptions about an old session's context.

Reusable scripts need explicit target parameters, error handling, and verification steps appropriate to the impact level. The commands in this lesson are a foundation for understanding the workflow; production environments also require change control following your organization's operational practices.

## 17. Self-Check Questions

1. Why might a resource appear in the Portal yet `az group show` returns not found?
2. Does changing the Portal's subscription filter replace `az account set`?
3. When you have already run `az account set`, why is it still necessary to check `Get-AzContext` if switching to Az cmdlets?
4. When an ephemeral Cloud Shell session ends, is a VM created during that session automatically deleted?
5. Why do tags on a resource group not prove that all child resources have the corresponding tags?
6. When a tag update command succeeds, how do you gather evidence of the new state?
7. Before deleting a lab group, what must be checked to avoid losing Cloud Shell persistent storage?

You have completed this lesson when you can use the Portal to accurately identify resources, use Cloud Shell to query and apply clearly scoped changes, and verify results using actual identifiers and state. These skills form the foundation for subsequent lessons on deploying, monitoring, securing, and controlling costs for Azure applications.
