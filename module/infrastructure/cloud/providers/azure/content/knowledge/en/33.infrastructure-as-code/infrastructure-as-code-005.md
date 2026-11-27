# Managing Parameters Across Environments and Protecting Sensitive Values

An application typically shares a single infrastructure design while requiring different configurations across **development (dev)**, **testing/staging (test)**, and **production (prod)**. For example, dev may use Azure Storage with LRS redundancy to save cost, whereas production requires higher redundancy, stricter monitoring, and tighter access controls. At the same time, each environment needs separate connection details and credentials. Embedding all these values directly into a template makes maintenance difficult and risks exposing secrets.

In the **Infrastructure as Code (IaC)** chapter of the Microsoft Azure learning track, we establish how to **separate declarative infrastructure code from per-environment configuration parameters**, control parameter changes, and protect sensitive values from storage through deployment. The focus is on **Bicep, `.bicepparam` files, ARM deployments, Azure Key Vault, Microsoft Entra ID**, and integrating these pieces into CI/CD pipelines. The same principles apply when using ARM JSON or other IaC tools.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why one template should serve multiple environments and identify which parameters should vary by environment.
2. Write Bicep templates with parameters, defaults, constraints, and separate **`.bicepparam`** files for dev, test, and prod.
3. Classify standard configuration, sensitive data, and secret credentials; decide which belong in Git.
4. Use **`@secure()`**, **Azure Key Vault**, and secret-referencing mechanisms during ARM/Bicep deployments.
5. Design identities, access controls, approvals, and pre-deployment checks to prevent leaks or environment misconfiguration.
6. Diagnose parameter errors and plan change management, secret rotation, and rollbacks.

## 2. What Are Parameters and Why Separate Them?

A **template** describes the resources, dependencies, and infrastructure configuration to provision. A **parameter** is an input that tailors the template for a given deployment: workload name, Azure region, SKU, environment, tags, scale size, Key Vault name, or credentials required by a resource.

Suppose a team operates the **orders-api** service on Azure. All three environments need a Storage Account and application resources, yet differ in cost, monitoring, redundancy, scale, and access requirements. Creating three copies of Bicep and editing them manually quickly accumulates configuration drift and unintended errors.

A common layout:

~~~text
main.bicep                 Shared infrastructure template
env/
  dev.bicepparam           Non-sensitive values for dev
  test.bicepparam          Non-sensitive values for test
  prod.bicepparam          Non-sensitive values for prod
~~~

This is an illustrative structure in documentation; these files have not been created in an actual project.

| Value Category | Examples | Where Should It Live? |
| --- | --- | --- |
| **Shared inputs** | Workload code, resource types, tagging rules | Template or sensible defaults |
| **Per-environment config** | `environment`, `location`, SKU, instance count, resource group name, cost-center tag | `.bicepparam` file in Git when non-sensitive |
| **Reference identifiers** | Key Vault name, managed identity name, token-free endpoint URIs | Parameter file or controlled configuration store |
| **Sensitive values** | Internal topology details, restricted resource identifiers | Stored only in systems with policy-compliant access control |
| **Secrets** | Passwords, API keys, private keys, tokens, connection strings containing credentials | Azure Key Vault or managed secret store; passed only over secure channels |

A **secret** is a value someone can use to authenticate or gain unauthorized access. A standard **Key Vault URI** only identifies where to look up a reference and does not by itself grant permission to read secrets; however, such metadata may still require protection under organizational policy.

Parameters enable template reuse, but **you should not parameterize everything**. Mandatory security rules—such as disabling public blob access—can be hardcoded in the template or enforced by Azure Policy so deployers cannot accidentally relax them.

## 3. Per-Environment Parameter Matrix

Before writing Bicep, define a **configuration contract** specifying values and their owners:

| Parameter | Dev | Test | Prod | Principle |
| --- | --- | --- | --- | --- |
| **environment** | dev | test | prod | Constrained via allowed values |
| **resourceGroup** | rg-orders-dev | rg-orders-test | rg-orders-prod | Isolate lifecycle and permissions |
| **location** | Chosen dev region | Appropriate test region | Driven by data residency and DR requirements | Verify service supports the region |
| **storageSku** | Standard_LRS | Standard_LRS | Standard_ZRS if supported by region | Validate cost and regional availability |
| **loggingRetention** | Short retention | Sufficient for testing | Meets operational/compliance requirements | Never below audit minimums |
| **workloadCode** | order | order | order | Stable for resource traceability |
| **keyVaultName** | Dev vault | Test vault | Prod vault | Isolate secrets and access per environment |
| **adminPassword** | Dev-specific secret | Test-specific secret | Prod-specific secret | Never store values directly in Git |

**Never copy secrets from dev to production.** Isolating secrets and identities per environment limits blast radius if an account or pipeline is compromised. In larger systems, production may live in a dedicated subscription with separate pipeline service connections and approvers.

Specifically distinguish:

- **Environment selectors:** `dev`, `test`, `prod`; these are configuration data.
- **Operational settings:** SKU, instance count, retention; these are configuration governed by cost and availability policies.
- **Secret values:** passwords, access tokens; these must be delivered strictly to components that require them.

## 4. Designing a Bicep Template with Parameter Constraints

### 4.1. Example `main.bicep`

The following template creates a Storage Account to illustrate applying one Bicep file across multiple environments:

~~~bicep
targetScope = 'resourceGroup'

@description('Allowed deployment environment.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environment string

@description('Workload code: 3-5 lowercase alphanumeric characters.')
@minLength(3)
@maxLength(5)
param workloadCode string = 'order'

@description('Azure deployment region.')
param location string = resourceGroup().location

@description('Allowed Storage redundancy SKU.')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
])
param storageSku string = 'Standard_LRS'

@description('Additional tags for resource and cost management.')
param resourceTags object = {}

var storageName = toLower(format(
  'st{0}{1}{2}',
  workloadCode,
  environment,
  uniqueString(resourceGroup().id)
))

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: storageSku
  }
  kind: 'StorageV2'
  tags: union(resourceTags, {
    environment: environment
    workload: workloadCode
  })
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageAccountId string = storage.id
output storageAccountName string = storage.name
~~~

**Design analysis:**

- **`@allowed`** constrains environment and SKU values; invalid inputs are caught during validation or deployment.
- **`@minLength`** and **`@maxLength`** enforce workload code length. Because Storage Accounts allow only lowercase letters and digits, pipelines or code reviews must still validate the allowed character set; length decorators alone do not enforce character rules.
- **`uniqueString(resourceGroup().id)`** creates a deterministic name suffix when redeploying to the same resource group. This function **does not generate a secret** and does not guarantee uniqueness against other people's resources; Storage Account names must still be globally unique.
- **`location`** defaults to the resource group's region, but can be overridden when architecture requires it.
- **`union`** applies system tags **`environment/workload`** last so callers cannot accidentally overwrite them via duplicate keys in `resourceTags`.
- **`allowBlobPublicAccess: false`** is a security safeguard fixed inside the template.
- The two **`output`** values expose only the resource ID and name, never credentials.

Note that **`Standard_ZRS`** is not available in every combination of region and storage type. Examples should adjust SKU or region to match actual subscription support—another reason pre-deployment checks are essential.

### 4.2. File `env/dev.bicepparam`

~~~bicep
using '../main.bicep'

param environment = 'dev'
param workloadCode = 'order'
param location = 'southeastasia'
param storageSku = 'Standard_LRS'

param resourceTags = {
  owner: 'platform-team'
  costCenter: 'dev-training'
  lifecycle: 'short'
}
~~~

### 4.3. File `env/test.bicepparam`

~~~bicep
using '../main.bicep'

param environment = 'test'
param workloadCode = 'order'
param location = 'southeastasia'
param storageSku = 'Standard_LRS'

param resourceTags = {
  owner: 'qa-team'
  costCenter: 'orders-qa'
  lifecycle: 'temporary'
}
~~~

### 4.4. File `env/prod.bicepparam`

~~~bicep
using '../main.bicep'

param environment = 'prod'
param workloadCode = 'order'
param location = 'southeastasia'
param storageSku = 'Standard_ZRS'

param resourceTags = {
  owner: 'operations'
  costCenter: 'orders-production'
  lifecycle: 'long'
}
~~~

Values in these three examples are illustrative and do not confirm access permissions or ZRS availability in the chosen region. The **`using '../main.bicep'`** statement tells Bicep which template the parameter file targets; the path is relative to the **`.bicepparam`** file.

When your Bicep/CLI version supports **`.bicepparam`**, deployers can pass that file directly and the tool resolves the template from the **`using`** directive. There is no need to duplicate **`main.bicep`** into three copies or put secrets in these files.

## 5. Running `what-if` and Deploying to the Right Environment

Assume the resource group already exists, the operator is signed in to Azure CLI, and the right subscription is selected. A safe dev workflow:

~~~bash
az account show --query "{subscription:id,tenant:tenantId}" -o json

az deployment group what-if \
  --resource-group rg-orders-dev \
  --parameters ./env/dev.bicepparam

az deployment group create \
  --resource-group rg-orders-dev \
  --parameters ./env/dev.bicepparam
~~~

The **`what-if`** command previews changes against live infrastructure before applying them. Inspect resource names, SKUs, regions, tags, any destructive operations, and environment impact. `what-if` is helpful yet limited when evaluating complex expressions or runtime properties; do not treat it as proof that every change is safe.

For test/prod, select the corresponding parameter file and resource group. For example:

~~~bash
az deployment group what-if \
  --resource-group rg-orders-prod \
  --parameters ./env/prod.bicepparam
~~~

**Never auto-deploy production solely because `what-if` succeeded.** Production should use a dedicated service connection or scoped identity, explicit approval gates, and matching policies. These commands assume Azure CLI/Bicep support **`.bicepparam`**, the Azure resource group exists, and the identity holds required permissions.

A critical mistake is selecting **`prod.bicepparam`** while targeting resource group **`rg-orders-dev`**. Without extra checks, the template would provision prod-labeled resources inside the dev group. Therefore, pipelines should cross-verify **`environment ↔ subscription ↔ resource group ↔ parameter file ↔ service connection`** before running deploy.

## 6. Distinguishing Standard Parameters, Secrets, and Runtime Configuration

Not all configuration values are resolved at the same stage.

| Stage | Example | Appropriate Mechanism |
| --- | --- | --- |
| **IaC compile/preparation** | `environment`, `workloadCode`, SKU | Bicep parameters and `.bicepparam` |
| **Resource provisioning** | Admin password required by a resource provider | **`@secure()`** parameters and Azure Key Vault references |
| **Application runtime** | API key used on outbound service calls | Managed identity reading Key Vault or service-native runtime secret references |
| **Pipeline orchestration** | Environment name, resource group, service connection name | Non-sensitive pipeline parameters/variables with access controls |

**Eliminate secrets whenever possible.** For example, an Azure application using a **managed identity** to access Storage, Key Vault, or other Azure services may not need any long-lived passwords stored at all. When credentials are unavoidable, keep them in a dedicated secret store.

Values such as **client secrets**, signing keys, passwords, or connection strings with embedded access keys must never appear directly in Git, committed **`.bicepparam`** files, YAML comments, template outputs, or log files.

## 7. Bicep `@secure()`: Necessary but Not Sufficient

### 7.1. Declaring a Secure Parameter

In Bicep, attach the **`@secure()`** decorator to **`string`** or **`object`** parameters carrying secrets:

~~~bicep
@description('SQL admin password supplied at deployment time.')
@secure()
param sqlAdminPassword string
~~~

ARM flags the corresponding input as a secure string, preventing plaintext values from being recorded in deployment parameter history. However, **`@secure()` is not a secret vault**: the deployer must still fetch the value from a secure source and pass it over a protected channel.

**What `@secure()` cannot do on its own:**

- It cannot erase a password already committed to Git history.
- It cannot protect a value if a script explicitly prints it to stdout, enables debug/tracing, or passes it to logging tools.
- It cannot stop a template author from wiring the secret into an output, tag, metadata field, or readable resource property.
- It does not replace RBAC, encryption, secret rotation workflows, or least privilege.

Rule of thumb: **never output a secure parameter**, never concatenate it into resource names or diagnostic logs, and use it only in the specific property that configures the service. A secret passed to a resource provider may also be subject to that service's own storage and visibility behavior; verify how each resource type handles it.

### 7.2. Example `database.bicep` Module Accepting a Secure Parameter

To illustrate passing a secret, the module below declares an Azure SQL logical server:

~~~bicep
targetScope = 'resourceGroup'

param sqlServerName string
param sqlAdminUser string
param location string = resourceGroup().location

@secure()
param sqlAdminPassword string

resource sqlServer 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlServerName
  location: location
  properties: {
    administratorLogin: sqlAdminUser
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    publicNetworkAccess: 'Disabled'
  }
}

output sqlServerId string = sqlServer.id
~~~

This example focuses strictly on consuming a secure parameter. A working SQL system also requires designing databases, private endpoint/DNS connectivity, policy-compliant firewall rules, backups, and monitoring. Provisioning Azure SQL incurs charges; logical server names must be globally unique, and passwords must satisfy Azure SQL complexity rules. Never run this snippet merely to test secrets in a production subscription without proper review.

## 8. Retrieving Secrets from Azure Key Vault at Deployment Time

Azure Key Vault provides centralized storage and lifecycle management for secrets, keys, and certificates. In this lesson we focus on **secrets**. A secret has a name, a value, and optional multiple **versions**, enabling rotation or pinning a specific version for a release.

### 8.1. Option A — Key Vault Reference in ARM JSON Parameters

An ARM **JSON** parameters file can use a **`reference`** block instead of embedding a password. For example, when deploying the **`database.bicep`** module above:

~~~json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "sqlServerName": {
      "value": "sql-orders-prod-example"
    },
    "sqlAdminUser": {
      "value": "sqladminprod"
    },
    "sqlAdminPassword": {
      "reference": {
        "keyVault": {
          "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-secrets-prod/providers/Microsoft.KeyVault/vaults/kv-orders-prod"
        },
        "secretName": "sql-admin-password"
      }
    }
  }
}
~~~

Strings inside angle brackets are **placeholders** that must be replaced with real values. No secret value appears in the JSON file. All other keys must match parameter names in the target Bicep file. Deployment commands:

~~~bash
az deployment group what-if \
  --resource-group rg-orders-prod \
  --template-file ./database.bicep \
  --parameters @./env/prod.secure.parameters.json

az deployment group create \
  --resource-group rg-orders-prod \
  --template-file ./database.bicep \
  --parameters @./env/prod.secure.parameters.json
~~~

This is the **ARM JSON parameters mechanism**, distinct from the **`.bicepparam`** syntax in Section 4. Do not mix both formats inside one file. In real projects, pick one consistent convention based on your toolchain version and team standards.

**Prerequisites for ARM Key Vault references to work:**

1. The secret **`sql-admin-password`** already exists in the vault.
2. The vault has **`enabledForTemplateDeployment`** enabled for ARM template deployments.
3. The deploying identity holds **`Microsoft.KeyVault/vaults/deploy/action`** on the vault scope; verify your tenant/subscription permission model.
4. The identity still has sufficient permissions on the target resource group to deploy Azure SQL.
5. Tenant, vault, network, and Azure Policy rules do not block the deployment operation.

Example of updating vault configuration by an authorized administrator:

~~~bash
az keyvault update \
  --name kv-orders-prod \
  --enabled-for-template-deployment true
~~~

This command alters a vault security property, so it must be reviewed and restricted under organizational authorization rules. Never grant broad admin rights just to fix a reference error. Enabling template deployment does not by itself let every principal read all secrets.

**Never declare literal secret values inside JSON parameter files.** If a file containing a password is ever pushed to Git, treat that value as compromised: revoke and rotate the credential and handle repository history per your incident-response policy rather than merely deleting the line in a new commit.

### 8.2. Option B — `getSecret()` When Passing Parameters to a Bicep Module

Bicep supports calling **`getSecret()`** on an **`existing`** Key Vault resource to pass a secret into a **module's secure parameter**:

~~~bicep
targetScope = 'resourceGroup'

param sqlServerName string
param sqlAdminUser string
param vaultName string
param vaultResourceGroup string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
  scope: resourceGroup(vaultResourceGroup)
}

module database './database.bicep' = {
  name: 'deploy-orders-sql'
  params: {
    sqlServerName: sqlServerName
    sqlAdminUser: sqlAdminUser
    sqlAdminPassword: vault.getSecret('sql-admin-password')
  }
}
~~~

In this example, **`database.bicep`** is the module declaring **`@secure() param sqlAdminPassword string`** from Section 7.2. **`vaultName`** and **`vaultResourceGroup`** are non-secret identifiers. The deployer must still satisfy all permission and Key Vault configuration prerequisites from Option A.

Important limitation: **`getSecret()` is only for assigning values to a module's secure parameter**. Never use it to populate an output, convert it to a plain string, or read it inside resource-naming expressions. When secrets are needed at **application runtime**, prefer managed identities and runtime retrieval rather than using deployments to copy passwords into outputs.

### 8.3. Fixed Secret Version vs. Latest?

| Choice | Advantage | Risk / Trade-off |
| --- | --- | --- |
| **Reference a specific version** | More reproducible deployments, easier auditing | Rotation requires updating the pinned reference |
| **Reference the latest version** | Conveniently picks up newly rotated secrets on redeploy | Same template can inject different secrets at different times |

Policy depends on your rotation workflow. When no secret version is specified in an ARM reference, deployment resolution fetches the current active version from Key Vault. Never assume a running application picks up a rotated secret immediately: refresh behavior depends on the specific Azure service and how the application loads secrets.

## 9. Runtime Secrets: Identity-Based Access Instead of Template Injection

If an application only needs an API key or connection string while serving requests, a sound design is assigning a **managed identity** to the application and granting that identity read access to only the required secret in Key Vault.

~~~mermaid
flowchart LR
  A["Git: main.bicep + env/prod.bicepparam"] --> B["CI/CD: validate and approval"]
  B --> C["ARM/Bicep deployment"]
  C --> D["Azure workload with managed identity"]
  V["Azure Key Vault: production secret"] -. "Read secret via authorized identity" .-> D
  C --> E["Resource configuration without secret values"]
~~~

For example, App Service apps can use **Key Vault references** in app settings, while Azure Container Apps offers native Key Vault secret references. Verify current service capabilities, identity configuration, RBAC/access policies, and refresh behavior for each service. Never place password-bearing connection strings into Bicep outputs or resource tags.

For Azure Storage and other APIs supporting Microsoft Entra ID, favor **RBAC via managed identity** over account keys. This eliminates long-lived shared secrets and enables centralized policy-driven access revocation.

## 10. Separating Scope and Access Permissions by Environment

### 10.1. One Template, Multiple Permission Boundaries

~~~mermaid
flowchart TB
  G["Repository containing IaC and non-sensitive parameters"] --> CI["Build: lint, validate, what-if"]
  CI --> DG["Deploy DEV"]
  CI --> TG["Deploy TEST"]
  CI --> PG["Prod approval + deploy PROD"]
  DG --> DEV["Dev subscription/RG + Dev Key Vault"]
  TG --> TEST["Test subscription/RG + Test Key Vault"]
  PG --> PROD["Prod subscription/RG + Prod Key Vault"]
~~~

Separating subscriptions is not mandatory in every organization, yet it is valuable for strict isolation, cost caps, and independent governance policies. At a minimum, separate resource groups, identities, and secrets within approved boundaries.

| Role | Appropriate Permissions | Should Not Be Granted by Default |
| --- | --- | --- |
| Developer | Read/edit Bicep, use dev environments as permitted | Read access to production secrets |
| CI validation | Read code, run lint/validate/`what-if` with minimal rights | Subscription-wide Owner |
| CI/CD dev deploy | Deploy into dev RG | Permission to deploy to production RG |
| Production deploy identity | Deploy within production scope and reference approved vaults | Unrestricted admin across all vaults |
| Runtime managed identity | Read specific workload secrets, access resources via RBAC | Create/delete secrets or manage vaults |
| Approver | Review check outputs and approve deployments | Passwords shared with the pipeline |

**Key Vault data plane** and **management plane** have distinct permission models. With RBAC, select the exact role and scope required. ARM's **`Microsoft.KeyVault/vaults/deploy/action`** permission applies specifically to template deployments—never equate it with an application's direct runtime secret read permissions via the Key Vault API.

### 10.2. Service Connections and CI/CD Authentication

When Azure Pipelines or GitHub Actions deploys IaC:

- Prefer **workload identity federation / OIDC** where supported to avoid long-lived client secrets.
- Use a dedicated **service connection** or identity for production, scoped to specific subscriptions/resource groups.
- Enforce branch protection, protected environments, required approvals, and PR checks prior to deploy.
- Never allow pipelines triggered by untrusted pull requests to access production credentials.
- Record who approved, which commit, which parameter file, which subscription/RG, and which deployment ID ran.

**Pipeline parameters** and **pipeline variables** are orchestration inputs—they do not automatically act as a secret store. In particular, Azure Pipelines **runtime parameters** must never be used to accept passwords, as values can appear in run history and pipeline UI. When a job truly needs a secret, use protected secret variables or Key Vault integration—yet for ARM deployments, prefer **Key Vault references** so plaintext secrets never pass through CLI arguments.

## 11. Sample Pipeline: Validating and Deploying Environment Parameters

For illustration, below is an Azure Pipelines job for **dev** deploying the template from Section 4. Production should use a separately protected job and dedicated service connection.

~~~yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

stages:
  - stage: ValidateDev
    displayName: 'Validate DEV infrastructure changes'
    jobs:
      - job: WhatIf
        steps:
          - task: AzureCLI@2
            inputs:
              azureSubscription: 'sc-azure-orders-dev'
              scriptType: 'bash'
              scriptLocation: 'inlineScript'
              inlineScript: |
                az account show --query id -o tsv
                az deployment group what-if \
                  --resource-group rg-orders-dev \
                  --parameters ./env/dev.bicepparam

  - stage: DeployDev
    displayName: 'Deploy DEV infrastructure'
    dependsOn: ValidateDev
    condition: succeeded()
    jobs:
      - deployment: Apply
        environment: 'iac-dev'
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self
                - task: AzureCLI@2
                  inputs:
                    azureSubscription: 'sc-azure-orders-dev'
                    scriptType: 'bash'
                    scriptLocation: 'inlineScript'
                    inlineScript: |
                      az deployment group create \
                        --resource-group rg-orders-dev \
                        --parameters ./env/dev.bicepparam
~~~

**Assumptions of this example:** the Azure DevOps project has a service connection named **`sc-azure-orders-dev`**, an environment **`iac-dev`**, a resource group **`rg-orders-dev`**, valid Bicep files, and an agent with compatible Azure CLI/Bicep versions. The deployment job includes **`checkout: self`** so IaC files are present at runtime. For production, configure approvals and checks on the Azure DevOps environment and lock down service connection permissions—merely naming an environment in YAML **does not create an approval policy**.

`what-if` output should be archived as controlled review evidence, but inspect logs before sharing: outputs can contain sensitive metadata, and debug flags easily leak values. IaC builds must never echo secret variables or enable shell tracing (`set -x`) when handling credentials.

**Pre-deployment environment cross-checking** can be implemented as a gating step:

1. Verify the active tenant ID and subscription ID of the service connection.
2. Verify the resource group belongs to the expected subscription and environment.
3. Verify **`env/dev.bicepparam`** specifies **`environment = dev`** and references the intended template.
4. Review `what-if` diffs, Azure Policy compliance, and cost thresholds.
5. Run `create` with that exact parameter file only after all checks pass.

For production, organizations may require two-person approval or custom policy checks, calibrated to actual operational risk.

## 12. Change Control and Parameter Versioning

Even a small parameter change like **`storageSku = Standard_ZRS`** alters cost, regional constraints, or data handling. Parameter files must be governed like source code.

Recommended workflow:

1. Open a **Pull Request** for changes to Bicep or `.bicepparam`.
2. **Review the environment matrix**, checking whether prod values make sense and comply with policy.
3. Run **validate and `what-if`** in the target subscription/RG, noting any availability-impacting changes.
4. **Obtain deployment approval** per target environment governance.
5. **Archive deployment records**: commit SHA, tool versions, parameter file, deployment ID, and check outputs.
6. **Monitor post-deployment** and keep prior approved parameter values ready for rollback where supported by the service and resource type.

When modifying the **template interface** (such as renaming a parameter), update every **`.bicepparam`** file and consuming pipeline. To avoid breaking consumers that upgrade asynchronously, consider controlled defaults or phased transitions.

**Never hardcode a default password** in Bicep just to avoid missing-parameter errors. When a secret is required, declare a `@secure()` parameter with no default so deployments fail fast unless supplied from a valid secret source.

## 13. Secret Rotation and Rollback Strategies

Standard parameters and secrets follow different lifecycles:

| Change | Action | Risks to Check |
| --- | --- | --- |
| Change region/SKU | Review parameters, `what-if`, apply | Resource may not support the region or may require replacement |
| Change Key Vault name | Update references, grant identity permissions | Old identities lose secret access |
| Rotate API key | Issue new version, update consumers, revoke old version | Services with stale caches or unrefreshed secrets |
| Rotate SQL admin password | Coordinate server update and credential-using apps | Connection outage if updates are out of sync |
| Rollback Bicep | Restore approved commit/parameters, run `what-if` | Data and destructive changes are not automatically undone |

A safe rotation pattern for runtime secrets is typically **issue new credential → switch consumers to new credential → verify operation → revoke old credential**. Depending on the system, a dual-credential overlap window may be needed. For single-password systems, schedule a maintenance window and recovery plan.

**Rolling back IaC does not mean rolling back secrets.** If a secret was exposed, never revert to the compromised credential just to match an older Git commit. On secret exposure, revoke the leaked credential and fix the leak vector—never reuse compromised material.

## 14. Common Pitfalls and How to Handle Them

| Issue | Symptom | Remediation |
| --- | --- | --- |
| **Missing required parameter** | Deployment reports parameter not supplied | Check Bicep declaration, `.bicepparam`/JSON keys, and defaults |
| **Wrong type or outside `@allowed`** | Validate reports type mismatch or invalid value | Fix types, update environment file, keep constraints intact |
| **Wrong resource group/subscription** | Resources appear in the wrong place or permission denied | Verify account, service connection, target RG, and param file pre-deploy |
| **Invalid Storage name** | Naming or conflict error | Check lowercase alphanumeric characters, length 3–24, and global uniqueness |
| **SKU unsupported in region** | Resource provider rejects creation | Check regional availability, choose a supported SKU/region |
| **Cannot retrieve Key Vault secret** | ARM template reports missing permission or secret not found | Verify vault ID, secret name/version, template deployment setting, and `deploy/action` |
| **Secret appears in logs** | Logs or build artifacts contain passwords/tokens | Revoke/rotate immediately, restrict logs, remove plaintext passing, audit access |
| **Secret not updated at runtime** | Application keeps using old key | Check refresh/caching, reload/restart, and managed identity permissions |
| **`what-if` differs from reality** | Deployment changes more than predicted | Inspect runtime conditions, provider behavior, Azure Policy, and drift |
| **Overly broad permissions** | CI unnecessarily holds Owner or Key Vault Admin | Separate identities and narrow Azure RBAC / Key Vault permissions |
| **Drift from manual Portal edits** | Template overwrites manual changes unexpectedly | Record drift and bring legitimate changes back into IaC |

When troubleshooting secret errors, trace in order: **vault/secret identifier → retrieving identity → permissions → ARM/runtime mechanism → safe logging**. Never "fix" it by pasting passwords into YAML or granting subscription-wide Owner.

## 15. Hands-On Practice: One Bicep Template for Dev and Prod

**Scenario:** The `orders-api` team wants to share a single Storage template across dev and prod. Production has stricter approval policies. A separate SQL module requires a password from Key Vault.

### Exercise A — Non-Sensitive Parameters

1. Create **`main.bicep`** based on Section 4 in an authorized practice repository.
2. Create **`env/dev.bicepparam`** and **`env/prod.bicepparam`**, keeping `workloadCode` identical while varying `environment`, tags, and SKU.
3. Create environment-specific resource groups and run **`what-if`** against dev.
4. Inspect the Storage Account name derived from the naming rule and confirm tag **`environment = dev`**.
5. Once authorized, run `what-if` for prod and compare the SKU and projected resource changes.

**Completion criteria:** Zero edits to **`main.bicep`** between environments, no hardcoded subscriptions in the shared template, and zero secrets in parameter files.

### Exercise B — Referencing Secrets

1. Review the **`database.bicep`** module in Section 7 and confirm **`sqlAdminPassword`** is marked **`@secure()`**.
2. Create a test Key Vault and secret through an authorized workflow, strictly isolated from real production.
3. Prepare an ARM JSON parameters file following Section 8 with a **`reference`** to the vault/secret; never write a literal password.
4. Verify ARM template deployment permissions and run validate/`what-if` against a test resource group.
5. Inspect deployment status without enabling secret-exposing debug logs; verify the password never appears in source, parameter files, outputs, or shared logs.
6. Clean up test resources per policy and save an execution record without copying secret values into the report.

**Completion criteria:** Template accepts the secure parameter properly, the Key Vault reference works with least-privilege permissions, and the secret never enters Git or deployment outputs.

### Exercise C — Environment Mismatch Scenario

Suppose an operator picks **`prod.bicepparam`** while the pipeline uses the dev service connection. Write a pre-`create` validation check that catches the mismatch by cross-checking subscription, resource group, and `environment` value. Then describe who may approve production deployments and what audit evidence must be recorded.

**Completion criteria:** The pipeline blocks mismatched environment combinations without printing any secrets to explain the failure.

## 16. Self-Check Knowledge Questions

**Q1.** Can **`Standard_ZRS`** be stored in Git?  
**Answer:** Yes, because it is standard non-sensitive configuration; still review cost, regional support, and availability requirements.

**Q2.** Should an Azure SQL password be stored in **`prod.bicepparam`** just because the repository is private?  
**Answer:** No. Private repositories still risk exposure via Git history, forks, runners, and user permissions. Use Key Vault and secure parameters.

**Q3.** Does the **`@secure()`** decorator make a secret safe to place in an output?  
**Answer:** No. It marks sensitive inputs in ARM deployments, but a template author can still leak data through outputs, logs, or resource properties.

**Q4.** When should you use **`.bicepparam`** vs. an **ARM JSON reference**?  
**Answer:** `.bicepparam` is convenient for typed inputs paired with Bicep; ARM JSON parameters support the **`reference`** structure for ARM to pull Key Vault secrets at deployment time. Pick the right tool and avoid mixing syntaxes.

**Q5.** Why prefer managed identity for application runtime secrets?  
**Answer:** Applications receive scoped permissions directly, eliminating static credentials in pipelines or templates and enabling centralized revocation.

**Q6.** Why can't `what-if` replace production approval?  
**Answer:** `what-if` only predicts changes within certain limits; it does not evaluate full business impact, data safety, maintenance windows, or organizational approval authority.

## 17. Pre-Deployment Checklist for Real IaC

- [ ] One shared template serves multiple environments, with typed, documented, constrained parameters.
- [ ] Each environment has its own non-sensitive parameter file reviewed in Git.
- [ ] Pipelines cross-verify subscription, resource group, environment, and parameter file.
- [ ] Secrets never appear in Git, outputs, resource names, tags, or logs.
- [ ] Secure parameters use **`@secure()`** when secrets are required at deployment time.
- [ ] Key Vault references or **`getSecret()`** are used only in valid contexts with exact least-privilege permissions.
- [ ] Workloads use managed identities to access resources and runtime secrets wherever feasible.
- [ ] Deployment rights for dev/test/prod are separated; production enforces approvals and Azure Policy.
- [ ] `what-if`, peer review, cost checks, and configuration validation run prior to apply.
- [ ] Deployment records, secret rotation plans, and impact-assessed rollback procedures are in place.

Strong parameter management lets environments **differ in controlled values** while staying **identical in architectural and security principles**. On Microsoft Azure, combining Bicep, `.bicepparam`, Azure Key Vault, Microsoft Entra ID, and approval-gated CI/CD makes infrastructure configuration reusable, traceable, and far less likely to expose sensitive values.
