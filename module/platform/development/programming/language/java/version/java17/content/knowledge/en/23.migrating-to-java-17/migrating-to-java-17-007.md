# Testing Character Encodings, Floating-Point Numbers, Time Zones, and Input Data When Upgrading to Java 17

**Topic:** Java 17  
**Chapter:** Migrating to Java 17  
**Lesson:** Testing character encodings, floating-point numbers, time zones, and input data

When upgrading an application to Java 17, many failures stem not from API removals but from the runtime environment and how the program interprets data. A string may be read under a different charset, a floating-point calculation may yield different results between the old and new runtimes, time zone rules may shift with a newer tzdb, or previously accepted input may now be parsed or validated differently.

Therefore, upgrade testing must go beyond confirming that the application starts and existing unit tests pass. You need deliberate input datasets, pinned controllable environment factors, identical scenario runs on the old runtime and Java 17, and contract-based result comparisons.

Four areas warrant particular attention:

1. **Character encoding:** default charset, UTF-8, Unicode data, invalid byte sequences, and byte-to-String conversions.
2. **Floating-point numbers:** always-strict floating-point semantics from Java 17, binary representation error, boundary values, and financial calculations.
3. **Time zones:** timezone database (tzdb), daylight saving time (DST) regions, skipped or repeated local hours, and default locale/timezone.
4. **Input data:** parsing, Unicode normalization, date/time/number formatting, value ranges, nulls, and malformed input.

This lesson uses current Java 17 APIs such as `StandardCharsets`, `java.time`, `Clock`, `BigDecimal`, `CharsetDecoder`, and explicit `Locale`. The goal is to build repeatable tests across machines that detect real changes affecting users.

## 1. Establish testing principles for a runtime upgrade

Before examining each data category, agree on how comparisons are evaluated. A difference between two runs does not automatically mean Java 17 has a bug. Differences can stem from:

- JDK and standard library versions.
- Operating system or container image.
- Process default charset.
- Default locale and timezone.
- Timezone database version.
- JVM configuration, classpath/module path, or dependencies.
- Non-identical fixture data.

### 1.1. Use identical fixtures on the old runtime and Java 17

Build a fixed fixture set for critical scenarios. For each fixture, record:

- Exact input data (bytes, text, numbers, or timestamps).
- Charset, locale, and timezone settings if applicable.
- Expected result according to the contract.
- Actual result on the old runtime.
- Actual result on Java 17.
- JDK version and execution environment.

Do not regenerate test data with a separate process on each runtime. For example, to compare how a UTF-8 file is read, feed the exact same byte file to both runtimes rather than generating a fresh file using each machine's default charset.

### 1.2. Separate deterministic tests from environment-dependent tests

Deterministic tests should explicitly specify charset, locale, timezone, and clock. For instance:

- Read files using `StandardCharsets.UTF_8`.
- Parse numbers with `Locale.GERMANY`.
- Create points in time from `Instant`.
- Convert times using `ZoneId.of("Asia/Ho_Chi_Minh")`.
- Use `Clock.fixed(...)` for logic depending on the current time.

Environment-dependent tests are still needed if the application intentionally uses machine defaults. Keep them in a separate group and execute them in CI environments representative of production. Never let a test relying on a developer laptop's timezone determine whether business logic is correct.

### 1.3. Compare against contracts, not blindly

Not every byte or decimal digit must match identically in every situation. Choose the right comparison method:

| Data | Appropriate comparison |
|---|---|
| UTF-8 file or protocol | Compare bytes if the contract mandates byte-exactness; if only text is contracted, compare decoded strings |
| Unicode | Compare code points or normalized forms if the contract specifies normalization |
| `double`/`float` | Compare bits, ULPs, or tolerances per calculation requirements |
| Currency | Compare `BigDecimal` per published scale/rounding rules |
| Absolute point in time | Compare `Instant` |
| Local wall-clock time | Compare local date/time and `ZoneId` per contract |
| Input validation | Compare accept/reject outcomes and published error types |

A good test answers "what is guaranteed?" before writing assertions.

## 2. Test charsets and character encodings

A charset maps bytes to characters and back. If a program relies on the default charset without specifying one explicitly, results can vary across operating systems or environment configurations.

### 2.1. Java 17 still has an environment-dependent default charset

A crucial point when upgrading is that **Java 17 does not yet enforce UTF-8 as the universal default charset**. JEP 400 standardized UTF-8 as the default starting in JDK 18. On Java 17, `Charset.defaultCharset()` can still depend on the runtime environment.

Therefore, do not assume a Java 17 application running on Windows, Linux, and containers shares the same default charset. A program may read a file correctly on a developer machine yet garble it on a server if the file encoding and default charset mismatch.

Inspect the environment with:

```java
import java.nio.charset.Charset;

public class CharsetEnvironment {
    public static void main(String[] args) {
        System.out.println("default charset = " + Charset.defaultCharset());
        System.out.println("file.encoding = " + System.getProperty("file.encoding"));
        System.out.println("java.version = " + System.getProperty("java.version"));
        System.out.println("os.name = " + System.getProperty("os.name"));
    }
}
```

This information helps diagnose and document environments. It does not replace specifying charsets in code. Avoid treating `file.encoding` overrides as the application's data contract; read/write APIs should explicitly name the charset they expect.

### 2.2. Always specify charsets for contract-bound data

Several APIs silently fall back to the default charset when none is passed, such as:

```java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
```

And character-stream constructors wrapping byte streams without a charset. Whenever data is exchanged between systems, persisted to disk, or sent over a network, pick the protocol charset and pass it explicitly.

UTF-8 example:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

For files:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");

Files.writeString(path, "Xin chào Việt Nam", StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
```

For protocols mandating UTF-8, both sender and receiver must enforce UTF-8. Never depend on each JVM's default charset.

### 2.3. Locate usages of the default charset

When upgrading a codebase, search for calls omitting a charset, especially:

- `String.getBytes()` with no arguments.
- `new String(byte[])` without a charset.
- `InputStreamReader(InputStream)` without a charset/decoder.
- `OutputStreamWriter(OutputStream)` without a charset/encoder.
- `FileReader` or `FileWriter` constructors without a charset.
- Parsing APIs or third-party libraries using the default charset internally.

Not every defaulted API is wrong. For machine-local data explicitly defined by the host environment, the default may be intentional. However, for config files, machine-parsed logs, CSVs, HTTP payloads, message queues, or integration data, the charset must be part of the contract.

### 2.4. Build Unicode fixtures capable of exposing bugs

ASCII-only fixtures cannot adequately test charsets because most common charsets encode ASCII identically. Include diverse character groups:

| Group | Example | What to verify |
|---|---|---|
| ASCII | `Hello 123` | Baseline case |
| Vietnamese with diacritics | `Tiếng Việt: ắ, ệ, ộ` | Non-ASCII characters |
| Extended Latin | `Ångström`, `Łódź` | Extended character sets |
| CJK | `東京`, `中文` | Non-Latin scripts |
| Emoji/supplementary | `🙂`, `𠜎` | Code points outside the BMP |
| Decomposed forms | `é` vs `e` + combining acute accent | Unicode representation differences |

UTF-8 round-trip test:

```java
import java.nio.charset.StandardCharsets;

String[] samples = {
    "Hello 123",
    "Tiếng Việt: ắ, ệ, ộ",
    "Ångström and Łódź",
    "東京 and 中文",
    "🙂 and 𠜎"
};

for (String sample : samples) {
    byte[] encoded = sample.getBytes(StandardCharsets.UTF_8);
    String decoded = new String(encoded, StandardCharsets.UTF_8);

    if (!sample.equals(decoded)) {
        throw new AssertionError("UTF-8 round-trip failed: " + sample);
    }
}
```

Add tests for file reads/writes, streams, HTTP bodies, and message brokers if your application uses those channels. An in-memory `String` round-trip does not exercise integration boundaries.

### 2.5. Invalid bytes and decoder error policies

A byte stream can contain malformed UTF-8 sequences. If a decoder silently substitutes replacement characters for invalid bytes, the application may accept corrupted data. When strict fidelity is required, configure an explicit error action.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String value = decoder.decode(ByteBuffer.wrap(inputBytes)).toString();
    process(value);
} catch (CharacterCodingException invalidEncoding) {
    rejectInput(invalidEncoding);
}
```

`REPORT` causes the decoder to throw instead of silently altering data. Use `REPLACE` or `IGNORE` only when the contract permits dropping or substituting characters.

Test at least three cases:

- Valid UTF-8 byte sequences.
- Byte sequences truncated mid-character across a multi-byte character.
- Byte sequences with invalid continuation or leading bytes.

### 2.6. Unicode normalization and string comparison

Two strings can look identical visually yet have different code point sequences. For example, `é` can be represented as a single precomposed code point or as `e` followed by a combining acute accent.

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "é";

System.out.println(composed.equals(decomposed)); // false

String normalizedA =
        Normalizer.normalize(composed, Normalizer.Form.NFC);
String normalizedB =
        Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(normalizedA.equals(normalizedB)); // true
```

If an application searches, compares names, or stores text keys, specify the normalization form in the contract. NFC is typically suitable for canonically equivalent text normalization; NFKC also applies compatibility normalization and can collapse meaningful distinctions in certain domains.

Do not normalize every string indiscriminately. Passwords, digital signatures, tokens, protocol identifiers, or opaque payloads may require preserving exact original bytes or code points.

### 2.7. String.length() is not the number of user-perceived characters

In Java, `String.length()` counts UTF-16 code units. A supplementary code point outside the BMP takes two code units. A user-perceived character can also consist of multiple code points, such as an emoji with modifiers or ZWJ sequences.

If a business rule states "maximum 20 characters," define clearly whether that means:

- 20 UTF-16 code units.
- 20 Unicode code points.
- 20 grapheme clusters (closest to user-perceived characters).

Counting code points:

```java
int codePoints = value.codePointCount(0, value.length());
```

This is still not a grapheme cluster counter. If length limits matter to users, apply appropriate Unicode segmentation rules and test with combining marks, emoji, and non-BMP characters.

## 3. Test floating-point numbers when upgrading to Java 17

Java 17 introduces a notable language/runtime change regarding floating-point arithmetic: JEP 306 restores **always-strict floating-point** semantics. From Java 17 onward, all floating-point expressions are evaluated under Java's strict semantics; the `strictfp` modifier is no longer needed to request this behavior.

This is particularly worth testing if the application previously ran on older JDKs and depended on floating-point results on platforms that could use extended exponent value sets. On many modern systems results may not change, yet during an upgrade you should verify with tests rather than assuming.

### 3.1. What always-strict means

Prior to Java 17, Java defined floating-point value sets that allowed non-strict expressions to use extended exponent ranges on certain architectures. That could cause intermediate results to differ across platforms.

Since Java 17, floating-point expressions always follow strict semantics. The goal is more consistent arithmetic behavior across platforms. `strictfp` may still appear in legacy source, though it is no longer required to enforce strict semantics.

Distinguish two facts:

- Always-strict governs how floating-point operations are evaluated under Java's rules.
- It does **not** make `float` or `double` represent every decimal fraction exactly, nor does it guarantee every math library function produces bit-for-bit identical results on every JVM.

`float` and `double` remain binary IEEE 754 floating-point numbers. Binary rounding errors on decimal fractions still occur.

### 3.2. Test decimals that cannot be represented exactly in binary

A familiar example:

```java
double value = 0.1 + 0.2;

System.out.println(value);          // typically prints 0.30000000000000004
System.out.println(value == 0.3);   // false
```

This is not a Java 17 bug. `0.1` and `0.2` have no exact finite binary representation, so addition exhibits rounding error.

Avoid writing tests like:

```java
assert 0.1 + 0.2 == 0.3;
```

when testing general floating-point outcomes. Choose a comparison criterion aligned with business precision requirements.

### 3.3. Tolerance-based comparison

For approximate calculations, combine absolute and relative tolerances:

```java
static boolean nearlyEqual(
        double actual,
        double expected,
        double absoluteTolerance,
        double relativeTolerance) {

    if (Double.doubleToLongBits(actual)
            == Double.doubleToLongBits(expected)) {
        return true;
    }

    if (Double.isNaN(actual) || Double.isNaN(expected)) {
        return false;
    }

    double difference = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(actual), Math.abs(expected));

    return difference <= Math.max(
            absoluteTolerance,
            relativeTolerance * scale
    );
}
```

No single tolerance fits every problem. For example:

- Graphics may accept small relative tolerances.
- Scientific computing derives tolerances from numerical stability and algorithm error bounds.
- Monetary systems must never use tolerances to hide representation error; use a proper decimal type instead.
- Algorithms requiring exact bit reproducibility must verify exact bit patterns and runtime conditions.

For upgrade tests, document the chosen tolerance and its rationale. Do not widen tolerances just to make a test pass without understanding why results changed.

### 3.4. Compare bit patterns when contracts require exactness

You can inspect the bit representation of a `double`:

```java
long bits = Double.doubleToRawLongBits(value);
System.out.printf("0x%016X%n", bits);
```

Use `doubleToRawLongBits` when distinguishing exact bit patterns, including NaN payloads. `Double.doubleToLongBits` canonicalizes NaNs into one canonical bit pattern, so the two methods behave differently in bit-level tests.

Bit comparison fits when:

- Verifying an algorithm with a bit-exact specification.
- Verifying numeric values serialized under a binary contract.
- Detecting rounding shifts in a deterministic pipeline.

Avoid bit equality for general floating-point tests. If the contract only requires accuracy within bounds, use tolerance or ULPs.

### 3.5. Boundary values to test

A floating-point test suite should cover:

| Case | Example | What to confirm |
|---|---|---|
| Normal finite numbers | `1.25`, `-3.5` | Baseline outcomes |
| Very small values | `Double.MIN_VALUE` | Subnormals and underflow |
| Smallest normal value | `Double.MIN_NORMAL` | Normal/subnormal boundary |
| Very large values | `Double.MAX_VALUE` | Overflow during computation |
| Positive/negative infinity | `POSITIVE_INFINITY`, `NEGATIVE_INFINITY` | Propagation rules |
| NaN | `Double.NaN` | Comparisons and NaN checks |
| Signed zero | `0.0`, `-0.0` | Sign bit distinction |
| Values near rounding midpoints | Midpoint boundary values | Rounding behavior |
| Accumulated values | Long running sums | Error accumulation |

Sample assertions:

```java
assert Double.isNaN(Double.NaN);
assert Double.isInfinite(1.0 / 0.0);
assert Double.doubleToRawLongBits(0.0)
        != Double.doubleToRawLongBits(-0.0);
assert Double.compare(-0.0, 0.0) < 0;
```

Note that `0.0 == -0.0` evaluates to true, yet the two values carry distinct sign bits and can produce different results in operations like division. `NaN` does not equal itself under `==`; use `Double.isNaN()` to test for it.

### 3.6. Test overflow, underflow, and error accumulation

Example:

```java
double overflow = Double.MAX_VALUE * 2.0;
double underflow = Double.MIN_VALUE / 2.0;

System.out.println(overflow);  // Infinity
System.out.println(underflow); // may become 0.0
```

Tests must verify how the application handles these outcomes. If large inputs can produce infinity that then gets written to a database or JSON, clearly specify whether it is accepted or rejected.

When summing multiple values, summation order can change results because floating-point addition is not strictly associative:

```java
double a = (1e16 + -1e16) + 1.0;
double b = 1e16 + (-1e16 + 1.0);

System.out.println(a); // 1.0
System.out.println(b); // may be 0.0
```

If an upgrade also changes collection iteration order or processing order, sums can shift even though every individual operation follows the exact same strict rules. Test both algorithms and data ordering.

### 3.7. Distinguish Math and StrictMath

Always-strict does not mean every method on `Math` returns the same bit pattern on every platform. For several transcendental functions, Java allows implementations within specified error bounds.

`StrictMath` provides specified functions with stricter cross-platform reproducibility guarantees. If an application requires consistent math function outputs across platforms per the API contract, evaluate `StrictMath` and test accordingly.

Do not blindly replace all `Math` calls with `StrictMath`. Weigh reproducibility requirements, performance, and accuracy per algorithm.

### 3.8. Use BigDecimal for currency and decimal arithmetic

When a domain handles prices, taxes, balances, or financial rates needing exact decimal rules, use `BigDecimal` rather than `double`.

Avoid constructing `BigDecimal` directly from `double`:

```java
BigDecimal wrong = new BigDecimal(0.1);
BigDecimal intended = new BigDecimal("0.1");
BigDecimal alsoUseful = BigDecimal.valueOf(0.1);
```

`new BigDecimal(0.1)` represents the exact rounded binary `double` value, yielding more decimal digits than expected. Use decimal strings or `BigDecimal.valueOf` when converting from the canonical decimal representation of a `double`.

Decimal division may have non-terminating results:

```java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        2,
        RoundingMode.HALF_UP
);
```

Explicitly specify scale and `RoundingMode`. Never leave monetary rules to implicit defaults.

### 3.9. BigDecimal equals() vs. compareTo()

`BigDecimal.equals()` compares both value and scale:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b));    // 0
```

When contracts compare numeric values, `compareTo() == 0` is usually intended. When scale itself carries meaning—such as stored decimal precision conventions—verify scale explicitly.

During upgrades, audit code using `BigDecimal` as keys in `HashMap`/`HashSet`, since `equals()` and `hashCode()` distinguish scale.

### 3.10. JEP 306 and the strictfp modifier

JEP 306 takes effect in Java 17 and restores always-strict floating-point semantics. Legacy source code may still contain `strictfp`; the Java 17 compiler may warn that the modifier is no longer necessary.

Do not add `strictfp` to new code to "fix" discrepancies. Re-test critical floating-point calculations on Java 17, especially if the application runs across multiple architectures or previously relied on extended precision. Official references are JEP 306 and JLS 17.

## 4. Test time zones and the timezone database

A time zone is more than a fixed offset from UTC. Regions such as `Europe/Paris` or `America/New_York` carry historical and future transition rules, including statutory DST changes. These rules ship with the JDK as the timezone database (tzdb) and can be updated between JDK releases.

When upgrading to Java 17, the same `LocalDateTime` and `ZoneId` can resolve to a different offset or instant if newer tzdb data reflects updated rules. This is why you should test historical dates, current dates, and future scheduled dates.

### 4.1. Distinguish Instant, LocalDateTime, OffsetDateTime, and ZonedDateTime

Types in `java.time` model distinct concepts:

| Type | Meaning | When to use |
|---|---|---|
| `Instant` | An absolute point on the UTC timeline | Event logs, creation timestamps, wire timestamps |
| `LocalDateTime` | Wall-clock date and time without zone/offset | Store opening hours or unzoned appointments |
| `OffsetDateTime` | Date and time with a fixed offset, e.g., +07:00 | Protocols requiring the offset at send time |
| `ZonedDateTime` | Date and time governed by a `ZoneId`'s rules | Regional schedules, DST, and local rules |

Do not replace a timezone region with a fixed offset if business rules depend on regional calendar rules. For instance, `Asia/Ho_Chi_Minh` is a zone with an ID and rule history; `+07:00` is purely a fixed offset.

For past events, storing `Instant` is usually appropriate. For future appointments defined in local wall-clock time, you generally need both the local date/time and zone ID, plus a gap/overlap resolution policy.

### 4.2. Why can tzdb updates change results?

Governments can change DST start/end dates, standard offsets, or regional rules. JDK updates can bundle newer tzdb releases. Therefore:

```java
ZoneId zone = ZoneId.of("Region/City");
LocalDateTime local = LocalDateTime.of(2030, 4, 1, 9, 0);

ZonedDateTime resolved = local.atZone(zone);
System.out.println(resolved);
System.out.println(resolved.toInstant());
```

Identical code and input can produce different outputs between two tzdb releases if a region's rules changed. That may be an accurate data update reflecting new legislation rather than a Java regression.

### 4.3. Record active tzdb versions

Java provides `ZoneRulesProvider.getVersions(zoneId)` to inspect available rule versions for a zone:

```java
import java.time.ZoneId;
import java.time.zone.ZoneRulesProvider;

String zoneId = "Europe/Paris";

var versions = ZoneRulesProvider.getVersions(zoneId);
System.out.println("tzdb versions = " + versions.keySet());
```

When investigating discrepancies between environments, record both the JDK version and rule versions for critical zones. This separates code changes from tzdb updates.

Never hard-code a tzdb version inside business logic. Version inspection exists for diagnostics and test reproducibility, while timezone data updates follow your system's deployment policy.

### 4.4. Test DST gaps: non-existent local times

When clocks spring forward to daylight saving time, a range of local times is skipped. For instance, in a DST zone, clocks may jump from 01:59 directly to 03:00; 02:30 does not exist on that transition day.

Check using `ZoneRules.getValidOffsets`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

ZoneId zone = ZoneId.of("Europe/Paris");
ZoneRules rules = zone.getRules();

LocalDateTime local =
        LocalDateTime.of(2024, 3, 31, 2, 30);

var offsets = rules.getValidOffsets(local);

System.out.println(offsets); // empty list if local time falls in a gap
```

During a gap, the valid offset list is empty. `ZonedDateTime.of` or `LocalDateTime.atZone` adjusts by pushing the local time forward past the gap. Applications must decide whether that is the intended business behavior or whether the input should be rejected.

Do not let API defaults accidentally dictate scheduling policy. If a user enters a non-existent time, the system might:

- Reject it and prompt for another time.
- Shift to the next valid time under a documented policy.
- Retain the input and ask for confirmation of the adjustment.

### 4.5. Test DST overlaps: local times occurring twice

When clocks fall back, a range of local times occurs twice with two distinct offsets. During an overlap, `getValidOffsets` normally returns two valid offsets:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local =
        LocalDateTime.of(2024, 10, 27, 2, 30);

var offsets = zone.getRules().getValidOffsets(local);

System.out.println(offsets); // two offsets for the two occurrences of 02:30
```

These two occurrences of 02:30 correspond to two distinct instants. Storing only `LocalDateTime` is ambiguous for identifying a unique instant.

You can select an offset explicitly:

```java
ZonedDateTime earlier =
        ZonedDateTime.ofLocal(local, zone, null)
                .withEarlierOffsetAtOverlap();

ZonedDateTime later =
        ZonedDateTime.ofLocal(local, zone, null)
                .withLaterOffsetAtOverlap();

System.out.println(earlier.toInstant());
System.out.println(later.toInstant());
```

Tests must verify which occurrence the system picks, or that it rejects the ambiguity for user confirmation. Do not assert only formatted display strings, since both results can print "02:30" while having different offsets and instants.

### 4.6. Test time arithmetic across DST transitions

`Duration` models elapsed timeline seconds; `Period` models calendar units. On a `ZonedDateTime`, adding one calendar day can differ from adding 24 elapsed hours.

Example:

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris")
);

ZonedDateTime calendarDay = start.plusDays(1);
ZonedDateTime elapsed24Hours = start.plus(Duration.ofHours(24));

System.out.println(calendarDay);
System.out.println(elapsed24Hours);
```

Across a DST transition, `plusDays(1)` preserves the local wall-clock time on the calendar, whereas `plus(Duration.ofHours(24))` adds 24 physical hours. The two outcomes can differ by one hour.

Clarify the business requirement:

- "Tomorrow at 12:00 local time" is usually a calendar operation.
- "Exactly 24 hours later" is an elapsed-duration operation.
- "In 15 minutes" should measure timeline elapsed time, typically using `Duration`.

### 4.7. Never rely on the default timezone in business logic

`ZoneId.systemDefault()` reads the environment's default timezone. It can differ across developer machines, CI runners, containers, and production nodes.

When business logic belongs to a specific region, pass an explicit `ZoneId`:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime localBusinessTime =
        instant.atZone(businessZone);
```

If an application genuinely must use the machine's default timezone, inspect the setting at startup and log it. Never let unit tests depend accidentally on the runner's local timezone.

You can run CI tests under a fixed timezone:

```bash
java -Duser.timezone=UTC -jar app-tests.jar
```

Then run an additional job configured with production or supported user timezones. Testing UTC does not replace testing DST; it merely gives a deterministic baseline.

### 4.8. Use Clock to test time-dependent logic

Avoid calling `Instant.now()` or `LocalDate.now()` directly inside business logic that needs deterministic tests. Inject a `Clock`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.fixed(
        Instant.parse("2024-06-01T10:15:30Z"),
        ZoneId.of("UTC")
);

LocalDate today = LocalDate.now(clock);
```

Production can inject `Clock.system(zone)` or `Clock.systemUTC()`; tests inject `Clock.fixed` for reproducible timestamps. `Clock.offset` can verify logic before and after elapsed intervals without waiting on real wall-clock time.

### 4.9. Test future schedules and rule changes

For future scheduled events, decide what the system preserves if tzdb rules change:

- Preserve the committed `Instant`, even if displayed local time shifts.
- Preserve the local wall-clock time in the zone and recompute the instant under updated rules.
- Store both the committed instant and the zone/local intent so differences can be explained or confirmed.

No single choice fits every product. Airline flights, recurring meetings, broadcast schedules, and store opening hours each have different requirements.

Upgrade tests should include fixtures for future appointments in regions with rule changes, verifying that the application's chosen policy holds consistently.

## 5. Test input data, parsing, and validation

JDK upgrades can expose hidden assumptions in how applications read, convert, and validate inputs. Test valid inputs, boundary inputs, and malformed inputs, especially wherever logic touches locale, Unicode, charsets, or default timezones.

### 5.1. Distinguish parsing from validation

Parsing converts raw representations into program data types. Validation verifies whether the parsed value satisfies business rules.

For example, with currency: `"1.234,50"` is parsed under the appropriate locale into a decimal number, then validated as non-negative, within bounds, and within accepted scale. Merging all three steps into a default parse call risks misreading decimal separators or accepting trailing garbage.

### 5.2. Locale affects number and date formats

Never rely on `Locale.getDefault()` to parse fixed-format protocols or files. Default locales vary across developer laptops, CI, and production.

| Locale | Display example |
|---|---|
| `Locale.US` | `1,234.50` |
| `Locale.GERMANY` | `1.234,50` |
| `Locale.FRANCE` | `1 234,50` |

When input follows an application-defined format, specify an explicit locale. When input reflects a user's regional formatting, obtain the locale explicitly from the request context or user profile.

### 5.3. Parse locale-formatted numbers and verify full consumption

`NumberFormat.parse` can parse a prefix of a string and stop before trailing characters. When an input must contain strictly one number, check that the parse position consumed the entire string.

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
DecimalFormat decimalFormat = (DecimalFormat) format;
decimalFormat.setParseBigDecimal(true);

String input = "1.234,50";
ParsePosition position = new ParsePosition(0);
Number parsed = decimalFormat.parse(input, position);

if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid numeric input");
}

BigDecimal amount = (BigDecimal) parsed;
```

Test valid locale formatting, separators from a different locale, trailing characters, leading/trailing spaces, minus signs, exponents, invalid digit grouping, empty strings, and whitespace-only strings. Never use display-locale parsers for machine-to-machine protocols with fixed grammars.

### 5.4. Parse dates with explicit, strict formatters

For fixed date formats, specify pattern, locale, and resolver style. Use `uuuu` for calendar year when strict date parsing is required:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("2024-02-29", formatter);
```

Test both valid and invalid leap dates: `2024-02-29` is valid; `2023-02-29`, `2024-13-01`, and `2024-04-31` are invalid. Strings missing digits or containing trailing characters must be rejected per contract.

If using a locale-sensitive formatter, pass the locale explicitly and test across supported product locales. Never let parsing behavior drift with `Locale.getDefault()`.

### 5.5. Test Unicode whitespace and trimming rules

`String.trim()` and `String.strip()` follow different rules. `strip()` delegates to `Character.isWhitespace` and handles a broader set of Unicode whitespace characters. Still, not every space-like character is treated as whitespace by `Character.isWhitespace`; certain non-breaking spaces are classified differently.

If an API strips leading/trailing whitespace, define the exact set of trimmed code points. Never replace `trim()` with `strip()` without testing.

```java
String input = "  hello  ";
String asciiTrimmed = input.trim();
String unicodeStripped = input.strip();
```

Test suites should cover tabs, line separators, em spaces, non-breaking spaces, and any whitespace your product chooses to handle. For identifiers or passwords, automatic stripping can alter credentials; establish an explicit contract before applying it.

### 5.6. Length, code points, and displayed characters

When validation caps string length, define the unit of measurement. `String.length()` counts UTF-16 code units, not code points or grapheme clusters.

```java
String basic = "A";
String supplementary = "🙂";
String combined = "é";

System.out.println(basic.length());          // 1
System.out.println(supplementary.length());  // 2 UTF-16 code units
System.out.println(combined.length());       // 2 code units
System.out.println(
        supplementary.codePointCount(0, supplementary.length())
); // 1 code point
```

If the product limits visible user characters, count grapheme clusters per Unicode text segmentation. Never equate `codePointCount` with "number of visible characters."

### 5.7. Test surrogates and malformed Unicode data

A Java `String` can hold unpaired surrogates even though it is not valid Unicode scalar values. When encoding to a charset, an encoder may replace or throw depending on configuration.

If data from parsers, files, or APIs can contain unusual strings, decide whether to accept and preserve UTF-16 code units, reject unpaired surrogates, or replace them per a documented policy. Where output integrity is critical, use `CharsetEncoder` with `CodingErrorAction.REPORT` to catch unencodable sequences instead of silent replacement.

### 5.8. Numeric validation and type boundaries

During an upgrade, test numeric type bounds and conversions:

- Minimum and maximum values of `int` and `long`.
- Out-of-range values during parsing.
- Strings with `+`/`-` signs, leading zeros, or exponents.
- Data loss when narrowing `long` to `int`.
- Rounding or truncation when converting `BigDecimal` to integers.
- `NaN` and infinity if inputs are floating-point.

```java
int value = Integer.parseInt(input);

if (value < 0 || value > 1000) {
    throw new IllegalArgumentException("Value out of range");
}

long source = 3_000_000_000L;
int converted = Math.toIntExact(source); // ArithmeticException
```

`Math.toIntExact` catches overflow rather than silently truncating via a cast. Test exact boundaries, just outside boundaries, empty strings, whitespace, non-ASCII Unicode digits, and strings with trailing tokens.

### 5.9. Locale affects output formatting

Not only parsing, but formatting can also shift with the default locale. For instance, `String.format("%,d", value)` uses the JVM's default locale.

For protocols, machine-read logs, canonical CSVs, or stable snapshots, specify the locale explicitly:

```java
String stable = String.format(Locale.ROOT, "%,.2f", 1234.5);
```

For user-facing display, pass the user's locale intentionally. Do not assert default-locale formatted strings across machines as if they were invariant business data.

## 6. Regression test suite for Java 17

Organize tests into independent groups so failures isolate root causes quickly.

| Group | Fixture | Key checks |
|---|---|---|
| Charset | Vietnamese UTF-8, CJK, emoji | Round-trip and byte output |
| Invalid charset | Invalid UTF-8 byte sequences | Decoder reports or replaces per policy |
| Unicode | NFC/NFD, combining marks, supplementary code points | Comparison and length limits |
| Default charset | Windows/Linux/containers | Log defaults; verify code has no unintended reliance |
| Floating-point | 0.1 + 0.2, rounding, overflow, underflow | Error bounds and always-strict behavior |
| Special floats | NaN, infinity, signed zero, subnormals | Branch handling and serialization |
| Decimal | BigDecimal scale, division, rounding | Monetary outcomes |
| Timezone | UTC, Asia/Ho_Chi_Minh, DST zones | Instant and local wall-clock times |
| DST gap/overlap | Non-existent or repeated local hours | Rejection/adjustment and offset choice |
| tzdb | Historical and future rules | Detect timezone data shifts |
| Locale | US, Germany, France | Number and date parsing/formatting |
| Input boundaries | Min/max, null, empty, trailing tokens | Validation and controlled errors |

### 6.1. Run tests across multiple default environments

If the application relies on default locale, timezone, or charset anywhere, run an intentional CI matrix:

- Linux/containers with a UTF-8 locale.
- Windows if the product supports it.
- US locale and a locale with comma decimal separators.
- UTC timezone and production timezone.
- Current supported old Java runtime and Java 17.

Each job should log its environment properties:

```java
System.out.println("charset=" + Charset.defaultCharset());
System.out.println("locale=" + Locale.getDefault());
System.out.println("zone=" + ZoneId.systemDefault());
System.out.println("runtime=" + Runtime.version());
```

Use this output to explain differences. Do not rely on a single job if production spans multiple OS flavors or container images.

### 6.2. Separate environment-dependent tests from business logic tests

A solid strategy maintains two groups:

- **Deterministic tests:** pass explicit charset, locale, zone, and clock; identical fixtures must yield identical results per contract.
- **Environment integration tests:** verify the application runs cleanly under real machine configurations and log which defaults are selected.

Do not mix everything into one environment-sensitive suite, or unrelated tests will break whenever CI changes its locale or timezone.

### 6.3. Use controlled golden fixtures

For critical data, store fixtures as bytes or explicitly encoded text—for example, UTF-8 files with Vietnamese/emoji characters, numeric payloads with a defined locale, UTC timestamps and local appointments with zone IDs, floating-point values with expected tolerances/bit patterns, and valid/invalid parser inputs.

For text fixtures, document the encoding alongside the test. Avoid creating fixtures with editors that silently convert encodings without verifying raw bytes.

### 6.4. Test on both the old runtime and Java 17

During migration, run the exact same fixture suite on the supported old runtime, on Java 17 with matching OS/containers and dependencies wherever possible, and on any additional production platforms.

Classify every discrepancy:

- **Expected runtime change:** such as always-strict floating-point semantics in Java 17.
- **Environment difference:** differing charset, locale, timezone, or tzdb.
- **Application regression:** new code or dependencies broke contracted behavior.
- **Existing defect exposed:** new tests uncovered a flawed pre-existing assumption.

Never alter expected outputs to mask a discrepancy before determining which category it falls into.

## 7. Example: fixing time in a test

An expiration date calculator can accept `Clock` and `ZoneId` instead of reading the system clock or default timezone directly:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

final class ExpiryPolicy {
    private final Clock clock;
    private final ZoneId businessZone;

    ExpiryPolicy(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    LocalDate expiryDate(int validDays) {
        return LocalDate.now(clock.withZone(businessZone))
                .plusDays(validDays);
    }
}
```

Tests can pin the instant:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2024-06-01T23:30:00Z"),
        ZoneOffset.UTC
);

ExpiryPolicy policy = new ExpiryPolicy(
        fixed,
        ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate expiry = policy.expiryDate(7);
```

Because the instant is 23:30 UTC, the calendar date in Ho Chi Minh City has already rolled over to the next day. This test verifies that the date logic uses the business timezone rather than the CI runner's arbitrary timezone.

## 8. Common upgrade pitfalls

1. **Assuming Java 17 defaults to UTF-8:** default charset remains environment-dependent; UTF-8 became the standardized default in Java 18.
2. **Testing with ASCII only:** include Vietnamese diacritics, CJK, emoji, and decomposed Unicode strings.
3. **Silently replacing invalid bytes:** for inputs requiring fidelity, configure `REPORT` and test malformed sequences.
4. **Assuming always-strict makes decimal fractions exact:** JEP 306 does not change the binary representation of `float`/`double`.
5. **Using exact equality on all doubles:** define tolerance/ULPs and test NaN, infinity, and signed zero separately.
6. **Using double for currency:** use `BigDecimal`, explicitly specifying scale and rounding at business steps.
7. **Treating an offset as a timezone:** fixed offsets carry no history or DST rules; use `ZoneId` for regional schedules.
8. **Assuming every day is 24 hours:** distinguish `Period`/calendar days from `Duration`/elapsed hours.
9. **Using the default timezone in tests:** inject `Clock.fixed` and explicit `ZoneId`.
10. **Parsing numbers/dates with the default Locale:** pass contract-specified locales and formatters.
11. **Using String.length() as visible character count:** clarify whether limits apply to code units, code points, or grapheme clusters.
12. **Testing only the happy path:** write negative tests for malformed inputs, out-of-range values, nulls, trailing characters, and DST transition days.

## 9. Checklist before moving production to Java 17

- [ ] Audited all byte read/write sites omitting an explicit charset.
- [ ] Specified UTF-8 or the contracted charset for files and protocols.
- [ ] Added Unicode fixtures with Vietnamese, CJK, emoji, and normalization cases.
- [ ] Added decoder tests with malformed byte sequences.
- [ ] Recorded the default charset in every supported environment.
- [ ] Tested floating-point calculations on Java 17, including rounding and boundary values.
- [ ] Reviewed algorithms previously relying on extended precision or `strictfp`.
- [ ] Used `BigDecimal` for decimals requiring explicit financial rules.
- [ ] Defined tolerance/ULP or bit-level expectations per calculation group.
- [ ] Verified `NaN`, infinity, signed zero, overflow, and underflow.
- [ ] Used `Instant` for absolute timestamps and `ZoneId` for regional schedules.
- [ ] Tested DST gaps and overlaps for DST-observing zones.
- [ ] Recorded tzdb versions when investigating discrepancies.
- [ ] Injected replaceable `Clock` instances into time-dependent logic.
- [ ] Specified locales explicitly for contract parsing and formatting.
- [ ] Tested valid, invalid, boundary, and Unicode whitespace inputs.
- [ ] Executed identical fixtures on both the old runtime and Java 17 before signing off.

## 10. Practice exercises

### Exercise 1. Default charset

An application running Java 17 on Windows reads a UTF-8 file using a constructor with no charset. On Linux the file reads properly, while on Windows garbled characters appear.

**Answer:** The two environments may have different default charsets. Pass `StandardCharsets.UTF_8` when reading the file and test with the exact same byte fixture.

### Exercise 2. Java 17 and floating-point arithmetic

A test asserting `0.1 + 0.2 == 0.3` fails on both Java 17 and the old runtime.

**Answer:** This is a property of binary floating-point representation, not specific to JEP 306. Use an appropriate tolerance or a decimal type such as `BigDecimal` if the domain requires exact decimal arithmetic.

### Exercise 3. Always-strict

Why re-test floating-point algorithms when upgrading to Java 17 even if the code has not changed?

**Answer:** Java 17 restores always-strict floating-point semantics. Applications that previously relied on extended exponent value sets on older platforms may observe differences in intermediate results.

### Exercise 4. BigDecimal

Are `new BigDecimal(0.1)` and `new BigDecimal("0.1")` identical?

**Answer:** No. The `double` constructor preserves the exact rounded binary value of the `double`; the `String` constructor creates the exact decimal value 0.1 from the input text.

### Exercise 5. DST gap

A user schedules an appointment at 02:30 on a day when clocks jump from 02:00 to 03:00.

**Answer:** That local time does not exist in that zone. Use `ZoneRules.getValidOffsets()` to detect the gap and enforce a policy to reject, adjust, or request confirmation.

### Exercise 6. DST overlap

A user schedules 02:30 on a day when clocks fall back and that hour occurs twice.

**Answer:** Two valid offsets/instants exist. The application must select the earlier occurrence, select the later occurrence, or ask the user to disambiguate.

### Exercise 7. A calendar day vs. 24 hours

A job must run every day at 09:00 local time. Should the schedule be modeled with `Duration.ofHours(24)` or calendar day arithmetic?

**Answer:** Local wall-clock schedules require calendar arithmetic with `ZoneId`, because a DST transition day may not be 24 hours long. `Duration` models elapsed physical time.

### Exercise 8. Locale parsing

The string `1.234,50` is sent in German format while the server runs under `Locale.US`.

**Answer:** Parse using the contracted or data-context locale rather than `Locale.getDefault()`. Verify that the parser consumed the entire string.

### Exercise 9. String length

An emoji has `String.length()` equal to 2. Does that mean the user sees two characters?

**Answer:** No. It may be a single Unicode code point encoded as two UTF-16 code units. A grapheme cluster is yet another distinct unit.

### Exercise 10. Designing an upgrade test

You need to compare the old application and Java 17, but date/time results differ on CI.

**Answer:** Record JDK, tzdb, timezone, and locale; run identical fixtures; pin `Clock` and `ZoneId`; determine whether the difference originates from rule data or code.

## 11. Official documentation references

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change in JDK 18, helpful for distinguishing Java 17 from newer JDKs.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): floating-point semantics change applied in Java 17.
- [JDK 17 API — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): default charset and character encoding APIs.
- [JDK 17 API — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): handling malformed/unmappable input.
- [JDK 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimals, scale, and rounding.
- [JDK 17 API — java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): modern date and time types.
- [JDK 17 API — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offsets, transitions, gaps, and overlaps.
- [JDK 17 API — ZoneRulesProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRulesProvider.html): providing and inspecting timezone rule versions.
- [JDK 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): substitutable clock for testing time logic.
- [JDK 17 API — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locales and language/region formatting rules.
- [JDK 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.

**Key takeaway:** When upgrading to Java 17, test charsets because UTF-8 is not yet universally defaulted across environments; test floating-point numbers because JEP 306 makes all operations always-strict; test timezones because tzdb can change across JDKs; and test parsing/validation with locales, Unicode, and boundary inputs. Use explicit charsets, locales, zones, and clocks for deterministic tests, then run integration tests in production-representative environments.
