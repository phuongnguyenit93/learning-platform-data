# Closing ApplicationContext and Server SmartLifecycle Lifecycle

**Module:** Spring Boot → web-runtime → **Graceful Shutdown**.

When an application receives a shutdown signal, what matters is not just “turning off Tomcat” or “calling `System.exit`”, but orchestrating the **ApplicationContext**, the **web server's SmartLifecycle**, in-flight HTTP requests, jobs/background consumers, and the destruction of singleton resources. This article presents the sequence **context close → ContextClosedEvent → LifecycleProcessor.onClose() → stopping SmartLifecycle by phase → @PreDestroy/DisposableBean → releasing BeanFactory**, how to use `server.shutdown`/`spring.lifecycle.timeout-per-shutdown-phase`, designing `stop(Runnable)` properly, pitfalls when running on Docker/Kubernetes, and a **Java 17 + Maven + Spring Boot 3.5.16** project with real verification using `SIGTERM`.

**Specific scope:** Spring Boot 3.5.x / Spring Framework 6.2.x, embedded Servlet container (the demo uses Tomcat via `spring-boot-starter-web`). The context and `SmartLifecycle` principles apply to many Spring applications, while web server behavior may differ for WebFlux/Jetty/Undertow/Netty, external servlet containers, and other Boot major versions. Version 3.5.16 belongs to a line whose OSS support ended in mid-2026; production should use a supported maintenance branch/version and verify against the actual version.

## 1. How does “graceful shutdown” differ from “process dies immediately”?

Suppose a request is processing a 7-second bank transfer. The process receives a shutdown request at second 3.

**Abrupt shutdown:** the container/process is terminated immediately, sockets close, and the request may lose its response; an in-progress transaction may roll back or may have committed without the caller receiving the result. There is no guarantee that the business operation is executed exactly once.

**Graceful shutdown:** the system **stops accepting new traffic** while giving in-flight requests a chance to complete within the **grace period**. Afterwards, it stops background components in order, releases connections/database pools, and closes the context. The grace period is **finite** and does not guarantee that every long-running job will finish if it exceeds the limit.

~~~text
T+0s   JVM receives SIGTERM / ctx.close() is called
  │
  ├── ContextClosedEvent
  │
  ├── stop higher-phase SmartLifecycle beans first (can block accepting new jobs)
  │
  ├── WebServer graceful shutdown in the first phase of the stop process
  │     ├── stop allowing new HTTP requests
  │     └── wait for running requests to finish, up to the phase deadline
  │
  ├── stop lower-phase SmartLifecycle beans (application consumers, schedulers)
  │
  ├── destroy singleton beans (@PreDestroy, DisposableBean, destroyMethod)
  │
  └── close BeanFactory / context and process exits
~~~

**This is a conceptual sequence of a normal Spring Boot context close**, not an exact log/timestamp imposed on every version. Beans in the same phase may stop concurrently via callbacks; dependency declarations can affect the order; nested contexts and framework integrations may add their own steps.

**Key takeaway:** if the JVM receives `SIGKILL`/`kill -9`, is OOM-killed, suffers a native crash, or executes `Runtime.halt(...)`, there is no guarantee that shutdown hooks, `ContextClosedEvent`, `stop`, or `@PreDestroy` will run. Graceful shutdown is **best effort within an allowed deadline**, and does not replace transactionality, retries, idempotency, and durability.

## 2. How does ApplicationContext close?

In Spring Boot, `SpringApplication.run(...)` returns a `ConfigurableApplicationContext`. By default, Spring Boot **registers a JVM shutdown hook** to call close when the JVM has a chance to shut down normally. Valid pathways include:

| Trigger | Mechanism | Is there a chance for graceful shutdown? |
| --- | --- | --- |
| `kill -TERM <pid>` command sent to the **JVM process** | JVM executes shutdown hooks, closing the context | **Yes**, if the process/OS allows enough time |
| Container orchestrator sends SIGTERM to PID 1 | Shutdown hook runs if the signal reaches the JVM properly | **Yes**, within the termination grace period |
| `context.close()` on `ConfigurableApplicationContext` | Invokes Spring context close directly | **Yes**; the caller thread performs the close cycle |
| `SpringApplication.exit(context)` | Closes context and computes exit code from ExitCodeGenerators | **Yes**; **does not automatically ensure the JVM has called System.exit** |
| JVM crash / `kill -9` / force-stop | Bypasses shutdown hooks or terminates immediately | **No** |
| IDE Stop button | Depends on what signal the IDE sends to the JVM | **Should not assume** it is always graceful |

A context can be closed when the code holds management control over it:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

// Lifecycle example for a CLI/test application only;
// do not call close right after run in a production web server.
context.close();
~~~

Corresponding imports for `SpringApplication` and `ConfigurableApplicationContext` are needed here. If `close()` is called immediately after starting a web app, the server will shut down at once — **this is an illustrative snippet** and does not belong in the demo project's main method.

**Do not create an unauthenticated `GET /shutdown` endpoint that calls `System.exit(0)`.** Spring Boot Actuator has a shutdown endpoint that supports context close, but it is **disabled by default**, requiring explicit enabling/exposing and very strict authentication/network controls. In most applications, let the process manager/orchestrator manage the lifetime rather than a public web API.

### 2.1. How does closing a context differ from refresh/restart?

`ContextRefreshedEvent` belongs to the context refresh/start process. `ContextClosedEvent` belongs to the close process. Do not call `context.refresh()` to “stop and self-restart” a web server: it is not a rolling restart/zero-downtime API. To roll out a new version, use multiple replicas behind a load balancer and orchestration, or perform a proper full process restart.

`@PreDestroy` is invoked when a singleton is destroyed according to the context lifecycle, not automatically “once per request”. For prototype scope, Spring does not manage destruction like a normal singleton; the caller using that scope must release it properly. `SmartLifecycle` manages **starting/stopping active components**, not as a replacement for all resource cleanup.

## 3. The actual close order inside Spring

In Spring Framework's `AbstractApplicationContext#doClose()`, when the context is active and the close process proceeds normally:

1. Publishes **`ContextClosedEvent`**.
2. Calls **`LifecycleProcessor.onClose()`**, typically `DefaultLifecycleProcessor`, to stop beans implementing `Lifecycle`/`SmartLifecycle`.
3. Calls **`destroyBeans()`**, destroying singleton beans and invoking destruction callbacks (for example `@PreDestroy`, `DisposableBean.destroy()`, inferred/custom destroy methods).
4. Closes the bean factory/marks context state and executes context cleanup hooks.

At startup, `ContextRefreshedEvent` and lifecycle startup also interact; learners should focus on the distinction: `ContextClosedEvent` is **not** a signal that “all servlets have finished stopping”. When a listener receives this event, the web server may **still be waiting for requests to complete**. Therefore:

- A `ContextClosedEvent` listener should be **fast**, marking state, recording logs/metrics, or sending a lightweight drain signal.
- **Do not close the database pool immediately in the listener** if HTTP requests still need the DB.
- **Do not sleep 30 seconds in the listener** to “wait for requests”: that can delay the lifecycle processor from even starting graceful shutdown.
- If you need ordered draining of background jobs and control over stop completion, implement `SmartLifecycle` with phases, callbacks, and deadlines.
- If you only need to close a resource after components have stopped, use `@PreDestroy` or `DisposableBean`.
- Pay attention to exceptions/timeouts: logging and cleanup must be fault-tolerant; stopping a process does not guarantee every step finishes.

### 3.1. Event vs lifecycle vs destruction

| Hook | Used for | Typical timing | Waits for async callback? |
| --- | --- | --- | --- |
| `ApplicationListener<ContextClosedEvent>` / `@EventListener` | Observing context close start, marking quiescing | Before stopping lifecycle beans | No; synchronous listeners should not block long by default |
| `SmartLifecycle.stop(Runnable)` | Stopping an active component with ordering and a completion signal | During `LifecycleProcessor.onClose` | **Yes**, processor waits for callback within phase timeout |
| `Lifecycle.stop()` | Stopping a simple active component | During lifecycle processor | No async completion callback in standard API |
| `@PreDestroy` | Cleanup when bean is destroyed | After lifecycle stop processing | No SmartLifecycle phase ordering |
| `DisposableBean.destroy()` | Explicit cleanup contract | Singleton destruction | Not an event equivalent to shutdown start |
| `@Bean(destroyMethod = "...")` | Destroying a third-party bean | Singleton destruction | Not for waiting on in-flight network drain beyond limits |

A bean can implement SmartLifecycle **and** have `@PreDestroy`, but you must ensure operations are idempotent and avoid running dangerous cleanup twice. `stop(Runnable)` should stop activity/stop accepting new work, while `@PreDestroy` releases final resources if needed.

## 4. Lifecycle, SmartLifecycle, DefaultLifecycleProcessor

### 4.1. `Lifecycle`: standard start/stop

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

When the context has a `LifecycleProcessor`, it can start/stop beans. Basic `Lifecycle` is **not** automatically started every time like `SmartLifecycle`; per Spring docs, regular Lifecycle beans belong to phase 0 and have different auto-start semantics (often requiring an explicit start). Avoid writing `Lifecycle` and assuming it will definitely auto-start on context refresh.

### 4.2. `SmartLifecycle` adds auto-start, phase, and async stop callback

Key methods:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();    // default true
    int getPhase();             // default Integer.MAX_VALUE
    void stop(Runnable callback);
}
~~~

This is an **abbreviated API description** for learning (not a copy of the full interface from Spring). When implementing SmartLifecycle:
- `isAutoStartup()` defaults to **true**, allowing the processor to start it automatically when the context refreshes.
- `getPhase()` defaults to `SmartLifecycle.DEFAULT_PHASE` = `Integer.MAX_VALUE`.
- `start()` must set `isRunning()` state to true when starting succeeds.
- `stop(Runnable callback)` must call **`callback.run()` after the component has actually stopped**; do not forget the callback, otherwise the processor may wait until timeout.
- `stop()` remains a method from `Lifecycle`; the callback variant is the method the lifecycle processor uses for SmartLifecycle during normal shutdown. If overriding both, ensure consistent semantics.
- `stop` can be async; the callback is a completion contract, **not** an HTTP callback or event listener.

### 4.3. Phase ordering: ascending start, descending stop

**Rule:**

~~~text
Component                   phase     Startup          Shutdown
Consumer                    -100      1                3
Worker                        0      2                2
Publisher                   +100      3                1

START:  -100 → 0 → +100
STOP:   +100 → 0 → -100
~~~

Within the **same phase**, components are not guaranteed a linear order and may depend on implementation/parallel callbacks. **Bean dependencies** can override phase order: if bean A depends on B, B starts before A, and A stops before B, regardless of declared phases. In Spring Framework, a bean implementing only `Lifecycle` is treated as phase 0 for processor start/stop commands.

**Do not confuse `@Order` on a bean with `SmartLifecycle.getPhase`.** To control lifecycle bean order, use phases and dependency relationships; `@Order` on a bean method is not a promise to stop before/after the server. Do not pick `Integer.MAX_VALUE` or `Integer.MIN_VALUE` arbitrarily without checking framework lifecycle phase constants.

### 4.4. Which phase does embedded server graceful shutdown belong to?

Spring Boot 3.5 has `WebServerGracefulShutdownLifecycle` to trigger `WebServer.shutDownGracefully(...)` in one of the high phases, because the lifecycle processor **stops from highest phase to lowest**. Boot documentation describes graceful shutdown as running in the **earliest phase of stopping SmartLifecycle beans**.

To keep code order clear:
- A `SmartLifecycle` that wants to **block accepting new work before** the server drains can use a phase **higher** than the web server's graceful phase (and test on the current version).
- A component that needs to **keep a resource alive until HTTP drain completes** should have a stop phase **lower** than web server graceful stop, or an appropriate dependency relationship.
- A bean using the default `SmartLifecycle.DEFAULT_PHASE` has a very high phase; it may stop **before web server graceful stop**. Do not assume every custom SmartLifecycle stops after the server finishes.

In Boot 3.5, the Java class `org.springframework.boot.web.context.WebServerGracefulShutdownLifecycle` exposes the phase constant `SMART_LIFECYCLE_PHASE`. To avoid locking the application to magic numbers or guessing integers, check the Javadoc/version or use this constant when designing strictly. **Do not alter a framework bean's phase via patching/reflection** just to get logs “in the right order”.

### 4.5. Timeout is per phase, not a single global clock

`DefaultLifecycleProcessor` uses a **timeout per shutdown phase**, defaulting in Spring Framework 6.2 to roughly **30 seconds per phase** (configurable by Boot). With the configuration:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

the processor waits up to 20 seconds for completion callbacks in **each phase**. This does **not** mean “the application always stops within 20 seconds”: there may be multiple distinct phases, plus `ContextClosedEvent`, `@PreDestroy`, library cleanup, and process exit overhead. If a component fails to invoke its callback, the phase may wait until timeout and then proceed to subsequent phases; that component's resources might not have stopped completely.

### 4.6. The callback must report completion, even on error

Synchronous stop pattern:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stopAcceptingNewWork();
        waitForCurrentWorkWithinDeadline();
        closeInternalListener();
    } finally {
        callback.run();
    }
}
~~~

This is an **illustrative snippet** and does not run standalone because the methods must be implemented. Exceptions must be accounted for, and the startup/shutdown thread should not be blocked for too long. For async stop:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            drainAndStop();
        } finally {
            callback.run();
        }
    });
}
~~~

This is an **illustrative snippet**, requiring a still-active executor and a drain implementation. In practice, you must also handle the case where `executor.execute` is rejected during shutdown so the callback is still invoked, and ensure the callback runs **exactly once**. Do not use an executor that itself was shut down in an earlier phase. In the section 7 demo, a dedicated thread is created for the bounded wait to make it easy to observe.

## 5. Spring Boot 3.5: graceful shutdown of embedded web servers

Spring Boot 3.5 **enables graceful shutdown by default** for four embedded servers: **Tomcat, Jetty, Reactor Netty, and Undertow**, across both Servlet and reactive stacks. Explicit configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

To actively disable this mechanism (usually only in a lab/debug session or special requirement):

~~~properties
server.shutdown=immediate
~~~

**`immediate` is not recommended** just to make the process exit faster if the application still processes requests with side effects. Graceful shutdown waits for **in-flight HTTP requests within the grace period** and **stops accepting new requests**. However, the strategy for rejecting new requests varies by server:
- **Tomcat, Jetty, Reactor Netty:** stop accepting new requests at the network layer during graceful drain.
- **Undertow:** may still accept connections but returns **503 Service Unavailable** during the grace window.
- HTTP persistent connections/HTTP2 streaming may have different detailed behavior; check the specific server.
- An overly long request, SSE/WebSocket stream, or slow-sending client can consume the phase timeout; you must decide how to close/notify the client according to the protocol.
- Expiring the timeout does not guarantee the business task rolls back cleanly; callers must know the retry/idempotency semantics.

### 5.1. Graceful shutdown does not mean waiting for all background jobs

Spring Boot manages the web server, but a custom `Thread`, scheduler, message consumer, file poller, or SDK client created by the application will not necessarily stop properly on its own. The team's responsibilities:
1. Stop accepting new jobs when termination begins.
2. Wait for/finish/cancel running jobs within an appropriate deadline.
3. Call `callback.run()` of SmartLifecycle after actually stopping.
4. Close executors, consumer subscriptions, DB connections, and resources when no longer in use.
5. Persist durable progress/offsets/idempotency to handle crashes or forced termination.

**Do not close the DataSource in `ContextClosedEvent`** while web requests are still running. Container request draining should occur before database connection beans are destroyed.

### 5.2. Web server timeout vs request timeout vs process grace

| Parameter | What does it measure? | What is not guaranteed? |
| --- | --- | --- |
| `spring.lifecycle.timeout-per-shutdown-phase=20s` | Processor waits up to 20s for a phase's stop callbacks | Does not cover all phases/`@PreDestroy`/preStop |
| `server.shutdown=graceful` | How the embedded HTTP server stops | Does not guarantee infinite requests always finish |
| `server.tomcat.connection-timeout` | Certain timeout aspects of Tomcat HTTP connections | Does not replace lifecycle phase timeout |
| Client `curl --max-time` | Deadline of the client command itself | Does not accurately reflect server shutdown |
| Kubernetes `terminationGracePeriodSeconds` | Total time a Pod is allowed to terminate after Pod termination begins | Does not automatically add preStop or Spring phases on top |
| Docker stop timeout | Wait time after SIGTERM before SIGKILL | Not an HTTP per-request timeout |
| `@PreDestroy` | Bean cleanup on destruction | Has no automatic per-phase timeout from the phase property |

When budgeting, use a safe upper bound covering **preStop time + web drain phase + required phases + destruction + margin**. Do not confuse orchestrator defaults with Spring's defaults.

## 6. Which hook to choose for which task?

| Task to perform | Recommended hook/mechanism | Reason |
| --- | --- | --- |
| Log that context started closing | `@EventListener(ContextClosedEvent.class)` | Fast, does not wait for drain |
| Block new batch jobs | High-phase `SmartLifecycle`, close admission gate | Ordered before downstream drain |
| Let in-flight HTTP requests finish | Spring Boot web server graceful lifecycle | Framework knows in-flight HTTP requests |
| Stop queue consumers after web traffic stops | Low-phase `SmartLifecycle`, stop(Runnable) and deadline | Keeps downstream dependencies alive long enough |
| Shut down scheduler/executor | `SmartLifecycle` or library/framework lifecycle integration | Explicit stop/awaitTermination semantics |
| Close ConnectionPool/HTTP client after jobs finish | Bean destruction hook, `@PreDestroy`, or destroy method | End-of-life resource destruction |
| Process shutdown by Kubernetes | SIGTERM to JVM PID 1 + probes + grace | Cooperates with load balancer/draining |
| Stopping a job after SIGKILL/crash | Persistent lease/checkpoint, idempotency | In-process callbacks cannot run |

**Choose one primary responsible mechanism per resource.** Do not simultaneously call `executor.shutdownNow()` in `ContextClosedEvent`, let web requests keep using the executor, and also try to block Spring destroy cleanup: this easily causes races/`RejectedExecutionException`.

## 7. Runnable Java 17 project: observing close order and keeping in-flight requests

Demo objectives:
- `GET /work?ms=7000` simulates an HTTP request working for 7 seconds.
- `AdmissionLifecycle` has a very high phase, **stopping new job intake** during shutdown.
- Spring Boot HTTP graceful lifecycle waits for requests already started to complete within 20s.
- `DrainLifecycle` at phase 0 runs async stop, waits for in-flight work count to reach 0 or a local deadline to expire, then calls `callback.run()`.
- `ShutdownSignals` logs `ContextClosedEvent` and `@PreDestroy` to verify the exact order.
- `@SpringBootTest(RANDOM_PORT)` tests the route, and an isolated test verifies ascending start phase / descending stop phase.

**Warning:** the lab has no authentication and uses `Thread.sleep` for simulation. Only bind on `127.0.0.1`. This is not a production solution for job queues, payments, exactly-once, or load balancing.

### 7.1. Directory tree

~~~text
lifecycle-shutdown-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/shutdown/
    │   │   ├── ShutdownDemoApplication.java
    │   │   ├── InFlightTracker.java
    │   │   ├── AdmissionLifecycle.java
    │   │   ├── DrainLifecycle.java
    │   │   ├── WorkController.java
    │   │   └── ShutdownSignals.java
    │   └── resources/application.properties
    └── test/java/com/example/shutdown/
        ├── LifecyclePhaseTest.java
        └── WorkHttpTest.java
~~~

### 7.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>lifecycle-shutdown-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

### 7.3. `src/main/java/com/example/shutdown/ShutdownDemoApplication.java`

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemoApplication.class, args);
    }
}
~~~

Spring Boot registers a JVM shutdown hook by default. `main` does not call `close()` right after `run()`, because the server needs to stay active until stopped by the process manager.

### 7.4. `src/main/java/com/example/shutdown/InFlightTracker.java`

~~~java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class InFlightTracker {
    private final AtomicInteger active = new AtomicInteger();

    public void begin() {
        active.incrementAndGet();
    }

    public void finish() {
        active.decrementAndGet();
    }

    public int activeCount() {
        return active.get();
    }
}
~~~

`InFlightTracker` stores the count of active HTTP work within **a single JVM**, purely for observation in the lab. It does not count every Tomcat request, does not track workers on other nodes, and does not itself prevent races between the admission check and shutdown. Production can use HTTP server metrics/in-flight accounting, queue-specific counters, and bounded concurrency.

### 7.5. `src/main/java/com/example/shutdown/AdmissionLifecycle.java`

~~~java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class AdmissionLifecycle implements SmartLifecycle {
    private static final Logger log =
            LoggerFactory.getLogger(AdmissionLifecycle.class);

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
        log.info("ADMISSION start: accepting new work");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            log.info("ADMISSION stop: reject new work");
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        // Higher than the web server graceful shutdown phase in Boot 3.5.
        return SmartLifecycle.DEFAULT_PHASE;
    }

    public boolean acceptingNewWork() {
        return running.get();
    }
}
~~~

`getPhase()` uses SmartLifecycle's very high default to close the admission gate in the first stage. `stop(Runnable)` calls the callback immediately because this operation is synchronous; the callback is inside `finally` so it is not missed even if logging fails. `stop()` is still implemented to satisfy the Lifecycle API, though the processor invokes the callback variant during a normal close.

**Do not use this gate for authorization or exactly-once guarantees.** A request that already passed the admission check before SIGTERM will proceed; a request arriving very close to shutdown may hit 503 or network rejection depending on the server and pipeline position. Race behavior is guarded only at the level of **not admitting new work once the gate is closed**, not as a distributed lock.

### 7.6. `src/main/java/com/example/shutdown/DrainLifecycle.java`

~~~java
package com.example.shutdown;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class DrainLifecycle implements SmartLifecycle {
    private static final Logger log =
            LoggerFactory.getLogger(DrainLifecycle.class);

    private final InFlightTracker tracker;
    private final AtomicBoolean running = new AtomicBoolean();

    public DrainLifecycle(InFlightTracker tracker) {
        this.tracker = tracker;
    }

    @Override
    public void start() {
        running.set(true);
        log.info("DRAIN start: tracking HTTP work");
    }

    @Override
    public void stop(Runnable callback) {
        // Do not block the lifecycle stop thread itself with Thread.sleep.
        Thread drainer = new Thread(() -> {
            try {
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(10);
                while (tracker.activeCount() > 0
                        && System.nanoTime() < deadline) {
                    Thread.sleep(100);
                }
                if (tracker.activeCount() > 0) {
                    log.warn("DRAIN timeout, active={}",
                             tracker.activeCount());
                } else {
                    log.info("DRAIN complete, active=0");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                log.warn("DRAIN interrupted");
            } finally {
                running.set(false);
                // Required: signal LifecycleProcessor that stop has finished.
                callback.run();
            }
        }, "demo-drain-lifecycle");

        drainer.setDaemon(true);
        drainer.start();
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        // Lower than web server graceful phase:
        // stop AFTER the server has had a chance to drain.
        return 0;
    }
}
~~~

`DrainLifecycle` clearly illustrates **asynchronous stop with callback**. It keeps `isRunning()==true` until the drain thread finishes, then calls `callback.run()` **exactly once** in `finally`. The while loop has an independent **10s** deadline; Spring's phase timeout config is **20s** to provide margin. If you replace the while loop with network calls/database operations, you must add a timeout/budget per operation.

**Caveat:** If a new thread cannot be created (e.g., `Thread.start()` fails due to exhausted resources), the callback would not be invoked; the processor would still wait until the phase timeout. Production should have fallback `try/catch` around thread creation/rejected executors, measure stop errors, and ensure the completion signal fires exactly once across all branches. The example is kept minimal intentionally to focus on lifecycle semantics.

In a real application, you do not necessarily need another `DrainLifecycle` just to count HTTP work, because the server already knows about in-flight requests. It is useful when representing **jobs/consumers or resource subscriptions** that the web server does not manage and that have their own deadline.

### 7.7. `src/main/java/com/example/shutdown/WorkController.java`

~~~java
package com.example.shutdown;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final AdmissionLifecycle admission;
    private final InFlightTracker tracker;

    public WorkController(AdmissionLifecycle admission,
                          InFlightTracker tracker) {
        this.admission = admission;
        this.tracker = tracker;
    }

    @GetMapping(path = "/work",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> work(
            @RequestParam(name = "ms", defaultValue = "5000")
            long milliseconds) {

        if (milliseconds < 0 || milliseconds > 15000) {
            return ResponseEntity.badRequest()
                    .body("ms must be between 0 and 15000\n");
        }
        if (!admission.acceptingNewWork()) {
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).body("draining\n");
        }

        tracker.begin();
        try {
            Thread.sleep(milliseconds);
            return ResponseEntity.ok(
                    "done after " + milliseconds + "ms\n");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).body("interrupted\n");
        } finally {
            tracker.finish();
        }
    }
}
~~~

In the lab, the HTTP worker thread blocks in `Thread.sleep` to leave time to send SIGTERM. **Do not use unbounded sleep/blocking I/O in production**, and there is no business side effect in this endpoint. When already started before shutdown, the controller can still finish the response within the 20s grace. When a request starts after the gate closes but before the server rejects at the network layer, the controller can return **503**.

### 7.8. `src/main/java/com/example/shutdown/ShutdownSignals.java`

~~~java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownSignals {
    private static final Logger log =
            LoggerFactory.getLogger(ShutdownSignals.class);

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        log.info("EVENT ContextClosedEvent: close requested for context={}",
                 event.getApplicationContext().getId());
    }

    @PreDestroy
    public void onDestroy() {
        log.info("DESTROY @PreDestroy: singleton cleanup");
    }
}
~~~

This same bean has both an event listener and a destroy hook to compare logs. `ContextClosedEvent` usually appears **before** lifecycle stop. This bean's `@PreDestroy` runs **after** lifecycle processor stop processing. Do not assign long request-waiting tasks to `@PreDestroy`; here it only logs to demonstrate the bean destruction step.

### 7.9. `src/main/resources/application.properties`

~~~properties
server.address=127.0.0.1
server.port=8080
spring.application.name=lifecycle-shutdown-demo

# Spring Boot 3.5 enables graceful by default; declared explicitly for learning.
server.shutdown=graceful

# Applies to EACH SmartLifecycle shutdown phase, not total process timeout.
spring.lifecycle.timeout-per-shutdown-phase=20s

# Enable health/readiness probes while the app is running.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health

logging.level.com.example.shutdown=INFO
~~~

Boot Actuator exposes health endpoints per the configuration. If using `/actuator/health/readiness` to observe while running, it can report readiness appropriately. **During shutdown, the HTTP server also stops accepting new requests**, so an external probe may receive no response rather than returning `REFUSING_TRAFFIC` JSON at every moment. Do not use a probe timeout as evidence that readiness did not change.

### 7.10. Build and run the executable JAR

~~~bash
java -version
mvn clean package
java -jar target/lifecycle-shutdown-demo-0.0.1-SNAPSHOT.jar
~~~

Use **java -jar** instead of only `mvn spring-boot:run` so you can clearly identify the **JVM PID** to send SIGTERM to. With Maven/IDE, there may be a process wrapper or IDE Stop sending a non-production-like signal.

In another terminal:

~~~bash
curl -i "http://127.0.0.1:8080/work?ms=20"
curl -i "http://127.0.0.1:8080/actuator/health/readiness"
~~~

Expected `/work?ms=20` returns **200 OK**, body:

~~~text
done after 20ms
~~~

The response body has a trailing newline character. HTTP headers such as Date, Content-Type, and Keep-Alive may vary by Tomcat/version. `/actuator/health/readiness` in the ready state typically returns JSON `status=UP` with health groups enabled; implementations/health contributors may cause health to differ in special environments.

### 7.11. SIGTERM experiment with a 7-second request

**Terminal A**, keep the JVM running `java -jar` and watch the startup/shutdown logs.

**Terminal B**, send a 7-second request:

~~~bash
curl -i -v "http://127.0.0.1:8080/work?ms=7000"
~~~

**Terminal C**, immediately after confirming the request is running, send the signal to the **Java process PID**:

~~~bash
# Linux/macOS example: find the exact PID before sending the signal.
ps -ef | grep 'lifecycle-shutdown-demo-0.0.1-SNAPSHOT.jar'
kill -TERM <JAVA_PID>
~~~

`<JAVA_PID>` is a **placeholder** that must be replaced with the actual PID; do not copy the angle brackets literally. Do **not** use `kill -9`. Do not send signals to random processes; verify the PID/jar name first. On Windows, `Stop-Process -Force` is forceful and not an equivalent replacement for SIGTERM; console Ctrl+C can be used if the terminal delivers the event properly, though behavior needs verification. Production-like testing is more reliable in a controlled Linux/container environment.

**Expected design behavior:**
1. Spring Boot receives the shutdown request and begins closing the ApplicationContext.
2. `ShutdownSignals.onContextClosed` logs `EVENT ContextClosedEvent`.
3. Very high-phase `AdmissionLifecycle` stops, logging `ADMISSION stop`.
4. Web server graceful shutdown stops accepting new HTTP requests and **waits for the running 7-second request** to complete within 20s.
5. The in-flight request's `curl` can receive **200 OK** and body `done after 7000ms`.
6. Phase 0 `DrainLifecycle` stops after web server grace, logs `DRAIN complete, active=0` (barring error/timeout), and invokes the callback.
7. `ShutdownSignals.onDestroy` logs `DESTROY @PreDestroy`, and the process exits.
8. New requests during shutdown may get **connection refused/connection reset/503** depending on timing and server; there is **no** single fixed HTTP status across every hop.

**Do not treat this as captured output**: logs will have different timestamps/thread names, and the order among logs in the same phase/framework components may interleave. The milestones **between the three beans created in this lesson** and the server phase are what matter.

### 7.12. Testing a request longer than the grace period

Purpose: distinguish “best effort drain” from “every request finishes”.

In the lab, the controller caps `ms <= 15000` and server timeout per phase is 20s, so to create a situation that **intentionally exceeds grace**, you can run the JAR with:

~~~bash
java -jar target/lifecycle-shutdown-demo-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Then send a 7s request and SIGTERM while the request is running. Depending on the server and timing, the HTTP response may be cut off before the controller completes, or the server/context will move to subsequent phases after the timeout; no exact TCP error code is asserted across all versions. `DrainLifecycle` has its own phase and its 3s timeout is also affected here. This is a **boundary test**, not a production configuration.

If a real request has a 2-minute SLA, a 20s grace does not guarantee completion. The approach is to design asynchronous durable job APIs, progress polling/retries, idempotency keys, or increase the budget based on measured tail latency and orchestration capabilities.

## 8. Automated tests: phase ordering and HTTP path

### 8.1. `src/test/java/com/example/shutdown/LifecyclePhaseTest.java`

This test uses a standalone `AnnotationConfigApplicationContext` to demonstrate the **phase rule** without depending on timing or server sockets. Do not mix it with the Spring Boot web app context in the same test.

~~~java
package com.example.shutdown;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecyclePhaseTest {

    @Test
    void phaseAscendingAtStartDescendingAtClose() {
        List<String> events = new ArrayList<>();
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.registerBean("low", Probe.class,
                () -> new Probe("low", -100, events));
        context.registerBean("high", Probe.class,
                () -> new Probe("high", 100, events));

        try {
            context.refresh();
            assertEquals(List.of("start low", "start high"), events);
        } finally {
            context.close();
        }

        assertEquals(List.of(
                "start low", "start high",
                "stop high", "stop low"), events);
    }

    static class Probe implements SmartLifecycle {
        private final String name;
        private final int phase;
        private final List<String> events;
        private boolean running;

        Probe(String name, int phase, List<String> events) {
            this.name = name;
            this.phase = phase;
            this.events = events;
        }

        @Override
        public void start() {
            events.add("start " + name);
            running = true;
        }

        @Override
        public void stop(Runnable callback) {
            try {
                events.add("stop " + name);
                running = false;
            } finally {
                callback.run();
            }
        }

        @Override
        public void stop() {
            events.add("stop " + name);
            running = false;
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

Expected **JUnit PASS** for two beans at phase -100/+100, with the exact sequence asserted. `stop(Runnable)` is invoked by the lifecycle processor on context close; the `stop()` method is not the variant preferred by the processor for SmartLifecycle.

**Test limitation:** it does not prove how the embedded web server handles keep-alive or in-flight requests. That requires the `SIGTERM` smoke test in section 7 and real infrastructure testing.

### 8.2. `src/test/java/com/example/shutdown/WorkHttpTest.java`

~~~java
package com.example.shutdown;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WorkHttpTest {

    @LocalServerPort
    int port;

    @Test
    void workCompletesBeforeShutdown() {
        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/work?ms=10")
                .retrieve()
                .body(String.class);

        assertEquals("done after 10ms\n", body);
    }
}
~~~

With the Spring Boot test dependency in the POM, this is an HTTP test running **real embedded Tomcat** on a random port, verifying that the route/controller works. It **does not send SIGTERM** and does not close the context mid-request; the SIGTERM smoke test in the previous section observes graceful drain.

Run:

~~~bash
mvn test
~~~

Expect **two passing tests** when the project is correct and the Java/Maven/dependencies runtime is complete. This is the **expected result from the source**, not a claim that it has been built/tested on the reader's machine.

## 9. Kubernetes: readiness, SIGTERM, preStop, and termination budget

A standard Pod when terminated:
1. Kubernetes starts counting **`terminationGracePeriodSeconds`**.
2. If there is a `preStop` hook, the hook runs within that grace window.
3. The runtime sends SIGTERM to the process in the container (the exact path depends on the runtime and preStop).
4. The Spring application starts its shutdown hook/context close, switches readiness to **`REFUSING_TRAFFIC`**, and stops accepting new requests per web server graceful logic.
5. Kubelet waits for the process to exit; upon deadline expiration it may SIGKILL, losing cleanup.

**Do not add `preStop` outside termination grace**: preStop **consumes the same budget**. If the app uses multiple SmartLifecycle phases, the Kubernetes budget must be **larger than the sum of stages that may wait + preStop + margin**.

**Illustrative** Pod/container configuration example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lifecycle-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lifecycle-demo
  template:
    metadata:
      labels:
        app: lifecycle-demo
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: example/lifecycle-demo:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

**Very important caveat:** the lab project's `application.properties` binds `server.address=127.0.0.1`, so it **cannot receive traffic via the Pod IP** in the Kubernetes configuration above if kept as-is. When containerizing, override `--server.address=0.0.0.0` (or edit the config appropriately) and enforce authentication/network policies. `image: example/lifecycle-demo:1.0.0` is an **illustrative image name, not a pre-built image**. `preStop sleep 5` is an **operational trade-off** that can provide a window for endpoint propagation/routing updates, does not replace graceful shutdown correctness, and should not be treated as a mandatory standard. Choose sleep via measurement, not blind copying.

### 9.1. Readiness vs liveness

| Signal | Meaning | What to avoid |
| --- | --- | --- |
| **Liveness** | Process is in a recoverable state; restart if severely deadlocked | Putting every transient dependency error into liveness and causing a restart storm |
| **Readiness** | Whether the Pod should receive new traffic from the service | Treating readiness 200 as a promise that in-flight requests are done |
| **Graceful stop** | Drain old requests, reject new ones, then destroy resources | Assuming readiness REFUSING_TRAFFIC means HTTP connections still return 503 |
| **preStop** | Hook running inside grace before SIGTERM | Hook too long, leaving no time for Spring |
| **terminationGracePeriodSeconds** | Total Pod termination deadline | Setting it equal to a single phase timeout while forgetting other phases |

Spring Boot Actuator has health probe groups and the states `ReadinessState.ACCEPTING_TRAFFIC` and `ReadinessState.REFUSING_TRAFFIC`. When the context closes, readiness transitions to refusing traffic during graceful shutdown; however, the HTTP connector is also closing, so an external probe **may not receive JSON**. Load balancers/endpoints controllers have propagation delay; to avoid dropping requests, coordinate routing + sufficient grace, not just in-JVM state.

### 9.2. Docker and PID 1

Prefer exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

so Java is PID 1 and receives the stop signal. Do not use a wrapper shell that swallows `SIGTERM` or forgets `exec java ...`. If an init process is needed for signal forwarding/reaping, use a proper container runtime solution. `docker stop` usually sends SIGTERM followed by SIGKILL after the configured timeout; adjust stop-grace-timeout so the app has corresponding time.

Do not rely on `docker kill` (which sends a hard kill by default) or forced restarts to verify graceful shutdown. App logs after SIGTERM should show lifecycle lines.

## 10. Relationship with background consumers, schedulers, and database pool

Not every component should be in phase 0. In a real design, classify them first:

| Component | Desired behavior at shutdown | Typical choice |
| --- | --- | --- |
| Admission control or queue listener accepting new tasks | Stop early, accept no new work | **High**-phase SmartLifecycle |
| Embedded HTTP server | Block new requests, wait for in-flight | Boot web server graceful lifecycle |
| Handler dependencies such as business services/DB repositories | Remain usable while HTTP requests drain | Destroy only after lifecycle stop |
| Batch worker processing accepted tasks | Finish/rollback/park within bound | Appropriate-phase SmartLifecycle + bounded stop(Runnable) |
| Kafka listener / Rabbit listener container | Stop consuming, commit/ack offsets per contract | Use container lifecycle integration and proper phase |
| Scheduled tasks | Stop scheduling and finish finite jobs | Scheduler lifecycle hooks, cooperative cancellation |
| JDBC/HikariCP pool | Close when nobody uses it anymore | Spring-managed bean destruction after drain |
| HTTP client/connection pool | Finish in-flight downstream calls, then close | Bean destruction or explicit bounded stop |
| Metrics/OTLP exporter/logging | Bounded flush, avoid unexpected signal loss | Framework shutdown integration + timeout |
| Custom executor | Stop accepting tasks, wait for bounded termination | Properly ordered lifecycle or destroy hook |

**Common mistake:** `@PreDestroy` of a database bean may run after `LifecycleProcessor.onClose`, yet dependency-aware ordering still applies across singleton destructions. If you manually call `dataSource.close()` inside a **ContextClosedEvent** listener, you force the DB into a closed state **before** HTTP drain finishes. If a custom high-phase SmartLifecycle closes a queue/executor while HTTP handlers are still calling it, in-flight requests can fail even though the web server is still graceful.

Therefore, you must **inspect the dependency graph and phases of the entire pipeline**, not just a single bean's phase value. `@DependsOn`/constructor dependencies can affect start/stop; test under load and races. Spring Boot's web server lifecycle does not automatically “know” every side effect in the app.

### 10.1. With HTTP long-lived connections

For **SSE, WebSocket, WebFlux Flux streams, streaming downloads, or async MVC**, a request can outlast the grace period. A clear policy is needed:
- stop new subscriptions before shutdown;
- send an event notifying server going away/reconnect hint if the protocol supports it and the connection is still alive;
- close the stream/cancel the subscription by the deadline, saving a cursor/Last-Event-ID if resume is needed;
- clean up subscribers/resource handles;
- ensure multi-replica reconnection to a live instance and provide a replay mechanism if no data may be lost.

Do not set timeouts to infinity just because SSE is long-lived: rollouts will stall and Kubernetes may SIGKILL. With WebFlux, `ApplicationContext`/`SmartLifecycle` principles still apply, though the HTTP runtime is Reactor Netty or a servlet-compatible server; test shutdown against the runtime in use.

### 10.2. Is stopping a message consumer safer than HTTP drain?

There is no single default phase suitable for every message broker. A consumer processing a 30s message may need to pause/stop receiving, commit offsets/ack after work finishes, and avoid duplicate processing on restart. If the stop callback reports completion too early, the context may destroy the DB/client while the consumer thread is still using it. If it never invokes the callback, LifecycleProcessor waits out the phase and may move on while the consumer is still running.

Design according to the Kafka/Rabbit/SDK contract: in-flight count, ack/commit and transaction boundaries, retry/redelivery, bounded drain. **Idempotent consumers** are still necessary because a forced kill can happen at any time.

## 11. Programmatic shutdown: usage and warnings

### 11.1. `SpringApplication.exit`

Snippet inside an intentional tool/CLI:

~~~java
ConfigurableApplicationContext ctx = SpringApplication.run(App.class, args);

// When deciding to close the application from a controlled flow:
int exitCode = SpringApplication.exit(ctx);
// exit() closes the context and computes the code; to terminate the JVM:
// System.exit(exitCode);
~~~

This is a **non-standalone illustrative snippet** (requires `App` and imports). Do not put this snippet in `main` right after `run` for a web service: the application will close immediately. Do not call `System.exit` from a request thread just because of a business error; a single request failure is not a reason to kill the entire process.

### 11.2. `registerShutdownHook`

Spring Boot creates a shutdown hook by default for contexts managed by SpringApplication. You may have multiple JVM hooks from libraries; **there is no guaranteed execution order among independent JVM shutdown hooks**. Therefore, do not rely on an arbitrary `Runtime.addShutdownHook` running “before the Spring hook” to manually close the DB or send logs. Prefer placing cleanup into the Spring-managed lifecycle while dependencies are still active.

If you intentionally call `setRegisterShutdownHook(false)`, you are responsible for explicit closing along the process path. Do not disable the hook to “fix” a bean that stops too slowly; fix that bean's stop/callback/deadline first.

### 11.3. Can `ContextClosedEvent` be called multiple times?

A normal context only closes once, but systems with a **context hierarchy** (parent/child Spring contexts) can have listeners receive events from multiple contexts, and test suites create/close multiple contexts. If business code relies on the event to write audit records or call external APIs, it must check the event source context and idempotence; do not assume “one event per JVM” across every architecture.

## 12. SmartLifecycle anti-patterns

| Anti-pattern | Risk | Correct approach |
| --- | --- | --- |
| Implementing `SmartLifecycle.stop(Runnable)` without calling the callback | Phase waits until timeout, prolonging shutdown | Call the callback after stopping, including error branches |
| Calling the callback as soon as the async task starts | Processor continues destroying beans while task still uses them | Only callback after actually finishing or making a controlled decision to abandon |
| Blocking indefinitely inside `stop(Runnable)` | Shutdown hook hangs, Kubernetes SIGKILL | Set a deadline, stop cooperatively, invoke callback |
| Using `@PreDestroy` to block new HTTP requests | Hook runs too late compared to web drain | Admission gate with an appropriate SmartLifecycle phase |
| Using `ContextClosedEvent` to shut down DataSource | In-flight HTTP requests lose DB access | Let Spring destroy resources after drain |
| Thinking a smaller phase stops first | Order is reversed: stops from **high to low** | Choose phases from dependency/drain design |
| Only putting `@Order` on a bean hoping lifecycle changes | @Order does not replace the getPhase contract | Implement `getPhase` and the dependency graph |
| Giving all beans phase MAX_VALUE | Loses meaningful ordering, stops too early | Assign clear phase responsibilities and test |
| Using `server.shutdown=immediate` to “stop hanging” | Cuts off in-flight HTTP | Find slow requests/phase callbacks and set bounds |
| Setting shutdown phase timeout too small | Aborts app mid-transaction/download | Budget based on measured latency and retries |
| Setting timeout too large while Pod grace is 10s | Kubernetes force-kills before app drains | Increase orchestrator budget and coordinate readiness |
| Testing with `kill -9` and concluding graceful is broken | SIGKILL bypasses hooks | Test SIGTERM to the right JVM |
| Trusting IDE Stop always sends SIGTERM | May force terminate | Run real jar/process to test |
| Relying on `@PreDestroy` to save critical state | Does not run on crash/SIGKILL | Persist state continuously, use retries/idempotency |
| Using a public GET shutdown endpoint | Anyone can kill the service | Process manager/orchestrator; strict security |
| Using health readiness as auth or a drain lock | Health state does not prevent business races | Admission gate + traffic routing + retries |
| Closing thread pool before consumers finish using it | RejectedExecutionException/lost jobs | Stop intake → drain → close resource |
| Ignoring executor/context thread leaks | Process fails to exit on time | Resource ownership, monitoring, and finite deadlines |

## 13. Runbook when a service fails to exit or drops requests during deploy

1. **Identify the actual stop signal:** SIGTERM or SIGKILL? Is Java PID 1? Does the shell wrapper/IDE forward signals?
2. **Check if `ContextClosedEvent` appears in logs.** If not, check signal delivery, crash/OOM, logger shutdown order, process wrapper.
3. **Check web server graceful logs.** Did draining start? `server.shutdown=immediate`? Boot version/server type?
4. **Check `spring.lifecycle.timeout-per-shutdown-phase` and the number of phases.** Total time may exceed a single phase timeout.
5. **List `SmartLifecycle` beans and phases** using dev-only instrumentation or bean inspection; watch out for default phase Integer.MAX_VALUE and dependency ordering.
6. **Audit `stop(Runnable)`:** is the callback called at the right time? Are errors/rejected tasks, `isRunning` state, and timeouts handled? Is any thread blocked?
7. **Find in-flight HTTP requests:** longer than grace, slow clients, SSE/WebSocket, large uploads/downloads, deadlocks, slow DB.
8. **Check background workers/DB pools:** is any resource closing before requests/jobs finish? Is new work admitted while shutting down?
9. **Check probes and load balancer:** readiness becoming REFUSING_TRAFFIC, endpoint propagation delay, preStop, and termination budget.
10. **Inspect client errors:** connection refused/reset vs 503, 504 from an upstream gateway? Do not assume every error came directly from the application returning that status.
11. **Reproduce in a controlled way:** run JAR, send a 7s request, SIGTERM, observe log order and response; repeat with timeout 3s to see the limit.
12. **Fix the root cause:** phase/lifecycle callbacks, deadlines, load balancer draining, retries/idempotency, rather than endlessly increasing timeouts.

### 13.1. Symptom and differentiation table

| Symptom | Possible cause | Check to perform |
| --- | --- | --- |
| SIGTERM sent but no close logs | Signal did not reach Java, hard kill, crash | PID tree, container entrypoint, OS events |
| ContextClosedEvent logged yet server still accepts requests briefly | Listener runs before stop phases | Track phases/grace; do not treat event as server stopped |
| Stuck for exactly 20s in one phase | Bean missing callback or waiting for 20s timeout | Inspect stop(Runnable), thread dumps |
| Pod killed at exactly 30s | Kube terminationGracePeriod too short | Describe Pod, kubelet events, manifest |
| Connection reset during a 5s GET | immediate shutdown, upstream LB, timeout, SIGKILL | Compare web logs/curl/network/proxy |
| Graceful requests finish yet process does not exit | Remaining phases/bean destruction/background non-daemon threads still running | Thread dumps and phase logs |
| HikariCP closed before handler finishes | Resource closed in event/high phase or custom manual close | Find custom listener/stop logic |
| Shutdown does not wait for Kafka job to finish | Consumer stop callback completed too early or no drain | Consumer metrics/offsets/in-flight |
| Callback not called because executor rejected | Executor already stopped before the component | Fix phase/dependency, add completion fallback |
| `@PreDestroy` not printed on `kill -9` | SIGKILL does not run hooks | Test `kill -TERM` |
| IDE stop drops requests | IDE uses force kill | Verify SIGTERM using jar process |
| Nginx 502/503 while app logs no error | LB/backend connector is draining | Access logs at each hop, readiness |
| `/actuator/health/readiness` returns no JSON while stopping | Connector stopped accepting new HTTP | Read availability state inside process/logs |
| Consumer stops before web, causing 503 in controller | Inappropriate high consumer SmartLifecycle phase | Adjust drain ordering or decouple pipeline |
| App restarts and reprocesses job | At-least-once/redelivery after crash | Idempotency, dedup, persistent checkpoints |

## 14. Production checklist

**Operational goal:** Stop accepting new work, finish accepted work within deadline, close resources per dependencies, and exit process before orchestrator deadline.

- [ ] Confirm Boot version and embedded server; `server.shutdown=graceful` is set properly.
- [ ] `spring.lifecycle.timeout-per-shutdown-phase` fits actual tail latency.
- [ ] Admission/drain policies exist for web requests, consumers, schedulers, and streaming endpoints.
- [ ] SmartLifecycle phases reflect dependencies; do not rely arbitrarily on MAX phase.
- [ ] All `stop(Runnable)` implementations invoke the callback exactly once after stopping or controlled error termination.
- [ ] Every drain has a deadline; resources stay alive until the last callers finish.
- [ ] `@PreDestroy` cleanup is bounded, idempotent, and does not call already-stopped services.
- [ ] JVM receives SIGTERM to the proper PID; not swallowed by a shell wrapper.
- [ ] Kubernetes terminationGracePeriodSeconds covers preStop + sum of stop phases + destruction + margin.
- [ ] Readiness refuses new traffic; load balancer has matching routing/drain policies.
- [ ] Long-lived SSE/WebSocket/async requests have close/reconnect strategies.
- [ ] Queue/broker jobs have checkpoints, retries, and idempotent processing.
- [ ] Test via SIGTERM with in-flight requests, slow DB/clients, background jobs, load, and forced kills.
- [ ] Logs/metrics measure time-to-drain, active requests/jobs, phase timeouts, and errors.
- [ ] Do not treat graceful shutdown as an exactly-once or transaction commit guarantee.

## 15. Self-check questions

1. Does `ApplicationContext.close()` only call `Tomcat.stop()`?
2. Does `ContextClosedEvent` arrive before or after `LifecycleProcessor.onClose()`?
3. Does `@PreDestroy` usually run before or after SmartLifecycle stop processing?
4. What is the default of `SmartLifecycle.isAutoStartup()`?
5. What value is `SmartLifecycle.DEFAULT_PHASE`?
6. Do start phases increase or decrease? Do stop phases increase or decrease?
7. Why can dependency relationships change the order expected from phases?
8. Which callback does `DefaultLifecycleProcessor` wait for in an async stop?
9. Why does forgetting `callback.run()` slow down shutdown?
10. Is `spring.lifecycle.timeout-per-shutdown-phase` the total JVM shutdown time or per phase?
11. In Boot 3.5, which web servers have graceful shutdown enabled by default?
12. How does `server.shutdown=immediate` differ from `graceful`?
13. Should a component that keeps the DB service alive until HTTP drain completes stop before or after the web server?
14. Why is `ContextClosedEvent` not an ideal place to close HikariCP early?
15. Why does `@Order(1)` not replace `SmartLifecycle.getPhase()`?
16. Does `kill -9` run JVM shutdown hooks and `@PreDestroy`?
17. Why might `mvn spring-boot:run` not be the most reliable way to test SIGTERM?
18. Does Kubernetes `preStop` consume `terminationGracePeriodSeconds`?
19. When readiness is `REFUSING_TRAFFIC`, must an external HTTP probe necessarily receive 503/JSON?
20. Why can requests exceeding the grace period still fail even in graceful mode?
21. What does it mean for a stop callback to report completion too early?
22. When a background queue consumer has no SmartLifecycle, does web graceful wait for it?
23. Why are idempotent retries still needed after a crash even with graceful shutdown enabled?
24. Can `SpringApplication.exit(context)` be used without calling `System.exit`?
25. For infinitely open SSE/WebSocket connections, what policy is needed during rollout?
26. In `LifecyclePhaseTest`, why does start go low/high while stop goes high/low?
27. Which is more appropriate for releasing bean resources: ContextClosedEvent or singleton destroy callbacks?
28. If a process is OOM-killed, which persistence primitives should be relied upon instead of @PreDestroy?
29. What is the purpose of using a very high phase for an admission gate?
30. When timeout per phase is 20s but total shutdown takes 50s, is the framework necessarily malfunctioning?

**Key answers:** (1) No, it closes the whole Spring context, lifecycles, and destroy callbacks. (2) Before. (3) After lifecycle stop processing. (4) True. (5) Integer.MAX_VALUE. (6) Start ascends, stop descends. (7) Dependencies take precedence. (8) SmartLifecycle.stop(Runnable). (9) The processor waits until timeout. (10) Per phase. (11) Tomcat, Jetty, Reactor Netty, Undertow. (12) Drain in-flight vs stop immediately. (13) After web server drain. (14) Requests still need the DB. (15) Phase belongs to the lifecycle processor; @Order does not replace it. (16) No. (17) Signal may hit the process wrapper. (18) Yes. (19) No, the connector may already be closed. (20) Finite deadline. (21) Reporting done while tasks still run and use dependencies. (22) Does not automatically know about your jobs. (23) Forced kills and network failures still occur. (24) Yes, it returns an exit code; JVM termination is separate. (25) Close/cancel, reconnect/resume, limits. (26) Stop reverses start phases. (27) After drain, in bean destruction. (28) Durable queues/checkpoints/idempotency. (29) Stop accepting work before web drain. (30) No, multiple phases/destruction/preStop.

## 16. Official documentation

- Spring Boot 3.5 — **Graceful Shutdown** (defaults, web servers, per-phase timeout, rejection differences): https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- Spring Boot 3.5 — **SpringApplication, Application Exit, JVM shutdown hook and events**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — **Actuator Endpoints, Application Lifecycle and Probe States**: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Framework 6.2 — **Customizing the Nature of a Bean: Lifecycle and SmartLifecycle phase**: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- Spring Framework 6.2 — **SmartLifecycle API**, callback, DEFAULT_PHASE: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.2 — **DefaultLifecycleProcessor API**, phase ordering and shutdown waits: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.2 — **AbstractApplicationContext API**, doClose/ContextClosedEvent/destroyBeans: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Boot 3.5 — **WebServerGracefulShutdownLifecycle API**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/context/WebServerGracefulShutdownLifecycle.html
- Kubernetes — **Pod Termination/Lifecycle**, preStop and terminationGracePeriodSeconds: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- Spring Boot 3.5.16 release and support status: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
