# Assigning Custom Formatters per Argument in MessageFormat and Limitations with java.time Types

`java.text.MessageFormat` combines a sentence pattern with dynamic arguments such as user names, quantities, unit prices, or appointment dates. In practice, **a single sentence pattern may need multiple custom formatting rules**, and **modern date/time types in `java.time` are not directly compatible with `MessageFormat`'s legacy date/time formats on Java 17/21**.

This lesson shows how to assign `java.text.Format` **per argument index**, distinguish argument indices from placeholder appearance order, select locales, and handle `LocalDate`/`LocalDateTime`/`Instant` in three ways: **pre-formatting into a string**, **using `DateTimeFormatter.toFormat()`**, or **converting to `java.util.Date` when interoperability with legacy APIs is truly required**. The programs run on Java 17 and later; the `MessageFormat` syntax covered is what is available on **Java 17 and Java 21**, avoiding reliance on extensions from newer JDKs.

## 1. Recap: Where MessageFormat Fits

A `MessageFormat` takes a **pattern** containing items like `{0}`, `{1,number}`, `{2,date,short}` and an array of arguments. The number inside curly braces is the **argument index**, starting from 0; it points into the array passed to `format(...)`.

```java
import java.text.MessageFormat;
import java.util.Locale;

MessageFormat message = new MessageFormat(
        "Hello {0}, you have {1,number,integer} items.",
        Locale.US);
String text = message.format(new Object[] {"Lan", 5});
```

This is a **fragment inside a method**, not a standalone runnable file. The value of `text` is:

```text
Hello Lan, you have 5 items.
```

Normally, `MessageFormat` automatically creates subformatters for `number`, `date`, `time`, and `choice` according to the pattern and locale. Sometimes, however, developers need a custom `DecimalFormat`, an order-code formatter, or a `DateTimeFormatter` for `LocalDate`. In such cases, replacing the subformatter for a specific **argument index** via `setFormatByArgumentIndex(...)` is essential.

### Two Easily Confused Index Types

The following pattern has three **format elements** but only two **argument indices**:

```text
Pattern:      "A={1}; B={0}; C={1}"
Position 0:   {1}   -> argument index 1
Position 1:   {0}   -> argument index 0
Position 2:   {1}   -> argument index 1 (repeated)
```

- **Argument index**: the number inside `{...}`, such as `1` in `{1}`. Preserves argument meaning even when translations change placeholder order.
- **Format-element index**: the 0, 1, 2... appearance position of a `{...}` expression when scanning the pattern from left to right. This can change when translators rearrange the sentence.

That is why you cannot arbitrarily swap `setFormatByArgumentIndex(1, ...)` for `setFormat(1, ...)`.

## 2. Four Formatter-Assignment APIs and Their Meanings

| API | Corresponding index | Effect when an index repeats |
| --- | --- | --- |
| `setFormatByArgumentIndex(int argIndex, Format format)` | **Argument index**, e.g., the number in `{1}` | Replaces the formatter for **every** format element using that argument index |
| `setFormatsByArgumentIndex(Format[] formats)` | Array index = argument index | Same, across multiple argument indices |
| `setFormat(int elementIndex, Format format)` | Position of the **format element** in the pattern | Replaces only one specific occurrence |
| `setFormats(Format[] formats)` | Positions of format elements in the pattern | Each array element affects one appearance position |

Prefer `setFormatByArgumentIndex` or `setFormatsByArgumentIndex` whenever **an argument has one uniform formatting rule**, especially if translated sentences have different placeholder orders.

There is still a valid reason to use `setFormat(elementIndex, ...)`: when the same argument must appear in two places with **two different representations**, such as a short date in a heading and a long date in the body. In that case you intentionally format **each occurrence**, while recognizing that translator edits to sentence structure can change element order.

### What Type Is `Format`?

These methods accept `java.text.Format` or a subclass; for example:

- `NumberFormat`: numbers, percentages, currencies; supports explicit locale and currency selection.
- `DecimalFormat`: numeric patterns such as `"0000"`, `"#,##0.00"`.
- `DateFormat`/`SimpleDateFormat`: formats `java.util.Date` and compatible legacy types.
- `ChoiceFormat`: branches by numeric value in simple sentence patterns.
- A `Format` adapter created via `DateTimeFormatter.toFormat()`: accepts `java.time.temporal.TemporalAccessor` objects in Java 17/21.

**Note:** `DateTimeFormatter` is not a subclass of `java.text.Format`. You cannot pass `DateTimeFormatter.ISO_LOCAL_DATE` directly to `setFormatByArgumentIndex`; you must use `toFormat()` or another conversion strategy.

## 3. Runnable Example: Assigning Formatters by Argument Index

Create the file **`ArgumentFormatDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.util.Locale;

public class ArgumentFormatDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;

        MessageFormat byArgument = new MessageFormat(
                "Order={1}, qty={0}, repeat={0}", locale);

        DecimalFormat quantity = new DecimalFormat(
                "0000", DecimalFormatSymbols.getInstance(locale));
        byArgument.setFormatByArgumentIndex(0, quantity);

        System.out.println(byArgument.format(
                new Object[] {7, "AB"}));

        MessageFormat byElement = new MessageFormat(
                "One={1}; plain={0}; again={1}", locale);
        DecimalFormat padded = new DecimalFormat(
                "000", DecimalFormatSymbols.getInstance(locale));
        byElement.setFormat(0, padded);

        System.out.println(byElement.format(
                new Object[] {7, 7}));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ArgumentFormatDemo.java
java ArgumentFormatDemo
```

Stdout:

```text
Order=AB, qty=0007, repeat=0007
One=007; plain=7; again=7
```

**Line 1 explanation:** both `{0}` placeholders use the same argument `7`, so `setFormatByArgumentIndex(0, quantity)` formats **both** as `0007`. Where `{0}` appears in the sentence does not matter.

**Line 2 explanation:** `setFormat(0, padded)` only replaces the **first format element** of the pattern, which is `{1}` inside `One=...`. The second occurrence of `{1}` in `again=...` keeps its default formatting, yielding `7`. Passing `0` to `setFormat(0, ...)` does not mean "assign to argument index 0".

### What If a Translation Reorders Placeholders?

Suppose English uses `"Qty={0}; code={1}"` while Vietnamese uses `"Mã {1}; số lượng {0}"`. With `setFormatByArgumentIndex(0, quantity)`, the quantity is formatted identically regardless of its sentence position. With `setFormat(0, quantity)`, the first format element of the Vietnamese translation is `{1}` (the item code), which can cause a type error or incorrect display.

That is why APIs based on **argument index** are the right default choice when message patterns come from multiple `ResourceBundle` files.

## 4. Assigning Multiple Formatters with an Array

`setFormatsByArgumentIndex(new Format[] {...})` lets you assign rules for multiple indices:

```java
Format[] formats = {
    null,        // argument 0: no explicit subformat assigned
    null,        // argument 1
    priceFormat  // argument 2
};
message.setFormatsByArgumentIndex(formats);
```

This is just a **fragment**: `message` and `priceFormat` must be declared in the enclosing context. Array positions correspond to arguments 0, 1, and 2, respectively. For an argument that does not appear in the pattern, its entry is ignored; if the array has fewer elements than arguments used, remaining indices keep their current formats. A `null` entry means no explicit subformat is assigned for that slot (when formatting, `MessageFormat` uses default behavior based on the argument type).

**Runnable program — `MultipleFormatsDemo.java`:**

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.Format;
import java.text.MessageFormat;
import java.util.Locale;

public class MultipleFormatsDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "Price={2}; item={0}; again={2}", Locale.US);

        DecimalFormat price = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));

        message.setFormatsByArgumentIndex(
                new Format[] {null, null, price});

        System.out.println(message.format(
                new Object[] {"Notebook", "unused", 12.5}));
    }
}
```

```bash
javac -encoding UTF-8 MultipleFormatsDemo.java
java MultipleFormatsDemo
```

Stdout:

```text
Price=12.50; item=Notebook; again=12.50
```

`setFormats(...)` uses the **appearance order** of `{2}`, `{0}`, `{2}`. Because `{2}` repeats, passing an array indexed by argument index avoids misplacing formatters or missing an occurrence.

### Reading Back Formatter Configuration

- `getFormatsByArgumentIndex()` returns an array indexed by **argument index**. If the same argument appears multiple times with different formatters, the returned slot reflects the **last occurrence** of that argument, because one array slot cannot represent all variations.
- `getFormats()` returns an array indexed by **format-element index**, which distinguishes individual occurrences.
- Both APIs are useful for inspecting configuration, though in application code you should keep track of both the **source pattern** and intended formatters, because calling `applyPattern(...)` can replace previously assigned subformatters.

## 5. MessageFormat Locale vs. Component Formatter Locale

`new MessageFormat(pattern, locale)` selects the locale for subformats created from patterns like `{0,number}` and `{1,date,short}`. If you attach a `DecimalFormat` or `DateFormat` **created by yourself**, it keeps the locale/configuration of **that formatter object**, rather than automatically switching to `MessageFormat`'s locale.

```java
Locale uiLocale = Locale.forLanguageTag("vi-VN");
Locale numericLocale = Locale.US;

MessageFormat message =
        new MessageFormat("Value={0}", uiLocale);
DecimalFormat numeric =
        new DecimalFormat("0.00",
                DecimalFormatSymbols.getInstance(numericLocale));
message.setFormatByArgumentIndex(0, numeric);
```

The snippet above is a **Java fragment** with appropriate imports. Its meaning: the message pattern is prepared for the `vi-VN` UI language, while the numeric argument uses number conventions controlled by `numericLocale`. If you want numbers to follow `vi-VN` as well, create `DecimalFormatSymbols.getInstance(uiLocale)`.

**`setLocale(Locale)` does not update previously created subformatters.** It affects subformatters created by subsequent `applyPattern(...)` calls and certain formatting cases without a fixed subformat. Recreate `MessageFormat` or re-attach subformatters when the request locale changes.

**`applyPattern(...)` parses the pattern and rebuilds the format elements**, so a custom formatter previously attached via `setFormatByArgumentIndex(...)` can be lost after applying another pattern. The recommended order is:

1. Load the **locale-appropriate pattern** from translation resources.
2. Construct `MessageFormat(pattern, locale)`.
3. Create subformatters with the appropriate locale/currency/time zone.
4. Assign formatters by **argument index**.
5. Call `format(new Object[] {...})` with values of the expected types.

Never design a global formatter and repeatedly call `setLocale` or `applyPattern` while requests run concurrently.

## 6. The Big Issue with `java.time` on Java 17 and Java 21

The classic `MessageFormat` syntax for dates and times is:

```text
{0,date}
{0,date,short}
{1,time,long}
{2,date,yyyy-MM-dd}
```

On **Java 17 and Java 21**, these `date`/`time` elements create `java.text.DateFormat` or `SimpleDateFormat`. They understand legacy date/time input types, particularly `java.util.Date`, but **do not accept `LocalDate`/`LocalDateTime`/`Instant` as a `java.util.Date`**.

| Input value | `{0}` without a subformat | `{0,date,short}` on Java 17/21 |
| --- | --- | --- |
| `java.util.Date` | `MessageFormat` uses default date/time formatting for Date arguments | Formatted via `DateFormat` |
| `LocalDate` | Usually becomes a string via `toString()`; e.g., `2026-10-28` | Typically throws `IllegalArgumentException` because it is not a `Date` |
| `LocalDateTime` | `toString()` string, without time zone info | Not directly supported by `DateFormat` |
| `Instant` | `toString()` string like `2026-10-28T...Z` | Not directly supported by `DateFormat` |
| `ZonedDateTime` | `toString()` string with zone/offset info | Not directly supported by `DateFormat` |

**Do not confuse `toString()` with localization:** when a pattern only has `{0}`, seeing `LocalDate` printed as `2026-10-28` does not mean `MessageFormat` applied the user's date conventions. That is merely the object's default string representation. If you need localized month names or day/month order, you must use an appropriate `DateTimeFormatter`.

### Example Demonstrating the Difference — `JavaTimeLimitationDemo.java`

```java
import java.text.MessageFormat;
import java.time.LocalDate;
import java.util.Locale;

public class JavaTimeLimitationDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        MessageFormat raw = new MessageFormat(
                "Raw={0}", Locale.US);
        System.out.println(raw.format(new Object[] {date}));

        MessageFormat legacy = new MessageFormat(
                "Date={0,date,short}", Locale.US);
        try {
            System.out.println(
                    legacy.format(new Object[] {date}));
        } catch (IllegalArgumentException exception) {
            System.out.println(
                    "Date type rejected: "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 JavaTimeLimitationDemo.java
java JavaTimeLimitationDemo
```

Stdout on Java 17/21:

```text
Raw=2026-10-28
Date type rejected: IllegalArgumentException
```

The first line is `LocalDate.toString()`, and the second is the error when `DateFormat` is selected for the placeholder. Do not try to "fix" this by casting `(java.util.Date) localDate`: these are unrelated type hierarchies, and a direct cast is invalid.

**Version note:** newer JDKs may introduce `MessageFormat` syntax that interacts directly with `DateTimeFormatter`. Do not assume that new syntax exists in **Java 17/21**. This lesson focuses on solutions that actually work on the common Java 17+ baseline.

## 7. Approach 1 — Pre-format `java.time` and Pass a String

The simplest, most controllable approach when a sentence pattern only needs **one date representation**: use `DateTimeFormatter` to convert the temporal object into a string, then let `MessageFormat` insert that string into `{0}`.

**File `PreformatJavaTimeDemo.java`:**

```java
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class PreformatJavaTimeDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter dateFormatter =
                DateTimeFormatter.ISO_LOCAL_DATE;

        String prepared = date.format(dateFormatter);

        MessageFormat message = new MessageFormat(
                "Meeting date: {0}", Locale.US);

        System.out.println(message.format(
                new Object[] {prepared}));
    }
}
```

```bash
javac -encoding UTF-8 PreformatJavaTimeDemo.java
java PreformatJavaTimeDemo
```

Stdout:

```text
Meeting date: 2026-10-28
```

To localize, replace `ISO_LOCAL_DATE` with:

```java
// Fragment inside a method with the relevant classes imported.
DateTimeFormatter local = DateTimeFormatter
        .ofLocalizedDate(java.time.format.FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("vi-VN"));
String prepared = date.format(local);
```

The `prepared` text then depends on JDK locale data, so avoid asserting a hardcoded localized date string as invariant stdout across all environments.

**Pros:** explicit steps, leverages immutable `java.time` APIs, easily handles `LocalDate`, `LocalTime`, and `LocalDateTime`. **Limitation:** when a translation needs the same date argument to appear **twice in two different formats**, you must prepare two strings or use an adapter; translators should know the parameter is already formatted.

**Important:** never use a pattern like `"{0,date}"` for an argument that is already a `String`: the `DateFormat` subformat still expects a legacy date value and may throw an error. With a pre-formatted string, the pattern must use `{0}`.

## 8. Approach 2 — `DateTimeFormatter.toFormat()` to Attach a Subformatter

`DateTimeFormatter` does not extend `java.text.Format`, but it provides **`toFormat()`** and **`toFormat(TemporalQuery<?>)`**, which return a `Format` adapter. This adapter accepts objects implementing `TemporalAccessor` when formatting, including `LocalDate`; this is the direct bridge for using `setFormatByArgumentIndex` in Java 17/21.

**Standalone runnable example — `JavaTimeFormatBridgeDemo.java`:**

```java
import java.text.Format;
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class JavaTimeFormatBridgeDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        MessageFormat message = new MessageFormat(
                "Planned={0}; repeated={0}", Locale.US);

        Format adapter =
                DateTimeFormatter.ISO_LOCAL_DATE
                        .toFormat(LocalDate::from);

        message.setFormatByArgumentIndex(0, adapter);

        System.out.println(message.format(
                new Object[] {date}));
    }
}
```

```bash
javac -encoding UTF-8 JavaTimeFormatBridgeDemo.java
java JavaTimeFormatBridgeDemo
```

Stdout:

```text
Planned=2026-10-28; repeated=2026-10-28
```

**How it works:**

1. `DateTimeFormatter.ISO_LOCAL_DATE` knows how to format a `LocalDate` into an ISO date.
2. `toFormat(LocalDate::from)` returns a `java.text.Format` compatible with `MessageFormat` setters. When **parsing** back, the query produces a `LocalDate` instead of a generic `TemporalAccessor`.
3. `setFormatByArgumentIndex(0, adapter)` attaches the adapter to **both** `{0}` placeholders.
4. The argument stays a **`LocalDate`**, without needing conversion to `java.util.Date` or a string beforehand.

You can use `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(uiLocale).toFormat()` to format dates according to the user's locale. When using a formatter containing time fields, you must supply a temporal type with all required fields. For instance, a `LocalDate` **has no time-of-day** and will fail if the formatter requires hours; a `LocalDateTime` **has no offset/zone** and cannot represent a global instant without a `ZoneId`.

### What About Reverse Parsing?

No-argument `toFormat()` typically parses into a resolved `TemporalAccessor`; `toFormat(LocalDate::from)` requests a `LocalDate`. In messaging applications, `MessageFormat` is primarily used for **formatting**; parsing back from translated prose sentences is ambiguous and unsuitable as a critical data-input API. If you need to parse dates, call `LocalDate.parse(input, dateFormatter)` directly with a known formatter and locale.

## 9. Approach 3 — Converting to `java.util.Date` When Legacy `DateFormat` Is Required

In a legacy system that already has a configured `DateFormat` or `SimpleDateFormat`, you can convert `java.time` objects to `java.util.Date` **after explicitly determining the instant and time zone**.

**There is no direct conversion from `LocalDate` to `Date` without choosing a zone**, because `LocalDate` is strictly a calendar date without time-of-day or time zone. The date `2026-10-28` at start-of-day in `Asia/Ho_Chi_Minh` corresponds to a different instant than start-of-day in `UTC`.

**File `LegacyDateBridgeDemo.java`:**

```java
import java.text.MessageFormat;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDateBridgeDemo {
    public static void main(String[] args) {
        LocalDate localDate = LocalDate.of(2026, 10, 28);
        ZoneId zone = ZoneId.of("UTC");

        Date oldDate = Date.from(
                localDate.atStartOfDay(zone).toInstant());

        SimpleDateFormat legacyFormat =
                new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        legacyFormat.setTimeZone(TimeZone.getTimeZone(zone));

        MessageFormat message = new MessageFormat(
                "Legacy={0}", Locale.US);
        message.setFormatByArgumentIndex(0, legacyFormat);

        System.out.println(message.format(
                new Object[] {oldDate}));
    }
}
```

```bash
javac -encoding UTF-8 LegacyDateBridgeDemo.java
java LegacyDateBridgeDemo
```

Stdout:

```text
Legacy=2026-10-28
```

The output is stable because both **the `LocalDate`-to-instant step** and **`SimpleDateFormat`** use UTC. If you omit `setTimeZone(...)`, the formatter may interpret the `Date` in the JVM's default time zone and shift the displayed date in some environments.

When you already have an `Instant`, you can use `Date.from(instant)` since both represent an instant in time. When you have a `LocalDateTime`, choose the business-appropriate `ZoneId` to construct a `ZonedDateTime`/`Instant` before converting. **Never treat the server's time zone as an implicit default** when date/time belongs to a specific location or user.

**Trade-off:** this approach fits interoperating with legacy code; for new code, `DateTimeFormatter.toFormat()` or pre-formatting usually takes fewer steps and carries less risk of time-zone bugs. `SimpleDateFormat` holds mutable state and is unsafe when called concurrently by multiple threads without protection.

## 10. Technical Pitfalls When Assigning Formatters

### A. Passing the Wrong Argument Type

If the specified subformat is a `NumberFormat`, the argument must be a compatible number; `DateFormat` requires a supported date value; a `DateTimeFormatter` adapter accepts a `TemporalAccessor` with the required fields. For example:

```java
MessageFormat form = new MessageFormat(
        "Date={0,date,short}", Locale.US);
form.format(new Object[] {
        java.time.LocalDate.of(2026, 10, 28)
});
```

This snippet **illustrates an error on Java 17/21**, not a working example: the `DateFormat` created by the `date` pattern receives an incompatible `LocalDate`, typically throwing `IllegalArgumentException`. The fix is to use one of the three approaches above.

### B. Using Element Indices on Translated Content

`setFormat(0, ...)` assigns to the **first placeholder in the sentence**, not necessarily argument `0`. Sentences in two languages can swap their order. Prefer `setFormatByArgumentIndex(0, ...)` whenever the same argument needs one formatter.

### C. Formatting One Argument in Multiple Ways

If a pattern contains `"{0,date,short} ... {0,date,long}"`, calling `setFormatByArgumentIndex(0, custom)` replaces **both subformatters**, erasing the short/long distinction. When two formats are intentionally needed, you can pass **two pre-prepared arguments** (e.g., `{0}` for the short date and `{1}` for the long date), or assign by **element index** with translation tests.

### D. `applyPattern` Resets Custom Formatters

`applyPattern(...)` re-parses the pattern and creates a fresh set of format elements. If code assigns custom formatters first and applies the translation pattern afterward, those formatters can be lost. Always **select the pattern first, attach formats afterward**; when changing locale, create a new `MessageFormat` or re-attach formats for the new context.

### E. Treating `setLocale` as a Command to Update All Formatters

`message.setLocale(newLocale)` does not automatically update previously created subformatters. `DecimalFormat`, `DateFormat`, and `DateTimeFormatter` adapters that you attached retain their own settings. If you need to change locale, rebuild the configuration from scratch.

### F. Sharing MessageFormat Across Threads

`MessageFormat` is unsynchronized; many subformatters such as `NumberFormat` and `SimpleDateFormat` have mutable state. In a web server, create instances per render/request or guard shared usage by design. Avoid calling `setFormatByArgumentIndex` on an object actively used by other requests.

### G. Forgetting Single Quotes and Braces in Patterns

In `MessageFormat` patterns, the single quote `'` acts as syntactic quoting; to display a real single quote, you usually must write `''`. Literal `{`/`}` characters in prose that are not placeholders must be properly quoted. When loading patterns from `ResourceBundle`, translators must know these strings are parsed by `MessageFormat`; incorrect quoting can prevent placeholders from being substituted.

### H. Using `MessageFormat.parse` to Reconstruct Business Data

`format` is not always invertible. If the same argument appears multiple times, `parse` may return only the **last match**. Currency units, time zones, locales, and display formatting can also lose precision. Inputs requiring structured data should use dedicated parsers (`LocalDate.parse`, `NumberFormat.parse` with full-input validation, etc.) rather than parsing UI sentences.

## 11. Example: Assembling a ResourceBundle Message with Per-Argument Formatters

In a localized product, **wording belongs to the bundle**, data belongs to the code, and formatters belong to the formatting context. You can define a parameterized key in `messages.properties`:

```properties
order.summary=Order {0} has {1} units, ship date {2}.
```

Example `messages_vi.properties`:

```properties
order.summary=Đơn {0} có {1} sản phẩm, giao ngày {2}.
```

When messages come from a bundle, a typical workflow is:

1. Determine the user's `Locale uiLocale`, load the bundle via `ResourceBundle.getBundle(baseName, uiLocale)`.
2. Retrieve the pattern with `bundle.getString("order.summary")`.
3. Construct `MessageFormat(pattern, uiLocale)`.
4. Attach a numeric formatter for argument `1` and a `DateTimeFormatter` adapter for argument `2`.
5. Pass the arguments—order ID, quantity, and `LocalDate`—and receive a complete sentence.

**Standalone Java 17+ program** — file `MessageBundleBridgeDemo.java` (the pattern is inline here so no extra `.properties` file is needed for this test):

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class MessageBundleBridgeDemo {
    public static void main(String[] args) {
        Locale uiLocale = Locale.US;
        String pattern =
                "Order {0}: {1} units, date {2}, repeat {2}";

        MessageFormat message =
                new MessageFormat(pattern, uiLocale);

        DecimalFormat quantity = new DecimalFormat(
                "000", DecimalFormatSymbols.getInstance(uiLocale));
        message.setFormatByArgumentIndex(1, quantity);

        message.setFormatByArgumentIndex(
                2, DateTimeFormatter.ISO_LOCAL_DATE.toFormat());

        Object[] values = {
                "AX-9",
                7,
                LocalDate.of(2026, 10, 28)
        };

        System.out.println(message.format(values));
    }
}
```

```bash
javac -encoding UTF-8 MessageBundleBridgeDemo.java
java MessageBundleBridgeDemo
```

Stdout:

```text
Order AX-9: 007 units, date 2026-10-28, repeat 2026-10-28
```

This example embeds the pattern directly for standalone execution. When switching to a real `ResourceBundle`, replace `pattern` with `bundle.getString(key)` and keep assigning formats by **argument index**, so translations can reorder arguments without breaking data types. Date formatting can switch from `ISO_LOCAL_DATE` to `ofLocalizedDate(FormatStyle.MEDIUM).withLocale(uiLocale)` when the UI needs local conventions; the resulting date string then depends on runtime locale data.

## 12. Formatting Capabilities and Limits by `java.time` Type

| Temporal type | Can pre-format with `DateTimeFormatter`? | Can use `toFormat()` as subformatter? | Key caveats |
| --- | --- | --- | --- |
| `LocalDate` | Yes, with a date formatter | Yes, if formatter only requires date fields | Has no time-of-day or time zone |
| `LocalTime` | Yes, with a time formatter | Yes, if it only requires time fields | Has no date or time zone |
| `LocalDateTime` | Yes, if formatter requires date and/or time | Yes | Does not specify an instant without a zone |
| `OffsetDateTime` | Yes, using a pattern with offset when needed | Yes | Has an offset, not necessarily a region zone |
| `ZonedDateTime` | Yes, including zone/offset if formatter requires | Yes | Zone rules can affect output |
| `Instant` | Yes with `DateTimeFormatter.ISO_INSTANT`, or a formatter given an appropriate zone | Yes with a compatible formatter | Does not inherently contain regional calendar fields unless the formatter has a zone |
| `YearMonth` | Yes with pattern `uuuu-MM` | Yes with a formatter requiring only year/month | Has no day of month |
| `Duration` / `Period` | Not a standard calendar-date object for localized date/time formatters | Cannot directly use `ofLocalizedDate` | Use `toString()` or custom business formatting |

**Rule for choosing a formatter:** to format a type, the type must supply the fields the formatter requests. For example, `LocalDate` lacks `HOUR_OF_DAY`, so `DateTimeFormatter.ofLocalizedTime(...)` cannot fabricate an hour. `Instant` must be mapped to a zone to produce local date/time components; a locale alone is not enough.

**Do not equate `Locale` and `ZoneId`:** locale determines language/formatting conventions, while `ZoneId` determines how an instant maps to local wall-clock time. Two users sharing `en-US` can live in different time zones, and a user can select a language different from their physical region.

### Advanced Note: Immutable Formatters Under Controlled Lifecycle

`DateTimeFormatter` is immutable and thread-safe by itself. However, the enclosing `MessageFormat` object remains mutable and is not guaranteed safe when shared without synchronization. Do not assume that using a solid `DateTimeFormatter` makes the entire `MessageFormat` thread-safe.

## 13. Essential Tests

A practical test suite for message formatting should cover:

- **Repeated arguments:** `{0}` appears multiple times and `setFormatByArgumentIndex(0, ...)` applies to all occurrences.
- **Translation reordering:** swap `{0}`/`{1}` between two patterns; formatters stay attached to the right **argument index**.
- **Element vs. argument distinction:** verify `setFormat(0, ...)` only alters the first position, not every placeholder with the same argument number.
- **Wrong type:** `LocalDate` with `{0,date,short}` on Java 17/21 throws an error; with `DateTimeFormatter.toFormat()`, it succeeds.
- **Pre-formatted string:** `date.format(dtf)` passed into `{0}` without needing legacy `DateFormat`.
- **Time zone:** when converting `LocalDate` to `Date`, specify and test both the zone used to build the instant and the formatter's time zone.
- **Changing locales:** format numbers/dates per request locale; do not rely on `setLocale` to update existing subformatters.
- **`applyPattern`:** when applying a new pattern, reconfigure formatters before rendering.
- **Multithreading:** concurrent requests do not mutate a shared `MessageFormat` or `SimpleDateFormat`.
- **Parsing:** if reading structured user input, use dedicated parsers and validate the whole string rather than relying on recovering data from rendered sentences.

### Exercise 1 — Two Positions for the Same Argument

Given the pattern `"ID={1}; amount={0}; amountAgain={0}"` and arguments `{12.5, "A-1"}`, use `setFormatByArgumentIndex(0, new DecimalFormat("0.00", DecimalFormatSymbols.getInstance(Locale.US)))` so both numeric slots print `12.50`. Then try `setFormat(0, ...)` and explain why it affects the `{1}` placeholder at the start of the sentence.

### Exercise 2 — Modern Dates

With `LocalDate.of(2026, 10, 28)`, create two patterns `"Date={0}"` and `"Date={0,date,short}"`. Observe the behavior on Java 17/21. Use `ISO_LOCAL_DATE.toFormat()` for the `{0}` pattern, then try a localized formatter with `withLocale(Locale.forLanguageTag("vi-VN"))`.

### Exercise 3 — From Bundle to Screen

Create two message files containing the same pair of argument indices for order ID and quantity, but in different orders. Read each pattern and assign a numeric formatter by argument index. Prove that both translations receive the right data regardless of placeholder position in the sentence.

## 14. Official Documentation and Versions

- [JDK 21 — java.text.MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html): patterns, `setFormatByArgumentIndex`, `setFormatsByArgumentIndex`, `setFormat`, `applyPattern`, and legacy date/time defaults.
- [JDK 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): `toFormat()`, `toFormat(TemporalQuery)`, `withLocale`, `withZone`, and `java.time` formatting.
- [JDK 21 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html): legacy date/time model, time zones, and mutable-format caveats.

Newer JDKs may expand `MessageFormat` capabilities; when a program targets Java 17/21, always consult the documentation for **the exact version in use** and do not copy syntax from newer JDK docs without verifying compatibility.

## 15. Key Takeaways

**`setFormatByArgumentIndex(index, format)` assigns a formatter by argument index and applies to every placeholder referencing that argument; `setFormat(elementIndex, format)` assigns only by the placeholder's appearance position in the sentence.** For translated messages, assignment by argument index is much more resilient when sentence order changes.

On **Java 17/21**, `MessageFormat`'s `{0,date}`/`{0,time}` elements rely on `java.text` APIs and cannot be used directly with many `java.time` types like `LocalDate`. To handle this properly, **pre-format to a string**, **attach a `DateTimeFormatter.toFormat()` adapter**, or **convert to `java.util.Date` with an explicit `ZoneId` when interoperating with legacy code**. Always control locale, argument types, time zones, and `MessageFormat` lifecycle to prevent formatting bugs or thread contention.
