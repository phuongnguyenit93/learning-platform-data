# Testing Locale, Charset, Timezone, and Internationalized Data

Upgrading a JDK is not just about checking class files, removed APIs, or application response times. The exact same Java source code can produce **different date strings**, **different numeric separators**, **different bytes when writing files**, or **different instant calculation results** after switching the JDK, operating system, container image, or timezone database update. These changes may not throw an exception: the system keeps running, yet exchanged data and business decisions become wrong.

Processing paths involving **locale**, **charset**, **timezones**, and **internationalization (i18n)** are particularly sensitive. For example, decomposed Vietnamese characters can look identical to precomposed characters yet fail direct equality comparisons; a comma in `1,234` can represent a grouping separator or a decimal separator depending on the locale; `02:30` in a location with daylight saving time (DST) may not exist on the clock-transition day; and a file written using the default charset on an old JDK may be read differently on a new JDK.

This lesson guides the design of **regression tests** for those issues in the context of Java Advance Compatibility Migration: defining data contracts, isolating environment defaults, creating intentional test datasets, running matrices across multiple JDKs/locales/charsets/timezones, and handling differences by business semantics rather than only comparing string snapshots.

## 1. Why Can the Same Java Code Produce Different Results?

A text or temporal processing result can depend on multiple layers:

~~~text
Source code + dependencies
            |
            v
       JDK runtime
            |
            +--> CLDR / locale data version
            +--> Unicode properties / normalization data
            +--> Default charset / charset mappings
            +--> TZDB (time zone rules)
            |
            v
       Process environment
            |
            +--> Default Locale
            +--> Default ZoneId / user.timezone
            +--> OS/container locale & timezone
            +--> JAVA_TOOL_OPTIONS / JVM options
            |
            v
        Input data
            |
            +--> Bytes + encoding
            +--> User's locale
            +--> Event timezone and offset
            +--> Unicode representation
            |
            v
       Parse / Format / Compare
            |
            v
       Data, response, business decision
~~~

Even when the JDK version stays the same, updating a container image, database, host settings, or tzdata can create differences. During an actual migration, multiple variables often change simultaneously, so you must first isolate the cause.

### 1.1. Classifying Four Groups of Changes

| Group | Affected inputs/settings | Regression examples |
|---|---|---|
| **Locale** | `Locale`, CLDR, language/region | Date formatting, number separators, case conversion, collation |
| **Charset** | `Charset.defaultCharset()`, decode/encode APIs | Corrupted Vietnamese diacritics when reading files, wrong checksums, mojibake messages |
| **Timezone** | `ZoneId`, TZDB, system default, DST | Shifted appointment times, wrong duration calculations, different timestamps |
| **i18n/Unicode** | Normalization, properties, resource bundles, Unicode data | Missing translations, colliding/distinct identifiers, changed regex validation |

A good test case must explicitly specify **input, locale, charset, zone, JDK, and expected result**. Saying "it works on my machine" omits these factors.

### 1.2. Source Compatibility Differs from Behavioral Compatibility

The following code still compiles:

~~~java
String output = java.text.NumberFormat.getInstance()
    .format(1234.56);
~~~

However, the result can depend on the process's default locale and the runtime's locale data. Therefore, compiling cleanly on a new JDK does not prove that the output remains compatible with old consumers.

Conversely, if a system **intentionally** formats according to the user's language, a CLDR update to a rule may be a linguistically accurate change rather than a bug to force back to the old output. Tests must distinguish stable contracts at the machine-protocol level from presentation for humans.

## 2. Starting from the Data Contract

Before writing JUnit tests, classify where invariant output is required and where variation by locale/timezone is allowed.

| Field/behavior | Contract should state clearly | Test type |
|---|---|---|
| Transaction ID | ASCII with fixed grammar | Exact input/output |
| JSON data | UTF-8 per protocol and schema | Byte round-trip, Unicode fixtures |
| Monetary amount stored in DB | Explicit unit, precision, currency | Semantic equality, do not use formatted strings |
| Displayed monetary amount | User's locale/currency | Format by locale, semantic + controlled snapshot |
| API timestamp | Explicitly specified UTC instant / offset / zone | ISO 8601 parse/round-trip |
| Local appointment | `LocalDateTime` + region `ZoneId` + DST policy | Gap/overlap tests |
| Person names | Unicode, normalization, and length limits | NFC/NFD, supplementary, combining marks |
| List sorting | Collation per defined locale | Ordering of key cases |
| Multilingual messages | ResourceBundle locale/fallback | Missing keys, placeholders, translations |

**Do not store locale-formatted strings as canonical numeric or temporal data for exchange between services**, unless the protocol specifies that exact format. Prefer storing canonical values and formatting only at the display boundary.

### 2.1. Test-Definition Question Set

Each data path should answer:

1. Do characters enter as bytes or `String`? Where does the encoding come from?
2. Does the locale come from the user/account, HTTP request, environment, or JVM default?
3. Does the date/time represent an **instant**, a **local time**, or a **zone-aware schedule**?
4. Is the formatted output solely for display or used as a key/API contract?
5. Is there a Unicode normalization, lowercasing, or collation step?
6. If JDK locale/TZDB data changes, which outputs are allowed to change?
7. Will the old system continue to parse data written by the new version?

Without distinguishing these, a snapshot assertion expecting "identical to the old JDK" can be simultaneously too rigid for UI and too loose for APIs.

## 3. `Locale` in Java: Use the Default or Pass Explicitly?

`java.util.Locale` describes language, region, and related subtags. It does **not** contain the formatting rules itself; classes such as `DateTimeFormatter`, `NumberFormat`, and `Collator` use the runtime's locale data.

Example:

~~~java
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale french = Locale.FRANCE;
Locale turkish = Locale.forLanguageTag("tr-TR");
Locale neutral = Locale.ROOT;

System.out.println(vietnamese.toLanguageTag()); // vi-VN
~~~

Use `Locale.forLanguageTag(...)` for BCP 47 language tags. Locales also support extensions such as numbering systems/calendars; for multi-market products, do not collapse everything down to a two-letter language code.

### 3.1. Default Locale Is Environment State

~~~java
Locale current = Locale.getDefault();
Locale format = Locale.getDefault(Locale.Category.FORMAT);
Locale display = Locale.getDefault(Locale.Category.DISPLAY);
~~~

The two categories `FORMAT` and `DISPLAY` serve different purposes. An application might need a menu language different from its date/number formatting; passing `Locale.getDefault()` everywhere may fail to satisfy that design.

The default locale can depend on OS, environment, and JVM configuration settings. When moving from a host to a container, this value can change even when the source code and database do not.

### 3.2. Avoid Using the Default Locale for Protocols

**Avoid:**

~~~java
String reportValue =
    String.format("%.2f", 1234.56);
~~~

Because `String.format` without a locale argument uses the default locale, the output may have a different decimal separator. If the string is a protocol value, define an invariant representation:

~~~java
String machineValue =
    String.format(Locale.ROOT, "%.2f", 1234.56);
~~~

If it is for UI, pass the user's locale:

~~~java
String displayValue =
    String.format(Locale.forLanguageTag("vi-VN"),
                  "%.2f", 1234.56);
~~~

`Locale.ROOT` is suitable for some language-independent formatting/case-mapping operations, but it is not the right choice for all UI content.

### 3.3. Do Not Change the Default Locale in Parallel Tests

~~~java
Locale.setDefault(Locale.FRANCE);
~~~

This call modifies **JVM-wide state**; tests running in parallel or other libraries may observe the new value. Even with a `finally` block restoring it, the test can still race with other threads.

Preferred approach: pass `Locale` explicitly into the code under test. If you must test legacy code that relies on JVM defaults, run a **separate test process/fork** configured with the default locale at startup.

## 4. Locale Data and CLDR Changes Across JDKs

Java uses locale data to format dates, digits, currencies, country names, calendars, and many other features. Part of this data comes from the **Unicode Common Locale Data Repository (CLDR)**.

### 4.1. Key Milestones to Know

- **JDK 9 – JEP 252:** shifted runtime defaults to prefer CLDR data over legacy JRE locale data.
- **JDK 18 – JEP 400:** made UTF-8 the default charset under the standard policy—a separate change from CLDR, though it frequently causes i18n regressions at the same time.
- Newer JDK feature/update releases can update CLDR, Unicode, and locale data.
- Legacy locale providers such as `COMPAT` have been changed/removed in modern JDKs; do not rely long-term on `java.locale.providers=COMPAT,...` to freeze old formatting.

If the application previously used legacy provider selection via the `java.locale.providers` property, check the **release notes of the exact target runtime** and eliminate the assumption that the old provider always exists.

### 4.2. Formatted Output Is Not an Immutable Interchange Standard

Example:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

Locale fr = Locale.FRANCE;
String text = NumberFormat.getNumberInstance(fr)
    .format(1234567.89);

System.out.println(text);
~~~

The string may use a locale-specific decimal separator and grouping separator; the grouping character may be a form of Unicode space rather than an ASCII space. CLDR data and the JDK version can affect the specific character.

If a test demands `"1 234 567,89"` with an ASCII space on every JDK, the test may fail even when the implementation conforms to updated locale data. You must decide to what extent UI output is allowed to change.

### 4.3. Regression Tests Should Have Two Tiers

**Semantic contract tier:** formatted strings can be parsed back to the same value; currency codes are accurate; dates are accurate; users receive output in the requested locale.

**Presentation snapshot tier:** when the interface requires exact characters, messages, or formatting, store official golden fixtures per locale/JDK and intentionally review CLDR changes.

Do not "update all snapshots" after upgrading a JDK without verifying whether the change is accepted by business/UX stakeholders.

## 5. Testing Number Formatting and Parsing

`NumberFormat`, `DecimalFormat`, and `DecimalFormatSymbols` exhibit locale-dependent behavior. `Double.parseDouble` and `BigDecimal(String)`, by contrast, use an API/Java-defined independent numeric grammar rather than locale-specific parsing functions.

### 5.1. Using `NumberFormat` for Its Intended Purpose

~~~java
import java.text.NumberFormat;
import java.util.Locale;

Locale fr = Locale.FRANCE;
NumberFormat formatter =
    NumberFormat.getNumberInstance(fr);

formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);

String display = formatter.format(1234.5);
System.out.println(display);
~~~

The displayed value may include grouping separators, decimal separators, and Unicode spacing according to locale data. Do not use it as a storage key or pass it directly to a service expecting an ASCII decimal string.

### 5.2. Parsing Must Validate the Entire String

`NumberFormat.parse(String)` can parse a **prefix** and ignore the trailing portion depending on the parser. A test case verifying "parser does not throw an exception" is insufficient if the code treats the input as a monetary amount.

You can check `ParsePosition`:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public final class LocaleNumberParser {
    public static Number parseEntirely(String text, Locale locale) {
        NumberFormat format =
            NumberFormat.getNumberInstance(locale);

        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (parsed == null ||
            position.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                "Invalid localized number");
        }
        return parsed;
    }
}
~~~

For currency and decimal precision, use an appropriate storage type such as `BigDecimal`, also considering `DecimalFormat`'s parse-to-`BigDecimal` capability (with `setParseBigDecimal(true)`) and explicitly defining rounding rules.

### 5.3. Do Not Compare Money as `double`

~~~java
double amount = 0.1 + 0.2;
System.out.println(amount == 0.3); // false
~~~

Floating-point error is not a locale bug. However, when combined with formatting/parsing, it can make tests hard to diagnose. For monetary values, specify the unit, currency, precision, and rounding mode.

`BigDecimal` example:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("1234.565")
    .setScale(2, RoundingMode.HALF_UP);

System.out.println(amount.toPlainString()); // 1234.57
~~~

The `toPlainString()` form is better suited for certain invariant decimal contracts; do not use UI-oriented `NumberFormat` strings as a machine-to-machine exchange format.

### 5.4. Currency Symbols Can Also Change

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

NumberFormat money =
    NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("vi-VN"));

money.setCurrency(Currency.getInstance("VND"));
System.out.println(money.format(1234567));
~~~

Symbols, symbol placement, grouping separators, and whitespace can depend on locale data. Tests should confirm **currency code and amount semantics**, and control UI snapshots separately when needed.

### 5.5. `NumberFormat` Is Not Safe to Share Arbitrarily Across Threads

Some `java.text` formatters are mutable and not designed for unsynchronized sharing. In concurrent tests, create a separate formatter per request/test or manage synchronization properly. If tests flake during parallel execution, the cause may be a shared formatter rather than JDK locale data.

## 6. Case Conversion, Comparison, and Locale-Aware Sorting

### 6.1. The Letter I in Turkish

~~~java
import java.util.Locale;

System.out.println("I".toLowerCase(Locale.ROOT)); // i
System.out.println(
    "I".toLowerCase(Locale.forLanguageTag("tr-TR"))
); // ı (dotless i)
~~~

If a system calls `String.toLowerCase()` without passing a locale to normalize technical identifiers, a different default locale can alter keys and cause lookup/duplication bugs.

For language-independent technical identifiers, consider `Locale.ROOT` along with explicit charset/normalization rules. For proper names and natural text, locale-specific case mapping may be required.

### 6.2. Case Folding Is Not Completely Synonymous with Lowercase

Case-insensitive comparison can involve various Unicode characters and special rules. `equalsIgnoreCase`, `toLowerCase(Locale)`, regex `CASE_INSENSITIVE`, and Unicode-aware case folding are not interchangeable across all languages.

If an application uses case-insensitive usernames, design an explicit canonicalization and uniqueness policy; do not treat `equalsIgnoreCase` as a comprehensive security/confusable-detection guarantee.

### 6.3. Collation with `Collator`

~~~java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

String[] names = {"An", "Ánh", "Anh", "Ân"};
Collator collator =
    Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

Arrays.sort(names, collator);
System.out.println(Arrays.toString(names));
~~~

`Collator` uses locale-based comparison rules and has comparison levels (*strength*) such as primary, secondary, and tertiary. Ordering rules can change with locale data or configuration.

If a system stores *sort keys* or builds search indexes based on collation, upgrading the JDK may require **reindexing** when rules change; do not just rerun unit tests.

### 6.4. Do Not Use User-Locale Collation to Generate Durable Data Identifiers

Using locale/JDK-dependent sort keys as partition keys, unique keys, or digital signatures can produce unstable results across migrations. Use a well-defined canonical representation for machine-to-machine contracts; use collation only for search and presentation when appropriate.

## 7. ResourceBundle and UI Translations

Java supports multilingual resources via `ResourceBundle`. An application may contain:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_fr.properties
  messages_tr.properties
~~~

Examples:

~~~properties
# messages.properties
welcome=Welcome
items=You have {0} items
~~~

~~~properties
# messages_vi.properties
welcome=Xin chào
items=Bạn có {0} mục
~~~

Code:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
    ResourceBundle.getBundle("messages", locale);

String template = bundle.getString("items");
String output = new MessageFormat(template, locale)
    .format(new Object[] {5});

System.out.println(output);
~~~

### 7.1. Fallback and Missing Translations

A `vi-VN` request can use the `messages_vi` bundle when `messages_vi_VN` does not exist. If a key is missing in the selected bundle, the framework may fall back according to `ResourceBundle` rules or throw `MissingResourceException`.

Tests should check:

- Mandatory keys exist across supported locales.
- Bundle fallback works properly when a specific locale is missing.
- Keys have not been renamed across versions.
- Placeholder indices and types match.
- Parameter formatting matches the expected locale.
- No unintended mixed-language text appears on critical screens.

### 7.2. Encoding of Properties Files

Do not confuse the two APIs:

- `java.util.Properties.load(InputStream)` uses **ISO-8859-1** rules and supports Unicode escapes `\uXXXX`.
- `Properties.load(Reader)` reads characters already decoded by the `Reader` according to the charset chosen by the caller.

Example:

~~~java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

Properties props = new Properties();

try (InputStream input =
        getClass().getResourceAsStream("/config.properties");
     InputStreamReader reader =
        new InputStreamReader(input, StandardCharsets.UTF_8)) {
    props.load(reader);
}
~~~

The example assumes the resource exists; in production code, check `input != null` before constructing `InputStreamReader` and handle errors appropriately.

`PropertyResourceBundle` has its own encoding rules that were improved in **JDK 9 (JEP 226)**: by default, it includes a mechanism for reading UTF-8 and falling back where appropriate for legacy compatibility. Do not conflate loading this bundle with `Properties.load(InputStream)`.

### 7.3. `MessageFormat` Has Its Own Quoting Syntax

In localized templates, single quotes carry special escaping semantics for `MessageFormat`. A translation containing an apostrophe may render incorrectly or drop placeholders if the template is not authored properly.

Tests must use **real translations** containing apostrophes, braces, pluralization, and parameter values. Do not just verify that the bundle retrieves a string.

### 7.4. Do Not Hot-Reload Bundles in a Way That Causes Flaky Tests

`ResourceBundle` involves caching, class loaders, and fallback behavior. When tests modify properties content within the same JVM, you may have to clear caches using the appropriate API or use an isolated process/class loader. Better yet, in CI, resource files are normally immutable artifacts and tests run against the real artifact.

## 8. Charset: `String` and Bytes Are Two Different Layers

A `String` is a character sequence at the Java API level, whereas files/networks/storage handle **bytes**. A charset defines how encoding/decoding maps between the two layers.

~~~text
Java String
     |
     | encode(UTF-8)
     v
Bytes  ------> File / API / Queue / DB
     |
     | decode(UTF-8)
     v
Java String
~~~

If the writer uses Windows-1252 or a system charset while the reader defaults to UTF-8, data may get corrupted diacritics or show the replacement character `�` (*replacement character*).

### 8.1. APIs Prone to Depending on the Default Charset

~~~java
byte[] bytes = text.getBytes();        // No charset passed
String decoded = new String(bytes);    // No charset passed
~~~

Constructors like `InputStreamReader(InputStream)` and `OutputStreamWriter(OutputStream)` when no charset is specified can also use the default charset per the API.

If the data source has a UTF-8 contract, pass it explicitly:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes =
    text.getBytes(StandardCharsets.UTF_8);

String decoded =
    new String(bytes, StandardCharsets.UTF_8);
~~~

These operations are more stable across JDKs and OSes.

### 8.2. JDK 18 and JEP 400

**JEP 400 – UTF-8 by Default** changes the default charset of Java APIs within the JEP's scope to UTF-8 starting in JDK 18. Previously, the default charset could depend on the environment's OS/locale.

Migration implications:

- A file written with an API without passing a charset on an old JDK on Windows may have used the native charset.
- A new JDK may read the exact same bytes as UTF-8 and get a different result.
- Code that passes an explicit charset is generally less impacted.
- **Console I/O** charsets have separate considerations; do not infer from `Charset.defaultCharset()` that every terminal also uses UTF-8.

Some JDKs support compatibility configuration options such as `-Dfile.encoding=COMPAT` under JEP 400. This is a **transitional measure** on supporting runtimes, not a long-term substitute for specifying an explicit charset. Do not rely on setting `file.encoding` to an arbitrary charset name if the runtime/JDK does not guarantee that behavior.

### 8.3. Checking the Actual Charset

~~~java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
System.out.println(System.getProperty("file.encoding"));
System.out.println(System.getProperty("native.encoding"));
~~~

`native.encoding` is environment information available in modern JDKs; its availability and value must be confirmed on the specific JDK release.

In tests, record the exact runtime/vendor/build and startup options. Merely inspecting `file.encoding` in the environment and inferring the actual bytes is insufficient if the code passes a different charset when constructing a `Reader`.

## 9. File Reads/Writes Must Declare Encoding

### 9.1. Using `StandardCharsets.UTF_8`

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("data", "customers.csv");

Files.writeString(file,
    "id,name\n1,Nguyễn Ánh\n",
    StandardCharsets.UTF_8);

String text =
    Files.readString(file, StandardCharsets.UTF_8);
~~~

`Files.readString` and `writeString` have overloads that default to UTF-8 in modern APIs, yet passing the charset explicitly makes the contract easier to inspect. With `Path.of`/`readString`, ensure the target Java runtime supports these APIs.

### 9.2. Do Not Automatically Use UTF-8 to Read Legacy Bytes

If a system stored files in Windows-1258, Shift_JIS, ISO-8859-1, or another legacy charset, reading them directly as UTF-8 will cause errors or corrupt data.

Conversion workflow:

1. Identify the true encoding from the protocol, metadata, or producer source.
2. Decode using the source charset.
3. Validate the Unicode content and handle malformed bytes according to policy.
4. Encode into UTF-8 or the target charset.
5. Reconcile data, record counts, and checksums if appropriate.
6. Record version/encoding metadata after conversion.

It is impossible to determine the exact charset for every file just by "looking at bytes"; byte sequences are sometimes valid across multiple encodings. When no trusted source exists, a data identification and sign-off workflow is needed.

### 9.3. Controlling Malformed/Unmappable Input

By default, some decoding APIs replace invalid bytes with the replacement character. For critical business data where you want to **detect wrong encodings** instead of silently substituting characters, use `CharsetDecoder`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class StrictUtf8 {
    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
    }
}
~~~

This is useful when parsing digitally signed files, financial data, or contracts requiring zero character loss. For user-facing display data, the replacement policy may differ, but it must be explicit.

### 9.4. BOM and Newlines

UTF-8 can have a byte order mark (BOM) at the start of a file. A custom-written CSV/JSON parser may treat the BOM as part of the first field if unhandled. UTF-16 has different byte order and BOM requirements.

Line endings also vary by OS (`\n`, `\r\n`). When comparing files at the byte level, separate **newline changes** from **charset changes**. Do not normalize everything before testing if the actual protocol requires a byte-for-byte match.

## 10. HTTP, CSV, JSON, Database, and Queues

Charset migrations often surface at service boundaries.

### 10.1. HTTP Content-Type and Body Bytes

If an endpoint receives or returns text, specify the charset according to the media type and protocol. For JSON, modern systems typically use UTF-8 per the corresponding standard; do not rely on the default charset of a servlet container or an `OutputStreamWriter` without specifying an encoding.

Example with the Java HTTP client when manually creating a body from text:

~~~java
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String json = "{\"name\":\"Nguyễn Ánh\"}";

HttpRequest.BodyPublisher body =
    HttpRequest.BodyPublishers.ofString(
        json, StandardCharsets.UTF_8);
~~~

When testing HTTP, inspect **bytes on the wire**, response headers, client decoding policy, and round-trip content—do not only compare `String`s after the framework has automatically converted them.

### 10.2. CSV and File Import/Export

CSV does not inherently specify its charset, separator, quote, and newline. A Vietnamese file exported from an old system might use an encoding other than UTF-8, and the column separator can also vary depending on the spreadsheet tool's locale.

Regression tests should include:

- UTF-8 with/without BOM per contract.
- Vietnamese, Japanese, Arabic names, emoji, and combining marks.
- Commas, semicolons, quotes, and newlines inside quoted fields.
- Empty/null data and Unicode whitespace.
- Large sizes and chunk boundaries in streaming parsers.
- Round-trip export → import and byte-level assertions when needed.

### 10.3. JDBC/Database Collation

A JDBC driver exchanges data according to the protocol/database encoding, not necessarily using `Charset.defaultCharset()` directly. However, the application may generate raw bytes on its own, or database collation may govern text ordering/uniqueness.

Check:

- Database/server/client encoding.
- How `String`/`NString` and Unicode columns are bound.
- Collation and case/accent comparison behavior.
- Indexes/search keys requiring rebuild when collation changes.
- Which encoding migration scripts use to read SQL files.
- Truncation rules by bytes, code points, or characters.

A unique constraint under a new collation may identify two strings as "duplicates" differently than before. This is a regression capable of affecting data, not merely the UI.

### 10.4. Kafka/Message Brokers and Object Storage

If payloads are bytes, producers and consumers must agree on serialization/charset. A new Java consumer defaulting to UTF-8 cannot "fix" bytes written by a legacy producer in another encoding without metadata.

If events are stored long-term, they should have schemas/versions and an invariant format. When changing codecs, test old consumers reading data produced by new producers and vice versa according to the compatibility contract.

## 11. Unicode Normalization and Character Limits

Unicode allows certain visually identical strings to have different sequences of code points.

Vietnamese example:

~~~java
String nfcLike = "ắ";               // U+1EAF
String decomposed = "a\u0306\u0301"; // a + breve + acute

System.out.println(nfcLike.equals(decomposed));
// false
~~~

To compare for canonical equivalence by choosing an NFC policy:

~~~java
import java.text.Normalizer;

String a =
    Normalizer.normalize(nfcLike, Normalizer.Form.NFC);
String b =
    Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(a.equals(b)); // true
~~~

### 11.1. NFC/NFD and NFKC/NFKD Are Different

- **NFC/NFD:** canonical composition/decomposition.
- **NFKC/NFKD:** compatibility normalization, which can lose meaningful distinctions in certain data.

Do not apply NFKC to all proper names or legal records just for "maximum normalization." Choose the form based on the data contract and preserve the original when required.

### 11.2. `String.length()` Does Not Count Visible Characters

~~~java
String emoji = "😀";

System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(
    emoji.codePointCount(0, emoji.length())
); // 1 Unicode code point
~~~

A grapheme cluster can even consist of multiple code points, such as an emoji sequence joined by zero-width joiners or a letter with combining marks. If the UI limits input to "20 characters," define whether the unit is bytes, UTF-16 code units, code points, or grapheme clusters.

### 11.3. Checking Unicode Classification

`Character.isLetter`, `isDigit`, and regex Unicode properties can depend on the JDK's Unicode data. Newly added code points may be recognized differently between JDKs.

Example:

~~~java
boolean isUnicodeDigit = Character.isDigit('١');
boolean isAsciiDigit = '١' >= '0' && '١' <= '9';

System.out.println(isUnicodeDigit); // true
System.out.println(isAsciiDigit);   // false
~~~

If a transaction ID accepts only ASCII digits, use an explicit policy instead of `Character.isDigit`. If person names accept multiple scripts, also test combining marks, code points outside the BMP, and the scripts supported by the product.

### 11.4. Do Not Use a Normalizer as Anti-Spoofing Protection

Some characters from different scripts look similar (*confusables*). NFC does not turn every visually similar character into the same value. For usernames/sensitive identifiers, also apply appropriate mixed-script, uniqueness, and anti-spoofing policies.

## 12. Java Time API: Choosing the Right Data Type

`java.time` clearly distinguishes **absolute points in time** from **date/time representations on a local calendar**.

| Type | Stored information | Purpose |
|---|---|---|
| `Instant` | Point on the UTC timeline | Event timestamps, audit logs, ordering |
| `LocalDate` | Date without a zone | Birthdays, holidays, accounting dates |
| `LocalTime` | Time of day without a zone | Scheduled opening hours |
| `LocalDateTime` | Local date/time, without zone/offset | User-entered appointment time before attaching a zone |
| `OffsetDateTime` | Date/time + UTC offset | Transmitting timestamps with offsets |
| `ZonedDateTime` | Date/time + region zone + current offset | Schedules dependent on DST/region rules |
| `Duration` | Amount of time on the timeline | Timeouts, elapsed seconds |
| `Period` | Calendar span in years/months/days | Adding months, billing schedules |
| `ZoneId` | Region ID or offset | `Asia/Ho_Chi_Minh`, `America/New_York` |
| `Clock` | Abstract time source | Writing deterministic tests |

**Do not use `LocalDateTime` alone to represent a global instant.** It carries no offset/zone, so multiple instants can map to the same local date-time in regions with DST overlaps.

### 12.1. Persisting Event Timestamps as Instants

~~~java
import java.time.Instant;

Instant createdAt = Instant.parse(
    "2024-10-01T08:30:00Z");

System.out.println(createdAt.toString());
~~~

The `Instant.toString()` format is suitable for many ISO 8601/UTC contracts. When presenting to users, convert to the appropriate zone and locale; do not modify the stored `Instant` value.

### 12.2. Displaying Instants in the User's Zone

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant event = Instant.parse(
    "2024-10-01T08:30:00Z");

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime local = event.atZone(zone);

System.out.println(local);
~~~

For Vietnam's timezone at the example date, UTC+07:00 applies. However, **do not hard-code `+07:00` for all regions/timestamps**, and do not use a fixed offset when region rules with DST must be represented.

## 13. Default Timezone Is Not Business Data

~~~java
import java.time.ZoneId;

ZoneId current = ZoneId.systemDefault();
System.out.println(current);
~~~

This value can differ across laptops, Linux hosts, containers, and CI servers. Using `ZoneId.systemDefault()` where payment deadlines or appointment times are determined can cause results to change after migrating infrastructure.

A clearer example:

~~~java
ZoneId businessZone =
    ZoneId.of("Asia/Ho_Chi_Minh");
~~~

If a service handles international appointments, the zone should come from the account/event location rather than defaulting to the server's timezone.

### 13.1. `UTC` and Region Zones Are Not Equivalent

`ZoneOffset.UTC` is a fixed offset of 0. `Europe/Paris` or `America/New_York` is a region zone whose offset rules change over time and history. `ZoneId.of("+07:00")` is a fixed offset; `ZoneId.of("Asia/Ho_Chi_Minh")` is a region with historical data that may experience policy changes in the future.

If the business rule is "opens at 09:00 local time in a given city," store the region zone and appropriate conversion rules, not just the current UTC offset.

### 13.2. The Timezone DB Is Versioned Data

The JDK bundles timezone rules from the **IANA Time Zone Database (TZDB)** per the corresponding update. Countries can change DST rules or offsets by legislation. A new JDK patch release can update TZDB, causing calculations for a future date to differ from an older release.

You can inspect the zone rules version via the API:

~~~java
import java.time.zone.ZoneRulesProvider;

String version =
    ZoneRulesProvider.getVersions(
        "America/New_York").lastKey();

System.out.println(version);
~~~

The set of versions and how they are reported depend on the provider; tests should record the JDK/vendor/build and TZDB version when comparing.

**Do not freeze future offsets in an assertion if the business intends to follow legal timezone changes.** Conversely, if a transaction schedule was finalized based on the rule set at booking time, define how TZDB updates should be handled.

## 14. DST Gaps and Overlaps: Mandatory Testing for Appointments

DST creates two prominent transition types:

- **Gap:** a span of local time that does not exist because the clock jumps forward.
- **Overlap:** a span of local time that repeats because the clock falls back.

These are not bugs in `java.time`. They are business cases whose handling must be defined.

### 14.1. Gap Example in New York

In `America/New_York`, on **2024-03-10** during DST spring-forward, local time `02:30` does not exist.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(
    2024, 3, 10, 2, 30);

ZoneRules rules = ny.getRules();

System.out.println(
    rules.getValidOffsets(missing).size()
); // 0 with 2024 New York TZDB rules
~~~

When converting `LocalDateTime.atZone(ny)`, the API uses default resolver rules and may shift the local time across the gap. Yet in a scheduling application, you should not silently shift `02:30` to another time without notifying the user.

Possible policies include:

1. Reject the nonexistent time and ask the user to choose again.
2. Shift to the nearest valid time per product rules.
3. Choose a deterministic time according to an explicit domain contract.

Tests must verify the chosen policy, not just that the API does not throw an exception.

### 14.2. Overlap Example in New York

On **2024-11-03**, `01:30` occurs twice with two different offsets.

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime ambiguous = LocalDateTime.of(
    2024, 11, 3, 1, 30);

System.out.println(
    ny.getRules().getValidOffsets(ambiguous).size()
); // 2 with New York rules at this point
~~~

If constructing a `ZonedDateTime` solely from `LocalDateTime` and `ZoneId` without an overlap policy, the API chooses an offset by default. Business scheduling may need to ask the user "first or second occurrence," or store the specific offset.

### 14.3. Using `ZoneRules` for Validation

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class AppointmentTime {
    public static ZonedDateTime requireUnambiguous(
            LocalDateTime local,
            ZoneId zone) {
        List<ZoneOffset> offsets =
            zone.getRules().getValidOffsets(local);

        if (offsets.size() != 1) {
            throw new IllegalArgumentException(
                "Gap or overlap: " + local + " in " + zone);
        }

        return ZonedDateTime.ofStrict(
            local, offsets.get(0), zone);
    }
}
~~~

This example defines a strict contract: **accept only local times that have exactly one valid offset**. A real application may have different rules, but they must be tested explicitly.

### 14.4. Do Not Use Local Time Differences in Place of Elapsed Duration

A night across a DST transition may not be exactly 24 hours of elapsed time. Compare:

~~~java
import java.time.Duration;
import java.time.ZonedDateTime;

ZonedDateTime before =
    ZonedDateTime.parse(
        "2024-03-09T12:00:00-05:00[America/New_York]");
ZonedDateTime after = before.plusDays(1);

System.out.println(
    Duration.between(before, after).toHours()
); // 23 across spring-forward
~~~

`plusDays(1)` performs calendar arithmetic by local day, whereas `plusHours(24)` advances a different amount of time. For billing, SLAs, schedules, and token expiration, choose the right definition between **calendar time** and **elapsed time**.

## 15. Parsing and Formatting Dates and Times by Locale

### 15.1. Display Formatting by Locale

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 10, 1);

String french =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.FRANCE)
        .format(date);

System.out.println(french);
~~~

Output depends on locale data and style. Do not use it as an invariant API timestamp. Use explicit ISO formats for machine-readable data:

~~~java
String machineDate =
    DateTimeFormatter.ISO_LOCAL_DATE.format(date);
// 2024-10-01
~~~

### 15.2. Pattern Symbols and Literal Letters

~~~java
DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern(
        "dd/MM/uuuu", Locale.ROOT);
~~~

Distinguish `M` (month) from `m` (minute), `u` (proleptic year) from `Y` (week-based year), and `d` (day of month) from `D` (day of year). A pattern using `YYYY` instead of `uuuu` can yield a different year on dates near the start/end of the year under week-based-year rules, which are affected by locale.

Do not confuse format pattern bugs with TZDB/CLDR regressions. Also test end-of-month dates, year-end dates, leap days, and transition dates.

### 15.3. `WeekFields` by Locale

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

DayOfWeek firstInUs =
    WeekFields.of(Locale.US).getFirstDayOfWeek();

DayOfWeek firstInFrance =
    WeekFields.of(Locale.FRANCE).getFirstDayOfWeek();
~~~

Calendar UIs and weekly reports may use different first-day-of-week orders or minimal-days rules. If the product requires ISO weeks, choose `WeekFields.ISO`; do not use the default locale and assume weeks always start on Monday.

### 15.4. Calendars Are Not Always the Gregorian Calendar

Some locales/calendar extensions represent different calendar systems. If an application serves multiple countries, do not assume every date displays with the same era and month names. A specific `Chronology` or format policy may be required.

At the event-storage level, use `Instant`/ISO chronology when specified by the contract, then convert to the display calendar at the UI boundary.

## 16. Do Not Let Tests Depend on Uncontrolled `now()`

A test like:

~~~java
LocalDate today = LocalDate.now();
~~~

can fail when run across midnight, in a different timezone, or during a DST transition hour. Use `Clock` to make tests deterministic:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock frozen = Clock.fixed(
    Instant.parse("2024-10-01T23:30:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate businessDate = LocalDate.now(frozen);

System.out.println(businessDate); // 2024-10-02
~~~

A service design should accept a `Clock` or time-provider function via dependency injection. In tests, inject a fixed clock; in production, use `Clock.system(...)` with the contract's zone.

### 16.1. Testing Boundaries

The test suite should include:

- Before/after midnight in the business zone.
- Before/after a DST transition time.
- Leap day 29/02 and 01/03.
- End of year, ISO week 1, and week-based year differing from calendar year.
- Timestamps with different offsets representing the same `Instant`.
- Dates far in the past or future, where TZDB data may differ.
- Timeouts measured by `Duration`/monotonic elapsed time rather than wall-clock time to avoid NTP adjustments.

For internal timeouts and latency measurement, use a monotonic time source such as `System.nanoTime()` under the appropriate contract, rather than measuring differences of `LocalDateTime.now()` which can jump due to system clock adjustments.

## 17. Multi-JDK/Locale/Charset/Timezone Regression Matrix

Running every combination is not necessary; prioritize the dimensions that actually affect the application.

| Axis | Configuration examples | Goal |
|---|---|---|
| JDK | Current version, target version, supported patches/vendors | Detect library data/runtime changes |
| Locale | `vi-VN`, `en-US`, `fr-FR`, `tr-TR`, `ja-JP` | Numbers, dates, case, resource bundles |
| Default zone | `UTC`, `Asia/Ho_Chi_Minh`, `America/New_York` | Avoid server-timezone dependence |
| Source charset | UTF-8, ISO-8859-1, a legacy encoding if applicable | Decode/encode and byte migration |
| Data form | NFC/NFD, combining marks, supplementary | Unicode handling |
| OS/container | Linux, Windows, or target image | Locale, filesystem, console, tzdata |
| Protocol | CSV, JSON, DB, broker, file export | End-to-end bytes and schema |

A minimal matrix for an e-commerce/retail application might include:

1. **Vietnam baseline:** `vi-VN`, `Asia/Ho_Chi_Minh`, UTF-8.
2. **Locale contrast:** `fr-FR` to check decimal and grouping separators.
3. **Case mapping:** `tr-TR` to expose code relying on default lowercase.
4. **DST case:** `en-US` with `America/New_York` at gap/overlap.
5. **Machine contract:** `Locale.ROOT`, UTC, UTF-8, and ISO formats.
6. **Legacy import:** files with the actual source charset saved in the old system.

### 17.1. Selecting Tests by Risk

- If the system only uses Vietnam time, you still need to check UTC day-boundary hours and zone history; New York DST can be a separate test case for shared libraries.
- If customer names are multilingual, Unicode/normalization and database collation must be prioritized.
- If legacy files are not used, there is no need to force dozens of extra charsets just to inflate test counts.
- If there is global deployment, test the locales/zones covered by the product's support policy.

### 17.2. Recording the Environment

Each result should record:

~~~text
JDK vendor:
JDK feature/update/build:
java.version:
java.vendor:
Charset.defaultCharset:
file.encoding:
native.encoding (if present):
Locale default:
Locale FORMAT:
Locale DISPLAY:
ZoneId.systemDefault:
TZDB version(s):
OS/container image:
Database collation/encoding:
Test fixture version:
~~~

This information helps distinguish JDK regressions from CI runner differences.

## 18. JUnit 5 Example: Testing with an Explicit Locale

The example below assumes the project has matching `org.junit.jupiter` dependencies.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class LocaleRegressionTest {

    @ParameterizedTest
    @ValueSource(strings = {"vi-VN", "fr-FR", "en-US"})
    void numberRoundTripWithExplicitLocale(
            String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);

        DecimalFormat format = (DecimalFormat)
            NumberFormat.getNumberInstance(locale);

        format.setGroupingUsed(false);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setParseBigDecimal(true);

        BigDecimal expected = new BigDecimal("1234.50");
        String text = format.format(expected);

        ParsePosition end = new ParsePosition(0);
        Object parsed = format.parse(text, end);

        assertEquals(text.length(), end.getIndex());
        assertEquals(expected, parsed);
    }
}
~~~

This tests the **internal format–parse contract under the same locale**, not that string representations remain unchanged across CLDR versions. If the API requires an exact string, add fixture tests under a separate contract.

### 18.1. Do Not Let JUnit Tests Change the Global Locale

The tests above pass a locale into a dedicated formatter, so they do not need `Locale.setDefault` and can run concurrently more safely. If legacy code only calls `NumberFormat.getInstance()` without passing a locale, test it in a separate process with the default locale set at startup rather than mutating JVM state while other tests are running.

### 18.2. Checking Turkish Lowercase

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class CaseMappingTest {

    @Test
    void languageSensitiveLowercaseIsExplicit() {
        Locale turkish = Locale.forLanguageTag("tr-TR");

        assertEquals("ı", "I".toLowerCase(turkish));
        assertEquals("i", "I".toLowerCase(Locale.ROOT));
    }
}
~~~

This test has explicit expected values per case-mapping rules, helping catch code that accidentally uses the default locale.

## 19. JUnit Example: Charset Round-Trip and Malformed Bytes

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class CharsetRegressionTest {

    @Test
    void vietnameseTextRoundTripsInUtf8() {
        String original = "Đặng Ánh - Hà Nội - 😀";
        byte[] bytes = original.getBytes(
            StandardCharsets.UTF_8);

        String decoded = new String(
            bytes, StandardCharsets.UTF_8);

        assertEquals(original, decoded);
    }

    @Test
    void rejectsMalformedUtf8() {
        byte[] malformed = {(byte) 0xC3, (byte) 0x28};

        assertThrows(CharacterCodingException.class, () ->
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(malformed))
        );
    }
}
~~~

Do not write a test that only uses `new String(original.getBytes())` on the same runtime; if both steps use the same wrong default charset, the test can still pass even when data is incompatible with other systems.

**Cross-boundary test:** encode with the source process/runtime into file bytes, decode with the target runtime, and compare against expected text; also test the reverse direction while the system still supports rollback.

### 19.1. Comparing Bytes Where the Contract Requires It

For example, a system produces JSON or CSV with checksums, digital signatures, or hash keys depending on bytes. Two visually identical strings to a human reader may have different NFC/NFD bytes.

Tests must specify the normalization form and encoding before computing hashes. If the product only requires semantic equality, do not force byte hashes of locale-sensitive output to always stay identical across every CLDR upgrade.

## 20. JUnit Example: DST Gap, Overlap, and Instant

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import org.junit.jupiter.api.Test;

class ZoneRegressionTest {

    private static final ZoneId NEW_YORK =
        ZoneId.of("America/New_York");

    @Test
    void springForwardHasMissingLocalTime() {
        LocalDateTime local = LocalDateTime.of(
            2024, 3, 10, 2, 30);

        assertEquals(0,
            NEW_YORK.getRules().getValidOffsets(local).size());
    }

    @Test
    void fallBackHasAmbiguousLocalTime() {
        LocalDateTime local = LocalDateTime.of(
            2024, 11, 3, 1, 30);

        assertEquals(2,
            NEW_YORK.getRules().getValidOffsets(local).size());
    }

    @Test
    void calendarDayMayNotBe24ElapsedHours() {
        ZonedDateTime before = ZonedDateTime.parse(
            "2024-03-09T12:00:00-05:00[America/New_York]");

        ZonedDateTime nextDay = before.plusDays(1);

        assertEquals(23,
            Duration.between(before, nextDay).toHours());
    }

    @Test
    void timestampRepresentationRoundTrips() {
        Instant original = Instant.parse(
            "2024-10-01T08:30:00Z");

        assertEquals(original,
            Instant.parse(original.toString()));
    }
}
~~~

These historical dates were chosen to illustrate the New York DST rules in effect at those timestamps. When running in an environment using a custom TZDB or different rules, tests should record the version and explain the discrepancy. For **future** events, timezone rules can change by law, so avoid freezing offsets prematurely if the business contract must follow updated data.

## 21. Testing Default Environment in a Separate Process

To catch code that depends on JVM defaults, you can run a small diagnostic program:

~~~java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class EnvironmentProbe {
    public static void main(String[] args) {
        System.out.println(
            "java.version=" + System.getProperty("java.version"));
        System.out.println(
            "java.vendor=" + System.getProperty("java.vendor"));
        System.out.println(
            "locale=" + Locale.getDefault().toLanguageTag());
        System.out.println(
            "formatLocale=" +
            Locale.getDefault(Locale.Category.FORMAT)
                .toLanguageTag());
        System.out.println(
            "charset=" + Charset.defaultCharset());
        System.out.println(
            "zone=" + ZoneId.systemDefault());
    }
}
~~~

Example run with predefined locale/timezone environments:

~~~bash
javac EnvironmentProbe.java

java -Duser.language=vi -Duser.country=VN \
     -Duser.timezone=Asia/Ho_Chi_Minh \
     EnvironmentProbe

java -Duser.language=tr -Duser.country=TR \
     -Duser.timezone=America/New_York \
     EnvironmentProbe
~~~

Line-continuation commands use Unix-style shell syntax. On Windows PowerShell 5.1, put the command on a single line or use the appropriate line-continuation syntax.

### 21.1. Why Is Process Isolation Better Than `Locale.setDefault` in Tests?

Startup options establish a predictable testing condition for the **entire process**. Code that relies on the default locale, timezone, or default charset can be observed without racing against other tests in the same JVM.

Note: `user.language`/`user.country` is not the only mechanism for all locale extensions, and timezone/container environments can introduce further effects. To test complex locale-specific formatting, passing `Locale` and `ZoneId` directly into the API remains the clearest approach.

### 21.2. Do Not Use Arbitrary `-Dfile.encoding` Instead of an Explicit Charset

When testing default-charset differences, you can use the real source/target runtime environment and policies supported by the JDK. Setting `-Dfile.encoding=COMPAT` can be useful as a diagnostic step on supporting JDKs, but it does not replace fixing the code to pass an explicit charset.

To test legacy encodings deterministically, generate file bytes in fixtures using the appropriate `Charset.forName("...")` rather than relying on whatever OS default happens to be on the runner.

## 22. Golden Fixtures for Internationalized Data

Fixtures should be chosen purposefully rather than using only a few ASCII names.

| Group | Sample data | What to check |
|---|---|---|
| ASCII | `ABC123`, `-_.` | Fixed protocol grammar |
| Precomposed Vietnamese | `Nguyễn Ánh`, `Đặng Thị Hòa` | UTF-8, collation, case |
| Decomposed Vietnamese | `a\u0306\u0301` and equivalent NFC form | Normalization, uniqueness |
| CJK/Japanese | `中文`, `東京` | Unicode decoding, font/output pipeline |
| Arabic script | `العربية` | UTF-8, directionality, bidi |
| Non-ASCII digits | `١٢٣` | Validation vs numeral display |
| Supplementary Unicode | `😀` or code points outside BMP | UTF-16 vs code point length |
| Combining characters | `e\u0301` | NFC/NFD, search |
| Unicode whitespace | U+00A0, U+2003, tab | Trim/strip/parse differences |
| Decimal/grouping marks | Locales fr-FR/en-US/vi-VN | NumberFormat, strict parse |
| Leap day | 29/02/2024 | Calendar/date arithmetic |
| DST gap | New York 10/03/2024 02:30 | Invalid local time |
| DST overlap | New York 03/11/2024 01:30 | Ambiguous local time |
| UTC crossing midnight | 23:30 UTC | Business date per zone |
| Year-end week | 29–31/12 and 01–03/01 | ISO week vs locale week |
| Legacy-encoded file | ISO-8859-1 bytes or true source encoding | Migration decoding |

### 22.1. Saving Both Text and Bytes

When building fixtures for charsets, save representative samples at **two levels**:

~~~text
fixtures/
  customer-utf8.txt
  customer-utf8.sha256
  customer-legacy.bin
  customer-legacy.expected.txt
  nfc-vietnamese.txt
  nfd-vietnamese.txt
  numbers-fr.expected.json
  timezone-cases.json
~~~

`*.bin` files must be generated from a known encoding and carry metadata. Do not guess the legacy charset at test runtime.

### 22.2. Recording Which Type of Expectation Applies

A fixture can be:

- **Normative/contract fixture:** bytes/text must be invariant.
- **Semantic fixture:** parsed values/timepoints are equivalent; presentation may differ.
- **Snapshot for review:** UI output may change with CLDR but must be reviewed.
- **Migration fixture:** the product must read data created by the old version, not necessarily write back identically.

If every fixture uses exact-string assertions, the team will encounter many "false positives" when locale data updates. If every fixture only checks parse success, serious semantic bugs can be missed.

## 23. Comparing Source JDK and Target JDK

An effective test plan keeps as many variables constant as possible.

~~~text
Same application commit / artifact
Same dataset / test fixture
Same test matrix
            |
   +--------+--------+
   |                 |
   v                 v
Source JDK       Target JDK
   |                 |
   +--------+--------+
            |
            v
Compare:
- semantic values
- exact protocol bytes
- UI snapshot deltas
- logs and environment identity
            |
            v
Classify intentional vs regression
~~~

If upgrading framework, JDK, database collation, and container image simultaneously, add variable-isolation experiments:

1. Old app on old JDK + old environment.
2. Old app on new JDK + equivalent environment if supported.
3. New app on new JDK + old environment when feasible.
4. New app on new environment/container.

Not every combination is runnable; document blockers explicitly. The goal is to identify **which change caused the difference**, not simply to produce more builds.

### 23.1. Cross-Version Read/Write

If the system has file exports, caches, queues, or persisted JSON from the old runtime, verify:

~~~text
Writer old JDK -> Reader old JDK
Writer old JDK -> Reader new JDK
Writer new JDK -> Reader new JDK
Writer new JDK -> Reader old JDK (if rollback is still supported)
~~~

An encoding or format change can prevent the old binary from reading data written by the new binary. Hence this is also a **rollback condition**, not merely a UI i18n problem.

### 23.2. Running the Right Artifact on the Right JVM

With Maven Toolchains/Gradle toolchains, the compiler JDK and test JVM can differ. An artifact compiled with `--release 17` does not prove tests ran on Java 17. Record `java.version`, `java.home`, artifact hash, and selected profile in CI.

## 24. CI Configuration and Avoiding Flaky Tests

### 24.1. Pinning What Must Be Pinned

For machine-to-machine data tests, explicitly specify:

- `Locale.ROOT` or an explicit locale.
- `StandardCharsets.UTF_8` or the protocol's charset.
- `ZoneId.of(...)` or UTC per contract.
- `Clock.fixed(...)` for current time.
- `DateTimeFormatter.ISO_*` or a formatter with a defined pattern.
- Explicit rounding mode/scale for monetary values.
- Canonical normalization form when comparing identifiers.
- Verified sample data and expected values.

### 24.2. Do Not Lose Regression Detection Capability by Pinning Every Default

If the product genuinely depends on the real default locale or timezone, tests using only UTC/`Locale.ROOT` will fail to detect issues. Maintain **two tiers**:

- A deterministic core tier with explicit parameters.
- An environment compatibility tier running processes under representative locales/zones.

The second tier requires separate processes to avoid race conditions when tests modify JVM globals.

### 24.3. Container Timezone Data

A container image may lack an OS timezone database, while the JVM uses timezone rules built into the JDK. Some system utilities like `date` or native libraries read the OS tzdata instead.

Therefore, `date` displaying a given offset inside a Linux container does not prove on its own that `java.time.ZoneId` uses the exact same data source. Record and verify both if the application mixes Java and native/OS APIs.

### 24.4. Locale Data Updates Can Create Test Noise

If a UI snapshot changes due to CLDR:

1. Identify which field changed.
2. Inspect the JDK/CLDR update and affected locale.
3. Verify the format remains semantically correct.
4. Review UX and translation requirements.
5. Update snapshots intentionally only after verification.
6. Document release notes if consumers/customers are affected.

Do not automatically strip out all formatting assertions claiming "locales are unstable"; balance data flexibility with product requirements.

## 25. Common Symptoms and How to Diagnose Them

| Symptom | Possible cause | Evidence to capture |
|---|---|---|
| Monetary amounts change separators | Default locale/CLDR/provider changed | `Locale`, `NumberFormat`, JDK build |
| Parse reads partial string without error | `NumberFormat.parse` accepts prefixes | `ParsePosition` and full length |
| `I` lowercases to `ı` | Locale tr-TR used implicitly | Lowercase call and default locale |
| Sort order changes | Different `Collator`/database collation provider/version | `Collator`/database collation, fixtures |
| Vietnamese names show `�` | Wrong charset decoding/malformed bytes | Source hex bytes, source/target charset |
| CSV corrupts first column | Different BOM or separator/quote | Hex bytes, header, parser config |
| `Properties` misreads accents | Confusing `load(InputStream)` with UTF-8 | API overload, file encoding |
| ResourceBundle missing translations | Bundle fallback/key or resource packaging | Bundle names, locale, artifact contents |
| UI date flips day/month order | Locale/style provider changed | Locale, formatter, CLDR version |
| Appointment date shifts by one day | Default timezone changed | Instant, zone, `systemDefault` |
| DST appointment time shifts | Default gap resolution | `ZoneRules.getValidOffsets` |
| Two appointments show identical local time | DST overlap | Offset of each instant, region zone |
| "One day" is only 23/25 hours | Calendar day vs Duration | `plusDays`/`plusHours` code |
| Test fails near midnight | Unfixed `now()` | `Clock`, CI timezone |
| Test hash differs despite identical-looking text | NFC/NFD, encoding, or newline | Code points, bytes, normalization |
| New JDK patch changes future schedules | TZDB update | TZDB version/rules, policy |
| API returns UI string instead of ISO | Locale-dependent format in protocol | Response bytes/schema, formatter |

### 25.1. Printing Code Points Instead of Only Viewing Characters in Logs

~~~java
String text = "a\u0306\u0301";

text.codePoints().forEach(cp ->
    System.out.printf("U+%04X%n", cp));
~~~

Two strings with nearly identical visual appearance can have different code points. Logging both code points and sample bytes helps distinguish normalization issues from charset corruption.

When logging real user data, comply with personal data protection policies; use synthetic fixtures for tests and bug tickets.

### 25.2. Distinguishing Parsing Bugs from Display Bugs

An improperly decoded `String` may be "valid" in memory according to the wrong bytes and get locale-formatted cleanly—while the result is still wrong. Conversely, correct bytes/Unicode with a UI font missing glyphs can display square boxes; that is not a `CharsetDecoder` bug.

Investigate layer by layer: source bytes → decoded code points → normalized string → formatted output → font/UI.

## 26. Recommended Migration Workflow

### Step 1: Inventory

Find usages of:

~~~text
Locale.getDefault()
Locale.setDefault(...)
ZoneId.systemDefault()
TimeZone.getDefault()
new Date()
LocalDate.now()
LocalDateTime.now()
new String(bytes)
String.getBytes()
InputStreamReader(...)
OutputStreamWriter(...)
String.format(...)
NumberFormat.getInstance()
DateTimeFormatter.ofLocalized...
SimpleDateFormat
Collator
ResourceBundle
MessageFormat
Properties.load(InputStream)
Charset.defaultCharset()
~~~

There is no need to fix everything immediately. Categorize by impact: protocol/financial, persistence, user display, and debug logs.

### Step 2: Define the Contract

Explicitly document:

- Text encoding at each boundary.
- Locale and currency policy for UI.
- UTC instant and region zone for schedules.
- Normalization and identity policy.
- Invariant formats for APIs/files.
- Resource bundle fallback.
- Whether the old version can read new data if rollback is required.

### Step 3: Write Fixtures and Unit Tests

Create multilingual datasets, legacy bytes, locale numbers/dates, DST gaps/overlaps, and near-midnight cases. Prefer explicit API parameters and `Clock.fixed`.

### Step 4: Run Source and Target JDKs

Keep the same artifact/test matrix where possible and record runtime/env details. For default-locale tests, run separate processes; for contract tests, use explicit locale/charset/zone.

### Step 5: End-to-End Testing

Test file import/export, HTTP payloads, DB collation, queue messages, search indexes, and logs. Do not test only unit-level formatters, as data can corrupt at byte boundaries.

### Step 6: Classify Differences

| Difference type | Action |
|---|---|
| Violates machine contract/bytes | Fix before deployment |
| Wrong parsing or lost Unicode data | Fix encoding/schema/validation |
| Wrong instant or business DST behavior | Fix policy/time conversion |
| CLDR display changed but valid | Review UX and intentionally update snapshots |
| Reindex needed due to collation | Plan data migration |
| New data cannot be read by old runtime | Close rollback gate or prepare a fallback-compatible release |

### Step 7: Canary, Monitoring, Rollback

Monitor parse errors, replacement-character counts, resource-lookup failures, timestamp skew, rejected-input rates, and business invariants. Before rolling back, verify whether the old runtime can safely read/write data created by the new release; rolling back a binary does not automatically revert encoding or data schemas.

## 27. Common Misconceptions

**"Java `String` is always UTF-8."** No. `String` is a character abstraction; UTF-8 is a charset used to encode/decode bytes.

**"Java 18 defaults to UTF-8, so legacy data is automatically right."** No. If source bytes belong to another charset, decode with the source charset before converting.

**"`Properties.load(InputStream)` reads UTF-8 because the JDK defaults to UTF-8."** No. That API follows ISO-8859-1 rules; distinguish it from `load(Reader)` and `PropertyResourceBundle`.

**"Locale only affects message language."** No. It also affects numbers, dates, month names, case mapping, and collation.

**"`Locale.ROOT` is always right for every user."** No. It fits certain machine-to-machine/locale-neutral contracts, whereas UI needs the user's locale.

**"Adding `Locale.setDefault` at the start of a test is enough."** Unsafe for parallel tests and code running in the same JVM.

**"A timestamp without a zone still represents a unique point in time."** No. `LocalDateTime` contains neither offset nor zone.

**"UTC+07:00 and `Asia/Ho_Chi_Minh` are the same kind of data."** No. One is a fixed offset, while the other is a region zone with history/rules.

**"A day is always 24 hours."** Not when using calendar days across DST or calendar contracts that differ from elapsed duration.

**"DST only breaks when changing the JDK."** No. The bug lies in the domain time model and can surface when data/TZDB or infrastructure changes.

**"You can hard-code offsets for future dates."** Risky if governments change timezone rules; an explicit policy is required.

**"Two visually identical strings are always equal."** No. Unicode has distinct canonical-equivalent representations and confusables.

**"`String.length()` is the number of characters the user sees."** No. It counts UTF-16 code units.

**"A changed golden snapshot is definitely a regression."** Not necessarily; CLDR can validly update formatting. However, changes to API bytes or business semantics are still regressions.

**"Testing on one JDK suffices to prove rollback."** No. If new data has been written, the old runtime must be tested reading/writing it back per contract.

## 28. i18n Regression Testing Checklist

- [ ] Source/target JDK, vendor, build, and OS/container recorded.
- [ ] Actual default FORMAT/DISPLAY Locale, Charset, and ZoneId known.
- [ ] Places depending on default locale/charset/timezone inventoried.
- [ ] Machine contracts separated from UI formatting.
- [ ] Fixtures include NFC/NFD Vietnamese, non-Latin scripts, combining marks, and emoji.
- [ ] UTF-8 encode/decode and malformed bytes tested.
- [ ] Conversion of actual legacy charsets for old data tested if applicable.
- [ ] `Properties`/`PropertyResourceBundle` encoding checked.
- [ ] HTTP, CSV, JSON, JDBC, and message payload bytes checked.
- [ ] Decimal/grouping separators, strict parsing, and currency semantics tested.
- [ ] Locale-dependent case mapping and collation tested.
- [ ] ResourceBundle fallback, placeholders, and missing keys checked.
- [ ] UTC instant → local display and near-midnight cases tested.
- [ ] Leap day, week-based year, DST gaps, and overlaps tested.
- [ ] Policy defined for nonexistent or ambiguous local times.
- [ ] `Clock.fixed` used for tests depending on current time.
- [ ] TZDB version inspected if zone rule results differ.
- [ ] Tests needing JVM defaults isolated into separate processes.
- [ ] Runtime/locale/zone matrix executed per actual support policy.
- [ ] Presentation snapshot changes separated from semantic regressions.
- [ ] Data from the new version verified compatible with rollback release if needed.
- [ ] Test evidence recorded and all intentional display-format changes reviewed.

## 29. Technical References

- [JEP 400 – UTF-8 by Default](https://openjdk.org/jeps/400): default charset change in JDK 18, limitations, and compatibility.
- [JEP 252 – Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): locale data and changes since JDK 9.
- [JEP 226 – UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226): encoding when loading resource bundles.
- [`Locale` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): locales, language tags, and categories.
- [`Charset` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): charsets and default charset.
- [`StandardCharsets` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): charsets guaranteed to exist in Java.
- [`NumberFormat` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): locale-aware number formatting/parsing.
- [`ResourceBundle` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): i18n resources and fallback.
- [`Normalizer` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.
- [`DateTimeFormatter` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): patterns and localized date/time formatting.
- [`ZoneRules` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html): DST gaps/overlaps and valid offsets.
- [`ZoneRulesProvider` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRulesProvider.html): timezone rules versions.
- [IANA Time Zone Database](https://www.iana.org/time-zones): timezone data and local policy changes.
- [Unicode Standard](https://www.unicode.org/standard/standard.html): code points, properties, and normalization.

The examples use modern APIs and should be run on the JDK version supported by the project. When verifying a specific CLDR/TZDB/Unicode change, always consult the release notes of the **exact JDK feature/update/vendor** and the temporal/language data the product processes.

## 30. Conclusion

**Locale, charset, timezone, and internationalization are data contracts whose behavior can change when upgrading the JDK, even when source code stays unchanged and the application starts up normally.** Locale data governs numbers/dates/collation; charset determines byte interpretation; TZDB governs region-based time conversions; Unicode normalization and character classification affect validation/search/identifiers.

A solid regression testing strategy is to **pass locale/charset/zone explicitly at critical boundaries, use `Clock` in tests, define invariant machine formats, retain multilingual fixtures, and run a JDK–locale–timezone–encoding matrix**. When output differs, separate acceptable presentation differences from semantic errors or data loss. Do not merely update snapshots or flip environment defaults: verify bytes, code points, instants, business invariants, and cross-version data readability.

Doing so ensures the migration not only "passes the build," but also **preserves the accuracy of international user data and time/language-dependent business behavior**.
