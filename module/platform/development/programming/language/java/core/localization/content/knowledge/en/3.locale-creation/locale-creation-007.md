# Unicode Locale Extensions for Calendar, Numbering System, and Other Conventions

## 1. Why Language and Country Alone Are Not Enough

A `Locale` in Java is commonly imagined through language (`language`), script (`script`), and region (`region`). However, two people both using Thai in Thailand may still want different **calendar systems** or **numbering systems**; two people both using German in Germany may want different **string collation/sorting orders**.

**Unicode locale extensions** provide a way to record *preferences for local conventions* directly inside a **BCP 47** language tag, introduced by `-u-`. In Java, `java.util.Locale` stores and lets you query these preferences.

Examples:

| Locale Tag | Base Components | Unicode Extension | Preference Meaning |
| --- | --- | --- | --- |
| `th-TH` | Thai, Thailand | Undeclared | Uses default conventions decided by the API/locale data |
| `th-TH-u-ca-buddhist` | `th-TH` | `ca=buddhist` | Requests the Buddhist calendar when supported by the API |
| `th-TH-u-nu-thai` | `th-TH` | `nu=thai` | Prefers Thai digits in number formatting when supported by the API |
| `th-TH-u-ca-buddhist-nu-thai` | `th-TH` | `ca=buddhist`, `nu=thai` | Combines both preferences |
| `de-DE-u-co-phonebk` | `de-DE` | `co=phonebk` | Requests phonebook collation/sorting order, if supported by the service |
| `en-US-u-hc-h23` | `en-US` | `hc=h23` | Prefers a 0–23 hour cycle where supported |

Core principle: **a Unicode locale extension describes a preference, not a command forcing every API to automatically execute that preference**. The locale-creation API can store `u-ca`, `u-nu`, `u-co`, or `u-hc` completely; whether formatting or sorting actually changes depends on the API, Java version, locale data, and provider in use.

## 2. Structure of `-u-` in a BCP 47 Tag

Consider the following tag:

~~~text
th-TH-u-ca-buddhist-nu-thai
│  │  │ │  │        │  └── thai: Thai digit style
│  │  │ │  │        └───── nu: numbering system key
│  │  │ │  └────────────── buddhist: Buddhist calendar type
│  │  │ └───────────────── ca: calendar key
│  │  └─────────────────── u: Unicode locale extension
│  └────────────────────── TH: region/territory
└───────────────────────── th: language
~~~

The `u` portion is a BCP 47 **extension singleton**; following it are attributes (if any) and **keyword key–type** pairs.

- Unicode locale keyword keys such as `ca`, `nu`, `co`, and `hc` have **two alphanumeric characters** per extension syntax.
- Type values typically consist of one or more subtags, such as `buddhist`, `gregory`, `latn`, `thai`, or `phonebk`. Whether a value is understood by a service is a separate matter from whether the syntax is valid.
- Multiple keywords can coexist within a single `-u-` extension. When exporting the tag via `Locale.toLanguageTag()`, Java uses a canonical form, including keyword ordering.
- `language`, `script`, `region`, and `variant` live in the main tag; keywords live in the extension. **`ca` does not replace language; `nu` does not replace region.**

For example, `en-US-u-ca-buddhist-nu-thai` still has `getLanguage()` equal to `en` and `getCountry()` equal to `US`. Calendar and numbering system are additional preferences; they do not turn the locale into Thai.

**Distinguishing from other extensions:** `-x-` is for private use; a tag can have extensions other than `-u-`. `Locale.stripExtensions()` removes **all** extensions, not just one Unicode keyword. Do not use this method if you want to remove a single preference while preserving others.

## 3. Important Keywords and Applicability Limits

| Keyword | Meaning | Example | What to Understand Correctly |
| --- | --- | --- | --- |
| `ca` | Calendar system | `ca-buddhist`, `ca-gregory`, `ca-japanese` | Used to choose a calendar system in supporting APIs; does **not** determine time zone |
| `nu` | Numbering system | `nu-latn`, `nu-thai`, `nu-arab` | Affects digit shapes in supporting formatters; does **not** change integer values |
| `co` | Collation | `co-phonebk`, `co-pinyin` | Refers to text comparison/sorting; level of support depends on the collator |
| `hc` | Hour cycle | `hc-h12`, `hc-h23` | Preference for 12/24-hour clock display, though not every time API applies it |
| `fw` | First day of week | `fw-mon`, `fw-sun` | Describes the first day of the week; check whether the calendar API uses it |
| `ms` | Measurement system | `ms-metric`, `ms-ussystem` | Describes unit conventions; does not automatically convert measured values |
| `kn` | Numeric collation | `kn-true` | Relates to comparing strings containing numbers when supported by the collator |

Keywords and type values belong to the Unicode locale data system (UTS #35/CLDR). Do not infer that Java SE is required to support every combination simply because `Locale.Builder` accepts the tag. Typical values in the table above help read configuration requirements, not serve as an exhaustive catalog.

### Three Layers to Distinguish

1. **Identification and storage:** `Locale` preserves keywords present in the tag and allows reading them back.
2. **Data and providers:** the JDK or library needs corresponding rules for calendars, number symbols, collation, etc.
3. **Consuming API:** your code must go through an API that understands the keyword. An ordinary `String`, `LocalDate`, or `String.compareTo` comparison does not change automatically just because you created a `Locale` with an extension.

For example, `nu-thai` affects how numbers are *presented* when using a supporting formatter; the addition `123 + 7` is still `130`, the `int` type does not change, and `Integer.toString(123)` still uses ordinary ASCII characters `1`, `2`, `3`.

## 4. Creating and Reading Unicode Locale Extensions in Java 17+

Java provides built-in APIs for working with Unicode extensions:

- `Locale.forLanguageTag(String)`: reads a BCP 47 tag from a string.
- `Locale.Builder.setLanguageTag(String)`: builds a locale from a tag, checking syntax errors more strictly.
- `Locale.Builder.setUnicodeLocaleKeyword(String key, String type)`: sets or replaces a Unicode keyword in the locale being built.
- `Locale.getUnicodeLocaleKeys()`: set of Unicode keyword keys.
- `Locale.getUnicodeLocaleType(String key)`: reads the type value of a key; returns `null` if the key is absent.
- `Locale.getExtension('u')`: retrieves the full value of extension `u` as a string, omitting the leading `u-`.
- `Locale.toLanguageTag()`: outputs the normalized tag.
- `Locale.stripExtensions()`: creates a new locale without extensions.

### Example 1 — Creating, Querying, and Comparing Locales

Save the following code in `UnicodeLocaleDemo.java`:

~~~java
import java.util.Locale;

public class UnicodeLocaleDemo {
    public static void main(String[] args) {
        Locale base = Locale.forLanguageTag("th-TH");

        Locale preferred = new Locale.Builder()
                .setLocale(base)
                .setUnicodeLocaleKeyword("ca", "buddhist")
                .setUnicodeLocaleKeyword("nu", "thai")
                .build();

        System.out.println("Tag: " + preferred.toLanguageTag());
        System.out.println("Language: " + preferred.getLanguage());
        System.out.println("Region: " + preferred.getCountry());
        System.out.println("Unicode u: " + preferred.getExtension('u'));
        System.out.println("Calendar: " + preferred.getUnicodeLocaleType("ca"));
        System.out.println("Numbers: " + preferred.getUnicodeLocaleType("nu"));
        System.out.println("Collation absent: "
                + (preferred.getUnicodeLocaleType("co") == null));
        System.out.println("Base without extensions: "
                + preferred.stripExtensions().toLanguageTag());
        System.out.println("Same as base: " + preferred.equals(base));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 UnicodeLocaleDemo.java
java UnicodeLocaleDemo
~~~

Output:

~~~text
Tag: th-TH-u-ca-buddhist-nu-thai
Language: th
Region: TH
Unicode u: ca-buddhist-nu-thai
Calendar: buddhist
Numbers: thai
Collation absent: true
Base without extensions: th-TH
Same as base: false
~~~

Explanation:

1. `base` and `preferred` share language `th` and region `TH`.
2. `setUnicodeLocaleKeyword` adds only the two preferences; `getUnicodeLocaleType` reads those exact values back.
3. Java does not fill in undeclared keys: `getUnicodeLocaleType("co")` returns `null`.
4. `stripExtensions()` removes both preferences, returning the `th-TH` tag.
5. `Locale.equals` inspects extensions as well, so the two locales here differ. If an application builds a cache keyed by locale, decide explicitly whether to include extensions in the key; storing only `language + country` will lose preferences.

### Other Useful Operations

~~~java
Locale input = Locale.forLanguageTag("de-DE-u-co-phonebk");
System.out.println(input.getUnicodeLocaleType("co")); // phonebk

Locale changed = new Locale.Builder()
        .setLocale(input)
        .setUnicodeLocaleKeyword("co", null) // Remove only keyword co
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();
System.out.println(changed.toLanguageTag()); // de-DE-u-nu-latn
~~~

This is an **illustrative code fragment inside a Java method**, not a standalone program. Removing with `setUnicodeLocaleKeyword("co", null)` preserves the base components and any other extensions/keywords. An empty string type value has a different meaning from `null` for certain boolean-style Unicode keywords.

When receiving a locale from an external system, check syntax and the catalog of keywords allowed by your product. `Locale.forLanguageTag` may accept a valid prefix and drop subsequent invalid parts; `Locale.Builder.setLanguageTag` may throw `IllformedLocaleException` on malformed tags. **“A tag can be parsed” does not mean “the keyword is supported by the business API”.**

## 5. Using `ca` and `nu` in Java

### 5.1. Calendar: Same Region, Different Calendar System

In the `java.util.Calendar` API, the calendar system can be selected from `ca` when supported by the implementation/provider. For example, `th-TH-u-ca-buddhist` specifies the Buddhist Calendar; `th-TH-u-ca-gregory` specifies the Gregorian Calendar.

Save as `CalendarKeywordDemo.java`:

~~~java
import java.util.Calendar;
import java.util.Locale;

public class CalendarKeywordDemo {
    public static void main(String[] args) {
        Locale buddhist = Locale.forLanguageTag("th-TH-u-ca-buddhist");
        Locale gregory = Locale.forLanguageTag("th-TH-u-ca-gregory");

        Calendar first = Calendar.getInstance(buddhist);
        Calendar second = Calendar.getInstance(gregory);

        System.out.println(first.getCalendarType());
        System.out.println(second.getCalendarType());
        System.out.println(first.getTimeZone().getID().equals(
                second.getTimeZone().getID()));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CalendarKeywordDemo.java
java CalendarKeywordDemo
~~~

In a JDK supporting these two calendar types, the first two lines are:

~~~text
buddhist
gregory
~~~

The third line is typically `true` if the JVM does not change its default time zone between the two calls; the example intentionally **does not pin** the time zone or current date. The goal is to see that `ca` selects the calendar system, while time zone is a separate decision. To get deterministic results for instants, dates/times, and year numbers, specify the time zone and reference date explicitly before formatting.

**With `java.time`:** `LocalDate` is a date in the ISO system; holding a locale with `u-ca` does not automatically turn an existing `LocalDate` into a Buddhist calendar object. When you genuinely need a non-ISO calendar, use a chronology intentionally (such as `ThaiBuddhistChronology.INSTANCE` and `DateTimeFormatter.withChronology(...)`) and test the formatted output. Do not treat calling `withLocale(locale)` alone as a guarantee of changing chronology in all situations.

### 5.2. NumberFormat: Same Numeric Value, Different Digit Shapes

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class NumberingKeywordDemo {
    public static void main(String[] args) {
        int value = 12345;

        Locale latinDigits = Locale.forLanguageTag("th-TH-u-nu-latn");
        Locale thaiDigits = Locale.forLanguageTag("th-TH-u-nu-thai");

        NumberFormat western = NumberFormat.getIntegerInstance(latinDigits);
        NumberFormat thai = NumberFormat.getIntegerInstance(thaiDigits);

        System.out.println(western.format(value));
        System.out.println(thai.format(value));
        System.out.println(value);
    }
}
~~~

Save as `NumberingKeywordDemo.java` and run:

~~~bash
javac -encoding UTF-8 NumberingKeywordDemo.java
java NumberingKeywordDemo
~~~

With a CLDR provider supporting `nu-thai`, the output is typically:

~~~text
12,345
๑๒,๓๔๕
12345
~~~

A common mistake is treating the lines above as fixed output for **every** JVM. Digit styles, grouping separators, locale data, and provider settings can influence the output. Test on the JDK and configuration where your product is deployed. The third line still prints `12345` because it prints the `int` directly without going through `NumberFormat`.

In addition, choosing digits for **display** does not mean every **parsing** API supports every numbering system. If you need to read user-entered numbers, test `NumberFormat.parse` and your error-handling policy for expected inputs.

### 5.3. Other Conventions: Collation, Hours, Week, Measurement

For example, `de-DE-u-co-phonebk` expresses a request for phonebook collation, `en-US-u-hc-h23` expresses a desire for 24-hour clock format, and `en-US-u-fw-mon` suggests a Monday week start. You can read them with `getUnicodeLocaleType`, yet **each service has a different level of support**:

- For sorting, use a locale-aware collator (`Collator` or a specialized library such as ICU depending on requirements) and test with real datasets. `String.compareTo` compares UTF-16 code units, not local collation rules.
- For time formatting, configure formatter patterns transparently when 12/24-hour format is mandatory. Do not assume adding `hc-h23` alone will reliably change every `DateTimeFormatter`.
- For first day of week or measurement system, check specific API documentation or implement business rules instead of expecting `fw`/`ms` to automatically alter every calculation, screen, or library.

## 6. Designing a Proper Locale Processing Flow

Suppose a user chooses Thai, Buddhist calendar, and Thai digits. A reliable implementation flow is:

~~~text
User selection
    |
    v
th-TH-u-ca-buddhist-nu-thai
    |
    +--> Store the full language tag in profile/config
    |
    +--> Locale.forLanguageTag(...) on the Java side
    |
    +--> Supporting Calendar / NumberFormat / formatter
    |
    +--> Test displayed values and fallback
~~~

**Application principles:**

1. **Preserve the full tag:** store `Locale.toLanguageTag()` (or a validated and normalized input tag) when preferences must persist across requests, sessions, or services. Do not store only `th-TH` if `ca`/`nu` are intentional choices.
2. **Separate preference from capability:** an API being able to store `u-ca`/`u-nu` does not prove formatters actually support those type values. Choose suitable APIs and handle unsupported values.
3. **Have a fallback policy:** when a calendar or numbering system is unavailable, clearly define which default is used, whether the user is notified, and how consistency is kept across screens.
4. **Do not let metadata alter source data:** monetary amounts, timestamps, and stored points in time should not depend on display symbols. Calendar and digit rules used in the UI must remain separate from durable data representation.
5. **Key caches and compare with all relevant parts:** two locales sharing `language` and `region` can still differ in `u-nu` or `u-ca`. For formatted results that depend on those keywords, caching solely by `language/region` can return the wrong result.
6. **Mind the time zone:** `ca` is a calendar system, **not** a `ZoneId`. When presenting real dates and times, choose the time zone separately, especially when communicating between servers and users across regions.
7. **Ensure library compatibility:** run tests on the actual JDK/provider. Third-party libraries sometimes read different extensions or ignore them; passing a `Locale` into a function does not automatically confirm support.
8. **Test both parsing and formatting:** handle user input, forms, CSV, APIs, and different character sets without accidentally forcing display formatting into storage format.

### Targeted Testing

| Test Scenario | What to Verify |
| --- | --- |
| `th-TH` vs `th-TH-u-nu-thai` | Does number formatting output differ when supported by provider; does numeric value stay unchanged |
| `th-TH-u-ca-buddhist` vs `th-TH-u-ca-gregory` | Does `Calendar.getCalendarType()` match the specified choice |
| Valid keyword but unsupported by provider | Application handles fallback/warning clearly |
| Tag without `nu` keyword | `getUnicodeLocaleType("nu")` returns `null`; application uses default policy |
| Tag with two keywords | Reads back both `ca` and `nu`, without losing preferences during serialization |
| User changes preference | Cache, profile, and UI update properly without mixing results from the old locale |

## 7. Common Misconceptions and Corrections

| Misconception | Correct Understanding |
| --- | --- |
| “`th-TH` always means the Buddhist calendar.” | The base locale does not explicitly specify the keyword; default behavior depends on the API and data/provider. To specify explicitly, use `ca-buddhist`. |
| “With `nu-thai`, an `int` holds Thai digits.” | `int` remains a numeric value; the formatter chooses characters to represent it. |
| “If `getUnicodeLocaleType("ca")` returns `buddhist`, every API uses the Buddhist calendar.” | That only confirms metadata. You must verify each API, including `java.time` and external libraries. |
| “`ca` is country/region.” | `ca` is the Unicode keyword for **calendar**; `getCountry()` still reflects the region in the main part of the locale. |
| “All extensions are `-u-`.” | BCP 47 has other extensions and `-x-` private use. |
| “Calling `stripExtensions()` removes only `ca`.” | The method removes **all** extensions. To remove one Unicode keyword, use `Locale.Builder.setUnicodeLocaleKeyword(key, null)`. |
| “Default `ResourceBundle` automatically picks translations by `u-nu`/`u-ca`.” | Standard bundle lookup rules rely mainly on language/script/region/variant; do not design translation filenames around extensions unless implementing a custom bundle selection mechanism. |
| “Testing `Locale.toLanguageTag()` is enough.” | Add real tests on Calendar/NumberFormat/collators/formatters and storage, cache, and fallback flows. |

## 8. Self-Check Exercises

1. Create a `Locale` from `en-US-u-ca-japanese-nu-latn`. What do `getLanguage()`, `getCountry()`, `getUnicodeLocaleType("ca")`, and `getUnicodeLocaleType("nu")` return respectively? Why is the language part still `en`?
2. Start with `th-TH-u-ca-buddhist-nu-thai` and use `Locale.Builder` to remove only the `ca` keyword. Write and check the remaining tag; verify `nu-thai` has not been lost.
3. Two requests with `th-TH-u-nu-latn` and `th-TH-u-nu-thai` query a number-formatting cache. If the cache key is only `th-TH`, what bug can occur?
4. Compare `Calendar.getCalendarType()` for two tags differing only in `ca`, then format the same number using two tags differing only in `nu`. Record the results and your JDK/provider details.
5. Explain why `hc-h23` or `co-phonebk` are stored in `Locale`, yet system-wide compliance with them should not be taken for granted.

**Key takeaway:** `-u-` extends a BCP 47 language tag with localization preferences such as `ca` (calendar system), `nu` (numbering system), and `co` (collation rules). In Java, `Locale` **stores and queries** these keywords; the **specific processing API** decides whether they are applied. To satisfy business requirements, store the full tag, pick the right APIs, test on real providers, and build explicit fallback.