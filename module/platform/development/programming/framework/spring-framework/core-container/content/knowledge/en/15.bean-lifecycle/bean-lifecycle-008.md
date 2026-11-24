# @PreDestroy, DisposableBean, and destroyMethod Callbacks in Spring Framework

## Objectives

The Spring IoC container does not only create and inject beans. When a bean's lifecycle ends, the container can also invoke **destruction callbacks** so the bean closes resources it owns: network connections, file handles, thread pools, listeners, buffers, or external clients. The three key configuration options are `@PreDestroy`, `org.springframework.beans.factory.DisposableBean`, and a **custom destroy method** on the bean definition, commonly seen as `@Bean(destroyMethod = "close")`.

This lesson belongs to the **Bean Lifecycle** section of the Spring Framework Core Container. After completing it, you will know how to choose callbacks, understand execution order when combining them, use them properly across scopes, configure shutdown, and avoid resource leaks. The primary example uses **Java 17 and Spring Framework 6**, runs with Maven, and produces deterministic stdout.

## 1. What Is a Destruction Callback?

Every bean has a lifecycle governed by the container and its scope. For a standard singleton:

~~~text
Read BeanDefinition
       ↓
Create instance, inject dependencies
       ↓
Initialization callbacks:
  @PostConstruct → InitializingBean.afterPropertiesSet()
                 → @Bean(initMethod="...") (if any)
       ↓
Bean serves the application
       ↓
ApplicationContext closes or bean is destroyed
       ↓
Destruction callbacks:
  @PreDestroy → DisposableBean.destroy()
              → custom destroy method (if any)
       ↓
Release resources and stop using the bean
~~~

This is a high-level diagram of the lifecycle. In practice, Spring also uses `BeanPostProcessor`s, scope management, proxies, the dependency graph, and startup/shutdown phases.

**Do not equate destruction callbacks with Java garbage collection:** `@PreDestroy` is not a finalizer and does not run whenever an object loses all references. Only when Spring or the responsible scope explicitly triggers the destruction lifecycle are the appropriate callbacks invoked. For objects instantiated manually with `new` outside the container, Spring has no lifecycle responsibility.

**Do not equate destroy with rollback or mandatory final business transactions.** When the JVM is forcibly terminated, the process crashes, or power is lost, callbacks are not guaranteed to run. Data durability requirements need commit/recovery independent of shutdown.

### Examples of resources needing cleanup

A client dedicated to one bean may need `client.close()`; a background poller needs to stop accepting work, await in-flight tasks, and shut down its executor; an object that registered callbacks with another library needs to unregister. Conversely, if a resource is owned by another container or is a shared client, closing it arbitrarily inside this bean can break other beans. Always establish **resource ownership** before writing a callback.

## 2. Comparing the Three Declaration Mechanisms

| Mechanism | How it is used | When should you choose it? | Class coupling to Spring |
| --- | --- | --- | --- |
| `@PreDestroy` | Annotation on an instance method | Application class needs cleanup and is Spring-managed | No `DisposableBean` dependency; uses Jakarta annotation |
| `DisposableBean` | Implement interface, override `destroy()` | Infrastructure bean designed to depend on Spring | Yes, via `org.springframework.beans.factory.DisposableBean` |
| Custom `destroyMethod` | Specify method name in `@Bean` or XML | Resource belongs to an external library whose class cannot be modified | None needed, because metadata lives in configuration |
| Inferred method | Spring auto-detects `close()/shutdown()` for eligible `@Bean`s | Library bean with a standard close API | None needed |

The mechanisms are not mutually exclusive. A single bean can use all three, though if only one cleanup step is needed, it is usually best to choose **one clear mechanism** to reduce the risk of duplicate calls and simplify maintenance.

## 3. @PreDestroy: Declaring Inside the Class

With Spring Framework 6+ and Spring Boot 3+, import:

~~~java
import jakarta.annotation.PreDestroy;
~~~

Example of an application bean:

~~~java
package demo;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class MetricsBuffer {
    private boolean closed;

    public void append(String event) {
        if (closed) {
            throw new IllegalStateException("Buffer is closed");
        }
        // Write event to the application's actual buffer.
    }

    @PreDestroy
    public void cleanup() {
        if (!closed) {
            closed = true;
            // Flush and close the buffer owned by this bean.
        }
    }
}
~~~

This is an **illustrative class**, not a standalone application; an application context scanning package `demo` is needed so Spring registers the bean and processes annotations. Spring typically detects `@PreDestroy` using `CommonAnnotationBeanPostProcessor` (part of the destruction-aware processors used by the container during destruction).

### What shape should the method have?

- Use a **no-arg**, **`void`-returning instance method**.
- May be non-public if reflection access is allowed; with the Java module system, remember to open packages where appropriate.
- Do not create new beans while the container is closing.
- Do not use the callback to launch new business processing flows.
- Should be idempotent if the same resource can also be closed via another path.
- Cleanup should run quickly, enforce timeouts on network I/O, and never block indefinitely.

In older projects using Spring Framework 5.x, the annotation may be imported from `javax.annotation.PreDestroy`. With Spring 6+, Jakarta is the proper namespace. Do not mix legacy `javax.annotation` with modern `jakarta.annotation`.

### How does @PreDestroy differ from @PostConstruct?

`@PostConstruct` runs **after injecting dependencies and before the bean is used normally**; `@PreDestroy` runs while the container/scope is destroying the bean. Both are callbacks at different stages. `@PreDestroy` is not automatically invoked when you directly call a business method named `close()`.

## 4. DisposableBean.destroy(): Spring's Dedicated Interface

The Spring interface contract:

~~~java
package org.springframework.beans.factory;

public interface DisposableBean {
    void destroy() throws Exception;
}
~~~

This is an abbreviated API signature for explanation, not a file to create yourself.

Example class implementing the interface:

~~~java
package demo;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class BackgroundSession implements DisposableBean {
    private boolean disposed;

    @Override
    public void destroy() throws Exception {
        if (!disposed) {
            disposed = true;
            System.out.println("session disposed");
        }
    }
}
~~~

When the bean is destroyed by Spring under the appropriate lifecycle, the container invokes `destroy()`. The method declaration allows `throws Exception`, yet the author still needs to design error handling for cleanup. An exception during shutdown is not necessarily propagated back to the caller across all scope/implementation types; log informatively and ensure other resources still get a chance to be released.

**Advantage:** the callback is expressed as an explicit contract; easy to recognize in infrastructure code coupled to Spring.

**Limitation:** domain/utility classes now depend on a Spring API. Spring documentation prefers `@PreDestroy` or a custom method when wanting lower coupling.

### DisposableBean is not AutoCloseable

`DisposableBean.destroy()` is called by Spring when destroying a managed bean. `AutoCloseable.close()` is a Java interface supporting `try-with-resources`. Spring can infer `close()` as a destruction method when the bean definition qualifies, but that **does not** turn every `AutoCloseable` object into a Spring-managed bean.

## 5. Custom Destroy Method via Bean Definition

The third mechanism requires no Spring annotations or interfaces on the resource class. The bean configurator specifies which method to run on destruction.

Example external library API client with a `shutdown()` method:

~~~java
@Configuration
public class ExternalClientConfig {
    @Bean(destroyMethod = "shutdown")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

This is an **illustrative snippet**, assuming `ExternalClient` is a library class with a `shutdown()` method. Place inside a `@Configuration` class with the corresponding `org.springframework.context.annotation.Bean` and `Configuration` imports.

When the target bean is destroyed, Spring invokes the registered `shutdown()` method. If the library class only has a `close()` method, declare similarly:

~~~java
@Bean(destroyMethod = "close")
public ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

In XML configuration, the corresponding metadata:

~~~xml
<bean id="externalClient"
      class="example.ExternalClient"
      destroy-method="shutdown"/>
~~~

The XML snippet is part of a `<beans>` configuration file, not a complete XML document. Modern projects using Java configuration typically use `@Bean`.

### Why does this fit third-party libraries?

With a networking library, you cannot edit its source code to add `@PreDestroy` or `implements DisposableBean`. However, you can provide a factory method and declare the cleanup method name. The library code stays independent of Spring; ownership and close timing live in configuration.

## 6. The Inferred Destroy Method Mechanism of @Bean

For a `@Bean` method, the default value `destroyMethod = "(inferred)"` allows Spring to detect a no-arg `public close()` or `public shutdown()` method on the bean instance when applicable. A bean implementing `AutoCloseable`/`Closeable` also has `close()` for Spring to detect; this takes effect when the container actually controls the destruction lifecycle. It **does not** mean Spring automatically closes every object created with `new` or every component having a `close()` method.

If a resource is owned by another system, you can declare `@Bean(destroyMethod = "")` to disable custom destroy method inference for that bean definition. This setting **does not disable** `@PreDestroy` or `DisposableBean.destroy()` independently. If another callback directly calls `close()`, you still need to review the ownership contract.

The next lesson specifically examines the detection order of `close`/`shutdown`, behavior when disabling inference, method signatures, and runnable examples. In this lesson, the key takeaway is that **configured/inferred destroy methods are one of the three destruction hook groups**, coming after `@PreDestroy` and `DisposableBean` when each hook is a distinct method.

## 7. Callback Order When Combined

When a bean has three separate callbacks, Spring executes them in order:

1. `@PreDestroy` method.
2. `DisposableBean.destroy()`.
3. Custom configured destroy method (e.g., `@Bean(destroyMethod = "finish")`).

~~~text
Spring decides to destroy target
       |
       v
BeanPostProcessor invokes @PreDestroy method
       |
       v
DisposableBean.destroy()
       |
       v
@Bean(destroyMethod = "finish")
       |
       v
Destruction lifecycle complete
~~~

**This is the order of callbacks within the same bean.** Across multiple beans, destruction order depends on bean dependencies, scope, and context. There is no rule that every `@PreDestroy` of all beans runs before every `DisposableBean.destroy()` of all beans.

The order above also mirrors the initialization callbacks (`@PostConstruct` → `InitializingBean.afterPropertiesSet()` → custom `initMethod`); do not mix up startup and shutdown.

## 8. Standalone Runnable Java 17 Example: All Three Callbacks on One Bean

### 8.1. Directory layout

~~~text
destroy-callback-demo/
├── pom.xml
└── src/main/java/demo/
    └── DestroyCallbackDemo.java
~~~

### 8.2. pom.xml

The example uses Spring Framework 6.2.9 and Jakarta Annotations 2.1.1:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>destroy-callback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. src/main/java/demo/DestroyCallbackDemo.java

~~~java
package demo;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class DestroyCallbackDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ManagedResource resource = context.getBean(ManagedResource.class);
            resource.use();
        }

        System.out.println("context closed");
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean(destroyMethod = "finish")
        public ManagedResource managedResource() {
            return new ManagedResource();
        }
    }

    public static class ManagedResource implements DisposableBean {
        private boolean closed;

        public ManagedResource() {
            System.out.println("resource created");
        }

        public void use() {
            if (closed) {
                throw new IllegalStateException("Already closed");
            }
            System.out.println("resource in use");
        }

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("1. @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("2. DisposableBean.destroy()");
        }

        public void finish() {
            if (!closed) {
                closed = true;
                System.out.println("3. @Bean(destroyMethod=finish)");
            }
        }
    }
}
~~~

### 8.4. Run

From the `destroy-callback-demo` directory:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.DestroyCallbackDemo
~~~

**Program stdout** (excluding Maven messages if any):

~~~text
resource created
resource in use
1. @PreDestroy
2. DisposableBean.destroy()
3. @Bean(destroyMethod=finish)
context closed
~~~

**Explanation of results:**

- `AnnotationConfigApplicationContext` reads `AppConfig`, creates `ManagedResource` as a singleton, and registers destruction metadata.
- The constructor prints `resource created`. `resource.use()` prints `resource in use`.
- Exiting the `try` block causes `context.close()` to run, even if the `try` body throws an exception.
- Spring calls `beforeDestroy()` via `@PreDestroy`, then `destroy()` via the `DisposableBean` interface, and finally `finish()` from `@Bean(destroyMethod = "finish")`.
- The program prints `context closed` **after** `close()` completes.

The example uses neither Spring Boot nor an HTTP server, so stdout is independent of requests. The methods have distinct names to prove the exact callback order. The code includes package, imports, filenames, nested configuration, and a Java 17+ `main`.

### 8.5. Self-experiments

1. Remove `@PreDestroy` from `beforeDestroy()` and re-run: only the interface callback and custom method remain.
2. Remove `implements DisposableBean` and `destroy()`: the custom method is still invoked when Spring closes the singleton.
3. Replace `destroyMethod = "finish"` with `destroyMethod = ""`: Spring no longer invokes custom `finish()` via the bean definition; the other two callbacks are not disabled.
4. Try another class that only has a public `close()` inside `@Bean` without specifying a destroy method: observe the inferred method feature.
5. Replace `try-with-resources` with a context that is created but never closed: do not expect callbacks to run automatically when `main` finishes if no shutdown hook is registered.
6. Create two beans with a real dependency to observe destruction ordering between dependent and dependency, not just the three callbacks inside one bean.

## 9. When Does Spring Actually Run Callbacks?

### 9.1. Singleton

For a singleton created and managed by `ApplicationContext`, the container is responsible for destruction. In plain Java programs, use:

~~~java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Use beans.
} // context.close() is invoked automatically.
~~~

This is a **snippet inside a method**, relying on `AppConfig` from the example above. You can call `context.close()` manually; `ConfigurableApplicationContext` itself also offers `registerShutdownHook()` so the JVM gets a chance to close the container on normal shutdown.

In Spring Boot, the context and shutdown hook are managed by the framework runtime. When receiving a normal stop signal with sufficient time, Spring coordinates stop/close and destruction. However, a forcibly killed process or crash does not guarantee callbacks run. Never use destruction callbacks as the sole place to persist critical data.

### 9.2. Prototype: not automatically destroyed after returning the instance

With `@Scope("prototype")`, Spring creates and initializes the bean each time the container is asked for one, but **does not retain a list of all prototype instances handed to callers to auto-destroy when ApplicationContext closes**.

Conceptual example:

~~~java
@Bean(destroyMethod = "close")
@Scope("prototype")
public TempHandle tempHandle() {
    return new TempHandle();
}
~~~

This snippet requires a `TempHandle` class with `close()`, importing `@Scope`, and proper Spring configuration. Even with destroy method metadata, **the caller must proactively manage the resource lifecycle of each prototype instance**. The caller can invoke `close()` if it owns the resource, or use the bean factory's explicit destruction API when wanting Spring lifecycle hooks applied.

This also holds when a prototype is injected into a singleton: if injected once into the constructor, the singleton holds a reference to that single instance and does not automatically obtain a new prototype on each call. When dynamic lookup is needed, use `ObjectProvider<T>` or an appropriate scoped proxy design; target cleanup must still be decided.

### 9.3. Request, session, and application

In a `WebApplicationContext` supporting web scopes, Spring stores request/session targets per HTTP request/session. Destruction callbacks are coordinated by the scope when the target's lifetime ends, such as when the request finishes or the session is invalidated/expired.

| Scope | Target lifetime | Typical end point |
| --- | --- | --- |
| `request` | One HTTP request | Spring finishes the request lifecycle |
| `session` | One HTTP session | Session invalidates or expires |
| `application` | One ServletContext | End of the application/ServletContext lifecycle |
| Custom scope | Application-defined | Determined by the scope implementation |

A scoped proxy can be injected into a singleton, yet **a proxy is not the target**. A request target can be created and destroyed within a single request while the singleton/proxy stays alive; callbacks apply to targets per scope, not to every method call on the proxy.

### 9.4. Custom scopes and destruction callbacks

An implementation of `org.springframework.beans.factory.config.Scope` must support:

~~~java
void registerDestructionCallback(String name, Runnable callback);
~~~

Spring submits a destruction callback to the scope when a bean has cleanup metadata. The scope implementation must store and **invoke the callback when the target/scope ends**; otherwise, the bean may be evicted from storage while its resources remain unclosed.

`Scope.remove(String name)` normally removes the target/callback from the registry and returns the target so the caller can destroy it under its own responsibility. It is not a promise that callbacks are always invoked inside `remove`. A custom `end()`/`closeConversation()` API must coordinate cleanup of remaining targets, ensuring single execution and freeing storage.

## 10. Destruction Order Across Multiple Beans

The three-callback order is a rule **within a single bean**. Across beans, Spring tries to respect dependencies: a dependent bean gets a chance to clean up **before** the bean it depends on when the container destroys singletons.

Example `InvoiceService` using `RemoteClient`:

~~~text
At initialization:
RemoteClient → InvoiceService

When closing context:
InvoiceService cleanup
       ↓
RemoteClient cleanup
~~~

This allows `InvoiceService` to flush data through the client before `RemoteClient` closes the socket. If a relationship is not expressed via injection, dependency metadata such as `@DependsOn` may be needed (when truly appropriate), though do not overuse it to dictate arbitrary ordering.

While the context is closing, callbacks should not call `context.getBean()` to create new singletons. Dependencies may already be undergoing destruction; creating new beans during shutdown is an unstable design.

### SmartLifecycle vs destruction callbacks

For components with background threads or worker queues, "stop accepting jobs" may need to happen before "close socket". Spring provides `Lifecycle` and `SmartLifecycle` to participate in startup/shutdown phases; normal shutdown handles stopping first and general bean destruction afterward.

`SmartLifecycle.stop(Runnable)` is useful when coordinating a bounded graceful stop. Afterward, `@PreDestroy` or a custom destroy method closes remaining resources. Nevertheless, in some abnormal situations, destroy might be called without full stop callbacks; cleanup must still remain safe.

## 11. Principles for Writing Reliable Cleanup

### 11.1. Resource ownership

Only close resources that the bean truly owns. If a bean receives a resource from another Spring-managed singleton, the bean providing the resource is typically the owner; if an object references a shared connection pool, never close the whole pool from a request-scoped bean.

### 11.2. Idempotency

A resource might be closed directly by application code and closed again by Spring during context shutdown. Designing `close` to tolerate repeated calls is safer when the resource contract permits.

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

public class SafeResource implements AutoCloseable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        System.out.println("closed once");
    }

    public static void main(String[] args) {
        SafeResource resource = new SafeResource();
        resource.close();
        resource.close();
    }
}
~~~

Run standalone with Java 17:

~~~bash
javac -d . SafeResource.java
java demo.SafeResource
~~~

Stdout output:

~~~text
closed once
~~~

The source file above should be named `SafeResource.java` (even with `package demo`, `javac -d .` puts the output in the right package). `AtomicBoolean` prevents executing the cleanup body multiple times across concurrent calls. It does not by itself manage tasks actively using the resource; resources with in-flight requests need proper synchronization and quiescence.

### 11.3. Errors while cleaning up resources

Cleanup can throw exceptions due to networking or I/O. Designs should have informative logging, bounded timeouts, and still attempt to release remaining resources. Do not assume an exception in `@PreDestroy` will be rethrown to the `context.close()` caller identically across all Spring versions/processors/scopes. The main responsibility is that shutdown can proceed and errors are observable.

Example method closing two resources:

~~~java
public void closeBoth(AutoCloseable first, AutoCloseable second)
        throws Exception {
    Exception failure = null;
    try {
        first.close();
    } catch (Exception ex) {
        failure = ex;
    }
    try {
        second.close();
    } catch (Exception ex) {
        if (failure == null) {
            failure = ex;
        } else {
            failure.addSuppressed(ex);
        }
    }
    if (failure != null) {
        throw failure;
    }
}
~~~

This is an **illustrative method**, not a standalone class. The goal is not skipping the second resource just because closing the first resource failed. In a real bean, ensure the closing order and ownership of both.

### 11.4. Avoid indefinite blocking

Never wait indefinitely on `Thread.join()` or an HTTP response without a timeout inside a destruction callback. When stopping, stop accepting new work, signal threads, and wait with a bound; if the deployment platform enforces a shutdown deadline, align phases accordingly. Callbacks may run on the thread closing the context, so blocking prolongs application shutdown.

### 11.5. Do not use destructors for business writes that must not be lost

Destruction callbacks are not guaranteed to run under every process exit mode. Transaction commits, outboxes, durable queues, and recovery must happen in business flows or proper persistence infrastructure. Callbacks should only handle cleanup and graceful shutdown.

## 12. Testing the Lifecycle

A good test must make Spring **actually destroy the bean**, then assert the effect. Calling `bean.cleanup()` directly does not prove Spring recognized the annotation.

Cases worth testing:

1. Singleton created in `AnnotationConfigApplicationContext`: callback has not run before closing the context and runs after `close()`.
2. Same bean with all three differently named callbacks: verify order `@PreDestroy` → `DisposableBean.destroy()` → custom method.
3. `@Bean` bean with public `close()` and no specified destroy method: verify inference when the bean qualifies.
4. `@Bean(destroyMethod = "")`: verify only inferred method handling is disabled, without losing other annotation/interface callbacks.
5. Prototype handed out to a caller: verify closing the context does **not** automatically destroy all prototype targets; cleanup belongs to the caller.
6. Request-scoped target: in an HTTP integration test, verify the callback runs per request lifecycle rather than the singleton proxy's lifecycle.
7. Error path: a bean resource fails to close; logging and cleanup of other resources are still handled properly.
8. Two-bean dependency: the dependent cleans up before the dependency during normal singleton shutdown.
9. Idempotency: closing the resource repeatedly does not corrupt data or throw unreasonable exceptions.
10. Do not leak test contexts; use `try-with-resources`/`finally` for tests creating dedicated containers.

When using Spring TestContext caching, a context can stay alive across multiple test methods. Singleton destruction **does not necessarily run after each test method**, but rather when the context is actually closed or evicted from cache. Test startup/shutdown with a dedicated context to avoid confusion.

## 13. Common Errors and How to Fix Them

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `@PreDestroy` is not called | Object created with `new` outside Spring | Hand lifecycle to container or clean up proactively from owner |
| Annotation not recognized | Wrong `javax`/`jakarta` namespace, missing annotation processing | Use `jakarta.annotation.PreDestroy` with Spring 6+ and a supporting context |
| No callback seen when `main` exits | Plain Java context never closed, no shutdown hook | Use `try-with-resources` or register a shutdown hook |
| `@Bean` calls `close()` even though undeclared | Default inferred destroy method | Check ownership; use `destroyMethod = ""` when justified |
| Inference disabled yet callback still runs | `@PreDestroy` or `DisposableBean` still present | Review all destruction metadata |
| Prototype is not cleaned up on context close | Spring does not automatically manage destruction of handed-out prototypes | Caller closes resources or uses the appropriate bean destruction API |
| `shutdown` method does not run | Wrong name/signature, bean never created, or scope never closed | Check metadata, target, scope, and logs |
| Threads/sockets remain after shutdown | Cleanup never ran, incomplete handling, or close stalled on error | Trace resource ownership and shutdown path |
| Callback invoked multiple times across app code | Resource closed both manually and by container | Idempotency and single-owner convention |
| Resource destruction order is wrong | Real dependency between beans not declared | Use proper injection and dependency metadata |
| Shutdown hangs | Callback blocks waiting indefinitely on threads/network | Appropriate stop phases, timeouts, and cancellation |
| Callback depends on request context and fails on app shutdown | No active HTTP request during singleton shutdown | Separate business data from request-bound context |
| Test does not see destructor | Test context is still cached | Close a dedicated context to verify lifecycle |
| Callback does not run when process receives SIGKILL | OS forcibly terminates process; Spring cannot run | Have recovery mechanisms; never rely on callbacks for critical data |

### Diagnostic sequence

Check: **(1)** is the object really a Spring bean; **(2)** was the target ever created; **(3)** which scope owns the target; **(4)** has the lifecycle endpoint occurred yet; **(5)** what callback metadata does the bean have; **(6)** did the callback error out or time out; **(7)** is anything still referencing or using the closed resource? Do not swap the three mechanisms by trial-and-error without identifying the cause.

## 14. Self-Check Questions

**Question 1: Can you just add `@PreDestroy` to an object created with `new` and expect Spring to close it automatically?**  
**Answer:** No. The object must belong to a Spring-managed lifecycle, or the caller must clean up itself.

**Question 2: A singleton has `@PreDestroy`, `DisposableBean.destroy()`, and `@Bean(destroyMethod="finish")`. With three differently named methods, what is the order?**  
**Answer:** `@PreDestroy` first, `DisposableBean.destroy()` next, and custom `finish()` last.

**Question 3: Does setting `@Bean(destroyMethod = "")` disable `@PreDestroy`?**  
**Answer:** No. It only disables the inferred custom destroy method, without disabling other lifecycle mechanisms.

**Question 4: Why does BeanFactory not automatically destroy all prototype instances?**  
**Answer:** After creating and returning a prototype target to the caller, the container does not continue tracking each instance to clean up on context close; the caller is responsible for cleanup.

**Question 5: Must you declare `destroyMethod = "close"` for every `@Bean` returning an AutoCloseable?**  
**Answer:** Not necessarily. Spring `@Bean` supports inferred `close`/`shutdown` by default on eligible beans. Explicit declaration can clarify ownership, though you must understand inference and avoid closing shared resources from the wrong owner.

**Question 6: Does a shutdown hook guarantee cleanup even if the JVM is forcibly killed?**  
**Answer:** No. Hooks get a chance to run on normal JVM shutdown; crashes/SIGKILL have no guarantee.

**Question 7: A request-scoped bean is injected via a proxy into a singleton. Does the target callback run when the singleton closes or when the request ends?**  
**Answer:** Following the target's lifecycle in request scope; the singleton proxy is a separate object and does not extend the target across requests.

**Question 8: Why should `SmartLifecycle.stop()` and `@PreDestroy` not be treated as identical?**  
**Answer:** `stop()` participates in the context's coordinated shutdown process, while destruction callbacks mainly clean up bean resources; during abnormal shutdown, not all expected stop signals may occur.

## Official Documentation

- [Spring Framework Reference — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html), sections *Destruction Callbacks* and *Combining Lifecycle Mechanisms*.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html), section on lifecycle by scope.
- [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html), section on inferred destroy methods and `destroyMethod`.
- [Spring Framework Javadoc — DisposableBean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/DisposableBean.html).
- [Spring Framework Javadoc — Bean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/Bean.html).
- [Jakarta Annotations — PreDestroy](https://jakarta.ee/specifications/annotations/2.1/apidocs/jakarta.annotation/jakarta/annotation/PreDestroy.html).
