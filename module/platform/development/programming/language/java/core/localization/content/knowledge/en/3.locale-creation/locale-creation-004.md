# Distinguishing Syntax Validation from Language or Region Verification in Java

## 1. The Problem: Is a Locale-Like String Actually Usable?

When a program receives a locale from configuration, a user profile, or an HTTP header (such as `vi-VN`, `en-US`, or `zh-Hant-TW`), there are at least **three independent questions** to answer:

1. **Syntactically valid (well-formed):** Does the string follow BCP 47 language tag structure?
2. **Registered/recognized codes (registered/valid):** Do components such as language, script, and region belong to the applicable code set or registry? Are they combined according to registry constraints?
3. **Supported in the usage context:** Do the runtime, libraries, resource bundles, and product itself have sufficient data, translations, or policies to serve that locale?

These three conditions are not equivalent. **A `Locale` successfully created by Java does not prove the language and region exist; a real code does not prove the application supports the corresponding interface.**

For example, `xx-YY` has the structure of a language tag (two letters for language, two letters for region). On Java 17, `Locale.Builder` accepts the syntax and can create a `Locale`, yet Java's documentation cites this as an example of **unregistered subtags** in the IANA Language Subtag Registry. Nor does a Vietnamese/English application have any reason to automatically provide translations for it.

## 2. Reading the Syntax of a Locale According to BCP 47

Language tags usually use hyphens `-` to separate components:

| Example | Breakdown | Meaning |
| --- | --- | --- |
| `vi` | language = `vi` | Vietnamese, no region specified |
| `vi-VN` | language = `vi`, region = `VN` | Vietnamese tied to Vietnam region |
| `en-US` | language = `en`, region = `US` | English (US) |
| `sr-Latn-RS` | language = `sr`, script = `Latn`, region = `RS` | Serbian, Latin script, Serbia |
| `zh-Hant-TW` | language = `zh`, script = `Hant`, region = `TW` | Chinese, Traditional script, Taiwan |
| `en-US-u-nu-latn` | plus Unicode extension `u` | Includes instruction for Latin numbering system |

For fields accepted by `Locale.Builder.setLanguage`, `setScript`, and `setRegion`, Java 17 describes the basic well-formed shapes:

- **Language:** from 2 to 8 ASCII letters; merely having the right letter count does not mean a registered language code exists.
- **Script:** exactly 4 ASCII letters (e.g., `Latn`, `Cyrl`).
- **Region:** 2 ASCII letters or 3 digits (e.g., `VN`, `US`, `419`); a region is not necessarily an independent country, since numeric UN M.49 region codes also exist.
- **Variants, extensions, and grandfathered tags:** have specific rules under BCP 47. You cannot accurately validate all language tags with a simple regular expression that only accepts `xx-YY`.

The `_` in `en_US` often appears in Java's legacy representation (for example `Locale.toString()`); the standard BCP 47 input for `setLanguageTag` is `en-US`. Java normalizes casing: language becomes lowercase, script becomes title case, and region becomes uppercase. Thus `vi-vn` is normalized to `vi-VN`; differing letter case is **not** an invalid code.

**Do not equate region with language:** `en-VN` can indicate a user wants English in a Vietnam context. Likewise, never infer locale from nationality, time zone, or currency without explicit business rules.

## 3. What Can Java Validate?

### 3.1. `Locale.Builder`: Checks Structure, Does Not Verify the Registry

`Locale.Builder` provides commonly used APIs:

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();

System.out.println(locale.toLanguageTag()); // sr-Latn-RS
~~~

The snippet above is **illustrative only** when used inside a Java method that has imported `java.util.Locale`. Builder checks fields and throws `IllformedLocaleException` when syntax is invalid; it **does not** query IANA to confirm a value is registered, makes no network calls, and does not guarantee translations exist.

To validate an input BCP 47 string, prefer:

~~~java
Locale locale = new Locale.Builder()
        .setLanguageTag("vi-VN")
        .build();
~~~

There is no need to split parts manually if the input is a complete language tag. Use `getLanguage()`, `getScript()`, `getCountry()`, and `toLanguageTag()` to access the normalized result.

### 3.2. `Locale.forLanguageTag`: Lenient Decoding, Can Hide Errors

Unlike Builder, `Locale.forLanguageTag(text)` **drops the first syntactically ill-formed subtag and all following subtags**, instead of throwing an error. For example:

~~~java
Locale lenient = Locale.forLanguageTag("en-US-@");
System.out.println(lenient.toLanguageTag()); // en-US
~~~

Consequently, merely checking `Locale.forLanguageTag(input) != null` has **zero value for input validation**. With data sent by users or external systems, silently dropping part of a code can mask configuration errors. If the goal is to reject syntactically invalid input, use `new Locale.Builder().setLanguageTag(input).build()` and catch `IllformedLocaleException`.

### 3.3. Constructors Are Not Validators Either

Java 17 constructors such as `new Locale("en", "US")` exist for historical compatibility; they do not enforce the same syntax checks as Builder. Do not treat a successful constructor call as proof that a country/language code exists.

### 3.4. Being Able to Create a `Locale` Does Not Mean Formatting or Translation Is Supported

`Locale.getAvailableLocales()` returns the union of locales installed by the Java environment and `LocaleServiceProvider` implementations; it is neither the complete IANA registry nor the list of locales the application commits to supporting. Even if a locale is absent from this array, a formatting service may still perform fallback or use other data; conversely, a locale being present in the array does not prove the application has a resource bundle for it.

In practical design, separate:
- **Structure:** Builder.
- **Registered codes:** IANA Language Subtag Registry or an up-to-date standard catalog chosen by the system.
- **Runtime services and data:** each specific API/provider/formatter.
- **Product languages:** the supported locale list and actually deployed bundles.

## 4. Complete Java 17 Example: Three Different Validation Outcomes

The standalone example below shows that `xx-YY` passes the syntax step, yet is absent from the two queried 2-letter ISO catalogs, and is still rejected by application policy. Put the code in **`LocaleValidationDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.Set;

public class LocaleValidationDemo {
    private static final Set<String> SUPPORTED =
            Set.of("en-US", "vi-VN");

    // Step 1: check structure; step 2: check product list.
    static Locale requireSupportedLocale(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Missing locale");
        }

        final Locale parsed;
        try {
            parsed = new Locale.Builder()
                    .setLanguageTag(input)
                    .build();
        } catch (IllformedLocaleException e) {
            throw new IllegalArgumentException("Malformed locale tag", e);
        }

        // Compare normalized BCP 47 tag, do not compare raw input.
        String canonical = parsed.toLanguageTag();
        if (!SUPPORTED.contains(canonical)) {
            throw new IllegalArgumentException("Unsupported locale: " + canonical);
        }
        return parsed;
    }

    public static void main(String[] args) {
        System.out.println("normalized: " +
                requireSupportedLocale("vi-vn").toLanguageTag());

        Locale syntacticallyValid = new Locale.Builder()
                .setLanguageTag("xx-YY").build();
        System.out.println("well-formed: " +
                syntacticallyValid.toLanguageTag());

        boolean isoLanguage = Arrays.asList(Locale.getISOLanguages())
                .contains("xx");
        boolean isoRegion = Arrays.asList(Locale.getISOCountries())
                .contains("YY");
        System.out.println("ISO language xx: " + isoLanguage);
        System.out.println("ISO region YY: " + isoRegion);

        System.out.println("lenient: " +
                Locale.forLanguageTag("en-US-@").toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en-US-@").build();
            System.out.println("strict: accepted");
        } catch (IllformedLocaleException e) {
            System.out.println("strict: rejected");
        }

        try {
            requireSupportedLocale("xx-YY");
            System.out.println("application: accepted");
        } catch (IllegalArgumentException e) {
            System.out.println("application: rejected");
        }
    }
}
~~~

Compile and run (Java 17 or later):

~~~bash
javac -encoding UTF-8 LocaleValidationDemo.java
java LocaleValidationDemo
~~~

Output:

~~~text
normalized: vi-VN
well-formed: xx-YY
ISO language xx: false
ISO region YY: false
lenient: en-US
strict: rejected
application: rejected
~~~

**Explanation:**

- `vi-vn` is structurally valid and canonicalized to `vi-VN`, so it passes the application list.
- `xx-YY` is accepted by Builder because it is well-formed, even though `xx` is not in the two-letter ISO 639 language code list and `YY` is not in the two-letter ISO 3166 country code list returned by Java.
- `Locale.forLanguageTag("en-US-@")` silently accepts the `en-US` part; Builder rejects the `@` subtag.
- Application policy only allows `en-US` and `vi-VN`, so even a **syntactically valid** locale like `xx-YY` is rejected.

Here `SUPPORTED` is an intentional **product** choice for illustration. Do not derive the supported list from `Locale.getAvailableLocales()`, and do not use `ISO` catalogs to replace this policy.

## 5. ISO and IANA Codes: Different Scopes

Useful APIs in Java 17:

| API | Usable Check/Data | Limitations |
| --- | --- | --- |
| `Locale.getISOLanguages()` | Array of **two-letter** ISO 639 language codes | Does not contain all valid language subtags: many languages use three characters or other forms; includes both old and new codes in some cases |
| `Locale.getISOCountries()` | Array of **two-letter** ISO 3166 country codes | Does not contain numeric UN M.49 region codes and does not fully represent all BCP 47 region subtags |
| `Locale.getISOCountries(Locale.IsoCountryCode.PART1_ALPHA2)` | Set of ISO 3166-1 alpha-2 country codes | Also not a list of every region code that can appear in a language tag |
| `Locale.getAvailableLocales()` | List of locales that the runtime/providers report as installed | Not an ISO/IANA standard set, not a promise that the application has translations |
| `Locale.Builder.setLanguageTag(...)` | Parses and enforces BCP 47 **syntax** | Does not automatically check whether subtags are registered |

If business logic needs to verify **real language or region codes**, specify the exact standard:

- For **BCP 47 language tags**, use the **IANA Language Subtag Registry**, noting `language`, `extlang`, `script`, `region`, and `variant` types, grandfathered tags, and deprecation/preferred-value fields. The standard is not just the two ISO arrays.
- For systems that only accept **two-letter ISO 639-1 language codes**, you can check that specific catalog, but explicitly document the limitation so valid BCP 47 tags are not mistakenly rejected.
- For systems that only accept **ISO 3166-1 alpha-2 countries**, use the country catalog; do not treat `419` (a numeric region code) as invalid BCP 47 syntax just because it is absent from `getISOCountries()`.
- Legacy codes, name changes, or replacement rules may exist. You must define a policy for deprecated codes, preferred replacements, and registry data versions; do not assume data is frozen forever.

It is not sufficient to use a regex alone, such as `[a-z]{2}-[A-Z]{2}`, and conclude "valid code": that regex both accepts unregistered `xx-YY` and rejects `zh-Hant-TW` or `en`, which are structurally valid tags.

**Technical note:** `Locale.getISO3Language()`/`getISO3Country()` convert code forms in some cases and can throw `MissingResourceException`; they are not verification services for every subtag or entire BCP 47 tags.

## 6. Normalization, Registry Verification, and Application Policy Should Run in Order

A reliable input pipeline:

~~~text
Input string (config / user / request)
       |
       v
Check null / empty / length limit / data type
       |
       v
Parse strictly with Locale.Builder.setLanguageTag
       |-- invalid syntax --> reject or return explainable error
       v
Normalized Locale: toLanguageTag()
       |
       +--> [When required by business logic] check IANA / ISO
       |       and legacy code, script, geographic region policy
       |
       v
Check against product-supported locale list
       |-- unsupported --> reject or choose documented fallback
       v
Select resource bundle, formatter, locale for each request
       |
       v
Localized output / structured data
~~~

If input comes from a client and is not among supported locales, there are two reasonable policies depending on the product contract:

1. **Explicit rejection** for APIs/configuration requiring an exact locale: `invalid_locale` error for bad syntax, `unsupported_locale` error when syntax is valid but unsupported by the product.
2. **Fallback negotiation** for display needs: e.g., requesting `vi-VN` when the UI only has `vi`, using a documented priority order. This is the responsibility of an adapter/presenter, must be observable and tested, and must not alter business data.

Do not use `Locale.setDefault(...)` as a way to validate or switch locales per request: that is JVM-wide default state and can affect other requests in a multithreaded application. Pass the chosen `Locale` directly to formatting classes or obtain it from a safely managed request context.

## 7. What Does It Mean to "Support" a Locale?

To verify that a product truly supports a locale, test the exact components in use:

- **Application translations:** Is there a `ResourceBundle` or message catalog for the required locale? Are all keys present? `ResourceBundle.getBundle` can fall back; a successful call **does not prove** the desired translation exists.
- **Numbers, currency, dates/times:** Do `NumberFormat`, `DateTimeFormatter`, and providers have the needed locale data? If specific data is missing, fallback may occur.
- **Regional context:** a locale does not determine time zone, nor automatically supply exchange rates or tax rules. `ZoneId` and `Currency` are separate pieces of information.
- **Product language policy:** Does the product serve all regions/scripts of a language or only certain variants? Does it accept `en` and then pick `en-US` or `en-GB`, or require an exact match?
- **Final display:** Does the user actually see appropriate translations and formatting, or are they seeing all-English fallback labels?

For example: an application has `messages_en.properties` but lacks `messages_en_AU.properties`. A request for `en-AU` may be resolved by `ResourceBundle` via fallback; whether to label the product as “supports English (Australia)” belongs to translation quality policy, not Builder's output.

## 8. Common Mistakes

| Mistake | Why It Is Wrong | How to Handle |
| --- | --- | --- |
| `new Locale.Builder().setLanguage("zz")` runs, so `zz` is a recognized language | Builder checks shape, does not query the registry | If needed, check registry/business rules separately |
| `Locale.forLanguageTag(value)` did not throw, so input must be valid | This API ignores bad subtags and everything after them | Use strict Builder for input that must be validated |
| `getISOLanguages()` lacks three-letter codes, so the code is wrong | The API only lists two-letter codes | Use a standard covering the code types you need to accept |
| `getISOCountries()` lacks `419`, so the tag is invalid | Numeric UN M.49 regions do not belong to the alpha-2 array | Evaluate properly against BCP 47 / UN M.49 |
| Locale is in `getAvailableLocales()`, meaning the app has translations | The array reflects runtime and providers, not product bundles | Test bundles, UI labels, and fallback |
| Using `Locale.toString()` as BCP 47 standard input | `_` notation may not be a language tag | Use `toLanguageTag()` |
| Using locale code to infer time zone or currency | One language spans multiple regions and user preferences | Pass `ZoneId` / `Currency` independently |
| Blindly replacing `_` with `-` and trusting all strings are valid | Legacy variants and extensions have complex rules | Need explicit migration policy, re-validated with Builder |
| Comparing raw input with `"vi-VN"` | `vi-vn` has different casing yet is valid | Compare normalized tags |

Do not merely check whether `getDisplayLanguage()` returns a readable name: the display string may fall back to a code or name from runtime data and is not proof of registry validity.

## 9. Essential Test Cases to Have

- **Valid syntax, familiar codes:** `vi-VN`, `en-US`, `sr-Latn-RS`; verify components are read properly.
- **Valid syntax but unregistered codes:** `xx-YY`; Builder lets it pass, while the registry step (if required) or product allowlist can reject it.
- **Invalid syntax:** `en-US-@`, `en_ US`, or tags containing unusual characters; Builder must reject.
- **Different letter casing:** `vi-vn` becomes `vi-VN`; do not report an error merely for casing differences.
- **Language-only tags:** `en`, `vi`; decide support by policy, do not implicitly append `US`/`VN`.
- **Tags with script/region/extension:** `zh-Hant-TW`, `en-US-u-nu-latn`; do not use a two-part-only regex.
- **Empty, null, too long, or outside allowlist:** return a clear error, do not accept just because parsing could yield `Locale.ROOT`.
- **Missing translations or missing keys:** verify fallback behavior, logs/metrics, or errors per product requirements.

Distinguish tests for **syntax** (based on the Builder API contract), tests for **code catalogs** (based on a registry snapshot/version), and tests for **product support** (based on deployed resources and configuration). When testing formatted output, JDK/CLDR locale data can vary across Java versions: focus on desired behavior or pin the provider version when comparing verbatim text.

## 10. Key Takeaways to Apply

**No single Java function automatically guarantees syntax, code existence, and product support all at once.**

- Use `Locale.Builder.setLanguageTag` when **strict structural validation** of a language tag is needed.
- Use an **appropriate registry/standard policy** if the problem requires verifying that language/region subtags are registered.
- Use an **allowlist together with resource/formatter tests** to confirm the UI or service **actually supports** that locale.
- Choose rejection/fallback behavior intentionally and keep business values independent of localized text.

**References:**

- Java SE 17, `java.util.Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `Locale.Builder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html
- IANA Language Subtag Registry: https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry
- IETF BCP 47 (RFC 5646): https://www.rfc-editor.org/rfc/rfc5646