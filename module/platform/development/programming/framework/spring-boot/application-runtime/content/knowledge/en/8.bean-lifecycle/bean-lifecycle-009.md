# Order of @PreDestroy, DisposableBean, and destroyMethod When Spring Destroys a Bean

## 1. Why does bean destruction callback order matter?

A Spring bean can own connections, threads, buffers, file handles, subscriptions, or external resources. When the application stops, Spring needs to invoke cleanup steps to return resources to a safe state. If a bean simultaneously declares multiple cleanup mechanisms, the question arises: **which method runs first, which runs next, and when are they called?**

In Spring Framework 6.x / Spring Boot 3.x, if **the same Spring-managed bean** uses three destruction callbacks with **different method names**, the standard order is:

1. **`@PreDestroy`**: callback handled via `DestructionAwareBeanPostProcessor`, typically the infrastructure processing `@PreDestroy` annotations.
2. **`DisposableBean.destroy()`**: callback from the `org.springframework.beans.factory.DisposableBean` interface.
3. **Custom destroy method**: method configured via `@Bean(destroyMethod = "...")` or equivalent bean definition metadata.

```text
ApplicationContext.close()
         |
         v
  Begin destroying context-managed singletons
         |
         v
  [1] @PreDestroy
         |
         v
  [2] DisposableBean.destroy()
         |
         v
  [3] @Bean(destroyMethod = "cleanup")
         |
         v
  Bean completes cleanup callback sequence
```

This is the **order of mechanisms on the same bean**, when they are genuinely registered and invoked. It does **not** say Spring invokes `@PreDestroy` of *all* beans first and then `DisposableBean.destroy()` of *all* beans. Spring generally completes all callbacks for a bean when destroying that bean, respecting dependency relationships and singleton destruction rules.

Therefore, before asking “which callback runs first”, clarify **same bean or multiple beans**, **which scope**, **who manages the object**, and **whether the context was closed properly**.

## 2. Three declaration styles and their responsibilities

| Mechanism | Where declared? | How Spring invokes it | Advantages and trade-offs |
| --- | --- | --- | --- |
| `@PreDestroy` | On a method of the bean class | `BeanPostProcessor` infrastructure invokes before destroying the bean | Minimal Spring API coupling; readable; requires `jakarta.annotation.PreDestroy` in Boot 3 |
| `DisposableBean` | Class `implements DisposableBean` | Spring calls the `destroy()` method | Explicit framework contract; couples the class to Spring API |
| `destroyMethod` | Bean metadata, usually `@Bean(destroyMethod = "cleanup")` | Spring calls the specified or inferred method | Fits third-party library classes you cannot edit; keeps Spring API out of the class |

Three basic examples in standalone declaration contexts:

**Using `@PreDestroy`:**

```java
import jakarta.annotation.PreDestroy;

public class MessageCache {

    @PreDestroy
    public void clear() {
        System.out.println("Cleaning message cache");
    }
}
```

For the callback to work, `MessageCache` must be created as a **container-managed bean**, such as via `@Component` or `@Bean`. An object created with `new MessageCache()` outside Spring will not receive container callbacks automatically.

**Using `DisposableBean`:**

```java
import org.springframework.beans.factory.DisposableBean;

public class SocketManager implements DisposableBean {

    @Override
    public void destroy() throws Exception {
        System.out.println("Closing managed sockets");
    }
}
```

Spring recognizes that the bean implements `DisposableBean` and calls `destroy()` when the bean is destroyed per container lifecycle. A bean does not need `@PreDestroy` if it only wants this mechanism.

**Using `@Bean(destroyMethod = "...")`:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ThirdPartyClient thirdPartyClient() {
        return new ThirdPartyClient();
    }
}
```

`ThirdPartyClient` is an **illustrative type** from an external library and must exist in the project with an appropriate `shutdown()` method. This snippet proves you can instruct Spring to call a cleanup method without modifying the library's source.

**Which should you use?** For beans owned by your own team, `@PreDestroy` is usually clearer and less coupled to Spring than the interface. For classes from external SDKs that already expose `close()` or `shutdown()`, `destroyMethod` is convenient. `DisposableBean` makes sense when intentionally defining an infrastructure component tightly integrated with Spring. There is no need to attach all three mechanisms to one bean just to guarantee cleanup; the combined example below exists to demonstrate ordering.

## 3. Complete example: all three callbacks on the same bean

This example runs on **Java 17+**, **Spring Boot 3.3.x**, with the `spring-boot-starter` dependency in a Maven/Gradle project configured for Spring Boot.

Create the file:

```text
src/main/java/demo/lifecycle/DestroyOrderApplication.java
```

Contents:

```java
package demo.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DestroyOrderApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(DestroyOrderApplication.class, args)) {
            System.out.println("app.running");
        }

        System.out.println("app.closed");
    }

    @Bean(destroyMethod = "customCleanup")
    CleanupProbe cleanupProbe() {
        return new CleanupProbe();
    }
}

class CleanupProbe implements DisposableBean {

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("1. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2. DisposableBean.destroy()");
    }

    public void customCleanup() {
        System.out.println("3. @Bean(destroyMethod)");
    }
}
```

To focus on bean lifecycle, add:

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
```

Gradle dependency in a project using the Spring Boot Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Run with the Gradle wrapper:

```bash
./gradlew bootRun
```

Or package and run the actual executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/actual-jar-filename.jar
```

Lines printed by **the example program itself**:

```text
app.running
1. @PreDestroy
2. DisposableBean.destroy()
3. @Bean(destroyMethod)
app.closed
```

Spring Boot may print additional logs before, between, or after these illustrative lines; the order of the five lines printed by the example code is the result to verify. If another framework or bean also logs during shutdown, total stdout will include more than just those five lines.

### Step-by-step analysis

- `SpringApplication.run(...)` creates, refreshes, and returns `ConfigurableApplicationContext`.
- The `cleanupProbe()` method declares a Spring-managed singleton bean (by default).
- The bean is registered with **explicit destruction metadata**: `destroyMethod = "customCleanup"`.
- The bean's class is detected to have `@PreDestroy` and implement `DisposableBean`.
- The `try-with-resources` block closes `ConfigurableApplicationContext` upon exit, so cleanup callbacks are invoked before `app.closed`.
- Spring calls `beforeDestroy()`, `destroy()`, and then `customCleanup()` in exact order.

**Key condition:** the example intentionally uses **three distinct method names** so we can observe three separate invocations, avoiding the case where one method is registered under multiple mechanisms and deduplicated.

### A common misinterpretation

If you remove `try-with-resources` and do not manually call `context.close()`, Spring Boot may still register a JVM shutdown hook to close the context on normal JVM exit. However, when a shutdown hook runs depends on process lifecycle; do not rely on that to predict that cleanup lines will appear immediately after `app.running`. The example uses `try-with-resources` to guarantee **observable context close timing**.

If the application has a web server, closing the context can also trigger stopping request acceptance and shutting down the web server. Those steps belong to the context/web server lifecycle and do not change the order of the three callbacks on **the same bean**.

## 4. In what order does Spring invoke the three mechanisms internally?

In Spring's singleton management system, a bean destruction adapter coordinates the registered callbacks.

It can be approximated with Java pseudo-code:

```java
void destroyManagedBean(Object bean, String beanName) {

    // 1. Infrastructure handling @PreDestroy and destruction post-processors.
    for (DestructionAwareBeanPostProcessor processor : destroyProcessors) {
        processor.postProcessBeforeDestruction(bean, beanName);
    }

    // 2. Spring-specific callback.
    if (bean instanceof DisposableBean disposable) {
        disposable.destroy();
    }

    // 3. Destroy method declared in the bean definition.
    invokeConfiguredDestroyMethodIfPresent(bean);
}
```

This is **pseudo-code explaining the order**, not a complete class and not copied verbatim from Spring Framework source; the real implementation also handles method resolution, `close/shutdown` inference, deduplication, and exception handling.

`@PreDestroy` is registered by annotation processing infrastructure via `DestructionAwareBeanPostProcessor`. In Spring Framework, the lifecycle-annotation processor recognizes the annotated method and triggers it before the `DisposableBean` step.

Next, the adapter checks whether the bean implements `DisposableBean`. If so, Spring invokes `destroy()` directly per the interface contract.

Finally, if the bean definition declares another destroy method, Spring invokes that method. Thus, the order is not dictated by method placement in the Java file, import order, or annotation order in source code; **it is orchestrated by the framework during bean destruction**.

A mnemonic:

```text
Annotation callback
        ↓
Spring interface callback
        ↓
Bean-definition custom callback
```

When reading logs, if a callback is missing, check **whether that mechanism was registered** before suspecting the order was reversed.

## 5. @PreDestroy: detection timing, requirements, and limits

In Spring Boot 3.x, use:

```java
import jakarta.annotation.PreDestroy;
```

For older Spring Boot 2.x projects, many online examples use `javax.annotation.PreDestroy`. Spring Framework 6 / Boot 3 migrated to Jakarta, so importing the wrong namespace can cause compile errors or prevent the annotation from being processed as expected. Do not mix guides from different Spring generations without checking dependencies.

A typical `@PreDestroy` method is a no-argument instance method returning `void`:

```java
@Component
public class ReportBuffer {

    @PreDestroy
    public void flushAndClose() {
        System.out.println("Closing report buffer");
    }
}
```

The snippet above requires importing `org.springframework.stereotype.Component`, `jakarta.annotation.PreDestroy`, and living in an appropriately packaged `ReportBuffer.java` file. It runs when the bean is scanned or registered by Spring and the context closes through the standard lifecycle.

Points to remember:

1. **Do not call it manually**: Spring calls the method when destroying the bean. Calling `flushAndClose()` from business logic is an ordinary Java call and can cause double-closing if uncontrolled.
2. **Annotation lives on the bean's method**: `@PreDestroy` only works if the object passes through Spring bean management and compatible destruction-aware post-processors.
3. **Do not place it on a static utility method** and expect Spring to manage the class's lifecycle.
4. **Do not force callbacks to rely on already-destroyed beans**: if a bean uses resources from another bean, declare proper dependency relationships so the container orders destruction across beans.
5. **Do not use it for long-running work**: shutdown may be time-bounded by the container, OS, or orchestrator. Cleanup should be fast, safe to repeat, and time-bounded.

`@PreDestroy` also works on beans created via `@Bean`, not only `@Component`. In the combined example, `CleanupProbe` lacks `@Component` yet still receives the callback because the instance is declared via `@Bean` and managed by the context.

### When is @PreDestroy not called?

- The object was instantiated with `new` and **not registered as a Spring bean**.
- The bean has `prototype` scope, which the container does not automatically track for destruction.
- The process terminates abruptly, e.g. `kill -9` on Unix/Linux, power loss, or forced termination skipping shutdown hooks.
- The context never instantiated the bean due to lazy initialization, so no instance exists to destroy.
- Annotation/post-processor infrastructure is customized or missing in a special container configuration.
- Code exited or stopped in a way that bypasses standard lifecycle.

Thus, the statement “Spring always calls `@PreDestroy`” must be qualified with **when the bean is actually managed and the container executes destruction**.

## 6. DisposableBean.destroy(): Spring's own contract

Interface:

```java
package org.springframework.beans.factory;

public interface DisposableBean {
    void destroy() throws Exception;
}
```

This is a **condensed version to explain the contract**, not a file to create in your project. When a bean implements this interface, the container has an explicit invocation path without needing to discover callback names from annotations.

Example:

```java
public final class WorkerPool implements DisposableBean {

    private boolean closed;

    @Override
    public void destroy() {
        if (closed) {
            return;
        }
        closed = true;
        System.out.println("WorkerPool stopped");
    }
}
```

This snippet assumes `WorkerPool` is registered as a bean and imports `DisposableBean`. The `closed` flag illustrates handling repeated calls in a single-threaded setting. In real multithreaded code, use proper synchronization or an idempotent resource-management component.

The advantage of `DisposableBean` is that the lifecycle signal sits right on the interface: reading the class signature reveals it participates in the destruction contract. The drawback is coupling a library/business object to Spring Framework, making reuse outside Spring harder.

If a bean has both `@PreDestroy` and `DisposableBean`, **the `@PreDestroy` method runs before `destroy()`** in the standard flow. If it also configures a different custom destroy method, that custom method runs afterward.

Do not confuse roles: `DisposableBean.destroy()` is a callback when Spring destroys a bean, not an API for callers to command “shut down the entire app”. Calling it manually will not cause Spring to close the context, update the bean registry, destroy dependent beans, or stop the web server.

## 7. destroyMethod: declared via @Bean metadata

`@Bean` allows specifying the cleanup method name directly where the bean is defined:

```java
@Configuration
class ResourceConfiguration {

    @Bean(destroyMethod = "release")
    ResourceHolder resourceHolder() {
        return new ResourceHolder();
    }
}

class ResourceHolder {

    public void release() {
        System.out.println("Resource released");
    }
}
```

This snippet requires importing `org.springframework.context.annotation.Bean` and `Configuration`, with classes in a valid package. This approach works with libraries that do not depend on Spring.

An important naming detail: **`destroyMethod` does not have to be named `destroy()`**. It can be `release`, `close`, `shutdown`, or another suitable method. The `destroyMethod` attribute on `@Bean` specifies the exact callback name Spring should invoke per the bean definition.

If using XML instead of Java config, Spring also supports `destroy-method="..."` on XML bean definitions. Because the mechanism lives in **bean metadata**, destruction infrastructure applies the same principles.

### @Bean's close/shutdown inference

In Spring Framework, `@Bean` defaults to **inferring** `close()` or `shutdown()` destroy methods when applicable. Thus:

```java
@Bean
ExternalClient client() {
    return new ExternalClient();
}
```

If `ExternalClient` is a type with an eligible public `close()` or `shutdown()`, Spring can automatically register the cleanup callback without manually specifying `destroyMethod`. This is a conceptual example requiring a definition or library providing `ExternalClient`.

To disable **specifically `@Bean`'s destroy-method inference**, use:

```java
@Bean(destroyMethod = "")
ExternalClient externallyManagedClient() {
    return new ExternalClient();
}
```

This configuration **does not make the bean an unmanaged object** and is not a way to disable declared `@PreDestroy`/`DisposableBean.destroy()`. It only disables destroy-method inference under `@Bean` rules.

### Why is close sometimes not called?

Check whether:

- The bean was declared with `@Bean` or a bean definition specifying the corresponding destroy method.
- The `close()`/`shutdown()` method actually qualifies under inference rules.
- The `@Bean` return type (class or interface) hides type information needed by inference mechanisms.
- `destroyMethod = ""` was set somewhere.
- The bean belongs to a scope automatically destroyed by the container.
- Something already closed the resource before Spring invoked the callback.

Verify the actual lifecycle instead of assuming inference always triggers for every combination of interfaces and runtime types.

## 8. When the same method participates in multiple mechanisms

To analyze **order** clearly, the three callbacks in Section 3 used three different names. In practice, someone might configure:

```java
@Bean(destroyMethod = "destroy")
MyDisposableBean myBean() {
    return new MyDisposableBean();
}
```

while `MyDisposableBean` already implements `DisposableBean` with `destroy()`.

Spring Framework has logic to prevent a single method from being destroyed twice merely because it was detected through multiple mechanisms. Therefore, you should not claim “three mechanisms declared guarantees three invocations” if they all resolve to the same method.

Similarly, `AutoCloseable.close()` may be selected as a custom destroy callback via inference or configuration. What matters is knowing who owns the resource and whether the close method is registered and called, rather than layering duplicate callbacks.

**Implementation principle:** only one method should truly be responsible for releasing a resource, or callbacks should have distinct responsibilities. If both `@PreDestroy` and `destroy()` close the same connection, double-closing can log errors or make cleanup confusing. Make callbacks idempotent where appropriate, yet do not rely on idempotence to mask a duplicated lifecycle design.

## 9. When Spring performs destruction during context close

In a standard `ApplicationContext`, closing generally proceeds through these major stages:

```text
ApplicationContext.close()
    |
    +-- Publish ContextClosedEvent
    |
    +-- Ask LifecycleProcessor to stop Lifecycle/SmartLifecycle beans
    |
    +-- Destroy container-managed singletons
    |     |
    |     +-- select beans to destroy, respecting dependencies
    |     |
    |     +-- @PreDestroy
    |     +-- DisposableBean.destroy()
    |     +-- custom destroyMethod
    |
    +-- Close BeanFactory infrastructure / terminate context
```

This is a **simplified diagram**; specific contexts have extra hooks, and Spring Boot web apps add web-server shutdown steps. Key takeaways:

- **`ContextClosedEvent`** is published to notify that the context is closing. This is a context event, not a single bean's destroy callback.
- **`Lifecycle` / `SmartLifecycle`** has a `stop` step, typically occurring before singleton destructors. This is useful for background workers that must stop accepting new work before dependencies are closed.
- **Destruction callbacks** release resources owned by the bean.
- Once a bean is destroyed, do not continue calling its business methods as if it were still active.

Hence `@PreDestroy` can run **after** a bean receives `SmartLifecycle.stop()` if the class implements both. `stop` and `destroy` are separate mechanisms that coordinate halting processing loops before releasing resources.

### SmartLifecycle and controlled shutdown

A component serving requests or running long tasks may need to:

1. In `SmartLifecycle.stop(...)`: stop accepting new work and wait for in-flight work within a reasonable bound.
2. In its destructor: close pools, release files, cancel subscriptions, and finish cleanup.

In Spring Boot web apps, graceful shutdown is coordinated via appropriate web server/lifecycle infrastructure. Do not expect sleeping for several seconds inside `@PreDestroy` to be the right way to wait for HTTP requests to finish.

## 10. Callback order within one bean vs. destruction order across beans

Suppose bean `InvoiceProcessor` depends on bean `DatabaseClient`:

```text
InvoiceProcessor ---> DatabaseClient
      (uses)           (provides connection)
```

When closing the context, Spring must avoid destroying `DatabaseClient`'s resources while `InvoiceProcessor` still needs them during its own cleanup callback. For dependency relationships known to the container, **the dependent bean is generally destroyed before the bean it depends on**.

Complete component-style example:

```java
package demo.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class DatabaseClient {

    void execute(String sql) {
        System.out.println("Executing: " + sql);
    }

    @PreDestroy
    void closeDatabase() {
        System.out.println("DatabaseClient closed");
    }
}

@Component
class InvoiceProcessor {

    private final DatabaseClient databaseClient;

    InvoiceProcessor(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @PreDestroy
    void stopProcessor() {
        System.out.println("InvoiceProcessor stopped");
    }
}
```

These are **two package-private classes in the same package**, which can reside in appropriate Java files within a Spring Boot project scanning `demo.lifecycle`. The `execute` method merely illustrates the dependency; it does not need to be called at shutdown.

With both singletons registered and created successfully, when the context closes normally, the two lines from the destructors typically appear in this order:

```text
InvoiceProcessor stopped
DatabaseClient closed
```

**Do not conclude** Spring calls `@PreDestroy` across all beans alphabetically or in source-line order. Dependency relationships play a crucial role.

When multiple beans are independent, their destructor order is **not an application contract you should rely on**. If bean A's callback needs bean B still alive, declare a real dependency via constructor injection or dependency metadata like `@DependsOn` when needed. Do not use bean naming tricks to “force” destruction order.

`@DependsOn` affects not only initialization order. The relationship recorded by the container also applies to destruction order: **the dependent bean is destroyed before its dependency**. Still, it does not replace concurrency management and shutdown logic for complex resources.

### Visualizing the two ordering axes

```text
Across beans:
  Processor is destroyed
      before
  DatabaseClient is destroyed

Within Processor alone:
  @PreDestroy
      before
  DisposableBean.destroy()
      before
  configured destroyMethod

Within DatabaseClient alone:
  @PreDestroy
      before
  DisposableBean.destroy() (if present)
      before
  configured destroyMethod (if present)
```

This is the proper way to separate two questions often conflated into one.

## 11. Scope determines which callbacks Spring actively invokes

Not every created bean is tracked and destroyed by Spring in the same way.

| Scope / object | Cleanup behavior to understand |
| --- | --- |
| Standard `singleton` | Spring registers destroy callbacks for eligible beans and invokes them when the context/factory closes |
| `prototype` | Container creates and configures the instance, yet **does not manage destroying each instance**; the consumer owns cleanup |
| `request` / `session` in web apps | Destruction callbacks can run when that scope ends, depending on the actual scope implementation |
| Custom scope | Depends on whether the scope supports and triggers destruction callbacks |
| Manually created with `new` | Receives no Spring callbacks unless properly managed/registered |
| Lazy bean never initialized | No instance exists to invoke destructors on |
| Singleton created before context startup failed | Spring may clean up already-created singletons during refresh-failure teardown; do not assume all beans existed |

### Prototype: a common resource-leak trap

Example:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class TemporaryBuffer {

    @PreDestroy
    public void cleanup() {
        System.out.println("Prototype buffer destroyed");
    }
}
```

This snippet requires importing `Component`, `Scope`, `ConfigurableBeanFactory`, and `PreDestroy`. When obtaining multiple prototype instances, calling `context.close()` **does not automatically invoke** `cleanup()` on each prototype instance Spring handed out. If a prototype holds file handles or connections, the receiving code must arrange release.

You can use `AutoCloseable`, `try-with-resources`, or an explicit resource-management abstraction for such short-lived objects. Do not turn a prototype into a singleton just to get a destructor; design scope around the resource's real lifetime.

### Are singletons guaranteed to be called exactly once?

In a normal shutdown, singleton beans are destroyed by the container via registered management hooks. However, calling a destroy method directly from business logic, restarting contexts in custom code, or creating multiple contexts can cause the same logic to execute on other objects or runs. Cleanup design should avoid relying on “the JVM has exactly one bean and exactly one shutdown”.

## 12. Why didn't @PreDestroy run on application shutdown?

Many bugs are not about callback order, but about **no destruction event occurring**.

Cases to check:

- The app was terminated by killing the process without letting the JVM run shutdown hooks, e.g., `SIGKILL`/`kill -9`.
- The class was instantiated with `new` inside a service, not as a Spring-managed bean.
- The bean is `prototype` or in a custom scope that does not trigger destruction callbacks.
- The class was not component-scanned, or its `@Bean` declaration was not loaded.
- A Spring Boot 3 project mistakenly imported `javax.annotation.PreDestroy` instead of `jakarta.annotation.PreDestroy`.
- The callback was placed on an invalid method or annotation processing was inactive.
- The context was never closed in the tested execution path; the app is still running.
- A lazy bean never had an instance because it was never requested.
- Test vs. runtime mismatch: test contexts may be cached or closed at different times than expected.

**Minimal verification:**

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DestroyOrderApplication.class, args);

// Observation steps ...
context.close();
```

This is illustrative code inside a method with required imports. In apps purely testing callbacks, calling `close()` explicitly distinguishes wiring errors from never reaching shutdown.

In a production web application, never call `context.close()` from an endpoint just to test a destructor. Doing so shuts down the entire application and disrupts active requests.

## 13. Differences among close(), stop(), ContextClosedEvent, and destructors

| API / event | Target | Meaning |
| --- | --- | --- |
| `ConfigurableApplicationContext.close()` | Context | Begins closing and releasing container infrastructure |
| `ContextClosedEvent` | Context event | Notifies that the context is closing; listeners may react |
| `Lifecycle.stop()` | Lifecycle-capable bean | Stops work/running mode managed by the bean |
| `SmartLifecycle.stop(Runnable callback)` | Async-stop-capable bean | Signals stop-phase completion so the processor can proceed |
| `@PreDestroy` | Bean with valid annotation | Cleanup hook before destroying the bean |
| `DisposableBean.destroy()` | Bean implementing interface | Destruction hook per Spring's contract |
| `@Bean(destroyMethod = "x")` | Bean with matching metadata | Invokes the configured cleanup method |
| `Runtime.getRuntime().addShutdownHook(...)` | JVM | Registers action on JVM shutdown per JVM rules |

Do not confuse **context `stop()`** with **`close()`**. `stop()` forwards lifecycle signals to eligible beans; it does not automatically perform full bean destruction like `close()`. Likewise, `ContextClosedEvent` is an event published along the close path; it is not one of the three bean destruction callbacks in this lesson.

In Spring Boot, a shutdown hook is registered by default to close the context on normal JVM termination. Even so:

- Shutdown hooks do not run if the JVM is killed without allowing hooks to execute.
- Orchestrators such as Kubernetes impose container shutdown grace periods; overly slow callbacks can be terminated mid-run.
- Ordering among independent JVM shutdown hooks should not be relied upon as a business cleanup ordering contract.

Prefer **Spring lifecycle cleanup hooks** for Spring-managed resources. Use raw JVM hooks only when something genuinely lives outside the context's lifecycle.

## 14. Exceptions in destroy callbacks and safety principles

Destructors should perform **best-effort** cleanup while preserving diagnostic information on failure. Unlike handling a request, when a context closes, system state is tearing down; trying to reuse other beans or performing unbounded retries can make shutdown unpredictable.

An often suitable design:

```java
public final class FileWriterHolder implements AutoCloseable {

    private boolean closed;

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        // Close the actual writer here in an application with that resource.
    }
}
```

This snippet illustrates idempotence only; in multithreaded systems, handle concurrency, I/O errors, and real resources properly. When declared via `@Bean` without disabling destroy inference, an eligible `close()` can be registered by Spring for destruction.

Things to avoid in destructors:

1. Throwing a new exception that obscures the original root cause.
2. Waiting indefinitely on an HTTP call or connection pool close; enforce timeouts.
3. Calling business operations assuming all other beans are still active.
4. Spawning new background threads or jobs after the container has stopped accepting work.
5. Logging credentials, tokens, or sensitive data into shutdown logs.
6. Executing complex business transactions requiring guaranteed commit after shutdown has begun.

Spring handles errors during destruction phases and can continue destroying remaining beans, yet you **should not rely on error-swallowing to keep shutdown clean**. Log errors clearly and place cleanup in the layer that owns the resource.

### Assigning roles if forced to use all three callbacks

If an integration framework forces a bean to use all three mechanisms, assign clear roles:

- `@PreDestroy`: mark as no longer accepting new work and signal a soft stop.
- `DisposableBean.destroy()`: shut down executors/pools owned by the bean.
- `destroyMethod`: release or clean up final resources provided by an external library.

This is only an **illustrative design pattern**. When steps have complex dependencies, it is usually better to consolidate cleanup into one method triggered by one callback to avoid scattered logic and tricky error handling.

## 15. Mirroring initialization order: @PostConstruct and initMethod

Destruction order has an easy-to-remember symmetry with standard initialization order when a bean configures multiple mechanisms:

| Phase | Callback order within the same bean |
| --- | --- |
| **Initialization** | `@PostConstruct` → `InitializingBean.afterPropertiesSet()` → custom `initMethod` |
| **Destruction** | `@PreDestroy` → `DisposableBean.destroy()` → custom `destroyMethod` |

The difference is purpose: during initialization, the bean is prepared for use; during destruction, resources must be released. Do not deduce that if the container initialized bean A then B, it always destroys B then A unless there is a framework-managed dependency or ordering relationship.

In real projects, you usually only need **one** initialization mechanism and **one** cleanup mechanism suited to each bean type. The symmetry table explains how Spring combines callbacks when a single bean uses multiple mechanisms; it does not encourage always declaring all three.

## 16. Verification exercises and labs

### Exercise 1: run the three-callback model yourself

Run `DestroyOrderApplication` from Section 3. Inspect the output and answer:

1. Why does `app.running` appear before all three destructors?
2. Why does `@PreDestroy` run before `DisposableBean.destroy()`?
3. Why does `customCleanup()` run third?
4. If you remove `@Bean(destroyMethod = "customCleanup")` while keeping the other two callbacks, which lines remain?
5. If you change scope to prototype, is the result the same? Why does Spring not auto-destroy each prototype instance?

Expected answers for the first three steps: **the context closes at the end of `try`, destruction infrastructure invokes annotation callbacks first, interface callbacks second, and custom destroy metadata last**.

### Exercise 2: use only one callback

Try three independent variations:

- Remove `implements DisposableBean` and custom destroy metadata, keeping only `@PreDestroy`.
- Remove `@PreDestroy` and custom destroy metadata, keeping only `DisposableBean`.
- Remove `@PreDestroy` and `DisposableBean`, keeping `@Bean(destroyMethod = "customCleanup")`.

Each variation should produce only **one** cleanup line for `CleanupProbe` after `app.running`. This isolates callback registration bugs when multiple methods exist.

### Exercise 3: inferred close()

Create a class with a public `close()` without Spring APIs:

```java
public final class ClientHolder implements AutoCloseable {

    @Override
    public void close() {
        System.out.println("ClientHolder.close()");
    }
}
```

Register it with `@Bean` and close the context; observe whether Spring invokes `close()` via inference. Then try `@Bean(destroyMethod = "")` and compare. Keep the whole example inside a valid Spring project and do not call `close()` manually during the measured steps.

### Exercise 4: dependency relationship

Create two beans `Consumer` and `Provider`, where `Consumer` injects `Provider`. Each bean has a `@PreDestroy` printing its own name. Predict the destruction order, then close the context.

This exercise tests distinguishing **destruction order across beans** from **callback order within one bean**. Expect the dependent `Consumer` to be cleaned up before `Provider` once the container knows the dependency.

### Exercise 5: testing without stopping the whole application

In a test, you can create an isolated `AnnotationConfigApplicationContext`, register a configuration containing only the target beans, and call `refresh()` and `close()` within the test scope. This is cleaner than closing an application context shared across tests.

Conceptual snippet:

```java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(TestConfig.class);
    context.refresh();
    // Observe state before shutdown.
}
// Verify callbacks after context closes.
```

The snippet above requires importing `AnnotationConfigApplicationContext` and declaring `TestConfig` separately; it is a **pattern for use inside a test**, not a standalone complete program. Record the order into a test-controlled `List<String>` and assert exact list contents rather than parsing full console logs.

## 17. Summary of common troubleshooting cases

| Symptom | Causes to check | How to resolve |
| --- | --- | --- |
| No `@PreDestroy` line | Bean not managed by Spring, wrong annotation namespace, or context not closed | Check `@Bean`/scan, `jakarta.annotation.PreDestroy`, close lifecycle |
| `DisposableBean.destroy()` did not run | Class didn't implement interface properly, bean unregistered, or scope not container-destroyed | Check imports, bean registration, and scope |
| Custom destroy method did not run | Missing `destroyMethod`, wrong method name, or inference did not apply | Check bean definition and eligible public method |
| All three declared yet only two lines appear | Multiple mechanisms may point to the same method or one callback isn't registered | Use distinct callback names when testing and inspect metadata |
| Destructor ran twice in logs | Cleanup invoked both manually and by container, or multiple instances/contexts exist | Clarify ownership; avoid manual callback invocation |
| `@PreDestroy` did not run on `kill -9` | JVM could not run shutdown hooks | Use normal termination signals, set shutdown deadlines, design recovery |
| Prototype leaks resources | Container does not auto-destroy individual prototypes | Make the caller responsible for closing instances |
| Bean A's destructor uses already-closed bean B | Dependency relationship not registered with container or flawed design | Declare dependencies and layer cleanup properly |
| Need to stop tasks before closing pools | Destructors alone are too late to coordinate stop phases | Use `Lifecycle`/`SmartLifecycle` appropriately |
| Test in `@SpringBootTest` never invokes callback | Test context is cached and not torn down yet | Use an isolated context or test lifecycle management hooks |
| Resources close in tests but not in production | Different app stop method, shutdown hooks, scopes, or exceptions | Inspect runtime shutdown path and real logs |
| Error in callback skips remaining cleanup | Callback threw or blocked indefinitely | Keep cleanup small, bounded, and log errors properly |

Troubleshooting should start with **was the bean destroyed at all**; next check **which callbacks were registered**; and finally analyze **execution order**. This avoids confusing scope behavior with framework ordering bugs.

## 18. Rules to remember

- For **one singleton bean destroyed normally by the container** with three **differently named** callbacks, the fundamental order is: **`@PreDestroy` → `DisposableBean.destroy()` → custom `destroyMethod`**.
- `@PreDestroy` in Spring Boot 3.x is imported from `jakarta.annotation.PreDestroy`.
- `DisposableBean` is a Spring interface; `@Bean(destroyMethod = "...")` declares a method on the bean definition, fitting third-party classes too.
- `@Bean` infers `close`/`shutdown` by default. `@Bean(destroyMethod = "")` disables only destroy-method inference, not other lifecycle callbacks.
- Do not equate callback order **within one bean** with destruction order **across beans**. Dependency relationships let Spring destroy dependents before dependencies.
- `prototype` beans are not automatically tracked by Spring for destruction; objects created with `new` outside the container do not automatically receive Spring callbacks either.
- `ContextClosedEvent`, `SmartLifecycle.stop()`, and `ApplicationContext.close()` are **distinct** parts of shutdown.
- For resources owned by a bean, select only needed callbacks, avoid duplicate closing, and never block shutdown for too long.

### References

- [Spring Framework — Customizing the Nature of a Bean / Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `DisposableBean` interface, `@PreDestroy` annotation, init/destroy callbacks, and lifecycle integration.
- [Spring Framework — Using the @Bean Annotation / Receiving Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `destroyMethod`, `DisposableBean` invocation, and `close`/`shutdown` inference.
- [Spring Framework 6.1 — Bean factory lifecycle](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/beans/factory/DisposableBean.html): `DisposableBean.destroy()` contract.
- [Spring Framework 6.1 — Context close](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): closing the context and managing lifecycle.
