# Choosing a Reader with an Explicit Charset to Control Resource File Encoding

In Java, `.properties` files typically hold UI labels, error messages, and localized text. When a file contains Vietnamese or other non-ASCII characters, an important question arises: **which charset is used to decode the file's byte sequence before Java reads the `key=value` pairs?**

If your application needs strict control over how resource files are decoded, create a `Reader` with an explicit charset and pass it to `PropertyResourceBundle(Reader)`. This approach is especially useful when integrating resource sets with pre-agreed encodings, handling legacy non-UTF-8 files, or reporting clear errors whenever data violates the promised encoding.

This lesson focuses on **choosing a Reader with an explicit charset** and its consequences during resource file loading. We also contrast it with the default behavior of `PropertyResourceBundle(InputStream)` on Java 17 so you avoid applying another API's rules by mistake.

## 1. Separating three steps: bytes → characters → resource

The path of a resource file is:

~~~text
.properties file on disk or on the classpath
             |
             | InputStream: byte sequence
             v
  Reader using the chosen charset
             |
             | Unicode characters in Java
             v
  .properties syntax parser
             |
             | key=value, comments, escapes
             v
       PropertyResourceBundle
             |
             v
    bundle.getString("title")
~~~

The `Reader` is responsible for converting **bytes into characters**. Next, `PropertyResourceBundle` handles **properties file syntax**, including `=` or `:` separators, whitespace, comments, escape characters, and `\uXXXX` sequences according to properties rules.

These two steps are independent:

- A UTF-8 file containing `title=Chào Việt Nam` must have its bytes decoded as UTF-8 first.
- An ASCII file containing `title=Ch\u00E0o` can be decoded without UTF-8 bytes for `à`; the properties parser later converts the Unicode escape into the character.
- Choosing the right charset **does not fix** a file with broken properties syntax; the parser can still throw an error on a malformed Unicode escape.
- Choosing the right charset **does not select a locale**. `Locale` is the mechanism for choosing a resource set, whereas `Charset` is the mechanism for decoding bytes.

For example, the string `"Đăng nhập"` after proper UTF-8 reading becomes a normal Java `String`. When calling `getString`, the original charset is no longer a parameter of key lookup.

## 2. Why specify the charset explicitly?

Suppose you have the file:

~~~properties
title=Chào Việt Nam
button.login=Đăng nhập
notice=Đặt lịch thành công
~~~

If the file was saved in UTF-8 but read as ISO-8859-1, bytes of accented characters can be interpreted as multiple different characters, producing **mojibake**. A classic example is `"Café"` turning into a garbled form like `"CafÃ©"` when UTF-8 bytes are decoded as Latin-1.

Changing `Locale.forLanguageTag("vi-VN")` or changing the font cannot fix this issue. The error already happened at **the byte → character boundary**.

With Java 17, choose `StandardCharsets.UTF_8` when files are standardized in UTF-8. Use `StandardCharsets.ISO_8859_1`, `windows-1252`, or another charset only when you **already know** the data source actually uses that encoding. Never guess a charset from a country or from a few accented words.

Example of reading an existing file with UTF-8:

~~~java
Path path = Path.of("i18n", "messages_vi.properties");

try (Reader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    PropertyResourceBundle bundle =
            new PropertyResourceBundle(reader);
    System.out.println(bundle.getString("title"));
}
~~~

This is an **illustrative snippet** inside a method that declares or handles `IOException`; it requires imports for `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, `java.io.Reader`, and `java.util.PropertyResourceBundle`. The file path is just an example; an application must use its actual resource location.

`Files.newBufferedReader(path, charset)` opens a `Reader` with the selected charset and closes it safely via `try-with-resources`. Calling `new PropertyResourceBundle(reader)` reads the data while constructing the bundle; once the constructor completes, the bundle object can be used even after the `Reader` is closed.

## 3. Accurately comparing loading approaches in Java 17

You cannot infer the charset of every API with "properties" in its name from a single rule.

| Reading approach | How is the charset decided? | Key takeaway |
| --- | --- | --- |
| `new PropertyResourceBundle(reader)` | Character data already decoded by `Reader` | Choose the charset right when creating the Reader |
| `new PropertyResourceBundle(inputStream)` | Java 17 prefers UTF-8 and can re-read as ISO-8859-1 when UTF-8 bytes are invalid per API conditions | Can be affected by a dedicated system property |
| `ResourceBundle.getBundle("messages", locale)` | Uses the appropriate bundle loading mechanism; for standard `.properties` bundles, `PropertyResourceBundle` rules apply | Also manages locale bundle lookup and parent chain |
| `properties.load(inputStream)` with `java.util.Properties` | Reads `.properties` as ISO-8859-1 per API contract | **Not the same** as Java 17 `PropertyResourceBundle(InputStream)` |
| `properties.load(reader)` | Uses characters supplied by the Reader | Charset is determined when creating the Reader |

### Default behavior of PropertyResourceBundle(InputStream)

Since Java 9, `PropertyResourceBundle(InputStream)` reads bytes as UTF-8 by default. If it encounters invalid or unmappable byte sequences in UTF-8, Java can **re-read as ISO-8859-1** to maintain compatibility with legacy resource files.

In Java 17, the system property `java.util.PropertyResourceBundle.encoding` can be set to `UTF-8` or `ISO-8859-1` to force the respective choice for the `InputStream` path. When set to `UTF-8`, invalid UTF-8 data throws an error without Latin-1 fallback. This property is read at class initialization; changing it while the application is running is not a reliable way to switch charsets between requests.

**The rule above applies to the `InputStream` constructor, not to how Java handles a `Reader`'s charset.** With `PropertyResourceBundle(Reader)`, whichever charset the Reader was created with is used to decode the bytes. That system property does not alter the charset of a Reader that has already been created.

A byte stream can happen to contain bytes that form valid UTF-8 even though a producer wrote them in another encoding. In that case, an automatic mechanism cannot deduce the original encoding with certainty. When a data contract mandates a specific charset, choosing an explicit Reader yields more predictable results.

### Do not confuse with java.util.Properties

On Java 17, `Properties.load(InputStream)` still interprets each byte as an ISO-8859-1 character and supports Unicode escapes in properties syntax. To use UTF-8 with `Properties`, pass a UTF-8 `Reader` into `Properties.load(Reader)`.

Just because both `Properties` and `PropertyResourceBundle` read the `.properties` format does not mean they share the same charset policy when given an `InputStream`.

## 4. Creating a Reader from InputStream or Path

### Approach A: a file with a path on the filesystem

When working with a file on disk via a `Path`, use:

~~~java
try (Reader reader = Files.newBufferedReader(
        Path.of("config", "labels.properties"),
        StandardCharsets.UTF_8)) {
    PropertyResourceBundle labels =
            new PropertyResourceBundle(reader);
    String title = labels.getString("title");
}
~~~

This pattern fits tools that import translations from directories, resource-validation CLI commands, or configuration files outside the classpath. `Files.newBufferedReader` already returns a `BufferedReader`; there is no need to wrap it in another `BufferedReader` just because the constructor accepts `Reader`.

### Approach B: a resource inside the classpath

If the file is packaged inside a JAR or placed under `src/main/resources`, `Path.of("...")` may not point to the right runtime location. Use `ClassLoader.getResourceAsStream` to obtain bytes:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
if (loader == null) {
    loader = MyApplication.class.getClassLoader();
}

try (InputStream input =
        loader.getResourceAsStream("i18n/messages_vi.properties")) {
    if (input == null) {
        throw new FileNotFoundException("Missing resource");
    }
    try (Reader reader =
            new InputStreamReader(input, StandardCharsets.UTF_8)) {
        PropertyResourceBundle bundle =
                new PropertyResourceBundle(reader);
        System.out.println(bundle.getString("title"));
    }
}
~~~

This is an **illustrative snippet inside a declared class named `MyApplication`** with imports for `java.io.*`, `java.nio.charset.StandardCharsets`, and `java.util.PropertyResourceBundle`. Adjust the resource path and class-loader choice to match your application architecture; `getResourceAsStream` can return `null` when the file is not found. With JPMS named modules, follow the module's resource packaging and opening rules.

`getResourceAsStream` makes no guarantee about what charset the resource uses; it only supplies bytes. It is `new InputStreamReader(input, StandardCharsets.UTF_8)` that expresses the decoding decision.

### Approach C: legacy Latin-1 resource sets

If you know for certain that `labels_legacy.properties` was created in ISO-8859-1, use:

~~~java
try (Reader reader = Files.newBufferedReader(
        Path.of("legacy", "labels_legacy.properties"),
        StandardCharsets.ISO_8859_1)) {
    PropertyResourceBundle legacy =
            new PropertyResourceBundle(reader);
}
~~~

**Do not use this for modern UTF-8 files** because it corrupts many Unicode characters. ISO-8859-1 also cannot directly represent many Vietnamese letters; legacy files may contain `\uXXXX` sequences that the properties parser decodes after the Reader processes bytes.

## 5. Standalone Java 17+ example: three decoding modes and malformed data

The following program constructs bytes in memory so it does not depend on OS, console config, or external files. It demonstrates:

1. Selecting UTF-8 for UTF-8 data preserves the Unicode string.
2. Reading the same UTF-8 bytes as ISO-8859-1 produces a **different** string.
3. Selecting ISO-8859-1 for legacy Latin-1 data gives the right result.
4. Creating a `CharsetDecoder` with `CodingErrorAction.REPORT` catches invalid UTF-8 bytes.

Create **`ReaderCharsetDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;
import java.util.TreeSet;

public class ReaderCharsetDemo {
    static PropertyResourceBundle load(
            byte[] bytes, Charset charset) throws IOException {
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), charset)) {
            return new PropertyResourceBundle(reader);
        }
    }

    static PropertyResourceBundle loadStrictUtf8(
            byte[] bytes) throws IOException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), decoder)) {
            return new PropertyResourceBundle(reader);
        }
    }

    public static void main(String[] args) throws IOException {
        String vietnamese =
                "title=Chào Việt Nam\nbutton=Đăng nhập\n";
        byte[] utf8 = vietnamese.getBytes(StandardCharsets.UTF_8);

        PropertyResourceBundle correct =
                load(utf8, StandardCharsets.UTF_8);
        PropertyResourceBundle wrong =
                load(utf8, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 title correct: "
                + correct.getString("title").equals("Chào Việt Nam"));
        System.out.println("Wrong charset differs: "
                + !wrong.getString("title").equals("Chào Việt Nam"));
        System.out.println("Keys: "
                + new TreeSet<>(correct.keySet()));

        String latin1 = "title=Café\n";
        PropertyResourceBundle legacy = load(
                latin1.getBytes(StandardCharsets.ISO_8859_1),
                StandardCharsets.ISO_8859_1);
        System.out.println("Latin-1 title correct: "
                + legacy.getString("title").equals("Café"));

        try {
            loadStrictUtf8(new byte[] {
                    't', 'i', 't', 'l', 'e', '=',
                    (byte) 0xC3, (byte) 0x28
            });
            System.out.println("Malformed UTF-8 rejected: false");
        } catch (MalformedInputException ex) {
            System.out.println("Malformed UTF-8 rejected: true");
        }
    }
}
~~~

Compile and run commands with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ReaderCharsetDemo.java
java ReaderCharsetDemo
~~~

Stdout verified against the corresponding Java program:

~~~text
UTF-8 title correct: true
Wrong charset differs: true
Keys: [button, title]
Latin-1 title correct: true
Malformed UTF-8 rejected: true
~~~

**Output explanation:**

- The string `"Chào Việt Nam"` is encoded as UTF-8 and passed through `InputStreamReader(..., UTF_8)`; `PropertyResourceBundle(Reader)` reads the exact value. `equals` returns `true`.
- The same bytes decoded as ISO-8859-1 produce a different string; `equals` against the original is `false`, so `Wrong charset differs` prints `true`.
- `keySet()` returns the bundle's key set; `TreeSet` makes the `button`, `title` ordering deterministic.
- The in-memory Latin-1 payload containing `Café` is encoded and decoded with the same charset, preserving it intact.
- The byte sequence `0xC3 0x28` is invalid UTF-8. The strict decoder throws `MalformedInputException`, which the program catches and prints `true`.

The program is a standalone Java file requiring no external libraries. `-encoding UTF-8` tells the compiler **the encoding of the Java source file itself**; it does not set the charset for `InputStreamReader`. The resource's charset remains whatever value is passed in code.

## 6. Distinguishing charset selection from malformed-byte policy

Two related but distinct questions:

- **Which encoding should bytes be read as?** Choose the `Charset` when creating the Reader.
- **What should happen when bytes cannot be validly decoded?** Choose `CodingErrorAction` on `CharsetDecoder`.

With `new InputStreamReader(stream, charset)`, the default decoder can **replace** malformed byte sequences with a replacement character instead of throwing an error right away. For translation data requiring strict validation, silent replacement can let corrupted translations slip into production.

Use an explicit `CharsetDecoder` to catch errors:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(stream, decoder)) {
    PropertyResourceBundle bundle =
            new PropertyResourceBundle(reader);
}
~~~

This is an **illustrative snippet** where `stream` is an already-opened `InputStream`; import `java.io.*`, `java.nio.charset.*`, and `java.util.PropertyResourceBundle`. With `REPORT`, invalid bytes can cause `MalformedInputException` or `UnmappableCharacterException`, both of which should be handled according to your data contract.

However, **a strict decoder does not prove you picked the right charset**. A byte sequence can be valid under multiple charsets while carrying different meanings; under ISO-8859-1, every byte represents a character. To detect choosing the wrong encoding, you need authoritative source metadata (configuration, interface contract, metadata, or migration workflow), combined with assertions on expected strings.

The `Reader` returned by `Files.newBufferedReader(path, charset)` reports malformed bytes according to its API contract; whenever you need exact `REPORT`/`REPLACE`/`IGNORE` control, build your own `CharsetDecoder`.

### Handling errors at the right layer

| Error | Where it occurs | Interpretation |
| --- | --- | --- |
| `NoSuchFileException` | Opening a file on disk | Path does not exist |
| `IOException` | I/O or strict decoder failure | File unreadable / malformed byte data |
| `IllegalArgumentException` on malformed Unicode escape | `.properties` parser | Invalid resource syntax |
| `MissingResourceException` from `getString` | Key lookup | Key absent in bundle and parent chain |
| `ClassCastException` from `getString` | Looking up a non-`String` value | Resource type mismatches the API |

Do not lump every exception together as "missing translation." Wrong encoding, missing file, missing key, and broken syntax each have different fixes.

## 7. Reader and ResourceBundle.getBundle(): an important limitation

Constructing directly:

~~~java
PropertyResourceBundle bundle =
        new PropertyResourceBundle(reader);
~~~

creates only **a single bundle from the supplied character source**. It **does not run the Locale candidate selection algorithm** performed by:

~~~java
ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"));
~~~

Specifically, if you manually open `messages_vi_VN.properties` and call the `Reader` constructor, that object does not know that `messages_vi.properties` and `messages.properties` also exist to provide undefined keys. Do not assume missing keys will automatically fall back to a parent bundle.

If an application only needs to read a single file with a special charset, the `Reader` constructor is a simple choice. If the application needs **automatic locale selection, parent chains, and caching**, keep the `getBundle` mechanism and design charset loading to fit into it.

### When a custom Reader is needed inside the getBundle flow

In applications running on the **classpath / unnamed module**, you can customize `ResourceBundle.Control.newBundle` to open the stream for each candidate bundle, wrap it in `InputStreamReader(stream, chosenCharset)`, and construct `PropertyResourceBundle(reader)`. `getBundle` still organizes the parent chain across candidate locales and the Control policy.

Visualizing the flow:

~~~text
ResourceBundle.getBundle(baseName, locale, control)
           |
           | selects candidate locales, resource names
           v
control.newBundle(...):
           |
           | opens InputStream for the candidate
           | creates Reader with the required charset
           | new PropertyResourceBundle(reader)
           v
ResourceBundle manages the parent chain and cache per Control
~~~

This is a **mechanism diagram**, not standalone Java code. When implementing `Control.newBundle`, properly handle `format`, `loader`, the `reload` flag, URL connection/caching, and stream closing; do not load one fixed resource for every candidate expecting `getBundle`'s fallback to still work properly.

**Module limitation:** `ResourceBundle.getBundle` overloads that take `ResourceBundle.Control` are not supported in named-module contexts under the Java 17 contract and can throw `UnsupportedOperationException`. With JPMS named modules, consider an appropriate resource bundle provider/module mechanism rather than copying a classpath `Control` pattern without checking.

### Do you need a custom Control just to read UTF-8?

On Java 17, standard `PropertyResourceBundle(InputStream)` **already prefers UTF-8**. If all resources are standardized on UTF-8, applications usually do not need a custom `Control` just to support Unicode characters. Build a custom `Reader` loading path only when you have a specific requirement such as a different charset, custom decoder policy, custom resource source, or preventing automatic encoding fallback.

Whichever approach you choose, test the actual `getBundle` execution path in your deployed build to verify Vietnamese text, locale selection, key fallback, and resource caching behave as expected.

## 8. Real-world properties file example and testing checklist

A Gradle or Maven project typically places resources under `src/main/resources`:

~~~text
src/main/resources/
  i18n/
    messages.properties
    messages_vi.properties
    messages_vi_VN.properties
~~~

Example `i18n/messages_vi.properties` saved in UTF-8:

~~~properties
title=Chào mừng
button.login=Đăng nhập
message=Bạn có {0} thông báo
~~~

When reading this file directly from the classpath with a UTF-8 Reader, use:

~~~java
try (InputStream input = MyApplication.class.getClassLoader()
        .getResourceAsStream("i18n/messages_vi.properties")) {
    if (input == null) {
        throw new FileNotFoundException("Missing messages_vi.properties");
    }
    try (Reader reader =
            new InputStreamReader(input, StandardCharsets.UTF_8)) {
        PropertyResourceBundle bundle =
                new PropertyResourceBundle(reader);
        System.out.println(bundle.getString("title"));
    }
}
~~~

This is an **illustrative snippet** inside `MyApplication` with the necessary imports, not a standalone program. With the file above, `getString("title")` returns `Chào mừng`. This pattern reads `messages_vi.properties` on its own without linking `messages.properties` as a parent.

`{0}` in `message` is not substituted with input data by `PropertyResourceBundle`. If parameter formatting is required, combine `MessageFormat` with the appropriate `Locale`; that is a separate step from charset decoding. Do not use `String.format` expecting `{0}`-style placeholders to be replaced.

### Practical testing checklist

- Verify actual file bytes are saved in the committed encoding; editors and build tools must not silently transcode them.
- Include Vietnamese strings with rich diacritics, such as `Đăng nhập`, `Tạm biệt`, and `Ưu đãi`, to catch wrong decoding.
- Verify round-trips or compare against **expected Unicode strings** after `getString`, rather than just eyeballing output.
- Test missing-file errors; for classpath loading, handle `getResourceAsStream == null`.
- Test invalid UTF-8 bytes and verify whether raising an error or replacing matches the design.
- Check `.properties` syntax, especially backslashes, `\uXXXX` Unicode escapes, `=`, `:`, and whitespace.
- If using `getBundle`, also test locale fallback, inherited keys, `baseName`, resource packaging, and caching.
- For legacy resources, verify their exact charset and migration path to UTF-8, avoiding loading the same file with two different encodings depending on the environment.

## 9. Common mistakes and how to avoid them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `InputStreamReader(stream)` without specifying a charset | Can depend on the environment's default charset, especially on Java 17 | Pass `StandardCharsets.UTF_8` or the committed charset |
| Using `Locale` to guess the charset | Data is decoded wrongly even when the locale is right | Charset is independent of language/region |
| Assuming `Properties.load(InputStream)` and `PropertyResourceBundle(InputStream)` behave identically | Confuses ISO-8859-1 and UTF-8 policies | Follow each Java 17 API's exact contract |
| Using ISO-8859-1 to read a UTF-8 file | Accented characters become garbled | Standardize on UTF-8 and pass the matching Reader |
| Relying on the `InputStream` constructor's Latin-1 fallback to detect the right encoding | Valid bytes in another encoding can still be misread | Use an explicit encoding contract and test data |
| Using `InputStreamReader(stream, UTF_8)` thinking every bad byte throws an error | Default decoder can turn invalid bytes into replacement characters | Use a `CharsetDecoder` with `REPORT` when strictness is required |
| Creating `PropertyResourceBundle(reader)` manually and expecting parents from other locale files | Keys in parent bundles are not found | Use `getBundle` or build a controlled parent chain |
| Reading resources on disk with `Path` when packaged in a JAR | File cannot be found | Use class-loader or module resource APIs as appropriate |
| Failing to close the `Reader` | Descriptor/stream leaks | Use `try-with-resources` |
| Changing `java.util.PropertyResourceBundle.encoding` mid-runtime | Does not control Readers and may have no effect | Configure at startup or create a Reader with an explicit charset |
| Checking only that a key exists while ignoring its content | Mojibake is still returned by `getString` | Assert exact Unicode strings after loading |

## 10. Self-check questions

**Question 1.** A properties file saved in UTF-8 has `title=Đăng nhập`. Which API should you use to open it if strict UTF-8 decoding is guaranteed?

**Answer:** Use `Files.newBufferedReader(path, StandardCharsets.UTF_8)` or `new InputStreamReader(input, StandardCharsets.UTF_8)`, then pass the Reader into `new PropertyResourceBundle(reader)`. If strict detection of corrupted bytes is required, use a decoder configured with `CodingErrorAction.REPORT`.

**Question 2.** Why does `PropertyResourceBundle(InputStream)` on Java 17 usually read UTF-8 files properly without passing a charset, whereas `Properties.load(InputStream)` can produce garbled text?

**Answer:** The two APIs have different encoding contracts. Java 17 `PropertyResourceBundle(InputStream)` prefers UTF-8 with an ISO-8859-1 compatibility fallback; `Properties.load(InputStream)` uses ISO-8859-1.

**Question 3.** Why does reading a file with a UTF-8 Reader and constructing a `PropertyResourceBundle` directly not automatically inherit messages from `messages.properties`?

**Answer:** The `Reader` constructor loads only one bundle; it does not execute `ResourceBundle.getBundle`'s candidate-locale selection algorithm or establish a parent chain. Charset rules and bundle-fallback rules are two independent mechanisms.

**Question 4.** Does a charset-configured `Reader` cause `MessageFormat` to automatically substitute `{0}` in strings?

**Answer:** No. The Reader only decodes bytes; `PropertyResourceBundle` reads keys and values. To substitute parameters, use `MessageFormat` or another message formatter.

**Question 5.** A legacy Latin-1 file must be kept as-is until migration. Should you change `Locale.setDefault(Locale.US)` to read it properly?

**Answer:** No. `Locale.setDefault` does not change the charset for byte streams. Use a Reader with `StandardCharsets.ISO_8859_1` matching the file's contract and test it, then migrate the file to UTF-8 on schedule.

## 11. Conclusion and official documentation

When controlling resource file encoding, the reliable approach is to pick the **charset per the data contract**, create a `Reader` with that charset, read `.properties` via `PropertyResourceBundle(Reader)`, and verify the resulting Unicode text. For critical data, use a strict decoder so invalid bytes are never accepted silently. When automatic locale selection and parent resource chains are needed, test `ResourceBundle.getBundle` separately and customize the loading path only for concrete technical reasons.

References:

- [PropertyResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): `Reader` and `InputStream` constructors, encoding, and exceptions.
- [InputStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): charset and decoder selection.
- [Files.newBufferedReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): reading files with a specified charset.
- [Properties — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html): distinguishing `load(InputStream)` and `load(Reader)`.
- [ResourceBundle.Control — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): customizing bundle loading and limitations in named modules.

**Remember:** `Reader + Charset` determines how bytes are decoded, `PropertyResourceBundle` determines how key–value pairs are parsed, and `ResourceBundle.getBundle` determines how bundles are resolved by locale and parent chain. Controlling each layer properly keeps translations uncorrupted and behavior consistent across Java environments.
