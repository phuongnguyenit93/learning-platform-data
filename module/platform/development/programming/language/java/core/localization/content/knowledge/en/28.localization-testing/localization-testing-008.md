# Multi-Threaded Testing with Different Formatters and Locales

## 1. The Problem: Correct for One Request, Broken Under Concurrent Users

A multilingual Java application can simultaneously serve `en-US`, `de-DE`, `vi-VN`, and `fr-FR` users. Each user has distinct rules for displaying numbers, percentages, currencies, dates/times, and messages. If a **mutable stateful** formatter is shared across requests, one thread can alter its configuration while another thread is using it, causing:

- A US user seeing German grouping marks, decimal points, or currency symbols.
- Order A's USD amount rendering with a `€` symbol because request B just called `setCurrency`.
- `SimpleDateFormat` returning wrong results, random parse failures, or exceptions when shared across threads.
- Changing JVM-wide `Locale.setDefault` per request, causing other requests to receive default formatters for the wrong locale.
- Sequential tests passing while load/concurrency tests flake: given identical inputs and domain values, output becomes nondeterministic.

This is an object **state and ownership** design issue, not a translation bug. The underlying domain data `BigDecimal("1234.50")` and `Currency USD` must remain intact. Only the **presentation formatter** is responsible for formatting according to **that specific request's** locale and zone.

This lesson belongs to **Testing and Pitfalls**, focusing on how to **detect, reproduce, fix, and test** bugs caused by multiple threads using formatters and locales concurrently. All main examples use Java 17+.

### Objectives

After this lesson, you can:

1. Distinguish **mutable, non-thread-safe** APIs from **immutable/thread-safe** APIs.
2. Understand why holding a static `NumberFormat`/`SimpleDateFormat` and mutating locale/currency per request is hazardous.
3. Write controlled race tests using **`CountDownLatch`** instead of hoping random scheduling triggers the bug.
4. Reproduce locale leakage caused by `Locale.setDefault(...)` in a multi-threaded server.
5. Implement **per-operation/request** formatters or share immutable `DateTimeFormatter`s safely.
6. Design stress tests across multiple locales, number/date/currency kinds, fixed datasets, and domain invariants.
7. Understand the limits of `ThreadLocal`, `Locale`-keyed caches, `ResourceBundle`, `MessageFormat`, and `Collator`.
8. Distinguish testing **functional correctness** from testing **reproducible race evidence**.

## 2. What State Does a Formatter Object Hold?

Example:

```java
NumberFormat number =
        NumberFormat.getCurrencyInstance(Locale.US);
number.setCurrency(Currency.getInstance("USD"));
number.setMaximumFractionDigits(2);
```

This snippet illustrates code inside a method, requiring `import java.text.NumberFormat`, `java.util.Currency`, `java.util.Locale`. Even though the formatter was created for `Locale.US`, the object holds mutable configuration fields: currency, grouping, precision, rounding, parsing behavior, symbols, and in `DecimalFormat` also pattern, multiplier, and `DecimalFormatSymbols`.

If you keep an instance in a static field:

```java
// Anti-pattern if multiple requests can alter configuration:
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance(Locale.US);
```

then `final` guarantees only that the **reference cannot be reassigned**. It **does not freeze internal state**. Thread A may call `SHARED.setCurrency(USD)` and Thread B call `SHARED.setCurrency(EUR)` before Thread A runs `format`.

Even if every request only calls `format` on the same `NumberFormat` without actively calling setters, the Java SE documentation explicitly warns **number formats are generally not synchronized**. Never infer thread safety merely because your current code does not mutate configuration after initialization.

### API Properties Reference Table

| API | Key characteristic | Usage strategy |
| --- | --- | --- |
| `java.text.NumberFormat` | Mutable; not guaranteed thread-safe | Separate instance per operation or intentional synchronization |
| `java.text.DecimalFormat` | Mutable: pattern, symbols, rounding, multiplier, and parse state | Never share mutable formatters across requests |
| `java.text.DateFormat` / `SimpleDateFormat` | Mutable; unsafe for unsynchronized sharing | Prefer `java.time`; for legacy, create per-operation instances |
| `java.text.MessageFormat` | Mutable: pattern, locale, subformatters | Separate instance, or clone/synchronize under clear contract |
| `java.text.Collator` | Mutable: strength/decomposition; not guaranteed safe for shared config | One instance per operation or independent copies |
| `java.util.Calendar` | Mutable date/time fields, locale/week policy | Never share across requests |
| `java.util.TimeZone` | Mutable config in some subclasses; global default can change | Avoid shared mutable objects |
| `java.time.format.DateTimeFormatter` | **Immutable and thread-safe** | Safe to share with fixed configuration |
| `java.time.Instant`, `LocalDate`, `ZonedDateTime` | Immutable | Safe to share as value objects |
| `java.util.Locale` | Immutable | Shareable; store locale in per-request context |
| `java.util.Currency`, `BigDecimal` | Immutable value objects | Use as domain data; format at boundaries |
| `java.util.ResourceBundle` | Bundle lookup supports concurrent access; custom providers/subclasses may hold state | Pick explicit locale, never mutate bundles/custom data |
| `java.text.DecimalFormatSymbols` | Mutable | Never share and mutate symbols across threads |

**Core insight:** `Locale` immutability does not transfer to a mutable formatter constructed from that locale. Likewise, `DateTimeFormatter` thread safety does not mean you can mutate JVM-wide `Locale.setDefault` without affecting other requests.

## 3. Three Distinct Bug Categories Requiring Dedicated Tests

### 3.1. Data Race and Shared Mutable State

Two threads share one instance. One thread calls `setCurrency`, `setGroupingUsed`, or changes the pattern while the other thread formats. Logical corruption can happen even if setter and `format` **do not overlap on the exact same CPU instruction**: simple interleaving between two requests is enough.

### 3.2. Global-State Interference

A request calls `Locale.setDefault(...)` or `Locale.setDefault(Locale.Category.FORMAT, ...)` to switch languages temporarily. That sets the **JVM-wide default**, not a local request or thread variable. Another request calling `NumberFormat.getNumberInstance()` **without a locale** may pick up the previous user's locale.

### 3.3. Incorrect Cache Keys or Formatter Lifecycles

A cache like:

```java
Map<String, DateTimeFormatter> cache;
```

is not automatically correct just because `ConcurrentHashMap` is thread-safe. The key must also include **every setting affecting output**: pattern, `Locale`, `ZoneId`, chronology, and currency/numbering/rounding policy when applicable. Caching an immutable formatter keyed by pattern alone while omitting locale has no Java Memory Model data race, yet still **returns contextually wrong output**.

These are three separate bugs that can exist independently. A solid test suite verifies **thread safety**, **request isolation**, and **correct cache-key semantics**.

## 4. Anti-Pattern 1: One Shared `NumberFormat` Across Currencies

Suppose a server declares:

```java
static final NumberFormat CURRENCY_FORMAT =
        NumberFormat.getCurrencyInstance(Locale.US);

String show(BigDecimal amount, Currency currency) {
    CURRENCY_FORMAT.setCurrency(currency);
    return CURRENCY_FORMAT.format(amount);
}
```

This illustrative snippet belongs inside a class. The hazard: each request mutates a shared object to serve its own currency.

### Timeline

```text
Thread A (USD order)           Thread B (EUR order)
-------------------------      ------------------------
setCurrency(USD)
                               setCurrency(EUR)
format(1234.50)
→ result can be €1,234.50
```

Request A still holds the right `Currency USD` in its domain object; the bug happens because the shared formatter had its configuration overwritten. Fix it not by altering A's domain currency, but by fixing **formatter ownership**.

## 5. Deterministic Bug Reproduction Using `CountDownLatch`

A race test that launches two tasks and calls `sleep(10)` is unreliable: the scheduler can order execution differently, hiding the bug and letting broken code pass.

`CountDownLatch` lets you **pin the exact interleaving point**. The example below forces:

1. Thread A sets the shared formatter to USD.
2. Thread B waits for A, then sets the formatter to EUR.
3. Thread A formats only after B has switched the currency.

Create `SharedCurrencyRaceDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedCurrencyRaceDemo {
    static final NumberFormat SHARED =
            NumberFormat.getCurrencyInstance(Locale.US);

    public static void main(String[] args) throws Exception {
        CountDownLatch usdSet = new CountDownLatch(1);
        CountDownLatch eurSet = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<String> userA = pool.submit(() -> {
                SHARED.setCurrency(Currency.getInstance("USD"));
                usdSet.countDown();
                eurSet.await();
                return SHARED.format(new BigDecimal("1234.50"));
            });

            Future<String> userB = pool.submit(() -> {
                usdSet.await();
                SHARED.setCurrency(Currency.getInstance("EUR"));
                eurSet.countDown();
                return "configured EUR";
            });

            System.out.println("B: " + userB.get());
            System.out.println("A: " + userA.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SharedCurrencyRaceDemo.java
java SharedCurrencyRaceDemo
```

Result on a tested JDK with standard locale data:

```text
B: configured EUR
A: €1,234.50
```

Key observations:

- A **intended to format USD** yet received the EUR symbol.
- The latches guarantee B sets EUR before A calls `format`. This is **coordinated state interference**, not luck-based race probability.
- A's `NumberFormat` was still created with `Locale.US`, so grouping and decimal marks remain US-style; only the currency symbol changed. If locale provider/default or pattern also changed concurrently, failures would be even more erratic.
- Specific symbol output can vary by JDK/locale data; what your test must assert reliably is that **A's formatter currency/config was corrupted by B relative to request A**.
- `CountDownLatch.await()` throws `InterruptedException`; `Callable` selected by `ExecutorService.submit` permits throwing it here. Real production tasks need explicit interrupt/cancellation handling.

**Do not treat this example as valid formatter usage.** It intentionally demonstrates the failure mode for testing and training.

## 6. The Fix: Per-Task Private Formatters

Instead of `SHARED`, construct the formatter locally for the request:

```java
static String showMoney(BigDecimal amount,
        Currency currency, Locale locale) {
    NumberFormat formatter =
            NumberFormat.getCurrencyInstance(locale);
    formatter.setCurrency(currency);
    return formatter.format(amount);
}
```

Every invocation gets a fresh object. No other request holds the same instance to mutate before `format`. This fix is **simple, low-risk, and easy to test**.

**Do not confuse "create a private formatter" with "create a separate JVM"**; you only need a fresh object per invocation or an unshared lifetime. When profiling proves formatter allocation is genuinely a bottleneck, consider caching immutable configs or disciplined per-thread instances, while preserving locale, currency, and mutable state isolation.

### Java 17+ Example: Running 1,000 Multi-Locale Tasks

Create `SafeNumberConcurrencyDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SafeNumberConcurrencyDemo {
    public static void main(String[] args) throws Exception {
        final BigDecimal expected = new BigDecimal("1234.50");
        List<Callable<Boolean>> tasks = new ArrayList<>();

        for (int i = 0; i < 1_000; i++) {
            final Locale locale =
                    (i % 2 == 0) ? Locale.US : Locale.GERMANY;

            tasks.add(() -> {
                // Fresh instance, private to this single task.
                NumberFormat base =
                        NumberFormat.getNumberInstance(locale);
                if (!(base instanceof DecimalFormat formatter)) {
                    return false;
                }
                formatter.setMinimumFractionDigits(2);
                formatter.setMaximumFractionDigits(2);
                formatter.setParseBigDecimal(true);

                String rendered = formatter.format(expected);
                ParsePosition position = new ParsePosition(0);
                Number parsed =
                        formatter.parse(rendered, position);

                return parsed instanceof BigDecimal exact
                        && expected.compareTo(exact) == 0
                        && position.getIndex() == rendered.length();
            });
        }

        ExecutorService pool = Executors.newFixedThreadPool(8);
        int failures = 0;
        try {
            List<Future<Boolean>> results =
                    pool.invokeAll(tasks);
            for (Future<Boolean> result : results) {
                if (!result.get()) {
                    failures++;
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cases=" + tasks.size()
                + " failures=" + failures);
    }
}
```

```bash
javac -encoding UTF-8 SafeNumberConcurrencyDemo.java
java SafeNumberConcurrencyDemo
```

Stdout on the tested runtime:

```text
cases=1000 failures=0
```

This test checks **isolation and numeric round-trip when the formatter is configured to display 2 fractional digits**, using a value with exactly 2 fractional digits. One run **does not prove** every JDK/provider version is safe, nor does it validate strict grouping grammar. Still, the per-task design avoids the shared-mutable-object bug demonstrated earlier.

A production suite should also add:

- Varied amounts: negative, zero, large values, differing scales.
- `en-US`, `de-DE`, `fr-FR`, `vi-VN`, `ar-EG`, and multiple real currencies.
- Varied thread counts and schedules, simultaneous barriers, and repeated workloads.
- Assertions on **domain values** and currency codes, not merely non-empty string outputs.
- Rounding/scale policy tests when `format → parse` does not preserve all digits losslessly.

## 7. Anti-Pattern 2: Mutating `Locale.setDefault` per Request

`Locale.setDefault(...)` and `Locale.setDefault(Locale.Category.FORMAT, ...)` change the **JVM-wide default**. They do not create a thread- or request-local locale.

Distinguish:

- `Locale.getDefault()`: general default locale.
- `Locale.getDefault(Locale.Category.DISPLAY)`: default for displaying locale/language names.
- `Locale.getDefault(Locale.Category.FORMAT)`: default for many number/date formatter factories.
- `NumberFormat.getNumberInstance()`: **locale-less** overload relying on the `FORMAT` default.
- `NumberFormat.getNumberInstance(locale)`: **explicit-locale** overload avoiding global defaults.
- `String.format(locale, ...)`: explicitly picks a locale for string formatting; parameterless `String.format(...)` uses the `FORMAT` default.
- `DateTimeFormatter.withLocale(locale)`: returns an immutable formatter configured with an explicit locale.

**Trap:** code calls `Locale.setDefault(Locale.US)` to "initialize an English environment," and later a request calls `setDefault(Locale.GERMANY)`. No thread-local guard protects this JVM global while other requests call factory APIs without passing a locale.

### Failure Timeline

```text
Thread A: setDefault(FORMAT, en-US)
Thread B: setDefault(FORMAT, de-DE)
Thread A: NumberFormat.getNumberInstance().format(1234.5)
       → 1.234,5 (German format)
```

**Right approach:** always resolve the request's `Locale` from a validated profile/session/input and pass it to the formatter:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(requestLocale);
```

Never mutate the global default per request. For single-locale processes, configuring the default at startup can be reasonable, yet formatter dependencies should still stay explicit and tests should never depend on the developer machine's locale.

## 8. Java 17+: Reproducing a `Locale.setDefault` Race

The following example **intentionally mutates the JVM-wide default**, so run it only as a **standalone demo program**—never inside a server or shared test suite alongside tasks relying on the default locale. It saves and restores `Locale.Category.FORMAT` inside `finally`.

File `DefaultLocaleRaceDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class DefaultLocaleRaceDemo {
    public static void main(String[] args) throws Exception {
        Locale original =
                Locale.getDefault(Locale.Category.FORMAT);
        CountDownLatch usSet = new CountDownLatch(1);
        CountDownLatch deSet = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.US);

            Future<String> userA = pool.submit(() -> {
                Locale.setDefault(
                        Locale.Category.FORMAT, Locale.US);
                usSet.countDown();
                deSet.await();
                // Wrong: factory does not take request locale.
                return NumberFormat.getNumberInstance()
                        .format(1234.5);
            });

            Future<String> userB = pool.submit(() -> {
                usSet.await();
                Locale.setDefault(
                        Locale.Category.FORMAT, Locale.GERMANY);
                deSet.countDown();
                return "set de-DE";
            });

            System.out.println("B: " + userB.get());
            System.out.println("A: " + userA.get());
        } finally {
            Locale.setDefault(
                    Locale.Category.FORMAT, original);
            pool.shutdown();
        }
    }
}
```

```bash
javac DefaultLocaleRaceDemo.java
java DefaultLocaleRaceDemo
```

Stdout on a standard runtime:

```text
B: set de-DE
A: 1.234,5
```

Thread A set `en-US`, yet by the time it created its formatter, the `FORMAT` default was `de-DE`. The latches make the failure **reproducible** instead of waiting for lucky scheduling.

**Scope of restoring the default:** `finally` cleans up the demo when nothing else in the JVM alters the default locale. In a real process where other threads mutate the default concurrently, even "save and restore" can **overwrite someone else's configuration**. That is why the proper architecture is **never mutating the default per request**, rather than wrapping every request in `try/finally`.

## 9. `SimpleDateFormat`: Legacy Pitfalls in Date-Time Handling

`java.text.SimpleDateFormat` extends `DateFormat` and is **mutable and non-thread-safe**. It holds internal stateful components such as `Calendar`, `NumberFormat`, and time zone. Even `parse`/`format` operations mutate internal state during execution, so sharing one static instance across threads can cause inconsistent output, exceptions, or corrupted parses—even when callers never invoke setters between requests.

Anti-pattern:

```java
// Do not share without synchronization:
private static final SimpleDateFormat FORMATTER =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
```

Even more dangerous is calling `setTimeZone(...)` per request on the shared object to serve multiple zones.

### Two Safe Approaches

**Approach A — legacy compatibility:** construct a fresh `SimpleDateFormat` inside each task, passing an explicit `Locale` and setting the task's `TimeZone`:

```java
SimpleDateFormat format =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", locale);
format.setTimeZone(TimeZone.getTimeZone(zoneId));
String text = format.format(legacyDate);
```

This snippet illustrates code inside a method with `locale`, `zoneId`, and `legacyDate` variables. For strict parsing, also call `setLenient(false)` and verify full-input consumption.

**Approach B — modern preference:** use `java.time.Instant`, `ZoneId`, and immutable `DateTimeFormatter`. These APIs allow sharing a base formatter; per-request locale/zone settings are applied with `withLocale`/`withZone`, returning new instances. Changing the presentation zone **never alters the underlying `Instant`**.

## 10. Immutable `DateTimeFormatter`: Sharing a Base Properly

Create an immutable formatter:

```java
static final DateTimeFormatter BASE =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.ROOT);
```

Per request:

```java
String text = BASE.withLocale(requestLocale)
        .withZone(requestZone)
        .format(instant);
```

No setter mutates `BASE`; `withLocale`/`withZone` returns a new formatter (or the same instance if unchanged). Hence there is no race on formatter state, provided the right per-request data is passed in.

### Java 17+: Verifying Two Zones Across Multiple Threads

Create `ImmutableDateTimeConcurrencyDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ImmutableDateTimeConcurrencyDemo {
    private static final DateTimeFormatter BASE =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

    public static void main(String[] args) throws Exception {
        Instant time = Instant.parse(
                "2026-10-28T01:30:00Z");
        ZoneId utc = ZoneId.of("UTC");
        ZoneId tokyo = ZoneId.of("Asia/Tokyo");

        String expectedUtc = BASE.withZone(utc).format(time);
        String expectedTokyo = BASE.withZone(tokyo).format(time);

        List<Callable<Boolean>> tasks = new ArrayList<>();
        for (int i = 0; i < 1_000; i++) {
            final ZoneId zone = (i % 2 == 0) ? utc : tokyo;
            final Locale locale = (i % 2 == 0)
                    ? Locale.US : Locale.GERMANY;
            final String expected = (i % 2 == 0)
                    ? expectedUtc : expectedTokyo;

            tasks.add(() -> BASE.withLocale(locale)
                    .withZone(zone).format(time).equals(expected));
        }

        ExecutorService pool = Executors.newFixedThreadPool(8);
        int failures = 0;
        try {
            List<Future<Boolean>> results =
                    pool.invokeAll(tasks);
            for (Future<Boolean> result : results) {
                if (!result.get()) {
                    failures++;
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("UTC=" + expectedUtc);
        System.out.println("Tokyo=" + expectedTokyo);
        System.out.println("cases=1000 failures=" + failures);
    }
}
```

```bash
javac ImmutableDateTimeConcurrencyDemo.java
java ImmutableDateTimeConcurrencyDemo
```

Stdout with a fixed `DateTimeFormatter` pattern:

```text
UTC=2026-10-28 01:30 Z
Tokyo=2026-10-28 10:30 +09:00
cases=1000 failures=0
```

The example intentionally uses fixed Latin/numeric pattern letters and `Locale.ROOT` so stdout barely depends on CLDR. With `ofLocalizedDateTime(FormatStyle.MEDIUM)`, month names, punctuation, and patterns can change across JDK/CLDR upgrades; tests should compare against expectations pinned to the locale/runtime.

**Do not assume everything in date-time is immutable:** `ZoneId` is an immutable value, yet tzdb rules can be updated across JDK releases; the same `Instant` and zone can display a different historical offset if tzdb changes. That is a time-zone data update, not a formatter race.

## 11. Testing `MessageFormat` and `Collator` in Multilingual Concurrency

### 11.1. `MessageFormat`

`java.text.MessageFormat` can mutate its locale, pattern, and sub-`Format`s. Never store a static `MessageFormat` and invoke `setLocale`/`applyPattern` across requests:

```java
// Unsafe if requests mutate shared state:
static final MessageFormat MESSAGE =
        new MessageFormat("{0,number}", Locale.US);
```

Beyond races, `MessageFormat.setLocale(...)` **does not automatically update every previously installed subformat** across arbitrary patterns. To produce locale-accurate messages, construct a fresh instance from the **locale's `ResourceBundle` pattern**:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", locale);
MessageFormat message = new MessageFormat(
        bundle.getString("order.summary"), locale);
String text = message.format(new Object[] {amount, count});
```

This snippet belongs inside a method, requiring `Messages_<language>.properties` on the classpath with the matching key. Never use a shared mutable `MessageFormat` as a global cache without ownership.

### 11.2. `Collator`

`Collator` performs language-aware comparison/sorting. It exposes setters such as `setStrength` and `setDecomposition`, so never share one `Collator` and adjust it per request. A comparator backed by a mutable `Collator` can also produce **inconsistent ordering** mid-sort.

**Do not mix two test goals:**

- Sorting tests verify locale ordering during a single sort using a fixed-configuration comparator.
- Concurrency tests ensure request A never alters the `strength`/`locale` of a comparator in use by request B.

If caching collators, check cloning or per-operation instances per the provider's API docs, and never mutate an object in use by multiple threads.

### 11.3. `ResourceBundle`

`ResourceBundle.getBundle(baseName, locale)` is designed for multi-threaded environments and includes internal caching. Bundle caching itself never forces you to call `Locale.setDefault` per request. Bugs usually come from:

- Calling `getBundle` **without a locale**, falling back to the JVM default.
- Storing an `en-US` `ResourceBundle` in an app-wide mutable "current bundle" field and swapping it when a `vi-VN` request arrives.
- Implementing a custom `ResourceBundle` subclass or mutable value map without thread-safe access.
- Extracting a mutable `MessageFormat` from a bundle and sharing it across threads.

Look up bundles using an **explicit locale**, call `getString(key)`, and format text within the request scope.

## 12. Is `ThreadLocal` the Answer?

`ThreadLocal<SimpleDateFormat>` is a common legacy workaround:

```java
static final ThreadLocal<SimpleDateFormat> FORMAT =
        ThreadLocal.withInitial(() ->
                new SimpleDateFormat("yyyy-MM-dd"));
```

It avoids sharing the **same instance** across threads. However, on servers using **thread pools**, each thread is reused across many users. If the `ThreadLocal` instance is initialized with the first request's locale/zone, a later request scheduled onto the same thread may inherit the **stale locale**. `ThreadLocal` isolates at the *thread* level, not the *request* level.

### Other Risks

- Values linger in pooled threads after a request ends, risking memory/context leaks.
- A single thread may need multiple formatters of different kinds/locales; keying by thread alone is insufficient.
- Async tasks can hop to different threads; `ThreadLocal` context does not automatically follow tasks.
- Exception paths missing `remove()` in `finally` retain state longer than intended.
- `ThreadLocal` does not prevent damage from JVM-wide `Locale.setDefault` calls.

**Preference:** create mutable formatters locally inside methods when cost is acceptable; use immutable formatters for `java.time`; introduce pooling/caching/`ThreadLocal` only after profiling, backed by concurrency, locale-switching, cancellation, and cleanup tests.

## 13. Formatter Caching: Cache the Right Thing Under the Right Key

Comparison of strategies:

| Cache | Thread safety | Notes |
| --- | --- | --- |
| `static NumberFormat SHARED` | **Unsafe** if shared unsynchronized | Mutable, config cross-talk |
| `ConcurrentHashMap<Locale, NumberFormat>` | Map is thread-safe, **formatters inside are still unsafe** | Insufficient |
| `ConcurrentHashMap<Key, DateTimeFormatter>` | Safe if `Key` is immutable and complete | `DateTimeFormatter` is immutable |
| Cache `String` pattern/locale policy | Safe if data is immutable | Allocate `DecimalFormat` per call |
| Clone a formatter template per request | Can work depending on provider/clone semantics | Must verify `clone()` produces independent state |
| `ThreadLocal<DecimalFormat>` | Separates per thread yet risks stale request locale | Use only with strict context management |
| Synchronize every operation on shared formatter | Avoids races if **all reads/writes** share one lock | Reduces throughput; easy to miss locks elsewhere |

**The cache key must capture every parameter affecting output.** For example, a date-time formatter may require `Locale`, `ZoneId`, pattern/style, and chronology. A currency formatter requires locale **and** currency code; rounding/fraction digits and numbering systems also matter.

### Java 17+: Properly Caching Immutable `DateTimeFormatter`s

Standalone snippet illustrating key design:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;

public class FormatterCacheDemo {
    record Key(Locale locale, ZoneId zone) {}

    private static final ConcurrentHashMap<Key, DateTimeFormatter>
            CACHE = new ConcurrentHashMap<>();

    static DateTimeFormatter get(Locale locale, ZoneId zone) {
        return CACHE.computeIfAbsent(
                new Key(locale, zone),
                key -> DateTimeFormatter
                        .ofPattern("uuuu-MM-dd HH:mm", key.locale())
                        .withZone(key.zone()));
    }

    public static void main(String[] args) {
        var a = get(Locale.US, ZoneId.of("UTC"));
        var b = get(Locale.GERMANY, ZoneId.of("UTC"));
        var c = get(Locale.US, ZoneId.of("Asia/Tokyo"));

        System.out.println("different locale key: " + (a != b));
        System.out.println("different zone key: " + (a != c));
        System.out.println("entries: " + CACHE.size());
    }
}
```

```bash
javac FormatterCacheDemo.java
java FormatterCacheDemo
```

```text
different locale key: true
different zone key: true
entries: 3
```

**Limitation:** this example hard-codes one pattern; if pattern/style varies by request, include it in `Key`. An unbounded cache without eviction can grow indefinitely if untrusted input supplies arbitrary locales/zones/patterns; production systems need size bounds and validation against supported locales/zones.

Cached instances are **immutable**, making sharing safe. `computeIfAbsent` protects map insertion, yet **cannot make a mutable value object inside thread-safe**.

## 14. Choosing the Right Oracle for Multi-Locale Testing

A broken concurrency test:

```java
// Wrong if threads are operating on the formatter concurrently:
assertEquals("1,234.50", shared.format(amount));
```

This assertion can fail when locale/currency legitimately varies, or pass by accident when no race occurs. Tests need expectations tied to the *request context*, not mutable global state.

### Test Metadata Each Task Should Carry

```text
requestId
localeTag
currencyCode if formatting money
zoneId if formatting date/time
domain amount/ratio/instant
pattern or style, rounding, and fraction digits
expected result or independently computed oracle
```

**Two levels of oracles:**

1. **Numeric/domain oracle**: `BigDecimal.compareTo`, currency code, `Instant.equals`, scale/rounding policy. These must hold regardless of CLDR.
2. **Presentation oracle**: localized display strings per CLDR/JDK data and pattern. When asserting exact literals, pin runtime/provider or use approved fixtures for that runtime.

A good test computes expectations **before parallel execution**, never relying on a shared mutable formatter being mutated by other threads. For instance, format a baseline sequentially with a dedicated formatter per locale, then run per-task formatters in the pool and compare against the baseline. Where different locales happen to produce identical text, still verify the **locale/currency context** rather than forcing every locale to emit distinct strings.

## 15. Building Stress Tests with Higher Race-Detection Probability

Running once on a developer laptop is not enough. Alongside deterministic latch tests reproducing a specific ordering, run stress tests with:

1. **High thread counts:** more threads than CPU cores, or matching production thread-pool sizing.
2. **Diverse locales/currencies:** `en-US`/`de-DE`/`fr-FR`/`vi-VN`, USD/EUR/JPY/VND; zones UTC/`Asia/Tokyo`/`Europe/Berlin` as needed.
3. **Diverse values:** zero, negative numbers, large amounts, varying `BigDecimal` scales, percentages, DST dates, text with Unicode spacing.
4. **Synchronized start:** use `CountDownLatch` or `CyclicBarrier` to maximize contention; never treat `Thread.sleep` as an oracle.
5. **Repetition:** iterate across multiple JDKs/providers/OSes; fix a seed if randomizing and log minimal failing inputs.
6. **Categorized failures:** wrong locale symbol, wrong number, exception, trailing unparsed suffix, precision loss, stale `ThreadLocal`, UI snapshot differing from CLDR.
7. **Time-bounded execution:** enforce task/future timeouts so CI never hangs; handle interrupts and cleanup on timeout/cancellation.
8. **Never swallow worker exceptions:** `Future.get()` throws `ExecutionException`; inspect the root cause rather than just counting `false` results.
9. **Do not share mutable domain objects:** `BigDecimal`/`Instant` are safely immutable, whereas tests using mutable `Calendar`/`Date` require clear snapshots/ownership.
10. **Do not synchronize inside the production code under test solely via test locks** if the production path itself lacks synchronization; otherwise bugs remain in production.

### Determinism and Limitations

- **Latch tests** deterministically prove a buggy interleaving; invaluable for regression tests.
- **Stress tests** raise the odds of catching other races; passing does not mathematically prove code is race-free.
- **Static analysis / code review** spots shared mutable fields and default-locale calls; complementary, not a replacement for tests.
- **Production-like load tests** exercise real thread pools, async context propagation, and framework request scopes.

**Do not immediately blame a race whenever a log line looks "weird."** Output differences can also come from CLDR, time-zone database, format patterns, or JVM default differences across environments. Reproduce with matching inputs/runtime and trace state ownership.

## 16. Locale Context Can Leak Across Thread Pools

In a web server, a German request may execute on a thread that previously served an English user. If the app stores request locale in a `ThreadLocal<Locale>` and forgets `remove()`, a later task can inherit the stale locale.

This is a **context leak**. Even if formatters are freshly constructed, they can still use the **wrong locale** due to leaked context.

### Lifecycle Pattern

```java
try {
    REQUEST_LOCALE.set(localeFromRequest);
    // Process request, creating formatters with this locale.
} finally {
    REQUEST_LOCALE.remove();
}
```

This snippet illustrates cleanup inside a class holding `ThreadLocal<Locale> REQUEST_LOCALE`. It shows proper cleanup only; `ThreadLocal` should not be your default choice. **Passing locale as an explicit parameter** through services/presenters is usually simpler and less error-prone.

With `CompletableFuture`/`ExecutorService`, tasks can run on different threads; plain `ThreadLocal` does not propagate automatically. Never work around this with JVM-wide `Locale.setDefault`. Pass `Locale`, `ZoneId`, and `Currency` into lambdas/tasks as immutable values, or use framework-supported context propagation and test it thoroughly.

## 17. Locale Issues That Look Like Threading Bugs (Yet Are Not)

### 17.1. `Locale` and `Currency` Are Independent

`Locale.GERMANY` does not force an order to be EUR. A German-speaking user can pay in USD. Test expectations need **both locale and currency code**. Never derive currency from `Currency.getInstance(locale)` when domain currency is stored separately.

### 17.2. `Locale.Category.DISPLAY` Differs from `FORMAT`

Mutating `Locale.Category.DISPLAY` affects display names of languages/countries, whereas `Category.FORMAT` governs number/date formatting. Test the API with the matching category. If building a race test for `NumberFormat.getNumberInstance()`, target **`FORMAT`**, not `DISPLAY`.

### 17.3. Unicode Grouping and CLDR

`fr-FR` may use **U+202F NARROW NO-BREAK SPACE**, while another runtime/provider uses U+00A0 or something else. Identical inputs with zero race can still differ after a JDK upgrade. In concurrency tests, pin runtime metadata on literal snapshots while checking domain values independently.

### 17.4. Time-Zone Rule Updates

Date/time formatting differences across tzdb versions can also break snapshots. It is not a race if every thread with the same zone and immutable formatter produces identical output within a single runtime.

### 17.5. Relying on Default Locale in Tests

CI often has a different default locale than a developer laptop. Pass `Locale` explicitly in tests, or run default-locale tests in an **isolated JVM**. A test mutating `Locale.setDefault` can interfere with parallel tests in the same JVM even if it uses `finally`.

## 18. A Complete Test: Request Context and Per-Call Formatters

A practical pattern packages immutable request data in a record:

```java
record DisplayContext(Locale locale, Currency currency) {}
```

Each task receives a fixed context. Every mutable formatter is constructed inside the task; no static mutable field holds a "current locale."

Create `RequestScopedFormattingDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RequestScopedFormattingDemo {
    record Context(Locale locale, Currency currency) {}

    static String render(BigDecimal amount, Context context) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(context.locale());
        formatter.setCurrency(context.currency());
        return formatter.format(amount);
    }

    public static void main(String[] args) throws Exception {
        BigDecimal amount = new BigDecimal("1234.50");
        Context us = new Context(
                Locale.US, Currency.getInstance("USD"));
        Context de = new Context(
                Locale.GERMANY, Currency.getInstance("EUR"));

        String expectedUs = render(amount, us);
        String expectedDe = render(amount, de);

        List<Callable<Boolean>> tasks = new ArrayList<>();
        for (int i = 0; i < 1_000; i++) {
            final Context context = (i % 2 == 0) ? us : de;
            final String expected = (i % 2 == 0)
                    ? expectedUs : expectedDe;
            tasks.add(() -> render(amount, context).equals(expected));
        }

        ExecutorService pool = Executors.newFixedThreadPool(8);
        int failures = 0;
        try {
            List<Future<Boolean>> results = pool.invokeAll(tasks);
            for (Future<Boolean> future : results) {
                if (!future.get()) {
                    failures++;
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cases=1000");
        System.out.println("failures=" + failures);
        System.out.println("context unchanged="
                + (us.currency().getCurrencyCode().equals("USD")
                && de.currency().getCurrencyCode().equals("EUR")));
    }
}
```

```bash
javac -encoding UTF-8 RequestScopedFormattingDemo.java
java RequestScopedFormattingDemo
```

```text
cases=1000
failures=0
context unchanged=true
```

Here exact rendering expectations are computed **sequentially with dedicated formatters** before launching the 1,000 tasks. That makes the test resilient without hard-coding symbols/spaces for a specific JDK. It detects output diverging from the runtime baseline, though it does not replace **currency-identity** tests or tests where two locales share identical output.

Using the `Context` record is not magic concurrency dust; it makes per-request dependency passing **explicit**. `Locale`/`Currency`/`BigDecimal` are inherently immutable value objects.

## 19. Testing Parsing When Formatters Have Different Locales

The same `"1,234"` can carry different meanings:

- `en-US`: typically one thousand two hundred thirty-four.
- `de-DE`: typically one point two three four.

Both parsers can consume **the entire string** yet return **two different values**. Therefore, checking `ParsePosition.getIndex()==input.length()`, while needed to reject suffixes, **will not catch using the wrong locale** when the input happens to be valid in both locales.

### An Ownership-Safe Parser

```java
static BigDecimal parseDecimal(String raw, Locale locale) {
    NumberFormat base = NumberFormat.getNumberInstance(locale);
    if (!(base instanceof DecimalFormat format)) {
        throw new IllegalStateException("DecimalFormat required");
    }
    format.setParseBigDecimal(true);
    ParsePosition pos = new ParsePosition(0);
    Number parsed = format.parse(raw, pos);

    if (!(parsed instanceof BigDecimal decimal)
            || pos.getIndex() != raw.length()) {
        throw new IllegalArgumentException("Invalid input");
    }
    return decimal;
}
```

This snippet illustrates a method inside a class importing `BigDecimal`, `NumberFormat`, `DecimalFormat`, `ParsePosition`, and `Locale`. Each call creates its own formatter, making concurrent requests safe. Remember that **full consumption does not equal strict grouping**: `DecimalFormat` may accept grouping separators in non-standard positions. For money or strict schemas, add lexical/domain validation.

### Essential Parsing Tests

| Input | Source locale | Expected value | Note |
| --- | --- | --- | --- |
| `"1,234"` | `en-US` | `1234` | Must pass source locale |
| `"1,234"` | `de-DE` | `1.234` | Same text, different value |
| `"1.234,50"` | `de-DE` | `1234.50` | Must not parse with US locale |
| `"1,234.50oops"` | `en-US` | REJECT | Full-input check |
| `"12,34.50"` | `en-US` | Depends on lexical policy | Full parse alone is insufficient |
| `"NaN"` | `en-US` | REJECT if Money domain | Can return special `Double` |
| `fr-FR` number using U+202F | `fr-FR` | Exact numeric value | Test Unicode space |
| USD amount displayed in `de-DE` | `de-DE` + USD | Right numeric amount, USD currency | Do not infer currency from locale |

**Concurrency bugs and locale mismatches can look identical:** if a `de-DE` request gets an `en-US` parser from a bad cache, `ParsePosition` might stop early or parse the whole string into the wrong number. Tests must assert **both source locale and numeric result**.

## 20. Deep Concurrency Test Matrix

| Group | Test scenario | What to assert |
| --- | --- | --- |
| Shared formatter | A sets USD, B sets EUR, A formats | Reproduces anti-pattern failure |
| Per-request formatter | 1,000–10,000 multi-locale tasks | Zero value/context mismatches |
| Global default race | A sets `en-US`, B sets `de-DE` | Locale-less overloads suffer interference |
| Immutable date formatter | Shared `BASE` + `withLocale`/`withZone` | Zero cross-task interference |
| Legacy `SimpleDateFormat` | Per-task instance or synchronized access | Never shared mutable |
| `MessageFormat` | Two locales, different patterns/placeholders | No content or grammar leakage |
| `Collator` | Two strengths and locales while sorting | Never mutate in-use comparator |
| `ThreadLocal` | Two requests with different locales on same pool thread | No stale locale |
| Async tasks | Locale passed to task rather than read from thread-local | Context never lost |
| Currency | USD/EUR/JPY, same and differing locales | Currency code and amount invariant |
| Number parsing | Same text in `en-US`/`de-DE` | Result matches source locale |
| Percent | Ratio `0.125` in `12.5%` | Not multiplied/divided by 100 twice |
| Date/time | UTC/Tokyo, DST transition days | `Instant` invariant, right zone |
| Unicode spaces | `fr-FR`, U+202F/U+00A0 grouping | Never compare spaces by eye |
| JDK/CLDR upgrade | Same task, same locale, different runtimes | Classify presentation diffs |
| Error handling | `Future` throws/timeout/interruption | Never drop test failures |
| Cleanup | Shutdown executor, clear `ThreadLocal` | No retained state after request |
| Performance | With/without formatter caching | Optimize only after correctness |

Put deterministic coordinated race tests in CI; stress tests can run extra iterations, worker counts, and runtimes. When using a unit test framework, isolate JVM-wide state per test. Tests that intentionally call `Locale.setDefault` should run in a **separate forked JVM** or be strictly serialized away from default-dependent tests.

## 21. Logging Failures Effectively

Using non-sensitive synthetic fixtures, log:

```text
testCaseId
threadName / taskId
request localeTag, currencyCode, zoneId
formatter type / intended configuration
domain input (anonymized fixture)
expected output / actual output
actual Unicode code points
parse consumed index + error index if any
Java runtime/version, locale provider
worker exception/timeout/interrupt status
```

**Never log user secrets or real transaction data** just to debug localization. When outputs differ over Unicode spaces, dump code points via `String.codePoints()` rather than eyeballing strings:

```java
static String points(String text) {
    return text.codePoints()
            .mapToObj(cp -> String.format(
                    Locale.ROOT, "U+%04X", cp))
            .toList().toString();
}
```

This illustrative snippet requires `import java.util.Locale`. It immediately distinguishes `U+0020`, `U+00A0`, and `U+202F` if a formatter or CLDR version changes whitespace characters.

## 22. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sharing `static final DecimalFormat` | `final` does not protect mutable state | Per-call instance or full synchronization |
| Using `ConcurrentHashMap<Locale, NumberFormat>` | Map is safe; formatters are still unsafe | Cache immutable config or per-call instance |
| A sets currency then formats on shared object | B swaps currency, giving A the wrong symbol | Domain currency + per-request formatter |
| Static `SimpleDateFormat` | Unstable multi-threaded parse/format | Immutable `DateTimeFormatter` |
| `Locale.setDefault` per request | Global locale cross-talk | Pass locale explicitly |
| Using `Locale.getDefault()` in user-facing parsers | Input source locale differs from server | Pass request input locale |
| Unreset `ThreadLocal` | Thread-pool context leak / stale locale | `finally`/`remove` or avoid `ThreadLocal` |
| Relying on `ThreadLocal` across async tasks | Tasks on other threads lose context | Pass immutable values into tasks |
| Cache key has pattern only, omits locale | Wrong output despite thread-safe map | Include `Locale`/`Zone`/pattern in key |
| Caching `DateTimeFormatter` from unvalidated input | Unbounded cache growth from arbitrary locales/zones | Validate and bound cache |
| Race tests using only `Thread.sleep` | Flaky and hard to reproduce | `CountDownLatch`/`CyclicBarrier` |
| Passing once means code is thread-safe | Misses unseen thread schedules | Deterministic interleaving + stress |
| Testing strings in a single locale | Misses separator and digit bugs | Multi-locale matrix |
| Hard-coding symbols/spaces across all JDKs | CLDR upgrades break tests spuriously | Runtime metadata + domain invariants |
| Comparing formatted strings when domain is numeric | Fails to verify business values | `BigDecimal`/currency code |
| Ignoring `Future.get()` | Swallows worker exceptions | Collect all futures, assert/propagate |
| Forgetting `shutdown()` on executor | Hanging threads, leaks | `finally`/`shutdown`, with timeout if needed |
| Treating full parse as right locale | Same text yields two different numbers | Verify source locale and numeric value |

## 23. Self-Check Questions

1. **Why is `static final NumberFormat` not automatically safe?** `final` freezes the reference, not the mutable formatter's internal state.
2. **Thread A sets USD, B sets EUR, then A formats—what can happen?** A displays the EUR symbol even though its domain currency is USD.
3. **Why is the `CountDownLatch` example better than `Thread.sleep`?** It enforces a deterministic interleaving that reliably reproduces the logic bug.
4. **Is `Locale` immutable?** Yes. Yet a formatter constructed from it can still be mutable.
5. **Does `Locale.setDefault` apply only to the current request?** No; it alters the JVM-wide default.
6. **Which locale does parameterless `NumberFormat.getNumberInstance()` use?** The JVM's `FORMAT` default locale.
7. **What does calling `NumberFormat.getNumberInstance(locale)` per task avoid?** Dependence on default locale and shared mutable configuration.
8. **Does `DateTimeFormatter.withLocale` mutate the original formatter?** No; it returns a configured immutable formatter.
9. **Is `SimpleDateFormat` safe to share across threads?** Not without proper synchronization.
10. **Is `ConcurrentHashMap<Locale, DecimalFormat>` enough to protect formatting?** No; it only protects the map structure.
11. **Does `ThreadLocal` guarantee the right locale for the next request on the same thread?** No, if stale state or a mismatched cache persists.
12. **Why is `Future.get()` critical in stress tests?** To observe results and exceptions instead of silently losing worker failures.
13. **Does multi-threaded `ResourceBundle` usage require `setDefault`?** No; load bundles with explicit locales.
14. **Can `MessageFormat` use one static instance with `setLocale` per request?** Avoid doing so; it holds mutable state and subformats.
15. **Are two threads deriving `DateTimeFormatter` from a shared immutable `BASE` safe?** Yes, when using immutable methods and right per-request context.
16. **Why is `"1,234"` dangerous across `en-US` and `de-DE`?** It can parse completely in both yet yield two different values.
17. **Does a stress test passing 1,000 tasks prove all races are gone?** No; it only verifies the scenarios and schedules executed.
18. **Why might a French number literal snapshot flake after a JDK upgrade?** CLDR can change grouping spaces between U+202F and U+00A0.
19. **How should a request's locale be passed into a `CompletableFuture`?** Capture/pass immutable arguments explicitly instead of relying on `ThreadLocal` propagation.
20. **When should an immutable formatter cache key include `Locale` and `ZoneId`?** Whenever those attributes affect output, along with any relevant pattern/style.
21. **If date-time output changes due to a tzdb update, is that a race?** No; compare against runtime/zone rules.
22. **What must remain invariant even when requests run concurrently across changing locales?** Domain amounts, currency codes, ratios, `Instant`s, state, and business correctness.
23. **Why is locking only around `format` potentially insufficient?** If configuration setters sit outside the same lock, another thread can still interleave between setter and `format`.
24. **When must `Locale.Category.DISPLAY` be tested separately?** When code displays language/region names rather than `FORMAT` numbers/dates.

## 24. Pre-Deployment Checklist

- [ ] Identify all mutable formatters held in static fields, singletons, or caches.
- [ ] Ensure no request calls `Locale.setDefault` or `TimeZone.setDefault` to switch user context.
- [ ] Every number/currency formatter receives an explicit `Locale` and domain currency code.
- [ ] Mutable legacy formatters are created per operation, or the entire set/format/parse sequence is properly synchronized.
- [ ] For new date-time code, prefer `DateTimeFormatter` and immutable `java.time` types.
- [ ] `MessageFormat` and `Collator` are never reconfigured while shared across tasks.
- [ ] Mutable objects are never placed in a `ConcurrentHashMap` and assumed thread-safe.
- [ ] Any immutable formatter cache includes locale/zone/pattern/style in its key and enforces lifecycle bounds.
- [ ] Any `ThreadLocal` cleans up properly and is tested with thread pools and async tasks, or removed if unnecessary.
- [ ] Stress tests cover multiple locales/currencies/zones, multiple threads, diverse values, and inspect `Future.get()`.
- [ ] At least one deterministic interleaving test exists for previously observed anti-patterns.
- [ ] `Thread.sleep` is never used alone to control test ordering.
- [ ] Tests separate numeric/instant domain invariants from CLDR presentation output.
- [ ] Input parsers verify full consumption, source locale, and strict grammar/domain rules where required.
- [ ] Tests mutating default locale run in isolated JVMs so other tests are unaffected.
- [ ] CI tests log JDK/provider/locale and Unicode code points when unexpected outputs occur.
- [ ] Executors and resources are cleaned up in `finally`; timeouts and interrupts follow policy.

## References

- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): warning that number formats are not synchronized, locale-specific factories, and parsing.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): mutable configuration, patterns, symbols, and rounding.
- [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html): synchronization and legacy date-time handling.
- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): patterns, locale, subformats, and mutability.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): mutable collation strength/decomposition.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): immutable, thread-safe formatting by locale/zone.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `setDefault`, `getDefault`, and `Locale.Category.FORMAT`/`DISPLAY`.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): bundle/cache mechanics and locale-specific lookup.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating thread execution order in tests.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/invokeAll/shutdown.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): lifetime, set/get/remove, thread-pool context.
- [Unicode CLDR](https://cldr.unicode.org/): source of locale data, Unicode number/date/currency patterns updated across releases.
