# Distinguishing IDE Stop, OS Signals, and Force-Terminated Processes

A Spring Boot application processing HTTP requests, writing data, running scheduled tasks, or consuming messages from a broker can be stopped in several ways: **clicking Stop in an IDE**, **Ctrl+C in a terminal**, **sending SIGTERM from the OS**, **docker stop/kubectl delete pod**, or **force-terminating via SIGKILL, taskkill /F, crashes, or power loss**. All of these can make the application “disappear”, yet **they do not share the same guarantees for Spring ApplicationContext, lifecycle callbacks, HTTP connections, and in-flight data**.

What must be separated are **three independent layers**:

1. **Who issued the stop command, and does it reach the actual JVM process?** The IDE, shell, container runtime, Kubernetes, or OS may send different signals/termination mechanisms.
2. **Do the JVM and Spring get an opportunity to close the app cleanly?** Shutdown hooks, `ContextClosedEvent`, `SmartLifecycle.stop`, `@PreDestroy`, and bean destruction can only run if the runtime permits them.
3. **Does the HTTP server wait for running requests to finish?** That is *graceful web-server shutdown*, which must be configured/verified according to the **Spring Boot version**, timeouts, and infrastructure.

**Core config for Spring Boot 3.3.x**:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

**Version note:** In Spring Boot **3.3**, enable graceful shutdown with `server.shutdown=graceful`. **Spring Boot 3.4 onward changed the default to graceful** (which can be disabled with `server.shutdown=immediate`). Never copy the “graceful by default” conclusion from newer Boot docs onto an unconfigured Boot 3.3 service. Setting the property explicitly here keeps test outcomes clear.

This lesson focuses on **Spring Boot 3.x, Java 17+, Spring MVC/Servlet, and embedded Tomcat**. Comparisons cover Jetty, Undertow, Reactor Netty, Docker, Linux/macOS, Windows, IDEs, and Kubernetes. It includes a runnable Java 17+ demo, a long HTTP request experiment, safe local-only stop commands, lifecycle callback examples, and a deployment checklist.

## 1. Learning objectives

After this lesson, you can:

- Explain how *graceful shutdown* differs from *immediate shutdown* and *forced termination*.
- Distinguish `Ctrl+C`, `SIGINT`, `SIGTERM`, `SIGKILL`, `System.exit`, `Runtime.halt`, and IDE Stop actions.
- Understand that **Spring Boot registers a shutdown hook by default**, yet the hook only helps if the JVM starts a valid shutdown sequence.
- Distinguish `ContextClosedEvent`, `SmartLifecycle.stop(Runnable)`, `@PreDestroy`, and shutdown phase ordering.
- Know why a bean being destroyed does not by itself prove an HTTP request finished sending its response.
- Configure `server.shutdown` and `spring.lifecycle.timeout-per-shutdown-phase` for Spring Boot 3.3.
- Run an experiment with an 8-second request, send `SIGTERM`, and inspect responses/logs; compare against `SIGKILL`.
- Understand Docker StopSignal, stop timeout, PID 1, and exec-form `ENTRYPOINT`.
- Understand Kubernetes `preStop`, `terminationGracePeriodSeconds`, readiness, EndpointSlices, and real drain times.
- Design queue consumers, DB transactions, cron jobs, SSE/WebSockets, and distributed work safely against crashes.
- Test differences across IDEs, terminals, containers, and orchestrators without relying on a single log line.

## 2. A comparison table before diving deep

| Stop method | Common command/mechanism | JVM shutdown hook? | Chance to run Spring callbacks? | Guaranteed HTTP requests finish? |
| --- | --- | --- | --- | --- |
| Click Stop in IDE | Depends on IDE/run configuration: sends signal or terminates process | **Uncertain** | **Uncertain** | **Uncertain**, must verify |
| Ctrl+C in Unix terminal | Usually sends `SIGINT` to foreground process group | Usually yes if JVM handles the signal | Usually yes | Only if context closes cleanly and graceful server/timeouts fit |
| Send `SIGTERM` on Unix | `kill -TERM PID` | Usually yes on standard JVMs | Usually yes | Not automatic if Boot/version/config does not support it |
| `System.exit(code)` | Java proactively initiates JVM shutdown sequence | Yes | Usually yes if Boot hook/context registered | Depends on server graceful mode and deadline |
| `ApplicationContext.close()` | Closes Spring context directly | Does not need JVM hook | Yes in the closed context | Possibly, though the JVM may not exit |
| `docker stop` | Sends stop signal (usually TERM), then KILL if expired | If signal reaches JVM and time remains | Has a chance | Depends on Docker and Boot timeouts |
| Kubernetes pod termination | `preStop`, TERM, then KILL on grace expiry | Has a chance | Has a chance | Depends on drain, remaining time, and app |
| `kill -9`/`SIGKILL` | Kernel forces Unix process termination | **No** | **No** | **No** |
| Default `docker kill` | Usually SIGKILL | **No** | **No** | **No** |
| `taskkill /F`/TerminateProcess on Windows | Forces process termination | No guarantee hooks run | No guarantee | No |
| `Runtime.halt(code)` | JVM halts immediately, no shutdown sequence | **No** | **No** | **No** |
| Crash/JVM fatal error/host power loss | No reliable shutdown window | Not guaranteed | Not guaranteed | No |

**Rule:** never equate a button label or command name with the real outcome. Verify **signal delivery to the JVM, Spring context close, HTTP drain, and persisted/ACKed data** in each environment.

## 3. Three layers of an application shutdown

Desired shutdown flow:

```text
Operator / orchestrator requests stop
                  |
                  v
JVM process receives TERM / shutdown trigger
                  |
                  v
JVM starts shutdown sequence
                  |
                  v
Spring Boot shutdown hook closes ApplicationContext
                  |
                  v
ContextClosedEvent and lifecycle stop phases
                  |
                  +--> Graceful web server:
                  |      stop accepting new requests,
                  |      give in-flight requests time to finish
                  |
                  +--> Stop workers / schedulers / consumers
                  |
                  v
Destroy managed beans (@PreDestroy, destroy())
                  |
                  v
JVM / process finishes and exits the system
```

The diagram is a **conceptual model**, not a promise that callbacks always print in one rigid log order on every server. `SmartLifecycle` phases have ordering while other hooks follow their own rules; multi-threaded logs can interleave.

If the sequence is cut off by `SIGKILL` or the orchestrator's allowed window expires, the remaining steps **are not guaranteed to run**. Systems must tolerate crashes rather than relying solely on shutdown callbacks to preserve data.

### 3.1. JVM shutdown sequence and Spring ApplicationContext

Per the Java Runtime, the JVM can initiate a shutdown sequence when:

- The program calls `System.exit`/`Runtime.exit`.
- No non-daemon threads remain alive (under suitable runtime conditions).
- An external event, such as an OS interrupt/signal handled by the runtime, arrives.

During the shutdown sequence, the JVM starts registered shutdown hooks; execution order among independent hooks **is not guaranteed**. Spring Boot `SpringApplication` sets `registerShutdownHook=true` by default to close `ApplicationContext` on normal JVM shutdown. Thus Spring-managed beans get a chance to run lifecycle/destruction callbacks.

**Conversely:** `SIGKILL` and `Runtime.halt` do not trigger the normal shutdown sequence; `finally`, try-with-resources, hooks, and `@PreDestroy` never get a chance to run. Distinguish *a signal handled by the JVM* from *a forced process kill*.

### 3.2. “Having a hook” does not mean “requests finish”

Suppose a Servlet request runs for 8 seconds when SIGTERM arrives. The JVM may invoke Spring context close and `@PreDestroy`, yet the HTTP server—if it stops immediately—can sever the socket. To give in-flight requests time to finish, you must enable and verify **graceful web-server shutdown** for your Boot version.

A database transaction also needs separate guarantees: connections can close, transactions can roll back, or the caller may not know whether the commit succeeded. Never use a `@PreDestroy invoked` log as proof that all business operations finished.

### 3.3. “Having a grace period” does not mean “waiting forever”

`spring.lifecycle.timeout-per-shutdown-phase=20s` is the **timeout per lifecycle shutdown phase**, not an SLA guaranteeing everything completes in 20 seconds. External factors include Docker timeouts, Kubernetes termination grace, load balancer draining, network propagation, and callback duration. If a phase expires, the framework proceeds with shutdown and active requests get cut off; if the orchestrator runs out of time, it force-kills the whole process.

## 4. Stopping from an IDE: Stop is not a protocol

When running Java via IntelliJ IDEA, Eclipse, VS Code, NetBeans, or another IDE, the **Stop/Terminate** button controls a process or process tree managed by the IDE. How it stops Java varies by:

- OS: Linux/macOS vs Windows;
- IDE version and Run/Debug configuration;
- Running `java -jar` directly vs Gradle `bootRun`, Maven `spring-boot:run`, or the debugger;
- Which console/process group holds the Java process;
- Whether the IDE tries a graceful stop on first click and force-kills on the next click;
- Whether the tool runs Java in a container, WSL, remote dev, or SSH.

**Never claim “IDE Stop always sends SIGTERM”.** Spring Boot 3.3 documentation warns that graceful shutdown inside an IDE may not work if the IDE does not send a proper SIGTERM.

### 4.1. IDE Stop, Debug Disconnect, and Force Terminate

- **Stop/Terminate**: requests stopping the process using the IDE's mechanism. May be graceful or abrupt; check docs and test.
- **Disconnect debugger**: only detaches the debug channel in some setups, leaving the Java process running.
- **Force stop/Kill**: typically terminates the process immediately with no hook guarantee.
- **Stop Gradle task**: if the IDE manages a Gradle daemon/launcher, it might not deliver the right signal to the app JVM. Inspect the process tree.

Similar-looking UI buttons do not necessarily share the same semantics. Never take the app disappearing from the Run panel as proof it closed cleanly.

### 4.2. How to verify your actual IDE

In a local test application:

1. Log `ContextClosedEvent` and `@PreDestroy`.
2. Enable web graceful shutdown for your Boot version.
3. Open a sufficiently long request.
4. Click Stop **once**; observe whether the request returns 200 or breaks, whether lifecycle logs appear, and whether the process stays alive during grace.
5. Repeat with Debug Stop and Force Terminate, noting differences.
6. Record the IDE version, JVM, OS, and launcher instead of trusting the button name.

**Avoid testing on production**: IDE shortcuts and remote debug commands are not tools for testing safe draining of live services.

## 5. Common Unix signals: TERM, INT, KILL

### 5.1. SIGTERM — request to terminate with a chance to clean up

`SIGTERM` is typically the default signal when running `kill PID` or `kill -TERM PID` on Linux/macOS. It asks the process to stop. On standard HotSpot JVMs with Spring Boot's shutdown hook registered, receiving TERM leads to closing `ApplicationContext` and running callbacks.

```bash
kill -TERM 12345
```

`12345` is a **dummy PID for illustration**; obtain the exact PID of your test JVM and stop only your own process. Use `ps` or `jps -l` to find it. Never run illustrative PIDs blindly on a real machine.

TERM can be intercepted differently by wrapper scripts, blocked/unforwarded, or fail to reach the JVM. If the JVM is a child of a shell in a container, the signal may hit the shell rather than Java. In every case, the real question is **did the JVM start its shutdown sequence and close the Spring context?**

### 5.2. SIGINT — usually from Ctrl+C in a terminal

In a Unix terminal, pressing `Ctrl+C` normally sends `SIGINT` to the foreground process group. For typical Java apps, it initiates the shutdown sequence and runs Spring hooks similarly to TERM.

However, `Ctrl+C` is not a signal name with identical behavior across every OS/tool: on Windows consoles it is a console control event; inside IDEs or embedded terminals another process layer may intercept it. If Java runs via Gradle/Maven, signals can hit launchers and the app JVM in process-dependent ways.

### 5.3. SIGKILL — forced kill, cannot be caught or delayed

`SIGKILL`, typically `kill -9 PID`, is enforced by the kernel. Applications cannot use Java handlers or `finally` blocks to run beforehand. It does **not** run JVM shutdown hooks, `ContextClosedEvent`, `@PreDestroy`, or graceful HTTP drain through normal channels.

```bash
kill -KILL 12345
```

Use this command **only in a local lab** against a verified PID; never use it to stop real data-handling services when gentler alternatives exist.

### 5.4. Exit codes do not prove cleanup succeeded

Unix/shells/containers often follow exit code conventions like `128 + signal number`: 130 for SIGINT, 143 for SIGTERM, 137 for SIGKILL. Yet this is a convention depending on wrappers/shells/runtimes/orchestrators, **not independent proof** that hooks ran or requests completed.

For instance, a container may receive TERM, run partial cleanup, and then get KILLed on timeout, reporting exit 137. Conversely, a Java process could call `System.exit(143)` without ever receiving SIGTERM. Inspect timelines, events, logs, metrics, and request outcomes.

## 6. Java System.exit, Runtime.halt, and closing the Spring context

### 6.1. System.exit initiates the JVM shutdown sequence

```java
System.exit(0);
```

In Java, `System.exit` invokes `Runtime.exit` to start the shutdown sequence. Shutdown hooks run; the Spring context, if hooked, gets a chance to close. This is **not** an API to invoke directly from a production controller to shut down the server: a single request could kill the JVM mid-transaction without proper draining, auth, or audit.

A Spring batch/CLI app sometimes uses:

```java
ConfigurableApplicationContext ctx =
        SpringApplication.run(BatchApplication.class, args);

int exitCode = SpringApplication.exit(ctx);
System.exit(exitCode);
```

This is a **snippet for a batch application**, requiring imports and the `BatchApplication` class in the project. `SpringApplication.exit(ctx)` closes the Spring context and computes an exit code from `ExitCodeGenerator`/exception logic; `System.exit` then exposes process exit to the OS. Do not copy this snippet into a REST controller or an app actively serving requests.

### 6.2. ApplicationContext.close does not always terminate the JVM

```java
context.close();
```

This closes the Spring context and managed beans regardless of whether the JVM received TERM. Yet the OS process can stay alive if non-daemon threads remain. That is why we distinguish **Spring context lifecycle** from **OS process lifecycle**.

### 6.3. Runtime.halt bypasses shutdown hooks

```java
Runtime.getRuntime().halt(1);
```

This is a **counter-example of forced termination**, not for use in server demos or normal production shutdowns. It halts the JVM immediately without waiting for hooks/cleanup. Understand it only to see why `finally` and `@PreDestroy` are not durable contracts when a process dies abruptly.

### 6.4. A standalone Java 17 probe separating the JVM from Spring

Create `ShutdownSignalProbe.java`:

```java
import java.util.concurrent.CountDownLatch;

public final class ShutdownSignalProbe {

    public static void main(String[] args)
            throws InterruptedException {

        Runtime.getRuntime().addShutdownHook(
            new Thread(
                () -> System.out.println("JVM_SHUTDOWN_HOOK"),
                "demo-shutdown-hook"
            )
        );

        System.out.println(
            "READY pid=" + ProcessHandle.current().pid()
        );

        new CountDownLatch(1).await();
    }
}
```

Run with Java 17+:

```bash
javac ShutdownSignalProbe.java
java ShutdownSignalProbe
```

Output before stopping looks like:

```text
READY pid=12345
```

The PID changes. On Linux/macOS, send SIGTERM to the exact PID from another terminal: normally `JVM_SHUTDOWN_HOOK` prints before the JVM exits. If you force `SIGKILL`, the hook line will not appear via normal shutdown. On Windows, Ctrl+C/process termination depends on the console and OS.

**This demo does not prove HTTP graceful shutdown**, as it creates no Spring context or web server. It isolates the JVM hook layer so you can observe the mechanism.

## 7. Spring Boot lifecycle: ContextClosedEvent, SmartLifecycle, and @PreDestroy

When `ApplicationContext` closes normally:

1. Spring emits `ContextClosedEvent` so listeners know the context is about to close.
2. Lifecycle processor stops `Lifecycle`/`SmartLifecycle` beans by phases and dependencies.
3. Spring destroys singleton beans, calling `@PreDestroy` and matching callbacks such as `DisposableBean.destroy()` or custom destroy methods.
4. Components outside the JVM may have already begun pulling traffic or not finished yet; never deduce network outcomes from event order alone.

### 7.1. @EventListener(ContextClosedEvent.class)

```java
@Component
public class ShutdownTrace {
    private static final Logger log =
            LoggerFactory.getLogger(ShutdownTrace.class);

    @EventListener(ContextClosedEvent.class)
    public void onClosing() {
        log.info("LIFECYCLE_CONTEXT_CLOSING");
    }

    @PreDestroy
    public void beforeDestroy() {
        log.info("LIFECYCLE_BEAN_DESTROY");
    }
}
```

This is a **class snippet** missing imports; the full runnable program is in section 9. It uses these imports:

```java
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
```

The `ContextClosedEvent` log shows a Spring context is closing; `@PreDestroy` shows the bean is being destroyed by the container. Neither is called on SIGKILL, and neither confirms how many jobs/messages finished.

### 7.2. SmartLifecycle and phase order

`SmartLifecycle` fits workers/schedulers/consumers with clear lifecycles:

```java
@Component
public class ExampleWorkerLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            // Stop accepting new work and finish running work
            // per application policy (illustrative snippet).
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
        return 0;
    }
}
```

This is a **snippet** needing imports `AtomicBoolean`, `SmartLifecycle`, `@Component` inside a project; the “stop work” body is unimplemented because it depends on the message broker. Do not treat it as a complete queue draining implementation.

Core rules:

- Startup runs from **low → high** phase; shutdown runs from **high → low**.
- `depends-on` relationships affect order, taking precedence over phases when applicable.
- `stop(Runnable callback)` must call `callback.run()` when stopping completes. Omitting it can make the lifecycle processor wait until timeout.
- Each phase has a timeout; `timeout-per-shutdown-phase` does not mean the whole application shutdown shares one global timer.
- During startup failures or abnormal shutdowns, do not rely strictly on assuming `stop` always runs before destroy. Cleanup callbacks should be idempotent.

Spring Boot graceful web-server shutdown participates in lifecycle stop phases; its goal is to stop admitting new requests and give running requests time to complete. The application may also have schedulers, Kafka consumers, job threads, WebSocket sessions, and connection pools needing separate lifecycles.

### 7.3. Shutdown hooks must not block indefinitely

Avoid sleeping 10 minutes or waiting endlessly on a queue in `@PreDestroy`. The orchestrator can KILL the process before it finishes. Cleanup should be fast, bounded, and have explicit timeouts: stop accepting work, perform necessary flushes, release resources, and record metrics.

To ensure events/payments are never lost, use persistent transactions, durable queues, and idempotency instead of hoping the JVM always gets enough time to close cleanly.

## 8. Spring Boot 3.3: graceful HTTP shutdown

Per [Spring Boot 3.3 Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html), Spring Boot supports graceful shutdown with embedded **Tomcat, Jetty, Reactor Netty, and Undertow** on Servlet/reactive stacks. When the application context closes, the web server enters a shutdown phase where it **stops accepting new requests** and gives **running requests** a chance to finish within the configured duration.

### 8.1. Two key properties

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

- `server.shutdown=graceful`: enables web server request draining mode for Boot 3.3.
- `spring.lifecycle.timeout-per-shutdown-phase=20s`: timeout per lifecycle stopping phase. Tune to request durations and infrastructure budgets.

With `server.shutdown=immediate`, the context still closes and `@PreDestroy` still runs, **yet the web server does not gracefully wait for in-flight requests**. This separates “Spring cleanup” from “HTTP draining”.

### 8.2. Default differences by version

| Version | Notable default state | Lesson recommendation |
| --- | --- | --- |
| Spring Boot 3.3.x | Graceful web shutdown not enabled by default; set `server.shutdown=graceful` to activate | Declare the property explicitly |
| Spring Boot 3.4+ | Graceful web-server shutdown enabled by default per 3.4 release notes | Still check/tune timeouts |
| Newer Spring Boot | Newer docs may alter defaults/details by server | Read docs matching the deployed version |

Do not project newer Boot docs onto older binaries. Do not blindly change property names based on a random snippet without checking your dependency tree.

### 8.3. Servers reject new requests differently

Per Spring Boot 3.3 docs:

- Tomcat, Jetty, and Reactor Netty stop accepting new requests at the network layer.
- Undertow may still accept connections yet return HTTP **503 Service Unavailable** during graceful shutdown.
- Persistent keep-alive connections can behave differently from opening fresh TCP connections.
- A new request during drain may see connection refused/reset, 503, or another response depending on server/proxy; **there is no single HTTP status across every stack**.

Do not write tests requiring “every new request receives 503” on Tomcat because it may **not even accept the connection**.

### 8.4. Requests already started do not always finish

If a request takes 30 seconds while the web-server phase timeout is 20 seconds, graceful shutdown can end at expiry; the request is cut off, the client sees an error, and the app shuts down. If Docker only grants 10 seconds before SIGKILL, Boot's 20 seconds never gets a full 20 seconds either.

Pick timeouts matching real traffic, enforce max request durations, support cancellation, and design retries. Graceful shutdown does not solve slow clients, infinite streams, lost tasks, or network faults.

### 8.5. SSE, WebSocket, and long polling need separate policies

An SSE stream or WebSocket can live for hours. You cannot wait for these connections to finish naturally during every rolling deployment:

- Mark the instance draining and stop creating new subscriptions.
- Proactively send an application-level signal so clients reconnect/resubscribe when appropriate.
- Close active streams/sockets within budget, cleaning up subscriber maps/brokers.
- Clients reconnect with backoff/jitter and resume from a cursor if zero data loss is needed.
- Never rely on an HTTP 200 or `@PreDestroy` to conclude an entire event stream completed.
- Streaming requests can hold graceful shutdown until timeout; measure connection lifetimes and cancellation.

## 9. Runnable Java 17+ Spring Boot project to observe shutdown

Demo includes:

- `GET /quick`: immediate response.
- `GET /work?seconds=8`: a blocking HTTP request with configurable processing time.
- `ShutdownTrace`: logs context close and bean destruction.
- `ExampleLifecycle`: prints lifecycle start/stop and invokes the callback per contract.
- Actuator health/readiness for local observation.
- Properties enabling 20-second graceful shutdown.

The example **has no authentication, DB, Kafka, or real queue**. Use it locally or in an isolated container; never deploy it as a public service. `Thread.sleep` in the handler is just a tool to create an observable slow request; production must not wastefully block servlet threads like this.

### 9.1. Create the project

Use [Spring Initializr](https://start.spring.io/) or create a Gradle project for **Java 17 + Spring Boot 3.3.13**. In `settings.gradle`:

```groovy
rootProject.name = 'shutdown-lab'
```

Minimal complete `build.gradle` core config:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Initializr provides `gradlew`, `gradlew.bat`, and `gradle/wrapper`. If creating an empty directory manually without the Gradle Wrapper, generate the wrapper using a compatible Gradle version, or generate from Initializr and replace the files. Do not assume `gradlew` exists in a folder containing only `build.gradle`.

Structure:

```text
settings.gradle
build.gradle
gradlew
gradlew.bat
gradle/wrapper/...
src/
  main/
    java/demo/
      ShutdownLabApplication.java
      SlowController.java
      ShutdownTrace.java
      ExampleLifecycle.java
    resources/
      application.properties
  test/
    java/demo/
      SlowControllerTest.java
```

### 9.2. ShutdownLabApplication.java

File `src/main/java/demo/ShutdownLabApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownLabApplication.class, args);
    }
}
```

In Boot 3.3, `SpringApplication` registers a shutdown hook for the context by default. No need to call `Runtime.getRuntime().addShutdownHook(...)` manually just so Spring runs `@PreDestroy`; adding extra hooks complicates ordering and ownership.

### 9.3. SlowController.java: bounded request long enough to test

File `src/main/java/demo/SlowController.java`:

```java
package demo;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SlowController {

    private static final Logger log =
            LoggerFactory.getLogger(SlowController.class);

    @GetMapping("/quick")
    public String quick() {
        return "quick-ok\n";
    }

    @GetMapping("/work")
    public ResponseEntity<String> work(
            @RequestParam(defaultValue = "8") int seconds) {

        if (seconds < 0 || seconds > 25) {
            return ResponseEntity.badRequest()
                    .body("seconds must be between 0 and 25\n");
        }

        log.info("WORK_START seconds={}", seconds);

        try {
            TimeUnit.SECONDS.sleep(seconds);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            log.warn("WORK_INTERRUPTED");
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted\n");
        }

        log.info("WORK_DONE seconds={}", seconds);
        return ResponseEntity.ok("work-done\n");
    }
}
```

**Explanation:**

- `/quick` returns a fixed string for manual probing.
- `/work?seconds=8` blocks a servlet worker thread for 8 seconds so we can see a running request when the JVM receives TERM.
- Limiting 0..25 seconds prevents the test endpoint from becoming an infinite sleep; never expose it to the public Internet.
- `WORK_START` and `WORK_DONE` distinguish server-side processing from the HTTP outcome at the client.
- If the thread is interrupted, the code returns 503; this does not guarantee the response can always be sent successfully while shutting down.
- **WORK_DONE does not prove the client received all bytes**: serialization/writing and network transfer still follow.
- No database is included; to test commits/rollbacks, add a dedicated transaction test.

### 9.4. ShutdownTrace.java: two kinds of callbacks

File `src/main/java/demo/ShutdownTrace.java`:

```java
package demo;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownTrace {

    private static final Logger log =
            LoggerFactory.getLogger(ShutdownTrace.class);

    @EventListener(ContextClosedEvent.class)
    public void onClosing() {
        log.info("LIFECYCLE_CONTEXT_CLOSING");
    }

    @PreDestroy
    public void beforeDestroy() {
        log.info("LIFECYCLE_BEAN_DESTROY");
    }
}
```

`ContextClosedEvent` is only emitted when the context closes via the framework path; `@PreDestroy` only runs if Spring reaches the bean destruction stage. When the process gets SIGKILLed, do not expect either line.

### 9.5. ExampleLifecycle.java: SmartLifecycle demo

File `src/main/java/demo/ExampleLifecycle.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class ExampleLifecycle implements SmartLifecycle {

    private static final Logger log =
            LoggerFactory.getLogger(ExampleLifecycle.class);

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
        log.info("LIFECYCLE_WORKER_STARTED");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            log.info("LIFECYCLE_WORKER_STOPPED");
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
        return 0;
    }
}
```

This bean runs no real background task; it illustrates startup/stop callbacks. For a real queue consumer, `stop(Runnable)` must stop accepting messages, wait with a limit for running work, commit/ACK per protocol, and only then invoke the callback. If the callback is omitted, the lifecycle processor may wait until the phase timeout.

`getPhase()=0` is just a demo choice; web server graceful shutdown uses a Boot-managed phase. Do not hardcode log line order across multiple components relying on one phase number when dependencies or framework updates exist.

### 9.6. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Explicit for Spring Boot 3.3.x
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Enable health probes in local lab.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never

logging.level.demo=INFO
```

**No need to enable the Actuator shutdown endpoint.** It is disabled by default because it can stop the app over HTTP. Never add `management.endpoint.shutdown.enabled=true` or expose `shutdown` merely to replace TERM; exposing a destructive operational endpoint requires very strict identity/network/audit controls.

### 9.7. Build and run

In the project root containing the Gradle Wrapper:

```bash
./gradlew clean bootJar
```

Windows:

```powershell
.\gradlew.bat clean bootJar
```

The JAR is expected at `build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar` when `settings.gradle` and `version` match the listing. On Linux/macOS, run the JVM process directly:

```bash
java -jar build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar
```

Wait for the app to start. Logs show lines similar to `LIFECYCLE_WORKER_STARTED` and server listening on port 8080; other Spring Boot lines depend on the environment. Use `java -jar` directly so signals reach the **app JVM**, rather than killing the Gradle daemon PID and drawing conclusions about Spring.

### 9.8. Quick HTTP check

Second terminal:

```bash
curl -i http://localhost:8080/quick
curl -i 'http://localhost:8080/work?seconds=1'
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

`GET /quick` returns body:

```text
quick-ok
```

`GET /work?seconds=1` returns:

```text
work-done
```

Health probes usually return `UP` when ready, though status/HTTP code may change when stopping, unready, or failing. If probes are missing, check the Actuator dependency/properties rather than assuming routes are enabled in every environment.

## 10. Experiment A: sending SIGTERM while an HTTP request is running

### 10.1. Prepare terminals

**Terminal A:** run the JVM as in section 9.7, keeping it running.

**Terminal B:** open an 8-second request:

```bash
curl -v --no-buffer 'http://localhost:8080/work?seconds=8'
```

Server logs once controller starts:

```text
WORK_START seconds=8
```

**Terminal C:** find the exact Java PID:

```bash
jps -l
```

`jps` is a JDK tool and is not always present in JRE-only images. You can use `ps -ef` and verify the command line contains `shutdown-lab-0.0.1-SNAPSHOT.jar`. Once confirmed, send:

```bash
kill -TERM 12345
```

**`12345` is an illustrative PID; replace it with the verified actual PID**. This action is for a local app you own; never run it on production.

### 10.2. Expected result when the request fits within the grace period

With Boot 3.3 `server.shutdown=graceful`, ~6–8 seconds remaining, and a 20-second phase timeout, the app **has a chance** to return 200/`work-done` for `/work` before context close finishes.

Server may log:

```text
WORK_START seconds=8
LIFECYCLE_CONTEXT_CLOSING
... graceful shutdown commencing ...
WORK_DONE seconds=8
... graceful shutdown complete ...
LIFECYCLE_WORKER_STOPPED
LIFECYCLE_BEAN_DESTROY
```

This is an **illustration of events**, not a guarantee of exact log order/line count/wording. `SmartLifecycle` phases, server logs, and threads can alter the order. What must be verified:

1. Did the request start before TERM?
2. Did the JVM receive TERM and the Spring context start closing?
3. Did the controller reach `WORK_DONE`?
4. Did the client genuinely receive HTTP 200 and the complete body?
5. Did the process exit within the orchestrator/OS timeout?
6. Were any new requests accepted after drain started?

**Important:** if the server returns a reset for a new request during drain, that is not necessarily a bug. Tomcat usually stops accepting at the network layer without promising 503.

### 10.3. When the request exceeds the grace period

Keep `spring.lifecycle.timeout-per-shutdown-phase=20s`, then call:

```bash
curl -v --no-buffer 'http://localhost:8080/work?seconds=25'
```

Send SIGTERM right after the request starts. The request can be cut off when the phase expires; the client may see connection reset/empty reply or another error, with no guarantee of a 503 response. Some code may keep running inside the JVM until the process stops; **never treat WORK_DONE as proof the client received the body**.

Because the sample caps `seconds` at 25, this test lets you observe timeout without creating an infinite request. When testing, disable polling health dashboards if they clutter logs.

### 10.4. Verifying launcher-induced anomalies

If running with:

```bash
./gradlew bootRun
```

then the PID of `gradlew`/Gradle daemon is not necessarily the PID of the Java web app, especially when the build tool forks a JVM. Sending TERM to the Gradle wrapper can stop the app differently. For accurate signal experiments, use `java -jar` directly or inspect the PID tree and actual results.

## 11. Experiment B: SIGKILL and the boundary where cleanup cannot run

Restart the app in a fresh terminal. Open a long request:

```bash
curl -v --no-buffer 'http://localhost:8080/work?seconds=8'
```

In another terminal verify the PID, then send **only against your local demo process**:

```bash
kill -KILL 12345
```

When the kernel forces the JVM to stop:

- The client usually loses connection before receiving the full body.
- Do not expect `LIFECYCLE_CONTEXT_CLOSING`, `LIFECYCLE_WORKER_STOPPED`, or `LIFECYCLE_BEAN_DESTROY`.
- There is no HTTP graceful drain.
- The app cannot run `finally`, `@PreDestroy`, or Java shutdown hooks to finish work.
- Log buffers may remain unflushed; absence of a log line **does not prove** whether code ran before termination.

What matters is **designing crash-tolerant data flows**, because production can hit OOMKill, node failures, forced rollouts, disk/CPU faults, or power loss. Graceful shutdown lowers interruption probability in normal scenarios; it does not replace transactions, retries, and idempotency.

### 11.1. Never run SIGKILL experiments against real data

Keep tests inside the demo project with in-memory state and zero external dependencies. To test databases/queues, use sandboxes, fixtures, and scoped accounts; force-killing a live payment processor or production consumer can cause duplicates or lost ACKs.

## 12. Experiment C: IDE Stop and Windows

### 12.1. IDE on Linux/macOS

Open the project in your IDE, run `ShutdownLabApplication`, and start `/work?seconds=8` from a terminal. Click Stop once and compare:

| Observation | What you can infer | What you cannot conclude yet |
| --- | --- | --- |
| `ContextClosedEvent` present | Spring context started closing | All HTTP responses finished |
| `@PreDestroy` present | Bean destroyed by Spring | Zero requests were interrupted |
| Request returned full 200 | One request completed | All requests/jobs completed |
| App vanished from IDE | IDE stopped managing the process | JVM completed sufficient cleanup |
| Missing shutdown logs | Possibly abrupt termination or unflushed logs | Exact signal unknown without inspecting PID/OS logs |

Some IDE Stop buttons send TERM when conditions allow, while others force-terminate or kill the process tree. Under debugging, Stop/Disconnect also behave differently. Document your test environment: IDE version, OS, JDK, launcher, Spring Boot version, and network outcomes.

### 12.2. Windows consoles do not behave identically to Unix signals

On Windows, `Ctrl+C` is a console control event; Java shutdown hooks depend on the JVM and how the console/tool delivers events. PowerShell `Stop-Process` or `taskkill /F` can terminate a process **without** letting Spring run graceful close. Never equate a Windows command named “stop” with `kill -TERM`.

To test, run in PowerShell:

```powershell
java -jar build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar
```

In another PowerShell window:

```powershell
curl.exe -i "http://localhost:8080/work?seconds=8"
```

Press Ctrl+C in the console **running Java**, observe logs and the HTTP response. Then restart and test IDE Stop or `Stop-Process` against the **exact demo PID**. If it terminates abruptly without `@PreDestroy`, record that as the behavior of that termination method.

### 12.3. Do not draw conclusions from process exit codes

Windows Process Exit Codes and Unix exit statuses have no uniform mapping. Codes 137/143 are Linux container/shell conventions; do not apply them directly to Windows. What matters more are the timeline, application events, and data correctness after restart.

## 13. Docker stop: TERM → wait → KILL

Docker has two easily confused actions:

- `docker stop`: sends a **stop signal** to the container's main process (default usually SIGTERM), waits a configured period, and then sends SIGKILL if it hasn't stopped.
- `docker kill`: sends **SIGKILL** immediately by default, unless another signal is specified.

Docker timeouts are not Spring Boot timeouts. For Linux containers, the Docker daemon typically defaults to **10 seconds** when no other stop-timeout is set; Windows containers have different defaults. If `spring.lifecycle.timeout-per-shutdown-phase=20s` while Docker force-stops after 10 seconds, a 15-second request cannot be expected to complete.

### 13.1. Dockerfile exec-form ENTRYPOINT

After building the JAR in section 9, create `Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Exec form** makes the JVM the main process in the container so it receives stop signals directly from the runtime. Avoid shell form:

```dockerfile
# Not recommended when explicit signal forwarding is needed:
ENTRYPOINT java -jar /app/app.jar
```

With shell form, the shell can become PID 1 and fail to forward TERM to the child Java process as expected. If a shell script entrypoint is mandatory, the script should run `exec java -jar ...` to replace the shell with the JVM, while handling PID 1/process reaping per environment.

### 13.2. Running and stopping the lab container

```bash
docker build -t shutdown-lab:dev .
docker run -d --name shutdown-lab -p 8080:8080 shutdown-lab:dev
docker logs -f shutdown-lab
```

In another terminal open `/work?seconds=8`, then run:

```bash
docker stop --time 25 shutdown-lab
```

With a 25-second timeout, Spring Boot's 20-second phase usually has enough time compared to the 10-second default, though if multiple lifecycle phases or pre/post work take longer, you must still measure. `docker logs` reveals lifecycle events; `curl` reveals whether the client received the body.

Once stopped:

```bash
docker rm shutdown-lab
```

To observe the forced difference, recreate the demo container, start a new request, and run `docker kill shutdown-lab`. **Test only on self-created containers**; never kill shared infrastructure or real databases.

### 13.3. docker compose also has its own stop timeout

Compose supports `stop_grace_period` to tune the wait before force-killing, and `stop_signal` to select the signal. Example snippet:

```yaml
services:
  api:
    image: shutdown-lab:dev
    ports:
      - "8080:8080"
    stop_signal: SIGTERM
    stop_grace_period: 35s
```

This is a **compose snippet**; unneeded if running Docker CLI as above. Increasing the timeout while keeping a shell-form entrypoint that fails to forward TERM still prevents the JVM from receiving the signal. You need both the signal path and the grace budget.

### 13.4. PID 1 and Java apps

Inside containers, PID 1 has special signal/reaping semantics to account for. Running Java directly via exec-form ENTRYPOINT clarifies the signal path; if using a process supervisor/tini, verify it forwards signals and reaps children. Never use `sh -c "java -jar ..."` hoping Docker magically finds the child Java process to send TERM.

## 14. Kubernetes: preStop, TERM, and terminationGracePeriodSeconds

When a Pod is deleted/replaced during a rollout, kubelet tries to stop containers cleanly:

```text
Pod marked terminating
                |
                v
EndpointSlice / Service routing updates asynchronously
                |
                v
Kubelet runs preStop hook (if configured)
                |
                v
Container runtime sends TERM to container process
                |
                v
JVM / Spring Boot graceful shutdown
                |
                v
Process exits before deadline?
          /                   \
        Yes                    No
        |                       |
        v                       v
   Pod finishes            Runtime sends KILL
```

**Kubernetes's grace timer includes preStop time**, rather than adding it completely after preStop. Default `terminationGracePeriodSeconds` is **30 seconds** if left uncustomized. If `preStop` sleeps 10 seconds out of a 30-second deadline, the JVM has around 20 seconds or less to clean up.

Kubelet sometimes grants a very brief extension if preStop is still running at grace expiry, yet you should never rely on that as shutdown budget.

### 14.1. Example Deployment snippet

This is a **manifest illustrating shutdown-related fields**; add registry, image pull secrets, and policies for real use:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shutdown-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shutdown-lab
  template:
    metadata:
      labels:
        app: shutdown-lab
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: api
          image: registry.example.test/shutdown-lab:dev
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
```

The example provides 40 seconds termination grace, of which `preStop` uses ~5 seconds. The app sets `spring.lifecycle.timeout-per-shutdown-phase=20s`, leaving the rest for JVM stop and overhead. **40s is only a demo number**, not a universal recommendation for every service; measure p99 durations, queue drains, multiple phases, load balancer propagation, and orchestrator behavior.

`preStop sleep` is a trick to create a traffic-drain window for specific environments, **not a guarantee** that every ingress/load balancer stops sending requests in exactly 5 seconds. Do not hardcode sleeps across every project unnecessarily; use readiness/connection draining and real rollout tests.

### 14.2. Readiness and liveness differ from shutdown signals

- **Readiness** answers “is the Pod ready to receive traffic?”. When terminating, Kubernetes marks relevant endpoints unready for normal traffic, though propagation via EndpointSlices/kube-proxy/ingress is asynchronous.
- **Liveness** answers “does the container need restarting because it is stuck?”. Never deliberately fail liveness just to perform a graceful rollout, as it can trigger restart loops.
- **preStop** is a container lifecycle hook executed before TERM in the termination flow; it is not Java `@PreDestroy`.
- **terminationGracePeriodSeconds** is kubelet's limit, not `spring.lifecycle.timeout-per-shutdown-phase`.
- **SIGKILL** upon expiration prevents Java callbacks from running any further.

If the app has `/actuator/health/readiness`, ensure it is exposed and reachable on the internal network; if Spring Security blocks probes with 401, Pods may never turn Ready. A separate management port may not reflect the main app port, so verify probe path choices carefully.

### 14.3. Principles for draining traffic before stopping

A sound workflow:

1. Pod/instance receives drain signal and stops acting as a target for new traffic.
2. Ingress/load balancers/clients get sufficient time to pick up routing changes.
3. Web server stops accepting new requests and waits for running requests within limits.
4. Background consumers stop accepting new work, finish/ACK in a controlled manner.
5. Critical business state is committed/idempotent.
6. Connections close and beans are destroyed.
7. Process exits before deadline.

Never assume network and application sequences form an atomic transaction. Endpoint propagation lags, long-lived keep-alive connections, retries, client timeouts, and load balancing behavior all exist.

### 14.4. Crashes and OOMKilled still require recovery

Pods can be OOMKilled, nodes can suddenly lose power, container runtimes can kill, or Pods can be force-deleted. In those cases, never rely on `@PreDestroy`. Use message redelivery, database transactions, distributed leases/TTLs, idempotent side effects, and startup recovery logic.

## 15. Graceful shutdown with background tasks and queue consumers

### 15.1. Scheduled tasks

A running scheduled job can be cut off when the context closes or its executor stops accepting tasks. In Spring Framework 6.1, task executors/schedulers have lifecycle shutdown policies; `waitForTasksToCompleteOnShutdown`, `awaitTerminationSeconds`, and `acceptTasksAfterContextClose` govern behavior.

Never assume long `@Scheduled` jobs will be awaited solely via `server.shutdown=graceful`, since that property mainly controls **web server requests**. For long workers, use `SmartLifecycle`/executor stop policies and explicit time bounds.

### 15.2. Message broker consumers

RabbitMQ/Kafka/Redis Streams consumers need to:

1. Stop polling/receiving new messages.
2. Wait bounded time to process already-received messages.
3. Commit offsets/ACK **after** business side effects are durable.
4. If unfinished before deadline, allow broker redelivery or resumption.
5. Consumers must be idempotent to avoid duplicate processing.

If ACKing before DB commit, a crash can lose work. If DB commits before ACK is recorded, the broker can redeliver, so idempotency keys or unique constraints must prevent duplicate effects. **Shutdown hooks cannot manufacture exactly-once business effects**.

### 15.3. Never rely on cleanup for consistency

A payment request committing when SIGKILL arrives may complete in the database while the HTTP client gets no response. Client retries can create duplicate transactions without an idempotency key. Design transaction outcomes and retry semantics from the start; graceful shutdown reduces incident frequency without eliminating it completely.

### 15.4. Connection pools and closing resources

`@PreDestroy` should release database connections, HTTP clients, schedulers, and Spring-managed resources. Avoid calling slow remote services inside callbacks whenever possible; shutdown deadlines are finite and dependencies may also be shutting down. Ideally each resource has an idempotent close method with a timeout, while critical data is committed during normal business processing rather than deferred to shutdown.

## 16. Timeout budget: calculating from the outside in

Example service with:

| Limit | Illustrative value | Meaning |
| --- | --- | --- |
| p99 HTTP business duration | 8 seconds | Most requests finish under 8s |
| Spring lifecycle timeout/phase | 20 seconds | Max wait time per phase |
| preStop hook | 5 seconds | Consumes part of Pod grace |
| Kubernetes Pod grace | 40 seconds | Total Pod termination deadline |
| Docker stop timeout if used standalone | 25 seconds | Container-level Docker deadline |
| LB drain propagation | Measured few seconds | Not always instantaneous |

A healthy config gives the app enough time under expected conditions without waiting forever. Never add or compare these numbers mechanically because **per-phase timeouts and shutdown callbacks can accumulate**, request durations vary, and health checks/network latencies fluctuate.

### 16.1. Timing selection strategy

- Measure p95/p99/bounded max of requests and background jobs.
- Enforce request timeouts/cancellation and cap long-running workloads.
- Define grace budgets for work that genuinely needs to complete.
- Set Kubernetes `terminationGracePeriodSeconds` covering preStop + Spring phases + safety margin.
- With Docker/Compose, ensure stop timeouts are not shorter than the app requires.
- Keep shutdown callbacks bounded; evaluate worst-case dependency failures.
- Test in real-like environments with concurrent load and rolling updates.
- For infinite streams, design client reconnect/resume instead of extending grace forever.

### 16.2. Why raising grace to 10 minutes can backfire

A single hung request or deadlocked worker can stall rollouts, pin old connections/resources, raise concurrent pod counts, and cause deployments to miss deadlines. Long grace does not make code safe without cancellation, bounded queues, and idempotency. Fix the root cause of hangs instead of blindly bumping timeouts.

## 17. Automated testing: what fits unit/integration tests?

### 17.1. Test endpoints, don't fake SIGKILL in @SpringBootTest

Use Spring Boot Test to verify `/quick` and `/work` work. Create `src/test/java/demo/SlowControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SlowControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void quickIsAvailable() throws Exception {
        mvc.perform(get("/quick"))
                .andExpect(status().isOk())
                .andExpect(content().string("quick-ok\n"));
    }

    @Test
    void workCompletesNormally() throws Exception {
        mvc.perform(get("/work").param("seconds", "0"))
                .andExpect(status().isOk())
                .andExpect(content().string("work-done\n"));
    }

    @Test
    void rejectsOverlongRequest() throws Exception {
        mvc.perform(get("/work").param("seconds", "26"))
                .andExpect(status().isBadRequest());
    }
}
```

Run:

```bash
./gradlew test
```

The test only checks normal HTTP behavior and **does not** prove the process runs hooks on SIGTERM or SIGKILL. To test OS shutdown, run the JAR in an independent process, open a real request, send signals, and inspect network/process/logs. You cannot declare “graceful passed” from a controller unit test alone.

### 17.2. Integration test for SIGTERM

A sensible harness:

1. Start the JAR as a child process; record exact PID and health-check ready.
2. Open an 8-second HTTP request and verify it started.
3. Send TERM to the exact JVM PID.
4. Record timestamps for signal send, HTTP completion, context logs, and process exit.
5. Assert the request returned the right body **when placed within the grace budget**.
6. Assert the process exited before the orchestrator deadline.
7. Restart the app, test SIGKILL, and verify data integrity does not depend on callbacks.
8. Test multiple concurrent requests of varying durations, keep-alive, streaming, and slow clients if supported.

A test harness must handle races: if TERM arrives **before** the request enters the handler, the result may be connection refused and says nothing about graceful draining. Wait for a server-side marker like `WORK_START` or a test-only barrier before signaling.

### 17.3. Tests actually needed in a production-like environment

- IDE Stop when running directly vs Gradle runner.
- SIGTERM/SIGINT/SIGKILL with standalone JVM.
- Short vs long Docker stop timeouts; shell vs exec-form Dockerfiles.
- Kubernetes rolling updates with preStop, readiness, EndpointSlice, and ingress.
- Fast/slow requests, HTTP keep-alive, SSE/WebSocket, uploads/long polling.
- Mid-flight DB transactions, Kafka/RabbitMQ consumer ACK/commit, running schedulers.
- Crash/OOMKill and startup recovery.
- Metrics for active requests, connection counts, shutdown duration, and forced kills.

## 18. Observing shutdown with metrics and logs

Telemetry to collect:

- Timestamp when drain/SIGTERM request arrived from orchestrator if supported.
- Timestamp when `ContextClosedEvent` fired.
- Timestamp when the web server began/ended its graceful phase.
- Active requests at stop time and completed/interrupted counts.
- Thread-pool active jobs, queued tasks, consumer lag/in-flight messages.
- Open SSE/WebSocket connection counts, reconnect rate.
- Duration of each shutdown phase and process exit time.
- Exit code/reason from container/pod (`OOMKilled`, `Error`, `Completed`...).
- HTTP client errors/connection resets during rollout.
- Retry rates, duplicate operations, timeouts, and transaction failures after restart.

**Do not** log request bodies/credentials just to “see which requests dropped”. Use request IDs, trace IDs, route templates, durations, statuses, and safely managed idempotency keys. A request logging `WORK_DONE` without a client 200 still requires checking network and application semantics.

### 18.1. Missing logs and exit codes are inconclusive alone

Missing `@PreDestroy` in logs can mean a force kill, a different IDE stop method, logger shutdown, unflushed log collectors, or an unregistered callback. Conversely, seeing `@PreDestroy` logs does not prove request payloads, HTTP responses, or message ACKs finished. Correlate multiple signals.

### 18.2. Do not turn shutdown logging into a bottleneck

During shutdown, logging appenders/network sinks may also be closing. Avoid calling remote endpoints or writing massive log volumes from shutdown hooks. Keep logs concise, structured, secret-free, and best-effort; business durability belongs in main processing.

## 19. Common misconceptions

| False belief | Reality |
| --- | --- |
| “Clicking Stop in every IDE sends SIGTERM.” | Depends on IDE, OS, launcher, and run/debug mode; must test. |
| “@PreDestroy ran means every HTTP response was sent.” | Bean destruction is distinct from request completion/network delivery. |
| “SIGTERM and SIGKILL only differ in signal number.” | TERM lets the JVM shut down; KILL forces exit without hooks. |
| “Ctrl+C always equals kill -9.” | Unix Ctrl+C is usually SIGINT, not SIGKILL. |
| “System.exit bypasses JVM hooks.” | System.exit triggers the shutdown sequence; Runtime.halt bypasses it. |
| “ApplicationContext.close always stops the OS process.” | Context may close while non-daemon threads keep the JVM alive. |
| “Boot 3.3 enables graceful shutdown by default.” | Boot 3.3 requires `server.shutdown=graceful`; Boot 3.4 changed the default. |
| “graceful=20s always waits 20s before exiting.” | It can exit early when done; timeout applies per phase. |
| “Tomcat must return 503 during shutdown.” | It may stop accepting connections at the network layer; 503 is not promised. |
| “docker stop always gives 20s like Boot.” | Docker stop timeout is separate and often shorter unless configured. |
| “Docker sends TERM to Java regardless of ENTRYPOINT.” | Shell wrappers/PID 1 may fail to forward signals. |
| “Kubernetes preStop 5s is added on top of 30s grace.” | preStop is inside the grace budget. |
| “Pod readiness false drains all traffic immediately.” | Endpoint/ingress propagation is asynchronous. |
| “Adding 60s grace guarantees zero lost messages.” | Crashes/SIGKILL/network drops still happen; durable queues and idempotency are required. |
| “Exit 143 proves every @PreDestroy ran.” | Exit code is a hint, not proof of cleanup. |
| “Controller WORK_DONE means the client got 200.” | Network/writes can fail after the controller returns. |
| “When a JVM dies, finally always runs.” | With SIGKILL/Runtime.halt/fatal termination, it is not guaranteed. |

## 20. Self-check questions

**1.** Why is clicking IDE Stop insufficient to conclude Spring Boot graceful shutdown works?  
**Answer:** The IDE may send another signal or force-terminate the process/launcher; you must verify what mechanism the JVM received, callbacks, and HTTP request outcomes.

**2.** Spring Boot 3.3 already has a shutdown hook—is `server.shutdown=graceful` still needed?  
**Answer:** Yes, if you want the web server to wait for running requests up to a grace period; context-closing hooks and HTTP graceful shutdown are two separate layers.

**3.** How does Spring Boot 3.4 differ from Boot 3.3 here?  
**Answer:** Boot 3.4 made graceful web-server shutdown the default; Boot 3.3 requires configuring it explicitly.

**4.** If SIGTERM reaches the exact JVM, is `@PreDestroy` guaranteed to run?  
**Answer:** It has a chance during normal shutdown, though it is not absolute if the signal is blocked/unhandled, the JVM crashes, or SIGKILL arrives before that callback's turn.

**5.** Does `kill -9` give Java shutdown hooks a few seconds to run?  
**Answer:** No. SIGKILL forces kernel termination and the JVM runs no shutdown sequence.

**6.** Are `System.exit(0)` and `Runtime.halt(0)` identical?  
**Answer:** No. `System.exit` triggers shutdown hooks; `halt` terminates immediately without running hooks.

**7.** Tomcat stops accepting new requests during graceful shutdown. Must curl receive HTTP 503?  
**Answer:** No. It may fail to open a connection; Undertow exhibits 503 behavior in Boot 3.3 docs.

**8.** Docker defaults to 10s wait, Spring grace is 20s. Will a 15s request definitely finish?  
**Answer:** No. Docker can send KILL after 10s; configure Docker stop timeout and test.

**9.** What problem can Dockerfile `ENTRYPOINT java -jar ...` cause?  
**Answer:** Shell form can make the shell PID 1 and fail to forward TERM; use exec form or `exec` in scripts.

**10.** A Pod has `terminationGracePeriodSeconds=30` and `preStop sleep 10`. Does the JVM still have 30s?  
**Answer:** No. `preStop` consumes the grace budget; the JVM usually has ~20s or less left.

**11.** A Kafka consumer committed DB changes yet hadn't ACKed when SIGKILL hit. What can happen?  
**Answer:** The broker redelivers; idempotency or dedup is needed to avoid duplicate business side effects.

**12.** A request logged `WORK_DONE` and then the client hit connection reset; is data guaranteed safe?  
**Answer:** You cannot tell from the log alone. Check transaction commits, idempotency, and response delivery separately.

**13.** Why not wait for long-lived WebSockets forever during graceful shutdown?  
**Answer:** Connections can live for hours; close cleanly and have clients reconnect/resubscribe with cursors.

**14.** Does a passing `MockMvc` test prove SIGTERM draining works?  
**Answer:** No. You need a live process integration test sending OS signals and observing requests over TCP.

## 21. Pre-rollout checklist

- [ ] Verified exact Spring Boot version and `server.shutdown` default; Boot 3.3 sets `server.shutdown=graceful` explicitly.
- [ ] Set `spring.lifecycle.timeout-per-shutdown-phase` from active requests/jobs and real measurements.
- [ ] Tested IDE Stop rather than guessing signals from button names.
- [ ] Distinguished graceful context close, HTTP drain, and process termination.
- [ ] Added logs/context events/SmartLifecycle/@PreDestroy for visibility without treating them as sole proof.
- [ ] Callbacks are bounded, idempotent, and non-blocking; `SmartLifecycle.stop(Runnable)` invokes callback.
- [ ] Finite HTTP requests have matching timeouts/cancellation.
- [ ] SSE/WebSocket/streaming have close/reconnect/resume plans.
- [ ] Dockerfile uses exec-form ENTRYPOINT; PID 1 receives stop signals properly.
- [ ] Docker/Compose stop timeouts cover shutdown phase budgets.
- [ ] Kubernetes readiness, EndpointSlices, ingress drain, and preStop tested.
- [ ] `terminationGracePeriodSeconds` covers preStop + Spring phases + real margin.
- [ ] Queue consumers stop taking new work and commit/ACK properly; handle retries/dedup.
- [ ] DB transactions/idempotency do not rely on `@PreDestroy` for consistency.
- [ ] Have SIGTERM and forced-termination integration tests in production-like environments.
- [ ] Never rely on an exit code or a single log line to assume all requests finished.
- [ ] Metrics track shutdown duration, client errors, active requests, consumer lag, and forced kills.
- [ ] Actuator shutdown endpoint is not publicly open; app-stop permissions are restricted.
- [ ] Have a recovery playbook when a JVM/node dies unexpectedly so restarts and retries stay safe.

## Official references

1. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
2. [Spring Boot 3.4 — Release Notes, Graceful Shutdown Default](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
3. [Spring Boot 3.3 — SpringApplication.setRegisterShutdownHook Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
4. [Spring Framework 6.1 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html)
5. [Spring Framework — Bean Lifecycle and Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
6. [Java 17 — Runtime Shutdown Hooks and halt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
7. [Docker — docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/)
8. [Docker — docker container kill](https://docs.docker.com/reference/cli/docker/container/kill/)
9. [Docker — docker container run, stop-signal and stop-timeout](https://docs.docker.com/reference/cli/docker/container/run/)
10. [Docker Compose — Stop Grace Period](https://docs.docker.com/compose/compose-file/05-services/#stop_grace_period)
11. [Kubernetes — Pod Lifecycle: Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods)
12. [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
13. [Kubernetes — Deployment Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
14. [Spring Boot 3.3 — Actuator Health Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

**Conclusion:** **IDE Stop** is a UI action whose semantics vary by tool/OS; **SIGTERM/SIGINT** usually give the JVM a chance to run shutdown hooks and Spring callbacks; **SIGKILL/Runtime.halt/force terminate** do not. **Graceful HTTP shutdown** is a separate layer helping running requests finish before a deadline and must not be equated with `@PreDestroy`. Safe production shutdown requires combining **signal forwarding, the right Boot version, time budgets, traffic draining, background work lifecycles, and crash-tolerant/idempotent design**.
