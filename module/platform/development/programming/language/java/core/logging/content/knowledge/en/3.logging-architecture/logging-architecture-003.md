# Log Filter in Java Logging Architecture

## 1. What Is a Log Filter?

In a logging system, a **log filter** is the component that decides whether an already created log record may proceed to a log output destination. The filter receives information about the event, applies a condition, and returns **allow** or **discard**.

For example: a system generates many logs for a health-check endpoint. These records can be useful during diagnostics, but sending all of them to a centralized log store creates a lot of noise. A filter can drop periodic events known to be safe while keeping application errors, business outcomes, and signs of anomalies.

Filters help:

- **Reduce noise:** drop repetitive events or diagnostic information not needed for a specific output.
- **Control log volume:** avoid pushing every record to the console, file, or log collector.
- **Route by destination:** some events need to go to multiple destinations, while others are only needed for diagnostic destinations.
- **Preserve valuable signals:** focus on errors, state changes, and developments that need to be searched.

A filter is **not synonymous** with a log level. A level classifies severity or verbosity; a filter expresses additional conditions, such as excluding health-check events, accepting only records from a specific component, or allowing only one event type into a handler. A filter also **does not automatically mask sensitive data**: dropping an entire record is not a substitute for designing safe log data.

## 2. Where Does a Filter Sit in the Logging Architecture?

In Java SE, the **java.util.logging (JUL)** API provides the **java.util.logging.Filter** interface, which can be attached to a **Logger** or a **Handler**.

~~~text
Application code
   |
   | logger.log(...) / logger.info(...)
   v
Originating Logger
   |
   +-- Check Logger's effective log level
   |       Not met -> discard record
   |
   +-- Logger's Filter (if present)
   |       false -> discard record before Handlers
   |
   +-- Handler A
   |      +-- check Handler A's level
   |      +-- Handler A's Filter (if present)
   |      +-- Formatter -> console
   |
   +-- Handler B
   |      +-- check Handler B's level
   |      +-- Handler B's Filter (if present)
   |      +-- Formatter -> file/collector
   |
   +-- Parent Logger's Handlers if useParentHandlers=true
          +-- check each Handler's level and Filter
          +-- Formatter -> corresponding output
~~~

In the diagram above, each Handler has its own policy, so a record can be accepted by Handler A but discarded by Handler B.

Make sure to distinguish the following points clearly:

1. **A Filter attached to a Logger** controls records entering the processing flow of the invoked Logger itself. If it rejects a record, the Handlers receiving logs from that call do not receive the record.
2. **A Filter attached to a Handler** only controls the output of that corresponding Handler. It does not automatically block the remaining Handlers.
3. **The Logger's level** is checked before the record is passed down to Handlers. If the Logger does not let INFO through, setting a Handler's level to ALL will not recover the INFO record.
4. **The Handler's level** is a separate threshold. If the Logger allows FINE but the Handler is at INFO, the FINE record will still not be emitted by that Handler.
5. If **useParentHandlers=true**, the record can also be sent to the Handlers of parent Loggers. When forwarding the record up this Handler chain, JUL does not by default re-invoke each parent Logger's Filter as if the application had logged on the parent Logger; the parent's Handlers apply their own filters.
6. If **logger.log(...)** is called directly on a parent Logger, that parent Logger's Filter still takes effect. Do not confuse this with propagating a child Logger's record to the parent's Handlers.

The last point often causes configuration bugs: placing a Filter on a parent Logger and assuming that Filter automatically blocks all logs from every child Logger. To filter reliably at **a shared output**, attach the Filter to the Handler receiving those records; to filter right at **the source**, attach the Filter to the appropriate Logger.

## 3. The Filter Interface and Inspectable Data

JUL defines Filter as a functional interface with a single method:

~~~java
public interface Filter {
    boolean isLoggable(java.util.logging.LogRecord record);
}
~~~

This is an **illustrative signature** of the standard interface; when writing an application, import **java.util.logging.Filter**—there is no need to redeclare this interface yourself.

Return values:

- **true**: the record passes the filter at the attached point and can continue processing.
- **false**: the record is discarded at that point.
- Passing a Filter **does not guarantee** the log is emitted: there are still level thresholds, other Handlers, other Filters, formatters, output configurations, and write capability.

**LogRecord** holds the data of a logging event. Commonly used properties:

| Component | JUL API | Usage |
| --- | --- | --- |
| Log level | record.getLevel() | Check INFO, WARNING, SEVERE, FINE, etc. |
| Raw message | record.getMessage() | Identify a fixed event name |
| Logger name | record.getLoggerName() | Filter by named component/package |
| Parameters | record.getParameters() | Retrieve structured context passed by the application |
| Attached exception | record.getThrown() | Distinguish whether the record has a Throwable |
| Timestamp | record.getInstant() | Timestamp information of the record |
| Source class and method name | record.getSourceClassName(), getSourceMethodName() | Can be useful, but not always available or cheap to infer |

For instance, a filter that only lets records at WARNING or above pass can be written as:

~~~java
Filter warningsAndErrors = record ->
        record.getLevel().intValue() >= Level.WARNING.intValue();
~~~

This is an **illustrative snippet**; you need to import Filter and Level and attach it to a Logger or Handler. In practice, if you only need a WARNING threshold, **setLevel(Level.WARNING)** is simpler and usually more appropriate. Filter is meant for additional conditions that Level alone cannot express.

A good Filter should be **fast, deterministic, have minimal side effects**, and define a policy for missing fields. Do not perform database queries, network calls, or write other logs inside a Filter; if a Filter logs through the same pipeline, it can cause recursion.

## 4. How Do Level and Filter Differ?

| Aspect | Level | Filter |
| --- | --- | --- |
| Question | Is the record important enough to be considered? | Does this record satisfy a specific condition? |
| Primary criterion | Predefined severity/verbosity scale | Content, source, event, context, or policy |
| JUL | Logger.setLevel(), Handler.setLevel() | Logger.setFilter(), Handler.setFilter() |
| Expressiveness | E.g., accept INFO and above | E.g., drop health.ping but keep other INFO |
| Cost | Simple threshold comparison | Depends on filter logic |
| Scope | Each Logger/Handler has its own threshold | Each Logger/Handler has its own Filter |

In JUL, common levels in descending order of severity (increasing verbosity) are **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**. There are also **ALL** and **OFF** for threshold configuration. Do not use the numeric value of a log level to infer business rules: an INFO event may be critical for understanding an outcome, while a specific WARNING may just be noise from a test environment.

Configuration behavior example:

~~~text
Logger level = ALL
Logger Filter = exclude health.ping event
Handler console level = INFO
Handler console Filter = exclude INTERNAL category

FINE cache.lookup       -> Logger passes -> Handler drops due to level
INFO health.ping        -> Logger Filter drops
INFO cache.warmup       -> Logger passes -> Handler Filter drops
INFO order.created      -> Logger passes -> Handler passes
WARNING inventory.slow  -> Logger passes -> Handler passes
~~~

## 5. Standalone Java 17+ Example: Filters on Logger and Handler

The example below creates events with **event**, **requestId**, and **category** fields. We use an **Event record** (supported in Java 17) passed via **LogRecord.setParameters()**, allowing the Handler's Filter to inspect the event category without parsing free-form message strings.

Rules:

- The Logger drops the **health.ping** event; other events may proceed.
- The Handler only accepts records at **INFO or above**.
- The Handler drops the **INTERNAL** category.
- The Formatter outputs a fixed single-line format, making it easy to verify the exact result.
- The Handler writes to **stdout**; JUL's default ConsoleHandler normally writes to **stderr** and uses a different format.

Save the entire program as **LogFilterDemo.java**:

~~~java
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogFilterDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.filter");

    private enum Category {
        SYSTEM, BUSINESS, INTERNAL, DEPENDENCY
    }

    private record Event(String name, String requestId, Category category) {}

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Filter sourceFilter =
                record -> !"health.ping".equals(record.getMessage());
        LOG.setFilter(sourceFilter);

        Handler console = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                Event event = eventOf(record);
                if (event == null) {
                    return record.getLevel().getName() + " | "
                            + record.getMessage() + System.lineSeparator();
                }
                return record.getLevel().getName()
                        + " | event=" + event.name()
                        + " requestId=" + event.requestId()
                        + " category=" + event.category()
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        console.setLevel(Level.INFO);
        console.setFilter(record -> {
            Event event = eventOf(record);
            return event == null || event.category() != Category.INTERNAL;
        });
        LOG.addHandler(console);

        try {
            emit(Level.FINE, "cache.lookup", "req-42", Category.BUSINESS);
            emit(Level.INFO, "health.ping", "req-42", Category.SYSTEM);
            emit(Level.INFO, "cache.warmup", "job-7", Category.INTERNAL);
            emit(Level.INFO, "order.created", "req-42", Category.BUSINESS);
            emit(Level.WARNING, "inventory.slow", "req-42",
                    Category.DEPENDENCY);
        } finally {
            LOG.removeHandler(console);
            console.flush();
        }
    }

    private static void emit(
            Level level, String name, String requestId, Category category) {
        Event event = new Event(name, requestId, category);
        LogRecord record = new LogRecord(level, event.name());
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] {event});
        LOG.log(record);
    }

    private static Event eventOf(LogRecord record) {
        Object[] parameters = record.getParameters();
        if (parameters != null && parameters.length == 1
                && parameters[0] instanceof Event event) {
            return event;
        }
        return null;
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac LogFilterDemo.java
java LogFilterDemo
~~~

**Exact stdout:**

~~~text
INFO | event=order.created requestId=req-42 category=BUSINESS
WARNING | event=inventory.slow requestId=req-42 category=DEPENDENCY
~~~

### Step-by-Step Explanation for Each Record

| Call | Logger level | Logger Filter | Handler level | Handler Filter | Outcome |
| --- | --- | --- | --- | --- | --- |
| FINE cache.lookup | Pass (ALL) | Pass | Below INFO | Not evaluated | Not emitted |
| INFO health.ping | Pass | Rejected by event | Not received | Not received | Not emitted |
| INFO cache.warmup, INTERNAL | Pass | Pass | Pass | Rejected INTERNAL | Not emitted |
| INFO order.created, BUSINESS | Pass | Pass | Pass | Pass | Emitted INFO line |
| WARNING inventory.slow, DEPENDENCY | Pass | Pass | Pass | Pass | Emitted WARNING line |

**Key technical points to understand:**

1. **LOG.setUseParentHandlers(false)** prevents parent Logger Handlers from emitting extra records, ensuring the example has exactly one destination and avoids duplicate logs from inherited configuration.
2. **LOG.setLevel(Level.ALL)** only opens the Logger's threshold. It does not bypass the Filter, and it does not change the Handler's threshold.
3. **LOG.setFilter(sourceFilter)** applies the rule to exclude the `health.ping` event name at the point of origin.
4. **console.setLevel(Level.INFO)** prevents FINE from being printed, even though the Logger allows the FINE level.
5. **console.setFilter(...)** drops records in the INTERNAL category only on this console Handler. If another Handler is attached, that Handler will have its own level and Filter.
6. **LogRecord.setParameters()** passes an Event object into the record. The example uses typed metadata for demonstration; this is not a built-in automatic JSON structured logging mechanism in JUL.
7. **eventOf(record)** handles the case where no Event is present and returns null. For external logs that do not follow the application's format, the policy in this example is to let them pass the Handler Filter; in production, you must explicitly choose the behavior when metadata is missing.
8. Overriding **publish()** and calling **flush()** makes StreamHandler flush each line to stdout. A standard StreamHandler is buffered. The example does not close the handler that uses `System.out` because closing it could also close the program's stdout stream.
9. The Formatter here intentionally builds a deterministic string for verification, avoiding timezone-dependent date/time formats or JUL's default formatting. Therefore, the stdout above is stable.
10. Filters operate on an already constructed record; do not treat a Filter as a way to avoid all costs of building a LogRecord or evaluating arguments. Logger thresholds and lazy logging APIs where appropriate remain important for performance.

## 6. Where Should You Place a Filter for Your Goal?

### Filtering at the Logger: Drop an Event Type Right at the Source

For example, if a service has a dedicated Logger for heartbeats, you can attach a Filter to that exact Logger emitting the event if no destination needs heartbeats. For health checks, sometimes the best approach is **not to create an INFO log in the first place**, only logging unhealthy states or abnormal situations. When the application still has to log some heartbeats for other purposes, a Filter helps adjust this at runtime.

Use a Logger Filter when the criteria must affect **every Handler receiving records from calls on that originating Logger**. Do not assume that configuration on a parent Logger automatically filters all calls emitted from child Loggers.

### Filtering at the Handler: Each Log Destination Has Its Own Policy

Example:

~~~text
                       Order-processing Logger
                                |
                        Logger Filter: pass
                                |
                +---------------+---------------+
                |                               |
          Console Handler                 File Handler
         level=WARNING                    level=INFO
         filter=all categories            filter=exclude INTERNAL
                |                               |
         Technical alerts                 Operational records
~~~

The same business INFO record can be saved to a file without appearing on the console; a WARNING can go to both outputs. **A Handler Filter cannot make a Logger regenerate a record that was already dropped by the Logger level or Logger Filter.**

This is an architectural example, not a complete program snippet.

### Routing and Filtering Are Two Different Things

A Filter only decides **pass or reject**. It does not select a new Handler, change the level, transform the record, or move the record to another file. To route to multiple destinations, you must configure separate Handlers and policies, or use a logging framework/pipeline with corresponding routing capabilities.

## 7. Common Ways to Write a Filter

The following snippets are **illustrative patterns**, not standalone programs. They assume the required types are imported and the corresponding Logger/Handler objects are already available.

**a) Filter by Logger name**

~~~java
Filter serviceOnly = record -> {
    String name = record.getLoggerName();
    return name != null
            && (name.equals("com.example.orders")
                || name.startsWith("com.example.orders."));
};
~~~

Include a trailing dot after the package name to avoid mistakenly matching names with a similar prefix, such as `ordersLegacy`. When a LogRecord is created manually by the application, the Logger name can be null if the emitter did not set it; decide explicitly how to handle that case.

**b) Filter by exact event name**

~~~java
Filter excludePing =
        record -> !"health.ping".equals(record.getMessage());
~~~

If the message contains text translated via ResourceBundle, parameters, or free-form strings, using **getMessage()** to identify an event can be brittle. Prefer an application-controlled event code and an explicit metadata model, such as the Event example above.

**c) Filter by attached exception**

~~~java
Filter withThrowable = record -> record.getThrown() != null;
~~~

This filter only accepts records created with a **Throwable attached to the LogRecord**. A message string that merely contains the word "Exception" does not make `getThrown()` non-null. Do not use a Throwable-only policy for business flows, as it will drop many events valuable for investigation.

**d) Filter by event category**

~~~java
Filter businessOrDependency = record -> {
    Event event = eventOf(record);
    return event != null
            && (event.category() == Category.BUSINESS
                || event.category() == Category.DEPENDENCY);
};
~~~

This snippet relies on the **Event, Category** types and the **eventOf** helper from the LogFilterDemo example. If metadata is missing, it returns false. This policy differs from the Handler Filter in the main program, which lets records without an Event pass; no single choice fits every system.

## 8. Decision Sequence and Common Misconceptions

To troubleshoot why a log does not appear, follow this order:

1. Did the logging call actually execute? If guarded by an external condition or an unreached branch, the Filter is not involved.
2. Did the originating Logger meet the level? Did it inherit a threshold from a parent Logger?
3. Does the originating Logger have a Filter, and did that Filter return false?
4. Which Handlers received the record? Does **useParentHandlers** allow forwarding to parent Logger Handlers?
5. What level does the corresponding Handler have? Does it have its own Filter, and what did that Filter decide?
6. Are the Handler's formatter and stream/file/collector working properly? Are there write errors, buffering issues, or output configuration problems?

**Diagnostic example:** an application sets the Logger level to FINE, the Handler level to INFO, and adds a Filter that accepts FINE. When FINE logs disappear, the cause is the **Handler level**, not the Filter. Conversely, when INFO for `health.ping` disappears in the sample program, the cause is the **Logger Filter**, even though the Handler allows INFO.

Another mistake is **filtering at the Logger while intending to filter only one destination**. When you need to suppress an event on the console while still saving the record to a file for investigation, place the condition on the Console Handler; do not filter at the originating Logger, because the file will lose that record too.

## 9. Designing Safe and Effective Filters in Production

### Do Not Lose Critical Evidence

A careless filter rule can mask incidents. For example, filtering out all events whose path contains `health` will accidentally drop failed health-endpoint logs as well. Filter by **specific event codes** and distinguish successful heartbeats from abnormal warnings, instead of relying on generic substrings.

Retain logs for severe errors, state changes needed for investigation, and security events according to organizational policy. For an **audit trail**, requirements may include complete event coverage, tamper controls, retention, and access control; do not use sampling-style operational filters to drop mandatory audit records.

### Rules for Records with Missing Fields

Before deploying a Filter, clearly define:

- If `eventName`/`category`/`requestId` is missing, should it pass to avoid losing logs, or be rejected to protect a specialized output stream?
- If the level is SEVERE but the category is INTERNAL, is it allowed to be dropped?
- If a new event appears after a version upgrade, could the Filter mistakenly drop it?

**Fail-open** (allowing through when metadata is missing) reduces the risk of losing investigative logs, but can introduce noise. **Fail-closed** (dropping when metadata is missing) is useful for streams that only accept valid structured events, but risks dropping new events. Choose based on the purpose of the log destination rather than applying a single policy blindly.

### Sensitive Data and Log Injection

A Filter can block an **entire** record when a rule triggers, but it does not strip `password` or `token` fields from accepted records. Do not put secrets or sensitive payloads into a LogRecord at the source; use data minimization, masking, and an appropriate encoder when controlled data must be output.

Avoid filter conditions that concatenate unvalidated user input into regexes or message strings, especially data containing control characters or newlines. Use fixed event codes and handle escaping in the formatter/encoder. A Filter alone does not prevent log injection if accepted records still contain malicious content.

### Cost and Concurrency

In high-throughput applications, a Filter can be invoked frequently and concurrently. Therefore:

- Prefer simple comparisons on event codes or normalized data categories.
- Avoid network queries, I/O, heavy locks, expensive regexes, and heavy computation inside `isLoggable()`.
- If using stateful counting or sampling, ensure thread-safety; plain variable increments are not safe when updated by multiple threads.
- Verify stability when the Filter is called concurrently; ideally, configuration is immutable and logic has no side effects.
- Apply sampling only to high-volume logs with low individual value. Do not arbitrarily sample warnings or errors that require per-event investigation.
- Do not log a new message inside a Filter to explain why a record was dropped: this can create a logging loop and cause a spike in overhead.

If you want to reduce the cost of building diagnostic messages, check the **level** before constructing expensive messages and use the appropriate Supplier overload, such as **logger.fine(() -> expensiveDescription())**. A Filter may be called after record creation; it does not fully replace economical logging design.

## 10. JUL Filter vs. SLF4J, Logback, and Log4j 2

Distinguish between the **API** and the **backend**:

| Technology | Relevant Role |
| --- | --- |
| java.util.logging (JUL) | API and implementation built into Java SE; uses Filter on Logger/Handler |
| SLF4J | Facade for applications to call logging; has no single backend-agnostic Filter rule identical to JUL |
| Logback | Popular backend with SLF4J; has Filter on appenders and TurboFilter on the context, with its own semantics |
| Log4j 2 | API/backend with filters at multiple points such as LoggerConfig and Appender, following the framework's ACCEPT/DENY/NEUTRAL rules |
| Log collector/agent | Can filter after the application emits logs; does not fully save the initial record creation and write cost |

Do not copy JUL's **Logger.setFilter(Filter)** API directly into SLF4J/Logback or Log4j 2 code and expect it to compile. When using another framework, check that framework's filter mechanism, evaluation order, and attachment points.

**Practical case:** a Spring Boot application typically logs through SLF4J and uses Logback by default across many versions. To reduce HTTP health-check logs in such an application, inspect the Logger, appender/filter, or HTTP access log configuration that is actually emitting the records, rather than adding a JUL Filter to a Logger that is not on the real logging path.

## 11. Testing a Filter as an Operational Policy

A good Filter not only has the right condition, but also avoids accidentally dropping important events.

Use a small test matrix with clear input conditions and expected outcomes:

| Case | Level | Event | Category | Expected in Sample Program |
| --- | --- | --- | --- | --- |
| Cache detail | FINE | cache.lookup | BUSINESS | Not emitted due to Handler level |
| Health check | INFO | health.ping | SYSTEM | Not emitted due to Logger Filter |
| Internal task | INFO | cache.warmup | INTERNAL | Not emitted due to Handler Filter |
| Business success | INFO | order.created | BUSINESS | Emitted |
| Slow dependency | WARNING | inventory.slow | DEPENDENCY | Emitted |
| Record without Event | INFO | unknown.message | none | Formatter uses fallback branch; sample Filters let it pass |

When adding a new child Logger or Handler, also test **Handler inheritance scope**. A Filter working on the console Handler is not automatically applied to the file Handler. And a Filter placed on a parent Logger is not by default applied to records originating from a child Logger when those records are only forwarded to the parent Logger's Handlers.

Measure log volume, cost, and traceability again after enabling a Filter. If you reduce line count but can no longer explain why a request failed, the filtering policy has not met its goal.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking Filter and Level are the same | Cannot find why logs are dropped | Check both level and Filter on Logger/Handler |
| Setting Handler level to ALL to rescue logs already blocked by Logger | Logs are still lost | Adjust the originating Logger's level or Filter |
| Placing Filter only on parent Logger | Logs from child Loggers can still reach parent Handlers | Attach Filter at the source to filter or on the shared Handler |
| Placing Filter on originating Logger when only console filtering is wanted | File and other Handlers lose the logs too | Filter specifically on the Console Handler |
| Relying on arbitrary text strings | Condition breaks easily when messages or locales change | Use stable event codes and metadata |
| Dropping every log containing the word "health" | Can hide health-check failures | Filter only specific success events |
| Mechanically dropping WARNING/SEVERE for internal categories | Loses warnings needed for investigation | Define exceptions to retain severe errors and mandatory audits |
| Treating Filter as a secret masker | Accepted logs still contain sensitive data | Minimize data at source and use proper encoders/masking |
| Performing I/O or logging inside isLoggable() | Slow, recursive, or hard-to-diagnose errors | Keep Filter simple, fast, and side-effect-free |
| Not testing multiple Handlers or child Loggers | Policy behaves differently than expected | Test the Logger/Handler/Filter matrix and propagation to parent Loggers |

## 13. Checklist When Implementing a Log Filter

1. Identify the **log destination** and why events need to be excluded: console, file, collector, or all.
2. Classify signals to retain: business outcomes, technical errors, warnings, security events, and audits.
3. Choose **Level** for simple thresholds; choose **Filter** when conditions depend on events/metadata.
4. Decide whether to place the Filter at the **originating Logger** or a **specific Handler**; check **useParentHandlers**.
5. Use stable event names and structured information; define a clear policy for records with missing fields.
6. Keep the Filter lightweight, thread-safe, free of I/O, and free of recursive logging.
7. Test both kept and dropped events; verify against the actual output of each Handler.
8. Measure log volume and verify that failed requests or critical events remain traceable.
9. Review filtering rules when adding endpoints, changing Loggers, adding Handlers, or switching logging backends.

**Conclusion:** A log filter is a link in the logging pipeline that decides which records reach a destination. Understanding the boundary **Logger Filter → Handler level/Filter → Formatter/output** helps eliminate noise while preserving critical data for operations and incident investigation.
