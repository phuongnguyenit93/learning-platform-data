# Lazy Proxy and Target Cache Mechanism of @RefreshScope

In a Spring Cloud application, a bean may retain configuration from the time it was initialized. When configuration changes, merely updating `Environment` does not necessarily change the running objects: a bean might still hold a previously bound value, a connection might have been created with an old URL, or a client might have stored an old endpoint.

`@RefreshScope` addresses this category of cases using a **scoped proxy** and a **target cache**. Other components in the application hold a reference to the stable proxy; the proxy retrieves the current target from the scope when a call arrives. During a refresh, Spring Cloud destroys the cached target. The next call through the proxy creates a new target from the bean definition and reloads the current configuration.

This lesson belongs to the **Refresh Scope** chapter of the **SPRING_CLOUD_CORE** module. The content focuses on how the proxy forwards calls, how the cache stores targets, the lifecycle before and after refresh, observing the behavior with Java examples, and testing target replacement without changing the proxy.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why `@RefreshScope` uses a scoped proxy instead of replacing every bean reference across the entire application context.
- Distinguish between **proxy**, **target bean**, **bean definition**, and **target cache**.
- Describe initial target creation, target reuse, and target destruction during refresh.
- Distinguish `RefreshScope.refresh(beanName)` from `RefreshScope.refreshAll()`.
- Recognize why the target is recreated when the next call goes through the proxy.
- Write a `@RefreshScope` bean and a singleton that uses that proxy.
- Test that the proxy keeps the same identity while the target is replaced and receives the new configuration.
- Identify limitations regarding dependent beans, constructor binding, HikariDataSource, AOT/native images, and concurrent operations.

### 1.1. Required Dependencies

`@RefreshScope` belongs to the `spring-cloud-context` module. If the application already uses a Spring Cloud starter that pulls this module onto the classpath, check the dependency graph before declaring it explicitly. If you only need Context and refresh scope, you can declare it directly:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

The version is managed by the `spring-cloud-dependencies` BOM compatible with the application's Spring Boot line. Do not pick a Context version different from the release train in use. If you want to call `/actuator/refresh` over HTTP, add `spring-boot-starter-actuator` and configure exposure/security for the endpoint.

## 2. Four Components of the Mechanism

### 2.1. Bean Definition

A bean definition is the description Spring uses to create a bean: class, constructor, dependencies, properties, init method, destroy method, and other metadata. With `@RefreshScope`, the bean definition is registered under the scope named `refresh`.

Example:

~~~java
@Component
@RefreshScope
public class GreetingTarget {
    // ...
}
~~~

`@RefreshScope` is a convenience annotation equivalent to declaring scope `refresh` and a scoped proxy. The default proxy mode is `TARGET_CLASS`, meaning Spring creates a class-based proxy for the bean.

### 2.2. Proxy

The proxy is the object injected into other beans. Those beans invoke methods on the proxy just like a normal bean. The proxy intercepts the call, looks up the current target in the scope, and forwards the call to that target.

The proxy is not the target. It can live throughout the application context's entire lifecycle, even when the target behind it has been destroyed and recreated multiple times.

### 2.3. Target Bean

The target is the instance that executes the business logic. It is created from the bean definition, receives injected dependencies, and runs initialization callbacks such as `@PostConstruct` or `InitializingBean`.

The target may hold internal state, `@Value` values, clients, or resources created from configuration. When the target is refreshed, the old instance is destroyed and a new instance is created when needed.

### 2.4. Target Cache

`RefreshScope` stores initialized targets in a cache keyed by the scoped target bean name. When the proxy needs a target, the scope checks the cache:

- Valid target exists: returns the cached target.
- No target yet: creates a target from the bean definition, initializes it, and stores it in the cache.
- Target was invalidated: creates a new target on the next access.

This cache stores **bean instances by name within the application context**. It is not a cache of individual method results, not a per-HTTP-request cache, and not a cache shared across multiple JVMs.

## 3. Proxy and Target Cache Diagram

~~~mermaid
flowchart TD
    A[Singleton service] --> P[Refresh scoped proxy]
    P --> L[Resolve target from RefreshScope]
    L --> C{Target cache has entry?}
    C -->|Yes| T1[Current target]
    C -->|No| B[Create from bean definition]
    B --> I[Inject dependencies and initialize]
    I --> S[Store target in cache]
    S --> T2[New target]
    T1 --> M[Invoke method]
    T2 --> M
    R[refresh or refreshAll] --> D[Destroy and remove cached target]
    D --> C
~~~

During a refresh, Spring Cloud removes the entry from the cache and invokes the destruction callbacks of the old target. The proxy remains the exact object held by singletons. The next method call going through the proxy will not find the old target, so the scope creates a new target.

### 3.1. Initial Target Creation Flow

Suppose `GreetingController` is a singleton and injects `GreetingTarget`:

1. Spring creates a proxy bean registered under the name `greetingTarget`.
2. `GreetingController` receives this proxy in its constructor.
3. When the controller calls `greetingTarget.render()`, the proxy asks `RefreshScope` for the target.
4. If the cache has no target yet, the scope uses the bean definition to create an instance.
5. Spring injects dependencies, binds configuration values, and runs lifecycle callbacks.
6. The scope stores the target in the cache and then forwards the `render()` call to the target.
7. Subsequent calls continue using the cached target.

Key point to remember: the proxy may be created during context startup, but refresh-scoped targets are managed with lazy semantics. Obtaining the proxy does not mean the target has been initialized; the target is fetched or created when the scope needs to serve a call.

### 3.2. Target Refresh Flow

When a refresh occurs:

1. New configuration must be placed into `Environment` via the active update mechanism.
2. `RefreshScope` invalidates the target cache for one bean or the entire scope.
3. The old target is destroyed and registered destruction callbacks are executed.
4. The proxy remains injected in singletons just as before.
5. On the next call, the proxy requests the target from the scope.
6. The scope creates a new target from the bean definition; placeholders and expressions are re-evaluated, dependencies are re-injected, and initialization callbacks run.

Refresh does not proactively create all new targets immediately when clearing the cache. Recreation happens when the bean is next accessed. If a bean is not used after refresh, its new target may not be created yet.

## 4. Java Example: Tracking Proxy and Target Identity

Let's build `GreetingTarget` with an incrementing ID. Each time a target is created, `@PostConstruct` logs a message; when the target is destroyed, `@PreDestroy` logs a message.

### 4.1. Refresh-Scoped Bean

~~~java
package com.example.refresh;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class GreetingTarget {

    private static final Logger log =
            LoggerFactory.getLogger(GreetingTarget.class);

    private static final AtomicInteger SEQUENCE = new AtomicInteger();

    private final int targetId = SEQUENCE.incrementAndGet();

    @Value("${greeting.message:Hello}")
    private String message;

    @PostConstruct
    public void initialize() {
        log.info("Create GreetingTarget id={}, message={}",
                targetId, message);
    }

    @PreDestroy
    public void destroy() {
        log.info("Destroy GreetingTarget id={}", targetId);
    }

    public String render() {
        return "target-" + targetId + ": " + message;
    }
}
~~~

The class must not be declared `final` because the annotation creates a class-based proxy by default. Methods invoked through the proxy must be interceptable according to the selected proxy mode. If designing the bean around an interface, you can consider `ScopedProxyMode.INTERFACES`.

### 4.2. Singleton Using the Proxy

~~~java
package com.example.refresh;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final GreetingTarget greetingTarget;

    public GreetingService(GreetingTarget greetingTarget) {
        this.greetingTarget = greetingTarget;
    }

    public String greeting() {
        return greetingTarget.render();
    }
}
~~~

`GreetingService` is a singleton. Its constructor only receives the `GreetingTarget` proxy. After refresh, the `greetingTarget` field still points to the old proxy, but the proxy will look up the new target on the next `render()` call.

### 4.3. Controller for Observation

~~~java
package com.example.refresh;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting() {
        return greetingService.greeting();
    }
}
~~~

Each request to `/greeting` goes through the `GreetingService` singleton and then calls the proxy. If the target has been refreshed, the next first request triggers creation of the new target.

### 4.4. Initial Configuration

`application.yml`:

~~~yaml
greeting:
  message: "Hello"

management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

This Actuator configuration is only to demonstrate the refresh endpoint in a learning environment. In production, expose only required endpoints and protect them with Spring Security, authentication/authorization, HTTPS, and network policies. Do not expose `/actuator/refresh` to Internet users or callers without administrative privileges.

## 5. Observing the Target Cache Across Calls

After running the application, call:

~~~bash
curl http://localhost:8080/greeting
~~~

The first result looks like:

~~~text
target-1: Hello
~~~

Call again:

~~~bash
curl http://localhost:8080/greeting
~~~

The result is still:

~~~text
target-1: Hello
~~~

The target is not recreated for each request. The scope returns the cached instance.

Now update the configuration value through a source the application can reload—for example, Config Server—and then call:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

After the refresh endpoint completes, call again:

~~~bash
curl http://localhost:8080/greeting
~~~

Illustrative output:

~~~text
target-2: Bonjour
~~~

Expected logs look like:

~~~text
Create GreetingTarget id=1, message=Hello
Destroy GreetingTarget id=1
Create GreetingTarget id=2, message=Bonjour
~~~

Order matters: update `Environment` first, invalidate the cache second, and only then will the new target be created with the new value. If you only call `refreshAll()` before `Environment` receives the new configuration, the next target will still be created from the old value.

## 6. Refresh One Bean or the Entire Scope?

`RefreshScope` provides two main operations:

~~~java
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.stereotype.Service;

@Service
public class RefreshOperations {

    private final RefreshScope refreshScope;

    public RefreshOperations(RefreshScope refreshScope) {
        this.refreshScope = refreshScope;
    }

    public boolean refreshGreetingTarget() {
        return refreshScope.refresh("greetingTarget");
    }

    public void refreshAllScopedBeans() {
        refreshScope.refreshAll();
    }
}
~~~

| API | Effect | When to use |
| --- | --- | --- |
| `refresh(beanName)` | Destroys the cached target for a single bean | Only one bean has configuration or resources that need reinitialization |
| `refreshAll()` | Destroys all targets in the refresh scope | A configuration update affects multiple beans |

The name passed to `refresh(beanName)` is the Spring bean name. For scoped proxies, Spring Cloud translates the normal bean name to the internal target name to invalidate the right cache entry. In the example, the bean name is `greetingTarget`, not the fully qualified class name.

If the bean does not yet have a target in the cache, `refresh(beanName)` may return `false` because there is no instance to destroy. That does not mean the proxy was deleted or the bean definition disappeared.

### 6.1. Actuator Endpoint

Spring Cloud Context provides the `POST /actuator/refresh` endpoint to run the refresh workflow. This endpoint requires Actuator and exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

In an application using Spring Cloud Config, the refresh endpoint asks Config Client to update configuration via the context refresher mechanism and then refreshes scoped beans. The response typically contains the list of changed keys. Endpoint details and behavior depend on the release train.

Expose this endpoint only on a protected management interface. `POST /actuator/refresh` can cause multiple beans to be destroyed and recreated on the next request, making it an administrative operation with runtime impact.

### 6.2. Updating Multiple Instances

`RefreshScope` is a cache within a single application context of a single JVM. When a system runs multiple replicas, calling refresh on one instance does not automatically clear the target caches of other instances.

You can use Spring Cloud Bus to broadcast refresh events to participating instances on the bus. Without Bus, your deployment pipeline must invoke the refresh mechanism on each instance via a protected workflow. Monitor the outcome per instance because some instances might update slowly or fail when creating a new target.

## 7. Why Does the Proxy Stay the Same After Refresh?

Look at the two separate objects:

~~~text
GreetingService (singleton)
        |
        | field greetingTarget
        v
  Refresh scoped proxy  --------------------+
        |                                   |
        | before refresh                    | after refresh
        v                                   v
  target-1: Hello                     target-2: Bonjour
~~~

The singleton holds a reference to the proxy. When the target is destroyed, Spring does not have to find every singleton holding a reference and replace their fields. The proxy remains in place and can look up the new target in the scope.

This is the main benefit of a scoped proxy: consuming beans do not need to know the target changed. They keep calling the same reference, while the scope manages the target lifecycle behind it.

### 7.1. Do Not Store Copies of Values from the Target in a Singleton

The following example does not update automatically after refresh:

~~~java
@Service
public class CachedGreeting {

    private final String startupMessage;

    public CachedGreeting(GreetingTarget target) {
        this.startupMessage = target.render();
    }

    public String message() {
        return startupMessage;
    }
}
~~~

The constructor calls the proxy and retrieves a string at initialization time. Thereafter, the singleton holds that string; the proxy switching to a new target cannot change the value already copied into `startupMessage`.

If you need to read fresh configuration, invoke the method through the proxy when needed, or design the service to accept an abstraction that reads configuration at the time of use. Do not copy data from a target into a singleton field and expect the scope to update that field automatically.

### 7.2. Do Not Keep Direct References to the Target

The scoped proxy only dispatches calls that go through the proxy. If code explicitly unwraps the proxy, grabs the internal target and stores it, or creates the object with `new`, that reference does not automatically switch to the new target after refresh.

Similarly, if a method returns a mutable object belonging to the target and the caller keeps that object long-term, the returned object remains the old one. The proxy can only dispatch subsequent calls made through the proxy; it cannot replace references that were already handed out earlier.

## 8. Proxy Modes and Class Requirements

`@RefreshScope` defaults to `ScopedProxyMode.TARGET_CLASS`. Spring creates a class-based proxy so other beans can inject by class type.

If you want an interface-based proxy:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

public interface Greeting {
    String render();
}

@Component
@RefreshScope(proxyMode = ScopedProxyMode.INTERFACES)
public class DefaultGreeting implements Greeting {

    @Override
    public String render() {
        return "Hello";
    }
}
~~~

When using an interface proxy, injection sites should depend on the `Greeting` interface. Injecting by the concrete class `DefaultGreeting` may fail because the interface proxy might not satisfy that type.

With class-based proxies, avoid declaring the class or intercepted methods as `final`, as proxies cannot override final classes/methods. Choose the proxy mode suited to your class design and dependency types.

## 9. Lazy Target Does Not Mean Everything Is Deferred

There are three distinct points in time:

1. **Registering the bean definition and proxy:** occurs during application context initialization.
2. **Creating the target:** performed by the scope when a target is needed for a call, following refresh scope's lazy semantics.
3. **Creating the target after refresh:** occurs when the proxy is next invoked after the cache entry has been destroyed.

Therefore, successful application startup does not necessarily prove the target can be recreated successfully after a refresh. A dependency might fail only when the new target is created—for example, a malformed new endpoint, invalid credentials, or a client constructor failing to connect to an external system.

Operations teams should monitor post-refresh target initialization failures and have a configuration rollback plan. Do not just check the HTTP response of the refresh endpoint and assume every bean was recreated successfully.

## 10. Lifecycle and Concurrency

When the old target is invalidated, Spring Cloud invokes registered destruction callbacks for that target. When the new target is created, dependencies are injected and initialization callbacks run like a normal bean.

This means:

- `@PreDestroy`, `DisposableBean.destroy()`, or a configured destroy method can run when the old target is destroyed.
- `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or an init method runs when the new target is created.
- Resources owned by the target must be closed properly; new resources are recreated according to the new configuration.
- State kept only in memory on the old target is lost when the target is replaced.

`RefreshScope` includes synchronization around access and refresh for beans in the scope. The Spring Cloud documentation notes that reading a bean in the scope is serialized with the refresh operation to avoid reading a target whose lifecycle is mid-change. However, that **does not turn refresh into an atomic transaction across the entire application context**, nor does it synchronize across different replicas.

Do not store unique business state inside a refresh-scoped target. For instance, account balances, shopping carts, or order processing progress must live in storage with an appropriate lifecycle rather than relying on fields of a bean that can be destroyed on refresh.

## 11. Distinguishing RefreshScope from @ConfigurationProperties Rebinding

Spring Cloud Context can handle `EnvironmentChangeEvent` in several ways. Two mechanisms are often confused:

| Mechanism | How it updates | Bean identity |
| --- | --- | --- |
| Rebinding `@ConfigurationProperties` | Rebinds fields of an existing bean from values in `Environment` | Usually keeps the same instance and updates internal state |
| `@RefreshScope` | Invalidates the target cache, then recreates the target from the bean definition on access | New target is a different instance; proxy stays the same |

In-place rebinding can allow a thread to read a bean right while its fields are being updated. The Spring Cloud documentation notes that when a consistent view across a refresh is needed, consider `@RefreshScope`, because the scope coordinates reads with refresh per bean.

`@RefreshScope` also does not mean every `@ConfigurationProperties` bean automatically becomes refresh-scoped. Identify which beans truly need to be recreated and verify how each bean is registered.

## 12. Cases Where You Should Not Expect Targets to Refresh

### 12.1. Beans Declared in `@Configuration`

Putting `@RefreshScope` on a `@Configuration` class does not make every `@Bean` method inside that class automatically refresh-scoped. Other beans depending on beans declared in that configuration also do not automatically receive new targets unless they themselves are designed to participate in refresh.

Place the scope directly on the bean that needs recreation:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @RefreshScope
    RemoteClient remoteClient(RemoteClientFactory factory,
                              RemoteClientProperties properties) {
        return factory.create(properties.endpoint());
    }
}
~~~

In this example, the `remoteClient` bean is placed in refresh scope. Consuming beans need to inject the corresponding proxy. If another bean already copied state or kept an internal reference to the old target, it must be redesigned to go through the proxy.

### 12.2. Constructor Binding and Java Records

According to Spring Cloud Context documentation, objects using constructor binding—including Java records annotated with `@ConfigurationProperties`—do not belong to the group that can be refreshed via normal rebinding. If you need to recreate an immutable configuration object, choose an appropriate bean registration and lifecycle strategy and test it on the exact release train; do not assume merely adding `@RefreshScope` to any configuration properties style is sufficient.

### 12.3. HikariDataSource

`HikariDataSource` is in the `spring.cloud.refresh.never-refreshable` list by default. Therefore, you should not expect this pool to be destroyed and recreated solely via `@RefreshScope`. Spring Cloud documentation recommends choosing a different `DataSource` implementation if you genuinely need to refresh a datasource this way.

Do not arbitrarily remove a datasource from `never-refreshable`: a pool with active connections and shared resources requires an explicit close/open, request-draining, and rollback procedure.

### 12.4. Native Image and AOT

Context Refresh is not supported for Spring AOT transformations and native images according to current Spring Cloud documentation. For AOT/native applications, configure:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

In that case, configuration design should rely on restart/rollout or another supported runtime mechanism.

### 12.5. Removing a Property from the Configuration Source

Deleting a property from a file or repository and refreshing does not always restore the absence of the property as expected. Spring Cloud documentation notes that removing a configuration value and refreshing does not update the presence of that value in a way the application might expect. If logic depends on a key no longer existing, design explicit default/absence semantics and test key deletion on the exact version in use.

## 13. Testing a Stable Proxy and Recreated Target

A useful test should prove three things:

1. The first call creates the target with the current configuration value.
2. After changing the configuration source and refreshing, the proxy held by the test is still the exact same object.
3. The next call through the proxy creates a new target and returns the new value.

Example with `@DynamicPropertySource`:

~~~java
package com.example.refresh;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RefreshScopeTest {

    private static final AtomicReference<String> MESSAGE =
            new AtomicReference<>("Hello");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("greeting.message", MESSAGE::get);
    }

    @Autowired
    GreetingTarget greetingTarget;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void keepsProxyButRecreatesTargetAfterRefresh() {
        GreetingTarget proxyReference = greetingTarget;

        String first = greetingTarget.render();
        assertThat(first).contains("Hello");

        MESSAGE.set("Bonjour");
        assertThat(refreshScope.refresh("greetingTarget")).isTrue();

        assertThat(greetingTarget).isSameAs(proxyReference);

        String second = greetingTarget.render();
        assertThat(second).contains("Bonjour");
        assertThat(second).isNotEqualTo(first);
    }
}
~~~

The test uses Spring Boot test dependencies and a mutable property supplier. `refresh("greetingTarget")` destroys the old target; when `render()` is called again, `@Value` is evaluated on the new target. The proxy injected into the test does not change identity.

If tests run in parallel or share an application context, reset `MESSAGE` to its default value after each test so one test's state does not affect another. Use `@DirtiesContext` if context isolation is needed.

### 13.1. Additional Test Cases

| Case | What to verify |
| --- | --- |
| Multiple calls before refresh | Target ID does not change; target is not recreated on every request |
| Refresh a single bean | Only the selected bean target is destroyed and recreated on access |
| Refresh all | All targets in the refresh scope are invalidated |
| Bean never called yet | Refresh does not force immediate target creation; first subsequent call creates it |
| New target initialization failure | Error is observed via logs/health indicator and requests do not silently use a destroyed target |
| Lifecycle callbacks | `@PreDestroy` of old target and `@PostConstruct` of new target run properly |
| Concurrent calls from multiple threads | No partially modified target is observed during scope refresh |
| Multiple application instances | Each instance is refreshed via the corresponding broadcast/operation mechanism |

## 14. Diagnosing When Refresh Has No Effect

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Bean still returns old value | Configuration was not updated in `Environment` | Check configuration source and effective value before refreshing scope |
| Target is not recreated | No call went through the proxy after refresh | Invoke the bean method through the injected reference |
| A singleton still uses the old value | Singleton copied the value from the target into its own field | Remove the copy or read through the proxy at time of use |
| `refresh(beanName)` returns `false` | Wrong bean name or target was never cached | Verify bean name and whether the target was ever invoked |
| `@PreDestroy` is not seen | Target was never created, destroy callback not registered, or wrong bean name/scope | Check init logs, bean definition, and lifecycle callbacks |
| `@Configuration` refreshed but `@Bean` did not change | Scope placed on configuration class does not automatically apply to individual bean methods | Place `@RefreshScope` directly on the bean that needs recreation |
| Datasource is not replaced | Datasource is in `never-refreshable`, especially `HikariDataSource` | Check `spring.cloud.refresh.never-refreshable` and datasource type |
| Only one replica gets the new configuration | Refresh was only invoked on one JVM | Use Spring Cloud Bus or invoke refresh on each instance |
| Native image not supported | Context Refresh does not support AOT/native | Disable refresh and choose a rollout/restart strategy |

## 15. Controlled Operational Workflow

When applying refresh in a real environment, follow this sequence:

1. Update the configuration source and verify the published version/label.
2. Send the refresh request via an authenticated management channel.
3. Verify that the instance's `Environment` received the expected new values.
4. Invalidate the target cache via the refresh endpoint or API.
5. Trigger health checks / business call paths so new targets are initialized.
6. Monitor lifecycle logs, target creation errors, health indicators, request error rates, and latency.
7. If the new target fails, restore the previous configuration and refresh again following the rollback procedure.

Do not treat an HTTP `200` from the refresh endpoint as proof that all targets were recreated successfully. The endpoint primarily triggers the update and invalidates the cache; targets are recreated on the next call.

## 16. Summary

`@RefreshScope` creates a stable scoped proxy so other beans can continue using the same reference. The scope stores target beans in a cache; on refresh, the current target is destroyed and the cache entry is removed. The next method call through the proxy creates a new target from the bean definition, injects dependencies, and re-runs lifecycle callbacks.

This mechanism avoids replacing references in every singleton, but it does not automatically refresh values copied outside the proxy, does not refresh every bean in the application context, and does not broadcast across multiple JVMs. You must update `Environment` before invalidating targets, secure the refresh endpoint, and test failure cases when new target initialization fails.

## References

- [Spring Cloud Context — Application Context Services, Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): lazy proxy, target cache, `refreshAll()`, `refresh(String)`, lifecycle, bean limitations, and AOT/native.
- [Spring Cloud `@RefreshScope` annotation source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/config/annotation/RefreshScope.java): annotation mapping to scope `refresh` and default proxy mode.
- [Spring Cloud `RefreshScope` implementation](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java): destroying targets by name, `refreshAll()`, and post-refresh events.
- [Spring Cloud `GenericScope` and refresh tests](https://github.com/spring-cloud/spring-cloud-commons/tree/main/spring-cloud-context/src/test/java/org/springframework/cloud/context/scope/refresh): tests for target recreation after refresh and lifecycle callbacks.

Cross-check documentation against the Spring Cloud release train you are using. Details regarding non-refreshable beans, rebinding, AOT, and health indicators may vary across versions.
