# PropertySourceLocator Runs at the Wrong Time or Is Invoked Repeatedly

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_CORE** module. `PropertySourceLocator` is an extension point of Spring Cloud bootstrap that allows an application to add a `PropertySource` from Config Server, a secret/configuration service, or an external data source. When a locator is invoked before profiles, the application name, or bootstrap settings are ready, the application may load the wrong configuration. When a locator is invoked multiple times, the application may send multiple requests to the configuration source, produce duplicate logs, increase startup time, or repeat side effects if the implementation is unsafe.

Not every repeated invocation is a bug. In modern release trains, Spring Cloud can invoke locators in two phases: first to fetch profile-less property sources so they have an opportunity to activate profiles, and next after the main application context starts with active profiles determined. Spring Boot's Config Data can also make multiple requests to Config Server when using `spring.config.import`. Additionally, context hierarchies and tests can create multiple independent bootstrap contexts.

This lesson helps you distinguish those mechanisms, determine whether a locator is running in the bootstrap or main context, inspect profiles and property source order, design locators to be safe when re-invoked, and choose the right registration approach for Config Data or legacy bootstrap.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain the role of `PropertySourceLocator` in Spring Cloud bootstrap.
2. Distinguish the bootstrap context, main application context, and Config Data loading.
3. Explain why a locator can be invoked twice in modern release trains.
4. Distinguish a profile-less fetch from a fetch with active profiles.
5. Understand the purpose and scope of `spring.cloud.config.initialize-on-context-refresh`.
6. Identify when an application uses legacy bootstrap, Config Data, or both.
7. Detect multiple bootstrap contexts in a context hierarchy.
8. Register custom bootstrap configurations via `META-INF/spring.factories`.
9. Prevent bootstrap configurations from being component-scanned into the main application context.
10. Design an idempotent locator without side effects and without depending on beans that only exist in the main context.
11. Handle `spring.application.name`, active profiles, labels, and property source precedence.
12. Diagnose errors caused by `@Order` ordering or duplicate property source names.
13. Write unit tests for locators and integration tests for the bootstrap lifecycle.
14. Distinguish locator invocation at startup from locator re-invocation during runtime refresh.
15. Use logs and dependency inspection to tell valid fetches apart from abnormal fetches.

## 2. Where Does PropertySourceLocator Sit in the Application Lifecycle?

### 2.1. Bootstrap Context and Main Application Context

In legacy bootstrap, Spring Cloud creates a bootstrap context as the parent of the main application context. The bootstrap context is responsible for loading external configuration and preparing property sources before the main context is initialized.

High-level flow:

~~~mermaid
flowchart TD
    A["SpringApplication starts"] --> B["Create bootstrap context"]
    B --> C["Read BootstrapConfiguration from spring.factories"]
    C --> D["Create PropertySourceLocator beans"]
    D --> E["Run locator bootstrap phase"]
    E --> F["Add bootstrap PropertySources to Environment"]
    F --> G["Create main application context"]
    G --> H["Determine active profiles"]
    H --> I["Run locator phase with main context Environment"]
    I --> J["Finalize Environment and create application beans"]
~~~

The diagram illustrates the common two-phase idea in versions supporting profile-aware bootstrap. Exact timing depends on the Spring Cloud release train and bootstrap configuration. Do not use this diagram to conclude that every application always has exactly two calls.

The bootstrap and main contexts can share an `Environment` via Spring Cloud mechanisms, yet they remain two distinct ApplicationContexts. A property source added during bootstrap can be inherited by the main context. A locator receives the `Environment` of the context to which it is supplying property sources.

### 2.2. What Does PropertySourceLocator Do?

The `PropertySourceLocator` interface resides in the package:

~~~java
org.springframework.cloud.bootstrap.config.PropertySourceLocator
~~~

Its primary contract is:

~~~java
public interface PropertySourceLocator {

    PropertySource<?> locate(Environment environment);
}
~~~

The `locate` method receives the current Environment and returns a PropertySource; it may return `null` if no data is available. The interface also supports `locateCollection` to represent one or more property sources, including child property sources of a CompositePropertySource.

A locator is not an ordinary business bean. It is used during bootstrap to contribute configuration before most beans in the main application context are created.

### 2.3. What Is Inside the Passed-In Environment?

The received Environment already contains the property sources Spring Boot provides for the corresponding context. The locator can read information such as:

- `spring.application.name`.
- `spring.profiles.active` and `Environment.getActiveProfiles()`.
- Config labels or tenant selectors already present from bootstrap/local settings.
- System properties and environment variables needed to locate the configuration source.

However, do not assume every remote value already exists on the first invocation. One purpose of two-phase loading is to allow the first fetch to return properties that activate profiles, and the subsequent fetch to retrieve profile-specific configuration.

## 3. Why Is the Locator Called Twice?

### 3.1. Profile-Aware Two-Phase Behavior Is Expected

In modern release trains, Spring Cloud documentation describes `PropertySourceLocators` being invoked twice:

1. **First fetch:** retrieves property sources before active profiles are resolved from remote config. These property sources may contain `spring.profiles.active` to activate profiles.
2. **Second fetch:** after the main application context starts, the locator is invoked again with the resolved active profiles to find additional profile-matching property sources.

For example, Config Server returns default configuration:

~~~yaml
spring:
  profiles:
    active: production

app:
  feature:
    mode: safe-default
~~~

Once the `production` profile is activated, the subsequent fetch can retrieve the corresponding property source:

~~~yaml
app:
  feature:
    mode: production
~~~

Therefore, two log entries from the same locator with different profile lists are usually normal.

### 3.2. Differences Across Release Trains

Current Spring Cloud Commons documentation explicitly notes that prior to Spring Cloud 2022.0.3, PropertySourceLocators (including the Config Client locator) ran in the main application context rather than the bootstrap context. You can set `spring.cloud.config.initialize-on-context-refresh=true` in `bootstrap.yml` or `bootstrap.properties` to force locators to run in the bootstrap context.

Older Spring Cloud lines may have different transition milestones and behaviors in their respective release train docs. When troubleshooting, consult the exact BOM in use; do not infer lifecycle behavior solely from the latest version's documentation.

### 3.3. Invocation Count Is Not a Fixed Guarantee for Every Application

The observed call count also depends on:
- The Spring Cloud release train.
- Whether legacy bootstrap is enabled.
- Whether Config Data is used.
- The number of ApplicationContexts in a hierarchy.
- Whether tests create one or multiple contexts.
- Retry mechanisms in the locator or the client it uses.
- Whether the application re-initializes contexts within the same process.

Compare context IDs, active profiles, threads, timestamps, and stack/log markers to identify which phase each invocation belongs to. Do not write production assertions tightly coupled to an assumption that the entire application makes exactly two calls.

### 3.4. Distinguishing from Multiple Config Data Requests

Spring Boot Config Data uses `spring.config.import` to load configuration. Config Client may send an initial request with the `default` profile to discover profiles activated from remote config, then send a subsequent request with the active profiles.

These requests belong to the Config Data loader, not a legacy bootstrap custom `PropertySourceLocator`.

| Indicator | Legacy bootstrap locator | Config Data import |
| --- | --- | --- |
| Mechanism | `PropertySourceLocator` | Config Client's `ConfigDataLocationResolver` / ConfigDataLoader |
| Activation | Bootstrap is enabled and the locator is registered in bootstrap configuration. | `spring.config.import=configserver:` is present. |
| Where configured | `bootstrap.yml` and `spring.factories` per bootstrap mechanism. | `application.yml` or Config Data import location. |
| Multiple fetches | Can have profile-aware two-phase calls and multiple contexts. | Can have multiple requests due to resolving default profile and active profiles. |
| How to handle | Inspect bootstrap lifecycle and custom locator. | Inspect Config Data import, resolver/loader, and profile resolution. |

If logs show two Config Server requests without logs from your custom locator, do not rush to modify `PropertySourceLocator`. Identify the requests generated by the Config Data loader.

## 4. What Does initialize-on-context-refresh Control?

### 4.1. Default Value

Property:

~~~yaml
spring:
  cloud:
    config:
      initialize-on-context-refresh: false
~~~

The default in current Spring Cloud Commons is `false`. This property controls initializing bootstrap configuration on ContextRefreshedEvent. It relates to when locators run in the bootstrap lifecycle.

### 4.2. When to Set true?

In legacy bootstrap, the property can be set in `bootstrap.yml` or `bootstrap.properties`:

~~~yaml
spring:
  cloud:
    config:
      initialize-on-context-refresh: true
~~~

This option forces PropertySourceLocators to execute in the bootstrap context as described by Spring Cloud. It is useful when a property source must be present earlier during main context creation.

### 4.3. It Is Not a Switch to Disable the Second Invocation

Do not use `initialize-on-context-refresh=true` aiming to eliminate the profile-specific fetch. This option adjusts bootstrap initialization timing; profile-aware two-phase behavior must still be understood per the release train in use.

If a locator calls a remote service, make every invocation safe to repeat. If the goal is to reduce request count, optimize fetching, cache by application/profile/label, or redesign the configuration source architecture after pinpointing which requests are redundant.

### 4.4. Place the Property in the Right Location

With legacy bootstrap, place the property in bootstrap configuration:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: inventory-service
  cloud:
    config:
      initialize-on-context-refresh: true
      uri: http://config-server:8888
~~~

If the application only uses Config Data via `spring.config.import`, this bootstrap property is not a switch to control the number of Config Data requests. Verify which mechanism is actually in use before making changes.

## 5. Registering a Custom Locator Properly

### 5.1. Enable Legacy Bootstrap

Bootstrap can be enabled via the `spring-cloud-starter-bootstrap` starter or the `spring.cloud.bootstrap.enabled=true` property passed via system property/environment variable per the corresponding version's documentation.

Gradle example:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-bootstrap")
}
~~~

If dependency management already supplies `spring-cloud-starter-bootstrap`, do not declare a separate version. In a real application, only add the bootstrap starter if the architecture requires legacy bootstrap or a custom PropertySourceLocator.

If enabling bootstrap via property instead of starter, the property must be available before Spring Boot reads application configuration. Example run command:

~~~bash
java -Dspring.cloud.bootstrap.enabled=true -jar inventory-service.jar
~~~

Or pass the `SPRING_CLOUD_BOOTSTRAP_ENABLED=true` environment variable from the runtime. Do not put this property only inside `application.yml` and expect it to enable bootstrap automatically, because that file is processed during the main application config phase.

### 5.2. Register via spring.factories

Create the file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Content:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=com.example.bootstrap.CatalogBootstrapConfiguration
~~~

The `org.springframework.cloud.bootstrap.BootstrapConfiguration` key declares configuration classes used to build the bootstrap context. Multiple classes can be listed, separated by commas.

### 5.3. Prevent Bootstrap Configuration from Being Component-Scanned

Place bootstrap classes in a separate package outside the packages scanned by `@SpringBootApplication` or `@ComponentScan` of the main app.

Example structure:

~~~text
com.example.inventory
  InventoryApplication.java
  service/
  controller/
  config/
com.example.inventorybootstrap
  CatalogBootstrapConfiguration.java
  CustomCatalogPropertySourceLocator.java
src/main/resources/META-INF/spring.factories
~~~

If the same configuration class is loaded into both the bootstrap context and the main context, duplicate beans, double-registered locators, or unexpected dependency lifecycles may occur.

### 5.4. Check Packages and Classpath

When a locator does not run:
- Verify the `META-INF/spring.factories` resource is included in the final artifact.
- Verify the class name in the file has the exact package and class name.
- Verify bootstrap has been enabled.
- Verify the `spring-cloud-context` dependency and compatible release train.
- Verify the configuration class is not component-scanned into the main context.
- Verify multiple `spring.factories` files are not unintentionally declaring the same locator.

## 6. Writing a Locator That Is Safe When Re-Invoked

### 6.1. A Locator Should Be a Repeatable Read Operation

A good locator should:
- Read the application name and active profiles from Environment.
- Call the configuration source with finite timeouts.
- Return an immutable property source or snapshotted data.
- Not write to databases, register services, or publish messages.
- Not mutate Environment directly inside `locate`.
- Not create business beans or hold references to the main application context.
- Not store shared results while ignoring profiles, labels, or tenants.

Because a locator can be invoked repeatedly, any side effect inside this method risks being repeated.

### 6.2. Simple Locator Example

The example below illustrates a locator fetching effective configuration by application and active profiles. `fetchEffectiveProperties` represents application-implemented logic to read a remote configuration source; in the example, it returns a sample map to clarify merging default and profile configurations.

~~~java
package com.example.inventorybootstrap;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

public class CustomCatalogPropertySourceLocator
        implements PropertySourceLocator {

    @Override
    public PropertySource<?> locate(Environment environment) {
        String application =
                environment.getProperty("spring.application.name");

        if (application == null || application.isBlank()) {
            return null;
        }

        List<String> profiles =
                Arrays.asList(environment.getActiveProfiles());

        Map<String, Object> properties =
                fetchEffectiveProperties(application, profiles);

        if (properties.isEmpty()) {
            return null;
        }

        return new MapPropertySource(
                "catalog-" + application,
                properties
        );
    }

    private Map<String, Object> fetchEffectiveProperties(
            String application,
            List<String> profiles) {

        Map<String, Object> result = new LinkedHashMap<>();

        // Default values are always fetched first.
        result.put("catalog.timeout-ms", 2000);
        result.put("catalog.mode", "safe");

        // Specific profile overrides default values.
        if (profiles.contains("production")) {
            result.put("catalog.timeout-ms", 5000);
            result.put("catalog.mode", "production");
        }

        return result;
    }
}
~~~

The locator class in the example above is not component-scanned. It is created as a bean by the bootstrap configuration below, then loaded via `spring.factories`.

### 6.3. Explicit Bootstrap Configuration Example

You can declare the locator as a bean inside a configuration class:

~~~java
package com.example.inventorybootstrap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class CatalogBootstrapConfiguration {

    @Bean
    @Order(Ordered.LOWEST_PRECEDENCE)
    CustomCatalogPropertySourceLocator catalogPropertySourceLocator() {
        return new CustomCatalogPropertySourceLocator();
    }
}
~~~

And register the configuration class in `META-INF/spring.factories`:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=com.example.inventorybootstrap.CatalogBootstrapConfiguration
~~~

Choose one consistent registration method. Do not both component-scan the locator class in the main app and register it in the bootstrap context.

### 6.4. Always Merge Default and Profile-Specific Properties

On subsequent calls, bootstrap property sources are rebuilt based on the Environment and available locators. A locator should return the complete effective property set for the current application/profile, including default/common values and active profile overrides.

Do not return only the profile-specific delta if the configuration source does not guarantee preserving the base source. If the second call returns only `production` keys, default keys absent from the new result may disappear from the composite bootstrap property source.

### 6.5. Caches Must Have Complete Keys

If the configuration source is expensive and caching is needed, the cache key should at minimum distinguish:
- Application name.
- Normalized list of active profiles.
- Config label/revision.
- Tenant or namespace if applicable.
- Credential/configuration request version if it affects the output.

Do not cache solely by application name and reuse the initial result for the profile-aware call. That makes the locator run twice properly yet return the wrong property source in the second phase.

## 7. Diagnosing a Locator Running at the Wrong Time

### 7.1. Required Property Missing During the First Call

Symptoms:
- Locator cannot find `spring.application.name`.
- Config source queries the wrong application.
- Bootstrap URL or credentials are not yet available.
- Locator does not know which profile to use.

The cause is often that the property was placed in the very remote source the locator is trying to query. A locator cannot use a value only obtainable after that query to locate the first request.

Resolution:
1. Place minimal bootstrap identity in environment variables, system properties, or `bootstrap.yml`.
2. Place `spring.application.name` and Config Server URI somewhere available before bootstrap.
3. Let remote config supply the remaining configuration.
4. If profiles are activated from remote config, use the first-phase result to activate profiles and the later phase to fetch profile-specific properties.

### 7.2. Locator Depends on a Main Context Bean

The bootstrap context is created before the main context. Beans declared only in the main app package or created by main context auto-configurations may not exist yet when the locator runs.

Do not inject business services such as repositories, domain services, or clients initialized only in the main context into a bootstrap locator.

Instead:
- Create a minimal bootstrap-specific client.
- Use an HTTP client with explicit timeouts.
- Pass bootstrap credentials from environment/system properties.
- Register required dependencies inside bootstrap configuration.
- Avoid reverse dependencies from bootstrap beans into the main context.

### 7.3. Locator Runs Before Active Profiles Are Set

If profiles are configured in a remote property source, the first fetch may not have those profiles yet. This is why a subsequent fetch phase exists.

If a profile must be known from the very start, set the profile in the local/bootstrap environment:

~~~yaml
spring:
  profiles:
    active: production
~~~

If the profile is activated by remote config, do not force the locator to see that profile on the first call. Inspect the second call and the returned property source.

### 7.4. Locator Runs After the Application Needs the Property

If the main context needs a remote property to decide bean configuration very early, determine whether that property is genuinely needed during bootstrap. With legacy bootstrap, evaluate `spring.cloud.config.initialize-on-context-refresh=true` in `bootstrap.yml` to move locators into the bootstrap phase via the supported mechanism.

If using Config Data, declare `spring.config.import` properly so remote properties participate in Config Data resolution. Do not use legacy properties to fix a Config Data flow they do not control.

## 8. Diagnosing a Locator Invoked More Times Than Expected

### 8.1. Check Which Mechanism Actually Sends Requests

Enable safe logging for:
- `org.springframework.cloud.bootstrap.config.PropertySourceBootstrapConfiguration`.
- The application's custom locator.
- Config Client loader if using `spring.config.import`.

In a custom locator, log non-sensitive metadata:
- Locator name.
- Application name.
- Active profiles.
- Context ID if determinable.
- Timestamp and correlation ID.
- Invocation count in tests.

Do not log tokens, passwords, raw property values, or the entire Environment.

### 8.2. Check Simultaneous Config Data and Legacy Bootstrap

A common cause is an application having all of:
- `spring.config.import=configserver:`.
- `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true`.
- Old `spring.cloud.config.uri` and custom `PropertySourceLocator` configuration.

When both Config Server loading paths are enabled, duplicate requests from two independent mechanisms can occur. Pick one primary configuration model. If you need a custom source in Config Data, consider implementing it via Spring Boot's Config Data extension point instead of keeping an old bootstrap locator for the same source.

### 8.3. Check Context Hierarchy

With `SpringApplicationBuilder`, an application can create parent, child, or sibling contexts. Each context in the hierarchy can have its own bootstrap property sources and, depending on configuration, may query remote sources separately.

Check:
- How many ApplicationContexts are created?
- Which contexts are parent, child, or sibling?
- Which application name does each context use?
- Is the Environment shared?
- Does the locator need to run separately for each child?

Do not use a JVM-wide static counter to conclude a locator is called repeatedly if the application intentionally creates multiple contexts.

### 8.4. Check Tests Creating Multiple Contexts

`@SpringBootTest`, `@ContextConfiguration`, or tests launching multiple `SpringApplication` instances can create multiple contexts in the same JVM. Test isolation, context caching, and context hierarchies affect how many times a locator is initialized.

In integration tests, log the context ID alongside application/profile. If each test class initializes its own context, multiple calls can be completely valid.

### 8.5. Check Client Retries Inside the Locator

If a locator makes HTTP calls to Config Server, Vault, or a custom service, that client may retry on timeout or transient errors. A single `locate` call can generate multiple network requests.

Distinguish:
- How many times `locate` is called.
- How many HTTP requests are sent within one `locate` call.
- How many times contexts/bootstrap are initialized.

Attach a correlation ID to each locate call and a request ID to each outbound request to identify which layer causes repetition.

### 8.6. Check Runtime Refresh Re-Invoking Configuration Sources

A locator call after startup may come from a refresh operation rather than a new startup. When legacy bootstrap is enabled, Spring Cloud creates `LegacyContextRefresher`; when `POST /actuator/refresh` or a refresh event is processed, the refresher reloads bootstrap property sources and can re-invoke PropertySourceLocators.

When bootstrap is disabled, Spring Cloud uses `ConfigDataContextRefresher` to reload configuration via Config Data. This flow uses Config Data's resolvers/loaders; those requests should not be attributed to a custom PropertySourceLocator.

Distinguish the two cases:

| Condition | Selected Refresher | Re-Executed Extension Point |
| --- | --- | --- |
| Legacy bootstrap enabled | `LegacyContextRefresher` | `PropertySourceLocator` in the bootstrap context. |
| Bootstrap disabled, using Config Data | `ConfigDataContextRefresher` | Config Data import/resolver/loader. |

The `spring.cloud.config.initialize-on-context-refresh` property controls when locators initialize in the bootstrap lifecycle. It is not a switch to stop `LegacyContextRefresher` from calling locators during a runtime refresh.

When you see locator logs after the application is already READY, check:
- Whether `POST /actuator/refresh` was called.
- Whether a RefreshEvent came from Spring Cloud Bus or a custom event listener.
- Whether a scheduled job or watcher emits refresh events.
- How many refreshes were triggered in a time window.
- Whether refresh uses LegacyContextRefresher or ConfigDataContextRefresher.

In integration tests, record timestamps, request/correlation IDs, and profiles on each locate; then hit the refresh endpoint once to verify exactly one refresh cycle is observed. Do not assert total process-wide call counts if tests also create multiple contexts or trigger retries.

## 9. Locator Ordering and Property Source Precedence

### 9.1. Use @Order When Multiple Locators Exist

Spring Cloud sorts `PropertySourceLocator` instances by order before executing them. If there are multiple locators, place `@Order` or implement `Ordered` to express an explicit order.

Example:

~~~java
@Bean
@Order(10)
PropertySourceLocator platformDefaultsLocator() {
    return platformDefaultsLocator;
}

@Bean
@Order(20)
PropertySourceLocator serviceOverridesLocator() {
    return serviceOverridesLocator;
}
~~~

Do not let ordering depend on classpath order or component scanning. When two sources contain the same key, write tests verifying the final value and higher-precedence source under the actual configuration.

### 9.2. Property Source Names Must Be Stable and Meaningful

Use a unique, stable, easily recognizable name:

~~~java
return new MapPropertySource(
        "catalog-config-" + application,
        properties
);
~~~

Avoid generating random names with timestamps or UUIDs on every call. Constantly changing names complicate diagnostics, increase the risk of duplicate property sources, and make verifying order difficult.

### 9.3. Remote Property Sources Can Have High Precedence

Bootstrap property sources are usually added with high precedence under bootstrap rules. If you want local configuration to override remote properties, understand `spring.cloud.config.allowOverride`, `overrideNone`, and `overrideSystemProperties`. Some override permissions must be granted by the remote source; they cannot always be enabled solely via local properties.

Do not fix precedence errors by randomly renaming property sources. Verify the property source list, order, and override policy.

## 10. Logging and Observability Tools

### 10.1. Logs Should Show Phase and Profile

Safe log example:

~~~text
locator=CatalogLocator
application=inventory-service
profiles=[]
context=bootstrap
phase=initial
result=property-source-found
~~~

Subsequent call:

~~~text
locator=CatalogLocator
application=inventory-service
profiles=[production]
context=main
phase=profile-specific
result=property-source-found
~~~

The phase label is diagnostic metadata logged by the application; it is not a required Spring Cloud field. Obtain context IDs and profiles from the corresponding Environment or context when available.

### 10.2. Do Not Log Property Values

Property sources may contain passwords, tokens, private keys, database URLs, or internal details. Do not log `PropertySource.toString()`, map values, or the entire Environment in production.

If diagnostics are needed:
- Log property source names.
- Log key counts.
- Log application/profile/label.
- Log non-sensitive revision or config versions.
- Log request durations and outcomes.
- Display only allowlisted keys when necessary.

### 10.3. Inspecting Environment and Property Sources

In development environments, you can inspect:
- Active profiles.
- PropertySource names.
- Values of non-sensitive properties.
- Property origins if supported.

Actuator `/actuator/env` can reveal configuration data. Expose it only in controlled environments, require proper authorization, and never open this endpoint publicly for debugging.

### 10.4. Inspecting the Dependency Tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-starter-bootstrap,org.springframework.cloud:spring-cloud-config-client,org.springframework.cloud:spring-cloud-context
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-starter-bootstrap --configuration runtimeClasspath
~~~

Look for dependencies pulling in the bootstrap starter transitively. Do not remove a dependency solely because it appears in the tree; verify which component needs legacy bootstrap before making changes.

## 11. Testing PropertySourceLocator

### 11.1. Unit Tests by Profile

Unit tests should verify the locator with different Environments:
- No active profiles.
- One profile.
- Multiple profiles.
- Missing application name.
- Empty remote source.
- Configuration source returning an error.
- Two calls with the same Environment returning consistent results.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.core.env.PropertySource;

class CustomCatalogPropertySourceLocatorTests {

    private final CustomCatalogPropertySourceLocator locator =
            new CustomCatalogPropertySourceLocator();

    @Test
    void returnsDefaultPropertiesWithoutActiveProfile() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.application.name", "inventory-service");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source).isNotNull();
        assertThat(source.getProperty("catalog.mode")).isEqualTo("safe");
    }

    @Test
    void returnsProfileSpecificProperties() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.application.name", "inventory-service");
        environment.setActiveProfiles("production");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source.getProperty("catalog.mode"))
                .isEqualTo("production");
    }
}
~~~

This is a unit test for locator logic; it does not prove the bootstrap lifecycle invoked it in two phases. A separate integration test is required for lifecycle behavior.

### 11.2. Integration Test Verifying Two Phases

Create a recording locator in tests that captures:
- Number of method invocations.
- Active profiles on each invocation.
- Application name.
- Context ID or phase marker.
- Invocation timestamps.

When running against a release train supporting two phases, verify the first call retrieves base properties and the subsequent call receives profiles activated by those base properties. Do not assert a single hardcoded number across all context hierarchies or retry scenarios.

### 11.3. Idempotency Tests

Invoke the locator twice with the same Environment and verify:
- Equivalent configuration results.
- No duplicate records/database rows created.
- No events or messages emitted.
- No repeated service registrations.
- No shared state mutated outside controlled caches.

If a locator must trigger a side effect, move that side effect to a lifecycle hook with explicit once-only semantics rather than placing it in `locate`.

### 11.4. Context Hierarchy Tests

Create parent/child contexts with different application names or profiles if the real application uses a hierarchy. Verify:
- Which locators are invoked in each context.
- Whether the child inherits the parent's property sources.
- Whether same-named property sources are replaced according to Spring rules.
- Whether the child's application name/profile queries a separate remote source.

### 11.5. Testing Config Data and Bootstrap Separately

If the application is migrating:
1. Test Config Data import in one application profile.
2. Test the legacy bootstrap locator in a separate profile.
3. Test when both are enabled to detect duplicate requests.
4. Verify only the chosen mechanism is used in the final deployment.

Do not rely on a locator unit test to claim the Config Data loader is working.

## 12. Common Symptoms

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Locator is never called. | Bootstrap not enabled or spring.factories not read. | Check starter/property, resource inside JAR, and BootstrapConfiguration key. |
| Locator is called yet application name is empty. | spring.application.name exists only in remote config. | Set application name in local/bootstrap environment. |
| First call has no profile. | This is the phase fetching base properties to activate profiles. | Inspect the subsequent call; do not treat the first call as an error. |
| Locator called twice with different profiles. | Spring Cloud's profile-aware two-phase behavior. | Ensure locator is idempotent and returns full effective properties. |
| Multiple HTTP requests occur yet locator logs only once. | Client inside locator retries or a request was redirected. | Attach request IDs in HTTP client and measure retries. |
| Config Server called twice even without custom locator logs. | Config Data profile resolution. | Check spring.config.import and ConfigData loader. |
| Config Server called from both bootstrap and Config Data. | Both legacy bootstrap and Config Data are configured. | Choose one primary mechanism; remove duplicate loading path after migration verification. |
| Locator runs before bean dependencies are ready. | Bean exists only in main context. | Move required dependencies to bootstrap config or use a minimal client. |
| Profile-specific properties lost after second call. | Locator returns only delta instead of base + profile merged source. | Return the complete effective property set for the current profile. |
| Two locators override same key unpredictably. | Missing @Order or undefined precedence. | Declare order and write property source precedence tests. |
| Property source appears under multiple different names. | Source name generated randomly on each locate call. | Use a stable name per application/source. |
| Locator runs multiple times in tests. | Multiple ApplicationContexts or context hierarchies created. | Log context ID and separate counts per context. |
| Locator unexpectedly runs in main context. | Bootstrap configuration component-scanned or timing differs by release train. | Use a separate bootstrap package and check initialize-on-context-refresh. |
| Locator invoked again after app is READY. | POST /actuator/refresh, RefreshEvent, or Bus refresh event triggers LegacyContextRefresher. | Inspect refresh source and check whether LegacyContextRefresher or ConfigDataContextRefresher is used. |
| Changing property in bootstrap.yml has no effect. | Bootstrap file not loaded or bootstrap not enabled. | Verify legacy bootstrap activation and file location. |
| Production profile is not fetched. | Profile not activated in first phase or locator ignores active profiles. | Check spring.profiles.active, Environment, and second fetch phase. |
| Slow startup caused by locator. | Network call without timeouts or excessive retries. | Configure connect/read timeouts, retry budget, and duration metrics. |
| Locator causes duplicate database rows. | locate() has side effects and is re-invoked. | Switch to read-only/idempotent operation; move side effects to a dedicated lifecycle hook. |
| Custom config does not appear in Environment. | Locator returns null/empty, PropertySource replaced, or wrong precedence order. | Log source name/key count and inspect property source order in tests. |

## 13. Ordered Diagnostic Procedure

1. **Identify versions.** Record Spring Boot version and the running Spring Cloud release train/BOM.
2. **Identify mechanism.** Check `spring.config.import`, bootstrap starter, and `spring.cloud.bootstrap.enabled`.
3. **Determine context count.** Record parent/child context IDs and how many times SpringApplication is initialized.
4. **Instrument each locate call.** Log application name, active profiles, and timestamp.
5. **Separate requests from method calls.** Add a request ID in the locator's HTTP client.
6. **Inspect property sources.** Log source names and key counts, never values.
7. **Check registration.** Verify spring.factories and component scan packages.
8. **Check timing.** If an early bootstrap phase is required, evaluate initialize-on-context-refresh in bootstrap config.
9. **Check ordering.** Verify @Order and property source precedence.
10. **Retest.** Run unit tests, two-phase integration tests, and context hierarchy tests if used by the application.

## 14. Design and Operational Principles

1. **Treat locate as a repeatable operation.** Do not assume it is invoked only once.
2. **Separate fetches by profile.** The first call may have no profiles; subsequent calls may have activated profiles.
3. **Return complete effective configuration.** Later phases must retain base values and apply profile overrides.
4. **Keep locators read-only.** Never write to databases, emit messages, or register services inside locate.
5. **Set timeouts for remote sources.** Do not let bootstrap hang indefinitely on a config endpoint.
6. **Limit retries.** Distinguish transient errors from wrong credentials/profiles/labels.
7. **Use caches with complete keys.** Application, profile, label, and tenant must be part of the cache key when they affect results.
8. **Keep bootstrap configuration minimal.** Include only information needed to locate configuration sources.
9. **Do not depend on main context beans.** Bootstrap runs before most business beans.
10. **Register in exactly one place.** Avoid both component scanning and bootstrap registration.
11. **Set @Order intentionally.** Test key collisions and property source precedence.
12. **Distinguish Config Data from bootstrap.** The two mechanisms have different lifecycles and extension models.
13. **Log safely.** Log only app/profile/context/source metadata.
14. **Cross-check the release train.** Invocation timing and behavior can change across Spring Cloud lines.
15. **Test both startup and context hierarchies.** Locator unit tests alone do not prove lifecycle behavior.
16. **Measure fetch timing.** Monitor startup duration, outbound request counts, and retry counts.

## 15. Completion Checklist

- [ ] Can explain the role of PropertySourceLocator.
- [ ] Can distinguish the bootstrap context and main application context.
- [ ] Understand profile-aware two-phase fetching in modern release trains.
- [ ] Can distinguish PropertySourceLocator from Config Data loaders.
- [ ] Know the meaning of spring.cloud.config.initialize-on-context-refresh.
- [ ] Placed bootstrap properties in the right file and at the right time.
- [ ] Checked spring-cloud-starter-bootstrap or spring.cloud.bootstrap.enabled.
- [ ] Registered BootstrapConfiguration in META-INF/spring.factories.
- [ ] Prevented bootstrap configuration from being component-scanned.
- [ ] Read application name and active profiles from Environment.
- [ ] Return complete base properties and profile-specific properties.
- [ ] Designed the locator to be idempotent and free of side effects.
- [ ] Configured timeouts/retries for remote fetches.
- [ ] Used @Order when multiple locators exist.
- [ ] Checked property source names and precedence.
- [ ] Distinguished multiple contexts from multiple locate calls within the same context.
- [ ] Distinguished method invocations from HTTP retries.
- [ ] Added unit tests for profiles and application name.
- [ ] Added integration tests for the bootstrap lifecycle.
- [ ] Verified Config Data and legacy bootstrap are not both configured unintentionally.

**Official documentation to consult for your project version:**

- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, context hierarchy, custom PropertySourceLocator, and profile-aware two-phase invocation.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): defaults and meaning of spring.cloud.config.initialize-on-context-refresh.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, Config First Bootstrap, and multiple requests when resolving default/active profiles.
- [ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java): refreshEnvironment, updateEnvironment, and publishing EnvironmentChangeEvent.
- [RefreshAutoConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/autoconfigure/RefreshAutoConfiguration.java): selecting LegacyContextRefresher when bootstrap is enabled and ConfigDataContextRefresher when bootstrap is disabled.
- [PropertySourceLocator API](https://www.javadoc.io/doc/org.springframework.cloud/spring-cloud-context/latest/org/springframework/cloud/bootstrap/config/PropertySourceLocator.html): locate, locateCollection contracts, and returning null when no property source exists.
- [PropertySourceBootstrapConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/bootstrap/config/PropertySourceBootstrapConfiguration.java): sorting locators, calling locateCollection, adding property sources, and handling ContextRefreshedEvent.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data loading and extending configuration sources without legacy bootstrap.

When you see a PropertySourceLocator invoked repeatedly, first identify the profile and context of each invocation. Two-phase fetching can be expected behavior; real bugs usually stem from locators having side effects, caches missing profile keys, configuring both loading mechanisms simultaneously, or bootstrap configurations being registered in multiple contexts unintentionally.
