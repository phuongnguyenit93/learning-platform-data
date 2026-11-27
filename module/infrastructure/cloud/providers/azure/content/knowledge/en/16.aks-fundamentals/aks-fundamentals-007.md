# AKS Workload Identity for Pods

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data. Learners master deploying, monitoring, securing, and controlling costs for application architectures on Azure. In the **Azure Kubernetes Service Fundamentals** chapter, this lesson focuses on **AKS Workload Identity**: enabling applications running inside Kubernetes pods to access Azure resources using a Microsoft Entra ID identity without embedding client secrets or storage access keys inside containers.

Imagine a Java API running on AKS that needs to read a connection string from Azure Key Vault. An insecure approach is storing a client secret inside a Kubernetes Secret, passing it into a pod environment variable, and using it to authenticate with Microsoft Entra ID. If that secret is copied from configs, logs, or images, an attacker can reuse it outside the cluster until it is revoked. **Microsoft Entra Workload ID** uses a trust federation between the AKS-issued ServiceAccount token and Microsoft Entra ID so the application acquires an access token for the target Azure resource, reducing reliance on static credentials.

After this lesson, you can:

- Explain the differences among **Kubernetes ServiceAccount**, **managed identity**, **AKS cluster identity**, **kubelet identity**, and **Workload Identity**.
- Describe the flow **OIDC issuer → projected ServiceAccount token → federated identity credential → Entra access token → Azure RBAC**.
- Enable OIDC issuer and workload identity on AKS using supported procedures.
- Create a **user-assigned managed identity**, configure a federated identity credential, and assign least-privilege Azure RBAC.
- Configure a ServiceAccount, annotation, pod label, and deployment, and use the Azure SDK in a Java application.
- Verify authentication outcomes and troubleshoot issuer/subject/audience mismatches, pod mutation, RBAC, and networking issues.
- Design namespace boundaries, identity lifecycle, CI/CD, monitoring, and cost controls for production.

## 1. The problem AKS Workload Identity solves

An application inside a pod frequently needs to access resources **outside Kubernetes**, such as:

- Azure Key Vault to read secrets or certificates per granted permissions.
- Azure Storage to read/write blobs using Entra ID and Azure RBAC.
- Azure SQL or services supporting Microsoft Entra authentication.
- Azure Service Bus, Event Hubs, or Azure APIs supporting bearer access tokens.

The application must prove its identity to the target service. In a standard Kubernetes cluster, a pod's ServiceAccount token is issued by Kubernetes and **is not automatically an Entra access token** to call Key Vault. AKS Workload Identity bridges those two trust domains through **OpenID Connect (OIDC) federation**.

```text
Pod in AKS
  |
  | Projected Kubernetes ServiceAccount token
  | (JWT with issuer, subject, and audience)
  v
Microsoft Entra ID
  |
  | Matches federated identity credential of managed identity
  | and validates token from trusted OIDC issuer
  v
Entra access token for Key Vault / Storage / target service
  |
  v
Azure service checks Azure RBAC / data permissions
  |
  +-- Sufficient permissions & valid network -> operation allowed
  +-- Insufficient permissions / conditions -> denied
```

**Do not confuse these two layers:**

1. **Federation/authentication** determines which Entra identity a pod can exchange its Kubernetes token for.
2. **Authorization at the target service** determines whether that identity can read a secret, write a blob, or send a message.

Successfully creating a federated credential does not grant Key Vault permissions. Conversely, assigning an Azure RBAC role to a managed identity will not let a pod acquire tokens if the issuer, ServiceAccount, or workload identity webhook is misconfigured.

### 1.1. Before and after adopting Workload Identity

| Aspect | Client secret placed in pod | AKS Workload Identity |
|---|---|---|
| Credential material held by app | Client secret/certificate with its own lifecycle | Projected ServiceAccount token and non-secret identity metadata |
| Static secret distribution | Must manage, rotate, and prevent leaks | No Entra application client secret needed for this flow |
| Trust source | Entra application credential | AKS OIDC issuer and federated credential |
| Azure permissions | Still requires Azure RBAC or service permissions | Still requires Azure RBAC or service permissions |
| Workload scoping | Secret can be copied and used outside the pod if leaked | Token is bound to issuer/subject/audience and lifetime; still must prevent token theft |
| Lifecycle management | Secret rotation, distributing updated secrets | Manage ServiceAccount, federated credential, managed identity, and roles |

Workload Identity **reduces static secret risk**; it does not mean the pod holds zero credentials. The projected token remains sensitive while valid and must be protected from logging, exfiltration, and unauthorized workloads.

## 2. Components and identities to distinguish

### 2.1. AKS cluster identity

AKS has an identity used by the control plane to **manage the cluster's Azure infrastructure** as supported. It handles tasks like managing related Azure resources and is not automatically the identity of every application running in pods.

### 2.2. Kubelet identity

The kubelet identity is tied to node/kubelet operations for AKS-supported tasks, commonly mentioned when granting permissions to **pull images from Azure Container Registry**. Kubelet being able to pull an image does not allow Java code inside a pod to read Key Vault.

### 2.3. Kubernetes ServiceAccount

A **ServiceAccount (SA)** is an identity **inside Kubernetes**, scoped to a **namespace**. A pod can run with a specified `serviceAccountName`. The Kubernetes API Server issues tokens carrying a subject such as:

```text
system:serviceaccount:<namespace>:<service-account-name>
```

Example:

```text
system:serviceaccount:orders:orders-kv-reader
```

ServiceAccounts and Kubernetes RBAC govern access to the **Kubernetes API**. They do not grant Azure Key Vault access on their own. Naming a ServiceAccount does not create an Entra application or an Azure managed identity.

### 2.4. User-assigned managed identity

A **User-assigned managed identity (UAMI)** is an Azure resource backed by an Entra service principal. It has:

| Property | Meaning | Usage in this lesson |
|---|---|---|
| **Resource ID** | Azure Resource Manager ID of the UAMI | Identifies the resource for management |
| **Client ID** | Application/client identifier | ServiceAccount annotation `azure.workload.identity/client-id` |
| **Principal ID** | Object ID of the service principal in the Entra tenant | Assignee when creating Azure RBAC role assignments |
| **Tenant ID** | Associated Entra tenant | Verifies issuer/trust and credentials |

**Client ID differs from Principal ID.** Use Client ID when the annotation asks for client ID; use Principal/Object ID when creating role assignments with `--assignee-object-id`.

In some models, AKS Workload Identity can also federate with a separately registered Entra application, but this hands-on lesson chooses **UAMI** to get an Azure-managed identity resource that is easy to assign Azure RBAC to.

### 2.5. Federated identity credential (FIC)

A **Federated identity credential** is a trust relationship attached to a UAMI/Entra application describing which external tokens are allowed to exchange for an Entra access token of that identity. Three core fields:

- **Issuer:** the AKS cluster's OIDC issuer URL.
- **Subject:** exact `system:serviceaccount:<namespace>:<serviceaccount>`.
- **Audience:** typically `api://AzureADTokenExchange` in Azure public cloud for Workload Identity flows.

Issuer, subject, and audience must **match** the projected token's claims. Creating a ServiceAccount with the same name in a different cluster will not work because the issuer differs. Namespace, ServiceAccount name, and issuer form part of the security boundary, not decorative metadata.

### 2.6. OIDC issuer and webhook

When AKS enables the **OIDC issuer**, the cluster exposes an issuer endpoint so Microsoft Entra ID can verify Kubernetes-issued tokens under federation. When **workload identity** is enabled, the service's admission webhook mutates eligible pods, injecting the projected token volume and environment variables for the Azure Identity SDK.

In a typical configuration, a pod using Workload Identity needs:

1. A ServiceAccount annotated with the UAMI's **Client ID**.
2. A pod template carrying the label **`azure.workload.identity/use: "true"`** so the webhook recognizes it.
3. A pod specifying the matching `serviceAccountName` running on a cluster with the required features enabled.
4. An FIC with exact issuer/subject/audience, plus Azure roles granted on the target service.

**Annotating the ServiceAccount while forgetting the pod label** can prevent the webhook from injecting the token and environment variables as expected.

## 3. Authentication flow from pod to Azure Key Vault

```mermaid
sequenceDiagram
    participant P as Java Pod (orders namespace)
    participant K as AKS OIDC issuer
    participant E as Microsoft Entra ID
    participant V as Azure Key Vault

    Note over P: SA orders-kv-reader and workload identity pod label
    K-->>P: Projected ServiceAccount JWT
    P->>E: Request token with federated JWT
    E->>K: Verify issuer/signature via OIDC metadata
    E->>E: Match FIC: issuer, subject, audience
    E-->>P: Access token for Key Vault
    P->>V: Read secret with Entra access token
    V->>V: Check RBAC/permissions + network
    V-->>P: Data if allowed; error if denied
```

The diagram shows the **logical flow**; token verification and metadata retrieval may use caching and internal mechanisms rather than opening a direct network call to the issuer on every single request.

### 3.1. Environment variables and token provided by the webhook

In a mutated pod, the Azure Identity SDK typically uses:

| Name | Function |
|---|---|
| `AZURE_CLIENT_ID` | Specifies the Entra client ID of the managed identity the workload intends to use |
| `AZURE_TENANT_ID` | Tenant used for token exchange |
| `AZURE_FEDERATED_TOKEN_FILE` | Path inside the container to the projected ServiceAccount token |
| `AZURE_AUTHORITY_HOST` | Cloud authority endpoint if provided/needed |

The file at `AZURE_FEDERATED_TOKEN_FILE` holds a **short-lived JWT**, not a direct access token for calling Key Vault. The Azure Identity SDK reads that token, performs token exchange with Entra ID, and receives an access token scoped to the target service.

**Never log token contents**, never mount the token into containers that do not need it, and never copy the token outside the cluster. `AZURE_CLIENT_ID` is an identifier rather than a secret, yet the projected token itself must still be protected.

### 3.2. Tokens and permissions have different lifecycles

The projected ServiceAccount token has an expiration and is managed/rotated by Kubernetes per supported configuration. The Entra access token has its own lifetime, cached and refreshed by the SDK. If an app reads the JWT file once at startup and caches it forever, it will fail once the token expires.

Revoking a UAMI's Key Vault role does not immediately invalidate all previously issued access tokens in every scenario. Design incident response around token lifetimes, available revocation mechanisms, and target service policies.

## 4. How Workload Identity differs from earlier approaches

| Solution | Approach | Assessment |
|---|---|---|
| **Static client secret** | Entra application secret/certificate placed in workload | Must manage credentials, rotation, and prevent exfiltration |
| **Node/kubelet-attached managed identity** | Uses infrastructure/node identity | Provides no per-pod boundary if all pods share the same identity |
| **AAD Pod Identity (legacy)** | Intercepts/routes token calls to Azure Instance Metadata Service | Legacy solution; for modern AKS, prefer Workload Identity per current guidance |
| **AKS Workload Identity** | Kubernetes OIDC token federation with Entra ID | Supports namespace + ServiceAccount + FIC boundaries and compatible SDKs |
| **Kubernetes Secret holding access keys** | Pod uses Storage/Key Vault/app keys | Easily over-scoped; hard to revoke or audit per workload |

A major advantage is **no longer needing pod-level interception of the node's Instance Metadata Service (IMDS)** to obtain identities. However, code must use compatible SDKs/credentials and the cluster must enable the right features. Never assume an AKS upgrade automatically converts legacy applications to Workload Identity.

## 5. Designing permissions by namespace and ServiceAccount

Suppose a cluster runs three applications:

```text
AKS: aks-orders-prod
|
+-- Namespace orders
|    +-- ServiceAccount orders-kv-reader
|    +-- Deployment orders-api
|
+-- Namespace payments
|    +-- ServiceAccount payments-kv-reader
|    +-- Deployment payments-api
|
+-- Namespace reporting
     +-- ServiceAccount reports-blob-reader
     +-- CronJob reports-export
```

A least-privilege design could look like:

| Pod/ServiceAccount | Managed identity | Azure data permissions |
|---|---|---|
| `orders/orders-kv-reader` | `mi-orders-kv-prod` | Read only secrets needed by `orders` |
| `payments/payments-kv-reader` | `mi-payments-kv-prod` | Read `payments` secrets |
| `reporting/reports-blob-reader` | `mi-reports-blob-prod` | Read data from approved Blob containers |

Never use one UAMI with permission to read every secret and blob in the organization for all pods unless the rationale and risk scope have been thoroughly justified. One managed identity can have **multiple FICs** where supported, meaning multiple ServiceAccounts can share that identity's Azure permissions; document and govern such relationships closely.

### 5.1. Kubernetes RBAC is a separate layer

Kubernetes RBAC answers: *can this pod or user call the Kubernetes API, read ConfigMaps, or edit Deployments?* Azure RBAC answers: *can this UAMI read a Key Vault secret, send a Service Bus message, or write a Storage blob?*

Workload Identity **does not grant a ServiceAccount Kubernetes administration rights**. Conversely, unchecked permissions to create/edit ServiceAccounts, Pods, or FICs can become a path to hijack Azure access. Protect both **Kubernetes API authorization** and **Azure resource/IAM authorization**.

### 5.2. Namespaces are not the sole security barrier

A pod in another namespace using a ServiceAccount with the same name will have a **different subject** because the subject includes the namespace. However, anyone allowed to create/modify a Deployment in the target namespace and pick a trusted ServiceAccount can launch a pod assuming that federated identity. Therefore:

- Restrict who can create/modify pods, deployments, and ServiceAccounts in sensitive namespaces.
- Use admission policies to block unapproved pods from selecting privileged ServiceAccounts.
- Restrict permissions to create/edit federated credentials and role assignments in Azure.
- Enforce network policies, pod security, image governance, and anti-exfiltration controls inside workloads.
- Separate identities for applications with different data or owners.

## 6. Hands-on: configuring AKS Workload Identity with Azure CLI

We will configure a Java pod in the `orders` namespace to use a **user-assigned managed identity** to read a secret from Azure Key Vault. This is a controlled test environment, not a script to run blindly on production.

**Prerequisites:**

1. An existing AKS cluster running a Kubernetes/AKS version supporting **OIDC issuer** and **Workload Identity**.
2. Azure CLI, `kubectl`, appropriate permissions on the cluster and namespace, and permission to update AKS configuration.
3. Permissions to create a user-assigned identity, federated credential, and Azure role assignment on the target Key Vault scope.
4. An existing Key Vault in dev configured with the **Azure RBAC permission** model (if using the `Key Vault Secrets User` role example).
5. AKS networking capable of reaching Entra ID token exchange endpoints and Key Vault under current rules.
6. A test container image with Java code using the Azure Identity SDK already built and pullable from a registry. This lesson does not build a new app image or create a new Key Vault.

### 6.1. Set Bash variables and verify subscription

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

AKS_RG="rg-aks-dev"
AKS_NAME="aks-orders-dev"
IDENTITY_RG="rg-orders-identity-dev"
LOCATION="southeastasia"
UAMI_NAME="mi-orders-kv-reader-dev"

NAMESPACE="orders"
SERVICE_ACCOUNT="orders-kv-reader"
FIC_NAME="fic-aks-orders-dev"

VAULT_RG="rg-security-dev"
VAULT_NAME="kv-orders-dev-example"
SECRET_NAME="demo-message"
```

Replace all example values with real resource names. Never print secret values to shell output or logs. Never let test tasks modify production resource groups outside approved scope.

### 6.2. Enable OIDC issuer and Workload Identity

If not yet enabled on the cluster, run the update command:

```bash
az aks update \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --enable-oidc-issuer \
  --enable-workload-identity
```

If the cluster already has both enabled, simply verify the configuration; no need to re-run `update` repeatedly. Enabling features on live clusters must follow change management, checking AKS version support and running workloads.

Retrieve the exact issuer URL:

```bash
AKS_OIDC_ISSUER=$(az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "oidcIssuerProfile.issuerUrl" \
  --output tsv)

echo "$AKS_OIDC_ISSUER"
```

The value is typically an HTTPS URL provided by AKS; **never type or guess the issuer URL manually**. Even a single character difference—including a trailing `/` if present—can break federation matching.

Inspect cluster configuration:

```bash
az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{oidc:oidcIssuerProfile,workloadIdentity:securityProfile.workloadIdentity}" \
  --output json
```

If the issuer is empty or the features are not in the expected state, do not proceed with creating an FIC using a placeholder issuer. Resolve cluster prerequisites first.

### 6.3. Create the user-assigned managed identity

```bash
az identity create \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --location "$LOCATION"

UAMI_RESOURCE_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --query id --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --query clientId --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$UAMI_NAME" \
  --query principalId --output tsv)
```

At this point, the UAMI **has no Key Vault permissions yet** and the ServiceAccount **is not yet federated** with the identity. Merely creating the identity does not let any pod use it immediately.

### 6.4. Create the federated identity credential

The subject is built strictly from the namespace and ServiceAccount name:

```bash
FIC_SUBJECT="system:serviceaccount:$NAMESPACE:$SERVICE_ACCOUNT"

az identity federated-credential create \
  --resource-group "$IDENTITY_RG" \
  --identity-name "$UAMI_NAME" \
  --name "$FIC_NAME" \
  --issuer "$AKS_OIDC_ISSUER" \
  --subject "$FIC_SUBJECT" \
  --audience "api://AzureADTokenExchange"
```

Verify with a read-only command:

```bash
az identity federated-credential show \
  --resource-group "$IDENTITY_RG" \
  --identity-name "$UAMI_NAME" \
  --name "$FIC_NAME" \
  --output json
```

Cross-check carefully:

| FIC field | Value that must match |
|---|---|
| `issuer` | Exact `AKS_OIDC_ISSUER` of the right AKS cluster |
| `subject` | `system:serviceaccount:orders:orders-kv-reader` |
| `audiences` | `api://AzureADTokenExchange` per the active token exchange flow |
| UAMI | The identity whose access token the app should receive |

Federated credentials have quantity limits and service constraints. If multiple clusters or namespaces share one UAMI, inventory every FIC to avoid turning one identity into an over-privileged aggregation point.

### 6.5. Assign Azure RBAC to read a Key Vault secret

For a Key Vault using the **Azure RBAC permission** model, an example data-plane role is `Key Vault Secrets User`. Verify the vault's mode:

```bash
az keyvault show \
  --resource-group "$VAULT_RG" \
  --name "$VAULT_NAME" \
  --query "{id:id,vaultUri:properties.vaultUri,rbacEnabled:properties.enableRbacAuthorization}" \
  --output json
```

If `rbacEnabled` is not `true`, this role assignment **will not suffice** to control secret access; the vault likely uses the **access policy model** and requires its corresponding workflow. Never flip a production Key Vault's permission model just to run a lab.

Fetch the Resource ID and assign the role:

```bash
VAULT_ID=$(az keyvault show \
  --resource-group "$VAULT_RG" \
  --name "$VAULT_NAME" \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
```

Vault scope is used here for a simple lab. In production, if only a single secret is needed, consider **secret-level scope** or appropriate vault separation and Azure RBAC/Key Vault conditions to tighten permissions further. Never grant `Key Vault Administrator`, `Owner`, or `Contributor` just so an app can `get` one secret.

Read back the RBAC assignment:

```bash
az role assignment list \
  --assignee "$UAMI_PRINCIPAL_ID" \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
```

Role assignments can take time to propagate. If an app is denied right after assignment, verify the exact Object ID, role, scope, and permission model before widening privileges.

## 7. Configuring Kubernetes ServiceAccount and workload pod

### 7.1. Fetch kubeconfig for the target cluster

```bash
az aks get-credentials \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME"

kubectl config current-context
kubectl get namespaces
```

**Important:** `az aks get-credentials` can modify the kubeconfig/current context on your workstation. Always check `kubectl config current-context` before any `apply` or `rollout`; never run against production AKS by mistake.

### 7.2. Create the namespace and ServiceAccount

```bash
kubectl create namespace "$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: $SERVICE_ACCOUNT
  namespace: $NAMESPACE
  annotations:
    azure.workload.identity/client-id: "$UAMI_CLIENT_ID"
EOF
```

The annotation `azure.workload.identity/client-id` points to the **Client ID**, not the Principal ID. Azure Workload Identity offers additional optional annotations per feature, such as tenant ID or projected ServiceAccount token expiration. Only use them when required by design and supported by your SDK/cluster; sensible defaults minimize errors.

Inspect the object:

```bash
kubectl get serviceaccount "$SERVICE_ACCOUNT" \
  -n "$NAMESPACE" -o yaml
```

A ServiceAccount becomes a valid Azure identity source only when **the FIC matches issuer/subject/audience**, the pod uses that ServiceAccount, and workload mutation/token exchange succeed. An annotation alone never grants Azure RBAC permissions.

### 7.3. Sample Deployment with Workload Identity

Assume an image `acrordersdev001.azurecr.io/orders-api:1.0.0` exists containing a Java application integrated with the Azure Identity SDK. This is an **illustrative** image that must be built/pushed beforehand. **AKS kubelet ACR pull permission** is a separate topic and must be configured independently if using a private ACR.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-kv-reader
      containers:
        - name: orders-api
          image: acrordersdev001.azurecr.io/orders-api:1.0.0
          imagePullPolicy: IfNotPresent
          env:
            - name: KEY_VAULT_URL
              value: "https://kv-orders-dev-example.vault.azure.net/"
          ports:
            - containerPort: 8080
```

In `spec.template.metadata.labels`, the label **`azure.workload.identity/use: "true"`** tells the webhook to mutate the pod. Do not put the label only on the Deployment's metadata while forgetting the **Pod template**. `serviceAccountName` must match the SA in the `orders` namespace, and `azure.workload.identity/client-id` on that SA must match the managed identity holding the FIC.

The Key Vault name, image, port 8080, and replica count are examples. Production requires resource requests/limits, probes, network policies, logging, secure image policies, and proper rollout strategies. Never put Key Vault secret values into manifests.

### 7.4. Verify the mutated pod

After applying the manifest in the test environment:

```bash
kubectl get pods -n "$NAMESPACE" -l app=orders-api
kubectl describe deployment orders-api -n "$NAMESPACE"

# View PodSpec/metadata only; do not print JWT contents.
kubectl get pods -n "$NAMESPACE" \
  -l app=orders-api \
  -o json
```

In the mutated PodSpec, look for environment variables such as `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_FEDERATED_TOKEN_FILE`, and the projected service account token volume, depending on webhook and container configuration. Never print or copy the **contents** of the token file. If injection is missing, check the pod label, ServiceAccount, webhook health, and whether the pod was created **after** applying the configuration.

**Lifecycle note:** admission mutation happens at Pod creation time. Updating an annotation on a ServiceAccount will not automatically re-mutate an already-running pod. When needed, create/restart pods via a controlled rollout:

```bash
# Only when the change is approved and the workload is ready.
# kubectl rollout restart deployment/orders-api -n "$NAMESPACE"
```

Kubernetes authorization, Pod Security Admission / admission policies, and network boundaries must still be verified. Seeing the injected environment variables does not prove Entra ID token exchange succeeded.

## 8. Java application reading a secret via Azure Identity SDK

Java applications should use the **Azure SDK for Java** with Workload Identity support. Once the pod receives the webhook-injected environment variables and projected token file, the SDK handles federated token exchange without the app manually crafting HTTP requests or holding client secrets.

Typical Maven dependencies include:

```xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-identity</artifactId>
  <version><!-- Tested stable version supporting Workload Identity --></version>
</dependency>
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-security-keyvault-secrets</artifactId>
  <version><!-- Tested compatible version --></version>
</dependency>
```

These are dependency illustrations: in a real `pom.xml`, specify **valid versions** from an officially tested BOM or release; never paste placeholder comments as empty versions.

### 8.1. Java sample using DefaultAzureCredential

```java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class WorkloadIdentityKeyVaultDemo {
    public static void main(String[] args) {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("KEY_VAULT_URL is required");
        }

        DefaultAzureCredential credential =
                new DefaultAzureCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();

        // The secret must exist and the identity must have read permission.
        KeyVaultSecret secret = client.getSecret("demo-message");

        // Never print the secret value to console, logs, or HTTP responses.
        System.out.println("Retrieved secret metadata: " + secret.getName());
    }
}
```

Inside a mutated AKS pod, a compatible `azure-identity` version detects `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_FEDERATED_TOKEN_FILE` to use Workload Identity. In local dev environments, `DefaultAzureCredential` may select another credential (Azure CLI, IDE, etc.) depending on configuration; thus passing tests on a laptop **does not prove** Workload Identity works on AKS.

### 8.2. Choosing WorkloadIdentityCredential explicitly

To enforce that **production on AKS must strictly use federation**, the application can use `WorkloadIdentityCredentialBuilder` with a compatible SDK:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.WorkloadIdentityCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class ExplicitWorkloadIdentityDemo {
    public static void main(String[] args) {
        TokenCredential credential =
                new WorkloadIdentityCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(System.getenv("KEY_VAULT_URL"))
                .credential(credential)
                .buildClient();

        String name = client.getSecret("demo-message").getName();
        System.out.println("Fetched secret metadata for: " + name);
    }
}
```

This example assumes valid environment variables were injected. With an explicit credential, if the projected token is missing, authentication fails fast instead of accidentally falling back to a broader credential.

**Never add `AZURE_CLIENT_SECRET` or an account key into a Deployment** as a "fallback" when federation breaks. Fix the trust/annotation/permission root cause rather than bypassing Workload Identity.

### 8.3. Token refresh notes

Applications should manage SDK credentials/clients with proper lifecycles rather than reading the projected JWT once into a static variable forever. The Azure SDK handles acquiring and caching access tokens per credential capabilities, while Kubernetes rotates the projected ServiceAccount token.

If a custom library reads `AZURE_FEDERATED_TOKEN_FILE` directly instead of using the Azure SDK, the development team must implement expiration, refresh, audience matching, and token exchange error handling themselves. Unless there is a specific requirement, prefer the official SDK.

## 9. End-to-end verification after deployment

A thorough verification confirms **three separate outcomes**:

1. The pod receives the federation configuration injected by the webhook.
2. The pod can exchange the projected Kubernetes token for the UAMI's access token.
3. The target service enforces Azure RBAC and networking per your matrix.

### 9.1. Inspect configured objects

```bash
kubectl get serviceaccount "$SERVICE_ACCOUNT" \
  -n "$NAMESPACE" -o yaml

kubectl get deployment orders-api \
  -n "$NAMESPACE" -o yaml

az identity federated-credential list \
  --resource-group "$IDENTITY_RG" \
  --identity-name "$UAMI_NAME" \
  --output table

az role assignment list \
  --assignee "$UAMI_PRINCIPAL_ID" \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
```

Verify the ServiceAccount annotation, pod template label, FIC issuer/subject/audience, and permissions on the **exact principal**. Never use your own Azure CLI admin account as a proxy test for the pod's UAMI.

### 9.2. Observe pods and application behavior

```bash
kubectl get deployment orders-api -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -l app=orders-api
kubectl describe deployment orders-api -n "$NAMESPACE"

# Only view application logs designed not to print secrets or tokens.
kubectl logs deployment/orders-api -n "$NAMESPACE" --tail=100
```

The demo app should report that it **retrieved the secret metadata** or performed its authorized operation, without printing secret values to logs. A custom log message saying "token exchange successful" alone does not prove Key Vault authorized the operation; test a valid data request.

### 9.3. Negative tests

To prove least privilege, run **intentional tests in a test environment**:

| Test | Expected outcome |
|---|---|
| Pod `orders/orders-kv-reader` reads authorized secret | Succeeds |
| Another SA without a matching FIC attempts to use the same UAMI | Token exchange fails |
| An SA in namespace `payments` named `orders-kv-reader` without an FIC for `payments` | Subject mismatch, rejected |
| Orders UAMI tries reading data in another vault without authorization | Denied at authorization layer |
| Pod without the required workload identity label | Not injected by webhook per standard config |
| Key Vault allows only private endpoint while pod lacks network path | Connection fails despite valid identity/RBAC |

Never run negative tests by deleting roles or editing FICs serving production. Use lab resources, isolated identities, and reversible procedures.

## 10. When should you NOT use Workload Identity the same way?

AKS Workload Identity is ideal for **applications inside pods calling Azure data-plane APIs with Entra ID**. However, pick the right mechanism for each purpose:

| Need | Identity/permission to consider |
|---|---|
| Java pod reading Key Vault | Pod Workload Identity + Key Vault data-plane authorization |
| Pod writing to Blob Storage | Workload Identity + Storage Blob Data Contributor at appropriate scope |
| Pod sending Service Bus messages | Workload Identity + appropriate Azure Service Bus Data Sender |
| Kubelet pulling ACR images before pod starts | AKS kubelet identity / ACR integration or supported pull mechanism |
| AKS managing load balancers, subnets, or platform resources | Cluster/control-plane identity |
| Administrator deploying Kubernetes manifests | Kubernetes RBAC and control-plane Entra integration where supported |
| CI/CD deploying Helm charts | Separate pipeline identity and AKS/Kubernetes access permissions |

**Key point:** a pod **cannot use its own application Workload Identity to solve image pull failures that happen before the container starts**. Image pulling is normally handled by the node/kubelet using a separate authentication flow. If a pod is stuck in `ImagePullBackOff`, inspect node/kubelet registry auth, image name, DNS, and firewalls rather than granting Key Vault roles to the UAMI.

### 10.1. Azure RBAC is not uniform across services

Key Vault can use either the **Azure RBAC** or **access policies** permission model. Azure Storage uses data-plane roles like `Storage Blob Data Reader`/`Contributor`. Service Bus uses sender/receiver roles. A `Contributor` role at Azure Resource Manager level does not grant permission to read data across every service.

In every scenario, pick the **exact service role, exact action, and exact scope**, then verify target firewalls and private endpoints.

## 11. Common issues and investigation

### 11.1. Symptom – cause – resolution table

| Symptom | Possible cause | What to inspect |
|---|---|---|
| `AZURE_FEDERATED_TOKEN_FILE` missing in pod | Missing `azure.workload.identity/use` label, wrong Pod template, webhook did not mutate, or pod predates change | Deployment/Pod YAML, SA annotation, webhook, and recreate pod safely |
| `AZURE_CLIENT_ID` missing or wrong client ID | SA not annotated properly or pod uses wrong SA | `serviceAccountName`, `azure.workload.identity/client-id`, UAMI clientId |
| Entra returns "No matching federated identity record" | FIC issuer/subject/audience mismatch | Match real issuer URL, namespace, SA name, audience |
| Token exchange fails after switching clusters | OIDC issuer changed or FIC still points to old cluster | Fetch issuer from right AKS cluster, inspect FIC, update per process |
| Tenant/client mismatch error | Wrong UAMI or tenant selected, wrong client ID annotation | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, identity metadata |
| SDK finds no suitable credential | Outdated SDK, missing Workload Identity support, or missing env/token file | SDK version, startup logs, PodSpec injection |
| `401 Unauthorized` calling Azure service | Access token wrong audience, expired, or auth flow failed | SDK credential, resource scope/token audience, lifetime |
| `403 Forbidden` from Key Vault | Valid identity missing role, wrong permission model, or data permission | RBAC/access policy, principal ID, vault/secret scope |
| Timeout or cannot resolve Key Vault | DNS, egress, private endpoint, UDR/NSG/Azure Firewall | DNS/routes/firewalls/network connectivity from cluster |
| Pod runs yet hits `ImagePullBackOff` | Registry pull by kubelet/node failed | ACR role for kubelet, image tag, network, and registry credentials |
| One pod works while another fails | Different namespace, SA, annotation, label, or identity | Compare PodSpec, SA, FIC, and roles |
| Old pod still fails after fixing ServiceAccount | Admission mutation and projected token are not updated as desired on existing pod | Roll out new pod / restart Deployment per process |

Specific error messages depend on Azure Identity SDK version, Azure service, Kubernetes version, and logging setup. Never assume from the table that "403 always means missing role": networking layers, firewalls, and target services can emit different errors.

### 11.2. Sequential investigation workflow

1. **Identify app and namespace:** which Pod/Deployment is failing, and which ServiceAccount is it using?
2. **Check pod mutation:** is `azure.workload.identity/use` on the Pod template? Do the projected token volume and environment variables exist?
3. **Check OIDC issuer:** are OIDC issuer and workload identity enabled on the cluster? Does the FIC match the exact issuer?
4. **Check subject and audience:** any case, naming, or separator mismatch in namespace/SA?
5. **Check managed identity:** does the annotated Client ID match the UAMI? Does that UAMI's Principal ID hold the Azure RBAC assignment?
6. **Check SDK:** does the app use an Azure Identity version supporting Workload Identity and reading the token file properly?
7. **Check target service:** Azure RBAC/access policies, scope, data-plane actions, and permission propagation delay.
8. **Check networking:** are OIDC/Entra token endpoints and target services reachable via DNS, routes, firewalls/private endpoints?
9. **Test real requests:** can the pod perform permitted data operations while unauthorized operations remain blocked?
10. **Apply minimal fix:** fix the exact annotation/FIC/role/network issue, roll out a new pod revision when needed, and record evidence.

### 11.3. Do not log JWTs for debugging

Projected ServiceAccount tokens contain claims such as issuer, subject, audience, and timestamps. While claims help diagnostics, **the raw JWT is a bearer token** and must never be pasted into chats, issue trackers, log aggregators, or emails. If claim inspection is needed in a test environment, use approved tools with restricted access and never expose sensitive data publicly.

Recording these fields is usually sufficient: UTC timestamp, AKS cluster, namespace, SA name, UAMI client/principal ID, FIC name, Key Vault resource ID, error code, and the target service's request/correlation ID.

## 12. Lifecycle management and credential rotation

### 12.1. Deleting or renaming a ServiceAccount

An FIC references a **subject** bound to namespace and ServiceAccount. If you rename an SA, switch namespaces, or move a workload to another cluster, you must create/update a **new federated credential** matching the new issuer and subject. A deployment using a new SA will not automatically inherit permissions just because the old UAMI still exists.

For safe migration:

1. Create the new SA/FIC for the new target, scope permissions, and verify token exchange.
2. Deploy a canary pod using the new identity and test Azure service access.
3. Shift traffic/workloads per plan.
4. Revoke old FICs/role assignments once no dependent workloads remain.
5. Check issued tokens, logs, and running workload health.

### 12.2. Deleting a user-assigned managed identity

A UAMI is an independent Azure resource. Deleting a Deployment or ServiceAccount **does not delete the UAMI**. A UAMI may also be shared by multiple workloads or FICs; deleting it without an inventory can break token acquisition for other pods.

To revoke Azure access, delete the relevant role assignments or FICs per policy. Understand the difference between **stopping new token issuance** and **invalidating already-issued access tokens**; immediate revocation depends on token lifetimes and target service capabilities.

### 12.3. Switching clusters or recreating AKS

The OIDC issuer is part of the trust relationship. When a new cluster has a different issuer, old FICs will not authenticate new tokens. Any DR or cluster migration plan must include:

- Fetching the replacement cluster's issuer URL.
- Provisioning matching FICs for critical SAs.
- Confirming the UAMI's Azure RBAC remains valid for the right scope and tenant.
- Verifying webhook injection on the new cluster.
- Testing live data requests before shifting production traffic.

Never copy ServiceAccount YAML from an old cluster and assume federation still works without checking the FIC issuer.

## 13. Monitoring and safe governance

AKS Workload Identity sits on the boundary between **Kubernetes and Microsoft Entra ID**. Telemetry sources can include:

| Layer | Signals to monitor | Purpose |
|---|---|---|
| Kubernetes | Pod/deployment events, webhook behavior, ServiceAccount changes | Detect injection failures, SA changes, and mutation issues |
| Application | Token acquisition failures, request latency, dependency errors | Separate auth, authorization, and network faults |
| Azure IAM | UAMI, FIC, and role assignment changes via Activity Log | Track who expands or revokes permissions |
| Microsoft Entra ID | Workload identity/sign-in events where licensed/available | Analyze token exchanges and trust failures |
| Key Vault / Storage / target service | Diagnostic logs, access denied events, request IDs | Verify data-plane authorization |
| AKS networking | DNS, egress/Firewall, private endpoints, network policies | Catch network path failures |

Configure alerts for adding new FICs to sensitive UAMIs, widening role assignment scopes, spikes in token-exchange failures, and data access from unapproved workloads.

### 13.1. Change control

- Manage AKS settings, UAMIs, FICs, and role assignments via peer-reviewed **Infrastructure as Code**.
- Manage Kubernetes ServiceAccounts, Deployments, and policies via manifests/Helm/GitOps rather than ad-hoc edits.
- Record owner, environment, namespace, ServiceAccount, purpose, and scope for each identity.
- Check namespace, SA name, and AKS issuer impacts before applying manifests.
- Use audit logs and secret-safe diagnostics; never emit Entra tokens or Kubernetes JWTs into logs.

**Having an FIC does not mean everyone can use that identity.** The permission surface also includes anyone who can create pods in that namespace, edit SAs, modify identity resources, or grant themselves roles. Review this combined permission surface together.

## 14. Security principles to enforce in production

### 14.1. Grant each workload only the permissions it needs

For instance, `orders-api` only reads secrets, so `Key Vault Secrets User` at the narrowest valid scope is far better than vault-wide admin. If a pod only publishes events, pick a sender role rather than Service Bus namespace admin.

An auditable policy table:

| Workload | ServiceAccount | UAMI | Azure resource | Permission |
|---|---|---|---|---|
| `orders-api` | `orders/orders-kv-reader` | `mi-orders-kv-prod` | Key Vault/secrets for orders | Read secrets only |
| `payments-api` | `payments/payments-kv-reader` | `mi-payments-kv-prod` | Key Vault/secrets for payments | Read secrets only |
| `orders-worker` | `orders/orders-bus-sender` | `mi-orders-bus-prod` | Target Service Bus queue/topic | Data Sender |
| `report-export` | `reporting/reports-blob-writer` | `mi-report-export-prod` | Report output Storage container | Write data as needed |

The rule is **every identity has a clear purpose, owner, and scope**; individual pod replicas do not each need separate UAMIs. Replicas of the same deployment can share a ServiceAccount/UAMI when performing the same role with the same permissions. For two apps with different responsibilities or data, separate their identities and authorization boundaries.

### 14.2. Restrict who controls ServiceAccounts

Anyone able to edit a Deployment to set `serviceAccountName: orders-kv-reader`, or edit a ServiceAccount's annotations, can influence which identity a pod receives. Therefore:

1. Restrict namespace Kubernetes RBAC; never grant unconstrained pod/deployment creation to untrusted groups.
2. Use admission policies and workload security controls to constrain permitted ServiceAccounts.
3. Restrict permissions to modify FICs, managed identities, and Azure role assignments.
4. Audit which operators, pipelines, and GitOps controllers can alter manifests.
5. Alert on privilege-escalating edits and deployments outside approved pipelines.

A label or annotation **provides zero security barrier** if arbitrary users can modify it. Kubernetes API authorization and manifest review are indispensable.

### 14.3. Protect projected tokens inside containers

While not a long-lived static secret, a projected token can still be **used as a bearer credential** during its validity window. You should:

- Never read or print `AZURE_FEDERATED_TOKEN_FILE` to stdout, crash reports, or HTTP responses.
- Avoid mounting the token volume into sidecars or containers that do not need permissions, where configurable.
- Restrict container filesystem and execution privileges, enabling Pod Security controls per organizational standards.
- Never let untrusted pods share privileged ServiceAccounts.
- Keep SDKs and OS/container base images updated; scan images before release.
- Configure NetworkPolicy and egress policies to limit token abuse if a pod is compromised.

If an app needs multiple identities for different services, split workloads or use Azure-supported identity/credential patterns. Never assume the webhook automatically injects multiple simultaneous identities into one pod without explicit support.

### 14.4. Exercise care when granting Key Vault or Storage permissions

**Successful authentication** alone does not guarantee safety:

- Avoid granting vault-wide read access to a UAMI when only a small set of secrets is needed and policy supports narrower scoping.
- For Blob storage, use `Storage Blob Data Reader` for read-only workloads; grant `Contributor` only when writes are required.
- When data sits behind a private endpoint, design DNS, routing, firewalls, and network resiliency.
- For sensitive actions, capture audits and alerts rather than relying solely on token exchange working.
- When revoking access, check inherited role assignments at subscription/resource group levels as well as legacy access models.

### 14.5. Separate dev, test, and prod

Never reuse a production UAMI for test pods whenever avoidable. A clean, controllable layout:

```text
aks-orders-dev    -> orders/orders-kv-reader -> mi-orders-kv-dev
aks-orders-test   -> orders/orders-kv-reader -> mi-orders-kv-test
aks-orders-prod   -> orders/orders-kv-reader -> mi-orders-kv-prod
```

Even though namespace/SA names match, **distinct OIDC issuers across AKS clusters** and dedicated UAMIs prevent permissions in one environment from spilling into another. If sharing one UAMI across clusters is unavoidable, document every FIC and the blast radius if one cluster is compromised.

## 15. Operating multiple workload types: Deployment, CronJob, and Job

### 15.1. Deployments with multiple replicas

A `Deployment` with three replicas normally creates three pods sharing **the same ServiceAccount** in the pod template. Each pod receives a projected ServiceAccount token via Kubernetes and exchanges it with Entra ID as needed.

Never create three separate federated credentials just because there are three replicas with the same issuer/subject/audience. FICs bind to the ServiceAccount, not pod names or replica indices.

### 15.2. CronJobs using Workload Identity

A `CronJob` creates a `Job`, which creates pods. The label and ServiceAccount must sit inside the **Job's pod template**, not only on CronJob metadata:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
  namespace: reporting
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            azure.workload.identity/use: "true"
        spec:
          serviceAccountName: reports-blob-writer
          restartPolicy: Never
          containers:
            - name: report
              image: acrordersdev001.azurecr.io/report-export:1.0.0
```

You must create ServiceAccount `reporting/reports-blob-writer`, its FIC, and Storage roles beforehand; this YAML only illustrates where the label and SA go. The image must exist and pull permissions must be handled separately. Even if a CronJob runs only a few minutes daily, never attach an overly broad administrative UAMI.

### 15.3. Sidecars and init containers

When a Pod has multiple containers, assess which containers genuinely need Azure credentials. Mutating webhooks and projected volumes can expose identity details across containers depending on service configuration; never assume every sidecar is safe sharing a pod and token volume. Check webhook versions, container-skip annotations if supported, and separation of concerns across containers.

Avoid using an init container with privileged secret-reading permissions to dump secrets into an unprotected shared volume for the pod's lifetime. Whenever appropriate, let the main application call Azure services directly via SDK and managed identity rather than creating unnecessary credential copies.

## 16. Infrastructure as Code and release pipelines

For production systems, manage both sides of AKS Workload Identity:

1. **Azure side:** AKS OIDC/workload identity settings, user-assigned identities, federated identity credentials, Azure RBAC, Key Vault/Storage/Service Bus.
2. **Kubernetes side:** namespaces, ServiceAccounts, annotations, Deployment/CronJob pod labels, network policies, and admission/security settings.

An ordered deployment sequence:

```text
1. AKS ready + OIDC issuer + workload identity enabled
                         |
                         v
2. Create user-assigned managed identity
                         |
                         v
3. Create FIC with exact issuer/subject/audience
                         |
                         v
4. Assign data-plane Azure RBAC on target resource/scope
                         |
                         v
5. Create namespace + annotated Kubernetes ServiceAccount
                         |
                         v
6. Deploy Pod template with workload identity label
                         |
                         v
7. Canary test token exchange + Azure data access + deny test
                         |
                         v
8. Production rollout and monitoring
```

**Not every step should be run manually.** Use Bicep/ARM/Terraform for Azure resources and Helm/Kustomize/GitOps for Kubernetes manifests. Regardless of tooling, orchestrate **dependencies** among OIDC issuer, FIC, client ID, role assignments, and pods.

### 16.1. Documenting the identity mapping

A **conceptual** manifest (not a directly deployable schema):

```yaml
cluster: aks-orders-prod
namespace: orders
serviceAccount: orders-kv-reader
oidcIssuer: "<issuer-url-from-cluster>"
managedIdentity:
  name: mi-orders-kv-prod
  clientId: "<client-id>"
federatedCredential:
  subject: "system:serviceaccount:orders:orders-kv-reader"
  audience: "api://AzureADTokenExchange"
azurePermissions:
  - resource: "<key-vault-resource-id>"
    role: "Key Vault Secrets User"
owner: orders-platform-team
```

Maintaining this mapping helps identify unused FICs, avoid tenant mix-ups, and verify permissions after cluster or app migrations. Never store tokens, client secrets, or Key Vault secret values in such manifests.

### 16.2. Rollback and safe changes

Modifying an FIC or role can prevent newly created pods from acquiring tokens. Safe practices:

- Create new roles/FICs and validate with a canary before cutting over old flows when changing identities.
- Never delete an old FIC while other workloads still rely on that issuer/subject.
- Roll out with clear health checks and error visibility.
- Watch for token errors and Key Vault/Storage access-denied responses post-deployment.
- Once migration finishes, decommission legacy configs and roles per policy.

Never roll back by stuffing a client secret into a Kubernetes Secret to avoid fixing the real issue; that reintroduces the exact risk Workload Identity eliminates.

## 17. Cost impact and scalability

AKS Workload Identity is primarily an **identity and federation mechanism**, not an extra worker pool like a node pool. Still, the overall architecture incurs costs across:

| Component | Cost/limit factors to consider |
|---|---|
| AKS | Node VMs, disks, networking, control plane tier, and monitoring per usage |
| Microsoft Entra/identity | Identity/monitoring features and licensing terms of related services |
| Key Vault/Storage/Service Bus | Operations, storage capacity, throughput, logs, and networking |
| Networking | Private endpoints, NAT, Firewalls, DNS, and data transfer |
| Observability | Log Analytics ingestion, retention, metrics, and alerts |
| Federation operations | Number of identities/FICs, permission governance, policies, and testing |

Do not assume every token exchange has a separate VM-like billing meter; check official pricing and service quotas for your tenant/services. At large workload scales, bottlenecks typically stem from **identity governance, FIC and role assignment quotas, token acquisition latency, or target service endpoint limits**, not Kubernetes manifest overhead.

To operate efficiently:

- Share one ServiceAccount/UAMI across replicas that genuinely share the same purpose and permissions rather than creating redundant identities per replica.
- Rely on SDK token caching and refresh rather than fetching tokens on every business request.
- Govern FIC counts organization-wide and avoid casually reusing UAMIs across environments.
- Track metrics for auth errors, permission errors, Key Vault latency, and pod status.
- Prune unused UAMIs, FICs, and roles no longer tied to active workloads.

## 18. Scenario exercises

### Scenario A: API reading secrets only

A production AKS cluster has namespace `orders`, Deployment `orders-api`, and Key Vault `kv-orders-prod` using Azure RBAC. Requirement: only the API pods may read required secrets; zero client secrets stored.

**Tasks:**

1. Choose the managed identity type and explain why.
2. Determine the exact subject for ServiceAccount `orders-kv-reader`.
3. Describe the issuer and audience in the FIC.
4. Identify the least-privilege data role on Key Vault.
5. Specify where the annotation goes on the ServiceAccount and the label on the Pod template.
6. Outline what to check if application logs return `403`.

**Solution guide:** use a dedicated UAMI for `orders` (or an equivalently scoped identity); FIC with subject `system:serviceaccount:orders:orders-kv-reader`, exact AKS OIDC issuer, and matching token exchange audience. SA carries `azure.workload.identity/client-id`; Pod template carries `azure.workload.identity/use: "true"`. Assign secret-reading role at the narrowest valid scope, then verify vault permission model/RBAC, principal, DNS, and private endpoints.

### Scenario B: namespace rename breaks authentication

An operations team moves a Deployment from `orders` to `orders-v2`, keeping the same ServiceAccount name and client ID. Pods are mutated, yet Entra token exchange fails.

**Question:** Why wasn't editing the namespace in the manifest enough? What must change and how do you verify?

**Solution guide:** the old FIC subject is `system:serviceaccount:orders:orders-kv-reader`, whereas the new token presents `system:serviceaccount:orders-v2:orders-kv-reader`. Create or update the matching FIC, canary test, and clean up the old FIC per process—never widen data permissions to work around a subject mismatch.

### Scenario C: Key Vault works from laptop but fails inside pod

A developer runs `az login` on a laptop and reads Key Vault successfully, yet the Java API in AKS fails. The laptop uses the human user's permissions; the pod must use the UAMI.

**Tasks:** explain how to distinguish whether:

- The Workload Identity webhook failed to inject the token.
- The FIC issuer/subject/audience does not match.
- The UAMI lacks the Key Vault role.
- Key Vault is blocked by networking/private endpoints.
- The Java SDK is outdated or picked the wrong credential.

**Solution guide:** inspect PodSpec/SA, AKS issuer, FIC, UAMI client/principal ID, Key Vault permissions, and SDK. Laptop tests do not prove the pod's identity has access. Keep logs safe without printing JWTs or secret values.

### Scenario D: multiple teams sharing one UAMI

Three namespaces—`orders`, `payments`, and `hr`—share one UAMI with permission to read all secrets. A pod belonging to HR is compromised.

**Tasks:** assess the blast radius and propose migrating to separate UAMIs/FICs/roles, designing admission/RBAC protections around ServiceAccounts, a rollout plan, and revoking legacy permissions.

**Solution guide:** split UAMIs by domain/data boundary, scope Azure roles to specific vaults/secrets, define FICs per issuer and subject, roll out via canary, test that out-of-scope access is denied, then revoke unneeded shared FICs and roles.

## 19. Self-check questions

**1. Does a Kubernetes ServiceAccount automatically grant Azure Key Vault access?** No. It provides a Kubernetes identity; it requires federation with a managed identity and Azure service permissions.

**2. What are the three most important FIC fields?** Issuer, subject, and audience.

**3. What is the subject for SA `orders-kv-reader` in namespace `orders`?** `system:serviceaccount:orders:orders-kv-reader`.

**4. Does annotation `azure.workload.identity/client-id` take the Client ID or Principal ID?** The Client ID of the managed identity.

**5. Which pod label is normally required for the workload identity webhook to mutate a pod?** `azure.workload.identity/use: "true"` placed on the Pod template.

**6. Does Workload Identity solve kubelet pulling private images from ACR?** Not directly; image pulling uses a separate node/kubelet/registry authentication flow.

**7. Does a successful Entra token exchange prove the pod can read a Key Vault secret?** No. Key Vault still evaluates roles/access policies and network conditions.

**8. Why can changing a namespace break federation?** The ServiceAccount token subject includes the namespace; the FIC must match the new subject.

**9. Is a user-assigned identity deleted when a Deployment is deleted?** No. A UAMI is an independent Azure resource requiring its own cleanup lifecycle.

**10. Why use the Java Azure Identity SDK instead of manually reading the token once?** The SDK handles token exchange, caching, and refreshing using compatible mechanisms.

## 20. Production checklist

- [ ] AKS runs a supported version with OIDC issuer and Workload Identity enabled per process.
- [ ] Issuer URL retrieved from the **exact target cluster**, never guessed from cluster names.
- [ ] Chose a user-assigned identity or supported federation model with a documented owner.
- [ ] FIC has exact issuer, subject, and audience; audited for duplicate/unused FICs.
- [ ] Distinguished UAMI Resource ID, Client ID, and Principal/Object ID.
- [ ] Azure RBAC/data-plane permissions granted for exact actions and scope; avoided admin roles for data reading.
- [ ] Verified Vault/Storage/Service Bus permission models and network conditions.
- [ ] Kubernetes ServiceAccount holds the accurate client ID annotation.
- [ ] Pod template includes `azure.workload.identity/use: "true"` and the exact `serviceAccountName`.
- [ ] Newly created pods are mutated by the webhook with projected tokens and required environment variables.
- [ ] Applications use compatible Azure SDKs; tokens and secret values are never logged or hardcoded.
- [ ] Tested token exchange and real Azure operations alongside negative out-of-scope tests.
- [ ] Kubernetes RBAC/admission policies prevent unauthorized workloads from picking privileged ServiceAccounts.
- [ ] Pod identity kept distinct from AKS cluster identity and kubelet identity.
- [ ] Accounted for token refresh, RBAC propagation, webhook mutation on rollout, and network outages.
- [ ] Configured logging, alerts, CI/CD/IaC, runbooks, and plans for cluster/namespace/identity changes.
- [ ] Checked FIC count limits, identity quotas, performance, and related resource costs.
- [ ] Prepared safe production migration, rollback, and old-permission revocation procedures.

## Conclusion

**AKS Workload Identity** pairs an **OIDC-based Kubernetes ServiceAccount token** with a Microsoft Entra ID **federated identity credential** so pods receive an **Azure access token** for an approved identity. This lets applications access Key Vault, Storage, Service Bus, and other supported services **without storing client secrets inside containers**. Yet a successful token exchange is only half the story: target resources still enforce Azure RBAC or their own authorization models alongside network controls.

To operate securely, ensure **issuer–subject–audience match exactly**, ServiceAccounts carry the right client ID annotation, Pod templates carry the workload identity label, apps use compatible SDKs, and Azure permissions follow least privilege. Combined with Kubernetes RBAC, admission controls, projected token protection, CI/CD, logging, and identity lifecycle management, Workload Identity forms a reliable authentication foundation for applications running on AKS.
