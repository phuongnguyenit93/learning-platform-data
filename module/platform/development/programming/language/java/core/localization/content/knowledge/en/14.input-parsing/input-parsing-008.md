# Machine-Readable Conventions for Files, APIs, and Stored Data in Java

Localized applications deal with **two different worlds**: human-facing text formatted/parsed by `Locale`, and machine-facing data transmitted or stored under a **stable format contract**. A user in Germany may enter `1.234,50`; a user in the United States sees `1,234.50`. However, APIs, interchange files, and stored records must never depend on the running host's `Locale.getDefault()` to decide what a number means.

**Principle:** *User interfaces localize data for people; interchange and storage boundaries must use explicitly defined data types, encodings, syntax, and validation rules.* In Java 17+, this typically means: decimals use `BigDecimal` and contract-defined decimal representations; pure calendar dates use ISO `yyyy-MM-dd`; instants use UTC `Instant` or explicit-offset strings; locales use BCP 47 tags like `vi-VN`; files and APIs use UTF-8 and format-appropriate parsers.

This lesson focuses on **machine-readable conventions**: how to produce, read, validate, and convert data safely across *file → application → API → database* boundaries, rather than translating UI labels.

## 1. Why Display Formats Must Never Be Used for Transmission or Storage

Consider the same value one thousand two hundred thirty-four point five:

| Context | Illustrative Representation | Characteristics |
| --- | --- | --- |
| `en-US` UI | `1,234.50` | Comma grouping separator, dot decimal separator |
| `de-DE` UI | `1.234,50` | Dot grouping separator, comma decimal separator |
| `vi-VN` UI | May use grouping/decimal symbols per JDK locale data | Output depends on locale/provider |
| Recommended contract-based text decimal | `1234.50` | No grouping, ASCII dot, unambiguous digits |
| Database `DECIMAL`/`NUMERIC` column | Typed decimal value | Not a locale-formatted string |
| JSON number | `1234.50` | JSON numeric syntax; precision depends on consumer |
| JSON string carrying exact decimal | `"1234.50"` | Requires contract stating it parses as decimal |

If you write `"1.234,50"` directly into a CSV file and another service calls `Double.parseDouble`, parsing fails or misinterprets the number. If a server calls `NumberFormat.getInstance()` without a locale, behavior varies with the host machine's configuration.

### Two Axes to Separate

1. **Data semantics:** monetary decimal, ratio, integer count, calendar date, timestamp, locale code, customer ID.
2. **Boundary representation:** JSON number vs. string, ISO string, SQL `DECIMAL` column, UTF-8 bytes, CSV delimiter, time zone, nullability convention.

A `Locale` only governs regional naming, formatting, and reading conventions; it **does not define** an entire interchange protocol or storage schema. Start from the **data contract** rather than starting from `NumberFormat`.

## 2. Choose Internal Model Types Before Choosing External Strings

Java provides well-suited types for common domain concepts:

| Semantics | Recommended Java Type | Common Interchange Representation |
| --- | --- | --- |
| Integer quantity | `int`, `long`, `BigInteger` depending on range | JSON integer, integer column, digit string if needed |
| Exact decimal, money | `BigDecimal` | Contracted JSON decimal string or JSON number within compatible limits |
| Approximate measurement | `double` | Finite JSON number with clear error/precision contract |
| Date without time | `LocalDate` | `2026-10-28` (ISO calendar date) |
| Time without date or zone | `LocalTime` | `14:30:00` per agreed rules |
| Absolute instant | `Instant` | `2026-10-28T03:30:00Z` |
| Date-time with offset | `OffsetDateTime` | `2026-10-28T10:30:00+07:00` |
| Local wall-clock time + zone | `ZonedDateTime` or pair of `LocalDateTime` and `ZoneId` | Transmit local time, zone ID, and DST policy if business semantics require |
| User language/region | `Locale` | BCP 47 tag, e.g., `en-US` |
| Identifier with leading zeros | `String` | `"001234"`, never coerce to a number |

**Do not choose `double` for everything just because an API accepts numbers.** Financial decimals require decimal exactness and auditable rounding rules. **Do not choose `Date`/`Instant` for a birth date** when the meaning is strictly a calendar date: turning a date into a timestamp can shift the day across time zones.

In-memory types and wire types must have an **explicit mapping**, never relying on an arbitrary object's `toString()` as a permanent contract.

## 3. Machine-Readable Decimals: No Grouping, Explicit Decimal Point

For an application-defined string decimal field, a clean contract might require:

- ASCII digits `0–9` only; ASCII minus `-` if negative values are permitted.
- Decimal separator **`.`**, never a comma.
- No grouping symbols such as `,`, whitespace, grouping dots, or locale-specific separators.
- No currency signs, percent signs, arbitrary whitespace, `NaN`, or `Infinity`.
- Explicit decisions on whether exponent `E`, leading zeros, `+` sign, negative `-0`, and maximum digit counts are allowed.

One **application-chosen** grammar (not the sole grammar of all protocols) is:

```text
decimal := "-"? ( "0" | [1-9][0-9]* ) ( "." [0-9]+ )?
Valid:   0, -0, 12, 1234.50, -0.75
Invalid: 01, +2, .5, 1., 1,000.5, NaN, 1e3
```

The syntax above intentionally **forbids exponents** to keep the contract tight. JSON numbers have their own grammar and *do* allow exponents; do not take this regex and claim it parses all JSON numbers.

In Java, `new BigDecimal("1234.50")` constructs a locale-independent decimal value; `toPlainString()` outputs a decimal string without scientific notation. However, `BigDecimal(String)` accepts a wider syntax than our proposed grammar, so **validate explicitly** if your protocol requires the narrower grammar.

### Java 17+ Example Validating Contract Decimals

Save **`StrictWireDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.regex.Pattern;

public class StrictWireDecimalDemo {
    private static final Pattern WIRE_DECIMAL = Pattern.compile(
            "-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?");

    private static void inspect(String input) {
        if (!WIRE_DECIMAL.matcher(input).matches()) {
            System.out.println("Rejected: " + input);
            return;
        }

        BigDecimal amount = new BigDecimal(input);
        System.out.println("Accepted: " + amount.toPlainString());
    }

    public static void main(String[] args) {
        inspect("1234.50");
        inspect("1,234.50");
        inspect("0123");
        inspect("-0.75");
        inspect("1e3");
    }
}
```

Run in the directory containing the file:

```bash
javac -encoding UTF-8 StrictWireDecimalDemo.java
java StrictWireDecimalDemo
```

Stdout:

```text
Accepted: 1234.50
Rejected: 1,234.50
Rejected: 0123
Accepted: -0.75
Rejected: 1e3
```

**Explanation:** `matches()` requires the **entire** string to match the grammar; it never accepts a valid prefix and ignores the rest. Once the grammar matches, convert to `BigDecimal`; arithmetic can then use `setScale(RoundingMode)` or `MathContext` per policy. `toPlainString()` never adds grouping separators and never reads `Locale.getDefault()`.

**Essential warning:** this example demonstrates syntax only and does not yet bound string length, digit count, magnitude, scale, valid range, or resource consumption for huge inputs. In real APIs, enforce length, precision, scale, and range limits before and after parsing. `BigDecimal` is decimal-exact compared to `double`, but it does not automatically validate business suitability.

## 4. Converting Properly at the UI → Model → Storage Boundary

Suppose a user in Germany enters `1.234,50` and the application needs to store `1234.50`:

```text
User UI (de-DE): "1.234,50"
            |
            | parse with SELECTED input locale
            v
Java model: BigDecimal 1234.50
            |
            | validate quantity, precision, scale, range
            v
DECIMAL column or wire field "1234.50"
            |
            | locale-independent data
            v
Read back -> BigDecimal -> format in viewer's locale
```

**Never attempt to turn commas into dots universally via `String.replace(...)`.** A comma can be a grouping separator in `en-US`, a decimal separator in `de-DE`, or part of non-numeric text. Use a locale-aware parser for user-entered text and verify full-string consumption.

In Java, `NumberFormat.parse(String)` can accept a **valid prefix** without checking trailing characters. `DecimalFormat.setParseBigDecimal(true)` preserves decimal values instead of converting to `double`, though it is only available when the parser is actually a `DecimalFormat`. When exact decimals are needed, a controlled approach is constructing an explicit `DecimalFormat` with `DecimalFormatSymbols.getInstance(userLocale)`, enabling `setParseBigDecimal(true)`, using `ParsePosition`, and verifying `position.getIndex() == input.length()`. Parser patterns can still accept broader shapes than business rules allow, so validation remains essential.

### Java 17+ Demo Reading UI Numbers by Locale

Create the file **`UserNumberBoundaryDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class UserNumberBoundaryDemo {
    public static void main(String[] args) {
        Locale inputLocale = Locale.GERMANY;
        String typed = "1.234,50";

        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(inputLocale));
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(typed, position);

        boolean complete = parsed instanceof BigDecimal
                && position.getIndex() == typed.length()
                && position.getErrorIndex() < 0;

        if (!complete) {
            throw new IllegalArgumentException("Invalid amount");
        }

        BigDecimal value = (BigDecimal) parsed;
        System.out.println("Wire: " + value.toPlainString());
        System.out.println("Value unchanged: "
                + (value.compareTo(new BigDecimal("1234.50")) == 0));
    }
}
```

```bash
javac -encoding UTF-8 UserNumberBoundaryDemo.java
java UserNumberBoundaryDemo
```

Stdout on a JDK with corresponding `Locale.GERMANY` data:

```text
Wire: 1234.50
Value unchanged: true
```

Real applications must also enforce grouping rules (parsers can be permissive), maximum digit counts, scale, range, and whether trimmed input is allowed. `DecimalFormat` is mutable, so never share a single instance unsynchronized across requests.

**Keep the two flows strictly separate:** `user-entered text` can be parsed using the user's locale; `machine wire text` must be parsed against the **protocol grammar**, never the server's default locale. Never use locale-aware parsers to read JSON numbers or SQL decimal values.

## 5. Machine-Readable Dates: `LocalDate` Is a Date, Not a Timestamp

A date such as a birth date or delivery date consists only of year, month, and day. Use `LocalDate` and ISO representation `yyyy-MM-dd`:

```text
2026-10-28
```

For calendar dates, this format **carries no time zone**. Do not convert `2026-10-28` into `2026-10-28T00:00:00Z` and treat the two as synonymous: the latter is a **UTC instant**, whereas a calendar date is purely a date that occurs across many time zones.

Java:

```java
LocalDate date = LocalDate.parse(
        "2026-10-28", DateTimeFormatter.ISO_LOCAL_DATE);
String wire = date.format(DateTimeFormatter.ISO_LOCAL_DATE);
```

This is a **fragment inside a method** requiring imports for `java.time.LocalDate` and `java.time.format.DateTimeFormatter`. `LocalDate.parse` with the ISO formatter validates calendar dates; for example, `2026-02-30` does not exist and will not silently roll into March under this standard parse mode.

When displaying in the UI, use `DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(uiLocale)` to render. The displayed date string varies by locale while the wire value stays invariant.

## 6. Absolute Instants: UTC, Offsets, and Zone IDs

Three concepts that are easily conflated:

- **`Instant`:** a point on the timeline; can be exchanged using ISO-8601 strings ending in `Z`, e.g., `2026-10-28T03:30:00Z`.
- **`OffsetDateTime`:** date-time paired with a UTC offset, e.g., `2026-10-28T10:30:00+07:00`. Both strings can denote the same instant.
- **`ZonedDateTime`/`ZoneId`:** a time zone region with historical rules and DST, such as `Europe/Paris`. **An offset `+07:00` is not a zone ID**: it does not carry regional transition rules.

### Complete Example — `TemporalWireDemo.java`

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class TemporalWireDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.parse(
                "2026-10-28", DateTimeFormatter.ISO_LOCAL_DATE);
        Instant utc = Instant.parse(
                "2026-10-28T03:30:00Z");
        OffsetDateTime localOffset = OffsetDateTime.parse(
                "2026-10-28T10:30:00+07:00");

        System.out.println("Day: " + day);
        System.out.println("UTC instant: " + utc);
        System.out.println("Same instant: "
                + utc.equals(localOffset.toInstant()));

        try {
            LocalDate.parse("2026-02-30");
            System.out.println("Invalid date accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid date rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 TemporalWireDemo.java
java TemporalWireDemo
```

Stdout:

```text
Day: 2026-10-28
UTC instant: 2026-10-28T03:30:00Z
Same instant: true
Invalid date rejected
```

Observation: the same instant can be represented with `Z` or a specific offset. If an API requires a **UTC canonical form**, convert via `Instant` and format per that contract rather than simply stripping `+07:00` from the string. Specify sub-second precision (seconds/milliseconds/microseconds/nanoseconds), rounding, and consumer compatibility clearly; `Instant.toString()` omits unnecessary fractional digits and does not promise fixed width.

**Local wall-clock appointment data:** if a user schedules “09:00 daily in Europe/Paris,” storing only the `Instant` of a single occurrence is insufficient to regenerate recurring times under DST rules. When business logic requires it, store **local date/time + IANA zone ID + policy for ambiguous/nonexistent times**. Storing an instantaneous offset cannot replace a zone ID.

## 7. Locale Codes in Files and APIs: Use BCP 47, Never Display Names

Distinguish the following:

| Role | Value |
| --- | --- |
| Standardized interchange locale tag | `vi-VN`, `en-US`, `pt-BR` |
| Java object construction | `Locale.forLanguageTag("vi-VN")` or `Locale.Builder` |
| Java tag serialization | `locale.toLanguageTag()` |
| Legacy Java `locale.toString()` | May use `_` and Java-specific extension syntax |
| UI label | `locale.getDisplayName(uiLocale)`, depends on display locale |
| `ResourceBundle` file name | E.g., `messages_vi_VN.properties`; resource naming convention, not a wire tag |

If an API accepts `languageTag`, **never store Vietnamese labels like `"Tiếng Anh (Hoa Kỳ)"` or `Locale.toString()` strings as if they were BCP 47**. Display labels depend on UI language and JDK data; `Locale.toString()` is not designed as an HTTP/JSON BCP 47 serialization.

**Parsing note:** `Locale.forLanguageTag(String)` is intentionally lenient with malformed BCP 47 tags and may ignore or adjust invalid subtags. When you need to **reject malformed syntax**, use `new Locale.Builder().setLanguageTag(input).build()` and catch `IllformedLocaleException`; afterward, still validate against the **set of locales supported by your product**. Valid syntax **does not** imply your application has translations or business formatting for that locale.

### Java 17+ Example — `LocaleWireDemo.java`

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleWireDemo {
    public static void main(String[] args) {
        Locale locale = new Locale.Builder()
                .setLanguageTag("pt-BR")
                .build();
        System.out.println("Tag: " + locale.toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en_US").build();
            System.out.println("Unexpected acceptance");
        } catch (IllformedLocaleException ex) {
            System.out.println("Invalid tag rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 LocaleWireDemo.java
java LocaleWireDemo
```

Stdout:

```text
Tag: pt-BR
Invalid tag rejected
```

The hyphen `-` in BCP 47 tags differs from the underscore `_` used in traditional properties filenames. Never derive one format from the other via string replacement if full language/script/region/variant/extension tags must be supported; use dedicated `Locale` APIs.

## 8. Text Files: Bytes Need Explicit Charset, Newlines, and Structure

A machine-readable file is not just a `String`: it is **bytes + encoding + format + version/schema**. In modern systems, **UTF-8** is usually the right choice to support Vietnamese and other scripts.

Java 17 provides file read/write APIs with explicit charsets:

```java
Files.writeString(path, text, StandardCharsets.UTF_8);
String loaded = Files.readString(path, StandardCharsets.UTF_8);
```

This is a **fragment** with `path` and `text` declared. Both methods have overloads defaulting to UTF-8 in modern Java, yet passing `StandardCharsets.UTF_8` explicitly clarifies the contract, especially if code is refactored onto other I/O APIs.

A file specification should define:

- **Encoding:** UTF-8, presence/absence of BOM, handling of malformed bytes; never guess via the platform default charset.
- **Line endings:** LF or CRLF, and whether a final line without a trailing newline is permitted.
- **Structure:** JSON, CSV, TSV, NDJSON, or a versioned domain format with defined delimiters and quoting.
- **Schema:** field names, types, null/missing rules, precision, ranges, required/optional fields, and extensibility.
- **Read/write failures:** report parse errors with clear causes rather than silently turning bad rows into zeros or today's date.

### Java 17+ UTF-8 Round-Trip Example

Save **`Utf8FileRoundTripDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FileRoundTripDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("localization-", ".txt");
        try {
            String original = "Chào bạn — café";
            Files.writeString(
                    path, original, StandardCharsets.UTF_8);

            String restored = Files.readString(
                    path, StandardCharsets.UTF_8);
            System.out.println("Round trip: "
                    + original.equals(restored));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac -encoding UTF-8 Utf8FileRoundTripDemo.java
java Utf8FileRoundTripDemo
```

Stdout:

```text
Round trip: true
```

The code uses a temporary file to keep the example self-contained and deletes it in `finally`. In production applications, account for write permissions, I/O failures, atomic writes, integrity, and source data encoding. One successful round-trip only proves both sides of this example used UTF-8; **it does not prove other external systems are reading the format properly**.

## 9. JSON in APIs: JSON Grammar Is Not `NumberFormat` Grammar

JSON uses a structured grammar of numbers, strings, booleans, nulls, arrays, and objects. In JSON, a **number token** uses ASCII digits and `.` as the decimal point; **never use locale-specific grouping separators**:

```json
{
  "amount": 1234.50,
  "eventDate": "2026-10-28",
  "occurredAt": "2026-10-28T03:30:00Z",
  "locale": "vi-VN",
  "customerCode": "001234"
}
```

A JSON payload containing `"amount": 1.234,50` is invalid JSON syntax, even if the user is viewing a German UI. UI formatting occurs **after** JSON has been parsed into typed data.

**JSON numbers and precision:** JSON does not require every receiving implementation to use `BigDecimal`. Many JavaScript clients use `Number` (binary floating point), which can lose precision on huge integers or financial decimals. If a financial API needs end-to-end decimal exactness, define an explicit contract—such as `"amount": "1234.50"` as a valid decimal string parsed into decimal types on both ends, or an agreed typed decimal approach. Never assume every JSON number preserves decimal scale or precision across all languages.

**Java SE 17 has no built-in general-purpose JSON parser/generator in `java.base`.** In real applications, use your stack's standard JSON library (such as Jackson or JSON-B) configured to serialize/deserialize `BigDecimal`, `LocalDate`, and `Instant` with proper validation. Never build JSON by hand via string concatenation on user input: quotes, backslashes, control characters, and Unicode must be escaped per JSON rules.

### HTTP: Charset and Media Type

When sending JSON, use media type `application/json` and UTF-8 encoding under modern JSON contracts. Avoid relying on the HTTP server's locale to encode or parse payloads. The `Accept-Language` header is a **language hint for presentation content**, not a directive that changes JSON number grammar. `Content-Language` can describe the natural language of content, but it does not turn `1234.50` into `1.234,50` inside a JSON number.

If an API needs to return formatted display strings for a UI, keep **typed value fields** separate from **display label fields**. A machine-oriented field named `amount` must never silently flip from a number to a localized string based on a request header.

## 10. CSV and TSV: Define Delimiters, Quoting, Encoding, and Schema

CSV is a **text interchange format**; commas can appear both as column delimiters and inside person names or locale-formatted number strings. Without a quoting contract, parsers miscount columns.

CSV example with three columns `id,amount,customerName`:

```csv
id,amount,customerName
1,1234.50,"Nguyễn, Lan"
2,15.00,"Lê ""An"""
```

Under RFC 4180-style CSV conventions, a `"` inside a quoted field is escaped as **two quotes `""`**, and commas inside quoted fields **do not split columns**. Interchange files should specify UTF-8 charset, delimiter, header, newline convention, and quoting rules; never switch to semicolons merely because a viewer's `Locale` uses a decimal comma.

**Simple encoder fragment for a single CSV field** (not a full CSV parser or writer):

```java
static String quotedCsvField(String value) {
    return "\"" + value.replace("\"", "\"\"") + "\"";
}
```

It **always quotes** the field and doubles embedded `"` characters. Writing an entire file requires handling newlines, CRLF, delimiters, nulls, and consistent schemas; when reading, **never use `String.split(",")` as a CSV parser** because it does not understand quoted fields or embedded newlines. Use a battle-tested CSV library or a parser implementing your contract grammar.

### Lessons from Decimals in CSV

A machine-oriented `amount` column should hold `1234.50`. Never call `NumberFormat.getCurrencyInstance(locale).format(amount)` and write that into the data column, because it adds grouping separators and currency symbols. If you also need a human-friendly label like `1.234,50 €` for a report, put it in a **separate display column**, never in place of the typed value field.

If a user's spreadsheet software guesses CSV delimiters based on OS locale, treat that as **client import behavior**, not a reason to break your machine-readable system contract. You can offer a separate “Excel-friendly export” with explicit delimiter settings if needed.

## 11. Databases: Store Numbers/Dates in Typed Columns, Not Localized Strings

In a relational database, prefer appropriately typed columns:

| Data | Common Column Type | Java Type |
| --- | --- | --- |
| Monetary/decimal value | `DECIMAL(p,s)` or `NUMERIC(p,s)` | `BigDecimal` |
| Integer quantity | `INTEGER`, `BIGINT` | `int`/`long` |
| Calendar date | `DATE` | `LocalDate` (JDBC 4.2+ with driver support) |
| Timestamp | Database-appropriate timestamp type with clear UTC/offset/zone semantics | `Instant`/`OffsetDateTime` per driver mapping |
| Locale tag | `VARCHAR` with application constraint | BCP 47 string like `vi-VN` |
| Customer code with leading zeros | `VARCHAR` | `String` |

**Never store `"1.234,50"` in a decimal column or `"28/10/2026"` in a `DATE` column** just because that is how users view it. Typed storage enables safe querying, indexing, arithmetic, and environment portability.

With JDBC, use **prepared statements and typed parameters**, never concatenate formatted numeric/date literals into SQL:

```java
// Fragment inside a method with PreparedStatement ps.
ps.setBigDecimal(1, new BigDecimal("1234.50"));
ps.setObject(2, LocalDate.of(2026, 10, 28));
ps.setString(3, "vi-VN");
```

This assumes the SQL statement has matching `?` placeholders in order, along with a compatible JDBC connection/driver. `LocalDate` is supported in JDBC 4.2, whereas timestamp/zone mappings still depend on the database, driver, and column type. For absolute instants, consult your driver's documentation on UTC storage, offsets, and time zone conversions; never assume every `TIMESTAMP` column in every database behaves identically to `Instant`.

**`PreparedStatement` does more than prevent decimal separator bugs**: it separates query structure from input data, mitigating SQL injection risks. The locale used to format reports **is never** a parameter controlling whether SQL parsers expect commas or dots.

## 12. Characters, Unicode, and Identifiers

UTF-8 encodes characters into consistent byte sequences, yet it **does not automatically normalize Unicode**. An accented character may exist in precomposed form or as a base character plus combining mark. Visually identical strings can contain different code point sequences.

For personal names and free text, establish clear storage and comparison policies—avoid blindly stripping diacritics or changing case using the default locale without understanding the consequences. If the system standardizes on a normalization form such as **NFC**, apply it at a defined boundary and test thoroughly; never unconditionally normalize code/ID strings if the protocol requires preserving exact bytes or digital signatures.

For machine-readable identifiers:

- `"001234"` is a **code**, not the number 1234; converting it to `int` drops leading zeros.
- UUIDs, hashes, enum codes, and currency codes like `USD` should follow canonical protocol spelling, never a localized display name like “US Dollar”.
- Never use `Locale.getDisplayName()` as a database key; display names vary with UI language and JDK versions.
- When signing or canonicalizing JSON or files, apply the **canonicalization rules** agreed upon by both parties in the protocol rather than ad-hoc trimming or `toString()`.

## 13. A Java API Architecture Separating Data from Labels

You can organize the processing flow into the following stages:

```text
Request/CSV/file
    ↓ Parse with exact grammar + charset
Typed input DTO (BigDecimal, LocalDate, Instant, Locale tag)
    ↓ Validate domain (precision, scale, date range, supported locale)
Domain/service + typed database columns
    ↓ Serialize per machine-readable schema
Stable API/file values
    ↓ At UI layer: format for viewer's Locale
Human-readable labels
```

If a request carries both `locale=de-DE` and `amount="1234.50"`, treat `locale` as a product-supported presentation preference/hint while keeping `amount` as a schema-compliant wire decimal. If a product intentionally exposes an endpoint **accepting user-typed localized number strings**, clearly designate it as a UI input path, parse with the validated input locale, and keep it separate from endpoints using numeric wire format.

### Java 17+ Example Round-Tripping a Record

Create the file **`StableRecordDemo.java`**:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Locale;

public class StableRecordDemo {
    record OrderData(
            BigDecimal amount,
            LocalDate deliveryDate,
            Instant createdAt,
            Locale displayLocale) {}

    public static void main(String[] args) {
        OrderData order = new OrderData(
                new BigDecimal("1234.50"),
                LocalDate.parse("2026-10-28"),
                Instant.parse("2026-10-28T03:30:00Z"),
                Locale.forLanguageTag("vi-VN"));

        String amountWire = order.amount().toPlainString();
        String dayWire = order.deliveryDate().toString();
        String instantWire = order.createdAt().toString();
        String localeWire = order.displayLocale().toLanguageTag();

        OrderData restored = new OrderData(
                new BigDecimal(amountWire),
                LocalDate.parse(dayWire),
                Instant.parse(instantWire),
                Locale.forLanguageTag(localeWire));

        System.out.println("Amount: " + amountWire);
        System.out.println("Day: " + dayWire);
        System.out.println("Instant: " + instantWire);
        System.out.println("Locale: " + localeWire);
        System.out.println("Same data: "
                + order.equals(restored));
    }
}
```

```bash
javac -encoding UTF-8 StableRecordDemo.java
java StableRecordDemo
```

Stdout:

```text
Amount: 1234.50
Day: 2026-10-28
Instant: 2026-10-28T03:30:00Z
Locale: vi-VN
Same data: true
```

This example **defines and checks canonical values for a small model**; it is not a full JSON serializer or JDBC adapter. In real systems, the schema must specify required fields, null vs. absent handling, decimal formatting, precision, timestamp fractional precision, length bounds, and versioning strategy. `BigDecimal.equals` also inspects **scale**, so if the system does not preserve scale, define an appropriate comparison/normalization policy and use `compareTo` where needed.

## 14. Contracts Must Be Versioned and Rigorously Verified

**“Machine-readable” does not mean “valid as long as parsing succeeds.”** Interchange data must satisfy:

1. **Named formats:** JSON/CSV/ISO/BCP 47/decimal grammar; never vague descriptions like “international number format.”
2. **Types and nullability:** which fields are numbers/strings/dates, and which may be null or omitted.
3. **Precision, scale, range:** maximum digits, allowed fractional places, value bounds, and currency/measurement units.
4. **Time semantics:** calendar date vs. instant; offsets, zone IDs, sub-second precision, and DST rules where relevant.
5. **Charset and newlines:** UTF-8, BOM policy, invalid-byte handling, and CSV line endings.
6. **Canonicalization when required:** deterministic format for comparisons, signatures, and audits; never assume any `toString` is canonical.
7. **Versioning/schema evolution:** policies for adding/removing fields, backward compatibility, and data migration.
8. **Error reporting:** parse/validation errors must return structured error codes and field references rather than silently altering bad input.
9. **Round-trip fidelity:** parse → serialize → parse preserves committed semantics; test under different default locales.
10. **Safety:** bound payload size, digit counts, JSON nesting depth, CSV file size, and control characters; use hardened parsing libraries to prevent injection and DoS.

For instance, formatting `BigDecimal("1234.50")` with a `NumberFormat` limited to one fractional digit and parsing it back yields `1234.5`; the **numeric value** matches, while **scale** and original literal differ. Know whether your contract requires preserving value, fractional digit count, or exact literal.

## 15. Testing Independently of the Host's Default Locale

A valuable test runs machine-data parsing under **two different JVM locales** and proves identical results:

```bash
java -Duser.language=en -Duser.country=US StableRecordDemo
java -Duser.language=de -Duser.country=DE StableRecordDemo
```

`StableRecordDemo` does not rely on `Locale.getDefault()` for parsing or serialization, so machine-readable fields preserve identical semantics. Note that `-D...` here is a **JVM startup configuration**, not a recommendation to mutate defaults inside server code.

QA test cases should cover:

| Group | Test Input | Expected Result |
| --- | --- | --- |
| Valid decimal | `1234.50` | Parses as exact decimal; no grouping |
| Invalid wire grammar | `1.234,50`, `1,234.50` | Rejected on endpoints enforcing narrow grammar |
| Oversized number / too many digits | Digit string exceeding policy | Rejected within bounds before heavy processing |
| Standard date | `2026-10-28` | Parses to `LocalDate` |
| Invalid date | `2026-02-30` | Rejected without silent date rollover |
| Instant/offset | Equivalent `...Z` and `...+07:00` | Equal instants after offset conversion |
| Valid / malformed locale tag | `pt-BR` / `en_US` | Validates tag syntax and checks supported locales |
| Unicode text | `Chào bạn`, combining characters | Proper UTF-8 handling with clear Unicode policy |
| CSV quoted field | `"Nguyễn, Lan"` | Not split into two columns |
| Large JSON decimal | Number beyond client safe-integer range | Handled via decimal string schema or precision strategy |
| Typed DB parameters | `BigDecimal`, `LocalDate` | No display strings interpolated into SQL |
| Changed default locale | JVM `en-US` and `de-DE` | Machine representations remain invariant |

**Do not verify only visually** that numbers “look nice”; compare typed values, wire literals, and round-trip behavior. For JSON/CSV, write contract tests between services using distinct parsers to catch discrepancies before release.

## 16. Common Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Using default `NumberFormat.getInstance()` for API/DB | Results vary with server host locale | Use explicitly defined machine types/grammars |
| Storing numbers formatted as `1.234,50` | Consumers misread decimal vs. grouping separators | Convert to `BigDecimal` and serialize per schema |
| Using `String.replace(",", ".")` to normalize all numbers | Breaks when grouping and formats vary | Parse UI input by specific locale and validate fully |
| Using `double` for exact monetary decimals | Binary rounding bugs and precision loss | Use `BigDecimal` with explicit rounding policies |
| Calling `BigDecimal.toString()` assuming no exponents | Can output scientific notation | Use `toPlainString()` if grammar forbids exponents |
| Using `Date.toString()` as an API timestamp | Unstable wire contract, environment timezone leakage | Use `Instant`/ISO with explicit offset or UTC |
| Storing birth dates as midnight UTC | Time zone shifts can change the calendar date | Use `LocalDate` and a `DATE` column |
| Storing recurring appointments with only an offset | Missing regional DST rules | Store `ZoneId` and local schedule when needed |
| Saving `Locale.getDisplayName()` in APIs | Labels vary with UI language | Use `toLanguageTag()` |
| Assuming `Locale.forLanguageTag` rejects all invalid tags | API silently ignores/fixes malformed parts | Use `Locale.Builder` plus supported-locale validation |
| Calling `String.split(",")` on CSV | Breaks on commas inside quoted fields | Use a grammar-compliant CSV parser |
| Building JSON via string concatenation | Broken escaping, JSON injection/syntax errors | Use a proper JSON serializer |
| Storing code `001234` as an integer | Drops leading zeros | Store as `String` |
| Calling `Locale.setDefault` per request | Corrupts JVM-wide state, race conditions | Pass per-request locale only to the UI layer |
| Writing files with default charset and no contract | Unicode corruption across environments | Specify UTF-8 explicitly |
| Skipping validation because the parser returned an object | Can violate domain/precision/scale rules | Validate syntax, range, scale, and units |
| Building SQL literals from formatted numbers | Syntax errors and SQL injection risk | Use `PreparedStatement` typed parameters |

## 17. Applied Exercises

**Exercise 1 — Standardizing a numeric input path.** Build a `de-DE` UI accepting `1.234,50`. Parse with `DecimalFormat`, matching symbols, and `ParsePosition`; validate precision/scale; store as `BigDecimal`. When returning a machine decimal from an API, output `toPlainString()` per a published grammar. Compare the result with entering `1,234.50` in `en-US`.

**Exercise 2 — Separating calendar dates from instants.** Design a DTO containing `birthDate=2026-10-28` and `createdAt=2026-10-28T03:30:00Z`. Choose `LocalDate`/`Instant` accordingly; convert the same instant to offset `+07:00` and compare via `toInstant()`.

**Exercise 3 — JSON decimal contract.** Suppose a JavaScript frontend must handle exact invoice decimals. Propose a schema using `"amount": "1234.50"` alongside an explicit currency unit (e.g., `"currency": "USD"`), specifying parsing, precision, scale, and rounding. Explain why a display field like `"1,234.50 USD"` is unsuitable for calculations.

**Exercise 4 — CSV with comma-containing names.** Create a CSV with `customerName=Nguyễn, Lan`, decimal `1234.50`, and an ISO timestamp. Verify that your CSV parser does not split the quoted comma into an extra column.

**Exercise 5 — Locale tags.** Validate `pt-BR`, `zh-Hant-TW`, and `en_US` using `Locale.Builder`. Record which tags are syntactically valid, and match them against your application's supported locale list. Distinguish “syntactically valid tag” from “application has translations.”

## 18. References

- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): numeric strings, `toPlainString`, precision, and scale.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO formatters, parsing/formatting, and locales.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `toLanguageTag`, `forLanguageTag`, and `Locale.Builder`.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): locale-aware parsing, `setParseBigDecimal`, and rounding.
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259): JSON syntax and UTF-8 interchange.
- [RFC 4180 — CSV](https://www.rfc-editor.org/rfc/rfc4180): traditional CSV quoted-field rules.
- [RFC 5646 — Language Tags](https://www.rfc-editor.org/rfc/rfc5646): syntax foundation for BCP 47 language tags.

## 19. Key Takeaways

**Never store or transmit “translated numbers/dates” when the consumer needs typed data.** Use `BigDecimal` for exact decimals, `LocalDate` for calendar dates, `Instant`/explicit offsets for points in time, BCP 47 for locales, UTF-8 for files, and explicit versioned schemas for JSON/CSV/JDBC. Parse user input using the **input's locale**; parse machine wire data using the **protocol grammar**, independent of the JVM default. Always validate full input consumption, precision/scale/range, time zones, and round-trip behavior; apply `Locale` only at the UI boundary to produce human-readable labels.
