# Avoiding Calls to Other Beans or Heavy Work Inside Spring Initialization Callbacks

## 1. Purpose and Principles

Spring manages a bean's lifecycle: creating the instance, resolving dependencies, injecting properties, invoking initialization callbacks, applying bean post-processing, and then delivering the completed bean to the application. `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and `@Bean(initMethod = "...")` are callbacks **during the creation of that bean itself**.

**Practical rule:** initialization callbacks should only validate configuration and prepare small internal state with predictable cost. Do not use callbacks as a launchpad for arbitrary business workflows, heavy jobs, networking, databases, or background threads.

Official Spring documentation emphasizes that `@PostConstruct` and initialization methods in general execute inside the **singleton creation lock** for the singleton being created. A bean is only considered completely initialized after the callback returns; uncontrolled access to other beans at this stage increases the risk of **initialization deadlock**. For work that needs to happen after eager singletons finish, there are `SmartInitializingSingleton.afterSingletonsInstantiated()`, `ContextRefreshedEvent`, or `(Smart)Lifecycle`.

This does **not mean** every method call on an injected dependency is forbidden. Reading existing immutable data or checking simple invariants can be fine. What to avoid is dynamic access that pulls other beans into creation, triggers large business chains, or waits on tasks that depend on the container currently bootstrapping.

## 2. Lifecycle and When a Bean Is Truly Ready

~~~text
ApplicationContext.refresh()
  ├─ Read bean definitions, register BeanPostProcessors
  ├─ Resolve constructor/factory method arguments
  ├─ Create bean instance
  ├─ Inject setter/field/property dependencies
  ├─ Aware callbacks and pre-initialization post-processing
  │     └─ @PostConstruct is processed in this phase
  ├─ InitializingBean.afterPropertiesSet()
  ├─ Custom initMethod / init-method
  ├─ BeanPostProcessor post-initialization (may create proxy)
  ├─ Bean is complete and managed by the container per scope
  ├─ Finish creating remaining eager singletons
  ├─ SmartInitializingSingleton.afterSingletonsInstantiated()
  ├─ LifecycleProcessor starts eligible lifecycle beans
  └─ Publish ContextRefreshedEvent; finish refresh()
~~~

This is a conceptual diagram of a standard bean. Special cases exist such as `FactoryBean`, early proxies, lazily initialized beans, custom post-processors, or circular dependencies. Do not infer from the diagram that every pre-initialization post-processor is guaranteed to run before `@PostConstruct`: that annotation is handled by a dedicated post-processor, and ordering among post-processors has its own contract.

If three callbacks using **different methods** are declared on the same bean, the standard order guaranteed by Spring is:

1. `@PostConstruct` method.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method (e.g., `@Bean(initMethod = "initialize")`).

**A bean already created by its Java constructor** does not mean **Spring has finalized the bean**. Init callbacks still run before the outer AOP proxy is formed. If the object is handed to another thread too early, that thread may observe incomplete state or a raw target bypassing interceptors.

### Scope changes when init callbacks run

| Scope | When does the init callback run? | Specific risk |
| --- | --- | --- |
| Non-lazy singleton | Usually during context refresh | Blocking callback prolongs bootstrap |
| `@Lazy` singleton | When the bean is first needed, possibly after refresh | Slow first request; bean is still mid-creation |
| Prototype | Each time the container creates a new instance | Repeated cost/side effects |
| Request | When the target is created within an HTTP request | Slows down the first request in the scope |
| Session | When the target is created within an HTTP session | Slows down first access to session state |

Spring does not automatically invoke destroy callbacks for each handed-out prototype; resource-holding beans must have a clear owner.

## 3. Singleton Creation Lock and Wait Cycles

Spring must synchronize singleton creation so multiple threads do not arbitrarily construct the same bean and so the bean is published at the right time. An init method waiting on external work can stall the bean creation process itself.

~~~text
STARTUP thread:
    currently creating bean A
    A.@PostConstruct()
       ├─ submits a task T
       └─ Future.get() waits for T to finish

EXECUTOR thread:
    task T needs applicationContext.getBean(A.class)
       └─ waits for creation of A to complete

STARTUP is waiting on EXECUTOR
EXECUTOR is waiting on STARTUP
→ wait cycle can cause deadlock
~~~

The diagram is a **risk scenario**, not a guarantee that every Spring configuration deadlocks in this exact way; depending on the bean graph, the framework might throw `BeanCurrentlyInCreationException`, return an early reference where permitted, or block. Nonetheless, circular wait structures must be eliminated.

Operations that commonly introduce risk:

- Calling `applicationContext.getBean(...)` or `getBeansOfType(...)` without knowing which beans already exist, pulling other singletons into bootstrap.
- Calling another service that performs lazy lookup or calls back into the bean currently initializing.
- Spawning a thread and immediately calling `join()`/`Future.get()` inside the callback.
- Using latches, locks, or monitors that depend on an event only published after `refresh()`.
- Opening network/DB connections without timeouts or with unbounded retries.
- Starting executors/consumers/schedulers that begin processing immediately while dependencies and proxies are not yet initialized.

**Not every `getBean()` is guaranteed to deadlock.** A simple already-initialized bean can be retrieved successfully. The risk is that the callback holds container bean-creation state while the invoked logic can evolve or pull in additional dependencies over time. Long-lived designs should not depend on accidental initialization order.

## 4. Appropriate Tasks Inside `@PostConstruct`

Init callbacks fit **local validation, small data setup, and invariants of the bean itself**.

~~~java
@Component
public class RetrySettings {
    private final int attempts;
    private Map<String, Integer> delays;

    public RetrySettings(@Value("3") int attempts) {
        this.attempts = attempts;
    }

    @PostConstruct
    void validateAndPrepare() {
        if (attempts < 1 || attempts > 10) {
            throw new IllegalStateException("attempts out of range");
        }
        delays = Map.of("fast", 100, "normal", 500);
    }

    public int delay(String priority) {
        return delays.getOrDefault(priority, 1000);
    }
}
~~~

This is an **illustrative snippet**, requiring imports for `java.util.Map`, `jakarta.annotation.PostConstruct`, `org.springframework.stereotype.Component`, and `org.springframework.beans.factory.annotation.Value`; component scanning must be enabled. `@Value("3")` is a literal to make the lifecycle clear. The callback validates and builds a small `Map`, with no I/O, no waiting on external services, and no fetching other beans.

If the constructor can establish full state, consider dropping the callback altogether:

~~~java
public final class RetryDefaults {
    private final Map<String, Integer> delays;

    public RetryDefaults() {
        delays = Map.of("fast", 100, "normal", 500);
    }
}
~~~

The second snippet requires importing `Map`. Explicit `final` fields usually keep objects simple, easy to test, and less dependent on lifecycle order.

### Sensible fail-fast

If invalid configuration makes the bean unusable, `@PostConstruct` can throw `IllegalStateException` with a clear message. Spring normally wraps bean creation failures in `BeanCreationException`; for eager singletons, context refresh fails. This is appropriate for mandatory invariants, **unlike** bringing down the whole application because an optional remote cache is temporarily down.

## 5. Behaviors to Avoid in Callbacks

| Work | Problem | How to handle |
| --- | --- | --- |
| Warming a cache of millions of records | Holds up startup, consumes RAM, mid-way exceptions | Post-singleton hook, separate job, timeouts, and readiness |
| Calling REST/gRPC APIs repeatedly | Remote outage, DNS, infinite retries | Timeouts, bounded backoff; managed startup workflow |
| DB schema migration | DB locks, contention across replicas | Flyway/Liquibase or deployment migration |
| Starting consumer/long-running scheduler | Runs before app is initialized; lacks stop | `SmartLifecycle` |
| `Future.get()` waiting on task from init | Task may need startup beans/locks | Move orchestration after local init |
| `Thread.sleep()` waiting for another bean | Does not express dependency; hard-to-diagnose races | Constructor injection and readiness conditions |
| Scanning all beans in init | Can trigger premature bean creation | `SmartInitializingSingleton` if eager singletons are needed |
| Calling request/session proxy at startup | No active request/session yet | Use inside a request handler with valid context |
| Calling `@Transactional` method via `this` | Bypasses proxy-based AOP advice | Delegate to a collaborator via proxy after init |
| Creating a thread holding `this` | Bean is incomplete; unmanaged lifecycle | Managed executor and lifecycle |

There is no fixed duration threshold where Spring "allows under N ms and forbids over N ms". What matters is **whether the task is local initialization or an independent runtime activity**, its impact on the creation lock, boundedness of the work, and how failures are handled.

## 6. `@Transactional` and Proxies in Init Callbacks

A classic mistake:

~~~java
@Service
class PaymentService {
    @PostConstruct
    void init() {
        reconcilePayments();
    }

    @Transactional
    public void reconcilePayments() {
        // Query and update payment records.
    }
}
~~~

This is an **illustrative anti-example**, lacking imports and a transaction manager, not a standalone program. Calling `reconcilePayments()` from `init()` is equivalent to `this.reconcilePayments()`: self-invocation on the target **does not go through the Spring AOP proxy**. Moreover, the callback runs while the bean is still initializing; you cannot expect transaction advice, `@Async`, or caching advice to work the same way as a call from another bean through the proxy.

The fix is separating responsibilities:

~~~text
Bean A: @PostConstruct → only validates local configuration

StartupCoordinator: hook after eager singletons are initialized
       ↓ invokes Spring-injected collaborator
TransactionalPaymentService (Spring proxy)
       ↓ executes @Transactional business logic
~~~

For transactions to actually take effect, you still need transaction management enabled, a proper transaction manager, a public/proxy-interceptable method, and a call **through the Spring proxy**. Switching the hook alone does not establish a transaction.

### Request/session scoped proxies

Injecting a request-scoped proxy into a singleton can succeed at startup. However, **invoking a method through the proxy** when no HTTP request is bound usually results in a scope-not-active exception. A singleton's initialization callback does not create a synthetic HTTP request. Only use request data inside an active request, or extract independent data to pass to background jobs.

## 7. `BeanPostProcessor` and Prematurely Initialized Beans

`BeanPostProcessor` is an extension point registered relatively early by the container to intercept beans created afterward. If a BeanPostProcessor depends directly or indirectly on a business service, that service can be created **before all post-processors are registered**, leaving it ineligible for full post-processing, including auto-proxying in some cases. Spring may log a warning that a bean is not eligible for getting processed by all BeanPostProcessors.

For a `@Bean` producing a BeanPostProcessor, it is usually best to use a **static factory method** and minimize dependencies:

~~~java
@Configuration
class ExtensionConfig {
    @Bean
    static BeanPostProcessor loggingProcessor() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {
                return bean;
            }
        };
    }
}
~~~

This snippet requires importing `BeanPostProcessor`, `@Bean`, and `@Configuration`. The example keeps business logic out of the processor. Do not use `BeanFactoryPostProcessor` to call `getBean()` on business beans early; that extension point is meant primarily to adjust **bean definitions**, not instantiate bean instances during the configuration phase.

## 8. `SmartInitializingSingleton`: After Eager Singletons Are Created

`org.springframework.beans.factory.SmartInitializingSingleton` provides:

~~~java
void afterSingletonsInstantiated();
~~~

The callback runs at the end of the pre-instantiation phase of **regular non-lazy singletons**, outside each singleton's local init method. If you need to inspect the set of eager singletons or call an already-constructed collaborator, this is an appropriate choice.

~~~java
@Component
class IndexWarmup implements SmartInitializingSingleton {
    private final IndexService index;

    IndexWarmup(IndexService index) {
        this.index = index;
    }

    @Override
    public void afterSingletonsInstantiated() {
        index.validateLocalMetadata();
    }
}
~~~

This is a snippet; it assumes the application has `IndexService`, the corresponding Spring imports, and fast metadata validation.

**Exact limits:**

- This hook does not run for prototypes or request/session beans, and is **not guaranteed** to run for `@Lazy` singletons created only after the eager bootstrap phase.
- Eager singletons being initialized does not mean **external systems** are ready or traffic readiness has been reached.
- The hook is **not automatically async**; a 30-second callback still slows startup by 30 seconds.
- For asynchronous workers needing real start/stop control, Spring Javadoc recommends `Lifecycle` or `SmartLifecycle`.

## 9. `ContextRefreshedEvent`: After the Refresh Phase

You can use `ApplicationListener<ContextRefreshedEvent>` or `@EventListener` to run logic after the context finishes its refresh initialization steps.

~~~java
@Component
class StartupVerifier {
    private final ExternalCheck check;

    StartupVerifier(ExternalCheck check) {
        this.check = check;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onContextRefreshed() {
        check.verifyWithTimeout();
    }
}
~~~

This is a snippet: `ExternalCheck` must be supplied and its method must genuinely enforce a deadline, with imports for `EventListener`, `ContextRefreshedEvent`, and `Component`.

**Notes:**

- Standard event listeners are invoked **synchronously** by the default multicaster. Slow I/O in a listener still slows down `refresh()`.
- Multiple contexts (parent/child) or multiple refreshes can exist; events may arrive more than once. Use filtering and idempotency if the operation has side effects.
- The `ContextRefreshedEvent` milestone is not synonymous with **application readiness**. `ApplicationReadyEvent` is a Spring Boot hook with higher-level semantics than the Spring Core Container.

Example context filtering if a listener applies only to a specific context:

~~~java
if (event.getApplicationContext() != expectedContext) {
    return;
}
~~~

This is a snippet, with `expectedContext` properly identified in the application.

## 10. `SmartLifecycle`: Starting/Stopping a Long-Lived Process

A polling job, consumer, or scheduler needs both **startup and shutdown**, not just an init callback. `SmartLifecycle` supports:

- `start()`: starts the component.
- `stop()` or `stop(Runnable)`: stops the component; for async shutdown, invoke the callback **after** stopping finishes.
- `isRunning()`: current status.
- `isAutoStartup()`: whether to start automatically on refresh.
- `getPhase()`: relative ordering. **Lower phases start first; higher phases stop first** in a typical shutdown sequence.

~~~java
public final class PollerLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        // Register polling worker on a managed executor.
        running = true;
    }

    @Override
    public void stop() {
        // Stop polling and close resources per real contract.
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

This is an **illustrative skeleton**, not a production worker since it lacks a real executor, queue, and concurrency handling. It requires importing `org.springframework.context.SmartLifecycle` and registering the bean. If `stop()` is asynchronous, never invoke `callback.run()` before shutdown has truly completed. `running=true` also does not prove business readiness.

## 11. Runnable Java 17 Example: Lightweight Init and Two Post-Init Milestones

Standalone example using Java 17, Maven, and Spring Framework 6.2.12. Does not use Spring Boot, a web server, or async tasks with unpredictable stdout.

Directory structure:

~~~text
safe-startup/
├── pom.xml
└── src/main/java/example/SafeStartupDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>safe-startup</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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

File `src/main/java/example/SafeStartupDemo.java`:

~~~java
package example;

import java.util.Map;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;

public final class SafeStartupDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            LocalRules rules = context.getBean(LocalRules.class);
            if (rules.weight("urgent") != 10) {
                throw new IllegalStateException("Unexpected rules");
            }
            System.out.println("6. Main: context refreshed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(initMethod = "prepare")
        public LocalRules localRules() {
            return new LocalRules("vn");
        }

        @Bean
        public StartupHooks startupHooks(LocalRules rules) {
            return new StartupHooks(rules);
        }
    }

    public static final class LocalRules {
        private final String region;
        private Map<String, Integer> weights;

        public LocalRules(String region) {
            this.region = region;
            System.out.println("1. Constructor: region configured");
        }

        @PostConstruct
        public void validate() {
            if (region.isBlank()) {
                throw new IllegalStateException("Region required");
            }
            System.out.println("2. @PostConstruct: validation");
        }

        public void prepare() {
            weights = Map.of("urgent", 10, "normal", 5);
            System.out.println("3. initMethod: local map");
        }

        public int weight(String key) {
            return weights.getOrDefault(key, 0);
        }
    }

    public static final class StartupHooks
            implements SmartInitializingSingleton,
                       ApplicationListener<ContextRefreshedEvent> {
        private final LocalRules rules;

        public StartupHooks(LocalRules rules) {
            this.rules = rules;
        }

        @Override
        public void afterSingletonsInstantiated() {
            if (rules.weight("normal") != 5) {
                throw new IllegalStateException("Rules not ready");
            }
            System.out.println("4. Eager singletons initialized");
        }

        @Override
        public void onApplicationEvent(ContextRefreshedEvent event) {
            System.out.println("5. ContextRefreshedEvent received");
        }
    }
}
~~~

Run command:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.SafeStartupDemo
~~~

Exact stdout from `System.out.println` in the program (excluding Maven or system logger output):

~~~text
1. Constructor: region configured
2. @PostConstruct: validation
3. initMethod: local map
4. Eager singletons initialized
5. ContextRefreshedEvent received
6. Main: context refreshed
~~~

Explanation:

1. Spring invokes the `localRules()` factory method, which calls the `LocalRules("vn")` constructor.
2. `@PostConstruct` validates a string in internal state, without fetching other beans or performing I/O.
3. `initMethod="prepare"` builds a small `Map`; at this point the bean has completed its internal callbacks.
4. `StartupHooks` is an eager singleton; `afterSingletonsInstantiated` runs after eager singletons' pre-instantiation, so `LocalRules` is already ready.
5. `ContextRefreshedEvent` is published during the refresh of the single context.
6. After the `AnnotationConfigApplicationContext(Config.class)` constructor finishes, `main` prints line 6.

The code properly distinguishes **local init**, **after eager singleton initialization**, and **context refresh**. It spawns no async tasks so the six-line order is deterministic. If you add an executor/thread, completion order depends on scheduling and synchronization; never fabricate a fixed stdout.

## 12. Moving Risky Warmup Out of Local Init

**Before — heavy work inside the callback:**

~~~java
@Component
class ProductCache {
    private final ProductApi api;

    ProductCache(ProductApi api) {
        this.api = api;
    }

    @PostConstruct
    void init() {
        api.downloadFullCatalog();
    }
}
~~~

This is an illustrative anti-example, not a standalone Java file. If the network is slow, `ProductCache` remains not fully initialized the entire time `downloadFullCatalog()` waits. A remote outage turns into a bootstrap failure.

**After — lightweight init, warmup in an appropriate hook:**

~~~java
@Component
class ProductCache {
    private final ProductApi api;

    ProductCache(ProductApi api) {
        this.api = api;
    }

    @PostConstruct
    void validateLocalState() {
        // Only validate local configuration.
    }

    void warmup() {
        api.downloadCatalogWithDeadline();
    }
}

@Component
class ProductCacheWarmup implements SmartInitializingSingleton {
    private final ProductCache cache;

    ProductCacheWarmup(ProductCache cache) {
        this.cache = cache;
    }

    @Override
    public void afterSingletonsInstantiated() {
        cache.warmup();
    }
}
~~~

These two illustrative classes require a `ProductApi` type and appropriate Spring imports. This approach moves external I/O to after eager singleton initialization, **yet it is still synchronous**: a 2-minute download still delays startup by 2 minutes. If the cache is optional or warmup is very expensive, use a managed executor/job and proper readiness. Do not assume `SmartInitializingSingleton` automatically offloads work to the background.

## 13. Choosing the Right Hook for Each Goal

| Real goal | Choice | Limitation to remember |
| --- | --- | --- |
| Validate config and build a small local map | Constructor/`@PostConstruct`/`initMethod` | Should not depend on other unready beans |
| Need to call a collaborator after regular eager singletons finish | `SmartInitializingSingleton` | Excludes lazy/prototype beans, can still block |
| Need to act at the context refresh milestone | `ContextRefreshedEvent` | May run synchronously and fire multiple times |
| Worker/consumer must start and stop in phases | `SmartLifecycle` | Must genuinely manage resources and shutdown callback |
| Logic after Boot has run startup runners | `ApplicationReadyEvent` (Spring Boot) | Not part of the pure Core Container API |
| Versioned DB migration/seeding | Flyway/Liquibase or deployment job | Requires coordination across multiple replicas |
| Large job, retry/cancel, progress tracking | Managed executor/job queue | Readiness and failure policy must be separated from local bean init |
| Per-HTTP-request handling | Request handler/service | Cannot be replaced by an application startup callback |

"After singleton init" **does not guarantee all external systems are healthy**. Each choice distinguishes between **a bean finishing creation**, **context finishing refresh**, and **the application genuinely being ready to handle traffic**.

## 14. Timeouts, Startup Failures, Idempotency, and Cleanup

### 14.1. Mandatory validation vs transient errors

- Invalid local configuration: **fail fast** in init is appropriate.
- External API experiencing an outage when a fallback exists: usually report degraded health and use bounded retries; never wait indefinitely in init.
- Required infrastructure not ready yet: policy may be blocking readiness, bounding startup duration, or failing startup per operational requirements.

Distinguish **mandatory** errors from **recoverable** errors; do not swallow exceptions and claim "ready" when core functionality is unusable.

### 14.2. Timeouts

External I/O needs a connect timeout, read/request timeout, and overall deadline. Retries should be bounded, with backoff and policies preventing thundering herds across replicas. Timeouts prevent infinite hangs, but **do not fix dependency-cycle deadlocks**, so wait cycles must still be eliminated.

### 14.3. Idempotency

A `ContextRefreshedEvent` can arrive multiple times with context hierarchies or re-refreshes. Multiple application instances may run a startup job concurrently. If a job creates tables, sends messages, or writes to a DB, you need idempotency, unique keys, locking, or proper migration orchestration; Spring events do not guarantee exactly-once execution for side effects outside the JVM.

### 14.4. Cleanup

Threads, executors, subscriptions, sockets, and file handles need a clear owner, shutdown callback, and bounded stop duration. With `SmartLifecycle.stop(Runnable)`, the callback must be invoked **once stopping has finished**. Do not rely on `@PreDestroy` as a magic mechanism to stop self-created threads without actual cleanup code. When startup fails partway through, do not assume every destroy callback runs on partially initialized objects; use `try/finally` or controlled cleanup mechanisms.

## 15. Diagnosing an Application Hung at Startup

When the application logs "Creating bean ..." and never finishes, do the following:

1. Take a thread dump; inspect which startup thread is stuck in `@PostConstruct`, `Future.get()`, DB read, socket read, lock, or call graph.
2. Trace the dependency graph from the bean being created; identify which call from the callback triggers creating another bean or loops back to the same bean.
3. Check whether the bean has an AOP proxy; distinguish raw target vs proxy, and self-invocation vs external invocation.
4. Measure duration of constructors, setters, callbacks, listeners, and lifecycle start. Configure timeouts on external I/O.
5. Check whether `refresh()` is stalled on init, `SmartInitializingSingleton`, or a synchronous event listener.
6. If you see a warning that a bean is "not eligible for getting processed by all BeanPostProcessors", check if some BeanPostProcessor pulled a service into creation too early.
7. Test with slow APIs, offline DBs, executors with zero workers, parent-child contexts, startup failures, and shutdowns with in-flight tasks.

Never fix a startup hang simply by increasing wait times indefinitely.

## 16. Common Pitfalls

| Symptom | Typical cause | How to fix |
| --- | --- | --- |
| Init callback calls a bunch of services | Accessing other beans too early | Keep init local; use a post-eager-singleton hook |
| `BeanCurrentlyInCreationException` | Circular dependency | Split responsibilities and break the dependency cycle |
| `@Transactional` has no effect in init | `this` bypasses proxy | Call collaborator through Spring proxy after init |
| `@Async` is not async on internal call | Self-invocation | Separate beans, manage executor and lifecycle |
| Request proxy fails at startup | No active request yet | Use only during an HTTP request |
| Boot takes minutes to start | DB/network/warmup inside callback | Add timeouts, move job out, manage readiness |
| Moved `@PostConstruct` to listener but still slow | Listeners are synchronous by default | Use managed async or a dedicated job workflow |
| `afterSingletonsInstantiated` does not run | Bean is lazy/prototype | Review scope and hook contract |
| Listener runs twice | Context hierarchy/repeated refresh | Filter context, ensure idempotency |
| Shutdown hangs | Worker lacks stop/cancel or shutdown callback | `SmartLifecycle`, graceful stop with deadline |
| Bean is not auto-proxied | Created too early by a BeanPostProcessor | Simplify processor and its dependencies |
| Prototype repeats I/O on every lookup | Init callback runs per instance | Move I/O out of prototype or cache appropriately |

## 17. Self-Check Questions

**Question 1.** Does calling `getBean(OtherService.class)` inside `@PostConstruct` always deadlock?

**Answer:** No. However, the callback runs mid-bean-creation and can pull uninitialized dependencies, causing circular dependencies or deadlocks. Keep interactions local, explicit, and short; avoid unnecessary dynamic bean resolution.

**Question 2.** Does moving a 90-second warmup to `SmartInitializingSingleton` make startup finish instantly?

**Answer:** No. The hook still runs synchronously. It solves timing relative to eager singleton creation, not async execution.

**Question 3.** Does `@EventListener(ContextRefreshedEvent.class)` guarantee running exactly once and asynchronously?

**Answer:** No. It can run synchronously and receive multiple events/context refreshes. Configure dispatch and idempotency if required.

**Question 4.** Is a `@Transactional` method called via `this` from an init callback guaranteed to have a transaction?

**Answer:** No. Self-invocation bypasses proxy-based Spring AOP advice; the bean is also still under initialization.

**Question 5.** A worker must start in order and stop gracefully. Choose `@PostConstruct` or `SmartLifecycle`?

**Answer:** `SmartLifecycle`, because it provides phases, start, stop, and a shutdown callback.

**Question 6.** A prototype bean has `@PostConstruct` calling an external API. If `getBean` is called 100 times, is the API called only once?

**Answer:** No. Each new prototype instance runs its own initialization callback; external I/O can repeat 100 times. Redesign with appropriate state units and caching.

## 18. Official References

- [Spring Framework — Customizing the Nature of a Bean / Initialization Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Javadoc — SmartInitializingSingleton](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html)
- [Spring Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
