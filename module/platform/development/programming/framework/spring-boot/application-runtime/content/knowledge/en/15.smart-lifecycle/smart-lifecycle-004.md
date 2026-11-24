# isAutoStartup and Components Requiring Explicit Startup in SmartLifecycle

A Spring bean can **already be created and have its dependencies fully injected** while still **not permitted to begin operating**. For example: a message consumer should only subscribe after operator approval; a polling job needs to wait for business configuration; a worker can be turned on/off on command; or a long-lived connection should not open immediately on context refresh.

`SmartLifecycle` is Spring Framework's lifecycle contract for components with **start**, **stop**, a **running** state, and **phase** ordering. The deciding method in this lesson is:

~~~java
boolean isAutoStartup();
~~~

- Returning **`true`**: the component is eligible for Spring to automatically invoke `start()` during **ApplicationContext refresh**, via the `LifecycleProcessor` mechanism.
- Returning **`false`**: Spring is not asked to automatically start that component during the refresh step; the application is expected to call **`start()` explicitly** when business conditions are met.

**Do not confuse:** `isAutoStartup() == false` **does not prevent Spring from creating the bean**, does not mean the bean is lazy, does not disable someone else's `start()` call, and does not automatically make the application NotReady.

The examples use **Java 17+ and Spring Boot 3.3.x** (Spring Framework 6.1.x). Because the API belongs to Spring Framework, it does not depend on whether the application runs an HTTP server or a batch job.

## 1. Two independent states: bean exists and worker is running

A singleton can go through these milestones:

~~~text
JVM / SpringApplication.run(...)
   |
   +-- Create ApplicationContext
   +-- Register bean definitions
   +-- Create SmartLifecycle bean
   |      +-- constructor
   |      +-- dependency injection
   |      +-- @PostConstruct / init callbacks
   |
   +-- Context refresh -> LifecycleProcessor.onRefresh()
   |      |
   |      +-- isAutoStartup() == true:
   |      |      may call start() by phase/dependency
   |      |
   |      +-- isAutoStartup() == false:
   |             does not auto-start based on this condition alone
   |
   +-- Context finishes refresh
   +-- Spring Boot runs ApplicationRunner/CommandLineRunner
   +-- ApplicationReadyEvent, run(...) returns
   |
   +-- When business conditions are satisfied:
          component.start() is called explicitly
~~~

This is a conceptual model and does not list every Spring Boot event. What matters is that **bean initialization** and **lifecycle start** are not one and the same action.

For example, a bean may have:

~~~java
@PostConstruct
void initializeMetadata() {
    // Validate configuration, prepare internal state.
}
~~~

However, if `isAutoStartup()` returns `false`, calling `initializeMetadata()` during bean creation **does not mean** a background consumer, polling loop, or listener is already running. Those operational tasks should be handled by `start()`.

The `isRunning()` method lets a coordinator query the **running state per the component contract**, rather than implying `ApplicationContext.isActive()` or a readiness probe must have the same value.

## 2. What contracts does SmartLifecycle extend?

Basic declaration in Spring Framework:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    int getPhase();
}
~~~

This snippet describes the contract, not a Java file you need to compile yourself. `SmartLifecycle` inherits:

- `Lifecycle.start()`: asks the component to begin operating.
- `Lifecycle.stop()`: asks the component to stop operating.
- `Lifecycle.isRunning()`: indicates whether the component is currently operating.
- `Phased.getPhase()`: provides a phase so Spring can coordinate **multiple components**.
- `SmartLifecycle.isAutoStartup()`: decides **whether to auto-start on context refresh**.
- `SmartLifecycle.stop(Runnable callback)`: supports asynchronous stopping and notifies once complete.

In Spring Framework 6.1, two important defaults:

| Method | SmartLifecycle default | Meaning |
|---|---|---|
| `isAutoStartup()` | `true` | If you want the component started manually, **you must override to return false**. |
| `getPhase()` | `Integer.MAX_VALUE` | A SmartLifecycle component defaults to a very late phase on start and a very early phase on stop. |

To control operational ordering, do not rely accidentally on bean registration order; declare explicit phases and dependencies.

### Comparing Lifecycle and SmartLifecycle

| Characteristic | Implementing only `Lifecycle` | Implementing `SmartLifecycle` |
|---|---|---|
| Has `start()`, `stop()`, `isRunning()` | Yes | Yes |
| Auto-starts on context refresh | Not by SmartLifecycle auto-start mechanism | Yes if `isAutoStartup() == true` |
| Controls auto-start via `isAutoStartup()` | Does not have this API | Yes |
| Phase ordering | Usually treated by processor as phase `0` | Has `getPhase()`, defaulting to MAX_VALUE |
| Async stop with callback | Not present on this interface | Has `stop(Runnable)` |

If you do not need auto-start and only want manual starting, implementing `Lifecycle` can also work. If you need phase ordering, shutdown callbacks, or configurable auto-start mode, `SmartLifecycle` gives a clearer contract.

## 3. Runnable Java 17+ example: one auto worker and one manual worker

Goal: when `SpringApplication.run(...)` finishes, the **auto-starting worker** is running while the **manual worker** is not yet running. Then `main` calls `manual.start()`, observes the state, and stops the worker. When the context closes, Spring stops the still-running auto worker.

The example uses a Spring Boot console project with `spring-boot-starter`, without starting an HTTP server so output is easy to compare.

Create file:

`src/main/java/com/example/lifecycle/ManualSmartLifecycleApplication.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManualSmartLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManualSmartLifecycleApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ManagedWorker auto =
                    context.getBean("autoWorker", ManagedWorker.class);
            ManagedWorker manual =
                    context.getBean("manualWorker", ManagedWorker.class);

            System.out.println(
                    "After run: auto=" + auto.isRunning()
                            + ", manual=" + manual.isRunning());

            // Only one worker is started by an explicit command.
            manual.start();
            System.out.println(
                    "After manual.start: auto=" + auto.isRunning()
                            + ", manual=" + manual.isRunning());

            // start() is designed to be idempotent.
            manual.start();
            System.out.println(
                    "After repeated start: manual=" + manual.isRunning());

            manual.stop();
            System.out.println(
                    "After manual.stop: auto=" + auto.isRunning()
                            + ", manual=" + manual.isRunning());
        }
        // try-with-resources closes ApplicationContext and stops autoWorker.
    }

    @Bean
    ManagedWorker autoWorker() {
        return new ManagedWorker("auto", true);
    }

    @Bean
    ManagedWorker manualWorker() {
        return new ManagedWorker("manual", false);
    }

    public static final class ManagedWorker implements SmartLifecycle {

        private final String name;
        private final boolean autoStartup;
        private final AtomicBoolean running = new AtomicBoolean();

        public ManagedWorker(String name, boolean autoStartup) {
            this.name = name;
            this.autoStartup = autoStartup;
        }

        @Override
        public boolean isAutoStartup() {
            return autoStartup;
        }

        @Override
        public int getPhase() {
            return 0;
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("start " + name);
                // In production: start the real work source.
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("stop " + name);
                // In production: stop the work source, reclaim resources.
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                // Must report completion so LifecycleProcessor does not wait needlessly.
                callback.run();
            }
        }
    }
}
~~~

**Note about the class:** `ManagedWorker` is a nested static class, not annotated with `@Component`; it becomes a Spring bean solely through the exact two `@Bean` factory methods. Thus there is no accidental third worker from component scanning.

### Gradle run configuration

If you need to set up a new project, minimal `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.lifecycle.ManualSmartLifecycleApplication'
}
~~~

Run from the project directory that already has Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

With a Maven project using the Spring Boot Maven plugin, you can also run `./mvnw spring-boot:run` when the appropriate main class is configured. Because the code uses Spring Boot/Spring Framework, it cannot be compiled standalone with `javac ManualSmartLifecycleApplication.java` without the dependencies on the classpath.

### Output of the example itself

Ignoring the banner and logs printed by Spring Boot, the lines **explicitly printed by the Java code above** appear in order:

~~~text
start auto
After run: auto=true, manual=false
start manual
After manual.start: auto=true, manual=true
After repeated start: manual=true
stop manual
After manual.stop: auto=true, manual=false
stop auto
~~~

Explanation:

1. On refresh, `LifecycleProcessor` sees `autoWorker.isAutoStartup() == true` and calls its `start()`; the line `start auto` appears before `app.run(args)` returns.
2. `manualWorker.isAutoStartup() == false`, so it is not auto-started on refresh. The bean **already exists**, yet `manual.isRunning() == false`.
3. `manual.start()` is a direct Java call that enables the worker manually. The second call does not print `start manual` again because the example uses `AtomicBoolean.compareAndSet(...)` to ensure repeated starts do not restart it.
4. `manual.stop()` transitions the manual worker to the non-running state.
5. Upon exiting `try-with-resources`, `context.close()` asks the lifecycle processor to stop still-active components. `autoWorker` is still running so it prints `stop auto`; `manualWorker` has already stopped so it prints nothing more.

Limitation: `AtomicBoolean` only keeps the example's state simple and thread-safe at the flag-flip level. In production, actually creating/stopping threads, consumers, or connections must be synchronized with state; **do not set running=true and assume every async startup succeeded**.

## 4. isAutoStartup=false does not mean the bean is not created

This is the most common misconception.

| Event | For manualWorker in the example |
|---|---|
| Spring records bean definition | Yes |
| Spring creates singleton bean | Yes, via normal non-lazy singleton mechanics |
| Dependency injection, `@PostConstruct`/init method if present | Still takes place |
| `isAutoStartup()` queried on context refresh | May be used by the lifecycle processor |
| Automatically calls `start()` on refresh | No, because it returns `false` |
| Bean can be retrieved via `getBean(...)` | Yes |
| Can manually call `start()` after refresh | Yes |
| Can be stopped on context close if running | Yes |

Why distinguish this? Sometimes an author sets `isAutoStartup=false` while the constructor or `@PostConstruct` already opens a connection, subscribes to a message broker, starts a timer, or spawns threads. Then the component **still causes side effects during bean initialization**, even though `start()` was never called.

Proper design is:

- **Constructor / bean initialization:** store configuration, receive dependencies, prepare inactive objects.
- **`start()`:** open consumers, begin polling, register listeners, create or activate workload per contract.
- **`stop()` / `stop(Runnable)`:** stop accepting new work, stop workload, finish or cancel remaining work per policy, and reclaim resources.
- **`isRunning()`:** accurately reflect the state callers and the lifecycle processor can rely on.

Do not try to use `@Lazy` as a substitute for `isAutoStartup(false)`. With `SmartLifecycle`, Spring may need to instantiate the bean while handling context lifecycle, so the lazy-init flag has **limited effect**, as warned in the framework Javadoc. The two settings solve two different goals.

## 5. Manual start via bean.start() or context.start()

There are **two different scopes of explicit startup**:

### Approach A — Start a single specific bean

~~~java
ManagedWorker manual =
        context.getBean("manualWorker", ManagedWorker.class);

if (!manual.isRunning()) {
    manual.start();
}
~~~

This snippet belongs inside a program that already has the variables and classes from the section 3 example, not a standalone file.

Advantage: **precisely selects** which worker is turned on; other workers are not necessarily affected. Ideal for named commands, feature switches, approval-gated jobs, or internal orchestration APIs.

Drawback: calling `start()` directly does not mean Spring reorders all phases of related components. Your code must ensure dependencies are ready, handle exceptions, and obey concurrency rules against unintended concurrent `start()` calls.

### Approach B — Start the entire context

~~~java
context.start();
~~~

`ConfigurableApplicationContext.start()` delegates to the context's `LifecycleProcessor` to start `Lifecycle` beans according to container procedures. When called **explicitly** like this, the processor is not restricted to `SmartLifecycle` beans with `isAutoStartup() == true`. A component with `isAutoStartup() == false` can also be started.

**This is an easily overlooked point:** `isAutoStartup=false` prevents auto-start during **refresh**, but it is not a "hard lock" against subsequent `context.start()` calls.

Comparison:

| Operation | Scope | Can make manual worker run? |
|---|---|---|
| `ApplicationContext.refresh()` | Refreshes container, runs auto-start callbacks | Not from auto-start flag alone, if `false` |
| `manualWorker.start()` | Only the called bean | **Yes** |
| `context.start()` | Lifecycle components in the context | **Yes** |
| Call from other code to `manualWorker.start()` | Only the called bean | **Yes** |
| `context.close()` | Shuts down and destroys context | Not used to start workers |

**Dependency relationship note:** the lifecycle processor also considers explicit dependency relationships. A bean with `isAutoStartup=false` is not always strictly isolated from dependency chains that contain auto-starting components. If `depends-on` is configured or another lifecycle bean needs that worker, verify the actual order and avoid treating this boolean as an access-control mechanism.

If you want to **enable individual consumers selectively**, calling the specific bean's `start()` through an internal coordinator is usually more accurate than `context.start()`.

## 6. How does isAutoStartup differ from getPhase?

The two methods answer **two different questions**:

- `isAutoStartup()`: **Should it run automatically on context refresh?**
- `getPhase()`: **When the container coordinates start/stop of multiple components, where in the order does this component sit?**

For lifecycle beans that auto-start:

~~~text
START (from lower phase to higher):
  phase -100  -> foundational connections
  phase    0  -> dependent components
  phase  100  -> job-accepting consumers

STOP (from higher phase to lower):
  phase  100  -> stop accepting new jobs
  phase    0  -> stop processing
  phase -100  -> close foundational connections
~~~

This is an **ordering design example**, not a rule forcing every system to use those exact numbers.

Spring Framework's Javadoc states:

- Startup goes from **smaller to larger** phases.
- Shutdown goes in the **reverse** order.
- Components in the same phase should not rely on a stable relative order among themselves.
- Explicitly declared `depends-on` relationships can take precedence over phase.
- `SmartLifecycle` defaults to `Integer.MAX_VALUE`, whereas plain `Lifecycle` beans not implementing `SmartLifecycle` are treated as phase `0`.

**Important:** When calling `manualWorker.start()` directly, setting phase to 100 **does not make the container automatically start lower-phase components before this Java call**. Phase is part of container coordination; to explicitly activate an individual worker, the caller must ensure dependencies are already ready.

The example in section 3 overrides `getPhase()` to return `0` to avoid depending on the huge default value, rather than using phase to determine the output. With only one auto-start bean, there is no startup ordering competition among auto workers in the example.

## 7. Conditional startup after refresh with ApplicationRunner

A real-world pattern is: **the worker must be created up front, yet only run when startup arguments permit**.

In Spring Boot, `ApplicationRunner` runs **after the context has refreshed** and before normal startup completes. It can inspect `ApplicationArguments` and then call `start()` on the manual worker.

For example, instead of calling it in `main` as in section 3, you can add the following bean **to a Spring configuration class**, with the corresponding imports:

~~~java
@Bean
ApplicationRunner enableManualWorker(
        @Qualifier("manualWorker") ManagedWorker worker) {
    return args -> {
        if (args.containsOption("enable-manual-worker")) {
            worker.start();
        }
    };
}
~~~

This requires importing `org.springframework.boot.ApplicationRunner` and `org.springframework.beans.factory.annotation.Qualifier`. This snippet **is an alternative**, not part of the section 3 program, because adding it changes when `manualWorker` starts and alters the stdout described there.

Run with:

~~~bash
./gradlew bootRun --args='--enable-manual-worker'
~~~

Now the runner itself decides whether to start the worker based on the flag. `ApplicationRunner` is still invoked after refresh; `isAutoStartup() == false` keeps the worker from running before the runner decides under normal auto-start rules.

Two caveats:

1. If the worker is enabled **by the runner**, startup is only considered normally complete once the runner finishes. If the runner throws an exception, Boot may fail startup.
2. If the requirement is for **an operator to start the worker at any time during runtime**, a runner is unsuitable because runners execute during the startup sequence; you need a protected internal coordinator, a command message, or an access-controlled admin interface.

Never expose a public `POST /start-worker` endpoint for arbitrary clients without authentication, authorization, rate limiting, and auditing.

## 8. Enabling later than ApplicationReadyEvent

Sometimes a component must not auto-start on refresh, nor start immediately in a runner, but only after a business event.

Examples:

- Waiting for approval of a configuration.
- Checking a leader lock before consuming messages.
- Waiting for a separate data migration process to finish.
- Satisfying operational safety or quota conditions.
- Allowing only one node in a cluster to run a scheduler.

In this case, use orchestration logic **separated from lifecycle callbacks**:

~~~text
ApplicationContext finishes refresh
      |
      v
manual SmartLifecycle: running=false
      |
      v
Business condition is confirmed
      |
      v
Coordinator calls manual.start()
      |
      v
manual.isRunning() == true
      |
      v
Asked to stop -> manual.stop()
~~~

Choose a control source fitting the system: internal config/state, authenticated command queue, leader election, or a protected admin API. If the condition can flip rapidly, add debouncing rules against rapid start/stop flapping, record desired state, use retry/backoff, and control concurrency.

Do not assume `ApplicationReadyEvent` is an all-purpose switch to start everything: it is an event about normal Spring Boot startup, not a business approval mechanism. Likewise, reading `ApplicationAvailability.ReadinessState.ACCEPTING_TRAFFIC` only tells you the current readiness state and **does not guarantee the manual worker is running**, unless you design a health/readiness contract that checks the worker.

## 9. Stop and shutdown callbacks still matter greatly

A worker that is only started manually **still needs** a proper stop contract. When the context closes, Spring Framework uses `LifecycleProcessor` to stop still-running lifecycle components in the proper order.

`SmartLifecycle.stop(Runnable callback)` handles asynchronous stopping:

~~~java
@Override
public void stop(Runnable callback) {
    // Ask worker to stop accepting work.
    // Once actually stopped and resources reclaimed:
    callback.run();
}
~~~

This is an illustrative method skeleton, not a complete asynchronous implementation. Do not put `callback.run()` immediately after an operation that **merely sends a stop request** if real work is still running and you want the lifecycle processor to wait for it to finish.

Rules:

- **Always invoke the callback** after stopping finishes. If the callback is not called, the lifecycle processor may wait until the phase timeout, dragging out shutdown.
- For synchronous stopping, you can follow the section 3 example: call `stop()` and then `callback.run()` in `finally`.
- For asynchronous stopping, the callback must fire right when real work has stopped. Handle failure and timeout paths of the shutdown task as well.
- Do not only override `stop()` and ignore the meaning of `stop(Runnable)`. When the lifecycle processor stops a `SmartLifecycle`, it uses the **callback overload**.
- If `isRunning() == false`, the processor usually does not need to call stop on that component during context close. Do not rely on `stop` to clean up something you already allocated in the constructor even if the component never started.

An async example using an application-managed executor must consider: the thread/executor responsible for stopping might itself also be shutting down by phase. Without a guarantee that the callback runs, the application may hang on exit.

### Example of writing a safe synchronous stop

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();  // Synchronously stop work and update running.
    } finally {
        callback.run();
    }
}
~~~

In the section 3 example, stopping only flips an `AtomicBoolean`, so it completes instantaneously. With a real message listener or thread pool, `stop()` must actually stop or wait per policy criteria, rather than merely setting `running=false` and abandoning threads that are still working.

## 10. isAutoStartup=false and lazy initialization are not the same

Two settings that are often confused:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

and:

~~~java
@Lazy
@Bean
ManagedWorker manualWorker() {
    return new ManagedWorker("manual", false);
}
~~~

The second snippet is just an alternative bean declaration in configuration and requires importing `org.springframework.context.annotation.Lazy`; it is not a full substitute for the first method.

| Mechanism | Controls |
|---|---|
| `@Lazy` | When the container **instantiates the bean object** via lazy initialization. |
| `isAutoStartup()` | Whether the lifecycle processor **auto-starts the component on refresh**. |
| `getPhase()` | Start/stop ordering when the container coordinates lifecycle. |
| `isRunning()` | Current operational state of the component. |

Because of auto-start/lifecycle discovery, Spring Framework warns that the lazy-init flag has only limited effect on `SmartLifecycle` beans. Therefore, if your goal is **preventing work execution**, it is more important to keep constructor/initialization **free of startup side effects** and guard logic inside `start()`.

If bean creation cost itself is also too large, explicitly create heavy resources inside `start()` or use an appropriate component factory; do not assume combining `@Lazy` with `isAutoStartup=false` guarantees the object will never be created.

## 11. Can a manual-start worker be started indirectly?

Yes. The boolean `isAutoStartup=false` only describes the preference during the **auto-start stage of the lifecycle processor on refresh**, not a security boundary. Several paths can still cause the worker to run:

- Other code holds a reference and calls `worker.start()`.
- A coordinator calls `context.start()`, causing the processor to start lifecycle beans in the context.
- An auto-starting component has an explicit lifecycle dependency on the worker; resolving dependencies may start the worker as part of the start chain. Check `depends-on` configuration and actual order.
- An initialization method (constructor, `@PostConstruct`, or `@Bean(initMethod=...)`) starts threads/clients early, bypassing `SmartLifecycle.start()` semantics.
- An application-written listener/runner calls `start()` without checking governance conditions.

If starting the worker must be strictly controlled, guard the **start call site** with application logic: permission checks, desired-state checks, dependency verification, leader lease, and auditing. `isAutoStartup=false` is just a startup default policy, not a security lock.

## 12. Testing state before and after activation

When testing, do not merely assert that the bean exists in the context. Check `running` state both before and after operations.

Simple unit test example **without a Spring container** for the custom `ManagedWorker` logic in section 3:

~~~java
ManagedWorker worker = new ManagedWorker("test", false);

assert !worker.isRunning();

worker.start();
assert worker.isRunning();

worker.start(); // Does not run start a second time in this example.
assert worker.isRunning();

worker.stop();
assert !worker.isRunning();
~~~

This is an illustrative snippet in the same package or a class with access to `ManagedWorker` and requires enabling JVM assertions with `-ea` if using `assert`. Because there is no container, it **does not test `isAutoStartup` on context refresh**.

For a Spring Boot integration test, verify with these ideas:

1. After context refresh finishes, call `getBean("manualWorker")`.
2. Assert the bean exists yet `isRunning() == false`.
3. Assert `autoWorker.isRunning() == true`.
4. Call `manualWorker.start()`, assert it transitions to `true`.
5. Call `manualWorker.stop()`, assert it transitions to `false`.
6. Close the context, ensuring still-running components are stopped and resources reclaimed.

When you need to test `context.start()`, use **a separate test** because it can start multiple lifecycle beans rather than just the manual worker. Do not combine that operation into a test meant to prove the manual worker stays idle.

## 13. Difference between auto-start, readiness, and serving traffic

A Spring Boot application can report readiness as **ACCEPTING_TRAFFIC** while a manual `SmartLifecycle` component is **not running**. This is not necessarily a bug:

- If the worker is an optional feature, overall readiness can still be valid.
- If the worker is mandatory for every request, design readiness to reflect that condition.
- If the worker is a background consumer allowed to run on only one node in the cluster, having `isRunning=false` on multiple Pods can be completely normal.

Therefore, do not implicitly interpret `isRunning=false` as "the app is dead" or force the liveness probe to fail. Separate them:

| Question | Appropriate mechanism |
|---|---|
| Has the Spring bean been created by the container? | BeanFactory / bean initialization. |
| Is the worker currently operating? | `SmartLifecycle.isRunning()` plus actual business state. |
| Does the worker auto-start on refresh? | `SmartLifecycle.isAutoStartup()`. |
| Is the ApplicationContext still active? | `ConfigurableApplicationContext.isActive()`. |
| Should this instance receive new traffic? | Readiness state/health probe designed to requirements. |
| Is the process broken beyond self-recovery? | Liveness state/health probe, not simply an optional worker's running flag. |

A listener not yet started while waiting for leader election **does not mean the JVM is broken**. In fact, not enabling it before holding the leader lease is the correct behavior.

## 14. Common mistakes and how to avoid them

**Mistake 1 — "`isAutoStartup=false` means Spring does not create the bean."**

False. For normal singletons, constructor, dependency injection, and init callbacks still occur. Only `SmartLifecycle` auto-start on refresh is disabled.

**Mistake 2 — "`SmartLifecycle` does not auto-run by default."**

False. In Spring Framework 6.1, `SmartLifecycle.isAutoStartup()` defaults to **true**. If you want manual start, you must override it explicitly.

**Mistake 3 — "Setting a huge `getPhase()` will keep the worker from running."**

No. Phase determines ordering during start/stop, **not** `isAutoStartup()`. To disable auto-start, return `false`.

**Mistake 4 — "Once set to false, `context.start()` also skips the worker."**

False. `context.start()` is an **explicit context-wide** lifecycle startup action, unlike the `onRefresh()` callback which only selects auto-start candidates.

**Mistake 5 — "`start()` is only ever called once in a lifetime."**

Not guaranteed. Code can restart after stop or invoke it repeatedly. Make `start()` idempotent as needed, synchronize properly, and handle startup errors.

**Mistake 6 — "Just adding `@Lazy` prevents the worker from running."**

Not reliable. `SmartLifecycle` has its own lifecycle discovery and management; `@Lazy` has limited effect on this kind of bean.

**Mistake 7 — "A `manual.start()` call automatically obeys all phases."**

No. A direct call targets a single bean. The caller must check dependencies and state; phase is meaningful when the container coordinates.

**Mistake 8 — "Just override `stop()`, no need to care about `stop(Runnable)`."**

Prone to unexpected shutdown behavior. `LifecycleProcessor` uses the callback overload when stopping `SmartLifecycle`; the callback must be fired after stopping actually completes.

**Mistake 9 — "`isRunning()` just needs to return true once a start request is received."**

Inaccurate if the work source is not ready yet or startup failed. Design consistent state reflecting real start/stop and actual worker readiness.

**Mistake 10 — "Seeing a worker not running means liveness must fail."**

Not by default. The worker may be waiting on business conditions, optional, or active only on the leader node. Liveness is about process recovery, not one component's start flag.

## 15. Production manual-start worker design checklist

- The bean is created and configured **without auto-starting** in the constructor or `@PostConstruct`.
- `isAutoStartup()` explicitly returns `false` with a comment explaining why.
- `start()` validates preconditions, is idempotent, thread-safe, and reports errors when startup fails.
- `isRunning()` reflects real state, not merely that a start request was sent.
- `stop()` stops accepting work and reclaims resources per policy; `stop(Runnable)` invokes the callback after stopping finishes.
- Distinguish code coordinating **one bean** from `context.start()` starting **multiple beans**.
- Control `@DependsOn`, phases, and callbacks that could indirectly start the worker.
- When startup is slow or has external dependencies, use timeouts, retry/backoff, logging, and metrics.
- Test state after refresh, after start, after stop, and after context close.
- Do not expose worker start/stop control via unprotected public endpoints.
- Readiness/liveness reflects application coordination goals, not a 1-to-1 binding to `isRunning()` if the worker is optional.

### References

- Spring Framework 6.1 — `SmartLifecycle` Javadoc (defaults, phase, stop callback): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `Lifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/Lifecycle.html
- Spring Framework — Bean lifecycle and `LifecycleProcessor`: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — `SpringApplication`, runners, and lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Remember:** `SmartLifecycle.isAutoStartup() == false` does not make the bean disappear and does not forbid starting. It only states **not to auto-call start on `ApplicationContext` refresh** under the normal auto-start mechanism. A component that must be turned on conditionally needs an **explicit start command**, proper state management, and proper shutdown; calling `context.start()` affects the whole context, which is not equivalent to enabling a single worker.
