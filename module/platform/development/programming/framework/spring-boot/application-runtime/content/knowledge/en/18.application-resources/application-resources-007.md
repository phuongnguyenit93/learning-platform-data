# Detecting Thread, Connection, File, and Classloader Leaks in Spring Boot

A Spring Boot application can keep returning HTTP 200 for a long time while **holding onto resources it no longer needs**. When the number of threads, borrowed connections, file descriptors, or old classloaders continues rising with load and fails to return to a steady baseline after work ends, the system can suffer timeouts, `OutOfMemoryError`, file descriptor exhaustion, connection pool exhaustion, or very slow shutdowns.

The tricky part is that **increasing resource counts do not automatically prove a leak**. Thread pools commonly keep workers after tasks finish; HikariCP keeps **idle** connections for reuse; the JVM caches class metadata; the OS allocates many file descriptors for sockets and libraries. To reach an accurate conclusion, you must understand **who owns a resource, how long it should live, when it must be returned, and whether it is genuinely released**.

This lesson focuses on four categories within Spring Boot Application Runtime:

1. **Thread leaks:** threads or background tasks never stopped, executors or schedulers never shut down.
2. **Connection leaks:** JDBC/HTTP/message connections held too long or never returned to the pool.
3. **File/descriptor leaks:** streams, channels, sockets, or file handles left unclosed.
4. **Classloader leaks:** classloaders whose lifetime should have ended yet remain referenced; commonly seen during restarts/redeploys, plugins, or dynamically loaded modules.

The main examples use **Java 17+ and Spring Boot 3.3.x**. Diagnostic commands use common HotSpot JDK tools; support and diagnostic overhead depend on JVM/OS.

## 1. Distinguishing Active, Cached, and Leaked Resources

In practice, three different cases exist:

| Observation | Necessarily a Leak? | Why? |
|---|---|---|
| A pool keeps 10 threads even with no current jobs | No | Workers can be retained to avoid recreation overhead. |
| HikariCP has 8 idle connections | No | Idle connections were returned **to the pool**, rather than closing physical sockets immediately. |
| A servlet request holds a connection while a query runs | No | The connection has a valid owner during processing. |
| After hundreds of requests, active connections keep rising and never drop | **Suspicious** | Checkouts may not be returned or queries may be hanging. |
| File descriptor count grows and fails to return to baseline after a batch finishes | **Suspicious** | Streams/sockets/channels may not be closing. |
| Metaspace grows during startup and then stabilizes | No | Classloading and JIT/caching can produce legitimate growth. |
| After several reloads, an old classloader remains retained with all its classes | **Suspicious** | Threads, static references, listeners, or `ThreadLocal`s may retain the old classloader. |

**Practical definition:** a resource leak occurs when something that should have been released after a lifecycle remains **retained or unclosed**, causing resource consumption to trend upward across repeated similar lifecycles.

For the Java heap, a leak is usually **objects still reachable from GC roots even though business logic no longer needs them**, preventing the garbage collector from reclaiming them. For connections, file descriptors, and native handles, relying solely on a heap histogram **is not enough**, because they also hold state in the OS, pools, and external systems.

## 2. Diagnostic Strategy: Inspect Trends Before Stack Traces

A single point-in-time measurement can mislead. Conduct controlled measurements:

~~~text
Baseline after startup
       |
       v
Run small, deterministic, repeatable load
       |
       v
Wait for tasks to finish, pool to settle, backlog to clear
       |
       v
Re-measure the same set of signals
       |
       +-- Returns to steady level: likely normal usage
       |
       +-- Accumulates each cycle: investigate ownership
       |
       v
Capture detailed evidence: dumps / stacks / allocations / handles
       |
       v
Identify code creating the resource and code that must close it
       |
       v
Fix and re-run the controlled experiment
~~~

Items to record for each measurement:

- Uptime, code version, Java/Boot versions, JVM flags, replica count.
- Throughput, concurrency, active job count, timeouts/retries.
- Live thread count and thread names; queue length; active tasks.
- Pool connections active/idle/pending/max and checkout duration.
- Number of file descriptors/handles and what they point to.
- Loaded classes, Metaspace, and surviving classloaders across reload/redeploy cycles.
- GC/heap pressure, native memory, `too many open files` errors, or connection timeouts.

Observations must be **compared against workload**. An executor with 20 threads and 20 active jobs is completely different from an executor with 20 threads created because every request spawned a new unclosed pool.

## 3. Built-In Signals from Spring Boot Actuator

Add `spring-boot-starter-actuator` to use Micrometer metrics that Spring Boot auto-configures when conditions match. Not every metric is available on every OS or bean type.

Commonly useful metric names:

| Metric or Group | What to Watch | Notes |
|---|---|---|
| `jvm.threads.live` | Live thread count | Growth under load or pool initialization can be legitimate. |
| `jvm.threads.states` | Thread state distribution | `WAITING`/`BLOCKED` alone does not prove a leak. |
| `jvm.memory.used` | Heap/non-heap, including Metaspace via tags | Memory growth requires checking GC and steady-state plateau. |
| `jvm.classes.loaded` | Loaded class count | Does not directly show whether an old classloader is retained. |
| `process.files.open` | Open file descriptors, if OS/JVM supports it | Can include sockets/pipes, not just data files. |
| `jdbc.connections.active` | Borrowed/active connections | Depends on `DataSource` metadata and pool. |
| `jdbc.connections.idle` | Idle connections ready for reuse | `Idle > 0` is not by itself a leak. |
| `hikaricp.connections.active` | Hikari checked-out connections | Correlate with load, hold duration, and pool max. |
| `hikaricp.connections.pending` | Threads waiting for a connection | Sustained growth can indicate saturation or held connections. |
| `executor.active` / `executor.queued` | Active/queued tasks for instrumented executors | Not every executor is instrumented automatically. |

To inspect the metrics **actually registered**:

~~~properties
management.endpoints.web.exposure.include=health,metrics
~~~

Then query in a test environment:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/jvm.classes.loaded
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
~~~

**Important:** the metrics endpoint only returns meters **that have been registered**. If a name is absent, do not rush to conclude the feature is broken or the resource count is 0. Check the classpath, pool initialization timing, Micrometer configuration, OS, custom beans, and tags. For instance, the Hikari pool might not have initialized yet at the first measurement.

**Security:** never expose sensitive Actuator endpoints directly to the Internet. The `heapdump` and `threaddump` endpoints can leak data, system names, call stacks, or credentials; enable them only behind proper access controls. Never set `management.endpoints.web.exposure.include=*` in production just for a one-off investigation.

## 4. Thread Leaks: Symptoms, Sources, and How to Find Them

### 4.1 Common causes

- Every request calls `new Thread(...)` without any stop mechanism or `join()`.
- Every service call creates `Executors.newFixedThreadPool(...)` without calling `shutdown()`.
- A `ScheduledExecutorService` or timer is recreated across multiple refreshes/context restarts.
- A consumer or polling loop ignores the interrupt flag and keeps running after shutdown.
- A task blocks indefinitely on a socket/lock/queue and never exits.
- A library spawns background threads, yet the bean lifecycle never closes the library.
- A background thread retains a `contextClassLoader` or `ThreadLocal` pointing to an old deployment's classloader.

A **fixed-size thread pool** is not necessarily a leak. Stronger evidence is **the count of threads in the same group growing after each operation cycle**, or threads surviving after the owning component/context has closed.

### 4.2 Thread dumps

With a HotSpot JDK and appropriate attach permissions:

~~~bash
jcmd -l
jcmd <PID> Thread.print -l
~~~

`<PID>` is a placeholder for the real process ID. `Thread.print -l` prints thread lists, stack traces, and lock info; it can incur overhead and produce large output. Do not run tight dump loops automatically in production.

When reading a dump, inspect:

1. Which executor/scheduler prefix do thread names carry?
2. Are stacks stuck at `Thread.sleep`, `SocketInputStream`, `LockSupport.park`, `BlockingQueue.take`, or specific application code?
3. **Which pool** does the thread belong to, and does that pool have an owner/destroy callback?
4. How many threads of the same kind exist after the first, second, and third load cycles?
5. When `ApplicationContext` closes, does that group of threads disappear?

**Do not equate `WAITING` with "leaked."** A thread pool worker can legitimately wait for work. Confirming a deadlock or forgotten shutdown usually requires lifecycle context and stack evidence across multiple timestamps.

Supporting tools: Java Flight Recorder (JFR), Java Mission Control (JMC), VisualVM, IDE thread dumps, or a secured `/actuator/threaddump` if you intentionally enable it.

### 4.3 Wrong and right ways with executors

An anti-pattern:

~~~java
public void processRequest() {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    pool.submit(() -> doWork());
    // No shutdown; the pool and threads can outlive the request.
}
~~~

This is **faulty illustrative code** with incomplete functions/imports. If this runs on every request, it creates multiple executors whose lifetimes outlast requests.

Common fix: **one executor with a clear owner and lifecycle**:

~~~java
@Component
public class BackgroundWorker {

    private final ExecutorService pool =
            Executors.newFixedThreadPool(4);

    public Future<?> submit(Runnable task) {
        return pool.submit(task);
    }

    @PreDestroy
    public void shutdown() {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

This is an illustrative class requiring imports for `Component`, `jakarta.annotation.PreDestroy`, and the corresponding `java.util.concurrent` classes. In real applications, prefer a Spring-managed `ThreadPoolTaskExecutor`, which has clearer queue, pool, shutdown, and instrumentation configuration.

Distinguish **stopping task intake**, **completing running tasks**, and **reclaiming the executor**. Calling `shutdown()` alone does not turn every queued task into a completed result; deadlines and cancellation policies must be designed.

## 5. JDBC Connection Leaks: Look at the Pool, Not Just Sockets

### 5.1 How do pooled connections work?

In an application using `HikariDataSource`:

~~~text
HTTP request
     |
     v
dataSource.getConnection()  -> borrow a logical connection from Hikari pool
     |
     v
Execute SQL
     |
     v
connection.close()          -> return logical connection to pool
     |
     v
Hikari keeps physical connection idle for reuse if appropriate
~~~

With **pooled connections**, calling `Connection.close()` usually means **returning the connection to the pool**, not necessarily closing the physical TCP connection immediately. Therefore observing `idle connections > 0` is normal. Conversely, **`active` staying near `maximumPoolSize` and `pending` climbing persistently after load stops** is a sign to investigate.

Common causes:

- Code calls `getConnection()` and skips `close()` when an exception occurs.
- Queries or transactions hold connections too long.
- Streaming JDBC `ResultSet`s are not read/closed per contract.
- Async tasks hold a connection while waiting on unrelated work.
- Leaks in a library or custom `DataSource` wrapper.
- Request volume exceeds capacity, causing pool exhaustion **even with zero leaks**.

### 5.2 Hikari leakDetectionThreshold does not prove a leak

HikariCP has the property:

~~~properties
spring.datasource.hikari.leak-detection-threshold=2000
~~~

The unit is **milliseconds**. If a connection is borrowed beyond the threshold without being returned, Hikari logs a **possible/apparent connection leak** warning. The typical effective minimum threshold is 2000 ms; `0` disables the warning.

**This warning is a clue, not a verdict.** A legitimate 5-second transaction will also trigger the warning at the 2-second mark, and then return the connection when the transaction finishes. If Hikari later logs "previously reported leaked connection ... was returned to the pool," that is an exact example of a connection that **was returned**, not a permanent leak.

To investigate:

1. Enable a suitable threshold in the target environment, keeping noise under control.
2. Inspect the stack trace captured at checkout or when the warning fires.
3. Observe `hikaricp.connections.active`, `idle`, `pending`, and pool max over time.
4. Measure transaction/query durations and network wait times.
5. Verify code returns connections on **every path**, including errors, timeouts, and cancellations.
6. Run small repeated loads and check whether `active` returns to baseline.

Do not pick a threshold lower than normal processing times: you will flood logs with false positives, burying real incidents.

### 5.3 try-with-resources

Good JDBC code follows this pattern:

~~~java
String sql = "select count(*) from orders";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet results = statement.executeQuery()) {

    if (results.next()) {
        long total = results.getLong(1);
        // Use total...
    }
}
~~~

This is an illustrative snippet inside a class with `DataSource dataSource` and a corresponding `orders` table, not a standalone program. `try-with-resources` closes `ResultSet`, `PreparedStatement`, and `Connection` in reverse order when the block exits, even if an exception occurs.

If code uses Spring `JdbcTemplate`/Spring Data, let the framework manage connections and transactions via its API, avoiding manual `getConnection()` calls outside places genuinely requiring low-level JDBC. With `@Transactional`, a connection can be held until the transaction ends; **long-running transactions** still cause pool starvation even though the framework did not "forget to close."

## 6. File Descriptor, File Handle, and Socket Leaks

### 6.1 Symptoms

- `Too many open files` exceptions on Linux/Unix.
- Unable to open more files or sockets even though the heap is not full.
- Application cannot delete/rename files in some environments, especially Windows.
- File handle count climbs after every batch import/export.
- Many sockets stuck in unexpected states or I/O timeouts.

A descriptor can represent a **file, socket, pipe, eventfd, or other OS resource**, so an increase in `process.files.open` alone is not enough to conclude a CSV file was left unclosed.

### 6.2 Inspection tools

On Linux:

~~~bash
ls -l /proc/<PID>/fd
lsof -p <PID>
~~~

Replace `<PID>` with the real PID. `/proc/<PID>/fd` lists descriptors; `lsof -p` shows which files/sockets they point to, given the command and permissions. Count descriptors **multiple times under identical load** to filter out noise from log rotation, new sockets, JAR files, and JVM internals.

On Windows, you can use **Microsoft Sysinternals Process Explorer/Handle** or authorized handle-inspection tools to inspect handle counts and held objects. File opening/sharing semantics and locking behavior differ from Linux; do not apply Linux FD counts as a universal threshold across all platforms.

In Actuator, `process.files.open`/`process.files.max` metrics may depend on OS/JVM. If a metric is missing on Windows or inside a minimal container, that may be a signal-collection limitation rather than a handle count of 0.

### 6.3 Closing streams/channels properly

Recommended pattern:

~~~java
Path input = Path.of("data", "orders.csv");

try (BufferedReader reader =
             Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line.
    }
}
~~~

This is an illustrative Java snippet requiring imports for `Path`, `Files`, `BufferedReader`, `StandardCharsets`, and an existing `data/orders.csv` file. The file does not need to exist while reading this lesson.

Objects that may require closing: `InputStream`, `OutputStream`, `Reader`, `Writer`, `FileChannel`, `ZipFile`, `JarFile`, sockets/clients, result cursors. With `Files.lines(path)`, the returned `Stream<String>` must also be closed after traversal.

Anti-pattern:

~~~java
Stream<String> lines = Files.lines(path);
long total = lines.count();
// Never calls close() on the Stream.
~~~

Correct pattern:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long total = lines.count();
}
~~~

Both snippets are illustrative and require `Path path`, `Stream`, and appropriate imports. Never rely on finalizers or GC to close OS resources on time.

## 7. Classloader Leaks: Why Are They Different from Ordinary Heap Leaks?

### 7.1 What does a classloader own?

A `ClassLoader` loads classes and relates to class metadata, object instances, static fields, reflection caches, the thread context classloader (TCCL), and module/deployment resources. When a **short-lived** classloader (plugin, DevTools restart, application redeploy) should have been reclaimed, lingering references can retain it along with many associated classes/objects.

Example:

~~~text
An application-created thread (still alive)
           |
           v
Thread.contextClassLoader
           |
           v
OldRestartClassLoader
           |
           +-- classes from the old deployment
           +-- static fields / reflection metadata
           +-- still-reachable objects
~~~

An object reference can travel along many paths: threads, `ThreadLocal`s, static registries, callbacks/listeners registered in libraries on a parent classloader, executors, MBeans, driver registrations, or global caches.

It is not true that "every static field causes a classloader leak." Static fields belong to classes loaded by **a specific classloader** and matter if referenced from a GC root outliving the old loader. The problem arises when a **longer-lived** component holds a reference to a **shorter-lived** classloader or its objects.

### 7.2 DevTools and repeated restarts

Spring Boot DevTools restarts typically use **two classloaders**:

- **Base classloader:** holds rarely changing dependencies.
- **Restart classloader:** holds classes of the application under development; replaced on restart.

After a restart, the old restart classloader **should become eligible for GC** once unneeded references clear. If an old thread/plugin/cache retains its TCCL or callbacks from that loader, the old loader can remain alive, causing **Metaspace** and heap to grow across restarts.

Do not treat a single Metaspace increase after startup as a leak. Measure **across multiple similar restart/deploy cycles** and check whether the old loader stays reachable after appropriate GC.

### 7.3 Classloader diagnostic commands

On a HotSpot JDK supporting these commands:

~~~bash
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.classloaders
jcmd <PID> VM.metaspace
~~~

These commands report loader statistics/hierarchies or Metaspace usage; they are **aggregate evidence**, not the full retention reference chain.

You can also inspect via Actuator:

~~~bash
curl "http://localhost:8080/actuator/metrics/jvm.classes.loaded"
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=id:Metaspace"
~~~

These metrics help detect trends yet **do not pinpoint the specific loader** being retained. To find the root cause, analyze a controlled heap dump in Eclipse Memory Analyzer (MAT), VisualVM, or a supported tool, looking for **GC roots / paths to GC roots** leading to the old classloader.

**Caution:** heap dumps can be huge, pause the application depending on capture method, and contain secrets or personal data from the heap. Store them only in secure locations, enforce retention/deletion policies, and never expose `/actuator/heapdump` publicly.

### 7.4 Fixing TCCL and listener ownership

Code that changes the context classloader should restore the exact previous value:

~~~java
ClassLoader before =
        Thread.currentThread().getContextClassLoader();

try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Perform work using the plugin.
} finally {
    Thread.currentThread().setContextClassLoader(before);
}
~~~

This is an **illustrative** snippet in which `pluginLoader` is owned by the plugin system and already created. Always restore in `finally`; never leave a short-lived loader's TCCL parked on a shared thread.

If you use `URLClassLoader` or a module-loading library yourself, closing the loader per contract is only **one step**. `close()` releases resources managed by the loader yet **does not guarantee classes are unloaded** if threads/static caches/listeners still hold references.

When unloading a plugin, you must:

1. Stop the plugin's executors, schedulers, listeners, and tasks.
2. Register/unregister callbacks with lifecycle-matched owners.
3. Clear `ThreadLocal`s and restore TCCLs where needed.
4. Remove entries from global/static registries outliving the plugin.
5. Close connection pools, files, and `JarFile`/`URLClassLoader` if the plugin actually owns them.
6. Drop references to plugin objects/classes/classloader.
7. Verify the old loader disappears after GC and subsequent runs.

## 8. Runnable Spring Boot 3.3 Example: Holding Resources Briefly in a Controlled Way and Returning Them

This example intentionally **holds a JDBC connection and a file channel for a few seconds** while a task runs on an executor. It teaches how to observe all three resource groups **without creating a permanent leak**. After the request completes, the connection, file channel, and temp file are all returned/closed/deleted; the executor is a Spring-managed bean shut down when the context closes.

Classloader leaks require a separate **redeploy/restart** experiment in a later section; you should not try to permanently pin a classloader inside this web demo.

### 8.1 Structure and dependencies

~~~text
resource-diagnostics/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/resources/ResourceDiagnosticsApplication.java
        └── resources/application.properties
~~~

File `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'com.h2database:h2'
}

springBoot {
    mainClass = 'com.example.resources.ResourceDiagnosticsApplication'
}
~~~

**H2 in-memory** is chosen to observe HikariCP without an external database. In production, measure signals from both the real database and the client connection pool.

### 8.2 Configuration file

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=resource-diagnostics
server.port=8080

spring.datasource.url=jdbc:h2:mem:resource_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.pool-name=lab-pool
spring.datasource.hikari.maximum-pool-size=3
spring.datasource.hikari.minimum-idle=1
spring.datasource.hikari.connection-timeout=3000

# Enable low threshold only in lab; warning does not prove a real leak.
spring.datasource.hikari.leak-detection-threshold=2000

management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
~~~

Explanation:

- Hikari pool capped at 3 connections to make `active`, `idle`, and `pending` easy to observe.
- `leak-detection-threshold=2000` logs a **possible leak** warning when a request holds a connection longer than 2 seconds. Because the lab intentionally holds for 4 seconds, the warning is **expected even though the code closes properly**.
- `connection-timeout=3000` limits wait time to acquire a connection, not the maximum duration a transaction can hold one.
- Expose only `health`/`metrics` in the lab environment. The resource-holding `/lab/hold` endpoint must be removed or secured before going to production.

### 8.3 Complete Java file

Create `src/main/java/com/example/resources/ResourceDiagnosticsApplication.java`:

~~~java
package com.example.resources;

import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ResourceDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDiagnosticsApplication.class, args);
    }

    @Bean("labExecutor")
    ThreadPoolTaskExecutor labExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("lab-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    @RestController
    public static class LabController {

        private final DataSource dataSource;
        private final ThreadPoolTaskExecutor executor;

        public LabController(
                DataSource dataSource,
                @Qualifier("labExecutor")
                ThreadPoolTaskExecutor executor) {
            this.dataSource = dataSource;
            this.executor = executor;
        }

        @PostMapping("/lab/hold")
        public String hold(
                @RequestParam(defaultValue = "4000") long millis)
                throws Exception {

            if (millis < 0 || millis > 10000) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "millis must be between 0 and 10000");
            }

            // Temp file has a clear owner and is always deleted when done.
            Path temp = Files.createTempFile(
                    "spring-resource-lab-", ".txt");

            try {
                // Connection borrowed from Hikari; FileChannel holds an FD.
                try (Connection connection = dataSource.getConnection();
                     FileChannel channel = FileChannel.open(
                             temp, StandardOpenOption.WRITE)) {

                    channel.write(
                            StandardCharsets.UTF_8.encode("lab\n"));

                    // Worker thread owned by the executor bean.
                    Future<String> worker = executor.submit(() -> {
                        TimeUnit.MILLISECONDS.sleep(millis);
                        return Thread.currentThread().getName();
                    });

                    try {
                        String name = worker.get(
                                15, TimeUnit.SECONDS);
                        return "completed on " + name;
                    } finally {
                        if (!worker.isDone()) {
                            worker.cancel(true);
                        }
                    }
                }
                // Both resources in the try block are closed before the outer finally.
            } finally {
                Files.deleteIfExists(temp);
            }
        }
    }
}
~~~

**Why does this code not leak?**

- `Connection` is declared in `try-with-resources`; upon completion whether by success or exception, `close()` returns the connection to the Hikari pool.
- `FileChannel` is also closed automatically, after which the temp file is deleted in `finally`.
- `labExecutor` is a Spring-managed bean, not creating a new pool on every request. It has a clear lifecycle/shutdown.
- `Future` is awaited with a timeout; if unfinished, a cancel request is sent. The demo task only sleeps and honors interruption; production tasks must design timeouts/cancellation for real I/O.
- `@PostMapping` avoids using GET for creating files/holding resources in the lab.
- `millis` is bounded from 0 to 10,000 to avoid infinite requests in the example. Even so, the lab endpoint must not be exposed publicly.

**What the code does not promise:** requests may receive HTTP 500 if the executor/pool is overloaded or the file system errors, and no business transaction is run against H2. The goal is observing resource lifecycles, not designing a production endpoint.

### 8.4 Running and measuring

In a project with the Gradle wrapper and JDK 17+:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If you do not have a wrapper yet, generate/configure a compatible Gradle setup first. This is a Spring Boot application with dependencies, not a single Java file runnable via bare `javac` without a classpath.

In another terminal, run:

~~~bash
curl -X POST "http://localhost:8080/lab/hold?millis=4000"
~~~

The HTTP response body looks like:

~~~text
completed on lab-worker-1
~~~

**The thread name suffix may differ** across multiple requests; this is sample output, not a guaranteed string. The program may log a Hikari warning like "apparent connection leak" after 2 seconds because the connection is held for 4 seconds, followed by a message that the connection was returned to the pool.

While the request is still running, observe:

~~~bash
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/process.files.open
~~~

The result is JSON meter data with measurements and tags if the metric exists; **there is no fixed stdout** because it depends on sampling timing and concurrent requests.

Try a few consecutive requests and then stop. After work completes:

- `hikaricp.connections.active` normally drops back near 0, and connections can become idle.
- The Hikari pool may keep physical connections open by design.
- `lab-worker-*` threads may still exist because the thread pool retains workers for reuse; **do not conclude a leak** simply because threads do not vanish immediately.
- The temp file is deleted; FD count may fluctuate due to other sockets/logs, so compare against a load-matched baseline.
- When shutting down the application cleanly, Spring closes the executor bean and datasource per lifecycle.

**Important control experiment:** change `millis=1000` so it does not exceed 2000ms under normal conditions; no Hikari long-checkout warning appears. Keep `millis=4000` to trigger the warning while the connection is still returned. Lesson: time-threshold warnings **do not** prove a `close()` bug.

## 9. Controlled Leak Experiments and Fixes

Never intentionally create unbounded leaks in production. When reproducing a bug to understand it, work on a **lab machine**, bound the iteration count, and keep the ability to stop the process.

### 9.1 Threads

**Failure control:** in an isolated test, each iteration creates a `ScheduledExecutorService` without closing it. Observe thread names increasing alongside iteration count. Run only a small number of iterations and terminate the entire lab process afterward; never put this pattern into real code.

**Fix:** move the executor into an owning bean, call `shutdown/awaitTermination` in `@PreDestroy`, or use a Spring-managed `ThreadPoolTaskExecutor`.

**Post-fix proof:** thread counts belonging to the executor stabilize at the pool size, and those threads disappear after the context closes.

### 9.2 Connections

**Failure control:** create an isolated test path that intentionally omits returning `Connection` after `getConnection()`, capped to a few requests in a separated environment. Wait until `active=max` and `pending` rises, then stop the test. Never put this code into a public endpoint.

**Fix:** `try-with-resources` or letting Spring's data access/transaction framework manage connections properly.

**Post-fix proof:** `active` drops after requests/transactions end, with no upward accumulation across similar cycles.

### 9.3 File handles

**Failure control:** in an isolated test, open a few `FileInputStream`s and omit closing them, measuring FD counts. Avoid running to the point of exhausting FDs on a shared machine.

**Fix:** close streams/channels with `try-with-resources`, even on exceptions.

**Post-fix proof:** FD count pointing to the test files returns to baseline; do not look solely at total JVM FDs because the total has other fluctuating sources.

### 9.4 Classloaders

**Failure control:** in a DevTools/plugin test environment, load and unload a module several times; intentionally keep a reference to an object from the old loader inside a longer-lived registry, then inspect `VM.classloader_stats` or a heap dump.

**Fix:** unregister registries/listeners, stop threads, clear TCCL/`ThreadLocal`, close loaders, and drop references to the plugin.

**Post-fix proof:** the old loader is **no longer reachable** via GC root paths after appropriate unload/GC cycles. Seeing Metaspace drop alone does not prove every retention path was fixed, and conversely Metaspace not dropping immediately does not by itself prove a leak remains.

## 10. Observing Native Memory and Heap When Symptoms Are Unclear

Some bugs cannot be deduced from heap usage alone. The JVM uses multiple regions:

~~~text
Java process memory
 +-- Java heap
 +-- Metaspace / class metadata
 +-- Code cache
 +-- Thread stacks
 +-- Direct buffers
 +-- GC/JIT/native allocations
 +-- Memory managed by native libraries/OS
~~~

When container RSS grows while `jvm.memory.used` heap does not rise accordingly, **native memory, thread stacks, direct buffers, class metadata, or memory mappings** may be involved.

HotSpot JDK provides Native Memory Tracking (NMT). If you start the JVM with:

~~~text
-XX:NativeMemoryTracking=summary
~~~

then you can run:

~~~bash
jcmd <PID> VM.native_memory summary
~~~

NMT must be enabled at JVM startup with the right flag. It carries overhead and mainly analyzes **JVM-tracked memory**, without guaranteeing coverage of every third-party native library allocation. Pair it with OS-level RSS, thread, FD, and pool metrics.

If heap analysis is needed:

~~~bash
jcmd <PID> GC.class_histogram
~~~

This command can be expensive and cause notable pauses depending on heap size; use only when permitted. It shows class/object counts in the heap, yet does not itself show **retention paths**. When suspecting a classloader leak, a heap dump and dominator/GC-root analysis are usually far more informative than a standalone histogram.

Java Flight Recorder can collect time-based evidence:

~~~bash
jcmd <PID> JFR.start name=resource-lab settings=profile duration=60s filename=resource-lab.jfr
~~~

This is an example command for HotSpot/JDK supporting JFR. Check permissions, filesystem space, recording settings, and overhead before running. Recording files can contain sensitive data and must be stored under controls similar to heap dumps.

## 11. Leaks at the Spring ApplicationContext Boundary

Spring manages the lifecycle of **registered beans**, yet a resource you create manually outside the container can bypass destruction mechanisms:

~~~java
class ExternalClientHolder {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    // If this object is created with new outside Spring and never closed,
    // Spring does not automatically know to shut down the executor.
}
~~~

This is a compact example illustrating an ownership bug, not a standalone program.

Key principles:

- Every resource must have a **concrete owner**.
- If the owner is a Spring bean, register `@PreDestroy`, `DisposableBean`, or `@Bean(destroyMethod=...)` as appropriate.
- If the owner is a method, use `try-with-resources`.
- If the owner is a job/stream, ensure close on completion, error, and cancellation.
- If the owner is an `ApplicationContext`, stop child components **before** the shared dependencies they use.
- If a resource belongs to a library, use the library's `close()/shutdown()` API rather than merely clearing Java references.
- When running **multiple `ApplicationContext`s in one JVM**, close every created context; closing only the final context does not guarantee another context's resources are handled properly.

### @PreDestroy and shutdown are not enough if tasks do not cooperate

Even with:

~~~java
@PreDestroy
public void shutdown() {
    executor.shutdownNow();
}
~~~

this snippet still only issues a stop request. If a task ignores interruption or blocks on an API without timeouts, it can remain alive. You need I/O timeouts, cancellation contracts, graceful shutdown, and verification that threads actually exited.

Never use `System.exit(...)` as a normal workaround for a leaking component: it kills the whole JVM, hides the ownership bug, and prevents controlled resource closing.

## 12. Real-World Troubleshooting Workflow

Suppose production reports gradually increasing timeouts after a few hours. An effective workflow:

**Step 1 — Isolate the symptom.** When did the error rate start rising? Did CPU, heap, GC, thread count, FDs, or pending pool connections change? Was there a recent deploy or config change?

**Step 2 — Identify the resource type.** If `hikaricp.connections.pending` climbs, inspect the JDBC pool and transactions. If `process.files.open` climbs, inspect descriptors. If threads named `custom-worker-*` multiply, inspect the executor owner. If Metaspace/classloaders climb after each redeploy, focus on loader retention.

**Step 3 — Sample over time.** Measure at minimum before load, under load, after settling idle, and across several similar load cycles. A snapshot during peak load alone does not prove a leak.

**Step 4 — Gather concrete evidence.** Thread dumps/JFR, Hikari checkout stacks, `lsof`/Handle, classloader stats/heap dumps. Use only tools authorized in that environment.

**Step 5 — Find the missing owner.** Search for calls to `new Thread`, `Executors.new...`, `DataSource.getConnection`, `Files.new...`, `URLClassLoader`, listener registrations, or `ThreadLocal`. Compare against where closing/unregistering must occur.

**Step 6 — Fix the root cause and write regression tests.** Every success, exception, timeout, cancellation, and context-close branch needs a cleanup policy.

**Step 7 — Verify after the fix.** Run the same scenario at the same load and re-measure. Only declare the leak fixed when resources reach a steady baseline/plateau and stop accumulating across cycles.

**Step 8 — Set meaningful alerts.** Do not alert solely on absolute total threads/FDs. Prefer growth rates, pool pending thresholds, error rates, timeouts, active/max ratios, and user impact.

## 13. Practical Checklist by Resource Type

| Type | Initial Evidence | Deeper Tooling | Common Fix |
|---|---|---|---|
| Thread | `jvm.threads.live`, executor active/queue, thread prefix | Thread dump/JFR, lifecycle logs | Shut down executor/scheduler, cancel tasks, add I/O timeouts. |
| JDBC connection | Hikari active/idle/pending/max, timeouts | `LeakDetectionThreshold` + stack, transaction traces | `try-with-resources`, shorten transactions, enforce proper owner. |
| File descriptor | `process.files.open`, "too many open files" | `/proc/PID/fd`, `lsof`, Process Explorer/Handle | Close streams/channels/sockets, manage client lifecycle. |
| Classloader | Class count, Metaspace, loader count after reload | `VM.classloader_stats`, heap dump, paths to GC roots | Stop threads, unregister registries/listeners, clear TCCL/`ThreadLocal` and loader references. |

Do not use one tool as a substitute for everything else. For example, **a heap dump can help find objects holding `FileInputStream`**, yet the OS confirms which file descriptors remain open; **a Hikari warning helps find the call stack**, yet pool metrics and checkout history evaluate whether connections are actually going unreturned.

## 14. Common Misconceptions

**Misconception 1 — "If heap isn't growing, there can't be a leak."** False. Thread stacks, native memory, socket/file descriptors, and connections can run out before heap grows much.

**Misconception 2 — "A thread in `WAITING` state is leaked."** False. A worker waiting for tasks can be normal. Check owner, count, lifecycle, and shutdown behavior.

**Misconception 3 — "Hikari idle connections are connection leaks."** False. Idle connections are already returned to the pool and ready for reuse per configuration.

**Misconception 4 — "Hikari `leakDetectionThreshold` logging means `close` was definitely forgotten."** No. It warns on long checkouts; a valid slow query/transaction can also exceed the threshold.

**Misconception 5 — "`Connection.close()` always closes the physical TCP socket."** Not necessarily with a pool; it usually returns the logical connection to the pool.

**Misconception 6 — "GC will close files or sockets in time."** You cannot rely on that. Close them explicitly per contract.

**Misconception 7 — "Metaspace growing means a classloader leak."** Insufficient. Classloading/caching can be legitimate; prove the old loader cannot be GC'd due to retaining references.

**Misconception 8 — "`URLClassLoader.close()` alone guarantees class unloading."** No. References from threads/static registries can still pin the loader and class metadata.

**Misconception 9 — "Enabling Spring DevTools restart makes all resources from the old run vanish automatically."** Not guaranteed, especially for unmanaged resources, TCCL, and listeners/`ThreadLocal`s outliving the context.

**Misconception 10 — "Increasing `maximumPoolSize` fixes leaks."** It may only let the system last longer before exhausting; if code forgets to return connections, even a huge pool eventually runs dry.

**Misconception 11 — "Just calling `shutdownNow()` definitely stops every thread."** No. Tasks must cooperate with interruption and timeouts; unresponsive I/O can still hold resources.

**Misconception 12 — "Expose all Actuator endpoints to make debugging easy."** Serious security risk. Expose only needed endpoints over protected paths and control diagnostic data.

## 15. Verification Lab Exercises

1. **Run the lab app** in Section 8 and measure `hikaricp.connections.active` before/during/after a `millis=4000` request.
2. **Explain the Hikari warning** at the 2000ms threshold: why can a 4-second request emit a warning even when the connection is returned properly?
3. **Observe the executor** via `jvm.threads.live` and `lab-worker-*` thread names after several requests. Why do surviving workers not prove a leak by themselves?
4. **Inspect descriptors** using `/proc/<PID>/fd` or `lsof` while a request holds `FileChannel`. Why can the total fluctuate due to sockets or loggers?
5. **Increase concurrent requests within limits** to hit Hikari pool max=3. Observe active/pending/timeouts and distinguish saturation from leaks.
6. **Shut down the app cleanly**; verify the executor and Hikari pool close and the process is not kept alive by unmanaged threads.
7. **Write controlled regression tests** for exception/timeout branches of file and JDBC operations. Verify `finally`/`try-with-resources` still returns resources.
8. **Try DevTools restarts in an isolated environment** and run `VM.classloader_stats`; do not infer a leak from a single class-count bump.
9. **Analyze an authorized heap dump** with MAT, locating an old classloader and paths from GC roots; store diagnostic files per security policy.
10. **Re-run after fixing** with the same load and observation window; record evidence that resource usage settles onto a stable plateau.

### Official Documentation

- Spring Boot 3.3 — Actuator Metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot — Actuator Endpoints and exposure security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Developer Tools, restart vs reload and two classloaders: https://docs.spring.io/spring-boot/reference/using/devtools.html
- Oracle JDK 21 — `jcmd` diagnostic commands: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — Diagnostic Tools/JFR: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- HikariCP — Configuration, `leakDetectionThreshold`: https://github.com/brettwooldridge/HikariCP/wiki/Configuration

**Takeaway:** detecting leaks is not about finding a large number, but proving that **resources fail to return to their proper lifecycle**. With Spring Boot, combine Actuator metrics, thread dumps/JFR, Hikari statistics, file-handle inspection, and classloader/heap analysis. Every resource needs an owner, a close/shutdown/unregister path on both success and failure branches, and a controlled experiment confirming the resource is released once work ends.
