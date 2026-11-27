# Implementing PropertySourceLocator for a Custom Configuration Source

> **Chapter:** Custom Configuration Sources  
> **Module:** SPRING_CLOUD_CORE

When an application's configuration does not come solely from `application.yml`, environment variables, or Spring Cloud Config Server, the development team may need to read properties from a custom source: an internal configuration service, a per-tenant parameter store, a feature management system, or an environment-based configuration API. In Spring Cloud's traditional bootstrap model, **`PropertySourceLocator`** is the extension point that integrates that source into the `Environment` before the main ApplicationContext finishes initializing.

Implementing a locator requires understanding when it runs, how to register bootstrap configuration, how to return a `PropertySource`, precedence ordering, and the policy when the remote source fails. This lesson builds a testable example while distinguishing the legacy bootstrap locator from modern Spring Boot's Config Data extension mechanism.

## 1. What Problem Does `PropertySourceLocator` Solve?

Spring Boot represents configuration through `Environment`. Each `PropertySource` provides values by property name, such as:

- `application.yml` and `application-{profile}.yml`.
- Environment variables and Java system properties.
- Command-line arguments.
- Property sources loaded by Spring Cloud Config Client.
- Property sources added by the application or an integration library.

A custom configuration source may fetch data from a proprietary API, yet needs to bring that data into the same property model so Spring components can consume it uniformly. `PropertySourceLocator` provides the contract:

~~~java
public interface PropertySourceLocator {
    PropertySource<?> locate(Environment environment);
}
~~~

Spring Cloud invokes `locate` with the existing `Environment` during the bootstrap phase. The locator can read properties identifying the application, profiles, or tenant, call the custom configuration source's client, and then return a `PropertySource<?>`. Those values are added to the configuration environment so components initialized later can resolve them.

Some examples of data that can be fetched from a custom source:

| Source | Example data | Purpose |
| --- | --- | --- |
| Tenant settings API | Feature limits, region codes, per-tenant settings | Use the same artifact across multiple tenants |
| Internal parameter service | Dependency endpoints, timeouts, quotas | Centralized parameter management |
| Environment metadata service | Cluster name, zone, deployment ring | Adjust behavior by environment |
| Feature configuration service | Application-level feature states | Provide startup configuration for features |

A locator only solves **putting properties into the Environment**. It does not automatically create an admin UI, user authorization, dynamic configuration synchronization, or guarantee that every bean can refresh when source data changes.

## 2. Bootstrap Lifecycle and Where the Locator Fits

In the legacy model, Spring Cloud creates the bootstrap context before the main ApplicationContext. The bootstrap context can instantiate configuration beans and invoke registered locators. Property sources returned by locators are added to the environment for the main application to use during initialization.

~~~mermaid
flowchart TB
    A["Spring Boot process starts"]
    A --> B["Create bootstrap context"]
    B --> C["Register BootstrapConfiguration"]
    C --> D["Initialize PropertySourceLocator"]
    D --> E["locate(Environment)"]
    E --> F["Read application/profile/tenant"]
    F --> G["Client queries custom configuration source"]
    G --> H["MapPropertySource / CompositePropertySource"]
    H --> I["Add property source to Environment"]
    I --> J["Initialize main ApplicationContext"]
    J --> K["Bind @ConfigurationProperties and create beans"]
~~~

The critical point is that the locator runs **earlier than many business beans**. Therefore, it must not depend on a service that is only created in the main ApplicationContext. Dependencies required by the locator must be provided in the bootstrap context or initialized independently there.

### 2.1. When Is the Bootstrap Context Activated?

In Spring Cloud applications using the legacy mechanism, bootstrap is typically enabled via the `spring-cloud-starter-bootstrap` dependency or the `spring.cloud.bootstrap.enabled=true` flag supplied early enough according to the version. Merely creating a `bootstrap.yml` file does not mean the bootstrap context is guaranteed to run in all modern setups.

When bootstrap is not enabled, having a class implementing `PropertySourceLocator` on the classpath does not automatically guarantee Spring Cloud will invoke it. Verify dependencies, registration, and startup logs.

### 2.2. A Locator Is Not a Config Data Loader

Spring Boot 2.4 and later include the Config Data API to load configuration sources via `spring.config.import`. Spring Cloud Config Client integrates with Config Data using locations like `configserver:`. This is a different extension path from legacy bootstrap.

| Extension point | Phase | Suitable use case |
| --- | --- | --- |
| `PropertySourceLocator` | Spring Cloud legacy bootstrap context | Integrating a configuration source into the legacy bootstrap model |
| `ConfigDataLocationResolver` and `ConfigDataLoader` | Spring Boot Config Data | Creating a custom location declarable via `spring.config.import` |
| `EnvironmentPostProcessor` | Spring Boot Environment preparation phase | Adding to or transforming the Environment within supported extension boundaries |

If the project already uses Config Data and wants to declare a custom source like `vaultx:` or `tenantconfig:` in `spring.config.import`, look into `ConfigDataLocationResolver`/`ConfigDataLoader`. Do not treat `PropertySourceLocator` as a drop-in replacement for all modern extension points.

## 3. Registering BootstrapConfiguration

A bootstrap configuration class must be discovered by Spring Cloud. In the traditional bootstrap model, a library or application registers that class in `META-INF/spring.factories` under the `org.springframework.cloud.bootstrap.BootstrapConfiguration` key.

Example file:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.example.order.bootstrap.TenantBootstrapConfiguration
~~~

Configuration class:

~~~java
package com.example.order.bootstrap;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TenantBootstrapConfiguration {

    @Bean
    PropertySourceLocator tenantPropertySourceLocator(
            TenantSettingsClient client) {
        return new TenantPropertySourceLocator(client);
    }
}
~~~

In a real project, `TenantSettingsClient` is a component provided by the application or library to call the configuration source. It must be present in the bootstrap context. If this bean depends on beans only created in the main ApplicationContext, split the minimal client into bootstrap configuration or use a standalone implementation.

### 3.1. Contents and Location of spring.factories

The `spring.factories` file must be placed in the exact location:

~~~text
src/main/resources/
  META-INF/
    spring.factories
~~~

If the locator is packaged in a library, the file must be included in that library's JAR. Applications using the library need the corresponding dependency and must enable bootstrap in the way supported by their Spring Cloud version.

Do not place a bootstrap class in a package covered by regular component scanning and assume that suffices to register bootstrap configuration. The bootstrap context has its own discovery mechanism. Inspect the built JAR contents if the application fails to find the locator.

Version note: the legacy bootstrap registration mechanism relies on `spring.factories` for `BootstrapConfiguration`. Spring Boot's auto-configuration mechanism in newer versions may use different metadata, but that does not replace the legacy bootstrap registration mechanism.

## 4. Designing a Client for the Custom Configuration Source

Suppose the system has a Tenant Settings Service that returns configuration by application name, tenant, and profiles. Decouple network calls from the locator with an interface:

~~~java
import java.util.Map;

public interface TenantSettingsClient {

    Map<String, Object> fetch(
            String applicationName,
            String tenantId,
            String[] profiles);
}
~~~

This interface keeps the locator independent of a specific HTTP library. During testing, a fake or mock client can be used. In a real implementation, the client can use `WebClient`, `RestClient`, or an HTTP client appropriate for the Spring version.

An example response:

~~~json
{
  "catalog.client.base-url": "https://catalog.tenant-a.internal",
  "catalog.client.read-timeout": "2s",
  "feature.new-checkout.enabled": true,
  "tenant.region": "ap-southeast"
}
~~~

Keys in the response should match the property names the application intends to bind. If using a dedicated namespace such as `catalog.client`, the application can bind with `@ConfigurationProperties(prefix = "catalog.client")` after the property source has been loaded.

Do not return arbitrary unconvertible objects or unnecessary sensitive data. Define the response schema, data types, contract versioning, and how unrecognized keys are handled.

### 4.1. Keep Credentials Out of Source Code

A client calling the configuration service may require a token or certificate. Credentials must come from an appropriate secure source at bootstrap, such as mounted secrets or platform-provided environment variables. Never hard-code tokens in `spring.factories`, committed YAML files, or Java code.

Also never log the entire response, request headers, or property map. A configuration source may contain passwords, tokens, internal URLs, and infrastructure details.

## 5. Implementing the Locator

Below is an illustrative implementation. It reads the application name and tenant ID from the Environment, calls the client, and returns a `MapPropertySource`.

~~~java
package com.example.order.bootstrap;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.util.StringUtils;

public final class TenantPropertySourceLocator
        implements PropertySourceLocator, Ordered {

    private final TenantSettingsClient client;

    public TenantPropertySourceLocator(TenantSettingsClient client) {
        this.client = client;
    }

    @Override
    public PropertySource<?> locate(Environment environment) {
        String applicationName = environment.getProperty(
                "spring.application.name", "unknown-application");

        String tenantId = environment.getProperty("platform.tenant-id");

        if (!StringUtils.hasText(tenantId)) {
            return null;
        }

        String[] profiles = environment.getActiveProfiles();
        Map<String, Object> values =
                client.fetch(applicationName, tenantId, profiles);

        if (values == null || values.isEmpty()) {
            return null;
        }

        Map<String, Object> copy = new LinkedHashMap<>(values);

        return new MapPropertySource(
                "tenantSettings:" + tenantId,
                copy);
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
~~~

Key points to note:

- `locate(Environment)` receives the current environment to read application and tenant identifiers.
- `spring.application.name` has a default value in the example so logs/diagnostics do not hit null; a real project can choose to require it and fail-fast.
- `platform.tenant-id` is an application-defined property. It must be present from a source loaded before the locator, such as an environment variable or system property.
- `getActiveProfiles()` returns the profiles active at the time the locator is called. If a profile is added later by another source, the current locator does not automatically rerun just because profiles changed.
- `MapPropertySource` provides the key/value map to Spring.
- The property source name should be meaningful and stable to make Environment inspection easy.
- `Ordered` lets you define locator ordering when multiple locators exist. The final ordering among property sources also depends on how bootstrap integrates them and other sources; verify the effective value instead of guessing.

### 5.1. Why Return null When There Is No Tenant?

In the example, the tenant ID is the condition for calling the configuration source. If the application does not declare a tenant, the locator returns null to indicate it has no additional property source.

This is a policy choice, not a rule for every system. If a tenant is mandatory in production, missing the tenant should fail startup with a clear configuration error rather than silently skipping the source. If the source is only used in certain environments, it can be skipped locally while required in staging/production.

Example mandatory check:

~~~java
if (!StringUtils.hasText(tenantId)) {
    throw new IllegalStateException(
            "platform.tenant-id is required for remote tenant configuration");
}
~~~

Do not use `return null` to mask authentication or network errors when remote data is required.

## 6. Error Policy and Availability

`PropertySourceLocator` typically runs synchronously during initialization. Therefore, a hanging remote call can prolong startup or prevent the application from starting. Client design must include timeouts and a clear error policy.

| Configuration source state | Source is required | Source is optional |
| --- | --- | --- |
| Returns valid data | Load property source | Load property source |
| No configuration for tenant | Throw an error if missing data is invalid | Skip or return an empty source per convention |
| Timeout/connection error | Fail-fast with a clear message | Can fall back if a safe fallback is defined |
| Invalid response schema | Throw an error to avoid using bad config | Skip only if the data is truly optional and log a warning |
| Missing tenant ID | Fail-fast | Skip if this environment does not need tenant config |

Implementation principles:

1. **Bounded timeouts:** configure connect timeout and response/read timeout; never let startup wait indefinitely.
2. **Bounded retries:** only retry transient errors, with backoff and a total time limit.
3. **No blind retries:** configuration read requests are typically idempotent, but load on the Config Service must still be bounded.
4. **Fail-fast when data is required:** do not start with missing configuration that can cause business errors or security issues.
5. **Intentional fallback:** only use local values if they are an approved fallback plan.
6. **Helpful error messages:** log application, tenant, and error type; never log tokens or secret values.
7. **Do not swallow all exceptions:** catch and translate errors at the client boundary when needed, while preserving the underlying cause for diagnostics.

For example, the client can throw a dedicated exception:

~~~java
public final class TenantSettingsUnavailableException
        extends RuntimeException {

    public TenantSettingsUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The locator or bootstrap flow can let this error fail startup if the source is required. For an optional source, it can catch the exact specified exception type, log a secret-free warning, and return null. Do not catch generic `Exception` and silently treat every error as "no configuration".

## 7. Precedence and Property Conflicts

When multiple sources declare the same key, Spring resolves the value according to the property source order in the Environment. A locator may return a source containing keys that overlap with `application.yml` or Config Server. Therefore, clearly define who owns each key and which source has override authority.

Example:

`application.yml`:

~~~yaml
catalog:
  client:
    read-timeout: 5s
    max-attempts: 2
~~~

The tenant source returns:

~~~json
{
  "catalog.client.read-timeout": "2s",
  "catalog.client.max-attempts": 3
}
~~~

The effective value received by `@ConfigurationProperties` depends on the order of property sources. Do not assume that a locator always has the highest or lowest priority across all versions/configurations. Properties controlling Spring Cloud Config Server overrides should also not be applied mechanically to a custom locator.

Verify by reading the effective value from `Environment` or the bound bean in tests. If there are multiple locators, define order via `Ordered` and assign distinct property source names.

### 7.1. Avoiding Unintended Overwrites of Sensitive Configuration

Do not allow a tenant source to arbitrarily override any key. You can restrict the allowed set of returned keys:

~~~java
private static final Set<String> ALLOWED_PREFIXES = Set.of(
        "catalog.client.",
        "feature.",
        "tenant."
);
~~~

Before creating the property source, check that each key falls within an allowed namespace. Keys such as datasource passwords, signing keys, tokens, or security policies require a separate management workflow and strict access control.

Another option is to allow the remote source to supply only a dedicated configuration object, such as `tenant.features.*`, instead of having authority to override the entire Environment. The smaller the scope, the easier conflicts are to control.

## 8. Testing PropertySourceLocator

Test the locator in isolation first, then run bootstrap context integration tests. Isolated tests verify reading from the Environment, calling the client, and creating the property source without starting a Config Server.

Example using `MockEnvironment` and a fake client:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MockEnvironment;
import org.springframework.core.env.PropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class TenantPropertySourceLocatorTest {

    @Test
    void createsPropertySourceForConfiguredTenant() {
        TenantSettingsClient client = (application, tenant, profiles) ->
                Map.of(
                        "tenant.region", "ap-southeast",
                        "catalog.client.read-timeout", "2s"
                );

        TenantPropertySourceLocator locator =
                new TenantPropertySourceLocator(client);

        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.application.name", "order-service")
                .withProperty("platform.tenant-id", "tenant-a");

        environment.setActiveProfiles("production");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source).isInstanceOf(MapPropertySource.class);
        assertThat(source.getProperty("tenant.region"))
                .isEqualTo("ap-southeast");
        assertThat(source.getProperty("catalog.client.read-timeout"))
                .isEqualTo("2s");
    }
}
~~~

The test above uses a fake client to focus on locator logic. In a real project, add tests for these cases:

| Case | Expected outcome |
| --- | --- |
| Tenant ID present, client returns map | Property source exists with expected keys/values |
| Tenant ID missing and source is optional | Locator does not create a source |
| Tenant ID missing and source is required | Startup fails with a clear error |
| Client returns empty map | No source added or handled per chosen convention |
| Client timeout | Fail-fast/fallback applied according to policy |
| Response has key outside allowlist | Reject or strip key according to policy |
| Two locators provide the same key | Effective value follows designed ordering |
| Profile changes | Verify whether locator is called again or requires restart per actual lifecycle |

### 8.1. Bootstrap Integration Testing

Unit tests do not verify that `spring.factories` has been packaged and the bootstrap context actually discovers the configuration. You need an integration test or smoke test that starts the application with bootstrap enabled, then checks:

- The locator is created in the bootstrap context.
- The client is injected properly.
- The config source appears in the main application's Environment.
- `@ConfigurationProperties` binds the keys provided by the locator.
- No unexpected remote requests are made.
- Errors when a required source is unreachable are reported properly.

If the locator resides in a library, verify the JAR contains `META-INF/spring.factories` and the exact class name. This is a packaging mistake easily missed when unit tests run directly inside the module.

## 9. Locators and Configuration Refresh

`PropertySourceLocator` is not a polling or subscription mechanism. The locator is called during the bootstrap lifecycle; changes to the configuration source afterward do not mean the locator automatically keeps re-running.

If configuration needs to change while the application is running, choose a separate mechanism, such as:

- Using Spring Cloud Config and the appropriate refresh events.
- Building an endpoint/event to update the configuration source and manage bean lifecycles.
- Using a dedicated feature flag service if the goal is dynamic feature toggling.
- Restarting or performing a rolling deploy if changes affect configuration that cannot be safely applied at runtime.

Spring Cloud Context provides `@RefreshScope` for certain beans that can be recreated on refresh. However, refreshing property sources and having beans pick up new values are two separate parts that must be verified individually. A legacy locator does not automatically provide an event channel or refresh policy for a custom source.

Do not use a synchronous bootstrap locator to build a dynamic configuration system by continuously calling APIs. If frequent updates are needed, use a mechanism designed for runtime updates with security, observability, and rate control.

## 10. Security and Operations

A custom configuration source may contain internal endpoints, feature flags, tenant metadata, and secrets. Therefore, controls are required on both the client and server sides.

- **Source authentication:** use TLS and an appropriate service-to-service authentication mechanism.
- **Per-tenant authorization:** the tenant ID sent by the client must be authenticated; do not trust a tenant ID from a user request if it determines startup configuration.
- **Key restriction:** only accept namespaces the application permits.
- **Secret protection:** do not log payloads, expose them via Actuator, or include them in exception messages.
- **Timeouts and capacity:** limit connections, response times, and concurrent requests to the config service.
- **Observability:** record configuration load duration, success/failure status, and tenant/app/profile at a safe metadata level.
- **Version control:** define the response schema and version so server-side changes do not unexpectedly break startup of older clients.
- **Fallback:** explicitly document which values are permitted when the remote source is unavailable; avoid silent fallback for required configuration.

You can record metrics such as locator invocation count, load duration, error count by type, and fallback count. Avoid using unbounded tenant IDs as metric labels if that creates excessive cardinality; use structured logs or normalized labels instead.

## 11. Common Mistakes

1. **Locator is not invoked:** bootstrap is not enabled, missing the proper starter/flag, or bootstrap configuration is not registered.
2. **Configuration class not found:** `spring.factories` has the wrong key, wrong class name, or was not packaged into the JAR.
3. **Cannot inject client:** the client only exists in the main ApplicationContext while the locator is created in the bootstrap context.
4. **Calling Config Service takes too long:** missing connect/read timeouts or unbounded retries.
5. **Remote values do not override as expected:** property source order and locator order were not checked.
6. **Custom source accidentally overrides unintended keys:** missing namespace restriction or undefined property ownership.
7. **Source changes but beans do not update:** locators do not poll automatically; a separate refresh mechanism or restart is required.
8. **Enabling legacy locator alongside Config Data import:** can create two configuration loading paths; pick the extension point matching the mechanism in use.
9. **Secrets leaked in logs:** logging the full map or exceptions from the HTTP client; log only non-sensitive metadata.
10. **Tests pass but production fails to discover the locator:** forgot to verify the JAR and real bootstrap context.

## 12. Choosing the Right Extension Point

Before implementing, answer three questions:

| Question | If the answer is... | Recommended direction |
| --- | --- | --- |
| Does the application use the legacy bootstrap context? | Yes, and needs to load the source before the main context | `PropertySourceLocator` |
| Does the custom source need to be declared via `spring.config.import`? | Yes, the application uses Config Data | `ConfigDataLocationResolver` and `ConfigDataLoader` |
| Only need to add some properties during Spring Boot Environment preparation? | Yes, no custom location model needed | Consider `EnvironmentPostProcessor` and its execution order |

Do not choose an extension point just because the interface name is familiar. Cross-check the Spring Boot/Spring Cloud versions, initialization lifecycle, error-handling capabilities, and runtime update requirements.

**Key takeaway:** `PropertySourceLocator` is Spring Cloud's legacy bootstrap contract for deriving a `PropertySource` from `Environment` and adding it during application startup. Proper implementation requires registering `BootstrapConfiguration`, supplying dependencies inside the bootstrap context, configuring clear timeouts and error policies, restricting overridable keys, and testing both the locator and packaging. For new custom sources in Config Data, use the corresponding resolver/loader instead of inadvertently introducing another bootstrap path.
