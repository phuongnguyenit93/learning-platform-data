# OFF and ALL in Java Core Logging

## 1. Learning Objectives

In a logging system, **OFF** and **ALL** are two special values at opposite ends of the log level scale. They are typically used as **configuration thresholds**: OFF to stop accepting regular logging events; ALL to avoid filtering out events solely due to priority level. Understanding both values accurately is essential when you need to reduce noisy logs, investigate incidents, or diagnose why a log record does not appear.

After this lesson, you will be able to:

- Distinguish between an **event's severity level** (INFO, WARNING, FINE, etc.) and the **filtering threshold** set on a Logger or Handler.
- Accurately explain the meaning of **java.util.logging.Level.OFF** and **Level.ALL** in Java Util Logging (JUL).
- Understand how Level, Filter, Handler, and parent/child Loggers work together to decide whether a record is emitted.
- Use OFF and ALL in Java 17+ code and **logging.properties** configuration.
- Identify situations where OFF does not disable all child loggers and ALL does not cause every record to be printed automatically.
- Choose safe configurations when operating applications, avoiding the loss of investigative data or the generation of excessive logs.

**Scope:** This lesson focuses on **log levels** in Java Core Logging, using JUL as a standalone example. Frameworks such as Logback and Log4j 2 have similar concepts, but they have their own APIs, configurations, and processing pipelines.

## 2. Logging Thresholds vs. Event Severity Levels

An application typically emits log records at levels such as SEVERE, WARNING, INFO, FINE, and FINEST. When a record is emitted, the Logger compares the event's level against the Logger's **effective level** threshold.

For standard JUL levels, the order from highest threshold to lowest is:

| JUL Level | Numeric Value (intValue) | Common Interpretation |
| --- | ---: | --- |
| **OFF** | 2,147,483,647 | Disables log acceptance at this threshold; special control value |
| **SEVERE** | 1,000 | Serious failure |
| **WARNING** | 900 | Abnormal condition requiring attention |
| **INFO** | 800 | Operational information |
| **CONFIG** | 700 | Configuration information |
| **FINE** | 500 | Debugging detail |
| **FINER** | 400 | More detailed |
| **FINEST** | 300 | Very high level of detail |
| **ALL** | -2,147,483,648 | Allows all levels at the threshold check; special control value |

**Key takeaway:** **OFF** and **ALL** differ from severities such as WARNING or INFO. They primarily represent **controls for accepted levels**, not business event categories that you should assign to a log line. In code, emit events at INFO, WARNING, SEVERE, FINE, etc., and reserve OFF/ALL for configuration.

You can think of a threshold as a gate:

~~~text
Record level:      SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST

INFO threshold:    accepts SEVERE, WARNING, INFO; drops CONFIG, FINE, FINER, FINEST
FINE threshold:    accepts SEVERE ... FINE; drops FINER and FINEST
ALL threshold:     does not drop standard records solely for having too low a level
OFF threshold:     blocks regular logging records at that point
~~~

The numeric scale helps JUL compare thresholds. **However, you should not write your own numeric comparison and assume it replaces the full logging algorithm**: Logger, Handler, and Filter also have their own contracts, in which OFF is treated as a special disable level. For example, calling **logger.log(Level.OFF, "message")** is not a standard way to emit an event and can produce confusing behavior. Avoid using OFF or ALL as an event's severity.

## 3. Level.OFF: Disabling Logging at a Checkpoint

**Level.OFF** means **disabling the acceptance of regular log events** at the Logger or Handler configured with that level.

Example:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.service");
logger.setLevel(Level.OFF);

logger.info("Starting service");
logger.warning("Fallback activated");
logger.severe("Database unavailable");
~~~

This is an **illustrative snippet**, not a standalone Java program because it has no class or main method. Once the Logger is set to OFF, regular calls at INFO, WARNING, and SEVERE are not accepted by this Logger. Even SEVERE is blocked: OFF does not mean "disable DEBUG only."

Points to note:

1. **OFF applies to the configured Logger**, and can affect child Loggers that **inherit** that level.
2. If a child Logger **has its own explicit level**, it can still accept records even when the parent Logger is set to OFF. Do not treat a parent's OFF as a global kill switch for all descendants.
3. **Handlers also have their own levels**. A Handler set to OFF will not output regular logging records even if the Logger allowed them through.
4. **OFF does not delete previously written logs**, does not remove files, and does not block other telemetry sources such as metrics/traces or loggers outside the configured scope.
5. If you want to completely disable logging for **a component**, you must identify the exact loggers, handlers, libraries, and pipelines that actually emit or receive that component's events.
6. Turning off logs with OFF can cost you clues when troubleshooting errors. Use it purposefully, within a clear scope, and with a plan to restore it.

### 3.1. OFF Does Not Mean the Highest Error Level

A common misconception is "OFF is above SEVERE, so only extremely critical errors will be logged." In JUL, **OFF represents disabled**, not an error threshold "higher than SEVERE" that lets the application keep selecting more severe events. In practice, **there is no standard event level higher than SEVERE that you should use to bypass OFF**.

If the requirement is "log only critical errors," set **Level.SEVERE**, not OFF:

~~~java
logger.setLevel(Level.SEVERE);
logger.severe("Unrecoverable task failure"); // Accepted by Logger.
logger.warning("Retrying");                   // Rejected by Logger.
~~~

When should you use OFF? For example, when you are running a bounded operation and want to temporarily silence an experimental logger that produces too much unhelpful noise, then restore the level according to the standard configuration.

## 4. Level.ALL: Allowing a Logger or Handler to Accept All Levels

**Level.ALL** means that at the **level checkpoint set to ALL**, all regular event levels are eligible to proceed:

~~~java
Logger logger = Logger.getLogger("demo.service");
logger.setLevel(Level.ALL);

logger.severe("Service failed");
logger.info("Service started");
logger.fine("Query arguments prepared");
logger.finest("Low-level tracing detail");
~~~

However, **ALL does not mean all of the lines above are guaranteed to be printed to the console or a file**. It only removes the level-filtering threshold on that Logger. A record must still pass through other steps: the Logger's Filter if present, the corresponding Handler, the Handler's level, the Handler's Filter, the formatter, the sink, and the collection pipeline.

For example, if the Logger is set to ALL while ConsoleHandler remains at INFO, **FINE** and **FINEST** records will be dropped by the Handler. This is a very common situation when developers "enabled ALL but still don't see debug logs."

### 4.1. ALL Does Not Mean Unlimited Resource Logging

ALL is a configuration level, **not a policy guaranteeing delivery of every record** across the entire system. Other factors can prevent a record from reaching its destination:

- A Filter rejects the record based on content or attributes.
- No Handler is attached to the Logger, or the Logger does not forward records to parent handlers.
- The Handler level is higher than the record level.
- A queue/async appender is full, a collector fails, or an exporter loses its connection.
- The backend applies sampling, rate limiting, or retention rules.
- The code never invokes logging on the execution branch being inspected.

Enabling ALL broadly—especially in event-heavy libraries or tight loops—can generate a **massive log volume**, impacting I/O, CPU, storage capacity, latency, and query costs. When you only need details for one package, target that specific Logger/package and enable it only for the duration of the investigation.

## 5. Combined Effect of Logger and Handler: Passing Both Layers

JUL typically involves at least two important threshold layers:

- **Logger level:** filters before the event is dispatched to Handlers.
- **Handler level:** filters per output destination. A Logger can dispatch to multiple Handlers, and each Handler has its own policy.

The following table assumes standard-level records, no additional Filters, and that records are actually forwarded to the Handler:

| Logger level | Handler level | INFO Record | FINE Record | SEVERE Record | Conclusion |
| --- | --- | --- | --- | --- | --- |
| **OFF** | ALL | No | No | No | Logger blocks |
| **ALL** | INFO | Yes | No | Yes | Handler blocks FINE |
| **ALL** | ALL | Yes | Yes | Yes | Not blocked by level |
| **INFO** | ALL | Yes | No | Yes | Logger blocks FINE |
| **ALL** | OFF | No | No | No | Handler blocks |
| **WARNING** | FINE | No | No | Yes | Logger enforces higher threshold |
| **FINE** | WARNING | No | No | Yes | Handler enforces higher threshold |

When no filters are involved, an emitted record must generally **pass both thresholds**. However, you should not try to invent a single application-wide "effective level": with multiple Handlers, each destination has its own threshold and filter.

Illustrative processing flow:

~~~text
Code calls logger.fine("query.detail")
      |
      v
Logger: level = ALL?
  | yes
  v
Does Logger Filter allow it?
  | yes
  v
Handler A (console): level = INFO  -> FINE is blocked
Handler B (file):    level = ALL   -> FINE is written if B's Filter allows it
~~~

This is why an event can appear in a file without appearing on the console, or vice versa.

## 6. Standalone Java 17+ Example: Verifying OFF, ALL, and Inheritance

The program below uses only **java.util.logging** from the JDK. It creates a Handler that prints to **stdout** with a simple inline format inside the publish method so accepted records are easy to see. The Handler calls **isLoggable(record)** itself to honor the configured level and filter.

Create the file **OffAllLevelsDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class OffAllLevelsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.off.all");
        logger.setUseParentHandlers(false);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName() + " | " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
        handler.setLevel(Level.INFO);
        logger.addHandler(handler);

        try {
            logger.setLevel(Level.OFF);
            logger.severe("off.severe");
            System.out.println("logger OFF: " + logger.isLoggable(Level.SEVERE));

            logger.setLevel(Level.ALL);
            logger.fine("all.fine");
            logger.info("all.info");

            handler.setLevel(Level.ALL);
            logger.finest("all.finest");

            logger.setLevel(Level.WARNING);
            logger.info("warning.info");
            logger.warning("warning.warning");

            handler.setLevel(Level.OFF);
            logger.severe("handler.off.severe");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        Logger parent = Logger.getLogger("lesson.parent");
        parent.setLevel(Level.OFF);
        Logger child = Logger.getLogger("lesson.parent.child");
        child.setLevel(null);
        System.out.println("child inherits OFF: " + child.isLoggable(Level.INFO));

        child.setLevel(Level.INFO);
        System.out.println("child overrides: " + child.isLoggable(Level.INFO));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 OffAllLevelsDemo.java
java OffAllLevelsDemo
~~~

**Actual stdout**, compiled/run and verified:

~~~text
logger OFF: false
INFO | all.info
FINEST | all.finest
WARNING | warning.warning
child inherits OFF: false
child overrides: true
~~~

### 6.1. Step-by-Step Explanation

**Step 1 — Logger is set to OFF.** Calling **logger.severe("off.severe")** emits no record because the Logger is disabled. **logger.isLoggable(Level.SEVERE)** returns false, so the first line is **logger OFF: false**.

**Step 2 — Logger is set to ALL, Handler remains INFO.** **logger.fine("all.fine")** passes the Logger's level check, but the Handler with an INFO threshold drops FINE. **logger.info("all.info")** passes both thresholds, so it is printed.

**Step 3 — Handler is also switched to ALL.** **logger.finest("all.finest")** passes both Logger and Handler, so it appears in the output.

**Step 4 — Logger is set to WARNING.** INFO is blocked immediately at the Logger, while WARNING is accepted and printed.

**Step 5 — Handler is set to OFF.** SEVERE still passes the Logger's WARNING threshold, but the Handler set to OFF drops it. There is no **handler.off.severe** line in the output.

**Step 6 — Checking parent/child relationship.** The parent Logger is set to OFF; the child Logger initially has **level = null**, meaning it **inherits the effective level from its parent**, so **isLoggable(INFO)** returns false. Once the child is explicitly set to **Level.INFO**, the check returns true, regardless of the parent being OFF.

### 6.2. Why Does the Example Use a Custom Handler?

The example uses a small custom Handler to **precisely control stdout**, without depending on the default formatting, timestamps, thread names, or stderr output of ConsoleHandler. **setUseParentHandlers(false)** also prevents records from appearing additionally through the root logger's Handlers.

This illustrative Handler is **not a production sink**: it does not handle complex I/O errors, backpressure, or multi-threaded synchronization. Use ConsoleHandler, FileHandler, or an appropriate logging backend in real applications. If you write a custom Handler, you must follow the publish/flush/close contract and use ErrorManager when needed.

## 7. OFF/ALL and Level Inheritance Between Loggers

JUL organizes Loggers in a parent/child hierarchy based on their names. A Logger can have a **directly configured level**, or **level = null** to inherit its effective level from the nearest configured ancestor.

Example:

~~~text
Logger: com.example                 setLevel(OFF)
    |
    +-- com.example.payment         level = null (inherits OFF)
    |
    +-- com.example.order           setLevel(INFO) (own level)
~~~

Consequences:

- **com.example.payment** does not accept regular log events because its effective level is OFF.
- **com.example.order** can accept INFO events and above because it has its own INFO level.
- Another child Logger can be configured to ALL; in that case, it does not inherit the parent's OFF for its own level check.
- **Logger.getLevel() == null** does not mean ALL. It means the Logger **does not have its own level**, and you must inspect its ancestors to determine its effective level.
- **Logger.setLevel(null)** is how you return a child Logger to inheritance mode. Do not apply this arbitrarily to the root logger, because the root logger requires an explicit level under the JUL contract.

**An important subtlety:** JUL forwards records up to **parent Logger Handlers** when useParentHandlers is enabled. Having a parent level of OFF **does not necessarily cause a record already accepted by a child Logger to be re-filtered by the parent logger**; the parent's Handlers still have their own levels and filters. Therefore, you should not assume you can "turn off an entire namespace" just by setting a parent Logger to OFF while child Loggers still have their own levels. Specify thresholds for each child Logger and each Handler when designing your policy.

## 8. Configuration in logging.properties

JUL can load its configuration from a **logging.properties** file, allowing you to change thresholds without modifying logging calls in business code.

Example:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

com.example.noisy.level = OFF
com.example.diagnostics.level = ALL
~~~

Explanation:

- **.level = INFO** sets the level for the root logger.
- **ConsoleHandler.level = INFO** ensures the console only outputs records meeting the INFO threshold, even if an individual Logger is set to ALL.
- **com.example.noisy.level = OFF** disables regular logging for that Logger and any child Loggers that actually inherit OFF.
- **com.example.diagnostics.level = ALL** allows the diagnostics Logger to accept very detailed levels; however, because **ConsoleHandler is at INFO**, FINE, FINER, and FINEST will still not appear on the console.
- Depending on any additional attached handlers and the useParentHandlers setting, logs may still reach other destinations with different thresholds.

To allow the console to receive FINEST as well, you can change:

~~~properties
java.util.logging.ConsoleHandler.level = ALL
~~~

Limit **ALL to the specific Logger/package needing diagnosis**, and avoid setting the root logger to ALL in high-traffic environments unless you have a clear reason and an appropriate log budget.

Example command to launch a compiled application:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This command **illustrates how to specify a JUL configuration file**; it assumes you have a **com.example.Main** class and an **out** directory containing the compiled bytecode, so it is not the command to run the OffAllLevelsDemo in Section 6. If the application calls **logger.setLevel(...)** itself after loading the configuration, the level can be overridden by code. Configuration and reload workflows also depend on how the application initializes LogManager and which backend is in use.

### 8.1. "I Set ALL in Properties, Why Don't I See FINE?"

Check in the following order:

1. Was the configuration file actually loaded by the JVM at the right time? Is the path in **-Djava.util.logging.config.file** correct?
2. Does the Logger emitting the record have the exact expected name and position in the logger hierarchy?
3. Does any code call **setLevel** after the configuration is loaded?
4. What is the Logger's effective level? Does **isLoggable(Level.FINE)** return true or false?
5. Which Handler is receiving the record? Is **Handler.getLevel()** still INFO?
6. Is there a Filter on the Logger or Handler rejecting the record? Does the Logger forward to parent Handlers?
7. Did the record reach the destination only to be transformed or dropped later by an encoder, async pipeline, or collector?

If **logger.isLoggable(Level.FINE)** is true but there is no output, that is a sign to inspect the **Handler/Filter/output destination**, rather than repeatedly setting the Logger to ALL.

## 9. Comparison with Popular Logging Frameworks

The concepts **OFF = disabled** and **ALL = catch-all threshold** also appear in several modern logging backends. However, their APIs and configurations differ:

| Logging System | Common Place for OFF/ALL | Notes |
| --- | --- | --- |
| **java.util.logging (JUL)** | **java.util.logging.Level.OFF**, **Level.ALL** | Built into the JDK; Logger and Handler have separate levels |
| **Logback** | Logback Level, logger/root/appender configuration | Filtering policy also passes through appenders, filters, and encoder settings |
| **Log4j 2** | Level.OFF, Level.ALL in API/Core and configuration | Events must pass through logger configuration, filters, appenders, etc. |
| **SLF4J** | SLF4J is a **facade**; the provider controls level configuration | Do not assume a **logger.setLevel(ALL)** method exists on SLF4J's Logger API |

When using SLF4J, you typically emit common levels such as ERROR, WARN, INFO, DEBUG, and TRACE through the facade; OFF and ALL live primarily in the **backend configuration**. Do not copy JUL class names, properties syntax, or bridge behavior directly to Logback or Log4j 2.

**Specifically:** "ALL" in a backend does not mean retaining every piece of telemetry. After a log is created, appender layers, async queues, collectors, or storage systems may still apply filters, sampling, or rate limits. Setting "OFF" on a logger in one backend also does not necessarily disable logging from a library using a different backend.

## 10. Choosing OFF, ALL, or an Intermediate Level?

| Need | Configuration to Consider | Reason |
| --- | --- | --- |
| Only want to see critical errors | **SEVERE** | Keeps important error signals while dropping lower levels |
| Want standard operational logs | **INFO** | Balances observability and log volume for most systems |
| Investigating an issue in one package | **FINE / FINER / FINEST** or narrowly scoped **ALL** | Gathers extra detail without increasing volume everywhere |
| Temporarily silencing a noisy logger | **OFF** with a clear scope | Suppresses records from that logger when policy permits |
| Want all levels through a diagnostic sink | **Logger ALL + Handler ALL**, plus check Filters | Both source and destination must accept the records |
| Want no output from one specific Handler | **Handler OFF** | Blocks only that destination; the Logger may still have others |

There is no single "best" level for every environment. Threshold selection should be based on event value, system criticality, traffic volume, logging cost, and retention/audit requirements.

**Note on auditing:** If a system is required to record mandatory security or transactional events, do not use OFF arbitrarily in a way that drops those records. Diagnostic logging and audit logging may have different durability, access control, and transport requirements.

## 11. Common Misconceptions and Pitfalls

### Pitfall 1 — Treating OFF as "Disable DEBUG Only"

**Wrong:** Setting OFF because you want to hide FINE lines while still seeing SEVERE.  
**Right:** Use **INFO**, **WARNING**, or **SEVERE** depending on what you want to keep. OFF disables regular logging at that configuration point.

### Pitfall 2 — Treating ALL as "Force Every Record to Appear"

**Wrong:** Setting Logger.ALL and concluding the system is dropping logs because FINE does not appear.  
**Right:** Also check the Handler level, Filters, parent handler configuration, destination, async pipeline, and where you are looking for logs.

### Pitfall 3 — Confusing null with ALL

**Wrong:** Assuming Logger.getLevel() returning null means ALL by default.  
**Right:** null means the level is **inherited** from the parent Logger. The parent might be at INFO, OFF, or another level.

### Pitfall 4 — Believing OFF on a Parent Always Disables All Child Loggers

**Wrong:** Setting only **com.example** to OFF when some child Loggers already have their own INFO/ALL levels set.  
**Right:** Verify the effective level of each Logger you need to manage; also consider parent Handlers when records are forwarded.

### Pitfall 5 — Setting OFF on One Handler While Forgetting Multiple Destinations

**Wrong:** Thinking that setting one Handler to OFF stops the application from emitting any records, while the Logger still has another active Handler.  
**Right:** A Handler's OFF blocks only **that destination**. To control actual output, check all handlers/appenders and bridges.

### Pitfall 6 — Leaving ALL Enabled Long-Term Where Sensitive Data Exists

**Wrong:** Enabling ALL system-wide and logging raw request bodies, tokens, or personally identifiable information.  
**Right:** Protect data at the point of emission, use low-level logging for limited durations, narrow the scope, and enforce access control and retention policies. OFF/ALL are **threshold controls**, not data-protection mechanisms.

### Pitfall 7 — Assuming OFF Deletes History

**Wrong:** Setting OFF and expecting existing records in files or backends to disappear.  
**Right:** OFF affects only events *after the configuration takes effect*. Retaining or deleting historical data is a separate responsibility of storage and retention policies.

### Pitfall 8 — Mixing JUL Levels with Logging from Other Libraries

**Wrong:** Setting JUL root to ALL to control every library even when some use a different backend.  
**Right:** Identify the actual API, provider/bridge, and backend for each library, and configure them at the proper layer.

## 12. How to Test OFF/ALL Configurations Yourself

**Experiment A — Testing the Logger.** In the program from Section 6, keep the Handler at ALL and set the Logger sequentially to OFF, SEVERE, INFO, FINE, and ALL. Emit one INFO and one FINE record each time. Record which ones the Logger accepts.

**Experiment B — Testing the Handler.** Keep the Logger at ALL and switch the Handler between OFF, INFO, and ALL. Observe FINE being dropped by the INFO Handler even though the Logger accepted it.

**Experiment C — Testing Inheritance.** Create a parent Logger set to OFF; create a child Logger with level null, then call setLevel(INFO). Compare the result of isLoggable(INFO) before and after.

**Experiment D — Testing Filters.** Add a Filter to the Handler that rejects records with the prefix "health.". Even with both Logger and Handler at ALL, records rejected by the Filter will not appear.

**Experiment E — Testing Log Volume.** Over a repeated operation, compare the record count and processing time with INFO versus ALL enabled. Do not use numbers from a tiny example to extrapolate production performance; benchmark against your actual backend and workload.

When testing, use **logger.isLoggable(Level.FINE)** to check the Logger's level gate, but **do not treat a true result as proof that the record will reach the destination**. To verify output, you must observe the actual Handler or sink.

## 13. Self-Assessment Questions

**Question 1:** Logger is OFF, Handler is ALL. Does a regular SEVERE record reach the Handler?  
**Answer:** No. The Logger rejects the event at the first step.

**Question 2:** Logger is ALL, Handler is INFO. Is a FINE record printed?  
**Answer:** It does not pass the INFO Handler. Logger ALL only clears the level check at the Logger layer.

**Question 3:** Parent Logger is OFF, child Logger has its own INFO level. What does isLoggable(INFO) return on the child Logger?  
**Answer:** It typically returns **true** (as verified in the demo program), because the child Logger uses its own level. Whether the record reaches a destination still depends on Handlers, Filters, and propagation.

**Question 4:** If Logger.getLevel() returns null, is the Logger set to ALL?  
**Answer:** No. It is inheriting its level from its parent.

**Question 5:** To keep only WARNING and SEVERE, should you choose OFF, ALL, or WARNING?  
**Answer:** **WARNING**, while also ensuring the Handler does not enforce a higher threshold.

**Question 6:** Does OFF erase logs saved from yesterday?  
**Answer:** No. OFF controls acceptance of new events after the configuration takes effect; historical logs are managed by storage and retention policies.

**Question 7:** Why can enabling ALL broadly cause incidents?  
**Answer:** A sharp increase in record volume can drive up CPU, I/O, memory, storage, cost, and latency, and can inadvertently expose sensitive data if the application does not sanitize what it logs.

## 14. Key Takeaways

**OFF = disabled at the configured threshold. ALL = allows all levels at the configured threshold.** Both are primarily **configuration levels**, not severities to attach to business events.

In JUL, for a record to be emitted, it must be permitted by both the Logger and the Handler, and not blocked by Filters or downstream transport steps. **OFF on a parent Logger does not automatically lock child Loggers that have their own levels**, and **ALL on a Logger cannot force an INFO Handler to print a FINE record**.

When designing a configuration, always specify **which logger, which handler, which level, which destination, and for how long**. That is how to use OFF and ALL both accurately from a technical standpoint and safely in operations.
