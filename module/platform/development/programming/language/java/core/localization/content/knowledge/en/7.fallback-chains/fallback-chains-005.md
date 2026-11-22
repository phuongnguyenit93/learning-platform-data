# Search Order for Class-Based and Properties-Based Bundles

In Java, `ResourceBundle.getBundle(...)` searches for localized resources along **two distinct priority dimensions**:

1. **Locale specificity**: prioritize bundles matching the requested locale (for example `en_US`), then consider more general bundles (`en`, root bundle).
2. **Resource format within the same locale**: under the default configuration, Java prioritizes a bundle implemented as a **Java class** (`java.class`) before a bundle implemented as a **`.properties` file** (`java.properties`).

Do not infer that **every class-based bundle always beats every properties-based bundle**. `Messages_en_US.properties` can be selected ahead of `Messages_en.class` because `en_US` is more specific than `en`. However, if **both** `Messages_en_US.class` and `Messages_en_US.properties` exist, by default the class version takes precedence **at that exact `en_US` level**.

This also affects the **parent chain**: after locating the best-matching bundle, Java can link more general bundles to look up missing keys. **Two class/properties files at the same locale level are not automatically merged into a single bundle.**

This lesson explains the logical order, how it runs in practice on Java 17+, how to customize formats, and common pitfalls when bundle fallback or caching is involved.

## 1. Two Ways to Implement the Same `ResourceBundle` Family

Suppose `baseName` is `Messages`.

### Class Form — `java.class`

A class typically extends `ListResourceBundle`:

~~~java
import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"welcome", "Hello"},
                {"cancel", "Cancel"}
        };
    }
}
~~~

The source file `Messages_en.java` is compiled into `Messages_en.class`. When the classpath/module allows access, the loader can instantiate that class as a `ResourceBundle`. The class form lets you store values that are not only `String`: `ListResourceBundle` stores `Object` values retrievable via `getObject`, while requiring data validity and thread-safety across threads.

A class bundle must be a valid `ResourceBundle` subclass that can be loaded and instantiated under Java/runtime access rules; merely having a `.class` file with the matching name does not guarantee loading succeeds.

### Resource Form — `java.properties`

File `Messages_en.properties`:

~~~properties
welcome=Hello
cancel=Cancel
~~~

When the corresponding resource is found on the classpath/module, Java can read it as a `PropertyResourceBundle`. Values in `.properties` are strings; with `ListResourceBundle`, values can be arbitrary objects.

For Java 17+, `PropertyResourceBundle` supports reading UTF-8 per the JDK specification. Save files consistently as UTF-8. Do not confuse Java's resource bundle `.properties` loading with generic reading via `java.util.Properties.load(InputStream)`, as the two mechanisms have different encoding rules.

Both implementations **belong to the same `baseName` family** and can participate in a single fallback chain when placed at **different locale levels**.

## 2. Default Order Described by `ResourceBundle.Control`

In standard bundle loading on the **classpath/unnamed module**, `ResourceBundle.Control.FORMAT_DEFAULT` has the order:

~~~text
java.class
java.properties
~~~

This is the default format list returned by `Control.getFormats(baseName)`. At a given candidate locale, the runtime tries the class-based bundle first, and only then tries the properties-based bundle if no suitable class bundle can be selected.

Useful constants:

| Constant | Format list | Effect |
| --- | --- | --- |
| `ResourceBundle.Control.FORMAT_DEFAULT` | `["java.class", "java.properties"]` | Standard default order |
| `ResourceBundle.Control.FORMAT_CLASS` | `["java.class"]` | Try class form only |
| `ResourceBundle.Control.FORMAT_PROPERTIES` | `["java.properties"]` | Try properties form only |

These lists describe **formats**, not a replacement for the candidate locale order. When analyzing an unexpected result, ask **which locale's bundle was selected** first, and then ask **which format won at that locale**.

**Limitation:** In **named modules** (JPMS), lookup is also governed by package/module access rules and service providers; `getBundle` overloads taking `ResourceBundle.Control` are not supported when called from a named module. The `Control` demonstrations below are intended for **classpath/unnamed module** applications.

## 3. Candidate Locales: More Specific Wins First

Example:

~~~java
Locale requested = Locale.US; // language en, region US
ResourceBundle bundle = ResourceBundle.getBundle("Messages", requested);
~~~

For this locale, the standard candidate list by specificity is:

~~~text
Messages_en_US
Messages_en
Messages
~~~

The corresponding formats are tried for **each** candidate name:

| Locale level | Logical priority order at that level |
| --- | --- |
| `en_US` | `Messages_en_US.class` → `Messages_en_US.properties` |
| `en` | `Messages_en.class` → `Messages_en.properties` |
| Root (ROOT) | `Messages.class` → `Messages.properties` |

Thus, the **logical priority order** when selecting a bundle is:

~~~text
Messages_en_US.class
Messages_en_US.properties
Messages_en.class
Messages_en.properties
Messages.class
Messages.properties
~~~

Note that this is the **logical precedence order for understanding outcomes**, not a promise that every call opens files in that exact physical sequence. The JDK may already have cached certain bundles, or load parent/root bundles while building the parent chain. Hence logged `newBundle(...)` call order or actual file accesses **may differ** from this logical precedence order.

For more complex locales (such as script `zh-Hant-TW` or variants), `Control.getCandidateLocales(...)` produces a longer candidate sequence with special cases. Do not simply strip tag suffixes by hyphen in all cases.

## 4. Experiment 1: Class and Properties at the Same Locale — Class Wins

Create **five files** in the **same directory**. Filenames matter because Java uses them to construct bundle names.

**File `Messages_en_US.java`:**

~~~java
import java.util.ListResourceBundle;

public class Messages_en_US extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"origin", "US class"},
                {"shared", "from US class"}
        };
    }
}
~~~

**File `Messages_en_US.properties`:**

~~~properties
origin=US properties
shared=from US properties
onlyInProperties=hidden value
~~~

**File `Messages_en.properties`:**

~~~properties
origin=English properties
languageOnly=from language bundle
~~~

**File `Messages.properties`:**

~~~properties
origin=Root properties
rootOnly=from root bundle
~~~

**File `BundleOrderDemo.java`:**

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleOrderDemo {
    public static void main(String[] args) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", Locale.US);

        System.out.println(bundle.getLocale().toLanguageTag());
        System.out.println(bundle.getString("origin"));
        System.out.println(bundle.getString("shared"));
        System.out.println(bundle.getString("languageOnly"));
        System.out.println(bundle.getString("rootOnly"));
        System.out.println(bundle.containsKey("onlyInProperties"));
    }
}
~~~

Run with JDK 17+ in the directory containing all five files:

~~~bash
javac -encoding UTF-8 Messages_en_US.java BundleOrderDemo.java
java -cp . BundleOrderDemo
~~~

Output:

~~~text
en-US
US class
from US class
from language bundle
from root bundle
false
~~~

**Line-by-line analysis:**

1. `getLocale()` reports that the selected bundle corresponds to `en-US`. This is the locale of the **returned bundle**, not proof that every key lives in that bundle.
2. `origin` and `shared` exist in the `Messages_en_US` class, so values from the class are returned.
3. `languageOnly` does not exist in `Messages_en_US` class, so Java walks up to the `en`-level parent and fetches it from `Messages_en.properties`.
4. `rootOnly` is fetched via the root parent `Messages.properties`.
5. `onlyInProperties`, although present in `Messages_en_US.properties`, **does not appear**: because the class bundle at the **same `en_US` locale** was selected, Java does not attach the same-locale properties file as a parent or "supplementary key set".

This experiment clarifies two things: **format priority applies per candidate locale**, whereas **key fallback** traverses the parent chain of more general candidate locales.

If you remove `Messages_en_US.class` (with no other copy of the class loadable on the classpath) and relaunch in a fresh JVM, Java can select `Messages_en_US.properties`. In cached applications, verify the actual JVM run and classpath before concluding that deleting a file took effect immediately.

## 5. Experiment 2: Specific Properties Beats General Class

To avoid mixing with Experiment 1, use a **different bundle family** with baseName `Levels`.

**File `Levels_en.java`:**

~~~java
import java.util.ListResourceBundle;

public class Levels_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"origin", "EN class"},
                {"common", "English parent"}
        };
    }
}
~~~

**File `Levels_en_US.properties`:**

~~~properties
origin=US properties
~~~

**File `LevelsDemo.java`:**

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class LevelsDemo {
    public static void main(String[] args) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("Levels", Locale.US);

        System.out.println(bundle.getLocale().toLanguageTag());
        System.out.println(bundle.getString("origin"));
        System.out.println(bundle.getString("common"));
    }
}
~~~

Compile/run both `.java` files while keeping `Levels_en_US.properties` on the classpath:

~~~bash
javac -encoding UTF-8 Levels_en.java LevelsDemo.java
java -cp . LevelsDemo
~~~

Output:

~~~text
en-US
US properties
English parent
~~~

At the `en_US` level, `Levels_en_US.properties` exists; because it is **more specific** than `Levels_en.class`, **US properties wins as the primary bundle**. When looking up `common`, which is absent in the US bundle, Java uses `Levels_en.class` as the parent.

This example refutes the misconception "Java checks all classes first and only then all properties". More accurately: **select by candidate locale first; within each candidate, class precedes properties**.

## 6. Why Is There a Parent Chain?

After finding the bundle at the most specific existing candidate, `ResourceBundle` sets more general bundles as **parents**, for example:

~~~text
Messages_en_US (class)
    └── Messages_en (properties)
          └── Messages (properties)
~~~

When calling `bundle.getString("someKey")`:

1. Java looks up the key in the current bundle.
2. If not found, it searches its parent, then the next parent.
3. If absent across the entire chain, it throws `MissingResourceException`.

`getString` and `getObject` search through the parent chain; by contrast, `bundle.getLocale()` only reflects the locale of the primary bundle returned. A resource displayed from a parent **does not change** `getLocale()`.

**Distinguish from Java inheritance:** class `Messages_en_US extends ListResourceBundle` uses Java class inheritance, yet the **ResourceBundle parent chain** is a separate resource fallback mechanism. You do not need to declare `Messages_en_US extends Messages_en` for Java to find `Messages_en`; the runtime links parents automatically based on candidates. A class bundle setting its own parent manually is a special case; standard code should avoid relying on manual parent wiring unless needed.

There is no rule saying "if a key is missing, check the same-locale properties file" once the same-locale class has been chosen. This is a very common source of production bugs when a team accidentally ships both `Messages_en_US.java` and `Messages_en_US.properties` for the same baseName.

## 7. Fallback When the Requested Locale Is Not Found

In the default classpath flow, bundle selection may consider the **JVM default locale** if no bundle matches the requested locale; finally, it may fall back to the **root bundle** if present.

For example: the application requests `fr_CA`, but the `Messages` family has no French bundle. When the JVM default is `en_US` and English bundles exist, Java can pick a bundle for default `en_US`. If no other candidate exists, the root bundle can be the last resort. `getBundle(...)` throws `MissingResourceException` when no suitable resource is found across the entire search mechanism.

Do not oversimplify this algorithm into "always use root bundle before default". Under the default `Control` flow, the root bundle can be held back as the last choice while trying the default locale's chain. Java 17 also has differences across overloads and module contexts; always check the exact API being used.

### Distinguish Two Kinds of Fallback

- **Bundle fallback:** selecting a different bundle when no bundle matches the requested locale.
- **Key fallback:** a bundle was selected, but a key is missing; look up that key from a parent.

For instance, `getLocale()` may return `en-US` while one key comes from `Messages.properties`. That is **key fallback**. Conversely, requesting `fr-CA` while `getLocale()` returns `en-US` is a case of **bundle fallback** via default.

A multi-user application should pass an explicit locale into `getBundle(baseName, locale)`, with a transparent supported-locale and fallback policy. Do not call `Locale.setDefault(...)` per HTTP request: default is JVM-wide shared state and can mix languages across threads.

## 8. Observing Candidates Using `ResourceBundle.Control`

For applications running on the **classpath/unnamed module**, you can print the candidate/format lists standard Java uses to understand the logical order. Create `BundleCandidatesDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleCandidatesDemo {
    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_DEFAULT);

        System.out.println(control.getFormats("Messages"));

        for (Locale candidate : control.getCandidateLocales(
                "Messages", Locale.US)) {
            System.out.println(
                    candidate.equals(Locale.ROOT)
                            ? "ROOT"
                            : candidate.toLanguageTag()
            );
        }
    }
}
~~~

~~~bash
javac BundleCandidatesDemo.java
java BundleCandidatesDemo
~~~

Output:

~~~text
[java.class, java.properties]
en-US
en
ROOT
~~~

`getCandidateLocales` helps explain **locale level order**, while `getFormats` shows **format order within one level**. Iterating through the list for observation does not load any bundles and does not require `Messages*.properties` files to exist.

If the request is `Locale.forLanguageTag("zh-Hant-TW")`, the algorithm may include both scripted and unscripted candidates in the list. Do not write your own `language_country` string-joining logic and assume it represents the full JDK search.

**Important:** `ResourceBundle.Control` cannot be used in `getBundle(..., Control)` overloads when the caller is in a **named module**. If your application uses JPMS, prefer module-compatible APIs and inspect `ResourceBundleProvider`/export-open rules rather than copying Control experiments directly into a named module.

## 9. Class-Only or Properties-Only Options

In environments compatible with `ResourceBundle.Control`, Java supports configuring lookup to try only one format:

~~~java
ResourceBundle.Control onlyProperties =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle messages = ResourceBundle.getBundle(
        "Messages",
        Locale.US,
        onlyProperties
);
~~~

This is an **illustrative snippet inside a method**, requiring `import java.util.Locale;` and `import java.util.ResourceBundle;`. It uses candidate locales normally, yet allows **only the `java.properties` format**. Similarly, `FORMAT_CLASS` uses classes only.

You can also use:

~~~java
ResourceBundle.Control noDefaultLocaleFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_DEFAULT);
~~~

`getNoFallbackControl` prevents the alternative default-locale retry step per Control configuration; it does **not** mean "only load the exact requested locale" because the parent chain `en_US → en → ROOT` is still examined.

### Caution with Caching When Changing Control

`ResourceBundle` maintains a cache keyed by baseName/locale/class loader or module and governed by TTL. In many cases, a class bundle already cached under default configuration may continue to be returned if a subsequent call switches `Control` to allow only properties. The `ResourceBundle.Control` documentation warns that inconsistently changing format lists or candidate locales across calls for the same baseName can yield unexpected results.

When migrating an entire application from class to properties, pick **one consistent policy** and avoid mixing multiple Controls for the same bundle family. For tests, use separate JVMs or isolated baseNames/class loaders to test loading order; only use `ResourceBundle.clearCache()` under appropriate scope and conditions, remembering that already-held bundle references are not replaced simply by clearing the cache.

## 10. How Java Names and Locates Resources

For a `baseName` with a package:

~~~java
ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.US
);
~~~

Some corresponding names:

~~~text
com.example.i18n.Messages_en_US   (class name)
com/example/i18n/Messages_en_US.properties   (resource path)
com.example.i18n.Messages_en
com/example/i18n/Messages_en.properties
com.example.i18n.Messages
com/example/i18n/Messages.properties
~~~

When writing a Java class, the package name and class name must follow Java identifier rules. With Gradle or Maven, class bundles typically reside under Java sources, while `.properties` files live under application resources, and after packaging must be **present on the runtime classpath/module**. Filenames are case-sensitive on many filesystems; for example, `messages_en.properties` differs from `Messages_en.properties`.

Note that traditional Java resource filenames use underscores for locale components (`Messages_en_US.properties`), whereas `Locale.toLanguageTag()` returns BCP 47 format with hyphens (`en-US`). Do not rename files to `Messages_en-US.properties` just because language tags look that way.

**Classpath and class loader matter greatly:** a single same-named class bundle in another dependency loaded earlier can prevent your intended properties file from ever being chosen. When diagnosing, inspect the actual JARs/classpath and active class loader, not only the module's source folder.

## 11. Diagnosing Unexpected Bundle Selection Results

When translated values do not match a `.properties` file, inspect in order:

1. **Check the actual baseName and target locale.** For example, did the request pass `en-US`, or accidentally call the no-locale overload and use default?
2. **Check `bundle.getLocale()`.** This is the locale of the primary bundle, which can differ from target on fallback.
3. **Check candidate locales.** For `Locale.US`, typically `en_US`, `en`, ROOT. For scripts/variants/special locales, use `getCandidateLocales` in a supported context.
4. **Check both class and properties forms for each candidate.** At the **same** locale, class wins by default.
5. **Determine which bundle holds the key.** If a key is absent in the primary bundle, `getString` may retrieve it from a parent; `getLocale()` does not reflect that.
6. **Inspect the deployed artifact contents.** Does an old `Messages_en_US.class` still linger in the JAR from a previous build? Is the `.properties` file actually packaged at the right path?
7. **Check Control/provider policy, caching, and modules.** A different `Control`, another class loader, a previously cached instance, or JPMS configuration can alter the lookup path.
8. **Check case-sensitivity and character encoding issues.** A file appearing in source does not guarantee the runtime reads the intended file or bytes.

Avoid jumping to "the properties file wasn't read because Java prefers classes across all locales"; analyze both priority dimensions to pinpoint the exact reason.

## 12. Common Mistakes and Misconceptions

### "Class always beats properties"

**False if the class is at a less specific locale.** `Levels_en_US.properties` is selected as the primary bundle for `en-US` even when `Levels_en.class` exists. Only at the **same candidate locale** does class precede properties in the default format list.

### "A properties file at the same locale will fill in keys missing from the class"

**False.** In Experiment 1, `Messages_en_US.class` and `Messages_en_US.properties` are not automatically merged. Missing keys may be searched in parent bundles `Messages_en`/`Messages`; the shadowed properties file at the **same level** does not become a parent.

### "`getLocale()` tells you which locale every key came from"

**False.** `getLocale()` reflects the selected bundle. If a key comes from a parent, this method does not tell you which parent level supplied the key. To test true origin, use controlled values per bundle as in the experiments above.

### "The root bundle is always used immediately when the target locale is missing"

Not necessarily. Default locale fallback may be tried before accepting root as the final outcome. Distinguish bundle acquisition from the parent chain used for key lookup.

### "If `Messages_en_US.java` exists, `ResourceBundle` loads the `.java` file"

**False.** `.java` source code must be **compiled** into `.class`. Runtime loading does not execute Java source files as properties resources.

### "Changing resources at runtime updates immediately"

Not guaranteed due to caching. `ResourceBundle.clearCache()` affects the corresponding managed cache, yet does not mutate bundle objects already held by the application, and does not clear caches managed by other frameworks.

### "All APIs using `Control` work identically in every named module"

**False.** Overloads accepting `Control` are not supported when the caller is in a named module. JPMS also enforces encapsulation and resource access rules; analyze the module lookup path separately.

## 13. Practice Exercises with Answers

### Scenario A: Selecting the Primary Bundle

Files present:

~~~text
Labels_en_US.properties
Labels_en.class
Labels.properties
~~~

Request `Locale.US` using the default format. Which primary bundle is selected?

**Answer:** `Labels_en_US.properties` because candidate `en_US` takes priority over `en`. `Labels_en.class` can still serve as parent for missing keys.

### Scenario B: Both Formats Present at the Same Locale

Present:

~~~text
Labels_en_US.class
Labels_en_US.properties
Labels_en.properties
~~~

Request `Locale.US`. Key `title` exists only in `Labels_en_US.properties`, and is absent from `Labels_en_US.class`. Does Java automatically pull `title` from the same-locale properties file?

**Answer:** Not under the default order. The same-locale class is already selected; Java looks up missing keys via **parents** (`en`, ROOT if present), without automatically merging same-level `en_US` properties.

### Scenario C: No Translation for the Requested Locale

`Labels_en.properties` and `Labels.properties` exist, with no French bundle; JVM default is `en-US`, and `fr-CA` is requested. Can the English bundle be selected?

**Answer:** Yes, under the default-locale fallback mechanism; do not assume the system only looks at root when `fr_CA` is missing. Product i18n policy should manage fallback explicitly.

### Scenario D: Testing with Control

`Control.FORMAT_PROPERTIES` is applied on first access in a JVM with no cached class bundles. Given `Labels_en_US.class` and `Labels_en_US.properties`, which format is allowed to match?

**Answer:** Only `java.properties`. However, using different Controls for the same baseName after the cache has been populated can produce misleading test results.

### Scenario E: Missing Key Error

`ResourceBundle.getBundle("Labels", Locale.US)` returns a bundle, yet `getString("missing")` throws `MissingResourceException`. What happened?

**Answer:** The bundle **was found**, but the key `missing` does not exist in the primary bundle or its parents. This is not a bundle-not-found error.

## 14. Practical Summary

When designing bundles for a Java application:

- Use a **consistent baseName** and standard file/class names.
- Pick **one primary format** per bundle family, or if intentionally mixing class and properties, understand the candidate-locale priority rules clearly.
- Ensure critical keys exist in the specific bundle tier or a clearly designed parent.
- Remember that **class and properties at the same locale are not merged**.
- Pass `Locale` per request/user and test your fallback policy instead of changing the JVM default.
- Verify on the actual packaged classpath/module, especially when changing loading strategies or caching.

**Rule of thumb:** **A more specific locale wins first; within the same candidate locale, class precedes properties (with the default format).** After finding the primary bundle, Java continues looking up **missing keys** through the parent chain; that is a separate step from class/properties selection.

**References:** [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) and [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html).