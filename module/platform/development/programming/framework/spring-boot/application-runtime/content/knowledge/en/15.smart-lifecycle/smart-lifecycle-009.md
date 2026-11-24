# Per-Phase Shutdown Timeout of DefaultLifecycleProcessor in Spring Boot

## 1. Why does shutdown need a per-phase timeout?

A Spring Boot application often has multiple long-lived components: HTTP server, message consumer, scheduler, streaming processor, connection pool, task-processing worker, and components managing connections to external systems. When the application stops, merely issuing a single "stop everything" command is not enough.

Suppose a message consumer uses a storage client:

1. On startup, the **storage client must become active first**.
2. Only then can the consumer receive and process messages.
3. On shutdown, the **consumer must stop accepting new work first**.
4. The storage client must stay alive so the consumer can finish in-flight work.
5. Finally, the storage client is stopped.

Spring Framework provides **Lifecycle**, **SmartLifecycle**, and **DefaultLifecycleProcessor** to organize starting/stopping these components by **phase**. For components that stop asynchronously, Spring needs to know **how long to wait at most** before moving forward with shutdown.

**Timeout per shutdown phase** is the maximum duration `DefaultLifecycleProcessor` spends **waiting for the group of SmartLifecycle beans with the same phase value to invoke their stop-completion callbacks**. It is not a per-bean timeout, not a mandatory total deadline for the entire JVM, and not a command that forcibly kills threads when expired.

Sentence to remember:

> **Phase determines order, stop(Runnable) signals completion, timeout-per-shutdown-phase bounds the wait time for a phase group.**

This topic belongs to **Spring Boot Application Runtime → SmartLifecycle**. Spring Boot configures `DefaultLifecycleProcessor` in the `ApplicationContext` and provides a property allowing operators to customize the timeout for shutdown phases.

## 2. Participating APIs

| Component | Responsibility |
| --- | --- |
| **Lifecycle** | Declares `start()`, `stop()`, `isRunning()` for a component |
| **Phased** | Provides `getPhase()` to express ordering |
| **SmartLifecycle** | Extends `Lifecycle` and `Phased`, adding `isAutoStartup()` and `stop(Runnable)` |
| **LifecycleProcessor** | Coordinates starting/stopping Lifecycle beans in the context |
| **DefaultLifecycleProcessor** | Default `LifecycleProcessor` implementation; manages phase groups and wait timeouts |
| **ApplicationContext.refresh()** | Activates the context; triggers auto-start for eligible `SmartLifecycle` beans |
| **ApplicationContext.close()** | Begins context shutdown; lifecycle processor requests beans to stop |
| **spring.lifecycle.timeout-per-shutdown-phase** | Spring Boot property configuring the default wait limit **per phase** |

In Spring Framework 6.2, the full class name is:

~~~java
org.springframework.context.support.DefaultLifecycleProcessor
~~~

Related interface:

~~~java
org.springframework.context.SmartLifecycle
~~~

A typical `SmartLifecycle` implementation:

~~~java
public final class WorkerLifecycle implements SmartLifecycle {

    @Override
    public void start() {
        // Start accepting and processing work.
    }

    @Override
    public void stop() {
        // Synchronous stop if called directly.
    }

    @Override
    public void stop(Runnable callback) {
        // Request stop; invoke callback.run() after actually stopped.
    }

    @Override
    public boolean isRunning() {
        return false;
    }

    @Override
    public int getPhase() {
        return 200;
    }
}
~~~

The snippet above only **illustrates API signatures**; it is not a working program yet because imports, running state, and cleanup logic are omitted. Section 7 provides a complete runnable Java example.

### How does SmartLifecycle.stop(Runnable) differ from Lifecycle.stop()?

**Lifecycle.stop()** usually represents synchronous stopping: when the method returns, the component should already have stopped running.

**SmartLifecycle.stop(Runnable callback)** allows asynchronous stopping. `LifecycleProcessor` calls this method and waits for **`callback.run()`** to know the component has stopped; it cannot infer completion solely from `stop(Runnable)` returning.

The `SmartLifecycle` Javadoc emphasizes that the callback **must be invoked after shutdown actually completes**, avoiding wasted wait time or timeouts in overall shutdown.

If code **never invokes the callback**, the processor may wait until the phase timeout expires even if the component stopped long ago.

## 3. Phase order on start and stop

Spring Framework uses the integer returned by **`SmartLifecycle.getPhase()`**.

- **Start:** **smaller** phase first, **larger** phase later.
- **Stop:** **larger** phase first, **smaller** phase later.
- **Negative values** are typically suited for infrastructure that must live early and stop late.
- **Positive values** are typically suited for components depending on infrastructure: start late, stop early.
- Default `SmartLifecycle` has **`getPhase() = Integer.MAX_VALUE`**, so without overriding, it typically starts very late and stops very early.
- A plain **Lifecycle** bean not implementing `SmartLifecycle`/`Phased` is assigned default phase **0** by `DefaultLifecycleProcessor`.

Example:

| Component | Phase | On start | On stop |
| --- | ---: | --- | --- |
| Storage client | -100 | 1 | 4 |
| Internal registry | 0 | 2 | 3 |
| Message consumer | 100 | 3 | 2 |
| Request intake | 200 | 4 | 1 |

~~~text
START:
phase -100 -> phase 0 -> phase 100 -> phase 200

STOP:
phase 200 -> phase 100 -> phase 0 -> phase -100
~~~

Within a same-phase group of beans, do not rely on a fixed order not guaranteed by the docs. If component A must stop before B, design explicit dependencies/phases and test them.

**Spring honors `depends-on` relationships** even when dependency order conflicts with expected phases. A component needing its dependency alive while stopping must declare the proper dependency; `getPhase` cannot be treated as a full dependency-management mechanism.

### @Order does not replace getPhase()

**@Order** is typically used to sort lists of components, filters, or runners under their respective contracts. It is **not** a way to declare `SmartLifecycle` lifecycle ordering. To set phase, override **`getPhase()`** or implement **`Phased`** per the API.

## 4. How is per-phase shutdown timeout applied?

During context close, `DefaultLifecycleProcessor` groups Lifecycle beans by phase. For a group:

1. The processor selects the phase with higher stop priority.
2. For running `SmartLifecycle` beans, it calls **`stop(Runnable)`** and tracks completion callbacks.
3. Beans in the same phase can execute cleanup **asynchronously within the same wait window**.
4. The processor waits for that group up to the **phase timeout**.
5. Once all required callbacks are invoked, the processor can advance immediately without waiting the full timeout.
6. If the timeout expires while callbacks are still missing, the processor may log a warning and proceed to subsequent phases.

Example with three phases:

~~~text
timeout-per-shutdown-phase = 5 seconds

Phase 200: receiver-A and receiver-B
  stop(receiver-A) takes 1 second
  stop(receiver-B) takes 4 seconds
  -> wait for phase 200 group ~4 seconds, not 1 + 4
  -> phase 100 starts after group 200 finishes

Phase 100: scheduler
  stop() finishes after 2 seconds
  -> wait ~2 seconds

Phase 0: infrastructure
  stop() finishes after 1 second
  -> wait ~1 second

Wait time across groups ≈ 4 + 2 + 1 = 7 seconds
~~~

This is a **conceptual example** for stop callbacks executed asynchronously, not real measured timings. Software incurs extra overhead, other callbacks, destroy methods, GC, OS scheduling, and dependency conditions.

If phase 200 has **10 beans**, a 5-second timeout is still the **wait budget for the entire phase-200 group**, not 10 × 5 seconds.

### What happens if a phase fails to stop or exceeds the timeout?

With contract-compliant async stop, timeout expiration does not necessarily force running cleanup to terminate. The processor may move on so it does not hang forever in the same phase. Dangerous consequence: a lower-phase bean can be stopped while a higher-phase bean **is still cleaning up and still needs to use it**.

Therefore, timeouts must be **long enough for resources to stop safely**, and implementations must invoke callbacks **at the right time**. Do not use a tiny timeout to mask a forgotten callback or a consumer lacking a mechanism to stop receiving messages.

## 5. Distinguishing types of timeouts to configure

| Concept | What does it bound? | Same as timeout per phase? |
| --- | --- | --- |
| **Timeout per shutdown phase** | Wait time for callbacks of a SmartLifecycle group sharing a phase | This lesson's exact topic |
| **Timeout for a specific phase** | Dedicated override for a chosen phase | Same mechanism, specific config takes precedence |
| **Graceful HTTP shutdown timeout** | Time web server processes active requests during shutdown phase | Related; may share a SmartLifecycle phase budget |
| **Executor shutdown wait timeout** | Waiting for running tasks per executor settings | Separate lifecycle mechanism, must coordinate |
| **Network connection timeout** | Waiting on network connect/read/write | Not replaced by lifecycle timeout |
| **Kubernetes terminationGracePeriodSeconds** | Total budget for container to exit cleanly before force-kill | Enclosing outer limit, not identical |
| **preStop hook duration** | Time hook runs before process shutdown signal | Also consumes shutdown grace budget |
| **JVM shutdown hook** | JVM mechanism invoking callbacks on process shutdown | Does not mean JVM waits for just one single phase timeout |

Do not confuse **timeout per phase** with **a single JVM-wide countdown clock**. For example, four phases with a 5-second max timeout each can add up to nearly 20 seconds of wait time, **plus** other cleanup work. In practice it can be shorter if callbacks report completion early.

Especially, if a **`stop(Runnable)` implementation runs long blocking work right on the calling thread** instead of quickly starting async shutdown and returning, phase timeout **does not automatically interrupt** that blocking method. Handle I/O timeouts explicitly and design `stop` to make progress when dependencies are unresponsive.

## 6. Default values and how to configure in Spring Boot 3.5

### 6.1. Common property

Spring Boot 3.5 supports:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

The value is a **`Duration`**. Common suffixes include **`ms`**, **`s`**, and **`m`** per Spring Boot's binding contract. For example:

~~~properties
# Up to 500 milliseconds per phase:
spring.lifecycle.timeout-per-shutdown-phase=500ms
~~~

Or when more time is needed for in-flight requests:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=45s
~~~

This property sets the **default across phase groups** for the lifecycle processor auto-configured by Spring Boot. It does not by default turn all of shutdown into a single 45-second absolute deadline.

### 6.2. Do not confuse Framework defaults with Boot defaults

Version documentation matters:

- **Spring Framework 6.2 `DefaultLifecycleProcessor` JavaDoc** states the internal default per-phase timeout is **10,000 ms (10 seconds)** when not configured otherwise.
- **Spring Boot 3.5 Common Application Properties** states the default of **`spring.lifecycle.timeout-per-shutdown-phase`** is **30 seconds**. Boot auto-configures the lifecycle processor to apply this property.

Therefore, do not deduce that a Boot 3.5 app defaults to 10 seconds/phase just because you read Spring Framework's raw JavaDoc. With Boot 3.5 under normal auto-configuration, the **reference default is 30 seconds/phase**.

If a project supplies a custom **`lifecycleProcessor`** bean, excludes/alters auto-configuration, or uses another version, confirm the effective value empirically. Do not claim all Spring applications regardless of configuration share the same default.

### 6.3. Per-phase configuration via Framework 6.2 API

If one phase needs a very different budget from the rest, Spring Framework 6.2 provides an API:

~~~java
DefaultLifecycleProcessor processor =
        new DefaultLifecycleProcessor();

processor.setTimeoutPerShutdownPhase(5_000L);
processor.setTimeoutForShutdownPhase(200, 15_000L);
~~~

This is an **illustrative code fragment**, not a standalone runnable program; it requires importing **`org.springframework.context.support.DefaultLifecycleProcessor`** and registering this processor on the appropriate context.

Meaning:

- Phases not overridden: use 5,000 ms.
- **Phase 200:** uses 15,000 ms.
- Individual overrides can be set for multiple phases using **`setTimeoutsForShutdownPhases(Map<Integer, Long>)`**.

The **`setTimeoutForShutdownPhase`** and **`setTimeoutsForShutdownPhases`** APIs were added in Spring Framework **6.2**. Do not use that exact code on Spring Framework 6.1 or a version lacking those APIs.

You can replace the lifecycle processor via a bean named **`lifecycleProcessor`**:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

@Configuration(proxyBeanMethods = false)
public class PhaseTimeoutPolicy {

    @Bean(name = "lifecycleProcessor")
    DefaultLifecycleProcessor lifecycleProcessor() {
        DefaultLifecycleProcessor processor =
                new DefaultLifecycleProcessor();

        processor.setTimeoutPerShutdownPhase(5_000L);
        processor.setTimeoutForShutdownPhase(200, 15_000L);
        return processor;
    }
}
~~~

This is a **complete Java configuration class**; if placed into a Spring Boot 3.5 project under a component-scanned package, it provides a custom lifecycle processor and replaces the default processor configuration when the bean name matches.

**Configuration note:** Once a custom `lifecycleProcessor` is defined, do not assume Spring Boot will keep applying **`spring.lifecycle.timeout-per-shutdown-phase`** to your custom bean. Configure the processor directly in this code or verify actual auto-configuration/conditional behavior. The two configuration approaches above are **two alternatives**, not automatically combined by default.

**Upgrade note:** Do not replace `DefaultLifecycleProcessor` with a custom bean of differing behavior if all you need is a single shared timeout. Boot's property is usually shorter and less risky.

## 7. Runnable Java 17+ example: seeing phases, callbacks, and wait time

The Spring Boot 3.5.x example below illustrates:

1. Two `SmartLifecycle` components at phases **100** and **200**.
2. Phase 100 starts **before** phase 200.
3. On context close, phase 200 stops **before** phase 100.
4. Each `stop(Runnable)` spawns a small cleanup thread and returns; `DefaultLifecycleProcessor` waits for the callback.
5. When the timeout exceeds cleanup duration, context close finishes only after both callbacks.
6. No web server is needed; a non-web example makes the lifecycle easy to observe.

### 7.1. Creating the project

Use Spring Initializr: **Maven**, **Java 17 or newer**, **Spring Boot 3.5.x**, group **com.example**, artifact **lifecycle-demo**, package **com.example.demo**. Select **Spring Boot Starter**; Spring Web is not needed.

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=lifecycle-demo
spring.main.web-application-type=none

# Maximum timeout PER phase, large enough for the demo:
spring.lifecycle.timeout-per-shutdown-phase=2s
~~~

No `server.port` is needed because this is a non-web app. Even if the project has other starters on the classpath, `web-application-type=none` tells Boot to run in non-web mode.

### 7.2. Complete Java file

Create **src/main/java/com/example/demo/PhaseTimeoutDemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PhaseTimeoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PhaseTimeoutDemoApplication.class);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("RUN_RETURNED active="
                    + context.isActive());
        }

        System.out.println("CONTEXT_CLOSED");
    }

    @Bean
    SmartLifecycle storage() {
        return new DemoLifecycle("storage", 100, 250);
    }

    @Bean
    SmartLifecycle consumer() {
        return new DemoLifecycle("consumer", 200, 350);
    }

    static final class DemoLifecycle implements SmartLifecycle {

        private final String name;
        private final int phase;
        private final long cleanupMillis;
        private volatile boolean running;

        DemoLifecycle(String name, int phase, long cleanupMillis) {
            this.name = name;
            this.phase = phase;
            this.cleanupMillis = cleanupMillis;
        }

        @Override
        public void start() {
            running = true;
            System.out.println("START " + name
                    + " phase=" + phase);
        }

        @Override
        public void stop() {
            // Synchronous stop path if someone calls Lifecycle.stop() directly.
            running = false;
        }

        @Override
        public void stop(Runnable callback) {
            System.out.println("STOP_REQUEST " + name
                    + " phase=" + phase);

            // Do not block the stop-calling thread: simulate asynchronous stop.
            Thread worker = new Thread(() -> {
                try {
                    Thread.sleep(cleanupMillis);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    // Demo manages no real resources:
                    // set stopped state then report completion.
                    running = false;

                    System.out.println("STOP_DONE " + name
                            + " phase=" + phase);
                    callback.run();
                }
            }, "shutdown-" + name);

            worker.start();
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return phase;
        }
    }
}
~~~

**This is a complete Java program when placed in a Spring Boot Maven project with the right dependencies.** The filename matches the public class, the package structure is valid, and all abstract methods of `SmartLifecycle`/`Lifecycle` are implemented. **`isAutoStartup()`** uses `SmartLifecycle`'s default `true`.

Using **`Thread.sleep`** only simulates bounded cleanup; it is not a guide for implementing a production message consumer by sleeping on shutdown. In a real system, the worker must stop accepting new work, manage in-flight tasks, and release real resources **before invoking the callback**.

### 7.3. Running the program

In the project directory with Maven Wrapper:

~~~bash
# Linux/macOS:
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

With normal configuration, the lines **printed by the example code itself**, in order:

~~~text
START storage phase=100
START consumer phase=200
RUN_RETURNED active=true
STOP_REQUEST consumer phase=200
STOP_DONE consumer phase=200
STOP_REQUEST storage phase=100
STOP_DONE storage phase=100
CONTEXT_CLOSED
~~~

Spring Boot/Maven may also print other interleaved logs. The output above lists only the demo's lines. The 250/350 millisecond values are expected sleep times, not a precise clock promise across all operating systems.

**Why is the order like this?**

- On refresh, `DefaultLifecycleProcessor` sees two auto-starting `SmartLifecycle` beans. **`storage` phase=100** starts before **`consumer` phase=200**.
- After startup hooks finish, `SpringApplication.run` returns and `main` prints **`RUN_RETURNED`**.
- Leaving the **`try-with-resources`** block invokes **`ConfigurableApplicationContext.close()`**.
- Shutdown proceeds from phase 200 down to phase 100. Consumer stops first; only after consumer's callback reports done does shutdown move to storage.
- The 2-second timeout easily covers 350ms and 250ms cleanup, so there is no need to wait out the timeout.
- After context close finishes, the program prints **`CONTEXT_CLOSED`**.

### 7.4. Testing timeout misconceptions

Run the demo again with a timeout lower than the cleanup duration:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--spring.lifecycle.timeout-per-shutdown-phase=100ms
~~~

If using Windows/PowerShell, adapt the Maven arguments syntax to your shell; you can also edit `application.properties` directly while learning.

This scenario **intentionally triggers a phase timeout that is too short**:

- Consumer needs a simulated 350ms, yet the phase waits at most 100ms.
- The processor can time out before consumer invokes its callback.
- It can proceed to request stopping storage even while consumer is still cleaning up.
- Worker threads can continue running after the processor stops waiting for them.
- The order of **`STOP_DONE`** may shift or interleave; do not expect one fixed stdout block for this case.
- A warning log may appear stating beans did not finish stopping within the phase timeout.

**This is a timeout-behavior experiment**, not a recommended production configuration. A 100ms timeout is too short for real consumer/connection drains.

If in the low-timeout experiment the process stays alive briefly longer, that is normal: the spawned cleanup threads still exist. **Timeout expiration in `DefaultLifecycleProcessor` is not equivalent to Java `Thread.interrupt` or forceful resource closing.**

## 8. Multiple beans in the same phase

Suppose three components:

~~~text
phase=200:
  consumer-A -> callback after 700ms
  consumer-B -> callback after 1500ms

phase=100:
  storage    -> callback after 300ms
~~~

If the default timeout per phase = 2 seconds:

- For phase 200, the processor must wait for **the group's callbacks**. If they truly stop asynchronously in parallel, this group finishes in ~1500ms, not 700 + 1500ms.
- Only then does it request stopping phase 100 and wait ~300ms.
- Total wait time across both groups is roughly 1800ms, excluding other steps.

If `consumer-B` fails to invoke the callback:

- For phase 200, the processor knows only that the group is incomplete, even though `consumer-A` finished.
- After at most 2 seconds, it can warn and advance to phase 100.
- Whether B actually stops processing messages depends on B's implementation; the timeout does not solve that automatically.

### Why not give each bean its own timeout?

The wait duration belongs to the **same-phase group** because `DefaultLifecycleProcessor` must ensure a group of dependents stops before moving to the next phase. If each bean had a separate sequential budget, ordering and delays would differ and shutdown time could grow excessively.

If one bean is very slow while remaining beans need to stop promptly, consider:

- Moving the slow bean to a phase with a **dedicated budget**.
- Optimizing cleanup, batching, cancellation, and bounding in-flight tasks.
- Using **`setTimeoutForShutdownPhase(...)`** when genuinely needed.
- Redesigning dependencies: stop intake first, drain briefly, then close storage.
- Avoiding raising the application-wide timeout just because one component stops uncontrollably.

## 9. setTimeoutForShutdownPhase and fine-grained group configuration

Spring Framework 6.2 supports:

~~~java
processor.setTimeoutForShutdownPhase(200, 15_000L);
processor.setTimeoutForShutdownPhase(100, 5_000L);
~~~

Two phases have distinct budgets:

| Phase | Example component | Timeout |
| ---: | --- | ---: |
| 200 | Message consumers | 15 seconds |
| 100 | Stateful storage clients | 5 seconds |
| Other phases | Default policy | e.g., 3 or 5 seconds as configured |

You can use a map:

~~~java
processor.setTimeoutsForShutdownPhases(
        java.util.Map.of(200, 15_000L, 100, 5_000L));
~~~

This is an **illustrative code fragment** inside a scope that has a `processor` variable of type `DefaultLifecycleProcessor`. Per-phase APIs arrived in Spring Framework 6.2; check compatibility when upgrading/downgrading.

**Do not confuse with `setConcurrentStartupForPhase(...)`** in Spring Framework 6.2.6+: that method relates to optional **concurrent startup** for certain phases, not timeouts for stop callbacks. Both mention phases and settings, yet lifecycle direction and semantics differ.

One point to watch: the **Spring Boot property** applies one default `Duration` across all phases. When you need to override only specific phases while keeping Boot policy, consider a custom `lifecycleProcessor` or controlled processor configuration; never invent a property like **`spring.lifecycle.timeout-phase-200`** because Spring Boot 3.5 has no such standard property.

## 10. How does graceful HTTP shutdown relate?

Spring Boot 3.5 supports graceful shutdown for embedded web servers and **enables graceful shutdown by default** on supported servers. During `ApplicationContext` closing, web server graceful shutdown participates in `SmartLifecycle` stop phases.

Spring Boot 3.5 documentation describes graceful web shutdown as occurring in the **earliest stopping phase** of `SmartLifecycle` components. At this stage the server tries to stop accepting new requests and lets already-accepted requests finish within configured bounds.

Example:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

This property can also serve as the wait budget for the phase in which graceful web shutdown executes, so it **does not apply solely to application-authored beans**.

Distinguish:

- **Rejecting new requests:** may occur at the network layer or via differing HTTP responses depending on web server type.
- **In-flight requests:** allowed to finish within the graceful shutdown window.
- **`ApplicationContext` lifecycle:** `SmartLifecycle` beans are stopped by phase.
- **Deeper resources:** thread pools, messaging clients, caches, and database pools still have their own lifecycles.

**Do not assign arbitrary phases** to components that must keep serving web requests while the server drains, if doing so could close a dependency before requests finish. Always check the phases of key infrastructure components, understand `depends-on`, and test the entire shutdown path on your actual web server.

### Stopping new requests can differ across servers

The Spring Boot 3.5 Reference notes that graceful shutdown behavior depends on the embedded web server. Some servers stop accepting new connections at the network layer, while others may return specific HTTP responses. Do not write rigid tests expecting every new request after `SIGTERM` to return HTTP 503; sometimes connections are refused instead of receiving a response.

Graceful shutdown does not by itself guarantee **zero downtime**. Coordinate readiness, load balancer draining, connection reuse, Kubernetes termination budgets, proper retries, and healthy replica counts.

## 11. Relationship with Kubernetes terminationGracePeriodSeconds

A Deployment can declare:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 75
      containers:
        - name: app
          image: example/lifecycle-demo:1.0.0
~~~

This is a **fragment** of a Pod template, not a complete Deployment manifest; the image is an illustrative value that must be replaced with a real image.

When a Pod is terminated:

1. Kubernetes starts the termination grace budget.
2. Any `preStop` hook runs and **consumes part of this same budget**.
3. Kubernetes sends a stop signal to the process per the runtime mechanism.
4. The JVM/Spring Boot runs shutdown hooks and closes `ApplicationContext`.
5. `DefaultLifecycleProcessor` requests stopping `SmartLifecycle` phases.
6. Bean destroy callbacks, executor cleanup, web server close, and other resources take time.
7. When termination grace expires, kubelet/runtime may force-kill the container if it has not exited yet.

### Estimating the total budget

If a project has:

~~~text
phase 300: max 20s
phase 200: max 15s
phase 100: max 10s
phase   0: max 5s
--------------------------------
Total phase wait budget ~50s
PreStop hook: 5s
Bean destruction/overhead: extra time
~~~

then **`terminationGracePeriodSeconds=30`** is a risky choice because kubelet may force-kill the container before Spring finishes properly designed stop phases.

Do not treat this sum as a rigid addition for every app: many callbacks finish before timeout, some phases have no beans, and some work runs concurrently. Still, a grounded **upper-bound planning estimate** is better than picking a random number.

For the demo in section 7, because the app is **short-lived non-web** and `main` closes the context after `run`, neither Kubernetes nor a grace period is needed to observe phase timeouts.

### Readiness and shutdown

In deployments behind a load balancer, switch readiness to **`REFUSING_TRAFFIC`** when preparing to shut down so routing cuts back new requests. However, readiness probes have polling intervals and endpoint propagation lag; they do not guarantee new requests stop **instantly**. Combine readiness with graceful web shutdown instead of merely raising lifecycle timeouts.

## 12. Relationship with @PreDestroy and cleanup callbacks

A bean can have multiple cleanup hooks:

- **`SmartLifecycle.stop(Runnable)`**: handles **ordered lifecycle stop** with callbacks and phase timeouts.
- **`DisposableBean.destroy()`**: destroy callback after normal lifecycle stop steps.
- **`@PreDestroy`**: bean destruction callback.
- **Custom `destroy-method`**: cleanup method declared on the bean definition.
- **Executor/ConnectionPool shutdown hooks**: each library's own mechanism.

During normal shutdown, Spring usually handles **lifecycle stop before general bean destruction**. Therefore, if a `SmartLifecycle` stops too early or invokes its callback before truly finishing, a dependency may be destroyed while another thread is still using it.

**Per-phase timeout does not replace `@PreDestroy` timeouts or unbounded network closes.** If `@PreDestroy` executes a 60-second blocking call, a 5-second lifecycle timeout does not mean Spring will interrupt `@PreDestroy` after 5 seconds.

Nor is it guaranteed that every startup error runs all lifecycle stop hooks: when refresh fails, some beans may be destroyed on the error path before ever starting. Cleanup implementations must be idempotent, tolerate partially initialized resources, and not throw when already stopped.

### Two-step business stopping

Some services need clear stages:

~~~text
1. Quiesce: stop accepting new messages/requests.
2. Drain: wait for in-flight tasks to finish, with deadline.
3. Close: release connections, threads, consumers.
4. Signal: callback.run() reports stopped.
~~~

If draining exceeds the deadline, the system needs a clear policy: controlled task cancellation, checkpointing/requeuing unprocessed messages, recording recovery state, or accepting redelivery via idempotency. **Never invoke the callback and silently leave the worker processing as before**.

## 13. Anti-patterns: forgotten callback, early callback, and blocking stop

### 13.1. Forgotten callback

~~~java
@Override
public void stop(Runnable callback) {
    stopConsumerAsync();
    // Missing callback.run(): violates contract.
}
~~~

This is an **anti-pattern fragment**, assuming `stopConsumerAsync()` is defined. `DefaultLifecycleProcessor` cannot know stopping finished and may wait out the phase timeout.

### 13.2. Calling the callback too early

~~~java
@Override
public void stop(Runnable callback) {
    stopConsumerAsync();
    callback.run(); // Wrong if cleanup is still ongoing.
}
~~~

This anti-pattern emits a **stopped** signal while the resource is still active. Spring can advance to a later phase and close a dependency the consumer is still using.

### 13.3. Blocking directly inside stop(Runnable)

~~~java
@Override
public void stop(Runnable callback) {
    waitForNetworkForever(); // Can block the shutdown thread.
    callback.run();
}
~~~

If the method gets stuck in **`waitForNetworkForever`**, the callback-wait latch timeout in `DefaultLifecycleProcessor` cannot reliably rescue the blocked thread. Design I/O timeouts, bounded waits, and cancellation explicitly.

### 13.4. Stopping in the wrong order

~~~text
Storage phase=200
Consumer phase=100

STOP: Storage before Consumer -> consumer loses dependency.
~~~

If the consumer needs storage while flushing, this phase assignment can cause lost messages or cleanup errors. Redesign so **Consumer has a higher phase than Storage** or declare an explicit dependency.

### 13.5. Changing timeouts to mask design bugs

Raising timeout from 30 seconds to 10 minutes may reduce warnings yet slows deploys/rolling updates and risks exceeding termination budgets. Investigate root causes: non-exiting threads, infinite network retries, forgotten callbacks, uncheckpointed jobs, or deadlocks.

## 14. Measuring shutdown duration properly

When testing shutdown, record milestones:

~~~text
T0  : Context starts closing / SIGTERM
T1  : Highest phase STOP_REQUEST
T2  : Last STOP_DONE of that phase
T3  : Next phase STOP_REQUEST
T4  : Next phase STOP_DONE
T5  : Destroy callbacks finish
T6  : Process actually exits
~~~

Metrics and logs should include **bean name**, **phase**, **`elapsedMillis`**, **timeout budget**, **remaining work count**, and **cleanup outcome**. Do not log sensitive data or full message payloads.

### Intentional testing matrix

| Scenario | What to observe |
| --- | --- |
| Callbacks complete before deadline | Next phase starts right after previous group finishes |
| Two beans in same phase, one slow | Phase budget belongs to the group, not summed per bean |
| One bean omits callback | Warning/timeout then advances phase; do not treat as success |
| One bean blocks indefinitely in stop | Phase timeout does not automatically free the blocked thread |
| Timeout too short | Previous phase's cleanup may overlap next phase |
| Slow `@PreDestroy` | Total shutdown can exceed total phase wait time |
| Multiple replicas terminate concurrently | Grace budget/traffic drain and dependency shutdown still hold |
| JVM receives `SIGKILL` | Cannot expect all callbacks to run |
| Bean never started | `stop()` must be safe if not running |
| Context refresh fails | Partial resource teardown must not rely on the happy path |

### How should a timeout warning log be interpreted?

A timeout warning means **the processor did not receive all completion signals** within the time allotted for the phase. It does not definitively prove whether the resource has stopped. Check callbacks, thread dumps, active tasks, queue lag, pool statistics, and relevant system metrics.

## 15. Distinguishing SmartLifecycle from executor shutdown

An executor such as **`ThreadPoolTaskExecutor`** has its own settings for whether to accept new tasks during context close, whether to wait for active tasks to finish, and how long to wait. Depending on Spring Boot/Spring Framework version, task execution shutdown properties may exist **alongside** lifecycle timeouts.

Therefore:

- **`DefaultLifecycleProcessor`** manages stop ordering of `Lifecycle`/`SmartLifecycle` beans.
- **Executors** can manage worker thread counts, queues, and their own shutdown policies.
- **Database clients / messaging libraries** can have their own network, flush, or close timeouts.
- **Kubernetes** enforces container termination deadlines.

A setting like **`spring.lifecycle.timeout-per-shutdown-phase=30s`** is not enough to prove every executor task stops in exactly 30 seconds. Identify exactly which lifecycle phase or destroy path each bean participates in and configure compatible deadlines across them.

If a consumer uses an executor, ensure the order: stop new intake → wait for in-flight work within deadline → close executor/storage per dependencies. Do not shut down the executor before the consumer finishes what it needs.

## 16. Reinforcement questions and exercises

**Question 1.** There are 5 `SmartLifecycle` beans sharing `phase=200`. Timeout per phase=10s. Does Spring spend up to 50s waiting for the whole group?

**Question 2.** Two beans A (`phase=300`) and B (`phase=100`). A needs B during shutdown. Which bean will Spring ask to stop first? On startup, which bean starts first?

**Question 3.** Why is an implementation that calls `callback.run()` immediately after starting an asynchronous stop incorrect?

**Question 4.** A bean actually stopped yet forgot to invoke the callback. How may the processor react?

**Question 5.** If a Spring Boot 3.5 configuration does not set the timeout property, what is the default in Boot Common Application Properties? Why should you not confuse it with Framework 6.2's raw JavaDoc default?

**Question 6.** When phase 200 needs 15s while remaining phases need only 5s, which API do you use?

**Question 7.** If `stop(Runnable)` calls a network API without a timeout and blocks forever, can merely reducing timeout per phase solve it?

**Question 8.** A Kubernetes Pod has `terminationGracePeriodSeconds=25` while phase budgets sum to nearly 50s. What risk arises?

**Question 9.** During graceful HTTP shutdown, why must the connection pool not be stopped before in-flight requests using it have completed?

**Question 10.** Why is `@Order` not the right way to adjust `SmartLifecycle` stop order?

### Suggested answers

1. No; the timeout applies to **the entire phase**, and callbacks can run asynchronously sharing that budget.
2. Start B before A, stop A before B by phase.
3. Spring assumes cleanup finished and may stop dependencies too early.
4. Waits until the phase timeout expires, logs a warning, and proceeds to stop other groups.
5. Boot 3.5 uses **30 seconds/phase** per its default property; raw Framework 6.2 `DefaultLifecycleProcessor` JavaDoc notes 10 seconds.
6. **`setTimeoutPerShutdownPhase(5_000L)`** and **`setTimeoutForShutdownPhase(200, 15_000L)`** on a customized processor.
7. No; you must design bounded I/O and contract-compliant callbacks.
8. The Pod can be force-killed before cleanup completes; timeouts and grace budgets must be aligned.
9. Closing a dependency pool while requests are unfinished can cause errors or lost work.
10. Only **`getPhase()`** and `depends-on` govern lifecycle ordering.

## 17. Implementation checklist and summary

- [ ] Identify which beans actually implement `SmartLifecycle`.
- [ ] Understand **ascending start phase, descending stop phase**.
- [ ] Assign phases based on **live/stop dependencies**, not aesthetics.
- [ ] For async stop, call `callback.run()` **only after cleanup**.
- [ ] Never let `stop(Runnable)` block forever or make un-timed network calls.
- [ ] Understand the timeout applies to **a phase group**, not per bean.
- [ ] Do not confuse Spring Boot 3.5's 30s default with raw Framework 6.2's 10s default.
- [ ] Use **`spring.lifecycle.timeout-per-shutdown-phase`** when a single shared budget suffices.
- [ ] Override **`setTimeoutForShutdownPhase`** only when one phase truly needs a separate budget.
- [ ] Be careful when supplying a custom **`lifecycleProcessor`** bean so you do not silently bypass auto-configuration.
- [ ] Remember connections with graceful HTTP shutdown, executors, `@PreDestroy`, and connection pools.
- [ ] Evaluate total shutdown time alongside **`terminationGracePeriodSeconds`** and `preStop`.
- [ ] Test timeout paths, forgotten callbacks, I/O errors, and restarts in staging.
- [ ] Add logs/metrics measuring duration from stop request to callback completion.

**Summary:** `DefaultLifecycleProcessor` lets Spring stop `SmartLifecycle` components in phase order. Each same-phase group is given a **shared wait budget** for stop callbacks. If callbacks finish early, Spring advances immediately; if the timeout expires, Spring does not forcibly terminate all threads and resources, so the application must uphold its stop contract and cleanup deadlines itself. Sound design coordinates **phases, callbacks, timeouts**, related dependencies, and platform termination budgets.

### Official documentation

1. Spring Framework 6.2 JavaDoc — `DefaultLifecycleProcessor`, timeout per phase and per-phase overrides: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
2. Spring Framework 6.2 JavaDoc — `SmartLifecycle`, `stop(Runnable)`, default phase, and automatic startup: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/SmartLifecycle.html
3. Spring Framework 6.2 — Customizing the Nature of a Bean, lifecycle startup/shutdown phases: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
4. Spring Boot 3.5 — Common Application Properties, `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
5. Spring Boot 3.5 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
6. Kubernetes — Pod termination behavior: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination

The runnable example is designed for **Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2.x**. Other versions may alter default values, per-phase override APIs, and graceful shutdown behavior; check the exact version's JavaDoc before applying to production systems.