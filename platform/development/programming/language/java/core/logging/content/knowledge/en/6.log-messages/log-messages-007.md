# String Concatenation When Creating Log Messages in Java

## 1. What is string concatenation and why does it matter for logging?

**String concatenation** is the operation of joining multiple values into a string, commonly using the `+` operator. In Java, when one operand of `+` is a `String`, the result is a string joining the textual representations of both operands. This is a natural way to build log messages containing variables:

```java
String orderId = "O-17";
int attempts = 3;
String message = "orderId=" + orderId + ", attempts=" + attempts;
// Result: "orderId=O-17, attempts=3"
```

In logging, we often see:

```java
// Demonstration inside a class that already has a logger.
logger.debug("Loading order " + orderId);
logger.info("Order " + orderId + " accepted");
logger.warn("Payment retry count=" + attempts);
```

The most important point: **Java evaluates the concatenation expression before calling the logger method**. When the log level is disabled, the event may not be recorded, yet the program has already spent effort building the message, calling data-producing methods, or converting objects to strings. This is why string concatenation is often discussed alongside *log messages*, *log levels*, and *performance*.

String concatenation is not wrong in every case. For short messages, enabled log levels, or code outside hot paths, `+` can be simple and completely acceptable. You should understand **evaluation timing**, **expression cost**, and the **logging API in use** before deciding to optimize.

## 2. How string concatenation works in Java

### 2.1. The + operator converts values to text

A few examples with deterministic results:

```java
System.out.println("value=" + 10);        // value=10
System.out.println("value=" + true);      // value=true
System.out.println("value=" + (String) null); // value=null
System.out.println(1 + 2 + " items");     // 3 items
System.out.println("items=" + 1 + 2);     // items=12
```

In the last two lines, left-to-right evaluation rules produce different results:

- `1 + 2 + " items"`: first `1 + 2` is arithmetic addition (`3`), then concatenated with the string.
- `"items=" + 1 + 2`: the expression starts with a string, so subsequent `+` operations produce `"items=1"` and then `"items=12"`.

When concatenating an object, Java uses its string representation (semantically equivalent to `String.valueOf(object)`); if the value is `null`, the textual result is `"null"`. For non-null objects, the `toString()` method may be called. This leads to two notable risks when logging: `toString()` can be **expensive or have side effects**, and its default representation may **lack useful information or expose sensitive data**.

```java
// If request.toString() serializes many fields,
// that work happens when evaluating the concatenated string.
logger.debug("Incoming request: " + request);
```

If `toString()` throws an exception or performs unexpected operations, the error can occur right when constructing the expression; logging should not be assumed to be always harmless.

### 2.2. Java 17 does not mean every + creates a separate StringBuilder

At the language level, the evaluation order of operands and the concatenation result are specified. **How bytecode is generated is an implementation detail**. With modern `javac`, many string concatenations use `invokedynamic` and `java.lang.invoke.StringConcatFactory`; the compiler/JVM can optimize allocation. You should not claim that every `+` creates a `new StringBuilder` or always allocates an independent intermediate `String`.

Expressions consisting only of string constants can be folded at compile time:

```java
String fixed = "Order " + "accepted";
// Equivalent to a single string constant "Order accepted" in this case.
```

Performance issues in logging are usually **not just the number of objects created by `+`**, but also the mandatory work required to evaluate operands, invoke methods, serialize data, and build strings even when the log record is filtered out.

## 3. What happens when the log level does not allow the event?

Consider the call:

```java
logger.debug("Order details: " + serialize(order));
```

The typical flow is:

```text
1. Java evaluates serialize(order)
                  |
2. Java concatenates "Order details: " with the result
                  |
3. Call logger.debug(message)
                  |
4. Logger/backend checks whether DEBUG is enabled
                  |
           +------+------+
           |             |
       Disabled       Enabled
           |             |
    Discard record   Filter, formatter,
                     appender/handler...
```

Even in the "Disabled" branch, steps 1 and 2 **have already happened**. The logging framework cannot undo the message construction that the caller already completed.

For example:

```java
// Demonstration snippet with a logger and a buildReport() method.
logger.debug("Report: " + buildReport());
```

If `buildReport()` iterates over thousands of records, performs remote queries, or serializes large objects, that cost is still incurred when DEBUG is disabled. Making remote queries or mutating state just to prepare a log line is an error-prone design.

**Distinguish between two points in time:**

1. **Expression evaluation at the caller:** Java performs this before calling the logger. With `+` or `String.format(...)`, this is eager processing.
2. **Backend formatter/encoder:** may only run after the logger accepts the event. Depending on the framework and configuration, a filter on a handler/appender can still drop the event after that point.

An API that defers message construction usually avoids significant cost when the **logger level is disabled**, but does not automatically guarantee that all cost disappears when a downstream filter discards the event.

## 4. Ways to create log messages and their "eager/lazy" behavior

| Approach | When are the message/arguments evaluated? | Notes |
| --- | --- | --- |
| `logger.debug("id=" + id)` | The concatenated string is evaluated at the caller before the call. | Often simple for small IDs, but still incurs cost when DEBUG is off. |
| `logger.debug("data=" + expensive())` | `expensive()` runs before the call, even when DEBUG is off. | Should be avoided on hot paths. |
| `logger.debug("data={}", data)` in SLF4J | Evaluates variable `data` at the caller; message formatting can usually be deferred until the log is processed. | `toString()` may be avoided if the level is off; does **not** mean the method producing `data` is deferred. |
| `logger.debug("data={}", expensive())` in SLF4J | `expensive()` still runs before the call. | Placeholders do not make all arguments lazy. |
| `logger.atDebug().addArgument(() -> expensive()).log("data={}")` in SLF4J 2.x | The supplier can be evaluated when the event is actually processed; disabled DEBUG avoids evaluating the supplier via the fluent API. | Requires SLF4J 2.x and a compatible backend; illustrative snippet. |
| `logger.log(Level.FINE, () -> "data=" + expensive())` in JUL | `Supplier<String>` is only invoked when the logger processes level FINE. | Suitable for pure-JDK Java 17; a downstream handler filter can still drop the record. |
| `if (logger.isLoggable(Level.FINE)) { logger.fine("data=" + expensive()); }` | Evaluates the expression after checking the level condition at the caller. | Explicit, but repeats checks and does not anticipate all sink filters. |

**Do not confuse parameterized logging with lazy evaluation of all arguments.** The difference lies between **deferring message formatting** and **deferring argument-producing method calls**. These two concerns may be handled by different APIs.

## 5. Standalone Java 17+ example: + is evaluated when logging is disabled

This example uses `java.util.logging` (JUL), built into the JDK. The goal is to observe how many times an "expensive" method is called with **direct string concatenation** versus **`Supplier<String>`**. The program intentionally uses a simple counter so results are exact and independent of machine runtime.

Create the file **`LoggingConcatDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingConcatDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.concat");

        // Write only through a dedicated handler for stable stdout,
        // without propagating to parent logger handlers.
        logger.setUseParentHandlers(false);
        for (Handler oldHandler : logger.getHandlers()) {
            logger.removeHandler(oldHandler);
        }

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " | " + record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        // INFO is enabled; FINE is lower than INFO so it is filtered out.
        logger.setLevel(Level.INFO);
        AtomicInteger calls = new AtomicInteger();

        System.out.println("FINE enabled: "
                + logger.isLoggable(Level.FINE));

        // expensiveValue() still runs before logger.fine(...).
        logger.fine("EAGER value=" + expensiveValue(calls));
        System.out.println("Calls after concatenation: "
                + calls.get());

        // JUL only invokes the Supplier when FINE is enabled on the logger.
        logger.log(Level.FINE,
                () -> "LAZY value=" + expensiveValue(calls));
        System.out.println("Calls after disabled supplier: "
                + calls.get());

        // Normal message; INFO level is enabled.
        String orderId = "O-17";
        logger.info("Order " + orderId + " accepted");

        // The INFO supplier is invoked, incrementing the counter to 2.
        logger.log(Level.INFO,
                () -> "LAZY value=" + expensiveValue(calls));
        System.out.println("Calls after enabled supplier: "
                + calls.get());
    }

    private static String expensiveValue(AtomicInteger calls) {
        return "value-" + calls.incrementAndGet();
    }
}
```

Compile and run from the directory containing the file, using **JDK 17 or later**:

```bash
javac -encoding UTF-8 LoggingConcatDemo.java
java LoggingConcatDemo
```

**Exact stdout of running the code above**:

```text
FINE enabled: false
Calls after concatenation: 1
Calls after disabled supplier: 1
INFO | Order O-17 accepted
INFO | LAZY value=value-2
Calls after enabled supplier: 2
```

Explanation:

1. `Logger.setLevel(Level.INFO)` causes `logger.isLoggable(Level.FINE)` to return `false`.
2. The expression `"EAGER value=" + expensiveValue(calls)` is evaluated **before** `logger.fine(...)`. The counter increments from 0 to 1 even though no FINE line is output.
3. With `logger.log(Level.FINE, Supplier<String>)`, JUL determines FINE is not loggable and **does not invoke the supplier**. The counter remains 1.
4. `logger.info(...)` emits an INFO record, so the handler outputs the simple message: `INFO | Order O-17 accepted`.
5. The INFO-level supplier is invoked; `expensiveValue(calls)` returns `value-2`. The handler writes the INFO line and the counter becomes 2.

**Limitations of the example:** `expensiveValue` is not actually heavy; it only counts calls to illustrate evaluation timing. The code uses a synchronous handler writing to stdout and does not configure collectors, JSON formatting, multithreading, or persistence. In real systems, the goal is not always to eliminate `+`, but to avoid unnecessary work on disabled logs, especially when arguments are expensive or prone to side effects.

## 6. First fix: check the level before building the string

If you use JUL and want to construct the message manually:

```java
// Demonstration snippet in a method with logger, order, and buildSummary.
// These variables/methods must be defined in a real application.
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Order summary: " + buildSummary(order));
}
```

When FINE is disabled, `buildSummary(order)` does not run. The downside is an extra conditional branch; if the code uses another backend with different level names, you must call the corresponding API (e.g., SLF4J `logger.isDebugEnabled()`).

Two important limitations:

- **Level checks do not replace sink filters:** if FINE is accepted by the logger but a downstream handler/appender drops the event, the code still builds the string.
- **Do not separate the check and the log over a continuously changing configuration and rely on them as an atomic transaction:** the log level can change between the two points; this is only an optimization, not an access control mechanism or audit guarantee.

When the caller must already compute a value for business logic independent of logging, there is no need to artificially make it lazy: simply pass the already-available value to the log. Optimization is most meaningful when the extra work **exists solely to build the log message**.

## 7. Second fix: Supplier<String> in java.util.logging

In modern Java versions, JUL provides overloads:

```java
// In a Java application with logger and buildSummary(order).
logger.log(Level.FINE, () -> "Order summary: " + buildSummary(order));
```

The body inside the lambda is a *recipe for creating the message*, not an immediately constructed string. When the logger does not accept level FINE, the supplier does not need to be evaluated. The advantage is avoiding an `if` statement at every call site while keeping the message expression close to the logger call.

However, a lambda **does not provide guarantees across every stage**:

- Expressions evaluated when **creating the lambda object** outside the lambda body still run immediately. For example, `String s = buildSummary(order); logger.log(Level.FINE, () -> s);` has already called `buildSummary` beforehand.
- A supplier can capture variables/objects; if an object is mutated at different times, the message must reflect the intended snapshot. Do not rely on mutable state when the callback may be deferred.
- When the level is enabled but a downstream handler or filter drops the log, the cost of calling the supplier may still be incurred.
- Do not put business logic, data updates, or operations with side effects inside a logging supplier. Disabling logs must never alter business processing outcomes.

Besides the supplier overload, JUL also supports `{0}`-style parameterized formatting:

```java
// Demonstration snippet in an application with logger and variables.
logger.log(Level.INFO,
        "Order {0} completed after {1} attempts",
        new Object[]{orderId, attempts});
```

In JUL, an appropriate formatter can use `java.text.MessageFormat` to replace `{0}`, `{1}` with parameters from `LogRecord`. That is **JUL/MessageFormat** syntax, not SLF4J's `{}` placeholder. Creating the argument array `new Object[]{expensive()}` still runs `expensive()` at the caller; the formatter can only defer converting the message into its rendered form.

Do not copy placeholders mechanically between APIs: JUL `{0}`, SLF4J `{}`, and `String.format` use different mechanisms.

## 8. Third fix: Parameterized logging in SLF4J

In projects with SLF4J and a configured logging backend, the common syntax is:

```java
// Demonstration in a class with an SLF4J logger.
logger.debug("Loading orderId={} from cache", orderId);
logger.info("Order {} accepted after {} attempts",
        orderId, attempts);
```

**Meaning:** stores the message template and parameters separately so the backend handles formatting. When DEBUG is disabled, the system typically avoids constructing the final message string and avoids formatting work, especially calling `toString()` on parameters that do not need to be output. In many cases, this is a more readable and sufficient choice than `"id=" + orderId`.

However, you must distinguish clearly:

```java
// expensiveSerialize(order) STILL runs before the call.
logger.debug("Order detail={}", expensiveSerialize(order));

// You can avoid serialization when DEBUG is disabled
// by using SLF4J 2.x's fluent API:
logger.atDebug()
        .addArgument(() -> expensiveSerialize(order))
        .log("Order detail={}");
```

On the first line, the placeholder defers message **formatting** but does not defer argument **evaluation**. In the fluent example, `addArgument(Supplier<?>)` allows deferring evaluation of the value inside the supplier when DEBUG is not enabled. This is **SLF4J 2.x** syntax; projects using SLF4J 1.x cannot use the fluent API by default.

If a logging method accepts varargs, array creation and argument evaluation still occur according to Java method-invocation rules. Under high log volume, one- or two-argument overloads often help the backend reduce overhead compared to creating a varargs array. However, actual impact depends on the API and version: do not draw absolute performance conclusions without measuring in the target environment.

**Note on exceptions:** when logging an exception, prefer overloads that accept a `Throwable` so the backend preserves the stack trace properly:

```java
// Demonstration inside a catch block with orderId and exception "ex".
logger.warn("Gateway timeout for orderId={}", orderId, ex);
```

In SLF4J, a trailing `Throwable` argument is handled according to API conventions when appropriate. Concatenating `"Gateway timeout: " + ex` usually only yields the exception's `toString()` description, which can **lose the stack trace** and make investigation harder. Do not print exception contents that contain secrets without a control policy.

## 9. String.format, StringBuilder, and other alternatives

### 9.1. String.format does not make logging "lazy"

```java
// String.format(...) builds the String before calling the logger.
logger.debug(String.format(
        "Order %s completed after %d attempts",
        orderId, attempts));
```

`String.format` is a string-formatting utility with formatter/locale rules; it **does not defer itself** just because it is placed inside a logger call. For disabled logs, you still pay the cost of parsing the format string and building the result. Cases requiring complex formatting can use it where appropriate, but if the backend supports placeholders, you should generally prefer the logging API to avoid unnecessary work.

### 9.2. StringBuilder is useful when accumulating many parts, not for solving eagerness

```java
// Illustration, not a standalone runnable program.
StringBuilder details = new StringBuilder();
for (String item : items) {
    details.append(item).append(';');
}
logger.debug("items=" + details);
```

`StringBuilder` is appropriate when a string is built across a loop with many appends. Here, however, iterating over `items` already happened **before** the backend checked the DEBUG level. If the string is only for logging, place the entire construction step inside a level-checked branch or an appropriate supplier.

Do not automatically rewrite every `"a=" + x + ", b=" + y` into `new StringBuilder()...`: on Java 17, the compiler/JVM already optimizes string concatenation; more complex code may bring no benefit.

### 9.3. Text blocks, join, and JSON serializers also follow evaluation timing

`String.join(...)`, `StringBuilder`, text blocks with interpolated data, or JSON serializers must all be invoked at a specific point in time. Wrapping an expensive operation in a "readable" API does not make it lazy. If you build a JSON string of an entire object before `logger.debug(...)`, that work still happens even when DEBUG is disabled.

To write structured logs, use an appropriate API/encoder to keep fields such as `event`, `orderId`, and `elapsedMs` separate. Do not manually concatenate a JSON-like string and assume it is safely escaped, parsed, and indexed.

## 10. Performance: when should you optimize?

There are three distinct cost categories:

1. **Evaluating operands:** calling complex getters, iterating collections, serializing, preparing extra data, calling `toString()`.
2. **Building the message:** concatenating strings, formatting numbers, escaping/encoding, creating intermediate objects.
3. **Logging pipeline and I/O:** filtering, buffering, locking, formatting, writing to stdout/file/network, collectors/storage; many systems are dominated more by this part than by a simple concatenation itself.

An evidence-based way to check:

- Find high-frequency log sites, especially DEBUG/TRACE inside loops or request hot paths.
- Identify which log-only expressions are performing expensive work when the level is disabled.
- Measure CPU, allocation, throughput, and latency with a profiler or a benchmark with proper warm-up; do not infer performance merely from counting `+` signs.
- If running JMH, the benchmark must consume result values properly, avoid dead-code elimination, and account for JVM JIT/GC effects; compare the actual JDK version, API, and backend configuration in use.
- Set goals based on latency and system cost; keep messages clear and useful for investigation.

A call like `logger.info("orderId=" + id)` can be completely reasonable on an infrequent path with an already-available ID. The most valuable optimizations are usually removing `serializeEverything(request)` from disabled DEBUG logs, reducing log spam, or choosing an appropriate pipeline/sink.

**Easy-to-miss point:** a supplier or template can reduce cost when the level is disabled, but if INFO is always enabled and logs are emitted in high volume, I/O and ingestion costs still remain. In that case, revisit the logging policy, frequency, buffering, and query model.

## 11. Message correctness and safety matter more than speed

### 11.1. Log injection from control characters

Suppose a user enters a display name containing a newline. If the application concatenates directly:

```java
// Illustration of a risky pattern.
logger.info("Login attempt user=" + untrustedUserName);
```

The user can inject newlines, control characters, or strings resembling another log line's prefix, misleading readers into seeing one event as multiple lines. Placeholders do not **automatically guarantee** protection against injection: you need an escaping encoder/layout, structured logging, and input control before writing. With JSON Lines, the serializer must properly escape quotes, backslashes, newlines, and control characters.

### 11.2. Sensitive data

Do not concatenate or directly include passwords, OTPs, cookies, access tokens, refresh tokens, secret keys, or sensitive request bodies in logs. Likewise, do not rely on `toString()` of a business object that might contain these fields. Use a field allowlist, permitted internal IDs, and redaction at the source. If audit support is needed, record actor/action/outcome with verified identifiers and design a dedicated audit store when durability/integrity is required.

### 11.3. Side effects and mutable data

```java
// Do not call methods with side effects just to build a message.
logger.debug("Next sequence=" + sequence.incrementAndGet());
```

Here, the counter **increments even when DEBUG is off**. If switched to a supplier, the counter might **not increment** when logging is disabled. Both cases show that business state updates must not depend on logging.

With async logging, mutable object arguments can be modified before the formatter runs. If you need to record the **value at the time of the event**, capture a small, immutable, log-safe snapshot (such as an ID and a string/enum status) at the point the event is created. Do not enqueue live objects containing sensitive data and expect every backend to capture the right state.

## 12. Several before-and-after scenarios

**Case A: Debug is disabled, need to avoid expensive serialization**

```java
// Before: serialization still runs when DEBUG is disabled.
logger.debug("payload=" + expensiveSerialize(payload));

// After, if using SLF4J 2.x:
logger.atDebug()
        .addArgument(() -> expensiveSerialize(payload))
        .log("payload={}");
```

Pass only safe, filtered data into `expensiveSerialize`; do not serialize an entire payload containing secrets just because a supplier is used.

**Case B: Logging ordinary variables with SLF4J**

```java
// Before: the message is built at the caller.
logger.info("Loaded orderId=" + orderId + ", status=" + status);

// After: readable template and the backend can defer formatting.
logger.info("Loaded orderId={}, status={}", orderId, status);
```

If `orderId` and `status` are already available, the main benefit is readability and the ability to avoid formatting when the level is filtered out; do not assume this is a major performance improvement in every program.

**Case C: Logging exceptions**

```java
// Before: only concatenates the exception's string representation into the message.
logger.warn("Order failed: " + ex);

// After: SLF4J accepts a Throwable to record the stack trace.
logger.warn("Order failed for orderId={}", orderId, ex);
```

**Case D: Pure-JDK Java wanting to avoid message construction**

```java
// Before: always performs expensive computation.
logger.fine("trace=" + buildTraceSummary());

// After: use JUL Supplier<String>.
logger.log(Level.FINE, () -> "trace=" + buildTraceSummary());
```

The snippets in this section only **illustrate code placement in an application**, not standalone runnable programs. SLF4J examples require the appropriate dependencies, backend, and application logger declaration; JUL examples require a JUL logger.

## 13. Testing behavior and performance

Do not test only the output; also verify **whether expressions are evaluated**:

| Test case | What to verify |
| --- | --- |
| DEBUG/FINE disabled with concatenation calling a method | The method still runs per Java's argument evaluation rules, even with no log record emitted. |
| DEBUG/FINE disabled with a valid supplier | The supplier does not execute at the logger step when the level is disabled. |
| INFO enabled with a supplier | The message is built and can be output at the appropriate handler. |
| Logger enabled but handler/appender filters | The event can still be dropped; avoid assuming the supplier will never run. |
| Data containing quotes, backslashes, newlines | Output formatting is compliant; does not forge log records or break JSON. |
| Object with an expensive `toString()` | Measure when `toString()` runs under each API style and configuration. |
| Mutable object with async logging | Logged values meet snapshot/event-time requirements without unexpected data leaks. |
| Exception | The backend preserves the stack trace when supported by the API and does not expose secrets. |
| Hot-path benchmark | Measure allocation/CPU/latency with matching level, backend, and sink; avoid measuring an unrepresentative case. |

You can create a counter like the example in section 5 to prove side effects. For professional tests, use a logger/backend test appender or a test `Handler` that collects records, avoiding reliance on timestamps and default console output that may vary by configuration.

## 14. Common mistakes and application checklist

Mistakes to avoid:

- Believing `logger.debug("x=" + expensive())` skips `expensive()` when DEBUG is off.
- Believing SLF4J `logger.debug("x={}", expensive())` is lazy with respect to calling `expensive()`.
- Treating every `+` as extremely slow while ignoring Java 17 optimizations and real I/O bottlenecks.
- Manually concatenating many values without labels/fields, making logs hard to search or understand.
- Using `String.format(...)` in disabled DEBUG logs and assuming the formatter only runs after the log-level check.
- Replacing `+` with `StringBuilder` while still building the entire message before calling the logger.
- Confusing JUL `{0}` with SLF4J `{}` or `String.format("%s")`.
- Concatenating an exception with `+` and losing the stack trace needed for investigation.
- Capturing or passing mutable objects into async logging without defining an event-time snapshot.
- Logging secrets or unescaped data into text/JSON logs; placeholders are not a security mechanism.
- Putting business side effects inside log-only expressions.

**Checklist when writing a log message:**

1. Choose the appropriate level and confirm the message is genuinely useful at that level.
2. Evaluate whether operands are used for business logic or computed solely for logging.
3. With SLF4J, prefer `{}` templates for already-available variables; for expensive work, consider a Supplier or the fluent API of your version.
4. With JUL, use `Supplier<String>` or `isLoggable(...)` when you want to defer string construction.
5. Record meaningful fields: event, outcome, permitted IDs, correlation ID; pass exceptions the way the backend supports.
6. Control sensitive data, escape dangerous characters, and keep the message/event schema stable.
7. Measure and test where cost actually lies: hot paths, disabled log levels, logger/filter/sink, async, and I/O.

**Remember:** `+` in Java is valid and often convenient for string concatenation. In logging, what matters is that **concatenation and argument-producing methods execute before the logger call**; use parameterized logging or deferred message construction when you need to avoid cost, while keeping records clear, safe, and traceable.
