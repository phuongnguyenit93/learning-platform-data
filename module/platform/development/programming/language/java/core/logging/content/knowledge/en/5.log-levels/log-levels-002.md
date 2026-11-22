# DEBUG — Detailed Log Level in Java

## 1. What is DEBUG?

**DEBUG** is the log level intended for detailed information that helps developers **understand which steps a program took, which execution branch it chose, what intermediate state looked like, and why a particular behavior occurred**. DEBUG is especially useful when investigating hard-to-reproduce bugs, testing hypotheses about execution flow, or analyzing interactions between components.

Examples of events suitable for DEBUG:

~~~text
DEBUG service=pricing requestId=req-17 rule=member-discount matched=true
DEBUG service=pricing requestId=req-17 subtotal=100 discount=10 total=90
DEBUG service=inventory requestId=req-17 cache=miss fallback=database
~~~

These are **illustrative** lines, not the default output of any specific library. They show that DEBUG can record **decisions and intermediate state** that normally do not need to appear in operational logs.

DEBUG is **not a debugger**. A debugger can pause a program, set breakpoints, and inspect variables at runtime. DEBUG is a **log record severity level**: the application continues running normally and can emit events according to its configuration even without a debugger attached.

DEBUG also **does not automatically enable JVM debug mode, does not run line-by-line more slowly through any special mechanism, does not fix bugs, and does not alter business logic**. It only allows emitting additional logging events that the developer explicitly wrote at that level (and that the logging system lets through).

## 2. Where does DEBUG sit among log levels?

Popular logging libraries such as **SLF4J with Logback** and **Log4j 2** typically use the following ascending order of severity:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Exact names and configuration depend on the library, but the threshold rule is usually as follows:

| Configured threshold | Messages typically permitted in the scale above |
| --- | --- |
| ERROR | ERROR |
| WARN | WARN, ERROR |
| INFO | INFO, WARN, ERROR |
| DEBUG | DEBUG, INFO, WARN, ERROR |
| TRACE | TRACE, DEBUG, INFO, WARN, ERROR |

This table assumes no other filters or appender-level restrictions. When configured at **INFO**, `debug(...)` calls are normally ignored. When configured at **DEBUG**, `debug(...)` calls become eligible for output; the application still needs an appender and filters that allow them.

### Does standard Java have a DEBUG level?

In **java.util.logging (JUL)**, the built-in JDK API, **there is no `java.util.logging.Level.DEBUG` constant**. JUL uses levels such as **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**.

To learn the concept of DEBUG using plain JDK, you can use **Level.FINE** as a roughly equivalent level for debugging details:

| Intent | Typical SLF4J/Logback | Typical JUL |
| --- | --- | --- |
| Operational milestone | INFO | INFO |
| Troubleshooting detail | DEBUG | FINE |
| Very detailed tracing | TRACE | FINER or FINEST |
| Warning | WARN | WARNING |
| Serious error | ERROR | SEVERE |

**This is a comparison by intent, not a guaranteed one-to-one mapping**. If an application uses JUL, call **LOGGER.fine(...)** or **LOGGER.log(Level.FINE, ...)**; if it uses SLF4J, call **logger.debug(...)**. Do not write **Level.DEBUG** in JUL code because that constant does not exist.

## 3. When should you log at DEBUG?

DEBUG is most valuable at points where the reader needs **concrete evidence of flow and decisions**:

1. **Branch selection:** "Applied discount rule A because of order type X."
2. **Dependency calls:** "Cache miss, falling back to database read," along with the operation name and correlation ID.
3. **Data transformations:** record counts before/after filtering, applied conditions, or aggregated results that are safe to log.
4. **Lifecycle of a complex operation:** start/completion of meaningful phases, or duration of an expensive step.
5. **Hypothesis-driven bug investigation:** recording the minimal state values needed to distinguish two execution paths; can be enabled briefly when needed.
6. **System integration:** recording response codes, retry counts, chosen timeouts, or circuit breaker state; avoid putting sensitive content in logs.

Example:

~~~text
DEBUG component=payment requestId=req-22 attempt=2 retryDelayMs=200 reason=timeout
~~~

This message is useful for seeing *why the system retried*; meanwhile, retries per minute, timeout rate, or p95 latency should be measured with **metrics** to track trends.

Do not log every local variable just because DEBUG is enabled. A good DEBUG line should tie back to a **specific diagnostic question**; unfocused logging buries important events in noise.

## 4. How enabling/disabling DEBUG works

Typical flow:

~~~text
Application code: logger.debug("...")
                    |
                    v
             Logger checks level
                    |
           Is DEBUG accepted?
             /               \
           no                yes
           |                  |
         skip         create/pass log event
                              |
                              v
                     Appender and filter
                              |
                              v
                    Encoder/Formatter
                              |
                              v
                   Console / File / ...
~~~

In JUL, the corresponding components are **Logger**, **Handler**, and **Formatter**; the exact order and filter evaluation depend on configuration. The same event can also be forwarded up to parent loggers, resulting in multiple handlers receiving the record.

Three concepts should be kept separate:

- **Event level:** the DEBUG/FINE call indicates what kind of information this is.
- **Logger threshold:** the first gate determining whether the event is emitted.
- **Handler or appender threshold/filter:** decides whether an emitted event reaches that destination.

Therefore, setting a logger to DEBUG while an appender has a filter allowing only INFO and above can still result in **no DEBUG output**. Conversely, setting a very verbose appender cannot rescue an event that was already filtered out by the logger at the start.

Log levels can usually be configured by **package/logger name**. For example, you can enable DEBUG only for the pricing component while keeping other components at INFO. This is a practical way to narrow log volume during an incident investigation.

## 5. Runnable Java 17+ example: illustrating DEBUG with JUL FINE

To run directly on JDK 17 or later **with no dependencies**, the following example uses **java.util.logging.Level.FINE** to represent the DEBUG concept. It intentionally shows the detailed event hidden when the threshold is INFO and appearing after switching the threshold to FINE.

Create **DebugLevelDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class DebugLevelDemo {
    private static final Logger LOGGER =
            Logger.getLogger(DebugLevelDemo.class.getName());

    public static void main(String[] args) {
        // Use only the handler below so the output is not printed twice.
        LOGGER.setUseParentHandlers(false);

        // Initially emit only INFO and more severe levels.
        LOGGER.setLevel(Level.INFO);

        // Output destination is stdout; the handler must also allow FINE.
        Handler console = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        console.setLevel(Level.FINE);
        LOGGER.addHandler(console);

        LOGGER.info("Bắt đầu xử lý job-42");

        // Not emitted: logger is at INFO, so FINE is filtered out.
        LOGGER.log(Level.FINE,
                () -> "jobId=job-42 branch=standard");

        // Enable the detail level roughly equivalent to DEBUG.
        LOGGER.setLevel(Level.FINE);
        LOGGER.log(Level.FINE,
                () -> "jobId=job-42 base=100 discount=10");
        LOGGER.info("Hoàn tất job-42: total=90");

        // StreamHandler is buffered, so flush is needed in a short example.
        console.flush();
    }
}
~~~

Compile and run in a UTF-8 terminal:

~~~bash
javac -encoding UTF-8 DebugLevelDemo.java
java DebugLevelDemo
~~~

**Exact stdout** of the program in the described environment:

~~~text
INFO | Bắt đầu xử lý job-42
FINE | jobId=job-42 base=100 discount=10
INFO | Hoàn tất job-42: total=90
~~~

Explanation:

1. **LOGGER.setLevel(Level.INFO)** sets the initial threshold. Because **FINE** is lower than INFO, the `branch=standard` message is not emitted.
2. **LOGGER.setLevel(Level.FINE)** allows FINE events for subsequent calls. No recompilation is needed to switch thresholds in this example.
3. **console.setLevel(Level.FINE)** makes the handler accept FINE; if the handler stayed at INFO, the FINE line could still be dropped.
4. **LOGGER.setUseParentHandlers(false)** prevents parent logger handlers from printing duplicate records, potentially in a different format.
5. **StreamHandler(System.out, Formatter)** explicitly sends logs to **stdout** and formats them with only level + message. **JUL's default ConsoleHandler typically writes to stderr**, so do not assume both approaches target the same output stream.
6. **console.flush()** pushes buffered content to stdout so the output is complete.
7. The **() -> ...** lambda provides the message via JUL's `Supplier`; this is useful when constructing the log message is expensive and the level is disabled.

In real applications, levels are usually configured centrally and changed in a controlled way per environment. Configuring a handler manually inside `main` here is only for clearly demonstrating each component.

## 6. Real DEBUG with SLF4J and Logback

In a project using **SLF4J** as the API and **Logback** as the backend, a common pattern is:

~~~java
// Illustrative snippet placed in a class with orderId and ruleName variables.
// Requires SLF4J API and an appropriate logging provider in dependencies.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PricingService.class);

LOG.debug("orderId={} matchedRule={}", orderId, ruleName);
LOG.info("Đã hoàn tất tính giá cho orderId={}", orderId);
~~~

This is an **illustrative snippet**, not a standalone JDK-only program: it requires declaring the `PricingService` class, the variables, and SLF4J/backend dependencies. **{}** is SLF4J's placeholder convention, not the **{0}** parameter syntax commonly used in JUL.

With Logback, an example configuration in **logback.xml** on the classpath:

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.pricing" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

What this means:

- Code under the **com.example.pricing** logger hierarchy can emit DEBUG.
- Other logger hierarchies normally inherit the root **INFO** threshold unless configured separately.
- The STDOUT appender receives accepted events and formats them. This sample does not add a separate threshold filter, so DEBUG from the pricing hierarchy can be printed through the appender attached to root.
- This configuration only takes effect when the project **actually uses Logback** and the file is loaded properly. Do not apply `logback.xml` to an application using only JUL.

A Spring Boot application may provide its own level-configuration mechanism; check your project's actual framework/backend rather than assuming everything reads the same config file.

### DEBUG is enabled, but no logs appear: what to check?

Check in order:

1. Does the code actually call **debug(...)** or **Level.FINE** at the location you are observing?
2. Did execution actually take that branch in the test case you are running?
3. Does the level for the **exact logger/package name** allow DEBUG/FINE?
4. Is a handler/appender threshold or another filter blocking it?
5. Did the application load the right config file or environment variable for the **active backend**?
6. Are logs sent to console, stderr, a file, a container collector, or a centralized service? You might be looking at the wrong destination.
7. Is there filtering, sampling, buffering, or collection delay at the destination?

A logger call does not guarantee that the record will always show up in every log viewer.

## 7. Performance: disabled levels can still have a cost

**Disabling DEBUG does not mean every computation that builds DEBUG data is free.** In Java, argument expressions are evaluated *before* the method is invoked.

Illustrative example (variables and methods are already defined where used):

~~~java
LOG.debug("Chi tiết đơn hàng: {}", expensiveSerialize(order));
~~~

Even though the backend may not output DEBUG, **expensiveSerialize(order)** is still executed to produce the argument for the call. SLF4J's placeholders avoid part of the string-building/formatting cost when the level is disabled, **but they do not defer evaluating every argument expression**.

With SLF4J, if building the data is very expensive, you can guard it:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("Chi tiết đơn hàng: {}", expensiveSerialize(order));
}
~~~

With JUL, use a `Supplier` or check the level:

~~~java
LOGGER.log(Level.FINE,
        () -> "Chi tiết đơn hàng: " + expensiveSerialize(order));
~~~

These two snippets **only illustrate usage inside a class that already has a logger, the `order` variable, and the `expensiveSerialize(...)` method**, not a standalone compilable program. In JUL, a supplier defers building the message when the logger rejects the level; if you use another framework, use whatever lazy logging mechanism that version supports.

**Do not put required side effects inside message construction.** For example, do not increment a business counter, write to a database, or mutate state inside a supplier just to log DEBUG; when DEBUG is off, that work may not run.

### What happens if DEBUG is enabled in production?

DEBUG can increase:

- String allocations and data formatting overhead.
- Event volume through handlers/appenders, I/O, and storage usage.
- Pressure on buffers or asynchronous logging queues.
- Transmission, indexing, and query costs in centralized logging systems.
- Exposure risk if detailed messages contain sensitive data.

The impact depends on event volume, formatting, and actual configuration. There is no fixed rule that DEBUG always slows an application down by a specific percentage. Measure and enable selectively.

## 8. Writing useful DEBUG messages

A good practice is to describe the **target/operation, processing stage, decision, and outcome** using consistent fields:

~~~text
DEBUG service=order requestId=req-43 stage=validate rule=stock-check result=passed
DEBUG service=order requestId=req-43 stage=price strategy=member subtotal=120 discount=20
DEBUG service=order requestId=req-43 stage=reserve-stock skuGroup=standard result=success
~~~

Reading these three lines, you can follow the progress of the same request and the branch chosen. In multi-service systems, a **trace ID** can link corresponding spans and logs.

Guidelines:

- **Prefer meaningful messages:** "chose strategy X because of Y" is far more useful than "reached line 125."
- **Use safe correlation IDs:** `requestId`/`traceId` can help find related logs. Do not assume every ID is harmless; follow internal data rules.
- **Keep formatting consistent:** use stable field names and clear units like `durationMs`, `sizeBytes`; structured logging makes querying fields easier.
- **Avoid dumping entire objects unnecessarily:** `toString()` can be long, expensive, change across versions, or accidentally contain sensitive data.
- **Avoid logging inside tight loops:** if there are 100,000 items, one DEBUG line per item generates huge volume. Consider logging at summary milestones or only on anomalies.
- **Do not use DEBUG as a substitute for metrics:** request rate, error rate, queue depth, and latency percentiles belong in proper metrics; DEBUG is for detailed case-by-case investigation.

### Data that requires strict caution

Never log passwords, access tokens, session cookies, API keys, private keys, card numbers, or sensitive personal data in raw form, **even if the log is only at DEBUG**. Logs can still be shipped, stored in backups, accessed by others, or persist after DEBUG is turned off.

Avoid logging full HTTP headers/bodies, SQL statements containing secret values, complete user objects, or external service payloads. If you need an attribute for investigation, keep only the minimum required, mask sensitive fields, and follow retention policies.

Strings from untrusted sources may contain newline characters or forged log entries. When designing structured logging or formatters, handle encoding/escaping properly so logs cannot be spoofed or corrupted.

## 9. DEBUG in multithreaded and distributed systems

Java applications can handle many concurrent requests. DEBUG lines from different threads will interleave, for example:

~~~text
DEBUG requestId=A stage=validate
DEBUG requestId=B stage=validate
DEBUG requestId=A stage=price
DEBUG requestId=B stage=price
~~~

Relying on line order alone makes it hard to tell which event belongs to which request. Therefore, include a **consistent request ID or trace ID** in the context; logging libraries and frameworks may provide MDC, ThreadContext, or equivalent context propagation.

- **JUL Logger** does not automatically have the same MDC API as SLF4J/Logback.
- When using thread pools, async tasks, or reactive pipelines, propagate context explicitly; do not assume `ThreadLocal` always follows the work automatically.
- Timestamps should have a clear timezone and format; machines can have clock skew, so do not infer a strict global ordering from a single list of lines.
- DEBUG can be enabled per service or logger under investigation; when correlating across services, standardize IDs and context fields.

If part of a request is slow, **metrics** or **distributed traces** help pinpoint where to look; DEBUG can then clarify internal choices and state at that spot.

## 10. Workflow for enabling DEBUG during incident investigation

Suppose metrics show rising timeouts in the checkout service, but INFO logs are not enough to see which retry branch was chosen.

1. **Define the scope:** the service, package/logger, time window, and sample requests to observe.
2. **Verify log points:** check whether existing DEBUG calls capture the retry branch and needed context; avoid logging secrets.
3. **Enable DEBUG selectively** through the configuration mechanism your project supports, keeping other components at INFO where appropriate.
4. **Observe actual output:** verify logger, appender, filter, timestamps, and IDs; do not assume events will reach the collector.
5. **Correlate evidence:** combine DEBUG logs, error logs, metrics, and traces to form a root-cause hypothesis; do not conclude the cause from a single isolated line.
6. **Disable or restore operational levels** after collecting enough data and verifying traffic/cost impact.
7. **Keep the right observability:** if the same issue is repeatedly hard to diagnose, consider adding metrics, tracing, or a better-placed log rather than leaving DEBUG on system-wide for long periods.

Some libraries support changing levels at runtime, while others require reloading configuration or restarting. Your procedure should match how the project actually configures logging.

## 11. Common mistakes with DEBUG

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Calling JUL `Level.DEBUG` | Compilation error because JUL has no such constant | Use `Level.FINE` for a roughly equivalent purpose |
| Confusing DEBUG with a debugger | Misunderstanding the impact of log levels | Distinguish event logging from breakpoints and variable inspection |
| Changing only the logger and forgetting handler/appender | Detailed logs do not appear | Check thresholds and filters at the destination too |
| Leaving application-wide DEBUG on too long | Excessive logs, high cost, hard to find errors | Enable per package/service for an appropriate duration |
| Logging entire objects or payloads | Overly large data, potential secret leaks | Log only needed fields and mask sensitive data |
| Expensive string concatenation before calling debug | Still consumes CPU when DEBUG is off | Use placeholders, level guards, and appropriate lazy logging |
| Using DEBUG inside uncontrolled loops | Log volume grows rapidly | Log by phase, on anomalies, or with sampling |
| Logging DEBUG and expecting the program to handle errors | The bug remains, execution flow is unchanged | Use proper exception handling and business logic |
| Missing request ID across multiple threads | Cannot distinguish related events | Add controlled correlation context |
| Treating DEBUG as the sole performance measure | Hard to track trends and percentiles | Combine with metrics and tracing |

## 12. Self-check questions

**Q1.** An application uses SLF4J with the logger configured at INFO. Will `logger.debug(...)` normally appear?

**Answer:** No. DEBUG is lower than INFO, so it is usually filtered out at the logger. To see DEBUG, configure an appropriate threshold and ensure appenders/filters accept it.

**Q2.** In Java 17 using only `java.util.logging`, should you use `Level.DEBUG` or `Level.FINE`?

**Answer:** JUL does not have `Level.DEBUG`; use **Level.FINE** for detailed information roughly equivalent to DEBUG's purpose.

**Q3.** Why can `LOG.debug("data={}", expensiveSerialize(data))` still consume CPU when DEBUG is disabled?

**Answer:** Java evaluates **expensiveSerialize(data)** before calling `debug(...)`. Placeholders do not defer every argument expression. Use a guard or lazy logging when the computation is expensive.

**Q4.** When you need p95 latency and error rate over 5 minutes, should you just enable DEBUG?

**Answer:** No. **Metrics** are better suited for rates and latency distributions; DEBUG adds behavioral details when investigating root causes.

**Q5.** Can you log an access token at DEBUG because production is set to INFO?

**Answer:** No. Levels can be changed, and logs can be collected or stored unintentionally. Never log secrets at any log level.

**Q6.** A logger has DEBUG enabled, yet no records appear on the console. Is it certain that execution has not reached the debug line?

**Answer:** Not necessarily. You must check the logger name, appender/handler threshold, filters, backend configuration, output destination, and buffering/collection mechanisms.

**Takeaway:** **DEBUG is the log level for diagnostic details**, typically disabled under INFO configurations and enabled selectively during investigation. In **SLF4J/Logback**, use `debug(...)`; in **JDK JUL**, use `FINE` for a roughly equivalent purpose. Log meaningful decisions and state, protect sensitive data, and keep the cost of verbose logging under control.
