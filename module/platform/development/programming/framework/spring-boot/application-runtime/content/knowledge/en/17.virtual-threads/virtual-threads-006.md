# Virtual Threads Are Daemon Threads and the Risk of Background Apps Exiting Early

## 1. What happens when enabling virtual threads for Spring Boot

Since Java 21, **virtual threads** have been an official concurrency mechanism enabling many I/O-waiting tasks to run with lower thread overhead than traditional platform threads. Spring Boot 3.3 can use virtual threads for task execution and scheduling. However, one JVM constraint is often overlooked: **every virtual thread is a daemon thread**.

**Daemon threads do not keep the JVM process alive once all non-daemon threads have finished.** Consequently, a Spring Boot application *without a web server*, running only background tasks or **@Scheduled**, may start successfully and then **exit early before the first scheduled job runs** if all remaining threads are virtual/daemon threads.

Example of a program managing a schedule every 30 minutes:

~~~text
main (platform, non-daemon)
    |
    +-- SpringApplication.run(...)
    |      +-- create ApplicationContext
    |      +-- register ScheduledAnnotationBeanPostProcessor
    |      +-- auto-configure scheduler using virtual threads
    |      +-- invoke runners, publish ApplicationReadyEvent
    |
    +-- run(...) returns
    +-- main() exits
              |
              v
      any non-daemon threads remaining?
              |
              +-- NO  -> JVM starts shutdown
              |           scheduled job not due yet -> does not run
              |
              +-- YES -> JVM can stay alive
                          scheduler has a chance to trigger
~~~

This does not mean Spring Boot failed to detect **@Scheduled**. The scheduler may have been registered properly, yet **the JVM terminated before it had a chance to run**. Therefore, merely seeing **Started Application** or a passing context test is insufficient to confirm a background service actually stays running.

Spring Boot 3.3 provides two properties with distinct responsibilities:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

- **spring.threads.virtual.enabled=true:** allows Boot-supported infrastructure to use virtual threads when running on Java 21+.
- **spring.main.keep-alive=true:** keeps the JVM running even when remaining work threads are daemon/virtual threads, suitable for a long-running background service.

This article follows **Java 21, Spring Boot 3.3.13, and Spring Framework 6.1**. Examples using **Thread.ofVirtual()** and **Thread.isVirtual()** cannot compile on JDK 17.

## 2. JVM rule: non-daemon keeps the process alive, daemon does not

Java defines a thread as either daemon or non-daemon. This status affects **when the JVM is allowed to begin normal shutdown**, rather than indicating the importance of the work.

| Criterion | Platform thread | Virtual thread (Java 21) |
| --- | --- | --- |
| Thread object | java.lang.Thread | java.lang.Thread |
| Can be daemon | Yes | **Always daemon** |
| Can be non-daemon | Yes | **No** |
| Can keep JVM alive | Yes, while non-daemon is active | No, merely by existing |
| Uses isDaemon() API | Yes | Yes, always true |
| Uses isVirtual() API | false | true |
| Change daemon before start | Possible for platform thread | Cannot set false for virtual thread |
| Used for I/O work | Yes | Yes, typically a suitable use case |

**Survival rule:** the JVM begins its shutdown sequence once all **started non-daemon threads** have terminated. Unfinished virtual threads do not prevent that.

~~~text
State A:
main (non-daemon)       alive
background-vt (daemon)  waiting
=> JVM stays alive because of main.

State B:
main (non-daemon)       terminated
background-vt (daemon)  waiting
other non-daemon        none
=> JVM begins shutdown, even though background-vt is not done.

State C:
main (non-daemon)       terminated
background-vt (daemon)  waiting
server-thread           non-daemon, alive
=> JVM stays alive because of server-thread.
~~~

When main ends, **you cannot immediately infer the JVM will exit**: a web server, consumer, or another thread might still be non-daemon. However, if a non-web program truly only has daemon tasks left, the risk of early exit is real.

### 2.1. Why is a virtual thread always a daemon?

Virtual threads were designed by Java for **many thread-per-task** usage. They are scheduled by the JVM onto a set of carrier platform threads, letting a virtual thread pause while waiting on I/O without holding an OS thread exclusively the entire time.

The ability to spawn huge numbers does not mean every virtual thread should be responsible for keeping the JVM alive indefinitely. Java separates **task lifecycle** from **process lifecycle** so the application explicitly decides whether to wait for results, keep a long-lived service running, or exit.

Daemon status **does not mean** a virtual thread has lower priority, cannot perform I/O, or cannot run critical business logic. It simply is not a JVM keep-alive mechanism.

### 2.2. Thread.currentThread() reflects the virtual thread, not the carrier

When code runs inside a virtual thread:

~~~java
Thread current = Thread.currentThread();
System.out.println(current.isVirtual());
System.out.println(current.isDaemon());
~~~

The output is:

~~~text
true
true
~~~

Even though the virtual thread executes on a **carrier platform thread**, Thread.currentThread() returns the current virtual Thread. Do not treat the carrier thread as a non-daemon keeper guaranteed by the framework for the application.

### 2.3. Cannot convert a virtual thread to non-daemon

On Java 21:

~~~java
Thread virtual = Thread.ofVirtual()
        .name("background-vt")
        .unstarted(() -> {});

System.out.println(virtual.isDaemon()); // true
virtual.setDaemon(false);               // IllegalArgumentException
~~~

This is a snippet inside a Java method. Java specifies that **Thread.setDaemon(false)** on a virtual thread throws **IllegalArgumentException**; there is no **Thread.ofVirtual().daemon(false)** builder option. Thus, changing the daemon flag is not a solution.

## 3. Standalone Java 21 demo: task still waiting yet process exited

The example below creates a virtual thread and uses a CountDownLatch to ensure the thread has actually started. Then the virtual thread waits on a latch **that is never released**, while main exits.

Create **VirtualDaemonExitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class VirtualDaemonExitDemo {

    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread worker = Thread.ofVirtual()
                .name("background-vt")
                .start(() -> {
                    Thread current = Thread.currentThread();

                    System.out.println(
                            "VT | virtual=" + current.isVirtual()
                            + " daemon=" + current.isDaemon());

                    started.countDown();

                    try {
                        neverReleased.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }

                    System.out.println("VT | finished");
                });

        started.await();

        Thread main = Thread.currentThread();
        System.out.println(
                "MAIN | virtual=" + main.isVirtual()
                + " daemon=" + main.isDaemon());
        System.out.println("MAIN | returning");

        // Do not join(worker), do not release neverReleased.
    }
}
~~~

Run with **JDK 21+**:

~~~bash
javac VirtualDaemonExitDemo.java
java VirtualDaemonExitDemo
~~~

In a standard terminal Java run, the lines printed by the program are:

~~~text
VT | virtual=true daemon=true
MAIN | virtual=false daemon=false
MAIN | returning
~~~

**There is no VT | finished line.** The task is still waiting on neverReleased.await(), yet no non-daemon thread remains to keep the JVM running after main finishes.

Design detail of the example: started.await() only makes main wait until the virtual thread **prints the observation line**, not until it finishes. Without CountDownLatch started, main could exit even before VT prints its first line, making output nondeterministic.

**Note:** an IDE, debugger, or Java agent may create additional non-daemon threads, making process lifetime in that environment differ from a standalone terminal Java command. Use a separate executable process when experimenting.

### 3.1. What if we switch to a non-daemon platform thread?

If you change Thread.ofVirtual() to **Thread.ofPlatform().daemon(false)**, the worker waiting on the latch will **keep the JVM alive** even after main returns. This difference often makes an application that previously ran on a platform scheduler thread become unstable after switching to virtual threads.

Do not use a platform thread waiting forever as a production solution; that creates shutdown hangs and lacks lifecycle management.

## 4. Java 21 demo: waiting for finite tasks with join

For a finite CLI job, the right approach is **waiting for completion**, not keeping the process alive indefinitely.

Create **VirtualThreadJoinDemo.java**:

~~~java
public class VirtualThreadJoinDemo {

    public static void main(String[] args)
            throws InterruptedException {

        Thread job = Thread.ofVirtual()
                .name("report-job")
                .start(() -> {
                    System.out.println(
                            "TASK | virtual="
                            + Thread.currentThread().isVirtual());
                    System.out.println("TASK | completed");
                });

        job.join();
        System.out.println("MAIN | joined");
    }
}
~~~

Run:

~~~bash
javac VirtualThreadJoinDemo.java
java VirtualThreadJoinDemo
~~~

Stdout:

~~~text
TASK | virtual=true
TASK | completed
MAIN | joined
~~~

**join() makes the non-daemon main thread wait** until the virtual thread finishes. The virtual thread remains daemon, yet the JVM does not shut down because main stays alive.

A cleaner variant for multiple finite tasks:

~~~java
try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> result =
            executor.submit(() -> "report-complete");

    System.out.println(result.get());
}
~~~

This is a snippet requiring imports for **ExecutorService**, **Executors**, **Future**, and handling checked exceptions. Java 21 supports ExecutorService as AutoCloseable; try-with-resources closes the executor and, per the API's semantics, waits for tasks when needed. Suitable for batch jobs requiring controlled termination.

### 4.1. Why doesn't Thread.sleep replace join?

The code:

~~~java
Thread.ofVirtual().start(() -> performBusinessTask());
Thread.sleep(500);
~~~

is a snippet illustrating an anti-pattern; assume performBusinessTask() exists. 500 ms is merely a guess. When CI is slow or an external API times out, the task may still be unfinished and get cut off when main exits.

**Wait for an actual condition**: Thread.join(), Future.get(), CountDownLatch, or another completion contract; use timeouts and proper error handling when time bounds are needed.

## 5. How does Spring Boot auto-configure virtual-thread executors and schedulers?

Spring Boot 3.3 supports:

~~~properties
spring.threads.virtual.enabled=true
~~~

when the runtime is Java 21+. Without a **custom Executor** altering the default selection, Spring Boot can use:

- **SimpleAsyncTaskExecutor** with virtual threads for Boot-integrated async work such as **@EnableAsync**, Spring MVC asynchronous request processing, and certain other integrations.
- **SimpleAsyncTaskScheduler** with virtual threads when the application needs a scheduler, such as when **@EnableScheduling** is enabled.
- If virtual threads are not enabled, the typical corresponding defaults are **ThreadPoolTaskExecutor** and **ThreadPoolTaskScheduler**.

This is an *auto-configuration choice*, not a rule turning every thread across the entire JVM virtual automatically. Components such as the **main thread**, library threads, and **custom Executors/TaskSchedulers** can still use platform threads.

### 5.1. When can't you expect an auto-configured virtual executor?

If the application defines:

~~~java
@Bean
Executor customExecutor() {
    return Executors.newFixedThreadPool(4);
}
~~~

this is a snippet requiring imports and proper Executor shutdown handling. A custom Executor bean can prevent/affect auto-configuration and executor selection. The virtual threads property does not automatically turn a custom fixed-thread-pool into virtual threads.

Likewise, a manually declared **ThreadPoolTaskScheduler** still uses platform threads unless configured otherwise itself.

Verify the actual executor/scheduler via bean wiring and Thread.currentThread().isVirtual() inside callbacks. Do not conclude from a single property alone.

### 5.2. Pool properties may no longer apply

With **SimpleAsyncTaskExecutor** creating a virtual thread per task, **ThreadPoolTaskExecutor** pool-tuning properties no longer have the same effect:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
~~~

These properties do not automatically become a limit of 16 virtual tasks. With SimpleAsyncTaskScheduler, ThreadPoolTaskScheduler pool properties do not apply the same way either.

Thus, if downstream can only handle 20 concurrent database queries, you must use a **Semaphore**, connection-pool size, bulkhead, or dedicated limiting mechanism. **Virtual threads do not add capacity to databases/networks**.

## 6. Why is @Scheduled-only the riskiest case?

With a non-web application:

~~~java
@SpringBootApplication
@EnableScheduling
public class ScheduleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScheduleApplication.class, args);
    }
}
~~~

Spring Boot can register scheduled beans properly, invoke runners, and publish ApplicationReadyEvent. Yet:

~~~text
0s       main calls run()
1s       context refresh finishes
1s       ApplicationReadyEvent
1s       main() returns
1s       only daemon/virtual work remains
1s       JVM starts shutdown
5s       @Scheduled expected to trigger => process no longer exists
~~~

The timestamps are **illustrative examples** only.

**A ready context does not prove a future scheduled callback will execute.** Neither does the presence of scheduled metadata or executor beans in the context keep the JVM alive.

### 6.1. Does @Scheduled always run after ApplicationReadyEvent?

No. Depending on scheduler registration timing, initialDelay, runner duration, and machine load, a scheduled callback might execute before startup/runners finish. However, for a job whose initialDelay exceeds startup duration, it definitely needs the process to remain alive until the scheduled mark.

Do not rely on accidental timing order to solve keep-alive. Choose the service lifecycle explicitly.

### 6.2. Virtual threads do not turn cron into a durable scheduler

**@Scheduled** typically runs inside each JVM instance. If the process terminates, the schedule is not automatically handed off to another process. With multiple replicas, each instance may run the same job, causing duplicate work.

If durable execution is required, you need a distributed scheduler/job database/queue, retries, and idempotence. **Keep-alive only keeps the process alive**, and does not guarantee jobs are persisted or run exactly once cluster-wide.

## 7. How Spring Boot 3.3 keeps the JVM alive: spring.main.keep-alive

Configuration:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Spring Boot 3.3 recommends enabling **spring.main.keep-alive=true** when using virtual threads, especially with @Scheduled or other technologies that only create daemon threads.

### 7.1. Two properties solve two separate problems

| Property | Function | Does not guarantee |
| --- | --- | --- |
| **spring.threads.virtual.enabled=true** | Boot-supported execution components can use virtual threads | Does not keep the process alive |
| **spring.main.keep-alive=true** | Ensures JVM stays alive even when only virtual/daemon work remains | Does not guarantee job success or survival across SIGKILL |

Enabling keep-alive **does not change** the Thread.isDaemon() value of virtual threads. Java 21 still returns true. Spring Boot uses a mechanism to maintain application lifetime rather than hacking the daemon flag.

### 7.2. Keep-alive does not solve every shutdown or error

This property does not prevent:

- SIGTERM/Ctrl+C and normal shutdown paths.
- System.exit(...) explicitly called by the application.
- SIGKILL, crashes, out-of-memory errors, or container orchestration terminating the process.
- ApplicationContext closing per lifecycle.
- Async work throwing exceptions.
- Lost jobs because the executor only held tasks in memory.

Therefore **keep-alive is not a durable queue**, nor is it a mechanism that “guarantees every virtual thread finishes”.

### 7.3. Which workloads should enable keep-alive?

**Suitable:** non-web background services that must stay alive continuously to trigger scheduled jobs, consume messages, handle listeners/watchers, and execute tasks when future events arrive.

**Not always suitable:** finite CLI/batch jobs that need to finish one piece of work and exit with a clear exit code. For those, await completion and close the context/exit the process intentionally.

## 8. Complete Spring Boot 3.3 / Java 21 example

The lab keeps the exact same program, running sequentially with **keep-alive=false** and **keep-alive=true**, observing whether the process stays alive long enough for a scheduled tick.

### 8.1. Maven structure

~~~text
virtual-keepalive-demo/
  pom.xml
  src/main/java/com/example/keepalive/VirtualKeepAliveApplication.java
~~~

Use **JDK 21+**, Spring Boot **3.3.13**, and Maven 3.9+.

**pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>virtual-keepalive-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 8.2. Complete Java code

Create **src/main/java/com/example/keepalive/VirtualKeepAliveApplication.java**:

~~~java
package com.example.keepalive;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableScheduling
public class VirtualKeepAliveApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(VirtualKeepAliveApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        application.run(args);

        System.out.println("MAIN | run returned");
        // Do not close context, do not call System.exit().
    }

    @Bean
    ApplicationRunner startupThread() {
        return args -> {
            Thread thread = Thread.currentThread();
            System.out.println(
                    "RUNNER | virtual=" + thread.isVirtual()
                    + " daemon=" + thread.isDaemon());
        };
    }
}

@Component
class BackgroundHeartbeat {

    private final AtomicInteger counter = new AtomicInteger();

    @Scheduled(initialDelay = 5000, fixedRate = 2000)
    public void tick() {
        Thread thread = Thread.currentThread();
        int sequence = counter.incrementAndGet();

        System.out.println(
                "TICK | count=" + sequence
                + " virtual=" + thread.isVirtual()
                + " daemon=" + thread.isDaemon());
    }
}
~~~

**Code explanation:**

- **@EnableScheduling** enables Spring's @Scheduled detection mechanism.
- **WebApplicationType.NONE** avoids having an HTTP server create threads that keep the process alive, keeping the demo focused on the scheduler.
- No custom **Executor** or **TaskScheduler** is declared, allowing Boot auto-configuration to operate per the virtual thread property.
- Synchronous **ApplicationRunner** typically runs on the main thread; isVirtual() returns false and isDaemon() returns false in a standard Java run.
- **@Scheduled(initialDelay=5000, fixedRate=2000)** waits about five seconds before the first tick, then schedules at a two-second cadence.
- **AtomicInteger** safely stores the count when callbacks may execute across multiple threads.
- **Thread.currentThread().isVirtual()** and **isDaemon()** inspect via API rather than guessing from thread names.
- After run, main prints **MAIN | run returned** and exits. There is no infinite sleep or manual Thread workaround.

### 8.3. Build

~~~bash
java -version
mvn -q -DskipTests package
~~~

Verify JDK 21+ for both **java** and **mvn**. If using Maven Wrapper on Windows:

~~~powershell
.\mvnw.cmd -q -DskipTests package
~~~

### 8.4. Run A: virtual threads enabled, keep-alive disabled

~~~bash
java -jar target/virtual-keepalive-demo-1.0.0.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=false
~~~

In a demo process without other non-daemon threads created, you typically see:

~~~text
RUNNER | virtual=false daemon=false
MAIN | run returned
~~~

Then the JVM can terminate before the first tick. If so, **no TICK lines appear**, even though @Scheduled was registered.

**Do not assert absolute output across every IDE, Java agent, or deployment.** Another library might hold a non-daemon thread and keep the process alive. What matters is verifying the **actual production environment** and lifetime policy.

### 8.5. Run B: virtual threads and keep-alive enabled

~~~bash
java -jar target/virtual-keepalive-demo-1.0.0.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=true
~~~

Startup typically prints:

~~~text
RUNNER | virtual=false daemon=false
MAIN | run returned
~~~

Yet **the process stays alive**. When the @Scheduled callback executes on Boot's virtual-thread SimpleAsyncTaskScheduler, the expected lines are:

~~~text
TICK | count=1 virtual=true daemon=true
TICK | count=2 virtual=true daemon=true
TICK | count=3 virtual=true daemon=true
~~~

TICK lines appear over time, without guaranteeing exact absolute timing due to scheduling latency. You can stop with Ctrl+C after a few cycles.

Key takeaway: **main returned, yet the scheduler kept running because application lifetime was preserved**. Virtual threads remain daemon=true; keep-alive does not change thread nature.

### 8.6. Run C: virtual threads disabled

~~~bash
java -jar target/virtual-keepalive-demo-1.0.0.jar \
  --spring.threads.virtual.enabled=false \
  --spring.main.keep-alive=false
~~~

In the default configuration with a platform-thread scheduler, Spring Boot can use ThreadPoolTaskScheduler; non-daemon platform scheduler threads typically keep the process alive to run TICK:

~~~text
TICK | count=1 virtual=false daemon=false
~~~

This is **illustrative output under default configuration**, not a rule for every custom scheduler. If a custom TaskScheduler uses a daemon factory, JVM retention behavior can differ.

### 8.7. Why not use spring.task.scheduling.pool.size to fix early exit?

When the executor/scheduler actually uses virtual threads, ThreadPoolTaskScheduler pool settings do not turn virtual threads into non-daemon threads. Changing:

~~~properties
spring.task.scheduling.pool.size=3
~~~

does not solve the daemon lifetime nature of virtual threads in SimpleAsyncTaskScheduler. When lifetime is needed, use **spring.main.keep-alive=true**; when concurrency limiting/tuning is needed, configure the selected scheduler/executor properly.

## 9. Differences between web, CLI, and background worker applications

### 9.1. Web application

Spring MVC on Tomcat or another web stack may own **non-daemon threads** that keep the JVM alive after main returns. Enabling virtual threads does not mean every web app will exit immediately.

However, if you switch the same artifact to **non-web** mode, or deploy an instance that only runs scheduled tasks, that non-daemon process-keeping source may disappear. Do not rely on results from a web deployment to guarantee a worker deployment shares the same lifecycle.

### 9.2. Finite CLI/batch job

A command:

~~~bash
java -jar importer.jar --input=data.csv
~~~

typically needs to **finish processing -> report status -> exit**. For this pattern:

~~~text
run()
  -> submit finite tasks
  -> Future.get()/join() or await result with timeout
  -> write output/commit
  -> close context
  -> return exit code per result
~~~

fits better than **infinite keep-alive**. Enabling keep-alive without a clear shutdown path can prevent a batch pod/CI step from ever reaching Completed status.

### 9.3. Continuous background service

Workers/schedulers/consumers awaiting future work need a **long-lived process**. With Java 21 virtual threads, proactively configure keep-alive, monitor heartbeats, and provide a proper shutdown path on SIGTERM.

**@Async** with an in-memory executor does not automatically provide durability or post-crash retries; if losing tasks is a business risk, consider Spring Batch, a database task table, a message broker/outbox, or dedicated job infrastructure.

## 10. Do not confuse readiness with process lifetime

Spring Boot publishes **ApplicationReadyEvent** after the application context refreshes and runners succeed. Yet the ready milestone **does not promise the JVM will survive long enough for a future scheduled tick**.

~~~text
Startup
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   +-- main() returns
   +-- no non-daemon threads remaining
   +-- JVM shutdown
   +-- future scheduled tick never occurs
~~~

**@Scheduled** may fire before or after ready depending on initialDelay and startup time. Do not treat a tick that happened to fire before ready as proof that process lifecycle is safe.

Even when ApplicationReadyEvent appears in logs, you need an **actual smoke test monitoring process survival after startup**.

## 11. Testing the Java daemon contract with JUnit 5

A small unit test can verify the daemon property without a Spring context. In the Maven demo, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **src/test/java/com/example/keepalive/VirtualThreadDaemonTest.java**:

~~~java
package com.example.keepalive;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VirtualThreadDaemonTest {

    @Test
    void virtualThreadCannotBeNonDaemon()
            throws InterruptedException {

        Thread vt = Thread.ofVirtual()
                .name("virtual-test")
                .unstarted(() -> {});

        assertTrue(vt.isVirtual());
        assertTrue(vt.isDaemon());

        assertThrows(IllegalArgumentException.class,
                () -> vt.setDaemon(false));

        vt.start();
        vt.join();
    }

    @Test
    void platformThreadCanBeNonDaemon()
            throws InterruptedException {

        Thread platform = Thread.ofPlatform()
                .daemon(false)
                .unstarted(() -> {});

        assertFalse(platform.isVirtual());
        assertFalse(platform.isDaemon());

        platform.start();
        platform.join();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

This test verifies the Java 21 contract: virtual threads are always daemon and cannot be changed to non-daemon. It **does not test Spring Boot keep-alive or whether the production process stays alive**.

### 11.1. Why isn't a simple @SpringBootTest enough?

A test:

~~~java
@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
    }
}
~~~

is a **snippet** checking Spring context loading. JUnit/Maven test runners have their own threads/lifecycle, which can keep the **test JVM** alive even when a standalone executable JAR would exit once main ends.

Therefore **contextLoads PASS does not equal standalone process lifetime PASS**. This is a common testing pitfall in scheduler-only applications.

### 11.2. Only a process-level smoke test checks the real risk

Test as follows:

1. Build the executable JAR with JDK 21.
2. Start the JAR in a **separate process**, passing the exact virtual/keep-alive properties.
3. Record the **MAIN | run returned** milestone.
4. Wait past **initialDelay** plus a reasonable scheduling buffer.
5. With keep-alive=true: the process must still be alive and emit at least one **TICK**.
6. Send SIGTERM/Ctrl+C to request normal termination.
7. Wait for shutdown with a timeout; if it fails to exit, treat that as a bug to fix.
8. With keep-alive=false: observe whether the process terminates before the tick; compare with the keep-alive config.

To automate, a test harness can use **ProcessBuilder** to launch a child JVM and **Process.isAlive()** to check. Example test logic:

~~~java
Process process = new ProcessBuilder(
        "java",
        "-jar",
        "target/virtual-keepalive-demo-1.0.0.jar",
        "--spring.threads.virtual.enabled=true",
        "--spring.main.keep-alive=true"
).inheritIO().start();

try {
    // In a real test: wait for the TICK condition via log/health signal
    // with a deadline, not just sleeping for a fixed duration.
    if (!process.isAlive()) {
        throw new AssertionError("Application exited too early");
    }
} finally {
    process.destroy();
    if (!process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)) {
        process.destroyForcibly();
    }
}
~~~

The snippet above **is only a skeleton**, needing a method/test wrapper declaring **throws Exception**, ensuring the JAR is built, and completing the TICK signal wait before using as an official test. It illustrates **observing an independent process and cleaning up**, not a complete JUnit test. Do not leave child processes orphaned in CI.

### 11.3. Do not verify by thread name alone

Inside an @Scheduled callback:

~~~java
Thread t = Thread.currentThread();
System.out.println(
        "virtual=" + t.isVirtual()
        + " daemon=" + t.isDaemon()
        + " name=" + t.getName());
~~~

The **isVirtual()** and **isDaemon()** methods reflect real APIs. A thread named **virtual-worker** can still be an arbitrarily named platform thread; names are not proof.

However, a callback running on a virtual thread **does not prove the JVM lacks other non-daemon threads**. Lifetime must be verified at the process level.

## 12. Shutdown and work data when keep-alive is enabled

Keeping the JVM alive is necessary for background services, yet it does not guarantee work finishes if stopped abruptly.

~~~text
SIGTERM / Ctrl+C
     |
     +-- SpringApplication shutdown hook
     +-- ApplicationContext close
     +-- ContextClosedEvent / SmartLifecycle stop
     +-- scheduler/executor stops accepting tasks
     +-- destruction callbacks like @PreDestroy
     +-- process exits
~~~

Exact ordering depends on Spring lifecycle phases and the dependency graph. **@PreDestroy is not guaranteed to run on SIGKILL or process crash**.

For business-critical work:

- Persist durable state/checkpoints before reporting completion.
- Prevent duplicates via idempotence.
- Have appropriate retry, timeout, dead-letter, or compensation policies.
- Stop accepting new jobs before draining running jobs.
- Use a suitable **termination grace period** when running in containers.
- Do not hold a task forever during shutdown waiting for a result that never arrives.

**spring.main.keep-alive** replaces none of those mechanisms.

### 12.1. SIGTERM and SIGKILL differ

SIGTERM gives the application a chance to shut down gracefully. SIGKILL, power loss, or node crashes give the JVM no chance to run full cleanup. If a container orchestrator sends SIGKILL after the grace period, in-memory virtual-thread work can be cut off mid-flight.

Rely on a durable job system for tasks that cannot be lost, not on the daemon flag or keep-alive property.

### 12.2. Do not swallow errors and report false success

If an async task fails, the JVM staying alive does not mean the task succeeded. Track futures/exceptions and publish appropriate metrics; for required jobs, report real failure status.

Conversely, if a process exits early with no stack trace in logs, do not assume a Spring config bug: distinguish **normal JVM shutdown due to no remaining non-daemon threads** from BeanCreationException, OOM, SIGTERM, or System.exit.

## 13. Common misconceptions

### 13.1. “Virtual threads run on carrier platform threads so they still keep the JVM alive”

False. Java makes no keeper guarantee through carrier threads; virtual threads are always daemon. Check actual non-daemon threads or use keep-alive intentionally.

### 13.2. “Having an @Scheduled bean makes the scheduler keep the process alive automatically”

Not necessarily. In Java 21 virtual-thread mode, the scheduler may leave only daemon threads. Do not treat the annotation as a process lifetime contract.

### 13.3. “Enabling virtual threads automatically enables keep-alive”

False. The two properties are independent. When a continuous background application is needed, explicitly declare **spring.main.keep-alive=true**.

### 13.4. “A virtual thread can be changed to non-daemon”

False. The Java 21 Thread API forbids it and **setDaemon(false)** throws IllegalArgumentException.

### 13.5. “main returning means context.close has run”

Not necessarily. main and ApplicationContext have distinct lifecycles. The JVM only starts shutdown when thread conditions and other shutdown mechanisms are met. Calling context.close() explicitly is a separate action.

### 13.6. “The web app runs fine so a background-only deployment will be fine”

Insufficient basis. Web servers may have non-daemon threads; non-web apps lack that source. Test each workload profile separately.

### 13.7. “A green @SpringBootTest proves the standalone scheduler will not exit”

False. The test runner has its own non-daemon threads. A **process-level** smoke test is required.

### 13.8. “Just increase pool size when using virtual threads”

False. Virtual schedulers/executors do not have platform-pool semantics. Pool size does not fix daemon lifetime; concurrency limits must follow downstream capacity.

### 13.9. “Enabling keep-alive guarantees all jobs finish before SIGKILL”

False. Keep-alive only keeps the process running under normal conditions, creating no durability guarantee.

### 13.10. “A finite CLI app should enable keep-alive so it doesn't lose jobs”

Not necessarily. If a CLI has finite work, **await completion** and exit; infinite keep-alive can hang the job pod/CI.

### 13.11. “Creating a non-daemon Thread that waits forever is a good solution”

Not recommended. It lacks lifecycle integration and easily prevents the process from stopping when the context closes. Spring Boot provides **spring.main.keep-alive**, which fits long-running background apps better.

### 13.12. “Seeing the Started Application log is enough to know scheduled jobs run”

False. Startup and scheduled ticks are two separate milestones. Metrics/logs/job state are needed to verify callbacks actually execute.

### 13.13. “Keep-alive prevents System.exit or closing the context”

False. Keep-alive is not a mechanism resisting explicit termination requests; proper shutdown paths and task completion must still be designed.

## 14. Safe operational strategy

### 14.1. Clearly identify the workload

| Application type | Policy to consider |
| --- | --- |
| Web service with embedded server | Check server lifetime, virtual-thread support, and shutdown; keep-alive can be enabled for explicit policy |
| Background scheduler-only | **Enable keep-alive**, verify ticks after startup |
| Long-running consumer | Manage lifecycle + keep-alive if only virtual/daemon threads remain |
| One-shot CLI/batch job | Await Future/join, return exit status, exit intentionally |
| Multi-replica scheduled jobs | Beyond keep-alive, coordination/locking or idempotence is also required |

### 14.2. Observe key signals

Know whether:

- The process stays **alive** after main and after initialDelay.
- When @Scheduled last ran.
- Succeeded/failed job counts, duration, and deadlines.
- Execution thread type via **isVirtual()/isDaemon()**.
- Whether executor/scheduler was overridden by custom beans.
- Whether there are abnormal errors or exit codes.
- Whether shutdown completes within deadline.
- Whether uncommitted tasks exist or need retry after restart.

Do not rely solely on thread names or startup logs. For deep debugging, use **jcmd**, thread dumps, or JDK Flight Recorder compatible with JDK 21, while ensuring a live process exists to capture data.

### 14.3. Virtual threads do not magically make I/O or CPU faster

Virtual threads can efficiently increase concurrency for I/O-waiting workloads; they do not make heavy CPU computations run faster. If millions of virtual tasks access a database with a 20-connection pool concurrently, the bottleneck remains the DB/pool.

Java 21 also has pinning issues in certain synchronized/native blocking scenarios; measure actual throughput and limit downstream calls. These concerns **differ from the daemon/early-exit issue**, yet can appear alongside it when migrating an application to virtual threads.

## 15. Pre-deployment checklist

- [ ] Actual runtime is **Java 21+**, with Maven/compiler also using a matching JDK.
- [ ] Spring Boot version supports both the virtual and keep-alive properties.
- [ ] Confirmed **spring.threads.virtual.enabled=true** in the target deployment.
- [ ] Distinguished **long-running services** from **finite batch jobs**.
- [ ] For non-web long-running services, enabled **spring.main.keep-alive=true**.
- [ ] Do not rely on virtual threads to keep the JVM alive.
- [ ] Do not call setDaemon(false) on virtual threads.
- [ ] @EnableScheduling is present and scheduled beans are properly managed.
- [ ] Checked the actual auto-configured or custom TaskScheduler.
- [ ] Do not rely on old platform pool settings to cap virtual concurrency.
- [ ] Tested JDK isDaemon/isVirtual and tested process lifetime separately.
- [ ] Launched standalone executable JAR and waited past scheduled initialDelay.
- [ ] Observed at least one scheduled tick while the process stayed alive.
- [ ] Tested shutdown with SIGTERM/Ctrl+C with a timeout.
- [ ] No orphaned child processes left in CI.
- [ ] Critical jobs have checkpoints, retries, and idempotence.
- [ ] With multiple replicas, mechanisms prevent duplicate execution when business requires.
- [ ] Finite CLIs await completion and exit rather than keeping the process alive forever.
- [ ] Do not infer job success from ApplicationReadyEvent.
- [ ] Logging and metrics show jobs actually running and their status.

## 16. Self-check questions

**Question 1.** On Java 21, can a virtual thread be non-daemon?

**Answer:** No. Virtual threads are always daemon; calling setDaemon(false) is invalid.

**Question 2.** When does the JVM begin normal shutdown?

**Answer:** Once every started non-daemon thread has ended; active daemon threads do not prevent the JVM from beginning shutdown.

**Question 3.** Can an @Scheduled-only app with virtual threads enabled exit immediately after startup?

**Answer:** Yes, if no other non-daemon thread keeps the JVM alive and keep-alive is not used.

**Question 4.** Which Spring Boot property helps address this risk?

**Answer:** **spring.main.keep-alive=true**.

**Question 5.** Does spring.threads.virtual.enabled=true replace keep-alive?

**Answer:** No. It selects the virtual-thread execution mechanism, and does not guarantee the JVM stays alive long-term.

**Question 6.** Why does Thread.join() allow a one-shot virtual task to finish?

**Answer:** Non-daemon main waits for the task to finish, so the JVM does not enter shutdown while main stays alive.

**Question 7.** Is a web app with non-daemon server threads guaranteed to exit on its own because of virtual threads?

**Answer:** No. Non-daemon server threads can keep the JVM alive.

**Question 8.** Is @SpringBootTest contextLoads enough to prove a non-web process will survive past a scheduled trigger time?

**Answer:** No. The test JVM has its own lifecycle/threads. A process-level smoke test is needed.

**Question 9.** Does keep-alive guarantee tasks are not lost on SIGKILL?

**Answer:** No. Persistence, checkpoints/retries, or durable job infrastructure are needed.

**Question 10.** Why doesn't spring.task.scheduling.pool.size solve the daemon status of virtual threads?

**Answer:** SimpleAsyncTaskScheduler uses a virtual threads model distinct from platform pools; pool-size settings do not alter daemon semantics.

**Question 11.** When a CLI application finishes a finite task, should keep-alive be enabled so the process never exits?

**Answer:** Usually no; await Future/join, report status, then close the context and exit.

**Question 12.** When multiple replicas use @Scheduled, does keep-alive guarantee only one job runs across the cluster?

**Answer:** No. Keep-alive manages each JVM individually; distributed job coordination is a separate concern.

## 17. Conclusion

**Virtual threads are always daemon threads in Java 21.** They can execute many I/O tasks efficiently, yet **do not keep the JVM alive** after all non-daemon threads finish. Therefore, a non-web Spring Boot application relying solely on a scheduler or background virtual tasks can exit early after startup, before scheduled jobs come due.

For **long-running background services**, use:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

For **finite batch jobs**, await results via Future/join and terminate intentionally. Do not equate keeping the process alive with guaranteeing job completion or durable delivery. Test with an independent executable process, verify ticks after initialDelay, and ensure shutdown/recovery are bounded and observable.

## 18. Official references

- Spring Boot 3.3.13 — Virtual Threads, daemon, and keep-alive: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Java SE 21 — Thread API (isDaemon, isVirtual, setDaemon): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- Oracle Java 21 — Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html