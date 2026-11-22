# Special Cases of Locale Names and How to Inspect Candidate Chains

## 1. Why Can't You Deduce the Bundle Chain Just by Trimming Suffixes?

In Java, `ResourceBundle` locates resources matching a `Locale` from a **base name** and a list of **candidate locales**. For a simple case like `vi-VN`, we usually picture:

```text
com.example.i18n.Messages_vi_VN
com.example.i18n.Messages_vi
com.example.i18n.Messages              (ROOT)
```

Yet that rule is **insufficient** for locales with scripts, variants, languages with historical naming, or special rules such as Chinese and Norwegian. For example, `zh-TW` can be interpreted as Traditional Chinese and generate names containing `Hant` even though the input tag specifies no script.

To diagnose accurately, do not construct names via `locale.toString()`, do not merely split `locale.toLanguageTag()` on hyphens, and do not assume every `Locale` produces the same chain length or shape. Use `ResourceBundle.Control.getCandidateLocales(baseName, locale)` and `Control.toBundleName(baseName, candidate)` directly to observe the name sequence the standard classpath mechanism considers.

This lesson focuses on **candidate chains and locale naming exceptions**. Distinguish the candidate list from actually locating a bundle file, falling back to the default locale, and looking up a key through parent bundles.

## 2. Three Related but Distinct Names

| Concept | Example | Where is it used? |
| --- | --- | --- |
| **Language tag** | `zh-Hant-TW` | Interchanging/representing languages per BCP 47; `Locale.forLanguageTag(...)`, `toLanguageTag()` |
| **Locale instance** | Language `zh`, script `Hant`, region `TW` | Argument to Java APIs and candidate selection |
| **Bundle name** | `com.example.i18n.Messages_zh_Hant_TW` | Candidate name used to look up a class or resource file |
| **Resource path** | `com/example/i18n/Messages_zh_Hant_TW.properties` | Actual location in classpath/JAR of a `.properties`-type bundle |

The bundle name appends to the **base name** without an extension. With `FORMAT_PROPERTIES`, Java converts that name into a resource path using `/` separators and the `.properties` extension.

Subtle detail: `Locale.toString()` is a representation for reading/logging `Locale` details, **not a bundle-filename contract**. For example, a locale with a script can render as `zh_TW_#Hant` when calling `toString()`, whereas the candidate bundle name is `Messages_zh_Hant_TW`. Call `Control.toBundleName(...)` to get the actual name Java searches for.

## 3. APIs for Inspecting Candidates Yourself

In **classpath/unnamed module** mode, `ResourceBundle.Control` provides:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_DEFAULT);

List<Locale> candidates =
        control.getCandidateLocales(
                "com.example.i18n.Messages",
                requested);

for (Locale candidate : candidates) {
    System.out.println(
            control.toBundleName(
                    "com.example.i18n.Messages",
                    candidate));
}
```

This is an **illustrative snippet** using variable `requested` and imports `Locale`, `List`, and `ResourceBundle`; a complete runnable program is shown in Section 4.

- `getCandidateLocales(baseName, requested)` returns an **ordered** list from specific candidates to broader ones, ending with `Locale.ROOT` under standard configuration.
- `toBundleName(baseName, candidate)` turns each candidate `Locale` into a **bundle name** following Java rules; this is the step to use when checking filename mistakes.
- `FORMAT_DEFAULT` can try class bundles and properties bundles; pick `FORMAT_PROPERTIES` when only `.properties` bundles are relevant.
- The returned list only describes **names considered**. It does not prove any of those names exist on the classpath, nor does it state which bundle will actually be selected.

**Important:** `getCandidateLocales` is a method on `ResourceBundle.Control`. Overloads of `ResourceBundle.getBundle` taking `Control` have limitations with **named modules**; do not blindly copy this example into a program running on the module path. Module-aware mechanisms are discussed in Section 9.

## 4. Java 17+ Program Printing Actual Candidate Name Chains

Create **`CandidateNamesDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class CandidateNamesDemo {
    private static final String BASE = "demo.Messages";

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getControl(
                    ResourceBundle.Control.FORMAT_DEFAULT);

    private static void print(String name, Locale locale) {
        List<Locale> candidates =
                CONTROL.getCandidateLocales(BASE, locale);

        String names = candidates.stream()
                .map(candidate ->
                        CONTROL.toBundleName(BASE, candidate))
                .collect(Collectors.joining(" -> "));

        System.out.println(name + ": " + names);
    }

    public static void main(String[] args) {
        print("vi-VN", Locale.forLanguageTag("vi-VN"));
        print("zh-TW", Locale.forLanguageTag("zh-TW"));
        print("zh-CN", Locale.forLanguageTag("zh-CN"));
        print("sr-Latn-RS", Locale.forLanguageTag("sr-Latn-RS"));
        print("en-US-u-nu-thai",
                Locale.forLanguageTag("en-US-u-nu-thai"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CandidateNamesDemo.java
java -cp . CandidateNamesDemo
```

Below are the output lines of the standard `Control` algorithm on modern JDKs, with the passed base name `demo.Messages` (long lines kept intact):

```text
vi-VN: demo.Messages_vi_VN -> demo.Messages_vi -> demo.Messages
zh-TW: demo.Messages_zh_Hant_TW -> demo.Messages_zh_Hant -> demo.Messages_zh_TW -> demo.Messages_zh -> demo.Messages
zh-CN: demo.Messages_zh_Hans_CN -> demo.Messages_zh_Hans -> demo.Messages_zh_CN -> demo.Messages_zh -> demo.Messages
sr-Latn-RS: demo.Messages_sr_Latn_RS -> demo.Messages_sr_Latn -> demo.Messages_sr_RS -> demo.Messages_sr -> demo.Messages
en-US-u-nu-thai: demo.Messages_en_US -> demo.Messages_en -> demo.Messages
```

This program **does not require `demo/Messages*.properties` files** because it only lists candidates without calling `getBundle` to load resources. To prove which bundle gets selected, you must supply real bundle files/classes and call `getBundle`; see Section 8.

## 5. Special Cases to Understand

### 5.1. Chinese: Script Inferred by Region

For `Locale.forLanguageTag("zh-TW")`, Java has a special case that infers script **`Hant`** (Traditional). Consequently, the candidate order can be:

```text
Messages_zh_Hant_TW
Messages_zh_Hant
Messages_zh_TW
Messages_zh
Messages
```

Similarly, `zh-CN` is treated with script **`Hans`** (Simplified):

```text
Messages_zh_Hans_CN
Messages_zh_Hans
Messages_zh_CN
Messages_zh
Messages
```

This has two consequences:

1. Even when requesting just `zh-TW`, Java can use `Messages_zh_Hant.properties` if no more specific file exists, before checking `Messages_zh_TW.properties`.
2. Do not rely on the absence of `Hant` in the input string to conclude the candidates lack a script.

For the tag `zh-Hant-TW` with an explicit script, the basic candidate order also starts at `zh_Hant_TW`, then `zh_Hant`, `zh_TW`, `zh`, and the root bundle. The examples above are **Java's candidate rules**, not a claim that all user bases in Taiwan/China share identical linguistic needs. Translation quality still requires real localization.

### 5.2. Locales with Explicit Scripts: Script Can Precede Region in Search Order

For `sr-Latn-RS` (Serbian written in Latin script in Serbia), Java considers:

```text
Messages_sr_Latn_RS
Messages_sr_Latn
Messages_sr_RS
Messages_sr
Messages
```

Although `sr_Latn` specifies no region, it can be tried **before** `sr_RS` because script strongly affects the writing system and readability of content. This shows fallback order is not simply "drop region first, then drop script" in every case.

**Filename note:** use `Messages_sr_Latn_RS.properties`, do not take `Locale.toString()` directly as the filename.

### 5.3. Norwegian: `no`, `nb`, `nn`, and Historical Variant `NY`

Java preserves several historical compatibility rules for Norwegian:

- `no` is the general Norwegian code.
- `nb` represents Norwegian Bokmål.
- `nn` represents Norwegian Nynorsk.
- The historical locale `new Locale("no", "NO", "NY")` represents an old special case related to Nynorsk.

For `nb-NO`, candidates under the standard algorithm are:

```text
Messages_nb_NO
Messages_no_NO
Messages_nb
Messages_no
Messages
```

For `nn-NO`:

```text
Messages_nn_NO
Messages_nn
Messages_no_NO_NY
Messages_no_NO
Messages_no
Messages
```

With the **legacy constructor** `new Locale("no", "NO", "NY")`, the candidate chain also begins with `nn_NO`, `nn`, and only then `no_NO_NY`:

```text
Messages_nn_NO
Messages_nn
Messages_no_NO_NY
Messages_no_NO
Messages_no
Messages
```

This is a **specific exception**, not a general rule for `Locale` converting any language into another. `NY` is a historical variant that does not satisfy standard BCP 47 variant syntax; therefore do **not** use `new Locale.Builder().setVariant("NY")` as a substitute example (the builder may throw `IllformedLocaleException`). To inspect the legacy case accurately, use the constructor as above or a legacy locale value received from older systems.

### 5.4. Historical Language Codes vs. Modern Codes

Some language codes once used in Java have historical forms:

| Old form | Modern equivalent |
| --- | --- |
| `iw` | `he` (Hebrew) |
| `in` | `id` (Indonesian) |
| `ji` | `yi` (Yiddish) |

The `Locale` API has compatibility rules for these codes; for instance, `Locale.forLanguageTag("iw-IL").toLanguageTag()` can return `he-IL`. Depending on how a locale is constructed and JDK compatibility rules, display strings from `getLanguage()`/`toString()` are not a safe basis for writing your own bundle-renaming algorithm.

**Right practice:** for a specific legacy locale, call `getCandidateLocales` and `toBundleName` on the target runtime; then verify which resource/class names are actually packaged. Whether files use old or new names can also depend on maintained legacy resources and JDK compatibility.

### 5.5. Variants: Not Always a Single Suffix

For locales with valid variants, Java can generate multiple candidates by **progressively trimming variant components** before dropping other specific components. When a script is present, the list can include both a scripted branch and a non-scripted branch.

Example name pattern:

```text
Messages_en_US_POSIX
Messages_en_US
Messages_en
Messages
```

The actual list depends on the locale, script, variant, and Java's special cases. Do not build fallback by repeatedly calling `lastIndexOf('_')` on `Locale.toString()`; that can produce the wrong order and miss branches such as `zh_Hant` or `nn_NO`.

### 5.6. Unicode Locale Extensions Do Not Automatically Become Bundle Suffixes

The tag:

```text
en-US-u-nu-thai
```

has extension `u-nu-thai` requesting Thai digits in APIs that understand Unicode locale attributes. However, in standard `ResourceBundle.Control.getCandidateLocales`, this extension **does not generate a file** like `Messages_en_US_u_nu_thai.properties`. The basic candidate chain is:

```text
Messages_en_US
Messages_en
Messages
```

Similarly, information like calendar `u-ca-japanese` can be meaningful to date/time services, yet does not imply a separate message bundle exists for each extension. Applications wishing to differentiate messages by extension must design custom rules and test them, rather than expecting automatic support from `getBundle`.

## 6. Dedicated Program Observing the Norwegian Exception

Create **`NorwegianCandidatesDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class NorwegianCandidatesDemo {
    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getControl(
                    ResourceBundle.Control.FORMAT_DEFAULT);

    private static void print(String label, Locale locale) {
        String names = CONTROL
                .getCandidateLocales("demo.Messages", locale).stream()
                .map(candidate ->
                        CONTROL.toBundleName("demo.Messages", candidate))
                .collect(Collectors.joining(" -> "));
        System.out.println(label + ": " + names);
    }

    public static void main(String[] args) {
        print("nb-NO", Locale.forLanguageTag("nb-NO"));
        print("nn-NO", Locale.forLanguageTag("nn-NO"));
        print("no_NO_NY", new Locale("no", "NO", "NY"));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 NorwegianCandidatesDemo.java
java -cp . NorwegianCandidatesDemo
```

Standard candidate chain output:

```text
nb-NO: demo.Messages_nb_NO -> demo.Messages_no_NO -> demo.Messages_nb -> demo.Messages_no -> demo.Messages
nn-NO: demo.Messages_nn_NO -> demo.Messages_nn -> demo.Messages_no_NO_NY -> demo.Messages_no_NO -> demo.Messages_no -> demo.Messages
no_NO_NY: demo.Messages_nn_NO -> demo.Messages_nn -> demo.Messages_no_NO_NY -> demo.Messages_no_NO -> demo.Messages_no -> demo.Messages
```

This check saves you from guessing special orders from filenames on disk. Similarly, you can swap the `Locale` passed to `print` to inspect other locales.

## 7. Candidate Chain Differs from Default-Locale Fallback

A common misconception is assuming `getCandidateLocales(...)` shows the **entire order that every `ResourceBundle.getBundle(...)` call is guaranteed to search**. In reality, distinguish:

**A. Candidate list for the requested locale.** `getCandidateLocales(baseName, requestedLocale)` lists options belonging to the requested locale, including `Locale.ROOT` under standard control.

**B. Fallback pass to the default locale.** When no suitable bundle is found under lookup rules, `ResourceBundle.Control.getFallbackLocale(baseName, locale)` may return the **JVM default locale** to try another candidate list. That branch does not mean `getCandidateLocales` for the requested locale already contains every locale on the machine.

**C. Parent bundle during key lookup.** A selected bundle can still query its parents when a key is missing; thus a key's value may come from a resource different from `bundle.getLocale()`.

**D. Root bundle `Locale.ROOT`.** The root bundle is a general candidate in the chain; it is not a specific language and is not synonymous with the JVM default locale. `Locale.ROOT.toLanguageTag()` returns `und`.

For instance, merely printing candidates for `fr-CA` is not enough to know whether Java will next try default locale `en-US` or whether the root bundle exists. You must know the control configuration and packaged resources.

To disable the **fallback branch to the JVM default locale** when working with properties bundles on the classpath:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "demo.Messages",
                Locale.forLanguageTag("fr-CA"),
                control);
```

This is an excerpt; it requires `java.util.Locale`, `java.util.ResourceBundle`, and real resources for `demo.Messages`. Calling it this way **does not remove the root bundle**, nor does it disable parent key lookup.

## 8. Checking Which Candidate Is Actually Loaded

Printing candidate names only answers **which names Java will consider**. To see which name exists and gets selected, you need an example with real `.properties` files.

Create the following structure in a working directory:

```text
workspace/
├── LoadedBundleDemo.java
└── demo/
    ├── Messages.properties
    ├── Messages_zh.properties
    └── Messages_zh_Hant.properties
```

**File `demo/Messages.properties`:**

```properties
message=ROOT
```

**File `demo/Messages_zh.properties`:**

```properties
message=CHINESE
```

**File `demo/Messages_zh_Hant.properties`:**

```properties
message=TRADITIONAL
```

**File `LoadedBundleDemo.java`:**

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class LoadedBundleDemo {
    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    private static void show(String languageTag) {
        Locale requested = Locale.forLanguageTag(languageTag);
        ResourceBundle bundle =
                ResourceBundle.getBundle("demo.Messages", requested, CONTROL);

        System.out.println(requested.toLanguageTag()
                + " -> loaded=" + bundle.getLocale().toLanguageTag()
                + ", value=" + bundle.getString("message"));
    }

    public static void main(String[] args) {
        show("zh-TW");
        show("zh-CN");
        show("fr-CA");
    }
}
```

From the `workspace` directory, run:

```bash
javac -encoding UTF-8 LoadedBundleDemo.java
java -cp . LoadedBundleDemo
```

Result with those exact three properties files and the control above:

```text
zh-TW -> loaded=zh-Hant, value=TRADITIONAL
zh-CN -> loaded=zh, value=CHINESE
fr-CA -> loaded=und, value=ROOT
```

**Explanation:**

- For `zh-TW`, among the candidates `Messages_zh_Hant_TW.properties` is absent, while `Messages_zh_Hant.properties` exists, so Java picks the `zh-Hant` bundle.
- For `zh-CN`, `zh_Hans_CN`, `zh_Hans`, and `zh_CN` are absent; `Messages_zh.properties` matches before reaching root.
- For `fr-CA`, no French bundle exists, so the root `Messages.properties` is used. `Locale.ROOT.toLanguageTag()` is `und`.
- Because `getNoFallbackControl` is used, the program does not try a JVM default locale branch that could alter the result.

Even if a `Messages_zh_TW.properties` file were added, the candidate order still checks `zh_Hant` before `zh_TW` for requested locale `zh-TW`. So `Messages_zh_Hant.properties` in the example can continue to be selected. To force a region-specific message for `zh-TW`, place the resource at the appropriate higher-priority candidate (such as `Messages_zh_Hant_TW.properties`) or design explicit selection logic.

## 9. Limitations When a Project Uses JPMS / Named Modules

`ResourceBundle.Control` is a practical tool for exploring candidate ordering on the classpath. However, when resource bundles reside in a **named module**, the module system uses its own loading mechanism, and `ResourceBundle.getBundle` overloads taking `Control` are not supported and may throw `UnsupportedOperationException`.

For JPMS projects:

- Use `getBundle(baseName, locale)` or overloads accepting `Module` as appropriate for the caller module's design.
- Verify resources are packaged into the module, along with package access policies and service declarations if using `ResourceBundleProvider`.
- Test on the **actual module path**. Do not treat classpath runs as proof that all resource names and JPMS access rules behave identically.
- You can use `Control.getCandidateLocales` standalone to **understand candidate naming rules**, yet do not treat it as a complete measurement of the actual module provider mechanism.

The runnable examples in this lesson intentionally use the classpath so `Control` behavior and properties files can be demonstrated directly.

## 10. How to Diagnose Unexpected Fallback

When Java selects the wrong translation, check systematically:

1. **Record the input:** actual `locale.toLanguageTag()`, language, script, region, variant, and extension values. Note that `Locale.toString()` can differ from the language tag.
2. **Print all candidates:** call `getCandidateLocales` and `toBundleName` as in Section 4 or 6. Inspect the order, especially for `zh`, `sr`, `nb`, `nn`, legacy variants, and extensions.
3. **Compare against real files/classes:** check the corresponding paths in the classpath or JAR, including uppercase/lowercase spelling. Never assume a file exists just because a name appears in the list.
4. **Check bundle format:** by default, class-based bundles may take precedence over `.properties` with the same candidate name; the examples here choose `FORMAT_PROPERTIES` to avoid ambiguity.
5. **Check default fallback:** inspect `Locale.getDefault()` and the `Control` in use. For deterministic testing, a no-fallback control as in Section 8 can help.
6. **Identify the loaded bundle:** `bundle.getLocale()` reports the selected bundle's locale. Key values can still come from a parent if the child bundle lacks a key.
7. **Check runtime state:** JDK version, classloader, resources inside build artifacts, module path, and `ResourceBundle` caching. If data changes while the process stays alive, caching may prevent loads from reflecting edited files.
8. **Test edge cases properly:** regions with inferred scripts, regions with explicit scripts, Norwegian, legacy language codes, Unicode extensions, language-only locales, and locales with no bundle at all.

| Symptom | What to check first | Reason |
| --- | --- | --- |
| `zh-TW` picks general Traditional bundle instead of `zh_TW` file | `zh_Hant*` appears ahead of `zh_TW` | Script inference has a special rule |
| `nn-NO` loads `no_NO_NY` resource | Historical Norwegian candidates | Java has a special compatibility branch |
| `en-US-u-nu-thai` ignores files with `u_nu_thai` | Candidate list drops Unicode extensions | Extensions do not automatically become bundle suffixes |
| `locale.toString()` looks different from filename | Compare with `toBundleName` | The two strings follow different formatting contracts |
| `getCandidateLocales` lists a file yet `getBundle` says missing | File/class absent from runtime classpath/module | Candidates are only names that may be tried |
| A key displays a different language from `bundle.getLocale()` | Key falls back to a parent | Key origin and selected bundle can differ |
| Works on classpath yet fails on module path | JPMS rules and `Control` calls | Module lookup and access permissions differ |

## 11. Takeaways

- The `ResourceBundle` candidate chain is an **ordered set of rules**, not merely progressive truncation of a BCP 47 tag.
- Cases to watch most closely: **scripts** (`sr-Latn-RS`), **inferred scripts for Chinese** (`zh-TW` → `zh_Hant*`, `zh-CN` → `zh_Hans*`), **Norwegian** (`nb`, `nn`, `no_NO_NY`), **historical language codes**, **variants**, and **Unicode extensions**.
- Use `ResourceBundle.Control.getCandidateLocales` followed by `toBundleName` to print candidate bundle names; do not build filenames from `Locale.toString()`.
- A candidate name appearing in the list **does not prove the resource exists**. Use `getBundle`, `bundle.getLocale()`, key checks, and artifact inspection to verify what is actually loaded.
- **Candidate chain**, **fallback to default locale**, and **parent key lookup** are three distinct concepts; understanding each tier lets you diagnose localization bugs accurately.
