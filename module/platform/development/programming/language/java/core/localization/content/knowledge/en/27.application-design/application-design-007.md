# Managing Mutable Formatters and Locale-Based Caches in Java Applications

## 1. The Design Problem: Reusable Formatters Are Not Automatically Safe to Share

Multilingual Java applications often format thousands of numbers, monetary amounts, dates/times, and text strings per second. A tempting idea is to create each formatter once and store it in a `static Map<Locale, Formatter>` for reuse across all requests.

This idea **can fail** for many legacy API formatters:

- `java.text.NumberFormat` and `DecimalFormat` are **mutable** objects and are not safe when used concurrently by multiple threads without proper synchronization.
- `java.text.DateFormat` and `SimpleDateFormat` are also mutable, holding `Calendar`, `TimeZone`, leniency, and pattern state.
- `java.text.MessageFormat`, `ChoiceFormat`, `Collator`, and similar formatting/comparison classes also carry mutable configuration.
- `java.time.format.DateTimeFormatter`, by contrast, is designed to be **immutable and thread-safe**, so it can be shared once created.

Beyond thread safety, **`Locale` is not always sufficient as a cache key**. For the same `Locale.US`, an application may need two decimal places or zero decimal places, two currencies or two time zones, or different date patterns.

This lesson focuses on **designing, managing lifecycles for, and caching formatters by locale and configuration** in Java 17+, including:

1. Why caching a mutable formatter and returning it directly to callers easily causes bugs.
2. Creating formatters per call, caching prototypes and cloning, or using thread-scoped instances.
3. Caching immutable `DateTimeFormatter`s with complete keys.
4. Defining cache keys that capture locale, pattern, rounding, currency, time zone, and other policies.
5. Memory bounds, eviction, consistency after configuration changes, and concurrency testing.

**Short principle:** *Share immutable configuration data; never accidentally share mutable formatter state.*

## 2. Map of Common Formatters

| API | Mutability / thread safety | Management guidance |
|---|---|---|
| `NumberFormat` | Mutable; not thread-safe when shared | Create per request, clone prototype, or scope per thread |
| `DecimalFormat` | Mutable; holds pattern, symbols, rounding, min/max digits | Never return the raw cached reference for callers to mutate |
| `DateFormat` | Mutable; holds `Calendar`/`TimeZone` and parse options | Create/clone per use; prefer `java.time` APIs where possible |
| `SimpleDateFormat` | Mutable, not thread-safe | Never use an unsynchronized shared `static` instance |
| `MessageFormat` | Mutable; holds pattern and subformat objects | Clone or recreate; guard subformats as well |
| `ChoiceFormat` | Mutable | Create/clone per context when changing patterns/limits |
| `Collator` | Mutable; strength/decomposition can change | Clone/create per request; never mutate a comparator in use by a collection |
| `DateTimeFormatter` | Immutable, thread-safe | Safe to cache and share directly |
| `DateTimeFormatterBuilder` | Stateful builder while constructing a formatter | Do not share a builder being mutated; cache the `toFormatter(...)` result |
| `DecimalFormatSymbols`, `DateFormatSymbols` | Symbols/names can be mutated | Do not treat mutable config objects as stable keys |

In real designs, a formatter may also hold or reference mutable sub-objects such as `Calendar` or child `Format` instances. **Do not look only at the outer class name** and overlook the objects it delegates to.

A `Locale` describes a language/region. It does not automatically encode every formatter setting, such as `RoundingMode.HALF_UP`, currency `EUR`, pattern `dd/MM/uuuu`, `ZoneId.of("Asia/Ho_Chi_Minh")`, or `ResolverStyle.STRICT`.

## 3. Seeing the Bug Immediately with a Shared Mutable Cache

The following example is simple yet **must not be used in production**:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class UnsafeSharedFormat {
    private static final NumberFormat SHARED =
            NumberFormat.getNumberInstance(Locale.US);

    public static String format(double value) {
        SHARED.setMaximumFractionDigits(0);
        return SHARED.format(value);
    }
}
```

Problems:

- `SHARED` is a formatter whose configuration can be mutated.
- Another call site might want two fractional digits and call `setMaximumFractionDigits(2)`.
- When two requests run concurrently, configuration can be altered **before one request finishes formatting**.
- Even without concurrency, changing configuration in an earlier request can leave unexpected state for a subsequent request.
- `NumberFormat` itself does not guarantee safety for concurrent format/parse calls on the same instance.

This cannot be fixed completely just by using `ConcurrentHashMap<Locale, NumberFormat>`. The map may be thread-safe for **get/put**, yet **the cached formatter inside remains mutable**.

This highlights two independent layers of safety:

1. **Cache structure safety:** multiple threads can get/put without corrupting the map's internal structure.
2. **Cached value safety:** multiple threads can use the formatter without state conflicts.

`ConcurrentHashMap` solves the first layer; it **does not make `DecimalFormat` thread-safe**.

## 4. A Cached Mutable Formatter Can Fail Even Without Concurrency

Consider two sequential requests:

```java
DecimalFormat shared = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

shared.setMaximumFractionDigits(0);
String first = shared.format(1234.5);

shared.setMaximumFractionDigits(2);
String second = shared.format(1234.5);
```

There is no concurrency here. Yet if caller A lowers `maximumFractionDigits` and forgets to reset it, caller B retrieving the same instance from the cache inherits A's setting. Therefore, assuming "there's no race because requests run one at a time" is **still insufficient**.

Moreover, `NumberFormat` setters interact: raising minimum past maximum can automatically bump maximum upward. Do not write code assuming a setter touches only one isolated field.

### Java 17+ Example Verifying `clone` Isolation

Save `MutableFormatterDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class MutableFormatterDemo {
    public static void main(String[] args) {
        DecimalFormat prototype = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        prototype.setRoundingMode(RoundingMode.HALF_EVEN);

        DecimalFormat copy =
                (DecimalFormat) prototype.clone();
        copy.setMaximumFractionDigits(0);

        BigDecimal value = new BigDecimal("1234.50");

        System.out.println(
                "prototype=" + prototype.format(value));
        System.out.println("clone=" + copy.format(value));
        System.out.println(
                "prototypeAgain=" + prototype.format(value));
    }
}
```

Run:

```bash
javac MutableFormatterDemo.java
java MutableFormatterDemo
```

Verified JDK output:

```text
prototype=1,234.50
clone=1,234
prototypeAgain=1,234.50
```

`copy` has its own configuration. Changing the clone's maximum does not mutate the prototype. That is an essential property for building a **prototype cache**: store a template and **return a clone per use**, never the prototype itself.

**Note:** `clone()` on any specific API must be understood according to that class's contract. For the JDK's `DecimalFormat` and `DateFormat`, clones are designed to carry independent configuration/subformat objects for this purpose. Do not generalize this conclusion to arbitrary custom classes simply because they implement `clone()`.

## 5. Simplest Option: Create a New Formatter Each Time

If you have no evidence that formatter instantiation is a meaningful bottleneck, the clearest and most controllable option is creating an instance within the processing scope:

```java
static String formatAmount(
        BigDecimal amount,
        Locale locale) {

    DecimalFormat formatter = new DecimalFormat(
            "#,##0.00",
            DecimalFormatSymbols.getInstance(locale));
    formatter.setRoundingMode(RoundingMode.HALF_UP);
    return formatter.format(amount);
}
```

This is a **code fragment** requiring imports for `BigDecimal`, `Locale`, `DecimalFormat`, `DecimalFormatSymbols`, and `RoundingMode`.

Benefits:

- No mutable formatter is shared across requests.
- Every instance receives the exact current locale and configuration.
- No cache eviction or invalidation mechanism is needed.
- Simple to test and no memory accumulates across many users.

Trade-off: creating formatters involves pattern parsing and locale data lookup, which has a cost at very high call rates. Still, **do not add caching based on intuition alone**. Benchmark with a realistic workload—including GC and concurrency—before adopting a more complex structure.

If an application formats several values within a single request, creating one instance for that request and reusing it sequentially is reasonable: **reusing within one thread/request** is very different from **sharing globally across threads**.

## 6. Cache a Prototype, Then Clone: A Design for `DecimalFormat`

When formatter construction genuinely matters and the configuration set is bounded, you can cache **configured prototypes**. Each caller receives a fresh clone.

A Java 17 example using a `record` as key and `ConcurrentHashMap` to construct prototypes safely when multiple threads request the same key concurrently.

### Complete Java 17+ Program

Save `DecimalFormatCacheDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class DecimalFormatCacheDemo {
    record Key(
            Locale locale,
            String pattern,
            RoundingMode rounding) {}

    private static final ConcurrentMap<Key, DecimalFormat> PROTOTYPES =
            new ConcurrentHashMap<>();

    private static DecimalFormat fresh(Key key) {
        DecimalFormat template =
                PROTOTYPES.computeIfAbsent(key, k -> {
                    DecimalFormat f = new DecimalFormat(
                            k.pattern(),
                            DecimalFormatSymbols.getInstance(k.locale()));
                    f.setRoundingMode(k.rounding());
                    return f;
                });

        return (DecimalFormat) template.clone();
    }

    public static void main(String[] args) {
        Key us = new Key(
                Locale.US, "#,##0.00", RoundingMode.HALF_UP);
        Key de = new Key(
                Locale.GERMANY, "#,##0.00", RoundingMode.HALF_UP);

        DecimalFormat a = fresh(us);
        DecimalFormat b = fresh(us);
        DecimalFormat c = fresh(de);

        a.setMaximumFractionDigits(0);

        BigDecimal value = new BigDecimal("1234.50");

        System.out.println("changed=" + a.format(value));
        System.out.println("unchanged=" + b.format(value));
        System.out.println("germany=" + c.format(value));
        System.out.println("keys=" + PROTOTYPES.size());
    }
}
```

Compile and run:

```bash
javac DecimalFormatCacheDemo.java
java DecimalFormatCacheDemo
```

Verified output:

```text
changed=1,235
unchanged=1,234.50
germany=1.234,50
keys=2
```

Explanation:

- `Key` holds `Locale`, pattern, and rounding mode. Both US instances share one prototype; German uses another.
- `computeIfAbsent` constructs and publishes the prototype per key in the concurrent map, avoiding raw get–create–put races in caller code.
- `fresh(key)` **returns a clone**; `a` and `b` are distinct objects. Calling `a.setMaximumFractionDigits(0)` does not affect `b`.
- `PROTOTYPES.size() == 2` because there are two distinct keys.
- Prototypes are **never mutated after insertion into the cache**, an essential invariant of this design.

However, this approach **does not bound the key count automatically**: if callers supply arbitrary patterns or thousands of combinations, the map will grow. Restrict allowed configurations or use a cache with appropriate eviction, expiration, or quotas.

### Why Never Return the Prototype Directly

Wrong:

```java
return PROTOTYPES.computeIfAbsent(key, this::createFormatter);
```

This is a **bad snippet**, not a standalone program. Returning the original formatter lets all callers mutate and format on the same instance. A thread-safe map does not prevent that.

Correct for prototype design:

```java
DecimalFormat prototype = PROTOTYPES.get(key);
return (DecimalFormat) prototype.clone();
```

Use this only when the prototype has already been constructed, is non-null, and is **never mutated** after publication. In actual code, `fresh(...)` above handles both initialization and cloning.

### Is `clone` Always Faster Than `new`?

There is no universal guarantee. Cloning may skip some setup work, yet it still allocates a new instance and pays copying overhead. Benchmark with your actual configurations, locales, JDK version, and workload. If constructing a fresh formatter is cheap enough, the simpler option is often preferable.

## 7. Cache Keys Must Fully Describe Formatting Behavior

A map keyed solely by `Locale` is usually insufficient:

```java
Map<Locale, DecimalFormat> byLocale;
```

Even within `Locale.US`, you might have:

- Patterns `#,##0.00` and `0.###`.
- `RoundingMode.HALF_UP` and `HALF_EVEN`.
- Different minimum/maximum fraction digits.
- Currencies `USD` and `EUR` with different symbols/precision.
- Grouping enabled vs. disabled.
- Parsing modes `setParseBigDecimal(true)` vs. `setParseIntegerOnly(true)`.
- Custom `DecimalFormatSymbols`.
- Application-set prefixes/suffixes.
- Special rules for percentages, negatives, `NaN`, infinity, and signs.

If two formatters share a locale yet differ in **output or parsing behavior**, they must have distinct keys or must not share a cached entry.

An illustrative key record:

```java
record NumberKey(
        Locale locale,
        String pattern,
        RoundingMode roundingMode,
        boolean grouping,
        int minimumFraction,
        int maximumFraction,
        String currencyCode) {}
```

This is an illustrative model, not a complete cache implementation. Enforce consistency—such as `minimumFraction <= maximumFraction`, valid currency codes, allowed patterns/locales, and setter application order—so identical keys always produce identical formatters.

**Never use mutable `DecimalFormat` or `DecimalFormatSymbols` objects as keys** if they could be modified after insertion. Keys in `HashMap` / `ConcurrentHashMap` must have stable `equals()`/`hashCode()` while in the map. Components like `String`, `Locale`, `RoundingMode`, enums, and primitives make solid key fields.

## 8. Configuration Application Order Is Also Part of the Contract

`DecimalFormat` has setters whose order affects the final result:

```java
DecimalFormat f = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

f.setMaximumFractionDigits(0);
f.setMinimumFractionDigits(3);
```

After the final call, the formatter can automatically raise `maximumFractionDigits` so minimum never exceeds maximum. Therefore, when building a prototype from a key:

1. Initialize the pattern and symbols for the locale.
2. Set currency/grouping and other options.
3. Set max/min digits in a well-defined order.
4. Set rounding mode and parsing policy.
5. Read back key getters in unit tests to verify the final configuration.

Do not call `applyPattern(...)` **last** after setters have already configured min/max digits you intend to keep: `applyPattern` can reset bounds based on the new pattern.

When caching, a key is trustworthy only if the factory is **a pure function of the key and immutable configuration policy**. If the factory silently reads `Locale.getDefault()`, the server's default time zone, or mutable global config, the same key can produce two different formatters.

## 9. `DateFormat`/`SimpleDateFormat`: Greater Risk Due to `Calendar`

`java.text.DateFormat` and `SimpleDateFormat` hold date/time formatting state and typically mutate an internal `Calendar` during format/parse calls. Invoking a single `SimpleDateFormat` across multiple threads can throw exceptions, return wrong results, or behave unpredictably under concurrency.

**Unsafe** example:

```java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
```

Beyond thread safety, `SimpleDateFormat` can pick up the default time zone or be mutated by callers via:

```java
SHARED.setTimeZone(TimeZone.getTimeZone("UTC"));
SHARED.applyPattern("dd/MM/yyyy");
SHARED.setLenient(false);
```

These are illustrative fragments, not a complete program. If this formatter is cached under a locale-only key, a caller can accidentally apply **the previous request's time zone or pattern** to the next request.

### If You Must Use `DateFormat`

Options:

- Create a fresh instance per request / operation.
- Cache prototypes keyed by `Locale + pattern + timezone + leniency` and `clone()` per use.
- Use a thread-local instance **only when the entire configuration is fixed per key/thread and lifecycle is managed properly**.
- Synchronize all access to a mutable instance (can be correct, though it adds contention and prevents callers from changing settings outside the lock).

In new code unconstrained by legacy APIs, **prefer `java.time` + `DateTimeFormatter`**: it greatly reduces mutable-state management.

### Cloning `DateFormat` Must Account for Time Zone Policy

An example runnable inside a method with imports:

```java
SimpleDateFormat prototype =
        new SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.US);
prototype.setTimeZone(TimeZone.getTimeZone("UTC"));
prototype.setLenient(false);

SimpleDateFormat copy =
        (SimpleDateFormat) prototype.clone();

copy.setTimeZone(
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
```

If `copy` is used for a local request, never mutate the prototype or a clone currently in use by another request. When two formatters have different time zones, **never cache them under the same `Locale.US`-only key**.

### Caution When Parsing

`DateFormat` also has `setLenient`. If one request expects strict-ish parsing and another expects lenient parsing, that is a major behavioral difference. Furthermore, `setLenient(false)` on legacy parsers **is no substitute for checking trailing characters** with `ParsePosition`. A parser cache requires keys and tests covering parsing mode, pattern, and full-input consumption.

## 10. `DateTimeFormatter`: Immutable and Directly Shareable

`java.time.format.DateTimeFormatter` is designed to be **immutable and thread-safe**, so once created it can be shared across multiple threads without cloning or synchronization for format/parse operations.

Example:

```java
import java.time.format.DateTimeFormatter;

public final class Dates {
    public static final DateTimeFormatter ISO_DAY =
            DateTimeFormatter.ISO_LOCAL_DATE;
}
```

Use the same formatter for many dates:

```java
String text = Dates.ISO_DAY.format(
        java.time.LocalDate.of(2024, 3, 1));
```

The result is `2024-03-01` and the formatter is never mutated. Methods like `withLocale(...)`, `withZone(...)`, `withResolverStyle(...)`, and `withDecimalStyle(...)` return a configured formatter **without modifying the original**.

Example:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.US);

DateTimeFormatter vietnam =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter utc =
        base.withZone(ZoneOffset.UTC);
```

`base`, `vietnam`, and `utc` can all be shared safely once configured. When formatting an `Instant`, `vietnam` and `utc` produce different local times.

**Note:** immutability here applies to the **formatter instance**, not to all input objects or current time. `java.time` also has a mutable `DateTimeFormatterBuilder`: use the builder only during construction, and share only the resulting `toFormatter(...)` object.

## 11. Caching `DateTimeFormatter` with Keys Containing Locale, Pattern, and Zone

With multiple patterns/locales/zones, caching immutable `DateTimeFormatter`s is natural:

```java
ConcurrentHashMap<DateKey, DateTimeFormatter>
```

Because the formatter is immutable, the cache may **return the cached instance directly** to callers. No cloning is needed.

### Complete Java 17+ Program

Save `DateTimeFormatterCacheDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class DateTimeFormatterCacheDemo {
    record Key(
            Locale locale,
            String pattern,
            ZoneId zone) {}

    private static final ConcurrentMap<Key, DateTimeFormatter> CACHE =
            new ConcurrentHashMap<>();

    private static DateTimeFormatter get(Key key) {
        return CACHE.computeIfAbsent(key, k ->
                DateTimeFormatter.ofPattern(
                        k.pattern(), k.locale())
                        .withZone(k.zone()));
    }

    public static void main(String[] args) {
        Instant timestamp =
                Instant.parse("2024-03-01T00:00:00Z");

        Key local = new Key(
                Locale.US,
                "dd/MM/uuuu HH:mm",
                ZoneId.of("Asia/Ho_Chi_Minh"));

        Key utc = new Key(
                Locale.US,
                "dd/MM/uuuu HH:mm",
                ZoneOffset.UTC);

        System.out.println(
                "local=" + get(local).format(timestamp));
        System.out.println(
                "utc=" + get(utc).format(timestamp));
        System.out.println(
                "sameObj=" + (get(local) == get(local)));
        System.out.println("cacheSize=" + CACHE.size());
    }
}
```

Compile and run:

```bash
javac DateTimeFormatterCacheDemo.java
java DateTimeFormatterCacheDemo
```

Verified output:

```text
local=01/03/2024 07:00
utc=01/03/2024 00:00
sameObj=true
cacheSize=2
```

What this demonstrates:

1. `Key` carries `Locale`, pattern, and `ZoneId`.
2. `computeIfAbsent` creates one immutable formatter per key and publishes it via the concurrent map.
3. Two different zones yield **two keys** and two local time results.
4. Repeated calls with the same key return the exact same cached instance (`sameObj=true`).
5. No caller can mutate the cached instance's configuration. For another configuration, derive a new formatter via `withZone`/`withLocale` or use a different key.

This example uses an **unbounded cache**, which is fine for illustration but insufficient for production systems with dynamic zones, patterns, or locales.

## 12. `DateTimeFormatter` Cache Keys May Need Even More Fields

`Locale + pattern + ZoneId` is a starting point, **not a formula covering every formatter**. Other options affect output:

- `ResolverStyle`: `STRICT`, `SMART`, `LENIENT` when parsing.
- `Chronology`: e.g., ISO calendar vs. `JapaneseChronology` or `ThaiBuddhistChronology`.
- `DecimalStyle`: minus sign, decimal separator, and digits for locale/numbering system.
- `DateTimeFormatterBuilder` settings such as optional sections, case-insensitive parsing, strict/lenient parsing, and defaulting fields.
- Pattern style, localized style (`SHORT`/`MEDIUM`/`LONG`/`FULL`), and whether a zone override is applied.
- Version of the pattern policy or application configuration.

If an application builds a formatter with `withResolverStyle(STRICT)` for input parsing, yet the cache key only records `Locale + pattern` and returns a `SMART` formatter, that is **a functional bug**, not merely a suboptimal optimization.

A more complete key might be:

```java
record DateKey(
        Locale locale,
        String pattern,
        ZoneId zone,
        ResolverStyle resolverStyle,
        Chronology chronology) {}
```

This is an **illustrative model** requiring imports for `java.time.format.ResolverStyle` and `java.time.chrono.Chronology`. If the app uses multiple `DecimalStyle`s or builder flags, store those in the key too or split into separate caches by function.

You do not always have to cram every attribute into one record. A cleaner approach is defining **a separate factory/formatter per use case**, with keys holding only the parameters that actually vary. What matters is that two distinct configurations **never alias to the same entry**.

## 13. `ThreadLocal`: Useful in the Right Place, Not a Magical Cache

`ThreadLocal<T>` gives each thread its own instance. For legacy `SimpleDateFormat`, for example:

```java
private static final ThreadLocal<SimpleDateFormat> UTC_FORMAT =
        ThreadLocal.withInitial(() -> {
            SimpleDateFormat f =
                    new SimpleDateFormat(
                            "yyyy-MM-dd'T'HH:mm:ss",
                            Locale.US);
            f.setTimeZone(TimeZone.getTimeZone("UTC"));
            f.setLenient(false);
            return f;
        });
```

This snippet requires importing `SimpleDateFormat`, `ThreadLocal`, `Locale`, and `TimeZone`. Each thread gets its own formatter when calling `UTC_FORMAT.get()`.

It solves **concurrent access by multiple threads to the same instance**, subject to conditions:

- The formatter in this example must always keep **the exact same pattern/locale/zone**; never mutate it per request and leave the thread to serve another request.
- Thread pools reuse threads across requests, so leftover data or settings can affect the next request.
- A `ThreadLocal` tied to dynamic configuration fields does not automatically become a per-locale cache. If a thread handles US and then DE, the formatter does not switch locales on its own.
- Thread-local values can retain objects long-term in thread pools. Manage lifecycle and call `remove()` when appropriate, especially if holding sensitive data or request context.
- With Java virtual threads or very large thread counts, holding one formatter **per thread** may be uneconomical; measure memory and workload.

### Mistake: `ThreadLocal` Mutated with Per-Request Locale

Design flaw example:

```java
SimpleDateFormat f = UTC_FORMAT.get();
f.applyPattern(requestPattern);
f.setTimeZone(requestZone);
String text = f.format(date);
```

Without full restoration, the next request on that thread receives the previous request's pattern/zone. `ThreadLocal` **does not prevent leakage across sequential requests sharing a pooled thread**.

Better options for dynamic patterns/locales/zones:

- Create a new formatter per request.
- Cache prototypes by complete key and clone.
- Or prefer immutable `DateTimeFormatter`.

A fixed `ThreadLocal` for one invariant configuration can make sense; a `ThreadLocal` mutated arbitrarily per request is hard to verify.

## 14. Synchronizing a Shared Formatter: Correct Only If Scoped Completely

Synchronization can protect a mutable formatter:

```java
synchronized (sharedFormatter) {
    String result = sharedFormatter.format(value);
    // Use result here.
}
```

However, if configuration must change, **the entire sequence of configuring + formatting/parsing** must sit inside the exact same lock. If thread A sets the time zone outside the lock, thread B can format right before A enters `synchronized`.

Risks:

- **Contention:** multiple threads wait on the same formatter.
- **Mismatched locking scope:** other code accesses the object without holding the same lock.
- **Keying without locale:** if multiple locales share one formatter, synchronization alone does not guarantee the right settings.
- **Integration leaks:** the formatter escapes, allowing callers to invoke it outside the lock.

Thus, synchronizing a shared formatter **can be safe if every access is strictly controlled**, but it is rarely the best design for high-concurrency web servers. Creating fresh instances, cloning prototypes, or using immutable formatters avoids sharing mutable state altogether.

## 15. `MessageFormat` and `Collator` Follow the Same Principles

### `MessageFormat`

`MessageFormat` has a mutable pattern, locale, and child subformats. Even for the same item-count pattern, an application may call `setLocale`, `applyPattern`, or customize subformats. If requests share and mutate one instance, results bleed into each other.

Create per locale:

```java
MessageFormat message =
        new MessageFormat(
                "You have {0,number,integer} items.",
                Locale.US);

String result = message.format(new Object[]{1234});
```

This snippet requires importing `MessageFormat` and `Locale`. For localized messages, load patterns from a resource bundle and include **locale + message key + pattern/version + format configuration** in the cache key if you genuinely need caching. Never treat message key alone as sufficient when translations can change.

When cloning, ensure subformats and formatting state are not shared/mutated by callers in ways that violate the contract. Never cache a `MessageFormat` and hand it directly to code free to call `applyPattern(...)`.

### `Collator`

`Collator` has `setStrength` and `setDecomposition`; comparison results depend on both. Caching by locale alone when one request uses `PRIMARY` for flexible search and another uses `TERTIARY` for sorting produces wrong results.

Snippet example:

```java
Collator prototype = Collator.getInstance(Locale.FRENCH);
prototype.setStrength(Collator.TERTIARY);

Collator perRequest = (Collator) prototype.clone();
perRequest.setStrength(Collator.PRIMARY);
```

The clone can be mutated without affecting the prototype. For `TreeMap`/`TreeSet`, **never mutate a comparator while a collection is using it**, even within the same thread: the ordering relation changes while the tree structure is not rebuilt.

## 16. Should `ResourceBundle` Be Cached Like Formatters?

`ResourceBundle` serves **translation lookup**, unlike number/date formatters. `ResourceBundle.getBundle(...)` has built-in internal caching and locale fallback. Managing resource bundles requires distinguishing:

- Whether a UI translation file like `messages_vi.properties` actually exists.
- The requested locale vs. the actual locale of the resolved bundle.
- Reload policies and `ResourceBundle.Control` (noting its restrictions in named modules).
- ClassLoader/module lifecycles and translation data versions.

Do not build a custom `ConcurrentHashMap<Locale, ResourceBundle>` merely because you are caching `DecimalFormat`. `ResourceBundle`'s built-in cache is often sufficient; if hot-reloading translations is needed, establish a clear reload policy instead of holding old references forever.

**Specifically:** changing a formatter's locale does not automatically switch UI translations. Conversely, having `messages_vi.properties` does not guarantee `NumberFormat` is using the right JDK locale data. The two configuration streams must be managed independently.

## 17. Rules for Choosing Cache Keys by Function

Describe each formatting category's requirements before designing keys:

| Function | Configuration dimensions likely needed in key |
|---|---|
| Decimal numbers | Locale, pattern, rounding, min/max digits, grouping, symbols |
| Currency | Display locale, currency, fraction digits, rounding, pattern |
| Percentages | Locale, pattern/scale, rounding, min/max digits |
| Legacy date/time | Locale, pattern, `TimeZone`, leniency, chronology/calendar |
| `java.time` date/time | Locale, pattern/style, zone, chronology, resolver, decimal style |
| `MessageFormat` messages | Locale, message key, pattern/version, custom formats |
| Collation | Locale, strength, decomposition, rule/version/provider |
| Input parsing | Locale, pattern, leniency, full-consumption policy, numeric type |

A cache key is a **configuration-equivalence contract**: two requests may share an entry only when the factory produces behavior valid for both. If a key omits a dimension, bugs can occur even without concurrency.

Another strategy is splitting caches into fixed use cases: `NUMBER_TWO_DECIMALS`, `NUMBER_INTEGER`, `CURRENCY_DISPLAY`, `SHORT_DATE`. Locale then becomes the sole varying dimension inside **each specialized cache** — provided the policies for those use cases do not silently drift.

## 18. Designing a User-Context Formatter Factory

Instead of scattering `Locale.getDefault()` and formatter caches everywhere, gather input settings into one class/record:

```java
record FormattingContext(
        Locale locale,
        ZoneId zone,
        Currency currency,
        RoundingMode rounding) {}
```

This snippet requires importing `Locale`, `ZoneId`, `Currency`, and `RoundingMode`.

Each request resolves `FormattingContext` from a validated profile, tenant, language header, or business policy. Factories then construct formatters matching that context:

```text
HTTP request / user settings
           |
           v
FormattingContext (locale, zone, currency, rounding)
           |
           +--> immutable date formatter cache
           |
           +--> mutable number formatter factory/clone
           |
           +--> localized messages / ResourceBundle
           |
           v
Response/UI
```

Separate locale from time zone: `vi-VN` describes language/region, yet a Vietnamese speaker may be in Paris; time zone cannot be derived one-to-one from locale. Separate currency from locale: a `EUR` transaction can still be formatted using Vietnamese conventions. Rounding is also a business policy and cannot always be guessed from locale.

**Never write request-context changes into global `Locale.setDefault(...)` or `TimeZone.setDefault(...)`.** They are global state and will affect concurrent requests.

## 19. Watch Out for Unbounded Caches and User-Supplied Keys

`ConcurrentHashMap` retains entries until removed or the map is collected. If keys include client-supplied patterns or locale tags, the key space can grow without bound:

```text
locale=vi-VN, pattern=A
locale=vi-VN, pattern=B
locale=vi-VN, pattern=C
...
```

A buggy or untrusted request can intentionally generate endless distinct patterns, inflating memory and GC pressure. Therefore:

1. **Restrict accepted patterns** to an application-approved set.
2. **Validate locale tags** and constrain to product-supported locales where appropriate.
3. Enforce eviction/maximum-size policies if the combination space is genuinely large.
4. Add timeouts/metrics for costly entry creation.
5. Never place secrets or user-specific data into global caches without clear justification and isolation.
6. Monitor hit ratio, total entry count, formatter construction cost, allocations, and GC.

With only a handful of fixed locales/patterns, a small `Map` can be plenty. With many combinations, a dedicated cache library supporting maximum size and expiry (if the project already has the dependency and clear need) is usually better than hand-rolling synchronized LRU logic from scratch.

**Avoid caching by `Locale.toString()` when using BCP 47 extensions.** Use immutable `Locale` directly or normalized `toLanguageTag()` per policy, ensuring extensions that actually affect output are preserved.

## 20. Invalidating Caches on Config Changes and Data Upgrades

A cache valid at creation time can become **stale** after:

- Editing date/number patterns in deployment configuration.
- Changing rounding or currency policies.
- User switching locale or time zone.
- Reloading translation bundles.
- Upgrading the JDK with updated CLDR/locale data.
- Updating the time-zone database (tzdb) or calendar rules.

Do not key solely by a fixed `Locale` while the factory reads `globalConfig.getPattern()` directly and expect entries to refresh when the pattern changes. Instead:

- Include `pattern/version/configRevision` in the key.
- Tie the cache to configuration lifecycle and **clear/rebuild** on change.
- Create a fresh cache per configuration version.
- Use bounded TTLs where appropriate, while remembering TTL **does not replace** immediate correctness when business rules require it.

Caches built under one JDK should not be serialized as persistent data or used as the basis for persistent identity/sort keys without versioning. For example, locale collation can change across JDK/provider releases; when it does, rebuild indices or run regression tests.

For `ZoneId`, future timestamp calculations depend on the runtime's tzdb; test sensitive DST dates after JDK upgrades. Never assume an immutable cache "auto-updates tzdb data" in a running JVM without an explicit mechanism.

## 21. Cache Keys and Default Data: Avoid Global State Dependencies

Avoid designing factories like this:

```java
DecimalFormat createFormatter() {
    Locale locale = Locale.getDefault();
    return (DecimalFormat)
            NumberFormat.getNumberInstance(locale);
}
```

This is a bare snippet without class/imports for illustration. Its output depends on the JVM's global default locale. If the cache key omits the actual locale or the environment mutates the default locale, later calls may use the wrong entry.

Clearer alternative:

```java
DecimalFormat createFormatter(Locale locale) {
    return new DecimalFormat(
            "#,##0.00",
            DecimalFormatSymbols.getInstance(locale));
}
```

The same applies to time zones: `ZoneId.systemDefault()` should be read once during intentional configuration or passed per request, never sampled implicitly inside a cache factory keyed only by locale.

Good configuration is **deterministic**: the same key and data/runtime version yield identical behavior, making tests simple and caches trustworthy.

## 22. Concurrency Testing: "1,000 Threads Looked Fine" Is Not Enough

Zero errors in one stress-test run **does not prove** `SimpleDateFormat` is thread-safe. Races depend on timing, JIT compilation, CPU cores, and input data.

Tests should cover:

- Two requests with the same locale but different patterns.
- Two requests with the same locale but different rounding modes or min/max digits.
- Two requests with the same pattern but different time zones.
- One request cloning a formatter, mutating settings, and asserting neither prototype nor other clones changed.
- More concurrent requests than worker threads; verify zero state bleed.
- Strict vs. lenient parsers sharing the same locale.
- Cache configuration changes (version/reload) while requests are in flight.
- Locales with non-US decimal marks; never test only `12`, where locale differences are invisible.
- `DateTimeFormatter` formatting an instant near midnight, where different time zones cross into different local dates.
- Memory/metrics under many locale tags.

### Clone Invariant Tests

A valuable invariant example:

```text
prototype.format(1234.50) == "1,234.50"
cloneA.setMaximumFractionDigits(0)
cloneA.format(1234.50) == "1,235"
cloneB.format(1234.50) == "1,234.50"
prototype.format(1234.50) == "1,234.50"
```

Tests should pass `BigDecimal("1234.50")` to avoid binary floating-point representation quirks near rounding boundaries.

### Immutable Cache Invariant Tests

With `DateTimeFormatterCacheDemo`:

```text
local=01/03/2024 07:00
utc=01/03/2024 00:00
sameObj=true
cacheSize=2
```

A correct formatter cache never mixes zones or returns patterns mutated by another request. This test does not even need concurrency to prove **the key includes zone** and the formatter is reused properly.

## 23. Benchmark in the Right Place, Do Not Optimize by Gut Feel

Choose caching based on measurements, not because formatters "feel heavy":

- **Throughput:** operations/sec for per-call creation vs. prototype cloning vs. cached immutable formatters.
- **Latency:** p95/p99 percentiles under realistic multi-threaded load.
- **Allocation:** bytes allocated per formatter creation/clone.
- **GC pressure:** whether collection overhead rises or falls.
- **Cache hit ratio:** percentage of requests hitting the same configuration.
- **Retained memory:** long-lived entry count and child objects.
- **Contention:** whether a synchronized shared instance bottlenecks the pipeline.

For reliable Java benchmarks, use JMH rather than timing a naive loop with `System.nanoTime()` without warmup or JIT controls. Run benchmarks on the exact target JDK version, locale set, and representative workload.

**A cache can actually make a program slower or use more RAM** if keys vary widely, hit rates are low, eviction churns, or entries are complex. Prototype caches still clone per request, so they do not achieve "zero formatter allocation"; they only save part of setup cost.

## 24. Design Guidance by Scenario

| Scenario | Preferred approach |
|---|---|
| A few numbers per request | Create a new `DecimalFormat`; use sequentially within the request |
| Many numbers with identical config in one request | Create one request-scoped formatter; never share outside the request |
| Repeated patterns/locales, costly creation | Cache prototype and `clone()` before use |
| Legacy date formatter required | Create/clone or fixed-config `ThreadLocal`; test thoroughly |
| Dates/times using `java.time` | Cache/share immutable `DateTimeFormatter` |
| `Collator` sorting across locales | Cache rules/prototypes by locale + strength + decomposition; clone if mutating |
| Input carries untrusted patterns | Validate allowlist; avoid unbounded caches |
| Runtime configuration changes | Version keys or rebuild/clear cache |
| High request concurrency | Never return shared mutable formatters unsynchronized |
| Maximum throughput truly needed | Benchmark; consider bounded cache with metrics |

The "safest" option is not necessarily the one with the "fewest objects". The ideal strategy is **eliminating shared mutable state**, then optimizing proven hot paths with data.

## 25. Common Mistakes

1. **"`ConcurrentHashMap` is thread-safe, so `DecimalFormat` inside it is too."** False: map safety and value safety are two separate concerns.
2. **Caching by locale alone when formatters use different patterns.** Produces wrong output within the same language.
3. **Returning a mutable prototype directly.** Callers can mutate settings and break other requests.
4. **Mutating a shared `SimpleDateFormat`'s time zone per request.** Leaks context and causes races.
5. **Using an unsynchronized `static SimpleDateFormat`.** Unsafe under concurrent formatting/parsing.
6. **Assuming `ThreadLocal` resets locale per user.** Thread pools reuse threads; stale settings linger.
7. **Keying caches on unbounded user-supplied patterns/currencies.** Risks unbounded cache growth.
8. **Treating `DateTimeFormatter` as mutable and cloning/synchronizing needlessly.** It is immutable/thread-safe and can be shared directly.
9. **Confusing builder and formatter.** `DateTimeFormatterBuilder` is stateful; only the `toFormatter` result is immutable.
10. **Omitting `ResolverStyle` from date-parsing cache keys.** May silently return a `SMART` parser instead of `STRICT`.
11. **Omitting time zone from date-time cache keys.** Users in different zones get each other's local times.
12. **Assuming locale determines currency and time zone.** Those preferences are independent.
13. **Mutating a `Collator` comparator while a `TreeMap` uses it.** Breaks tree invariants and lookup consistency.
14. **Changing a cached `MessageFormat`'s pattern without versioning.** Produces mismatched translations and output.
15. **Calling `Locale.setDefault` per request.** Mutates global state and corrupts other threads.
16. **Benchmarking on a single thread only.** Misses lock contention and synchronization costs.
17. **Forgetting invalidation on config/JDK/tzdb updates.** Caches retain stale behavior.
18. **Using `new Date()`/`Instant.now()` in fixed tests.** Flaky results and hidden time-zone bugs.
19. **Equating a cache hit with semantic correctness.** A valid cache needs complete keys, proper lifecycle, and zero mutable-state leakage.
20. **Optimizing before verifying localization correctness.** Fast output with the wrong decimal mark or date/time is still a bug.

## 26. Self-Check Questions

**Question 1.** Why is `ConcurrentHashMap<Locale, DecimalFormat>` insufficient for thread-safe formatting across threads?  
**Answer:** The map synchronizes cache operations, but `DecimalFormat` itself is mutable and not thread-safe when shared.

**Question 2.** What is the difference between a prototype cache and a shared-instance cache?  
**Answer:** A prototype cache holds a read-only template and returns `clone()` to callers; a shared-instance cache returns the same mutable object, inviting mutation and races.

**Question 3.** With a `DateTimeFormatter` cache, do you need to clone before each `format()`?  
**Answer:** No. `DateTimeFormatter` is immutable and thread-safe; the cached instance can be returned directly.

**Question 4.** Why does `Locale.US` still require two cache entries for two time zones?  
**Answer:** The same instant in two time zones can correspond to different local hours or calendar dates.

**Question 5.** Does `ThreadLocal<SimpleDateFormat>` automatically prevent request locales from leaking into each other?  
**Answer:** No. Thread pools run multiple requests sequentially on the same thread; if the instance is mutated per request without proper reset, settings leak to subsequent requests.

**Question 6.** What should a cache key contain?  
**Answer:** Every attribute affecting format/parse behavior for that entry: locale, pattern, rounding, time zone, currency, digits, resolver, and any other formatter-specific options.

**Question 7.** How should an app handle thousands of user-supplied patterns?  
**Answer:** Validate against an allowlist, avoid unbounded maps, and use a bounded cache or skip caching rare configurations.

**Question 8.** If a shared `SimpleDateFormat` has all `format` calls inside `synchronized`, while `setTimeZone` sits outside, is it safe?  
**Answer:** No. Every operation reading or mutating state must use the exact same synchronization mechanism.

**Question 9.** Why should tests format numbers like `1234.50` instead of just `12`?  
**Answer:** Numbers with grouping and fractional digits expose locale, pattern, and rounding bugs much more clearly.

**Question 10.** What happens if deployment patterns change while cache keys contain only locale?  
**Answer:** Stale entries may keep getting used; add a version to the key, invalidate the cache, or rebuild for the new config.

## 27. Summary

**Mutable formatters must be isolated or strictly synchronized; immutable formatters can be shared safely.** In Java 17+:

- `NumberFormat`, `DecimalFormat`, `SimpleDateFormat`, `MessageFormat`, and `Collator` should be created per request, cloned from immutable prototypes, or governed by explicit concurrency/lifecycle rules.
- `java.time`'s `DateTimeFormatter` can be cached and shared directly because it is immutable and thread-safe.
- Cache keys must capture **every configuration dimension affecting output**; `Locale` alone is rarely enough.
- Caches need size bounds, invalidation/versioning, and tests when configuration or locale/timezone data changes.
- `ThreadLocal` and synchronization cannot turn an under-keyed cache into a semantically correct design.
- Prioritize **multilingual data correctness**, then measure and optimize proven hot paths.

**Official documentation:** [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [DateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormat.html) · [SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html) · [MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) · [Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) · [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) · [ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html).
