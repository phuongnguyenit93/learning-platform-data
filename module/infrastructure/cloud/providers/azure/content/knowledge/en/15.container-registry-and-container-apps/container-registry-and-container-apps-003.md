# Authenticating to a Registry with RBAC and Managed Identity

In the **CLOUD_PROVIDERS_AZURE** module, we explore Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data services, while learning how to deploy, monitor, secure, and control costs for an application architecture on Azure. In the **Container Registry and Container Apps** chapter, the core focus is securing the container image supply: **who is allowed to push, who is allowed to pull, from which repository, and using which identity?**

For example, a development team builds the `orders-api` image and pushes it to **Azure Container Registry (ACR)**. A production **Azure Container Apps** workload needs to pull that exact image when creating a new revision or scaling out replicas. If a registry administrator account is used and its password is placed into application configuration, a leak could expose broad access to images across the entire system. A better solution is using **Microsoft Entra ID + Azure RBAC**, combined with a **managed identity** for workloads running on Azure.

After this lesson, you will be able to:

- Distinguish **authentication** and **authorization** in ACR, as well as the control plane and data plane.
- Understand ACR sign-in options: Entra ID, managed identity, service principal/federated identity, and registry admin account.
- Choose **pull**, **push**, and repository management permissions matching the two authorization modes: registry-level RBAC and repository-level **RBAC + ABAC**.
- Grant permissions to a **user-assigned managed identity**, then configure Azure Container Apps to pull private images without storing registry passwords.
- Troubleshoot `401 Unauthorized`, `403 Forbidden`, incorrect image names, expired tokens, and DNS/firewall errors.
- Apply least privilege, logging, permission rotation workflows, testing, and cost control.

## 1. Azure Container Registry and Objects to Protect

**Azure Container Registry (ACR)** is an Azure-managed registry service for storing and distributing container images along with supported OCI artifacts. When building Java, Node.js, or .NET applications into containers, development teams can push artifacts to ACR; App Service, Container Apps, AKS, Azure Container Instances, or other tools then pull the artifacts to run.

A registry with an example resource name `acrordersdev001` typically has a **login server** formatted as:

```text
acrordersdev001.azurecr.io
```

Images are identified by repository, tag, or digest:

```text
acrordersdev001.azurecr.io/orders/api:1.4.2
acrordersdev001.azurecr.io/orders/web:1.2.0
acrordersdev001.azurecr.io/orders/api@sha256:<digest>
```

Where:

| Component | Example | Meaning |
|---|---|---|
| Registry | `acrordersdev001` | Azure resource storing and serving artifacts |
| Login server | `acrordersdev001.azurecr.io` | Endpoint to which Docker/OCI clients connect |
| Repository | `orders/api` | Collection of manifests/tags for an image inside the registry |
| Tag | `1.4.2` | Convenient reference name; target can change if uncontrolled |
| Digest | `sha256:...` | Hashed manifest content identifier, suitable for pinning exact artifacts |
| Manifest/layers | OCI image contents | Actual data the client must download when pulling |

**Pull** downloads the manifest and required layers; **push** uploads manifests/layers or new image versions to the registry. Operations such as deleting tags, deleting repositories, listing the catalog, and modifying registry settings do not automatically share the same permissions.

### 1.1. Map of the Build → Registry → Application Flow

```text
Developer / CI pipeline
       |
       | 1. Entra ID / workload identity
       | 2. Permitted to push to required repository
       v
Azure Container Registry
       |    acrordersdev001.azurecr.io/orders/api:1.4.2
       |
       | 3. Container Apps uses managed identity
       | 4. RBAC/ABAC permits pull
       v
Azure Container Apps environment
       |
       +-- Container App: orders-api
            +-- Revision: image 1.4.2
            +-- Replica 1
            +-- Replica 2
```

This is the logical model. For deployment to succeed, the network path to ACR, DNS, Container Apps environment, image tag/digest, and identity permissions must also be correct.

## 2. How Does Authentication Differ from Authorization?

**Authentication:** proves who an actor is. For example, a developer signs in to Azure CLI with Microsoft Entra ID, or a Container App uses a managed identity to obtain a token for accessing ACR.

**Authorization:** determines what an authenticated actor can do. An identity that successfully signs in may still have **no pull permission** or **no push permission** on a repository.

```text
User / workload identity
          |
          v
Microsoft Entra ID authenticates
          |
          v
Obtains appropriate token and sends request to ACR
          |
          v
ACR evaluates role assignments + repository conditions
          |
          +-- Authorized for action/resource -> allow
          |
          +-- Insufficient permissions -> deny
```

A login token for the Azure Portal does not automatically make all Docker operations permitted. The ACR client needs an authentication mechanism compatible with the registry, and the Entra principal needs data permissions at the proper scope.

### 2.1. Control Plane and Data Plane

Azure distinguishes two categories of operations:

| Plane | Examples | Permission Type |
|---|---|---|
| **Control plane** (managing Azure resources) | Create ACR, change SKU, configure networking, create role assignments | Azure Resource Manager operations and corresponding management roles |
| **Data plane** (registry contents) | Pull image, push image, read repository manifest, manipulate artifacts | Registry/repository permissions under ACR RBAC or RBAC + ABAC mechanisms |

A user might be permitted to **view ACR configuration details** in the Azure Portal yet not be allowed to pull images. Conversely, a pipeline might be allowed to **push images** yet not be allowed to alter registry firewalls or grant permissions to others.

**Common mistake:** assigning `Owner` or `Contributor` over an entire resource group just to fix a Docker pull error. This needlessly expands administrative privileges and is not the right solution for all repository permission modes.

## 3. Ways to Authenticate to ACR

### 3.1. Microsoft Entra ID for Users

Developers typically sign in interactively:

```bash
az login
az account set --subscription "<subscription-id>"
az acr login --name acrordersdev001
```

`az acr login` uses the Entra ID identity currently signed in to Azure CLI to execute the registry login flow and, when the Docker CLI/daemon is available, configures Docker login. A successful login command **does not prove** the developer can push to every repository: permissions are evaluated during the actual operation.

Some environments without a Docker daemon can use an appropriate token mode in Azure CLI/OCI clients; review the documentation and never print tokens to the terminal, log files, or pipeline output.

### 3.2. Managed Identity for Azure Workloads

A **managed identity** is a Microsoft Entra identity managed by Azure for supported Azure resources. Workloads use this identity to obtain tokens **without storing a client secret or password in app settings**.

There are two types:

- **System-assigned managed identity:** tied to the lifecycle of the host resource; deleting the resource typically deletes the identity.
- **User-assigned managed identity:** an independent identity resource that can be assigned to one or more workloads per supported features; its lifecycle does not depend on a single Container App.

For the Container Apps pulling images from ACR flow, a **user-assigned managed identity** often makes it easier to prepare permissions before creating the Container App and reuse them in a controlled way. System-assigned identities are also supported in suitable workflows/products, though they may require a different order of app creation and registry configuration, especially if a private image must be pulled during initial app creation.

Managed identity **only provides a way to obtain an identity/token**; it **does not automatically grant `AcrPull`**, does not open firewalls, does not configure image names, and does not replace supply chain security policies.

### 3.3. Service Principal and Workload Identity Federation

CI/CD pipelines running outside Azure or requiring an independent application identity can use a **service principal** and appropriate role assignments.

- With a **client secret/certificate**, the pipeline must protect and manage the credential lifecycle.
- With **workload identity federation / OIDC**, a supported CI/CD provider can exchange trusted tokens with Microsoft Entra ID via a federated credential; this approach typically reduces the need to store long-lived client secrets.

If CI runs on an Azure service supporting managed identity, you can use a managed identity instead of a secret. If CI runs on GitHub Actions or external systems, consider OIDC federation with an appropriate scope instead of using a registry admin password.

### 3.4. Registry Admin User and Registry Tokens

ACR has a registry-level username/password **admin account** in supported configurations. This is a convenience mechanism for testing or compatibility, but it carries broad permissions and is not an ideal model for production.

ACR also provides **repository-scoped tokens and scope maps** in supported SKUs/features. They can serve clients unable to use Entra ID, yet they remain standalone credentials that must be protected, scoped, rotated, and revoked. **A repository-scoped token is not a managed identity**, nor does it become an Azure RBAC role.

| Option | Benefits | Risks / Considerations |
|---|---|---|
| Entra user + `az acr login` | Convenient for developers, tied to organizational identity | Do not use interactive login for production workloads |
| Managed identity | No registry password stored in Azure workloads | Requires correct role and host service support |
| Service principal + OIDC | Suits external CI/CD | Requires configuring federation, trust conditions, and roles |
| Service principal + secret | Compatible with many tools | Secret can leak; requires rotation |
| Registry admin account | Simple in some labs | Broad privileges; hard to attribute to individual identity |
| Repository-scoped token | Scope-map permissions on registry where supported | Independent credential requiring secure management |

**Recommendation:** use Entra ID for users; use managed identity for Container Apps; use managed identity or federation for CI/CD when applicable. Avoid using the admin account as the default solution.

## 4. Azure RBAC for Azure Container Registry

Azure RBAC assigns a **role** to a **principal** at a **scope**. A principal can be a user, group, service principal, or managed identity.

```text
Role assignment
   ├── Principal: <managed-identity-object-id>
   ├── Role:      AcrPull (traditional registry RBAC model)
   └── Scope:     /subscriptions/.../registries/acrordersdev001
```

Relevant roles when the registry uses **RBAC Registry Permissions** mode:

| Role | Typical Data Plane Operations | Use Case |
|---|---|---|
| `AcrPull` | Pull permitted images and artifacts from the registry | Container Apps or workloads that only run images |
| `AcrPush` | Push and pull within the role's permission scope | Build/publish image pipelines |
| `AcrDelete` | Delete registry content per role permissions | Approved artifact cleanup tasks |
| `AcrImageSigner` | Image signing operations per corresponding capabilities/features | Specialized signature management, not routine pull/push roles |

**Do not assign `AcrPush` to a runtime that only needs `pull`.** A compromised identity with push permissions poses the risk of pushing tampered artifacts to the registry if the deployment system does not strictly enforce tags/digests.

### 4.1. Registry-Level RBAC Is Not Always Repository-Level Isolation

In the traditional registry RBAC model, `AcrPull` and `AcrPush` are typically assigned at the **registry scope**, granting permissions across repositories in the registry per role. If a registry holds images from multiple teams, assigning a broad registry-level role may exceed least privilege requirements.

Example:

```text
acrsharedprod.azurecr.io
  ├── payments/api
  ├── orders/api
  └── hr/reporting
```

The `orders-api` app should only pull `orders/api`. Using broad `AcrPull` across the whole registry could grant the identity the ability to pull other repositories even though the app does not need them. When repository-level segmentation is needed, evaluate **RBAC + ABAC Repository Permissions mode** or design separate registries along security boundaries.

## 5. Two ACR Authorization Modes: RBAC and RBAC + ABAC

This is a critical point for modern ACR. A registry can be configured with a service-supported **role assignment permissions mode**. The selected mode determines which roles are used for data operations.

### 5.1. RBAC Registry Permissions (Registry-Level Style)

- Uses familiar registry roles such as `AcrPull` and `AcrPush`.
- Permissions typically apply across the registry scope; granular per-repository restrictions cannot be expressed via those legacy roles.
- Suitable when registries are already separated along a single workload/team boundary and detailed repository policies are unnecessary.

### 5.2. RBAC Registry + ABAC Repository Permissions

**ABAC (Attribute-Based Access Control)** allows applying conditions based on **repository name** to specialized ACR repository roles where supported. The goal is to continue using Entra ID principals/role assignments while scoping actions by repository rather than opening the entire registry.

Key roles to know in this mode:

| Repository Role | Primary Role | When to Choose |
|---|---|---|
| `Container Registry Repository Reader` | Pull/read artifacts per scope and condition | Runtimes that only pull images |
| `Container Registry Repository Writer` | Push and read artifacts per supported permissions | Build/publish pipelines |
| `Container Registry Repository Contributor` | Broader artifact management operations, potentially including delete per supported permissions | Approved repository maintenance tasks |
| `Container Registry Repository Catalog Lister` | List repository names at the registry level per supported mechanism | Only when catalog discovery is needed |

When a registry uses **ABAC repository permissions mode**, do not assume legacy `AcrPull`/`AcrPush` continue granting identical data permissions. You must **verify the mode, choose the corresponding role, and configure conditions properly**. Catalog permissions also differ from pulling an image whose name is already known; do not grant Catalog Lister merely because a workload needs to pull a specific image.

Target policy example:

| Principal | Role | Repository Condition | Desired Permission |
|---|---|---|---|
| `mi-orders-api-prod` | Repository Reader | `orders/api` | Pull only the orders API image |
| `ci-orders-build` | Repository Writer | `orders/api` | Push builds into the API repository |
| `ci-payments-build` | Repository Writer | `payments/api` | Cannot push into `orders/api` |
| `registry-maintainers` | Repository Contributor | Approved repository scope | Maintain artifacts per workflow |

ABAC conditions are configured on the **role assignment** and must follow syntax, attributes, and actions supported by ACR/Azure RBAC. You cannot simply write a repository name in the role description field and treat it as an enforced restriction.

### 5.3. Which Mode Should You Choose?

| Need | Design Direction |
|---|---|
| Each registry belongs to one team; pull/push managed at registry level | RBAC Registry Permissions may suffice |
| One registry shared across multiple teams needing per-repository authorization | RBAC + ABAC Repository Permissions |
| Legacy client cannot use Entra ID and requires custom scope | Consider repository-scoped tokens/scope maps per SKU, with credential controls |
| Strict isolation by environment, network, or billing | Consider multiple registries rather than relying solely on role conditions |

**Note when switching modes:** changing modes can cause existing role assignments to stop granting data permissions as expected. Before enabling or switching, inventory every pull/push client, pipeline, service principal, managed identity, and login method; plan role transitions and test in an appropriate environment. Never change the mode on a production registry just to troubleshoot an unverified `403`.

### 5.4. Example Creating a Conditional Role Assignment

When using the Azure Portal in ABAC mode:

1. Open the **Azure Container Registry** to manage and confirm **Role assignment permissions mode**.
2. Go to **Access control (IAM)** and select **Add role assignment**.
3. Select a specialized repository role, such as **Container Registry Repository Reader**.
4. Select the application's **managed identity** as the principal.
5. In the **Conditions** step, define the repository condition using the UI/Azure RBAC supported options, e.g., only `orders/api`.
6. Review the condition expression, principal, and scope; apply, wait for RBAC propagation, and test **that the permitted repository can be pulled and another repository is denied**.

Do not use an improvised CLI command with an unverified ABAC condition, as a faulty expression can accidentally grant overly broad access or no access at all. For production, manage role assignments + conditions using tested IaC/API versions, with change reviews and negative test cases.

## 6. Managed Identity: Choosing an Identity and Understanding the IDs

A user-assigned managed identity has at least three identifiers that learners often confuse:

| Attribute | Illustrative Example | Used For |
|---|---|---|
| **Resource ID** | `/subscriptions/.../userAssignedIdentities/mi-orders-acr-pull` | Assigning the identity to an Azure Container App |
| **Principal ID / Object ID** | UUID of the corresponding service principal in the Entra tenant | Selecting the principal when creating an Azure RBAC role assignment |
| **Client ID** | Application UUID of the managed identity | Selecting the identity in SDK/token-acquisition flows when needed |

Do not use **Client ID** in place of **Object ID** in `--assignee-object-id`, and do not use **Principal ID** in place of **Resource ID** when the CLI expects `--user-assigned` or `--identity` as an Azure resource.

### 6.1. System-Assigned or User-Assigned for Container Apps?

| Criterion | System-Assigned | User-Assigned |
|---|---|---|
| Lifecycle | Tied to the Container App | Independent resource |
| Pre-provisioning permissions before app creation | Harder because the principal does not exist until the app is created | Easy: create identity and assign RBAC beforehand |
| Shared across multiple apps | No: bound to one resource | Possible, though blast radius must be considered |
| Best suited for | Existing apps or workflows supporting post-creation role assignment | Bootstrapping private image pulls, IaC CI/CD environments |
| Risk | Deleting the app removes the identity and breaks associated role mappings | Sharing an identity can create excessive permissions if boundaries are not separated |

For production, **not every app has to share the same user-assigned identity**. If apps belong to different data zones, consider separate identities and dedicated role conditions so a compromised app cannot pull sensitive images belonging to another app.

## 7. Overall Workflow: Container App Pulling a Private Image

A standard deployment path:

```text
1. ACR already holds image orders/api:1.4.2
                    |
2. Create user-assigned managed identity
                    |
3. Grant pull role matching ACR mode/scope/repository
                    |
4. Attach identity to Azure Container App
                    |
5. Configure registry server + identity (no password)
                    |
6. Set Container App image reference
                    |
7. Azure acquires token from managed identity, verifies ACR permissions
                    |
8. Revision/replica pulls image and runs
```

Steps 3 and 7 are where authorization is enforced. If the image tag/digest is wrong, the registry endpoint is blocked, or the Container App lacks the right identity attachment, a role assignment alone is insufficient.

**Security boundary:** the identity used to **pull images** does not have to be the same identity that code inside the container uses to call Key Vault, Storage, or databases. To minimize excess privileges, separate artifact pull permissions from application data access permissions, even though a single identity could technically serve multiple purposes.

## 8. Azure CLI Practice: Granting ACR Permissions to a Managed Identity

This hands-on section uses **Bash in Azure Cloud Shell or a machine with Azure CLI**. The sample commands demonstrate a registry in **traditional RBAC Registry Permissions mode**; **do not run the `AcrPull` assignment snippet verbatim on a registry configured with RBAC + ABAC mode**, because the data role must change to match the mode and may require a repository condition.

Assumptions:

- ACR `acrordersdev001` exists with image `orders/api:1.4.2` already pushed.
- Resource group `rg-orders-dev` contains the ACR, or the operator knows the registry's resource group.
- Resource group `rg-orders-app-dev` holds identities and Container Apps.
- The person running commands has permission to create managed identities and **permission to assign Azure RBAC roles** on the ACR (e.g., appropriate role assignment management rights), not just registry read rights.
- A **Container Apps environment** `cae-orders-dev` exists in the right region and network; or the operator prepares the environment via a separate workflow before deploying the app.
- Appropriate permissions to create Container Apps, sufficient quota, and proper firewall/DNS. All commands are practiced strictly on approved dev resources.

### 8.1. Confirm Registry, Subscription, and Mode

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

ACR="acrordersdev001"
ACR_RG="rg-orders-dev"
APP_RG="rg-orders-app-dev"
LOCATION="southeastasia"
IDENTITY="mi-orders-acr-pull-dev"
CONTAINERAPP="ca-orders-api-dev"
ENVIRONMENT="cae-orders-dev"

ACR_ID=$(az acr show \
  --resource-group "$ACR_RG" \
  --name "$ACR" \
  --query id --output tsv)

LOGIN_SERVER=$(az acr show \
  --resource-group "$ACR_RG" \
  --name "$ACR" \
  --query loginServer --output tsv)

az acr show \
  --resource-group "$ACR_RG" \
  --name "$ACR" \
  --query "{name:name,loginServer:loginServer,sku:sku.name,adminUserEnabled:adminUserEnabled,id:id}" \
  --output json
```

**Before assigning roles:** in ACR → **Access control (IAM)** or the registry permissions settings supported by Azure Portal/CLI, verify whether the registry uses **RBAC Registry Permissions** or **RBAC Registry + ABAC Repository Permissions**. Do not infer the mode solely from the SKU or resource name. If ABAC mode is enabled, follow the repository role guidance in Section 5 rather than running the `AcrPull` snippet below.

### 8.2. Create the User-Assigned Managed Identity

```bash
az identity create \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --location "$LOCATION"

UAMI_RESOURCE_ID=$(az identity show \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --query id --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --query principalId --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group "$APP_RG" \
  --name "$IDENTITY" \
  --query clientId --output tsv)
```

The three variables serve three different contexts:

- `UAMI_RESOURCE_ID`: attaches the identity to the Azure Container App.
- `UAMI_PRINCIPAL_ID`: serves as the **assignee object ID** for the role assignment.
- `UAMI_CLIENT_ID`: can be used to select the identity when code/SDK acquires tokens, if needed by the application.

Inspecting the identity does not imply pull permissions exist; at this stage Azure has only created the principal and has not granted ACR data plane permissions.

### 8.3. Grant Exact Pull Permissions for Registry-Level RBAC Mode

**Only for registries using RBAC Registry Permissions mode:**

```bash
az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
```

This command does not grant `AcrPush`, does not create a password, and does not modify the registry admin user. The scope is the **ACR resource**, not the entire subscription or resource group. Still, `AcrPull` at the registry level can allow pulling multiple repositories within the registry: that is why ABAC or separate registries are needed when strict isolation is required.

Verify assignments:

```bash
az role assignment list \
  --scope "$ACR_ID" \
  --assignee "$UAMI_PRINCIPAL_ID" \
  --output table
```

Role assignments may take time to propagate; if a pull fails immediately after creation, verify the role, mode, and wait for propagation before repeatedly adding extra permissions.

**If ACR uses RBAC + ABAC Repository Permissions mode:** replace step 8.3 with the **Container Registry Repository Reader** role with a condition restricting `orders/api`. You must implement valid Azure RBAC condition syntax via the Portal or tested IaC; do not assume the legacy `AcrPull` command suffices. If the runtime also needs to list the catalog for discovery, evaluate permissions separately for that task; pulling a known image name does not inherently require registry-wide catalog permissions.

### 8.4. Verify the Image Actually Exists

With a **developer or pipeline identity granted appropriate permissions** to inspect images, you can run:

```bash
az acr repository show-tags \
  --name "$ACR" \
  --repository orders/api \
  --output table
```

This command executes under **the current Azure CLI identity**, not to test the managed identity created in step 8.2. If the CLI identity lacks repository permissions, the command may fail even when the workload identity has permission. Do not use this check to conclude that Container Apps is configured properly.

Build the image reference:

```bash
IMAGE="$LOGIN_SERVER/orders/api:1.4.2"
```

To reproduce production accurately and reduce tag overwrite risks, consider pinning the image by **digest** rather than relying solely on a mutable tag. Pipelines must verify the built manifest, provenance, and image security policies, not just the tag name.

## 9. Configuring Azure Container Apps to Pull ACR with Managed Identity

Azure Container Apps has per-app **registry authentication** configuration. The objective is to link the **ACR login server** to an **identity with pull permissions**, rather than placing an admin password inside Container App secrets.

### 9.1. Creating a New Container App

In supported environments, Azure CLI lets you specify the user-assigned identity while creating the Container App:

```bash
# Assumes Container Apps environment already exists and image is accessible.
az containerapp create \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --user-assigned "$UAMI_RESOURCE_ID" \
  --registry-server "$LOGIN_SERVER" \
  --registry-identity "$UAMI_RESOURCE_ID" \
  --ingress internal \
  --target-port 8080
```

Conditions:

- The CLI and **Azure Container Apps extension** must support these parameters in the installed version.
- `--user-assigned` attaches the identity to the app; `--registry-identity` instructs it to use that identity when authenticating to ACR.
- `--ingress internal` is only appropriate if the workload needs internal access within the Container Apps environment topology; it does not automatically make the entire environment or ACR private.
- `--target-port 8080` is only valid if the container actually listens on port 8080. If the app does not need HTTP ingress, select an appropriate ingress configuration instead of opening a sample port.
- The assigned ACR role and network/registry authentication must allow pulling at the moment the revision is created.

If the CLI/feature does not support this combined bootstrap flow, you can use the **Azure Portal** to create the Container App with an existing user-assigned identity, pick the image from ACR, and configure identity-based registry authentication. Never use the admin account simply to bypass bootstrap requirements.

### 9.2. Attaching an Identity to an Existing Container App

When a Container App already exists, you can attach the user-assigned identity first:

```bash
az containerapp identity assign \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --user-assigned "$UAMI_RESOURCE_ID"
```

Then declare the registry server and corresponding identity:

```bash
az containerapp registry set \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --server "$LOGIN_SERVER" \
  --identity "$UAMI_RESOURCE_ID"
```

This configures the ACR credential source for the Container App **without passing `--username` or `--password`**. If the Container App already uses a private image and cannot yet spin up a revision, ensure the bootstrap sequence and pull permissions are ready.

Verify the registry configuration:

```bash
az containerapp registry list \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --output json

az containerapp identity show \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --output json
```

Verify the login server, identity resource ID, and absence of unnecessary username/password entries. When modifying a registry identity, check other existing registry entries to avoid unintentionally altering another workload's configuration.

### 9.3. Updating Image and Revision

Once the role and registry configuration are correct:

```bash
az containerapp update \
  --name "$CONTAINERAPP" \
  --resource-group "$APP_RG" \
  --image "$IMAGE"
```

Container Apps manages **revisions** per service mechanics. Updating the template/image may create a new revision; observe provisioning state, replicas, health, and traffic splitting before shifting all production traffic.

For critical releases, tie the image tag/digest to a build ID and rollback capability. **Managed identity only proves the workload has pull rights**; it does not prove the image passed security scans, contains no vulnerabilities, or is an approved release.

### 9.4. Verifying Role Assignments and Policies on ACR

If the Container App reports failure to pull the image:

1. Confirm the **Container App actually has the identity attached** with Resource ID `UAMI_RESOURCE_ID`.
2. Confirm the registry configuration points to the exact `LOGIN_SERVER` and that identity.
3. Confirm the identity's principal ID holds the **role matching the ACR mode** and exact repository condition.
4. Confirm the image repository/tag/digest exists and has not been deleted.
5. Inspect Azure Container Apps revision/provisioning events alongside ACR logs, DNS, firewall, and private endpoint settings.

If a Container App uses a **system-assigned identity**, the identity must exist before a role can be assigned to its principal ID. The creation/assignment/image-setting order can differ from a user-assigned identity; this does not mean system-assigned identities are unsupported across all scenarios.

## 10. Build/Push Pipelines: Never Use Runtime Permissions for CI

Permissions for the **pipeline building images** differ from permissions for the **Container App running images**. A pipeline may need `push` permissions to a repository; the Container App only needs `pull`.

```text
Git repository / CI
      |
      | Workload identity federation or appropriate service principal
      | Push permissions per registry mode
      v
ACR/orders/api:1.4.2
      |
      | Container App's user-assigned managed identity
      | Pull permissions per registry mode
      v
Container Apps (runtime)
```

### 10.1. Example Developer Push Using Entra ID

Assuming the developer has push permission on the repository and a running Docker daemon:

```bash
az login
az account set --subscription "<subscription-id>"
az acr login --name "$ACR"

# Image was built on developer/pipeline machine.
docker tag orders-api:1.4.2 "$LOGIN_SERVER/orders/api:1.4.2"
docker push "$LOGIN_SERVER/orders/api:1.4.2"
```

The `docker push` command requires data permissions per the **current registry mode**. If the developer only holds `AcrPull` or Repository Reader, the push will be denied even if `az acr login` succeeded.

### 10.2. Granting Least-Privilege Pipeline Permissions

In **RBAC Registry Permissions mode**, a pipeline can use the `AcrPush` role at the registry scope if truly needed. In **ABAC mode**, use **Container Registry Repository Writer** with a condition restricting it to the exact repository. Do not grant repository Contributor or Owner just so a pipeline can push an image.

Some pipelines also need to read tags, delete old artifacts, or list the catalog; those permissions must be evaluated and granted separately per task. Never use a denied `az acr repository list` step as justification to automatically grant registry-wide push/delete permissions.

### 10.3. Federated Credentials Instead of Client Secrets

For CI platforms supporting OIDC, the general workflow is:

1. Create an Entra application/service principal or a federation-capable identity per architecture.
2. Configure a **federated credential** with issuer, subject, and audience matching the trusted repository/branch/environment.
3. Assign the narrowest ACR data role and repository condition if using ABAC mode.
4. The pipeline exchanges its OIDC token for an Entra access token and signs in to ACR via supported commands/tools.
5. Push the image, record the digest and build metadata; do not store registry passwords in CI secrets.

Do not allow every branch or every repository in federation trust conditions when only one protected environment is permitted to publish production images. Identity federation trust conditions and ACR data-plane permissions are **two separate layers of defense**.

## 11. Repository-Based Authorization: Multi-Team Design Example

A registry is shared among multiple teams:

```text
acrplatformprod.azurecr.io
  ├── orders/api
  ├── orders/web
  ├── payments/api
  └── reports/worker
```

Requirements:

- Container App orders-api only pulls `orders/api`.
- Container App payments-api only pulls `payments/api`.
- The orders pipeline can push `orders/api` and `orders/web`, and cannot modify payments.
- The audit team can view lists of required repositories without pushing or deleting.

Reference design when the registry uses **RBAC + ABAC Repository Permissions mode**:

| Principal | Role | Condition |
|---|---|---|
| `mi-orders-api-prod` | Container Registry Repository Reader | Repository = `orders/api` |
| `mi-payments-api-prod` | Container Registry Repository Reader | Repository = `payments/api` |
| `ci-orders-prod` | Container Registry Repository Writer | Repository in set `orders/api`, `orders/web` per supported condition syntax |
| `auditors` | Read/catalog permissions required for duty | Limited strictly to approved audit scope and tasks |

**Mandatory testing:** verify identities can pull their permitted repo yet **cannot** pull another team's repo, cannot push with Reader only, cannot delete with build/pull rights only, and cannot modify their own IAM permissions. These "deny" tests prove the boundary is implemented properly.

If **different network isolation, encryption keys, or lifecycle policies** are required between orders and payments, repository-level ABAC may be insufficient: consider placing them in **separate registries**.

### 11.1. When Is Catalog Lister Permission Needed?

A container runtime that already knows the image name `acrplatformprod.azurecr.io/orders/api:1.4.2` typically only needs pull operations. A discovery tool calling APIs to list all repositories may need a dedicated catalog role in ABAC mode.

Granting catalog listing exposes **repository names**, even if it does not allow pulling every manifest. Therefore, assign `Container Registry Repository Catalog Lister` only to tasks with a concrete justification, never to all runtimes.

## 12. Network Security: Having the Role Can Still Fail to Pull

ACR can be protected by **firewall/network rules**, private endpoints, DNS, and other networking controls depending on SKU/capabilities. An Azure Container App with `pull` permissions that **lacks a network path** to the registry will still fail to download images.

Diagram illustrating a private registry:

```text
Container Apps environment
         |
         | Outbound via supported VNet/route
         v
Private DNS resolution
         |
         v
ACR private endpoint (private IP)
         |
         v
Azure Container Registry
         |
         +-- Verify identity + RBAC/ABAC repository permissions
```

Layers to inspect:

1. **DNS:** the registry login server and required data endpoints must resolve properly per the private endpoint model. Configure appropriate private DNS zones/links, custom DNS, or resolvers.
2. **Networking:** do the Container Apps environment, VNet/subnet, UDRs, NSGs, Azure Firewall/NAT, and outbound rules allow HTTPS/TCP 443 to ACR endpoints?
3. **Registry firewall:** does ACR restrict public access or allow only private endpoints? Are other policies blocking source IPs or paths?
4. **Identity:** does the Container App use the correct identity and role matching the permissions mode?
5. **Artifact:** does the image tag/digest exist and permit downloading manifests/layers?

**Do not open ACR public network access to the entire Internet just to troubleshoot an unverified pull error.** Separate network issues from authorization issues; when firewall adjustments are strictly necessary for testing, perform them in a test environment with a plan to restore secure configuration.

### 12.1. ARM Audience Token for Managed Identity

In certain ACR configurations, supporting token authentication with an **Azure Resource Manager (ARM) audience** is a condition relevant to managed-identity pull flows from Azure services. Inspect the registry's feature support/setting status rather than focusing exclusively on role assignments.

Example inspection command on a supported CLI version:

```bash
az acr config authentication-as-arm show \
  --registry "$ACR" \
  --output json
```

If the status does not align with the managed identity flow being deployed, read the feature requirements and apply changes with approval. **Do not toggle it arbitrarily in production**, as this may impact other clients using the registry.

### 12.2. A Private Endpoint Does Not Replace Pull Permissions

A private endpoint only alters the network path. A client connecting successfully to a private IP can still receive `401` or `403` errors due to missing an Entra token or proper role. Conversely, a valid `AcrPull` role cannot bypass a blocked route or firewall.

When debugging, build a table separating the two layers:

| Network Checks | Authorization Checks |
|---|---|
| DNS resolution of `<acr>.azurecr.io` | Actual identity used by the Container App |
| Route/NSG/Firewall/Private endpoint | RBAC vs RBAC + ABAC mode |
| TLS connectivity to relevant endpoints | Role assignment and scope |
| Data endpoints and image layers | ABAC repository condition, pull permissions |

## 13. Observability, Logs, and Troubleshooting

### 13.1. Collecting Traces at the Right Points

To investigate an image pull failure, check:

- **Container Apps revision state and provisioning events**: which revision failed, what image reference was used, and at which phase image retrieval failed.
- **Container Apps system logs**: platform messages on container initialization and image pulls within the log scope provided by the service.
- **ACR diagnostic logs**: sign-in requests, repository access, operations, and errors per enabled log categories.
- **Azure Activity Log**: control-plane changes to role assignments, networking, registry settings, or managed identities.
- **Entra ID / identity events** per available permissions and scope: token authentication, wrong principal/tenant, and workload identity issues.

Never record access tokens, registry passwords, or full Docker login strings in support tickets. Capturing the UTC timestamp, ACR resource ID, login server, repository/tag, Container App revision, principal **Object ID**, and error code is sufficient for most initial triage.

### 13.2. Typical Errors

| Symptom | Possible Cause | Check or Resolution |
|---|---|---|
| `401 Unauthorized` on pull | No valid token, identity not attached, misconfigured registry auth | Container App registry config, managed identity, Entra token flow |
| `403 Forbidden` | Identity exists but role/scope/condition denies access | RBAC mode, role assignment, ABAC repository condition |
| `denied: requested access to the resource is denied` | Repo/tag pull not permitted or auth requirements unmet | Verify repo, pull action, identity, and policy |
| `manifest unknown` or `not found` | Tag/digest does not exist, wrong repository name or registry | Check standard image name and push/publish pipeline |
| Timeout, TLS handshake, or DNS error | Network, firewall, DNS, private endpoint, or data endpoint unreachable | Egress path, resolver, routes, network restrictions |
| Error after switching registry mode | Legacy AcrPull/AcrPush roles no longer match ABAC mode | Migrate to Repository Reader/Writer and conditions |
| Can pull orders but not payments | Either working ABAC condition or missing permission | Cross-check desired policy and negative tests |
| `az acr login` succeeds, `docker push` fails | Sign-in succeeded but principal lacks push permission | Appropriate Push/Repository Writer role, repository condition |
| Only new app fails, old app still runs | New app uses different identity, new revision must pull, tag/digest changed | Identity bindings, revision events, artifact, and registry config |
| Newly assigned role cannot pull yet | RBAC has not propagated yet or stale token/session | Wait for propagation, confirm role/scope, refresh session per guidance |
| Admin login works but managed identity fails | Two distinct auth paths; admin bypasses intended RBAC boundaries | Do not substitute admin; fix role, identity, and ARM audience support |

Specific HTTP/status codes and messages may vary by Docker/OCI client, Azure Container Apps, and registry configuration. Always check **actual log details** rather than assuming every 401 stems from a single root cause.

### 13.3. Ordered Investigation Procedure

1. **Identify the image:** exact login server, repository, tag/digest, environment, and failing revision.
2. **Inspect revision/system events:** did the error occur before the container ran (pull) or during application startup?
3. **Check networking:** are the registry endpoint and layer/data endpoints reachable? How are DNS/routes/firewalls configured?
4. **Check the principal:** is the exact managed identity resource ID attached to the Container App? Which identity does the registry config use?
5. **Check ACR permissions mode:** traditional RBAC or RBAC + ABAC?
6. **Verify role and condition:** are Object ID/scope/action/repository accurate?
7. **Verify token/registry settings:** are ARM audience mechanisms or required APIs compatible?
8. **Check the artifact:** does the tag or digest exist, and did the pipeline publish it successfully?
9. **Controlled testing:** test pulling permitted and unpermitted repositories with an equivalent identity in a supported environment.
10. **Minimal remediation:** fix role/condition, identity binding, route, or image name; observe the new revision and document the outcome.

Never create a registry admin password or assign `Owner` "just to see if it works." Doing so masks configuration bugs, invalidates least-privilege testing, and introduces long-term risk.

## 14. Enforcing Least Privilege and Managing Identity Lifecycles

### 14.1. Separating Build Identity and Runtime Identity

A production architecture might specify:

| Identity | Permitted Resource | Actions |
|---|---|---|
| `ci-orders-build` | `orders/api` | Push and read artifacts needed for build/test |
| `mi-orders-acr-pull-prod` | `orders/api` | Pull only; no push/delete |
| `mi-orders-workload-prod` | Relevant Key Vault or Storage | Access data strictly required by the application |
| `registry-operators` | Approved ACR and IAM settings | Infrastructure administration, never used as runtime credentials |

Using two separate identities for image pull and data access is not syntactically mandatory, but it limits blast radius if an app is exploited. If a team chooses to share one identity for simplicity, document the rationale and the combined permissions held by that identity.

### 14.2. Role Assignments Have a Lifecycle

When creating, modifying, or deleting a Container App:

- Inventory existing **principal IDs** and corresponding role assignments.
- With a **system-assigned identity**, deleting the host resource can cause the principal to disappear; orphaned role assignments should be inspected and cleaned up.
- With a **user-assigned identity**, deleting a Container App does not delete the identity itself. If keeping the identity, check which apps still attach it and whether it still needs registry permissions.
- When promoting an app from dev to prod, **do not carelessly reuse a dev identity holding overly broad roles**.
- When revoking permissions, check whether previously issued tokens/credentials remain valid for a grace window; test after changes and maintain an emergency response plan.

Revoking permissions may not cause a running container to **stop immediately**: the image is already downloaded and the active process does not re-pull every second. Revocation affects subsequent registry data operations, such as pulling during new revision/replica creation per service conditions.

### 14.3. Protecting Artifacts Beyond RBAC

RBAC only governs who can perform operations against the registry. You cannot infer that an artifact pushed by an authorized pipeline is safe or approved. Supplement with:

- **Vulnerability scanning** and policies blocking builds with critical risks.
- **Image signing/attestation, provenance, and SBOM** per tooling capabilities.
- **Digest pinning** in release manifests and strict governance of critical production tags.
- Dependency and base image reviews, applying patches periodically.
- Release pipeline approvals, dev/test/prod separation, and branch/tag protection.
- Container runtime hardening: avoid unnecessary high privileges, never bake secrets into images.

If a pipeline with push rights to a production repository is compromised, an attacker can still upload malicious images to the registry. ABAC limits the blast radius across repositories, yet it does not replace supply chain checks.

### 14.4. Disabling the Admin User Once Clients Have Migrated

If ACR no longer has clients relying on the admin account, consider disabling it:

```bash
# Run only after inventorying credentials and approving the change.
az acr update \
  --name "$ACR" \
  --resource-group "$ACR_RG" \
  --admin-enabled false
```

This operation can break older clients if they still rely on the admin username/password. Therefore, inventory CI pipelines, App Service, Container Apps, AKS, and external tools before applying it. Disabling the admin user does not remove secrets previously leaked into repositories or logs.

## 15. Organizing Deployment with Infrastructure as Code

To prevent configuration drift, version-control:

1. ACR (SKU, networking, policies, permissions mode, and diagnostics).
2. Managed identity resources and where they attach to workloads.
3. Azure RBAC role assignments and **ABAC conditions** when using repository mode.
4. Container Apps environment, Container App registry configuration, and image references.
5. CI/CD federation, release policies, and non-sensitive parameters.

Illustrative design document example (**illustrative only, not a directly deployable YAML**):

```yaml
environment: production
acr:
  name: acrplatformprod
  roleAssignmentMode: RBAC+ABAC
  repositories:
    - name: orders/api
      runtimeReader: mi-orders-acr-pull-prod
      pipelineWriter: ci-orders-build
    - name: payments/api
      runtimeReader: mi-payments-acr-pull-prod
      pipelineWriter: ci-payments-build

containerApp:
  name: ca-orders-api-prod
  image: acrplatformprod.azurecr.io/orders/api@sha256:<approved-digest>
  registryIdentity: mi-orders-acr-pull-prod
  applicationIdentity: mi-orders-workload-prod
```

The manifest above helps express **intent** and test boundaries; to deploy, use real **Bicep, ARM, or Terraform** schemas and valid ABAC conditions matching current API versions/capabilities. Never put secrets or tokens into source control.

### 15.1. Deployment Ordering to Avoid Dependency Cycles

With a user-assigned identity, a recommended IaC sequence is:

```text
Create ACR / choose permissions mode
         |
         v
Create user-assigned managed identity
         |
         v
Assign Repository Reader or AcrPull per mode
         |
         v
Create/Update Container Apps environment
         |
         v
Create Container App + identity + registry config + image
         |
         v
Verify revision, image pull, application, and monitoring
```

If ACR uses a private endpoint and the Container Apps environment is VNet-integrated, prepare **network/DNS before the pull step**. When updating policies in production, test with a canary revision to catch propagation or networking issues before shifting all traffic.

## 16. Cost and Operational Considerations

**Managed identities and role assignments** are not the primary driver of ACR costs; total cost depends on the resources provisioned and consumed.

| Component | Cost Factors to Estimate |
|---|---|
| Azure Container Registry | SKU, artifact storage volume, retention duration, add-on features, and data operations per applicable pricing |
| Registry networking | Private endpoints, network data transfer, VNet/NAT/firewall components |
| Container Apps | Compute/requests/replicas per environment and workload billing models |
| Logging | Log Analytics ingestion, retention, Azure Monitor alerts |
| CI/CD | Build agents, image layers/cache, registry tasks if used |
| Replication/geo-replication | Storage and image distribution across supported SKUs and regions |

Putting all teams into one registry to save money reduces resource count, yet if security and isolation needs diverge, a shared registry demands stricter ABAC/IAM/network policies and operations. Weigh cost against **blast radius** and complexity, not merely registry count.

### 16.1. Why Clean Up Old Artifacts and Permissions?

Registries accumulate tags/manifests/image layers with every release. Without retention/cleanup, storage grows steadily; without cleaning up role assignments and identities, stale permissions persist longer than needed.

A sound workflow:

- Keep actively running image versions and rollback targets per SLA/DR requirements.
- Use retention policies or cleanup jobs per SKU capabilities, reviewing before deletion.
- Maintain a **Container App revision → image digest** mapping so still-needed artifacts are not deleted by mistake.
- Audit principals holding Writer/Contributor rights and overly broad conditions.
- Track costs and set alerts for sudden spikes in storage, image pulls, or revision counts.

Deleting an artifact may not stop a running container immediately, yet it can cause **scale-outs or redeployments to fail pulling**. Always cross-check dependencies before cleaning up.

## 17. Scenario Exercises

### Scenario A: Container App Cannot Pull Image

A team deploys:

```text
Container App: ca-orders-api-prod
Registry: acrplatformprod.azurecr.io
Image: acrplatformprod.azurecr.io/orders/api:1.4.2
Identity: mi-orders-acr-pull-prod
```

The registry was switched to **RBAC + ABAC Repository Permissions mode**. Previously, the pipeline assigned the `AcrPull` role to the managed identity at the registry scope, but the new Container Apps revision reports `403` on pull.

**Tasks:**

1. Explain why the old role may no longer grant data permissions.
2. Propose the new role and condition restricted solely to `orders/api`.
3. Distinguish Resource ID and Principal/Object ID of the managed identity across the two configuration steps.
4. List three log/information sources to inspect before changing permissions.
5. Describe a test proving the app **cannot** pull `payments/api`.

**Solution outline:** confirm the mode, transition to `Container Registry Repository Reader` with a repository condition for `orders/api`, assign to the exact principal, and configure the registry identity using its Resource ID. Inspect Container Apps revision/system logs, ACR diagnostics, role assignments/mode, networking, and the image reference. Run a positive pull test on `orders/api` and a negative pull test on `payments/api` using an equivalent identity, avoiding the admin account which would mask the error.

### Scenario B: Separating CI and Runtime Permissions

A pipeline builds version `2.0.0` of `payments/api` and a Container App pulls this image to run. The security team wants to ensure that if the app is compromised, an attacker **cannot overwrite production images**.

**Design requirements:**

- Use two identities: `ci-payments-build` and `mi-payments-acr-pull-prod`.
- The pipeline can publish to the required repository.
- Runtime has pull permissions only.
- Do not store ACR admin passwords in Container App secrets.
- Pin the image by digest in the release manifest.

**Solution outline:** the pipeline uses a service principal/OIDC federation or suitable CI environment identity, assigned `AcrPush` (legacy mode) or Repository Writer (ABAC mode) at the required scope. The Container App uses a user-assigned identity with only `AcrPull` or Repository Reader. Set a repository condition if the registry uses ABAC. Alongside this, apply image signing/scanning and release reviews so the pipeline cannot push unapproved images.

### Scenario C: Private Endpoint Registry

A Container App has the right permissions and registry config, yet `orders/api` still fails to pull. ACR only allows private endpoints and sits in a hub/spoke topology.

**Task:** describe how to inspect DNS, routes, firewalls, and private endpoints before adding roles; explain why a successful `az acr login` from a developer laptop does not prove Container Apps has a network path to the registry.

**Solution outline:** the laptop and Container Apps may use **different networks, DNS resolvers, and source IPs**. Verify from the relevant environment/workload: network egress, private DNS, registry/data endpoints, HTTPS ports, UDRs/NSGs/firewalls, and logs. Only after confirming networking should you re-check identity/permissions.

### Scenario D: Revoking Permissions When Deleting an App

A team deleted `ca-orders-api-test`, yet the user-assigned identity `mi-orders-test` still exists and holds the Reader role on the production registry.

**Task:** propose a procedure to clean up unused identities and role assignments, verify no other Container App uses the identity, and explain why deleting an app does not automatically revoke all permissions of a user-assigned identity.

**Solution outline:** inventory identity bindings, role assignments, owners, and last-use evidence if available; revoke roles first and then delete the identity per procedure once no dependencies remain. A user-assigned identity has an independent lifecycle, so it can persist even after an app is deleted.

## 18. Self-Check Questions

**1. Does a successful `az acr login` prove the principal can push every image?** No. Login is authentication; pushing requires an authorization role/condition matching the repository and registry mode.

**2. Which permission should a Container App runtime that only pulls images choose?** `AcrPull` in RBAC registry mode, or `Container Registry Repository Reader` with an appropriate condition in RBAC + ABAC mode.

**3. Why should `AcrPush` not be assigned to a runtime?** Because the runtime does not need to modify artifacts; push permissions increase impact if the identity is exposed or abused.

**4. How does a managed identity differ from an ACR admin account?** A managed identity is an Entra principal managed by Azure and controlled via role assignments; an admin account is a broad-privilege registry credential not tied to granular per-principal RBAC.

**5. Are Principal ID and Resource ID of a user-assigned identity interchangeable?** No. Principal/Object ID is used for the RBAC assignee; Resource ID is used to attach the identity to a Container App and specify the registry identity per supported syntax.

**6. How does ACR RBAC + ABAC differ from RBAC registry mode?** ABAC enables repository roles and repository-name conditions within supported scopes; legacy roles such as `AcrPull` should not be assumed to remain effective as before.

**7. Can a Container App with Repository Reader permission pull if the ACR private endpoint is network-blocked?** No. Both network connectivity and authorization are required.

**8. Does a running workload that already pulled its image immediately stop when the Reader role is revoked?** Not automatically. A running process does not continuously re-pull the image; new pulls will be subject to current permissions and remaining token validity.

**9. When should the Catalog Lister role be granted?** When a client genuinely needs to enumerate repository names per supported capabilities, never merely to pull a known image name.

**10. Does using a single shared registry with ABAC replace every need for separate registries?** No. Network isolation, encryption boundaries, billing, operations, and compliance may still require separate registries.

## 19. Production Checklist

- [ ] Accurately identified ACR, login server, repository, tag/digest, and Container App/environment.
- [ ] Verified the registry's **role assignment permissions mode** before selecting roles.
- [ ] Granted pull-only to runtime; separate push to CI; avoided admin passwords in apps.
- [ ] In ABAC mode, configured exact **repository conditions** and tested both allow and deny cases.
- [ ] In RBAC registry mode, evaluated whether applying `AcrPull` across the whole registry is appropriate.
- [ ] Documented Principal/Object ID, Client ID, and Resource ID of managed identities without mixing them up in configs.
- [ ] Identity is genuinely attached to the Container App and the registry entry uses that exact identity.
- [ ] Reviewed **ARM audience token authentication** when needed for managed identity pull flows.
- [ ] Verified DNS, TLS, private endpoints, registry firewalls, and egress paths from the Container Apps environment.
- [ ] Selected an approved OCI image, pinned version/digest, with appropriate scanning and provenance.
- [ ] Separated CI publish permissions from runtime pull permissions; CI federation/credentials have narrow scopes.
- [ ] Configured ACR diagnostic logs, Container Apps system logs, Azure Activity Log, and appropriate alerts.
- [ ] Tested new Container Apps revisions, nonexistent images, missing permissions, and network disconnections.
- [ ] Established a runbook for handling 401/403 errors, network timeouts, RBAC propagation, and permission mode switches.
- [ ] Inventoried shared user-assigned identities, obsolete role assignments, and Catalog Lister permissions.
- [ ] Estimated and monitored costs for registry, storage, networking, Container Apps, logging, and CI.
- [ ] Placed ACR, identities, role assignments/ABAC conditions, and Container Apps configs into IaC/review.

## Conclusion

**Azure Container Registry** stores and distributes images, while **Microsoft Entra ID, Azure RBAC, and managed identities** provide workload-controlled authentication and authorization without sharing registry passwords. With Container Apps, a user-assigned managed identity lets you prepare **pull** permissions ahead of time, attach the identity to the app, and configure registry authentication by identity instead of username/password.

The most important point is choosing the right ACR authorization model: **`AcrPull`/`AcrPush`** for corresponding registry-level RBAC mode, or **Container Registry Repository Reader/Writer** with repository conditions when using **RBAC + ABAC Repository Permissions mode**. Proper configuration must go hand in hand with network connectivity, DNS, pipeline security, image versioning/digests, logging, deny testing, and identity lifecycle governance. As a result, Azure applications hold only the registry permissions truly needed throughout building, deploying, scaling, and operations.
