# Placeholders in Java Log Messages

## 1. What is a placeholder?

When logging, we often want to keep a **fixed message template** and insert values that vary with each event. A **placeholder** is a marker position in a message template where the logging API substitutes argument values when building the displayed message.

Conceptual example:

```text
Template: orderId=<order-id> status=<status>
Values:   ORD-7, ACCEPTED
Output:   orderId=ORD-7 status=ACCEPTED
```

In the example above, `<order-id>` and `<status>` are just **illustrative** symbols. The actual placeholder syntax depends on the **logging API**. Two common forms in Java are:

| API/ecosystem | Template syntax | Call |
|---|---|---|
| SLF4J (often paired with Logback) | `{}`, substituted sequentially from left to right | `log.info("orderId={} status={}", orderId, status)` |
| Log4j 2 API with standard parameterized messages | `{}`, substituted sequentially | `log.info("orderId={} status={}", orderId, status)` |
| `java.util.logging` (JUL) | `{0}`, `{1}`, based on `MessageFormat` | `log.log(Level.INFO, "orderId={0} status={1}", new Object[]{orderId, status})` |

**Key takeaway:** `{}` and `{0}` are **not two equivalent ways of writing the same thing**. You cannot copy an SLF4J template into JUL and assume parameters will still be substituted. The backend, formatter, and library version also determine the exact way a message is rendered.

Placeholders make logging code easier to read, keep message structure consistent, and can avoid building the final string when a log level is disabled. However, passing arguments to a logger call **does not mean Java skips evaluating the argument expressions**; this is analyzed in section 6.

## 2. Why use placeholders instead of string concatenation?

Compare two ways of logging the same event in an application using SLF4J:

```java
// String concatenation:
log.debug("Loading order " + orderId + " from " + source);

// Placeholder:
log.debug("Loading order {} from {}", orderId, source);
```

With string concatenation, Java builds the resulting string **before calling** `debug(...)`, even when DEBUG events are not logged. With placeholders, the logger receives the template and arguments separately; if DEBUG is disabled, the backend can usually skip rendering the string and calling `toString()` on the arguments.

This is not only about performance:

- **Readability:** readers see a clear message template and the corresponding list of data.
- **Consistency:** similar events share the same template, making it easier to group log messages.
- **Preserved intent:** the code clearly separates fixed text from variable values.
- **Better tool integration:** some backends/collectors can additionally preserve the template and arguments; this depends on capabilities and configuration, and **does not happen automatically with every logger**.
- **Deferred message construction:** the API can decide when and how to format arguments, rather than letting the application's string concatenation decide immediately.

However, a placeholder is **not a SQL prepared statement**; it does not automatically prevent log injection, mask sensitive data, or turn message text into structured JSON. Those responsibilities still require separate design.

## 3. SLF4J: the `{}` placeholder

SLF4J is a **logging facade**; the application calls the SLF4J API, while the provider/backend performs the actual writing and formatting. In standard parameterized logging calls, `{}` represents the argument at the corresponding position.

### 3.1. Sequential argument substitution

```java
String orderId = "ORD-7";
String status = "ACCEPTED";
int quantity = 3;

log.info("orderId={} status={} quantity={}", orderId, status, quantity);
```

Message after rendering:

```text
orderId=ORD-7 status=ACCEPTED quantity=3
```

This is an **SLF4J illustrative snippet**, assuming the `log` variable has already been created and the backend is configured to log INFO. The output above is the **message part**, not the entire console line: the appender/layout may prepend the timestamp, level, logger name, and thread name.

Each `{}` consumes the next argument in order. It does not carry a name or index like JUL's `{0}`; if you need the same value in two places, pass that value twice:

```java
log.info("orderId={} relatedOrderId={}", orderId, orderId);
```

Avoid pairing placeholders with text whose positions are hard to understand:

```java
// Easy to read and search:
log.info("orderId={} paymentId={} result={}", orderId, paymentId, result);

// Hard to understand when only values are visible:
log.info("{} {} {}", orderId, paymentId, result);
```

A good message usually includes **field names or a verb describing the event**. Placeholders are only a mechanism for inserting values; they do not make a message meaningful on their own.

### 3.2. How are data types rendered?

In SLF4J, numeric, boolean, and object arguments are typically converted into an appropriate text representation. For custom objects, the result depends on `toString()` or the formatting mechanism of the API/backend.

```java
log.info("attempt={} success={}", 2, false);
log.info("customer={}", customer);
```

If `customer.toString()` returns a string containing too much information or sensitive data, the log may expose that data as well. It is usually better to log specific fields intentionally:

```java
log.info("customerId={} status={}", customerId, status);
```

For arrays, some SLF4J versions/formatting mechanisms handle elements or nested arrays; do not rely on `Object.toString()` as a standard business format. If the system needs a stable schema, use structured logging fields instead of converting an entire object into one long string.

### 3.3. Placeholders are not property names

The call:

```java
log.info("orderId={} status={}", orderId, status);
```

typically produces **a single rendered message** such as `orderId=ORD-7 status=ACCEPTED`. It **does not guarantee** that a collector will automatically receive two separate JSON fields named `orderId` and `status`.

If you need to store `orderId` as a field that can be filtered accurately, use **structured arguments, key–value pairs, MDC, or a structured logging mechanism** supported by your API/backend. Clearly distinguish:

- **Message template:** the text string containing placeholders.
- **Arguments:** the values used when rendering the template.
- **Structured fields:** name–value pairs written by the backend/encoder as separate fields, if configured.

## 4. JUL: `{0}` placeholders and `MessageFormat`

`java.util.logging` is built into the JDK. JUL does not use SLF4J's `{}` rule by default; for parameterized messages, `java.util.logging.Formatter.formatMessage(LogRecord)` uses `java.text.MessageFormat` rules when formatting.

Example:

```java
Logger logger = Logger.getLogger("com.example.orders");
logger.log(Level.INFO,
        "orderId={0} status={1}",
        new Object[]{"ORD-7", "ACCEPTED"});
```

The `{0}` pattern takes element 0 and `{1}` takes element 1 from the parameter array. Unlike SLF4J's `{}`, **the index is meaningful**: you can reorder or repeat a parameter in the template.

### 4.1. The link between LogRecord and Formatter

When emitting a JUL event, the logger stores the message template and parameters in a `LogRecord`. The Formatter determines the displayed string:

```java
// Inside a class extending java.util.logging.Formatter:
String raw = record.getMessage();          // Template, e.g. "orderId={0}"
String shown = formatMessage(record);      // Values substituted
```

These are **two illustrative lines inside a formatter**, not a standalone program. If you write a custom formatter and only use `getMessage()`, you may see literal `{0}` in the output. When you want the message with parameters substituted, use `formatMessage(record)`.

If the `LogRecord` has a resource bundle, `formatMessage` also handles looking up the message from the bundle before formatting. Keep in mind that this is a formatter step; calling `log.log(...)` does not mean the string is concatenated immediately at the call site.

### 4.2. Complete Java 17+ example with no external libraries

Create the file `PlaceholderDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PlaceholderDemo {
    private static final Logger LOG =
            Logger.getLogger(PlaceholderDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        String requestId = "req-42";
        String orderId = "ORD-7";

        LOG.log(Level.INFO,
                "requestId={0} orderId={1} status={2}",
                new Object[]{requestId, orderId, "ACCEPTED"});

        LOG.log(Level.WARNING,
                "orderId={0} retryAttempt={1}",
                new Object[]{orderId, 2});

        LOG.log(Level.INFO,
                "order ''{0}'' completed",
                new Object[]{orderId});

        LOG.log(Level.FINE,
                "hiddenDebug={0}",
                new Object[]{orderId});

        console.flush();
    }
}
```

Compile and run with JDK 17 or later from the directory containing the file:

```bash
javac -encoding UTF-8 PlaceholderDemo.java
java PlaceholderDemo
```

Console output:

```text
INFO requestId=req-42 orderId=ORD-7 status=ACCEPTED
WARNING orderId=ORD-7 retryAttempt=2
INFO order 'ORD-7' completed
```

These lines appear on **stderr** because JUL's `ConsoleHandler` writes to the standard error stream; **stdout has no output from this example**. There is no timestamp in the output because the example formatter only combines the level and message, making it easy to identify each line accurately.

Explanation:

1. `LOG.log(Level.INFO, template, Object[])` stores the template and parameters. `formatMessage(record)` substitutes `{0}`, `{1}`, and `{2}` in the specified order.
2. `retryAttempt={1}` receives the integer `2` and outputs `2` in this case.
3. `MessageFormat` treats a single quote as a syntax-quoting character. Write `''` to output **a single quote**: the template `"order ''{0}'' completed"` produces `order 'ORD-7' completed`.
4. `Level.FINE` is lower than `Level.INFO`, so the `hiddenDebug` event does not appear; both the logger and handler are set to INFO.
5. `LOG.setUseParentHandlers(false)` prevents duplicate output from events also propagating to parent handlers in the example; it does not change placeholder syntax.

**Note on `MessageFormat`:** besides `{0}`, it supports patterns like `{0,number}` and `{0,date}` with locale rules. Number/date formats can vary by locale or timezone, so when consistent output across servers is needed, choose an explicit convention. Do not assume a custom message formatter will understand all of this syntax if it bypasses `formatMessage`.

### 4.3. Common JUL call mistakes

```java
// Not a valid JUL parameter placeholder:
LOG.info("orderId={}");

// This is just a text string containing two curly braces.
// Use JUL's template and parameterized API:
LOG.log(Level.INFO, "orderId={0}", "ORD-7");
```

The snippet above illustrates the call patterns; it assumes `LOG` already exists and the INFO level is enabled. With `LOG.info("orderId={0}")` without passing parameters, there is no value to insert: the formatter cannot guess the order ID on its own. With JUL, do not replace `{0}` with `{}` out of habit when switching from SLF4J.

## 5. Log4j 2 and the boundaries of placeholder syntax

The Log4j 2 API commonly supports `{}`-style parameterized messages:

```java
// Illustrative Log4j 2 example; requires corresponding dependencies and backend configuration.
private static final org.apache.logging.log4j.Logger LOG =
        org.apache.logging.log4j.LogManager.getLogger(OrderService.class);

LOG.info("orderId={} status={}", orderId, status);
```

This is an **illustrative code snippet**, not a complete standalone runnable Java file. Exact rendering behavior also depends on the `Message` type used and the Log4j 2 configuration. Avoid treating all features of Log4j 2, SLF4J, and JUL as a single shared placeholder protocol, even though in simple cases they use `{}` or braces.

Beyond parameterized messages, Log4j 2 has different message and structured logging mechanisms. Choose the API and message type based on your actual backend, log collection pipeline, and query requirements. When migrating ecosystems, test **both the rendered output and the information stored as separate fields**.

## 6. Where do placeholders help performance, and where don't they?

### 6.1. String formatting is deferred

In SLF4J:

```java
log.debug("Loaded item={} from cache={}", itemId, cacheName);
```

When DEBUG is disabled, the logger can usually skip building the complete message and converting objects to strings. This helps if the application logs heavily or if an object has a relatively expensive `toString()`.

By contrast:

```java
log.debug("Loaded item=" + itemId + " from cache=" + cacheName);
```

String concatenation executes **before the logger call**, regardless of whether DEBUG is filtered out.

### 6.2. Argument expressions are still evaluated by Java upfront

Example:

```java
log.debug("Full report={}", buildExpensiveReport());
```

Java calls `buildExpensiveReport()` before calling `log.debug(...)`, **even when DEBUG is disabled**. Placeholders do not defer expression evaluation.

If the computation is genuinely expensive, you can use a guard:

```java
if (log.isDebugEnabled()) {
    log.debug("Full report={}", buildExpensiveReport());
}
```

These snippets use a hypothetical SLF4J API; to compile, you need a `log` declaration and the appropriate dependency. Guards should only be added when the computation is significant, to avoid cluttering the code for simple arguments.

### 6.3. Lazy messages in JUL

JUL has an overload accepting `Supplier<String>` to build the message only when the level is enabled:

```java
// LOG is a java.util.logging.Logger:
LOG.log(Level.FINE, () -> "report=" + buildExpensiveReport());
```

When the FINE level is disabled, the supplier does not need to be executed. This is an **illustrative code snippet**, assuming `buildExpensiveReport()` exists. It produces a **final string via a supplier**, rather than passing a `{0}` parameter array; when choosing an approach, weigh the need for deferred evaluation against keeping the template and arguments separate.

JUL also has the `log(Level, Throwable, Supplier<String>)` overload to log an exception together with a lazily supplied message. This API is useful, but it does not change the fact that if an argument expression is evaluated outside the lambda, it is still evaluated eagerly.

### 6.4. SLF4J 2.x Fluent API

In applications already using **SLF4J 2.x**, the fluent API can express values and suppliers using a builder syntax:

```java
// SLF4J 2.x illustration; requires a log variable and dependency:
log.atDebug()
        .addArgument(() -> buildExpensiveReport())
        .log("Full report={}");
```

The supplier is invoked by the backend/API only when needed according to fluent logging handling, avoiding expensive computation just to build a disabled message. Use a library version that supports the corresponding API; this is **not SLF4J 1.x or JUL syntax**.

## 7. Is a Throwable a placeholder argument?

When catching an exception, you need to both describe the context and preserve the error cause. This is a common source of confusion across overloads:

```java
// Common SLF4J usage: Throwable in the last position.
log.error("Failed to save orderId={} stage={}", orderId, stage, error);
```

With the standard SLF4J API, a `Throwable` in the last argument position of a parameterized logging call is typically recognized as the **error cause**, so the backend logs the stack trace rather than treating it as a value to print into a final placeholder. This depends on the overload and argument count; verify against the API you are using.

**Avoid doing this:**

```java
log.error("Failed to save: {}", error.getMessage());
```

That only logs a message string and can lose the stack trace and cause chain. When appropriate, pass the **Throwable object** through the logger overload.

For JUL, overloads must be clearly distinguished:

```java
// Log an exception directly, message without parameters:
LOG.log(Level.SEVERE, "Failed to save order ORD-7", error);

// Log a parameterized message (arguments array), does not attach a throwable automatically:
LOG.log(Level.SEVERE,
        "Failed to save order {0}",
        new Object[]{"ORD-7"});
```

If you need **both a parameterized template and a Throwable** in JUL, you can create a `LogRecord` and set both properties separately:

```java
// Illustrative snippet; error is a caught Throwable.
LogRecord record = new LogRecord(Level.SEVERE,
        "Failed to save order {0}");
record.setParameters(new Object[]{"ORD-7"});
record.setThrown(error);
LOG.log(record);
```

JUL's `LogRecord` and the overloads used above only work as intended when the formatter/handler properly handles both parameters and `getThrown()`. A custom formatter that only returns `formatMessage(record)` can **drop the stack trace**; you need a formatter that handles `Throwable` or an appropriate built-in formatter.

## 8. Placeholders and structured logging

It is easy to confuse two concepts:

- **Parameterized message:** `"orderId={} status={}"` and arguments are rendered into a human-readable message.
- **Structured logging:** a log event has independent fields, such as `orderId`, `status`, and `traceId`, written by an encoder into JSON or another structured format.

Example of a regular message:

```text
INFO OrderService - orderId=ORD-7 status=ACCEPTED
```

Example of structured JSON:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "event": "order_accepted",
  "orderId": "ORD-7",
  "status": "ACCEPTED",
  "traceId": "trace-42",
  "message": "Order accepted"
}
```

The JSON above is **only a schema illustration**, not the automatic output of the logger calls above. If a collector needs to query `orderId` as an exact field instead of running regex over a string, you must provide structured data and configure the layout/encoder/collector to preserve that field.

**MDC/correlation context** helps attach the same `requestId` or `traceId` across multiple log records; placeholders do not automatically propagate context across threads or services. For applications using thread pools, design MDC copying and cleanup at the right lifecycle points so information does not leak between requests.

## 9. Special formatting rules and common pitfalls

### 9.1. Single quotes in `MessageFormat`

With JUL, `MessageFormat` uses single quotes as quoting syntax. If you want a literal `'` in the output when formatting parameters, the template usually needs `''`, as shown in the runnable Java example above:

```text
Template: order ''{0}'' completed
Argument: ORD-7
Result:   order 'ORD-7' completed
```

Do not assume this rule applies to SLF4J's `{}`: each ecosystem has different rules. When messages contain single quotes, braces, escape characters, or free-form user content, test directly against the actual formatter.

### 9.2. Mismatched placeholder and argument counts

```java
// Missing one argument for two placeholders:
log.info("orderId={} status={}", orderId);

// Passing more arguments than intended:
log.info("orderId={}", orderId, status);
```

These snippets assume SLF4J. How missing or extra arguments are handled can vary by API, backend, overload, and whether the last argument is a `Throwable`. Do not build business logic on fallback behavior when argument counts are wrong. During code review, **count placeholders and verify argument order**, especially after editing a template.

With JUL, `{0}` and `{1}` patterns have explicit indices; make sure the `Object[]` array contains enough elements and uses appropriate types if `number`/`date` formats are used.

### 9.3. Printing complex objects

```java
log.info("order={}", order);
```

If `order.toString()` accesses lazy fields, iterates over large collections, or prints sensitive data, the result can be slow performance, data exposure, or huge logs. Prefer meaningful messages with small, stable fields:

```java
log.info("orderId={} itemCount={} state={}",
        order.getId(), order.getItemCount(), order.getState());
```

Even when using placeholders, **getters are still called before entering the logger** in a normal Java call. If a getter is expensive and the level is usually disabled, consider a guard or a supplier API.

### 9.4. Newlines and log injection

Suppose `customerName` comes from user input and contains newline characters or text forged to look like another log line. Placeholders **do not automatically escape** that data into a single safe line. Choose an encoder/formatter with proper escaping, enforce size limits, avoid logging uncontrolled payloads, and test how your collector handles multiline input.

If outputting JSON, use a standard encoder/serializer to escape double quotes and control characters. Do not build JSON by concatenating strings with user-supplied argument values.

### 9.5. Exposing sensitive data

`log.info("Authorization={}", token)` still logs the token if the event is recorded; a placeholder is not masking. Avoid logging passwords, access tokens, API keys, payment data, or unnecessary personal information. Apply data controls at the source and redaction aligned with your system's policies.

### 9.6. Losing the stack trace

`log.error("failed={}", error.getMessage())` logs only a message and does not pass the `Throwable` object. If you need to investigate exceptions, pass the `Throwable` to a supporting API and ensure the layout/encoder actually outputs the exception. Avoid logging the same exception repeatedly at every layer.

### 9.7. Confusing numeric and string types

With `MessageFormat`, `{0,number}` or `{0,date}` patterns require compatible data. Passing the wrong type or missing a parameter can cause unexpected formatting results or errors during rendering. For logs that must remain consistent across locales, use consistent data types and test the formatting.

## 10. Troubleshooting when placeholders are not substituted

| Symptom | Cause to check | How to fix |
|---|---|---|
| Log prints literal `{}` | Using SLF4J syntax in JUL or missing arguments | Choose the right API and matching parameters |
| Log prints literal `{0}` | Formatter only reads `getMessage()` or no parameters were passed | For JUL, use `formatMessage(record)` and an overload accepting parameters |
| Message is missing or has extra values | Placeholder count, argument order, or overload mismatch | Review template and call site, especially a trailing Throwable |
| Log has unexpected single quotes | `MessageFormat` `'` quoting syntax | Escape as `''` and write a test for the output |
| DEBUG is disabled but app still does heavy work | Argument is an eagerly evaluated method call | Use a guard or an appropriate lazy/supplier API |
| Missing stack trace | Passing `error.getMessage()` or formatter ignores Throwable | Log the `Throwable` object and check the encoder |
| Object value is very long or sensitive | `toString()` includes unintended data | Log specific fields, limit size, and filter data |
| JSON fails to parse | Manual JSON concatenation or mixing text with JSON | Use a structured encoder and test the parser |
| Different formats across services | Different backends/locales/timezones or templates | Standardize schema, conventions, and test actual output |

When investigating, first identify **which logging API is being called**, what the actual backend is, which formatter/layout receives the event, and whether the log level allows the event to reach its destination. If the event is filtered out upfront, changing placeholders will not make it appear.

## 11. Checklist for writing log messages with placeholders

1. **Right API:** choose `{}` for standard SLF4J/Log4j 2 parameterized logging; choose `{0}`, `{1}` for JUL when using `MessageFormat`.
2. **Clear event name:** write messages with a verb or named fields, e.g., `orderId={} status={}`.
3. **Right arguments:** check order, count, data types, and the overload for `Throwable`.
4. **Preserve exceptions:** pass the actual `Throwable` if a stack trace is needed and verify the formatter.
5. **No wasted work:** avoid string concatenation; avoid calling expensive methods before the logger when the level is usually disabled.
6. **No leaked secrets:** inspect arguments and `toString()`, escape dangerous characters, and limit payload size.
7. **Distinguish from structured fields:** if you need exact key-based querying, use structured logging instead of expecting a collector to parse the message text.
8. **Test actual output:** verify level, text, exceptions, timezone/locale, and behavior when the log level is disabled.

**Practical rule:** keep a stable message template, pass arguments through the corresponding API, and let the formatter/backend handle presentation. Placeholders make logging code concise, readable, and able to reduce string-building overhead; log quality still depends on context, log levels, security, and how data is collected.
