# ContextPropagatingTaskDecorator and Context Library Integration Requirements

## 1. The Problem: Why Does Context Disappear When Switching to a Worker Thread?

In a Spring application, the HTTP request thread typically carries thread-bound context data: a correlation ID (`correlationId`), tenant ID, observation (`Observation`) info, trace context, or MDC used to attach metadata to logs. Many libraries use `ThreadLocal` to store these values within the scope of a single thread.

When submitting a task to a `TaskExecutor` or calling an `@Async` method, Spring may execute the task on a **different worker thread**. The caller's `ThreadLocal` **does not automatically transfer to the worker**. For example:

```java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

// Request-receiving thread:
TENANT.set("tenant-A");

executor.execute(() -> {
    // Without a propagation mechanism, the value is usually null:
    System.out.println("Worker tenant = " + TENANT.get());
});

TENANT.remove();
```

This is merely an **illustrative code snippet**, assuming `executor` is already configured. The observed outcome depends on the actual executor and configuration: an executor running directly on the caller can read `tenant-A`; a normal thread pool does not automatically carry the caller's `ThreadLocal` to the worker.

Spring Framework **6.1 and above** provides the class:

```java
org.springframework.core.task.support.ContextPropagatingTaskDecorator
```

This is a `TaskDecorator` dedicated to **capturing a snapshot of accessible context at task submission, then setting that context while the task executes**, and restoring the prior state when the scope ends. The class relies on **Micrometer Context Propagation**, not a magical copy of every `ThreadLocal` in the JVM.

This topic has two inseparable parts:

1. **Configuring `ContextPropagatingTaskDecorator` on the executor that actually receives the task.**
2. **Ensuring context library integration and corresponding accessors** so the data to be propagated can be captured/restored.

Without the second part, the decorator can still be instantiated, yet it will not know how to access a custom `ThreadLocal`. Without `io.micrometer:context-propagation` on the runtime classpath, even loading or instantiating the class can fail.

### Learning Objectives

After this lesson, you will understand the snapshot/scope mechanism, check the right dependencies and versions, register `ThreadLocalAccessor`, use `ThreadPoolTaskExecutor.setTaskDecorator(...)`, apply it with `@Async`, write a runnable Maven example on Java 17, verify zero context leakage when workers are reused, and distinguish it from transactions, security, Reactor, MDC, or manual parameter passing.

## 2. Why Doesn't a Plain ThreadLocal Cross Thread Boundaries?

`ThreadLocal<T>` gives each thread its own value. Even with the same `ThreadLocal` object, different threads have separate storage slots:

```text
HTTP thread / caller              Worker thread
---------------------            ----------------
TENANT.set("tenant-A")             TENANT.get() -> null
        |
        +-- executor.execute(task) ---------->
        |
        +-- continues work                   task.run()
                                           does not automatically have tenant-A
```

`InheritableThreadLocal` is not a general fix: it supports inheritance at **child thread creation time**, whereas thread pools typically reuse workers created earlier or by other threads. Values can be stale, belong to the wrong tenant, or outlive the request if copied improperly.

You also should not call `TENANT.set(...)` on a worker and forget `remove()`. A worker thread can handle many requests sequentially; data from request A stored in a thread-local can leak into request B. With tenant or security info, this bug can become a data isolation incident.

**Safety rule:** If a thread-local must be used on a worker, you must know exactly **which value is propagated, when it is captured, when it is installed, how it is restored, and when it is cleared**. A wrapper that only `set`s without `restore` is insufficient.

## 3. What Does ContextPropagatingTaskDecorator Do?

`ContextPropagatingTaskDecorator` lives in `spring-core` and implements the `TaskDecorator` interface. Its Javadoc describes it as wrapping task execution to support context propagation, especially helpful for **logging context** or **observation context**.

Key components:

| Component | Package/API | Role |
|---|---|---|
| `TaskDecorator` | `org.springframework.core.task.TaskDecorator` | Contract for wrapping a `Runnable` before the executor runs it |
| `ContextPropagatingTaskDecorator` | `org.springframework.core.task.support` | Decorator based on Micrometer snapshots to propagate context |
| `ContextSnapshotFactory` | `io.micrometer.context` | Creates snapshots and manages capture/restore logic |
| `ContextSnapshot` | `io.micrometer.context` | Holds captured context values |
| `ContextRegistry` | `io.micrometer.context` | Registry of accessors known to Micrometer |
| `ThreadLocalAccessor<T>` | `io.micrometer.context` | Reads, sets, and resets a type of ThreadLocal |
| `ContextAccessor` | `io.micrometer.context` | Map-like context access, e.g., reactive integration |

Concise decorator contract:

```java
Runnable decorate(Runnable original);
```

Spring calls `decorate(...)` to create a Runnable capable of restoring context around `original.run()`. With `ThreadPoolTaskExecutor`, decoration is wired via:

```java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

**Not every Executor supports `setTaskDecorator(...)`.** A `java.util.concurrent.ExecutorService` created directly with `Executors.newFixedThreadPool(...)` does not automatically run Spring's decorator simply because another bean in the context configured it. You must use a Spring executor supporting `TaskDecorator` or intentionally wrap the task/executor with an appropriate mechanism.

### 3.1. Two Constructors

Spring 6.1+ Javadoc publishes:

```java
new ContextPropagatingTaskDecorator()
```

The default constructor creates a default `ContextSnapshotFactory`, normally using Micrometer's global `ContextRegistry`.

When a dedicated registry/factory is needed:

```java
new ContextPropagatingTaskDecorator(customFactory)
```

`customFactory` is a pre-configured `io.micrometer.context.ContextSnapshotFactory`. This is useful when you want to control which accessors/context types participate and avoid mixing with the global registry; a full example is in section 10.

### 3.2. A Decorator Does Not Add More Workers

A decorator does not manage the thread pool. It does not increase worker count, add queue capacity, solve rejections, or turn a synchronous computation into an asynchronous one. It only wraps **Runnable execution** once the executor has decided to run the task.

If the executor runs synchronously on the caller, the caller's thread-locals are already present; the decorator may provide no benefit while still adding overhead. Spring's Javadoc explicitly emphasizes this: the mechanism adds cost, especially worth considering if the application submits a huge volume of tiny tasks.

## 4. Integration Requirements: Adding spring-core Alone Is Not Enough

The `ContextPropagatingTaskDecorator` class belongs to Spring Framework, yet the core of the context snapshot mechanism uses Micrometer. In a standard Spring Framework 6.1+ environment, ensure the following artifact is **actually present on the runtime classpath**:

```text
io.micrometer:context-propagation
```

Maven example for a project not using the Spring Boot BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>6.2.7</version>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>context-propagation</artifactId>
        <version>1.1.3</version>
    </dependency>
</dependencies>
```

These two versions are a **concrete version pair for illustration and use in this lesson's demo**, not a claim that they are the latest releases. When working in a project with Spring Boot/dependency management, prefer **your chosen stack's BOM** instead of forcing incompatible Micrometer versions. Java requirements, runtime classpath, dependency exclusions, and deployment environments must align.

**Distinguish three requirement layers:**

1. Having a Spring Framework version that provides `ContextPropagatingTaskDecorator` (**since Spring 6.1**).
2. Having a compatible `context-propagation` jar at **runtime**, not only compile time; check the dependency tree, classloaders, and version conflicts.
3. Having the right `ThreadLocalAccessor`/`ContextAccessor` in `ContextRegistry` for **the data you actually want to propagate**. A custom `ThreadLocal` does not automatically gain an accessor just because the jar was added.

This library only provides **context propagation infrastructure**. Producing full traces/metrics also requires instrumentation, registries, tracing bridges/exporters, and corresponding observability configuration. `ContextPropagatingTaskDecorator` does not send spans to an observability backend on its own without tracing infrastructure.

### 4.1. Common Dependency Errors

| Symptom | Likely Cause | How to Fix |
|---|---|---|
| Cannot find `ContextPropagatingTaskDecorator` at compile time | Spring Framework is too old or wrong module/classpath | Verify Spring 6.1+ and proper `spring-core` import |
| `NoClassDefFoundError: io/micrometer/context/ContextSnapshotFactory` | Missing Micrometer Context Propagation at runtime | Add `io.micrometer:context-propagation` with right runtime scope |
| `NoSuchMethodError` related to Micrometer | Incompatible jar versions or conflict | Use the appropriate BOM, inspect actual dependency tree |
| Decorator runs yet custom tenant stays null | Accessor not registered, wrong registry, or context was empty on submit thread | Verify `ContextRegistry`, set timing, and capture |
| Only some execution paths have context | Decorator attached to one executor, other paths use different executors | Identify the exact executor and every thread-switch boundary |
| Previous request's context appears in next task | Set without reset, buggy custom wrapper, or faulty custom accessor | Test with reused worker, restore via Scope/finally |

In a Maven project, you can inspect the dependency:

```bash
mvn dependency:tree -Dincludes=io.micrometer:context-propagation
```

The command shows version/scope/path of the dependency in the Maven model; it does not guarantee the final deploy artifact contains the exact jar if packaging/classloader configuration differs. Verify the actual build artifact and runtime environment as well.

## 5. ContextRegistry and ThreadLocalAccessor: The Part You Must Not Skip

`ContextRegistry` knows **how to read and set each context type** through accessors. Micrometer cannot reflect over every `ThreadLocal` variable in an application to infer its meaning and lifecycle automatically.

Suppose an application has:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();
```

So Micrometer can capture `REQUEST_ID.get()` and restore it onto the task-running thread, you can register an accessor via callbacks:

```java
import io.micrometer.context.ContextRegistry;

ContextRegistry.getInstance().registerThreadLocalAccessor(
        "lesson.requestId",
        REQUEST_ID::get,
        REQUEST_ID::set,
        REQUEST_ID::remove
);
```

This is a **Java snippet inside a class declaring `REQUEST_ID`**, not a standalone program. The four-argument `registerThreadLocalAccessor` takes:

- **key**: stable identifier for the context type, e.g., `lesson.requestId`.
- **getter**: reads the value on **the current thread**.
- **setter**: sets the value inside the scope on restoration.
- **resetter**: clears the value (`ThreadLocal.remove()`) when resetting is needed.

In the demo, `ContextRegistry.getInstance()` is used because the decorator's default constructor looks up accessors via the global registry. If you create a **separate** `ContextRegistry`, you must pass that registry to `ContextSnapshotFactory` and pass the factory to the decorator; registering on a registry not used by the decorator will have no effect.

### 5.1. Implementing ThreadLocalAccessor as a Class

Micrometer also has the interface:

```java
import io.micrometer.context.ThreadLocalAccessor;

public final class RequestIdAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "lesson.requestId";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return RequestIdContext.get();
    }

    @Override
    public void setValue(String value) {
        RequestIdContext.set(value);
    }

    @Override
    public void setValue() {
        RequestIdContext.clear();
    }
}
```

This is an **illustrative class depending on an application-defined `RequestIdContext`**. Then:

```java
ContextRegistry.getInstance().registerThreadLocalAccessor(
        new RequestIdAccessor());
```

What matters is not callback vs. class form, but that **the accessor returns the right key, reads the right ThreadLocal, restores the right value, and clears at the right time**. For multiple distinct context types, separate accessors or library-provided bridges are required.

### 5.2. When Should You Register an Accessor?

Register during **application configuration startup**, before creating/running tasks needing context, and clarify registry ownership. Registering accessors with duplicate keys across modules without coordination can overwrite earlier accessors, making behavior confusing.

`ContextRegistry` is a list of accessors, **not a store holding per-request IDs**. The request ID value is still set into `ThreadLocal` on the caller during execution; the snapshot reads the value when the task is submitted.

## 6. The Capture → Restore → Cleanup Mechanism

A single execution through the decorator works like this:

```text
Submit thread:
  set REQUEST_ID = "R-100"
  |
  v
TaskDecorator.decorate(original Runnable)
  |
  +-- ContextSnapshotFactory.captureAll()
  |   looks at registered accessors
  |   stores value "R-100" in snapshot
  |
  +-- returns wrapped Runnable
  |
  v
Executor puts wrapper into queue / worker
  |
  v
Worker thread:
  snapshot opens Scope -> sets REQUEST_ID = "R-100"
  |
  +-- runs original.run()
  |      logging/tracing can read the corresponding REQUEST_ID
  |
  +-- Scope.close() -> restores pre-scope value
  v
Worker can be reused for another request
```

This is a logical model. Snapshot/scope is implemented by Micrometer, while `ThreadPoolTaskExecutor` decides when the decorator is applied and the task is run.

### 6.1. Snapshot at **Submit** Time, Not When the Worker Pulls the Task

Suppose:

```java
REQUEST_ID.set("R-100");
executor.execute(work); // decorator captures context on submit path

REQUEST_ID.set("R-200");
// The worker may not run work until after this change.
```

If `REQUEST_ID` has an accessor and the executor uses the decorator properly, `work` uses **the captured value `R-100`**, not automatically changing to `R-200` just because the caller mutated its thread-local after submitting.

Avoid explaining the decorator as holding a "live" reference to the caller's entire ThreadLocal. It saves the values captured by accessors at that point in time. For **mutable objects**, a snapshot typically holds a reference to that object rather than deep-copying all contents automatically. If the object is mutated concurrently, races and thread-safety rules still apply.

### 6.2. Scope and Cleanup Prevent Context Leaks

Micrometer uses a closeable `ContextSnapshot.Scope` to reset/restore thread-locals after the task finishes. This is especially important for worker pools because the same worker runs many tasks sequentially.

Manual snapshot pattern:

```java
ContextSnapshot snapshot = factory.captureAll();

try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
    // Inside scope: registered ThreadLocals are restored.
    process();
}
// After scope: ThreadLocals are restored to their prior values.
```

This is an illustrative snippet; `factory` is `ContextSnapshotFactory` and `process()` is provided by the application. `ContextPropagatingTaskDecorator` applies similar logic around `Runnable` execution, avoiding repeating this boilerplate on every task.

Do not conclude "zero leaks exist" across an entire app simply by enabling the decorator: an **unregistered `ThreadLocal`**, a library using a different storage mechanism, or an out-of-scope wrapper can still leak. Tests must prove that **actually supported contexts** are restored.

### 6.3. When Context Has No Value at Submit Time

If an accessor is registered yet the caller **sets no value**, the snapshot cannot invent a tenant ID. Depending on the mechanism and snapshot configuration, an absent value may not be included in the snapshot; therefore, it is crucial that workers have a clean baseline and proper scope to avoid leftover data from prior tasks.

For business flows that must strictly never reuse an old tenant, combine accurate accessor reset, context cleanup at request/task boundaries, and integration tests on **the same reused worker**. Never use context propagation as a standalone access-control mechanism.

## 7. Configuring ThreadPoolTaskExecutor in Spring

Typical Java Configuration pattern:

**File `ContextExecutorConfiguration.java` — Spring configuration class.**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ContextExecutorConfiguration {

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("ctx-worker-");

        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());

        return executor;
    }
}
```

Conditions for this snippet to take effect:

1. Spring Framework 6.1+ and a compatible `io.micrometer:context-propagation` are on the classpath.
2. This executor bean **is actually used** to submit tasks.
3. Appropriate accessors are registered or supplied by an integration library.
4. The context to propagate **is already set on the sending thread** before the task is decorated.
5. The worker does not use context outside security policy, transactions, or valid lifecycle.

**`@EnableAsync` is not needed if you only inject `TaskExecutor` and call `execute(...)` directly.** If you want to use `@Async("contextExecutor")` methods, you must enable `@Async` support and invoke through the Spring proxy.

### 7.1. @Async Selects the Right Executor

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("contextExecutor")
    public CompletableFuture<String> generate(String id) {
        return CompletableFuture.completedFuture(
                "report=" + id + ", thread="
                + Thread.currentThread().getName());
    }
}
```

This class is a **Spring component**, requiring an application context, `@EnableAsync`, and the executor configuration above; it is not standalone Java SE. Spring looks up the bean named `contextExecutor`, where the task gets decorated. However, if the method is invoked via `this.generate(...)` inside the same bean, the `@Async` interceptor is bypassed in default proxy mode and the decorator is not applied along that path.

Attaching a decorator to **another pool** does not give the pool selected by `@Async` context propagation capabilities. This is a very common configuration mistake when an application has multiple executors.

## 8. Complete Java 17 + Spring Framework + Micrometer Example

The example below requires no servlet container or tracing backend. We register an accessor for a custom `ThreadLocal<String>`, and configure two executors: one pool **without** a decorator and one pool **with** a decorator. We then verify that `@Async` also uses the decorated pool.

The example intentionally makes outcomes deterministically verifiable via `Future.get(timeout)` instead of `Thread.sleep(...)`.

### 8.1. Project Structure

```text
context-propagation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── lesson/
                └── ContextPropagationDemo.java
```

### 8.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>context-propagation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.3</version>
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
```

`spring-context` brings in the needed Spring components, and `context-propagation` is the Micrometer library providing the registry, snapshots, and accessors. Versions are pinned so the demo has consistent dependencies when learners re-run it; real projects should use their stack's dependency management.

### 8.3. File src/main/java/lesson/ContextPropagationDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ContextPropagationDemo {

    private static final ThreadLocal<String> TENANT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ContextRegistry registry = ContextRegistry.getInstance();
        registry.registerThreadLocalAccessor(
                "lesson.tenant",
                TENANT::get,
                TENANT::set,
                TENANT::remove);

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskExecutor plain = context.getBean(
                    "plainExecutor", TaskExecutor.class);
            TaskExecutor propagating = context.getBean(
                    "propagatingExecutor", TaskExecutor.class);
            TenantService service = context.getBean(TenantService.class);

            try {
                TENANT.set("tenant-A");
                System.out.println("Không decorator: "
                        + readTenant(plain));
                System.out.println("Có decorator: "
                        + readTenant(propagating));

                TENANT.set("tenant-B");
                System.out.println("Giá trị mới: "
                        + readTenant(propagating));
                System.out.println("@Async: "
                        + service.currentTenant()
                                .get(5, TimeUnit.SECONDS));

                TENANT.remove();
                System.out.println("Sau clear: "
                        + readTenant(propagating));
            } finally {
                TENANT.remove();
            }
        } finally {
            registry.removeThreadLocalAccessor("lesson.tenant");
        }
    }

    private static String readTenant(TaskExecutor executor)
            throws Exception {
        return CompletableFuture
                .supplyAsync(TENANT::get, executor)
                .get(5, TimeUnit.SECONDS);
    }

    private static ThreadPoolTaskExecutor pool(String prefix) {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix(prefix);
        return executor;
    }

    @Configuration
    @EnableAsync
    public static class Config {

        @Bean("plainExecutor")
        public ThreadPoolTaskExecutor plainExecutor() {
            return pool("plain-");
        }

        @Bean("propagatingExecutor")
        public ThreadPoolTaskExecutor propagatingExecutor() {
            ThreadPoolTaskExecutor executor = pool("ctx-");
            executor.setTaskDecorator(
                    new ContextPropagatingTaskDecorator());
            return executor;
        }

        @Bean
        public TenantService tenantService() {
            return new TenantService();
        }
    }

    public static class TenantService {

        @Async("propagatingExecutor")
        public CompletableFuture<String> currentTenant() {
            return CompletableFuture.completedFuture(
                    TENANT.get());
        }
    }
}
```

### 8.4. Compile and Run

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.ContextPropagationDemo
```

Five lines **printed by the program on normal execution**:

```text
Không decorator: null
Có decorator: tenant-A
Giá trị mới: tenant-B
@Async: tenant-B
Sau clear: null
```

Maven may print additional notices of its own if execution/configuration differs. The program output is logically deterministic:

1. `TENANT` is a **plain** `ThreadLocal`, not an `InheritableThreadLocal`. Pool `plainExecutor` runs on a separate worker, so it does not automatically see `tenant-A` from the caller.
2. Pool `propagatingExecutor` is decorated. When the caller holds `tenant-A`, the accessor reads it into the snapshot; the worker reads the same value inside the scope.
3. The caller switches to `tenant-B` and submits a new task. The new snapshot holds the new value; the new task does not reuse the previous task's snapshot.
4. `TenantService.currentTenant()` is an `@Async("propagatingExecutor")` method invoked **through the Spring bean proxy**, so it reads `tenant-B` from the decorated worker.
5. The caller calls `TENANT.remove()` before the final submission. The worker has no leftover tenant value; the last read returns `null`.
6. `get(5, TimeUnit.SECONDS)` is merely how the demo awaits results with a bound. It blocks `main`; in a real HTTP request, blocking immediately can slow the request down.
7. The context closes via `try-with-resources`; Spring manages the lifecycle of both executor beans. The global `ContextRegistry` is returned to a state without the `lesson.tenant` accessor when the demo ends.

This pattern intentionally avoids using thread sequence numbers for verification: thread names are an operational detail, while **tenant values** are what must be confirmed. For stricter verification in real projects, combine this with worker reuse tracking and ensure zero tenant leaks across concurrent requests.

### 8.5. What to Avoid When Copying the Demo to Production

- Do not use `TENANT` as an access-control decision mechanism on its own. Identity/authorization must be verified at business and security boundaries.
- Do not repeatedly register a global accessor on every HTTP request. Register once per application lifecycle, and define ownership when multiple modules exist.
- Do not modify other libraries' global registries to "fix" context bugs without understanding their tracing/security systems.
- Do not create two pools solely to demonstrate the decorator; the demo includes a plain pool for before–after comparison.
- Do not keep tokens, request streams, or short-lived mutable objects inside snapshots.
- Do not interpret `TENANT.remove()` on the caller as directly clearing the worker's `ThreadLocal`; worker cleanup is handled by the scope/accessor.

## 9. You Can Use a Custom ContextSnapshotFactory Instead of the Global Registry

A large application may want an accessor set **dedicated to one executor**. Micrometer allows configuring `ContextSnapshotFactory` with a specific `ContextRegistry`:

```java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

ContextRegistry registry = new ContextRegistry();
registry.registerThreadLocalAccessor(
        "lesson.requestId",
        REQUEST_ID::get,
        REQUEST_ID::set,
        REQUEST_ID::remove);

ContextSnapshotFactory factory =
        ContextSnapshotFactory.builder()
                .contextRegistry(registry)
                .build();

ContextPropagatingTaskDecorator decorator =
        new ContextPropagatingTaskDecorator(factory);

executor.setTaskDecorator(decorator);
```

This is a **configuration code snippet**; `REQUEST_ID` is an application `ThreadLocal<String>` and `executor` is a Spring executor supporting `setTaskDecorator`. Unlike the no-arg constructor, this snippet **binds the decorator to a factory using the designated registry**.

Customization helps when:

- You want to test with an isolated registry, avoiding touching JVM-wide accessors.
- You only want to propagate a vetted, safe subset of contexts.
- You want control over snapshot configuration (and where supported by the Micrometer version, options for handling absent values).
- Multiple libraries register different accessors and unintended interactions must be prevented.

However, a private registry can omit important accessors registered by observability libraries on the global registry. If using a custom registry, you must know clearly **which context types you dropped or kept**. Do not assume all spans/MDC will appear if the factory only sees a request ID accessor.

## 10. Logging MDC, Observation, and Trace Context: Distinct Cases

`ContextPropagatingTaskDecorator` is particularly helpful for log correlation and observability, yet the following concepts are not identical:

| Context | Purpose | Integration Requirement |
|---|---|---|
| Custom `ThreadLocal<String>` | Request ID, tenant ID, or technical info | Application-supplied/registered accessor |
| SLF4J/Logback `MDC` | Log metadata, e.g., traceId/correlationId | `ThreadLocalAccessor` integration compatible with MDC mechanism; do not assume built-in |
| Micrometer `Observation` | Tracking observation scope, metrics/tracing when configured | Observation registry, suitable accessor/instrumentation |
| Trace/span context | Linking operations across distributed systems | Tracing bridge, exporters, and matching context propagation |
| Spring Security context | Thread-bound authentication/authorization info | Dedicated Spring Security mechanism or verified accessor |
| Spring transaction context | Transaction boundaries, thread-bound resources | **Do not** treat as context safe to copy to a worker |

**Having the Context Propagation library does not mean every context is auto-registered.** Depending on the library stack in use, some accessors may be supplied by integrations/SPI; custom contexts usually need manual registration. Inspect `ContextRegistry` in practice and test a task to confirm, rather than just seeing a dependency in `pom.xml`.

### 10.1. Does MDC Propagate Automatically?

You should not make a blanket claim that all versions of SLF4J/Logback/Micrometer propagate MDC automatically. In a fully configured observability ecosystem, trace/span context and logging correlation can be bridged through accessors/instrumentation. In an application lacking an appropriate bridge, you must register an accessor for the MDC data to propagate or pick a dedicated log-context propagation solution.

MDC is usually a per-thread map. If implementing manually, you must intentionally **copy** the map on capture and restore the old map in `finally`; never share a mutable map across requests. If using a dedicated accessor, verify that it supports reset and prevents request A's MDC from leaking into request B.

### 10.2. Observation Does Not Mean Tracing Is Enabled

Micrometer Observation can help produce metrics and spans when a handler/tracing bridge is configured. The decorator can carry observation context to a worker, yet **it does not automatically start a new observation or export traces** for all code.

A task that is decorated without an active Observation at submit time may have no trace correlation to propagate. Check where observations start, registered accessors, logging patterns, tracing exporters, and actual log output.

## 11. SecurityContext and Transactions: Safety Boundaries

### 11.1. Security Context Needs Its Own Policy

Spring Security's `SecurityContextHolder` has a thread-based storage strategy; switching threads usually loses context unless an explicit mechanism exists. Some integrations may provide appropriate accessors/adapters, yet **do not assume `ContextPropagatingTaskDecorator` automatically copies the entire security context**.

Spring Security also has dedicated wrappers and executors such as `DelegatingSecurityContextAsyncTaskExecutor`. When choosing a solution, check:

- When is security context captured; is it mid-authentication or already sanitized?
- Does the worker truly need the principal or only a non-sensitive ID?
- Is user A's context retained after the task finishes?
- Could an old principal be accidentally passed across a worker pool or another callback?
- Are permissions re-checked in background tasks if business logic involves long wait times?

Context propagation is a **data-transport mechanism**, not a replacement for authentication/authorization. Do not copy tokens, passwords, or HTTP request objects to workers without an approved security requirement.

### 11.2. Do Not Propagate Caller Transactions Like an Arbitrary ThreadLocal

Spring transactions typically use thread-bound resources and transaction state. Propagating the associated `ThreadLocal`s to a worker **does not mean safely transferring the same transaction** to another thread.

```text
Request thread:
  @Transactional TX-A starts
       |
       +--> executor submits task
       |
  TX-A commits/rolls back per caller

Worker thread:
  executes independently in time
  does not automatically join TX-A
  if transaction needed: design appropriate TX-B on worker
```

When a task needs data valid only after commit, consider transaction events, outbox patterns, or durable orchestration mechanisms. Do not write a custom `ThreadLocalAccessor` to copy raw JDBC connections, `EntityManager`, or caller transaction status.

**Propagating a correlation ID** and **propagating access to thread-bound resources** are two very different problems.

## 12. @Async, CompletableFuture, and Every Executor Transition

An `@Async("contextExecutor")` method called through a Spring proxy dispatches method execution to the decorated executor bean. However, that **does not guarantee all subsequent CompletableFuture steps run on the same executor**.

Example:

```java
CompletableFuture<Result> future = service.load();

CompletableFuture<String> next = future.thenApplyAsync(
        value -> transform(value));
```

This is an **illustrative code snippet**, with `Result` and `transform` defined by the application. `thenApplyAsync(...)` without an executor may use CompletableFuture's default executor (usually the common pool), which **is not guaranteed to have `contextExecutor`'s context propagation**. Similarly, `CompletableFuture.supplyAsync(...)` without an executor may run outside the decorated pool.

If you need to keep a context-carrying execution path, specify the executor explicitly:

```java
CompletableFuture<String> next = future.thenApplyAsync(
        value -> transform(value),
        contextExecutor);
```

Even then, you still must know **which thread registers the continuation** and which context is active **at the time the continuation is scheduled**. If the callback is scheduled from a thread lacking context, the decorator cannot recover the original request ID from an already completed Future.

For complex pipelines, you may need to capture snapshots at the root boundary, use a context-aware executor/API, or pass explicit correlation IDs to each step. Do not add the decorator once and assume propagation crosses every library and every stage.

### 12.1. Avoid Creating Two Redundant Layers of Scheduling

If a service already uses `@Async("contextExecutor")`, there is no need to wrap another `CompletableFuture.supplyAsync(...)` without an executor inside the method body just to "run more asynchronously". Doing so can move work to the common pool, lose context, and complicate error handling.

Likewise, an `@Async` method returning `CompletableFuture.completedFuture(value)` inside the worker **is completely valid**: the Spring proxy holds the asynchronous handle for the method invocation, while the target method supplies a completed placeholder future matching the signature.

## 13. TaskDecorator Is Not a Task Error-Catching Mechanism

`ThreadPoolTaskExecutor.setTaskDecorator(...)` Javadoc warns that the decorator may be applied to an **internal execution callback**, not the exact `Runnable`/`Callable` submitted by the caller. With `submit(...)`, the callback may be a `FutureTask`: `FutureTask.run()` typically holds exceptions inside the Future rather than throwing out of the wrapper.

Therefore, a custom `TaskDecorator` like:

```java
return () -> {
    try {
        runnable.run();
    } catch (RuntimeException error) {
        log(error);
        throw error;
    }
};
```

cannot be relied upon to log **every** error from `submit(...)`. The snippet above only illustrates catching in a wrapper; `runnable` and `log(...)` must exist in an appropriate method/class.

`ContextPropagatingTaskDecorator`'s job is **restoring context around execution**, not handling errors. With Spring `@Async void`, qualifying errors can go to `AsyncUncaughtExceptionHandler`; with `Future/CompletableFuture`, the caller must observe the Future; with plain Java `ExecutorService`, errors follow the corresponding `execute/submit` contracts.

If a task throws an exception, the snapshot scope still needs to close in the wrapping mechanism's `finally` path to prevent context leaks. This is a good reason to use a library with a clear scope contract rather than manually `set`ting and forgetting cleanup.

## 14. CompositeTaskDecorator When Multiple Concerns Are Needed

An application may need telemetry, business naming, or timing alongside context propagation. Spring provides `CompositeTaskDecorator` to combine multiple `TaskDecorator`s:

```java
import java.util.List;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.CompositeTaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

TaskDecorator timing = runnable -> () -> {
    long start = System.nanoTime();
    try {
        runnable.run();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("elapsedNs=" + elapsed);
    }
};

TaskDecorator composite = new CompositeTaskDecorator(
        List.of(new ContextPropagatingTaskDecorator(), timing));

executor.setTaskDecorator(composite);
```

This is a **code snippet in a configuration class** with an `executor` supporting `setTaskDecorator`. It is not a standalone program. The goal is showing how to compose concerns; in production do not use `System.out` per task due to overhead.

**Decorator ordering affects scope open/close order and timing code order.** When a logging/timing decorator needs to observe the restored context, test the wrapping order instead of guessing from list placement. If two decorators modify the same `ThreadLocal`, their cleanup rules must be compatible, or one may overwrite the other's value.

## 15. Observability and Performance: Not Every Context Is Worth Capturing

According to Spring Javadoc, `ContextPropagatingTaskDecorator` carries overhead and **is not recommended to be applied blindly to a huge volume of very small tasks**.

Potential costs include:

- Reading registered accessors when tasks are submitted.
- Creating snapshots and wrappers per task (depending on implementation).
- Setting/restoring values in `ThreadLocal` around every execution.
- Additional object allocations, GC pressure, and logging/tracing integration work.
- Carrying excessive context data unnecessary for the task.

If a task only increments a counter in a few microseconds, overhead can be significant compared to business logic; if a task performs hundreds of milliseconds of I/O, that cost is usually smaller—though still worth measuring on real workloads.

Verification suggestions:

1. Benchmark two configurations under identical load: with and without the decorator, keeping worker/queue counts fixed.
2. Measure `task queue wait`, `run duration`, p95/p99, and throughput.
3. Measure allocated bytes/GC, snapshot size, and number of participating accessors.
4. Assess whether the improved trace/log correlation is genuinely useful.
5. Limit context to data actually needed by the worker.
6. Never put tokens or large request objects into ThreadLocal just so they "tag along" on every task.

Be careful to separate **throughput**, **per-task cost**, and **context accuracy**. Having the decorator turned on and tasks running is not enough to claim the integration meets operational requirements.

## 16. Spring Boot: Auto-Configuration Does Not Replace Understanding the Actual Executor

In supported Spring Boot versions, observability documentation provides the property:

```properties
spring.task.execution.propagate-context=true
```

This property provides **opt-in propagation for the Spring Boot auto-configured AsyncTaskExecutor**. **Not every Boot version has this property**, and it must not be treated as proof that a **manually registered** executor already has the decorator.

Boot documentation also notes: if you define your own `AsyncTaskExecutor`, configure `ContextPropagatingTaskDecorator` appropriately — for example, declaring a decorator bean or attaching it directly to the executor as supported by your version — rather than expecting the property to automatically modify every custom pool.

In a concrete system, verify:

- The actual Spring Boot and `spring-context` versions.
- Which `TaskExecutor`/`AsyncTaskExecutor` bean `@Async` is using.
- Whether the bean is created by Boot or manually by the application.
- Whether the `context-propagation` dependency is present at runtime.
- Whether accessors/registries are initialized before tasks are submitted.
- Whether other paths such as `@Scheduled`, `CompletableFuture`, or external libraries pass through that executor.

**Do not confuse with** `spring.reactor.context-propagation=auto`: that configures Reactor's propagation mechanism in supported Boot versions, not a global switch forcing every Java thread pool to copy ThreadLocals.

## 17. Reactor Context Differs From ThreadLocal Context

In Spring WebFlux/Reactor, context data is typically placed in `reactor.util.context.Context` attached to the reactive pipeline. It is not identical to `ThreadLocal`:

- `ThreadLocal` is bound to the executing thread.
- Reactor `Context` is bound to the subscription/Publisher chain.
- A reactive pipeline can switch threads via `publishOn`/`subscribeOn` without automatically preserving active ThreadLocals onto the new thread.

Micrometer Context Propagation supplies `ContextAccessor` and snapshot mechanisms to **bridge between context types** when configured. `ContextPropagatingTaskDecorator` is useful at **the TaskExecutor Runnable boundary**, yet it does not automatically turn every Reactor operator into something with restored MDC/ThreadLocal.

If an application bridges from WebFlux to `@Async` or vice versa, check explicitly:

1. Is the source context Reactor Context or ThreadLocal?
2. When and where is the snapshot captured?
3. Is the appropriate accessor registered?
4. Which executor/reactive operator owns restoration?
5. Could context keys be lost or overwritten across scopes?

In cases where only a request ID is needed to log a simple task, passing an explicit ID via parameter is easier to control than building a complex propagation pipeline.

## 18. Boundaries Where You Need a Different Solution

| Need | Is ContextPropagatingTaskDecorator Enough? | Additional Solution / Check |
|---|---|---|
| Propagate custom request ID via `ThreadPoolTaskExecutor` | Possibly, **once accessor is registered** | Test capture/restore, cleanup |
| Preserve trace correlation for `@Async` | Possibly, with right observability integration | Check tracing bridge/accessors and exact executor |
| Propagate MDC for every logging framework | No universal guarantee | Evaluate accessors and logging stack |
| Propagate Spring Security context | Not automatically | Consider appropriate Spring Security wrappers/bridges |
| Keep caller's transaction on worker | **No** | Open a separate transaction, coordinate after commit |
| Auto-propagate context via plain Java `ExecutorService` | Not automatically | Wrap task/executor or choose decorated Spring executor |
| Propagate context across all `CompletableFuture.*Async` | Not automatically | Pass appropriate executor, capture context at schedule time |
| Propagate context to another JVM/service | No | HTTP headers, messaging metadata, network tracing propagation |
| Guarantee tasks survive restarts | No | Durable queues, outbox, persistence |
| Limit workers/queues/backpressure | No | Executor sizing, load shedding, rejection policies |

**The hardest point:** context propagation does not create a **transactional, authorization, or durability relationship** between caller and worker. It merely carries permitted, supported values to the corresponding execution scope.

## 19. Implementation Mistakes and Fixes

| Mistake | Symptom | Proper Fix |
|---|---|---|
| Adding decorator without `context-propagation` | Missing Micrometer classes at runtime | Declare compatible dependency at runtime |
| Using Spring older than 6.1 | Decorator class cannot be found | Upgrade to a Spring version with that API |
| Creating `new ContextPropagatingTaskDecorator()` without attaching to pool | Worker still loses context | `executor.setTaskDecorator(...)` on the **active pool** |
| Registering custom accessor in private registry while decorator uses global registry | Task sees `null` | Pass factory using the matching registry |
| Assuming every `ThreadLocal` propagates automatically | Tenant/MDC does not appear | Register/verify the corresponding `ThreadLocalAccessor` |
| Changing `ThreadLocal` after submit and expecting worker to see new value | Worker uses old value | Understand snapshot at schedule time; submit new task if needed |
| Using `InheritableThreadLocal` to "fix" thread pool | Value can be stale/wrong request | Propagate context with explicit scope/restore |
| Manually setting context on worker and forgetting remove | Request B reads Request A's data | Use scope/finally and test worker reuse |
| Internal `@Async` call `this.method()` | Bypasses proxy, decorator never runs | Call another bean via Spring proxy |
| `@Async` uses a different executor from the decorated bean | Only some tasks have context | Explicitly specify `@Async("contextExecutor")` |
| `CompletableFuture.supplyAsync(...)` without executor | Context may be lost in common pool | Supply executor and capture at right time |
| Treating context snapshot as deep object copy | Shared mutable object races | Use immutable values or clear ownership |
| Copying transaction/JDBC resources to worker | Transaction errors or cross-thread resource misuse | Create separate transaction/resources |
| Assuming traces exist just from decorator | No spans/exports | Configure observation/tracing bridge |
| Using decorator to catch `submit` errors | Exception sits inside Future | Observe `Future.get/CompletableFuture` |
| Enabling for millions of tiny tasks without measuring | Higher allocation/CPU/GC | Benchmark, limit contexts, pick another path |

## 20. Proper Testing: Propagating, Not Propagating, and Not Leaking

To evaluate a context propagation feature, do not test only the "one request, one task" case.

### 20.1. Minimum Test Suite

1. **With context:** Caller sets `requestId=A` and submits to decorated executor; worker must see A.
2. **Without decorator:** Submit to plain pool; worker must not accidentally see caller's ThreadLocal A.
3. **Context change:** Caller switches to B before submitting second task; worker must see B for that task, not A.
4. **Caller clear:** After caller removes context, next task on the same worker must see neither A nor B.
5. **Failing task:** Task throws exception; scope still closes, subsequent submit leaks no context from the failed task.
6. **Multiple workers:** Interleaved tasks from different tenants must each preserve their own snapshot without mixing.
7. **Queued delay test:** Caller changes context after task is queued; worker still uses snapshot from submit time.
8. **Multiple executors:** One executor with decorator, one without; verify which boundaries actually support propagation.
9. **Missing accessor:** Prove a custom ThreadLocal is not propagated without a bridge.
10. **Runtime dependency:** Ensure the deployable artifact includes the Micrometer jar at the right version; not just compile pass.

### 20.2. Avoid Tests Relying on Thread.sleep

`Thread.sleep(100)` does not guarantee a worker or cleanup handler has finished. Use `CountDownLatch`, `Future.get(timeout)`, or `CompletableFuture` to await specific checkpoints, with finite timeouts in integration tests.

In section 8's demo, `get(5, TimeUnit.SECONDS)` gives the test clear await points and fails if the environment stalls. For high-load concurrency tests, use controlled latches/queues instead of relying on worker print order.

### 20.3. Verifying Missing Accessor Failures Separately

If no accessor is registered for `TENANT` while the decorator is attached to the executor, the worker may not see the tenant. That does not prove the Spring decorator is broken; it shows the registry lacks a bridge to that value. Tests must distinguish **missing dependency**, **missing accessor**, and **wrong executor selected**, as the fixes differ.

## 21. Practical Implementation Checklist

When a PR adds `ContextPropagatingTaskDecorator`, ask in order:

1. **Versions:** Does Spring Framework have the 6.1+ API, and is the Micrometer Context Propagation dependency present at **runtime** and compatible?
2. **Registry:** Does the data to propagate have an accessor? Is the accessor registered in the registry actually used by the decorator/factory?
3. **Timing:** Is context set on the sending thread **before** the executor accepts the task?
4. **Execution path:** Do tasks or `@Async` calls pass through the exact `TaskExecutor` with the decorator attached?
5. **Scope:** Is context restored/reset after every task, including when exceptions are thrown?
6. **Security:** Are unauthorized tokens, principals, or request objects avoided; is propagation never used in place of authorization?
7. **Transactions:** Are caller-thread transactions/resources never copied?
8. **Reactive boundaries:** Are there Reactor pipelines or CompletableFutures switching to other executors that need extra strategy?
9. **Performance:** Has context snapshot overhead and p95/p99 impact been measured for short tasks or high submission rates?
10. **Lifecycle:** Are global registries/accessors registered consistently once rather than per request; do executors have worker/queue bounds?
11. **Observability:** Were actual logs/traces verified rather than assumed from adding a jar?
12. **Testing:** Were worker reuse, failing tasks, absent context, and multiple tenants tested?
13. **Promise boundaries:** Is it clear the decorator does not guarantee execution, retries, trace export, rollback, or cross-system delivery?

## 22. Practice Exercises and Suggested Answers

### Exercise 1 — Distinguishing Two Dependencies

An application uses Spring Framework 6.2.x but lacks `io.micrometer:context-propagation`. A developer adds `new ContextPropagatingTaskDecorator()`. What can happen?

**Hint:** Micrometer classes are missing at runtime, potentially causing `NoClassDefFoundError` or initialization failures. Add a compatible dependency and check runtime scope/classpath.

### Exercise 2 — Missing Accessor

An application attached the decorator to `ThreadPoolTaskExecutor`, yet a custom `ThreadLocal<String> TENANT` remains null on the worker. What three things should be checked?

**Hint:** (1) Does the registry have a `ThreadLocalAccessor` for TENANT, (2) does the decorator use the right registry/factory, and (3) did the caller set TENANT before submit and route the task through that executor?

### Exercise 3 — Point-in-Time Snapshot

Caller sets `requestId=R1` and calls `execute(task)`; immediately afterward changes it to `R2` before the worker starts. Which value must the task see when context is captured properly?

**Hint:** R1 — the snapshot captured at schedule time, not the caller's newer value.

### Exercise 4 — Checking for Context Leaks

A pool has only one worker. Task A belongs to tenant X; task B belongs to tenant Y; task C has no tenant. What sequence of values should appear on the worker if propagation and cleanup are clean?

**Hint:** X, Y, then null. If C sees X or Y, investigate cleanup, accessor reset, and thread baseline.

### Exercise 5 — Internal @Async Call

Method `start()` in the same bean calls `this.reportAsync()`, even though `reportAsync()` is annotated with `@Async("contextExecutor")`. Why does the decorator not take effect as expected?

**Hint:** Self-invocation bypasses the Spring proxy in default mode. Move to another bean so the call is intercepted.

### Exercise 6 — Continuation Outside the Executor

An `@Async("contextExecutor")` method returns CompletableFuture; the caller uses `thenApplyAsync(...)` without passing an executor. Is the continuation guaranteed to receive context from the first method?

**Hint:** No. The continuation may run on the common pool; specify the executor and capture context at schedule time or use a dedicated propagation mechanism.

### Exercise 7 — Security and Transactions

A task needs to read tenant data and write to a database. Should you pass the raw JDBC Connection and SecurityContext to the worker through a custom ThreadLocalAccessor?

**Hint:** Do not arbitrarily copy thread-bound resources/transactions or sensitive security objects; use proper abstractions and authorization/transaction boundaries on the worker.

### Exercise 8 — Running the Maven Demo

Run the `ContextPropagationDemo` project and confirm the five output lines. Then remove `registerThreadLocalAccessor(...)` and explain why the decorated pool still lacks the custom tenant.

**Hint:** Without an accessor, the snapshot cannot read/set TENANT. The decorator is the task-wrapping infrastructure; the registry defines which contexts are supported.

## 23. Summary

- **`ContextPropagatingTaskDecorator` (Spring 6.1+)** supports capturing and restoring context at the `Runnable` execution boundary of a compatible executor.
- **Essential integration requirements:** `io.micrometer:context-propagation` must exist on the runtime classpath and have a matching `ThreadLocalAccessor`/`ContextAccessor` for the data to propagate.
- **There is no magic copying all ThreadLocals.** Custom request IDs/tenants need a proper accessor registered in the registry used by the snapshot factory.
- **Attach the decorator to the right executor**, such as `ThreadPoolTaskExecutor.setTaskDecorator(...)`; with `@Async`, `@EnableAsync` and proxy invocation are also needed.
- **Snapshots reflect context at submission time**; the worker temporarily sets context inside the scope and restores after the task runs, preventing cross-request data mixing.
- **Do not conflate logging, Observation, tracing, security, and transactions.** Each mechanism needs its own integration, permissions, and verification.
- **Do not ignore overhead, scope, or Future errors.** The decorator does not spawn workers, does not catch all exceptions, does not guarantee durable jobs, and does not propagate context across every pipeline automatically.
- **Testing with/without decorator, changing values, clearing, errors, worker reuse, and the right executor** provides more trustworthy operational evidence than merely adding a dependency.

### Official Documentation

- [Spring Framework API — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework API — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework Reference — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [Micrometer Context Propagation — Examples](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Micrometer Context Propagation — Installing](https://docs.micrometer.io/context-propagation/reference/installing.html)
- [Micrometer ContextRegistry API](https://javadoc.io/doc/io.micrometer/context-propagation/1.1.3/io/micrometer/context/ContextRegistry.html)
- [Spring Boot Reference — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
