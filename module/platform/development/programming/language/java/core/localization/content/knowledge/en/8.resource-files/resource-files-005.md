# Distinguishing Properties.load(InputStream) from PropertyResourceBundle

## 1. Two APIs that both read .properties but serve two different purposes

Suppose an application stores messages in `messages_vi.properties`:

```properties
title=Tiếng Việt
button.save=Lưu
```

You can read this file with `java.util.Properties.load(InputStream)`, or let the localization system locate the file via `ResourceBundle.getBundle(...)` and `PropertyResourceBundle`. Both understand the key/value syntax of the `.properties` format, yet **they are not the same resource-loading mechanism**.

The difference most likely to cause bugs with Vietnamese: **`Properties.load(InputStream)` always decodes bytes as ISO-8859-1**, whereas **`PropertyResourceBundle(InputStream)` on Java 9+ defaults to decoding as UTF-8, with the ability to re-read as ISO-8859-1 if an invalid UTF-8 byte sequence is encountered**. Even when the file sits on the same classpath with a `.properties` extension, using the wrong API will turn accented text into garbled characters (mojibake).

This lesson helps you clearly distinguish their purpose, decoding behavior, locale selection, fallback, lifecycle, and when to choose a `Reader` for reliable data handling on Java 17+.

## 2. Quick overview: Properties and PropertyResourceBundle

| Criterion | `Properties` with `load(InputStream)` | `PropertyResourceBundle` |
| --- | --- | --- |
| Java class | `java.util.Properties` | `java.util.PropertyResourceBundle extends ResourceBundle` |
| Primary purpose | Load a key/value configuration map from a stream | Represent a localized resource bundle from properties content |
| Reading API | `getProperty(key)`, `getProperty(key, default)` | `getString(key)`, `getObject(key)`, `ResourceBundle` APIs |
| File value type | `String` | `String`; does not automatically create `String[]` or numbers |
| `InputStream` decoding | **ISO-8859-1** per API contract | **UTF-8 since Java 9+**; defaults to ISO-8859-1 fallback if UTF-8 fails |
| `Reader` | `load(Reader)` uses characters already decoded by the Reader | Constructor `PropertyResourceBundle(Reader)` uses characters supplied by the Reader |
| Locale | No built-in locale selection mechanism | Can be used inside `ResourceBundle.getBundle(baseName, locale)` |
| Parent/fallback | Can specify `Properties defaults`; does not automatically look up files by locale | `ResourceBundle` system provides candidate locale/parent chains when using `getBundle` |
| Lifecycle | Object created and managed by code; `load` merges into the existing object | Bundle created on load; `ResourceBundle.getBundle` provides caching |
| When appropriate | Application configuration, general properties, reading arbitrary files | Messages, labels, and localized resources by language/region |

**Distinguishing two layers:** `PropertyResourceBundle` is an *implementation* of `ResourceBundle`. `ResourceBundle.getBundle(...)` is the *lookup and selection mechanism* for bundles by locale, which can create a `PropertyResourceBundle` from `.properties` or select a Java class-based bundle. If you call `new PropertyResourceBundle(inputStream)` directly, Java **does not infer locale or parent bundles from the filename alone**.

## 3. Same .properties format, different decoding rules

### 3.1. How Properties.load(InputStream) works

An `InputStream` supplies **bytes**. `Properties.load(InputStream)` interprets each byte using **ISO-8859-1 (Latin-1)** encoding; it does not inspect the file and guess UTF-8, nor does it change this behavior on Java 17/21 just because the JVM's `Charset.defaultCharset()` is UTF-8.

This means:

- Ordinary ASCII characters, such as `id=123` or `enabled=true`, read identically in UTF-8 and ISO-8859-1.
- A non-ASCII character encoded in UTF-8 can turn into **multiple wrong Latin-1 characters** when loaded with `load(InputStream)`.
- Characters that cannot be directly encoded in ISO-8859-1 must be represented as `\uXXXX` in files meant for this overload.
- `Properties.load(InputStream)` **does not accept a charset argument**; to read UTF-8 bytes directly, use `Properties.load(Reader)` with `InputStreamReader(..., StandardCharsets.UTF_8)`.

Illustrative example:

```java
Properties properties = new Properties();

try (InputStream input = Files.newInputStream(Path.of("config.properties"))) {
    properties.load(input); // Bytes are interpreted as ISO-8859-1.
}
```

This is a **snippet**, requiring imports from `java.io`, `java.nio.file`, and `java.util`; the filename is just an example path. If `config.properties` is saved as UTF-8 with literal Vietnamese text, the result can be wrong.

### 3.2. How PropertyResourceBundle(InputStream) works

On **Java 9 and later**, the constructor:

```java
new PropertyResourceBundle(inputStream);
```

attempts to decode bytes as **UTF-8**. By default, if `MalformedInputException` or `UnmappableCharacterException` occurs during UTF-8 decoding, it re-reads the data as **ISO-8859-1** for compatibility with legacy resource files. This is the JEP 226 behavior, not the behavior of `Properties.load(InputStream)`.

When the file is genuinely valid UTF-8, Vietnamese accents are preserved accurately. If a file is corrupted or has invalid bytes, the default mode can silently produce Latin-1 decoded results instead of throwing the error you expected. Therefore, standardize file encodings in your build pipeline.

You can force `PropertyResourceBundle` to use only one encoding with the **exact system property**:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 Main
```

Recognized values are `UTF-8` or `ISO-8859-1`. The option is read when **the `PropertyResourceBundle` class initializes**, so do not expect changing `System.setProperty(...)` between requests to alter decoding behavior. When set to `UTF-8`, invalid bytes can cause a decoding exception instead of fallback; when set to `ISO-8859-1`, files must be encoded accordingly or use `\uXXXX`.

**Do not confuse the property name:** it is `java.util.PropertyResourceBundle.encoding`; passing this flag has no effect on `Properties.load(InputStream)`.

### 3.3. The two Reader overloads: explicit encoding control

Both APIs have a `Reader` path:

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("messages_vi.properties"), StandardCharsets.UTF_8)) {
    Properties props = new Properties();
    props.load(reader);
}
```

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("messages_vi.properties"), StandardCharsets.UTF_8)) {
    ResourceBundle bundle = new PropertyResourceBundle(reader);
}
```

A `Reader` provides **already-decoded characters** instead of bytes. Selecting UTF-8 happens in `Files.newBufferedReader(...)`; the properties-loading APIs do not decode a second time. This is the explicit choice when you control the file and want to **specify UTF-8 at the read site**.

The snippets above are **standalone fragments inside a method**, requiring imports for `java.io.Reader`, `java.nio.charset.StandardCharsets`, `java.nio.file.Files`, `java.nio.file.Path`, `java.util.Properties`, and `java.util.ResourceBundle` or `java.util.PropertyResourceBundle`. The complete demo below provides a compilable and runnable program.

## 4. Java 17+ experiment reproducing the encoding bug without external files

Use a string containing characters outside Latin-1 such as `ế` and `ệ` to clearly distinguish decoding behavior. The string `"Xin chào"` has Vietnamese characters, yet `à` and `ò` alone fall inside Latin-1; if you write a poorly chosen test using only such characters, it might not expose the bug as expected when the input encoding is altered. Thus, the following example checks **the final value against the original string** rather than just printing garbled characters directly.

Create **`PropertyEncodingDemo.java`** saved as UTF-8:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.PropertyResourceBundle;

public class PropertyEncodingDemo {
    public static void main(String[] args) throws Exception {
        String expected = "Tiếng Việt";
        byte[] utf8 = ("greeting=" + expected + "\ncount=3\n")
                .getBytes(StandardCharsets.UTF_8);

        Properties fromBytes = new Properties();
        fromBytes.load(new ByteArrayInputStream(utf8));

        Properties fromReader = new Properties();
        fromReader.load(new InputStreamReader(
                new ByteArrayInputStream(utf8), StandardCharsets.UTF_8));

        PropertyResourceBundle bundleFromBytes =
                new PropertyResourceBundle(new ByteArrayInputStream(utf8));

        PropertyResourceBundle bundleFromReader =
                new PropertyResourceBundle(new InputStreamReader(
                        new ByteArrayInputStream(utf8),
                        StandardCharsets.UTF_8));

        System.out.println("Properties/InputStream OK: "
                + expected.equals(fromBytes.getProperty("greeting")));
        System.out.println("Properties/Reader OK: "
                + expected.equals(fromReader.getProperty("greeting")));
        System.out.println("Bundle/InputStream OK: "
                + expected.equals(bundleFromBytes.getString("greeting")));
        System.out.println("Bundle/Reader OK: "
                + expected.equals(bundleFromReader.getString("greeting")));
        System.out.println("Bundle count type: "
                + bundleFromBytes.getObject("count")
                        .getClass().getSimpleName());
    }
}
```

Compile and run with **JDK 17 or 21**, without passing any system property that changes encoding:

```bash
javac -encoding UTF-8 PropertyEncodingDemo.java
java PropertyEncodingDemo
```

**Stdout:**

```text
Properties/InputStream OK: false
Properties/Reader OK: true
Bundle/InputStream OK: true
Bundle/Reader OK: true
Bundle count type: String
```

Explanation:

1. `utf8` is created from `"Tiếng Việt"` in UTF-8, containing multi-byte sequences.
2. `Properties.load(InputStream)` decodes them as ISO-8859-1, so the string no longer equals `expected`.
3. `Properties.load(Reader)` receives the right characters because `InputStreamReader` specifies UTF-8.
4. `PropertyResourceBundle(InputStream)` on Java 17+ recognizes valid UTF-8 and returns the text verbatim.
5. `PropertyResourceBundle(Reader)` is also correct because the Reader already used UTF-8.
6. The value `count=3` is treated as a **String** by `.properties`-based bundles, not automatically converted into an `Integer`.

The example uses in-memory data so it does not depend on file paths, OS default encodings, or classpath packaging. `ByteArrayInputStream` holds no OS resources; for real files, use `try-with-resources` to close streams and readers.

**Reverse test:** if you replace `java PropertyEncodingDemo` with `-Djava.util.PropertyResourceBundle.encoding=ISO-8859-1`, `Bundle/InputStream OK` becomes `false` while both `Reader` paths remain `true`. This flag does not alter `Properties.load`'s behavior.

## 5. Properties: reading configuration files without automatic language selection

`Properties` is well suited for key/value configuration:

```properties
server.port=8080
feature.enabled=true
display.name=Demo
```

Example:

```java
Properties settings = new Properties();
try (Reader reader = Files.newBufferedReader(
        Path.of("app.properties"), StandardCharsets.UTF_8)) {
    settings.load(reader);
}

String port = settings.getProperty("server.port");
String fallback = settings.getProperty("unknown.key", "default");
boolean enabled = Boolean.parseBoolean(
        settings.getProperty("feature.enabled", "false"));
```

All values remain `String`. Converting types to `int`, `boolean`, or other types is a separate step; `NumberFormatException` can occur when parsing an invalid number.

**State differences:**

- `new Properties()` creates an empty table. Calling `load(...)` **adds/overwrites the keys found** into the existing table; it **does not automatically remove older keys not listed** in the new data.
- `setProperty(...)` and `getProperty(...)` update and read keys as `String`. Avoid misusing `put(...)` with non-String values even though `Properties` extends `Hashtable<Object,Object>`.
- `Properties` can take a **defaults** object via the `Properties(defaults)` constructor, but that is a developer-configured fallback and **does not automatically probe `messages_vi.properties` and `messages.properties`**.
- `load(InputStream)` and `load(Reader)` do not close the passed stream or reader; callers should manage their lifecycle with `try-with-resources`.

`Properties` options fit regular configuration. If you need `Locale`-dependent translations, consider `ResourceBundle` instead of hand-rolling file-selection logic.

## 6. PropertyResourceBundle: part of the ResourceBundle mechanism

### 6.1. ResourceBundle.getBundle locates files by locale

An application might organize files as:

```text
resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
```

If the files reside on the **classpath root**, `ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))` can select `messages_vi.properties` when `messages_vi_VN.properties` does not exist.

**File `messages.properties`**:

```properties
title=Default title
footer=Powered by Java
```

**File `messages_vi.properties`**:

```properties
title=Tiếng Việt
```

Create **`BundleLookupDemo.java`** in the same directory as the two properties files for a simple classpath run:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLookupDemo {
    public static void main(String[] args) {
        ResourceBundle messages = ResourceBundle.getBundle(
                "messages", Locale.forLanguageTag("vi-VN"));

        System.out.println("Locale: "
                + messages.getLocale().toLanguageTag());
        System.out.println("Title: " + messages.getString("title"));
        System.out.println("Footer: " + messages.getString("footer"));
        System.out.println("Title type: "
                + messages.getObject("title").getClass().getSimpleName());
    }
}
```

Compile and run with JDK 17+ in the directory containing **all three files**:

```bash
javac -encoding UTF-8 BundleLookupDemo.java
java BundleLookupDemo
```

Stdout:

```text
Locale: vi
Title: Tiếng Việt
Footer: Powered by Java
Title type: String
```

Because `messages_vi.properties` defines `title`, the bundle returns the Vietnamese text; `footer` is not declared in the Vietnamese file, so it is resolved from **the parent** `messages.properties`. The selected bundle has `getLocale()` equal to `vi` (different from the requested locale `vi-VN`). The files are saved in UTF-8, and on Java 17+ `PropertyResourceBundle`'s default loading path understands UTF-8.

Remember that `getBundle(...)` **is not an overload of `Properties.load(...)`**: it has candidate locale selection, fallback, and caching strategies. If a Java class `messages_vi` implementing `ListResourceBundle` is also on the classpath, the bundle-format selection strategy can affect the outcome; do not accidentally place resources with colliding base names. When running inside a JPMS-packaged module or a custom framework, resource paths and availability also depend on module/provider configuration.

### 6.2. Direct constructor does not create fallback automatically

On the other hand:

```java
try (InputStream in = Files.newInputStream(
        Path.of("messages_vi.properties"))) {
    PropertyResourceBundle direct = new PropertyResourceBundle(in);
    System.out.println(direct.getString("title"));
}
```

This is a **snippet**. It loads only the exact file passed in; it does not look for `messages.properties` next to it as a parent. Calling `direct.getString("footer")` when the file only has `title` throws `MissingResourceException`. By contrast, the `getBundle("messages", vi-VN)` version in the earlier example has a parent because `ResourceBundle`'s loader builds the corresponding bundle chain.

Do not write `new PropertyResourceBundle(...)` expecting a `_vi` filename suffix to trigger translation selection or parent lookup automatically. To get that behavior, use `ResourceBundle.getBundle`, or configure parent policies intentionally in a supported resource mechanism.

### 6.3. Return types and access errors

With a `.properties` resource:

```properties
retry.count=3
tags=red,green,blue
```

- `bundle.getString("retry.count")` returns `"3"`.
- `bundle.getObject("retry.count")` returns a `String` object, not an `Integer`.
- `bundle.getStringArray("tags")` throws `ClassCastException`, because `"red,green,blue"` is just a single string, not a `String[]`.
- `bundle.getString("not.existing")` throws `MissingResourceException` if the key is absent from the bundle and all of its parents.

If you need `String[]` or non-String object values, use a bundle source that supports those types, such as `ListResourceBundle`, or parse a clearly defined data format yourself. `Properties.load` does not turn `retry.count=3` into an integer either.

## 7. Properties syntax and Unicode escapes

Both APIs work with basic properties file syntax:

```properties
# Comment
language=vi
message: Xin chào
continued=Phần thứ nhất \
  phần thứ hai
escaped=Line 1\nLine 2
unicode=\u1ebf
```

Rules to understand:

1. `=` or `:` can separate keys and values; in some cases whitespace also acts as a separator. Use one consistent style for readability.
2. Lines starting with `#` or `!` (after optional leading whitespace) are comments.
3. A trailing backslash on a logical line continues it onto the next line. Avoid complex multi-line messages directly when presentation formatting needs explicit line breaks preserved.
4. The `\n` escape inside a value becomes a newline character when read; `\\` is a backslash; certain special characters in keys or values require escaping.
5. `\uXXXX` is a Unicode escape consisting of **exactly four hex digits**; for example, `\u1ebf` represents `ế`. Characters outside the BMP require a surrogate pair using the appropriate escape syntax. Do not write malformed escapes, as the parser can throw `IllegalArgumentException`.
6. An ISO-8859-1 file containing `unicode=\u1ebf` can still be loaded accurately by `Properties.load(InputStream)`, because the escape sequence consists of ASCII bytes before the parser converts it to Unicode.

**Distinguish two steps:** the charset (UTF-8/Latin-1) decodes **bytes into characters**; the properties parser then turns `\uXXXX`, `\n`, and separators into key/value pairs. Unicode escapes do not mean `Properties.load(InputStream)` supports direct UTF-8 decoding.

For ordinary Vietnamese content, using UTF-8 together with `Properties.load(Reader)` or `PropertyResourceBundle` on Java 9+ is much easier to author and review than escaping every accented character.

## 8. Java version compatibility and deployment consistency

| Environment | `Properties.load(InputStream)` | `PropertyResourceBundle(InputStream)` |
| --- | --- | --- |
| Java 8 | ISO-8859-1 | ISO-8859-1 (for standard InputStream loading) |
| Java 9+ | ISO-8859-1 | UTF-8 default; retries ISO-8859-1 if UTF-8 sequence is invalid |
| Java 17/21 | ISO-8859-1 | UTF-8 default with the compatibility mechanism above |
| Java 17/21 with `-Djava.util.PropertyResourceBundle.encoding=ISO-8859-1` | Still ISO-8859-1 | Uses ISO-8859-1 only |
| Java 17/21 with `-Djava.util.PropertyResourceBundle.encoding=UTF-8` | Still ISO-8859-1 | Uses UTF-8 only |

**Why does fallback matter?** An ISO-8859-1 file containing non-ASCII characters may contain bytes that are invalid in UTF-8 and trigger Latin-1 re-reading. However, a byte sequence that is genuinely Latin-1 **can coincidentally be valid UTF-8**, so automatic reading can still produce wrong output without throwing any error. Hence, a project should standardize and validate encoding during build/test rather than relying on guesswork.

Do not confuse this flag with `-Dfile.encoding=UTF-8`. `Properties.load(InputStream)` has a fixed ISO-8859-1 contract, and `PropertyResourceBundle` has its own policy. Changing the machine's default encoding does not override a parser with an explicitly specified encoding.

For repositories that still support Java 8, using a `Reader` with UTF-8 can give you manual control over reading properties. If relying on default `ResourceBundle.getBundle` loading on Java 8, ensure files and encodings follow that JDK's rules or configure an appropriate loading mechanism; do not copy Java 17's UTF-8 assumption back to Java 8.

## 9. When should you use which API?

**Scenario A — runtime configuration independent of user language.**

For example, `app.properties` holding port, timeout, feature flags, and endpoints. Use `Properties` (or your framework's configuration mechanism), reading with a `Reader` in the file's charset when you want UTF-8. There is no need to create a `ResourceBundle` just to read `server.port`.

**Scenario B — UI messages with multiple language versions.**

For example, `messages.properties`, `messages_vi.properties`, `messages_en.properties`. Use `ResourceBundle.getBundle("messages", userLocale)`. For `.properties` files, the bundle used is typically `PropertyResourceBundle`; a project may route through a provider depending on configuration. Check for missing keys, untranslated locales, fallback behavior, and the grammar of each message.

**Scenario C — reading one specific properties file by path while wanting the bundle API.**

You can use `new PropertyResourceBundle(Reader)` if you want `ResourceBundle`'s `getString`/`keySet` and supply the content yourself. However, it will not automatically select across multiple locale files just because the file has a `_vi` suffix.

**Scenario D — multi-typed data and complex structures.**

Both properties file APIs store values as `String`. Complex structures should use a well-defined schema, an appropriate parser/validator, or `ListResourceBundle` when object-typed resources are genuinely needed. Do not treat commas in a string as proof that it is a `String[]`.

## 10. Common bugs and how to diagnose them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `Properties.load(InputStream)` returns garbled Vietnamese | UTF-8 file decoded as ISO-8859-1 | Switch to `load(Reader)` and specify UTF-8 |
| `PropertyResourceBundle` reads a Latin-1 file with wrong characters | Bytes happen to be valid UTF-8, or mixed encodings | Standardize all files; consider a fixed encoding flag and tests |
| Works on Java 8, characters change on Java 17 | Default behavior change in `PropertyResourceBundle` since Java 9 | Inspect source encoding and loading path instead of blindly swapping parsers |
| `getString("unknown")` throws an exception | Key missing from bundle and parents | Check key name, base name, parent/fallback |
| `getProperty("unknown")` returns `null` | Key absent from `Properties`/defaults | Use the default-value overload or handle missing keys |
| `getStringArray("menu")` with `menu=A,B` | Properties files create `String`, not arrays | Use separate keys or a parser with explicit rules |
| `ResourceBundle.getBundle` picks the wrong language | Default locale, fallback, or candidate configuration misunderstood | Pass an explicit locale, inspect `getLocale()` and supported catalog |
| `new PropertyResourceBundle(file)` does not fall back | Direct constructor builds no parent chain | Use `ResourceBundle.getBundle` when a locale strategy is needed |
| After `Properties.load`, old keys remain | `load` does not clear the table before adding entries | Create a new `Properties` object if you want a full replacement |
| `-Dfile.encoding=UTF-8` set, yet the bug persists | `InputStream` overloads have fixed encoding rules | Pick the matching API/Reader instead of relying on default charset |
| `Integer.parseInt(getString(...))` fails | File value is a string not formatted as a number | Validate and report config errors; do not treat bundles as automatic type converters |
| Malformed `\uXXXX` Unicode escape | Fewer than four hex digits or mis-escaped text | Verify syntax and use explicit UTF-8 |

### Notes on resources, security, and testing

- **Close streams and readers** that you open using `try-with-resources`. Do not swallow `IOException` when reading files; if a file is required, report the path/source and cause.
- **Never store secrets directly** in translation resources or properties packaged in public applications. Resources are plain key/value maps, not secret stores.
- **Do not call `Locale.setDefault(...)` per request** to switch languages: the default locale is JVM-wide state and can affect multiple threads. Pass the user's locale to `getBundle`.
- **Separate file encoding from console encoding.** If the Java string is right while the terminal prints wrongly, check console encoding separately. Compare with `String.equals` or code points to determine whether the error happens at load time or output time.
- **Test in at least two environments** when upgrading the JDK or migrating legacy files: Vietnamese text with characters outside ASCII/Latin-1, a file with Unicode escapes, missing keys, bundle fallback, mixed-encoding files, and invalid input cases.
- **Test caching** if translations need to change while the application is running: `ResourceBundle.getBundle` caches bundles; updating a file on disk does not mean every lookup automatically picks up the new version. Design an explicit reload policy carefully with respect to versions already in use.

## 11. Self-check

**Question 1.** `messages_vi.properties` is saved as UTF-8 and contains `title=Tiếng Việt`. Why can `new Properties().load(InputStream)` return garbled text on Java 21?

**Answer:** Because `Properties.load(InputStream)` interprets bytes as **ISO-8859-1**, even on Java 21. Use `Properties.load(Reader)` with `InputStreamReader` or `Files.newBufferedReader` specifying UTF-8.

**Question 2.** With the same file, what encoding does `new PropertyResourceBundle(InputStream)` use by default on Java 17?

**Answer:** It tries **UTF-8** first. If specific decoding errors occur, by default it has a mechanism to re-read as ISO-8859-1 for compatibility, unless the `java.util.PropertyResourceBundle.encoding` system property forces a supported encoding.

**Question 3.** You call `new PropertyResourceBundle(input)` with the contents of `messages_vi.properties`, then look up a key present only in `messages.properties`. Will it automatically fetch it from the root file?

**Answer:** No. The direct constructor does not probe parent files by filename suffix. Locale-based fallback chains are established through a bundle selection mechanism such as `ResourceBundle.getBundle`.

**Question 4.** Do either of the two APIs load `quantity=3` directly as an `int` or `Integer`?

**Answer:** No. Values in properties files remain `String`. Type conversion is a separate application step.

**Question 5.** If you replace `Properties.load(InputStream)` with `load(Reader)` where the Reader uses an uncontrolled default charset, is accurate text guaranteed?

**Answer:** No. The Reader must decode using the file's actual charset. Explicitly specify `StandardCharsets.UTF_8` (or the confirmed source charset) for consistent results.

**Question 6.** If a configuration file contains only ASCII, why do both approaches usually give the same result?

**Answer:** Standard ASCII bytes map to the same character values in both UTF-8 and ISO-8859-1; differences emerge with non-ASCII Unicode data.

## 12. Summary and official documentation

- **`Properties.load(InputStream)` = ISO-8859-1**, always per the Java contract. To read a UTF-8 file with `Properties`, use `load(Reader)` with an explicit charset.
- **`PropertyResourceBundle(InputStream)` on Java 9+** defaults to UTF-8 decoding with possible Latin-1 fallback. You can control it via `java.util.PropertyResourceBundle.encoding`.
- **`Reader` handles the byte-decoding step**, while the properties parser interprets keys, values, and escapes; do not confuse these two layers.
- `Properties` suits configuration and merges into an existing table. `PropertyResourceBundle` serves i18n resources, and `ResourceBundle.getBundle` orchestrates file selection by locale, parent chain, and caching.
- Either way, values in `.properties` files remain **strings**, never automatically turning into numbers or arrays.

References:

- [Java SE 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
