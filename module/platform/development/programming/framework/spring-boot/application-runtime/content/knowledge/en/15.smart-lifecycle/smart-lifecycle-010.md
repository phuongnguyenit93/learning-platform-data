# Interaction Between SmartLifecycle, Lazy Initialization, and Closing ApplicationContext

## 1. The big picture

In Spring Boot, a single bean can simultaneously participate in the **container lifecycle**, be marked for **lazy initialization**, and own resources that must be safely stopped when `ApplicationContext` closes. These three topics are often conflated, leading to mistakes such as:

- Placing `@Lazy`, yet seeing the `SmartLifecycle` bean's constructor still run at application startup.
- Enabling `spring.main.lazy-initialization=true`, yet seeing background workers or listeners still auto-start.
- Implementing `stop()`, yet on context close seeing resources destroyed before asynchronous work finishes.
- Adding `@PreDestroy`, without understanding how it differs from `SmartLifecycle.stop(Runnable)`.
- Setting `phase`, yet stopping a dependency before stopping the component using it.

**Core conclusion:** `SmartLifecycle` is used to **coordinate when a component starts and stops**, especially components that must auto-run on context refresh and stop in a controlled order. `@Lazy` and `spring.main.lazy-initialization=true` primarily control **when bean instances are created**. `ApplicationContext.close()` coordinates **closing the context**, including publishing events, stopping lifecycle components, and then destroying eligible singletons.

**Most important misconception:** Spring Framework's official documentation notes that `SmartLifecycle` beans **are still typically initialized at context startup**, even when the bean definition has lazy-init, because the auto-start mechanism needs to discover and process lifecycle beans. Thus `@Lazy` has **very limited effect** on `SmartLifecycle`. Never use `@Lazy` as a guarantee that a `SmartLifecycle` will stay uncreated or inactive until the first request.

### 1.1. Diagram of the three layers of responsibility

```text
SpringApplication.run(...)
          |
          v
 ApplicationContext.refresh()
          |
          +-- Create required beans
          |     |-- Normal eager singletons
          |     |-- Infrastructure beans
          |     +-- SmartLifecycle beans may be initialized
          |         even if marked @Lazy
          |
          +-- LifecycleProcessor.onRefresh()
          |     +-- find eligible lifecycle components
          |     +-- order by phase and dependencies
          |     +-- call start() for auto-start SmartLifecycle
          |
          +-- ContextRefreshedEvent
          |
          v
  ApplicationStartedEvent / runners / ApplicationReadyEvent
          |
          | Application running
          |
          v
 ApplicationContext.close()
          |
          +-- ContextClosedEvent
          +-- LifecycleProcessor.onClose()
          |     +-- stop SmartLifecycle in reverse phase order
          |     +-- wait for stop(Runnable callback) to finish
          |         within configured bounds
          +-- Destroy singleton instances
          |     +-- @PreDestroy
          |     +-- DisposableBean.destroy()
          |     +-- other destroyMethod (if any)
          |
          v
 Context closes
```

Abbreviated diagram of the major stages. Specific order also depends on implementations and application type. It does not imply every bean is created on refresh, or that every `SmartLifecycle` must auto-start.

## 2. Interfaces to distinguish

### 2.1. Lifecycle

Spring Framework defines the interface:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

This is an **abbreviated signature for learning**, not a source file to recreate. `Lifecycle` describes a component's ability to be started, stopped, and report running state. By default, it does not request the bean to auto-start on context refresh via `SmartLifecycle`'s mechanism.

A `Lifecycle` bean can be started/stopped by the context via `ConfigurableApplicationContext.start()` and `stop()` when a lifecycle processor is active.

### 2.2. Phased

`Phased` provides:

```java
int getPhase();
```

The `phase` value determines relative start/stop order:

- **Start:** lower phase first, higher phase later.
- **Stop:** higher phase first, lower phase later.

If bean B uses bean A and wants A running first, give A a **lower** phase than B, unless you already declared an explicit dependency so the framework enforces the dependency rule.

### 2.3. SmartLifecycle

`SmartLifecycle` extends `Lifecycle` and `Phased`, adding two key capabilities:

```java
public interface SmartLifecycle extends Lifecycle, Phased {

    default boolean isAutoStartup() {
        return true;
    }

    default void stop(Runnable callback) {
        stop();
        callback.run();
    }

    default int getPhase() {
        return Integer.MAX_VALUE;
    }
}
```

This is a **representation of default contracts in Spring Framework 6.1**, omitting Javadoc and library details. In real code, `implements org.springframework.context.SmartLifecycle` instead of redefining this interface.

Points to understand:

1. `isAutoStartup()` returns `true` by default: eligible beans auto-start during refresh.
2. `stop(Runnable callback)` is the callback used by the lifecycle manager when stopping a `SmartLifecycle`, letting it report **when stopping has truly completed**.
3. `getPhase()` defaults to `Integer.MAX_VALUE` in Spring Framework 6.1: beans at the default phase usually start late and stop earlier than low-phase lifecycle beans.
4. `isRunning()` must reflect real state; never hardcode `true` or `false` out of convenience.
5. `start()` and `stop()` should tolerate repeated calls safely if the architecture can issue duplicate requests.

**Do not equate auto-start with lazy-init:** `isAutoStartup()` controls **whether `start()` is auto-called on refresh**; it is not a flag forcing the container **not to create an instance**.

## 3. Four milestones often confused

| Milestone | What happens | What not to conclude yet |
| --- | --- | --- |
| Bean creation | Constructor, injection, bean lifecycle callbacks processed | That the bean called `start()` and is actually running |
| `SmartLifecycle.start()` | Component transitions to active state when requested | That all runners finished or the app is ready for traffic |
| `SmartLifecycle.stop(Runnable)` | Component is asked to stop, possibly asynchronously | That all singletons have been destroyed |
| Destruction callback | `@PreDestroy`, `DisposableBean`, custom destroy method on eligible beans | That this callback itself handled all phased stop work |

A bean can be:

- **Created yet not running**: e.g., `isAutoStartup() == false`.
- **Running yet the whole app is not ready**: `start()` runs during refresh, before runners.
- **Stopped yet the instance still exists**: the context ran the stop phase without destroying singletons yet.
- **Created and never started**: can still run `@PreDestroy` when the context closes.

Proper shutdown design must account for both **stopping new intake/processing** and **releasing resources**; never conflate method names to treat both steps as one.

## 4. Why does @Lazy have limited effect on SmartLifecycle?

### 4.1. Normal lazy singleton mechanics

A regular singleton bean annotated:

```java
@Component
@Lazy
class OptionalFormatter {
    OptionalFormatter() {
        System.out.println("formatter.constructed");
    }
}
```

If no eager bean requires `OptionalFormatter`, the container can defer creating it until `getBean` or an injection/call path needs it. `@Lazy` here primarily changes **pre-instantiation** of the bean.

### 4.2. SmartLifecycle differs at bean discovery

If the class instead implements `SmartLifecycle`:

```java
@Component
@Lazy
class BackgroundReceiver implements SmartLifecycle {
    // start(), stop(), isRunning(), ...
}
```

`DefaultLifecycleProcessor` needs to identify lifecycle components that must auto-start and order them by phase. To do so, it typically needs to fetch/instantiate `SmartLifecycle` beans. Consequently **lifecycle beans typically still appear and start at startup**, even when the bean definition carries `@Lazy`.

Spring Framework 6.1's `SmartLifecycle` Javadoc states explicitly: because of auto-start capability, `SmartLifecycle` instances are typically initialized at application context startup; hence bean-definition lazy-init has very limited effect on these beans.

**Do not infer the opposite:** saying "typically initialized" is not a guarantee that every implementation or condition creates **every** such bean. There may be conditional bean registration, proxies, custom lifecycle processors, scopes, or unrefreshed contexts. Still, in a standard context, **`@Lazy` is not the right tool to keep a default `SmartLifecycle` dormant until first use**.

### 4.3. Global lazy also does not guarantee SmartLifecycle is deferred

Spring Boot allows:

```properties
spring.main.lazy-initialization=true
```

This flag applies lazy initialization broadly to eligible beans, often helping cut singleton creation time at startup. However, lifecycle infrastructure must still run; `SmartLifecycle` beans can continue to be discovered, initialized, and auto-started.

Thus in an application with global lazy:

```text
Ordinary @Lazy bean:
  May not have been created yet when SpringApplication.run() returns.

SmartLifecycle @Lazy bean:
  Typically already initialized and started during refresh.
```

It is vital to distinguish **lazy-initialization policy** from **lifecycle start policy**. The two policies do not replace each other and do not cancel each other out.

### 4.4. @Lazy at an injection point is even less of a start/stop switch

For example, a bean receiving:

```java
MyCoordinator(@Lazy BackgroundReceiver receiver) {
    this.receiver = receiver;
}
```

This is an illustrative snippet: it requires a matching `MyCoordinator` class and `BackgroundReceiver` bean, `@Lazy` import, and `receiver` field; it is not a standalone Java program.

`@Lazy` on a constructor parameter can cause the dependency to be injected via a lazy-resolution proxy. However, if `BackgroundReceiver` is a `SmartLifecycle` bean, **the lifecycle processor can still proactively create/start the target independently** during refresh. The proxy only defers resolution **through that injection path**; it does not govern the target's global lifecycle.

If the receiver must **not auto-start**, design `isAutoStartup()` and explicitly decide who/when calls `start()`; do not merely add `@Lazy` on the consumer.

## 5. isAutoStartup(): distinguishing not started from not created

By default `SmartLifecycle.isAutoStartup()` returns `true`. It can be overridden:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

This tells the lifecycle processor: **do not auto-start this bean on refresh; I will decide when to start it later**.

However:

- `isAutoStartup() == false` **is not** a promise that the constructor has not run.
- The container may still need to instantiate the bean to discover lifecycle beans or read `getPhase()`/`isAutoStartup()`.
- An eager consumer, `ApplicationRunner`, or other code can still request the bean instance.
- The bean can have `start()` called later via the lifecycle API or `context.start()` depending on configuration, once properly created and registered.
- If the bean was never running, the stop phase may handle it differently from a running bean; **destruction callbacks remain an independent responsibility**.

**Formula to remember:** `isAutoStartup=false` = *do not auto-transition to running on refresh*. It **does not mean** *no instance exists in `BeanFactory`*.

A mechanism that truly must start **on business demand** may fit better as a regular service with a `startOnDemand()` method and `@PreDestroy`/`AutoCloseable`, instead of forcing `SmartLifecycle` into a lazy model.

## 6. Phases: forward start order and reverse stop order

For independent `SmartLifecycle` beans:

| Bean | `getPhase()` | Start order | Stop order |
| --- | ---: | ---: | ---: |
| StorageConnection | -100 | 1 | 3 |
| MessageDispatcher | 0 | 2 | 2 |
| RequestReceiver | 100 | 3 | 1 |

Interpretation:

```text
START:
StorageConnection(-100)
        ↓
MessageDispatcher(0)
        ↓
RequestReceiver(100)

STOP:
RequestReceiver(100)
        ↓
MessageDispatcher(0)
        ↓
StorageConnection(-100)
```

Why stop in reverse? Because the receiver must **stop taking in more data** before the dispatcher stops; the dispatcher must finish in-flight work before storage closes.

Spring Framework specifies startup from lower to higher phases and shutdown in the reverse order. If two lifecycle components share the **same phase**, never rely on their internal order to enforce a critical dependency.

### 6.1. Explicit dependencies take precedence over phase

If bean B **depends on** bean A and the container knows that relationship, Spring requires B to start after A and stop before A, even when phase numbers suggest the opposite. Valid dependencies can be expressed via injection or bean-definition `depends-on` metadata per Spring rules.

Therefore:

- Use proper dependencies to model **resource/object** dependencies.
- Use `phase` to organize **start/stop layers**.
- Never create circular dependencies to "keep order".
- Never assume placing `@Order` on an arbitrary class is equivalent to `SmartLifecycle.getPhase()`.

### 6.2. Default phase

In Spring Framework 6.1:

- `SmartLifecycle.DEFAULT_PHASE` is `Integer.MAX_VALUE`.
- `SmartLifecycle.getPhase()` returns that value by default.
- Plain `Lifecycle` not implementing `SmartLifecycle` is treated as phase **0** for basic coordination.
- `SmartLifecycle` beans using the default phase usually **start late** and **stop early** relative to phase-0 lifecycle beans.

This is an intentional API distinction. If a receiver must start before a phase-0 component, **choose an appropriate phase** or declare the proper dependency; do not rely on which bean was constructed earlier.

## 7. The refresh sequence: when is SmartLifecycle.start() called?

In a standard `ApplicationContext`, `refresh()` executes many steps, including:

1. Preparing the environment and bean factory.
2. Loading/finalizing bean definitions and post-processing infrastructure.
3. Instantiating eligible non-lazy singletons.
4. Preparing and using `LifecycleProcessor`.
5. Calling `LifecycleProcessor.onRefresh()` to process lifecycle beans requiring auto-start.
6. Completing refresh and publishing `ContextRefreshedEvent`.

Note: this diagram is abbreviated; exact refresh sequencing in specific implementations includes additional hooks.

With Spring Boot:

```text
SpringApplication.run(...)
    |
    +-- ApplicationContext.refresh()
    |      |
    |      +-- SmartLifecycle auto-start
    |      +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    |
    +-- return ApplicationContext
```

**Therefore, `SmartLifecycle.start()` usually runs before runners and before `ApplicationReadyEvent`.** If a `SmartLifecycle` receiver opens network connections or begins consuming messages inside `start()`, that activity can begin **before Boot reports the application as ready**.

If business logic must wait for a runner to populate critical data, reorganize initialization order or add a traffic/message intake gate; never assume `ApplicationReadyEvent` always precedes `SmartLifecycle` auto-start.

## 8. Runnable Spring Boot 3.3, Java 17+ example: SmartLifecycle still runs despite lazy

This example intentionally creates **two different beans**:

- `ManagedQueue` implements `SmartLifecycle` and has `@Lazy` on the class; it defaults to auto-start.
- `OptionalCache` is just a plain `@Lazy` bean not participating in lifecycle. No consumer requests it.

Enable `spring.main.lazy-initialization=true` and observe after `SpringApplication.run(...)` finishes.

### 8.1. Project structure

```text
smart-lifecycle-lazy-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          lifecycle/
            LifecycleLazyApplication.java
    resources/
      application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'smart-lifecycle-lazy-demo'
```

`build.gradle`:

```groovy
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
```

The project needs a compatible Gradle wrapper and JDK 17+. Spring Boot 3.3.13 is used to illustrate the 3.3 line, not as a recommendation to pick an end-of-life release for new projects.

`src/main/resources/application.properties`:

```properties
spring.application.name=smart-lifecycle-lazy-demo
spring.main.web-application-type=none
spring.main.lazy-initialization=true
spring.main.banner-mode=off
logging.level.root=ERROR
```

Choosing non-web keeps the example free of an HTTP server or requests, avoiding noise while observing.

### 8.2. Complete Java code

File `src/main/java/demo/lifecycle/LifecycleLazyApplication.java`:

```java
package demo.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class LifecycleLazyApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LifecycleLazyApplication.class, args)) {

            var factory = context.getBeanFactory();

            System.out.println("main.managedCreated="
                    + factory.containsSingleton("managedQueue"));
            System.out.println("main.cacheCreated="
                    + factory.containsSingleton("optionalCache"));
            System.out.println("main.managedRunning="
                    + context.getBean(ManagedQueue.class).isRunning());
        }

        System.out.println("main.contextClosed");
    }
}

@Component
@Lazy
class ManagedQueue implements SmartLifecycle {

    private volatile boolean running;

    ManagedQueue() {
        System.out.println("managed.constructed");
    }

    @Override
    public void start() {
        if (!running) {
            running = true;
            System.out.println("managed.start");
        }
    }

    @Override
    public void stop() {
        if (running) {
            running = false;
            System.out.println("managed.stop");
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
    public int getPhase() {
        return 100;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @PreDestroy
    public void cleanup() {
        System.out.println("managed.destroy");
    }
}

@Component
@Lazy
class OptionalCache {

    OptionalCache() {
        System.out.println("cache.constructed");
    }

    @PreDestroy
    public void cleanup() {
        System.out.println("cache.destroy");
    }
}
```

All top-level classes reside in one file; only `LifecycleLazyApplication` is `public`. The two components have default bean names `managedQueue` and `optionalCache`, respectively. `@PreDestroy` is imported from `jakarta.annotation.PreDestroy`, matching Spring Boot 3.x.

### 8.3. Running the program

In a project with Gradle Wrapper:

```bash
./gradlew bootRun
```

The lines **printed by the example code itself** during a normal startup and context close, with the configuration and beans above:

```text
managed.constructed
managed.start
main.managedCreated=true
main.cacheCreated=false
main.managedRunning=true
managed.stop
managed.destroy
main.contextClosed
```

Spring Boot and Gradle may print additional messages. The lines above are the key markers; do not claim total stdout consists solely of these eight lines.

Analysis:

1. Bean `ManagedQueue` carries `@Lazy` and global lazy is also enabled, yet the lifecycle manager still needs it for auto-start, so its constructor runs at startup.
2. `ManagedQueue.start()` flips `running` to `true` before `run(...)` returns.
3. `main.managedCreated=true` reflects that the singleton instance was created.
4. Bean `OptionalCache` does not implement lifecycle and nobody requested it, so no instance exists yet: `main.cacheCreated=false`.
5. `context.getBean(ManagedQueue.class)` in the observation code **is not what caused it to be created**; it was already created during refresh. Still, in other applications, `getBean` can alter a lazy bean's state—that is why the example checks `containsSingleton` **before calling `getBean`**.
6. Leaving `try-with-resources`, the context closes; the lifecycle processor invokes `stop(Runnable)`, which calls `stop()` and then `callback.run()`.
7. After stopping, the `@PreDestroy` destruction callback runs on the `ManagedQueue` singleton.
8. `OptionalCache` was never created, so there is no instance on which to run the cache's `@PreDestroy`.

**Experiment conclusion:** lazy initialization and lifecycle auto-start are two separate contracts. `@Lazy` is not a "do not start background receiver at startup" switch.

### 8.4. What if global lazy=false is configured?

Change:

```properties
spring.main.lazy-initialization=false
```

in a **fresh run**. `OptionalCache` still carries `@Lazy` on its own bean definition, so without a consumer it may still remain uncreated. `ManagedQueue` still participates in lifecycle. The difference made by the global flag is only clearly observable if you also have a **singleton without `@Lazy`** that no consumer requests.

Therefore, do not use a demo containing only `@Lazy` beans to conclude global lazy "has no effect"; this example's goal is proving the **practical exception for `SmartLifecycle`**.

## 9. Variant: not auto-starting on refresh

Edit one method in `ManagedQueue`:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

This is a **replacement variant** for the `isAutoStartup()` method of the class in section 8, not an additional duplicate signature in the file.

Effect: the lifecycle processor **does not auto-call `start()`** for this component during that refresh.

What **must not be concluded**:

- `ManagedQueue` has definitely not been constructed.
- `managedQueue` is definitely absent from the singleton cache.
- The bean cannot be fetched via `getBean(...)`.
- The bean will auto-start the first time a consumer calls any method.

A bean in the non-running state may still already have been instantiated for the framework to evaluate lifecycle, and having an instance does not imply `isRunning()==true`.

### 9.1. Starting via an explicit API

If you want to start lifecycle components through the context:

```java
ConfigurableApplicationContext context = // context already created and refreshed
context.start();
```

This is a **conceptual snippet** and cannot compile verbatim with a `//` comment in place of an assignment expression. In a real program, `context` must be a variable obtained from `SpringApplication.run(...)` or a valid context. `context.start()` sends a start signal to lifecycle beans per context rules, not necessarily targeting just a single chosen bean.

If you want to start only one component, call it through that service's dedicated API or:

```java
ManagedQueue queue = context.getBean(ManagedQueue.class);
queue.start();
```

This snippet requires an existing `context` variable. When multiple beans need phase coordination, prefer letting `LifecycleProcessor` coordinate instead of manually calling one bean without checking dependencies.

### 9.2. Closing when a bean is not running

A `SmartLifecycle` that was created yet has `isRunning()==false` may not go through the same `stop(Runnable)` path as a running bean. However, when the **context closes**, an already-created singleton can still receive destructors such as `@PreDestroy`, `DisposableBean.destroy()`, or a custom destroy method.

Separate two questions:

- **Is it running and needing stop?** → `isRunning()` and lifecycle stop processing.
- **Does the instance own resources needing destruction?** → bean destruction and ownership.

Do not put all file/pool closing in `stop(Runnable)` and omit a destructor if the bean can be instantiated without ever starting.

## 10. stop(Runnable callback): the shutdown completion contract

On context close, `DefaultLifecycleProcessor` uses **`SmartLifecycle.stop(Runnable callback)`** to allow phased stopping even when a component needs time to finish async tasks.

Meaning of the callback:

- Spring is requesting the component to stop.
- The component can initiate stopping and **not finish immediately**.
- **Only when the component actually completes shutdown** must it invoke `callback.run()` to let the processor continue managing phases.
- If the callback is not called, the processor must wait until the timeout limit; closing can drag on or dependencies can be stopped while work is unfinished.

Spring Framework Javadoc stipulates the callback **must be invoked when stopping completes** to avoid unnecessary delays in closing the context.

### 10.1. Synchronous stop case

If stopping finishes immediately on the calling thread, a simple implementation:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop(); // actually complete stopping
    } finally {
        callback.run();
    }
}
```

This method belongs **inside a class implementing `SmartLifecycle`** with a matching `stop()`. `finally` ensures the callback is invoked even if synchronous cleanup hits an error; in production you still must log and handle errors to avoid masking root causes or reporting "stopped cleanly" when actual state is dirty.

Important point: **`stop()` in the example must actually complete stopping synchronously**. If it only sends a signal and returns, calling the callback right away falsely reports work has ended.

### 10.2. Asynchronous stop case

Suppose the receiver has its own executor and must wait for in-flight tasks. A sound design in principle:

```text
stop(callback) is called
    |
    +-- stop accepting new tasks
    +-- ask in-flight work to finish
    +-- return to lifecycle processor (if async)
                |
                v
       Prior work completes
                |
                +-- update isRunning=false
                +-- close/hand over resources per design
                +-- callback.run()
                |
                v
       Processor can end the phase
```

**Do not invoke the callback merely because a stop request was sent.** The callback means **completed**.

Illustrative method example:

```java
@Override
public void stop(Runnable callback) {
    accepting.set(false);

    completionStage.whenComplete((unused, error) -> {
        try {
            running.set(false);

            if (error != null) {
                // Log error without exposing sensitive data.
            }
        } finally {
            callback.run();
        }
    });
}
```

This snippet is **pseudocode referencing `accepting`, `running`, and `completionStage` that must be defined** in a real implementation. It shows how to connect the callback to **actual completion**, not a complete copy-pasteable template. A production component must handle already-completed stages, errors, duplicate callbacks, rejected executors, and cancellation deadlines.

### 10.3. Do not confuse stop(Runnable) with stop()

Spring Framework 6.1 Javadoc clearly states `LifecycleProcessor` invokes only the **`stop(Runnable)`** overload for `SmartLifecycle`. Therefore:

- If you only override `stop()`, the interface's default `stop(Runnable)` delegates to `stop()` and then invokes the callback.
- If you override `stop(Runnable)` yourself, **ensure the callback is invoked** at the right moment.
- Do not expect the processor to also call `stop()` after `stop(Runnable)` completes, unless your implementation calls it explicitly.

A common mistake is writing:

```java
@Override
public void stop(Runnable callback) {
    // Signal sent, but not yet finished.
    requestStop();
    // Forgot callback.run() when truly finished.
}
```

This is an **anti-pattern snippet**; `requestStop()` is hypothetical. Missing the callback can cause the processor to wait until timeout.

## 11. How does phase affect wait limits?

In Spring Boot 3.3, you can configure:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This is a timeout for **each shutdown phase**, not the maximum duration of the entire process across all configurations. With multiple phases or other work, total close time can exceed a single phase timeout.

Simple conceptual model:

```text
Phase 100:
  ReceiverA.stop(callback)  ─┐
  ReceiverB.stop(callback)  ─┤ wait for callbacks / phase timeout
                             ┘
Phase 0:
  Dispatcher.stop(callback) ── wait for callback / phase timeout

Phase -100:
  Storage.stop(callback)    ── wait for callback / phase timeout
```

If two beans share a phase and one stops asynchronously, both may be asked to stop in the same stage. **Do not assume they have a deterministic internal order** without an explicit dependency.

**Critically important:** the timeout is not a mechanism that forces resources to stop cleanly. When the wait time expires, the lifecycle processor can proceed with closing, risking destroying a dependency before a component has finished stopping. Therefore:

- Stop duration must be bounded at the component level, not relying solely on framework timeouts.
- The callback must fire exactly once upon completion.
- Have a policy for in-flight work: wait, reject, retry, checkpoint, or drop if business rules allow.
- For long-running work, combine readiness, intake halting, and early shutdown signaling.

Do not pick a tiny timeout just to make the app "shut down fast" if it holds tasks that must complete; nor pick a huge timeout without considering orchestrator deadlines.

## 12. Sequence during ApplicationContext.close()

A standard Spring context goes through major stages:

```text
ApplicationContext.close()
      |
      +-- ContextClosedEvent
      |
      +-- LifecycleProcessor.onClose()
      |      +-- evaluate running state
      |      +-- order stops in reverse phase order
      |      +-- wait for callback completion or timeout
      |
      +-- destroySingletons()
      |      +-- @PreDestroy on created beans
      |      +-- DisposableBean.destroy()
      |      +-- destroy-method
      |
      +-- close bean factory and other context resources
```

This is a high-level diagram; subclasses may add hooks or specialized infrastructure shutdown orderings.

### 12.1. Why does @PreDestroy usually run after stop?

`SmartLifecycle.stop(Runnable)` is for **stopping operation**: rejecting new messages/tasks, waiting for active workers to finish, updating state.

`@PreDestroy` is for **releasing instance resources**: closing executors, buffers, clients, connections, or file handles owned by the bean.

Separating these roles ensures resources are not closed while components are still processing.

Example:

```text
SmartLifecycle.stop(callback)
    -> accepting=false
    -> drain/finish in-flight work
    -> callback.run()

@PreDestroy
    -> executor.shutdown()
    -> close client / buffers
```

If `@PreDestroy` shuts down the executor **before** `stop` finishes, tasks waiting to complete may be lost or throw errors mid-run. Conversely, if you only clean up the executor in `stop` and the bean never started, cleanup can be missed.

### 12.2. ContextClosedEvent is not @PreDestroy

`ContextClosedEvent` announces the context is starting to close; it does not mean every lifecycle bean has stopped. An `ApplicationListener<ContextClosedEvent>` may still observe some beans running.

Do not:

- Submit new work to a queue just because `ContextClosedEvent` arrived.
- Assume every repository or client is already closed.
- Use `ContextClosedEvent` in place of stop callbacks when phase ordering must be guaranteed.

### 12.3. context.stop() does not mean context.close()

`context.stop()` coordinates stopping lifecycle components without **destroying all singletons** like `context.close()`.

Similarly:

- `context.start()` can resume starting lifecycle components.
- `context.close()` moves the context to the closed state and destroys eligible singletons.
- Do not rely on `context.start()` after a context has closed; normally a new context must be created.

If you want to pause and resume a system, design lifecycle beans for repeated start/stop with consistent state handling. If you want the application to truly shut down, close the context via the proper path.

## 13. Interaction with @PreDestroy, DisposableBean, and destroyMethod

A `SmartLifecycle` bean can also declare standard destructors:

```java
@Component
class ConsumerLifecycle implements SmartLifecycle, DisposableBean {

    // SmartLifecycle methods must be fully implemented.

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("destruction.preDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("destruction.disposableBean");
    }
}
```

This is an **illustrative snippet that does not compile standalone**, because `SmartLifecycle.start`/`stop`/`isRunning` are omitted and imports for `Component`, `DisposableBean`, and `PreDestroy` are needed. It clarifies that one bean can participate in both **lifecycle stop** and **bean destruction**.

When the context closes properly and the bean has matching callbacks:

1. Lifecycle processor asks running beans to stop.
2. Spring destroys singletons per `BeanFactory` lifecycle.
3. `@PreDestroy` is handled by the destruction-aware bean post-processor.
4. `DisposableBean.destroy()` is called if the bean implements the interface.
5. Custom destroy method, if registered and distinct from already-handled methods, typically runs after the two mechanisms above.

**The order `@PreDestroy → DisposableBean.destroy → custom destroy method` is the order within a single bean being destroyed**, not a statement that all beans in the context are destroyed by class or bean name order.

### 13.1. Do not double-close the same resource

If both `stop(Runnable)` and `@PreDestroy` call `executor.shutdownNow()` or close the same connection, the app can perform duplicate cleanup, causing errors or losing unfinished work.

Good design:

- `stop`: stop intake and coordinate draining.
- Destructor: close/cancel remaining resources, never launch new work.
- Make cleanup methods **idempotent** if they might be invoked from multiple shutdown paths.
- Never design a callback that calls business methods on a dependency that was already stopped/destroyed.

## 14. Plain lazy singletons and SmartLifecycle differ on close

Suppose two beans:

```text
LazyCache (@Lazy)
SmartReceiver (@Lazy, implements SmartLifecycle)
```

On context refresh:

- `LazyCache` may **not have been created** because no consumer requested it.
- `SmartReceiver` is **usually initialized** so the lifecycle processor knows about it and handles auto-start.

On context close:

- If `LazyCache` **was never created**, there is no instance to invoke a destructor on. `@PreDestroy` on a class is not called for a nonexistent instance.
- If `LazyCache` was already created as a singleton, the container can invoke matching destructors on close.
- If `SmartReceiver` was running, the lifecycle processor requests stop before bean destruction.
- If `SmartReceiver` was created yet not running, it may still have a destructor needing execution; do not rely solely on `stop()`.

**This is an important reason not to treat lazy as "having no lifecycle".** A lazy bean still has a Spring lifecycle once created. A `SmartLifecycle` bean can still be constructed despite being lazy, and then participate in both start/stop and destroy.

## 15. Global lazy and beans needed at startup

When enabling:

```yaml
spring:
  main:
    lazy-initialization: true
```

evaluate these components:

- Broker message listeners.
- Schedulers/worker threads.
- Polling consumers.
- Web server lifecycle.
- Health/availability infrastructure.
- Beans using `@PostConstruct` for background startup.
- `SmartLifecycle` wrappers for clients/queues.

They do not share identical behavior. A regular `@Lazy` service holding business methods can be deferred; an auto-starting `SmartLifecycle` is typically still pulled into startup, while a scheduled job may be affected by other infrastructure beans needing instantiation.

**Do not claim global lazy is completely ineffective** just because you observed one `SmartLifecycle` starting early. The flag can still defer many other singletons.

### 15.1. Is @Lazy(false) the standard solution for SmartLifecycle?

`@Lazy(false)` marks a bean definition eager in situations where early initialization is required while global lazy is enabled. Because `SmartLifecycle` is already typically created for auto-start, `@Lazy(false)` **does not answer the question "whether to auto-start"**.

If your goal is:

- **Must auto-start:** suitable `SmartLifecycle`, `isAutoStartup()==true`; pick a phase.
- **Must not auto-start:** `isAutoStartup()==false`; define who will call `start`.
- **No instance needed until business demand:** consider a regular bean with `@Lazy`/`ObjectProvider` instead of forcing it to implement `SmartLifecycle`.
- **Must fail-fast on a dependency:** use eager policy or appropriate startup/readiness checks, not proxies alone.

Do not give one bean both application-wide lifecycle listener responsibilities and a strict "must not be created until first use" requirement without resolving the design conflict.

## 16. Relationship with ApplicationRunner and ApplicationReadyEvent

Distinguish Spring Boot milestones:

| Milestone | Characteristic |
| --- | --- |
| `@PostConstruct` | Runs while a bean instance is being initialized |
| `SmartLifecycle.start()` | Usually invoked in `refresh()` for auto-start beans |
| `ContextRefreshedEvent` | Published when refresh succeeds |
| `ApplicationStartedEvent` | Published by Boot after refresh, before runners |
| `ApplicationRunner` / `CommandLineRunner` | Runs after refresh, before ready |
| `ApplicationReadyEvent` | Published after runners succeed |
| `ContextClosedEvent` | Published at the start of context closing |
| `SmartLifecycle.stop(Runnable)` | Ordered stopping during lifecycle shutdown |
| `@PreDestroy` | Destroys eligible bean instances after stop |

If a `SmartLifecycle` receiver starts during refresh, it **can receive messages before `ApplicationRunner` finishes preparing data**. Never rely on post-runner logic to initialize conditions the receiver needs immediately at `start`.

Some solutions:

1. Move minimal required state into a dependency initialized before the receiver.
2. Design the receiver with a **gate**: start lifecycle without processing messages until real readiness conditions are met.
3. Choose `isAutoStartup=false` and have an orchestrator **explicitly start** after setup finishes.
4. Use phases and dependencies to enforce order among lifecycle components, without thinking `phase` controls `ApplicationRunner` order.

**`ApplicationReadyEvent` does not automatically start `SmartLifecycle` beans with `isAutoStartup=false`.** If you want to start them at that milestone, write explicit startup code with idempotency and error handling.

## 17. SmartLifecycle and Spring Boot web server graceful shutdown

In **Spring Boot 3.3**, when running a web app with a supported server, graceful shutdown can be enabled:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Spring Boot 3.3 supports graceful shutdown on documented embedded web servers, executing it as part of **closing `ApplicationContext`** via `SmartLifecycle`/lifecycle phases.

Implications:

- When the context closes through a proper path, the web server stops or restricts accepting new requests via its server-specific mechanism.
- In-flight requests have a **time window** to complete within configured bounds.
- This stop operation participates in lifecycle phases, coordinating with other components.
- Some servers reject new connections at the network layer; others may return HTTP status codes depending on implementation.
- Never assume graceful shutdown automatically makes every background job or message consumer drain safely. Those components need their own lifecycle protocol.

**Do not copy blindly across versions:** graceful shutdown defaults can change across Spring Boot generations. This lesson uses explicit configuration to avoid relying on unstated defaults.

### 17.1. Phase timeout differs from orchestrator timeout

`spring.lifecycle.timeout-per-shutdown-phase` sets the wait duration per phase from the Spring lifecycle processor's perspective. Container orchestration like Kubernetes has **its own deadline**. If the orchestrator kills the process before Spring finishes, remaining callbacks may not complete.

Therefore design so that:

- Total phase stop time + destroy + overhead fits within the granted window.
- The orchestrator's grace period is large enough for required work to finish.
- Each component has internal timeouts and fallback logic.
- Readiness updates promptly to reduce incoming work while stopping.
- No secrets or sensitive data are logged from canceled tasks.

### 17.2. Why can the server start before ready?

The web server can be created/started during refresh, which is also the stage processing `SmartLifecycle`. This can happen **before `ApplicationReadyEvent`**. The server listening on a port does not equate to the application reaching deployment-level readiness.

For consumers actively receiving messages, the risk is similar: `SmartLifecycle.start()` can activate work before runners. If startup steps are mandatory for correctness, add an explicit gate or orchestrator rather than relying solely on the "Started application" log.

## 18. Closing context manually, JVM shutdown hook, and SIGTERM

A context can be closed via:

```java
try (ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args)) {
    // Short-lived CLI application.
}
```

This is illustrative code requiring `DemoApplication` to exist with proper imports. `try-with-resources` fits short-lived CLI/batch tools; **never** copy immediate context closing into a long-running web server.

For services, Spring Boot usually registers a shutdown hook per configuration to close the context on normal JVM shutdown. However:

- `SIGTERM` usually gives the JVM a chance to run shutdown hooks where supported by the deployment environment.
- `SIGKILL`/`kill -9` gives the JVM no chance to run normal shutdown hooks.
- Power loss, kernel crashes, or forced kills can prevent `stop` and destructors from running.
- An IDE stop button sometimes uses a different termination mechanism; do not assume it equals `SIGTERM`.

Thus neither `SmartLifecycle` nor `@PreDestroy` **guarantees cleanup across every failure type**. Data-writing and broker systems must design idempotency, retries, checkpoints, and restart recovery.

## 19. When context refresh fails

If a bean or lifecycle component fails during startup:

- `SpringApplication.run` may fail before `ApplicationReadyEvent` is published.
- Already-created beans may be cleaned up by the container along the failure path.
- Not every bean was created, so not every `@PreDestroy` has an instance to call.
- If `start()` performed partial side effects and then threw an exception, understand how the app rolls back/cleans up rather than assuming `stop()` will definitely be invoked.
- `ApplicationFailedEvent` may be published via Spring Boot's mechanism, though a bean's listener might not be registered if failure happens very early.

A `SmartLifecycle.start()` should:

1. Validate truly required dependencies.
2. Set `running=true` only when operational state is valid, or ensure rollback on error.
3. If resources are opened before an exception, clean up partial allocations locally via `try/catch/finally`.
4. Never swallow errors so the app reports ready while a mandatory component is down.
5. Avoid unbounded blocking in `start`.

Global lazy does not prevent startup failures in `SmartLifecycle` beans that are still initialized during refresh.

## 20. Building a production-ready SmartLifecycle: core principles

A solid implementation does more than fill in required methods. It needs a clear operational contract.

### 20.1. start must be idempotent

```java
@Override
public void start() {
    if (!running.compareAndSet(false, true)) {
        return;
    }
    // Start accepting work, with rollback handling on error.
}
```

This is a **snippet** assuming `running` is a declared `AtomicBoolean`. In practice, if starting resources can fail after CAS succeeds, restore state and release resources in the error branch. CAS alone does not make external initialization atomic.

### 20.2. isRunning must reflect real state

```java
@Override
public boolean isRunning() {
    return running.get();
}
```

This continues the `AtomicBoolean` snippet. Do not return true as soon as a *start request is sent* while the receiver is not actually accepting work. If the system has `STARTING` / `RUNNING` / `STOPPING` / `STOPPED` states, build an appropriate state machine rather than an overly simplistic boolean.

### 20.3. stop must coordinate with the callback

```java
@Override
public void stop(Runnable callback) {
    try {
        stopAcceptingNewWork();
        awaitInFlightWorkWithinDeadline();
        releaseActiveHandles();
        running.set(false);
    } finally {
        callback.run();
    }
}
```

This is **pseudocode**: `stopAcceptingNewWork`, `awaitInFlightWorkWithinDeadline`, and `releaseActiveHandles` are undefined, so it is not standalone runnable source. It illustrates controlled synchronous stopping. If stopping is truly asynchronous, invoke the callback from the **actual completion** signal, not from the request-submitting thread.

### 20.4. Destruction must handle the never-started case

```java
@PreDestroy
public void destroyResources() {
    closeResourcesIfPresent();
}
```

This snippet requires implementing `closeResourcesIfPresent` and importing `jakarta.annotation.PreDestroy`. Its purpose is cleaning up resources **allocated in constructor/init** even if `start` was never called. Destructors should check for null/state and be safe to invoke repeatedly.

### 20.5. Never let an exception drop the callback

If stopping can throw or an async task can fail, define error reporting while **still upholding the callback protocol** as far as possible. However, calling the callback does not mean claiming "stopped cleanly" if live resources remain. Log/emit metrics for the failure state and provide a fallback policy.

## 21. Real-world scenario: message consumer and database client

Suppose an application has:

- `DatabasePool`: manages database connections, must be ready before the consumer.
- `MessageConsumer`: receives messages from a broker and calls the database.
- `OptionalAuditClient`: used only in a few business branches, can be lazy.

Sound design:

```text
START:
DatabasePool (ready)
    |
    v
MessageConsumer.start()
    |
    v
Receive messages

OptionalAuditClient (@Lazy) may not be created yet.

STOP:
MessageConsumer.stop(callback)
    |
    +-- Stop accepting new messages
    +-- Wait for in-flight messages / checkpoint
    +-- callback.run()
    |
    v
DatabasePool closes per lifecycle and bean destruction
```

If `MessageConsumer` implements `SmartLifecycle` to auto-start, adding `@Lazy` **does not guarantee it is deferred**. If it must run only after an import step in a runner completes, explicitly disable auto-start and have an orchestrator start it after that condition, or design a startup gate.

If `OptionalAuditClient` is only a service/SDK and truly rarely used, **do not force it to implement `SmartLifecycle` just to get a close callback**. Keep it as a `@Lazy` singleton with `@PreDestroy` or an appropriate factory `destroyMethod`; that avoids forcing auto-start.

## 22. Testing: verifying start/stop order and laziness

### 22.1. Testing lazy policy across two bean kinds

Using the section 8 demo:

1. Enable `spring.main.lazy-initialization=true`.
2. Launch a fresh `SpringApplication`.
3. Observe `managed.constructed` / `managed.start` occurring during startup.
4. Verify `containsSingleton("managedQueue") == true`.
5. Verify `containsSingleton("optionalCache") == false` before calling `getBean(OptionalCache.class)`.
6. Close the context and observe `managed.stop` then `managed.destroy`.
7. Verify no `cache.destroy` occurs if the cache was never created.

This test distinguishes **instance creation**, **auto-start**, and **destruction**, rather than merely comparing startup timings.

### 22.2. Testing isAutoStartup=false

Change `ManagedQueue`'s `isAutoStartup()` to `false`. Launch a fresh context and observe `managed.start` is not called automatically. **Do not assert the constructor definitely did not run**: the primary effect of the change is startup policy.

Then call `context.start()` or an appropriate start coordination API. Verify `isRunning()` changes as the component actually starts and stops, and then close the context.

### 22.3. Testing phases

Create two `SmartLifecycle` beans with phases -100 and 100, each recording markers into a test-controlled `List<String>`. Expected:

```text
phase-100.start
phase100.start
phase100.stop
phase-100.stop
```

This expectation holds **when the two beans are independent, both auto-start, and start/stop synchronously per contract**. If there is an explicit dependency between them or different phases, re-evaluate the expected order.

### 22.4. Testing async stop callbacks

Do not merely assert that `stop(Runnable)` was called. Build a simulated stop using `CountDownLatch` or `CompletableFuture` to control completion:

1. Start closing the context on a separate test thread with a timeout.
2. Verify `stop(Runnable)` was requested.
3. Keep the callback uninvoked and verify the processor waits within the timeout.
4. Complete the stop work and then invoke the callback.
5. Verify the context proceeds to destructors and finishes closing.

Avoid tests relying on random `Thread.sleep` durations or exceeding timeouts to prevent flaky tests. Ensure tests always release latches/resources in `finally`.

### 22.5. Testing accurately before measuring

Some introspection calls mutate the exact thing you want to measure:

- `context.getBean(OptionalCache.class)` can **instantiate the lazy bean**.
- `BeanFactory.containsBean(...)` only indicates a bean definition/bean can be found, **not proving an instance was created**.
- `ConfigurableListableBeanFactory.containsSingleton(name)` checks whether a singleton instance is present without invoking its constructor.
- In a test using `@Autowired` on the lazy bean itself, the test framework may trigger the bean earlier than in the real scenario.

To observe accurately, inspect state **before explicitly requesting the target**.

## 23. Comparison table: which tool for which purpose?

| Requirement | Sensible mechanism | What to understand |
| --- | --- | --- |
| Avoid creating a rarely used SDK until needed | `@Lazy` on regular bean / `ObjectProvider` | Eager consumers can force target creation |
| Defer creating many Spring Boot singletons | `spring.main.lazy-initialization=true` | Infrastructure and `SmartLifecycle` still have practical exceptions |
| Auto-start a receiver on refresh | `SmartLifecycle.isAutoStartup()==true` | Bean is usually instantiated during startup |
| Create bean yet do not start receiver yet | `SmartLifecycle.isAutoStartup()==false` | Does not guarantee instance stays lazy |
| Coordinate multiple lifecycle components | `getPhase()` and explicit dependencies | Ascending phase start, descending stop |
| Stop a receiver processing work | `stop(Runnable callback)` | Callback must signal **completed** |
| Release instance resources on destroy | `@PreDestroy` / `DisposableBean` / `destroyMethod` | Does not replace phased stopping |
| Shut down entire application context | `ConfigurableApplicationContext.close()` | Stops lifecycle then destroys singletons |
| Pause / resume lifecycle | `context.stop()` / `context.start()` | Not synonymous with closing context |
| Let HTTP requests finish on shutdown | Boot graceful shutdown | Enable properly on Boot 3.3 and pick timeout |
| Ensure application is business-ready | Readiness checks / startup orchestration | Auto-start and port listening do not equal ready |

## 24. Common errors

| Symptom | Root cause | How to handle |
| --- | --- | --- |
| `@Lazy SmartLifecycle` still constructed at startup | LifecycleProcessor needs to find/auto-start bean | Expected typical behavior; do not use `@Lazy` to block auto-start |
| Enabled global lazy yet worker still runs | Worker is `SmartLifecycle` or required by startup infrastructure | Check `isAutoStartup`, dependencies, and lifecycle processor |
| `isAutoStartup=false` yet constructor still runs | Flag controls starting, not guaranteed instance deferral | Check bean discovery/dependencies; use regular bean for true lazy |
| `@Lazy` at injection point yet receiver still started | Lazy proxy affects only that injection edge; lifecycle processor manages bean | Control start via `isAutoStartup` or orchestrator |
| `stop()` has code yet doesn't run as expected | SmartLifecycleProcessor calls `stop(Runnable)`; custom override didn't delegate | Implement `stop(Runnable)` properly and invoke callback |
| Context close hangs until phase timeout | Forgot `callback.run()` or component never finishes | Diagnose stop path; ensure callback after completion |
| `@PreDestroy` runs while receiver still has work | Stop callback reported done too early or phase timed out | Fix drain protocol and deadlines |
| Database client closes before message consumer | Wrong dependency/phase or timeout cut stop short | Declare explicit dependencies and phases with adequate time |
| High phase still gets started early | `depends-on` relationship or custom flow exists | Check dependency graph; dependencies override phase |
| No `managed.destroy` on `kill -9` | JVM did not run shutdown hooks | Use normal `SIGTERM`; design recovery for forced kills |
| Lazy bean shows no `@PreDestroy` | No instance existed to destroy | Check scope and whether instance was ever created |
| Bean still exists after `context.stop` | `stop` is not `destroy` | Call `close` when actually shutting down |
| Ready arrives after consumer already received messages | `SmartLifecycle` started in refresh before runners/ready | Use a gate or disable auto-start and start after setup |
| Graceful HTTP shutdown not working | Forgot `server.shutdown=graceful` on Boot 3.3 or wrong stop signal | Check version, config, and lifecycle stop |
| Shutdown exceeds Kubernetes deadline | Many waiting phases, slow stopping task | Measure per phase, add internal timeouts, adjust deadline |
| Start error leaves app half-running | Failed to roll back resources when `start()` threw exception | Clean up partial init, fail-fast, and report clearly |
| Stopping twice throws exception | `stop`/destructor not idempotent | Manage state and close resources only if still open |

### Sequential diagnostics

1. Confirm whether the bean actually implements `SmartLifecycle` or only `Lifecycle`.
2. Check whether the bean definition has `@Lazy`, global lazy, and `@Lazy` at injection points; these are **three distinct mechanisms**.
3. Check what `isAutoStartup()` returns at runtime.
4. Check whether `isRunning()`, `start()`, and stop callbacks reflect real state.
5. Inspect each component's `getPhase()`; identify explicit dependencies.
6. Trace log milestones: constructor, start, application ready, context close, stop, destructor.
7. If shutdown is slow, see which callback hasn't fired and check per-phase timeout.
8. If a component receives messages too early, define gates and readiness conditions before starting.
9. If a resource closes prematurely, check phase order and whether stop genuinely waits for work to finish.
10. Run controlled tests on an isolated context rather than stopping a production environment context to experiment.

## 25. Self-check questions

1. Why might a regular `@Lazy` bean remain uncreated after refresh, while a `@Lazy` bean implementing `SmartLifecycle` is usually already created?
2. Does `isAutoStartup=false` mean the bean is definitely not constructed during startup?
3. Does `SmartLifecycle.start()` get called before or after `ApplicationRunner` during normal startup?
4. If bean A has phase 0, bean B has phase 100, and both are independent, which starts first and which stops first?
5. If B directly depends on A yet has a lower phase number than A, how does the dependency relationship affect coordination?
6. Why must `stop(Runnable)` invoke the callback **after** stop tasks complete, not merely after sending the stop signal?
7. Does `@PreDestroy` on a created-but-never-running bean still have meaning?
8. Does `context.stop()` destroy singletons and run all destructors like `context.close()`?
9. Why is enabling global lazy not a reliable strategy to stop a message consumer from auto-starting?
10. To stop HTTP requests and background message consumers safely together in Boot 3.3, what shutdown bounds must be configured or measured?
11. Can a lazy bean that was never created receive `@PreDestroy`? Why or why not?
12. Should a rarely used SDK be implemented as a `SmartLifecycle` solely to be closed on shutdown?

### Suggested answers

1. The lifecycle processor needs to find and manage auto-start components; lazy flags on `SmartLifecycle` have very limited effect.
2. No. Auto-start is **operational state**, not **instance creation policy**.
3. Usually before runners, during the refresh stage.
4. A starts before B; B stops before A.
5. Container-known dependencies take precedence when determining start/stop order.
6. Reporting completion too early lets Spring stop/destroy dependencies while the component is still working.
7. Yes, to clean up resources allocated even though it never started.
8. No. `stop` coordinates lifecycle; `close` includes destruction.
9. Because `SmartLifecycle` beans are typically discovered and instantiated to start on refresh.
10. Shutdown phase timeout, server graceful shutdown, orchestrator deadline, and consumer-specific timeout/drain.
11. Without an instance, there is no bean instance destructor to invoke.
12. Usually unnecessary; use a regular bean with an appropriate destructor if auto-start/phase mechanics are not needed.

## 26. Design rules to remember

- **SmartLifecycle** coordinates start/stop of stateful operational components, especially background ones.
- **@Lazy** and **global lazy** concern bean creation; do not use them to control `SmartLifecycle` auto-start.
- **isAutoStartup=false** only blocks auto-start at refresh; it does not prove a bean instance wasn't created.
- **Lower phase starts first, higher phase stops first**; explicit dependencies must still be declared properly.
- **stop(Runnable)** must invoke the callback when stopping truly finishes. Forgetting the callback makes closing wait for timeout.
- **@PreDestroy** and other destructors release bean resources, usually after the lifecycle stop stage.
- **close() differs from stop()**: only closing the context executes full corresponding destruction.
- **Global lazy is a performance choice with trade-offs**: it can defer initialization errors or costs until first use, yet does not stop infrastructure and `SmartLifecycle` beans from running.
- **`SmartLifecycle.start()` can run before `ApplicationReadyEvent`**. If business readiness is needed before accepting messages, use a gate or explicit startup orchestration.
- **Graceful shutdown is not magic**: respect Spring timeouts and platform deadlines, coordinate stop callbacks, and design recovery for abnormal shutdowns.

### Official documentation

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): auto-start, lazy-init semantics, phases, stop callbacks, and default methods.
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): managing start/stop by phase and timeouts.
- [Spring Framework — Startup and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle-processor): `LifecycleProcessor`, `SmartLifecycle`, and handling context refresh/close.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): meaning of singleton lazy-init.
- [Spring Boot 3.3 — Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): global lazy and startup trade-offs.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown=graceful` and `spring.lifecycle.timeout-per-shutdown-phase`.
