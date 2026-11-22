# PropertyResourceBundle vs. ListResourceBundle in Java

## Objective

When a Java application needs to display content by language, `ResourceBundle` provides a common interface to look up resources by key name and `Locale`. Two typical resource implementations in the standard library are **`PropertyResourceBundle`** — reading key/value pairs from `.properties`-formatted content — and **`ListResourceBundle`** — retrieving resources from Java code via `getContents()`.

After this lesson, you can:

- Explain similarities and differences in **data source, value types, compilation, distribution, and maintenance**.
- Create bundles from `.properties` files and from `ListResourceBundle` Java classes, then look them up through the unified `ResourceBundle.getBundle(...)` API.
- Understand bundle naming by `Locale`, resolving matching bundles, looking up keys in parents, and source format precedence when both a class file and a `.properties` file share the same name.
- Distinguish `getString(...)` from `getObject(...)` when values are not `String`.
- Understand `PropertyResourceBundle` encoding rules on Java 17+, `Reader` vs. `InputStream` boundaries, and common mistakes.

This lesson focuses on **these two `ResourceBundle` implementations**. Locale selection mechanisms, language filtering, and product content management are related topics that should be kept separate.

## 1. Common Ground: Both Are `ResourceBundle`

`PropertyResourceBundle` and `ListResourceBundle` both extend `java.util.ResourceBundle`. Ordinary resource consumers do not need to know whether data is stored in a properties file or a Java class:

```java
ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);
String greeting = bundle.getString("greeting");
```

This is an illustrative snippet used inside a method, assuming a `Locale` variable `locale` already exists and `java.util.ResourceBundle` is imported.

In this model:

1. **Base name** `"Messages"` represents a **bundle family**.
2. **Requested locale** specifies the target language/region to search for.
3. **Specific bundle** (such as `Messages_vi.properties` or class `Messages_en`) supplies the keys and values.
4. **`ResourceBundle` API** resolves candidates, parent/fallback chains, and key lookup.

`ResourceBundle` governs selection and lookup; each subclass decides **how its own key/value pairs are stored**. Consequently, the two implementations are interchangeable at the API call level, yet differ in how resource sources are authored and maintained.

`ResourceBundle` also has a cache and fallback strategy. Editing a source file on disk **does not guarantee** the next `getBundle` call immediately reads the changes; caching belongs to `ResourceBundle` itself, not just one bundle type.

## 2. High-Level Comparison

| Criterion | `PropertyResourceBundle` | `ListResourceBundle` |
| --- | --- | --- |
| Data source | Java `.properties`-formatted content | A Java class extending `ListResourceBundle` |
| Resource definition | `key=value` lines, properties delimiters, and escapes | Override `protected Object[][] getContents()` |
| Key type | `String` | `String` |
| Value type | `String` | `Object` — can be `String`, `Integer`, `String[]`, etc. |
| Needs compiling translation source? | No compilation for `.properties`, though must be packaged as classpath resource | Yes, because values are declared in Java code |
| Naming by locale | `Messages.properties`, `Messages_vi.properties`, … | `Messages`, `Messages_vi`, … (corresponding public Java classes) |
| Best suited for | UI messages, labels, and translated text managed by translators | Typed object resources or resources conveniently generated in Java |
| Common risks | Wrong resource name/path, escape/encoding bugs, missing keys | Malformed `Object[][]` structure, unloadable class, recompilation needed on resource edits |

Which one to choose depends on the content:

- **Text, labels, messages, `MessageFormat` patterns**: `.properties` files are usually easier to edit, diff, and hand off to translators.
- **Data that genuinely requires Java types** (such as string arrays, numbers, immutable objects): `ListResourceBundle` can be appropriate.
- Mixing both in one resource set works, provided naming, loading rules, and value types remain consistent to avoid unpredictable side effects.

Just because `ListResourceBundle` is written in Java does not mean it auto-translates text, and just because `PropertyResourceBundle` uses plain text files does not mean it auto-refreshes when files change.

## 3. `PropertyResourceBundle`: Key-String Pairs in `.properties`

A properties file might look like:

```properties
# Messages.properties
greeting=Hello
help=Contact support
source=Root bundle
```

Vietnamese version:

```properties
# Messages_vi.properties
greeting=Xin chào
help=Liên hệ hỗ trợ
```

These files belong to the same bundle family with base name `Messages`.

When calling:

```java
ResourceBundle vi = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));
```

`ResourceBundle` can select `Messages_vi.properties` for locale `vi-VN` when no dedicated `vi_VN` variant exists. If the Vietnamese file lacks key `source`, the resource in base bundle `Messages.properties` can be resolved through the parent chain.

`.properties` files do not contain executable Java expressions. Values like:

```properties
maxRetries=3
enabled=true
```

are still strings `"3"` and `"true"` when read via `PropertyResourceBundle`. If you need an `int` or `boolean`, application code must validate and convert:

```java
int retries = Integer.parseInt(bundle.getString("maxRetries"));
boolean enabled = Boolean.parseBoolean(bundle.getString("enabled"));
```

This is an illustrative snippet inside a method with variable `bundle`. For editable input, validate values and handle `NumberFormatException` appropriately.

### `.properties` Syntax Rules

- `=` and `:` can separate keys from values; whitespace can also act as a delimiter under the properties format.
- Lines starting with `#` or `!` are comments (after optional leading whitespace).
- Backslash `\` is used for escapes, such as `\n` and `\uXXXX`; certain special characters in keys require escaping.
- Line continuations using trailing `\` at the end of a physical line follow specific rules. Do not assume displayed text will preserve newlines simply because the file wraps onto another line.

Therefore, when writing messages containing `:`, `=`, or `\`, distinguish key vs. value positions and test the loaded values. Java properties are **not JSON, YAML, or Java source**, and do not evaluate `MessageFormat` placeholders on their own: placeholders are processed only if you pass the string to the appropriate formatter.

### Encoding on Java 17+

This is an area often misunderstood due to older documentation:

- **Starting in Java 9**, `PropertyResourceBundle` reading from a byte stream prefers **UTF-8**. For byte sequences that are invalid UTF-8, default behavior can fall back to **ISO-8859-1** for compatibility with legacy sources.
- Setting the system property `java.util.PropertyResourceBundle.encoding` to `UTF-8` or `ISO-8859-1` can request a specific encoding for byte-stream reading. If UTF-8 is forced, invalid bytes can trigger an error instead of falling back.
- This encoding property is checked when the **`PropertyResourceBundle` class is initialized**. Changing the property mid-run is not a reliable way to alter encoding for already-loaded bundles.
- The `PropertyResourceBundle(Reader)` constructor uses characters already decoded by the `Reader`; **charset selection is the responsibility of the code creating the `Reader`**, not this constructor.

Thus, on Java 17+, you can normally write `greeting=Xin chào` directly in a UTF-8 saved `Messages_vi.properties`. Do not mechanically apply the legacy Java rule that "properties read only ISO-8859-1 and every Unicode character must always be escaped."

Note: `java.util.Properties.load(InputStream)` is a different API from `PropertyResourceBundle`'s loading mechanism. Do not assume they share the same encoding contract just because they share the file syntax.

### Direct Constructor vs. `getBundle`

You can instantiate a `PropertyResourceBundle` directly from an `InputStream` or `Reader`:

```java
import java.io.StringReader;
import java.util.PropertyResourceBundle;

PropertyResourceBundle direct = new PropertyResourceBundle(
        new StringReader("greeting=Xin chào\n"));
String greeting = direct.getString("greeting");
```

This is an illustrative snippet placed inside a method that handles or declares `IOException`. `StringReader` already provides a Unicode character stream, so `PropertyResourceBundle` performs no UTF-8 byte decoding here.

When creating a bundle directly like this, you manage the source yourself and do not automatically receive `ResourceBundle.getBundle(...)`'s name resolution, locale matching, caching, or parent chain. For typical multilingual message sets, `getBundle` is the more convenient entry point.

## 4. `ListResourceBundle`: A Java Class Returning `Object[][]`

`ListResourceBundle` is an `abstract` class. To create a bundle, write a public subclass and override `getContents()`:

```java
import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
            {"greeting", "Hello from Java class"},
            {"maxRetries", Integer.valueOf(3)},
            {"enabled", Boolean.TRUE}
        };
    }
}
```

Save it in `Messages_en.java` and compile to `Messages_en.class`.

Each row in `Object[][]` has exactly **two elements**: key and value. Keys must be `String`, while values can be any appropriate Java object. Never include duplicate keys or invalid values and assume the loader will cleanly resolve conflicts. Best practice is keeping keys unique, values non-null, and datasets easy to test.

When calling:

```java
ResourceBundle en = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("en-GB"));

String message = en.getString("greeting");
Integer retries = (Integer) en.getObject("maxRetries");
Boolean enabled = (Boolean) en.getObject("enabled");
```

This is an illustrative snippet inside a method with `import java.util.ResourceBundle;` and `import java.util.Locale;`.

Crucially, **values are typed**:

- `getObject(key)` returns `Object`, which can be cast after knowing or checking its type.
- `getString(key)` is valid only when the value is actually a `String`.
- `getStringArray(key)` is for `String[]` values.
- Calling `getString("maxRetries")` on `Integer.valueOf(3)` throws `ClassCastException`; runtime types do not auto-convert numbers to text for you.

Do not use `ListResourceBundle` as an arbitrary store for mutable stateful objects. Resources are cached and may be accessed by multiple threads; immutable or safely managed values help prevent concurrency bugs. A bundle holding mutable arrays also needs defensive strategies if returning direct references to callers.

### When Is `ListResourceBundle` Useful?

There are cases where you want to represent a resource that is not naturally a single string—such as a fixed list of choices, an ordered sequence of names, or values whose types should be preserved without text parsing. In those cases, declaring them in Java can be clear.

The downside is that translators often have to touch source code or a Java-class generation pipeline; files must be compiled and released with the application. When all values are UI text, `.properties` is usually simpler and easier to maintain.

## 5. Complete Example: Two Ways to Declare the Same Bundle Family

The following example runs on **Java 17+** and demonstrates:

1. `ResourceBundle.getBundle(...)` can load both `Messages_en.class` and `Messages_vi.properties` in the same family.
2. Values in a Java class bundle can be `Integer`.
3. Keys absent from a localized bundle can be resolved from the root bundle.
4. `getString(...)` does not automatically coerce an `Integer`.

Create these four files in the **same directory**.

### File 1: `Messages.properties`

```properties
greeting=Hello from root
help=Help from root
origin=Root resource
```

### File 2: `Messages_vi.properties`

Save as **UTF-8**:

```properties
greeting=Xin chào
help=Trợ giúp bằng tiếng Việt
```

### File 3: `Messages_en.java`

```java
import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
            {"greeting", "Hello from Java class"},
            {"maxRetries", Integer.valueOf(3)},
            {"enabled", Boolean.TRUE}
        };
    }
}
```

### File 4: `BundleTypesDemo.java`

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleTypesDemo {
    public static void main(String[] args) {
        ResourceBundle english = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("en-GB"));

        ResourceBundle vietnamese = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("vi-VN"));

        System.out.println(english.getClass().getSimpleName());
        System.out.println(english.getString("greeting"));
        System.out.println(english.getString("help"));
        System.out.println(english.getObject("maxRetries"));

        System.out.println(vietnamese.getClass().getSimpleName());
        System.out.println(vietnamese.getString("greeting"));
        System.out.println(vietnamese.getString("help"));
        System.out.println(vietnamese.getString("origin"));

        try {
            english.getString("maxRetries");
        } catch (ClassCastException ex) {
            System.out.println("Wrong type for getString");
        }
    }
}
```

Open a terminal in the directory containing all four files and run:

```bash
javac -encoding UTF-8 Messages_en.java BundleTypesDemo.java
java -cp . BundleTypesDemo
```

Expected stdout:

```text
Messages_en
Hello from Java class
Help from root
3
PropertyResourceBundle
Xin chào
Trợ giúp bằng tiếng Việt
Root resource
Wrong type for getString
```

Result explanation:

- `en-GB` has no dedicated `Messages_en_GB`, so it selects language bundle `Messages_en` (the Java class). This class defines `greeting`, `maxRetries`, and `enabled`.
- `help` is not declared in `Messages_en`, so the lookup gets the value from `Messages.properties`, the root resource.
- `vi-VN` has no dedicated `Messages_vi_VN`, so it finds `Messages_vi.properties`. The Vietnamese keys are read from the UTF-8 file; `origin` comes from the root resource.
- `getClass().getSimpleName()` shows which implementation was returned in the example. Inspecting the concrete class is only for **observation**; production code should normally program against the `ResourceBundle` interface.
- `maxRetries` in the Java class is an `Integer`, so `getObject` returns the numeric object. Calling `getString` on the same key throws `ClassCastException`, which is caught to print the last line.

The output does not depend on the JVM's default locale because both requested locales have matching bundles and the base bundle is present. To keep the output consistent, ensure no other `Messages*` classes or files with the same name exist on the classpath.

In a project with packages, stay consistent with fully qualified names: for example class `com.example.i18n.Messages_en` and resource `com/example/i18n/Messages_vi.properties`, then call `getBundle("com.example.i18n.Messages", locale)`.

## 6. How `ResourceBundle` Chooses `.class` vs. `.properties`

When calling `ResourceBundle.getBundle(baseName, locale)` under standard default classpath mechanics, the search is guided by **base name**, **locale candidates**, and **allowed formats**.

For `Messages` and a request for `en-GB`, the relevant candidates might be:

```text
Messages_en_GB
Messages_en
Messages
```

For each candidate, the loader checks whether a matching Java class or `.properties` file exists. **For the same candidate name**, the default format order is **`java.class` before `java.properties`**. Thus, if both class `Messages_en` and file `Messages_en.properties` exist simultaneously, default classpath mechanics prioritize the Java class for candidate `Messages_en`.

However, **locale specificity also matters**: a `Messages_en_GB.properties` file for a more specific locale can be selected before the `Messages_en` class. Do not misinterpret "classes have priority" as "every class in the bundle family always beats every properties file."

### Cases to Remember

| Situation | Typical Outcome with Default Lookup |
| --- | --- |
| `Messages_vi.properties` exists and `vi-VN` is requested | Selects `vi` when no matching `vi_VN` exists |
| Both `Messages_en.class` and `Messages_en.properties` exist for the same candidate | `.class` takes format precedence |
| `Messages_en_GB.properties` and `Messages_en.class` exist, `en-GB` requested | More specific candidate `en_GB` wins |
| Selected bundle lacks a key, parent bundle has it | Key resolved via parent chain |
| No bundle found under fallback rules | `MissingResourceException` may be thrown |
| A key exists in both child and parent | Child value shadows parent value for the same key |

Lookup and fallback are not simply replacing `"vi-VN"` with `"vi"`. For some inputs lacking candidates, default mechanics may check the JVM's default locale before the root bundle. Behavior depends on runtime configuration, class loader, custom `ResourceBundle.Control`, or modules if the application uses them.

Therefore, **do not assume every lookup miss for a requested language immediately jumps to the base bundle**. To make predictable language decisions in an application, resolve the product's supported locales before looking up resources.

### Avoiding Unintended Shadowing

In the example, class `Messages_en` and file `Messages_vi.properties` support two different locales, so there is no ambiguity. If a project accidentally packages **both** `Messages_en.class` and `Messages_en.properties`, the team might edit the properties file without seeing changes because the class gets picked first.

When migrating a bundle family from one format to the other, inspect the final artifact (JAR/classpath), remove stale shadowing resources, and test output across supported locales. Do not look only at the source directory.

## 7. Value Types: Differences That Directly Affect the API

`PropertyResourceBundle` provides strings. `ListResourceBundle` can provide arbitrary object types as needed.

```java
protected Object[][] getContents() {
    return new Object[][] {
        {"title", "Welcome"},
        {"retryCount", Integer.valueOf(5)},
        {"tabs", new String[] {"home", "settings"}}
    };
}
```

This illustrates overriding `getContents()` inside a subclass of `ListResourceBundle`, not a standalone program.

When consuming this resource:

```java
String title = bundle.getString("title");
int count = (Integer) bundle.getObject("retryCount");
String[] tabs = bundle.getStringArray("tabs");
```

These illustrative expressions assume `bundle` already holds the corresponding bundle.

If `retryCount` is accidentally changed from `Integer` to the string `"5"`, casting to `Integer` will fail. That is a **type-contract change**, even though the key stayed the same. Conversely, with properties files, the app typically parses `"5"` to `int` at the call site and handles invalid data.

Do not put arbitrary typed values into `ListResourceBundle` just to avoid parsing. For UI labels, both developers and translators usually find text easier to inspect when keys and values are all `String`.

## 8. Missing Keys, Caching, and Resource Loading Errors

### Missing Keys

`getString("missingKey")` does not return an empty string by default. If the key is absent from the current bundle and all parent bundles, `ResourceBundle` throws `MissingResourceException`. Handling should align with product policy:

- During development/testing: detect missing keys early to avoid releasing a partially translated UI.
- In production: use a defined fallback message or controlled logging; never silently return `null` and trigger `NullPointerException` elsewhere.
- During translation: keep keys consistent and avoid renaming keys without updating all localizations.

Resource bundle keys are case-sensitive. `title` and `Title` are two distinct keys.

### Caching

`ResourceBundle.getBundle(...)` caches resolved bundles. Updating `Messages_vi.properties` directly on disk while the application runs does **not** mean held bundle references or subsequent lookups immediately see the new contents.

Depending on needs, you can use `ResourceBundle.clearCache()` (or the class-loader overload) and manage an appropriate reload workflow. Clearing the cache does not alter `ResourceBundle` references already stored by code, nor does it guarantee every class loader, module, and framework reloads identically. If hot-reloading resources is required, design and test a dedicated workflow.

### Configuration Errors

- A wrong base name or placing resources outside the classpath can lead to `MissingResourceException`.
- An unloadable Java class bundle (wrong visibility/package/constructor) may be skipped during candidate resolution or raise an error depending on the loading path; inspect the class-loading cause.
- A `.properties` file with invalid escapes can throw `IllegalArgumentException` during parsing.
- Enforcing UTF-8 decoding with invalid bytes can cause encoding errors when reading `PropertyResourceBundle`.
- `Object[][]` data violating the contract (non-`String` key, null value, duplicate keys) is a bug in the `ListResourceBundle` class; do not expect `ResourceBundle` to repair invalid content.

For quick diagnostics, verify **base name**, **package path**, **class loader**, **actual runtime artifact contents**, **requested locale**, and **selected resource source**.

## 9. When Should You Choose Each One?

Choose `PropertyResourceBundle` when:

- Content is mainly translated text, labels, error messages, and display templates.
- Translators or localization pipelines need to edit data without modifying Java code.
- You need to diff key/value sets across languages and check for missing keys.
- You want to keep translation sources separate from Java logic.

Choose `ListResourceBundle` when:

- Resources are typed Java objects and preserving types provides real value.
- Certain structured values are awkward to express cleanly as string properties.
- You control compilation and release of resource classes.
- The development team has tests validating keys and value types.

You can mix both approaches within the same family, as shown in the example, provided you understand **source selection rules**, **return types**, and **parent fallback**. In complex systems, separating non-localized structured data out of `ResourceBundle` is sometimes cleaner than stuffing everything into mixed-type bundles.

### Implementation Checklist

1. Choose a stable base name such as `com.example.i18n.Messages`.
2. Name each language variant accurately according to Java's candidate locale rules.
3. Ensure classes and properties are packaged in the right classpath/module locations.
4. Keep keys consistent across locales and test for missing keys.
5. Keep value types stable for callers using `getObject`/`getStringArray`.
6. Save `.properties` as UTF-8 on Java 17+ and write tests for Unicode.
7. When migrating from files to classes or vice versa, verify no same-named resources remain to shadow the new ones.
8. Explicitly decide fallback policy, cache/reload behavior, and the supported locale list.

## 10. Self-Check Questions

**Question 1.** If `Messages_vi.properties` has `count=5`, what type does `getObject("count")` return? Why can't you cast it straight to `Integer` as when reading from a `ListResourceBundle` containing `Integer.valueOf(5)`?

**Question 2.** An application has both `Messages_en.class` and `Messages_en.properties`. For the same candidate `Messages_en` under default lookup, which source takes precedence? If you add `Messages_en_GB.properties` and request `en-GB`, how does specific-candidate precedence change?

**Question 3.** Bundle `Messages_vi.properties` lacks key `help`, yet `Messages.properties` has it. Why can `getString("help")` still return a value? If even the parent bundle lacks the key, what exception occurs?

**Question 4.** Why does `PropertyResourceBundle` on Java 17+ not require Unicode escapes for every Vietnamese character? Why does the `Reader`-accepting constructor not perform UTF-8 decoding itself?

**Question 5.** If you edit `Messages_vi.properties` while the application is running, do existing `ResourceBundle` references automatically pick up the new values? How does caching affect this?

**Question 6.** A resource set currently holds only `String` messages. Explain why a team with multiple translators might prefer `PropertyResourceBundle`, and when `ListResourceBundle` is genuinely worthwhile.

## 11. Conclusion

`PropertyResourceBundle` and `ListResourceBundle` both implement the `ResourceBundle` contract, yet differ in source format and data types. **`PropertyResourceBundle`** reads properties-style resources and exposes values as `String`, making it well suited for localized text. **`ListResourceBundle`** retrieves resources from `Object[][]` in a Java class, supporting typed object values at the cost of compilation and type-contract enforcement.

At the usage layer, `ResourceBundle.getBundle(baseName, locale)` handles selecting the matching bundle, parent/fallback chains, and key lookup. Understand class-vs-properties precedence **for the same candidate**, keep specific candidates distinct from source formats, and test both Unicode and keys/types before release.

API documentation references: [`ResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html), [`PropertyResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html), [`ListResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListResourceBundle.html) (Java SE 17).
