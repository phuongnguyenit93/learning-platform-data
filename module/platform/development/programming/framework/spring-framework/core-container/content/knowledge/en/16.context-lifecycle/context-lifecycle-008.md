# Refresh Failure and Cleaning Up Created Resources in Spring ApplicationContext

## 1. Why is this an important part of the context lifecycle?

When starting an `ApplicationContext`, Spring must load bean definitions, run extension points, create non-lazy singletons, and complete lifecycle callbacks. If a step fails, the application cannot treat the context as ready. However, **a portion of objects may already have been created and some resources may already have been opened** before the error occurred.

Example:

1. Spring has created a singleton pool; the pool opens connections and background threads.
2. Spring creates a service depending on the pool.
3. Inside the service's `@PostConstruct`, invalid configuration causes an exception.
4. This `refresh()` fails; the initialized Spring-managed beans/resources must be cleaned up.
5. The caller must still close or revert resources that Spring had not yet managed or that were created outside the container.

Key learning points:

- `refresh()` has a mechanism to **destroy already-registered singletons** in the failure branch.
- The container marks the context **inactive** when refresh is cancelled.
- Objects that **have not finished initialization**, prototypes, externally self-created resources, and off-system side effects **are not automatically rolled back completely**.
- Ownership and cleanup logic must be placed in the right spots, especially when an init method or `@Bean` factory method can throw.

This lesson examines API/behavior of **Spring Framework 6.2.x**, focusing on the Spring Core Container. Spring Boot may add failure handling when running an application, closing contexts, or publishing its own application events; do not use Boot events to infer every path of `AbstractApplicationContext.refresh()`.

## 2. Basic contract of refresh()

`ConfigurableApplicationContext.refresh()` loads or refreshes configuration state and initializes the container. The Javadoc emphasizes: if startup fails, it **should destroy already-created singletons** to avoid holding unused resources. This is the container's lifecycle intent, **not a guarantee to destroy every Java resource ever created anywhere**.

Normal flow, simplified:

```text
prepareRefresh()
   |
obtainFreshBeanFactory()
   |
prepareBeanFactory()
   |
invokeBeanFactoryPostProcessors()
   |
registerBeanPostProcessors()
   |
initMessageSource(), initApplicationEventMulticaster()
   |
onRefresh(), registerListeners()
   |
finishBeanFactoryInitialization()
   |   +--> preInstantiateSingletons()
   |   +--> create bean, inject dependencies, init callbacks
   |
finishRefresh()
   |   +--> lifecycle handling
   +--> ContextRefreshedEvent
```

A non-lazy singleton can open sockets, start pools, load files, or spawn threads in its constructor, factory method, or init callback. If another bean subsequently fails to initialize, Spring enters the error-handling branch instead of publishing refresh completion.

**Key milestone:** `ContextRefreshedEvent` is solely a sign that refresh reached the event-publishing step; if failure occurs earlier, listeners do not receive that event from the failing refresh. If a listener itself throws an exception during synchronous event publishing, consider that earlier listeners already received the event; do not infer nobody was notified when a listener fails at the final step.

## 3. How does Spring 6.2 handle errors inside refresh()?

In Spring Framework 6.2.18, `AbstractApplicationContext.refresh()` has a `try/catch` block wrapping most processing steps after `prepareBeanFactory()`. The core error-handling branch is equivalent to the **condensed pseudocode**:

```java
try {
    postProcessBeanFactory(beanFactory);
    invokeBeanFactoryPostProcessors(beanFactory);
    registerBeanPostProcessors(beanFactory);
    initMessageSource();
    initApplicationEventMulticaster();
    onRefresh();
    registerListeners();
    finishBeanFactoryInitialization(beanFactory);
    finishRefresh();
} catch (RuntimeException | Error ex) {
    // Spring logs a warning cancelling the in-progress refresh.
    destroyBeans();
    cancelRefresh(ex);
    throw ex;
}
```

This is not a standalone runnable source file, and omits tracking/locks and other preparation methods. See the [Spring v6.2.18 tagged source](https://github.com/spring-projects/spring-framework/blob/v6.2.18/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java) when cross-referencing.

Meaning of the actions:

- **Log/throw exception:** the initialization cause is propagated to the caller; startup failure is not masked as success.
- **`destroyBeans()`:** in the default implementation, delegates to `getBeanFactory().destroySingletons()` to destroy **singletons currently managed by the container**.
- **`cancelRefresh(ex)`:** switches `active` state back to `false` and clears some Spring metadata caches.
- **Stop proceeding:** normal steps after the failure location are not run.

### Do not claim every error in every phase hits the exact same catch

Pay attention to where the handler block sits in source by version. In Spring 6.2.18, calls to `prepareRefresh()`, `obtainFreshBeanFactory()`, and `prepareBeanFactory()` execute **before the catch block above**. An exception from very early phases can take a different path or depend on how a subclass loads its BeanFactory. Therefore, saying "every failure anywhere in refresh definitely runs full destroyBeans/cancelRefresh" is overly broad.

This point is especially important for custom `ApplicationContext`s and loading configuration from files/URLs. If custom resource creation happens **before the BeanFactory owns the corresponding singletons**, manage cleanup right inside that preparation step.

### Distinguishing Spring versions

Newer versions may add extra handling steps before `destroyBeans()` (such as coordinating already-started lifecycle components). Do not extrapolate source on GitHub's `main` branch as true for every released Spring 6.2 version. In this lesson, the example verifies the Spring 6.2.18 branch and invariants published by the API.

## 4. What does destroyBeans actually manage?

`destroyBeans()` in `AbstractApplicationContext` defaults to:

```java
protected void destroyBeans() {
    getBeanFactory().destroySingletons();
}
```

This is a very short API excerpt illustrating delegation. `destroySingletons()` processes the singleton registry, registered destruction callbacks, and dependency relationships. **It does not scan the heap**, does not hunt down every object ever `new`ed, and does not automatically roll back external actions such as HTTP requests, sending emails, database writes, or file creation.

### 4.1. Singletons successfully created and registered

A fully initialized singleton that has been taken under factory management and has appropriate destruction metadata may have invoked:

- `@PreDestroy` method.
- `DisposableBean.destroy()`.
- Custom `destroyMethod`, including inferred methods per `@Bean` config such as `close()`/`shutdown()`.
- Callbacks from `DestructionAwareBeanPostProcessor` or related supporting extension points.

With multiple callbacks on the **same bean**, Spring follows a lifecycle order; across **different beans**, dependency relationships affect teardown order.

A class having a `close` method is only invoked when its bean definition has an appropriate destruction mechanism and the container genuinely owns destruction of that instance. `AutoCloseable` is a signal that a close API exists, not proof that every scope is tracked by Spring.

### 4.2. Bean failing during initialization

Suppose a bean's constructor finishes, yet `@PostConstruct` or `initMethod` throws an exception. The instance may **not yet have reached the destruction callback registration step** and is not yet registered as a complete singleton.

In Spring 6.2.18's `AbstractAutowireCapableBeanFactory.doCreateBean()` flow, Spring calls `populateBean`/`initializeBean` first, and only afterward `registerDisposableBeanIfNecessary`. If initialization throws, execution exits before the normal destruction registration step for that bean.

Practical consequence: **do not rely on `@PreDestroy` of the failing bean itself** to close resources its constructor/init method opened before throwing. When init itself is a potential failure point, clean up local resources directly in `catch/finally`.

### 4.3. Prototype beans

Spring creates and initializes prototypes when requested by callers, yet does not track full destruction lifecycle after returning them. A successfully initialized prototype holding a socket/file is not automatically closed just because context refresh subsequently fails.

### 4.4. Objects created outside BeanFactory

`new Client()` in a static initializer, a startup hook outside the container, a thread spawned inside a factory method before the bean is returned, a temporary file created and losing reference, or objects owned by other libraries can all sit outside the singleton registry.

Do not label them "Spring-managed" merely because the object-creating code executes inside a `@Bean` method. The crucial condition is whether the object has **been accepted by the factory as an instance with managed lifecycle**.

## 5. Complete Java 17+ example: refresh fails, singletons cleaned up

The example uses Spring Framework 6.2.18 via Gradle, without Spring Boot. We intentionally build a dependency chain:

```text
BrokenService
    |
    v
   Pool
    |
    v
 Connection
```

`Connection` and `Pool` are successfully created singletons. `BrokenService` is constructed, yet its init method intentionally throws. Expected result: Spring cleans up `Pool` and `Connection` when cancelling refresh. We also observe that the destruction callback of `BrokenService` itself—which failed before finishing initialization—is not a mechanism to rely on.

Project structure:

```text
refresh-failure-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/RefreshFailureDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'refresh-failure-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'RefreshFailureDemo'
}
```

### src/main/java/RefreshFailureDemo.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;

public class RefreshFailureDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    public static final class Connection implements AutoCloseable {
        public Connection() {
            EVENTS.add("connection.created");
        }

        @Override
        public void close() {
            EVENTS.add("connection.closed");
        }
    }

    public static final class Pool implements AutoCloseable {
        private final Connection connection;

        public Pool(Connection connection) {
            this.connection = connection;
            EVENTS.add("pool.created");
        }

        @Override
        public void close() {
            EVENTS.add("pool.closed");
        }
    }

    public static final class BrokenService {
        private final Pool pool;

        public BrokenService(Pool pool) {
            this.pool = pool;
            EVENTS.add("service.created");
        }

        public void initialize() {
            EVENTS.add("service.initialize");
            throw new IllegalStateException("simulated startup failure");
        }

        public void cleanup() {
            EVENTS.add("service.cleanup");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(destroyMethod = "close")
        public Connection connection() {
            return new Connection();
        }

        @Bean(destroyMethod = "close")
        public Pool pool(Connection connection) {
            return new Pool(connection);
        }

        @Bean(initMethod = "initialize", destroyMethod = "cleanup")
        public BrokenService brokenService(Pool pool) {
            return new BrokenService(pool);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        AtomicBoolean refreshedEventSeen = new AtomicBoolean(false);
        context.addApplicationListener(event -> {
            if (event instanceof ContextRefreshedEvent) {
                refreshedEventSeen.set(true);
            }
        });

        context.register(Config.class);
        boolean failed = false;
        try {
            context.refresh();
        } catch (BeansException ex) {
            failed = true;
        } finally {
            // Closing a context we created remains good practice.
            // In this case Spring already destroyed singletons
            // and marked context inactive when refresh failed.
            context.close();
        }

        EVENTS.forEach(System.out::println);
        System.out.println("refreshFailed=" + failed);
        System.out.println("contextActive=" + context.isActive());
        System.out.println("refreshedEventSeen=" + refreshedEventSeen.get());
        System.out.println("failedBeanCleanupCalled="
                + EVENTS.contains("service.cleanup"));
    }
}
```

Run from the directory containing `build.gradle`:

```bash
gradle run --quiet
# If Gradle Wrapper is already created in the project:
# ./gradlew run --quiet
```

Lines printed by program logic via `System.out`:

```text
connection.created
pool.created
service.created
service.initialize
pool.closed
connection.closed
refreshFailed=true
contextActive=false
refreshedEventSeen=false
failedBeanCleanupCalled=false
```

Spring may also emit a **WARN log on stderr or via a logging framework** notifying that refresh was cancelled. That log is not part of the `System.out` set above and the exact message may vary by version/log configuration.

### Why is this result reliable?

1. Bean `BrokenService` requires `Pool` in its factory method; `Pool` in turn requires `Connection`, creating real dependency relationships without relying on `@Bean` method order in the file.
2. Spring successfully created and registered `Connection` and `Pool` under the default singleton scope.
3. `BrokenService.initialize()` throws `IllegalStateException`. During bean creation, Spring reports an initialization failure (typically via `BeanCreationException`, a subtype of `BeansException`).
4. `AbstractApplicationContext.refresh()` in this failure path calls `destroyBeans()`; the container cleans up managed singletons. Because `Pool` depends on `Connection`, the two close callbacks execute in proper dependency teardown order.
5. `BrokenService` failed before completing destruction registration, so its `cleanup()` method does not run in the illustrated scenario.
6. `cancelRefresh()` causes `context.isActive()` to return `false`. `ContextRefreshedEvent` was not published because the error occurred during the singleton creation loop.
7. `context.close()` in `finally` keeps resource ownership consistent from caller code; do not treat this call as the sole reason singletons were cleaned up, since `refresh()`'s error branch already did so.

**Output scope guarantee:** this list applies to the bean structure and Spring 6.2.18 in the example. If changing processors, scopes, Spring version, or startup method, re-measure rather than assuming identical log order.

## 6. Dangerous case: init opens resources before throwing

In the previous example, `BrokenService.initialize()` only added an event and threw. If it opens a socket, spawns a thread, starts a remote session, or creates a temporary file, the destructor of **the bean whose initialization failed** is not guaranteed to be registered for Spring to call.

**Unsafe** code example:

```java
public void initialize() throws Exception {
    socket = new Socket(host, port);
    validateRemoteHandshake();  // May throw.
}

// Cannot rely on @PreDestroy to guarantee
// cleanup for the bean whose init itself failed.
@PreDestroy
public void shutdown() throws Exception {
    socket.close();
}
```

This is an illustrative snippet, not standalone; `host`, `port`, and `validateRemoteHandshake` belong to a hypothetical application. If validation throws an exception before initialization completes, the bean's `@PreDestroy` may never run.

### Solution A: manage local resources before committing state

```java
public void initialize() throws Exception {
    Socket candidate = new Socket(host, port);
    boolean success = false;
    try {
        validateRemoteHandshake(candidate);
        this.socket = candidate;
        success = true;
    } finally {
        if (!success) {
            candidate.close();
        }
    }
}
```

This is also an illustrative snippet; `validateRemoteHandshake(Socket)` must be implemented in the application. The idea is to transfer socket ownership from a local variable to the instance only after fallible steps finish. If there are multiple resources, design cleanup in reverse order when initialization fails.

### Solution B: extract the resource into its own managed bean

Instead of opening a socket inside an init method that can fail, create an independent resource bean with an explicit destroy callback and inject it into the service. When the service fails to init, the successfully created resource bean will be included by Spring in singleton destruction.

```java
@Bean(destroyMethod = "close")
ClientConnection clientConnection() {
    return ClientConnection.connect();
}

@Bean(initMethod = "verify")
BusinessService businessService(ClientConnection connection) {
    return new BusinessService(connection);
}
```

This is a configuration snippet, not a standalone runnable program. If `ClientConnection.connect()` itself **opens resources and then throws before returning an object**, the factory method must also clean up internally; Spring has not yet received a completed bean to destroy.

### Solution C: try-with-resources for operation-scoped resources

For short operations, there is no need to turn every `AutoCloseable` into a singleton. You can acquire the resource inside a business method and close it via `try-with-resources`, completely independent of context teardown.

```java
try (ClientSession session = clientFactory.openSession()) {
    session.performValidation();
    session.execute();
}
```

This is an illustrative snippet requiring `ClientSession implements AutoCloseable` and corresponding APIs. This makes the lifetime explicit even when exceptions occur.

## 7. Bean factory method throws before returning

Another classic trap is putting initialization code inside a `@Bean` method:

```java
@Bean(destroyMethod = "close")
ExternalClient client() {
    ExternalClient client = new ExternalClient();
    client.open();
    client.verifySettings(); // Throws after open().
    return client;
}
```

This is an illustrative anti-example, assuming `ExternalClient` has the invoked methods. `destroyMethod = "close"` **is not sufficient to guarantee** cleanup if `verifySettings()` throws before `return client`. The container may never receive a finished bean instance.

Fix by cleaning up directly inside the factory method:

```java
@Bean(destroyMethod = "close")
ExternalClient client() {
    ExternalClient candidate = new ExternalClient();
    try {
        candidate.open();
        candidate.verifySettings();
        return candidate;
    } catch (RuntimeException | Error ex) {
        try {
            candidate.close();
        } catch (Exception cleanupError) {
            ex.addSuppressed(cleanupError);
        }
        throw ex;
    }
}
```

This is an illustrative snippet; exception types chosen must match real APIs. If `open/verify` declare checked exceptions, expand handling accordingly, e.g., declaring `throws Exception` and cleaning up in the appropriate catch branch. The purpose of `addSuppressed`: keep the original exception as the startup failure reason while preserving secondary cleanup error info instead of masking the primary cause.

If `close()` can throw `Error` or severe errors, do not blindly write `catch(Throwable)` and swallow everything. In production, thoroughly test the error contracts of the SDKs you integrate.

## 8. Destruction callbacks: order and limits

Common destruction mechanisms in Spring:

- `@PreDestroy`: handled by the lifecycle annotation processor.
- `DisposableBean.destroy()`: Spring interface for managed beans.
- Custom `destroyMethod`: can be `close()`, `shutdown()`, or a custom method.
- `DestructionAwareBeanPostProcessor`: infrastructure hook when a bean is destroyed.
- `SmartLifecycle.stop()`: phase-based lifecycle orchestration for components requiring controlled start/stop.

For callbacks with **different method names** on the same managed bean, the usual rule is `@PreDestroy` before `DisposableBean.destroy()`, then custom destroy method.

Important: **how the container handles a failed refresh is not equivalent to a normal shutdown of an active context**. In Spring 6.2.18, code catching exceptions in `refresh()` runs `destroyBeans()` and `cancelRefresh()`. It does not go through the entire `doClose()` branch that publishes `ContextClosedEvent` and runs normal lifecycle stop coordination.

Therefore:

1. **Do not rely solely on `ContextClosedEvent`** to clean up resources needing destruction on refresh failure.
2. **Do not rely solely on `SmartLifecycle.stop()`** when failure occurs before lifecycle start or when a version does not invoke lifecycle shutdown like a normal `close()`.
3. Beans that genuinely registered destroy callbacks are still cleaned up by the container in the appropriate failure branch.
4. Code must manage side effects occurring in stages before bean registration finishes.

### Dependency destruction

If A depends on B and both are successfully created singletons, Spring attempts to destroy A **before** B so A gets a chance to stop using B before B closes. This is why the example where `Pool` depends on `Connection` receives `pool.closed` before `connection.closed`.

Do not infer that all unrelated beans will destroy in class declaration order or alphabetical order. Test meaningful events by dependency relationships rather than snapshotting entire framework logs.

## 9. Closing after failed refresh: getting ownership right

With an `AnnotationConfigApplicationContext` created using the empty constructor, callers typically do:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
try {
    context.register(AppConfig.class);
    context.refresh();
    // If refresh succeeds, use context.
} finally {
    context.close();
}
```

This is an illustrative snippet; assume `AppConfig` is a valid `@Configuration` class. Calling `close()` in `finally` is good resource management practice when **the caller owns the context**.

However, distinguish two situations:

- **Refresh succeeds, then close:** `doClose()` on an active context can publish `ContextClosedEvent`, run lifecycle stop, destroy singletons, close the BeanFactory, and mark the context inactive.
- **Refresh fails in the normal catch path:** `destroyBeans()` and `cancelRefresh()` have already run. When calling `close()` while `active=false`, do not expect the entire normal `doClose()` sequence or `ContextClosedEvent` publication. That is not a complete "successful shutdown."

**Do not try calling `getBean()` after a context has cancelled refresh** to use "surviving" singletons. Treat startup as failed; do not serve this context as a ready application. Some metadata query APIs may still respond depending on context class, yet that does not prove the bean graph is valid.

### Can a context be refreshed again?

There is no single universal answer across all `ApplicationContext` implementations:

- Some context types support multiple refresh cycles with a new or rebuilt BeanFactory.
- `GenericApplicationContext` and `AnnotationConfigApplicationContext` are backed by a single BeanFactory and **do not support multiple refreshes** in the usual way; after one initialization, calling it again can throw `IllegalStateException`.
- If startup fails, the safest option is **creating a new context** after fixing the root cause, rather than trying to reuse a failed object with ambiguous resource state.

This matters in integration tests: each failure test should isolate its ApplicationContext to avoid polluting the context cache or reusing a failed context across runs.

## 10. Context hierarchy and external-owned resources

Applications may have parent/child contexts. Each context manages its own BeanFactory/beans; a bean in a child can inject dependencies from the parent. If the child's refresh fails, do not assume Spring will destroy **every singleton of the parent**. The parent still has an independent owner and lifecycle.

Example of a system with a shared client from outside the container:

```java
@Bean(destroyMethod = "")
SharedClient sharedClient(ExternalRegistry registry) {
    return registry.lookupSharedClient();
}
```

This is an illustrative snippet assuming `SharedClient` and `ExternalRegistry` exist in the application. If Spring only **borrows** the resource, you may need to disable inferred `close()`/`shutdown()` using `destroyMethod = ""`. Conversely, if the context truly owns the resource, keep a destroy method enabled to run on failed refresh.

### Clear ownership rules

| Resource | Who is the owner? | How to clean up on startup failure |
| --- | --- | --- |
| Singleton resource created and successfully registered with context | Spring (if design delegates ownership to Spring) | Destroy method/`@PreDestroy`/`DisposableBean` via destruction pipeline |
| Local resource freshly created inside an init method that can still throw | The init method before committing ownership | `try/finally` or try-with-resources inside the method itself |
| Resource freshly created in `@Bean` factory method before returning | The factory method | `catch/finally` before throwing |
| Prototype already handed to caller | Caller | Caller calls `close()`/`destroy()` explicitly |
| External JNDI/shared pool | External owner | Do not close from borrowing context; configure ownership/destroy appropriately |
| File/database/message already written to another system | Side-effect-controlling system/transaction | Explicit compensation/transaction/rollback when contract allows |
| Thread started manually by app outside Spring-managed lifecycle | Thread-spawning code | Interrupt, signal, join per contract, close resources used by thread |

Note: no scope table can automatically guarantee "every resource always destroys itself"; you must know up to which stage a bean is actually managed.

## 11. Different failure types and cleanup scope

| Stage where error occurs | Example | What may have already happened | Handling approach |
| --- | --- | --- | --- |
| Before a valid BeanFactory exists | Environment/property source or config loading error | Few or no singletons; custom code may have side effects | Clean up in custom loader/preparation and report root cause |
| BeanDefinitionRegistryPostProcessor | Wrong definition registration, conflict | Registry being modified; some processors/dependencies may be created early | Do not create business beans in metadata phase; fix definitions |
| BeanFactoryPostProcessor | Missing placeholder, invalid config | Regular bean instances not yet pre-instantiated, exceptions may trigger early creation | Validate metadata, avoid `getBean()` inside BFPP |
| BeanPostProcessor registration | Processor has overly broad dependencies or constructor error | Infrastructure beans partially created | Keep processors lean, avoid forcing business singletons to create early |
| Constructor/factory method | Throws after opening socket/file | Failed object not yet fully managed | Clean up immediately in factory/constructor wrapper; extract resource owner bean |
| Setter/`@Autowired` dependency | `NoSuchBeanDefinitionException`, circular dependency | Some dependency singletons already ready | Container destroys existing singletons; fix graph |
| `@PostConstruct`/`afterPropertiesSet`/custom init | Invalid config, handshake failure | Failing bean initializing, dependencies may already be registered | Internal cleanup before throwing, plus destruction of dependency singletons |
| `SmartInitializingSingleton` | End-of-singleton-loop validation fails | Many singletons may already have finished | Clean up singletons via failed refresh; do not publish readiness |
| `SmartLifecycle`/`finishRefresh` | Background consumer startup or listener throws exception | Workers may exist, part of subsystem active | Design dedicated stop/cleanup, check Spring version behavior, and test failures |
| ApplicationEvent listener | Synchronous listener throws exception | Some listeners already saw the event before error | Choose clear event/exception semantics; do not assume atomic broadcast |

This table describes responsibilities and risks. The exact catch branch depends on Spring version and exception location, especially **before the try block managing destruction**.

## 12. Resource leaks are not just "unclosed beans"

A failed refresh can leave behind side effects that `destroySingletons()` cannot roll back:

- **HTTP calls** already sent to another service.
- **Messages** already published to a broker.
- **Files** already written to the filesystem.
- **Database updates** committed outside a controlled transaction.
- **OS threads** still running if the app started them without a termination hook.
- **Scheduled tasks** registered with an external scheduler.
- **Static caches/registries** holding references to incomplete beans.
- **ThreadLocal** holding unreset data.

Any cleanup callback running inside a container failing startup can also encounter another dependency that is not ready. Hence destruction methods should be **idempotent, non-blocking within reasonable limits, tolerant of partial state**, and not demand that the entire context be active.

### Idempotent close example

```java
import java.util.concurrent.atomic.AtomicBoolean;

final class SafeHandle implements AutoCloseable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        // Perform actual cleanup, according to handle ownership.
    }
}
```

This is a syntactically standalone illustrative class, though `// actual cleanup` must be implemented per resource. The code shows how to avoid duplicate callbacks closing the same handle across failure or shutdown paths. For complex resources, ensure close does not mark "cleaned" before cleanup genuinely succeeds if retry/reconciliation mechanisms exist.

### Do not swallow the original exception

When handling init errors, prioritize logging the full root cause, then run cleanup without replacing the primary cause message. Use `Throwable.addSuppressed` when cleanup also throws while handling an already-existing failure.

Do not return `null` or a "dummy" bean from a factory method just to let refresh continue when a required dependency is unavailable; the container could complete startup in an invalid state that is much harder to diagnose.

## 13. Signs that the context cancelled refresh

When Spring executes the standard 6.2.18 `cancelRefresh()` branch, `context.isActive()` returns `false`. In the section 5 example, these observations:

```text
refreshFailed=true
contextActive=false
refreshedEventSeen=false
failedBeanCleanupCalled=false
```

carry distinct meanings:

- `refreshFailed=true`: the caller received an exception and does not treat context startup as successful.
- `contextActive=false`: the container lifecycle state was cancelled.
- `refreshedEventSeen=false`: the error path occurred before finishing refresh and publishing the event.
- `failedBeanCleanupCalled=false`: the instance failing in init had not yet registered a destruction callback for Spring to invoke in that scenario.

Do not use `isActive()` alone to conclude that **all OS and remote resources have been reclaimed**. To prove that, check actual resources or counters/callbacks from the responsible owners.

### A key diagnostic sequence of questions

When seeing a startup exception, ask in order:

1. **Where did the initial exception come from?** Constructor, factory method, BFPP, BPP, init callback, or an event listener?
2. **Which beans registered successfully?** Find dependencies created before the failing bean.
3. **Which resources were opened before the bean finished its lifecycle?** Are they cleaned up in `catch/finally`?
4. **Are there threads or external side effects outside BeanFactory?**
5. **Did destruction logs actually appear?** If close threw an exception, was the startup root cause masked?
6. **Is anything depending on `ContextClosedEvent` of a failed context?** Re-examine the design.
7. **Is anything retrying with the same context instance?** If so, check whether the context type supports it and whether state truly resets.

## 14. Unit tests and integration tests for the failure branch

A unit test of class `BrokenService` can call `initialize()` and assert an exception, yet that **does not** prove Spring automatically destroys dependency singletons when `refresh()` fails. To verify this contract, instantiate a real `ApplicationContext`.

### Meaningful tests

- Create `Connection` and `Pool` singletons via BeanFactory; force a dependent bean to throw in init.
- Assert the caller receives `BeansException` or the expected cause.
- Assert `Connection.close()` and `Pool.close()` are both called exactly once per contract.
- Assert cleanup order by dependency: pool before connection.
- Assert the init-failing bean is not assumed to have registered destruction.
- Assert context is inactive and did not successfully publish `ContextRefreshedEvent` before failure.
- Assert out-of-container clients/jobs are cleaned up by their respective owners if present.
- Assert successful initialization still closes properly on normal context shutdown.
- Assert cleanup works when init throws on the first attempt and across multiple attempts (avoiding retry resource leaks).
- Assert cleanup exceptions do not obscure the startup root cause.

For the section 5 example, the `EVENTS` list can be turned into JUnit 5 assertions:

```java
assertTrue(EVENTS.contains("connection.closed"));
assertTrue(EVENTS.contains("pool.closed"));
assertFalse(EVENTS.contains("service.cleanup"));
assertTrue(EVENTS.indexOf("pool.closed")
        < EVENTS.indexOf("connection.closed"));
```

This is an **illustrative test snippet**; assume test code has access to `EVENTS` and imports appropriate assertions. Testing small events like these proves lifecycle executed, unlike tests that only check `context.isActive()==false`.

Do not snapshot verbatim Spring WARN log text as a test contract: internal logging can change across patch versions.

## 15. When should you not use refresh() to retry?

Some applications intend to "call `refresh()` again after a few seconds" if startup fails. This approach easily goes wrong:

- `GenericApplicationContext`/`AnnotationConfigApplicationContext` implementations are not meant for repeated refresh after initialization.
- Some external resources are already destroyed, others are not, and the singleton registry may no longer be in a valid state to recreate beans as expected.
- Custom BeanFactoryPostProcessors may have mutated definitions once already.
- Static state and global callbacks may remain from the first attempt.
- Shutdown hooks/lifecycle events on a failed context are not a general application resetter.

If you want resilience when an **external dependency is temporarily unavailable**, consider separating retry strategy into the **resource/client layer** with proper timeouts, backoff, retry budgets, and circuit breakers/health checks. When initialization must fail-fast, fixing the cause and **instantiating a new context** is the safer direction.

Do not retry infinitely inside `@PostConstruct` and block startup forever when the application cannot report progress or stop cleanly on shutdown.

## 16. Differences between failed refresh and normal close

| Criterion | Refresh succeeds then `close()` | Refresh fails inside Spring 6.2.18 catch |
| --- | --- | --- |
| State before shutdown | Context active | Startup hit an exception |
| `ContextRefreshedEvent` | Published at end of refresh | No if failed before `finishRefresh()` |
| Main cleanup path | `doClose()` | `destroyBeans()` then `cancelRefresh()` |
| `ContextClosedEvent` | Published from `doClose()` of active context | Should not be expected since cancel path is not `doClose()` |
| `LifecycleProcessor.onClose()` | Called during normal shutdown | Should not be expected by default in 6.2.18 catch branch |
| Singleton destroy callbacks | Executed when applicable | Attempted for already-managed singletons |
| Bean failing mid-init | Not applicable when startup already succeeded | May not have registered destructor yet |
| Prototype destruction | Caller responsible | Caller still responsible |
| External side effects | Not automatically rolled back | Not automatically rolled back |
| Context active after operation | `false` | `false` if `cancelRefresh` path finishes |

Check Javadoc/source for the exact **version** when implementing custom contexts or libraries requiring graceful shutdown; do not apply 6.2.18 observations blindly to every newer release.

## 17. Common mistakes and solutions

| Mistake | Why is it wrong? | Adjustment |
| --- | --- | --- |
| Assuming a failed refresh never created any singletons | Many dependency singletons may have been created before the failing bean | Understand `destroyBeans` cleans up managed singletons |
| Believing `@PreDestroy` of an init-failing bean always runs | The failing bean may not have registered disposal yet | Clean up opened resources immediately in init code when throwing |
| Relying on `@Bean(destroyMethod="close")` when factory method throws before returning | Factory has not handed a finished bean to the container | Try/finally inside the factory method |
| Treating `ContextClosedEvent` as the sole cleanup point | Failed refresh is not a normal close path | Use destroy callbacks on owner beans and cleanup in failure paths |
| Holding references to beans from an inactive context | Bean graph may be partially destroyed | Discard failed context, create a new context |
| Calling `getBean()` in BeanFactoryPostProcessor to "check readiness" | Instantiates beans too early, missing processors | Validate metadata or use an appropriate post-initialization hook |
| Opening resources in constructor and leaving `@PreDestroy` to handle constructor throw | Container never receives a successfully created object | Create resources in a factory wrapper with explicit cleanup |
| Closing an external shared client on failed refresh | Ownership belongs to another app server/registry | Use empty `destroyMethod` if appropriate, preventing callbacks from closing it |
| Not testing cleanup when callbacks throw | Leaks or lost root cause | Test failure injection + suppressed exceptions |
| Assuming every Spring version auto-stops every SmartLifecycle on refresh failure | Code paths can differ by version and timing | Read exact version source; design idempotent teardown |
| Calling `refresh()` again on the same `AnnotationConfigApplicationContext` | Not a multi-cycle refreshable context | Instantiate a new context |
| Concluding "no leak" solely from `isActive=false` | Active is context state, not measuring sockets/threads/files | Measure actual resources, callback counts, and worker liveness |

## 18. Safe design guidelines for real systems

1. **Separate ownership into small beans:** database connection pools, HTTP clients, executors, and message consumers should each have an owner with a clear lifecycle. When a downstream service fails, Spring can destroy successfully created owners.
2. **Init commits state only after succeeding:** every resource opened in init must be protected by local cleanup if a subsequent step throws.
3. **Disable cleanup only when the resource is borrowed:** `@Bean(destroyMethod = "")` helps when the container does not own an external resource; it does not automatically disable `@PreDestroy`/`DisposableBean` if the bean still has those callbacks.
4. **Do not abuse init callbacks to start threads immediately:** `SmartLifecycle` or an explicit start/stop mechanism may fit better, while still designing failure cleanup per version/timing.
5. **Do not make shutdown depend on an active context:** a bean's destruction method may be called while the container is cancelling; avoid arbitrary `getBean()` calls inside destroy.
6. **Use the dependency graph instead of declaration order:** a bean needing another resource must declare a real dependency via constructor/factory args so Spring knows destruction relationships.
7. **Preserve the error cause:** log the bean name and root cause; if cleanup also fails, record suppressed error details.
8. **Test both fail-fast and partial-success:** a test that only fails before any bean is created does not prove Spring cleanup under the hardest conditions.

## 19. Summary mental checklist

Three questions can be asked for every resource that may have been created during `refresh()`:

**First, who owns it?** If Spring created and registered it as a managed singleton, Spring can invoke its destruction callback when cancelling refresh. If the resource is owned by a local method or another container, ownership does not transfer merely because code lives inside a Spring app.

**Second, did the object finish creation?** An init callback throwing an error leaves the object without completed destruction registration under normal processing; that object's own cleanup must be designed locally.

**Third, in which phase did the failure occur?** In Spring 6.2.18, the catch block responsible for `destroyBeans()`/`cancelRefresh()` wraps most operations after `prepareBeanFactory()`, and cannot be applied unconditionally to every early exception before that phase.

If all three questions are answered clearly, you can verify startup failures without confusing cancelled context state with genuinely released external resources.

## 20. Official sources

- [Spring Framework 6.2.18 — AbstractApplicationContext.refresh() source](https://github.com/spring-projects/spring-framework/blob/v6.2.18/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java): try/catch placement, `destroyBeans()`, `cancelRefresh()`, and differences from `doClose()`.
- [Spring Framework 6.2.18 — AbstractAutowireCapableBeanFactory.doCreateBean() source](https://github.com/spring-projects/spring-framework/blob/v6.2.18/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java): `populateBean`/`initializeBean` before `registerDisposableBeanIfNecessary`.
- [Spring Framework 6.2 — AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh failure contract, `destroyBeans`, `cancelRefresh`, `doClose`.
- [Spring Framework 6.2 — ConfigurableApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): startup, refresh, and close semantics.
- [Spring Framework Reference — Bean lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, and custom destruction.
- [Spring Framework Reference — Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton and prototype destruction semantics.

**Key takeaway:** failure inside `refresh()` triggers cleanup scoped to container-managed beans; application code remains responsible for closing resources opened before bean creation finishes and reverting side effects outside the BeanFactory.
