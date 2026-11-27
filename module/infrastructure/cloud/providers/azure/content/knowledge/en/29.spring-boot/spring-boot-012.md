# Managing Spring Boot Secrets with Azure Key Vault

A Spring Boot application deployed on Azure App Service needs to connect to a database and call a payment gateway. If database passwords or API tokens are written in `application.yml`, committed to Git, or packaged into a JAR or Docker image, anyone with access to the artifact or repository history can read those secrets. Rotating a secret then forces edits across multiple environments, uncoordinated restarts, and uncertainty over which application uses which credential.

**Azure Key Vault** provides centralized secret storage and management backed by **Microsoft Entra ID**, data-plane authorization, versioning, access auditing, and network-level protections. **Spring Cloud Azure** lets Spring Boot read secrets as a **PropertySource** in the Spring Environment, or use the **Azure SDK for Java** directly via **SecretClient** on demand. Combined with managed identity or workload identity, the application needs no secondary client secret just to access the vault.

This lesson belongs to the **Spring Boot on Azure** chapter in the **CLOUD_PROVIDERS_AZURE** module—spanning subscriptions, resource groups, Entra ID, and networking through deployment, observability, security, and cost management for Azure applications. It focuses on **secret values**; Key Vault also stores **keys** and **certificates**, though all three object types carry distinct APIs and permissions.

**Scope and boundaries:** code examples below illustrate Spring Boot 3.5.x with a compatible Spring Cloud Azure release per official docs, Azure public cloud, and a lab vault. Never place real secrets in documentation, source control, or logs. Never create or modify production Azure resources without approval. SDK versions, permission models, and properties evolve—always check the BOM and docs matching your deployment version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what a secret is and why `application.yml`, container images, Git history, and logs are not safe places for secrets.
2. Distinguish **Key Vault Secrets, Keys, and Certificates**, and understand secret name, value, version, enabled state, expiration, and tags.
3. Diagram the flow Spring Boot → Entra ID/managed identity → Key Vault → bean/database.
4. Distinguish Azure's **management plane** from the **Key Vault data plane**, RBAC, and access policies.
5. Configure Spring Cloud Azure **spring-cloud-azure-starter-keyvault-secrets** with a compatible BOM.
6. Use the Key Vault **PropertySource** to feed `@Value`, `@ConfigurationProperties`, and Spring auto-configuration.
7. Use **SecretClient / SecretClientBuilder** to fetch secrets on demand and handle errors safely.
8. Authenticate locally via Azure CLI and deploy using managed identity or AKS workload identity.
9. Apply least privilege, the **Key Vault Secrets User** role, environment-separated vaults, and explicit secret loading lists.
10. Understand secret naming rules, hyphen-to-dot mapping, property precedence, and multi-vault setups.
11. Design versioned secret rotation, rollback, cutovers, and zero-disruption connection handling.
12. Distinguish PropertySource refresh from bean rebinding, HikariCP datasource credentials, and token caching.
13. Connect to Key Vault over Private Endpoints, DNS, and TLS, and handle 401/403, timeouts, and throttling.
14. Prevent secrets from leaking via Spring Actuator, HTTP endpoints, logs, exceptions, traces, or CI/CD.
15. Plan testing, observability, incident response, recovery, retention, and cost controls.

## 2. What Is an Application Secret?

### 2.1. Common Examples

- JDBC passwords for Azure SQL Database or PostgreSQL when Entra/passwordless auth is not yet enabled.
- API keys for calling a payment partner.
- Third-party application client secrets.
- Webhook signing secrets / HMAC keys when shared-secret verification is required.
- SMTP passwords or legacy service credentials.
- Connection strings containing a username/password or storage account key.
- Long-lived access tokens for external SaaS integrations.

Not every configuration setting is a secret:

| Data category | Examples | Recommended storage |
|---|---|---|
| Public/non-secret config | Environment name, endpoint URL, cache TTL | `application.yml`, App Configuration |
| Secret | DB password, API token, signing secret | Key Vault Secrets |
| Cryptographic keys requiring managed crypto ops | Encryption/signing keys | Key Vault Keys where supported capabilities fit |
| TLS/authentication certificates | X.509 certificates and associated private keys | Key Vault Certificates or dedicated cert management |
| Short-lived runtime access tokens from Entra ID | `TokenCredential` acquisition | Azure Identity / managed identity; never hard-code as long-lived secrets |

**Never store a database password in Key Vault when the Azure service supports and your architecture permits direct managed identity / Entra authentication.** Eliminating secrets altogether is safer and simpler than merely moving a password from a file to a vault.

### 2.2. Where Secrets Leak

~~~mermaid
flowchart TD
    S["Application secret"] --> G["Git commit / history"]
    S --> I["Container image layers"]
    S --> L["Application / CI logs"]
    S --> E["Environment / process inspection"]
    S --> A["Actuator /env, /configprops"]
    S --> H["HTTP response / exception"]
    S --> D["Heap dump / diagnostic artifacts"]
    S --> B["Backup / exported config"]
~~~

Moving a secret into Key Vault **does not eliminate** leak risks once the application loads it into RAM. Secrets can still be written to logs, captured in crash dumps, or accidentally serialized in HTTP responses. You must manage the **entire secret lifecycle**.

## 3. What Problem Does Azure Key Vault Solve?

### 3.1. Resource and Logical Model

~~~mermaid
flowchart LR
    APP["Spring Boot on App Service / AKS / VM"] --> ID["Microsoft Entra ID"]
    ID -->|Access token| APP
    APP -->|TLS HTTPS + token| KV["Azure Key Vault"]
    KV --> SEC["Secret name + versions"]
    APP --> DB["Database / external API"]
    KV -. "Audit / metrics" .-> MON["Azure Monitor"]
    APP -. "App logs / traces" .-> MON
~~~

Detailed flow:

1. The application receives the **vault endpoint** (a URL, not a secret) via deployment configuration.
2. Azure Identity acquires an access token for the active principal.
3. The application connects to the Key Vault endpoint over HTTPS/TLS.
4. Key Vault evaluates identity, permission model, network policies, and secret status.
5. If authorized, Key Vault returns the requested secret value and version.
6. Spring injects the value into a PropertySource, or Java logic reads it via `SecretClient`.
7. Logs/metrics emit approved operational metadata without recording the raw secret value.

A vault name, URI, and subscription ID **are not secrets**; you do not need to hide them inside a vault. Still, control deployment configuration carefully so workloads never accidentally point at the wrong environment's vault or leak unnecessary topology details.

### 3.2. Key Vault Secrets, Keys, and Certificates

| Type | Contents | Operations/API |
|---|---|---|
| **Secrets** | Arbitrary string/byte secret values supported by the service | set/get/list versions/disable/delete |
| **Keys** | Cryptographic keys with policy-protected key material | encrypt/decrypt/sign/verify/wrap/unwrap |
| **Certificates** | X.509 certificate lifecycle and metadata | import/create/manage certificates |

Storing a PEM private key as a secret technically stores the text, but **misses Key Vault Keys policies** around key usage, HSM backing, and cryptographic operation audits. Pick the object type matching the security requirement.

### 3.3. Core Concepts

- **Vault:** an Azure resource with an endpoint like `https://<vault-name>.vault.azure.net/` in Azure public cloud.
- **Secret name:** logical identifier such as `payment-api-token`.
- **Secret version:** a distinct revision created each time a new value is set, identified by a version ID.
- **Current/latest:** the version returned by an unversioned `get` call per service semantics.
- **Enabled:** flag controlling whether a version can be retrieved.
- **Expires / Not before:** validity window metadata enforced by service/client checks.
- **Tags:** operational metadata for owner, service, and rotation policy—never put secret values in tags.
- **Soft delete / purge protection:** protects against accidental deletion according to retention settings.

**Expiration does not mean "auto-rotation."** Without a rotation pipeline updating both the issuer and consumers, an expired secret can still bring down the service.

### 3.4. Key Vault Does Not Replace Application Authorization

Key Vault decides whether a principal may read a secret. It has no awareness of whether HTTP user A is authorized to view tenant B's records. When Spring Boot uses a shared managed identity to read a DB password and query multi-tenant data, the application still must enforce **authorization at the API and database layers**.

## 4. Three Ways to Integrate Secrets in Spring Boot

| Approach | Flow | Best fit | Watch-outs |
|---|---|---|---|
| **Spring Cloud Azure PropertySource** | Key Vault → Spring Environment → `@Value`/auto-config | Datasource passwords and startup configuration | Early loading, precedence, refresh, bean lifecycle |
| **Azure SDK SecretClient** | Java code fetches from Key Vault on demand | Event-driven token lookup, version/metadata checks | Manual caching, throttling, and error handling |
| **Platform reference/mount** | App Service Key Vault reference or AKS CSI/secret mount → env/file → Spring | When the platform manages secret injection | Refresh lag, identity, sync mechanics, file permissions |

You do not need all three simultaneously. Avoid loading the same secret through multiple overlapping paths with ambiguous precedence where operators cannot tell which value is active.

### 4.1. PropertySource: "Secrets as Configuration"

Spring Cloud Azure loads secrets as a PropertySource inside the Spring Environment **early**, before most beans initialize:

~~~text
Key Vault:  db-password = <secret-value>
      ↓
Spring Environment: db-password
      ↓
spring.datasource.password = placeholder db-password
      ↓
Spring DataSource/HikariCP initializes
~~~

This fits secrets needed during Spring auto-configuration such as datasource credentials, provided you remember: **reloading the PropertySource does not automatically update credentials inside already-constructed beans**.

### 4.2. SecretClient: "Read Secrets on Demand"

~~~text
PaymentService
   ↓ calls provider to fetch token on demand
SecretClient.getSecret("payment-api-token")
   ↓
Key Vault returns KeyVaultSecret
   ↓
Token is used in memory, never printed to logs
~~~

This suits cases needing version IDs, expiration timestamps, metadata, or custom caching/refresh logic. However, calling `getSecret` **on every web request** adds latency, risks HTTP 429 throttling and higher charges, and couples availability directly to Key Vault.

### 4.3. Platform References: "Runtime Secret Injection"

For example, on App Service, an App Setting can hold a **Key Vault reference** resolved by the platform via managed identity. On AKS, the Secrets Store CSI Driver can mount secrets as files or sync them to Kubernetes Secrets when configured.

These shift where refresh and permissions live:
- App Service references follow platform caching/refresh cycles.
- CSI-mounted files depend on file permissions, sync/rotation intervals, and scheduling.
- Kubernetes Secrets require their own RBAC, encryption at rest, and retention policies.
- Process environment variables generally **do not update live** when the platform resolves a new value unless the process restarts or rebinds.

Never conflate Key Vault PropertySource refresh, App Service references, and CSI driver syncing—they operate differently.

## 5. Designing Permissions: Microsoft Entra ID and Key Vault

### 5.1. Two Permission Planes

- **Management plane (Azure Resource Manager):** create/modify vaults, networking, settings, and IAM.
- **Data plane (Key Vault):** get/list/set/delete secrets, keys, and certificates.

A principal holding **Contributor** on the resource group cannot by default read secret values from a vault using Azure RBAC. Conversely, a principal permitted to read secrets cannot alter firewall rules, create vaults, or assign RBAC roles.

### 5.2. Common RBAC Roles

| Role | Typical permissions | Intended use |
|---|---|---|
| **Key Vault Reader** | Read metadata only; **cannot read secret values** | Monitoring/metadata discovery |
| **Key Vault Secrets User** | Read secret values | Spring Boot runtimes needing get/list |
| **Key Vault Secrets Officer** | Manage secrets without assigning roles | Controlled release/rotation pipelines |
| **Key Vault Administrator** | Broad data-plane management across objects | Special administration; never assign to apps |
| **Key Vault Data Access Administrator** | Manage a subset of Key Vault data role assignments conditionally | Identity/governance teams |

When an app only reads tokens, **Key Vault Secrets User** is far more appropriate than Secrets Officer or Administrator. A vault-level role grants read access to all secrets in that vault; consider per-app vaults or narrower scoping/ABAC where supported and required by policy.

### 5.3. Azure RBAC vs. Legacy Vault Access Policies

Key Vault supports two permission models:
- **Azure role-based access control (RBAC)**; or
- **Vault access policies** (legacy / existing model).

These two models are **mutually exclusive**. Never assign the Key Vault Secrets User RBAC role and expect it to work on a vault configured with access policies. Likewise, adding an access policy on an RBAC-enabled vault will not fix a 403 error.

Always check the vault's permission model before granting access; migrating permission models in production is sensitive, requires approval, and demands care so administrators do not lock themselves out.

### 5.4. Separating Principals

A baseline separation design:

~~~mermaid
flowchart LR
    DEV["Developer identity"] -->|Limited lab access| KVD["kv-orders-dev"]
    RUNTIME["Orders runtime managed identity"] -->|Secrets User read| KVP["kv-orders-prod"]
    CICD["Release/rotation identity"] -->|Secrets Officer with approval| KVP
    ADMIN["Security platform admin"] -->|Manage IAM/network| KVP
~~~

Production applications must never share developer credentials. CI/CD jobs that create or rotate secrets should use separate identities from the app runtime. Isolating principals and vaults shrinks the blast radius if any single token is compromised.

## 6. Preparing a Safe Lab Environment

### 6.1. Prerequisites

- An Azure subscription approved for lab use with permissions to inspect the resource group/vault and request role assignments.
- An **authorized Key Vault**—never spin up an unapproved vault in production just because you cannot locate one.
- Clearly identified Microsoft Entra identities for the developer and workload.
- JDK and Spring Boot versions compatible with the Spring Cloud Azure BOM.
- Maven or Gradle.
- Azure CLI for environment verification.
- Network reachability to the vault and Microsoft Entra token endpoints.
- Example vault endpoint **https://kv-orders-dev.vault.azure.net/**; substitute your real lab vault name.

To avoid unintended charges or mutations, most commands below read metadata only. Commands creating roles or secrets belong strictly in an **authorized lab**.

### 6.2. Inspect Subscription and Vault

In Bash / Azure Cloud Shell:

~~~bash
az login
az account show --query "{subscription:id, tenant:tenantId, name:name}" -o json

# Replace with the vault provisioned by the platform team.
VAULT_NAME="kv-orders-dev"

az keyvault show --name "$VAULT_NAME" \
  --query "{id:id,uri:properties.vaultUri,rbac:properties.enableRbacAuthorization}" \
  -o json
~~~

**Never print access tokens, credential JSON, or secret values into build logs.** Automated pipelines should use workload federation or managed identity with scoped permissions rather than interactive login.

### 6.3. Inspect Secret Metadata Without Reading Values

~~~bash
az keyvault secret list \
  --vault-name "$VAULT_NAME" \
  --query "[].{name:name,enabled:attributes.enabled}" \
  -o table

# Print URI/version ID of a specific secret; do not print .value.
az keyvault secret show \
  --vault-name "$VAULT_NAME" \
  --name "payment-api-token" \
  --query "id" \
  -o tsv
~~~

If `list` or `show` fails with 403, the vault is not necessarily broken: verify the permission model and data-plane permissions of the signed-in identity. If the secret does not exist, `show` returns 404. Because secret names can also reveal topology in sensitive environments, limit logging them broadly.

### 6.4. Grant Secret Read Role to the Runtime Identity

For vaults using **Azure RBAC**, an authorized platform administrator can grant read access:

~~~bash
VAULT_ID="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault-name>"
APP_PRINCIPAL_OBJECT_ID="<managed-identity-principal-object-id>"

az role assignment create \
  --assignee-object-id "$APP_PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
~~~

This command **modifies IAM**; never run it without approval. **Principal object ID** is the managed identity's RBAC object identifier, **not** the application's client ID. Because a vault-level assignment covers every secret in the vault, consider separate vaults or finer secret scoping where supported and required.

This applies only when the vault uses RBAC. For access-policy vaults, manage permissions via vault access policies rather than mixing models.

### 6.5. Seed a Dummy Value in the Lab

If no test secret exists and you are authorized to create one:

~~~bash
# Use a dummy string only, never a real password/token.
az keyvault secret set \
  --vault-name "$VAULT_NAME" \
  --name "payment-api-token" \
  --value "lab-demo-value-not-a-real-secret" \
  --output none
~~~

**Warning:** command-line arguments can leak into shell history, process listings, or CI logs. This snippet uses a harmless dummy value strictly for lab illustration. Real production secrets must travel through an **approved vault/secret provisioning workflow**, secure tooling, or pipelines that never echo values. Never store real secrets in unencrypted files, source control, or shell history.

### 6.6. Lab Verification Evidence

- Exact subscription/tenant and vault URI.
- Confirmed vault permission model.
- App identity and exact data-plane role/scope.
- Endpoint reachable from developer/runtime hosts.
- Secret name/version exists (never screenshot the value).
- Application reads the dummy secret via PropertySource or SDK.
- Logs/traces show zero secret values.
- Cleanup executed for temporary lab roles and resources.

## 7. Declaring Maven or Gradle Dependencies

### 7.1. Spring Cloud Azure BOM

Spring Boot and Spring Cloud Azure versions must align. Per Microsoft Learn documentation checked at writing time:

| Spring Boot | Suggested Spring Cloud Azure BOM | Notes |
|---|---|---|
| 4.0.x | 7.4.0 | Check Java/Spring compatibility |
| 3.5.x | 6.5.0 | Primary version line used in this lesson |
| 3.1.x–3.5.x | 5.25.0 | 5.x line listed in docs |
| 2.x | 4.20.0 | Legacy; review support lifecycle |

These numbers reflect documentation at writing time and are **not permanently "latest."** If your project uses Boot 3.3 or 3.4, do not blindly copy BOM 6.5.0 just because examples target Boot 3.5. Import the Spring Cloud Azure BOM in dependency management rather than pinning individual modules inconsistently.

### 7.2. Maven with Spring Boot 3.5

Snippet to add to `pom.xml`, assuming Spring Boot parent/dependency management is already present:

~~~xml
<properties>
    <spring-cloud-azure.version>6.5.0</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
    </dependency>
</dependencies>
~~~

**Exact artifact:** `com.azure.spring:spring-cloud-azure-starter-keyvault-secrets`. The broader **spring-cloud-azure-starter-keyvault** also exists if you genuinely use Key Vault keys or certificates alongside secrets.

Do not confuse these with legacy starters such as `azure-spring-boot-starter-keyvault-secrets` or `azure.keyvault.*` properties from older generations.

### 7.3. Gradle with the BOM

Gradle Groovy DSL snippet assuming Spring Boot plugin/dependency management is configured:

~~~groovy
dependencies {
    implementation platform(
        "com.azure.spring:spring-cloud-azure-dependencies:6.5.0"
    )
    implementation "com.azure.spring:spring-cloud-azure-starter-keyvault-secrets"
}
~~~

Gradle Kotlin DSL uses the corresponding Kotlin syntax. Always align all Spring Cloud Azure artifacts on the same BOM. Never accidentally import two conflicting BOMs or downgrade `azure-core`/`azure-identity` to incompatible older versions, which causes `NoSuchMethodError` at startup.

### 7.4. Using the Plain Azure SDK Only

If you do not need a Spring `PropertySource`, you can depend only on:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Here you must manage versions using the Azure SDK BOM or supported dependency management. **The Spring Cloud Azure BOM is not a general Azure SDK BOM for arbitrary libraries**—avoid mixing two uncoordinated BOMs. Likewise, if the Spring starter already auto-configures a `SecretClient` bean suited to your needs, you do not need to duplicate SDK setup manually.

## 8. Option A: Key Vault as a Spring PropertySource

### 8.1. Configuring application.yml

Assume the vault contains two secrets named **payment-api-token** and **db-password**, and the endpoint is supplied via a non-secret environment variable:

~~~yaml
spring:
  application:
    name: orders-api
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: orders-secrets
              endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - payment-api-token
                - db-password
              refresh-interval: 30m

app:
  payment:
    token: ${payment-api-token}
~~~

In the deployment environment:

~~~text
AZURE_KEYVAULT_ENDPOINT=https://kv-orders-dev.vault.azure.net/
~~~

**Explanation:**

- **property-sources** configures one or more Key Vault PropertySources.
- **endpoint** is the vault URI (not a secret).
- **secret-keys** limits which secret names are loaded; if omitted, the PropertySource may attempt to list/load all secrets per library behavior.
- **refresh-interval: 30m** sets the PropertySource refresh period in Spring Cloud Azure releases described on Microsoft Learn.
- **app.payment.token** uses a placeholder to map the Key Vault secret name to your application property.

Never put real secret values in YAML. If the Key Vault, permissions, or network are missing at boot, startup may fail or properties remain unresolved depending on configuration—always test startup failure modes.

### 8.2. Reading Properties with @Value

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PaymentTokenHolder {
    private final String token;

    public PaymentTokenHolder(
            @Value("${app.payment.token}") String token) {
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                "Payment token is not configured");
        }
        this.token = token;
    }

    // Token is used strictly inside the partner client.
    // No getter or public endpoint exposes the token.
    public boolean isConfigured() {
        return !token.isBlank();
    }
}
~~~

Notice that this example intentionally **never prints the token**, exposes no REST getter, and avoids Lombok `@Data`/`@ToString` on classes holding secrets. A `@Value` injected into a singleton bean is resolved when the bean is instantiated. If the PropertySource later refreshes, **never assume that `token` field updates automatically**.

### 8.3. Using Secrets for a Datasource Password

If your database still requires a password, you can name the Key Vault secret **spring-datasource-password**. Spring Cloud Azure maps hyphens to dots for property lookup:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://<db-host>:5432/orders
    username: orders_user
    # spring.datasource.password can be resolved from
    # Key Vault secret: spring-datasource-password
~~~

Spring Cloud Azure docs support mapping the secret **spring-datasource-password** to **spring.datasource.password**. To keep mappings explicit, you can also use a placeholder:

~~~yaml
spring:
  datasource:
    password: ${db-password}
~~~

When configuring URL, username, and password together, avoid mixing up secret names and property keys: a placeholder `${db-password}` does not automatically mean Key Vault names must match `spring.datasource.password` verbatim unless mapped. Watch out for properties with compound hyphens/dots—use explicit placeholders whenever naming gets ambiguous.

**Rotation warning:** HikariCP / `DataSource` retains its connection pool and credentials resolved at startup. Rotating a Key Vault version or refreshing the PropertySource does not guarantee new DB connections immediately pick up the new password. Design restarts, bean reconfiguration, or overlap migrations per Section 15.

### 8.4. Comparing @Value and @ConfigurationProperties

| Mechanism | Pros | Cautions |
|---|---|---|
| `@Value` | Concise, direct placeholders | Scattered fields, singleton beans do not auto-rebind |
| `@ConfigurationProperties` | Type-safe grouped config with validation | Exclude secret fields from `toString()` / serialization |
| Spring auto-config | E.g. `DataSource` consumes loaded properties | Beans build early; secret changes do not auto-refresh them |
| `SecretClient` | Fetches latest/specific versions on demand | Requires manual caching and Key Vault availability handling |

**Never expose a REST controller dumping the Spring Environment** to verify secrets. Validate through business health checks or an internal boolean/status indicator.

### 8.5. Load Only the Secrets You Need

If a vault holds thousands of secrets, never load all of them blindly:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - payment-api-token
                - db-password
~~~

Entries in **secret-keys must match the exact Key Vault secret names** per configuration rules; property-lookup case insensitivity does not mean you can spell the `secret-keys` list sloppily.

Filtering `secret-keys` cuts load volume and clarifies ownership, but **does not alter data-plane IAM permissions**: if the principal holds vault-wide read access, code can still read other secrets via `SecretClient`. Real isolation belongs in Key Vault RBAC.

## 9. Option B: On-Demand Reads via SecretClient

### 9.1. Why Use the SDK Directly?

Use **SecretClient** directly when your application needs to:
- Inspect expiration dates, tags, or version metadata.
- Fetch a specific secret only when executing a given integration.
- Pin a specific version during controlled credential cutovers.
- Implement custom caching or circuit breaking.
- Audit refresh timestamps and active version IDs (never logging the secret value).
- Keep secrets out of Spring Environment and bean properties altogether.

### 9.2. Declaring a SecretClient Bean

~~~java
package com.example.orders;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KeyVaultClientConfiguration {

    @Bean
    public SecretClient secretClient(
            @Value("${AZURE_KEYVAULT_ENDPOINT}") String endpoint) {
        return new SecretClientBuilder()
            .vaultUrl(endpoint)
            .credential(
                new DefaultAzureCredentialBuilder().build()
            )
            .buildClient();
    }
}
~~~

Modern Spring Cloud Azure starters may already auto-configure a **`SecretClient` bean**. When present, inject the auto-configured bean instead of registering a duplicate unless you understand the auto-configuration conditions. Manual declaration is appropriate when using `azure-security-keyvault-secrets` + `azure-identity` directly or customizing builder settings intentionally.

### 9.3. Reading Values Without Logging Them

~~~java
package com.example.orders;

import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import org.springframework.stereotype.Service;

@Service
public class PaymentCredentialProvider {
    private final SecretClient client;

    public PaymentCredentialProvider(SecretClient client) {
        this.client = client;
    }

    // Call only when a refresh is actually needed in a workflow.
    public String loadCurrentToken() {
        KeyVaultSecret secret = client.getSecret("payment-api-token");
        String value = secret.getValue();

        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Invalid payment API token");
        }
        return value;
    }
}
~~~

This simplified snippet shows the API only. **Never call `loadCurrentToken` on every HTTP request** under real traffic—build a proper TTL cache, version policy, and bounded refresh scheduler. Keep tokens out of HTTP responses, logs, `@ToString`, and metric tags.

### 9.4. Secret Versions

~~~java
KeyVaultSecret latest = client.getSecret("payment-api-token");

// When a deployment-managed version ID is known:
// KeyVaultSecret pinned = client.getSecret(
//     "payment-api-token", "<version-id>");
// ...
~~~

Version-pinned reads support controlled cutovers and rollbacks, but never auto-rotate. Unpinned reads fetch the latest enabled version per Key Vault semantics, though app-level caches and bean lifetimes can still hold older values until refreshed.

Although you can inspect `KeyVaultSecret.getProperties().getExpiresOn()`, expiration is vault metadata/validity enforcement—it does not guarantee the downstream partner revokes credentials on schedule, so coordinate lifecycle externally with the token issuer as well.

### 9.5. SecretClient Error Handling

| Scenario | Likely symptom | Response |
|---|---|---|
| Secret missing | `404` / `ResourceNotFoundException` | Verify name/version/env and fail appropriately |
| Identity lacks permission | `403` | Stop retrying indefinitely; check IAM |
| Invalid auth/token | `401` | Inspect Azure Identity / tenant / scope |
| Unreachable | DNS/TLS/timeout | Network diagnostics and bounded retry |
| Rate limited | `429` | Honor `Retry-After`, cache, throttle refreshes |
| Secret disabled/expired | Version unusable | Rotate or re-enable per approval |
| Vault deleted/changed | Wrong endpoint or missing resource | Restore/rollback via IaC |

Never catch `Exception` and return a dummy placeholder like `"NO_TOKEN"` just to keep calling production APIs—that triggers broken side effects and masks outages. Critical secrets require fail-closed behavior or an explicitly approved fallback.

## 10. Local Development: Authenticating Without Stored Credentials

### 10.1. Using the Azure CLI Credential Chain

In an authorized developer environment:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show \
  --query "{name:name,tenant:tenantId,subscription:id}" \
  -o json
~~~

Azure Identity's **DefaultAzureCredential** tries credential sources in library-defined order: environment variables, workload identity, managed identity, and local developer tools (such as Azure CLI). Locally, the SDK picks up your signed-in Azure CLI credential.

Do not interpret that as needing admin privileges for developers. Local identities should read only lab secrets, and you should verify the active tenant and subscription. Being logged into Azure CLI does not guarantee Data-Plane RBAC has been assigned.

### 10.2. Setting the Non-Secret Endpoint

Bash shell:

~~~bash
export AZURE_KEYVAULT_ENDPOINT="https://<vault-name>.vault.azure.net/"
~~~

PowerShell:

~~~powershell
$env:AZURE_KEYVAULT_ENDPOINT = "https://<vault-name>.vault.azure.net/"
~~~

This is a resource URL, not a secret token. You can keep it in a local launch profile or non-secret environment config. Never commit files containing `AZURE_CLIENT_SECRET` or real passwords.

### 10.3. Verifying Secret Loading Without Leaking Values

A **safe smoke check** initializes a bean and verifies a boolean presence condition:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SecretSmokeCheck {
    @Bean
    ApplicationRunner check(
            @Value("${payment-api-token}") String token) {
        return args -> {
            if (token == null || token.isBlank()) {
                throw new IllegalStateException(
                    "Failed to load secret payment-api-token");
            }
            // Log status only; never log length, hash, or secret value.
            System.out.println("Key Vault secret: configured");
        };
    }
}
~~~

This snippet is for lab verification; production should use internal health indicators or automated checks rather than printing to stdout. Never expose a public HTTP endpoint to verify secrets.

### 10.4. Identity Pitfalls

- Developer signed into Azure CLI with a different account than their IDE.
- `DefaultAzureCredential` picking up leftover service principal environment variables on the workstation.
- An identity authorized on the dev vault lacking permissions on the prod vault.
- `az account set` switching CLI subscription context without changing the Entra tenant/audience used by SDK calls.
- Key Vault role assignments taking time to propagate.
- Local proxies/TLS/networking differing from App Service production.

Log the active **principal object ID**, tenant, vault URI, and permission check status—never log access tokens.

## 11. Production Deployment with Managed Identity

### 11.1. Why Managed Identity?

Managed identities provide Azure-managed Entra ID identities so applications acquire tokens without storing client secrets:

- **System-assigned managed identity:** tied to the Azure resource's lifecycle.
- **User-assigned managed identity:** standalone identity resource assignable to multiple workloads per policy.

Secret values still load into application RAM; managed identity solves **authenticating to Key Vault**, not runtime secret hygiene.

### 11.2. App Service + System-Assigned Identity

Flow:

~~~mermaid
sequenceDiagram
    participant A as Spring Boot App Service
    participant M as Managed Identity endpoint
    participant V as Azure Key Vault
    participant D as Downstream service
    A->>M: Request token for Key Vault
    M-->>A: Entra access token
    A->>V: GET secret with token
    V-->>A: Secret value/version
    A->>D: Use credential securely
~~~

Operations enables identity on App Service and assigns `Key Vault Secrets User` at the vault scope once approved. **Read-only** verification command:

~~~bash
az webapp identity show \
  --resource-group "<app-rg>" \
  --name "<app-service-name>" \
  --query "{principalId:principalId,type:type}" \
  -o json
~~~

Enabling identity via Azure commands modifies production infrastructure and must go through IaC/approval. Use **object ID / `principalId`** for RBAC assignments; **`clientId`** is a separate property used when selecting a user-assigned identity.

### 11.3. User-Assigned Managed Identity

When an app has multiple identities or organizational policy assigns a dedicated user-assigned identity, specify which identity reads the vault. For **PropertySource**, keep production credential config in its own deployment profile:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              credential:
                managed-identity-enabled: true
                client-id: ${AZURE_CLIENT_ID}
~~~

**Warning:** this snippet targets environments exposing a managed identity endpoint. Leaving it enabled in a local developer profile breaks local Azure CLI authentication. Split `application-local` and `application-prod`, or enable credential selection only in cloud profiles. With system-assigned MI, you typically do not pass a `client-id`.

### 11.4. AKS and Workload Identity Federation

AKS uses **Microsoft Entra Workload ID**, binding Kubernetes ServiceAccounts via federated identity credentials so Pods acquire tokens without long-lived client secrets.

~~~mermaid
flowchart LR
    P["Spring Boot Pod"] --> SA["Kubernetes ServiceAccount / projected token"]
    SA --> E["Microsoft Entra token exchange"]
    E --> K["Key Vault data plane"]
    K --> P
~~~

Logical steps:

1. Ensure the AKS cluster has OIDC issuer and workload identity enabled.
2. Create a user-assigned managed identity for the workload.
3. Configure a federated credential matching the ServiceAccount subject and audience.
4. Annotate the ServiceAccount, attach it to the Pod, and enable workload identity labels/token projection per AKS guidance.
5. Assign `Key Vault Secrets User` to that identity at the right scope.
6. The Azure Identity SDK uses workload identity credentials / `DefaultAzureCredential` inside the Pod.
7. Verify from inside the live Pod, not just with a developer's `kubeconfig`.

**Never blindly force `managed-identity-enabled=true` for Pods using workload identity federation**, because its token path differs from the IMDS managed identity endpoint. Verify Spring Cloud Azure / `azure-identity` version compatibility, injected tenant/client/token-file environment variables, and credential chain resolution.

### 11.5. Azure Functions, Container Apps, and VMs

Depending on compute host:
- Azure Functions supports managed identity and VNet integration per hosting plan.
- Azure Container Apps has managed identity and platform-level secret references.
- Azure VMs acquire managed identity tokens via the Azure Instance Metadata Service (IMDS).
- AKS favors Workload ID or your organization's approved identity mechanism.

Never assume every host exposes identical identity endpoints or refresh behavior. Always validate token acquisition and Key Vault data-plane reads on the **actual runtime**.

## 12. Secret Naming Rules and Spring Property Mapping

### 12.1. Key Vault Secret Names

Per Key Vault Secrets naming rules, names allow **ASCII letters, digits, and hyphens (`-`) only**. Periods, underscores, spaces, and slashes are forbidden.

| Key Vault secret | Desired Spring property | Resolution strategy |
|---|---|---|
| `payment-api-token` | `app.payment.token` | Placeholder |
| `spring-datasource-password` | `spring.datasource.password` | Spring Cloud Azure hyphen/dot mapping |
| `db-password` | `spring.datasource.password` | Explicit placeholder |
| `orders--api--token` | Complex custom key | Avoid obscure conventions; use tested mappings |
| `billing-v2-token` | `app.billing.token` | Placeholder / typed config |

Never rely on guesswork transformations for production secret names; test mappings explicitly, especially when Spring property names mix hyphens and dots.

### 12.2. Placeholders Are Clearer When Names Differ

Example:

~~~yaml
app:
  partner:
    token: ${payment-api-token}

spring:
  datasource:
    password: ${db-password}
~~~

Give secrets clean physical names in Key Vault and map them to business-meaningful Spring properties. If a secret is renamed in Key Vault later, adjust the mapping via your normal release plan.

### 12.3. Case Sensitivity and `secret-keys`

Spring Cloud Azure PropertySource exposes a **case-sensitive** toggle (commonly `false` by default in docs), whereas the **secret-keys** list requires **exact** matching against Key Vault secret names.

Example:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              case-sensitive: false
              secret-keys:
                - payment-api-token
                - db-password
~~~

Never assume "because `@Value` resolved `Payment-API-Token`, casing in `secret-keys` doesn't matter." Standardize on lowercase kebab-case names and verify against real vault versions.

### 12.4. Spring PropertySource Precedence

When the same key exists in multiple sources, Spring picks the value by PropertySource order. In Spring Cloud Azure Key Vault Secrets configurations documented by Microsoft Learn:

- When `SystemEnvironmentPropertySource` is present, environment variables can take **higher precedence than `KeyVaultPropertySource`**.
- Among multiple Key Vault PropertySources, declaration order sets priority; earlier sources can take precedence over later ones.
- Additional Spring sources such as command-line args and system properties also participate depending on bootstrap and Spring Boot version.

Consequently, a stale environment variable containing an **old secret** can silently shadow a newly rotated secret in Key Vault. Never assume rotation failed before checking for property shadowing.

### 12.5. Inspecting Active Sources Without Printing Secrets

Safe steps:
1. Identify the logical property name.
2. List candidate sources (env, files, vaults, CLI) from deployment config.
3. Check precedence against docs and diagnostic metadata.
4. Validate runtime behavior via an authenticated test call.
5. Never dump the Spring Environment or print secret values "just to check."
6. To verify versions, log the allowed **secret version ID** metadata rather than the value.
7. Do not log raw hashes/fingerprints of secrets if barred by security policy.

## 13. Multiple Key Vaults and Environment Isolation

### 13.1. Two Vaults in One Application

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: app-owned
              endpoint: ${ORDERS_KEYVAULT_ENDPOINT}
              secret-keys:
                - payment-api-token
                - db-password
            - name: shared-owned
              endpoint: ${SHARED_KEYVAULT_ENDPOINT}
              secret-keys:
                - trusted-partner-token
~~~

Each vault has independent policies, regions, networks, and IAM; the app's identity must hold read access to every vault it queries. If two vaults define a secret with the same name, source precedence decides the winner.

### 13.2. Why Separate Dev, Test, and Prod?

| Environment | Principle |
|---|---|
| Dev | Dummy values, developer identities, zero production access |
| Test/Staging | Dedicated test secrets, production-like checks, restricted roles |
| Prod | Dedicated runtime identity, access approvals, auditing, rotation |
| Disaster recovery | Replicated/backed secrets, versions, and network paths per DR plan |

Never point a developer laptop at a production vault to avoid provisioning a dev vault. That widens the attack surface and invites accidental operations against real credentials.

### 13.3. Per-Application Vault vs. Shared Vault

- **Per-application vault:** smaller blast radius, clear ownership, simpler RBAC; more vaults, networks, and monitors to manage.
- **Shared vault:** centralized administration and fewer resources; complex permission boundaries/rotation and larger blast radius.
- **Per-environment vault:** baseline separation keeping dev away from prod.
- **Per-tenant vault:** watch out for thousands of vaults, quotas, operational overhead, and data residency rules.

No single topology fits every company. Decide based on team ownership, principal count, data classification, cost, and disaster recovery needs.

### 13.4. Never Use Naming Prefixes as Your Only Security Boundary

Naming secrets `orders-db-password` and `billing-db-password` in one shared vault will not stop Orders' identity from reading Billing's secrets if both receive vault-wide read access.

When strict isolation is needed:
- Split vaults or apply scoped roles/ABAC where supported by platform and policy.
- Never grant Secrets Officer to runtime apps.
- Enable audit logs and run periodic access reviews.
- Write negative tests verifying cross-app denial.

## 14. Refresh Does Not Equal Bean Reconfiguration

### 14.1. PropertySource Refresh Interval

Per Spring Cloud Azure Secret Management docs reviewed for this lesson, **`KeyVaultPropertySource`** uses a default refresh interval around **30 minutes**; configurable via:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              refresh-interval: 60m
~~~

In releases supporting it, setting **`refresh-interval: 0` disables auto-refresh**. Distinguish clearly between **when the PropertySource polls Key Vault** and **when a business bean or connection pool adopts the new value**.

### 14.2. @Value Inside a Singleton

A Spring singleton:

~~~java
@Service
public class PartnerClient {
    private final String token;

    public PartnerClient(@Value("${payment-api-token}") String token) {
        this.token = token;
    }
}
~~~

captures `token` when the constructor runs. Even if the underlying PropertySource refreshes, `this.token` **does not mutate automatically**. Never treat `refresh-interval: 1m` as a rotation SLA guaranteeing every client uses the new token after sixty seconds.

### 14.3. Is @RefreshScope the Only Answer?

Spring Cloud Context provides `@RefreshScope` and refresh/rebinding mechanisms, but:
- Not every project includes `spring-cloud-context` / Actuator refresh.
- A Key Vault PropertySource refresh does not always emit a Spring Context refresh event in the way you might assume.
- Beans serving active traffic may hold old connections or clients.
- Bean recreation impacts thread safety and graceful cutover.
- `DataSource` / HikariCP and JPA `EntityManager` have complex lifecycles.

Adopt `@RefreshScope` only after testing **end-to-end refresh events, bean recreation, downstream behavior, and exact SDK/Boot version behavior**. When hot rotation is unnecessary, a controlled rolling restart is simpler and safer to test.

### 14.4. SecretClient + Application Cache

With `SecretClient`, you can:
- Cache secrets in RAM with a short, concurrency-safe TTL.
- Refresh on a schedule or controlled event.
- Log the active version ID (never the value).
- Atomically swap references to the active credential.
- Retain the prior credential briefly during overlap windows if upstream permits.
- Handle 429s/timeouts via backoff and bounded fetch concurrency.
- Avoid infinite caching that breaks rotation.

Do not over-engineer dynamic caches if startup-only secrets plus rolling restarts suffice—but equally, never call Key Vault **per HTTP request** under thousands of RPS.

### 14.5. Datasource Passwords and Connection Pools

HikariCP / `DataSource` retains its bound password and open DB connections. When rotating a DB password:
1. The app does not automatically update pool credentials.
2. New pool connections may continue using the old password.
3. Existing connections may keep working temporarily depending on the DB engine and policies.
4. If the DB revokes the old password immediately, new connection attempts fail with auth errors.
5. Handle this via dual-credential overlap, bean restart/reconfiguration, or coordinated rolling deployments per Section 15.

**Adding a secret version in Key Vault does not change the password inside the database or partner API.** Rotation pipelines must update both the **credential issuer** and **all consumers**.

## 15. Rotation: Updating Secrets Without Downtime

### 15.1. Three Distinct State Versions

Every live credential spans three places:
- The version stored in Key Vault.
- The version cached in each Spring Boot instance's RAM.
- The credential actively accepted by the downstream DB or partner API.

If these three fall out of sync, the service breaks even if Key Vault reports "latest secret updated."

### 15.2. API Token Rotation with Overlap

~~~mermaid
flowchart TD
    A["Old token active"] --> B["Issue new token at partner"]
    B --> C["Create new Key Vault secret version"]
    C --> D["Canary instance refresh/restart"]
    D --> E["Verify partner API with new token"]
    E --> F{"Health and metrics pass?"}
    F -->|No| R["Rollback app to known working credential"]
    F -->|Yes| G["Roll out to all instances"]
    G --> H["Verify all instances use new version"]
    H --> I["Revoke old partner token after overlap"]
    I --> J["Audit / remove stale access"]
~~~

Safe steps:

1. Identify the secret owner, expiration, issuer, and rotation window.
2. Issue the new credential at the downstream provider while keeping the old one valid if supported.
3. Write the **new version** to Key Vault without logging the value.
4. Keep the old token active throughout the overlap window.
5. Canary an instance on the new version and validate a business call.
6. Roll out/refresh across the fleet while watching 401/403/429 and p95 metrics.
7. Confirm every instance is using the new version.
8. Revoke the old token downstream once safe.
9. Disable the old Key Vault version per policy after an appropriate rollback window.
10. Record audit evidence without putting secret values in tickets.

### 15.3. When Downstream Does Not Support Two Concurrent Credentials

Plan a coordinated cutover window:
- Synchronize deployment operators clearly.
- Pause or queue traffic if permitted.
- Update the downstream password and Key Vault version nearly simultaneously.
- Restart/reconfigure clients.
- Reconnect and run health verification.
- Keep a rollback plan with an accountable owner.
- Communicate maintenance windows/SLAs if zero downtime is impossible.

A legacy system allowing only one active password per user cannot rotate with zero downtime through Key Vault refresh alone.

### 15.4. Secret Versions and Rollback

Key Vault preserves historical versions per retention policy, yet:
- Older versions can be disabled or expired.
- Downstream systems may have already revoked the old credential.
- Switching back to latest/older versions may not take effect immediately if caches retain another value.
- Rolling back an app to an earlier secret version **fails** if the third party already revoked that token.

Rollback plans must verify **Key Vault version + app state + downstream acceptance**, not merely pick a version ID.

### 15.5. Expiration Alerts and Rotation Ownership

Track and maintain:
- `expiresOn` metadata and a rotation calendar.
- Pre-expiration alerts with enough lead time to rotate safely.
- Primary and backup owners plus change approvals.
- Documentation of credential issuers and all consumers.
- UTC audit logs for rotate, disable, and delete events.
- Periodic dry runs of both rotation and rollback.
- Key Vault Event Grid notifications or automation where supported and beneficial.

**Key Vault does not automatically generate a new database or partner credential** just because a `SecretNearExpiry` event fires. Automation must integrate properly with the issuing system and verify changes end-to-end.

## 16. Private Networking, DNS, and TLS

### 16.1. Connecting to Key Vault via Private Endpoint

For private-only Key Vaults, architecture typically combines an **Azure Private Endpoint**, VNet routing, and Private DNS.

~~~mermaid
flowchart LR
    APP["Spring Boot App Service / AKS Pod"] --> VNET["VNet integration / Pod egress"]
    VNET --> DNS["Private DNS resolver"]
    DNS --> PE["Key Vault Private Endpoint"]
    PE --> KV["Azure Key Vault data plane"]
    APP --> ENTRA["Microsoft Entra / Identity endpoint"]
~~~

**Two network paths** must succeed: acquiring tokens from Entra / managed identity, and connecting over HTTPS to the vault. Token success does not prove vault DNS works; reaching the vault does not prove RBAC authorization succeeds.

### 16.2. FQDNs and DNS Zones

In Azure public cloud:

- Applications keep using the standard URL **`https://<vault-name>.vault.azure.net/`**.
- The Private DNS Zone is typically **`privatelink.vaultcore.azure.net`**.
- DNS resolution from inside the private runtime must return the Private Endpoint's private IP.
- TLS continues validating the standard hostname against the certificate.
- Never replace `vaultUrl` with a raw private IP in Java code.

If the app sits in a separate subnet or VNet, configure DNS forwarding, VNet links, and NSGs/routes properly. Never open public internet access just to mask a broken DNS link.

### 16.3. Checklist from the Real Runtime

1. Does App Service have VNet Integration and outbound routing configured properly?
2. Which DNS resolver and egress route does the AKS Pod actually use?
3. Is the Private DNS Zone linked to the right VNet or forwarded from on-prem?
4. Is the Private Endpoint approved and connected?
5. Do NSGs and Azure Firewall permit HTTPS (443)?
6. Are TLS trust stores and hostname validation intact?
7. Are Microsoft Entra token endpoints / managed identity endpoints reachable?
8. Does the identity hold the right data-plane permission?
9. Do vault firewall/public-network rules align with your route?
10. Do logs capture status codes and request IDs safely for correlation?

### 16.4. Distinguishing Network Errors from Authorization Errors

| Symptom | Layer to inspect |
|---|---|
| DNS resolution fails | Resolver, private DNS zone, forwarding |
| DNS returns a public IP from a private Pod | Misconfigured DNS chain or missing VNet link |
| Connection timeout | Routing, NSGs, firewall, proxy |
| TLS handshake failure | CA trust, hostname mismatch, clock skew |
| `401` | Identity/token/tenant |
| `403` | RBAC / access policy or vault firewall |
| `404` | Wrong vault/secret/version |
| `429` | Key Vault throttling |
| `5xx` | Transient service failure; apply bounded retry |

**Never escalate an app to Key Vault Administrator on a 403** before separating firewall denials from missing RBAC. Never disable TLS certificate validation or open unrestricted public access as a workaround.

## 17. Platform Integrations: App Service References and AKS CSI

### 17.1. App Service Key Vault References

Azure App Service supports **Key Vault references** inside Application Settings: the platform resolves secrets using the app's identity and injects values into the runtime environment.

~~~text
App Setting name:
  PAYMENT_API_TOKEN

App Setting value (structural example):
  @Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/payment-api-token/)
~~~

This differs from Spring Cloud Azure `PropertySource`:

- App Service handles Key Vault communication for the reference.
- Spring receives an already-resolved environment/app property.
- Refresh/caching follows App Service platform policies, not `PropertySource` `refresh-interval`.
- Process environment variables and previously bound beans may not update automatically when the reference refreshes.
- If resolution fails, the application must fail/alert rather than treating the literal string `@Microsoft.KeyVault(...)` as a valid API token.

The App Service identity still requires Key Vault permissions and network paths; never bypass IAM by pasting plaintext secrets directly into App Settings from a repo.

### 17.2. AKS Secrets Store CSI Driver

The Azure Key Vault Provider for Secrets Store CSI Driver can:
- Mount secrets as files inside Pods.
- Sync values into Kubernetes Secrets when configured.
- Authenticate via workload identity or managed identity per setup.
- Poll/rotate mounted secrets per driver/provider settings and version.

Keep in mind:
- Mounted files need OS permissions readable by the container user.
- Spring beans reading a file once at startup will not see subsequent file updates automatically.
- Syncing to Kubernetes Secrets introduces Kubernetes RBAC, encryption-at-rest, and etcd backup security considerations.
- Secrets across multiple namespaces or tenants must never share an overly broad mount.
- Never grant Pods broad permissions across unrelated cluster secrets.

### 17.3. Choosing an Integration Pattern

| Context | Starting option to evaluate |
|---|---|
| Spring needs secrets for startup config binding | Spring Cloud Azure `PropertySource` |
| Need explicit version/metadata control and live refresh | `SecretClient` with custom cache |
| App Service teams standardize on KV references | App Settings Key Vault references |
| AKS platform teams standardize on secret mounts | CSI Driver with Workload ID |
| Database supports Entra passwordless auth | Drop password secrets; use managed identity |

Avoid loading the same secret simultaneously via environment variables, platform references, and Spring `PropertySource` unless precedence and rotation semantics are completely understood and tested.

## 18. Spring Boot Actuator, Logging, and Protecting Secret Values

### 18.1. Common Secret Leak Vectors

- Printing secrets in `CommandLineRunner` or health checks.
- Logging the entire Spring `Environment` or `@ConfigurationProperties`.
- Exceptions containing full connection strings with embedded passwords.
- Publicly exposed Spring Actuator `/env`, `/configprops`, `/heapdump`, or `/logfile`.
- Azure SDK HTTP logging set to `BODY` or `BODY_AND_HEADERS`.
- Metric labels containing tokens, sensitive secret names, or raw URLs.
- `@ToString` / `toString()` on DTOs or records carrying secrets.
- Heap dumps or core dumps saved to overly permissive storage.
- CI/CD pipelines printing environment variables or command-line arguments.
- Web controllers accidentally serializing a bean holding a secret.

### 18.2. Configuring Actuator Carefully

If your project includes **spring-boot-starter-actuator**, an example baseline configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
    health:
      show-details: never
~~~

This reduces accidental exposure through Actuator, but **does not replace authentication, authorization, and network restrictions**. Defaults vary across Spring Boot releases—test the live exposed endpoints directly rather than assuming YAML behavior alone.

### 18.3. What Should Be Logged

Safe to log:
- Key Vault operation category (`READ` / `REFRESH` / `ROTATE`).
- Policy-approved vault identifier.
- Response status/error class and latency.
- Controlled request/correlation IDs.
- Source/version metadata when needed, never the value.
- Application release/instance ID and UTC timestamp.
- Startup/rotation check `PASS`/`FAIL` status.

Never log:
- `KeyVaultSecret.getValue()`.
- `Authorization` headers or access tokens.
- Full JDBC connection strings containing passwords.
- Raw PropertySources dumps.
- SAS signatures or client secrets.
- Secret hashes/fingerprints unless explicitly cleared by security policy.

### 18.4. HTTP Logging, Tracing, and Metrics

The Azure SDK for Java provides `HttpLogOptions` levels (`NONE`, `BASIC`, `HEADERS`, `BODY`, `BODY_AND_HEADERS`). For secret-handling paths, stay at **`NONE`/`BASIC`** and enforce strict header allowlists/redaction per security policy.

Keep metrics low-cardinality (operation, service, status class, environment). Never attach raw URLs, usernames, or secret values as metric dimensions. Protect Application Insights / Log Analytics / trace stores with strict RBAC and retention controls.

### 18.5. Secret Exposure Incident Response

1. Stop ongoing leakage immediately: lock down logs, artifacts, or endpoints.
2. Determine exposure scope across repos, images, CI logs, and Actuator.
3. Rotate/revoke the credential at the **downstream issuer**—merely creating a new Key Vault version may leave the leaked token active.
4. Review vault/identity permissions and narrow scopes if needed.
5. Preserve audit evidence per retention and incident response rules.
6. Deploy new credentials across all affected consumers following your rollout plan.
7. Clean up exposed artifacts properly without violating legal holds.
8. Run security reviews and automated secret scanning.
9. Re-run tests and monitor closely for anomalous usage.

## 19. Resilience, Caching, Quotas, and Cost

### 19.1. Key Vault Is a Critical Dependency

If a `PropertySource` requires a secret to initialize `DataSource` and Key Vault is unreachable, Spring Boot may **fail to start**. If a hot path calls `SecretClient` on every HTTP request, Key Vault 429s or timeouts spike API latency immediately.

Mitigations:
- Startup lookups paired with rolling deployments.
- Controlled `PropertySource` refresh intervals.
- `SecretClient` backed by thread-safe caching and atomic swaps.
- Bounded retries/backoff honoring `Retry-After`.
- Deliberate choice between failing closed or approved conditional fallback.
- Alerts on near-expiration, 401/403, 429, and Key Vault latency.
- Limits on concurrent fleet-wide refreshes.
- Capacity/quota planning by vault tier and region.

### 19.2. Fail Closed vs. Fail Open

**Fail closed:** if a signing secret, payment token, or required DB credential cannot be loaded, halt sensitive operations and raise an error rather than inventing a fallback string.

**Conditional fallback:** if the vault drops briefly while the app holds a valid cached token in RAM, continuing briefly **only when approved by security policy** is reasonable—never keep using a revoked or expired token.

Decision matrix:

| Scenario | Recommended action |
|---|---|
| Payment token has never loaded yet | Fail closed / mark readiness unhealthy |
| Cached token still valid during brief vault outage | Consider retaining cache per policy |
| Credential revoked downstream | Never use stale cache |
| Non-sensitive feature flag | Fall back per business policy |
| Payment request signing system | Never substitute a default signing secret |
| App needs DB password at boot | Bounded startup retry / fail with alerts |

Never write `catch (Exception e) { return "default-token"; }` for sensitive credentials.

### 19.3. Spring Cloud Azure Retries and Timeouts

You can configure retries specifically on a Key Vault PropertySource:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              retry:
                mode: exponential
                exponential:
                  max-retries: 3
                  base-delay: PT0.2S
                  max-delay: PT5S
~~~

These parameters are examples only. Spring Cloud Azure provides retry, timeout, and proxy properties at both global and per-service/per-source levels. Tune values to your API SLO and network topology instead of copying identical settings everywhere.

Distinguish clearly between:
- Connect timeout.
- Response/read timeout.
- Retry attempts and backoff delays.
- Startup timeout.
- Overall business operation deadline.
- Outer retries (Spring Retry, queue triggers, API gateways).

Never stack multiple uncoordinated retry layers without bounding total attempts and end-to-end latency.

### 19.4. Why Not Call Key Vault on Every Request?

Suppose Orders API serves 1,000 requests/second and reads 2 secrets per request:

~~~text
1,000 API requests/s × 2 Key Vault GETs
    = 2,000 Key Vault GETs/s
~~~

This is an **illustrative traffic scenario**, not an official quota or pricing limit. Multiplied across replicas or full-vault refreshes, transaction costs and throttling escalate rapidly.

Better design:
1. Fetch only required secrets.
2. Cache securely in RAM aligned with freshness and security rules.
3. Refresh off the hot path via controlled schedules or events.
4. Never cache indefinitely when timely rotation matters.
5. Track latest version vs. actively used credential.
6. Rate-limit and cap concurrent refreshes.
7. Monitor cache hits/misses, 429s, latency, and rotation success.

### 19.5. Startup Storms

Scaling out 100 Pods at once where each Pod lists/gets 500 secrets generates a massive burst against the vault.

Mitigate startup storms by:
- Specifying only required **`secret-keys`**.
- Partitioning vaults and permissions per workload.
- Rolling deployments with controlled surge/scale rates.
- Using exponential backoff with jitter.
- Defining crisp startup/readiness behavior.
- Staggering overlapping background refresh timers.
- Monitoring request rates, 429s, and availability.

Never grant Secrets Officer to work around 429 throttling—permissions do not raise service rate limits.

### 19.6. Total Cost Picture

~~~text
Total secret-management cost =
    Azure Key Vault operations/transactions per pricing
  + Identity / networking / Private Endpoints where applicable
  + Azure App Service / AKS / Functions compute
  + Azure Monitor / Log Analytics ingestion + retention
  + Rotation automation, CI/CD, approvals, auditing
  + Retry, polling, and startup-storm overhead
  + Incident and recovery operations
~~~

Do not count secret names alone—**GET/list counts, replica counts, refresh frequency, and cache misses** drive operation volume. Pricing and quotas vary by SKU, region, and date; use the Azure Pricing Calculator, Cost Management, and live Key Vault metrics to estimate.

## 20. Repeatable Testing Without Production Secrets

### 20.1. Unit Tests Without a Real Vault

In `application-test.yml`, disable the Key Vault `PropertySource` and supply dummy values for beans:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: false

payment-api-token: fake-token-for-test-only
~~~

Explicitly set the active test profile so `application-prod.yml` is never loaded by accident. Dummy values exist solely to test binding—never allow tests to call production payment APIs.

### 20.2. Mocking SecretClient

~~~java
import static org.mockito.Mockito.when;
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class PaymentCredentialProviderTest {
    @Test
    void readsFakeTokenWithoutAzureNetwork() {
        SecretClient client = Mockito.mock(SecretClient.class);

        when(client.getSecret("payment-api-token"))
            .thenReturn(new KeyVaultSecret(
                "payment-api-token", "fake-test-only"));

        PaymentCredentialProvider provider =
            new PaymentCredentialProvider(client);

        assertEquals("fake-test-only", provider.loadCurrentToken());
    }
}
~~~

This example assumes compatible JUnit 5 and Mockito dependencies. Unit tests never touch real Key Vault, TLS, Entra, or RBAC—pair them with staging integration tests.

### 20.3. Integration Test Matrix

| Test | Expected condition |
|---|---|
| Correct vault, correct identity | App reads dummy secret; zero value logging |
| Wrong role | 403 classified cleanly; no infinite retry |
| Wrong secret name | 404 handled cleanly; never falls back to prod defaults |
| Disabled/expired secret | Startup/read path responds per policy |
| Wrong tenant | Token/auth failure metadata recorded |
| Misconfigured Private DNS | Network-layer timeout caught clearly |
| `429` throttling | Bounded retry/cache prevents storms |
| Duplicate names across two vaults | Precedence matches config order |
| Environment variable override | Shadowing detected via test assertions |
| Rotation to new value | App/beans/DB pool transition cleanly per rollout |
| Rollback | Only reverts to old version if downstream still accepts it |
| Multi-instance startup | Stays within throughput/quota limits |
| Actuator/logs | Zero secret values exposed |
| CSI / App Service references | Platform refresh mechanics verified |
| Revoked identity | Access denied cleanly and alerted |

### 20.4. Negative Security Tests

- Orders runtime identity cannot read Billing's vault.
- Unauthenticated HTTP clients cannot read `/env`, `/configprops`, or `/heapdump`.
- App never prints `TokenCredential` or access tokens to logs.
- Dummy environment variables never unintentionally shadow production config.
- CI pipelines print zero values during rotation.
- TLS hostname verification is never disabled.
- DNS failure never triggers falling back to public Key Vault endpoints.
- Missing secrets never fall back to hard-coded defaults.
- Old credentials are revoked downstream after the overlap window per policy.

### 20.5. Evidence to Retain

- BOM, Spring Boot, and JDK versions alongside deployment commit SHA.
- Vault URI, permission model, and principal object ID.
- Role assignment scope and policy approval.
- Test PASS/FAIL results, status/error classes, and UTC timestamps.
- Secret names/version IDs where permitted by policy—**never secret values**.
- Latency/quota/retry metrics and log-redaction test results.
- Rotation timestamps, readiness checks, rollback state, and incident owners.

## 21. Key Vault Incident Runbooks for Spring Boot

### 21.1. Symptom Lookup Table

| Symptom | Common cause | Diagnosis / action |
|---|---|---|
| Startup fails with unresolved placeholder | Secret not loaded, typo, missing starter | Inspect `PropertySource` config and `secret-keys` |
| `401` on `getSecret` | Wrong tenant, audience, or credential | Inspect `DefaultAzureCredential` chain |
| `403` on `getSecret` | Missing Secrets User or access policy | Check data-plane permission model |
| `403` despite correct role | Key Vault firewall / Private Link | Inspect diagnostics and network rules |
| `404` secret not found | Wrong vault/name/version or deleted | Check metadata, spelling, and lifecycle |
| Cannot read disabled secret | Secret version is disabled | Verify enabled state and rotation runbook |
| Secret expired | `ExpiresOn` mismatch with renewal | Issue fresh credential |
| DNS returns public IP | Private DNS misconfigured | Check zone link and forwarders |
| Connection timeout | VNet, NSG, firewall, or proxy | Test from the actual runtime host |
| `429` | Excessive refresh/retries/replicas | Add caching, `secret-keys`, backoff, rate limits |
| Bean still uses old token | Singleton `@Value`/datasource bound at boot | Controlled rolling restart or tested bean refresh |
| Works locally, fails in prod | Dev credential differs from managed identity | Inspect runtime principal |
| Prod reads dev vault | Misconfigured endpoint/env | Add env allowlists and release gates |
| Env var beats Key Vault | `PropertySource` precedence | Inspect variable shadowing |
| Secret rotated yet DB fails | Downstream password mismatch | Coordinate cutover/overlap plan |
| Secrets appear in logs | Custom logging or Actuator | Block output, revoke/rotate, audit |
| CSI file updated yet app stays stale | App never reloaded file/client | Implement file watcher or restart |
| App Service reference stays stale | Platform cache / ref lag | Verify config refresh and restart |
| Errors after Boot/SDK upgrade | BOM/classpath mismatch | Re-verify compatibility matrix and dependencies |

### 21.2. Runbook: 403 at Spring Boot Startup

1. Record resource name, UTC timestamp, Java exception type, and HTTP status—never log secret values.
2. Verify the vault endpoint in environment/profile config.
3. Identify the **actual runtime Azure Identity principal**, not the assumed one.
4. Confirm tenant, subscription, and Key Vault permission model.
5. If RBAC-enabled, verify **Key Vault Secrets User** at the target vault/secret scope.
6. If access-policy-enabled, inspect data-plane access policies instead of RBAC roles.
7. Confirm role propagation completed and the secret is enabled.
8. If permissions look valid, inspect Key Vault network/firewall diagnostic logs.
9. Test fetching a dummy secret/metadata in staging under the same runtime identity.
10. Only adjust permissions with evidence and approval—never assign Administrator as a "quick test."

### 21.3. Runbook: Secret Rotated Yet Application Ignores It

1. Verify secret name, latest version ID, and rotation timestamp.
2. Confirm the downstream provider issued and activated the new credential.
3. Check `PropertySource` `refresh-interval` and `secret-keys` list.
4. Check whether an environment variable or App Setting is shadowing the property.
5. Check whether the Spring bean bound `@Value` at construction or queries `SecretClient`.
6. Inspect cache TTLs and actual refresh timestamps.
7. For HikariCP/`DataSource`, verify which credentials the pool actually uses.
8. Canary-restart a single instance to test loading the new value.
9. Monitor 401s, connection errors, and business health metrics.
10. Roll forward or roll back per plan, revoking the old credential only when safe.

### 21.4. Runbook: Private-Only Key Vault Unreachable

1. Identify the compute host (App Service, AKS, VM, Functions).
2. Run DNS lookup for the vault's standard FQDN from inside the runtime.
3. Inspect Private DNS Zone **`privatelink.vaultcore.azure.net`**.
4. Verify VNet links/forwarders and Private Endpoint connection state.
5. Check NSGs, Azure Firewall, proxies, and route tables.
6. Verify TLS trust chain and exact hostname.
7. Verify reachability of the managed identity token endpoint and Entra ID.
8. Inspect Key Vault diagnostic logs to distinguish network blocks from 403 RBAC denials.
9. Never open unrestricted public network access.
10. Remediate network config through IaC and change approval, then verify every replica.

### 21.5. Runbook: 429s and Rising Service Latency

1. Graph Key Vault GET/list operation counts over time.
2. Inspect replica count, refresh intervals, and `secret-keys` scope.
3. Verify the app is not fetching secrets per HTTP request.
4. Inspect stacked retry layers, `Retry-After` handling, and total timeouts.
5. Cap concurrent refreshes/startups and add jitter/backoff.
6. Enable caching aligned with security freshness bounds.
7. Narrow loaded secrets and partition vaults by workload if appropriate.
8. Review tier quotas, regional health, and alerts.
9. Rehearse load behavior in staging before scaling back out.
10. Track p95/p99, 429 rate, startup success, and costs.

### 21.6. Runbook: Accidental Secret or Vault Deletion

1. Halt further delete/cleanup jobs immediately and freeze the change window if needed.
2. Verify soft-delete state, retention window, and purge protection.
3. Never purge a resource "to clean up," as that can make recovery impossible.
4. Execute the approved recovery workflow to restore the vault/secret within the retention window.
5. Verify secret version, enabled status, and expiration metadata.
6. Confirm downstream credentials remain valid.
7. Canary an application instance against the restored vault/secret.
8. Reconcile any rotations or revocations that occurred during the outage.
9. Write a postmortem and tighten IaC guardrails and delete permissions.
10. Keep secret values completely out of incident tickets and recovery logs.

## 22. Case Study: Spring Boot Orders API on Azure

### 22.1. Requirements

An order management platform includes:
- Spring Boot Orders API on Azure App Service.
- Azure SQL Database storing orders (initially one legacy integration uses a password).
- Payment partner requiring an API token.
- Blob Storage holding invoice PDFs.
- App Configuration managing non-secret feature flags.
- Key Vault protecting secret tokens and passwords.
- Application Insights monitoring latency and 401/403/429 errors.
- Enterprise-mandated VNet / Private Endpoint isolation.
- Roadmap to migrate the database to Entra passwordless auth where supported.

### 22.2. Reference Architecture

~~~mermaid
flowchart LR
    U["Client / API Gateway"] --> APP["Spring Boot Orders API"]
    APP --> ID["Managed Identity / Entra"]
    APP --> KV["Azure Key Vault Secrets"]
    APP --> DB["Azure SQL Database"]
    APP --> BLOB["Azure Blob Storage"]
    APP --> CFG["Azure App Configuration"]
    APP --> PAY["Payment partner"]
    APP --> MON["Azure Monitor / App Insights"]
    KV -. "Audit + alerts" .-> MON
~~~

Not every resource must share one VNet or identical public access rules. Private Endpoints, DNS, and identities are tailored per service and deployment—this diagram shows the logical topology.

### 22.3. Separating Secrets from Configuration

| Parameter | Stored in | Consumed by |
|---|---|---|
| `AZURE_KEYVAULT_ENDPOINT` | App Setting (non-secret) | Spring Cloud Azure config |
| `PAYMENT_API_TOKEN` | Key Vault secret | Payment integration |
| `LEGACY_DB_PASSWORD` | Key Vault secret | Temporary JDBC `DataSource` |
| `FEATURE_CHECKOUT_V2` | App Configuration | Feature flag |
| Storage endpoint | App config (non-secret) | Blob SDK |
| Azure access tokens | Acquired dynamically by Azure Identity | SDK data-plane calls |
| Key Vault permissions | Azure RBAC / access policy | Runtime identity |

Note: never create a Key Vault secret for an Azure Storage account key if Blob Data RBAC with managed identity works. Likewise, eliminate legacy DB passwords once the database and JDBC driver support Entra authentication.

### 22.4. Deployment Workflow

1. IaC/Platform team provisions App Service, managed identity, and Key Vault.
2. Security team assigns minimal secret-read roles.
3. Network team validates Key Vault Private Endpoint and DNS from App Service.
4. Release pipeline deploys Spring Boot with **non-secret** endpoints.
5. Spring `PropertySource` loads `payment-api-token` and `db-password` at startup.
6. App readiness verifies beans and downstream connectivity per policy.
7. Smoke tests validate payment sandbox and DB without logging secret values.
8. Monitoring tracks secret read latency, 429s, startup errors, and downstream auth failures.
9. Canary/rolling deployment promotes to production.
10. Rollback and rotation policies remain documented and rehearsed.

### 22.5. Scenario 1: Rotating Payment Token with Overlap

- Partner issues the new token while keeping the old token active temporarily.
- Rotation pipeline writes a new secret version in Key Vault.
- Canary App Service instance restarts or refreshes cleanly.
- Low-risk/sandbox payment verification passes.
- Remaining instances roll out sequentially while watching 401s and latency.
- Fleet confirms every instance switched to the new version.
- Partner revokes the old token after the overlap window.
- Audit records approval and completion with zero logged tokens.

### 22.6. Scenario 2: Rotating DB Password Without Overlap

When the database accepts only one active password per user:
- Schedule a coordinated cutover/maintenance window.
- Decouple DB credential rotation from routine app rollbacks.
- Drain traffic and queue workers per business SLA.
- Update the DB password and Key Vault secret version together during the change window.
- Restart or reconfigure HikariCP/`DataSource` cleanly.
- Verify new JDBC connections and transactions.
- Monitor connection errors with rollback steps ready.
- Long term, migrate to Entra passwordless auth to eliminate shared passwords.

### 22.7. Acceptance Criteria

1. Zero real secrets in repos, Docker images, or config artifacts.
2. Runtime identity can read only Orders' Key Vault.
3. Developers have no default read access to the production vault.
4. Local tests run with dummy secrets and lab Azure CLI identities.
5. Spring `PropertySource` resolves the intended secret names accurately.
6. `SecretClient` is never invoked per HTTP request unnecessarily.
7. `@Value` beans and `DataSource` follow verified rotation/restart behavior.
8. Private-only networking succeeds from the real runtime host.
9. 401/403/404/429 responses are categorized properly with runbooks.
10. Zero secret values appear in Actuator, logs, or traces.
11. Rollouts and rollbacks never reference revoked credentials.
12. Cost budgets, quota alerts, and audit evidence are active.

## 23. Design Pitfalls to Avoid

| Mistake | Consequence | Better practice |
|---|---|---|
| Putting passwords in `application.yml` | Exposed in Git and build artifacts | Key Vault or passwordless auth |
| Committing `.env` with real credentials | Secrets persist in Git history | Secret scanning and rotation |
| Logging `getSecret().getValue()` for debug | Secrets exposed in log stores | Log status and version metadata only |
| Assigning Key Vault Administrator to apps | Excessive blast radius | Scope to Secrets User |
| Mixing RBAC and access policies | Confusing 403 failures | Verify active permission model |
| Pointing local laptops at the prod vault | Cross-environment risk | Separate vaults and identities |
| Omitting `secret-keys`, loading entire vault | Higher call counts and exposure | Explicitly filter `secret-keys` |
| Assuming refresh updates every `@Value` bean | Stale token remains in RAM | Rebind or restart per test results |
| Rotating vault without changing upstream password | Credential mismatch outage | Sync issuer and consumers |
| Revoking old token before fleet switches | Outage | Use overlap, canary, and verification |
| Calling Key Vault per API request | 429s, latency spikes, high cost | Cache and refresh off the hot path |
| Exposing Spring Environment over REST | Secret leak | Secure Actuator and ban dumps |
| Disabling TLS to work around DNS issues | MITM vulnerability | Fix Private DNS and TLS properly |
| Granting Owner immediately on 403 | Over-privileged access | Diagnose data-plane RBAC vs. firewall |
| Opening public network on private-only vaults | Security policy violation | Fix VNet and Private DNS |
| Mixing App Service refs and `PropertySource` arbitrarily | Confusing shadowing/refresh | Standardize on one primary source |
| Treating `SecretClient` caches as eternal | Broken rotation | Enforce bounded TTL cache policies |
| Assuming `expiresOn` rotates DB passwords | Auth outages | Build real rotation automation |
| Putting dots in Key Vault secret names | Invalid secret names | Use kebab-case and placeholders |
| Neglecting soft-delete/purge-protection planning | Unrecoverable accidental deletes | Enable purge protection and approvals |
| Enabling HTTP body logging | Secrets leaked in wire logs | Keep `NONE`/`BASIC` with redaction |

## 24. Production Checklist

### 24.1. Data Classification and Secret Lifecycle

- [ ] Classified real secrets, non-secret config, keys, and certificates.
- [ ] Evaluated **passwordless / Entra authentication** to replace stored secrets where possible.
- [ ] Every secret has an owner, purpose, consumer inventory, expiration, and rotation schedule.
- [ ] Key Vault secret names stick to letters, digits, and hyphens.
- [ ] Documented workflow covers new versions, canarying, overlap, revocation, and rollback.
- [ ] Production secrets never appear in test fixtures, READMEs, or CI logs.
- [ ] Tags/metadata omit secret values and unnecessary PII.
- [ ] Soft delete, purge protection, and retention match recovery/compliance rules.
- [ ] Pre-expiration alerts and assigned owners are configured.

### 24.2. Spring Boot Integration

- [ ] Spring Cloud Azure BOM matches Spring Boot and JDK versions cleanly.
- [ ] Deliberate choice made among `PropertySource`, `SecretClient`, and platform references.
- [ ] Vault endpoints originate from validated non-secret configuration.
- [ ] `secret-keys` lists only required secret names.
- [ ] Multi-source property precedence tested explicitly.
- [ ] Environment variables cannot unintentionally shadow vault secrets.
- [ ] Zero hard-coded credentials in YAML, Docker images, or source code.
- [ ] `@Value`, `@ConfigurationProperties`, and auto-config beans bind cleanly at startup.
- [ ] Verified in tests that **refresh does not auto-rebind beans**.
- [ ] HikariCP/`DataSource` rotation rehearsed practically, not just in theory.
- [ ] `SecretClient` instances are reused with clear caching/refresh policies.
- [ ] Outage fallback rules approved by the security team.

### 24.3. Identity and Least Privilege

- [ ] Dev, staging, and prod maintain separate identities and vaults per policy.
- [ ] Runtimes use managed identity or workload identity wherever supported.
- [ ] Principal object ID, client ID, and tenant ID clearly distinguished.
- [ ] Vault permission model (RBAC vs. access policy) verified.
- [ ] Runtimes hold only **Key Vault Secrets User** or minimal required access.
- [ ] Rotation/deployment identities kept separate from runtime identities.
- [ ] Service principal client secrets avoided in favor of federation/managed identity.
- [ ] Role assignments have owners, approvals, and periodic reviews.
- [ ] Negative tests verify App A cannot read App B's secrets.

### 24.4. Networking and Security

- [ ] Vault URIs use standard hostnames with TLS certificate validation enabled.
- [ ] VNet, Private Endpoints, and DNS tested from the real runtime environment.
- [ ] Private DNS Zone `privatelink.vaultcore.azure.net` and resolvers configured cleanly.
- [ ] Both token/managed-identity endpoints and Key Vault data plane are reachable.
- [ ] Key Vault public access/firewall matches security policy.
- [ ] Actuator does not expose `/env`, `/configprops`, or `/heapdump` publicly.
- [ ] Production HTTP logs never run at `BODY` or `BODY_AND_HEADERS` on secret paths.
- [ ] Logs, traces, metrics, and exceptions contain zero secret values.
- [ ] Secret scanning runs across Git, CI, and container artifacts.
- [ ] Audit logs, access logs, diagnostic settings, and retention match compliance.

### 24.5. Resilience, Cost, and Operations

- [ ] Workload-appropriate retry, backoff, and timeout budgets configured.
- [ ] 401/403/404/429/5xx responses classified accurately.
- [ ] Infinite retries never masked behind missing roles or network blocks.
- [ ] Key Vault refreshes never execute on every HTTP request unnecessarily.
- [ ] Multi-instance deployments avoid startup storms.
- [ ] Metrics track GET/list counts, latency, 429s, startup health, and rotation state.
- [ ] Alerts watch expirations, disabled secrets, and config mismatches.
- [ ] Staging rehearsals cover rotation, rollback, and vault outages.
- [ ] Budgets and Cost Management cover vault ops, Private Link, logging, and automation.
- [ ] Runbooks and on-call owners exist for principal, network, rotation, and deletion incidents.
- [ ] IaC deploying roles and networking leaks zero secrets into unprotected state/logs.
- [ ] Migration roadmap exists to replace legacy passwords with Entra auth.

## 25. Self-Check Questions

1. **What is a secret?** A sensitive value requiring protection, such as a password, API token, or signing key.
2. **Why keep secrets out of `application.yml`?** They leak easily through source control, JARs, Docker images, and build artifacts.
3. **What are the three main object types in Key Vault?** Secrets, Keys, and Certificates.
4. **What does a secret version do?** Tracks revisions under one secret name for controlled rollouts and valid rollbacks.
5. **Does `expiresOn` generate a new credential automatically?** No.
6. **Does Key Vault replace API-level authorization in the app?** No.
7. **What does `PropertySource` do?** Exposes Key Vault secrets as Spring Environment properties.
8. **What does `SecretClient` do?** Lets Java code read secret values, versions, and metadata on demand.
9. **When should you use `PropertySource`?** When secrets are needed at startup for beans or auto-configuration.
10. **When should you use `SecretClient`?** When you need on-demand reads, version pinning, or custom caching.
11. **How do App Service Key Vault references differ from `PropertySource`?** The platform resolves the reference rather than Spring Cloud Azure loading it.
12. **What does the CSI Driver typically do?** Mounts secrets as files inside Pods or syncs them to Kubernetes Secrets.
13. **What problem does managed identity solve?** Acquires Entra tokens without storing long-lived client secrets.
14. **How do local developers typically authenticate?** Via Azure CLI or developer credential chains in Azure Identity.
15. **Which identity should App Service production use?** A least-privilege managed identity.
16. **What underpins AKS workload identity?** ServiceAccounts, OIDC, and federated identity credentials.
17. **Can Azure Contributor automatically read secret values?** Not on a vault using data-plane RBAC.
18. **Does Key Vault Reader read secret values?** No, metadata only per permissions.
19. **Which RBAC role is standard for reading secrets?** Key Vault Secrets User.
20. **Should a read-only app receive Secrets Officer?** No, that privilege is excessive.
21. **Are Azure RBAC and vault access policies the same?** No; verify the vault's active permission model.
22. **Can secret names contain dots?** No; stick to letters, digits, and hyphens.
23. **What secret name maps to `spring.datasource.password`?** Either `spring-datasource-password` or an explicit placeholder mapping.
24. **Does `secret-keys` limit how much of the vault is loaded?** Yes, though it does not replace IAM scoping.
25. **Should `secret-keys` use arbitrary casing?** No; names must match the actual vault entries.
26. **Can an environment variable override Key Vault `PropertySource`?** Yes, per documented precedence rules.
27. **How are duplicate keys across two Key Vault PropertySources resolved?** By declaration order and configuration precedence.
28. **What is the default `PropertySource` refresh interval in current docs?** Around 30 minutes.
29. **What does `refresh-interval: 0` typically do?** Disables auto-refresh where supported by the SDK version.
30. **Does refreshing `PropertySource` automatically update `@Value` fields in singletons?** Not automatically.
31. **Does refresh automatically recreate HikariCP with a new password?** Never assume so.
32. **Does rotating a secret in Key Vault change the database password?** No.
33. **Why use an overlap window when rotating API tokens?** So all consumers migrate before revoking the old token.
34. **What if a downstream system cannot hold two concurrent passwords?** Schedule a coordinated cutover/maintenance window or use another migration approach.
35. **Does rolling back to an old Key Vault version always work?** Not if the downstream service already revoked the old credential.
36. **Why avoid fetching Key Vault on every HTTP request?** Causes latency, 429 throttling, and unnecessary transaction costs.
37. **What is one risk of a startup storm?** Hundreds of replicas simultaneously calling get/list and getting throttled.
38. **Which endpoint should Java use for a private-only vault?** The standard `vault.azure.net` FQDN, never a raw private IP.
39. **What is the Private DNS Zone for Key Vault in Azure public cloud?** `privatelink.vaultcore.azure.net`.
40. **Should you disable TLS to bypass Private DNS issues?** No—that creates security risk and misdiagnoses the issue.
41. **How does 401 differ from 403?** 401 indicates authentication failure; 403 indicates authorization or network denial.
42. **What does 404 on `getSecret` mean?** Missing name/version or lifecycle mismatch.
43. **How should an app handle 429 on `getSecret`?** Cache, apply backoff, rate-limit refreshes, and honor retry policies.
44. **Where can Actuator leak secrets?** `/env`, `/configprops`, heap dumps, or custom endpoints.
45. **Should you ever log `KeyVaultSecret.getValue()`?** Never.
46. **Why scan Git history for secrets?** Removing a line in HEAD leaves the secret visible in past commits.
47. **Do unit tests need a production vault?** No; use dummy values and mocks.
48. **What should integration tests verify?** Identity, RBAC, networking, rotation, precedence, logs, and failure modes.
49. **What do soft delete and purge protection provide?** Recovery from and defense against accidental deletion within retention rules.
50. **What defines a solid production secret architecture?** Least-privilege identity, right-sized vaults, lifecycle/rotation, private networking/TLS, caching, safe logging, monitoring, tests, and runbooks.

## 26. References

Review the official documentation aligned with your project's Spring Boot, Spring Cloud Azure, and Azure Key Vault versions:

- [Spring Cloud Azure secret management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management) — PropertySource, secret-keys, refresh intervals, and precedence.
- [Spring Cloud Azure developer guide](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview) — BOM, starters, supported versions, and integration.
- [Load a secret from Key Vault in a Spring Boot application](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-starter-java-app-with-azure-key-vault) — PropertySource and SecretClient.
- [Azure Key Vault Secrets configuration properties](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration-properties-azure-key-vault-secrets) — endpoints, credentials, retries, refresh, and logging.
- [Spring Cloud Azure configuration reference](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration) — global and per-service settings.
- [Azure Identity library for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/authentication/overview) — DefaultAzureCredential and managed identity.
- [Azure Key Vault Secrets Java SDK](https://learn.microsoft.com/en-us/java/api/overview/azure/security-keyvault-secrets-readme) — SecretClient and SecretClientBuilder.
- [Azure Key Vault overview](https://learn.microsoft.com/en-us/azure/key-vault/general/overview) — vaults, keys, secrets, and certificates.
- [Azure Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide) — Key Vault Secrets User/Officer/Administrator.
- [Azure Key Vault security](https://learn.microsoft.com/en-us/azure/key-vault/general/security-features) — encryption, networking, and permissions.
- [Azure Key Vault Private Link](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service) — private endpoints, DNS, and connectivity.
- [Key Vault private link diagnostics](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-diagnostics) — troubleshooting DNS and Private Endpoints.
- [Azure Key Vault soft-delete and purge protection](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview) — deletion recovery.
- [Key Vault event notifications](https://learn.microsoft.com/en-us/azure/key-vault/general/event-grid-overview) — near-expiry and new-version events.
- [Key Vault references for App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references) — platform secret injection.
- [AKS Azure Key Vault Secrets Store CSI Driver](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver) — Pod mounts and rotation.
- [AKS Microsoft Entra Workload ID](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview) — federated workload identity.
- [Azure Key Vault monitoring](https://learn.microsoft.com/en-us/azure/key-vault/general/monitor-key-vault) — metrics, diagnostic settings, and auditing.
- [Azure Key Vault pricing](https://azure.microsoft.com/en-us/pricing/details/key-vault/) — service pricing and transaction charges.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — budgets, attribution, and cost tracking.

**Conclusion:** managing Spring Boot secrets with Azure Key Vault is an end-to-end **identity, configuration, networking, operational, and lifecycle design**, never just replacing a password with a GET call. Spring Cloud Azure **`PropertySource`** loads secrets early to bind into the Spring Environment; **`SecretClient`** fits on-demand lookups needing versions or metadata; **App Service references and AKS CSI** offer platform-level alternatives. A secure system pairs managed identity or workload identity with least-privilege **Key Vault Secrets User** permissions, isolates vaults across environments, blocks leaks through logs and Actuator, recognizes that refresh does not auto-rebind beans, rotates credentials using canary and overlap windows, enforces private networking and TLS, bounds retries and caches, tracks expiration and 429/403 telemetry, tests failure scenarios, and maintains clear recovery runbooks. Wherever possible, eliminate static passwords altogether using **Entra passwordless authentication** instead of managing more long-lived secrets.
