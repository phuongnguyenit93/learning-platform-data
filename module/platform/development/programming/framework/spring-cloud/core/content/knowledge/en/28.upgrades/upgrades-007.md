# Checking Rebind Changes, Property Deletion, and Refresh Scope Limits

In a Spring Cloud application, configuration can change after the application has started. Some changes only need rebinding onto a `@ConfigurationProperties` bean; others require recreating the bean because values are read at initialization time; and some changes cannot be applied safely by merely deleting a key from a configuration source.

Three mechanisms are frequently confused: updating `Environment`, rebinding `@ConfigurationProperties`, and refreshing `@RefreshScope` beans. They have different lifecycles:

- `EnvironmentChangeEvent` notifies listeners that one or more keys in `Environment` have changed. Spring Cloud can rebind `@ConfigurationProperties` beans and update logger levels.
- `ConfigurationPropertiesRebinder` updates the state of configuration beans. For a JavaBean with a single no-argument constructor, properties are reset to class-level defaults before rebinding so deleted values are not retained.
- `RefreshScope` manages target beans through proxies and a cache. Upon refresh, the current target is destroyed; the next call creates a new target from the bean definition and current `Environment`.

These differences become especially important during a Spring Cloud upgrade. A bean using constructor binding, a property deleted from Config Server, or a `DataSource` on the non-refreshable list can make post-refresh results differ from what older code assumed.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_CORE** module. Learners will verify configuration changes, validate property-deletion semantics, choose between rebinding and Refresh Scope, identify each mechanism's limits, and build regression tests before upgrading a release train.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish `Environment` changes, `@ConfigurationProperties` rebinding, and `@RefreshScope` target refresh.
2. Explain the roles of `EnvironmentChangeEvent` and `ConfigurationPropertiesRebinder`.
3. Test a changed property being rebound onto a mutable bean.
4. Explain when a deleted property resets to its class-level default.
5. Identify cases where constructor binding or multiple constructors skip resetting to defaults.
6. Distinguish deleting a key from one `PropertySource` versus deleting it from the effective `Environment`.
7. Explain the limitations when deleting properties used by `@RefreshScope` beans.
8. Test destroying and recreating target beans in Refresh Scope.
9. Identify non-refreshable beans such as `HikariDataSource`.
10. Use `extra-refreshable` and `never-reset-nested-types` appropriately.
11. Ensure multi-replica applications receive configuration changes.
12. Design regression tests and safe upgrade procedures per Spring Cloud version.

## 2. Three Mechanisms to Distinguish

### 2.1. Environment Changes

`Environment` is the collection of `PropertySource` instances Spring uses to resolve configuration. A property can come from `application.yml`, environment variables, system properties, Config Server, Vault, or custom application sources.

When a source changes, the resolved value can change:

~~~text
Before:
checkout.endpoint = https://checkout-v1.internal

After:
checkout.endpoint = https://checkout-v2.internal
~~~

Mutating a `Map` or updating Config Server does not automatically ensure that every bean that already read the old value receives the new value. `Environment` is where values are resolved; beans are the objects holding or reading those values.

### 2.2. Rebinding @ConfigurationProperties

A `@ConfigurationProperties` bean typically holds properties bound to fields or setters. Spring Cloud can listen for `EnvironmentChangeEvent` and instruct `ConfigurationPropertiesRebinder` to rebind configuration beans.

Example:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";
    private boolean enabled = false;
    private int timeoutMillis = 1500;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }
}
~~~

If `Environment` provides a new `checkout.endpoint` and an `EnvironmentChangeEvent` is published, the bean can pick up the new value without recreating the entire `ApplicationContext`.

### 2.3. Refresh Scope

`@RefreshScope` is a special scope using proxies and a target cache. Upon refresh, Spring destroys the current target. The proxy remains the object referenced by other components; the next call through the proxy initializes a new target.

~~~mermaid
flowchart TD
    A[Caller] --> B[RefreshScope proxy]
    B --> C{Target in cache?}
    C -->|Yes| D[Current target]
    C -->|No| E[Create new target]
    E --> F[Read current Environment]
    F --> G[Cache new target]
    G --> D
    H[Refresh request] --> I[Destroy cached target]
    I --> C
~~~

This mechanism fits beans that read configuration at initialization time—such as clients holding an endpoint or stateful components needing recreation. It does not refresh every singleton in the application.

## 3. EnvironmentChangeEvent and the Update Flow

### 3.1. The Event Carries the List of Changed Keys

`EnvironmentChangeEvent` holds a set of keys representing the difference between `Environment` before and after an update.

Example:

~~~java
Set<String> changedKeys = Set.of(
        "checkout.endpoint",
        "checkout.timeout-millis"
);

applicationContext.publishEvent(
        new EnvironmentChangeEvent(applicationContext, changedKeys)
);
~~~

Spring Cloud has listeners for this event. Default behaviors include:

- Rebinding `@ConfigurationProperties` beans in the context.
- Updating log levels for properties prefixed with `logging.level`.

The event does not fetch configuration from Config Server by itself. Another component must update `Environment` or invoke the refresh workflow to pull updated sources before the event is published.

### 3.2. Config Client Does Not Poll by Default

Spring Cloud Config Client does not continuously poll Config Server by default for changes. The application needs a trigger mechanism for updates, for example:

- Calling the secured refresh endpoint.
- Using Spring Cloud Bus to broadcast refresh events across instances.
- Integrating an orchestrator or internal event system.
- Calling the `ContextRefresher` API from a managed component.

With multi-replica applications, updating only one instance creates inconsistent state. Spring Cloud Bus can broadcast notifications so all instances receive the same change.

### 3.3. Rebind Typically Processes All Configuration Beans

`ConfigurationPropertiesRebinder` receives `EnvironmentChangeEvent` and rebinds beans under its management. Do not assume that an event containing one key touches only the bean holding that exact key.

Therefore, a configuration bean unrelated to the changed key may still go through the rebind lifecycle. Constructors, setters, nested objects, and callbacks on the bean must be safe when reinitialized or rebound.

### 3.4. Distinguishing the Two Actuator Endpoints

| Endpoint | Primary effect |
| --- | --- |
| `POST /actuator/env` | Updates `Environment`, rebinds `@ConfigurationProperties`, and updates log levels |
| `POST /actuator/refresh` | Reloads bootstrap/context configuration per the active mechanism and refreshes `@RefreshScope` beans |

The two endpoints do not replace each other. If you only need to update a mutable configuration bean, rebinding may suffice. If you need to recreate target beans, Refresh Scope is the relevant mechanism.

The `POST /actuator/env` endpoint must be enabled explicitly via `management.endpoint.env.post.enabled` and restricted to allowed keys via `management.endpoint.env.post.valid-keys-regex`. These endpoints must be protected by authentication, authorization, and appropriate network policies.

## 4. How Mutable Bean Rebinding Works

### 4.1. Reset First, Bind Second

In current Spring Cloud Commons, when a `@ConfigurationProperties` bean is rebound, Spring Cloud first resets properties to class-level defaults and then binds the data currently in `Environment`.

Example:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";

    private int timeoutMillis = 1500;

    // getters and setters
}
~~~

Suppose `Environment` initially contains:

~~~properties
checkout.endpoint=https://checkout-v1.internal
checkout.timeout-millis=2500
~~~

After rebinding, the bean holds:

~~~text
endpoint       = https://checkout-v1.internal
timeoutMillis  = 2500
~~~

If the next update provides:

~~~properties
checkout.endpoint=https://checkout-v2.internal
~~~

and `timeout-millis` is no longer present in the effective `Environment`, the bean resets and rebinds to:

~~~text
endpoint       = https://checkout-v2.internal
timeoutMillis  = 1500
~~~

The value `1500` is the default declared in the class. It is not a generic Spring default.

### 4.2. Resetting Prevents Retaining Stale Values

Without resetting first, fields populated during a previous bind could keep their old values when a property is deleted. In that case, an operator deletes a key in Config Server, yet the application continues using the stale value.

Resetting first returns the bean to a deterministic default state before applying the properties that still exist.

### 4.3. The Single No-Arg Constructor Condition

Resetting to class-level defaults only occurs when the class declares a no-argument constructor as its sole constructor.

Compliant example:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";

    public CheckoutProperties() {
    }

    // getters and setters
}
~~~

If the class has another constructor accepting parameters—even while retaining a no-arg constructor for the framework—the reset step is skipped.

Example:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint;

    public CheckoutProperties() {
        this.endpoint = "https://fallback.internal";
    }

    public CheckoutProperties(HostResolver resolver) {
        this.endpoint = resolver.defaultEndpoint();
    }

    // getters and setters
}
~~~

When multiple constructors exist, instantiating a fresh object via the no-arg constructor might not reproduce the original bean's actual defaults. Spring Cloud skips the reset step to avoid wiping data that no property source ever supplied.

As a consequence, a property removed from `Environment` can retain its previous value on the bean if resetting is skipped. Write dedicated tests for classes with multiple constructors.

### 4.4. Nested Configuration Properties

Resetting can recurse into nested `@ConfigurationProperties` objects, even nested objects without a setter on the parent.

Example:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private Retry retry = new Retry();

    public Retry getRetry() {
        return retry;
    }

    public static class Retry {

        private int maxAttempts = 3;
        private long backoffMillis = 200;

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public long getBackoffMillis() {
            return backoffMillis;
        }

        public void setBackoffMillis(long backoffMillis) {
            this.backoffMillis = backoffMillis;
        }
    }
}
~~~

If a nested object holds internal state, cyclic references, or a library object graph that should not be altered, recursive resetting can be unsafe.

### 4.5. Excluding Nested Types from Resetting

You can configure `spring.cloud.refresh.never-reset-nested-types` to exclude classes or package prefixes from recursive resetting.

~~~yaml
spring:
  cloud:
    refresh:
      never-reset-nested-types:
        - com.example.sdk.ClientState
        - com.example.crypto.
~~~

Type names are matched as prefixes of the fully qualified class name. Only use this setting once you understand the object graph and have a clear reason to preserve nested state. It does not make nested types refresh differently on their own.

## 5. Property Deletion: Three Different Scenarios

### 5.1. Key Deleted from a Higher-Priority PropertySource

Suppose there are two sources:

~~~text
runtime override:
  checkout.timeout-millis = 1000

application.yml:
  checkout.timeout-millis = 2500
~~~

If the key is removed from `runtime override`, `Environment` still finds the value in `application.yml`. The effective value reverts to `2500`.

This is not a property removed from `Environment`. It is a case where a higher-priority source stops supplying the key and resolution falls back to a lower-priority source.

### 5.2. Key Absent from Every Effective Source

If the key is removed from all effective configuration sources, `Environment` can no longer resolve that property. For a mutable bean eligible for reset, rebinding can return the field to its class-level default.

This holds only when:

- A refresh event is published with the relevant key.
- `Environment` was updated before the event was published.
- The bean belongs to the set managed by the rebinder.
- The class has a no-arg constructor as its sole constructor.
- Resetting the property and nested objects is not excluded or failing.
- No lower-priority source continues supplying the key.

### 5.3. Key Deleted, but Class Is Ineligible for Reset

If the class has multiple constructors or resetting cannot reliably construct a default instance, Spring Cloud skips resetting. Rebinding still applies properties remaining in `Environment`, while deleted properties may retain their previous values.

Do not assume every `@ConfigurationProperties` bean automatically reverts to `null` or its default when a key is deleted. Inspect the actual constructor and bean type.

### 5.4. Comparison Examples

| Scenario | Value after rebind |
| --- | --- |
| Key added or changed | Binds the new value |
| Key deleted in higher-priority source, still in lower source | Binds the value from the lower source |
| Key absent from `Environment`, bean eligible for reset | Reverts to class-level default |
| Key absent from `Environment`, bean ineligible for reset | May retain previously bound value |
| Nested type listed in `never-reset` | Nested state preserved per reset exclusion |
| Properties using constructor binding/record | Not refreshed by this rebind mechanism |

## 6. Constructor Binding and Java Records

### 6.1. Constructor-Bound Objects Are Immutable

Spring Boot supports constructor binding for immutable classes and Java records. Example:

~~~java
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        String endpoint,
        int timeoutMillis
) {
}
~~~

This type is constructed via its constructor with bound values. It has no setters to mutate fields like a mutable JavaBean.

### 6.2. Constructor-Bound Properties Are Not Refreshed

Spring Cloud Commons explicitly states that objects using constructor binding—including Java records annotated with `@ConfigurationProperties`—cannot be refreshed via the normal rebind mechanism.

Do not design records expecting `EnvironmentChangeEvent` to instantiate a new instance and swap all references pointing to the old bean. When runtime configuration updates are needed:

- Use a mutable JavaBean designed for rebinding.
- Place the configuration-dependent bean in `@RefreshScope` if appropriate.
- Use a provider holding a configuration snapshot and swap snapshots explicitly.
- Or restart/roll out the `ApplicationContext` when values change.

### 6.3. Choosing Immutable vs. Mutable by Lifecycle

| Need | Suitable design |
| --- | --- |
| Configuration read-only after startup | Constructor binding or record |
| Configuration needing runtime rebind | Mutable `@ConfigurationProperties` |
| Stateful bean needing recreation | `@RefreshScope` |
| New snapshot needing atomic swap | Provider holding an immutable snapshot |
| Changing bean graph or dependencies | Restart/redeploy the application |

Do not sacrifice an immutable design just to enable refresh. If configuration rarely changes, a controlled restart is often easier to reason about.

## 7. Rebinding Does Not Replace the Bean Instance

### 7.1. The Bean Is Mutated In Place

During rebinding, `ConfigurationPropertiesRebinder` resets and rebinds fields on the same instance. It does not simply instantiate a new object and replace all references holding the old bean.

~~~mermaid
sequenceDiagram
    participant Env as Environment
    participant Event as EnvironmentChangeEvent
    participant Rebind as ConfigurationPropertiesRebinder
    participant Bean as CheckoutProperties
    Env->>Event: Publish changed keys
    Event->>Rebind: Notify listener
    Rebind->>Bean: Destroy callbacks
    Rebind->>Bean: Reset fields to defaults
    Rebind->>Bean: Bind current Environment
    Rebind->>Bean: Initialize callbacks
    Note over Bean: Same bean instance, fields changed in place
~~~

This matters for threads reading the bean while rebinding is underway.

### 7.2. Concurrent Rebinds Are Serialized, but Readers Are Not Locked

Spring Cloud serializes concurrent rebind operations on the same bean so two rebinds do not interleave destroy/reset/initialize steps.

However, readers on other threads are not locked under the same mechanism. A thread can read the bean while fields are being updated and observe an intermediate state.

Example:

~~~text
Before rebind:
  endpoint = v1
  timeout  = 1000

During rebind:
  endpoint = default
  timeout  = 1000

After bind:
  endpoint = v2
  timeout  = 2000
~~~

A request reading mid-process could combine an endpoint and a timeout from two different states.

### 7.3. When Is RefreshScope Needed?

If a bean needs a consistent state while configuration changes, `@RefreshScope` provides a proxy and per-bean read/refresh locking. This prevents callers from reading a target while that target is being refreshed.

This guarantee is per bean. Do not treat multiple beans across the entire `ApplicationContext` as an atomic configuration transaction if the application has multiple dependencies changing together.

### 7.4. Do Not Put Dangerous Side Effects in Setters

Setters on `@ConfigurationProperties` can be invoked multiple times during the rebind lifecycle. Setters should not:

- Open new connections without closing old ones.
- Send requests to external systems.
- Write business data.
- Mutate irreversible global state.
- Spawn new threads or schedulers on every bind.

Setters should only update configuration data. Creating or swapping resources needs an explicit lifecycle.

## 8. Limits of Refresh Scope

### 8.1. Proxies and the Target Cache

A `@RefreshScope` bean is accessed through a scoped proxy. The scope acts as a cache of initialized targets. When a cache entry is invalidated, the current target is destroyed and a new target is created on the next invocation.

Destroy and initialize lifecycle callbacks run according to the bean definition. Placeholders or expressions are re-evaluated when the new target is created.

### 8.2. Refreshing One Bean or the Whole Scope

`RefreshScope` provides:

~~~java
refreshScope.refresh("checkoutClient");
~~~

to refresh a specific bean, and:

~~~java
refreshScope.refreshAll();
~~~

to invalidate all targets in the scope.

Bean names must be checked against the actual registered names in `ApplicationContext`. After invalidation, the proxy stays intact; a new target is created only upon the next call.

### 8.3. @RefreshScope on @Configuration Does Not Cover Every @Bean

Annotating a `@Configuration` class with `@RefreshScope` does not mean every `@Bean` declared inside that class automatically belongs to refresh scope.

If another bean depends on those beans, the dependency may keep holding the old instance. If you want dependencies recreated simultaneously, scope the individual beans appropriately or encapsulate the lifecycle in a dedicated factory.

### 8.4. HikariDataSource Is Non-Refreshable by Default

`HikariDataSource` is in Spring Cloud's default `spring.cloud.refresh.never-refreshable` list. Therefore, do not assume changing the JDBC URL or credentials and calling refresh will recreate the Hikari pool.

If you need to swap database connection pools, design a controlled resource replacement or perform a rolling restart of instances. Only modify `never-refreshable` when you thoroughly understand the `DataSource` implementation's lifecycle and compatibility.

### 8.5. extra-refreshable

`spring.cloud.refresh.extra-refreshable` lets you add bean names or classes to be post-processed into refresh scope, which is especially useful when you cannot place `@RefreshScope` directly on library-provided beans.

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable:
        - com.example.partner.LegacyClient
~~~

This is not a universal fix for every immutable object. The bean must be safe to re-instantiate from its bean definition and current dependencies.

### 8.6. never-refreshable

`spring.cloud.refresh.never-refreshable` specifies bean names or classes that must not be refreshed or rebound.

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable:
        - com.zaxxer.hikari.HikariDataSource
        - com.example.crypto.HardwareKeyStore
~~~

Use this list to protect resources or objects with internal state unsuitable for refresh lifecycles. Verify the exact bean names or class names in the version you are running.

### 8.7. Deleted Properties in Refresh Scope

Spring Cloud Commons documents a specific limitation: deleting a configuration value and triggering refresh does not update the property's presence as a new value. The property must remain present for its value to be updated via refresh.

Therefore, do not use key deletion as the sole signal for a `@RefreshScope` bean to transition into a disabled or unconfigured state.

Instead, keep the property and use an explicit value:

~~~yaml
checkout:
  mode: disabled
  endpoint: https://checkout.internal
~~~

Or:

~~~yaml
checkout:
  enabled: false
~~~

The new bean can read the disabled state and stop using the endpoint. This represents the change as a concrete value the application can inspect.

### 8.8. AOT and Native Images

Spring Cloud Context Refresh is not supported for Spring AOT transformations and native images. For those two models, set:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Do not use Refresh Scope as a way to update beans in native images. Use startup configuration, a dedicated runtime data provider, or rolling restarts.

## 9. @Value, Environment, and ConfigurationProperties

### 9.1. @Value in a Standard Singleton

A singleton bean reads properties into fields at initialization:

~~~java
@Component
public class CheckoutClient {

    @Value("${checkout.endpoint}")
    private String endpoint;

    public String endpoint() {
        return endpoint;
    }
}
~~~

This field is not updated automatically just because `EnvironmentChangeEvent` is published. It received its value when the bean was initialized.

### 9.2. @Value with RefreshScope

If the bean uses `@RefreshScope`, a new target is recreated and placeholders are resolved again:

~~~java
@Component
@RefreshScope
public class CheckoutClient {

    @Value("${checkout.endpoint}")
    private String endpoint;

    public String endpoint() {
        return endpoint;
    }
}
~~~

When the target is invalidated and recreated, values are injected from `Environment` at the time the new target initializes.

### 9.3. Reading Environment on Every Call

A component can read `Environment` at call time:

~~~java
@Component
public class CheckoutEndpointProvider {

    private final Environment environment;

    public CheckoutEndpointProvider(Environment environment) {
        this.environment = environment;
    }

    public String currentEndpoint() {
        return environment.getRequiredProperty("checkout.endpoint");
    }
}
~~~

This reads the current value on every call, provided `Environment` has been updated. However, it does not automatically recreate HTTP clients, connection pools, or resources already built from the old endpoint.

### 9.4. Choosing the Right Abstraction

| Configuration reading approach | Updates when `Environment` changes? | Notes |
| --- | --- | --- |
| `@Value` in a singleton | Does not update fields automatically | Requires refreshing target or recreating bean |
| `Environment.getProperty` on each call | Reads current value | Previously created resources do not change automatically |
| Mutable `@ConfigurationProperties` | Can rebind | Pay attention to resetting and concurrency |
| Constructor-bound record | Does not support rebind | Use startup/restart |
| `@RefreshScope` bean | Target is recreated after invalidation | Applies only to beans in the scope |

## 10. Testing Rebind When Properties Change

### 10.1. Preparing a Mutable Configuration Bean

Use a class with a single no-arg constructor and defaults declared on fields:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";

    private int timeoutMillis = 1500;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }
}
~~~

Register the class using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### 10.2. Testing EnvironmentChangeEvent

Integration test example:

~~~java
@SpringBootTest
class CheckoutPropertiesRefreshTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    CheckoutProperties properties;

    @Autowired
    ApplicationContext context;

    @Test
    void rebindsPropertiesAfterEnvironmentChange() {
        Map<String, Object> values = new ConcurrentHashMap<>();

        MapPropertySource runtimeSource =
                new MapPropertySource("runtime-test", values);

        environment.getPropertySources().addFirst(runtimeSource);

        values.put(
                "checkout.endpoint",
                "https://checkout-v2.internal"
        );

        values.put("checkout.timeout-millis", 2500);

        events.publishEvent(
                new EnvironmentChangeEvent(
                        context,
                        Set.of(
                                "checkout.endpoint",
                                "checkout.timeout-millis"
                        )
                )
        );

        assertThat(properties.getEndpoint())
                .isEqualTo("https://checkout-v2.internal");

        assertThat(properties.getTimeoutMillis())
                .isEqualTo(2500);
    }
}
~~~

The test must run in a context where Spring Cloud Context and `ConfigurationPropertiesRebinder` are auto-configured. `MapPropertySource` uses a mutable map so the test can change values inside the same `PropertySource`.

### 10.3. Testing Deleted Properties and Reset to Default

You can extend the test:

~~~java
@Test
void removedPropertyReturnsToClassDefaultWhenBeanCanBeReset() {
    Map<String, Object> values = new ConcurrentHashMap<>();

    MapPropertySource runtimeSource =
            new MapPropertySource("runtime-test", values);

    environment.getPropertySources().addFirst(runtimeSource);

    values.put(
            "checkout.endpoint",
            "https://temporary.internal"
    );

    events.publishEvent(
            new EnvironmentChangeEvent(
                    context,
                    Set.of("checkout.endpoint")
            )
    );

    assertThat(properties.getEndpoint())
            .isEqualTo("https://temporary.internal");

    values.remove("checkout.endpoint");

    events.publishEvent(
            new EnvironmentChangeEvent(
                    context,
                    Set.of("checkout.endpoint")
            )
    );

    assertThat(environment.getProperty("checkout.endpoint"))
            .isNull();

    assertThat(properties.getEndpoint())
            .isEqualTo("https://checkout-default.internal");
}
~~~

This test simulates the rebind listener when a key has genuinely vanished from the effective `Environment`. If a lower-priority `PropertySource` still defines `checkout.endpoint`, the null assertion on `Environment` will fail and the bean will receive that source's value.

### 10.4. Testing Classes with Multiple Constructors

Create a configuration bean with a no-arg constructor and another constructor taking a dependency. Verify that deleting a key does not automatically reset fields to the no-arg constructor's defaults.

Do not write tests assuming that any class with a no-arg constructor will be reset. Spring Cloud's condition is that the no-arg constructor must be the sole declared constructor.

### 10.5. Testing Nested Properties

Create a nested object with its own defaults. Update and then delete a nested property, then verify the value resets properly. If the nested type is listed in `never-reset-nested-types`, verify its state is preserved per policy.

## 11. Testing RefreshScope

### 11.1. A Bean Reading Configuration When Creating Its Target

~~~java
@Component
@RefreshScope
public class CheckoutEndpoint {

    private final String endpoint;
    private final String mode;

    public CheckoutEndpoint(Environment environment) {
        this.endpoint = environment.getProperty(
                "checkout.endpoint",
                "https://checkout-default.internal"
        );

        this.mode = environment.getProperty(
                "checkout.mode",
                "enabled"
        );
    }

    public String endpoint() {
        return endpoint;
    }

    public String mode() {
        return mode;
    }
}
~~~

The bean stores values in its constructor. Thus, when a new target is created, it reads the new configuration from `Environment`.

### 11.2. Testing Target Recreation

~~~java
@SpringBootTest
class CheckoutEndpointRefreshTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    RefreshScope refreshScope;

    @Autowired
    CheckoutEndpoint checkoutEndpoint;

    @Test
    void refreshCreatesTargetWithNewValues() {
        Map<String, Object> values = new ConcurrentHashMap<>();

        MapPropertySource source =
                new MapPropertySource("runtime-test", values);

        environment.getPropertySources().addFirst(source);

        values.put(
                "checkout.endpoint",
                "https://checkout-v2.internal"
        );

        values.put("checkout.mode", "enabled");

        refreshScope.refresh("checkoutEndpoint");

        assertThat(checkoutEndpoint.endpoint())
                .isEqualTo("https://checkout-v2.internal");

        values.put(
                "checkout.endpoint",
                "https://checkout-v3.internal"
        );

        refreshScope.refresh("checkoutEndpoint");

        assertThat(checkoutEndpoint.endpoint())
                .isEqualTo("https://checkout-v3.internal");
    }
}
~~~

This test confirms the proxy stays injected and the target is recreated after the cache entry is invalidated. The bean name `checkoutEndpoint` must match the registered name in the context.

### 11.3. Testing Disabled State via Sentinel

With Refresh Scope, use a still-present property to represent the disabled state:

~~~java
values.put("checkout.mode", "disabled");
refreshScope.refresh("checkoutEndpoint");

assertThat(checkoutEndpoint.mode()).isEqualTo("disabled");
~~~

This is a much safer regression test than deleting `checkout.mode` and expecting the bean to infer the feature was disabled.

### 11.4. Testing Resource Lifecycles

If the target manages HTTP clients, connections, or thread pools, check:

- Destroy callbacks are invoked when the target is refreshed.
- A new target is initialized on the next access.
- The old client is closed.
- In-flight requests can finish per policy.
- Multiple connection pools are not unexpectedly created simultaneously.
- Errors creating a new target are logged and health reflects the appropriate status.

Do not merely assert that a getter returns the new value. A bean can hold the new value while its underlying resource still uses the old configuration.

## 12. Checking Non-Refreshable Beans

### 12.1. HikariDataSource

`HikariDataSource` is a default `DataSource` type in Spring Cloud's `never-refreshable` list. During an upgrade, check whether code expects JDBC URLs, usernames, or passwords to change immediately after refresh.

If so, suitable options are usually:

- Rolling restarts of instances.
- Creating a pool-swapping factory with explicit lifecycle and draining.
- Using another `DataSource` implementation if you have verified it supports the desired lifecycle.

Do not remove Hikari from `never-refreshable` just to make the refresh endpoint report something different. The pool holds active connections and internal threads; unsafe changes can cause connection errors or resource leaks.

### 12.2. Immutable Library Beans

Some beans created by third-party libraries cannot be annotated directly with `@RefreshScope`. You can use `extra-refreshable` if recreating the bean from its bean definition is safe.

Before adding a class to `extra-refreshable`, check:

- Can the constructor run again?
- Are dependencies re-injected properly?
- Are there resources that must be closed?
- Are there side effects during initialization?
- Are threads or schedulers created in the constructor?
- Do other components hold direct references to the bean?

### 12.3. Beans That Should Not Be Refreshed

Place a bean in `never-refreshable` when it holds internal state unsuitable for recreation or rebinding. Current documentation allows declaring bean names or class names in this list.

### 12.4. Do Not Refresh a Bean Just Because It Has Properties

A bean having properties does not mean it needs Refresh Scope. If values only need to be read at startup, use regular configuration and restart on changes. Refresh Scope should apply only to beans whose lifecycle and recreation behavior have been tested.

## 13. Actuator, Security, and Observability

### 13.1. /actuator/env

`POST /actuator/env` can update `Environment` and trigger `@ConfigurationProperties` rebinding and log level updates. To enable `POST`, configure:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: "^(checkout\\.|logging\\.level\\.).*"
~~~

The regex in this example permits updating only keys under `checkout` and `logging.level`. Adjust according to your actual application.

### 13.2. /actuator/refresh

The `refresh` endpoint triggers reloading configuration via `ContextRefresher` and refreshes `@RefreshScope` beans. If an application does not use refresh scope, do not expose the endpoint just because another application does.

### 13.3. /actuator/configprops

The `configprops` endpoint is helpful for verifying values bound into `@ConfigurationProperties` beans. Use it in a protected admin environment and ensure sensitive fields are masked.

### 13.4. RefreshScopeHealthIndicator

Spring Cloud provides `RefreshScopeHealthIndicator` to track errors when a bean fails to re-initialize or rebind after a context refresh. If refresh fails, the health indicator can transition to `DOWN` and surface the relevant exception details.

Monitor health alongside logs, metrics, and rollout state. A refresh request returning HTTP success does not necessarily mean every underlying resource is ready to serve with the new configuration.

### 13.5. Securing Endpoints

Endpoints that mutate `Environment` can allow changing endpoints, log levels, or sensitive configuration. You need to:

- Authenticate callers.
- Enforce role-based authorization.
- Restrict network access.
- Restrict allowed updatable keys.
- Audit the caller, timestamp, and changed keys.
- Never log plaintext secrets.
- Never expose admin endpoints to the public internet.

## 14. Impact When Upgrading Spring Cloud

### 14.1. Check the Exact Release Train

Spring Cloud Commons spans multiple release trains, and semantics can evolve across versions. Before upgrading:

1. Identify the Spring Boot version.
2. Select a compatible Spring Cloud release train.
3. Lock dependencies with the Spring Cloud BOM.
4. Read documentation for that exact version, not only the `current` page.
5. Check configuration metadata and default values.
6. Re-run rebind, deletion, and Refresh Scope tests.

Do not force a newer Spring Cloud version onto an older Spring Boot just because dependencies compile.

### 14.2. Check New or Changed Refresh Properties

Properties to review in configuration:

| Property | Role |
| --- | --- |
| `spring.cloud.refresh.enabled` | Enables/disables refresh auto-configuration |
| `spring.cloud.refresh.extra-refreshable` | Adds beans/classes treated as refreshable |
| `spring.cloud.refresh.never-refreshable` | Beans/classes excluded from refresh or rebind |
| `spring.cloud.refresh.never-reset-nested-types` | Nested types excluded from recursive reset |
| `spring.cloud.refresh.on-restart.enabled` | Refreshes context on JVM restart after checkpoint/restore |
| `management.health.refresh.enabled` | Enables/disables `RefreshScopeHealthIndicator` |

Check the default of each property in `configprops` for your actual release train.

### 14.3. Check ConfigurationProperties Constructors

A change in a configuration class can alter reset behavior without touching any YAML file.

For example, adding a dependency-injecting constructor to a JavaBean that previously had only a no-arg constructor can cause resetting to class defaults to be skipped. When upgrading code or libraries, inspect constructors and how beans are instantiated.

### 14.4. Check Auto-Configured Beans

Dependency changes can alter bean types or implementation classes. For example, a `DataSource` may still be `HikariDataSource` after upgrading even if application code does not declare it directly.

Use `ApplicationContext` or `configprops` to verify actual runtime types, then compare against `never-refreshable`.

### 14.5. Check AOT and Native Images

Context Refresh is not supported for Spring AOT transformations and native images. In those two models, set `spring.cloud.refresh.enabled=false` and do not rely on the refresh endpoint.

When upgrading, verify build-time profiles, the bean graph, and runtime configuration according to the AOT/native model. Use rolling restarts or runtime data providers for changes that must apply to running processes.

## 15. Decision Matrix: Rebind vs. RefreshScope

| Scenario | Rebind `@ConfigurationProperties` | `@RefreshScope` |
| --- | --- | --- |
| Changing a simple timeout value | Usually suitable | Can be used if the bean needs a new target |
| Changing an endpoint stored in a field | Rebind if bean is mutable | Creates a new target if bean is stateful |
| Deleting a property and reverting to default | Possible if class is eligible for reset | Do not rely on key deletion |
| Bean using constructor binding | Not supported | Does not directly rebind an immutable config object |
| Need to keep the same bean instance | Yes | Proxy stays stable, target changes |
| Need consistent state reads during refresh | Risk of readers seeing intermediate state | Read/refresh serialized per bean |
| `HikariDataSource` | Non-refreshable by default | Non-refreshable by default |
| Changing bean graph or classpath | Not suitable | Not suitable |
| Native image/AOT | Context Refresh not supported | Context Refresh not supported |

## 16. Upgrade and Regression Testing Process

### Step 1 — Inventory Dynamic Properties

List properties that can change after startup:

- Downstream endpoints.
- Timeouts and retries.
- Feature flags.
- Log levels.
- Pool sizing.
- Database credentials.
- TLS material.
- Routing or tenant lists.

Record which beans hold each property and how they receive values.

### Step 2 — Classify Beans

Categorize into:

- Mutable `@ConfigurationProperties` needing rebind.
- Constructor-bound properties read only at startup.
- `@RefreshScope` beans needing target recreation.
- Non-refreshable beans/resources.
- Runtime data better placed in a dedicated provider or store.

### Step 3 — Check Key-Deletion Semantics

For every property that might be deleted:

1. Identify the highest-priority property source.
2. Check whether a lower-priority source still supplies the key.
3. Check whether the class has a single no-arg constructor.
4. Check whether nested types are reset.
5. Confirm class-level defaults.
6. Verify bean behavior after rebind.
7. If using RefreshScope, replace deletion with a sentinel or explicit state.

### Step 4 — Write Tests Before Changing Dependencies

Create tests for:

- Changing a property from an old value to a new value.
- Deleting a property from the effective `Environment`.
- Deleting a property from a high-priority source while it remains in a lower source.
- Beans with multiple constructors.
- Constructor-bound records.
- Nested configuration properties.
- RefreshScope target recreation.
- `HikariDataSource` and `never-refreshable`.
- Multiple replicas receiving the same event.

### Step 5 — Upgrade BOM and Run Tests

Upgrade Spring Boot/Spring Cloud on a compatible release train. Run regression tests on the new dependencies and check startup warnings, bean types, Actuator `configprops`, and health.

### Step 6 — Staging Verification

Test updating Config Server or a test config source. Confirm all instances receive the same revision, beans enter the right state, and old resources close safely.

### Step 7 — Monitor and Rollback

Record:

- Artifact version.
- Spring Boot version.
- Spring Cloud release train.
- Config revision.
- Active profiles.
- Refresh count.
- Rebind errors.
- `RefreshScopeHealthIndicator`.
- Connection pool and downstream errors.

If refresh fails, roll back the configuration or deploy a verified artifact. Do not repeatedly retry refresh when the root cause is a non-rebindable bean or non-refreshable resource.

## 17. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Bean retains old property after key deletion | Bean is ineligible for reset or key remains in a lower source | Check constructors and all `PropertySource` entries |
| Value reverts to `null` instead of desired default | Class declares no default on field or constructor | Define clear defaults and verify reset eligibility |
| Record does not update after event | Constructor binding is not refreshed | Use startup/restart or a mutable configuration model |
| Request sees new endpoint but old timeout | Reader observed bean mid-in-place rebind | Use RefreshScope or an immutable snapshot |
| `@Value` singleton keeps old value | Field was injected only at bean initialization | Use dynamic `Environment` or RefreshScope |
| Deleting key fails to disable feature | RefreshScope does not treat key deletion as a new state | Use `enabled=false` or `mode=disabled` |
| Hikari pool does not change URL | `HikariDataSource` is `never-refreshable` by default | Use restart or lifecycle-aware pool replacement |
| Beans inside `@Configuration` do not refresh | `@RefreshScope` on config class does not scope every `@Bean` | Annotate required beans or design a factory |
| New bean fails to initialize after refresh | Constructor or dependency failure | Inspect `RefreshScopeHealthIndicator` and logs |
| One replica receives config, another does not | Event published locally only or Bus is misconfigured | Check Spring Cloud Bus and broadcasting |
| `POST /actuator/env` returns error | `POST` disabled or key blocked by regex | Check endpoint config and `valid-keys-regex` |
| Rebind causes repeated side effects | Setter or init callback creates resources on every bind | Separate configuration from resource lifecycle |
| Refresh behavior changes after upgrade | Release train or bean constructor/type changed | Read docs for exact version and run regression tests |
| Native image lacks refresh support | Context Refresh is incompatible with AOT/native | Set `spring.cloud.refresh.enabled=false` and roll out |

## 18. Pre-Release Checklist

### Environment and Events

- [ ] `Environment` is updated before `EnvironmentChangeEvent` fires.
- [ ] Changed keys are identified accurately.
- [ ] Replicas receive events or refresh signals.
- [ ] Not relying on default Config Client polling.
- [ ] Logging level changes are tested separately.

### Rebind

- [ ] Mutable beans have explicit defaults.
- [ ] No-arg constructor is the sole constructor if resetting to defaults is required.
- [ ] Constructor-bound records are not expected to rebind.
- [ ] Nested properties have been tested.
- [ ] Nested library types are not reset unintentionally.
- [ ] Setters and initialization callbacks have no dangerous side effects.
- [ ] Tests cover adding, updating, and deleting keys.

### Refresh Scope

- [ ] Only beans that truly need recreation use `@RefreshScope`.
- [ ] Not assuming `@RefreshScope` on `@Configuration` covers every `@Bean`.
- [ ] `HikariDataSource` and `never-refreshable` beans are identified.
- [ ] `extra-refreshable` is used only for beans safe to re-instantiate.
- [ ] Deletion is not used as a disable signal.
- [ ] Target destroy/recreate and resource cleanup are tested.

### Operations and Security

- [ ] Actuator endpoints are secured.
- [ ] `POST /actuator/env` restricts `valid-keys-regex`.
- [ ] `configprops` and `env` are exposed selectively.
- [ ] `RefreshScopeHealthIndicator` is monitored.
- [ ] Logging/auditing exists for configuration changes.
- [ ] Native image/AOT disables Context Refresh.
- [ ] A rolling restart or rollback plan is in place.

## 19. Practice Exercises

**Exercise 1 — Rebind a property.** Create a mutable `CheckoutProperties`, add a runtime `MapPropertySource`, publish `EnvironmentChangeEvent`, and verify the endpoint updates.

**Exercise 2 — Delete a key.** Remove `checkout.timeout-millis` from the only `PropertySource` containing it. Publish the event and confirm the bean reverts to its class-level default.

**Exercise 3 — PropertySource precedence.** Set the same key in both a runtime override and `application.yml`. Remove the key from the runtime override and prove the value from `application.yml` wins.

**Exercise 4 — Multiple constructors.** Add a dependency-injecting constructor to `CheckoutProperties`. Delete a property and observe why resetting to class-level defaults is skipped.

**Exercise 5 — Nested properties.** Create nested `RetryProperties` and test recursive resetting. Add the type to `never-reset-nested-types` and compare.

**Exercise 6 — Record.** Create a `@ConfigurationProperties` record and confirm the design does not rely on runtime rebinding; test restarting the context to pick up new values.

**Exercise 7 — RefreshScope.** Create a `@RefreshScope` `CheckoutEndpoint`, change the endpoint in `Environment`, refresh the target, and verify a new target initializes.

**Exercise 8 — Sentinel instead of deletion.** Use `checkout.mode=disabled` instead of deleting `checkout.mode`. Verify the bean transitions to the disabled state after refresh.

**Exercise 9 — HikariDataSource.** Inspect the `DataSource` type and `never-refreshable`. Design a restart or pool-replacement workflow instead of direct refresh.

**Exercise 10 — Multiple replicas.** Run two instances and broadcast changes with Spring Cloud Bus. Confirm both instances share the same revision and configuration values.

**Exercise 11 — Actuator security.** Enable `POST /actuator/env` with a restricted `valid-keys-regex`. Verify unauthorized callers cannot modify properties.

**Exercise 12 — Upgrade regression.** Upgrade the Spring Cloud BOM, re-run all rebind/deletion/refresh tests, and compare behavior with the previous release train.

## 20. Key Takeaways and Reference Sources

- `EnvironmentChangeEvent` announces changed keys; it does not fetch configuration from Config Server by itself.
- Spring Cloud Config Client does not poll by default; multi-replica applications should use a broadcast mechanism such as Spring Cloud Bus.
- Rebinding `@ConfigurationProperties` updates mutable configuration beans and logger levels.
- Rebinding mutates the same instance in place; concurrent readers can observe intermediate state.
- Rebinding resets to class-level defaults only when the class has a no-arg constructor as its sole constructor.
- If a key is deleted from one source yet remains in a lower-priority source, `Environment` still resolves a value and the bean binds that value.
- Constructor binding and Java records are not refreshed by the standard rebind mechanism.
- `@RefreshScope` uses proxies and a target cache; refresh destroys the current target and creates a new target on the next invocation.
- Deleting a key is not a reliable signal to change property presence in Refresh Scope; use an explicit sentinel such as `enabled=false` or `mode=disabled`.
- `HikariDataSource` belongs to `never-refreshable` by default.
- `@RefreshScope` on `@Configuration` does not automatically make every `@Bean` inside it refresh-scoped.
- Check the exact Spring Cloud release train because reset behavior and configuration properties can change by version.
- Context Refresh is not supported in Spring AOT transformations and native images; set `spring.cloud.refresh.enabled=false` in those models.

Official sources to cross-check for your project's Spring Boot/Spring Cloud version:

1. [Spring Cloud Commons 5.0.4 – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
3. [Spring Cloud Commons – EnvironmentChangeEvent source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/environment/EnvironmentChangeEvent.java)
4. [Spring Cloud Commons – ConfigurationPropertiesRebinder source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/properties/ConfigurationPropertiesRebinder.java)
5. [Spring Cloud Commons – ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java)
6. [Spring Cloud Commons – RefreshScope source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java)
7. [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
8. [Spring Boot – Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
9. [Spring Cloud Bus – Broadcasting configuration changes](https://docs.spring.io/spring-cloud-bus/reference/)
10. [Spring Cloud – Release trains and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
