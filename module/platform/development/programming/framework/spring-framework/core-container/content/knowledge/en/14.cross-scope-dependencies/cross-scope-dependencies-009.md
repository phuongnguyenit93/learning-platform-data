# Designing, Registering, and Controlling Custom Scope Lifecycles in Spring Framework

## 1. Why Build a Custom Scope?

**Bean scope** answers the question: *For a given bean definition, over what time span or context should Spring supply the same instance?* The default `singleton` scope keeps one instance per bean definition within an IoC container; `prototype` creates an instance each time the container is asked. In web applications, `request`, `session`, `application`, and `websocket` are also available when supported by the context.

Business lifecycles sometimes do not align with built-in scopes. For example:

- A **job execution** must share a state object across steps, yet the next job needs a fresh object.
- A **batch processing run** has a short-lived cache that must be cleared when the batch finishes.
- A multi-step **conversation/wizard** needs to retain state until the user completes the conversation.
- A **unit of work** acquires resources upon first access and closes them cleanly when the work completes.

In such cases, Spring lets you define a new scope via the `org.springframework.beans.factory.config.Scope` interface, give it a name (such as `operation`), register it with `ConfigurableBeanFactory`, and attach that scope name to bean definitions.

This is a feature of **Spring Core Container / Dependency Injection**. A custom scope manages the *lifetime and identity* of target beans; it does not on its own handle transactions, locking, HTTP requests, security, or cross-JVM synchronization.

### Learning Outcomes

After this lesson, you will be able to:

1. Properly design *scope identity*, activation timing, storage, and termination boundaries.
2. Understand the semantics and contracts of the five methods in the `Scope` SPI.
3. Register a scope before Spring creates dependent beans using `registerScope` or `CustomScopeConfigurer`.
4. Use `@Scope`, scoped proxies, and `ObjectProvider` to coordinate short-lived beans with singletons.
5. Proactively run destruction callbacks, avoid leaks with thread pools, handle concurrency, exceptions, and lifecycle tests.
6. Run a Java 17 + Spring Framework example and verify each operation gets its own target and cleanup runs exactly once.

## 2. Distinguishing Bean Definition, Scope Storage, Proxy, and Target

In Spring, a bean definition holds the metadata Spring needs to create a bean: class/factory method, dependencies, lifecycle configuration, and scope name. The **Scope** is the component that stores or looks up the *target objects* of beans sharing that scope name.

~~~text
ApplicationContext / BeanFactory
  ├── bean definition: scopedState; scope="operation"
  │       └── scoped proxy (if proxyMode declared)
  │                 └── Scope.get(targetName, ObjectFactory)
  │                         ├── operation A → ScopedState #1
  │                         └── operation B → ScopedState #2
  └── bean definition: worker; scope="singleton"
          └── holds reference to scoped proxy
~~~

If a singleton holds onto a **target** created during operation A, it will accidentally reuse stale data during operation B. Instead, the singleton can hold a **scoped proxy**, or request the target via `ObjectProvider` while the operation is active.

**Do not conflate these three moments:**

1. **Scope registration:** `BeanFactory` learns that the name `operation` maps to a `Scope` implementation object.
2. **Bean definition registration:** Bean `scopedState` declares it uses `operation`; if a proxy is configured, Spring can create the proxy before any operation begins.
3. **Target creation:** Only when the application actually calls through the proxy/provider while the scope is active does `Scope.get(...)` retrieve or create the corresponding target.

Changing from `ScopedProxyMode.INTERFACES` to `TARGET_CLASS` only alters the *proxy type*, not the rules governing how targets are created or destroyed by the scope.

## 3. Designing the Lifecycle Contract Before Writing Code

A custom scope must clearly answer the following questions:

| Aspect | Decision needed | Example `operation` scope |
| --- | --- | --- |
| Context key | What identifies one scope session? | Each call to `begin(operationId)` |
| Activation | When is accessing beans valid? | Between `begin` and `end` on the same thread |
| Identity | Do two lookups of the same bean in the same context return the same instance? | Yes |
| Storage | Where are instances held? | A map bound to `ThreadLocal` in the sample |
| Creation | Who actually constructs the bean? | `ObjectFactory.getObject()` supplied by Spring |
| Early removal | What happens if an individual bean is removed? | `remove(name)` removes the instance and its callback |
| Natural destruction | Who runs callbacks when the scope ends? | `end()` runs callbacks, then releases state |
| Context propagation | Does an operation automatically cross to other threads? | Not in the sample |
| Concurrency | Do multiple threads share the same context? | No; each thread has its own scope state |
| Errors | What if a callback throws an exception? | Continue remaining callbacks, finally clean state and report errors |

**Scope identity must match the business concept.** `ThreadLocal` is suitable only for *an operation bound to a single thread*; it does not automatically become a scope for an HTTP request, distributed job, Reactor subscription, or arbitrary thread-pool tasks. If an operation spans multiple threads, you need storage keyed by operation-id and controlled context propagation—swapping out storage while keeping lifecycle/callback semantics intact.

For a scope accessible concurrently from multiple threads, you must design **atomic get-or-create per `(scope-id, bean-name)`**, handling termination while callers are active, and synchronization of destruction callbacks. Using `ConcurrentHashMap` alone does not solve races between creation, destruction, and scope closing.

## 4. Scope SPI: Five Essential Methods

Interface:

~~~java
package org.springframework.beans.factory.config;

public interface Scope {
    Object get(String name, ObjectFactory<?> objectFactory);
    Object remove(String name);
    void registerDestructionCallback(String name, Runnable callback);
    Object resolveContextualObject(String key);
    String getConversationId();
}
~~~

This is an **abbreviated illustrative signature**: nullability annotations and Javadoc are omitted, so it is not source code to compile as an application file. `ObjectFactory` belongs to `org.springframework.beans.factory.ObjectFactory`.

### 4.1. get(String name, ObjectFactory<?> objectFactory)

This is the central method Spring calls to retrieve a target:

1. Verify that the scope is **active**; if not, typically throw `IllegalStateException`.
2. Look up the target by bean name in the active scope's storage.
3. If the target already exists, return **that exact instance**.
4. If not, call `objectFactory.getObject()` so **Spring creates and initializes the target**, store it, and return it.

Do not construct targets via `new TargetClass()` inside a scope implementation: doing so bypasses Spring dependency injection, `BeanPostProcessor`s, initialization, and lifecycle handling. `ObjectFactory` is provided by `BeanFactory` to construct the bean per its metadata.

`get(...)` should not return `null`; the lifecycle contract requires returning an object. Do not call `ObjectFactory.getObject()` on every lookup in a scope whose goal is "one instance per operation": doing so turns the scope into something akin to prototype, giving the same unit of work multiple targets.

### 4.2. remove(String name)

Removes an individual target from storage and returns the removed instance, or `null` if absent. If a destruction callback exists for that bean, the scope implementation **should remove the callback from the registry** to prevent it from running again when the scope ends.

One easy point of confusion: per the `Scope` contract, `remove()` is **not required to execute the destruction callback itself**; when removal is triggered through `BeanFactory`, the caller may be responsible for destroying the bean appropriately. Therefore, avoid arbitrarily both running the callback inside `remove` and letting the caller destroy the same bean a second time.

To terminate the **entire scope**, provide a dedicated API such as `end()` or `closeConversation(id)`: that API runs callbacks for remaining targets, clears storage, and releases the context.

### 4.3. registerDestructionCallback(String name, Runnable callback)

Spring uses this method to register cleanup logic when the scoped bean actually has destruction configuration (for example `@PreDestroy`, `DisposableBean`, or a method declared via `@Bean(destroyMethod = "...")`).

The scope's responsibility is to retain the callback alongside the instance's lifecycle and **execute it when the instance/scope is naturally destroyed**. Callbacks do not run merely because the Java garbage collector reclaims a proxy, nor are they guaranteed to run when closing `ApplicationContext` unless the custom scope proactively closes any open context state.

If a scope does not support callbacks, resources such as connections, buffers, or caches can be held too long. A production implementation should:

- Allow callbacks to be added while targets are being created.
- Never run a callback twice.
- Run cleanup for remaining instances even if another callback fails.
- Clear references to instances/callbacks from storage to prevent memory leaks.
- Establish destruction order clearly; often running in **reverse order** of callback registration works, though complex dependencies need dedicated design.
- Report cleanup errors using the application's observability mechanism rather than silently swallowing exceptions.

**Distinction:** `prototype` has a different destruction lifecycle: Spring does not track and clean up every prototype instance after handing it to a client. In a custom scope, the implementation itself can proactively collect and invoke callbacks registered by `BeanFactory`.

### 4.4. resolveContextualObject(String key)

Allows resolving a scope-level object or piece of metadata by a specific key. For example, a custom operation scope might support the key `"operationId"` to access the current context's id.

If no matching contextual object exists, it may return `null`. Do not use this API as an arbitrary service locator or to expose sensitive data outside the current context. When the scope is inactive, the implementation can throw `IllegalStateException` consistently with `get`.

### 4.5. getConversationId()

Returns an identifier for the **current scope context** if meaningful. For HTTP session scope, that is usually the session id; for `operation`, it can be the operation id. It may return `null` if the scope has no suitable identifier.

The word `conversation` here is a Scope SPI concept: it does not mean you must build a web conversation or store data in an HTTP session.

## 5. Registering the Scope at the Right Time

### 5.1. registerScope: The Explicit Path

Spring provides:

~~~java
ConfigurableBeanFactory beanFactory = /* BeanFactory of the context */;
beanFactory.registerScope("operation", new OperationScope());
~~~

`registerScope(String, Scope)` binds a scope name to an implementation. Registration must happen **before any bean definition using that scope is resolved to create a target**; in practice, do this during `BeanFactory` configuration before the context begins eager singleton creation.

Never reuse `singleton` or `prototype` as a custom scope name: those are core scopes that cannot be overridden this way. Choose a distinct name expressing its semantics—`operation`, `batch`, `conversation`, etc.—and avoid colliding with other registered scopes.

In the runnable example in section 6, the order guarantees this:

~~~java
AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext();
OperationScope operationScope = new OperationScope();
context.getBeanFactory().registerScope("operation", operationScope);
context.register(AppConfig.class);
context.refresh();
~~~

This snippet sits inside the Java `main` method of the program below. `refresh()` is the context initialization boundary; proxies and singletons can be set up during that phase.

### 5.2. CustomScopeConfigurer in Spring Configuration

Spring provides `CustomScopeConfigurer`, a `BeanFactoryPostProcessor` dedicated to registering scopes. This is a suitable option when letting Spring bootstrap the entire context from configuration:

~~~java
@Bean
static CustomScopeConfigurer customScopeConfigurer() {
    CustomScopeConfigurer configurer = new CustomScopeConfigurer();
    configurer.addScope("operation", new OperationScope());
    return configurer;
}
~~~

This snippet assumes the method sits in a `@Configuration` class with `CustomScopeConfigurer` imported. Declaring `@Bean static` lets Spring create the `BeanFactoryPostProcessor` early, avoiding premature instantiation of the configuration class itself just to create the post-processor.

**Note on sharing the same instance:** If business code must call `begin()/end()` on the scope implementation, it needs a reference to **the exact same scope object registered with `BeanFactory`**. Do not accidentally construct two `new OperationScope()` objects and control the unregistered one. In that case, manage the object via explicit bootstrap as in section 6, or design a suitable factory/registrar.

A more flexible option is writing your own `BeanFactoryPostProcessor` that calls `beanFactory.registerScope("operation", scope)`. Both registration approaches are better than trying to register too late inside another singleton's constructor.

### 5.3. Declaring the Scope on a Bean

~~~java
@Component
@Scope(value = "operation", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class OperationState {
    public String status() {
        return "active";
    }
}
~~~

This illustrative snippet sits in an application that has registered the `operation` scope name. You can also place `@Scope` on a `@Bean` method or use the `scope` attribute in XML bean definitions. A custom scope name **does not come into existence** just because you put it in an annotation; `BeanFactory` must still have the corresponding scope implementation registered.

If `@Scope("operation")` leaves `proxyMode` at its default `DEFAULT`, there is normally no scoped proxy. To inject into a singleton without fetching the target ahead of time, configure a proxy or use lazy lookup.

## 6. Complete Example: An "operation" Scope with begin/end and Cleanup

The following Java 17 example **requires no Spring Boot, servlets, or HTTP server**. It illustrates opening an operation, reusing the same target within that operation, creating a new target in the next operation, and invoking cleanup callbacks when the operation closes.

### 6.1. Project Structure

~~~text
operation-scope-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ScopeLifecycleDemo.java
~~~

**pom.xml** — Spring Framework `6.2.9` and Java 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>operation-scope-demo</artifactId>
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

**src/main/java/demo/ScopeLifecycleDemo.java**

~~~java
package demo;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectFactory;
import org.springframework.beans.factory.config.Scope;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ScopedProxyMode;

public class ScopeLifecycleDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // 1. Instantiate and register the exact custom scope instance.
            OperationScope operationScope = new OperationScope();
            context.getBeanFactory().registerScope("operation", operationScope);

            // 2. Load bean definitions, then start the container.
            context.register(AppConfig.class);
            context.refresh();

            // 3. This is a singleton holding a scoped proxy.
            Worker worker = context.getBean(Worker.class);

            // 4. Open / close two business scopes sequentially.
            for (String operationId : List.of("op-A", "op-B")) {
                operationScope.begin(operationId);
                try {
                    int first = worker.currentStateId();
                    int second = worker.currentStateId();

                    System.out.println(
                            "operation=" + operationScope.getConversationId()
                                    + " first=" + first
                                    + " second=" + second);
                } finally {
                    operationScope.end();
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean(destroyMethod = "cleanup")
        @org.springframework.context.annotation.Scope(
                value = "operation",
                proxyMode = ScopedProxyMode.TARGET_CLASS)
        public ScopedState scopedState() {
            return new ScopedState();
        }

        @Bean
        public Worker worker(ScopedState scopedState) {
            return new Worker(scopedState);
        }
    }

    public static class Worker {
        private final ScopedState scopedState;

        public Worker(ScopedState scopedState) {
            this.scopedState = scopedState;
        }

        public int currentStateId() {
            return scopedState.id();
        }
    }

    public static class ScopedState {
        private static final AtomicInteger NEXT_ID = new AtomicInteger();
        private final int id = NEXT_ID.incrementAndGet();

        public int id() {
            return id;
        }

        public void cleanup() {
            System.out.println("destroy=" + id);
        }
    }

    public static class OperationScope implements Scope {
        private final ThreadLocal<Bucket> current = new ThreadLocal<>();

        // Only one operation active per thread in this example.
        public void begin(String operationId) {
            Objects.requireNonNull(operationId, "operationId");
            if (current.get() != null) {
                throw new IllegalStateException("Operation already active");
            }
            current.set(new Bucket(operationId));
        }

        // Destroy remaining targets and always clear ThreadLocal.
        public void end() {
            Bucket bucket = requireActive();
            try {
                List<Runnable> callbacks =
                        new ArrayList<>(bucket.destructionCallbacks.values());
                Collections.reverse(callbacks);

                RuntimeException failure = null;
                for (Runnable callback : callbacks) {
                    try {
                        callback.run();
                    } catch (RuntimeException ex) {
                        if (failure == null) {
                            failure = ex;
                        } else {
                            failure.addSuppressed(ex);
                        }
                    }
                }
                if (failure != null) {
                    throw failure;
                }
            } finally {
                bucket.beans.clear();
                bucket.destructionCallbacks.clear();
                current.remove();
            }
        }

        @Override
        public Object get(String name, ObjectFactory<?> objectFactory) {
            Bucket bucket = requireActive();
            return bucket.beans.computeIfAbsent(
                    name, ignored -> Objects.requireNonNull(
                            objectFactory.getObject(), "Scoped bean is null"));
        }

        @Override
        public Object remove(String name) {
            Bucket bucket = requireActive();
            bucket.destructionCallbacks.remove(name);
            return bucket.beans.remove(name);
        }

        @Override
        public void registerDestructionCallback(
                String name, Runnable callback) {
            requireActive().destructionCallbacks.put(
                    name, Objects.requireNonNull(callback));
        }

        @Override
        public Object resolveContextualObject(String key) {
            Bucket bucket = requireActive();
            return "operationId".equals(key) ? bucket.operationId : null;
        }

        @Override
        public String getConversationId() {
            return requireActive().operationId;
        }

        private Bucket requireActive() {
            Bucket bucket = current.get();
            if (bucket == null) {
                throw new IllegalStateException("No active operation scope");
            }
            return bucket;
        }

        private static class Bucket {
            final String operationId;
            final Map<String, Object> beans = new LinkedHashMap<>();
            final Map<String, Runnable> destructionCallbacks =
                    new LinkedHashMap<>();

            Bucket(String operationId) {
                this.operationId = operationId;
            }
        }
    }
}
~~~

### 6.2. Compiling and Running

Ensure `java -version` and `mvn -version` report JDK 17 or higher. In the `operation-scope-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ScopeLifecycleDemo
~~~

**Program stdout** (excluding Maven's own messages if printed by the environment):

~~~text
operation=op-A first=1 second=1
destroy=1
operation=op-B first=2 second=2
destroy=2
~~~

Explanation of each observation:

1. `Worker` is a singleton so it is created during `context.refresh()`; its constructor only receives the class proxy for `ScopedState`.
2. `begin("op-A")` opens a new `Bucket`. On the first call to `worker.currentStateId()`, the proxy requests a target, the scope invokes `ObjectFactory.getObject()`, and `ScopedState` with id 1 is created.
3. The second call within **the same operation** retrieves the same instance with id 1.
4. `end()` invokes the destruction callback Spring registered for the bean with `destroyMethod="cleanup"`. Hence `destroy=1` appears.
5. `begin("op-B")` creates another `Bucket`. The new target has id 2; upon `end()`, the callback prints `destroy=2`.

Even though `Worker` keeps **the same proxy**, the underlying `ScopedState` object changes per operation. The `begin/end` lifecycle is driven by application code, with no hidden server or request context doing it behind the scenes.

### 6.3. Why Doesn't the Code Above Use @PostConstruct to Inspect the Bean?

A singleton can be created during context refresh—that is, **before `begin()`**. If inside `Worker`'s constructor, `@PostConstruct`, or bean initialization method you called `scopedState.id()`, the scoped proxy would try to resolve the target while `OperationScope` is not yet active and fail. The constructor should only store the proxy; calls to the target happen after the operation has begun.

### 6.4. Why Use try/finally Instead of Calling end After Business Code?

If processing code throws an exception and `end()` sits after normal statements, cleanup can be skipped. `finally` ensures callbacks have a chance to run and `ThreadLocal` is cleared whether work succeeds or fails. In production applications, wrap the API in an `AutoCloseable` handle and use `try-with-resources` if you want to enforce compliance across callers:

~~~java
try (OperationHandle handle = operationManager.open("op-C")) {
    worker.process();
}
~~~

This is an **illustrative API design**, not built into Spring and not defined in section 6's program. In a real implementation, `OperationHandle.close()` must be idempotent or guard against double-close, enforce thread/ownership rules, and call `end` on the proper scope.

### 6.5. Intentional Limitations of the Example

The scope in section 6 is designed for **sequential operations, one thread at a time**, because:

- `ThreadLocal` stores state only on the exact thread that called `begin()`.
- `LinkedHashMap` is unsynchronized; safe within single-thread boundaries.
- `begin()` rejects nested openings. Supporting nested operations requires a context stack, logic to restore the prior context, and target visibility rules.
- `get()` does not support concurrent access to the same `Bucket`. If shared across threads, locking/lifecycle coordination is required.
- If a thread terminates abruptly before `finally`, cleanup is not guaranteed. In thread-pool environments, forgetting `end()` leaves reused threads carrying stale state and risks memory/data leaks.
- This is a single-JVM illustration with no persistence/distributed coordination.

Those limitations are **properties of the example implementation**, not mandatory restrictions of the Spring `Scope` interface.

## 7. Registering a Scope in Spring Boot or Large Applications

When Spring Boot creates the context automatically, you usually do not construct `AnnotationConfigApplicationContext` manually. There are two approaches:

**Approach A — use a `BeanFactoryPostProcessor` to create and register the scope:**

~~~java
@Configuration
class ScopeRegistrationConfig {

    @Bean
    static org.springframework.beans.factory.config.BeanFactoryPostProcessor
    registerOperationScope() {
        return beanFactory ->
                beanFactory.registerScope("operation", new OperationScope());
    }
}
~~~

This is an **integration snippet**, requiring `OperationScope` to be available in an application package. If code must control `begin/end`, you must provide a way to obtain **the exact registered instance**, such as a lifecycle-managed coordinator/factory. Avoid creating duplicate scope state.

**Approach B — `CustomScopeConfigurer`:**

~~~java
@Configuration
class ScopeRegistrationConfig {

    @Bean
    static org.springframework.beans.factory.config.CustomScopeConfigurer
    customScopes() {
        var configurer =
                new org.springframework.beans.factory.config.CustomScopeConfigurer();
        configurer.addScope("operation", new OperationScope());
        return configurer;
    }
}
~~~

`CustomScopeConfigurer` is a Spring-provided `BeanFactoryPostProcessor` that supports registering scopes by name. In XML configuration, you can declare a `CustomScopeConfigurer` bean and configure its `scopes` map accordingly.

**Do not register a scope late inside a controller/service constructor:** Eager singleton initialization may have already occurred before then, leaving scoped beans unrecognized. Registering during `BeanFactory` preparation/BFPP is far more reliable.

With multiple `ApplicationContext`s (for instance parent/child web contexts), register in the **`BeanFactory` holding the relevant bean definitions**. Custom scope storage and registries belong to each individual `BeanFactory`; the same name in two contexts does not automatically share the same `Scope` object or targets.

## 8. Cross-Scope Lifetimes and Interactions with Singleton/Prototype

### 8.1. Injecting Short-Lived Beans into a Singleton

~~~java
@Service
class JobService {
    private final OperationState state;

    JobService(OperationState state) {
        this.state = state;
    }

    void execute() {
        state.process();
    }
}
~~~

If `OperationState` is declared `@Scope(value = "operation", proxyMode = ScopedProxyMode.TARGET_CLASS)`, the singleton `JobService` can hold a scoped proxy. When `execute()` is called inside an active operation, the proxy locates the appropriate target.

If using `INTERFACES`, code must inject via an interface exposed by the proxy; JDK proxies are not instances of concrete implementation classes. If the class is `final`, class-based proxies cannot subclass it. That is a *proxy type* concern distinct from the custom scope's *lifecycle storage* responsibility.

### 8.2. ObjectProvider When You Want Explicit Control Over Target Retrieval Timing

~~~java
@Service
class JobService {
    private final ObjectProvider<OperationState> states;

    JobService(ObjectProvider<OperationState> states) {
        this.states = states;
    }

    void execute() {
        OperationState current = states.getObject();
        current.process();
    }
}
~~~

This illustrative snippet requires importing `org.springframework.beans.factory.ObjectProvider` and `org.springframework.stereotype.Service`, a real `OperationState` class, and a registered scope. You can use an **unproxied** `@Scope("operation")` for the target in this case. `getObject()` is called once the operation is active; if called outside an operation, the scope can throw `IllegalStateException`. A provider does not automatically open a scope or make beans "thread-safe."

### 8.3. Never Fetch a Target and Hold onto It Permanently

If a client does the following:

~~~java
OperationState cached = provider.getObject();
// Store cached in a static/global singleton field, then reuse in another operation.
~~~

then the custom scope cannot swap the target behind the `cached` reference. Once the scope's lifetime ends, resources may have been cleaned up while the caller still holds the reference. Pass only needed data out of the scope instead of retaining targets, or use a scoped proxy when context-aware lookup behavior is required.

### 8.4. How Does a Custom Scope Differ from Singleton/Prototype?

| Scope | When fetching a bean | Who determines end of life? | Target cleanup |
| --- | --- | --- | --- |
| `singleton` | Same bean instance per bean definition in the container | Container / context | Spring performs destruction on orderly container shutdown |
| `prototype` | Creates a new instance when looked up in `BeanFactory` | Caller decides usage duration | Caller is responsible for cleanup; Spring does not track instances for auto-destroy |
| Custom `operation` | Same target within one operation, different target in the next operation | Application-defined `end()` | Scope implementation executes callbacks and releases state |
| Built-in `request` in web-aware context | Same target within the HTTP request | HTTP request lifecycle | Web scope implementation handles lifecycle cleanup |

When comparing, distinguish the **actual target** from a proxy: the same scoped proxy can be used across many operations while its underlying target changes.

## 9. Controlling Destruction and Early Removal

### 9.1. Where Do Callbacks Come From?

When Spring constructs a target via `ObjectFactory` and the bean has destruction metadata, `BeanFactory` registers destruction logic with the `Scope` implementation via `registerDestructionCallback`. For example, `@Bean(destroyMethod = "cleanup")` generates the callback closing `ScopedState`.

Related mechanisms include:

- `@PreDestroy` (with Jakarta annotations API if used by the application).
- `DisposableBean.destroy()`.
- `@Bean(destroyMethod = "...")` or other destroy-method metadata.

Not every bean registers a callback: beans with no destruction logic may register none; removing entries from scope storage still needs to happen.

### 9.2. Closing the Scope Is an Explicit Application Action

A custom scope does not automatically know when a "job is finished" or a "conversation has ended" from the container alone. Designers must place `end()` at the proper execution boundary—such as a job dispatcher's `finally` block or a conversation-ending hook—and ensure every branch runs cleanup.

Closing `ApplicationContext` **does not substitute for** closing all self-managed scope contexts across threads. Merely calling `context.close()` does not mean a custom `ThreadLocal` scope will automatically gather state from every thread: that data may no longer be reachable from the thread closing the container.

### 9.3. Removing a Single Bean

In the example, `OperationScope.remove(name)`:

- Removes the target from `beans`.
- Removes the corresponding destruction callback from `destructionCallbacks`.
- Returns the removed target (or `null`).

This adheres to the standard `Scope.remove` contract: do not run the callback automatically, because the caller may handle destruction. If your application exposes an "invalidate bean" API, decide clearly whether it merely evicts or also destroys resources along one single responsible path, avoiding double destruction or resource leaks.

### 9.4. Cleanup Ordering and Errors

In the sample, callbacks run in reverse registration order. If a callback throws `RuntimeException`, the code still runs remaining callbacks, attaches subsequent errors via `addSuppressed`, and finally clears maps/`ThreadLocal` in `finally`.

In complex systems, also consider:

- Destruction order following bean dependency relationships.
- Callbacks that might mutate scope structure or trigger creation of another target during shutdown.
- Hanging/long-blocking callbacks, timeouts/cancellation.
- Distinguishing the primary business exception from cleanup exceptions so the root cause is not accidentally masked.
- Logging/metrics for callback failures.
- Thread interrupts and serious `Error`s; the system must have a clear handling policy.

The example catches `RuntimeException` only to stay concise; complex production cleanup may need a stricter error policy and a `closing` state to reject new target creation while the scope is shutting down.

## 10. Concurrency, Context Propagation, and Distribution

### 10.1. ThreadLocal Is a Strategy, Not the Definition of Scope

For `ThreadLocal`:

~~~text
Thread T1: begin("A") → target#1 → end() → remove ThreadLocal
Thread T2: begin("B") → target#2 → end() → remove ThreadLocal
Thread T1: begin("C") → target#3 → end() → remove ThreadLocal
~~~

Even when T1 is reused by a thread pool, `begin("C")` must create fresh state. Forgetting `end()` can cause the next call on the same thread to fail with "Operation already active" while still holding references. Worse, a sloppy implementation could accidentally mix data between two tasks.

Do not use `InheritableThreadLocal` as a blanket way to share scopes across `ExecutorService`: pool workers are reused and lack a one-to-one lifetime relationship with tasks. For async/reactive workflows, use proper context propagation or a scope keyed by logical operation, along with clear ownership/cleanup strategies.

### 10.2. If the Same Operation Runs Across Multiple Threads

You must redesign around an `operationId → bucket` map or an appropriate framework storage mechanism:

1. Have a mechanism to carry `operationId` to every execution segment.
2. The same `operationId` must resolve the same bucket (if business semantics require sharing).
3. `get(name, factory)` synchronizes bean creation so duplicate instances are never created.
4. Do not close the bucket while in-flight users remain.
5. Decide whether to use reference counting, leases, timeouts, or explicit ownership.
6. On termination, stop new creations, await/handle active requests, run callbacks, and evict storage.
7. If an operation spans multiple nodes/JVMs, state and lifecycle need dedicated distributed coordination; an in-memory map in one JVM does not share state with other nodes.

**Scope isolation does not automatically guarantee bean thread safety.** If a scoped target holds a mutable `ArrayList` accessed by multiple threads, the target can still race.

### 10.3. Timeouts and Cleanup When Clients Disconnect

For long-lived conversations or application-defined sessions, callers may fail to call `end()` due to crashes/network drops. Production scopes often need TTL/idle eviction/scheduled cleanup governed by policy, ownership boundaries, and retry/idempotency handling. Avoid letting callbacks destroy resources while a valid task is still accessing them.

## 11. Testing Strategy for Custom Scopes

Both the SPI contract and container integration should be tested.

### 11.1. Unit Tests for Scope Operations

For an implementation similar to the example:

- Calling `get("x", factory)` **before begin** must report the scope is inactive.
- `begin("A")`; calling `get("x", factory)` twice returns **the same object**, with the factory invoked only once.
- Calling `get("y", factory)` creates a distinct object.
- `resolveContextualObject("operationId")` and `getConversationId()` return id A; unknown keys return `null`.
- Register callbacks, call `end()`: callbacks run exactly once, state is cleared.
- `begin("B")`; `get("x", factory)` creates a new object.
- `remove("x")` returns the old instance and removes its callback; calling `get("x", factory)` afterward creates a new target if the operation is still active.
- `begin(...)` while already active must be rejected per the example API.
- Have a callback throw an error; verify remaining callbacks still run and `ThreadLocal` holds no leftover state.
- With multiple threads, verify isolation according to the designed contract.

### 11.2. BeanFactory Integration Tests

Run the section 6 example and verify:

- The scope is registered before refresh.
- Singleton `Worker` is created even with no active operation.
- The proxy does not resolve the target in the constructor.
- Two calls within one operation share the same instance.
- The next operation gets a new target.
- `@Bean(destroyMethod = "cleanup")` is called after each operation, never twice.
- After `end()`, calling the target through the proxy fails cleanly due to inactive scope.
- `context.close()` is not mistaken for a substitute for `end()`.

When using JUnit 5, you may share one Spring context while opening and closing separate operations in `@BeforeEach`/`@AfterEach`, strictly preventing state from a previous test from leaking into the next test. For multithreaded tests, verify not only unique ids but also callback timing and absence of data races.

## 12. Common Errors and Diagnostics

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `No Scope registered for scope name 'operation'` | Forgot to register scope or registered on the wrong `BeanFactory` | Register the exact name, on the right container, before resolving targets |
| `Scope 'operation' is not active for the current thread` | Invoked target outside `begin/end`, or on a different thread | Place calls inside an active operation or provide properly designed context propagation |
| Singleton fails initialization when injecting custom-scoped bean | Injected target directly while scope was inactive | Use a scoped proxy or `ObjectProvider` with lazy lookup |
| Every call yields a new id even in the same operation | `get` always invokes object factory without caching by bean name | Cache results by `(active scope identity, bean name)` |
| Next operation still has the old id | Stored target in a singleton/static field, or forgot to clear state on close | Hold proxy/provider, close `end`, and clear storage |
| Cleanup method does not run | Failed to store/run callbacks, bean lacks destruction metadata, or forgot `end` | Register callbacks per SPI, wrap execution boundary with `finally` |
| Callback runs twice | Executed inside `remove` and also by caller, or `end` called repeatedly unguarded | Establish single destruction responsibility and enforce idempotency where needed |
| Thread pool retains data from previous job | Forgot to clear `ThreadLocal` | Clean up in `finally`, control full job lifecycle |
| Cleanup exception skips remaining beans' cleanup | `end` aborts on the first failing callback | Run all callbacks, aggregate errors, and clear state in `finally` |
| Two threads construct the same bean twice | Non-atomic storage/get-or-create in multi-thread scope | Synchronize per scope/key and coordinate scope closing |
| Changed `proxyMode` yet scope error persists | Proxy type does not activate contexts or fix the registry | Diagnose proxy typing, registry, and scope activation separately |
| CGLIB fails to create proxy | Target bean is a `final` class or intercepted methods are `final`/`private` | Use interface-based proxy or design a proxiable class |
| One operation "shared" across JVMs has diverging state | Scope only stores local in-memory state per JVM | Design distributed state and cluster lifecycle |

When hitting an error, classify in order: **(1) is the scope name registered? (2) right `BeanFactory`? (3) is the context active? (4) does the proxy/provider fetch the target at the right moment? (5) do storage and cleanup follow exact semantics?** Read the root cause of `BeanCreationException`/`ScopeNotActiveException` instead of stopping at the outermost message.

## 13. Principles for Real-World Projects

1. **Prefer built-in scopes** when semantics already match; custom scopes add lifecycle, observability, and concurrency responsibilities.
2. Clearly define identity: which key, who opens/closes, when targets match, and maximum lifetime.
3. Delegate bean creation to Spring via `ObjectFactory`; do not bypass dependency injection.
4. Register scopes early and choose names that avoid colliding with `singleton`/`prototype` and web scopes.
5. When injecting into singletons, use scoped proxies or `ObjectProvider`; never retain targets across scope lifetimes.
6. Guarantee every target is destroyed **exactly once** per contract, especially with removal/eviction.
7. Wrap execution boundaries in `try/finally` or `try-with-resources` and always release `ThreadLocal`.
8. If concurrency or cross-thread execution is involved, design context propagation, synchronization, and shutdown sequencing up front.
9. Never assume closing the context automatically cleans up all custom-scope state created outside the container lifecycle.
10. Test happy paths as well as cancellation, bean-creation failures, callback errors, nested calls, pool reuse, and multiple contexts.

## 14. Self-Check

**Question 1.** Why should `Scope.get` call `objectFactory.getObject()` instead of `new`?

**Answer:** Because `ObjectFactory` supplied by `BeanFactory` constructs the bean according to Spring metadata, including dependency injection and lifecycle callbacks, whereas a manual `new` is not processed by Spring as a bean target.

**Question 2.** If an operation-scoped bean is injected into a singleton without a proxy, what can happen?

**Answer:** The singleton may attempt to retrieve the target at initialization when no operation is active yet, or hold onto a fixed target from an earlier operation. Use a scoped proxy/`ObjectProvider` to resolve when an operation is active.

**Question 3.** Is `Scope.remove(name)` required to invoke the destruction callback?

**Answer:** No. The contract allows the caller to handle destruction. The scope implementation should remove the registered callback to prevent duplicate destruction; closing the entire scope requires a separate mechanism to invoke callbacks.

**Question 4.** Why must a `ThreadLocal` scope clear data in `finally`?

**Answer:** Thread-pool workers can be reused. If state remains attached to a thread after an operation, it can leak data and retain references to objects that should have been destroyed.

**Question 5.** Does registering `operation` in `BeanFactory` automatically open an operation?

**Answer:** No. Registration merely creates the mapping from name → `Scope` implementation. The application must still activate and terminate the context according to the scope's semantics.

**Question 6.** When a scope is accessed concurrently by multiple threads, is `ConcurrentHashMap` sufficient?

**Answer:** No. You must coordinate get/create/destroy, closing lifecycle, callback races, ownership, and in-flight requests. A scope is only sound when it cannot hand out already-destroyed targets or create duplicates outside intended semantics.

**Question 7.** Why does the operation-scoped bean with `@Bean(destroyMethod="cleanup")` in the example print "destroy" after `end()`?

**Answer:** Spring registers the target's destruction callback with the custom scope; the application-designed `end()` API runs the callbacks and then drops storage. This is an explicit responsibility of the scope implementation.

## References

- Spring Framework Reference — [Bean Scopes / Custom Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html#beans-factory-scopes-custom).
- Spring Framework API — [Scope SPI](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/Scope.html).
- Spring Framework API — [ConfigurableBeanFactory.registerScope](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html#registerScope(java.lang.String,org.springframework.beans.factory.config.Scope)).
- Spring Framework API — [CustomScopeConfigurer](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/CustomScopeConfigurer.html).
- Spring Framework Reference — [Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html#beans-factory-scopes-other-injection).
