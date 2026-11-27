# Declaring Azure Functions and Related Resources with Bicep

Azure Functions is a serverless service that executes code in response to HTTP requests, messages, or events. When deploying to Azure, a Function App typically requires several supporting resources: a hosting plan, Storage Account, Application Insights, managed identity, access permissions, application settings, triggers, and sometimes a virtual network, queue, Key Vault, or deployment slot.

**Bicep** is an Infrastructure as Code (IaC) language for declaring Azure resources. Instead of creating each resource in the Portal, you describe the desired state in `.bicep` files, parameterize by environment, and deploy through Azure Resource Manager (ARM). Bicep compiles down to ARM templates and supports type checking, modularization, dependency graphs, and what-if change previews.

For Java serverless, distinguish two deployment concerns: Bicep creates and configures infrastructure; the pipeline builds Java, packages it, and deploys the function code. Separating the two keeps code changes from recreating the whole infrastructure and lets Azure resources be reviewed, reproduced, and managed in version control.

## 1. Resource Model of an Azure Function App

A Function App is the unit of deployment and configuration containing one or more functions. It runs on a hosting plan, uses a runtime, has an identity, and connects to storage services or event sources.

A Java Function App architecture typically includes these resources:

| Resource | Role |
|---|---|
| Resource group | Groups resources by application, environment, or lifecycle |
| App Service plan / hosting plan | Provides compute and defines scaling, cost, and limits |
| Function App | Hosts function code, runtime, and configuration |
| Storage Account | Stores host state, leases, artifacts, or binding data depending on workload |
| Application Insights | Collects telemetry, traces, exceptions, and dependencies |
| Log Analytics workspace | Stores and queries logs/telemetry per configuration |
| Managed identity | Identity of the Function App when accessing Azure services |
| Role assignment | Grants RBAC permissions to the identity on each resource |
| Queue, topic, or event source | Emits messages/events to trigger functions |
| Key Vault | Stores secrets and certificates when needed |
| Virtual network and subnets | Private connectivity to databases or internal services |
| Deployment slot | Creates a staging slot for testing and swapping if supported by the plan |

Overview diagram:

~~~mermaid
flowchart TD
    RG["Resource group"] --> PLAN["Function hosting plan"]
    RG --> FA["Java Function App"]
    RG --> ST["Storage Account"]
    RG --> LAW["Log Analytics workspace"]
    LAW --> AI["Application Insights"]
    FA -->|"System-assigned identity"| ID["Managed identity"]
    ID -->|"RBAC role assignments"| ST
    ID --> KV["Key Vault"]
    FA -->|"Telemetry"| AI
    Q["Queue / Event source"] -->|"Trigger or binding"| FA
    VNET["Virtual network"] -. "Private access when required" .-> FA
    FA --> SLOT["Deployment slot (supported plans)"]
~~~

Not every application needs all of these resources. Start from the function's actual triggers, permissions, and dependencies; then add storage, monitoring, and networking as needed.

## 2. Bicep and Azure Resource Manager

Bicep is a declarative language. Bicep files describe desired resources and properties; Azure Resource Manager (ARM) executes the deployment and orchestrates resource creation order.

A Bicep file typically contains:

- **Parameters:** environment-specific inputs such as app name, location, SKU, or runtime settings.
- **Variables:** reusable computed values within the template, such as resource names or role definition IDs.
- **Resources:** Azure resources to create or update.
- **Modules:** template sections extracted into separate files for reuse.
- **Outputs:** values returned after deployment, such as the Function App name or hostname.

Minimal example:

~~~bicep
param location string = resourceGroup().location
param functionAppName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stordersdemo001'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageAccountId string = storage.id
~~~

This declaration creates a Storage Account and outputs its ID. Bicep uses a typed syntax, so the IDE and compiler catch many property name or type errors before submitting a deployment.

Bicep is not a sequential script. You describe the desired state; ARM automatically infers dependencies from resource references. When a dependency cannot be inferred from references, you can declare `dependsOn`, though direct references should be preferred so the dependency graph stays clear.

## 3. Choosing Deployment Scope and Organizing Files

Bicep supports multiple scopes:

- **Resource group:** commonly used when creating a Function App and application resources in the same resource group.
- **Subscription:** used when creating resource groups, policies, or subscription-level resources.
- **Management group:** used for governance across multiple subscriptions.
- **Tenant:** used for certain tenant-wide operations.

For a typical serverless application, resource group deployment is the easiest to manage. Resource groups should reflect lifecycle and ownership. You do not necessarily need a separate resource group per function if they share the same release lifecycle and security boundary.

A repository structure could look like this:

~~~text
infra/
  main.bicep
  modules/
    function-app.bicep
    storage.bicep
    monitoring.bicep
    network.bicep
    role-assignments.bicep
  parameters/
    dev.bicepparam
    staging.bicepparam
    prod.bicepparam
src/
  OrdersFunction/
pom.xml
host.json
~~~

This layout is just a suggestion. For small systems, a single Bicep file may be easier to read. When multiple resources or teams share infrastructure ownership, modularization separates responsibilities and promotes reuse.

## 4. Parameters, Variables, and Protecting Configuration

Do not hardcode values that differ across dev, staging, and production inside resource definitions. Use parameters to pass environment-specific values.

Example:

~~~bicep
@description('Function App name, must be globally unique')
param functionAppName string

@description('Azure region for deploying resources')
param location string = resourceGroup().location

@description('Java runtime version')
@allowed([
  '17'
  '21'
])
param javaVersion string = '21'

@description('SKU of the Linux Premium plan')
@allowed([
  'EP1'
  'EP2'
  'EP3'
])
param planSku string = 'EP1'

~~~

Bicep supports decorators such as `@description`, `@allowed`, `@minValue`, `@maxValue`, `@minLength`, and `@maxLength`. They validate inputs and document the template's contract.

For secrets, use secure parameters:

~~~bicep
@secure()
param externalApiKey string
~~~

However, `@secure()` only protects how ARM handles the value in deployment metadata; it does not make passing secrets on the command line safe. Prefer Key Vault references or managed identity so the function retrieves secrets at runtime. Do not commit secrets into `.bicepparam` files, source control, or pipeline logs.

## 5. Choosing a Hosting Plan Before Declaring the Function App

The hosting plan affects how resources are declared, scaling, networking, deployment, and cost. Common options include:

| Plan | Characteristics | When to Consider |
|---|---|---|
| Flex Consumption | Event-driven serverless, flexible scaling, supports configuring instance memory and concurrency | Event-driven workloads needing load-based scaling and the modern consumption model |
| Consumption (legacy) | Consumption-based, scales by trigger, has runtime and feature limits | Existing apps or workloads fitting the plan's limits |
| Premium | Always-ready instances, supports VNet and slots within plan limits | Need reduced cold starts, longer execution, or private networking |
| Dedicated (App Service) | Runs on an App Service plan with dedicated provisioned capacity | Workloads needing steady compute or sharing a plan with App Service apps |
| Azure Container Apps | Functions run in Container Apps, released via images/revisions | Need container workflows and revision/traffic management |

Do not reuse the exact same resource property set across all plans. Flex Consumption uses its own `functionAppConfig` settings; Premium/Dedicated typically use an App Service plan and `siteConfig`; Azure Container Apps uses the container app/revision model. Choose the right schema and API version for your plan and region.

The main example in this article uses a Linux Premium plan to illustrate App Service plan, Function App, managed identity, and RBAC. When deploying Flex Consumption, use the corresponding Flex resource model rather than just swapping the Premium SKU.

## 6. Declaring a Storage Account

Azure Functions needs storage for host operations and certain triggers/bindings. A storage account can also hold application data, though host storage and business data storage should be kept separate for cleaner permissions and lifecycle management.

Example Storage Account:

~~~bicep
param location string = resourceGroup().location
param storageAccountName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
  }
}

output storageId string = storage.id
output storageName string = storage.name
~~~

Storage Account names must be globally unique, 3 to 24 characters long, and contain only lowercase letters and digits. Bicep can generate names from a prefix and `uniqueString(resourceGroup().id)` to reduce collision risk:

~~~bicep
var generatedStorageName = toLower('stfn' + uniqueString(resourceGroup().id))
~~~

Do not enable public blob access unless the application requires it. When using managed identity for host storage, you can disable shared key access after confirming that all extensions and operational processes support identity-based connections.

Choose storage redundancy such as LRS, ZRS, GRS, or GZRS based on durability, regional availability, recovery requirements, and cost. Do not pick redundancy out of habit; verify support for the target region and storage account kind.

## 7. Declaring the Hosting Plan and Java Function App

The example below creates a Linux Premium plan and a Function App using Java 21. This is an illustrative configuration; runtime versions and SKUs must be verified against the region, subscription, and workload requirements.

~~~bicep
param location string = resourceGroup().location
param functionAppName string
param javaVersion string = '21'
param planSku string = 'EP1'

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-' + functionAppName
  location: location
  kind: 'elastic'
  sku: {
    name: planSku
    tier: 'ElasticPremium'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'JAVA|' + javaVersion
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'java'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
      ]
    }
  }
}

output functionAppId string = functionApp.id
output functionAppName string = functionApp.name
output functionPrincipalId string = functionApp.identity.principalId
~~~

Key properties:

- `serverFarmId` links the Function App to the hosting plan.
- `kind` identifies this as a Linux Function App.
- `linuxFxVersion` selects the Java stack version on Linux App Service.
- `FUNCTIONS_EXTENSION_VERSION` selects the major version of the Azure Functions host.
- `FUNCTIONS_WORKER_RUNTIME=java` selects the Java language worker.
- `WEBSITE_RUN_FROM_PACKAGE=1` configures running from a package for deployment models that support this setting.

For Flex Consumption, do not copy this configuration verbatim. Flex declares runtime, deployment storage, scaling, and concurrency via `functionAppConfig`; it does not use an `EP1` App Service plan or rely on `WEBSITE_RUN_FROM_PACKAGE=1` like the Premium example.

## 8. Managed Identity and RBAC for Host Storage

Managed identity allows a Function App to access Azure services without embedding passwords or account keys in configuration. With a system-assigned identity, Azure creates a principal tied to the Function App's lifecycle. When the Function App is deleted, this identity is deleted as well.

To use an identity-based connection for `AzureWebJobsStorage`, configure app settings instead of a connection string:

~~~bicep
{
  name: 'AzureWebJobsStorage__accountName'
  value: storage.name
}
{
  name: 'AzureWebJobsStorage__credential'
  value: 'managedidentity'
}
~~~

The Function App must be granted the appropriate roles on the Storage Account. For host storage, commonly required roles include Storage Blob Data Owner, Storage Queue Data Contributor, and Storage Account Contributor; if the workload uses Table storage or other extensions, additional roles may be required. Confirm role requirements based on your trigger types, extension bundle, and Functions runtime version.

Example role assignments for a system-assigned identity:

~~~bicep
var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var queueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageAccountContributorRoleId = '17d1049b-9a84-46fb-8f53-869881c3d3ab'

resource hostBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, blobDataOwnerRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      blobDataOwnerRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, queueDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      queueDataContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostStorageManagementRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, storageAccountContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageAccountContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
~~~

The role IDs above are built-in role definition IDs. The role assignment is scoped to the Storage Account and targets the Function App's identity as principal. Referencing `functionApp.identity.principalId` creates a dependency so ARM creates the Function App before assigning permissions.

RBAC can take some time to propagate. If the function starts immediately after a role assignment is newly created, the host may encounter transient authorization errors. Pipelines should wait and verify readiness before treating the deployment as complete.

Do not grant Storage Account Contributor for business data if a function only needs to read a blob or write to a queue. For application data, create dedicated role assignments scoped to the specific container, queue, or resource to minimize permissions.

## 9. Application Insights and Log Analytics

Application Insights provides visibility into function invocations, exceptions, dependencies, and traces. Workspace-based Application Insights stores data in a Log Analytics workspace, enabling queries alongside other Azure logs.

Example:

~~~bicep
param location string = resourceGroup().location
param workspaceName string
param appInsightsName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

output workspaceId string = workspace.id
output appInsightsId string = appInsights.id
~~~

Connect the Function App to Application Insights via an app setting:

~~~bicep
{
  name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
  value: reference(appInsights.id, '2020-02-02').ConnectionString
}
~~~

In the full template, this app setting goes inside `siteConfig.appSettings` of the Function App. Using `reference` creates a dependency on Application Insights. If using OpenTelemetry or another telemetry setup, determine the instrumentation approach compatible with your Java runtime and extensions.

Retention affects both cost and investigation windows. Choose retention according to operational, audit, and data policy requirements; avoid logging payloads containing tokens, secrets, or unnecessary personal data.

## 10. Combining Resources into a Complete Template

Below is an abbreviated combined template for a Linux Premium Java Function App. It highlights the relationships between hosting plan, Storage, monitoring, identity, and RBAC. Before using in production, externalize parameters, verify API versions, and add networking, tags, alerts, Key Vault, and environment-appropriate resource policies.

~~~bicep
@description('Azure region')
param location string = resourceGroup().location

@description('Function App name, globally unique')
param functionAppName string

@description('Java runtime version available in the selected region')
@allowed([
  '17'
  '21'
])
param javaVersion string = '21'

@description('Premium plan SKU')
@allowed([
  'EP1'
  'EP2'
  'EP3'
])
param planSku string = 'EP1'

var storageName = toLower('stfn' + uniqueString(resourceGroup().id))
var workspaceName = 'law-' + functionAppName
var appInsightsName = 'appi-' + functionAppName

var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var queueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageAccountContributorRoleId = '17d1049b-9a84-46fb-8f53-869881c3d3ab'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-' + functionAppName
  location: location
  kind: 'elastic'
  sku: {
    name: planSku
    tier: 'ElasticPremium'
  }
  properties: {
    reserved: true
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'JAVA|' + javaVersion
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'java'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: reference(appInsights.id, '2020-02-02').ConnectionString
        }
      ]
    }
  }
}

resource hostBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, blobDataOwnerRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      blobDataOwnerRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, queueDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      queueDataContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource hostStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, storageAccountContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageAccountContributorRoleId
    )
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output functionAppId string = functionApp.id
output functionAppName string = functionApp.name
output functionPrincipalId string = functionApp.identity.principalId
output storageAccountName string = storage.name
output applicationInsightsName string = appInsights.name
~~~

This is an illustrative baseline for a Linux Premium Function App using identity-based host storage. Verify required roles based on actual triggers and extensions. If a function uses only a subset of features, roles can be narrowed further. If deploying Flex Consumption, replace the resource configuration with the Flex schema rather than keeping the Premium plan from the sample.

The Storage Account name is derived from the resource group ID. If a name must remain stable across resource group migrations, pass it as a parameter and enforce your own naming convention. Do not attempt to rename existing Azure resources by changing the `name` property; many resource types require creating a new resource and migrating data.

## 11. App Settings, Connection Strings, and Key Vault

App settings pass configuration into the Function App process. Common settings include:

| Setting | Purpose |
|---|---|
| `FUNCTIONS_EXTENSION_VERSION` | Major version of the Functions host |
| `FUNCTIONS_WORKER_RUNTIME` | Language worker, e.g. `java` |
| `AzureWebJobsStorage__accountName` | Storage account for identity-based host connection |
| `AzureWebJobsStorage__credential` | Selects managed identity credential |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights connection |
| `WEBSITE_RUN_FROM_PACKAGE` | Run from package on supported plans |
| `APP_ENV` | Application environment name |
| `ORDERS_QUEUE_NAME` | Business queue name |

Do not embed secrets in Bicep or committed parameter files. Two common approaches are:

1. **Key Vault reference:** the app setting holds a reference to a secret in Key Vault. The Function App identity is granted permission to read the secret.
2. **Direct managed identity:** Java code uses Azure SDK `DefaultAzureCredential` or Managed Identity credentials to fetch secrets or call services.

Example app setting referencing Key Vault:

~~~bicep
{
  name: 'PAYMENT_API_KEY'
  value: '@Microsoft.KeyVault(SecretUri=https://kv-orders.vault.azure.net/secrets/payment-api-key/)'
}
~~~

For the reference to resolve, the Function App needs an appropriate identity and Key Vault must grant secret read permissions via RBAC or access policy depending on the vault configuration. If using a user-assigned identity to resolve Key Vault references, configure the corresponding identity reference on the Function App. Verify resolution status in the Azure Portal or diagnostic logs.

In Java code, do not read an app setting once and assume the secret never rotates. Design refresh/caching behavior matching the secret's TTL and security requirements.

## 12. Declaring Triggers and Related Bindings

Bicep provisions Azure resources and application settings, while triggers/bindings are typically defined in Java code via annotations. When deploying the package, the Azure Functions host reads metadata generated by the Java build to register triggers.

Example Queue Trigger:

~~~java
@FunctionName("processOrder")
public void run(
    @QueueTrigger(
        name = "message",
        queueName = "orders",
        connection = "OrdersStorage"
    ) String message,
    final ExecutionContext context
) {
    context.getLogger().info("Received an order event");
    // Validate and process idempotently.
}
~~~

The `OrdersStorage` app setting identifies the Storage Queue connection per binding configuration. When using an identity-based connection, declare the settings required by the extension—such as queue service URI and credential—and grant the Storage Queue Data Message Processor role to the identity. Exact setting names and required roles depend on the extension and version.

For Service Bus, Event Hubs, or Cosmos DB triggers, Bicep can create the namespace, queue, event hub, database, or subscription and assign RBAC. The function package contains the matching annotations/bindings. Verify that:

- Queue/topic names in annotations match the provisioned resources.
- Connection settings point to the right namespace/account.
- The function identity holds the role to receive messages or read events.
- Triggers have appropriate retry, poison-message, checkpoint, or DLQ policies.
- Staging does not accidentally consume from production event sources unless intended.

## 13. Network Integration and Private Resources

If a function needs to reach a private database or API, you can configure VNet integration on a supported hosting plan. Bicep typically must declare the VNet, dedicated integration subnet, security groups, and routes per your network architecture.

Items to verify:

- Whether the hosting plan supports VNet integration and requires a dedicated subnet.
- Whether the subnet has sufficient address space for scale-out and required network interfaces.
- Whether security groups allow outbound traffic to the database or target service.
- Whether DNS resolves private endpoints properly.
- Whether routes to the internet, NAT, or service endpoints are configured correctly.
- Whether Storage, Key Vault, and other dependencies have private endpoints if required.
- Whether network restrictions allow deployment pipelines and runtime access.

Simply placing a Function App in a VNet does not automatically grant access to every private resource. Network path and authorization are separate layers. A security group may allow connectivity while the managed identity still needs RBAC; conversely, having the right role will not succeed if DNS or routing is misconfigured.

For Flex Consumption, VNet integration and network configuration have specific plan requirements. Do not copy Premium subnet configurations directly to Flex without checking the plan documentation.

## 14. Deployment Slots and Dependent Resources

On Consumption, Premium, or Dedicated plans that support slots, you can declare slots with the `Microsoft.Web/sites/slots` resource type. Example:

~~~bicep
resource stagingSlot 'Microsoft.Web/sites/slots@2023-12-01' = {
  parent: functionApp
  name: 'staging'
  location: location
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      appSettings: [
        {
          name: 'APP_ENV'
          value: 'staging'
        }
      ]
    }
  }
}
~~~

This snippet illustrates the resource structure; add runtime configuration, identity, storage, app settings, and slot-specific permissions according to your actual deployment. Slots are not supported on Flex Consumption; Azure Functions on Azure Container Apps uses revisions instead.

Some settings must be sticky so they do not swap—for example, database, storage, queue, and trigger-disable flags. Bicep can manage slot app settings and slot-specific configurations per the `Microsoft.Web` schema. Verify after deployment that sticky settings are actually marked as slot settings; merely defining an app setting with the same name does not make it sticky.

Managed identities and certain network settings behave independently per slot. Do not assume production and staging system-assigned identities are the same principal. Assign RBAC roles appropriately to each identity and restrict which event sources staging is permitted to process.

## 15. Splitting Bicep into Modules

As templates grow, split resources by responsibility. Example Storage module:

~~~bicep
// modules/storage.bicep
param storageAccountName string
param location string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageId string = storage.id
output storageName string = storage.name
~~~

Main file invoking the module:

~~~bicep
module storageModule './modules/storage.bicep' = {
  name: 'storageDeployment'
  params: {
    storageAccountName: storageName
    location: location
  }
}

output storageAccountId string = storageModule.outputs.storageId
~~~

Modules help:

- Reuse standardized patterns.
- Separate ownership across application, platform, and security teams.
- Test and review changes independently.
- Keep the main file concise.
- Standardize naming, tagging, diagnostics, and security baselines.

Do not create a module for every tiny resource if passing parameters and outputs makes the template harder to read. A module should group resources that share a responsibility and lifecycle.

You can use a registry to share internal modules across multiple repositories. When consuming registry modules, pin explicit versions so builds do not pull unexpected changes automatically.

## 16. Parameter Files for Dev, Staging, and Production

You can create a `.bicepparam` file for each environment:

~~~bicep
// parameters/dev.bicepparam
using '../main.bicep'

param location = 'southeastasia'
param functionAppName = 'fn-orders-dev-001'
param javaVersion = '21'
param planSku = 'EP1'
~~~

~~~bicep
// parameters/prod.bicepparam
using '../main.bicep'

param location = 'southeastasia'
param functionAppName = 'fn-orders-prod-001'
param javaVersion = '21'
param planSku = 'EP2'
~~~

Do not store secrets in parameter files. The Function App name must be globally unique; other names must satisfy each resource type's constraints. Production may need different SKUs, redundancy, retention, private networking, and alerting compared to dev.

Avoid duplicating entire templates per environment. Keep a shared module/entrypoint and vary parameters to minimize drift. For genuine architectural differences such as Flex versus Premium, consider separate modules or entrypoints rather than forcing everything into one heavily branched template.

## 17. Validate, What-If, and Deploy Bicep

A basic workflow:

1. Check syntax and types.
2. Run the linter to catch poor patterns.
3. Preview changes with what-if.
4. Deploy to dev/staging.
5. Verify resource provisioning and role assignments.
6. Deploy the code package.
7. Run smoke tests.
8. Promote configuration to production through the pipeline.

Common commands:

~~~bash
az bicep build --file infra/main.bicep
az bicep lint --file infra/main.bicep
az deployment group what-if \
  --resource-group rg-orders-dev \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam
~~~

Once what-if results are reviewed:

~~~bash
az deployment group create \
  --resource-group rg-orders-dev \
  --name orders-infra-dev \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam
~~~

What-if reveals which resources will be created, modified, or deleted prior to deployment. Pay close attention to changes that cause replacement, such as resource names, SKUs, networking, or storage settings. A seemingly small change in a template can cause resource replacement or a Function App restart.

Never run production deployments directly from a personal workstation without review and access controls. Use a pipeline service connection or workload identity federation/OIDC with least-privilege permissions scoped to the target subscription/resource group.

## 18. Separating Infrastructure Deployment from Code Deployment

Bicep describes infrastructure, while the Java package holds handlers and dependencies. Both can be released independently:

~~~mermaid
flowchart TD
    A["Source commit"] --> B["Build Java with Maven"]
    A --> C["Validate Bicep"]
    B --> D["Publish immutable ZIP artifact"]
    C --> E["What-if and deploy infrastructure"]
    E --> F["Wait for identity/RBAC propagation"]
    D --> G["Deploy package to Function App"]
    F --> G
    G --> H["Smoke test HTTP/event trigger"]
    H --> I["Promote release"]
~~~

A pipeline might:

- Run `mvn -B clean verify` and build the deployment package.
- Run Bicep build/lint/what-if.
- Deploy resources into the resource group.
- Wait for RBAC propagation and check health.
- Deploy the package to the Function App via an Azure Functions deploy task or ZIP deployment.
- Run smoke tests.
- Record the commit SHA, artifact checksum, and deployment name.

When code changes frequently, you do not need to redeploy the Storage Account or workspace every time. When IAM or networking changes, deploy infrastructure before releasing code that depends on the new permissions or configuration.

## 19. Managing Drift, Changes, and Rollback

IaC is only effective when Bicep remains the source of truth. If someone edits app settings, role assignments, or network rules directly in the Portal, live state diverges from the template. That is configuration drift.

Ways to manage it:

- Restrict manual changes in production.
- Review all IaC changes through pull requests.
- Run what-if before deploying.
- Periodically check for drift and reconcile configurations.
- Preserve deployment history and artifact versions.
- Pin module versions and API versions.
- Do not delete a resource solely because it is absent from a small template file; verify deployment mode and ownership.
- Use `existing` resources when referencing resources managed by another stack.

Rolling back infrastructure is not always as simple as rolling back code. Changing SKUs, storage settings, or schemas can trigger replacement or data loss. For databases and storage, favor backward-compatible migrations, backups, and recovery plans. For the Function App, retain previous package versions in the artifact repository so you can redeploy them when needed.

## 20. Security and Least Privilege

Bicep can create IAM/RBAC, network rules, and secret references, but a valid template does not guarantee a secure design.

Core principles:

- Enable HTTPS-only and appropriate minimum TLS versions.
- Disable public blob access unless needed.
- Use managed identities instead of long-lived credentials.
- Grant role assignments at the smallest possible scope.
- Separate function identities by workload or permission boundary.
- Never write secrets into outputs or deployment logs.
- Use Key Vault and RBAC for secrets.
- Restrict pipeline deployment permissions to the target resource group and environment.
- Protect Bicep parameters and pipeline state/secrets.
- Review public network access, private endpoints, and egress.
- Enable diagnostic settings and retention per policy.
- Apply owner, environment, data classification, and cost center tags.

In particular, infrastructure deployment permissions are usually broader than function runtime permissions. Pipelines need permission to create resources and role assignments under controlled processes; the Function App identity only needs read/write permissions for the business resources the handler actually uses.

## 21. Common Issues When Declaring Azure Functions with Bicep

| Symptom | Common Cause | How to Check |
|---|---|---|
| Function App creation fails | SKU or API version unsupported in region | Check plan, region, quota, and resource providers |
| Host fails to start | Incompatible runtime stack, worker setting, or package | Check `linuxFxVersion`, `FUNCTIONS_WORKER_RUNTIME`, host logs |
| `AzureWebJobsStorage` authorization failure | Missing role or wrong identity connection setting | Check `principalId`, role assignments, `accountName`, and credential |
| Function does not receive messages | Wrong binding connection, queue name, or data-plane role | Check annotations, app settings, and trigger roles |
| Application Insights has no telemetry | Missing connection string or SDK/extension not configured | Check app settings, instrumentation, and logs |
| Function cannot reach private database | Wrong DNS, route, subnet, or security group | Check VNet integration and private endpoints |
| Deployment package not recognized | ZIP has an extra parent folder or lacks `host.json` | Inspect ZIP layout and build output |
| Deployment succeeds but triggers do not fire | Wrong function metadata, extension, or trigger settings | Check host indexing and function logs |
| Bicep reports role assignment conflict | Unstable role assignment name or existing assignment for another principal | Use a deterministic GUID and check scope/principal/role |
| What-if shows resource replacement | Changing an immutable property or resource name | Review changes before deploy and plan migration |

When troubleshooting, inspect layer by layer: ARM provisioning, identity/RBAC, app configuration, runtime startup, trigger connectivity, and business logic. Do not conclude function code is broken when resources lack permissions or the host has not started.

## 22. Production Checklist for Bicep and Azure Functions

Before promoting a template to production, verify:

1. Does the hosting plan fit runtime, scaling, networking, and deployment requirements?
2. Do resource provider API versions support all properties used?
3. Are resource names valid and stable?
4. Do parameters have clear descriptions, validation, and sensible defaults?
5. Are any secrets hardcoded in Bicep or parameter files?
6. Does the Storage Account enforce HTTPS-only, TLS, and proper public access settings?
7. Does the Function App have a managed identity?
8. Do role assignments use the right principals, roles, and minimal scopes?
9. Is `AzureWebJobsStorage` configured with identity/connection matching the runtime?
10. Are Java runtime, Functions host version, and package compatible?
11. Are app settings complete and separated by environment?
12. Do Application Insights and Log Analytics have appropriate retention?
13. Do triggers/bindings have valid event sources and data-plane permissions?
14. Have VNet, subnets, DNS, routes, and private endpoints been tested?
15. Does the slot or revision strategy match the hosting plan?
16. Have Bicep build, lint, and what-if run before deployment?
17. Do infrastructure and code packages have separate pipelines with immutable artifacts?
18. Is readiness verified after role assignments and resource provisioning complete?
19. Are drift, deployment history, and costs monitored?
20. Are backup, rollback, and recovery plans in place for critical data and resources?

## References

- [Bicep documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Azure Functions hosting options](https://learn.microsoft.com/azure/azure-functions/functions-scale)
- [Azure Functions app settings reference](https://learn.microsoft.com/azure/azure-functions/functions-app-settings)
- [Configure an identity-based connection for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference#connecting-to-host-storage-with-an-identity)
- [Azure Functions Java developer guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-java)
- [Deploy Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-deployment-technologies)
- [What-if operation for ARM deployments](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if)

## Conclusion

Bicep lets you declare a Function App and related Azure resources in a configuration that can be reviewed, reused, and deployed consistently. A complete template models the hosting plan, Function App, Storage, monitoring, managed identity, role assignments, and dependencies such as queues, Key Vault, or networking as required.

For Java Functions, Bicep should manage infrastructure and runtime configuration; Maven and CI pipelines manage building and packaging code. Use parameters and modules to separate environments, managed identities to avoid long-lived credentials, least-privilege RBAC, and what-if to preview changes. Combining IaC with immutable artifacts, readiness checks, and drift/rollback processes gives teams controlled, maintainable serverless deployments.
