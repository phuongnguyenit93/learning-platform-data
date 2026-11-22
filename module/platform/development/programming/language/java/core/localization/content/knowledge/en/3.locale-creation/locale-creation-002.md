# Locale.forLanguageTag() and toLanguageTag(): BCP 47 Language Conversion in Java

In Java, `Locale` describes the language/region context of data and UI. When receiving a locale from configuration, a URL, a user profile, or another protocol, applications typically represent it using a **BCP 47 language tag**, such as `vi-VN`, `en-US`, or `zh-Hans-CN`. Two directly related methods are:

- `Locale.forLanguageTag(String languageTag)`: parses a BCP 47 language tag into a `Locale` object.
- `locale.toLanguageTag()`: outputs a `Locale` as a BCP 47 language tag string normalized according to Java rules.

It is necessary to understand both conversion directions, because **the output tag string does not necessarily match the input string character-for-character**. In addition, `forLanguageTag` parses leniently when encountering malformed components; applications requiring strict input validation must choose another approach.

## 1. What Components Does a BCP 47 Tag Represent?

BCP 47 is a convention for identifying languages and related variants, using a hyphen `-` between components (subtags). In Java, the commonly encountered parts are:

| Component | Example | Meaning |
| --- | --- | --- |
| Language | `vi`, `en`, `zh`, `sr` | Language |
| Script | `Latn`, `Cyrl`, `Hans`, `Hant` | Writing system |
| Region | `VN`, `US`, `CN`, `419` | Territory/region |
| Variant | `rozaj` | Language variant |
| Extension | `u-ca-buddhist`, `u-nu-thai` | Additional options, e.g., calendar system, numbering system |
| Private use | `x-acme` | Custom extension defined by system convention |

A common tag has the approximate structure:

~~~text
language[-Script][-REGION][-variant...][-extension...][-x-private...]
~~~

This is a **quick-reading model**, not the complete BCP 47 grammar; some components have specific rules for length, order, combinations, and repeatability. Java accepts tags with valid syntax according to the rules supported by the API.

Examples:

- `vi-VN`: Vietnamese in Vietnam.
- `en-US`: English in the United States.
- `zh-Hans-CN`: Chinese, Simplified script, China region.
- `sr-Latn-RS`: Serbian, Latin script, Serbia region.
- `th-TH-u-ca-buddhist-nu-thai`: Thai in Thailand, with Unicode locale options for calendar (`ca`) and numbering system (`nu`).

**Do not confuse:** region `VN` is not time zone `Asia/Ho_Chi_Minh`; script `Latn` is not charset UTF-8; `u-ca-...` information also does not automatically force every formatting API to enforce a particular calendar system. Each library uses the tag parts appropriate to its capabilities.

## 2. From String to Locale with forLanguageTag()

Signature:

~~~java
public static Locale forLanguageTag(String languageTag)
~~~

Typical usage:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale serbianLatin = Locale.forLanguageTag("sr-Latn-RS");

String language = vietnamese.getLanguage(); // "vi"
String country = vietnamese.getCountry();   // "VN"
String script = serbianLatin.getScript();    // "Latn"
~~~

The examples above are code snippets placed inside a program that has imported `java.util.Locale`. `forLanguageTag` processes **a single** BCP 47 tag, not a list of tags or an entire HTTP `Accept-Language` header value.

### Extracting Parts of a Locale

After parsing, you can read:

- `getLanguage()`: language code; e.g., `"vi"`.
- `getScript()`: script code; e.g., `"Hans"`.
- `getCountry()`: region code, whose historical method name is `Country`; e.g., `"CN"`.
- `getVariant()`: variant part, if any.
- `getExtension(char key)`: contents of an extension; e.g., `'u'`.
- `getUnicodeLocaleType(String key)`: value of a Unicode locale key, e.g., `"buddhist"` for `"ca"`.
- `getUnicodeLocaleKeys()`: set of configured Unicode keys.

These methods read identification metadata; they do not automatically translate the language of a sentence. To display a language or region name in another language, you can use `getDisplayLanguage(displayLocale)` and `getDisplayCountry(displayLocale)`; to translate content, you need separate localization resources or services.

### Case-Insensitive Parsing

According to `Locale` rules, the language component is normally normalized to lowercase, script to title case, region to uppercase, and extensions to lowercase.

~~~java
Locale locale = Locale.forLanguageTag("ZH-hans-cn");
System.out.println(locale.getLanguage()); // zh
System.out.println(locale.getScript());   // Hans
System.out.println(locale.getCountry());  // CN
~~~

This typical case produces the same locale object semantically as the tag `zh-Hans-CN`.

## 3. From Locale Back to String with toLanguageTag()

Signature:

~~~java
public String toLanguageTag()
~~~

Example:

~~~java
Locale locale = Locale.forLanguageTag("vi-vn");
String tag = locale.toLanguageTag();  // "vi-VN"
~~~

Use `toLanguageTag()` when you need to store or exchange a BCP 47 tag. **Do not substitute `toString()`**: `Locale.toString()` preserves the legacy representation for Java compatibility, typically with underscores, such as `vi_VN`. Meanwhile, the BCP 47 tag is `vi-VN`.

| Expression | Value | When to use? |
| --- | --- | --- |
| `Locale.forLanguageTag("vi-VN")` | `Locale` object | Reading BCP 47 config or input |
| `locale.toLanguageTag()` | `"vi-VN"` | Storing/sending standard BCP 47 tags |
| `locale.toString()` with `vi-VN` | `"vi_VN"` | Legacy display/debugging, not to be treated as BCP 47 |
| `Locale.ROOT.toLanguageTag()` | `"und"` | “Undetermined” tag when there is no language |

`und` is the BCP 47 code indicating an undetermined language. `Locale.ROOT` has empty language, script, and region fields, yet `toLanguageTag()` returns `"und"`; this is not an exception.

### Syntax Normalization and Extension Ordering

Consider input with inconsistent letter casing and Unicode extension keys in a different order:

~~~java
Locale locale = Locale.forLanguageTag("th-TH-u-nu-thai-ca-buddhist");
String tag = locale.toLanguageTag();
// "th-TH-u-ca-buddhist-nu-thai"
~~~

The two keys `ca` and `nu` are placed in canonical order in Java's output. If compared against the original string using `equals()`, they differ, even though the locale's meaning is preserved in this conversion.

## 4. What Is a Round Trip?

A **round trip** typically starts from a tag string, creates a `Locale`, outputs a string, and parses it again:

~~~java
String input = "ZH-hans-cn";
Locale first = Locale.forLanguageTag(input);
String normalizedTag = first.toLanguageTag();
Locale second = Locale.forLanguageTag(normalizedTag);

boolean sameLocale = first.equals(second); // true for this example
~~~

Distinguish two kinds of “preservation”:

1. **Preserving exact text representation:** `input.equals(normalizedTag)` may be `false`, because letter casing, extension order, or aliases have been normalized.
2. **Preserving validly representable locale state:** for ordinary valid tags, `first.equals(second)` is a reasonable check after a round trip.

You should not claim that a round trip always preserves all data in every case. In particular, a `Locale` created with old constructors using a language, region, or variant that is **not valid BCP 47 syntax** may contain values that cannot be exported intact. `toLanguageTag()` will attempt to produce a valid tag and may drop or transform the representation of incompatible parts. In cases where you need to store the **verbatim user input** for auditing, store the raw input separately alongside the normalized tag.

### Aliases and Compatibility

Java has compatibility rules for certain legacy language codes and special tags. For example, the codes `iw`, `ji`, and `in` are converted to their newer counterparts `he`, `yi`, and `id` when parsed. Thus `toLanguageTag()` is an **API-normalized representation**, not a raw string concatenation operation.

When an application uses locales as cache keys, normalize input into a `Locale` and standardize the key policy. If two different spellings are supposed to be equivalent, avoid using unnormalized user strings as two separate keys.

## 5. Easy to Miss: forLanguageTag() Is Lenient with Malformed Tags

`Locale.forLanguageTag()` is not a strict validator. Under the Java 17 contract, when encountering a **syntactically ill-formed** subtag, the first invalid subtag and all subsequent subtags are ignored; the API does not throw `IllformedLocaleException` for this situation alone.

Verifiable example:

~~~java
Locale parsed = Locale.forLanguageTag("en-US-@bad");
System.out.println(parsed.toLanguageTag()); // en-US
~~~

The `@bad` part is invalid and therefore dropped. Consequence: an application can **accidentally accept part of an invalid input** if it only checks whether the method returns a `Locale`.

Another error is using underscores:

~~~java
Locale parsed = Locale.forLanguageTag("en_US");
System.out.println(parsed.toLanguageTag()); // und on Java 17
~~~

`"en_US"` is a common representation from `toString()` or legacy config, **not a valid BCP 47 tag**. Therefore, do not rely on `forLanguageTag()` to automatically convert underscores into hyphens. If legacy configs must be supported, define an explicit conversion step and test it, instead of silently replacing every `_` character without analyzing structure.

Furthermore, `forLanguageTag(null)` throws `NullPointerException`. An empty string or `und` input should not be implicitly treated as a real user locale; have a separate default/error response policy when the problem requires knowing the language.

## 6. When Strict Validation Is Needed: Locale.Builder.setLanguageTag()

`Locale.Builder` provides stronger **syntax** checking. Unlike `forLanguageTag`, `setLanguageTag` throws `IllformedLocaleException` for syntactically invalid tags (for instance, a subtag containing `@`).

~~~java
try {
    Locale locale = new Locale.Builder()
            .setLanguageTag("en-US-@bad")
            .build();
} catch (IllformedLocaleException ex) {
    // Reject syntactically invalid tag.
}
~~~

The snippet above requires `import java.util.Locale;` and `import java.util.IllformedLocaleException;`. In a real application, handle empty input first; `Locale.Builder.setLanguageTag(null)` or an empty string clears the Builder's state rather than automatically signaling missing input.

**Important limitation:** `Builder` mainly checks **well-formed syntax**; it does not definitively confirm whether every language/region code is registered or supported by your system. A syntactically valid tag may still lack translations, formatting data, or business meaning. To select an actually served language, you must also check the application's supported locale list and apply fallback rules.

A reliable input pipeline:

1. Check that the string exists, is not empty, and meets an appropriate length limit.
2. Use `Locale.Builder().setLanguageTag(input).build()` if syntax errors must be rejected.
3. Obtain `locale.toLanguageTag()` as the normalized tag for internal use or storage.
4. Check against the list of actually supported languages/regions; if absent, apply the documented fallback.
5. When original input evidence must be kept, store the raw input in another field.

If the input source is generated by a trusted system and already validated, `Locale.forLanguageTag()` is often concise and suitable. For admin configuration or user data where invalid input must produce an error, prefer Builder plus business validation.

## 7. Standalone Java 17+ Example: Bidirectional Conversion, Normalization, and Input Errors

Create the file **`LanguageTagDemo.java`** with the following content:

~~~java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LanguageTagDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-vn");
        Locale chinese = Locale.forLanguageTag("ZH-hans-cn");
        Locale customized =
                Locale.forLanguageTag("th-TH-u-nu-thai-ca-buddhist");

        System.out.println("Vietnamese: "
                + vietnamese.toLanguageTag());
        System.out.println("Chinese: "
                + chinese.toLanguageTag());
        System.out.println("Script: " + chinese.getScript());
        System.out.println("Calendar: "
                + customized.getUnicodeLocaleType("ca"));
        System.out.println("Numbering: "
                + customized.getUnicodeLocaleType("nu"));
        System.out.println("With extensions: "
                + customized.toLanguageTag());
        System.out.println("Equivalent: "
                + vietnamese.equals(Locale.forLanguageTag("vi-VN")));
        System.out.println("Locale toString: " + vietnamese);
        System.out.println("Malformed lenient: "
                + Locale.forLanguageTag("en-US-@bad").toLanguageTag());
        System.out.println("Wrong separator: "
                + Locale.forLanguageTag("en_US").toLanguageTag());
        System.out.println("Root: " + Locale.ROOT.toLanguageTag());

        try {
            new Locale.Builder()
                    .setLanguageTag("en-US-@bad")
                    .build();
            System.out.println("Builder: accepted");
        } catch (IllformedLocaleException ex) {
            System.out.println("Builder: rejected");
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac -encoding UTF-8 LanguageTagDemo.java
java LanguageTagDemo
~~~

Output (verified with source compiled at Java 17 compatibility level):

~~~text
Vietnamese: vi-VN
Chinese: zh-Hans-CN
Script: Hans
Calendar: buddhist
Numbering: thai
With extensions: th-TH-u-ca-buddhist-nu-thai
Equivalent: true
Locale toString: vi_VN
Malformed lenient: en-US
Wrong separator: und
Root: und
Builder: rejected
~~~

Analysis by group:

- `vi-vn` and `ZH-hans-cn` are normalized to `vi-VN` and `zh-Hans-CN`.
- `getScript()` reads `Hans`; `getUnicodeLocaleType("ca")` and `("nu")` read calendar/numbering preferences under the Unicode extension.
- `toLanguageTag()` sorts the `u` keys in the output tag.
- Two `Locale` instances with the same value after normalization can have `equals()` return `true` even when casing in the input tags differed.
- `toString()` represents `vi_VN` in the legacy form, different from `toLanguageTag()`.
- The lenient parser keeps `en-US` when encountering `@bad`; Builder rejects that error.
- `en_US` is not understood as `en-US` in the BCP 47 parser; `Locale.ROOT` outputs `und`.

The program does not depend on the default locale, time zone, or output encoding to determine the printed strings above, aside from the console needing to display standard ASCII characters.

## 8. Applications in Configuration and System Communication

### Storing Language Choices in a User Profile

For example, a user selects Vietnamese:

~~~java
String requestedTag = "vi-vn";
Locale locale = new Locale.Builder()
        .setLanguageTag(requestedTag)
        .build();

String canonicalTag = locale.toLanguageTag(); // "vi-VN"
~~~

This is an **illustrative code snippet** inside a class/method that has imported `java.util.Locale`. When storing configuration, use `canonicalTag` to keep a consistent spelling, but add a check to verify whether the application supports `vi-VN`. `toLanguageTag()` does not automatically provide the application with a translation bundle.

### HTTP Accept-Language Input Is Not a Single Language Tag

Example header:

~~~http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.7
~~~

This is a **priority-weighted list of choices**, not a single tag. Do not pass this entire string into `Locale.forLanguageTag()` and expect Java to negotiate the language automatically. You can use `Locale.LanguageRange.parse(header)` followed by `Locale.lookup(...)` / `Locale.filter(...)` with the application's supported locale list, or use the framework's locale resolution mechanism.

Illustrative snippet showing the idea inside a method that imports `java.util.List` and `java.util.Locale`:

~~~java
List<Locale> supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"));
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("vi-VN,vi;q=0.9,en-US;q=0.7");
Locale selected = Locale.lookup(priorities, supported);
// May be null if no matching tag is found: choose a fallback explicitly.
~~~

Order and weights affect negotiation results; when a system truly supports only two languages, you should test the no-match scenario, fallback, and generic tag (`vi`) versus regional tag (`vi-VN`).

### Do Not Equate Locale with Actual Formatting

The tag `th-TH-u-ca-buddhist` expresses a preference for calendar type, but whether a specific API uses this extension depends on the API and localization data provider. A standard `LocalDate` is still a date in the ISO calendar. Similarly, `vi-VN` does not automatically pick the Vietnam `ZoneId`, UTF-8 charset, or display font. Each technical requirement needs its own configuration.

### Standardizing Input Across APIs, Databases, and Caches

A stable strategy is to accept valid tags, normalize with `toLanguageTag()`, check the supported list, and then use the normalized value consistently across profiles, caches, and URLs. However, **BCP 47 normalization is not the same concept as language negotiation**: requesting `en-GB` does not automatically mean `en-US` content; two locales can share a language yet have different formatting conventions. Fallback decisions belong to business logic.

## 9. Common Mistakes

| Mistake | Why It Is Wrong | How to Prevent |
| --- | --- | --- |
| Using `Locale.toString()` to store language tags | Returns legacy form like `en_US` | Use `toLanguageTag()` |
| Using `forLanguageTag("en_US")` | `_` is not part of BCP 47 syntax | Use `"en-US"`; have a plan to migrate legacy config |
| Comparing raw strings `"vi-vn"` and `"vi-VN"` | Differ in case but equivalent after parsing | Normalize before using as a key |
| Assuming the parser throws errors on all bad tags | `forLanguageTag` drops the invalid part and everything after it | Builder + business validation |
| Thinking Builder verifies real languages | Mainly checks well-formed syntax | Check supported catalog/registry when needed |
| Sending the whole `Accept-Language` into `forLanguageTag` | Header is a weighted list | Use `LanguageRange` or framework support |
| Believing `Locale` translates text by itself | Locale only describes context | Use message bundles or translations |
| Believing `toLanguageTag` always keeps input byte-for-byte | Normalization and compatibility rules apply | Store original input separately if needed for audit |
| Calling `Locale.setDefault` per request | Default state is process-wide | Pass `Locale` directly to formatters |

## 10. Exercises and Self-Check Questions

**Exercise 1.** Explain the meaning of each part of `sr-Latn-RS`. When running `Locale.forLanguageTag(...).getScript()`, what do you expect to receive?

**Answer:** `sr` is Serbian, `Latn` is Latin script, `RS` is the Serbia region; `getScript()` returns `"Latn"`.

**Exercise 2.** Why can `Locale.forLanguageTag("en-US-@bad")` still return a `Locale` with language `en` and region `US`?

**Answer:** The lenient parser drops the first syntactically invalid subtag and the remaining part. It does not guarantee strict validation of the entire string.

**Exercise 3.** An API receives `"ZH-hans-cn"`, then returns `"zh-Hans-CN"`. Does that necessarily mean the API lost the locale?

**Answer:** No. This is per-component case normalization. You should compare the parsed locale state, not require the input string to remain identical character-for-character.

**Exercise 4.** When should you use `new Locale.Builder().setLanguageTag(value).build()` instead of `Locale.forLanguageTag(value)`?

**Answer:** When input must be rejected if syntactically invalid. You still need to check the application's supported locale list and fallback choice.

**Exercise 5.** Should `locale.toString()` be sent to a system that expects an IETF BCP 47 tag?

**Answer:** No. You must use `locale.toLanguageTag()`, e.g., `vi-VN` instead of `vi_VN`.

## Official References

- [Java SE 17 — java.util.Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): contracts for `forLanguageTag`, `toLanguageTag`, tag structure, and compatibility rules.
- [Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): `setLanguageTag` and `IllformedLocaleException`.
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): foundation of BCP 47 syntax.

**Key takeaway:** `forLanguageTag` converts **BCP 47 tag → Locale** and may drop syntactically invalid parts; `toLanguageTag` converts **Locale → normalized BCP 47 tag**. When strict constraints are needed, use `Locale.Builder` along with the application's locale support policy and fallback.