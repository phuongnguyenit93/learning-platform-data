# SimpleDateFormat Is Not Thread-Safe When Shared Across Multiple Threads

## 1. A Fixed Pattern Does Not Make a Formatter Immutable

A common optimization in legacy code is creating a shared `SimpleDateFormat` to avoid instantiating it repeatedly:

```java
private static final SimpleDateFormat FORMAT =
        new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
```

This declaration illustrates an object that can be shared; the declaration line itself does not indicate whether call sites are synchronized. If multiple threads call `FORMAT.format(...)` or `FORMAT.parse(...)` concurrently without protection, that usage is **not safe**.

`final` only keeps the reference constant; it does not make the internal state of `SimpleDateFormat` immutable. Even when the pattern does not change and each thread's input is different, formatting/parsing operations can still use internal working state inside the object.

In an application handling many requests, bugs may be rare, appear only under load, or vary across runs. Observing no errors in a single-threaded run does not prove a shared formatter is safe.

## 2. Why Can format and parse Contend Over State?

`SimpleDateFormat` does not only hold a pattern string. It is also tied to objects and state used in interpreting calendar and numeric fields, such as `Calendar`, `NumberFormat`, along with locale/time-zone configuration.

When one thread is processing input A and another thread uses the same object for B, state read/write steps can interleave. The observed result can be an incorrect string/date or an unexpected exception. The exact symptom depends on thread scheduling and data; there is no single fixed stdout or stack trace across all runs.

Two things are easy to overlook:

- **Calling only format still requires thread-safety consideration.** It does not become a pure operation just because it is not named like a setter.
- **Reconfiguring the formatter is also a state-mutating operation.** `setTimeZone`, `applyPattern`, `setLenient`, or letting an internal reference leak out can cause subsequent calls to run with a different configuration.

Placing the reference in `volatile`, a `ConcurrentHashMap`, or a wrapper class named “thread safe” does not automatically protect operations inside the contained object. A specific formatter usage policy must be chosen.

## 3. Appropriate Approaches

| Approach | Mechanism | What to Keep Clear |
|---|---|---|
| Use `DateTimeFormatter` | Immutable object, safe when shared | Migrate pattern, data types, and parsing policy accurately |
| Create a `SimpleDateFormat` per call | Each invocation has its own instance | Fully configure locale, time zone, and leniency |
| One dedicated formatter per thread | Prevent threads from sharing a single instance | Manage lifecycle and per-context configuration |
| Synchronize a shared formatter | Prevent related operations from running concurrently | Every access path must use the same lock |

For new code, `DateTimeFormatter` usually expresses the contract clearly and allows convenient sharing. When a legacy API must be preserved, per-call creation or synchronization are options that can be verified directly.

Do not choose based solely on the intuition that instantiating a formatter is definitely a bottleneck. If performance is an actual issue, measure in the usage context and then weigh allocation cost, lock contention, and configuration complexity.

## 4. Per-Call Creation or Shared Locking Must Cover the Right Scope

### Creating a New Instance in a Method

A helper method that creates a local formatter can configure it up front:

```java
SimpleDateFormat format = new SimpleDateFormat(pattern, Locale.ROOT);
format.setTimeZone(TimeZone.getTimeZone("UTC"));
format.setLenient(false);
```

This is an illustrative configuration using the `pattern` variable. The object is owned by a single call, so there is no formatter contention between threads.

Do not create it locally once and then put it into a global cache afterward while still calling that usage “one instance per call”. The actual sharing boundary lies where references are stored and used.

### Synchronizing a Shared Formatter

If a private instance is kept, a dedicated private lock can be used:

```java
synchronized (LOCK) {
    return SHARED.format(date);
}
```

Every `format`, `parse`, and configuration change on the same instance must obey the **same lock**. Locking only object creation, locking only the parse side, or using two different locks does not eliminate contention.

Keep the formatter private so other code cannot bypass the lock. If a feature's operation consists of changing the time zone per request and then formatting, the entire sequence of changing configuration + using configuration must be protected as one consistent operation; even better, avoid mutating shared configuration per user.

Locking the formatter also does not automatically protect an input `Date` that is being modified by another thread. Data and formatter are two separate sources of state; in the full example, the input is an immutable `Instant` and Date is only created locally when needed.

### One Instance per Thread

`ThreadLocal<SimpleDateFormat>` is a legacy approach that can be used to isolate instances by thread. However, threads in a pool can outlive a single request and handle multiple users. Do not let a previous request's time zone/pattern remain and affect a later request.

A clear lifecycle policy is needed; when a value belongs only to one task and should not be retained in the pool, it can be cleaned up with `remove()` in `finally`. For designs that create many threads or require varying configurations, compare the simplicity of local creation or using `DateTimeFormatter` before adding thread-bound state.

## 5. Migrating to DateTimeFormatter Is More Than Renaming the Class

A modern formatter can be kept as a shared constant:

```java
private static final DateTimeFormatter FORMAT = DateTimeFormatter
        .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT)
        .withZone(ZoneOffset.UTC);
```

`withZone`, `withLocale`, and `withResolverStyle` return a new formatter; they do not mutate the original constant. This property ensures no shared working configuration is modified during normal formatting calls.

However, pattern symbols do not match `SimpleDateFormat` one-to-one. For example, `u` in `SimpleDateFormat` is day number of week, whereas in `DateTimeFormatter` it is year. For strict ISO date validation in new code, `uuuu` is typically used rather than mechanically copying `yyyy` and overlooking year-of-era semantics.

Additional things to check:

- Fractional-second precision and input/output data types.
- The time zone used when a string does not carry its own offset.
- Month names/language by locale.
- Whether nonexistent dates are rejected or normalized.
- Whether consuming the entire string is required.

Thread safety is only one property. A thread-safe formatter with the wrong time zone still produces semantically wrong data.

## 6. Do Not Treat a Single Load Test as Proof of the Contract

You can write a test with multiple threads sharing an unlocked SimpleDateFormat to observe failures, but you should not guarantee that a single run will definitely fail or produce a specific error message.

If the test produces no errors, it only shows that that run's schedule did not expose the issue. If it produces errors, that is useful observational evidence, not a complete description of every possible failure mode.

The program below proactively verifies **three safe approaches** with deterministic inputs. It waits for each task's result with `Future.get()` so failures in worker threads are not ignored. Expected strings are written explicitly rather than just formatting then parsing back and assuming two errors cannot cancel each other out.

## 7. Complete Runnable Program

Save the following code to `FormatterConcurrencyDemo.java`. The program requires Java 17 or later and needs no external libraries. Each approach runs 24 tasks, with each task checking 100 rounds of formatting and parsing back.

```java
import java.text.ParseException;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FormatterConcurrencyDemo {
    private static final String LEGACY_PATTERN =
            "yyyy-MM-dd'T'HH:mm:ss.SSS";
    private static final DateTimeFormatter MODERN = DateTimeFormatter
            .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT)
            .withZone(ZoneOffset.UTC);
    private static final Object LOCK = new Object();
    private static final SimpleDateFormat SHARED_LEGACY = newLegacyFormatter();

    interface Codec {
        String format(Instant value);
        Instant parse(String text) throws ParseException;
    }

    private static SimpleDateFormat newLegacyFormatter() {
        SimpleDateFormat format =
                new SimpleDateFormat(LEGACY_PATTERN, Locale.ROOT);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);
        return format;
    }

    private static Instant parseFully(SimpleDateFormat format, String text)
            throws ParseException {
        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(text, position);
        if (parsed == null || position.getIndex() != text.length()) {
            int index = position.getErrorIndex() >= 0
                    ? position.getErrorIndex() : position.getIndex();
            throw new ParseException("invalid timestamp", index);
        }
        return parsed.toInstant();
    }

    public static void main(String[] args) throws Exception {
        Codec modern = new Codec() {
            public String format(Instant value) {
                return MODERN.format(value);
            }
            public Instant parse(String text) {
                return LocalDateTime.parse(text, MODERN)
                        .toInstant(ZoneOffset.UTC);
            }
        };

        Codec perCall = new Codec() {
            public String format(Instant value) {
                return newLegacyFormatter().format(Date.from(value));
            }
            public Instant parse(String text) throws ParseException {
                return parseFully(newLegacyFormatter(), text);
            }
        };

        Codec locked = new Codec() {
            public String format(Instant value) {
                synchronized (LOCK) {
                    return SHARED_LEGACY.format(Date.from(value));
                }
            }
            public Instant parse(String text) throws ParseException {
                synchronized (LOCK) {
                    return parseFully(SHARED_LEGACY, text);
                }
            }
        };

        check("modern", modern);
        check("perCall", perCall);
        check("locked", locked);
    }

    private static void check(String label, Codec codec) throws Exception {
        Instant[] values = {
                Instant.parse("2026-10-25T10:20:30.123Z"),
                Instant.parse("2000-01-02T03:04:05.456Z")
        };
        String[] expected = {
                "2026-10-25T10:20:30.123",
                "2000-01-02T03:04:05.456"
        };
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Callable<Void>> tasks = new ArrayList<>();
            for (int task = 0; task < 24; task++) {
                int index = task % values.length;
                tasks.add(() -> {
                    for (int repeat = 0; repeat < 100; repeat++) {
                        String text = codec.format(values[index]);
                        if (!expected[index].equals(text)
                                || !values[index].equals(codec.parse(text))) {
                            throw new AssertionError("wrong value: " + label);
                        }
                    }
                    return null;
                });
            }
            for (Future<Void> future : pool.invokeAll(tasks)) {
                future.get();
            }
            System.out.println(label + "=PASS");
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```shell
javac FormatterConcurrencyDemo.java
java FormatterConcurrencyDemo
```

Expected output when all checks pass:

```text
modern=PASS
perCall=PASS
locked=PASS
```

If the string or instant is wrong, the task throws `AssertionError`; `Future.get()` propagates the failure to the main thread. The program does not merely print “ran” and treat that as data-correctness verification.

`parseFully` uses `ParsePosition` to check both conditions: that a Date was created and that the entire string was consumed. `setLenient(false)` checks calendar values, but does not by itself replace verifying that the entire string was consumed in the legacy parsing API.

All inputs have millisecond fractional parts, matching Date/SimpleDateFormat in the example. Do not infer that a round trip through Date can preserve all nanosecond parts of an Instant.

The strings have no offset suffix; the example contract defines them as UTC time. `newLegacyFormatter` and `MODERN` are both configured according to that decision. If real data needs to carry its own offset, an appropriate pattern and parsing type are required, not just appending a literal `Z` to the string.

## 8. Proper Conclusions from the Example

- `modern` relies on the immutability/thread-safety contract of DateTimeFormatter, not merely on the current number of test iterations.
- `perCall` does not share SimpleDateFormat instances, so tasks do not contend over formatter state.
- `locked` keeps one instance but serializes operations through the same private lock.
- A PASS result from the example does not prove that every other wrapper or every other SimpleDateFormat configuration is safe.
- Synchronizing a formatter does not make every other component in the application thread-safe; mutable input data, other formatters, or configuration classes still need their own contracts.

Nor should you infer which approach is fastest from the runtime of a single run of this program. This is a correctness demonstration for the chosen constructs, not a benchmark.

## 9. Hands-On Practice

1. Add a third input with a date/month/year far removed from the first two, along with its expected string. Confirm all three approaches still keep each task's data separate.
2. In a separate test copy, remove the lock on one parse or format path of the `locked` approach. Explain why the construct no longer guarantees safety, even if a run still prints PASS. Do not put that variant into production code.
3. Add a test case with a trailing remainder in the string to verify that `parseFully` rejects it. Distinguish this parsing-contract check from a thread-contention check.
4. If choosing ThreadLocal in a legacy application, clearly document who creates the configuration, whether it varies per user, and when thread-bound data is cleaned up. Evaluate whether local creation would make the contract simpler.

References: [SimpleDateFormat — synchronization](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html) and [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) in Java SE 21.