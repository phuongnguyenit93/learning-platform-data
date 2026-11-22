# Log Levels in Development Environments — Java Core Logging

## Objectives and Scope

When developing a Java application, logs need to show where the execution flow went, which decision was chosen, at which step an error occurred, and the final outcome of an operation. Log levels let you control the verbosity of these records without modifying individual log statements every time you investigate an issue.

After this lesson, you will be able to choose appropriate levels in a development environment; understand why both the logger and the handler affect whether logs are displayed; enable debug information for the right package or class; run a Java 17+ program to compare INFO with FINE; and manage security and performance when increasing verbosity.

This lesson belongs to the **Log level** group and focuses on **log levels in development environments**. The main example uses the JDK's built-in **java.util.logging (JUL)** API. Other frameworks such as SLF4J with Logback or Log4j 2 are mentioned to avoid confusion about how levels are configured.

## 1. How Do Log Levels Help During Development?

An order-processing flow can involve many steps: receiving a request, checking the cart, checking the cache, selecting a discount rule, calling a dependency, retrying, and returning a result. When you only need to confirm that the business operation completed, you usually do not need to see every step. When there is a pricing bug, those intermediate steps become critical.

Example scenario:

~~~text
INFO    event=checkout.started requestId=req-17
FINE    event=cart.checked requestId=req-17 items=3
FINE    event=discount.rule_selected requestId=req-17 rule=WELCOME
FINEST  event=discount.expression_step requestId=req-17 index=4
WARNING event=inventory.retry requestId=req-17 attempt=2
INFO    event=checkout.completed requestId=req-17 status=200
~~~

This is an illustrative sequence, not the output of the hands-on program below. At the INFO threshold, a developer sees the request start, a retry, and the final outcome. At FINE, two additional lines explaining internal decisions are shown. At FINEST, the system can emit a large amount of step-by-step detail, which is only useful when reproducing a narrow issue.

**Log levels do not change the application's business logic.** Changing a threshold only changes which records are accepted and emitted. A WARNING may be a retry that recovered; the request in the example still succeeded with status=200. Conversely, a log call at INFO does not necessarily mean the system is healthy; you must inspect the actual content and outcome.

In development, the right question is not "how do I print everything?" but "which records do I need to distinguish between two hypotheses?" Increasing verbosity at the right spot saves search time and prevents flooding the console.

## 2. Log Level Ordering in JUL

In **java.util.logging**, the severity/verbosity order is typically viewed from top to bottom as follows:

| JUL Level | Typical Meaning | Development Usage |
| --- | --- | --- |
| SEVERE | Serious failure preventing an operation or component from completing properly | Loss of functionality, with exception and context for investigation |
| WARNING | Notable anomaly; may still recover | Unexpected retry, fallback, or unexpected input depending on impact |
| INFO | Useful business or operational milestone | Operation start/end, request outcome, job completed |
| CONFIG | Operational configuration details | Checking profiles or non-sensitive options |
| FINE | Basic debug information | Cache hit/miss, selected rule, execution branch |
| FINER | Deeper detail | Intermediate state changes during diagnosis |
| FINEST | Very detailed, often high-frequency | Step-by-step details inside an algorithm or parser for a short period |

JUL also has **OFF** to disable logging by threshold and **ALL** to allow all levels through the corresponding threshold. These two values are not business event types. Each level has a numeric value; a record is discarded by a threshold check if its level is lower than the effective threshold. Do not compare levels based on alphabetical order of their names.

For example, on a single logger, an **INFO threshold** allows INFO, WARNING, and SEVERE, while discarding CONFIG, FINE, FINER, and FINEST. A **FINE threshold** additionally allows CONFIG and FINE; FINER and FINEST are still discarded. A **FINEST threshold** allows even the most detailed levels. Filters, handlers, or output routes may still decide not to emit a record that passed the logger threshold.

In other frameworks, you often encounter ERROR, WARN, INFO, DEBUG, and TRACE. In terms of intended use, JUL's FINE is generally close to DEBUG, and FINER/FINEST are generally close to TRACE. This is only a **semantic comparison**, not a guarantee of equivalent APIs, numeric values, or behavior. To configure levels accurately, you must know whether the application is actually logging through JUL or another backend.

## 3. Choosing Levels for Different Development Scenarios

| Scenario | Example Record | Suggested Level |
| --- | --- | --- |
| Application is ready to serve requests | event=app.ready port=8080 | INFO |
| A batch job finishes | event=batch.completed processed=120 durationMs=85 | INFO |
| A request finishes with a measurable outcome | event=request.completed requestId=req-17 status=200 | INFO |
| Selecting a pricing rule | event=pricing.rule_selected rule=WELCOME requestId=req-17 | FINE |
| Checking cache to explain a decision | event=cache.lookup result=miss requestId=req-17 | FINE |
| Tracing a hard-to-diagnose parser step by step | event=parser.transition state=HEADER index=12 | FINER or FINEST |
| Retry after timeout with noticeable impact | event=payment.retry attempt=2 reason=timeout | WARNING or FINE depending on expectations |
| Dependency cannot serve the request | event=inventory.unavailable requestId=req-17 | SEVERE when the impact is truly severe |
| User enters invalid input along an expected branch | event=validation.rejected field=quantity | FINE/INFO or omit if too frequent |

The level values in the table are examples based on **impact and operational expectations**. There is no rule saying "every caught exception is SEVERE." An exception handled as a normal business case may not need a warning. Conversely, a configuration error that prevents the application from starting must be reported clearly at a sufficiently high level.

A good log message should include **action + outcome + identifier + sufficient context**. Use stable event names, appropriate requestId/traceId, safe reason codes, and measurements with units such as durationMs. Avoid lines like "step1", "here", or "debug" because they are hard to read when multiple requests run concurrently.

## 4. Strategy for Enabling Levels in Development

**Start at INFO by default.** Important records that verify the application is running, explain final outcomes, and highlight anomalies can remain at INFO/WARNING/SEVERE. Do not log every assignment, loop iteration, or input value at INFO.

**When you spot an issue, enable FINE for a narrow scope.** If you are debugging pricing, increase verbosity for the pricing logger/package and its directly related dependencies. Pick a few log points that distinguish logic branches: cache values, selected rules, processing outcomes. Continue filtering by requestId to follow a single execution flow.

**Use FINER/FINEST only when FINE is not enough.** These levels can generate a huge volume of records. Enable them for the specific package or class under investigation, reproduce a controlled case, and turn them off as soon as you have the evidence. Enabling FINEST for all networking, database, and JDK libraries usually buries the important lines.

**After fixing the issue, restore the configuration to baseline.** If a message helps long-term maintenance, keep it at an appropriate level; if it was only overly detailed experimental output, remove it. Do not leave system-wide debug configuration enabled indefinitely. Never assume local logs are private: terminal output, IDE logs, CI logs, or attached issue reports can still be saved and shared.

In multi-service development, selectively enabling logs on the **relevant service/package** and searching by traceId/requestId is usually more effective than changing the entire system. Lines with close timestamps across different machines do not necessarily belong to the same request or follow causal order.

## 5. Two Filtering Layers: Logger and Handler

With JUL, a log call can be dropped right at the **Logger**, or accepted by the logger and then dropped by the **Handler** before being displayed.

- **Logger level:** If the logger is set to FINE, a FINE record can be accepted. If the logger is set to INFO, FINE is dropped before reaching the handler. A logger can inherit its threshold from its parent when its own level is null.
- **Handler level:** ConsoleHandler, FileHandler, or custom handlers have their own thresholds. A handler at INFO will not emit FINE even if the logger is at FINE.
- **Filter:** Both loggers and handlers can apply additional filters. A matching level alone does not guarantee a record will be emitted.
- **Parent handlers:** JUL can forward records to parent logger handlers. If multiple handlers receive the record, it may appear multiple times; if you look at the wrong output destination, you may think records are missing.
- **Formatter:** Determines which fields and text format are displayed; a record may contain information that the formatter does not output.
- **Destination:** ConsoleHandler normally writes to stderr. IDEs, test runners, or container environments may display stderr and stdout differently.

| Logger Effective Level | Handler Level | Does a FINE line reach this handler? |
| --- | --- | --- |
| INFO | FINE | No, dropped by logger |
| FINE | INFO | No, dropped by handler |
| FINE | FINE | Yes, unless dropped by a filter or output error |
| FINEST | FINE | Yes |
| OFF | ALL | No, logger is off |

A key point when debugging: **configuring a logger to FINE does not mean the console is displaying FINE**. In particular, ConsoleHandler may still be using the INFO threshold. When you need detailed output, check the effective threshold in both places and verify whether any framework replaces JUL handlers or configuration.

An illustrative statement (assuming a logger variable is already defined) is:

~~~java
logger.fine("event=pricing.rule_selected rule=WELCOME");
~~~

If the logger is at FINE but ConsoleHandler is at INFO, this line is still dropped at the handler. If the handler is set to FINE but the logger inherits INFO, the line is dropped as soon as the logger is called.

## 6. Java 17+ Program Comparing Two Observation Levels

This example uses **java.util.logging**, requiring no dependencies outside the JDK. In the same simulated processing flow, the application makes five log calls. A custom system property **app.env** determines whether INFO or FINE is used.

Create the file **DevLogLevelDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DevLogLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(DevLogLevelDemo.class.getName());

    public static void main(String[] args) {
        boolean development = "dev".equals(System.getProperty("app.env"));
        Level selected = development ? Level.FINE : Level.INFO;

        // Use a single handler in this demo to avoid duplicate output.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(selected);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(selected);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        try {
            LOG.info("event=request.started requestId=req-17");
            LOG.fine("event=cache.lookup requestId=req-17 result=miss");
            LOG.log(Level.FINE, () ->
                    "event=route.selected requestId=req-17 branch=fallback");
            LOG.warning("event=dependency.retry requestId=req-17 attempt=2");
            LOG.info("event=request.completed requestId=req-17 status=200");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

### Run 1: Default INFO

Compile and run with **JDK 17 or later**:

~~~bash
javac DevLogLevelDemo.java
java DevLogLevelDemo
~~~

**Exact output written by ConsoleHandler to stderr**:

~~~text
INFO | event=request.started requestId=req-17
WARNING | event=dependency.retry requestId=req-17 attempt=2
INFO | event=request.completed requestId=req-17 status=200
~~~

The FINE lines are not emitted because both the logger and the handler are set to the INFO threshold. They are still logging calls executed in code; their details are simply not sent to the destination.

### Run 2: Enable FINE for Development

Run:

~~~bash
java -Dapp.env=dev DevLogLevelDemo
~~~

**Exact output on stderr**:

~~~text
INFO | event=request.started requestId=req-17
FINE | event=cache.lookup requestId=req-17 result=miss
FINE | event=route.selected requestId=req-17 branch=fallback
WARNING | event=dependency.retry requestId=req-17 attempt=2
INFO | event=request.completed requestId=req-17 status=200
~~~

The FINE threshold reveals the cache miss and fallback branch selection. Both runs still produce the same business outcome: the request finishes with status=200. A WARNING appears in both modes and only reports a retry, not that the request failed.

### Component-by-Component Explanation

1. **System.getProperty("app.env")** reads a JVM property defined by this exercise. The `-Dapp.env=dev` option goes before the class name in the `java` command. This is not a built-in JUL logging configuration property.
2. **LOG.setLevel(selected)** sets the threshold on the logger to allow INFO or FINE.
3. **handler.setLevel(selected)** sets the threshold on ConsoleHandler. If you only change the logger while the handler stays at INFO, the two FINE lines will not appear.
4. **LOG.setUseParentHandlers(false)** prevents records from being forwarded to the root logger's handler and potentially appearing twice in the demo.
5. **Formatter** here prints only the level and message, omitting timestamp, logger name, and stack trace so the output is deterministic. Real formatters should include such metadata for troubleshooting.
6. **LOG.log(Level.FINE, () -> ...)** uses a `Supplier<String>` to defer message construction; if the logger filters out FINE, the Supplier may not be invoked. Do not put business side effects inside a Supplier.
7. **LOG.removeHandler(handler)** and **handler.close()** release the handler after the demo finishes. Real applications typically initialize and manage handlers over the application lifecycle rather than creating a new handler per request.

JUL's ConsoleHandler writes to **stderr**, whereas `System.out.println` writes to stdout. The fact that a terminal interleaves both streams does not make them the same stream. If your environment only captures stdout, check how stderr is configured or collected.

## 7. Configuring Verbosity Outside Code

In real projects, you emit logs through a logger, but you should usually configure levels by **environment/profile** so you can change observability without editing code. The practice code above calls `setLevel` directly only for demonstration; the external configurations below apply to applications using the corresponding mechanism and do not immediately override programmatic configuration.

### Example JUL logging-dev.properties File

~~~properties
# Root logger at INFO.
.level = INFO

# Specify handler for root; handler accepts FINE.
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Increase verbosity for the package under investigation.
com.example.checkout.level = FINE
~~~

When a suitable application has main class `com.example.Main` and the classpath is in the `out` directory, you can run:

~~~bash
java -Djava.util.logging.config.file=logging-dev.properties -cp out com.example.Main
~~~

The file must exist at a path accessible to the JVM. In this example, root is at INFO; the `checkout` package is set to FINE; and the root handler must be verbose enough not to drop FINE lines from the `checkout` logger. Other loggers still inherit the root's INFO threshold unless configured separately.

**This is not the command to run DevLogLevelDemo from Section 6.** That program creates its own ConsoleHandler and calls `setLevel` in code, so it does not demonstrate external configuration working independently. When using JUL's default SimpleFormatter, the format and timestamps will also differ from the custom formatter output above.

### Example Framework Configuration Such as Spring Boot

For a logging system configured by Spring Boot, an illustrative YAML snippet is:

~~~yaml
logging:
  level:
    root: INFO
    com.example.checkout: DEBUG
~~~

This keeps root at INFO while enabling DEBUG for the `checkout` package. That is **Spring Boot syntax**, not JUL `logging.properties` syntax. Level names in SLF4J/Logback/Log4j 2 can differ from JUL. When an application uses a facade and a separate backend, adjusting JUL's ConsoleHandler may have no effect on loggers emitting through that backend.

Common things to check: whether the development profile is active, whether the config file is actually loaded, whether the package name matches the logger name, whether the level is overridden by environment variables or command-line arguments, and whether any code calls `setLevel` after configuration is loaded.

### Environment-Based Configuration Conventions

Locally, you can enable FINE/DEBUG for a specific component to reproduce an issue. In test environments, choose enough verbosity to diagnose failing tests without generating uselessly long logs. Staging and production environments typically need a consistent operational baseline, observing via INFO/WARNING/SEVERE with a controlled mechanism to enable debug logging on demand when needed. Exact level choices should be based on load, storage capacity, security, and product conventions.

## 8. When FINE or DEBUG Is Missing: Checklist in Order

**Step 1 — Verify the code path.** Set a breakpoint or check calling conditions to be sure the branch in question actually executes. Missing logs alone do not prove the code did not run.

**Step 2 — Confirm the logger name.** Check the class/package name or manually specified logger name. A FINE threshold on a different logger does not affect every logger in the JVM.

**Step 3 — Check the effective level.** Does the logger have level FINE, or is it inheriting INFO from its parent? In JUL, a null level means inherited; do not confuse it with ALL.

**Step 4 — Check the handler/appender.** ConsoleHandler/FileHandler may still be at INFO or have its own filter. Another handler might be writing FINE to a file while the console does not show it.

**Step 5 — Check propagation.** Parent handlers can produce duplicate output or use a different format if `useParentHandlers` is enabled. Do not change the entire root configuration just because you see a duplicated line.

**Step 6 — Check the actual backend.** An SLF4J facade + Logback is not controlled directly by JUL ConsoleHandler; find out which adapter/backend the application is using.

**Step 7 — Check effective configuration.** Is the right profile active, was the file loaded, is the system property placed correctly, and is anything overriding it after startup?

**Step 8 — Check the destination and reader.** ConsoleHandler usually writes to stderr. CI, containers, test runners, IDEs, or log collectors may separate streams or apply different parsers/filters.

**Step 9 — Check delay and missing data.** With a log collector, there may be batching, sampling, ingestion delay, retention limits, or dropped records. Do not conclude an event never happened just because you cannot find the record yet.

When diagnosing, identify **which layer dropped the record** before raising the log level at that layer. Setting ALL across the entire application may flood your logs without fixing the real problem of looking at the wrong service, class, file, or requestId.

## 9. Cost and Security When Enabling Verbose Logging

**Never log sensitive data, even at FINEST on a developer machine.** Avoid passwords, session cookies, access tokens, refresh tokens, API keys, OTP codes, payment details, payloads containing personal data, or configurations with credentials. Data printed in exception messages, URLs, or `toString()` can also leak sensitive information. When correlation is needed, use policy-approved identifiers; do not assume every ID is safe to log.

**Untrusted input can cause log injection.** User-supplied strings containing newlines and control characters can forge a new log record when concatenated directly into text logs. Use proper escaping, structured logging, size limits, and input sanitization.

**Do not build expensive messages when the level is filtered out.** With JUL, a `Supplier` defers message construction:

~~~java
// Illustrative snippet; assumes logger and expensiveSummary() are already declared.
logger.log(java.util.logging.Level.FINE,
        () -> "event=state.snapshot details=" + expensiveSummary());
~~~

You can also use an `isLoggable` check when preparing expensive data. A `Supplier` is not invoked when the logger filters out the level, but **a handler or filter can still drop the record later**; do not rely on logging to execute business side effects.

Do not log entire objects or values on every iteration of a hot path. When records are actually emitted, serialization, formatting, disk I/O, buffering, and shipping can all slow down the application. For timing-related bugs, heavy logging can even alter race-condition behavior. Use metrics for aggregate counts/latencies and traces for request paths; logs should capture information that explains events or decisions.

## 10. Common Mistakes and How to Fix Them

| Common Mistake | Consequence | Fix |
| --- | --- | --- |
| Enabling ALL/FINEST JVM-wide for days | Noisy logs and higher I/O | Enable FINE/DEBUG only for relevant packages and only while needed |
| Setting logger to FINE, handler to INFO | FINE lines do not appear | Check both logger and handler |
| Treating WARNING as a failed request | Wrong conclusions when retries recover | Check the final outcome and requestId |
| Logging "here1", "here2" | Unclear which event or flow occurred | Use event names, branch, requestId, and outcome |
| Logging INFO for every assignment | Hard to find key milestones | Move internal debug details to FINE/FINER |
| Confusing Logback DEBUG with JUL FINE | Misconfigured logging | Identify the facade, backend, and profile |
| Concatenating only `ex.getMessage()` | Loses Throwable type, cause, and stack trace | Log the Throwable using the appropriate overload when needed |
| Logging the same exception at multiple layers | Inflated error counts | Log once at the responsible boundary with sufficient context |
| Logging success before commit | Record does not reflect final outcome | Log after confirming the result or name the event accurately |
| Using `System.out.println` everywhere | No levels, loggers, or management | Use the project's unified logging API |
| Logging raw requests or secrets for quick debugging | Risk of data exposure | Log minimal, safe, masked fields |
| Forgetting to lower levels after investigation | Logs keep growing and adding noise | Restore development configuration before finishing |

When using `Throwable`, distinguish between exceptions that are caught and handled legitimately and errors that break functionality. A stack trace shows where an error was thrown; a contextual message explains **which operation failed and which entity was affected**. Do not assign a level based solely on the exception class name.

## 11. Practical Workflow for Debugging a Feature

Suppose you need to investigate incorrect pricing caused by possibly picking the wrong fallback branch:

1. **Create a reproduction case** with synthetic or sanitized data, recording the inputs and `requestId`.
2. **Form a hypothesis**: is the wrong price caused by a cache miss or by rule selection? You need logs at both decision points.
3. **Keep INFO milestones** for request start and final outcome; use FINE at `cache.lookup` and `pricing.rule_selected`.
4. **Enable FINE on the right package** in both the logger and the active handler/backend; avoid increasing verbosity for all libraries.
5. **Rerun and filter by requestId**, then order the timeline. Observe the two contrasting branches instead of searching generically for `ERROR`.
6. **Cross-check logs with a debugger, tests, metrics, or traces**. If a log only records an event before the transaction completes, verify the actual final state.
7. **Fix the bug and verify business behavior** with proper tests, not just by checking that a log line appeared.
8. **Lower the level and remove temporary debug logs**, keeping records with long-term maintenance value at an appropriate level.

Logs are evidence of what the code and logging pipeline recorded. They do not replace assertions, business-state verification, or independent measurements, nor do they guarantee every event was recorded completely when filtering, sampling, or I/O errors occur.

## 12. Self-Check

**Q1:** Logger is at FINE and ConsoleHandler is at INFO. Will a FINE line appear on that handler's console?  
**Answer:** No. The logger accepts the record, but the handler filters at INFO. Both thresholds must be set appropriately.

**Q2:** If the JUL threshold is FINE, are FINER records shown automatically?  
**Answer:** No. FINER is lower than FINE in threshold order; you need a sufficiently detailed level such as FINER or FINEST at the relevant layers.

**Q3:** Why does running the example with `-Dapp.env=dev` produce two extra FINE lines?  
**Answer:** The program selects FINE for both the Logger and ConsoleHandler, whereas the default run selects INFO. The business code still executes the exact same steps.

**Q4:** Does a WARNING on a retry event mean the request failed?  
**Answer:** No. The retry may have succeeded; check the completion event for the same `requestId`.

**Q5:** Why avoid enabling FINEST for all libraries?  
**Answer:** High overhead, heavy noise, potential data exposure, and difficulty finding important records. Increase verbosity only for the scope relevant to your hypothesis.

**Q6:** Can you use JUL's `logging.properties` to directly control an SLF4J/Logback logger?  
**Answer:** Not by default. You must know the logging facade, backend, and bridge, then configure the appropriate mechanism.

**Q7:** Are logs on a personal machine allowed to include raw tokens just because it is for debugging?  
**Answer:** No. Logs can end up in IDE windows, terminal history, CI, or bug reports; protect sensitive data in every environment.

## Key Takeaways

In a development environment, **the goal is to produce enough evidence to explain behavior**, not to print everything. Keep your baseline readable, enable FINE/DEBUG for the exact area under investigation, remember both logger and handler thresholds, attach context so you can read by request, and lower verbosity when done. Enabling logs must never alter business logic or leak sensitive data.
