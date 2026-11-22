# Parameterizing Messages in Java Logging

## 1. What Is Message Parameterization?

**Message parameterization** (parameterized logging message) is a technique of declaring a **message template** with placeholders and supplying the values as separate arguments instead of manually concatenating all values into a string before calling the logger.

Conceptual example:

~~~text
Template : orderId={} items={} status={}
Arguments: o-17, 3, accepted
Result   : orderId=o-17 items=3 status=accepted
~~~

This only illustrates the `{}` placeholder convention of SLF4J/Log4j 2; not every Java API understands this template format.

Parameterization makes code easier to read, keeps the literal text consistent across events, reduces the need for manual string concatenation, and **can** save message formatting work when the log level is disabled. It also helps separate the template from variable data, which is useful for grouping similar events. However, parameterization **does not automatically turn logs into structured JSON**, **does not protect sensitive data**, and **does not guarantee that every argument is evaluated lazily**.

The goal of this lesson is to answer accurately:

- How are placeholders written in each logging API?
- When is the message assembled, and which part of the work is affected by the log level?
- How do you log values, exceptions, and contextual data clearly and safely?
- When should you use parameterized messages, `Supplier`, structured logging, or level checks?

## 2. Three Easily Confused Syntaxes

Different APIs have different semantics. Identify the **logger type** before choosing a placeholder.

| API / Mechanism | Message Template | How Values Are Passed | Notes |
| --- | --- | --- | --- |
| `java.util.logging.Logger` (JUL) | `"orderId={0} items={1}"` | `logger.log(level, template, new Object[]{id, count})` | 0-based indices, formatted via `MessageFormat` in standard formatters |
| SLF4J | `"orderId={} items={}"` | `logger.info(template, id, count)` | `{}` consumes arguments in order; uses the configured backend/provider |
| Log4j 2 with parameterized messages | `"orderId={} items={}"` | `logger.info(template, id, count)` | Common `{}` pattern; message factory mechanism is configurable |
| `String.format` / `"..." .formatted(...)` | `"orderId=%s items=%d"` | `String.format(template, id, count)` | Standard Java string formatting, not the default convention of SLF4J or JUL |

**A very common mistake** is writing `LOG.info("userId={}", userId)` from memory when `LOG` is actually a JUL `java.util.logging.Logger`. JUL does not have an `info(String, Object)` overload like SLF4J; that code will not compile. With JUL, use `LOG.log(Level.INFO, "userId={0}", userId)` or an overload that accepts a parameter array.

Do not blindly replace `{0}` with `{}` when switching frameworks. If you pass `"id={0}"` to SLF4J using the standard approach, it has no `{}` placeholder to substitute; conversely, JUL does not interpret `{}` as a `MessageFormat` index.

### Why Not Call String.format Directly Before Logging?

The snippet:

~~~java
// Illustrative snippet: logger is SLF4J, variables already exist.
log.debug(String.format("orderId=%s items=%d", orderId, itemCount));
~~~

builds the string before calling `debug(...)`, even when DEBUG is disabled. A better approach in SLF4J is:

~~~java
log.debug("orderId={} items={}", orderId, itemCount);
~~~

SLF4J can defer the final formatting step until the event is accepted. **However, argument evaluation expressions still follow Java's evaluation rules**; see Section 6.

## 3. JUL Placeholder Semantics: {0}, {1}, ...

JUL is the logging API built into the JDK. When using an overload such as:

~~~java
// Illustrative snippet inside a class that has LOG, orderId, and itemCount.
LOG.log(Level.INFO, "orderId={0} items={1}",
        new Object[] {orderId, itemCount});
~~~

the logger can record the template and parameters into a `LogRecord`. JUL's `Formatter.formatMessage(record)` processes the parameters with `java.text.MessageFormat` when appropriate. Depending on the formatter/handler, the final message output may differ. To see the parameterized template rendered properly, choose a formatter that calls `formatMessage(record)`.

In `MessageFormat`, `{0}` is the first parameter value and `{1}` is the second. An index can be repeated, for example `"orderId={0} confirmedId={0}"`. It does not automatically treat unindexed `{}` braces as placeholders. Patterns like `{0,number}` or `{0,date}` use `MessageFormat`-specific formatting, which is often locale-dependent, so be careful if you expect identical output across all environments.

**Single-quote rule:** in `MessageFormat`, the `'` character has special meaning. To print a literal single quote in a string processed by `MessageFormat`, you usually have to write `''` in the template. For example, the template `"user=''{0}''"` with `{0} = alice` produces `user='alice'`. The template `"user='{0}'"` may cause `{0}` to be treated as literal text because it falls inside a quoted region. Therefore, always check templates containing single quotes, especially English messages like `it's` or text data.

Do not embed untrusted content as a `MessageFormat` **template**. Keep templates as developer-defined strings and pass dynamic data in parameters; avoid letting users directly control the template or placeholder indices.

## 4. Standalone JDK 17 Example and Deterministic Output

This example uses JUL with a formatter that calls `formatMessage(record)`. A custom handler writes to stdout and flushes immediately so the exercise output is deterministic; real-world applications should configure handlers through their logging configuration system.

Save as **ParameterizedMessageDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class ParameterizedMessageDemo {
    private static final Logger LOG =
            Logger.getLogger(ParameterizedMessageDemo.class.getName());
    private static int diagnosticCalls = 0;

    private static String buildDiagnostic() {
        diagnosticCalls++;
        return "calculated";
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setLevel(Level.INFO);
        LOG.addHandler(output);

        String orderId = "o-17";
        int itemCount = 3;

        LOG.log(Level.INFO, "orderId={0} items={1}",
                new Object[] {orderId, itemCount});
        LOG.log(Level.INFO, "orderId={0} status={1}",
                new Object[] {orderId, "accepted"});

        // FINE is disabled, but the call's argument is still evaluated.
        LOG.log(Level.FINE, "diagnostic={0}",
                new Object[] {buildDiagnostic()});

        // The Supplier is not executed while FINE is disabled.
        LOG.fine(() -> "lazyDiagnostic=" + buildDiagnostic());

        System.out.println("diagnosticCalls=" + diagnosticCalls);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ParameterizedMessageDemo.java
java ParameterizedMessageDemo
~~~

Expected **stdout**:

~~~text
INFO orderId=o-17 items=3
INFO orderId=o-17 status=accepted
diagnosticCalls=1
~~~

Step-by-step explanation:

1. The first template uses `{0}` for `orderId` and `{1}` for `3`, so the first INFO line contains both values.
2. The second template keeps the stable literal text `orderId=... status=...` and only changes the parameters.
3. The `FINE` level is lower than `INFO`, so the logger drops the detailed log. However, `buildDiagnostic()` in the parameter call still runs before `LOG.log(...)` is invoked, incrementing `diagnosticCalls` to 1.
4. The lambda `() -> ...` passed to `LOG.fine(...)` only constructs the message when the FINE level is accepted, so it does not increment the counter in this run.
5. Because a custom formatter and handler are used, the sample lines do not include a timestamp or logger name. Another application's default JUL configuration may print a different format and to a different destination.

**Variation exercise:** change both `LOG.setLevel(Level.INFO)` and `output.setLevel(Level.INFO)` to `Level.FINE`. Then both `diagnostic=calculated` and `lazyDiagnostic=calculated` will appear, and `diagnosticCalls` will be 2. If you only change the logger to FINE while leaving the handler at INFO, the detailed message may be generated but still not displayed: **both the logger and the handler have filter levels**.

## 5. Parameterized Messages with SLF4J

SLF4J is a **logging facade outside the JDK**. A project must include the `slf4j-api` dependency and a compatible provider/backend, such as Logback; the following example **does not compile standalone with just the default `javac`**.

In a class using SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CheckoutService {
    private static final Logger LOG =
            LoggerFactory.getLogger(CheckoutService.class);

    public void confirm(String orderId, int itemCount, String status) {
        LOG.info("orderId={} items={} status={}",
                orderId, itemCount, status);
    }
}
~~~

With `orderId = "o-17"`, `itemCount = 3`, and `status = "accepted"`, the **message** part renders as:

~~~text
orderId=o-17 items=3 status=accepted
~~~

The final output may also include the timestamp, thread, logger name, and INFO level provided by the layout/appender.

### Placeholders and Argument Count

- `LOG.info("id={}", id)`: one placeholder, one value.
- `LOG.info("id={} count={}", id, count)`: two placeholders in order.
- `LOG.info("id={} idAgain={}", id, id)`: if you want the same value twice, pass the value twice.
- The number of placeholders and arguments **should not mismatch**. Excess or missing arguments can produce unexpected messages; exact handling rules depend on the API and special cases such as a trailing `Throwable`.
- `{0}`, `%s`, and `{}` are not equivalent. Read your backend's documentation when you need literal curly braces or escaping.

Putting stable metadata directly in the template makes logs easier to read:

~~~java
LOG.info("operation=checkout orderId={} itemCount={} outcome={}",
        orderId, itemCount, status);
~~~

Good templates state clear names and units: `durationMs={}`, `bytesRead={}`, `retryAttempt={}`. Avoid vague messages like `"value={} {}"` because after a few weeks it becomes very difficult to tell which object each value belongs to.

### SLF4J 2.x Fluent API and On-Demand Value Evaluation

If the project uses **SLF4J 2.x**, the fluent API can accept a `Supplier<?>` to defer argument creation:

~~~java
// Illustrative snippet in a class with LOG and order, using SLF4J 2.x.
LOG.atDebug()
   .addArgument(() -> safeDescribe(order))
   .log("orderDetail={}");
~~~

An approach compatible with multiple SLF4J versions is a guard:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("orderDetail={}", safeDescribe(order));
}
~~~

Both are suitable when `safeDescribe(order)` is genuinely expensive and has no side effects. When DEBUG is disabled, calling the data-description function is avoided. When DEBUG is enabled, building the description still consumes resources. Never fetch sensitive data or query external systems solely for a log message.

**Note:** Java must evaluate `orderId`, `itemCount`, or any argument expression before calling a normal logging API method. SLF4J can defer *formatting*, but it does not automatically make all argument expressions lazy. For values that are already available and cheap, calling a parameterized message directly is readable and usually appropriate.

## 6. Cost Comparison: String Concatenation, Placeholders, and Supplier

Consider three statements at the DEBUG level:

~~~java
// SLF4J illustration, not a complete program.
LOG.debug("customer=" + expensiveDescription(customer));
LOG.debug("customer={}", expensiveDescription(customer));
LOG.atDebug().addArgument(() -> expensiveDescription(customer))
        .log("customer={}");
~~~

| Approach | When DEBUG Is Disabled | Remarks |
| --- | --- | --- |
| String concatenation | `expensiveDescription` still runs, and the string is built before the call | Avoid on hot paths if the data is expensive to compute |
| Standard `{}` placeholder | `expensiveDescription` still runs; the formatter's message assembly may be skipped | Better than concatenation for already-available arguments, but does not make expensive computations lazy |
| SLF4J 2.x `Supplier` | The description function does not need to run if the event is not accepted | Suitable when the log-data builder is pure and expensive |

**Do not assume "parameterized = zero allocation".** Java may box primitives, allocate varargs arrays, hold object references, or create log records depending on the overload and framework. Even when the log level is disabled, some method-call or argument-evaluation overhead may still remain. For messages with many arguments or logs on hot paths, inspect the actual implementation and use a profiler rather than relying on a blanket claim.

Do not put business logic inside a `Supplier`. Bad example:

~~~java
// Flawed design: if DEBUG is disabled, the state update might not happen.
LOG.atDebug().addArgument(() -> inventory.reserve(order))
        .log("reserved={}");
~~~

`reserve` is a business operation with side effects; it must be called independently first, and then only the result should be safely logged. Business behavior must remain identical whether the logger is enabled or disabled.

## 7. Parameterized Messages When Logging Exceptions

Exceptions need to preserve their **stack trace** and cause, not just their class name or message. How a `Throwable` is passed varies by API.

### With JUL

~~~java
// Illustrative snippet inside a catch block; orderId and LOG already exist.
catch (java.io.IOException e) {
    LOG.log(Level.SEVERE, "operation=loadOrder orderId=" + orderId
            + " outcome=failed", e);
    throw e;
}
~~~

`LOG.log(Level.SEVERE, String, Throwable)` uses the overload dedicated to `Throwable`; an appropriate formatter/handler will include the stack trace in the record. This is **code inside an exception-handling block** and cannot run standalone without context. Concatenating a short ID into the error message here is straightforward; do not reduce the exception to `e.getMessage()` and lose the stack trace.

If you want both to parameterize the JUL message and preserve the `Throwable`, you can create a `LogRecord` and set `parameters` and `thrown` before passing it to `Logger.log(LogRecord)`, though for most common cases a simple API call and logging context at the handling boundary is cleaner. Only use `LogRecord` manually when there is a specific requirement.

### With SLF4J

~~~java
// Illustrative snippet inside a catch block; LOG is an SLF4J Logger.
catch (java.io.IOException e) {
    LOG.error("operation=loadOrder orderId={} outcome=failed",
            orderId, e);
    throw e;
}
~~~

SLF4J generally recognizes a trailing `Throwable` in a parameterized logging call as the event's exception. Therefore, it can log the stack trace without requiring an extra `{}` for `e`. There is also an `error(String, Throwable)` overload. Use the right overload and check your log format to avoid accidentally turning a `Throwable` into a plain string or logging an error without its stack trace.

**Do not log the same exception as ERROR at every layer** if each layer simply rethrows it without adding necessary context: this creates duplicate records, increases cost, and adds noise during investigation. Choose the boundary responsible for reporting the error.

## 8. How Do Parameterized Messages Differ from Structured Logging?

A parameterized message is a **text template plus arguments**; once rendered, it usually becomes a human-readable string:

~~~text
operation=checkout orderId=o-17 durationMs=35 outcome=success
~~~

Structured logging represents fields as distinct key/value pairs (often emitted as JSON). Illustrative data example:

~~~json
{
  "level": "INFO",
  "operation": "checkout",
  "orderId": "o-17",
  "durationMs": 35,
  "outcome": "success"
}
~~~

Log collection systems can query the numeric `durationMs` field or filter on `outcome` more easily if the encoder and pipeline **actually preserve data types and fields**. Simply writing `durationMs={}` in a string does not automatically guarantee a `durationMs` JSON field in the log. A backend might only emit plain text messages.

In SLF4J 2.x, the fluent API also supports key/value pairs:

~~~java
// Illustrative snippet in an SLF4J 2.x class; requires a suitable encoder to output fields.
LOG.atInfo()
   .addKeyValue("operation", "checkout")
   .addKeyValue("orderId", orderId)
   .addKeyValue("durationMs", durationMs)
   .log("Checkout completed");
~~~

Whether those fields appear as text, JSON, or are ignored depends on the provider and encoder/layout. Do not assume that calling `addKeyValue` will automatically make the console print JSON.

**MDC (Mapped Diagnostic Context)** in some frameworks helps attach a request ID or trace ID to multiple logs within the same execution flow. With async or worker threads, the context must be propagated or managed properly; thread-local values are not guaranteed to move across threads automatically. MDC does not replace meaningful message content, and secrets must never be placed in it.

## 9. Designing Stable, Searchable Templates

When crafting messages for an event type, try to keep the literal text fixed and place variable values in placeholders. Good example:

~~~java
LOG.info("order accepted orderId={} itemCount={}", orderId, count);
~~~

If messages are built with strings that change word order or phrasing, searching for events of the same type becomes harder. Stable templates help group log records and track error frequencies, though exact grouping behavior depends on the pipeline.

Practical recommendations:

1. **State the action first:** `"payment validation failed"`, `"cache entry expired"`, `"job completed"` rather than `"Problem"` or `"Done"`.
2. **Use clear field names:** use `orderId`, `itemCount`, `durationMs`, `attempt`; avoid labels like `x`, `data`, or unannotated values.
3. **Be consistent with units:** `durationMs` differs from `durationNs`; `amountCents` differs from a formatted currency string.
4. **Ensure useful context:** safe correlation IDs, operation, outcome, error codes, and status. You do not need to repeat every field in every log; choose what aids diagnosis.
5. **Separate variable data from the template:** do not pass user input as the logger template; pass it as an argument after evaluating its safety.
6. **Do not overuse dynamic messages:** a request with thousands of fields should not all be dumped into a string just because placeholders exist; control both count and length.

Example of a clear, self-explanatory line:

~~~text
INFO operation=sendEmail templateId=welcome recipientCount=120 outcome=success durationMs=84
~~~

There is no need to log all 120 email addresses or the full email body to know that the operation succeeded and how long it took.

## 10. Security: Parameterization Does Not Automatically Make Data Safe

Some developers confuse parameterized logging with SQL prepared statements. **The two mechanisms serve different purposes.** Prepared statements send commands and data separately through the database query protocol; parameterized logging is for representing and formatting messages. It does not automatically prevent all data leaks or log forgery risks.

- Never log tokens, passwords, OTPs, cookies, private keys, card numbers, or unnecessary personal data at any log level.
- User input may contain newlines, control characters, or strings resembling log prefixes, causing **log forging/log injection** if emitted directly as text. Use an encoder with proper target escaping, sanitize/bound fields, and query against normalized fields.
- Limit message length and record volume for unusual inputs; avoid letting large payloads bloat logs or spike allocations.
- Configure appropriate access controls and retention periods for logging systems. Even if TRACE/DEBUG is only enabled temporarily, records can still be shipped to multiple collectors and backups.
- If data must be anonymized or masked, prefer selecting only safe fields from the start. Building a full string and masking it with regex can be both expensive and prone to missing new fields.

Example of **what not to do**:

~~~java
// SLF4J illustration: passwords must not be logged even when using placeholders.
LOG.info("login user={} password={}", username, password);
~~~

A **more appropriate** example:

~~~java
LOG.info("login attempt userId={} result={}",
        safeUserId, authenticationResult);
~~~

Use a `safeUserId` that complies with the system's data protection policy; do not assume every user ID can be logged unrestrictedly.

## 11. Checklist for Choosing an Approach in a Project

| Need | Suitable Approach |
| --- | --- |
| JUL, message with 1–n values | `Logger.log(Level, "...{0}...{1}", params)` |
| SLF4J/Log4j 2, arguments already available | `{}` placeholders matching the API |
| Expensive string construction when the log may be disabled | `isLoggable`/`isDebugEnabled`, or `Supplier` if supported by the API |
| Need to log a `Throwable` | Proper overload or convention for passing `Throwable` in the logging API |
| Need to filter/query by typed fields | Structured logging with an appropriate encoder |
| Need to correlate multiple events for one request | Properly managed correlation ID / MDC |
| Very high frequency | Limit events, apply sampling/rate limiting where appropriate; measure CPU/GC, bytes/s, latency |
| Untrusted input | Pick safe fields, escape/encode, limit length, never use input as the template |

To evaluate performance, do not measure only the time of a `logger.info(...)` call. Inspect object allocations, formatters, I/O, async queues, p95/p99 latency, storage, and log lines per second under a realistic workload. Parameterization can reduce part of the cost, but it is no substitute for choosing **the right events, the right log level, and the right amount of data**.

## 12. Common Mistakes and How to Fix Them

| Mistake | Problem | Fix |
| --- | --- | --- |
| Using `{}` in JUL | Not JUL's parameterization syntax | Use `{0}`, `{1}`, and `Logger.log` |
| Using `{0}` or `%s` in SLF4J | Not the standard placeholder syntax | Use `{}`; only use other formatting when the API explicitly supports it |
| Concatenating strings or calling `String.format` inside a DEBUG call | Message construction cost is paid even when the log is disabled | Use templates and a `Supplier`/guard when expressions are expensive |
| Treating placeholders as lazy for all parameters | Java still evaluates argument expressions | Move expensive computations into a `Supplier` or guard when safe |
| Fewer or more arguments than placeholders | Hard-to-read logs, misaligned values | Match count and order; check trailing exception handling |
| Misusing `'` in `MessageFormat` | `{0}` may be printed literally | Escape single quotes according to `MessageFormat` rules |
| Logging only `e.getMessage()` on error | Loses the stack trace and failure origin | Pass `Throwable` using the proper overload |
| Logging full objects or credentials | Data exposure, excess bytes and allocations | Whitelist safe fields and limit sizes |
| Assuming parameterized text creates JSON fields | The system stores a single plain string | Use structured logging with a supporting encoder |
| Dumping all logs at DEBUG/TRACE | Huge log volume, hard to search | Classify by event, level, and observability needs |

## 13. Self-Check Exercises

1. **JUL:** fix the template `"orderId={1} count={0}"` with parameters `new Object[]{3, "o-17"}`, predict the message after `formatMessage` is applied, then swap the two parameters and explain the consequence.
2. **DEBUG disabled:** starting from `LOG.debug("details={}", expensiveDescription(order))`, rewrite it in two ways: an `isDebugEnabled()` guard and SLF4J 2.x `addArgument(Supplier)`. Explain the condition under which the expensive function actually does not run.
3. **Exceptions:** write two exception-logging snippets for JUL and SLF4J, ensuring the stack trace is preserved; explain why `LOG.error("failed {}", e.getMessage())` is not equivalent to passing the `Throwable`.
4. **Structured logging:** given the fields `operation`, `orderId`, `durationMs`, and `outcome`, write a parameterized message and a corresponding JSON representation. Explain why the numeric type of `durationMs` cannot be automatically inferred from plain text alone.
5. **Security:** given user input containing newlines or curly braces, explain the risk of log forging and why using placeholders does not replace escaping at the encoder level.
6. **Performance measurement:** compare string-concatenation logging with parameterized templates in a workload with DEBUG disabled, and then with DEBUG enabled. Observe CPU, allocations, and bytes/s; distinguish argument-building time from formatting/writing time.

**Key takeaway:** message parameterization keeps log templates clear and consistent and can reduce formatting overhead. Choose **the right syntax for your logger**, remember that **Java arguments are still evaluated**, use **a `Supplier` or guard for expensive computations**, pass **`Throwable` properly**, and sanitize **sensitive data** before logging.