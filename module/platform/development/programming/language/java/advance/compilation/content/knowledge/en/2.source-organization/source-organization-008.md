# Encoding, Unicode Characters, and Reproducibility When Reading Java Sources

During Java compilation, a `.java` file starts out as **a sequence of bytes**. The compiler must decode that byte sequence into Unicode characters, process Unicode escapes, parse tokens and syntax, and only then generate bytecode. If different machines decode the same file using different charsets, they can end up with different programs, or one machine can compile it while another reports an error. This is an issue of source code organization and build reproducibility.

After this lesson, you should be able to distinguish bytes, charsets, Unicode code points, and UTF-16 code units; properly configure the encoding for `javac` and build tools; recognize Unicode escape/normalization risks; and verify that a source is read consistently on development machines and CI.

## 1. From Source File Bytes to a Java Program

Conceptual flow:

```text
.java file (bytes on disk)
    -> decode using source charset, e.g. UTF-8
    -> sequence of Unicode characters
    -> translate Unicode escapes (\uXXXX) very early
    -> analyze characters, tokens, comments, and literals
    -> analyze syntax/types, generate .class
```

* **Unicode** defines characters and code points (for example, `U+1EC7` is “ệ”); Unicode itself is not a byte storage format.
* **UTF-8** encodes a code point using 1–4 bytes. ASCII characters use one byte; “ệ” uses three bytes; “😀” uses four bytes.
* **UTF-16** represents most common characters with a single 16-bit unit, but characters outside the Basic Multilingual Plane (such as “😀”) require two units, called a *surrogate pair*.
* **Charset** determines byte ↔ character mapping. If an editor saves UTF-8 while the compiler reads using Windows-1252, Latin-1, or another system charset, Vietnamese diacritics can become corrupted or compilation can fail.
* **Line ending** (LF or CRLF) is also bytes in the source file. It usually does not change the meaning of a Java program, but it changes the file's hash, error locations, and the output of text-processing steps.

For example, the string `"Việt 😀"` contains 6 code points, 7 UTF-16 code units, and 11 bytes when UTF-8 encoded. The three numbers measure three different things. `String.length()` counts UTF-16 code units, not code points or bytes.

## 2. Explicitly Specifying the Compiler's Input Charset

Use the following option when compiling directly:

```bash
javac -encoding UTF-8 -d out src/SourceEncodingDemo.java
```

`-encoding UTF-8` applies to **the source files that `javac` reads**. `-d out` only selects the class output directory; you need to create the `out` directory before running the command. The path to the source and the filename must match the corresponding `public class`.

Defaults depend on the version/environment: on JDK 17 and earlier, the default charset of platform-dependent APIs could follow the environment; starting in JDK 18, JEP 400 specifies UTF-8 as the default charset for most standard APIs. However, a reproducible build should **explicitly declare UTF-8** rather than leaving it to default charsets, IDE configuration, Gradle/Maven processes, or CI machines. The switch to UTF-8 as the default does not automatically fix files that were originally saved in another encoding.

In Gradle Groovy DSL (`build.gradle`):

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

In Maven (`pom.xml`):

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

This is configuration for *reading source code*. Other inputs such as resources, test fixtures, configuration files, or data produced by a code generator may need their own charset policy. With Maven, check the actual configuration of the compiler/resources plugins in the version used by the project. With Gradle, if generating Java source, ensure the generator also **writes UTF-8**.

Specifying the charset is not the same as specifying the Java version. For a stable build, you also need to lock/configure the JDK/toolchain, `--release` or `sourceCompatibility`/`targetCompatibility` when appropriate, dependencies, and related build parameters.

## 3. Unicode Escapes Are Processed Even Before Comments and String Literals

Java allows Unicode escape syntax of the form `\uXXXX`, where `XXXX` is four hex digits of a UTF-16 code unit. The escape translation step happens **very early, before recognizing tokens and comments** according to the lexical translation rules of the Java Language Specification.

The example below **illustrates a hazard**, not code you should copy into a project:

```java
// \u000a System.out.println("Dòng này có thể trở thành code!");
```

If the raw character sequence in the file is indeed a backslash followed by a valid `u000a`, the Unicode escape translation step creates a newline character; the part after it can break out of the `//` comment and become a Java statement. Therefore, **do not treat `\uXXXX` inside comments or literals as harmless text**. Sequences of backslashes are also subject to the language's *eligible backslash* rule, so you cannot mechanically substitute every `\u` sequence.

When a string literal needs to contain Unicode characters, it is usually easier to read if the characters are stored directly in a UTF-8 file, for example `"Tiếng Việt"`. Use escapes when there is a specific reason (control characters, ASCII text required, or auto-generated code). Java Unicode escapes `\uXXXX` represent individual **UTF-16 code units**, so code point `U+1F600` cannot be written directly as `\u1F600`; you must use the actual character, the appropriate escape, or an API such as `Character.toChars(0x1F600)`.

Do not confuse Unicode escapes compiled during source reading with escapes in data read at runtime. A CSV file containing the six characters `\u0041` remains six data characters until the program itself decides to interpret it.

## 4. Compilable and Testable Java 17+ Example

Save the file `src/SourceEncodingDemo.java` as **UTF-8 without BOM**:

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class SourceEncodingDemo {
    public static void main(String[] args) {
        String text = "Việt 😀";
        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));
        System.out.println("utf8Bytes=" + text.getBytes(StandardCharsets.UTF_8).length);

        String composed = "\u00E9";     // é: one code point
        String decomposed = "e\u0301";  // e + combining acute accent
        System.out.println("sameRaw=" + composed.equals(decomposed));
        System.out.println("sameNfc=" +
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                        .equals(composed));
    }
}
```

From the project directory, create `out` and run:

```bash
mkdir out
javac -encoding UTF-8 -d out src/SourceEncodingDemo.java
java -cp out SourceEncodingDemo
```

Exact stdout:

```text
utf16Units=7
codePoints=6
utf8Bytes=11
sameRaw=false
sameNfc=true
```

Explanation: “Việt” has four code points, the space has one, and the emoji has one. The emoji takes two UTF-16 code units and four UTF-8 bytes; the character “ệ” takes three UTF-8 bytes. The two strings “é” and “e” + combining acute accent may look the same, but `String.equals` compares sequences of UTF-16 code units, so it initially returns `false`. Normalizing both inputs into one Unicode form, such as NFC, allows comparison according to the intended rules. **The Java compiler does not automatically normalize all literals, names, and paths to NFC**.

The example only prints numbers and booleans so the result does not depend on the terminal's ability to display emoji. If printing Vietnamese or emoji directly, the program may produce the exact characters while the screen still displays them incorrectly due to terminal/font/output encoding settings; that is a separate issue from reading the `.java` file.

## 5. Reading Sources Programmatically and with the JavaCompiler API

When a source analysis tool, linter, or generator reads `.java` files as data itself, specify the charset in Java code rather than relying on the default charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadSourceUtf8 {
    public static void main(String[] args) throws Exception {
        Path path = Path.of(args[0]);
        String source = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println("codePoints=" +
                source.codePointCount(0, source.length()));
    }
}
```

This is a **standalone program** that should be saved in `ReadSourceUtf8.java` and passed an existing file path when run, for example:

```bash
javac -encoding UTF-8 ReadSourceUtf8.java
java ReadSourceUtf8 src/SourceEncodingDemo.java
```

The printed code point count depends on the actual contents of the input file, so there is no single fixed stdout for all files. `Files.readString(path, UTF_8)` decodes bytes into characters; if the bytes are invalid for UTF-8, the read operation reports an error instead of silently guessing another charset. `Files.readAllBytes(path)` is appropriate when comparing raw bytes or hashing files.

Tools integrating the compiler inside the JVM process can choose the charset of `StandardJavaFileManager`:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
try (StandardJavaFileManager manager =
         compiler.getStandardFileManager(
             null, java.util.Locale.ROOT,
             java.nio.charset.StandardCharsets.UTF_8)) {
    // Pass the manager to the compiler task and handle diagnostics here.
}
```

The snippet above is **illustrative code inside a method**, requiring imports for `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, and `javax.tools.StandardJavaFileManager` if used in practice; it is not a standalone runnable program. `ToolProvider.getSystemJavaCompiler()` can return `null` if the runtime environment does not have a system compiler. Choosing UTF-8 for the file manager helps the tool read sources consistently with `javac -encoding UTF-8`.

## 6. Unicode Normalization, Filenames, and Reproducibility

Two strings with the same visual appearance can be represented by different code points. This affects:

- **Literals, data, and hashes:** NFC and NFD do not have the same UTF-8 bytes; the SHA-256 of the source file will differ even though the text looks similar.
- **Java identifiers:** the compiler evaluates characters according to language rules; it must not be assumed that visually similar strings are the same name. Naming identifiers with plain ASCII is a way to reduce differences across tools; literals and comments can still normally use UTF-8 with diacritics.
- **Filenames/paths:** operating systems and filesystems have different rules for case sensitivity, Unicode normalization, and name matching. The filename of a `public class` must match exactly; if the repository runs across platforms, prefer stable ASCII file/package names.
- **Character representation across external systems:** JSON, HTTP, databases, terminals, and resources may need their own charsets; output bytes do not necessarily match the bytes of the source file.

Do not automatically convert all sources to NFC just to "clean things up": a bulk normalization step can alter literals, comments, documentation, or bytes used for comparison; define a policy, inspect the diff, and apply intentionally. When comparing user-entered input strings, normalize both sides using the same policy before comparing.

## 7. Controlling Encoding in the Code Repository and CI

A practical workflow:

1. **Standardize encoding:** save all `.java` files as UTF-8 (preferably without BOM); configure editors/IDEs, formatters, generators, and `javac`/Gradle/Maven to the same standard.
2. **Lock the toolchain:** specify the JDK and target release; do not arbitrarily use JDK 17 on a developer machine and JDK 21 on CI while expecting identical `.class` files.
3. **Lock line endings:** choose a consistent LF/CRLF policy for the repository. You can configure `.gitattributes` as follows if the team agrees on storing LF:
   
   ```gitattributes
   *.java text eol=lf
   ```
   
   This is a Git checkout policy. Changing line endings can change file hashes even when Java interprets the same meaning.
4. **Validate input files:** detect files saved in the wrong charset, BOMs, invalid UTF-8 bytes, the replacement character U+FFFD, or unexpected Unicode normalization differences.
5. **Do not rely on the terminal:** clearly log the JDK name, compiler arguments, source charset, and source byte checksums when investigating discrepancies; inspect bytes and decoded content instead of just looking at text on screen.
6. **Re-run in a clean environment:** compile the same commit with the same JDK/toolchain, same dependencies, and configuration; compare errors/warnings, outputs, and appropriate hashes.

If a **byte-for-byte reproducible** build is required, encoding is only one condition. Timestamps in archives/JARs, packaging order, annotation processors, absolute paths, locale, timezone, environment variables, dependencies, and plugins can also affect the output. "Reading the same source" is not enough to conclude that every artifact will be identical.

## 8. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Check/Resolution |
| --- | --- | --- |
| `unmappable character for encoding ...` or `malformed input` during compilation | Source file bytes do not match the compiler charset | Check the actual file encoding, convert in a controlled way to UTF-8, compile with `-encoding UTF-8` |
| `illegal character` at the start of the file, possibly showing `\ufeff` | BOM or leading file character incompatible with the parser/tool | Inspect leading file bytes and save as UTF-8 without BOM; do not blindly delete other characters |
| Source runs but Vietnamese literals have corrupted diacritics | Text was saved/read with the wrong charset or mojibake occurred before compilation | Compare raw bytes in Git, editor encoding, and compiler charset; fix from an uncorrupted source copy |
| Console prints `?` or square boxes | Terminal output encoding/font | Check code points in the JVM, output charset, and font support; do not rush to edit the source file |
| `String.length()` differs from "visible character count" | `length()` counts UTF-16 code units | Use `codePointCount` if code points are needed; a *grapheme cluster* is a different concept and may require advanced Unicode handling |
| Strings look identical but `equals` is `false` | NFC/NFD or visually similar characters with different code points | Print code points in hex; normalize intentionally before comparing |
| Comment containing `\u000a` alters code | Unicode escape is translated before comment recognition | Audit escapes in sources/generators; do not place dangerous escapes in comments |
| Only CI fails with "file/class not found" | Different path name, casing, or filesystem Unicode normalization | Check the actual filename, `public class` name, and checkout behavior on the CI operating system |

When diagnosing, separate three layers: **bytes in Git**, **characters decoded by the compiler**, and **characters displayed in the console**. Fixing the wrong layer can mask symptoms on one machine while leaving builds on other machines broken.

## 9. Practice Exercise and Completion Criteria

Create the UTF-8 file `SourceEncodingDemo.java` above; run it with JDK 17+ using `javac -encoding UTF-8` and verify the exact five lines of stdout. Then try opening a **copy** in an editor with a mismatched charset, or changing the compiler configuration in a test environment: observe the decoding error/mojibake and inspect the cause from the raw bytes. Test NFC/NFD strings with `equals` and `Normalizer`, and verify the counts of UTF-16 code units, code points, and UTF-8 bytes.

Finally, run a build of the same commit in two environments with **the same JDK, the same UTF-8 setting, and the same configuration**. Compare the sources (bytes, encoding, line endings, hashes) before evaluating the artifacts. If the artifacts differ, continue investigating other build inputs; do not immediately blame Unicode for every difference.

**Guiding principle:** the Java version and charset must be explicitly configured; source bytes need to be stored, read, and checked consistently; Unicode escapes, normalization, and character display are distinct layers. Understanding each layer clearly helps pinpoint the exact cause when Java code compiles or displays properly on only one machine.
