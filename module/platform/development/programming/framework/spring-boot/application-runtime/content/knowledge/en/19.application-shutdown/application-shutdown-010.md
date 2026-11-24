# SIGTERM, Ctrl+C, and Cleanup Limits on Forced Process Termination in Spring Boot

A Spring Boot application needs a **controlled shutdown** mechanism: stop accepting new work, give in-flight requests or tasks a chance to complete, stop consumers, return connections, and close resources. However, not every way a process terminates allows these steps to execute.

**Three things to distinguish immediately:**

1. **`SIGTERM`** on Unix/Linux systems is a termination request that the JVM can handle to begin its shutdown sequence. In standard Java/Spring Boot configurations, shutdown hooks get a chance to run, from which Spring closes the `ApplicationContext`.
2. **`Ctrl+C`** in a Unix terminal typically sends `SIGINT` to the foreground process group; a standard HotSpot JVM can also initiate the shutdown sequence. On Windows, console control events and how IDEs/terminals forward signals differ from Linux; verify in the real environment.
3. **`SIGKILL`** (such as `kill -9`), `Runtime.halt(...)`, certain native crashes, or power failures can terminate the process **immediately**. Java **does not guarantee running shutdown hooks, `@PreDestroy`, or `finally`**. A container killed after its grace period expires also falls into this group.

Therefore, **graceful shutdown is time-bounded best effort, not an unconditional guarantee that all work finishes**. A sound design both cleans up quickly and verifiably on soft signals and **recovers accurately after sudden kills**.

This lesson belongs to the **Application Shutdown** section of Spring Boot Application Runtime; examples use Java 17+, Spring Boot 3.3.x, and Linux/Kubernetes. Behavior dependent on OS, JVM, web server, and launch mechanism is stated explicitly rather than assuming a single shutdown path across all environments.

## 1. Map of Process Termination Paths

| Scenario | What happens at the system level | Likelihood of running app cleanup |
|---|---|---|
| `kill -TERM <PID>` on Linux | Sends SIGTERM; JVM normally begins shutdown sequence | Has a chance to run JVM shutdown hooks → close Spring context → lifecycle callbacks |
| Pressing `Ctrl+C` in a Unix terminal | Terminal sends SIGINT to the foreground process group | JVM normally handles the signal, though wrappers/IDEs may alter effects |
| `System.exit(code)` | Starts the JVM shutdown sequence | Runs hooks per Java contract if the JVM can proceed |
| `SpringApplication.exit(context)` | Closes context and computes app exit code | Runs lifecycle callbacks on context close; **does not terminate the JVM by itself** |
| `context.close()` | Closes a Spring ApplicationContext | Runs context lifecycle callbacks; JVM may stay alive |
| `kill -KILL <PID>` or `kill -9 <PID>` | SIGKILL cannot be caught or ignored by the app | **Does not run** Java cleanup as a pre-kill step |
| `Runtime.getRuntime().halt(code)` | JVM exits immediately without normal shutdown sequence | Skips hooks; risks losing cleanup |
| Container exceeds termination grace period | Runtime forces remaining processes down, typically via SIGKILL | In-progress cleanup is cut short |
| Severe native crash / power loss | Process or machine stops outside normal coordination | No guarantee of hooks/`finally` |

The `kill` commands in the table are **Unix/Linux illustrations**; never run them against production PIDs without authorization. `<PID>` is a placeholder for the **lab** process PID.

**Wording note:** never call `SIGTERM` a "guaranteed clean stop". It is a **request signal** to stop. The JVM still needs time to run hooks, and the application must coordinate beans properly. If the JVM is unresponsive, a hook hangs, or infrastructure times out, the system can still force termination.

## 2. How Do JVM Shutdown Hooks Work?

Java provides:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            System.out.println("JVM shutdown hook");
        }, "my-shutdown-hook")
);
~~~

This snippet illustrates Java 17+, not a complete Spring Boot program. When the JVM enters the **normal shutdown sequence**, registered shutdown hooks are started.

Key points in the `java.lang.Runtime` contract:

- A hook must be an instantiated `Thread` that has **not yet started** when registered.
- The JVM starts shutdown hooks in an **unspecified order**; hooks may **run concurrently**.
- Once shutdown has begun, hooks can no longer be registered or unregistered; doing so may throw `IllegalStateException`.
- Hooks must finish quickly, be thread-safe, and avoid deadlocks.
- Hooks run while other services are also stopping; never assume thread pools, logging, databases, or other hooks remain operational.
- If a hook blocks indefinitely, the shutdown sequence may never finish. OS/containers will not wait forever.
- Hooks can be triggered by `System.exit(...)`, natural JVM exit, or OS signals supported by the JVM implementation.
- `SIGKILL`, `Runtime.halt(...)`, and abort scenarios give this sequence no reliable chance.

**Do not write multiple custom JVM hooks to control individual Spring bean closing order.** Because hook order is unspecified, a custom hook closing a JDBC pool while Spring's hook is still stopping requests can cause requests to hit an already closed pool.

Spring Boot already provides a hook and lifecycle to manage the context. Prefer **`@PreDestroy`, `SmartLifecycle`, `DisposableBean`, or `@Bean` destroy methods** rather than adding a new hook to manipulate Spring-owned resources directly.

## 3. What Does SpringApplication Do When JVM Shutdown Is Requested?

Under Spring Boot 3.3, `SpringApplication` registers a JVM shutdown hook by default to close `ApplicationContext` on JVM exit. Configure via:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);

application.setRegisterShutdownHook(true);  // Default is true.
application.run(args);
~~~

This is illustrative code: `MyApplication` must be a valid configuration source with imports. Keeping `setRegisterShutdownHook(true)` is the default, so a typical Spring Boot application **does not need to register its own hook to call `context.close()`**.

Condensed path:

~~~text
SIGTERM / SIGINT handled by JVM / System.exit(...)
                    |
                    v
            JVM shutdown sequence
                    |
                    +-- JVM hooks are started
                          (no guaranteed order among hooks)
                    |
                    +-- Spring Boot shutdown hook:
                          closes ApplicationContext
                                   |
                                   v
                      LifecycleProcessor.onClose()
                          - stop SmartLifecycle beans
                          - graceful web server stop if enabled
                                   |
                                   v
                         Destroy singleton beans
                          - @PreDestroy
                          - DisposableBean.destroy()
                          - @Bean(destroyMethod=...)
                                   |
                                   v
                        Close bean-owned resources
~~~

This is a **conceptual diagram** of Spring context closure, not the full internal call stack. Exact order among beans depends on phases, dependencies, and destroy mechanisms; never rely on log ordering across hooks from separate systems.

### context.close Differs from System.exit

| Call | Primary effect |
|---|---|
| `context.close()` | Closes **that context**. With multiple contexts in one JVM, other contexts do not vanish just because this one closed. |
| `SpringApplication.exit(context)` | Closes context via Boot's helper and returns an exit code computed from `ExitCodeGenerator` beans. |
| `System.exit(code)` | Starts terminating **the entire JVM**, triggering shutdown hooks. |
| `Runtime.getRuntime().halt(code)` | Terminates the JVM immediately without running normal shutdown hooks. |

A console application can explicitly do:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

This example is **only for intentional exit**, never to be placed verbatim into a long-lived web server. `SpringApplication.exit(context)` already closes the context; `System.exit(code)` proceeds to exit the JVM and may execute remaining hooks. Calling only `SpringApplication.exit(...)` may leave non-daemon threads keeping the JVM alive.

Never call `System.exit(...)` arbitrarily from `@PreDestroy` or inside a shutdown hook to "clean up faster"; doing so risks hangs, circular dependencies, or breaking the shutdown sequence.

## 4. @PreDestroy and SmartLifecycle Solve Two Layers of Responsibility

There are two distinct tasks:

1. **Stopping operations:** stop accepting new work, stop polling/message consumers, stop spawning tasks, and await a bounded share of in-flight work. `SmartLifecycle` manages start/stop and phase ordering.
2. **Destroying beans/resources:** close files, connections, clients, caches, or objects owned by the bean. `@PreDestroy`, `DisposableBean`, and custom destroy methods represent cleanup when the bean is destroyed.

Example:

~~~java
@Component
public class RemoteClientOwner {

    private final ExternalClient client;

    public RemoteClientOwner(ExternalClient client) {
        this.client = client;
    }

    @PreDestroy
    public void close() {
        client.close();
    }
}
~~~

This is **illustrative code**; `ExternalClient` and bean wiring are omitted, so it is not a standalone runnable file. `@PreDestroy` runs only when Spring **destroys a managed bean**, not whenever an object is garbage-collected.

Spring will not clean up objects created with `new` outside the container unless you organize ownership explicitly. With **`prototype` scope**, Spring does not manage full destruction callbacks after handing the prototype instance to the caller the way it does for singletons; the caller is responsible for cleaning up resources per contract.

### SmartLifecycle stop(Runnable) and Wait Limits

A component can implement:

~~~java
@Override
public void stop(Runnable callback) {
    // Stop accepting new work and wait for tasks to complete.
    // ONLY once stopping truly finishes:
    callback.run();
}
~~~

This is an illustrative method inside a class implementing `SmartLifecycle`. When the container closes, `LifecycleProcessor` can use `stop(Runnable)` to coordinate shutdown. The callback must be invoked **after stopping succeeds or a controlled stop policy completes**.

Do not invoke the callback immediately after **merely issuing an async stop request** and pretend work is done. Conversely, if you never invoke the callback, the lifecycle processor may wait until the phase timeout expires before moving on to remaining shutdown steps.

**Do not expect phase timeouts to kill every Java task.** They bound Spring's waiting mechanism; threads/tasks that ignore interruption can keep running, keeping the process alive or getting killed by the platform at deadline.

## 5. Graceful Shutdown of the HTTP Server in Spring Boot 3.3

In Spring Boot 3.3.x, graceful shutdown of the embedded HTTP server is enabled explicitly via:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot supports graceful shutdown for Tomcat, Jetty, Reactor Netty, and Undertow according to each server's capabilities. When the context closes, graceful stop integrates with the web server's lifecycle: restricting new requests and giving running requests a chance to complete **within a wait window**.

**New-request rejection can differ by server:**

- One server may stop accepting new connections at the network layer.
- Another server may respond with a service error code such as HTTP 503.
- Keep-alive connections, proxies/load balancers, and active requests can make network-level behavior differ from a naive reading of "all new requests are immediately rejected".

`spring.lifecycle.timeout-per-shutdown-phase=20s` is the **wait duration per shutdown phase** in the lifecycle processor, not a guarantee that all JVM cleanup finishes within 20 seconds. With multiple phases, slow `@PreDestroy` callbacks, slow network closes, or Kubernetes `preStop`, total duration can be larger. Always budget the **total container lifetime** rather than looking at this single property alone.

### What Should Stop First?

One design sequence:

~~~text
Begin shutdown
   |
   v
Router/orchestrator stops routing new requests to instance
   |
   v
HTTP server graceful stop / stop accepting new messages
   |
   v
Wait for in-flight requests/jobs with bounded deadline
   |
   v
Stop schedulers, consumers, executors by dependency
   |
   v
Close DB pools, HTTP clients, broker connections, file handles
   |
   v
Process exits
~~~

This is the **desired sequence**, not a promise that events always occur strictly serially. Real semantics depend on Spring lifecycle phases, bean dependencies, container runtime, clients, and job completion behavior.

For example, if a message consumer keeps pulling messages after the database pool closed, cleanup is out of order. Organize `SmartLifecycle.getPhase()`, dependency relationships, or component-level shutdown policies to stop producers/consumers before closing resources they still use.

## 6. Runnable Spring Boot 3.3 Example: Observing Soft vs. Forced Stop

This demo accomplishes three things:

- Creates a Spring Boot web application so the JVM stays up serving requests.
- Registers **a `SmartLifecycle` bean** that logs on start/stop, alongside `@PreDestroy` on the same bean.
- Exposes `GET /lab/slow` simulating a bounded long request to observe graceful HTTP shutdown on SIGTERM.

### Structure

~~~text
shutdown-lab/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/shutdown/ShutdownLabApplication.java
        └── resources/application.properties
~~~

### build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

springBoot {
    mainClass = 'com.example.shutdown.ShutdownLabApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'shutdown-lab.jar'
}
~~~

### application.properties

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=shutdown-lab
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
logging.level.root=INFO
~~~

In production applications, 20 seconds is not mandatory; choose based on real latency/processing times, number of shutdown phases, and orchestrator budgets.

### ShutdownLabApplication.java

Create `src/main/java/com/example/shutdown/ShutdownLabApplication.java`:

~~~java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;

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
public class ShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownLabApplication.class, args);
    }

    @Bean
    ShutdownObserver shutdownObserver() {
        return new ShutdownObserver();
    }

    public static final class ShutdownObserver implements SmartLifecycle {

        private final AtomicBoolean running = new AtomicBoolean(false);

        @Override
        public boolean isAutoStartup() {
            return true;
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
                System.out.println("observer: started");
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("observer: stopped");
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                // Valid only because stop() in the demo completes synchronously.
                callback.run();
            }
        }

        @PreDestroy
        public void destroy() {
            System.out.println("observer: @PreDestroy");
        }
    }

    @RestController
    public static class LabController {

        @GetMapping("/lab/ping")
        public String ping() {
            return "pong";
        }

        @GetMapping("/lab/slow")
        public String slow(
                @RequestParam(defaultValue = "8000") long millis) {

            if (millis < 0 || millis > 15000) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "millis must be between 0 and 15000");
            }

            try {
                Thread.sleep(millis);
                return "completed";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "request interrupted during shutdown", ex);
            }
        }
    }
}
~~~

**Why is this program easy to verify?**

- Bean `ShutdownObserver` is created via `@Bean` and managed by Spring. It implements `SmartLifecycle`, so the context calls `start()` during refresh and `stop(Runnable)` during close while the bean is running.
- `@PreDestroy` is a separate cleanup callback on **the same bean**. During a normal context close, Spring stops lifecycle components before the corresponding singleton destruction phase.
- `stop(Runnable)` invokes the callback in `finally` because `stop()` in the demo **only flips a flag** and finishes synchronously. Never copy this verbatim for a consumer that must wait on asynchronous work.
- The slow endpoint simulates a request up to 15 seconds long, shorter than the 20-second HTTP graceful wait in the lab scenario.
- No manual JVM shutdown hook is created in code. Spring Boot manages context closure via its default mechanism.

### Build and Run Directly

With JDK 17+ and a project containing Gradle Wrapper:

~~~bash
./gradlew bootJar
java -jar build/libs/shutdown-lab.jar
~~~

On Windows, run `.\gradlew.bat bootJar` then `java -jar build/libs/shutdown-lab.jar`. Without a wrapper, prepare Gradle or create the project structure first. This is a Spring Boot application with dependencies; it cannot be compiled standalone with a bare `javac ShutdownLabApplication.java` command.

On successful startup, alongside Spring Boot logs, you will see:

~~~text
observer: started
~~~

To test HTTP:

~~~bash
curl http://localhost:8080/lab/ping
~~~

Expected body:

~~~text
pong
~~~

### Testing Ctrl+C

When the app runs **directly** via `java -jar ...` in an interactive terminal, press `Ctrl+C`. With a standard HotSpot JVM and Unix terminal, the JVM receives SIGINT and Spring's shutdown hook gets a chance to close the context.

Lines **printed by `ShutdownObserver`** when shutdown completes normally:

~~~text
observer: stopped
observer: @PreDestroy
~~~

Spring/Tomcat may also print shutdown logs; timing and interleaved logs are not fixed. When running via a Gradle task, an IDE, or a Windows console, Stop/Ctrl+C behavior **can differ**, because the hosting tool may terminate the JVM through its own mechanism. To verify signal behavior accurately, run the JAR directly and observe the real process.

### Testing SIGTERM on Linux in a Lab Environment

Open the first terminal and run in the shell:

~~~bash
java -jar build/libs/shutdown-lab.jar > shutdown.log 2>&1 &
APP_PID=$!
echo "Lab JVM PID=$APP_PID"
~~~

Wait for server startup. In another terminal, send a slow request:

~~~bash
curl -v "http://localhost:8080/lab/slow?millis=8000"
~~~

While the request is still running, send TERM to **that exact PID** (from the shell holding `APP_PID`):

~~~bash
kill -TERM "$APP_PID"
wait "$APP_PID"
~~~

If the server accepted the request before shutdown began, the 8-second request can have a chance to finish within the 20-second budget. Depending on signal timing, connections, load balancers, and other timeouts, every individual HTTP request is not guaranteed to succeed.

Check `shutdown.log`: on a clean soft stop, observer lines normally show `stopped` and `@PreDestroy`. **Do not** treat those log lines as proof that all database transactions, message acks, and in-flight writes committed durably.

### Comparing with SIGKILL — Only in Test Environments

Launch the app in a fresh lab process:

~~~bash
java -jar build/libs/shutdown-lab.jar > forced.log 2>&1 &
LAB_PID=$!
~~~

Once the server is up, in the same shell:

~~~bash
kill -KILL "$LAB_PID"
wait "$LAB_PID" || true
~~~

Never run this command on someone else's app, production processes, or any unverified PID.

**Core result:** SIGKILL terminates the process immediately; it prevents the JVM from running shutdown hooks and gives no guarantee that `observer: stopped` or `observer: @PreDestroy` appears. If a log line had been written before the kill due to another event, relying solely on its presence is inconclusive. Run each scenario in a fresh process under controlled conditions.

The OS reclaims many local process resources such as file descriptors and socket handles, yet incomplete business operations **do not finish automatically**. For instance, transactions may roll back depending on the system and connection state; unacked messages may be redelivered; partially written files may remain on disk.

## 7. Does `finally` Always Run?

No. `finally` is a mechanism of **a Java control flow unwinding through a `try` block**, not a contract resistant to arbitrary process kills.

Example:

~~~java
try {
    updateExternalSystem();
} finally {
    releaseLocalResource();
}
~~~

This is an illustrative snippet with pre-existing methods. If the method returns or throws an exception during normal Java execution, `finally` normally executes as control leaves `try`. However:

- If the JVM receives SIGKILL, execution can be cut mid-`try` or mid-`finally`.
- If the JVM hits `Runtime.halt()` or a native crash, Java cleanup is not guaranteed.
- If a thread blocks indefinitely and never exits `try`, `finally` does not run just because time passed.
- If the process is killed while writing external side effects, `finally` having run earlier **does not** prove the side effect completed durably.

**Similarly, `@PreDestroy` is not a function "guaranteed to run before the process vanishes".** It runs inside a controlled bean-destruction flow, and only if context closure actually reaches that callback.

Therefore, resources needing cleanup still need `finally`/`try-with-resources`/`@PreDestroy`; yet business correctness must be guaranteed through **interruption-recovery mechanisms**.

## 8. Kubernetes: `terminationGracePeriodSeconds` Is a Total Budget

When a Pod is deleted or replaced in a rollout, kubelet normally tries to let containers stop softly:

~~~text
Pod is marked Terminating
      |
      +-- EndpointSlice updates serving/ready state
      |   so new traffic gradually drains away
      |
      +-- If preStop hook exists, kubelet runs preStop
      |   (hook duration counts inside the grace period)
      |
      +-- Runtime sends TERM to container's main process
      |
      +-- Wait for container exit within total budget
      |
      +-- If time expires and still running -> SIGKILL
~~~

Kubernetes defaults to **`terminationGracePeriodSeconds: 30`** unless configured otherwise. The moment the Pod is marked terminating, the grace period starts ticking; **`preStop` is not granted extra free time outside the budget**. If `preStop` takes 15 seconds out of a 30-second budget, the app has only the remaining time for TERM handling and cleanup (aside from brief kubelet edge-case extensions).

Illustrative YAML snippet in a Pod/Deployment configuration:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: spring-app
      image: example.invalid/shutdown-lab:demo
      ports:
        - containerPort: 8080
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

This is an **illustrative Pod spec snippet**, not a ready-to-run complete manifest; `example.invalid/...` is a placeholder image name that must be replaced for your environment. `sleep 5` merely illustrates that `preStop` **consumes five seconds** of the total grace period. Do not treat sleeping as a complete traffic-draining plan.

Drain steps depend on Kubernetes Services, EndpointSlices, ingress/gateways, propagation lag, and keep-alive connections. Readiness flipping to NotReady also does not make **all existing connections disappear instantly**.

### Coordinating Two Kinds of Timeouts

If Spring Boot has:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

and the Pod has:

~~~yaml
terminationGracePeriodSeconds: 45
~~~

you still need to account for the total time of:

1. `preStop`.
2. Routing drain and in-flight request duration.
3. Spring shutdown phases (each phase has its own timeout).
4. Bean destruction: `@PreDestroy`, closing datasources, HTTP clients, brokers, files, etc.
5. Safety margin for CPU throttling, GC pauses, networking, and log flushing.

**There is no magic safe formula** like "`45 >= 20`, so everything definitely finishes". Multiple phases or slow cleanup can exhaust 45 seconds. Measure p95/p99 shutdown latency in staging and size budgets with appropriate headroom.

### Do Not Forget Signals to PID 1

In Linux containers, the runtime sends the stop signal to the main process / PID 1 (depending on runtime/image config). If PID 1 is a shell wrapper that does not forward TERM, the JVM may **never receive the signal as expected**.

Prefer the Dockerfile exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Or if a shell script entrypoint is required, hand off at the end of the script with:

~~~sh
exec java -jar /app/app.jar
~~~

With `exec`, the shell is replaced by the Java process; TERM reaches the JVM directly. With `sh -c "java -jar ..."` without explicit signal handling/forwarding, inspect who PID 1 is and verify actual signal delivery.

Note: some images/runtimes use an init process or signal proxy, changing behavior; never guess from the Dockerfile alone—verify the container process tree and events.

## 9. Why Can Ctrl+C and SIGTERM Differ Under Gradle, IDEs, or Windows?

A `java -jar app.jar` command run directly has a different signal path than:

- `./gradlew bootRun` (Gradle has its own process and may fork a child JVM).
- IDE Stop button (may send a signal, terminate the process, or force-kill).
- Windows PowerShell/cmd/terminals using console control events rather than Unix signals.
- Docker/Kubernetes sending TERM to the container's main process.
- Windows service managers, systemd, or another process supervisor.

A UI "Stop" action **is not guaranteed** to be equivalent to `SIGTERM`. For instance, when an IDE force-kills the JVM, you may never see `@PreDestroy` even with correct code.

To diagnose:

1. Identify the **real JVM PID**, not Gradle's, a wrapper's, or a supervisor's PID.
2. Verify which signal or termination command the tool actually sends.
3. Observe Spring shutdown lifecycle logs and resource metrics before/after.
4. Run the JAR directly as a control.
5. Repeat in the target deployment environment rather than assuming production matches local.

**Do not pass `-Xrs` lightly** when relying on JVM signal handling, because it reduces the JVM's use of certain OS signals and can alter shutdown hook behavior. Test specific JVM flags and vendor behavior per environment.

## 10. Graceful HTTP Shutdown Does Not Mean All Background Jobs Finished

Web requests, message consumers, schedulers, executors, database transactions, and job queues have **distinct owners and completion conditions**.

| Component | What to handle on shutdown | Risk on SIGKILL |
|---|---|---|
| HTTP server | Stop new intake, give in-flight requests bounded time | Mid-request cutoffs, client retries. |
| `@Scheduled` jobs | Stop new triggers, handle running job | Job cut mid-run, next tick may be missed. |
| `@Async` / executor | Stop submissions, await/cancel workers at deadline | In-memory queue lost, incomplete tasks. |
| Kafka/Rabbit/message consumer | Stop intake, process then ack/commit per contract | Possible redelivery, duplicates, rebalancing. |
| JDBC transactions | Commit/rollback at clear boundaries, no unbounded holds | In-flight transactions may abort/rollback or leave clients unaware of outcome. |
| External HTTP calls | Timeouts, cancel/complete, idempotency | Remote side effects may succeed while caller never gets the response. |
| File exports | Flush/close and publish atomically where possible | Temporary or partial files left on disk. |
| Metrics/logging | Flush within bounded time | Loss of trailing logs/metrics, especially async buffers. |

A shutdown hook waiting 30 seconds for all work **does not guarantee** better shutdown. If the Pod deadline is only 20 seconds, infrastructure can kill the process before cleanup reaches critical steps.

Design **per-group time limits**: for instance, stop accepting events immediately, wait 10 seconds for in-flight tasks, then cancel or let a durable system retry. The right policy depends on data-loss tolerance, queue semantics, and idempotency.

### Avoid "Closing the Connection Pool Before Stopping Work"

A dangerous sequence:

~~~text
Close DataSource
     |
     v
Background worker still running SQL
     |
     v
SQLException / mid-transaction failure
~~~

If producer/consumer beans have complex lifecycles, use `SmartLifecycle.getPhase()` or explicit dependency management. On start, lower-phase components start before higher-phase ones; on stop, higher-phase components stop before lower-phase ones. However, explicit dependencies can alter order, and bean destroy callbacks follow their own semantics.

Never rely on **ordering among independent JVM shutdown hooks** to orchestrate closing Spring services.

## 11. Designing Workloads to Survive Forced Kills

Because `SIGKILL` can strike mid-task, cleanup cannot be the only line of defense. These principles matter more than "promising everything always finishes before exit":

### 11.1 Idempotency

If a client gets no response because the server was killed, the client may retry. Operations like creating a payment or sending an email must use an **idempotency key** or duplicate-prevention mechanism.

Example:

~~~text
Client -> POST create transaction (idempotency-key=abc)
Server sends processing request downstream
Server is killed before returning HTTP response
Client retries with the same key
System recognizes key was already processed or in progress
No duplicate transaction created
~~~

This is an illustrative flow; real implementations require **durable idempotency state storage** and concurrency control, not an in-JVM `ConcurrentHashMap`.

### 11.2 Ack/Commit After Durable Persistence

For message queues:

~~~text
Receive message
   |
   v
Process business logic with transaction/idempotency
   |
   v
Commit result durably
   |
   v
Ack/commit offset per broker semantics
~~~

If you ack before persisting data durably, a force-kill after ack can lose work. If business state commits yet a kill happens before ack, the broker may redeliver, so processing logic must tolerate duplicates.

Never claim "exactly once" solely from using transactional code or `@PreDestroy`: understand the contracts of the broker, database, and external side effects.

### 11.3 Checkpoints and Resumption

For batch imports/exports:

- Assign a job ID and durable state.
- Save checkpoints after each batch or stage.
- On restart, resume or retry from the committed checkpoint.
- Use temporary files, integrity checks, and atomic rename/publish steps to avoid releasing partial files.
- Never rely solely on an executor's in-memory state.

### 11.4 Timeouts and Cancellation

Never use `Thread.sleep(9999999)` or untimed I/O calls during cleanup. Tasks should know the remaining deadline, stop accepting new work, and cooperate with interruption when asked to stop.

However, Java interruption **is not SIGKILL**. Interruption is a cooperative thread-level signal; OS SIGKILL terminates the process without waiting for tasks to react.

## 12. Common Mistakes

**Mistake 1 — "SIGTERM is SIGKILL; neither can run cleanup."** Wrong. TERM is a soft signal the JVM can handle; KILL cannot be caught or handled by the application.

**Mistake 2 — "Ctrl+C is always equivalent to kill -9."** Wrong. In standard Unix terminals, Ctrl+C generates SIGINT and the JVM runs shutdown hooks. IDEs/wrappers/Windows may differ.

**Mistake 3 — "Having `@PreDestroy` guarantees closing when the process dies."** No. Callbacks execute only if the Spring context goes through a valid close sequence; forced kills offer no guarantee.

**Mistake 4 — "`finally` always runs, even on SIGKILL."** Wrong. SIGKILL can interrupt the JVM mid-bytecode without letting threads unwind stacks.

**Mistake 5 — "Shutdown hooks run in registration order."** No. Java does not guarantee order, and hooks may run concurrently. To order beans, use Spring lifecycle.

**Mistake 6 — "Just setting `spring.lifecycle.timeout-per-shutdown-phase=20s` guarantees the JVM exits within 20 seconds."** Wrong. It is a **per-phase** budget, excluding `preStop` and other steps.

**Mistake 7 — "A 10-second `preStop` adds 10 extra seconds to Kubernetes grace period."** Wrong. `preStop` consumes the same total grace period.

**Mistake 8 — "Using `sh -c java -jar` always delivers SIGTERM to the JVM."** No. The shell may be PID 1 and fail to forward signals as expected; use exec form, explicit `exec`, or a suitable init/supervisor.

**Mistake 9 — "Graceful shutdown lets all running requests finish indefinitely."** No. Timeouts, client disconnects, and force-kill risks still exist.

**Mistake 10 — "`System.exit` and `SpringApplication.exit` are identical."** No. `SpringApplication.exit` closes the context and returns an exit code; `System.exit` starts JVM shutdown.

**Mistake 11 — "Kubernetes deleting a Pod means all connections drop instantly."** Not quite. Endpoint status/draining and active connections behave differently; verify ingress and graceful HTTP server behavior.

**Mistake 12 — "After SIGKILL, the OS closes no resources at all."** Inaccurate. The OS reclaims many local process resources, yet business state, remote side effects, partial files, and message acks are not guaranteed to finish.

**Mistake 13 — "Just setting a huge `terminationGracePeriodSeconds` is enough."** No. A hung task still never finishes by itself. You need timeouts, recovery/idempotency, and sensible cleanup bounds.

**Mistake 14 — "`@Scheduled`/`@Async` uses one thread, so context close always waits for all tasks."** Incorrect. Behavior depends on executor/scheduler types, shutdown configs, queues, interruption, and remaining time.

## 13. Verification Procedure in Staging

Never test `kill -9` on production or processes you do not own. In an isolated staging deployment:

1. **Measure baseline:** in-flight requests, active JDBC connections, consumer lag, executor queued tasks, file descriptors, uptime.
2. **Send SIGTERM to the exact JVM PID:** verify the Spring context closes and cleanup callbacks run; measure duration from signal to process exit.
3. **Test Ctrl+C directly on the JAR:** compare with SIGTERM. Then test Gradle/IDE separately to observe differing signal paths.
4. **Run a bounded long request:** send TERM after the request is accepted; check whether it finishes within the grace period.
5. **Test container TERM and `preStop`:** verify the real JVM receives TERM, how much time `preStop` uses, and whether endpoints drain.
6. **Test forced termination past deadline:** in a lab, send SIGKILL and verify the system restarts cleanly and detects/retries incomplete work.
7. **Inspect persistence:** job tables, queue acks, idempotency keys, temp files, DB transactions. Do not look only at `@PreDestroy` logs.
8. **Measure shutdown tail latency:** p50/p95/p99 of stop duration, including GC pauses, CPU throttling, and network timeouts.
9. **Review total budget:** Spring shutdown phases + `preStop` + application cleanup + orchestrator budget + buffer.
10. **Write automated integration tests:** terminate a child process with TERM, await with a timeout, verify logs/exit code/state; test forced kill separately and verify recovery.

### Exit Codes: Reference Only, Not Sole Proof

In many Unix shells, exit status **143** commonly corresponds to `128 + 15` for SIGTERM, and **137** commonly corresponds to `128 + 9` for SIGKILL. However, wrappers, shells, JVMs, container runtimes, custom exit codes, and termination mechanisms can change observed values.

Never conclude "OOMKilled" solely from seeing exit code 137; inspect Kubernetes container state, reason, events, and memory pressure. Likewise, never conclude cleanup finished solely because the process returned exit code 0.

## 14. Operational Checklist

- Every Spring `ApplicationContext` has an owner and is closed at end of life.
- Do not disable `SpringApplication`'s JVM shutdown hook without a valid reason and reliable replacement.
- Keep `@PreDestroy`/destroy methods brief, idempotent, bounded by timeouts, and error-handled sensibly.
- `SmartLifecycle.stop(Runnable)` calls the callback only after stopping truly finishes per contract.
- Coordinate order: stop new requests/messages first, stop workers before closing shared dependencies.
- Configure `server.shutdown=graceful` on web servers when request draining is needed in Spring Boot 3.3.
- Treat `spring.lifecycle.timeout-per-shutdown-phase` as a **per-phase** budget, not total lifecycle time.
- Size Kubernetes `terminationGracePeriodSeconds` for `preStop` + shutdown phases + cleanup + buffer, verified empirically.
- Ensure the Java process receives TERM properly: verify PID 1, entrypoint, signal forwarding, and IDE/process wrappers.
- Enforce timeouts on DB/HTTP/broker calls and never wait indefinitely during shutdown.
- Ensure critical tasks have persistence, retries, idempotency, checkpoints, and proper ack semantics for forced kills.
- Monitor signals, readiness/EndpointSlices, in-flight requests, active tasks, pool closures, and restart events.
- Test both SIGTERM/Ctrl+C **and** forced termination in isolated environments.

### Official Documentation References

- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — SpringApplication, Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — `SpringApplication#setRegisterShutdownHook`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Java 17 — Runtime, shutdown hooks and halt: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Kubernetes — Pod Lifecycle, Termination of Pods: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — Container Lifecycle Hooks / PreStop: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/

**Conclusion:** SIGTERM and Ctrl+C **normally give the JVM a chance** to close the Spring `ApplicationContext` and run `SmartLifecycle`/`@PreDestroy`; `SIGKILL`, `halt`, and sudden failures **do not guarantee** those steps. Spring graceful shutdown has timeouts, and Kubernetes enforces **one total grace period** including `preStop`. Safe systems combine **time-bounded cleanup** with **durable data, idempotency, and recovery when processes die mid-flight**.
