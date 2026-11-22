# PropertyResourceBundle UTF-8 and the ISO-8859-1 Fallback Mechanism

When a Java application reads localization resources from `.properties` files, **which encoding the file is saved in** determines whether characters like `Tiếng Việt`, `café`, and `日本語` display accurately. Starting in **Java 9**, `java.util.PropertyResourceBundle` changed how it reads from an `InputStream`: it **prefers UTF-8** and, by default, **re-reads using ISO-8859-1 if a UTF-8 decoding error occurs**. This is a compatibility behavior for legacy bundles, not an exact detector for every encoding.

This lesson explains the rule, when fallback occurs, its limitations, how to control it with the `java.util.PropertyResourceBundle.encoding` system property, the difference between `InputStream` and `Reader`, runnable Java 17+ examples, and how to organize i18n resources to avoid garbled text.

## 1. Why do .properties files have encoding issues?

A `.properties` file is stored as **bytes** on disk; Java must convert those bytes into **Unicode characters**. Different character encodings can represent the same character with different byte sequences:

| Character | UTF-8 (hex) | ISO-8859-1 (hex) | Meaning |
| --- | --- | --- | --- |
| `A` | `41` | `41` | ASCII is identical in both encodings |
| `é` (U+00E9) | `C3 A9` | `E9` | One character, two encodings |
| `à` (U+00E0) | `C3 A0` | `E0` | Basic Vietnamese accents can be encoded differently |
| `ệ` (U+1EC7) | `E1 BB 87` | Cannot be represented directly | ISO-8859-1 does not cover all of Vietnamese |
| `日` (U+65E5) | `E6 97 A5` | Cannot be represented directly | UTF-8 supports every valid Unicode character |

If you read **byte `E9`** as UTF-8, it is not a valid standalone UTF-8 sequence; decoding can trigger a `MalformedInputException`. Yet byte `E9` is a valid character in ISO-8859-1: `é`.

Conversely, the bytes `C3 A9` are valid UTF-8 for `é`, and at the same time they are two valid ISO-8859-1 characters: `Ã©`. Therefore, **data that "can be read" is not always data read in its original encoding**. This point is critical when evaluating the fallback mechanism.

### Background of the change between Java 8 and Java 9+

In older Java versions, `.properties` bundles loaded via `PropertyResourceBundle(InputStream)` were traditionally read as ISO-8859-1; characters outside that charset had to be written as **Unicode escapes** like `\u1EC7`. [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226) introduced the **UTF-8 first, ISO-8859-1 fallback** mechanism in Java 9 for the `InputStream` reading path. As a result, with **Java 17+**, you can usually write Vietnamese directly in a `messages_vi.properties` file saved as UTF-8.

This change does not mean **every properties-reading API** defaults to UTF-8. You must distinguish the exact class and overload being used.

## 2. The rule of PropertyResourceBundle(InputStream)

With Java 17+ defaults and no encoding forced via system property, the processing flow can be visualized as follows:

```text
.properties bundle file (bytes)
          |
          v
PropertyResourceBundle(InputStream)
          |
          v
Try decoding the ENTIRE stream as UTF-8
          |
          +-- Valid -----------------> parse key=value using UTF-8
          |
          +-- MalformedInputException /
          |   UnmappableCharacterException
          v
Reset stream state before the attempt
          |
          v
Re-read the ENTIRE stream as ISO-8859-1
          |
          v
Parse key=value from the decoded characters
```

This is a **re-read of the stream**, not an operation that isolates a single bad character and converts a few bytes to another encoding. When UTF-8 fails, Java switches **the entire input** to ISO-8859-1. If a file mixes UTF-8 sections with old Latin-1 sections, the fallback can turn otherwise valid UTF-8 sections into garbled text.

**Three scenarios:**

1. Valid UTF-8 file: read once as UTF-8; ISO-8859-1 is **not** tried.
2. ISO-8859-1 file containing bytes invalid under UTF-8 (such as a lone `E9`): the UTF-8 attempt fails, and the stream is re-read as ISO-8859-1.
3. Legacy file whose bytes *happen to form valid UTF-8 sequences*: no UTF-8 error is raised, so **no fallback occurs**; the resulting value may differ from what the author intended to write.

In particular, ISO-8859-1 can decode every byte value from `00` to `FF`, so decoding bytes into characters does not guarantee semantically valid or linguistically accurate content. Beyond character decoding, the `.properties` parser still has its own key/value, escape, and Unicode-escape error rules; an `IllegalArgumentException` caused by a malformed `\u` escape is **not** a trigger to switch charsets.

## 3. Java 17+ example: verifying UTF-8 first and Latin-1 fallback

This example creates two `word=café` payloads **with the same text but different byte encodings** directly in Java, independent of any editor used to create files. A third payload illustrates the ambiguity when ISO-8859-1 bytes happen to be valid UTF-8.

Create the file **`PropertyEncodingDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

public class PropertyEncodingDemo {
    private static byte[] encode(String text, Charset charset) {
        return ("word=" + text + "\n").getBytes(charset);
    }

    private static void inspect(String label, byte[] bytes) {
        try (ByteArrayInputStream input =
                     new ByteArrayInputStream(bytes)) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(input);
            System.out.println(label + ": "
                    + bundle.getString("word"));
        } catch (IOException exception) {
            System.out.println(label + ": "
                    + exception.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        byte[] utf8 = encode(
                "café", StandardCharsets.UTF_8);
        byte[] latin1 = encode(
                "café", StandardCharsets.ISO_8859_1);
        byte[] ambiguous = encode(
                "cafÃ©", StandardCharsets.ISO_8859_1);

        inspect("UTF8", utf8);
        inspect("LATIN1", latin1);
        inspect("AMBIGUOUS", ambiguous);
    }
}
```

Compile and run on Java 17+:

```bash
javac -encoding UTF-8 PropertyEncodingDemo.java
java PropertyEncodingDemo
```

**Stdout in default mode** (without `-Djava.util.PropertyResourceBundle.encoding`):

```text
UTF8: café
LATIN1: café
AMBIGUOUS: café
```

Explanation of the mechanism, rather than just looking at the strings:

- `UTF8`: from `"café"`, produces the bytes `63 61 66 C3 A9`; valid UTF-8, so it decodes to `café`.
- `LATIN1`: from the same word, produces `63 61 66 E9`; the lone `E9` byte is invalid UTF-8, triggering an **ISO-8859-1 re-read** and producing `café`.
- `AMBIGUOUS`: the author intentionally encodes the string `cafÃ©` under ISO-8859-1. It also produces the bytes `63 61 66 C3 A9`, which are valid UTF-8, so Java reads it as `café`. The original string had different characters, yet **there was no decoding error to trigger fallback**.

The third case proves why you cannot use this fallback mechanism to reliably determine "which encoding a file belongs to." **Standardize all project bundles to UTF-8** rather than intentionally mixing old and new encodings.

> For real data files, inspect the source bytes; a value that looks reasonable when displayed does not prove the right charset was used. Legacy Latin-1 strings that are pure ASCII look identical under both encodings and reveal nothing about the original encoding either.

## 4. Forcing an encoding with java.util.PropertyResourceBundle.encoding

Java supports a **system property** with the exact name:

```text
java.util.PropertyResourceBundle.encoding
```

If set to exactly `UTF-8` or `ISO-8859-1`, `PropertyResourceBundle(InputStream)` **uses only the specified charset**. The UTF-8-then-fallback mode **will not run**.

Re-run the program from section 3 as **separate JVM processes**:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 PropertyEncodingDemo
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 PropertyEncodingDemo
```

**With `-D...=UTF-8`**, stdout:

```text
UTF8: café
LATIN1: MalformedInputException
AMBIGUOUS: café
```

On the `LATIN1` row, byte `E9` is invalid UTF-8, so a decoding exception is reported **without trying ISO-8859-1**. This behavior is useful when you want to catch files that do not conform to UTF-8.

**With `-D...=ISO-8859-1`**, stdout:

```text
UTF8: cafÃ©
LATIN1: café
AMBIGUOUS: cafÃ©
```

The bytes `C3 A9` in the UTF-8 payload are interpreted as the two characters `Ã©`. Because ISO-8859-1 accepts every byte, this reading mode does not automatically throw an error when encountering UTF-8 content.

| JVM startup configuration | Valid UTF-8 | Latin-1 containing invalid UTF-8 bytes | Fallback charset used? |
| --- | --- | --- | --- |
| Property not set | Reads UTF-8 | Retries ISO-8859-1 | Yes |
| `-Djava.util.PropertyResourceBundle.encoding=UTF-8` | Reads UTF-8 | Reports decoding error | No |
| `-Djava.util.PropertyResourceBundle.encoding=ISO-8859-1` | May be read as garbled text | Reads as Latin-1 | No |

Some important constraints:

- Java recognizes only the two exact values `UTF-8` and `ISO-8859-1` for this system property; any other value **does not select an arbitrary encoding**, and is ignored according to the specification.
- The property is **read during initialization of the `PropertyResourceBundle` class**. Changing or clearing the property with `System.setProperty(...)` after that point **does not alter** the locked-in configuration.
- Place `-D...` **before the main class name** on the `java` command line. Each command above must start a fresh JVM rather than alternating by changing the property mid-run in the same program.
- The system property applies JVM-wide to this `InputStream` bundle-reading path. Do not use it as a per-user encoding option.
- When migrating a project to standard UTF-8, you can force `UTF-8` in CI or test runs to uncover misencoded legacy sources. Assess existing data and resource loading paths before enabling it in production serving users.

### Why not use -Dfile.encoding instead?

`file.encoding` generally relates to the default charset of Java I/O and the runtime environment. It is **not** the switch that controls the UTF-8/ISO-8859-1 rule of `PropertyResourceBundle(InputStream)`. Use `java.util.PropertyResourceBundle.encoding` when you want to control this specific mechanism. In your own code creating an `InputStreamReader`, passing `StandardCharsets.UTF_8` explicitly is usually better than relying on the default charset.

## 5. InputStream vs. Reader: same class, two different responsibilities

`PropertyResourceBundle` has two important constructors:

```java
PropertyResourceBundle(InputStream stream)
PropertyResourceBundle(Reader reader)
```

- **`InputStream`:** the constructor receives **bytes**; `PropertyResourceBundle` is responsible for decoding using UTF-8-first / ISO-8859-1 fallback or the forced encoding system property.
- **`Reader`:** the constructor receives **already-decoded characters**; converting bytes to characters is the responsibility of the **caller-created Reader**. This constructor does not automatically retry ISO-8859-1.
- **Unicode escapes** like `\u00E9` are processed by the properties parser according to `.properties` syntax after the character stream is obtained. Because escapes consist only of ASCII bytes, they remain compatible between UTF-8 and ISO-8859-1 when written properly.

Explicit `Reader` example, file **`ReaderCharsetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

public class ReaderCharsetDemo {
    public static void main(String[] args) throws Exception {
        byte[] latin1 = "word=café\n".getBytes(
                StandardCharsets.ISO_8859_1);

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(latin1),
                StandardCharsets.ISO_8859_1)) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(reader);
            System.out.println(bundle.getString("word"));
        }
    }
}
```

```bash
javac -encoding UTF-8 ReaderCharsetDemo.java
java ReaderCharsetDemo
```

Stdout:

```text
café
```

Here the result is correct because **the caller chose ISO-8859-1 in `InputStreamReader`**. No "fallback" happens inside `PropertyResourceBundle(Reader)`. If the caller chooses the wrong charset, replacement characters or decoding errors can occur depending on the Reader's decoder configuration; the constructor does not detect "this file was originally Latin-1" to rescue the content.

The `Reader` path is appropriate when a program must read a source with a **known** encoding and needs control over the decoding step. When building a new system, prefer sources consistently saved in UTF-8 rather than guessing encodings via read errors.

## 6. Difference from java.util.Properties.load(InputStream)

The `.properties` extension does not guarantee that every Java API interprets bytes the same way:

| API | Input | Decoding rule |
| --- | --- | --- |
| `new PropertyResourceBundle(inputStream)` in Java 17+ | Bytes | UTF-8 first; defaults to ISO-8859-1 fallback on decoding error; a single charset can be forced via system property |
| `new PropertyResourceBundle(reader)` | Characters | The Reader decides byte decoding; does not use the `InputStream` retry mechanism |
| `new Properties().load(inputStream)` | Bytes | Per `Properties.load(InputStream)` API contract: ISO-8859-1, out-of-range characters use `\uXXXX` escapes |
| `new Properties().load(reader)` | Characters | The Reader decides decoding; the parser reads properties syntax over characters |

**Key point to remember:** JEP 226 changed how *property resource bundles* are read; it did not turn `Properties.load(InputStream)` into a default UTF-8 API. If a UTF-8 file containing Vietnamese accents is loaded with `Properties.load(InputStream)`, characters can become garbled without any exception being thrown.

The standalone example below demonstrates this difference. Save as **`PropertiesVsBundleDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.PropertyResourceBundle;

public class PropertiesVsBundleDemo {
    public static void main(String[] args) throws Exception {
        byte[] utf8 = "word=café\n".getBytes(
                StandardCharsets.UTF_8);

        Properties properties = new Properties();
        properties.load(new ByteArrayInputStream(utf8));

        PropertyResourceBundle bundle =
                new PropertyResourceBundle(
                        new ByteArrayInputStream(utf8));

        System.out.println("Properties: "
                + properties.getProperty("word"));
        System.out.println("Bundle: " + bundle.getString("word"));
    }
}
```

```bash
javac -encoding UTF-8 PropertiesVsBundleDemo.java
java PropertiesVsBundleDemo
```

Default stdout on Java 17+:

```text
Properties: cafÃ©
Bundle: café
```

Both receive **the exact same byte array**, yet their decoding contracts differ. If you want to use `Properties` with UTF-8, create an explicit `Reader`:

```java
// Code snippet inside a method that has the byte[] utf8 variable.
try (var reader = new java.io.InputStreamReader(
        new java.io.ByteArrayInputStream(utf8),
        java.nio.charset.StandardCharsets.UTF_8)) {
    java.util.Properties values = new java.util.Properties();
    values.load(reader);
    System.out.println(values.getProperty("word"));
}
```

This snippet prints `café` when `utf8` contains the example's bytes, though it is only a **fragment placed inside a method**, not a standalone Java file.

## 7. Applying with ResourceBundle.getBundle on the classpath

In typical applications, you do not call `new PropertyResourceBundle(InputStream)` directly. Instead, `ResourceBundle.getBundle(...)` locates the matching `.properties` resource on the classpath and loads it via the property bundle mechanism.

Example structure:

```text
i18n-demo/
├── BundleOnClasspathDemo.java
├── messages.properties
└── messages_vi.properties
```

File **`messages.properties`** (saved as UTF-8):

```properties
greeting=Hello
```

File **`messages_vi.properties`** (saved as UTF-8):

```properties
greeting=Chào bạn
```

File **`BundleOnClasspathDemo.java`**:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleOnClasspathDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", locale,
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES));
        System.out.println(bundle.getString("greeting"));
    }
}
```

Run **directly inside the directory containing all three files**:

```bash
javac -encoding UTF-8 BundleOnClasspathDemo.java
java -cp . BundleOnClasspathDemo
```

Stdout with files saved in UTF-8 on Java 17+:

```text
Chào bạn
```

`messages_vi.properties` is selected for `vi-VN` because a `messages_vi_VN.properties` file is not required to use the general Vietnamese bundle. `Control.FORMAT_PROPERTIES` selects only properties-file bundles; `getNoFallbackControl` prevents a fallback pass to **the JVM default locale** during bundle lookup, while still allowing the normal candidate/parent chain and root bundle.

**Distinguish two completely different "fallbacks":**

- **Locale/bundle fallback:** when no file exists for `vi-VN`, Java considers `vi` and then the root depending on bundle lookup rules. This is **resource lookup** logic, unrelated to charsets.
- **Charset fallback:** once a stream for a properties file has been opened, `PropertyResourceBundle` can **re-read the bytes as ISO-8859-1** if the UTF-8 attempt fails. This is **content decoding** logic for a single file.

Do not use garbled characters as a signal to switch to the root bundle or pick a different locale. Conversely, a properly selected locale bundle can still produce garbled text if the file was saved in the wrong encoding.

### Errors can be wrapped when reading via getBundle

With `new PropertyResourceBundle(InputStream)` directly, decoding exceptions under forced UTF-8 can surface as `MalformedInputException` or `UnmappableCharacterException`. When loading through `ResourceBundle.getBundle`, resource loading failures can be reflected during bundle lookup and appear in the **cause** of a higher-level exception or be affected by fallback candidates. Therefore, when investigating encoding bugs in real applications, inspect **the cause chain**, the selected bundle file, the classpath, and cache settings; do not assume every charset error in `getBundle` throws one single exception type directly.

## 8. Real-world cases: legacy accented Latin-1 data and mixed-encoding data

### True Latin-1 files

A French bundle from a legacy system might contain byte `E9` for `é`. When read under Java 17+ defaults, the UTF-8 attempt fails and falls back to ISO-8859-1, making the content **still look right** even though the file has not been converted to UTF-8. This is a compatibility mechanism and should not be taken as proof that the entire file repository has been standardized.

### Bytes valid under both encodings

If a legacy file contains the sequence `C3 A9` meaning Latin-1 "`Ã©`", Java will see valid UTF-8 representing "`é`" and **will not fall back**. The `AMBIGUOUS` example above demonstrates this behavior. Other byte sequences can turn into gibberish while the parser still runs without error.

### Files with sections in multiple encodings

Suppose the top of a bundle is UTF-8 and an older tool appended Latin-1 bytes at the end. One invalid UTF-8 byte near the end causes the parser to re-read **the entire file** as Latin-1. Result: the old Latin-1 portion may look right, while the UTF-8 portion turns into garbled text. To fix this, you must **convert the source file to a single encoding**, not add per-key fallback rules.

### Unicode escapes

A value such as:

```properties
greeting=caf\u00E9
```

contains only ASCII characters in the file, so it decodes identically under UTF-8 and ISO-8859-1 before the parser turns `\u00E9` into `é`. Unicode escapes are useful for compatibility with legacy tools, though not required for UTF-8 on Java 17+. If using escapes for non-BMP characters, represent them properly with a UTF-16 surrogate escape pair per `\uXXXX` syntax, not an arbitrary code point longer than four hex digits in a single escape.

## 9. Encoding governance and testing in projects

A reliable workflow for managing `messages*.properties` bundles:

1. **Standardize on UTF-8 as the source format** for all locale files. Configure editors and build pipelines to create/copy resources as bytes without unintended transcoding.
2. **Check bytes and UTF-8 validity** in CI for files that must conform. Do not infer encoding solely from filename suffixes or from `getBundle` succeeding without errors.
3. **Run a test suite in a separate JVM with `-Djava.util.PropertyResourceBundle.encoding=UTF-8`** to catch bundles that are invalid UTF-8. Results through `ResourceBundle.getBundle` are also affected by locale fallback and caching, so tests should load the exact resource being checked.
4. **Verify concrete Unicode values** such as `Chào bạn`, `Đặng`, `café`, and `日本語`. Having the right keys does not guarantee the right bytes or characters.
5. **Audit legacy sources:** identify which files are ISO-8859-1, convert bytes to UTF-8 with a tool using an explicit charset, review character diffs, and eliminate mixed encodings before enabling strict UTF-8 mode.
6. **Use a fresh process when changing the system property in tests:** the property is locked in at `PropertyResourceBundle` initialization; do not run test A then test B in the same JVM using `System.setProperty` expecting the constructor to switch modes.
7. **Test classpath and packaging:** `.properties` files must be at the right resource path, such as the resources root or matching package. If a file is missing from the JAR, the failure is a missing resource, not an encoding bug.
8. **Check the output environment:** a console without Unicode support can display text wrongly even when the Java string is correct. Separate **content decoding** bugs from **rendering** bugs by comparing Unicode strings in tests.

### Small tests that can be automated

With `PropertyEncodingDemo`:

| Mode | What to verify |
| --- | --- |
| Default | Both the UTF-8 source and the Latin-1 source with a single `E9` byte produce `café` |
| Force UTF-8 | The Latin-1 source with byte `E9` is rejected with a decoding error |
| Force ISO-8859-1 | The UTF-8 source `C3 A9` becomes `Ã©` |
| Default with ambiguous bytes | A legacy file whose bytes are valid UTF-8 **does not trigger fallback** |

These directly test the `InputStream` constructor to isolate encoding behavior. For application-level `ResourceBundle.getBundle` tests, also check **the resolved locale**, root/parent bundles, inherited keys, and caching.

## 10. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Assuming Java always reads `.properties` as ISO-8859-1 | Inaccurate for `PropertyResourceBundle(InputStream)` since Java 9 | Know the exact API, constructor, and Java version |
| Assuming every Latin-1 file is automatically detected | Some Latin-1 byte sequences are valid UTF-8 | Standardize on UTF-8 and validate bytes |
| Assuming fallback fixes only the failing character | The parser re-reads the **entire** stream as ISO-8859-1 | Never mix encodings in one file |
| Using `-Dfile.encoding=UTF-8` to force `PropertyResourceBundle` to reject Latin-1 | Not the dedicated property | Use `-Djava.util.PropertyResourceBundle.encoding=UTF-8` |
| Calling `System.setProperty` after `PropertyResourceBundle` has already been used | The class has already locked in its encoding configuration | Set it at JVM startup |
| Using `Properties.load(InputStream)` to read UTF-8 Vietnamese directly | That API still interprets bytes as ISO-8859-1 | Use `load(Reader)` with UTF-8 or the appropriate bundle API |
| Assuming `PropertyResourceBundle(Reader)` falls back automatically | Charset is the Reader's responsibility | Create the Reader with an explicit charset |
| Confusing bundle fallback with charset fallback | Misdiagnosing why text is wrong | Separate locale selection from byte decoding |
| Seeing `getString` return a value and assuming the text is right | The value may be mojibake | Assert exact Unicode strings and verify encoding |
| Testing `-D...` modes in the same JVM | The property is evaluated only at class initialization | Use a new JVM per mode |
| Thinking Unicode escapes are stored in a separate encoding | The parser processes escapes after decoding | Write escapes with valid `\uXXXX` syntax |
| Fixing only the console when source bytes are wrong | Input bugs and display bugs are two different layers | Check bytes, then Java strings, then the terminal |

## 11. Practice questions

**Exercise 1.** Create the bytes of `"greeting=café"` using `StandardCharsets.UTF_8` and `ISO_8859_1`. Use `new PropertyResourceBundle(InputStream)` to read both on Java 17+. Explain why both display properly by default and why that does not guarantee the charset was detected accurately.

**Exercise 2.** Run `PropertyEncodingDemo` in three separate JVMs: default, forced `UTF-8`, and forced `ISO-8859-1`. Record the `UTF8`, `LATIN1`, and `AMBIGUOUS` output lines; explain the `E9` and `C3 A9` bytes.

**Exercise 3.** Use `Properties.load(InputStream)` to read a UTF-8 byte array containing `é` and compare it with `PropertyResourceBundle(InputStream)`. Replace `Properties.load(InputStream)` with `Properties.load(Reader)` using `UTF_8` and verify the result.

**Exercise 4.** Create `messages.properties` and `messages_vi.properties` saved in UTF-8, then call `ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))`. Verify the Vietnamese text and separately analyze three possible causes if it fails: wrong UTF-8 file bytes, wrong bundle selected, or wrong console rendering environment.

**Key takeaway:** Java 17+ defaults to trying UTF-8 first and re-reading as Latin-1 on decoding errors; forcing `UTF-8` disables the retry; `Properties.load(InputStream)` always uses Latin-1; `Reader` uses the caller-chosen charset. When something breaks, identify the exact layer that introduced the discrepancy.

## 12. Official documentation

- [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226): compatibility motivation and the default change starting in Java 9.
- [JDK 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html): `InputStream`/`Reader` constructors, fallback rules, and the encoding system property.
- [JDK 21 — java.util.Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): `load(InputStream)` and `load(Reader)`.
- [JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): loading bundles from the classpath by locale.

## 13. Summary

**On Java 17+, `PropertyResourceBundle(InputStream)` prefers UTF-8; if a decoding error occurs, it re-reads the entire stream as ISO-8859-1.** This mechanism supports legacy compatibility but does not accurately detect every encoding, nor can it rescue misencoded bytes that happen to form valid UTF-8. You can force a single charset with `-Djava.util.PropertyResourceBundle.encoding=UTF-8` or `ISO-8859-1` **at JVM startup**, in which case no fallback occurs. `PropertyResourceBundle(Reader)` and `Properties.load(InputStream)` follow their own rules and do not inherit this behavior.

In new projects, save bundles consistently in **UTF-8**, verify actual bytes and Unicode content, configure strict encoding in CI where appropriate, and keep **charset fallback** distinct from **locale-based resource fallback**.
