# Secret Management with Azure Key Vault Integration

An application running on **Azure Kubernetes Service (AKS)** needs database connection strings, API tokens, and TLS certificates. Putting these values inside a `Dockerfile`, ConfigMap, or Git repository exposes sensitive information to unintended readers. Moving them into a Kubernetes Secret can improve configuration handling, yet without proper access controls, encryption, and lifecycle management, secret-exposure risks remain.

**Azure Key Vault** is Azure's service for managing secrets, keys, and certificates. On AKS, a common integration is the **Secrets Store CSI Driver with the Azure Key Vault Provider**: Pods read values from Key Vault via **file-based volumes**, instead of forcing every value into Kubernetes Secrets. Access identities can be granted via **managed identity** or **Microsoft Entra Workload Identity**, depending on design and supported features.

This lesson belongs to the **Azure Kubernetes Service Fundamentals** chapter in the `CLOUD_PROVIDERS_AZURE` module. The module guides learners through Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, while deploying, monitoring, protecting, and controlling costs for application architectures. Here, the focus is **secure secret management for AKS workloads**, not tricks for stuffing passwords into Kubernetes manifests.

> Add-on names, Azure CLI flags, Key Vault RBAC rules, and CSI rotation capabilities can vary by AKS/driver/provider version. Examples use placeholders and contain no real credentials. When working in live environments, always verify subscription, cluster, namespace, permissions, and matching feature docs.

## 1. Learning objectives

After this lesson, you can:

1. Distinguish **Kubernetes Secret**, **Azure Key Vault secret**, **Key Vault key**, and **Key Vault certificate**.
2. Explain the path of a secret from Key Vault to a container via the **Secrets Store CSI Driver**.
3. Enable or verify the **Azure Key Vault Secrets Provider add-on** on AKS using supported mechanisms.
4. Compare the **add-on managed identity** with **Microsoft Entra Workload Identity**.
5. Create a `SecretProviderClass` and a Pod mounting a CSI volume **without hardcoding secret values**.
6. Know when **syncing to a Kubernetes Secret** is needed, along with its security and lifecycle implications.
7. Design rotation, refresh, rollback, and handling when Key Vault is unreachable.
8. Govern Key Vault permissions, Kubernetes RBAC, service accounts, networking, and auditing.
9. Use Azure CLI/`kubectl` to verify configurations and troubleshoot mount errors.
10. Build safe, observable, and recoverable operational workflows.

## 2. Why not put passwords directly in images or YAML?

Consider three configuration patterns:

| Approach | Example | Primary risk |
|---|---|---|
| Hardcoded in source/image | `DB_PASSWORD=real-password` in Dockerfile or source code. | Secrets persist indefinitely across image layers, Git history, and build artifacts. |
| Plaintext in Pod/ConfigMap | `env.value: real-password`. | Anyone able to read manifests or pipeline logs sees the value. |
| Reference secret from managed store | `SecretProviderClass`, CSI volume, identity, Key Vault. | Reduces value copying, though permissions and runtime still require protection. |

With real secrets, **never** commit them to Git—not even in a commit immediately reverted afterward; commit history, CI logs, or caches may already retain the value. If exposure is suspected, **revoke/rotate** the credential rather than just deleting the password line.

### Secrets are not ordinary configuration parameters

- **Non-sensitive parameters:** environment name, log level, timeouts → regular ConfigMaps/env vars where appropriate.
- **Secrets:** passwords, API keys, private keys, sensitive credentials/certificates → dedicated protection mechanisms.
- **Identity-based access:** if the target service supports Microsoft Entra authentication, you may **need no password at all**. This is generally preferable to creating extra secrets merely to prove integration.

## 3. What object types does Key Vault store?

| Type | Purpose | Examples |
|---|---|---|
| **Secret** | Stores sensitive strings/byte values per API support. | Database password, API token, connection string. |
| **Key** | Manages cryptographic keys and supported crypto operations. | Key encryption key, signing key. |
| **Certificate** | Manages certificates and related lifecycles. | TLS certificates, cert chains, private keys in supported configs. |

**A Key Vault secret is not the same as a Kubernetes Secret.** Key Vault is an external service with its own versioning, policies, and audits. A Kubernetes Secret is an object in the Kubernetes API stored/synced by the cluster control plane.

Do not assume fetching a certificate/key via CSI automatically produces the exact PEM/PFX format every application expects. Mounted content depends on **`objectType`, object kind, provider-supported formats, and conversion settings**. When handling private keys, carefully check file read permissions and cert structure, and never print private keys to logs.

## 4. Integration architecture: AKS – Secrets Store CSI Driver – Key Vault

Conceptual flow:

```text
                  Microsoft Entra ID
                          |
             Managed identity / Workload Identity
                          |
                          v
                     Azure Key Vault
                      secret / key / cert
                          ^
                          | authorized object fetch request
                          |
AKS cluster               |
┌──────────────────────────────────────────────────────┐
│ Node                                                 │
│  Secrets Store CSI Driver + Azure Key Vault Provider │
│       |                                              │
│       | CSI volume mount                             │
│       v                                              │
│  Pod: orders-api                                     │
│    /mnt/secrets-store/db-password (file, read-only)  │
│       |                                              │
│       v                                              │
│  Application reads secret file                       │
└──────────────────────────────────────────────────────┘
```

Key components:

1. **Key Vault:** source of values and access policies.
2. **AKS add-on:** installs and manages Secrets Store CSI Driver components plus the Azure provider per AKS model.
3. **SecretProviderClass:** Kubernetes custom resource specifying which vault, which objects, object types, and identity mode.
4. **Pod CSI volume:** declares the mount referencing the `SecretProviderClass`.
5. **Identity:** authorizes the provider to read objects from Key Vault per granted permissions.
6. **Kubernetes RBAC / Pod security:** restricts who can deploy Pods mounting secrets and who can read secret files inside containers.

**When an application reads CSI files directly, no Kubernetes Secret is required.** Syncing to a Kubernetes Secret is strictly optional when an app or controller requires the Kubernetes Secret interface.

### Where does `SecretProviderClass` live?

`SecretProviderClass` is a **namespaced resource**. A Pod normally must reference a `SecretProviderClass` in the **same namespace**. Vault names, object names, and identities are not guessed from filenames; they must match approved configuration.

## 5. How do Kubernetes Secrets and CSI-mounted secrets differ?

| Criterion | Standard Kubernetes Secret | CSI mount from Azure Key Vault |
|---|---|---|
| Data source | Object managed by the Kubernetes API. | Key Vault object fetched via CSI provider. |
| How apps consume it | Env var or volume. | File inside a CSI volume, or optional sync to Kubernetes Secret. |
| Primary storage | Cluster control plane / etcd per Kubernetes model. | Key Vault; file mounted on node/Pod via CSI mechanism. |
| Value creation | API or sync/automation tools. | Vault + identity + `SecretProviderClass`. |
| Rotation | Must update object and handle app refresh. | Supports rotation/remount when enabled; app must handle file updates. |
| Attack surface | RBAC for Kubernetes Secrets, Pod/service account rights. | Key Vault authorization, pod/CSI config, and runtime file permissions. |
| Specific risk | Base64 values easily mistaken for encryption. | Mount fails if identity, Key Vault, network, or provider fails. |

**Base64 is not encryption.** The `data:` field in a Kubernetes Secret is base64-encoded for API transport. Anyone authorized to read the Secret and decode base64 retrieves plaintext. For strict security, govern Kubernetes RBAC, control-plane encryption at rest per platform support, and the entire secret creation/distribution pipeline.

CSI mounts eliminate copies of secrets in the Kubernetes API **only when Secret sync is disabled**. Values still appear on the **Pod's runtime filesystem** and can be read by processes with permission; it is not a "zero plaintext anywhere" magic shield.

## 6. Authentication options with Azure Key Vault

Two common options on AKS:

### A. Managed identity tied to the add-on/node infrastructure

When enabling the AKS Azure Key Vault Secrets Provider add-on, AKS typically creates a **user-assigned managed identity** for the add-on in the **node resource group** and configures it for the provider where supported.

Pros:

- Quick to set up; fits labs or clusters needing a simple start.
- May avoid creating per-app federated credentials under the managed identity config.

Considerations:

- An add-on/node-scoped identity has a broader shared infrastructure scope than a single workload.
- If granted read access to too many secrets, workloads able to reference the same identity per cluster permissions create lateral access risks.
- Administrators must remember **client ID and principal ID differ**: client ID is used in provider configs, while principal/object ID is used for Azure role assignments.

### B. Microsoft Entra Workload Identity

**Workload Identity** links a **Kubernetes ServiceAccount** to a Microsoft Entra identity via **OIDC issuer + federated identity credential**. Key Vault read permissions are granted to each workload's dedicated identity.

Pros:

- Cleanly isolates permissions per application, namespace, and service account.
- Avoids embedding Entra client secrets inside Pods.
- Ideal when multiple applications hold different secret scopes.

Prerequisites:

1. AKS enables **OIDC issuer** and **workload identity**.
2. Managed identity or suitable Entra object created as the workload identity.
3. Federated credential matching exact **issuer, audience, and subject**.
4. ServiceAccount annotated with the right client ID.
5. Pod carrying the Workload Identity label and right `serviceAccountName`.
6. `SecretProviderClass` selecting the matching identity.
7. Identity granted **Key Vault object read permissions** with network reachability to the vault.

**Workload Identity does not replace the CSI Driver.** Workload Identity solves **authentication**, while the CSI Driver / Key Vault provider solves **fetching secrets and mounting files**.

### Which option to pick?

| Scenario | Recommended approach |
|---|---|
| Small lab, testing a single secret mount, few teams | Add-on managed identity. |
| Multiple teams/namespaces with distinct vaults and policies | Per-service-account Workload Identity. |
| App calls Key Vault SDK directly without needing file mounts | Workload Identity + SDK + vault permissions; CSI is optional. |
| Legacy workload/controller requiring a Kubernetes Secret | CSI + optional sync, carefully weighing data exposure surface. |

## 7. Key Vault permissions: control plane differs from data plane

An identity holding permissions in Azure Resource Manager **does not automatically have permission to read secret values**. In Key Vault, resource management and data access are separate layers depending on the vault's permission model.

| Permission | What does it allow? | Example |
|---|---|---|
| Azure RBAC resource management | Create/edit vaults and ARM settings per role. | An Azure admin role at the appropriate scope. |
| **Key Vault Secrets User** | Read secret values under Key Vault's Azure RBAC model. | Used by provider to fetch `db-password`. |
| Key Vault key/certificate permissions | Access keys/certificates by object type and operation. | Corresponding roles/permissions; never inferred from Secrets User. |
| Kubernetes RBAC | Create Pods, ServiceAccounts, `SecretProviderClass`, read Kubernetes Secrets. | Role within a namespace. |
| In-container permissions | Read mounted files, open connections to target systems. | User/group IDs, volume mounts, and Pod security policies. |

If a vault uses the **Key Vault access policy model** instead of Azure RBAC, permissions must follow access policies. Never scatter both models randomly, and never assume an ineffective role assignment means "Key Vault is broken" before checking the active permission model.

### Principle of least privilege

- Grant **secret read-only** access to identities that only need to read.
- Separate vaults and identities by product group or security boundary when feasible.
- Never share one identity capable of reading every secret across Production and Development.
- Restrict who can create/modify `SecretProviderClass` and Pods to workload owners.
- Audit and prune role assignments when apps retire or switch namespaces.

**A `SecretProviderClass` name is not a security barrier.** Anyone allowed to create Pods can reference volumes/identities allowed in that namespace; Azure and Kubernetes permissions must be designed together.

## 8. Prerequisites for a safe lab

Assume our learning environment has:

| Resource | Illustrative value |
|---|---|
| AKS resource group | `rg-aks-lab` |
| Cluster | `aks-lab` |
| App namespace | `orders` |
| Key Vault | `kv-orders-lab` |
| Key Vault secret | `orders-db-password` |
| Managed identity | `mi-orders-reader` or add-on identity |
| `SecretProviderClass` | `kv-orders` |
| Container mount path | `/mnt/secrets-store` |
| File inside Pod | `/mnt/secrets-store/orders-db-password` |

You need:

1. Azure CLI, `kubectl`, and compatible extensions for your AKS cluster.
2. Permissions on AKS and the Kubernetes namespace to configure add-ons, identities, and Pods for the lab.
3. Minimal permissions to manage role assignments and access Key Vault per organizational workflow.
4. Running cluster, sufficient node capacity, and DNS/network connectivity to Key Vault.
5. A **dummy secret**, never a real Production credential.
6. Approved sandbox environment and cost limits.

Before any write action, confirm cluster context:

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

kubectl config current-context
kubectl get nodes
```

`kubectl get nodes` only checks Kubernetes API connectivity and node state; it **does not prove** Key Vault permissions or secret mounting work.

## 9. Enabling the Azure Key Vault Secrets Provider add-on

On an AKS cluster you are authorized to modify, enable the add-on via Azure CLI:

```bash
az aks enable-addons \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --addons azure-keyvault-secrets-provider
```

**This command modifies the cluster** and must run only in an authorized lab/cluster. AKS manages add-on components under its service model; never manually install a conflicting CSI driver alongside it without understanding compatibility.

### Inspect the add-on

```bash
az aks show \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --query "addonProfiles.azureKeyvaultSecretsProvider" \
  --output json

kubectl get csidriver
kubectl get secretproviderclass --all-namespaces
```

Expect a CSI driver named `secrets-store.csi.k8s.io` and Azure provider components once enabled. Seeing zero `SecretProviderClass` objects initially is normal: operators **create those later** per app, not the add-on automatically.

### Add-on identity

After enabling the add-on, AKS may provision an identity for the provider. Read `identity.clientId` / `identity.objectId` from the returned metadata according to the add-on's schema. **Never guess a client ID** from a managed identity name.

Verification checklist:

- Add-on reports enabled/succeeded.
- Driver/provider Pods or DaemonSets are running on target nodes.
- Captured the client ID of the vault-access identity.
- Key Vault granted read permission to the exact principal.
- Nodes/pods have a network path to the vault at mount time.

## 10. Model 1: `SecretProviderClass` using add-on managed identity

After creating the Key Vault secret and granting permissions to the add-on identity, create a `SecretProviderClass` in namespace `orders`.

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: kv-orders
  namespace: orders
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    useVMManagedIdentity: "true"
    userAssignedIdentityID: "<ADDON_IDENTITY_CLIENT_ID>"
    keyvaultName: "<KEY_VAULT_NAME>"
    tenantId: "<ENTRA_TENANT_ID>"
    objects: |
      array:
        - |
          objectName: orders-db-password
          objectType: secret
          objectVersion: ""
```

Field explanation:

| Field | Meaning |
|---|---|
| `provider: azure` | Selects the CSI driver's Azure Key Vault provider. |
| `useVMManagedIdentity: "true"` | Uses the VM/node-attached managed identity as supported by the provider. |
| `userAssignedIdentityID` | Client ID of the user-assigned identity to use. |
| `keyvaultName` | Name of the Key Vault holding the object. |
| `tenantId` | Microsoft Entra tenant hosting the vault/identity per configuration. |
| `objects.array[].objectName` | Object name in Key Vault. |
| `objectType: secret` | Specifies a Key Vault **secret**, not key or certificate. |
| `objectVersion: ""` | Does not pin to a specific version per provider syntax. |

**Permission note:** valid YAML does not replace granting read permissions to the identity. Without Key Vault permissions or with blocked egress, the Pod fails at mount time.

### Why distinguish secret name from filename?

In this example, `orders-db-password` appears as a file inside the mount path per provider naming rules. If you set **`objectAlias`**, the mounted filename becomes the alias instead of `objectName`; when syncing to a Kubernetes Secret, reference the mounted filename accurately.

## 11. Pod mounting the secret as a read-only file

Using the `SecretProviderClass` above, create an illustrative Pod:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-secret-check
  namespace: orders
spec:
  containers:
    - name: checker
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: secrets-store
          mountPath: /mnt/secrets-store
          readOnly: true
  volumes:
    - name: secrets-store
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: kv-orders
```

This Pod is solely for **verifying mounts**, not how real database passwords are created. Key lines:

- `driver: secrets-store.csi.k8s.io`: invokes the Secrets Store CSI Driver.
- `secretProviderClass: kv-orders`: looks up the resource in the same namespace.
- `mountPath: /mnt/secrets-store`: files are readable here.
- `readOnly: true`: prevents the app from modifying volume contents directly.

### Verify without exposing the secret

After creating in the lab:

```bash
kubectl -n orders get pod orders-secret-check
kubectl -n orders describe pod orders-secret-check

kubectl -n orders exec orders-secret-check -- \
  test -s /mnt/secrets-store/orders-db-password
```

`test -s` only checks that the file exists and is non-empty; **it never prints the secret value**. Avoid running `cat /mnt/secrets-store/orders-db-password` in logged terminals or screen shares.

If the Pod fails to start, inspect Pod **Events** before blaming application code. When CSI mounting fails, the Pod never reaches container startup.

## 12. Model 2: Microsoft Entra Workload Identity per application

To cleanly isolate permissions between `orders-api` and `billing-api`, use Workload Identity with dedicated service accounts.

### Enable OIDC issuer and Workload Identity on AKS

On an authorized cluster:

```bash
az aks update \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --enable-oidc-issuer \
  --enable-workload-identity
```

**This command modifies cluster configuration.** Verify version support and impact on existing workloads first. The CSI add-on must still be enabled separately when using CSI mounts.

Verify the issuer:

```bash
az aks show \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --query "oidcIssuerProfile.issuerUrl" \
  --output tsv
```

### Create identity and federated credential

Prepare a dedicated user-assigned managed identity for the workload. The federated credential must match exactly:

| Field | Example |
|---|---|
| Issuer | OIDC issuer URL returned by AKS. |
| Subject | `system:serviceaccount:orders:orders-sa` |
| Audience | `api://AzureADTokenExchange` |
| Client ID | Client ID of the user-assigned managed identity. |

Example command once the identity and namespace exist:

```bash
az identity federated-credential create \
  --resource-group "<IDENTITY_RESOURCE_GROUP>" \
  --identity-name "<WORKLOAD_IDENTITY_NAME>" \
  --name "orders-aks-federation" \
  --issuer "<AKS_OIDC_ISSUER_URL>" \
  --subject "system:serviceaccount:orders:orders-sa" \
  --audiences "api://AzureADTokenExchange"
```

This creates a trust credential and requires appropriate IAM permissions. Even a single-character difference in issuer or subject breaks token exchange.

### Kubernetes ServiceAccount

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-sa
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "<WORKLOAD_IDENTITY_CLIENT_ID>"
```

### `SecretProviderClass` using Workload Identity

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: kv-orders-wi
  namespace: orders
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    clientID: "<WORKLOAD_IDENTITY_CLIENT_ID>"
    keyvaultName: "<KEY_VAULT_NAME>"
    tenantId: "<ENTRA_TENANT_ID>"
    objects: |
      array:
        - |
          objectName: orders-db-password
          objectType: secret
          objectVersion: ""
```

Crucial difference from the earlier example: Workload Identity specifies **`clientID`** per provider configuration instead of `useVMManagedIdentity: "true"` and `userAssignedIdentityID`. Depending on provider version, verify exact supported parameters against the documentation for your installed release.

### Pod using the service account and Workload Identity label

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-wi-check
  namespace: orders
  labels:
    azure.workload.identity/use: "true"
spec:
  serviceAccountName: orders-sa
  containers:
    - name: checker
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: secrets-store
          mountPath: /mnt/secrets-store
          readOnly: true
  volumes:
    - name: secrets-store
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: kv-orders-wi
```

Verify all five pieces: **ServiceAccount annotation**, **Pod label**, **client ID in `SecretProviderClass`**, **federated credential**, and **Key Vault permissions**. Setting `serviceAccountName` alone does not authorize AKS to read the vault.

### Note on access scope

Workload Identity reduces sharing one broad identity across workloads, yet security still depends on who can **create/edit Pods, ServiceAccounts, `SecretProviderClass`, and federations**. If users can alter Pod templates to impersonate another workload, enforce Kubernetes RBAC, admission policies, and tight namespace governance.

## 13. Assigning Key Vault read roles for the exact object type

Assuming the vault uses the **Azure RBAC permission model**, the identity needs a secret-reading role.

Illustrative command:

```bash
az role assignment create \
  --assignee-object-id "<IDENTITY_PRINCIPAL_ID>" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "<KEY_VAULT_RESOURCE_ID>"
```

**This creates a role assignment**; do not run without approval. Distinguish:

- **Client ID:** application/managed identity ID used in provider parameters.
- **Principal/Object ID:** Entra object ID used when assigning Azure RBAC.
- **Vault Resource ID:** scope of the role assignment.

### Scoping roles by object type

When the provider fetches:

- **Secret:** secret read role, such as `Key Vault Secrets User` in the RBAC model.
- **Certificate:** permissions to view/read certificates and, when fetching private keys via the backing secret object, the matching permissions per object mechanism.
- **Key:** permissions to read key metadata or perform cryptographic operations as supported—do not assume `Key Vault Secrets User` covers keys.

Never copy a password role blindly for certificates or signing keys. For regulated credentials, coordinate with your security team on vault isolation, key types, scopes, and rotation.

### Verifying permissions without reading values

```bash
az role assignment list \
  --assignee "<IDENTITY_PRINCIPAL_ID>" \
  --scope "<KEY_VAULT_RESOURCE_ID>" \
  --output table
```

This is one part of verification; effective access also depends on permission model, propagation delay, deny assignments, and conditional access. Never read secret values just to verify identity plumbing.

## 14. Syncing to a Kubernetes Secret: when is it needed?

Some apps or controllers only support reading **Kubernetes Secrets** via `secretKeyRef`, `envFrom`, or the Kubernetes API. The Secrets Store CSI Driver can **sync mounted objects** into a Kubernetes Secret when `secretObjects` is configured and supported by your driver/provider version.

Extended `SecretProviderClass` example:

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: kv-orders-sync
  namespace: orders
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    useVMManagedIdentity: "true"
    userAssignedIdentityID: "<ADDON_IDENTITY_CLIENT_ID>"
    keyvaultName: "<KEY_VAULT_NAME>"
    tenantId: "<ENTRA_TENANT_ID>"
    objects: |
      array:
        - |
          objectName: orders-db-password
          objectType: secret
          objectVersion: ""
  secretObjects:
    - secretName: orders-db-credential
      type: Opaque
      data:
        - objectName: orders-db-password
          key: password
```

When a Pod consumes this `SecretProviderClass` via CSI mount, the driver creates or updates the Kubernetes Secret `orders-db-credential` holding key `password`.

A legacy app can then consume:

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-db-credential
        key: password
```

### Important consequences

1. **Data is now copied into a Kubernetes Secret.** Apply security controls to the Kubernetes API and etcd as well.
2. Kubernetes Secret syncing depends on a **Pod actively mounting the `SecretProviderClass`**; do not expect the Secret to appear merely from creating `SecretProviderClass`.
3. A volume consumer must exist per driver requirements; when no Pods mount it anymore, the synced Secret's lifecycle behaves according to driver rules.
4. With `objectAlias`, `secretObjects.data[].objectName` must match **the mounted filename**, not necessarily the original `objectName`.
5. If **environment variables** are populated from a Kubernetes Secret, running containers **do not automatically pick up new values** when the Secret updates. Restart/roll out Pods per process.
6. Never treat base64 in `kubectl get secret -o yaml` as encryption; anyone permitted to read it can decode the value.

**Prefer direct CSI file mounts** whenever applications can read secrets from files without requiring an intermediate Kubernetes Secret.

## 15. Rotation: when a secret changes, does the app receive the new one?

This is one of the most frequent causes of Production outages.

### Three separate clocks

1. **Key Vault rotation/update:** when a new secret version is created or the target credential changes.
2. **CSI provider refresh:** when the driver/provider updates the mounted file per enabled rotation and polling interval.
3. **Application refresh:** when the app process actually re-reads the file, rebuilds connection pools, or reloads TLS certificates.

```text
09:00  Secret version A in Key Vault
       Pod mounts file A, app reads A

10:00  Add secret version B in Key Vault
       ↓
10:02+ CSI rotation updates mounted file content per config
       ↓
10:05  App re-reads/reloads and switches to B
       ↓
10:15  Revoke credential A after verifying whole system
```

These timestamps are **illustrative only**, not SLA commitments. Actual timing depends on polling interval, vault connectivity, provider refresh mechanics, and application behavior.

### Enabling rotation on the add-on

On an authorized AKS cluster where supported:

```bash
az aks addon update \
  --resource-group "rg-aks-lab" \
  --name "aks-lab" \
  --addon azure-keyvault-secrets-provider \
  --enable-secret-rotation \
  --rotation-poll-interval 2m
```

This command **modifies the cluster**. The `2m` interval is an example, not a guarantee every app receives secrets in two minutes. Verify add-on type, AKS version, and supported poll intervals before applying.

### Two common traps

- **Pinned version:** if `objectVersion` pins a specific Key Vault version, adding a new version **does not update** what the provider reads until you update the config.
- **Mounting via `subPath`:** if a container mounts a secret file using `subPath`, CSI file updates may **not propagate** into the container the way mounting the full directory does. For rotation, mount the **directory** and read the path cleanly.

### App caching secrets in memory

If an application reads the password once at startup and holds it in memory forever, updating the mounted file **will not force** connection pools to switch credentials. You may need:

- Tested file-watching/reload logic.
- Rebuilding connection pools upon credential changes.
- Scheduled/approved rolling restarts.
- An **overlap window where both A and B are valid** if the target system supports it, enabling safe cutover.

## 16. TLS certificates via CSI: special considerations

Beyond passwords, the CSI provider can fetch certificates in supported formats and mount them into containers. Applications often require:

- Certificate and private key in **two separate files**.
- Complete PEM chain matching the hostname.
- File updates triggering the server to **reload its TLS context**.
- File permissions restricted to the process UID/GID.
- Avoiding simultaneous restarts of all replicas.

Therefore, for certificates:

1. Identify the exact object type/format returned by the Key Vault provider.
2. Verify paths and formatting using checks that **never print private keys**.
3. Design rotation with an overlap window where both certificate A and B are valid.
4. Test readiness and HTTPS handshakes from clients.
5. Monitor expiration well ahead of time; never wait for browser expired-cert errors.

### CSI mounts differ from Ingress Kubernetes TLS Secrets

An Ingress controller typically expects a Kubernetes Secret of type `kubernetes.io/tls`; in that case you may need Secret syncing or a controller with native Key Vault integration. Do not assume mounting a file into an application Pod updates the TLS certificate of an Ingress controller running in another Pod.

## 17. Network security between AKS and Key Vault

Even with exact identity permissions, the provider must still **reach Key Vault** and supporting identity endpoints per architecture.

Checkpoints:

- Do AKS nodes/pods resolve the vault hostname via DNS accurately?
- Do Network Security Groups, Azure Firewall, UDRs, or egress policies allow required traffic?
- If Key Vault uses a **Private Endpoint**, are the VNet and private DNS zone (e.g., Key Vault's privatelink DNS zone per design) configured properly?
- Do VNet peering / hub-spoke topologies permit routing to the private endpoint?
- Is the Key Vault firewall blocking traffic?
- Did a newly added node pool or network change alter egress paths?
- Are Entra identity/metadata endpoints reachable via supported mechanisms?

**A Private Endpoint does not grant secret-reading permissions.** It restricts network reachability, while identity and Key Vault authorization still decide whether `Get` succeeds.

### Migrating a vault from public to private

Before disabling public network access:

1. Verify AKS nodes resolve the vault name to the right private endpoint IP.
2. Verify routes and firewalls for Key Vault traffic.
3. Validate a lab workload mounting a secret over the private network.
4. Monitor CSI mounts and Key Vault logs.
5. Roll out the production change within an agreed rollback window.

Never treat a `curl` from an admin laptop as proof pods/nodes can reach a private vault; network paths and DNS differ.

## 18. Kubernetes RBAC and Pod safety

Azure RBAC on Key Vault is one layer; Kubernetes RBAC and Pod isolation form the other.

### Kubernetes permissions worth locking down

| Action | Risk if granted broadly |
|---|---|
| Create/edit Pods or Deployments | Users can launch another container to read secrets mounted via the workload's identity. |
| Create/edit `SecretProviderClass` | Users can swap Key Vault object names or configs accessible to the permitted identity. |
| Read Kubernetes Secrets | Users can read values synced into the API. |
| `kubectl exec` into Pods | Users can read mounted secret files visible to the container. |
| View logs | Can leak secrets if apps accidentally log credentials. |
| Edit ServiceAccounts/federation | Can open paths to assume other identities if permissions are loose. |

### Mitigations

- Separate namespaces per team and environment.
- Narrow Roles/RoleBindings; restrict `secrets` `get/list/watch` when unneeded.
- Enforce admission policies and Pod Security standards, blocking privileged containers.
- Never mount secrets into sidecars that don't need them.
- Avoid sharing one service account/identity across unrelated workloads.
- Use trusted, vulnerability-scanned, patched images and restrict workload creation rights.
- When strict isolation is needed, use separate clusters, node pools, subscriptions, or vaults rather than relying on namespace names alone.

**Any process permitted to read the mounted file can grab the secret.** CSI does not protect secrets from an already-compromised container with sufficient privileges. Workload hardening remains mandatory.

## 19. Deploying via GitOps/IaC without exposing secrets

A clean GitOps model stores **references**, never secret values:

```text
Git repository
├── Namespace/ServiceAccount
├── SecretProviderClass: vault name + object names + identity ref
├── Deployment: CSI volume + mountPath
├── RBAC/network policy
└── NO passwords / API tokens / private keys
             |
             v
  CI/CD or GitOps controller
             |
             v
  AKS applies manifests
             |
             v
  Pod uses identity → Key Vault → mounts secret file
```

### What must still stay protected

- Terraform state / IaC outputs can contain secrets if secret values were passed as variables/outputs.
- Helm values containing plaintext passwords can leak into release history or pipeline logs.
- Cluster admin kubeconfigs/credentials.
- Storage/registry/service principal secrets outside Workload Identity.
- Key Vault exports, backups, and logs containing tokens.

**`SecretProviderClass` contains vault and object names**: while not secret values themselves, they can still reveal sensitive architectural metadata; govern repository access accordingly.

## 20. Integrated observability: inspect multiple log sources

A "Pod won't start" incident can stem from three separate layers:

| Source | Can detect | Cannot conclude alone |
|---|---|---|
| **Kubernetes Pod events** | `FailedMount`, timeouts, missing `SecretProviderClass`, object fetch errors. | Does not fully explain Key Vault policies or networking. |
| **CSI Driver / Azure Provider logs** | Provider comms, identity, mount/rotation failures. | Does not show whether the app read and used the secret properly. |
| **Key Vault diagnostic logs** | `Get` calls, authorization errors, vault health. | Does not prove the container process reloaded the secret. |
| **Microsoft Entra sign-in / workload identity logs** | Token/credential exchange errors when logs exist. | Does not prove filesystem mounting succeeded. |
| **Application logs/metrics** | DB auth failures, TLS expiry, connection success/failure. | Does not fully explain why Key Vault `Get` was denied. |
| **Azure Activity Log** | Key Vault resource edits, role assignments, AKS add-on control-plane changes. | Does not record every Key Vault secret value read by default. |

### Inspecting Pod events

```bash
kubectl -n orders describe pod orders-secret-check

kubectl -n orders get events \
  --sort-by=.metadata.creationTimestamp
```

Read messages around `MountVolume.SetUp failed`, `FailedMount`, `SecretProviderClass not found`, `Forbidden`, `Unauthorized`, or timeouts. Exact wording varies by driver/provider version.

### Inspecting driver/provider Pods

```bash
kubectl -n kube-system get pods
kubectl get csidriver
kubectl -n orders get secretproviderclass
kubectl -n orders get secretproviderclasspodstatus
```

Locate Secrets Store CSI and Azure Provider Pods/DaemonSets in `kube-system` by their live names. Select the exact Pod and container before running `kubectl logs`; avoid copying commands with component names from a different release.

`SecretProviderClassPodStatus` surfaces mounted object versions per driver without **printing secret contents**. It helps verify which version a Pod received during rotation.

## 21. Common troubleshooting table

| Symptom | Possible cause | First checks |
|---|---|---|
| `SecretProviderClass not found` | Typo, resource missing, or wrong namespace. | Compare `volumeAttributes.secretProviderClass`, namespace, and `kubectl get spc`. |
| Pod stuck in `ContainerCreating` with `FailedMount` | Driver/provider, identity, vault, or networking. | Pod events, CSI/provider logs, Key Vault audit logs. |
| `Forbidden` reading vault | Identity lacks role or vault uses a different permission model. | Principal ID, Key Vault RBAC/access policy, scope. |
| `Identity not found` or cannot acquire token | Managed identity not on node; Workload Identity federation/SA mismatch. | Add-on identity, OIDC issuer, subject, audience, client ID. |
| `SecretNotFound` | Wrong `objectName`, vault, or version; secret disabled/deleted. | Object metadata, vault name, name/version. |
| Timeout reaching Key Vault | DNS, firewall, private endpoint, routing, or outbound egress. | Test network path from AKS node/pod, not only laptop. |
| File mounted yet app reports missing credential | App reads wrong path, alias filename, or permission denied. | `mountPath`, `objectAlias`, UID/GID, app config. |
| Rotation succeeded yet app still uses A | App caches in memory, env var didn't refresh, or `subPath` mount. | Refresh logic, mounted file, pod rollout. |
| Synced Kubernetes Secret never appears | No Pod mounts SPC, bad `secretObjects` config, or sync unsupported. | Pod lifecycle, object mapping, driver events. |
| New cert uploaded yet clients see old cert | Process/Ingress hasn't reloaded TLS. | TLS endpoint, controller config, rollout/reload. |
| Works in one namespace, fails in another | Different service account, federated credential, identity, or RBAC. | Compare subject, Pod label, SPC, vault policy. |
| Image runs yet only some replicas fail | Node/driver rollout uneven or credential/rotation out of sync. | Pod node placement, plugin logs, identity/rotation state. |

### Short remediation workflow

1. Capture **cluster, namespace, Pod, node, revision/image, and UTC timestamp**.
2. Check Pod events and confirm `SecretProviderClass` sits in the right namespace.
3. Check driver/provider health on the Pod's node.
4. Verify identity mode: managed identity vs. Workload Identity.
5. Check Key Vault object metadata, role/scope, and secret status.
6. Check DNS/routes/firewalls on timeouts.
7. Confirm the mounted file exists using a **command that never prints contents**.
8. Confirm the app reads the right path and reloads cleanly.
9. Fix the **narrowest root cause**, roll out safely, and verify metrics/logs.
10. Document timeline and revert any temporary emergency permissions.

Never resolve `Forbidden` by granting subscription Owner or opening Key Vault to the Internet. That creates a far bigger hole than the original incident.

## 22. Rotation incident: safe handling

**Scenario:** the DB password just rotated in Key Vault; Pods stay Running yet the app returns HTTP 500s due to database authentication failures.

### Investigation

1. Identify the new secret version in Key Vault and which credential the target DB accepts.
2. Check if `SecretProviderClass` pins `objectVersion`.
3. Confirm rotation is enabled and driver/provider logs show no errors.
4. Check mounted object version metadata without reading values.
5. Check if the app reads the file at startup only or supports live reload.
6. If the app reads a synced Kubernetes Secret via env vars, check whether Pods restarted/rolled out after the update.
7. Confirm every replica/worker switched to the new credential before revoking the old one.

### Remediation

- Prefer **overlapping credentials** if the DB or target service supports them.
- If the secret file updated yet the app did not reload, execute an approved rolling restart/rollout.
- If the Key Vault reference was wrong, fix `SecretProviderClass` and verify the mount.
- If an old version was pinned, update the version explicitly or switch to versionless tracking per change controls.
- Watch DB connections and HTTP 5xx rates before confirming recovery.

**Rollback:** revert to credential A only if it remains valid and Security/DB owners approve. Never restore a secret that was revoked due to suspected compromise.

## 23. Key Vault unavailability and CSI limits

When Key Vault becomes unreachable:

- **Already running Pods** can generally keep using previously mounted files/values depending on CSI and app state.
- **New or rescheduled Pods** may fail to mount if they cannot fetch objects or identity tokens.
- Rotation pauses; if an active credential expires meanwhile, apps can fail even while Pods stay Running.
- Synced Kubernetes Secrets may persist per driver/Kubernetes lifecycle, yet **never treat them as an independent backup or startup guarantee during a Vault outage**.

Resiliency planning should include:

1. Monitoring Key Vault availability and CSI mount failures.
2. Avoiding unnecessary Pod churn/restarts during an active Vault outage; follow operational runbooks.
3. Maintaining replica capacity/HA and conditional rolling updates.
4. Configuring Key Vault backup/recovery, soft delete, and purge protection per policy.
5. Planning secret expiration, token/DB credential lifetimes, and rotation schedules.
6. Testing vault network loss in a lab environment.
7. If strict SLAs apply, evaluate dependency caching/resiliency architecture rather than assuming CSI masks every outage.

**Never hardcode a fallback password inside an image** to survive outages: that leaves a long-lived credential hard to revoke and easy to abuse.

## 24. Key Vault soft delete, purge protection, and backup

Azure Key Vault provides lifecycle safeguards including **soft delete** and **purge protection** per service terms.

| Mechanism | Protects against | Does NOT solve |
|---|---|---|
| Soft delete | Accidental object or vault deletion within supported retention. | Apps automatically switching versions or network outages. |
| Purge protection | Premature permanent deletion before retention expires. | Authorized users reading secrets via CSI. |
| Secret versioning | Preserves historical value versions when adding new ones. | Automatic app reloads without rotation/rollout. |
| Audit/diagnostic logs | Investigating who/what accessed within log scope. | Preventing incidents without alerts/response. |
| Backup/recovery | Restoring per vault-supported backup methods. | Operational recovery drills and restore permissions. |

**Incident revocation for a leaked secret** differs from routine rotation: evaluate active tokens/sessions, downstream permissions, blast radius, and access logs. Simply adding a new Key Vault version does not automatically invalidate old credentials at target systems.

## 25. Combining Kubernetes policies and auditing

To turn this setup into a repeatable standard, establish:

- **Naming conventions:** `spc-<app>-<env>`, `sa-<app>`, and clearly owned object names.
- **Namespace boundaries:** separate Production from Development; minimize shared identities.
- **Identity ownership:** who assigns vault read roles, who owns ServiceAccounts and federations.
- **GitOps templates:** peer-reviewed `SecretProviderClass`, Pod volumes, and Kubernetes RBAC.
- **Rotation runbooks:** whether each app uses files or env vars and whether it supports live reload.
- **Secret inventory:** vault, object name, type, expiry/rotation, consuming apps—**never** secret values.
- **Audit reviews:** role changes, federated credentials, Pod `exec`, and provider logs.
- **CI policies:** scan repositories/manifests to block hardcoded secrets.
- **Break-glass:** approved temporary elevation, audited and revoked post-incident.
- **Cost controls:** Key Vault operations, Azure Monitor ingestion, and networking components.

### Pre-production review checklist

1. Clear rationale for using a secret rather than identity-based auth.
2. Managed identity or Workload Identity aligned with workload boundaries.
3. Vault and objects placed in the right tenant/subscription/region per policy.
4. Roles scoped strictly to read only required objects.
5. `SecretProviderClass` and Pod mounts contain zero plaintext credentials.
6. Unnecessary groups lack `kubectl exec` or synced Kubernetes Secret read access.
7. If using synced Secrets, reviewed etcd/RBAC security and refresh workflows.
8. Private networking and DNS tested from inside the cluster.
9. Rotation tested for both **running Pods** and **newly scheduled Pods**.
10. Alerts, logs, and restore runbooks assigned to clear owners.
11. No sidecar or auxiliary container receives secrets unnecessarily.
12. Vault, logging, and operational costs fit budget.

## 26. Hands-on exercise: protecting the Orders API password

**Scenario:** a team has a lab AKS cluster, namespace `orders`, and app `orders-api` needing a dummy DB password. The secret must live in Azure Key Vault, with Pods reading from a CSI file. The team must prove rotating the password never leaks values into Git or consoles.

### Requirements

| Component | Illustrative value |
|---|---|
| AKS cluster | `aks-lab` |
| Namespace | `orders` |
| Key Vault | `kv-orders-lab` |
| Key Vault object | `orders-db-password` (secret) |
| `SecretProviderClass` | `kv-orders` or `kv-orders-wi` |
| Pod | `orders-secret-check` |
| File mount | `/mnt/secrets-store/orders-db-password` |
| Identity | Add-on managed identity or workload-specific identity |
| Rotation | Documented refresh and app verification workflow |
| Testing | Zero secret values printed |

### Tasks

1. Diagram the path Key Vault → identity → CSI provider → Pod file.
2. Explain why a Kubernetes Secret is **optional** for direct file mounts.
3. Choose between add-on managed identity and Workload Identity for a multi-app cluster and justify.
4. Verify the AKS add-on and CSI components are running.
5. Assign secret read permissions matching the Key Vault permission model.
6. Create the `SecretProviderClass` in the right namespace with exact object names.
7. Create a Pod mounting the volume read-only and test file existence with `test -s`.
8. If using Workload Identity, verify ServiceAccount annotation, Pod label, and federated credential.
9. Write a rotation runbook for an app that reads secrets only at startup.
10. Explain why mounting via `subPath` breaks rotation updates.
11. Analyze risks of enabling sync to a Kubernetes Secret.
12. Propose log sources and alerts to troubleshoot `FailedMount` and `Forbidden`.
13. Propose an incident response plan when Key Vault is unreachable while existing Pods keep running.
14. Select one Key Vault backup/recovery control and one CI safeguard against secret leaks.

### Guided solution

**Architecture:**

```text
Key Vault: orders-db-password
     |
     +-- RBAC: workload identity granted secret read
     |
     v
AKS CSI Driver + Azure Provider
     |
     +-- SecretProviderClass: kv-orders-wi
     |
     v
Pod orders-secret-check
     |
     +-- file /mnt/secrets-store/orders-db-password
     |
     v
App reads file, NEVER logs value
```

**In multi-app environments:** a dedicated Workload Identity for service account `orders-sa` narrows access far better than a node-wide identity reading every vault. Even so, restrict Pod and `SecretProviderClass` creation permissions to prevent misuse.

**Verification outcome:** Pod `Running`, CSI volume mounted, `test -s` returns exit code 0, Key Vault logs show valid reads where collected, and application logs contain zero secrets.

**Rotation:** add a new secret version in Key Vault; if CSI rotation is enabled and version is unpinned, wait for file refresh; trigger app reload or rolling restart; revoke the old credential only after confirming all consumers switched.

**If errors occur:** inspect Pod events and driver logs first, then check identity/roles and networking. Never fix errors by pasting passwords into Deployment plaintext.

**Acceptance:** able to redeploy Pods in the lab namespace, verify mounts without printing secrets, prove zero secrets reside in repos/manifests, and document recovery steps if the vault or identity changes.

## 27. Knowledge self-check

**Question 1.** Why doesn't base64 encoding in a Kubernetes Secret mean the secret is safely encrypted?

**Answer:** Base64 is a trivial encoding, not encryption. You still need Kubernetes RBAC, control-plane protection, and proper encryption/data-access policies.

**Question 2.** What is the primary role of `SecretProviderClass`?

**Answer:** Declaring the Key Vault source, objects, and identity/parameters for the Secrets Store CSI Driver so Pods can mount the data.

**Question 3.** When a Pod reads files directly from CSI, is creating a Kubernetes Secret mandatory?

**Answer:** No. Syncing to a Kubernetes Secret is optional for apps or controllers requiring the Kubernetes Secret API.

**Question 4.** Is `Azure Key Vault Secrets User` always enough to fetch Key Vault keys and certificates?

**Answer:** No. Permissions differ by object type and action; verify the exact roles/permissions required for keys and certificates.

**Question 5.** Which Kubernetes attributes does Workload Identity bind an identity to?

**Answer:** OIDC issuer, federated credential subject `system:serviceaccount:<namespace>:<serviceaccount>`, audience, and workload identity client ID; Pods specify the matching service account and label.

**Question 6.** When the add-on uses a node managed identity, what is the main risk of granting read access to the entire vault?

**Answer:** It widens the secret blast radius accessible to workloads able to use that shared identity. Narrow scopes/permissions or isolate identities per workload.

**Question 7.** Why might a running app still use an old secret after a new version is added in Key Vault?

**Answer:** CSI refreshes on its own rotation cycle, and apps may cache files or env vars. Env vars populated from Kubernetes Secrets require a container restart to pick up new values.

**Question 8.** What problem can mounting via `subPath` cause during rotation?

**Answer:** CSI file updates may not reflect inside `subPath` mounts; mount the parent directory instead and design app reload logic properly.

**Question 9.** An identity has valid RBAC yet mounting returns `Forbidden` or times out. What else should you check?

**Answer:** Vault permission model, actual identity/client ID, federated credential, secret state, networking, DNS, firewalls, private endpoints, and logs.

**Question 10.** Can a Pod in namespace `orders` reference a `SecretProviderClass` that exists only in namespace `billing` by name?

**Answer:** Not normally; `SecretProviderClass` is namespaced and the Pod needs the resource in its own namespace.

**Question 11.** With sync enabled, does the Kubernetes Secret appear immediately after creating `SecretProviderClass` before any Pod mounts it?

**Answer:** Do not assume so. Syncing is tied to a Pod actively mounting the CSI volume; verify driver lifecycle behavior.

**Question 12.** Why doesn't a Pod `FailedMount` event automatically prove a Key Vault RBAC failure?

**Answer:** Mounts can also fail due to missing `SecretProviderClass`, CSI driver issues, identity mismatches, DNS, firewalls, wrong secret name/version, or network timeouts.

**Question 13.** When Key Vault loses connectivity, if existing Pods stay running, are new Pods guaranteed to start?

**Answer:** No. New Pods may require the CSI provider to fetch objects and fail; already mounted volumes on running Pods do not guarantee future startups.

**Question 14.** For an API that can sign in directly to a database using Microsoft Entra, is storing a database password in Key Vault strictly necessary?

**Answer:** No. When target services support identity-based authentication, password secrets can often be reduced or eliminated.

**Question 15.** When should you restart Pods after rotation?

**Answer:** When apps do not re-read files dynamically, consume env vars from synced Kubernetes Secrets, or require a rollout to pick up new credentials—after verifying vault version and connectivity.

**Question 16.** Which logs are most useful when a new Pod fails to mount a Key Vault secret?

**Answer:** Pod events/describe, CSI driver/provider logs, Key Vault diagnostics, role/identity details, and network/DNS info—never needing to print secret values.

**Question 17.** If an admin runs `kubectl exec` into a Pod, can they read mounted secret files?

**Answer:** Potentially yes, if processes and file permissions allow it. Therefore restrict `exec` permissions and runtime access, not just Key Vault RBAC.

**Question 18.** Why shouldn't you revoke credential A immediately after adding version B in Key Vault?

**Answer:** Pods, drivers, or apps may not have refreshed yet; verify all consumers switched to B cleanly before revoking A, except during emergency compromise revocations.

**Summary:** Secret management in AKS coordinates **secret store (Key Vault) – identity (managed identity / Workload Identity) – delivery mechanism (CSI volume) – Kubernetes permissions – rotation lifecycle – observability and recovery**. Start with a lab secret, grant least privilege, mount read-only files, never print values, and test both rotation and failure scenarios. A strong integration does more than let apps read secrets today: it **controls who can access secrets, tracks when they change, and recovers safely when errors happen**.
