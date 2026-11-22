# Language, Script, Region, and Variant Components in Java `Locale`

## 1. Nature of `Locale`

`java.util.Locale` identifies the language, writing system, and regional conventions used in localization. The four key components of the model are:

| Component | Question it answers | Examples | Java Getter |
|---|---|---|---|
| `language` | Which language is used? | `vi`, `en`, `sr`, `zh` | `getLanguage()` |
| `script` | Which writing system is it written in? | `Latn`, `Cyrl`, `Hans`, `Hant` | `getScript()` |
| `region` | Which regional conventions are preferred? | `VN`, `US`, `TW`, `419` | `getCountry()` |
| `variant` | Is there any specialized variant? | `POSIX`, `rozaj` | `getVariant()` |

The components describe different dimensions. A single language can be written in multiple scripts; a single region can use multiple languages; the same language can have different presentation conventions across regions. `Locale` also has **extensions** (such as calendar or numbering system), which sit outside the four components above.

`Locale` is an **identifier/context** for APIs, not a translation repository, does not represent a time zone, and does not infer the user's actual geographic location. Having a valid `Locale` also does not guarantee that the system has translations or dedicated data for that locale.

## 2. BCP 47: Representation as a language tag

An IETF BCP 47 language tag typically has the form:

```text
language[-Script][-REGION][-variant...][-extension...]
```

Subtags are separated by a hyphen `-`. The readable convention is lowercase language (`en`), title-case script (`Latn`), uppercase region (`US`), and usually lowercase variant. Java normalizes some fields when constructing a `Locale`; do not rely on letter casing to infer meaning.

| Language tag | Language | Script | Region | Variant | Meaning |
|---|---|---|---|---|---|
| `vi-VN` | `vi` | empty | `VN` | empty | Vietnamese in Vietnam |
| `en-US` | `en` | empty | `US` | empty | English in the United States |
| `en-GB` | `en` | empty | `GB` | empty | English in the United Kingdom |
| `sr-Latn-RS` | `sr` | `Latn` | `RS` | empty | Serbian, Latin script, in Serbia |
| `sr-Cyrl-RS` | `sr` | `Cyrl` | `RS` | empty | Serbian, Cyrillic script, in Serbia |
| `zh-Hant-TW` | `zh` | `Hant` | `TW` | empty | Chinese, Traditional Han script, in Taiwan |
| `en-US-POSIX` | `en` | empty | `US` | `POSIX` | A POSIX variant |

A field that is **absent** is genuinely an empty field in the object, not a default value automatically filled in. `zh-TW` does not declare a script, even though applications might infer one from cultural data. If the script itself is a condition for selecting content, use an explicit tag such as `zh-Hant-TW`.

## 3. `language` — language

`language` identifies the requested language, usually using ISO 639 codes such as `vi` (Vietnamese), `en` (English), `fr` (French), `ja` (Japanese), `zh` (Chinese), `sr` (Serbian). Common language codes have two or three letters; BCP 47 allows other valid syntactic forms. `getLanguage()` returns the code normalized to lowercase.

Key point: **language is not synonymous with country**. `en` does not implicitly mean `en-US`; `fr` does not implicitly mean `fr-FR`. Language also does not specify a script if script is left empty. For an application that only needs to select a generic language, `Locale.forLanguageTag("en")` may suffice. When selecting specific date, currency, or spelling rules, check region/script as well.

## 4. `script` — writing system

`script` uses a **four-letter** ISO 15924 code; examples include `Latn` (Latin), `Cyrl` (Cyrillic), `Hans` (Simplified Han), `Hant` (Traditional Han), and `Arab` (Arabic). `getScript()` returns the code with the first letter capitalized when present.

Script is practically significant when the same language exists in multiple writing systems:

- `sr-Latn` and `sr-Cyrl` are both Serbian, but use Latin and Cyrillic scripts.
- `zh-Hans` and `zh-Hant` both have language `zh`, but distinguish Simplified and Traditional Han scripts.

`Hans`/`Hant` is a **script**, not a region. Script also differs from **encoding**: `Latn` does not mean UTF-8; byte encoding belongs to a different API (such as `StandardCharsets.UTF_8`). If you only compare `getLanguage()` and ignore script, the application may serve the wrong character set/writing system.

## 5. `region` — country or area

`region` is usually a two-letter ISO 3166-1 country code (`VN`, `US`, `FR`, `TW`) or a three-digit UN M.49 area code (`001` for World, `419` for Latin America). Java's API structure has a naming difference: `Locale.Builder.setRegion(...)` sets the region, whereas `Locale.getCountry()` reads it. For letter codes, the value is normalized to uppercase; numeric region codes remain unchanged.

`en-US` and `en-GB` share the same language but have different regions; `en-CA` and `fr-CA` share the same region but have different languages. Region helps select number, date, currency formatting, and local conventions, but **does not solely determine** all data. The result still depends on the API, JDK version, and locale/provider data.

Do not use region in place of a **time zone** or **fixed currency**: a country can have multiple time zones, and currency rules can change. Use `java.time.ZoneId` and `java.util.Currency` when business logic requires dedicated identifiers.

## 6. `variant` — specialized variant

`variant` indicates a specific variant not fully described by language + script + region. `getVariant()` returns an empty string when no variant is present.

BCP 47 requires each variant subtag to be **5–8 alphanumeric characters**, or **4 characters starting with a digit**. Multiple variants may be present. `POSIX` and `rozaj` are examples with valid syntax. `Locale.Builder.setVariant(...)` validates syntax and can throw `IllformedLocaleException` when invalid. It **does not** automatically validate whether each code is registered or has practical meaning in locale data.

Three examples to distinguish:

- `en-US`: empty variant.
- `en-US-POSIX`: variant is `POSIX`.
- `en-US-u-nu-thai`: variant is still empty; the `u-nu-thai` part is a **Unicode locale extension** specifying the `thai` numbering system. Retrieve it using `getUnicodeLocaleType("nu")`.

Similarly, `u-ca-japanese` specifies selecting a calendar system belonging to extensions, not variant. Do not use variant to stuff user IDs, tenants, time information, or arbitrary configuration. The legacy constructor `new Locale(language, country, variant)` may hold a variant that does not follow BCP 47 syntax; converting back to a language tag can cause compatibility issues. For new code, prefer `Locale.Builder` and standard tags.

## 7. Runnable Java 17+ example: reading all four components

Create the file `LocalePartsDemo.java`:

```java
import java.util.Locale;

public class LocalePartsDemo {
    public static void main(String[] args) {
        show(Locale.forLanguageTag("en-US"));
        show(Locale.forLanguageTag("sr-Latn-RS"));
        show(Locale.forLanguageTag("zh-Hant-TW"));

        Locale posix = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setVariant("POSIX")
                .build();
        show(posix);
    }

    private static void show(Locale locale) {
        System.out.printf(
                "tag=%s | language=%s | script=%s | region=%s | variant=%s%n",
                locale.toLanguageTag(),
                display(locale.getLanguage()),
                display(locale.getScript()),
                display(locale.getCountry()),
                display(locale.getVariant()));
    }

    private static String display(String value) {
        return value.isEmpty() ? "(trong)" : value;
    }
}
```

Compile and run in the directory containing the file:

```bash
javac LocalePartsDemo.java
java LocalePartsDemo
```

Output:

```text
tag=en-US | language=en | script=(trong) | region=US | variant=(trong)
tag=sr-Latn-RS | language=sr | script=Latn | region=RS | variant=(trong)
tag=zh-Hant-TW | language=zh | script=Hant | region=TW | variant=(trong)
tag=en-US-POSIX | language=en | script=(trong) | region=US | variant=POSIX
```

`(trong)` is merely a label chosen by the `display` method for presentation; the actual getters return `""` for missing components. Notably, the region getter is named `getCountry()`, with no corresponding `getRegion()`.

## 8. Creating `Locale`, converting, and checking syntax

### From a BCP 47 language tag

```java
Locale locale = Locale.forLanguageTag("sr-Latn-RS");
String tag = locale.toLanguageTag(); // "sr-Latn-RS"
```

`forLanguageTag(...)` is suitable for converting a valid language tag into a `Locale`. However, it is **not a strict validation tool**: when encountering an invalid subtag, it may ignore the invalid part without throwing an exception.

### From individual fields

```java
Locale locale = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();

System.out.println(locale.toLanguageTag()); // sr-Latn-RS
```

`Builder` is suitable when a form/configuration provides each component individually. It validates the syntax of language, script, region, variant, and extension; for syntactically invalid strings, it can throw `IllformedLocaleException`. However, a **syntactically valid** combination may still lack resources or not be supported by the application.

Full example of validating a language tag with Builder, saved as `ValidateLocaleTag.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class ValidateLocaleTag {
    public static void main(String[] args) {
        String input = "sr-Latn-RS";

        try {
            Locale locale = new Locale.Builder()
                    .setLanguageTag(input)
                    .build();
            System.out.println(locale.toLanguageTag());
        } catch (IllformedLocaleException exception) {
            System.out.println("Language tag sai cu phap");
        }
    }
}
```

Run `javac ValidateLocaleTag.java` then `java ValidateLocaleTag`. Output:

```text
sr-Latn-RS
```

`Locale.Builder.setLanguageTag(...)` can detect syntax errors, but validating against the list of supported locales is the application's own policy. If the input data is an entire `Accept-Language` header with `q=...` weights, process it with appropriate negotiation syntax (such as `Locale.LanguageRange`/`Locale.lookup`) rather than passing the whole header as a single language tag.

### Why choose `toLanguageTag()` instead of `toString()`?

`Locale.toString()` uses Java's historical representation, which may contain `_` and script/extension parts in a non-BCP 47 structure. When storing or exchanging a locale with APIs, use `toLanguageTag()`; to read it back, use `forLanguageTag(...)` or `Builder`. Do not manually split `toString()` by underscores to infer all four components.

## 9. Applying in localization

Different needs lead to different choices:

| Need | Relevant component(s) | Examples |
|---|---|---|
| Select translated text | Language and sometimes script | `vi`; `sr-Latn` |
| Select the right script | Script | `sr-Latn` / `sr-Cyrl` |
| Select regional formatting conventions | Language + region | `en-US` / `en-GB` |
| Identify a rare defined variant | Variant | `sl-rozaj` |
| Select numbering system or calendar | Unicode extension, not variant | `en-US-u-nu-thai`; `ja-JP-u-ca-japanese` |

Example of a formatting API taking a locale as a parameter, saved as `FormatWithLocale.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class FormatWithLocale {
    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale fr = Locale.forLanguageTag("fr-FR");

        System.out.println(NumberFormat.getCurrencyInstance(us).format(1234.5));
        System.out.println(NumberFormat.getCurrencyInstance(fr).format(1234.5));
    }
}
```

Run `javac FormatWithLocale.java` then `java FormatWithLocale`. Grouping separators, decimal separators, currency symbols, and whitespace may vary across JDKs/providers/locale data; therefore **do not hardcode a single stdout** for this example. `Locale` specifies the context request, while `NumberFormat` performs the formatting.

`ResourceBundle` also uses `Locale` to find the appropriate bundle. When resources for the requested combination do not exist, the lookup mechanism may fall back to a less specific language/region, the default locale, or the root bundle according to `ResourceBundle` rules. Do not assume that a valid `Locale` will have complete translations; test the actual content returned after fallback.

Some APIs use the default locale if no object is passed. In a server application handling multiple users, **pass `Locale` explicitly to every call**. `Locale.setDefault(...)` mutates global default state, which can affect other threads/requests. Java also distinguishes defaults for `Locale.Category.DISPLAY` and `Locale.Category.FORMAT`.

## 10. Common mistakes and how to avoid them

1. **Confusing `language` with `region`**: `en` is English, `US` is the United States; `en-US` contains both.
2. **Ignoring script**: `sr-Latn-RS` and `sr-Cyrl-RS` differ in script, even though language and region match.
3. **Inferring script from region**: `zh-TW` does not declare `Hant`; use `zh-Hant-TW` when the requirement must be explicit.
4. **Using region instead of time zone**: region does not uniquely identify a `ZoneId`; handle time zones using the date/time API.
5. **Confusing variant with extension**: `getVariant()` does not return `nu-thai`; use `getUnicodeLocaleType("nu")`.
6. **Using `en_US` as a BCP 47 tag**: the standard tag is `en-US`; legacy Java may use `_` in `toString()`.
7. **Treating `forLanguageTag` as a validator**: the method may accept part of a string; use `Builder` and check the supported list when strictness is required.
8. **Treating `Builder` as a semantic validator**: it only verifies valid syntactic form, not that codes are registered or have translation resources.
9. **Mutating the default locale per request**: easily affects other threads; pass the locale explicitly.
10. **Using display names as IDs**: `getDisplayName(...)` can change depending on display language/JDK data; use the `Locale` object and language tag as identifiers.

## 11. Knowledge check

- `sr-Latn-RS` vs `sr-Cyrl-RS`: differs in **script**.
- `en-US` vs `en-GB`: differs in **region**.
- `zh-Hant-TW`: `language=zh`, `script=Hant`, `region=TW`, `variant=""`.
- `en-US-POSIX`: has a **variant**; `en-US-u-nu-thai`: has a **Unicode extension**, empty variant.
- Read region with `getCountry()`; store/pass BCP 47 with `toLanguageTag()`.
- Only declare components you actually know; when a feature must distinguish script/region/variant, declare them explicitly and test the fallback mechanism.

**References:** [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html) · [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
