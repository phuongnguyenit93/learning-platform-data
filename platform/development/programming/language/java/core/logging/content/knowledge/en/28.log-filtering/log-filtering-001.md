# What Is Log Filtering? Event Filtering Mechanisms in Java Logging

## 1. Concepts and Purpose

**Log filtering** is a mechanism that inspects a logging call or a log event against defined conditions, and then decides whether that event should continue processing, be routed to an output destination, or be discarded.

For example, the same application might log many different events:

~~~text
DEBUG  | SQL parameters for order 42
INFO   | Order 42 created
INFO   | healthcheck: ok
WARN   | Payment provider is slow
ERROR  | Payment failed
~~~

The desired policy might be: the console receives only WARN/ERROR; the business log file receives INFO and above while dropping repetitive healthchecks; and a diagnostic channel receives only DEBUG logs from a package currently experiencing errors. Achieving these outcomes requires choosing the right **filtering location** and **filtering conditions**.

Filtering provides three main benefits:

1. **Noise reduction:** hides logs with low observability value (e.g., repetitive healthcheck requests).
2. **Cost reduction:** fewer events need to be formatted, written to disk, transmitted over the network, indexed, and stored.
3. **Log flow control:** allows each destination to receive the appropriate type of events—for example, separate policies for the operations console and the audit file.

However, overly aggressive filtering can hide errors; and **log filtering does not by itself guarantee data security or zero log loss**. It is an observability decision that must be tested according to the system's requirements.

## 2. Which Layers Do Logs Pass Through?

A Java logging pipeline using a facade such as SLF4J and a backend such as Logback or Log4j 2 typically involves the following decisions:

~~~text
Application calls logger.debug/info/warn/error(...)
                         |
                         v
              Is logger level enabled?
                         |
             +-----------+-----------+
             |                       |
            No                      Yes
             |                       |
          Ignore               Check filter
                                     |
                    +----------------+----------------+
                    |                                 |
                   DENY                            Proceed
                    |                                 |
                 Ignore                    Create/pass LogEvent
                                                      |
                                               Select appender
                                                      |
                                           Appender filter/threshold
                                                      |
                                          Encoder / writer / sink
                                                      |
                                        File, console, log collector
~~~

This is a conceptual diagram. **Actual order varies by backend and where the filter is attached**: Logback has TurboFilter operating before event creation and standard filters at the appender; Log4j 2 has filters at the context, logger, appender reference, and appender levels; JUL has Filter on the Logger or Handler.

There is no simple rule that "every filter runs after the level check." Some filters run very early and can affect event acceptance before the standard level check. When encountering unexpected results, consult the exact pipeline of the backend and version in use.

## 3. Distinguishing Level, Filter, Appender, and Sampling

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Logger level** | Is a call at this level enabled on the emitting logger? | ROOT=INFO, package payment=DEBUG |
| **Filter** | Does the event satisfy specific conditions to proceed? | Drop healthcheck messages; accept only logs with marker AUDIT |
| **Appender/Handler** | Which destination does the event go to? | Console, file, broker, HTTP sink |
| **Appender threshold** | From what level does that destination accept events? | File accepts only WARN and ERROR |
| **Sampling/rate limiting** | How many events are kept by ratio or rate limit? | Keep only 1% of diagnostic events |
| **Masking/redaction** | How are sensitive values processed before output? | Replace tokens with [REDACTED] |

**Level** is a common filtering condition, but filters are more flexible: they can inspect markers, MDC/ThreadContext, message content, source, tenant, request path, or contextual information. Depending on the library, conditions may be evaluated before or after the message is formatted.

**Do not equate filtering with routing.** If an event is rejected at the CONSOLE appender, it can still be sent to the FILE appender. However, if the event is dropped at the logger or a global filter, downstream appenders may never receive it.

## 4. Common Filtering Conditions

### 4.1. By Severity Level

Accept only WARN/ERROR for the operations console:

~~~text
DEBUG  -> drop
INFO   -> drop
WARN   -> accept
ERROR  -> accept
~~~

This is **threshold filtering**. It differs from **exact single-level filtering**:

~~~text
Accept only WARN:
DEBUG -> drop
INFO  -> drop
WARN  -> accept
ERROR -> drop
~~~

This distinction is critical when using Logback: ThresholdFilter with level WARN typically allows WARN and above; LevelFilter with level WARN can be configured to allow only WARN and reject ERROR as well.

### 4.2. By Logger Name or Package

For example, enable DEBUG only for com.example.payment while keeping package org.hibernate at WARN. This case can be solved cleanly via per-logger level configuration without necessarily writing a custom filter.

Logger names are usually derived from the fully qualified class name, though they can also be manually named by the developer. You must match the actual logger name; a similar package name does not match automatically.

### 4.3. By Content or Event Code

For example, dropping messages starting with "healthcheck:", or accepting events with eventCode="PAYMENT_RETRY".

String filtering based on formatted content is fragile: changed wording, localization, different parameter formatting, or casing differences can break the filter. When the application supports structured logging, prefer filtering on **stable semantic attributes** such as eventCode, marker, and context fields.

### 4.4. By Context: MDC/ThreadContext

In Logback, MDC is contextual data typically bound to a thread, such as correlationId or tenant. Log4j 2 provides ThreadContext (context map) for a similar purpose.

For example, you can filter events for a specific job type:

~~~text
eventCode=IMPORT_PROGRESS, jobType=BULK -> can be reduced or sampled
eventCode=IMPORT_FAILED,   jobType=BULK -> still kept
~~~

Ensure that context is properly propagated across thread pools or async processing and cleared after the request completes. A filter relying on an empty MDC or one leaked from another request can drop the wrong events.

### 4.5. By Marker, Frequency, or Destination

- **Marker:** a structured tag attached to a log call, e.g., SECURITY_ALERT; filters match markers using the backend's API.
- **Burst/rate:** limits the number of events in a group that can be dropped or allowed within a time window, while tracking what was discarded.
- **Per-appender:** console receives only WARN+, while a dedicated file receives all matching events. If an event was already dropped at a layer before the appender, the dedicated appender cannot recover it.

## 5. Filter Results: Binary and Three-State

In JUL, the java.util.logging.Filter interface has an isLoggable(LogRecord) method returning a **boolean**:

- **true:** this filter allows the record to proceed to the corresponding processing step;
- **false:** the record is rejected by the filter at that point.

Logback and Log4j 2 use a common mechanism with three outcomes:

| Outcome | Basic meaning |
| --- | --- |
| **DENY** | Reject the event at the layer being evaluated |
| **NEUTRAL** | Undecided; continue evaluating subsequent conditions/filters |
| **ACCEPT** | Accept at the current filter stage according to backend rules |

**NEUTRAL does not mean DENY.** If a filter does not match and returns NEUTRAL, the decision is typically passed to the next filter or the default rule. Conversely, **ACCEPT is not a guarantee that the event has been durably written**: a later layer or the appender itself may still reject or fail to write it.

For Logback appender filters, filters run in order: DENY stops and drops the event; ACCEPT stops that appender's filter chain and lets the event proceed; NEUTRAL continues to the next filter. For Log4j 2, detailed semantics depend on the stage. For example, a global filter returning ACCEPT may affect the initial level check, but downstream filters and output destinations still have a say. Therefore, do not use ACCEPT arbitrarily to "force" every message to be logged.

## 6. Standalone Java 17+ Example: Filtering with java.util.logging

The following example uses **JUL**, the logging API built into the JDK. It demonstrates two independent layers: the logger allows all levels; the handler accepts INFO and above and uses a filter to drop healthcheck messages.

Create the file **LogFilterDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogFilterDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.orders");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        // This handler prints to stdout so results are easy to inspect.
        Handler console = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " | " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        console.setLevel(Level.INFO);
        console.setFilter(record ->
                !record.getMessage().startsWith("healthcheck:"));

        logger.addHandler(console);

        try {
            logger.fine("debug details");      // dropped by handler: below INFO
            logger.info("order=42 created");  // accepted
            logger.info("healthcheck: ok");   // rejected by filter
            logger.warning("payment delayed");// accepted
        } finally {
            logger.removeHandler(console);
            console.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac LogFilterDemo.java
java LogFilterDemo
~~~

Stdout:

~~~text
INFO | order=42 created
WARNING | payment delayed
~~~

Why are there exactly two lines in the output?

1. The logger sets Level.ALL, so FINE, INFO, and WARNING calls all qualify at the **logger layer**.
2. The Handler sets Level.INFO. Therefore, FINE is not printed even though the logger allows it.
3. The Filter on the Handler inspects the LogRecord and drops messages starting with healthcheck:.
4. WARNING does not match the drop condition, so it passes through the Handler.
5. setUseParentHandlers(false) disables forwarding to the root handler, preventing extra lines from being accidentally printed with the default format.

**Important technical detail:** Our custom Handler.publish() must call isLoggable(record). This Handler method checks both the level and the Filter attached to the Handler. If a custom handler omits this step, setLevel/setFilter may not take effect as expected. For built-in JDK handlers, the library handles this according to each handler's implementation.

This example intentionally places the **filter on the Handler**. JUL also supports Logger.setFilter(Filter). If an event is dropped at the logger, handlers never get a chance to receive it; whereas a filter on a handler only controls that handler's output.

## 7. Example: Changing Policy Without Changing Log Calls

Suppose the new requirement is to accept **all INFO logs and above**, and no longer drop healthchecks:

~~~java
// Illustrative snippet using the variables from the example above.
console.setFilter(null);       // Remove the content filter.
console.setLevel(Level.INFO);  // Keep the INFO threshold.
~~~

If you want to check **only WARNING events and above** at the handler:

~~~java
// Illustrative snippet, not a standalone program.
console.setLevel(Level.WARNING);
~~~

If you want to drop messages starting with "healthcheck:" across **all handlers** belonging to a JUL logger, you can set the filter on the logger instead of on each handler:

~~~java
// Illustrative snippet, where the logger is being configured.
logger.setFilter(record ->
        !record.getMessage().startsWith("healthcheck:"));
~~~

However, string filtering on LogRecord.getMessage() is suitable only for learning and simple experiments. In production systems, getMessage() may be an **unformatted template** with accompanying parameters; do not rely on this matching approach to verify that all sensitive data or message variants have been masked.

## 8. Logback: Appender Filters and TurboFilter

Logback Classic commonly serves as the backend for applications calling SLF4J. Logback has two main filter groups:

- **Standard appender filters:** operate on an already-created ILoggingEvent and are attached to a specific appender. If the CONSOLE appender drops an event, another FILE appender can still receive that event.
- **TurboFilter:** attached to the LoggerContext and can evaluate log calls very early, with parameters such as logger, level, marker, format, and arguments. TurboFilter is useful when an early decision is needed before creating a LoggingEvent; its ACCEPT/DENY/NEUTRAL outcome can interact with level checks according to Logback's mechanism.

### 8.1. ThresholdFilter: Keep WARN and Above

Example **logback.xml** file:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
      <level>WARN</level>
    </filter>
    <encoder>
      <pattern>%-5level %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

ROOT=DEBUG allows loggers to create DEBUG and higher events under normal policy. However, the **CONSOLE appender** has a WARN ThresholdFilter, so it drops DEBUG/INFO and lets WARN/ERROR proceed. Because the filter is placed at the appender, another appender without this filter can still receive INFO/DEBUG.

Result table at CONSOLE when no other filters are present:

| Event | Result |
| --- | --- |
| DEBUG | Dropped |
| INFO | Dropped |
| WARN | Accepted |
| ERROR | Accepted |

To change only the overall threshold for all destinations, setting ROOT=WARN is usually simpler. Appender filters are appropriate when **different destinations need different thresholds**.

### 8.2. LevelFilter: Accept Exactly One Level

If the requirement is to output only WARN and **not ERROR** on an appender, use LevelFilter:

~~~xml
<!-- Place inside Logback's <appender> element. -->
<filter class="ch.qos.logback.classic.filter.LevelFilter">
  <level>WARN</level>
  <onMatch>ACCEPT</onMatch>
  <onMismatch>DENY</onMismatch>
</filter>
~~~

The snippet above is a fragment of **logback.xml** and must be placed properly inside an appender; it is not a standalone XML file. When an event has level WARN, the filter returns ACCEPT. Other levels, including ERROR, return DENY. Do not substitute LevelFilter for ThresholdFilter if you want to keep both warnings and errors.

### 8.3. Combining Multiple Filters

Logback appender filters use a three-state mechanism. If filter A returns NEUTRAL, filter B can continue evaluating the event; if A returns DENY, the event stops; if A returns ACCEPT, remaining filters on that same appender are skipped.

For example: filter A rejects only healthcheck and returns NEUTRAL for other events; filter B blocks all levels below WARN. Result: healthcheck is dropped, and the remaining events are printed only if they are WARN or above.

You must check the rules of each filter type: a filter returning ACCEPT too early can prevent subsequent filters from being applied. Filter ordering is part of the policy.

## 9. Log4j 2: Filters at Multiple Locations

Log4j 2 Core supports filters at:

1. **Context/global:** evaluated early before processing logger configurations.
2. **LoggerConfig:** applies conditions on the corresponding logger or logger group.
3. **AppenderRef:** applies when routing an event from a logger to a referenced appender.
4. **Appender:** applies at the output destination itself.

Placing filters earlier generally helps avoid the cost of event creation, context capture, formatting, and queuing into an async queue; however, it can also make the event disappear from **all destinations**. Placing filters at the appender allows per-destination policies, at the cost of some logging work already having occurred before the event reaches it.

Example **log4j2.xml** so that CONSOLE receives only WARN and above:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <ThresholdFilter level="warn"
                       onMatch="NEUTRAL"
                       onMismatch="DENY"/>
      <PatternLayout pattern="%-5p %c - %m%n"/>
    </Console>
  </Appenders>

  <Loggers>
    <Root level="debug">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

ThresholdFilter at the appender returns DENY for levels below WARN; for WARN and above, NEUTRAL lets the event continue through the appender pipeline. In this configuration, there is only one filter at the appender, so qualifying WARN/ERROR events go out to the console.

You can also use **MarkerFilter**, **ThreadContextMapFilter**, **RegexFilter**, and other Log4j 2 filters depending on the data to inspect. For filters with onMatch/onMismatch, pay attention to the default values of **that specific filter type** and the difference between ACCEPT and NEUTRAL; do not assume that omitting onMismatch means the event will always proceed.

**Do not copy Logback XML directly to Log4j 2** or vice versa. For example, Logback uses the class ch.qos.logback.classic.filter.ThresholdFilter in a filter class element; Log4j 2 uses the ThresholdFilter XML plugin with its own attributes.

## 10. Spring Boot: Is logging.level a Filter?

In a Spring Boot application, you can control log levels per package/logger via **application.properties**:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.org.springframework.web=WARN
~~~

Or via **application.yml**:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
~~~

The logging.level properties adjust **logger thresholds**. They do not create conditions like "drop healthcheck but keep all other INFO logs." To filter by content, marker, or MDC at the appender, use **backend configuration** (typically logback-spring.xml when Spring Boot uses Logback), or controlled integration code.

You should also avoid enabling DEBUG on the entire ROOT logger just because you need one package. Enabling only the specific logger under investigation avoids generating excessive log volume and accidentally exposing sensitive information from other libraries.

## 11. When One Event Has Multiple Destinations

Consider a system with:

~~~text
                    +--> CONSOLE (WARN+ only)
Logger INFO --------|
                    +--> APP_FILE (INFO+)
                    |
                    +--> AUDIT_FILE (events with AUDIT marker)
~~~

A business INFO event may not appear on CONSOLE yet still be present in APP_FILE. An event with the AUDIT marker can additionally be sent to AUDIT_FILE if the logger, filters, and additivity/appenderRef are configured appropriately.

Therefore, separate three questions when someone says "a log was filtered":

- **Not created from the log call?** Check the logger level and early filters.
- **Created, but did not reach a specific appender?** Check appender references, additivity, and that appender's filters.
- **Received by the appender, but missing in the centralized system?** Check write errors, async queues, file rotation, agent/collector, ingestion delay, and search queries.

A filter configured on CONSOLE does not ensure the event disappears from FILE. Conversely, an early filter dropping an event can deprive all appenders of the chance to receive it. In multi-destination systems, clearly document the **scope of each filter**.

## 12. When Should You Write a Custom Filter?

Use logger levels or built-in filters if you only need:

- A WARN/ERROR threshold;
- Exactly one level;
- Matching markers or context fields using built-in features;
- Simple filtering by package or target appender.

Write a custom filter if the rule requires a truly stable business expression that built-in mechanisms cannot express—such as throttling progress events when status=RUNNING while always keeping events when status=FAILED.

A custom filter should have the following characteristics:

- **Fast execution:** avoid database/network calls, long locks, heavy formatting, or external data lookups on every log call.
- **Thread-safe:** it can be invoked from multiple threads, especially with high-performance and async logging.
- **Testable:** clear conditions, including missing context, null values, or invalid formats.
- **Defined error behavior:** decide upfront whether to pass or block when the filter throws an exception. Do not silently drop critical events.
- **No recursive logging:** logging inside a filter using the same logger/backend can cause infinite loops or deadlocks.
- **Independent metrics:** when dropping many events, count the dropped events rather than reporting only through the very pipeline being filtered.

Do not cram full business logic or access control into logging filters: filters decide log visibility, not business execution permissions.

## 13. Filtering, Sampling, and Data Requiring Durable Storage

With high volumes of repetitive events, filters can be combined with sampling or rate limiting to reduce costs. However:

- Sampling intentionally drops a portion of events; you no longer have complete logs to count exact business occurrences by counting log lines.
- If you need to measure request counts or error counts, use dedicated metrics/counters and properly designed tracing.
- For audits, financial transactions, or mandatory evidence, **do not use a filter capable of dropping events or an in-memory logging queue as the sole data source**. Use a durable storage channel with acknowledgments, retry/duplicate handling, and access policies.
- If filtering by tenant/user, ensure you do not turn metadata containing sensitive identifiers into high-cardinality metric labels or leak information in reports.

In production environments, clearly define which events may be dropped and which must be stored completely. Dropping all logs below WARN can reduce immediate costs, but it also loses the event sequence needed to investigate the root cause of an ERROR.

## 14. Filters Are Not a Mechanism for Masking Sensitive Data

A dangerous misconception is: "I have a filter that drops logs containing the word password, so I can log the entire request body."

This is false. Filters only check patterns anticipated by the developer; secret data may reside in another field, use a different name, come from another library, or reach another appender before the filter runs.

To protect data:

1. **Never put secrets into a LogEvent at the source.** Avoid logging passwords, auth tokens, API keys, session cookies, or full payment data.
2. For data that must be logged yet protected, use a **structured masking/redaction** pipeline in a reliable location and test edge cases.
3. Check all log destinations, including console, files, application errors, collectors, and temporary debug records.
4. Restrict access permissions, retention periods, and log searchability according to data policies.

Filters can support an information protection policy, but **they cannot replace the rule of not logging sensitive data in the first place**.

## 15. Testing Filters with an Event Matrix

Do not only test that a line is dropped; verify that lines **meant to be kept** are not accidentally discarded.

For the sample policy "logger INFO+, console WARN+, file INFO+ excluding healthchecks", the expected matrix is:

| Event | Logger | Console | File |
| --- | --- | --- | --- |
| DEBUG, order detail | Not created | No | No |
| INFO, order created | Passed | No | Yes |
| INFO, healthcheck: ok | Passed | No | No |
| WARN, payment slow | Passed | Yes | Yes |
| ERROR, payment failed | Passed | Yes | Yes |

This is an illustrative policy; the backend must configure levels and filters at the appropriate layers to produce the results in the table.

How to test:

1. Emit events with a **unique eventCode and testRunId** at TRACE/DEBUG/INFO/WARN/ERROR depending on the backend version.
2. Attach a valid set of context values (MDC/ThreadContext), and also test missing-context and invalid-context cases.
3. Observe each destination: console, file, or mock appender; do not inspect only one place and draw conclusions about the entire pipeline.
4. Test exact thresholds (WARN vs. ERROR), match/mismatch conditions, multi-filter ordering, and additivity effects.
5. With async appenders, wait for drain/flush or close the context properly before comparing event counts.
6. Measure overhead under load: if regex filters or complex checks run on every event, compare latency and throughput before and after.
7. Test context loss across thread pools/async boundaries, filter return values on null inputs, and configuration changes across different instances.

Compare using event IDs and event types rather than matching entire lines containing constantly changing timestamps or thread names.

## 16. Common Pitfalls When Configuring Filters

### Enabled DEBUG but no DEBUG lines appear

Check the logger name, effective level, global filters, logger filters, appenderRef, appender filter/threshold, and destination. If an earlier layer drops the event, raising the level at a downstream appender cannot recover it.

### WARN appears, but ERROR disappears

You may be using a **LevelFilter matching exact WARN** with onMismatch=DENY instead of a **ThresholdFilter WARN**. Test one WARN and one ERROR independently to confirm.

### Filtered healthcheck on console, but it still appears in the file

The filter is on the CONSOLE appender, while FILE is a separate appender. To adjust multiple destinations, place the policy at the right layer, taking care not to drop events needed for auditing or investigation.

### Wrote a custom handler, but setFilter has no effect

With JUL, if a handler implements publish() itself without calling isLoggable(record), the handler may bypass both the filter and the threshold. Review the handler implementation and compare it with the Java example above.

### Logs appear to be dropped, but actually just arrived late

With asynchronous logging, events may still be sitting in the queue, not yet flushed, or not yet indexed by the collector. Do not conclude a filter dropped the event without checking both queue state and the receiving destination.

### Filter is active, yet CPU usage remains high

If the filter is placed only at the end of the pipeline on the appender, event creation, argument evaluation, context capture, or encoding may have already occurred. For high-cost operations, consider appropriate levels or early filtering based on backend capabilities. However, early optimization must preserve the required observability policy across destinations.

### Filtering by message, but regex does not match

The message may be an unformatted template, contain newline characters, or have been modified by a layout; depending on the layer, the API may receive the raw format and arguments rather than the final string. Prefer markers/eventCode or structured fields, and test with real data at the exact layer.

## 17. Checklist Before Deploying Filters to Production

- [ ] Clear filtering goal: reduce noise, reduce cost, or split logs by destination?
- [ ] Exact scope identified: logger, entire context, appenderRef, or a single appender?
- [ ] Level, filter, and additivity ordering known for the backend/version in use.
- [ ] Difference understood between **exact single level** and **level threshold and above**.
- [ ] Match, mismatch, NEUTRAL behavior, and filter ordering clearly defined.
- [ ] Tests exist for keeping WARN/ERROR, inverse conditions, and missing context.
- [ ] Filtered logs are not used to infer exact transaction counts; metrics exist where needed.
- [ ] Filters are not relied upon to protect secrets; sensitive data is avoided at the source.
- [ ] A way exists to observe dropped event counts and revert configuration during incident investigation.

**Remember:** A log filter is a **rule for accepting or rejecting an event at a specific point in the logging pipeline**. To use it correctly, you must understand **the filtering condition, the layer where it applies, and the output destination** simultaneously; an event dropped at one destination is not necessarily dropped at all destinations.

## References

- [Oracle Java SE 17 — java.util.logging.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html): Filter.isLoggable(LogRecord).
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): Handler level, setFilter, and isLoggable.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html): Appender filter, TurboFilter, ACCEPT/DENY/NEUTRAL.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html): filter application points, three-state outcomes, and processing order.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging.level and logging backend configuration.
