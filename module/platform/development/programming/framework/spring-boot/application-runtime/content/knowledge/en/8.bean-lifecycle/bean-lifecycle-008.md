# Choosing a Bean Callback vs. Runner for Spring Boot Startup Work

## 1. The problem: “at startup” spans multiple distinct moments

In Spring Boot, not all code that runs when an application starts executes at the same moment. **Bean lifecycle callbacks** run while Spring is instantiating and initializing individual beans; **ApplicationRunner** and **CommandLineRunner** run after the ApplicationContext has refreshed, right before SpringApplication finishes startup. Picking the wrong execution point can slow down startup, create dependency cycles, use beans before they are ready, publish readiness too early, or make resource cleanup difficult on failure.

Distinguish two goals:

- **Initializing a single bean:** validating internal configuration, building data structures from injected dependencies, preparing resources owned by that bean. Use a constructor, @PostConstruct, InitializingBean.afterPropertiesSet(), or initMethod as appropriate.
- **Performing an application-level task after the context has been built:** warming an initial cache, verifying mandatory connections, importing startup data, validating conditions before accepting requests. Use ApplicationRunner or CommandLineRunner.

Startup work that must finish **before the system considers the service ready** fits runners, because Spring Boot publishes **ApplicationReadyEvent after runners finish**. Conversely, building small internal data tightly coupled to one bean belongs inside that bean. Listeners/schedulers that run **continuously** usually need SmartLifecycle or a dedicated start/stop mechanism; runners do not provide a stop lifecycle on their own.

## 2. Lifecycle sequence map

In a Spring Boot 3.x application following the successful startup path, the simplified sequence is:

~~~text
SpringApplication.run(args)
    |
    +-- Prepare Environment / create ApplicationContext
    |
    +-- refresh context
    |     |
    |     +-- Create and inject non-lazy singletons
    |     |     +-- constructor / dependency injection
    |     |     +-- @PostConstruct
    |     |     +-- InitializingBean.afterPropertiesSet()
    |     |     +-- @Bean(initMethod = "...")
    |     |
    |     +-- SmartInitializingSingleton.afterSingletonsInstantiated()
    |     +-- SmartLifecycle.start() (autoStartup=true)
    |     +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- SpringApplication.run(...) returns
~~~

This is a **conceptual sequence** for regular context components. Initialization order **across different beans** depends on the dependency graph, @DependsOn, scope types, lazy initialization, and configuration; beans with @PostConstruct must not be treated as a list executed together in class-name order. Spring Framework invokes internal callbacks of **the same bean** in the documented order: **@PostConstruct → afterPropertiesSet() → custom initMethod** when all three are present and are distinct methods.

A **lazy** bean may only be created when first used, even after the application is ready. Thus “@PostConstruct always runs before ApplicationRunner” is **not true for every bean**. When a runner injects a normal non-lazy bean, that bean's callbacks definitely complete before the runner uses it.

## 3. Selection table by criterion

| Criterion | Bean initialization callback | ApplicationRunner / CommandLineRunner |
| --- | --- | --- |
| Scope | One bean and resources it owns | An application-level task after context refresh |
| Timing | When the bean is created, during bean initialization | After ApplicationStartedEvent, before ApplicationReadyEvent |
| Dependency injection | Dependencies are injected into the bean before the callback | Runners are beans and can inject already-constructed services |
| Whole-context state | Does not guarantee all other beans exist yet | Context refreshed successfully; lazy beans may still be uncreated |
| Command-line arguments | Can inject ApplicationArguments, though rarely needed | ApplicationRunner receives ApplicationArguments; CommandLineRunner receives String... args |
| Ordering across tasks | Primarily via dependency graph and @DependsOn | Use @Order / Ordered to order runners |
| If an exception is thrown | Bean creation or refresh may fail; lazy beans may fail on later use | SpringApplication.run(...) fails, does not proceed to ready |
| Shutdown timing | Tied to the bean's destroy callback if present | Runners have no built-in stop callback; use a separate lifecycle/resource owner |
| Best suited for | Validating config, building lookup tables, preparing local state | Mandatory warmup, verifying startup preconditions, controlled import/seeding |

**Selection rule:** if the operation is a precondition for **the bean itself** to become valid, choose bean initialization; if it is **work requiring multiple ready beans** that must finish before readiness, choose a runner.

## 4. Bean initialization: when to use it?

### 4.1. Constructors and dependency injection

Constructors should establish invariants, accept and validate required dependencies, and initialize simple state. Avoid long network I/O, sending messages, calling payment APIs, or querying millions of rows from a constructor. At constructor time, bean creation is incomplete, proxy/AOP wrapping has not been fully applied, and failures midway make cleaning up newly opened resources difficult.

Example:

~~~java
public PricePolicy(int maxDiscountPercent) {
    if (maxDiscountPercent < 0 || maxDiscountPercent > 100) {
        throw new IllegalArgumentException("Invalid discount");
    }
    this.maxDiscountPercent = maxDiscountPercent;
}
~~~

This is an **illustrative snippet** inside a `PricePolicy` class that declares the `maxDiscountPercent` field; it is not a standalone Java program.

### 4.2. @PostConstruct

Spring Framework 6 / Spring Boot 3 uses **jakarta.annotation.PostConstruct**, rather than **javax.annotation.PostConstruct** from older ecosystems.

~~~java
import jakarta.annotation.PostConstruct;

@PostConstruct
void validate() {
    if (path == null || path.isBlank()) {
        throw new IllegalStateException("Missing output path");
    }
}
~~~

This is an **illustrative snippet inside a bean** with a `path` field; its learning point is the callback location. The method runs **after dependencies are injected and before the bean is exposed as fully initialized**. It suits validating properties, building small in-memory data structures, or checking invariants.

A slow @PostConstruct can prolong singleton creation and context refresh. In particular, avoid complex operations that touch many other beans, because singleton creation is still underway and deadlocks or dependency cycles can arise.

**AOP/transaction note:** @PostConstruct runs during bean initialization, before post-processing BeanPostProcessors create needed proxies. Calling an @Transactional method on the same bean inside @PostConstruct **does not guarantee passing through the transaction proxy**. If startup requires transactional work, have a runner invoke **another Spring service** through its container proxy instead of self-invocation.

### 4.3. InitializingBean and custom initMethod

**InitializingBean.afterPropertiesSet()** is a Spring interface requiring an initialization method; it suits components tightly coupled to the framework that need an explicit contract. **@Bean(initMethod="initialize")** calls an init method you name, useful when configuring external library classes whose source cannot be edited.

~~~java
@Bean(initMethod = "initialize", destroyMethod = "close")
ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

The example above is **illustrative configuration code**, where `ExternalClient` is a hypothetical class with `initialize()` and `close()` methods. Method names must match the library's actual API. Do not declare all three of @PostConstruct, afterPropertiesSet, and initMethod just to “be safe”; pick one clear mechanism and avoid duplicating init work.

**Cleanup:** for beans owning connections, streams, or executors, register **@PreDestroy**, **DisposableBean**, or an appropriate destroyMethod. If a factory/constructor opens a resource and then throws before the bean is fully registered, close that resource immediately in a local try/finally; do not assume Spring can clean up an object that failed mid-creation.

## 5. Runners: when to use them?

Spring Boot provides two interfaces for post-refresh startup work:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

These two snippets show **simplified signatures for learning**, omitting packages and Javadoc; they do not replace Spring Boot's actual source. Both become **Spring beans** when registered with @Component or @Bean, and both are invoked by SpringApplication at the same stage.

**ApplicationRunner** fits when convenient argument parsing is useful: **args.containsOption("flag")**, **args.getOptionValues("name")**, **args.getNonOptionArgs()**. **CommandLineRunner** receives the raw `String[]` array, suitable when you have your own parser or simple commands. They differ mainly in **how arguments are passed**, not in execution timing.

Examples of tasks well-suited for runners:

- Warming up a mandatory cache before accepting traffic.
- Checking readiness conditions of a critical resource and aborting startup if unmet.
- Verifying system metadata or data after all beans/services have initialized.
- Running a CLI/batch job taking command-line inputs, after which the application exits by design.

For database schema migrations, use **Flyway or Liquibase** and Spring Boot's corresponding integration: migrations have explicit ordering, history, and version control. Do not replace migration tools with @PostConstruct or an ad-hoc runner. For data seeding, ensure idempotency and execution guards so restarts do not insert duplicate rows.

## 6. Complete Java 17+, Spring Boot 3.x example

The example below shows **@PostConstruct running during bean creation**, followed by an **ApplicationRunner** performing warmup, then a **CommandLineRunner** recording that tasks ran, and finally **ApplicationReadyEvent** being published.

Create a Spring Boot 3.3.x project using Java 17+, with the **spring-boot-starter** dependency and Spring Boot Gradle plugin. The example needs no web server. Put all code into **src/main/java/demo/StartupChoiceDemo.java**; only one class is public while the rest are package-private, which Java permits in a single file.

~~~java
package demo;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class StartupChoiceDemo {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupChoiceDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_RETURNED");
        }
    }
}

@Component
class ConfigurationCheck {
    private boolean valid;

    @PostConstruct
    void initialize() {
        valid = true;
        System.out.println("BEAN_INITIALIZED");
    }

    boolean isValid() {
        return valid;
    }
}

@Component
@Order(10)
class WarmupRunner implements ApplicationRunner {
    private final ConfigurationCheck configuration;

    WarmupRunner(ConfigurationCheck configuration) {
        this.configuration = configuration;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!configuration.isValid()) {
            throw new IllegalStateException("Configuration not initialized");
        }

        System.out.println("RUNNER_WARMUP_START");

        if (args.containsOption("fail-warmup")) {
            throw new IllegalStateException("Warmup failed");
        }

        System.out.println("RUNNER_WARMUP_DONE");
    }
}

@Component
@Order(20)
class AuditRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("RUNNER_AUDIT");
    }
}

@Component
class ReadyReporter {
    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        System.out.println("APPLICATION_READY");
    }
}
~~~

### How to run

If the project uses a Gradle wrapper configured with the Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Order of lines printed by the example itself, on a successful run with no arguments:**

~~~text
BEAN_INITIALIZED
RUNNER_WARMUP_START
RUNNER_WARMUP_DONE
RUNNER_AUDIT
APPLICATION_READY
MAIN_RETURNED
~~~

Spring Boot/Gradle logs may appear in between, yet the order **among these six messages** is guaranteed by dependencies and lifecycle contracts in the example:

1. **ConfigurationCheck** is initialized by Spring and injected into WarmupRunner; @PostConstruct sets `valid=true` and prints **BEAN_INITIALIZED** before the runner uses the bean.
2. After refresh, **WarmupRunner** runs. **@Order(10)** puts it ahead of AuditRunner **@Order(20)**, even though the two runners implement different interfaces.
3. **AuditRunner** prints **RUNNER_AUDIT** after warmup finishes.
4. Spring Boot publishes **ApplicationReadyEvent** after both runners return normally; ReadyReporter prints **APPLICATION_READY**.
5. **SpringApplication.run(...)** returns the context and main prints **MAIN_RETURNED**.

**Important:** @Order controls **runner** order, not the order in which Spring must create all beans per annotation. If multiple runners share the same order, use explicit dependencies or distinct order values when sequence is required; do not rely on component scanning order.

### Testing a warmup failure

~~~bash
./gradlew bootRun --args="--fail-warmup"
~~~

In this run, the application messages appearing before the failure are:

~~~text
BEAN_INITIALIZED
RUNNER_WARMUP_START
~~~

Then the runner throws **IllegalStateException("Warmup failed")**. SpringApplication handles the startup failure; **RUNNER_WARMUP_DONE**, **RUNNER_AUDIT**, **APPLICATION_READY**, and **MAIN_RETURNED** do not appear on this failure path. Gradle may print additional exception details and report that the bootRun task failed. The example demonstrates that **runners act as part of the startup barrier**—if one fails, ready is not published along the success path.

If an exception occurs in **ConfigurationCheck's @PostConstruct** when the bean is initialized, context refresh can fail **before any runner is invoked**. For lazy beans created only on late access, init errors can also surface later: that is why you must consider bean kind and actual creation time.

### Why does the example use ApplicationReadyEvent?

ApplicationReadyEvent here is **only to observe when the application becomes ready**, not where mandatory warmup should run. Moving warmup into an ApplicationReadyEvent handler pushes heavy work into event dispatch. Spring Boot invokes event listeners synchronously by default; doing so delays readiness signaling and makes business ordering across multiple tasks harder to express. Runners are better suited for startup conditions that must finish before serving.

## 7. Options between bean init and runners

Not every case falls cleanly into just two buckets. Spring Framework provides specialized hooks, each solving a different problem.

### SmartInitializingSingleton

**SmartInitializingSingleton.afterSingletonsInstantiated()** is called after the BeanFactory finishes creating **non-lazy singletons**. It fits when a component needs regular singletons to already exist while still participating in context initialization, such as validating the set of registered plugins/handlers.

~~~java
@Component
class HandlerRegistryVerifier implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Check the set of handlers created during the singleton phase.
    }
}
~~~

This is an illustrative snippet: import **org.springframework.beans.factory.SmartInitializingSingleton** and **org.springframework.stereotype.Component** in a full Java class. This hook **does not guarantee all lazy/prototype beans have been created** and is not the ApplicationReadyEvent signal.

### SmartLifecycle

If a bean must **start and stop ongoing activity** (consumers, listeners, background workers), **SmartLifecycle** fits better than a plain runner because it provides **start()**, **stop()**, **isRunning()**, **isAutoStartup()**, **getPhase()**, and controlled shutdown.

On context refresh, SmartLifecycle beans auto-start if **isAutoStartup()=true** via the lifecycle processor. **Lower getPhase() starts first**, and shutdown runs in reverse; dependency relationships still apply. This is lifecycle-bean start/stop ordering, **distinct from runner @Order**.

If a consumer begins pulling remote messages as soon as SmartLifecycle.start() is called, you must manage traffic acceptance yourself while the application is not yet ready. Do not assume external systems wait for Spring Boot to publish readiness.

### ContextRefreshedEvent, ApplicationStartedEvent, ApplicationReadyEvent

- **ContextRefreshedEvent** indicates the context refreshed. In applications with a context hierarchy or multiple refreshes, handlers may receive multiple events; do not assume it runs only once.
- **ApplicationStartedEvent** in Spring Boot appears after refresh but **before runners**; suitable for observing the started milestone, not for replacing runners on ordered tasks.
- **ApplicationReadyEvent** appears **after runners** and before Spring Boot publishes **ReadinessState.ACCEPTING_TRAFFIC**. Suitable for lightweight logging/telemetry once startup succeeds.

If the goal is **business work that must finish before ready**, runners are the easiest option to trace. If background work should run **after becoming ready**, design proper background execution and readiness/monitoring policies; merely annotating @Async to “push work out of startup” lets the runner return before actual work completes.

## 8. Notes on @Transactional and external dependencies

Startup work often needs to query a database or call a remote API. The clean structure is **runner orchestrates, service executes business logic**, with transactions placed at the service boundary and invoked through a Spring-managed bean:

~~~java
@Service
class SeedService {
    @Transactional
    public void seedIfMissing() {
        // Read and write data inside a transaction.
    }
}

@Component
class SeedRunner implements ApplicationRunner {
    private final SeedService seedService;

    SeedRunner(SeedService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seedIfMissing();
    }
}
~~~

This snippet **only illustrates responsibility separation**, since imports, real business logic, repositories, and a transaction manager must be added to run. With Spring Boot 3.x, @Service is **org.springframework.stereotype.Service**, and @Transactional is **org.springframework.transaction.annotation.Transactional**.

Having the runner call **seedService.seedIfMissing()** via an injected bean lets Spring AOP's transaction proxy apply when transaction management is configured. **Self-invocation** within the same class, especially inside @PostConstruct, can bypass the proxy and omit the expected transaction.

When seeding at startup:

- Enforce **idempotency**: if multiple instances start simultaneously, a naive “check then insert” has a race condition; use unique constraints, upserts, or proper locking/coordination.
- Define **timeouts**, bounded retries, and behavior when external dependencies are unavailable.
- Separate **schema migration** (Flyway/Liquibase) from **data seeding**.
- If a run fails halfway, consider transaction boundaries or checkpoints so retries do not corrupt data.
- Do not assume a runner runs only once **across the whole cluster**: it runs each time the corresponding SpringApplication starts, including every Pod/replica and every restart.

## 9. Correctness of readiness and startup failures

Per Spring Boot, after refresh comes **ApplicationStartedEvent**, and liveness is published as valid. After all runners finish, **ApplicationReadyEvent** fires and readiness is published as **ACCEPTING_TRAFFIC**. This has operational significance:

| Case | Operational signal |
| --- | --- |
| Mandatory singleton's @PostConstruct throws | Context refresh may fail; runners do not run |
| Mandatory runner throws | Startup fails; does not reach ready on success path |
| Runner spawns async task and returns immediately | Spring Boot may report ready while async task still runs |
| HTTP request fails after ready | Usually a runtime error, not automatically a startup failure |
| SmartLifecycle starts consumer early | Consumer may pull work before readiness unless gated |
| Runner runs indefinitely | Delays startup/readiness; may trigger startup probe or orchestrator timeouts |

**Do not treat readiness as an all-powerful business health test.** Readiness reflects an instance's published capacity to receive traffic; systems also need health probes, metrics, and per-request/event error handling.

If a startup runner could block indefinitely on an external dependency, bound it with timeouts and define a fail-fast or degraded-mode strategy based on product contracts. Do not use infinite retries that leave the process stuck in “starting” forever.

## 10. Scenario matrix: which hook to choose?

| Requirement | Appropriate extension point | Reason |
| --- | --- | --- |
| Validate a bean's configuration properties | Constructor or @PostConstruct | Local invariant; fail fast when the bean is created |
| Build a small lookup table from injected fields | @PostConstruct or initMethod | Fast internal state preparation |
| Use services and repositories to warm a mandatory cache | ApplicationRunner | Context already refreshed; coordinates before ready |
| Process CLI options like --name=value | ApplicationRunner | Provides parsed ApplicationArguments |
| Pass raw String[] array to a custom parser | CommandLineRunner | Receives raw arguments |
| Verify all singleton handlers initialized | SmartInitializingSingleton | After non-lazy singleton pre-instantiation |
| Start a consumer with explicit start/stop | SmartLifecycle | Manages running state and shutdown |
| Log when context finishes refreshing | ContextRefreshedEvent | Observes context; mind multiple contexts |
| Emit telemetry after startup runners | ApplicationReadyEvent | Marks successful startup past runners |
| Versioned DB schema migrations | Flyway/Liquibase | Provides ordering, history, and versioning |
| Periodic work after service is running | Scheduler/@Scheduled or managed worker | Not a one-time startup task |
| Seed data only once across an entire cluster | Dedicated migration/job or distributed coordination | Runners on each replica do not guarantee cluster-wide once execution |

## 11. Common pitfalls

**Mistake 1 — Putting multi-minute tasks into @PostConstruct.** It runs while BeanFactory is still instantiating beans; it can hold singleton creation locks, slow refresh, or conflict with other beans. Move whole-context work to a runner if it must complete before ready.

**Mistake 2 — Calling complex beans from a constructor.** Other beans may still be initializing, proxies are not yet formed, and resources are not ready. Keep constructors concise and focused on object invariants.

**Mistake 3 — Thinking @PostConstruct runs after the app is ready.** It runs when the bean is created. For regular non-lazy singletons, that is **before** ApplicationStartedEvent and runners; for lazy beans, it can be much later.

**Mistake 4 — Using @Order to order all bean callbacks.** @Order works for ordering runners; it does not replace the dependency graph and @DependsOn for bean creation, nor does it shift @PostConstruct relative to ready.

**Mistake 5 — Runner launches async work and returns immediately, assuming warmup finished.** Spring Boot only knows `run(...)` returned. If async results are required for readiness, await completion with a timeout, handle errors, or control readiness explicitly.

**Mistake 6 — Runner exits the entire JVM with System.exit(0) on failure.** Orchestrators may record a false success. Let mandatory exceptions fail startup and return proper exit codes in CLI apps.

**Mistake 7 — Using @PostConstruct to call an @Transactional method on the same bean.** Self-invocation bypasses the Spring proxy; the transaction may not activate. Move business logic to a separate service and call it from a runner.

**Mistake 8 — A runner opens background resources with no shutdown path.** Runners are an entry point and do not provide stop() or destroy(). Use a resource-owning bean with @PreDestroy, destroyMethod, or SmartLifecycle.

**Mistake 9 — Treating a runner like a cron job that runs once system-wide.** Every restart/replica can re-run it; implement idempotency, constraints, and coordination.

**Mistake 10 — Using ApplicationReadyEvent to run a very long task.** Synchronous listeners can delay completion or block the event dispatch thread; choose runners for mandatory startup work and separate background mechanics for non-mandatory work.

**Mistake 11 — Initializing beans by relying on class scan order.** Component scanning is not a business execution schedule. Declare explicit dependencies and use @Order for runners.

## 12. Design checklist

Before choosing a callback, answer:

1. Is the task **tied to one bean** or **coordinating multiple services**?
2. Does it need to wait until **ApplicationContext refresh finishes**?
3. Must the task **finish before accepting traffic**?
4. Does it need **command-line arguments**, transactions, repositories, or remote APIs?
5. How long will it take, and are **timeouts/retries** and error reporting defined?
6. Does it need **continuous start/stop** or resource release on shutdown?
7. Can the work re-run on every replica/restart? Is **idempotency** guaranteed?
8. If an exception occurs, should it **fail startup**, run degraded, or log a background error?

A sound rule of thumb is: **bean init to make the bean valid; runners to finish app-level work before readiness; SmartLifecycle to manage continuously running components**.

## 13. Self-check

**Question 1:** A bean must check that its `"timeoutMs"` property is greater than 0 after injection. What should you choose?  
**Answer:** Constructor if the value is already passed at creation, or @PostConstruct/initMethod to validate that bean's own invariant.

**Question 2:** Three services must be called to preload a critical cache before the service accepts HTTP requests. What should you choose?  
**Answer:** ApplicationRunner; use @Order/Ordered if multiple runners need ordering.

**Question 3:** What is the main difference between ApplicationRunner and CommandLineRunner?  
**Answer:** ApplicationRunner receives parsed ApplicationArguments; CommandLineRunner receives `String... args`.

**Question 4:** A runner starts a Future to load data, does not wait for the Future to finish, and returns. Is the cache guaranteed ready before ready?  
**Answer:** No. The runner finished at the method level while async work may still be running.

**Question 5:** If @PostConstruct throws an exception, will runners run?  
**Answer:** If it is a mandatory non-lazy singleton during refresh, startup fails and runners do not run. For a lazy bean created later, failure timing depends on when the bean is requested.

**Question 6:** To have a Kafka consumer start and stop in a controlled way, should you use a runner or SmartLifecycle?  
**Answer:** SmartLifecycle or the existing listener container mechanism is better suited for long-lived lifecycles.

**Question 7:** Two runners have @Order(10) and @Order(20); which runs first?  
**Answer:** The order-10 runner, regardless of whether they implement ApplicationRunner or CommandLineRunner.

**Question 8:** A runner calls its own @Transactional method via `this.doWork()`; is the transaction guaranteed to work?  
**Answer:** No. Self-invocation typically bypasses the AOP proxy; call an injected service bean with proper transaction management.

**Remember:** Choose **bean callbacks** to ensure validity and local state of a single bean during its initialization; choose **ApplicationRunner/CommandLineRunner** for application-level work after refresh and before ready. Order runners with @Order/Ordered, avoid long startup tasks in bean callbacks, and always define clear behavior for errors, timeouts, restarts, and shutdown.

### References

- [Spring Boot — SpringApplication and Application Events](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot 3.3 — CommandLineRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html)
- [Spring Framework — Bean lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — SmartInitializingSingleton API](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html)
