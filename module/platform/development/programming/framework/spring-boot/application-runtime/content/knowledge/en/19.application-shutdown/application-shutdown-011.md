# Differences Between the IDE Stop Button and Controlled Shutdown Signals — Spring Boot 3.3

## 1. Lesson Objectives

While developing with Spring Boot, developers often click the **Stop** button in IntelliJ IDEA, Eclipse, VS Code, or a run/debug window and see the Java process disappear. Yet **the process disappearing** does not mean the application ran its full shutdown sequence: stopping HTTP request intake, waiting for in-flight requests, stopping consumers, flushing data, closing connections, and invoking `@PreDestroy`.

A Java process can also be stopped via `Ctrl+C`, `SIGTERM`, closing the `ApplicationContext`, Docker/Kubernetes commands, or forced termination with `SIGKILL`. These methods differ in whether they trigger JVM shutdown hooks and Spring lifecycle callbacks.

**Main takeaway:** *The Stop button is a dev-tool action, not a standardized application shutdown contract.* To test controlled shutdown, identify **what action the IDE/OS/launcher sends to the JVM**, use the right signal, and observe **actual shutdown behavior**. Never assume Stop always sends `SIGTERM` or always skips `@PreDestroy`.

After this lesson, you can:

1. Distinguish **graceful shutdown**, **terminate**, and **force kill**.
2. Understand when the JVM gets a chance to run shutdown hooks and when it does not.
3. Explain the roles of `SpringApplication`, `ApplicationContext.close()`, `ContextClosedEvent`, `SmartLifecycle.stop(Runnable)`, `@PreDestroy`, and graceful web servers.
4. State the limits of IDE Stop/Exit/Terminate buttons across versions, run configurations, operating systems, and launch mechanisms.
5. Practice stopping a Spring Boot 3.3.13 app running on JDK 21 with `SIGTERM` and contrast it with `SIGKILL`.
6. Write deterministic shutdown tests independent of how an IDE implements Stop.
7. Design production shutdown so in-flight requests/jobs never use already closed resources.

## 2. Three Important Types of Termination

### 2.1. Graceful Shutdown

The application is notified to stop operating and **gets a chance** to execute these steps:

```text
Controlled shutdown requested
  |
  +-- Stop accepting new work/traffic
  +-- Wait for running requests/jobs within deadline
  +-- Stop lifecycle components
  +-- Flush / checkpoint / ACK where appropriate
  +-- Destroy Spring beans
  +-- Close resources and exit process
```

"Graceful" does **not** guarantee 100% of all work completes. If a request hangs or exceeds the timeout, the system may still have to cancel work, return errors, or be killed by the platform after the grace period.

### 2.2. Normal JVM Shutdown

With a standard JVM, paths such as:

- The `main` method returns and no non-daemon threads remain keeping the process alive.
- A `System.exit(status)` call.
- A termination signal handled by the JVM, typically `SIGTERM`/`SIGINT` on Unix-like systems.

can move the JVM into its shutdown sequence and run registered **shutdown hooks**, where Spring Boot registers a mechanism to close the context by default. However, if the process lacks a valid Boot context, disabled the hook, hit a severe runtime failure, or the signal never reached the child JVM, the outcome differs.

**Distinction:** A Java shutdown hook is a JVM mechanism; HTTP graceful shutdown is a specific Spring Boot mechanism executed when the context closes. Having a JVM hook is **not enough** to conclude all requests/jobs drained cleanly.

### 2.3. Forceful Termination

A forced process termination command typically prevents the JVM from running shutdown hooks, for example:

- `SIGKILL` on Linux/macOS (`kill -KILL` or `kill -9`).
- `Runtime.getRuntime().halt(status)` inside the JVM.
- Forced process killing by the OS, IDE, or process manager.
- Power loss, sudden container kill, or severe JVM crash.

In those cases, `@PreDestroy`, `finally`, and cleanup on worker threads are **not guaranteed to run**. A log entry may still sit in a buffer; missing logs alone also cannot prove exactly which method did or did not run. Preventing data loss requires transactions, durable queues, idempotent retries, and checkpoints.

## 3. Comparing IDE Stop and Other Stop Actions

| Action | Who initiates it? | Chance to run Spring shutdown? | Things to note |
| --- | --- | --- | --- |
| **IDE Stop** | Run/Debug tool window | **Depends on IDE, version, config, OS, and launcher** | May terminate softly, simulate interrupt, or force-kill |
| **IDE Exit/Graceful Exit** (if provided by IDE) | IDE offering a soft exit | Can intentionally route the app through normal termination | Not every IDE/version has the same button |
| **`Ctrl+C` in terminal** | Operator | Usually yes, if signal/console event reaches JVM cleanly | On Unix-like OSes usually `SIGINT`; on Windows it is a console control event |
| **`kill -TERM PID`** | Unix-like OS | Usually yes; JVM can run shutdown hooks | Must target the **real JVM** PID, not a wrapper |
| **`kill -KILL PID`** | Unix-like OS | **No** | Skips shutdown hooks and cleanup |
| **`context.close()`** | Code inside the app | Yes, executes Spring lifecycle on that context | Does not necessarily exit JVM if other threads/contexts remain |
| **`SpringApplication.exit(context)`** | Code inside the app | Closes context and computes exit code via Boot | API itself does not replace OS stop commands in all cases |
| **`System.exit(code)`** | Code inside the JVM | Usually triggers JVM shutdown hooks | Should not be called arbitrarily in business code |
| **`Runtime.halt(code)`** | Code inside the JVM | **No** | Terminates quickly, no flush guarantee |
| **`docker stop` / Kubernetes graceful termination** | Orchestration platform | Usually sends stop signal then waits for grace period | Uses forced kill at expiration; requires config and testing |

**Do not treat this table as an absolute promise:** Maven/Gradle launchers, process trees, debuggers, script wrappers, terminal emulators, Windows, or containers can alter how signals are sent and forwarded.

### 3.1. The Stop Button Is Not a Standard Java Command

Java defines no API named "IDE Stop". An IDE may choose to terminate the process, send a console interrupt, run a script, detach the debugger, or kill the process tree. If you click Stop on a **Maven/Gradle task**, what stops first may be the **build tool**, not the Spring Boot JVM directly.

Even across docs/UI of a single IDE, Stop, Exit, Kill Process, and Debug Stop can have distinct semantics. **Read the help docs for your exact IDE version and run configuration, and verify experimentally** rather than carrying rules from IntelliJ over to Eclipse or VS Code.

### 3.2. IntelliJ IDEA Case

JetBrains documentation describes **Stop**, **Exit**, and **Kill Process** actions in the Run tool window, including cases where Stop performs a soft kill before offering a forced kill option. In other guides, Stop is described as a forceful termination that may skip cleanup. Because behavior varies by version and launch context, you cannot claim **every** IntelliJ Stop button sends `SIGTERM`, `SIGINT`, or runs hooks.

A practical test is: run an app logging `ContextClosedEvent`, `SmartLifecycle.stop`, and `@PreDestroy`; click Stop **once**, observe logs; then repeat with **Exit** if available, or run the JAR directly in a terminal and send `SIGTERM`. Never click **Kill Process** when verifying graceful behavior on a workload holding important data.

### 3.3. Eclipse, VS Code, and Other IDEs

**Terminate/Stop** buttons usually target the **process/debug session**. Never infer from a button's name that the JVM ran shutdown hooks.

Notably, debugging an app attached to an existing JVM may only **detach the debugger**, leaving the Spring Boot process running. Conversely, a launcher configured to "terminate" can kill the process abruptly. Distinguish stopping a debug session, stopping a task runner, and stopping the actual JVM.

## 4. How Does Spring Boot Handle a Controlled Shutdown?

In a normally started Boot application, `SpringApplication` registers a shutdown hook by default to close `ApplicationContext` when the JVM enters an appropriate shutdown sequence.

When the context closes, the conceptual milestones are:

```text
JVM handles valid shutdown
   |
   +-- Spring Boot shutdown hook
         |
         +-- ConfigurableApplicationContext.close()
               |
               +-- Publish ContextClosedEvent
               |
               +-- LifecycleProcessor.onClose()
               |     +-- Stop SmartLifecycle by phase/dependency
               |     +-- Graceful web server shutdown if enabled
               |     +-- stop(Runnable) may wait for callback/timeout
               |
               +-- Destroy singleton beans
                     +-- @PreDestroy / DisposableBean / destroy method
```

**Do not confuse event order:** `ContextClosedEvent` is published when context closure begins, before normal stop/destroy steps. `@PreDestroy` happens during bean destruction, so a component currently in `stop()` must not be assumed to have already run `@PreDestroy`.

### 4.1. SmartLifecycle and Deadlines

`SmartLifecycle` extends `Lifecycle` so Spring can coordinate:

- `start()`, `stop()`, `isRunning()`;
- `isAutoStartup()`;
- `getPhase()`;
- `stop(Runnable callback)` when knowing the actual stop completion time is required.

Typically higher phases **start later**, yet **stop earlier** than lower phases. Bean dependencies known to Spring can take precedence over phase, since dependent components must stop before their dependencies.

The `stop(Runnable)` callback must be invoked once stopping finishes per contract. If a listener container merely fires an async stop request and calls the callback immediately, Spring can proceed to close underlying resources prematurely.

### 4.2. Graceful HTTP Shutdown Is Only One Part

Spring Boot 3.3 provides properties:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

For web apps with embedded servers, graceful shutdown runs as part of **closing the application context**. It attempts to restrict/stop new requests and let existing requests complete within the configured wait time. Boot supports Tomcat, Jetty, Reactor Netty, and Undertow; how new requests are refused depends on the server/connection.

An HTTP request may have submitted a **background task** to an executor and returned a response. That task **does not automatically become** an in-flight HTTP request for graceful server shutdown; if needed, the service managing that task must design its own stop/drain.

### 4.3. Readiness and the ApplicationReadyEvent Milestone

`ApplicationReadyEvent` occurs **after runners finish** on the successful startup path. During shutdown, what matters is **stopping new traffic and jobs** before draining; never confuse "was once ready" with "can keep accepting work throughout shutdown".

Availability/readiness can tell an orchestrator to temporarily refuse traffic, yet `ReadinessState.REFUSING_TRAFFIC` **does not close sockets or cancel all tasks itself**. Safety requires combining platform routing, graceful servers, and consumer-specific lifecycles.

## 5. Complete Spring Boot 3.3.13 + Java 21 Example

We will build a **web** application to observe simultaneously:

1. An HTTP `/work` request that can be running when shutdown starts.
2. `ContextClosedEvent` published.
3. A `SmartLifecycle` stopping and invoking its callback.
4. The bean destroyed via `@PreDestroy`.
5. Comparing milestones when clicking Stop in an IDE vs. sending `SIGTERM`.

The demo intentionally uses `Thread.sleep` **only to simulate a slow request**; production must use deadlines, client timeouts, and proper concurrency controls.

### 5.1. Project Structure

```text
shutdown-signal-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/shutdown/
    │   │   ├── ShutdownSignalApplication.java
    │   │   ├── ShutdownTrace.java
    │   │   ├── WorkController.java
    │   │   └── ShutdownWitness.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/shutdown/
            └── ShutdownContractTest.java
```

### 5.2. pom.xml

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
    <artifactId>shutdown-signal-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Only the web starter and test starter are used; no database, Actuator, or broker is needed to run the example.

### 5.3. application.properties

File `src/main/resources/application.properties`:

```properties
spring.application.name=shutdown-signal-demo
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

`server.shutdown=graceful` specifically needs to be enabled when using Spring Boot **3.3**. Never extrapolate defaults from a newer Boot version onto 3.3. The 20-second timeout is an example, not a universal fit for every system.

### 5.4. ShutdownSignalApplication.java

```java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownSignalApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownSignalApplication.class, args);
    }
}
```

`SpringApplication.run(...)` keeps the context/web server running. **Do not** close the context immediately after `run()` returns in this server app; shutdown is triggered when the JVM receives an appropriate stop request or the app explicitly closes the context.

### 5.5. ShutdownTrace.java

```java
package com.example.shutdown;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class ShutdownTrace {

    private final CopyOnWriteArrayList<String> events =
            new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
        System.out.println("DEMO " + event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

This bean records lifecycle milestones. `System.out.println` aids illustration, whereas production should use structured logging, metrics, trace IDs, flush policies, and external observability. **`System.out` alone is not durable proof of completion** because stdout can be buffered or the process can be killed mid-way.

### 5.6. ShutdownWitness.java

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownWitness implements SmartLifecycle {

    private final ShutdownTrace trace;
    private volatile boolean running;

    public ShutdownWitness(ShutdownTrace trace) {
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        trace.record("LIFECYCLE start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        trace.record("LIFECYCLE stop");
        running = false;
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
    public int getPhase() {
        return 100;
    }

    @EventListener
    public void onClosing(ContextClosedEvent event) {
        trace.record("CONTEXT closing");
    }

    @PreDestroy
    void onDestroy() {
        trace.record("BEAN preDestroy");
    }
}
```

`SmartLifecycle.isAutoStartup()` defaults to `true`, so `start()` runs during context refresh. When the context closes via a valid path, the listener sees `ContextClosedEvent`; then the lifecycle processor calls `stop(callback)`, and finally bean destruction calls `@PreDestroy`.

The demo's `stop(Runnable)` is synchronous, so the callback runs right **after** `stop()` finishes. Real consumers must wait/drain work rather than calling the callback prematurely.

**Order among `CONTEXT closing`, active requests, and web server logs can interleave**. Do not compare entire console output as an absolute sequence.

### 5.7. WorkController.java

```java
package com.example.shutdown;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {

    private final ShutdownTrace trace;

    public WorkController(ShutdownTrace trace) {
        this.trace = trace;
    }

    @GetMapping("/work")
    public String work(@RequestParam(defaultValue = "8") int seconds)
            throws InterruptedException {

        if (seconds < 1 || seconds > 15) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "seconds must be 1..15");
        }

        trace.record("HTTP work begin");

        try {
            Thread.sleep(seconds * 1000L);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            trace.record("HTTP work interrupted");
            throw ex;
        }

        trace.record("HTTP work complete");
        return "completed";
    }
}
```

The controller simulates a request up to 15 seconds long. In real products, **never use `Thread.sleep` to perform business work**; this merely reproduces an in-flight HTTP request.

To verify graceful shutdown, pick an 8-second request, a 20-second grace period, and send the stop signal while the request is still running. When the server and OS permit controlled shutdown, the request has a chance to return `completed`; under a forced kill, the connection may reset or the request may be interrupted.

### 5.8. Build and Start

Requires JDK 21, Maven, and permission to download dependencies.

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/shutdown-signal-demo-0.0.1-SNAPSHOT.jar
```

On a normal JAR run, `ShutdownWitness.start()` prints:

```text
DEMO LIFECYCLE start
```

Other messages are Spring Boot and web container logs. `LIFECYCLE start` occurs during refresh, before application ready in Boot's lifecycle.

## 6. Experimenting via Terminal Instead of Relying on an IDE

### 6.1. Linux/macOS Experiment: SIGTERM

**Terminal A:** run the JAR directly:

```bash
java -jar target/shutdown-signal-demo-0.0.1-SNAPSHOT.jar
```

**Terminal B:** issue an 8-second request:

```bash
curl -v "http://localhost:8080/work?seconds=8"
```

While the request has not finished, find the **exact PID of the demo JVM**, e.g.:

```bash
jps -l
```

Then request a controlled termination:

```bash
kill -TERM <DEMO_JVM_PID>
```

Replace `<DEMO_JVM_PID>` with the actual PID number; do not paste the placeholder literally into the shell. **Do not pick your IDE's JVM or another app by mistake.** `jps` requires JDK tools and the list may contain multiple processes.

**Milestones to observe** when the shutdown hook and graceful web server execute:

```text
DEMO HTTP work begin
DEMO CONTEXT closing
DEMO HTTP work complete
DEMO LIFECYCLE stop
DEMO BEAN preDestroy
```

**This is one valid observation scenario, not a guaranteed absolute stdout sequence for every scheduling order.** `CONTEXT closing` typically prints as closure starts, while requests may still be running. What matters to verify is:

- The request started and **had a chance** to finish within the deadline.
- The Spring context received the close process.
- `SmartLifecycle` stopped.
- The bean with `@PreDestroy` was destroyed.
- The client received a successful response or a reasoned error if timed out/interrupted.

If the request finished **before** SIGTERM was sent, `HTTP work complete` appears before `CONTEXT closing`. That is not a bug; repeat the experiment and send the signal sooner to genuinely observe in-flight draining.

### 6.2. Linux/macOS Experiment: SIGKILL

**Test only on a demo instance without real data.** Restart the JAR, send a long request, find the **new PID**, and run:

```bash
kill -KILL <DEMO_JVM_PID>
```

With `SIGKILL`, the JVM cannot run shutdown hooks and Spring gets no chance to execute `ContextClosedEvent`, `SmartLifecycle.stop`, or `@PreDestroy` from this kill command.

Thus you will normally **not see** shutdown milestones appear after the kill. Still, missing console logs are not an absolute verification method: output may be lost to buffering or transport. Check the client side and external resources if you want to confirm the impact.

**Never use `kill -9` as a routine shutdown action for production apps.** When a deadline expires and forced kill becomes necessary, business crash recovery must handle it.

### 6.3. Ctrl+C

On Unix-like terminals, `Ctrl+C` normally sends `SIGINT` to the foreground process group. A standard JVM can handle this event and run shutdown hooks; however, if the JAR runs through a wrapper, a different terminal, an IDE, or a build tool, do not assume the child JVM receives the right signal.

On Windows, `Ctrl+C` is a console control event, **not POSIX SIGTERM**. A normal console Java process can go through shutdown, yet `Stop-Process`, Task Manager, and an IDE's Stop button are not equivalent verification tools. On Windows, prefer in-process `context.close()` tests and verify the shutdown behavior of your specific launcher before relying on any stop method in operations.

### 6.4. Why Run the JAR Directly?

If you run:

```bash
mvn spring-boot:run
```

or run through a Gradle task, the terminal may be controlling the **Maven/Gradle launcher**, not the application JVM's PID. The launcher may fork a child process, forward signals under its own rules, or terminate children. To eliminate variables when studying JVM shutdown mechanics, run `java -jar` directly and signal the **exact PID**.

### 6.5. Experimenting with IDE Stop

After testing via terminal:

1. Run the application from your IDE using your usual configuration and wait for the server to listen.
2. Call `/work?seconds=8` from an external terminal.
3. While the request is running, **click Stop once**.
4. Record whether the request succeeded or errored; look for `DEMO CONTEXT closing`, `DEMO LIFECYCLE stop`, and `DEMO BEAN preDestroy`.
5. If the IDE offers an **Exit/Graceful** action distinct from Stop, retest to compare.
6. Record the exact IDE version, Run vs. Debug, JDK, OS, and run configuration type.
7. Do not click Kill Process repeatedly while trying to verify graceful shutdown.

**Valid takeaway:** if the IDE run lacks milestones that terminal SIGTERM produced, that indicates the IDE/launcher's stop path does not go through the same cleanup sequence or logs were not forwarded; consult docs and test further to distinguish. Even if all milestones appear, **still** verify in-flight work and deadlines rather than only spotting one `@PreDestroy` line.

## 7. JUnit Lifecycle Testing Without OS Signals

A small unit/integration test can close the Spring context **in the same JVM**, independent of IDE Stop or OS signals. The test below verifies the event → stop → destroy sequence, while HTTP graceful draining requires the live experiments in section 6.

File `src/test/java/com/example/shutdown/ShutdownContractTest.java`:

```java
package com.example.shutdown;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShutdownContractTest {

    @Test
    void contextCloseInvokesLifecycleAndDestroy() {
        ShutdownTrace trace;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ShutdownTrace.class, ShutdownWitness.class)) {
            trace = context.getBean(ShutdownTrace.class);
            assertTrue(context.getBean(ShutdownWitness.class).isRunning());
        }

        assertEquals(List.of(
                "LIFECYCLE start",
                "CONTEXT closing",
                "LIFECYCLE stop",
                "BEAN preDestroy"
        ), trace.snapshot());
    }
}
```

`AnnotationConfigApplicationContext` creates and refreshes a real bean context, `SmartLifecycle` auto-starts, and `try-with-resources` closes the context via Spring's normal path. `@EventListener(ContextClosedEvent.class)` and `@PreDestroy` are handled by Spring on context close.

Run:

```bash
mvn test
```

Expect this test class to have **one passing test** when the project compiles cleanly. The test opens no web server, catches no OS signals, and proves nothing about what signal IDE Stop sends; it strictly verifies the **context-closing contract**.

## 8. When a Request or Background Task Is Still Running

### 8.1. Graceful HTTP Shutdown and Background Executors

Suppose a request triggers report generation:

```java
@GetMapping("/submit")
public String submit() {
    taskExecutor.execute(this::generateReport);
    return "accepted";
}
```

**Illustrative snippet, not part of the runnable project in section 5.** Once the `"accepted"` response is returned, the HTTP request has ended while `generateReport` may still be queued or executing. Therefore, the web server finishing HTTP request draining **does not** mean background tasks completed.

A `SmartLifecycle` or job coordinator must:

- Stop accepting new tasks.
- Wait for / cancel queued and running tasks in a controlled way.
- Write checkpoints or retry state.
- Keep DBs/clients/resources open until tasks no longer use them.
- Signal `stop(Runnable callback)` completion **after** those steps truly finish.

### 8.2. stop(Runnable) Must Not Report Completion Too Early

Anti-pattern:

```java
@Override
public void stop(Runnable callback) {
    executor.execute(this::drainPendingWork);
    callback.run(); // Wrong: the task was just enqueued.
}
```

This is illustrative code. Calling the callback immediately lets the lifecycle processor proceed to close resources in the next phase, causing `drainPendingWork` to hit already closed objects.

Conceptually correct pattern:

```java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewWork();
    CompletionStage<Void> draining = drainWithDeadline();
    draining.whenComplete((ignored, failure) -> {
        if (failure != null) {
            recordFailure(failure);
            applyRecoveryPolicy();
        }
        markStopped();
        callback.run();
    });
}
```

**The code above is a non-standalone architectural pattern**, requiring real methods, imports, and synchronization/cancellation mechanics. Besides stage failures, handle exceptions occurring **before** the stage is created. Never forget the callback, yet never report draining succeeded while work continues using resources.

### 8.3. Bounded Waiting Instead of Infinite Waiting

`Future.get(timeout, unit)`, `CountDownLatch.await(timeout, unit)`, or bounded completion stages cap shutdown duration. Timeouts **do not automatically make** remote I/O stop or roll back; request cancellation, JDBC/HTTP client timeouts, checkpoints, and idempotency/retries are still needed.

Never call blocking `future.get()` on **the single worker thread** whose awaited task is queued on that very same executor: that causes a deadlock.

## 9. Testing Shutdown in Containers and Production

### 9.1. Docker and Kubernetes

For a Spring Boot container:

```text
Orchestrator requests stop
   |
   +-- Send SIGTERM / termination intent
   +-- Grant grace period
   |      +-- context close
   |      +-- web graceful shutdown
   |      +-- lifecycle stop/drain
   |      +-- bean destruction
   |
   +-- If expired: force kill
```

Actual behavior depends on the entrypoint, PID 1, signal propagation, shell wrappers, and how the process starts. If `java` is a child of a shell script that does not forward signals, the JVM may **never receive** the stop command sent to PID 1 by orchestration. Inspect the container entrypoint and real termination flow.

### 9.2. The Grace Period Must Be Unified

`spring.lifecycle.timeout-per-shutdown-phase=20s` does not guarantee a Pod gets 20 seconds if the platform kills the process sooner; each phase can also consume its own time. Total shutdown budget design must cover:

- Time for the load balancer to stop sending new work.
- Time for surviving HTTP requests to complete.
- Time to stop consumers/schedulers.
- Time to drain background tasks, flush, and checkpoint.
- Time to close connection pools, loggers, and other resources.

Do not multiply a per-phase timeout without accounting for the platform's total deadline.

### 9.3. When the Application Decides to Stop Itself

An authorized internal coordinator can call `context.close()` or use `SpringApplication.exit(context)` when appropriate. The benefit is deliberately traversing the Spring lifecycle, allowing breakpoints and tests independent of any UI button.

**Caution:** never expose a public `/shutdown` HTTP endpoint just for testing. If administrative shutdown is required, enforce authentication/authorization, auditing, network restrictions, and formal operational controls. Never use an unprotected endpoint letting outsiders shut down the service.

### 9.4. SIGKILL and Durability

Even with well-built graceful shutdown, applications must handle crash/force-kill scenarios:

- Critical business data is written transactionally.
- Consumers process messages **idempotently**.
- In-progress jobs maintain checkpoints or retry state.
- Outboxes or durable queues ensure messages are not lost when a process dies.
- The next startup can detect unfinished work and reprocess safely.

**Never build a "zero lost work" design relying solely on `@PreDestroy` or JVM shutdown hooks.**

## 10. Common Misconceptions

| Misconception | Reality | How to handle |
| --- | --- | --- |
| "Clicking IDE Stop always calls @PreDestroy" | Depends on IDE/launcher/OS mechanics | Verify `ContextClosedEvent`, stop, and destroy milestones |
| "Clicking IDE Stop is always SIGTERM" | Many IDEs distinguish Stop/Exit/Kill semantics | Read docs for your version; test directly |
| "JVM terminated means all hooks ran" | Forced kills can skip hooks | Distinguish graceful vs. forced kills |
| "SIGKILL can be caught for cleanup" | SIGKILL gives the JVM no chance to run hooks | Design crash recovery |
| "Having @PreDestroy equals graceful shutdown" | Does not prove HTTP requests and jobs drained | Graceful web + lifecycle job drain |
| "ContextClosedEvent means resources are closed" | Event fires at the start of closure | Observe stop/destroy milestones separately |
| "Clicking Stop means the process is definitely dead" | IDE may only detach debug or soft-stop hung | Check PID and process tree |
| "Stopping a Maven task always stops the Spring child JVM cleanly" | Launcher may not forward signals | Test `java -jar` directly |
| "Ctrl+C and SIGTERM are identical on every OS" | Windows console events differ from POSIX signals | Test on the real target OS and launcher |
| "No active HTTP requests means background jobs finished" | Jobs may have detached from request threads | Manage in-flight jobs separately |
| "20s shutdown timeout guarantees jobs finish" | Tasks may be slow/uncooperative | Timeouts + cancellation + retry/checkpoints |
| "Larger grace period is always better" | Can exceed deploy deadlines and stall rollouts | Measure and set realistic budgets |
| "`System.exit` is how to stop any service request" | Abruptly terminates traffic and other contexts | Use managed orchestration/close properly |
| "Missing @PreDestroy log proves Java never called it" | Console output may be lost when killed | Corroborate with tests, exit codes, external metrics |
| "Debug Stop button is the same as Detach" | One may only detach debugger while the other terminates the process | Identify the exact action and inspect the process |

## 11. Diagnostic Checklist When IDE Stop Is Not Graceful

1. Which IDE, which version, Run or Debug, Stop/Exit/Terminate/Kill Process?
2. Which JDK vendor/version, and which OS?
3. Does the JVM run directly or via Maven/Gradle, shell script, debugger, or container?
4. After clicking Stop, does the **JVM PID** disappear?
5. Is `ContextClosedEvent` recorded?
6. Do `SmartLifecycle.stop(Runnable)` and callback completion run?
7. Do `@PreDestroy` / destroy methods execute?
8. Is `server.shutdown=graceful` configured properly for Boot 3.3?
9. Is `spring.lifecycle.timeout-per-shutdown-phase` sufficient and aligned with the platform grace period?
10. Did in-flight requests complete or get cut off? Are client errors visible?
11. Which background tasks still use executors/DataSource after context close?
12. Is a custom shutdown hook hanging or racing with another hook?
13. Does the JVM receive `SIGTERM` cleanly if signaled directly from a terminal to its PID?
14. Could console output be buffered or truncated?
15. Did something trigger a force kill (clicking twice, orchestrator timeout, process manager)?
16. Are retries, checkpoints, and durable state in place when the process dies abruptly?

If `java -jar` + `SIGTERM` shows full stop/destroy while IDE Stop does not, **investigate the IDE and launcher termination path first**; do not rush to alter Spring annotations or raise timeouts when the JVM never even got a chance to close its context.

## 12. Practice Exercises

1. Explain the difference between an IDE Stop action and POSIX `SIGTERM`.
2. Why can't `SIGKILL` invoke `@PreDestroy`?
3. Draw the timeline `ContextClosedEvent` → `SmartLifecycle.stop` → `@PreDestroy`.
4. When might a `@PreDestroy` log appear even though HTTP requests were not handled cleanly?
5. In the demo, why must `server.shutdown=graceful` be enabled on Boot 3.3?
6. Using two terminals, run `/work?seconds=8` and send `SIGTERM`; record whether the request finishes or gets interrupted.
7. Restart the JAR, send `SIGKILL` to the exact demo PID; explain the result.
8. Test Stop/Exit in your IDE, recording exact version and OS. Does it traverse the same lifecycle?
9. Why should you launch the JAR directly when comparing signal behavior rather than running via `mvn spring-boot:run`?
10. On Windows, why can't Unix `kill -TERM` serve as a default test?
11. Write an `AnnotationConfigApplicationContext` test verifying `SmartLifecycle.stop` and `@PreDestroy` without OS signals.
12. If a request already returned its response while an async job keeps running, does HTTP graceful shutdown wait for the job?
13. Why must `stop(Runnable callback)` not invoke the callback right after enqueueing the drain task?
14. Why doesn't `Future.get(timeout)` cancel a blocking HTTP call by itself?
15. If Kubernetes kills a Pod before Spring's timeout expires, what happens to pending jobs?
16. What must a message consumer do before its connection factory is destroyed?
17. Write a shutdown test plan with a 5-second request, a 20-second grace period, and a forced-kill test.
18. List safety mechanisms for unexpected JVM crashes: transactions, outboxes, queues, retries, idempotency.
19. Distinguish `System.exit`, `Runtime.halt`, and `context.close`.
20. Why shouldn't you expose an unprotected shutdown endpoint just for debugging?
21. If you observe `DEMO CONTEXT closing` without `DEMO BEAN preDestroy`, what should you investigate next?
22. If `Ctrl+C` in a terminal running Maven fails to stop the child JVM cleanly, what should you check?
23. Propose a production shutdown runbook covering traffic drain, worker drain, resource closure, and timeout fallbacks.
24. Compare what a context-closing unit test proves vs. a `SIGTERM` experiment on a real process.
25. Explain why a system still needs force-kill handling even when every service configures graceful shutdown.

**Passing criteria:** do not equate IDE Stop with graceful shutdown; know how to send controlled stop signals for your OS/JVM; read `ContextClosedEvent`, `SmartLifecycle`, and `@PreDestroy` logs accurately; understand that shutdown timeout, HTTP drain, and job drain are distinct concepts; and design recovery when a process cannot run cleanup.

## 13. Official Documentation and References

- Spring Boot 3.3 — Graceful Shutdown, timeout configuration, and IDE shutdown warning: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — SpringApplication and application events lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — SmartLifecycle API and `stop(Runnable)`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `AbstractApplicationContext.close()`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Java 21 — JVM shutdown hooks, Runtime API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html
- JetBrains IntelliJ IDEA — Run tool window, Stop/Exit/Kill Process: https://www.jetbrains.com/help/idea/run-tool-window.html
- JetBrains IntelliJ IDEA — Running Applications, Stop vs Exit: https://www.jetbrains.com/help/idea/running-applications.html
- Linux man-pages — `signal(7)`, `SIGTERM`/`SIGKILL`: https://man7.org/linux/man-pages/man7/signal.7.html
