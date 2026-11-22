# Logging in the Java Application Lifecycle

## 1. Goal: Seeing How the Application Transitions Between States

**Application lifecycle logs** are records that show how far the application has progressed during startup, when it is eligible to accept work, what it is currently processing, at which step it encountered an error or degradation, and how it shut down. This is a chronological stream of events; a simple “started” message is not enough to determine whether a service is **ready to serve**.

When reading logs, operators need to be able to answer: which run instance produced the event, in which phase the event occurred, what the outcome was, where an error originated, and what happened next. Logs support diagnosis; health/readiness states, metrics, and traces still play their own distinct roles.

A common lifecycle looks like this:

```text
PROCESS_START
   → BOOTSTRAP/STARTING
   → INITIALIZING
   → READY
   → RUNNING (accepting and processing multiple tasks)
   → STOPPING (stop accepting new work, finish in-flight work)
   → STOPPED
```

Other branches exist as well: `STARTING → FAILED`, `RUNNING → DEGRADED → RECOVERED`, `RUNNING → FAILED`. Not every application goes through every state. If a process is terminated abruptly, `STOPPING`/`STOPPED` logs may not exist at all.

## 2. Placing Logs at Lifecycle Milestones

| Phase | Events to Log | What You Need to Read |
| --- | --- | --- |
| Bootstrap | `app.start`, `logging.configured` if applicable | Version, service name, environment, initial state; configured log destinations and levels |
| Initialization | `component.init.start`, `component.init.end`, `component.init.failed` | Which component is being created, how long it took, whether it blocks startup |
| Ready | `app.ready` | Essential prerequisites are met; from this point on the service can accept work |
| Running | `request.begin`, `request.end`, `job.start`, `job.finish` | Correlation ID, outcome, duration, error if any |
| Degradation/Recovery | `dependency.unavailable`, `retry.scheduled`, `dependency.recovered` | Which dependency failed, impact, retry behavior, whether it has recovered |
| Graceful Shutdown | `app.stopping`, `drain.completed`, `resource.closed`, `app.stopped` | Stopped accepting work, completed in-flight work, released resources, and flushed logs |
| Error Shutdown | `app.failed`, `app.stop_failed` while still able to log | Final cause, exception, phase where the failure occurred; do not claim a clean shutdown |

### 2.1. Bootstrap and STARTING

Configure the logger, log levels, handlers/appenders, format, output destinations, and log rotation policy **as early as possible**. Logs emitted before logging configuration is complete may go to a default destination, use a different format, or lack contextual information. Therefore, if a bootstrap logger is used, you must clearly define where early logs go and how handoff to the main configuration works.

At `app.start`, log *safe* identifying information: `service`, `version` or build ID, `environment`, `instanceId`, and `event`. Do not print all environment variables, passwords, tokens, connection strings, or configuration files, as they may contain secrets. If loading configuration fails, log the relevant key/component name and an appropriate reason, without logging sensitive values.

During the `INITIALIZING` phase, only log details for steps that help diagnose why startup is slow or failing: creating connection pools, loading required caches, applying configuration, and checking essential dependencies. For unrecoverable errors, log `component.init.failed` and `app.failed` at the boundary responsible for terminating the process; avoid repeating the same stack trace at every call layer.

### 2.2. READY Is Different from “main Has Run”

`READY` is an **application-level commitment** that essential prerequisites are satisfied: configuration is valid, required resources are operational, and the service is ready to process work. An open HTTP port or `main()` returning from an initialization call is not enough to infer readiness. For services with a readiness endpoint, only turn on the ready state when those conditions are genuinely met.

If the application is not ready yet, do not log `app.ready` just to “make the logs look clean.” If startup fails, log the failed state and the reason. It is good practice to have both `app.start` and `app.ready` milestones to measure startup time; measure durations using a monotonic clock such as `System.nanoTime()`, while using wall-clock timestamps to correlate events across systems.

### 2.3. RUNNING: Tying Each Unit of Work to the Lifecycle

When processing a request/job, log at least **one final outcome** at the responsible boundary: success or failure, an appropriate business/error code, and duration. Log `begin` when tracking the start time is genuinely useful. For example:

```text
INFO  event=request.begin requestId=req-42 operation=createOrder
INFO  event=request.end   requestId=req-42 operation=createOrder outcome=success durationMs=18
```

Having both lines share the same `requestId` helps stitch the journey together, though each request must have its own unique ID. If distributed tracing is available, prefer `traceId`/`spanId` to span across multiple services. For asynchronous processing or thread switches, correlation context must be propagated with the work; do not assume `ThreadLocal` automatically transfers to a new executor or thread. In applications using SLF4J with a backend that supports MDC, you can put the ID into MDC for the scope of the request and then **clear/restore the context** in a `finally` block so reused threads do not retain stale IDs. MDC is not a built-in feature of `java.util.logging` (JUL).

Do not log every minor step at `INFO` or dump verbatim requests/responses. A successful request usually only needs a summary record; detailed logs for investigation belong at `FINE`/DEBUG and must have their volume controlled. Avoid logging personal data, access keys, and sensitive payloads.

### 2.4. DEGRADED, RETRY, and RECOVERED

A temporarily unavailable dependency does not necessarily mean the entire application must stop. Distinguish between:

- **Per-attempt errors:** log with the dependency code/name, retry attempt, and backoff policy; do not generate thousands of identical stack traces.
- **Transition to degraded state:** log a single `dependency.unavailable` or `app.degraded` event for the state transition, along with its impact.
- **Recovery:** log `dependency.recovered` or `app.recovered`, including the outage duration if measurable.

The log level depends on the impact: expected retries can be at `FINE` or `WARNING`; losing a mandatory dependency that prevents accepting work may warrant `SEVERE`. Logging state-transition events is much easier to follow than spamming every retry loop.

### 2.5. STOPPING and STOPPED

A controlled shutdown usually follows this sequence: detect shutdown signal → **stop accepting new work** → wait for or cancel in-flight work according to a timeout → close connections and resources → log the shutdown outcome → flush log buffers. If closing resources fails, log `app.stop_failed` with the reason; do not log `app.stopped` as if everything succeeded.

`try/finally` helps close resources when an execution flow leaves a scope; a **JVM shutdown hook** is a different mechanism used when the JVM shuts down normally or receives a handled termination signal. Hooks are not guaranteed to run on `SIGKILL`, `Runtime.halt()`, power loss, or a severe JVM crash. Hooks should be short, have bounded wait times, avoid deadlocks, and must not be treated as a guarantee that final logs will be written. Asynchronous loggers need to be drained/flushed according to their backend documentation; a process killed abruptly can lose logs still sitting in buffers.

## 3. Designing the Content of a Log Event

A useful production log record typically includes:

| Field | Meaning |
| --- | --- |
| `timestamp`, `level` | When the event occurred and its severity level |
| `service`, `version`, `instanceId` | Which process/version emitted it |
| `event`, `state` | Stable event type and lifecycle state |
| `requestId` or `traceId` | Correlates lines belonging to the same task or trace |
| `outcome`, `durationMs` | Result and time cost when applicable |
| `errorType`, `errorCode`, exception | Failure diagnosis; stack trace when needed |

Keep `event` stable for filtering and building dashboards; put variable details in separate fields. JSON-formatted logs are convenient for centralized logging systems; structured text logs remain useful when there is a clear way to parse them. Timestamps and levels can be added automatically by the backend, so there is no need to concatenate them manually into every message. Ensure system clocks are synchronized for cross-machine correlation, and measure durations with a monotonic time source so they are unaffected by wall-clock adjustments.

With JUL, commonly used levels are `SEVERE` (critical errors), `WARNING` (risks or recoverable errors), `INFO` (lifecycle milestones), `CONFIG`, `FINE`, `FINER`, `FINEST` (increasingly detailed information). **Both the logger and the handler filter by level**: if the logger allows `FINE` but the handler only accepts `INFO` and above, `FINE` records will still not appear. Other frameworks may use ERROR/WARN/INFO/DEBUG/TRACE; do not assume level names are completely identical across libraries.

## 4. Standalone Java 17 Example Using java.util.logging

This example creates a successful run that emits `STARTING → READY → RUNNING → STOPPING → STOPPED`. It uses JUL built into the JDK; a compact formatter keeps output consistent and preserves stack traces when an exception occurs. The handler writes to **stdout** and flushes on every event for easy observation in the example; in production, use centralized handler/backend configuration rather than manually creating ad-hoc handlers.

Save with the exact filename `AppLifecycleLoggingDemo.java`:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class AppLifecycleLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(AppLifecycleLoggingDemo.class.getName());

    public static void main(String[] args) {
        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder text = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" ")
                        .append(formatMessage(record))
                        .append(System.lineSeparator());
                if (record.getThrown() != null) {
                    StringWriter stack = new StringWriter();
                    record.getThrown().printStackTrace(new PrintWriter(stack));
                    text.append(stack);
                }
                return text.toString();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(output);

        try {
            LOG.info("event=app.start state=STARTING");
            initialize();
            LOG.info("event=app.ready state=READY");
            processRequest("req-001");
        } catch (RuntimeException e) {
            LOG.log(Level.SEVERE, "event=app.failed state=FAILED", e);
        } finally {
            LOG.info("event=app.stopping state=STOPPING");
            try {
                closeResources();
                LOG.info("event=app.stopped state=STOPPED");
            } catch (RuntimeException e) {
                LOG.log(Level.SEVERE,
                        "event=app.stop_failed state=FAILED", e);
            } finally {
                output.flush();
                LOG.removeHandler(output);
            }
        }
    }

    private static void initialize() {
        // Example: validate configuration, open required connections.
    }

    private static void processRequest(String requestId) {
        LOG.info("event=request.begin requestId=" + requestId);
        try {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException("requestId is blank");
            }
            LOG.info("event=request.end requestId=" + requestId
                    + " outcome=success");
        } catch (RuntimeException e) {
            LOG.log(Level.SEVERE,
                    "event=request.end requestId=" + requestId
                    + " outcome=failed", e);
            throw e;
        }
    }

    private static void closeResources() {
        // Example: stop accepting requests, wait for jobs, close connections/pools.
    }
}
```

Compile and run from the directory containing the file:

```bash
javac AppLifecycleLoggingDemo.java
java AppLifecycleLoggingDemo
```

**stdout when running the example properly:**

```text
INFO event=app.start state=STARTING
INFO event=app.ready state=READY
INFO event=request.begin requestId=req-001
INFO event=request.end requestId=req-001 outcome=success
INFO event=app.stopping state=STOPPING
INFO event=app.stopped state=STOPPED
```

Explanation: `initialize()` completes before emitting `app.ready`; request `req-001` has both `begin` and `end`; `finally` executes the shutdown branch even if processing inside throws a `RuntimeException`. `setUseParentHandlers(false)` prevents records from being printed twice by the default console handler; `setLevel` on both the logger and the handler allows the events to be recorded. The formatter includes the stack trace in the log when `LogRecord.getThrown()` is non-`null`. In real code, `initialize()` and `closeResources()` must have corresponding implementations and timeout policies.

This example focuses on event ordering. It has no HTTP listener loop, does not register a shutdown hook, and does not measure duration. For long-running services, the `STOPPING` milestone should be tied to actual shutdown signals; do not assume `main`'s `finally` block represents every kind of JVM termination. If startup fails critically, a real application needs to exit with a non-zero exit code / mark health as failed at the startup boundary; **merely logging `SEVERE` and exiting with a success code can mislead monitoring systems**.

## 5. Reading a Log Sequence to Find Errors

Suppose a system stops accepting requests after deployment:

```text
INFO    event=app.start state=STARTING version=2.4.0
INFO    event=component.init.start component=database
SEVERE  event=component.init.failed component=database errorType=ConnectException
SEVERE  event=app.failed state=FAILED
INFO    event=app.stopping state=STOPPING
INFO    event=app.stopped state=STOPPED
```

This sequence shows the process **never reached READY**; the failure occurred during database initialization, not while handling a request. `STOPPED` only indicates that cleanup finished—it does not mean the run succeeded. When a system is already serving and a dependency becomes intermittent, look for `DEGRADED`/`RECOVERED` transition events and correlate the `requestId`/`traceId` of failed requests during that window.

Keep in mind that **a missing log does not prove an event did not happen**: logs can be filtered by level, unflushed, lost in transit, or never created due to an abrupt process termination. Combine logs with exit codes, health checks, metrics, traces, and deployment data when drawing conclusions.

## 6. Common Implementation Mistakes

1. **Logging READY too early:** the program has bound its port but has not checked mandatory dependencies. Only log READY and enable readiness when the service can genuinely accept work.
2. **No completion point for a task:** having only `request.begin` makes it hard to tell whether a request hung or finished. Log `request.end`/`request.failed` at the responsible boundary, including on error paths.
3. **Repeating the same exception across multiple layers:** a single error logged at `SEVERE` in the repository, service, and controller distorts the perceived incident count. The layer responsible for handling/exiting should log it in full; lower layers can add context and rethrow.
4. **Losing correlation in asynchronous execution:** a job switches threads without propagating `traceId`/`requestId`. Propagate context explicitly and clean it up after processing.
5. **Relying solely on STOPPED/hooks:** forced termination can lose final logs. Monitor process state, exit codes, and health independently.
6. **Leaving secrets in startup/error logs:** configuration, URIs, and exception messages can contain tokens or passwords. Mask or strip those fields before logging and control access/retention.
7. **Logging too much at INFO or failing to flush:** logs get flooded by retries/detailed requests or lost in buffers during an incident. Choose appropriate levels, sampling/rate limits, and flushing mechanisms.
8. **Confusing events with metrics:** a `durationMs=...` line helps investigate a single request; histograms and alerts require a proper metrics system.

## 7. Checklist for Designing Lifecycle-Based Logging

- Identify the application's actual states and the state transitions that must be logged; place `app.ready` after readiness conditions are met.
- Log service name/version, stable event names, state, and correlation IDs; measure duration where the work is owned.
- Cover success, startup failure, degradation/recovery, and shutdown; log error causes at the right boundary and keep stack traces when needed.
- On shutdown, stop accepting new work, finish or cancel in-flight work, close resources, report cleanup results, and flush logs as far as possible.
- Verify logger/handler level filtering, actual output, secret masking, retention rules, and log–trace–metric correlation.
- Test at least four scenarios: successful startup, failed startup, failed request, and graceful shutdown; simulate a crash to understand what logs may be missing.

The key takeaway is that **logs must accurately reflect state transitions and processing outcomes**, allowing you to reconstruct the lifecycle of each application session without guessing from a single “started” or “stopped” line.
