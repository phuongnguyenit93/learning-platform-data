# Why Should `SimpleDateFormat` Not Be Shared Arbitrarily Across Multiple Threads?

## 1. The problem in concurrent Java applications

`java.text.SimpleDateFormat` is a legacy API for formatting and parsing dates and times based on patterns such as `dd/MM/yyyy`, `yyyy-MM-dd HH:mm:ss`, and locale rules. It appears widely in long-lived Java applications, processing `Date` values, reports, logs, and system integrations.

Consider a web application handling many concurrent requests:

```java
// ANTI-PATTERN: do not share across multiple threads like this.
private static final SimpleDateFormat FORMAT =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);
```

Then multiple threads call concurrently:

```java
String text = FORMAT.format(date);  // Thread A
Date value = FORMAT.parse(input);   // Thread B
```

This pattern **is not safe merely because the `FORMAT` variable is `static final`**. `SimpleDateFormat` and its superclass `DateFormat` hold **mutable state**; even formatting and parsing operations mutate internal state. Java does not guarantee that multiple threads may call `format` and `parse` concurrently on the same instance without proper synchronization.

What can happen is wrong output, unstable parsing, bugs that surface only under high load, or one thread observing configuration changed by another thread. A single successful test run **does not prove** thread safety.

> **Design rule:** `SimpleDateFormat` should be owned by one thread/task at a time, or every operation on a shared instance must be consistently synchronized. For new Java code, prefer `java.time.format.DateTimeFormatter`, which is immutable and thread-safe.

## 2. Where is `SimpleDateFormat` mutable?

`SimpleDateFormat` extends `DateFormat` and uses components related to date/time and numbers. Notable mutable state/settings include:

| Component or operation | Why is it tied to mutability? |
| --- | --- |
| `DateFormat`'s `Calendar` | Participates in computing year, month, day, hour, and timezone fields during parse/format |
| Associated `NumberFormat` | Participates in reading/writing numeric parts of date and time |
| `applyPattern(...)` | Changes the pattern of an existing formatter |
| `setTimeZone(...)` | Changes the time zone used for interpretation/display |
| `setLenient(...)` | Changes the rules for accepting invalid dates |
| `setDateFormatSymbols(...)` | Changes locale-related symbols and month/day names |
| `setCalendar(...)`, `setNumberFormat(...)` | Replaces the components used for parse/format |

A `SimpleDateFormat` instance is **an object with both configuration and operational state**. Neither `format` nor `parse` is a pure transformation promised by the API to be thread-safe.

Picture two calls on **the same instance**:

```text
Thread A: format(dateA)             Thread B: parse(textB)
    │                                   │
    ├── update calendar state           │
    │                                   ├── use/update calendar state
    ├── read calendar fields            │
    │                                   ├── read/write parser fields
    └── build result string             └── build Date/result
```

This diagram only illustrates **the risk of interleaved operations on shared state**, not a claim that every JDK executes steps in this exact order. The key point is that **there is no internal synchronization contract sufficient for arbitrary sharing**.

Symptoms can vary by JDK, environment, and input data. Do not rely on a specific error like `NumberFormatException` or a wrong date to "confirm" that a race condition exists only when that error appears.

## 3. `static final` does not mean immutable

Three distinct concepts are often confused:

- **`static`**: a class-level reference, typically shared across all instances and threads.
- **`final`**: after initialization, the reference cannot be reassigned to another object.
- **Immutable/thread-safe**: an **object behavioral contract**; `static final` does not turn a mutable formatter into an immutable one or automatically synchronize its methods.

Example:

```java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("dd/MM/yyyy", Locale.US);

// Valid Java syntax, yet still mutates SHARED's internals:
SHARED.setLenient(false);
SHARED.setTimeZone(TimeZone.getTimeZone("UTC"));
SHARED.applyPattern("yyyy-MM-dd");
```

This is an **illustrative code snippet**, requiring imports for `SimpleDateFormat`, `Locale`, and `TimeZone` within an appropriate class/method scope. `final` only prevents `SHARED = new SimpleDateFormat(...)`; it does not prevent calling setters.

Even when an application **never calls setters** after initialization, you must not assume multiple threads can call `format`/`parse` concurrently on the same instance. Configuring it once **is not enough** to make this legacy class thread-safe.

### Two distinct failure modes

**State contention during format/parse:** two threads use the same formatter at the same time. Results can become corrupted due to interference on internal state.

**Configuration contention:** one thread calls `setTimeZone`, `applyPattern`, or `setLenient` while another thread formats. The latter thread may use a configuration not meant for its request. Even if `format` alone is wrapped in a lock while setters do not use the same lock, the design remains unsafe.

## 4. When does sharing actually pose a risk?

A `SimpleDateFormat` **used locally and sequentially** can work completely fine. Risk arises when **the same instance** can be accessed concurrently without a synchronization contract.

| Scenario | Assessment |
| --- | --- |
| Creating a formatter inside a method, used only by that thread and discarded | Appropriate; no shared formatter state |
| A single thread using a formatter across multiple sequential operations | No cross-thread race on that formatter |
| Storing a formatter in a singleton and having multiple requests call `format` | **Unsafe** unless all accesses are guarded |
| A `static final` formatter where multiple threads only call `parse` | Still **not guaranteed safe** |
| `synchronized` around **every** access to a shared formatter | Can preserve correctness, but serializes operations |
| Each thread gets its own formatter via `ThreadLocal` with lifecycle management | Workable, but adds state/lifecycle overhead |
| A shared immutable `DateTimeFormatter` | Designed thread-safe per the `java.time` contract |

"Read-only" is misleading here: `FORMAT.format(date)` looks like it only reads `date`, yet **methods of a mutable formatter object** are not guaranteed to be read-only with respect to internal state.

In applications using thread pools, tasks may reuse threads or execute concurrently at different times. Do not infer a formatter is safe merely because test runs happened not to overlap.

## 5. Anti-pattern example: unprotected shared formatter

The following example only illustrates a design to avoid; **no output is guaranteed** and it must not be used as production code:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class UnsafeSharedFormatter {
    private static final SimpleDateFormat SHARED =
            new SimpleDateFormat(
                    "yyyy-MM-dd HH:mm:ss", Locale.US);

    public static String render(Date date) {
        // Concurrent calls from multiple threads: not guaranteed safe.
        return SHARED.format(date);
    }
}
```

This class compiles without a `main` method; it illustrates how a service can accidentally share formatter state via a `static` variable.

A thousand test runs might all succeed; that still does not make the code concurrency-safe. When bugs appear, they can also depend on input data, scheduling, JIT, and JDK implementation. **Do not write unit tests that require a race to reproduce**; a concurrency bug is a contract violation, not necessarily something with deterministic symptoms.

## 6. Approach 1: create a new `SimpleDateFormat` per task

This is the simplest approach when you must use the legacy API and operation volume is moderate: **do not share the formatter**.

Create the file **`TaskLocalSimpleDateFormatDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TaskLocalSimpleDateFormatDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < 3; i++) {
                final int id = i;
                tasks.add(() -> {
                    // Each task owns its own formatter.
                    SimpleDateFormat formatter =
                            new SimpleDateFormat(
                                    "yyyy-MM-dd HH:mm:ss", Locale.US);
                    formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
                    formatter.setLenient(false);

                    Date instant = new Date(id * 1000L);
                    String text = formatter.format(instant);
                    Date parsed = formatter.parse(text);

                    return "task-" + id + ": " + text
                            + " -> " + parsed.getTime();
                });
            }

            List<Future<String>> futures = executor.invokeAll(tasks);
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 TaskLocalSimpleDateFormatDemo.java
java -cp . TaskLocalSimpleDateFormatDemo
```

Output:

```text
task-0: 1970-01-01 00:00:00 -> 0
task-1: 1970-01-01 00:00:01 -> 1000
task-2: 1970-01-01 00:00:02 -> 2000
```

**Why is this safe for the formatter?** Each `Callable` creates its own `SimpleDateFormat` instance, configures UTC, and never hands that instance to another thread. There is no shared mutable formatter.

Task execution order is not guaranteed, but the program collects `Future`s in submission order before printing, keeping stdout stable in the example. The time zone is explicitly set to UTC so it does not depend on the machine's time zone.

**Trade-off:** each invocation allocates a formatter. Under high throughput, measure actual performance; do not prematurely optimize by moving a mutable formatter into a global variable.

## 7. Approach 2: consistent synchronization when sharing a formatter

When the architecture cannot be changed immediately, a shared lock can protect a `SimpleDateFormat` instance. The requirement is that **every** access path — `format`, `parse`, and any state-mutating setters — must follow the same synchronization policy.

Create the file **`SynchronizedLegacyDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SynchronizedLegacyDemo {
    private static final Object FORMAT_LOCK = new Object();

    private static final SimpleDateFormat SHARED =
            new SimpleDateFormat(
                    "yyyy-MM-dd HH:mm:ss", Locale.US);

    static {
        SHARED.setTimeZone(TimeZone.getTimeZone("UTC"));
        SHARED.setLenient(false);
    }

    private static String renderAndParse(int id) throws Exception {
        Date date = new Date(id * 1000L);

        synchronized (FORMAT_LOCK) {
            // Both format and parse are protected by the same lock.
            String text = SHARED.format(date);
            Date parsed = SHARED.parse(text);
            return "task-" + id + ": " + text
                    + " -> " + parsed.getTime();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                final int id = i;
                tasks.add(() -> renderAndParse(id));
            }

            List<Future<String>> futures = executor.invokeAll(tasks);
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SynchronizedLegacyDemo.java
java -cp . SynchronizedLegacyDemo
```

Output:

```text
task-0: 1970-01-01 00:00:00 -> 0
task-1: 1970-01-01 00:00:01 -> 1000
task-2: 1970-01-01 00:00:02 -> 2000
```

**Critical safety condition:** no other method or code path may call `SHARED.format`, `SHARED.parse`, `SHARED.setTimeZone`, or `SHARED.applyPattern` outside your designated lock. If even a single code path skips the lock, races can still occur.

**Cost:** concurrent requests must queue through the same critical section, which can create a bottleneck under high load. Do not treat `synchronized` as the default optimal solution for every application. Locking on **the formatter itself** (`synchronized (SHARED)`) also only works when every caller agrees on that exact monitor; a dedicated private lock object usually makes access control clearer.

## 8. Approach 3: `ThreadLocal<SimpleDateFormat>` — useful, but requires lifecycle management

`ThreadLocal` associates **each thread** with **its own instance**. When each thread obtains its own formatter, operations on that formatter do not contend directly with another thread's formatter.

Example utility class:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public final class LegacyThreadLocalFormats {
    private static final ThreadLocal<SimpleDateFormat> FORMATTER =
            ThreadLocal.withInitial(() -> {
                SimpleDateFormat f = new SimpleDateFormat(
                        "yyyy-MM-dd HH:mm:ss", Locale.US);
                f.setTimeZone(TimeZone.getTimeZone("UTC"));
                f.setLenient(false);
                return f;
            });

    public static String format(Date date) {
        return FORMATTER.get().format(date);
    }

    public static void clearCurrentThread() {
        FORMATTER.remove();
    }

    private LegacyThreadLocalFormats() {
    }
}
```

This is a **compilable utility class without a `main` method**; it illustrates a design pattern rather than a standalone runnable demo.

Considerations:

- In a **thread pool**, threads can be long-lived and serve many requests. A thread's formatter remains alive and is reused; this can help performance, yet also allows **configuration or state tied to an earlier request to leak into a subsequent request** if code mutates the formatter.
- When state must be released at request/task boundaries, call `remove()` in a `finally` block at the appropriate boundary. After `remove()`, the next `get()` creates a fresh formatter.
- If locale/zone/pattern vary per request, a fixed-configuration `ThreadLocal` formatter **does not automatically adapt** to each user. Do not mutate the thread-local formatter's timezone and forget to reset it.
- `ThreadLocal` is no substitute for an immutable architecture and increases memory/lifecycle management work, especially in application servers or long-lived thread pools.

If you just need to format a date in a request, creating a fresh formatter or using `DateTimeFormatter` is usually less risky than maintaining a `ThreadLocal`.

## 9. Approach 4 recommended for new code: `DateTimeFormatter`

The `java.time.format.DateTimeFormatter` API is designed to be **immutable** and **thread-safe**. A constructed formatter can be called concurrently from multiple threads; neither `synchronized` nor `ThreadLocal` is needed just to protect the formatter.

For UTC date-time, using the same `Instant` from epoch and one shared formatter:

Create **`ModernFormatterConcurrencyDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ModernFormatterConcurrencyDemo {
    private static final DateTimeFormatter SHARED =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd HH:mm:ss XXX", Locale.US)
                    .withZone(ZoneOffset.UTC);

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < 3; i++) {
                final int id = i;
                tasks.add(() -> {
                    Instant instant = Instant.ofEpochSecond(id);
                    String text = SHARED.format(instant);
                    Instant parsed = Instant.from(SHARED.parse(text));

                    return "task-" + id + ": " + text
                            + " -> " + parsed.getEpochSecond();
                });
            }

            List<Future<String>> futures = executor.invokeAll(tasks);
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ModernFormatterConcurrencyDemo.java
java -cp . ModernFormatterConcurrencyDemo
```

Output:

```text
task-0: 1970-01-01 00:00:00 Z -> 0
task-1: 1970-01-01 00:00:01 Z -> 1
task-2: 1970-01-01 00:00:02 Z -> 2
```

Differences:

1. `SHARED` is the exact same formatter used concurrently by all tasks under its **thread-safety contract**.
2. `Instant` is immutable and represents an absolute point in time; `withZone(ZoneOffset.UTC)` supplies the zone required to print time fields.
3. Parsing includes the `XXX` offset, so an `Instant` can be extracted from the parsed result. If the pattern only contains date/time without zone or offset, you cannot assume it holds enough information to convert to an absolute instant.
4. Results are collected from `Future`s in order, avoiding dependence on executor scheduling.

### How to convert from `Date` to `java.time`

When a legacy API returns `java.util.Date`, convert it to `Instant`:

```java
Date legacyDate = new Date(0L);
Instant instant = legacyDate.toInstant();
```

This is a **snippet** requiring `java.util.Date` and `java.time.Instant` imports. You can format `instant` with a zone-configured `DateTimeFormatter`.

Conversely, when a legacy API requires a `Date`, you can use `Date.from(instant)`. However, converting the data type **does not automatically pick a locale, zone, or pattern**. When migrating, ensure temporal semantics and input expectations stay accurate.

## 10. Do not confuse patterns and temporal types when migrating

`SimpleDateFormat` uses patterns like `yyyy-MM-dd`; `DateTimeFormatter` has similar letters yet **does not guarantee every letter carries identical semantics** across the two APIs.

For example:

- `DateTimeFormatter` has `u` for **proleptic year**, whereas `y` is **year-of-era**. With a `ResolverStyle.STRICT` parser, `uuuu` is usually preferred over `yyyy` when parsing Gregorian calendar dates without an era.
- `SimpleDateFormat` uses `Date`/`Calendar`, whereas the modern API recommends `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, or `Instant` depending on meaning.
- `LocalDateTime` **is not an `Instant`**. It has no zone/offset; converting it to an absolute point in time requires a zone or offset chosen by business logic.
- Locale and zone are **two separate configurations**. Using the Vietnamese language does not require the user to be in `Asia/Ho_Chi_Minh`.
- For rejecting invalid dates, `SimpleDateFormat.setLenient(false)` and `DateTimeFormatter.withResolverStyle(ResolverStyle.STRICT)` belong to two different APIs; test boundary cases before assuming migration equivalence.

Therefore, renaming the class and copying the pattern verbatim is not a complete migration strategy. Test formatting, parsing, timezones, leap years, calendars, and error behavior.

## 11. Locale and timezone in a multi-user service

Sharing a formatter becomes even more dangerous if an application uses the same `SimpleDateFormat` and **mutates its configuration per request**:

```java
// ANTI-PATTERN: two requests mutate the same object.
SHARED.setTimeZone(userTimeZone);
String text = SHARED.format(date);
```

Request A may set `Asia/Ho_Chi_Minh`, but before A calls `format`, request B changes it to `Europe/Berlin`. A's output can end up using B's timezone. This is a **shared configuration state** bug, distinct from internal format/parse state races.

Proper design:

- With the legacy API, create a formatter **per request** with the request's `Locale` and `TimeZone`; do not set the timezone on a global formatter per request.
- With the modern API, create an immutable base formatter and derive variants with `withLocale(userLocale)` and `withZone(userZone)`. Both methods return a formatter with the updated configuration **without mutating the original**.
- Do not call `Locale.setDefault` or `TimeZone.setDefault` per request; these defaults are JVM-wide state that can affect other threads.

Snippet with `DateTimeFormatter`:

```java
DateTimeFormatter perRequest = BASE
        .withLocale(userLocale)
        .withZone(userZone);
String text = perRequest.format(instant);
```

This is an **illustrative code snippet**, assuming `BASE`, `userLocale`, `userZone`, and `instant` are already declared. Immutability lets each request hold its own configuration without mutating the base formatter.

Caching formatters by pattern/locale/zone is also viable, provided the cache structure is thread-safe and the cache key includes **all configuration dimensions that affect output**. Do not build an unbounded cache from arbitrary user-supplied pattern strings.

## 12. Real-world failure scenarios and how to distinguish them

### 12.1. Non-reproducible wrong output

Symptom: for the same date/time, a shared formatter occasionally produces a different string, or the parser returns unstable results under load. The cause may involve concurrent access to mutable state, though you should inspect input data, locale, timezone, and setters before concluding. Do not "fix" it merely by reordering tasks or adding `sleep`.

### 12.2. Random parser exceptions

When concurrent threads call `parse`, the legacy formatter's internal state can be corrupted. Some implementations/scenarios can throw exceptions or yield unexpected values. Do not document a single **fixed exception type** as a guaranteed outcome on every JDK; there is no guarantee which run will exhibit a failure.

### 12.3. Same formatter, timezone changes between requests

This issue is typically easy to trace to `setTimeZone`: the setter mutates a **shared object**. Even without parser exceptions, output can reflect the wrong time zone. The fix is per-request configuration or strict synchronization and sharing policies.

### 12.4. Formatter is synchronized, but a helper bypasses the lock

Suppose a controller synchronizes `format` while a background task calls `SHARED.parse(...)` directly. The design still has a race. One prevention technique is wrapping the formatter in a **service with a single API** and never exposing the mutable instance externally; all accesses are coordinated uniformly.

### 12.5. Switched to `DateTimeFormatter`, yet concurrency bugs persist

Inspect other parts of the system: concurrently mutated `HashMap`s, mutable temporal objects returned by legacy APIs, globally mutated `Locale`/`TimeZone` defaults, or sharing a `DateTimeFormatterBuilder` that is still being modified.

A thread-safe `DateTimeFormatter` **does not automatically make all surrounding code thread-safe**.

## 13. Measuring and testing concurrency meaningfully

A test spawning multiple threads for 10,000 iterations without failing is a useful signal for a single run, yet **has zero value as proof** that `SimpleDateFormat` is thread-safe. Race conditions can depend on scheduling, CPU/JVM, system load, and specific code paths.

Instead of trying to force random failures at any cost, organize QA systematically:

1. **Audit ownership:** where is the formatter created—stored in `static`, a singleton, a Spring bean, a thread pool, or local scope?
2. **Trace every call site:** `format`, `parse`, `applyPattern`, `setTimeZone`, `setLenient`, `setCalendar`, etc. on the same instance.
3. **Classify protection strategy:** per-task, thread confinement, full synchronization, or migration to immutable.
4. **Use fixed data:** `Date(0)`, UTC timestamps, explicit locales; never depend on the CI clock or default timezone.
5. **Collect results in order:** with executors, collect `Future`s and assert expected values, avoiding flakiness from log ordering.
6. **Test both formatting and parsing:** do not test `format` while ignoring `parse` branches; different branches may touch different state.
7. **Test per-request configuration:** at least two zones/locales and concurrent requests, especially if legacy code ever called setters on a shared formatter.
8. **Test after migration:** dates, times, leap years, DST, invalid dates, zone signs, and languages. Compare business contracts, not just strings in one environment.
9. **Benchmark performance after correctness:** benchmark per-call, synchronized, `ThreadLocal`, and `DateTimeFormatter` on realistic workloads; never choose an unsafe design based on assuming formatter creation is expensive.

The runnable examples in sections 6–9 produce stable output by configuring UTC and collecting results in order. If an intentionally **unsynchronized** stress test is ever written against a shared formatter, use it strictly to **reproduce the risk**—never put it in production code and never declare "it ran fine once so it's safe."

## 14. Frequently asked questions

**Can `SimpleDateFormat` be used inside a normal method?**

Yes. If a formatter is created and used by one task at a time without being published to other threads, sequential use is normal. The problem is **concurrent access to the same instance**.

**Is calling only `format`, without `parse`, safe?**

Not guaranteed. `SimpleDateFormat`'s contract does not permit inferring that concurrent `format` calls on the same mutable object are thread-safe.

**Does `static final` guarantee safety?**

No. `final` only fixes the reference; it does not prevent the object from mutating internal state or having its configuration changed via setters.

**Is adding `synchronized` to just one method calling the formatter enough?**

Only if **every** access path to that same instance goes through the same lock and nothing mutates state outside the lock. If the application exposes the instance for direct calls elsewhere, that guarantee breaks easily. Full synchronization can also cause contention.

**Is `ThreadLocal` always better than creating a new instance?**

No. It reduces object allocation in some scenarios but requires lifecycle management, proper state cleanup, and preventing config leakage across requests in thread pools. Creating a fresh instance is often easier to verify.

**Is `DateTimeFormatter` safe when used by multiple threads simultaneously?**

Yes, per its API contract; it is immutable and thread-safe. However, each thread still needs proper temporal data and locale/zone configuration, and surrounding code must manage other mutable state separately.

**Can `SimpleDateFormat` be kept forever if properly locked?**

It can be kept temporarily in legacy systems when all accesses are controlled and performance is acceptable. However, for new code or major upgrades, `java.time` typically provides a clearer data model and eliminates mutable-formatter sharing risks.

## 15. Solution comparison table

| Solution | Safety when implemented properly | Cost / limitations | When to consider |
| --- | --- | --- | --- |
| Create `SimpleDateFormat` per task | No shared mutable formatter | Allocation/initialization cost | Quick, simple fix under moderate load |
| `synchronized` around all shared accesses | Safe if all paths use the same lock | Serialization; easy to miss a code path | Legacy code hard to refactor, single-point control needed |
| `ThreadLocal<SimpleDateFormat>` | Each thread has its own formatter | Lifecycle, config, and cleanup management | Measured justification in a legacy system |
| Shared `DateTimeFormatter` | Immutable, thread-safe per API | Requires meaningful migration of types/patterns/zones | Preferred choice for modern Java code |

## 16. Key takeaways

- **`SimpleDateFormat` is a mutable, non-thread-safe formatter.** `format` and `parse` operations on the same instance must not be shared arbitrarily across multiple threads.
- **`static final` fixes the reference rather than making the object immutable.** Races still occur with a shared legacy formatter.
- **How to avoid the risk:** create a separate formatter per task, synchronize **all** accesses, or manage a per-thread instance with a clear lifecycle.
- **Recommendation for new code:** use immutable, thread-safe `java.time.format.DateTimeFormatter`; still choose the right temporal type, locale, zone, and pattern.
- **Do not treat stress-test results as a safety contract.** Seeing no failures does not mean thread-safe; design quality rests on API contracts and proper shared-state management.
