# 5.1 Distinguishing Application Logs from JVM Unified Logging

> **Java Advance – runtime-diagnostics** · **5. Logging and Stack Traces**

## 1. A Java Process Can Emit Multiple Types of Logs

When opening the logs of a Java service, you may encounter:

- Lines written by **application code** when receiving requests, calling databases, retrying, or catching exceptions.
- Lines emitted by the **JVM/HotSpot** about GC, safepoints, class loading, runtime activity, or the execution environment.
- **Stack traces** of an uncaught exception, printed by the exception handling mechanism or the application.
- Lines from the **container, web server, framework, native libraries, agents, and operating system**.

These lines may appear together in a terminal, a file, or a centralized system like Loki/ELK, but **their producer, enable/disable mechanism, metadata, and diagnostic questions are different**. A line appearing in Docker logs does not automatically become an "application log"; a line containing the word "GC" in the application is not automatically Unified Logging.

The two main systems in this lesson:

1. **Application logging**: the application/framework actively logs **business events and behavior in Java code** via java.util.logging (JUL), SLF4J + Logback/Log4j2, System.Logger, or the corresponding framework.
2. **JVM Unified Logging (UL)**: the logging system from **JVM components**, primarily configured with HotSpot's **-Xlog** option, using *tags*, *levels*, *decorators*, and *outputs*.

The goal is not to choose one over the other. During runtime diagnostics, we usually **need both**, each answering a different class of questions.

### Learning Outcomes

After this lesson, you will be able to: identify which source a log line belongs to; choose application logging or Unified Logging to test a hypothesis; read `-Xlog` syntax and tag/level/decorator/output components; explain why logs in the same file still do not belong to the same system; correlate application logs, JVM logs, exceptions/stack traces, and metrics on a timeline; and enable diagnostic logging with controlled scope, duration, and cost.

## 2. Comparison by Source, Purpose, and Control

| Criterion | Application Logs | JVM Unified Logging |
| --- | --- | --- |
| **Who emits the log?** | Application code, Java frameworks, libraries via the application's logger | JVM runtime/HotSpot and VM components that support Unified Logging |
| **What does it answer?** | Which request failed, which business step errored, what did downstream reply, where was a retry triggered? | Which GC occurred, which JVM safepoints happened, how were classes loaded/unloaded, what is the VM doing? |
| **API/configuration** | Logger API, Logback/Log4j2/JUL configuration files, framework settings | The **-Xlog** option, and some runtime configuration via **jcmd VM.log** |
| **Classification** | Logger name/category, level, MDC/structured fields per framework | Tag sets such as *gc*, *safepoint*, *class+load* and levels *error, warning, info, debug, trace* |
| **Request context** | Can record requestId, traceId, tenant, route, status if provided by the application | Does not inherently have business requestId/traceId; typically has timestamp/uptime/PID/thread ID via decorators |
| **Output** | Console, file, collector, appender/handler, JSON… depending on configuration | stdout, stderr, file, and `-Xlog`'s file rotation mechanism |
| **Stack trace** | Can attach a Throwable for the formatter/appender to print the exception stack | Some JVM logs contain VM details; does not replace application exception stack traces |
| **Changing level** | Per framework configuration/application management | Via `-Xlog` at startup, or `VM.log` on a running JVM if supported and permitted |
| **Risks when enabling verbose output** | Volume, sensitive data, formatter/appender overhead | VM event volume, CPU/I/O, disk, noise; trace level can be very large |

**Important boundary:** JVM Unified Logging is **not** a facade for application loggers. Setting *-Xlog:gc=debug* does not automatically raise the *com.company.payment* logger to DEBUG; setting Logback root level to DEBUG also does not automatically enable HotSpot GC details. You must configure the exact **producer** you want to observe.

It is also necessary to distinguish a **framework logger** from *System.out.println*: a println statement merely writes data to an output stream without carrying severity, logger name, trace ID, standard format, or rotation. A framework can be configured to send logs to the same stdout, but sharing a destination does not make the two mechanisms one.

## 3. Application Logging: Logs Along Execution Flow and Business Logic

### 3.1 Appropriate Content

A checkout service application might log:

- Request start: route template, request ID, trace ID, version code.
- Dependency call duration, success/failure outcome, retry count.
- Business-related exceptions, error type, current operation, and outcome.
- Processing duration or completion status to compare against p95/p99 metrics.
- Important operational events: circuit breaker state transitions, approved configuration changes, retry policy.

An application **should not** log personal data, tokens, passwords, full payment payloads, or sensitive SQL parameters just for debugging. Having a randomized/controlled requestId helps tracing; it does not mean the entire request data should be logged.

Example of a hypothetical application log record:

~~~text
2026-10-29T08:10:12.340Z INFO service=checkout route=/orders/{id} traceId=t-9 requestId=r-42 message="start"
2026-10-29T08:10:13.105Z ERROR service=checkout traceId=t-9 requestId=r-42 exception=TimeoutException message="payment call timed out"
~~~

This is an **illustrative log**, not a mandatory format of JUL, Logback, or Log4j2. Timestamps, fields, error levels, JSON or text are determined by configuration and code. In real applications, do not turn user IDs or URLs with dynamic identifiers into high-cardinality metric labels; logs/traces may contain correlation IDs in accordance with security policy.

### 3.2 Logger Name, Level, Handler/Appender

A common model:

~~~text
Application code
  -> Logger ("com.example.checkout")
  -> Level/filter (INFO/WARN/ERROR...)
  -> Formatter/encoder (text or JSON)
  -> Handler/appender (stdout, stderr, file, collector...)
  -> Log pipeline / storage
~~~

- **Logger/category** usually reflects the class/package or business component.
- **Level** filters verbosity. Level names differ by framework: JUL uses *SEVERE/WARNING/INFO/FINE/...*, while Logback/Log4j2 typically use *ERROR/WARN/INFO/DEBUG/TRACE*. They are **not** directly `-Xlog` levels.
- **Context** (MDC or structured arguments) is an application logger/framework mechanism, not an automatic HotSpot decorator.
- **Handler/appender** decides whether to send to stdout, stderr, or a file. JUL's ConsoleHandler defaults to stderr; other framework configurations may use stdout. **Do not infer the log source solely from the output stream**.

If a handler uses an async queue or remote shipper, logs may be delayed, dropped under overload, or appear out of global order. A missing log line does not by itself prove the event did not happen.

### 3.3 Limitations of Application Logs

An application only knows what is instrumented or logged by the framework. If the code does not log GC pauses or class unloading, application logs cannot independently provide evidence about them. Conversely, the VM may know GC is running, yet not know which requestId is waiting on payment unless another observability correlation mechanism is in place.

When a request reports a timeout, you need application logs about network/dependency/exceptions and possibly VM logs about GC/safepoints to distinguish waiting on an external service from runtime-level application pauses.

## 4. JVM Unified Logging: Logs Emitted by the JVM

Unified Logging is HotSpot's standardized logging mechanism (introduced in JDK 9, present on JDK 17+). It uses a **tag set** to specify the VM subsystem and a **level** to select verbosity.

Groups of information commonly useful for diagnostics:

| Tag set / selector | What to investigate? | Notes |
| --- | --- | --- |
| *gc* | Main GC messages | Does not automatically include every record with other GC tag combinations |
| *gc*=info* | Tag sets containing *gc*, at info level or higher in terms of verbosity threshold | Wildcards broaden scope; log volume can grow sharply |
| *gc+heap=debug* | Messages tagged with the exact tag set *gc,heap* at debug level | Not equivalent to selecting *gc* or *heap* separately |
| *safepoint* | VM safepoint events | Specific availability and formatting depend on JDK/VM |
| *class+load* | Class loading | Can generate very many lines, especially during startup |
| *os+container* | Runtime container information when supported | Exact tags/events must be verified on the JVM in use |

**These selectors are common HotSpot/JDK examples, not a guarantee that every JVM/vendor/version emits the exact same events.** Always check *java -Xlog:help* on the actual version.

### 4.1 Tag Sets and Plus vs. Comma

In `-Xlog` syntax:

- The **+** sign combines tags belonging to **one tag set**, for example *gc+heap*.
- The **,** between selections defines **multiple selections**, for example *gc,safepoint*.
- The **\*** immediately after a tag set creates a **wildcard match**: *gc\** matches tag sets containing *gc*; without a wildcard, it generally requires an **exact tag set match**.

Examples:

~~~bash
java -Xlog:gc=info MyApp
java -Xlog:gc*=info MyApp
java -Xlog:gc+heap=debug MyApp
java -Xlog:gc,safepoint MyApp
~~~

In the comparison table above, the first two selectors are **not identical**: *gc=info* selects only messages with the exact tag set *gc*, whereas *gc*=info* (with `*` at the end of the tag selector) expands to multiple tag sets containing *gc* such as *gc,heap*, *gc,start*, depending on the JVM. Therefore, two dashboards "with GC logs" can still have different levels of detail. Selections with **+** and **,** are also not interchangeable.

**Shell warning:** some special characters in arguments require quoting depending on the shell. The commands above only illustrate JVM syntax; when placed in a Dockerfile, YAML, or shell script, verify escaping and argument integrity after deployment.

### 4.2 Unified Logging Levels

Commonly supported levels:

~~~text
off  error  warning  info  debug  trace
~~~

In terms of verbosity, *trace* usually produces more information than *debug*, while *info* focuses on normal operational events. VM level names **do not necessarily map one-to-one** to application logging frameworks.

An often overlooked point: **the default is not "JVM logs nothing"**. Without `-Xlog` configured, HotSpot has a default equivalent to logging **warning/error** messages across tags, typically to stdout with decorators *uptime,level,tags*. Enabling the *-Xlog:gc* selector adds GC info-level details without needing to disable default logging.

**Do not use -Xlog:disable arbitrarily.** This directive turns off all Unified Logging output, including default warnings/errors, until another configuration re-enables it. Missing warnings afterward can cause the loss of diagnostic evidence.

### 4.3 Why Do JVM Logs Not Contain requestId?

The JVM knows about threads, heap, classes, GC cycles, safepoints, and many internal events. It does not by default know the *requestId* placed in the application's MDC. A GC line may contain **GC ID**, **uptime**, and **PID**, but a GC ID is not a request ID and a thread ID in a decorator is not automatically a business correlation ID.

Correlation is usually done via **timestamp + host/container/pod + PID/JVM instance + trace/metric**. If two JVMs print to the same collector stdout without instance metadata, it is very easy to attribute a GC pause from JVM A to a failing request on JVM B.

## 5. -Xlog Syntax: Reading Left to Right

General form (per the `java` command documentation for HotSpot):

~~~text
-Xlog:[what]:[output]:[decorators]:[output-options]
~~~

Parts after `-Xlog` can be omitted to use defaults. A complete example:

~~~bash
java -Xlog:gc*=debug:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=10M MyApp
~~~

Breakdown:

| Part | Example value | Meaning |
| --- | --- | --- |
| *what* | *gc*=debug* | Selects tag sets containing *gc* (wildcard) at debug level and less verbose levels |
| *output* | *file=gc-%p.log* | Writes to file; *%p* expands to PID |
| *decorators* | *time,uptime,level,tags* | Adds calendar time, time since VM start, severity, and tag set |
| *output-options* | *filecount=5,filesize=10M* | Configures log rotation up to the approximate file count/target size |

The syntax above belongs to **JVM launch flags** and must be placed **before the main class or -jar**:

~~~bash
java -Xlog:gc=info -jar service.jar
~~~

If *-Xlog:gc=info* is placed after *-jar service.jar*, it usually becomes an **application argument**, not a JVM option; the program may receive the string, but the JVM will not change its logging configuration.

### 5.1 Unified Logging Outputs

- **stdout**: e.g., *-Xlog:gc:stdout*; suitable if the container pipeline actively collects stdout.
- **stderr**: e.g., *-Xlog:gc:stderr*; can help separate streams, though a collector may merge them back together.
- **file=...**: e.g., *-Xlog:gc:file=gc.log*; requires checking write permissions, path inside the container, disk capacity, rotation, collection mechanism, and retention.

Output choices say nothing about application loggers. You can configure the app logger to stdout and JVM UL to a separate file, or both to stdout. **Same destination does not mean same filter or same structure**.

Example of a separate file for GC:

~~~bash
java -Xlog:gc*:file=gc-%p.log:time,uptime,level,tags:filecount=3,filesize=5M -jar service.jar
~~~

If the file lives on the container's ephemeral filesystem without a volume/shipper, it can disappear when the pod is replaced. If using file rotation, verify how the collector tracks renamed files and neither re-reads nor misses segments.

**Do not assume filecount/filesize equals permanent retention.** File size rotation is a local mechanism, whereas centralized retention, archival, data protection, and pod lifecycle must be designed separately.

### 5.2 Decorators: VM Timestamp Is Not App Timestamp

Common decorators:

- *time*: calendar time in a format including timezone.
- *utctime*: UTC timestamp.
- *uptime*: elapsed time since JVM startup, e.g., 12.345s.
- *level*: severity of the VM message.
- *tags*: tag set that emitted the message.
- *pid*: process ID.
- *tid*: thread identifier recorded by the JVM logging system.
- *hostname*: host name.

If decorators are not specified, the common default is **uptime,level,tags**. Therefore, a sample like:

~~~text
[3.452s][info][gc] GC(0) Pause Young (Normal) ... 12M->4M(128M) 3.4ms
~~~

is a **format illustration**, not guaranteed stdout on every JDK/GC. Seeing *[3.452s]* does not mean the event occurred at 03:45:02 system time; it is typically **JVM uptime**. To align with the moment a request failed in application logs, you need the JVM start time or to enable the *time/utctime* decorator.

Example with calendar and uptime decorators:

~~~bash
java -Xlog:gc=info:stdout:time,uptime,level,tags,pid -jar service.jar
~~~

This adds useful metadata for correlation, but does not automatically give application logs the same timestamp format. Centralized log collectors may also attach an **ingestion timestamp** distinct from the **event timestamp**; do not treat them as interchangeable when determining causal order.

### 5.3 Checking Actual Support and Tags

Inspect the `java` command of the JVM that will run:

~~~bash
java -version
java -Xlog:help
~~~

*-Xlog:help* displays the syntax, tags, levels, decorators, and examples supported on that build. This is a better source than copying flags verbatim from another JDK/vendor and assuming they always work.

There is no need to enable **all=trace** in production just to discover tags. *Trace* can generate huge volume and overhead. Start with a narrow scope and low verbosity, then increase when you have a specific hypothesis and time limit.

## 6. Both Log Streams Can Enter the Same Container stdout

Example topology:

~~~text
[Application code]
    |
    +-- SLF4J/Logback/JUL -> stdout ------------+
                                                |
[JVM/HotSpot]                                  +-- container runtime
    |                                           |        |
    +-- -Xlog:gc*=info:stdout ------------------+        +-- shipper/collector
                                                         |
                                                         +-- dashboard/query
~~~

Operators see multiple lines in the same *docker logs*, *kubectl logs*, or centralized index. Yet application logger filtering still controls **application logs**, and `-Xlog` still controls **JVM logs**.

**Example of lines from two sources in one stream (illustrative):**

~~~text
2026-10-29T08:21:04.100Z INFO service=checkout requestId=r-7 message="handling request"
[2026-10-29T08:21:04.130+0000][9.451s][info][gc] GC(17) Pause Young ... 5.2ms
2026-10-29T08:21:04.180Z WARN service=checkout requestId=r-7 message="downstream slow"
~~~

The middle line has Unified Logging decorators/tags. The outer two lines follow the structure defined by the application logger. Appearing close together in time **does not by itself prove GC caused downstream slowness**: the GC pause may be only 5.2 ms while the request was slow by hundreds of ms. You must check time overlap, same instance, total pause time, request trace, CPU, and dependency latency.

When a collector merges stdout and stderr, the received order can differ from actual event order, especially across threads/async queues. For an incident, distinguish timestamps attached by the **producer**, the **runtime**, and the **collector**.

## 7. Standalone Java 17+ Example: Application Logs Outside -Xlog

The program below uses standard JDK **java.util.logging (JUL)** without external frameworks. To make stdout deterministic and easy to compare, it defines a custom **Handler** with an explicit format instead of relying on default timestamps/formatters. The example intentionally throws and catches an exception and attaches it to the LogRecord. The illustrative Handler prints only the exception **type**, not the full stack trace; in production, use a formatter/appender suitable for investigation needs.

Create the file **AppVsVmLoggingDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AppVsVmLoggingDemo {
    private static final Logger LOG = Logger.getLogger("demo.checkout");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        Handler stdout = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) return;
                String cause = record.getThrown() == null ? ""
                    : " cause=" + record.getThrown().getClass().getSimpleName();
                System.out.println(record.getLevel().getName()
                    + " [" + record.getLoggerName() + "] "
                    + record.getMessage() + cause);
            }

            @Override public void flush() { System.out.flush(); }
            @Override public void close() { }
        };
        stdout.setLevel(Level.ALL);
        LOG.addHandler(stdout);
        try {
            LOG.info("requestId=demo-001 checkout-start");
            try {
                throw new IllegalStateException("simulated");
            } catch (IllegalStateException ex) {
                LOG.log(Level.SEVERE, "requestId=demo-001 checkout-failed", ex);
            } finally {
                LOG.info("requestId=demo-001 checkout-end");
            }
        } finally {
            stdout.flush();
            LOG.removeHandler(stdout);
        }
    }
}
~~~

Compile/run on JDK 17 or higher:

~~~bash
javac AppVsVmLoggingDemo.java
java AppVsVmLoggingDemo
~~~

**The exact three lines emitted by the application Handler:**

~~~text
INFO [demo.checkout] requestId=demo-001 checkout-start
SEVERE [demo.checkout] requestId=demo-001 checkout-failed cause=IllegalStateException
INFO [demo.checkout] requestId=demo-001 checkout-end
~~~

The program does not use JVM `-Xlog` to emit these three lines. *LOG.log(Level.SEVERE, ... , ex)* attaches the Throwable to the record; the custom Handler only summarizes the Throwable type. With another handler/formatter, a multi-line stack trace can be printed. Because the error was caught, the JVM does not have to print the exception itself to stderr.

Try enabling a **separate** VM log source in the same process:

~~~bash
java -Xlog:class+load=info:stdout:uptime,level,tags AppVsVmLoggingDemo
~~~

When run, the JVM can print **very many** class loading events tagged *[info][class,load]* alongside the three application lines. The order and number of JVM lines depend on build, classpath, class loading process, and environment; **there is no fixed stdout for the whole process** when `-Xlog` is added.

To observe them separately:

~~~bash
java -Xlog:class+load=info:file=classload-%p.log:uptime,level,tags AppVsVmLoggingDemo
~~~

The three application lines are still sent to stdout by the Handler; class loading events are sent by Unified Logging to a PID-named file. Not a single line of Java application logging changed. **Detailed class-load logging should not be kept enabled continuously in production without a clear reason and a collection plan.**

### 7.1 Why Is the Demo Not Production-Grade?

For ease of learning, the custom Handler uses synchronous *System.out.println* without escaping, structured JSON, sensitive data handling, backpressure, or full stack traces. It also simulates only a single request. In production, use a standardized framework/handler, add necessary context fields, support multi-threading, rotation/collectors, and retention policies. The demo only proves **the independence between the application producer and the JVM producer**.

## 8. Where Do Stack Traces Fit in the Two Logging Systems?

A **stack trace** is the set of stack frames describing the call path at the time of a Throwable or sampling point, not a separate "logger type". It can be:

1. Written via an application logger when code passes a *Throwable* to LogRecord/SLF4J/Log4j2.
2. Printed directly via *Throwable.printStackTrace()* or by the uncaught exception reporting mechanism (usually to stderr).
3. Collected from a thread dump/JFR/profiler or other diagnostic tool, where the stack is state/execution data rather than necessarily a framework log event.
4. Emitted as details of certain VM events, depending on tag/command and JVM.

**Three commonly confused statements must be distinguished:**

- "The application logged ERROR with an exception stack": the application/framework logged a Throwable and the formatter could print the stack.
- "There is a stack trace in the terminal": it could be an uncaught exception on stderr; not necessarily routed through the application logger.
- "JVM Unified Logging is enabled": this does not mean every business exception will have its full stack frames printed.

Illustrative example of a Throwable logged by a framework:

~~~text
ERROR checkout requestId=r-9 Payment failed
java.lang.IllegalStateException: payment rejected
    at com.example.CheckoutService.pay(CheckoutService.java:42)
    at com.example.CheckoutHandler.handle(CheckoutHandler.java:18)
~~~

Why is this stack valuable? It reveals the call path **at the point the exception was thrown/logged** in the application context. However, it may say nothing about:

- Which GC pauses happened concurrently.
- What locks another thread was holding.
- When classes were loaded or safepoints occurred.
- How a timeout happened due to a dependency, DNS, or queue wait if the stack only reflects the reporting point.

Therefore, when runtime evidence is needed, we supplement with Unified Logging/metrics/JFR/thread dumps according to our hypothesis, rather than expecting an application stack trace to explain everything.

### 8.1 Multi-line Stack Traces and Centralized Logging

An exception stack can span many lines. If a shipper treats **each line** as a separate event, the `"at ..."` frames can lose their `requestId` and get interleaved with other stacks. Use a JSON exception field format or controlled pipeline multiline parsing. Do not truncate a stack to the first few lines and conclude there is no *Caused by* or *Suppressed* if the system may have truncated it due to size limits.

When sharing logs with other teams, filter out sensitive arguments, internal paths, usernames, or tokens. Stack traces are useful for diagnostics but can also reveal system structure.

## 9. Combining Application Logs and Unified Logging to Distinguish Causes

Consider a scenario: p99 of the `/checkout` endpoint jumped from 180 ms to 1.2 s after a deploy. A few requests timed out. Looking only at application logs shows *TimeoutException*; looking only at JVM GC logs shows Young GCs. That is not enough basis to conclude Young GC caused the timeouts.

Evidence-based procedure:

1. **Define the symptom:** route, status, time range, instance/pod, request count, timeout rate, latency distribution.
2. **Inspect application logs:** request/trace ID, request receipt time, DB/payment calls, retries, exceptions, failure messages. Ensure timestamps share the same timezone/clock basis.
3. **Inspect JVM logs:** GC/safepoint events and durations on the **same JVM instance** within the window; note *uptime* differs from wall-clock time.
4. **Correlate metrics:** CPU, heap, GC pause histogram, active/pending thread pool, completed request rate, error count.
5. **Compare timelines:** Do GC pauses overlap the slow request window? Is total pause large enough to explain 1.2 s, or only 3–10 ms? Are there signs of downstream waits?
6. **Form competing hypotheses:** H1 due to GC pauses; H2 dependency latency; H3 thread pool/connection pool saturation; H4 retry amplification.
7. **Verify:** use trace spans, thread dumps/JFR, or targeted tag logging with cost limits; compare before/after under the same load; record confidence level.

### Scenario A – JVM Under Allocation Pressure

**Application:** requests are sporadically slow; app logs have requestId/time, no obvious code errors. **VM:** GC event frequency rises, total GC pause time rises overlapping the latency spike, and heap allocation rate also rises. This is **supporting evidence** for an allocation/GC pressure hypothesis, not sole proof; you must cross-check exact GC durations against request timelines, CPU, heap, and workload.

### Scenario B – Dependency Timeout While GC Is Normal

**Application:** many TimeoutExceptions against the same dependency, retry counts rise, traces show HTTP/downstream waiting. **VM:** only brief GCs occur, not overlapping the 1–2 s slow request intervals. Investigation should prioritize network, retry policy, connection pool, downstream, and queues instead of enabling *gc=trace* indefinitely.

### Scenario C – JVM Safepoint or Class Loading Affecting Startup

**Application:** startup delay, slow warmup, or high first-request latency. **VM:** increased class loading/compilation or safepoint events near startup time. Correlate deployment startup, JIT warmup, readiness gating, class loading, and GC using appropriate tags; do not assume every *class+load* line is an incident.

### Scenario D – Application Exception Without GC Logs

**Application:** stack trace clearly shows the call path leading to an IllegalArgumentException. **VM:** no corresponding GC info because no GC occurred, the appropriate selector wasn't enabled, or logs went to a different file. Do not say "the JVM reported no errors so the app has no errors"; GC logs are not responsible for recording business exceptions.

## 10. Choosing the Log Source by Hypothesis

| Investigation question | Priority | Supporting evidence |
| --- | --- | --- |
| At which step did the order fail? | Application log, trace, exception stack | Dependency status, retry metric |
| Why did the request call payment twice? | Application log by requestId/traceId | Attempt count, trace graph |
| Did a GC pause overlap the p99 spike? | JVM Unified Logging `gc` tag and GC metrics | JFR, request timeline |
| Is the JVM loading/unloading classes abnormally? | Unified Logging `class+load/unload` tag if needed | Metaspace metrics, classloader stats |
| Did the thread pool run out of workers? | Application framework metrics/logs, thread dump | JVM safepoint, CPU, queue |
| App prints ERROR without a stack trace? | Formatter/appender config, logger call site | Was Throwable passed, did collector truncate |
| No logs seen even though JVM restarted? | Check container stdout/stderr, output file, rotation, collector | Process start time, app shutdown logs |
| Need configuration errors from JVM startup? | JVM startup warnings/flags, VM logging | Java command-line, deployment config |
| Another pod behaves normally? | Compare app + JVM logs per instance/version | Traffic mix and resource limits |

**Which source cannot answer which question?** Do not look for `requestId` in GC tags; do not expect application logger WARN messages to appear just by enabling *-Xlog:all=warning*; do not use `UncaughtExceptionHandler` as a replacement for logging every request; do not use a single stack trace line to conclude a memory leak or deadlock.

## 11. Changing JVM Logging at Runtime with jcmd VM.log

Some HotSpot JVMs allow viewing/modifying the Unified Logging configuration of a **running JVM** via the diagnostic command *VM.log*.

Example using a **hypothetical PID 12345**, replace with the confirmed target JVM PID:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.log list
jcmd 12345 help VM.log
~~~

If *VM.log list* is supported, it shows the VM's current logging configuration. The *help VM.log* command shows arguments such as *what*, *output*, *decorators*, *output_options*, *list*, and *rotate* for the current build.

**Runtime changes do not permanently update the launch configuration.** If the JVM restarts, startup/deployment flags still determine the initial state. Before enabling extra tags or changing outputs in production, you need operational authorization, a goal, a duration limit, verbosity bounds, and a rollback plan.

Example showing command arguments (only perform in authorized environments and after reading `help` on the target JVM):

~~~bash
jcmd 12345 VM.log output=stdout what="gc*=debug"
~~~

This operation **modifies the runtime logging configuration**, not a read-only command. Syntax and output names can vary by JDK; verify with *VM.log list* before and after. Do not enable *all=trace*, delete existing outputs, or use *disable* without understanding the impact. For JVMs that disallow attach or do not support `VM.log`, use launch configuration/telemetry instead of trying to bypass permissions.

Dynamic **application logging** configuration (if a framework provides an API/JMX/actuator) is a **separate** mechanism; you cannot use *VM.log* to lower the `com.example` package logger from DEBUG to INFO.

## 12. Log Rotation, Volume, Overhead, and Evidence Quality

More detailed logs come at a cost: CPU for formatting, I/O, disk, network, storage cost, and pressure on the collector. During high-traffic incidents, uncontrolled trace-level logging can sometimes make things worse.

### 12.1 Distinguishing Forms of Rotation and Backpressure

- Application loggers use appenders/handlers and retention according to their own configuration.
- Unified Logging file output has rotation options like *filesize* and *filecount*; values are approximate targets, not exact byte guarantees.
- Container runtimes may have independent log rotation; collectors may apply different retention policies.
- When `-Xlog` uses asynchronous mode *-Xlog:async* (if supported by the JVM), records queued into the buffer can be **dropped** when the bounded buffer fills; "not seeing an event" does not automatically mean "it did not happen".
- Application async appenders can also drop/suspend per policy. Ask about pipeline reliability and dropped-log metrics when analyzing very short incidents.

For production, start at the necessary level, preferring bounded tags and finite observation windows. To track counts/latencies continuously at low cost, **metrics** are usually more suitable than logging every event at debug level. Use **traces** for request paths, **logs** for event details, and **JFR** for structured runtime event profiling; they complement each other.

### 12.2 Why Can Timestamps Cause Wrong Conclusions?

A JVM log has an **uptime** decorator and an application log has a UTC timestamp. Joining the two requires knowing the JVM start time. If the JVM just restarted, uptime resets near 0. Collector timestamps may lag event time by several seconds due to buffering. Machine clocks can drift if time sync is unstable. To conclude "GC happened 5 ms right before the request failed", you must compare exact **event timestamps** on the same **instance**.

Do not rely on line order across multiple streams to infer causality. An application WARN line after a GC line in the same terminal is only **temporal correlation**, not proof that GC caused the WARN.

### 12.3 Security and Privacy

- Application logs: restrict PII, session keys, request/response payloads, access tokens, and credentials.
- JVM logs: can expose class names, paths, memory sizes, runtime configuration; command lines or heap dumps are especially sensitive.
- Stack traces: can expose directories, package structure, SQL, inputs, or exception details.
- Apply least privilege, retention, and redaction; do not publish raw production logs publicly for debugging.
- Logs should not turn into unauthorized user surveillance tools.

## 13. Common Mistakes When Reading Both Types of Logs

| Misconception | Reality | How to handle |
| --- | --- | --- |
| "Enabling Logback DEBUG shows GC details" | Logback filters app events; GC belongs to JVM UL | Enable the appropriate `-Xlog` tag |
| "Enabling -Xlog:gc makes app INFO appear" | `-Xlog` does not control application loggers | Check the app's logger/handler/appender |
| "All stdout lines are application logs" | UL can also write to stdout | Distinguish producer/tag/formatter and instance source |
| "Line `[info][gc]` is SLF4J INFO" | That is a level/tag in JVM UL | Do not map levels directly between the two systems |
| "`gc+heap` means `gc` or `heap`" | `+` combines tags in one tag set | Distinguish from comma and wildcard |
| "`gc=info` equals `gc*=info`" | No wildcard: exact tag set; wildcard: sets containing tag | Verify selector behavior per JDK |
| "No GC logs means no GC occurred" | Tag might be disabled, written to another file, or collector dropped data | Check `-Xlog` config, output, metrics |
| "PID in GC log is the request ID" | PID is only the process; GC ID is not a trace ID either | Correlate via instance + timestamp + trace/metric |
| "Exception stack trace is JVM UL" | Can come from app logger/printStackTrace/uncaught handler | Find the producer and formatter |
| "`VM.log` can change logger `com.example`" | `VM.log` manages only Unified Logging | Use the separate app logging mechanism |
| "`-Xlog:disable` only turns off debug" | Can disable default warnings/errors too | Avoid uncontrolled use in production |
| "A GC line before an error proves GC caused it" | Correlation is not causation | Compare pause duration, trace, metrics |
| "Rotating GC files means centralized retention exists" | Rotation and retention are two separate mechanisms | Check file shipping and lifecycle |
| "Stack lacks `Caused by` so there is no deeper cause" | Collector may have truncated or misparsed multiline logs | Check raw log/formatter/truncation |

## 14. Diagnostic Procedure When Expected Logs Are Missing

**A. Application logs are missing:**

1. Confirm the right service/version/instance and that requests actually reach it.
2. Confirm logger name, level, appender/handler, filters, and async queue.
3. Check actual output: stdout/stderr/file; does the container collector scrape that target?
4. Check sampling, rate limiting, structured parsing, multiline/truncation.
5. If an error was caught and swallowed without logging anything, JVM Unified Logging will not generate that application event either.

**B. JVM Unified Logging is missing:**

1. Use *java -Xlog:help* on the matching JDK to verify selectors/tags.
2. Confirm the actual launch args before the main class or `-jar`, and that you are viewing the right JVM instance.
3. Check default/file/stderr output, write permissions, container mounts, and collector.
4. Confirm **the event actually occurred**; enabling *gc* does not force a GC in a short program.
5. If permitted, check *jcmd PID VM.log list* for the current configuration; do not change production log levels without authorization.
6. Cross-check metrics/JFR to distinguish whether the event didn't occur or wasn't recorded/collected.

**C. Application ERROR exists but no stack trace:**

1. Was a *Throwable* passed to the log API? Logging only *ex.getMessage()* usually drops the stack.
2. Is the formatter/encoder configured to print stacks or a JSON exception field?
3. Did the collector split one stack trace into multiple events or truncate due to size limits?
4. Is there a redaction policy stripping sensitive fields?

**D. Logs from multiple JVMs are interleaved:**

1. Identify container/pod/host/PID/version for each line.
2. Normalize timestamps to UTC, noting uptime and JVM start epoch time.
3. Group logs by instance before making runtime inferences.
4. Only aggregate for service-wide statistics; never treat VM logs from instance A as the cause of a request on B.

## 15. Log Reading Exercises with Answers

### Exercise 1 – Identifying the Producer

Given three illustrative lines:

~~~text
INFO [order.service] requestId=r-12 save-order
[4.100s][info][gc] GC(1) Pause Young ... 2.1ms
java.lang.IllegalArgumentException: invalid quantity
~~~

**Question:** Which line is definitely Unified Logging in standard format? Which line definitely uses SLF4J?

**Answer:** The second line matches Unified Logging output thanks to the level/tag decorator *gc*. The first line looks like an application log, but **you cannot conclusively say it uses SLF4J** from text alone; JUL, Log4j2, or a custom formatter can print similarly. The third line is the header of an exception stack/Throwable message, whose producer/output destination cannot be determined without context.

### Exercise 2 – Selectors

**Question:** Does *gc+heap=debug* mean "enable gc and heap separately at debug"?

**Answer:** No. The `+` creates a **combined tag set**; without a wildcard, the selector matches that exact tag set. For multiple selectors use a comma, and for tag sets containing *gc* use the wildcard *gc\**.

### Exercise 3 – No GC Observed

Enabled *-Xlog:gc=info* for a program running a few milliseconds. Not a single GC info line appeared. **Can we conclude the JVM did not run?**

**Answer:** No. The run may not have triggered a GC event matching the selector, the collector/output may differ, the launch arg may be misplaced, or logging may vary by build. Verify launch config, output, and events.

### Exercise 4 – Same stdout

Container stdout contains both application JSON lines and *[info][gc]* lines. Operations wants to drop GC debug logs while keeping application INFO. **Where do you adjust?**

**Answer:** In the **JVM Unified Logging selector/level** and related output. Do not lower the app INFO logger if you only want to reduce GC output. If runtime adjustment is needed, verify *VM.log* support and permissions; if configured at startup, perform a controlled rollout.

### Exercise 5 – Same Timestamp Means Same Cause?

A request took 1,400 ms, during which a 6 ms GC pause occurred. **Can we say GC explains the entire latency?**

**Answer:** No. A 6 ms pause alone does not explain 1,400 ms. Check whether there were multiple pauses, CPU/scheduling delays, queue waits, and per-dependency traces; occurring at the same time only shows overlap, not causal mechanism.

### Exercise 6 – Missing Stack Trace

Code only calls the logger with *ex.getMessage()* and the collector displays a single ERROR line. **Does the missing stack prove the exception had no stack?**

**Answer:** No. It happens because the code did not pass the Throwable, the formatter did not print the stack, or the log pipeline truncated it; check the log call site and configuration. You can log *logger.log(Level.SEVERE, message, ex)* in JUL or the framework equivalent, subject to security policy.

### Exercise 7 – Uptime 3,000 Seconds

The GC log has decorator *[3000.000s]*, and the application log has timestamp 10:05:00 UTC. **Are they at the same moment just from looking at these two numbers?**

**Answer:** Insufficient data. You need the JVM start time or `time/utctime` decorator, matching PID, and instance clock; uptime is not calendar time.

## 16. Summary Checklist for Incident Reports

Before drawing conclusions from logs:

- **Source:** application code/framework, JVM UL, stderr stack trace, or container/OS?
- **Destination:** stdout, stderr, file, which collector? Any rotation/drop/truncation?
- **Scope:** right instance/pod/PID/version, route, and request?
- **Time:** event time or ingestion time; UTC or uptime?
- **Verbosity:** application logger level/appender or `-Xlog` tag/level/decorator?
- **Evidence:** do app events/stacks for the request, VM events and durations, metrics, and traces align?
- **Limitations:** could logs be missing due to sampling, lack of instrumentation, event non-occurrence, or pipeline loss?
- **Safety:** does changing log levels introduce overhead, sensitive data, start/stop time bounds, authorization, and rollback capability?

Example of a well-founded conclusion:

> Between 08:10–08:15 UTC, requestId r-42 on pod checkout-v2-7 timed out on the payment call per application logs/traces. JVM UL for the same PID recorded two GC pauses of 4 ms and 6 ms, insufficient to explain a 1.2 s request. Primary hypothesis: downstream latency or connection wait; next verification steps: dependency spans, pool gauges, and retry metrics. There is no evidence to conclude GC was the cause.

## 17. Official References for Verifying Against Actual JDKs

- **Oracle JDK 21 – The java Command**, section *Enable Logging with the JVM Unified Logging Framework*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Oracle JDK 21 – The jcmd Command**, diagnostic command *VM.log*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **OpenJDK JEP 158 – Unified JVM Logging**: https://openjdk.org/jeps/158
- **Java SE 17 – java.util.logging API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html

Always inspect *java -Xlog:help* and *jcmd PID help VM.log* on the **exact JVM build** being diagnosed; available tags, outputs, and commands may change by version/vendor.

## Key Takeaways

**Application logging** answers "what are the application and requests doing, and where did business logic fail?"; **JVM Unified Logging** answers "what is the virtual machine doing, and what GC/safepoint/class/runtime events occurred?". Both may write to stdout, yet **they do not share the same producer, filters, or context**. Stack traces can come from loggers or stderr and **are not synonymous with -Xlog**. When diagnosing, distinguish the producer, record exact instance/PID and timestamps, combine application logs with Unified Logging, metrics, and traces/JFR, and verify hypotheses rather than inferring causality from a single log line.
