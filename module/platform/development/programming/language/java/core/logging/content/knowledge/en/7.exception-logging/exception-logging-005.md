# Unrecoverable Errors — Exception Logging in Java

## 1. What Does "Unrecoverable Error" Mean?

In a Java application, an **unrecoverable error at a given location** is a situation where the code at that location **has no reasonable way to continue or recover according to its contract**. The error can be propagated up to a higher layer so that layer can decide whether to abort the request, fail the task, refuse startup, or stop the process. **Exception logging** records evidence of the failure so operators can understand the root cause and scope of impact.

It is important to distinguish between concepts that are often conflated:

- **Cannot be handled at the current layer:** a method cannot recover, so it **rethrows or propagates the exception** to a layer that knows how to decide. The exception may still be handled properly elsewhere.
- **Unhandled exception:** an exception escapes an execution boundary without matching handling code. For the main thread, the JVM typically prints the stack trace and terminates that thread; for other threads, behavior depends on the execution environment and the uncaught-exception handler. Not every unhandled exception brings down the entire JVM.
- **Unrecoverable failure:** within the scope under consideration, there is no safe action to achieve the goal. Examples include missing required configuration at startup, inability to complete a transaction, or data state that has violated a critical invariant.

An HTTP request may **fail to be processed successfully**, yet the application can still **handle the failure** by rolling back, returning a 5xx response, logging at the boundary, and continuing to serve other requests. Therefore, "unable to process this unit of work" does **not by default** mean shutting down the entire process.

Example of an incident logged with context:

~~~text
SEVERE event=startup.failed component=database outcome=abort errorType=IllegalStateException
~~~

This is an **illustrative line**, not a fixed output of any logging library. The message should clearly state **what failed, what the impact is, and what the program decided to do**; the `Throwable`/stack trace information should be recorded using the appropriate logging API.

## 2. When Is an Error Truly Unrecoverable?

The decision point is the component's **scope of responsibility**. Ask: "Can this layer recover while still guaranteeing data correctness, API contract compliance, and system safety?"

| Situation | What can the layer do? | Typically appropriate logging |
| --- | --- | --- |
| User submits malformed data | Return a 4xx validation error with safe content | Not necessarily ERROR; may log info/metrics per policy |
| Cache is unavailable while the database still works | Fall back to the primary data source | Possibly WARNING with a fallback event code |
| External service times out and retries are allowed | Retry with limits, then report failure if needed | Log retry info selectively; do not emit a stack trace for every attempt |
| Money transfer command cannot commit | Roll back and report failure | Log once at the boundary with transaction context |
| Required configuration is missing at startup | Cannot initialize safely | Log SEVERE/ERROR and terminate startup with an error status |
| Internal invariant violated, state untrustworthy | Stop the task or isolate the component; stop the app if necessary | Log a critical error and preserve the cause |
| JVM is critically out of memory | Recovery and logging may be unreliable | Prioritize JVM monitoring and crash diagnostics; do not assume the logger will save the situation |

**Not every exception is an "unrecoverable error."** An expected business exception or a successful retry should not automatically become a critical incident alert. Conversely, swallowing an error that breaks an invariant just to keep the program "running" can make the situation worse.

## 3. Three Distinct Responsibilities: Detection, Propagation, and Recording

A healthy workflow typically looks like this:

~~~text
Lower layer detects error
         |
         v
Can it recover safely here?
     /               \
   Yes                No
    |                  |
Recover per       Propagate exception
contract          (preserve cause)
    |                  |
    v                  v
Continue      Request / job / main boundary
                       |
                       v
             Roll back / return error / stop safely
                       |
                       v
             Log once with full context
                       |
                       v
               Metrics / alerts if needed
~~~

Three responsibilities should be separated:

1. **Detection:** the lower layer recognizes that an operation failed—for example, a database connection cannot be opened.
2. **Propagation:** if that layer has no valid recovery plan, it should **rethrow the same exception** or wrap it in an appropriate exception **while preserving the cause**.
3. **Recording and decision:** the final layer—which has full context about the request, task, or startup—determines the failure outcome, writes the log, and executes the next policy step.

The practical rule is to **log at the boundary responsible for handling the failure and possessing sufficient context**, typically once per root cause. Not every system shares the same boundary: an HTTP framework might log exceptions automatically, whereas a worker processing scheduled jobs may need to log explicitly when a job fails.

### Why shouldn't you log in every `catch` block?

Suppose an operation flows through controller → service → repository. If all three layers call `logger.error(..., ex)` and then rethrow, the system can produce **three stack traces for a single error**. Log counts will exaggerate the number of incidents, search tools become noisy, and root-cause tracing becomes harder.

If the service layer **adds context and rethrows**, it can wrap the exception and let the boundary layer log it. If the service **successfully recovers**, a `WARNING` or `DEBUG` log may suffice, and the boundary never receives an exception. If the framework already logs the exception automatically, check its configuration before creating a duplicate record.

## 4. Logging Exceptions Properly: Preserving `Throwable` and `cause`

When an error is unrecoverable, a message like "An error occurred" is rarely sufficient. You should preserve:

- A stable **event code**: `event=order.failed`, `event=startup.failed`.
- **Scope:** service/component, operation, `requestId`/`traceId`, or `jobId` if safe.
- **Impact:** `outcome=failure`, `action=abort`, `action=rollback`, `action=reject`.
- **Technical cause:** exception type, cause chain, and stack trace when needed.
- **Bounded metadata:** `retryAttempt`, `dependency`, timing; avoid unnecessary data.

With standard Java **java.util.logging (JUL)**, the appropriate method is:

~~~java
// Illustrative snippet inside a class where LOGGER and variable ex are already declared.
LOGGER.log(java.util.logging.Level.SEVERE,
        "event=order.failed action=rollback",
        ex);
~~~

This is an **illustrative code snippet**, not a standalone program. The third argument is a **`Throwable`**. JUL stores the `Throwable` in **`LogRecord.getThrown()`** so that the formatter/handler can render the stack trace and cause chain.

By contrast:

~~~java
LOGGER.severe(ex.getMessage());
~~~

This call logs only the **message string**, without passing the `Throwable` object to the logger. If the exception message is missing or contains sensitive data, troubleshooting becomes difficult or may leak data.

One important note: **passing a `Throwable` to a `Logger` does not mean every formatter will print the stack trace**. A minimal formatter may print only the level and message; in production, configure a formatter/encoder that supports exceptions, with appropriate data masking and retention policies.

## 5. Preserving the Cause When Propagating

### 5.1. Rethrowing the same exception

When you cannot handle the error and do not need to change its type, you can rethrow it:

~~~java
try {
    saveTransaction();
} catch (java.io.IOException ex) {
    throw ex;
}
~~~

This is an **illustrative snippet** that assumes a `saveTransaction()` method and a matching `throws` signature at the call site. In practice, if a `catch` block only rethrows without doing anything else, you can usually omit the `catch` block altogether and let the exception propagate naturally.

### 5.2. Wrapping an exception while preserving `cause`

If you need to translate an infrastructure-layer exception into a component-boundary error:

~~~java
try {
    saveTransaction();
} catch (java.io.IOException ex) {
    throw new IllegalStateException(
            "Cannot complete transaction", ex);
}
~~~

**`new IllegalStateException(message, ex)`** preserves the original exception in the cause chain; when the stack trace is logged, investigators can see both the new error layer and the original source.

Avoid replacing it with:

~~~java
throw new IllegalStateException(ex.getMessage());
~~~

This drops the **cause**. Moreover, messages from underlying libraries or original exceptions sometimes contain sensitive data and must not be exposed verbatim in client-facing responses.

### 5.3. Is logging and rethrowing always wrong?

Not strictly. A layer might need to log because the event has **its own distinct meaning that upper boundaries will not record**—for example, an independent background task genuinely failed and the calling system only receives an aggregate failure count. However, for the same cause and context, there should be **one primary place responsible for logging** to avoid duplication. When logging in multiple places is unavoidable, each log should carry distinct additional information and a clear operational justification.

## 6. Runnable Java 17+ Example: Unable to Start Safely

Scenario: the application requires the **`DB_URL`** setting to be ready to serve. In this example, the check is hardcoded to simulate **missing required configuration**. The initialization method throws `IllegalStateException`; the `main` layer catches the error, logs **`SEVERE`** once, flushes the log, and exits with **exit code 1**.

The example intentionally avoids reading the real environment so the output is always deterministic. It uses JUL built into the JDK, requiring no external dependencies.

Create the file **`CriticalStartupDemo.java`**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class CriticalStartupDemo {
    private static final Logger LOGGER =
            Logger.getLogger(CriticalStartupDemo.class.getName());

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                Throwable cause = record.getThrown();
                String detail = (cause == null)
                        ? ""
                        : " | " + cause.getClass().getSimpleName()
                                + ": " + cause.getMessage();

                return record.getLevel().getName() + " | "
                        + formatMessage(record) + detail
                        + System.lineSeparator();
            }
        });
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        try {
            initializeRequiredConfiguration();
            System.out.println("APP_READY");
        } catch (IllegalStateException ex) {
            LOGGER.log(Level.SEVERE,
                    "event=startup.failed component=config outcome=abort",
                    ex);

            // Ensure StreamHandler flushes logs before exiting.
            stdout.flush();
            System.exit(1);
        }
    }

    private static void initializeRequiredConfiguration() {
        // Simulate a deterministic error so the example produces deterministic output.
        throw new IllegalStateException(
                "Required setting DB_URL is missing");
    }
}
~~~

Compile with **JDK 17 or later** and run in the terminal:

~~~bash
javac -encoding UTF-8 CriticalStartupDemo.java
java CriticalStartupDemo
~~~

**Exact stdout** of this program:

~~~text
SEVERE | event=startup.failed component=config outcome=abort | IllegalStateException: Required setting DB_URL is missing
~~~

The program exits with **exit code 1**. To inspect the exit code in bash immediately after the `java` command, run:

~~~bash
echo $?
~~~

The output of that shell command is:

~~~text
1
~~~

In PowerShell, you can inspect the exit code using **`$LASTEXITCODE`** after running `java`; this is a value provided by the shell, **not a log line printed by Java**. If testing with a script that has fail-fast mode enabled on command failure, use the exit-code capture mechanism appropriate for that script.

Code explanation:

1. **`initializeRequiredConfiguration()`** signals that a required condition cannot be met by throwing `IllegalStateException`. It does not log anything itself, avoiding duplicate records.
2. The **`main`** layer is the startup boundary. It cannot announce `APP_READY`; instead, it catches the error and logs the **`startup.failed`** event.
3. **`LOGGER.log(Level.SEVERE, message, ex)`** passes the full exception object. In JUL, the `Throwable` is attached to the `LogRecord`; **the event itself still preserves the cause**.
4. The custom `Formatter` is kept simple and prints only the **exception type and message** so stdout stays consistent; **it does not print the full stack trace**. In production deployments, use a formatter/encoder that outputs stack traces or appropriate diagnostic mechanisms as needed.
5. **`setUseParentHandlers(false)`** prevents parent loggers from printing the same record under a different configuration; **`StreamHandler(System.out, ...)`** explicitly writes to stdout. JUL's default `ConsoleHandler` typically writes to **stderr**.
6. **`stdout.flush()`** flushes buffered logs before `System.exit(1)`. In real systems, even flushing does not guarantee that a remote log collector has received and durably stored the log.
7. **`System.exit(1)`** expresses the **entry point's** policy for required startup failures. Do not call `System.exit` from libraries, repositories, or HTTP handlers; those layers must propagate errors to the orchestrating layer.

### What if you want to see the full stack trace?

You can let JUL's **`java.util.logging.SimpleFormatter`** format the `LogRecord` and `Throwable`, or configure your framework's formatter/encoder to output the exception field and stack trace. Timing, line placement, and stack trace formatting can vary across environments, so the example above uses a compact formatter to demonstrate exact output.

An unrecoverable error at the startup boundary also typically requires cleaning up resources, releasing open connections, and reporting an unready status to the orchestration platform. Using a non-zero exit code signals to external systems that process startup failed.

## 7. Error-Handling Boundaries in a Java Application

Not every error should stop the JVM. Choose where to log and act based on the **failing unit of work**.

### 7.1. HTTP request

Suppose a service throws an exception because the database is unavailable. The **exception handler at the HTTP boundary** can:

- Complete rollback if the transaction needs to be aborted per configuration/framework.
- Return an appropriate HTTP status such as 500 or 503 with safe content for the client.
- Log one error record with sufficient context, if the framework has not already done so.
- Increment error counters/record metrics; other independent requests can continue.

Do not return stack traces, passwords, or internal exception details directly to the client. A **500** status does not mean the JVM must be shut down. Conversely, if the entire process state is no longer trustworthy, you may need to stop accepting requests and let the orchestrator replace the instance.

### 7.2. Scheduled job or batch

A task that fails after exhausting its allowed retries can be logged as:

~~~text
ERROR event=job.failed jobType=sync-catalog jobId=job-52 attempts=3 outcome=failure
~~~

This is an illustrative line. The scheduler/worker layer decides whether to update the job status, retry, or move it to a dead-letter queue. Do not let an exception be swallowed so that the job is marked successful. Also, avoid logging a separate stack trace for every retry if a consolidated summary at final failure is sufficient.

### 7.3. Main/startup

When required configuration or dependencies are missing, the entry point should log the cause and report failure externally via a non-zero exit code or the appropriate health/readiness mechanism. **Never print "ready" if initialization has failed.**

### 7.4. Library or repository layer

Lower layers usually do not know whether to stop the application, which HTTP status to return, or how many times to retry. They should throw semantically appropriate exceptions with the full cause preserved, and log only if the layer itself genuinely handles the issue or has unique operational context that cannot be reconstructed higher up.

## 8. Uncaught Exceptions in Threads, `Future`, and `CompletableFuture`

In Java, **where an exception is thrown determines who can handle and log it**. The examples below are **illustrative snippets requiring surrounding context/classes**, not standalone programs.

### 8.1. Plain `Thread`

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Worker failed");
});
worker.setUncaughtExceptionHandler((thread, error) ->
        LOGGER.log(java.util.logging.Level.SEVERE,
                "event=worker.uncaught thread=" + thread.getName(),
                error));
worker.start();
~~~

An uncaught exception in that thread can reach **`UncaughtExceptionHandler`**. It will not be caught by a `try/catch` in the thread that called `worker.start()`. When configuring a handler, be careful about what data is logged, the task's state, and the stop/restart policy.

### 8.2. `ExecutorService.submit` and `Future.get`

~~~java
java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newSingleThreadExecutor();
try {
    java.util.concurrent.Future<?> future = pool.submit(() -> {
        throw new IllegalStateException("Job failed");
    });
    future.get();
} catch (java.util.concurrent.ExecutionException ex) {
    LOGGER.log(java.util.logging.Level.SEVERE,
            "event=async.job.failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    LOGGER.log(java.util.logging.Level.WARNING,
            "event=async.job.interrupted", ex);
} finally {
    pool.shutdown();
}
~~~

**`submit(...)`** typically stores the task's failure inside the **`Future`**, and **`get()`** reports it via `ExecutionException`; at that point **`ex.getCause()`** is the task's original exception. Do not assume an uncaught-exception handler on a worker thread will always catch errors from tasks submitted with `submit(...)`. If the `Future` is never observed, errors can be silently ignored at the orchestration layer.

When catching **`InterruptedException`**, **restore the interrupt flag** if the method decides not to rethrow, and follow the task's cancellation policy. Do not mechanically treat a cancellation request as a "critical error."

### 8.3. `CompletableFuture`

~~~java
java.util.concurrent.CompletableFuture<String> future =
        java.util.concurrent.CompletableFuture.supplyAsync(() -> {
            throw new IllegalStateException("Remote call failed");
        });

future.whenComplete((value, error) -> {
    if (error != null) {
        LOGGER.log(java.util.logging.Level.SEVERE,
                "event=async.operation.failed", error);
    }
});
~~~

A **`CompletableFuture`** can complete **exceptionally**; the `whenComplete` callback receives the error if the result failed. The error may be wrapped in a `CompletionException` or another wrapper depending on the execution path. A project should standardize which boundary is responsible for logging so it does not log both in the callback and at the `join()`/`get()` call site.

### 8.4. Avoid `catch (Throwable)` everywhere

Both **`Exception`** and **`Error`** extend `Throwable`, but many **`Error`** types (such as certain critical JVM errors) are not recoverable like normal business failures. Do not use `catch (Throwable)` to swallow everything and keep running in an unsafe state.

With **`OutOfMemoryError`**, the system may lack sufficient resources to allocate strings, build stack traces, or send logs. Relying solely on the logger in that situation is risky; have appropriate metrics, JVM flags, and external crash/health diagnostics in place.

## 9. Choosing a Log Level for Unrecoverable Errors

The log level should reflect the **impact and expectedness** of the error, not merely whether it is a checked or unchecked exception.

| Situation | Typical level to consider | Why |
| --- | --- | --- |
| Missing required config prevents app startup | SEVERE (JUL) / ERROR | Incident affects availability |
| Request fails due to unrecoverable infrastructure error | SEVERE / ERROR | Critical operation failed |
| Fallback from cache to database succeeds | WARNING or INFO | Abnormal condition, but system recovered |
| Invalid user input, returning 400 intentionally | May not need ERROR | This can be an expected business outcome |
| One retry fails and the next succeeds | DEBUG or WARNING per policy | Avoid alerting on an already-recovered error |
| A job fails completely after allowed retries | ERROR/SEVERE at job boundary | Final outcome of the unit of work is failure |

JUL has **`Level.SEVERE`** and **`Level.WARNING`**, not `Level.ERROR`. With **SLF4J**, the syntax is typically **`logger.error("...", exception)`**. In JUL it is **`logger.log(Level.SEVERE, "...", exception)`**; do not copy API names verbatim between libraries.

Whether every failure is critical in its *own context* depends on the system. An application receiving lots of invalid input should not trigger production alerts for every validation error as if it were an infrastructure failure.

## 10. Logging Errors So They Can Be Searched and Correlated

Suppose there are many concurrent payment requests. A context-free message:

~~~text
ERROR Something failed
~~~

makes it hard to determine the scope. A better message:

~~~text
ERROR service=payment event=payment.failed requestId=req-84 orderId=ORD-25 dependency=bank-gateway errorCode=PAYMENT_TIMEOUT outcome=failure
~~~

The line above is an illustrative example, not the output of the program in Section 6.

**`requestId`/`traceId`** helps find all logs for the same request; **`event`** and **`errorCode`** help group issues; **`dependency`** helps isolate the failing component. In many systems, structured logging/JSON can be used so fields are queried accurately instead of relying solely on free-form text concatenation.

Key principles:

- Use **stable event names** such as `startup.failed`, `job.failed`, `payment.failed`.
- **Do not embed individual IDs in the event name**, so event grouping stays consistent.
- Describe the **impact** and **action**: `retry exhausted`, `rollback`, `request rejected`, `startup aborted`.
- If a `Throwable` is present, pass the exception to the logging API and verify that the formatter/encoder actually stores the stack trace appropriately.
- **Never put request bodies, access tokens, session cookies, API keys, passwords, payment details, or sensitive personal data** into raw logs; exception messages and stack traces must also be controlled.

## 11. Logs, Metrics, and Alerts for Unrecoverable Errors

**Logs** tell you which error occurred, at which step, for which request/job, and with what cause for investigation. **Metrics** answer how many requests failed, the error rate, how many jobs failed, or the impact over time. **Tracing** reveals the flow across multiple services.

A single `SEVERE` error may be noteworthy, but it is not enough to prove the entire system is degraded. Conversely, thousands of identical error lines may indicate a recurring incident requiring an alert based on a consistent rate or condition.

Example:

~~~text
log:     event=payment.failed requestId=req-84 errorCode=PAYMENT_TIMEOUT
metric:  payment_failures_total{reason="timeout"} 125
~~~

Illustrative data. Specific metric names and labels depend on the deployed system. **Do not attach unique `requestId` or `orderId` values as metric labels**, as that creates huge numbers of distinct time series (*high cardinality*). Detailed IDs belong in logs/traces, whereas metrics use labels with a bounded set of values.

If a log source is filtered or fails to ship, **a missing log line does not prove the code did not run**. During investigation, cross-check actual state, metrics, traces, and business data.

## 12. Handling Resources and State on Failure

Logging is observability; **it does not replace rollback, resource cleanup, or application correctness**.

- For connections/files, prefer **try-with-resources** so resources are released when an exception occurs.
- For transactions, have an explicit **rollback/commit** policy; a successful log entry does not mean the transaction was rolled back.
- For retries, retry only when the operation is safe, control attempt counts and backoff delays, and consider idempotency to avoid repeated side effects.
- For requests that cannot be processed, return a clear and safe error response; avoid returning the raw `Throwable`/stack trace to the client.
- For failed startups, do not report readiness as healthy; exit or let the orchestrator replace the instance as needed.
- For asynchronous applications, update the job status to **failed** and propagate the error to monitoring rather than exiting normally as if it succeeded.

Additionally, logging excessive stack traces can create heavy load. Do not disable important diagnostic information just to save storage, but choose the right logging boundary, limit pointless repetition, and configure retention per operational requirements.

## 13. Common Programming Mistakes

| Mistake | Consequence | Appropriate approach |
| --- | --- | --- |
| `catch(Exception)` and ignore | Work fails while the program reports success | Handle it properly or propagate it to the boundary |
| Log the error at every layer and rethrow | Multiple duplicate stack traces for one incident | Choose one boundary responsible for logging |
| Log only `ex.getMessage()` | Loses `Throwable`/cause and stack trace | Pass the `Throwable` to the logging API |
| Wrap an exception without passing `cause` | Loses the path to the original root cause | Use a constructor that accepts `cause` |
| Call `logger.severe` and continue despite invalid state | Invariant violation or cascading failure | Stop or isolate the task per policy |
| Log every validation error as `SEVERE` | Creates false alarms and log noise | Distinguish expected errors from infrastructure failures |
| Log sensitive data in messages/exceptions | Data leaks through centralized logs | Keep only necessary fields and mask sensitive data |
| Assume `System.exit` always flushes remote logs | Buffered or unreceived records may be lost | Flush appropriately and use out-of-process observability |
| Catch `Throwable` and try to continue on critical JVM errors | System state may no longer be trustworthy | Use fail-fast / appropriate JVM monitoring |
| Ignore failed `Future`/`CompletableFuture` | Background task failures are not reported properly | Observe results and define a clear handling boundary |
| Catch `InterruptedException` and ignore it | Task cancellation becomes ineffective | Propagate or restore the interrupt flag |

## 14. Self-Check Questions

**Question 1.** A repository throws `IOException` and the service has no valid way to recover. Must the service log `ERROR` before rethrowing?

**Answer:** No. If the boundary layer will write one complete log entry, the service can let the exception propagate or wrap it with `cause` to add context. This avoids duplicate logs for the same failure.

**Question 2.** A request encounters an unrecoverable error and returns 500. Is it mandatory to shut down the entire JVM?

**Answer:** No. The HTTP boundary can roll back and return 500 for that request while other requests continue. Only stop the instance when system state or operational policy genuinely requires it.

**Question 3.** What is the difference between `LOGGER.severe(ex.getMessage())` and `LOGGER.log(Level.SEVERE, "event=...", ex)`?

**Answer:** The second form preserves the `Throwable` object in the `LogRecord` so the formatter/encoder can print the stack trace and cause chain. The first form passes only a string.

**Question 4.** Why is catching `IOException` and doing `throw new IllegalStateException(ex.getMessage())` poor practice?

**Answer:** It loses the `cause`. Use **`new IllegalStateException("Context description", ex)`** to preserve the original exception.

**Question 5.** A task submitted via `ExecutorService.submit` throws a `RuntimeException`. Will a `try/catch` around the `submit` call reliably catch that exception?

**Answer:** No. The error is stored in the `Future`; when calling **`get()`**, the caller can receive **`ExecutionException`** and access the cause. Task results must be observed at the appropriate boundary.

**Question 6.** The logger was called at `SEVERE`, yet no stack trace appears. Did JUL drop the `Throwable`?

**Answer:** Not necessarily. The formatter or handler may not be rendering `record.getThrown()`. Check the output configuration; the runnable Java example in Section 6 intentionally prints only the exception type and message.

**Question 7.** Why should a program that fails to start return a non-zero exit code?

**Answer:** So that the shell, service manager, or orchestrator knows startup failed. Simply logging a `SEVERE` line while exiting with code 0 can mislead external tools into thinking startup succeeded.

**Remember:** When a Java layer **cannot handle an error safely**, **preserve the exception/cause and propagate it to the appropriate boundary**. That boundary is responsible for **rolling back or isolating the work, logging once with full context, reporting the failure outcome accurately, and deciding whether the process must stop**. Logging aids diagnosis, while proper error handling determines application safety.
