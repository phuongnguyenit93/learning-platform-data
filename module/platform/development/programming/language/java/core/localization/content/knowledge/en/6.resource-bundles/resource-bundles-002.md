# Base Name, Package, and Bundle Naming Rules in Java `ResourceBundle`

## 1. From a Logical Name to a Real Resource

`java.util.ResourceBundle` is Java's mechanism for locating and reading resource sets by `Locale`, typically UI strings, labels, error messages, or other text values requiring localization.

A resource set might consist of these files:

```text
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
com/example/i18n/Messages_en.properties
```

In Java code:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
String greeting = bundle.getString("hello");
```

The string `"com.example.i18n.Messages"` is the **base name** of the entire bundle family; it **does not include** the locale suffix and **does not include** `.properties`. Java uses the base name together with the locale to generate a list of candidate bundle names, locates the matching resources, and returns the selected bundle.

A correctly named file placed in the wrong classpath location, or packaged into a JAR under the wrong path, still will not be found. Therefore you must understand **base name**, **package**, **runtime path**, and **locale suffix rules** together.

## 2. What Is a Base Name?

The **base name** is the shared identifier Java uses to look up language variants of the same resource set:

- `Messages`: a short base name, used when bundles sit at the root of the classpath.
- `com.example.i18n.Messages`: a **fully qualified** base name, used when bundles belong to the logical package `com.example.i18n`.

From the base name `com.example.i18n.Messages`, the candidate names can be:

```text
com.example.i18n.Messages_vi_VN
com.example.i18n.Messages_vi
com.example.i18n.Messages
```

For `.properties`-style bundles, Java maps dots in the package identifier to `/` in the resource path:

```text
com.example.i18n.Messages_vi_VN
                 ↓
com/example/i18n/Messages_vi_VN.properties
```

**Important rules:**

1. Pass the **base name**, such as `com.example.i18n.Messages`, to `getBundle`. Do not pass a filename with an extension like `Messages_vi_VN.properties`.
2. Do not hardcode a locale into the base name. If you pass `com.example.i18n.Messages_vi` as the base name, Java will treat `_vi` as part of the base name and continue generating additional candidates from it.
3. Choose clear functional names: `Messages`, `ValidationMessages`, `Labels`. Bundle families with different base names are resolved independently.
4. Dots in the base name represent the package; underscores separate locale components in the bundle name. Hyphens `-` are used in **BCP 47 language tags**, not as the standard separator in bundle filenames.

Comparison:

| Value / Location | Example | Purpose |
| --- | --- | --- |
| Base name passed to API | `com.example.i18n.Messages` | Identifies the bundle family to locate |
| Language tag | `vi-VN` | Represents the locale in BCP 47 |
| Candidate bundle name | `com.example.i18n.Messages_vi_VN` | Combines base name with locale |
| Resource file | `com/example/i18n/Messages_vi_VN.properties` | Actual resource loaded |
| Key in bundle | `hello` | Retrieves value via `getString("hello")` |

## 3. Package and Directory: Why Must They Match Exactly?

A Java class with the declaration:

```java
package com.example.i18n;
```

is typically stored in the corresponding source directory. However, `.properties` files are **runtime resources**, looked up through a classloader or the module system—not automatically inferred by Java from the directory of the `.java` file calling them.

Example Gradle/Maven project using the standard directory convention:

```text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/i18n/BundleNamingDemo.java
│   │   └── resources/
│   │       └── com/example/i18n/
│   │           ├── Messages.properties
│   │           ├── Messages_vi.properties
│   │           └── Messages_vi_VN.properties
```

When configured and built properly, resources are copied onto the runtime classpath, for example:

```text
build/classes/java/main/com/example/i18n/BundleNamingDemo.class
build/resources/main/com/example/i18n/Messages.properties
build/resources/main/com/example/i18n/Messages_vi.properties
build/resources/main/com/example/i18n/Messages_vi_VN.properties
```

When those runtime directories are on the classpath, the base name `com.example.i18n.Messages` resolves to the right resources.

**Do not confuse:** `src/main/resources` is a **build-time source directory**, not part of the base name. If you pass `"src.main.resources.com.example.i18n.Messages"`, Java will look up a different path and typically fail to find the bundle.

If you run with `java -cp ...` without Gradle/Maven, you must ensure the `.properties` files are placed under a **classpath root** at the exact package path. Simply putting resources next to `.java` source files is not enough if that directory is not included on the runtime classpath.

### The Caller's Package Does Not Automatically Determine the Base Name

Suppose class `com.example.app.Main` calls:

```java
ResourceBundle.getBundle("Messages", locale);
```

Java looks for the `Messages` family at the **root** of the corresponding resource path; it does not automatically turn it into `com.example.app.Messages`. If the bundles are in `com/example/app`, use `"com.example.app.Messages"`.

That is why fully qualified base names are usually safer and easier to maintain in multi-package projects.

## 4. `.properties` File Naming Rules by `Locale`

Common forms:

```text
<BaseName>.properties
<BaseName>_<language>.properties
<BaseName>_<language>_<COUNTRY>.properties
<BaseName>_<language>_<COUNTRY>_<VARIANT>.properties
```

For locales with a **script**, Java also generates candidate forms containing the script, such as `Messages_zh_Hant_TW.properties`.

Examples:

| Requested Locale | Typical Filename | Meaning |
| --- | --- | --- |
| `Locale.ROOT` | `Messages.properties` | Root bundle, no language/region attached |
| `Locale.forLanguageTag("vi")` | `Messages_vi.properties` | General Vietnamese |
| `Locale.forLanguageTag("vi-VN")` | `Messages_vi_VN.properties` | Vietnamese, Vietnam region |
| `Locale.forLanguageTag("en-US")` | `Messages_en_US.properties` | English, United States region |
| `Locale.forLanguageTag("en-GB")` | `Messages_en_GB.properties` | English, United Kingdom region |
| `Locale.forLanguageTag("zh-Hant-TW")` | `Messages_zh_Hant_TW.properties` | Chinese, Traditional script, Taiwan region |

For locales with script/variant components, `ResourceBundle.Control.getCandidateLocales` determines the exact candidates according to Java's algorithm; you should not naively concatenate every component using a single pattern. For example, with `zh-Hant-TW`, the list can include candidates with and without script/region before reaching the root bundle.

**Conventions to remember:**

- In **language tags**, write `vi-VN`, `zh-Hant-TW` with hyphens.
- In **bundle filename suffixes**, use underscores, such as `_vi_VN`, `_zh_Hant_TW`.
- Language is typically lowercase (`vi`, `en`), region is typically uppercase (`VN`, `US`), and script is typically title case (`Hant`, `Latn`). On case-sensitive filesystems, `Messages_vi_VN.properties` and `messages_vi_vn.properties` can be two different paths.
- Do not rename files directly from `locale.toLanguageTag()` by appending it to the filename. `ResourceBundle` candidate names are constructed from `Locale` components using specific rules.
- Files use the `.properties` extension (not `.property`, `.yml`, `.txt`), unless you deliberately implement a custom bundle mechanism.

## 5. In What Order Does Java Search for Bundles?

With:

```java
ResourceBundle.getBundle("com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

and basic bundles, Java generally considers candidates in order of decreasing specificity:

```text
Messages_vi_VN
      ↓
Messages_vi
      ↓
Messages  (ROOT)
```

**This is a simplified diagram for a locale with only language and region.** The standard algorithm can also include script, variant, class/properties format precedence, and a pass over the JVM's default locale. Therefore, not every call always follows just these three steps.

Distinguish between two levels of fallback:

1. **Selecting the matching bundle:** if `Messages_vi_VN.properties` does not exist but `Messages_vi.properties` does, `getBundle` can select the `vi`-level bundle.
2. **Looking up a key via parent bundles:** if the `vi_VN` bundle exists but does not contain the key `thanks`, `getString("thanks")` can retrieve it from the parent `vi` or root bundle. In that case, `bundle.getLocale()` still describes the **selected bundle**, not the locale of each individual key's origin.

If no bundle is available in the search mechanism, `getBundle` throws `MissingResourceException`. If a bundle is found but a key does not exist anywhere in that bundle's lookup chain, `getString` can also throw `MissingResourceException`.

### Root Bundle and Default Locale Are Not the Same

`Messages.properties` is the **root (`Locale.ROOT`)** resource of a bundle family. It does not mean "the translation of the JVM's default locale." Meanwhile, `Locale.getDefault()` is an environment setting that can affect the fallback pass when using the default `getBundle` overload.

To clearly observe locale candidate selection **without falling back to the JVM default locale**, the example below uses `ResourceBundle.Control.getNoFallbackControl(ResourceBundle.Control.FORMAT_PROPERTIES)`. This "no fallback" mode **does not eliminate the root bundle**; it only skips the fallback branch to the default locale in the algorithm.

## 6. Complete Java 17+ Example: Correct Naming, Package, and Bundle Loading

The following example is self-contained with no external libraries. It uses the **classpath** (unnamed module) and fixes the properties selection mechanism so results are not altered by the JVM default locale.

Create this exact structure:

```text
workspace/
├── src/
│   └── com/example/i18n/BundleNamingDemo.java
└── com/
    └── example/i18n/
        ├── Messages.properties
        ├── Messages_vi.properties
        └── Messages_vi_VN.properties
```

**File `com/example/i18n/Messages.properties`** — root bundle:

```properties
hello=Hello (default)
thanks=Thank you
```

**File `com/example/i18n/Messages_vi.properties`** — general Vietnamese:

```properties
hello=Xin chào
thanks=Cảm ơn
```

**File `com/example/i18n/Messages_vi_VN.properties`** — localized for Vietnam:

```properties
hello=Xin chào Việt Nam
```

**File `src/com/example/i18n/BundleNamingDemo.java`:**

```java
package com.example.i18n;

import java.util.Locale;
import java.util.ResourceBundle;

public class BundleNamingDemo {
    private static final String BASE_NAME = "com.example.i18n.Messages";

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    public static void main(String[] args) {
        show("vi-VN");
        show("vi-AU");
        show("ja-JP");
    }

    private static void show(String tag) {
        Locale requested = Locale.forLanguageTag(tag);
        ResourceBundle bundle = ResourceBundle.getBundle(
                BASE_NAME, requested, CONTROL);

        System.out.printf(
                "requested=%s, loaded=%s, hello=%s, thanks=%s%n",
                requested.toLanguageTag(),
                bundle.getLocale().toLanguageTag(),
                bundle.getString("hello"),
                bundle.getString("thanks"));
    }
}
```

From the `workspace` directory, compile and run:

```bash
javac -encoding UTF-8 -d . src/com/example/i18n/BundleNamingDemo.java
java -cp . com.example.i18n.BundleNamingDemo
```

Exact output with the three properties files above and JDK 17+:

```text
requested=vi-VN, loaded=vi-VN, hello=Xin chào Việt Nam, thanks=Cảm ơn
requested=vi-AU, loaded=vi, hello=Xin chào, thanks=Cảm ơn
requested=ja-JP, loaded=und, hello=Hello (default), thanks=Thank you
```

**Case-by-case explanation:**

- `vi-VN`: `Messages_vi_VN.properties` exists, so the selected bundle is `vi-VN`. Key `hello` comes from this bundle; key `thanks` is absent in `vi-VN`, so it falls back to parent `vi` and receives `Cảm ơn`.
- `vi-AU`: no `vi_AU` bundle exists, but `Messages_vi.properties` does; both keys come from bundle `vi`. `getLocale()` returns `vi`.
- `ja-JP`: no matching Japanese bundle exists, so the root `Messages.properties` is used. `Locale.ROOT.toLanguageTag()` returns `und` (*undetermined*), so `loaded=und` is expected.

The example does not depend on the machine's default locale because fallback to the default locale is disabled. Note that `getNoFallbackControl` is one way to use `ResourceBundle.Control` in a classpath environment; **named modules** have different restrictions—see section 8.

**Key takeaway:** the base name in code must match the exact path `com/example/i18n/Messages...`, yet the selected bundle name may differ from the requested locale. Additionally, an individual key can come from a **parent** rather than the file of the currently selected bundle.

## 7. Class-Based Bundles and Format Precedence

`ResourceBundle` does not read only `.properties` files. It also supports bundles implemented as **classes** (such as a class extending `ListResourceBundle`) with matching candidate names.

Example defining class **`com.example.i18n.Messages_en`**:

```java
package com.example.i18n;

import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"hello", "Hello"},
                {"thanks", "Thanks"}
        };
    }
}
```

This is a **component** within an application that already calls `ResourceBundle.getBundle("com.example.i18n.Messages", locale)`; to run as a standalone program, you still need a class with `main` and to place/compile the class in the proper package.

With default classpath behavior, Java can search for both class-based and `.properties` bundles. If both a class and a properties file represent **the same candidate name**, the class generally takes precedence under the default format order. Use `ResourceBundle.Control.FORMAT_PROPERTIES` when you intend to search only properties files, or `FORMAT_CLASS` when using classes only; the complete example in section 6 intentionally selects only properties.

**Do not confuse `Messages_en.java` with the resource `Messages_en.properties`:** the Java file must be compiled to `Messages_en.class` in the appropriate package, whereas properties files are loaded as resources. Both can share a base name, but they have different packaging mechanisms.

## 8. Classpath, JAR, and Named Modules

### 8.1. Running with the Classpath

For a program that does not use named modules, `getBundle` must be able to find the resource/class via the appropriate classloader. All of the following must align:

- Base name: `com.example.i18n.Messages`.
- Runtime directory: `com/example/i18n/`.
- Filename: `Messages_vi_VN.properties`.
- Classpath: the directory or JAR containing that path must be specified at runtime.

Inside a JAR, resource entries must be named like:

```text
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
```

You can inspect JAR contents with:

```bash
jar tf my-application.jar
```

If you do not see these resource entries (or see them prefixed unnecessarily with `src/main/resources/`), fix the packaging configuration or source location; arbitrarily changing the base name string does not solve the root cause.

In Gradle/Maven projects, use the standard resource source directories or configure resource roots explicitly. Do not assume a `resources` directory is found automatically by Java when invoking `java` directly without adding it to the classpath.

### 8.2. Using the Java Platform Module System (JPMS)

With **named modules**, resource lookup also depends on module boundaries, bundle placement, which `ResourceBundle.getBundle` overloads are used, and package accessibility. Do not mechanically copy a `getBundle(baseName, locale, control)` classpath example into a named module; overloads taking `ResourceBundle.Control` have restrictions and can throw `UnsupportedOperationException` in a named-module context.

In named modules, prefer appropriate module-aware APIs such as `ResourceBundle.getBundle(baseName, locale)` in the caller's context or overloads accepting `Module`, and configure resource package accessibility as required by module rules. If you choose to implement `ResourceBundleProvider`, follow the corresponding service/provider contract. Test **on the actual module path**, not only in classpath mode, because the two environments can load resources differently.

This section notes where resources are searched; the nature of base names and bundle naming principles remain unchanged.

## 9. Common Mistakes and How to Diagnose Them

| Symptom | Common Cause | How to Check or Fix |
| --- | --- | --- |
| `MissingResourceException: Can't find bundle for base name ...` | Wrong base name or missing candidate bundle at runtime | Check package, classpath/JAR, and root bundle |
| `Messages_vi_VN.properties` exists but is not used | Wrong directory, wrong case, not packaged, or wrong base name | Compare `com/example/i18n/` against base name and `jar tf` |
| Passing `Messages_vi_VN.properties` to `getBundle` | Passed filename instead of base name | Pass `com.example.i18n.Messages` and a separate locale |
| Naming `Messages_vi-VN.properties` | Confused BCP 47 `-` with bundle filename `_` | Name it `Messages_vi_VN.properties` |
| `getBundle("Messages", locale)` fails to find file in package | Base name lacks package | Use the fully qualified name |
| `vi_VN` bundle exists, yet some keys stay in English | Keys missing in child, falling back to parent/root | Check key coverage across each bundle |
| App uses wrong language when translation is missing | JVM default locale may participate in fallback | Define clear fallback policy, test `bundle.getLocale()` |
| Edited properties but output did not change | JAR file was not repackaged or bundle is cached | Verify artifact/runtime and cache lifecycle, redeploy as needed |
| Resources work on classpath but fail on module path | Different resource access rules | Check module, overload, and package accessibility |
| Vietnamese diacritics display incorrectly | Inconsistent resource encoding or packaging pipeline | Save files as UTF-8, check encoding and runtime/JDK |

### Additional Notes on Encoding and Caching

- On **Java 9+**, `PropertyResourceBundle` reads `.properties` as UTF-8 by default, with compatibility fallback for files encoded in the older style. With Java 17+, the Vietnamese example with diacritics in section 6 works appropriately. Ensure the IDE, build system, and translation tools use consistent encoding.
- `ResourceBundle` uses a **caching mechanism**. Updating a file on disk or inside a packaged JAR does not guarantee every running call immediately sees the new contents. If hot reload is required, design a dedicated cache lifecycle, resource update strategy, and loading mechanism.
- Filenames, keys, and values serve different roles: misnaming a bundle can cause **the entire bundle not to be found**; missing a key can cause Java to **fall back to a parent** or throw an error when the key does not exist anywhere.

## 10. Checklist for Adding a New Language

1. Identify the **base name** used in code and the runtime resource root location.
2. Create the file with the standard locale suffix, for example adding `Messages_en_GB.properties` for `en-GB`.
3. Place the file in the same package path as the bundle family, e.g., `com/example/i18n/`; do not create extra subdirectories named after locales when the API expects filename suffixes.
4. Check that critical keys have translations rather than unintentionally relying on default values.
5. Build and inspect the actual artifact (runtime directory or JAR contents).
6. Call `getBundle` with the target locale, observe `bundle.getLocale()`, verify important key values and fallback.
7. Also test a locale with the same language but different region, a locale without a bundle, and a missing-key case.
8. If the application runs as a named module, test the resource loading path under JPMS.
9. Document fallback rules, default locale handling, and cache behavior to avoid discrepancies between developer machines and deployment environments.

## 11. Key Takeaways

- **Base name** is the shared logical name of a bundle family, e.g., `com.example.i18n.Messages`; do not include `.properties` or language suffixes when calling `getBundle`.
- The **package** in the base name maps to the **runtime resource path**: `com.example.i18n.Messages` → `com/example/i18n/Messages*.properties`.
- **Bundle locale suffixes use underscores** such as `_vi`, `_vi_VN`, `_zh_Hant_TW`, whereas BCP 47 language tags use hyphens like `vi-VN`.
- **The selected bundle name and the source of each key may differ** due to fallback and parent bundles; inspect `bundle.getLocale()` and test key coverage.
- **Classpath, JAR contents, and named modules** determine whether resources are actually accessible. Naming files right is only half the job; they must be packaged and run in the proper environment.
