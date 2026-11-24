# Testing Virtual Threads and Observing the Effect of `spring.main.keep-alive`

**Topic:** Spring Boot Application Runtime → **Integrated Practice**. This lab designs a repeatable experiment to verify **virtual threads**, **daemon** status, the effects of the two settings `spring.threads.virtual.enabled` and `spring.main.keep-alive`, `@Scheduled` behavior, and the limits of "keeping the JVM alive". A **Java 21+ / Spring Boot 3.5.x** Maven project includes runnable Java code and a child-process probe program using `ProcessBuilder`. The lab guides observing all three factors: what kind of thread is running, whether the application stays alive after `main()` returns, and whether work actually finishes/cleans up on shutdown.

**Practice question:** Why can a Spring Boot CLI with `@Scheduled` running on a virtual thread **exit immediately after startup**, and why does adding `spring.main.keep-alive=true` keep the process alive until explicitly stopped?

**Version milestone:** `Thread.ofVirtual()`, `Thread.isVirtual()`, and virtual threads became official in **Java 21** (JEP 444). Java 17 **cannot** compile this lab. Use Spring Boot **3.5.x** (e.g., 3.5.16). Spring Boot 3.5 recommends Java 24+ for an improved virtual threads experience, though all sample APIs work starting with Java 21.

> **Core reality:** Virtual threads are **daemon threads**. The JVM does not keep a process alive solely because daemon threads remain. `spring.main.keep-alive=true` is Spring Boot's mechanism to keep the application alive when no other non-daemon threads exist; it does **not** turn virtual threads into non-daemon threads, does not automatically retry work, and does not guarantee protection against losing tasks on a crash or SIGKILL.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish **virtual threads** and **platform threads** using `Thread.currentThread().isVirtual()`.
2. Read `Thread.isDaemon()` and explain the effect of daemon threads on JVM process lifetime.
3. Understand why `spring.threads.virtual.enabled=true` and `spring.main.keep-alive=true` are **two independent settings**.
4. Describe how Spring Boot 3.5 auto-configures `SimpleAsyncTaskScheduler` with virtual threads and `ThreadPoolTaskScheduler` with platform threads under matching conditions.
5. Observe that virtual/daemon scheduler threads may **not keep the JVM alive**, even when `@Scheduled` is registered.
6. Set `spring.main.keep-alive=true` for a background application having only daemon tasks.
7. Create a `@Scheduled(fixedRate=...)` printing `isVirtual()/isDaemon()` and observe periodic execution while the JVM stays alive.
8. Launch a manual virtual thread via `Thread.ofVirtual().start(...)` and understand `main` does not wait for it automatically.
9. Experiment with three scenarios: virtual+no keepalive, virtual+keepalive, platform scheduler+no keepalive.
10. Use an **isolated** `java -jar` process so non-daemon threads from an IDE/Maven/test harness do not skew results.
11. Use `ProcessBuilder.waitFor(timeout)` to determine whether the process exited on its own or stayed alive; do not rely solely on logs.
12. Distinguish `spring.main.keep-alive` from HTTP `Connection: keep-alive`, executor `keepAliveSeconds`, and `@Scheduled` delay.
13. Avoid confusing "process is still alive" with "all tasks were processed successfully".
14. Specify valid stop mechanisms, `@PreDestroy`/`SmartLifecycle`, interruption, and proper owner resource closing.
15. Propose admission control/backpressure, resource quotas, durable queues, and idempotency when work is critical.
16. Interpret results on Java 21/24+, apps with web servers/non-daemon threads, or custom scheduler configurations.
17. Know when **not** to enable keepalive: a CLI/batch job that must finish and return an exit status rather than staying alive forever.
18. Gather sufficient evidence to reproducibly report differences between daemon threads and keepalive.

## 2. Two Settings Solving Two Different Problems

Set in `application.properties`:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Read accurately:

| Property | Question It Solves | Main Behavior |
|---|---|---|
| `spring.threads.virtual.enabled` | Which thread type do supported Spring-managed task/scheduling integrations use? | On Java 21+, Boot uses virtual threads in supported integrations |
| `spring.main.keep-alive` | Is the JVM kept alive when no non-daemon threads remain? | When true, Boot maintains a mechanism keeping the app alive |
| `spring.main.web-application-type=none` | Is there an embedded web server? | Creates no web server, keeping the JVM lifetime experiment clean |
| `spring.main.register-shutdown-hook` | Does Boot register a hook to close the context on JVM shutdown? | Defaults to true; does not replace durability or keepalive |
| `spring.task.scheduling.pool.size` | Number of platform scheduler threads when using a thread pool | Does not cap virtual threads in SimpleAsyncTaskScheduler |

**Spring Boot 3.5 default:** `spring.main.keep-alive=false`. Therefore, when virtual threads are enabled, Spring Boot recommends considering enabling keepalive, especially for apps relying on `@Scheduled` or background tasks to keep the process running.

**Independence:** When `spring.threads.virtual.enabled=false` and `spring.main.keep-alive=true`, Boot can still keep the process alive even though the task scheduler uses platform threads. When virtual=true and keepalive=false, the scheduler may use virtual daemon threads, yet the process is still not guaranteed to remain alive.

### 2.1. Enabling Virtual Threads Does Not Change Every Thread in the JVM

An application still has the main thread, GC threads, runtime/platform carrier threads, web containers, and threads created by libraries themselves. `spring.threads.virtual.enabled=true` affects **integrations supported by Spring Boot**, without forcing every third-party library's `new Thread(...)` to become a virtual thread.

Meanwhile, `Thread.ofVirtual()` creates a virtual thread **regardless** of Spring Boot properties, provided it runs on Java 21+. Thus the lab intentionally checks **two places**:

- `@Scheduled`: uses the scheduler auto-configured by Spring Boot, verifying the framework's virtual threads.
- `Thread.ofVirtual().start(...)`: uses the JDK API, proving a one-shot virtual daemon thread does not keep the JVM alive by itself.

### 2.2. Do Not Equate Daemon with "Running in the Background"

"Background job" is a business concept, whereas `Thread.isDaemon()` is a flag deciding **whether the thread keeps the JVM alive**. A platform thread can be set as daemon; a virtual thread is always daemon. "Doing important work" does not automatically grant a virtual thread permission to keep the process alive.

## 3. JVM Mechanism: When Does a Process Terminate on Its Own?

Per the Java Virtual Threads Guide, virtual threads are instances of `Thread` that are lighter than platform threads and suited for I/O-waiting operations. They are scheduled by the JVM onto platform carrier threads. **Virtual threads are always daemon** and cannot be turned into non-daemon threads to solve process liveness.

~~~text
main thread (platform, typically non-daemon)
   |
   +-- SpringApplication.run(...)
   |      |
   |      +-- create context, beans
   |      +-- register scheduler and scheduled jobs
   |      +-- run ApplicationRunner/CommandLineRunner
   |
   v
main() return
   |
   +-- Any other non-daemon threads remaining?
   |       |
   |       +-- YES -> JVM keeps running
   |       |
   |       +-- NO  -> JVM may start shutdown
   |                     daemon threads do not keep it alive
   |
   +-- spring.main.keep-alive=true?
           |
           +-- Boot helps keep JVM alive when needed
               -> waits for operator/SIGTERM/valid stop
~~~

**Important:** the JVM can shut down because **no non-daemon threads remain**, even while virtual threads are still in `sleep`, `await`, or waiting on network results. When the JVM terminates, daemon threads have no guarantee of finishing every `finally` block or business job like a transaction. During normal shutdown, the application's Java shutdown hooks are triggered; still, unmanaged tasks can be cut short when the process ends.

**Do not misinfer:** a JVM exiting naturally with status 0 does not mean background tasks succeeded; status 0 may merely reflect that `main` completed normally with no exception mapped to an exit code.

## 4. Which Scheduler Does Spring Boot 3.5 Use?

With `@EnableScheduling` and without a custom scheduler overriding the default selection, Boot may auto-configure:

| Condition | Typically Selected Scheduler | How Work Executes |
|---|---|---|
| `spring.threads.virtual.enabled=true`, Java 21+ | `SimpleAsyncTaskScheduler` with virtual threads | A scheduler thread and dedicated threads for suitable scheduled executions |
| `spring.threads.virtual.enabled=false` | `ThreadPoolTaskScheduler` | Pool of platform threads; default typically one thread |
| Custom `TaskScheduler` / `ScheduledExecutorService` bean present | Depends on existing bean/config | Must not assume Boot's default |

**With virtual threads, the scheduler thread is daemon**, per Spring Boot documentation. If a CLI relies solely on that scheduler to keep the program open, the JVM may exit right when `main` returns.

**Note trigger types:** `SimpleAsyncTaskScheduler` has specific behavior for `fixedDelay`: fixed-delay tasks run on the **scheduler thread** to preserve semantics, while fixed-rate/cron executions are typically handed off to separate execution threads. This lab uses **`fixedRate`** to clearly observe `Thread.isVirtual()` inside the scheduled method itself. Do not generalize that every `@Scheduled` trigger behaves identically.

### 4.1. Pool Properties Do Not Govern Virtual Thread Counts

When Spring Boot uses a virtual scheduler, pool settings such as:

~~~properties
spring.task.scheduling.pool.size=4
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
~~~

**do not cap virtual threads the way fixed platform thread pools do**. Do not add them to "keep the JVM alive" or limit every request to the database; they address different concerns and may have no effect on the corresponding virtual integrations.

If a workload spawns huge numbers of virtual threads against a database with a 10-connection pool, the DB still only has 10 configured connections; remaining virtual threads wait, time out, or get rejected. You need admission limits, semaphores/bulkheads, connection timeouts, request deadlines, and quotas aligned with real resources.

### 4.2. `@Async` and `@Scheduled` Are Not Identical Either

`@Scheduled` registers time-triggered work; `@Async` dispatches via a task executor, depending on `@EnableAsync`/bean configuration. When virtual threads are enabled, Boot can provide `SimpleAsyncTaskExecutor` for async task execution, yet a custom `Executor` bean may cause auto-configuration to back off or alter executor selection.

This lab **does not enable `@EnableAsync`**, avoiding another async executor muddying scheduler observations. A virtual thread created via the JDK API is also **not** automatically lifecycle-managed by Spring just because the app enabled the virtual-thread property.

## 5. Designing a Clean, Controlled Experiment

We use a CLI application **without Spring Web**, because an embedded web server can spawn non-daemon threads and keep the JVM alive even when keepalive=false. The app has three parts:

1. `main()`: calls `SpringApplication.run` and then prints `LAB_MAIN_RETURNED`.
2. `@Scheduled(fixedRate=1000, initialDelay=1000)`: prints tick count and `isVirtual/isDaemon`.
3. `ApplicationRunner`: submits a one-shot virtual thread via `Thread.ofVirtual()`, which sleeps 3 seconds and prints `LAB_JOB_DONE` if it gets the chance.

**Key scenarios:**

| Scenario | spring.threads.virtual.enabled | spring.main.keep-alive | Expectation in Non-Web CLI |
|---|---|---|---|
| A | `true` | `false` | Main returns, JVM may exit early before ticks/job complete |
| B | `true` | `true` | JVM stays alive; ticks and one-shot job done appear |
| C | `false` | `false` | Platform scheduler typically has a non-daemon thread; JVM stays alive |
| D (optional) | `false` | `true` | Stays alive; keepalive isn't needed to prove virtual scheduler behavior |

**Do not force an exact timestamp:** tick counts, thread names, and the order of `LAB_JOB_BEGIN`/`LAB_JOB_SUBMITTED` depend on scheduler/JIT/CPU. Observe for at least several seconds; if scenario A stays alive unusually long, check whether libraries, agents, or IDEs spawned non-daemon threads.

### 5.1. Three Independent Claims to Verify

- **Thread type:** `Thread.currentThread().isVirtual()` inside the scheduled method.
- **Daemon status:** `Thread.currentThread().isDaemon()` on the same thread.
- **Liveness:** whether the process **exited on its own** or is still running after 6 seconds, measured from a parent process.

Do not use a single `@Scheduled` log line as the sole proof of keepalive. A process staying alive could be due to a web server, debug agent, manually created thread, or plugin runner—not necessarily `spring.main.keep-alive=true`.

## 6. Creating the Java 21 and Spring Boot 3.5 Maven Project

### 6.1. Structure

Create a project via Spring Initializr:

- Project: **Maven**, Language **Java**, Java **21** (or 24+).
- Spring Boot: **3.5.x**, e.g., **3.5.16**.
- Group: `com.example`.
- Artifact: `virtual-keepalive-lab`.
- Package: `com.example.virtualkeepalive`.
- Dependencies: basic **Spring Boot Starter**; do **not** add Spring Web.
- Packaging: Jar.

~~~text
virtual-keepalive-lab/
  pom.xml
  mvnw                         (if using Maven Wrapper)
  mvnw.cmd
  src/main/java/com/example/virtualkeepalive/
    VirtualKeepAliveLabApplication.java
    HeartbeatTask.java
  src/main/resources/
    application.properties
  ProcessProbe.java            (optional: run using Java source-file mode)
~~~

The two files in `src/main/java` are **compilable on JDK 21** with the corresponding Spring Boot starter. `ProcessProbe.java` uses **only the Java standard library** to launch the JAR and inspect the process. The project needs no database, web server, or broker to test daemon/keepalive behavior.

### 6.2. Complete `pom.xml`

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>virtual-keepalive-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

`spring-boot-starter` brings in Spring Context and Scheduling support. `@EnableScheduling` activates scheduled method processing. Because there is no Spring Web, `web-application-type=none` is explicitly set in properties to avoid environment confusion if dependencies are added later.

### 6.3. Main Class and Virtual One-Shot Worker

File `src/main/java/com/example/virtualkeepalive/VirtualKeepAliveLabApplication.java`:

~~~java
package com.example.virtualkeepalive;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class VirtualKeepAliveLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                VirtualKeepAliveLabApplication.class, args);

        System.out.println("LAB_MAIN_RETURNED");
    }

    @Bean
    ApplicationRunner launchOneShotVirtualJob() {
        return args -> {
            Thread job = Thread.ofVirtual()
                    .name("lab-one-shot")
                    .start(() -> {
                        Thread current = Thread.currentThread();
                        System.out.println("LAB_JOB_BEGIN virtual="
                                + current.isVirtual()
                                + " daemon=" + current.isDaemon());

                        try {
                            Thread.sleep(3_000);
                            System.out.println("LAB_JOB_DONE");
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            System.out.println("LAB_JOB_INTERRUPTED");
                        }
                    });

            System.out.println("LAB_JOB_SUBMITTED virtual="
                    + job.isVirtual()
                    + " daemon=" + job.isDaemon());
        };
    }
}
~~~

**What to understand line by line:**

1. `@SpringBootApplication` registers app config, auto-config, and bean scanning.
2. `@EnableScheduling` enables execution of `@Scheduled` methods in `HeartbeatTask`.
3. `SpringApplication.run(...)` refreshes the context, runs `ApplicationRunner`, and completes startup; then `main` prints `LAB_MAIN_RETURNED`.
4. `Thread.ofVirtual()` creates a JDK virtual thread; it is always daemon, **independent of** `spring.threads.virtual.enabled`.
5. `job.start(...)` runs the task asynchronously; `ApplicationRunner` **does not wait** for the job. The thread may begin executing before the caller prints `LAB_JOB_SUBMITTED`, so the order of those two lines is not fixed.
6. `Thread.sleep(3_000)` creates an observation window: if the JVM loses all non-daemon threads early, `LAB_JOB_DONE` may not appear; if keepalive works, the job gets a chance to finish.
7. `InterruptedException` is handled explicitly and restores the interrupt flag. **Do not assume keepalive interrupts tasks** — sleep may be cut short for other reasons or process termination.
8. Do not call `job.join()` in the runner/main, because that **keeps the non-daemon main thread waiting until the job finishes**, inadvertently masking the behavior under test.
9. The task intentionally **has no lifecycle owner** to show that an unmanaged one-shot daemon job can be abandoned. It is a **lab demonstrating risk**, not a production pattern for orders/payments.

### 6.4. Scheduled Task Observing Thread Type

File `src/main/java/com/example/virtualkeepalive/HeartbeatTask.java`:

~~~java
package com.example.virtualkeepalive;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PreDestroy;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class HeartbeatTask {

    private final AtomicInteger ticks = new AtomicInteger();

    @Scheduled(initialDelay = 1_000, fixedRate = 1_000)
    public void heartbeat() {
        Thread thread = Thread.currentThread();
        int count = ticks.incrementAndGet();

        System.out.println("LAB_TICK n=" + count
                + " virtual=" + thread.isVirtual()
                + " daemon=" + thread.isDaemon()
                + " name=" + thread.getName());
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println(
                "LAB_CONTEXT_DESTROYED ticks=" + ticks.get());
    }
}
~~~

**Why choose `fixedRate` and a one-second initial delay?**

- `initialDelay=1000` separates the main startup phase from the first tick.
- `fixedRate=1000` triggers scheduled executions on a cadence rather than sleeping 1 second inside the method.
- With the virtual `SimpleAsyncTaskScheduler`, fixed-rate executions use virtual worker threads per the implementation, so `Thread.isVirtual()` inside the scheduled method reflects Boot's virtual-thread setting.
- With the default `ThreadPoolTaskScheduler`, execution runs on a platform thread so `isVirtual()==false`.
- Do not put `Thread.sleep(5min)` inside `@Scheduled` just to "keep the program running", because the goal here is measuring daemon/liveness, not holding a busy task.
- `@PreDestroy` prints the tick count when Spring closes the context during normal shutdown. Do not assume "seeing the destroy marker" means all external jobs finished.
- Note that `@Scheduled` has no built-in business retry/durable queue; if a task fails, define a dedicated error policy and monitoring.

### 6.5. `application.properties`

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=virtual-keepalive-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=WARN

# Default mode for LAB A; CLI can override.
spring.threads.virtual.enabled=true
spring.main.keep-alive=false
~~~

**Explanation:** We intentionally set keepalive=false in the file as the default baseline. Spring Boot 3.5 also defaults `spring.main.keep-alive=false` if omitted. When running the remaining scenarios, pass command-line arguments to override:

~~~text
--spring.threads.virtual.enabled=true
--spring.main.keep-alive=true
~~~

Because `application.properties` sets false, make sure the real command passes `--spring.main.keep-alive=true` when testing case B. Do not change the JAR between scenarios; keep identical dependencies, JDK, and machine.

## 7. Building the Project with JDK 21+

### 7.1. Linux/macOS

~~~bash
java -version
./mvnw -version
./mvnw clean package
~~~

If there is no Maven Wrapper:

~~~bash
mvn -version
mvn clean package
~~~

### 7.2. Windows PowerShell

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
~~~

If only an installed Maven is available:

~~~powershell
mvn -version
mvn clean package
~~~

**Always verify `java -version` and the JDK used by Maven.** `Thread.ofVirtual`/`Thread.isVirtual` were introduced in Java 21. If Maven uses JDK 17, the build will fail with missing method/API errors or unsupported release 21. If `JAVA_HOME` points to a newer JDK while `java` on PATH is older, running the JAR will also use the wrong version.

The JAR built per the POM is:

~~~text
target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar
~~~

If you changed `<version>` in the POM, use the actual JAR name. For lifetime experiments, **run raw `java -jar`** instead of `mvn spring-boot:run`, IDE Run, or JUnit. Intermediate launchers have their own threads/process management, which can prevent scenario A from exiting on its own as expected.

## 8. Experiment A — `virtual=true, keep-alive=false`

Run as a **separate process**:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=false
~~~

In Windows PowerShell on a single line:

~~~powershell
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=true --spring.main.keep-alive=false
~~~

**Typical milestones observed:**

~~~text
LAB_JOB_SUBMITTED virtual=true daemon=true
LAB_JOB_BEGIN virtual=true daemon=true
LAB_MAIN_RETURNED
LAB_CONTEXT_DESTROYED ticks=0
~~~

**This is an illustrative example of markers, not byte-for-byte stdout.** `LAB_JOB_BEGIN` may appear before `LAB_JOB_SUBMITTED`, `LAB_CONTEXT_DESTROYED` may interleave with other logs, and tick count could be non-zero in environments with unexpected non-daemon threads.

**Expected conclusion:** After `main()` returns, if no non-daemon threads remain, the JVM proceeds to shutdown. The virtual/daemon scheduler and one-shot virtual/daemon thread **do not keep the JVM alive**, so a 3-second sleeping job may be aborted. `LAB_JOB_DONE` and `LAB_TICK` **may not appear**, which is by design.

This does not mean Spring Boot "disabled `@Scheduled`": the scheduled method was registered, yet the process did not stay alive long enough to reach its execution time. If the process does not exit after a few seconds, inspect non-daemon threads, agents, or added dependencies; **do not assume the property was ignored merely because the process stayed alive**.

### 8.1. Checking the Exit Code When the JVM Terminates on Its Own

In Bash:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=false
echo $?
~~~

When main succeeds and the process exits normally, the shell typically prints `0`. However, **exit status 0 does not prove `LAB_JOB_DONE` occurred**. If the JVM hits OOM/startup failure or a process supervisor alters exit behavior, a different status may appear.

In PowerShell, check `$LASTEXITCODE` immediately after the java command to read the native process exit status.

## 9. Experiment B — `virtual=true, keep-alive=true`

Run the same JAR again:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=true
~~~

Windows PowerShell:

~~~powershell
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=true --spring.main.keep-alive=true
~~~

This time `main` still returns, yet the process **must stay alive** thanks to Spring Boot's keep-alive mechanism. After a few seconds, you may see:

~~~text
LAB_JOB_SUBMITTED virtual=true daemon=true
LAB_JOB_BEGIN virtual=true daemon=true
LAB_MAIN_RETURNED
LAB_TICK n=1 virtual=true daemon=true name=...
LAB_TICK n=2 virtual=true daemon=true name=...
LAB_TICK n=3 virtual=true daemon=true name=...
LAB_JOB_DONE
LAB_TICK n=4 virtual=true daemon=true name=...
~~~

Thread names, counters, and timings may vary. Reliable markers are `LAB_TICK virtual=true daemon=true` and **the process remaining alive after main returns**. Once 3 seconds pass, the one-shot job can complete and print `LAB_JOB_DONE` if no unexpected errors/interrupts occur.

### 9.1. Stopping the Process and Observing Cleanup

Press **Ctrl+C** in the terminal running Java or send a valid SIGTERM. On Spring Boot's normal shutdown path, the context closes and beans with `@PreDestroy` run lifecycle destruction, e.g.:

~~~text
LAB_CONTEXT_DESTROYED ticks=...
~~~

That proves a bean reached its destroy hook, not that every unmanaged virtual thread received an interrupt and finished. A real app must manage shutdown of executors, consumers, connections, and jobs via owners, deadlines, and durable state.

**Avoid** using `kill -9` to test graceful shutdown: SIGKILL does not give Java a reliable chance to run hooks. When simply stopping the experiment, Ctrl+C or SIGTERM is appropriate.

### 9.2. Keep-Alive Does Not Change Thread Type

In the output above:

~~~text
virtual=true daemon=true
~~~

stays unchanged when keepalive is enabled. It does **not** make `Thread.isDaemon()` false. Spring Boot maintains a mechanism for process lifetime; it does not alter the daemon flag of virtual threads, nor does it turn a scheduled method into a platform thread just to keep the app open.

## 10. Experiment C — `virtual=false, keep-alive=false`

Run the control trial:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=false \
  --spring.main.keep-alive=false
~~~

Windows PowerShell:

~~~powershell
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=false --spring.main.keep-alive=false
~~~

**Expectations:**

- `@Scheduled` runs on Spring Boot's `ThreadPoolTaskScheduler`, typically a **non-daemon platform** worker, logging `LAB_TICK virtual=false daemon=false`.
- Because the scheduler has a non-daemon thread, the JVM typically **stays alive** even with keepalive=false.
- The one-shot worker created manually via `Thread.ofVirtual()` still prints `virtual=true daemon=true` and can complete after 3 seconds because the platform scheduler keeps the JVM alive.
- Press Ctrl+C to terminate and observe bean destruction.

If an app has a custom scheduler making threads daemon, liveness behavior can differ. The lab is designed **without a custom scheduler** and without a web server, so it demonstrates the difference in Boot defaults.

### 10.1. Why Is Scenario C Important?

If you only test "virtual=true keepalive=false" and "virtual=true keepalive=true", you know keepalive affects liveness, yet you have not proven the root cause lies in the daemon scheduler. Scenario C shows that when virtual integration is disabled, the platform scheduler can act as a **non-daemon thread keeping the JVM alive**, even without keepalive.

This is a causal comparison: **the same `@Scheduled`, same JAR, same Java, same cadence**, changing only two flags. Do not use this result to claim virtual threads are "slower", since the experiment only measures **liveness and daemon semantics**, not task throughput/latency.

## 11. Automating the Test with Java `ProcessBuilder`

To observe process lifecycle repeatably without holding an IDE or test harness "hostage", use a standalone Java program that **launches child JVMs**. The parent may have its own non-daemon threads, yet **does not make the child JVM live longer**; this is why testing across a process boundary is more reliable than calling `main` directly in JUnit.

Save `ProcessProbe.java` in the project root directory, **not** under `src/main/java`; run using JDK 21 **source-file mode**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ProcessProbe {

    private record Scenario(
            String name, boolean virtual, boolean keepAlive) {
    }

    private static final List<Scenario> SCENARIOS = List.of(
            new Scenario("virtual-no-keepalive", true, false),
            new Scenario("virtual-with-keepalive", true, true),
            new Scenario("platform-no-keepalive", false, false));

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java ProcessProbe.java path/to/app.jar");
            System.exit(2);
        }

        Path jar = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException(
                    "JAR does not exist: " + jar);
        }

        String javaBinary = System.getProperty("os.name")
                .startsWith("Windows") ? "java.exe" : "java";
        String java = Path.of(
                System.getProperty("java.home"), "bin",
                javaBinary).toString();

        for (Scenario scenario : SCENARIOS) {
            Path log = Path.of(
                    "probe-" + scenario.name() + ".log")
                    .toAbsolutePath();

            ProcessBuilder builder = new ProcessBuilder(
                    java,
                    "-jar",
                    jar.toString(),
                    "--spring.threads.virtual.enabled="
                            + scenario.virtual(),
                    "--spring.main.keep-alive="
                            + scenario.keepAlive());

            builder.redirectErrorStream(true);
            builder.redirectOutput(log.toFile());

            Process child = builder.start();

            // If child process exits on its own within 6 seconds,
            // waitFor returns true. Does not exit on its own => false.
            boolean exitedNaturally = child.waitFor(
                    6, TimeUnit.SECONDS);

            String initialStatus = exitedNaturally
                    ? "EXITED(code=" + child.exitValue() + ")"
                    : "STILL_RUNNING_AFTER_6S";

            // Clean up child process so the probe does not leave
            // scheduler JARs running indefinitely after the test.
            if (!exitedNaturally) {
                child.destroy();
                if (!child.waitFor(3, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                    child.waitFor();
                }
            }

            List<String> lines = Files.readAllLines(log);
            long ticks = lines.stream()
                    .filter(s -> s.contains("LAB_TICK n="))
                    .count();
            boolean jobDone = lines.stream()
                    .anyMatch(s -> s.contains("LAB_JOB_DONE"));
            boolean mainReturned = lines.stream()
                    .anyMatch(s -> s.contains("LAB_MAIN_RETURNED"));

            System.out.println("PROBE name=" + scenario.name()
                    + " initial=" + initialStatus
                    + " mainReturned=" + mainReturned
                    + " ticks=" + ticks
                    + " jobDone=" + jobDone
                    + " log=" + log);
        }
    }
}
~~~

**This is a complete Java file** using only the standard library; `ProcessProbe` needs no Spring dependencies. It does not connect to Google Sheets, the network, or real services. Each child JVM runs the same JAR with its respective flags.

Run in the project root after building:

~~~bash
java ProcessProbe.java target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar
~~~

The same syntax works in PowerShell. Source-file mode works from JDK 11+, and JDK 21 aligns with the whole lesson. The program runs three scenarios **sequentially**; each scenario is observed for up to 6 seconds, then the child is stopped if still running. It writes three log files in the working directory, allowing visual inspection instead of guessing.

### 11.1. Interpreting the Results

In a clean local environment, the report looks similar to:

~~~text
PROBE name=virtual-no-keepalive initial=EXITED(code=0) mainReturned=true ticks=0 jobDone=false log=...
PROBE name=virtual-with-keepalive initial=STILL_RUNNING_AFTER_6S mainReturned=true ticks=5 jobDone=true log=...
PROBE name=platform-no-keepalive initial=STILL_RUNNING_AFTER_6S mainReturned=true ticks=5 jobDone=true log=...
~~~

**This is illustrative output** (specific ticks, paths, and status depend on the environment). Do not expect exact `ticks=5`, as startup and timing vary. What is valuable to verify is that process A exits early when no non-daemon thread keeps it alive, B stays running thanks to keepalive, and C has a non-daemon scheduler per Boot defaults.

**Careful with `destroy()`:** In the probe, when a child has not exited, `Process.destroy()` requests stopping the child; exact signal mechanisms vary by OS and JVM. After 3 seconds, `destroyForcibly()` prevents leaving stray processes alive. This is **test harness cleanup**, not an example guaranteeing graceful shutdown. Inspect `LAB_CONTEXT_DESTROYED` if present, without treating it as mandatory when a child is force-killed.

### 11.2. Limitations of the Probe

- The probe measures whether a process **exited on its own within 6 seconds**, not a performance benchmark.
- A JVM hitting startup failure can exit with a non-zero code; inspect logs and never infer daemon exit solely from "EXITED" without `LAB_MAIN_RETURNED`.
- `mainReturned=false` and `ticks=0` signal failed or overly slow setup/startup, not proof of keepalive behavior.
- Logs may be flushed during normal process shutdown; crashes or forced kills lose trailing output.
- On some environments, JVM agents, profilers, or third-party libraries create non-daemon threads; scenario A might stay alive. Inspect thread dumps and run the raw JAR without extra agents.
- Log filenames are fixed per scenario; re-running the probe overwrites **the lab's own log files**. Do not point the script at a directory holding important production logs.
- To test production signal semantics, use dedicated containers/systemd/Kubernetes and inspect lifecycle logs rather than relying on Java `ProcessBuilder` alone as end-to-end proof.

## 12. Why Testing via Maven Run/IDE/JUnit Easily Misleads

Development tools can spawn additional threads or processes:

| Run Method | Risk |
|---|---|
| `mvn spring-boot:run` | Maven/plugin may use launchers/process management that obscure status/lifetime |
| IDE Run/Debug | Debugger agents and dedicated threads can affect liveness |
| JUnit in the same JVM | JUnit/TestContext and test runner threads remain alive, masking self-exit |
| Spring Boot DevTools | Restart classloaders or extra threads may keep the process alive |
| An app with Spring Web/Tomcat | Embedded server can keep the JVM alive with non-daemon platform threads |
| Shell running `java -jar` directly | Tests process lifetime closest to production runtime |
| `ProcessBuilder` spawning `java -jar` | Great for automated tests with timeouts and captured output |

**Do not use a `@SpringBootTest` test to claim the process will exit on its own:** the test JVM is managed by the test framework and can keep running after the Spring application context closes. For liveness questions, **the proper unit of test is the OS process**.

In Spring Boot 3.5, `@SpringBootTest` also has `useMainMethod`, defaulting to `NEVER`, so many tests do not go through custom setup in `main`. If you want to test custom `main` configuration, the test context must select the proper main mode; still, **testing JVM exit** should be isolated in a subprocess.

## 13. `spring.main.keep-alive` Is Not Other "Keep Alive" Settings

| Setting / Concept | Target | Do Not Substitute for `spring.main.keep-alive` |
|---|---|---|
| `spring.main.keep-alive` | SpringApplication / JVM process lifetime | **The** property in this lesson |
| HTTP `Connection: keep-alive` | Reusing HTTP TCP connections | Does not keep a CLI JVM alive this way |
| Tomcat `server.tomcat.keep-alive-timeout` | Timeout for reusing HTTP connections | Does not apply to virtual daemon schedulers |
| `ThreadPoolExecutor.keepAliveTime` | Idle time for excess workers before shrinking | Does not stop JVM exit when only daemon threads remain |
| `ThreadPoolTaskExecutor.setKeepAliveSeconds` | Idle lifetime of threads beyond core size | Does not keep a background app alive |
| Kubernetes liveness probe | Platform mechanism detecting unhealthy containers | Does not make the JVM retain a daemon task |
| Kubernetes readiness probe | Traffic routing decision when Pod is ready | Not a Java process keepalive mechanism |
| OS process supervisor restart policy | Can restart an exited process | Does not automatically recover lost jobs |

**Specifically:** changing `spring.task.execution.pool.keep-alive` or HTTP keep-alive timeouts and seeing no effect on a `@Scheduled` virtual daemon is expected, because they operate at a different layer.

## 14. When Should You Enable or Disable It?

### 14.1. Scheduled Daemon Service

An application that does not serve HTTP yet needs `@Scheduled` running long-term (cron poller, periodic audit, cleanup, event consumer). With Java 21+ and Boot's virtual scheduler, `spring.main.keep-alive=true` is a **sensible choice** so it does not exit right when `main` returns.

However, you must also have:

- Health/readiness or an external supervisor fitting the workload.
- Retries/error handling for periodic tasks.
- Quotas/concurrency limits if each tick calls APIs or DBs.
- A shutdown lifecycle with deadlines to stop taking jobs and clean up resources.
- Logs/metrics confirming the scheduler is still running, not merely that the process is alive.

### 14.2. Finite Batch/CLI Job

A one-off batch job needs to return an exit status to a scheduler/CI. If keepalive=true is enabled without an explicit stop mechanism, the process **may stay alive indefinitely** after the job completes, causing CI/Kubernetes Jobs to hang and time out. For this workload:

- Execute work with a clear completion point.
- Wait on `Future` or completion stages with deadlines when needed.
- Use `SpringApplication.exit(context)` followed by `System.exit(code)` if the contract requires an OS exit code, after proper cleanup.
- Or close the context per lifecycle if the entrypoint is designed for CLI.
- Never use `spring.main.keep-alive=true` as a substitute for `join/get/await` on a finite job.

### 14.3. Web Application That Already Has Non-Daemon Threads

In Tomcat/Jetty/Netty apps, platform threads from the server/framework often keep the JVM alive even when `spring.main.keep-alive=false`. Testing on a web server therefore will not demonstrate a CLI's daemon-scheduler exit. You can still set keepalive=true by design, though its observable effect may be masked by other threads keeping the process alive.

### 14.4. Daemon Jobs with Critical Side Effects

If processing payments, orders, mandatory emails, or broker events, enabling keepalive alone does not protect against losing work. Processes can restart, hit OOM, receive SIGKILL, lose nodes, or hit deployment termination deadlines. When handling critical work, use durable storage, proper ack/retry timing, and idempotency keys.

## 15. Keeping the JVM Alive Differs from Ending Tasks Cleanly

**Keepalive solves liveness.** It does not solve **lifecycle ownership** or **durability**.

In the lab, `Thread.ofVirtual()` is spawned inside `ApplicationRunner` without being owned by any Spring bean. When an operator stops the process, Spring does not automatically `join` arbitrary manual virtual threads. If a task is still running, it can be abandoned. In production, use a proper owner:

~~~text
RUNNING
   |
   v
QUIESCING: reject new jobs, stop HTTP/broker intake
   |
   v
DRAINING: wait for in-flight jobs within deadline
   |
   +-- completed -> commit/ack
   +-- retryable -> persist state/requeue per semantics
   +-- cancelled -> interrupt + cooperative cleanup
   |
   v
CLOSING: close executors, sessions, connections
   |
   v
TERMINATED: context completes shutdown
~~~

**Three situations to distinguish:**

1. **`main` returns**: the main thread finishes, yet the process may stay alive if non-daemon threads or keepalive exist; this does not mean the app shut down.
2. **`SpringApplication.exit(context)` / `context.close()`**: the application enters the shutdown lifecycle intentionally; keepalive **should not** keep a closed context running indefinitely.
3. **SIGKILL/JVM crash**: `@PreDestroy`, `SmartLifecycle`, `finally`, and final logs are not guaranteed; in-memory-only data can be lost.

### 15.1. Example Managing `ExecutorService` with Deadlines (Snippet)

When a bean owns an `ExecutorService`, it needs bounded stop logic:

~~~java
private void stopExecutor(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(4, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

**This is a method snippet, not part of the lab's two runnable Java files.** It needs `ExecutorService`/`TimeUnit` imports and must be called by the proper lifecycle owner (`@PreDestroy` or appropriate `SmartLifecycle`). `shutdownNow()` issues a **best-effort** stop request; external I/O ignoring interrupts can still linger. Put deadlines on JDBC/HTTP clients, cleanup in `finally`, and durable work state when work cannot be lost.

**Do not confuse `ExecutorService.close()` with keepalive:** Java 21's `ExecutorService.close()` can wait for tasks to finish; if a task blocks without a deadline, it can hold up shutdown unexpectedly. Design realistic shutdown budgets instead of calling unbounded close inside a hook.

### 15.2. Keepalive Does Not Automatically Fix Virtual Thread Pinning

On JDK 21, blocking inside certain `synchronized`/native scenarios can pin a virtual thread to its carrier, reducing throughput. JDK 24+ introduces major improvements via JEP 491 for synchronized pinning. This is a **scheduler efficiency** issue, distinct from process self-exit due to daemon semantics. Enabling keepalive does not improve pinning and does not replace profiling/JFR.

If throughput is slow, measure JFR, CPU samples, thread dumps, and downstream timeouts; do not assume `keepalive=true` fixes performance or changes thread types.

## 16. Concurrency Limits and External Resource Safety

Virtual threads are lightweight, yet **not free**, and do not increase database connection counts or API quotas. For example:

- 1,000 virtual threads can simultaneously wait on 10 JDBC connections.
- A partner API may allow only 2 in-flight calls even if the application spawns 100 virtual threads.
- `@Scheduled(fixedRate=100ms)` can produce overlapping executions if each call exceeds the cadence and the scheduler permits it.
- A job retrying infinitely can build up a backlog even while the JVM stays healthy thanks to keepalive.

Use admission control or a `Semaphore` around scarce resources. Snippet example:

~~~java
private final Semaphore slots = new Semaphore(2);

public void invokeExternalService() throws InterruptedException {
    if (!slots.tryAcquire(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("external capacity exhausted");
    }
    try {
        callExternalServiceWithTimeout();
    } finally {
        slots.release();
    }
}
~~~

**This is a design snippet**, requiring imports, real fields/methods for the external service, error handling, and client closing. A `Semaphore` only limits concurrency within **one JVM**; multiple replicas can still exceed cluster-wide quotas. Do not hold permits while waiting on work unrelated to the external call; enforce deadlines and release in `finally`.

**Distinction:** `spring.main.keep-alive=true` keeps the process alive, while a `Semaphore`/connection pool determines **how much work can execute concurrently**. The two mechanisms do not replace one another.

## 17. Observing with `jcmd`/JFR and Logs

### 17.1. Inspecting Actual Threads

Run scenario B with keepalive=true; after seeing `LAB_MAIN_RETURNED`, open a second terminal:

~~~bash
jcmd -l
jcmd PID Thread.dump_to_file -format=json virtual-lab-threads.json
~~~

Replace `PID` with the running application's JVM PID. `jcmd` belongs to the JDK; you need permission to attach to the process and compatible JDK/tooling. On JDK 21+, JSON thread dumps support observing virtual threads per version format/capabilities. Do not expect a very short-lived virtual task to always appear in a snapshot if it has already completed.

If only `jstack` is available, virtual thread support/formatting may differ; consult your current JDK docs. JFR can also observe virtual-thread events, pinning (where supported by the JDK), and blocking behavior.

### 17.2. Useful Logging Markers

| Marker | What It Measures | What Must Not Be Inferred |
|---|---|---|
| `LAB_MAIN_RETURNED` | `main` received the return from `SpringApplication.run` and reached its final line | JVM has stopped |
| `LAB_JOB_SUBMITTED` | Runner created a virtual thread | Job has completed |
| `LAB_JOB_BEGIN` | Virtual worker started | Task has durability |
| `LAB_JOB_DONE` | One-shot demo finished its sleep per code | External side effects committed |
| `LAB_TICK virtual=true` | Scheduled method is running on a virtual thread | Entire system uses only virtual threads |
| `LAB_TICK daemon=true` | Method's thread does not keep the JVM alive | Process has no other non-daemon threads |
| `LAB_CONTEXT_DESTROYED` | Bean destroy hook was invoked | All work/connections cleaned up |
| `PROBE ... EXITED` | Child process terminated within the observation budget | All background jobs succeeded |
| `PROBE ... STILL_RUNNING` | Child remained alive after budget | Alive due to keepalive if another non-daemon source exists |

Cross-check **at least two forms of evidence**: thread type and process liveness. To conclude "the virtual scheduler caused the app to exit early", show `virtual=true, daemon=true` or docs, `main returned`, child process exited, and no web server or manual non-daemon threads present.

### 17.3. Measuring with Uptime and Startup State

In production, process uptime/restart count is not enough to know `@Scheduled` is running successfully. Add metrics for heartbeat age, last tick timestamp, duration/failure count, upstream availability, queue backlog, and job outcomes. If the process stays alive via keepalive while the scheduler failed due to an exception or disabled configuration, uptime keeps climbing — so never use liveness alone as "healthy".

## 18. Situations That Easily Lead to Wrong Conclusions

| Symptom | Common Cause | How to Handle |
|---|---|---|
| Enabled virtual=true and CLI exited immediately | Virtual/daemon scheduler, no non-daemon threads remaining | Enable `spring.main.keep-alive=true` when workload needs long life |
| Keepalive=true yet no ticks appear | Missing `@EnableScheduling`, bean not scanned, cron/filter error, startup failure | Check scheduler bean, logs, job method, and startup |
| Disabled keepalive yet app stays alive | Another non-daemon thread exists: platform scheduler, web, agent | Run raw JAR, inspect thread dump, check dependencies |
| Set `spring.task.scheduling.pool.size=4` yet still virtual scheduler behavior | Pool setting ignored in virtual mode | Identify `SimpleAsyncTaskScheduler`; use separate resource limits |
| `@Scheduled(fixedDelay)` differs from fixedRate | SimpleAsyncTaskScheduler has special fixed-delay semantics | Use fixedRate in lab; read scheduler Javadoc |
| Virtual worker prints `LAB_JOB_DONE` even with keepalive=false | JVM stayed alive due to another thread/timing | Check process liveness and thread dump |
| Keepalive=true and batch CLI never exits on its own | Keepalive holds JVM even after job finishes | Use explicit exit/close for batch jobs |
| Running via Maven/IDE gives opposite result | Launcher/agent has its own lifecycle | Run an isolated `java -jar` subprocess |
| `Thread.currentThread().isVirtual()==false` in scheduled task | Virtual integration not enabled or custom scheduler uses platform threads | Check properties/JDK/scheduler implementation |
| One-shot `Thread.ofVirtual()` stays true when property is false | That is a JDK API independent of Spring Boot settings | Do not use it to prove Boot's scheduler switched |
| Only 1 tick then app exits | Process lifecycle or exception/cancel/signal | Log signals, `@PreDestroy`, status, environment |
| App stops during container replacement despite keepalive=true | TERM/SIGKILL/platform termination | Keepalive does not block operator shutdown |
| `@PreDestroy` does not log on kill -9 | SIGKILL does not reliably run Java hooks | Use durability; do not infer from missing logs |
| High CPU with virtual threads | CPU-bound work, pinning, excessive concurrency | JFR/profiling, downstream limits |
| DB pool runs out of connections | Virtual threads exceed external resource quotas | Bounded admission, semaphores, timeouts |
| Scheduler method runs too long | Fixed-rate overlap/backlog, I/O without timeouts | Deadlines, concurrent call limits, backpressure |
| App on Java 17 hits `NoSuchMethodError`/compile error | Virtual threads require Java 21+ | Verify java/Maven runtime versions |
| Changed property yet scenario unchanged | CLI args/property precedence or running stale JAR | Inspect actual args, rebuild, log version |
| Unit test PASSES yet process exits in prod | JUnit/test runner keeps JVM alive | Use ProcessBuilder end-to-end tests |
| `LAB_CONTEXT_DESTROYED` appears while job is incomplete | Unmanaged virtual worker | Design owner/shutdown state |
| PID not visible in jcmd | Scenario A process exited too quickly | Observe scenario B with keepalive=true |

## 19. Graded Extension Exercises

### Exercise A — Identifying Daemon Threads

In a process B run, record output `LAB_JOB_BEGIN virtual=true daemon=true` and `LAB_TICK virtual=true daemon=true`. Answer: why doesn't `isDaemon==true` force the JVM to shut down **immediately** when keepalive=true?

**Sample conclusion:** Keepalive ensures the process has a liveness mechanism independent of virtual workers' daemon state; virtual workers are not converted into non-daemon threads.

### Exercise B — Comparing Three Modes

Run ProcessProbe and save all three log files. Build a table of `autoExited`, `mainReturned`, `tickCount`, and `jobDone` for A/B/C. If A does not self-exit within 6 seconds, inspect non-daemon threads and document the limitation instead of altering results to match expectations.

### Exercise C — Varying One-Shot Job Duration

In a copy of the lab, change `Thread.sleep(3_000)` to 8 seconds while ProcessProbe still observes for 6 seconds. In B, the child may be terminated by the probe before `LAB_JOB_DONE` appears. This proves **keepalive gives a chance to run, not a guarantee that jobs complete before an operator stops the process**.

### Exercise D — Switching `fixedRate` to `fixedDelay`

Try `@Scheduled(initialDelay=1000, fixedDelay=1000)` on a copy, observing thread name/`isVirtual` and `SimpleAsyncTaskScheduler` behavior. Read the Javadoc: fixed-delay has semantics that execute on the scheduler thread; do not deduce from one result that virtual threads were disabled app-wide.

### Exercise E — Without Web vs With Web

Add Spring Web to a copy and run with virtual=true keepalive=false. Compare process lifetime with the CLI. Why can an embedded server prevent A from exiting on its own? Remove the dependency after the experiment to return to baseline.

### Exercise F — Tasks with Durable Results

Replace the one-shot sleep with writing a record to a local test database/queue with acknowledgement. Test normal shutdown and forced kill in a simulated environment, recording lost jobs, redelivery, and idempotency. Never run forced kills on real production data.

### Exercise G — Limiting Upstream Concurrency

Have a scheduled task fire 20 virtual calls to a local mock API whose quota is only 2 concurrent calls. Add `Semaphore(2)` with an acquire deadline; measure external peak <=2, failed/rejected count, and reiterate that keepalive does not manage quotas.

### Exercise H — JDK 21 vs JDK 24+

Using the same workload, compare virtual thread behavior and JFR diagnostics. On JDK 21, inspect `jdk.VirtualThreadPinned` when blocking inside `synchronized`; on JDK 24+, read JEP 491 to understand synchronized pinning changes. Never use a single benchmark run to conclude a newer JDK is always faster.

## 20. Acceptance Checklist

- [ ] Running on proper JDK 21+ with Maven building Spring Boot 3.5.x.
- [ ] `spring.main.web-application-type=none`, no web starter in baseline.
- [ ] `@EnableScheduling` and `@Scheduled(fixedRate=...)` present.
- [ ] Understand virtual threads are always daemon.
- [ ] Know the keepalive property defaults to false.
- [ ] Ran A separately: virtual=true, keepalive=false.
- [ ] Ran B separately: virtual=true, keepalive=true.
- [ ] Ran C separately: virtual=false, keepalive=false.
- [ ] In B, observed `LAB_TICK virtual=true daemon=true` and process stayed alive after main returned.
- [ ] In C, observed `LAB_TICK virtual=false` with platform scheduler per Boot default.
- [ ] In A, evaluated whether the process exited early; checked non-daemon threads if not.
- [ ] Did not rely on Maven Run/IDE/test runner as sole evidence.
- [ ] Did not interpret `LAB_JOB_SUBMITTED` as job completion.
- [ ] Observed `LAB_JOB_DONE` when the process stayed alive long enough.
- [ ] Tested Ctrl+C/SIGTERM and understood `@PreDestroy` differs from unmanaged thread cleanup.
- [ ] Understand keepalive=true does not block deliberate shutdown, crashes, or SIGKILL.
- [ ] Did not confuse main keepalive with HTTP keepalive or executor idle timeouts.
- [ ] Did not use keepalive as a replacement for `Future.get` or durable queues.
- [ ] Understand virtual threads do not expand DB connections/upstream quotas.
- [ ] Recorded observation table including JVM version, Spring Boot version, and environment.
- [ ] Correctly explained why scheduled daemon tasks may fail to keep the JVM alive.

## 21. Official Documentation

1. **Spring Boot 3.5 — SpringApplication, Virtual Threads**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html — Java 21+, daemon threads, `@Scheduled`, and `spring.main.keep-alive=true`.
2. **Spring Boot 3.5 — Common Application Properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/ — default value of `spring.main.keep-alive`.
3. **Spring Boot 3.5 — Task Execution and Scheduling**: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html — `SimpleAsyncTaskExecutor`, `SimpleAsyncTaskScheduler`, and pool properties.
4. **Spring Boot 3.5 — SpringApplication API**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html — `isKeepAlive()`, `setKeepAlive(boolean)`.
5. **Java SE 21 — Virtual Threads Guide**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html — virtual vs platform threads, daemon semantics, and `Thread.ofVirtual()`.
6. **Java SE 21 — Thread API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html — `isVirtual()`, `isDaemon()`, `join()`, and interruption.
7. **Java SE 21 — Process/ProcessBuilder API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html — launching child processes and observing exit.
8. **Spring Framework 6.2 — SimpleAsyncTaskScheduler API**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html — virtual mode and fixedDelay behavior.
9. **Spring Framework 6.2 — @Scheduled**: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html — enabling and defining schedules.
10. **JEP 444 — Virtual Threads**: https://openjdk.org/jeps/444 — semantics and goals of virtual threads.
11. **JEP 491 — Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491 — pinning changes starting in JDK 24.

**Summary:** When Spring Boot 3.5 runs on Java 21+ with virtual threads enabled, schedulers/workers can be **daemon**; therefore a CLI application having only scheduled/background work can **terminate immediately after `main()`**, even though tasks are registered. `spring.main.keep-alive=true` keeps the JVM alive when no non-daemon threads remain and lets tasks continue running, yet **does not convert virtual threads into platform threads, does not guarantee business completion, and does not change shutdown/durability**. Verify with a real `java -jar` process, cross-check `isVirtual/isDaemon` against process liveness, and add lifecycle owners, deadlines, backpressure, and durable state for production workloads.