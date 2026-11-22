# Safely Closing Appenders in Java Logging

## Lesson Objectives

In a Java application, a logger call returning **does not mean** every log byte has been written, sent, or durably stored. An appender may hold a stream, file lock, queue, worker thread, or network connection. If the process terminates without a proper shutdown sequence, you may encounter missing trailing logs, unclosed files, lingering worker threads, or lost critical diagnostic information.

This lesson belongs to the **Appenders and Handlers** group of **Java Core Logging**, focusing on **safely closing appenders**. After this lesson, you will be able to:

- Explain **start/stop**, **flush/close**, and the lifecycle management responsibilities of appenders/handlers.
- Choose the correct sequence: **stop accepting work → wait for in-flight tasks → emit final logs → stop logging context → exit process**.
- Use **LoggerContext.stop()** in Logback, and understand when the backend/framework should be the lifecycle owner.
- Evaluate the limits of **AsyncAppender**, queues, `discardingThreshold`, `neverBlock`, and `maxFlushTime` during shutdown.
- Run a **Java 17 + Logback** example that writes to a file, stops the context, and reads the data back; compare it with **java.util.logging.Handler.close()** through a standalone JDK example.
- Identify scenarios where zero log loss cannot be guaranteed: forced kills, crashes, network disconnections, queue overload, or missing acknowledgments from the storage system.

## 1. Why Must Appenders Be Closed?

A typical logging pipeline:

~~~mermaid
flowchart LR
    A["Java Code / Logger"] --> B["Level, Filter"]
    B --> C["Appender"]
    C --> D["Encoder / Layout"]
    D --> E["File, console, network"]
~~~

With asynchronous logging, there is an additional queue and worker thread:

~~~mermaid
flowchart LR
    A["Logger"] --> B["AsyncAppender: queue"]
    B --> C["Worker thread"]
    C --> D["FileAppender / Network appender"]
    D --> E["Destination"]
~~~

Depending on the implementation, an Appender may own:

- **OutputStream/file descriptor** and I/O buffers.
- **Lock file**, active target file name, and rotation/rolling state.
- **Encoder** with initialization, header/footer, and charset mechanisms.
- **Queue** receiving logging events and a **worker thread** forwarding records to the destination.
- **Network connections**, batch requests, or post-rotation file compression tasks.
- **Auxiliary resources** that must be released according to the lifecycle.

When the JVM stops abruptly, those resources do not always finish their work. For **safe closing**, you should not only ask "was stop called?", but also "**are any producers still generating events, are there any records left in the queue, were there errors closing the destination, and has the collection system received them?**".

**Important limitation:** closing appenders in the right sequence reduces the risk of log loss and releases resources, but **does not guarantee** that logs have been fsynced to the storage device, accepted by a collector, or achieved database-transaction-level durability.

## 2. Distinguishing stop, close, flush, shutdown, and durability

| Term | Core Meaning | What Not to Infer |
| --- | --- | --- |
| **Appender.start()** | Activates the appender after configuration | Does not prove the destination can always receive logs |
| **Appender.stop()** | Stops the appender and releases resources managed by the implementation | No general guarantee that all records have been durably stored |
| **Handler.flush()** (JUL) | Pushes buffered data to the handler's target stream | Does not mean the file has been synced to disk |
| **Handler.close()** (JUL) | Flushes then closes the handler and releases resources | The handler should not be used again after close |
| **LoggerContext.stop()** (Logback) | Stops the logging context, associated appenders, and context tasks | Does not replace stopping business producers or external services |
| **Async queue drain** | Worker consumes remaining queued events | Can be limited by timeout, sink errors, or drop policies |
| **Graceful process shutdown** | Stops work and releases resources in order | Not every step runs when killed forcibly |
| **Durable delivery** | The final destination has confirmed storage under its own contract | Cannot be inferred solely from `logger.info(...)` returning |

In **Logback**, an Appender belongs to a lifecycle with start/stop operations and a started state. Do not casually assume Java `Closeable`/`AutoCloseable` semantics or that any Appender can be placed in a try-with-resources block. The standard mechanism to use is **stop()**, or letting **LoggerContext.stop()** manage the appenders within the same context.

In **java.util.logging (JUL)**, the corresponding component is **Handler**. The Handler API has **flush()** and **close()**; per Java SE 17, `close` performs a flush and releases resources, after which the handler **should not be used further**. Because JUL `Handler` is not the same kind of API as Logback `Appender`, do not use their method names interchangeably.

## 3. Safe Shutdown Sequence

An intentional application shutdown flow should follow this order:

~~~text
1. Receive stop request: SIGTERM, lifecycle event, or administrative action.
2. Stop accepting new requests/jobs.
3. Wait for or cancel in-flight work in a controlled manner, with a reasonable deadline.
4. Emit necessary final log records, including results of completed jobs.
5. Stop the logging context / async appender to drain the queue and close output destinations.
6. Verify results within observable scope, then let the process exit.
~~~

**Why step 4 must happen before step 5:** if you call `logger.info("server.stopped")` after stopping the appender, the record may be dropped or only trigger an internal warning. The log statement still executes in code, but there is no longer a valid destination to write to.

**Why steps 2–3 must precede step 5:** if in-flight requests continue emitting logs while the appender is being closed, those records may be lost. Stopping logging before stopping executors or HTTP servers is a common shutdown ordering bug.

This is the **logical** order. Detailed implementation depends on the server/framework: Spring, Jakarta Servlet, worker consumers, command-line applications, schedulers, or container environments have different shutdown callbacks and deadlines. You should clearly designate the **owner of calling stop**, avoiding two components arbitrarily closing the same context while the application is still logging.

## 4. Logback: Who Is Responsible for Closing Appenders?

Logback Classic has **LoggerContext**, which holds loggers and their associated appender configurations. In an application that genuinely uses Logback as its SLF4J provider, you can obtain the context and stop it:

~~~java
// Illustrative snippet: only appropriate when the backend is actually Logback Classic.
ch.qos.logback.classic.LoggerContext context =
        (ch.qos.logback.classic.LoggerContext)
                org.slf4j.LoggerFactory.getILoggerFactory();
context.stop();
~~~

The Logback documentation recommends stopping the context to release resources. This closes the appenders attached to loggers belonging to the context and stops active threads of the logging system according to Logback's mechanism.

**This snippet is not backend-agnostic:** `LoggerFactory.getILoggerFactory()` may return a different implementation if the provider is `slf4j-simple` or a Log4j 2 adapter. In that case, casting to `LoggerContext` is wrong. The SLF4J facade **does not provide a method to close all backends under a single common contract**. Shutdown is the responsibility of the backend or the framework that owns it.

**Do not arbitrarily close shared appenders.** If multiple loggers send to the `FILE` appender, one module should not call `FILE.stop()` just because its own work is done; doing so can cause other modules to lose their output destination. For an application that owns the entire context, stopping the context during application-wide shutdown is usually easier to control than manually closing individual appenders.

### When to Stop an Individual Appender?

You may stop an appender individually when **you directly create and manage it**, are certain no producers are still using it, and are changing configuration or shutting down a component with an isolated lifecycle. The procedure should include detaching it from loggers or blocking new producers, ensuring there are no races, and then stopping it. Do not stop a shared appender just because you want to delete old logs.

### When Should Business Code Not Call stop Manually?

In many application servers or frameworks, the logging lifecycle is already managed by the container/framework. In those cases, avoid having every service call `LoggerContext.stop()`. Instead, use the **application owner's** lifecycle/shutdown callbacks (or an appropriate shutdown hook) to perform an ordered shutdown, and check whether the framework automatically closes Logback upon stopping.

## 5. Practice with Java 17 + Logback: Write to File Then Stop Context

This example runs standalone via Maven with **Logback Classic 1.5.18**. The program emits two events, calls `LoggerContext.stop()` in `finally`, then reads the file to verify the results and checks that the context has stopped. The file is placed under the project's **target** directory.

The goal is to demonstrate **the right sequence in a small application with a single logging thread**, not to prove that distributed applications always deliver logs exactly once.

### Project Structure

~~~text
safe-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── SafeAppenderDemo.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>safe-appender-demo</artifactId>
  <version>1.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Versions are pinned for lesson reproducibility**, not as a claim about the latest release. The `logback-classic` dependency brings in Logback components and the compatible SLF4J API. A real project should manage versions via a BOM/`dependencyManagement` and your organization's security policy.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>target/shutdown-demo.log</file>
    <append>false</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
~~~

- **FILE** is an appender that writes to a file, not a `ConsoleAppender`. The demo's logs are not printed to the terminal automatically.
- **append=false** is only meant to create a clean new file for each practice run. In production, do not accidentally use this mode on log paths that must be preserved across restarts; consider appropriate append/rolling/retention settings.
- **PatternLayoutEncoder** outputs records as UTF-8 text. The pattern prints the level, message, and newline character.
- **root INFO** permits the two INFO events. No other loggers are attached to appenders in the sample configuration.

### File src/main/java/com/example/logging/SafeAppenderDemo.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SafeAppenderDemo {
    public static void main(String[] args) throws Exception {
        Path logFile = Path.of("target", "shutdown-demo.log");
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        Logger logger = LoggerFactory.getLogger(SafeAppenderDemo.class);
        try {
            logger.info("event=job.started id={}", "job-7");
            logger.info("event=job.finished id={} result={}", "job-7", "ok");
        } finally {
            context.stop();
        }

        List<String> lines = Files.readAllLines(logFile, StandardCharsets.UTF_8);
        System.out.println("recordCount=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
        System.out.println("contextStarted=" + context.isStarted());
    }
}
~~~

### Compile and Run

From the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.SafeAppenderDemo"
~~~

The Exec Plugin launches **a child JVM** with the project's classpath. This avoids confusion with Maven's own logging environment when running the example in the same JVM. Files are generated under `target`; Maven needs the dependencies already downloaded or access to an appropriate Maven repository.

**Exact stdout of the program** with the configuration above, excluding lines from Maven or the environment:

~~~text
recordCount=2
INFO | event=job.started id=job-7
INFO | event=job.finished id=job-7 result=ok
contextStarted=false
~~~

This output has been tested with the JDK and Maven on the corresponding program.

### Reading the Results Properly

1. **LoggerFactory** returns `LoggerContext` because the runtime uses Logback Classic. This is an implementation-dependent cast, intentional in a Logback learning example.
2. **The two `logger.info` calls** are emitted while the context is active. `FILE` is the appender that receives the events and writes the corresponding text.
3. **finally** calls `context.stop()` even if the code in `try` throws an exception. This releases the logging context's resources once execution reaches the `finally` block.
4. **Files.readAllLines** is executed **after stop** to observe the file contents from a closed logging state, rather than reading while the appender is still writing.
5. **recordCount=2** is the result for this specific demo data. Do not use this result to claim that all async backends/destinations never lose records.
6. **contextStarted=false** shows that the context was stopped at the time of inspection. This is not proof that the file was fsynced to durable storage.
7. **System.out.println** is used to report the demo output after logging has stopped. In a real application, do not continue emitting business logs through a Logger that has already been stopped.

Because the example is single-threaded, no tasks continue producing records when `context.stop()` runs. In a real service, **you must control still-running threads/requests/jobs before stopping Logback**.

## 6. AsyncAppender: Risk of Log Loss During Shutdown

Logback Classic's **AsyncAppender** places a queue between application threads and the target appender. Application threads can submit events faster than the file/network destination can write; AsyncAppender's worker takes events out and forwards them to the child appender.

Consequence: after calling `logger.info(...)`, **the event may still only be in the queue**, not yet written to the file. If the process exits before the worker finishes processing, the trailing events may be lost.

The Logback documentation states clearly: when stopping/redeploying, **AsyncAppender must be stopped**, typically via `LoggerContext.stop()`. During stop, `AsyncAppender` waits for its worker to drain the queue up to the **maxFlushTime** parameter. If the deadline expires, remaining events may be discarded. Setting `maxFlushTime` to **0** means waiting for the worker to finish without a time limit under that setting; however, it can hang shutdown if the destination is stuck, and it is not a delivery/durability guarantee.

### Example AsyncAppender Configuration

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>target/async-demo.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%d{HH:mm:ss.SSS} %-5level %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>512</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>5000</maxFlushTime>
    <appender-ref ref="FILE"/>
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

**This is an alternative illustrative configuration**; do not paste this entire block into the `logback.xml` from section 5 because there would be two `root` elements. The program in section 5 can still use `LoggerContext.stop()`, but the output with this configuration will be **different** due to timestamps, file name, and `append=true`; do not compare against section 5's output after changing the config.

Meaning of the parameters:

| Property | Meaning | When Evaluating Shutdown |
| --- | --- | --- |
| **queueSize=512** | Limits the number of events waiting in the queue | A large queue absorbs bursts but requires time and memory to drain |
| **discardingThreshold=0** | Disables the mechanism that drops low-priority records when the queue is nearly full | Does not solve event loss caused by crashes or timeouts |
| **neverBlock=false** | When the queue is full, the logging path may wait for space instead of dropping immediately under `neverBlock` mode | Can create backpressure on application threads |
| **maxFlushTime=5000** | Waits up to 5,000 ms when stopping the worker to process the queue | Unprocessed events when the deadline expires may be discarded |
| **appender-ref FILE** | Destination receiving events from the worker | If `FileAppender` fails, draining the queue still does not guarantee proper storage |

In Logback, `AsyncAppender` **by default may drop TRACE/DEBUG/INFO when the queue is nearly full** (a threshold related to 80% capacity). If important information must be kept, you must understand **discardingThreshold** and congestion policies; do not just increase `maxFlushTime` and assume all events were preserved beforehand.

**A zero-loss configuration** is a very different goal from "safely closing appenders." When the queue is full, the network fails, or the JVM is killed, an appender can lose records even though the code called the logger properly. Data that must never be lost requires a dedicated **durable recording system**, not just a logging queue.

### Why Not Arbitrarily Set maxFlushTime=0?

Setting 0 can be appropriate if you control the sink, have bounded latency, and prioritize waiting for the queue to drain. However, if the sink hangs, the worker can hardly finish and the process may fail to exit on time. In containers, the orchestrator's shutdown grace period is usually bounded; once it expires, the process may be forcibly terminated.

Therefore, you must **balance** the volume of events to drain, allowed wait time, sink write capacity, and operational policy. You can set a finite timeout, measure actual drain times, monitor shutdowns where events are dropped, and tune the configuration based on specific risks.

## 7. Shutdown Hooks: Useful, Not Absolute Insurance

Logback supports a shutdown hook in its configuration to stop the context when the JVM begins a normal shutdown. For example:

~~~xml
<configuration>
  <shutdownHook/>
  <!-- Configure appenders, encoders, and loggers as usual. -->
</configuration>
~~~

The snippet above only illustrates **how to declare the hook**; it must be placed inside a complete Logback configuration file, not used in place of the entire `root`/`appender` setup. Hook class names and mechanisms may vary across versions; check the documentation for the version you deploy.

A shutdown hook is useful in a **standalone Java app** when there is no framework managing the lifecycle. In a server/webapp, it is better to choose a lifecycle-appropriate shutdown mechanism and clearly define who is responsible for stopping the context.

Limitations:
- **SIGKILL**, severe process crashes, or power loss do not guarantee the shutdown hook will run.
- A shutdown hook can run **concurrently** with other hooks. If another hook still logs, arbitrary ordering can cause trailing logs to be lost.
- A hook does not by itself guarantee that producers have stopped or that an external system has received every byte.
- A shutdown hook used for logging cleanup should not itself emit a complex chain of logs after appenders have been closed.

**Rule of thumb:** prefer ordered shutdown within the application lifecycle, use a hook as a supporting mechanism when appropriate, and test application shutdown under realistic load.

## 8. Comparing with java.util.logging.Handler.close()

In JUL, the component that receives and outputs records is typically called a **Handler**, not a Logback Appender. JUL provides **flush()** and **close()** in the `Handler` API. Per Java SE 17, `Handler.close` flushes, then closes and releases resources, and **the Handler should not be used after it has been closed**.

For a handler **created and owned by your code**, the safe pattern is:

~~~java
// Illustration: the logger and handler are managed by this code.
logger.addHandler(handler);
try {
    logger.info("event=job.finished");
} finally {
    logger.removeHandler(handler);
    handler.close();
}
~~~

This pattern does not mean every handler in an application should be closed at the end of every request. If a handler is shared across the entire service, close it at the **service shutdown lifecycle**. Do not close the JVM-wide root `ConsoleHandler` in the middle of execution while other modules are still logging.

### Complete Java 17 Program Using JUL FileHandler

The following program uses only the JDK, creates a temporary file, writes a record, removes the handler from the logger, closes the handler, and then reads back and deletes the file.

Create **JulHandlerCloseDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulHandlerCloseDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jul-close-", ".log");
        Logger logger = Logger.getLogger("demo.jul.close");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(path.toString(), false);
        handler.setEncoding("UTF-8");
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        try {
            logger.info("event=job.finished id=job-7");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        System.out.println("recordCount=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
        Files.deleteIfExists(path);
    }
}
~~~

Run:

~~~bash
javac JulHandlerCloseDemo.java
java JulHandlerCloseDemo
~~~

**Exact stdout**:

~~~text
recordCount=1
INFO | event=job.finished id=job-7
~~~

This example has been tested on the JDK. Closing releases the `FileHandler`'s stream/lock before deleting the file, which is especially important on operating systems that lock open files. `FileHandler` has a different default formatter than the demo's custom formatter, so this output only applies to the code configuration shown.

**Do not infer that JUL `Handler.close()` is equivalent to `LoggerContext.stop()`.** One method closes **a single handler** you own; the other manages **an entire logging context** and its associated Logback appenders. If your code uses SLF4J with a Logback backend, closing a JUL `Handler` does not stop Logback appenders.

## 9. FileAppender, RollingFileAppender, and Associated Resources

For **FileAppender**, shutdown checks include file descriptors, file locks, buffered data, charset/encoder, and write permissions. For **RollingFileAppender**, there are also rotation policies, archive files, and post-processing tasks such as file compression; these auxiliary tasks may need time to finish.

**Stopping the context** is usually the right choice when the application owns the entire context, rather than hunting down individual appenders to close manually. However, do not claim that all external dependent tasks have completed without a corresponding confirmation signal.

Common file-related mistakes:
- **Not calling stop before exit** leaves files open longer than expected or loses trailing records in buffered/async configurations.
- **Changing the file path while the appender is active** is not equivalent to a safe close/reopen; you must follow the backend's lifecycle/reconfiguration mechanism.
- **Closing an appender shared across multiple loggers** causes other loggers to lose output.
- **Using `append=false` in production** can wipe out previous log data on every startup; only use it when you intentionally want to overwrite content like in a demo.
- **Not checking disk space/permissions** can lead to logging errors even with a proper shutdown sequence.
- **Assuming console output is always durably stored** is wrong: stdout/stderr typically pass through the runtime/container/collector with its own policies.

When collecting logs via a sidecar or agent, you must also consider the shutdown order between the **log-producing application** and the **log-receiving collector**. If the collector stops before the application finishes flushing, trailing logs may not reach central storage.

## 10. Reconfiguration and Redeployment

In long-running systems, logging configuration may be changed while the app is running, or the application may be redeployed. This is where "safe appender closing" bugs can arise even though the process does not fully shut down.

Things to check:
1. **Who is authorized to reconfigure the logger context?** Avoid two components concurrently adding/removing appenders without coordination.
2. **Which producers are running?** Do not stop an appender receiving events from other threads without a safe transition mechanism.
3. **Is the old appender stopped properly?** Creating a new file/appender without stopping the old instance can leak file descriptors and threads.
4. **Has the new appender started validly?** If the sink fails to open, switching from the old appender to the new one can cause all logs to be lost.
5. **Where do logs go during the transition?** Understand the implementation's behavior during reconfiguration; do not assume zero dropped events.
6. **Is a file shared between two contexts/processes?** Multiple processes contending for the same file/rotation should not be considered safe merely because each appender calls stop.

Logback has its own reconfiguration mechanisms. This lesson does not recommend arbitrarily calling `reset()`/`stop()`/`start()` on a production context: configuration changes should be coordinated with the application lifecycle and tested under appropriate load.

## 11. Graceful Shutdown in Servers, Job Runners, and Containers

### HTTP Server

A server typically needs to **stop accepting new requests** and let in-flight requests complete within an allowed timeframe. Once no business jobs remain, it emits summary logs and stops the logging system.

If you call `LoggerContext.stop()` inside a request handler, concurrent requests still running may lose logs; therefore, stopping the context must belong to the **application-wide** shutdown callback or the corresponding logging owner.

### Executor or Background Worker

For a thread pool, shutdown can follow these steps:
1. Stop submitting new tasks.
2. Call `executor.shutdown()` to stop accepting new tasks.
3. Wait for running tasks using `awaitTermination` with a controlled timeout.
4. If the deadline expires, apply the cancel/force-shutdown policy and log the outcome **before stopping logging**.
5. Stop `LoggerContext` after workers no longer need to emit logs.

Operation pattern:

~~~java
// Illustration; the executor and logger are created/managed elsewhere.
executor.shutdown();
if (!executor.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
    logger.warn("event=workers.shutdown_timeout");
    executor.shutdownNow();
}
// Only stop logging after the workers that still emit logs have been handled/controlled.
~~~

**Warning:** calling `shutdownNow()` sends an interrupt request rather than guaranteeing every task has stopped immediately. If a task ignores interrupts, it can still emit events afterward. You need a complete wait/cancellation policy instead of treating `shutdownNow` as a completion barrier.

### Container/Orchestrator

A container may receive a stop signal and only be granted a limited window to terminate. You must allocate time for **draining requests, closing dependencies, draining async queues, and closing logging**. If `maxFlushTime` is too large while the grace period is too short, the process may be killed before `stop` finishes.

Conversely, setting `maxFlushTime` too small can cause many queued records to be discarded during shutdown. Measure sink throughput and test under appropriate worst-case load, rather than using a quiet local run as your only benchmark.

## 12. Proper Closing Still Does Not Guarantee Saving Every Log

Distinguish the guarantee layers:

~~~text
logger.info(...) is called
    ↓
Level/filter accepts the record
    ↓
Appender/AsyncAppender receives the record
    ↓
Queue drains and encoder generates bytes
    ↓
OutputStream/OS receives bytes
    ↓
File is flushed / network sends data
    ↓
Collector receives data
    ↓
Backend stores/indexes and makes queryable
~~~

Each arrow can be affected by errors, timeouts, filters, sampling, queues, or receiving-system policies. **Calling stop safely only addresses part of the lifecycle on the current producer/backend side.**

Situations with no zero-loss guarantee:
- JVM crash, `SIGKILL`, power loss, or severe out-of-memory errors.
- `AsyncAppender` queue already dropped records when full or prioritized dropping low log levels.
- Worker did not finish draining the queue before `maxFlushTime`.
- File/disk ran out of space, permissions changed, or backend failed.
- Network collector disconnected, lost acknowledgments, or received data without durable persistence.
- Logger/Handler/Filter blocked the record from passing through in the first place.
- File rotation or retention moved/removed older records from the location being queried.

For data that must be stored under a business contract (e.g., transaction confirmations, regulatory audit trails), do not use diagnostic logs as the sole source of truth. Use durable storage/transactions/outbox patterns or a dedicated audit service depending on the required guarantee level.

## 13. Shutdown Testing and Acceptance Criteria

The practice in section 5 demonstrates a **synchronous FileAppender** case where two records are written properly, the context is stopped, and the file can be read back. That is a baseline test; real systems need additional load and failure scenarios.

A suggested QA plan:

| Scenario | How to Test | What to Evaluate |
| --- | --- | --- |
| Normal shutdown | Put server in stopping state, drain requests, then stop context | Final logs appear before stop; no logger is used after stop |
| Shutdown under load | Multiple requests/threads logging concurrently | Producers actually stop before the logging context closes |
| Async queue nearly full | Generate traffic exceeding sink speed in a controlled way | Drops, blocking, time-to-drain, and pending state |
| Slow sink | Simulate slow file/network I/O | Whether `maxFlushTime` and grace period are appropriate |
| No write permission | Create an environment lacking temp file permissions | Whether backend reports errors/`StatusManager` appropriately and how the app reacts |
| Forced runtime stop | Simulate forced kill in a test environment | Document limits; do not advertise zero-loss guarantees |
| Redeploy or config change | Start new appender, stop old one per lifecycle | No thread/descriptor leaks, no duplicate writes |
| JUL Handler close | Write file, close, then read/delete file | No lingering locks, no writes on closed handler |

**Count records in the right unit.** A `Throwable` can produce many stack trace lines in a text log; do not count each line as a separate event. For async logging, compare the number of events **accepted by the backend** against events at the destination when appropriate tracking exists; do not just count logger calls if some were filtered out by level/filter.

**Do not test by intentionally corrupting production data.** Use temporary files, synthetic data, test environments, and bounded record counts/time windows when testing shutdown impact.

## 14. Common Mistakes

| Mistake | Why It Is Dangerous | Appropriate Approach |
| --- | --- | --- |
| Calling `stop()` immediately upon `SIGTERM` | Requests/workers are still running and logging after close | Drain producers first, then stop logging |
| Calling `logger.info` after `context.stop()` | Records no longer have a reliable output destination | Emit final logs before stopping |
| Not stopping `AsyncAppender` | Queue/worker has not finished before JVM exits | Stop via `LoggerContext.stop()` or managed appender lifecycle |
| Assuming `logger.info` returning means logs reached the collector | Async queue, I/O, and network still have to process | Distinguish acceptance from delivery/durability |
| Setting `maxFlushTime=0` for all services | Shutdown may hang indefinitely on a slow sink | Choose a timeout based on grace period and risk assessment |
| Using `neverBlock=true` while requiring zero event loss | A full queue may drop events | Choose an appropriate backpressure/sink policy |
| Only increasing `maxFlushTime` to prevent log loss | Events may already have been dropped due to `discardingThreshold` | Check queue, filter, sink, and shutdown policies together |
| Closing a shared appender between requests | Other requests lose logs | Manage at the application/context level |
| Using `FileAppender` `append=false` for files that must be kept | Overwrites/truncates the file from the previous run | Choose an explicit append/rolling policy |
| Assuming JUL `Handler.close` is like Logback `Appender.stop` | Different APIs and different lifecycle scopes | Use the proper mechanism for each backend |
| Using try-catch and ignoring close errors | Unknown whether resources closed or logs were lost | Observe errors/status and design appropriate fallbacks |
| Stopping the collector before producers | Trailing logs are not collected | Coordinate shutdown across the entire pipeline when possible |
| Using logs for audits requiring strict durability | Logging does not guarantee transactions/end-to-end acks | Use dedicated durable storage/audit systems |

## 15. Self-Check Questions

**Question 1.** Why must you not call `LoggerContext.stop()` while requests are still being processed?

**Answer:** Running requests may continue logging while the appender has stopped, causing missing records. You must stop accepting work and manage in-flight tasks first.

**Question 2.** `AsyncAppender` accepts an event and `logger.info` returns. Is the event guaranteed to be in the file yet?

**Answer:** No. The event may still be in the queue or waiting for the worker and target appender.

**Question 3.** What does `maxFlushTime=5000` mean?

**Answer:** When stopping `AsyncAppender`, the worker has a configured wait limit of up to about 5,000 ms to drain the queue; if it does not finish, unprocessed records may be discarded.

**Question 4.** What side effect can setting `maxFlushTime=0` cause?

**Answer:** It removes the time limit for waiting on the worker to drain the queue; if the sink hangs, shutdown can take a very long time or be forcibly terminated by the orchestrator.

**Question 5.** Why must you check `discardingThreshold` and `neverBlock` in addition to `maxFlushTime`?

**Answer:** Because records may already have been dropped when the queue was nearly full or full while the application was running; waiting at shutdown cannot recover already-dropped data.

**Question 6.** In the Logback example, why is the file read after `context.stop()`?

**Answer:** Because the program wants to read the file after the appender has closed according to its lifecycle. Test results are clearer and less affected by open-file state.

**Question 7.** What is the conceptually equivalent resource-release method in JUL?

**Answer:** `Handler.close()`, after stopping related producers and removing the Handler from the Logger if you directly own the handler. This is not an identical API to `LoggerContext.stop()`.

**Question 8.** Why is a shutdown hook not guaranteed to run when a machine loses power or a process receives `SIGKILL`?

**Answer:** These situations may not allow the JVM to execute its normal shutdown sequence.

**Question 9.** Does stopping the context successfully guarantee that logs have been durably stored by a central backend?

**Answer:** No. There are still OS, network, collector, external service queue, and persistence policy layers.

**Question 10.** With an SLF4J backend other than Logback, can you cast `ILoggerFactory` to `LoggerContext` and stop it?

**Answer:** No. That is a Logback-specific API. You must identify the actual backend and let the lifecycle-owning component execute the appropriate shutdown.

## 16. References

- [Logback Manual — Configuration: Stopping logback-classic](https://logback.qos.ch/manual/configuration.html): stopping `LoggerContext`, managing appenders, and shutdown hooks.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queue, drop policy, `neverBlock`, `maxFlushTime`, and stopping the worker.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): `start`/`stop` mechanisms and `doAppend`.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `flush()`, `close()`, and Handler lifecycle.
- [Oracle Java SE 17 — java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): file output, rotation, and `close()`.

## Key Takeaway

**Safely closing appenders is not just calling one method at the end of `main`.** Identify who owns the logging lifecycle, stop log-emitting threads first, write final records while logging is still active, then stop Logback `LoggerContext` or close JUL `Handler` within the proper scope. With `AsyncAppender`, evaluate the queue, drop/block policies, and flush timeout; even a clean shutdown does not by itself guarantee delivery or durability in external systems. The goal of logging shutdown is **to release resources properly, reduce the risk of record loss, and clearly state the remaining limitations**.
