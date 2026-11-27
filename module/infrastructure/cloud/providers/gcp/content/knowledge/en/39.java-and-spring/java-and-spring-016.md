# Graceful Shutdown and Handling Container Termination Signals

A Java/Spring application may be right in the middle of serving an HTTP request, writing data, acknowledging a message, or flushing logs to monitoring when the platform decides to replace the container. If the process terminates abruptly, requests fail mid-flight, transactions remain incomplete, messages get reprocessed unnecessarily, or buffered data never reaches durable storage.

**Graceful shutdown** is the process of stopping new work intake, giving in-flight work a bounded window to finish, releasing resources, and exiting cleanly. This lesson belongs to the **Java and Spring on GCP** chapter in the **CLOUD_PROVIDERS_GCP** module. It helps operate Spring Boot on Cloud Run, Google Kubernetes Engine (GKE), and containerized environments while tying into resource protection, release automation, reliability monitoring, and cost management on Google Cloud.

After this lesson, you will be able to:

- Explain the roles of `SIGTERM`, `SIGKILL`, PID 1, and shutdown hooks inside containers.
- Distinguish shutdown limits on Cloud Run versus GKE.
- Configure Spring Boot to drain in-flight requests and clean up resources.
- Design suitable readiness probes, `preStop` hooks, and termination grace periods.
- Ensure background jobs, consumers, transactions, and telemetry exporters can be interrupted safely.
- Test, observe, and troubleshoot shutdown errors during deployments or scale-downs.

## 1. Why Are Containers Terminated?

Containers do not run forever. Common termination scenarios include:

| Scenario | Google Cloud example | Risk if stopped abruptly |
|---|---|---|
| New version rollout | Rolling update of a GKE Deployment; Cloud Run revision swap | Unanswered requests, dropped connections |
| Autoscaling | GKE scales down Pods; Cloud Run reclaims idle instances | Background work left incomplete |
| Maintenance or node replacement | GKE drains workloads, upgrades node pools | Connections, leases, or locks unreleased |
| Configuration changes | Updating env vars, images, or resources | In-progress records left uncommitted |
| Manual stop | `docker stop`, Pod deletion, job cancellation | Process killed before flushing |
| Failure or crash | OOM, unreachable node, forced `SIGKILL` | Zero opportunity to run cleanup |

Graceful shutdown matters especially during planned stops. However, processes do not always receive a graceful signal. On node failures, container OOMs, or forced kills, cleanup will not run. Therefore, **idempotency, transactions, and retry/checkpoint mechanisms remain mandatory** for critical work.

## 2. Understanding SIGTERM, SIGKILL, and PID 1

On Linux, container platforms send signals to request process termination:

- **`SIGTERM` (15):** catchable termination request. The JVM initiates its shutdown sequence and runs shutdown hooks.
- **`SIGKILL` (9):** forced termination that cannot be caught or ignored. Java has zero guarantee of running `finally`, `@PreDestroy`, or shutdown hooks.
- **`SIGINT` (2):** typically sent via Ctrl+C in a terminal; can also trigger shutdown, though it is not the default signal used by container platforms.

In containers, signals are delivered to the primary process—usually **PID 1**. If PID 1 is a shell and Java runs as a child process, the shell may fail to forward `SIGTERM` to Java. The application gets no chance to clean up before being forcefully killed.

~~~mermaid
sequenceDiagram
    participant P as Container platform
    participant J as JVM / Spring Boot
    participant W as Workload
    P->>J: SIGTERM
    J->>W: Stop accepting new work
    W-->>J: Finish in-flight work
    J->>J: Close ApplicationContext, cleanup
    alt Exits within deadline
        J-->>P: Process exit
    else Exceeds deadline
        P->>J: SIGKILL
        Note over J: Remaining cleanup does not run
    end
~~~

### Dockerfile: Ensuring Java Receives Signals

Prefer **exec form** for `ENTRYPOINT`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/checkout-api.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Here, Java runs as PID 1 in the container. When the platform sends `SIGTERM`, the JVM receives it directly. Depending on the environment, an init process such as `tini` can forward signals and reap zombie processes if the app spawns child processes.

Be cautious with shell form:

~~~dockerfile
# Not recommended: shell may hold PID 1 and fail to forward SIGTERM
ENTRYPOINT java -jar /app/app.jar
~~~

If a startup script is required, its final line should use `exec java -jar /app/app.jar` to replace the shell with the JVM. Do not merely add `trap` in a shell script while neglecting signal forwarding and child process waiting.

### Do the JVM and Spring Need Custom SIGTERM Handlers?

Normally **you do not need to register custom signal handlers using internal JDK APIs**. When the JVM receives `SIGTERM`, normal shutdown runs registered JVM shutdown hooks. Spring Boot registers a hook to close `ApplicationContext`, triggering Spring lifecycles, graceful web-server shutdown, and bean destroy callbacks.

Registering multiple competing hooks or calling `System.exit(...)` inside a hook risks race conditions, deadlocks, or exiting before cleanup finishes. Write custom signal logic only when an app has specialized requirements and you fully understand the JVM lifecycle.

## 3. Desired Shutdown Order

A controlled shutdown sequence typically follows:

1. **Stop new intake:** service stops accepting new requests or consumers stop pulling messages.
2. **Draining:** allow in-flight requests a bounded interval to finish.
3. **Commit or checkpoint:** commit transactions, persist recoverable state, and ack only after durable completion.
4. **Close resources:** connection pools, HTTP clients, schedulers, executors, and telemetry exporters.
5. **Exit process:** return an appropriate exit code before the platform deadline.

~~~mermaid
flowchart TD
    A["SIGTERM / stop request"] --> B["Reject new work"]
    B --> C["Drain in-flight requests and background tasks"]
    C --> D{"Finished before deadline?"}
    D -->|Yes| E["Commit / ack / flush and close resources"]
    D -->|No| F["Checkpoint or leave unfinished work for retry"]
    E --> G["JVM exit"]
    F --> G
    G --> H["Platform reclaims container"]
~~~

An application must never wait forever for every request to finish. The platform enforces a hard deadline; waiting indefinitely just triggers `SIGKILL`. Choose a drain duration suited to your workload while reserving budget for other lifecycle phases.

## 4. Differences Between Cloud Run and GKE

| Aspect | Cloud Run services | GKE / Kubernetes Pods |
|---|---|---|
| Normal stop signal | `SIGTERM` sent to containers in the instance | Kubelet tells the runtime to send `TERM` to containers |
| Time before forced kill | 10 seconds after `SIGTERM`, then `SIGKILL` | Default 30 seconds; configurable via `terminationGracePeriodSeconds` |
| Adjustable grace period | No custom Pod termination grace period for services | Can be raised/lowered in the Pod spec |
| Traffic shifting | Platform routes requests; may stop an instance mid-request in edge cases | `EndpointSlice` marks endpoint terminating, readiness false, Service/LB drains |
| `preStop` hook | Does not use Kubernetes Pod lifecycle hooks | Supports `preStop`; hook duration counts inside grace period |
| Readiness setup | Startup/liveness and routing managed by Cloud Run | Readiness/liveness/startup probes declared in Pod spec |
| Active testing | Local `docker stop`; inspect logs during revision swaps/scale-downs | Rolling updates, deleting Pods in staging, watching events |

**Cloud Run:** the current runtime contract states that Cloud Run sends `SIGTERM` to all containers in an instance roughly 10 seconds before `SIGKILL`. CPU remains allocated and billed during this period. Normally, in-flight requests are allowed to finish before instance reclamation; exceptional cases may still receive `SIGTERM` while requests are active. Never promise that long requests always get a full extra 10 seconds. In first-generation execution environments, containers not trapping `SIGTERM` may exit immediately; in second-generation environments, ensure processes handle signals properly.

**GKE:** kubelet triggers termination when a Pod is deleted or replaced. `terminationGracePeriodSeconds` defaults to 30. If `preStop` is configured, it runs before `TERM` and **shares** this same grace period; once expired, surviving containers receive `SIGKILL`. A Pod entering `Terminating` or reporting readiness false does not mean every proxy or load balancer stops routing instantaneously.

### Distinguishing Cloud Run Services, Jobs, and Worker Pools

Cloud Run **services** handle HTTP/gRPC requests. Cloud Run **jobs** run finite tasks; when a task hits its timeout or is cancelled, it receives `SIGTERM` with roughly 10 seconds before `SIGKILL`. For jobs, write periodic checkpoints and design for retries rather than expecting to flush all work in the final 10 seconds.

Cloud Run **worker pools** have their own lifecycle and do not auto-scale to zero on idle like services. When a worker pool instance shuts down, it also receives `SIGTERM` and roughly 10 seconds before `SIGKILL`. Message processors must stop polling and let the broker handle redelivery of unfinished work.

## 5. Configuring Graceful Shutdown in Spring Boot

Spring Boot supports graceful shutdown for embedded web servers in both Servlet and reactive apps. In newer Spring Boot versions, graceful shutdown may be enabled by default; older versions require enabling it explicitly. To keep configuration explicit across upgrades, declare:

**application.yml**

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 8s
~~~

Equivalent **application.properties**:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s
~~~

`spring.lifecycle.timeout-per-shutdown-phase` caps **each phase** of `SmartLifecycle`; it is not a global cap across the entire container shutdown. If multiple phases or bean cleanups run sequentially, total duration can exceed that value. On Cloud Run, pick an internal budget shorter than 10 seconds and measure real shutdown duration; the 8-second value above is only an example to tune per app.

When `ApplicationContext` closes, the web server stops accepting new requests and waits up to the timeout for active requests. On Tomcat, Jetty, and Reactor Netty, stopping intake happens at the network layer; some other servers/versions may return errors for new requests. Keep-alive connections, streaming responses, SSE, and WebSockets require separate testing because long-lived connections may not finish before the deadline.

Web server graceful shutdown does not guarantee background tasks finish automatically. Manage application-created background components explicitly.

### Choosing Timeouts by Environment

Reference examples:

| Environment | Platform grace period | Suggested Spring setting | Notes |
|---|---|---|---|
| Cloud Run service | 10 seconds | `timeout-per-shutdown-phase: 6s` | Leaves headroom for cleanup/flush; unsuitable for very long requests |
| GKE deployment | 45 seconds (configured) | `timeout-per-shutdown-phase: 25s` | With a 5s `preStop`, leaves room for other phases |
| Local Docker | Set via `docker stop -t` | 8–20 seconds per test | Set Docker timeout larger than total cleanup time |
| Cloud Run job | ~10s after `SIGTERM` on cancel/timeout | Fast shutdown, checkpoint earlier | Retries and idempotency are the primary safeguards |

These numbers are illustrative. When workloads change, evaluate p95/p99 latency, request timeouts, commit durations, consumer stop times, and flush lag to pick realistic budgets.

## 6. Cleaning Up Resources with @PreDestroy

Spring calls bean destruction callbacks when `ApplicationContext` closes orderly. In modern Spring Boot using Jakarta namespaces, implement:

~~~java
package com.example.checkout;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ShutdownCleanup {
    private static final Logger log =
        LoggerFactory.getLogger(ShutdownCleanup.class);

    @PreDestroy
    public void close() {
        long started = System.nanoTime();
        log.info("shutdown_cleanup_start");

        // Example: close a resource owned by this bean.
        // Do not start long-running work or wait indefinitely here.
        // Many Spring-managed resources already handle their own lifecycle.

        long elapsedMs =
            (System.nanoTime() - started) / 1_000_000L;
        log.info("shutdown_cleanup_complete duration_ms={}", elapsedMs);
    }
}
~~~

When beans already configure automatic destroy methods (HikariCP, Kafka listener containers, Spring-managed executors), do not manually close them a second time. `@PreDestroy` fits brief cleanup of application-owned resources—closing custom clients, flushing small buffers, or releasing timed locks.

Notes:

- Never place mandatory business logic inside `@PreDestroy`: `SIGKILL`, OOMs, or node failures bypass callbacks.
- Never wait indefinitely, sleep for seconds, or make unbounded network calls.
- Make cleanup **idempotent** so repeated calls cause no errors and handle partially closed resources.
- If maintaining Spring Boot 2 with legacy namespaces, the annotation may be `javax.annotation.PreDestroy`; the example above uses `jakarta.annotation.PreDestroy` for modern Spring releases.
- When phased start/stop coordination across components is required, prefer `SmartLifecycle` over stuffing everything into one destroy callback.

## 7. Managing Background Workers with SmartLifecycle

Suppose an application uses a dedicated `ExecutorService` for short tasks dispatched by HTTP handlers. On shutdown, it must stop accepting new tasks, await running tasks for a bounded time, and terminate cleanly.

Simple example adaptable to real needs:

~~~java
package com.example.checkout;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class BackgroundWork implements SmartLifecycle {
    private final ExecutorService executor =
        Executors.newFixedThreadPool(2);

    private final AtomicBoolean accepting = new AtomicBoolean(false);

    public boolean submit(Runnable work) {
        if (!accepting.get()) {
            return false;
        }
        try {
            executor.submit(work);
            return true;
        } catch (RejectedExecutionException rejected) {
            return false;
        }
    }

    @Override
    public void start() {
        accepting.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        accepting.set(false);
        executor.shutdown();
        try {
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> {});
    }

    @Override
    public boolean isRunning() {
        return accepting.get();
    }
}
~~~

Key takeaways:

- `SmartLifecycle` lets Spring orchestrate component shutdown by lifecycle phase; `callback.run()` signals the component has stopped or finished attempting to stop.
- Reject new submissions **before** calling `shutdown()` and handle races via `RejectedExecutionException`.
- `shutdown()` awaits queued tasks; `shutdownNow()` only attempts interrupts and cannot forcibly unblock uninterruptible I/O.
- This example assumes a one-shot lifecycle (start once, stop on exit). If restartable within the same `ApplicationContext`, re-create the executor on `start()`.
- Never treat an in-memory executor as the sole durable store for critical tasks. If the JVM dies before persistence, tasks vanish. Use Cloud Tasks, Pub/Sub, an ack/redelivery broker, or an outbox table when durability is required.

For apps using `@Async` or `@Scheduled`, verify shutdown wait settings on the backing task executor/scheduler; do not assume every task is awaited by default. For Kafka, RabbitMQ, or Pub/Sub, rely on the listener/client library's lifecycle to stop polling, commit/ack properly, and close connections cleanly.

## 8. Transactions, Messages, and Long Tasks During Shutdown

Consider a consumer processing order messages:

1. Receive message from Pub/Sub.
2. Write order state to the database inside a transaction.
3. Commit successfully.
4. Only then ack the message.

If `SIGTERM` arrives before commit, the consumer should stop pulling new messages; for the in-flight message, either finish within the remaining grace period or let the broker redeliver. **Never ack before data is durably persisted.**

Because messages may be reprocessed, handlers must be idempotent by message ID or business key. Use unique constraints, state machines, or outbox/inbox patterns—never rely solely on an in-memory boolean.

| Work type | Shutdown handling | Avoid |
|---|---|---|
| HTTP request mutating data | Finish transaction within deadline; return clear status | Partial writes followed by success |
| Pub/Sub subscriber | Stop pulling; ack after commit; allow redelivery if incomplete | Acking immediately on receipt |
| Kafka consumer | Stop polling; commit offsets matching durable progress; close consumer | Committing offsets for unprocessed records |
| Scheduled task | Stop launching new runs; checkpoint unfinished work | Relying solely on in-RAM threads |
| Large upload or long stream | Offload to object storage, resumable uploads, chunks/checkpoints | Holding requests open for minutes expecting a 10s cleanup |
| Telemetry/log exporter | Bounded flush; prefer async background shipping during execution | Holding all logs until shutdown |

On Cloud Run services, background threads are not guaranteed CPU when no requests are active, depending on billing/CPU allocation. Move durable long-running work to Cloud Tasks or Cloud Run jobs with checkpoints, retries, and explicit task IDs.

## 9. GKE: Readiness, preStop, and Termination Timing

Kubernetes marks terminating Pod endpoints `ready=false`, yet proxy or load balancer propagation lag can briefly route new connections to the old Pod. Applications must coordinate readiness, termination grace periods, and shutdown logic.

Spring Boot Actuator probes:

- `/actuator/health/liveness` reflects process liveness.
- `/actuator/health/readiness` reflects readiness to accept traffic.
- Enabling `management.endpoint.health.probes.add-additional-paths=true` exposes `/livez` and `/readyz` on the main application HTTP port, avoiding probing a separate management port that might remain up after the primary web server closes.

Example configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

The app requires the `spring-boot-starter-actuator` dependency. When Spring begins graceful shutdown, `ReadinessState` transitions to `REFUSING_TRAFFIC`. Once the HTTP connector closes, probes stop answering HTTP; Kubernetes also marks the Pod terminating independently of probes. Readiness probes alone do not guarantee all traffic ceases instantaneously.

### Example Deployment for GKE

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: checkout-api
          image: asia-southeast1-docker.pkg.dev/example-project/apps/checkout-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

Here, the total grace period is **45 seconds**, covering the 5-second `preStop` sleep plus Spring shutdown. A `preStop` sleep is an optional buffer when routing updates need propagation time; it is neither the only option nor always necessary. If using a distroless image lacking `/bin/sh` or `sleep`, this hook fails—omit it or use an image-compatible mechanism.

Never set `preStop` to 40 seconds inside a 45-second grace period expecting Spring to get a separate 25 seconds to drain. Kubernetes starts the timer when termination begins. If hooks have not finished when the grace period expires, kubelet grants at most a brief ~2-second extension before killing the container.

For high-availability systems, combine rolling updates, at least two replicas where appropriate, `PodDisruptionBudget`, and realistic readiness probes. PDBs limit voluntary disruptions, yet they do not replace graceful shutdown or prevent unexpected node failures.

## 10. Cloud Run: Optimizing for the 10-Second Limit

On Cloud Run services, the post-`SIGTERM` deadline is roughly 10 seconds and cannot be extended via `spring.lifecycle.timeout-per-shutdown-phase`. Spring's shutdown budget must fit under the platform limit.

A Cloud Run profile might configure:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 6s
~~~

This leaves room for cleanup callbacks, though sequential phases, hung database queries, or long streaming requests can still hit `SIGKILL`. Therefore:

- Set explicit timeouts on database, HTTP client, and messaging calls.
- Avoid external network calls without timeouts inside `@PreDestroy`.
- Never launch new background tasks after receiving a stop signal.
- Log concise start and completion events during shutdown; avoid flushing massive telemetry batches.
- Rely on external retries/checkpoints for critical work.
- Test during new revision rollouts, traffic shifts, and instance reclamation.

**Request timeout is not shutdown timeout.** Configuring Cloud Run to allow requests longer than 10 seconds does not grant Spring that extra duration after `SIGTERM`. Cloud Run normally lets in-flight requests finish before reclaiming an instance, though exceptions and abrupt interruptions still occur.

Cloud Run jobs also have a short post-`SIGTERM` window upon timeout or cancellation, even when the task timeout is much longer. For large jobs, periodic checkpointing is primary; shutdown flushing is purely supplemental.

## 11. Testing Graceful Shutdown Locally

Use a test environment to measure real behavior. You can add a test endpoint with artificial latency to observe in-flight requests:

~~~java
package com.example.checkout;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ShutdownDemoController {
    @GetMapping("/demo/slow")
    String slow() throws InterruptedException {
        Thread.sleep(3000);
        return "completed";
    }
}
~~~

This endpoint is for testing only—never expose it in a public production API.

Build and run the image:

~~~bash
docker build -t checkout-graceful:local .
docker run -d --name checkout-graceful -p 8080:8080 checkout-graceful:local
~~~

In one terminal, send a ~3-second request:

~~~bash
curl -v http://localhost:8080/demo/slow
~~~

Immediately after starting the request, run in another terminal:

~~~bash
docker stop --time 15 checkout-graceful
docker logs checkout-graceful
docker inspect checkout-graceful --format "{{.State.ExitCode}}"
~~~

Expected result: the JVM receives `SIGTERM`, Spring stops accepting new requests, the in-flight request completes, and cleanup logs appear before the container exits. Stopping an idle container separately measures pure cleanup duration.

Test with `docker stop --time 2` to simulate an overly tight deadline. Here `SIGKILL` hits before Spring finishes, demonstrating why cleanup callbacks are never guaranteed to run to completion.

Note that Docker's `docker stop` timeout differs from Cloud Run's fixed deadline and Kubernetes `terminationGracePeriodSeconds`.

## 12. Testing on GKE and Cloud Run

### On GKE Staging

1. Deploy multiple replicas with readiness probes and graceful shutdown configured.
2. Generate mixed load containing fast and slow requests; record 5xx counts, latency, and in-flight counts.
3. Trigger a rolling restart of the Deployment in the `staging` namespace.
4. Watch Pod transitions, `EndpointSlice` updates, and logs of terminating containers.
5. Verify in-flight requests are not dropped beyond acceptable thresholds, no messages are lost, and no invalid states are committed.

Example commands:

~~~bash
kubectl -n staging rollout restart deployment/checkout-api
kubectl -n staging rollout status deployment/checkout-api
kubectl -n staging get pods -l app=checkout-api -w
~~~

While a Pod still exists:

~~~bash
kubectl -n staging describe pod POD_NAME
kubectl -n staging logs POD_NAME -c checkout-api --timestamps
~~~

Once Pods are deleted, logs remain only in Cloud Logging depending on collection and retention settings. Query Cloud Logging by Pod, container, or trace ID for post-rollout audits. Never run Pod deletion tests in production without an approved change plan.

### On Cloud Run Staging

Cloud Run decides when to reclaim instances, so no command guarantees a specific instance receives `SIGTERM` immediately. Use `docker stop` locally to verify signal handling, then deploy a test revision, shift traffic or trigger scale-down, and inspect shutdown logs when instances actually terminate.

Verify `java` runs as PID 1, timeouts fit cleanly, and callbacks finish well within 10 seconds. Do not assume a single deploy immediately emits `SIGTERM` to conclude whether shutdown works.

## 13. Logging, Metrics, and Failure Signals

Emit structured logs to trace shutdown phases:

~~~text
event=shutdown_started service=checkout-api revision=abc123
event=drain_completed active_requests=0 elapsed_ms=1850
event=shutdown_cleanup_complete duration_ms=120
~~~

Key signals to monitor:

- **Shutdown duration:** elapsed time from stop signal to process exit.
- **Request failures:** 5xx responses, connection resets, or gRPC `CANCELLED`/`UNAVAILABLE` during rollouts.
- **In-flight requests:** active requests at drain start and drain completion.
- **Pod events / restart reasons:** `Terminating`, `OOMKilled`, `Error`, or kill signals.
- **Work queues:** in-progress tasks, ack/commit timeouts, retries, and dead-letter counts.
- **Dependency cleanup:** active pool connections, running executors, slow telemetry flushes.
- **SLOs:** rollout impact on availability and latency.

In Cloud Logging, filter by service, revision, and shutdown messages. On GKE, correlate Kubernetes events with container stdout/stderr. Not every `SIGKILL`ed process gets to flush a final log line; missing log lines are themselves diagnostic clues.

### Common Exit Codes

| Exit code / signal | Typical interpretation | What to check |
|---|---|---|
| `0` | Clean exit | Cleanup succeeded, job completed |
| `143` (128+15) | Some shells/runtimes report exit due to `SIGTERM` | Confirm signal receipt; do not assume an error from 143 alone |
| `137` (128+9) | Usually `SIGKILL`; may indicate OOM or exceeded grace period | Check container termination reason, memory, events/logs |
| `1` or other non-zero | Application error | Exceptions, startup/shutdown stack traces, and events |

Exit codes depend on the process and runtime; never diagnose root cause from an exit code alone. For OOM kills, inspect `OOMKilled` and memory metrics.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Running Java via shell form in Dockerfile | JVM does not receive `SIGTERM` directly | Use exec form or `exec` in launcher scripts |
| Setting a 30s Spring timeout on Cloud Run | Container killed around 10 seconds | Streamline cleanup, keep shutdown short, checkpoint early |
| Assuming `@PreDestroy` always runs | Data loss on OOM, `SIGKILL`, or node failure | Idempotency, transactions, retries, durable queues |
| Setting readiness only without draining in-flight | Active requests severed on Pod termination | Combine draining, Spring graceful shutdown, and grace periods |
| `preStop` sleep consuming the whole grace period | Spring has no time left to shut down | Budget `preStop` + lifecycle phases + cleanup together |
| Acking Pub/Sub or Kafka before DB commit | Lost messages or inconsistent state | Ack/commit only after durable persistence |
| Making unbounded network calls in callbacks | Hit by `SIGKILL` before logs/cleanup finish | Enforce network and cleanup timeouts |
| Shutting down consumers while accepting new HTTP work | New work rejected or dropped | Stop intake first, drain with a deadline |
| Installing custom signal handlers calling `System.exit` | Hook races or deadlocks | Rely on JVM and Spring lifecycles |
| Testing shutdown only on idle containers | Misses connection resets during rollouts | Test under active load with slow requests |

## 15. Pre-Release Checklist

- [ ] Dockerfile uses exec form or `exec` in launcher scripts so Java receives `SIGTERM`.
- [ ] Spring Boot declares `server.shutdown=graceful` and appropriate timeouts.
- [ ] Measured total shutdown time fits comfortably below platform limits.
- [ ] GKE deployments configure appropriate readiness and liveness probes.
- [ ] `terminationGracePeriodSeconds` on GKE accounts for `preStop` plus Spring phases.
- [ ] Background workers and consumers stop intake and drain with bounded timeouts.
- [ ] Transactions, acks, retries, and idempotency handle sudden kills safely.
- [ ] Cleanup enforces timeouts and never assumes `@PreDestroy` always runs.
- [ ] Long requests, streaming, WebSockets, and batch tasks have explicit interruption strategies.
- [ ] Local `docker stop` tests and staging rollout tests have been executed.
- [ ] Shutdown logs and metrics verify rollout behavior in production.
- [ ] Plans exist for rollback, load shedding, and recovering interrupted work.

## 16. Self-Check Questions

1. Why must Java run as PID 1 or receive `SIGTERM` forwarded from PID 1?
2. What is the fundamental difference between `SIGTERM` and `SIGKILL`?
3. Does setting `spring.lifecycle.timeout-per-shutdown-phase=20s` give a Cloud Run container 20 seconds after `SIGTERM`?
4. On GKE, with a 10-second `preStop` and 30-second termination grace period, how much time remains at most for remaining shutdown steps?
5. Why does readiness turning false not guarantee every connection switches immediately to a new Pod?
6. When a Pub/Sub subscriber receives `SIGTERM` mid-transaction, when should the message be acked?
7. Why is `@PreDestroy` insufficient by itself to guarantee no critical work is lost?
8. How do you test graceful shutdown while an application is serving a slow request?

**Answer Key**

1. Container signals go to PID 1; if a shell fails to forward signals, the JVM never receives the shutdown request.
2. `SIGTERM` lets the process shut down and run cleanup, whereas `SIGKILL` terminates immediately without running callbacks.
3. No. Cloud Run still enforces roughly 10 seconds before `SIGKILL`; Spring's timeout only caps internal phase waiting.
4. Roughly 20 seconds (minus overhead and routing lag), because `preStop` shares the grace period.
5. Endpoints and proxies/load balancers update asynchronously; existing connections may continue briefly.
6. Only after the transaction commits successfully; if unfinished, allow redelivery and handle idempotently.
7. Shutdown hooks do not run on `SIGKILL`, OOM, or node crashes; durable storage, retries, and idempotency are essential.
8. Send a slow request, trigger `SIGTERM` via `docker stop` or a staging rolling update, and check responses, logs, drain time, and errors.

## References

- [Google Cloud: Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Google Cloud: Cloud Run execution environments and SIGTERM](https://docs.cloud.google.com/run/docs/configuring/execution-environments)
- [Google Cloud: Cloud Run service billing and background work](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [Google Cloud: Cloud Run jobs task timeouts](https://docs.cloud.google.com/run/docs/configuring/task-timeout)
- [Kubernetes: Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes: Container lifecycle hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
- [Spring Boot: Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot: Actuator Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Framework: Bean destruction and @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Docker: Dockerfile ENTRYPOINT exec and shell forms](https://docs.docker.com/reference/dockerfile/)
