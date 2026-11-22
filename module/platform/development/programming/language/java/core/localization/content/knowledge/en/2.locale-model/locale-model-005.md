# The Role of Script in Locales Sharing the Same Language

## 1. The problem to understand

A **language** can be written in multiple **writing systems** (*scripts*). Therefore, two locales with the same language code and even the same region may still require different UI content, translation resources, and display behavior.

Examples:

| Locale (BCP 47) | Language | Script | Region | Meaning |
| --- | --- | --- | --- | --- |
| `sr-Latn-RS` | Serbian (`sr`) | Latin (`Latn`) | Serbia (`RS`) | Serbian written in Latin script in Serbia |
| `sr-Cyrl-RS` | Serbian (`sr`) | Cyrillic (`Cyrl`) | Serbia (`RS`) | Serbian written in Cyrillic script in Serbia |
| `zh-Hans-CN` | Chinese (`zh`) | Simplified Han (`Hans`) | China (`CN`) | Common choice for Simplified Chinese UI |
| `zh-Hant-TW` | Chinese (`zh`) | Traditional Han (`Hant`) | Taiwan (`TW`) | Common choice for Traditional Chinese UI |

The pair `sr-Latn-RS` / `sr-Cyrl-RS` is especially useful to analyze: **language and region are identical, only the script differs**. If a system only matches on `sr` or `sr-RS`, it may select the wrong resource bundle for what the user wants.

> **Distinction:** `script` provides information about the writing system; `language` describes the language, and `region` describes the country/region. A script code is **not** a character encoding, a font, or an automatic transliteration operation from Latin to Cyrillic.

## 2. Where does script fit in the `Locale` model?

A **BCP 47** language tag typically has the structure:

`language-Script-REGION`

Where:

- `language` is usually an ISO 639 language code, such as `sr`, `zh`, `az`.
- `Script` is a four-letter **ISO 15924** writing system code, typically normalized to Title Case: `Latn`, `Cyrl`, `Hans`, `Hant`.
- `REGION` is a region code, typically two uppercase letters, such as `RS`, `CN`, `TW`.
- BCP 47 also permits variant, extension, and private-use subtags when needed; the example above only shows the three components directly relevant to this lesson.

Not every locale declares a script. `sr-RS` has language and region, yet **does not specify a writing system**; it is not strictly equivalent to `sr-Cyrl-RS`. Localization data or language-selection systems may infer a commonly used script by convention, but the script value inside Java's `Locale` object remains empty if the input tag does not specify a script.

**Why does script matter?**

1. **Accurate translation and text form:** two translations may use the same language yet be authored in two different scripts.
2. **Resource selection:** an application may have string sets, guides, or images containing text appropriate for each script.
3. **User experience:** language selector labels should distinguish "Serbian (Latin)" and "Serbian (Cyrillic)" when the product supports both.
4. **Search, sorting, and display:** data, fonts supporting the glyphs, input methods, and sometimes collation rules may differ by script. Concrete behavior still depends on libraries, locale data, and runtime environment; the script code itself does not execute these operations.
5. **Accuracy of user preferences:** do not infer script solely from country when the user has explicitly selected a script.

## 3. Representing script with `java.util.Locale` in Java 17+

Java supports the script component through `Locale.forLanguageTag`, `Locale.Builder`, and `getScript`.

~~~java
import java.util.Locale;

public class ScriptParts {
    public static void main(String[] args) {
        Locale latin = Locale.forLanguageTag("sr-Latn-RS");
        Locale cyrillic = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Cyrl")
                .setRegion("RS")
                .build();
        Locale unspecified = Locale.forLanguageTag("sr-RS");

        System.out.println(latin.toLanguageTag());
        System.out.println(latin.getLanguage());
        System.out.println(latin.getScript());
        System.out.println(latin.getCountry());
        System.out.println(cyrillic.toLanguageTag());
        System.out.println(unspecified.getScript().isEmpty());
    }
}
~~~

Save as `ScriptParts.java` and run:

~~~bash
javac -encoding UTF-8 ScriptParts.java
java ScriptParts
~~~

Output:

~~~text
sr-Latn-RS
sr
Latn
RS
sr-Cyrl-RS
true
~~~

Explanation:

- `toLanguageTag()` reconstructs the BCP 47 tag with hyphens (`-`).
- `getLanguage()` returns `sr`; `getCountry()` returns `RS`.
- `getScript()` returns `Latn` or `Cyrl` when a script is present, and an empty string `""` when unspecified.
- `Locale.Builder` helps construct a locale with language, script, and region while validating subtags. For tags from external sources, validate/normalize the input data; `Locale.forLanguageTag` may handle malformed tags by discarding invalid parts rather than always throwing an error.
- Two `Locale` objects that differ in script should not be collapsed into one when script is a functional requirement of the application.

**Important note:** Java `String` uses Unicode, so the same application can hold both "Zdravo" and "Здраво". Selecting `Locale.forLanguageTag("sr-Cyrl-RS")` **does not automatically turn** the string "Zdravo" into "Здраво". The application must provide the corresponding resources or apply a separate transliterator if transliteration is truly required.

## 4. Practical application: selecting the right `ResourceBundle` by script

Suppose a Java UI supports Serbian in two writing systems. The following resources can be organized in the same directory/classpath:

~~~text
.
├── LocaleScriptDemo.java
├── Messages.properties
├── Messages_sr_Latn.properties
└── Messages_sr_Cyrl.properties
~~~

Contents of `Messages.properties` (fallback version):

~~~properties
hello=Hello
~~~

Contents of `Messages_sr_Latn.properties`:

~~~properties
hello=Zdravo
~~~

Contents of `Messages_sr_Cyrl.properties` (save file as UTF-8):

~~~properties
hello=Здраво
~~~

Create `LocaleScriptDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleScriptDemo {
    public static void main(String[] args) {
        String[] tags = {"sr-Latn-RS", "sr-Cyrl-RS"};

        for (String tag : tags) {
            Locale locale = Locale.forLanguageTag(tag);
            ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);

            System.out.printf(
                    "%s | language=%s | script=%s | region=%s | hello=%s%n",
                    locale.toLanguageTag(),
                    locale.getLanguage(),
                    locale.getScript(),
                    locale.getCountry(),
                    bundle.getString("hello")
            );
        }
    }
}
~~~

From the directory containing all the files above, run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 LocaleScriptDemo.java
java -cp . LocaleScriptDemo
~~~

Expected output:

~~~text
sr-Latn-RS | language=sr | script=Latn | region=RS | hello=Zdravo
sr-Cyrl-RS | language=sr | script=Cyrl | region=RS | hello=Здраво
~~~

**What happens?**

1. `Locale.forLanguageTag` reads the locale tag and preserves the script.
2. `ResourceBundle.getBundle("Messages", locale)` searches for the corresponding resource. Given the files present in this example, the Latin locale selects `Messages_sr_Latn.properties`, and the Cyrillic locale selects `Messages_sr_Cyrl.properties`.
3. `getString("hello")` returns the text prepared for the right writing system.
4. Java 9+ supports reading `.properties` resources in `PropertyResourceBundle` as UTF-8 by default (with a fallback mechanism for certain invalid byte sequences). The example uses JDK 17+ and files saved in UTF-8 to preserve Cyrillic characters.

BCP 47 tags use **hyphens** like `sr-Latn-RS`, whereas `ResourceBundle` file naming conventions use **underscores** like `Messages_sr_Latn.properties`; do not confuse the two syntaxes.

### What if a script-specific resource is missing?

`ResourceBundle` has a candidate lookup and fallback mechanism; an application may end up using a more general resource, the root bundle (`Messages.properties`), or in some situations trying the JVM's default locale. Do not assume that every case where `Messages_sr_Latn.properties` is missing will automatically receive a suitable Latin version or always fall straight back to the root file. Test against the actual resource set and fallback configuration of your application.

For content that requires a strict script match, **define an intentional fallback rule**: prefer matching language + script first, warn if resources are missing, and then pick a product-approved fallback option. Serving a Cyrillic bundle for a Latin request (or vice versa) can make the UI unreadable even though the language code is correct.

## 5. Design rules for multilingual applications

### When selecting and storing locales

- Store the full `language-Script-REGION` tag when the user has selected a script, such as `sr-Latn-RS`; do not shorten it to `sr` or `sr-RS` and lose the script preference.
- Only require selecting a script when disambiguation is genuinely needed; not every language has multiple commonly used scripts in a product.
- For input without a script, preserve the explicit "unspecified" state, then apply a default policy based on product needs and locale data. Do not assume `getScript()` will fill itself in.
- Display choices with user-friendly names, such as "Srpski (latinica)" and "Српски (ћирилица)", instead of showing two identical `sr` codes.
- Write tests with at least two locales sharing the same language and region but differing in script to catch dropped script components in cache keys, matching logic, or resource routing.

### When processing text

- **Localization:** providing content and formatting suited to the target locale.
- **Transliteration:** converting spelling between writing systems; this is a separate text-processing step that may require linguistic rules and exception handling.
- **Translation:** conveying meaning between languages. Two locales differing only in script may still require different editorial content and wording, not necessarily solvable by transliteration alone.
- **Fonts/rendering:** fonts supporting the characters to display are still required. `Locale` does not install fonts, change encodings, or guarantee glyphs render properly.

With `zh-Hans` and `zh-Hant`, Simplified/Traditional relate to Chinese writing systems, yet preparing appropriate content may also involve differences in terminology and phrasing. Do not treat this problem as a one-to-one character substitution.

## 6. Common misconceptions

| Misconception | Correct understanding and handling |
| --- | --- |
| "Same `language` means same UI content." | You must also inspect `script` and other locale differences that need support. `sr-Latn-RS` and `sr-Cyrl-RS` are not unconditionally interchangeable. |
| "Having `region=RS` makes `getScript()` return `Cyrl`." | If the source tag does not declare a script, `getScript()` returns an empty string; common inferences in other systems do not mutate this `Locale` object. |
| "Changing `Locale` automatically transliterates all strings." | `Locale` holds metadata for choosing behavior/resources; you need script-specific translations or a dedicated transliteration algorithm. |
| "`Script` is a region code or encoding." | `Latn`/`Cyrl` are ISO 15924 codes; `RS` is a region code; UTF-8 is an encoding, a different concept. |
| "Bundle filenames look identical to BCP 47 tags." | Tags use `-`, bundle suffixes use `_`. |
| "Testing only `sr-RS` is enough." | Test each script explicitly, including missing-script or missing-bundle cases, and observe fallback paths. |

## 7. How to test your understanding

1. Create three locales `sr-Latn-RS`, `sr-Cyrl-RS`, and `sr-RS`. Compare `getLanguage()`, `getCountry()`, and `getScript()`. Which field distinguishes the first two locales?
2. Run the `ResourceBundle` example; temporarily rename `Messages_sr_Latn.properties` to observe actual fallback behavior, then restore the file. Why must that behavior be controlled when the UI requires the right script?
3. Design a storage key for Serbian translations. Why does using only `language + region` create a collision risk?
4. Explain why "selecting `zh-Hant-TW`" does not mean "Java automatically converts all existing Simplified text into Traditional text".

**Key takeaway:** When multiple locales share the same language, **script is an essential identifying component for display and resource selection**. In Java, represent script explicitly with BCP 47/`Locale` when needed, preserve it throughout locale selection, and test resource fallback.
