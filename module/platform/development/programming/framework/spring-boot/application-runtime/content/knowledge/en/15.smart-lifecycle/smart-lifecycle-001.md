# Distinguishing Bean Initialization from Component Startup

## 1. Two phrases that sound similar but belong to different lifecycles

When Spring Boot creates a bean, learners often assume that "bean initialized" means "component started". That is **incorrect** for components that have their own operational lifecycle, such as a message consumer, a dedicated scheduler, a streaming connection, a watcher, a socket listener, a worker thread, or a connector that needs to start and stop.

Three ideas need to be separated:

1. **The bean is created and initialized**: Spring invokes the constructor/factory method, injects dependencies, and runs eligible initialization callbacks such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or a custom init method.
2. **The component starts operating (`start`)**: an object implementing the `Lifecycle`/`SmartLifecycle` contract transitions to the running state; it may begin polling, register a consumer, activate a background process, or start a waiting resource.
3. **The application completes startup (`ready`)**: Spring Boot finishes refreshing the context, publishes `ApplicationStartedEvent`, invokes runners, publishes `ApplicationReadyEvent`, and then announces readiness accordingly.

**Object initialization does not automatically mean a background service is already active.** Conversely, if a `@PostConstruct` method calls `start` itself, that is **behavior explicitly written by the developer**, not two Spring phases naturally coinciding.

The main extension point of this lesson is **`SmartLifecycle`**: Spring Framework uses it to manage starting and stopping components with an operational lifecycle when the `ApplicationContext` refreshes or closes. This lesson applies to **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**.

> **Remember:** "bean initialized" answers *has the object been set up by the container?*; "component started" answers *has it been asked to run?*; "application ready" answers *has the entire application passed the required startup steps?*.

## 2. Bean initialization: the object setup phase

The typical initialization process of a singleton bean:

```text
Bean definition is discovered
    |
    +--> Create instance: constructor / @Bean factory method
    +--> Inject dependencies into constructor/field/setter
    +--> Certain Aware callbacks and BeanPostProcessor
    +--> @PostConstruct
    +--> InitializingBean.afterPropertiesSet()
    +--> custom init-method (if configured)
    +--> BeanPostProcessor after initialization
    |
    +--> Bean is ready to be provided to other beans
```

The exact order can be affected by `BeanPostProcessor`s, proxies, factory beans, and the dependency graph. The general meaning is: **initialization finalizes the configuration of the instance**. It can verify internal conditions, normalize values, and build in-memory data structures, rather than automatically triggering a long-running operational process.

A simple bean:

```java
@Component
class RuleCache {

    private Map<String, String> rules;

    @PostConstruct
    void initialize() {
        rules = Map.of("level", "basic");
    }

    String find(String key) {
        return rules.get(key);
    }
}
```

This is an **illustrative snippet**; it requires importing `Map`, `Component`, and `PostConstruct`. After initialization, `RuleCache` is already usable, but it does not have a "worker" that needs to start or stop. Not every bean needs `SmartLifecycle`.

### 2.1. Does @PostConstruct automatically run a second time on context.start()?

**No.** `@PostConstruct` belongs to the **instance initialization** process. `context.start()` is a runtime lifecycle signal for eligible `Lifecycle` components; it does not recreate all beans and does not repeat `@PostConstruct` by default.

### 2.2. Initialized does not guarantee remote dependencies are "ready"

A bean can be initialized successfully while an external system is still disconnected, a message-receiving worker has not been enabled yet, or a runner has not finished preloading data. Successful injection only means dependencies in the **bean object graph** have been resolved by Spring; it does not prove all those dependencies have started running and are ready for business work.

This is an important reason to distinguish **object configuration** from **activating operation**.

## 3. What contracts are Lifecycle and SmartLifecycle?

Spring Framework defines the `Lifecycle` interface:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

This is an abbreviated signature for learning, not code to redeclare in your application. The methods describe the ability to start/stop a component and check its running state.

`SmartLifecycle` extends `Lifecycle` and `Phased` to support:

- **`isAutoStartup()`**: should it auto-start when the context refreshes?
- **`getPhase()`**: coordinate the start/stop order relative to other lifecycle components.
- **`stop(Runnable callback)`**: support an asynchronous stop process; the container waits for the callback to complete within the timeout/phase.

API model:

```java
public interface SmartLifecycle extends Lifecycle, Phased {
    default boolean isAutoStartup() {
        return true;
    }

    default int getPhase() {
        return DEFAULT_PHASE;
    }

    default void stop(Runnable callback) {
        stop();
        callback.run();
    }
}
```

This is **code explaining the main contract**, not a complete copy for recreating the Spring interface. In Spring 6.1, the API defaults are:

- `isAutoStartup()` returns **`true`**.
- `DEFAULT_PHASE` is **`Integer.MAX_VALUE`** (very late on startup, very early on shutdown relative to smaller phases).
- `stop(Runnable)` calls `stop()` and then the callback by default; implementations with asynchronous stopping should override it appropriately.
- `getPhase()` is part of `Phased`, with a default provided by `SmartLifecycle`.

**Common pitfall:** A plain `Lifecycle` **is not automatically started just because the context refreshes**, whereas a `SmartLifecycle` with `isAutoStartup() == true` is automatically started by `LifecycleProcessor` during refresh.

## 4. Where does SmartLifecycle sit in SpringApplication?

Abbreviated timeline for Boot 3.3:

```text
SpringApplication.run(args)
    |
    +--> prepare Environment and ApplicationContext
    +--> load bean definitions
    +--> refresh(context)
    |       +--> create/wire non-lazy singletons
    |       +--> @PostConstruct / bean init methods
    |       +--> finishRefresh / LifecycleProcessor.onRefresh()
    |                +--> auto-start SmartLifecycle with isAutoStartup=true
    |                +--> handle startup phases and depends-on
    |       +--> ContextRefreshedEvent
    |
    +--> ApplicationStartedEvent
    +--> publish LivenessState.CORRECT
    +--> ApplicationRunner / CommandLineRunner
    +--> ApplicationReadyEvent
    +--> publish ReadinessState.ACCEPTING_TRAFFIC
    +--> SpringApplication.run(...) returns

When closing the context along the normal path:
    |
    +--> LifecycleProcessor.onClose()
    |       +--> stop running SmartLifecycle beans
    |       +--> run shutdown phases in reverse order
    |       +--> wait for stop(Runnable callback) within timeout
    +--> @PreDestroy / DisposableBean / destroyMethod for eligible beans
    +--> close context
```

**Order takeaway:** For an auto-starting singleton `SmartLifecycle` bean, Spring completes that bean's **initialization callbacks** before calling its `start()`. `start()` usually occurs **during context refresh**, which is **before** `ApplicationStartedEvent` and before runners.

Do not overgeneralize that every lazy bean in the entire application is created before every `start()`; that is a simplified picture of non-lazy singletons and components processed by refresh. With custom scopes, lazy initialization, or a custom lifecycle processor, the creation timing of other beans may differ.

### 4.1. Do not equate start() with ApplicationStartedEvent

Despite sharing the word "start", these are two fundamentally different events:

| Mechanism | Executed on | Typical milestone | Who is responsible |
| --- | --- | --- | --- |
| `@PostConstruct` | A Spring-managed bean instance | When the bean is initialized | Bean container / post-processor |
| `SmartLifecycle.start()` | A lifecycle component | During refresh if auto-start, or manual start call | `LifecycleProcessor` or caller |
| `ApplicationStartedEvent` | Entire SpringApplication | After refresh, **before runners** | Spring Boot |
| `ApplicationRunner.run()` | A startup task bean | After started event | Spring Boot |
| `ApplicationReadyEvent` | Entire SpringApplication | After runners complete successfully | Spring Boot |
| `@PreDestroy` | Destruction of eligible bean | When the bean is destroyed | Bean container |

A `SmartLifecycle.start()` returning does not prove the whole system is ready. If it merely launches a background thread and returns immediately, Boot's readiness does not automatically wait for that thread to become fully operational.

### 4.2. start() is not a second constructor

Do not call `start()` to patch unfinished constructor logic. You should separate responsibilities:

- **Constructor / dependency injection:** receive required dependencies.
- **@PostConstruct:** validate/normalize and prepare state quickly, without unnecessary long I/O.
- **start:** transition to the active state and begin consuming/registering/subscribing to resources.
- **stop:** stop accepting work, and close or release resources owned by the component.
- **@PreDestroy:** final cleanup; do not treat it as a replacement for phased stop and coordinated shutdown.


## 5. Runnable Java 17+ example: initialized before start, started before runner

The goal of this experiment is to observe **one** `SmartLifecycle` bean, with no network logic, to see the exact milestones. The code explicitly prints the constructor, `@PostConstruct`, `start()`, started event, runner, ready event, `stop(Runnable)`, and `@PreDestroy`.

### 5.1. Gradle project configuration

Create a project with Gradle Wrapper, Java 17+, and Spring Boot 3.3.13. File `build.gradle`:

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

File `settings.gradle`:

```groovy
rootProject.name = 'smart-lifecycle-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Choose non-web mode so the process exits automatically after `try-with-resources` closes the context. This is a lifecycle demonstration; no web server or database is needed.

### 5.2. Complete Java code

Create file `src/main/java/com/example/lifecycle/LifecycleStagesApplication.java`:

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LifecycleStagesApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LifecycleStagesApplication.class, args)) {

            DemoWorker worker = context.getBean(DemoWorker.class);
            System.out.println("07 main: running=" + worker.isRunning());
        }
    }

    @Bean
    DemoWorker demoWorker() {
        return new DemoWorker();
    }

    @Bean
    ApplicationRunner checkWorker(DemoWorker worker) {
        return args -> System.out.println(
                "05 runner: running=" + worker.isRunning());
    }

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("04 ApplicationStartedEvent");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("06 ApplicationReadyEvent");
    }

    static final class DemoWorker implements SmartLifecycle {
        private volatile boolean running;

        DemoWorker() {
            System.out.println("01 constructor");
        }

        @PostConstruct
        public void initialize() {
            System.out.println("02 @PostConstruct");
        }

        @Override
        public void start() {
            if (running) {
                return;
            }
            running = true;
            System.out.println("03 SmartLifecycle.start");
        }

        @Override
        public void stop() {
            if (!running) {
                return;
            }
            running = false;
            System.out.println("08 SmartLifecycle.stop");
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                // Important: notify LifecycleProcessor that stop has finished.
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
            return 100;
        }

        @PreDestroy
        public void cleanup() {
            System.out.println("09 @PreDestroy");
        }
    }
}
```

**This is a complete and consistent Java file**: the class containing `main`, bean factory, runner, event listeners, and the class implementing `SmartLifecycle` are all in one file. The `jakarta.annotation` annotations are supported by the Spring Boot starter.

In the program:

- `DemoWorker` is created by the `@Bean` method; the constructor runs before `@PostConstruct`.
- `SmartLifecycle` auto-starts during refresh because `isAutoStartup()` returns `true`.
- `getPhase() == 100` is the worker's phase level. Because there is only **one worker created by this code**, the phase number here does not change the stdout order; it illustrates where to declare order when there are multiple components.
- `ApplicationStartedEvent` occurs after refresh; the runner observes `worker.isRunning() == true`.
- `ApplicationReadyEvent` occurs after the runner.
- `try-with-resources` closes the context upon leaving the block. Spring invokes `stop(Runnable)` and then the bean's destruction callback.
- `@PreDestroy` is not the same callback as `stop()`. It prints a separate line to clarify the two phases.

### 5.3. Run commands

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

The lines **printed directly by the Java code**, with the configuration above:

```text
01 constructor
02 @PostConstruct
03 SmartLifecycle.start
04 ApplicationStartedEvent
05 runner: running=true
06 ApplicationReadyEvent
07 main: running=true
08 SmartLifecycle.stop
09 @PreDestroy
```

Gradle and the runtime may emit their own logs; compare only the numbered lines from the program. This is the **timeline of the non-web example**, not a claim that every listener/bean registered by auto-configuration logs at the same milestones.

If line `02` appears without line `03`, you cannot yet conclude the component has started. If line `03` is present but the runner has not finished, you cannot conclude the application is ready. If shutdown shows line `08`, the `stop` callback has been handled; `09` shows that bean destruction is still a separate step.

### 5.4. Switching from auto-start to manual start

Change the implementation:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

This is a **change to one method in the file above**, not a standalone Java file. With this change, the context still creates/initializes the bean when needed, but `LifecycleProcessor.onRefresh()` **does not automatically call `DemoWorker.start()`**. The runner will observe `running=false`, unless other code explicitly starts it.

To enable it manually **after `SpringApplication.run` returns**, call:

```java
DemoWorker worker = context.getBean(DemoWorker.class);
worker.start(); // or context.start() if you want to start eligible Lifecycle beans
```

Very important note: in the modified experiment, the runner already ran **before** `main` resumed with the context; if the runner requires the component to be active, manual start in `main` is **too late**. In that case, you need a different bootstrap structure or `isAutoStartup=true`.

### 5.5. What if start() throws?

Suppose you replace the body of `start()` with:

```java
@Override
public void start() {
    throw new IllegalStateException("Cannot start the worker");
}
```

This is an **illustrative replacement snippet**. Because `SmartLifecycle.start()` runs during refresh, an escaping exception can cause **context refresh to fail** and Boot to enter startup failure. In that case, `ApplicationStartedEvent`, runners, and `ApplicationReadyEvent` **are not milestones reached** along the success path.

Thus, an error in `start()` and an error in `ApplicationRunner.run()` occur at different places: a runner fails after refresh, whereas a start failure can prevent refresh from completing. In both cases, do not silently swallow errors of required conditions.

### 5.6. Can a component be restarted without recreating the bean?

While the context is still active and the component properly supports repeated start/stop, you can do:

```java
DemoWorker worker = context.getBean(DemoWorker.class);
worker.stop();
worker.start();
```

This is an **illustrative snippet** in a place that already has `context` and `DemoWorker`. There is no second `@PostConstruct` call: it is still the same previously initialized instance. The `running` state changes via `stop()/start()`, illustrating the independence between **object creation** and **runtime activation**.

If a component opens resources that cannot be reopened, manual start/stop may not support restarting; this must be designed explicitly. Do not call `start()` after the context has called `close()`.


## 6. Bean initialization order is not phase order

One of the biggest misconceptions: "`getPhase() = -100` makes that bean get **created before** beans with phase `10`". **No.**

`getPhase()` is used by `LifecycleProcessor` to **coordinate start/stop** of lifecycle components. It **does not replace** constructor injection, bean dependencies, component scanning, `@DependsOn`, or bean initialization order.

Suppose we have two workers (this is an **illustrative class snippet**, not a standalone file):

```java
class DatabaseConnector implements SmartLifecycle {
    @Override public int getPhase() { return 100; }

    // The start, stop, isRunning, ... methods must be fully implemented.
}

class MessageConsumer implements SmartLifecycle {
    @Override public int getPhase() { return 200; }

    // The start, stop, isRunning, ... methods must be fully implemented.
}
```

If both are auto-starting lifecycle beans in the same context, under normal ordering:

```text
START: DatabaseConnector(100) -> MessageConsumer(200)
STOP : MessageConsumer(200)   -> DatabaseConnector(100)
```

This makes sense if the consumer needs the connector to be **active** before subscribing. Conversely, stopping the consumer first prevents generating more requests to a connector that is shutting down.

**However:** before `start` is called, both beans may already have been created/initialized according to the dependency graph and singleton pre-instantiation. Do not use `phase` to predict whether constructor or `@PostConstruct` logs run earlier or later.

### 6.1. Phase values: lower starts first, higher stops first

| Phase | Startup | Shutdown |
| --- | --- | --- |
| `-100` | Earlier than 0 | Later than 0 |
| `0` | After -100, before 100 | After 100, before -100 |
| `100` | After 0, before 200 | Before 0, after 200 |
| `200` | After 100 | Before 100 |
| `Integer.MAX_VALUE` | Usually very late | Usually very early |

In Spring Framework 6.1:

- `SmartLifecycle.DEFAULT_PHASE == Integer.MAX_VALUE`.
- Plain `Lifecycle` beans (not implementing `SmartLifecycle`) are treated as **phase 0** in overall coordination.
- Avoid using `Integer.MIN_VALUE` or `MAX_VALUE` yourself without a specific reason, as framework components may use those special levels.
- Beans with the **same phase** have no guaranteed relative order; do not write code that depends on an accidental order observed in logs.

**This is not `@Order`.** `@Order` is typically used to sort listeners, runners, collection injection, or other extension points. `SmartLifecycle` uses `getPhase()` for start/stop phases.

### 6.2. @DependsOn can take precedence over getPhase

Spring Framework specifies that an explicit `depends-on` dependency relationship takes precedence in lifecycle order: **the dependent bean is started after its dependency, and stopped before its dependency**, even if the declared phases conflict.

Conceptual example:

```java
@Bean("source")
SourceWorker source() {
    return new SourceWorker();
}

@Bean("consumer")
@DependsOn("source")
ConsumerWorker consumer() {
    return new ConsumerWorker();
}
```

This snippet only illustrates bean methods; it requires defining the two classes and importing `@Bean`/`@DependsOn`. If `ConsumerWorker` depends on `SourceWorker`, Spring must preserve the lifecycle relationship according to dependency order; `getPhase()` should not be used to break that constraint.

It is best to **express the dependency explicitly** when the consumer genuinely requires the source. When there is no explicit bean dependency and only a business startup order, use phases carefully.

### 6.3. Do not assume a stable order within the same phase

If two consumers both have phase 100, the execution order within the same phase is **not a contract you can rely on**. It can depend on the number of beans, registration order, or version changes.

When one consumer strictly needs to wait for another consumer to start, separate their phases or declare a dependency, and more importantly **verify that it is actually ready**, not merely that `start()` has been called.

### 6.4. @Lazy does not reliably prevent SmartLifecycle auto-start

`SmartLifecycle` participates in the auto-start mechanism during refresh. `LifecycleProcessor` may have to fetch the bean to call `isAutoStartup()/start()`, so the `@Lazy` flag has **limited effect** on SmartLifecycle beans. Spring Framework documentation explicitly notes that SmartLifecycle beans are still typically initialized during startup.

If you want to avoid auto-activating a component, set `isAutoStartup() == false` and **review how the bean is initialized/consumed**, rather than merely adding `@Lazy` and hoping the worker will not run.

## 7. stop(), stop(Runnable), and @PreDestroy are not the same

### 7.1. Situations where stop is called

- `context.stop()`: signals lifecycle components in the context to stop **without destroying all beans**; `context.start()` can be called again if the context is still valid.
- `context.close()`: closes the context; the lifecycle processor stops running components and then Spring handles destruction callbacks for eligible beans.
- Direct `worker.stop()`: called directly on the object; you are responsible for ensuring the component and other dependencies are not stopped out of order.
- `@PreDestroy`: destruction callback when a bean is destroyed; **not automatically equivalent** to a properly phased `stop()` command.

With `SmartLifecycle`, when `DefaultLifecycleProcessor` performs a graceful stop, it uses **`stop(Runnable callback)`**, not necessarily calling the no-argument `stop()` directly. If you override `stop(Runnable)`, invoke the real stop logic and report completion properly.

### 7.2. Why must callback.run() be called?

A component may need to stop asynchronously: send a queue close signal, wait for consumer acks, drain in-flight messages, and only then release connections. Spring waits for `stop(Runnable callback)` to signal that stopping has finished, within the phase timeout.

Correct pattern for callback responsibility:

```java
@Override
public void stop(Runnable callback) {
    workerExecutor.execute(() -> {
        try {
            stopReceivingNewTasks();
            awaitInFlightTasks();
            releaseOwnedResources();
        } finally {
            running = false;
            callback.run();
        }
    });
}
```

This snippet is **illustrative only**; it requires the `workerExecutor`, `running`, `stopReceivingNewTasks` fields/methods and the remaining methods to be defined; it is not a standalone runnable class. In real code, you must also handle the case where `workerExecutor.execute(...)` rejects the task: if scheduling fails, you still must handle cleanup/failure and **complete the callback exactly once**. Do not call `callback.run()` immediately upon submitting the task if stopping has not finished.

**Failing to call the callback** causes the lifecycle processor to wait until the phase timeout expires, making shutdown slow or unclean. **Calling the callback too early** makes the container believe the component has stopped while tasks are still running, which can cause its dependencies to be closed prematurely.

### 7.3. Timeout per shutdown phase

Spring Framework 6.1's `DefaultLifecycleProcessor` has a per-shutdown-phase timeout (default **30 seconds** in this API). Spring Boot 3.3 allows configuring it:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This is a **wait time per phase**, not an absolute timeout guaranteeing the entire process exits within 20 seconds. If there are multiple phases, or if the container or orchestrator imposes additional limits, total shutdown time may differ.

In Kubernetes, you need to coordinate this duration with `terminationGracePeriodSeconds`, reverse proxies, and queue/consumer thresholds. A `SIGKILL` or crash gives Java no opportunity to complete graceful callbacks.

### 7.4. Separate destruction callback after stop

For normal singleton beans, `@PreDestroy`/`DisposableBean.destroy()`/custom destroy methods run when the container actually destroys the bean, not on every `context.stop()`. During a controlled shutdown, lifecycle stop usually runs before bean destruction. However, in some **startup failures or refresh failures**, it cannot be guaranteed that every stop notification runs in the normal sequence; destruction callbacks may still run to clean up already-created resources.

A prototype bean **does not automatically have its destruction callback called by Spring when the context closes** merely because its class implements `SmartLifecycle`. Components requiring centralized lifecycle management should generally be registered as **singletons** with a clear owner.

## 8. isAutoStartup(), manual start, and running state

### 8.1. Meaning of isAutoStartup

- `true` (default): the lifecycle processor will auto-start the component during refresh, respecting phase/depends-on.
- `false`: do not auto-start solely because of refresh; the component is designed to be activated by an explicit signal later.
- A bean **being created/initialized** does not mean `isRunning() == true`. 

`isRunning()` must reflect the actual state managed by the implementation.

If a system has a feature that only runs when enabled by an operator, `isAutoStartup=false` is an option, but there must be a clear place calling `start()` when conditions are met.

### 8.2. start() must have an idempotent contract

In a practical implementation:

```java
@Override
public synchronized void start() {
    if (running) {
        return;
    }
    connect();
    beginConsuming();
    running = true;
}
```

This is an **illustrative pattern**; `running`/`connect`/`beginConsuming` must be defined. Do not set `running=true` too early if `connect()` can throw: startup monitors will misread the state. If `beginConsuming()` is async, `start()` returning does not guarantee the consumer is ready; an additional wait/ack/readiness mechanism is needed.

In multi-threaded components, `volatile` or proper synchronization is necessary for state. `isRunning()` should not return an arbitrary boolean unrelated to actual operational capability.

### 8.3. stop() must also tolerate repeated calls

Stop can be requested by the context, a caller, or a shutdown hook. The implementation should consider:

- If already stopped, do not close resources a second time unsafely.
- If currently stopping, coordinate calls and callbacks instead of reporting a false stop.
- Do not let a cleanup exception prevent the callback from being invoked.
- Do not wait indefinitely when a dependency is unresponsive.
- Do not release resources **borrowed** from another bean when the component is not the owner.

A lifecycle component holding a network handle should be designed to close in proper order: stop accepting new tasks, process in-flight work within a deadline, unregister the consumer, release owned resources, update state, and invoke the callback.

## 9. When to use @PostConstruct, SmartLifecycle, or ApplicationRunner?

| Need | Typically appropriate extension point | Reason |
| --- | --- | --- |
| Validate/normalize fields, build pure in-memory cache | Constructor / `@PostConstruct` | Tied to bean initialization |
| Enable a consumer/poller on context refresh | `SmartLifecycle` | Provides start/stop, phase, auto-start, shutdown callback |
| Coordinate multiple workers needing ordered startup | `SmartLifecycle.getPhase()` + dependency | Phase increases on start, decreases on stop |
| Worker enabled only upon user/admin command | `SmartLifecycle(isAutoStartup=false)` or dedicated API | Does not auto-activate on refresh |
| Check required conditions after beans are created | `ApplicationRunner`/`CommandLineRunner` | Runs after refresh, before ready |
| Need a trigger when Boot startup completes | `ApplicationReadyEvent` | Event fired after runners succeed |
| Attach destroy operation when singleton is released | `@PreDestroy` or `@Bean(destroyMethod=...)` | Bean cleanup, not phased start/stop |
| Expose accurate readiness when background worker isn't ready | `ApplicationAvailability`/readiness health | Returning from start doesn't prove background init finished |
| Orchestrate multi-step business flow with rollback/retry | Explicit service/workflow | Phase does not replace transaction orchestration |

### 9.1. Choose SmartLifecycle for long-running workers

Example object:

```text
MessageConsumer bean
    |
    +--> @PostConstruct: validate queue name, prepare options
    +--> start: subscribe to broker / begin polling
    +--> isRunning: reflect consumer state
    +--> stop(callback): pause intake, drain inflight, unsubscribe
    +--> @PreDestroy: release any remaining final resources
```

This is where `SmartLifecycle` shines: starting and stopping alongside the context lifecycle and coordinating by dependencies. Avoid running an infinite consumer loop directly inside a constructor or `@PostConstruct`, which would hang bean creation.

### 9.2. Choose a runner for one-time bootstrap

An `ApplicationRunner` is suitable when you need to load mandatory reference data or verify conditions after refresh before readiness. It **has no separate stop/restart contract**. If a runner starts a background service and leaves it running for the lifetime of the application, ask whether that service needs `SmartLifecycle` so it can be stopped properly.

### 9.3. Choose events when you only need to observe a milestone

`ApplicationStartedEvent` and `ApplicationReadyEvent` are `SpringApplication` events, not low-level commands to start/stop individual components. They are suitable for lightweight telemetry/notifications, not as a replacement for dependency lifecycle ordering.

## 10. How do liveness/readiness relate to SmartLifecycle?

In Boot 3.3.x, after refresh and auto-starting eligible `SmartLifecycle` beans, Boot publishes `ApplicationStartedEvent`; then runners are called; accepting readiness is published after `ApplicationReadyEvent`.

**However:** an implementation of `start()` might only submit a task to an executor and return, while the task has not actually connected to the broker yet. Spring may consider the start phase complete, and Boot still proceeds to ready after the runners. **Do not confuse "start() method returned" with "service is serving properly".**

If actual readiness depends on a background worker:

- Design `start()` to wait for a readiness signal with a deadline when appropriate; fail fast if required conditions are not met.
- Or use a runner that waits for the worker's startup result before ready.
- Or use readiness health/state reflecting real conditions, avoiding routing traffic to an instance that cannot serve yet.
- Record async errors in metrics/logs/alerts and provide a mechanism to revoke readiness if the worker loses operational capability after startup.
- Do not mark liveness as BROKEN just because an external dependency is temporarily down if a restart will not fix the outage.

**Phase is not a readiness gate**. It only coordinates the order of start/stop calls between components.

## 11. Common errors and how to check

| Symptom / assumption | Possible cause | How to handle |
| --- | --- | --- |
| "Having `@PostConstruct` means the worker is running" | Init does not automatically trigger `SmartLifecycle.start` | Check `start()` and `isRunning()` |
| "`ApplicationStartedEvent` is the component's callback" | Boot event after refresh, not a bean's start method | Distinguish the three layers: bean/component/application |
| "`getPhase(-100)` makes the bean constructor run first" | Phase orders start/stop, not initialization | Use the dependency graph and proper bean lifecycle |
| "`@Order(10)` controls SmartLifecycle phase" | Confusing `@Order` with `SmartLifecycle.getPhase` | Override `getPhase()` for start/stop |
| "Two workers with the same phase definitely run by bean name" | Ties do not guarantee order | Use explicit phases/dependencies |
| "`SmartLifecycle` defaults to phase 0" | `SmartLifecycle`'s default is `Integer.MAX_VALUE` | Explicitly override phase by design |
| "`@Lazy` definitely prevents SmartLifecycle auto-creation" | LifecycleProcessor may instantiate it for auto-start | Consider `isAutoStartup=false` |
| "`isAutoStartup=false` yet runner still sees worker active" | Other code called `start()` | Inspect logs/callers and state |
| "Using `@PreDestroy` instead of `stop(Runnable)` is enough" | Loses phase coordination and async stop signaling | Implement stop according to the contract |
| "`stop(Runnable)` doesn't need the callback" | LifecycleProcessor may wait until timeout | Invoke callback after stop completes |
| "Calling callback right after submitting shutdown job is done" | Job may not have actually stopped yet | Invoke callback once the worker has stopped |
| "`Context.stop()` is the same as `context.close()`" | stop does not destroy beans; close triggers destruction | Choose the operation matching the lifecycle need |
| "`SmartLifecycle.start()` returning means app is ready" | Runners and async warmup may still be incomplete | Track ready/readiness |
| "Bean start fails, Boot always still publishes ApplicationStartedEvent" | Start error during refresh can abort startup | Check refresh stacktrace and `ApplicationFailedEvent` |
| "stop callback always runs even when JVM receives SIGKILL" | No opportunity for graceful shutdown | Design timeouts and recovery |
| "Prototype SmartLifecycle is auto-destroyed by Spring on context close" | Prototypes are not tracked for destruction like singletons | Use singleton for long-running components or a dedicated owner |

### 11.1. Checklist for debugging when a component actually becomes active

1. Log constructor/`@PostConstruct`/`start()`/`stop(Runnable)`/`@PreDestroy` with the bean/component name.
2. Read the component's `isAutoStartup()` and `getPhase()`.
3. Check `@DependsOn`/dependency graph if phase does not yield the expected order.
4. Check if `@Lazy`, scope, or a custom bean factory alters when the bean is created.
5. Cross-reference with `ContextRefreshedEvent`, `ApplicationStartedEvent`, runners, and `ApplicationReadyEvent`.
6. On shutdown, measure whether `stop(Runnable)` actually invokes the callback or waits for timeout.
7. If there is a background thread, measure actual state and readiness signals instead of relying on an early boolean flag.
8. On error in `start()`, look for the root cause of the refresh/startup failure, not just the wrapper exception.
9. In a web application, observe the readiness health group and the moment the port starts accepting traffic.
10. On unclean shutdown, inspect per-phase wait time, resource ownership, and executor behavior.
11. Do not put tokens, passwords, or sensitive payloads into lifecycle logs.

## 12. Self-check

**Question 1.** Does `@PostConstruct` running mean `SmartLifecycle.start()` has also run?

**Answer:** No. Bean initialization and component startup are two different phases. If auto-start is enabled, `start()` is called after initialization during refresh.

**Question 2.** When Spring Boot publishes `ApplicationStartedEvent`, have auto-starting `SmartLifecycle` beans generally been called already?

**Answer:** Yes, along the normal successful refresh path. However, that does not guarantee async tasks they started are truly ready if `start()` returned too early.

**Question 3.** Does `getPhase() = -100` make a bean's constructor run before beans with phase 100?

**Answer:** No. Phase coordinates start/stop, not bean initialization order.

**Question 4.** If A has phase 10 and B has phase 20, both auto-starting, in what order do startup and shutdown occur?

**Answer:** Startup A then B; shutdown B then A, unless an explicit dependency relationship must take precedence.

**Question 5.** If a `SmartLifecycle` does not override `isAutoStartup()` and `getPhase()`, what are the defaults?

**Answer:** `isAutoStartup() == true` and `getPhase() == Integer.MAX_VALUE` in Spring Framework 6.1.

**Question 6.** If `isAutoStartup() == false`, does context refresh automatically call `start()`?

**Answer:** No, per the auto-start contract. The bean may still be created/initialized; a caller can start it manually or use the context lifecycle.

**Question 7.** Is it dangerous for `stop(Runnable)` to invoke the callback before async stopping finishes?

**Answer:** Yes. The container may stop a dependency before the worker stops using it. Invoke the callback right when stopping has finished.

**Question 8.** Why not just use `@PreDestroy` to coordinate stopping multiple consumers?

**Answer:** `@PreDestroy` is a destruction callback; it does not provide the phased start/stop protocol or async callback coordination of `SmartLifecycle`.

**Question 9.** Does `context.stop()` cause Spring to invoke `@PostConstruct` again on `context.start()`?

**Answer:** No. This is a runtime state change on existing instances; it does not recreate beans.

**Question 10.** If `start()` throws an exception, can you expect `ApplicationStartedEvent` and runners to keep running as in a successful startup?

**Answer:** You should not expect that. An error during refresh auto-start can make refresh fail, causing Boot to handle startup failure before the started/runner/ready milestones.

**Question 11.** Why is `@Lazy` not enough to stop a `SmartLifecycle` from auto-starting?

**Answer:** `LifecycleProcessor` may have to instantiate it to determine and perform auto-start; the default `isAutoStartup() == true` is the relevant factor to address.

## 13. Takeaways and references

- **Initialization:** constructor/injection/`@PostConstruct`/init methods prepare the **bean object**.
- **Runtime start:** `SmartLifecycle.start()` activates the **component**, usually during refresh if auto-start is enabled.
- **Boot started/ready:** **application-level milestones** after refresh and after runners, not identical to individual components.
- **Ordering:** smaller `getPhase()` values start earlier; shutdown runs in reverse order. Explicit `depends-on` can override phase. Do not use `@Order` to infer phase.
- **Spring 6.1 defaults:** `SmartLifecycle.isAutoStartup() == true` and default phase `Integer.MAX_VALUE`.
- **Clean stop:** `stop(Runnable)` must notify the callback **after** the component actually stops; destruction callbacks like `@PreDestroy` are a separate step.
- **Async readiness:** `start()` returning does not prove background work is ready. Appropriate timeouts, readiness states, and error handling are required.

Official documentation:

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html), especially `DEFAULT_PHASE`, `isAutoStartup()`, and `stop(Runnable)`.
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html), `onRefresh()`, `onClose()`, phase order, and timeouts.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html), lifecycle callbacks and SmartLifecycle sections.
- [Spring Boot 3.3 — SpringApplication and Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), distinguishing started/runner/ready.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html), `server.shutdown` and `spring.lifecycle.timeout-per-shutdown-phase`.

In practice, when asking whether a worker "has started yet?", clarify whether you are asking about **bean initialized**, **`SmartLifecycle.isRunning()`**, **background work actually ready**, or **the entire `SpringApplication` past ready**. These four things can be observed at different milestones.
