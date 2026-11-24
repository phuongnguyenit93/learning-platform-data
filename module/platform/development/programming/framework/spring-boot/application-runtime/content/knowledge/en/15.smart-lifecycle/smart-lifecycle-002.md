# The Lifecycle Contract: `start()`, `stop()`, and `isRunning()` in Spring Boot 3.3

## 1. Objectives

A Spring bean can be **created successfully** while a task attached to that bean has still **not started running**. For example: a consumer has not subscribed to a broker yet, a data collector is not polling yet, or a background service has been injected without opening its connection yet. That is why Spring Framework provides the **`org.springframework.context.Lifecycle`** contract:

- `start()`: start or resume the component's operation.
- `stop()`: request the component to stop operating.
- `isRunning()`: indicate whether the component is currently considered running.

Spring Framework also provides **`SmartLifecycle`**, which extends `Lifecycle` to auto-start on `ApplicationContext.refresh()`, allows ordering start/stop by **phase**, and supports the `stop(Runnable)` callback for coordinating asynchronous shutdown.

This lesson focuses on **the Lifecycle contract and how the container invokes it in Spring Boot 3.3**. After studying it, you will be able to:

1. Distinguish a bean that is **created**, **initialized**, **running**, **stopped**, and **destroyed**.
2. Write a class that implements `Lifecycle` accurately, idempotently, and returns `isRunning()` truthfully.
3. Explain why a plain `Lifecycle` does not auto-start merely on context refresh, whereas `SmartLifecycle` can.
4. Use `ConfigurableApplicationContext.start()`, `.stop()`, and `.close()` for their intended purposes.
5. Understand `isAutoStartup()`, `getPhase()`, and `SmartLifecycle.stop(Runnable)`.
6. Build a runnable Java 21 / Spring Boot 3.3.13 demo with deterministic log ordering.
7. Avoid pitfalls with async startup/shutdown, cancellation, retries, and graceful shutdown.

**Key takeaway:** `Lifecycle` manages the **operational state of a component**, not merely Spring creating or destroying a Java object. `start()` and `stop()` should perform meaningful operations on real resources or work; `isRunning()` must reflect that actual state.

## 2. Distinguishing bean lifecycle from the Lifecycle contract

Spring manages several distinct milestones:

```text
Register BeanDefinition
      |
      +-- Create instance (constructor or factory method)
      +-- Inject dependencies
      +-- BeanPostProcessor and init callbacks
      |     +-- @PostConstruct
      |     +-- InitializingBean.afterPropertiesSet()
      |
      +-- Bean is initialized
      |     |
      |     +-- Lifecycle.start() (when requested)
      |     +-- Component is running
      |     +-- Lifecycle.stop() (when requested)
      |
      +-- Close ApplicationContext
            +-- Stop still-running lifecycle beans
            +-- Destroy singletons
                  +-- @PreDestroy / DisposableBean / destroy method
```

This diagram is conceptual; a bean might not implement `Lifecycle`, or may be lazy, prototype, or have custom mechanisms.

| Concept | Purpose | Is it synonymous with running? |
| --- | --- | --- |
| Constructor | Create the Java object and receive dependencies | No |
| `@PostConstruct` | Initialize the bean after dependency injection | Not by default |
| `Lifecycle.start()` | Activate the bean's operation or resources | Yes, if starting actually succeeded |
| `Lifecycle.isRunning()` | Observe the current operational state | Must be reflected by the implementation |
| `Lifecycle.stop()` | Stop the bean's operation | After stopping, should report false |
| `@PreDestroy` | Cleanup when the bean is destroyed | Different from temporary stop and restartability |
| `ApplicationContext.close()` | Close the entire context | Once closed, that context cannot be started again |

Example: a `MessageConsumer` may have constructor-injected `MessageClient` and passed `@PostConstruct`, yet still not have subscribed as a consumer with the broker. Only when `start()` is called does the component start receiving messages; `stop()` stops receiving messages. Meanwhile, `@PreDestroy` can still release the connection pool or final resources.

**Avoid confusion:** not every bean executes `start()`. Only objects implementing `Lifecycle` (or a corresponding extension) are managed by `LifecycleProcessor` under this contract.

## 3. The Lifecycle interface: a three-method contract

The core methods of `org.springframework.context.Lifecycle`:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

This is an **illustrative API contract excerpt**, not a file you create in your application; your application uses the interface from Spring Framework.

### 3.1. `start()`

Meaning: marks the point where the component begins operating. An implementation should:

- Be safe to call multiple times without creating duplicate consumers/threads/connections.
- Set `running` to `true` only after the **actually required startup work** succeeds.
- If startup fails, leave state reflecting reality and throw an appropriate exception.
- Not leave half-opened resources behind on partial startup failure; perform rollback/cleanup.
- Clearly define whether `start()` must wait until the component is actually operating or merely submits a background task.

Logic example:

```java
@Override
public synchronized void start() {
    if (running) {
        return;
    }

    // Activate an actual resource before reporting running.
    openConsumer();

    running = true;
}
```

This is an **illustrative snippet**; it requires an application-defined `running` field and `openConsumer()` method. When `openConsumer()` throws an exception, the flag remains false. With async startup, you must separately define when the component is considered running, and avoid reporting true before it is truly ready if the consumer is not yet connected.

### 3.2. `stop()`

Meaning: requests the component to cease operation. An implementation should:

- Be idempotent: stopping when already stopped must not throw errors or close resources a second time.
- Stop accepting new work when transitioning to stopping.
- Decide explicitly whether to wait for in-flight tasks to finish and what the maximum wait time is.
- Close/cancel resources in a safe order.
- Update `running=false` right when stopped, not merely because a stop request was just sent.

Example:

```java
@Override
public synchronized void stop() {
    if (!running) {
        return;
    }

    // Stop the resource, unregister, and reclaim resources.
    closeConsumer();

    running = false;
}
```

This is an **illustrative pattern**, not a standalone program; `closeConsumer()` must be implemented. You need a clear failure policy: if close fails, continue cleaning up whatever else is possible, log the cause, and consider having state reflect reality.

### 3.3. `isRunning()`

Meaning: reflects current operational state; it is not a command for Spring to "turn on" the component.

```java
@Override
public boolean isRunning() {
    return running;
}
```

If start/stop can be invoked from multiple threads, use proper state synchronization (`volatile`, locks, or atomic state) to ensure visibility. In the runnable example in section 7, state is held in a `volatile boolean` and transitions occur inside `synchronized` methods.

**Do not write `isRunning() { return true; }` just to avoid being started again by the container.** `LifecycleProcessor` relies on `isRunning()` to know when to call start/stop. Reporting falsely can prevent a bean from starting when needed or cause shutdown to skip resource cleanup.

### 3.4. Minimal state contract

```text
STOPPED
   | start() succeeds
   v
RUNNING
   | stop() completes
   v
STOPPED
```

Simple state transition loop:

| Initial state | Action | Expected result |
| --- | --- | --- |
| STOPPED | `start()` | RUNNING |
| RUNNING | `start()` again | Remains RUNNING, no duplicate resources created |
| RUNNING | `stop()` | STOPPED |
| STOPPED | `stop()` again | Remains STOPPED, no error |
| STARTING | concurrent `stop()` | Must have a coordination policy to avoid races |
| STOPPING | concurrent `start()` | Must have an explicit restart or rejection policy |

The last two rows apply to real systems with concurrency. A simple `boolean` is only suitable for short single-threaded/synchronous examples; production applications may need a state machine `NEW → STARTING → RUNNING → STOPPING → STOPPED → FAILED`, along with timeouts and synchronization locks.

## 4. When is Lifecycle invoked by the container?

### 4.1. Plain `Lifecycle` does not auto-start on refresh

Merely implementing `Lifecycle` does **not** mean Spring will automatically call `start()` during `ApplicationContext.refresh()`.

Spring's default `LifecycleProcessor` acts in these situations:

- The context is asked to **`start()`**: the container calls `start()` on Lifecycle beans that need starting, by phase/dependency.
- The context is asked to **`stop()`**: the container calls `stop()` on running Lifecycle beans, in stop order.
- The context **`close()`**: closing the context handles stopping still-running lifecycle components and then destroys beans.
- The context **`refresh()`**: the processor handles **auto-startup** of eligible `SmartLifecycle` beans; plain `Lifecycle` beans normally have not started yet.

Therefore, the following snippet is **not enough** to conclude a plain `Lifecycle` has started:

```java
@Component
class DataCollector implements Lifecycle {
    // Has start, stop, isRunning methods...
}
```

This is an **illustrative pattern**, not a complete Java class. The object being created/initialized does not guarantee its `start()` method is called at refresh.

### 4.2. ConfigurableApplicationContext can control lifecycle

In a controllable application context:

```java
ConfigurableApplicationContext context = ...;

context.start();  // Start Lifecycle components.
context.stop();   // Stop Lifecycle components.
context.close();  // Stop if needed, destroy beans, and close context.
```

This is an illustrative snippet requiring a `context` variable from Spring Boot or Spring Framework. The **context's** `start()` and `stop()` methods coordinate lifecycle components; they are not commands to re-refresh bean definitions or recreate an `ApplicationContext`.

Distinguish:

- `context.stop()` does not destroy singletons; `context.start()` can be called again if components support restarting.
- `context.close()` closes the context and destroys singletons; you cannot "reopen" a closed context with `start()`.
- Calling `aLifecycleBean.start()` directly only affects **that bean** and may bypass context-wide ordering/coordination; to coordinate the system, use the context lifecycle processor or an appropriate coordinator service.

### 4.3. Spring Boot lifecycle

In a typical Boot startup:

```text
SpringApplication.run(args)
  |
  +-- refresh ApplicationContext
  |     +-- init bean
  |     +-- LifecycleProcessor.onRefresh()
  |           +-- Auto-start eligible SmartLifecycle beans
  |
  +-- ContextRefreshedEvent
  +-- ApplicationStartedEvent
  +-- ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
  |
  +-- SpringApplication.run(...) returns
```

Thus, an auto-starting `SmartLifecycle` can begin **before** `ApplicationRunner` is invoked. If you want to process data after runners complete, do not treat `SmartLifecycle.start()` as an "after ready" callback.

## 5. What does SmartLifecycle add?

`org.springframework.context.SmartLifecycle` extends `Lifecycle` and `Phased`. In Spring Framework 6.1, it provides default methods and callbacks:

```java
public interface SmartLifecycle extends Lifecycle, Phased {
    default boolean isAutoStartup() { return true; }
    default int getPhase() { return Integer.MAX_VALUE; }
    default void stop(Runnable callback) {
        stop();
        callback.run();
    }
}
```

This is an **illustrative model of the default contract**, not the exact full library interface source. Do not copy it into a file to replace `org.springframework.context.SmartLifecycle`. Real overrides must conform to Spring's `SmartLifecycle`.

Comparison table:

| Aspect | `Lifecycle` | `SmartLifecycle` |
| --- | --- | --- |
| `start()` | Must implement | Inherited, still must implement |
| `stop()` | Must implement | Inherited, still must implement |
| `isRunning()` | Must implement | Inherited, still must implement |
| `isAutoStartup()` | Not present | Defaults to `true` |
| `getPhase()` | Not present (effective default phase 0) | Defaults to `Integer.MAX_VALUE` |
| `stop(Runnable callback)` | Not present | Has default; can override for async shutdown |
| Auto-start on refresh | Not by default | Yes if `isAutoStartup()==true` |
| Phased start/stop | Participates at phase 0 when `Phased` not declared | Participates according to `getPhase()` |

### 5.1. `isAutoStartup()`

By default, `SmartLifecycle.isAutoStartup()` returns `true`. When the context refreshes, `DefaultLifecycleProcessor` calls `start()` for SmartLifecycle beans deemed to need auto-starting.

If overridden to return `false`:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

The component **is not auto-started on refresh**. However, when **`context.start()`** is called explicitly, it can still be started like any other Lifecycle bean. Do not interpret `false` as "Spring will never call start".

**Warning about lazy:** `SmartLifecycle` may need to be created early by the bean factory to inspect `isAutoStartup` and manage start/stop, so `@Lazy` on a SmartLifecycle bean is not a reliable way to defer all initialization of it. If you want to control when resources are actually activated, use `isAutoStartup()` and `start()` rather than relying completely on the lazy flag.

### 5.2. `getPhase()` and start/stop ordering

When Spring coordinates lifecycle components:

- **Start in ascending phase order**: smaller phases first; larger phases later.
- **Stop in descending phase order**: larger phases first; smaller phases later.
- Plain `Lifecycle`, without separate phase metadata, has an effective phase of **0**.
- `SmartLifecycle` defaults to `Integer.MAX_VALUE`: thus a SmartLifecycle that does not override phase usually starts late and stops earlier than a Lifecycle at phase 0.
- You can override `getPhase()` to place the component in the phase appropriate for your app infrastructure.

Example:

```java
@Override
public int getPhase() {
    return 100;
}
```

If a phase-100 consumer depends on a phase-0 resource, phased startup lets the resource start before the consumer; shutdown runs in reverse.

**Limitation:** bean dependency relationships (`depends-on`, DI, and dependencies known to Spring) can **take precedence over phase ordering** during framework coordination. Do not create a phase graph contradicting the dependency graph and rely on accidental results. Beans in the **same phase** have no guaranteed ordering by class name, so use real dependencies when strict constraints exist.

### 5.3. `stop(Runnable callback)` and asynchronous shutdown

This is a very important distinction:

```java
@Override
public void stop(Runnable callback) {
    stop();
    callback.run();
}
```

In Spring Framework 6.1, `SmartLifecycle` has a similar default implementation. `DefaultLifecycleProcessor` invokes **`stop(Runnable)`** when stopping a SmartLifecycle; it does not necessarily invoke no-arg `stop()` directly unless `stop(Runnable)` delegates to it.

The callback does not mean "stop has been requested"; it must be invoked **when the stop work has finished** so the processor can move on to subsequent phases and avoid waiting until timeout. If stopping is asynchronous, the callback must run **after closing the consumer, draining work, and releasing resources** per the required contract.

Pseudo-code example for async stop:

```java
@Override
public void stop(Runnable callback) {
    shutdownExecutor.execute(() -> {
        try {
            drainAndClose(); // Return only after stopping has finished.
            running = false;
        }
        finally {
            callback.run();
        }
    });
}
```

This is **illustrative code, not standalone**: it requires `shutdownExecutor`, `drainAndClose()`, state synchronization, and handling when the executor rejects the task. In production, if `execute(...)` fails before scheduling, you must still handle fallback/callback properly, or shutdown can hang until timeout.

If stopping is handled completely synchronously, overriding `stop(Runnable)` to call no-arg `stop()` and then the callback is enough. Do not spawn a thread just to fake async shutdown.

### 5.4. Default `stop(Runnable)` does not replace no-arg stop

A SmartLifecycle implementation must understand two call paths:

- `myComponent.stop()` called directly by application code.
- `LifecycleProcessor` calling `myComponent.stop(callback)` to coordinate shutdown.

If you override `stop(Runnable)` and **forget to perform the actual stop** or forget to invoke the callback, the lifecycle processor may wait until timeout while resources remain running.

### 5.5. Timeout per shutdown phase

Spring Boot 3.3 has the property:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

The example above sets the wait time for each shutdown phase. The timeout does not guarantee every thread has stopped if the implementation is buggy or a resource hangs. When configuring graceful shutdown for a web application in Boot 3.3, you can set:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This configuration belongs to **an appropriate web project**; it does not turn the non-web program in section 7 into an HTTP service. Allow enough shutdown time for real business work, while designing tasks to be idempotent/recoverable after timeout expiration.

## 6. Lifecycle, Context, and application ordering

### 6.1. Context refresh does not automatically call start on every bean

`SpringApplication.run(...)` triggers context `refresh()`. The lifecycle processor auto-starts SmartLifecycle beans that allow auto-start, but **plain Lifecycle beans do not run automatically** just because the context refreshes.

That does not mean plain Lifecycle is useless. Some systems want to create beans at startup and only start receiving messages when an operator calls `context.start()`, when a configuration is enabled, or when a coordinator issues a command.

### 6.2. Lifecycle stop differs from bean destroy

On `context.stop()`:

- Spring calls stop on running lifecycle components.
- Beans remain in the container; an active context can call `start()` again.
- `@PreDestroy` is not part of `stop()` by default.

On `context.close()`:

- Spring stops running lifecycle components.
- The context proceeds to singleton destruction and cleanup.
- `@PreDestroy`/destroy methods may be invoked for eligible beans.
- A closed context cannot be restarted with `context.start()`.

**Pitfall to avoid:** `isRunning()==false` does not mean the bean has been destroyed. It is only a signal about the **operational state** defined by `Lifecycle`.

### 6.3. Lifecycle start is not equivalent to availability READY

Spring Boot also has `ApplicationAvailability` and `ReadinessState`. A `SmartLifecycle` reporting `isRunning()==true` for **one component** does not prove the entire application has finished runners, is healthy, or is ready to accept traffic. Wire business requirements into readiness probes/health checks in the right place.

Typical sequence:

```text
refresh context
  -> start SmartLifecycle auto components
  -> ApplicationStartedEvent
  -> ApplicationRunner and CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
```

If a component launches an async task and returns right away with `isRunning()` reporting true too early, Spring Boot can still reach ready while the subsystem is not yet ready. You must define startup completion and readiness clearly.

## 7. Complete example: plain Lifecycle vs. SmartLifecycle

Demo goals:

- `ManualPollingWorker` implements **`Lifecycle`**. After `SpringApplication.run(...)`, the bean is created but not running yet. It starts only when **`context.start()`** is called explicitly.
- `AutoPollingWorker` implements **`SmartLifecycle`**, `isAutoStartup()` true, `getPhase()==100`. It auto-starts during context refresh.
- `context.stop()` stops `AutoPollingWorker` at phase 100 **before** `ManualPollingWorker` at phase 0.
- `isRunning()` confirms state before and after each operation.
- After `context.stop()`, `try-with-resources` closes the context to release resources without calling stop again on already-stopped beans.

### 7.1. Project structure

```text
lifecycle-contract-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/lifecycle/
    │       ├── LifecycleContractApplication.java
    │       ├── ManualPollingWorker.java
    │       └── AutoPollingWorker.java
    └── test/
        └── java/com/example/lifecycle/
            └── LifecycleContractTest.java
```

### 7.2. Maven

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-contract-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` is sufficient to create a non-web application with an `ApplicationContext`. `spring-boot-starter-test` provides JUnit Jupiter and Spring context testing tools.

### 7.3. Plain Lifecycle bean

File `src/main/java/com/example/lifecycle/ManualPollingWorker.java`:

```java
package com.example.lifecycle;

import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public class ManualPollingWorker implements Lifecycle {

    private volatile boolean running;

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        // Demo creates no real thread: simulates enabling polling.
        running = true;
        System.out.println("MANUAL start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        // Demo creates no real thread: simulates disabling polling.
        running = false;
        System.out.println("MANUAL stop");
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

There is no `@PostConstruct` launching polling; constructor/bean creation does not imply start. Only when `context.start()` or an appropriate `start()` call occurs does `running` become true.

`synchronized` serializes flag transitions in the demo; `volatile` makes updates visible to other threads. In production, if start/stop takes time, do not hold locks indefinitely; add timeouts and a state machine to coordinate races.

### 7.4. Auto-starting SmartLifecycle bean

File `src/main/java/com/example/lifecycle/AutoPollingWorker.java`:

```java
package com.example.lifecycle;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class AutoPollingWorker implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        // Demo creates no real thread: simulates enabling task intake.
        running = true;
        System.out.println("AUTO start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        running = false;
        System.out.println("AUTO stop");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        }
        finally {
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
}
```

`stop(Runnable)` invokes synchronous stop and then notifies the lifecycle processor of completion. `finally` ensures the callback is invoked even if a cleanup step throws an exception; in production, you must log errors, determine resource state, and apply an appropriate policy rather than assuming "callback ran" equals "resource stopped cleanly".

`isAutoStartup()==true` is already the Spring Framework 6.1 default; it is overridden here so learners see the contract clearly. `getPhase()==100` allows comparing against plain `Lifecycle` at effective phase 0.

### 7.5. Main class

File `src/main/java/com/example/lifecycle/LifecycleContractApplication.java`:

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class LifecycleContractApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LifecycleContractApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            AutoPollingWorker auto = context.getBean(AutoPollingWorker.class);
            ManualPollingWorker manual =
                    context.getBean(ManualPollingWorker.class);

            System.out.println("MAIN initial auto=" + auto.isRunning()
                    + ", manual=" + manual.isRunning());

            context.start();
            System.out.println("MAIN after-start auto=" + auto.isRunning()
                    + ", manual=" + manual.isRunning());

            context.stop();
            System.out.println("MAIN after-stop auto=" + auto.isRunning()
                    + ", manual=" + manual.isRunning());
        }
    }
}
```

`app.run(args)` already includes refresh, `ApplicationStartedEvent`, runners (if any), and `ApplicationReadyEvent`; when the method returns, the auto-starting SmartLifecycle is already active. `context.start()` calls the lifecycle processor and starts the non-running plain Lifecycle. `context.stop()` stops both by phase; the context can still be `start()`ed again if desired. The demo closes the context after printing the state.

### 7.6. Running the program

JDK 21, Maven, and appropriate dependency download access are required. Inside the `lifecycle-contract-demo` directory:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/lifecycle-contract-demo-0.0.1-SNAPSHOT.jar
```

The lines **explicitly printed by the demo code**, ignoring the banner and Spring Boot logging, appear in this order:

```text
AUTO start
MAIN initial auto=true, manual=false
MANUAL start
MAIN after-start auto=true, manual=true
AUTO stop
MANUAL stop
MAIN after-stop auto=false, manual=false
```

Detailed explanation:

1. `AUTO start` happens during context refresh, because `SmartLifecycle.isAutoStartup()==true`.
2. When `app.run(args)` returns, auto is running, manual is not running.
3. `context.start()` causes the plain Lifecycle to start. Auto is already running so it does not start again.
4. `context.stop()` stops phase 100 **before** phase 0: `AUTO stop` then `MANUAL stop`.
5. Both running flags are false. `context.close()` in `try-with-resources` cleans up the context; the two beans do not need to run stop again because they are already in the stopped state.

**Important:** the printed lines have no real polling or network connection code; the demo only simulates state. For production use, put actual resource registration and teardown into start/stop, ensuring flags only reflect real outcomes.

### 7.7. Context lifecycle restart exercise

In `main`, after `context.stop()` and before leaving the `try` block, you can try:

```java
context.start();
System.out.println("MAIN restarted auto=" + auto.isRunning()
        + ", manual=" + manual.isRunning());
```

This is a snippet **added to `main` where `context`, `auto`, and `manual` already exist**, not a standalone program. Because both are currently stopped, `context.start()` will invoke `MANUAL start` at phase 0 before `AUTO start` at phase 100. Afterward, `close()` will stop the two still-running beans in reverse phase order.

This illustrates: **auto-startup only decides activation at refresh; phase decides coordination order when starting/stopping**. If there are real dependencies between components, see section 9 on dependency-based ordering.

## 8. JUnit test to verify the contract

You do not need to inspect all Spring Boot logs. You can test the bean states directly.

File `src/test/java/com/example/lifecycle/LifecycleContractTest.java`:

```java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = LifecycleContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LifecycleContractTest {

    @Autowired
    private AutoPollingWorker auto;

    @Autowired
    private ManualPollingWorker manual;

    @Autowired
    private ConfigurableApplicationContext context;

    @Test
    void autoStartsButPlainLifecycleNeedsExplicitStart() {
        assertTrue(auto.isRunning());
        assertFalse(manual.isRunning());

        context.start();
        assertTrue(auto.isRunning());
        assertTrue(manual.isRunning());

        context.stop();
        assertFalse(auto.isRunning());
        assertFalse(manual.isRunning());
    }
}
```

`@SpringBootTest` creates a real context without invoking the demo's `main(...)` that executes `context.start()` inside `try`. Thus the test can observe `auto` running and `manual` stopped right after refresh. `@DirtiesContext` ensures the context is evicted from Spring Test's cache after the class, reducing stopped-state leakage to other tests.

Run:

```bash
mvn test
```

Expect **1 test passed, 0 failures, 0 errors** for this class, if no other tests are added. `mvn package` runs tests by default so you may observe auto start/stop logs during the test phase; that is output from lifecycle beans in the test, **not a run of main**.

If you want to test real concurrency/async stop, use concurrency primitives (latches/futures) and timeouts instead of `Thread.sleep(...)` and guessing that the task has finished.

## 9. Phase and dependencies: how to coordinate multiple components

Suppose one component provides a data source and another component processes data. The system might need:

```text
START:
  resourceProvider (phase 0)
       |
       v
  consumer (phase 100)

STOP:
  consumer (phase 100)
       |
       v
  resourceProvider (phase 0)
```

This is where phase is especially useful: the work receiver starts after its dependency source and stops before its dependency source.

However, **phase is not a vehicle for expressing every bean dependency**. If the consumer genuinely uses `ResourceProvider`, use constructor injection. For side-effect initialization dependencies, consider `@DependsOn`, in which case `LifecycleProcessor` also factors the dependency into coordination.

Illustrative example:

```java
@Component
class ConsumerCoordinator implements SmartLifecycle {

    private final ResourceProvider resourceProvider;

    ConsumerCoordinator(ResourceProvider resourceProvider) {
        this.resourceProvider = resourceProvider;
    }

    // start(), stop(), isRunning(), and getPhase()
    // are implemented according to the contract above.
}
```

This is a **non-standalone design pattern**: it requires defining `ResourceProvider` and implementing the methods. Spring knows the bean dependency through constructor injection, so you do not need to rely on bean names to hope for ordering.

### 9.1. Does the same phase guarantee alphabetical order?

**No.** If two Lifecycle beans share the same phase and have no dependency between them, their relative order may depend on container registration/initialization order. Do not rely on class names, file names, or `@Order` as a way to automatically dictate all start/stop ordering.

When A must operate before B, create a real dependency, put them into a coordinator, or design phases matching the contract. Avoid creating circular dependencies.

### 9.2. `@Order` differs from `getPhase()`

`@Order` is typically used for sorting collections/strategies or callbacks at extension points that support ordering. `getPhase()` is the **lifecycle start/stop order** contract. They do not substitute for each other.

| Need | Mechanism |
| --- | --- |
| Sort `List<Handler>` by processing priority | `@Order` |
| Control `start()`/`stop()` order of lifecycle components | `Phased` / `SmartLifecycle.getPhase()` |
| B must receive instance A when constructor runs | Constructor injection |
| B needs A's init side effects to complete | `@DependsOn` when no object dependency fits |
| B only runs after A finishes async work | Future/callback coordination or explicit workflow state |

### 9.3. `isAutoStartup=false` does not mean phase is ignored

A SmartLifecycle returning `false` from `isAutoStartup()` will not auto-start on refresh, but when the context is manually `start()`ed, its `getPhase()` still matters for coordination. When the context `stop()`s/`close()`s, **running** components are still handled accordingly.

## 10. Contract with asynchronous work

### 10.1. Asynchronous start: when to report running?

If `start()` merely submits a task and returns:

```java
@Override
public void start() {
    executor.submit(this::connectToBroker);
    running = true;
}
```

This is an **illustrative anti-pattern snippet**, not a standalone file. `running=true` is set before `connectToBroker` has actually connected successfully. `isRunning` can therefore report true while the component cannot serve yet.

Better designs depending on requirements:

- If the broker must be ready **before startup finishes**, start can wait for the connection with a timeout and report an error clearly on failure.
- If background connecting is acceptable, use a `STARTING`/`RUNNING` state machine and only transition to `RUNNING` when connecting succeeds. `Lifecycle.isRunning` is a Boolean, so an additional internal status API may be needed for diagnostics.
- If whole-application readiness depends on the connection, combine health checks and startup readiness policy instead of trusting the `isRunning()` boolean alone.

### 10.2. Asynchronous stop: callback must happen at the right time

A SmartLifecycle may allow stopping in the background, but **must invoke the callback after stopping has finished**:

```text
LifecycleProcessor
    |
    +-- stop(callback)
          +-- Stop accepting new work
          +-- Complete/drain in-flight work
          +-- Close resources
          +-- Set isRunning=false
          +-- callback.run()     <-- report actual completion
```

**Do not** invoke the callback right upon enqueuing shutdown if cleanup is still running behind the scenes. When the callback is omitted, the processor may wait until the per-phase timeout, delaying or breaking application shutdown.

With event-driven or external resource shutdown, you must confirm when the task terminates. Use `CompletableFuture.whenComplete`, a latch/ack, or a completion signal with error handling; the callback must be invoked exactly once even if cleanup fails, while clearly reporting errors for observability. If the callback is invoked too early, shutdown can advance to the next phase and close dependencies before the consumer has fully stopped.

### 10.3. Thread safety and memory visibility

`isRunning()` is often called from the lifecycle processor, health checks, and application code on different threads. If updating the flag lacks memory visibility, another thread may read stale state.

- Use `volatile`, `AtomicBoolean`, or an appropriate lock.
- Ensure `start()`/`stop()` are idempotent under repeated calls.
- If state has multiple phases, a single boolean may lack information.
- Do not hold a lock while waiting for a resource that another thread needs the same lock to finish: easy deadlock.
- Have finite timeouts and handle `InterruptedException` by restoring the interruption flag when needed.

**The demo example** keeps start/stop logic short and synchronous, so `volatile` and `synchronized` suffice to explain the contract. It does **not** replace real-world thread pool, consumer, and shutdown management.

### 10.4. Shutdown in Kubernetes or containers

In real deployments, orchestration may send a stop signal to the process. For Spring to process `SmartLifecycle.stop(Runnable)`, the context must be closed in a controlled way.

- A forced kill gives no guarantee that stop callbacks or `@PreDestroy` will run.
- Configure graceful shutdown and reasonable wait durations.
- Stop accepting new work before cutting off underlying resources.
- Do not rely on shutdown hooks to guarantee "exactly once"; a consumer can be killed mid-step.
- Message-processing tasks should have proper idempotency, retries, and checkpointing to recover.

In a Boot web application, graceful HTTP shutdown and custom SmartLifecycle phases can interact; check the actual phases and dependencies of the server and consumer, and do not pick arbitrary phase numbers when strict ordering is required.

## 11. Common errors and fixes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `Lifecycle` bean created but `start()` doesn't run on Boot startup | Plain Lifecycle does not auto-start on refresh | Call `context.start()` or use auto-starting `SmartLifecycle` |
| `SmartLifecycle` does not auto-start | `isAutoStartup()` returns false, bean not registered, or startup error | Check registration, auto-start flag, exceptions |
| `isRunning()` stays true even though consumer stopped | Flag only set in constructor or not updated on stop | Only flip flag when resource actually starts/stops |
| Calling `start()` twice creates two consumers | Non-idempotent implementation | Check state and synchronize start |
| Calling `stop()` twice throws an error | Not designed for idempotency | Check state before cleanup |
| `stop(Runnable)` fails to invoke callback | LifecycleProcessor waits until timeout, prolonging shutdown | Invoke callback exactly once after stopping finishes |
| Callback invoked right when enqueuing shutdown | Later phase may close dependency too early | Invoke after real completion signal |
| SmartLifecycle's `stop()` not called by processor | Processor calls `stop(Runnable)` overload | Implement/delegate the callback overload properly |
| `@Order(1)` does not make bean start earlier | `@Order` differs from `getPhase()` | Use phase and dependency graph |
| Large `getPhase()` yet startup doesn't match expectation | Dependency overrides phase or same phase | Inspect DI/`depends-on` and phases |
| `@Lazy` does not defer SmartLifecycle as expected | Auto-start lifecycle may pull bean during refresh | Use `isAutoStartup()` for toggling auto-start |
| `context.stop()` does not run `@PreDestroy` | Stop is not destroy | Use `context.close()` to close the entire context |
| Calling `context.start()` after `context.close()` | Context is already closed | Create a new context via `SpringApplication.run(...)` if needed |
| Component running yet app is not ready | One running bean does not mean app readiness | Check runners, `ApplicationAvailability`, health probes |
| Exception in `start()` swallowed | Processor thinks start succeeded despite broken resource | Propagate or handle error with truthful state |
| Shutdown times out | Slow async stop, deadlock, callback not invoked, or unresponsive broker | Timeouts, drain protocol, cancellation, and observability |

### 11.1. Diagnostic checklist

1. Is the bean actually registered with Spring (`@Component`, `@Bean`)?
2. Does it implement `Lifecycle` or `SmartLifecycle`?
3. Does `isAutoStartup()` return true? Has the context refreshed?
4. Does `isRunning()` initially reflect false accurately?
5. Does `start()` actually activate the resource or just submit an async task?
6. Are there dependencies/phases altering startup order?
7. Is `stop(Runnable)` called and does the callback run after stopping completes?
8. Is the context calling `stop()` or `close()`? Is it already closed?
9. Is any caller invoking start/stop directly and bypassing the processor?
10. Are there races between start/stop, timeouts, or interrupts?
11. Does application readiness require more than the bean's `isRunning()`?
12. Are there logs/metrics distinguishing `STARTING`, `RUNNING`, `STOPPING`, and `FAILED`?

## 12. Real-world scenarios

### 12.1. Message broker consumer

At app startup, the client connection is injected while the consumer has not subscribed yet. `SmartLifecycle.start()` can perform message subscription; `stop(Runnable)` stops new intake, drains in-flight messages, and then invokes the callback. If a coordinator must ensure the database/resource provider exists before the consumer, use appropriate dependencies and phases.

### 12.2. A task collector that only runs when enabled by an operator

A component implements only plain `Lifecycle`. The app creates the bean without starting the collector. When an operator triggers an administrative flow, a coordinator can invoke the lifecycle API per policy. Avoid exposing `context.start()` directly to arbitrary requests because it affects **all** eligible Lifecycle components, not just the collector.

### 12.3. Traffic-serving server and background worker

In a web app, a worker's `SmartLifecycle` can start during refresh, before `ApplicationReadyEvent`. If the worker should only process work after startup checks complete, you need a coordinator/runner/ready policy rather than assuming `start()` equals "app ready".

### 12.4. Graceful rolling deployment

When an orchestrator requests shutdown, the app should drain traffic, stop accepting new work, wait for in-flight work within a finite deadline, flush state, and release resources. `SmartLifecycle.stop(Runnable)` provides a cooperation point with Spring's shutdown processor; however, traffic routing and retries still require configuration in the load balancer, consumer, or Kubernetes.

### 12.5. Singleton bean that needs operational restarts

A singleton can stay alive in the context while `Lifecycle.stop()` temporarily pauses it. If the implementation supports restarting, `Lifecycle.start()` can turn it back on. This is an important difference from destroying and recreating a bean.

## 13. Self-check exercises

1. How does `@PostConstruct` differ from `Lifecycle.start()`? Is an initialized bean necessarily running?
2. Write the signatures of the three methods of `Lifecycle`; what should `isRunning()` reflect?
3. Why might a bean implementing only `Lifecycle` and annotated with `@Component` not start when Boot starts up?
4. In the example, why does the `AUTO start` line appear before `MAIN initial`?
5. Why does `MANUAL start` only appear after `context.start()`?
6. Why does `AUTO stop` happen before `MANUAL stop` on `context.stop()`?
7. Does `isAutoStartup=false` prevent manual context start?
8. Compare the default phases of plain `Lifecycle` and `SmartLifecycle` in Spring Framework 6.1.
9. What happens when two lifecycle beans have the same phase and no dependency? Should you rely on bean names to guess order?
10. How does `stop(Runnable)` differ from no-arg `stop()`? Why is the callback important?
11. If a `stop(Runnable)` implementation invokes the callback **before** resources close, what consequences can happen in the next shutdown phase?
12. If a `SmartLifecycle.start()` just submits a background task and sets `running=true`, what is wrong with the semantics of `isRunning()`?
13. Does `context.stop()` trigger `@PreDestroy`? How does `context.close()` differ?
14. After `context.close()`, can you use `context.start()` to recover the context?
15. Given DI dependency A → B and opposing `getPhase()` values: can the framework prioritize the dependency relationship?
16. Does `@Order(1)` on a bean have the same meaning as `getPhase()==1`? Explain.
17. For a CLI app with two lifecycle beans, why does one self-running bean not equate to `ReadinessState.ACCEPTING_TRAFFIC`?
18. How do you test idempotency of start/stop and that the stop callback is invoked at the right time?
19. Describe how to handle shutdown when the broker does not respond before timeout.
20. For a production consumer, propose a state machine with at least `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED` and transition criteria.

**Passing criteria:** run the non-web Spring Boot example; explain the output lines accurately; understand the exact meaning of `start`, `stop`, and `isRunning`; distinguish plain `Lifecycle` and `SmartLifecycle`; know how to apply phases and shutdown callbacks without mistaking them for readiness or real dependencies.

## 14. Official references

- Spring Framework 6.1 — `Lifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/Lifecycle.html
- Spring Framework 6.1 — `SmartLifecycle` and default methods: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `LifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/LifecycleProcessor.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `ConfigurableApplicationContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Boot 3.3 — Graceful Shutdown and `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — SpringApplication / Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
