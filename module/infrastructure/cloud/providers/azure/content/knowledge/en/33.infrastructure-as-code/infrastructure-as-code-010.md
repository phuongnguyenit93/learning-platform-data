# Storing Terraform State Remotely in Azure Storage

A team is using Terraform to provision an Azure Virtual Network, Azure App Service, Azure SQL, Azure Key Vault, and permissions for a Spring Boot application. Developer A runs **`terraform apply`** on a laptop; **`terraform.tfstate`** is created locally on A's machine. The next day, Developer B runs the same code without that state file. Terraform has no record of previously managed resources, leading to inaccurate plans, overlapping management, conflicting changes, and poor auditability. If two pipelines run `apply` concurrently against the same environment, the risk grows even higher.

**Terraform state** stores the mapping between Terraform configuration and managed infrastructure objects. On Azure, the **`azurerm`** backend stores state as a **blob in Azure Storage**, enabling multiple engineers and CI/CD pipelines to share a single centralized source of state. This backend supports **state locking via Azure Blob leases**, preventing concurrent state writes when clients respect locking. However, storing state in Storage is only secure when backed by **data-plane Azure RBAC, Microsoft Entra ID, network controls, versioning/recovery, monitoring, and lock-handling procedures**.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_AZURE** module. Across the Microsoft Azure learning path—from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data—governing Terraform remote state is foundational to deploying consistent Azure architectures, protecting resources, auditing changes, and controlling costs.

> **Core principle:** Terraform state is **not** ordinary source code. It can contain resource names, resource IDs, connection strings, generated passwords, secret-derived attributes, and provider-returned data. **Never commit state to Git, never print raw state in CI logs, and never enable public blob access.** Even when Terraform marks an output as **`sensitive`**, its value can still reside inside state stored in the backend.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Explain Terraform state, resource addresses, provider identities, and how they map to live Azure resources.
2. Compare a local backend with the **`azurerm` remote backend** across collaboration, concurrency, security, and recovery.
3. Describe **Azure Storage account, blob service, container, blob key, Blob lease, and versioning**.
4. Design a backend bootstrapping pattern **before** running `terraform init`.
5. Create a dedicated `StorageV2` account/container for state via Azure CLI in an approved lab environment.
6. Use Microsoft Entra ID and **Storage Blob Data Contributor** to access state blobs under least privilege.
7. Author **`terraform { backend "azurerm" { ... } }`** and initialize it with `terraform init`.
8. Distinguish **backend authentication** from **`azurerm` provider authentication**, and understand the limits of access keys, SAS, and OIDC.
9. Inspect `plan`, `apply`, `state list`, `state show`, and `state pull` **without leaking sensitive data**.
10. Understand **locking via Blob leases**, how to handle lock conflicts/timeouts, and when `force-unlock` may be considered.
11. Isolate state by application, environment, and workstream; never treat Terraform workspaces as a security boundary.
12. Migrate local state to remote state using **`terraform init -migrate-state`** and plan rollbacks.
13. Design backups with blob versioning/soft delete, restore permissions, and controlled disaster recovery workflows.
14. Configure firewalls, Private Endpoints, private DNS, and network paths for self-hosted agents.
15. Integrate CI/CD using OIDC/workload identity federation and harden PR jobs.
16. Monitor storage operations, lock anomalies, state drift, retention, quotas, and FinOps.
17. Run negative tests, troubleshoot issues, and establish a production readiness checklist.

## 2. End-to-End Scenario: Orders API and Three Environments

Suppose a team operates a Java **Orders API** on Azure App Service with infrastructure managed by Terraform:

- **Network**: virtual network, subnets, routes, and private endpoints.
- **Compute**: Azure App Service Plan, Web App, or container services.
- **Data**: Azure SQL and supporting storage.
- **Security**: managed identities, Azure RBAC, and Key Vault.
- **Observability**: Azure Monitor, Application Insights, and diagnostic settings.

The three environments—**dev**, **staging**, and **prod**—have distinct lifecycles. The team wants:

- One clear source of state per environment for Terraform.
- CI/CD using scoped identities instead of copied storage keys.
- Concurrent `apply` jobs on the same state never silently overwriting each other.
- Every `plan` clearly knowing which state key and subscription it targets.
- Production state accessible only from approved actors and agents.
- Recoverable snapshots if a blob is corrupted or accidentally deleted.
- State preserved even if an application resource group is deleted.
- Visibility into costs for state storage, networking, logs, and CI agent workloads.

Example logical layout:

~~~text
Azure subscription: platform-shared
  Resource group: rg-iac-state-prod
    Storage account: stiacstateprod001
      Blob container: tfstate
        orders/prod/network.tfstate
        orders/prod/app.tfstate
        orders/prod/data.tfstate

Azure subscription: application-dev
  Resource group: rg-orders-dev
    VNet, App Service, SQL, Key Vault...

Azure subscription: application-prod
  Resource group: rg-orders-prod
    VNet, App Service, SQL, Key Vault...
~~~

**Names are illustrative only.** Storage account names must be globally unique across Azure and contain only lowercase letters and digits—so **st iac state prod** with spaces is invalid. For production, pick names with unique suffixes following your naming convention.

## 3. What Is Terraform State and Why Must It Be Governed?

A resource in configuration:

~~~hcl
resource "azurerm_resource_group" "orders" {
  name     = "rg-orders-dev"
  location = "southeastasia"
}
~~~

Terraform records the link between a **resource address** like **`azurerm_resource_group.orders`** and the live Azure resource (such as its ARM resource ID), plus attributes needed for refresh and planning. State also holds dependency metadata for Terraform/providers and may capture sensitive values.

### 3.1. Three Artifacts Not to Confuse

| Artifact | Contains | Can Replace |
|---|---|---|
| **Terraform configuration (.tf)** | Desired-state declarations | Cannot serve as a record of currently managed live resources |
| **Terraform state (.tfstate)** | Resource address mappings and tracked live metadata | Cannot replace configuration code or Azure itself |
| **Live Azure resources** | Actual deployed Azure infrastructure | Does not carry Terraform resource addresses |

Terraform uses configuration, state, and provider APIs together to build plans. Without state, importing, destroying, or modifying resources becomes hazardous even though the Azure resources still exist.

### 3.2. What Can State Contain?

- Resource IDs, DNS names, subnet IDs, and private endpoint IDs.
- Managed identity principal IDs and role assignment metadata.
- Provider-returned values, which can include connection strings or secrets depending on the resource/provider.
- Random passwords from **`random_password`** resources.
- Outputs, including outputs marked **`sensitive`**.
- Configuration parameters and attributes used to compute diffs.

**`sensitive = true`** masks values in certain CLI outputs, **without encrypting or removing them from state**. State storage must therefore be protected as a store that can hold secrets.

### 3.3. State Is Not an Immutable Transaction Log

When `terraform apply` succeeds, state is updated. If `apply` fails partway through, state and Azure resources can diverge. You need versioning/recovery and a reconciliation workflow—never treat state as an atomic transaction backup of all Azure resources.

## 4. Local Backend vs. Remote Backend

| Criterion | Local State | Azure Storage Remote State |
|---|---|---|
| Location | Developer workstation / CI workspace | Designated Azure Blob |
| Collaboration | Difficult to share safely | Multiple actors share state under access controls |
| Concurrency locking | Local filesystem behavior; fails across machines | **Blob lease locking** |
| Recovery | Relies on local backups | Blob versioning / soft delete / backup policy when enabled |
| Access control | Local OS filesystem permissions | Data-plane Azure RBAC + network rules |
| Availability | Tied to one machine | Tied to Azure Storage, networking, and identity |
| Auditing | Local/CI logs only | Azure Storage logs + Activity Logs when enabled |
| Cost | Local disk | Storage operations, capacity, networking, monitoring |
| Risks | Lost laptop, leaked file, concurrent applies | State leak from overly broad RBAC, network issues, locks, deletion |

A remote backend is essential for production, yet **does not by itself enforce** who may edit Terraform code, who may run `apply`, who manages Azure resources, or whether the application is secure.

### 4.1. Why Never Store `tfstate` in Git?

- State can contain sensitive values.
- Git history is hard to purge thoroughly once leaked.
- Merge conflicts cannot guarantee consistency with live Azure state.
- Git lacks lease locking for Terraform operations.
- Git clones and forks replicate the file across many machines.
- Git code review is built for source code, not internal state-update protocols.

Do not "solve" this by **gitignoring** remote state locally and then pushing a plaintext backup copy to another Git repository.

## 5. `azurerm` Backend Architecture

~~~mermaid
flowchart LR
    DEV["Terraform CLI<br/>developer / CI job"] --> AUTH["Microsoft Entra ID<br/>Azure CLI / OIDC"]
    DEV --> BACK["Terraform azurerm backend"]
    AUTH --> BACK
    BACK --> SA["Azure Storage Account<br/>Blob service"]
    SA --> CON["Container: tfstate"]
    CON --> BLOB["Blob key:<br/>orders/prod/app.tfstate"]
    BACK -. "Blob lease for lock" .-> BLOB
    DEV --> PROV["Terraform azurerm provider"]
    PROV --> ARM["Azure Resource Manager<br/>VNet/App Service/SQL..."]
    MON["Azure Monitor / Logs"] -. "operations, alerts" .-> SA
~~~

**Separating the two paths:**

1. **Backend data plane**: reads/writes state blobs and acquires/releases leases using Azure Storage authorization and networking.
2. **Provider control/data plane**: creates/updates/deletes Azure resources such as App Service, SQL, RBAC, and networks; its permissions may differ completely from the backend.

`terraform init` connects to the **backend** early—even before provider blocks execute. Consequently, **authenticating to the `azurerm` provider does not prove** the backend holds `Storage Blob Data Contributor` permissions.

### 5.1. Storage Components

| Component | Example | Purpose |
|---|---|---|
| Backend resource group | `rg-iac-state-prod` | Organizes state infrastructure lifecycle |
| Storage account | `stiacstateprod001` | Governance, network, replication, and encryption boundary |
| Blob service | Default blob endpoint | Object storage host |
| Container | `tfstate` | Namespace for state blobs |
| Blob key | `orders/prod/app.tfstate` | Object name representing one Terraform state |
| Blob lease | Lease on state blob | Lock preventing concurrent writers when enforced by backend |
| RBAC | `Storage Blob Data Contributor` | Permits blob data and lease operations at scope |
| Versioning | Blob version history | Restores prior snapshots after corruption/accidental writes per policy |
| Soft delete | Retains deleted blobs/versions for retention window | Aids recovery |
| Private endpoint | Private Blob access path | Eliminates public exposure when required |

### 5.2. Containers Are Not Git Folders

A blob key like **`orders/prod/app.tfstate`** contains **`/`** and resembles folders; in object storage, it is a **flat key name**. Azure Portal/CLI tools render virtual directories visually—never assume a "folder" creates an RBAC or security boundary unless specific hierarchical ACL features apply.

## 6. Designing the Backend Before Provisioning Resources

### 6.1. Lifecycle Isolation

**The Storage account holding state must never be destructible by a Terraform stack whose state lives inside it.** If an application's Terraform stack manages and destroys its own state storage, you lose state management, backups, locks, and recovery paths.

Safe pattern:

- Bootstrap the backend via platform IaC, controlled CLI steps, or a **dedicated bootstrap Terraform stack with its own separate state**.
- Govern state storage lifecycle, RBAC, and logs via the platform team or guarded workflows.
- Orders API Terraform stacks merely **reference the pre-existing backend**.
- Protect state storage resources against accidental deletion with policies, locks, and break-glass runbooks.

### 6.2. Separating Dev / Staging / Prod

| Design | Pros | Risks |
|---|---|---|
| One account + container, multiple blob keys | Simple management, fewer resources | Large blast radius if data-plane roles are scoped too broadly |
| One account, multiple containers | Tighter container-scoped RBAC | Network, encryption, and account settings still shared |
| Dedicated Storage account per environment | Clearer RBAC and network boundaries | More resources and operational overhead |
| Dedicated subscription for prod state | Strong isolation and governance | Cross-subscription operations and permission management |
| One blob shared by dev and prod | Deceptively simple | **Never do this:** state collisions and cross-environment destruction |

**A distinct blob key alone is not a security boundary.** If a principal holds `Storage Blob Data Contributor` across the entire account, it can read/write every key in that account. When strong isolation is required, separate containers, accounts, or subscriptions, scope roles narrowly, and use distinct identities.

### 6.3. Splitting Stacks by Blast Radius

Example:

~~~text
orders/dev/network.tfstate
orders/dev/app.tfstate
orders/dev/data.tfstate

orders/staging/network.tfstate
orders/staging/app.tfstate
orders/staging/data.tfstate

orders/prod/network.tfstate
orders/prod/app.tfstate
orders/prod/data.tfstate
~~~

A dedicated network stack keeps App Service changes from holding permissions to modify shared networking, at the cost of cross-stack output dependencies. Design cross-stack references and output security carefully without over-fragmenting the state graph.

### 6.4. Naming Conventions

- Valid, globally unique Storage account name containing no secrets.
- Clear container name such as **`tfstate`**.
- Blob keys prefixed by application, environment, and workstream.
- Never reuse **`orders/prod/app.tfstate`** for staging by flipping a pipeline variable.
- Document backend coordinates in ops docs—never account keys.
- Never embed PII, passwords, or tokens inside blob keys.
- Apply resource tags: `owner`, `service`, `environment`, retention class, and cost center per convention.

## 7. Azure CLI Lab: Bootstrapping the Storage Account and Container

The steps below are **a guide for learners to run in an approved Azure lab**, not commands executed while authoring this lesson. Azure Storage, Log Analytics, and network resources can incur costs. Never run these verbatim against a production subscription or shared storage.

### 7.1. Prerequisites

- Approved lab subscription and resource group creation rights.
- Azure CLI signed in with an authorized identity.
- Permission to create a Storage Account; **Azure role-assignment permission** held by an admin or delegated principal.
- Compatible Terraform CLI supporting the **`azurerm` backend**.
- A fresh, valid, globally unique Storage account name.
- Network connectivity to Azure ARM and Azure Blob endpoints.
- Lab goal: **no public container access** and Entra data-plane authentication preferred.
- Cleanup and retention plan post-exercise.

### 7.2. Sign In and Verify Subscription

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --query \
  "{name:name,id:id,tenantId:tenantId}" \
  --output json
~~~

**Never** guess your active subscription from Azure CLI defaults when you access multiple tenants or subscriptions. Specify the approved subscription ID and double-check before creating resources.

### 7.3. Create a Dedicated Resource Group for the Backend

~~~bash
RG="rg-tfstate-lab"
REGION="southeastasia"

az group create \
  --name "$RG" \
  --location "$REGION"
~~~

The state backend RG should be managed by the platform team. In production, never let an Orders API Terraform stack delete this group during **`terraform destroy`**.

### 7.4. Create a `StorageV2` Account

~~~bash
# MUST replace with an unused Azure Storage name,
# 3-24 characters, lowercase letters and digits only.
SA="<globally-unique-storage-account>"

az storage account create \
  --name "$SA" \
  --resource-group "$RG" \
  --location "$REGION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --allow-shared-key-access false

az storage account show \
  --name "$SA" \
  --resource-group "$RG" \
  --query "{id:id,name:name,publicAccess:allowBlobPublicAccess,sharedKeyAllowed:allowSharedKeyAccess}" \
  --output json
~~~

**`Standard_LRS`** is a lab choice, not a blanket recommendation for production backends. Choose LRS, ZRS, GRS, or GZRS based on availability, disaster recovery requirements, and regional/tier support.

**`--allow-shared-key-access false`** eliminates reliance on account keys and requires Entra authentication for Blob data, provided your Terraform `azurerm` backend version and auth flow support it. Some legacy tools may be incompatible—never toggle it blindly on live production storage.

### 7.5. Check Identity and Assign the Data-Plane Role

Fetch the Storage account's Azure resource ID and the lab user's object ID:

~~~bash
SA_ID=$(az storage account show \
  --name "$SA" \
  --resource-group "$RG" \
  --query id --output tsv)

USER_OID=$(az ad signed-in-user show \
  --query id --output tsv)

echo "Backend storage account resource ID obtained"
~~~

An authorized role-assignment administrator (**not necessarily the developer**) can assign in the lab:

~~~bash
az role assignment create \
  --assignee-object-id "$USER_OID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "$SA_ID"
~~~

**Storage Blob Data Contributor** is the data-plane role typically required for the backend to read, write, and lease state blobs. ARM-scope **Reader** or **Contributor** does not grant Blob data-plane access.

Role assignments can take time to propagate. Never "fix" a 403 error by re-enabling shared keys or granting subscription-wide Owner before checking identity, scope, and network paths.

### 7.6. Create a Private Container via Entra Login

~~~bash
CONTAINER="tfstate"

az storage container create \
  --name "$CONTAINER" \
  --account-name "$SA" \
  --auth-mode login \
  --public-access off

az storage container show \
  --name "$CONTAINER" \
  --account-name "$SA" \
  --auth-mode login \
  --query "{name:name,publicAccess:properties.publicAccess}" \
  --output json
~~~

If your CLI version differs on any flag, check **`az storage container create --help`**; do not omit `--auth-mode login` and accidentally fall back to shared keys. A private container does not restrict an identity holding an account-scoped role to just one blob—the role assignment scope still governs data access.

### 7.7. Enable Blob Recovery with Versioning and Soft Delete

For a lab backend lacking an existing policy:

~~~bash
az storage account blob-service-properties update \
  --account-name "$SA" \
  --resource-group "$RG" \
  --enable-versioning true \
  --enable-delete-retention true \
  --delete-retention-days 14
~~~

Versioning preserves **previous versions of the state blob**. Soft delete preserves deleted blobs during the retention window. Neither replaces off-site backups, incident response, or proper state governance.

**Never enable immutability, WORM, or legal hold directly on an active state blob that Terraform writes and leases** without thorough evaluation: an immutable object breaks state writes and locking. If compliance requires immutable archives, write separate archive copies and test restoration.

### 7.8. Verify the Container / Data Plane

~~~bash
az storage blob list \
  --account-name "$SA" \
  --container-name "$CONTAINER" \
  --auth-mode login \
  --query "[].name" \
  --output table
~~~

Freshly bootstrapped, the container will have no blobs yet. **Never upload a fake empty JSON file as a placeholder state**: the backend will fail to parse it as valid Terraform state.

### 7.9. When Should Storage Public Network Access Stay Closed?

In short-lived labs, public network access may be permitted with Entra auth and firewall rules. Sensitive production environments typically require **Private Endpoints, private DNS, controlled agent egress, and disabled public network access**. Design network paths **before** locking down the backend, or `terraform init` from laptops or Microsoft-hosted agents will lose connectivity.

## 8. Writing the Terraform `azurerm` Backend

### 8.1. Backend Block in Terraform

In the IaC project, **`backend.tf`**:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  backend "azurerm" {
    resource_group_name  = "rg-tfstate-lab"
    storage_account_name = "stexampleiaclab001"
    container_name       = "tfstate"
    key                  = "orders/dev/app.tfstate"

    use_azuread_auth = true
    use_cli          = true
  }
}
~~~

**The storage account name is an example only—do not assume it exists.** Substitute your newly created account and verify your running **Terraform CLI version** supports these backend authentication settings.

- **`resource_group_name`**: resource group holding the backend Storage account.
- **`storage_account_name`**: Storage account name.
- **`container_name`**: Blob container storing state.
- **`key`**: blob object key representing **one state file**.
- **`use_azuread_auth`**: instructs the backend to use Microsoft Entra ID for blob data-plane auth.
- **`use_cli`**: enables Azure CLI authentication as supported by the backend version.

### 8.2. The Terraform Provider Is Configured Separately

A **`providers.tf`** file:

~~~hcl
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = "<application-subscription-id>"
}
~~~

With AzureRM provider 4.x, supply the target subscription ID explicitly or via environment variables. The provider requires permissions to manage resource groups, App Services, or role assignments—those permissions **are not** the backend's `Storage Blob Data Contributor` role.

**Ideal permission separation:**

~~~text
Terraform Backend Identity:
    Read / write / lease one authorized state container

Terraform Provider Identity:
    Manage approved Azure resources
    on approved subscription/resource group
~~~

If a pipeline uses a single identity for both, it must hold the union of both permission sets. When separating jobs or identities, ensure `init` and `plan`/`apply` receive the right identity at each step.

### 8.3. Backend Blocks Do Not Accept Terraform Variables

Never write:

~~~hcl
terraform {
  backend "azurerm" {
    # INVALID: backend init runs before variable evaluation.
    key = var.state_key
  }
}
~~~

Backend initialization occurs during **`terraform init`**, before variables, locals, or providers are evaluated. Never use **`var`**, **`local`**, or interpolations in the `backend` block. Use **partial backend configuration** or CI-generated non-secret config files instead.

### 8.4. Partial Backend Configuration

File **`backend.tf`**:

~~~hcl
terraform {
  backend "azurerm" {}
}
~~~

File **`backend.dev.hcl`**:

~~~hcl
resource_group_name  = "rg-tfstate-lab"
storage_account_name = "stexampleiaclab001"
container_name       = "tfstate"
key                  = "orders/dev/app.tfstate"
use_azuread_auth     = true
use_cli              = true
~~~

Initialize:

~~~bash
terraform init -backend-config=backend.dev.hcl
terraform validate
terraform plan
~~~

A corresponding production environment uses **`backend.prod.hcl`** with a separate storage account/container/key and separate identity/networking. However, **switching backend files** in an already-initialized working directory requires deliberate `-reconfigure` or `-migrate-state` handling—never run `init` casually and assume Terraform switched to the right state.

**Security note:** backend configs and flags passed to **`terraform init -backend-config`** can be cached inside **`.terraform/`** and plan artifacts. Put only **non-secret coordinates** into backend HCL files—never client secrets, SAS tokens, or access keys. Replace all placeholders before running.

### 8.5. A Small Sample State Stack

In **`main.tf`** of a dedicated lab project, you might declare:

~~~hcl
resource "azurerm_resource_group" "orders_demo" {
  name     = "rg-orders-demo"
  location = "southeastasia"
  tags = {
    application = "orders"
    environment = "lab"
  }
}
~~~

Only run **`terraform apply`** in a lab subscription where you have resource creation rights. This is an illustrative snippet; **no resources were created while writing this lesson**.

### 8.6. What Does `terraform init` Do?

A typical **`terraform init`** run:

1. Reads the backend configuration.
2. Validates backend coordinates and authentication settings.
3. Initializes access to the storage container/blob.
4. Reads/verifies existing remote state if present.
5. Downloads provider plugins and modules matching the lockfile/config.
6. Updates working-directory metadata under **`.terraform/`**.
7. Prompts if backend configuration changed or requires migration.

**A successful `terraform init` does not prove** the user holds permissions to create Azure resources in the provider subscription—only that initialization steps succeeded.

## 9. Terraform CLI: Inspecting and Controlling Remote State

### 9.1. Commands to Know

| Command | Purpose | Risk |
|---|---|---|
| **`terraform init`** | Connects backend, plugins, and modules | Auth or backend mismatch |
| **`terraform fmt -check`** | Verifies HCL formatting | Does not deploy resources |
| **`terraform validate`** | Checks HCL syntax and provider schemas | Does not verify Azure RBAC |
| **`terraform plan`** | Computes diff from state and live APIs | Output/plan files can be sensitive |
| **`terraform apply`** | Modifies resources and updates state | Modifies live infrastructure |
| **`terraform state list`** | Lists managed resource addresses | Metadata can be sensitive |
| **`terraform state show`** | Displays attributes of one resource | **Can print sensitive values** |
| **`terraform state pull`** | Downloads raw state JSON | **Highly sensitive** |
| **`terraform state mv/rm`** | Modifies mappings in state | Can break resource management |
| **`terraform force-unlock`** | Clears a state lock by lock ID | Risk of concurrent writes |
| **`terraform workspace list`** | Lists logical workspaces | Provides no security isolation |

### 9.2. Recommended Lab Command Sequence

~~~bash
terraform version
terraform fmt -check -recursive
terraform init -backend-config=backend.dev.hcl
terraform validate

# Plan reads resources and proposes changes;
# verify target, subscription, and backend key before running.
terraform plan
~~~

**Do not run `terraform apply` automatically** when merely studying remote state. `plan` calls Azure APIs and can read sensitive configuration; protect CI logs accordingly. When saving a binary plan via **`terraform plan -out=plan.bin`**, treat `plan.bin` as a sensitive artifact.

### 9.3. When Does the State Blob Appear After `init`?

Terraform creates or updates the state blob when state changes or a state write is needed; **`terraform init`** on a fresh backend does not necessarily create an empty blob immediately if no state exists yet. Never manually upload a placeholder JSON file in Terraform's place.

Once state is written, the blob name matches the configured **`key`**, such as **`orders/dev/app.tfstate`**. In the Azure Portal, keys containing `/` render as virtual folders.

### 9.4. Inspecting Blob Metadata Without Downloading State Values

~~~bash
az storage blob list \
  --account-name "$SA" \
  --container-name "tfstate" \
  --auth-mode login \
  --query "[].{name:name,etag:properties.etag,lastModified:properties.lastModified}" \
  --output table
~~~

Listing names and ETags avoids printing state JSON, though **resource names and metadata** can still be sensitive. This command requires matching data-plane read permissions.

### 9.5. Never Print Raw State in a Terminal

Avoid:

~~~bash
# Never run against production without approved incident authorization.
terraform state pull
terraform show -json plan.bin
terraform output -json
~~~

These commands can expose sensitive state or outputs. If backups or forensics are needed, write directly to encrypted, access-restricted files rather than stdout or CI logs. **`sensitive` outputs** do not make raw state JSON harmless.

### 9.6. Safe Apply Workflow

A controlled process:

1. Verify backend coordinates, environment, and subscription.
2. Confirm identity, Azure data-plane/backend permissions, and provider permissions.
3. Run `fmt` and `validate`.
4. Generate `plan` and inspect the diff.
5. Obtain authorized human/automated approval for `apply`.
6. Ensure no other `apply` is running against the same state key.
7. Run `apply` with locking enabled and an appropriate lock timeout.
8. Monitor run logs, state updates, and live Azure resources.
9. If `apply` fails mid-run, never delete state—reconcile state against live drift.

## 10. State Locking via Azure Blob Leases

### 10.1. What Problem Do Locks Solve?

Suppose CI job A and job B both target **`orders/prod/app.tfstate`**:

~~~text
A reads state version N
B reads state version N
A creates resource X and updates state N+1
B also applies based on stale state N
→ Risk of duplicated/overwritten/conflicting operations
~~~

The **`azurerm`** backend uses **Blob leases** to lock state during operations requiring a lock. While one job holds the lease, a second job **waits or fails with a lock error** rather than silently overwriting state.

### 10.2. Locking Flow

~~~mermaid
sequenceDiagram
    participant A as Terraform Job A
    participant B as Terraform Job B
    participant ST as Azure Blob state
    A->>ST: Acquire blob lease
    ST-->>A: Lease acquired
    B->>ST: Acquire lease
    ST-->>B: Locked / wait or fail
    A->>ST: Read, plan/apply and write state
    A->>ST: Release lease
    B->>ST: Acquire lease after release
    ST-->>B: Lease acquired
~~~

This diagram models locking behavior; lease renewal and duration details are handled internally by the backend. A Blob lease **is not a distributed transaction over Azure resources**: `apply` can create an Azure resource and then fail to write state, requiring reconciliation.

### 10.3. Lock Timeout

An `apply` command can pass:

~~~bash
terraform apply -lock-timeout=5m
~~~

**`-lock-timeout`** instructs Terraform to wait up to the specified duration for a lock before failing; it does not guarantee acquiring the lock if the holder never releases it. Choose timeouts based on typical apply duration, queue depth, concurrency, and CI timeouts.

### 10.4. Scenarios Requiring Investigation

- Two concurrent `apply` runs targeting the same key.
- Job A killed mid-`apply`.
- Network drop while holding a lock.
- Azure Storage throttling or service timeout.
- Terraform client state or backend config changes.
- Another tool holding a lease on the state blob.

When encountering **`Error acquiring the state lock`**, inspect active runs and lock metadata first. Never jump straight to `force-unlock`.

### 10.5. Why Never Use `-lock=false`?

~~~bash
# Anti-pattern; never run against shared/prod state:
terraform apply -lock=false
~~~

Disabling locking on shared state invites concurrent writes and state-to-Azure corruption. Only highly isolated, expert-reviewed recovery scenarios might ever discuss this flag—never use it as a routine workaround for lock errors.

### 10.6. `force-unlock` Is a Break-Glass Operation

Terraform supports:

~~~bash
# Syntax illustration ONLY; requires approval and verified LOCK_ID.
terraform force-unlock "<verified-lock-id>"
~~~

Before running it:

1. Confirm the **exact backend key** and environment.
2. Verify all related Azure Pipelines / GitHub Actions / Jenkins jobs have stopped.
3. Confirm nobody is running `apply` from a laptop.
4. Inspect lock metadata, holder, creation timestamp, and audit logs.
5. Notify the owning team.
6. Back up state securely per policy if corruption is suspected.
7. Obtain an incident ticket and approval.
8. Unlock only once the lock is confirmed stale; test with a safe `plan`.
9. Audit state and live Azure resources afterward.

**Force-unlocking an active lock lets two writers run simultaneously and corrupt state.** Never run **`az storage blob lease break`** as a knee-jerk reaction; it is a low-level storage operation that can violate backend assumptions.

## 11. Microsoft Entra ID and Storage Blob Data-Plane Permissions

### 11.1. Resource Management Permissions Differ from Blob Data Permissions

| Permission | Meaning | Enough for State Read/Write? |
|---|---|---|
| Azure Reader on RG | Read resource metadata | No |
| Azure Contributor on RG | Manage Azure resources | No direct Blob data-plane permission by default |
| **Storage Blob Data Reader** | Read blob data | Insufficient to write/lease state |
| **Storage Blob Data Contributor** | Read/write/delete/lease blobs per role | Usually appropriate for the backend |
| Storage Blob Data Owner | Broader data-plane rights | Usually unnecessary |
| Owner / User Access Administrator | Can assign roles at scope | Does not grant data-plane access unless assigned |

**Note:** Principals with certain Storage account management rights can list account keys when Shared Key is enabled, indirectly gaining data-plane access. Lock down management roles as well; **disabling Shared Key** closes one privilege-escalation path when tooling supports Entra auth.

### 11.2. Role Assignment Scope

An identity needing one state container should not hold **Storage Blob Data Contributor** across every storage account in a subscription. Assign at the narrowest scope supported by the backend and operations:

~~~text
/subscriptions/<id>
  /resourceGroups/<rg>
    /providers/Microsoft.Storage/storageAccounts/<account>
      /blobServices/default/containers/<container>
~~~

Container-scoped role assignments restrict reads and writes to a single container once bootstrapped. If `init` or backend auth flows also require an ARM metadata/endpoint lookup, analyze and grant only minimal read-only ARM permissions—never Owner.

### 11.3. Local Azure CLI Authentication

A usable local configuration:

~~~hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-lab"
    storage_account_name = "stexampleiaclab001"
    container_name       = "tfstate"
    key                  = "orders/dev/app.tfstate"
    use_azuread_auth     = true
    use_cli              = true
  }
}
~~~

Local sign-in:

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
terraform init
~~~

If your Azure CLI environment has multiple accounts or tenants, verify the active identity and token. **Backend auth** follows Terraform CLI's backend implementation and does not automatically inherit all provider settings.

### 11.4. Never Store Account Keys or SAS Tokens in HCL

Bad configuration:

~~~hcl
terraform {
  backend "azurerm" {
    storage_account_name = "stexampleiaclab001"
    container_name       = "tfstate"
    key                  = "orders/prod/app.tfstate"

    # ANTI-PATTERN: NEVER put real credentials in source code.
    access_key = "DO_NOT_PUT_REAL_STORAGE_KEYS_HERE"
  }
}
~~~

If a credential was ever committed, deleting the line at `HEAD` is **insufficient** because Git history and CI logs may already hold it. Assess exposure, revoke/rotate the key or SAS per policy, scan history/artifacts, and switch to Entra authentication.

## 12. Backend Authentication and Provider Authentication Are Separate

### 12.1. The Two Paths Can Target Different Tenants or Subscriptions

Example:

~~~text
Backend:
    Storage subscription = platform-shared
    Storage RBAC = Storage Blob Data Contributor
    Backend blob key = orders/prod/app.tfstate

Provider:
    Application subscription = application-prod
    Azure resource permissions = scoped Contributor + roles
~~~

A pipeline may use two separate identities or one identity holding both permission sets. For **least privilege** and separation of duties, separating permissions makes auditing far cleaner.

### 12.2. Very Common Mistake

Someone configures:

~~~hcl
provider "azurerm" {
  features {}
  subscription_id = "<app-subscription-id>"
}
~~~

and assumes the backend automatically knows which subscription holds the storage account. **Incorrect**: the `backend` block requires its own coordinates and authentication, and backend `init` executes before provider initialization.

### 12.3. Authentication Strategy

| Method | Best Use | Trade-offs |
|---|---|---|
| Azure CLI / interactive Entra | Developer labs | Unsuitable for unattended CI |
| Managed identity | Azure-hosted runner with attached identity | Requires proper runner networking/identity setup |
| OIDC / workload identity federation | CI/CD with short-lived tokens | Federation/claim/config setup complexity |
| Service principal secret/cert | Legacy / non-OIDC workloads | Credential rotation and leak risks |
| Storage account key | Legacy backend auth | Broad privileges, static credential requiring rotation |
| SAS token | Scoped/delegated storage access | Expiry/revocation and secret handling |

Prefer **OIDC / managed identity / Entra blob auth** wherever supported by your Terraform CLI/backend version and Azure DevOps/GitHub platform. Never enable all five methods at once and leave the backend guessing which one wins.

## 13. Terraform Workspaces and State Key Isolation

### 13.1. What Are Workspaces?

Terraform **CLI workspaces** support multiple state instances for one configuration where supported by the backend. With `azurerm`, non-default workspaces use **`workspace_key_prefix`** / backend-managed naming conventions.

Example:

~~~bash
terraform workspace list
terraform workspace new dev
terraform workspace select dev
terraform workspace show
~~~

**Do not guess** the exact Blob key name just by concatenating the workspace name in your head. Check backend documentation and inspect Blob object names after `init` and operations.

### 13.2. Workspaces Are Not a Security Boundary

If an identity holds read access on the entire container, switching workspace names **does not narrow** permissions. When dev and prod need RBAC or network isolation, use separate storage accounts/containers and distinct identities.

### 13.3. Workspaces vs. Separate Backend Keys

| Goal | Recommendation |
|---|---|
| Ephemeral PR environments sharing permissions and lifecycle | Workspaces can be convenient |
| Long-lived prod/staging/dev needing isolation | Separate backend keys / containers / accounts |
| Network state and app state with different owners | Separate state keys and stacks |
| Sensitive multi-tenant data | Separate backend security scopes |
| Clear CI/CD target verification | Explicit per-environment backend coordinates |

Never rely on **`terraform workspace select prod`** as your sole safeguard preventing a PR job from deploying to production. Enforce RBAC, service connection approvals, and branch rules.

### 13.4. Never Rename a Key to "Switch Environments"

If current state manages dev resources, changing **`key`** from dev to prod without controlled migration or authorization makes Terraform see an **empty/new state**, proposing to recreate resources or corrupt environments. Any change to backend coordinates demands review and dry-runs.

## 14. Terraform State and Outputs Can Expose Secrets

### 14.1. Terraform's `sensitive` Flag Protects UI, Not Storage

~~~hcl
output "connection_string" {
  value     = azurerm_storage_account.example.primary_connection_string
  sensitive = true
}
~~~

This HCL sample assumes the referenced resource exists in the project. **`sensitive = true`** primarily masks CLI outputs/UI; **it does not remove or encrypt the value inside state**.

### 14.2. Avoid Putting Secrets into State by Design

- Use **managed identity / Entra auth** instead of connection strings or account keys wherever services support it.
- Avoid using **`random_password`** and exporting raw values in outputs when an identity-based flow is possible.
- When managing a secret is unavoidable, tightly restrict state readers and remember that **Key Vault Secret resource metadata** or provider attributes can still persist in state.
- Avoid unnecessary data sources that read secret values.
- Never print sensitive outputs in CI logs or issue trackers.
- Never use **`terraform state pull`** to feed secrets to an application runtime.

## 15. Migrating Local State to Azure Storage: `terraform init -migrate-state`

### 15.1. Why Never Copy the File Manually?

Suppose a team has a local **`terraform.tfstate`** managing 20 Azure resources. If you simply add a `backend` block, delete the local file, and run `init`, Terraform sees an empty remote state and tries to recreate everything. Uploading a state file manually via Storage Explorer risks wrong blob keys, formatting issues, concurrency bugs, or skipping migration checks.

**Use Terraform's built-in migration mechanism**—never treat backend migration as a plain file copy.

### 15.2. Pre-Migration Runbook

1. **Assign an owner and maintenance window** for the stack.
2. Notify everyone to stop running **`plan`/`apply`/state commands** on the stack.
3. Verify the exact branch/commit, Terraform version, and provider lockfile.
4. Confirm local state currently tracks the expected resources and subscription.
5. Verify no `apply` jobs are running.
6. Prepare the target storage account/container/key with Entra RBAC and network connectivity.
7. Verify the destination blob **does not already contain another stack's state**.
8. Save a backup of local state and supporting files under a **secure backup runbook**—never upload to Git or chat.
9. Document the rollback plan, owner, and verification criteria.
10. Avoid editing resource definitions simultaneously with migration unless required.

If local state is lost or incomplete, execute import/recovery runbooks first; migration cannot reconstruct missing resource-to-address mappings from Azure on its own.

### 15.3. Before Migration: Local Backend

A Terraform project configured as:

~~~hcl
terraform {
  required_version = ">= 1.6.0"
  # No backend block yet: uses default local state.
}
~~~

Inspect local state **without exposing values**:

~~~bash
terraform version
terraform state list
terraform plan
~~~

**`terraform state list`** prints resource addresses and names; treat this metadata as internal. Avoid running **`terraform state pull`** and printing raw JSON.

### 15.4. Adding the Partial `azurerm` Backend

Edit **`backend.tf`**:

~~~hcl
terraform {
  backend "azurerm" {}
}
~~~

Create **`backend.prod.hcl`**:

~~~hcl
resource_group_name  = "rg-iac-state-prod"
storage_account_name = "stexampleiacprod001"
container_name       = "tfstate"
key                  = "orders/prod/app.tfstate"
use_azuread_auth     = true
use_cli              = true
~~~

Names are illustrative; substitute approved live storage coordinates. **Backend files must hold only non-secret metadata**—no account keys or client secrets.

### 15.5. Running the Migration

With writers frozen, Azure CLI identity authorized, and storage reachable:

~~~bash
az login
az account set --subscription "<backend-subscription-id>"

terraform init \
  -migrate-state \
  -backend-config=backend.prod.hcl
~~~

Terraform prompts to confirm **copying/migrating existing state**. Confirm only after verifying source and destination. In automated migrations, never bypass prompts on production without explicit approvals and destination-collision guards.

**Never run a concurrent `terraform apply`** during migration. State migrations and backend switches are high-sensitivity operations.

### 15.6. Post-Migration Verification

1. Run **`terraform state list`** and confirm resource addresses and counts match.
2. Confirm the blob key exists in the right storage account/container using a **metadata-only list**.
3. Record state lineage/serial securely if required—**never print raw state**.
4. Run **`terraform plan`** with the intended identity and provider permissions.
5. Expect **no changes** if code and live resources haven't changed (aside from any known real drift or provider normalization).
6. Verify lease/locking with a controlled test—never run parallel applies on prod.
7. Update runbooks, team docs, and CI backend config references.
8. Confirm all developers and pipelines have switched to the remote backend.
9. Archive the local backup in a secure vault per retention rules; remove stray plaintext state from laptops and CI workspaces.

If `plan` proposes recreating all resources, **stop immediately** and do not apply. Check the key, workspace, migration outcome, source state, and subscription to avoid creating duplicate resources.

### 15.7. `terraform init -reconfigure` vs. `-migrate-state`

| Option | Purpose | Risk |
|---|---|---|
| **`terraform init -migrate-state`** | Migrates existing state to the new backend via workflow | Requires accurate source/target and frozen writers |
| **`terraform init -reconfigure`** | Discards cached backend config and re-initializes | **Does not copy state** |
| **`terraform init -backend=false`** | Skips backend init (useful for certain offline validations) | Performs no remote state operations |
| **`terraform force-unlock`** | Clears a stale state lock with approval | Concurrent write / state overwrite risk |

**Never use `-reconfigure` as a "faster migration shortcut".** If the new backend key is empty, Terraform treats the stack as unmanaged from scratch.

### 15.8. Migration Rollback

If a migration goes wrong before any new `apply` runs:

- Freeze all writers and determine which backend holds the **source of truth**.
- Compare state metadata/lineage using authorized tools.
- Never run operations simultaneously against both local and remote copies.
- Restore from a secure backup or blob version **per runbook**.
- Use controlled Terraform backend migration/reconfigure commands and log a change ticket.
- Resume `plan`/`apply` only after verifying state mappings against live Azure resources.

Once a new `apply` has mutated remote state, rolling back to an older state backup drops newly created tracking. **Reconcile** carefully instead of blindly overwriting with an old snapshot.

## 16. Versioning, Soft Delete, and Backup Design

### 16.1. Why Back Up State?

Risks:

- Accidental deletion of a state blob or container.
- Running `terraform state rm/mv` on the wrong address.
- `apply` failing halfway after modifying Azure resources.
- Another pipeline targeting the wrong backend key.
- Compromised principal writing corrupt or arbitrary state.
- Expired or lost local backup files.
- Storage account deletion, regional or network outage.
- State schema shifts from incompatible provider upgrades or botched migrations.

### 16.2. Blob Versioning

With versioning enabled, Azure Blob Storage retains prior versions of the state blob on overwrites. This lets you pick a restore point if **the latest state becomes corrupted or unwanted**, within service and retention limits.

**Do not assume every blob version matches live Azure resources.** An `apply` can create or modify Azure resources before writing state. Selecting the right backup serial/lineage/timestamp requires checking audit logs and live resources.

### 16.3. Soft Delete

Soft delete retains deleted blobs for a configured retention period, enabling recovery from accidental deletion. Distinguish:

- **Blob soft delete**.
- **Container soft delete**, when enabled separately where supported.
- **Blob versioning**.
- **Storage account/resource deletion** (not automatically protected in all cases by blob soft delete alone).
- **Off-site / cross-region backup and recovery**.

Do not confuse these features with "Azure Storage automatically backs up everything forever".

### 16.4. Replication Is Not Historical Backup

| Redundancy | General Meaning | What It Does Not Guarantee |
|---|---|---|
| **LRS** | Synchronous copies within a single datacenter/region per Storage service | Does not protect against regional failure |
| **ZRS** | Synchronous copies across availability zones where supported | Does not fix logically corrupted state |
| **GRS / RA-GRS** | Asynchronous replication to a paired region | Does not guarantee zero RPO or active writes in secondary |
| **GZRS / RA-GZRS** | Combines zone and geo redundancy where supported | Does not replace failover/recovery runbooks |
| **Versioning / soft delete** | Retains historical objects for restore | Does not stop storage account deletion by high-privilege attackers |

A logically corrupted state write is **faithfully replicated** to the secondary region. Geo-replication and historical versioning solve two different problems.

### 16.5. Safe State Recovery Procedure

When state loss or corruption is suspected:

1. Place the stack in **maintenance/freeze**; halt all `plan`/`apply` writers.
2. Identify the exact Storage account, container, blob key, and workspace.
3. Inspect Azure Storage diagnostic logs and Activity Logs for the last write/delete event.
4. List available blob versions and soft-deleted objects using authorized permissions.
5. Preserve a copy of raw evidence in a secure vault—never paste into CI logs.
6. Compare candidate versions against Terraform state lineage, serial, resource addresses, and live Azure resources.
7. Pick a recovery point with documented evidence—never blindly pick the newest timestamp.
8. Restore via an organization-approved Azure Storage / Terraform procedure.
9. Verify leases, locks, and authorization without breaking an active writer's lock.
10. Run a supervised **`terraform plan`**—do not apply immediately.
11. Resolve any drift using `import`, `moved` blocks, or state commands only with approval.
12. Write a postmortem covering root cause, blast radius, RPO/RTO, and policy fixes.

**Never paste raw state into chat or tickets** for peer review. State can contain credentials even when masked in CLI summaries.

### 16.6. Backup Encryption and Immutable Archives

Storage encrypts blob data at rest by default; **customer-managed keys (CMK)** may be required by policy. For tamper-proof archives, configure **separate** immutable storage/archive copies. Never slap a legal hold on an **active state blob**: Terraform must overwrite state and manage Blob leases.

### 16.7. Recovery Point Objective

- **RPO**: maximum acceptable state-change loss (e.g., one `apply`).
- **RTO**: time required to restore controlled `plan`/`apply` capability.
- **Durability vs. recoverability**: durable storage is useless if you cannot identify which version is valid.
- **Incident command**: who holds authority to restore state versions and reconcile against live Azure resources?

Set SLO/RPO/RTO targets per stack criticality rather than applying one arbitrary number everywhere.

## 17. Storage Security, Encryption, Resource Locks, and Delete Permissions

### 17.1. Defense-in-Depth Security Controls

~~~mermaid
flowchart TD
    ID["Microsoft Entra ID<br/>managed/OIDC identity"] --> RBAC["Storage Blob Data Contributor<br/>scoped access"]
    RBAC --> NET["VNet / Firewall / Private Endpoint"]
    NET --> TLS["HTTPS TLS 1.2+"]
    TLS --> BLOB["State blob"]
    BLOB --> VER["Versioning + soft delete"]
    BLOB --> MON["Audit logs + alerts"]
    ARM["ARM management governance"] --> GUARD["Resource lock / Azure Policy"]
    GUARD --> BLOB
~~~

The layers in this diagram represent a **control model**, not an internal authorization evaluation order.

### 17.2. Disabling Public Blob Access vs. Disabling Public Network Endpoint

- **Allow Blob anonymous public access = false** blocks anonymous public reads on containers/blobs.
- **Public network access = disabled** shuts down the public network endpoint and requires private connectivity.
- **Azure AD / RBAC** governs what authenticated callers can do on the data plane.
- **Private Endpoint** governs private VNet connectivity and DNS resolution.
- **Shared Key access disabled** removes account-key auth paths when all tooling is compatible.

A storage account with anonymous access disabled is still reachable over the public internet for **authenticated requests** if firewalls/network rules remain open. Never confuse these two controls.

### 17.3. Azure Resource Locks

A **`CanNotDelete`** lock on the state storage account or backend RG reduces accidental deletion via ARM, yet it:

- Does not block data-plane overwrites of state blobs.
- Does not replace RBAC or blob versioning.
- Can block legitimate platform maintenance operations.
- Requires separate break-glass governance and auditing.

Never confuse an **ARM resource lock** with a **Terraform state lock** or Azure Blob lease—they solve completely different problems.

### 17.4. Encryption

Azure Storage encrypts blob data at rest and enforces HTTPS in transit. If using a **customer-managed key (CMK)**, configure Key Vault/Managed HSM, managed identity, and key rotation/recovery policies carefully. Revoking a key or experiencing a Key Vault outage can block access to encrypted storage, halting `terraform init`/`plan`/`apply`.

**Encryption at rest does not replace RBAC**: any caller authorized to read the blob receives plaintext state over the authorized API.

### 17.5. Least Privilege and Break-Glass

Production environments should:

- Separate bootstrap/storage-admin identities from Terraform runtime identities.
- Scope `Storage Blob Data Contributor` to the specific container wherever feasible.
- Restrict container/account deletion at the management plane.
- Alert on role assignment, Shared Key, and network policy modifications.
- Maintain time-bound break-glass identities/approvals rather than static credentials in CI.
- Periodically rehearse read-only restores and backend failover using safe snapshots/clones.

## 18. Private Endpoints and Private DNS for Remote State

### 18.1. Why Does the Backend Need a Network Path?

`terraform init`/`plan`/`apply` require HTTPS access to Azure Storage's **Blob endpoint**. If the storage account allows only private networks, a default internet-hosted Microsoft agent **is outside the VNet**, even when the pipeline holds valid Azure service connections and data roles.

**Having a valid token and RBAC is not enough** if network policies block traffic.

### 18.2. Azure Blob FQDN

The standard endpoint looks like:

~~~text
https://<storage-account>.blob.core.windows.net
~~~

With a Private Endpoint, clients still connect to the standard FQDN; internal DNS resolves it via the private DNS zone:

~~~text
privatelink.blob.core.windows.net
~~~

Never replace the storage account hostname with a raw private IP to "skip DNS", as TLS hostname validation and service routing will break.

### 18.3. Network Topology

~~~mermaid
flowchart LR
    AGENT["Terraform agent<br/>inside approved VNet"] --> DNS["VNet DNS resolver"]
    DNS --> PE["Private Endpoint<br/>Blob service"]
    PE --> SA["Azure Storage account<br/>tfstate container"]
    AGENT --> ID["Microsoft Entra token endpoint"]
    AGENT --> ARM["ARM API for provider resources"]
    SOC["Azure Monitor"] -. "storage logs" .-> SA
~~~

Verify all paths together:

- Agent egress to the Azure Storage Blob private endpoint.
- Private DNS zone links and DNS forwarding in hub-and-spoke topologies.
- Reachability to Entra token endpoints.
- Reachability to Azure Resource Manager endpoints for the provider.
- VNet route tables, NSGs, Azure Firewall/NAT, and proxies.
- Cross-region and cross-subscription networking rules.

### 18.4. Microsoft-Hosted vs. Self-Hosted Agents

| Agent | When Storage Is Private-Only |
|---|---|
| Default Microsoft-hosted agent | Usually **cannot** reach VNet private endpoints directly |
| Self-hosted agent inside VNet | Can use private DNS and routing when configured properly |
| Managed DevOps Pools / VNet-injected runners | Verify VNet injection capabilities per product/SKU |
| Local developer over VPN/ExpressRoute | Works if DNS forwarding and VNet routing are configured |

Never open storage public access to the entire internet just to get a pipeline running. Pick the right agent/network architecture—or use governed firewall allowlists only if permitted by policy.

### 18.5. Network Checklist

1. Storage account `publicNetworkAccess` setting.
2. Private Endpoint for the Blob service exists and its connection is approved.
3. Private DNS zone **`privatelink.blob.core.windows.net`** is linked to the right VNet.
4. The actual agent resolves the storage account FQDN to the expected private IP.
5. Firewalls, NSGs, routes, and proxies permit HTTPS traffic.
6. Entra token endpoints are reachable.
7. `Storage Blob Data Contributor` is assigned to the exact principal.
8. Terraform backend is not accidentally attempting a disabled Shared Key flow.
9. Azure Monitor diagnostics can deliver logs to the approved destination.
10. Failures clearly distinguish network/TLS errors from 403 RBAC errors.

### 18.6. Blob Private Endpoints vs. File/Queue/Table

Azure Storage exposes separate subresources for Blob, File, Queue, and Table. Terraform's **`azurerm` backend** stores state on the **Blob service**, so the Private Endpoint must target the **`blob` subresource** (plus additional subresources only if your workflow uses them). Having a `file` private endpoint is not enough.

## 19. OIDC / Workload Identity Federation for Terraform CI/CD

### 19.1. Objective

A pipeline runs **`terraform init/plan/apply`** daily. Storing a Storage account key or a long-lived service principal secret in CI variables risks leakage via logs, untrusted PRs, or pipeline admins.

**OIDC federation** lets a CI identity exchange trusted claims for short-lived Entra tokens with zero long-lived secrets. Supported patterns include:

- Azure DevOps ARM service connections with Workload Identity Federation.
- GitHub Actions OIDC with federated identity credentials.
- Azure-hosted runners using managed identities.
- Other CI platforms when supported by the backend's credential exchange.

### 19.2. Key Prerequisites

- Terraform CLI and `azurerm` backend version supporting **`use_oidc`** and Entra blob auth.
- Federated identity credential matching the CI platform's exact issuer, subject, and audience.
- Properly provisioned Entra app/service principal or user-assigned managed identity.
- **`Storage Blob Data Contributor`** assigned to that principal on the state storage account/container.
- Separate provider permissions to plan and apply Azure resources.
- Agent network reachability to Blob, ARM, and Entra endpoints.
- OIDC token issuance restricted by branch, environment, or resource trust policies.
- Zero static client secrets or SAS tokens in backend config or pipeline variables.

### 19.3. Backend Block for OIDC

Sample **backend configuration** for an OIDC-capable runtime:

~~~hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-iac-state-prod"
    storage_account_name = "stexampleiacprod001"
    container_name       = "tfstate"
    key                  = "orders/prod/app.tfstate"
    use_azuread_auth     = true
    use_oidc             = true
  }
}
~~~

Client ID, tenant ID, subscription ID, and OIDC token parameters are supplied by the CI platform and credential flow per backend version. **Do not mix `use_cli = true` from local setups with this OIDC setup assuming the backend will pick the right one automatically.**

### 19.4. Verifying Azure DevOps Service Connections

In Azure DevOps:

1. Create an **Azure Resource Manager service connection** using Workload Identity Federation per organizational standards.
2. Scope it tightly to required subscriptions, resource groups, or resources.
3. Guard the connection with pipeline permissions and approvals/checks.
4. Grant the Blob data role on the state container to that exact service principal.
5. Grant provider resource permissions in a separate permission layer.
6. Inside approved jobs, pass **federated token and principal metadata** into the Terraform backend as supported by your backend version.
7. Never echo ID tokens or access tokens to logs.
8. Run `init`/`plan` from trusted branches; gate `apply` behind approvals.
9. Audit the actual backend identity via logs and role assignments.

**Important:** Having an `AzureCLI@2` task log in via a service connection **does not automatically ensure** the Terraform backend receives an OIDC token or works in Azure CLI mode. Verify **Terraform `azurerm` backend auth docs** for your exact release and how tokens/metadata are passed. Never assume `azureSubscription` automatically satisfies backend authentication.

### 19.5. GitHub Actions OIDC

GitHub OIDC likewise requires:

- Matching repository, environment, or branch subject claims.
- Granting **`id-token: write`** only on workflows that need it.
- Configuring Azure login/OIDC per the exact action/tool version.
- Assigning `Storage Blob Data Contributor` for state to the federated principal.
- Isolating provider credentials and subscriptions cleanly.
- Protected environments and required reviewers for production.

Never bind production backend roles to an identity that pull requests from forks can impersonate.

## 20. CI/CD Pipeline Patterns with Terraform Remote State

### 20.1. Three Tiers to Separate

| Tier | Purpose | Permissions |
|---|---|---|
| **PR static validation** | `fmt`/`validate`/module tests | Zero access to production state |
| **Trusted plan** | Reads remote state + live Azure resources, builds diff | Blob data read/write lease + matching provider read |
| **Approved apply** | Executes diff and writes state | `Storage Blob Data Contributor` + scoped provider write/role rights |

`terraform plan` usually acquires a state lock (unless disabled by specific flags), meaning even plan jobs typically need lease/write permissions on the state blob. Never assume **`Storage Blob Data Reader`** suffices for every remote plan.

### 20.2. Static PR Validation Without Live Backend Init

A PR job can run:

~~~bash
terraform fmt -check -recursive
terraform init -backend=false -input=false
terraform validate -no-color
~~~

This may download uncached providers/modules, yet **never touches production remote state**, minimizing blast radius from untrusted PR code. For private module/provider feeds, still isolate feed credentials along trust boundaries.

### 20.3. Trusted Plan Job

In a job holding proper federation/managed identity, network reachability, and backend config:

~~~bash
terraform init \
  -input=false \
  -backend-config=backend.prod.hcl

terraform validate -no-color

terraform plan \
  -input=false \
  -lock-timeout=5m \
  -out=plan.bin
~~~

**`plan.bin` is a sensitive artifact.** If persisted for post-approval `apply`, encrypt it, restrict downloads, bind it to the run ID/commit, and enforce short TTLs. Never run **`terraform show -json plan.bin`** and dump the full payload into public PR comments.

### 20.4. Approved Apply

Once approved, apply **the exact binary plan** from that trusted run so code and inputs cannot shift between `plan` and `apply`:

~~~bash
terraform apply \
  -input=false \
  -lock-timeout=5m \
  plan.bin
~~~

Remember that a saved plan becomes invalid if remote state changes in the meantime; Terraform rejects it as a **stale plan**. Never bypass this with `-lock=false` or `force-unlock`. Re-plan against current source and approvals.

### 20.5. Never Commit Credentials or Plans

A Git repository should typically ignore:

~~~text
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
plan.bin
crash.log
crash.*.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
~~~

**`.terraform.lock.hcl`** is the dependency selection lockfile and **should normally be committed** to pin provider versions and checksums; never confuse it with a **Terraform state lock** or Blob lease. Keep the lockfile in version control and review every provider diff.

### 20.6. Concurrency Guards Beyond Terraform Leases

Azure Pipelines/CI can serialize applies per environment or resource using deployment locks, checks, or concurrency groups, reducing job contention. Still, **Terraform Blob leases remain essential** whenever engineers or external CI jobs could trigger runs concurrently.

Minimum guards:

- At most one approved `apply` job per state key at a time.
- Never share a blob key between dev and prod.
- CI branch and permission rules prevent PRs from applying prod.
- Alerts fire when an `apply` holds a lock abnormally long.
- Runbooks govern stale-lock investigation and `force-unlock`.
- Post-apply checks verify updated state and drift status.

## 21. Controlling Backend Changes via Pull Requests

### 21.1. High-Sensitivity Files

- **`backend.tf`** or backend HCL files.
- Terraform provider version constraints.
- **`.terraform.lock.hcl`**.
- CI workflows passing backend configs or credentials.
- Terraform modules managing the Storage account or RBAC.
- IAM role assignments and service connections.
- Private endpoints and firewall rules on the state storage account.
- Retention, versioning, and diagnostic settings.

A PR changing just **`key = "orders/prod/app.tfstate"`** to another key can be as risky as modifying hundreds of Azure resources. Reviewers must treat it as a **state migration**, not a casual rename.

### 21.2. Changing a State Key Requires Its Own Procedure

Before merging:

1. Document old key, new key, owner, and justification.
2. Verify current state and canonical source of truth.
3. Freeze `apply` writers.
4. Take a secure state backup.
5. Migrate using a Terraform-supported workflow.
6. Verify resource address count and confirm `plan` shows no unexpected changes.
7. Update CI pipelines, agents, and approvals.
8. Retain recovery points per retention policy.
9. Re-enable `apply` only after verification completes.

### 21.3. Never Silently Fall Back to a Default Backend for Prod

If a pipeline fails to locate **`backend.prod.hcl`**, never fall back to local state or the dev backend. **Fail fast** with an error naming only the missing config path—never printing credentials.

### 21.4. Should `backend.hcl` Files Be Committed?

Files holding only **non-secret** resource group, storage account, container, key, and auth flags can live in Git under governance. However, organizations classifying infrastructure coordinates as sensitive metadata can store them in protected config libraries/templates instead. **Never commit account keys, SAS tokens, or client secrets.**

## 22. Drift, Import, and Controlled State Repair

### 22.1. What Is Drift?

Drift occurs when live Azure resources are altered outside Terraform or state no longer matches reality—for instance, an operator upgrades an App Service plan in the Azure Portal while Terraform HCL still specifies the old SKU.

**`terraform plan`** detects diffs during state refresh, though not every external change surfaces immediately or maps cleanly in every provider schema.

### 22.2. State Loss vs. Infrastructure Loss

- **Lost state**: Azure resources still run, yet Terraform loses track of mappings.
- **Lost resource**: state still lists an address for a deleted resource.
- **State divergence**: state holds stale attributes or resource IDs.
- **Out-of-band change**: Azure resource exists but was modified outside IaC.

Never respond to every mismatch by running **`terraform destroy`** and recreating from scratch.

### 22.3. When to Use `terraform import`?

When an Azure resource exists outside state, bring it under management using **`terraform import`** or **`import` blocks** per your Terraform version. Before importing:

1. Confirm the exact live resource ID and desired Terraform resource address.
2. Verify no duplicate mapping already exists in the current state key.
3. Ensure importing won't place the same resource under two separate state files.
4. Review the provider resource schema.
5. Run the import inside a locked change window.
6. Run `plan` and reconcile any configuration diffs.
7. Document the origin and outcome.

**Importing does not generate complete HCL automatically**: you must write matching configuration so subsequent plans do not try to modify or destroy the imported resource.

### 22.4. Risky State Commands

| Command | Effect | Risk |
|---|---|---|
| `terraform state list` | Lists addresses | Low operational risk; still exposes metadata |
| `terraform state show` | Displays attributes | Exposes sensitive attributes |
| `terraform state mv` | Moves resource address mapping | Wrong mapping breaks plans |
| `terraform state rm` | Drops resource from state while keeping live resource | Resource becomes unmanaged |
| `terraform import` | Binds existing resource to an address | Duplicate management if misapplied |
| `terraform force-unlock` | Clears state lock | Concurrent writes |
| `terraform state pull` | Prints raw state | Data exposure |
| `terraform state push` | Overwrites raw state | State corruption if misused |

Any state-mutating command requires approval, a backup, an owner, and a follow-up `plan`. Never practice syntax on production state.

## 23. Supply Chain Security Perspective on Terraform State

Terraform HCL declares infrastructure, yet modules, providers, and external data sources execute code and read sensitive resources. IaC pipelines cannot rely solely on blob storage security.

### 23.1. Trust Chain

~~~mermaid
flowchart TD
    GIT["Git commit + review"] --> MOD["Terraform modules/providers"]
    MOD --> PLAN["Plan artifact + approval"]
    PLAN --> APPLY["Approved apply job"]
    APPLY --> ARM["Azure live resources"]
    APPLY --> BLOB["Azure Blob remote state"]
    ID["OIDC/managed identity"] --> APPLY
    RBAC["Blob data + provider RBAC"] --> APPLY
    AUDIT["Logs/alerts/provenance"] -. "observe" .-> BLOB
~~~

### 23.2. Governing Providers and Modules

- Pin provider versions in `required_providers` and commit **`.terraform.lock.hcl`**.
- Run **`terraform init -lockfile=readonly`** in CI when policy forbids automatic lockfile edits.
- Use trusted module registries/sources and pin immutable versions or commit SHAs.
- Review remote module updates; never track unpinned branch HEADs in production.
- Never embed access tokens in module source URLs or backend configs.
- Restrict network egress and identity scope on CI runners.
- Separate PR validation from approved `apply` jobs.
- Scan IaC for policy violations, secrets, and unsafe network/resource defaults.
- Verify source commit and saved plan provenance before running `apply`.

### 23.3. What Can an Attacker Do with State Write Access?

A principal holding data-plane write access on the state blob can:

- Read stored sensitive attributes.
- Overwrite or delete state, destroying resource mappings.
- Cause lock or availability disruptions.
- Trick future plans into destructive edits by tampering with state.
- Obscure infrastructure changes from Terraform's perspective.

Thus **`Storage Blob Data Contributor`** on production state is a highly privileged permission—never treat it as "just permission to upload a file".

### 23.4. Detecting and Responding to State Tampering

When unauthorized state modification is suspected:

1. Freeze all CI applies.
2. Inspect storage diagnostic logs and RBAC role changes.
3. Preserve forensic evidence and prior blob versions.
4. Trace the principal, source IP, commit, and pipeline run.
5. Securely compare state lineage/serial against live Azure inventory.
6. Revoke compromised identities/credentials per incident runbook.
7. Restore or reconcile state under formal approval.
8. Run `plan` in a controlled session.
9. Check for exposed secrets in state and rotate them as needed.
10. Strengthen detection, least privilege, and network controls.

Never restore an older state snapshot and allow production `apply` without auditing how live Azure resources changed in the interim.

## 24. Sharing State and Protecting Terraform Outputs

### 24.1. `terraform_remote_state` Is Not Secret Isolation

Terraform's **`terraform_remote_state`** data source lets one stack read another stack's outputs. Even though the HCL surface exposes only outputs, backend permissions grant read access to **the entire raw state snapshot**, including sensitive data.

To share non-sensitive values between stacks safely, consider:

- Azure App Configuration for non-secret settings.
- Azure Key Vault for secrets.
- ARM resource IDs via naming conventions or scoped ARM data sources.
- Access-controlled pipeline artifacts / contract manifests containing zero secrets.
- Publishing selected non-sensitive outputs into a store with narrow data-plane RBAC.

Never grant **`Storage Blob Data Reader`** over all of production state just so a dev stack can look up a URL.

### 24.2. Plan Files and Crash Logs Also Need Protection

**`terraform plan -out=plan.bin`** can store sensitive values and context. Terraform debug logs (`TF_LOG`) can capture raw HTTP requests and responses. Protect CI artifacts and crash logs just like state:

- Restrict retention, access, and artifact download rights.
- Never publish `plan.bin` as a public artifact.
- Never dump raw **`terraform show -json`** into public PR comments.
- Enable log redaction and avoid verbose debug levels in shared pipelines.
- If state or a plan leaks, treat it as an incident and rotate impacted credentials.

### 24.3. Rules for Sharing Data Across Stacks

| Need | Appropriate Approach | What to Avoid |
|---|---|---|
| App stack needs subnet ID | ARM data source / approved output contract | Granting read access to full network state unnecessarily |
| App runtime needs API secret | Managed identity + Key Vault | Reading Terraform state for secrets |
| CI needs environment metadata | Secure non-secret config manifest | Pasting raw `tfstate` into pipeline variables |
| Another stack needs storage endpoint | Azure resource data source / App Configuration | Making state blobs public |
| Investigating state corruption | Authorized encrypted backup / forensics | Sending state JSON via chat or tickets |
| Approved rollback | Blob versions + Terraform reconciliation | Blindly overwriting with old state while applies run |

When publishing selected outputs to an external store, evaluate **data classification, audience, update/retention lifecycle, and access permissions**. Not every Terraform output is safe for public consumption.

## 25. Troubleshooting the `azurerm` Backend

Remote state failures stem from **backend config, identity, RBAC, networking, storage metadata, locking, or Terraform CLI**. Isolate the exact layer before making changes.

### 25.1. Diagnostic Table

| Symptom | Likely Cause | Next Checks |
|---|---|---|
| `init` reports container not found | Wrong storage account/container or not bootstrapped | List container via Azure CLI using Entra auth |
| `init` reports state blob not found | First run with no state yet, or wrong key | Verify key/lifecycle; never upload empty JSON |
| 401 Unauthorized | Missing/wrong token audience or auth flow mismatch | Check Azure CLI / OIDC / managed identity / backend version |
| 403 `AuthorizationPermissionMismatch` | Insufficient Blob data-plane role | Verify principal, scope, and role assignment |
| 403 due to firewall | Agent outside allowed network | Check public access / Private Endpoint / DNS / firewall |
| Shared Key rejected | Account disables Shared Key while backend attempts key flow | Check `use_azuread_auth` and identity settings |
| 404 wrong storage name | Typo or wrong backend coordinates | Check backend HCL and ARM metadata |
| 409 `LeaseAlreadyPresent` / lock conflict | Another job holds lease or stale lock | Inspect active runs, lock metadata, `-lock-timeout` |
| 412 Precondition Failed | Lease/ETag/precondition conflict on operation | Check concurrency and state version/lock |
| "Error acquiring state lock" | Active writer or unreleased lock | Locate active job/actor; don't rush `force-unlock` |
| State unexpectedly empty | Key or workspace changed without migration | Compare before/after backend configuration |
| Terraform proposes recreating all resources | Wrong state key or failed migration | **STOP**, verify lineage and resource addresses |
| "Backend configuration changed" | Backend HCL or flags modified | Choose `-migrate-state` or `-reconfigure` intentionally |
| Local auth works, CI fails | CI identity differs from developer | Verify OIDC/MI principal, token, and environment |
| `init` OK, `plan` gets 403 on Azure resources | Backend authorized, provider lacks permissions | Verify provider subscription and RBAC |
| `init` gets 403 on Blob, Portal views account OK | Identity has ARM read only, lacks blob data role | Assign `Storage Blob Data Contributor` |
| DNS returns public IP despite Private Endpoint | Wrong Private DNS zone, VNet link, or forwarder | Test DNS resolution from the actual CI runner |
| `terraform apply` fails after creating resources | Provider/API/network/partial failure | Reconcile state with live resources; never delete state |
| Blob versioning shows no history | Feature disabled or lifecycle policy expired it | Check blob service properties and timestamps |
| Git accidentally contains `terraform.tfstate` | Secret exposure | Quarantine repo, scan/rotate credentials |
| Shared backend account scheduled for deletion | Missing lifecycle guard or lock | Halt ops, preserve evidence, trigger incident response |

### 25.2. Triage Procedure for 401 and 403 Errors

A 403 error is often misdiagnosed as missing Azure Subscription Contributor rights:

1. Determine whether the error comes from the **Azure Blob backend** or the **`azurerm` provider**.
2. Verify the exact **storage account, container, and key**.
3. Identify the exact **principal object ID** of the user or CI agent.
4. Check backend auth flags: **`use_azuread_auth`**, **`use_cli`**, or **`use_oidc`**.
5. Verify **`Storage Blob Data Contributor`** is assigned at the intended scope.
6. Check for role propagation delay, Conditional Access, or tenant mismatches.
7. Check storage account **`allowSharedKeyAccess`** and CLI/backend compatibility.
8. Check firewalls, `publicNetworkAccess`, and Private Endpoint approval status.
9. From the **actual host/runner**, resolve the storage FQDN and test HTTPS connectivity.
10. Cross-check Azure Storage diagnostic logs and Azure Activity Log role changes.
11. Retest with a metadata-only Blob call against a **lab container** first.
12. Document root cause; never fall back to account keys to bypass controls without approval.

### 25.3. Distinguishing Network Errors from RBAC Errors

Two runs using the exact same principal and data role from different agents:

~~~text
Developer laptop via corporate VPN → terraform init OK
Microsoft-hosted agent (not in VNet) → terraform init Forbidden
~~~

The culprit is likely a network restriction even though the token is valid. Switching to a VNet-joined self-hosted agent with proper private DNS/routing resolves it—**no need to grant Owner** or open the storage account to the public internet.

### 25.4. Checking Backend Coordinates When `init` Sees Empty State

Verify:

- Resource group of the **backend storage account**, not the App Service resource group.
- Exact spelling of the storage account name.
- Container exists and is private.
- Exact key—e.g., **`orders/prod/app.tfstate`**, not **`orders/dev/app.tfstate`**.
- Active Terraform workspace.
- Backend configuration re-initialized after changes.
- Identity holds read permissions on the right container.
- Whether prior state still sits at a source needing migration.

**Never run `apply`** if `plan` proposes creating resources that already exist because state appears missing.

### 25.5. Resolving Lock Conflicts

If pipeline A is applying and B cannot acquire the lease:

- Wait or queue B with **`-lock-timeout`** per policy.
- Check with pipeline A's owner and inspect Azure DevOps / CI run status.
- If A hung, cancel or terminate it per runbook.
- Allow the backend to release the lease cleanly if the operation is still finishing.
- Run `force-unlock` only after confirming zero active writers, obtaining approval, and recording the lock ID.
- Run `plan` to check for drift after unlocking.
- Add CI concurrency controls and agent timeouts to prevent future contention.

### 25.6. Stale Plan Errors

A saved plan was generated against state serial N. Another job applied changes advancing state to N+1; Terraform rejects applying the old plan. This is a **safety feature**, not a bug to bypass. Re-plan from reviewed commits/variables and obtain fresh approval if required by policy. Never revert state to N just to force an old binary plan through.

### 25.7. Failures After Storage Account Key Rotation

If a legacy backend uses access keys, rotation breaks automation holding the old key. Long-term, migrate to Entra authentication. During an incident:

1. Verify whether the backend actually uses keys, SAS, or Entra.
2. Check the rotation timeline and Key Vault references through approved channels.
3. Never print keys.
4. Update secrets via an approved secure variable store.
5. Retest backend access, then schedule migrating off key-based auth.
6. Audit Git, CI logs, and workspaces for leftover old credentials.

## 26. Monitoring and Auditing Remote State

### 26.1. Three Telemetry Sources to Combine

| Source | What It Observes | Limitations |
|---|---|---|
| **Azure Storage Blob diagnostic logs** | Blob data-plane operations: read/write/delete/lease requests per config | Does not record Terraform source changes |
| **Azure Activity Log** | ARM control-plane changes to storage accounts, networks, IAM, and diagnostic settings | Does not log individual state blob reads |
| **Terraform CI / apply logs** | Commit SHA, runner, init/plan/apply outcomes, state lock conflicts | Must never capture raw state or credentials |

Microsoft Entra sign-in/workload logs and runner network logs also help diagnose token and Private Endpoint failures.

### 26.2. Enabling Diagnostics for the Blob Service

In the Azure Portal:

1. Open the backend Storage account.
2. Select **Monitoring → Diagnostic settings** or **Blob service → Diagnostic settings** depending on UI.
3. Select supported categories such as **StorageRead, StorageWrite, StorageDelete** on the Blob service.
4. Route logs to a Log Analytics workspace or destination approved by platform/SOC.
5. Verify category, destination, schema, and retention.
6. Never ship raw state JSON into custom logs.
7. Alert on unauthorized edits to diagnostic settings or access policies.

Diagnostic categories attach to the **Blob service subresource** beneath the storage account; do not assume every category appears if configuring at the account root.

**Read-only** CLI example to list supported categories:

~~~bash
BLOB_SERVICE_ID="$SA_ID/blobServices/default"

az monitor diagnostic-settings categories list \
  --resource "$BLOB_SERVICE_ID" \
  --output table
~~~

### 26.3. Log Analytics Table Schema

Azure Storage resource-specific logs appear in **`StorageBlobLogs`** (when resource-specific destination mode is enabled) or under **`AzureDiagnostics`** depending on mode and resource. Column names vary by schema.

Exploratory query:

~~~kusto
StorageBlobLogs
| where TimeGenerated >= ago(24h)
| take 10
~~~

If the workspace lacks this table, check diagnostic settings, destination mode, and ingestion lag. Never conclude state wasn't accessed simply because a query returns table-not-found.

### 26.4. KQL: Summarizing Blob Operations

When **`StorageBlobLogs`** exists with matching columns:

~~~kusto
StorageBlobLogs
| where TimeGenerated >= ago(7d)
| summarize Requests = count()
    by OperationName, StatusCode
| order by Requests desc
~~~

From the results, distinguish reads, writes, lease operations, 403s, 409 lock conflicts, and unusual spikes. **KQL snippets are examples for matching schemas**; inspect your live table and adjust column names as needed.

### 26.5. KQL: Data-Plane Failures Over Time

~~~kusto
StorageBlobLogs
| where TimeGenerated >= ago(24h)
| where toint(StatusCode) >= 400
| summarize Failures = count()
    by bin(TimeGenerated, 15m), OperationName, StatusCode
| order by TimeGenerated asc
~~~

An isolated 404 when checking for an uninitialized state blob can be normal; a burst of 403s after identity rotation is an operational signal requiring investigation.

### 26.6. KQL: Azure Activity Log for the Storage Account

Only when Azure Activity Logs are routed to **`AzureActivity`** in the workspace:

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where ResourceProviderValue =~ "MICROSOFT.STORAGE"
| project TimeGenerated, OperationNameValue,
          ActivityStatusValue, Caller, ResourceId, CorrelationId
| order by TimeGenerated desc
~~~

To audit **Azure role assignments**, query **`Microsoft.Authorization`** operations, which may sit at parent scopes above the storage account—do not filter solely on the Storage provider.

### 26.7. Operational Metrics

- Terraform **`init` success rate** by environment.
- **`plan`/`apply` duration**, queue wait time, and failure rate.
- **Lock acquire wait time** and lock conflict counts.
- **Storage 401/403/409/429/5xx** counts by agent and identity.
- Azure Storage availability, latency, and transaction volume.
- Blob storage capacity, version count, and retention growth.
- Audit log ingestion and retention health.
- Count of **unexpected state readers/writers**.
- Pipeline changes touching backend config, roles, or networking.
- Unexpected drift/plan diff counts.
- Recovery drill success rate and measured RPO/RTO.

### 26.8. Alerting on Signs of Compromise

High-priority events:

1. State blob read by an uninventoried principal or network source.
2. `Storage Blob Data Contributor` assigned broadly outside change approvals.
3. State blob deleted or overwritten outside an approved `apply` window.
4. Diagnostic settings disabled or redirected.
5. Shared Key access re-enabled against policy.
6. Public network access expanded without approval.
7. Repeated lock failures or `force-unlock` events tied to incidents.
8. `terraform plan`/`apply` executed from an unapproved commit or runner.
9. Unexpected edits to provider versions, lockfiles, or backend configs.

A single `BlobRead` does not prove exfiltration; correlate principal, CI run, storage key, IP, change ticket, and subsequent events.

## 27. FinOps for Terraform Backends

### 27.1. Where Do Costs Come From?

| Cost Driver | Impact |
|---|---|
| Storage account Blob | State capacity and historical object versions |
| LRS/ZRS/GRS/GZRS replication | Tier/region durability pricing |
| Data-plane operations | Read, write, list, lease, and metadata requests |
| Versioning / soft delete | Retained count and size of historical state versions |
| Private Endpoint | Private Link hourly and per-GB data-processing charges |
| Azure Monitor | Log ingestion, retention, queries, and alerts |
| CI agents | Compute time for `init`/`plan`/`apply`, queuing, and parallelism |
| Network / Firewall / NAT | Egress, VPN/ExpressRoute, and supporting infrastructure |
| Backup / DR | Secondary copies, testing, and operations |
| Security governance | Access reviews, scanning, and recovery drills |

State files are small compared to data lakes, yet **version history, log ingestion, Private Endpoints, and CI compute** add up across hundreds of active stacks.

### 27.2. Example Operation Volume Estimate

Suppose 40 stacks each run 2 plans/day and 1 apply/day:

~~~text
40 stacks × (2 plans + 1 apply)
= 120 Terraform operations/day
~~~

This **does not equal 120 billable Blob transactions**. Each `init`/`plan`/`apply` triggers multiple read, list, lease, write, and metadata requests depending on backend behavior, retries, and storage responses. Measure actual Azure Storage metrics before finalizing budgets.

### 27.3. Managing Version Growth

Suppose an average of 20 state writes/day at 2 MiB per version:

~~~text
20 writes/day × 2 MiB × 30 days
≈ 1,200 MiB of version data/month
~~~

This rough estimate ignores compression, metadata, base blobs, retries, and growth. With one-year retention across many stacks, version storage grows noticeably. Tune lifecycle retention **without pruning needed recovery points**—always test restores before shortening retention.

### 27.4. Never Optimize Costs by Sacrificing Recoverability

- Never disable soft delete or versioning without an alternative backup.
- Never disable Terraform locking to "run faster".
- Never open anonymous blob access or public networking to save setup effort.
- Never dump all prod and dev states into one broad-access container solely to reduce resource count when isolation matters.
- Never purge approved historical backups before checking RPO and incident retention rules.
- Never poll `plan` every minute unless drift SLOs genuinely demand it.
- Eliminate duplicate CI runs with controlled queuing and concurrency.
- Apply budgets, tags, and Cost Management tracking to backend and monitoring resources.

### 27.5. Choosing Redundancy

Select LRS, ZRS, GRS, or GZRS from **business continuity requirements**, regional availability, storage failover procedures, and cost. Geo-redundant storage does not guarantee Terraform state stays consistent with Azure resources at every instant during a failover.

## 28. End-to-End Lab Workflow and Acceptance Criteria

### 28.1. Preparation

1. Create an approved lab subscription/resource group.
2. Create a dedicated `StorageV2` account for the Terraform backend.
3. Disable anonymous blob access; prefer Entra data-plane auth.
4. Assign `Storage Blob Data Contributor` to the lab identity at an appropriate scope.
5. Create the private **`tfstate`** container via **`--auth-mode login`**.
6. Enable versioning and soft delete per lab retention policy.
7. Verify CLI/Terraform versions and backend feature support.
8. Choose a state key **`orders/lab/app.tfstate`**.
9. Confirm no other `terraform apply` runs target that key.
10. Never use production secrets or a production subscription.

### 28.2. Terraform Project

Create **`backend.tf`** with a partial backend:

~~~hcl
terraform {
  required_version = ">= 1.6.0"
  backend "azurerm" {}
}
~~~

Create **`backend.lab.hcl`**:

~~~hcl
resource_group_name  = "rg-tfstate-lab"
storage_account_name = "stexampleiaclab001"
container_name       = "tfstate"
key                  = "orders/lab/app.tfstate"
use_azuread_auth     = true
use_cli              = true
~~~

Create **`main.tf`** with a simple resource group per Section 8 or a module tested only up to **`plan`**. Set the provider subscription ID to your lab ID, never production.

### 28.3. Init, Validate, and Plan

~~~bash
terraform fmt -check -recursive
terraform init -backend-config=backend.lab.hcl
terraform validate
terraform plan -lock-timeout=2m
~~~

Record:

- Backend storage account, container, and key (non-secret metadata).
- Active identity (controlled principal alias/object ID).
- Plan outcome.
- Network path used.
- Storage Blob data role verified.
- Observed logs and lease events.

### 28.4. Small Approved Apply

If permitted by the lab owner:

~~~bash
terraform apply -lock-timeout=2m
~~~

Review the plan carefully before confirming. Post-apply, verify state blob metadata exists and lab resources match expectations. Never print raw state JSON to the terminal.

### 28.5. Testing Locking with Two Lab Terminals

- Terminal A runs a valid operation holding a lock on the **lab state**.
- Terminal B launches a second `plan`/`apply` against the same key while A still holds the lock in a controlled scenario.
- Observe B waiting or failing with a lock conflict.
- Never pass `-lock=false` or `force-unlock` during this test.
- Once A finishes, B retries or proceeds per timeout policy.
- Record lock wait duration and sanitized error output.

**Never induce lock contention on production state** to practice locking.

### 28.6. Controlled Backend Key Change Test

In an isolated lab copy, take a safe backup and test **`terraform init -migrate-state`** per runbook. Never rename a dev key to prod just to see what Terraform does.

### 28.7. Negative Permission Tests

- Identity A has `Storage Blob Data Contributor` → backend `init`/`plan` succeeds if provider and network permissions pass.
- Identity B has only ARM Reader/Contributor without a Blob data role → backend blob access fails as expected.
- Identity C has only `Storage Blob Data Reader` → can read state, yet fails write/lease operations for `plan`/`apply`.
- Identity D has RBAC, yet connects from outside the private network → network failure / 403.
- Never auto-grant new permissions from a runtime job to bypass a failing negative test.

### 28.8. Recovery Drill on a Lab Clone

1. Enable versioning and write at least two valid state versions via Terraform runs.
2. Record backup/recovery points per policy.
3. Strictly on an approved **state clone or sandbox**, simulate state deletion or corruption.
4. Restore the candidate version via Storage recovery procedures.
5. Run `plan` to confirm resource mappings.
6. Record RPO/RTO without pasting state contents.
7. Clean up lab resources per owner and retention policy.

### 28.9. Sample Acceptance Report

| Item | Expected Outcome |
|---|---|
| Backend Storage account | Exists, owned by platform/lab |
| Container | Private, anonymous access disabled |
| Blob key | Unique per stack/environment |
| Backend authentication | Microsoft Entra ID |
| Runtime data role | `Storage Blob Data Contributor` at scoped target |
| CLI/provider subscription | Independently verified |
| `terraform init` | PASS |
| `terraform validate` | PASS |
| `terraform plan` | Expected diff / zero unexpected resources |
| Lock test | Competing operation waits or fails safely |
| Backup | Versioning and soft delete configured |
| Recovery drill | Restore + `plan` validation on clone |
| Network | Approved path, DNS/TLS valid |
| Audit | Blob diagnostic metadata available |
| Secrets in logs | None |
| Production resources modified | None |

These are **expected criteria**, not output from a run executed while writing this lesson.

## 29. Anti-Patterns: Practices That Break State

| Anti-Pattern | Consequence | Safe Alternative |
|---|---|---|
| Commit **`terraform.tfstate`** to Git | Secrets/history leak, merge conflicts | Private Azure remote state + restricted backups |
| Share one blob key across dev and prod | State collisions and cross-environment edits | Unique key/container/account per environment |
| Let app Terraform manage/destroy its own backend storage | Loss of state store and recovery | Bootstrap backend with separate lifecycle |
| Put account keys in `backend.tf` | Credential leaks via Git/plan/`.terraform` | Entra auth + scoped RBAC |
| Store account keys in CI YAML | Any authorized PR/script can read them | OIDC/managed identity + secure resources |
| Assume ARM Contributor implies Blob Data Contributor | 403 during `init`/`plan` | Assign data-plane role explicitly |
| Grant `Storage Blob Data Owner` subscription-wide | Huge blast radius | Container-scoped Data Contributor where feasible |
| Disable state locking on 409 errors | Concurrent writes and state corruption | Wait, inspect active jobs, use lock timeout |
| `force-unlock` while job A is applying | Two writers corrupt state concurrently | Break-glass runbook after verification |
| Upload empty JSON as a state blob | Backend parse error / lost mappings | Let Terraform manage state creation |
| Switch keys with `init -reconfigure` instead of migrate | New backend looks empty | `terraform init -migrate-state` |
| Restore old state version and `apply` immediately | State diverges from live resources | Freeze → inspect → restore → `plan` |
| Enable GRS without version history | Corrupted state writes replicate cleanly | Versioning/soft delete + DR |
| Put active state under strict immutability/WORM | Blocks writes and Blob leases | Separate immutable archive if required |
| Public anonymous blob access | State exposed to the internet | Disable anonymous access |
| Open storage firewall to all IPs so CI works | Exposed state endpoint | Private Endpoint / approved agent egress |
| Connect to Blob via raw private IP instead of FQDN | TLS/DNS validation fails | Use FQDN + private DNS |
| Treat Terraform workspaces as a security boundary | Principal can read other state files | Separate RBAC scopes/containers/accounts |
| Use `terraform_remote_state` to fetch API keys | Grants broader state read than needed | Managed identity + Key Vault |
| Publish `plan.bin` publicly | Sensitive values leaked | Encrypted short-lived artifact |
| Run `TF_LOG=TRACE` and paste into tickets | Exposes tokens, state, and HTTP metadata | Sanitized logs and incident protocol |
| Provider and backend point to mismatched subscriptions | Mutates wrong resources | Explicit IDs, guards, and approvals |
| Ignore drift after restoring state | State out of sync with live resources | Import/reconcile + `plan` |
| Ignore RBAC propagation delays | 403s and retry storms | IAM validation and bounded retries |
| Skip reviewing `backend.tf` diffs | Unintended state key or identity switch | Code owners and PR gates |
| Monitor only Azure Activity Log | Misses Blob data-plane operations | Enable Storage Blob diagnostics |
| Disable versioning to save pennies with no backup | Loss of recovery points | Balance RPO, retention, and FinOps |
| Reuse self-hosted runners across untrusted PRs and prod applies | Runner and credential compromise | Isolate trust boundaries |
| Force-apply a stale saved plan by breaking locks | Breaks state consistency | Re-plan and re-approve |

## 30. Backend Architecture Decision Matrix

### 30.1. Local vs. Remote?

| Scenario | Choice | Rationale |
|---|---|---|
| Short personal Terraform exercise on one laptop, unshared | Local state can suffice temporarily | Low complexity, accepted limited risk |
| Multiple people managing Azure resources | Azure Storage remote backend | Collaboration, locking, auditing, and recovery |
| CI/CD pipeline deploying shared environments | Azure Storage remote backend | Centralized source of truth |
| Untrusted PR needing `fmt`/`validate` only | `init -backend=false` for validation | Zero access to prod state needed |
| High-compliance production | Isolated account/subscription/private network backend | Minimal blast radius, full auditability |
| Critical cross-region DR | Redundancy + versioning + recovery drills | Replication alone does not replace history |
| Non-sensitive ephemeral stacks | Lifecycle-controlled keys/workspaces | Fast, though not an RBAC boundary |
| Multiple teams with separate security ownership | Separate containers/accounts and identities | Least privilege |
| App runtime needing secrets | Key Vault, **not** remote state | Secret access isolation |

### 30.2. Choosing Authentication

| Context | Recommended Method | Requirements |
|---|---|---|
| Developer local lab | Azure CLI user login + Entra blob auth | Supported backend version, Blob data role |
| Self-hosted agent on Azure VM | Managed identity | Proper identity, networking, and RBAC |
| Trusted Azure DevOps or GitHub CI | OIDC federation | Pipeline/service-connection identity and backend support |
| Legacy automation | Managed service principal cert/secret | Rotation, secure storage, migration plan |
| Account key / SAS | Legacy compatibility only with approval | Strict secret handling, never commit |
| Forked PR | No prod backend access | Static validation only |

### 30.3. Choosing Scope Isolation

**Treat storage account, container, and blob key as three distinct organizational layers:**

- **Account**: network, encryption, redundancy, and management boundary.
- **Container**: supports scoped Blob data-plane RBAC isolation.
- **Blob key**: identifies a state object, yet **is not an access boundary on its own**.

A requirement like "team app may read only one key" is not enforced merely by naming prefixes. Design proper RBAC and resource isolation.

### 30.4. Is Splitting State as Small as Possible Always Better?

Not unconditionally. Splitting too small causes:

- Excessive cross-stack dependencies.
- Complex output wiring.
- Too many CI pipelines and approvals.
- Harder coordination across cross-stack changes.

Keeping state monolithic causes:

- One `plan` touching networking, DB, and apps together.
- Contention over a single state lock.
- Overly broad RBAC roles.
- Huge blast radius on bad applies.

Draw boundaries around **ownership, deployment cadence, security, concurrency, and dependency graphs**—not raw file count.

## 31. Production Checklist

### 31.1. Bootstrap and Design

- [ ] Backend storage is bootstrapped **before** stacks that use it.
- [ ] State storage RG/account cannot be destroyed by the same stack.
- [ ] Storage name, container, and key follow conventions with zero secret coordinates.
- [ ] Each stack and environment has a unique state key.
- [ ] Prod/dev/staging isolation meets the threat model.
- [ ] Owners, tags, and platform change governance are assigned.
- [ ] Backend identifiers and recovery contacts are documented.
- [ ] Zero plaintext state exists in Git or CI artifacts.
- [ ] `StorageV2`/SKU/region/redundancy align with SLO/RPO/RTO.

### 31.2. Identity and RBAC

- [ ] Backend uses Entra auth (OIDC/managed identity/Azure CLI) where supported.
- [ ] No Storage account keys or SAS tokens stored in backend config.
- [ ] Runtime and CI principal object IDs are verified.
- [ ] `Storage Blob Data Contributor` is granted at the narrowest appropriate scope.
- [ ] Provider permissions are defined **separately** from backend permissions.
- [ ] CI `plan`/`apply` jobs run strictly under trusted identities.
- [ ] Untrusted PR jobs have zero access to production state.
- [ ] IAM role assignments and Shared Key policies are audited.
- [ ] Runbooks exist for propagation delays, token expiry, and client ID mismatches.
- [ ] Credential revocation and rotation procedures exist for exposures.

### 31.3. Blob Service and Networking

- [ ] Container is private with anonymous public access disabled.
- [ ] HTTPS/TLS policies enforced.
- [ ] Shared Key disabled once all tooling and auth support Entra auth.
- [ ] Firewalls, public network settings, and Private Endpoints are approved.
- [ ] DNS for **`privatelink.blob.core.windows.net`** resolves properly from CI agents.
- [ ] Agent egress reaches Entra, ARM, and Blob endpoints.
- [ ] Private Endpoint targets the Blob subresource specifically.
- [ ] Never bypass TLS or connect directly via raw private IP.
- [ ] Blob versioning enabled per policy.
- [ ] Blob soft delete and container recovery policies defined.
- [ ] No immutability policy breaking state writes or leases.
- [ ] Delete protection / ARM locks evaluated.
- [ ] Recovery drills and break-glass accounts/roles established.

### 31.4. Terraform and CI/CD

- [ ] Terraform CLI and `azurerm` backend versions pinned and tested.
- [ ] `.terraform.lock.hcl` properly maintained.
- [ ] Backend config avoids invalid `var`/`local` interpolations.
- [ ] PRs run `fmt`/`validate` without touching prod backend.
- [ ] `plan` targets the exact matching backend key and provider subscription.
- [ ] `apply` runs only from approved runs matching the saved plan and commit.
- [ ] CI concurrency and lock timeouts configured.
- [ ] Never pass `-lock=false` on shared state.
- [ ] `force-unlock` restricted strictly to break-glass runbooks.
- [ ] Binary plans protected like state.
- [ ] Never log raw state, full plan JSON, or sensitive outputs.
- [ ] Dedicated migration playbook for backend key changes.
- [ ] Post-migration `plan` shows zero unexpected changes.
- [ ] Import/reconciliation runbooks ready for drift or state loss.
- [ ] Never run `apply` against an unexpectedly empty state.

### 31.5. Monitoring, FinOps, and DR

- [ ] Storage Blob diagnostics enabled per policy.
- [ ] Activity Logs for ARM/network/IAM changes retained properly.
- [ ] Log workspace and table schemas tested.
- [ ] Alerts configured for unexpected Blob reads/writes/deletes and 403/409/429 spikes.
- [ ] Alerts configured for edits to public access, Shared Key policy, or diagnostic settings.
- [ ] Dashboards track Terraform `plan`/`apply`/lock wait/queue failures.
- [ ] RPO/RTO and version retention approved by owners.
- [ ] State restoration tested on a sandbox/clone.
- [ ] Incident response plan covers state tampering and credential exposure.
- [ ] Budgets and tracking cover storage versions, log ingestion, and Private Endpoints.
- [ ] Never purge state or backups prematurely before retention policy allows.
- [ ] Controlled upgrade workflow for Terraform and provider versions.
- [ ] Stop-writers checklist enforced before any restoration or migration.

## 32. Hands-On Exercises

### Exercise 1: Why Use Remote State?

Two developers share a Terraform repo; A ran `apply`, while B has no local state. Analyze:

- Why can B's `plan` be dangerous?
- How does a remote backend solve this?
- Do Blob leases guarantee live Azure resources always stay consistent?
- What data could leak if local state is committed to Git?

### Exercise 2: Bootstrapping Azure Storage

In a lab subscription:

1. Create a dedicated backend RG.
2. Create a `StorageV2` account with HTTPS/TLS enforced and anonymous public access disabled.
3. Assign `Storage Blob Data Contributor` to your lab principal.
4. Create the `tfstate` container using **`--auth-mode login`**.
5. Enable versioning and soft delete per policy.
6. Confirm the container is private.
7. Explain why the app's Terraform stack must never destroy the backend RG.

### Exercise 3: Writing the `azurerm` Backend

Create **`backend.tf`** and **`backend.lab.hcl`** with:

~~~text
resource_group_name = rg-tfstate-lab
container_name      = tfstate
key                 = orders/lab/app.tfstate
auth                = Microsoft Entra ID
~~~

Write valid HCL syntax, keep credentials out of files, and run `fmt`/`init`/`validate` in the lab.

### Exercise 4: Distinguishing Backend and Provider

The backend lives in the **platform subscription**, while app resources live in the **application subscription**. Diagram both permission sets and identities. Explain why holding Azure Contributor on the app subscription does not guarantee `terraform init` succeeds on the backend.

### Exercise 5: Container-Scoped Role

Assign `Storage Blob Data Contributor` at container scope for a lab workload instead of the full account (where supported by service/permissions). Run a negative test against a second container and record the result.

### Exercise 6: `terraform init` Migration

Suppose you have local state with 5 demo resources:

1. Freeze writers.
2. Back up state securely.
3. Prepare an empty remote backend at the right key.
4. Run **`terraform init -migrate-state`**.
5. Verify `state list` and blob metadata.
6. Run `plan` confirming no unexpected recreates.
7. Explain when never to use **`-reconfigure`** to migrate.

### Exercise 7: Collision Between Two Environments

Both dev and prod accidentally share:

~~~text
key = orders/shared/app.tfstate
~~~

Explain the failure mode and design naming/RBAC guards to block PRs from altering keys or hitting the wrong backend. Never run `apply` against production to reproduce this.

### Exercise 8: Lock Conflict

Two Terraform jobs access the same state. Job A holds the lock; Job B hits 409.

- Use **`-lock-timeout=5m`** when appropriate.
- Inspect run A.
- When should you wait?
- When is **`terraform force-unlock`** justified?
- Why is **`-lock=false`** dangerous?

### Exercise 9: Stale Plan

A trusted plan was saved at state serial N, while another job applied and bumped state to N+1. Why must you re-plan and re-approve instead of rolling state back just to apply the saved plan?

### Exercise 10: Versioning and DR

Design backups for a 2 MiB state with 20 writes/day and 30-day retention. Estimate approximate data growth, choose versioning/soft delete/replication settings, and outline a clone recovery drill.

### Exercise 11: Private DNS Error

A self-hosted CI runner inside a VNet fails to resolve **`storage.blob.core.windows.net`** via a private endpoint.

- Identify the private DNS zone.
- Check VNet links and forwarders.
- Verify the FQDN and TLS path.
- Distinguish ARM vs. Blob connectivity.
- Avoid raw private IPs or opening public internet access.

### Exercise 12: OIDC in CI

Design federated service connections for trusted `apply`. Specify:

- Principal/client ID, tenant, and trust claims.
- Blob data roles and provider permissions.
- Source branch and approval guards.
- Backend OIDC support/version.
- Why client secrets must never be committed.
- How to prevent untrusted PRs from reading prod state.

### Exercise 13: Sensitive Outputs

Terraform uses **`random_password`** or a connection string output marked **`sensitive = true`**. Explain why the state blob remains sensitive, why **`terraform_remote_state`** must not be used as a secret API, and how managed identity + Key Vault replace it.

### Exercise 14: Separating Validate / Plan / Apply in CI

Design three stages: PR static validation (`backend=false`), trusted `plan`, and approved `apply`. Detail permissions per job, plan artifact retention, and lock controls.

### Exercise 15: State Tampering

SOC detects an unknown principal writing to the state blob and modifying role assignments:

1. Halt all applies.
2. Gather Blob diagnostics, Activity Logs, and CI run evidence.
3. Audit storage RBAC.
4. Pick a blob version recovery point.
5. Reconcile live Azure resources.
6. Rotate any secrets exposed in state.
7. Write a postmortem and harden controls.

### Exercise 16: Drift and Import

An Azure Resource Group was created outside Terraform, and the app team wants to manage it in their stack. Write an import plan/block specifying resource ID and address, state review, locking, `plan`, and approvals. Avoid managing the same resource from two separate states.

### Exercise 17: Cost Growth

Compare sharing one storage account across many states against three separate accounts for dev/staging/prod. Factor in storage transactions, versions, redundancy, Private Endpoints, log ingestion, and blast radius. Justify the choice on both cost **and** security—not raw resource count alone.

### Exercise 18: Restoring the Wrong Version

An operator wants to restore yesterday's state, yet three new resources were created today. Why must you not overwrite immediately? Outline the sequence: freeze, inspect, restore-on-clone, `plan`, import/reconcile, and authorization.

## 33. Self-Check Questions

1. What information does Terraform state store?
2. Why is state not just an ordinary Git configuration file?
3. What goes wrong with a local backend when multiple engineers run `apply`?
4. Which Azure service does the `azurerm` backend use to store state?
5. How do a storage account, container, and blob key differ?
6. Does a slash inside a blob key create a folder-level security boundary?
7. How does the Terraform backend differ from the `azurerm` provider?
8. Why must backend authentication and provider authentication be verified separately?
9. Can an identity holding Azure Contributor automatically read/write Blobs?
10. Is **`Storage Blob Data Reader`** sufficient for Terraform to lock and write state?
11. Why is **`Storage Blob Data Contributor`** highly sensitive?
12. When should RBAC be scoped to a container instead of the entire account?
13. How does Azure CLI login differ from OIDC CI authentication?
14. Why must `access_key`, SAS tokens, and `client_secret` never be committed in `backend.tf`?
15. What does **`use_azuread_auth`** mean?
16. When do you use **`use_cli`** vs. **`use_oidc`**?
17. Why doesn't the `backend` block accept **`var.state_key`**?
18. What problem does partial backend configuration solve?
19. Why must backend storage be bootstrapped beforehand?
20. Why should the Orders API stack never destroy its own state storage?
21. What does **`terraform init`** do?
22. How does **`terraform init -migrate-state`** differ from **`-reconfigure`**?
23. If switching keys causes Terraform to see an empty state, should you run `apply`?
24. Does a passing `terraform init` prove the provider has permissions to create resources?
25. Why can **`terraform plan -out`** produce a sensitive artifact?
26. Should **`terraform state pull`** ever be printed to CI logs?
27. Does **`sensitive = true`** encrypt or strip an output from state?
28. Why can **`terraform_remote_state`** expose more data than just outputs?
29. What problem do Blob lease locks prevent?
30. How does `-lock-timeout` differ from `-lock=false`?
31. When is **`terraform force-unlock`** appropriate?
32. Why is running `force-unlock` during an active `apply` dangerous?
33. Which scenarios do blob versioning and soft delete protect against?
34. Can geo-replication recover from logically corrupted state writes?
35. When restoring an older state version, why compare it against live Azure resources?
36. How does an Azure Resource Lock differ from a Terraform state lock?
37. Why shouldn't you enable an immutable WORM policy casually on active state?
38. When storage uses a Private Endpoint, which hostname does Terraform connect to?
39. What is the standard Private DNS zone for Azure Blob?
40. Why might a Microsoft-hosted agent fail to reach a private Blob endpoint?
41. Are an Entra token and valid RBAC enough when a firewall denies access?
42. What scenarios trigger 403 errors from the Blob backend?
43. How should you handle a 409 / lease conflict error?
44. Why does OIDC reduce long-lived credential risks in CI?
45. When should untrusted PRs run `terraform init -backend=false`?
46. How does `.terraform.lock.hcl` differ from a state lease lock?
47. Which log source records Blob data-plane operations?
48. Does the Azure Activity Log capture every read of a `tfstate` blob?
49. What drivers increase backend costs beyond raw state file size?
50. When might a remote Azure Storage backend not be worth the cost or complexity?

## 34. References

- [Terraform azurerm backend — HashiCorp](https://developer.hashicorp.com/terraform/language/backend/azurerm)
- [Terraform backend configuration](https://developer.hashicorp.com/terraform/language/backend)
- [Terraform state overview](https://developer.hashicorp.com/terraform/language/state)
- [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking)
- [terraform init command](https://developer.hashicorp.com/terraform/cli/commands/init)
- [terraform force-unlock](https://developer.hashicorp.com/terraform/cli/commands/force-unlock)
- [Terraform CLI state commands](https://developer.hashicorp.com/terraform/cli/commands/state)
- [Terraform remote state data source](https://developer.hashicorp.com/terraform/language/state/remote-state-data)
- [Terraform workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)
- [Terraform dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock)
- [Store Terraform state in Azure Storage — Microsoft Learn](https://learn.microsoft.com/azure/developer/terraform/store-state-in-azure-storage)
- [Authenticate Terraform to Azure](https://learn.microsoft.com/azure/developer/terraform/authenticate/authenticate-to-azure)
- [Azure Blob Storage introduction](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Authorization for Blob data with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Assign an Azure role for access to Blob data](https://learn.microsoft.com/azure/storage/blobs/assign-azure-role-data-access)
- [Azure Storage authorization overview](https://learn.microsoft.com/azure/storage/common/authorize-data-access)
- [Prevent Shared Key authorization for Azure Storage](https://learn.microsoft.com/azure/storage/common/shared-key-authorization-prevent)
- [Azure Storage private endpoints](https://learn.microsoft.com/azure/storage/common/storage-private-endpoints)
- [Storage networking and firewalls](https://learn.microsoft.com/azure/storage/common/storage-network-security)
- [Blob versioning overview](https://learn.microsoft.com/azure/storage/blobs/versioning-overview)
- [Soft delete for blobs](https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview)
- [Concurrency management and Blob leases](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage)
- [Azure Storage redundancy](https://learn.microsoft.com/azure/storage/common/storage-redundancy)
- [Monitor Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/monitor-blob-storage)
- [Azure Monitor diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings)
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log)
- [Azure Monitor reference: StorageBlobLogs](https://learn.microsoft.com/azure/azure-monitor/reference/tables/storagebloblogs)
- [Azure Blob Storage pricing](https://azure.microsoft.com/pricing/details/storage/blobs/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Azure DevOps Pipelines](https://learn.microsoft.com/azure/devops/pipelines/)
- [Azure service connections](https://learn.microsoft.com/azure/devops/pipelines/library/service-endpoints)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
