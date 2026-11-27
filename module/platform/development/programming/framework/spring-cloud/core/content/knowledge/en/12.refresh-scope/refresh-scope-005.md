# Invalidating Targets and Recreating Them on the Next Call

Spring Cloud's `@RefreshScope` allows a bean to be recreated when configuration changes and a refresh process is triggered. The key mechanism lies in the **target cache**: Spring keeps a stable proxy for other beans to call, while the actual executing object behind the proxy is stored in the scope. During refresh, Spring destroys the cached target. The next call through the proxy creates a new target with the current configuration.

Thus, refresh scope does not necessarily recreate the object at the exact moment it receives a refresh command. It **invalidates the current target**, then defers creating the new target until the next access. Understanding this lifecycle helps avoid retaining stale references, predict resource release, and design safe refreshes in Spring Cloud applications.

## 1. The Proxy and the Target Are Two Different Objects

When a bean is placed in refresh scope, the bean that other components receive is typically a **scoped proxy**. The proxy serves as a stable access point. On every method invocation, the proxy looks up the current target in the refresh scope and forwards the call.

You can visualize it as:

~~~text
CatalogService
     |
     | inject
     v
Refresh-scoped proxy
     |
     | resolve target on method call
     v
RefreshScope target cache
     |
     +-- current target: RemoteCatalogClient #1
~~~

Two concepts:

- **Proxy:** object injected into dependent beans; typically lives throughout the context's lifecycle.
- **Target:** the real object holding the bean's state and logic; the scope manages targets in a cache keyed by bean name.

If a target has already been created, the proxy forwards calls to the cached target. If the target has not yet been created or has been destroyed, the scope uses the object factory to create a new target and stores it.

### 1.1. Why Is a Proxy Needed?

Suppose `CatalogService` is created once at application startup and injects a client whose endpoint needs to change with configuration. If the service holds the old client object directly, configuration changes cannot automatically replace that reference.

Refresh scope solves this by having the service hold a proxy. The proxy can resolve a new target without needing to recreate the entire `CatalogService` or `ApplicationContext`.

~~~mermaid
sequenceDiagram
    participant S as CatalogService
    participant P as Scoped proxy
    participant R as RefreshScope
    participant T1 as Target #1

    S->>P: getCatalog()
    P->>R: Get target by bean name
    R-->>P: Target #1 (cache hit)
    P->>T1: getCatalog()
    T1-->>S: Result
~~~

The proxy keeps the call site stable; the target can change across refreshes.

## 2. The Target Cache Is Populated on Demand

Refresh scope operates with lazy target creation. The bean proxy can be injected into a consumer before the target is actually initialized. When the first method is called, the scope creates the target if it is not yet in the cache.

Simplified lifecycle:

~~~mermaid
stateDiagram-v2
    [*] --> NotCreated: Bean proxy created
    NotCreated --> Cached: First call / create target
    Cached --> Invalidated: refresh(beanName)
    Invalidated --> NewlyCached: Next call / create new target
    NewlyCached --> Invalidated: refresh(beanName)
    NewlyCached --> Destroyed: Context closed
~~~

This leads to several consequences:

- Injecting the proxy does not guarantee the target has been initialized.
- Refreshing a target that was never created does not need to build a new target right away.
- A new target typically appears only when the next call arrives.
- If no call happens after refresh, a new target may not be created yet.
- Errors when creating a new target may appear on the first request after refresh, rather than at the moment the refresh command is issued.

This is an important distinction between "refresh completed" and "all new targets were created successfully." Refresh scope only manages the cache and target lifecycle according to access demand.

## 3. Declaring a Bean with `@RefreshScope`

Consider a client calling a catalog service. We want to change its endpoint via configuration without having to recreate every service that uses the client.

Configuration:

~~~yaml
catalog:
  api:
    base-url: https://catalog-v1.example.internal
    connect-timeout: 2s
~~~

Property group:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.api")
public class CatalogApiProperties {
    private String baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Register this configuration group with `@ConfigurationPropertiesScan` on the startup class or `@EnableConfigurationProperties(CatalogApiProperties.class)` on a configuration class. When using Spring Cloud Config, the refresh workflow must update `Environment` and rebind configuration beans according to your version's mechanism before the client target is recreated.

Bean placed in refresh scope:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    @RefreshScope
    RemoteCatalogClient remoteCatalogClient(CatalogApiProperties properties) {
        return new RemoteCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }
}
~~~

Illustrative client:

~~~java
import java.time.Duration;

public class RemoteCatalogClient {
    private final String baseUrl;
    private final Duration timeout;

    public RemoteCatalogClient(String baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public String endpoint() {
        return baseUrl;
    }

    public Duration timeout() {
        return timeout;
    }

    public String getCatalog() {
        // Send request using current baseUrl and timeout.
        return "Catalog from " + baseUrl;
    }
}
~~~

Service depending on the refresh-scoped bean:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final RemoteCatalogClient client;

    public CatalogService(RemoteCatalogClient client) {
        this.client = client;
    }

    public String loadCatalog() {
        return client.getCatalog();
    }
}
~~~

Spring injects the scoped proxy into `CatalogService`. When `loadCatalog()` calls `client.getCatalog()`, the proxy resolves the current target. After the target is invalidated, that same proxy reference will lead to the new target on the next call.

This example is illustrative code; a real client needs proper HTTP connection pool configuration, timeouts, TLS, authentication, and error handling. The target class must be compatible with the proxy type used. With subclass-based proxies, avoid `final` classes or methods; you can design around an interface and configure the appropriate proxy mode if needed.

## 4. Invalidating a Single Target with `refresh(beanName)`

If only one bean needs to be recreated, you can inject `RefreshScope` and call `refresh(beanName)`:

~~~java
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.stereotype.Component;

@Component
public class CatalogRefreshManager {
    private final RefreshScope refreshScope;

    public CatalogRefreshManager(RefreshScope refreshScope) {
        this.refreshScope = refreshScope;
    }

    public void refreshCatalogClient() {
        refreshScope.refresh("remoteCatalogClient");
    }
}
~~~

The name passed in is the **bean name** registered in the `ApplicationContext`, not the class name, property prefix, or service ID. With `@Bean` methods, the default name is usually the method name; if an explicit name is declared with `@Bean(name = "...")`, use that exact name.

When `refresh("remoteCatalogClient")` is called, the scope destroys the cached target for that bean. The proxy does not need to be re-injected. The next call through the proxy asks the scope to create a new target.

### 4.1. Refreshing One Bean Does Not Mean Refreshing the Entire Application

Only the target with the specified name is invalidated. Other beans—including other refresh-scoped beans—keep their current targets unless they are refreshed individually or included in a full refresh.

This is useful when:
- A single client needs to change its endpoint or credentials.
- A narrowly scoped setting changes independently.
- You want to avoid recreating unrelated targets.

Make sure the properties that the new bean needs to read have already been updated in `Environment` before invalidating the target. If you only call `refresh(beanName)` while `Environment` still holds old values, the new target will be created from the old configuration.

## 5. Invalidating All Targets with `refreshAll()`

When you need to invalidate every target managed by refresh scope, call:

~~~java
refreshScope.refreshAll();
~~~

This command destroys existing targets in the refresh scope. Proxies remain the consumers' access points. New targets are recreated when the corresponding beans are next invoked.

Comparison:

| API | Scope | Behavior |
| --- | --- | --- |
| `refresh("remoteCatalogClient")` | One bean by name | Destroys that bean's cached target |
| `refreshAll()` | All targets in refresh scope | Destroys the entire target cache belonging to the scope |
| `ContextRefresher.refresh()` | Application-level configuration refresh workflow | Refreshes `Environment` via the configured mechanism and then triggers refresh scope |

`refreshAll()` only affects refresh-scoped targets. It does not restart the JVM, recreate the entire `ApplicationContext`, or update data on Config Server.

## 6. How Does Destroying the Old Target and Creating the New Target Happen?

When a target is invalidated, the scope destroys the managed object and invokes destruction callbacks supported by the bean. The target is then removed from the cache.

Detailed flow:

~~~mermaid
sequenceDiagram
    participant Ops as Refresh trigger
    participant Scope as RefreshScope
    participant Cache as Target cache
    participant Proxy as Scoped proxy
    participant Factory as Bean factory

    Ops->>Scope: refresh("remoteCatalogClient")
    Scope->>Cache: Remove cached target
    Scope->>Scope: Run destruction callbacks
    Scope-->>Ops: Target refresh complete
    Note over Proxy,Cache: Proxy still exists, cache has no target
    Proxy->>Scope: Next call
    Scope->>Factory: Create new target
    Factory-->>Scope: New RemoteCatalogClient
    Scope->>Cache: Store new target
    Scope-->>Proxy: Return new target
    Proxy->>Proxy: Forward method invocation
~~~

A target can release resources via `@PreDestroy`, `DisposableBean`, or a destroy method if configured properly. For example, a target managing an HTTP client or connection must close it when destroyed.

Do not let a target create external resources without declaring how to release them. If the old target fails to close connection pools, threads, or file handles, repeated refreshes can cause resource leaks.

### 6.1. Old Targets and In-Flight Calls

Refresh does not switch a mid-execution call over to the new target. A request that already started using the old target can continue until the method completes; invalidation affects target resolution for subsequent accesses.

In systems with concurrent traffic, design targets with a safe lifecycle:
- Avoid closing resources while requests are still using them unless the client's lifecycle guarantees safety.
- Set reasonable request timeouts.
- Check whether the client library supports close/drain semantics.
- Use a graceful shutdown/connection-pool strategy suited for target replacement.

Do not treat refresh scope as an atomic switchover mechanism for all in-flight requests to a new configuration.

## 7. Refreshing Targets Differs from Updating `Environment`

This is the most common point of confusion.

`RefreshScope.refresh(name)` or `refreshAll()` **invalidates the target cache**. They do not fetch new configuration from Config Server, modify property sources, or change values in `Environment`.

For remote configuration updates, a complete workflow typically requires:
1. Updating the configuration source, such as Config Server or another property source.
2. Config Client/`ContextRefresher` loading or applying the new values into `Environment`.
3. The refresh scope mechanism invalidating cached targets.
4. The next call creating a new target and reading current properties.

Diagram:

~~~mermaid
flowchart TD
    A["Config Server / config source changed"] --> B["Config Client / ContextRefresher"]
    B --> C["Update Environment and PropertySource"]
    C --> D["RefreshScope.refreshAll()"]
    D --> E["Target cache invalidated"]
    E --> F["Proxy receives next call"]
    F --> G["Create new target from current configuration"]
~~~

If you skip updating `Environment`, the new target may still use old values. If you update `Environment` without refreshing beans that need to re-read properties, beans holding old state may continue operating with the previous configuration.

### 7.1. Triggering via `ContextRefresher`

In applications using Spring Cloud Context, `ContextRefresher` coordinates refreshing `Environment` and refresh scope according to the version's mechanism. You can invoke it from an internal administrative component when truly needed:

~~~java
import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.stereotype.Component;

@Component
public class ApplicationRefreshManager {
    private final ContextRefresher contextRefresher;

    public ApplicationRefreshManager(ContextRefresher contextRefresher) {
        this.contextRefresher = contextRefresher;
    }

    public void refreshConfiguration() {
        contextRefresher.refresh();
    }
}
~~~

How properties are reloaded depends on `PropertySourceLocator`, Config Client, Config Data/Bootstrap mode, and the Spring Cloud version. Do not assume calling this method reloads arbitrary sources or automatically synchronizes every replica in a cluster.

### 7.2. Actuator Endpoint and Security

Some Spring Cloud setups provide a refresh endpoint via Actuator to trigger the refresh workflow. When using it, make sure to:
- Choose dependencies and endpoint configuration appropriate for your version.
- Expose the endpoint intentionally via management configuration.
- Protect it with authentication/authorization and restrict network access.
- Audit configuration change operations.
- Prevent external users from arbitrarily triggering refresh.
- Inspect endpoint responses and configuration status afterward.

Never expose `/actuator/refresh` publicly. It is an administrative operation that alters runtime behavior and causes targets to be recreated on the next access.

## 8. What Refresh Scope Does Not Do Automatically

Refresh scope only manages target lifecycles for beans in the scope. It does not automatically:
- Modify configuration files or values in Config Server.
- Fetch new properties from arbitrary external systems.
- Refresh all singleton beans outside refresh scope.
- Restart the embedded web server or change `server.port`.
- Update DNS, registries, load balancers, or network configuration.
- Migrate in-flight requests from the old target to the new target.
- Synchronize cache state or mutable objects across replicas.
- Guarantee every bean/resource type can be safely reinitialized.

If a changed property is used to build a resource that cannot be modified at runtime, evaluate a restart/redeploy or a dedicated update mechanism.

## 9. Choosing Which Beans to Place in Refresh Scope

Place refresh scope on beans that can be safely recreated and genuinely need to re-read configuration at runtime. Examples:
- HTTP client wrappers whose endpoint or timeout changes.
- Adapters holding recreatable policies.
- Beans providing configuration details accessed through a proxy.
- Clients that do not hold long-lived business state and have clear cleanup lifecycles.

Be cautious with:
- Beans holding changing business state.
- Transaction managers, connection pools, or resources with complex lifecycles.
- Beans referenced directly as targets rather than proxies by multiple components.
- Beans whose constructors produce side effects.
- Beans requiring synchronization with other replicas.

Certain bean types cannot be safely refreshed or are excluded by Spring Cloud's default refresh list depending on version. For example, `HikariDataSource` is typically configured as `never-refreshable` in Spring Cloud. If you want to swap a datasource, use an appropriate connection pool management workflow rather than assuming `@RefreshScope` alone suffices.

### 9.1. Constructors with Side Effects

Because the new target is created on the next access, the constructor/factory method may run during the first request after refresh. If the constructor performs network calls, loads metadata, or initializes slow resources, that request may experience higher latency.

Consider:
- Keeping constructors/factory methods lightweight.
- Moving heavy initialization off the request path when appropriate.
- Checking readiness before routing traffic to the new target.
- Monitoring target creation failures and latency of the first request after refresh.

## 10. Stale References Can Defeat Refresh

Consumers should hold the scoped proxy injected by Spring. If code obtains the real target, unwraps the proxy, or stores the target in another field/static cache, that reference may continue pointing to the old object after the scope invalidates the cache.

Example of what not to do:

~~~java
// Anti-pattern illustration:
RemoteCatalogClient target = unwrapScopedProxy(client);
this.cachedTarget = target;
~~~

When the scope destroys the old target and the proxy points to the new target, `cachedTarget` may still hold the old object. Avoid:
- Unwrapping scoped proxies to cache targets.
- Copying target dependencies into static fields.
- Passing the real target into an object that outlives the proxy.
- Caching target references manually outside the scope.

Inject the proxy and call through the proxy every time it is needed. If a library forces holding a direct target, design an adapter that swaps references after refresh or use a different lifecycle mechanism.

## 11. Testing Target Invalidation and Recreation

A test can count how many times the factory method creates a target. After the first call, refresh the bean by name and call again through the proxy; the new generation must increment.

Illustrative example with Spring Boot test:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RefreshScopeTestApplication {

    static final AtomicInteger generations = new AtomicInteger();

    @Bean
    @RefreshScope
    VersionedClient versionedClient() {
        return new VersionedClient(generations.incrementAndGet());
    }

    public static class VersionedClient {
        private final int generation;

        VersionedClient(int generation) {
            this.generation = generation;
        }

        public int generation() {
            return generation;
        }
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.scope.refresh.RefreshScope;

@SpringBootTest(classes = RefreshScopeTestApplication.class)
class RefreshScopeLifecycleTest {

    @Autowired
    RefreshScopeTestApplication.VersionedClient client;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void targetIsRecreatedOnNextInvocation() {
        int first = client.generation();

        refreshScope.refresh("versionedClient");

        int second = client.generation();

        assertThat(second).isGreaterThan(first);
    }
}
~~~

This test verifies that the proxy remains in use and a new target appears after invalidation. In a real test suite, manage the static `AtomicInteger` state across contexts/tests so parallel tests do not alter generation ordering. Use a per-context factory counter or reset the counter during setup.

### 11.1. Testing Destruction Callbacks

Besides verifying that a new target is created, verify that the old target is destroyed if it owns resources to release. A target can increment a counter when `@PreDestroy` runs; after calling `refresh(beanName)`, the test verifies the callback executed.

This helps catch leaked connections, threads, or resources across repeated refreshes.

### 11.2. Testing `Environment` Updates

Target lifecycle tests do not by themselves verify that Config Client fetched new configuration. A separate integration test should:
1. Provide initial property values.
2. Initialize and invoke the refresh-scoped bean to create the target.
3. Modify the property source via the test mechanism.
4. Trigger the appropriate refresh workflow.
5. Invoke the proxy again.
6. Verify the new target reads the new values.

Separating scope tests from Config Server tests helps isolate whether a bug lies in `Environment` updates or target lifecycle.

## 12. Monitoring and Operating Refresh

When refresh occurs in production, observe:
- Which bean names were refreshed.
- Start/end timestamps of invalidation.
- Whether old targets released resources cleanly.
- Whether new targets are created on the next request.
- Whether the first request after refresh shows increased latency or errors.
- Whether replicas received the same configuration and trigger.
- Whether any missing property prevented the new target from initializing.

Never log credentials or secret values when monitoring refreshes. Only log bean names, version/config revisions, status, and appropriate correlation IDs.

When multiple replicas run independently, calling refresh on one instance does not automatically refresh the remaining instances. You need a mechanism to broadcast triggers or orchestrate refreshes across instances, while ensuring every instance retrieves the same target configuration version.

## 13. Common Errors and Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Calling refresh leaves values unchanged | `Environment` was not updated; new target re-reads old values | Check property sources and effective values before/after refresh |
| Proxy still exists after refresh | Expected behavior; the proxy is the stable access point | Check target generation changes on the next call |
| New target is not created immediately after refresh | Refresh scope lazily creates targets on the next call | Send a call through the proxy and observe the factory |
| First request after refresh fails | New target is created at that moment and config/resource is invalid | Check target initialization exceptions, required properties, and connectivity |
| Bean is not refreshed | Bean is not in refresh scope or wrong bean name was passed | Check `@RefreshScope`, bean name, and scope registration |
| Old bean is still used | Consumer holds direct target reference outside the proxy | Avoid unwrapping proxies or caching targets |
| Resource leaks after multiple refreshes | Target lacks proper destruction callbacks/cleanup | Check `@PreDestroy`, destroy methods, and owned resources |
| Refreshing one replica leaves others unchanged | Trigger ran only on one process | Design broadcast/orchestration and check each instance |
| Some beans cannot be refreshed | Bean/resource is on the non-refreshable list or unsafe to recreate | Check refresh configuration and release train guidance |
| Refresh increases request latency | New target lazily initializes on the first request | Measure latency, reduce factory side effects, or perform intentional warm-up |

## Key Takeaways

Refresh scope keeps a stable proxy and caches the target behind it. When `refresh(beanName)` or `refreshAll()` is called, Spring destroys the cached target; only the next call through the proxy creates a new target. This mechanism does not automatically update `Environment`, does not refresh all singletons, and does not migrate in-flight requests to the new target. To apply external configuration, update `Environment` first, invalidate targets second, ensure old targets release resources, and test the first call after refresh.
