# Distinguishing Between Azure App Configuration and Azure Key Vault

In a Spring Boot application running on Azure, configuration typically consists of two groups of information: **parameters that control application behavior** and **data that must be kept secret**. Azure provides two complementary services: **Azure App Configuration** manages application configuration, while **Azure Key Vault** protects secrets, cryptographic keys, and certificates.

This lesson belongs to the **Azure Configuration** chapter of the `SPRING_CLOUD_PROVIDER_INTEGRATION` module. The goal is to know how to choose the right service, integrate with Spring Cloud Azure using appropriate identities and permissions, understand the Key Vault reference flow, and test and operate configuration safely.

## 1. Distinguishing with Questions About the Data

Start with two questions:

1. **Is the value a secret?** If exposing the value could allow unauthorized access (passwords, API tokens, private credentials), store it in **Key Vault**.
2. **Is the value used to adjust application behavior?** If it is a timeout, retry threshold, public endpoint address, feature choice, or a value that differs across environments, store it in **App Configuration**.

Example of an ordering system:

| Data | Suitable Storage | Why |
| --- | --- | --- |
| `orders.timeout=PT3S` | App Configuration | Operational parameter, adjustable per environment |
| `orders.max-retries=4` | App Configuration | Retry logic configuration, not a secret |
| Enable/disable new payment feature | App Configuration | Has feature flags and release management mechanisms |
| `payments.api-key` | Key Vault | Partner access key that needs restricted readers |
| Database access password | Key Vault | Authentication secret, requires permission granting and rotation workflows |
| Key used for signing/encryption, TLS certificate | Key Vault | Cryptographic object with its own API and management lifecycle |
| URI referencing `payments.api-key` | App Configuration | Can hold a **reference** for the application to retrieve the secret from Key Vault |

**Key rule:** App Configuration encrypts data at rest and in transit, but that does not turn it into a dedicated secret management store. When combining both services, App Configuration holds a **pointer to the secret**, while the secret value remains in Key Vault.

## 2. Comparison Table by Responsibility

| Criterion | Azure App Configuration | Azure Key Vault |
| --- | --- | --- |
| Purpose | Centralize application configuration management, feature flags | Manage secrets, cryptographic keys, certificates |
| Primary data unit | Key-value, label, metadata, feature flag | Versioned secret, versioned key, certificate |
| Examples | Timeout, service URL, rollout flag | Password, API token, signing key, certificate |
| Environment separation | Labels, key prefixes, app/profile-specific configuration | Can separate vaults per environment/application and grant permissions |
| Bulk reading | Select/filter multiple key-values by key and label | Secrets are typically retrieved individually by name/version |
| Runtime configuration changes | Spring library has configurable check and refresh mechanisms | Changing a secret does not automatically update all objects holding the old value |
| Typical read access control | `App Configuration Data Reader` | `Key Vault Secrets User` for secrets (Azure RBAC) |
| Secret lifecycle | Does not replace secret, key, or certificate management | Versioning, expiration, rotation, cryptographic operations depending on object type |
| Spring integration | App Configuration config provider, feature management | Key Vault Secrets property source, Azure SDK for keys/certificates |
| Relationship with the other service | Stores **Key Vault reference** | Provides secret value when the application is authorized |

**Distinguishing three object types in Key Vault:** a secret is sensitive data readable as data; a key is a cryptographic key object serving operations like signing or decryption depending on permissions and key type; a certificate serves certificate management. The `spring-cloud-azure-starter-keyvault-secrets` starter handles **secrets** as a Spring property source; it does not implicitly replace the Key Vault Keys or Certificates APIs.

## 3. Characteristic Concepts

### 3.1. App Configuration: key, label, and feature flag

App Configuration stores key-value pairs. A key can have multiple values distinguished by **label**:

| Key | Label | Value |
| --- | --- | --- |
| `/application/orders.timeout` | `dev` | `PT10S` |
| `/application/orders.timeout` | `prod` | `PT3S` |
| `/application/orders.max-retries` | `prod` | `4` |

The Spring provider has a convention of reading keys under the `/application/` prefix and mapping them to Spring properties such as `orders.timeout`. By default, if no separate label filter is configured, the provider uses the active Spring profile as the label; if there is no active profile, it uses values without a label. Check the key/label selection rules for the library version being used.

A **feature flag** is a specialized data type for controlling feature visibility, different from creating a regular boolean property yourself. The feature management mechanism can evaluate conditions, filters, and rollout strategies; merely storing a `checkout.enabled=true` key does not provide full feature management behavior.

### 3.2. Key Vault: secret, identity, version

For example, Key Vault has a secret named `payments-api-key`. Key Vault provides a URI such as:

~~~text
https://demo-payments-kv.vault.azure.net/secrets/payments-api-key
~~~

This URI is **not** the secret. The secret value is only returned to an identity with read permission, over a valid connection and network policy. When a new version exists, a URI with a specific version points to a fixed version; a URI without a version allows retrieving the current version according to service and library behavior, though the application still needs to reload/update its cache properly.

## 4. Combining Both Services with Key Vault Reference

A practical configuration:

- In **Key Vault**, manage the `payments-api-key` secret with the real value.
- In **App Configuration**, create the `/application/payments.api-key` key of type **Key Vault reference**, pointing to the secret's URI.
- Spring Boot loads configuration via the App Configuration provider. When encountering a reference, the **application-side library** queries Key Vault and puts the resolved value into the Spring `Environment`.

~~~mermaid
sequenceDiagram
    participant Spring as Spring Boot + Spring Cloud Azure
    participant Config as Azure App Configuration
    participant Vault as Azure Key Vault
    Spring->>Config: Read /application/payments.api-key
    Config-->>Spring: Key Vault reference (URI, not secret)
    Spring->>Vault: Read secret using URI and application identity
    Vault-->>Spring: Secret value (if authorized)
    Note over Spring: Put value into Spring Environment
~~~

Common point of confusion: **App Configuration does not forward the secret value for the application**. The application's client provider itself receives the reference and then connects to Key Vault. The identity running the application must be permitted to read **both App Configuration and Key Vault**; granting only `App Configuration Data Reader` is not enough.

A Key Vault reference is also not the same as the `@Microsoft.KeyVault(...)` syntax used for *App Service application settings*. That is Azure App Service's own resolution mechanism; in this lesson we use **App Configuration Key Vault reference** supported by the Spring provider.

## 5. Integration in Spring Boot with Spring Cloud Azure

### 5.1. Prerequisites and dependencies

Assume the project uses Spring Boot, Java 17+, and Maven configuration. Choose the **Spring Cloud Azure BOM compatible with the Spring Boot version**. For example, according to the support matrix: Spring Boot 3.5.x pairs with Spring Cloud Azure 6.x (or a supported 5.x version), while Spring Boot 4.0.x pairs with Spring Cloud Azure 7.x. Do not mix incompatible major lines.

In `pom.xml`, declare the corresponding BOM and dependencies:

~~~xml
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
  <!-- App Configuration provider; the web variant supports automatic refresh checks -->
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-appconfiguration-config-web</artifactId>
  </dependency>

  <!-- Only needed when reading Key Vault secrets as Spring properties -->
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
  </dependency>
</dependencies>
~~~

Set the `spring-cloud-azure.version` property in the POM to a **verified compatible** version; for example `6.2.0` with Spring Boot 3.5.x or `7.2.0` with Spring Boot 4.0.x. The App Configuration dependency **does not need the Key Vault Secrets starter to resolve Key Vault references**; the App Configuration provider has its own mechanism. We add the Key Vault starter to illustrate the case where the application **reads a secret directly** from Key Vault.

If you do not have Spring Web or do not need automatic refresh checks driven by web events, you can choose the `spring-cloud-azure-appconfiguration-config` library instead of the `-web` variant.

### 5.2. Creating data for both access patterns

On the Azure portal:

1. Create an App Configuration store and a Key Vault, for example `demo-orders-config` and `demo-payments-kv`.
2. In App Configuration, create `/application/orders.timeout` = `PT3S`, `/application/orders.max-retries` = `4` with label `prod`.
3. In Key Vault, create secrets `payments-api-key` and `jdbc-password` using your environment's secret management workflow; do not copy real values into source code, documentation, shell history, or logs.
4. In App Configuration, create a **Key Vault reference**: key `/application/payments.api-key`, label `prod`, secret URI `https://demo-payments-kv.vault.azure.net/secrets/payments-api-key`.
5. Use the `jdbc-password` secret to illustrate the **direct** read path via the Key Vault Secrets property source.

Equivalently, the Azure CLI command to create the reference looks like:

~~~bash
az appconfig kv set-keyvault \
  --name demo-orders-config \
  --key /application/payments.api-key \
  --label prod \
  --secret-identifier "https://demo-payments-kv.vault.azure.net/secrets/payments-api-key"
~~~

The key's value in App Configuration is now a **reference**, not a copy of the API key.

### 5.3. Identity and authorization

On a development machine, you can sign in to Azure CLI with `az login` (and select the appropriate subscription). When deploying, enable **Managed Identity** for the Spring Boot runtime environment, such as App Service or a workload that supports identity. The Spring Cloud Azure library supports Azure credential methods, including identity-based configurations and credential chains; check the credential selection behavior for the exact version used.

For an application runtime identity that only needs to read:

| Resource | Minimum permission with Azure RBAC | Purpose |
| --- | --- | --- |
| App Configuration store | `App Configuration Data Reader` | Read key-values, labels, references |
| Key Vault | `Key Vault Secrets User` | Read referenced secret values and directly read secrets |

If the vault uses **Vault access policy** instead of Azure RBAC, you must grant the `Get` permission for secrets; if the property source is configured to list all secrets, check whether the `List` permission is also needed. Avoid assigning `Owner` or `Contributor` just to fix a 403 error. Signing in to Azure successfully does not mean having permission to read data from both services.

Note that the identity running in the cloud and the developer's identity on a local machine can be **different**. Verify RBAC on the exact principal, exact subscription/resource, and wait for permissions to propagate if they were just assigned.

### 5.4. Connecting both configuration sources

Example `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: ${AZURE_APPCONFIG_ENDPOINT}
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - jdbc-password
~~~

Environment variables hold **endpoints**, not secrets:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-orders-config.azconfig.io
AZURE_KEYVAULT_ENDPOINT=https://demo-payments-kv.vault.azure.net/
SPRING_PROFILES_ACTIVE=prod
~~~

- `spring.config.import=azureAppConfiguration` is the import syntax of the modern App Configuration library; do not replace it with `azure-appconfiguration:` if the documentation for your version requires the exact string `azureAppConfiguration`.
- The provider loads applicable keys/labels for the configuration; the active profile `prod` corresponds to label `prod` in the example.
- `keyvault.secret.property-sources` provides a **direct access path** to `jdbc-password`. The `secret-keys` list limits which secret names to load, rather than reading the entire vault. This starter is not required for `payments.api-key` if it is already loaded via an App Configuration reference.
- Do not put `connection-string` values containing credentials, passwords, client secrets, or access keys into files committed to Git.

If you want to force a label instead of relying on the active profile, you can configure explicit label selection:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/*
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=prod
~~~

For multi-environment production configurations, consider keeping shared values without a label and layering environment-specific values using appropriate labels, avoiding precedence confusion across multiple Spring `PropertySource` entries.

### 5.5. Reading values in Spring code

Both types of configuration, once successfully loaded, are accessed through Spring `Environment`, `@Value`, or `@ConfigurationProperties`. Business logic should not know about Key Vault URIs or SDK calls.

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrderSettings(Duration timeout, int maxRetries) {}
~~~

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PaymentGatewaySettings {
    private final String apiKey;
    private final String jdbcPassword;
    private final OrderSettings orders;

    public PaymentGatewaySettings(
            @Value("${payments.api-key}") String apiKey,
            @Value("${jdbc-password}") String jdbcPassword,
            OrderSettings orders) {
        this.apiKey = apiKey;             // App Configuration -> Key Vault reference
        this.jdbcPassword = jdbcPassword; // Direct Key Vault property source
        this.orders = orders;             // App Configuration key-value
    }

    public boolean isConfigured() {
        return apiKey != null && !apiKey.isBlank()
                && jdbcPassword != null && !jdbcPassword.isBlank()
                && orders.timeout().isPositive();
    }
}
~~~

In a real application, sensitive values should only be passed to the clients or connections that need them; **do not** return secrets via REST APIs, logs, or error messages. The example above intentionally only checks that configuration is valid and does not print the values.

## 6. Runtime Updates, Rotation, and Caching

**App Configuration** supports refresh, but not every change is pushed immediately into every bean:

- The `spring-cloud-azure-appconfiguration-config-web` library can check for refresh through Spring Web activity; it does not create an instant push mechanism for an application receiving no requests. The library also supports active/programmatic checks.
- Enable monitoring/refresh when needed and configure trigger conditions for the system. Once values are reloaded, `@RefreshScope` can help recreate beans after an actual refresh; objects that cache values themselves still need an update strategy.
- The default minimum interval between checks is documented by App Configuration as 30 seconds. Observed results also depend on requests, triggers, and caching.

Example configuration enabling change monitoring (part of `application.properties`):

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
~~~

**Key Vault secret rotation** is a separate flow: create a new secret version, ensure the application can read the appropriate version, update/invalidate caches, and verify that clients are using the new value. If an App Configuration reference specifies **a fixed version**, changing the secret to a new version does not automatically move that reference. If using a versionless URI, whether the application sees the new value still depends on re-resolving the reference and caching/refresh.

Replacing a secret in Key Vault cannot be assumed to automatically update running Spring beans immediately. For critical secrets, design phased rotation: issue the new credential → allow both old and new during a transition window if the system supports it → trigger reload/restart of necessary components → revoke the old credential.

## 7. Security and Reliability in Practice

| Situation | How to Handle |
| --- | --- |
| Application can access App Configuration but resolving reference returns 403 | Check secret permissions on Key Vault for the **same identity** the client actually uses; verify RBAC model or access policy |
| App Configuration returns 403 right at startup | Check `App Configuration Data Reader`, identity/token, role assignment scope, and permission propagation |
| `orders.timeout` is missing or wrong environment is loaded | Check `/application/` prefix, key filter, active Spring profile, label, and configuration source precedence |
| Secret does not exist / invalid reference URI | Check vault name, secret name, version, enabled status, and read permissions |
| Secret was changed but application still uses old value | Review version-pinned reference, cache, refresh interval, beans, and connection pools |
| DNS error, timeout, or 429 | Check network/private endpoint, firewall, retry with backoff; avoid querying secrets too repeatedly |
| Application runs fine locally but fails when deployed | Verify Managed Identity is enabled and roles are granted to the **workload principal**, not the local account |
| Startup tests accidentally call real Azure resources | Disable external source integration in tests and supply dummy properties in the test environment |

Several principles should be applied together:

1. **Least privilege:** separate read permissions for App Configuration and Key Vault; scope roles by application/environment.
2. **Never expose secrets:** avoid logging `Environment`, Actuator `/env`, exception dumps containing credentials, or passing secrets in URLs/tracing.
3. **Environment separation:** use App Configuration labels and consider separate vaults for critical environments; do not share production secrets for local development.
4. **Network controls:** configure private endpoints, firewalls, and access paths to each service according to system policy.
5. **Monitoring:** track authentication failures, configuration loading errors, secret read operations, and latency; never put secret contents into telemetry.
6. **Cost and load:** App Configuration has tier limits/costs, and Key Vault also has its own quotas and read operations; each reference can trigger a Key Vault query, so consider the number of references and caching.

## 8. Testing Without Depending on Real Azure

In business logic tests, supply dummy values (not real credentials) and disable reading external configuration sources. For example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.appconfiguration.enabled=false",
    "spring.cloud.azure.keyvault.secret.property-source-enabled=false",
    "orders.timeout=PT3S",
    "orders.max-retries=4",
    "payments.api-key=test-placeholder",
    "jdbc-password=test-placeholder"
})
class OrdersApplicationTests {
    @Test
    void contextLoads() {}
}
~~~

This kind of test only verifies **Spring wiring and binding**. It does **not** prove Azure permissions, Key Vault references, or refresh work. To verify integration, you can use a dedicated dev environment with a restricted-permission identity, test secrets, and these verification steps:

1. Load `prod` or `dev` keys/labels matching the profile, confirming `orders.timeout`.
2. Verify the `payments.api-key` reference resolves successfully (only confirm the app can use it, do not print the secret).
3. Revoke Key Vault read permission on a test identity, confirming the access error is logged and clearly distinguished from an App Configuration error.
4. Change a non-sensitive configuration value and observe refresh according to the configured interval/trigger.
5. Create a new test secret version, checking behavior when using a version-pinned URI versus a versionless URI.

**Key takeaway:** mock tests keep execution fast and stable, while integration tests need to validate both services, permissions, networking, and data-change lifecycles.

## 9. Decision Exercise

Consider a `checkout-service` system deployed to `dev`, `staging`, and `prod`:

| Requirement | Recommended Decision |
| --- | --- |
| Change partner API timeout across three environments | One App Configuration key, three labels by environment |
| Use different API tokens across three environments | Secrets in Key Vault per environment; reference from App Configuration if a unified management point is desired |
| Enable new checkout for a pilot user group | Feature flag in App Configuration and the appropriate feature management library |
| Application is allowed to view timeout but not partner token | Grant App Configuration role to the config-reading identity; separate Key Vault read permissions according to actual need |
| Rotate token without committing code | Create a new secret version; design reload and update Key Vault reference/configuration per the rotation lifecycle |

**Self-check questions:**

1. Why is App Configuration's data encryption still not enough to treat it as a secret store?
2. When App Configuration contains a Key Vault reference, which component actually retrieves the secret?
3. What issue will an identity with `App Configuration Data Reader` but no Key Vault read permission encounter?
4. Why does changing a secret version not guarantee a running Spring bean sees the new value?
5. When should you use Key Vault Secrets property source directly instead of an App Configuration Key Vault reference?

**Suggested answers:** (1) Key Vault provides dedicated lifecycle governance and permissions for secrets/keys/certificates; (2) the application-side provider; (3) it can read the reference but cannot resolve the secret; (4) there are still URI versions, caching, refresh, and bean lifecycles; (5) when the application only needs to read secrets by name and does not need to manage pointers through App Configuration.

## 10. Official References

- [Microsoft Learn – Azure App Configuration FAQ](https://learn.microsoft.com/en-us/azure/azure-app-configuration/faq): comparison with Key Vault and recommendations for storing secrets.
- [Microsoft Learn – Azure App Configuration quickstart for Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-java-spring-app): dependencies, `spring.config.import`, and `/application/` convention.
- [Microsoft Learn – Key Vault references in Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-key-vault-references-spring-boot): linking the two services.
- [Microsoft Learn – Dynamic configuration in Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): refresh mechanism.
- [Microsoft Learn – Spring Cloud Azure configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): configuration properties for Azure SDK clients and Key Vault property source.
- [Azure SDK – Spring versions mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): choosing a BOM compatible with Spring Boot.
- [Microsoft Learn – App Configuration with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-enable-rbac): data access authorization.

In real-world systems, choose your model based on **data characteristics and update lifecycle**: App Configuration for behavior control and feature flags; Key Vault for secrets/keys/certificates. When combined, the Spring Cloud Azure application is authorized to read configuration, receive references, and independently retrieve secrets from Key Vault using its separately authorized identity.
