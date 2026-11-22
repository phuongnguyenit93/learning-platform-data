# Impact of Formatter Creation Time and Caching

In Java, when a formatting API **does not receive an explicit `Locale`**, it typically reads the default locale **at the time the formatter object is created**. If the application later changes the default locale, already-created formatters generally **do not update automatically**, whereas newly created formatters may use the new value. Caching makes this behavior easy to misunderstand: old objects continue to be reused even though the current configuration has changed.

This is an important topic under **Default Locale**: you must know **when the locale is selected, who holds the formatter, what the cache is keyed on, and which changes require refreshing the cache**.

> **Practical rule:** Choose the request/user's locale explicitly and pass it into the formatter. Do not use JVM default locale mutation as a way to switch languages per request, and do not cache mutable formatters for concurrent use across threads.

## 1. Distinguishing Four Points in Time

Suppose an application goes through these steps:

1. **T1:** The JVM currently has a default locale of `en-US`.
2. **T2:** The application creates a `NumberFormat` or `DateTimeFormatter` without passing a locale.
3. **T3:** Another part of the code calls `Locale.setDefault(..., Locale.GERMANY)`.
4. **T4:** The application reuses the old formatter or creates a new formatter to display data.

At T4, the two operations can yield different results:

- **Reusing the formatter created at T2:** the object already holds its locale or related rules/settings; changing the default at T3 does not automatically reconfigure that object.
- **Creating a new formatter at T4:** a factory call without a locale can read the new default and thus produce German formatting.

Changing the default **is not a command to “refresh every existing formatter”**. Conversely, if you pass `Locale` at creation time, the behavior does not depend on when the JVM default was set.

| Object or operation | Time when the default takes effect | Notes |
| --- | --- | --- |
| `NumberFormat.getNumberInstance()` | When the factory is called | Creates a formatter using the `FORMAT` default at that moment |
| `NumberFormat.getNumberInstance(locale)` | Does not need to read the default to select the locale | Uses the parameter locale |
| `DateTimeFormatter.ofLocalizedDate(style)` | The default locale is attached when creating the formatter | `getLocale()` observes the formatter's locale |
| `formatter.withLocale(locale)` | When `withLocale` is called | Returns a **new formatter** with the requested locale |
| `new SimpleDateFormat(pattern)` | When the constructor runs | May capture defaults for locale and time zone; mutable object |
| `ResourceBundle.getBundle(baseName)` | When the call selects the default locale | Bundles are cached independently by the `ResourceBundle` mechanism |
| `Locale.getDefault(...)` | Immediately when called | Reads the JVM's current default state; not a formatter |

You should not generalize a single rule for **all libraries**. Standard Java APIs and third-party libraries may make different choices regarding snapshots, lazy loading, caching, fallback, and reconfigurability.

## 2. General Default Locale vs. Category Default Locales

Java provides `Locale.getDefault()` and `Locale.getDefault(Locale.Category)`. Two notable categories:

- `Locale.Category.FORMAT`: default context for formatting services such as numbers and dates/times.
- `Locale.Category.DISPLAY`: default context for display names of locales, countries, and languages.

`Locale.setDefault(Locale)` changes the general default locale and also updates the category default locales according to the API contract. `Locale.setDefault(Locale.Category.FORMAT, locale)` changes only the `FORMAT` category default; doing so does not mean the no-argument `getDefault()` or the `DISPLAY` category will necessarily return the same value.

**Scope warning:** the default locale is **JVM-wide** state, not a local variable for one user or one HTTP request. Changing it while multiple threads are creating formatters can cause one thread to pick up another thread's conventions. The examples below only mutate defaults inside self-contained demo programs and restore defaults using `finally`.

## 3. Runnable Experiment: Old Formatter vs. New Formatter

Create the file **`FormatterCreationTimeDemo.java`**:

~~~java
import java.text.NumberFormat;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormatterCreationTimeDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault(Locale.Category.FORMAT);

        try {
            Locale.setDefault(Locale.Category.FORMAT, Locale.US);

            NumberFormat oldNumber = NumberFormat.getNumberInstance();
            DateTimeFormatter oldDate =
                    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

            NumberFormat newNumber = NumberFormat.getNumberInstance();
            DateTimeFormatter newDate =
                    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

            System.out.println("Old date locale: "
                    + oldDate.getLocale().toLanguageTag());
            System.out.println("New date locale: "
                    + newDate.getLocale().toLanguageTag());

            System.out.println("Old number: " + oldNumber.format(1234.5));
            System.out.println("New number: " + newNumber.format(1234.5));
            System.out.println("Old number again: "
                    + oldNumber.format(1234.5));
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, original);
        }
    }
}
~~~

Compile/run using **Java 17+**:

~~~bash
javac FormatterCreationTimeDemo.java
java FormatterCreationTimeDemo
~~~

On a JDK with standard formatting data for these two locales, the output is:

~~~text
Old date locale: en-US
New date locale: de-DE
Old number: 1,234.5
New number: 1.234,5
Old number again: 1,234.5
~~~

The two `getLocale().toLanguageTag()` lines prove that the old `DateTimeFormatter` object still holds `en-US`, while the new object holds `de-DE`. The numbers illustrate the decimal/grouping separator difference between `Locale.US` and `Locale.GERMANY`. Locale/provider data can vary across JDKs, so when byte-for-byte testing is needed, pin both the runtime and formatting dependencies rather than treating every localized string as a universal immutable contract.

**Accurate interpretation:** Calling `Locale.setDefault` did not "change the contents" of `oldNumber` or `oldDate`. At time T4, `oldNumber` still uses the earlier configuration; `newNumber` obtains a different configuration when created. Calling `format` repeatedly on the same formatter does not necessarily re-read the default locale.

## 4. `DateTimeFormatter`: Immutable, Creating a New Instance When Changing Locale

In the Java Time API (`java.time`), `DateTimeFormatter` is immutable and thread-safe. `withLocale`, `withZone`, `withChronology`, and similar methods return a newly configured formatter without modifying the original formatter.

Example code snippet placed inside a Java method:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");

DateTimeFormatter base =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter forVietnam = base.withLocale(vietnamese);

System.out.println(forVietnam.getLocale().toLanguageTag());
~~~

Requires importing `java.util.Locale`, `java.time.format.DateTimeFormatter`, and `java.time.format.FormatStyle`. Output line:

~~~text
vi-VN
~~~

Even if `base` was created under an `en-US` default, `forVietnam` has locale `vi-VN`. In a multi-user service, a clearer approach is to pass the user's locale at the call layer:

~~~java
String formatDate(java.time.LocalDate date, Locale locale) {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);
    return formatter.format(date);
}
~~~

This is an **illustrative method**, which must be placed inside a class with appropriate imports; it is not a standalone Java program. It does not depend on another thread having just changed the JVM default.

### Two Things Not to Confuse

1. **The formatter's locale** and **the locale data used to interpret localized patterns** are two layers. The formatter holds the locale selection, while the JDK/provider supplies patterns, month names, and symbols. Some implementation details may be looked up or cached as the formatter operates; that does not turn a new default into the old formatter's new locale.
2. **`withLocale` is not a command to translate all strings in the application.** It configures the formatter. UI message translations must come from i18n resources, while time zones, currencies, and calendars may need separate configuration.

## 5. `NumberFormat` and `SimpleDateFormat`: Mutable State

Unlike `DateTimeFormatter`, legacy formatters such as `java.text.NumberFormat`, `DecimalFormat`, and `SimpleDateFormat` have mutable state. They can hold symbols, patterns, fraction digit counts, rounding modes, or time zones depending on the class and configuration.

Example of `NumberFormat` having setters:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
number.setGroupingUsed(false);
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
System.out.println(number.format(1234.5));
~~~

This is a **code snippet inside a method** with `import java.text.NumberFormat;` and `import java.util.Locale;`. Output:

~~~text
1234.50
~~~

Even if the JVM default later switches to `Locale.GERMANY`, the `number` object retains all attributes that were set. Changing the default is not designed to replace setter calls or reconfigure existing objects.

**Thread safety:** `NumberFormat` and `SimpleDateFormat` are not guaranteed to be safe when multiple threads access one instance concurrently. Placing them in a global cache and sharing them can cause data corruption/races even if **every** request uses the same locale. Safe approaches typically include:

- Creating a new instance scoped to a single request/formatting operation.
- Using synchronization when sharing is mandatory, with performance evaluation.
- Caching **immutable configurations or factories**, then creating a dedicated mutable formatter instance when used.
- For dates and times, preferring immutable `DateTimeFormatter`, which can be cached safely.

Do not change `Locale.setDefault` to “fix thread safety” of formatters: those are two completely different issues.

## 6. Caching Makes Time-Dependent Behavior More Pronounced

In a Java application, several different caches may exist:

| Layer | Example | What to watch out for |
| --- | --- | --- |
| **Application-created cache** | `static Map<Locale, DateTimeFormatter>` | Key, creation time, and invalidation policy are owned by the application |
| **Library/framework cache** | Formatter cache, message catalog, compiled templates | Depends on library documentation and configuration |
| **JDK internal service cache** | Locale data/patterns/providers reused by the JDK | No general contract that changing defaults clears all caches |
| **`ResourceBundle` resource cache** | Bundles by base name, locale, class loader/module | Has its own cache/clear API, distinct from formatter caches |
| **Formatted-result cache** | Currency/date strings attached to records | Keys must reflect the locale and formatting parameters |

Separate **two questions**:

1. Is the cache storing a **formatter** or a **result string**?
2. Does the cache key already reflect every piece of information that can change the output?

For example, a `Map<String, String>` caching UI HTML keyed only by product ID could serve a Vietnamese version to an English user. The cache key may need `productId + effectiveLocale + currency + zone + version` depending on the actual content. If only plain numbers are formatted, `ZoneId` is unnecessary; choose exactly the dimensions that affect output and avoid redundant keys.

### Caching Formatters by Locale

Flawed by design:

~~~java
// Anti-pattern example in a multi-user service.
static final NumberFormat SHARED =
        NumberFormat.getNumberInstance();
~~~

The problems include both taking a **snapshot** of the default when the class is initialized and being **mutable / not thread-safe** when multiple requests invoke the same `SHARED` instance. When the default changes, `SHARED` does not become a new formatter for another locale.

Also easy to get wrong:

~~~java
// Cache has only one entry, yet output depends on locale.
static DateTimeFormatter cached =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);
~~~

The `cached` object is immutable and thread-safe, but if used for users from multiple locales without switching the locale, everyone sees the format captured at initialization time. **Thread-safe does not mean user-context-correct.**

Better design: cache **immutable** formatters keyed by explicitly selected locales; also include other affecting options in the key if needed.

## 7. Runnable Example: Properly Caching `DateTimeFormatter` by Locale

Create the file **`LocaleAwareFormatterCache.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class LocaleAwareFormatterCache {
    private static final ConcurrentMap<Locale, DateTimeFormatter> CACHE =
            new ConcurrentHashMap<>();

    public static String format(LocalDate date, Locale locale) {
        DateTimeFormatter formatter = CACHE.computeIfAbsent(
                locale,
                requested -> DateTimeFormatter
                        .ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(requested)
        );
        return formatter.format(date);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 12, 31);
        Locale original = Locale.getDefault(Locale.Category.FORMAT);

        try {
            String first = format(date, Locale.US);

            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

            String second = format(date, Locale.US);
            System.out.println(first.equals(second));
            System.out.println(CACHE.size());
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, original);
        }
    }
}
~~~

~~~bash
javac LocaleAwareFormatterCache.java
java LocaleAwareFormatterCache
~~~

Output:

~~~text
true
1
~~~

Explanation:

- `computeIfAbsent` creates a new formatter only for locales not yet in the map; the key is passed into `withLocale(requested)`.
- Both calls use `Locale.US`, so the result for the same date does not change merely because the JVM's `FORMAT` default switched to Germany.
- The cache has exactly one entry for `Locale.US`. Because the formatter is immutable, that instance can be shared across threads.

**Example limitations:** In a real system, if caching unboundedly by user-supplied locales, you may need to validate whether the locale is supported by the application and bound the cache size. If formatters vary by `FormatStyle`, `ZoneId`, `Chronology`, pattern configuration, or numbering system, a key with only `Locale` is insufficient for all needs.

Do not cache formatters just to avoid writing a single `withLocale` line. Before adding a cache, measure the actual cost; an unbounded cache with an incomplete key can cause more bugs than the performance it saves.

## 8. `ResourceBundle` Has Its Own Cache

`ResourceBundle` is a mechanism for retrieving localized messages, **not a number or date formatter**. It has its own cache.

Suppose the classpath contains:

~~~text
Messages.properties
Messages_en.properties
Messages_vi.properties
~~~

With code:

~~~java
ResourceBundle messages = ResourceBundle.getBundle("Messages");
~~~

The call **without a locale argument** selects the default locale at the moment the call is made (per `ResourceBundle` rules). A retained `messages` object does not automatically switch to a new language bundle just because the default changes afterward.

Conversely:

~~~java
ResourceBundle messages =
        ResourceBundle.getBundle("Messages", requestedLocale);
~~~

The second snippet **passes the locale explicitly** (the variable `requestedLocale` must be declared where used), reducing dependence on the default at call time. However, `ResourceBundle` has its own candidate selection and fallback mechanism; if the requested locale lacks a sufficiently matching bundle, fallback options may include the JVM default locale or the root bundle depending on the case. To guarantee product policy, test the fallback chain and actual resources.

### Does updating translation files automatically update the cache?

Not necessarily. Under the default mechanism, `ResourceBundle` may keep bundles cached. Java provides `ResourceBundle.clearCache()` and `ResourceBundle.clearCache(ClassLoader)`, but calling these methods only affects `ResourceBundle`'s cache per the API contract: it **does not** clear all framework caches or application variables still holding references to old bundles.

If dynamic reloading is needed, you can use `ResourceBundle.Control` (in API contexts that support it), design an explicit TTL/reload policy, or use your framework's catalog mechanism. That choice must be compatible with class loaders/modules and the actual resource deployment setup. **Changing the default locale is not a solution for automatically reloading translations.**

### Example Verifying Bundle Selection at Call Time

Suppose the same directory contains two UTF-8 files:

**`Messages_en.properties`:**

~~~properties
greeting=Hello
~~~

**`Messages_vi.properties`:**

~~~properties
greeting=Xin chào
~~~

File **`BundleCreationTimeDemo.java`**:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleCreationTimeDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault();

        try {
            Locale.setDefault(Locale.ENGLISH);
            ResourceBundle oldBundle =
                    ResourceBundle.getBundle("Messages");

            Locale.setDefault(Locale.forLanguageTag("vi"));
            ResourceBundle newBundle =
                    ResourceBundle.getBundle("Messages");

            System.out.println(oldBundle.getString("greeting"));
            System.out.println(newBundle.getString("greeting"));
            System.out.println(oldBundle.getString("greeting"));
        } finally {
            Locale.setDefault(original);
        }
    }
}
~~~

~~~bash
javac BundleCreationTimeDemo.java
java -cp . BundleCreationTimeDemo
~~~

Output:

~~~text
Hello
Xin chào
Hello
~~~

When the default language changes, the second `getBundle` call can retrieve a different bundle, even though the JDK still uses caching for optimization. The `oldBundle` reference in the program is not replaced. Bundle reloading capability and selection changes following the default are **two different behaviors**.

In a multi-user environment, pass an explicit locale to `getBundle` rather than rotating the JVM-wide default on each request.

## 9. Default Time Zone: Another Source of Time-Dependent Behavior

With dates and times, **locale** governs localization style/patterns, whereas **time zone** governs how an instant on the timeline is interpreted into local time. Changing the default locale does not change the actual instant of an `Instant`, and changing the default time zone is not a language-selection operation.

Legacy date/time APIs like `DateFormat`/`SimpleDateFormat` can capture the default time zone **at initialization**. A long-lived formatter may continue holding its configured time zone even if the JVM default changes later. Thus, the cache key for a formatter or formatted instant output may need `ZoneId` in addition to `Locale`.

With Java Time, convert `Instant` or `ZonedDateTime` using the zone chosen by the user/application and use a `DateTimeFormatter` with an explicit locale:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class ExplicitContextDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2024-01-01T00:00:00Z");
        ZoneId zone = ZoneId.of("Asia/Tokyo");
        Locale locale = Locale.US;

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(locale)
                        .withZone(zone);

        System.out.println(formatter.getLocale().toLanguageTag());
        System.out.println(formatter.getZone().getId());
        System.out.println(instant.atZone(zone).getHour());
    }
}
~~~

~~~bash
javac ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Exact output:

~~~text
en-US
Asia/Tokyo
9
~~~

The code clearly separates three components: the **instant** `Instant`, the **time zone** `ZoneId`, and the **display context** `Locale`. `formatter` in the example has explicit zone and locale settings; subsequent calls to `format(instant)` follow that configuration rather than reading any new JVM default.

## 10. When Must a Cache Be Invalidated?

A cache is only correct when **inputs that can change the result** are reflected in the key and cached data remains valid.

**Case A — Only the JVM default changed; formatters are cached by explicit locale.** If the call and key already contain `Locale.US`, there is no need to clear the cache just because the JVM default switched from `en-US` to `de-DE`. That is precisely the benefit of eliminating implicit dependencies.

**Case B — Formatters created via default are cached without a locale in the key.** This is an error-prone design: after changing the default, you still receive the old formatter. Fix **how formatters are created and keyed**, rather than relying on ad-hoc cache clearing. After fixing the design, remove/rebuild old entries that did not reflect the locale.

**Case C — The user changes their saved locale.** A cache of rendered/HTML/message results per user must use the new effective locale in the key or be invalidated appropriately. Otherwise, stale results may appear even when new formatters are created properly.

**Case D — Translations or application rules are updated.** Message/result caches need versioning or an explicit reload policy. `ResourceBundle.clearCache` only handles the cache managed by `ResourceBundle`.

**Case E — Upgrading the JDK, CLDR/provider libraries, tzdb data, or formatting configuration.** Output quality/appearance can change. Run regression tests and rebuild cached formatted data if the product requires reflecting the new rules. Many internal runtime caches have no public “clear all” API; typically deploying the new runtime version serves as a fresh initialization boundary.

If a cache stores formatted results, a key might include `value`, `locale`, `formatOptions`, `currency`, `zone`, and `catalogVersion` when those factors actually affect the result. If a cache stores `DateTimeFormatter`, the key usually includes locale, style/pattern, and formatter configurations. **There is no single universal cache key suitable for every application.**

## 11. Concurrency, Consistency, and Preventing Context Leaks

Consider a server with two HTTP requests running in parallel:

~~~text
Request A (vi-VN): setDefault(vi-VN) --- create formatter --- format
Request B (en-US):       setDefault(en-US) --- create formatter --- format
~~~

The interleaving timing of the two requests cannot be controlled. Request A may create a formatter **after** B has changed the default to `en-US`. This problem occurs even without caching. Adding a cache does not fix this race and can make a transient bug persist longer.

Safer alternative:

~~~text
Request A (vi-VN) → Locale A → vi-VN formatter/cache key → result A
Request B (en-US) → Locale B → en-US formatter/cache key → result B
~~~

- Locale is request data or user context, passed explicitly to the formatting layer.
- Immutable formatters can be shared by an appropriate key.
- Mutable formatters need dedicated instances or explicit synchronization.
- Never call `Locale.setDefault` on the request-handling path.
- If the framework has a request-scoped locale context, understand its scope and how context propagates across async tasks/thread pools; do not assume thread-bound variables are always inherited properly.

**Additional reminder:** a `ConcurrentHashMap` cache only guarantees that operations on the map itself are thread-safe; it **does not make mutable `NumberFormat` values inside it thread-safe**.

## 12. Properly Testing Time-Dependent Behavior

To verify that a system does not implicitly depend on the JVM default, you can design these tests:

| Test | What to observe |
| --- | --- |
| Create formatter under default A, switch to default B, reuse formatter | The old formatter retains the formatting/config it was created with |
| Create a new formatter after changing default | APIs without a locale parameter may pick B |
| Pass explicit locale A, change default repeatedly | Results for the same value/formatter A remain stable |
| Cache by `Locale`, concurrent access | No locale mixing across requests |
| Shared mutable formatter cache | Check for races; best to eliminate this design |
| User changes language | Content cache returns the new language |
| Reload bundle/update messages | Cache policy returns the right translation version |
| Change time zone or update tzdb | Local time results align with policy |
| Upgrade JDK/provider | Compare critical formatting output, especially Unicode characters and date patterns |

### Keeping Tests Reproducible Without Cross-Test Contamination

In a standalone Java program, you can save the default before an experiment and restore it in `finally`. However, if a test suite runs **in parallel within the same JVM**, changing the default can still affect other tests before `finally` executes. Consider running tests that must mutate defaults in a separate JVM process or sequentially with isolation, and prefer testing logic by passing explicit locales.

If you need to assert **exact** localized strings, pin the JDK version, locale provider, and dependent data. Do not casually compare spaces that look alike: regular space (`U+0020`), non-breaking space (`U+00A0`), and narrow no-break space (`U+202F`) are different characters. In business logic tests, asserting data fields or the selected locale can be more reliable than character-by-character CLDR-dependent snapshots.

## 13. Common Misconceptions

1. **“Calling `Locale.setDefault` makes all live formatters switch language.”** False: many formatters retain settings from creation time.
2. **“Every `format` call re-checks the default locale.”** There is no general guarantee of that; normally the formatter already holds its locale selection/rules.
3. **“A `static final NumberFormat` will automatically update per user.”** False; it is also mutable and not thread-safe.
4. **“An immutable `DateTimeFormatter` always has the right locale.”** False; it can be thread-safe to share while still carrying the wrong locale.
5. **“Changing the default clears JDK, framework, and `ResourceBundle` caches.”** There is no such general cache-clearing behavior.
6. **“`ResourceBundle.clearCache()` alters old bundle objects already held.”** False: clearing cache entries does not replace references the application already stored.
7. **“Using `ConcurrentHashMap<Locale, NumberFormat>` makes the formatter thread-safe.”** False: a thread-safe map does not make its mutable values thread-safe.
8. **“Locale and time zone are the same thing.”** False: both can affect display, yet they govern different parts.
9. **“Caching by a single locale is enough for every format.”** It may miss style, pattern, zone, currency, chronology, and other options.
10. **“Wrapping `Locale.setDefault` in `synchronized` per request solves everything.”** It does not protect against other libraries/threads reading the default outside that lock, and still leaves a JVM-wide implicit context.

## 14. Applying This in a Java Application

A practical architecture usually follows this order:

1. **Receive and validate the user's locale** against the product's supported locale list, with a documented fallback.
2. **Select the effective locale** right at the request/use-case boundary.
3. **Pass an explicit `Locale`** to formatters and message systems; pass time zone, currency, and independent options as needed.
4. **Cache immutable `DateTimeFormatter` instances with complete keys** where clearly beneficial; for mutable `NumberFormat`, create per-scope instances.
5. **Do not mutate the JVM-wide default locale on multi-user processing paths.**
6. **Manage content and bundle caches with dedicated policies**, using versioning/reloading when translations or rules are updated.
7. **Test context switching and concurrent requests**, rather than testing only against one fixed JVM startup default.

### Self-Check Questions

**1.** `NumberFormat.getNumberInstance()` was created when the default was `en-US`. Later the default changed to `de-DE`. Will calling `format` on the old object automatically switch to `de-DE`?

**Answer:** No; the old formatter keeps its creation-time configuration. To format in German, create a new formatter with the right locale or explicitly configure an appropriate formatter.

**2.** Is a thread-safe `static final DateTimeFormatter` a good choice for every locale?

**Answer:** Not enough; it is safe for concurrent access, but can carry only the single locale chosen at creation time. Use `withLocale` or cache by specific locale.

**3.** Why does `ResourceBundle.clearCache()` not guarantee that the UI immediately switches all translations?

**Answer:** The application may still hold old bundle references, cached HTML output, or another framework's cache. Each layer must be managed.

**4.** If `vi-VN` and `en-US` users exist concurrently in one JVM, why not call `Locale.setDefault` per request?

**Answer:** The default is shared state; two threads can interleave reads/writes and create formatters with the wrong locale. Passing each request's locale is the proper control.

**5.** When caching formatted date-time strings, besides locale, what other factors can affect the result?

**Answer:** The timestamp value, zone, style/pattern, chronology, and formatting data version, depending on the use case.

**Key takeaway:** **Formatter creation time determines a crucial part of the configuration it carries; caching can extend the lifetime of that configuration.** The default locale is JVM state, so multi-user systems need explicit locale selection, adequately keyed caches, and formatter lifecycle management suited to immutable/mutable characteristics.
