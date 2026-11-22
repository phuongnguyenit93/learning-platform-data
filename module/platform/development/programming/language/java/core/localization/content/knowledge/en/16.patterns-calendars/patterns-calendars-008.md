# ResolverStyle.STRICT, SMART, LENIENT and Valid Date Parsing in Java

## 1. A String Matching a Date Pattern Is Not Necessarily a Valid Date

Applications accepting birth dates, appointment dates, payment due dates, or effective dates often receive strings like `2024-02-29`. Having the expected digit counts and order is **not enough** to conclude that the date exists on the calendar.

For example:

| String | Matches `uuuu-MM-dd` shape? | Does the ISO calendar date exist? |
| --- | --- | --- |
| `2024-02-29` | Yes | Yes: 2024 is a leap year |
| `2023-02-29` | Yes | No: 2023 is not a leap year |
| `2023-02-30` | Yes | No: February has no day 30 |
| `2023-13-40` | Yes (still 2 digits for month/day) | No: month/day out of bounds |
| `2023-2-9` | No, if the pattern strictly requires `MM` and `dd` | Can express a real date, but **wrong pattern** |
| `abc` | No | No |

Java provides `java.time.format.ResolverStyle` to govern how **parsed date/time fields are resolved** into meaningful temporal objects. The three options are:

- `ResolverStyle.STRICT`: validates strictly against the calendar; rejects nonexistent dates.
- `ResolverStyle.SMART`: adjusts certain imprecise cases according to "sensible" per-field and per-calendar rules.
- `ResolverStyle.LENIENT`: accepts many out-of-range values during resolution and normalizes them via date/time arithmetic.

**Most importantly:** all three are **date resolution policies**, not three regular-expression modes, not three text formats, and not three "safety levels" interchangeable across domains. If users enter a real birth date, `STRICT` usually makes sense; if data represents relative day additions, `LENIENT` can be useful, provided it is an intentional choice.

## 2. Java Parses in Two Phases

In `DateTimeFormatter`, text parsing happens in two phases:

1. **Parse text against the formatter structure:** reads digits, separators, month names, optional sections, time zones, etc., into `TemporalField → value` pairs and related metadata. In this phase, `"2023-02-29"` can be parsed into `YEAR=2023`, `MONTH_OF_YEAR=2`, `DAY_OF_MONTH=29`, even though that combination is not a valid ISO date.
2. **Resolve fields into a date/time:** validates or normalizes the fields according to the active `ResolverStyle` and `Chronology`. This phase decides whether February 29, 2023 is rejected, clamped to February 28, or turned into March 1.

~~~text
Input "2023-02-29"
       |
       v
Phase 1: parse with "uuuu-MM-dd"
       |
       +--> YEAR = 2023
       +--> MONTH_OF_YEAR = 2
       +--> DAY_OF_MONTH = 29
       |
       v
Phase 2: resolve with ResolverStyle
       |
       +--> STRICT  : reject (2023 is not a leap year)
       +--> SMART   : 2023-02-28
       +--> LENIENT : 2023-03-01
~~~

Because `ResolverStyle` controls only the **resolve phase**, switching to `LENIENT` **does not make malformed strings parse automatically**. For example, `uuuu-MM-dd` still rejects `2023-2-9` for lacking the required width, and `abc` lacks valid numeric fields.

Keep these two concepts separate:

- `DateTimeFormatterBuilder.parseStrict()` / `parseLenient()` controls **strictness during the text-parsing phase** in the builder.
- `DateTimeFormatter.withResolverStyle(...)` controls **the field-resolution phase**. Setting the resolver to `LENIENT` is not equivalent to calling `parseLenient()` on the builder.

Java also offers `parseUnresolved(...)` to inspect phase-1 results before resolution; this is a low-level debugging API, **not** a validated final value ready to enter your domain model.

## 3. STRICT: Rejecting Nonexistent Calendar Dates

In the ISO calendar, `ResolverStyle.STRICT` requires field values to be within valid ranges and **the year–month–day combination to actually exist**.

~~~java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate valid = LocalDate.parse("2024-02-29", strict);
~~~

This is an **illustrative snippet inside a method**; it requires imports `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle`, and `java.util.Locale`. A standalone program appears in section 7.

Results:

- `2024-02-29` → valid date.
- `2023-02-29` → `DateTimeParseException`.
- `2023-02-30` → `DateTimeParseException`.
- `2023-13-40` → `DateTimeParseException`.
- `2023-00-10` → `DateTimeParseException`.

**When should you use it?** Birth dates, issue dates, contract deadlines, invoice dates, work schedule inputs, accounting dates, or any scenario where the key requirement is that **the entered date must exist** and never be silently altered.

However, `STRICT` only validates against the **calendar**; it does not enforce business rules. A date like `2099-12-31` may be a valid ISO date yet lie outside the registration window, holiday schedule, supported year range, or allowed age limits. After parsing, you must still validate **domain bounds and business rules**.

## 4. SMART: Adjusting Certain Days Within a Month, Not Fixing Everything

`ResolverStyle.SMART` is a smart policy defined **per field and per chronology**. When combining year/month/day in the ISO calendar, Java checks that day-of-month falls within the general **1 to 31** range, and if it exceeds the last day of **that specific month**, it can clamp to the last day of the month.

With the pattern `uuuu-MM-dd`:

| Input | `SMART` | Explanation |
| --- | --- | --- |
| `2024-02-29` | `2024-02-29` | Exists, kept as-is |
| `2023-02-29` | `2023-02-28` | Clamped to the end of February |
| `2023-02-30` | `2023-02-28` | Day 30 is in 1–31 but does not exist in February |
| `2023-02-32` | Rejected | Day exceeds general 1–31 range |
| `2023-13-40` | Rejected | Month 13 and day 40 are invalid |
| `2023-00-10` | Rejected | Month 0 is invalid |

**Do not use `SMART` to validate verbatim user input** when entering `2023-02-29` is an error the user should fix. In the example above, `LocalDate.parse` does not throw: the application receives `2023-02-28`, even though the input differed from what is stored.

`SMART` can fit if the domain **explicitly contracts** that days past month-end clamp to the last day of the month. For instance, certain monthly billing schedules expect this, though it is usually clearer to express that policy via explicit date operations such as `YearMonth.atEndOfMonth()` or `TemporalAdjusters.lastDayOfMonth()` rather than relying on an implicit side effect of parsing.

**Do not claim SMART always "rounds dates"**: handling depends on the field, chronology, and data type. For example, certain cases like `24:00` are handled differently from day-of-month values, so check each field's specific contract rather than extrapolating February's rule to every temporal field.

## 5. LENIENT: Normalizing Out-of-Range Months and Days

`ResolverStyle.LENIENT` allows many out-of-range fields and resolves them via calendar addition/subtraction.

For the ISO calendar and `uuuu-MM-dd`, you can visualize it as:

1. Start at the first day of the normalized year/month.
2. Offset by the parsed month and day values, even when out of bounds.
3. Return the resulting real `LocalDate`.

Verified examples:

| Input | `LENIENT` | Breakdown |
| --- | --- | --- |
| `2024-02-29` | `2024-02-29` | Valid date, unchanged |
| `2023-02-29` | `2023-03-01` | Day after 2023-02-28 |
| `2023-02-30` | `2023-03-02` | Two days after 2023-02-28 |
| `2023-13-40` | `2024-02-09` | Month 13/2023 → 01/2024, day 40 → 2024-02-09 |
| `2023-00-10` | `2022-12-10` | Month 0 → December of previous year |
| `2023-02-32` | `2023-03-04` | Day 32/02 rolls over into March |
| `abc` | Rejected | Fails the text-parsing phase |

`LENIENT` does not mean "ignore errors and fall back to today". It **normalizes out-of-range fields into a different date** that can be far from what the user thought they entered. This is especially hazardous for due dates, deadlines, birth dates, or legal documents: `2023-13-40` can turn into `2024-02-09` without the user ever realizing their input was broken.

**When to use it?** Data transformation tools with documented rollover semantics, automated calendar tests, or relative calculations whose inputs intentionally exceed normal field ranges. In almost all APIs accepting **user-typed absolute dates**, choosing `STRICT` and reporting specific errors avoids nasty surprises.

If the goal is adding 40 days, use explicit date-arithmetic APIs:

~~~java
LocalDate result = LocalDate.of(2024, 1, 1).plusDays(39);
~~~

This is an illustrative snippet, not a standalone file. This is far more transparent than constructing a month-13/day-40 string and relying on `LENIENT`.

## 6. Default Resolver Style and the yyyy vs. uuuu Pitfall

### 6.1. Not every default formatter is STRICT

Java SE 17 factories and predefined formatters have different defaults:

| Formatter | Default Resolver Style |
| --- | --- |
| `DateTimeFormatter.ofPattern("uuuu-MM-dd")` | **SMART** |
| `DateTimeFormatter.ofPattern("uuuu-MM-dd", locale)` | **SMART** |
| `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)` | **SMART** |
| `DateTimeFormatter.ISO_LOCAL_DATE` | **STRICT** |

Therefore:

~~~java
LocalDate parsed = LocalDate.parse(
        "2023-02-29",
        DateTimeFormatter.ofPattern("uuuu-MM-dd"));
~~~

This is an illustrative snippet. **The result can be `2023-02-28`**, rather than throwing an exception as many developers expect. Explicitly set the resolver style whenever the goal is validating user-entered dates.

~~~java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

`withResolverStyle` returns a **new formatter** because `DateTimeFormatter` is immutable; if you call it and discard the return value, the configuration does not change.

### 6.2. `yyyy` is not equivalent to `uuuu` in STRICT

This is another common pitfall when switching a formatter from `SMART` to `STRICT`:

- `u` / `uuuu`: **proleptic year** (`ChronoField.YEAR`), capable of representing year 0 and negative years in the proleptic ISO calendar.
- `y` / `yyyy`: **year-of-era** (`ChronoField.YEAR_OF_ERA`), requiring an **era** (`G`) context to locate the year on the timeline.
- `G`: **era** name/value (e.g., AD/BC in the ISO calendar per locale).

Comparing with `ResolverStyle.STRICT`:

~~~java
DateTimeFormatter wrongForStrict = DateTimeFormatter
        .ofPattern("yyyy-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter correctForIso = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

Both snippets are illustrative. With input `2024-02-29`:

- `uuuu-MM-dd` resolves `YEAR=2024`, `MONTH=2`, `DAY=29` → valid `LocalDate`.
- `yyyy-MM-dd` has only `YEAR_OF_ERA=2024` and **no era**, so under `STRICT` it lacks enough data to produce a `LocalDate`. The result is `DateTimeParseException` even though that calendar date is completely valid.
- If you intend year-of-era, supply an era such as `G yyyy-MM-dd` (e.g. `AD 2024-02-29` in an English locale) or intentionally configure a parse default for the era.

**For numeric ISO dates used as input**, prefer `uuuu-MM-dd` with `STRICT`, or use the built-in `DateTimeFormatter.ISO_LOCAL_DATE`. Do not randomly replace `yyyy` with `uuuu` in every display formatter when `yyyy` has valid semantics with era-based years.

### 6.3. Chronology can change resolution outcomes

The examples above use the **ISO calendar** (`LocalDate`). Under other `Chronology` systems (Japanese, Hijrah, Thai Buddhist...), calendar fields, leap years, eras, and bounds can differ. `ResolverStyle` sets the resolution policy, while the chronology actually combines fields into a date.

Do not conclude that `SMART` always clamps `29/02` to the 28th in **every chronology**; that is an **ISO** example. When requiring a specific calendar, apply its chronology explicitly and test appropriate boundary inputs.

## 7. Complete Java 17 Program and Verified Output

Place the following in **`ResolverStyleDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    static DateTimeFormatter formatter(ResolverStyle style) {
        return DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(style);
    }

    static String parse(ResolverStyle style, String input) {
        try {
            return LocalDate.parse(input, formatter(style)).toString();
        } catch (DateTimeParseException e) {
            return "REJECTED";
        }
    }

    static void show(String input) {
        System.out.println(input
                + " | STRICT=" + parse(ResolverStyle.STRICT, input)
                + " | SMART=" + parse(ResolverStyle.SMART, input)
                + " | LENIENT=" + parse(ResolverStyle.LENIENT, input));
    }

    public static void main(String[] args) {
        show("2024-02-29");
        show("2023-02-29");
        show("2023-02-30");
        show("2023-13-40");
        show("2023-00-10");
        show("abc");

        DateTimeFormatter yyyy = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter uuuu = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            System.out.println("STRICT yyyy="
                    + LocalDate.parse("2024-02-29", yyyy));
        } catch (DateTimeParseException e) {
            System.out.println("STRICT yyyy=REJECTED");
        }
        System.out.println("STRICT uuuu="
                + LocalDate.parse("2024-02-29", uuuu));

        System.out.println("ofPattern default="
                + DateTimeFormatter
                        .ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .getResolverStyle());
        System.out.println("ISO_LOCAL_DATE default="
                + DateTimeFormatter.ISO_LOCAL_DATE
                        .getResolverStyle());
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 ResolverStyleDemo.java
java ResolverStyleDemo
~~~

**Verified stdout** for the Java example:

~~~text
2024-02-29 | STRICT=2024-02-29 | SMART=2024-02-29 | LENIENT=2024-02-29
2023-02-29 | STRICT=REJECTED | SMART=2023-02-28 | LENIENT=2023-03-01
2023-02-30 | STRICT=REJECTED | SMART=2023-02-28 | LENIENT=2023-03-02
2023-13-40 | STRICT=REJECTED | SMART=REJECTED | LENIENT=2024-02-09
2023-00-10 | STRICT=REJECTED | SMART=REJECTED | LENIENT=2022-12-10
abc | STRICT=REJECTED | SMART=REJECTED | LENIENT=REJECTED
STRICT yyyy=REJECTED
STRICT uuuu=2024-02-29
ofPattern default=SMART
ISO_LOCAL_DATE default=STRICT
~~~

How to read the output:

1. `2024-02-29` is a valid leap-day; all three modes produce the same date.
2. `2023-02-29` is rejected by `STRICT`; `SMART` picks the end of February, while `LENIENT` moves to March 1.
3. `2023-02-30` again shows `SMART` **clamping to February 28**, whereas `LENIENT` moves to March 2.
4. `2023-13-40` and `2023-00-10` illustrate `LENIENT` normalizing out-of-range months and days.
5. `abc` provides no fields matching the pattern, so all three modes reject it in the text-parsing phase.
6. `STRICT yyyy` is rejected due to the missing **era**, not because 2024-02-29 is invalid; `STRICT uuuu` succeeds.
7. `ofPattern` defaults to `SMART`, whereas `ISO_LOCAL_DATE` is `STRICT`.

The program prints `REJECTED` instead of raw exception messages so the output stays stable across Java versions. In real applications, handle `DateTimeParseException` with a clear error policy and never expose internal stack traces directly to users.

## 8. Building Reliable Date-Input Validators

### 8.1. Parse strictly with an ISO pattern when the source requires real dates

For APIs accepting `yyyy-MM-dd`-style input under common naming conventions, the proper Java pattern for ISO **proleptic** year is `uuuu-MM-dd`:

~~~java
public static LocalDate requireIsoDate(String raw) {
    DateTimeFormatter format = DateTimeFormatter
            .ofPattern("uuuu-MM-dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);
    return LocalDate.parse(raw, format);
}
~~~

This is an **illustrative method**, not a standalone program. It must live in a class with imports `LocalDate`, `DateTimeFormatter`, `ResolverStyle`, and `Locale`. Callers should catch `DateTimeParseException` for invalid data and handle `null` inputs per their contract.

If the protocol **strictly** mandates standard ISO format, you can often write concisely:

~~~java
LocalDate date = LocalDate.parse(raw, DateTimeFormatter.ISO_LOCAL_DATE);
~~~

This is an illustrative snippet where `raw` is the input string. `ISO_LOCAL_DATE` has `STRICT` resolution and ISO chronology declared. However, **`STRICT` does not automatically mean "input has only 4 unsigned year digits" under every formatter construction**; width, sign prefixes, and lexical policies belong to the pattern/builder. If an API requires exact byte or character shapes in a narrower form, validate against the protocol contract and build the matching pattern/builder.

### 8.2. Separate calendar validation from business validation

Once you have a valid `LocalDate`, you still need to check:

- Does the date fall within the **supported system range**?
- Does the date violate deadlines, cutoffs, booking windows, or closing dates?
- Is the date a business day, and does it fall on a product-configured holiday?
- Does the user have permission to select this date?
- If date-time is involved, are there time zones, DST gaps/overlaps, or offsets to resolve?

Example:

~~~java
if (date.isBefore(LocalDate.of(2000, 1, 1))
        || date.isAfter(LocalDate.of(2100, 12, 31))) {
    throw new IllegalArgumentException("Date outside supported range");
}
~~~

This is an illustrative snippet assuming `date` already parsed successfully. **ResolverStyle does not replace a business validator**. A calendar-valid `2024-02-29` can still be rejected if it falls outside the contract's allowed date range.

### 8.3. Parsing and formatting are two distinct operations

`DateTimeFormatter.withResolverStyle(...)` affects **parsing** only; it does not alter the date value when the formatter **formats** an already valid `LocalDate`. Meanwhile, `withLocale` changes month names, weekday names, or localized patterns; `withChronology` and `withZone` serve separate roles.

Never call `format(date)` and re-parse the string with `SMART` to "fix" invalid business data. Temporal data should be validated at the input boundary, stored in the appropriate `java.time` type, and formatted only at the presentation layer.

## 9. Edge Cases and Common Mistakes

| Misconception / Error | Consequence | How to Handle It |
| --- | --- | --- |
| Assuming `ofPattern` defaults to `STRICT` | `2023-02-29` can become `2023-02-28` | Call `withResolverStyle(STRICT)` |
| Using `yyyy` with `STRICT` and no era | Even valid dates fail to resolve to `LocalDate` | Use `uuuu` for ISO years or provide `G` |
| Using `LENIENT` for birth dates / contract deadlines | Invalid input silently shifts to another date | Use `STRICT` and report an error |
| Thinking `SMART` fixes any bad month/day | Month 13 or day 32 is still rejected | Understand the chronology's exact SMART rules |
| Thinking `LENIENT` accepts arbitrary text | Lexical pattern mismatches are still rejected | Separate the parse phase from the resolve phase |
| Calling `formatter.withResolverStyle(STRICT)` and ignoring the result | Original formatter remains `SMART` | Reassign or use the returned formatter |
| Confusing `parseStrict` with `ResolverStyle.STRICT` | Wrong phase configured | Choose lexical parsing vs. field resolution properly |
| Catching `DateTimeParseException` and defaulting to `LocalDate.now()` | Bad data is masked, corrupting business state | Report invalid input and ask for correction |
| Assuming STRICT guarantees business validity | Dates may still violate bounds, holidays, or cutoffs | Run domain validation after parsing |
| Treating `SimpleDateFormat` like `DateTimeFormatter` | Different defaults and thread-safety semantics | Prefer `java.time` in new code |
| Changing locale/zone to "fix" an invalid date | Cannot repair nonexistent calendar dates | Check chronology, pattern, and resolver |
| Catching the exception and returning raw internal message to UI | Leaks implementation details, hard to localize | Return an error code and locale-appropriate message |

### 9.1. Single-digit month/day case

With fixed pattern `uuuu-MM-dd`, input `2023-2-9` is rejected even under `LENIENT` in the tested JDK example. To support typing one or two digits, build a formatter whose pattern/builder accepts that input, and **still** apply `STRICT` whenever the domain needs valid dates. Never turn `LENIENT` into a patch for syntax mismatches.

### 9.2. Trailing garbage case

Input `2023-02-29extra` cannot be treated as a complete date merely because it has a prefix matching `uuuu-MM-dd`. `LocalDate.parse(text, formatter)` overloads create date objects and require full-text consumption; let parse failures surface clearly.

If using lower-level APIs with `ParsePosition`, verify that the entire text was consumed. Never accept a string where the parser only read the leading characters and silently ignored the rest.

### 9.3. Time zones, DST, and instants

`ResolverStyle.STRICT` checks calendar fields within the formatter's context, yet **does not verify** that a local `LocalDateTime` maps one-to-one to an `Instant` in a given `ZoneId`. On DST transition days, local wall times can **fail to exist** or **occur twice**.

When the domain validates meeting times, payment timestamps, flight schedules, or regional events, determine the `ZoneId` and handle gaps/overlaps with explicit rules. `ResolverStyle` does not replace checking `ZoneRules`.

### 9.4. What about SimpleDateFormat?

`java.text.SimpleDateFormat` relies on `setLenient(boolean)` backed by `Calendar`, not the three modes of `java.time.ResolverStyle`. In new projects, prefer `java.time` for immutable, thread-safe formatters and explicit parsing semantics. When integrating legacy code, test parsing/normalization behavior directly rather than assuming `SimpleDateFormat.setLenient(false)` matches `ResolverStyle.STRICT` in every detail.

## 10. Essential Testing

A proper test suite for real-world date input should include:

1. **Leap years:** `2024-02-29` valid; `2023-02-29` must be rejected by `STRICT`.
2. **Month ends:** `2023-04-30` valid; `2023-04-31` must be rejected by `STRICT`.
3. **Out-of-range months:** `2023-13-10` and `2023-00-10` must not be silently normalized in APIs expecting absolute dates.
4. **Out-of-range days:** `2023-02-30`, `2023-02-32`, and negative values if the pattern allows them; verify SMART vs. LENIENT distinctions.
5. **Width/syntax:** `2023-2-9`, `2023/02/09`, leading/trailing whitespace, and trailing garbage.
6. **Year and era:** `uuuu` vs. `yyyy` under STRICT; when using eras, test `G`.
7. **Default formatters:** verify `ofPattern` is `SMART` and `ISO_LOCAL_DATE` is `STRICT`.
8. **Locale:** month names follow the requested language, while calendar validity/chronology is explicitly declared.
9. **Business bounds:** dates before/after allowed range, holidays, weekends, cutoffs, and authorization checks.
10. **DST and time zones:** when data is a local date-time, test gaps/overlaps against the relevant `ZoneId`.
11. **Do not alter input:** the app must store **the date confirmed by the user**, never silently shifting deadlines via SMART/LENIENT.
12. **Exceptions:** `DateTimeParseException` maps to an understandable message without leaking stack traces.

In automated tests, assert the exact parsed **`LocalDate`**, not just whether an exception was thrown. Because `SMART` can "succeed" by changing the value, tests must verify the resulting date.

## 11. Practice Exercises

- Test all three modes with `2023-04-31`, explaining why `SMART` yields April 30 while `LENIENT` moves to May 1.
- Test `2024-02-30`: inspect the results in a leap year.
- Replace `uuuu-MM-dd` with `yyyy-MM-dd` while keeping `STRICT`; deduce why it fails even for `2024-02-29`.
- Add the era via `G yyyy-MM-dd` and test `AD 2024-02-29` with `Locale.US`; inspect the returned date.
- Build a formatter using `DateTimeFormatterBuilder` that parses single- or two-digit months flexibly while keeping `ResolverStyle.STRICT`; verify single-digit months are accepted while nonexistent dates are still rejected.
- Compare `DateTimeFormatter.ISO_LOCAL_DATE` against `ofPattern("uuuu-MM-dd").withResolverStyle(STRICT)` on boundary dates and year pattern symbols.
- Write a validator `requireDueDate(String input)` that parses in `STRICT` mode and compares against an injected `LocalDate.now(clock)` for deterministic tests.
- For appointments, test a `LocalDateTime` on a DST transition day in a specific `ZoneId`; distinguish a calendar-date error from an instant not existing in that zone.

## 12. Summary

`ResolverStyle` controls the **resolve phase** of `DateTimeFormatter`, without altering all character-reading rules. For ISO dates:

- **STRICT** accepts only calendar combinations that genuinely exist.
- **SMART** can clamp days past month-end to the last day of that month, while still rejecting completely absurd values.
- **LENIENT** can normalize out-of-range months/days by rolling over, easily producing **a different date from the input**.

For forms requiring a real date matching exactly what the user entered, choose `DateTimeFormatter.ISO_LOCAL_DATE` or `uuuu-MM-dd` with `ResolverStyle.STRICT`, handle errors explicitly, and continue with business-rule validation. Most importantly, remember **`yyyy` is year-of-era and `uuuu` is proleptic year**: under STRICT mode, that difference can decide whether a valid date parses at all.

**References:**

- Java SE 17, `ResolverStyle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html
- Java SE 17, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `DateTimeFormatterBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html
- Java SE 17, `LocalDate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html
- Java SE 17, `DateTimeParseException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeParseException.html
