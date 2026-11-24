# SmartLifecycle.getPhase and Startup Ordering from Low to High Phase

## 1. Understanding the problem

A Spring Boot application often has multiple long-lived components: connections to background services, processors, message consumers, schedulers, or request-accepting adapters. They may depend on one another: infrastructure must be operating before the worker, and the worker must be prepared before the consumer; when stopping, new work must stop arriving before shutting down the worker and infrastructure.

Spring Framework's **`SmartLifecycle.getPhase()`** lets you describe the **start/stop order across lifecycle beans within the same ApplicationContext**.

Core rules:

- **Startup:** **lower** phases start first, higher phases start later.
- **Shutdown:** **higher** phases stop first, lower phases stop later.
- **Same phase:** there is no contract guaranteeing order between beans.
- **Explicit `depends-on` relationships:** take precedence over phase ordering if the two conflict.

Three-component example:

| Component | getPhase() | Start | Stop |
| --- | ---: | --- | --- |
| Infrastructure | -100 | First | Last |
| Worker | 0 | Second | Second |
| Consumer | 100 | Last | First |

Using phases creates an understandable flow: **open infrastructure → open worker → accept work**; on shutdown, **stop accepting work → stop worker → close infrastructure**.

**Do not think of phase as a time delay.** `getPhase()` returns an integer used for grouping, not milliseconds to wait or CPU priority.

## 2. What does SmartLifecycle provide?

Spring Framework has two foundational interfaces:

- **Lifecycle** provides `start()`, `stop()`, and `isRunning()`.
- **Phased** provides `getPhase()`.

**SmartLifecycle extends Lifecycle, Phased** and adds `isAutoStartup()` and `stop(Runnable callback)`. Viewed structurally:

~~~text
Lifecycle:
  start()
  stop()
  isRunning()

Phased:
  getPhase()

SmartLifecycle extends Lifecycle, Phased:
  isAutoStartup()
  stop(Runnable callback)
~~~

Meaning of each method:

| Method | Responsibility |
| --- | --- |
| start() | Bring the component into an appropriate active state |
| stop() | Stop operation per the Lifecycle contract |
| isRunning() | Reflect whether the component is currently running |
| getPhase() | Provide relative ordering during start/stop |
| isAutoStartup() | Allow automatic start on context refresh |
| stop(Runnable callback) | Stop and notify the lifecycle processor when stopping completes |

`SmartLifecycle` is a mechanism for **managing component lifecycles inside a Spring container**, not a distributed lock or Kubernetes process manager. Each `ApplicationContext` orders only its own beans; two Pods have two separate containers and there is no cluster-wide ordering from `getPhase()` alone.

## 3. What values does getPhase() accept?

`getPhase()` returns an **int**, in the range **Integer.MIN_VALUE to Integer.MAX_VALUE**. Negative numbers, 0, positive numbers, or non-contiguous gaps can all be used.

~~~text
phase -1000 -> starts very early in the relative group
phase  -100 -> starts after -1000
phase     0 -> starts after -100
phase   100 -> starts after 0
phase  1000 -> starts after 100
~~~

When stopping, the order reverses:

~~~text
phase  1000 -> stops first
phase   100 -> stops next
phase     0 -> stops next
phase  -100 -> stops next
phase -1000 -> stops last
~~~

Choose consistent value ranges and document them internally if you have many components. There is no need to overuse `Integer.MIN_VALUE` or `Integer.MAX_VALUE` for every bean, because the framework may have its own lifecycle phases and `SmartLifecycle`'s default phase is already very high.

**Special default values:**

- `SmartLifecycle.DEFAULT_PHASE` is **Integer.MAX_VALUE**.
- `SmartLifecycle.getPhase()` returns `DEFAULT_PHASE` by default if the implementation does not override it.
- `SmartLifecycle.isAutoStartup()` returns **true** by default.
- A **plain `Lifecycle`**, if not also implementing `SmartLifecycle`/`Phased`, is treated as being in **phase 0** when the lifecycle processor orders it.

This is a common source of confusion: **a `SmartLifecycle` that does not override `getPhase()` is not in phase 0, it is in `Integer.MAX_VALUE`**. Therefore it typically starts later than `SmartLifecycle` beans with smaller phases and stops earlier than them.

A plain `Lifecycle` bean is not automatically auto-started on refresh merely because it has effective phase 0. Distinguish participating in lifecycle start/stop commands from `SmartLifecycle`'s special auto-start mechanism.

## 4. Who calls start() and when?

**DefaultLifecycleProcessor** is Spring Framework's default component coordinating lifecycles inside `ApplicationContext`. When the context refreshes, the lifecycle processor inspects `SmartLifecycle` beans with **`isAutoStartup() = true`**, determines phases and dependencies, and invokes `start()` accordingly.

Abbreviated Spring Boot sequence:

~~~text
SpringApplication.run(args)
        |
  Create ApplicationContext
        |
  Refresh ApplicationContext
        |
  Initialize normal singletons
        |
  LifecycleProcessor.onRefresh()
        |
  SmartLifecycle.start() from low -> high phase
        |
  Finish refresh
        |
  ApplicationStartedEvent
        |
  ApplicationRunner / CommandLineRunner
        |
  ApplicationReadyEvent
        |
  ReadinessState.ACCEPTING_TRAFFIC
~~~

What matters is that **SmartLifecycle auto-starts during refresh, normally before runners**. A high phase must not be taken as a signal that the consumer will wait for `ApplicationRunner` to finish. If a Kafka/RabbitMQ listener container has `autoStartup=true`, it can start polling messages before a runner finishes warming up caches.

If a consumer must wait for a mandatory startup task, use **`isAutoStartup=false`**, the container lifecycle API, pause/resume mechanisms, or a readiness gate—not merely a high phase number.

## 5. Ordering between beans in the same phase

Suppose two `SmartLifecycle` beans both return phase 10. They belong to the **same phase group**. Spring Framework guarantees no specific order between them.

Do not rely on:

- Alphabetical bean names.
- Class ordering inside a source file.
- Component scan discovery order.
- `@Bean` declaration positions inside a `@Configuration` class.
- Observing a fixed order in one run.

If B genuinely needs A to have started already:

1. Put A in a lower phase than B when the relationship is group-level.
2. Declare an explicit dependency, such as `@DependsOn`, if B must start after A.
3. Or use a coordinator component that invokes steps in sequence and checks actual completion state.

Phase only determines the **order of `start()` calls**; it does not automatically guarantee that asynchronous threads spawned by `start()` have finished their work.

## 6. depends-on relationships take precedence over phase

In Spring, when **B depends-on A**, A must start before B, and B must stop before A. That relationship holds even when `getPhase()` values suggest the opposite order.

Intentional conflicting example:

~~~text
A: StorageLifecycle    phase = 100
B: ConsumerLifecycle   phase = -100
B depends-on A
~~~

Looking only at phase, B has a smaller number and might appear to start first. However, because B depends on A, the actual lifecycle order is:

~~~text
START A
START B

STOP B
STOP A
~~~

Illustrative syntax snippet:

~~~java
@Component("storage")
class StorageLifecycle implements SmartLifecycle {
    // getPhase() method returns 100.
    // Other Lifecycle methods must be implemented.
}

@Component("consumer")
@DependsOn("storage")
class ConsumerLifecycle implements SmartLifecycle {
    // getPhase() method returns -100.
    // Other Lifecycle methods must be implemented.
}
~~~

**This is structural pseudocode**, not two complete Java classes, because required methods and imports are omitted.

In real designs, choose phases **aligned with dependencies**, avoiding deliberately creating two conflicting rules. Use `depends-on` when it is a direct, critical dependency, rather than trying to deduce everything from phase numbers.

## 7. getPhase() and @Order solve different problems

**getPhase()** is used by the lifecycle processor to order `SmartLifecycle` beans.

**@Order/Ordered** is typically used to sort `ApplicationRunner`, `CommandLineRunner`, or the order of certain lists/listeners in Spring contexts that support it.

Example:

~~~java
@Order(-100)
@Component
class MessageConsumer implements SmartLifecycle {
    @Override
    public int getPhase() {
        return 100;
    }

    // Other required methods.
}
~~~

This is **incomplete illustrative code**, meant solely to compare the two mechanisms. When `DefaultLifecycleProcessor` coordinates `SmartLifecycle`, this bean participates in **phase 100**; it does not automatically move to phase -100 because of `@Order`.

Pitfalls to avoid:

- `@Order(-100)` on a runner **does not make the runner run before `ApplicationStartedEvent`**; runners still sit after refresh.
- `@Order` on a `SmartLifecycle` **does not replace `getPhase()`**.
- `getPhase()` **does not order runners**.
- A phase-100 `SmartLifecycle` can still start before all runners, because lifecycle auto-start occurs during refresh.

## 8. Complete example: start low-to-high, stop high-to-low

Try a **Spring Boot 3.3.x, Java 17+** project with three `SmartLifecycle` beans. They use phases -100, 0, and 100 and print logs on start/stop.

### 8.1. File structure

~~~text
phase-order-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          PhaseOrderDemo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'phase-order-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
~~~

The project requires JDK 17+, a compatible Gradle version, and plugins/dependencies downloadable or cached.

### 8.2. Self-contained Java file

Place everything in **src/main/java/demo/PhaseOrderDemo.java**:

~~~java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class PhaseOrderDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(PhaseOrderDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_AFTER_RUN");
        }
    }

    @Bean
    NamedLifecycle infrastructure() {
        return new NamedLifecycle("INFRA", -100);
    }

    @Bean
    NamedLifecycle worker() {
        return new NamedLifecycle("WORKER", 0);
    }

    @Bean
    NamedLifecycle inputConsumer() {
        return new NamedLifecycle("INPUT", 100);
    }

    @Bean
    ApplicationRunner verifyRunner(
            @Qualifier("infrastructure") NamedLifecycle infrastructure,
            @Qualifier("worker") NamedLifecycle worker,
            @Qualifier("inputConsumer") NamedLifecycle inputConsumer) {
        return args -> {
            boolean allRunning = infrastructure.isRunning()
                    && worker.isRunning()
                    && inputConsumer.isRunning();

            System.out.println("RUNNER_ALL_RUNNING=" + allRunning);

            if (!allRunning) {
                throw new IllegalStateException("Lifecycle not started");
            }
            if (args.containsOption("fail-runner")) {
                throw new IllegalStateException("Demo runner failure");
            }
        };
    }
}

@Component
class StartupSignals {

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("EVENT_STARTED");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("EVENT_READY");
    }
}

final class NamedLifecycle implements SmartLifecycle {
    private final String label;
    private final int phase;
    private volatile boolean running;

    NamedLifecycle(String label, int phase) {
        this.label = label;
        this.phase = phase;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public synchronized void start() {
        if (!running) {
            running = true;
            System.out.println("START_" + label + " phase=" + phase);
        }
    }

    @Override
    public synchronized void stop() {
        if (running) {
            running = false;
            System.out.println("STOP_" + label + " phase=" + phase);
        }
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
}
~~~

Why this is a **valid Java example**:

- Only **PhaseOrderDemo** is a public class; the filename matches.
- The other two classes are package-private, so they can reside in the same Java file and `demo` package.
- `@Bean` creates three `NamedLifecycle` beans, each with a distinct name and phase.
- `@Qualifier` ensures the runner injects the exact three beans even though they share the `NamedLifecycle` type, regardless of whether the compiler preserves parameter names.
- `SmartLifecycle` is completely implemented: `start()`, `stop()`, `isRunning()`, `getPhase()`, `isAutoStartup()`, `stop(Runnable)`.
- `WebApplicationType.NONE` keeps the app from opening a web server and lets `main` explicitly close the context, showing shutdown order clearly.

### 8.3. Running the program

With Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If you do not have the wrapper yet but have a compatible Gradle installed:

~~~bash
gradle bootRun
~~~

The messages **printed by the code itself** appear in order on a successful run:

~~~text
START_INFRA phase=-100
START_WORKER phase=0
START_INPUT phase=100
EVENT_STARTED
RUNNER_ALL_RUNNING=true
EVENT_READY
MAIN_AFTER_RUN
STOP_INPUT phase=100
STOP_WORKER phase=0
STOP_INFRA phase=-100
~~~

Spring Boot/Gradle logs may interleave, so do not assert on the entire console output. In this example with no conflicting `depends-on` relationships and three distinct phases, **START** lines always appear in ascending phase order; **STOP** lines appear in descending phase order.

Analysis:

1. **START_INFRA** runs first because -100 is smallest.
2. **START_WORKER** runs next at phase 0.
3. **START_INPUT** runs last in this phase group at 100.
4. **EVENT_STARTED** appears after context refresh.
5. The runner runs only afterward and sees all three running.
6. **EVENT_READY** appears when the runner finishes successfully.
7. `main` closes the context via `try-with-resources`; shutdown stops Input before Worker before Infra.

**No `Thread.sleep` is needed for ordering.** Phase coordinates the method call order regardless of CPU speed. However, note: the sample code uses synchronous `start()` and sets `running=true` directly inside `start()`, rather than loading dependencies asynchronously.

### 8.4. Testing the runner-failure branch

Run:

~~~bash
./gradlew bootRun --args="--fail-runner"
~~~

Lines printed by the program before the exception occurs:

~~~text
START_INFRA phase=-100
START_WORKER phase=0
START_INPUT phase=100
EVENT_STARTED
RUNNER_ALL_RUNNING=true
~~~

The runner throws **IllegalStateException("Demo runner failure")**. **EVENT_READY** and **MAIN_AFTER_RUN** do not appear along the successful startup path. Spring Boot enters startup failure handling and closes the context if it was built; already-running lifecycle beans are typically stopped when the context closes. Failure log/cleanup details may interleave; do not treat failure-branch stdout as an immutable exact string.

The experiment shows: **SmartLifecycle auto-starts before runners**. If a runner later fails, readiness is not reached yet lifecycle components may already have opened resources, so proper shutdown matters.

## 9. isAutoStartup(): toggling start on refresh

`SmartLifecycle` has the method:

~~~java
@Override
public boolean isAutoStartup() {
    return true;
}
~~~

In Spring Framework 6.1, `SmartLifecycle`'s default is true. If changed to **false**:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

then the lifecycle processor does not automatically call that component's `start()` during context refresh under the `SmartLifecycle` auto-startup mechanism. You can call **`start()` manually** at a designed point or start the context lifecycle via the appropriate API.

Example of a consumer needing to wait for a preloaded cache:

~~~java
@Component
class ConsumerStarter implements ApplicationRunner {
    private final CacheWarmupService warmup;
    private final MessageConsumer consumer;

    ConsumerStarter(CacheWarmupService warmup, MessageConsumer consumer) {
        this.warmup = warmup;
        this.consumer = consumer;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmup.preload();
        consumer.start();
    }
}
~~~

**This snippet only illustrates code organization** and will not run standalone because `CacheWarmupService` and `MessageConsumer` are not defined. The consumer must have a real start/stop mechanism and `autoStartup=false`.

When **calling `consumer.start()` directly**, you activate one specific component rather than asking `DefaultLifecycleProcessor` to start all other beans by `getPhase()`. Do not equate phase ordering with a single manual call.

**Do not use a huge phase to substitute for `autoStartup=false`.** A `SmartLifecycle` with phase `Integer.MAX_VALUE` can still auto-start during refresh, **before `ApplicationRunner`**.

## 10. getPhase() does not wait for async work spawned by start()

A component might implement:

~~~java
@Override
public void start() {
    executor.submit(this::connectToRemoteService);
    running = true;
}
~~~

This is illustrative code; `executor`, `connectToRemoteService`, and `running` must be defined in the class.

In that case, `start()` returns right after **submitting the task**, while the real connection may still be establishing. A higher-phase bean may have its `start()` called by Spring before the lower-phase bean's task finishes.

Therefore, distinguish:

- **Call order:** `start(A)` is called before `start(B)`.
- **Actual ready state:** whether A has connected, initialized data, or verified dependencies.

If B strictly requires A, you can:

1. Make `start(A)` wait synchronously until A is ready with a timeout.
2. Have B start only after a reliable ready signal from A completes.
3. Move mandatory warmup into a runner and then start the consumer with `autoStartup=false`.
4. Use an explicit state machine and health/readiness checks when work cannot block startup.

Do not use **`Thread.sleep`** as a synchronization mechanism. A lower phase starting earlier is not a promise that all its child tasks have completed.

## 11. stop(Runnable callback) and reverse-order shutdown

`SmartLifecycle` has two stop forms:

~~~java
void stop();
void stop(Runnable callback);
~~~

When `DefaultLifecycleProcessor` manages shutdown of a `SmartLifecycle`, **`stop(Runnable callback)`** matters because it signals that the component has finished stopping so the next phase can proceed.

Synchronous stop pattern:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

The example in section 8 uses this pattern. The callback is always invoked after attempting `stop()` so the lifecycle processor is not left waiting forever. A serious implementation also needs error reporting and resource state verification; the callback must not be used to **claim a successful stop while resources are still running**.

With asynchronous shutdown, the callback must be invoked **when closing work truly finishes**, not right when a close command is merely submitted.

Pseudocode example:

~~~java
@Override
public void stop(Runnable callback) {
    client.stopAsync().whenComplete((unused, failure) -> {
        try {
            if (failure != null) {
                log.error("Async stop failed", failure);
            }
            running = false;
        } finally {
            callback.run();
        }
    });
}
~~~

Here `client`, `log`, and `running` are hypothetical components, not a standalone runnable class. In a real implementation, you must also handle **`stopAsync()` itself throwing an exception before returning a `Future`**, ensuring the callback is invoked exactly once per contract and avoiding leaving unclosed resources behind.

**High-to-low stop order** lets the system stop consumers first, allow workers to finish in-flight tasks, and only then close connection pools or low-phase infrastructure.

### Timeout per shutdown phase

Spring Boot 3.3 supports:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

This is the **timeout per phase during close**, not a wait interval between starts and not a total JVM time limit. If a component fails to invoke the callback or takes too long to stop, shutdown may wait for the entire phase budget. Define internal I/O timeouts inside components and an active stop policy.

Note: **`kill -9`, power loss, or a JVM crash** can bypass shutdown callbacks. Do not treat graceful shutdown as the sole mechanism protecting data or releasing external leases.

## 12. How should you choose phase values?

There is no fixed number set for all applications. You can design layered ranges for readability:

| Layer | Example phase | Start | Stop |
| --- | ---: | --- | --- |
| Foundational infrastructure that must outlive everything | -200 | Earliest | Latest |
| Registry or foundational connections | -100 | After infrastructure | Before infrastructure |
| Data-processing worker | 0 | After connections | Before connections |
| Message-receiving consumer | 100 | After worker | Before worker |
| Adapter allocating/accepting new work | 200 | Last | First |

This is an **illustrative convention**, not mandatory Spring Boot values. Infrastructure libraries such as web servers, message listener containers, or schedulers may carry their own phases; inspect their specific API/config before picking numbers for custom components.

Better questions to ask than picking random numbers:

- **Who needs to exist first?** Assign a lower phase or declare an explicit dependency.
- **Who must stop accepting work first?** Assign a higher phase than the resources it uses.
- **Who must stay running during shutdown to help finish tasks?** Assign a lower phase than the consumer.
- **Does a resource already have a Spring-owned lifecycle?** No need to wrap everything in a custom `SmartLifecycle`.
- **Do two tasks only have a one-time business ordering before ready?** Use a runner or coordinator; do not force `getPhase` to solve a runner's problem.

## 13. When start() or refresh encounters an error

Suppose:

~~~text
Infrastructure phase -100: start OK
Worker         phase    0: start OK
Consumer       phase  100: start FAILED
~~~

If `start()` throws an exception, context refresh can fail, and `SpringApplication` never reaches runners or ready. However, do not assume every stop callback will run identically to a normal graceful shutdown when **refresh is interrupted**.

Cleanup principles:

1. Resources already managed by the container must have proper closing lifecycles.
2. If `start()` **opens a resource and then fails mid-initialization**, the component must clean up immediately in `try/catch` or `try/finally` of the allocation step itself.
3. Do not use static initializers or self-spawned threads assuming the lifecycle processor will always close them on early startup failure.
4. Significant exceptions must propagate so `SpringApplication` detects startup failure, instead of catching and faking `running=true`.
5. For non-transactional external resources, ensure idempotency and compensation on restart.

Pseudocode:

~~~java
@Override
public void start() {
    Resource resource = openResource();
    try {
        configure(resource);
        running = true;
    } catch (RuntimeException | Error failure) {
        try {
            resource.close();
        } catch (Exception closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
~~~

`Resource`, `openResource`, and `configure` are hypothetical business APIs. The point is to **clean up partial setup yourself**, without waiting for `@PreDestroy` or `stop()` when the object has not reached a fully managed state.

For runner errors occurring **after refresh has finished**, auto-starting `SmartLifecycle` beans may already be running and will need shutting down when Spring Boot handles the failure. Therefore, test both failures inside `start()` and failures inside runners.

## 14. How does SmartLifecycle differ from nearby hooks?

| Mechanism | Timing | What is it for? |
| --- | --- | --- |
| Constructor | Object creation and invariants | Local state, validating input dependencies |
| `@PostConstruct`/`initMethod` | Bean initialization | Preparing the bean's own state |
| `SmartLifecycle.start()` | During context lifecycle, usually on refresh | Starting long-lived, phased components |
| `SmartLifecycle.stop(Runnable)` | When lifecycle processor closes/stops context | Ordered shutdown, supporting async shutdown |
| `ApplicationRunner` | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` | Startup tasks that must finish before ready |
| `CommandLineRunner` | Same stage as `ApplicationRunner` | Startup handling with raw arguments |
| `ApplicationStartedEvent` | After context refresh | Observing the started milestone |
| `ApplicationReadyEvent` | After runners | Observing the successful startup milestone |
| `@PreDestroy` | When the bean is destroyed | Releasing resources per bean lifecycle |

**SmartLifecycle does not automatically replace these hooks.** If you only need fast property validation, constructor/`@PostConstruct` is cleaner. If you only need to preload a cache before ready, a runner is easier to understand. If a consumer runs continuously and needs phased start/stop, `SmartLifecycle` or the framework's existing listener container fits.

## 15. Relationship between phase and readiness

In the normal Spring Boot sequence:

~~~text
Context refresh
    |
SmartLifecycle auto-start
    |
ApplicationStartedEvent
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Therefore, a `SmartLifecycle` consumer with `autoStartup=true` can start receiving messages right during refresh, while HTTP readiness is not yet accepting traffic. This does not contradict the API: **phase only orders lifecycles**, whereas readiness is an operational state published by Spring Boot afterward.

If the system requires "do not process messages before warmup", choose the right mechanism: `autoStartup=false`, start from a runner after warmup, pause/resume, or check conditions before acknowledging. Handle retries, redelivery, and backpressure according to broker semantics; do not simply drop messages when not ready.

Point to remember: **an HTTP readiness probe does not automatically block Kafka/RabbitMQ consumers, schedulers, or custom threads**. If readiness is needed across multiple work sources, design conditions appropriate for each source.

## 16. Phase testing checklist

### 16.1. Start order

Capture the specific order of messages:

~~~text
START_INFRA -> START_WORKER -> START_INPUT
~~~

Do not assert on interleaved framework logs; compare only events explicitly emitted by your code.

### 16.2. Stop order

Close the context and verify:

~~~text
STOP_INPUT -> STOP_WORKER -> STOP_INFRA
~~~

Verify completion callbacks in each phase and that real resources are closed.

### 16.3. Two beans in the same phase

Have two `SmartLifecycle` beans both return `getPhase()=10` and verify **no test asserts a fixed order between them**. If ordering is actually needed, fix the design with dependencies or distinct phases.

### 16.4. Depends-on opposing phase

B depends on A, yet B's phase is lower than A's phase. Verify A still starts before B and B stops before A. After confirming the principle, align phases for readability.

### 16.5. Auto-start false

Verify the bean does not start on refresh. Then call `start()` from a runner or coordinator; verify `isRunning()` changes appropriately.

### 16.6. Async start

Have `start()` only submit a `Future` and return; demonstrate that a higher phase can start before the `Future` finishes. Then add a real barrier, timeout, or readiness gate.

### 16.7. Shutdown and failure

Test slow `stop(Runnable)`, phase timeouts, failure when `start()` opens partial resources, runner failure after refresh, stopping from Kubernetes/IDE, and resource leaks. Never assume `kill -9` will run callbacks.

## 17. Common mistakes

**1. "Higher phase starts first."** False. Lower phase starts first.

**2. "Stop also goes low to high."** False. Stop goes high to low.

**3. "Phase is a number of seconds of delay."** False. It is group ordering.

**4. "SmartLifecycle defaults to phase 0."** False. `SmartLifecycle.DEFAULT_PHASE = Integer.MAX_VALUE`.

**5. "A plain Lifecycle auto-starts just like SmartLifecycle."** No. Auto-start on refresh is for `SmartLifecycle` with `isAutoStartup=true`.

**6. "`@Order` on a component replaces `getPhase`."** False when `DefaultLifecycleProcessor` orders lifecycle beans.

**7. "Two beans in the same phase always follow class names."** False. Internal order is not guaranteed.

**8. "`Depends-on` is unrelated to stop order."** False. Dependent stops before dependency.

**9. "Putting a consumer at a very high phase is enough to wait for runners."** False. Auto-start still runs during refresh.

**10. "`start()` returning means async tasks finished."** False if it merely submitted the task.

**11. "`stop(Runnable)` can skip calling the callback when stopping finishes."** False. The callback must signal completion.

**12. "Just call `callback.run()` right after sending the async stop command."** False. The callback must represent actual completion of stopping.

**13. "`@Lazy` definitely prevents `SmartLifecycle` from being instantiated at startup."** Not guaranteed. Auto-start discovery limits the effect of lazy-init.

**14. "`getPhase` synchronizes startup across Pods in a cluster."** False. Scope is each individual `ApplicationContext`.

**15. "A refresh error definitely cleans up all resources like graceful shutdown."** Cannot be assumed; partially created resources need local cleanup.

**16. "Use `getPhase` to sort runners."** False. Runners use `@Order`/`Ordered` or a coordinator as needed.

## 18. Self-check questions

**Question 1:** A has phase -50, B has phase 0, C has phase 200. In what order do they start?  
**Answer:** A → B → C.

**Question 2:** When closing the context, what is the stop order?  
**Answer:** C → B → A.

**Question 3:** What is the default phase of a `SmartLifecycle` that does not override `getPhase`?  
**Answer:** `Integer.MAX_VALUE` in Spring Framework 6.1.

**Question 4:** What does `isAutoStartup()` return by default?  
**Answer:** `true`.

**Question 5:** Are two `SmartLifecycle` beans with the same phase 0 guaranteed to run in bean name order?  
**Answer:** No.

**Question 6:** B depends on A, yet B has phase -100 and A has phase 100. Which bean starts first?  
**Answer:** A, because `depends-on` takes precedence.

**Question 7:** Does `@Order(1)` on an `ApplicationRunner` make it run before `SmartLifecycle.start()`?  
**Answer:** No. Runners sit after context refresh during normal startup.

**Question 8:** A consumer must wait for a cache preloaded in a runner. Is setting `getPhase=Integer.MAX_VALUE` enough?  
**Answer:** Not yet. Use `autoStartup=false` and controlled start after warmup, or an equivalent gate.

**Question 9:** Why must `stop(Runnable)` call the callback after stopping?  
**Answer:** `LifecycleProcessor` needs the completion signal to coordinate shutdown phases.

**Question 10:** Does `start(A)` being called before `start(B)` guarantee an async connection opened by A is already ready?  
**Answer:** No. You need a real ready signal or a bounded wait.

**Question 11:** Is `timeout-per-shutdown-phase=20s` used for the wait time between starts?  
**Answer:** No. It bounds stop time per phase.

**Question 12:** Do five Kubernetes replicas coordinate a shared `getPhase`?  
**Answer:** No; each `ApplicationContext` manages its own ordering independently.

**Question 13:** If `start()` opened a connection and threw an exception partway through, who must clean it up?  
**Answer:** The component must ensure local cleanup of partially created resources; do not rely solely on lifecycle callbacks.

**Conclusion:** **`getPhase()` defines `SmartLifecycle` startup order from low to high phase and shutdown order from high to low phase**. Auto-starting `SmartLifecycle` beans normally run during refresh, before runners; the same phase has no guaranteed order; explicit dependencies take precedence. When implementing, align phases with dependencies, verify true readiness, implement `stop(Runnable)` per contract, and test both startup failures and shutdown.

### References

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Boot — Application Events and Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
