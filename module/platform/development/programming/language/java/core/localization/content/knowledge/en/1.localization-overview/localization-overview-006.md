# Core Java API Groups for Localization

Localization (l10n) is the process of presenting content in the user's language and conventions: wording, digits, currencies, dates and times, region names, sorting order, and character boundaries. In Core Java, this work does not belong to a single API; multiple API groups work together. This lesson introduces the capabilities, selection criteria, and combinations of those API groups on Java 17+.

## 1. Distinguishing Internationalization and Localization

- **Internationalization (i18n):** Designing a program so displayed content can change by language/region without modifying business logic. Example: retrieving messages via keys rather than hardcoding them in source code.
- **Localization (l10n):** Providing translations and selecting conventions suitable for a specific locale. Example: Vietnamese translations, number separators, and date display styles.
- **Locale:** A collection of language, region, script, and variant characteristics; not synonymous with time zone, currency unit, current physical location, or complete translations.
- **Unicode:** A representation of text across many writing systems. Every localized application must handle Unicode properly, yet using UTF-8 alone is not enough to translate messages or format dates and times.

For example, the same numeric value **1234567.5** can be displayed differently depending on the locale. The numeric data in business logic remains a numeric value; separators belong strictly to the presentation layer. Similarly, an instant should be stored using an appropriate time type, and only formatted according to the user's locale and time zone.

## 2. Map of the Main API Groups

| Need | Core Java API Group | Role and Limitations |
| --- | --- | --- |
| Specify language/region | **java.util.Locale**, **Locale.Builder** | Creates, reads, and passes locale context; does not translate content by itself. |
| Look up translations | **java.util.ResourceBundle**, **PropertyResourceBundle**, **ListResourceBundle** | Fetches strings by key, selects bundles by locale, supports fallback mechanisms. |
| Insert parameters into sentences | **java.text.MessageFormat**, **ChoiceFormat** | Formats parameterized messages by locale; not an auto-translation system or complete solution for all plural rules. |
| Numbers, percentages, currencies | **java.text.NumberFormat**, **DecimalFormat**, **DecimalFormatSymbols**, **java.util.Currency** | Formats and parses numeric strings; does not convert exchange rates. |
| Dates, times | **java.time.format.DateTimeFormatter**, **FormatStyle**, **java.time.ZoneId**; legacy **java.text.DateFormat** API | Displays dates/times, controls locale and time zone. |
| Language-aware string sorting | **java.text.Collator**, **CollationKey** | Compares text by linguistic rules, unlike raw character comparison. |
| Segment text | **java.text.BreakIterator** | Finds word, sentence, line, or character cluster boundaries provided by the API. |
| Unicode normalization | **java.text.Normalizer**, **java.nio.charset.StandardCharsets** | Handles Unicode canonical forms and text byte encoding; does not replace translation or locale collation. |
| Parameterized text formatting | **java.util.Formatter**, **String.format(Locale, …)** | Useful for technical content, numbers, and layout; translatable sentence structures usually suit **MessageFormat** better. |

Not every API group is needed in every application. A simple screen typically needs only **Locale**, **ResourceBundle**, **MessageFormat**, **NumberFormat**, and **DateTimeFormatter**; search tools, directories, or text editors may additionally need **Collator**, **Normalizer**, and **BreakIterator**.

## 3. Locale: Shared Context for the APIs

### 3.1. Creating and Passing Locale

**Locale** is an immutable data type describing a language/region preference. Prefer explicit BCP 47 language tags, such as **vi-VN**, **en-US**, or **zh-Hant-TW** (Chinese language, Traditional script, Taiwan).

~~~java
import java.util.Locale;

public class LocaleExample {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        Locale traditionalChinese = new Locale.Builder()
                .setLanguage("zh")
                .setScript("Hant")
                .setRegion("TW")
                .build();

        System.out.println(vietnamese.toLanguageTag());
        System.out.println(traditionalChinese.toLanguageTag());
    }
}
~~~

Save as **LocaleExample.java**, then run:

~~~bash
javac LocaleExample.java
java LocaleExample
~~~

Output:

~~~text
vi-VN
zh-Hant-TW
~~~

A locale can carry only a language such as **vi**, or both language and region such as **vi-VN**. Region affects presentation conventions but does not determine time zone by itself. **Locale.ROOT** is the neutral locale for operations needing language independence; it is not a UI language for end users. Prefer passing the locale explicitly to formatting, translation lookup, and string comparison methods.

### 3.2. Default Locale and the Global State Trap

**Locale.getDefault()** reflects the JVM's default locale; **Locale.setDefault(...)** mutates shared process-wide state. Java also distinguishes **Locale.Category.DISPLAY** (region/language display names) and **Locale.Category.FORMAT** (formatting conventions). Relying on defaults causes output to differ across developer machines, CI, and servers.

In multi-user applications, each request or user profile should carry its own locale; never call **Locale.setDefault(...)** to switch languages per request. User-requested locales must also be checked against the list of languages the application actually supports. A valid locale does not guarantee that all translations exist.

## 4. ResourceBundle: Managing Strings by Language

### 4.1. Concept and Mechanism

**ResourceBundle** separates UI wording from Java code. Each message has a **stable key** such as **welcome**, **validation.required**, or **order.confirmed**. The same key can point to different text in individual **.properties** files or in classes extending **ListResourceBundle**.

Example with base name **messages**:

~~~text
messages.properties
messages_vi.properties
messages_vi_VN.properties
~~~

When **vi-VN** is selected, the most specific matching bundle is preferred, typically checking from variant/region to language and finally the base bundle. The default mechanism also has a fallback branch to the JVM's default locale in certain cases; do not assume every missing-translation request goes straight to the base file. If an application requires deterministic fallback, you can configure **ResourceBundle.Control** (where the packaging model supports that API) or design a language-selection policy right at the application layer.

Files must reside on the classpath in the matching package. For example, **com/example/i18n/messages_vi.properties** corresponds to base name **com.example.i18n.messages**. When resources sit in the current working directory and classpath, the simple base name **messages** is sufficient.

**Encoding note:** Since Java 9, **PropertyResourceBundle** loads from byte streams using UTF-8 by default, with an ISO-8859-1 compatibility fallback for invalid byte sequences. This differs from **java.util.Properties.load(InputStream)**, which defaults to ISO-8859-1; use a **Reader** with an explicit charset when needed. Save translation files in UTF-8 and verify encoding in your build pipeline.

### 4.2. Usage

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle labels = ResourceBundle.getBundle("messages", locale);
String title = labels.getString("page.title");
~~~

**getString** throws **MissingResourceException** if the bundle or key does not exist. Maintain a base file, validate all keys across languages at build time, log missing keys, and choose an appropriate error policy. **ResourceBundle** caches bundles; editing files while the program runs does not automatically reload new content. **ResourceBundle.clearCache()** can clear the cache, though reload workflows need explicit design.

Do not arbitrarily pass passwords, business codes, or unvalidated user-generated text into dynamic keys. Stable keys help detect missing translations, aid searching, and simplify testing.

## 5. MessageFormat: Assembling Messages in Linguistic Context

Concatenations like **"Xin chào, " + name + "!"** work, yet make it hard to reorder parameters when translating into other languages. **MessageFormat** lets translations decide parameter positions.

~~~properties
# messages_vi.properties
welcome=Xin chào, {0}!
purchase={0} đã mua {1,number,integer} sản phẩm.
~~~

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

String pattern = bundle.getString("welcome");
MessageFormat formatter = new MessageFormat(pattern, locale);
String result = formatter.format(new Object[] {"Mai"});
System.out.println(result);
~~~

The output of the illustrative snippet, once **locale** is declared, imported, and the bundle is loaded as above, is: **Xin chào, Mai!**. Placeholders **{0}**, **{1}** reference parameters by index; the syntax **{1,number,integer}** instructs MessageFormat to format the second value as an integer according to the locale. You can use the **number**, **date**, **time**, and **choice** format types supported by MessageFormat.

**Important pitfalls:**
- Single quotes have special meaning in **MessageFormat** patterns. To display a literal single quote normally, you usually must write two consecutive quotes in the pattern, such as **You''re {0}**. Test translations containing apostrophes.
- **MessageFormat** uses the legacy date/time formatting model for date parameters; for **java.time.LocalDate** or **Instant**, it is usually better to format beforehand with **DateTimeFormatter** and pass the resulting string into the pattern.
- **ChoiceFormat** can express simple selections, but pluralization, grammatical gender, and inflection rules across many languages are complex. Do not assume Core Java includes full ICU MessageFormat plural syntax; projects needing complex rules may consider ICU4J or a dedicated localization layer.
- **MessageFormat** holds mutable state and should not share a single mutable instance across threads without synchronization/control; create instances per use or keep separate safe configurations.

## 6. NumberFormat, DecimalFormat, and Currency

### 6.1. Formatting for Display

**NumberFormat** is a high-level API that selects thousand grouping symbols, decimal marks, percentages, and currency symbols by locale. Common factories:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat number = NumberFormat.getNumberInstance(locale);
NumberFormat integer = NumberFormat.getIntegerInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
NumberFormat money = NumberFormat.getCurrencyInstance(locale);

System.out.println(number.format(1234567.5));
System.out.println(integer.format(1234567));
System.out.println(percent.format(0.25));
System.out.println(money.format(1234567));
~~~

This is an illustrative snippet inside a method and requires importing **java.text.NumberFormat** and **java.util.Locale**. Exact formatted output can vary by locale data and JDK version, so do not hardcode spaces or separators in tests. Notably, percentages accept ratios: **0.25** means **25%**, not 0.25%.

**Currency** represents an ISO 4217 currency code. A locale with a region usually picks a default currency for **getCurrencyInstance**; when business logic determines the currency, set it explicitly:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance(Locale.US);
formatter.setCurrency(java.util.Currency.getInstance("JPY"));
~~~

Setting **JPY** changes the currency metadata and formatting symbol/decimal digits; it does **not** convert USD values to JPY or look up exchange rates. Never infer a currency unit solely from the user's locale. For business monetary data, prefer **BigDecimal** with an explicit currency code to avoid floating-point errors.

### 6.2. Custom Patterns and Parsing Back

**DecimalFormat** supports patterns such as **#,##0.00**; **DecimalFormatSymbols** provides locale-specific symbols. If you need to parse a numeric string back into a value, use **NumberFormat.parse** with the corresponding locale. The return type is **Number**, not **BigDecimal** by default.

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberParsingExample {
    public static void main(String[] args) throws Exception {
        NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
        DecimalFormat decimal = (DecimalFormat) format;
        decimal.setParseBigDecimal(true);

        BigDecimal value = (BigDecimal) decimal.parse("1,234.50");
        System.out.println(value.toPlainString());
    }
}
~~~

Save as **NumberParsingExample.java**, run with **javac NumberParsingExample.java** then **java NumberParsingExample**. Exact output:

~~~text
1234.50
~~~

For user input, **parse(String)** can accept a valid prefix without checking trailing characters; to ensure the entire string is consumed, use the overload taking **ParsePosition** and check the ending index. Parsing user-entered numbers must also handle whitespace, invalid values, and business domain bounds. **NumberFormat/DecimalFormat** formatters are mutable and must not be assumed thread-safe across concurrent threads.

## 7. Dates, Times, and Time Zones: DateTimeFormatter Is the Modern Choice

Java 17+ prefers the **java.time** package: **LocalDate** is a calendar date without time/zone; **LocalDateTime** does not represent a global instant; **Instant** represents a point on the UTC timeline; **ZonedDateTime** binds a timestamp/date-time with a **ZoneId**. Locale and time zone are two independent decisions.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class DateLocalizationExample {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter localDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
        System.out.println(localDate.format(date));

        Instant instant = Instant.parse("2026-10-28T03:00:00Z");
        DateTimeFormatter localDateTime = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(locale)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println(localDateTime.format(instant));
    }
}
~~~

Save **DateLocalizationExample.java** and run **javac DateLocalizationExample.java**, **java DateLocalizationExample**. The first line is October 28, 2026 in Vietnamese conventions; the second line is the corresponding time in the **Asia/Ho_Chi_Minh** time zone. Month spelling, separators, or spaces can vary between JDK locale data versions, so test time values and structure rather than matching a hardcoded localized string if the environment is not pinned.

- **DateTimeFormatter.ofLocalizedDate/Time/DateTime** and **FormatStyle** are good choices for user screens.
- **DateTimeFormatter.ofPattern(...)** is used when the product specifies an exact pattern; pass the locale whenever the pattern includes textual month/weekday names.
- For time records or API communication, prefer deterministic standard formats such as **DateTimeFormatter.ISO_INSTANT**, rather than arbitrary locale display patterns.
- **DateTimeFormatter** is immutable and safe to share across threads. **java.text.DateFormat/SimpleDateFormat**, **java.util.Date**, **Calendar**, and **TimeZone** belong to the legacy API; understand them for maintenance, but avoid choosing them by default for new code.
- **WeekFields.of(locale)** supports conventions for the first day of the week and minimum days in the first week; do not assume every region starts weeks on Monday. Non-ISO calendars are a separate **Chronology** concern and are not automatically inferred properly from language alone.

Do not format an **Instant** by guessing **ZoneId** from Locale; the same language can be used across many time zones. Obtain the zone from settings, user profile, or business rules.

## 8. Collator: Language-Aware Text Comparison and Sorting

**String.compareTo** compares order based on Unicode/UTF-16 code units; it does not enforce language-specific sorting rules. For instance, the ordering of accented letters can differ between Vietnamese, German, and Swedish.

~~~java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

public class SortingExample {
    public static void main(String[] args) {
        String[] names = {"Ánh", "An", "Ân", "Bình"};
        Collator collator = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        Arrays.sort(names, collator);
        System.out.println(Arrays.toString(names));
    }
}
~~~

Save **SortingExample.java**, compile/run similarly to the previous examples. Output depends on the collation rules supported by the JDK version, so do not enforce a specific order in tests without a pinned environment.

The levels **Collator.PRIMARY**, **SECONDARY**, and **TERTIARY** control which character differences are considered, such as accent or case differences, though exact effects still vary by locale. Do not use locale collation as the identity standard for account names, IDs, or security keys. When comparing the same data repeatedly, **CollationKey** can be useful, provided the keys come from compatible Collator configurations. Because Collator is mutable, do not share an instance and mutate its strength across threads.

## 9. Normalizer, BreakIterator, and Unicode Handling

Two visually identical strings can have different Unicode code sequences: for example, a precomposed accented letter versus a base letter plus a combining mark. **Normalizer** brings text into canonical forms, commonly **NFC** (composed) and **NFD** (decomposed).

~~~java
import java.text.Normalizer;

public class UnicodeExample {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(composed.equals(decomposed));
        System.out.println(Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)));
    }
}
~~~

Save **UnicodeExample.java**, run **javac UnicodeExample.java** and **java UnicodeExample**. Output:

~~~text
false
true
~~~

**Normalization does not mean stripping diacritics**: NFD only decomposes; it does not automatically remove combining marks. Never silently strip diacritics from personal names, legal data, or text requiring exact spelling. Normalization should follow a consistent policy at input, search, or matching boundaries; it does not replace Collator when language-aware sorting is needed.

**BreakIterator** finds boundaries better suited to natural text than slicing strings at arbitrary indices:

~~~java
BreakIterator words = BreakIterator.getWordInstance(locale);
BreakIterator sentences = BreakIterator.getSentenceInstance(locale);
BreakIterator characters = BreakIterator.getCharacterInstance(locale);
~~~

These are illustrative lines requiring **java.text.BreakIterator** to be imported and **locale** defined. Use **setText(text)**, **first()**, **next()**, and the constant **BreakIterator.DONE** to iterate over boundaries. Do not assume every segment between two word boundaries is a meaningful word; punctuation and whitespace also produce segments. Segmentation rules, especially for combined emoji and complex scripts, depend on the JDK version's Unicode support.

**String.length()** counts UTF-16 code units, not user-perceived characters. **String.codePoints()** iterates over code points, yet one visible character cluster may still comprise multiple code points. Therefore, input length checks, highlighting, and text truncation must decide upfront whether to count code units, code points, or visible character clusters.

## 10. Formatter, Charset, and Supporting APIs

**String.format(locale, pattern, args...)** and **Formatter** let you format numbers by locale in technical strings. For example, **String.format(Locale.US, "%.2f", 1.5)** returns **1.50**. However, format expressions like **"Hello %s"** usually fix word order, whereas **MessageFormat** interpolates within translated messages more flexibly. Do not treat **String.format** as a translation system.

**StandardCharsets.UTF_8**, **InputStreamReader**, **OutputStreamWriter**, **Files.readString(path, UTF_8)**, and **Files.writeString(path, text, UTF_8)** help read and write text consistently. UTF-8 is a data transmission foundation; it does not determine number separators or sorting rules. For JSON/HTTP, set charset or media type per the communication contract instead of relying on the platform's default encoding.

Additionally, **Locale.getDisplayLanguage(...)**, **getDisplayCountry(...)**, and **Locale.getDisplayName(...)** can display language/region names; **java.util.spi** provides locale provider extension points for specialized cases. This is an advanced group and is usually unnecessary just for switching UI languages.

## 11. Complete Example: Combining ResourceBundle, MessageFormat, NumberFormat, and DateTimeFormatter

The following example runs on Java 17+ with three files in the same directory. The program reads a language tag from command-line arguments, defaulting to **vi-VN**, loads the greeting from resources, and formats a number and date using the same locale.

**File messages.properties**

~~~properties
greeting=Hello, {0}!
~~~

**File messages_vi.properties**

~~~properties
greeting=Xin chào, {0}!
~~~

**File LocalizationDemo.java**

~~~java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizationDemo {
    public static void main(String[] args) {
        String languageTag = args.length == 0 ? "vi-VN" : args[0];
        Locale locale = Locale.forLanguageTag(languageTag);

        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);
        String greeting = new MessageFormat(
                messages.getString("greeting"), locale)
                .format(new Object[] {"Mai"});

        NumberFormat numbers = NumberFormat.getNumberInstance(locale);
        DateTimeFormatter dates = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);

        System.out.println("Locale: " + locale.toLanguageTag());
        System.out.println(greeting);
        System.out.println("Số: " + numbers.format(1234567.5));
        System.out.println("Ngày: " + dates.format(LocalDate.of(2026, 10, 28)));
    }
}
~~~

Run in the directory containing the three files:

~~~bash
javac -encoding UTF-8 LocalizationDemo.java
java -cp . LocalizationDemo vi-VN
~~~

The first two lines of stdout are **exact**:

~~~text
Locale: vi-VN
Xin chào, Mai!
~~~

Then the program prints two more lines starting with **Số:** and **Ngày:**. The rendering of separators, spaces, month words, and field order depends on the active JDK's localization data. When running **en-US** in an environment with matching resources or appropriate fallback, both content and presentation change. The example does not mutate the global default locale, making it safer for multi-user applications.

Processing flow of the example:

1. Convert the language choice into a **Locale** object.
2. Locate the matching bundle and retrieve text by key.
3. Insert the name at the position specified by the translation using **MessageFormat**.
4. Use **NumberFormat** and **DateTimeFormatter** to display typed data without storing formatted strings as canonical data.

If the application expands to more languages, add corresponding bundle files (such as **messages_ja.properties**) and use a supported-locales list to select the language. The demos use the standard classpath; in modular Java applications declaring **module-info.java**, packaging and resource lookup rules must be checked separately.

## 12. Choosing APIs by Scenario and Avoiding Common Mistakes

| Scenario | Practical Choice | What to Avoid |
| --- | --- | --- |
| Buttons, error messages, page titles | **ResourceBundle** + fixed keys | Hardcoding Vietnamese/English in logic or using arbitrary keys. |
| Sentences with personal names, counts, amounts | **MessageFormat** + typed data; **NumberFormat** when appropriate | Fixed string concatenation and ignoring parameter order/single quotes. |
| Invoice prices and currency units | **BigDecimal** + **Currency** + **NumberFormat** | Using **double** for exact money; treating symbol changes as currency conversion. |
| User number input | **NumberFormat.parse** + remainder/range checks | Using **Double.parseDouble** for all locales or accepting trailing junk. |
| Displaying date and time to users | **java.time** + **DateTimeFormatter** + explicit locale/zone | Guessing time zone from language; storing formatted dates as data. |
| Sorting name lists by language | **Collator** | Relying only on **String.compareTo** and expecting linguistic order. |
| Searching/slicing strings with diacritics, emoji | **Normalizer**/**BreakIterator** with a Unicode policy | Counting visible characters with **String.length()** or stripping diacritics unintentionally. |
| Reading/writing multilingual text | Explicit **UTF-8** | Confusing charset with locale or relying on platform default. |

Implementation checklist:
- Clearly define **supported locales**, default language, and fallback order; verify bundles for missing keys at build time.
- Resolve locale per request/user and pass it explicitly; avoid mutating JVM defaults to handle individual users.
- Store business data in canonical types: numbers, currency codes, dates/instants, time zones; localize only at UI/export boundaries.
- Test with at least two locales having different conventions, one locale with incomplete translations, translations containing single quotes/parameters, Unicode text with combining marks, and time zones across day boundaries.
- When snapshot-testing JDK locale-formatted strings, pin the Java version and locale data if byte-for-byte output is required; JDK releases can update CLDR data so display output is not guaranteed invariant.
- Check translated string lengths (translations can be longer than the source sentence), right-to-left readability if supported, and friendly error messages when keys are missing or input is invalid.

## 13. Key Takeaways

**Locale** defines context; **ResourceBundle** supplies text; **MessageFormat** assembles messages; **NumberFormat/Currency** and **DateTimeFormatter** present typed data; **Collator/Normalizer/BreakIterator** process text by linguistic and Unicode rules. They address distinct layers and complement one another. Proper design separates canonical data from display strings, passes locale and time zone intentionally, and tests across the languages the product commits to supporting.
