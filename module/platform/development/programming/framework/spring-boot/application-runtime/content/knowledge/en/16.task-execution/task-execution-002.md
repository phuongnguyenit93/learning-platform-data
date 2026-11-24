# Daemon Threads, Non-Daemon Threads, and Conditions for JVM Survival in Spring Boot

## 1. The problem: main has finished yet the Java process keeps running — or exits too early

A Spring Boot application may print its startup completion message, finish `ApplicationRunner`, and return control from `SpringApplication.run(...)`, yet the JVM stays alive. Conversely, an application running only asynchronous tasks may exit right after startup even while jobs are waiting to run. The cause usually lies not in the `main` method name, but in **which threads remain alive and which threads are marked as daemon**.

In Java, aside from cases where the program explicitly shuts down the JVM or is terminated externally, the key rule is:

> The JVM continues running while at least one Java **non-daemon thread is alive**; once only daemon threads remain, the JVM can proceed to normal shutdown.

A thread in `sleep`, `WAITING`, `BLOCKED`, or waiting on I/O is still an **alive** thread if it has not terminated. Only when it actually terminates does it stop keeping the JVM alive under the non-daemon rule. Conversely, a daemon thread may still be executing Java code yet **does not keep the JVM alive by itself** once all non-daemon threads have finished.

Easily confused concepts to separate:

| Concept | Meaning | What should NOT be inferred |
| --- | --- | --- |
| `main(String[] args)` | Familiar entry point of a program | `main` returning does not necessarily stop the JVM immediately |
| Non-daemon thread | Thread counted when the JVM checks normal termination conditions | Does not mean the thread is actively consuming CPU |
| Daemon thread | Thread that does not prevent JVM exit when only daemons remain | Not guaranteed to finish `finally`/file writes on shutdown |
| `Thread.isAlive()` | Thread has started and not yet terminated | Does not tell whether the thread is doing useful work |
| `Thread.isDaemon()` | Daemon flag of a `Thread` | Does not imply priority, OS service, or background process |
| `System.exit(int)` | Requests initiating JVM shutdown | Not the same as naturally running out of non-daemon threads |
| `SpringApplication.run(...)` | Initializes and starts the Spring context | Not a call that always blocks until the process exits |
| `spring.main.keep-alive` | Boot option to keep the app alive even with no other non-daemon threads | Does not replace resource management and graceful shutdown |

This matters especially for three kinds of applications: **CLI/batch**, **web applications**, and **applications running schedulers/async tasks**. All three use the JVM, yet the infrastructure components creating threads and lifecycle policies can differ.

## 2. Exactly when does the Java Virtual Machine terminate?

Under the contract of `java.lang.Thread` and `Runtime`, two common cases leading to JVM shutdown are:

1. **Normal termination:** the last non-daemon threads have terminated, while whether daemon threads remain or not does not prevent shutdown.
2. **Explicit exit request:** code calls `System.exit(status)`, equivalent to `Runtime.exit(status)`, or an external actor requests termination handled by the JVM/runtime.

There are also other situations such as `Runtime.halt(status)`, forcible OS kill, fatal JVM errors, or container limits. `Runtime.halt` differs from `System.exit`: it terminates the JVM forcibly, **without running shutdown hooks normally**.

~~~mermaid
flowchart TD
  A["JVM starts, main thread is typically non-daemon"] --> B["main creates or starts multiple threads"]
  B --> C["main returns"]
  C --> D{"Any non-daemon thread alive?"}
  D -->|"Yes"| E["JVM continues executing"]
  E --> D
  D -->|"No"| F["JVM begins normal shutdown"]
  F --> G["Shutdown hooks, appropriate runtime cleanup"]
  G --> H["JVM process exits"]
  E --> I["System.exit / signal / external stop"]
  I --> F
~~~

**The diagram only shows the normal shutdown path.** Calling `System.exit` can start shutdown even while non-daemon threads are active; shutdown hooks do not necessarily complete when a process is forcibly killed. JVM state also depends on the native/JVM runtime and OS, so the non-daemon rule is a basis for analysis, not a promise that every crash runs cleanup.

### "Alive thread" includes WAITING and TIMED_WAITING

For example, a non-daemon worker with code:

~~~java
while (true) {
    Thread.sleep(1000);
}
~~~

This is a **snippet** (the method must declare/handle `InterruptedException`). It may do nothing besides sleeping, yet it keeps the JVM running because it has not finished. If another worker waits indefinitely on `CountDownLatch.await()` and is non-daemon, the effect of keeping the process alive is the same.

Conversely, a busy-looping daemon worker does not guarantee the JVM keeps it alive once `main` and all other non-daemon threads have finished.

### NEW is not the same as ALIVE

A `Thread` object freshly instantiated via `new Thread(...)` without calling `start()` is not an alive thread per `Thread.isAlive()`. Therefore keeping dozens of unstarted `Thread` objects in a list **does not by itself** keep the JVM alive forever. The daemon flag can be configured on the object before starting the thread.

## 3. Core Thread API

| API | Effect | Notes |
| --- | --- | --- |
| `new Thread(Runnable, name)` | Creates a new platform thread object in Java 17 | Does not execute `run()` until `start()` is called |
| `setDaemon(true)` | Marks as daemon | Must be called **before** `start()` |
| `setDaemon(false)` | Marks as non-daemon | Likewise, must be called while the thread is not yet alive |
| `isDaemon()` | Reads the daemon flag | Does not indicate alive status by itself |
| `isAlive()` | Thread has started and not yet terminated | Includes threads in sleep, waiting, or blocked states |
| `start()` | Asks the JVM to schedule thread execution | Calling again on the same thread throws `IllegalThreadStateException` |
| `join()` | Caller waits for a thread to finish | Does not change the daemon flag of the joined thread |
| `interrupt()` | Sends a cooperative interrupt signal | Not a forcible "kill thread" |
| `Thread.currentThread()` | Gets the thread currently executing code | Useful for logging name/daemon flag/state |
| `Thread.getState()` | Reads observed state at call time | Snapshot can change immediately afterward |

### The daemon flag is inherited

A new platform thread created via `new Thread(...)` normally **inherits the daemon flag of the creating thread**, unless code changes the flag or uses a `ThreadFactory`/API that explicitly sets it. The `main` thread is normally non-daemon, so:

~~~java
Thread worker = new Thread(() -> {
    System.out.println(Thread.currentThread().isDaemon());
});
worker.start();
~~~

When the code above runs from non-daemon `main` with no other changes, it prints `false`. However, if created inside a daemon thread, the default value can be `true`. Therefore **do not assume every `new Thread` is always non-daemon**, and do not treat an environment-dependent result as an immutable Java invariant.

### setDaemon must be called before start

~~~java
Thread worker = new Thread(task, "data-loader");
worker.setDaemon(true);
worker.start();
~~~

`task` is a `Runnable` defined externally, so this is a snippet. Calling `worker.setDaemon(false)` while the thread is alive throws `IllegalThreadStateException`. You cannot change the daemon status of a running thread to "rescue" an exiting process. Configure it before starting, or create a new thread with a different policy.

### Daemon does not mean low-priority thread

`isDaemon()` does not measure priority and does not cause the OS to schedule the thread at lower priority. Both daemon and non-daemon threads can use CPU, acquire locks, make network calls, open files, or emit events. The central difference is **whether the thread preserves the JVM's liveness condition**; scheduling policies, priority, or concurrency are separate concerns.

## 4. Standalone Java 17 example: daemon exits with the JVM, non-daemon keeps the JVM alive

The example below **does not require Spring Boot**, making the JVM rule clear before placing it inside a web or scheduled application. The program uses `CountDownLatch` so output line ordering does not depend on CPU scheduling races.

Create **`DaemonThreadLab.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class DaemonThreadLab {

    public static void main(String[] args)
            throws InterruptedException {

        boolean daemon = args.length > 0
                && args[0].equals("daemon");

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            System.out.println("worker daemon="
                    + Thread.currentThread().isDaemon());
            started.countDown();

            try {
                if (daemon) {
                    // Intentionally wait forever to illustrate that daemon
                    // does not keep JVM alive when main finishes.
                    new CountDownLatch(1).await();
                } else {
                    // Only exit after main has printed its message.
                    release.await();
                    System.out.println("worker completed");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "lab-worker");

        worker.setDaemon(daemon);
        worker.start();

        started.await();
        System.out.println("main reached end");

        if (!daemon) {
            release.countDown();
        }
    }
}
~~~

Compile with Java 17+:

~~~bash
javac -encoding UTF-8 DaemonThreadLab.java
~~~

Run **daemon**:

~~~bash
java DaemonThreadLab daemon
~~~

The output of the two `println` calls is synchronized by the latch:

~~~text
worker daemon=true
main reached end
~~~

The daemon thread stays blocked waiting on an unreleased latch. Once `main` returns and no other non-daemon threads remain, the JVM can shut down normally even though the daemon worker has not reached the end of `run()`. The program will **not** print `worker completed` in this branch, because that line only exists in the non-daemon branch.

Run **non-daemon**:

~~~bash
java DaemonThreadLab user
~~~

Output:

~~~text
worker daemon=false
main reached end
worker completed
~~~

The non-daemon thread only exits after receiving `release.countDown()`; the final line must appear before the JVM can terminate naturally due to no non-daemon threads remaining. `main reached end` is a message printed by code near the end of the method; do not use it alone as an exact timestamp of when the main thread died.

### Why use CountDownLatch?

Without a latch, the scheduler could print the worker log before or after main's log, making a test easily mistake log ordering for thread liveness rules. The latch establishes happens-before relationships for the milestones being compared, making the example output deterministic. It is **not** a mechanism for toggling daemon status.

**Do not put this forever-waiting daemon into production.** It exists solely for learning to prove the JVM can exit before a daemon task finishes. A production task must have explicit termination conditions and a shutdown plan.

## 5. Java 17 example: verifying IllegalThreadStateException when changing the flag too late

Create **`DaemonFlagRules.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class DaemonFlagRules {

    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread thread = new Thread(() -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "flag-demo");

        thread.setDaemon(true);
        System.out.println("configured=" + thread.isDaemon());

        thread.start();
        ready.await();

        try {
            thread.setDaemon(false);
            System.out.println("unexpected");
        } catch (IllegalThreadStateException e) {
            System.out.println("change while alive rejected");
        }

        release.countDown();
        thread.join();

        System.out.println("joined");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 DaemonFlagRules.java
java DaemonFlagRules
~~~

Output:

~~~text
configured=true
change while alive rejected
joined
~~~

`ready.await()` guarantees the thread has entered the unreleased wait before `setDaemon(false)` is called, so we can reliably know the thread is alive. `thread.join()` is called from `main` to wait for the daemon to finish, showing that **a non-daemon caller can choose to wait for a daemon**, though the daemon itself does not keep the JVM alive. If you omit `join` and let `main` finish early, there is no guarantee the daemon finishes in time.

### What if you want to wait for a daemon task?

You can use `join`, `Future.get`, or an appropriate synchronization mechanism **from a still-alive non-daemon thread**. While main calls `join`, main stays alive during the wait, so the JVM has not yet run out of non-daemon threads. However, waiting indefinitely can hang the program; design timeouts and cancellation.

## 6. Main, System.exit, shutdown hooks, and Runtime.halt

### main returning is not System.exit

~~~java
public static void main(String[] args) {
    startSomeBackgroundWork();
    System.out.println("main returned");
}
~~~

This is a snippet; `startSomeBackgroundWork()` must be defined. The JVM can continue running if background work created a still-alive non-daemon thread. A Spring Boot web server can keep the process running even after `main` has passed `SpringApplication.run(...)`.

### System.exit does not wait for every worker to finish

~~~java
System.exit(0);
~~~

Even if non-daemon threads remain, calling `System.exit` initiates the JVM shutdown sequence. On the normal shutdown path, registered shutdown hooks are started; they can clean up resources or close the context, yet **this does not mean every running task will automatically finish**.

Do not use `System.exit(0)` as a default "fix" for a hung process caused by forgetting to close an executor. It can lose in-flight writes, cause abrupt termination, and hide the root lifecycle bug.

### Does a shutdown hook keep the JVM alive?

A shutdown hook is registered via:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> System.out.println("shutdown hook")));
~~~

**Merely registering a hook does not start running it right away**, so it does not turn into an alive non-daemon worker keeping the JVM up. The JVM triggers hooks when shutdown starts according to supported mechanisms. Hooks run concurrently; do not assume invocation order or assign infinite remote I/O to a hook.

Hooks may not run on `Runtime.halt(...)`, `SIGKILL`, forcible container kills, or JVM crashes. If data preservation is required, explicitly commit/flush at proper business checkpoints rather than relying solely on shutdown hooks.

### Closing the Spring context differs from stopping every custom thread

`ConfigurableApplicationContext.close()` triggers lifecycle stop/destroy on Spring-managed beans, but does not automatically locate and interrupt every `new Thread(...)` created manually by developers outside management. A forgotten custom non-daemon thread can keep the process alive **after the context closes**.

To terminate cleanly, manage workers via an appropriate executor/bean lifecycle; call `shutdown`/`interrupt` with control, wait a reasonable duration, and log failures if any occur.

## 7. Thread pools: why doesn't the JVM exit after a task finishes?

In practice, many applications do not instantiate `new Thread` directly, instead using `ExecutorService`, `ScheduledExecutorService`, Spring `TaskExecutor`, or schedulers. A thread pool can keep **non-daemon worker threads** alive waiting for more tasks, even when the queue is empty. Forgetting to shut down the pool can keep the JVM running indefinitely.

### Executors.defaultThreadFactory and non-daemon

In Java SE, `Executors`'s default thread factory creates **non-daemon** worker threads. With `Executors.newSingleThreadExecutor()`, the pool worker can normally stay alive waiting for new tasks. Thus task completion alone **is not enough** to conclude the JVM can exit.

Create **`ExecutorShutdownLab.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ExecutorShutdownLab {

    public static void main(String[] args)
            throws Exception {

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<Integer> result = executor.submit(() -> {
                System.out.println("pool daemon="
                        + Thread.currentThread().isDaemon());
                return 42;
            });

            System.out.println("result=" + result.get());
        } finally {
            executor.shutdown();

            if (!executor.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        System.out.println("executor closed");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ExecutorShutdownLab.java
java ExecutorShutdownLab
~~~

Output with Java 17's default thread factory:

~~~text
pool daemon=false
result=42
executor closed
~~~

`result.get()` waits for the task to finish; `shutdown()` tells the pool to reject new tasks; `awaitTermination(...)` waits for the pool to stop. These are distinct: **Future completion** does not mean **the executor has shut down**.

Omitting `shutdown()` in the `newSingleThreadExecutor()` example lets the non-daemon worker keep waiting for jobs and holding the JVM open. Do not work around this by blindly making all threads daemon; instead **manage the pool's lifecycle**.

### Custom ThreadFactory

A custom `ThreadFactory` can create daemon or non-daemon threads:

~~~java
ThreadFactory factory = task -> {
    Thread t = new Thread(task, "custom-worker");
    t.setDaemon(true);
    return t;
};
~~~

This snippet requires importing `java.util.concurrent.ThreadFactory`. Creating a daemon pool can make sense for auxiliary work where dropping in-flight work is acceptable, but **not** for tasks that must finish writing data. A daemon pool still needs closing to release resources and run deliberate cleanup; daemon is not a resource-management mechanism.

### Scheduled executor and waiting workers

A `ScheduledExecutorService` waiting for its next scheduled run can keep a non-daemon thread alive. Conversely, if the scheduler thread is daemon, it will not keep the JVM alive merely because `fixedRate`/`fixedDelay` schedules are registered. That is why every timer/scheduler application must inspect its actual thread policy instead of guessing from API names.

## 8. Spring Boot: does SpringApplication.run returning mean the application has ended?

No. In Spring Boot, `SpringApplication.run(...)` typically creates the `ApplicationContext`, refreshes the context, publishes lifecycle events, and runs `ApplicationRunner`/`CommandLineRunner`. When it completes successfully, `run(...)` returns `ConfigurableApplicationContext` to the caller; from there, **remaining alive threads** and keep-alive mechanisms determine whether the process continues.

~~~mermaid
flowchart TD
  A["main()"] --> B["SpringApplication.run(...)"]
  B --> C["Refresh context, create beans"]
  C --> D["ApplicationStartedEvent"]
  D --> E["Runner tasks"]
  E --> F["ApplicationReadyEvent"]
  F --> G["run returns"]
  G --> H{"Remaining non-daemon / keep-alive?"}
  H -->|"Yes"| I["JVM continues"]
  H -->|"No"| J["JVM shutdown"]
~~~

This is a simplified logic diagram; Boot also publishes `AvailabilityChangeEvent` for liveness/readiness at relevant milestones. A runner throwing an exception can cause startup to fail before `run` returns normally.

### Spring Boot CLI/batch app

For a project with only `spring-boot-starter`, no web server, and no long-lived non-daemon workers, the program typically **exits on its own after startup**. An `ApplicationRunner` that performs synchronous work and returns usually suits batch CLIs: once done, there is no reason to keep the JVM alive forever.

### Spring Boot web app

With `spring-boot-starter-web` or an equivalent web runtime, the embedded server and infrastructure components can spawn threads that keep the process alive after `main`/`run` returns. Thus "main finished printing yet the service still listens on HTTP" is normal behavior.

Do not generalize that "a web server always creates exactly N non-daemon threads": Tomcat, Jetty, Undertow, Netty, virtual threads, server options, and versions can differ. Inspect actual thread dumps and configuration.

### Background runners, @Async, @Scheduled

- `ApplicationRunner` runs synchronously on the default startup path until `run(...)` completes. If it **spawns** a worker and returns, Boot does not automatically wait for that worker merely because it was created inside a runner.
- `@Async` invokes tasks via a configured executor, typically enabled by `@EnableAsync`; daemon status depends on the executor/thread factory type. Do not assume every `@Async` call keeps the app alive.
- `@Scheduled` requires scheduling to be enabled (e.g. `@EnableScheduling`) and depends on the scheduler in use. Having a schedule is not a guarantee that a non-daemon thread always keeps the JVM alive.
- `CompletableFuture.runAsync(...)` may use the common pool or another executor. Do not rely on uncontrolled daemon flags to guarantee background tasks complete before the app exits.

Some executors/schedulers auto-configured by Spring Boot differ depending on whether virtual threads are enabled. Check `spring.threads.virtual.enabled`, `TaskExecutor`/`TaskScheduler` beans, `ThreadFactory`, and each pool's scope/lifecycle.

## 9. Runnable Spring Boot 3.5.16 Java 17+ example: CLI application with two thread modes

This project uses **Spring Boot 3.5.16**, Java 17+, Maven, and the core starter. It is designed with **deterministic stdout ordering for lines printed by our code**, demonstrating that the JVM exits immediately with a daemon worker and waits for non-daemon work.

Structure:

~~~text
thread-lifetime-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/lifetime/
    │   └── ThreadLifetimeApplication.java
    └── resources/application.yaml
~~~

### File pom.xml

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
    <artifactId>thread-lifetime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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

### File src/main/resources/application.yaml

~~~yaml
spring:
  main:
    web-application-type: none
    banner-mode: "off"
    keep-alive: false
~~~

`web-application-type: none` keeps the experiment in CLI mode without depending on a web server. `keep-alive: false` is Boot 3.5's default but is stated explicitly for clarity; it can be overridden via CLI during experiments.

### File src/main/java/com/example/lifetime/ThreadLifetimeApplication.java

~~~java
package com.example.lifetime;

import java.util.concurrent.CountDownLatch;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ThreadLifetimeApplication {

    private static final CountDownLatch AFTER_RUN =
            new CountDownLatch(1);

    public static void main(String[] args) {
        SpringApplication.run(ThreadLifetimeApplication.class, args);

        System.out.println("MAIN_AFTER_RUN");
        AFTER_RUN.countDown();
    }

    @Bean
    ApplicationRunner spawnTask() {
        return args -> {
            boolean daemon = args.containsOption("daemon-task");
            CountDownLatch announced = new CountDownLatch(1);

            Thread worker = new Thread(() -> {
                System.out.println("TASK_DAEMON="
                        + Thread.currentThread().isDaemon());
                announced.countDown();

                try {
                    if (daemon) {
                        // Wait forever: used solely as an illustrative lab.
                        new CountDownLatch(1).await();
                    } else {
                        // Wait until main has printed MAIN_AFTER_RUN.
                        AFTER_RUN.await();
                        System.out.println("TASK_FINISHED");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "demo-task");

            worker.setDaemon(daemon);
            worker.start();

            announced.await();
            System.out.println("RUNNER_RETURNED");
        };
    }
}
~~~

**Code analysis:**
1. `SpringApplication.run` completes startup/runners before printing `MAIN_AFTER_RUN`.
2. The runner creates a thread, sets the daemon flag **before** `start()`, and uses a latch to wait for the thread to print its status.
3. If `--daemon-task` is passed, the thread waits forever in the daemon branch, yet does not keep the JVM alive when main finishes.
4. Without the flag, the non-daemon thread waits on `AFTER_RUN`, printing `TASK_FINISHED` only after main has printed `MAIN_AFTER_RUN`; the JVM does not exit naturally before this thread finishes.
5. `CountDownLatch` is an output-ordering synchronization mechanism; it does not make a thread daemon or non-daemon.
6. The example intentionally creates a forever-blocked daemon to prove the semantics; **do not use this technique in production**.

### Build and run

In the directory containing `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar
~~~

Lines printed by the example code, in controlled order:

~~~text
TASK_DAEMON=false
RUNNER_RETURNED
MAIN_AFTER_RUN
TASK_FINISHED
~~~

The framework may print other startup logs; do not compare the entire stdout against the block above.

Run the daemon branch:

~~~bash
java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar --daemon-task
~~~

Lines printed by the example code:

~~~text
TASK_DAEMON=true
RUNNER_RETURNED
MAIN_AFTER_RUN
~~~

Even though the daemon thread is still waiting on an infinite latch, the CLI application can exit normally after main returns because it has no other non-daemon threads left in this illustrative setup.

### A change that keeps the JVM from exiting even when the worker is daemon

Spring Boot 3.5 provides the property `spring.main.keep-alive`. When enabled:

~~~bash
java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar \
  --daemon-task \
  --spring.main.keep-alive=true
~~~

Boot keeps the application alive even when only daemon threads remain. This run will not exit on its own because the worker waits forever **and** Boot keeps it alive; stop it with Ctrl+C or an appropriate shutdown signal. Do not misunderstand `keep-alive=true` as guaranteeing daemon tasks finish: the worker is still blocked, and you must not rely on a long-lived process instead of cancellation.

To run a time-bounded experiment on Linux with GNU `timeout`:

~~~bash
timeout 5s java -jar target/thread-lifetime-demo-0.0.1-SNAPSHOT.jar \
  --daemon-task \
  --spring.main.keep-alive=true
~~~

When the process does not terminate before the deadline, `timeout` sends a stop signal per its policy; the default exit status is typically **124** when an actual timeout occurs. This result depends on environment and startup time, so do not treat exact 5 seconds or status 124 as a guaranteed Java output in all cases. On PowerShell/cmd, run a single command and stop the process manually instead of using GNU `timeout`.

### Takeaways from the demo

The same JAR, in three modes, produces three lifecycle policies:

| Configuration | Worker | Can exit on its own when main finishes? |
| --- | --- | --- |
| No flag, `keep-alive=false` | Non-daemon, finishes after main's signal | Only after the worker finishes |
| `--daemon-task`, `keep-alive=false` | Daemon waiting forever | Yes, when no other non-daemon threads remain |
| `--daemon-task --spring.main.keep-alive=true` | Daemon waiting forever and Boot keeps alive | Does not exit via normal non-daemon exhaustion |

This illustrates a CLI app **with no web server or other auxiliary non-daemon components**. In a real project, thread libraries, executors, logging pipelines, database drivers, and integrations can create other threads; measure empirically.

## 10. Java 21+ virtual threads — a crucial point with Spring Boot

The `new Thread(...)` examples above use **platform threads** and run on Java 17. Starting in **Java 21**, Java provides **virtual threads**: lighter-weight Java threads managed by the JVM, suited for many I/O-waiting tasks.

**The decisive point for this topic: virtual threads are always daemon threads.** They do not keep the JVM alive merely because virtual tasks remain. This is documented behavior from Oracle and Spring Boot, not an unofficial quirk.

### Standalone Java 21 example

File **`VirtualThreadDaemon.java`** — compiles only on Java 21+:

~~~java
public final class VirtualThreadDaemon {

    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = Thread.ofVirtual()
                .name("vt-demo")
                .start(() -> {
                    System.out.println("virtual="
                            + Thread.currentThread().isVirtual());
                    System.out.println("daemon="
                            + Thread.currentThread().isDaemon());
                });

        worker.join();
    }
}
~~~

Run with JDK 21+:

~~~bash
javac VirtualThreadDaemon.java
java VirtualThreadDaemon
~~~

Output:

~~~text
virtual=true
daemon=true
~~~

`join()` in main waits for the virtual worker to print both lines; this does not make the virtual thread non-daemon. If `join` is omitted and main exits very quickly, the virtual thread may be shut down before finishing printing.

Do not copy `Thread.ofVirtual()` into a Java 17-locked project: that API **does not exist in Java 17**. Nor can you convert a virtual thread to non-daemon to solve keep-alive; use the appropriate application lifecycle mechanism.

### Spring Boot and the virtual threads flag

In Spring Boot 3.5, if running on Java 21+, you can enable:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Spring Boot documents that when virtual threads are enabled, auto-configured task execution/scheduling can use virtual threads. For example, with `@Scheduled`, a scheduler using virtual threads in supported setups means those threads **do not keep the JVM running on their own**. Thus Boot recommends `spring.main.keep-alive=true` if the application must stay alive so those tasks continue executing.

Do not assume `spring.threads.virtual.enabled=true` turns **every** thread in the process into a virtual thread; the JVM still has platform/carrier threads and many libraries may create platform threads themselves. And do not assume virtual threads make code run faster for all workloads; the primary goal is supporting high concurrency for I/O-bound tasks with lower overhead, not accelerating CPU-bound computation.

### Scheduled app with virtual threads

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration
@EnableScheduling
class ScheduleConfiguration {

    @Scheduled(fixedDelay = 5000)
    void tick() {
        System.out.println("SCHEDULE_TICK");
    }
}
~~~

This is an illustrative class that must reside in a scanned package with Spring scheduling infrastructure enabled. If an application only has periodic schedules, no web server keeping it alive, and uses a daemon virtual-thread scheduler, it can exit right after startup unless `spring.main.keep-alive=true` is enabled. Registering `@Scheduled` **is not a guarantee that the process stays alive forever**.

**Configuration pitfall:** when using virtual threads, traditional thread pool sizing properties may no longer apply to the new auto-configured executor/scheduler types. Check the exact Boot version and created bean types before tuning `spring.task.execution.pool.*` or `spring.task.scheduling.pool.*`.

## 11. Do @Async, CompletableFuture, and background tasks keep the JVM alive?

### Spring @Async

`@Async` typically uses a Spring `Executor`/`TaskExecutor`. It does not carry an independent "keep application alive" flag separate from the configured executor.

~~~java
@Async
public CompletableFuture<Void> sendNotification() {
    // logic...
    return CompletableFuture.completedFuture(null);
}
~~~

This is a snippet requiring Spring `@Async`, `@EnableAsync` or equivalent async setup, importing `CompletableFuture`, and placing the method in an appropriate bean. Receiving a future at the caller does not mean the JVM automatically waits for the future to finish before exiting. You need to know whether the executor uses daemon platform threads, non-daemon platform threads, or virtual threads, and how errors/cancellation should be handled.

If using `@Async` for **work that must finish before the application is ready**, running asynchronously and returning from a startup hook may be the wrong design. Wait on the future with a controlled timeout in startup orchestration or use another suitable workflow; do not rely on non-daemon threads to "luckily keep the JVM alive".

### CompletableFuture is not a lifecycle mechanism

~~~java
CompletableFuture<Void> task =
        CompletableFuture.runAsync(() -> doWork());
~~~

This snippet requires `CompletableFuture` and a `doWork()` method. By default, async tasks may use the common ForkJoinPool, where thread factory/daemon behavior depends on environment and configuration; under certain runtime conditions there are other fallbacks. Do not tie correctness to generic assumptions that "commonPool always keeps the JVM alive" or "is always daemon in every case".

For control, supply an explicit executor, track the `Future`, and shut down the executor when the application exits. If it is a Spring-managed component, integrate with the bean lifecycle.

### Task completion and thread pool completion are two different things

- `Future.isDone() == true`: that individual task completed, failed, or was canceled.
- `ExecutorService.isShutdown() == true`: the pool received a shutdown request, not necessarily that all tasks finished.
- `ExecutorService.isTerminated() == true`: the pool has terminated after shutdown.
- `Thread.isAlive() == true`: a thread is still alive, possibly with no useful tasks left.
- `ApplicationReadyEvent`: Spring Boot reached a startup milestone, not confirming all background futures are done.

Distinguishing these states avoids bugs like "the job is done yet the process stays up" or "app is ready yet backlog isn't processed".

## 12. Graceful shutdown: stop properly, don't rely on daemon to drop work

Turning every worker into a daemon is not a safe fix for hung processes. A daemon can be cut off by JVM shutdown while:
- writing files or committing a transaction;
- sending messages and waiting for acknowledgment;
- updating caches or checkpoints;
- holding locks or connections;
- flushing logs/telemetry.

When the JVM exits because only daemons remain, there is no guarantee daemons receive an interrupt or finish `finally` blocks. Important work therefore needs controlled lifecycles, durable progress persistence, and cancellation handling.

### Using @PreDestroy in Spring Boot 3.x

Example bean managing its own worker:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class ManagedWorker {

    private Thread worker;

    @PostConstruct
    void start() {
        worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    doOneUnitOfWork();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }, "managed-worker");
        worker.setDaemon(false);
        worker.start();
    }

    private void doOneUnitOfWork()
            throws InterruptedException {
        Thread.sleep(1000);
    }

    @PreDestroy
    void stop() {
        if (worker == null) {
            return;
        }
        worker.interrupt();

        try {
            worker.join(3000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

This is an **illustrative bean suitable for a Spring Boot 3.x application**, using `jakarta.annotation`. It simulates work via `Thread.sleep` without real business logic. When the context closes, Spring calls `@PreDestroy`, sends an interrupt, and waits up to three seconds. If the worker ignores interrupts or blocks on uninterruptible I/O, stronger timeouts/metrics and cleanup policies are needed; `join(3000)` does not forcibly kill the thread if it remains alive after the timeout.

**Do not spawn lots of raw threads like this simple example in production.** Prefer `TaskExecutor`/`TaskScheduler` or a managed `ExecutorService` with proper lifecycle, concurrency limits, and queues.

### Managed executor

For a pool, typical lifecycle:

~~~java
executor.shutdown();

if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
    executor.shutdownNow();
}
~~~

This Java snippet requires `ExecutorService`, `TimeUnit`, and handling `InterruptedException`. `shutdownNow` also only attempts to interrupt tasks and returns waiting tasks; it cannot force an uncooperative task to exit. For critical data-processing applications, combine idempotency, checkpoints, and retry after restart.

### SmartLifecycle and shutdown phases

Spring supports `SmartLifecycle` for components needing phased start/stop coordination; auto-configured executors/schedulers also manage lifecycles depending on type. Use the right abstraction when components depend on resource-closing order. Do not call `System.exit` from a bean merely because you don't know how to stop a worker.

## 13. Tools to diagnose which thread is keeping the JVM alive

When application logs report ready or the context has closed yet the process has not exited, first confirm whether any **non-daemon threads remain alive** and what state they are in.

### JDK tools

On a machine with JDK and attach permissions:

~~~bash
jcmd PID Thread.print
~~~

or:

~~~bash
jstack PID
~~~

Replace `PID` with the actual process id. Thread dumps typically show thread names, daemon markers when present, stack traces, and `RUNNABLE`/`WAITING`/`TIMED_WAITING` states. Inspect stacks for workers waiting on `BlockingQueue.take`, `CountDownLatch.await`, `ThreadPoolExecutor.getTask`, network I/O, or deadlocks. Do not immediately blame a single daemon thread for holding the JVM; the culprit is usually an alive **non-daemon** thread.

### Inspecting the process from the OS

On Linux:

~~~bash
ps -ef | grep java
ps -L -p PID -o pid,tid,stat,comm
~~~

`ps -L` displays OS threads tracked by the operating system, **not a complete list of every Java 21+ virtual thread**. When using virtual threads, use virtual-thread-aware tools such as the corresponding `jcmd`/JFR commands for your JDK version.

### Logging thread info from Java itself

~~~java
Thread current = Thread.currentThread();

System.out.println("threadName=" + current.getName());
System.out.println("daemon=" + current.isDaemon());
System.out.println("alive=" + current.isAlive());
System.out.println("state=" + current.getState());
~~~

This is a snippet inside a method. It only reports details of the thread running this code, not a conclusion for the entire process. You can observe thread snapshots via `Thread.getAllStackTraces()` during diagnostics, though snapshots can miss concurrently created/terminated threads and must not be used as production coordination.

### Finding a pool forgotten to be shut down

Useful signs:
1. Logs indicate the business job finished, yet `java -jar` does not return to the prompt.
2. The thread dump still shows `pool-1-thread-1` or custom-named workers `WAITING` in a pool queue.
3. An `ExecutorService` received tasks but never had `shutdown` called.
4. After adding shutdown at the right lifecycle point, the process exits naturally.
5. If the context already closed yet custom threads outside the container remain, add cleanup to the owning bean/service.

Do not call `System.exit` to hide a thread leak before finding the root cause. A "forcibly closed" process can still drop work and corrupt data.

## 14. Scenario matrix and right choices

| Symptom | Possible cause | What to check or fix |
| --- | --- | --- |
| `main` returns yet process doesn't exit | Remaining non-daemon thread or keep-alive | Thread dump, executors, schedulers, `spring.main.keep-alive` |
| CLI app exits before daemon task finishes writing | No non-daemon threads left | Await task deliberately, use proper executor/lifecycle |
| Virtual threads enabled, `@Scheduled` misses next runs | Scheduler only has daemon virtual threads, JVM exits | `spring.main.keep-alive=true` and verify Java 21+ |
| Executor task finished yet Java keeps running | Non-daemon pool worker waiting for next job | `shutdown` / `awaitTermination` |
| Calling `setDaemon(false)` on running thread fails | `IllegalThreadStateException` | Configure before `start`, choose proper ThreadFactory |
| Sleeping worker keeps process alive | Sleeping does not terminate a thread | Provide stop/interrupt signal and handle interruption |
| Bean `@PreDestroy` ran yet JVM stays up | Custom unmanaged thread ignoring interrupt | Track/join worker, explicitly stop pool |
| Web server still serves after "Started" log | Infrastructure threads keep JVM alive | Usually expected behavior; inspect server lifecycle |
| `ApplicationReadyEvent` fired yet background job still runs | Ready doesn't automatically await spawned tasks | Coordinate readiness or await tasks if startup-critical |
| Daemon thread logs miss final lines | JVM exited before daemon finished | Do not assign mandatory work to unawaited daemons |
| Kubernetes stops pod and job loses data | Short shutdown grace period, uncooperative task | Timeouts/cancellation/checkpoints, terminationGracePeriodSeconds |
| `System.exit` kills process despite non-daemon threads | Explicit JVM shutdown | Use only at proper boundaries, clean resources first |

## 15. Troubleshooting workflow when Spring Boot "won't exit" or "exits early"

### Case A — Does not exit after job completion

1. Identify application type: web, CLI, scheduled worker, or message consumer.
2. Verify `SpringApplication.run` finished and whether the context is still open.
3. Check `spring.main.keep-alive`, especially on Java 21+ with virtual threads.
4. Capture a thread dump when the business job reports completion.
5. Find live non-daemon threads, which executor/scheduler created them, and why they haven't stopped.
6. Add shutdown/interrupt/join at the proper lifecycle point rather than converting all threads to daemon.
7. Re-run and verify the process exits on its own, data is flushed/committed, and the exit code is right.

### Case B — Exits before tasks finish

1. Check whether the task belongs to `@Async`, `CompletableFuture`, `@Scheduled`, raw `Thread`, or virtual threads.
2. Check the daemon flag or ThreadFactory/Executor in use; do not guess from method names.
3. Determine whether the task must finish before the process/traffic ends.
4. If required: use `Future.get`/`join` in timeout-bounded orchestration, or a durable queue/checkpoint workflow.
5. If it is a long-running scheduler: manage application keep-alive/lifecycle rather than just spawning daemons.
6. Write a shutdown test: send a signal, observe cancellation and resource cleanup, confirm no mandatory jobs are lost.

### Case C — After enabling spring.threads.virtual.enabled=true, process exits by itself

1. Verify the **actual JDK is Java 21+** and the Spring Boot version supports the property.
2. Check whether scheduler/executor beans switched to virtual-thread implementations.
3. Check if any non-daemon platform threads remain serving a web server; **do not assume**.
4. Try `spring.main.keep-alive=true` per Boot guidance for long-running applications.
5. Stop the process cleanly and verify shutdown hooks/context cleanup.
6. Review pinning, concurrency, and executor configuration if performance changes, not just lifecycle.

## 16. Anti-patterns to avoid

**Anti-pattern 1 — Using daemon to "kill" a hung process.**  
If a thread wasn't shut down properly, turning it into a daemon just lets the JVM exit mid-task. Consequences can include data loss or dirty resource release.

**Anti-pattern 2 — Calling System.exit in @PostConstruct or @EventListener to fix lifecycle.**  
This can interrupt a partially initialized context, complicate debugging, and bypass error/health handling. Use meaningful startup exceptions, lifecycle hooks, and intentional shutdown instead.

**Anti-pattern 3 — Assuming @Scheduled keeps the JVM alive on its own.**  
Especially wrong when the scheduler uses virtual threads. Spring Boot recommends enabling keep-alive when an application depends on such daemon workers.

**Anti-pattern 4 — Treating only RUNNABLE thread state as alive.**  
Non-daemon `WAITING` still keeps the JVM alive; daemon `RUNNABLE` does not keep the JVM alive when no other non-daemon threads exist.

**Anti-pattern 5 — Closing only ApplicationContext while forgetting custom executors.**  
Spring cannot automatically manage what it doesn't own; raw threads and pools created outside the container require explicit cleanup.

**Anti-pattern 6 — Thinking System.exit guarantees all finally blocks run.**  
Shutdown hooks have limits and forcible stops bypass them. Protect critical data with transactions, checkpoints, idempotency, and task management.

**Anti-pattern 7 — Equating daemon with an OS detached/background process.**  
The daemon flag belongs to `java.lang.Thread`. It does not turn a thread into a separate service, spawn a new process, or auto-start a process with the OS.

## 17. Thread and task design checklist for Spring Boot

- Clearly identify the app type (CLI/web/scheduler/consumer) and lifecycle goal.
- If creating a platform `Thread`, set the daemon flag **before `start()`**; never modify it on a live thread.
- Do not assign work requiring completion to daemon threads without proper orchestration/awaiting.
- Manage `ExecutorService` with `shutdown`, `awaitTermination`, and interruption/timeouts.
- For Spring beans, integrate with `@PreDestroy`/`SmartLifecycle`/managed task infrastructure.
- Check startup events: `ApplicationReadyEvent` does not mean every self-spawned background task has finished.
- With Java 21+ and virtual threads, remember virtual threads are daemons; consider `spring.main.keep-alive=true` for long-running apps.
- Inspect the actual task executor/scheduler; do not infer daemon status from `@Async` or `@Scheduled` names.
- Keep shutdown graceful: stop accepting new work, finish or cancel tasks, flush/checkpoint, close pools/context.
- Test both directions: **the process does not exit while mandatory work remains**, and **the process exits cleanly once work finishes**.
- When a process behaves unexpectedly, capture a thread dump before adding `System.exit` or flipping every ThreadFactory.
- Use Java 17 for platform-thread examples; use Java 21+ for `Thread.ofVirtual()`.
- Do not rely on cross-thread stdout ordering without synchronization; use latches for deterministic examples.
- When running in containers, verify grace periods, signal handling, and actual load before deploying.

## 18. Self-check questions

**1. When main finishes, must the JVM necessarily exit?**  
No. If non-daemon threads remain alive, the JVM normally continues running.

**2. Does a non-daemon thread in WAITING keep the JVM alive?**  
Yes. It is still a live non-daemon thread.

**3. Is a daemon thread guaranteed to finish its finally block before JVM shutdown?**  
No. The JVM can exit once only daemon threads remain without waiting for them to complete.

**4. When may Thread.setDaemon(true) be called?**  
Before the thread is started. Calling it on a live thread can throw `IllegalThreadStateException`.

**5. How does daemon differ from thread priority?**  
Daemon affects JVM termination conditions; priority provides scheduling hints, which is a separate aspect.

**6. Where does a new thread normally inherit its daemon flag from?**  
From the thread that created it, unless a ThreadFactory/API call changes it.

**7. Can calling join on a daemon thread keep the process alive?**  
Yes, if the caller is a waiting non-daemon thread; the still-alive caller keeps the JVM up, not the daemon changing type.

**8. Does an executor task completing mean the pool has stopped?**  
No. The pool may still have non-daemon workers waiting for new tasks; it must be shut down.

**9. Why does the web server keep running after SpringApplication.run returns?**  
The web server and infrastructure can have live threads keeping the process up, independent of main passing run.

**10. Does @Scheduled with virtual threads keep the JVM alive automatically?**  
Not guaranteed. Virtual threads are always daemon, so Spring Boot recommends `spring.main.keep-alive=true` when needed.

**11. Can Thread.ofVirtual() be used on Java 17?**  
No. The official virtual threads API requires Java 21+.

**12. Does spring.main.keep-alive=true complete all background tasks?**  
No. It keeps the application alive; it does not synchronize, enforce timeouts, or track job outcomes.

**13. Does System.exit wait for all non-daemon workers to finish before shutting down?**  
No. It initiates shutdown even while workers are still alive; cleanup must be designed separately.

**14. How do you find out why the JVM isn't exiting?**  
Capture a thread dump with `jcmd PID Thread.print`/`jstack PID`, find live non-daemon threads, waiting pools, and unclosed resources.

**15. If the Spring context closes while a raw Thread you created remains alive, can the JVM keep running?**  
Yes, if that thread is non-daemon. Closing the context does not automatically interrupt every thread outside managed lifecycles.

## 19. Official references for version cross-checking

- [Oracle Java SE 17 — Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): daemon inheritance, `setDaemon`, `isDaemon`, `isAlive`, and JVM termination conditions.
- [Oracle Java SE 17 — Runtime API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt`, and shutdown hooks.
- [Oracle Java SE 17 — Executors API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): default thread factory, thread pools.
- [Oracle Java SE 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `awaitTermination`, and `isTerminated`.
- [Spring Boot 3.5 — SpringApplication / Virtual Threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): daemon virtual threads and `spring.main.keep-alive`.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured executors/schedulers and virtual threads configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.main.keep-alive=false` by default.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual/platform threads, daemon semantics, `Thread.ofVirtual()`.
- [Oracle JDK 17 — jcmd tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print` and JVM diagnostics.

**Conclusion:** the question "will the JVM keep running?" must be answered from **the real lifecycle of non-daemon threads and shutdown/keep-alive policies**, not from whether `main` returned, the `@Async` annotation, or the existence of a `@Scheduled` job. For critical tasks, combine thread policies, resource lifecycles, timeouts/cancellation, and real observation so the process neither exits prematurely nor hangs indefinitely.