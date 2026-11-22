# Locale.of and Built-in Locale Constants in Java

## 1. The Problem: Creating the Right Locale to Handle Language and Region

An application may need to display content for users in Vietnam (`vi-VN`), English users in the United States (`en-US`), English in the United Kingdom (`en-GB`), or French in Canada (`fr-CA`). Each choice represents a **`Locale`**: a set of information identifying a language and regional context, which may include a script (writing system), variant, and extensions.

In Java, the `java.util.Locale` class provides objects used by `ResourceBundle`, `NumberFormat`, `DateTimeFormatter`, `Collator`, and many other APIs. To create a common `Locale`, you can call the `Locale.of(...)` factory or use **predefined constants** such as `Locale.US`, `Locale.ENGLISH`, and `Locale.JAPAN`.

**Key point:** A `Locale` is a *language/region* descriptor, not a translated sentence, not a time zone, and not a transaction currency. `Locale.of("vi", "VN")` does not automatically turn English strings into Vietnamese; it creates a context object so appropriate components know how to behave.

Lesson objectives: understand the overloads of `Locale.of`, choose common constants accurately, distinguish language and region, read back locale components, know when to use BCP 47 tags/`Locale.Builder`, and avoid JDK version errors.

## 2. Creating a Locale with Locale.of(...) — Available Since Java 19

Since **Java 19**, `Locale` provides three static factory methods:

```java
Locale.of(String language)
Locale.of(String language, String country)
Locale.of(String language, String country, String variant)
```

The three parameters have different meanings:

| Parameter | Common Values | Purpose |
| --- | --- | --- |
| `language` | `"vi"`, `"en"`, `"fr"`, `"ja"` | Language code (usually from ISO 639), normalized to lowercase |
| `country` / region | `"VN"`, `"US"`, `"GB"`, `"JP"` | Country/region code (usually ISO 3166-1 alpha-2 or three-digit UN M.49), normalized to uppercase |
| `variant` | `"POSIX"` | Additional variant, preserving letter case; use only when actually required |

Example:

```java
Locale vietnamese = Locale.of("vi");              // Language only
Locale vietnam = Locale.of("vi", "VN");            // Language + region
Locale americanEnglish = Locale.of("en", "US");
Locale withVariant = Locale.of("en", "US", "POSIX");
```

These objects are created by the factory; they **do not change** the JVM's default `Locale` and do not directly change an application's formatting. Pass the `Locale` to the API that needs it.

`Locale.of` normalizes the language and country components: `Locale.of("EN", "us")` represents the same locale as `Locale.of("en", "US")`. This factory **does not perform full syntax validation** on the supplied codes; passing arbitrary symbols can still create an object that has no meaning to locale data providers. `null` arguments cause a `NullPointerException`. Therefore, system locale choices must be validated at the application layer.

### A Very Common Pitfall: Locale.of Does Not Accept a Single BCP 47 Tag

The following two expressions have different meanings:

```java
Locale correct = Locale.of("en", "US");
Locale alsoCorrect = Locale.forLanguageTag("en-US");

// WRONG INTENT: the entire "en-US" is treated as a single language argument.
Locale incorrect = Locale.of("en-US");
```

`Locale.of(String)` expects a **standalone language code**, such as `"en"`, rather than parsing a combined string `"en-US"` into language + region. If you receive a locale tag string from configuration, an HTTP header, or a user profile, use `Locale.forLanguageTag("en-US")`; if strict BCP 47 syntax checking is needed, consider `Locale.Builder`.

### When to Use the Third Overload?

`Locale.of("en", "US", "POSIX")` adds a variant. A variant is part of the locale identifier; do not use a variant to stuff in a time zone, username, currency code, or any arbitrary label. Cases requiring a script such as `zh-Hant-TW` or an extension such as `th-TH-u-nu-thai` should use `Locale.forLanguageTag` or `Locale.Builder`; `Locale.of` has no dedicated parameters for scripts and extensions.

## 3. Commonly Used Locale Constants

Java defines common objects as `public static final` constants. Use a constant when it has the **exact meaning** your program needs: the code is concise, avoids typos in codes, and makes the intent clear.

### 3.1. Language-Only Constants

| Constant | Language tag | Meaning |
| --- | --- | --- |
| `Locale.ENGLISH` | `en` | English, no region specified |
| `Locale.FRENCH` | `fr` | French, no region specified |
| `Locale.GERMAN` | `de` | German, no region specified |
| `Locale.ITALIAN` | `it` | Italian, no region specified |
| `Locale.JAPANESE` | `ja` | Japanese, no region specified |
| `Locale.KOREAN` | `ko` | Korean, no region specified |
| `Locale.CHINESE` | `zh` | Chinese, no region/script specified |

For example, `Locale.ENGLISH` is equivalent in value to `Locale.of("en")`; it **does not automatically** carry the United States country code. This matters when selecting translation resources by language rather than imposing a default region.

### 3.2. Constants with Language and Region

| Constant | Language tag | Meaning |
| --- | --- | --- |
| `Locale.US` | `en-US` | English in the United States |
| `Locale.UK` | `en-GB` | English in the United Kingdom |
| `Locale.CANADA` | `en-CA` | English in Canada |
| `Locale.CANADA_FRENCH` | `fr-CA` | French in Canada |
| `Locale.FRANCE` | `fr-FR` | French in France |
| `Locale.GERMANY` | `de-DE` | German in Germany |
| `Locale.ITALY` | `it-IT` | Italian in Italy |
| `Locale.JAPAN` | `ja-JP` | Japanese in Japan |
| `Locale.KOREA` | `ko-KR` | Korean in South Korea |
| `Locale.CHINA` | `zh-CN` | Chinese in China |
| `Locale.TAIWAN` | `zh-TW` | Chinese in the Taiwan context |

The constants related to Chinese require further understanding:

- `Locale.PRC` is an alias with the same value as `Locale.CHINA`.
- `Locale.SIMPLIFIED_CHINESE` has the same value as `Locale.CHINA` (`zh-CN`).
- `Locale.TRADITIONAL_CHINESE` has the same value as `Locale.TAIWAN` (`zh-TW`).

**Do not infer that the constants above contain the `Hans` or `Hant` script.** The names `SIMPLIFIED_CHINESE` and `TRADITIONAL_CHINESE` are historical constant names tied to regions; wanting to *explicitly specify the script* requires `Locale.forLanguageTag("zh-Hans-CN")` or `Locale.forLanguageTag("zh-Hant-TW")`. `zh-TW` and `zh-Hant-TW` may lead to similar display results in some APIs, but they **are not two `Locale` objects with the same components**.

### 3.3. Locale.ROOT Is a Special Case

`Locale.ROOT` has an empty language, country, and variant. It does not represent English or any country. It is the neutral locale, often useful when processing needs rules independent of user preferences, or as the root locale in resource systems.

Example:

```java
Locale root = Locale.ROOT;

System.out.println(root.getLanguage().isEmpty()); // true
System.out.println(root.getCountry().isEmpty());  // true
System.out.println(root.toLanguageTag());         // und
```

`"und"` is the “undetermined language” tag in BCP 47 output. Do not implicitly use `Locale.ROOT` as a “default English translation”; a fallback translation must be configured separately.

### 3.4. Not Every Locale Has a Constant

The API does not have a `Locale.VIETNAM` or `Locale.VIETNAMESE` constant. For Vietnamese:

```java
Locale vietnam = Locale.of("vi", "VN"); // Java 19+
Locale vietnamFromTag = Locale.forLanguageTag("vi-VN"); // Java 7+
```

The two objects represent the same language/region and compare equal with `equals`. You should not “borrow” `Locale.CHINESE` or `Locale.ENGLISH` as a fallback just because you do not see a matching constant.

## 4. Java 21 Example: Creating, Comparing, and Reading Locales

Create the file **`LocaleFactoryDemo.java`** (a standalone Java file):

```java
import java.util.Locale;

public class LocaleFactoryDemo {
    public static void main(String[] args) {
        Locale vietnam = Locale.of("vi", "VN");
        Locale us = Locale.of("EN", "us");
        Locale traditional = Locale.forLanguageTag("zh-Hant-TW");

        System.out.println("Vietnam tag: " + vietnam.toLanguageTag());
        System.out.println("US equals constant: " + us.equals(Locale.US));
        System.out.println("ENGLISH tag: " + Locale.ENGLISH.toLanguageTag());
        System.out.println("US tag: " + Locale.US.toLanguageTag());
        System.out.println("ROOT tag: " + Locale.ROOT.toLanguageTag());
        System.out.println("Script/region: "
                + traditional.getScript() + "/" + traditional.getCountry());
        System.out.println("CHINA aliases: "
                + Locale.CHINA.equals(Locale.SIMPLIFIED_CHINESE));
        System.out.println("TAIWAN aliases: "
                + Locale.TAIWAN.equals(Locale.TRADITIONAL_CHINESE));
    }
}
```

Compile and run with **JDK 21**:

```bash
javac -encoding UTF-8 LocaleFactoryDemo.java
java LocaleFactoryDemo
```

Output:

```text
Vietnam tag: vi-VN
US equals constant: true
ENGLISH tag: en
US tag: en-US
ROOT tag: und
Script/region: Hant/TW
CHINA aliases: true
TAIWAN aliases: true
```

Points to observe:

1. `Locale.of("EN", "us")` is normalized to `en-US`, so `equals(Locale.US)` is `true`.
2. `Locale.ENGLISH` is `en`, different from `Locale.US` which is `en-US`: choosing a language is not the same as choosing a region.
3. `Locale.ROOT.toLanguageTag()` returns `und`; this is not a specific language.
4. For the tag `zh-Hant-TW`, `getScript()` returns `"Hant"` and `getCountry()` returns `"TW"`. The factory `Locale.of("zh", "TW")` does not automatically contain `Hant`.
5. The alias constants compare equal according to `equals` because they have the same locale value.

Note: if you use `Locale.of` in this file with JDK 17, compilation will fail because the method does not exist in Java 17; the error is at the **API version level**, not a missing `import`.

## 5. Choosing the Right Way to Create a Locale

| Situation | Recommended API | Reason |
| --- | --- | --- |
| Need a locale that already has a constant, e.g., US English | `Locale.US` | Clear meaning and less prone to typos |
| Separate language and region codes are known, on Java 19+ | `Locale.of("vi", "VN")` | Concise, matches component data |
| Language only, Java 19+ | `Locale.of("fr")` | Keeps region unspecified |
| Receiving a BCP 47 language tag string | `Locale.forLanguageTag("en-GB")` | Parses components from a tag string |
| Need script/extension, or stricter syntax checking | `new Locale.Builder()...build()` | Sets all fields and checks well-formedness |
| Project still compiles with Java 17 | `Locale.forLanguageTag("vi-VN")` or `new Locale("vi", "VN")` | `Locale.of` does not exist in Java 17; old constructors were later marked deprecated |

### Example Using Builder to Express a Script

```java
Locale traditionalChinese = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hant")
        .setRegion("TW")
        .build();

System.out.println(traditionalChinese.toLanguageTag());
// zh-Hant-TW
```

Builder reports malformed syntax errors via `IllformedLocaleException`. It cannot prove that the language/region has translations in the application or is fully supported by locale providers. `Locale.forLanguageTag` handles some malformed tags more leniently than Builder; if input requires strict validation, you must define your own validation policy.

### What Should Be Done for Java 17?

`Locale.forLanguageTag("vi-VN")` has existed since Java 7 and is a concise way, without using the old constructors, when the input source is a language tag. `new Locale("vi", "VN")` still works on Java 17; the `Locale(String...)` constructors were marked **deprecated as of Java 19**. Do not copy `Locale.of` into a library that must run/compile at `--release 17`.

## 6. How to Read Information Inside a Locale

Common methods:

| Method | Result | Notes |
| --- | --- | --- |
| `getLanguage()` | e.g., `"vi"` | Language code, not the display name |
| `getCountry()` | e.g., `"VN"` | Region code; may be empty |
| `getScript()` | e.g., `"Hant"` | Empty if no script is set |
| `getVariant()` | e.g., `"POSIX"` | Empty if there is no variant |
| `toLanguageTag()` | e.g., `"vi-VN"` | BCP 47 tag form, suitable for storing/transmitting locale info between systems |
| `toString()` | e.g., `"vi_VN"` | Legacy Java representation; not BCP 47 |
| `getDisplayLanguage(displayLocale)` | Human-readable language name | Depends on display locale and JDK data |
| `getDisplayCountry(displayLocale)` | Human-readable region name | Depends on display locale and JDK data |
| `getDisplayName(displayLocale)` | Name suitable for displaying to users | Should not hardcode stdout across all JDKs/CLDR |

Example:

```java
Locale selected = Locale.of("vi", "VN");
Locale ui = Locale.US;

System.out.println(selected.getLanguage()); // vi
System.out.println(selected.getCountry());  // VN
System.out.println(selected.toString());    // vi_VN
System.out.println(selected.toLanguageTag()); // vi-VN

// Display name in the UI language (here, English):
String label = selected.getDisplayName(ui);
```

Do not use `toString()` as a language tag sent over HTTP or as a BCP 47 configuration value, because it typically uses an underscore (`vi_VN`) instead of a hyphen (`vi-VN`). In systems using BCP 47, use `toLanguageTag()` for output and `forLanguageTag(...)` for input.

Simply calling `Locale.getAvailableLocales()` does not mean all returned locales already have translated strings in the application. That is the set of locales supported by providers in the runtime, which differs from the list of languages the **product** decides to support. Manage the supported list separately (for example, a `Set<Locale>` or a set of allowed language tags).

## 7. Practical Applications and Mistakes to Avoid

Suppose a notification service has one user who chooses Vietnamese and an administrator who chooses US English. The program picks `Locale.of("vi","VN")` for the first user's notification and `Locale.US` for the second; it then passes the locale to the corresponding `ResourceBundle`/formatter. **Do not call `Locale.setDefault(...)` per request**: the default locale is shared JVM state and can affect other concurrently running requests.

Common mistakes:

- **Confusing language-only with language + country:** `Locale.ENGLISH` is `en`, not equivalent to `Locale.US`. Date/number formatting can differ depending on locale and provider.
- **Passing the entire `"vi-VN"` into `Locale.of(String)`:** the factory does not split tags automatically; use `Locale.of("vi", "VN")` or `forLanguageTag("vi-VN")`.
- **Calling `Locale.of` in code compiled for Java 17:** the API was introduced in Java 19. Choose an API compatible with the actual version level; this lesson's demo code runs on JDK 21.
- **Using `Locale.CHINA` and assuming the `Hans` script is stored:** the constant has the tag `zh-CN`, not `zh-Hans-CN`; the script must be declared explicitly when it is part of the requirement.
- **Treating `Locale.ROOT` as a user's locale:** root is a neutral locale and does not represent a specific language.
- **Believing `Locale.of` validates all input codes:** the factory normalizes case but does not guarantee every value has valid syntax, semantics, or resources.
- **Using a locale to infer a time zone or transaction currency:** `Locale` does not contain a `ZoneId` and does not determine the currency unit of an order. Those values must be chosen separately according to business logic.
- **Comparing display names as canonical values:** `getDisplayName` can change depending on the UI language and data version; compare identifiers using `equals` or controlled language tags.
- **Using `Locale.getDefault()` where a user locale is needed:** the result depends on the process/server. Pass the locale explicitly.

## 8. Self-Check Questions

**Question 1.** Are `Locale.of("en")` and `Locale.US` equal?

**Answer:** No. The first object only has language `en`, while the second has language `en` and country `US`. `Locale.ENGLISH` is equivalent in value to `Locale.of("en")`.

**Question 2.** Configuration input contains the string `"zh-Hant-TW"`. Which method should be used?

**Answer:** `Locale.forLanguageTag("zh-Hant-TW")` to parse the full language, script, and region. If building from separate fields and strict syntax validation is needed, use `Locale.Builder`.

**Question 3.** Is `Locale.of("fr", "CA")` the same as `Locale.CANADA`?

**Answer:** No. `Locale.CANADA` has tag `en-CA`; `Locale.of("fr", "CA")` has tag `fr-CA` and equals `Locale.CANADA_FRENCH`.

**Question 4.** Why does the example use JDK 21?

**Answer:** Because `Locale.of(...)` starts in **Java 19**. Java 17 projects can use `Locale.forLanguageTag(...)`; do not rely on `Locale.of(...)` when Java 17 compatibility is required.

**Question 5.** Are the two locales `zh-TW` and `zh-Hant-TW` completely identical?

**Answer:** No. The second tag explicitly declares the `Hant` script; the first does not contain a script even though a provider may infer appropriate handling for the region.

## 9. Key Takeaways

- `Locale.of(language[, country[, variant]])` is a factory introduced in **Java 19** for separate locale components. It is not a parser for a language tag string.
- Constants such as `Locale.ENGLISH`, `Locale.US`, `Locale.FRANCE`, `Locale.JAPAN`… help use common locales with clear semantics. A language-only constant is **different** from a constant with language and region.
- `Locale.ROOT` is the neutral locale; `Locale.CHINA`/`SIMPLIFIED_CHINESE` and `Locale.TAIWAN`/`TRADITIONAL_CHINESE` are pairs of constants with the same value.
- Need a script, extension, or language tag input: use `Locale.forLanguageTag`/`Locale.Builder`. Need to run on Java 17: avoid `Locale.of`.
- Use `toLanguageTag()` when exchanging BCP 47 tags, `equals` to compare locale values, and pass the locale explicitly when formatting/translating per user.

**Official reference documentation:** [Java SE 21 — java.util.Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html); [Java SE 17 — java.util.Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html).