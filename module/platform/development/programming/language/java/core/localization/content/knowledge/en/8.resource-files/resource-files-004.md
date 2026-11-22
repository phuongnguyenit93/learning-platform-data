# java.util.PropertyResourceBundle.encoding and When It Takes Effect

## 1. The problem to understand

In Java, a language resource bundle is typically stored as `.properties` files. If a file contains Vietnamese accents, Japanese, German, or other Unicode characters, the program must **correctly decode the file's bytes into characters** before using the values.

Since Java 9, `java.util.PropertyResourceBundle` reads `.properties` files using **UTF-8 first**, and in default mode retries with **ISO-8859-1** if certain UTF-8 decoding errors are detected. Java lets you force a reading mode using the **system property**:

~~~text
java.util.PropertyResourceBundle.encoding
~~~

The crucial detail to remember is that this value is **read and evaluated when the `PropertyResourceBundle` class is first initialized in the JVM**. Changing it afterward—even deleting or overwriting it with `System.setProperty(...)`—**does not cause the class's decoding mode to update**.

Startup command example:

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleEncodingDemo
~~~

When running this command, `-D...` is a **JVM** configuration placed before the main class name. It is not a property declared inside `Messages.properties`, it is not a `Locale`, and it is not re-read on every `ResourceBundle.getBundle(...)` call.

**Lesson goal:** understand the exact three decoding modes, when the configuration takes effect, its scope, and how to verify it with Java 17+ examples—thereby avoiding garbled characters (*mojibake*) and ineffective configurations in production.

## 2. Distinguishing bytes, charsets, Locale, and ResourceBundle

Consider a UTF-8 resource with the contents:

~~~properties
welcome=Xin chào
~~~

Before the application sees the Java string `"Xin chào"`, the file's UTF-8 byte sequence must be decoded. The character `à` in UTF-8 is represented by the two bytes `C3 A0`. If those two bytes are decoded separately as ISO-8859-1, the application sees wrong characters even though the source file itself is fine.

| Component | Role | Does it choose the `.properties` charset? |
| --- | --- | --- |
| `Messages_vi.properties` file | Holds bytes, keys, and translation values | The file must be saved in the appropriate charset |
| `Locale.forLanguageTag("vi-VN")` | Requests language/region to select a bundle | **No** |
| `ResourceBundle.getBundle(...)` | Finds and returns a resource bundle across locale candidates | Uses the corresponding resource-loading mechanism |
| `PropertyResourceBundle` | Reads key/value resources from `.properties` | **Yes**, when loaded via `InputStream` per Java 9+ rules |
| `java.util.PropertyResourceBundle.encoding` | Selects the decoding mode of `PropertyResourceBundle(InputStream)` | **Yes**, but locked in at class initialization |
| `Reader`'s `Charset` | Governs how the `Reader` turns bytes into characters | Applied when creating the `Reader` |
| Terminal/stdout charset | Governs how Java prints characters to the screen | Does not change how resources are read |

A correct `Locale` cannot fix a resource read with the wrong encoding. Likewise, a console failing to display Unicode does not prove the data was read wrongly; you must separate **reading the file**, **Java's internal representation**, and **writing to the console**.

## 3. The three modes of `PropertyResourceBundle(InputStream)` in Java 9+

For the standard `InputStream`-based resource loader:

| System property setting at class initialization | Decoding behavior | On invalid UTF-8 bytes |
| --- | --- | --- |
| **Unset**, or invalid value | Reads as **UTF-8**; on `MalformedInputException`/`UnmappableCharacterException`, re-reads from the start as **ISO-8859-1** | Retries ISO-8859-1 |
| `UTF-8` | Reads **only as UTF-8** | Raises a decoding error, **no fallback** to ISO-8859-1 |
| `ISO-8859-1` | Reads **only as ISO-8859-1** | Does not try UTF-8; bytes are decoded as Latin-1 |

Only two valid values are precisely defined by the Java documentation:

~~~text
UTF-8
ISO-8859-1
~~~

Strings such as `utf8`, `UTF8`, `Latin1`, `windows-1258`, or `CP1252` are not recognized values for this system property; **other values are ignored**, meaning the default rule is used. Do not use non-standard spellings and assume you have forced a reading mode.

### 3.1. Default: UTF-8 with fallback to ISO-8859-1

In default mode, Java attempts to decode as UTF-8. If an invalid UTF-8 byte sequence causes `MalformedInputException` or `UnmappableCharacterException`, `PropertyResourceBundle` can reset reading and retry the entire payload as ISO-8859-1. This is a compatibility mechanism for legacy Java 8-era resource bundles.

**Important caveat:** this fallback relies on *decoding errors*, not an algorithm that reliably detects a file's charset. A Latin-1 file whose bytes happen to be valid UTF-8 can be misinterpreted without triggering fallback. Therefore, do not rely on auto-detection to manage multilingual files long-term; standardize files on UTF-8.

### 3.2. Forcing `UTF-8`

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleEncodingDemo
~~~

This mode accepts only UTF-8. When an invalid UTF-8 byte sequence is encountered, reading fails instead of silently switching to ISO-8859-1. That is useful when you want to guarantee every resource bundle file in production is truly saved in UTF-8.

If you call the `new PropertyResourceBundle(InputStream)` constructor directly, the failure can be observed as an `IOException` or specific decoding exception. When loading via `ResourceBundle.getBundle(...)`, the error can surface through the bundle lookup/loading exception flow; do not assume every call produces the exact same root exception type, since resource selection and error handling also participate.

### 3.3. Forcing `ISO-8859-1`

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . BundleEncodingDemo
~~~

This mode is intended for environments deliberately maintaining Latin-1 byte resources. For files containing characters outside ISO-8859-1, use Unicode escapes such as `\u1EA1` per `.properties` syntax, or migrate resources to UTF-8 and run under a UTF-8 policy.

**Warning:** if a file is actually UTF-8 while ISO-8859-1 is forced, multi-byte Unicode characters are treated as multiple Latin-1 characters. The application can display garbled strings without throwing any exception. Changing `Locale` or clearing the cache will not fix choosing the wrong charset.

## 4. When it takes effect: locked in at class initialization

This is the core point of the lesson. The `PropertyResourceBundle` specification states that the system property is **read and evaluated when the class is initialized**.

~~~text
JVM starts up
      |
      +-- Receives -Djava.util.PropertyResourceBundle.encoding=...
      |
      v
PropertyResourceBundle is initialized for the first time
      |
      +-- Reads/evaluates the system property once
      +-- Locks in the decoding mode
      |
      v
Subsequent PropertyResourceBundle instances created
      |
      +-- Use the locked-in mode
      |
      v
System.setProperty("java.util.PropertyResourceBundle.encoding", ...)
      |
      +-- DOES NOT update the locked-in mode
~~~

**Practical consequences:**

1. Passing `-Djava.util.PropertyResourceBundle.encoding=...` **before the JVM runs application code** is the clearest way to ensure the class reads the intended setting.
2. When `PropertyResourceBundle` gets initialized may be triggered earlier by your own code or by a library/framework. You cannot always assume `main()` will touch it first.
3. `System.setProperty("java.util.PropertyResourceBundle.encoding", "UTF-8")` **can take effect only if the class has not yet initialized**. Because initialization order in large applications is hard to control, do not use it in place of JVM startup configuration.
4. Once the class is initialized, **changing or clearing the property has no effect** on the class's decoding mode.
5. Calling `ResourceBundle.clearCache()` can affect cached bundles, yet it **does not re-initialize the `PropertyResourceBundle` class**, so it does not make the JVM re-read the encoding property.
6. Each new JVM process has its own class initialization. To switch policies reliably, configure the option at startup and launch a new JVM.

### 4.1. Why is `System.setProperty(...)` inside a request handler inappropriate?

Bad design example:

~~~java
// Do not do this inside a request handler.
System.setProperty(
        "java.util.PropertyResourceBundle.encoding",
        "UTF-8"
);
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", Locale.forLanguageTag("vi-VN"));
~~~

This is an illustrative snippet requiring `java.util.ResourceBundle` and `java.util.Locale` imports. The flaw is not syntactic: a system property is a **global** configuration, and `PropertyResourceBundle` reads it once at initialization. If the class has already been used, `System.setProperty` cannot change the mode; if not, the application depends on fragile class-loading timing.

Specifically, never set different property values per user, per language, or per request. **Resource file charset** is a packaging and resource-loading policy, not a user localization preference.

### 4.2. How to configure at deployment

Set the JVM option directly in the launch command or in the JVM arguments of your launcher:

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -jar app.jar
~~~

In IDE, build, or container configurations, make sure this argument is passed to the **JVM running the application**. For instance, putting a property inside Spring Boot's `application.properties` **does not automatically turn it into a JVM system property before `PropertyResourceBundle` initializes**. `-D` goes before `-jar` or the main class name. For an already running JVM process, changing machine config or editing source files without restarting will not change the locked-in decoding mode.

## 5. Runnable example: a UTF-8 file and three startup modes

The following exercise uses Java 17+, running on the **classpath** in a dedicated demo directory. Create two files:

~~~text
demo/
├── BundleEncodingDemo.java
└── Messages_vi.properties
~~~

Save `Messages_vi.properties` as **UTF-8** (UTF-8 without BOM is recommended for tool consistency):

~~~properties
welcome=Xin chào Việt Nam
farewell=Tạm biệt
~~~

Create `BundleEncodingDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleEncodingDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");
        ResourceBundle messages =
                ResourceBundle.getBundle("Messages", requested);

        System.out.println("Requested: " + requested.toLanguageTag());
        System.out.println("Resolved: " + messages.getLocale().toLanguageTag());
        System.out.println(messages.getString("welcome"));
        System.out.println(messages.getString("farewell"));
    }
}
~~~

From the `demo` directory, compile:

~~~bash
javac -encoding UTF-8 BundleEncodingDemo.java
~~~

### 5.1. Running in default mode

~~~bash
java -cp . BundleEncodingDemo
~~~

With the file saved in UTF-8, output:

~~~text
Requested: vi-VN
Resolved: vi
Xin chào Việt Nam
Tạm biệt
~~~

`Resolved: vi` occurs because the demo has only `Messages_vi.properties` and no `Messages_vi_VN.properties`. That is **the locale of the selected bundle**, independent of the encoding used to read its values.

### 5.2. Forcing UTF-8 at startup

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleEncodingDemo
~~~

The output is still:

~~~text
Requested: vi-VN
Resolved: vi
Xin chào Việt Nam
Tạm biệt
~~~

Here the file is valid UTF-8, so default mode and forced UTF-8 mode both read it accurately. However, forcing UTF-8 makes an important difference if a file in the system contains **invalid bytes**: the application reports a decoding error instead of falling back to Latin-1.

### 5.3. Forcing ISO-8859-1 on a UTF-8 file

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . BundleEncodingDemo
~~~

The first two lines still report the locales as before; the Vietnamese text afterward can turn into garbled characters (*mojibake*), because UTF-8 bytes are decoded as Latin-1. **Do not** treat that garbled output as a fixed benchmark: multi-byte Unicode sequences can become control characters or special whitespace, and console rendering depends on the environment.

Verification should focus on the cause and on the correctness of the Java string rather than only looking at console screenshots. You can assert `messages.getString("welcome").equals("Xin chào Việt Nam")` to check whether decoding succeeded, provided the `.java` source was compiled with UTF-8.

## 6. Latin-1 bytes example: default mode falls back while strict UTF-8 fails

The following example constructs bytes directly in code that are valid ISO-8859-1 but **invalid** UTF-8, because byte `E9` stands alone. Thus no legacy file editor is needed.

Save as `LegacyBytesDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.PropertyResourceBundle;

public class LegacyBytesDemo {
    public static void main(String[] args) throws Exception {
        // A simulated .properties file: text=<byte E9> + newline.
        // E9 is the character é in ISO-8859-1, invalid on
        // its own in UTF-8.
        byte[] legacyLatin1 = {
                't', 'e', 'x', 't', '=', (byte) 0xE9, '\n'
        };

        try (InputStream input =
                     new ByteArrayInputStream(legacyLatin1)) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(input);
            System.out.println(
                    "Decoded correctly: "
                    + "é".equals(bundle.getString("text"))
            );
        }
    }
}
~~~

Run three **separate processes**:

~~~bash
javac -encoding UTF-8 LegacyBytesDemo.java

java -cp . LegacyBytesDemo

java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . LegacyBytesDemo

java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . LegacyBytesDemo
~~~

Interpreting the results:

| Run command | Expected result |
| --- | --- |
| Without `-D` | `Decoded correctly: true`, because the UTF-8 attempt fails and re-reads as ISO-8859-1 |
| Force `ISO-8859-1` | `Decoded correctly: true` |
| Force `UTF-8` | Throws a decoding error (such as `MalformedInputException`), **does not** print the success line |

Noticeably, all three runs use **the exact same program and byte array**, yet the JVM setting before class initialization leads to different outcomes. This is concrete proof of how the system property and fallback mode work.

Do not mutate the system property multiple times in a single JVM and call the constructor again to "test all three modes": that **does not properly test** the read-once mechanism. Use **three separate Java processes** as shown above.

## 7. `InputStream` vs. `Reader`: the true scope of the system property

`PropertyResourceBundle` has two important constructors:

~~~java
new PropertyResourceBundle(inputStream)
new PropertyResourceBundle(reader)
~~~

- With `InputStream`, the class must decode bytes, so the UTF-8/ISO-8859-1 policy and the system property apply.
- With `Reader`, characters **have already been decoded** by the `Reader`. The `Reader` constructor reads those characters; the system property `java.util.PropertyResourceBundle.encoding` **does not control the Reader's charset**.

### Example using Reader with an explicit charset

Save as `ReaderEncodingDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

public class ReaderEncodingDemo {
    public static void main(String[] args) throws Exception {
        byte[] raw = "text=Tiếng Việt\n"
                .getBytes(StandardCharsets.UTF_8);

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(raw),
                StandardCharsets.UTF_8
        )) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(reader);
            System.out.println(bundle.getString("text"));
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ReaderEncodingDemo.java

java -cp . ReaderEncodingDemo

java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . ReaderEncodingDemo
~~~

Both runs print:

~~~text
Tiếng Việt
~~~

Reason: `InputStreamReader(..., StandardCharsets.UTF_8)` already determined the charset before `PropertyResourceBundle(Reader)` received the data. This option allows a **custom** loader to read resources in a specific charset without depending on the `PropertyResourceBundle(InputStream)` system property. If a project customizes `ResourceBundle.Control.newBundle(...)` or uses its own file-reading mechanism, inspect **the actual loading path** rather than assuming the system property affects every `.properties`-reading library.

### `java.util.Properties.load(InputStream)` is a different API

An especially common mistake:

~~~java
Properties properties = new Properties();
try (InputStream input = Files.newInputStream(path)) {
    properties.load(input);
}
~~~

This is an **illustrative snippet inside a method**, requiring imports for `java.util.Properties`, `java.io.InputStream`, `java.nio.file.Files`, and `java.nio.file.Path` (with `path` already defined).

`Properties.load(InputStream)` still interprets bytes as **ISO-8859-1**, and characters outside Latin-1 require `\uXXXX` escapes. It **does not** switch to UTF-8 just because you run Java 17 or because `java.util.PropertyResourceBundle.encoding=UTF-8` is set.

By contrast, `Properties.load(Reader)` reads characters via a `Reader`, so you can write:

~~~java
try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
~~~

This is also an illustrative snippet inside a method, requiring `java.io.Reader` and `java.nio.charset.StandardCharsets` in addition to the `Properties`/`Files`/`Path` imports above. The charset is specified at `newBufferedReader`.

**Remember the distinction:**

| API | Decoding rule |
| --- | --- |
| `PropertyResourceBundle(InputStream)`, Java 9+ | UTF-8 default with ISO-8859-1 fallback; governed by the system property at class initialization |
| `PropertyResourceBundle(Reader)` | Uses the created `Reader`'s charset |
| `Properties.load(InputStream)` | ISO-8859-1 by API contract, independent of the property above |
| `Properties.load(Reader)` | Uses the `Reader`'s charset |
| `ResourceBundle.getBundle(...)` | Depends on the actual bundle loader; for properties files and the standard loader, involves `PropertyResourceBundle` |

Do not confuse resource decoding rules with locale selection in `ResourceBundle.getBundle(baseName, requestedLocale)`. Locale selection decides **which file** is found; charset decides **which characters that file's bytes** represent.

## 8. Differences between Java 8 and Java 9+

| Version / configuration | Reading `PropertyResourceBundle` from `InputStream` |
| --- | --- |
| Java 8, standard behavior | ISO-8859-1; characters outside Latin-1 usually require `\uXXXX` escapes |
| Java 9 and later | UTF-8 default, ISO-8859-1 fallback on decoding error |
| Java 9+ with `-D...encoding=UTF-8` | Uses UTF-8 only |
| Java 9+ with `-D...encoding=ISO-8859-1` | Uses ISO-8859-1 only |

This change was introduced via **JEP 226 — UTF-8 Property Resource Bundles**. For projects that still need to run on Java 8, check the build and actual resources: raw UTF-8 files with Vietnamese accents cannot be read properly by default Java 8 `PropertyResourceBundle` the way Java 17 does. One compatibility option is converting non-Latin-1 characters to Unicode escapes in legacy resources; if targeting only Java 17+, standardize bundles on UTF-8.

A Unicode escape looks like:

~~~properties
# \u00E9 represents the character é
word=caf\u00E9
~~~

The escape `\u00E9` uses only ASCII characters in the file, so it is read identically under both UTF-8 and ISO-8859-1. This is a compatibility option, not a requirement for every `.properties` file on modern JDKs.

## 9. Diagnosing garbled characters in practice

When accented translations break, verify in a testable order:

1. **Original bytes:** Are the file in the repository and the file packaged inside the JAR truly UTF-8? Does the build have a *resource filtering*, copy, encoding-conversion, or repackaging step?
2. **Loading path:** Does the application use `ResourceBundle.getBundle` with standard `.properties` bundles, or does it directly construct `PropertyResourceBundle(Reader)`, call `Properties.load`, or use a custom i18n library?
3. **JVM configuration:** Print `System.getProperty("java.util.PropertyResourceBundle.encoding")` to see how the JVM was configured, but **do not assume** modifying it at runtime will change a mode already locked in.
4. **Initialization timing:** Did any framework or library use `PropertyResourceBundle` before your application's property-setting logic ran? If so, the property has already been evaluated.
5. **Caching:** Resource bundles can be cached. Replacing a file or calling `ResourceBundle.clearCache()` can help reload content, but **never** forces the class to re-read the system property.
6. **Java String:** Compare the loaded value against the expected string, or inspect Unicode code points. If the Java string is right while the console renders wrongly, investigate terminal charset/font separately.
7. **Version compatibility:** Confirm the actual runtime JDK. Do not apply Java 17 rules when predicting an application still running on Java 8.
8. **Valid-UTF-8-yet-wrong-meaning possibility:** Do not assume a misread Latin-1 file will always throw an exception. Default mode falls back only on defined decoding errors.

### Diagnosing common symptoms

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Valid UTF-8 displays wrongly when ISO-8859-1 is forced | Wrong charset selected | Remove forced Latin-1, standardize file to UTF-8, restart JVM |
| Decoding error when UTF-8 is forced | Resource contains invalid UTF-8 bytes | Convert source file to UTF-8 or fix bytes; check packaging |
| `System.setProperty` was called but had no effect | `PropertyResourceBundle` was already initialized | Pass `-D` at JVM startup and restart |
| After `clearCache()`, still reads with old charset | Cache does not control the locked-in static setting | Fix startup config and start a new process |
| `Properties.load(InputStream)` still reads Latin-1 | That is `Properties`' contract | Use `Properties.load(Reader)` with an explicit charset |
| `Reader` always reads UTF-8 despite JVM forcing Latin-1 | Charset was decided by the Reader | Inspect where the Reader is created and which constructor is used |
| Java string is right, but console shows boxes/strange symbols | Output font or encoding | Check console, font, and output environment |

## 10. Design and testing rules

**Stable configuration:**

- Choose one consistent encoding, typically **UTF-8**, for all module resource files.
- If you want to catch misencoded files at load time, consider running Java 17+ with `-Djava.util.PropertyResourceBundle.encoding=UTF-8`.
- Pass the property at JVM startup and verify the actual JVM arguments of the application or container.
- Avoid changing `java.util.PropertyResourceBundle.encoding` via `System.setProperty` in business logic or per request.
- Do not treat `ResourceBundle.clearCache` as a way to refresh charset configuration.
- When using custom loaders or `Reader`, specify the charset explicitly where the Reader is created and test it directly.

**Useful test suite:**

1. Include at least one accented Vietnamese string and one non-Latin-1 character in a UTF-8 bundle.
2. Assert the string value returned by `getString` via actual Unicode comparison, not just console screenshots.
3. Launch **separate JVMs** for default, strict UTF-8, and ISO-8859-1 modes to verify behavior.
4. Include a case with Latin-1 bytes invalid in UTF-8 to verify default fallback and strict UTF-8 failure.
5. Verify the built and packaged file, not just the file in the source directory.
6. When supporting multiple Java versions, run integration tests on each target runtime.
7. If using caching or runtime resource reloading, test content refresh rules separately from startup encoding rules.

## 11. Self-check questions

1. In Java 17, what will `PropertyResourceBundle(InputStream)` do if no system property is set and the file contains invalid UTF-8 bytes? What changes when `UTF-8` is configured?
2. Why is calling `System.setProperty("java.util.PropertyResourceBundle.encoding", "ISO-8859-1")` after the application has already loaded a bundle not guaranteed to change how files are read?
3. If you call `ResourceBundle.clearCache()` and reload the file, is the encoding system property re-read from scratch? Why or why not?
4. Does setting `-Djava.util.PropertyResourceBundle.encoding=UTF-8` make `Properties.load(InputStream)` read UTF-8?
5. Why does `new PropertyResourceBundle(new InputStreamReader(stream, UTF_8))` not depend on the encoding property the way the `InputStream` constructor does?
6. A UTF-8 file displays wrongly when the app forces `ISO-8859-1`. Distinguish a resource byte-decoding error from a console lacking Unicode support.
7. If you must support both Java 8 and Java 17, what `.properties` storage approach or reading mechanism should you choose to avoid garbled characters?

**Remember:** In Java 9+, `PropertyResourceBundle(InputStream)` reads **UTF-8 by default** and falls back to **ISO-8859-1** on eligible decoding errors. The system property `java.util.PropertyResourceBundle.encoding` can force exactly `UTF-8` or `ISO-8859-1`, but it is **read only when the `PropertyResourceBundle` class initializes**. For reliable configuration, pass `-D` at JVM startup, manage resource files in UTF-8, and test the exact resource loading path.

### References

- [Java SE 17: PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) — encoding, both constructors, and when the system property is read.
- [Java SE 17: Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — distinguishing `load(InputStream)` and `load(Reader)`.
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226) — the Java 9 change and compatibility goals.
