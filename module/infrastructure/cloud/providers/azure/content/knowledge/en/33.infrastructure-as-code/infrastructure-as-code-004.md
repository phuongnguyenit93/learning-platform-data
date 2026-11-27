# Referencing Existing Resources and Managing Dependencies

## 1. Why Distinguish Existing Resources from Resources to Create?

When deploying infrastructure on Microsoft Azure with **Infrastructure as Code (IaC)**, an application frequently shares pre-existing resources: a Log Analytics workspace managed by operations, a shared virtual network, a storage account holding data, or an environment's App Service plan. Redeclaring those resources as new resources can cause a deployment to overwrite configuration that the application team does not own.

Within the **CLOUD_PROVIDERS_AZURE** module, this lesson bridges knowledge of subscriptions, resource groups, identities, and access control with application deployment using **Bicep/ARM templates**. Two distinct questions must be answered separately:

1. **Referencing:** Which resources already exist, at what scope, with what Azure Resource Manager (ARM) identifier, and how is the current deployment permitted to use them?
2. **Deployment ordering:** Which resources are actually provisioned in this deployment, and which must be ready before another resource can be created or configured?

For example, a new application uses an existing Log Analytics workspace `law-shared`. The IaC template must obtain the workspace's exact resource ID and pass it to Application Insights. When the workspace is managed by another deployment, the application template **must not assume** that referencing it will create the workspace or wait for an external deployment to finish.

After this lesson, you will be able to declare `existing` resources in Bicep, reference resources inside or outside the current resource group, understand implicit vs. explicit dependencies, structure dependencies across modules, and check risks before deploying.

## 2. The Resource Model in Azure Resource Manager

Every Azure resource has a **resource type**, **name**, **scope**, and **resource ID**. For a resource-group-scoped resource, the ID looks like:

~~~text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>
/providers/<resource-provider>/<resource-type>/<resource-name>
~~~

The snippet above wraps across lines for readability; **an actual resource ID is a single continuous string**. For example:

~~~text
/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-observability/providers/Microsoft.OperationalInsights/workspaces/law-shared
~~~

Subscription-, management-group-, tenant-scoped, and child resources follow ID structures matching their respective scopes and parent-child hierarchies. Avoid manually concatenating ID strings when Bicep or ARM provides native ways to construct typed identifiers.

| Concept | Meaning | Deployment Impact |
| --- | --- | --- |
| `resource name` | Name of the resource within its scope | Same name in a different scope refers to a different resource |
| `resource type` | E.g., `Microsoft.OperationalInsights/workspaces` | Determines the provider and supported properties/API |
| `scope` | Subscription, resource group, or another scope | Determines where ARM looks up or creates the resource |
| `resource ID` | Full identifier including scope and resource type | Commonly used by other services to link resources |
| `apiVersion` | Resource provider API version | Determines which schema/properties can be read and declared |
| `dependency` | Ordering relationship where one resource waits on another | Controls execution order **within a deployment** |

**Key takeaway:** `existing` answers *what to reference*; `dependsOn` and implicit dependencies answer *what to deploy first*. They solve two separate problems.

## 3. Declaring Existing Resources in Bicep

Bicep uses the `existing` keyword to declare a previously provisioned resource. This declaration creates a **symbolic reference** for use in the template; it does not emit create, update, or delete operations for the referenced resource.

### 3.1. Referencing Within the Same Resource Group

Create a `main.bicep` file as follows. Assume the Log Analytics workspace `law-shared` already exists in the target resource group; the template only creates a new Application Insights component linked to that workspace.

~~~bicep
targetScope = 'resourceGroup'

@description('Name of the existing Log Analytics workspace in the current resource group.')
param workspaceName string

@description('Name of the Application Insights resource to create.')
param componentName string

@description('Deployment region for Application Insights.')
param location string = resourceGroup().location

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: componentName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

output applicationInsightsId string = appInsights.id
output connectedWorkspaceId string = workspace.id
~~~

Reading each part:

- `workspace ... existing` identifies the pre-existing workspace. Because `scope` is omitted, Bicep defaults to the current deployment's resource group.
- `workspace.id` supplies the resource ID for `WorkspaceResourceId`—not a connection string or access key.
- `appInsights` has no `existing` modifier, so ARM creates or updates that resource as declared.
- `appInsights.id` is the ID of the deployment-managed resource. Re-running the template with the same name reconciles desired state rather than creating an independent duplicate.

**Note on existence checks:** Using `workspace.id` alone can construct the ID from the name and scope; that is **not** proof the workspace actually exists. The linked service or resource provider validates the ID when applying configuration. If your template reads a runtime property of the workspace, ARM issues a `reference` call and may fail earlier if missing.

### 3.2. Referencing Across Resource Groups or Subscriptions

In organizations with shared resource groups, you must declare `scope` explicitly. The following standalone Bicep snippet returns the ID of a storage account located in another resource group, potentially in a different subscription:

~~~bicep
targetScope = 'resourceGroup'

@description('Subscription containing the shared storage account.')
param sharedSubscriptionId string

@description('Resource group containing the storage account.')
param sharedResourceGroupName string

@description('Name of the existing storage account.')
param storageAccountName string

resource sharedStorage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
  scope: resourceGroup(sharedSubscriptionId, sharedResourceGroupName)
}

output sharedStorageId string = sharedStorage.id
~~~

If the resource sits in **another resource group within the same subscription**, you can use `scope: resourceGroup(sharedResourceGroupName)`. The `resourceGroup(subscriptionId, name)` function targets a resource group in a specified subscription when supported by the resource type and deployment model.

A deployment does not automatically gain permissions in another subscription or resource group. The deploying identity needs appropriate permissions to read or reference resources, and consuming services may also require **data-plane** permissions. ARM permissions and data-plane access are two separate layers.

### 3.3. Child Resources Under an Existing Parent Resource

You can create a new resource **inside** an existing parent resource. The following example creates a blob container via the management plane inside an existing storage account and `default` blob service:

~~~bicep
targetScope = 'resourceGroup'

param storageAccountName string
param containerName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

output containerId string = blobContainer.id
~~~

`parent` constructs the parent-child resource path; marking `storage` and `blobService` as `existing` does not transfer management ownership of the entire storage account to this template. Only `blobContainer` is declared for deployment. The storage account must already exist, the blob service must be available, and the deploying identity needs management-plane permissions to create containers.

## 4. How Dependencies Work

Azure Resource Manager can deploy resources **in parallel** when no dependency exists. When one resource must wait for another, ARM needs a dependency to enforce ordering.

~~~mermaid
flowchart LR
    A["New NSG"] -->|"dependency: create first"| B["New Virtual Network"]
    C["Existing Log Analytics workspace"] -.->|"resource ID used for linking"| D["New Application Insights"]
~~~

The solid arrow depicts a deployment dependency between two resources managed in the same deployment. The dashed arrow depicts a reference to a resource outside the creation scope of this deployment; it **does not** turn the existing workspace into a pre-creation task in the current deployment.

### 4.1. Implicit Dependencies from Symbolic References

In Bicep, when a resource **created in the same deployment** references a property of another resource created in that deployment, the compiler normally emits the required dependency. For example:

~~~bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param nsgName string = 'nsg-app'
param vnetName string = 'vnet-app'

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: []
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'app'
        properties: {
          addressPrefix: '10.42.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}
~~~

Here, `vnet` uses `nsg.id` from the **new NSG**. Bicep has enough context to instruct ARM to deploy the NSG before the virtual network. Adding `dependsOn: [nsg]` is unnecessary and merely duplicates the already-inferred relationship.

Similarly, when a new resource sets `parent` to a **new** parent resource, Bicep understands the parent-child hierarchy and generates the proper dependency automatically.

### 4.2. Referencing `existing` Does Not Create a Deployment Dependency

Consider replacing the new NSG above with a pre-existing NSG:

~~~bicep
resource sharedNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' existing = {
  name: 'nsg-shared'
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-app'
  location: resourceGroup().location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.50.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'app'
        properties: {
          addressPrefix: '10.50.1.0/24'
          networkSecurityGroup: {
            id: sharedNsg.id
          }
        }
      }
    ]
  }
}
~~~

ARM uses the ID of `nsg-shared` when creating the virtual network and **does not** deploy that NSG. If the NSG does not yet exist or the ID is wrong, creating the association will fail. If the NSG is created by another pipeline, you must ensure that pipeline finishes successfully **before** starting the dependent deployment.

Do not treat `existing` as a synchronization mechanism between two independent deployments. Ordering across pipelines or deployments must be enforced by pipeline orchestration, stage/job dependencies, or explicit readiness checks.

### 4.3. When Is Explicit `dependsOn` Needed?

Bicep supports the `dependsOn` property on a resource or module when **a real deployment order requirement exists** that cannot be inferred from a property reference or `parent`. Syntax skeleton:

~~~bicep
// Add inside the declaration of a newly created resource or module:
// dependsOn: [
//   resourceCreatedEarlier
// ]
~~~

Add it only to **resources or modules created within the same deployment** after confirming a genuine dependency. Unnecessary dependencies reduce parallelism; mutual dependencies trigger a `CircularDependency` error.

With `existing`, there is no creation operation to wait on. Adding `dependsOn` to wait for a resource managed by another deployment does not synchronize across separate deployments.

## 5. Dependencies Between Bicep Modules

When splitting infrastructure into modules, the same rule applies: **pass outputs from the producing module into the consuming module or resource**. Reading `module.outputs` automatically establishes the dependency between deployment operations.

Suppose there are two files in the same directory.

**File `workspace.bicep` — creates the Log Analytics workspace:**

~~~bicep
targetScope = 'resourceGroup'

param workspaceName string
param location string

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

output workspaceId string = workspace.id
~~~

**File `main.bicep` — invokes the module and creates Application Insights:**

~~~bicep
targetScope = 'resourceGroup'

param workspaceName string
param componentName string
param location string = resourceGroup().location

module monitoring './workspace.bicep' = {
  name: 'deploy-monitoring-workspace'
  params: {
    workspaceName: workspaceName
    location: location
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: componentName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: monitoring.outputs.workspaceId
  }
}
~~~

Because `appInsights` consumes `monitoring.outputs.workspaceId`, ARM knows the `monitoring` module must complete before configuring the consuming resource. No manual `dependsOn` is needed.

**Architectural choice:** If the workspace belongs to the platform team and is deployed in a separate pipeline, the application module should accept `workspaceName`/scope or `workspaceResourceId` as inputs and either declare an `existing` resource or pass the ID directly. Avoid pulling the workspace into the application module as a managed resource, which would let application deployments alter shared infrastructure.

## 6. Equivalent in ARM JSON Templates

Bicep is a declarative language that compiles to ARM JSON templates. Traditional ARM JSON **has no direct `existing` keyword equivalent**. For existing resources, templates typically use `resourceId(...)` to construct the ID or `reference(...)` to read runtime properties.

The ARM JSON example below deploys only Application Insights and links it to an existing Log Analytics workspace in the same resource group:

~~~json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "workspaceName": {
      "type": "string"
    },
    "componentName": {
      "type": "string"
    }
  },
  "resources": [
    {
      "type": "Microsoft.Insights/components",
      "apiVersion": "2020-02-02",
      "name": "[parameters('componentName')]",
      "location": "[resourceGroup().location]",
      "kind": "web",
      "properties": {
        "Application_Type": "web",
        "WorkspaceResourceId": "[resourceId('Microsoft.OperationalInsights/workspaces', parameters('workspaceName'))]"
      }
    }
  ]
}
~~~

Related ARM functions:

| ARM Expression | Purpose |
| --- | --- |
| `resourceId('Microsoft.Storage/storageAccounts', name)` | Builds a resource ID in the current resource group |
| `resourceId(rgName, 'Microsoft.Storage/storageAccounts', name)` | Builds an ID in another resource group of the same subscription |
| `resourceId(subscriptionId, rgName, 'Microsoft.Storage/storageAccounts', name)` | Builds an ID in a specified subscription and resource group |
| `reference(resourceId(...), apiVersion)` | Instructs ARM to read runtime properties from the resource provider |
| `listKeys(resourceId(...), apiVersion)` | Invokes key listing when supported by the provider and permitted by RBAC |

**Be careful with dependencies in ARM JSON:** `resourceId(...)` only constructs an ID string; it **does not** create a dependency on its own. When both source and target **are created in the same template**, declare the dependency via ARM mechanisms (such as `dependsOn`) if the reference does not infer it automatically. In ARM JSON, certain forms of `reference` using a **same-template resource name** can infer a dependency, whereas passing a **full resource ID** usually does not. In Bicep, symbolic references let the compiler handle these relationships much more cleanly.

Never use `listKeys` or secret-exposing outputs just to look up an ID. When applications need access to a workspace, storage, or Key Vault, prefer managed identities and scoped RBAC over exposing credentials in deployment outputs or logs.

## 7. How to Choose the Right Dependency Pattern

When reading a template, classify each link using the table below:

| Scenario | How to Declare | Who Guarantees Ordering / Existence? |
| --- | --- | --- |
| New resource A needs ID of new B in the same Bicep deployment | Reference `b.id` or `b.properties...` | Bicep/ARM infers the dependency |
| New child resource with a new parent | `parent: parentResource` | Bicep/ARM infers the dependency |
| New resource A uses existing B | `b ... existing` and `b.id` | Operations must ensure B exists; no create action for B |
| Resource A needs a value from module B | Use `moduleB.outputs.someValue` | ARM waits for module B to finish |
| New A and B need ordering without a property reference | Explicit `dependsOn` if genuinely needed | ARM waits per declaration |
| A and B are provisioned by **two separate pipelines** | Cross-pipeline outputs, stage/job ordering, readiness checks | Pipeline orchestration, not `existing` |

For complex dependency graphs, sketch the resources **owned by the current deployment** and draw arrows from prerequisites to consumers. If A depends on B and B depends on A, redesign: separate baseline creation from cross-linking configuration, or remove the cyclic reference—reordering lines in Bicep will not break a cycle.

## 8. Safe Deployment and Verification

### Step 1: Confirm the Actual Resource ID and Scope

Example for an existing workspace:

~~~bash
az account show --query "{subscription:id, tenant:tenantId}" -o json
az resource show \
  --resource-group rg-observability \
  --resource-type Microsoft.OperationalInsights/workspaces \
  --name law-shared \
  --query "{id:id,location:location}" -o json
~~~

First confirm the active subscription, then verify the workspace exists in the expected resource group. When working across multiple subscriptions, specify `--subscription` explicitly or set the right CLI context first. Reading an ID does not mean the application identity holds all permissions on that workspace.

### Step 2: Evaluate Changes Before Applying

For the `main.bicep` example in Section 3.1, once the existing resource is verified in the target resource group:

~~~bash
az deployment group what-if \
  --resource-group rg-app \
  --template-file main.bicep \
  --parameters workspaceName=law-shared componentName=appi-demo
~~~

This command assumes the workspace lives **inside `rg-app` itself**; if it lives in `rg-observability`, use the explicit `scope` version from Section 3.2. Before deploying for real, inspect the `what-if` output: expected changes must be confined to application-managed resources, with no surprise updates to shared infrastructure. `what-if` predicts changes and does not completely replace deployment-time permission and validation checks.

When the diff looks right, deploy with:

~~~bash
az deployment group create \
  --resource-group rg-app \
  --template-file main.bicep \
  --parameters workspaceName=law-shared componentName=appi-demo
~~~

For shared environments, select the right scope, parameter file, and internal approval workflow before running `create`.

### Step 3: Verify the Association Post-Deployment

~~~bash
az resource show \
  --resource-group rg-app \
  --resource-type Microsoft.Insights/components \
  --name appi-demo \
  --query "{id:id,workspace:properties.WorkspaceResourceId}" -o json
~~~

Compare `workspace` in the output against the resource ID verified in Step 1. Also inspect deployment status and live service functionality; having the right ID linked does not by itself prove telemetry data is flowing successfully.

## 9. Common Errors and Remediation

| Symptom | Possible Cause | How to Check or Fix |
| --- | --- | --- |
| `ResourceNotFound` / `ParentResourceNotFound` | Wrong name/scope or existing parent not yet provisioned | Verify ID, subscription, resource group, resource type, and external provisioning order |
| `InvalidResourceReference` or linking failure | Syntactically valid ID, but resource is missing or incompatible | Look up live ID; verify region, resource type, and service constraints |
| `AuthorizationFailed` / `LinkedAuthorizationFailed` | Identity lacks permissions on referenced resource or scope | Check RBAC on both the deployment scope and the linked resource scope |
| `CircularDependency` | New resources depend on each other in a loop | Fix the dependency graph; separate creation from cross-configuration |
| Deployment runs before shared resource is ready | External pipeline unfinished; `existing` does not wait | Add stage/job dependencies and readiness verification |
| Deployment unexpectedly modifies shared infrastructure | Existing resource declared as new, or wrong scope | Switch to `existing`, check ownership boundaries, run `what-if` |
| Cannot read runtime property | Identity can build IDs but lacks resource read rights; wrong API version | Check permissions, API version, and provider queries |

Also distinguish **readiness** from **deployment success**. ARM may report a deployment succeeded while a dependent service still needs network rules, RBAC propagation, DNS records, or warm-up time. Across multi-deployment systems, checking service health belongs in orchestration logic rather than artificial `dependsOn` hacks.

## 10. Hands-On Exercise: Application Using a Platform-Managed Workspace

**Scenario:** The platform team manages `law-shared` in `rg-observability`; the application team deploys `appi-orders-dev` into `rg-orders-dev` within the same subscription. The application team must manage Application Insights without altering shared workspace settings.

1. Create `main.bicep` based on Section 3.1 and add a `sharedResourceGroupName` parameter. Inside `workspace ... existing`, set `scope: resourceGroup(sharedResourceGroupName)`.
2. Pass `workspaceName=law-shared`, `sharedResourceGroupName=rg-observability`, and `componentName=appi-orders-dev` when running `what-if` targeting `rg-orders-dev`.
3. Confirm the diff includes no create or update operations on the Log Analytics workspace. Verify the projected `WorkspaceResourceId` matches the shared resource ID.
4. Design-simulate the scenario where the workspace is created by another pipeline: identify which stage must run first and what condition proves the workspace is ready. Then analyze what breaks if you keep `existing` but remove the pipeline wait condition.

**Completion criteria:** Bicep manages only one new application-owned resource; the workspace is declared `existing` with the right scope; the link uses `workspace.id`; existence and access verification steps are included; and cross-pipeline dependencies are handled explicitly. Never convert `existing` into a managed resource just to force ordering.

## 11. Takeaways for Azure IaC Design

- Use `existing` for pre-existing resources, specifying exact **name + type + scope** while keeping team ownership boundaries clear.
- Use symbolic references to **new** resources and `module.outputs` so Bicep infers dependencies; add `dependsOn` only when there is a concrete technical reason.
- Separate resource IDs, ARM permissions, data-plane permissions, and service readiness. Holding an ID neither grants access nor proves a service is operational.
- Coordinate independent deployments via pipeline stages and readiness checks; `existing` does not synchronize separate deployments.
- Inspect `what-if`, verify resource IDs, and validate live links after deployment to avoid unintended impacts on shared infrastructure.

Mastering how to reference existing resources and manage dependencies lets an Azure architecture reuse platform foundations, provision components in the right order, and keep strict control over what each template owns.
