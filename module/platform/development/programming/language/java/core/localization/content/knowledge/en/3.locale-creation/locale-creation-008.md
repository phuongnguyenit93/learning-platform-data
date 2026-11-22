# Locale.equals(), stripExtensions(), and the Limitations of toString() for Storage

## 1. Objective and Context

`java.util.Locale` describes language, script, territory/region, variant, and extensions that can influence localization behavior. When working with multiple `Locale` instances, three easily confused operations are:

- **`equals(Object)`:** checks whether two `Locale` objects have the exact same full locale identity.
- **`stripExtensions()`:** creates a locale representation **with no extensions**, while preserving language, script, country, and variant.
- **`toString()`:** outputs Java's traditional text representation, convenient for quick inspection, but **not a BCP 47 exchange/storage format**.

For storing or exchanging language tags with other systems, use **`toLanguageTag()`** and restore via `Locale.forLanguageTag(...)` or `Locale.Builder.setLanguageTag(...)`, with appropriate input validation.

Examples:

```text
en-US                   language=en, region=US
en-US-u-nu-thai         same language/region but has Unicode extension nu=thai
sr-Latn-RS              language=sr, script=Latn, region=RS
sr-Cyrl-RS              language=sr, script=Cyrl, region=RS
```

Two locales with the same language and region are **not necessarily equal** if their script, variant, or extensions differ.

## 2. What Does `equals(Object)` Compare?

`Locale.equals(Object)` returns `true` if the other object is also a `Locale` and has the same identifying components: **language, script, country/region, variant, and extensions**. This is a comparison of the entire locale identity, not a "similar" match or a measure of language compatibility.

| First Locale | Second Locale | `equals` | Reason |
| --- | --- | --- | --- |
| `en-US` | `en-US` | `true` | Equivalent components |
| `en-US` | `en-GB` | `false` | Different region |
| `sr-Latn-RS` | `sr-Cyrl-RS` | `false` | Different script |
| `en-US` | `en-US-u-nu-thai` | `false` | Different extensions |
| `en-US-u-nu-thai` | `en-US-u-ca-buddhist` | `false` | Same language/region, different extensions |
| `EN-us-u-NU-thai` | `en-US-u-nu-thai` | `true` after parsing | Tags are case-insensitive; `Locale` normalizes to valid form |

**Note:** the table applies to objects created via `Locale.forLanguageTag(...)`, and does not claim raw string comparison can replace `equals`. For example, `"EN-us".equals("en-US")` in Java returns `false` because `String.equals` is case-sensitive, whereas the `Locale` objects created from those two tags can be equal.

Because `equals` checks full identity, `Locale` can be used as a key in `HashMap`/`HashSet`; `hashCode()` follows the same contract. However, if the problem requires grouping by language or region, **choose a dedicated grouping criterion** instead of expecting `equals` to ignore irrelevant components.

Example distinguishing three questions:

- "**Is it the exact same locale?**" → `a.equals(b)`.
- "**Is it the same language?**" → compare `a.getLanguage()` with `b.getLanguage()` (understanding that the same language does not guarantee the same script/content).
- "**Is it the same identity if extensions are ignored?**" → `a.stripExtensions().equals(b.stripExtensions())`, **only** when business logic permits ignoring extensions.

## 3. What Does `stripExtensions()` Remove?

BCP 47 supports extensions, for example:

- `en-US-u-nu-thai`: extension `u`, Unicode key `nu` with value `thai` (Thai numbering system).
- `en-US-u-ca-buddhist`: extension `u`, key `ca` with value `buddhist` (Buddhist calendar preference).
- `ja-JP-u-ca-japanese`: extension requesting the Japanese calendar system.

`stripExtensions()` removes **all extensions** (including Unicode extensions and other extension groups). It **does not** remove language, script, region, or variant.

```text
en-US-u-nu-thai       --stripExtensions()--> en-US
zh-Hant-TW-u-nu-hanidec --stripExtensions()--> zh-Hant-TW
sr-Latn-RS            --stripExtensions()--> sr-Latn-RS
```

The input is a `Locale`, and the output is also a `Locale`. `Locale` is immutable, so the call **does not mutate the original object**. If there are no extensions, Java may return the current instance itself; **do not** write business logic that relies on comparing two references with `==`. Use `equals` to check value equality.

Important: `stripExtensions()` does not mean "completely generalize" or "reduce to the base language locale". For example, `sr-Latn-RS` and `sr-RS` still differ after stripping because the `Latn` script remains present. To generalize by language, you must define a specific rule, possibly using `getLanguage()`, while accepting the loss of other distinctions.

### When Should It Be Used?

In a system where **resource lookup keys only care about language/script/region/variant**, stripping extensions before lookup can be an intentional policy. For example, translated copy may not distinguish between Thai digits and Latin digits, whereas the number-formatting component still needs to distinguish them.

### When Should It Not Be Used?

Do not strip a locale right before formatting calendars, numbers, or currencies if the relevant extension is a configuration the user actually requested. Removing `u-nu-thai` or `u-ca-buddhist` can discard the user's numbering/calendar preference; the actual impact depends on which extensions the API/provider supports.

Keep in mind the difference between two criteria: **equal after stripping extensions** and **safely interchangeable everywhere**. The first outcome does not guarantee the second.

## 4. Java 17+ Example: `equals` and `stripExtensions`

Create the file `LocaleEqualityDemo.java`:

```java
import java.util.Locale;

public class LocaleEqualityDemo {
    public static void main(String[] args) {
        Locale base = Locale.forLanguageTag("en-US");
        Locale thaiDigits = Locale.forLanguageTag("en-US-u-nu-thai");
        Locale buddhistCalendar =
                Locale.forLanguageTag("en-US-u-ca-buddhist");

        System.out.println(base.equals(thaiDigits));
        System.out.println(thaiDigits.stripExtensions().equals(base));
        System.out.println(thaiDigits.getUnicodeLocaleType("nu"));
        System.out.println(
                thaiDigits.stripExtensions().getUnicodeLocaleType("nu"));
        System.out.println(thaiDigits.equals(buddhistCalendar));
        System.out.println(thaiDigits.equals(
                Locale.forLanguageTag("EN-us-u-NU-thai")));

        Locale latin = Locale.forLanguageTag("sr-Latn-RS");
        Locale cyrillic = Locale.forLanguageTag("sr-Cyrl-RS");

        System.out.println(latin.equals(cyrillic));
        System.out.println(latin.stripExtensions().equals(
                Locale.forLanguageTag("sr-RS")));
        System.out.println(latin.toString());
        System.out.println(latin.toLanguageTag());
    }
}
```

Run:

```bash
javac LocaleEqualityDemo.java
java LocaleEqualityDemo
```

Exact output:

```text
false
true
thai
null
false
true
false
false
sr_RS_#Latn
sr-Latn-RS
```

Step-by-step explanation:

1. `base` differs from `thaiDigits` because `thaiDigits` has the `u-nu-thai` extension.
2. After stripping extensions, `thaiDigits` becomes `en-US` and equals `base`.
3. `getUnicodeLocaleType("nu")` returns `thai` before stripping; after stripping it returns `null` because the `nu` keyword is gone.
4. Two locales with different extensions (`nu` versus `ca`) are not equal.
5. Parsing `EN-us-u-NU-thai` yields the same identity as `en-US-u-nu-thai`.
6. Latin and Cyrillic scripts differ; stripping does not remove script.
7. For the same `latin` object, `toString()` returns `sr_RS_#Latn` in Java's representation, while `toLanguageTag()` returns `sr-Latn-RS` per BCP 47.

**Verification note:** the `null` printed to stdout comes from `System.out.println(String)` receiving a `null` result, not a literal `"null"` string stored as a locale keyword.

## 5. Why Is `toString()` Unsuitable as a Storage Format?

`Locale.toString()` outputs a string according to Java's historical rules: typically separating language, country, and variant with underscores `_`, and script/extensions representations may include `#`. A few examples:

| `Locale` Object | `toString()` | `toLanguageTag()` |
| --- | --- | --- |
| `Locale.US` | `en_US` | `en-US` |
| `Locale.forLanguageTag("sr-Latn-RS")` | `sr_RS_#Latn` | `sr-Latn-RS` |
| `Locale.forLanguageTag("zh-Hant-TW-u-nu-hanidec")` | `zh_TW_#Hant_u-nu-hanidec` | `zh-Hant-TW-u-nu-hanidec` |

Strings like `en_US` or `sr_RS_#Latn` are custom representations according to the `toString` API; they are **not** BCP 47 language tags. Passing them directly into `Locale.forLanguageTag` may be treated as invalid syntax and lose information, because that parser expects hyphenated tags like `en-US`.

Three practical limitations:

1. **Not a standard exchange contract:** if an external API expects BCP 47, strings from `toString` do not comply.
2. **No universal inverse parsing pair:** Java does not provide a general contract that "passing any `toString` output into `forLanguageTag` restores the locale intact". `forLanguageTag` is designed for BCP 47, not for reading legacy strings.
3. **Error-prone to split or replace delimiters manually:** script, variant, and extensions make legacy strings more complex than `language_COUNTRY`. Do not use `replace('_', '-')` as a general-purpose parser or converter.

`toString()` remains useful for debugging/logging if readers recognize it as a Java representation. However, a string written to a database, JSON, URL, message queue, or sent to another system should have an **explicit schema**: if the field is a BCP 47 language tag, write it using `toLanguageTag()`.

### Demonstrating the Risk of Data Loss

Create `LocaleStorageDemo.java`:

```java
import java.util.Locale;

public class LocaleStorageDemo {
    public static void main(String[] args) {
        Locale original =
                Locale.forLanguageTag("zh-Hant-TW-u-nu-hanidec");

        String legacy = original.toString();
        String tag = original.toLanguageTag();

        System.out.println(legacy);
        System.out.println(tag);
        System.out.println(
                Locale.forLanguageTag(legacy).toLanguageTag());

        Locale restored = new Locale.Builder()
                .setLanguageTag(tag)
                .build();
        System.out.println(original.equals(restored));
        System.out.println(original.stripExtensions().toLanguageTag());
        System.out.println(
                original.equals(original.stripExtensions()));
    }
}
```

Run:

```bash
javac LocaleStorageDemo.java
java LocaleStorageDemo
```

Output:

```text
zh_TW_#Hant_u-nu-hanidec
zh-Hant-TW-u-nu-hanidec
und
true
zh-Hant-TW
false
```

`und` stands for "undetermined" language when exporting a tag; here it appears because `forLanguageTag` does not accept the legacy underscore string as a valid BCP 47 tag. The `true` result proves that the `toLanguageTag()` string in this example is restored by `Builder.setLanguageTag()` while preserving script, region, and Unicode extension. After `stripExtensions()`, only `zh-Hant-TW` remains, so it is no longer equal to `original`.

**Scope of guarantee:** the example starts with a valid BCP 47 `Locale`. Legacy `Locale` objects constructed with old APIs using variants that do not fit BCP 47 grammar may not round-trip completely through `toLanguageTag`/`forLanguageTag`. When designing a new schema, prefer BCP 47-valid locales; when migrating legacy data, inspect each case instead of assuming all strings convert losslessly.

## 6. Practical Workflow for Storing and Restoring Locales

Use clearly named fields such as `localeTag` or `languageTag` with example values like `"vi-VN"` or `"en-US-u-nu-thai"`. Store the tag after normalizing with `toLanguageTag()`; restore using Builder if you need to **reject syntactically invalid input**.

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleInputDemo {
    static Locale parseTag(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Missing language tag");
        }
        try {
            return new Locale.Builder()
                    .setLanguageTag(input.trim())
                    .build();
        } catch (IllformedLocaleException ex) {
            throw new IllegalArgumentException(
                    "Invalid language tag", ex);
        }
    }

    public static void main(String[] args) {
        Locale locale = parseTag("EN-us-u-nu-thai");
        String stored = locale.toLanguageTag();
        Locale loaded = parseTag(stored);

        System.out.println(stored);
        System.out.println(locale.equals(loaded));

        try {
            parseTag("en_US");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac LocaleInputDemo.java
java LocaleInputDemo
```

```text
en-US-u-nu-thai
true
Invalid language tag
```

In this flow, `Builder.setLanguageTag` validates **tag syntax**. It does not guarantee every language code belongs to an allowed business set, nor does it guarantee language resources or extensions are supported by the runtime. The application can additionally check a `supportedLocales` list when needed.

**Distinguishing parsers:**

- `Locale.forLanguageTag(tag)` is **lenient**: upon hitting an invalid subtag, it may drop the faulty subtag and everything after it without throwing an error.
- `Locale.Builder.setLanguageTag(tag)` is **strict** on malformed syntax: it throws `IllformedLocaleException`.
- Neither is a complete verifier of locale existence in all registries or of application support.

In production code, use `stripExtensions()` only to build a **separate** key for an intentional case. If you want to preserve the user's calendar/digit choices when saving, do not strip before writing `localeTag`.

## 7. Choosing a Comparison Method Based on Business Logic

| Question | API Pattern | What Must Be Accepted |
| --- | --- | --- |
| Do two locale choices match completely? | `a.equals(b)` | Any difference in script/variant/extension is distinguished |
| Do two locales share the same core parts when all extensions are removed? | `a.stripExtensions().equals(b.stripExtensions())` | Extensions have been intentionally ignored |
| Do two locales have the same language? | `a.getLanguage().equals(b.getLanguage())` | Region, script, variant, and extensions are not examined |
| Should number/calendar settings stay in formatter cache keys? | Keep the full `Locale` as key | Extensions can affect formatting output |
| Need to send a locale as a string to an API? | `locale.toLanguageTag()` | String is BCP 47, not `toString()` |
| Need to quickly inspect the object in logs? | `locale.toString()` | Use only as diagnostic info |

For example, a translation-name cache by language may intentionally ignore extensions; conversely, a formatter cache for `en-US` and `en-US-u-nu-thai` should consider keeping extensions in the key because omitting them risks reusing the wrong numbering configuration. Not every provider may act on `nu`, yet the key decision must follow the program's formatting contract.

If you want a fallback chain such as "`en-US-u-nu-thai` → `en-US` → `en`", build and document your application's fallback policy or use a resource-management API with corresponding fallback support. **`stripExtensions()` does not perform that entire fallback chain by itself**: it only returns an object without extensions.

## 8. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| `Locale.forLanguageTag("en_US")` | `_` is not a BCP 47 subtag separator; may yield `und` | Use `en-US` in BCP 47 data |
| `a.equals(b)` when only comparing language | `equals` checks all components | Compare `getLanguage()` as required |
| Calling `stripExtensions()` thinking it removes script/region | The method only removes extensions | Handle individual components via getters |
| Stripping extensions before saving all locales | Loses information such as `nu`, `ca` | Save the full tag with `toLanguageTag()` |
| Saving `toString()` and re-parsing with `forLanguageTag` | Not a uniform format | Store BCP 47 `toLanguageTag()` |
| Blindly converting `_` to `-` on all legacy strings | Variant/script/extensions may be misinterpreted | Migrate data according to a known schema |
| Using `==` to compare two `Locale` instances | `==` checks reference identity | Use `equals` |
| Treating `Locale` equality as a translation selection rule | Equality does not mean "same resources" | Define an explicit resource/fallback policy |

## 9. Self-Check

1. Is `en-US` equal to `en-US-u-nu-thai` according to `equals`? **No**, because one side has the `nu` extension.
2. What tag does `en-US-u-nu-thai` produce after `stripExtensions()`? **`en-US`**.
3. Do `sr-Latn-RS` and `sr-Cyrl-RS` become equal after stripping? **No**, their scripts differ and are not removed.
4. When storing a locale in JSON for another system to read, choose `toString` or `toLanguageTag`? **`toLanguageTag`**, storing the field under a BCP 47 contract.
5. Does `Locale.forLanguageTag(locale.toString())` reliably restore every locale? **No**. `toString()` has its own syntax, such as `sr_RS_#Latn`.
6. When a locale uses the Unicode extension `u-ca-buddhist`, should extensions be stripped before caching every formatter? **Not by default**; only drop them if business logic proves the extension does not affect the output.

## References

- [Java SE 21 — java.util.Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `equals`, `hashCode`, `stripExtensions`, `toString`, `toLanguageTag`, `forLanguageTag`.
- [Java SE 21 — Locale.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.Builder.html): `setLanguageTag`, `build`.
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): BCP 47 syntax and semantics.