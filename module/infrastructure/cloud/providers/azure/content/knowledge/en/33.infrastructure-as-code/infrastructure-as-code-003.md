# Bicep Modules and Reusable Infrastructure Components

In the **CLOUD_PROVIDERS_AZURE** module, learners explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networking, compute, storage, and data services; the goal is to know how to deploy, monitor, secure, and control costs for an application architecture on Azure. Part of the **Infrastructure as Code** chapter, this lesson teaches how to build **Bicep modules** to encapsulate an Azure infrastructure component into a reusable, testable, versioned contract that can be deployed safely across environments.

**End-to-end scenario:** a Java team deploys an ordering application on Azure App Service/AKS, using Azure Storage for invoices, a Virtual Network for internal access, Key Vault for secrets, Azure Monitor for observability, and Azure SQL for data persistence. If every application copies and pastes hundreds of lines of ARM/Bicep to create a Storage Account, the team will quickly face inconsistencies in TLS, logging, tags, SKUs, network security, and lifecycle management. Bicep modules centralize standardized decisions in one place so applications consume them through **parameters/outputs** with controlled changes.

After this lesson, you will be able to:

- Explain **Bicep, Azure Resource Manager, and module deployments**; distinguish modules from resources, parameter files, and nested deployments.
- Design a **module contract** covering inputs, defaults, constraints, outputs, scope, dependencies, and security responsibilities.
- Build a complete **Storage Account** module, invoke it from **`main.bicep`**, and deploy across environments using **`.bicepparam`**.
- Use **local modules, Bicep registries (OCI on Azure Container Registry), Azure Verified Modules**, and **Template Specs** appropriately.
- Apply **module scopes**, loops, conditions, dependency inference, composability, and separation of resource group vs. subscription deployments.
- Validate infrastructure with **build/linter, validate, what-if, deployment outputs**, and post-deploy testing.
- Organize repositories, semantic versioning, CI/CD, Azure RBAC, secure parameters, Azure Policy, monitoring, cost controls, and rollback workflows.
- Spot common pitfalls: missing outputs, wrong scope, resource name collisions, missing role-assignment permissions, circular dependencies, module version drift, and destructive resource changes.

## 1. Where Does Bicep Fit in the Azure IaC Ecosystem?

**Bicep** is a declarative infrastructure language built by Microsoft to author **Azure Resource Manager (ARM) templates** more cleanly than JSON. You describe the desired state of Azure resources; the Bicep compiler transpiles your files into an ARM template, and the **Azure Resource Manager deployment engine** executes the resource provider operations.

```text
Source repository
  |
  +-- main.bicep
  +-- modules/storage.bicep
  +-- modules/network.bicep
  +-- environments/dev.bicepparam
  +-- environments/prod.bicepparam
  |
  v
Bicep compiler / module restore
  |
  v
ARM deployment template + parameter values
  |
  v
Azure Resource Manager
  |
  +--> Microsoft.Storage resource provider
  +--> Microsoft.Network resource provider
  +--> Microsoft.KeyVault resource provider
  +--> Microsoft.Insights resource provider
  |
  v
Azure resources and deployment outputs
```

**Bicep is not a continuously running infrastructure daemon.** Deployments go through ARM. It does not run your Java application code, does not replace Azure RBAC, does not automatically enable monitoring across all resources, and does not guarantee a production application is healthy merely because an ARM deployment succeeded.

### 1.1. Declarative vs. Sequential Commands

Manual CLI commands such as:

```bash
az group create ...
az storage account create ...
az network vnet create ...
```

form an **imperative sequence of operations**. Bicep defines **resources, properties, and relationships**; the engine resolves dependencies and orchestrates provisioning. The declarative approach makes diffs reviewable, standardizes configuration, and supports repeatable runs—though you must still design lifecycles carefully to avoid destructive updates.

### 1.2. What Is a Bicep Module Under the Hood?

A **module** is a Bicep file (or a module from a registry or Template Spec) **invoked from another Bicep file** using the `module` keyword. It groups resources and logic for a cohesive capability: storage, networking, observability, compute, data, identity, and so on.

At compile time, a module call is emitted as a **nested ARM deployment** (via deployment resources) according to Bicep/ARM semantics. Do not think of a module as a Java library or a function executing inside a JVM.

### 1.3. What Modules Do Not Do

- They do not automatically elevate Azure subscription-level permissions.
- They do not automatically know which resources belong to dev vs. prod unless callers pass the right scope and parameters.
- They do not guarantee application-level readiness across dependencies.
- They do not replace Azure Policy or architecture reviews.
- They are not free: they provision real resources with quotas, costs, and lifecycles.
- They do not "hide" secrets from authorized viewers simply by putting `@secure()` on everything or using outputs carelessly.

## 2. Why Use Modules Instead of Copy/Pasting Bicep?

Suppose three projects share the same Azure Storage requirements:

| Property | Team A | Team B | Team C |
|---|---|---|---|
| Minimum TLS | 1.2 | Left at default | 1.2 |
| Public blob access | Disabled | Enabled | Disabled |
| Diagnostic settings | Yes | No | No |
| Tags owner/costCenter | Yes | Missing | Different schema |
| Naming | Follows convention | Ad-hoc | Ad-hoc |
| SKU/redundancy | Standard_LRS | Standard_GRS | Standard_LRS |

When organizational policy changes (for example, prohibiting public blob access), updating multiple copied templates is error-prone. **Modules** centralize stable requirements and expose only intentional variations:

```text
                  platform/storage module
                  +----------------------+
                  | TLS >= 1.2           |
                  | Blob public disabled |
                  | Required tags        |
                  | Controlled SKU       |
                  +----------------------+
                         ^      ^      ^
                         |      |      |
                     Orders   Billing  Support
                       App      App      App
```

**However, do not turn everything into a "mega-module".** If a single module provisions networking, SQL, AKS, storage, logs, and business resources just to deploy a simple API, its parameter list explodes and changing one part can impact the entire system. Split along **lifecycle and ownership boundaries**, not merely by Azure resource type names.

### 2.1. Measurable Benefits

- **Consistency:** uniform security defaults, naming, tagging, and logging patterns.
- **Reuse:** multiple teams consume the same component via a single contract.
- **Reviewability:** module changes are reviewed in one place.
- **Maintainability:** root templates focus on composition instead of per-property boilerplate.
- **Governance:** policy, approval, and CI validation can be enforced on the module.
- **Testing:** modules can be tested independently and in composition before rollout.
- **Versioning:** new releases roll out per application, avoiding surprise fleet-wide mutations.

### 2.2. Risks of Reuse

A bug in a shared module can propagate across many deployments. Overwriting a published version or renaming an output without a migration path can break many callers at once. Therefore, **modules require versioning, owners, tests, compatibility contracts, and a deprecation policy**.

## 3. Core Bicep Keywords

| Keyword/Concept | Purpose | Example |
|---|---|---|
| `targetScope` | Default deployment scope of the template | `targetScope = 'resourceGroup'` |
| `param` | Input from deployment/caller | `param location string` |
| `@description` | Documentation for consumers | `@description('Azure region')` |
| `@allowed` | Restricts allowed values | SKU/environment allowlist |
| `@minLength`, `@maxLength` | String/array length constraints where supported | Storage name length |
| `@secure` | Marks a secure parameter | Input password/API key |
| `var` | Variable computed from inputs | Suffix/tags/derived settings |
| `resource` | Creates/manages an Azure resource | `Microsoft.Storage/storageAccounts` |
| `existing` | References a pre-existing resource | Key Vault / Log Analytics workspace |
| `module` | Invokes another module | `module storage './modules/storage.bicep' = {...}` |
| `scope` | Sets the deployment scope of a module | Another resource group |
| `output` | Public return value of a template/module | Resource ID, endpoint |
| `dependsOn` | Explicit dependency when inference is insufficient | Rarely needed manually |
| `if`, `for` | Conditional deployment and resource/module loops | Optional diagnostics, multi-region |

### 3.1. `main.bicep` and `modules/*.bicep`

`main.bicep` is not a mandatory keyword: it is a **naming convention** for the entrypoint template. Modules are ordinary valid Bicep files and can be built, validated, or deployed standalone if supplied with appropriate parameters and scope. The root template defines how modules are composed.

### 3.2. Bicep Uses Resource Provider API Versions

```bicep
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  // ...
}
```

The date after `@` is the **ARM resource API version**, not the Bicep compiler version or the Azure SDK for Java version. Choose a supported API version compatible with the properties you need, and check release/deprecation notes when upgrading; do not bump versions blindly without testing.

### 3.3. Symbolic Name vs. Azure Resource Name

```bicep
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stordersdev123456'
  // ...
}
```

`storage` is the **symbolic name** for internal Bicep references, while `stordersdev123456` is the **actual Azure resource name**. Renaming the symbolic name does not change the live resource; changing `name` or `scope` can create a new resource and leave the old one behind depending on deployment mode and lifecycle.

## 4. Module Contract: Inputs, Outputs, and Invariants

A well-designed module acts like a **public API**: callers know what to pass and what the module guarantees to provide, without needing to know internal resource layout details.

### 4.1. Recommended Inputs

- **Name or prefix:** must comply with resource naming rules and uniqueness requirements.
- **Location:** usually parameterized rather than hardcoding regions.
- **SKU/tier:** constrain choices to an approved subset.
- **Tags:** environment, owner, and cost center per policy.
- **Network/security controls:** only options with genuinely approved variants.
- **Existing resource IDs:** references to Log Analytics workspaces, VNets/subnets, or identities when needed.
- **Feature flags:** only for optional resources with clear lifecycles.

### 4.2. Recommended Outputs

- Canonical **Resource ID** for downstream modules to reference.
- Non-sensitive **name/endpoint** when callers need it.
- **Principal ID** of a managed identity for identity modules (never a client secret).
- **Subnet ID / Key Vault URI** depending on module type.

**Never output passwords, Key Vault secret values, Storage Account keys, or connection strings containing keys.** ARM deployment outputs and history become a leak vector if poorly designed. For secrets, use managed identities, Key Vault references, or tightly scoped secure parameter passing.

### 4.3. Do Not Expose Every Resource Property

If a storage module accepts 60 parameters mirroring 60 resource properties, it is merely a thin wrapper providing no standardization value. Expose only what callers need to vary and preserve intentional **security defaults**. Any escape hatch for edge cases should require explicit review rather than an unconditional `param disableSecurity bool = false`.

### 4.4. Contract Table

| Field | Required? | Default | Rules |
|---|---|---|---|
| `storageAccountName` | Yes | None | 3–24 characters, lowercase letters/digits, globally unique |
| `location` | No | Resource group location | Approved region |
| `skuName` | No | `Standard_LRS` | Approved SKU set |
| `tags` | No | `{}` | Merge required tags via caller or policy |
| Output `storageAccountId` | Yes | N/A | ARM resource ID, no secrets |
| Output `blobEndpoint` | When needed by callers | N/A | Blob service endpoint |

**Module parameter constraints do not replace Azure naming or Policy validation.** For example, `@minLength` and `@maxLength` do not check allowed character sets or global uniqueness. Preflight naming checks and deployment validation are still required.

## 5. Repository Structure for a Modular Project

Example source layout:

```text
infrastructure/
├── main.bicep
├── modules/
│   ├── storage.bicep
│   ├── network.bicep
│   ├── diagnostics.bicep
│   └── identity.bicep
├── environments/
│   ├── dev.bicepparam
│   ├── staging.bicepparam
│   └── prod.bicepparam
├── bicepconfig.json
└── docs/
    └── module-contracts.md
```

**This directory tree is an in-lesson illustration, not an instruction to create files outside the assigned Markdown file.** In practice, teams may keep shared platform modules in a central repository and consumer templates in service repositories.

### 5.1. Separating Shared Modules from App Composition

- **Platform modules:** storage, networking, monitoring, identity, security patterns.
- **App composition:** selects modules, instances, environment names, and wiring.
- **Environment parameters:** region/SKU/naming/tags; never plaintext secrets.
- **Policy/CI:** validate, what-if, approval, deployment, and post-deployment verification.

### 5.2. File Naming Conventions

Use **capability-focused names** such as `storage-account.bicep`, `network-vnet.bicep`, or `sql-database.bicep`, rather than a catch-all `common.bicep`. For larger modules, use nested directories and a README documenting inputs/outputs; never create circular imports or module references.

### 5.3. Reuse Is a Means, Not an End in Itself

If a resource appears only once and has an independent lifecycle, keeping it in the root Bicep file may be simpler. Extract a module when there is **genuine reuse, an ownership boundary, complexity, or policy to encapsulate**.

## 6. Core Lab: Authoring a Storage Account Module

We will design an illustrative **`modules/storage.bicep`** file for a Bicep repository. The example focuses on a baseline-secure storage account; production environments requiring advanced networking or diagnostics will extend it later.

### 6.1. Complete Module Code

```bicep
targetScope = 'resourceGroup'

@description('Storage account name: 3-24 lowercase letters/digits, globally unique.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Azure region where the storage account is created.')
param location string = resourceGroup().location

@description('Storage redundancy SKU approved for this workload.')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
])
param skuName string = 'Standard_LRS'

@description('Resource tags.')
param tags object = {}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: skuName
  }
  kind: 'StorageV2'
  tags: tags
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Enabled'
  }
}

@description('ARM resource ID of the deployed storage account.')
output storageAccountId string = storageAccount.id

@description('Blob service endpoint, without an account key.')
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
```

**Security scope of this example:** `allowBlobPublicAccess: false` disables anonymous Blob public access, but **`publicNetworkAccess: 'Enabled'` does not mean the storage account is only reachable over a private network**. The service still exposes a public endpoint requiring authorization. Production workloads requiring private-only access must configure firewalls, `defaultAction: Deny`/network rules, or private endpoints and private DNS per policy—**never deploy this minimal example as-is and claim it is private-only**.

### 6.2. Why Use Decorators?

- `@description` clarifies the API contract for callers.
- `@minLength` and `@maxLength` catch obvious invalid values before or during deployment.
- `@allowed` blocks arbitrary SKUs outside the module's approved set.
- `param location` enables multi-region deployment and local validation.
- `output storageAccountId` provides a stable output for downstream modules.

Decorators do not replace checking **global storage name uniqueness, regional SKU support, pricing, encryption, or network policies**. Run ARM/Policy validation before production deployments.

### 6.3. True Meaning of Idempotency

Deploying the same template with the same resource ID and properties lets ARM update or no-op the existing resource declaratively. **Idempotency does not mean every change is harmless**: changing names, SKUs, immutable properties, or replacement-triggering settings can be rejected or create a separate resource. Always inspect `what-if` and plan migrations for stateful resources.

## 7. Root Entrypoint Calling the Module with `module`

The **`main.bicep`** file acts as the root template at resource group scope:

```bicep
targetScope = 'resourceGroup'

@description('Environment name.')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string

@description('Storage account name. Must be globally unique.')
param storageAccountName string

param location string = resourceGroup().location
param owner string = 'orders-platform'
param costCenter string = 'commerce'

var commonTags = {
  environment: environment
  owner: owner
  costCenter: costCenter
  managedBy: 'bicep'
}

module storage './modules/storage.bicep' = {
  name: 'storage-${environment}-${uniqueString(resourceGroup().id)}'
  params: {
    storageAccountName: storageAccountName
    location: location
    skuName: environment == 'prod' ? 'Standard_ZRS' : 'Standard_LRS'
    tags: commonTags
  }
}

@description('Storage account ARM ID for downstream modules.')
output storageId string = storage.outputs.storageAccountId

@description('Storage Blob endpoint for applications using managed identity.')
output storageBlobEndpoint string = storage.outputs.blobEndpoint
```

### 7.1. Reading the Syntax Top to Bottom

`module storage ... = { ... }` declares a **module deployment resource**. Inside it:

- `'./modules/storage.bicep'` is the local module path being called.
- `name` is the **ARM nested deployment name**, not the storage account name.
- `params` maps caller inputs to the module's public parameters.
- `storage.outputs...` reads outputs returned by the module after deployment.

### 7.2. Two Easily Confused Names

```text
Nested deployment name:
  storage-prod-<short-deterministic-suffix>

Actual Azure Storage Account name:
  stordersprodxxxxxxxx
```

**The nested deployment name** must be valid, stable, and non-colliding within its scope when multiple deployments run concurrently. **The storage account name** must be globally unique, 3–24 characters long, and lowercase letters/digits only. `uniqueString(...)` generates a deterministic suffix from its inputs, but cannot guarantee global uniqueness across all Azure subscriptions; validate and enforce proper naming conventions.

### 7.3. Callers Do Not Need to Know Internal Resource Symbols

The caller only consumes `storage.outputs.storageAccountId`, without knowing whether the module internally names the resource `storageAccount` or later refactors its implementation across multiple resources. This is the essence of **encapsulation**.

### 7.4. Never Put Secrets in Outputs

If the root needs Blob connectivity, use **managed identity + Storage Blob Data Contributor/Reader** alongside the endpoint—do not output storage account keys or connection strings containing a Shared Key. In CI, deployment outputs may appear in logs; protect even seemingly non-sensitive outputs if they expose internal resource names or IDs.

## 8. `.bicepparam` Parameter Files for Dev and Prod

Do not maintain nearly identical `main-dev.bicep` and `main-prod.bicep` files just for different regions or SKUs. Use **one composition template** with separate parameter files.

### 8.1. `environments/dev.bicepparam`

```bicep
using '../main.bicep'

param environment = 'dev'
param storageAccountName = 'stordersdev123456'
param location = 'southeastasia'
param owner = 'orders-team'
param costCenter = 'commerce-dev'
```

### 8.2. `environments/prod.bicepparam`

```bicep
using '../main.bicep'

param environment = 'prod'
param storageAccountName = 'stordersprod123456'
param location = 'southeastasia'
param owner = 'orders-team'
param costCenter = 'commerce-prod'
```

These account names are illustrative only; **there is no guarantee they are available or globally unique**. The root template chooses the SKU by environment; for production, verify **`Standard_ZRS`** regional availability and requirements before deploying.

### 8.3. Using Parameter Files with the CLI

```bash
az login
az account set --subscription "<approved-nonproduction-subscription-id>"

RG="rg-orders-dev"
az group create --name "$RG" --location southeastasia

# Bicep CLI and Azure CLI versions must support .bicepparam.
az deployment group what-if \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam

az deployment group create \
  --name orders-storage-dev \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam
```

With tooling that supports `.bicepparam` and `using '../main.bicep'`, Azure CLI resolves the template directly from the parameter file. On older CLI versions, syntax and capabilities may differ; **upgrade/verify Azure CLI and Bicep versions** before running in CI. Creating a resource group and deploying are **hands-on operations that can incur costs**; run them only in authorized environments, never ad-hoc in a production subscription.

### 8.4. Parameter Files Are Not Secret Vaults

Never commit `param sqlAdminPassword = 'P@ssword...'` into a repository. Use Bicep/ARM-supported secret references, CI secure variables/Key Vault, or passwordless managed identity authentication. **`.bicepparam` is a plain-text source file, not an encryption layer.**

## 9. Second Module: Virtual Network and Subnet

To see that modules apply beyond Storage, let's build a networking module with a clean interface. This **`modules/network.bicep`** module owns one VNet and one application subnet; the example omits NSGs, UDRs, and peering and should be extended to match your real network policy.

### 9.1. Network Module Contents

```bicep
targetScope = 'resourceGroup'

@description('Virtual Network name.')
param vnetName string

@description('Subnet name for the application.')
param appSubnetName string = 'snet-app'

@description('VNet CIDR.')
param vnetCidr string = '10.40.0.0/16'

@description('Application subnet CIDR, contained in the VNet range.')
param appSubnetCidr string = '10.40.1.0/24'

param location string = resourceGroup().location
param tags object = {}

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetCidr
      ]
    }
  }
}

resource appSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = {
  parent: vnet
  name: appSubnetName
  properties: {
    addressPrefix: appSubnetCidr
  }
}

output vnetId string = vnet.id
output appSubnetId string = appSubnet.id
```

**Why use a child resource?** `appSubnet` declares `parent: vnet`, so Bicep/ARM knows the resource hierarchy and required ordering. Do not add `dependsOn: [vnet]` just to restate an already-inferred dependency.

### 9.2. Caller Combining Two Modules

In a root file that needs both networking and storage, you can declare:

```bicep
module network './modules/network.bicep' = {
  name: 'network-${environment}'
  params: {
    vnetName: 'vnet-orders-${environment}'
    appSubnetName: 'snet-orders'
    vnetCidr: '10.40.0.0/16'
    appSubnetCidr: '10.40.1.0/24'
    location: location
    tags: commonTags
  }
}

output applicationSubnetId string = network.outputs.appSubnetId
```

This is a **fragment meant to be placed into `main.bicep` from Section 7**, using `environment`, `location`, and `commonTags` defined there. Do not copy this fragment into a standalone file expecting it to build. Each environment must use non-overlapping CIDRs; dev/staging/prod in peered or hybrid VNets require coordinated IP planning.

### 9.3. What Should a VNet Module Own?

There are two common patterns:

1. **VNet + subnet module** when both share the same team and network service lifecycle.
2. **Separate VNet module** and **subnet/NSG/route module** when a platform team owns the VNet while product teams manage individual subnets or attachments.

Choose based on **ownership and change frequency**. If multiple modules modify a VNet's `subnets` property through different deployment paths, you risk **last-writer-wins / lost updates**. Designate a clear **single writer** for each resource or child resource.

## 10. Communicating Between Modules via Outputs

Suppose a private networking or application compute module needs the newly created subnet:

```text
network module
  |
  +-- output appSubnetId
              |
              v
        compute module
        param subnetId
              |
              v
        compute resource
```

A root composition can look like:

```bicep
module network './modules/network.bicep' = {
  name: 'orders-network'
  params: {
    vnetName: 'vnet-orders-dev'
    appSubnetName: 'snet-app'
  }
}

module application './modules/application.bicep' = {
  name: 'orders-app'
  params: {
    subnetId: network.outputs.appSubnetId
  }
}
```

**This is a schematic composition example:** `application.bicep` must be implemented by your team with `param subnetId string` and actual resources. Because it references `network.outputs.appSubnetId`, Bicep automatically infers the **dependency** between the two module deployments without manual `dependsOn`.

### 10.1. Outputs Are a Versioned Contract

If module version 1.1 outputs `appSubnetId` and version 2.0 renames it to `subnetResourceId`, existing callers fail to compile or restore. Renaming or changing the type of an output is a **breaking change**. Best practices:

- Keep output names and shapes stable within a major version.
- Add new outputs alongside old ones instead of removing them abruptly.
- Provide migration notes whenever contracts change.
- Run consumer compilation tests across key callers before publishing.

### 10.2. Do Not Output Huge Untyped Objects

Writing `output everything object = storageAccount` or dumping raw resource state couples callers to internal implementation details, increases sensitive-data exposure, and can run into runtime-property issues. Output only the **required IDs, names, and URIs** with stable types. If complex metadata is needed, define an explicitly versioned object contract.

### 10.3. Limits of Dependency Inference

ARM/Bicep infers ordering from references, `parent`/`scope`, and outputs; it cannot model **non-ARM business prerequisites** such as "wait 10 minutes after DB provisioning for schema migrations to finish". Schema migrations, app health checks, or Key Vault RBAC propagation belong in **deployment pipeline orchestration and readiness tests**, not abused `dependsOn` chains.

## 11. When Is `dependsOn` Needed?

Example:

```bicep
module storage './modules/storage.bicep' = {
  name: 'orders-storage'
  params: {
    storageAccountName: storageAccountName
  }
}

module other './modules/other.bicep' = {
  name: 'orders-other'
  params: {
    // Output reference creates an automatic dependency.
    storageResourceId: storage.outputs.storageAccountId
  }
}
```

This is an **illustrative fragment** requiring `storageAccountName` in the root and a corresponding `other.bicep` file. Because `other` consumes an output from `storage`, ordering is already inferred. `dependsOn` is only necessary when a genuine dependency **cannot be expressed via an expression or scope** and is clearly justified.

### 11.1. Anti-Pattern: Serializing Every Module

```bicep
// Avoid creating unnecessary dependency chains:
// network -> storage -> keyvault -> sql -> app -> monitor
```

Storage and VNet can deploy in parallel if independent; forcing serial execution slows deployments and complicates debugging. Maintain a **dependency DAG** reflecting actual resource relationships—not file order or personal preference.

### 11.2. Module Compilation Does Not Prove Runtime Readiness

A module returning a resource ID after a successful ARM deployment does not guarantee **the Java app in App Service can connect to SQL** or that **AKS Pods are healthy**. Add post-deployment smoke tests and health gates.

## 12. Scope: Resource Group, Subscription, Management Group, or Tenant?

Bicep/ARM supports target scopes including **resource group**, **subscription**, **management group**, and **tenant**, depending on resource types and module design. Not every resource type can be deployed at every scope; you need matching API/resource provider support and Azure RBAC permissions.

### 12.1. Resource Group Scope

```bicep
targetScope = 'resourceGroup'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: resourceGroup().location
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
```

This is a **fragment** requiring `param storageAccountName string` if used standalone. Typically deployed with `az deployment group create` to provision an application into a resource group.

### 12.2. Subscription Scope Creating a Resource Group and Calling a Module

```bicep
targetScope = 'subscription'

@description('Azure region for the resource group and storage.')
param location string
param resourceGroupName string
param storageAccountName string

resource appRg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

module storage './modules/storage.bicep' = {
  name: 'storage-${uniqueString(subscription().id, resourceGroupName)}'
  scope: appRg
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

output storageId string = storage.outputs.storageAccountId
```

The `storage.bicep` module has `targetScope = 'resourceGroup'`, while the root targets the subscription. Setting `scope: appRg` routes that module deployment into the newly declared resource group; this is a valid **cross-scope module deployment** when permissions and APIs allow it.

Corresponding CLI commands:

```bash
az deployment sub what-if \
  --location southeastasia \
  --template-file ./subscription-main.bicep \
  --parameters location=southeastasia \
               resourceGroupName=rg-orders-dev \
               storageAccountName="<globally-unique-storage-name>"

az deployment sub create \
  --location southeastasia \
  --template-file ./subscription-main.bicep \
  --parameters location=southeastasia \
               resourceGroupName=rg-orders-dev \
               storageAccountName="<globally-unique-storage-name>"
```

`--location` on a subscription deployment specifies where **deployment metadata** is stored, distinct from the `location` parameter for the resource group and storage; they may match, but serve two different purposes. Creating a resource group at subscription scope requires corresponding ARM permissions. **Never run against a production subscription outside change review.**

### 12.3. Calling a Module Against an Existing Resource Group

From a root template with `targetScope = 'subscription'`:

```bicep
param sharedResourceGroupName string
param storageAccountName string

resource sharedRg 'Microsoft.Resources/resourceGroups@2022-09-01' existing = {
  name: sharedResourceGroupName
}

module storage './modules/storage.bicep' = {
  name: 'shared-storage-module'
  scope: sharedRg
  params: {
    storageAccountName: storageAccountName
  }
}
```

This **does not create** `sharedRg` because of `existing`; if the resource group does not exist yet, the deployment fails when ARM attempts to target that scope. `existing` merely references it—it does not grant permissions or transfer resource ownership.

### 12.4. Scope Is Part of the Contract

A networking or storage module normally targets a resource group; an Azure Policy assignment module may target a subscription or management group; a role assignment module scopes to its target resource. If a caller passes a `scope` incompatible with the module's `targetScope` or resource types, the Bicep compiler or ARM raises an error. Never "solve" that by granting subscription Owner instead of fixing the scope.

## 13. Conditional Modules with `if` and Feature Flags

An application may only need a diagnostics workspace in production. You can use **conditional deployment** when a module is genuinely optional.

```bicep
param deployDiagnostics bool = true
param logAnalyticsWorkspaceId string = ''

module diagnostics './modules/diagnostics.bicep' = if (deployDiagnostics) {
  name: 'orders-diagnostics'
  params: {
    workspaceId: logAnalyticsWorkspaceId
    targetResourceId: storage.outputs.storageAccountId
  }
}
```

This is a **composition fragment**: it requires a team-authored `diagnostics.bicep` module and the `storage` module from Section 7. Different resource types have different diagnostic categories and scopes; **never assume a single generic diagnostics module works for every Azure resource**.

### 13.1. Output Risks on Skipped Modules

When `deployDiagnostics = false`, the module is not deployed. If the caller still accesses `diagnostics.outputs...` without a guard, the deployment can fail or trigger compiler warnings about nullable/conditional resources. Only read outputs when **the condition is guaranteed**, using guarded conditional expressions as supported by your Bicep version.

### 13.2. Feature Flags Must Clarify Lifecycle

Flipping `deployDiagnostics` from `true` to `false` **does not automatically ensure old logs or diagnostic resources are retained or deleted per policy**. Depending on deployment mode, previously created resources may remain live or behave differently. Before disabling a resource-provisioning module, establish a migration plan, run `what-if`, and decide on retention.

## 14. Module Collections with `for` Loops

When you need multiple Storage Accounts across environments or regions, you can loop over a module:

```bicep
targetScope = 'resourceGroup'

@description('Globally unique Storage Account names.')
param storageAccountNames array

@description('Default region for all accounts in this example.')
param location string = resourceGroup().location

@batchSize(1)
module storageAccounts './modules/storage.bicep' = [
  for (accountName, index) in storageAccountNames: {
    name: 'storage-${index}-${uniqueString(resourceGroup().id)}'
    params: {
      storageAccountName: accountName
      location: location
    }
  }
]

output storageIds array = [
  for i in range(0, length(storageAccountNames)):
    storageAccounts[i].outputs.storageAccountId
]
```

### 14.1. `@batchSize` and Concurrency Limits

`@batchSize(1)` demonstrates **sequential deployment one iteration at a time** to reduce contention/throttling or enforce ordering when genuinely needed. When accounts are independent, parallel deployment is faster; do not apply `@batchSize(1)` everywhere out of habit.

### 14.2. Loop Limits and Quotas

ARM/Bicep imposes limits on loop iterations, resource counts, nested deployments, throttling, and per-provider quotas. A loop creating 1,000 Storage Accounts may compile cleanly yet hit quotas, cost limits, or policies. Enforce **upper bounds**, clear ownership, and policies; use staged wave orchestration when needed.

### 14.3. Deployment Names Must Be Stable

In a collection, nested deployment `name` values must be **unique within scope when multiple instances deploy**. Using the array index generates position-based names, meaning **reordering the array** shifts instance mappings and deployment names. For stateful workloads needing stable identities, prefer a **stable logical key** over an index and verify name length limits.

### 14.4. Collection Outputs

`storageIds` is an ordered array matching the collection. Consumers should not assume index `0` is always `eastus` if inputs can be reordered; pass structured input objects with explicit names/regions and return mapped outputs per contract when needed.

## 15. Designing Small Modules Composed into a Larger System

An illustrative architecture:

```text
subscription/main.bicep
    |
    +-- resource group(s)
              |
              v
application/main.bicep
    |
    +-- network module
    |      +-- VNet/subnet/NSG
    |
    +-- identity module
    |      +-- managed identity
    |
    +-- storage module
    |      +-- storage account
    |
    +-- key-vault module
    |      +-- Key Vault (no secret values in outputs)
    |
    +-- database module
    |      +-- Azure SQL database/server
    |
    +-- compute module
    |      +-- App Service/AKS/workload configuration
    |
    +-- observability module
           +-- Log Analytics/diagnostic settings/alerts
```

### 15.1. Dependencies You Should Encode

- Compute module needing a subnet ID: consume `network.outputs...`.
- App Service/VM/AKS identity needing a role assignment scope: reference **resource ID + principal ID**.
- Diagnostic settings needing a workspace ID: reference **workspace module output**.
- Database firewall/private endpoint needing network/subnet config: reference **network outputs**.

### 15.2. Dependencies You Should Not Encode by "Blindly Waiting"

- Java application schema migrations that must run after SQL database provisioning.
- Key Vault secrets provisioned by a security team that must exist before pod startup.
- Azure RBAC token propagation before data-plane calls succeed.
- App configuration, deployment slots, or traffic switching requiring smoke tests.

These belong in **pipeline sequencing, IaC outputs + application health checks**, not arbitrary sleep scripts or ad-hoc VM extensions inside a module.

### 15.3. Ownership and Team Boundaries

A platform team may own the core VNet while product/network teams manage workload subnets under policy. Do not let an application root template overwrite a shared central VNet/NSG if that team lacks ownership; use `existing` references with clear contracts, or split deployments by scope and approvals.

## 16. Module Patterns That Reduce Coupling

| Type | Purpose | Example |
|---|---|---|
| **Resource module** | Wraps a single resource + key defaults | Storage Account |
| **Pattern module** | Coordinates a group of resources sharing a lifecycle | Private Endpoint + DNS zone group for a specific service |
| **Composite module** | Combines multiple modules into a workload baseline | Java App Service + identity + diagnostic settings |
| **Policy module** | Applies guardrails/RBAC at the right scope | Azure Policy assignment |
| **Integration module** | Connects pre-existing resources | Role assignment / diagnostic settings |

### 16.1. Choosing Granularity for Operations

A "resource" module is too thin if it wraps one resource and exposes every raw property without enforcing standards; a "composite" module is too coarse if every small change redeploys the entire stack. **Good boundaries** usually share:

- The same owning team.
- The same deploy/update/delete lifecycle.
- Shared security and compliance invariants.
- A stable public output API and manageable input surface.
- Reasonable standalone testability and cost.

### 16.2. Reuse Does Not Mean Every App Must Look Identical

Dev may use `Standard_LRS`, while prod needs `Standard_ZRS` or geo-redundancy; one app requires private-only access, while another uses a firewalled public endpoint. Modules should define **an approved set of options**, rather than hardcoding a single configuration that ignores business requirements.

## 17. Three Module Sources: Local, Registry, and Template Specs

Bicep supports multiple module sources. Choosing a source affects **caching, authentication, versioning, governance, networking, and CI build behavior**.

| Type | Conceptual Reference Syntax | Characteristics | When to Use |
|---|---|---|---|
| **Local file** | `'./modules/storage.bicep'` | Lives in the source repo, versioned with commits | Small/single-team modules edited together |
| **OCI module in registry** | `'br:contoso.azurecr.io/bicep/modules/storage:1.2.0'` | Versioned artifact published to a registry; requires restore | Platform modules shared across multiple repositories |
| **Template Spec** | `'ts:<subscription>/<rg>/<spec>:<version>'` | ARM Template Spec versioned Azure resource | Organizations standardizing on ARM Template Specs governance |
| **Azure Verified Modules (AVM)** | Registry modules via published public aliases/paths | Curated library with tested patterns and conventions | Accelerate adoption, while still reviewing contracts |

**Local module paths** resolve relative to the caller file. With registries, Bicep must download artifacts into its module cache (or reuse a valid cached copy), and the build identity/environment needs read access. Template Specs require ARM access and proper scope/version—they are not automatic local files.

### 17.1. Choosing by Organizational Boundaries

- One service repo with 3 internal modules: start with **local modules**.
- A platform team providing storage/network baselines to 20 services: a **private OCI Bicep registry** with pinned versions and release notes usually fits best.
- An organization standardized on **ARM Template Specs**: reference approved Template Spec versions.
- Common foundational patterns: evaluate **AVM** before reinventing the wheel, while carefully checking contracts, outputs, defaults, and security.

### 17.2. Do Not Confuse a Bicep Registry with a Container Image Registry

Bicep modules in Azure Container Registry use **OCI artifact storage**, but **they are not runnable Docker container images**. Module repositories and tags do not spin up AKS or Container Apps workloads; ARM remains the deployment engine.

## 18. Publishing Bicep Modules to Azure Container Registry

Suppose the platform team operates ACR `contoso.azurecr.io` and has configured a module repository (with proper permissions and scope). An example command:

```bash
az login
az account set --subscription "<approved-platform-subscription-id>"

# Verify Azure CLI Bicep subcommands and version before CI.
az bicep version

az bicep publish \
  --file ./modules/storage.bicep \
  --target br:contoso.azurecr.io/bicep/modules/storage:1.2.0
```

**Do not run against a real ACR without authorization/approval; this writes an artifact to the registry.** Your Azure CLI/Bicep version must support publish, the URI must be valid, and the deployer must hold push permissions matching ACR's **permission mode**. Classic registry RBAC uses roles such as AcrPull/AcrPush, whereas RBAC+ABAC repository permissions use repository-scoped reader/writer roles. Never assume one role works across every permission mode.

### 18.1. Consumer Using a Published Module

```bicep
targetScope = 'resourceGroup'

param storageAccountName string
param location string = resourceGroup().location

module storage 'br:contoso.azurecr.io/bicep/modules/storage:1.2.0' = {
  name: 'storage-from-registry'
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

output storageResourceId string = storage.outputs.storageAccountId
```

At build time, Bicep restores the module definition from the URI and validates parameters/outputs. Consumer repositories do not need to copy the module source, provided **the referenced version keeps a stable contract and artifact**.

### 18.2. Restoring Dependencies

```bash
az bicep restore --file ./main.bicep
az bicep build --file ./main.bicep
```

An offline runner without a populated module cache cannot restore registry artifacts. For reproducibility, pin versions, ensure registry availability and IAM permissions, protect CI credentials, and define cache/retention policies.

### 18.3. Do Not Publish Uncontrolled Mutable Tags

The tag `1.2.0` is a version convention; registries may allow overwrites depending on permissions and settings. **Never assume tags are immutable by default.** Configure release pipelines to prevent re-publishing existing tags, enforce retention/ownership policies, track provenance, and record source revision to build artifact mappings. If a URI stays the same while its content changes, consumer builds diverge via stale caches and break reproducibility.

### 18.4. Private Registry Security

A private Bicep registry should have:

- Least-privilege writers/publishers.
- Consumers restricted to reading approved repositories/scopes.
- Audit logging for publish, delete, and overwrite events.
- Separation between non-prod/test modules and released modules.
- Mandatory review, versioning, and testing prior to publish.
- Zero secrets, connection strings, or plaintext credentials in module sources.
- A contingency plan for deprecated modules or registry outages.

## 19. Bicep Module Aliases via `bicepconfig.json`

To avoid repeating long registry FQDNs and repository prefixes, Bicep supports **module aliases** in configuration.

### 19.1. Illustrative JSON Config

```json
{
  "moduleAliases": {
    "br": {
      "platform": {
        "registry": "contoso.azurecr.io",
        "modulePath": "bicep/modules"
      }
    }
  }
}
```

### 19.2. Using an Alias in a Caller

```bicep
module storage 'br/platform:storage:1.2.0' = {
  name: 'orders-storage'
  params: {
    storageAccountName: storageAccountName
  }
}
```

**This is a fragment** assuming `storageAccountName` is declared at root. The `platform` alias must exist and resolve from `bicepconfig.json` in the expected directory hierarchy. If a consumer checks out a repo missing that config, module restore will fail or target the wrong registry. Treat alias configuration as **part of the build environment API** and version it alongside the source repository.

### 19.3. Aliases Do Not Change Authorization

An alias merely shortens a URI; it does not grant Azure Container Registry pull permissions. CI agents and developers still need valid tenant/principal authentication and network reachability to read from the registry. Never embed registry passwords in alias config.

## 20. Azure Verified Modules (AVM)

**Azure Verified Modules** are a collection of IaC modules maintained by Microsoft and the community under published verification standards. Bicep AVM modules are distributed via the public Bicep registry with conventions for parameters, diagnostics, role assignments, locks, and private endpoints depending on the module.

### 20.1. Why Evaluate AVM Before Writing From Scratch?

- Broad coverage of common Azure resources and patterns.
- Typically ships with docs, examples, and usage guides.
- Follows automated validation conventions and versioned releases.
- Reduces repeated mistakes in naming, tagging, diagnostics, and security properties.

### 20.2. Never Assume an AVM Module Automatically Meets Every Security Policy

AVM does not replace your organization's security review: default settings may differ from internal policies, networking/zone layouts may differ from your architecture, and parameter/output structures can change across versions. When adopting AVM:

1. Pick the right module category (**resource module** or **pattern module**).
2. Verify the **published version** and compatibility with your CLI/Bicep toolchain.
3. Read **params/outputs**, required/optional features, and examples for that exact release.
4. Test security defaults against Azure Policy plus negative network/IAM checks.
5. Pin **specific versions**—never rely on a floating `"latest"` assumption.
6. Plan regression tests before upgrading major or minor versions.

### 20.3. Conceptual Reference Format

```text
br/public:avm/res/<provider>/<resource-type>:<published-version>
```

This is a **URI pattern with placeholders**, not a literal buildable module path/version. Look up the **exact verified registry reference** from the official documentation/registry for your target module. AVM pattern modules use different paths; do not assume one template fits all.

### 20.4. Internal Wrappers Around AVM

A platform team can publish an internal/private wrapper module:

```text
Orders App
   |
   v
Internal platform/storage module
   |
   v
Pinned AVM storage resource module
   |
   v
Azure Storage Account
```

A wrapper exposes only **approved customizations**, injects baseline tags/security/monitoring, and shields applications from raw AVM contract churn. Still, avoid wrapping so heavily that essential features become inaccessible or upgrades become opaque.

## 21. Template Specs as a Module Source

**Azure Resource Manager Template Specs** store versioned ARM templates inside Azure as governed ARM resources. Bicep can consume a Template Spec as a module via a `ts:` URI when supported by the compiler, ARM, and permissions.

### 21.1. Sample URI

```text
ts:<subscription-id>/<resource-group-name>/<template-spec-name>:<version>
```

Schematic example:

```bicep
module storage 'ts:00000000-0000-0000-0000-000000000000/rg-templates/storage-standard:1.2.0' = {
  name: 'storage-from-template-spec'
  params: {
    storageAccountName: storageAccountName
  }
}
```

This is a **fragment using a placeholder subscription ID**; replace resource IDs, version, parameter contract, and permissions—do not run it as a complete template. Template Specs are not **Azure Policy** and will not automatically approve a noncompliant deployment.

### 21.2. Choosing Between ACR Registry and Template Specs

| Criterion | OCI Bicep Registry (ACR) | Azure Template Specs |
|---|---|---|
| Primary artifact | Bicep module published as an OCI artifact | ARM Template Spec version resource |
| Reference | `br:...:version` / alias | `ts:...:version` |
| Goal | Share Bicep modules across repositories | Reuse ARM template versions governed in Azure |
| Access | ACR repository/registry permissions | ARM RBAC on Template Spec resources |
| Pipeline | Build/validate/publish Bicep module | Build/deploy ARM Template Spec versions |
| Governance | Registry, tag/version policies | Azure resource RBAC, version lifecycle |

There is no universal winner. Organizations often combine **local modules + a private registry** for Bicep while keeping Template Specs for legacy ARM templates.

## 22. SemVer and Module Compatibility Contracts

A shared module is a **dependency** for its consumers. Adopt predictable release practices such as **semantic versioning** (a governance convention, not an automatically enforced ARM feature):

| Change | Conventional Version Bump | Risk |
|---|---|---|
| Fix docs/comments without changing outputs | Patch | Low, still test |
| Bug fix preserving input/output contract | Patch | May alter property defaults; still run `what-if` |
| Add optional param with safe default | Minor | May alter behavior depending on default |
| Add new output | Minor | Usually backwards compatible |
| Rename required param or output | Major | Breaks caller compilation |
| Change default from public enabled to private-only | Major or migration release | Can break workload networking |
| Change resource type/name/scope | Major + migration | Can recreate/delete stateful resources |
| Change default database SKU/HA | Major or change-management | Cost, availability, and lifecycle impact |

**SemVer does not replace `what-if`**: a minor patch can still trigger unintended ARM updates if implementation properties change. Publish release changelogs detailing **what changed**, **who is affected**, and **migration instructions**.

### 22.1. Version Pinning in Consumers

```text
Service A -> platform/storage:1.2.0
Service B -> platform/storage:1.2.0
Service C -> platform/storage:1.3.0
```

This enables wave-based rollouts. **Never silently push every service to `latest`** via a shared alias pointing to a mutable tag. Even an urgent security-fix module requires coordinated rollout, deadlines, and per-environment canary/`what-if` checks.

### 22.2. Common Breaking Changes

- Changing `storageAccountName` from `string` to `object` or adding a new required parameter.
- Renaming output `storageAccountId` to `id`.
- Moving a resource to a different resource group or scope.
- Changing naming logic so Azure treats it as a brand-new resource.
- Tightening network defaults and cutting off existing consumer connectivity.
- Altering role assignment schemas so runtime identities lose data-plane access.

### 22.3. Deprecation Contract

When an older module version has a vulnerability or relies on a retiring Azure API:

1. Announce impacted versions.
2. Release a tested replacement.
3. Publish migration and rollback instructions.
4. Notify consumers tracked in your dependency inventory.
5. Restrict publishing/consumption of deprecated versions via policy.
6. Track adoption and alert on workloads pinned to outdated versions.

Do not delete old registry artifacts while clients still depend on restores, unless an active security emergency requires removal with a coordinated replacement plan.

## 23. Defining a "Quality Module" by Contract

A module is reusable-ready when it meets these criteria:

```text
Inputs
  - Typed and documented
  - Required fields explicit
  - Safe defaults and validation

Outputs
  - Stable names and types
  - Only necessary public data
  - No raw credentials

Security
  - Azure Policy and RBAC-compatible
  - No accidental public exposure
  - No secret values in logs/outputs

Operations
  - Tags, diagnostics and lifecycle
  - Tested updates, not only fresh create
  - What-if / negative tests / rollback guidance

Distribution
  - Pinned API/module versions
  - Signed/reviewed publishing workflow where supported
  - Changelog, ownership and deprecation notice
```

### 23.1. Module Contract Tests

Do not test only "first-time creation succeeded". Verify:

- Valid values compile, validate, and create resources.
- Invalid SKUs/names are rejected at the appropriate stage.
- Updating parameters does not unexpectedly delete unrelated resources.
- Required tags and security defaults are present post-deployment.
- Outputs match expected types consumed by downstream modules.
- No sensitive values leak in outputs or deployment logs.
- Both dev and prod configurations deploy cleanly under scoped permissions.
- Concurrent runs and module deployment names do not collide.

### 23.2. Reuse Requires Documentation

Module documentation should state:

- Purpose and explicit non-goals.
- Inputs/outputs, defaults, and constraints.
- Supported API/Bicep versions and deployment scopes.
- Security and networking assumptions.
- Example `module` usage and test environment notes.
- Pricing implications and resource lifecycle behavior.
- Changelog plus rollback/migration guidance.

If a consumer must read 1,000 lines of implementation code just to guess `skuName` or an output ID, the module lacks an adequate API contract.

## 24. Pre-Deployment Verification: Build, Validate, What-If

A reliable module deployment pipeline enforces **at least three verification layers**:

```text
Source code + pinned modules
       |
       v
1) Static Bicep compilation / linter checks
       |
       v
2) ARM validate in correct deployment scope
       |
       v
3) What-if + change/security review
       |
       v
4) Deploy to test/staging
       |
       v
5) Runtime post-deploy assertions
       |
       v
6) Production approval + deployment
```

### 24.1. Bicep Build

```bash
# Check the actual compiler version.
az bicep version

# Compile Bicep and run diagnostics/linter per config.
az bicep build --file ./main.bicep
```

Building may generate an **ARM JSON artifact** in the working directory when run on a real repo. In this lesson, **do not execute commands**—they are explained conceptually. Build catches **syntax, types, resource properties, module references, and linter diagnostics**, but does not prove Azure resources exist or names are globally unique.

### 24.2. ARM Validate

```bash
RG="rg-orders-dev"
az deployment group validate \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam
```

In toolchains compatible with `.bicepparam`, the CLI resolves the template from the `using` directive. If an older CLI lacks support, upgrade your toolchain or pass the template/parameter flags supported by that version. **Validation does not replace deployment**: resource provider checks, permissions, quotas, and network/data-plane validations may fail only during actual apply.

### 24.3. What-If

```bash
az deployment group what-if \
  --resource-group "$RG" \
  --parameters ./environments/dev.bicepparam
```

`what-if` compares the desired template against live Azure state to **predict changes**. It surfaces creates, modifies, deletes, ignores, or unknowns based on engine evaluation, yet **is not an absolute guarantee**: runtime values, `reference()` functions, provider quirks, or permissions can produce `Ignore/NoChange/unknown` results. Read diffs carefully and inspect high-risk changes.

### 24.4. Reading `what-if` as a Security Review

Example:

```text
~ Microsoft.Storage/storageAccounts/stordersprod...
    properties.publicNetworkAccess:
      'Disabled' => 'Enabled'

+ Microsoft.Network/privateEndpoints/new-endpoint

- Microsoft.KeyVault/vaults/kv-orders-prod
```

**This is simulated output, not live Azure output.** If a PR switches `publicNetworkAccess` from `Disabled` to `Enabled` or predicts deleting a Key Vault or database, halt the deployment and require security/owner review. Never waive a dangerous diff just because Bicep compiled cleanly.

### 24.5. Post-Deployment Automated Tests

Example test assertions:

- The Storage account exists in the expected resource group and subscription.
- Minimum TLS and `allowBlobPublicAccess=false` are enforced.
- Resource tags (`owner`, `environment`, `costCenter`) are applied.
- The app's managed identity holds the actual data-plane role.
- Private endpoint/DNS exist when required by production policy, and public access is denied.
- Diagnostic settings stream logs to the intended Log Analytics workspace.
- Output resource IDs match the live deployed IDs.
- The Java application can upload/download a synthetic Blob using its intended identity.

Only **post-deployment integration tests** prove end-to-end behavior. Static IaC checks cannot verify **runtime policy, networking, or identity propagation**.

## 25. Bicep Linter, Conventions, and Secure Parameters

### 25.1. Why Use the Linter?

A template can compile cleanly while still harboring risky patterns: unused parameters, hardcoded locations, redundant dependencies, secret outputs, or overly complex expressions. Bicep provides **analyzers/linter rules** configured in `bicepconfig.json` per version.

Common rule categories:

| Category | Goal |
|---|---|
| Syntax/type correctness | Templates compile cleanly |
| Unused params/vars | Avoid dead or ambiguous interfaces |
| No unnecessary `dependsOn` | Clean, accurate dependency graph |
| Secure param defaults | Prevent hardcoded plaintext secrets |
| No hardcoded environment URLs | Avoid pointing at wrong regional/tenant endpoints |
| Naming/tagging | Enforce organizational conventions |
| Allowed resource APIs/SKUs | Maintain security and governance compatibility |

Exact rule names and severity levels must be checked against your pinned **Bicep CLI version**; do not copy a linter setting from outdated docs and assume your pipeline enforces it.

### 25.2. Secure Parameters

```bicep
@secure()
@description('Database admin password, injected from an approved secret source.')
param adminPassword string
```

`@secure()` instructs ARM to handle the parameter securely (omitting its plaintext value from deployment history unlike standard parameters). However, it **does not make a plaintext source safe** if you commit passwords to Git or echo them in logs. Never return the value via `output`, or embed it in tags, resource names, or public URLs.

### 25.3. Referencing Key Vault Secrets for a Module

A pattern supported by Bicep when permissions and settings allow is passing a secret directly to a **module's secure parameter**:

```bicep
param keyVaultName string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

module database './modules/database.bicep' = {
  name: 'orders-database'
  params: {
    adminPassword: keyVault.getSecret('sql-admin-password')
  }
}
```

This is a **fragment requiring a real `database.bicep` module** with `@secure() param adminPassword string` and its remaining parameters. `getSecret()` is only valid in supported Bicep/ARM contexts—typically **inside module `params`**—not as a general-purpose function or a way to print secrets into `var`. The Key Vault must allow **ARM template deployment secret access** where applicable and the deployment principal needs corresponding access; enabling this carries security implications and should not be turned on casually just to make a demo pass. Whenever supported, **prefer managed identity for application/database workloads** to avoid passing admin passwords altogether.

### 25.4. Secure Outputs and Sensitive Data

Recent Bicep versions introduce secure output mechanisms per published release notes, yet the safest default remains **never outputting secrets at all**. Do not rely on a decorator expecting CI logs, shell commands, or downstream consumers to handle secret outputs safely if misused.

## 26. Governance: Azure Policy, RBAC, and Resource Locks

### 26.1. Bicep Does Not Bypass Azure Policy

If your organization has an Azure Policy `deny` rule blocking Storage Accounts with anonymous Blob access enabled, deploying a module with `allowBlobPublicAccess=true` will be rejected—even if the file compiles and `what-if` appears schema-valid.

```text
Bicep template
    |
    v
ARM deployment
    |
    +--> Azure Policy check / deny / modify where configured
    |
    +--> RBAC permissions
    |
    +--> Resource provider validation / quotas
    |
    v
Resource created or deployment failed
```

Modules should encode **safe defaults aligned with policy**, while **Azure Policy remains the guardrail** across all producers (Portal, CLI, Terraform, scripts)—not just team-controlled Bicep files.

### 26.2. Separating Deployment Identity from Runtime Identity

| Identity | Responsibility | Example Permissions |
|---|---|---|
| **CI deployment principal** | Create/update ARM resources | Scoped RBAC on target RG/subscription as needed |
| **Java app managed identity** | Read Blob/Key Vault data plane | Storage Blob Data Reader, Key Vault Secrets User |
| **Platform module publisher** | Publish OCI module artifacts | ACR repository write per permission mode |
| **Module consumer build agent** | Restore OCI module artifacts | ACR repository read |
| **Network owner** | Provision Private Endpoints/VNets/DNS links | Azure Network resource permissions |
| **Security owner** | Govern Policy/RBAC approvals | Scoped Azure Policy / role assignment rights |

**A CI identity with ARM Contributor does not automatically grant the Java app permission to read Blobs or Key Vault.** If a module creates role assignments, CI needs specific, narrowly scoped role-assignment permissions. Never grant subscription-wide Owner to work around `AuthorizationFailed`.

### 26.3. Least Privilege for Cross-Scope Modules

A root subscription template may create a resource group while a child module targets that RG using the **same effective deployment identity** and its inherited or assigned RBAC. If CI lacks permissions on the target scope, the module fails. Separate infrastructure provisioning from role-assignment approvals when required instead of giving one principal blanket production rights.

### 26.4. Resource Locks and Deletion Safety

Resource locks such as `CanNotDelete` or `ReadOnly` block certain management operations and update/delete actions depending on scope. Never treat locks as a substitute for authorization or backups, and test how locks interact when IaC deployments need to update resources. For critical stateful resources, combine **backup/restore, soft delete, purge protection, lifecycle reviews, and deployment safeguards**.

## 27. Multi-Environment Deployment Patterns with Modules

### 27.1. Same Code, Different Parameters and Scope

```text
                  same pinned module contract
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
               dev         staging         prod
              /   \\          /   \\         /   \\
           RG-dev  ...   RG-staging ...   RG-prod ...
           LRS            LRS              ZRS/GRS
           small          medium           production tiers
           test tags      preprod tags     owner/cost tags
```

Never let an `environment` string automatically grant production access or choose a subscription on its own. Subscription IDs, RG scopes, and CI federated environments must be enforced independently; `param environment='prod'` is just an input string, not an authorization boundary.

### 27.2. Dev vs. Staging vs. Prod

| Attribute | Dev | Staging | Prod |
|---|---|---|---|
| Subscription/RG | Non-prod | Controlled non-prod | Dedicated production |
| Module version | Can test next release | Release candidate | Approved version |
| Storage SKU | Cost-optimized | Production-like when needed | Business-continuity required |
| Network | Test VNet / limited public per policy | Production-like private paths | Least privilege / private endpoints |
| Identity | Test managed identity | Federated/workload identity test | Runtime managed identity |
| Monitoring | Baseline | Validated alert rules | Full telemetry/SLO/runbook |
| Deployment approval | Developer/team | Test/owner | Change/production approvers |
| Data | Synthetic | Synthetic/test class | Production data |

Never reuse production secrets or key material in staging merely because module outputs have the same structure.

### 27.3. Cost Impact of Version Upgrades Across Environments

Module version 1.3 adding diagnostic settings or a Private Endpoint increases storage, logging, and networking charges. An upgrade's impact **is not just code**: the same module version incurs different costs depending on region, SKU, and traffic volume. Include **estimated cost + `what-if`** per environment in PRs and release notes.

### 27.4. Separating Scope and State Ownership

A dev root deployment must never write into a production resource group. Enforce target subscription/RG restrictions via **CI environment/identity allowlists**, not just the filename `dev.bicepparam`. For shared networking resources, use **`existing` references** owned by the network team so app teams do not overwrite shared state.

## 28. CI/CD for Modules and Consumers

Design two separate pipelines:

1. **Module publishing pipeline:** tests and publishes versioned module artifacts.
2. **Consumer deployment pipeline:** restores pinned modules, runs `what-if`, and deploys application infrastructure.

### 28.1. Module Publishing Pipeline

```text
PR to platform-modules
  |
  +-- compile + linter
  +-- validate module contracts
  +-- deploy integration fixture into test RG
  +-- assert security/outputs/idempotency
  +-- run what-if on existing fixture (update test)
  +-- review API/versions/changelog
  |
  v
Trusted release branch/tag
  |
  +-- sign/review provenance as supported by policy
  +-- publish immutable version to ACR/Template Spec
  +-- verify artifact can be restored by consumer
  +-- record source revision + artifact version
```

### 28.2. Consumer Deployment Pipeline

```text
PR to orders-service
  |
  +-- pin module versions
  +-- az bicep restore/build
  +-- parameter validation + static policy checks
  +-- ARM validate + what-if against test scope
  +-- security/cost review when necessary
  |
  v
Merge
  |
  +-- deploy dev + smoke test
  +-- deploy staging + integration tests
  +-- production approval
  +-- production what-if + change gate
  +-- production deploy
  +-- app/API/identity/network health checks
  +-- record outputs, deployment/incident links
```

### 28.3. GitHub Actions Skeleton

```yaml
name: bicep-deployment-review

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  validate-nonprod:
    runs-on: ubuntu-latest
    environment: nonproduction
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_NONPROD_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_NONPROD_SUBSCRIPTION_ID }}
      - name: Compile Bicep
        run: az bicep build --file ./infrastructure/main.bicep
      - name: Preview non-prod changes
        run: |
          az deployment group what-if \
            --resource-group rg-orders-dev \
            --parameters ./infrastructure/environments/dev.bicepparam
```

**This is a manually triggered workflow skeleton on a trusted branch/environment**, not a complete copy-paste pipeline or a safe job for untrusted PRs. Configure workload identity federation / OIDC trust, GitHub protected environments, pinned action versions per security policy, repo paths, test scopes, approvals, branch protection, and output checks. Never expose Azure write credentials or production deploy permissions to PRs from forks or untrusted code; run static build/lint on untrusted PRs in isolation. Do not confuse GitHub Actions `${{ ... }}` expressions with Bicep `${...}` string interpolation—they are evaluated by different tools at different stages.

### 28.4. OIDC Does Not Grant Azure Permissions by Itself

OIDC federation proves a CI workflow matches trust claims; Azure RBAC on the deployment scope and ACR repository permissions still dictate what actions are allowed. Use separate identities for **module publisher**, **dev deployer**, and **prod deployer**.

### 28.5. Never Deploy to Production Without Reviewing the Diff

For changes affecting Key Vault, SQL, VNet, firewalls, or stateful resources:

- Require **`what-if`** against the intended target subscription/RG.
- Review security, networking, and data lifecycle impacts.
- Separate migration steps where needed.
- Obtain approvals per organizational policy.
- Prepare rollback/forward-fix plans and post-deploy verification tests.

### 28.6. Version Locking & Supply Chain

Pin **module versions**, Azure CLI/Bicep versions, and CI actions; never reference mutable `latest` or `main` branches for platform modules in production. Record SBOM/provenance artifacts where supported, protect registries against unauthorized publishes or overwrites, and monitor relevant CVEs or configuration advisories.

## 29. Drift Detection and Intentional Deployment

**Drift** occurs when live Azure state diverges from approved templates/parameters—for example, someone enables public Blob access in the Portal or alters a subnet NSG.

### 29.1. Why Is Drift Dangerous?

- Module source in Git says **Disabled** while the live resource is **Enabled**.
- A subsequent deployment can revert the manual edit and cause an unexpected outage.
- Compliance reports built from source code alone become inaccurate.
- Multiple teams editing a shared resource overwrite each other.

### 29.2. Practical Workflow

1. Periodically run **`what-if`** on authorized scopes or use appropriate drift-detection tooling.
2. Monitor Azure Policy compliance dashboards for security invariants.
3. Audit Azure Activity Logs for out-of-band management changes.
4. Reconcile tags, owners, schemas, and resource inventories.
5. Triage: is it a legitimate change missing from IaC, or an unauthorized modification?
6. Open a PR to adopt the change into code or revert it with approval.

### 29.3. Never "Blindly Re-run IaC"

If a live SQL database differs from a template due to a valid migration or emergency fix, running IaC to "fix drift" can disrupt data or networking. Require **`what-if` + owner review** and check whether multiple writers manage the resource.

### 29.4. Incremental Deployment and Deletion Semantics

ARM deployments commonly use **incremental mode** to create/update declared resources, without deleting resources omitted from the template as newcomers often assume. Complete mode carries accidental deletion risks and is increasingly superseded by **Deployment Stacks** for explicit deletion lifecycle management. Never assume setting a module's `if` flag to `false` automatically deletes previously created resources; choose an intentional **resource deletion strategy**, verify with `what-if`, and take backups.

### 29.5. Deployment Stacks vs. Modules

**Modules** structure template code. **Deployment Stacks** manage the lifecycle, deletion/detach behavior, and scope of a group of deployment-owned resources. Both can work together, but they are not synonyms and have distinct lifecycles and permissions.

## 30. Rollback: Distinguishing Code Rollback from Resource Rollback

Suppose storage module version 1.3 flips `publicNetworkAccess` to `Disabled`. An application without a Private Endpoint configured suffers an outage.

### 30.1. What Does Not Roll Back Automatically?

- Reverting a Git commit does not alter live Azure resources.
- A mid-flight ARM deployment failure does not guarantee all resource providers undo prior steps.
- Deleting a module call does not automatically remove or revert resources under incremental semantics.
- Restoring an older module version may not restore lost data or permissions.
- Storage Account/SQL names, regions, encryption settings, or delete operations can have side effects or be irreversible.

### 30.2. Rollback Plan

```text
Detect impact via application SLI
      |
      v
Pause further rollout
      |
      v
Inspect deployment operations and actual resource state
      |
      v
Choose forward-fix or approved rollback template/params
      |
      v
Run what-if against current scope
      |
      v
Approve and redeploy safely
      |
      v
Verify network/identity/data/application health
      |
      v
Record incident + regression tests
```

### 30.3. Never Use Destructive Rebuilds as a "Quick Fix"

If a storage account holds production invoices, **never delete and recreate it under a new name** just to bypass a property update error. Perform backups, migration, data-integrity checks, and RPO/RTO reviews. For stateful resources, preserving **resource identity and data lifecycle** comes first.

### 30.4. Testing Rollback in Staging

Module upgrade tests should include:

1. Deploying version N on test resources.
2. Recording state, IDs, and fixture data.
3. Deploying version N+1, running `what-if`, and verifying behavior.
4. Testing rollback or forward-fix when supported by the design.
5. Verifying data preservation and policy compliance.
6. Documenting caveats in release notes.

## 31. Tagging, Diagnostics, and Cost Control in Reusable Modules

A widely shared module is a natural place to standardize **metadata, cost attribution, and observability**, without blindly attaching expensive alerts to every resource.

### 31.1. Tags Should Carry Clear Semantics

Example:

```bicep
param environment string
param owner string
param costCenter string
param additionalTags object = {}

var requiredTags = {
  environment: environment
  owner: owner
  costCenter: costCenter
  managedBy: 'bicep'
}

// Merge precedence rules must be confirmed by the team.
var finalTags = union(additionalTags, requiredTags)
```

Here `requiredTags` is passed last so colliding keys in `additionalTags` do not overwrite mandatory values under `union` precedence semantics. **This is a fragment**; the parameters and `finalTags` must be wired into an actual resource or module. Verify organizational tagging and **cost attribution** policies, and never place passwords, personal emails, or PII into tags.

### 31.2. Diagnostics Is a Cross-Cutting Concern

A Storage Account module can accept `logAnalyticsWorkspaceId` to enable diagnostic settings, but each resource and subresource has **distinct diagnostic categories**. For example:

- Storage Account service endpoints emit service-specific logs/metrics; Blob diagnostic settings often scope to **`blobServices`** rather than the account root.
- Azure SQL, Service Bus, AKS, and Key Vault use different resource types and categories.
- Azure Monitor metric alerts require matching signals, dimensions, granularity, and action groups.

Therefore, **a single "generic" diagnostics module accepting only a resource ID is not always sufficient**. Use resource-specific pattern modules or a composite wrapper aware of target scopes and supported categories.

### 31.3. Do Not Let Modules Create Dozens of Workspaces

If every workload deployment creates its own Log Analytics workspace, observability costs, retention, RBAC, and cross-workspace queries fragment quickly. Platform teams often manage **shared workspaces by environment, region, and data classification**, passing the workspace ID to apps via parameters. Conversely, tenant or data isolation may require dedicated workspaces. Base the choice on **security and operational boundaries**, not reuse alone.

### 31.4. Tags Do Not Prove a Resource Is Secure

Having `environment=prod` is not an Azure RBAC control. A tagged resource can still be exposed to the public internet or lack encryption. Combine module defaults, Azure Policy, live property checks, post-deploy tests, and audits.

### 31.5. Cost Impact of Module Versions

| Change in Module | Potential Cost Impact | What to Check |
|---|---|---|
| Storage LRS → ZRS/GRS | Storage/redundancy billing | Region availability, DR requirements |
| Enable Private Endpoint | Hourly endpoint + data-processing charges | VNet/DNS/cross-region traffic |
| Add Log Analytics diagnostics | Log ingestion and retention fees | Categories, log volume, compliance |
| Enable Azure Monitor alerts | Alert rule evaluation and action charges | Severity, noise, budget |
| Change App Service Plan SKU | Compute cost and capacity | Load/SLO and scaling |
| Add NAT gateway/firewall | Hourly and per-GB processing charges | Security, egress, routing |
| Add Azure SQL secondary | DB, licensing, storage, and replication | RPO/RTO, region/HA |

**`what-if` is not a price quote.** Pair it with the Azure Pricing Calculator, Cost Management, budgets, and cost reviews before rolling out module upgrades in production.

## 32. Integrating Java Applications with Bicep Outputs

Bicep should provide **resource IDs and endpoints**, never raw secrets. A secure pattern:

```text
main.bicep
  |
  +-- storage.outputs.blobEndpoint
  +-- identity.outputs.clientId
  +-- keyvault.outputs.vaultUri
  |
  v
Approved application configuration / deployment manifest
  |
  v
Java application (managed/workload identity)
  |
  +-- Azure Blob SDK with TokenCredential
  +-- SecretClient for Key Vault
  |
  v
Azure data-plane operations
```

### 32.1. Java Blob SDK at Runtime

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String blobEndpoint = System.getenv("AZURE_BLOB_ENDPOINT");
if (blobEndpoint == null || !blobEndpoint.startsWith("https://")) {
    throw new IllegalArgumentException("Expected HTTPS Blob endpoint");
}

BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();
```

This is a **Java fragment** requiring the Azure SDK for Java dependencies and application wiring—not Bicep code. The runtime credential/identity must hold data-plane RBAC roles such as `Storage Blob Data Reader/Contributor` and an allowed network path. **Creating a Storage Account with Bicep does not automatically grant the Java app permission to read Blobs.**

### 32.2. Passing Outputs into Configuration Safely

After an ARM deployment, you can query outputs (replacing placeholders):

```bash
az deployment group show \
  --resource-group "rg-orders-dev" \
  --name "orders-storage-dev" \
  --query "properties.outputs" \
  --output json
```

Pass only **non-secret outputs** into app settings or pipeline variables. If sensitive outputs exist, never print the JSON to console; better yet, design module contracts to avoid secret outputs altogether. Verify the exact **deployment name**, since root deployments and nested Bicep module deployments have distinct names.

### 32.3. Never Grant Subscription Owner to a Java Service

A Java app performing data-plane operations should use a **managed or workload identity** with least-privilege permissions. The ARM deployment identity that provisions infrastructure and role assignments is a separate principal; never inject CI client secrets or subscription Owner tokens into runtime app settings.

### 32.4. Testing the Application Post-Deployment

After provisioning storage, identity, and networking:

1. Read the expected Blob endpoint from root outputs or the live resource.
2. Deploy the app configured with its intended managed/workload identity.
3. Run a synthetic upload/download test over the permitted network path.
4. Inspect Blob metadata and HTTP responses.
5. Run negative RBAC checks where appropriate.
6. Verify logs, traces, metrics, and clean up test fixtures.

A pipeline reporting "Bicep deployment succeeded" does not prove the Java application works.

## 33. Testing Modules at Three Levels

### 33.1. Static Checks

Require no live Azure resources:

- Bicep build/linter and module restoration.
- Type, `@allowed`, and contract checks.
- No hardcoded secrets.
- Required tags, baseline TLS, and public access settings.
- Disallowing unpinned external module references per policy.
- Checking for module cycles or unnecessary `dependsOn`.

### 33.2. ARM Validate / What-If

Run against a test subscription/resource group:

- Valid API and provider properties in the target region.
- Role assignment permissions and Azure Policy compliance.
- Predicted modify/replace/delete diffs on existing resources.
- Scope validity and parameter file correctness.

**Does not replace runtime tests.** ARM validate/what-if cannot verify every runtime value or side effect of provider updates.

### 33.3. Live Integration Tests

Run in a **non-production subscription/RG**:

- Deploy the module into a test resource group.
- Query Azure APIs to inspect actual live properties.
- Verify live security policies and Network ACLs.
- Re-deploy with identical parameters to confirm idempotent behavior.
- Test safe updates across allowed parameter changes.
- Verify output contracts with downstream modules.
- Test guarded deletion/cleanup aligned with retention policies.

### 33.4. Testing Matrix

| Test | Build | Validate/What-if | Live Azure |
|---|---|---|---|
| Missing parameter or wrong type | Yes | Often | Not needed |
| Valid resource API property | Partial | Partial | Yes |
| Storage name globally unique | No | Partial | **Yes** |
| Security tags/defaults applied | Contract test | Predicted | **Yes** |
| Effective data-plane RBAC | No | Role def/scope | **Yes** |
| Private DNS / port 443 connectivity | No | Incomplete | **Yes** |
| Java app reads Blob successfully | No | No | **Yes** |
| Update preserves data | No | Predicted | **Must test** |
| Module 1.3 backwards compatible | Compile consumers | What-if | Test upgrade |
| Deployment cost | No | No pricing | Actual Cost Management |

### 33.5. Use Synthetic Data Only

Never copy production SQL databases, passwords, or customer PII into test environments just to test a module. For Azure Storage, create small synthetic Blob fixtures, prefix resource names with a run ID, and **clean up test-owned resources** afterward.

### 33.6. Cleanup Requires Clear Ownership

```text
test resource group: rg-module-it-<run-id>
tags:
  purpose=module-integration-test
  owner=platform-iac
  runId=<run-id>
  expiresAt=<timestamp>
```

If CI is aborted before a `finally` or post-step runs, use a scheduled janitor enforcing **resource ID allowlists, owner/run IDs, age thresholds, and active-build checks**. **Never wipe every resource group starting with `"rg-test"`**, as another team or active build may own it.

## 34. Troubleshooting When a Bicep Module Fails to Deploy

| Symptom | Likely Cause | Next Checks |
|---|---|---|
| `BCP...` compile error | Invalid syntax, type, output, param, or namespace | Bicep compiler message & line number, API version docs |
| `Unable to restore module` | ACR URI, alias, network, auth, role, or cache issue | Registry path/version, module alias config, ACR permissions |
| `Module not found` | Wrong local relative path or missing registry tag | Root path, case sensitivity on CI filesystem |
| `InvalidTemplate` | Wrong scope, ARM constraint, or API property | ARM validation errors, `targetScope`, and resource provider |
| `StorageAccountAlreadyTaken` | Globally unique name collision | Naming convention and namespace logic |
| `LocationNotAvailable` or invalid SKU | Region/SKU/service limit | Resource provider availability and subscription quota |
| `AuthorizationFailed` | Deployment identity lacks ARM role at scope | Principal ID, subscription/RG, role assignment |
| `RequestDisallowedByPolicy` | Denied/modified by Azure Policy | Policy assignment, exemption, and remediation |
| `DeploymentFailed` | Provider failure, quota, or conflict | Deployment operations and nested module error details |
| `Circular dependency` | Module references form a cycle | Refactor graph/outputs; remove cyclic `dependsOn` |
| `Deployment name conflict` | Parallel runs sharing nested deployment name/scope | Use unique, stable module deployment names |
| `what-if unknown/ignore` | Runtime or reference evaluation limits | Review high-risk properties and test in staging |
| `output missing` | Conditional module skipped or contract changed | Guard conditional outputs, pin versions, check schema |
| Java SDK 403 post-deploy | Data-plane RBAC, ACL, or private endpoint mismatch | Runtime identity, network path, role propagation |
| Wrong tags or SKU on resource | Wrong parameter file or out-of-band drift | Live Azure properties and environment scope mapping |

### 34.1. Inspecting ARM Deployment Operations

```bash
RG="rg-orders-dev"
DEPLOYMENT="orders-storage-dev"

az deployment group show \
  --resource-group "$RG" \
  --name "$DEPLOYMENT" \
  --output json

az deployment operation group list \
  --resource-group "$RG" \
  --name "$DEPLOYMENT" \
  --output json
```

Exact subcommand names and flags can vary by Azure CLI version, so check `az deployment operation group --help` if needed. When failures happen inside a **nested deployment**, trace the module's deployment name and inspect the **inner error**—do not stop at the top-level `DeploymentFailed` line.

### 34.2. Wrong Subscription Is Riskier Than Broken YAML

A valid template deployed to the wrong subscription provisions real resources, incurs charges, and violates compliance. Before every deployment:

```bash
az account show \
  --query "{subscription:id, tenant:tenantId, name:name}" \
  --output json
```

CI pipelines should enforce subscription/RG allowlists and scoped identities—never rely solely on a filename like `prod.bicepparam` to identify the target environment.

### 34.3. Developer vs. CI Azure CLI Version Mismatch

Bicep compiling locally yet failing in CI often stems from an older toolchain, differing module registry support, or API version mismatches. **Pin Azure CLI and Bicep versions**, standardize build container images, and run integration tests on those exact versions.

### 34.4. Module Updated, Caller Still Uses Old Behavior

With ACR, local module caches or mutable tag overwrites cause local and CI builds to diverge. Do not treat "clearing the cache" as a root fix. Enforce **immutable artifact versions**, verify digests/provenance, and update consumer URIs through reviewed PRs.

### 34.5. Role Assignment and Data-Plane Permission Errors

A module may create a managed identity and role assignment on Storage/Key Vault and report ARM success, yet data-plane calls still fail with 403 due to **RBAC propagation delay, principal mismatch, token caching, or network ACLs**. Test directly from the target runtime workload, use bounded retries, and never escalate to Owner.

## 35. Runbook 1: Module Registry Restore or Publish Failure

**Symptom:** build reports it cannot restore `br:...`, or the release pipeline publish fails.

1. Verify the registry hostname, repository path, and version tag.
2. Check `bicepconfig.json` aliases and which config file is loaded.
3. Check ACR availability, network path, Private Endpoint, firewall, and DNS if applicable.
4. Verify the active identity and repository read/write roles per ACR permission mode.
5. Check whether the artifact/version already exists and review its release record.
6. Test restore on a trusted runner with proper network and IAM access.
7. If publish fails because the tag already exists, **do not force-overwrite against policy**; release a new version.
8. After fixing, build a sample consumer and verify module outputs.
9. Document the incident and strengthen pipeline checks.

**Never hardcode an ACR admin password into `bicepconfig.json` or source code** as a quick authentication workaround.

## 36. Runbook 2: `what-if` Reports Dangerous Changes

**Symptom:** `what-if` forecasts a storage account replacement, public network enablement, or Key Vault deletion.

1. Halt automatic production deployment gates.
2. Confirm the target subscription/RG, module version, and parameter file.
3. Inspect source diffs, ARM resource IDs, properties, and scope.
4. Assess impact on **data preservation, RPO/RTO, RBAC, and networking**.
5. Account for `Ignore/unknown` results and known `what-if` limitations.
6. Test against a staging fixture with realistic data/permissions.
7. Choose a reviewed migration, forward-fix, or rollback plan.
8. Obtain sign-off from resource, security, and cost owners.
9. Deploy in controlled waves with post-deploy tests and monitoring.

**Never let pipelines auto-approve destructive changes simply because Bicep compiles cleanly.**

## 37. Runbook 3: Module Upgrade Breaks a Java App

**Symptom:** ARM deployment reports `Succeeded`, yet the Java app loses connectivity to Azure SQL, Storage, or Key Vault.

1. Check application SLIs/health and determine customer impact scope.
2. Review resource change history, module version diffs, and `what-if` logs.
3. Check whether resource IDs, names, or scopes changed.
4. Verify public network access, Private Endpoints, DNS resolution, and firewalls post-upgrade.
5. Verify the managed identity client ID / principal ID and data-plane RBAC.
6. Check whether app configurations pulled from outputs are stale.
7. If RBAC propagation is lagging, use bounded retries and inspect logs to separate auth errors from network errors.
8. Choose data-preserving mitigations—never delete and recreate stateful resources hastily.
9. Validate synthetic transactions and Azure Monitor alerts.
10. Add a regression integration test before the next module release.

If tightened network security broke app access, prioritize **fixing private connectivity** rather than reopening an unapproved public endpoint.

## 38. Case Study: Bicep Modules for an Azure Ordering Platform

### 38.1. Context

A company operates three Java services:

- **Orders API:** Spring Boot on App Service/AKS backed by Azure SQL.
- **Receipt Worker:** consumes a queue and archives invoices in Azure Blob Storage.
- **Notification Worker:** uses Azure Service Bus to dispatch notifications.

Shared infrastructure includes a VNet, Key Vault, managed identities, Log Analytics, storage, and alerting. Services must isolate **dev/staging/prod**, carry `owner`/`costCenter` tags, and enforce **private networking** in production.

### 38.2. Module Layout

```text
iac/
  modules/
    network.bicep          # VNet/subnets/NSG baseline
    storage.bicep          # Storage account TLS/anonymous access policy
    identity.bicep         # User-assigned managed identities
    keyvault.bicep         # Vault RBAC/access policy model
    database.bicep         # SQL resource pattern
    compute.bicep          # App Service or AKS pattern
    monitoring.bicep       # Workspace/diagnostics/alerts as supported
    private-link.bicep     # Resource-specific PE/DNS pattern
  main.bicep               # Composition + dependency wiring
  environments/
    dev.bicepparam
    staging.bicepparam
    prod.bicepparam
```

In practice, this is a **blueprint diagram**; modules not implemented in this lesson require their own implementations and contracts. The core focus here is **design principles and the two working Storage and VNet sample modules** provided above.

### 38.3. Key Contracts

| Module | Key Inputs | Outputs for Callers |
|---|---|---|
| Network | VNet name, CIDRs, region, tags | VNet ID, subnet IDs |
| Storage | Account name, SKU, tags, network policy | Account ID, Blob endpoint |
| Identity | Identity name, region, tags | Resource ID, client ID, principal ID |
| Key Vault | Vault name, RBAC settings, network/diag integration | Vault resource ID, URI |
| Database | Name, SKU, identity, network rules | Server/db IDs, FQDN |
| Compute | Plan/cluster name, subnet ID, identity IDs | Host/cluster IDs, endpoints |
| Monitoring | Workspace ID, categories, action group | Workspace/alert resource IDs |
| Private Link | Target resource/subresource, subnet ID, DNS zone | PE ID, observed connection approval status |

**Never output DB admin passwords or storage account keys.** The Java runtime uses an appropriate identity and endpoint configuration.

### 38.4. Dependency Flow

```text
Network --> Private Link --> Storage/Key Vault private access
   |
   +------> Compute
               |
Identity ------+------> Data plane RBAC
               |
Storage ID ----+------> Blob endpoint/config
               |
Database ID ---+------> SQL connection target
               |
Monitoring ----+------> Diagnostics/alerts
```

Do not make every module `dependsOn` every other module. With Azure Private Endpoints, dependencies on the target resource and subnet are clear, yet **DNS readiness and RBAC propagation** still require checks after the ARM deployment completes.

### 38.5. Rollout Roadmap

1. Platform team publishes `storage:1.2.0` and `network:1.0.0` from test-validated source.
2. Orders app pins those versions in its root template.
3. `dev.bicepparam` specifies RG, SKU, region, and naming; CI runs build/validate/`what-if`.
4. Deploy dev and run synthetic Blob/SQL/service tests.
5. Deploy staging with production-like networking and identity; verify private DNS and role assignments.
6. Run production `what-if`, scope, security, and cost reviews.
7. Deploy prod with approvals and canary validation.
8. Run smoke tests across Orders API, Receipt Worker, and Key Vault/SQL access.
9. Monitor Azure Monitor and costs; log deployment versions, outputs, and incident links.

### 38.6. A Failure Scenario

Module version 1.3 switches the network default from public to private-only (matching security policy), but App Service lacks outbound VNet Integration. The ARM deployment succeeds, yet the Java app fails to connect to Blob and Key Vault.

Analysis:

- **Module contract change:** the new network assumption is a breaking behavioral change.
- **Dependency outside ARM:** application runtime network routing configuration.
- **Testing gap:** staging lacked canary or negative network tests.
- **Action:** inspect PE/DNS/VNet Integration, preserve least privilege, repair private connectivity or perform an approved rollback, and add integration tests.

This demonstrates why **reusable modules require versioned behavioral contracts**, not just public parameter schemas.

### 38.7. Acceptance Criteria

```text
MODULES
  source revision/version pinned
  build and contract validation pass
  no plaintext credentials in params/outputs

AZURE
  correct subscription/RG/scope
  security baseline and Azure Policy pass
  resource IDs/tags/SKU/network as expected

RUNTIME
  Java app uses intended managed identity
  data-plane permissions work
  private routes/DNS where required
  synthetic transaction succeeds

OPERATIONS
  metrics/logs/alerts usable
  what-if reviewed
  cost/owner/rollback documented
```

## 39. Hands-On Exercises

### Exercise A — Writing Your First Storage Module

**Prompt:** Create `modules/storage.bicep` from Section 6 with parameters `storageAccountName`, `location`, `skuName`, and `tags`, and outputs `storageAccountId` and `blobEndpoint`. Invoke it from `main.bicep`.

**Requirements:**

1. Account name has length constraints and is tested with a valid name.
2. HTTPS-only and minimum TLS 1.2 enabled.
3. Anonymous Blob public access disabled.
4. No account keys in outputs.
5. `az bicep build` succeeds.

**Solution guide:** Use `resource Microsoft.Storage/storageAccounts`, `@allowed` SKUs, and resource ID/endpoint outputs; verify live security properties after deployment. If your organization mandates private-only access, add a separate networking module and test against policy.

### Exercise B — Separating Environments with `.bicepparam`

A team copied `main-dev.bicep` to `main-prod.bicep`. The two files differ only in names, SKUs, and tags.

**Task:** Refactor into a single `main.bicep` paired with `dev.bicepparam` and `prod.bicepparam`, enforcing safe naming and scope boundaries.

**Solution guide:** Share the module/composition, let callers pass environment/SKU/names, and enforce subscription/RG selection in CI via scoped identities and allowlists rather than trusting an `environment` string.

### Exercise C — Adding a VNet/Subnet Module

Create `modules/network.bicep` with inputs `vnetName`, `vnetCidr`, `appSubnetName`, and `appSubnetCidr`, and output `appSubnetId`.

**Task:** Explain parent vs. child resources and why manual `dependsOn` is unnecessary when the subnet sets `parent: vnet`.

**Solution guide:** Use `resource vnet` and `resource subnet ... { parent: vnet }`; verify CIDRs do not overlap.

### Exercise D — Wiring Dependencies Between Modules

An application requires the app subnet ID. Write a Bicep composition that calls the network module and passes `network.outputs.appSubnetId` to the compute module.

**Task:** Explain dependency inference; if the compute module were completely independent, should you still force `dependsOn` on the network module?

**Solution guide:** Referencing an output creates an implicit dependency. Never add `dependsOn` if compute has no real dependency on networking.

### Exercise E — Cross-Scope Deployment

From subscription scope, create `rg-orders-dev` and then invoke `storage.bicep` targeting that resource group.

**Task:** Write `targetScope='subscription'`, `resource appRg`, and `module storage {scope: appRg}`. State how to invoke `az deployment sub create` and what permissions are required.

**Solution guide:** Set the module `scope` to the created RG; the CLI requires a deployment `--location` and an identity with permissions at both subscription and target RG scopes.

### Exercise F — Conditional Module

A diagnostics module is enabled only in production. Write `module diagnostics ... = if (enableDiagnostics)`.

**Task:** Explain how to avoid reading outputs when the module is skipped and why **turning off the flag does not guarantee deletion of existing diagnostic settings**.

**Solution guide:** Use guarded output expressions and define an explicit resource lifecycle/deletion policy; verify with `what-if` and review.

### Exercise G — Module Loops and Quotas

An application needs three Storage Accounts: uploads, processing, and archive. Write an array input and module loop to deploy all three.

**Task:** Ensure unique nested deployment names, explain `@batchSize(1)`, and describe the risk of reordering the input array.

**Solution guide:** Prefer stable logical keys over array indices, review quotas and costs, and use `@batchSize(1)` only when sequential execution is required.

### Exercise H — Publishing a Module to ACR

A platform team maintains a private Azure Container Registry for Bicep modules.

**Task:** Design the workflow: build → integration test → approval → publish version `1.2.0` → consumer restore. Identify differing publish vs. restore permissions and how to prevent tag overwrites.

**Solution guide:** Use `az bicep publish` to `br:...:1.2.0`, pin URIs in consumers, grant distinct ACR repository write/read roles per permission mode, and enforce immutable release conventions.

### Exercise I — Module Alias Build Failure

A consumer references `br/platform:storage:1.2.0`, but CI fails to resolve the alias.

**Task:** Diagnose potential causes and design a fix.

**Solution guide:** Missing or mislocated `bicepconfig.json`, wrong registry/modulePath under `moduleAliases.br.platform`, or missing artifact; also check ACR network and RBAC.

### Exercise J — Comparing AVM vs. Custom Modules

A team wants to standardize Storage Accounts. Compare:

- Consuming a published AVM module version directly.
- Writing an internal resource module.
- Wrapping AVM to enforce security defaults.

**Task:** Choose an approach and define contract, versioning, and upgrade tests.

**Solution guide:** Align with organizational policy and team capacity; AVM reduces boilerplate, yet still requires verifying networking, diagnostics, outputs, and version pinning.

### Exercise K — Secure Parameters and Key Vault

An engineer puts an SQL admin password inside `prod.bicepparam` and returns the connection string as an output.

**Task:** Identify the two security flaws and propose how to pass secure parameters properly or eliminate passwords with Entra managed identity where supported.

**Solution guide:** Use `@secure()`, pull from a protected secret store, never commit plaintext or echo outputs, and prefer identity/RBAC for the data plane.

### Exercise L — `what-if` on Stateful Resources

`what-if` reports changing `storageAccount.name` from `stordersprod01` to `stordersprod02` and adding a Private Endpoint.

**Task:** Assess the risk of replacement, data loss, old resource lifecycle, migration planning, cost, and approval gates.

**Solution guide:** Do not auto-deploy; inventory data, prepare backups and migration steps, obtain owner review, and run post-cutover connectivity tests.

### Exercise M — Azure Policy Denial

`az deployment group validate` passes, yet deployment fails with `RequestDisallowedByPolicy` because the module enables anonymous Blob public access.

**Task:** Explain why the module still compiled and how to remediate properly.

**Solution guide:** Azure Policy is an independent governance layer; update module defaults/parameters to comply and test in a non-prod subscription—never request Owner to bypass policy.

### Exercise N — Java Cannot Access Blob After Deployment

Bicep created the Storage Account, but the Java SDK using `DefaultAzureCredential` receives HTTP 403.

**Task:** Distinguish successful resource provisioning from data-plane authorization and networking; write a checklist covering principal, Storage Blob Data role, and firewall/DNS/Private Endpoint.

**Solution guide:** RBAC and networking are independent gates; test from the intended runtime identity rather than falling back to shared account keys.

### Exercise O — Backwards Compatibility

Module `storage:1.3.0` renames output `storageAccountId` to `id`, while multiple apps consume `1.2.0`.

**Task:** Classify the breaking change, propose a deprecation/migration plan, and outline CI consumer compilation tests.

**Solution guide:** Preserve legacy outputs across minor releases and add new aliases if needed; reserve breaking removals for major versions with migration docs.

### Exercise P — Reuse Across Owning Teams

The platform team owns the VNet, the product team owns App Service, and the security team owns Key Vault. Design modules, target scopes, `existing` references, and exchanged outputs.

**Solution guide:** Enforce clear ownership so apps cannot modify the shared VNet, exchange resource IDs across approved scopes, and separate deployment identities and reviews.

### Exercise Q — Drift and Rollback

An operator enables public network access in the Portal while Bicep source declares `Disabled`.

**Task:** Design drift detection using `what-if` + Azure Policy/Activity Log, handle the change through proper process, and roll back without causing an outage.

**Solution guide:** Verify business need, security impact, and owners first; remediate through an audited, approved change rather than blindly reapplying IaC.

### Exercise R — Estimating Module Upgrade Costs

A new storage module release enables ZRS, a Private Endpoint, and diagnostic logs.

**Task:** List potential new cost drivers and explain how to estimate and compare cost, availability, and security before production rollout.

**Solution guide:** Check Pricing Calculator/Cost Management across region, SKU, Log Analytics ingestion, and PE data processing, combined with `what-if` and canary rollout.

### Exercise S — Building a CI Release Gate

Design a workflow for a Java service deploying Bicep modules across these stages:

```text
PR -> build -> restore -> validate -> what-if -> review
   -> dev deploy -> runtime smoke -> staging test
   -> prod approval -> prod what-if -> deploy -> monitoring
```

**Task:** Identify which identity needs ACR read, who may publish modules, and who may deploy to production.

**Solution guide:** Separate publisher, consumer, and deployer identities, pin versions, use OIDC federation with scoped RBAC, and protect GitHub/Azure pipelines.

### Exercise T — Designing a Production-Ready Module Contract

Build a contract table for a `keyvault-private.bicep` module with:

- Params: vault name, location, identity, subnet ID, private DNS zone ID, tags.
- Outputs: vault resource ID, vault URI, private endpoint resource ID.
- RBAC/Policy: disallow public data-plane access as required.
- Tests: DNS resolves to private IP, Secrets User allowed, no-role denied, public network denied, no secrets logged.

**Task:** Identify which parts Bicep can declare and which require **post-deploy testing**.

**Solution guide:** ARM provisions the vault, PE, DNS zone group, and roles; **runtime DNS resolution, RBAC propagation, and Java `SecretClient` reads** must be verified outside the compiler.

## 40. Self-Check Questions

**1. What is Bicep?** A declarative language for authoring and deploying ARM templates for Azure resources.

**2. What is a Bicep module?** A file or module reference called from another Bicep template, encapsulating resources and a params/outputs contract.

**3. Is a module a Java application running in Azure?** No. It compiles and deploys through ARM, not inside a JVM.

**4. Why do modules reduce drift across teams?** They standardize defaults, contracts, and versions while centralizing change reviews.

**5. What should be extracted into a module?** Components with real reuse, clear lifecycle/ownership boundaries, or encapsulated policy/complexity.

**6. What does `targetScope` do?** Sets the default deployment scope of a Bicep file.

**7. How does a symbolic resource name differ from an actual Azure name?** The symbolic name is for internal template references; `name` is the live resource name in Azure.

**8. How does `param` differ from `var`?** `param` receives inputs from callers/deployments; `var` computes intermediate values inside the template.

**9. What is `output` used for?** Exposing contracted return values to callers or downstream modules.

**10. Should you output a Storage Account key?** No; avoid exposing secrets and use managed identity / data-plane RBAC wherever appropriate.

**11. What does `@allowed` provide?** Restricts a parameter to an approved value list, without replacing Azure Policy.

**12. Does `@secure()` make a plaintext secret in Git safe?** No. It does not encrypt source files or CI logs.

**13. What does `module storage './modules/storage.bicep'` mean?** Calls a local module by relative path with its parameters and deployment name.

**14. Is a module deployment name the same as a Storage Account name?** No. One is the ARM nested deployment name; the other is the actual Azure resource name.

**15. Why must a Storage Account name be globally unique?** Due to Azure Storage service naming rules across global DNS endpoints.

**16. Does `allowBlobPublicAccess=false` disable the public network endpoint?** No; it blocks anonymous blob access, not public network reachability itself.

**17. Should dev and prod copy-paste separate root templates?** Usually no; share the same Bicep composition with separate parameter files and scopes.

**18. Is `.bicepparam` safe for literal passwords?** No; it is a plain-text source file and must not contain plaintext secrets.

**19. When does Bicep infer a module dependency?** When a downstream module references an output, resource, or scope expression from another module.

**20. When should `dependsOn` be used?** Only when a real dependency cannot be inferred by Bicep from references or relationships.

**21. Does an `existing` resource create a new resource?** No; it references an already-existing resource for metadata or scoping.

**22. Can a resource-group-scoped module be called from a subscription-scoped root?** Yes, by setting `scope` to a valid RG and holding required permissions.

**23. Why does a subnet child resource use `parent: vnet`?** To express the parent-child relationship and dependency on the VNet.

**24. What does `if (flag)` do on a module?** Deploys the module only when the condition is true; conditional outputs must be guarded.

**25. Does turning off an `if` flag guarantee old module resources are deleted?** No; deletion depends on deployment/lifecycle mode and requires a dedicated strategy.

**26. What does `@batchSize(1)` do?** Constrains a module loop to deploy one instance sequentially at a time.

**27. Why shouldn't you blindly loop 1,000 resources?** It can exceed ARM/provider quotas, cost limits, and deployment throttling limits.

**28. How does a local module differ from an OCI registry module?** Local modules live in the same repository/revision; OCI modules are published and restored by version/ref from a registry.

**29. What is `br:...` used for?** Referencing an OCI Bicep module hosted in a registry such as ACR.

**30. Does a `bicepconfig.json` alias grant ACR permissions automatically?** No; it only shortens module URIs—the identity still needs registry read roles.

**31. Is a Bicep module in ACR a Docker image?** No, it is an OCI artifact packaging a Bicep module.

**32. Why pin module versions?** To ensure reproducible builds, controlled upgrade reviews, and avoid mutable dependency drift.

**33. What is AVM?** Azure Verified Modules—curated Bicep/Terraform modules following published standards that still require version and security review before use.

**34. Should you assume AVM automatically matches every internal policy?** No; review parameters, defaults, and features, and wrap them if needed.

**35. Is a Template Spec the same as Azure Policy?** No; it stores versioned templates rather than enforcing compliance.

**36. Is renaming a module output a breaking change?** Yes, it can break compilation for every caller referencing the old output name.

**37. Does `az bicep build` deploy Azure resources?** No; it compiles the template into ARM JSON.

**38. Is `az deployment group validate` enough to guarantee runtime success?** No; live provider limits, runtime networking, and IAM can still fail.

**39. What is `what-if` used for?** Previewing predicted resource changes prior to deployment, though not all runtime behavior is known upfront.

**40. Why must a `what-if` deleting a Key Vault or SQL database be blocked?** Because of severe data lifecycle, compliance, and customer-impact risks.

**41. Can Azure Policy block a Bicep deployment?** Yes; Bicep cannot bypass governance guardrails.

**42. Does CI having ARM Contributor guarantee permission to read Blobs?** No; data-plane RBAC is separate from control-plane roles.

**43. Does a module guarantee a Java app successfully connects to SQL/Blob?** No; runtime smoke and integration tests are required.

**44. What is drift?** When live Azure resources diverge from expected template or policy state.

**45. Why does a Git rollback not equal an Azure resource rollback?** Resource state must be intentionally redeployed or migrated, and some changes are irreversible.

**46. How do Deployment Stacks differ from modules?** Stacks manage resource lifecycle and deletion/detach behavior; modules structure template code.

**47. Should CI cleanup delete every RG prefixed with `test`?** No; verify owner/run IDs, resource IDs, and active job lifecycles first.

**48. Why shouldn't `what-if` findings be averaged into an automated "risk score"?** Different changes carry vastly different impacts requiring resource, data, security, and owner review.

**49. What must be checked before upgrading a module?** Version contract, `what-if`, security/cost impacts, staging deployment, runtime smoke tests, and rollback plan.

**50. What makes a module reusable-ready?** Typed, documented inputs/outputs, safe defaults, version pinning, tests, IAM/security alignment, lifecycle/ownership clarity, and change governance.

## 41. Production Readiness Checklist

### 41.1. Module Contract

- [ ] Module purpose, owner, scope, and non-goals are clearly documented.
- [ ] Inputs have appropriate types, descriptions, required/default settings, and constraints.
- [ ] SKU, tier, and network defaults align with Azure Policy and business needs.
- [ ] No hardcoded account secrets, tenant-specific credentials, or arbitrary production-only resource IDs.
- [ ] Outputs have stable names/types and never leak secrets, passwords, or keys.
- [ ] Resource/module symbolic names are clearly distinguished from actual Azure resource names.
- [ ] Azure API versions are intentionally chosen and tested rather than blindly using unsupported latest.
- [ ] Module boundaries align with ownership and lifecycle without creating mega-modules.
- [ ] Migration and deprecation contracts exist for breaking changes.
- [ ] Versioning, changelog, release owner, and usage examples are maintained.

### 41.2. Composition, Dependencies, and Scopes

- [ ] Root Bicep composition invokes only necessary modules without copying implementation details.
- [ ] Module input-output references establish clear automatic dependencies wherever possible.
- [ ] No redundant `dependsOn` entries that unnecessarily serialize deployments.
- [ ] Cross-scope modules specify matching `targetScope` and `scope`.
- [ ] Shared resources are referenced with `existing` according to ownership boundaries.
- [ ] Child resources are not managed concurrently by multiple uncoordinated writers.
- [ ] Conditional modules and their outputs are properly guarded.
- [ ] Looped module names are unique and stable, with iteration counts bounded for quotas and cost.
- [ ] Subnet CIDRs, VNets, peering, identities, and DNS resources have coordinated plans.
- [ ] Application readiness is verified after ARM deployment completes.

### 41.3. Registry and Supply Chain

- [ ] Local module paths are accurate and build cleanly on the CI filesystem.
- [ ] External module versions are explicitly pinned.
- [ ] ACR/private registry URIs, aliases, and network connectivity are verified.
- [ ] Publishers and consumers hold matching repository write/read permissions per permission mode.
- [ ] Artifact versions cannot be arbitrarily overwritten; build provenance is audited.
- [ ] AVM/Template Specs use verified releases and reviewed contracts.
- [ ] Consumer compilation and integration tests run before upgrading shared modules.
- [ ] No floating `"latest"` module references in production.
- [ ] Contingency plans exist for registry outages, caching, and artifact retention.
- [ ] Bicep/CLI toolchain versions are pinned and tested for compatibility.

### 41.4. Parameter Files and Azure Environments

- [ ] `.bicepparam` files specify the right `using` root and valid environment values.
- [ ] Dev/staging/prod target strictly allowlisted subscriptions and resource groups.
- [ ] CI identities are scoped independently rather than trusting `param environment` alone.
- [ ] Global uniqueness and naming constraints are checked prior to deployment.
- [ ] Regions, SKUs, and service quotas are verified, with `owner` and `costCenter` tags applied.
- [ ] Production never mixes secrets or data with dev/staging.
- [ ] No plaintext secrets are committed to parameter, source, or config files.
- [ ] Private networking, diagnostics, and retention policies match each environment.
- [ ] Rollback and DR plans for stateful resources are approved.

### 41.5. Validation and Change Safety

- [ ] Bicep build/linter passes cleanly or all diagnostics are triaged.
- [ ] ARM validate runs against the right deployment scope.
- [ ] `what-if` against the **real target subscription/RG** is reviewed before deploy.
- [ ] Destructive changes, public exposure, or role/network edits have explicit approval.
- [ ] Modules are tested in a non-prod RG with synthetic fixtures.
- [ ] Idempotent redeployments and updates to existing resources are tested.
- [ ] Azure Policy, RBAC, quota, and regional errors are caught and clearly reported.
- [ ] Post-deployment Java/Blob/Key Vault/SQL runtime smoke tests pass.
- [ ] Runbooks exist for failed or partial ARM deployments without assuming automatic rollback.
- [ ] Resource drift, Activity Logs, and Policy compliance are monitored.

### 41.6. Operations, Security, and Cost

- [ ] Deployment identities and workload managed identities are separated.
- [ ] Data-plane RBAC roles are least-privilege and live-tested.
- [ ] Private Endpoints, DNS, and network paths are verified against production requirements.
- [ ] Secrets are never written to ARM deployment history or CI logs via outputs.
- [ ] Monitoring and diagnostic settings target valid categories and governed workspaces.
- [ ] Cost impacts of module upgrades are projected with Pricing Calculator and tracked in actual billing.
- [ ] Budgets and cost alerts cover resources, log ingestion, and Private Endpoint charges.
- [ ] IaC changes are audited with policy-as-code, separating author and deployer privileges.
- [ ] Automated cleanup never deletes shared or production resources.
- [ ] Approvals, smoke verification, and rollback/forward-fix owners are established post-deploy.
- [ ] Deployment artifacts, source versions, outputs, and incidents remain traceable.

## 42. Conclusion

**Bicep modules and reusable infrastructure components** transform scattered Azure declarations into **reusable contracts**: typed and constrained inputs, clear outputs, ARM/Bicep-inferred dependencies, accurate scopes, and encapsulated implementations. With **local modules**, teams iterate quickly inside a repository; with **OCI registries on ACR, Azure Verified Modules, and Template Specs**, platform teams distribute tested, versioned building blocks across applications and environments.

Good module design goes beyond shorter code. It requires **safe defaults, parameterization, least-privilege Azure RBAC, network and data-plane security, diagnostics and tags, versioning, and lifecycle policies**. Before rolling out, compile/lint, validate, inspect **`what-if`**, test on non-production Azure resources, and run **Java application smoke tests** after deployment. Above all, remember that **module updates do not guarantee safe resource replacement, rollbacks are not automatic, and outputs must never expose secrets**.

By pairing well-scoped modules with **CI/CD approvals, Azure Policy, monitoring, and cost governance**, teams can reuse infrastructure consistently while preserving strict control across subscriptions, resource groups, applications, and environments—laying the groundwork for auditable, resilient Azure architectures as systems scale.
