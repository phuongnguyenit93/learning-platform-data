# spring.lifecycle.timeout-per-shutdown-phase and Completion Wait Time

## 1. When the system receives SIGTERM: why isn't 30 seconds still enough?

A Spring Boot application is handling HTTP requests, writing database records, and running background consumers/workers. During a Kubernetes rolling deploy, old requests get cut off, jobs are left half-done, or Pods get `SIGKILL`ed before flushing data. Operators added:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

yet the application sometimes **takes longer than 30 seconds to stop**, and sometimes gets cut off **before 30 seconds have passed**. This is not a contradiction: this property **is not a hard timeout for the entire JVM**. In Spring Boot, it controls **how long Spring's LifecycleProcessor waits for SmartLifecycle beans in each phase group to finish stopping**. The HTTP graceful shutdown duration is one part of that mechanism, while platform termination deadlines, executor shutdowns, preStop hooks, destroy callbacks, and network timeouts are separate clocks.

This lesson belongs to **Graceful Shutdown** and targets these skills:
- Understanding `spring.lifecycle.timeout-per-shutdown-phase` accurately **per phase**, without confusing it with HTTP request timeouts or total shutdown duration.
- Distinguishing `server.shutdown=graceful`, `ApplicationContext.close()`, `SmartLifecycle.stop(Runnable)`, `@PreDestroy`, SIGTERM/SIGKILL, readiness, and draining.
- Determining phase ordering, asynchronous callbacks, dependency ordering, and what happens when a phase times out.
- Coordinating with Kubernetes `terminationGracePeriodSeconds` and `preStop`, load balancer deregistration, and task executors.
- Running a Java 17+/Spring Boot 3.5 demo with a slow request and two SmartLifecycle beans at phases 200 and 100; measuring results when sending SIGTERM.
- Designing deadlines/recovery for long requests, SSE/WebSocket, jobs, and non-idempotent side effects.
- Having a real deployment testing checklist and knowing how to observe logs/metrics.

> **Versions:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, Spring MVC/Tomcat for the demo. Per Boot 3.5 documentation, **graceful HTTP shutdown is enabled by default** for embedded Jetty, Reactor Netty, Tomcat, and Undertow, for both reactive and Servlet. `spring.lifecycle.timeout-per-shutdown-phase` defaults to **30s**. Older versions may default HTTP shutdown to immediate; always check the exact version's documentation.

## 2. Definition of the property

Configuration in `application.yml`:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Equivalent:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`20s` is a `Duration`. When needed, values with units such as `500ms` or `1m` can be used. Always write the unit explicitly to avoid confusing seconds and milliseconds.

**Spring Boot 3.5 describes the property** as the timeout for stopping **any phase** (a group of `SmartLifecycle` beans sharing the same `phase` value). A phase may contain multiple beans. Within each phase, the lifecycle processor waits for callbacks or until the timeout expires. If an app has multiple phases, total wait time can exceed a single `timeout-per-shutdown-phase` value—**the framework is not ignoring the property**.

### Concept comparison

| Subject | What it bounds | What it does not bound |
|---|---|---|
| `spring.lifecycle.timeout-per-shutdown-phase` | Wait time for **one SmartLifecycle stop group** | Total JVM time, all `@PreDestroy` hooks, every worker task |
| `server.shutdown=graceful` | Selects HTTP server shutdown mode for in-flight requests | Sets no duration of its own without lifecycle timeout |
| `server.shutdown=immediate` | Selects non-graceful shutdown for HTTP | Does not disable other SmartLifecycle phases |
| HTTP read/request timeout | Processing/communication time of one request in the stack | Does not automatically wait for context close |
| `terminationGracePeriodSeconds` | Total termination budget enforced by Kubernetes | Does not alter Spring lifecycle properties |
| `preStop` | A container lifecycle hook | Does not grant an independent extra Spring budget |
| `@PreDestroy` | Bean destruction callback | Not automatically timeboxed by the lifecycle property |
| `spring.task.execution.shutdown.await-termination-period` | Wait time for the corresponding Boot-managed executor | Does not wait for unmanaged custom executors |

**Consequence:** you must design multiple **coordinated** timeouts instead of expecting this single config setting to replace the other mechanisms.

## 3. What is a SmartLifecycle phase?

Spring Framework defines `Lifecycle` with `start()`, `stop()`, `isRunning()`; `SmartLifecycle` adds auto-startup, phases, and a stop callback:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

This is a **simplified model** of the interface, not the complete Spring source code. Usage:
- Each bean defines `getPhase()`.
- **Startup** proceeds from lowest phase → highest phase.
- **Shutdown** proceeds in reverse: highest phase → lowest phase.
- Beans **in the same phase** are grouped into one stop round.
- `stop(Runnable callback)` can complete asynchronously; the lifecycle processor waits for the **callback**.
- The callback must be invoked after the bean finishes its stop process, **exactly once**, even when reporting a controlled failure.
- Explicit `depends-on` dependency relationships can override ordering, so do not treat phases as a substitute for understanding dependencies.

### Multiple beans in the same phase

Suppose phase 200 has three beans:
- Bean A stops after 1s.
- Bean B stops after 5s.
- Bean C stops after 12s.

When `timeout-per-shutdown-phase=10s`, phase 200 **does not get 10s each for A, B, and C**. The processor can wait on the group for up to ~10s. A and B have already called back; when C has not finished, the phase can time out and the processor moves on to subsequent phases.

If all beans stop asynchronously in the same group and have no special dependencies, the total phase duration is typically governed by the **slowest bean**, rather than summing every bean's time sequentially. However, if a bean works **synchronously and blocks inside its stop method**, the processor may have no way to enforce the wait limit like an external thread interrupter.

### Multiple different phases

Example:
- Phase 300 takes 4s to stop.
- Phase 200 takes 6s to stop.
- Phase 100 takes 3s to stop.

With a **10s per-phase** timeout, those three phases alone take nearly **13s**, even though each individual phase finished well under 10s. If custom phases stop slowly and the web server phase precedes them, JVM shutdown time can be even longer.

**Mental formula:** stop time ≈ sum of actual durations of sequentially processed phases + time of other callbacks/destruction + overhead; not `max(phase durations)` and not a single shared timeout.

## 4. When does web server graceful shutdown take place?

A conceptual flow:

~~~text
Process receives SIGTERM / ApplicationContext.close
             |
             v
       Spring Context closing
             |
             v
    DefaultLifecycleProcessor
             |
             +-- HTTP server graceful stop (early phase)
             |     +-- stop accepting new HTTP requests
             |     +-- wait for in-flight requests to finish
             |     +-- stop waiting when phase times out
             |
             +-- SmartLifecycle high custom phase
             |     +-- stop(Runnable callback)
             |
             +-- SmartLifecycle low custom phase
             |     +-- stop(Runnable callback)
             |
             +-- destroy callbacks / resource close
             |
             v
        JVM process exits
~~~

Spring Boot 3.5 states that HTTP graceful shutdown happens in the **first phase of the SmartLifecycle stop sequence**. The server gives in-flight requests a chance to end, while preventing new requests from starting.

Embedded servers differ in how they reject:
- Tomcat, Jetty, and Reactor Netty may stop accepting new requests at the network layer.
- Undertow, per Boot 3.5 docs, may still accept connections and return **503 Service Unavailable**.
- HTTP keep-alive/persistent connections can make behavior differ from expectations set by a simple client.

**Never claim** that after SIGTERM every new client receives 503, or every old client receives 200. There can be connection refused, resets, incomplete responses, proxy 502/503/504, or timeouts. The outcome depends on the server, LB, request lifecycle, connection pool, and platform.

### Limitations

If `/api/export` needs 60s while only 10s remain before the phase timeout, graceful shutdown does not automatically:
- Migrate the running request to another pod.
- Extend Pod termination time.
- Guarantee the 60s of work gets rolled back.
- Return a fixed HTTP status upon timeout.
- Re-run the request in an exactly-once manner.

If work is long-running or side effects matter, dedicated **durable queues/operation IDs, idempotency, status reconciliation, or checkpoints** are required.

## 5. When is the callback truly completed?

Incorrect snippet:

~~~java
// WRONG: performs async stop without signaling completion.
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        flushPendingWrites();
        // callback.run() was forgotten!
    });
}
~~~

If this bean is in phase 100, the processor may wait for the **entire phase timeout** even though `flushPendingWrites()` already finished.

Illustrative snippet showing the right contract:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            flushPendingWrites();
        } catch (Exception failure) {
            recordShutdownFailure(failure);
        } finally {
            callback.run();
        }
    });
}
~~~

The names `executor`, `flushPendingWrites`, and `recordShutdownFailure` are project-defined APIs; this code is a **fragment**, not standalone. When applying it:
1. Do not use an executor **that has already been shut down** before the bean calls `stop`.
2. If `executor.execute(...)` throws `RejectedExecutionException` upon submission, have a fallback policy and avoid leaving the lifecycle processor waiting forever.
3. The callback only signals completion of the **component stop procedure**; it does not prove partner side effects committed.
4. Do not invoke the callback before mandatory flushes complete just to “shut down fast”.
5. On failure, record what remained unfinished for recovery after restart.
6. When a timeout is needed for network flushes, enforce a deadline inside the operation itself; do not wait for the lifecycle processor to interrupt you.
7. Stop accepting **new work** before measuring outstanding work, avoiding an endless backlog.

### Synchronous vs asynchronous stop

`stop()` without a callback belongs to `Lifecycle`; it works for synchronous stops. With `SmartLifecycle`, `stop(Runnable)` permits async completion. Do not confuse:
- “Bean has started stopping” with “bean has completely stopped”.
- “Processor stopped waiting” with “all cleanup tasks were canceled”.
- “Callback was invoked” with “business data was committed end-to-end”.

## 6. Per-phase timeout is not a hard interrupter

This is a critical technical detail. If `stop(Runnable)` spawns another task and returns right away, Spring can enforce the timeout while **waiting for the callback**. But if `stop(Runnable)` itself calls a long blocking network I/O before returning:

~~~java
// RISKY: fragment blocks directly inside the stop call.
@Override
public void stop(Runnable callback) {
    blockingSdk.flushWithoutTimeout();
    callback.run();
}
~~~

then the default processor does not necessarily have a way to sever this thread right at the phase deadline. A `Duration` property **is not equivalent** to `Thread.interrupt()`, HTTP cancellation, transaction rollback, or `SIGKILL`.

For stop I/O operations, use:
- An SDK with **connect/read/operation timeouts**.
- Futures/async completion with bounded timeouts, if cancellation actually makes sense.
- A shared component deadline clock (do not let each I/O attempt spend the entire grace).
- Durable outbox/checkpoints when the deadline expires.
- Logging of the reasons for incomplete work.

Do not use `System.gc()`, `Thread.stop()`, or infinite wait loops to “ensure safety”.

## 7. @PreDestroy is a different stage

`@PreDestroy` and `DisposableBean.destroy()` are invoked by Spring during bean destruction. They are not automatically bounded by `spring.lifecycle.timeout-per-shutdown-phase` like `SmartLifecycle` stop callbacks.

Counter-example:

~~~java
// Illustrative only; should not be done in production.
@PreDestroy
void destroy() throws InterruptedException {
    Thread.sleep(60_000);
}
~~~

If the phase timeout is 10s, there is no contract guaranteeing that the `@PreDestroy` block above will be interrupted after 10s. It can delay context close until it finishes or gets killed by the platform. Therefore:
- `@PreDestroy` suits small, fast, bounded cleanup.
- Multi-stage consumer/background loop stopping should consider `SmartLifecycle`.
- Take real runtime measurements rather than assuming bean destruction is always instantaneous.
- Do not place all critical persistence flushes inside an unbounded destroy callback.

### Bean dependency ordering

A consumer needs a database client to commit its final offset. If the DB pool closes **before** the consumer, the consumer's callback can fail. Design the order:
1. Block new work.
2. Stop/finish running workers.
3. Commit/checkpoint.
4. Close downstream clients, data sources, and caches when nothing uses them anymore.
5. Finish observability/logging via framework mechanisms.

The exact order depends on service architecture. Spring `depends-on` and phases are supporting tools, not substitutes for understanding resource relationships.

## 8. Runnable practice: Spring Boot Java 17 with two SmartLifecycle phases

Goal: create a project with:
- `GET /api/fast` returning HTTP 200 immediately.
- `GET /api/slow?ms=6000` running 6 seconds on a Servlet thread.
- `SmartLifecycle` bean `cache-flush` at phase **200**, taking ~1.2s to stop.
- `SmartLifecycle` bean `consumer-stop` at phase **100**, taking ~1.2s to stop.
- During shutdown, the web server graceful phase waits first, then **phase 200 → phase 100**.
- Easy to change cleanup delay via a JVM system property and phase timeout via a Boot CLI flag.

**Local demo only.** `Thread.sleep` provides observable timing and does not represent durable business cleanup.

### 8.1. Dependencies

Create a project from Spring Initializr:
- Artifact ID: `shutdown-phase-demo`.
- Spring Boot **3.5.x**, Java **17+**, Gradle.
- Dependency **Spring Web**; add **Spring Boot Starter Test** for tests.

In a project already using the Gradle plugin/dependency management, `dependencies` correspond to:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **Gradle fragment**, not the complete `build.gradle` file. The Gradle wrapper is generated by Initializr.

### 8.2. Complete Java file

Create `src/main/java/demo/shutdown/ShutdownPhaseDemoApplication.java`:

~~~java
package demo.shutdown;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ShutdownPhaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownPhaseDemoApplication.class, args);
    }

    @Bean
    SmartLifecycle cacheFlusher() {
        return new DelayedStopBean(
            "cache-flush", 200, Long.getLong("demo.cleanup.ms", 1200L));
    }

    @Bean
    SmartLifecycle messageConsumer() {
        return new DelayedStopBean(
            "consumer-stop", 100, Long.getLong("demo.cleanup.ms", 1200L));
    }

    private static final class DelayedStopBean implements SmartLifecycle {
        private final String name;
        private final int phase;
        private final long delayMs;
        private final AtomicBoolean running = new AtomicBoolean();

        private DelayedStopBean(String name, int phase, long delayMs) {
            this.name = name;
            this.phase = phase;
            this.delayMs = delayMs;
        }

        @Override
        public void start() {
            running.set(true);
            System.out.println(name + " START phase=" + phase);
        }

        @Override
        public void stop(Runnable callback) {
            System.out.println(name + " STOP_BEGIN phase=" + phase);

            Thread cleanupThread = new Thread(() -> {
                try {
                    Thread.sleep(delayMs);
                    System.out.println(
                        name + " STOP_COMPLETE phase=" + phase);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println(
                        name + " STOP_INTERRUPTED phase=" + phase);
                } finally {
                    running.set(false);
                    callback.run();
                }
            }, name + "-cleanup");

            // Use daemon thread only for studying timeout behavior.
            cleanupThread.setDaemon(true);
            cleanupThread.start();
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
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return phase;
        }
    }
}

@RestController
class DemoHttpController {

    @GetMapping("/api/fast")
    public Map<String, String> fast() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/slow")
    public Map<String, Object> slow(
            @RequestParam(defaultValue = "6000") long ms)
            throws InterruptedException {

        if (ms < 0 || ms > 15000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "ms must be between 0 and 15000"
            );
        }

        System.out.println("HTTP_WORK_BEGIN ms=" + ms);
        // Simulate synchronous I/O on a Servlet worker thread.
        Thread.sleep(ms);
        System.out.println("HTTP_WORK_COMPLETE ms=" + ms);

        return Map.of("status", "done", "sleptMs", ms);
    }
}
~~~

**Runnability check:**
- A single Java source file has one `public class` matching the filename; `DemoHttpController` is a package-private top-level class scanned by Spring Boot component scanning in `demo.shutdown`.
- `@Bean` returns two `SmartLifecycle` instances with `getPhase()` values 200 and 100.
- `Long.getLong("demo.cleanup.ms", 1200L)` reads a **JVM system property** of type long, not a Spring `@ConfigurationProperties`. Change the delay at runtime with `-Ddemo.cleanup.ms=3500`.
- `running` uses `AtomicBoolean` to ensure visibility when start/stop callbacks run on different threads.
- `stop(Runnable)` invokes the callback in `finally`, so completion is not skipped if the thread is interrupted. Production needs stronger failure handling and state preservation.
- `System.out.println` is used for learning; real logs should include structured timestamps and phase names.
- `Thread.sleep` runs on an MVC Servlet thread. Do not copy this method as-is onto a WebFlux event loop.

### 8.3. application.yml configuration

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 8s
~~~

`server.shutdown: graceful` in Boot 3.5 merely **states the default explicitly**. `8s` is a parameter for the hands-on lab, not a recommendation for all servers.

### 8.4. Build/Run

At the project root:

~~~bash
./gradlew bootJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
~~~

When the artifact ID is `shutdown-phase-demo` with Initializr's default version, the jar is typically named:

~~~text
build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar
~~~

**Check the actual filename before running**, as it depends on build config. On Linux/macOS/WSL:

~~~bash
java -jar build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar
~~~

Running the Java process directly is cleaner than `bootRun` when sending SIGTERM to the exact **JVM PID**, avoiding confusion with the Gradle wrapper/daemon.

## 9. Testing HTTP graceful shutdown with an in-flight request

Open three terminals in a Linux/WSL/container environment:

**Terminal A:** run the Java process from section 8.4; watch startup logs.

**Terminal B:** start a 6s request:

~~~bash
curl -sS -i \
  "http://localhost:8080/api/slow?ms=6000"
~~~

**While Terminal B is still waiting**, use Terminal C to find the exact Java PID:

~~~bash
jps -lv
~~~

Send the signal:

~~~bash
kill -TERM 12345
~~~

`12345` is an **illustrative PID**; replace it with the actual JVM PID. Do not send signals to all Java processes on the machine.

### When the 8s grace is sufficient

If SIGTERM arrives right after the request starts and there is no major bottleneck, the HTTP request has a chance to complete:

~~~json
{"status":"done","sleptMs":6000}
~~~

JSON field order is not fixed; expected HTTP status is **200** when the request actually completes. Relevant logs may look like:

~~~text
HTTP_WORK_BEGIN ms=6000
... embedded web server graceful shutdown begins ...
HTTP_WORK_COMPLETE ms=6000
cache-flush STOP_BEGIN phase=200
cache-flush STOP_COMPLETE phase=200
consumer-stop STOP_BEGIN phase=100
consumer-stop STOP_COMPLETE phase=100
... application stops ...
~~~

Framework-emitted Boot lines vary in format and text by server/logging config. The two custom phases run in **200 → 100** order during shutdown; startup goes the opposite way **100 → 200**. If the client disconnects, a proxy times out, or the signal arrives near the end of grace, the response can differ. One successful demo run does not guarantee identical behavior under heavy load.

### New requests during shutdown

A new request sent right as graceful stop begins may receive connection refused/reset or a proxy error. **Do not write tests asserting only 503.** Boot 3.5 with Tomcat/Jetty/Reactor Netty stops accepting at the network layer; Undertow may return 503. Client retries must follow HTTP semantics and idempotency, avoiding blind auto-retries of critical POSTs when the first outcome is unknown.

### If using Windows

PowerShell `Stop-Process` generally uses a different termination path than POSIX SIGTERM; do not rely on it to verify graceful semantics. Use WSL/Linux or a container and send SIGTERM. On Docker, `docker stop` sends a stop signal to PID 1 and waits for the timeout; Java must receive the signal properly—if a shell wrapper swallows the signal, the graceful hook may not run.

## 10. Testing per-phase vs total shutdown duration separately

To distinguish per-phase timeout from total time:
1. Restart the app after each trial.
2. Send **no** slow requests, so the web graceful phase does not have to wait long.
3. Set phase timeout to **2s** and each custom cleanup to **1.2s**:

~~~bash
java -jar build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=2s
~~~

Send SIGTERM. Relevant custom logs:

~~~text
cache-flush STOP_BEGIN phase=200
cache-flush STOP_COMPLETE phase=200
consumer-stop STOP_BEGIN phase=100
consumer-stop STOP_COMPLETE phase=100
~~~

The two custom phases take roughly **1.2s + 1.2s = 2.4s**, already exceeding **2s** without violating the property because each phase has its own 2s budget.

**Do not compare process wall-clock against an exact 2,400ms**: framework phases, scheduling, IO flush, JVM overhead, and runtime variance exist. Observe phase ordering and callback completion instead.

### One cleanup intentionally taking longer than phase timeout

Restart with:

~~~bash
java -Ddemo.cleanup.ms=3500 \
  -jar build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=2s
~~~

After SIGTERM, each custom cleanup is expected to take **3.5s**, yet the processor only waits ~**2s for a single phase**. You may observe:
- The processor reports a phase timeout and moves to the next phase.
- `STOP_BEGIN phase=100` appears before phase 200 prints `STOP_COMPLETE`.
- Because the cleanup threads in the demo are **daemon**, the process may exit before they finish printing completion.
- There is no guarantee Spring called `Thread.interrupt()` on all threads right at second 2.

**Lesson takeaway:** phase timeout bounds the **wait time**, not guaranteed completion, cancellation, or durability. Do not model “accepting data loss” in production.

## 11. One phase with two beans: sharing the deadline

To verify, add a second phase-200 bean with an 800ms cleanup (fragment placed inside the demo class):

~~~java
@Bean
SmartLifecycle secondCacheFlusher() {
    return new DelayedStopBean("another-flush", 200, 800L);
}
~~~

This fragment goes inside the **class that already contains DelayedStopBean**, not a separate Java file. When stopping phase 200, the lifecycle processor calls stop on beans in that phase and waits for callbacks within **one time budget**. With a 2s phase timeout, `another-flush` finishes in 0.8s and `cache-flush` finishes in 1.2s, so the phase can complete in around 1.2s, **not summing each bean 0.8+1.2=2s** by default.

If one bean fails to call its callback, the phase may have to wait up to 2s even when the other bean is very fast. When dependencies exist or long synchronous stops occur, observe actual behavior rather than treating a simple max formula as an absolute guarantee.

### Do not “fix” things by setting every phase to 0

Putting all custom SmartLifecycle beans in the same phase makes them stop almost concurrently, which can cause:
- A resource closing before its dependent worker.
- A consumer still running while the publisher has closed.
- Trace/log exporters stopping while jobs still try to log.
- The DB pool closing before transactions flush.

Choose phases based on dependency ownership and stop sequence. Whenever possible, use framework-managed lifecycles for integration components; do not override phases recklessly.

## 12. Spring Boot task execution/scheduling has separate shutdown config

Alongside phase timeout, Boot offers:

~~~yaml
spring:
  task:
    execution:
      shutdown:
        await-termination: true
        await-termination-period: 10s
    scheduling:
      shutdown:
        await-termination: true
        await-termination-period: 10s
~~~

These properties control the behavior of **eligible auto-configured task execution/scheduling components**, not every `ExecutorService` you instantiate with `new`. Values are illustrative; defaults/behavior depend on executor type, version, virtual threads, and bean creation method.

A service with many queued tasks needs to separate:
- Stopping submission of new jobs.
- Waiting for small jobs that can finish before the deadline.
- Checkpointing jobs without enough time.
- Returning work to a durable queue/outbox for re-execution.
- Ensuring retries and redelivery do not duplicate side effects.

**Do not count “task submitted to Executor” as business work completed.** If the JVM is killed, in-memory queues are usually not durable. Shutdown timeouts only set a waiting budget, not exactly-once delivery.

### Custom executor

If the app writes:

~~~java
// Fragment: manually created executor, not fully managed by Boot.
ExecutorService executor = Executors.newFixedThreadPool(4);
~~~

it needs explicit lifecycle/bean destroy behavior or a Boot-managed Executor. Merely setting `spring.task.execution.shutdown.await-termination-period` does not automatically shut down/await every executor created anywhere.

## 13. Long requests and long-lived HTTP responses

HTTP graceful stop gives in-flight requests a chance to finish, but requests must be categorized:

| Workload | Risk on SIGTERM | Strategy |
|---|---|---|
| JSON GET 100ms | Usually completes within grace | Measure latency, bound request timeout |
| POST payment/order 5s | Client may lose response after DB commit | Idempotency key + operation status lookup |
| HTTP export 60s | Longer than phase budget | Async job + 202/operation ID/download later |
| Large file upload | Still receiving body when connector stops | Bounded upload/resumable protocol if needed |
| Infinite SSE | Request never completes naturally | App drain/complete stream + event replay |
| Hours-long WebSocket | Session pinned to one pod | Close 1001 when possible, reconnect/backoff/shared state |
| Long polling | Request waiting for an event | Controlled finish, client re-polls by cursor |
| HTTP/2 stream | Shares connection with multiple streams | GOAWAY/connection draining and per-stream semantics |

**Do not set hours-long grace periods to keep WebSockets alive during rolling deploys.** Application-level drain and client reconnect are needed. For SSE, `Last-Event-ID` only helps when the server has **durable event IDs and a replay implementation**; it does not turn an in-memory `Flux.interval` into a message log.

When a downstream side effect was applied yet the client never saw the response, the outcome is **ambiguous**. For non-idempotent POSTs, do not retry with a new operation ID after shutdown; reuse the same idempotency key or reconcile status.

## 14. Kubernetes deadline: one total budget, not per-phase

When a Pod is deleted/scaled in:

~~~text
Kubernetes marks Pod terminating
        |
        +-- Endpoint slices / LB routing gradually update
        +-- preStop hook (if declared)
        |       |
        |       +-- can consume several seconds of total grace
        |
        +-- SIGTERM to PID 1 process
        |       |
        |       +-- Boot graceful web phase
        |       +-- other SmartLifecycle phases
        |       +-- destroy callbacks
        |
        +-- JVM exits normally
        |
        +-- If terminationGracePeriodSeconds expires
                -> SIGKILL/force termination per runtime
~~~

**Propagation events and hooks can overlap**, with no guarantee of strict serialization across every network edge. Per Kubernetes docs, default `terminationGracePeriodSeconds` is typically **30s**. It counts for the **entire** termination process; `preStop` consumes part of it. If an app has:
- preStop = 10s;
- web phase wait = 20s;
- consumer phase = 10s;
- destroy overhead = 5s;
- Pod grace = 30s;

then the configuration has a **budget conflict**. Java can be killed before cleanup, regardless of whether Spring's property is 20s or 30s. Avoid thinking “10s preStop, and then Kubernetes gives Spring 30s more” if the total budget is only 30s.

### Suggested budget with margin

Planning example (not production defaults):

| Item | Planned budget |
|---|---:|
| pre-drain/LB propagation | 5s |
| HTTP graceful phase | 12s |
| Consumer phase | 8s |
| Flush phase | 6s |
| Destroy/executor overhead | 4s |
| Safety margin | 5s |
| **Total** | **40s** |

Assuming a 45s Pod grace gives a small cushion if the assumptions hold. Yet if the system has additional phases/GC pauses, it can still run longer. Size `terminationGracePeriodSeconds` from **measured maximum shutdown durations**, request latency SLOs, background queue drain rates, and infrastructure behavior.

**Do not hardcode per-phase=45s just because Pod grace=45s**: if preStop or multiple phases take close to 45s each, the platform will still kill it.

## 15. Readiness, liveness, and pre-drain

Spring Boot provides `ApplicationAvailability` and `ReadinessState`:
- `ACCEPTING_TRAFFIC`: app is ready for new workload.
- `REFUSING_TRAFFIC`: app should not be routed new requests.
- Liveness indicates whether the process is still healthy or needs a restart, **not a signal meaning “stop sending new requests”**.

When graceful shutdown begins, Boot can switch readiness to REFUSING_TRAFFIC and stop the HTTP connector from accepting new requests. However, the readiness probe may **fail to read HTTP 503** because the connector stopped accepting. For systems with LB propagation delay, design a **pre-drain before SIGTERM** when needed:
1. Transition the app to draining state / readiness false.
2. Reject new business intake, especially background jobs/handshakes.
3. Wait for LB/ingress endpoint propagation over a measured window.
4. Actively close long-lived streams/reject new subscriptions.
5. Send SIGTERM and let HTTP graceful + SmartLifecycle cleanup run.
6. Clients reconnect or job runners recover from durable state.

An availability event can be published from the control plane (fragment):

~~~java
// Fragment inside a bean holding ApplicationContext context:
AvailabilityChangeEvent.publish(
    context, ReadinessState.REFUSING_TRAFFIC);
~~~

Imports:
- `org.springframework.boot.availability.AvailabilityChangeEvent`
- `org.springframework.boot.availability.ReadinessState`
- `org.springframework.context.ApplicationContext`

**Do not open a public endpoint letting outsiders toggle draining freely.** If an admin endpoint exists, require authentication/authorization/mTLS or internal-only access. Changing readiness to false alone does not guarantee every Load Balancer stops sending traffic immediately; test propagation.

### Illustrative Kubernetes PodSpec

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: spring-api
      image: example/shutdown-demo:local
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: 8080
        periodSeconds: 2
        failureThreshold: 1
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: 8080
        periodSeconds: 5
        failureThreshold: 3
~~~

This is a **PodSpec fragment**, not a complete Deployment, and `example/shutdown-demo:local` is not a production image. You must add `spring-boot-starter-actuator`, enable probes properly if the environment does not auto-enable them, secure management endpoints, and configure readiness/liveness on the right server port.

### preStop sleep: what does it do and what does it not do?

~~~yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 5"]
~~~

This is only a container fragment. It **delays** the stop signal, potentially creating a window for endpoint propagation, yet:
- Does not emit `REFUSING_TRAFFIC` on its own.
- Does not stop consumers, websockets, or schedulers on its own.
- Does not guarantee every ingress updated within 5s.
- Deducts 5s from termination grace.
- Can slow rollouts if too many pods wait simultaneously.

A good preStop ties into rollout/capacity strategy and measurements rather than blindly copying numbers from internet snippets.

## 16. Docker PID 1 and signals reaching the JVM

A Docker container can use:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec-form makes Java PID 1. If using a shell wrapper, use `exec java -jar ...` so the shell hands over the process; do not run Java as a child of a shell that does not forward signals.

When the runtime sends `SIGTERM`:
- The JVM has a chance to run shutdown hooks/context close.
- If a wrapper swallows the signal, Spring does not receive the stop request properly.
- When platform grace expires, the runtime can use SIGKILL, bypassing cleanup.

**Do not use** `kill -9` or Windows `Stop-Process` as your primary test of graceful shutdown. They have different semantics and can terminate the process without running Spring cleanup.

## 17. Background workers: durability must be ensured before the deadline

A consumer:
1. Receives message “charge order 123”.
2. Starts a remote request.
3. JVM receives SIGTERM.
4. Remote API takes longer than remaining grace.
5. Process gets killed.

If the message was ACKed **before commit**, the message can be lost even though the payment did not complete. If un-ACKed, the broker can redeliver after restart, causing a duplicate without idempotency. Therefore:
- Stop intake before closing dependencies.
- Track in-flight operations.
- Enforce processing deadlines and bounded remote timeouts.
- Commit/ACK based on durable outcome, not immediately on message receipt.
- Use stable business operation IDs/idempotency keys.
- Use outboxes/queues/leases/checkpoints when jobs outlast shutdown grace.
- Provide status reconciliation for remote operations with ambiguous outcomes.
- Test crashes/hard kills, not just successful graceful stops.

`SmartLifecycle` stop callbacks indicate the component finished its stop protocol **per its implementation**, not an exactly-once certificate for distributed transactions.

## 18. Observing the effectiveness of per-phase timeout

A useful dashboard/logs can answer:
- Time drain/readiness false began.
- Time the JVM received SIGTERM.
- HTTP requests running at stop time, their durations, and route templates.
- When the HTTP graceful phase started/completed/timed out.
- `STOP_BEGIN`, callback completion, and timeout for each SmartLifecycle bean/phase.
- In-flight Kafka/Rabbit messages, executor queue depth, active DB transactions.
- Total shutdown duration and process exit code.
- Pod force-kill events, ingress 502/503s, client reconnect spikes.

Use **structured logs** with low-cardinality fields like `phase`, `component`, `outcome`, `durationMs`, `instance`. Do not put JWTs, cookies, raw personal IDs, or sensitive payloads in metric labels.

Some embedded server log text is emitted automatically depending on version/level. Do not assume an exact log string must appear in every Boot version. Use timestamps and your own markers to measure.

### Signs of insufficient budget

- Phase stop callback never prints `STOP_COMPLETE` before the process vanishes.
- Phase timeout or server graceful timeout logs appear.
- Kubernetes reports exit code 137/SIGKILL (distinguish OOMKill vs platform force-kill).
- HTTP clients get resets/partial responses during rollouts.
- Queued jobs jump after restart; active tasks were un-ACKed.
- New replicas suffer reconnect storms as thousands of clients disconnect at once.

Do not equate exit code 137 with a single cause; inspect `kubectl describe pod`, Events, `lastState.terminated.reason`, node/container memory, and the termination timeline.

## 19. Automated testing: controller tests vs signal integration tests

In a project with `spring-boot-starter-test`, create `src/test/java/demo/shutdown/ShutdownPhaseDemoApplicationTests.java`:

~~~java
package demo.shutdown;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ShutdownPhaseDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void fastRequestReturnsOk() throws Exception {
        mvc.perform(get("/api/fast"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void slowRequestCanFinish() throws Exception {
        mvc.perform(get("/api/slow").param("ms", "10"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sleptMs").value(10));
    }

    @Test
    void invalidSlowDurationIsRejected() throws Exception {
        mvc.perform(get("/api/slow").param("ms", "15001"))
            .andExpect(status().isBadRequest());
    }
}
~~~

This is a **complete Java 17/JUnit5 test file**, yet `@SpringBootTest`/MockMvc tests mainly verify HTTP handler behavior. They **do not prove** real process SIGTERM, network connector shutdown, or Kubernetes Pod termination.

Run:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Do not claim `BUILD SUCCESSFUL` without actually running it on the project; learners should build and verify in their own environment.

### What does a signal/termination integration test need?

Use a real process in Linux/WSL/container:
1. Start the jar and wait for `/api/fast` healthy.
2. Send a slow HTTP request.
3. Once inside the handler, send `SIGTERM` to the exact JVM.
4. With 8s grace and 6s work, expect a chance to complete with 200.
5. Change grace to 2s; observe incomplete request/failure without asserting a fixed HTTP status.
6. Add two beans in the same phase; test the shared phase deadline.
7. Omit a callback in one bean in an isolated test; observe phase timeout and logs.
8. Test `preStop`/`terminationGracePeriodSeconds` on a test Kubernetes cluster.
9. Run under CPU throttling/GC/slow downstream conditions.
10. Test `SIGKILL` separately to prove recovery when shutdown hooks do not run.

**Do not measure only with a mock server**, because MockMvc cannot fully reproduce signal-to-JVM, LB deregistration, container grace, and socket closure.

## 20. FAQ: major misconceptions

| Misconception | Reality |
|---|---|
| “30s property = entire JVM stops in at most 30s” | No; each SmartLifecycle phase gets a 30s wait budget |
| “With 3 beans in the same phase, each gets its own 30s” | No; they share the phase timeout |
| “Phase 100 stops before phase 200” | Opposite; shutdown runs high → low |
| “Skipping the callback is fine once the thread finishes” | Processor may wait until timeout because completion was not signaled |
| “Phase timeout expiry always interrupts threads” | Timeout only limits waiting, not hard-canceling all I/O/threads |
| “@PreDestroy gets cut off by this timeout property” | Not automatically; that is a separate bean destruction stage |
| “Boot 3.5 needs server.shutdown set to be graceful” | Graceful is already default in Boot 3.5; explicit declaration is allowed |
| “Every new request after SIGTERM returns 503” | Server/proxy may reject at network layer, with no fixed status |
| “Client sees reset => server rolled back the POST” | No, outcome may have committed; idempotency/status lookup needed |
| “TaskExecutor queue waits under HTTP grace” | Executor shutdown has its own configuration/mechanism |
| “PreStop finishes and only then does Pod start counting 30s” | PreStop consumes out of total terminationGracePeriodSeconds |
| “Setting Spring grace to 5 minutes makes Kubernetes wait 5 minutes” | Pod grace is independent and can kill earlier |
| “Graceful shutdown migrates WebSockets to a new pod” | No; clients reconnect and restore state |
| “SIGKILL is used to test graceful shutdown” | SIGKILL bypasses cleanup; use it to test crash recovery |
| “One successful local shutdown means production-safe” | Load/proxy/rollout tests, metrics, and durable recovery are required |

## 21. Production readiness checklist

- [ ] Checked the exact **Spring Boot version** and default HTTP graceful behavior.
- [ ] Configured `server.shutdown` and `spring.lifecycle.timeout-per-shutdown-phase` explicitly when needed.
- [ ] Each `SmartLifecycle` bean has a clear phase/dependency; startup and stop ordering make sense.
- [ ] `stop(Runnable)` invokes callback **after** actually finishing, handling error/rejection paths.
- [ ] No unbounded blocking I/O inside `stop()`, `@PreDestroy`, or network cleanup.
- [ ] New HTTP requests are blocked at the right moment; old requests wait within a measurable budget.
- [ ] Readiness/drain propagation is coordinated with LB/ingress.
- [ ] Pod `terminationGracePeriodSeconds` covers preStop + phases + destructors + margin.
- [ ] Container PID 1 or shell wrapper forwards SIGTERM to the JVM.
- [ ] Background executors/schedulers have separate shutdown policies.
- [ ] Message consumers stop intake and then ACK/commit/retry against durable state.
- [ ] Jobs outlasting grace have checkpoints/outbox/leases and idempotency.
- [ ] SSE/WebSocket have close/reconnect/backoff/replay; do not expect socket migration.
- [ ] Dashboards/logs track phase durations, active HTTP, queue lag, and forced kills.
- [ ] Tested 2s/8s/long request/long cleanup in a safe environment.
- [ ] Tested both graceful SIGTERM and hard-crash recovery separately.
- [ ] Avoided overly large per-phase timeouts that stall rolling deploys.
- [ ] Do not assume HTTP 200 completion means all background work is durable.

## 22. Review questions

**1.** Does `spring.lifecycle.timeout-per-shutdown-phase=20s` limit the entire JVM shutdown to 20s?

**Answer:** No. It is the wait limit **per SmartLifecycle phase**, not a hard global deadline.

**2.** Two beans in phase 200 take 1s and 7s, per-phase timeout is 10s. Does Spring wait a total of 8s?

**Answer:** Not necessarily. If async stops run concurrently, the group typically finishes after the slowest bean (~7s) under one shared 10s deadline.

**3.** On shutdown, does phase 100 or 200 run first?

**Answer:** Phase **200** stops first, phase **100** stops later (startup goes in the reverse direction).

**4.** What happens if a bean forgets `callback.run()`?

**Answer:** The processor may wait out the phase timeout and report non-completion, even if the actual stop work finished.

**5.** If `@PreDestroy` takes 60s, does `timeout-per-shutdown-phase=10s` automatically interrupt it?

**Answer:** Not by default. That timeout's scope is SmartLifecycle phase waits.

**6.** Why can Pod grace=30s still result in SIGKILL when Spring phase timeout=60s?

**Answer:** Kubernetes has its own overall deadline; once Pod grace expires, it can force-kill the JVM before Spring finishes waiting.

**7.** Does Boot 3.5 need graceful HTTP server enabled explicitly?

**Answer:** Graceful is the default per Boot 3.5 docs for supported embedded servers; `server.shutdown=graceful` may still be written explicitly for clarity.

**8.** Are new requests during the graceful phase guaranteed to get HTTP 503?

**Answer:** No. Tomcat/Jetty/Reactor Netty may reject at the network layer; Undertow may return 503; proxies may differ.

**9.** If a POST request loses its response while the Pod stops, is retrying with a new key safe?

**Answer:** No. The server may have committed. A stable idempotency key and status reconciliation are needed.

**10.** Does a cleanup thread still running after the phase timeout mean the property has no effect?

**Answer:** No. The property bounds **how long the processor waits**; it does not force-interrupt threads.

**11.** Why keep readiness false while keeping liveness true during drain?

**Answer:** To stop receiving new traffic while the process is still healthy and needs time to finish work; false liveness triggers premature restarts.

**12.** Should timeout be raised to 10 minutes just because an SSE stream can live for 1 hour?

**Answer:** No. Streaming needs deliberate close/reconnect and replay rather than making Pods wait for unbounded connections.

**13.** Does `spring.task.execution.shutdown.await-termination-period` replace the lifecycle phase timeout?

**Answer:** No. It bounds waiting on the corresponding task executor and is one piece of the overall shutdown design.

**14.** Do passing MockMvc tests prove graceful shutdown works behind an ALB?

**Answer:** No. You need signal tests on a real process and traffic routed through a real LB/ingress.

**15.** If orders must not be lost on a hard kill, what matters most?

**Answer:** Durable transactions/queues/outbox, idempotency, and recovery. Graceful timeouts reduce disruption but do not protect when cleanup cannot run.

### Extension exercises

Starting from the demo:
1. Run a 6s slow request and send SIGTERM with per-phase=8s; record the response/stop timeline.
2. Change per-phase=2s, run a 6s slow request, and observe the failure path without asserting 503.
3. Set custom phase delays=1.2s with phase limit=2s, proving total phase work can exceed 2s.
4. Set system property `-Ddemo.cleanup.ms=3500` when phase=2s and see which callback arrives late.
5. Add a second phase-200 bean; measure the shared group deadline and lifecycle ordering.
6. Add a `@PreDestroy` with sleep in an **isolated test** and observe why it is not cut off by the phase timeout.
7. Measure preStop, readiness transition, and Pod termination on a test cluster; calculate headroom.
8. Add a simulated queue consumer with a pending operation ID and verify recovery after SIGKILL.

## 23. Official documentation

- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework 6.2 — Bean Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Spring Framework — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
- [Spring Framework — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Boot 3.5 — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 — Actuator Kubernetes Liveness/Readiness](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
- [Dockerfile ENTRYPOINT exec form](https://docs.docker.com/reference/dockerfile/#entrypoint)
- [RFC 9110 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)

**Conclusion:** `spring.lifecycle.timeout-per-shutdown-phase` is a wait budget **per SmartLifecycle phase group**, not total process time or universal cancellation. Safe shutdown requires synchronizing **readiness → traffic drain → HTTP graceful phase → worker/consumer phase callbacks → destroy/executor cleanup → Pod termination deadline**, along with durable recovery for any work that cannot complete on time.
