# BCP 47 Language Tags and Separators in Java

## 1. Objectives

After this lesson, you can:

- Read and write language tags according to BCP 47, such as `vi-VN`, `en-US`, and `zh-Hant-TW`.
- Distinguish the BCP 47 hyphen `-` from the underscore `_` in legacy `Locale` formatting and resource bundle filenames.
- Convert, normalize, and validate language tag syntax using `java.util.Locale`.
- Properly handle locale data coming from URLs, configuration, and HTTP, and avoid confusing valid syntax with application-supported locales.

This lesson belongs to the **Locale Model** topic of Java Core. `Locale` describes the preferred language and regional conventions; it is not itself a time zone, translation, or formatting dataset.

## 2. What does BCP 47 represent?

**BCP 47** is the standard for language identification tags (primarily specified in RFC 5646). A tag consists of multiple **subtags** joined by an **ASCII hyphen `-` (hyphen-minus)**, in a prescribed order.

| Example | How to read |
| --- | --- |
| `vi` | Vietnamese, no region specified yet |
| `vi-VN` | Vietnamese in Vietnam |
| `en-US` | English in the United States |
| `en-GB` | English in the United Kingdom |
| `zh-Hans-CN` | Chinese, Simplified script, China region |
| `zh-Hant-TW` | Chinese, Traditional script, Taiwan region |
| `sr-Latn-RS` | Serbian, Latin script, Serbia region |
| `es-419` | Spanish, region 419 (Latin America and the Caribbean) |
| `th-TH-u-nu-thai` | Thai in Thailand, requesting the Thai numbering system via a Unicode extension |

For common tags, an easy-to-remember structure is:

```text
language[-Script][-REGION][-variant...][-extension...][-x-privateuse...]
```

The main components:

1. **Language**: typically a two- or three-letter ISO 639 code, such as `vi`, `en`, `ja`; Java's language field also supports longer alphabetic codes according to the corresponding rules.
2. **Script**: four letters (ISO 15924), such as `Latn`, `Cyrl`, `Hans`, `Hant`. Script refers to the writing system; it is **not** a country.
3. **Region**: two letters (usually an ISO 3166-1 code) or three digits (UN M.49), such as `VN`, `US`, `419`.
4. **Variant**: a language variant with specific subtag rules (usually 5–8 alphanumeric characters, or four characters starting with a digit), such as `sl-rozaj-biske`.
5. **Extension**: a group starting with a single character, such as `-u-` in `en-US-u-ca-gregory-nu-latn`; `ca` refers to calendar, `nu` refers to numbering system.
6. **Private use**: starts with `-x-`; system-specific information requiring agreement between sender and receiver to carry meaning.

This is a **summary pattern for common cases**, not the full RFC 5646 grammar (the standard also includes extlang and certain grandfathered tags). Do not build your own BCP 47 parser solely from that summary pattern.

**Casing convention:** `language` is lowercase, `Script` is Title Case, and `REGION` is uppercase; for example `zh-Hant-TW`. BCP 47 subtags are essentially case-insensitive, so `EN-us` and `en-US` identify the same tag; normalized casing helps store and compare consistently.

## 3. `-` and `_`: three contexts to keep separate

| Context | Example values | Rule |
| --- | --- | --- |
| BCP 47 language tag (APIs, configuration, HTTP) | `vi-VN`, `zh-Hant-TW` | Subtags separated by **`-`** |
| Java's `Locale.toString()` (historical representation) | `vi_VN`, `en_US`; may include script/variant/extension parts | Typically uses **`_`**; **not** a BCP 47 string |
| `ResourceBundle` filename suffix | `messages_vi_VN.properties` | The **`_`** is a Java file naming convention, not a tag sent over HTTP |

Do not pass `en_US` directly to APIs expecting BCP 47. Specifically, `Locale.forLanguageTag("en_US")` does **not** automatically convert `_` to `-`: the `_` makes the initial segment invalid, which can result in an empty locale (`toLanguageTag()` returns `und`). Conversely, do not use `Locale.toString()` as exchange data when a partner expects a BCP 47 tag; the legacy string has additional rules for script, variant, and extension.

When you need to produce BCP 47 from a Java object, use **`locale.toLanguageTag()`**. When you need to create an object from BCP 47, use **`Locale.forLanguageTag(tag)`** or `Locale.Builder.setLanguageTag(tag)`.

For legacy data in the form `language_REGION`, only convert when **the input schema is clearly known**: split out the separately defined fields (`language`, `region`, `script`, etc.) and pass them into `Locale.Builder`; do not use `replace('_', '-')` as a general-purpose normalizer for arbitrary `Locale.toString()` strings.

## 4. Java 17+: Key APIs

| API | Purpose and behavior to remember |
| --- | --- |
| `Locale.forLanguageTag(String)` | Reads a BCP 47 tag **leniently**: when encountering a malformed subtag, it discards that subtag and all following subtags; does not throw `IllformedLocaleException` in this case |
| `new Locale.Builder().setLanguageTag(String).build()` | Reads **strictly**: a malformed tag throws `IllformedLocaleException`; suitable when validating user input |
| `locale.toLanguageTag()` | Outputs a BCP 47 tag using Java's normalization rules; this is the API for exchanging tags |
| `locale.getLanguage()`, `getScript()`, `getCountry()`, `getVariant()` | Retrieves object components instead of slicing strings by position |
| `locale.getUnicodeLocaleType("nu")` | Reads the corresponding Unicode extension value (e.g. `thai`) |
| `locale.toString()` | Traditional Java representation; use for diagnostics/legacy, not as a replacement for `toLanguageTag()` |

Valid syntax is **not enough** to guarantee that the language/region has formatting data, translations, or product support. `Locale.Builder` validates syntactic form, **not by looking up all codes in the IANA Language Subtag Registry**. To restrict to the set of locales the application supports, check against the application's list as well.

## 5. Runnable example: reading, outputting, and detecting separator errors

Create the file `LanguageTagsDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LanguageTagsDemo {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-vn");
        Locale zh = Locale.forLanguageTag("zh-Hant-TW");
        Locale th = Locale.forLanguageTag("th-TH-u-nu-thai");

        System.out.println(vi.toLanguageTag());
        System.out.println(vi.getLanguage());
        System.out.println(vi.getCountry());
        System.out.println(zh.toLanguageTag());
        System.out.println(zh.getScript());
        System.out.println(th.getUnicodeLocaleType("nu"));

        System.out.println(Locale.US.toString());
        System.out.println(Locale.US.toLanguageTag());

        // '_' is not valid in a BCP 47 tag.
        System.out.println(Locale.forLanguageTag("en_US").toLanguageTag());

        // The lenient parser keeps the valid prefix before the invalid subtag.
        System.out.println(Locale.forLanguageTag("en-US-invalid_thing").toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en_US").build();
            System.out.println("valid tag");
        } catch (IllformedLocaleException ex) {
            System.out.println("invalid tag");
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac LanguageTagsDemo.java
java LanguageTagsDemo
```

Output:

```text
vi-VN
vi
VN
zh-Hant-TW
Hant
thai
en_US
en-US
und
en-US
invalid tag
```

Explanation:

- `vi-vn` normalizes to `vi-VN`; the getters retrieve `vi` and `VN`.
- `zh-Hant-TW` parses the script `Hant`; `-u-nu-thai` contains the Unicode locale keyword `nu` with value `thai`.
- The same `Locale.US` has `toString() = en_US` but `toLanguageTag() = en-US`. These are **two different formats**.
- With `en_US`, `forLanguageTag` does not fix the separator: the result is equivalent to an undetermined-language locale, outputting `und`.
- With `en-US-invalid_thing`, the parser keeps `en-US` and drops the invalid tail. `Builder` instead detects the error; the code catches the exception instead of letting input be silently altered.

## 6. Building tags from fields instead of manual string concatenation

When data comes as separate fields, `Locale.Builder` helps set the right components and the right separator:

```java
import java.util.Locale;

public class LocalePartsDemo {
    public static void main(String[] args) {
        Locale locale = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .build();

        System.out.println(locale.toLanguageTag());
        System.out.println(locale.getLanguage());
        System.out.println(locale.getScript());
        System.out.println(locale.getCountry());
    }
}
```

```bash
javac LocalePartsDemo.java
java LocalePartsDemo
```

```text
sr-Latn-RS
sr
Latn
RS
```

One way to apply this when converting legacy data with a clear schema: receive two fields `language = "en"` and `region = "US"`, call `setLanguage("en").setRegion("US")`, then use `toLanguageTag()` to output `en-US`. No need to manually concatenate hyphens and guess script/region positions.

## 7. Using tags in practice: accepting input and checking support

Suppose an application only publishes three locales: `vi-VN`, `en-US`, and `ja-JP`. First validate syntax with the builder, then **compare against the supported list**; all blank, malformed, or unsupported cases fall back to the default `vi-VN`.

Create the file `SupportedLocaleDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.Set;

public class SupportedLocaleDemo {
    private static final String DEFAULT_TAG = "vi-VN";
    private static final Set<String> SUPPORTED =
            Set.of("vi-VN", "en-US", "ja-JP");

    static Locale resolve(String input) {
        if (input == null || input.isBlank()) {
            return Locale.forLanguageTag(DEFAULT_TAG);
        }
        try {
            Locale candidate = new Locale.Builder()
                    .setLanguageTag(input.trim())
                    .build();
            return SUPPORTED.contains(candidate.toLanguageTag())
                    ? candidate
                    : Locale.forLanguageTag(DEFAULT_TAG);
        } catch (IllformedLocaleException ex) {
            return Locale.forLanguageTag(DEFAULT_TAG);
        }
    }

    public static void main(String[] args) {
        System.out.println(resolve("vi-VN").toLanguageTag());
        System.out.println(resolve("EN-us").toLanguageTag());
        System.out.println(resolve("en_US").toLanguageTag());
        System.out.println(resolve("fr-FR").toLanguageTag());
    }
}
```

```bash
javac SupportedLocaleDemo.java
java SupportedLocaleDemo
```

```text
vi-VN
en-US
vi-VN
vi-VN
```

Here `EN-us` is normalized to `en-US`. `en_US` has invalid BCP 47 syntax; `fr-FR` has valid syntax but is not yet supported by the application. Both cases fall back to the default per the **example policy**. Another application might return HTTP 400, ask the user to choose again, or apply language-based fallback rules; that is a product decision, not mandatory BCP 47 behavior.

In HTTP, tag values such as `vi-VN` may appear in `Content-Language` or as part of an `Accept-Language` list. **The entire string** `Accept-Language: vi-VN,vi;q=0.9,en;q=0.7` is a weighted list, **not a single BCP 47 tag**: you must parse the header/list before feeding individual tags into `Locale`. Java provides `Locale.LanguageRange.parse(...)` to work with preference lists; do not pass that entire string to `Locale.forLanguageTag(...)`.

## 8. Notes on storage, comparison, and fallback

- Store exchange identifiers using `toLanguageTag()` after validating input. If supporting legacy formats, convert at the data ingestion boundary and document the compatibility schema clearly.
- String comparisons should use normalized forms; `en`, `en-US`, and `en-GB` are different levels of specificity. Do not assume they share the same data or translations.
- When matching content by language, use the application's fallback mechanism or `ResourceBundle`; filenames like `messages_vi_VN.properties` use `_` per bundle naming rules, while `Locale` APIs still accept `vi-VN`.
- Unicode extensions such as `u-ca-buddhist` or `u-nu-thai` express a request for calendar/numbering system. Whether a specific formatter applies the extension depends on the API, provider, and locale data; do not assume every library supports it.
- Language tags **do not carry a time zone**. Do not infer `Asia/Ho_Chi_Minh` solely from `vi-VN`; time handling requires an independent `ZoneId`.
- `und` is the "undetermined" subtag (undetermined language) when exporting BCP 47; when parsed into `Locale`, `getLanguage()` may be an empty string. It does not mean English or Vietnamese by default.

## 9. Common mistakes and fixes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Sending `en_US` to an API expecting BCP 47 | Malformed tag; lenient parsers may yield `und` | Send `en-US` |
| Using `locale.toString()` to store/send tags | Produces legacy `_` notation and possibly special segments | Use `locale.toLanguageTag()` |
| Thinking `forLanguageTag` always reports errors | May silently drop invalid trailing subtags | Use `Locale.Builder.setLanguageTag` when malformed tags must be rejected |
| Thinking builder guarantees the language name exists/is supported | Only checks well-formedness, not registry or UI data | Check against the application's supported locale list |
| Building tags via fixed-position string concatenation | Mixes up script/region/variant/extension | Use `Locale.Builder` and getters |
| Replacing all `_` with `-` on every legacy string | Can misinterpret variant/extension | Convert only according to a clearly known schema |
| Treating country as determining language or time zone | Selects wrong content/time zone | Separate language, region, and `ZoneId` |

## 10. Self-check

1. What parts does `zh-Hant-TW` have? **Answer:** language `zh`, script `Hant`, region `TW`.
2. Which string is valid when passed to `Locale.forLanguageTag` as a BCP 47 tag: `pt-BR` or `pt_BR`? **Answer:** `pt-BR`; the subtag separator is `-`.
3. Why not rely solely on `Locale.forLanguageTag` to validate input? **Answer:** it may silently discard invalid subtags and everything after them, losing information; builder is stricter.
4. How do `Locale.US.toString()` and `Locale.US.toLanguageTag()` differ? **Answer:** they are `en_US` and `en-US`, respectively.
5. Does `ja-JP-u-ca-japanese` mean every Java library must format using the Japanese calendar? **Answer:** no; the extension expresses a request, while support belongs to the API/provider.

## References

- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646)
- [Java SE 21 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.Builder.html)
