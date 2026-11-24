# Limits of Ordering Guarantees Between Same-Phase Components in SmartLifecycle

## Learning objectives

In Spring Framework and Spring Boot, `SmartLifecycle` lets components with a *start/stop* state participate in the `ApplicationContext` lifecycle. Each component can return an integer from `getPhase()` so Spring coordinates **by phase group**. However, returning the same phase **does not establish a fixed execution order between those components**.

This is especially important for systems with connections, message consumers, schedulers, workers, listeners, or data-processing pipelines: if a consumer requires an already-active connection, you cannot simply put both in the same phase and hope Bean A always starts before Bean B.

After this lesson, you will:

1. Understand the exact ordering between **different phases** and the limits on **beans in the same phase**.
2. Distinguish when **bean creation**, **`start()` invocation**, **business startup completion**, and **`stop(Runnable)` invocation** happen.
3. Understand why `@Order`, `@Bean` declaration order, component scanning, and bean names cannot replace lifecycle contracts.
4. Know how to use `@DependsOn` to establish mandatory constraints between two components, even when they share the same phase.
5. Write a `SmartLifecycle` with `getPhase()`, `isAutoStartup()`, `start()`, `isRunning()`, `stop()`, and `stop(Runnable)` following the lifecycle properly.
6. Run a Java 17+ / Spring Boot 3.3.13 project proving **guaranteed before-after rules** without testing accidental same-phase ordering.
7. Design safe startup/shutdown for real resources, understanding the limits of async start/stop, timeouts, and readiness.

**Context:** Spring Boot Application Runtime → SmartLifecycle. API explanations follow Spring Framework **6.1.x** and Spring Boot **3.3.x**. Newer Spring Framework versions add deployment options such as concurrent startup per phase; do not assume those exist in 6.1.

## 1. What is SmartLifecycle responsible for?

Spring provides the `Lifecycle` interface to represent a component that can start and stop:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

This is an **illustrative signature**, not a file to create yourself; the real interface is `org.springframework.context.Lifecycle`.

`SmartLifecycle` extends `Lifecycle` and `Phased`, adding auto-startup on context refresh and a stop callback:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

The signature above is also abbreviated for learning; the real interface is in `org.springframework.context.SmartLifecycle`, and methods have default implementations depending on the version.

A `SmartLifecycle` bean can be coordinated by `DefaultLifecycleProcessor`:

- When the application context **refreshes**, eligible auto-startup beans are asked to start.
- When the application context **closes**, running beans are asked to stop according to phase and dependency rules.
- When explicit lifecycle operations are invoked via `ConfigurableApplicationContext`, the processor handles relevant lifecycle beans per its contract.

`SmartLifecycle` is usually suited for components **holding resources or having a continuous operational lifecycle**, such as client connection managers, event consumers, thread-based workers, or receivers. Do not turn every stateless service with only business methods into a `SmartLifecycle`.

### Three things not to equate

| Concept | Meaning | Example |
| --- | --- | --- |
| Bean initialization | Spring creates object, injects dependencies, runs init callbacks | Constructor, `@PostConstruct` |
| Lifecycle startup | Spring calls `SmartLifecycle.start()` | Begin receiving messages, open consumer, start scheduler |
| Business readiness | Component is **actually ready** to work per business criteria | Connection handshake completed, subscription active |

A bean may **already be created** while `isRunning() == false`. And a bean may be marked running after submitting a background task while the business connection has not finished yet. Phase only coordinates **lifecycle calls**, not automatically verifying external resources are ready.

## 2. Ordering rules across different phases

Under the `SmartLifecycle.getPhase()` contract:

- **Startup:** **smaller** phase values first, **larger** later.
- **Shutdown:** **larger** phase values first, **smaller** later.
- Phase values are `int`; they may be negative, 0, or positive.
- If two beans have different phases and no conflicting dependency constraints, ordering is expressed by phase groups.

Example:

~~~text
              STARTUP
                  |
     phase -100: connection factory
                  |
      phase   0: message dispatcher
                  |
      phase 100: public consumer
                  |
              Running
                  |
              SHUTDOWN
                  |
      phase 100: public consumer
                  |
      phase   0: message dispatcher
                  |
     phase -100: connection factory
~~~

Architectural meaning: a supporting component below usually starts early and stops late; a consuming component above usually starts later and stops earlier. Thus phase creates an **inter-group order**, not describing the entire dependency graph by itself.

### Distinguishing default phases

| Lifecycle bean type | Typical default phase in Spring Framework 6.1 |
| --- | --- |
| `SmartLifecycle` without overriding `getPhase()` | `SmartLifecycle.DEFAULT_PHASE` = `Integer.MAX_VALUE` |
| Plain `Lifecycle` not implementing `Phased` | Treated by the processor as phase `0` |
| `SmartLifecycle` overriding `getPhase()` | Application-specified `int` value |

Default `SmartLifecycle` beans usually sit at a very high phase so they auto-start late and auto-stop earlier than low-phase lifecycle beans. However, **do not assume 0 is SmartLifecycle's default**: 0 is the default applied to plain `Lifecycle` by the processor.

Framework components may already have their own phases. Do not choose phase values for an application without knowing whether the related components reside in the same `ApplicationContext` and share the same lifecycle processor.

## 3. Same phase has no guaranteed ordering

This is the core of the lesson.

Suppose three independent components:

~~~text
Bean A → getPhase() = 0
Bean B → getPhase() = 0
Bean C → getPhase() = 0
~~~

Spring guarantees they belong to the **same phase group** relative to other groups, yet **does not promise A, B, C start alphabetically, by source code order, by scan order, or by bean creation order**.

Any of these observed orders can conform to the contract when no dependency exists:

~~~text
Run 1: start(A), start(B), start(C)
Run 2: start(C), start(A), start(B)
Run 3: start(B), start(C), start(A)
~~~

These are **three valid illustrative scenarios**, not a claim that Spring randomly shuffles order on every real run. On a specific setup, order may appear stable across many runs due to internal data structures. **Accidental stability does not turn it into an API guarantee.**

Similarly at shutdown, independent beans in the same phase are not given an absolute order under the `SmartLifecycle` contract. The reversed phase relationship at the **group** level does not say "Bean C definitely stops before B, and B before A" if all three share a phase.

### Valid contract vs. false assumptions

| Claim | Assessment |
| --- | --- |
| Phase `-100` starts before phase `0`, absent an inverting depends-on | True |
| Phase `100` stops before phase `0`, absent an inverting depends-on | True |
| Same phase means Spring starts by bean name A→Z | **Not guaranteed** |
| Same phase means Spring starts by `@Bean` declaration order | **Not guaranteed** |
| Same phase means stop order always exactly reverses observed start log | **Not guaranteed** |
| Explicit `@DependsOn` exists: dependency starts before dependent | True per contract |
| `@DependsOn` exists: dependent stops before dependency | True per contract |
| Adding `@Order(1)` on a SmartLifecycle bean is the standard start-order way | **No**; use phase or dependencies |
| `start()` called earlier means external resource is already operational | Not necessarily; depends on `start()` implementation |

### Why same-phase assumptions easily cause bugs

Example:

- Bean `ConnectionPoolManager` must connect successfully **before** bean `QueueConsumer` begins receiving messages.
- Both return `getPhase() == 0`.
- Without describing the dependency, Spring has no contract forcing `ConnectionPoolManager.start()` to run before `QueueConsumer.start()`.
- A deployment observed succeeding many times can still fail after upgrading the framework, adding modules, changing bean registration, or switching context topology.

**If ordering is a business invariant, design a constraint recognized by the framework**; do not rely on one run's logs.

## 4. @DependsOn: explicit constraint within the same phase

Spring Framework explicitly specifies: an explicit **depends-on** relationship takes precedence over phase ordering. The dependent bean is **started after** its dependency and **stopped before** its dependency.

Example:

~~~java
@Bean("queueConnection")
SmartLifecycle queueConnection() {
    return new QueueConnectionLifecycle();
}

@Bean("queueConsumer")
@DependsOn("queueConnection")
SmartLifecycle queueConsumer() {
    return new QueueConsumerLifecycle();
}
~~~

This is an **illustrative configuration snippet**, not a full project: you must define the lifecycle classes and import `Bean`/`DependsOn`/`SmartLifecycle`. Even if both have phase `0`, Spring still enforces:

~~~text
START: queueConnection → queueConsumer
STOP : queueConsumer   → queueConnection
~~~

`@DependsOn("queueConnection")` here uses the **bean name** `queueConnection`, not the Java class name. A wrong bean name can cause bean creation failure; keep names clear and check them during refactors.

### How do dependencies and phase groups align without conflict?

The cleanest setup is:

~~~text
phase -100: queueConnection
phase    0: queueConsumer, @DependsOn("queueConnection")
~~~

Both phase and dependency point the same way: connection starts before consumer; consumer stops before connection.

If you assign opposing phases while keeping `@DependsOn`, the `SmartLifecycle` contract states **`depends-on` takes precedence over phase**. Still, that is hard-to-read design; pick phases reflecting the dependency graph rather than intentionally putting two mechanisms in conflict.

### @DependsOn also affects initialization

`@DependsOn` does not apply solely to `SmartLifecycle.start()`. It also expresses an initialization relationship between bean definitions: Spring must process the dependency before the dependent when creating beans. Consequently:

- It can cause an otherwise lazy bean to be requested early.
- It can shift constructor/`@PostConstruct` timing.
- It is an explicit tool when **initialization and lifecycle** constraints are both needed.
- It should not be sprinkled onto dozens of beans to force an unnecessary chain.

**Distinguishing constructor injection and `@DependsOn`:** constructor injection declares an actual object dependency so the bean can be built; `@DependsOn` helps when a startup relationship cannot be naturally expressed as a constructor parameter—for example, infrastructure that must start first without the consumer calling that object directly. Making real dependencies explicit through injected interfaces is usually easier to maintain when possible.

## 5. @Order is not a SmartLifecycle ordering tool

Spring uses `@Order`/`Ordered` for many purposes: ordering strategy beans in collections, certain callbacks, startup runners, or aspects. However, **not every `@Order`-aware mechanism affects the lifecycle processor**.

Example:

~~~java
@Component
@Order(1)
class FirstConsumer implements SmartLifecycle {
    // ...
}

@Component
@Order(2)
class SecondConsumer implements SmartLifecycle {
    // ...
}
~~~

These are **partial illustrative classes**, lacking enough methods to compile standalone. You must not infer from `@Order(1)` and `@Order(2)` that `FirstConsumer.start()` always runs before `SecondConsumer.start()` when both have the same phase and no dependency.

**To control lifecycle ordering:**

- **Inter-group relationships:** override `getPhase()` returning distinct integers.
- **Mandatory relationships between beans:** declare an explicit dependency, such as `@DependsOn`.
- **Complex conditional/rollback multi-step chains:** consider a lifecycle coordinator component or orchestration service instead of many peer beans relying on accidental ordering.

### Bean names and @Bean declaration order also create no contract

Given:

~~~java
@Bean SmartLifecycle alpha() { /* ... */ }
@Bean SmartLifecycle beta()  { /* ... */ }
~~~

Writing `alpha` before `beta` in the same Java file is not a contract requiring `alpha.start()` to precede `beta.start()`. To establish provable order, use distinct phases or dependencies.

### @Priority does not substitute for phase

Some Spring mechanisms also honor `@Priority`. Do not treat it as a `SmartLifecycle` contract when `SmartLifecycle` docs explicitly specify phase and `depends-on`. An annotation affecting **injection list order** does not mean it affects **start/stop order**.

## 6. isAutoStartup and startup timing

`SmartLifecycle.isAutoStartup()` returns `true` by default in Spring Framework 6.1. On context refresh, `DefaultLifecycleProcessor` discovers `SmartLifecycle` beans and asks eligible components to start.

If a bean returns `false`:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

then it is not automatically started during the refresh phase merely for being a `SmartLifecycle`. It can be started through an appropriate explicit lifecycle operation. If a component must always be ready by the time Boot reaches ready, define its startup strategy explicitly rather than accidentally disabling auto-startup.

**Note:** `SmartLifecycle` beans are often still **instantiated** so the lifecycle processor can inspect and manage them, even if a bean definition has lazy-init. Therefore `@Lazy` is not a reliable tool to defer every `SmartLifecycle` bean at runtime. Bean creation and `start()` invocation are two separate milestones.

### The default phase is not 0

By default `SmartLifecycle.getPhase()` returns `Integer.MAX_VALUE` (via `DEFAULT_PHASE`), so `SmartLifecycle` beans that do not override phase belong to a very late group on startup and a very early group on shutdown. To align a group consistently, **override `getPhase()` explicitly** rather than implicitly assuming 0.

This matters especially when you have a plain `Lifecycle` (treated as phase 0) and a default `SmartLifecycle` (phase `MAX_VALUE`). They are not naturally in the same phase.

## 7. Complete example: testing mandatory relationships without guessing same-phase order

This example uses **Java 17+**, **Spring Boot 3.3.13**, and Gradle. It is a **non-web** application: it creates five `SmartLifecycle` beans and one event-recording bean, verifies constraints during startup, and then closes the context to verify reverse order on shutdown.

Five components:

| Bean name | Phase | Explicit dependency | Role |
| --- | --- | --- | --- |
| `storage` | `-100` | None | Foundational resource |
| `alpha` | `0` | None | Worker A |
| `beta` | `0` | `@DependsOn("alpha")` | Worker B, must run after A |
| `gamma` | `0` | None | Independent worker in the same phase |
| `api` | `100` | None | Upper-layer component |

**What needs to be proven:**

1. Start: `storage` before `alpha`/`beta`/`gamma`, and all three phase-`0` beans before `api`.
2. Start: `alpha` before `beta` due to `@DependsOn`.
3. Stop: `api` before the three phase-`0` beans, and phase-`0` beans before `storage`.
4. Stop: `beta` before `alpha` due to the reversed dependency relationship.
5. **Do not assert that `gamma` must sit before/after `alpha` or `beta`**: that is the exact same-phase contract boundary.

### 7.1. Directory structure

~~~text
smart-lifecycle-phase-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/phase/
    ├── PhaseDemoApplication.java
    ├── DemoLifecycle.java
    └── LifecycleTrace.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'smart-lifecycle-phase-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.phase.PhaseDemoApplication'
}
~~~

The project needs no web starter. The Gradle installation must be compatible with Spring Boot 3.3 and JDK 17. If dependencies are not cached yet, Gradle will need to download them from Maven Central.

### 7.2. SmartLifecycle class implementing start/stop

**`src/main/java/com/example/phase/DemoLifecycle.java`:**

~~~java
package com.example.phase;

import org.springframework.context.SmartLifecycle;

public final class DemoLifecycle implements SmartLifecycle {

    private final String id;
    private final int phase;
    private final LifecycleTrace trace;

    private volatile boolean running;

    public DemoLifecycle(String id, int phase, LifecycleTrace trace) {
        this.id = id;
        this.phase = phase;
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (!running) {
            running = true;
            trace.record("start:" + id);
        }
    }

    @Override
    public synchronized void stop() {
        if (running) {
            running = false;
            trace.record("stop:" + id);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        }
        finally {
            // Notify LifecycleProcessor that stop has finished.
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

**Why does this code not rely on accidental ordering?**

- `id` and `phase` are passed explicitly to the constructor.
- `start()` and `stop()` record only when state changes; methods can be called again without duplicate logs in normal cases.
- `running` is `volatile` so other threads see state updates; `synchronized` protects updates in the demo. It does not substitute for thread-safe design around external resources.
- `stop(Runnable)` invokes `stop()` and always invokes the callback in `finally`. Because `stop()` in the demo finishes **synchronously**, this is a valid moment to notify the lifecycle processor.
- `getPhase()` returns the exact assigned value rather than relying on default `Integer.MAX_VALUE`.
- `isAutoStartup() == true` enables auto-starting on context refresh.

A real project must ensure inside `start()`/`stop()` that the corresponding resource has reached the right state before changing `running`. With no network resource here, state changes are instantaneous.

### 7.3. Event recorder and partial-order checker class

**`src/main/java/com/example/phase/LifecycleTrace.java`:**

~~~java
package com.example.phase;

import java.util.ArrayList;
import java.util.List;

public final class LifecycleTrace {

    private final List<String> events = new ArrayList<>();

    public synchronized void record(String event) {
        events.add(event);
    }

    public synchronized void verifyStartup() {
        before("start:storage", "start:alpha");
        before("start:storage", "start:beta");
        before("start:storage", "start:gamma");

        before("start:alpha", "start:beta");

        before("start:alpha", "start:api");
        before("start:beta", "start:api");
        before("start:gamma", "start:api");
    }

    public synchronized void verifyShutdown() {
        before("stop:api", "stop:alpha");
        before("stop:api", "stop:beta");
        before("stop:api", "stop:gamma");

        before("stop:beta", "stop:alpha");

        before("stop:alpha", "stop:storage");
        before("stop:beta", "stop:storage");
        before("stop:gamma", "stop:storage");
    }

    private void before(String first, String second) {
        int i = events.indexOf(first);
        int j = events.indexOf(second);

        if (i < 0 || j < 0 || i >= j) {
            throw new IllegalStateException(
                    "Expected " + first + " before " + second
                    + "; events=" + events);
        }
    }
}
~~~

The `before(...)` method compares the **positions of two milestones** in the list without requiring them to be adjacent. As a result:

- It verifies constraints guaranteed by phase and `depends-on`.
- It **does not** force `gamma` to run before or after `alpha`/`beta`.
- It does not demand the entire event trace match one rigid sequence.
- It does not depend on bean definition order or processor traversal order.
- When an event is missing or a before-after relation is wrong, it throws an exception with the event list for easy diagnosis.

Because `LifecycleTrace` is a regular bean, it can be injected into the `DemoLifecycle` instances. The trace only stores strings in memory for the example; real systems should use structured logging/metrics rather than accumulating events unboundedly.

### 7.4. Bean definitions and same-phase dependency

**`src/main/java/com/example/phase/PhaseDemoApplication.java`:**

~~~java
package com.example.phase;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;

@SpringBootApplication
public class PhaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PhaseDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        LifecycleTrace trace = null;

        try (ConfigurableApplicationContext context = app.run(args)) {
            trace = context.getBean(LifecycleTrace.class);
            trace.verifyStartup();
            System.out.println("CHECK: STARTUP PASS");
        }

        if (trace == null) {
            throw new IllegalStateException("LifecycleTrace unavailable");
        }

        trace.verifyShutdown();
        System.out.println("CHECK: SHUTDOWN PASS");
    }

    @Bean
    LifecycleTrace lifecycleTrace() {
        return new LifecycleTrace();
    }

    @Bean
    DemoLifecycle storage(LifecycleTrace trace) {
        return new DemoLifecycle("storage", -100, trace);
    }

    @Bean
    DemoLifecycle alpha(LifecycleTrace trace) {
        return new DemoLifecycle("alpha", 0, trace);
    }

    @Bean
    @DependsOn("alpha")
    DemoLifecycle beta(LifecycleTrace trace) {
        return new DemoLifecycle("beta", 0, trace);
    }

    @Bean
    DemoLifecycle gamma(LifecycleTrace trace) {
        return new DemoLifecycle("gamma", 0, trace);
    }

    @Bean
    DemoLifecycle api(LifecycleTrace trace) {
        return new DemoLifecycle("api", 100, trace);
    }
}
~~~

Notes:

- Each `@Bean` factory method creates one `DemoLifecycle` with bean name from the method name: `storage`, `alpha`, `beta`, `gamma`, and `api`.
- `beta` carries `@DependsOn("alpha")`. Both are at phase `0`, so the `alpha → beta` order cannot be explained by comparing phases; **dependency** is the reason.
- `gamma` is also at phase `0` yet has no dependency on `alpha` or `beta`. Thus the example intentionally **does not** assert its relative position.
- `storage` is at phase `-100`; `api` is at phase `100`. Phase relationships keep lower/higher groups in the right start/stop direction.
- `LifecycleTrace` is a regular bean not implementing `SmartLifecycle`, so it does not appear as a separate lifecycle member in the checks.
- `try-with-resources` closes `ConfigurableApplicationContext` at the end of the block. That triggers the processor to invoke stop so `verifyShutdown()` can check it. **Do not close the context right after startup in a long-running web app**; this style is only for a CLI demo.

### 7.5. Running the program

From the `smart-lifecycle-phase-demo` directory:

~~~bash
gradle bootRun
~~~

If Gradle Wrapper is present, use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows. The example does not auto-generate a wrapper; you need Gradle pre-installed or a wrapper created for the project.

Ignoring Gradle and Spring Boot lines, the **two lines explicitly printed by the application code** are:

~~~text
CHECK: STARTUP PASS
CHECK: SHUTDOWN PASS
~~~

This **does not mean** the whole event trace has a single unique order. Rather, the program prints pass only when **every checked mandatory relationship** holds, even though `gamma`'s relative order against `alpha`/`beta` may vary.

### 7.6. Why is this a better test than comparing a fixed log list?

An incorrect test might write:

~~~java
assertEquals(
    List.of("start:storage", "start:alpha", "start:beta",
            "start:gamma", "start:api"),
    actualStartupEvents);
~~~

This is **non-standalone illustrative test code**. It arbitrarily forces `gamma` after `beta`, even though all three share the same phase and `gamma` has no dependency. Even if the test passes on your machine today, it tests **behavior not guaranteed by the API**.

A proper test verifies the constraints:

~~~text
start(storage) < start(alpha)
start(storage) < start(beta)
start(storage) < start(gamma)
start(alpha)   < start(beta)       [@DependsOn]
start(alpha)   < start(api)
start(beta)    < start(api)
start(gamma)   < start(api)
~~~

Similarly for shutdown:

~~~text
stop(api)   < stop(alpha)
stop(api)   < stop(beta)
stop(api)   < stop(gamma)
stop(beta)  < stop(alpha)          [@DependsOn]
stop(alpha) < stop(storage)
stop(beta)  < stop(storage)
stop(gamma) < stop(storage)
~~~

In both tables above, the `<` sign means "happens before" (*in demo log order*), not a Java string comparison operator or a general memory-order guarantee. With async stop, distinguish **when stop is called** from **when stopping actually finishes**.

### 7.7. Three variants to try yourself

**Variant 1 — Remove `@DependsOn` on `beta`.**

Delete the annotation:

~~~java
@DependsOn("alpha")
~~~

This is a line **removed from the demo configuration**, not a new class. Now `alpha` and `beta` are both phase `0`, with no declared dependency. `verifyStartup()`/`verifyShutdown()` still require `alpha → beta` / `beta → alpha`, so now they **may** fail, or **may accidentally still pass** on one run. Neither outcome restores the lost API guarantee.

**Variant 2 — Change `beta`'s phase to 10 and remove `@DependsOn`.**

~~~java
@Bean
DemoLifecycle beta(LifecycleTrace trace) {
    return new DemoLifecycle("beta", 10, trace);
}
~~~

This method replaces the original `beta(...)` method. Phase ordering now guarantees `alpha` (phase 0) starts before `beta` (phase 10), and `beta` stops before `alpha`. However, `gamma` is still phase 0, so it also starts before `beta` and is no longer independent in the same phase as `beta`.

**Variant 3 — Keep `gamma` at phase 0 with an order annotation.**

Add an `@Order` onto `gamma` **without** changing phase or dependencies. This is not a method recognized by the `SmartLifecycle` contract to force `gamma` to start before phase-0 peers. Even if a test outcome appears to change, that is not proof that `@Order` is a lifecycle ordering API.

## 8. When to use phase, and when to use @DependsOn?

### Use phase for operational layers

A message processing system has layers:

~~~text
phase -200: transport / connection resources
phase -100: codec / shared receiver infrastructure
phase    0: consumer workers
phase  100: HTTP adapter allowing work intake
~~~

Choosing phases expresses **upper/lower layer** relationships. There is no need to distinguish individual workers within the same phase if they are independent and can start/stop in any order.

Phase is appropriate when you know one **category** of components should start before another category, even when beans do not directly inject one another.

### Use @DependsOn for mandatory relationships between beans

For example, worker `invoiceConsumer` strictly must start only after `schemaRegistryClient`, while both are managed in group 0 for operational reasons:

~~~java
@Bean
@DependsOn("schemaRegistryClient")
SmartLifecycle invoiceConsumer() {
    return new InvoiceConsumerLifecycle();
}
~~~

This is an **illustrative snippet** requiring appropriate classes and imports. It sets a direct relationship without pushing all other consumers to phase 1.

### Use orchestration for complex multi-step flows

If a pipeline must:

1. Validate configuration.
2. Open a connection.
3. Restore checkpoints.
4. Subscribe to a topic.
5. Wait for initial partition assignment.
6. Only then open traffic.

Incrementing phase numbers alone may be insufficient because `start()` can be asynchronous, have retries, or need rollback. An orchestration service/`SmartLifecycle` coordinating steps with explicit states, timeouts, and dedicated readiness is usually easier to test than turning ten same-phase peers into a tangled dependency chain.

**Key takeaway:** Phase describes **group ordering**, dependency describes **mandatory ordering**, and readiness describes **actual ability to work**. These three do not automatically substitute for one another.

## 9. Synchronous vs. asynchronous startup: what is actually guaranteed?

In a simple `SmartLifecycle`, `start()` might only launch a thread:

~~~java
@Override
public void start() {
    executor.execute(this::connectAndSubscribe);
    running = true;
}
~~~

This is an **incomplete illustrative snippet**, assuming `executor`, `connectAndSubscribe`, and `running` exist. It shows a common design bug: `start()` returns **before** `connectAndSubscribe()` finishes. The lifecycle processor can move on to the next component by phase/`depends-on`, yet the first component is not operational yet.

Example:

~~~text
10:00:00.000 start(ConnectionManager) is called
10:00:00.001 ConnectionManager submits async connect, returns
10:00:00.002 start(MessageConsumer) is called per depends-on
10:00:00.250 ConnectionManager completes connect/handshake
~~~

These timestamps are **illustrative only**, not measurements or real Spring guarantees. The order of `start` calls is still right, yet `MessageConsumer` can arrive too early if it requires the connection to truly be ready.

### Solutions

- If component startup must succeed before another component, have `start()` **wait for the ready condition with a time bound** before returning, or coordinate waiting in an appropriate startup mechanism.
- If start cannot block, provide a readiness signal/`Future` so the dependent component or orchestrator activates only when the condition completes.
- Distinguish "start command sent" from "consumer subscribed" or "connection handshake succeeded".
- Configure timeouts and error handling for networking; never use an unbounded `while(true)` on startup.
- On serious failure, decide whether to fail startup, retry finitely, or enter an observable degraded state.
- Do not use a `boolean running` field set `true` right after `executor.submit` as proof of readiness to serve.

### Version difference with startup concurrency

In **Spring Framework 6.1**, lifecycle groups are handled by phase and `DefaultLifecycleProcessor`'s internal contract. Versions **6.2** add options to configure concurrent startup for specific phases. Do not copy APIs like `setConcurrentStartupForPhases(...)` from 6.2 into a Boot 3.3/Framework 6.1 project without updating dependencies; and even when concurrent startup is configured, still never infer a fixed order among same-phase peers.

## 10. stop(Runnable): a phase may have to wait for components to finish together

On shutdown, `SmartLifecycle.stop(Runnable callback)` is invoked by the processor to support **asynchronous stopping**. The callback must run **after** the component has truly stopped; the processor uses the callback to track group shutdown progress.

Synchronous example from the section 7 project:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop(); // Finish before returning
    }
    finally {
        callback.run();
    }
}
~~~

This approach is valid when `stop()` genuinely finishes stopping the resource. With asynchronous shutdown, **do not** call `callback.run()` right after submitting a task if resources are still being released.

### Illustrative async stop pattern

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            closeConnectionsAndWait();
        }
        finally {
            running = false;
            callback.run();
        }
    });
}
~~~

This is a **partial illustrative snippet**, requiring `executor`, `closeConnectionsAndWait()`, `running`, and handling for when `executor.execute(...)` rejects the task. A production implementation must ensure the callback is triggered exactly once across relevant success/failure paths and never hides unreleased resources.

**Must distinguish:** "`stop(Runnable)` was called" ≠ "resource stop completed". For **same-phase** beans, stopping may involve multiple callbacks/waits within the same group; do not assume an absolute completion order among independent peers.

### Per-phase-group shutdown timeout

In Spring Framework 6.1, `DefaultLifecycleProcessor` has `setTimeoutPerShutdownPhase(long)`; the default per the 6.1 Javadoc is **30,000 ms (30 seconds)** per phase group. If a callback is not invoked on time, shutdown may be delayed up to the timeout instead of waiting forever.

An illustrative configuration:

~~~java
@Bean(name = "lifecycleProcessor")
DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor =
            new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(15_000);
    return processor;
}
~~~

This is an **additional configuration snippet**, not part of the section 7 project; it requires importing `Bean` and `org.springframework.context.support.DefaultLifecycleProcessor`. Naming a bean `lifecycleProcessor` has special meaning to `ApplicationContext`; change it only when you understand its impact on all lifecycle beans in the context.

**Do not confuse Framework 6.1's shutdown timeout with defaults or new APIs in 6.2/7.x.** Verify the configuration of your actual runtime version before changing it.

### @DependsOn during shutdown

If `beta` depends on `alpha`, Spring requires `beta` to **stop before** `alpha`. Especially for same-phase beans, this relationship is critical to ensure the consumer stops accepting work before the producer/shared infrastructure is released.

However, the order of **stop requests** and **actually stopping all background threads** match only when the implementation fulfills the contract and callback properly. If `beta.stop(Runnable)` invokes the callback too early, `alpha` can be stopped next while `beta` is actually still processing messages; that is an **implementation bug**, not a phase-ordering bug.

## 11. Lifecycle is not the same as bean destruction or startup runners

Many callbacks occur during the application lifecycle with different contracts:

| Hook | When it runs | Used for |
| --- | --- | --- |
| Constructor / `@Bean` factory method | When bean is created | Initial state setup |
| `@PostConstruct` | After a bean's dependency injection | Local init |
| `SmartLifecycle.start()` | When lifecycle processor starts bean | Starting a start/stop-capable component |
| `SmartLifecycle.stop(Runnable)` | When stopping a running lifecycle bean | Stopping and signaling completion to processor |
| `ApplicationStartedEvent` | After Spring context refresh | Observing Boot started milestone |
| `ApplicationRunner`/`CommandLineRunner` | After refresh, before Boot ready | Startup work that must finish before ready |
| `ApplicationReadyEvent` | After runners | Observing Boot ready milestone |
| `@PreDestroy` | When bean is destroyed in normal lifecycle | Final resource release |

`SmartLifecycle.start()` is invoked during **context refresh** for auto-start beans; do not confuse it with `ApplicationRunner`, which runs **after refresh**. A bean may already have run `start()` while runners are still executing, so the application is not ready yet.

When closing the context, the lifecycle processor asks running lifecycle beans to stop, and then the bean factory executes destruction callbacks per their lifecycle. `@PreDestroy` **does not replace** phased shutdown, and by default creates no start/stop order between two same-phase peers.

### @Lazy is also not a way to guarantee ordering

`SmartLifecycle` is discovered and managed by the container on refresh; per the Javadoc, because of auto-start, the lazy-init flag has **very little effect** for deferring such beans. Therefore:

- `@Lazy` on a `SmartLifecycle` does not mean that bean is guaranteed absent at startup.
- `@Lazy` does not establish an order between two same-phase `SmartLifecycle` beans.
- If a component must not auto-start, consider `isAutoStartup()` and manage starting explicitly.
- If a component must start **after** another component, consider `getPhase()` or dependencies.

## 12. Real-world design: connection, consumer, and HTTP gateway

Suppose a service receives HTTP requests, puts messages into a queue, and has a background consumer processing messages.

### Risky design

~~~text
SmartLifecycle ConnectionManager: phase 0
SmartLifecycle QueueConsumer:      phase 0
SmartLifecycle RequestGateway:     phase 0
~~~

No dependencies are declared. Possible outcomes:

1. Gateway starts before the queue consumer can process work.
2. Consumer starts before the connection is ready.
3. On shutdown, the connection stops before the consumer stops receiving messages.
4. Working on one instance does not guarantee other instances in the cluster behave the same.

### Phased design

~~~text
ConnectionManager: phase -100
QueueConsumer:      phase    0
RequestGateway:     phase  100

Startup : ConnectionManager → QueueConsumer → RequestGateway
Shutdown: RequestGateway → QueueConsumer → ConnectionManager
~~~

This is a sensible layered model **if all three really are lifecycle components managed by the same processor**. The embedded HTTP port managed by Spring Boot/the web server does not necessarily follow an arbitrary phase you assign to a custom wrapper; check the phase of the actual framework component rather than merely naming a bean "RequestGateway".

### Adding @DependsOn when strict constraints are needed

If `QueueConsumer` strictly uses `ConnectionManager`, mark the explicit dependency; if there are multiple independent consumers at phase 0, there is no need to force them into a sequential queue.

For asynchronous connections, ensure **connection readiness** is awaited properly before the consumer starts. Phase alone will not solve that part.

### Application readiness

Once `SmartLifecycle.start()` has been called, the application may still not be ready according to Spring Boot because startup runners remain. And when Boot publishes `ApplicationReadyEvent`, a background consumer that marked itself running too early might not actually have subscribed yet. For traffic-critical systems, use an appropriate readiness indicator or startup gate.

In particular, **binding a TCP port** does not mean the consumer is ready; if requests arrive before the pipeline is operational, messages can be lost or transient errors can spike.

## 13. Testing: verify a partial order instead of an absolute order

When testing phases, classify **mandatory relationships** separately from **relationships not guaranteed by the API**.

### Assertions you should have

For two phase groups `-100` and `100`, assert:

~~~text
start(phase -100) before start(phase 100)
stop(phase 100) before stop(phase -100)
~~~

With `@DependsOn("alpha")` on same-phase `beta`:

~~~text
start(alpha) before start(beta)
stop(beta) before stop(alpha)
~~~

For same-phase `gamma` with no dependency:

~~~text
Do not assert start(gamma) before/after start(alpha).
Do not assert stop(gamma) before/after stop(beta).
~~~

### A test that can "pass forever" yet still be wrong

If logs on your machine always look like:

~~~text
start(alpha)
start(beta)
start(gamma)
~~~

and you assert that exact order as a contract, the test is brittle. Adding a bean, upgrading Spring, or changing a dependency can alter the accidental order. Tests should verify **what application correctness requires**, not internal details the framework never promised.

### No need to force randomness to prove the contract

Running the app a hundred times without seeing the order change **does not refute the Javadoc**. "No guarantee" means your code must not rely on the order, not that the framework is required to randomize it every run.

### Testing async shutdown

For beans that stop asynchronously, also test:

- The `stop(Runnable)` callback is invoked after actual stop work finishes.
- The callback is invoked exactly once by design.
- Timeouts are handled according to version/framework configuration.
- No consumer continues accepting work after signaling stop completion.
- Shared dependencies are not closed while the consumer still uses them.
- Context shutdown does not hang indefinitely due to a forgotten callback.

## 14. Common mistakes

**1. "Same phase means order A, B, C is decided by name."** False. The Javadoc confirms same-phase peers are ordered arbitrarily within the group.

**2. "Phase 0 starts after phase 100."** False. On startup, smaller numbers start first. On shutdown, the direction reverses.

**3. "`@Order(1)` sets `SmartLifecycle` start order."** Not an official lifecycle contract. Use `getPhase()` or `@DependsOn`.

**4. "`@Bean` declared earlier starts earlier."** Not guaranteed. Bean creation order and lifecycle startup order are two different things.

**5. "Within the same phase, stop always exactly reverses the observed start order."** There is no order guarantee for independent peers; shutdown can also be asynchronous via callbacks.

**6. "`@DependsOn` is just a hint and doesn't affect stop."** False. Explicit `depends-on` dictates the dependent starts after and stops before its dependency.

**7. "A component implementing `SmartLifecycle` without overriding `getPhase()` sits at phase 0."** False. `SmartLifecycle.DEFAULT_PHASE` is `Integer.MAX_VALUE` in Spring Framework 6.1.

**8. "`isAutoStartup=false` prevents the bean from being created."** No. It affects auto-start. Bean instantiation is a separate contract.

**9. "`@Lazy` keeps a `SmartLifecycle` bean out of startup."** Unreliable; the processor normally looks up `SmartLifecycle` beans to perform auto-start, even with lazy-init.

**10. "`start()` called earlier means the connection is already ready."** Not necessarily. If `start()` submits an async task and returns, the next dependency may start before the earlier resource is ready.

**11. "When `stop(Runnable)` returns, you can invoke the callback right away even if the consumer is still running."** False. The callback must represent **completed shutdown** of the component.

**12. "No callback is needed if shutdown is fast."** With `SmartLifecycle.stop(Runnable)`, omitting the callback can make the processor wait until timeout.

**13. "A bean at the lowest phase is always first regardless of dependencies."** Not absolute. Explicit `depends-on` relationships can override phase.

**14. "Web port bound proves all `SmartLifecycle` beans and runners are ready."** No. Boot readiness and business state have different contracts.

**15. "Numbering phases finely is enough for all complex relationships."** Phases express group order; async steps, timeouts, retries, and rollbacks need dedicated coordination or readiness logic.

**16. "If a test pinning same-phase order passes, the contract is proven."** No. That may only be one implementation's behavior in one configuration.

**17. "Using `@PreDestroy` automatically guarantees the consumer stops before the connection."** Do not assume that. For lifecycle-managed components, use phases and dependencies to express stop order.

**18. "Every Spring Framework version has `concurrentStartupForPhases` APIs."** No. Such configuration APIs belong to versions newer than 6.1; check the docs matching your dependency.

## 15. Practice exercises

1. Three beans `alpha`, `beta`, and `gamma` all return phase `0`. Why should you not assert the order `alpha, beta, gamma` if no dependency is declared?
2. Two beans have phases `-10` and `20`. Write the expected start and stop order.
3. Bean `queueConsumer` has `@DependsOn("queueConnection")` and both share phase `0`. What start/stop order is guaranteed?
4. In the section 7 project, why does `verifyStartup()` not check whether `gamma` appears before `alpha`?
5. Remove `@DependsOn` from `beta` and run again. If it still PASSES multiple times, is that enough to trust that order?
6. Change `beta`'s phase to `10` and remove the dependency. What is decided by phase? What about the relationship between `gamma` and `alpha`?
7. Add `@Order(-100)` on `gamma` while keeping phase `0`. Are you entitled to claim `gamma.start()` always runs first in the group?
8. Add `@DependsOn("storage")` onto `api`. Does this relationship reinforce or conflict with phases `storage=-100`, `api=100`?
9. Take a `SmartLifecycle` that does not override `getPhase()`. Does it default to phase 0? What is the true value?
10. Add a bean implementing only plain `Lifecycle`. Which phase does the processor treat that bean as belonging to?
11. Change `gamma`'s `isAutoStartup()` to `false`. Which parts of the demo assertions must change to match the contract?
12. Have `storage`'s `start()` submit an async connection and return immediately. Even though `storage` starts before `alpha`, why can `alpha` still fail? Propose a startup gate.
13. Write an asynchronous `stop(Runnable)` that invokes the callback only after threads/connections have closed. If the callback never runs, what happens?
14. In Spring Framework 6.1, look up `setTimeoutPerShutdownPhase` and discuss how the timeout affects multiple same-phase peers.
15. In a system with two independent consumers sharing a connection pool, do you need an ordering between the two consumers? Why might a shared phase be the right choice?
16. A bean opens resources in `@PostConstruct` and stops them in `@PreDestroy`. When should it be refactored into a `SmartLifecycle` instead of keeping only init/destroy callbacks?
17. If you need a 6-step startup sequence with retries and rollback, why can one orchestration bean be easier to test than 6 cross-dependent `SmartLifecycle` beans?
18. Name three distinct signals: "bean created", "lifecycle started", "service ready for traffic". Which signal can phase directly affect?
19. Inspect the two events `ApplicationStartedEvent` and `ApplicationReadyEvent` in an application with runners. Why do these milestones differ even though `SmartLifecycle` already started during refresh?
20. Design unit/integration tests checking only the partial order guaranteed by phase/`depends-on`, without using repeated runs to "infer" a nonexistent guarantee.

## Key takeaways

- **Lower phases start first; higher phases stop first.** That is ordering **between phase groups**.
- **Independent beans in the same phase have no guaranteed start/stop order.** Do not rely on bean names, source code order, component scanning, or `@Order`.
- **`@DependsOn` establishes an explicit ordering relationship:** the dependency starts before its dependent; the dependent stops before its dependency, even in the same phase.
- `SmartLifecycle.DEFAULT_PHASE` in Spring Framework 6.1 is `Integer.MAX_VALUE`; regular `Lifecycle` without `Phased` is typically treated as phase `0`.
- `isAutoStartup()` affects automatic `start()` calls on refresh; it is distinct from bean initialization and business readiness.
- `start()` returning does not by itself mean external resources are ready, especially if logic is async. Await readiness per contract when critical dependencies exist.
- With `stop(Runnable)`, **invoke the callback only when the component has truly stopped**. Async stopping and timeouts can affect the shutdown duration of the whole group.
- Test the **partial order** guaranteed by the contract, not an absolute sequence for same-phase peers.

### References

- Spring Framework 6.1 — `SmartLifecycle` Javadoc (phase order, same-phase arbitrary, depends-on precedence, auto-start, callback): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` Javadoc (phase grouping, dependency order, timeout): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `Phased` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/Phased.html
- Spring Framework 6.1 — `DependsOn` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html
- Spring Framework — Bean Lifecycle Callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — SpringApplication Startup and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
