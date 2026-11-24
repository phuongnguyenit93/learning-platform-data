# Keeping the JVM Alive with spring.main.keep-alive

## 1. The problem: the application logs “Started” yet the JVM terminates on its own

In **Spring Boot 3.3.x** applications using **Java 21+ and virtual threads**, a confusing scenario occurs when the program starts up successfully, `ApplicationContext` refreshes, even an `@Scheduled` bean exists, yet the Java process **exits right after `main` returns**. This may not be an exception or a Spring initialization failure.

To understand the cause, distinguish:

1. **Spring Boot started successfully:** The container initialized, runners completed, and `SpringApplication.run(...)` returned an `ApplicationContext`.
2. **Scheduled background work exists:** `@Scheduled` or an executor may be waiting for the next run interval.
3. **The JVM still has a reason to stay running:** Per JVM rules, a standard Java process can terminate when only **daemon threads** remain; they **do not keep the JVM alive**.
4. **Spring Boot is instructed to sustain the JVM:** `spring.main.keep-alive=true` provides a mechanism so the JVM stays alive even when all remaining threads are daemon threads, such as all being virtual threads.

In Java 21, **virtual threads are always daemon threads**. Therefore, when an application relies solely on a scheduler or tasks executed on virtual threads to sustain the process, `SpringApplication.run(...)` returning can let the JVM exit before the next scheduled task cycle.

The solution recommended by official Spring Boot 3.3 documentation:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

**Very important limitation:** `spring.main.keep-alive` does not mean “keep every task alive until completion” and does not turn daemon virtual threads into non-daemon threads. It only resolves **the JVM survival condition** when no other non-daemon threads remain. Tasks can still fail, be cancelled, hang, or not be scheduled as expected.

This lesson explains the JVM mechanism, Spring Boot configuration, when to use it, a runnable Java 21+ example, how to verify it, and common misconceptions. Content is verified against **Spring Boot 3.3.13 / Spring Framework 6.1.x**; do not treat defaults or syntax from newer Boot major versions as defaults for Boot 3.3.

## 2. Daemon threads, platform threads, and virtual threads

### 2.1. When does the JVM exit on its own?

In the standard Java model, the JVM can begin its shutdown sequence when **all remaining live threads are daemon threads**. A live non-daemon thread is a reason for the JVM to stay running; a daemon thread **does not prevent** shutdown from starting.

One way to visualize it:

```text
JVM running
    |
    +--> main thread: platform, non-daemon
    |
    +--> background virtual thread: daemon
    |
    +--> scheduler/task virtual threads: daemon
    |
    +--> main() finishes, no other non-daemon threads remain
           |
           +--> Only daemon threads left
           |
           +--> JVM can begin shutdown
           |
           +--> Unfinished virtual threads may be stopped
```

This rule **does not depend** on whether Spring beans were initialized or `@Scheduled` registered successfully. Java does not “count pending jobs” to decide JVM survival; the JVM evaluates threads according to daemon/non-daemon semantics and shutdown mechanisms.

### 2.2. Java 21 virtual threads are always daemon

Java 21 provides virtual threads as `Thread` instances implemented by the JVM under a lightweight thread model. They suit workloads with many I/O-waiting tasks, yet two points must not be confused:

- A virtual thread **is still a thread** under the Java API, though scheduled differently from a traditional platform thread.
- A virtual thread **is always a daemon thread**, with no option to change it to non-daemon. You cannot use `setDaemon(false)` to turn a virtual thread into a JVM keep-alive tool.

Even when `thread.isAlive()` is true, if it is a daemon thread, by itself it **does not keep the process alive** after all non-daemon threads end.

### 2.3. Standalone Java 21 program confirming daemon behavior

Create **`VirtualThreadDaemonFact.java`** (no Spring dependency):

```java
public class VirtualThreadDaemonFact {
    public static void main(String[] args) throws InterruptedException {
        Thread virtual = Thread.startVirtualThread(() -> {
            Thread t = Thread.currentThread();
            System.out.println("virtual=" + t.isVirtual());
            System.out.println("daemon=" + t.isDaemon());
        });

        virtual.join(); // Just wait for printing to finish for stable stdout.
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac VirtualThreadDaemonFact.java
java VirtualThreadDaemonFact
```

Exact stdout:

```text
virtual=true
daemon=true
```

`join()` in the example **does not make the virtual thread non-daemon**. It only makes the **non-daemon main thread** wait until the virtual thread finishes printing, giving reliable output. Without `join()` and if main exits too early, there is no guarantee the virtual thread prints in time.

This is the exact boundary to understand before using `spring.main.keep-alive`: no Java API by default forces the JVM to wait for all virtual threads to finish once main has no work left.

## 3. What related settings does Spring Boot 3.3 have?

| Property / API | Meaning | What NOT to infer |
| --- | --- | --- |
| `spring.threads.virtual.enabled=true` | Enables Boot-supported integrations to use virtual threads on Java 21+ | Does not automatically switch all libraries/`new Thread(...)` calls to virtual |
| **`spring.main.keep-alive=true`** | Keeps JVM running even when no other non-daemon threads remain | Does not force all background tasks to finish and does not prevent crashes |
| `spring.main.keep-alive=false` | **Default** in Boot 3.3 | Does not force JVM to exit; another non-daemon thread can still keep JVM alive |
| `SpringApplication.setKeepAlive(boolean)` | Configures keep-alive behavior via Java bootstrap API, available since Boot 3.2 | Does not change the daemon flag of virtual threads |
| `@EnableScheduling` | Enables Spring to detect and register `@Scheduled` methods | Does not automatically guarantee the process stays alive if only daemon threads remain |
| `@Scheduled` | Schedules method runs per fixed rate/delay/cron | Does not create a JVM rule “must wait for all scheduled runs” |
| `spring.task.scheduling.pool.size` | Tunes scheduler using pool-based implementation | Does not have the same effect on virtual-thread scheduler `SimpleAsyncTaskScheduler` |
| `spring.task.execution.pool.keep-alive` | Controls idle timeout of pool workers in pool-based executor | **Not** `spring.main.keep-alive` and does not keep the whole JVM alive |
| `server.tomcat.keep-alive-timeout` | HTTP keep-alive timeout on Tomcat connector | Unrelated to the JVM exiting when only daemon threads remain |

Two properties to coordinate:

```properties
# Automatically use virtual threads in Boot 3.3 supported integrations.
spring.threads.virtual.enabled=true

# Ensure the JVM does not exit merely because no non-daemon threads remain.
spring.main.keep-alive=true
```

In Boot 3.3.x, `spring.main.keep-alive` is a **boolean**, **default false**. It can be placed in `application.properties`, `application.yml`, or any Boot-supported configuration source. If overridden via command-line option, consider externalized configuration precedence.

**Version requirement:** `spring.threads.virtual.enabled=true` only applies when running Java 21 or newer. Spring Boot 3.3 supports Java 17 as a baseline, yet **Java 17 lacks the official virtual threads API** needed to run this lesson. Hence the example below requires **JDK 21**—do not use Java 17 and simply set the property.

### 3.1. Since which version has Spring Boot solved this?

`SpringApplication.setKeepAlive(boolean)` and the `spring.main.keep-alive` property have existed since **Spring Boot 3.2**. This is not syntax newly introduced in Boot 4. Boot 3.3.13 documentation continues to recommend enabling it for virtual-thread applications to prevent the JVM from exiting due to a lack of non-daemon threads.

### 3.2. Must virtual threads be enabled for keep-alive to work?

**No.** The contract of `spring.main.keep-alive=true` is to keep the JVM alive when no non-daemon threads remain; virtual threads are simply an **important case** because they are always daemon. A non-web app with only manually created daemon threads can hit the exact same issue.

Conversely, if an application uses **platform non-daemon threads** sustained by another server/executor, the JVM may keep running even with `spring.main.keep-alive=false`. That is why you cannot look at a live process and conclude the property was applied.

## 4. @Scheduled and virtual threads: why doesn't the scheduler hold the process?

Spring Boot 3.3 can auto-configure a scheduler when the application uses `@EnableScheduling`. With Java 21+ and `spring.threads.virtual.enabled=true`, the auto-configured scheduler is **`SimpleAsyncTaskScheduler` using virtual threads**, instead of the default pool-based scheduler used when virtual threads are disabled.

Example of a bean:

```java
@Component
class CleanupTick {
    @Scheduled(initialDelay = 1000L, fixedRate = 1000L)
    void run() {
        System.out.println("periodic cleanup");
    }
}
```

This is an **illustrative snippet**, requiring `@EnableScheduling`, imports, and a valid Spring application. On context refresh, the method is registered to run at appropriate times. However:

- “The method has been scheduled” only means the scheduler knows the schedule.
- “The method will eventually be called” depends on the JVM process **still existing** and the scheduler staying active.
- When `spring.main.keep-alive=false`, if no non-daemon threads remain, the JVM can exit before the next scheduled run.
- When `spring.main.keep-alive=true`, Boot keeps the JVM alive so the scheduler can continue creating and running scheduled ticks, **without automatically guaranteeing every tick succeeds**.

### 4.1. fixedRate, fixedDelay, and SimpleAsyncTaskScheduler

Spring Framework 6.1 `SimpleAsyncTaskScheduler` is designed for virtual threads: it has one coordinating thread and typically launches each periodic execution on a separate thread.

Note carefully:

- **`fixedRate` or cron:** better suited to the virtual-thread-per-task mechanism recommended by Spring Framework.
- **`fixedDelay`:** on `SimpleAsyncTaskScheduler`, fixed-delay tasks execute on **a single scheduler thread**, rather than following the “new virtual thread per run” model of fixed-rate/cron. Using fixed-delay for blocking tasks can therefore bottleneck the scheduler.
- Pool settings like `spring.task.scheduling.pool.size` **do not behave as they do with ThreadPoolTaskScheduler** in virtual-thread mode.

Illustrative example:

```java
@Scheduled(fixedRate = 5000)
public void poll() {
    // Every 5 seconds attempts to start a run per fixed-rate semantics.
}
```

This is an illustrative method snippet; actual execution still depends on the scheduler, system load, and overlap handling. **fixedRate does not guarantee a prior task finished before the next one starts**. If overlap is disallowed, enforce concurrency control or use an appropriate design mechanism rather than picking fixedRate solely to leverage virtual threads.

### 4.2. @Async has a similar boundary

`@Async` typically submits work to an executor and returns to the caller per its asynchronous contract. If an `ApplicationRunner` calls `@Async` and returns immediately, Boot can publish `ApplicationReadyEvent` while the work is still running. Enabling `spring.main.keep-alive` does not alter this boundary: it only stops the JVM from exiting due to a lack of non-daemon threads, **does not await Futures**, and does not turn async failures into startup failures.

Work required before readiness must use an await/timeout mechanism or a dedicated readiness gate.


## 5. Runnable example: Spring Boot 3.3.13 + Java 21 + @Scheduled

The example uses a **non-web** application to eliminate embedded Tomcat/Netty effects and isolate the JVM keep-alive mechanism. With `spring.main.keep-alive=true`, the program stays running after `main` prints its completion message while scheduled ticks fire. With keep-alive off, if no other non-daemon threads remain, the JVM normally terminates without waiting for future ticks.

### 5.1. Create the Gradle project

Create a Gradle Groovy project with a **JDK 21-compatible Gradle Wrapper** and the following files. Use **Java toolchain 21**, not 17.

File **`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

File **`settings.gradle`**:

```groovy
rootProject.name = 'keepalive-virtual-lab'
```

File **`src/main/resources/application.properties`**:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR

spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

This is a non-web application: there is no HTTP listener creating an unintended extra non-daemon thread. The experiment focuses on the auto-configured scheduler with virtual threads enabled.

### 5.2. Write Java in the proper package/file

Create **`src/main/java/com/example/keepalive/KeepAliveVirtualApplication.java`**:

```java
package com.example.keepalive;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableScheduling
public class KeepAliveVirtualApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(KeepAliveVirtualApplication.class, args);

        System.out.println("MAIN: run returned; active=" + context.isActive());
        // Do not close context manually: we want to observe Boot keeping the JVM alive.
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY: Spring Boot startup completed");
    }

    @Component
    public static class TickJob {

        private final AtomicInteger count = new AtomicInteger();

        @Scheduled(initialDelay = 1500L, fixedRate = 1000L)
        public void tick() {
            Thread current = Thread.currentThread();
            System.out.println(
                    "TICK " + count.incrementAndGet()
                            + ": virtual=" + current.isVirtual()
                            + ", daemon=" + current.isDaemon());
        }

        @PreDestroy
        public void onDestroy() {
            System.out.println("STOP: bean destruction callback");
        }
    }
}
```

The code above is **a complete Spring Boot program in one Java file**. Package, class name, starter, and annotation imports are consistent.

**Detail-by-detail explanation:**

1. `@SpringBootApplication` creates the application context per configuration. `@EnableScheduling` activates detection of `@Scheduled` methods.
2. `spring.main.web-application-type=none` clarifies this is not a web server; process survival cannot be attributed to an HTTP connector.
3. `spring.threads.virtual.enabled=true` instructs Boot to auto-configure a virtual-thread-capable task scheduler on Java 21.
4. `spring.main.keep-alive=true` instructs Boot to keep the JVM running even when no non-daemon threads from other components remain.
5. `tick()` prints `Thread.currentThread().isVirtual()` and `isDaemon()`. With the auto-configured virtual scheduler in the sample config, fixed-rate runs execute on virtual threads, typically showing `virtual=true, daemon=true`.
6. `initialDelay=1500L` delays the first run after scheduling is registered; `fixedRate=1000L` specifies the desired interval between starts. Actual tick timing depends on load and scheduler.
7. `@EventListener(ApplicationReadyEvent)` marks startup completion. `SpringApplication.run(...)` returns after runners and the normal ready path.
8. `main` prints `context.isActive()` and **does not close the context**. That is an intentional choice to observe keep-alive; using `try-with-resources` to close the context immediately would stop the scheduled bean and end the keep-alive experiment.
9. `@PreDestroy` illustrates the shutdown callback when the context closes cleanly. Do not treat it as proof callbacks always run on SIGKILL/crash.

### 5.3. Build and run commands

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar
```

macOS/Linux:

```bash
./gradlew bootJar
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar
```

Run with **JDK 21+**. If multiple JDK versions exist in the terminal, check `java -version`, `javac -version`, and the Gradle toolchain.

An **illustrative output sample** during a steady run (tick counts and log positions vary over time):

```text
READY: Spring Boot startup completed
MAIN: run returned; active=true
TICK 1: virtual=true, daemon=true
TICK 2: virtual=true, daemon=true
TICK 3: virtual=true, daemon=true
...
```

**This is not an absolute ordering guarantee between the MAIN line and the first tick**. `@Scheduled` has its own schedule; if startup is delayed, a tick might appear earlier than MAIN. What to observe is that **after `main` returns, the process stays alive and future ticks keep appearing** thanks to keep-alive.

When ready to stop, send a controlled stop signal per your operational workflow, e.g., Ctrl+C in a direct terminal or SIGTERM in a container. During normal shutdown, beans get a chance to run `@PreDestroy`. Do not rely on the callback if forcefully killed.

### 5.4. Control run: disable keep-alive

Without editing Java, just override the property on the command line:

```bash
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar --spring.main.keep-alive=false
```

In an environment where only daemon/virtual background threads remain after main ends, the JVM **can and usually will exit** instead of staying up waiting for the scheduler. You may see `READY` and `MAIN`, yet no subsequent ticks or fewer ticks because the process no longer exists.

**Do not assert an exact stdout line count for the keep-alive=false run**: startup speed, time to first tick, other threads created by agents/libraries/launchers, and shutdown timing all matter. When false, the property **does not force the JVM to exit**; it simply stops SpringApplication from supplying a keep-alive reason. If another non-daemon thread is alive, the process can still continue.

### 5.5. Second control: disable virtual threads while keeping keep-alive

Run:

```bash
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=false --spring.main.keep-alive=true
```

When virtual threads are off, the default auto-configured scheduler is typically `ThreadPoolTaskScheduler` using platform threads. `Thread.currentThread().isVirtual()` in ticks will be `false` if no custom scheduler exists. Even so, `spring.main.keep-alive=true` still takes effect because it is a `SpringApplication`-level property, independent of whether virtual threads are active.

This difference lets you test two **independent** axes:

- `spring.threads.virtual.enabled` governs execution style of Boot auto-configured integrations.
- `spring.main.keep-alive` governs whether the application requests keeping the JVM alive when no other non-daemon threads remain.

### 5.6. Keeping the JVM alive does not guarantee jobs succeed

Even while ticks repeatedly print `virtual=true`, inside the method you might call an external API and hit exceptions or timeouts. The `spring.main.keep-alive` property does not retry tasks, wait for previous batches, create error handlers, check idempotency, or verify business outcomes.

Tests should record both **process status** and **task results** rather than just one of them.


## 6. Configuring via Java instead of application.properties

Spring Boot 3.3 provides the public API `SpringApplication.setKeepAlive(boolean)`:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(KeepAliveVirtualApplication.class);
    application.setKeepAlive(true);
    application.run(args);
}
```

This is **an illustrative replacement for the current main**, not to be pasted alongside the old main in the same file. Import `org.springframework.boot.SpringApplication` and the real application class. `setKeepAlive(true)` serves the same purpose: keeping the JVM alive when no non-daemon threads remain.

In applications with clear externalized configuration, **properties are usually preferred** for easier per-environment and deployment changes. If configured via both the API and properties/arguments, verify the effective configuration rather than guessing precedence across custom bootstraps.

### 6.1. Equivalent application.yml

```yaml
spring:
  main:
    keep-alive: true
  threads:
    virtual:
      enabled: true
```

This is **an alternative** to `application.properties`; there is no need to use both at once without intent. Exact property names are `spring.main.keep-alive` and `spring.threads.virtual.enabled`.

### 6.2. Environment variables and command line

In deployment systems with externalized configuration, properties can be set via environment variables or arguments:

```text
SPRING_MAIN_KEEPALIVE=true
SPRING_THREADS_VIRTUAL_ENABLED=true
```

The two lines above illustrate relaxed-binding environment variable names, not universal shell assignment commands across all OSes. For a process entrypoint, a less error-prone approach is the command line:

```bash
java -jar app.jar --spring.main.keep-alive=true --spring.threads.virtual.enabled=true
```

`app.jar` is an illustrative filename; for section 5's project, use `keepalive-virtual-lab-0.0.1-SNAPSHOT.jar`.

What must be verified is not just that the key exists in a config repository, but that the process **actually receives the right property value**, runs the right JDK, and uses the right Boot version. Do not mistake an un-injected environment variable name for an active configuration.

## 7. Which situations require enabling keep-alive?

| Application type | Risk of having no non-daemon threads | Recommendation |
| --- | --- | --- |
| Non-web app with only `@Scheduled` running on virtual threads | **Yes** | Enable `spring.main.keep-alive=true` to keep JVM alive |
| Consumer/job poller app using virtual-thread executor | **Possible** | Inspect threads and ownership; consider keep-alive |
| Servlet/Reactive web app using virtual threads | Depends on server, connector, actual threads | Enabling keep-alive is a safe measure per Boot docs; do not assume an open port guarantees JVM survival forever |
| One-shot CLI that must exit when done | **Undesirable** to keep process alive forever | Do not enable keep-alive; close context explicitly if needed |
| Spring Batch/command-line tool with job-driven lifecycle | Needs process exit per job result | Design exit codes/shutdown and avoid keeping JVM alive unnecessarily |
| App with persistent non-daemon platform workers | May not hit daemon-only exit risk | Keep-alive may not be needed, yet do not substitute it for lifecycle ownership |
| Integration framework spawning its own non-daemon threads | Depends on implementation and configuration | Verify in practice; do not infer from library names |

**Do not treat `spring.main.keep-alive=true` as an “always-right setting for every Java application”.** For one-shot CLIs/jobs, the right goal is **completing work and exiting**. Enabling keep-alive without an explicit shutdown mechanism can make CI/CD pipelines or batch orchestrators **hang forever** even after work is done.

### 7.1. Case where a web server already opened a port

A web server may have non-daemon threads keeping the JVM active. However, this depends on the embedded server, virtual-thread integration, and configuration. Spring Boot still recommends enabling keep-alive for virtual-thread applications to avoid accidental dependence on some other background thread.

On the other hand, **keeping the JVM alive does not guarantee the HTTP server is healthy**. The port might be wrong, the context might not be ready, a runner might fail, or the web server might have closed. Combine readiness/liveness, logs, and proper probes.

### 7.2. Case of periodic scheduled tasks

If a service is responsible for running hourly/daily, the scheduler must be allowed to survive until the next run. A sleeping daemon virtual thread or a scheduler holding a cron expression **is not enough** to ensure the process stays alive until then. `spring.main.keep-alive=true` fixes why the JVM exits in daemon-only configurations; scheduling and business success still require separate observation.

### 7.3. Case where a single task has finished

If an application only runs one `ApplicationRunner` to export a report and then wants to exit, keeping the JVM alive “just in case” can hang the command even after the runner returns. Do not use keep-alive for this purpose; manage resources and close the context once work is complete.

## 8. Keeping the JVM alive is not keeping the Spring context running unconditionally

Separate **process existence** from **ApplicationContext existence and state**.

- `spring.main.keep-alive=true` tells SpringApplication to keep the JVM alive when no other non-daemon threads remain; it does not replace context lifecycle management.
- If the application **explicitly calls `context.close()`**, scheduler/executor beans in the context can be stopped and destruction callbacks can run. Do not expect `@Scheduled` to keep firing after the context closes.
- If the application **calls `System.exit(...)`**, the JVM shuts down per its contract. Keep-alive does not block an intentional exit call.
- If the OS/container sends SIGTERM and the shutdown hook runs normally, Spring gets a chance to close the context and clean up resources. `spring.main.keep-alive` is not a “lock” against termination signals.
- If hit by SIGKILL, VM crash, host power loss, or severe OOM, Java callbacks or background tasks cannot be guaranteed to finish.
- If tasks are submitted to an in-RAM queue, keep-alive does not turn it into a durable queue surviving restarts.

**Especially with `try-with-resources`:** in this demo, **do not** write:

```java
try (ConfigurableApplicationContext context =
        SpringApplication.run(KeepAliveVirtualApplication.class, args)) {
    System.out.println("main done");
}
// context.close() here may stop scheduled beans.
```

This is an **anti-example relative to running a long-lived scheduler**, not invalid Java syntax. `try-with-resources` is very useful for batch programs with a defined end point; however, wrapping `SpringApplication.run` and immediately leaving the block closes the context and stops scheduled work per lifecycle.

### 8.1. Keep-alive is not waiting on a Future

Suppose a runner does:

```java
@Override
public void run(ApplicationArguments args) {
    executor.submit(() -> preloadRequiredCatalog());
    // Runner returns without awaiting the Future.
}
```

This is an **illustrative snippet**, requiring `executor`, `preloadRequiredCatalog`, and a real runner class. Even with keep-alive=true, Boot can still publish `ApplicationReadyEvent` once the runner returns. The property only prevents JVM termination from daemon-only threads; it **does not automatically call `Future.get`**.

If preloaded data is mandatory for readiness, await the task with a timeout, propagate exceptions, or design a readiness health gate. Keep-alive is no substitute for distinguishing “submitted” from “completed”.

### 8.2. Keep-alive does not convert daemon threads into non-daemon threads

`Thread.currentThread().isDaemon()` on a virtual thread remains `true`. Keep-alive is an **application/JVM-level** solution, not altering attributes of created virtual threads. Hence in the experiment you can simultaneously observe:

```text
TICK ... virtual=true, daemon=true
```

while the JVM remains alive after main returns. The two facts do not contradict each other.

## 9. Shutdown, SIGTERM, and running in containers

In Spring Boot 3.3, `SpringApplication` registers a JVM shutdown hook by default so the context has a chance to close cleanly when the process is asked to stop. The related property is:

```properties
spring.main.register-shutdown-hook=true
```

This is the default value; no need to declare it unless required otherwise. **It differs from `spring.main.keep-alive`**:

- **keep-alive:** prevents the JVM from exiting solely because no non-daemon threads remain.
- **register-shutdown-hook:** gives the Spring context a chance to clean up while the JVM is shutting down.
- **graceful shutdown:** policy for stopping the web server / lifecycle components, handling in-flight requests or tasks within configured limits and deadlines.

If the application has a web server, graceful shutdown can be configured as appropriate:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

These two properties **are not a way to keep the JVM alive** and do not force every async task to complete. Shutdown timeouts must be coordinated with Kubernetes `terminationGracePeriodSeconds`, health/readiness probes, I/O timeouts, and retry/idempotency mechanisms.

### 9.1. Kubernetes restart loops and keep-alive

Suppose a non-web scheduler Deployment uses virtual threads; with `spring.main.keep-alive=false`, the JVM can exit 0 right after startup. A Kubernetes Deployment defaults to `restartPolicy=Always` per standard Pod template behavior; the container can be restarted continuously. Looking at logs, you may see repeated startups with no Java exception.

Do not rush to alter `restartPolicy` or put `Thread.sleep(Long.MAX_VALUE)` in main. Check:

1. Are only daemon virtual threads remaining?
2. Is `spring.threads.virtual.enabled` actually enabled?
3. What is `spring.main.keep-alive` set to?
4. Is there a web server/non-daemon worker holding the process?
5. Is this a **Deployment service** meant to run continuously or a **CronJob/Job** meant to finish and exit?

If it is a one-off CronJob, exit 0 after finishing may be **by design**. Do not force the process to stay up forever just because “the pod keeps ending”.

### 9.2. When is real cleanup needed?

For long-running schedulers/consumers, let `ApplicationContext` manage owned resources and close threads/executors, connection pools, and message consumers via lifecycle callbacks or appropriate `SmartLifecycle`. Do not rely on keep-alive just to keep the process up while ignoring:

- timeouts and interruption handling;
- stopping acceptance of new work during shutdown;
- handling in-flight tasks within bounds;
- releasing owned resources;
- emitting proper readiness status if serving traffic;
- recovering unfinished jobs after an abnormal process death.

## 10. Easily confused “keep alive” properties

| Name / concept | Scope | How it differs from `spring.main.keep-alive` |
| --- | --- | --- |
| **`spring.main.keep-alive`** | SpringApplication/JVM process lifetime | Keeps JVM alive when no non-daemon threads remain |
| `spring.task.execution.pool.keep-alive` | Executor pool worker idle timeout | Only how long pool threads wait when idle |
| `server.tomcat.keep-alive-timeout` | HTTP connector connection persistence | HTTP keep-alive wait time between requests |
| HTTP `Connection: keep-alive` | HTTP protocol / client-server connection | Does not keep JVM alive under daemon rules |
| TCP `SO_KEEPALIVE` | Socket-level liveness probe | Unrelated to Java daemon threads |
| Database connection pool idle/maxLifetime | DB connection lifecycle management | Does not determine whether JVM has non-daemon threads |
| `Thread.sleep(...)` in `main` | Blocks the current thread | Not a standard Boot lifecycle configuration |
| `Future.get()` | Waits for one specific computation | Not a mechanism to keep periodic services alive forever |

In particular, do not mistake **`spring.task.execution.pool.keep-alive=60s`** for a way to stop the JVM from exiting. The names look similar, yet they are two completely different concerns. When a virtual-thread executor is enabled, several pool-based tuning properties are even **ignored** per Boot docs because the pool-based model no longer applies.

## 11. Why shouldn't you spawn a non-daemon thread that sleeps forever?

A workaround sometimes seen:

```java
new Thread(() -> {
    while (true) {
        try {
            Thread.sleep(60_000);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return;
        }
    }
}, "fake-keep-alive").start();
```

This is an **anti-example** for spotting code smells, not an implementation recommendation. Because `new Thread(...)` creates a standard non-daemon platform thread (when not inherited from a daemon creator thread), it can keep the JVM alive. However:

- Stopping/interrupting and managing the lifecycle of the “keeper thread” becomes the application's burden.
- If you forget to stop the thread, CLI/batch tasks can hang and fail to exit.
- The extra thread does not monitor the scheduler, handle failures/readiness, or fix resource leaks.
- When the JVM receives a shutdown signal, it does not replace standard cleanup callbacks.
- A bug in this thread creates yet another component to monitor.

With Spring Boot 3.3.x, using **`spring.main.keep-alive=true`** when the problem is genuinely daemon-only JVM exit is clearer, involves less boilerplate, and is supported by the framework.

### 11.1. Do not “fix” by blocking main indefinitely

`Thread.currentThread().join()` inside main itself or a `while(true) Thread.sleep(...)` can keep the process alive, yet makes code harder to reason about and application shutdown unclear. The process can still be killed, background tasks can still fail, and decoupling lifecycle from Spring easily causes readiness mismatches.

If the goal is a long-running service, use Boot lifecycle and proper orchestration instead of holding a meaningless platform thread.


## 12. Diagnosis: JVM exited right after Started

A systematic investigation workflow:

**Step 1 — check whether there is a real startup failure.** Look for `ApplicationFailedEvent`, stack traces, port binding errors, runners throwing exceptions, exit codes, and container logs. If an exception occurred, keep-alive does not fix startup failures.

**Step 2 — verify the right Java runtime.** Run:

```bash
java -version
```

Java **21+** is needed when enabling virtual threads. Do not run `Thread.isVirtual()` examples on Java 17.

**Step 3 — check application type.** Applications without a web starter or setting `spring.main.web-application-type=none` normally lack a web connector keeping the process up. That is normal for schedulers/batch jobs, not a bug.

**Step 4 — verify effective properties.** Confirm:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

If overridden in a container/command line, make sure the exact process received the right values rather than checking the wrong config file or profile.

**Step 5 — inspect threads and scheduler.** Inside the running method, log:

```java
Thread t = Thread.currentThread();
System.out.println("virtual=" + t.isVirtual()
        + ", daemon=" + t.isDaemon());
```

This is an **illustrative Java 21+ snippet**, not a standalone file. If using a custom scheduler or manually declared executor, it may differ from Boot's auto-configured scheduler; do not assume every thread is virtual solely from the property.

**Step 6 — test comparing true/false.** Using the exact `.jar` from section 5, run `--spring.main.keep-alive=true` and then `false`, observing whether the process keeps printing ticks. Test directly in a terminal, separate from launchers like Gradle/IDE, without relying on a fixed tick count.

**Step 7 — distinguish process death from inactive tasks.** If the process stays running yet `@Scheduled` prints nothing, the method may not be scanned, `@EnableScheduling` may be missing, the schedule may be wrong, triggers disabled, exceptions thrown, scheduler stopped, or logs filtered. Keep-alive does not fix those issues.

**Step 8 — distinguish ready from alive.** `ApplicationReadyEvent` only marks Boot startup completion. It does not guarantee a periodic task has come due, and does not replace health/monitoring for a scheduler service.

### 12.1. Common symptoms table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Logs “Started …”, then process exits 0 with no exception | Only daemon/virtual threads remain, keep-alive disabled | Enable `spring.main.keep-alive=true` if truly a long-running service |
| Process keeps running when keep-alive=false | Another non-daemon thread exists | Do not treat false as a force-exit command |
| Keep-alive enabled yet `@Scheduled` does not run | Scheduling not enabled, bean not scanned, wrong trigger, error/blocked task | Check `@EnableScheduling`, bean registration, and logs |
| Boot reports ready before mandatory init job finishes | Runner submits async and returns | Await Future/ack or use a readiness gate |
| JVM exits despite `@Async` virtual thread doing I/O | Daemon virtual thread does not hold JVM | Keep-alive for long-running services plus proper ownership/await |
| Enabling keep-alive stops CLI job from exiting | No app-closing mechanism, keeps process forever | Disable property for batch or close context/exit properly |
| Virtual threads enabled yet task stays platform | Custom executor/scheduler or integration not applying virtual | Inspect executor type and `Thread.isVirtual()` |
| Tuning `spring.task.scheduling.pool.size` has no effect | Boot uses `SimpleAsyncTaskScheduler` when virtual enabled | Choose proper concurrency, scheduling, and metrics policies |
| Long `fixedDelay` slows down the scheduler | With SimpleAsyncTaskScheduler, fixed-delay runs on one scheduler thread | Consider fixedRate/cron and overlap limits per contract |
| Container restart loop despite Java exit 0 | Periodic service meant to stay up forever, yet daemon-only process exits | Choose keep-alive or switch workload to proper Kubernetes Job/CronJob |
| SIGTERM stops app despite keep-alive=true | Keep-alive does not resist termination signals | Distinguish normal shutdown from daemon-only exit |
| Only sees ticks a few times then stops | Process stopped, scheduler shut down, method errored, or other thread stalled | Check process lifetime, context lifecycle, and error logs |
| Web app has open port yet is not ready | Readiness differs from socket binding | Check `ApplicationAvailability`/readiness probe |
| @Scheduled method throws exception yet JVM stays alive | Keep-alive does not handle task exceptions | Logging/alerts/retries/idempotency; handle failure in task |

### 12.2. Production observability tips

For long-running scheduler/consumer applications:

- Track process up/down, restart counts, and exit codes.
- Track last task execution `lastRunAt`, last success `lastSuccessAt`, duration, and failure count.
- Track backlog/job age if queued, not just thread counts.
- Retain task error logs and correlation IDs, avoiding token/secret dumps.
- Add health indicators when needed to show “service can still do work” instead of only “JVM is alive”.
- If work uses external resources, configure I/O timeouts, bounded retries, and post-restart recovery policies.
- Distinguish service readiness/liveness from the completion status of **one specific job**.

Keep-alive is a **lifetime prerequisite**, not an observability or error-handling strategy.

## 13. Self-check questions

**Question 1.** Are virtual threads daemon by default?

**Answer:** Yes. In Java 21, virtual threads are always daemon and do not prevent the JVM from starting shutdown when no non-daemon threads remain.

**Question 2.** What is Boot 3.3's default for `spring.main.keep-alive`?

**Answer:** `false`. Set `true` when the JVM must stay alive even when all remaining threads are daemon.

**Question 3.** Does `spring.threads.virtual.enabled=true` replace `spring.main.keep-alive=true`?

**Answer:** No. One property selects virtual threads in Boot-supported integrations; the other keeps the JVM alive in daemon-only cases.

**Question 4.** Once an `@Scheduled` bean exists, will the JVM definitely wait until the next run?

**Answer:** No. The scheduler knows the schedule, yet daemon threads do not keep the JVM alive. Verify process lifetime.

**Question 5.** Why do non-web applications expose this issue easily?

**Answer:** They may lack a web server/other non-daemon threads; once main finishes, only scheduler/virtual daemon threads remain.

**Question 6.** Does keep-alive=false force the JVM to exit right when main returns?

**Answer:** No. If other non-daemon threads remain, the JVM can still keep running.

**Question 7.** Does keep-alive=true guarantee `@Async` tasks succeed?

**Answer:** No. It does not await Futures, retry, or detect business failures.

**Question 8.** Can Java 17 run `Thread.currentThread().isVirtual()`?

**Answer:** No. The official API for virtual threads in the lab requires Java 21+.

**Question 9.** Why doesn't `spring.task.execution.pool.keep-alive` solve daemon-only JVM exits?

**Answer:** It only configures pool worker idle lifetime, not SpringApplication/JVM keep-alive.

**Question 10.** Does `@Scheduled(fixedDelay=...)` always run on its own virtual thread in `SimpleAsyncTaskScheduler`?

**Answer:** No. With this implementation, fixed-delay executes on a single scheduler thread; Spring Framework recommends fixedRate/cron as better suited for virtual-thread scheduling.

**Question 11.** If main closes the context right after `run`, does keep-alive=true keep scheduled beans running?

**Answer:** Do not expect so. Closing the context proceeds to shut down scheduler beans and corresponding lifecycle resources.

**Question 12.** When the JVM receives SIGKILL, does keep-alive protect running work?

**Answer:** No. It does not resist OS process termination and does not guarantee finally blocks, `@PreDestroy`, or task completion.

**Question 13.** Should a batch app that needs to return an exit code on completion enable keep-alive unconditionally?

**Answer:** No. That can leave the process waiting forever after the job finishes; manage lifecycle and exit per contract.

**Question 14.** Why is HTTP keep-alive timeout not the same as Spring main keep-alive?

**Answer:** HTTP keep-alive governs how long client/server connections stay open, whereas `spring.main.keep-alive` governs whether the JVM keeps running when only daemon threads remain.

## 14. Summary and reference sources

- **Java 21 virtual threads are always daemon**; daemon threads **do not keep the JVM alive** once non-daemon threads finish.
- With Spring Boot 3.3, `spring.threads.virtual.enabled=true` enables virtual-thread support in compatible Boot integrations.
- `spring.main.keep-alive=true` instructs Boot to sustain the JVM even when all remaining threads are daemon/virtual. **Boot 3.3's default is false.**
- The most critical case is a **non-web scheduler with `@Scheduled`** running on virtual threads: being scheduled does not mean the process will wait for ticks.
- Spring Boot 3.3 auto-configures `SimpleAsyncTaskScheduler` when virtual threads are enabled; Spring Framework 6.1 recommends fixedRate/cron over fixedDelay for this execution mode.
- **Keep-alive does not equal task completed, app ready, graceful shutdown, or protection against SIGTERM/SIGKILL.** If background work is mandatory, await Futures or use a readiness gate.
- Do not confuse `spring.main.keep-alive` with pool thread idle keep-alive, TCP keepalive, or HTTP connection keep-alive.
- For batch/CLI apps with a clear end point, avoid holding the JVM alive unnecessarily.

Official documentation:

1. [Spring Boot 3.3.13 — SpringApplication, Virtual Threads](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): Java 21+, daemon threads, and `spring.main.keep-alive` recommendation.
2. [Spring Boot 3.3.13 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.main.keep-alive` default false, task scheduling/execution properties.
3. [Spring Boot 3.3.13 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): `SimpleAsyncTaskScheduler` with virtual threads and ignored pool settings.
4. [Spring Boot 3.3.13 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `setKeepAlive(boolean)`/`isKeepAlive()`, available since Spring Boot 3.2.
5. [Spring Framework 6.1 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): virtual-thread-aligned scheduler and fixedDelay caveats.
6. [Java SE 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): virtual threads are daemon and do not prevent JVM shutdown.

**Conclusion:** If a Spring Boot application uses virtual threads and needs to run long-term, `spring.main.keep-alive=true` is the setting that protects **JVM lifetime**. After solving “the process stays running”, you still must separately build mechanisms confirming “tasks ran, succeeded, can keep serving, and will shut down cleanly when needed”.
