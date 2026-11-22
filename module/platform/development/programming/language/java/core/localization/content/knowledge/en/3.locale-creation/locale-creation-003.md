# Locale.Builder and Syntax Validation in Java

## Objectives

When you need to create a `Locale` from parts such as language, script, region, and extensions, `java.util.Locale.Builder` lets you declare each component explicitly and detect **syntax errors** right at build time. This lesson focuses on how to use Builder properly, how to read BCP 47 language tags, the meaning and limits of validation, and how to handle untrusted input.

After this lesson, you will be able to:

- Create a `Locale` using `Locale.Builder` from individual components or from a language tag.
- Understand `setLanguage`, `setScript`, `setRegion`, `setVariant`, and the extension methods.
- Explain when `IllformedLocaleException` is thrown, how to handle the error, and why `Locale.forLanguageTag` behaves differently.
- Distinguish **syntactic validity** from **meaningful language codes**, **JDK-supported locales**, and **application-allowed locales**.
- Write intentional input validation before using a locale in a multilingual system.

## 1. Builder's Role in the Locale Model

`Locale` is an identifier describing the language/region conventions an operation wants to use. It does not contain translated content, date formatting data, or time zone rules. `Locale` is an **immutable** object: once created, its components cannot be modified directly.

`Locale.Builder` is a **mutable** tool for preparing those components:

```text
Language / Script / Region / Variant / Extensions
                    |
                    v
          Locale.Builder (mutable)
                    |
                 build()
                    v
             Locale (immutable)
```

You can call multiple setters on the same Builder, then call `build()` to obtain a `Locale`. Modifying the Builder and calling `build()` again produces a new `Locale`; the previously created object retains its original value.

Builder also helps detect **syntactically** invalid components as soon as a setter is called or when setting an entire language tag. The `IllformedLocaleException` exception indicates that a string or component does not follow Locale/BCP 47 syntax rules. Keep in mind: Builder checks the **representation form**, not whether the application has translations or whether the JDK has full formatting rules for that locale.

## 2. Validated Components

Common language tags use BCP 47 syntax with hyphens `-`, such as `vi-VN`, `en-US`, `sr-Latn-RS`, and `zh-Hant-TW`.

| Component | Meaning | Common Form Accepted by Builder | Example |
| --- | --- | --- | --- |
| Language | Language code | 2–8 ASCII letters | `vi`, `en`, `sr` |
| Script | Writing system | Exactly 4 ASCII letters | `Latn`, `Cyrl`, `Hant` |
| Region | Country/region | 2 ASCII letters or 3 digits | `VN`, `US`, `419` |
| Variant | Variant | Subtag of 5–8 alphanumeric characters or 4 characters starting with a digit; multiple subtags allowed | `POSIX` |
| Extensions | Additional information | According to BCP 47 extension structure, consisting of a key and suitable subtags | `u-nu-latn` |

These are **string format rules**, not a promise that every validly formatted code is registered, translated, or supported by all providers. For example, a language code made of letters may pass the format check yet not belong to the list of locales implemented by the product.

Builder normalizes the casing of components in the resulting identifier. `toLanguageTag()` is the right way to obtain a language tag when saving configuration or communicating; you should not use the underscore-based `toString()` string as BCP 47 input.

### Key Methods

| Method | Effect |
| --- | --- |
| `setLanguage("vi")` | Sets the language code |
| `setScript("Latn")` | Sets the script |
| `setRegion("VN")` | Sets the region |
| `setVariant("POSIX")` | Sets the variant |
| `setExtension('u', "nu-latn")` | Sets an extension by singleton and value |
| `setUnicodeLocaleKeyword("nu", "latn")` | Sets a Unicode locale keyword, here the numbering system |
| `setUnicodeLocaleAttribute("...")` | Adds a valid Unicode locale attribute |
| `setLanguageTag("sr-Latn-RS")` | Reads and sets the entire Builder from a language tag |
| `setLocale(existingLocale)` | Sets the Builder from an existing `Locale` |
| `clearExtensions()` | Clears extensions while keeping basic components |
| `clear()` | Resets the Builder state to empty |
| `build()` | Creates an immutable `Locale` |

`setLanguageTag(...)` and `setLocale(...)` are operations that **reset the Builder's contents to match the input**; do not treat them as appending a single field onto old state. Individual setters for language/script/region are more suitable when you want to change one part at a time.

Setters validate and normalize their input according to the corresponding rules. For example, script `"Latin"` has five letters and is therefore invalid for `setScript`; region `"USA"` has three letters and is invalid for `setRegion`, whereas a three-**digit** region code like `"419"` is syntactically valid.

## 3. Standalone Runnable Java 17+ Example

The following example combines building explicit components, a Unicode locale keyword, and validating a language tag. It also demonstrates the difference between strict Builder validation and flexible parsing with `Locale.forLanguageTag`.

Save as `LocaleBuilderDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleBuilderDemo {

    private static void check(String tag) {
        try {
            Locale locale = new Locale.Builder()
                    .setLanguageTag(tag)
                    .build();

            System.out.println(tag + " => " + locale.toLanguageTag());
        } catch (IllformedLocaleException ex) {
            System.out.println(tag + " => INVALID");
        }
    }

    public static void main(String[] args) {
        Locale serbianLatin = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .build();

        Locale englishLatinDigits = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("nu", "latn")
                .build();

        System.out.println(serbianLatin.toLanguageTag());
        System.out.println(englishLatinDigits.toLanguageTag());

        check("vi-VN");
        check("en-US-@");

        Locale flexible = Locale.forLanguageTag("en-US-@");
        System.out.println(flexible.toLanguageTag());
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 LocaleBuilderDemo.java
java LocaleBuilderDemo
```

Stdout:

```text
sr-Latn-RS
en-US-u-nu-latn
vi-VN => vi-VN
en-US-@ => INVALID
en-US
```

Analysis:

1. `setLanguage("sr")`, `setScript("Latn")`, and `setRegion("RS")` combine into `sr-Latn-RS`. The fields remain separate inside `Locale`; the language part does not include `-RS`.
2. `setUnicodeLocaleKeyword("nu", "latn")` creates the Unicode extension `u-nu-latn`. It **describes a preference** to use the Latin numbering system; the specific formatting API decides whether to apply this keyword.
3. `setLanguageTag("vi-VN")` is accepted by Builder because it is syntactically valid.
4. The `@` character is invalid in the language tag `en-US-@`, so `setLanguageTag` throws `IllformedLocaleException` and the `catch` branch prints `INVALID`.
5. `Locale.forLanguageTag("en-US-@")` does not throw a similar exception; instead it parses the valid prefix and returns a locale with tag `en-US`. Therefore, **never use `forLanguageTag` alone as a strict syntax validator**.

The two object-creation approaches address different needs: Builder is appropriate when you need to report bad input; `forLanguageTag` is appropriate when flexible parsing is acceptable. They do not share the same input-error contract.

## 4. When Does IllformedLocaleException Occur?

`IllformedLocaleException` is an unchecked exception that **does not need to be declared in `throws`**. It can occur immediately inside a setter when a value does not match the expected format, rather than waiting until `build()`.

Examples of syntactic errors:

```java
new Locale.Builder().setLanguage("v");
new Locale.Builder().setScript("Latin");
new Locale.Builder().setRegion("USA");
new Locale.Builder().setLanguageTag("en_US");
```

These are **error-illustrating expressions**, not a standalone runnable program. Each line placed independently will throw `IllformedLocaleException` for the supplied value:

- `"v"` is a one-letter language code.
- `"Latin"` has five letters whereas a script code consists of four.
- `"USA"` has three letters whereas allowed region codes are two letters or three digits.
- `"en_US"` uses the underscore of the legacy representation rather than the `-` in a BCP 47 language tag.

When building components from strings coming from external sources, wrap both the setter chain and `build()` in `try/catch`. For example:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class ValidateLocale {
    public static void main(String[] args) {
        String suppliedTag = "en_US";

        try {
            Locale result = new Locale.Builder()
                    .setLanguageTag(suppliedTag)
                    .build();
            System.out.println("ACCEPTED: " + result.toLanguageTag());
        } catch (IllformedLocaleException ex) {
            System.out.println("INVALID TAG");
        }
    }
}
```

Save as `ValidateLocale.java`, then run `javac ValidateLocale.java` and `java ValidateLocale`. Stdout is:

```text
INVALID TAG
```

`IllformedLocaleException#getErrorIndex()` can help indicate the error position in an invalid input. However, **do not rely on fixed numeric positions** in error messages across all setters and all environments; keep user-facing messages at the application level, such as “invalid language tag”.

You should not catch a broad `Exception` and silently use the default locale: that approach hides data errors. Handle syntax errors explicitly and apply fallback clearly according to product policy.

## 5. Builder Compared to Locale.forLanguageTag

Both approaches below can construct a `Locale` from a valid BCP 47 tag:

```java
Locale strict = new Locale.Builder()
        .setLanguageTag("zh-Hant-TW")
        .build();

Locale flexible = Locale.forLanguageTag("zh-Hant-TW");
```

This is an illustrative snippet inside a method. Both objects represent `zh-Hant-TW`. The notable difference lies in **syntactically invalid input**:

| Situation | `new Locale.Builder().setLanguageTag(tag).build()` | `Locale.forLanguageTag(tag)` |
| --- | --- | --- |
| Valid tag `vi-VN` | Accepts, creates locale | Accepts, creates locale |
| Tag with invalid trailing part `en-US-@` | Throws `IllformedLocaleException` | May keep the valid prefix `en-US` |
| Application does not yet support the language | Can still create locale if syntax is valid | Can still create locale if syntax is valid |
| Need to reject syntactically invalid strings | Suitable | Insufficient if used alone |

Key takeaway: **no exception** from `forLanguageTag` **does not mean the original input was valid**. Calling `locale.toLanguageTag()` and seeing a clean-looking result also does not prove the data was validated, because invalid parts of the input may have been stripped.

In some cases, `setLanguageTag` may normalize or handle language tags with special rules defined in BCP 47; thus syntax validation does not necessarily mean `input.equals(locale.toLanguageTag())`. Do not require the two strings to be identical as a universal validation rule: differences in casing, canonical forms, and canonicalization are valid.

## 6. Building from Components Instead of Manual String Concatenation

Suppose a user chooses language `zh`, script `Hant`, and region `TW` in three separate fields. Do not concatenate strings and try to infer backward when an error occurs; Builder lets you validate exactly which part is wrong:

```java
Locale locale = new Locale.Builder()
        .setLanguage(languageCode)
        .setScript(scriptCode)
        .setRegion(regionCode)
        .build();
```

This is an **illustrative snippet inside a method** with three existing input variables: `languageCode`, `scriptCode`, and `regionCode`. You can catch `IllformedLocaleException` and report the corresponding input field, or validate each field individually to return more accurate errors.

Fields may be left empty when not applicable. For example, locale `en` only needs a language; do not automatically fill in `US` if the user has not chosen a region. Conversely, when a specific API requires regional conventions, the application must resolve the region according to its own policy instead of implicitly assuming every English speaker is in the United States.

### Builder Is Stateful; the Built Result Is Immutable

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US");

Locale first = builder.build();
builder.setRegion("GB");
Locale second = builder.build();

System.out.println(first.toLanguageTag());   // en-US
System.out.println(second.toLanguageTag());  // en-GB
```

This illustrative snippet sits inside a method; the two comments `// en-US` and `// en-GB` are the corresponding outputs. Modifying the Builder does not mutate `first`. Because Builder is a mutable object, avoid sharing the same Builder across multiple threads to construct locales concurrently. The created `Locale` can be shared safely because it is immutable.

If reusing a Builder, understand the state-clearing methods:

- `clearExtensions()` removes only extensions and Unicode attributes/keywords; language, script, region, and variant remain.
- `clear()` resets the Builder back to an empty state.
- `setLanguageTag(...)` sets all components according to the new tag; do not assume it only replaces one part.

If reuse is unnecessary, the simple approach is to instantiate a new Builder for each identifier.

## 7. Validating Extensions Properly

In addition to language/script/region/variant, BCP 47 supports extensions. A Unicode locale extension typically starts with `u`, for example:

```text
en-US-u-nu-latn
        |  |  |
        u  nu latn
        |  |  +-- numbering system type
        |  +----- Unicode keyword "numbering system"
        +-------- Unicode locale extension
```

With Builder, setting a keyword using the dedicated API helps avoid syntax errors from manual concatenation:

```java
Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(locale.toLanguageTag()); // en-US-u-nu-latn
System.out.println(locale.getUnicodeLocaleType("nu")); // latn
```

This is an illustrative snippet inside a method. `setUnicodeLocaleKeyword` requires a well-formed key and type. Builder may throw `IllformedLocaleException` when the structure is invalid. If a user selects multiple Unicode preferences, the keywords are represented in the `u` extension of the same locale. Canonical ordering when exporting the tag is handled by Java; there is no need to concatenate strings manually.

Do not equate a **syntactically valid extension** with **an API actually supporting the extension**. For instance, requesting the `nu-latn` numbering system does not automatically change every calculation or every format; each formatter/provider decides how to handle it. Keywords carry convention preferences, not multilingual processing features already implemented for every library.

Arbitrary extensions via `setExtension` require their own valid structure. When a dedicated API like `setUnicodeLocaleKeyword` exists, prefer that API because it expresses intent more clearly.

## 8. Valid Syntax Differs from Usability

Suppose `new Locale.Builder().setLanguageTag(tag).build()` succeeds. The only valid conclusion at this step is that **the tag has a syntactic form accepted by Builder**.

There are at least four distinct layers of checking:

1. **Syntax (well-formed):** the parts and assembly of the language tag conform to BCP 47. Builder can check this layer.
2. **Code meaning/registration:** whether the codes are truly recognized languages, scripts, regions, or variants appropriate for the problem. Builder is not a database verifying all registered codes and every meaningful combination.
3. **Data supported by the JDK/API:** whether suitable formatting, collation, display-name data, etc. exist. Results depend on the provider and data version. APIs may fall back.
4. **Application policy:** whether the product has translated resources, custom formatting rules, and allows selecting that language. This is an application decision.

For example, if a product only has `vi` and `en-US`, the tag `de-DE` may be completely syntactically valid yet **not belong to the set of supported UI languages**. You must reject it or resolve it to an explicitly documented option, rather than implicitly assuming `build()` succeeding means German translations already exist.

In addition, `Locale` does not determine a time zone (`ZoneId`), does not verify which country a user is physically located in, and does not decide the currency unit of a transaction. Builder validation cannot be used to validate those pieces of information.

## 9. Pipeline for Validating an External Language Tag

Suppose an HTTP API receives the configuration property `"locale": "vi-VN"`. A safe, testable pipeline:

1. **Define the input contract.** If the API requires a single BCP 47 language tag, reject empty values, overly long strings, or multi-value strings right at the request layer per product rules. Decide explicitly whether leading/trailing whitespace is accepted; avoid silently “fixing” strings.
2. **Validate syntax with Builder.** Call `setLanguageTag(value)` inside `try/catch (IllformedLocaleException)`; return an input error if syntax is invalid.
3. **Apply the supported list.** Match the parsed locale against the set of locales the application provides, e.g., `vi` and `en-US`. If a fallback mechanism exists, document clearly which cases map to the closest locale.
4. **Keep both request and result when needed.** `requestedLocale` may differ from `resolvedLocale` if the product uses fallback. Do not overwrite the original request and lose track of the cause.
5. **Pass the locale to the APIs that need it.** For example `ResourceBundle`, `NumberFormat`, `DateTimeFormatter`, or `Collator`. Do not call `Locale.setDefault` per request in a multi-user application.

You can write a syntax-checking function with a clear contract:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public final class LocaleInput {
    private LocaleInput() {}

    public static Locale parseStrict(String rawTag) {
        if (rawTag == null || rawTag.isBlank()) {
            throw new IllegalArgumentException("Locale tag is required");
        }
        if (rawTag.length() > 128) {
            throw new IllegalArgumentException("Locale tag is too long");
        }

        try {
            return new Locale.Builder()
                    .setLanguageTag(rawTag)
                    .build();
        } catch (IllformedLocaleException ex) {
            throw new IllegalArgumentException("Malformed locale tag", ex);
        }
    }
}
```

This is a utility class that can compile standalone into `LocaleInput.java`, though it has no `main` method to run directly. The 128-character limit here is only an **example of an application policy**, not a standard limit of BCP 47 or `Locale.Builder`. The function only returns a `Locale` after checking syntax and minimal input rules; **it does not yet check an allowlist, translation resources, or JDK support level**. The caller must perform that step if needed.

Note that `rawTag.isBlank()` rejects strings consisting only of whitespace, but does not automatically trim leading/trailing whitespace from other strings. If the input contract requires an exact tag, this behavior is consistent: the string `" vi-VN "` will be rejected by the parser rather than silently fixed. If trimming is desired, document it as an explicit policy and test inputs both before and after normalization.

### Do Not Use setLanguageTag to Parse Accept-Language Directly

An HTTP `Accept-Language` header may contain a priority list such as `vi-VN,vi;q=0.9,en-US;q=0.7`. This is **not a single language tag**. `Locale.Builder.setLanguageTag(header)` is not a parser for headers with `q` weights.

Java provides `Locale.LanguageRange.parse(...)` and the `Locale.lookup(...)`, `Locale.filter(...)` methods to support locale negotiation from a priority list. After the negotiation step, the application still needs to use its actually released locale list and product fallback rules.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Wrong | Appropriate Approach |
| --- | --- | --- |
| Calling `new Locale.Builder().setLanguage("en-US")` | `setLanguage` expects only a language code, not an entire tag | Use `setLanguageTag("en-US")` or `setLanguage("en").setRegion("US")` |
| Passing `en_US` into `setLanguageTag` | Underscore is not a BCP 47 delimiter | Use `en-US` if the source data truly represents English/United States |
| Using `forLanguageTag` for strict validation | The API may strip invalid parts without throwing an error | Use Builder or a validator with an appropriate contract |
| Thinking `build()` succeeding means translations exist | Builder only checks component syntax | Check the product's supported locale/resource list |
| Thinking `getAvailableLocales()` is the application's allowlist | JDK/provider locales and product-supported languages differ | Maintain the application's supported set independently |
| Using `toString()` as a BCP 47 tag | Legacy representation may use underscores | Use `toLanguageTag()` |
| Sharing one Builder across requests | Builder has mutable state and is not designed for concurrent sharing | Create a local Builder per operation |
| Building an entire tag via arbitrary string concatenation | Easy to misorder/misformat parts | Use corresponding setters or `setLanguageTag` for an existing tag |
| Basing core business logic on `getErrorIndex()` | Not every error is suitable for relying on fixed indices | Use the exception as a rejection signal and provide a clear message |
| Changing `Locale.setDefault` per user | The JVM default is shared state | Pass `Locale` explicitly via request context |
| Using locale to infer time zone or order currency | Those are independent concepts | Obtain `ZoneId`/`Currency` from configuration or business data |

## 11. Self-Check Exercises

**Scenario A.** You receive `"sr-Latn-RS"`. Create the locale in two ways: `new Locale.Builder().setLanguageTag(...)` and the individual setters `setLanguage`/`setScript`/`setRegion`. Verify that `toLanguageTag()` returns `sr-Latn-RS` in both cases.

**Scenario B.** A client sends `"en_US"`. Try Builder and catch `IllformedLocaleException`. If the product accepts BCP 47 tags, respond with a syntax error instead of silently treating `_` as `-`. If migrating a documented legacy format, build an explicit conversion layer and test it separately.

**Scenario C.** Builder accepts `"de-DE"` while the application only has `"vi"` and `"en-US"` resources. This is a **language support** error, not a syntax error; the decision to reject or fall back must reside in the application policy layer.

**Scenario D.** Create `en-US-u-nu-latn` using `setUnicodeLocaleKeyword("nu", "latn")`, then read it back with `getUnicodeLocaleType("nu")`. The result is `latn`. Explain why that value does not automatically force every Java API to switch numbering systems.

## 12. Key Takeaways

`Locale.Builder` is the right tool when you need to **construct a Locale from explicit components or strictly validate BCP 47 syntax**. Setters check value formats and may throw `IllformedLocaleException` immediately while setting data; `build()` produces an immutable `Locale`. Conversely, `Locale.forLanguageTag` parses flexibly and may retain the valid prefix of an invalid tag, so it is insufficient for strict input validation.

Syntax validation is always only the **first step**: a well-formed locale says nothing for certain about registered codes, provider-supported data, available translations, or product-allowed choices. Separating these validation layers helps multilingual applications return understandable errors, apply consistent fallback, and avoid conflating cultural preferences with actual data.