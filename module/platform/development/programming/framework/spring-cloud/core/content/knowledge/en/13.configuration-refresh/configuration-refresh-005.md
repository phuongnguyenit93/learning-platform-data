# Distinguishing In-Place Rebinding from Bean Recreation in Refresh Scope

When a Spring Cloud application's configuration changes, not every bean needs to be recreated. A bean that only holds simple configuration values can be rebound on its existing instance. Conversely, a client or stateful object built from configuration at initialization time may need to be destroyed and recreated to pick up a new endpoint, credentials, or resources.

Spring Cloud Context supports both approaches. **Rebinding** updates `@ConfigurationProperties` beans directly on the existing instance. **Refresh Scope** keeps a stable proxy while invalidating the cached target so the next access creates a new target. Understanding this difference helps you choose the right lifecycle, avoid half-old half-new state, and reduce risk when configuration changes while the application is serving requests.

This lesson belongs to the **Configuration Refresh** chapter of the **SPRING_CLOUD_CORE** module. We will go from `EnvironmentChangeEvent` to `ConfigurationPropertiesRebinder` and `RefreshScope`, write two examples where identity can be observed, and test the difference between in-place updates and target recreation.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of `EnvironmentChangeEvent` in the runtime configuration update workflow.
- Describe how `ConfigurationPropertiesRebinder` rebinds a bean without replacing its instance.
- Distinguish the identities of `@ConfigurationProperties` beans, scoped proxies, and `@RefreshScope` targets.
- Describe the order of updating the Environment, publishing events, rebinding, and invalidating the target cache.
- Choose rebinding for simple mutable configuration or `@RefreshScope` for beans requiring re-initialization.
- Identify concurrent-read risks during rebinding and consistency limits of Refresh Scope.
- Write Java examples and integration tests to prove which instances are preserved and which are newly created.
- Handle cases involving constructor binding, nested properties, HikariDataSource, property deletion, and multiple replicas.

### 1.1. Required Dependencies

Both mechanisms in this lesson belong to **Spring Cloud Context**. If this module is not yet in your dependency graph, add the dependency and let the Spring Cloud BOM manage its version:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

If you need the HTTP endpoint `/actuator/refresh`, add `spring-boot-starter-actuator` managed by Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

In projects already using Spring Cloud Config Client or other Cloud starters, `spring-cloud-context` may already be pulled in transitively. Check your dependency tree before declaring it directly. The Spring Boot/Spring Cloud pair must still follow the compatibility matrix of your release train.

## 2. Two Strategies with Different Lifecycles

### 2.1. In-Place Rebinding

For a bean managed with `@ConfigurationProperties`, Spring Cloud Context can rebind its properties upon receiving `EnvironmentChangeEvent`. The existing bean is kept; configuration fields are updated on that same object.

Example:

~~~java
@Component
@ConfigurationProperties(prefix = "routing")
public class RoutingProperties {

    private String host = "router-default";
    private int timeoutMs = 1000;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getTimeoutMs() {
        return timeoutMs;
    }

    public void setTimeoutMs(int timeoutMs) {
        this.timeoutMs = timeoutMs;
    }
}
~~~

After the Environment has `routing.host=router-v2` and the change event is published, `RoutingProperties` is rebound. If a service has injected this bean, the service's reference field still points to the same `RoutingProperties` instance; when calling `getHost()`, the service sees the new value.

### 2.2. Recreating the Target in Refresh Scope

For a `@RefreshScope` bean, Spring injects a scoped proxy into consuming beans. The scope stores the initialized target in a cache. On refresh, the old target is destroyed and the cache entry is removed. The proxy remains; the next method call through the proxy creates a new target.

Example:

~~~java
@Component
@RefreshScope
public class RoutingClient {

    @Value("${routing.host:router-default}")
    private String host;

    public String currentHost() {
        return host;
    }
}
~~~

A singleton holds the `RoutingClient` proxy. After refresh, the proxy field inside the singleton does not change, but the target executing `currentHost()` is a new instance and receives the current configuration value.

### 2.3. Direct Comparison

| Criterion | Rebinding `@ConfigurationProperties` | `@RefreshScope` |
| --- | --- | --- |
| Updated target | Existing configuration bean | Bean target inside refresh scope |
| Instance identity | Preserves the same instance | Target changes; proxy stays the same |
| Update mechanism | Rebinds fields on the object | Destroys cached target and creates a new target on access |
| Lifecycle | Existing bean is reset/rebound and reruns the rebinder's corresponding initialization steps | Old target runs destruction callbacks; new target runs initialization callbacks |
| When appropriate | Mutable, simple configuration that can be updated safely in place | Clients, factories, or beans with state/resources that must be rebuilt from new configuration |
| Primary risk | Other threads may read partially updated state | New target may fail to initialize; state in the old target is lost |
| Synchronization | Concurrent rebinds of the same bean are serialized; does not lock external readers | Reads through the proxy are coordinated with refreshes of that bean |

Neither strategy automatically replaces the other in all cases. Choose based on how the bean uses configuration and what resources it owns.

## 3. How Does EnvironmentChangeEvent Trigger Rebinding?

`EnvironmentChangeEvent` carries the list of keys that changed in the Environment. `ConfigurationPropertiesRebinder` listens for this event and rebinds `@ConfigurationProperties` beans. Spring Cloud also has a listener that updates log levels when `logging.level.*` keys change.

General flow:

~~~mermaid
sequenceDiagram
    participant Source as Config source
    participant Refresher as ContextRefresher
    participant Env as Environment
    participant Event as EnvironmentChangeEvent
    participant Rebind as ConfigurationPropertiesRebinder
    participant Scope as RefreshScope
    Source->>Refresher: New configuration
    Refresher->>Env: Reload PropertySource
    Refresher->>Refresher: Compare old/new keys and values
    Refresher->>Event: Publish changed keys
    Event-->>Rebind: Rebind @ConfigurationProperties
    Rebind->>Rebind: Update existing instance
    Refresher->>Scope: refreshAll()
    Scope->>Scope: Destroy cached target
    Note over Scope: Next call through proxy creates new target
~~~

In the standard Spring Cloud Context refresh workflow, `ContextRefresher.refresh()` performs these steps:

1. Snapshots the current values in the Environment.
2. Reloads configuration sources per the active mechanism, such as Config Data or legacy bootstrap.
3. Compares before and after states to identify changed keys.
4. Publishes `EnvironmentChangeEvent` so listeners rebind configuration beans and update loggers.
5. Calls `RefreshScope.refreshAll()` to invalidate targets in refresh scope.
6. Returns the set of changed keys.

Therefore, a single call to the refresh endpoint can trigger **both mechanisms** within the same workflow. The difference lies in the lifecycle of each bean type, not two completely separate endpoints.

### 3.1. Who Publishes the Event?

The application needs a mechanism to put new values into the Environment and publish the event. It can be:

- `POST /actuator/refresh` in an application using Spring Cloud Context and Config Client.
- Spring Cloud Bus publishing a refresh event to instances registered on the bus.
- An internal administrative component updating a PropertySource and then deliberately publishing `EnvironmentChangeEvent`.

Spring Cloud Config Client **does not poll Config Server by default** to automatically detect configuration changes. With multiple replicas, updating one instance does not automatically change the Environment of the other instances. You can use the Bus or a coordinated rollout/refresh mechanism so all instances receive the same configuration version.

### 3.2. Update the Environment Before Rebinding

`EnvironmentChangeEvent` only notifies that keys changed; it does not fetch data from Config Server itself. If you publish the event before the new PropertySource is installed in the Environment, the rebinder will rebind using the old values.

The correct sequence is:

~~~text
Load new configuration
        |
        v
Update Environment / PropertySources
        |
        v
Publish EnvironmentChangeEvent
        |
        +----> Rebind @ConfigurationProperties
        |
        v
Invalidate RefreshScope target cache
~~~

## 4. Rebinding Mutates the Existing Instance

### 4.1. Mutable JavaBean

Rebinding suits configuration beans that can be rebound through setters or fields. Example:

~~~java
package com.example.refresh;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "payment.retry")
public class RetryProperties {

    private int maxAttempts = 2;
    private long backoffMs = 200;

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public long getBackoffMs() {
        return backoffMs;
    }

    public void setBackoffMs(long backoffMs) {
        this.backoffMs = backoffMs;
    }
}
~~~

Initial `application.yml`:

~~~yaml
payment:
  retry:
    max-attempts: 2
    backoff-ms: 200
~~~

After the configuration source changes to:

~~~yaml
payment:
  retry:
    max-attempts: 4
    backoff-ms: 500
~~~

and the change event is published, the `RetryProperties` bean is rebound. A singleton that injected this bean continues holding the same reference and reads the new values through its getters.

### 4.2. Rebinding Preserves Instance Identity

You can observe identity using `System.identityHashCode` or the `==` operator:

~~~java
@Service
public class RetryService {

    private final RetryProperties properties;

    public RetryService(RetryProperties properties) {
        this.properties = properties;
    }

    public void logConfiguration() {
        System.out.println(
                "properties identity="
                        + System.identityHashCode(properties));
        System.out.println(
                "maxAttempts=" + properties.getMaxAttempts());
    }
}
~~~

Calling `logConfiguration()` before and after rebinding will show that the identity does not change, while the getter value changes.

### 4.3. Resetting Defaults Before Binding

In current Spring Cloud Context versions, the rebinder has a step that resets properties to their class-level default values before rebinding. The goal is to avoid retaining old values when a key is removed from the Environment.

Example:

~~~java
private int maxAttempts = 2;
~~~

If the previous configuration value was `5`, but the `payment.retry.max-attempts` key is removed and the bean can be reset to defaults, rebinding can restore the field to `2` instead of keeping `5`.

Reset capability depends on how the bean is constructed. For beans without a suitable no-argument constructor, constructor binding, or required constructor dependencies, the rebinder cannot reliably construct a default object just to obtain reset values. In that case, a removed value may not reset to default as expected. Do not rely on key deletion to drive business logic without testing against your exact version.

### 4.4. Bean Lifecycle During Rebinding

The rebinder updates and re-initializes the bean according to the rebinding mechanism, while keeping the same instance. Consequently:

- The object's identity does not change.
- Configuration fields are reset/rebound according to the bean's capabilities.
- Post-processing and initialization steps are rerun according to the rebinder's workflow.
- Other references holding the bean still point to the same object.
- Other business state inside the bean may remain, except for parts reset or altered by the binding process.

Do not treat rebinding as creating a `new` object. If the bean needs to rebuild connections, HTTP clients, or internal caches based on configuration, manage resource recreation explicitly or consider `@RefreshScope`.

## 5. Recreating the Target in Refresh Scope

### 5.1. Proxy Keeps Its Identity, Target Changes

`@RefreshScope` creates a scoped proxy. Other beans inject the proxy rather than holding the target directly. The scope caches the initialized target and reuses it for subsequent calls.

When `refresh(beanName)` or `refreshAll()` is called:

- The current target is destroyed if it has already been created.
- The target's destruction callbacks are executed.
- The cache entry is removed.
- The proxy remains in the application context.
- The next method call through the proxy creates a new target and runs initialization callbacks.

If the bean has never been used and has no cached target yet, refresh does not need to create a new target right away. A target will be created on the first call after refresh.

**Note on initial startup:** the proxy can forward calls to the target lazily, but current `RefreshScope` implementations also perform eager initialization upon receiving `ContextRefreshedEvent` for refresh-scoped beans not marked lazy. Thus, a target can be initialized early when the application context finishes starting up. The post-invalidation rule still holds: a target removed from the cache is recreated on the next access.

### 5.2. Example of a Target That Must Be Rebuilt from Configuration

~~~java
package com.example.refresh;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class PaymentEndpointClient {

    private static final AtomicInteger IDS = new AtomicInteger();

    private final int targetId = IDS.incrementAndGet();

    @Value("${payment.gateway.base-url}")
    private String baseUrl;

    @PostConstruct
    void initialize() {
        System.out.println(
                "Create target " + targetId + " for " + baseUrl);
    }

    @PreDestroy
    void destroy() {
        System.out.println("Destroy target " + targetId);
    }

    public String endpoint() {
        return baseUrl;
    }

    public int targetId() {
        return targetId;
    }
}
~~~

Singleton consuming the bean:

~~~java
@Service
public class PaymentGateway {

    private final PaymentEndpointClient client;

    public PaymentGateway(PaymentEndpointClient client) {
        this.client = client;
    }

    public String endpoint() {
        return client.endpoint();
    }

    public int targetId() {
        return client.targetId();
    }
}
~~~

`PaymentGateway` still holds the same `client` proxy. Once the target is invalidated, the next call to `client.endpoint()` creates a new `PaymentEndpointClient`, re-reads `payment.gateway.base-url`, and returns the new endpoint.

### 5.3. Do Not Hold Old State Outside the Proxy

The following code does not automatically update after refresh:

~~~java
@Service
public class CachedEndpoint {

    private final String endpoint;

    public CachedEndpoint(PaymentEndpointClient client) {
        this.endpoint = client.endpoint();
    }

    public String endpoint() {
        return endpoint;
    }
}
~~~

The constructor called the proxy and copied the string into a singleton field. After refresh, the proxy can switch to a new target, yet `CachedEndpoint.endpoint` remains the old string. To receive the new value, call through the proxy at usage time or refresh the bean holding that copy according to an appropriate design.

## 6. Both Mechanisms Operating in the Same Refresh

Suppose an application has:

- `RetryProperties`: a mutable `@ConfigurationProperties` bean.
- `PaymentEndpointClient`: a `@RefreshScope` bean using `@Value`.
- `PaymentGateway`: a singleton holding the `PaymentEndpointClient` proxy.

Before refresh:

~~~yaml
payment:
  retry:
    max-attempts: 2
  gateway:
    base-url: "https://sandbox.payments.example"
~~~

After Config Server publishes the new configuration:

~~~yaml
payment:
  retry:
    max-attempts: 4
  gateway:
    base-url: "https://payments.example"
~~~

When `ContextRefresher.refresh()` runs:

1. Environment receives the new values for both keys.
2. `EnvironmentChangeEvent` notifies that `payment.retry.max-attempts` and `payment.gateway.base-url` changed.
3. `ConfigurationPropertiesRebinder` rebinds `RetryProperties` on the existing instance.
4. `RefreshScope.refreshAll()` destroys the cached `PaymentEndpointClient` target.
5. `PaymentGateway` still holds the old proxy.
6. The next call to `PaymentGateway.endpoint()` creates a new `PaymentEndpointClient` target and receives the new base URL.

Result:

| Object | Before refresh | After refresh |
| --- | --- | --- |
| `RetryProperties` | Instance A, `maxAttempts=2` | Still instance A, `maxAttempts=4` |
| `PaymentEndpointClient` proxy | Proxy P | Still proxy P |
| `PaymentEndpointClient` target | Target T1, sandbox URL | Target T1 destroyed; next call creates T2 with production URL |
| `PaymentGateway` | Singleton G holding proxy P | Still singleton G holding proxy P |

This is the core distinction: **rebinding mutates state inside an instance; Refresh Scope replaces the target instance behind a proxy**.

## 7. Choosing a Mechanism by Bean Type

| Bean type or need | Approach to consider | Reason |
| --- | --- | --- |
| Bean holding only retry counts, timeouts, feature toggles | `@ConfigurationProperties` and rebinding | Simple value updates, preserves instance |
| Mutable configuration bean read by multiple services | Rebinding if readers tolerate in-place updates; Refresh Scope if a consistent view is needed | Choose based on concurrency requirements |
| HTTP client built from base URL and credentials | `@RefreshScope` or a factory with explicit client replacement | Target must be rebuilt from new configuration |
| Bean with an internal cache dependent on configuration | `@RefreshScope` or controlled manual cache invalidation | Simply changing a field may not clear old cache entries |
| Immutable/constructor-bound bean | Redesign lifecycle, use an appropriate refreshable bean, or restart | Standard rebinding does not update constructor-bound objects |
| DataSource/pool | Evaluate rebinding per property; consider restart or replacement-capable pool | Changing URL does not mean open connections are safely migrated |
| Business state such as balances or shopping carts | Do not use refresh scope to hold state | Targets can be destroyed and in-memory state lost |

Do not add `@RefreshScope` to every bean. Recreating beans has a cost: running constructors, injecting dependencies, initializing connections/clients, releasing old resources, and handling errors if the new target fails to initialize.

## 8. Consistency and Concurrent Access

### 8.1. Rebinding Does Not Lock Threads Reading the Bean

Spring Cloud serializes concurrent rebinds on the same bean so two refreshes do not overlap reset/bind/init steps. However, that does not prevent another thread from reading the bean while its fields are being updated.

For example, a bean with two properties:

~~~yaml
payment:
  min-amount: 100
  max-amount: 1000
~~~

When changing both values, a reader may see the new `min-amount` alongside the old `max-amount` while binding is underway. With mutable collections, the binder may clear the list first and then add new elements; a concurrent reader may temporarily observe an empty collection.

If a request must read a consistent set of configuration values rather than independent fields, in-place rebinding may not satisfy the requirement.

### 8.2. Refresh Scope Synchronizes Reads with Refresh Per Bean

Refresh Scope uses a per-bean read/write lock mechanism to coordinate calls through the proxy with target refresh operations. This prevents callers from reading a target while the scope is changing that target's lifecycle.

However, this is **not an atomic transaction across the entire application context**:

- One scoped bean may have already switched to a new target while another bean has not been called yet.
- Multiple replicas in a cluster are not synchronized by a single refresh on one JVM.
- A request using an old target may have already obtained a reference to it before refresh started; resource design must allow in-flight requests to finish and close resources according to lifecycle.

For changes requiring synchronization across multiple beans or services, consider configuration versioning, phased rollouts, Spring Cloud Bus, and backward compatibility between versions.

## 9. Updating Configuration via Actuator

In applications with Spring Cloud Context and Config Client, you can use the `POST /actuator/refresh` endpoint to run the refresh workflow. Actuator is required and the endpoint must be exposed:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

Calling the endpoint:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

The response is usually the list of changed keys. This is a useful signal for verifying the configuration loading workflow, but it does not prove all new targets have been successfully created: targets in Refresh Scope are only recreated on the next call.

The refresh endpoint has permission to alter runtime state, so it must be restricted via Spring Security, network policies, and internal management channels. Do not expose this endpoint publicly.

### 9.1. Refreshing Multiple Instances

When running multiple replicas, a direct refresh request only affects the application context that receives the request. You can:

- Use Spring Cloud Bus to broadcast events to instances.
- Invoke refresh on each instance through an internal management system.
- Use a rolling restart when changes require re-initializing many resources or require clear rollback.

Do not poll Config Server from every instance at short intervals without a clear operational reason. Polling generates load and can cause instances to see configuration at different times.

## 10. Known Limitations

### 10.1. Constructor Binding

`@ConfigurationProperties` objects using constructor binding, including Java records, cannot be refreshed by the standard rebinding mechanism. They are constructed via constructors and have no setters for the binder to update the existing instance.

If runtime changes are needed, you can:

- Encapsulate immutable data inside a bean with controlled lifecycle and recreate it via Refresh Scope.
- Use an abstraction that accesses the latest configuration at usage time.
- Restart/roll out the application when configuration changes.

### 10.2. HikariDataSource

`HikariDataSource` is included by default in `spring.cloud.refresh.never-refreshable`. Do not expect merely adding `@RefreshScope` to cause a Hikari pool to be recreated through the standard refresh workflow.

Replacing a datasource requires considering active connections, transactions, pool shutdown, request draining, and pool cutover timing. If you need runtime datasource replacement, choose a tested implementation and procedure; do not remove Hikari from `never-refreshable` just to make the refresh endpoint return success.

### 10.3. Beans Declared in @Configuration

Putting `@RefreshScope` on a `@Configuration` class does not automatically put all `@Bean` methods declared inside it into refresh scope. If another bean depends on those beans, it will not automatically receive new targets unless it is itself designed to refresh and dependencies are re-injected.

Place the scope directly on the bean that needs to be recreated:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    @RefreshScope
    PaymentEndpointClient paymentEndpointClient(
            PaymentClientFactory factory,
            PaymentProperties properties) {
        return factory.create(properties.baseUrl());
    }
}
~~~

In this case, the `paymentEndpointClient` bean is refreshed. Singletons that copied data from the target or hold their own resources still need their own lifecycle handling.

### 10.4. Removing a Property from the Environment

Spring Cloud documentation notes that removing a value from a configuration source and refreshing does not guarantee every bean will receive the expected "key no longer exists" semantics. Test key deletion against your exact version and design logic around default values or explicit states rather than relying on property disappearance.

### 10.5. AOT and Native Image

Context Refresh is not supported for Spring AOT transformations and native images according to current Spring Cloud documentation. For AOT/native applications, set:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Then use restart/rollout or a configuration update mechanism supported for this deployment type.

## 11. Testing the Difference Between Rebinding and Recreation

A good test should prove:

- The `@ConfigurationProperties` bean keeps the same identity while getters return new values.
- The `@RefreshScope` proxy keeps the same identity.
- The target behind the proxy is newly created after cache invalidation.
- The new target reads updated values from the Environment.

The example below uses `MapPropertySource` to change a value in a test, then publishes `EnvironmentChangeEvent` and refreshes the target:

~~~java
package com.example.refresh;

import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ConfigurationRefreshModeTest {

    @Autowired
    RetryProperties retryProperties;

    @Autowired
    PaymentEndpointClient paymentEndpointClient;

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    ConfigurableApplicationContext applicationContext;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void rebindKeepsPropertiesBeanButRefreshRecreatesTarget() {
        RetryProperties propertiesReference = retryProperties;
        PaymentEndpointClient proxyReference = paymentEndpointClient;

        int oldTargetId = paymentEndpointClient.targetId();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "testOverrides",
                        Map.of(
                                "payment.retry.max-attempts", 4,
                                "payment.gateway.base-url",
                                "https://payments.example")));

        applicationContext.publishEvent(
                new EnvironmentChangeEvent(
                        applicationContext,
                        Set.of(
                                "payment.retry.max-attempts",
                                "payment.gateway.base-url")));

        assertThat(retryProperties).isSameAs(propertiesReference);
        assertThat(retryProperties.getMaxAttempts()).isEqualTo(4);

        assertThat(paymentEndpointClient).isSameAs(proxyReference);
        assertThat(refreshScope.refresh("paymentEndpointClient")).isTrue();

        assertThat(paymentEndpointClient.targetId())
                .isNotEqualTo(oldTargetId);
        assertThat(paymentEndpointClient.endpoint())
                .isEqualTo("https://payments.example");
    }
}
~~~

The test assumes `RetryProperties` and `PaymentEndpointClient` beans are registered as in the earlier examples, the client bean name is `paymentEndpointClient`, and the application includes Spring Cloud Context. It publishes the event directly to focus on testing the two mechanisms; in production, also test the full path via `ContextRefresher`/Actuator or Spring Cloud Bus.

### 11.1. Additional Test Matrix

| Case | Expected outcome to verify |
| --- | --- |
| Rebind a mutable bean | Instance remains the same; property values are updated |
| Rebind multiple related fields | Concurrent readers may see intermediate state; confirm if acceptable |
| Remove a property | Verify default/reset behavior and cases where the bean cannot reset |
| Constructor-bound bean | Do not expect in-place rebinding to work |
| Refresh an already-created target | Old target is destroyed; new target is created on access |
| Refresh a never-called target | No immediate new target needed; first call creates target |
| New target fails initialization | Health/logs record error; configuration recovery plan exists |
| Multiple replicas | All instances receive the same version after Bus/rollout |
| AOT/native | Refresh is disabled and restart strategy is verified |

## 12. Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `@ConfigurationProperties` did not change | Environment not updated or event not published | Check effective PropertySources and `EnvironmentChangeEvent` |
| One field changed while another stayed old | Key missing from Environment, bind error, or default reset failed | Check `ConfigurationPropertiesRebinder` errors and constructor constraints |
| Bean has the same identity after refresh | This is expected behavior for rebinding | Check that getter values changed |
| `@RefreshScope` bean still returns old endpoint | Code holds a copy outside the proxy or target was not invalidated | Check all references and `refresh(beanName)` |
| Proxy identity changed | Consumer or context was recreated; may be comparing target instead of proxy | Check scope, context lifecycle, and injection site |
| Refresh endpoint returned, but target is not new | No call made through proxy yet, or new target failed initialization | Call the bean and check logs/lifecycle/health |
| One replica did not receive configuration | Refresh ran on only one JVM | Check Bus events or per-instance invocation process |
| Hikari pool was not replaced | Listed in `never-refreshable` | Check implementation and pool replacement plan |

## 13. Selection and Operational Workflow

Before deciding which mechanism to use, answer these questions:

1. Does the bean only hold rebindable configuration values, or has it created clients/resources from those values?
2. Can readers tolerate seeing fields change in place over a brief window?
3. Is a new target needed to run constructors, dependency injection, and lifecycle callbacks?
4. Does the target hold state that will be lost when destroyed? Is that state stored elsewhere?
5. Must the change apply to multiple beans or multiple replicas simultaneously?
6. Can you roll back if the new target fails to initialize?

A production workflow can include:

- Releasing configuration with a clear version/label.
- Authenticating Config Server and callers permitted to read/update configuration.
- Installing the new PropertySource into the Environment.
- Publishing the event to rebind configuration beans and update loggers.
- Invalidating the target cache for beans that require recreation.
- Triggering a safe call path so the new target is created.
- Verifying health, error rates, latency, and per-replica status.
- If errors occur, restoring the previous version and rerunning refresh or rollout.

Do not treat HTTP 200 from `/actuator/refresh` as proof that all configurations and resources have been applied successfully. Monitor rebinding errors, refresh scope health indicators, and target initialization results on subsequent usage.

## 14. Summary

Rebinding and Refresh Scope solve two different needs in the configuration refresh workflow. Rebinding uses `EnvironmentChangeEvent` to update `@ConfigurationProperties` beans directly on the existing instance. Refresh Scope keeps a stable proxy while destroying the cached target, then creates a new target on the next call.

Rebinding is lighter and suits mutable configuration, though concurrent readers may observe partially updated state. Refresh Scope suits beans that must re-initialize from new configuration and provides per-bean coordination between reads and refreshes; it is still not an atomic transaction across the entire application context or cluster.

In a single `ContextRefresher.refresh()`, Spring Cloud can update the Environment, publish `EnvironmentChangeEvent` for rebinding, and then invalidate Refresh Scope. Choose which beans should update in place and which should be recreated, test both lifecycles, and prepare error-handling plans before using refresh in production.

## References

- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `EnvironmentChangeEvent`, rebinding `@ConfigurationProperties`, concurrency, `@RefreshScope`, HikariDataSource, constructor binding, and AOT/native.
- [ConfigurationPropertiesRebinder source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/properties/ConfigurationPropertiesRebinder.java): listener for `EnvironmentChangeEvent` and bean rebind mechanism.
- [ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java): updating Environment, computing changed keys, publishing events, and calling `refreshAll()`.
- [RefreshScope source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java): destroying targets by name, refreshing the whole scope, and lifecycle callbacks.

Cross-check documentation with the Spring Cloud release train in use. Details on nested property resets, un-rebindable beans, and AOT behavior may vary across versions.
