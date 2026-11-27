# Configuration Refresh, Caching, and Secret Rotation

In a Spring Boot application running on Azure, configuration and secrets are typically loaded at startup and held in memory to serve requests. This reduces latency and service call volume, but raises three operational questions: **how to pick up new configuration**, **where caches live and how they are updated**, and **how to rotate secrets so running clients do not continue using old credentials**.

Spring Cloud Azure combined with **Azure App Configuration** and **Azure Key Vault** provides different mechanisms for each type of data. App Configuration supports polling-based, request-based, or manual refresh; Key Vault PropertySource has its own refresh interval; Key Vault references need re-resolution because App Configuration does not know when a secret on the Key Vault side has changed. Ultimately, beans, HTTP clients, and connection pools inside the application still need appropriate lifecycles to adopt new values.

This lesson belongs to the **Azure Configuration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, including identities/permissions, storage, messaging, data, secret protection, integration testing, and cloud provider comparisons. The goal here is to design **an observable, testable, and rollback-capable refresh and secret rotation workflow**.

## 1. Learning Objectives and Running Scenario

After this lesson, you should be able to:

1. Distinguish App Configuration refresh from direct Key Vault PropertySource refresh.
2. Configure polling, sentinel triggers, manual refresh, and request-based refresh in Spring.
3. Identify whether caching lives in the provider, a Spring bean, or a business client.
4. Explain why changing a secret in Key Vault does not automatically cause App Configuration to detect the change.
5. Design versioned/versionless URIs, cache TTLs, and rotation cycles.
6. Implement rotation with credential overlap, verify all instances, and revoke old credentials at the right time.
7. Test refresh and rotation in a dev environment without modifying production vaults.

Suppose `checkout-service` has:

- `payments.timeout` in Azure App Configuration, adjustable per environment.
- `payments.api-token` as a Key Vault reference pointing to secret `payments-api-token`.
- `PaymentGatewayClient` created at Spring startup and holding the token in memory to call the partner.
- 4 application instances running behind a load balancer.

When the timeout changes, we want the application to receive the new value without restarting. When the token rotates, we want instances to adopt the new token, verify successful transactions, and only then revoke the old token.

~~~mermaid
flowchart TD
    A["Azure App Configuration"] --> B["Spring Cloud Azure provider"]
    K["Azure Key Vault"] -->|Secret value| B
    B --> C["Spring Environment / PropertySource"]
    C --> D["ConfigurationProperties / RefreshScope"]
    D --> E["HTTP client / DataSource / service"]
    F["Refresh trigger / interval"] --> B
    G["Rotation workflow"] --> K
    G --> F
~~~

**Core principle:** reloading values from Azure and replacing the values clients actively use are **two separate steps**. Completing the first step does not prove the second step has occurred.

## 2. Distinguishing Data Types and Lifecycles

| Data Type | Source | Primary Refresh Mechanism | Example |
| --- | --- | --- | --- |
| Regular configuration | App Configuration key-value | Monitoring/polling, manual refresh, request-based refresh | Timeout, retries, public endpoint |
| Feature flag | App Configuration Feature Manager | Monitoring and feature-flag refresh interval | Enable checkout v2 |
| Direct secret | Key Vault Secrets PropertySource | `refresh-interval` of each vault property source | Password, API token |
| Referenced secret | App Configuration Key Vault reference | Re-resolve reference via App Configuration forced refresh or when reference changes | `payments.api-token` |

Each service has its own caching and change-notification behavior:

- **App Configuration** knows when its key-values or references change ETag.
- **Key Vault** knows when a secret gets a new version, but App Configuration does not automatically receive that event merely because the reference URI stayed the same.
- **Spring** can refresh properties and recreate certain beans.
- **HTTP clients, connection pools, or `String` values held in fields** may still hold old credentials.

Do not apply a single refresh interval across all data types without understanding which mechanism is actually watching for changes.

## 3. Refreshing Key-Values from Azure App Configuration

### 3.1. Polling and monitoring

The App Configuration provider supports **pull-based refresh**. The application checks whether watched keys have changed; if a change is detected, the provider reloads configuration and publishes a Spring refresh event.

Example configuration:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            monitoring:
              enabled: true
              refresh-interval: 30s
              triggers:
                - key: /application/config.refresh-sentinel
                  label: prod
~~~

In App Configuration, create `/application/config.refresh-sentinel` with label `prod`. This is the **sentinel key**. When updating a batch of settings, update the target keys first, then update the sentinel last. The provider watches the sentinel's ETag; when a change is detected, it refreshes the selected configuration in the store.

| Property | Meaning |
| --- | --- |
| `monitoring.enabled` | Enables change monitoring |
| `monitoring.refresh-interval` | Minimum interval between checks |
| `monitoring.triggers[].key` | Key watched via ETag |
| `monitoring.triggers[].label` | Label of the sentinel; must match the record created in the store |

According to Spring Cloud Azure documentation, the default refresh interval is **30 seconds** and can be configured above 1 second. This is the minimum wait before the next check is allowed, not a guarantee that every instance updates after exactly 30 seconds.

If no trigger is declared, some provider versions support watching the selected collection; for clear release workflows and to avoid refreshing on unrelated key edits, declare an explicit sentinel and verify behavior for your library version.

### 3.2. Why use a sentinel?

Suppose a release updates 6 keys: timeout, retries, endpoint, transaction limit, and two other parameters. If the provider watches every key, updates in progress could trigger multiple partial refreshes before all new data is written.

A sentinel provides **a single commit-signal point**:

1. Update all configuration keys.
2. Verify the keys are saved properly.
3. Update the sentinel.
4. Instances detect the new ETag and reload configuration.

A sentinel does not create an atomic transaction across multiple keys. It only tells the application **when a batch of configuration is finished publishing**. If you need immutable snapshots for releases, evaluate App Configuration snapshots.

### 3.3. Request-based refresh with the Web library

When using `spring-cloud-azure-appconfiguration-config-web` (or the Web variant supported by your project's BOM), a Spring MVC application can automatically check for refresh when receiving `ServletRequestHandledEvent`.

Monitoring configuration still needs to be enabled:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key=/application/config.refresh-sentinel
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].label=prod
~~~

This mechanism **is tied to request activity**. If the application receives no servlet requests, cache expiration alone does not ensure a refresh runs. In practical guides, after the interval elapses, the first request may trigger the check; subsequent requests observe the refreshed values depending on bean scope.

Do not rely on end-user requests as a mechanism to guarantee a security change takes effect instantaneously. For sensitive scenarios, use a controlled refresh/restart workflow and verify per-instance state.

### 3.4. Manual refresh

Both the core and Web libraries support proactive calls via the `AppConfigurationRefresh` bean. Example in an internal Spring MVC controller:

~~~java
package com.example.checkout;

import com.azure.spring.cloud.appconfiguration.config.AppConfigurationRefresh;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InternalConfigurationRefreshController {
    private final AppConfigurationRefresh refresh;

    InternalConfigurationRefreshController(AppConfigurationRefresh refresh) {
        this.refresh = refresh;
    }

    @PostMapping("/internal/configuration/refresh")
    boolean refreshConfiguration() {
        // Imperative MVC example: call on request thread, not WebFlux event loop.
        return Boolean.TRUE.equals(refresh.refreshConfigurations().block());
    }
}
~~~

`refreshConfigurations()` returns a reactive result indicating whether a refresh was triggered. Returning `false` is not necessarily an error: the interval may not have elapsed, no change was detected, or another thread is already checking.

The illustrative endpoint must be **protected with administrative authorization**, network restrictions, and auditing. Never expose a public refresh endpoint. In WebFlux/reactive applications, never call `.block()` on the event loop; use reactive composition or an appropriate execution mechanism.

### 3.5. Where do manual and automated approaches differ?

| Mechanism | Who Triggers the Check? | When Appropriate |
| --- | --- | --- |
| Poll + sentinel | Request/worker/manual calls refresh after interval | Want control over which key group is watched |
| Web automatic | Servlet request events after interval | Spring MVC apps with steady request traffic |
| Manual `AppConfigurationRefresh` | Code or internal task | Console apps, jobs, orchestrated operations |
| Push/Event Grid webhook | Azure event calls an endpoint | Only consider when needed and lifecycle is understood; current docs no longer recommend this as the default approach |

Microsoft documentation marks push-based refresh as **no longer recommended**, even though still supported. Prefer pull/monitoring or manual refresh unless the architecture has a clear reason otherwise.

## 4. How Does Spring Update Beans After Refresh?

When the provider receives new configuration, it updates the Spring configuration system and emits a refresh event. However, **not every Java object updates its state automatically**.

### 4.1. `@ConfigurationProperties`

Beans created from `@ConfigurationProperties` are integrated into refresh scope by default in Spring Cloud Azure. When refresh succeeds, the bean is recreated and bound with the new values.

Example:

~~~java
package com.example.checkout;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentSettings(Duration timeout, int maxRetries) {
}
~~~

After refresh, consumers accessing the proxy/bean under refresh scope receive the new configuration. If code copied `settings.timeout()` into another field at startup, that field may still retain the old value.

### 4.2. `@RefreshScope` for client-creating beans

For beans that construct clients from tokens or endpoints, mark the bean for recreation:

~~~java
package com.example.checkout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PaymentClientConfiguration {

    @Bean
    @RefreshScope
    PaymentGatewayClient paymentGatewayClient(
            @Value("${payments.api-token}") String token,
            @Value("${payments.base-url}") String baseUrl) {
        return new PaymentGatewayClient(baseUrl, token);
    }
}
~~~

When refresh scope is refreshed, the `PaymentGatewayClient` bean is recreated with the new property values. The example assumes the client class is an application adapter; in a real project, verify that the client/SDK supports clean recreation and proper closing of old resources.

**Do not mark only the config bean and forget the client holding the secret.** If a singleton creates an HTTP client in its constructor and stores the token in an interceptor, refreshing a `PaymentSettings` bean will not automatically update that interceptor. Either place the client in refresh scope or design a credential provider whose value can be safely replaced.

### 4.3. Bean scope does not replace resource lifecycles

| Component | After Property Changes | Action Required |
| --- | --- | --- |
| `@ConfigurationProperties` bean | Can be refreshed/rebound by integration | Consumers must read the new bean/proxy |
| `@RefreshScope` bean | Marked stale and recreated on access | Ensure new client initialization and proper cleanup of old client |
| HTTP client holding token | May still use old token if not recreated | Rebuild client or update credential provider |
| JDBC connection pool | Existing connections may continue using old sessions | Coordinate pool/reconnect; test with driver and DB |
| `String` copied into singleton field | Does not update automatically | Avoid manual caching or design explicit updates |
| Business cache | Does not automatically know config changed | Evict/refresh by version or TTL |

## 5. Cache Layers in the Architecture

Picture a secret traveling from Key Vault to a request:

~~~text
Key Vault secret/version
        |
        v
Provider cache / Spring PropertySource
        |
        v
Spring Environment + RefreshScope
        |
        v
PaymentGatewayClient / connection pool
        |
        v
Business-specific cache (if any)
        |
        v
Running request
~~~

Each layer has its own lifecycle. Seeing a property change in `Environment` does not yet prove the client switched tokens.

### 5.1. Provider-side caching

The App Configuration client caches loaded configuration so it does not call Azure on every property read. Monitoring/refresh checks at intervals and reloads when changes occur.

Direct Key Vault PropertySource also has its own cache. According to Spring Cloud Azure documentation, each property source's `refresh-interval` defaults to **30 minutes**. You can configure:

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
              refresh-interval: 15m
~~~

This property applies only to **direct Key Vault PropertySource**. If the application retrieves secrets via **App Configuration Key Vault reference**, you must understand App Configuration's forced refresh mechanism in section 6; do not set `keyvault.secret.property-sources[].refresh-interval` expecting it to affect references not loaded through that property source.

### 5.2. Caching inside application clients

HTTP clients commonly hold tokens inside interceptor configurations or connection objects to reduce overhead. This helps performance, but means the client may keep using the old token after the provider cache updates.

Do not call Key Vault on every request just to always have the latest value. That increases latency, network dependency, and throttling risk. Instead:

- Cache credentials in memory at the required scope.
- Refresh on events/intervals or via a rotation workflow.
- Update the client atomically or swap instances in a controlled manner.
- Use retries with backoff for transient errors.
- Track the age of the active credential and loaded version, but **never log secret values**.

Microsoft recommends caching secrets in memory and refreshing on secret rotation to reduce Key Vault calls and avoid throttling.

## 6. Refreshing Key Vault References When Secrets Change

This is an essential detail when combining App Configuration and Key Vault.

### 6.1. Why does App Configuration monitoring miss secret changes?

Suppose App Configuration contains:

| Key | Value |
| --- | --- |
| `/application/payments.api-token` | Versionless URI to `payments-api-token` |

The secret in Key Vault changes from version A to version B, but the URI in App Configuration **does not change**. App Configuration does not know the data behind the URI changed, so the reference key's ETag can remain identical. A monitoring trigger checking only App Configuration ETags will not detect the secret rotation.

**Spring Cloud Azure's solution:** configure the global forced refresh property:

~~~properties
spring.cloud.azure.appconfiguration.refresh-interval=5m
~~~

The `spring.cloud.azure.appconfiguration.refresh-interval` property sets the refresh cycle for all App Configuration settings. Unlike `stores[0].monitoring.refresh-interval`, it **does not check watch keys**; its purpose includes refreshing Key Vault references because App Configuration cannot know when a Key Vault secret has changed.

| Property | Scope | Mechanism |
| --- | --- | --- |
| `stores[0].monitoring.refresh-interval` | Store monitoring | After interval, checks triggers/collection; refreshes if changed |
| `spring.cloud.azure.appconfiguration.refresh-interval` | Global forced client refresh | Refreshes configuration on interval without checking watch keys |
| `keyvault.secret.property-sources[0].refresh-interval` | Direct Key Vault PropertySource | Refreshes secrets loaded by that PropertySource |

Do not confuse these three properties. They govern **three different data-loading paths**.

### 6.2. Complete configuration for Key Vault references

Example `application.yml`:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        refresh-interval: 5m
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            monitoring:
              enabled: true
              refresh-interval: 30s
              triggers:
                - key: /application/config.refresh-sentinel
                  label: prod
~~~

- `monitoring.refresh-interval` detects changes in App Configuration key-values/sentinel.
- `appconfiguration.refresh-interval` periodically reloads all configuration, including re-resolving Key Vault references to fetch current secrets.
- `5m` and `30s` are **illustrative values only**. Choose intervals based on sensitivity, load, quotas, instance count, and client refresh capability.

Each resolved Key Vault reference generates a secret pull to Key Vault; Key Vault returns secrets per read. With many references, an overly short refresh interval can spike requests and hit throttling. Reference only truly necessary secrets.

### 6.3. When the reference URI is version-pinned

There are two cases:

| Reference URI | When Secret Gets a New Version |
| --- | --- |
| Versionless | Upon re-resolution, Key Vault can return the current secret version for that URI |
| Fixed version | Continues returning the pinned version; to switch, update the reference URI in App Configuration |

With a version-pinned URI, updating the reference in App Configuration changes its ETag; monitoring triggers or collection monitoring can detect and load the new URI. With a versionless URI, the App Configuration key does not change when only the secret changes; forced refresh is the mechanism to rely on.

In either case, after the provider resolves the new value, ensure beans/clients are updated and verify every instance uses the new credential.

## 7. Secret Rotation Strategies

Rotation means replacing an old credential with a new credential and ensuring workloads switch to the new value before revoking the old one. **Creating a new version in Key Vault is only one step of rotation.**

### 7.1. Single-credential vs. dual-credential rotation

| Target System Type | Rotation Model | Characteristics |
| --- | --- | --- |
| Accepts only one credential at a time | Must coordinate change timing on both service and app | May require a maintenance window or accept a brief interruption |
| Supports two concurrent credentials (primary/secondary) | Create new credential in unused slot, switch workloads, then rotate the other slot | Can achieve near zero downtime if steps and clients are coordinated properly |

For example, a payment provider supporting two API keys:

- Key A is active; Key B is the standby slot.
- Create new Key B and store it in Key Vault.
- Update the reference/config so the application loads Key B.
- Verify instances and successful transactions.
- Revoke Key A, leaving slot A ready for the next rotation.

Not every service supports dual credentials. When there is only one password, schedule changes on both the database and application sides, prepare rollback, and control the transition window.

### 7.2. Recommended rotation workflow

~~~mermaid
flowchart TD
    A["Create new credential at target service"] --> B["Store new version in Key Vault"]
    B --> C["Update reference if URI is version-pinned"]
    C --> D["Trigger refresh / rolling restart"]
    D --> E["Recreate client and verify all instances"]
    E --> F{"Transactions and health checks pass?"}
    F -->|Not yet| G["Roll back to old credential"]
    G --> E
    F -->|Pass| H["Revoke old credential"]
    H --> I["Record version and complete rotation"]
~~~

Detailed sequence:

1. **Prepare:** identify owner, credential expiration, current version in use, instance count, and dual-credential support.
2. **Create new credential:** generate at the target service first (if required by the service), verifying the new credential is valid.
3. **Store in Key Vault:** create a new secret version; never put values into pipeline logs.
4. **Update reference:** if the URI is version-pinned, replace the URI in App Configuration. If versionless, schedule forced refresh or an appropriate trigger.
5. **Refresh application:** invoke refresh/wait out the interval or perform a rolling restart; recreate beans/clients holding tokens.
6. **Verify:** check non-sensitive version/metadata, health, test transactions, and authentication error counts across all instances.
7. **Revoke old credential:** only after confirming no workload still uses it.
8. **Audit:** record timestamp, operator, new version, outcome, and revocation time; never store plaintext secrets.

### 7.3. Event Grid and automation

Key Vault can emit secret lifecycle events, such as new version creation or near-expiration. **Event Grid** can route events to an Azure Function, Logic App, or operational workflow.

Events **do not automatically update variables inside the JVM**. Automation must perform follow-up actions: update a reference/sentinel, call a protected refresh mechanism, or orchestrate a rolling restart. If an event reaches only one instance, fan it out to other instances or let each instance refresh on its schedule.

For critical workflows, use Event Grid to **initiate the workflow**, while client switching and verification still require explicit steps.

## 8. Multi-Instance Refresh and Consistency

Suppose 4 instances sit behind a load balancer. Each instance has its own cache, its own timer/trigger, and its own clients. When configuration changes:

- Instance A may refresh first; instance B only refreshes on its next request.
- Some requests may be served by old clients during the transition period.
- If the old credential is revoked too early, unrefreshed instances may get 401/403 errors.
- If a request retries onto another instance, behavior may differ during the transition window.

### 8.1. Designing compatibility during the transition window

For credentials that can overlap, keep both old and new credentials valid during the transition window. Revoke the old one only when:

- Every instance has loaded the new version.
- HTTP clients/connection pools have been recreated or updated.
- No authentication errors from the old credential remain.
- In-flight requests have completed or exceeded the maximum allowed timeout.

If overlap is impossible, use a **rolling restart or maintenance window** coordinated with the target service. Never revoke a credential merely because one instance reported a successful refresh.

### 8.2. Avoiding synchronized refresh storms

If every instance refreshes at the exact same moment, requests to Key Vault/App Configuration spike. Consider:

- Using reasonable intervals and jitter where supported by the library/mechanism.
- Limiting the number of Key Vault references and loaded secret lists.
- Retrying with exponential backoff for 429/5xx errors and timeouts.
- Avoiding ultra-short refresh intervals just to shrink rotation time.
- Monitoring request counts, latency, auth errors, and cache age per instance.

## 9. Choosing TTLs and Cache Policies

No single TTL fits all data types. Choose based on **rate of change, impact of stale values, service load, and rollback capability**.

| Data | TTL / Refresh Guidance | Reason |
| --- | --- | --- |
| Non-sensitive timeouts/retries | 30s monitoring or longer as needed | Changes rarely need instantaneous rollout |
| Feature flags | Dedicated feature flag refresh interval | Rollout decisions need responsiveness while still bounding load |
| Versionless Key Vault reference | App Configuration forced refresh per rotation policy | App Configuration does not automatically detect secret changes |
| Direct Key Vault PropertySource | Default 30m or configured `refresh-interval` | Provider caches and refreshes selected secrets |
| Credentials in HTTP clients | Cache for client lifecycle; update on rotation | Avoid calling Key Vault on every request |
| Credentials in connection pools | Coordinate with pool/driver and connection lifetime | New properties do not alter already-open sessions |

A short TTL keeps old secrets in cache for less time, but increases service call volume. A long TTL reduces load but widens the window of using old credentials. For compromised secrets or emergency revocations, **do not wait out normal TTLs**; follow incident response procedures to revoke credentials and orchestrate immediate updates.

## 10. Testing Refresh and Rotation

### 10.1. Unit tests without Azure dependencies

Unit tests for configuration-reading logic should use dummy values and never call App Configuration/Key Vault. Example using `MockEnvironment` and Spring Binder:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class PaymentSettingsTest {
    @Test
    void bindsConfigurationValues() {
        var environment = new MockEnvironment()
                .withProperty("payments.timeout", "PT3S")
                .withProperty("payments.api-token", "test-token");

        PaymentSettings settings = Binder.get(environment)
                .bind("payments", Bindable.of(PaymentSettings.class))
                .orElseThrow();

        assertThat(settings.timeout()).isEqualTo(Duration.ofSeconds(3));
        assertThat(settings.toString()).doesNotContain("test-token");
    }
}
~~~

This test verifies binding and how the object avoids exposing secrets; it does not prove Azure refresh or RBAC.

### 10.2. Testing App Configuration refresh in a dev environment

With a test store and identity:

1. Create `/application/payments.timeout` and sentinel `/application/config.refresh-sentinel` with matching labels.
2. Start the app with monitoring enabled and record the initial timeout.
3. Change the timeout in the portal; once the interval elapses, send a request or call `AppConfigurationRefresh`.
4. Observe refresh logs and verify `@ConfigurationProperties` receives the new value.
5. Verify `@RefreshScope` beans are recreated; confirm the new client uses the new value.
6. Run with multiple instances and observe per-instance delay.

Never use real secrets in logs. Observe only non-sensitive values like timeout or a test-designed version label.

### 10.3. Testing Key Vault reference rotation

In a dev vault:

1. Create secret `payments-api-token` version A with a dummy token.
2. Create an App Configuration reference to the **versionless** URI.
3. Start the app and confirm the sandbox client uses token A.
4. Create version B while keeping A valid.
5. Wait for or trigger App Configuration forced refresh; verify the property re-resolves.
6. Recreate `PaymentGatewayClient` or update the credential provider.
7. Send sandbox transactions and verify all instances use B.
8. Revoke A in the test environment and confirm no requests still depend on A.

Repeat with a version-pinned URI to verify that the URI must be updated when switching versions.

### 10.4. Scenario matrix to cover

| Scenario | Expected Result |
| --- | --- |
| Sentinel unchanged | Trigger does not cause a data refresh |
| Sentinel changed after interval | Provider reloads selected configuration |
| Manual refresh before interval | Does not force a new check request |
| Secret changed but reference URI unchanged | Requires forced refresh/re-resolution per policy |
| Version-pinned URI, secret gets new version | Continues using old version until reference changes |
| New property, old client not recreated | Client may continue using old credential |
| Identity lacks Key Vault permission | Reference resolution fails; never fall back to hard-coded production token |
| One instance has not refreshed yet | Old credential must remain valid during transition window if zero downtime is required |

## 11. Diagnosing Common Failures

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Changed key in portal but app did not update | Monitoring disabled, interval not elapsed, or no request/manual trigger | Check `monitoring.enabled`, triggers, and refresh invocation |
| Waited over 30 seconds but Web app still uses old config | No servlet request arrived to trigger automatic refresh | Send a request after interval or use manual refresh |
| `refreshConfigurations()` returns false | Interval not reached, no changes detected, or another thread is checking | Treat as no-op refresh state; do not assume error |
| `@ConfigurationProperties` updated but HTTP client uses old config | Client holds a copy of token/timeout in a field | Use `@RefreshScope`, recreate client, or use a credential provider |
| New Key Vault secret but Spring reference stays stale | App Configuration does not know the secret behind the URI changed | Configure `spring.cloud.azure.appconfiguration.refresh-interval` |
| Versioned URI still returns old secret | Reference is pinned to a version | Update URI in App Configuration |
| Key Vault returns 403 on resolve | Identity lacks `Key Vault Secrets User` or `Get` access policy | Check runtime principal and vault scope |
| App Configuration returns 403 | Missing `App Configuration Data Reader` | Check role on the exact store |
| 429 during refresh | Too many references/requests or simultaneous refreshes | Reduce call frequency, cache, use jitter/backoff, and limit secrets |
| App only picks up secret after restart | Bean/client holds old value or provider is not refreshing | Design lifecycle and test refresh before relying on automated rotation |
| Some instances use old token | Per-instance independent caches/refreshes | Track each instance, overlap credentials, rolling refresh/restart |
| Logs contain secrets | Logging full config objects, exceptions, or HTTP headers | Redact data, reduce logging, and audit telemetry |

## 12. Production Operations Procedure

A standard procedure can be divided into four phases:

**Before rotation**

- Identify owner, credential expiration, current version in use, instance count, and dual-credential support.
- Confirm whether the target service supports dual credentials.
- Identify refresh intervals, manual/automatic mechanisms, and how clients are recreated.
- Verify read permissions and monitoring on Key Vault/App Configuration.

**During rotation**

- Create the new credential at the target service.
- Save the new version in Key Vault.
- Update the reference if the URI is version-pinned, or trigger forced refresh if versionless.
- Refresh each instance or perform a rolling restart; verify new clients.

**After rotation**

- Verify all instances and test transactions.
- Revoke the old credential after the overlap window closes.
- Review logs/audits and update rotation records.

**During an incident or suspected secret leak**

- Revoke the exposed credential at the target service per incident procedures.
- Do not wait out normal cache TTLs.
- Trigger urgent updates across all instances, restarting if necessary.
- Audit permissions, access logs, and signs of anomalous usage.
- Record root cause and add preventive controls.

## 13. Applied Exercise

An `order-service` running 5 instances requires:

- `orders.timeout` in App Configuration, changeable without restart.
- `orders.partner-token` as a Key Vault reference to a versionless secret URI.
- An HTTP client holding the token in memory.
- A provider supporting primary/secondary tokens.

**Tasks:**

1. Enable monitoring and a sentinel for `orders.timeout`.
2. Choose a forced refresh interval to update Key Vault references when the secret changes.
3. Annotate the HTTP client–creating bean with `@RefreshScope` or design an updatable credential provider.
4. Write a primary/secondary rotation plan keeping both tokens valid during the transition window.
5. Verify the new version is loaded and all 5 instances use the new token before revoking the old token.

Self-assessment questions:

- Why is `monitoring.refresh-interval` insufficient to detect a secret change behind a versionless URI?
- What is the difference between `spring.cloud.azure.appconfiguration.refresh-interval` and `stores[0].monitoring.refresh-interval`?
- Why might the first request after the interval trigger a refresh yet still read the old value?
- When must `@RefreshScope` be placed on the client-creating bean instead of only on the properties bean?
- Why is caching secrets in memory usually better than calling Key Vault on every request?
- When must a rolling restart or maintenance window be used instead of automatic refresh?

**Guided answers:** App Configuration does not know a Key Vault secret changed if the reference/ETag is unchanged; global forced refresh re-resolves references while monitoring checks triggers; a request may trigger refresh before scoped beans are recreated/read on the next call; clients retaining secrets must be recreated; caching cuts latency and throttling; single-credential services may require coordinated transition windows.

## 14. Official References

- [Microsoft Learn – Use dynamic configuration in a Java Spring app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): polling, manual refresh, Web request-based refresh, and `AppConfigurationRefresh`.
- [Microsoft Learn – Spring Cloud Azure App Configuration support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): monitoring, sentinels, forced refresh, Key Vault references, feature flags, and health.
- [Microsoft Learn – Spring Cloud Azure App Configuration Java API reference](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-cloud-starter-appconfiguration-config-readme?view=azure-java-stable): refresh interval, trigger, and feature flag interval properties.
- [Microsoft Learn – Secure your Azure Key Vault secrets](https://learn.microsoft.com/en-us/azure/key-vault/secrets/secure-secrets): secret caching, refreshing on rotation, retry/backoff, Event Grid, and monitoring.
- [Microsoft Learn – Azure Key Vault as Event Grid source](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-key-vault): secret/key/certificate lifecycle events.
- [Microsoft Learn – Automate secret rotation for resources with two sets of authentication credentials](https://learn.microsoft.com/en-us/azure/key-vault/secrets/tutorial-rotation-dual): dual-credential rotation workflow to minimize downtime.
- [Microsoft Learn – Automate secret rotation for resources with one set of authentication credentials](https://learn.microsoft.com/en-us/azure/key-vault/secrets/tutorial-rotation): coordinating rotation when a service supports only one credential.
- [Microsoft Learn – Azure Key Vault throttling guidance](https://learn.microsoft.com/en-us/azure/key-vault/general/overview-throttling): service limits and load handling.

**Remember:** provider refresh updates **configuration values**; refresh scope updates **beans**; rotation is complete only when **running clients actually use the new credential** and the old credential has been safely revoked. Design and test all three layers, especially when running multiple instances.
