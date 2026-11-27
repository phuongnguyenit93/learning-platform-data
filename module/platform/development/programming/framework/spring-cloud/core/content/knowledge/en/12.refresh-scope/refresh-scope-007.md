# Target Destruction Lifecycle and Resource Release

`@RefreshScope` allows Spring Cloud to replace a bean holding old configuration with a target recreated from new configuration. This mechanism is especially important for beans owning resources such as connection pools, HTTP clients, schedulers, file watchers, or message consumers. When a refresh occurs, Spring Cloud removes the current target from the scope's cache and invokes registered **destruction callbacks**. The next access through the scoped proxy creates a new target and re-runs the normal initialization steps.

A key point to understand thoroughly is that **the proxy and the target have different lifecycles**. Other beans typically hold the proxy injected from the start; the proxy remains intact after refresh. The old target object is destroyed, the resources it owns are released, and a new target is created when needed. This lesson focuses on that sequence, how to register destruction callbacks, how to test them, and the limitations when refreshing beans actively serving requests.

This lesson belongs to the **Refresh Scope** chapter of the **SPRING_CLOUD_CORE** module. Its content connects to Spring Cloud Context, externalized configuration, and operating Spring Boot applications in distributed systems.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish the scoped proxy, target bean, and `RefreshScope` cache.
2. Describe the refresh sequence: evicting the target, invoking destruction callbacks, and creating a new target on the next access.
3. Register resource cleanup using `@PreDestroy`, `DisposableBean`, or `@Bean(destroyMethod = "...")`.
4. Design refreshable beans with clear resource ownership and safe closing callbacks.
5. Use `RefreshScope.refresh(String)` and `refreshAll()` within the proper scope.
6. Distinguish refreshing targets from updating `Environment`, rebinding `@ConfigurationProperties`, and broadcasting refreshes to multiple instances.
7. Test that the old target is destroyed and a new target is recreated.
8. Identify limitations such as `HikariDataSource`, `@Configuration` scoping, immutable beans, and AOT/native images.

## 2. Three Components of Refresh Scope

### 2.1. Scoped Proxy

When a bean is declared with `@RefreshScope`, Spring creates a proxy for consumers to inject and invoke. The proxy provides a stable access point to the bean in the `refresh` scope.

For example, `OrderService` injects `PartnerClient`. What `OrderService` holds is the proxy for `PartnerClient`; it does not need to receive a new reference whenever configuration changes.

### 2.2. Target Bean

The target is the object that executes methods, created from the original bean definition. The target holds actual state and resources, such as:

- Endpoints, credentials, or timeouts read from `Environment`.
- HTTP connection managers or client transports.
- Connection pools.
- Schedulers, threads, or listeners.
- Internal caches initialized from configuration.

Targets can register initialization and destruction callbacks just like standard Spring beans.

### 2.3. Target Cache

`RefreshScope` stores initialized targets in a cache keyed by bean name. When the proxy needs to invoke a method, the scope looks up the target in the cache:

- Target present: uses the current target.
- No target yet: creates one from the bean definition, applies dependency injection and initialization callbacks, and stores it in the cache.

During refresh, the corresponding entry is evicted from the cache. If a target already existed and has destruction callbacks, those callbacks run during destruction. The next call creates a new target.

~~~mermaid
flowchart TD
    A[Consumer calls method] --> B[Scoped proxy]
    B --> C{Target in cache?}
    C -- Yes --> D[Forward call to current target]
    C -- No --> E[Create target from bean definition]
    E --> F[Inject dependencies and run init callbacks]
    F --> G[Store target in cache]
    G --> D
    H[Refresh bean] --> I[Remove target from cache]
    I --> J[Run destruction callbacks]
    J --> K[Proxy still exists]
    K --> A
~~~

The proxy and the target are not the same object. This is the foundation for understanding why consumers do not need to be recreated when a target refreshes.

## 3. Sequence of Target Destruction and Recreation

A refresh for an already-initialized bean typically proceeds in this sequence:

1. The application updates the configuration source or triggers the refresh operation via the configured mechanism.
2. `RefreshScope` identifies the target to refresh.
3. The current target is removed from the scope's cache.
4. Spring runs registered destruction callbacks for that target.
5. The scope publishes the corresponding refresh event.
6. The proxy remains held by consumers.
7. On the next call through the proxy, the scope creates a new target from the bean definition.
8. Dependencies and configuration values are re-resolved; initialization callbacks run on the new target.
9. The new target is stored in the cache and serves subsequent calls.

### 3.1. Refresh Is Not In-Place Field Mutation

Suppose `PartnerClient` was created with endpoint `https://partner-v1.internal`. After configuration changes to `https://partner-v2.internal`, refresh scope can destroy the old target and create a new target using the new endpoint.

The old `PartnerClient` object does not have its `baseUrl` field mutated to the new value. It is destroyed according to its lifecycle; a new object is created from the bean definition and current configuration.

### 3.2. New Targets Are Typically Created Only When Used

Refresh scope uses a scoped proxy and a target cache. Once a cache entry is removed, the refresh operation does not need to create a replacement target right away. A new target is created when the proxy receives a call needing the target. At startup, whether a target is eagerly initialized depends on eager/lazy configuration and version; seeing the proxy in the context does not by itself prove the target has been created.

This has two operational consequences:

- Refresh can complete before new targets have been initialized.
- New target initialization errors may surface only on the next usage.

A successful `refreshAll()` call does not prove every new target initialized cleanly or every dependency connected. After a refresh, verify critical beans with health checks or appropriate verification calls.

### 3.3. Beans Never Initialized Yet

If a target has never been created, there is no old instance to release resources from. Refreshing a non-existent cache entry cannot run destruction callbacks for a target that never existed.

Therefore, the number of destruction callback executions depends on the number of targets actually initialized and registered with destruction callbacks, not simply the number of refresh calls.

## 4. How Are Destruction Callbacks Registered?

Spring manages the lifecycle of target beans. When a target is created, the container records destruction callbacks provided by the bean definition or bean instance. Refresh scope invokes these callbacks when the target is evicted from the scope.

### 4.1. Using `@PreDestroy`

`@PreDestroy` fits when a bean owns resources directly and needs to close them before the target is destroyed:

~~~java
import jakarta.annotation.PreDestroy;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class PartnerClient {

    private final PartnerTransport transport;

    public PartnerClient(PartnerProperties properties) {
        this.transport = PartnerTransport.open(properties.getBaseUrl());
    }

    public String call(String request) {
        return transport.exchange(request);
    }

    @PreDestroy
    public void close() {
        transport.close();
    }
}
~~~

`PartnerTransport` and `PartnerProperties` are illustrative application classes. When the `PartnerClient` target is destroyed, Spring calls `close()` via the registered destruction callback.

With Spring Boot 3 and later, `@PreDestroy` is typically imported from `jakarta.annotation.PreDestroy`. Legacy projects may use the `javax.annotation` namespace; follow your project's dependencies and version.

### 4.2. Using `@Bean(destroyMethod = "...")`

For resources created via Java configuration, you can explicitly declare the destruction method:

~~~java
@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean(destroyMethod = "close")
    @RefreshScope
    PartnerTransport partnerTransport(PartnerProperties properties) {
        return PartnerTransport.open(properties.getBaseUrl());
    }
}
~~~

When the `partnerTransport` target is refreshed, Spring calls `close()` per the `destroyMethod` metadata. This makes resource ownership and lifecycle clearly visible right at the bean declaration.

Use `destroyMethod` when you need explicit control over the cleanup method name. If the resource API provides a standard close method, this is usually concise and explicit.

### 4.3. Implementing `DisposableBean`

A bean can also implement `org.springframework.beans.factory.DisposableBean`:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class PartnerTransport implements DisposableBean {

    @Override
    public void destroy() {
        closeTransportResources();
    }

    private void closeTransportResources() {
        // Close connection manager, executor, or resources owned by the bean.
    }
}
~~~

`DisposableBean` couples the class directly to Spring APIs. In new application code, `@PreDestroy` or `@Bean(destroyMethod = "...")` usually reduces coupling. However, `DisposableBean` remains useful when a class needs explicit Spring lifecycle integration.

### 4.4. What If There Is No Callback?

If a bean declares no destruction callback and has no lifecycle method recognized by Spring, Spring cannot guess how to close a custom resource.

For example, a class that creates an `ExecutorService` in its constructor without registering `shutdown()` risks leaving threads behind when the target refreshes. Design explicit callbacks for every resource with a lifecycle.

## 5. Designing Safe Resource-Release Callbacks

A good destruction callback must run at the right time, close the right resources, and handle errors during shutdown.

### 5.1. Close Only Resources Owned by the Target

If `PartnerClient` creates its own HTTP connection pool, the target is responsible for closing that pool. But if the pool is a shared singleton managed by the parent context, the target must not close it.

Ownership rules:

| Resource | Who should close it? |
| --- | --- |
| HTTP client created inside the target | The target owning the client |
| Shared singleton connection pool | The bean/context owning the pool |
| Scheduler created exclusively for the target | The target owning the scheduler |
| Executor shared across multiple services | The component managing the executor |
| Listener registered exclusively for the target | The target unregisters the listener |
| File watcher created by the target | The target stops the watcher and closes handles |

Closing a shared resource by mistake can break other beans immediately after a refresh.

### 5.2. Callbacks Should Be Idempotent

In practice, resource closing can be invoked across different lifecycle paths or wrappers depending on how the bean is configured. Design `close()` to be safe under repeated calls:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

class ManagedTransport implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();
    private final NativeTransport delegate;

    ManagedTransport(NativeTransport delegate) {
        this.delegate = delegate;
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            delegate.close();
        }
    }
}
~~~

`AtomicBoolean` ensures only a single invocation enters the resource-closing step. If the transport library already provides an idempotent `close()`, do not wrap it needlessly just to duplicate that behavior.

### 5.3. Shut Down Resources in Order

A target may own multiple interdependent resources. For example, a message consumer using an executor and a connection:

1. Stop accepting new work.
2. Unregister the listener or consumer.
3. Wait for in-progress work to finish within a bounded timeout.
4. Shut down the executor.
5. Close the connection or client transport.
6. Clear internal state no longer needed.

The exact order depends on the API. Closing the connection before the consumer stops receiving messages can cause errors or break graceful shutdown.

### 5.4. Callbacks Must Be Time-Bounded

`refresh(String)` or `refreshAll()` destroys targets and invokes destruction callbacks. If a callback waits indefinitely for a thread, awaits a message without a deadline, or blocks waiting for a connection to return, the refresh operation can hang.

Use:

- Timeouts for graceful shutdown.
- Bounded await times for executors.
- Explicit cancellation policies on timeout.
- Contextual error logging for resource-closing failures without exposing secrets.
- Metrics for shutdown duration and callback failure counts.

Do not swallow exceptions inside callbacks without recording them. A resource that fails to close can leak connections, threads, or file descriptors.

## 6. Complete Example: Refreshing a Client with Resources

Suppose `PartnerClient` creates a transport bound to a URL from configuration. When the URL changes, the application wants to close the old transport and create a new one.

### 6.1. Configuration

~~~yaml
partner:
  api:
    base-url: https://partner-v1.internal
    connect-timeout: 500ms
    read-timeout: 2s
~~~

### 6.2. Properties

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    private URI baseUrl;
    private Duration connectTimeout = Duration.ofMillis(500);
    private Duration readTimeout = Duration.ofSeconds(2);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

### 6.3. Refreshable Bean

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerApiProperties.class)
class PartnerConfiguration {

    @Bean(destroyMethod = "close")
    @RefreshScope
    PartnerClient partnerClient(PartnerApiProperties properties) {
        return new PartnerClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout(),
                properties.getReadTimeout()
        );
    }
}
~~~

`PartnerClient` is a target with its own lifecycle. `destroyMethod = "close"` ensures the destruction callback is registered for the target.

### 6.4. Target Holding and Releasing the Transport

~~~java
public class PartnerClient implements AutoCloseable {

    private final PartnerTransport transport;

    public PartnerClient(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout
    ) {
        this.transport = PartnerTransport.open(
                baseUrl,
                connectTimeout,
                readTimeout
        );
    }

    public PartnerResponse send(PartnerRequest request) {
        return transport.send(request);
    }

    @Override
    public void close() {
        transport.close();
    }
}
~~~

`PartnerTransport` represents the application's HTTP transport. In a real project, it can wrap a specific HTTP client and connection manager. `close()` must close the exact resources created by the target.

### 6.5. Consumer Holding the Proxy

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderPartnerGateway {

    private final PartnerClient partnerClient;

    public OrderPartnerGateway(PartnerClient partnerClient) {
        this.partnerClient = partnerClient;
    }

    public PartnerResponse submit(PartnerRequest request) {
        return partnerClient.send(request);
    }
}
~~~

`OrderPartnerGateway` is created once and holds a reference to the scoped proxy. After refresh, the gateway still calls that same reference; the proxy forwards calls to the scope's current target.

### 6.6. What Happens When the Endpoint Changes?

~~~mermaid
sequenceDiagram
    participant Admin as Refresh trigger
    participant Env as Environment
    participant Scope as RefreshScope
    participant Proxy as PartnerClient proxy
    participant Old as Target v1
    participant New as Target v2
    Admin->>Env: Update base-url
    Admin->>Scope: refresh("partnerClient")
    Scope->>Old: Run destruction callback close()
    Scope-->>Admin: Cache entry removed
    Note over Proxy: Proxy remains held by OrderPartnerGateway
    OrderPartnerGateway->>Proxy: send(request)
    Proxy->>Scope: Get current target
    Scope->>New: Create target with new base-url
    New-->>Proxy: Target initialized
    Proxy->>New: send(request)
~~~

The diagram illustrates refreshing a single bean. With `refreshAll()`, every cached target in refresh scope is handled similarly.

## 7. Refreshing One Bean or the Entire Scope

Spring Cloud provides the `RefreshScope` bean to control the target cache.

### 7.1. `refresh(String beanName)`

Method:

~~~java
boolean refreshed = refreshScope.refresh("partnerClient");
~~~

The name passed in is the regular bean name. `RefreshScope` handles mapping to the scoped target name when necessary.

- `true`: the corresponding target was in the cache and was destroyed from the scope.
- `false`: there was no cached target under that name to destroy.

A `true` value does not mean the new target has been created or connected to dependencies successfully. It indicates the current target was removed from the cache.

### 7.2. `refreshAll()`

~~~java
refreshScope.refreshAll();
~~~

This method destroys existing targets across the context's entire refresh scope. Proxies remain alive; targets are recreated when proxies are used afterward.

Only use `refreshAll()` when multiple beans genuinely need to pick up new configuration. If only one endpoint changed, refreshing the specific bean limits blast radius and lowers reinitialization cost.

### 7.3. The `RefreshScopeRefreshedEvent` Event

After refreshing a single bean or the entire scope, Spring Cloud publishes `RefreshScopeRefreshedEvent`. Listeners can use this event to log activity, update metrics, or trigger an appropriate coordination task.

Do not treat this event as proof that new targets initialized successfully. It reflects refresh scope activity; creating new targets may occur on a subsequent proxy call.

## 8. Triggering Refresh via Actuator

If the application includes Spring Boot Actuator and Spring Cloud Context, refresh functionality can be exposed via a management endpoint.

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

The refresh endpoint is typically invoked via HTTP `POST`:

~~~http
POST /actuator/refresh
~~~

This endpoint triggers the context refresh process: updating `Environment` via the application's mechanism, rebinding eligible configuration beans, and refreshing the refresh scope.

Actuator dependencies and appropriate Spring Cloud components must be present. Do not expose the endpoint solely by writing YAML if the endpoint implementation is missing from the classpath.

### 8.1. Securing the Endpoint

The refresh endpoint can alter runtime configuration and trigger resource recreation. Therefore:

- Expose it only on the required management interface.
- Protect it with authentication and authorization.
- Restrict network access.
- Do not allow public clients to call refresh.
- Audit the caller, timestamp, and outcome.
- Do not include secrets or full configuration contents in logs.

If using Spring Cloud Bus to broadcast refreshes to multiple instances, control permission to publish events and monitor outcomes on each instance. Refreshing one instance does not automatically refresh every replica.

## 9. Refreshing Targets and Releasing Resources Under Concurrent Requests

In production, a target may be actively serving many requests when a refresh is triggered. Understand the proxy mechanics and design appropriate resource cleanup.

### 9.1. Synchronous Calls Through the Scoped Proxy

Spring Cloud uses its scope and scoped proxy mechanisms to coordinate target access with target creation/destruction. Versions provide per-bean locking mechanisms to prevent destruction callbacks from running concurrently with a guarded method invocation on a target that has a destruction callback.

This mechanism helps protect the lifecycle of synchronous calls through the proxy within the scope of that implementation. However, it does not replace draining or shutdown procedures for underlying resources.

### 9.2. Asynchronous Work Can Outlive the Method Call

For example, a target method submits work to an executor and returns immediately:

~~~java
public CompletableFuture<Result> submitAsync(Request request) {
    return executor.submit(request);
}
~~~

The call through the proxy may return while the `CompletableFuture` is still running. If the destruction callback closes the executor or connection still used by the async task, that task may fail.

For asynchronous tasks, you need a dedicated policy:

1. Stop accepting new work.
2. Track the count of in-flight tasks.
3. Wait for tasks to complete within a time limit.
4. Cancel remaining tasks according to policy.
5. Close resources once no dependent work remains.

You can use a dedicated lifecycle manager for the executor or design the target so `close()` performs a graceful shutdown. Do not rely on the scoped proxy as a distributed lock or a manager for threads outside the scope of method invocation.

### 9.3. Do Not Hold Targets Outside the Proxy

Consumers should inject the proxy and call through the proxy. Avoid extracting the real target, storing it in static fields, or passing the target out to a component not managed by Spring.

If a consumer holds a direct reference to the old target, it may continue calling an already-destroyed object after refresh. This defeats the purpose of the scoped proxy.

### 9.4. Callbacks Can Slow Down Refresh Operations

If a callback closes a connection pool with a long wait time, `refreshAll()` can take significant time. Measure target destruction duration and avoid callbacks performing unbounded network operations.

If a resource requires an extended shutdown, consider an explicitly coordinated out-of-band drain mechanism, while still ensuring the target is never used after the resource closes.

## 10. Cases That Do Not Refresh Automatically

### 10.1. `@RefreshScope` on `@Configuration` Does Not Propagate to Every `@Bean`

Example:

~~~java
@Configuration
@RefreshScope
class PartnerConfiguration {

    @Bean
    PartnerClient partnerClient(PartnerProperties properties) {
        return new PartnerClient(properties.getBaseUrl());
    }

    @Bean
    PartnerMetrics partnerMetrics() {
        return new PartnerMetrics();
    }
}
~~~

Annotating a configuration class does not mean every bean created by its `@Bean` methods lives in refresh scope.

If `PartnerClient` needs to be recreated, place `@RefreshScope` directly on the corresponding bean method or bean class:

~~~java
@Bean(destroyMethod = "close")
@RefreshScope
PartnerClient partnerClient(PartnerProperties properties) {
    return new PartnerClient(properties.getBaseUrl());
}
~~~

If another bean depends on a bean created from changing configuration, that dependent bean may also need refreshing or a different dynamic configuration design.

### 10.2. Unsupported Refreshable Beans

Some beans may be excluded from refresh due to their implementation or specialized lifecycle. Current Spring Cloud documentation cites `HikariDataSource` as a default example in `spring.cloud.refresh.never-refreshable`.

Do not force a connection pool into refresh scope using annotations alone if the implementation does not support it. Review the `never-refreshable` list, how auto-configuration creates the bean, and whether the pool can be closed safely. If runtime datasource changes are required, design a verified pool replacement and connection-draining strategy for the active implementation.

### 10.3. `extra-refreshable` and `never-refreshable`

Some beans created by auto-configuration cannot be directly annotated in application code. Spring Cloud provides these properties:

| Property | Role |
| --- | --- |
| `spring.cloud.refresh.extra-refreshable` | Add bean names or class names to place in refresh scope |
| `spring.cloud.refresh.never-refreshable` | Declare bean names or class names excluded from refresh/rebind |

Illustrative configuration example:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable:
        - com.example.PartnerTransport
      never-refreshable:
        - com.zaxxer.hikari.HikariDataSource
~~~

Use these lists strictly according to your Spring Cloud version's semantics. Do not add a class to `extra-refreshable` just to work around a lifecycle error. First confirm the proxy can be created, the bean can be reinitialized, and the old resource has proper closing callbacks.

### 10.4. `@ConfigurationProperties` and Constructor Binding

Spring Cloud has a rebinding mechanism for `@ConfigurationProperties` beans. Rebinding typically updates the configuration object via its own mechanism; it does not mean replacing the target objects of every bean holding configuration.

If you need an object with consistent state across refreshes, consider placing the bean in `@RefreshScope`. Objects using constructor binding—including constructor-bound Java records—have refresh limitations and should not be assumed to rebind like normal mutable beans.

## 11. Lifecycle When `ApplicationContext` Closes

Refresh scope also participates in application shutdown lifecycle. When the context closes:

- Targets still cached with destruction callbacks are destroyed.
- Resource-closing callbacks execute per Spring's lifecycle.
- Scoped proxies do not require consumers to close targets manually.
- Resources shared across another context must be closed by the context that owns them.

With parent/child context hierarchies, determine which context a bean belongs to and which context manages the target's lifecycle. Do not let a child close a singleton resource still used by a parent or sibling.

During production shutdown, coordinate with readiness/load balancers:

1. Take the instance out of rotation for new traffic.
2. Wait for current requests to finish within the grace period.
3. Close the `ApplicationContext`.
4. Allow Spring to run destruction callbacks on remaining live targets.
5. Confirm connections, executors, and listeners have stopped.

Closing the context does not replace draining traffic beforehand.

## 12. Testing Destruction Callbacks and Target Recreation

Tests should prove three things: the first target is created, destruction callbacks run on refresh, and a new target is created the next time the proxy is used.

### 12.1. Test Bean with Lifecycle Counters

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class LifecycleCounters {
    final AtomicInteger created = new AtomicInteger();
    final AtomicInteger destroyed = new AtomicInteger();
}

class RefreshableResource implements AutoCloseable {

    private final int id;
    private final LifecycleCounters counters;

    RefreshableResource(LifecycleCounters counters) {
        this.counters = counters;
        this.id = counters.created.incrementAndGet();
    }

    int id() {
        return id;
    }

    @Override
    public void close() {
        counters.destroyed.incrementAndGet();
    }
}
~~~

### 12.2. Registering the Refreshable Bean

~~~java
@TestConfiguration(proxyBeanMethods = false)
class RefreshLifecycleTestConfiguration {

    @Bean
    LifecycleCounters lifecycleCounters() {
        return new LifecycleCounters();
    }

    @Bean(destroyMethod = "close")
    @RefreshScope
    RefreshableResource refreshableResource(
            LifecycleCounters lifecycleCounters
    ) {
        return new RefreshableResource(lifecycleCounters);
    }
}
~~~

Spring Cloud Context must be on the test runtime classpath to register the `refresh` scope. The test context must also import this configuration.

### 12.3. Testing Single-Bean Refresh

~~~java
@SpringBootTest
@Import(RefreshLifecycleTestConfiguration.class)
class RefreshLifecycleTest {

    @Autowired
    RefreshScope refreshScope;

    @Autowired
    RefreshableResource resource;

    @Autowired
    LifecycleCounters counters;

    @Test
    void destroysOldTargetAndCreatesNewTargetOnNextCall() {
        int firstId = resource.id();

        assertThat(counters.created.get()).isEqualTo(1);
        assertThat(counters.destroyed.get()).isEqualTo(0);

        assertThat(refreshScope.refresh("refreshableResource")).isTrue();

        assertThat(counters.destroyed.get()).isEqualTo(1);
        assertThat(counters.created.get()).isEqualTo(1);

        int secondId = resource.id();

        assertThat(secondId).isNotEqualTo(firstId);
        assertThat(counters.created.get()).isEqualTo(2);
        assertThat(counters.destroyed.get()).isEqualTo(1);
    }
}
~~~

Key observations in this test:

- The first `resource.id()` call makes the proxy retrieve the target.
- `refresh("refreshableResource")` destroys the old target and runs `close()`.
- The `created` counter has not incremented right after refresh because the new target has not been requested yet.
- The next `resource.id()` call causes the scope to create a new target.
- Different IDs prove the proxy switched to a new target.

This is an illustrative test example; a project must add JUnit, AssertJ, Spring Boot Test imports, and context configuration compatible with its release train.

### 12.4. Testing `refreshAll`

You can extend the test to create two beans in refresh scope, call `refreshAll()`, and verify both targets' callbacks were invoked. Then call through each proxy and confirm each bean is recreated when needed.

### 12.5. Testing Errors When Closing Resources

Include tests for:

- Closing callback runs exactly once for an initialized target.
- An uninitialized target has no resources to close.
- `close()` safely handles an already-closed resource.
- Errors closing a resource are logged/recorded.
- A new target is not created if consumers have not accessed the proxy.
- If the new target fails to initialize, the error surfaces on the proxy call and is observable via health/logs.

Do not only assert that `refreshScope.refresh(...)` returns `true`; verify the callback and new target creation.

## 13. Observing and Operating Refresh Scope

In production, monitor:

| Signal | Meaning |
| --- | --- |
| Refresh count per bean | Shows which beans are frequently refreshed |
| Destruction callback duration | Detects slow resource-closing callbacks |
| New targets created | Detects targets being recreated repeatedly |
| Target initialization errors | Shows whether new configuration can build clients/pools |
| Resource-closing errors | Detects unreleased connections/threads/file handles |
| Refresh scope health | Observes rebind or reinitialization errors when the health indicator is enabled |
| Readiness and request error rate | Detects impact on traffic during refresh |

Spring Cloud includes `RefreshScopeHealthIndicator` in current versions to track certain refresh/rebind failures. You can disable the health indicator if needed:

~~~yaml
management:
  health:
    refresh:
      enabled: false
~~~

Only disable it when alternative observability is in place. When refreshing critical beans, verify readiness or run a probe after the new target is initialized.

### 13.1. Events Do Not Replace Metrics

`RefreshScopeRefreshedEvent` is useful for recording refresh activity. However, an event does not report exact close durations, number of released connections, or quality of the new target. Add structured metrics and logs around target creation and destruction.

### 13.2. Distinguishing a Successful Refresh from Application Readiness

A refresh may have cleared the cache and run destruction callbacks, yet the new target has not been created yet. If the new target needs to connect to a remote service and the new endpoint is invalid, the next request may fail.

For critical beans, operational procedures should include post-refresh verification: invoke a test operation, check health, or watch for new-target initialization errors before concluding the instance picked up the configuration successfully.

## 14. Environment and Version Limitations

- Refresh scope belongs to Spring Cloud Context; appropriate dependencies and auto-configuration are required.
- `spring.cloud.refresh.enabled=false` disables refresh scope auto-configuration and related features.
- Context refresh is not supported for Spring AOT transformations and native images in current documentation; for AOT/native, set `spring.cloud.refresh.enabled=false`.
- Certain bean types such as `HikariDataSource` are in the default non-refreshable list.
- `@RefreshScope` on a `@Configuration` class does not automatically put all beans declared in that class into scope.
- APIs, non-refreshable bean lists, and auto-configuration behavior must be cross-checked against the Spring Cloud release train compatible with your Spring Boot version.
- Do not assume refreshing one instance broadcasts to all replicas; Spring Cloud Bus or an equivalent coordination mechanism is required.

When upgrading Spring Boot or Spring Cloud, re-verify proxy strategies, destruction callbacks, `spring.cloud.refresh.*` properties, and how Actuator exposes endpoints.

## 15. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Old target does not release connections | Destruction callback not registered or target lacks clear resource ownership | Use `@PreDestroy` or `@Bean(destroyMethod = "close")`; verify ownership |
| Refresh finished, yet new target has not appeared | No call went through the proxy after cache eviction | Send a probe/health check to trigger and verify the target |
| Consumer still uses old configuration | Consumer holds target directly instead of proxy, or dependent bean did not refresh | Inject scoped proxy and review dependency graph |
| `close()` is not called | Bean has no registered callback or implementation is excluded from refresh | Check bean definition, scope, and `never-refreshable` |
| Refresh disrupts async tasks | Task outlives the method call and still uses the old resource | Stop accepting tasks, drain, and close resources on a dedicated lifecycle |
| `@RefreshScope` on config class does not refresh desired bean | Annotation does not propagate to every `@Bean` method | Annotate each bean needing refresh directly |
| `HikariDataSource` is not refreshed | Listed in default `spring.cloud.refresh.never-refreshable` | Design another datasource/pool strategy and test thoroughly |
| `refresh(name)` returns false | No cached target exists under that bean name | Verify bean name and whether the target was ever initialized |
| Refresh endpoint does not exist | Missing Actuator/Context or endpoint not exposed | Check dependencies and management exposure |
| New requests fail after refresh | New target failed to initialize or new configuration is invalid | Check exceptions, property sources, and health after access |
| Shutdown hangs | Resource-closing callback blocks indefinitely | Add timeouts and bounded graceful shutdown |

## 16. Design Checklist Before Placing a Bean in Refresh Scope

Before applying `@RefreshScope`, answer:

- Does the bean actually hold state or resources depending on configuration that needs to change?
- Do consumers inject it through a scoped proxy?
- Which resources are owned by the target and need closing?
- Is a destruction callback registered?
- Is `close()` idempotent and time-bounded?
- Can async tasks continue using the resource after the method returns?
- Do any dependencies outside the scope still hold old configuration?
- Is the bean on the `never-refreshable` list?
- Do you need `extra-refreshable` for an auto-configured bean?
- Can the new configuration successfully build the new target?
- Are there tests verifying destruction callbacks and target recreation?
- Is refresh protected and monitored in production?

If there are no resources or state needing recreation, `@RefreshScope` may not be the right solution. Use typed configuration/rebinding or design a client that reads configuration dynamically if requirements are simpler.

## 17. Practice Exercises

**Exercise 1 — Draw the lifecycle.** Diagram the sequence from when a consumer calls the proxy, the target is created, configuration changes, refresh is invoked, destruction callbacks run, and the new target is created.

**Exercise 2 — Closing resources.** Create a refreshable bean owning an `ExecutorService`. Write a callback that stops accepting tasks, waits for completion within a deadline, and shuts down the executor. Test shutdown counts.

**Exercise 3 — Bean method callback.** Create `@Bean(destroyMethod = "close") @RefreshScope`. Call `refresh(beanName)` and prove `close()` runs before the new target is created.

**Exercise 4 — Proxy and target.** Inject a refreshable bean into a singleton consumer. Call through the consumer before and after refresh; prove the consumer holds the same proxy while the target ID changes.

**Exercise 5 — Async work.** Create a target method that submits a task to an executor and returns. Refresh while the task is running; observe the risks and design a graceful drain.

**Exercise 6 — Excluded beans.** Inspect the behavior of a `HikariDataSource` under refresh configuration. Read `spring.cloud.refresh.never-refreshable` and propose a safe datasource update strategy.

**Exercise 7 — Operational endpoint.** Expose `/actuator/refresh` locally, invoke it with HTTP POST, then inspect callbacks and health. Design authentication/authorization before bringing the endpoint to real environments.

**Exercise 8 — Scope-wide refresh.** Create two refreshable beans with separate resources, call `refreshAll()`, and measure destruction duration. Verify new targets are only created when each proxy is called again.

## 18. Key Takeaways and Reference Sources

- `@RefreshScope` places a bean in the `refresh` scope and provides a scoped proxy to consumers.
- Targets are cached; refresh evicts the target from cache and runs registered destruction callbacks.
- Proxies continue to exist. New targets are created from the bean definition when proxies are accessed after refresh.
- Use `@PreDestroy`, `DisposableBean`, or `@Bean(destroyMethod = "...")` to release resources.
- Targets should only close resources they own directly; shared resources must be managed by the components owning them.
- `refresh(String)` refreshes one bean; `refreshAll()` refreshes all targets in the scope.
- A successful cache refresh does not prove new targets have been created or connected successfully.
- Async tasks, connection pools, and resources with long shutdowns require dedicated drain/timeout policies.
- `HikariDataSource` is a default non-refreshable example; AOT/native images do not support Context Refresh per current documentation.
- In operations, monitor destruction duration, callback errors, new-target creation errors, and post-refresh readiness.

Official sources to cross-check for your project's Spring Cloud/Spring Boot versions:

1. [Spring Cloud Context – Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Javadoc – `RefreshScope`](https://docs.spring.io/spring-cloud-commons/docs/current/apidocs/org/springframework/cloud/context/scope/refresh/RefreshScope.html)
3. [Spring Cloud Javadoc – `GenericScope`](https://docs.spring.io/spring-cloud-commons/docs/current/apidocs/org/springframework/cloud/context/scope/GenericScope.html)
4. [Spring Framework Reference – Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
5. [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
6. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
