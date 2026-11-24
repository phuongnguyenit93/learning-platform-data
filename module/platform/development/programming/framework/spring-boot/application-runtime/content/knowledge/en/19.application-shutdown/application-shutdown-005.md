# Graceful Shutdown vs. Immediate Shutdown in Spring Boot

## 1. Why Must We Distinguish Shutdown Approaches?

A Spring Boot application may be serving HTTP requests, writing to a database, sending messages, running `@Scheduled` jobs, or processing `@Async` tasks when asked to terminate. If the process is cut off before work reaches a commit boundary, clients may see errors, messages may be reprocessed or lose transient state, and connections/resources may not be cleanly released.

**Graceful shutdown** is a coordinated shutdown: stop accepting new work, give in-flight work a chance to finish within a bounded time budget, then close resources and terminate the process. **Immediate server shutdown** disables waiting for in-flight HTTP requests when closing the web server; it is **not** a forced kill of the entire JVM. Meanwhile, `SIGKILL` is forced termination at the OS/container level and gives Java no chance to continue the normal shutdown path.

In Spring Boot **3.5.x**, graceful shutdown is the default configuration for **Tomcat, Jetty, Undertow, and Reactor Netty**, for both servlet and reactive web applications. Spring Boot performs graceful shutdown as part of closing the `ApplicationContext`, during an early stop phase of `SmartLifecycle` beans.

Questions to answer during design:
- How are new requests handled during shutdown?
- Do running requests and jobs get a chance to complete?
- In what order do beans, executors, schedulers, and database connections close?
- How does Spring's timeout differ from Kubernetes' timeout?
- When does a process stop via `SIGTERM`, and when is it killed with `SIGKILL`?
- How do we verify behavior using Java code, HTTP clients, logs, and exit status?

## 2. Termination Mechanisms and Consequences

| Mechanism | Primary impact | In-flight HTTP | Cleanup callbacks |
| --- | --- | --- | --- |
| `server.shutdown=graceful` with context close | Web server stops accepting new requests and waits with a bound | Has a chance to finish | Spring lifecycle/destroy callbacks run via context closure |
| `server.shutdown=immediate` with context close | Skips the HTTP graceful wait phase | Not guaranteed, though fast requests may still finish | Context still runs eligible lifecycle/destroy callbacks |
| `SIGTERM` received by JVM | Starts JVM shutdown path, normally triggers shutdown hooks | Depends on Spring hook and timeouts | Has a chance if not killed before deadline |
| `SIGKILL` / kill -9 | Kernel/container forcibly terminates process | No | JVM shutdown hooks and `@PreDestroy` have no chance to run |
| `context.close()` | Closes `ConfigurableApplicationContext` via Java API | Depends on server graceful/immediate | Yes |
| `SpringApplication.exit(context)` | Closes context, computes exit code | Depends on server | Yes |
| `System.exit(status)` | Initiates normal JVM shutdown mechanism | Depends on hooks and timing | Hooks may run |
| `Runtime.halt(status)` | Forcibly halts the JVM | No | Skips normal hook path |

**Do not equate `server.shutdown=immediate` with `System.exit` or `SIGKILL`.** A Spring Boot property only controls how the embedded web server shuts down within the context lifecycle; it does not send OS signals, power off the process, or skip bean destruction.

### Normal Shutdown Path Diagram

~~~mermaid
flowchart TD
  A["App serving requests"] --> B["SIGTERM or context.close()"]
  B --> C["ContextClosedEvent"]
  C --> D["SmartLifecycle shutdown by phase"]
  D --> E{"server.shutdown?"}
  E -->|"graceful"| F["Stop new requests, bounded wait for in-flight"]
  E -->|"immediate"| G["Stop web server without graceful waiting"]
  F --> H["Stop remaining lifecycle components"]
  G --> H
  H --> I["@PreDestroy / DisposableBean / custom destroy"]
  I --> J["Resource cleanup, close context"]
  J --> K["JVM exits when process conditions allow"]
~~~

This diagram is a **conceptual model**, not an absolute assertion of log ordering across custom beans, executors, and libraries. The `SIGKILL` path does not follow these cleanup steps.

## 3. Spring Boot 3.5 Configuration

### Graceful Shutdown Is Enabled by Default

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

`server.shutdown=graceful` is already the default in Spring Boot 3.5 for supported embedded servers; declaring it explicitly makes intent clear to readers. The `20s` value is a **custom example**, not the default: in Spring Boot 3.5 documentation, `spring.lifecycle.timeout-per-shutdown-phase` defaults to **30s**.

**This timeout applies per `SmartLifecycle` phase/group**, not as a hard ceiling for the entire JVM shutdown. Multiple phases, destroy callbacks, shutdown hooks, and non-container work may exist. Total SIGTERM→exit duration can exceed a single phase timeout.

### Stopping the Web Server Without Graceful Waiting

~~~properties
server.shutdown=immediate
~~~

When the context closes, the server skips the graceful HTTP in-flight protection phase. However, a short request may already have finished right before the server closes; therefore, never claim "every immediate-mode request always fails". You must observe requests that had genuinely been accepted by the server.

### Related Properties with Different Purposes

| Property | Effect | What it cannot do |
| --- | --- | --- |
| `server.shutdown` | Selects HTTP graceful or immediate | Does not kill the JVM itself |
| `spring.lifecycle.timeout-per-shutdown-phase` | Caps wait time for each lifecycle stop phase | Does not stop Java tasks that ignore interruption |
| `spring.main.register-shutdown-hook` | Whether `SpringApplication` registers a JVM shutdown hook | Does not turn `SIGKILL` into graceful shutdown |
| `spring.task.execution.shutdown.await-termination` | Configures waiting for eligible task executors on close | Does not affect arbitrary executors created outside Spring |
| `spring.task.scheduling.shutdown.await-termination` | Configures waiting for eligible schedulers on close | Does not guarantee every business job commits |
| `spring.main.keep-alive` | Keeps app alive when non-daemon threads are absent | Not a graceful shutdown flag |

## 4. In-Flight Requests vs. New Requests

### HTTP Behavior During the Grace Period

Spring Boot 3.5 documents:
- **Tomcat, Jetty, Reactor Netty** stop accepting new requests/connections at the network layer during graceful shutdown.
- **Undertow** may accept new connections yet immediately respond with `HTTP 503 Service Unavailable`.
- Keep-alive mechanisms, HTTP protocols, and embedded server implementations can cause details to vary.

Once draining begins, already accepted requests have a chance to finish within the limit. If an HTTP handler needs 45 seconds while the phase timeout is only 20 seconds, there is **no guarantee** the handler succeeds; clients may see timeouts, connection resets, or server-specific responses.

For **SSE, WebSockets, streaming, and long-polling**, requests/connections can stay open for a long time and do not fit an assumption that "everything finishes in a few seconds". Design explicit session/stream closure and reconnect signaling.

### Request Completion Differs from Job Completion

If an endpoint returns `HTTP 202 Accepted` right after enqueueing a job, the HTTP request is considered finished while the background job may still be running. HTTP graceful shutdown **does not automatically wait** for every future or queued job merely because the initiating HTTP request succeeded.

Similarly, a "response sent" log line does not necessarily prove every database transaction, message acknowledgement, or remote side effect committed. Never use a single 200 response as proof that data cannot be lost during shutdown.

## 5. Spring Context Lifecycle and Cleanup Callbacks

Spring Boot registers a JVM shutdown hook by default for each `SpringApplication` so the context closes along the normal shutdown path. When closing the context, Spring Framework offers these extension points:

- `ContextClosedEvent`: signal that the context is starting to close.
- `SmartLifecycle.stop(Runnable callback)`: phase-ordered stop mechanism, supporting asynchronous waiting.
- `@PreDestroy`: destroy callback on managed beans, using `jakarta.annotation` in Spring Boot 3.x.
- `DisposableBean.destroy()`: Spring interface callback.
- Custom destroy method: e.g., `@Bean(destroyMethod = "close")`.

### ContextClosedEvent

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ClosingListener {
    @EventListener
    void onContextClosed(ContextClosedEvent event) {
        System.out.println("CONTEXT_CLOSING");
    }
}
~~~

This class can be placed in a Spring component-scanned package. The listener should be brief, safe, avoid spawning unmanaged tasks, and avoid assuming all network clients remain usable throughout shutdown.

### @PreDestroy

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class ManagedResource {
    @PreDestroy
    void release() {
        System.out.println("RESOURCE_DESTROYED");
    }
}
~~~

Only container-managed beans receive these lifecycle callbacks. If a class is instantiated with `new` outside the context, the container does not automatically invoke `release()`. Under `SIGKILL`, `@PreDestroy` does not run. If a bean fails to be created during startup, an uncreated bean cannot be expected to receive destroy callbacks either.

If the same bean declares all destroy hooks, Spring Framework documents the standard order as `@PreDestroy`, `DisposableBean.destroy()`, and custom destroy method. Avoid closing the same resource multiple times if its API is not idempotent.

### SmartLifecycle Phase

`SmartLifecycle` allows auto-starting/stopping a component and choosing a phase:

~~~text
START: lower phase -> higher phase
STOP:  higher phase -> lower phase
~~~

Ordering is also influenced by `depends-on` relationships: a dependent bean must stop before its dependency is destroyed. Spring Boot uses an appropriate phase to run HTTP graceful shutdown early during the stop sequence.

`SmartLifecycle.stop(Runnable callback)` must invoke the callback after stopping completes. Otherwise, the lifecycle processor may wait until the phase timeout expires. For async work, call the callback in a `finally` block of the drain waiter or corresponding completion path—never invoke it while work is still running and falsely claim a clean stop.

### Illustrative Executor-Managing Class

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class ManagedJobLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final ExecutorService pool =
            Executors.newSingleThreadExecutor();

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 0;
    }

    @Override
    public void stop(Runnable callback) {
        running.set(false);  // stop accepting new jobs here
        pool.shutdown();

        Thread waiter = new Thread(() -> {
            try {
                if (!pool.awaitTermination(
                        8, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                pool.shutdownNow();
            } finally {
                callback.run();
            }
        }, "job-drain-waiter");

        waiter.setDaemon(true);
        waiter.start();
    }

    @Override
    public void stop() {
        running.set(false);
        pool.shutdownNow();
    }
}
~~~

This is syntactically valid Java code, though it omits a job submission API because its responsibility is illustrating stop behavior. Real applications must include an intake gate and track whether jobs committed. `shutdownNow()` only **attempts** interruption; if a job ignores interrupts, invoking the callback after the deadline **does not mean all business work succeeded**.

When manual management is unnecessary, prefer Spring's `TaskExecutor`/`TaskScheduler` or listener containers with framework-supported stop policies.

## 6. Runnable Spring Boot Java 17+ Example

The project uses Spring Boot 3.5.16, Java 17+, Maven, Spring Web, and Actuator. One endpoint holds a request for 5 seconds to test graceful shutdown, `/ping` checks availability, and a bean logs shutdown milestones.

File tree:

~~~text
graceful-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/grace/
    │   ├── GracefulLabApplication.java
    │   ├── WorkController.java
    │   └── ClosingObserver.java
    └── resources/application.yaml
~~~

### pom.xml

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
    <artifactId>graceful-lab</artifactId>
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

### application.yaml

~~~yaml
spring:
  application:
    name: graceful-lab
  main:
    banner-mode: "off"
  lifecycle:
    timeout-per-shutdown-phase: 12s

server:
  port: 18080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

The 12s timeout is a lab value sufficient to observe a 5s request and test requests exceeding the threshold. Do not treat this as a default production value. Readiness health probes are enabled so the script can wait for startup completion before testing shutdown.

### GracefulLabApplication.java

~~~java
package com.example.grace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GracefulLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(GracefulLabApplication.class, args);
    }
}
~~~

### WorkController.java

~~~java
package com.example.grace;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {
    private final AtomicInteger active = new AtomicInteger();

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/active")
    public int active() {
        return active.get();
    }

    @GetMapping("/work")
    public String work(
            @RequestParam(defaultValue = "5000") long millis)
            throws InterruptedException {

        if (millis < 0 || millis > 15000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid millis");
        }

        int count = active.incrementAndGet();
        System.out.println("WORK_BEGIN active=" + count);
        try {
            Thread.sleep(millis);
            System.out.println("WORK_FINISHED");
            return "finished";
        } finally {
            active.decrementAndGet();
        }
    }
}
~~~

`AtomicInteger` counts active requests for lab observation and does not replace transaction commits or durable job queues. `Thread.sleep` merely simulates a waiting request and should not be used in production logic to make an app "graceful".

### ClosingObserver.java

~~~java
package com.example.grace;

import jakarta.annotation.PreDestroy;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ClosingObserver {

    @EventListener
    public void onClose(ContextClosedEvent event) {
        System.out.println("CONTEXT_CLOSING");
    }

    @PreDestroy
    void destroy() {
        System.out.println("BEAN_DESTROYED");
    }
}
~~~

If the JVM receives a normal shutdown signal and the Spring context closes, this bean logs both milestones. Do not expect callbacks to run if the process is killed with `SIGKILL` or OOMKilled.

### Running

~~~bash
mvn -q -DskipTests package
java -jar target/graceful-lab-0.0.1-SNAPSHOT.jar
~~~

In another terminal:

~~~bash
curl -fsS http://127.0.0.1:18080/ping
curl -fsS http://127.0.0.1:18080/actuator/health/readiness
~~~

Body of `/ping`:

~~~text
pong
~~~

Once the application is ready, readiness health under default configuration typically returns status `UP`. Do not write tests relying on JSON field order because Actuator may be further customized.

## 7. Sending SIGTERM While a Request Is Processing

You must **send the signal to the Java PID**, not merely to a shell wrapper. Use Linux/Bash to automatically wait for server readiness and ensure the request entered the controller before sending TERM.

Create **measure-shutdown.sh** in the same directory as `pom.xml`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash measure-shutdown.sh graceful|immediate" >&2
  exit 2
fi

mode="$1"
if [[ "$mode" != "graceful" &&
      "$mode" != "immediate" ]]; then
  echo "Invalid mode" >&2
  exit 2
fi

jar="target/graceful-lab-0.0.1-SNAPSHOT.jar"
log="app-$mode.log"
response="response-$mode.txt"

java -jar "$jar" "--server.shutdown=$mode" \
    >"$log" 2>&1 &
pid=$!

cleanup() {
  kill -TERM "$pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for ((i=0; i<300; i++)); do
  if curl --max-time 1 -fsS -o /dev/null \
      http://127.0.0.1:18080/actuator/health/readiness \
      2>/dev/null; then
    ready=1
    break
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "App exited early, inspect $log" >&2
    exit 1
  fi
  sleep 0.1
done

if [[ "$ready" -ne 1 ]]; then
  echo "Readiness timeout" >&2
  exit 1
fi

curl --max-time 25 -fsS \
    "http://127.0.0.1:18080/work?millis=5000" \
    >"$response" 2>"curl-$mode.err" &
reqpid=$!

seen=0
for ((i=0; i<100; i++)); do
  if grep -q "WORK_BEGIN active=" "$log"; then
    seen=1
    break
  fi
  if ! kill -0 "$reqpid" 2>/dev/null; then
    break
  fi
  sleep 0.05
done

if [[ "$seen" -ne 1 ]]; then
  echo "Request not confirmed; inspect $log" >&2
  kill -TERM "$pid" 2>/dev/null || true
  wait "$reqpid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  exit 1
fi

started_ns=$(date +%s%N)
kill -TERM "$pid"

set +e
wait "$reqpid"
request_exit=$?
wait "$pid"
java_exit=$?
set -e

ended_ns=$(date +%s%N)
duration_ms=$(( (ended_ns - started_ns) / 1000000 ))

echo "mode=$mode"
echo "request_exit=$request_exit"
echo "java_exit=$java_exit"
echo "shutdown_ms=$duration_ms"

grep -E "WORK_BEGIN|WORK_FINISHED|CONTEXT_CLOSING|BEAN_DESTROYED" \
    "$log" || true
~~~

Run one at a time, never concurrently on port 18080:

~~~bash
bash measure-shutdown.sh graceful
bash measure-shutdown.sh immediate
~~~

**This script targets Linux with GNU `date`** supporting `%N`; default macOS Bash/`date` may not support nanosecond precision this way. It also requires `curl`, `grep`, Java 17+, and the built JAR. The script includes timeouts to avoid waiting indefinitely on startup, yet if a task ignores TERM or a shutdown hook hangs abnormally, `wait "$pid"` can still linger; in CI, wrap it with an external watchdog/timeout and a clear kill policy.

### What Results to Observe

In `graceful` mode with a 5-second request, if the signal arrives at the right time, the phase timeout is 12 seconds, and nothing else blocks shutdown, you can **expect**:
- The controller logged `WORK_BEGIN`.
- The request has a chance to log `WORK_FINISHED` and the client receives body `finished`.
- Spring logs context close and destroy milestones.
- The process exits after the request drains and shutdown callbacks finish.

However, **never promise fixed timing outcomes**. `immediate` mode may fail the request or finish in time depending on timing and server behavior. Compare logs, `request_exit`, and `shutdown_ms` across multiple runs rather than drawing conclusions from a single run.

If `request_exit=0`, the client received a successful response, yet that **does not** prove every message or DB transaction in a large app committed. If `java_exit` is non-zero, inspect JVM/server logs and signal status to determine the exact reason.

### Testing Exceeding the Deadline

Replace `millis=5000` with `millis=15000` in the script while keeping `timeout-per-shutdown-phase=12s`. Because the request exceeds the phase budget, there is **no guarantee** the client will receive a complete body. This experiment illustrates why applications need request timeouts, retries, and idempotency rather than endlessly increasing grace periods.

## 8. From Signals to Context: System.exit and SpringApplication.exit

### Closing the Context in Java

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// When reaching a valid stopping point:
context.close();
~~~

This is a **snippet** requiring imports for `ConfigurableApplicationContext` and `SpringApplication`, plus a `MyApplication` class. For a long-running web application, **do not call `context.close()` right after `run`**: doing so initiates web server shutdown right after startup.

### SpringApplication.exit and Exit Codes

For CLI/batch apps, you can use:

~~~java
int status = SpringApplication.exit(context);
System.exit(status);
~~~

`SpringApplication.exit` closes the context and resolves an exit code via `ExitCodeGenerator` beans if applicable, then `System.exit` passes the code to the OS. Example bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

This snippet requires imports for `ExitCodeGenerator` and `@Bean`, placed inside a Spring config class. This is not a standard way for a web application to exit automatically after `ApplicationReadyEvent`: the ready event signals startup completion, **not** a command to terminate the service.

### System.exit vs. Runtime.halt

`System.exit(code)` requests normal JVM shutdown and triggers shutdown hooks. Still, it does not guarantee completion of arbitrary running custom workers. `Runtime.halt(code)` forcibly terminates the JVM without running hooks; avoid using it for normal shutdown management.

### Spring Boot Shutdown Hook

By default `SpringApplication` registers a shutdown hook. If `spring.main.register-shutdown-hook=false` is configured or a custom lifecycle is built, the TERM→context.close path is no longer guaranteed by default configuration. In containers, verify whether Java is truly the PID receiving the signal.

## 9. Readiness, Liveness, and the Drain Phase

Spring Boot provides `ApplicationAvailability` and Actuator health groups for liveness/readiness. Model during shutdown:

| Phase | Liveness | Readiness | Meaning |
| --- | --- | --- | --- |
| Active | `CORRECT` | `ACCEPTING_TRAFFIC` | Can route requests |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Should not send new work; drain remaining in-flight |
| Context closed | HTTP probes no longer meaningful | HTTP probes no longer meaningful | Process stopped serving |

**Subtle point:** once the web server stops accepting new requests, `/actuator/health/readiness` may also become unreachable. External callers should not always expect a JSON response showing `REFUSING_TRAFFIC`; refusing connections is valid behavior during the closing phase.

The `ApplicationReadyEvent` milestone at startup does not prove all background jobs have finished. An application can be ready, return HTTP 200, and simultaneously process queued jobs; monitor, stop, and confirm those workstreams separately.

## 10. Kubernetes and Docker: Platform Shutdown Budgets

Kubernetes typically follows these steps:
1. The Pod is marked terminating; EndpointSlice/traffic routing begins updating.
2. If a `preStop` hook exists, kubelet runs it before asking the runtime to send TERM.
3. The runtime sends `SIGTERM` to PID 1 in the container.
4. The JVM/Spring Boot handles shutdown if still within capacity.
5. If `terminationGracePeriodSeconds` is exceeded, kubelet sends `SIGKILL` to forcibly stop it.

**`preStop` duration counts toward the total termination budget**, not as free extra time added on top. Kubernetes handles minor grace extensions in certain cases when preStop overruns, but never design around relying on that extension.

### Illustrative Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: graceful-lab
  template:
    metadata:
      labels:
        app: graceful-lab
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.org/demo/graceful-lab:1.0
          ports:
            - containerPort: 18080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 18080
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 18080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 18080
            periodSeconds: 10
~~~

This is an **illustrative manifest**; the image must be built, pushed, and replaced with a valid project image. Proper security, namespaces, quotas, image credentials, and deployment conditions are required. Never apply an example manifest directly to production.

`terminationGracePeriodSeconds=45` is the Pod's total budget; `spring.lifecycle.timeout-per-shutdown-phase=12s` applies per phase. If there are multiple phases, `preStop`, or slow cleanup, the total may still exceed 45 seconds. Measure **real TERM→exit** under load before choosing Kubernetes budgets.

### Container PID 1

A Dockerfile form like:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/graceful-lab.jar"]
~~~

lets the JVM receive signals directly in standard containers. If launching Java through a shell script, the final line should use `exec java ...` or ensure the shell forwards TERM properly rather than letting the shell catch the signal while the child JVM misses it. Never assume clicking Stop in an IDE behaves like Kubernetes SIGTERM.

### Is preStop Always Necessary?

No. It can help if a specific load balancer needs a drain delay for routing sync, yet a `preStop` that sleeps too long eats into the shutdown budget. If the container uses a distroless image, `/bin/sh` or `sleep` may not even exist. Add `preStop` only after identifying a concrete routing issue and measuring it.

## 11. @Async, Schedulers, Message Consumers, and Transactions

**Web graceful shutdown handles only web requests**, not automatically every task in the process. For Spring Boot auto-configured executors/schedulers, consider:

~~~properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=20s
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=20s
~~~

Exact behavior depends on the executor type and Spring Boot version; these do not automatically apply to a raw `Executors.newFixedThreadPool(...)` created manually by the application. When using virtual threads on Java 21+, re-verify the task executor type and whether these properties still apply.

### Stopping a Queue Consumer Safely

The practical sequence is usually:
1. Mark the consumer to stop taking new jobs.
2. Stop polling/claiming additional messages.
3. Wait for in-flight jobs to reach a commit boundary or deadline.
4. Ack/commit upon genuine success; retry/requeue per broker contract if unfinished.
5. Close producer/consumer/network clients once related work no longer needs them.

Details vary across Kafka, RabbitMQ, JMS, and custom queues. Never claim a message is "guaranteed not lost" just because Spring Boot closed its context. Use idempotency, durable queues, timeouts, and checkpoints.

### Database and Resource Dependencies

An executor stopping too late can try to use a datasource/client that has already been destroyed. Ensure proper stop phase and dependency ordering. HTTP client errors or interrupts do not prove whether a transaction rolled back or committed; inspect transaction managers, DB logs, and business outcomes.

### Schedulers

Stopping a scheduler differs from completing all running jobs. For Quartz, Spring Boot provides `spring.quartz.wait-for-jobs-to-complete-on-shutdown`; configure it to match job requirements. Never let an untimed job stall shutdown forever.

## 12. Common Operational Failures

| Symptom | Possible cause | Verification and fix |
| --- | --- | --- |
| `SIGTERM` sent yet process does not exit | Self-created non-daemon thread, blocked task, missing stop callback | Thread dump, inspect `SmartLifecycle`, interrupts/timeouts |
| `@PreDestroy` skipped on `kill -9` | Forced `SIGKILL` | Use normal TERM; build recovery for forced kills |
| `server.shutdown=immediate` yet destroy callbacks still run | Immediate only affects HTTP graceful waiting | This can be normal expected behavior |
| Graceful request cut off despite configured timeout | Request exceeded deadline, client cancelled, early SIGKILL, server behavior | Compare logs, deadlines, and signals |
| Readiness endpoint unreachable during shutdown | Web server stopped accepting new connections | Check logs/EndpointSlice instead of demanding health JSON |
| Shutdown takes longer than configured timeout | Timeout is **per-phase**, plus other cleanup/hooks | Measure full SIGTERM→exit and individual phases |
| Kubernetes sends SIGKILL despite Spring configured for 20s | Pod grace too small, preStop consumed time | Increase total grace appropriately based on measurements |
| HTTP 202 returned while job remains unfinished | Work is decoupled from HTTP lifecycle | Manage queue/executor lifecycle separately |
| Context closed yet JVM stays alive | Raw non-daemon thread did not stop | `jcmd`, stop executors, and join with a timeout |
| JVM exits without graceful logs | Wrong PID/signal, OOMKill, shell wrapper | Check container status/PID 1 and exit code |
| SIGTERM caught only by shell | Entrypoint did not forward TERM | Exec-form ENTRYPOINT or shell `exec` |
| IDE Stop drops requests | IDE may use immediate termination | Test real signals in terminal/staging |
| Incomplete DB transaction | Interrupt/timeout, premature resource destruction | Idempotency, transaction metrics, retries |
| `preStop` timed out | Hook consumed the grace period | Shorten hook, tune total budget |

### Why Shouldn't You Call System.exit in a Controller?

If a public HTTP request can trigger `System.exit`, a client could shut down the entire instance, creating security and availability issues. Allow stopping only via trusted control planes, service management, or strictly protected internal APIs when genuinely needed.

### Why Shouldn't You Increase Timeouts to Infinity?

Requests or jobs can hang due to deadlocks, untimed I/O, or unresponsive downstreams. An infinite graceful period can stall rollouts and auto-recovery while Kubernetes still enforces a kill deadline. Set SLO-based deadlines, cancellation, and retries/compensation for incomplete work.

## 13. Measuring Shutdown and Testing Before Deployment

Key metrics:

| Metric | Goal |
| --- | --- |
| SIGTERM→process exit | Compare total duration against Kubernetes grace |
| In-flight HTTP at shutdown start | Know the volume requiring drain |
| Requests completed before exit | Measure graceful effectiveness |
| Request timeouts, connection resets, 5xx | Detect cut-off requests |
| Queue backlog/in-flight jobs | Track background work |
| Message retries/requeues | Assess work preservation |
| DB commit/rollback outcomes | Verify data correctness |
| Per-phase stop latency | Identify slow shutdown phases |
| `@PreDestroy` and shutdown-hook logs | Verify lifecycle execution |
| SIGKILL/OOMKilled/exit code | Distinguish normal vs. forced stops |

Test at least these scenarios:
- Zero requests: application exits cleanly.
- One short in-flight request: graceful mode gives it a chance to complete.
- Request longer than timeout: predictable response and retry when needed.
- Multiple concurrent requests: server stops accepting infinite new work while draining.
- Running background tasks or consumers: dedicated stop policy works.
- Forced kill: recovery mechanism handles missing callbacks.
- Multi-replica rolling deployment: stays within availability SLO.
- CPU/memory pressure environments: shutdown still respects reasonable deadlines.

When benchmarking, run multiple iterations on the same JVM/Boot version, web server, and workload; report real measurements rather than assuming fixed millisecond counts. `WORK_FINISHED` in the lab only indicates execution passed a print statement, not that every business operation in a real system committed.

## 14. Deployment Checklist

1. Confirm Spring Boot version and embedded web server.
2. Recognize graceful is default in Spring Boot 3.5; set `server.shutdown=graceful` explicitly if desired.
3. Configure `spring.lifecycle.timeout-per-shutdown-phase` **per phase**, not as a process-wide deadline.
4. Stop intake before closing shared resources.
5. Wait for in-flight work with bounded timeouts and proper cancellation.
6. Manage `@Async`, `@Scheduled`, message consumers, and raw executors separately.
7. Invoke `SmartLifecycle.stop(Runnable)` callback once the phase finishes processing.
8. Use `@PreDestroy` for bean-managed resources without assuming it runs after SIGKILL.
9. Do not equate `server.shutdown=immediate` with `kill -9`.
10. Ensure the Java process receives TERM, especially inside Docker/Kubernetes.
11. Include `preStop` and all Spring phases within `terminationGracePeriodSeconds`.
12. Verify readiness/EndpointSlice and new traffic routing mechanics.
13. Set request timeouts, retries, idempotency, and checkpoints for critical data.
14. Monitor exit codes, shutdown duration, in-flight counts, 5xx rates, and broker commit outcomes.
15. Test repeatedly in staging under production-like load and signals.

## 15. Review Questions

**1. Does Spring Boot 3.5 default to graceful or immediate?**  
Graceful for supported embedded web servers.

**2. Which property disables HTTP graceful waiting?**  
`server.shutdown=immediate`.

**3. Does it skip `@PreDestroy` like SIGKILL?**  
No. The context still invokes destroy callbacks during normal closure.

**4. Is `spring.lifecycle.timeout-per-shutdown-phase` a global deadline?**  
No. It applies per `SmartLifecycle` phase.

**5. How does SIGTERM differ from SIGKILL?**  
TERM gives the JVM a chance to run hooks and cleanup; KILL forcibly terminates without normal cleanup paths.

**6. What must `SmartLifecycle.stop(Runnable callback)` do?**  
Invoke the callback once the corresponding stop step finishes so the container can advance the lifecycle.

**7. Do higher or lower phase numbers stop first?**  
Higher phases stop first; startup runs in the reverse direction.

**8. Does `ApplicationReadyEvent` confirm all background jobs finished?**  
No. It is a startup milestone and does not automatically await application-created futures.

**9. If an HTTP request returned 202 while a background job is running, does web graceful shutdown protect that job?**  
Not automatically; queue/executor lifecycles are needed.

**10. Why might health readiness fail to respond over HTTP during shutdown?**  
The web server is stopping acceptance of new requests/connections.

**11. Does `preStop` in Kubernetes consume termination grace?**  
Yes. It is not free extra time added on top.

**12. Context closed yet the JVM keeps running—what should you check?**  
Non-daemon threads or unshut-down executors, not only web server config.

**13. To protect data after SIGKILL, what is needed beyond `@PreDestroy`?**  
Transactions, idempotency, durable queues/checkpoints, and retries/recovery.

**14. Is it contradictory if a request still completes in immediate mode?**  
No. Depending on timing and server, a request may finish right before or during closure.

## 16. Official Documentation Sources

- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): default mode, server differences, and timeouts.
- [Spring Boot 3.5 — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): JVM shutdown hooks, `SpringApplication.exit`, and `ExitCodeGenerator`.
- [Spring Boot 3.5 — Actuator Endpoints / Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): readiness/liveness during shutdown.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): per-phase timeout, executor/scheduler shutdown, and shutdown hooks.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, `SmartLifecycle`, and phase ordering.
- [Oracle Java 17 — Runtime API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): JVM exit, halt, and hooks.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): TERM/KILL, preStop, and termination grace.

**Conclusion:** graceful shutdown is a **deadline-bounded coordinated process** across the Spring web server, context, background work, and deployment platform. Only when all of these layers are designed and tested together does the application have a chance to protect in-flight requests and preserve data consistency. No single property guarantees safety against every timeout, crash, or SIGKILL.