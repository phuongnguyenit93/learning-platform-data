# Accessing Key Vault with the Azure SDK for Java

A Java application running on Azure App Service needs to call a payment API using a secret key. During development, developers often place keys in configuration files, environment variables, or source code. Once the app deploys across multiple environments, requires key rotation, access auditing, and protection against accidental leaks by staff or attackers, that approach quickly exposes major risks.

**Azure Key Vault** is a managed Azure service for safeguarding and controlling access to **secrets, cryptographic keys, and certificates**. The **Azure SDK for Java** lets applications access vault items through dedicated clients authenticated via **Microsoft Entra ID**. Instead of hard-coding secrets or distributing access keys, applications typically use **managed identity** to call Key Vault and retrieve values only when genuinely needed.

This lesson belongs to the **Azure SDK for Java** chapter of the **CLOUD_PROVIDERS_AZURE** module. It is part of the broader journey across Microsoft Azure from subscriptions, resource groups, and Entra ID to virtual networks, compute, storage, and data. Content focuses on **deploying, monitoring, securing, and controlling the costs** of Java architectures on Azure.

The main focus is **Azure Key Vault Secrets** and the **`azure-security-keyvault-secrets`** library paired with **`azure-identity`**. Key Vault Keys and Certificates are compared to clarify when another client is required; this lesson avoids confusing reading a secret with performing asymmetric signing operations.

> **Security Principle:** Key Vault reduces the need to distribute secrets and adds authentication, authorization, and auditing. It does **not** make a secret already returned to the JVM un-leakable. Once fetched, Java code must still limit its lifetime, prevent logging, restrict who can access it, and govern how it is used.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **vault, secret, secret name, secret version, secret identifier, and properties**.
2. Identify the differences among **Secrets, Keys, Certificates**, and Managed HSM.
3. Explain Azure Key Vault **control plane** vs. **data plane**, Azure RBAC, and access policies.
4. Choose **`DefaultAzureCredential`**, **`ManagedIdentityCredential`**, and workload identity in the right contexts.
5. Identify the **Key Vault Secrets User**, **Key Vault Secrets Officer**, and **Key Vault Reader** roles and their boundaries.
6. Provision a lab Key Vault via Azure CLI, grant read access to a specific identity, and inspect its URL.
7. Configure Maven for **`azure-security-keyvault-secrets`** alongside **`azure-identity`**.
8. Write a complete Java application to **read a secret**, handle errors, and strictly avoid logging values.
9. Practice creating a new version, reading a secret by version, and reading metadata with the Java SDK.
10. Design rotation, caching, refresh, startup failure handling, and resilience during transient vault outages.
11. Explain firewalls, Private Endpoints, private DNS, and **401, 403, 404, 429** errors.
12. Compare the Java SDK against **Key Vault references** in App Service/Functions and Spring integration patterns.
13. Set up monitoring, diagnostic logs, least privilege, CI/CD, testing, incident response, and FinOps.
14. Evaluate a production architecture before allowing a Java workload to access real secrets.

## 2. Running Scenario: Java Orders API Needs an API Key

Suppose the **Orders API** service runs on Azure App Service or AKS. When processing orders, it must call a partner service using an API key.

Requirements:

- **Never commit** the API key to Git, JARs, Dockerfiles, image layers, Helm values, or unprotected properties files.
- **Never** send the key to browsers.
- The Java workload has its own identity authenticated by Azure.
- Each environment uses an appropriately managed Key Vault or secret scope.
- Only Orders API can read the specific secret it needs.
- Support key rotation and rollback if a new secret version fails.
- Secrets can be changed without rebuilding binaries.
- Vault failures or key expirations are detected early with runbooks ready.

Sample architecture:

~~~mermaid
flowchart LR
    DEV["Developer local<br/>az login"] --> CREDS["Azure Identity SDK<br/>TokenCredential"]
    APP["Orders API<br/>App Service / AKS"] --> CREDS
    ID["Microsoft Entra ID"] --> CREDS
    CREDS --> SDK["SecretClient<br/>azure-security-keyvault-secrets"]
    SDK --> VAULT["Azure Key Vault<br/>orders-payment-api-key"]
    VAULT --> SDK
    SDK --> APP
    APP --> PARTNER["Partner payment API"]
    AUDIT["Azure Monitor<br/>Key Vault diagnostics"] -. "traces/metrics" .-> VAULT
~~~

**Typical lifecycle:**

1. The application has a managed identity or another valid Entra authentication method.
2. The Azure Identity SDK acquires an **access token** for Key Vault.
3. `SecretClient` calls the vault's **data-plane HTTPS endpoint**.
4. Key Vault validates the token, access permissions, and network rules.
5. The vault returns the secret value and metadata to the authorized caller.
6. The app uses the value to connect to the partner, **never logging it or returning it in responses**.
7. When the secret rotates, the app reloads it via a designed refresh mechanism.

An Entra token to call the vault is **not** the payment secret itself. Never confuse the vault access token, the secret value, the partner API key, and the Azure account administering the vault.

## 3. What Types of Objects Does Key Vault Manage?

| Type | Purpose | Typical Java Client | Examples |
|---|---|---|---|
| **Secret** | Stores secret values and version metadata | **SecretClient** | API keys, connection passwords, third-party tokens |
| **Key** | Cryptographic keys to sign/verify, encrypt/decrypt, or wrap/unwrap per permissions and key type | **KeyClient**, **CryptographyClient** | RSA/EC keys, key-encryption keys |
| **Certificate** | Manages certificate lifecycles, policies, and related parts per certificate type | **CertificateClient** | Service TLS certificates |
| **Managed HSM** | Dedicated HSM-backed key management with distinct permissions and features | Service-supported clients | Specialized cryptographic and compliance needs |

### 3.1. A Secret Is Not a Key

A **Secret** returns its value directly to authorized apps. A **Key** can perform cryptographic operations without ever exporting the private key out of the service, depending on key type and protection settings.

**Never store a non-exportable private key** as a Key Vault Secret assuming it receives the same HSM guarantees as Key Vault Keys. When business requirements call for HSM-backed signing, use `CryptographyClient` and appropriate key policies.

### 3.2. What Do Secrets Typically Hold?

- SaaS or partner API keys.
- Passwords for external systems that do not support managed identity.
- Shared secrets used to verify webhooks.
- Token signing secrets when an architecture requires a shared symmetric key.
- Password-bearing connection strings when identity-based authentication is unsupported.

However, **not every credential should become a secret**. When Azure SQL, Storage, Service Bus, or another service supports **Microsoft Entra/managed identity**, prefer identity-based auth rather than storing account keys in Key Vault.

### 3.3. Key Vault Is Not a General Configuration Database

Never place thousands of public feature flags, localized strings, or user session state into Key Vault just to "avoid running a database." For non-secret configuration, use **Azure App Configuration**, an app config service, or deployment config mechanisms.

Use Key Vault for **values that require protection**, access control, and secret lifecycles. Every vault call incurs latency, quota consumption, and potential charges.

## 4. Vault Structure, Names, Versions, and Identifiers

~~~text
Azure subscription
└── Resource group
    └── Key Vault: kv-orders-prod-example
        ├── Secrets
        │   ├── orders-payment-api-key
        │   │   ├── version aaaaa...
        │   │   └── version bbbbb...
        │   ├── legacy-database-password
        │   └── external-webhook-signing-key
        ├── Keys
        └── Certificates
~~~

### 4.1. Vault URI

A Key Vault exposes a data-plane URL like:

~~~text
https://<vault-name>.vault.azure.net/
~~~

This is the **vault URI**, not the URL of a specific secret.

### 4.2. Secret Name

A secret has a **name** such as:

~~~text
orders-payment-api-key
~~~

Names must follow Key Vault character and length rules and should stay stable. Names containing spaces or invalid path separators are rejected. Never embed usernames or PII in secret names just for debugging convenience.

### 4.3. Secret Version

Setting a new value under the **same secret name** creates **a new version** in Key Vault. Versions are essential for rotation, auditing, and rollback.

~~~text
Secret name: orders-payment-api-key

Version A: DEMO_KEY_V1
Version B: DEMO_KEY_V2  ← latest enabled version per service state
~~~

This is an abstract model; never display real secret values like this in production.

### 4.4. Secret Identifier

A secret ID is a URI:

~~~text
https://kv-orders-prod-example.vault.azure.net/secrets/orders-payment-api-key/<version>
~~~

A **versionless URI** looks like:

~~~text
https://kv-orders-prod-example.vault.azure.net/secrets/orders-payment-api-key
~~~

Using a **versionless lookup** lets apps pick up new versions on refresh. Use **version-pinned** lookups when strict reproducibility or controlled rollouts/rollbacks are needed. Even with versionless lookups, SDKs or apps may cache values—do not assume changes take effect instantaneously mid-request.

### 4.5. Secret Properties

Each version carries metadata depending on service support:

- Name, ID, and version.
- Enabled/disabled state.
- `CreatedOn`, `UpdatedOn`.
- `ExpiresOn`, `NotBefore`.
- `ContentType`.
- Tags.
- Recovery/deletion metadata in supporting operations.

**`SecretProperties` is not the Secret value.** Metadata is less sensitive than the value itself, yet it can still expose system names or versioning schemes. Log only necessary fields.

## 5. Security Architecture: Three Layers to Distinguish

A Java `getSecret` call can fail at three completely separate layers.

~~~mermaid
flowchart TD
    APP["Java workload"] --> AUTH["1. Microsoft Entra ID<br/>TokenCredential"]
    AUTH --> NET["2. Network access<br/>firewall / Private Endpoint / DNS"]
    NET --> RBAC["3. Key Vault data-plane authorization<br/>RBAC or access policies"]
    RBAC --> SECRET["Get secret value"]
~~~

**Layer 1 – Authentication:** Java proves its identity via Entra ID and receives a token with the right audience/scope.

**Layer 2 – Network:** the vault may block public networks, restrict IPs/VNets, or require Private Endpoints and private DNS.

**Layer 3 – Data-plane authorization:** the identity must hold permission to read secret values under the vault's configured permission model.

Valid token **without Secret Get permission** → authorization error. Right role yet DNS misses the private endpoint → timeout/network error. Some network denials also surface as HTTP 403 with specific error codes; inspect error codes and request IDs.

### 5.1. Control Plane vs. Data Plane

| Plane | Responsibility | Examples |
|---|---|---|
| **Control plane (Azure Resource Manager)** | Create vaults, alter networking, backup settings, role assignments per permissions | Azure Portal, ARM/Bicep, `az keyvault create` |
| **Data plane (Key Vault endpoint)** | Get/set/list/delete/rotate secrets per data permissions | Java `SecretClient`, `az keyvault secret show` |
| **Partner application** | Uses the secret to call business APIs | HTTP `Authorization` header to partner API |

Resource group **Azure `Contributor`** does not implicitly grant permission to read secret values. Likewise, **Key Vault Reader** does not allow reading secret values.

### 5.2. Azure RBAC vs. Vault Access Policies

Key Vault supports different authorization models depending on configuration:

- **Azure RBAC permission model:** uses Azure role assignments at the vault or resource scope. Generally preferred for modern governance.
- **Vault access policy model:** grants data-plane permissions via vault access policies. Used when legacy apps or organizational policies require it with understood migration plans.

**Never mix both models assuming they grant permissions simultaneously.** Always check which permission model the vault enforces.

### 5.3. Common Roles

| Role | General Capability | When to Use |
|---|---|---|
| **Key Vault Secrets User** | Read secret values | Java workloads that only need `getSecret` |
| **Key Vault Secrets Officer** | Manage secrets (without managing permissions) | Rotation services or approved operators |
| **Key Vault Reader** | Read metadata without reading secret values | Auditing or inventorying as needed |
| **Key Vault Administrator** | Broad data-plane permissions across the vault | Exceptional admin tasks only; tightly restricted |
| **Key Vault Crypto User** | Cryptographic operations on keys per permissions | Apps using `KeyClient`/`CryptographyClient` |
| **Key Vault Certificates Officer** | Manage certificate lifecycles per role | Certificate management teams |

Role names and data actions can evolve; inspect actual role definitions and assign at the **narrowest feasible scope**.

### 5.4. Principle of Least Privilege

An Orders API that only reads **`orders-payment-api-key`** should not have permission to create or delete every secret. If an organization needs per-secret isolation via RBAC scopes or access policies, check supported scope granularity and management overhead—do not assume a vault-scoped data-plane role isolates individual secrets automatically.

A rotation worker typically needs **set** and **get** permissions, separated from read-only apps. Separating identities shrinks the blast radius.

## 6. Microsoft Entra ID and TokenCredential

### 6.1. DefaultAzureCredential

In Java, **`azure-identity`** provides **`TokenCredential`** implementations. **`DefaultAzureCredential`** tries supported credential sources based on configuration and environment, letting one code path run both locally and on Azure.

Example:

~~~java
TokenCredential credential =
    new DefaultAzureCredentialBuilder().build();
~~~

Identity sources can include environment credentials, managed/workload identities, and developer tooling like Azure CLI depending on version and environment. **Never assume the credential chain and ordering are immutable**, especially when multiple accounts or environment variables are present.

### 6.2. Local Development

On a developer workstation:

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table
~~~

A local identity from Azure CLI can read a secret only if **that user identity holds data-plane permissions** on the vault. Succeeding at `az login` **does not automatically grant Key Vault read access**.

If other credential environment variables exist, `DefaultAzureCredential` may select an identity different from the active CLI user. On 403, inspect the actual principal behind the access token and selected credential source before blindly modifying RBAC.

### 6.3. Managed Identity in Azure

With a **system-assigned managed identity** on App Service, Functions, or VMs:

1. Enable the identity on the workload.
2. Assign the **Key Vault Secrets User** role at the proper scope.
3. Have the app use `DefaultAzureCredential` or `ManagedIdentityCredential`.
4. Never use a client secret to prove identity.
5. Verify networking, TLS, and RBAC propagation.

With a **user-assigned managed identity**, specify the client ID explicitly when multiple identities exist:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String clientId = System.getenv("AZURE_CLIENT_ID");
if (clientId == null || clientId.isBlank()) {
    throw new IllegalArgumentException("Missing AZURE_CLIENT_ID");
}

TokenCredential credential =
    new ManagedIdentityCredentialBuilder()
        .clientId(clientId)
        .build();
~~~

**Client ID is not a secret**, yet it must still be tracked accurately per environment. Never confuse the **client ID** with the principal object ID used in role assignments.

### 6.4. AKS Workload Identity

In AKS, use **Microsoft Entra Workload ID** with a Kubernetes `ServiceAccount` and federated identity credential per cluster/add-on setup rather than mounting shared vault credentials in Pods.

- `TokenCredential` uses the environment variables and projected tokens injected by workload identity.
- Key Vault roles are granted to the corresponding Entra principal.
- Pod `ServiceAccount`, namespace, and federated subject must match.
- Never assume every pod in the cluster can read every secret.
- Networking and outbound DNS to Key Vault must still pass.

Never copy a Kubernetes Secret holding account keys claiming it is "workload identity" when the goal is eliminating static credentials.

### 6.5. Service Principals in CI/CD

CI/CD can use **federated identity / OIDC** where supported; this is generally superior to long-lived client secrets. If a service principal secret is unavoidable, grant least privilege, store it in the CI secret store, rotate it, and keep it out of logs and build artifacts.

Never use a personal developer identity to run production deployment pipelines.

## 7. Java SDK Call Flow to Key Vault

~~~mermaid
sequenceDiagram
    participant APP as Java Orders API
    participant ID as Azure Identity SDK
    participant EN as Microsoft Entra ID
    participant KV as Azure Key Vault
    participant EXT as Partner API
    APP->>ID: Build TokenCredential
    ID->>EN: Acquire access token
    EN-->>ID: Token for Key Vault
    APP->>KV: GET secret via SecretClient + token
    KV->>KV: Check network & data-plane permissions
    KV-->>APP: Secret value + properties
    APP->>EXT: Call API using secret in secure header
    EXT-->>APP: Result
~~~

The **Azure SDK** handles HTTP, auth, and retries per client policy, yet application developers must still:

- Protect secret values in memory.
- Never log or serialize secrets.
- Never rebuild clients on every HTTP request.
- Never retry 403 or 404 infinitely.
- Configure timeouts and clean degrade/fail-closed behavior.
- Decide when to refresh caches and handle rotation.
- Trace errors via status codes, request IDs, and correlation without exposing secrets.

## 8. Maven Structure and Azure SDK Modules

For **Java 17** and Maven, two core dependencies:

| Maven Artifact | Role |
|---|---|
| **com.azure:azure-security-keyvault-secrets** | `SecretClient`, `KeyVaultSecret`, `SecretProperties` |
| **com.azure:azure-identity** | `DefaultAzureCredential`, `ManagedIdentityCredential` |
| **com.azure:azure-core** | `TokenCredential` and HTTP/core types (typically transitive) |

**Do not confuse** with:

- **`azure-security-keyvault-keys`**: key operations.
- **`azure-security-keyvault-certificates`**: certificates.
- Azure Storage or Azure App Configuration SDKs.

### 8.1. Sample pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>keyvault-java-demo</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-security-keyvault-secrets</artifactId>
      <version>4.10.0</version>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-identity</artifactId>
      <version>1.16.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The two versions above are **major-version examples** for SDK v4/v1 and must be verified and updated per your project's dependency policy and CVE scans before building. If your organization uses the **Azure SDK BOM**, manage versions centrally rather than pinning individually. Never equate "an SDK version shown in an example" with "the latest release."

### 8.2. Build and Run

~~~bash
# Project structure:
# src/main/java/com/example/keyvault/ReadSecretDemo.java

mvn -q -DskipTests compile
mvn -q exec:java -Dexec.mainClass=com.example.keyvault.ReadSecretDemo
~~~

Locally, you must sign in to Entra, hold a data-plane role, and set **`KEY_VAULT_URL`** and the secret name. These commands will not work until the vault/secret are provisioned and dependencies resolve.

## 9. Secret Naming and Lifecycle Design

An illustrative naming convention:

~~~text
Vault per environment:
    kv-orders-dev-example
    kv-orders-test-example
    kv-orders-prod-example

Secret names:
    orders-payment-api-key
    orders-webhook-signing-secret
    legacy-db-password
~~~

There is no rule requiring one vault per microservice; weigh ownership, data classification, networking, RBAC boundaries, quotas, rotation, and cost. Never dump secrets from hundreds of sensitive apps into one vault shared by a single reader identity.

### 9.1. Versioned Secrets

A standard rotation workflow:

1. Generate a new credential on the partner system.
2. Write a **new secret version** in Key Vault.
3. Verify read access and roll out updates to apps.
4. Shift traffic or wait for controlled cache refresh.
5. Monitor for authentication / HTTP 401 errors from the partner.
6. Revoke the old credential after the overlap window.
7. Maintain a rollback option if permitted by the partner and policy.
8. Log audit trail, owner, date, and next rotation date.

**Updating a secret in Key Vault does not automatically update the credential in the partner system.** Both sides must be coordinated in the same workflow.

### 9.2. Disabled, Not-Before, and Expiration

- A **disabled** secret cannot be read per service rules.
- **`NotBefore`** governs when a version becomes active.
- **`ExpiresOn`** marks when a version expires.
- The SDK may receive errors if an app attempts to read a value no longer permitted.

Do not assume `ExpiresOn` automatically rotates keys or scrubs cached copies from memory or devices. Applications still need explicit refresh and revocation strategies.

### 9.3. Secret Version Pinning

Version pinning locks rollouts deterministically, yet carries a risk: after rotation, the app keeps reading the old version. Versionless lookups pick up new versions on refresh, yet require compatibility monitoring and avoiding mid-transaction surprises.

Choose policies per secret type: API keys, signing secrets, database passwords, and certificate chains each have different requirements.

## 10. Azure CLI Lab: Creating a Vault and Assigning Permissions Properly

The commands below are **guides only**; no Azure resources were created while authoring this lesson. Key Vault may bill per operation and feature/tier. Run only inside an authorized lab subscription with an approved budget, permissions, and resource names.

### 10.1. Prerequisites

- Up-to-date Azure CLI aligned with organizational standards.
- Lab subscription with permission to create resource groups and vaults.
- Role assignment permission granted via **`Owner`**, **`User Access Administrator`**, **`Role Based Access Control Administrator`**, or equivalent role.
- Never collide with production vault names; vault names are globally unique per Key Vault rules.
- Never put real secrets in documentation or terminal transcripts.
- Know whether the vault uses RBAC or access policies; this example **chooses RBAC**.

### 10.2. Create Resource Group and RBAC Vault

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table

RG="rg-keyvault-java-lab"
LOCATION="southeastasia"
VAULT="<globally-unique-vault-name>"

az group create \
  --name "$RG" \
  --location "$LOCATION"

az keyvault create \
  --name "$VAULT" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --enable-rbac-authorization true
~~~

**Note:** never run `create` against a vault name already owned by another organization; if a vault already exists, verify ownership. Confirm default soft-delete and purge-protection/retention settings against organizational policy, especially before production.

### 10.3. Inspect the Vault Without Exposing Secrets

~~~bash
az keyvault show \
  --name "$VAULT" \
  --query "{id:id,name:name,vaultUri:properties.vaultUri,rbac:properties.enableRbacAuthorization}" \
  --output json

VAULT_ID=$(az keyvault show \
  --name "$VAULT" \
  --query id \
  --output tsv)
~~~

An example **vault URI**:

~~~text
https://<vault-name>.vault.azure.net/
~~~

If the vault uses a Private Endpoint and you are outside an authorized network, data-plane commands can fail even while ARM management commands succeed.

### 10.4. Grant a Role to the Lab Developer

**Only an authorized administrator** should run role assignment commands. Creating a vault does not automatically give the creator data-plane secret-read permissions.

~~~bash
MY_OBJECT_ID=$(az ad signed-in-user show \
  --query id \
  --output tsv)

az role assignment create \
  --assignee-object-id "$MY_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Key Vault Secrets Officer" \
  --scope "$VAULT_ID"
~~~

**Key Vault Secrets Officer** is used here only so the lab developer can **create a dummy secret** and test versioning. In production, developers should not receive broad write roles on vaults containing real secrets just to run a sample GET; instead, have an operator pre-create the secret and grant developers **Key Vault Secrets User** at the right scope.

### 10.5. Create a Dummy Sample Secret with Non-Sensitive Data

~~~bash
az keyvault secret set \
  --vault-name "$VAULT" \
  --name "orders-payment-api-key" \
  --value "DEMO_ONLY_NOT_A_REAL_SECRET" \
  --query id \
  --output tsv
~~~

**Warning:** `--value` passed on the command line can be captured in shell history and process lists; use **strictly public non-secret demo strings**. In production, use approved secret provisioning flows that prevent exposure in logs, shell history, pipelines, or temp files. Never paste real credentials into illustrative commands.

### 10.6. View Metadata Without Printing Values

~~~bash
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "orders-payment-api-key" \
  --query "{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  --output json

az keyvault secret list \
  --vault-name "$VAULT" \
  --query "[].{name:name,id:id}" \
  --output table
~~~

Keep in mind CLI data-plane commands may **retrieve payload internally before client-side `--query` filtering**. Restrict logging and command history, and never let unauthorized users run commands against production vaults.

### 10.7. Grant Access to the App's Managed Identity

Once App Service or a VM has a managed identity, an administrator retrieves its real **principal object ID** and assigns the read role:

~~~bash
APP_PRINCIPAL_ID="<managed-identity-principal-object-id>"

az role assignment create \
  --assignee-object-id "$APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
~~~

This assigns the role at **vault scope** for simplicity. If security policy demands tighter boundaries, apply RBAC at the narrowest supported resource scope. Never execute with placeholders. Role assignment permission is required; plain **`Contributor`** may not be permitted to assign roles.

**Do not confuse:**

- **Application (client) ID**: selects a user-assigned identity.
- **Principal object ID**: identifies a service principal/managed identity for RBAC assignments.
- **Subscription ID**: Azure resource billing/scope boundary.
- **Tenant ID**: Entra directory context.
- **Secret ID**: URL of a specific secret version.

### 10.8. Role Propagation

After creating a role assignment, data-plane permissions can take time to propagate. If `getSecret` returns 403 right after granting access, check identity, scope, and permission model, wait within runbook bounds for propagation, and retry. Never "fix" this by granting Azure `Owner` or disabling network policies.

## 11. Java: Complete Secret-Reading Example

Create **`src/main/java/com/example/keyvault/ReadSecretDemo.java`**.

~~~java
package com.example.keyvault;

import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class ReadSecretDemo {

    private ReadSecretDemo() {}

    public static void main(String[] args) {
        String vaultUrl = requiredEnv("KEY_VAULT_URL");
        String secretName = requiredEnv("KEY_VAULT_SECRET_NAME");

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        SecretClient secretClient =
            new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();

        KeyVaultSecret secret = secretClient.getSecret(secretName);
        String secretValue = secret.getValue();

        if (secretValue == null || secretValue.isBlank()) {
            throw new IllegalStateException(
                "Secret was empty or unavailable");
        }

        // In a real application, pass secretValue to the component
        // using the credential server-side; never log or print it to the console.
        // This example only verifies successful retrieval.
        System.out.println(
            "Key Vault secret retrieved successfully; value omitted.");
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Required environment variable missing: " + name);
        }
        return value;
    }
}
~~~

### 11.1. Environment Configuration

Example for a dev terminal using demo data:

~~~bash
export KEY_VAULT_URL="https://<vault-name>.vault.azure.net/"
export KEY_VAULT_SECRET_NAME="orders-payment-api-key"

az login
mvn -q compile
mvn -q exec:java -Dexec.mainClass=com.example.keyvault.ReadSecretDemo
~~~

On Windows PowerShell, set environment variables like this:

~~~powershell
$env:KEY_VAULT_URL = "https://<vault-name>.vault.azure.net/"
$env:KEY_VAULT_SECRET_NAME = "orders-payment-api-key"
~~~

These are **two non-sensitive variables** holding the endpoint and secret name. **Never** put the secret value itself into these variables; the program fetches the value via the Azure SDK.

### 11.2. Why Never Print Secrets?

Statements like these are dangerous:

~~~java
// NEVER do this in production:
System.out.println(secret.getValue());
logger.info("Payment key = {}", secret.getValue());
throw new RuntimeException("Invalid key: " + secret.getValue());
~~~

Console logs, APM traces, exception messages, crash dumps, shell logs, and build outputs persist long-term and are readable by many people. Never log secrets to telemetry "for easier debugging."

### 11.3. Can You Scrub a Secret String from RAM?

The Azure SDK returns secret values as a **Java `String`**, which is immutable. The Java garbage collector decides when objects are reclaimed; you **cannot guarantee memory zeroization** simply by setting a reference to `null`. Converting a `String` to `char[]` still leaves the original `String` in heap until GC. Practical mitigations:

- Minimize copies and limit how long secrets stay in scope.
- Never hold secrets in static global/debug state unnecessarily.
- Never serialize secrets to JSON or HTTP responses.
- Restrict diagnostics, core dumps, and memory access.
- Use managed identity so **secrets are unnecessary** wherever possible.

## 12. Java SecretClient for Versions, Metadata, and Listing

### 12.1. Reading Latest vs. a Specific Version

~~~java
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

String secretName = "orders-payment-api-key";

KeyVaultSecret latest = secretClient.getSecret(secretName);

// Retrieve version when you want to pin a specific release.
String version = latest.getProperties().getVersion();
KeyVaultSecret pinned = secretClient.getSecret(secretName, version);

// NEVER print latest.getValue() or pinned.getValue().
// Metadata is used for auditing per policy.
System.out.println("Resolved version metadata available: " +
    (version != null));
~~~

In this snippet, **`secretClient` was built in section 11**. Versionless `getSecret(name)` resolves the active secret version on the service; it does not mean "blindly return the newest version even if disabled, not-before, or expired without checks."

### 12.2. Listing Secret Metadata

~~~java
import com.azure.security.keyvault.secrets.models.SecretProperties;

for (SecretProperties properties :
        secretClient.listPropertiesOfSecrets()) {

    // Even secret names can reveal system topology.
    // Log only if permitted by policy.
    System.out.println("Secret metadata inspected");
}
~~~

**`listPropertiesOfSecrets`** returns metadata, not secret values. Still, a role scoped strictly to **get one secret** may not allow **listing the vault**; never rely on listing when the app already knows the secret name.

### 12.3. Listing Versions

~~~java
import com.azure.security.keyvault.secrets.models.SecretProperties;

for (SecretProperties props :
        secretClient.listPropertiesOfSecretVersions(
            "orders-payment-api-key")) {

    String version = props.getVersion();
    Boolean enabled = props.isEnabled();

    // Do not fetch values of versions just for inventory.
    recordVersionMetadata(version, enabled);
}
~~~

**`recordVersionMetadata`** is an illustrative application helper you must define; this snippet focuses on the SDK API. If unsure about field/accessor names in your pinned SDK version, check `SecretProperties` Javadoc and use available getters.

### 12.4. Paged Results

SDK listing operations return **`PagedIterable`/`AsyncPagedIterable`**, which may issue multiple HTTP requests while iterating. Never inventory a vault with thousands of secrets inside an HTTP request handler; use pagination, rate limits, and background jobs.

## 13. Creating a New Secret Version in Java: Operators Only

**Secret-reading code** should not write or rotate secrets on startup. Only a dedicated rotation service or approved operator holding **Key Vault Secrets Officer** should write new versions per policy.

Illustrative lab example:

~~~java
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

String name = "orders-payment-api-key";
String value = "DEMO_NEW_VERSION_NOT_A_REAL_SECRET";

KeyVaultSecret created = secretClient.setSecret(name, value);

// Print only necessary metadata; NEVER print created.getValue().
String version = created.getProperties().getVersion();
System.out.println("Created demo secret version: " + version);
~~~

**Never** embed real secret values in source code like this example. In production, new credentials must come from a secure provisioning pipeline—never from string literals or unprotected config files.

### 13.1. SetSecret Creates a Version, Not a Partner Key Change

After `setSecret`:

- The vault holds a new version.
- Other app instances may still hold cached/older versions.
- The partner system may not yet accept the new credential.
- A dual-key overlap window may be needed if supported by the partner.
- Rollouts require health checks, alerts, and rollback plans.

Never set an automatic expiration assuming that alone completes rotation.

### 13.2. Updating Metadata Without Changing the Value

`SecretProperties` exposes updatable attributes per SDK and service support. Typical flow:

~~~java
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import com.azure.security.keyvault.secrets.models.SecretProperties;
import java.time.OffsetDateTime;

KeyVaultSecret current =
    secretClient.getSecret("orders-payment-api-key");

SecretProperties properties = current.getProperties();
properties.setExpiresOn(
    OffsetDateTime.now().plusMonths(3));

secretClient.updateSecretProperties(properties);
~~~

**This is an administrative operation**—never run it in a request handler. It requires property-management permissions, modifies version metadata, and **neither changes the secret value nor revokes keys outside Key Vault**. For critical secrets, derive expiration dates from security policy and rotation calendars rather than arbitrarily adding three months.

### 13.3. Never Use the Secret Value as a Version ID or Tag

Version IDs are assigned by the service. Never encode actual API keys inside names, tags, or URLs for tracking, as those fields appear in logs and audits.

## 14. Sync and Async Clients in the Azure SDK

The Azure SDK for Java offers:

- **`SecretClient`** (synchronous): suits blocking code, background jobs, or startup initialization.
- **`SecretAsyncClient`** (asynchronous/reactive): suits apps already built on Reactor/WebFlux requiring non-blocking composition.

Async client example:

~~~java
import com.azure.security.keyvault.secrets.SecretAsyncClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

SecretAsyncClient asyncClient =
    new SecretClientBuilder()
        .vaultUrl(vaultUrl)
        .credential(credential)
        .buildAsyncClient();

// Do not block inside the Spring WebFlux event loop.
// Chain the Mono so the framework manages the request lifecycle.
var secretValueMono =
    asyncClient.getSecret("orders-payment-api-key")
        .map(secret -> secret.getValue());
~~~

**Never call `.block()` carelessly on a reactive event loop.** In blocking Spring MVC apps, the sync client is simpler; in high-concurrency reactive apps, compose async flows with proper caching and timeouts.

### 14.1. Reuse the Client

Reuse `SecretClient` across the service's lifetime via dependency injection rather than instantiating it per request, because the SDK manages HTTP connections, token acquisition, and retry policies. Never build a new credential and client inside a loop serving thousands of HTTP requests.

### 14.2. Token Cache vs. Secret Cache

The Azure Identity SDK caches and refreshes Entra tokens, yet **it does not automatically cache Key Vault secret values** for your app. Caching secret values requires separate decisions on TTL, invalidation, rotation, and memory exposure.

## 15. Handling Java Errors at the Right Layer

A `getSecret` call can fail due to credentials, networking, RBAC, or secret state.

### 15.1. Common HTTP Statuses

| Symptom | Likely Cause | How to Verify |
|---|---|---|
| **401 Unauthorized** | Invalid, expired, or wrong-audience access token | Credential source, tenant, token scope |
| **403 Forbidden** | Missing data-plane role, access policy, or network firewall | Vault permission model, principal, firewall/private endpoint |
| **404 Not Found** | Wrong secret name/version, disabled/deleted, or missing path per error code | Vault URL, name, version, Key Vault error details |
| **429 Too Many Requests** | Throttling / quota exceeded | Rate metrics, `Retry-After`, per-vault traffic |
| **5xx / transient** | Service or network outage | Azure Service Health, request IDs, retry budget |
| **Timeout / DNS / TLS** | Routing, Private DNS, proxy, certificate, firewall | Network tracing, Private Endpoint DNS |
| **`PermissionDenied` on `set`** | Read-only Reader role | Assign Officer/operator properly; never grant `Owner` carelessly |
| **Secret expired / disabled** | Lifecycle condition invalid | `SecretProperties`, rotation runbook |

Do not assume every 403 means "missing role"; network policies can also deny requests before data-plane authorization runs.

### 15.2. Catching Errors Without Printing Secret Values

~~~java
import com.azure.core.exception.HttpResponseException;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

try {
    KeyVaultSecret secret =
        secretClient.getSecret("orders-payment-api-key");

    consumeSecretWithoutLogging(secret.getValue());

} catch (HttpResponseException error) {
    int status = error.getResponse() == null
        ? -1
        : error.getResponse().getStatusCode();

    // Log status and correlation ID via sanitized telemetry.
    System.err.println("Key Vault access failed, HTTP " + status);
    throw error;
}
~~~

**`consumeSecretWithoutLogging`** is an illustrative business adapter you must define. Never print **`error.getMessage()`** directly to public logs without checking whether it exposes sensitive URIs or metadata. Production error handlers should use exact SDK exception types, OpenTelemetry, and strict redaction rules.

### 15.3. Proper Retry Strategy

- 429/503/transient transport errors: retry via built-in SDK policies honoring `Retry-After` when present.
- 401: inspect credential, token, and audience rather than looping.
- 403: inspect identity, role, and networking; never retry continuously for minutes.
- 404: verify secret name, version, and deletion state; never silently create empty secrets from the app.
- Expiration/revocation: fail closed or transition per business security policy.
- Unrecoverable configuration errors should fail fast at startup if the app cannot operate safely.

**Never stack unbounded retry layers**: SDK retries + Spring retries + API gateway retries amplify load and worsen Key Vault throttling.

## 16. Authentication Across Azure Runtimes

| Runtime | Recommended Identity | Key Configuration Points |
|---|---|---|
| **App Service** | System-assigned or user-assigned managed identity | Enable identity, RBAC, VNet integration if needed |
| **Azure Functions** | Managed identity | Host/app settings and data-plane permissions |
| **Azure VM** | Managed identity | Identity endpoint and role assignments |
| **AKS** | Microsoft Entra Workload ID | `ServiceAccount`, federated credential, role |
| **Container Apps** | Managed identity | Identity config, egress/networking |
| **Local dev** | Azure CLI / dev tooling | `az login`, matching tenant, lab data role |
| **CI/CD** | Federated identity / OIDC where supported | Scope/issuer/subject, least privilege |

The exact same container image running on AKS and locally can use **`DefaultAzureCredential`** yet authenticate as completely different identities. Always verify the actual runtime principal via tests rather than assuming identical behavior.

### 16.1. Specifying a User-Assigned Identity

When a workload has multiple user-assigned identities, pass the exact client ID in runtime configuration (e.g., **`AZURE_CLIENT_ID`** for supporting credential chains). Never pass object ID as client ID. With `ManagedIdentityCredentialBuilder`, set **`clientId`** as shown in section 6.

### 16.2. When Not to Use DefaultAzureCredential in Production

`DefaultAzureCredential` is convenient across environments, yet the chain can pick an unintended source if stray credentials exist in the runtime environment. For security-sensitive systems, **bind explicit credentials** per environment:

- Production: `ManagedIdentityCredential` or `WorkloadIdentityCredential` for the exact identity.
- Local: `AzureCliCredential` or appropriate developer credential.
- Test: fake `TokenCredential` / injected `SecretClient` abstraction.

Choose based on SDK version and runtime identity platform; never hard-code production principal secrets to "avoid the chain."

## 17. Reading Secrets at Startup vs. on Every Request

### 17.1. Avoid Calling getSecret on Every HTTP Request

If an API serves 1,000 req/s and every request calls Key Vault:

~~~text
1,000 app requests/s
× 1 Key Vault GET/request
= 1,000 Key Vault data-plane calls/s
~~~

This is an illustrative load calculation; Key Vault enforces throttling, adds latency, and bills per operation/tier. Calling on every request increases 429 risks, couples request latency to the vault, and reduces outage resilience.

### 17.2. Startup Fetch

Reading secrets once at startup:

- Simple with clear readiness.
- Fails fast if credentials are missing.
- Adds zero network calls to request paths.
- However, **does not auto-refresh** when secret versions change.
- Secret values stay in memory long-term; check security policy.
- If Key Vault has an outage during scale-out, new instances fail to start.

Fits scenarios where rotation is coordinated via deployments or restarts.

### 17.3. TTL Cache with Controlled Refresh

One pattern:

~~~mermaid
flowchart TD
    CALL["Partner API call"] --> C{"Cached secret usable?"}
    C -->|Yes| USE["Use current in-memory value"]
    C -->|No| KV["Fetch latest version from Key Vault"]
    KV --> VALID["Validate state/version"]
    VALID --> UPDATE["Atomically update cache"]
    UPDATE --> USE
~~~

Set TTL according to rotation SLA, latency needs, and threat model. Use background refresh ahead of TTL expiry, add jitter so thousands of instances do not hit the vault simultaneously, and cap retries.

### 17.4. Handling Stale Secrets During Vault Outages

There is no single universal rule:

- For a partner API key, serving a stale cached key for a few minutes may be acceptable if still valid and permitted by security policy.
- For a suspected compromised/revoked secret or sensitive cryptographic material, **failing closed** may be mandatory.
- For an expired secret, never treat a stale cache entry as valid merely because the JVM still holds the `String`.
- A brief last-known-good grace window may be allowed per risk acceptance, accompanied by alerts.

**Never fall back to a hard-coded backup key in code.**

## 18. Rotation and Version Pinning in Java

### 18.1. Canary Rotation Workflow

~~~mermaid
flowchart TD
    O["Operator creates new key at partner"] --> SET["Set new Key Vault version"]
    SET --> CANARY["Canary app reads new secret version"]
    CANARY --> TEST{"Partner authentication works?"}
    TEST -->|No| ROLLBACK["Rollback app reference<br/>keep old key per policy"]
    TEST -->|Yes| ROLL["Roll out versionless refresh<br/>or explicit version"]
    ROLL --> OBS["Monitor partner 401/403, latency"]
    OBS --> REVOKE["Revoke old partner key after overlap"]
~~~

### 18.2. Secret Version vs. Partner Key Version

Two systems hold independent state:

- Key Vault secret version.
- Active credential on the partner system.
- Application cache version.
- Deployment configuration/release version.

If you update Key Vault before the partner provisions the new key, apps picking up the new version fail. If the partner revokes the old key before apps finish refreshing, running instances lose connectivity.

### 18.3. How to Test Rotation

1. Create two demo secret versions.
2. Have the app read by name (latest) and by explicit version.
3. Observe version IDs without logging values.
4. Simulate TTL refresh or restart.
5. Simulate partner authentication failure.
6. Execute a controlled rollback of the app reference.
7. Monitor retrieval and partner auth metrics.
8. Delete demo credentials on the partner when finished.

**Never use a rotation lab to modify production secrets or real account credentials.**

## 19. Key Vault and Networking: Public Firewalls, Private Endpoints, DNS

### 19.1. Vault URL Does Not Change with Private Endpoints

Applications still connect via:

~~~text
https://<vault-name>.vault.azure.net/
~~~

When **Azure Private Endpoint** is configured properly, private network DNS resolves the hostname to a private IP managed by the service. For Key Vault, the private DNS zone is typically:

~~~text
privatelink.vaultcore.azure.net
~~~

Never replace the vault URL in `SecretClient` with a raw private IP, as that breaks TLS hostname validation, certificate verification, and routing.

### 19.2. Illustrative Network Architecture

~~~mermaid
flowchart TB
    APP["App Service / AKS / VM<br/>private networking"] --> DNS["DNS resolver<br/>private zone integration"]
    DNS --> PE["Private Endpoint IP"]
    PE --> KV["Azure Key Vault data plane"]
    AUTH["Microsoft Entra token endpoint"] --> APP
    ADMIN["Azure ARM control plane"] -. "management" .-> KV
~~~

Account for network paths to Entra ID and other dependencies too. A Private Endpoint to Key Vault does not automatically route all authentication traffic privately or grant extra RBAC.

### 19.3. App Service VNet Integration vs. Private Endpoint

- App Service **VNet Integration** enables outbound access from the app into a VNet per configuration.
- Key Vault **Private Endpoint** exposes the vault via a private IP inside a VNet.
- App Service **Private Endpoint** governs inbound private access to the App Service itself—not outbound calls to Key Vault.
- DNS, NSGs, firewalls, and routes must align on every hop.

Enabling a private endpoint does not magically allow external apps outside the VNet to read secrets. Local developers may need VPN, ExpressRoute, or an authorized jump host.

### 19.4. Diagnosing DNS and Firewalls

1. Verify the exact configured Key Vault endpoint.
2. Confirm where the app runs (local, App Service, pod, VM).
3. Test DNS resolution for **`vault-name.vault.azure.net`** from inside that exact network.
4. Inspect private endpoint/DNS zone links and routing.
5. Check TLS handshakes without disabling certificate validation.
6. Check Azure Firewall, NSGs, proxies, and app egress rules.
7. Once networking passes, verify data-plane RBAC.
8. Inspect HTTP status codes, error codes, and correlation IDs.

**Never enable public network access "just to make it work"** when policy mandates private access. Fix DNS and routing properly.

### 19.5. Multi-Region and Recovery

Key Vault provides service-managed availability and replication features per tier and region. Never assume any vault provides **RTO=0, RPO=0** across every regional outage. For strict production failover requirements, design vault/secret distribution, identities/permissions, and app fallbacks explicitly and run DR drills before trusting them.

Never copy secrets across regions with ad-hoc unapproved scripts; doing so creates extra copies needing governance, auditing, and rotation.

## 20. App Service and Azure Functions: Key Vault References vs. Java SDK

There are two common ways for a Java workload to consume secrets.

### 20.1. Approach A: Direct Java SDK

~~~text
Java application
→ SecretClient / Managed Identity
→ Key Vault
→ secret value inside Java process
~~~

Advantages:

- Full control over when to read, refresh, and pin versions.
- Handles metadata, expiration, and business fallbacks.
- Same logic works across App Service, AKS, and VMs.
- Code-level telemetry and explicit secret-name validation.

Trade-offs:

- Adds SDK dependencies and lifecycle/retry code.
- Must design secret caching, rotation, and exception handling.
- Must avoid calling the vault on every request.

### 20.2. Approach B: Key Vault References in App Settings

Some Azure runtimes such as App Service and Functions support **Key Vault references** in application settings, e.g.:

~~~text
Setting name: PAYMENT_API_KEY

Setting value:
@Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/orders-payment-api-key/)
~~~

The platform resolves the reference using the configured identity, and the **Java app reads the value from environment/app settings** like ordinary configuration—no `SecretClient` needed for that variable.

Important details:

- The runtime still receives the **secret value** in process environment/config; never log or dump it.
- Vault RBAC and networking must still allow the app's identity.
- Which identity resolves the reference depends on runtime configuration.
- Versionless references follow platform cache/refresh intervals, **not guaranteed to update instantaneously**.
- Use references instead of the SDK only when the app needs no custom metadata, version, or rotation logic.
- Verify exact Key Vault reference syntax and limits for your runtime and tier.

### 20.3. Decision Table

| Need | Java SDK | Key Vault Reference |
|---|---|---|
| Read secret at startup | Yes | Yes, where runtime supports it |
| Fetch a specific secret version | Yes | Yes, via supported URI/config |
| Inspect metadata / expiration | Yes | Inconvenient for Java |
| Application-controlled refresh | Yes | Relies on platform refresh |
| Less Java boilerplate | Needs SDK code | Usually simpler |
| Portable across cloud runtimes | Java SDK is flexible | Feature tied to Azure runtime |
| Many dynamic per-tenant secrets | Possible, mind quotas/permissions | Poor fit for large setting counts |
| Restrict app permissions | Data-plane RBAC still required | Data-plane RBAC still required |

**Never use Key Vault references as an end-user authorization mechanism.** They only supply backend configuration secrets.

## 21. Spring Boot: Injecting SecretClient and Decoupling SecretProvider

### 21.1. Spring Bean

In an application already using Spring Boot dependencies, configure `SecretClient` as a singleton bean:

~~~java
package com.example.keyvault;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KeyVaultBeans {

    @Bean
    public SecretClient secretClient() {
        String vaultUrl = System.getenv("KEY_VAULT_URL");

        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("Missing KEY_VAULT_URL");
        }

        return new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

**Spring Boot dependencies are not included in the minimal Maven POM from section 8.** This snippet shows integration inside an existing Spring Boot project rather than compiling standalone with the demo POM.

### 21.2. Keep Vault Calls Out of Controllers

An interface decouples infrastructure from domain logic:

~~~java
package com.example.keyvault;

public interface SecretProvider {
    String requireSecret(String name);
}

public final class KeyVaultSecretProvider
        implements SecretProvider {

    private final com.azure.security.keyvault.secrets.SecretClient client;

    public KeyVaultSecretProvider(
            com.azure.security.keyvault.secrets.SecretClient client) {
        this.client = client;
    }

    @Override
    public String requireSecret(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Secret name required");
        }
        String value = client.getSecret(name).getValue();
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Secret value unavailable");
        }
        return value;
    }
}
~~~

This separation-of-concerns example **omits caching, retries, and rotation**. In Java/Spring, each `public` top-level type must live in its own `.java` file. Injecting `SecretProvider` into business services lets unit tests run without calling real Key Vault.

### 21.3. Spring Config and Secret Lifecycles

- Properties should hold **vault URL, secret names, and refresh intervals**—never secret values.
- For startup-required secrets, fail fast with sanitized error messages.
- For dynamic rotation, build a synchronized cache/refresh service with metrics.
- Never enable SDK/WebClient debug HTTP body logging on secret-handling paths.
- Never expose secret values via Spring Actuator **`/env`**, **`/configprops`**, health details, or error pages.
- Restrict Actuator endpoints to private/admin scopes with sanitization enabled.

## 22. Unit and Integration Testing Without Leaking Secrets

### 22.1. Unit Tests Using Fakes

Example:

~~~java
package com.example.keyvault;

import java.util.Map;

public final class FakeSecretProvider implements SecretProvider {
    private final Map<String, String> values;

    public FakeSecretProvider(Map<String, String> values) {
        this.values = values;
    }

    @Override
    public String requireSecret(String name) {
        String value = values.get(name);
        if (value == null) {
            throw new IllegalArgumentException("Unknown demo secret");
        }
        return value;
    }
}
~~~

Unit test:

~~~java
SecretProvider secrets = new FakeSecretProvider(
    java.util.Map.of(
        "orders-payment-api-key", "DEMO_ONLY_FOR_UNIT_TEST"));

String demo = secrets.requireSecret("orders-payment-api-key");
if (!"DEMO_ONLY_FOR_UNIT_TEST".equals(demo)) {
    throw new AssertionError("Unexpected demo secret");
}
~~~

Unit tests never need Entra or Key Vault. Fakes test business logic cleanly without network flakiness.

### 22.2. Integration Tests with a Dedicated Vault

When verifying the Azure SDK end-to-end:

1. Provision a dedicated lab Key Vault with approved role assignments.
2. Store a non-sensitive demo value.
3. Verify `getSecret` succeeds.
4. Test an unauthorized identity → expects 403 or equivalent denial.
5. Test an invalid secret name → expects proper error.
6. Test latest and version-pinned reads.
7. Test rotation and application refresh.
8. Test network restriction from an unauthorized environment.
9. Collect request IDs and metrics without logging values.
10. Clean up demo secrets/lab vault per retention policy.

Never write real Key Vault secrets into JUnit snapshots, screenshots, CI logs, or test reports.

### 22.3. Never Use Tests to Escalate Permissions

If an integration test lacks access, never let the test runner grant itself **Key Vault Administrator** or disable firewalls. CI jobs must use roles defined in IaC/policies with no self-privilege-escalation rights.

### 22.4. Testing Rotation in Staging

- App A uses version V1.
- Operator sets V2 in the vault.
- Canary App B refreshes V2.
- Partner auth accepts V2.
- App A restarts/refreshes per schedule.
- Revoke V1 once all instances use V2.
- Monitor error budgets, partner 401s, and Key Vault 403/429s.
- Drill rollback per runbook if V2 fails.

## 23. Soft-Delete, Purge Protection, and Recovery

Key Vault supports **soft-delete** and optional **purge protection** to protect against accidental permanent deletion. Retention windows and policy mutability depend on vault type and creation time—always verify before creating production vaults.

### 23.1. Deleting a Secret Is Not Purging

Key concepts:

- **Delete secret:** marks the secret deleted, recoverable during soft-delete retention when permitted.
- **Recover deleted secret:** restores it while still inside retention and permitted.
- **Purge:** permanent deletion subject to permissions and protection settings.
- **Purge protection:** blocks purging until retention expires, usually critical for production vaults.

**Never run `purge` casually in labs** just to tidy up; purging can be irreversible and purge protection blocks it. Do not assume deleting a resource group immediately frees vault or secret names for reuse.

### 23.2. When a Secret Leak Is Suspected

Incident response plan:

1. Identify which secrets may have leaked and assess the blast radius.
2. Revoke or disable the credential on the **partner system** where appropriate.
3. Generate a new key and rotate it in Key Vault through a secure channel.
4. Refresh or restart all application instances and caches.
5. Audit Key Vault logs, app logs, CI logs, and Git history.
6. Verify versions and access permissions.
7. Quarantine/restrict compromised principals and revoke tokens/sessions per security runbooks.
8. Confirm systems stabilize on the new key.
9. Write a postmortem and close remaining leak paths.

**Deleting a secret in the vault does not revoke copies already exfiltrated**, nor does it revoke keys on partner systems. Rotating and revoking at the source of truth is what closes exposure.

## 24. Monitoring and Auditing Key Vault

### 24.1. Telemetry Layers

| Layer | Metrics or Logs | Purpose |
|---|---|---|
| **Key Vault service** | Requests, latency, throttling/error codes per features | Track service health and quotas |
| **Key Vault data-plane diagnostics** | Secret get/set/list/delete metadata and results per diagnostic settings | Access auditing |
| **Azure Activity Log** | Vault resource, network, and role assignment changes | Control-plane auditing |
| **Java application** | Credential failures, `getSecret` latency, cache hits/refreshes | Application SLOs |
| **Rotation service** | Versions created, credential activations, rollback events | Lifecycle assurance |
| **Microsoft Entra logs** | Identity/token anomalies per log permissions | Authentication investigation |
| **Partner API** | Unauthorized responses post-rotation, external latency | Verify real key works |

Exact metric names and log categories vary by resource, tier, and diagnostic mode; do not assume all are enabled out of the box when creating a vault. Configure diagnostic settings and retention deliberately.

### 24.2. Safe Logging

~~~json
{
  "event": "KEYVAULT_SECRET_RESOLVE",
  "vaultName": "kv-orders-prod-example",
  "secretName": "orders-payment-api-key",
  "status": "SUCCESS",
  "durationMs": 48,
  "correlationId": "corr-example-481"
}
~~~

This JSON is an illustrative telemetry example. Never include **`secretValue`**, access tokens, connection strings, `Authorization` headers, or raw HTTP bodies. Even `secretName` can hint at internal topology; restricted environments may log only a hash or alias.

### 24.3. Alerts to Configure

- Spikes in 403/401 vault requests.
- Rising Key Vault 429 throttling or p95 latency.
- Cache refresh failures or startup secret-fetch failures.
- Secrets/certificates approaching expiration via metadata/events.
- Overdue rotations or apps pinned to stale versions.
- Unapproved role assignment, network, or firewall changes.
- Unusual off-hours secret read spikes.
- Accidental secret material appearing in logs or build artifacts.

### 24.4. Expiry Notifications

You can subscribe to **Azure Event Grid** Key Vault events for near-expiry, expired, or version-changed secrets/certificates where supported. However:

- Notifications are signals; they do not replace managed rotation schedules.
- Do not assume exactly-once event delivery or automatic partner key rotation.
- Consumers need idempotency and runbooks for subscription/DLQ failures.
- Pair events with periodic inventory/metadata checks to catch missed events.

### 24.5. Observability Must Never Leak Secrets

Never enable **HTTP BODY logging** on the Key Vault SDK in production if responses can include secret values. Never attach secret values to trace attributes, metric labels, or exception messages. Log status codes, vault aliases, request IDs, duration, and credential types per policy with strict sanitization.

## 25. Availability, Caching, and Fail-Closed Behavior

### 25.1. During a Key Vault Outage

An application may be in one of several states:

| State | Risk | Strategy |
|---|---|---|
| Running instance with cached secret | Can still call partner while credential remains valid | Serve from cache per TTL/security policy |
| New instance starting without secret | Startup fails or service unavailable | Fail fast / readiness false, bounded retries |
| Secret just revoked | Cache holds unsafe credential | Fail closed / force refresh per incident policy |
| Vault returns 429 | Retry storm | Backoff, cap concurrent fetches, lower refresh frequency |
| DNS / private network outage | Request timeouts | Fix networking; never disable TLS |
| Partner rotated key ahead of app | App auth errors | Rotation rollback / dual-key overlap |

### 25.2. Readiness vs. Liveness

**Never** let a liveness probe call Key Vault every 5 seconds; if the vault slows down, Kubernetes will restart every pod and trigger a thundering herd. Liveness checks whether the process is alive; readiness checks whether the app holds required configuration and can safely serve requests.

During a Key Vault outage, instances holding valid cached secrets can stay ready; instances without credentials or holding revoked credentials must fail readiness on secret-dependent routes per policy.

### 25.3. Cache Refresh with Jitter

Suppose 100 instances all refresh on the exact same second:

~~~text
100 concurrent Key Vault GETs
→ easily triggers spikes/throttling with many secrets on a smaller vault
~~~

Add jitter to refresh windows and tune TTLs to rotation SLAs, per-service quotas, and security needs. Never stretch TTLs indefinitely to hide network bugs.

### 25.4. Never Fall Back to a Key in the Binary

Anti-pattern:

~~~java
String key;
try {
    key = secretClient.getSecret(name).getValue();
} catch (Exception ignored) {
    key = "HARDCODED_BACKUP_KEY";
}
~~~

Such a fallback exposes credentials in binaries and can keep apps running on revoked keys. Replace with explicit errors, policy-compliant caching, or an approved degraded mode.

## 26. Quotas, Performance, and Cost

### 26.1. Never Call the Vault on Every Request

Suppose Orders API receives **1,000 requests/sec** and each request fetches a secret:

~~~text
1,000 × 60 × 60 × 24
= 86,400,000 Key Vault GETs/day
~~~

This is a **hypothetical calculation**, not an Azure quota. It drives up call volume, cost, and latency.

If 50 instances read one secret every **10 minutes** with a simple TTL cache:

~~~text
50 instances × 6 times/hour × 24 hours
= 7,200 GETs/day
~~~

Not counting restarts, rotation events, concurrent refreshes, retries, or multiple secret names, the contrast between per-request fetching and controlled caching is dramatic.

### 26.2. Cost Components

| Component | Cost Driver |
|---|---|
| Key Vault operations | Priced per API operation count and tier used |
| Premium / HSM features | Different pricing rates compared to Standard |
| Key rotation and versions | Management operations and lifecycle features |
| Azure Monitor | Diagnostic log ingestion, retention, and alerts |
| Private Endpoint and networking | Private Link, NAT/firewalls, cross-region data transfer |
| App runtime | App Service, AKS, VMs, Container Apps/Functions |
| High availability / DR | Multi-region resources and redundancy plans |
| CI/CD | Integration tests, repeated provisioning, auditing |

Never hard-code static pricing into architectures: consult Azure pricing tables, Cost Management, and budgets for your **exact region, tier, and date**.

### 26.3. Cost Is Not the Only Factor

Long cache TTLs reduce vault calls yet widen the window where an app uses an old secret after rotation or revocation. Balance:

- Rotation recovery time.
- Exposure risk.
- Latency SLOs.
- Quotas and peak bursts.
- Security and compliance requirements.
- Application failover behavior.

**Cost savings must never undermine committed security guarantees.**

## 27. Real-World Deployment Story: Orders API on App Service

A clean, verifiable deployment sequence:

1. Create resource group, App Service plan, and App Service in an approved subscription.
2. Enable system-assigned managed identity on Orders API.
3. Provision Key Vault with RBAC enabled and network/security settings via IaC.
4. Operator sets **`orders-payment-api-key`** through a secure channel.
5. Assign `Key Vault Secrets User` to the App Service's principal ID.
6. If private access is required, configure VNet Integration, Private Endpoint, DNS, and firewalls.
7. Set **`KEY_VAULT_URL`** and **`KEY_VAULT_SECRET_NAME`** (never the value).
8. Deploy the JAR and initialize a singleton `SecretClient` via DI.
9. Read the secret at startup or via controlled cache refresh; report ready only when valid.
10. Test the partner API using the credential without logging values or headers.
11. Enable app and Key Vault metrics and audit logging.
12. Rehearse canary key rotation.
13. Test incident paths: revoked key, vault 403, timeout/429, partner 401.
14. Periodically review roles, orphaned vaults, expirations, and costs.

**No real Azure operations were run while writing this lesson.** These steps form an illustrative runbook for learners and deployment teams.

## 28. Common Anti-Patterns

| Anti-Pattern | Why It Is Dangerous | Better Approach |
|---|---|---|
| Committing secrets in `application.properties` | Leaks via source, history, and build artifacts | Key Vault + managed identity |
| Using Azure service account keys despite Entra support | Unnecessary secret sprawl | Direct identity-based auth |
| Granting `Key Vault Administrator` to every app | Huge blast radius | Read-only `Secrets User` |
| Assuming Azure `Contributor` reads secret values | Confuses control and data planes | Dedicated data-plane RBAC |
| Passing secret values through CI env logs | Credential leakage | Secure secret provisioning and rotation |
| Creating `SecretClient` per HTTP request | HTTP/token/connection overhead | Singleton DI client |
| Calling `getSecret` on every HTTP request | 429s, cost, and latency spikes | Startup fetch or TTL cache refresh |
| Unversioned rotations | Hard to audit or roll back | Secret versions and rollout plans |
| Pinning one version forever | App misses rotated keys | Versionless refresh or planned rollout |
| Setting `expiresOn` thinking it rotates keys | Partner key remains stale | Rotation service and runbooks |
| Ignoring partner-side revocation | Leaked secret stays valid | Revoke at source of truth |
| Logging secrets in logs/exceptions | Credential leakage | Sanitized telemetry |
| Replacing Key Vault URL with private IP | Breaks TLS/hostname validation | FQDN + private DNS |
| Opening public firewall wide to fix 403 | Exposes attack surface | Fix identity or network at the right layer |
| Infinite retries on 403/404 | Self-inflicted DDoS on the vault | Classify errors properly |
| Calling `getSecret` in liveness probes | Pod restart storms | Separate readiness + caching |
| Unbounded secret cache TTLs | Ignores rotation and revocation | Bounded TTL, refresh, security policy |
| Unit tests hitting production vaults | Cost, data exposure, flakiness | Fake provider + lab integration tests |
| Deleting/purging secrets to clean up fast | Risk of permanent data loss | Follow soft-delete/purge-protection policies |
| Treating Key Vault as a general config DB | Extra cost and complexity | Use App Configuration for non-secrets |

## 29. Symptom-Based Diagnostic Runbooks

### 29.1. Java Receives 403 Even Though the Vault Exists

Check in order:

1. Read status code, error code, and request/correlation ID **without logging secret values**.
2. Confirm whether code runs locally, on App Service, AKS, or CI.
3. Identify the active `TokenCredential` and its **principal object ID**.
4. Check the vault permission model: Azure RBAC vs. access policies.
5. Inspect role assignments/access policies for that principal at the exact scope.
6. Distinguish **`Key Vault Secrets User`** from `Key Vault Reader` or Azure `Contributor`.
7. Account for Azure RBAC propagation if the role was just granted.
8. Inspect network restrictions, firewalls, private endpoints, and DNS.
9. Verify tenant ID, token audience, and managed identity client ID.
10. Test with an authorized demo secret without printing its value.
11. If still failing, gather sanitized diagnostics and correlate with Azure Monitor / Key Vault audit logs.
12. Turn the root cause into a regression or IaC permission test.

Never elevate to `Owner`/`Administrator` as a "quick fix" before knowing whether the fault is networking, scope, or token mismatch.

### 29.2. Java Receives 404 Not Found

Possibilities:

- Wrong **vault URL** (dev/test/prod mix-up).
- Wrong secret name, casing, or format per API rules.
- Passing a version ID belonging to a different secret.
- Secret/version is deleted, nonexistent, or disabled per state.
- A permission/network error masked as 404 by an app wrapper.

Actions:

1. Verify `KEY_VAULT_URL` and `KEY_VAULT_SECRET_NAME`.
2. Confirm the vault sits in the expected subscription, region, and tenant.
3. Inspect metadata via an authorized admin channel without printing values.
4. Check pinned versions and whether rotation created a new version.
5. Check app config caches and versions.
6. Never auto-create an empty secret when `get` fails.

### 29.3. 429s During Scale-Out

Symptoms: Key Vault latency climbs, SDK retries surge, new pods fail readiness.

Investigation steps:

1. Measure instance counts, requests/sec, and GET/SET/LIST breakdown.
2. Check whether the app calls `getSecret` on every HTTP request.
3. Check for stacked multi-layer retries.
4. Introduce TTL caching or startup caching if permitted by business rules.
5. Add jitter, coordinate refreshes, and bound concurrency.
6. Honor `Retry-After`.
7. Scale gradually and validate under controlled load.
8. Check per-vault quotas and limits for your tier.
9. Never disable retries completely when configured properly; enforce a clear retry budget.

### 29.4. Works Locally, Fails on App Service

- Local credential is an Entra user, while production uses a different managed identity.
- Role assigned to the developer instead of the App Service principal.
- Wrong production `KEY_VAULT_URL` or tenant.
- App Service uses user-assigned identity without selecting `clientId`.
- Production VNet, DNS, or firewall differs from local workstation.
- App Service Key Vault reference failed to resolve due to missing permissions.
- App restarted/scaled before identity/role propagation completed.

Fix: verify actual runtime identity, scope, networking, and dependency readiness—never copy developer client secrets into production.

### 29.5. Rotated the Secret Yet Java Still Uses the Old Key

- App cached the old version.
- Code calls `getSecret(name, pinnedVersion)`.
- App Service Key Vault reference cache has not refreshed yet.
- Partner API still accepts the old key, hiding the issue from health checks.
- Some instances refreshed while others did not.
- New secret version is disabled, not-before, or expired.
- No dual-key overlap or partner has not activated the new credential.

Runbook: compare version metadata across instances, canary a single instance, verify partner-side key state, coordinate refresh/restart, and revoke the old key on schedule. Never log both old and new keys "to compare them."

### 29.6. Private Endpoint TLS or DNS Errors

- `SecretClient` must use the **vault FQDN**, never a raw private IP.
- Verify the private DNS zone **`privatelink.vaultcore.azure.net`** and VNet links.
- Check App Service outbound VNet Integration or pod networking.
- Check routes, NSGs, Azure Firewalls, and proxies.
- Never bypass certificate validation.
- Never treat a successful Entra token call as proof that network access to the vault works.

### 29.7. SDK Errors on Expired/Disabled Secret

- Identify which exact version metadata was read.
- Check `ExpiresOn`, `NotBefore`, and `Enabled`.
- Contact the rotation owner and follow incident rules.
- Never revert to an older secret if it was revoked due to a leak.
- On critical systems, mark secret-dependent routes unavailable per policy.
- Trigger escalation alerts and execute a safe recovery plan.

## 30. Security and Reliability Testing

| Test Case | Action | Expected Result |
|---|---|---|
| Happy path local | Developer with `Secrets User` reads demo secret | `getSecret` succeeds; value never logged |
| No data role | Identity lacks read permission | 403 or matching denial; no value leaked |
| Reader metadata-only | Identity holds `Key Vault Reader` | Cannot read secret value |
| Wrong vault URL | Points to non-existent vault | Clear error; no hard-coded fallback |
| Wrong secret name | Queries missing name | Does not auto-create secret |
| Wrong version | `getSecret` with invalid version | Error; does not silently fall back to latest |
| Disabled / expired | Reads unavailable version | Fails/alerts per policy |
| Cache miss | Empty secret cache or miss | Fetches from Key Vault within bounds |
| Concurrent startup | 100 instances start together | No retry storm |
| Rotation | Set V2, refresh app | App picks up new version per contract |
| Partner rejects V2 | Partner API returns 401 | Rollback/quarantine per runbook |
| Vault 429 | Simulate throttling | Bounded backoff, full metrics |
| DNS / network down | Private endpoint unreachable | Sanitized error; TLS stays enabled |
| Secret leaked in log | Scan test logs | Zero secret values or tokens present |
| Managed identity changed | Principal loses role | Access denied cleanly |
| Role revocation | Remove data-plane permission | Access denied after propagation |
| Service restart | Cache cleared | Reloads or fails closed per policy |
| App setting reference refresh | Versionless reference updates | App receives new value per platform |
| Dev/prod separation | Prod secret queried by dev identity | Permission denied |
| Secret delete recovery | Soft-delete in approved lab | Restores per policy without purging |

Never test by rotating production secrets, disabling real firewalls, or deleting shared resources without owner approval.

## 31. Pre-Production Checklist

- [ ] Identified which secrets **cannot be replaced by Entra managed identity**.
- [ ] Vault sits in the right subscription, resource group, region, and ownership.
- [ ] Intentionally selected RBAC or access policy permission model.
- [ ] Application identity holds only **`Key Vault Secrets User`** or least-privilege data permissions.
- [ ] Rotation identity separated; app readers never hold write permissions.
- [ ] Managed/workload identity enabled and principal/client IDs verified.
- [ ] Zero developer identities, client secrets, or admin keys in production config.
- [ ] Secret values excluded from Git, Docker images, JARs, CI logs, and unprotected IaC state.
- [ ] SDK dependencies pinned via versions/BOM and scanned for CVEs.
- [ ] `SecretClient` reused via DI.
- [ ] App never calls `getSecret` on every request.
- [ ] Cache TTL, refresh, version pinning, and stale-secret policies defined.
- [ ] Clear fail-fast/fail-closed behavior when vault or partner is unavailable.
- [ ] Java logs, traces, HTTP body logging, and exception redaction audited.
- [ ] Secret names/URLs and non-sensitive configs managed per environment.
- [ ] Private Endpoints, VNet integration, firewalls, and DNS aligned with policy.
- [ ] TLS and certificate verification enabled.
- [ ] RBAC propagation and identity rotation tested on staging.
- [ ] Soft-delete, purge protection, and recovery permissions configured.
- [ ] Rotation owner, reminders, expiration, and partner-side revocation defined.
- [ ] V1→V2 canary rotation and rollback rehearsed.
- [ ] Tested 401/403/404/429, timeouts, and concurrent startups.
- [ ] Alerts set for unauthorized requests, throttling, overdue rotations, and secret expirations.
- [ ] Audit logs and retention match data classification.
- [ ] App Service Key Vault reference cache/refresh semantics understood if used.
- [ ] Spring Actuator and config endpoints never expose secrets.
- [ ] Key Vault is not used as a database for non-secret configuration.
- [ ] Measured Key Vault calls/sec and estimated cost/tier/quotas.
- [ ] Incident response plan covers leaked secrets and compromised identities.
- [ ] Lab and production resources carry tags, budgets, and cost alerts.
- [ ] Documented ownership and which identities read each secret.

## 32. Practice Exercises

### Exercise 1: Choose the Key Vault Object Type

For each requirement, pick Secret, Key, or Certificate:

1. Partner API key.
2. RSA key used to sign data without exporting the private key.
3. TLS certificate for the app's domain.
4. Legacy system password.
5. Non-secret feature flag.
6. Azure Storage supporting Microsoft Entra identity.

Explain why some cases do not need a Key Vault secret at all.

### Exercise 2: Create an RBAC Vault in a Lab

1. Select a lab subscription and resource group.
2. Create a vault using the Azure RBAC permission model.
3. Read `vaultUri` and non-sensitive metadata.
4. Retrieve the developer's principal object ID.
5. Have an authorized operator create the role assignment.
6. Create a secret with value **`DEMO_ONLY_NOT_A_REAL_SECRET`**.
7. List names and IDs without displaying values.
8. Document which role/permission each step required.

### Exercise 3: Java SecretClient

1. Create a Java 17 Maven project.
2. Add `azure-security-keyvault-secrets` and `azure-identity` per approved BOM/versions.
3. Implement `ReadSecretDemo` from section 11.
4. Sign in locally via `az login`.
5. Set `KEY_VAULT_URL` and `KEY_VAULT_SECRET_NAME`.
6. Call `getSecret` and print only a success message.
7. Confirm the project contains zero hard-coded real credentials.

### Exercise 4: Test Authorized vs. Unauthorized Principals

Use two lab identities:

- Identity A holds **`Key Vault Secrets User`**.
- Identity B holds only **`Key Vault Reader`** or no data role.

Run `getSecret` with both identities, record status/errors (never values), and explain why Azure `Contributor` or `Key Vault Reader` is insufficient.

### Exercise 5: Versions and Rotation

1. Create version V1 with a demo value.
2. Create version V2 with another demo value.
3. Call `getSecret(name)` and `getSecret(name, V1)`.
4. Compare version metadata and explain the difference.
5. Simulate the partner accepting only V2.
6. Design a V1-to-V2 rollout with canary and rollback.
7. Specify when V1 should be revoked on the partner.

### Exercise 6: Performance Math

An app runs 20 instances serving 500 requests/s. Compare:

- Every request calling Key Vault GET.
- Each instance caching a secret for 10 minutes.
- Refreshing with jitter and bounded retries.

Estimate GETs/day and explain why an overly long cache TTL can violate rotation SLAs.

### Exercise 7: Private Endpoints

Diagram the path from App Service/AKS to Key Vault:

- VNet Integration / outbound route.
- Private Endpoint and IP.
- Private DNS zone.
- Vault FQDN.
- Entra token acquisition.
- RBAC data-plane check.

Explain why connecting directly to a private IP breaks TLS and why network rules differ from data roles.

### Exercise 8: Spring Integration

1. Define a singleton `SecretClient` bean.
2. Define a `SecretProvider` interface.
3. Unit test with `FakeSecretProvider`.
4. Ensure only business services/controllers that need it invoke the provider.
5. Add TTL cache refresh and metrics when genuinely needed.
6. Verify Spring Actuator never exposes values.

### Exercise 9: Diagnose 403

A developer reads the demo secret fine, yet Orders API on App Service gets 403.

Distinguish between:

- App managed identity principal lacks the role.
- App uses a user-assigned identity with the wrong client ID.
- Vault is in access policy mode.
- Vault network firewall / private endpoint denial.
- RBAC has not propagated yet.
- Azure tenant or vault URI mismatch.

Propose a troubleshooting sequence without "granting `Owner` to the app."

### Exercise 10: Leaked Secret Incident

A logging statement accidentally printed the API key. Design the incident response:

1. Isolate logs and restrict access.
2. Revoke the key at the partner.
3. Generate a new credential and update Key Vault.
4. Refresh apps / canary.
5. Audit logs, CI, Git history, and vault access logs.
6. Review RBAC, incident timeline, and policies.
7. Add a regression test blocking secret logging.

### Exercise 11: Compare SDK vs. Key Vault References

A Java App Service only needs an API key at startup, while an AKS app needs runtime refresh upon rotation. Choose the Java SDK or Key Vault reference for each and explain credential scope, latency, cache lifecycles, and platform support.

### Exercise 12: FinOps Review

Assume 50 instances read 10 secrets every 5 minutes. Calculate error-free Key Vault GETs/day, add a hypothetical 10% retry overhead, and list factors that would make this estimate diverge from the real Azure bill.

## 33. Self-Check Questions

1. What object types does Key Vault protect?
2. Is `SecretClient` used for Secrets or Key cryptographic operations?
3. How many versions can one secret name have?
4. How does a Vault URI differ from a Secret ID?
5. Does a versionless lookup force every app instance to refresh immediately?
6. How does a secret value differ from `SecretProperties`?
7. Why should Key Vault not hold all non-secret configuration?
8. Which type of credential does managed identity eliminate?
9. Which identities can `DefaultAzureCredential` select locally?
10. Why does succeeding at `az login` not prove permission to call `getSecret`?
11. How does a principal object ID differ from a client ID?
12. How does Key Vault's control plane differ from its data plane?
13. How does `Key Vault Secrets User` differ from `Key Vault Secrets Officer`?
14. Can `Key Vault Reader` view secret values?
15. Can Azure `Contributor` always read secret values?
16. How do the RBAC model and vault access policy model differ?
17. How does VNet Integration differ from a Key Vault Private Endpoint?
18. Which domain does a Key Vault Private DNS zone typically use?
19. With a private endpoint, should you replace the vault URL with the private IP?
20. What components does Java's `SecretClientBuilder` require?
21. Why should you never print `getSecret().getValue()`?
22. Can a Java `String` be guaranteed to be erased from RAM?
23. Why is reusing `SecretClient` better than creating one per request?
24. How do `SecretClient` and `SecretAsyncClient` differ?
25. What is the impact of reading a secret on every HTTP request?
26. What security trade-off does caching secrets introduce?
27. How does cache TTL differ from secret version lifecycles in Key Vault?
28. How do you distinguish 401 from 403?
29. Why can 403 come from a firewall even when the data role is right?
30. How does debugging a 404 from a wrong secret name differ from a wrong version?
31. How should 429s be handled?
32. Should 403s be retried infinitely?
33. Does rotating a Key Vault secret automatically rotate the API key at a partner?
34. Does version pinning help rollbacks, and what risk does it carry?
35. How do soft-delete, purge, and purge protection differ?
36. Why does deleting a secret not revoke a leaked credential on a partner system?
37. Does a Key Vault reference in App Service eliminate the need for `SecretClient` in Java?
38. Does a Key Vault reference prevent the secret from appearing in the process environment?
39. Under what circumstances can Spring Actuator expose secrets?
40. Why should liveness probes never call Key Vault?
41. Which logs should be enabled to audit secret access?
42. Which fields must never be recorded in telemetry?
43. Why separate the rotation worker identity from the application reader identity?
44. When should you use Entra directly instead of storing a service account password?
45. Which factors affect Key Vault costs?
46. Should you bake an admin key into a Dockerfile to avoid token errors?
47. When changing managed identities, what needs updating?
48. If the vault has an outage and the app has no cached secret, what should happen?
49. Name three critical negative tests before production.
50. What role does Key Vault play in a zero-trust architecture, and what are its limits?

## 34. References

- [Azure Key Vault documentation — Microsoft Learn](https://learn.microsoft.com/azure/key-vault/)
- [Azure Key Vault overview](https://learn.microsoft.com/azure/key-vault/general/overview)
- [About keys, secrets and certificates](https://learn.microsoft.com/azure/key-vault/general/about-keys-secrets-certificates)
- [Authenticate to Key Vault](https://learn.microsoft.com/azure/key-vault/general/authentication)
- [Azure RBAC for Key Vault](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Assign a Key Vault access policy](https://learn.microsoft.com/azure/key-vault/general/assign-access-policy)
- [Azure Key Vault firewall and network settings](https://learn.microsoft.com/azure/key-vault/general/network-security)
- [Private Link for Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/private-link-service)
- [Azure Key Vault soft-delete overview](https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview)
- [Azure Key Vault backup and recovery considerations](https://learn.microsoft.com/azure/key-vault/general/backup)
- [Azure Key Vault monitoring](https://learn.microsoft.com/azure/key-vault/general/monitor-key-vault)
- [Azure Key Vault secret management Java quickstart](https://learn.microsoft.com/azure/key-vault/secrets/quick-create-java)
- [Azure Key Vault Secrets Java SDK README](https://learn.microsoft.com/java/api/overview/azure/security-keyvault-secrets-readme)
- [Azure Identity Java SDK](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
- [DefaultAzureCredential in Java](https://learn.microsoft.com/java/api/com.azure.identity.defaultazurecredential)
- [SecretClient Java API reference](https://learn.microsoft.com/java/api/com.azure.security.keyvault.secrets.secretclient)
- [Use Key Vault references for App Service and Azure Functions](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Entra Workload ID on AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure SDK for Java guidelines](https://azure.github.io/azure-sdk/java_introduction.html)
- [Azure Key Vault pricing](https://azure.microsoft.com/pricing/details/key-vault/)
- [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/)





