# Access Permissions, Remote Source Failure Behavior, and Configuration Testing

A Spring Boot application may run fine on a developer's machine yet fail immediately when deployed to Azure because the **runtime identity lacks data-read permissions**, an endpoint is blocked, or required configuration fails to load. In other cases, the application starts up successfully using defaults, but ends up with stale values, a missing secret, or undetected remote source errors.

When integrating **Azure App Configuration** and **Azure Key Vault**, three aspects must be designed together: **who is permitted to read**, **how the application reacts when a remote source fails**, and **how to test so failures are caught before production**. Spring Cloud Azure constructs Spring `PropertySource` entries from Azure services; therefore, access failures can occur during configuration loading, before controllers or services are instantiated.

This lesson belongs to the **Azure Configuration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, including identities/permissions, storage, messaging, data, secrets, integration testing, and cloud provider comparisons. The goal is to grant the right permissions, select appropriate fail-safe/fail-closed strategies per configuration type, and build a test suite that verifies behavior when Azure experiences failures.

## 1. Expected Outcomes

After this lesson, you will be able to:

1. Distinguish **authentication** (verifying identity) from **authorization** (granting data access permissions).
2. Assign the right Azure RBAC roles for App Configuration and Key Vault; distinguish resource management permissions from data-plane read permissions.
3. Choose Managed Identity/`DefaultAzureCredential` for local, CI, and Azure environments.
4. Explain startup behavior when App Configuration import or Key Vault PropertySource is unreachable.
5. Distinguish mandatory configuration, configuration that can safely use defaults, and secrets that must never arbitrarily fall back.
6. Understand the removal/changes of the `fail-fast` property across Spring Cloud Azure lines and select current high-availability mechanisms.
7. Test binding, context startup, RBAC, remote source failures, refresh, and environment-specific configuration.

Running scenario: `checkout-service` reads `payments.timeout` from App Configuration, retrieves `payments.api-token` via a Key Vault reference, and uses Managed Identity to access both services. The timeout has a safe operational default; the payment token is **mandatory**.

~~~mermaid
flowchart TD
    A["Spring Boot starts"] --> B["Authenticate identity with Microsoft Entra ID"]
    B --> C["Read App Configuration"]
    C --> D["Read Key Vault if reference exists"]
    D --> E["Bind and validate Spring properties"]
    E --> F{"Required config valid?"}
    F -->|Yes| G["ApplicationContext ready"]
    F -->|No| H["Startup fails / instance not Ready"]
    C -->|Connection / permission error| H
    D -->|Connection / permission error| H
~~~

**Principle:** an application is considered ready only when it holds all mandatory configuration needed to execute business logic safely. Never use a dummy value or hard-coded secret to mask an access permission error.

## 2. Authentication and Authorization Are Two Separate Steps

With Microsoft Entra ID, accessing a service involves:

1. **Authentication:** the application proves its identity and obtains an OAuth 2.0 access token.
2. **Authorization:** the Azure service checks whether that token/principal is permitted to perform the operation on the resource or data.

Therefore, a successful `az login` or Managed Identity acquiring a token **does not prove** the application has permission to read App Configuration or Key Vault.

| Component | Question to Answer | Failure Examples |
| --- | --- | --- |
| Authentication | Who is the application? Can a token be acquired? | Wrong tenant, missing credential, identity not enabled |
| Authorization | Does the principal have data-read permission? | 403 Forbidden, missing data-plane role |
| Network | Can the application reach the endpoint? | DNS failure, timeout, TLS, firewall |
| Configuration selection | Are the right keys/labels/secrets selected? | App does not see property even though Azure call succeeded |

### 2.1. DefaultAzureCredential and Managed Identity

Spring Cloud Azure supports credentials such as `DefaultAzureCredential`, `ManagedIdentityCredential`, `WorkloadIdentityCredential`, `ClientSecretCredential`, and `AzureCliCredential`.

A minimal endpoint configuration:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

When no dedicated credential is declared, the client uses Spring Cloud Azure/Azure Identity's default credential mechanism. `DefaultAzureCredential` can draw credentials from deployment or development environments—such as Managed Identity, Workload Identity, Azure CLI, or IDE—depending on configuration and the SDK version's credential order.

**Local development:** you can sign in with `az login`, but you must grant permissions to the exact user/service principal selected by the credential chain.

**Azure runtime:** prefer Managed Identity to avoid storing long-lived client secrets. With a system-assigned identity, the identity is tied to the resource lifecycle. With a user-assigned identity, configure the client ID when selecting a specific identity:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: "${AZURE_CLIENT_ID}"
~~~

`AZURE_CLIENT_ID` is the user-assigned identity's client ID, not a secret. You do not need to configure a client ID when using a single system-assigned identity and the credential resolves properly.

### 2.2. Granting separate permissions for each service

If an application loads key-values from App Configuration and resolves Key Vault references, the runtime identity needs read permissions on **both resources**:

| Resource | Appropriate Azure RBAC Role | Purpose |
| --- | --- | --- |
| Azure App Configuration store | **App Configuration Data Reader** | Read key-values, labels, feature flags, and Key Vault references |
| Azure Key Vault | **Key Vault Secrets User** | Read the secret values pointed to by references |

Do not grant `App Configuration Data Owner` or `Key Vault Administrator` to an application that only needs to read. Resource management roles like `Contributor` do not implicitly grant data-plane read permissions.

If Key Vault still uses **Vault access policy** (the legacy model), grant `Get` on secrets; if the provider needs to list secrets, consider `List` as well. With RBAC, prefer dedicated roles at the required vault scope.

**Note:** permission to read a reference and permission to read a secret are two independent permissions. When App Configuration returns the URI but Key Vault returns 403, check roles on the vault rather than changing the key filter.

### 2.3. Example role assignments with Azure CLI

Example granting App Configuration Data Reader to a principal:

~~~bash
az role assignment create \
  --role "App Configuration Data Reader" \
  --assignee "<principal-object-or-client-id>" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.AppConfiguration/configurationStores/<store-name>"
~~~

Granting Key Vault Secrets User:

~~~bash
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee "<principal-object-or-client-id>" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.KeyVault/vaults/<vault-name>"
~~~

Replace placeholders with actual IDs. Distinguish the **principal object ID** from the client ID when running role assignment commands; check the appropriate flags for your principal type and Azure CLI version. Role assignments can take time to propagate to the data plane. If you just assigned a role, wait for propagation and re-check the token/principal.

### 2.4. Separating runtime permissions from administrative permissions

A practical model:

| Principal | Permission | Allowed Actions |
| --- | --- | --- |
| Spring runtime identity | App Configuration Data Reader | Read configuration |
| Spring runtime identity | Key Vault Secrets User | Read secrets |
| Release pipeline/operator | App Configuration Data Owner or scoped write role | Create/update key-values and references |
| Secret administrator/rotation workflow | Appropriate secret-write role | Create versions, update, or revoke secrets |

Do not share an Owner-privileged principal for runtime merely for deployment convenience. If a workload is compromised, restricted read permissions limit the blast radius.

## 3. Access Permissions Do Not Replace Network Requirements

An identity with the right RBAC roles can still fail to connect if the endpoint is blocked.

Points to verify:

- Does DNS resolve the App Configuration and Key Vault endpoints properly?
- Is the private endpoint inside a VNet reachable by the workload?
- Is the Private DNS zone linked properly to the VNet?
- Do firewalls allow the application's subnet or outbound path?
- Do proxies, TLS certificates, routes, or network security groups block traffic?
- Is the application using the right cloud environment endpoint, not confusing public Azure with a sovereign cloud?

When using private endpoints, verify **each service individually**. App Configuration and Key Vault have separate endpoints, DNS, and firewalls. Reaching one service does not guarantee the other is reachable.

## 4. Behavior When App Configuration Is Unreachable at Startup

When declaring:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Spring Boot processes App Configuration during **Config Data loading**. If a mandatory remote source fails to load, the failure can occur before Spring finishes creating the ApplicationContext.

Common scenarios:

| Failure | Expected Behavior |
| --- | --- |
| Wrong endpoint, DNS, or network timeout | Config cannot be loaded; mandatory import can fail startup |
| Credential fails to acquire token | Startup fails if no valid alternative credential source exists |
| Identity lacks App Configuration Data Reader | Azure returns 403; must not be treated as a safely fallbackable config error |
| Key/label does not exist | Corresponding property may be absent; app validation decides if startup is valid |
| Azure returns 429/5xx | Can retry or fail over if configuration and resources support it |
| Primary App Configuration unavailable while replica is healthy | Client can fail over to configured/discovered replica |

### 4.1. Mandatory configuration and optional import

For mandatory configuration, use import without the optional prefix:

~~~properties
spring.config.import=azureAppConfiguration
~~~

If the store fails to load, the application should fail startup. This is the right choice when remote config holds endpoints, policies, or parameters required to serve business logic properly.

Spring Boot supports the `optional:` prefix for a Config Data location that may not exist:

~~~properties
spring.config.import=optional:azureAppConfiguration
~~~

However, `optional:` is strictly Spring Config Data's optionality mechanism for missing-location errors reported by the resolver. **Do not treat it as a catch-all mechanism to swallow every 401/403, timeout, TLS, DNS, or 429 error from Azure.** Exact behavior depends on how the provider version in use translates errors; run integration tests before relying on optional imports in production.

If the remote source may legitimately be absent and the application has safe local defaults, you can design for optionality. But if a mandatory value is missing both locally and remotely, use validation to prevent the application from starting with incomplete configuration.

### 4.2. Do not use the legacy fail-fast property on Spring Cloud Azure 6.x/7.x

Older Spring Cloud Azure documentation (5.x and earlier) had `spring.cloud.azure.appconfiguration.stores[0].fail-fast`. In the 6.0.0 release line, this property was **removed** alongside the move to standard Config Data imports. Therefore, do not copy:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].fail-fast=false
~~~

into an application using Spring Cloud Azure 6.x/7.x expecting it to ignore remote source failures. Check the documentation for your exact BOM version. When high availability is required, prefer **replicas/geo-replication** instead of assuming a failing store can be safely skipped.

### 4.3. Distinguishing optional config from business defaults

Suppose the local file has:

~~~yaml
payments:
  timeout: PT3S
  max-retries: 2
~~~

Remote App Configuration can override these values when loaded successfully. Yet having local defaults **does not automatically guarantee** the application will start with local defaults if a mandatory import fails before context creation.

If timeout is a non-sensitive parameter with a tested default, you can design the remote source as optional according to verified provider/Spring Boot behavior. If the payment secret is missing, never use a default string to impersonate a production secret.

## 5. High Availability for App Configuration: Replicas and Failover

Spring Cloud Azure 6.0 removed the fail-fast property, and release notes recommend using **replicas** to increase availability. Azure App Configuration supports geo-replication; replicas have separate endpoints and can serve workloads in other regions.

### 5.1. Automatic replica discovery

According to current documentation, the provider can automatically discover a store's replicas. When the active endpoint encounters network errors, HTTP 500+, or 429 throttling, the client can try an appropriate replica endpoint. Once the primary recovers, the client can switch back to primary.

This mechanism helps with service/infrastructure outages, but **cannot fix authorization errors**. If all endpoints use the same principal lacking a role, failing over to a replica will also return 403.

### 5.2. Declaring an ordered endpoint list

Example configuring primary and replica endpoints:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoints:
              - "https://checkout-config-primary.azconfig.io"
              - "https://checkout-config-replica.azconfig.io"
~~~

The endpoints must belong to the same store configuration with replication properly set up. The list is tried in priority order. Check the provider documentation for your specific version regarding auto-discovery and how it combines with explicit endpoint lists.

You can disable auto-discovery if you want complete control over endpoints:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].replica-discovery-enabled=false
~~~

Only disable it when another failover strategy is already in place and tested. Otherwise, the application may lose the ability to switch to discovered replicas.

### 5.3. Replicas do not replace configuration design

- Ensure key-values, labels, and snapshots are replicated per Azure's mechanism.
- Verify the identity's read permissions on the resource/replica under Azure RBAC.
- Monitor latency, connection errors, and failover counts.
- Confirm the application does not depend on an endpoint hard-coded to another environment.
- Test primary down, replica down, and primary recovery.

Replicas improve **configuration source** availability; they do not make invalid secrets or misconfigured values valid.

## 6. Retries and Classifying Remote Errors

Retries help with transient errors like network interruptions, 429, or 5xx. Retries cannot fix configuration or permission errors such as 401, 403, wrong resource names, or missing secrets.

### 6.1. Retries with exponential backoff

Spring Cloud Azure supports retry configuration for Azure SDK clients. Example global configuration:

~~~yaml
spring:
  cloud:
    azure:
      retry:
        mode: exponential
        exponential:
          max-retries: 4
          base-delay: PT0.0801S
          max-delay: PT9S
~~~

Service-level settings can override global settings. For Key Vault PropertySource, you can configure per-source retries:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              retry:
                mode: exponential
                exponential:
                  max-retries: 4
                  base-delay: PT0.0801S
                  max-delay: PT9S
~~~

The numbers above are examples from Spring Cloud Azure documentation, not optimal values for every workload. Tune them based on total startup timeout, service latency, and request budgets. Multi-layer retries (SDK retries + app retries + orchestrator restarts) can multiply call volume and amplify pressure during outages.

### 6.2. Classifying errors before retrying

| Code/Error | Category | Action |
| --- | --- | --- |
| 401 Unauthorized | Credential/token | Check identity, tenant, credential chain; do not retry indefinitely |
| 403 Forbidden | Authorization/RBAC | Grant exact role, verify scope and propagation |
| 404 Not Found | Wrong resource/key/secret or version | Verify endpoint, key, label, secret name, and status |
| 429 Too Many Requests | Throttling | Honor retry-after if supported by SDK, exponential backoff, shed load |
| 500–599 | Service error | Bounded retry, fail over to replica if available |
| DNS/connection timeout | Network | Bounded retry; check DNS, firewall, routes, and private endpoint |
| TLS/certificate validation | Trust/configuration | Fix certificate/proxy/endpoint; never disable TLS verification as a workaround |
| Missing property after load | Mapping/selection/validation | Check key filter, label, secret-keys, and binding |

Never log access tokens, connection strings, secret values, or full HTTP headers. When reporting errors, log error type, non-sensitive resource name, correlation/request ID if available, and a safely identified principal.

## 7. Behavior When Key Vault or a Secret Is Unreachable

Key Vault can be used in two ways in Spring Cloud Azure:

- **Direct Key Vault Secrets PropertySource:** loads secrets into the Spring Environment during initialization.
- **Key Vault reference in App Configuration:** App Configuration provider receives the reference and calls Key Vault to resolve the secret.

### 7.1. Mandatory secrets must fail closed

If `payments.api-token` is required to call the payment gateway, the application must not continue starting with an empty token, a revoked old token, or a demo string. Use validation to catch missing secrets:

~~~java
package com.example.checkout;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        @NotBlank String apiToken,
        @NotNull Duration timeout) {
}
~~~

Enable `@ConfigurationPropertiesScan` in the application class and add a Spring Boot–compatible Bean Validation dependency if not already present. When a secret fails to resolve or a property is missing, validation makes the ApplicationContext invalid rather than building clients with dummy credentials.

### 7.2. There is no single universal fail-fast switch across all sources

App Configuration and Key Vault have different lifecycles:

| Source | Control Mechanism | On Failure |
| --- | --- | --- |
| App Configuration Config Data import | `spring.config.import`, provider enable/disable, replicas, and Config Data optional semantics | Failure to load a mandatory import can fail startup |
| Key Vault reference | App Configuration provider resolves reference using an identity with Key Vault permissions | Resolution failure can leave a property missing or fail startup when the property is required |
| Direct Key Vault PropertySource | `property-source-enabled`, `secret-keys` list, retry, and refresh interval | Secret load failure during initialization can prevent context startup |
| `SecretClient` called in code | Application decides when to call and how to handle exceptions | Failures occur at runtime and must be handled at the service boundary |

Do not assume the legacy `fail-fast=false` property from older App Configuration applies to Key Vault PropertySource or App Configuration 6.x/7.x. Current Key Vault PropertySource property references do not provide an equivalent global fail-fast switch to turn mandatory secrets into optional ones.

### 7.3. Secrets must never fall back to dummy values

Example **not to use in production**:

~~~yaml
payments:
  api-token: "${payments.api-token:demo-token}"
~~~

If the secret is missing, the placeholder fallback lets the application start with a demo value and only fail when real transactions run. For credentials, let mandatory properties and validation fail closed.

You may use a fallback for a **non-sensitive parameter** that has a safe default, such as a timeout. Never use fallbacks to hide authentication failures or revoked secret permissions.

## 8. Readiness, Liveness, and Behavior During Temporary Azure Outages

If an application cannot start due to mandatory configuration, the orchestrator will never receive a Ready instance. If the application has already started and Azure experiences a temporary outage, you must decide whether to keep serving with **last-known-good configuration** or mark the instance Not Ready.

| State | Suggested Handling |
| --- | --- |
| Mandatory configuration never loaded on startup | Fail startup; do not add instance to load balancer |
| Non-sensitive configuration loaded and still usable | Can continue using last-known-good within policy-allowed window |
| Secret expired/revoked or no longer valid | Stop transacting with the old credential; mark Not Ready or reject operations needing the secret |
| Temporary Azure error while app still holds valid cache | Retain cache within safe limits, alert, and retry in a controlled manner |
| New configuration invalid | Do not overwrite last-known-good with broken config; report refresh error and keep previously validated state if provider supports it |

**Do not make liveness probes depend directly on every Azure call.** If Azure is temporarily slow, failing liveness can trigger mass orchestrator restarts and amplify load. Readiness can reflect whether the application can still serve safely; liveness should focus on process forward progress.

If retaining last-known-good is required, explicitly design and test: where the cache lives, how long it may be used, how revoked secrets are handled, and how recovery works once Azure returns. Do not assume Spring Cloud Azure persists remote configuration to disk across restarts.

## 9. Multi-Layer Configuration Testing

No single test type proves the entire integration. Separate binding tests, Spring context tests, Azure permissions, and remote failure behavior.

~~~mermaid
flowchart TD
    A["Unit test: Binder / validation"] --> B["Spring context test: disable Azure providers"]
    B --> C["Integration test: dev App Configuration + Key Vault"]
    C --> D["Failure test: 401/403/404/429/network"]
    D --> E["Deployment test: Managed Identity + private endpoint"]
~~~

### 9.1. Unit tests for binding without calling Azure

Use `MockEnvironment` and `Binder` to verify property names, data types, and defaults:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class PaymentPropertiesBindingTest {
    @Test
    void bindsNonSecretSettings() {
        var environment = new MockEnvironment()
                .withProperty("payments.timeout", "PT3S");

        Duration timeout = Binder.get(environment)
                .bind("payments.timeout", Duration.class)
                .orElseThrow();

        assertThat(timeout).isEqualTo(Duration.ofSeconds(3));
    }
}
~~~

This test requires no Azure credentials and logs no fake secrets. You can add validation tests verifying that missing `payments.api-token` renders the configuration invalid.

### 9.2. Spring context tests with providers disabled

If `application.yml` imports App Configuration and Key Vault PropertySource, business tests must not accidentally call real Azure. Create `application-test.yml`:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        enabled: false
      keyvault:
        secret:
          property-source-enabled: false

payments:
  api-token: test-only-placeholder
  timeout: PT3S
~~~

Context test:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class CheckoutConfigurationContextTest {
    @Autowired
    PaymentProperties properties;

    @Test
    void startsWithExplicitTestConfiguration() {
        assertThat(properties.apiToken()).isEqualTo("test-only-placeholder");
        assertThat(properties.timeout().getSeconds()).isEqualTo(3);
    }
}
~~~

`spring.cloud.azure.appconfiguration.enabled=false` disables loading the store; `property-source-enabled=false` disables Key Vault PropertySource. Use a Spring Cloud Azure BOM that includes fixes for provider disabling issues seen in earlier releases. Check test logs and network activity to ensure zero requests hit Azure.

The `test-only-placeholder` value exists only in the test profile; never use this profile when deploying to production.

### 9.3. Integration tests with dedicated dev resources

To verify RBAC and the real provider, you need a dev/sandbox App Configuration store and Key Vault:

1. Create non-sensitive key-value `/application/payments.timeout`.
2. Create a dummy secret in Key Vault and reference `/application/payments.api-token`.
3. Assign App Configuration Data Reader and Key Vault Secrets User to the test identity.
4. Run the application with that credential and confirm Spring binds both properties.
5. Run a test with an identity holding only App Configuration permissions to confirm the reference fails to resolve when Key Vault permission is missing.
6. Revoke App Configuration permission in the test environment to verify 403 errors are classified accurately.
7. Test non-existent keys/labels and disabled/renamed secrets.
8. Verify logs contain no tokens, secret values, access tokens, or connection strings.

Never run permission-revocation, secret-deletion, or rotation tests on production resources. Create dedicated test identities and resources so negative scenarios never disrupt live services.

### 9.4. Testing when remote sources fail

| Test Case | Safe Simulation Method | Outcome to Verify |
| --- | --- | --- |
| 401 | Use a test identity unable to acquire a token or with wrong tenant | Startup/runtime reports authentication error |
| 403 App Configuration | Test identity missing App Configuration Data Reader | No remote key-values; clear authorization error |
| 403 Key Vault | Has App Configuration permission but lacks Key Vault Secrets User | Reference fails to resolve; mandatory secret keeps app not Ready |
| 404 key/secret | Use a non-existent key or secret name in the dev store | Validation catches missing mandatory property |
| 429 | Load test on dedicated resource or mock SDK response | Bounded retry/backoff, no retry storm |
| 5xx/network | Use test endpoint/replica or mock client | Retry/failover works; logs include correlation ID |
| Private endpoint/DNS | Run workload from a test subnet without proper route | Network error is distinguished from 403 |
| Post-startup refresh failure | Disconnect dev access after app has loaded config | Verify last-known-good/Readiness per policy |

Remote failure tests must observe **both the startup exit code and Spring context state**, not merely check a single exception message.

## 10. Verifying Mandatory Configuration with Validation

Some remote issues do not appear as immediate exceptions on load: a key might not exist, a label might be wrong, or a property name might be mismapped. Therefore, the application must validate configuration after loading.

Example `PaymentProperties`:

~~~java
package com.example.checkout;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        @NotBlank String apiToken,
        @NotNull Duration timeout) {
}
~~~

Enable scanning:

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

Add the Spring Boot–compatible validation dependency if the project does not have it yet:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

When `payments.api-token` fails to resolve or `payments.timeout` is missing, validation fails the context. This is a vital safeguard: **successfully loading a PropertySource does not mean the application's configuration is valid**.

Do not override `toString()` on a secret-bearing object in a way that prints all fields. When logging status, log only a configured boolean or non-sensitive property names.

## 11. Observability and Operations During Source Outages

A system can track:

- Successful and failed App Configuration/Key Vault loads.
- Latency, timeouts, 401/403, 404, 429, and 5xx counts.
- Retry counts, failovers, and recovery time.
- Timestamp of last successful refresh and age of loaded configuration.
- Ready status of each instance.
- Loaded secret version or metadata if recordable without revealing the value.

Never log secrets, tokens, or the entire `Environment`. If logging a Key Vault URI, consider logging only the vault/secret name and error type, never credentials or token-bearing queries.

### 11.1. Health checks must not create unbounded load

Do not call App Configuration and Key Vault on every readiness probe if probes run every few seconds. Instead, inspect the status of the latest cache/refresh and configuration validity window per application policy. If active connectivity probing is needed, use a bounded interval and never let health checks generate an Azure request on every single probe.

### 11.2. Rules for retaining last-known-good

For non-sensitive configuration, the app can continue using the most recently loaded value within an allowed window if refresh fails. Define:

- Maximum TTL for last-known-good.
- Which settings are permitted to use stale values.
- How alerts fire when the TTL is exceeded.
- Conditions under which the instance transitions to Not Ready.
- How configuration reloads and validates once the source returns.

For revoked or potentially exposed secrets, last-known-good is not always safe. Maintain a dedicated incident workflow to invalidate credentials, update clients, and stop transacting with the old token.

## 12. Fail-Open vs. Fail-Closed Decision Matrix

| Data Type | When Remote Source Fails | Recommended Decision |
| --- | --- | --- |
| Banners, display messages | Can use local value | Fail-open if default does not impact business logic |
| Timeout/retry with safe default | Can use tested local default | Bounded fail-open with alerting |
| Payment service endpoint | Wrong endpoint can send data to an unintended target | Usually fail-closed, or use only a controlled local endpoint |
| API tokens/passwords | Without a valid secret, safe authentication is impossible | Fail-closed |
| Security/authorization rules | Missing policy can overly broaden permissions | Fail-closed |
| Rollout feature flags | Can select the old branch if tested | Define per-flag defaults; never replace authorization |
| Data routing configuration | Can write to the wrong tenant/region | Fail-closed or controlled last-known-good |

**Fail-open** means the application continues operating with substitute values when a source fails. **Fail-closed** means refusing to start or refusing the operation if required configuration cannot be verified. Decide based on the consequence of using the wrong value, not merely to raise startup success rate.

## 13. Comprehensive Practice Exercise

An `order-service` uses:

- `orders.timeout` from App Configuration, with local default `PT3S`.
- `orders.partner-token` as a mandatory Key Vault reference.
- Managed Identity to read both services.
- Two App Configuration replicas across two regions.
- Spring Boot running three instances behind a load balancer.

**Requirements:**

1. Grant App Configuration Data Reader and Key Vault Secrets User to the exact runtime identity.
2. Design the import so timeout can fall back to its default when policy allows, while a missing token keeps the instance not Ready.
3. Configure replica endpoints and verify failover when primary returns 503/429.
4. Write unit tests for binding with dummy values.
5. Write a context test with both providers disabled.
6. Write an integration test with a test identity lacking Key Vault permission.
7. Verify logs do not print tokens and readiness does not continuously restart instances during temporary Azure errors.

**Self-assessment questions:**

- Why does acquiring an access token not prove the application can read a secret?
- What is the difference between App Configuration Data Reader and Contributor?
- Why should the `fail-fast` property from Spring Cloud Azure 5.x docs not be used on 6.x/7.x?
- When is `optional:azureAppConfiguration` useful, and why is it not a cure-all for network/403 errors?
- If App Configuration has replicas but the identity lacks roles on all endpoints, can failover solve it?
- Why should a mandatory secret fail closed while a banner can use a default?
- What does a Binder unit test prove and what does it not prove?

**Guided answers:** authentication issues tokens while authorization grants data-plane permissions; Data Reader only reads data whereas Contributor manages resources; `fail-fast` was removed starting in 6.0; `optional` only handles optional Config Data locations rather than replacing retries/replicas; replicas cannot fix 403; secrets must never fall back to dummy credentials; unit tests verify binding while integration tests verify real identities and Azure.

## 14. Official Reference Sources

- [Microsoft Learn – Spring Cloud Azure authentication](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/authentication): DefaultAzureCredential, Managed Identity, Microsoft Entra ID, and Azure RBAC.
- [Microsoft Learn – Developer Guide for Using Spring Cloud Azure App Configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): Config Data import, authentication, geo-replication, and failover.
- [Spring Cloud Azure – App Configuration client README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/spring/spring-cloud-azure-starter-appconfiguration-config/README.md): provider properties and endpoint/replica configuration.
- [Spring Cloud Azure – App Configuration release notes](https://github.com/Azure/AppConfiguration/blob/main/releaseNotes/SpringCloudAzureAppConfigurationConfig.md): 6.0 breaking changes, including the removal of `fail-fast`.
- [Microsoft Learn – Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): secret read/write roles and permission scopes.
- [Microsoft Learn – Spring Cloud Azure secret management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management): Key Vault PropertySource, secret-keys, retries, and refresh.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): Config Data import, optional locations, and property source precedence.
- [Microsoft Learn – Use dynamic configuration in a Spring Boot app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): manual/automatic refresh and impact on refresh-scoped beans.

**Remember:** Azure integration testing must verify the exact **principal, roles, network, resources, and property mappings**. For remote sources, classify errors before retrying, use replicas for availability, use fallbacks only for settings with safe defaults, and always fail closed when mandatory secrets or policies are invalid.
