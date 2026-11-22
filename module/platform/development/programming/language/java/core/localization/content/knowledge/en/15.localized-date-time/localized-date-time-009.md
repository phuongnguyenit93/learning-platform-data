# Immutability and Thread Safety of `DateTimeFormatter` in Java

## 1. The Problem: Formatting Dates and Times in Multi-Threaded Applications

A web system can handle hundreds of concurrent requests. Each request needs to convert a `LocalDate`, `Instant`, or `ZonedDateTime` into a date/time string tailored to the user's locale and time zone; other requests need to parse date/time strings back into Java data types.

A clean design is to **reuse a configured `DateTimeFormatter`** when multiple tasks share the same formatting rules. Java guarantees that `java.time.format.DateTimeFormatter` is **immutable and thread-safe**.

The two properties are related, yet not synonymous:

- **Immutability:** once created, a `DateTimeFormatter`'s configuration state cannot be modified by operations such as `format`, `parse`, `withLocale`, or `withZone`.
- **Thread safety:** multiple threads can concurrently call read/format/parse operations on **the same formatter** without external `synchronized` blocks just to protect the formatter's internal state.

This contrasts with `java.text.SimpleDateFormat`, which holds mutable state and **is not safe to share arbitrarily across threads**.

**Core point:** the formatter's thread safety does not make every passed-in object or data source immutable; nor does it solve choosing locales, time zones, calendars, date resolution, or validating invalid inputs.

## 2. Understanding "Immutable": Configuration Is Never Mutated in Place

Think of a formatter as a **rule-describing object** holding pattern, locale, chronology, decimal style, resolver style, and optionally a zone override. Once construction finishes, that configuration stays fixed.

Example:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);

DateTimeFormatter german = base.withLocale(Locale.GERMANY);
```

`withLocale(Locale.GERMANY)` **does not mutate** `base`; it returns a formatter configured with the requested locale. Hence `base` still uses English for month names, while `german` can use German.

Main `with...` methods:

| Method | Configuration changed on returned formatter | What does NOT happen |
| --- | --- | --- |
| `withLocale(locale)` | Locale used for localized text and related formatting rules | Does not change the original formatter's locale |
| `withZone(zone)` | Zone override for formatting/parsing per API semantics | Does not reset the JVM's global time zone |
| `withChronology(chronology)` | Chronology override | Does not mutate the source temporal object |
| `withDecimalStyle(style)` | Digit symbols, decimal separator, negative sign, etc. used where applicable | Does not alter every string in the application |
| `withResolverStyle(style)` | Policy for resolving date/time fields | Does not force the original formatter to switch resolver styles |
| `withResolverFields(...)` | Set of fields used during the resolve step | Does not change the original formatter |

**Note on object identity:** the API may optimize by returning **the same instance** if the requested configuration already matches the existing state. Therefore, do not test immutability with `a != a.withLocale(a.getLocale())`. The contract rests on **no observable mutation**, not "every call strictly allocates a new object".

Also remember: to use a modified configuration, **capture the return value**:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);

base.withLocale(Locale.GERMANY); // Does not modify base.
DateTimeFormatter german = base.withLocale(Locale.GERMANY); // Correct.
```

If you discard the return value, the application keeps using the original formatter. This is a common mistake when migrating from mutable setter-based APIs to immutable APIs.

## 3. Complete Example: `withLocale` Does Not Mutate the Original Formatter

Create **`ImmutableFormatterDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ImmutableFormatterDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);
        DateTimeFormatter german =
                english.withLocale(Locale.GERMANY);

        System.out.println("english=" + english.format(date));
        System.out.println("german=" + german.format(date));
        System.out.println("english-again=" + english.format(date));
        System.out.println("same-object=" + (english == german));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ImmutableFormatterDemo.java
java -cp . ImmutableFormatterDemo
```

Output with standard JDK English/German locale data:

```text
english=28 October 2026
german=28 Oktober 2026
english-again=28 October 2026
same-object=false
```

**Explanation:** `german` carries a different locale, yet the `english` formatter retains its original configuration. The `date` variable is a fixed `LocalDate` and is unchanged by formatting.

Month name output relies on the Java runtime's locale data; across JDK/CLDR releases and other languages, spelling can vary. Snapshot tests must account for locale data/versions; purely numeric examples are usually more stable for thread-safety tests.

### Common misconceptions when calling `withLocale`

- `withLocale` does not translate **literal words** explicitly placed in a pattern by the developer, such as `'tháng'`; it affects formatted elements backed by locale data such as month and day names.
- `withLocale` does not automatically change the **time zone**. A user choosing Vietnamese is not necessarily in Vietnam's time zone.
- `withLocale` does not dictate **display style** for every custom pattern. If a pattern is fixed as `dd/MM/uuuu`, the slashes and field order specified in the pattern stay that way.
- To get a date/time layout adapted to the locale (short, medium, long), use `DateTimeFormatter.ofLocalizedDate(...)` or `ofLocalizedDateTime(...)` with the right locale; localized pattern data may vary by JDK.

## 4. Thread-Safe Means One Formatter Can Be Shared

A fully initialized formatter can be held in a constant:

```java
private static final DateTimeFormatter DATE_FORMATTER =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu", Locale.US);
```

Multiple threads can then call `DATE_FORMATTER.format(date)` and `LocalDate.parse(input, DATE_FORMATTER)` concurrently, provided application logic does not share **other unsafe mutable state**.

Mental model comparison:

```text
Multiple requests
    │
    ├── request A ──> format(dateA) ──┐
    ├── request B ──> parse(textB) ──┤
    ├── request C ──> format(dateC) ──┤── shared formatter (immutable)
    └── request D ──> parse(textD) ──┘
```

You do not need to construct a new `DateTimeFormatter` for **every** format call if all requests use the same configuration. Nor do you need `ThreadLocal<DateTimeFormatter>` just out of fear that a Java Time formatter has mutable state.

However, sharing the **same formatter** is valid only when requests genuinely need **the same pattern, locale, chronology, resolver, and zone override**. If users have different locales, obtain a formatter variant per locale rather than forcing one formatter with the wrong locale on every user.

## 5. Java 17+ Example: Using One Formatter Across Multiple Threads

The example below shares the `SHARED` constant across four tasks. The tasks run on a thread pool, using the formatter to format and then parse dates. To make output deterministic, the program **reads each `Future` in task submission order**, rather than printing directly from worker threads.

Create **`SharedFormatterDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedFormatterDemo {
    private static final DateTimeFormatter SHARED =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < 4; i++) {
                final int taskId = i;

                tasks.add(() -> {
                    LocalDate date = LocalDate.of(2026, 10, 28)
                            .plusDays(taskId);
                    String text = SHARED.format(date);
                    LocalDate parsed = LocalDate.parse(text, SHARED);

                    return "task-" + taskId + ": " + text
                            + " -> " + parsed;
                });
            }

            List<Future<String>> results = pool.invokeAll(tasks);

            for (Future<String> future : results) {
                System.out.println(future.get());
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SharedFormatterDemo.java
java -cp . SharedFormatterDemo
```

Output:

```text
task-0: 28/10/2026 -> 2026-10-28
task-1: 29/10/2026 -> 2026-10-29
task-2: 30/10/2026 -> 2026-10-30
task-3: 31/10/2026 -> 2026-10-31
```

Each `Callable` uses **the same `SHARED` formatter object**. Each task's `LocalDate` and date string are created separately; `Future.get()` waits for results and prints them in fixed order. Actual thread scheduling order may vary, without affecting correctness or output line order.

**Academic note:** a single successful run of a multithreaded program is **not a mathematical proof** that an API is thread-safe; that guarantee comes from **`DateTimeFormatter`'s contract**. The example illustrates valid usage; do not rely on trying to trigger a data race and waiting for failures to "prove" thread safety.

## 6. `withZone` Returns a New Configuration Without Mutating the Shared Formatter

Dates and times also involve **time zones**. An `Instant` describes an absolute point in time, yet printing local time requires choosing a `ZoneId`. `DateTimeFormatter.withZone` creates a formatter with a **zone override**, suitable for formatting an `Instant` with a pattern containing hours and offsets.

Example:

```java
DateTimeFormatter utcFormatter =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US)
                .withZone(ZoneOffset.UTC);

DateTimeFormatter vietnamFormatter =
        utcFormatter.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
```

When formatting the same `Instant`, the two formatters produce different local times. Crucially, `utcFormatter` is not switched to Vietnam time by the `withZone` call.

### Complete program

Create **`FormatterZoneDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class FormatterZoneDemo {
    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-10-28T10:15:30Z");

        DateTimeFormatter utc =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.US)
                        .withZone(ZoneOffset.UTC);

        DateTimeFormatter hcm =
                utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC=" + utc.format(instant));
        System.out.println("HCM=" + hcm.format(instant));
        System.out.println("UTC-again=" + utc.format(instant));
    }
}
```

Run:

```bash
javac -encoding UTF-8 FormatterZoneDemo.java
java -cp . FormatterZoneDemo
```

Output:

```text
UTC=2026-10-28 10:15 Z
HCM=2026-10-28 17:15 +07:00
UTC-again=2026-10-28 10:15 Z
```

**Notes on the time model:**

- `Locale` is not `ZoneId`. Vietnamese can be used in any time zone.
- `Instant` can be converted to local time once a zone is supplied; `LocalDateTime` itself **does not represent an absolute point in time**, so you must not attach an offset as if it carried a time zone.
- When formatting by region, use region zone IDs such as `Asia/Ho_Chi_Minh` or `Europe/Paris` if the system needs regional/historical rules; a fixed offset like `+07:00` does not represent every rule of a region across all dates.
- Never call `TimeZone.setDefault(...)` or `Locale.setDefault(...)` per request to change global settings. Mutating defaults changes shared state and can cause cross-user interference.

## 7. `ResolverStyle` Is Immutable Yet Affects Parsing Results

A formatter may need to resolve date/time fields with different levels of strictness. `DateTimeFormatter.ofPattern(...)` defaults to `ResolverStyle.SMART`; `withResolverStyle(ResolverStyle.STRICT)` returns another formatter applying strict rules.

Put `uuuu` in the pattern when validating dates in the proleptic Gregorian year to avoid confusion between `yyyy` (year-of-era) and `uuuu` under `STRICT`.

Complete example **`ResolverStyleDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    public static void main(String[] args) {
        DateTimeFormatter smart =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.US);

        DateTimeFormatter strict =
                smart.withResolverStyle(ResolverStyle.STRICT);

        System.out.println("smart-style=" +
                smart.getResolverStyle());
        System.out.println("strict-style=" +
                strict.getResolverStyle());

        System.out.println("smart=" +
                LocalDate.parse("2026-02-30", smart));

        try {
            LocalDate.parse("2026-02-30", strict);
            System.out.println("strict=accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("strict=DateTimeParseException");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ResolverStyleDemo.java
java -cp . ResolverStyleDemo
```

Output:

```text
smart-style=SMART
strict-style=STRICT
smart=2026-02-28
strict=DateTimeParseException
```

Here `SMART` adjusts February 30 to the last day of the month, whereas `STRICT` rejects it. Both formatters are immutable. Immutability **does not decide** date validation policy; the developer must choose the `ResolverStyle` matching business rules.

For transaction dates or birth dates requiring exactness, consider `STRICT` with the right pattern and chronology. For display-only or lenient contexts, defaults may be acceptable, provided they are tested.

## 8. `DateTimeFormatterBuilder` Is **Not** `DateTimeFormatter`

This is an important distinction during construction:

- `DateTimeFormatterBuilder` is a **mutable builder**: methods like `appendPattern`, `appendLiteral`, `appendValue`, and `optionalStart` mutate the **builder's in-progress state**.
- The `DateTimeFormatter` produced by `builder.toFormatter(...)` is an **immutable formatter** safe to share across threads.

Do not share **the same builder** across multiple threads calling `append...`, because the builder holds mutable state. Finish building in a controlled place, then publish the completed formatter to request-handling threads.

Create **`BuilderFreezeDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.Locale;

public class BuilderFreezeDemo {
    public static void main(String[] args) {
        DateTimeFormatterBuilder builder =
                new DateTimeFormatterBuilder();

        builder.appendPattern("dd/MM/uuuu");

        DateTimeFormatter frozen =
                builder.toFormatter(Locale.US);

        // Continue mutating builder; does not affect 'frozen'.
        builder.appendLiteral('!');
        DateTimeFormatter later =
                builder.toFormatter(Locale.US);

        LocalDate day = LocalDate.of(2026, 10, 28);
        System.out.println("frozen=" + frozen.format(day));
        System.out.println("later=" + later.format(day));
    }
}
```

Run:

```bash
javac -encoding UTF-8 BuilderFreezeDemo.java
java -cp . BuilderFreezeDemo
```

Output:

```text
frozen=28/10/2026
later=28/10/2026!
```

Calling `appendLiteral('!')` mutates the builder; the `frozen` formatter created earlier still outputs text without `!`. This illustrates the exact boundary between **mutable construction** and an **immutable formatter**.

### Why is the builder useful?

`DateTimeFormatterBuilder` supports complex templates: optional sections, variable-width digits, case-sensitive/insensitive parsing, lenient/strict syntax parsing, text maps for temporal fields, zones, offsets, and more.

Note that the builder's `parseStrict()`/`parseLenient()` affect the **field syntax parsing phase**, which differs from `withResolverStyle(STRICT/SMART/LENIENT)` affecting the **phase that resolves parsed fields into date/time objects**. Immutability does not erase the difference between these two phases.

## 9. Why Should `SimpleDateFormat` Not Be Shared Arbitrarily?

The legacy API `java.text.SimpleDateFormat` is **mutable** and not thread-safe by default. It holds and mutates internal state related to `Calendar`, `DateFormat`, `NumberFormat`, and other settings during parsing and formatting.

The following code is an **anti-pattern** in multithreaded applications:

```java
// Anti-pattern snippet to avoid:
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("dd/MM/yyyy");

// Multiple concurrent threads:
SHARED.format(date);
SHARED.parse(input);
```

Even though the `SHARED` reference is `static final`, **the referenced object itself remains mutable**. The `final` keyword only prevents reassigning the variable/reference; it **does not make the object immutable**. Threads can corrupt each other's state, producing wrong results or intermittent exceptions. Never treat "ran multiple times without seeing a failure" as proof of safety.

Proper alternatives:

1. **Prefer `java.time` + `DateTimeFormatter`** whenever you can design or migrate the system.
2. If forced to keep `SimpleDateFormat`, create **a separate instance per task** or guard access with proper synchronization; `ThreadLocal` can help, though it requires managing lifecycle, configuration, and cleanup.
3. Do not simply change `static` to `static final` and assume the risk is gone.

For new code:

```java
private static final DateTimeFormatter SHARED =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
```

can be safely shared across threads. Still, pass an explicit `Locale` whenever rules involve language-based text to avoid environment dependence.

## 10. A Formatter's Thread Safety Does Not Automatically Extend to Everything Around It

### 10.1. Input data and output values

`LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, and `ZonedDateTime` are immutable types in `java.time`, ideal for sharing values. However, `TemporalAccessor` is an **interface**, and an application can supply custom implementations; do not blindly assume every custom implementation is thread-safe.

If a request uses external mutable objects or calls other non-thread-safe APIs, a thread-safe formatter **cannot fix** that issue on its own. For example, a `HashMap` cache modified concurrently by multiple threads still needs proper concurrency control even if the map's values are `DateTimeFormatter` instances.

### 10.2. Per-request configuration

A shared formatter can only be reused for identical rules. Different users may require:

- Locales `vi-VN` and `de-DE`.
- Zones `Asia/Ho_Chi_Minh` and `Europe/Berlin`.
- Short or long display styles.
- Different chronologies or decimal styles.

Instead of mutating one shared formatter (which cannot be mutated directly), derive a variant using `with...`:

```java
DateTimeFormatter requestFormatter = BASE_FORMATTER
        .withLocale(userLocale)
        .withZone(userZone);

String text = requestFormatter.format(instant);
```

The code above is just a **snippet**, assuming `BASE_FORMATTER`, `userLocale`, `userZone`, and `instant` are already defined. Each request receives the right logical configuration without affecting formatters used by other requests.

### 10.3. Time zones, locales, and system data updates

A formatter is immutable, yet results can still depend on **regional data** (CLDR and locale providers), **time-zone rules** from the timezone database, JDK version, chronology, and `TemporalAccessor` source. Thus month names, localized formats, or historical offsets can change across runtime updates. Immutability is a property of **an object within one running process**, not a guarantee of identical output strings across every Java release.

### 10.4. Synchronizing around a formatter does not replace domain concurrency control

Wrapping every formatter call in `synchronized` just because the formatter is shared introduces unnecessary contention. Conversely, if formatting is part of an operation updating shared state, synchronization for **domain state** must still be designed separately. Never omit locks on other mutable data simply because the formatter is thread-safe.

## 11. Designing a Formatter Cache: Correct, Necessary, and Sufficient

Creating a formatter can involve parsing a pattern, building internal structures, and storing configuration. For frequently used patterns, reuse makes sense:

```java
public final class DateFormats {
    public static final DateTimeFormatter API_DATE =
            DateTimeFormatter.ISO_LOCAL_DATE;

    public static final DateTimeFormatter UI_DATE =
            DateTimeFormatter.ofPattern(
                    "dd/MM/uuuu", Locale.US);

    private DateFormats() {
    }
}
```

This is a **utility component** (with no `main`), usable by other classes. Constants such as `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_INSTANT`, and `ISO_OFFSET_DATE_TIME` are already provided by Java and reusable, especially for standardized machine-to-machine data.

If the set of patterns/locales/zones is bounded, you can pre-build fixed formatters per configuration. If a dynamic cache is needed, the cache key must include **every configuration dimension affecting semantics** (pattern, locale, zone, resolver style, chronology, decimal style, etc.), and the cache structure must be thread-safe, such as a `ConcurrentHashMap` with a size-bounding policy.

Do not build an unbounded cache keyed on arbitrary user-entered patterns, as that can grow memory usage indefinitely. Nor should you use a cache key containing only locale if patterns or zones vary.

**When is creating a formatter per request still acceptable?** When traffic is modest, configurations vary widely, or simplicity is preferred, creating a new formatter per request is still functionally correct. Thread safety permits safe sharing; it does **not require** every application to maintain a global cache.

## 12. When to Use `ofLocalizedDate` vs. Fixed Patterns

`DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)` or `ofLocalizedDateTime(FormatStyle.MEDIUM)` expresses the intent to **format for human readers per locale conventions**. Combine with `withLocale` to pick each user's language/region.

```java
DateTimeFormatter localDate =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"));
```

This snippet requires importing `DateTimeFormatter`, `FormatStyle`, and `Locale`. Avoid writing tests expecting a single fixed string across all runtimes if localized date formatting data can vary.

Meanwhile, protocol data such as `2026-10-28` should follow standard UI-independent rules:

```java
String wire = DateTimeFormatter.ISO_LOCAL_DATE
        .format(LocalDate.of(2026, 10, 28));
```

The result is `2026-10-28` (requiring imports for `LocalDate` and `DateTimeFormatter`). Never use `Locale.getDefault()` to alter machine-to-machine dates based on the host machine's language.

Immutability and thread safety do not mean all formatters are interchangeable: a formatter built for `LocalDate` does not necessarily have enough fields to format an `Instant` without a zone; an ISO date formatter does not automatically include time and offset.

## 13. Thread-Safe Parsing Does Not Guarantee Parsing Always Succeeds

`DateTimeFormatter` is thread-safe for both **formatting** and **parsing**, yet a string violating the pattern can still throw `DateTimeParseException`.

Example:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate good =
        LocalDate.parse("2026-02-28", formatter);
```

With `2026-02-30`, strict parsing must fail. In web applications, handle errors in the context of the input, recording the active locale and pattern rather than returning raw exceptions to users.

Some data sources include whitespace, special Unicode characters, or malformed date/time strings. Do not equate "multiple threads parsing concurrently will not corrupt the formatter" with "the parser accepts every input". For semantic checks, enforce an explicit contract over year, month, day, time zone, precision, and `Temporal` type.

Furthermore, time sources like `Clock.systemDefaultZone()` depend on the environment. In tests, inject `Clock.fixed(...)` or use fixed date/time values so tests do not fail simply because wall-clock time advances.

## 14. Common Mistakes

| Mistake | What actually happens | Fix |
| --- | --- | --- |
| Calling `base.withLocale(locale)` and discarding the return value | `base` does not change configuration | Assign the new variant or use the return value directly |
| Thinking `withZone` changes the system time zone | Only configures the returned formatter's zone override | Pass explicit `ZoneId` per request |
| Sharing `SimpleDateFormat` in a `static final` field | Reference is final, yet formatter remains mutable and non-thread-safe | Use `DateTimeFormatter` or protect legacy APIs |
| Sharing one `DateTimeFormatterBuilder` and calling `append...` concurrently | Builder is mutable and lacks formatter thread-safety guarantees | Build on one thread, call `toFormatter`, then share the formatter |
| Giving every request one formatter with a fixed locale | Wrong language for users even without a race | Use `withLocale` variants per request |
| Changing only locale when Vietnam time is needed | Locale does not determine time zone | Select `ZoneId` independently |
| Using `LocalDateTime` as an `Instant` | Lacks zone/offset to identify an instant | Convert meaningfully using the right zone |
| Assuming immutability means every `with...` always returns a different object | API may reuse an instance when configuration matches | Test behavior, not object identity |
| Assuming `STRICT` is the default for every `ofPattern` | Default resolver is typically `SMART` | Explicitly call `withResolverStyle(STRICT)` when needed |
| Using `yyyy` with strict parsing without understanding era | `yyyy` is year-of-era, not identical to `uuuu` | Pick the appropriate year field and test edge cases |
| Keying a cache solely on locale name | May wrongly reuse mismatched pattern/zone/resolver | Cache keys must capture the full configuration |
| Assuming a new JDK always returns identical month names to an older JDK | Locale/tzdb data can change by version | Test on the target runtime |
| Printing directly from worker threads and asserting fixed line order | Thread scheduling order is non-deterministic | Collect results via `Future` or sort by ID before asserting |

## 15. Recommended Test Suite

A shared date/time formatting library used across an application should at minimum test:

1. **Immutability:** call `withLocale`, `withZone`, and `withResolverStyle`, then format again with the original formatter to confirm the old configuration still holds.
2. **Multithreading:** multiple tasks share one formatter to format/parse fixed dates, verifying accurate results and no unintended shared mutable state.
3. **Locales:** test at least all product-supported locales; month/weekday names, numbering style, and localized patterns must meet user expectations.
4. **Zones:** the same `Instant` across multiple `ZoneId`s produces matching times/offsets; test transitions near midnight as well.
5. **DST:** if supporting regions with daylight saving transitions, test transition moments and nonexistent/ambiguous local times; never assume every day is 24 hours in every region.
6. **Resolver:** nonexistent dates, leap years, month 0/13, end-of-month dates, and trailing characters.
7. **Patterns:** verify `u` vs. `y`, `LocalDate` vs. `Instant`, and fields with/without zone.
8. **Builder:** mutating a builder after `toFormatter` does not affect the published formatter.
9. **Legacy systems:** ensure no mutable `SimpleDateFormat` is shared against its contract.
10. **Runtime:** test on the JDK and tzdb/CLDR versions actually deployed; separate "fixed numeric syntax" tests from snapshots sensitive to locale data.

## 16. Key Takeaways

- **`DateTimeFormatter` is immutable and thread-safe**: a fully configured instance can be reused across many threads for formatting and parsing.
- **`withLocale`, `withZone`, `withResolverStyle`, `withDecimalStyle`, and `withChronology`** **do not mutate the original formatter**; always use the returned formatter.
- **`DateTimeFormatterBuilder` is mutable; the `DateTimeFormatter` it creates is immutable.** Never share a builder being mutated across multiple threads.
- **`SimpleDateFormat` is not thread-safe**; `static final` does not turn a mutable object into an immutable one.
- **Locale, zone, chronology, and resolver are separate configuration dimensions.** Sharing one formatter is valid only when tasks need the exact same configuration; otherwise, derive per-request variants.
- Thread safety is a property of the **formatter**, not a guarantee that input data, caches, business state, locale/tzdb environment, or parsing outcomes are automatically valid.
