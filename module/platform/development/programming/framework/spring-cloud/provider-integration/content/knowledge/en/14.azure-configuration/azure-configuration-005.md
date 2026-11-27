# Integrating Key Vault Secrets and Mapping Secrets to Properties

A Spring Boot application may need to connect to payment gateways, databases, and partner APIs using passwords or API tokens. Placing these values directly in `application.yml` risks leaking secrets into Git, build artifacts, logs, or configuration copies. **Azure Key Vault Secrets** stores sensitive values in a managed service, supporting identity-based read authorization and secret versioning.

**Spring Cloud Azure Key Vault Secrets** can expose secrets as a `PropertySource` in the Spring `Environment`. This allows `@Value`, `@ConfigurationProperties`, and auto-configurations such as `spring.datasource.password` to receive data at application startup without storing secret values in source code.

This lesson belongs to the **Azure Configuration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, including identities and permissions, storage, messaging, data, secrets, integration testing, and evaluating differences across cloud providers. The focus here is **integrating Key Vault Secrets, mapping secret names to Spring properties, and protecting the secret usage lifecycle**.

## 1. What Should You Be Able to Do Afterward?

You will know how to:

1. Choose **Key Vault Secrets PropertySource** for configuration needed at startup; distinguish it from Azure SDK `SecretClient` and Key Vault references in App Configuration.
2. Configure the vault endpoint, `secret-keys` list, and an identity with least-privilege read access.
3. Understand why secret names use `-` while Spring properties use `.`, and how to use placeholder aliases.
4. Bind secrets into beans or built-in Spring Boot properties without printing sensitive values.
5. Handle multiple vaults, precedence order, refresh, rotation, testing, and authentication errors.

Running scenario: `checkout-service` needs `payments-api-token` to call a payment provider and `database-password` to connect to a dev database. No secret is ever committed to the repository.

## 2. Secrets Belong in Key Vault, Regular Parameters in App Configuration

| Data | Appropriate Management Store | How Read in Spring |
| --- | --- | --- |
| Payment tokens, DB passwords, webhook signing secrets | **Key Vault Secrets** | Key Vault PropertySource or `SecretClient` |
| Cryptographic keys for signing/decryption in HSM | **Key Vault Keys** | Keys/Cryptography API, not the Secrets starter |
| Certificates managed inside the vault | **Key Vault Certificates** | Certificates API and appropriate certificate mechanisms |
| Timeouts, retries, non-sensitive endpoints | **Azure App Configuration** | App Configuration config provider |
| Feature flags | **Azure App Configuration Feature Manager** | Feature management library |
| URI pointing to a secret | **App Configuration Key Vault reference** | Provider receives the reference and queries Key Vault itself |

A secret is a **sensitive data value**, not synonymous with a **key** or **certificate** object. The `spring-cloud-azure-starter-keyvault-secrets` starter serves Secret operations and `PropertySource`; it does not automatically provide full Key Vault key signing workflows or TLS certificate configuration.

### 2.1. Three paths to retrieve secrets

| Mechanism | When Read | Best Suited When |
| --- | --- | --- |
| **KeyVaultPropertySource** | At startup and on each configured refresh | Secret must be bound as a Spring property to instantiate beans |
| **SecretClient** | When application code calls the API | Need on-demand reads by name/version or per-error handling |
| **App Configuration Key Vault reference** | When the App Configuration provider loads and dereferences | Want to manage application keys in App Configuration while keeping sensitive values in the vault |

This lesson uses **KeyVaultPropertySource directly**. If you only use the Secrets starter, you **do not need** `spring.config.import=azureAppConfiguration`: that import is for Azure App Configuration integration.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Source as KeyVaultPropertySource
    participant Entra as Microsoft Entra ID
    participant Vault as Azure Key Vault
    participant Bean as Spring Binder/Bean
    App->>Source: Read endpoint and secret-keys config
    Source->>Entra: Acquire token for application identity
    Entra-->>Source: Access token
    Source->>Vault: Get secret
    Vault-->>Source: Secret value if authorized
    Source-->>App: Add PropertySource to Environment
    App->>Bean: Resolve placeholders and bind properties
    Note over Bean: Do not log secret
~~~

## 3. Creating a Vault and Naming Secrets

Assume the development environment's Azure Key Vault is named `demo-checkout-kv` with endpoint:

~~~text
https://demo-checkout-kv.vault.azure.net/
~~~

Create two **secrets with dummy values** in Azure portal → Key Vault → Secrets:

| Secret Name | Purpose | Practice Recommendation |
| --- | --- | --- |
| `payments-api-token` | Payment gateway auth token | Use a test string with no real system privileges |
| `database-password` | Dev DB password | Use a password dedicated only to a test database |

Never put production values into documentation, shell commands stored in history, issues, or logs for illustration.

**Distinguish three things:**

~~~text
Secret name:       payments-api-token
Secret URI:        https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token
Versioned URI:     https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token/<version>
Secret value:      Value returned only to an identity with read permission
~~~

A secret record can have **multiple versions**. The secret name stays stable while the current value can change when a new version is published. When configuring `KeyVaultPropertySource`, you provide the **vault endpoint** and secret names; there is no need to put every full URI into `application.yml`.

### 3.1. Secret naming rules

Azure Key Vault secret names accept **Latin letters, digits, and hyphens `-`**. Dots `.`, underscores `_`, spaces, or `/` are not valid characters in a secret name. For example:

~~~text
Valid:       payments-api-token
Valid:       spring-datasource-password
Do not use:  spring.datasource.password
Do not use:  payments_api_token
~~~

In Spring, hierarchical property names like `spring.datasource.password` or `checkout.gateway.api-token` are common. This difference creates the need for mapping or placeholders, covered in section 6.

## 4. Identity, Permissions, and Vault Protection

Before connecting, identify whether the vault uses **Azure RBAC** or **Vault access policy** (the legacy model). With Microsoft Entra ID, the identity reading secrets and the identity creating/updating secrets should receive separate permissions.

| Model | Permission for a Read-Only Application |
| --- | --- |
| **Azure RBAC** | Assign the **Key Vault Secrets User** role at the appropriate vault scope |
| **Vault access policy** | Allow `Get`; also consider `List` when the application needs to enumerate secrets |
| **Azure resource management role** | `Key Vault Contributor` does not implicitly grant permission to read **secret values** |

Roles such as `Key Vault Secrets Officer` and `Key Vault Administrator` are broader than a read-only workload needs; avoid assigning them just to fix a 403 error. Following Key Vault RBAC recommendations, consider **separate vaults per application and environment** when separation of duties is required.

### 4.1. Local vs. cloud execution

| Where Running | Appropriate Identity |
| --- | --- |
| Developer machine | Appropriate Azure CLI/IDE/Developer CLI credential and authorized principal |
| Azure App Service or VM | **Managed Identity** enabled on the exact workload |
| Container using workload identity federation | Principal linked to the workload via federation |
| CI pipeline | Dedicated test principal, limited scope, no production permissions |

`az login` only signs in to the Azure CLI; Spring code must still resolve an appropriate credential. The account shown in the portal, the account in the CLI, and the Managed Identity principal running in production can be **different**. If you see a 403, inspect the identity actually used by the Azure SDK along with the role scope and the vault's authorization model.

Managed Identity eliminates the need to store a **client secret to sign in to Azure**. It does not replace every third-party secret: a payment gateway token may still need to be stored in Key Vault if the partner does not support direct identity authentication.

## 5. Adding the Spring Cloud Azure Dependency

The example uses **Spring Boot 3.5.x** and **Spring Cloud Azure 6.5.0**. According to Microsoft documentation, Spring Boot 4.0.x uses Spring Cloud Azure 7.x (for example 7.4.0). Check the compatibility matrix when using other versions.

In `pom.xml` of a Maven project that already has a Spring Boot parent or dependency management, add:

~~~xml
<properties>
    <java.version>17</java.version>
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The BOM (`spring-cloud-azure-dependencies`) keeps the libraries on the same compatible release line. There is no need to specify a separate version for the starter once the BOM is imported.

## 6. Configuring Key Vault PropertySource and Name Mapping

### 6.1. Loading only the two needed secrets

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
                - database-password
~~~

Set the environment variable containing only the endpoint:

~~~text
AZURE_KEYVAULT_ENDPOINT=https://demo-checkout-kv.vault.azure.net/
~~~

In PowerShell:

~~~powershell
$Env:AZURE_KEYVAULT_ENDPOINT = "https://demo-checkout-kv.vault.azure.net/"
~~~

Or Linux/macOS shell:

~~~bash
export AZURE_KEYVAULT_ENDPOINT="https://demo-checkout-kv.vault.azure.net/"
~~~

| Property | Meaning |
| --- | --- |
| `property-source-enabled` | Enables Key Vault PropertySource; default `true` |
| `property-sources[].name` | Source name to distinguish it when inspecting `Environment` |
| `property-sources[].endpoint` | Endpoint of the **vault**, not the URI of a single secret |
| `property-sources[].secret-keys` | Specifies names of secrets to fetch from the vault |
| `property-sources[].case-sensitive` | Enables case-sensitive property lookup; default `false` |
| `property-sources[].refresh-interval` | Refresh interval; default `30m` |

If `secret-keys` is omitted, the provider may load **all secrets**. When a vault holds hundreds of secrets, explicitly list the needed names to reduce access cost, `List` requirements, and the surface area loaded into `Environment`.

### 6.2. Secret name and property name mechanics

Consider secret name `spring-datasource-password`. According to Spring Cloud Azure documentation, the provider supports accessing it via:

- `spring-datasource-password` — direct secret name;
- `spring.datasource.password` — converted hierarchical form.

However, **do not** assume `spring.datasource-password` is also equivalent. Not every combination of replacing `-` and `.` is treated identically by Spring Cloud Azure.

| Name in Vault | Desired Spring Name | How to Implement |
| --- | --- | --- |
| `spring-datasource-password` | `spring.datasource.password` | Mapping supported by the provider |
| `payments-api-token` | `payments-api-token` | Read by direct secret name |
| `payments-api-token` | `checkout.gateway.api-token` | Create an explicit **placeholder alias** |
| `database-password` | `spring.datasource.password` | Create an explicit **placeholder alias** |

For properties with complex structure, an explicit alias is easy to test and relies less on guessing conversion rules.

### 6.3. Aliasing with placeholders

Add outside the `spring` root in `application.yml`:

~~~yaml
checkout:
  gateway:
    api-token: "${payments-api-token}"
~~~

At this point:

~~~text
Azure Key Vault secret       KeyVaultPropertySource       Spring property
payments-api-token       -> payments-api-token       -> checkout.gateway.api-token
                                      resolved via placeholder
~~~

This is **not a copy of the secret** stored on Azure; it is a Spring expression to look up the already-loaded value. Omit default fallbacks on mandatory secrets. For example, `${payments-api-token:demo}` could let a production application run with a dummy credential and hide an authentication failure.

### 6.4. Complete application.yml example

~~~yaml
spring:
  application:
    name: checkout-service
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token

checkout:
  gateway:
    api-token: "${payments-api-token}"
~~~

When adding a DataSource, simply add `database-password` to `secret-keys` and place `spring.datasource.password: "${database-password}"` under the **existing `spring` root**. Avoid writing two duplicate `spring:` roots in the same YAML document.

### 6.5. Using a secret to configure a DataSource

A standalone snippet for an application that has added a JDBC/JPA starter and database settings:

~~~yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${database-password}"
~~~

This is a **snippet to merge into the `spring` root** of the complete configuration file in section 6.4. At startup, KeyVaultPropertySource has already placed `database-password` into `Environment`; Spring Boot can resolve the placeholder to build the DataSource.

If the database supports **passwordless authentication with Microsoft Entra ID/Managed Identity**, consider that approach to eliminate storing a password altogether. When a password is still required, rotation must coordinate changing the database side and refreshing the connection pool.

### 6.6. User-assigned Managed Identity case

If the Azure environment has multiple identities and needs to select a specific user-assigned identity:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
              credential:
                managed-identity-enabled: true
                client-id: "${AZURE_CLIENT_ID}"
~~~

`AZURE_CLIENT_ID` is the Managed Identity's ID, **not a client secret**. The configuration above is an **alternative** to the endpoint/credential section of the previous example when deploying a user-assigned identity; you must enable/attach the identity to the workload and grant the Key Vault Secrets User role to that exact principal.

## 7. Binding Secrets into Spring Boot

### 7.1. Using `@ConfigurationProperties`

Create `CheckoutApplication.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Create `GatewayCredentials.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout.gateway")
public record GatewayCredentials(String apiToken) {
    public GatewayCredentials {
        if (apiToken == null || apiToken.isBlank()) {
            throw new IllegalArgumentException(
                    "Required checkout.gateway.api-token is missing");
        }
    }

    @Override
    public String toString() {
        // Default record toString() includes fields; do not expose the token.
        return "GatewayCredentials[REDACTED]";
    }
}
~~~

Create `GatewayReadinessCheck.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GatewayReadinessCheck {
    @Bean
    ApplicationRunner verifyGatewayCredential(GatewayCredentials credentials) {
        return args -> {
            if (credentials.apiToken().isBlank()) {
                throw new IllegalStateException("Gateway credential unavailable");
            }
            // Do not log the credentials.apiToken() value.
        };
    }
}
~~~

Result: the `payments-api-token` secret resolves to `checkout.gateway.api-token` and binds into `GatewayCredentials.apiToken()`. Business logic consumes the token via the configuration object without needing to know Key Vault URIs.

**Note on Java records:** the default `toString()` method usually prints all fields. For secrets, override it as shown above or use a regular class that does not auto-generate a data-exposing `toString()`. Storing a token in a `String` still keeps it present in application memory; limit the scope of objects with access to it.

### 7.2. Using `@Value`

A bean can retrieve a single property:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayTokenProvider {
    private final String token;

    public GatewayTokenProvider(
            @Value("${checkout.gateway.api-token}") String token) {
        this.token = token;
    }

    public boolean isConfigured() {
        return token != null && !token.isBlank();
    }
}
~~~

`@Value` is concise for one property but causes key strings to repeat across classes. `@ConfigurationProperties` is better when multiple parameters are used together. Never create a REST endpoint that returns a token just for test verification.

### 7.3. Choosing where to verify secrets

A safe verification method is **starting up successfully and executing a test transaction** using a sandbox partner account. You may log whether a credential is configured as a boolean, but never log the token, password, or an object containing the secret. If a test hits a failure branch, the exception should state only the **missing property name**, without appending any value.

## 8. Multiple Vaults and Precedence Order

Suppose an application needs a dedicated payments vault and a shared vault:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: payments-vault
              endpoint: "${PAYMENTS_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
            - name: shared-vault
              endpoint: "${SHARED_KEYVAULT_ENDPOINT}"
              secret-keys:
                - shared-webhook-key
~~~

According to Microsoft documentation on Spring Cloud Azure secret management:

- If **the same secret** is loaded into multiple Key Vault PropertySources, the source declared **earlier** has higher priority than one declared later.
- `SystemEnvironmentPropertySource` (environment variables) has higher priority than Key Vault PropertySource; therefore an environment variable can override a value from the vault.
- Other sources in Spring `Environment` have their own precedence rules, so still verify actual ordering when property names collide.

This order **differs** from certain App Configuration multi-store merging rules. Do not blindly carry App Configuration precedence assumptions over to Key Vault.

**Recommendation:** avoid placing secrets with the same name in multiple vaults unless intentional. When sharing is necessary, design namespaces and explicitly test which source wins, especially between `dev`/`prod`.

## 9. When to Use `SecretClient` Instead of PropertySource?

PropertySource suits properties needed at startup. If you need to read a secret **on demand** or a **specific version**, the Azure SDK `SecretClient` is the direct choice.

Illustrative example of a service checking existence without printing values:

~~~java
package com.example.checkout;

import com.azure.security.keyvault.secrets.SecretClient;
import org.springframework.stereotype.Service;

@Service
public class VaultSecretProbe {
    private final SecretClient secretClient;

    public VaultSecretProbe(SecretClient secretClient) {
        this.secretClient = secretClient;
    }

    public boolean hasGatewayToken() {
        String token = secretClient.getSecret("payments-api-token").getValue();
        return token != null && !token.isBlank();
    }
}
~~~

To inject a Spring Cloud Azure auto-configured `SecretClient`, configure the SDK client endpoint, for example:

~~~properties
spring.cloud.azure.keyvault.secret.endpoint=${AZURE_KEYVAULT_ENDPOINT}
~~~

This differs from `property-sources[0]`'s endpoint. When there are **multiple vaults**, do not assume a single `SecretClient` bean will automatically pick the right vault by secret name; configure separate clients or construct clients with explicit endpoints/credentials.

Comparison table of read timing:

| Mechanism | When Value Appears | What to Keep in Mind |
| --- | --- | --- |
| `KeyVaultPropertySource` | In Spring `Environment` | Has a refresh interval, but beans may retain old values |
| `SecretClient.getSecret` | Returned when calling the API | Must actively handle latency, retries, errors, and caching |
| App Configuration Key Vault reference | Dereferenced property | Requires read permissions on both App Configuration and Key Vault |

## 10. Refresh, Rotation, and Secret Versioning

### 10.1. Default 30-minute refresh

According to Spring Cloud Azure documentation, `KeyVaultPropertySource` refreshes by default **every 30 minutes**. You can configure:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
              refresh-interval: 60m
~~~

`refresh-interval: 60m` changes the interval to 60 minutes; set `0` to **disable automatic refresh**. This interval does not mean every bean receives the new secret the moment Key Vault gets a new version.

For example, an HTTP client constructed at startup with `String token` and stored in a field can continue using the old token even after PropertySource refreshes. Similarly, a DataSource or connection pool is not automatically recreated solely because `spring.datasource.password` changed.

### 10.2. Rotation requires coordinating the consumer side

A safe procedure to rotate `payments-api-token`:

1. Generate a new credential at the payment provider and confirm both old and new tokens are accepted during the transition window.
2. Create a **new secret version** in Key Vault via a protected workflow.
3. Let instances pick up the new value according to the refresh/restart plan; recreate any HTTP clients caching the credential if necessary.
4. Monitor 401/403 errors and sandbox transactions; confirm every instance uses a valid credential.
5. Revoke the old token after cutover, verifying no remaining requests use the old credential.

With `SecretClient` reading a fixed version or a Key Vault reference with a version-pinned URI, you must **update the referenced version** to receive the new value. Never treat “created a new secret version” as proof that rotation is complete.

### 10.3. Limits and retries

An application with many instances starting simultaneously can generate a burst of requests to Key Vault. If `secret-keys` is unconstrained or refresh is too frequent, you may encounter 429/throttling errors. Use retries with backoff and monitoring, but **do not** turn retries into an unbounded loop inside every business HTTP request.

## 11. Security Once a Secret Enters Environment

Key Vault protects data at rest and enforces read access at the service. But once Spring resolves a secret into a `String`, the value is present in application memory.

| Risk | Mitigation |
| --- | --- |
| Printing the whole `Environment`, config objects, records, or exceptions | Log only key names and status; redacted `toString()` on secret-holding objects |
| Exposing values via Spring Actuator | Restrict or disable `/env`, `/configprops`; protect access and verify masking |
| Storing secrets in Git or image/container layers | Commit only endpoints, secret names, and placeholders; never commit values |
| Picking the wrong identity on deploy | Verify Managed Identity principal, tenant, and RBAC |
| Dev/prod vaults sharing permissions | Separate vaults or roles per workload and environment |
| Polling Key Vault continuously | Use reasonable refresh/caching, measure quotas and latency |
| Network errors to the vault | Check firewall, private endpoint, DNS, proxy, and routing |
| Leaking tokens in HTTP query strings | Pass credentials via authentication mechanisms supported by the partner SDK |

For payment functionality, pass the token only to the **client that must use it**. Avoid putting secrets into API DTOs, logs, metric labels, trace tags, or error messages sent to users.

## 12. Testing Without Depending on Real Azure

### 12.1. Spring tests verifying binding only

When testing `GatewayCredentials`, you do not need a vault connection. Disable Key Vault PropertySource and provide dummy values via test properties:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.keyvault.secret.property-source-enabled=false",
    "checkout.gateway.api-token=test-placeholder"
})
class GatewayCredentialsTest {
    @Autowired
    GatewayCredentials credentials;

    @Test
    void bindsSecretAliasWithoutAzure() {
        assertThat(credentials.apiToken()).isEqualTo("test-placeholder");
        assertThat(credentials.toString()).doesNotContain("test-placeholder");
    }
}
~~~

This test proves **binding properties into Java** and object redaction. It does not prove Azure tokens or Key Vault permissions work. If `application.yml` also configures App Configuration independently, disable that provider separately in tests as well.

### 12.2. Integration tests against a dev vault

Use a test vault separated from production and a read-only identity:

1. Create a dummy secret `payments-api-token` in the dev vault.
2. Run the app with the dev endpoint; confirm the bean receives the credential and the sandbox client authenticates successfully.
3. Configure `secret-keys` to include only needed secrets and verify other properties are not loaded.
4. Test a principal without read permission, confirming the failure is logged as an error code/type and **contains no secret**.
5. Create a new test secret version; verify behavior before/after refresh or restart.
6. If using two vaults, verify precedence order with a dummy secret of the same name.
7. Simulate network or quota errors in the test environment and observe the impact on startup time.

Never run rotation tests against a production vault.

### 12.3. Inspecting sources without printing values

When tracking down a missing property, you can temporarily add a diagnostic in the dev environment:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class SecretSourceDiagnostic {
    @Bean
    ApplicationRunner reportSource(ConfigurableEnvironment environment) {
        return args -> {
            String key = "payments-api-token";
            System.out.println("Configured: " + environment.containsProperty(key));
            for (PropertySource<?> source : environment.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("PropertySource: " + source.getName());
                }
            }
        };
    }
}
~~~

This snippet prints only **true/false** and **source names**, not `environment.getProperty(key)`. Remove the diagnostic after use and avoid probing unnecessary secrets.

## 13. Troubleshooting

| Symptom | Cause to Check | Suggested Resolution |
| --- | --- | --- |
| 401 at Key Vault | Credential chain, token, wrong tenant | Verify which identity the SDK is actually using |
| 403 despite Azure login | Missing data-plane role, wrong scope, or vault uses different access policy model | Assign `Key Vault Secrets User` to the right principal or grant appropriate `Get` permission |
| Error when provider lists secrets | Missing `List` in access policy model or vault has too many secrets | Use `secret-keys` and appropriate permissions |
| Secret does not exist | Wrong name, wrong vault, disabled/expired, invalid version | Verify metadata; do not print value |
| `@Value` reports missing property | Wrong alias, secret not loaded, or property name mismatch | Check endpoint, `secret-keys`, and placeholder name |
| Cannot create secret name with `.` | Key Vault naming rules | Switch to `-`; create a Spring alias when needed |
| Secret exists but `spring.datasource-password` fails | Not a guaranteed mapping | Use `spring.datasource.password` or an explicit placeholder |
| Secret changed but bean keeps old token | Not refreshed yet, or bean/client caches value | Check `refresh-interval` and client lifecycle |
| Works locally, fails when deployed to Azure | Managed Identity differs from local principal; firewall/private endpoint differs | Check principal, RBAC, DNS/VNet |
| Two vaults with same key return unexpected source | Order of `property-sources` | The first declared source takes precedence per documentation |
| Tests accidentally access Azure | PropertySource not disabled | Set `property-source-enabled=false` and supply dummy properties |

## 14. Comprehensive Exercise

The `shipping-service` has operational timeout `shipping.timeout=PT4S` and a carrier token that must stay secret.

Requirements:

1. Store the token in Key Vault under the name `shipping-provider-token`.
2. In Spring, beans should read it via property `shipping.provider.token`.
3. The application may only read secrets; it must not create/delete secrets.
4. When the token is rotated, the client must actually use the new value.
5. Binding tests run locally without calling Azure; integration tests use a dev vault.

A configuration that solves the exercise:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: shipping-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - shipping-provider-token

shipping:
  timeout: PT4S
  provider:
    token: "${shipping-provider-token}"
~~~

Bind into Java:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping.provider")
public record ProviderCredentials(String token) {
    @Override
    public String toString() {
        return "ProviderCredentials[REDACTED]";
    }
}
~~~

Remember to enable `@ConfigurationPropertiesScan` on the application. After configuring, explain:

- Why should the real token not be placed in `application.yml`?
- Why can the secret name and Spring property name differ?
- If read permission is missing, does the failure happen in the Azure layer or the Spring Binder layer?
- Once PropertySource finishes refreshing, why might an already-created client still hold the old token?
- If a secret exists in two vaults, which source selection rule applies?
- When can passwords be replaced entirely by Managed Identity?

**Guided answers:** Key Vault protects secrets and enforces permissions, aliases map properties, permission errors occur when querying Key Vault, refreshing the source does not automatically recreate clients, the first KeyVaultPropertySource in the list takes precedence, and Managed Identity fits when the target service supports that authentication method.

## 15. Official References

- [Microsoft Learn – Spring Cloud Azure secret management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management): PropertySource configuration, `secret-keys`, secret names, precedence, and refresh.
- [Microsoft Learn – Load a secret from Azure Key Vault in Spring Boot](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-starter-java-app-with-azure-key-vault): two ways to read via `SecretClient` and PropertySource.
- [Microsoft Learn – Spring Cloud Azure configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): credential, retry, and client configuration at global/service levels.
- [Microsoft Learn – Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): read/write authorization, roles, and scopes.
- [Microsoft Learn – Assign a Key Vault access policy](https://learn.microsoft.com/en-us/azure/key-vault/general/assign-access-policy): legacy access policy model and permission scopes.
- [Microsoft Learn – Key Vault Secrets PropertySource sample](https://learn.microsoft.com/en-us/samples/azure-samples/azure-spring-boot-samples/loading-secrets-from-azure-key-vault-to-property-source-in-spring-boot-application/): loading one or multiple vaults and selecting secrets.
- [Spring Boot – Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `Environment`, placeholders, and precedence sources.

**Core takeaway:** integrating Key Vault Secrets must solve **three distinct problems**: an identity authorized to read the vault, mapping secret names to Spring properties, and a plan to update beans/clients consuming the secret when its value changes. Completing all three ensures the system uses secrets properly without accidentally leaking information.
