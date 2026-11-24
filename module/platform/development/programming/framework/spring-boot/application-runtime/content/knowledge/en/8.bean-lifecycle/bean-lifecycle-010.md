# Destruction Limits for Prototype Beans and Objects Created Outside the Container

## 1. Why can a Spring-created bean still not be auto-destroyed by Spring?

Spring manages bean lifecycles according to **scope** and whether the object falls under container management. Two questions must be separated:

1. **Does Spring instantiate and initialize this object?** That governs dependency injection, bean post-processors, `@PostConstruct`, and initialization steps.
2. **Who is responsible for ending its lifecycle and releasing resources?** That depends on scope, allocation method, ownership, and cleanup mechanisms.

For regular `singleton` beans, the Spring container holds the instance, tracks it, and invokes appropriate destruction callbacks when the context closes normally. For `prototype` beans, Spring generally **creates, configures, initializes, and hands the instance to the requester**; after that point the container **does not fully track** each prototype to destroy it automatically when the context closes.

Similarly, an object instantiated by the application calling `new` outside the container is normally **not a bean**. Spring has no automatic knowledge that the object holds file handles, sockets, thread pools, or streams needing closure.

Here is the central rule of this lesson:

> **Being initialized by Spring does not mean being auto-destroyed by Spring. Having a destruction annotation does not guarantee the callback will be called.**

This lesson applies to Spring Framework 6.1.x and Spring Boot 3.3.x on Java 17+. The goal is to understand resource-management limits, choose the right cleanup mechanism, and verify behavior with a runnable program.

## 2. Two distinct phases: initialization and destruction

A bean's overall lifecycle can be visualized as follows:

```text
Bean definition / request to get bean
    |
    v
Create instance (constructor or factory method)
    |
    v
Inject dependencies, apply BeanPostProcessors
    |
    v
Initialization callbacks
    |  @PostConstruct, InitializingBean, appropriate initMethod
    v
Bean handed to caller / ready for use
    |
    +----------------------+--------------------------+
    |                      |                          |
    v                      v                          v
singleton              prototype                 new outside Spring
Spring tracks          caller receives           caller holds instance
instance lifecycle     and owns cleanup          and owns cleanup
    |                      |                          |
    v                      v                          v
Context closes         Caller proactively        Caller proactively
normally               closes/destroys           closes/shuts down
    |                      |                          |
    v                      v                          v
Destruction callbacks  No auto destroy           No Spring callbacks
for singleton          callbacks from Spring     by default
```

**Note:** `@PostConstruct` and `@PreDestroy` are two sides of the lifecycle **when Spring actually manages those steps**. For prototypes, initialization callbacks are processed during bean creation; however, declared destruction callbacks such as `@PreDestroy` or `DisposableBean.destroy()` **do not run automatically just because the context closes**.

“Destroy” in Spring primarily means invoking developer-defined cleanup callbacks. The JVM may reclaim memory via GC at an unspecified time, yet GC **is not a timely mechanism for releasing** file descriptors, network connections, executors, or locks that must be released per application contract.

## 3. Comparing Spring's resource-management boundaries

| How the object is obtained | Does Spring know bean definition/instance? | Initialization | Destruction on normal context close | Who must clean up? |
| --- | --- | --- | --- | --- |
| Default `singleton` `@Bean` | Yes; container holds instance | Yes | Usually has configured callbacks | Spring invokes callbacks; callbacks must release resources properly |
| Singleton `@Component` | Yes; container holds instance | Yes | Usually has eligible callbacks | Spring invokes callbacks; bean class must implement cleanup |
| `@Bean` or `@Component` with `@Scope("prototype")` | Has definition and handles each creation; does not retain all instances for centralized destruction | Yes | **Does not auto-call destructor per prototype** | Caller or component owning the prototype |
| `new SomeResource()` outside container | No, unless handed to another management mechanism | Only constructor/self-called logic | No | Code that created/took ownership |
| `@Bean` returning an object created with `new` | **Yes**, when factory method returns the object as a Spring bean | Processes bean lifecycle | Depends on scope and destroy method | Check ownership contract when registering the bean |
| Resource created in a field of a singleton, not registered separately | Spring manages **owner bean**, does not necessarily know child resource | Depends on owner code | Auto-cleaned only if owner implements cleanup | Owner bean via `@PreDestroy` or destroy method |
| Object borrowed from another library or shared pool | Not necessarily | Per owning library | Not guaranteed | True owner per contract; borrower must not close shared resource |

Do not say all non-singleton scopes share prototype destruction behavior. `request`, `session`, and custom scopes may manage destruction callbacks at the end of the scope's lifetime via their own mechanisms. **The prototype rule here is specific to the default prototype scope.**

## 4. What exactly does Spring do with a prototype bean?

Example definition:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class FileTask {
    @PostConstruct
    public void init() {
        // Called by Spring when this instance is initialized.
    }

    @PreDestroy
    public void cleanup() {
        // NOT called automatically by Spring on context close for prototypes.
    }
}
```

This is an **illustrative snippet**, requiring Spring/Jakarta imports and placement inside a valid Spring Boot project. Once the bean definition exists, each time a caller requests a matching prototype, Spring creates a new instance:

```java
FileTask a = context.getBean(FileTask.class);
FileTask b = context.getBean(FileTask.class);
System.out.println(a == b); // false for regular prototype beans
```

### 4.1. Which callbacks still run?

When Spring creates a prototype, appropriate steps still take place: constructor or factory method, dependency injection, bean post-processors, and initialization callbacks such as `@PostConstruct`. When the bean is handed to the caller, that instance has been created/initialized by Spring's machinery.

A prototype is not necessarily created during context refresh. Usually it is created **each time the bean is requested**; if injected into a singleton via constructor, it is created when that singleton is instantiated.

### 4.2. Which callbacks do not run automatically?

When closing `ApplicationContext`, Spring normally **does not invoke** destruction callbacks declared for each prototype:

- `@PreDestroy`;
- `DisposableBean.destroy()`;
- `@Bean(destroyMethod = "close")` or other configured destroy method on a prototype bean;
- `close`/`shutdown` inference for prototype `@Bean`s.

Those mechanisms can be executed **when you explicitly pass the instance into the appropriate destruction API**. However, **closing the context once does not equal destroying every prototype ever handed out**.

### 4.3. Why does Spring work this way?

Prototypes are often created repeatedly, may live independently, and are passed across many components. Spring does not keep references to every prototype instance to decide when each object finishes being used. If the container retained all of them, holding references to finished objects could increase memory usage.

Therefore, after handing over the instance, **the caller must know when work finishes**. For resources like streams, sessions, or handles, this is where you must establish who owns `close()`.

## 5. Runnable Java 17+ / Spring Boot 3.3 example

The experiment below is intentionally written with **simulated resources**: it opens no real sockets or files so we can precisely observe which callbacks run and which do not. One prototype is closed manually; a second prototype is intentionally left unclosed **solely to prove Spring does not clean it up automatically**. Do not omit closing real resources in production.

### 5.1. build.gradle and configuration

Gradle Groovy project, Java 17, Spring Boot 3.3.13:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Create `settings.gradle`:

```groovy
rootProject.name = 'lifecycle-ownership-lab'
```

Create `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

No web starter is needed because we are testing bean lifecycle, unrelated to an HTTP server. The example assumes the **Gradle Wrapper** generated for the project.

### 5.2. Complete source code

Create the exact file `src/main/java/com/example/lifecycle/LifecycleOwnershipApplication.java`:

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Scope;

@SpringBootApplication
public class LifecycleOwnershipApplication {

    private static final AtomicInteger NEXT_ID = new AtomicInteger();

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LifecycleOwnershipApplication.class, args)) {

            try (PrototypeHandle first =
                    context.getBean(PrototypeHandle.class)) {
                System.out.println("use prototype #" + first.id());
            }

            PrototypeHandle second = context.getBean(PrototypeHandle.class);
            System.out.println("leave prototype #" + second.id()
                    + " unclosed (demo only)");

            try (ExternalHandle external = new ExternalHandle()) {
                System.out.println("use external");
            }
        }
        // Context closed. Prototype #2 is not closed automatically by Spring.
    }

    @Bean(destroyMethod = "close")
    SingletonHandle singletonHandle() {
        return new SingletonHandle();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    PrototypeHandle prototypeHandle() {
        return new PrototypeHandle(NEXT_ID.incrementAndGet());
    }

    static final class SingletonHandle implements AutoCloseable {
        SingletonHandle() {
            System.out.println("singleton created");
        }

        @Override
        public void close() {
            System.out.println("singleton close");
        }
    }

    static final class PrototypeHandle implements AutoCloseable {
        private final int id;

        PrototypeHandle(int id) {
            this.id = id;
        }

        int id() {
            return id;
        }

        @PostConstruct
        public void init() {
            System.out.println("prototype init #" + id);
        }

        @PreDestroy
        public void annotatedDestroy() {
            System.out.println("prototype @PreDestroy #" + id);
        }

        @Override
        public void close() {
            System.out.println("prototype close #" + id);
        }
    }

    static final class ExternalHandle implements AutoCloseable {
        ExternalHandle() {
            System.out.println("external created");
        }

        @PreDestroy
        public void annotatedDestroy() {
            System.out.println("external @PreDestroy");
        }

        @Override
        public void close() {
            System.out.println("external close");
        }
    }
}
```

In the program:

1. `SingletonHandle` is registered via a default singleton `@Bean`, and Spring calls `close` per `destroyMethod` when the context closes.
2. `PrototypeHandle` is registered via `@Bean` with prototype scope. Two `getBean` calls create two instances. Spring invokes `@PostConstruct` for both.
3. Instance `first` is placed inside `try-with-resources`, so **Java code calls `AutoCloseable.close()`** upon leaving the block. This action **does not mean** Spring called `@PreDestroy`.
4. Instance `second` is retrieved without closing, purely for demonstration. When the context closes, Spring invokes neither `@PreDestroy` nor `close` on this prototype instance.
5. `ExternalHandle` is created directly with `new` and closed via `try-with-resources`. The `@PreDestroy` annotation on that class **does not make Spring take over management of the object**.

### 5.3. How to run

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Lines **printed by the example code**, in exact order with the project as described:

```text
singleton created
prototype init #1
use prototype #1
prototype close #1
prototype init #2
leave prototype #2 unclosed (demo only)
external created
use external
external close
singleton close
```

Gradle may print other task/build lines. Properties disable the banner and startup INFO logging for cleaner output.

**Three notable lines that do not appear:**

```text
prototype @PreDestroy #1
prototype @PreDestroy #2
external @PreDestroy
```

These are **lines that are not printed**, shown for comparison; they are **not** part of expected stdout. Spring does not automatically destroy prototypes on context close and does not manage instances created with `new`. `first.close()` is a Java call invoked directly by `try-with-resources`; it does not trigger Spring's destruction callback chain.

### 5.4. Modifying the experiment

- Change `@Scope(PROTOTYPE)` to singleton: two `getBean` calls generally return the same instance, and its `@PreDestroy` can be called by Spring at context close. **Do not keep the `try-with-resources` block closing a singleton mid-program** as a production pattern, as that violates the container's ownership boundary.
- Remove `try-with-resources` from `first`: `prototype close #1` disappears; closing the context still does not rescue the missing cleanup.
- Remove `@PreDestroy` from the prototype: output is unchanged, since Spring was never going to invoke that callback on context close anyway.
- Turn `ExternalHandle` into a Spring-registered singleton bean with an appropriate destroy method: lifecycle ownership changes then, even though the factory method may still call `new` internally.

## 6. Objects created with new: when are they still Spring beans?

The statement “objects created with `new` are not managed by Spring” must be understood around **registration boundaries**. How a constructor is called does not decide lifecycle on its own.

### 6.1. new in ordinary application code

```java
ClientSession session = new ClientSession();
session.doWork();
```

This is an **illustrative snippet**, with `ClientSession` as a hypothetical application class. Unless `session` is registered with a container/scope appropriately, Spring knows nothing about that instance and will not call `@PostConstruct`, `@PreDestroy`, or `close()` on it. The creator or recipient of ownership must close it per the class contract.

Adding `@Component` to the **class definition** also does not turn manually `new`-created instances into Spring beans. The container manages only instances it is configured to create/manage.

### 6.2. new inside @Bean

```java
@Configuration
class ClientConfig {
    @Bean(destroyMethod = "close")
    ClientSession clientSession() {
        return new ClientSession();
    }
}
```

This is an **illustrative configuration snippet**, requiring a `ClientSession` class with a `close()` method and appropriate imports.

**The outcome is completely different:** the instance returned by a `@Bean` method is registered as a bean. With the default singleton scope, Spring tracks that bean's lifecycle and can invoke `close()` when the context closes.

If the `@Bean` method has `@Scope("prototype")`, Spring creates a bean on demand yet **does not automatically run destruction callbacks for each instance at context close**. Hence **“created by `@Bean`” is not enough** to conclude auto-cleanup applies; you must check scope.

### 6.3. Resource created *inside* a bean without being a bean itself

Example of a singleton owning an executor:

```java
@Component
class TaskOwner {
    private final ExecutorService executor =
            Executors.newFixedThreadPool(2);

    @PreDestroy
    void stop() {
        executor.shutdown();
    }
}
```

This is an **illustrative code snippet**, requiring imports for `java.util.concurrent.ExecutorService`, `Executors`, `org.springframework.stereotype.Component`, and `jakarta.annotation.PreDestroy`.

In this case, Spring manages the `TaskOwner` bean and calls `stop()` during normal singleton destruction. It **does not automatically treat `executor` as a bean** just because it lives in a bean field. Cleanup works because **the owner bean proactively calls `shutdown()`**. For long tasks, `shutdown()` only stops accepting new tasks; you may also need `awaitTermination(...)` with a timeout and a strategy for active tasks.

Similar resources include `InputStream`, `Socket`, `Connection`, message consumers, file watchers, thread pools, and native handles. Know the proper closing mechanism for each API.

## 7. Choosing a single owner for resource cleanup

In design, identify three facts together:

1. **Who creates or borrows the resource?** A bean factory, service, request handler method, external library, or external container?
2. **Who has the right to close it?** The true owner, not necessarily whoever currently holds a reference to the resource.
3. **When should it be closed?** At the end of a request/job, end of a scope, when a singleton closes, or at application shutdown.

Example choices:

| Resource | Desired lifetime | Recommended ownership |
| --- | --- | --- |
| Stream for a single file read | One short read block | Method opening the stream uses `try-with-resources` |
| Prototype processing a unit of work | One business job/request | Caller fetches prototype and calls `close` in `finally`/`try-with-resources` |
| Per-transaction connection | One transaction | Use transaction/connection pool mechanics; return connection per contract, do not close shared pool |
| Shared HTTP client or connection pool | Entire application lifetime | Singleton/owner bean manages and closes once on shutdown |
| Thread pool owned by a bean | Owner's lifetime | Owner calls `shutdown`, awaits tasks per policy |
| Client borrowed from an external library/host | Host's lifetime | Borrower must not close shared resource unless contract transfers ownership |
| Prototype held in a singleton field | Can extend to singleton lifetime | Singleton/owner must design cleanup for held instance; do not rely on automatic prototype destruction |

From this table, the easiest pattern to audit is **binding acquisition and release to the same code scope**. Example:

```java
try (ResourceHandle handle = openResource()) {
    handle.execute();
}
```

This is **Java pseudocode** with hypothetical class/method names. Even if an exception occurs inside the block, `try-with-resources` still calls `close()`. The resource must implement `AutoCloseable` or `Closeable`. Calling `@PreDestroy` manually or relying on GC cannot replace a resource's `close` contract.

### 7.1. Need a fresh prototype per operation: use ObjectProvider

A singleton directly injecting a prototype via constructor:

```java
@Service
class ReportService {
    private final ReportSession session;

    ReportService(ReportSession session) {
        this.session = session;
    }
}
```

If `ReportSession` is a prototype, the instance is resolved **when the `ReportService` singleton is created**, not refreshed on every method call. The singleton may retain the prototype for too long and easily forget to clean it up at the right time.

To get a prototype instance for **each operation**, inject `ObjectProvider<ReportSession>`:

```java
@Service
class ReportService {
    private final ObjectProvider<ReportSession> sessions;

    ReportService(ObjectProvider<ReportSession> sessions) {
        this.sessions = sessions;
    }

    void runReport() {
        try (ReportSession session = sessions.getObject()) {
            session.generate();
        }
    }
}
```

Both snippets above are **structural illustrations**, not standalone files: `ReportSession` must be declared as a prototype bean implementing `AutoCloseable`, define `generate()`, and import `ObjectProvider` and `@Service`. `ObjectProvider` **retrieves a fresh instance at the right time**, yet it **does not automatically clean up the instance** after returning it. Cleanup responsibility here belongs to the caller's `try-with-resources`.

If a prototype object only holds transient data without closable resources, you do not need to force it to implement `AutoCloseable`. Design cleanup proportional to the actual resource type rather than adding meaningless close operations.

## 8. @PreDestroy, DisposableBean, AutoCloseable, and @Bean destroyMethod

These mechanisms differ in **who triggers them** and **when they apply**.

| Mechanism | Who invokes when applicable? | Notes |
| --- | --- | --- |
| `@PreDestroy` | Spring destruction processing for eligible beans | Not automatically called for prototypes merely on context close |
| `DisposableBean.destroy()` | Spring when destroying a bean per lifecycle | Couples source code to Spring API |
| `@Bean(destroyMethod = "cleanup")` | Spring when destroying a `@Bean`-defined bean with matching callback | Only runs when lifecycle destruction actually executes |
| `@Bean(destroyMethod = "close")` | Spring invokes `close` when destroying the bean | Explicit for singleton beans owning resources |
| Default `@Bean`, object has public `close()` or `shutdown()` | Spring may infer the destruction method | Default inference mechanism; does not mean instances outside the container are closed |
| `AutoCloseable.close()` | Java `try-with-resources` or direct callers; Spring may use via bean config | Interface alone does not create an automatic destruction schedule for prototypes |
| `finally { resource.close(); }` | Application code | Suitable when managing lifecycle within a local scope |

### 8.1. @Bean auto-inferring close/shutdown: what to avoid

In Java configuration in Spring Framework 6.1, `@Bean` defaults to an **inferred** destroy method. The container can detect a public no-argument `close()` or `shutdown()` method on the actual bean and call it when destroying a container-managed bean.

```java
@Bean
ExternalClient client() {
    return new ExternalClient(); // assumed to have public close()
}
```

For a container-owned singleton bean, Spring can automatically invoke `close()` at context close even without `destroyMethod="close"`. That is helpful for application-owned clients/pools, yet it can become an **ownership bug** if the client is actually a shared resource **borrowed** from another system.

To **disable close/shutdown inference** specifically for a `@Bean`-created bean:

```java
@Bean(destroyMethod = "")
ExternalClient borrowedClient() {
    return externallyManagedClient;
}
```

This is an illustrative snippet; `externallyManagedClient` is an externally supplied variable/object. **Be careful:** `destroyMethod=""` only disables custom destroy-method inference; it does not necessarily suppress all destruction callbacks—for instance, `DisposableBean` or `@PreDestroy` may still be processed. If an object belongs to another owner, review the contract and avoid accidentally registering callbacks that close shared resources.

### 8.2. Do not “invoke annotations” manually

`@PreDestroy` is only metadata. When you directly call `resource.close()`, Java does not automatically execute a method annotated with `@PreDestroy` if they are two different methods. Conversely, Spring calling `@PreDestroy` does not mean it automatically closes all child resources: the callback method itself must close the resource or the bean must have an appropriate destroy callback.

Avoid creating two uncontrolled cleanup paths closing the same resource. Design idempotently when needed, and pick one clear ownership path.

## 9. When you need Spring to help destroy a specific prototype

Spring Framework provides an on-demand destruction API, such as `ConfigurableBeanFactory.destroyBean(String beanName, Object beanInstance)`, to apply bean-definition destruction rules to an instance, typically a prototype. This is an **explicit caller action**, distinct from the container automatically cleaning up all prototypes at shutdown.

Conceptual example:

```java
ConfigurableBeanFactory factory = context.getBeanFactory();
MyPrototype instance = context.getBean(MyPrototype.class);

try {
    instance.doWork();
} finally {
    factory.destroyBean("myPrototype", instance);
}
```

This is an **illustrative snippet**, not a standalone file: `context` must be a `ConfigurableApplicationContext`, `MyPrototype` must be registered under the corresponding bean name, and imports must be present. The `destroyBean` API can trigger applicable Spring callbacks on the instance, including callbacks different from a direct `close()` call. Understand the method/scope and use **only one ownership mechanism** to avoid double cleanup. For simple applications, having the resource implement `AutoCloseable` and callers use `try-with-resources` is usually easier to maintain.

Some specialized applications write a custom scope or bean post-processor to track prototypes needing destruction. Keeping every prototype in a global list to close at shutdown requires evaluating **memory retention from held references, thread synchronization, when resources actually expire, and risk of double-close**.

Do not solve the problem by naively converting all prototypes to singletons: shared singletons can break state isolation, thread safety, and data separation.

## 10. Normal shutdown vs. abrupt shutdown

Even for singletons, “Spring closes it automatically” is conditional: the application must get the chance to run its shutdown lifecycle.

| Scenario | Reliability of Spring cleanup |
| --- | --- |
| Closing context via `ConfigurableApplicationContext.close()` | Spring runs shutdown/destruction for eligible beans |
| `try (ConfigurableApplicationContext ctx = ...)` | Calls `close()` on block exit, even on normal exceptions |
| SIGTERM with shutdown hook working normally | Gets a chance to run graceful shutdown and bean destruction per config |
| `kill -9` / SIGKILL or hard crash | **No** chance to guarantee Java/Spring callbacks run |
| Power loss, forced process kill, severe OOM/resource exhaustion | Cannot guarantee callbacks complete |
| Prototype object without caller cleanup | Context shutdown **does not fix** missing cleanup |

Therefore, external resources must be designed for crash tolerance: database transaction/lease timeouts, idempotency, retries, broker redelivery, or connection timeouts. Shutdown callbacks are useful for normal termination; they are not the sole mechanism ensuring data correctness.

**JVM exit and GC:** the operating system reclaims many process-level resources when a process actually exits, yet that does not substitute for timely release in a running process and does not guarantee protocol/application-level cleanup. Java GC also makes no promise to invoke `close` or `@PreDestroy` on time.

## 11. Common mistakes

| Symptom or statement | What is wrong? | How to handle |
| --- | --- | --- |
| “Prototype bean has `@PreDestroy`, so Spring will call it on app stop” | Prototypes are not tracked by the container for centralized destruction | Caller manages cleanup or calls explicit destroy API |
| “Having `@PostConstruct` means `@PreDestroy` will run too” | Init and destroy are two phases with different contracts | Check scope and ownership |
| “Implementing `AutoCloseable` means closing context closes every instance” | Interface does not create ownership or tracking for all prototypes | Use `try-with-resources` or appropriate owner |
| “Every `new` object inside a bean is managed separately by Spring” | Only the owner bean is registered; child fields/resources are not automatically beans | Close resources in the owner's lifecycle callback |
| “`new` inside `@Bean` is definitely outside Spring” | Instance returned from `@Bean` can be a managed bean | Check scope, bean definition, and destroy method |
| “`@Bean(destroyMethod="")` disables all cleanup” | Only disables destroy-method inference/that custom method; other callbacks can still run | Check `@PreDestroy`, `DisposableBean`, and ownership |
| “Prototype injected into singleton always creates a new instance per call” | Dependency is usually resolved once when building the singleton | Use `ObjectProvider` when a new instance per task is needed |
| “With Spring context you don't need to close InputStream” | Per-task streams do not automatically belong to context lifecycle | Use `try-with-resources` at the owning site |
| “Closing resource right after getBean is always safe” | Resource might be borrowed/shared with other callers | Identify the owner; avoid closing shared resources prematurely |
| “Closing prototype guarantees `@PreDestroy` ran” | Java `close()` differs from Spring callbacks | Pick a specific mechanism and verify logs |
| “Spring guarantees cleanup after SIGKILL” | Process had no opportunity to run hooks | Design timeouts and crash recovery |
| “Just keep all prototypes in a list to close on JVM exit” | Can retain references too long and clean up at the wrong time | Match lifetime to task scope |

### 11.1. Resource-leak investigation checklist

1. Determine whether the object **is actually a bean** or just instantiated with `new`.
2. Check its **scope** and `getBean` call sites; for prototypes, trace callers receiving instances.
3. Check what the object owns: files/sockets, threads, sessions, pools, or plain data only.
4. Locate corresponding release calls like `close`, `shutdown`, `dispose`, and verify they run on both success and exception paths.
5. If Spring should destroy a singleton, confirm normal shutdown lifecycle and valid annotations/`destroyMethod`.
6. If the bean is returned from `@Bean`, check destroy-method inference and avoid accidentally closing borrowed objects.
7. For prototypes inside singletons, check whether `ObjectProvider`/lookup and per-instance cleanup are needed.
8. When investigating with logs, log **resource IDs and acquired/released timestamps**; never print secrets, connection strings with credentials, or sensitive data.

## 12. Self-check

**Question 1.** A prototype bean has `@PostConstruct` and `@PreDestroy`. When the context closes, which callback is guaranteed not to be invoked automatically by the container under prototype rules?

**Answer:** The `@PreDestroy` destruction callback is not called automatically per prototype at context close. `@PostConstruct` already ran when each instance was initialized by Spring.

**Question 2.** How many instances do two `context.getBean(MyPrototype.class)` calls normally return?

**Answer:** Two instances for a regular prototype bean. Each instance must be managed for its actual usage duration if it holds resources.

**Question 3.** Does `try (MyPrototype p = provider.getObject())` automatically trigger `@PreDestroy`?

**Answer:** No. Java invokes `AutoCloseable.close()` on `p`; `@PreDestroy` is a separate callback handled by Spring when destruction processing runs.

**Question 4.** Why can an object instantiated with `new` inside a `@Bean` method be closed by Spring?

**Answer:** Because the instance is **returned and registered as a bean**. With singleton scope and an eligible destroy method, Spring has authority to run lifecycle callbacks. Calling `new` in the constructor is not the only boundary.

**Question 5.** A singleton creates an `ExecutorService` in a field. Does Spring automatically call `shutdown()` on that field?

**Answer:** No, unless the executor is registered/managed separately or the owner bean proactively calls `shutdown()` in its own destruction callback.

**Question 6.** What does `@Bean(destroyMethod="")` do, and what does it not do?

**Answer:** It disables `close/shutdown` destroy-method inference for that `@Bean`; it does not guarantee disabling `@PreDestroy` or `DisposableBean`.

**Question 7.** Why does injecting a prototype into a singleton not mean every request gets a new instance?

**Answer:** Dependencies are resolved when the singleton is created; the singleton can hold onto that same prototype. To get one instance per task, use a provider/lookup and per-task cleanup.

**Question 8.** When the JVM receives SIGKILL, can you rely on `@PreDestroy` to send an end-of-transaction message?

**Answer:** No. You must design consistency/timeout/recovery mechanisms for abrupt failures; callbacks are only part of normal shutdown.

## 13. Key takeaways and references

- **Container-owned singletons:** Spring can execute destruction callbacks when the context closes normally.
- **Prototypes:** Spring performs initialization, hands over the instance, and **does not automatically invoke destruction callbacks per instance** when the context closes. Callers must handle cleanup if resources need releasing.
- **Objects outside the container:** `new` outside bean registration carries no Spring lifecycle; `@PreDestroy` on the class has no automatic effect.
- **`@Bean` and ownership:** an object created with `new` yet returned from `@Bean` can still be managed by Spring; check scope and destroy method.
- **`AutoCloseable` vs. `@PreDestroy`:** `try-with-resources` calls `close`; Spring destruction processing triggers the corresponding Spring callbacks.
- **Resource lifetime follows the owner:** acquisition and cleanup should be paired within a sound lifecycle, rather than relying arbitrarily on GC or JVM shutdown.

Official documentation:

- [Spring Framework — Bean Scopes: Prototype Scope](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html) — confirms prototype init while the container does not automatically invoke destruction callbacks.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html) — `@Bean(destroyMethod=...)` and `close/shutdown` inference.
- [Spring Framework 6.1 — Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html) — contract for destroy-method inference and `destroyMethod=""`.
- [Spring Framework 6.1 — ConfigurableBeanFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html) — `destroyBean(beanName, instance)` when explicit destruction is needed.

To diagnose accurately, always ask: **Is Spring managing a bean definition, an instance, a scope, or just an object referenced by another bean?** And even more importantly: **Who is the owner responsible for releasing the resource and when?**
