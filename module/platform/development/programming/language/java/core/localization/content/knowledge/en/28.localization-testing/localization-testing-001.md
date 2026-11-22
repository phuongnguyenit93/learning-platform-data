# Locale Testing Matrix: vi-VN, en-US, de-DE, tr-TR, and Right-to-Left Languages in Java

## 1. Why Does an English Test Suite Not Guarantee Correct Localization?

A Java program can run perfectly with `Locale.US` yet fail when users choose Vietnamese, German, Turkish, or a **right-to-left (RTL)** language. Bugs can hide in:

- Formatting of **numbers, thousand separators, decimal points, percentages, and currencies**.
- **Day/month/year order**, month names, time zones, and parsing date strings back.
- **Language-specific casing**, especially the letter I in Turkish.
- **`ResourceBundle` translation loading**, fallback, and missing keys or placeholders.
- **Language-aware sorting** with `Collator` instead of `String.compareTo`.
- **RTL layout**, icon/button placement, punctuation, numbers, and mixed Latin/Arabic/Hebrew text.
- **Translation length**, Unicode combining marks, emoji, text overflow, and accessibility issues.
- Bugs that appear only when a server uses a **different default locale** from the development environment.

Therefore, a **locale matrix** is not just a list of languages to "open and take a look at", but a QA plan with clear data, conditions, expectations, test types, and evaluation criteria.

This lesson uses **Java 17+**, focusing on six representative locales:

1. `vi-VN` — Vietnamese in Vietnam;
2. `en-US` — English in the United States;
3. `de-DE` — German in Germany;
4. `tr-TR` — Turkish in Turkey;
5. `ar-EG` — Arabic in Egypt, an RTL language;
6. `he-IL` — Hebrew in Israel, an RTL language.

**Terminology note:** `Locale` is not the entire test case. Each locale must also be tested against specific data/context, with font, viewport, `ZoneId`, charset, and JDK/CLDR version specified when needed.

## 2. Defining the Scope of the Matrix

| Locale | Primary testing focus | Example risks |
| --- | --- | --- |
| `vi-VN` | Diacritics, Vietnamese translations, localized dates/numbers | Missing fonts, broken diacritics, long text, fallback |
| `en-US` | English baseline, US date formatting | Assuming all locales share the same pattern |
| `de-DE` | Decimal and grouping separators different from English, currency/number formatting | Parsing `1,5` as `1.5` under the wrong locale |
| `tr-TR` | Two letter pairs I/ı and İ/i; case mapping and key lookup | `"TITLE".toLowerCase()` produces `"tıtle"` |
| `ar-EG` | Arabic formatting and script, numbers/text mixed with LTR, RTL UI | Punctuation, icon order, scrambled IDs |
| `he-IL` | Hebrew text, mixed LTR/RTL, dates and layout | Alignment, caret, parentheses, email/URL |

The matrix above **does not implicitly assert** that every `ar-EG` user uses the same numeral system, currency, or calendar. Behavior can vary depending on Unicode locale extensions, personal preferences, the JDK locale provider, and product policy.

Similarly, a user in Vietnam might use an English interface, a Japanese time zone, and USD currency. **Locale, ZoneId, Currency, Chronology, writing direction, and protocol format are related choices, not identical ones.**

### 2.1. Two Testing Dimensions: Functional and Presentation

**Automatable functional testing:**

- Format numbers/dates into strings and parse them back with the same formatter.
- Load the right bundle, complete keys, and proper fallback.
- Turkish case mapping produces the expected Unicode code points.
- Compare strings using `Collator` with a defined dataset and configuration.
- Business values do not change when switching locales.
- API data remains in an explicit machine-readable format.

**Visual or interactive testing:**

- RTL rendering order in the UI; icons, Back/Next buttons, menus, breadcrumbs.
- Content mixing Arabic/Hebrew script with ASCII digits/URLs.
- Punctuation placement, cursor, selection, copy/paste.
- Text overflow when translations are longer, fonts are zoomed, or viewports are narrow.
- Screen reader reads in the correct semantic order.
- Font fallback, diacritics, and proper glyph shaping.

Do not mark **"Full RTL PASS" simply because `java.text.Bidi` determines the paragraph direction**. Rendering also requires the UI engine and user testing.

## 3. Instantiating Locales Explicitly

Java supports BCP 47 language tags:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Locale en = Locale.forLanguageTag("en-US");
Locale de = Locale.forLanguageTag("de-DE");
Locale tr = Locale.forLanguageTag("tr-TR");
Locale ar = Locale.forLanguageTag("ar-EG");
Locale he = Locale.forLanguageTag("he-IL");
```

This is an illustrative snippet **inside a method**, requiring `import java.util.Locale;`.

In a real application, there should be a **product-approved list of supported locales**, rather than accepting any arbitrary language tag and assuming translations and fonts already exist.

### 3.1. Language Tags vs. Default Locale

- `Locale.forLanguageTag("de-DE")` creates an explicit target locale.
- `Locale.getDefault()` gets the general JVM default locale.
- `Locale.getDefault(Locale.Category.FORMAT)` gets the default used for formatting.
- `Locale.getDefault(Locale.Category.DISPLAY)` gets the default used for display names.

Do not call `Locale.setDefault(...)` **per HTTP request**: the default is JVM-wide state that can affect other users. Pass the locale explicitly where needed, or manage context per request without **turning it into a global default**.

### 3.2. Unicode Locale Extensions

A language tag can carry additional options, for example:

```text
ar-EG-u-nu-latn
th-TH-u-ca-buddhist
```

`nu` hints at the numbering system and `ca` hints at the calendar; however, whether they are applied depends on the specific API and locale provider. Do not assume that calling `String.toLowerCase(locale)` or `NumberFormat.getInstance(locale)` applies the exact same set of extensions as every other API.

A locale tag **does not determine** `ZoneId`. For time formatting, select `ZoneId` separately according to business requirements.

## 4. Baseline Testing Matrix

Here is a **sample test suite** that can be turned into a product test plan:

| Feature group | vi-VN | en-US | de-DE | tr-TR | ar-EG | he-IL |
| --- | --- | --- | --- | --- | --- | --- |
| Numbers/decimals | Yes | Yes | Yes | Yes | Yes | Yes |
| Percentages/currency | Yes | Yes | Yes | Yes | Yes | Yes |
| Localized date/time | Yes | Yes | Yes | Yes | Yes | Yes |
| Date/number parse round-trip | Yes | Yes | Yes | Yes | Yes | Yes |
| ResourceBundle/fallback | Yes | Yes | Yes | Yes | Yes | Yes |
| Placeholder formatting | Yes | Yes | Yes | Yes | Yes | Yes |
| Collation/sort | Yes | Yes | Yes | Yes | Yes | Yes |
| Letter I case-mapping | Ensure unaffected by other locales | ROOT baseline | Per policy | **Special** | Not used to infer Turkish I | Not used to infer Turkish I |
| Diacritics/Unicode | **Special** | Basic | Yes | Yes | **Special** | **Special** |
| RTL layout | Test not mistakenly mirrored | Test not mistakenly mirrored | Test not mistakenly mirrored | Test not mistakenly mirrored | **Required** | **Required** |
| Bidi text mixed with numbers/URLs | Basic | Basic | Basic | Basic | **Required** | **Required** |
| Overflow/zoom/accessibility | Yes | Yes | Yes | Yes | Yes | Yes |

"Yes" means **the corresponding test must be run**; it does not assert that a locale must naturally produce a fixed output string. "Special" marks high-risk areas that need additional test data/conditions.

The matrix should not be frozen forever. Add other locales as markets expand, especially complex scripts, languages that do not separate words with spaces, non-ISO calendars, and numeral localization.

## 5. Testing Number Formatting: Do Not Hard-Code Separators

`java.text.NumberFormat` can create a locale-aware formatter:

```java
NumberFormat nf = NumberFormat.getNumberInstance(locale);
nf.setGroupingUsed(true);

String shown = nf.format(12345.5);
Number parsed = nf.parse(shown);
```

**What the test should assert:** with the same formatter, valid sample data must format and parse back to an equivalent value, within precision limits. In a test that does not pin the JDK/CLDR/provider, do not hard-code that `shown` must always equal a single literal across all environments.

Common examples:

- `en-US` typically uses `.` for the decimal separator and `,` for grouping.
- `de-DE` typically uses `,` for the decimal separator and `.` for grouping.
- `vi-VN` has its own conventions that may differ from `en-US`.
- `ar-EG` may use Arabic-Indic digits and localized separator characters, depending on runtime/config.

**However, these are descriptions of conventions, not an absolute oracle for exact string comparisons across every JDK.** Some separators are also non-obvious Unicode spaces.

### 5.1. Do Not Parse Localized Strings with `Double.parseDouble`

`Double.parseDouble("1,5")` has no mechanism to read German decimal separators. For German user input, use a locale-selected formatter or a UI parser with a clear contract.

At the same time, `NumberFormat.parse` can accept a prefix and stop at an unrecognized character. If you want to validate **the entire input**, use `ParsePosition` and check `position.getIndex() == text.length()`, along with error conditions. That is why the runnable example later uses `ParsePosition` instead of calling an ambiguous parse and treating every string as valid.

### 5.2. Currency Values Do Not Convert Automatically

`NumberFormat.getCurrencyInstance(locale)` chooses how to **display** money for a locale; changing the locale or currency symbol **does not** convert a value from USD to EUR. Financial applications require an explicit `Currency`/ISO code, exchange rates with a source and timestamp when business logic actually converts, exact arithmetic with `BigDecimal`, and a defined rounding policy.

In localization tests, verify two independent things: *the numeric value remains unchanged* and *the currency label/presentation meets requirements*.

## 6. Testing Date and Time: Localized Patterns and Different Time Zones

Java 17 uses `java.time.format.DateTimeFormatter`. To display a date to the user:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);

String text = formatter.format(LocalDate.of(2026, 10, 28));
LocalDate parsed = LocalDate.parse(text, formatter);
```

This is inside a method with imports `java.time.LocalDate`, `java.time.format.*`.

For the chosen locales, a **round-trip** test shows that the formatter and parser behave consistently under the same locale/runtime. The actual pattern comes from locale data. `FormatStyle.MEDIUM` does not mean a fixed literal like `dd/MM/yyyy` in every country.

If the UI genuinely wants a regional date layout for the user, use `ofLocalizedDate(FormatStyle...)`. If the product needs a **fixed** format like `uuuu-MM-dd` for an API, use `DateTimeFormatter.ISO_LOCAL_DATE` or a machine contract; **do not** pass UI output as protocol data.

### 6.1. Fix Dates in Tests

Do not use `LocalDate.now()` in tests that expect deterministic output because the date can change depending on system and time zone. Use:

```java
LocalDate testDate = LocalDate.of(2026, 10, 28);
```

If you need to test an absolute point in time, use a fixed `Instant` and select `ZoneId` **explicitly**. For example, `Instant.parse("2026-10-28T07:30:00Z")` is an instant; when displayed in Vietnam or Berlin, the wall-clock time depends on the zone, not `Locale` alone.

### 6.2. Testing Year Boundaries and DST

Include at least:

- January 1 and December 31 to catch confusing `YYYY` (week-based-year) with `uuuu`.
- Leap-year February 29 and invalid February 31 to test `ResolverStyle.STRICT`.
- Timestamps in regions with daylight saving time (DST), including **gap/overlap** moments when computing local time.
- A date-only `LocalDate` should not shift hours by time zone.
- `ar-EG`/`he-IL` locales do not automatically imply Hijrah/Hebrew calendars; chronology/currency/zone must be chosen per requirements.

Do **not** assert that `ar-EG` or `he-IL` locales switch chronology to another calendar by default. `DateTimeFormatter.ofLocalizedDate` uses ISO chronology unless chronology is overridden.

## 7. Standalone Java 17 Example: Running the Number and Date Matrix

The file `LocaleMatrixSmokeDemo.java` below uses **six locales** without demanding exact formatted strings. It checks **round-trip values**, the number of characters consumed by the parser, and date stability.

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleMatrixSmokeDemo {
    private static final String[] TAGS = {
            "vi-VN", "en-US", "de-DE",
            "tr-TR", "ar-EG", "he-IL"
    };

    private static boolean numberRoundTrip(Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        format.setGroupingUsed(true);
        format.setMaximumFractionDigits(1);

        double expected = 12345.5;
        String shown = format.format(expected);

        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(shown, position);

        return parsed != null
                && position.getIndex() == shown.length()
                && Math.abs(parsed.doubleValue() - expected) < 0.000001;
    }

    private static boolean dateRoundTrip(Locale locale) {
        LocalDate expected = LocalDate.of(2026, 10, 28);
        DateTimeFormatter format =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                        .withLocale(locale);

        String shown = format.format(expected);
        LocalDate parsed = LocalDate.parse(shown, format);
        return expected.equals(parsed);
    }

    public static void main(String[] args) {
        for (String tag : TAGS) {
            Locale locale = Locale.forLanguageTag(tag);

            System.out.println(tag
                    + " number=" + numberRoundTrip(locale)
                    + " date=" + dateRoundTrip(locale));
        }
    }
}
```

Compile and run with Java 17:

```bash
javac -encoding UTF-8 LocaleMatrixSmokeDemo.java
java LocaleMatrixSmokeDemo
```

On a standard JDK 17 supporting these locales, the expected output according to the test invariant is:

```text
vi-VN number=true date=true
en-US number=true date=true
de-DE number=true date=true
tr-TR number=true date=true
ar-EG number=true date=true
he-IL number=true date=true
```

If any row does not PASS, record the **JDK vendor/version, locale provider, locale tag, formatted string, and parser stop position**, then investigate. The test does not assume all locales use the same separators or date order. For a real product, add tests for 0, negative numbers, very large numbers, NaN/Infinity if supported, percentages, and currencies per policy, not just the single value 12345.5.

**Limitation note:** this is a smoke test, not proof that every pattern, dataset, and UI element is properly localized. Date formatting under a special calendar or invalid inputs requires separate tests. For accurate currency testing, prefer `BigDecimal` arithmetic instead of comparing financial values with `double`; `double` is used here only to illustrate a simple numeric round-trip for 12345.5, which has an exact binary representation.

## 8. The Turkish Letter I: A Mandatory Test

Turkish has two letter pairs:

```text
I (U+0049)  <-->  ı (U+0131)
İ (U+0130)  <-->  i (U+0069)
```

Meanwhile, `Locale.ROOT` and many other languages normally follow `I → i` for lowercase. As a result, `"TITLE".toLowerCase()` can produce `"tıtle"` (with dotless ı) when the JVM's default locale is Turkish, causing lookups for the machine key `"title"` to fail.

**Split tests into two purposes:**

1. Turkish prose text must use `String.toLowerCase(trLocale)` or `toUpperCase(trLocale)` with accurate Unicode results.
2. **Machine identifiers** such as ASCII config/protocol keys must be normalized **locale-independently**, typically with `Locale.ROOT` and character-set validation. Do not use the default locale to process identifiers.

### Standalone Java 17: TurkishIAssertions.java

```java
import java.util.Locale;

public class TurkishIAssertions {
    private static final Locale TR =
            Locale.forLanguageTag("tr-TR");

    private static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        check("I-to-dotless-i",
                "I".toLowerCase(TR).equals("\u0131"));
        check("dotted-I-to-i",
                "\u0130".toLowerCase(TR).equals("i"));
        check("i-to-dotted-I",
                "i".toUpperCase(TR).equals("\u0130"));
        check("dotless-i-to-I",
                "\u0131".toUpperCase(TR).equals("I"));

        check("ROOT-machine-key",
                "TITLE".toLowerCase(Locale.ROOT).equals("title"));
        check("TR-not-machine-key",
                !"TITLE".toLowerCase(TR).equals("title"));
        check("ROOT-dotted-I-expansion",
                "\u0130".toLowerCase(Locale.ROOT)
                        .equals("i\u0307"));
    }
}
```

```bash
javac -encoding UTF-8 TurkishIAssertions.java
java TurkishIAssertions
```

Expected stdout on Java 17:

```text
PASS I-to-dotless-i
PASS dotted-I-to-i
PASS i-to-dotted-I
PASS dotless-i-to-I
PASS ROOT-machine-key
PASS TR-not-machine-key
PASS ROOT-dotted-I-expansion
```

Note: `"\u0130".toLowerCase(Locale.ROOT)` produces `i` plus combining dot above U+0307 (two code points), whereas Turkish produces a single `i`. Therefore, case conversion can change **string length and character offsets**. Do not reuse indices computed from the string before lowercasing to highlight the lowercased string without designing offset mapping.

`String.equalsIgnoreCase` **does not accept a Locale**, so it is not a Turkish semantic comparison algorithm. When language-aware sorting or matching is required, consider `Collator` or a locale-configured search engine; do not use `equalsIgnoreCase` to prove I/ı/İ/i is handled properly according to product rules.

## 9. Testing ResourceBundle and Fallback per Locale

A localization system typically has a bundle family:

```text
demo/
  Messages.properties
  Messages_vi.properties
  Messages_tr.properties
  Messages_de.properties
  Messages_ar.properties
  Messages_he.properties
```

`ResourceBundle` takes a **baseName**, such as `"demo.Messages"`, and resolves candidate bundles according to `Locale`. Whether a specific locale file exists depends on the product's translation status.

Test scenarios to include:

| Check | Expectation |
| --- | --- |
| `getBundle(baseName, viVN)` | Uses packaged Vietnamese bundle, or documented fallback |
| `getBundle(baseName, enUS)` | Uses appropriate English/root bundle |
| `getBundle(baseName, deDE)` | Uses German bundle if present; otherwise official fallback |
| `getBundle(baseName, trTR)` | Does not corrupt keys on case change; accurate Turkish translation |
| `getBundle(baseName, arEG)` | Valid Unicode Arabic text, with RTL layout at the UI layer |
| `getBundle(baseName, heIL)` | Valid Unicode Hebrew text, with RTL layout at the UI layer |
| Missing required key | Caught by QA; never shows raw keys or unhandled exceptions in production |
| Changing loader/package/JAR | Resources are still found within the right scope |
| Different default locale | Does not alter results when the caller specifies locale and fallback explicitly |

### 9.1. Fallback Is Not Accurate Translation

An application can fall back to the English `Messages.properties` when `Messages_ar.properties` is missing. That keeps the UI from crashing, **but does not mean Arabic localization passes**. Tests should distinguish:

- **Functional fallback PASS**: readable content exists, no `MissingResourceException`.
- **Translation coverage FAIL/WARNING**: translations are missing relative to the release requirement.

Do not use "getString is non-empty" as proof that the entire translation set is complete. Compare key sets between the base bundle and translations, detect missing/unused keys, and check placeholders, truncated text, and argument order.

### 9.2. Standalone Java 17: Testing a Sample Bundle Set

Use this structure:

```text
project/
  src/demo/BundleLocaleMatrixDemo.java
  resources/demo/Messages.properties
  resources/demo/Messages_vi.properties
  resources/demo/Messages_tr.properties
```

Contents of `resources/demo/Messages.properties`:

```properties
hello=Hello
```

Contents of `resources/demo/Messages_vi.properties`:

```properties
hello=Xin chào
```

Contents of `resources/demo/Messages_tr.properties`:

```properties
hello=Merhaba
```

Code in `src/demo/BundleLocaleMatrixDemo.java`:

```java
package demo;

import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLocaleMatrixDemo {
    private static final String[] TAGS = {
            "vi-VN", "en-US", "de-DE",
            "tr-TR", "ar-EG", "he-IL"
    };

    public static void main(String[] args) {
        ClassLoader loader =
                BundleLocaleMatrixDemo.class.getClassLoader();

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (String tag : TAGS) {
            Locale locale = Locale.forLanguageTag(tag);
            ResourceBundle bundle = ResourceBundle.getBundle(
                    "demo.Messages", locale, loader, control);

            System.out.println(tag + "=" +
                    bundle.getString("hello"));
        }
    }
}
```

Compile, copy resources, and run on the **classpath/unnamed module** (Bash commands):

```bash
mkdir -p out/demo
javac -encoding UTF-8 -d out src/demo/BundleLocaleMatrixDemo.java
cp resources/demo/Messages*.properties out/demo/
java -cp out demo.BundleLocaleMatrixDemo
```

Stdout when using the exact sample files:

```text
vi-VN=Xin chào
en-US=Hello
de-DE=Hello
tr-TR=Merhaba
ar-EG=Hello
he-IL=Hello
```

Because the demo intentionally includes only Vietnamese, Turkish, and the English root resources, the three locales `de-DE`, `ar-EG`, and `he-IL` fall back to root. This is a **fallback demonstration**, not a complete release sample. When a product requires German/Arabic/Hebrew translations, those three locales must have dedicated coverage.

**Java 17 note:** `PropertyResourceBundle` since Java 9 supports UTF-8 by default along with legacy compatibility; the example assumes files are saved in UTF-8 with no conflicting encoding override. `ResourceBundle.Control` is not appropriate for all named-module configurations; with JPMS, module-aware overloads or `ResourceBundleProvider` may be required. This example intentionally runs on the classpath.

## 10. MessageFormat, Placeholders, and Reordered Arguments

Proper translation is not just word substitution; word order can change across languages. With Java `MessageFormat`, use **argument indexes** such as `{0}`, `{1}` instead of string concatenation with `+`.

Example:

```text
English: "{0} sent {1} to {2}."
Other locale: "To {2}, {0} sent {1}."
```

This illustrates reordering clauses in a sentence, not a claim that it is natural phrasing for every language. Native translators must author the patterns. Each translation may reorder `{0}`/`{1}`/`{2}`, but must preserve the **role and type of each parameter**.

### What to Test

- Translations include all required arguments.
- No invalid indexes, such as `{3}` when the caller passes only three arguments.
- `number`/`date` format types match the argument data types.
- Single quotes `'` and braces are escaped according to `MessageFormat` syntax.
- No hard-coded prefixes/suffixes like concatenating `"Hello "` with a person's name across all languages.
- In HTML, user-supplied parameter values must still be **escaped for the output context**; `MessageFormat` is not an HTML sanitizer.
- Longer translations do not overflow the UI or break RTL reading order.

### Java 17 Example of Locale-Aware Formatting

```java
import java.text.MessageFormat;
import java.util.Locale;

// Inside a method:
Locale german = Locale.forLanguageTag("de-DE");
MessageFormat format = new MessageFormat(
        "Wert: {0,number}", german);

String shown = format.format(new Object[]{12345.5});
```

Here the formatter uses the German locale to represent numbers, though the exact details of `shown` can vary by CLDR/JDK; test numeric and semantic contracts rather than always comparing against a literal if the environment is not pinned.

**Do not use static `MessageFormat.format(pattern, args)` when you need an explicit locale** without controlling the default locale. Create `new MessageFormat(pattern, locale)` and use it in the right context.

## 11. Collator: Language-Aware Sorting Instead of Unicode Code Units

`String.compareTo` compares UTF-16 code unit values; it has no knowledge of language sorting rules. `java.text.Collator` applies locale collation rules:

```java
Collator collator = Collator.getInstance(locale);
collator.setStrength(Collator.TERTIARY);

names.sort(collator::compare);
```

This illustrates code inside a method with valid `locale` and `names` variables, importing `java.text.Collator`.

### Strength Levels

| Strength | General meaning | What to test |
| --- | --- | --- |
| `PRIMARY` | Base letter differences | Do not assume all diacritics are ignored in every language |
| `SECONDARY` | Adds certain accent differences | Locales may treat diacritics as significant at different levels |
| `TERTIARY` | Adds case/variant differences | Use when finer ordering is desired |
| `IDENTICAL` | Deeper distinction | Requires a Unicode decomposition strategy |

In Turkish, `I` and `ı` belong to one case pair, while `İ` and `i` belong to another. `Collator` has Turkish rules that differ from locale-independent case folding. In German, ordering of accented/umlauted letters also follows locale rules. Do not hard-code a single order across all locales.

### 11.1. Robust Collator Tests

- Test **reflexivity**: `collator.compare(s,s)==0`.
- Test **antisymmetry**: `sign(compare(a,b)) == -sign(compare(b,a))`.
- Test **transitivity**: if `a≤b` and `b≤c`, then `a≤c`.
- Test equivalence between `collator.compare(a,b)` and `getCollationKey(a).compareTo(getCollationKey(b))` on **the same unmodified Collator configuration**.
- Test realistic names for each market, with native speakers approving the expected order.
- Do not persist `CollationKey` long-term as a permanent sort key when JDK/provider/CLDR versions can change.

**Do not equate linguistic comparison with username/password checks or technical identifiers.** Security and uniqueness have different contracts; lower collation strengths may treat two distinct strings as equal.

## 12. RTL: Text Direction Differs from Language and Source Data

Right-to-left (RTL) languages such as Arabic or Hebrew require dedicated testing across at least three levels:

1. **Logical order:** the sequence of Unicode code points in `String`, used for storage, copy/paste, and protocols.
2. **Bidirectional reordering:** the visual display order of RTL/LTR runs after applying the Unicode Bidirectional Algorithm.
3. **Glyph shaping/layout:** cursive joining, glyph selection, diacritic placement, alignment, icons, and UI container layout.

Java provides `java.text.Bidi` for bidi analysis, but it is **not a translator**, does not automatically "reverse the String", and **does not replace** a rendering/shaping engine.

An Arabic paragraph can contain digits `1234`, a URL `https://example.com`, and Latin product names. If code attempts `new StringBuilder(text).reverse()` to simulate RTL, logical order and the meaning of punctuation/Unicode clusters can be corrupted.

### 12.1. Do Not Infer Direction Rigidly Across the Whole Application

- `ar-EG` and `he-IL` typically use an RTL UI layout, yet an **email/URL/serial number** field inside still requires appropriate LTR direction handling.
- A user may select an Arabic locale while typing English; input characters must not be reversed.
- `vi-VN`/`en-US`/`de-DE`/`tr-TR` are typically LTR, yet must still render quoted Arabic text or names properly.
- Directional navigation arrow icons may need **mirroring** depending on semantics; icons without directional meaning such as play/media symbols or logos do not necessarily need mirroring.

### 12.2. Testing Mixed-Direction Text

Your test dataset should include:

```text
Arabic only:       مرحبا
Hebrew only:       שלום
Arabic + digits:   رقم الطلب 12345
Hebrew + Latin:    שלום Java 17
Mixed address:     demo@example.com - مرحبا
Parentheses:       (مرحبا) 123
Currency/percent:  123.45 USD / 25%
```

These strings are **test data**, not an instruction to "reverse the String" before drawing. When taking screenshots, record the font, viewport, text direction, input scenario, and render engine.

### 12.3. Runnable Java 17: Verifying RTL Properties of Data

File `BidiSmokeDemo.java`:

```java
import java.text.Bidi;

public class BidiSmokeDemo {
    public static void main(String[] args) {
        String arabic = "\u0645\u0631\u062D\u0628\u0627";
        String hebrew = "\u05E9\u05DC\u05D5\u05DD";

        Bidi arabicBidi = new Bidi(
                arabic, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        Bidi hebrewBidi = new Bidi(
                hebrew, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("arabicRequiresBidi=" +
                Bidi.requiresBidi(
                        arabic.toCharArray(), 0, arabic.length()));
        System.out.println("hebrewRequiresBidi=" +
                Bidi.requiresBidi(
                        hebrew.toCharArray(), 0, hebrew.length()));
        System.out.println("arabicBaseRTL=" +
                !arabicBidi.baseIsLeftToRight());
        System.out.println("hebrewBaseRTL=" +
                !hebrewBidi.baseIsLeftToRight());
    }
}
```

```bash
javac -encoding UTF-8 BidiSmokeDemo.java
java BidiSmokeDemo
```

Expected stdout:

```text
arabicRequiresBidi=true
hebrewRequiresBidi=true
arabicBaseRTL=true
hebrewBaseRTL=true
```

The demo verifies the **bidirectional properties** of the two strings and how base direction is resolved from strong characters when using default paragraph direction. It **does not verify that Arabic glyphs join properly**, that checkboxes sit on the right, or that menus are mirrored, because those belong to the UI layer.

## 13. Non-Negotiable RTL UI Tests

Below is a manual/visual regression test matrix for `ar-EG` and `he-IL`:

| UI area | Test scenario | Expectation |
| --- | --- | --- |
| Navigation bar | Back, Next, breadcrumbs | Order and icon direction match RTL design |
| Forms | Labels, text inputs, placeholders, validation | Proper alignment; no lost focus/caret |
| Email/URL fields | Typing/editing/copying an LTR URL in an RTL form | Stored and pasted content preserves the logical string |
| Prices | Currency symbol, negative/positive numbers, decimals | Number/symbol order is clear, not byte-reversed |
| Lists | Icon order, bullets, numbering, pagination | Matches reading direction without altering meaning |
| Dialogs/toasts | Messages containing Latin IDs, digits, and Arabic characters | Punctuation/parentheses display clearly, text does not overflow |
| Data tables | Columns, headers, sort controls | Consistent order and alignment |
| Error states | Long validation text, warning icon | Does not cover fields or submit buttons |
| Accessibility | Screen reader, tab order | Focus/reading order matches logical flow |
| Responsive | Small phones, 200–400% zoom | No lost content or overlapping text |

For web UIs, set `lang` and `dir` appropriately; example markup:

```html
<div lang="ar" dir="rtl">
  <p>رقم الطلب: <bdi>ABC-1234</bdi></p>
</div>
```

`bdi` isolates an embedded span whose direction is independent within a bidi context when appropriate. This is an **HTML UI** example, not Java code, and does not replace CSS rules. For email inputs or complex UI components, test on the actual browser/framework being used.

In Java Swing, `ComponentOrientation.RIGHT_TO_LEFT` and orientation-aware components exist, though not every custom-painted component mirrors automatically with orientation. Verify the layout manager, font, and text renderer together.

### 13.1. Bidi Control Characters and Security

Unicode includes **bidi formatting controls**, such as U+202E RIGHT-TO-LEFT OVERRIDE, which can make text display in a different order from its logical code points. In logs, filenames, source code, or untrusted content, these characters can be abused to disguise character order.

For security-sensitive data such as filenames, URLs, identifiers, content reviews, and audit logs:

- Do not strip all valid RTL characters of a language.
- Have a policy to detect/warn on unexpected bidi controls in identifiers or logs.
- When displaying user content in the UI, use **context-appropriate isolation/escaping**.
- Show code points or escaped representations when debugging potentially deceptive strings.
- Do not rely solely on screenshots to prove raw data was not altered.

**Bidi controls and normal RTL data are two different things.** Validation policies should be domain-driven rather than banning all Arabic/Hebrew characters.

## 14. Unicode: Vietnamese Diacritics, Combining Marks, and Emoji

A localization QA suite needs non-ASCII Unicode test data:

- Vietnamese: `Tiếng Việt`, `Đặng`, `nghiêng`, uppercase/lowercase with diacritics.
- German: `Straße`, `Äpfel`, `für`.
- Turkish: `İstanbul`, `Iğdır`, `ışık`.
- Arabic/Hebrew: pure script and text mixed with Latin/digits.
- Supplementary emoji: `😀`, `🚀`.
- Decomposed forms: `e\u0301`, plus Vietnamese combining diacritics where relevant.

In Java, `String.length()` counts **UTF-16 code units**, not code points or grapheme clusters. Characters outside the BMP require a surrogate pair; a letter with combining marks can span multiple code points.

### Testing Canonical Normalization

`java.text.Normalizer` can normalize strings to `NFC` when a contract requires it. For example, `"\u00E9"` and `"e\u0301"` differ in code units yet are canonically equivalent after NFC.

However, do not blindly normalize passwords, tokens, signatures, or data with byte-level contracts. Normalization, case conversion, collation, and bidi rendering have **different goals** and require independent testing.

### Charset at I/O Boundaries

Translation data must be saved/read with an explicit charset, usually UTF-8. A UTF-8 file decoded with the wrong charset can produce mojibake without throwing an exception. `Locale.forLanguageTag("vi-VN")` **does not** guarantee a source file is encoded in UTF-8; the charset must be specified by the protocol or data configuration.

When you need to detect malformed UTF-8, use `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)` instead of relying on `new String(bytes, UTF_8)`, which may insert replacement characters. Testing a file containing diacritics/emoji helps catch wrong read paths.

## 15. Diagnosing Test Failures: Grouping Bugs by Layer

| Symptom | Likely issue category | Investigation steps |
| --- | --- | --- |
| `vi-VN` displays `?` or garbled characters | Encoding/font | Check UTF-8 bytes, decoder, and font glyphs |
| `de-DE` parses `"1,5"` incorrectly | Machine parser used instead of locale | Check `NumberFormat`/`ParsePosition` |
| `tr-TR` lookup for key `"TITLE"` fails | Default locale used when lowercasing ID | Switch to `ROOT`/explicit canonicalization |
| `ar-EG` text is right but layout is LTR | Missing `dir`/orientation | Check document direction and UI component |
| `he-IL` parentheses/numbers placed oddly | Bidi embedding/isolation | Check logical string, use bidi-aware engine |
| Target locale falls back to English | Missing `ResourceBundle` file/loader/fallback | Check bundle packaging and translation coverage |
| Date `03/04` misinterpreted | Ambiguous locale pattern or contract | Define input format, parse strictly |
| Fails only on Linux container | Different JDK/locale provider/fonts | Record environment and capture actual UI |
| Long text overflows buttons | Fixed layout, translation expansion | Responsive/auto-layout, pseudo-localization |
| Exact string tests break after JDK upgrade | CLDR/locale data updated | Pin runtime or assert invariants |
| Name sorting differs from expectations | Different `Collator` locale/strength | Check provider and test native dataset |
| Timestamps off by hours | Confusing `Locale` with `ZoneId` | Check `Instant`, `ZoneId`, DST |

A bug can span multiple layers; do not reflexively "fix" it by changing `Locale.setDefault` or lowercasing every string. Identify whether the defect belongs to **formatting, parsing, resource loading, encoding, text processing, or layout**.

## 16. Testing Invalid Data, Boundaries, and Failure Paths

For each locale, beyond the happy path, include:

**Number:**

- `0`, negative values, decimals, large numbers with grouping.
- Input with missing/malformed separators, strings with trailing garbage characters.
- Percentages, currency with actual currency codes, negative signs, and precision.
- User input containing Unicode spaces, Arabic digit shaping, or bidirectional characters if the product permits them.

**Date/time:**

- Leap days, nonexistent dates, year transitions, DST gaps/overlaps.
- `LocalDate` vs. `Instant`, explicit time zone, and date styles.
- Strict parsing with `uuuu` when input uses a fixed pattern.
- ISO formats for API payloads to avoid ambiguous interpretation.

**Resource/text:**

- Missing bundle, missing key, missing/wrong placeholder index.
- Escaped characters in `MessageFormat`, HTML characters, emoji.
- Untranslated fields and fields whose translations are 2–3× longer.
- Deliberately designed fallback paths.

**RTL and UI:**

- Navigation buttons, tables, forms, notifications, modals, keyboard tab order.
- Strings mixing code, email, numbers, parentheses, and RTL script.
- Resize, zoom, device rotation, large fonts, missing glyphs.
- Screen reader, copy/paste, and selection preserving logical text.

**Difference between test types:** a Java check verifying `Bidi.requiresBidi` returns `true` cannot prove a modal aligns its content properly. Conversely, a clean screenshot does not prove the backend preserved all code points. Both functional assertions and UI/visual checks are needed.

## 17. Pseudo-Localization: Complementing the Real Locale Matrix

Pseudo-localization transforms text to simulate translation—for example, adding accents, expanding string length, or simulating RTL characters. It helps uncover:

- Hard-coded strings not moved into resource bundles.
- Tight UI containers/widths.
- Truncation in buttons/menus, line height issues, and text clipping.
- Layout paths assuming English word counts.

**However, pseudo-localization does not replace** real translations and native linguistic review. An "expanded English" string cannot verify Turkish I casing rules, German collation, Vietnamese diacritics, or Arabic bidi shaping.

You can run an **expanded pseudo-locale** as an extra column, while the six real locales in this lesson must still have dedicated tests.

## 18. Writing Resilient Assertions: Separating Invariants from Snapshots

Not every locale test should compare exact text.

### 18.1. Assertions That Should Be Stable

- Same numeric value when formatting/parsing valid inputs with the same `NumberFormat`, within precision.
- Same `LocalDate` when formatting/parsing with the same formatter.
- Turkish `I/ı/İ/i` mappings under Java 17.
- `"TITLE".toLowerCase(Locale.ROOT)` is always `"title"`, regardless of JVM default.
- Unicode source strings lose no code points across valid UTF-8 encode/decode.
- Required bundle keys load and are non-empty.
- Bidi utility identifies pure Arabic/Hebrew strings as having RTL base direction.

### 18.2. Snapshots Requiring a Pinned Environment

- Exact output strings from `NumberFormat`, `DateTimeFormatter.ofLocalizedDate`, `Currency`, month names.
- Patterns and grouping/decimal symbols returned by CLDR/provider.
- Text sort order under `Collator` when providers change.
- Visual RTL screenshots dependent on font/OS, CSS/renderer, DPI, and browser.
- Rendering of emoji, combining marks, and fallback glyphs.

If a system **requires exact output** (for instance, a regulatory report bound to a fixed pattern), define the pattern/format explicitly, pin the environment/version, and test the literal. If it only needs to follow locale conventions, do not treat a snapshot from a developer machine as an "eternal truth."

### 18.3. Recording Environment Details on Failure

When a locale test fails, log:

```text
Locale tag:   tr-TR
Java version: 17.x (specific vendor/build)
Locale provider: relevant CLDR/COMPAT/config
ZoneId:       explicit setting
Font/renderer: (for UI tests)
Input value:  Unicode escaped, sensitive data scrubbed
Actual/expected: comparison type and invariant rationale
```

This is an example of **information to collect**, not the output of a Java command. Do not log passwords, tokens, or full PII while debugging.

## 19. Test Suite Design and CI Strategy

### 19.1. Test Layers

| Test layer | Target | Characteristics |
| --- | --- | --- |
| Unit | Casing, format/parse, fallback/key contract | Fast execution, fixed data |
| Integration | Loading resources from JAR/module, UTF-8 I/O | Close to production environment |
| Component UI | Orientation, text overflow, and interaction | Tests the app's rendering engine |
| E2E | User switches locale, submits forms, receives email/reports | Cross-layer verification |
| Visual regression | Screenshot comparison at fixed width/font | Pin font/browser and review RTL |
| Native review | Natural phrasing and language sort order | Approved by fluent speakers |
| Accessibility | Screen reader, focus/tab order, zoom | Beyond screenshot checks |

### 19.2. Controlling the Test Matrix to Avoid Combinatorial Explosion

Six locales × multiple browsers × multiple viewports × multiple time zones × multiple currencies produce a huge number of combinations. You can:

1. Run the unit matrix across **all locales** on every pull request.
2. Run UI smoke tests on at least one LTR and **both RTL** locales at primary viewport sizes.
3. Run visual regression on critical screens and high-risk locales.
4. Run the full matrix on a schedule or before releases.
5. Run targeted tests when changing i18n libraries, CLDR/JDK, fonts, CSS, or resource loaders.

Do not skip `tr-TR` or RTL because "few users use them right now": these locales **readily expose implicit assumptions in code**.

### 19.3. Realistic and Adversarial Sample Data

Beyond simple inputs, include accented names, long names, combining characters, mixed-script strings, and parentheses/URLs inside RTL text. Pick examples deliberately:

```text
vi-VN:  Nguyễn Thị Minh Anh
de-DE:  Straße, München
tr-TR:  İstanbul, Iğdır
ar-EG:  مرحبا Java 17 - 12345
he-IL:  שלום ABC-123
Unicode: e + U+0301, U+1F600
```

This is not an exhaustive linguistic corpus. Real-world language testing needs native specialists to confirm word choice, layout direction, and expected casing/ordering.

## 20. A Consolidated Java 17 Program Checking Invariants

Below is a standalone example **without JUnit**, suitable as a small smoke check in a build if desired. It verifies invariant conditions without relying on exact localized output.

File `LocaleMatrixAssertions.java`:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleMatrixAssertions {
    private static final String[] TAGS = {
            "vi-VN", "en-US", "de-DE",
            "tr-TR", "ar-EG", "he-IL"
    };

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        for (String tag : TAGS) {
            Locale locale = Locale.forLanguageTag(tag);

            NumberFormat nf = NumberFormat.getNumberInstance(locale);
            nf.setMaximumFractionDigits(1);
            String shownNumber = nf.format(12345.5);

            ParsePosition pos = new ParsePosition(0);
            Number parsedNumber = nf.parse(shownNumber, pos);

            check(parsedNumber != null
                    && pos.getIndex() == shownNumber.length()
                    && parsedNumber.doubleValue() == 12345.5,
                    tag + " number");

            LocalDate date = LocalDate.of(2026, 10, 28);
            DateTimeFormatter df =
                    DateTimeFormatter.ofLocalizedDate(
                            FormatStyle.MEDIUM).withLocale(locale);

            check(LocalDate.parse(df.format(date), df).equals(date),
                    tag + " date");

            check(!shownNumber.isEmpty(),
                    tag + " formatting missing");
            System.out.println(tag + ":PASS");
        }

        Locale tr = Locale.forLanguageTag("tr-TR");
        check("I".toLowerCase(tr).equals("\u0131"),
                "Turkish I");
        check("i".toUpperCase(tr).equals("\u0130"),
                "Turkish i");
        check("TITLE".toLowerCase(Locale.ROOT).equals("title"),
                "Machine key");
        System.out.println("case:PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocaleMatrixAssertions.java
java LocaleMatrixAssertions
```

On standard Java 17 with locale data available for all six tags, the expected stdout is:

```text
vi-VN:PASS
en-US:PASS
de-DE:PASS
tr-TR:PASS
ar-EG:PASS
he-IL:PASS
case:PASS
```

This test does not replace JUnit, nor does it check translation quality, RTL UI, currency conversion, DST, or exact styles. It only ensures that a core set of i18n APIs behaves consistently on the current runtime.

For serious CI usage, move each condition into a JUnit 5 parameterized test so failures are reported per locale and case. JUnit is not bundled with JDK 17, so it must be declared as a separate test dependency (Maven/Gradle); do not expect code importing JUnit to run with plain `javac` without adding it to the classpath.

## 21. Common Mistakes and Misconceptions

| Misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| "Running en-US is enough." | Other locales differ in diacritics/numbers/casing/RTL | Run a multi-locale matrix |
| "tr-TR differs from en-US only in translated words." | Turkish I has different case mapping | Test I/ı/İ/i explicitly |
| "Every number can be parsed with Double.parseDouble." | Machine parser ignores localized separators | `NumberFormat`/UI contract |
| "Vietnam and Germany use the same date pattern." | Patterns depend on locale/JDK | Use localized formatter and test |
| "Locale determines the time zone." | Locale and ZoneId are independent | Select zone explicitly |
| "Arabic/Hebrew only need translated text, not layout changes." | RTL affects navigation, inputs, bidi | Test actual UI |
| "To support RTL, reverse the String." | Breaks logical order and Unicode | Use a bidi-aware renderer |
| "String.length = visible character count." | Counts UTF-16 code units | Test code points/graphemes separately |
| "Having all keys means translation is complete." | Fallback can hide missing translations | Track coverage |
| "Collator is the same as compareTo." | Collation follows language rules | Test with real locales |
| "Snapshots of localized output never change." | CLDR/provider/JDK can change | Pin environment or test invariants |
| "Valid RTL data is always a malicious bidi control." | Valid Arabic/Hebrew script is normal language data | Context-based validation policy |
| "Pseudo-localization replaces native QA." | Cannot prove semantic/cultural correctness | Combine pseudo and native review |
| "Calling setDefault per request has no side effects." | Default is shared across the entire JVM | Pass locale explicitly |
| "If the screen looks good, the test passes." | Parsing/encoding/Unicode may still be broken | Need both assertions and UI tests |

## 22. Exercises and Answers

**Exercise 1.** Why can `"TITLE".toLowerCase()` break a key map in a `tr-TR` environment?

**Answer:** The no-argument overload depends on the JVM default locale; Turkish maps `I` to dotless `ı`. The key `"tıtle"` does not equal `"title"`. For ASCII technical identifiers, use a locale-independent canonicalization contract such as `Locale.ROOT`.

**Exercise 2.** A `de-DE` test compares `NumberFormat.getNumberInstance(de).format(12345.5)` against an exact literal. Why might it fail after a JDK upgrade?

**Answer:** Separators, spaces, or locale data may change across providers/CLDR. If the app only requires localized behavior, test the numeric value and parse round-trip; if an exact literal is required, pin the environment/format contract.

**Exercise 3.** `ar-EG` and `he-IL` already display translated text properly. Is that enough to conclude the RTL UI passes?

**Answer:** No. You also need to test navigation, icon direction, forms, mixed number/email text, punctuation, caret, font/shaping, zoom, and accessibility.

**Exercise 4.** Why should you not use `new StringBuilder(arabicText).reverse()` to "convert to RTL"?

**Answer:** RTL is a bidirectional layout rule, not reversing logical Unicode code units; reversing can corrupt characters, diacritics, and data.

**Exercise 5.** When using `ResourceBundle`, locale `he-IL` receives `Hello` from the root bundle. Which test PASSES and which may FAIL?

**Answer:** Fallback/no-crash behavior may PASS; Hebrew translation coverage still FAILS if Hebrew is required for the release.

**Exercise 6.** A `LocalDate` is formatted for `vi-VN` and `en-US`, then parsed back with the corresponding formatter. Should the date value change?

**Answer:** No. Those are two representations of the same date; a round-trip test must preserve the `LocalDate` value.

**Exercise 7.** An Arabic user enters the code `ABC-123`. Should the characters be reversed in the database because the UI is RTL?

**Answer:** No. Store the logical value and apply bidi isolation/orientation at the presentation layer as needed.

**Exercise 8.** When switching the locale to `tr-TR`, are `Collator` and `String.equalsIgnoreCase` semantically equivalent?

**Answer:** No. `Collator` uses locale-aware comparison rules, while `equalsIgnoreCase` does not accept a locale and does not replace Turkish collation.

**Exercise 9.** Why is calling `Locale.setDefault(ar)` inside a request not a good way to test or deploy multilingual behavior?

**Answer:** The default locale is shared JVM state that can affect other requests. Pass the locale explicitly, and isolate tests if you specifically need to test default-dependent overloads.

**Exercise 10.** A Vietnamese place name exists in composed and decomposed forms that look identical to the eye. Does `String.equals` treat them as equal automatically?

**Answer:** No. Java compares code units; if the contract requires canonical equivalence, normalize Unicode to `NFC` before comparing, without blindly normalizing sensitive data outside the contract.

**Exercise 11.** Does a passing `BidiSmokeDemo` test prove that an Arabic UI in Android/web/Swing renders properly?

**Answer:** No. It only tests the bidi algorithm on text data; rendering, fonts, direction, and UI interaction still require testing.

**Exercise 12.** A product is expanding into a new market that uses a non-ISO calendar. Is simply adding the locale to the matrix sufficient?

**Answer:** No. You also need calendar/chronology variants, numerals, zone, resource bundles, fonts, and domain-specific tests; a language-region locale does not determine everything automatically.

## 23. Pre-Release Checklist

- [ ] Every supported locale has resource bundles and translation coverage meeting release criteria.
- [ ] Key names/placeholders are consistent and fallback is controlled.
- [ ] Unit tests for number/date formatting run with `vi-VN`, `en-US`, `de-DE`, `tr-TR`, `ar-EG`, `he-IL`.
- [ ] Turkish I/ı/İ/i is tested and technical identifiers are guaranteed locale-independent.
- [ ] Localized number/date strings are not used as machine protocols without a contract.
- [ ] Currency/Chronology/ZoneId are chosen explicitly where business logic requires them.
- [ ] Collation is tested with native datasets, not replaced by `String.compareTo`.
- [ ] Visual UI tests exist for both Arabic and Hebrew with text mixing Latin/numbers/URLs.
- [ ] RTL forms work properly for caret movement, copy/paste, and validation.
- [ ] Fonts are supported and text does not overflow under long translations or zoom.
- [ ] Unicode, combining marks, emoji, and UTF-8 are tested.
- [ ] Multi-user logic does not rely on the JVM default locale.
- [ ] Java version/provider/font are recorded when debugging changing snapshots.
- [ ] Accessibility QA and native linguistic review are performed.
- [ ] Unit, integration, UI/E2E, and visual regression tests work together, not just one test type.

## 24. Summary

**A locale matrix is a tool for uncovering false assumptions in an application, not a list of translations to display.** With Java 17, start with `vi-VN`, `en-US`, `de-DE`, `tr-TR`, and at least two RTL languages such as `ar-EG` and `he-IL`.

Run the **right kinds of assertions**: number/date round-trips, Turkish Unicode casing, bundle fallback/key contracts, locale-aware collation, and proper encoding. Alongside that, verify **actual rendering** for RTL, fonts, diacritics, bidi/selection, overflow, and accessibility. Avoid hard-coding exact localized strings when JDK/CLDR data is not pinned; use exact literals only when an API or protocol defines an explicit contract.

If you need a single guiding principle: **business values, display language, UI direction, and protocol data must be kept separate; each layer needs appropriate tests.**

### Java SE 17 API References

- [Locale — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [NumberFormat — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [DateTimeFormatter — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [ResourceBundle — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Collator — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Bidi — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html)
- [String — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Unicode Bidirectional Algorithm (UAX #9)](https://www.unicode.org/reports/tr9/)
