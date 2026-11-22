# Exception Events in Java Flight Recorder

**Exception events** are JFR events that record the throwing of exceptions or Errors in the JVM. When enabled, these events provide the timestamp, thread, exception type, message, and stack trace to help locate where errors originate. They help answer: which exceptions occur, on which code paths, on which threads, and whether their frequency increases during an incident?

In JFR, the two primary events are:

- `jdk.JavaExceptionThrow`: event for objects in the `java.lang.Exception` hierarchy.
- `jdk.JavaErrorThrow`: event for objects in the `java.lang.Error` hierarchy.

In addition, `jdk.ExceptionStatistics` provides periodic statistics on the number of objects in the `java.lang.Throwable` hierarchy created. This is a statistical metric, distinct from detailed per-throw events.

Exception events are especially useful when an application catches and handles many errors internally in code. Application logs may only record the final error, whereas JFR helps find repeated stack traces or exceptions that occur before a request fails. However, a recorded event does not by itself prove that the exception escaped the request handler or caused a request failure; it must be correlated with logs, metrics, traces, and business custom events.

## 1. Exceptions in Java and Their Relationship to Throwable

Every exception and error in Java inherits from `java.lang.Throwable`.

~~~text
                 Throwable
                 /       \
           Exception     Error
              |
       RuntimeException
~~~

Main branches:

| Type | Meaning | Examples |
|---|---|---|
| Checked exception | Exception that must be declared or handled per language rules | IOException, SQLException |
| Unchecked exception | RuntimeException and its subclasses; the compiler does not require declaration | NullPointerException, IllegalArgumentException |
| Error | Serious issue related to the runtime or execution environment | LinkageError, StackOverflowError |
| OutOfMemoryError | Special Error when the JVM cannot allocate additional memory as requested | OutOfMemoryError |

Checked and unchecked are classifications in the Java language. JFR does not have a separate column recording "checked" or "unchecked"; when classification is needed, inspect `thrownClass` and that class's inheritance hierarchy.

`RuntimeException` still falls under `Exception`, so it belongs to `jdk.JavaExceptionThrow`. `Error` is a separate branch and is reflected by `jdk.JavaErrorThrow`.

An exception may be caught and handled immediately, rethrown to the caller, or ultimately cause a request to fail. Seeing the event alone is not enough to determine which handling path occurred.

## 2. JFR Events Related to Exceptions

### jdk.JavaExceptionThrow

This event records exceptions in the `java.lang.Exception` hierarchy. Commonly inspected fields:

| Field | Meaning |
|---|---|
| startTime | Timestamp when the event was recorded |
| eventThread | Thread associated with the event |
| thrownClass | Concrete class of the exception |
| message | Exception message, if any |
| stackTrace | Stack trace at the site where the event occurred, if enabled |

Examples of exception types that may appear:

- `java.lang.IllegalArgumentException`
- `java.lang.NullPointerException`
- `java.io.IOException`
- `java.sql.SQLException`
- `java.util.concurrent.TimeoutException`

This event helps group by exception type and stack trace to find repeated code paths. The message may be empty or null; do not use the message as a unique grouping key because it may contain dynamic values.

### jdk.JavaErrorThrow

This event is for objects in the `java.lang.Error` hierarchy. Common fields include:

- `thrownClass`: class of the Error.
- `message`: message, if any.
- `eventThread`: associated thread.
- `stackTrace`: call path at the site where the event occurred, if enabled.

Examples:

- `NoClassDefFoundError`
- `NoSuchMethodError`
- `LinkageError`
- `StackOverflowError`

Do not treat `jdk.JavaErrorThrow` as a mechanism guaranteed to record every `OutOfMemoryError`. Some HotSpot event definitions exclude `OutOfMemoryError` from this event; when investigating an OOME, combine JVM logs, automatic heap dumps, and memory diagnostic tools.

### jdk.ExceptionStatistics

`jdk.ExceptionStatistics` is a periodic statistical event. The `throwables` field indicates the number of objects in the `Throwable` hierarchy created during the corresponding statistical interval.

This event is useful for detecting spikes in exception object creation without keeping a stack trace for every exception. In common JFR configurations, the event is emitted periodically about once per second.

Keep in mind the distinction:

- `JavaExceptionThrow` and `JavaErrorThrow` provide per-event details, including class and stack trace when enabled.
- `ExceptionStatistics` counts `Throwable` objects created during the statistical interval.
- A created `Throwable` object is not necessarily thrown; therefore, this statistic is not the count of failed requests or unhandled exceptions.

### Comparison Table

| Event | Scope | Purpose |
|---|---|---|
| jdk.JavaExceptionThrow | Exception | Find exception types and stack traces |
| jdk.JavaErrorThrow | Error | Investigate errors in the Error hierarchy |
| jdk.ExceptionStatistics | Created Throwable objects | Monitor overall trends |

Event and field names may vary across JDK releases or JVM implementations. Use the recording's metadata and the documentation for the running JDK to confirm.

## 3. What Does an Exception Event Tell You?

An exception event typically helps answer four questions:

1. **What exception type?** Check `thrownClass`.
2. **When did it occur?** Check `startTime`.
3. **Which thread raised it?** Check `eventThread`.
4. **Which code path led to it?** Check `stackTrace`.

Illustrative example:

~~~text
jdk.JavaExceptionThrow {
  startTime = 14:05:12.431
  eventThread = "http-worker-3"
  thrownClass = java.lang.IllegalArgumentException
  message = "orderId is required"
  stackTrace = [
    com.acme.OrderService.validate(OrderService.java:42)
    com.acme.OrderService.submit(OrderService.java:27)
    com.acme.OrderController.create(OrderController.java:19)
  ]
}
~~~

This is illustrative output, not the fixed output of a specific recording.

The stack trace is usually the most valuable piece of information for locating the source. If the same exception class appears from multiple different stack traces, group by both class and call path, not by class name alone.

### An Event Is Not a Full Copy of the Throwable

Standard JFR events do not store the entire object graph of an exception. Fields such as class, message, thread, and stack trace aid diagnosis, but do not replace object inspection or full logs when needed.

Cause chains, suppressed exceptions, and custom data may not be fully represented in standard events. If you need a specific business code or request correlation, create a custom event with intentionally chosen fields.

### An Event Does Not Determine Whether an Exception Was Handled

JFR can record an exception even if code further up the stack catches and handles it. Therefore:

- Having an event does not mean the request failed.
- Having no events does not prove code did not throw exceptions; the event might be disabled, throttled, or outside the recording window.
- Events do not replace logs for handling outcomes.
- Correlate with custom events, logs, or traces to determine whether the exception caused a business operation to fail.

## 4. Default Configuration and Rate Limiting

A notable change starting in JDK 25: `jdk.JavaExceptionThrow` is enabled by default in the standard JFR configuration and is throttled at **100 events per second**. This enables collecting useful exception data without letting an application that throws exceptions continuously produce an overly large recording.

Key points to remember:

- Older JDKs may disable `JavaExceptionThrow` in the default template.
- Starting in JDK 25, the standard configuration enables the event and rate-limits it at 100/s.
- Stack traces are typically enabled for this event in the standard template.
- When exceptions occur above the limit, the recording is no longer a complete list of every throw.
- Do not use recorded event counts to compute exact total exceptions while throttling is active.

You can inspect the configuration used in a recording file:

~~~bash
jfr metadata exceptions.jfr
~~~

View active settings in the recording:

~~~bash
jfr print --events jdk.ActiveSetting exceptions.jfr
~~~

If the event is missing from the file or lacks stack traces, check the template and active settings before concluding that the application is not throwing exceptions.

### Throttle Is Not the Same as Threshold

These two settings have different meanings:

| Setting | Meaning |
|---|---|
| enabled | Enable or disable the event |
| stackTrace | Whether to record stack traces |
| throttle | Limit the maximum event rate over time |
| threshold | Omit duration events shorter than the threshold |

Exception events are primarily instant events at the time of occurrence, so `throttle` is the key setting for controlling event volume. Do not apply a duration `threshold` as a way to filter exception counts.

### When Should You Change Throttle?

If you need a short-term investigation of a rare error, the default limit may suffice. If you need to observe high-frequency errors, consider:

- Shorter recordings.
- Enabling only necessary events.
- Keeping stack traces if you need to identify call sites.
- Increasing the limit or disabling throttle only in a controlled test window.
- Monitoring recording size and overhead.
- Reverting to the default configuration after collection.

Do not disable throttling for long-running production recordings without first evaluating exception volume and storage cost.

## 5. Enabling Exception Events at JVM Startup

You can start a recording immediately when running the application:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=2m,filename=exceptions.jfr -jar app.jar
~~~

With JDK 25+ and the standard template, `jdk.JavaExceptionThrow` is enabled by default. If you need to ensure the event is enabled in an environment with a custom template, specify the settings directly:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=2m,filename=exceptions.jfr,jdk.JavaExceptionThrow#enabled=true,jdk.JavaExceptionThrow#stackTrace=true -jar app.jar
~~~

To record Error events as well:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=2m,filename=exceptions.jfr,jdk.JavaExceptionThrow#enabled=true,jdk.JavaErrorThrow#enabled=true -jar app.jar
~~~

The filename and duration are examples. Choose a directory with write permissions and an appropriate retention policy.

## 6. Enabling Exception Events on a Running JVM with jcmd

You do not need to restart the application just to start a new recording if the attach mechanism and permissions allow it.

Find the PID:

~~~bash
jcmd -l
~~~

Check the `JFR.start` syntax on the target JVM:

~~~bash
jcmd 2125 help JFR.start
~~~

Start a recording:

~~~bash
jcmd 2125 JFR.start name=exception-analysis settings=default duration=2m filename=/secure/records/exceptions.jfr "jdk.JavaExceptionThrow#enabled=true" "jdk.JavaExceptionThrow#stackTrace=true" "jdk.JavaErrorThrow#enabled=true" "jdk.ExceptionStatistics#enabled=true"
~~~

Replace the PID and path with actual values. The trailing event parameters use the `event-name#setting=value` syntax; quotes prevent the shell from altering the setting strings.

Check recordings:

~~~bash
jcmd 2125 JFR.check verbose=true
~~~

Dump a snapshot while the recording is still running:

~~~bash
jcmd 2125 JFR.dump name=exception-analysis filename=/secure/records/exceptions-snapshot.jfr
~~~

`JFR.dump` creates a snapshot file without stopping the recording. When you want to end the recording:

~~~bash
jcmd 2125 JFR.stop name=exception-analysis filename=/secure/records/exceptions-final.jfr
~~~

Use `JFR.stop` when you have collected enough data or need to release the recording. If the recording has a duration, the JVM can also stop it automatically when the duration elapses.

### Disabling Exception Events When No Longer Needed

You can start a new recording with the events disabled or use a dedicated JFC configuration. For an already running recording, check whether settings can be updated dynamically on the target JDK using the corresponding command's help; do not assume all settings can be changed dynamically in the same way.

## 7. Filtering and Viewing Exception Events with the jfr Tool

A `.jfr` file is a binary file. Start with a summary:

~~~bash
jfr summary exceptions.jfr
~~~

The summary shows the recording duration, event counts, and size per event type. Look for lines such as:

- `jdk.JavaExceptionThrow`
- `jdk.JavaErrorThrow`
- `jdk.ExceptionStatistics`

Print specific events:

~~~bash
jfr print --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow,jdk.ExceptionStatistics exceptions.jfr
~~~

View exceptions only:

~~~bash
jfr print --events jdk.JavaExceptionThrow exceptions.jfr
~~~

View Errors only:

~~~bash
jfr print --events jdk.JavaErrorThrow exceptions.jfr
~~~

Export JSON for processing with other tools:

~~~bash
jfr print --json --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow exceptions.jfr
~~~

Inspect metadata and fields:

~~~bash
jfr metadata exceptions.jfr
~~~

Metadata helps confirm actual event names, fields, and data types. This is useful when processing recordings generated from multiple JDK releases.

### Reading an Event

When reading the output, focus on:

1. Timestamp to determine when it occurred.
2. `thrownClass` to classify the exception.
3. `message` to understand context if a useful message is present.
4. `eventThread` to identify the involved thread.
5. `stackTrace` to locate the code path.

Messages may contain dynamic, unstable, or sensitive data. Do not use raw messages as statistical labels or expose them directly on public dashboards.

## 8. Analyzing with JDK Mission Control

JDK Mission Control (JMC) opens recording files and provides an Event Browser to filter, group, and inspect event details.

Workflow:

1. Open `exceptions.jfr` in JMC.
2. Verify the recording time range.
3. Open the Event Browser.
4. Filter by `jdk.JavaExceptionThrow` or `jdk.JavaErrorThrow`.
5. Group by `thrownClass`.
6. Compare events by thread and stack trace.
7. Select an event to inspect timestamp, message, and call path.
8. Correlate that timestamp with GC, CPU, locks, I/O, and request latency.
9. Check for exceptions repeating with the same stack trace.
10. Open the source code at the application frame to find the triggering condition.

Do not count exceptions by class alone. One class can appear in many different situations; the same class with different stack traces may indicate different root causes.

### Grouping by Class

Grouping by `thrownClass` helps identify the most common exception types. This is the first step to spotting:

- `NullPointerException` spiking after a deployment.
- `TimeoutException` appearing when an external service is slow.
- `IllegalArgumentException` increasing due to input data.
- `SQLException` increasing during a database issue.

### Grouping by Stack Trace

If many events share both the same class and the same stack trace, they likely originate from a repeated code path. Focus on the first frame belonging to application code, then inspect callers to understand the business flow.

### Correlating Timelines

Place exception events on the same timeline as:

- Request latency and error rate.
- GC pauses and allocation.
- Thread parking and monitor contention.
- Socket read/write.
- Deployments or configuration changes.
- Application and downstream service logs.

If exceptions spike at the same time as socket read timeouts, the root cause may lie in an external service rather than the code throwing `TimeoutException`.

## 9. Distinguishing Caught Exceptions from Request-Failing Exceptions

JFR exception events indicate that an exception was thrown, but do not by themselves determine whether it was handled successfully.

For example:

~~~java
try {
    Integer.parseInt(input);
} catch (NumberFormatException ex) {
    return Optional.empty();
}
~~~

The exception is still thrown and caught within the same method. It can appear in JFR even though the request is handled normally by design.

Meanwhile:

~~~java
try {
    paymentService.charge(order);
} catch (PaymentException ex) {
    throw new CheckoutFailedException(ex);
}
~~~

An initial exception may be wrapped and rethrown. A recording can show multiple events within the same handling chain. Do not count every event as a failed request.

### What Data Should You Correlate With?

| Source | Question Answered |
|---|---|
| JFR exception event | Which exception, at which stack trace, on which thread |
| Application log | How the handler processed or reported the error |
| HTTP metric | Whether the request returned an error status |
| Distributed trace | Which service/span the exception belonged to |
| Custom business event | Whether the business operation succeeded or failed |
| Counter/metric | Error rate by route or business type |

A good dashboard should distinguish exception volume from request failure rate. The two metrics may correlate, but they are not the same.

## 10. Recognizing Common Error Patterns

### Repeated Exceptions in a Loop

Signs:

- Same exception class.
- Same stack trace.
- Event count grows rapidly.
- CPU or allocation increases at the same time.

How to investigate:

- Look for unbounded loops or retries.
- Check whether exceptions are being used for normal control flow.
- Check retry delay, backoff, and maximum attempts.
- See whether the same invalid input is being processed repeatedly.

### NullPointerException After Deployment

Signs:

- NPE appears immediately after a release.
- Stack trace points to a new method or recently changed code path.
- Request error rate increases at the same time.

How to investigate:

- Identify the first frame belonging to application code.
- Check invariants and nullability of input data.
- Correlate with code/configuration changes.
- Add validation at system boundaries if needed.

### Increasing TimeoutException

Signs:

- `TimeoutException` appears alongside long socket reads or thread waits.
- Request latency increases.
- Connection pools or worker threads may be saturated.

How to investigate:

- Correlate with JFR I/O events.
- Check endpoints, timeouts, and retry policies.
- See whether threads are waiting on sockets, locks, or pools.
- Correlate with logs and metrics of dependent services.

### Overly Caught Exceptions

Signs:

- High exception event count but low HTTP error rate.
- Many stack traces end at the same catch handler.
- `ExceptionStatistics` increases rapidly.

How to investigate:

- Determine whether the exception represents a normal condition or an error signal.
- Replace control-flow branches with validation/return values where appropriate.
- Reduce repetitive stack trace logging.
- Add rate limits or metrics by error type.

### LinkageError or NoClassDefFoundError

Signs:

- `jdk.JavaErrorThrow` records linkage-related Errors.
- Stack trace points to class loading or method invocation.
- Errors appear after a deployment or dependency change.

How to investigate:

- Check classpath/module path.
- Compare dependency versions.
- Check class loaders and artifact packaging.
- Correlate runtime differences across environments.

## 11. ExceptionStatistics and Trend Measurement

`jdk.ExceptionStatistics` is useful when you want to observe the number of `Throwable` objects created per statistical interval.

Illustrative example:

| Time interval | throwables |
|---|---:|
| 10:00:00 | 12 |
| 10:00:01 | 14 |
| 10:00:02 | 180 |
| 10:00:03 | 205 |
| 10:00:04 | 22 |

A spike from 14 to 180 objects in one second can suggest a processing flow is creating exceptions at a high rate.

Keep in mind:

- This is the number of `Throwable` objects created, not necessarily unhandled exceptions.
- A `Throwable` object can be created without being thrown.
- Detailed exception events may be throttled.
- Do not add detailed event counts and `throwables` counts as if they were two independent sets.
- Compare the trend against request volume, workload, and error rate.

Use statistics to detect anomalous periods, then use events with stack traces to locate the code path.

## 12. Performance and Overhead of Exception Collection

Throwing an exception is typically more expensive than a normal conditional branch because the JVM must allocate an object and usually capture a stack trace. JFR adds the cost of writing the event, storing fields, and recording the stack trace.

The cost depends on:

- Exception frequency.
- Number of enabled events.
- Throttling.
- Whether stack traces are recorded.
- Recording size.
- Collection duration.
- Workload and JVM implementation.

Guidelines:

1. Start with the default template.
2. Record for a duration sufficient to reproduce the issue.
3. Use default throttling first.
4. Disable throttling only in short, controlled investigation windows.
5. Monitor CPU, recording size, and latency during collection.
6. Avoid recording stack traces for every custom event if not needed.
7. Stop the recording once enough data is collected.

JFR is designed for low-overhead profiling, but no configuration guarantees zero overhead. Measure on a representative workload before applying detailed configurations long-term.

## 13. Creating Custom Events for Business Errors

Standard events record the exception type and stack trace. When you need to know whether a business operation failed, create a custom event with standardized fields.

Examples of useful fields:

| Field | Meaning |
|---|---|
| operation | Business operation name |
| failureCode | Stable error code |
| exceptionType | Exception class name |
| retryable | Whether it can be retried |
| route | Route template, not a URL containing user data |

Do not record raw requests, access tokens, passwords, cookies, or full exception messages in custom events.

Custom events should be recorded at the boundary where the application knows the business outcome, such as in a catch handler or transaction coordinator. This lets the recording distinguish exceptions that occurred from operations that actually failed.

## 14. Java 17+ Example: Recording a Custom JFR Event When Catching an Exception

The following example intentionally throws three `IllegalArgumentException` instances, catches them, and records a custom `com.acme.OrderFailure` event for each failed handling.

Structure:

~~~text
project/
  src/
    com/acme/ExceptionEventDemo.java
  out/
~~~

File `src/com/acme/ExceptionEventDemo.java`:

~~~java
package com.acme;

import java.nio.file.Path;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class ExceptionEventDemo {

    @Name("com.acme.OrderFailure")
    @Label("Order Failure")
    @Category({"Acme", "Orders"})
    @Description("Records an order validation failure")
    static class OrderFailure extends Event {
        @Label("Operation")
        String operation;

        @Label("Failure Code")
        String failureCode;

        @Label("Exception Type")
        String exceptionType;

        @Label("Retryable")
        boolean retryable;
    }

    private static void validateOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("order-exceptions.jfr");
        int failures = 0;

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("order-exceptions");
            recording.enable(OrderFailure.class);
            recording.start();

            for (int i = 0; i < 3; i++) {
                try {
                    validateOrder("");
                } catch (IllegalArgumentException ex) {
                    OrderFailure event = new OrderFailure();

                    if (event.isEnabled()) {
                        event.operation = "validateOrder";
                        event.failureCode = "MISSING_ORDER_ID";
                        event.exceptionType = ex.getClass().getName();
                        event.retryable = false;
                        event.commit();
                    }

                    failures++;
                }
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("CAUGHT=" + failures);
        System.out.println("RECORDING=order-exceptions.jfr");
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 --add-modules jdk.jfr -d out src/com/acme/ExceptionEventDemo.java
~~~

Run:

~~~bash
java --add-modules jdk.jfr -cp out com.acme.ExceptionEventDemo
~~~

Exact stdout:

~~~text
CAUGHT=3
RECORDING=order-exceptions.jfr
~~~

The file `order-exceptions.jfr` is created in the working directory.

### Inspecting the Custom Event

View summary:

~~~bash
jfr summary order-exceptions.jfr
~~~

Print the custom event:

~~~bash
jfr print --events com.acme.OrderFailure order-exceptions.jfr
~~~

The recording contains three `com.acme.OrderFailure` events, each with `operation`, `failureCode`, `exceptionType`, and `retryable`.

This example records a stable error code instead of the raw message. This approach is helpful when messages might contain input data or private information.

## 15. Using Custom Duration Events for Error-Handling Time

An instant event indicates that an error occurred. If you need to measure the time spent handling or recovering from an error, you can create a duration event:

~~~java
RecoveryEvent event = new RecoveryEvent();
event.begin();

try {
    recoverFromFailure();
    event.succeeded = true;
} catch (RuntimeException ex) {
    event.succeeded = false;
    throw ex;
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

In this example, the duration spans the entire recovery interval. The `succeeded` field indicates the outcome.

Do not set a business event's duration to the lifetime of the exception object. Exception throw events and recovery events answer two different questions:

- Exception event: which exception occurred and on which code path?
- Recovery event: how long did the application take to handle or recover?

## 16. Filtering Events by Type and by Stack Trace

An effective analysis workflow is to filter the recording by event type:

~~~bash
jfr print --events jdk.JavaExceptionThrow exceptions.jfr
~~~

Then filter Errors:

~~~bash
jfr print --events jdk.JavaErrorThrow exceptions.jfr
~~~

If you need to inspect statistics:

~~~bash
jfr print --events jdk.ExceptionStatistics exceptions.jfr
~~~

In JMC, you can filter by event type and inspect individual records. When grouping by stack trace, normalize dynamic values in messages to avoid splitting a single bug into too many groups.

If the recording is large, export JSON and process events one by one instead of printing everything to the terminal:

~~~bash
jfr print --json --events jdk.JavaExceptionThrow exceptions.jfr
~~~

For automated pipelines, check metadata and JDK version. Do not assume fields or event settings are identical across all JDK releases.

## 17. Combining Exception Events with Other JVM Events

Exceptions are often the final symptom of another problem. Look at events occurring around the same time:

| Related event | What it can reveal |
|---|---|
| jdk.SocketRead / jdk.SocketWrite | Waiting on network or downstream services |
| jdk.FileRead / jdk.FileWrite | Slow file I/O |
| jdk.JavaMonitorEnter | Waiting on a synchronized monitor |
| jdk.ThreadPark | Thread parked or waiting |
| jdk.GarbageCollection | GC coinciding with the time of errors |
| jdk.ExecutionSample | CPU-consuming code paths |
| jdk.ClassLoad / jdk.ClassUnload | Class loading or dependency issues |

Examples:

- `TimeoutException` alongside long socket reads may point to network issues.
- `RejectedExecutionException` alongside thread pool saturation may point to queue or executor limits.
- `SQLException` alongside long connection wait times may point to database pool issues.
- `NoClassDefFoundError` alongside class loading events may point to packaging or classpath issues.

These are hypotheses to confirm with timelines and application data, not automatic conclusions from the exception name alone.

## 18. Protecting Data in Exception Recordings

Exception messages and stack traces can expose:

- Table names, SQL queries, or internal endpoints.
- File paths and directory structures.
- Class names, packages, and dependencies.
- User input embedded in messages.
- Account IDs, order IDs, or business data.
- Credentials if the application improperly includes secrets in messages.

Safeguards:

1. Collect only the events you need.
2. Do not record raw requests or access tokens in custom events.
3. Normalize messages and error codes.
4. Store recording files in directories with restricted access.
5. Encrypt at rest or in transit per organizational policy.
6. Limit retention.
7. Review recordings before sharing.
8. Scrub or exclude sensitive events when needed.
9. Record who collected the file and for what purpose.
10. Delete temporary copies once the investigation is complete.

Do not put full exception messages into metric labels. Dynamic values can cause very high cardinality and inadvertently leak data.

## 19. Troubleshooting Exception Events

| Symptom | Possible Cause | Resolution |
|---|---|---|
| JavaExceptionThrow not visible | Event disabled or older JDK uses a template with it disabled by default | Check `JFR.check`, `ActiveSetting`, and JFR version |
| Exceptions occur but event count is low | Throttle limits event rate | Check the `throttle` setting and `ExceptionStatistics` |
| Missing stack traces | `stackTrace=false` or recording settings do not enable it | Enable `stackTrace` for the event and re-collect |
| Only some exception classes appear | Recording covers only a window or events were throttled | Extend window appropriately and check rate limits |
| JavaErrorThrow misses OOME | Standard event may exclude `OutOfMemoryError` | Use JVM logs and `HeapDumpOnOutOfMemoryError` |
| Event appears but request succeeded | Exception was caught and handled | Correlate with application logs and business events |
| High exception count but few logs | Many exceptions caught internally or logs rate-limited | Group stack traces and inspect catch handlers |
| Empty message | Exception has no message or field was not recorded | Rely on `thrownClass` and `stackTrace` |
| JFR file too large | High exception volume or throttling disabled | Limit duration, enable throttling, and collect only needed events |
| ExceptionStatistics missing | Event disabled or absent in that template/JDK | Check `jfr metadata` and `ActiveSetting` |
| JMC cannot open recording | Incomplete file or incompatible JMC version | Run `jfr summary` and use a compatible JMC |
| Script miscounts events | Throttling, event schema, or JDK changes | Check metadata, version, and data limits |

## 20. Exception Investigation Workflow with JFR

1. Identify the symptom: failed requests, increased exception volume, or an Error appearing.
2. Confirm the JDK version and JFR template.
3. Check existing recordings with `jcmd PID JFR.check verbose=true`.
4. Enable `jdk.JavaExceptionThrow` and `jdk.JavaErrorThrow` if needed.
5. Keep the default throttle on the initial collection.
6. Start a short recording long enough to reproduce the incident.
7. Dump the file with `JFR.dump` or let the recording finish by duration.
8. Run `jfr summary` to inspect event counts.
9. Print `JavaExceptionThrow`, `JavaErrorThrow`, and `ExceptionStatistics` separately.
10. Group by `thrownClass` and stack trace.
11. Locate the first frame belonging to application code.
12. Correlate timestamps with logs, request metrics, traces, and other JVM events.
13. Determine whether the exception was caught, propagated, or caused a business failure.
14. If needed, add custom events at business boundaries.
15. Adjust throttle or stack settings only after evaluating overhead.
16. Record findings along with JDK version, recording settings, and collection time.
17. Secure recording files and apply retention policies once finished.

## 21. Key Takeaways

- `jdk.JavaExceptionThrow` records events related to exceptions in the `java.lang.Exception` hierarchy.
- `jdk.JavaErrorThrow` is for objects in the `java.lang.Error` hierarchy.
- `jdk.ExceptionStatistics` tracks `Throwable` objects created; it does not equate to failed requests.
- JFR events show timestamp, thread, `thrownClass`, `message`, and stack trace when those fields are enabled.
- An event does not by itself tell you whether an exception was caught, propagated, or caused a request failure.
- Starting in JDK 25, `JavaExceptionThrow` is enabled by default in the standard configuration and throttled at 100 events/second.
- When throttling is active, the recorded event count is not the actual total number of exceptions.
- Check `jfr metadata` and active settings before writing parsers.
- Use `jfr summary` and `jfr print --events` to inspect recordings.
- The JMC Event Browser helps filter and group events by class, thread, and stack trace.
- Combine exception events with logs, metrics, traces, and I/O, lock, and GC events to find root causes.
- Use custom JFR events to record business error codes and handling outcomes.
- Do not record raw requests, tokens, passwords, or unnecessary personal data in events.
- Keep recordings short and use reasonable throttling when investigating high exception volume.

## Official References

- [Troubleshoot Performance Issues Using Flight Recorder — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [JDK 25 Release Notes — JFR Exception Event Defaults](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)
- [jdk.jfr Package Summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Event API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [EventSettings API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)
