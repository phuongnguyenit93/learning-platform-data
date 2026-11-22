# Logging Levels in Java

## 1. What is a logging level?

A **logging level** is a label that indicates the severity or level of detail of an event recorded in an application's log. Log levels help developers and operators decide what information should appear in each environment, from critical error messages to very detailed execution traces.

For example, the same ordering application might log:
- **ERROR / SEVERE:** Unable to persist the order because the database is not responding.
- **WARN / WARNING:** The first call to the payment service timed out, but the retry succeeded.
- **INFO:** The application has started, or the order has transitioned to the completed state.
- **DEBUG / FINE:** Which processing branch was selected and how many records were read.
- **TRACE / FINER / FINEST:** Internal steps and intermediate values used when investigating hard-to-diagnose bugs.

Log level names depend on the API or framework. Java includes **Java Util Logging (JUL)** in the **java.util.logging** package. Other applications may log through **SLF4J** and forward to a backend such as Logback or Log4j 2. These level sets are similar in purpose, but their names do not match identically and there is no exact one-to-one mapping.

## 2. Levels in java.util.logging

The **java.util.logging.Level** class defines standard levels ordered from most severe to most detailed. Each level has a numeric value; a larger number represents a higher priority when filtering logs.

| JUL Level | Value | Meaning and usage |
| --- | ---: | --- |
| **SEVERE** | 1000 | Serious failure: an important operation failed, or a service or component is not functioning properly. |
| **WARNING** | 900 | An unusual or potentially risky situation, though the application can still continue or recover. |
| **INFO** | 800 | Notable business or lifecycle events during normal operation. |
| **CONFIG** | 700 | Configuration information useful for diagnostics, such as the selected cache strategy; do not log configuration secrets. |
| **FINE** | 500 | Relatively general debugging information. |
| **FINER** | 400 | More detailed execution flow, such as steps within an algorithm. |
| **FINEST** | 300 | Very fine-grained detail, which should only be enabled selectively when deep tracing is needed. |
| **OFF** | 2147483647 | A special value used to turn off logging by threshold. |
| **ALL** | -2147483648 | A special value used to allow all standard levels through the threshold. |

**OFF** and **ALL** are configuration values, not two types of business events to be logged regularly. JUL also allows defining custom **Level** instances; the table above lists the standard levels.

Some guidelines for choosing levels:
- A request rejected **in accordance with business rules** is not automatically a severe error. You can use INFO, FINE, or not log it at all, depending on observability needs.
- A **recoverable** error is usually appropriate for WARNING; an error that causes an essential function to fail is usually appropriate for SEVERE.
- Detailed debug data should not be pushed into INFO just to make it easy to see: that reduces the value of operational logs and increases storage costs.
- Level choices should be consistent with actual impact. Do not classify every exception as SEVERE simply because it is an exception.

## 3. Threshold-based filtering mechanism

When a JUL log threshold is set to a certain level, only events with a level **equal to or higher than the threshold** are eligible to be logged.

| Logger Threshold | Standard levels that can pass the Logger filter |
| --- | --- |
| **WARNING** | WARNING, SEVERE |
| **INFO** | INFO, WARNING, SEVERE |
| **CONFIG** | CONFIG, INFO, WARNING, SEVERE |
| **FINE** | FINE, CONFIG, INFO, WARNING, SEVERE |
| **FINER** | FINER, FINE, CONFIG, INFO, WARNING, SEVERE |
| **FINEST** or **ALL** | All seven normal levels |
| **OFF** | No normal events logged |

The JUL model has **two key places where filtering happens**:

1. **Logger** decides whether to create and publish a record at the requested level. When calling **logger.setLevel(null)**, the Logger inherits the effective level from its parent Logger.
2. **Handler** receives the record passed to it, then applies its own threshold and filter before outputting to the console, a file, or another destination.

Therefore, enabling **FINE** on the Logger does not guarantee that FINE lines will appear: if **ConsoleHandler** still has an **INFO** threshold, the Handler can drop that record. A record can also be dropped by a **Filter** or due to Handler routing configuration. In practice, when you "don't see debug logs", check the Logger, the Handler, and whether the Logger forwards records to its parent Logger.

## 4. Standalone Java 17 example

Create a file named **LoggingLevelsDemo.java** with the following code. The example explicitly disables parent Logger Handlers, sets the Logger level to **FINE**, lets the Handler accept **ALL**, and uses a simple formatter so the output is consistent across runs.

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingLevelsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(LoggingLevelsDemo.class.getName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);

        logger.severe("Không thể lưu cấu hình");
        logger.warning("Kết nối đang chậm");
        logger.info("Ứng dụng sẵn sàng");
        logger.config("Chế độ kiểm tra đã tắt");
        logger.fine("Đã tải 3 bản ghi");
        logger.finer("Chi tiết vòng lặp");
        logger.finest("Giá trị tại từng bước");

        handler.flush();
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 LoggingLevelsDemo.java
java LoggingLevelsDemo
~~~

Output displayed on **stderr** (ConsoleHandler writes to stderr by default, not stdout):

~~~text
SEVERE | Không thể lưu cấu hình
WARNING | Kết nối đang chậm
INFO | Ứng dụng sẵn sàng
CONFIG | Chế độ kiểm tra đã tắt
FINE | Đã tải 3 bản ghi
~~~

The two **finer** and **finest** calls do not appear because they are below the Logger's **FINE** threshold. If you change it to **logger.setLevel(Level.WARNING)**, only the SEVERE and WARNING lines remain. If you keep the Logger at FINE but change it to **handler.setLevel(Level.WARNING)**, only those two lines remain as well. The example verifies that a record must pass both the Logger threshold and the Handler threshold.

To prevent multiple Handlers from logging the same message twice, you need to understand the meaning of **setUseParentHandlers(false)**: the Logger in the example outputs logs through the Handler just added, instead of continuing to forward records to the parent Logger's Handlers. In real-world applications, centralized configuration is usually preferred over creating Handlers manually in multiple classes.

## 5. Choosing log levels in real-world scenarios

| Scenario | Suggested Level | Reason |
| --- | --- | --- |
| Unable to complete a transaction because the storage system failed | SEVERE / ERROR | A critical function has failed and needs investigation. |
| A secondary service is slow, but a fallback succeeds | WARNING / WARN | An anomaly worth monitoring, though the main flow still works. |
| Server started successfully, scheduled job completed | INFO | Valuable operational milestones in a production environment. |
| Recording the selected configuration strategy or runtime mode | CONFIG (JUL) | Useful for understanding how the application is configured; avoid sensitive data. |
| Knowing which processing branch was taken or cache hit/miss during diagnostics | FINE / DEBUG | Details that should only appear when investigation is needed. |
| Tracing each parsing step, every tiny internal branch | FINER–FINEST / TRACE | High volume; can consume CPU, I/O, and storage space. |

These are **recommended conventions**, not rigid rules. For example, a client error caused by invalid input data can be a normal occurrence; logging it at ERROR under high traffic will generate many unnecessary alerts. Conversely, a rare event that indicates data loss must be logged at a prominent level.

**Do not use logging as an error-handling mechanism.** Logging supports observability; the application must still handle exceptions, return appropriate error codes, retry, or roll back according to its design. An error already handled at a lower layer may only need to be logged once at the responsible boundary, avoiding having the same exception appear multiple times across the system.

## 6. Parameterized logging, exceptions, and message creation cost

In JUL, use the **logger.log** method to specify the log level, pass parameters, or attach the error cause. The following example is an **illustrative snippet inside a method that already has a Logger**, not a standalone program:

~~~java
logger.log(Level.INFO, "Đang xử lý đơn hàng {0}", orderId);

try {
    readConfiguration();
} catch (java.io.IOException e) {
    logger.log(Level.SEVERE, "Không thể đọc cấu hình", e);
}
~~~

The **orderId** parameter will be formatted according to JUL's mechanism when supported by the Formatter. When passing a **Throwable** to the appropriate overload, the record preserves the stack trace; how it is displayed depends on the Formatter. You should not log only **e.getMessage()** if you need the cause, location, and stack trace for diagnostics.

For messages involving expensive computations, avoid constructing the string before the system determines whether that level is enabled. Java supports **Supplier** for lazy logging:

~~~java
logger.log(Level.FINE, () -> "Số phần tử: " + expensiveCount());
~~~

In this call, **expensiveCount()** is only evaluated when JUL determines that the FINE level can be logged at the Logger. An equivalent approach is to check **logger.isLoggable(Level.FINE)** before a complex debug block. Keep in mind that a Handler threshold or Filter can still drop the event after this step; lazy logging does not replace designing appropriate thresholds. The snippets above illustrate the API and assume the relevant variables/functions already exist.

## 7. How do JUL and SLF4J/Logback differ?

In many Java projects, business code uses **SLF4J** as a unified API; an actual logging system (usually Logback or Log4j 2) handles filtering, formatting, and delivering logs to storage. SLF4J commonly uses the following five levels, from most severe to most detailed:

**ERROR → WARN → INFO → DEBUG → TRACE**

You can use the following comparison table **by intent**, not as a mandatory mapping rule:

| JUL | Common SLF4J | Notes |
| --- | --- | --- |
| SEVERE | ERROR | Errors requiring attention. |
| WARNING | WARN | Unusual or risky situations. |
| INFO | INFO | Normal operational information. |
| CONFIG, FINE | DEBUG (approximate) | No separate CONFIG level in SLF4J; actual mapping is determined by the bridge/backend. |
| FINER, FINEST | TRACE (approximate) | Only a comparison in terms of granularity. |

SLF4J does not define a separate **FATAL** level in its common API; some other frameworks, such as Log4j 2, have additional levels. **Do not assume that every JUL–SLF4J bridge applies the table above line-for-line.** When configuring a bridge, check the library's actual mapping and thresholds.

Example of SLF4J syntax in a class that already has a Logger (illustrative, **requires SLF4J and backend dependencies**):

~~~java
log.error("Không thể lưu đơn hàng {}", orderId, exception);
log.warn("Thanh toán chậm, requestId={}", requestId);
log.info("Job hoàn tất: {} bản ghi", count);
log.debug("Kết quả cache: {}", cacheResult);
log.trace("Đang xét phần tử index={}", index);
~~~

Methods like these typically use the **{}** placeholder to separate data from the message template. This is not JUL's formatting syntax; JUL uses a different parameterization approach, such as **{0}** in messages supported by the Formatter. Do not mix the two placeholder styles.

## 8. Configuring log thresholds in an application

In JUL, besides calling **setLevel** in code, you can configure it using a properties file loaded by the JVM at startup. Example **logging.properties** file:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = ALL
com.example.service.level = FINE
~~~

Run the application with the corresponding package:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Meaning: the root Logger threshold is INFO; Loggers under **com.example.service** can enable FINE; ConsoleHandler is set to ALL so it does not block FINE records that child Loggers let through. Use your project's actual Logger/package names and ensure the classpath and main class name match. The command above is a configuration example, **not the command to run the LoggingLevelsDemo program above** because the demo program explicitly configures its own Logger and Handler.

With Logback or Log4j 2, the configuration file and syntax differ from JUL; the concepts remain similar: Logger thresholds and appenders, record propagation paths, filters, formatters/layouts, and log destinations. An environment typically starts at **INFO**, enabling DEBUG/TRACE only for components that need diagnostics and for an appropriate duration. The actual default level depends on the framework and application configuration, so you should not rely on assumptions in operations.

## 9. Common mistakes to avoid

1. **Confusing ERROR/WARN/DEBUG with JUL constants.** JUL uses SEVERE/WARNING/FINE..., while ERROR/WARN/DEBUG are common in SLF4J and related frameworks.
2. **Adjusting only the Logger and forgetting the Handler/appender.** A higher threshold at the log output layer can still block records.
3. **Logging every step at INFO or SEVERE.** This drowns out the signal of real errors and causes log volume to explode.
4. **Enabling FINEST/TRACE system-wide for long periods.** This can impact performance, cost, and expose unnecessary information.
5. **Logging sensitive information.** Never put passwords, tokens, secret keys, personal data, or full sensitive requests/responses into logs, regardless of level.
6. **Logging and then rethrowing the same exception across multiple layers.** This easily creates duplicate records and makes incident counting difficult. Choose the layer responsible for logging errors and preserve the stack trace when needed.
7. **Performing expensive string concatenation before checking the threshold.** Use parameterized APIs, Supplier, or **isLoggable** checks when appropriate.
8. **Omitting traceable context.** When needed, include request IDs, operation IDs, component names, and outcomes; avoid sensitive identifiers or overly verbose data.

## 10. Self-check

- If the Logger is at **Level.INFO** and ConsoleHandler is at **Level.FINE**, will a FINE message appear? **No**, because the Logger blocks it first.
- If the Logger is at **Level.FINE** and ConsoleHandler is at **Level.WARNING**, will an INFO message appear? **No**, because the Handler blocks it.
- When the application successfully handles a retry after a timeout, should you use WARNING or SEVERE? **Usually WARNING**, because there was an anomaly but it recovered; the final choice depends on the level of impact.
- If you want to see very detailed steps of an algorithm in JUL, what should you choose? **FINER/FINEST** on the Logger **and** configure the Handler to allow those levels.
- When using SLF4J, which level corresponds to general diagnostics? **DEBUG**; use **TRACE** when deeper detail is needed.

**Remember:** Logging levels are a tool for tuning the amount of information based on severity and investigation needs. Choosing the right level at the point where the event occurs, configuring all filtering layers properly, and protecting data in logs will make the system both easier to operate and easier to debug.
