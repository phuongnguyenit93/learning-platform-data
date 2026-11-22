# Configuring `javac -encoding` for Environment-Independent Compilation

## 1. The problem to solve

Java source code is a **byte file** on disk. To understand text like `café`, `tiếng Việt`, `đường dẫn`, or characters inside comments and string literals, the compiler must decode those bytes into Unicode characters before parsing syntax. If the source code is saved in UTF-8 yet `javac` reads it using a different character encoding, the program may:

- Report illegal character errors when bytes fail to decode.
- Compile **successfully yet with corrupted data**, such as the string `"café"` turning into `"cafÃ©"`.
- Fail only on one operating system or one CI runner while working fine on the author's machine.

Depending on the JDK release and environment, omitting `-encoding` can cause the compiler to use a different default encoding. The reproducible approach is **standardizing source file encoding and declaring that encoding explicitly to the compiler**.

Standard example when `.java` files are saved as UTF-8:

~~~bash
javac -encoding UTF-8 -d out src/EncodingDemo.java
~~~

`-encoding UTF-8` tells `javac`: “**read the Java source files** using UTF-8”. It is not an option for configuring console encoding, data files read by the application at runtime, or network protocols.

## 2. Mechanism: source bytes → Unicode → bytecode

The process involving source code encoding can be visualized as follows:

~~~text
.java file on disk
  bytes (e.g. UTF-8: c a f C3 A9)
          |
          | javac -encoding UTF-8
          v
Unicode character string: "café"
          |
          | Java parsing, type checking, code generation
          v
.class file containing the correct string constant
          |
          | JVM runs the program
          v
Application outputs / saves / transmits characters (with its own encoding rules)
~~~

Three layers to distinguish:

1. **Source file encoding:** which bytes editors, formatters, code generators, and Git store inside `.java`.
2. **Compilation encoding:** `javac -encoding <charset>` determines how input bytes are interpreted. It must match the file's actual encoding.
3. **Runtime and display encoding:** reading/writing files via `Files`, `InputStreamReader`, printing to a terminal, connecting to a database, HTTP... are separate operations. Setting `-encoding` at compile time does not configure them.

Once the compiler decodes source strings into Unicode accurately, string constant representation in bytecode is defined by the JVM specification, not the compiler's input text encoding option. Therefore you do **not** pass `-encoding UTF-8` to “convert `.class` format to UTF-8”.

## 3. When `-encoding` is omitted, what does Java use?

Default behavior should not be relied upon as a build contract:

| Environment | Points to Know |
| --- | --- |
| JDK 17 and earlier | Java's default charset typically depends on OS, locale, and JVM configuration; on some Windows machines it may be a legacy encoding, while on Linux it is usually UTF-8. |
| JDK 18 and later | JEP 400 standardizes UTF-8 as the **default charset** of common Java APIs, including `javac`'s default under standard configurations; environment or compatibility flags can still affect specific situations. |
| Building via Maven, Gradle, IDE, CI | Build tools may pass an explicit encoding or choose their own defaults. What must be verified is the **command/setting passed to the compiler**, not just the IDE's display setting. |

For example, given the exact same UTF-8 source code, one pipeline using JDK 17 on a machine defaulting to Windows-1252 and another using JDK 21 defaulting to UTF-8 can produce different outcomes if **encoding is not declared**.

For projects supporting multiple JDKs or running across multiple operating systems, configure `UTF-8` explicitly in compilation settings rather than implicitly relying on JDK version, locale, or personal machine settings.

**Do not confuse these options:**

- `-encoding UTF-8`: how to **read source file contents**.
- `--release 17`: restricts output APIs/language/bytecode to the Java 17 platform.
- `-source 17`: Java syntax level permitted.
- `-target 17`: output class-file version (does not itself restrict platform APIs).
- `-d out`: where `.class` files are saved.
- `-classpath` / `--class-path`: where dependent classes are found.
- `-J-Dfile.encoding=...`: passes a system property to the JVM running the compiler; this is not a clear, stable substitute for `-encoding` and should not be used to work around this problem.

For example, `javac --release 17 -encoding UTF-8 -d out src/EncodingDemo.java` combines two independent requirements: using Java 17 APIs/language and decoding sources with UTF-8.

## 4. Practice: one program, two decoding interpretations

Create `src/EncodingDemo.java`, saved in **UTF-8 without BOM**, with the contents:

~~~java
public class EncodingDemo {
    public static void main(String[] args) {
        String word = "café";
        System.out.println(word);
    }
}
~~~

Create the output directory and compile using JDK 17 or higher:

~~~bash
mkdir out
javac --release 17 -encoding UTF-8 -d out src/EncodingDemo.java
java -cp out EncodingDemo
~~~

Correct result:

~~~text
café
~~~

The letters `c`, `a`, `f` are ASCII; the character `é` has Unicode code point U+00E9. In **UTF-8**, `é` is represented by two hex bytes `C3 A9`. With `-encoding UTF-8`, the compiler recovers `é` as intended.

To observe the bug **without altering the content or bytes of `src/EncodingDemo.java`**, recompile into another directory while intentionally declaring the wrong encoding:

~~~bash
mkdir out-latin
javac --release 17 -encoding ISO-8859-1 -d out-latin src/EncodingDemo.java
java -cp out-latin EncodingDemo
~~~

Result with the UTF-8 source above:

~~~text
cafÃ©
~~~

Because ISO-8859-1 interprets the two bytes `C3 A9` as two characters `Ã` (U+00C3) and `©` (U+00A9), the corrupted string `cafÃ©` is embedded in bytecode. The compiler **does not necessarily report an error**: both characters are valid inside a Java string literal. That is a *mojibake* bug.

Both compilations can run side by side thanks to separate output directories `out` and `out-latin`. The `mkdir` command works in common shells; if the directory already exists, simply skip creating it. If your terminal cannot render Unicode properly, on-screen output may differ from the illustration even when the string in the class file is correct: see the diagnostic section below.

### When input bytes are genuinely invalid

If a source is UTF-8 yet a charset is selected where some bytes are unmappable, `javac` may report errors such as `unmappable character for encoding ...` or `illegal character`, depending on the charset and byte position. Never infer that **every** wrong encoding causes a compile error; the `café` case above proves the opposite.

Conversely, a file actually saved in ISO-8859-1 may need `-encoding ISO-8859-1` to be read correctly during a migration phase. Do not merely switch the flag to `-encoding UTF-8` while source bytes remain ISO-8859-1: **transcode the source file** to UTF-8 first, or keep declaring its actual encoding until conversion is complete.

## 5. Syntax and scope of the `-encoding` option

Common syntax:

~~~bash
javac -encoding UTF-8 -d out src/EncodingDemo.java
javac --release 17 -encoding UTF-8 -d out src/EncodingDemo.java
~~~

- The argument after `-encoding` is a Java-recognized charset name, such as `UTF-8`, `US-ASCII`, `ISO-8859-1`, `windows-1252`. Prefer `UTF-8` for readability and consistency.
- `-encoding` applies to **source files read by that compiler invocation**, including source files located via the source path configuration. When compilers/annotation processors generate and compile extra sources, inspect the processor's or file generator's own configuration to ensure emitted bytes match the encoding. Do not assume it converts every emitted artifact.
- `-encoding` is a **per-`javac`-invocation** setting, and does not rewrite existing legacy-encoded source files into UTF-8.
- One `javac` invocation uses one source encoding for all files it processes. If a project mixes UTF-8 and legacy-charset files, standardize all sources instead of expecting the compiler to guess each file's encoding individually.

With a package layout:

~~~text
project/
  src/
    demo/
      App.java
  out/
~~~

If `App.java` declares `package demo;`, the compilation command and runtime class name are:

~~~bash
javac -encoding UTF-8 -d out src/demo/App.java
java -cp out demo.App
~~~

`-d` and `package` govern class file paths; encoding does not alter naming rules or package structure.

## 6. Configuration in Maven

In a Maven project, instead of reminding everyone to type `javac -encoding`, declare the encoding directly in `pom.xml`:

~~~xml
<project>
    <!-- modelVersion, groupId, artifactId, version,
         and other elements of a full POM lie outside this excerpt. -->
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

This XML snippet illustrates **what to add to an existing POM**, not a minimal standalone POM. The Maven Compiler Plugin typically uses `project.build.sourceEncoding` as the encoding for Java sources unless overridden. The `maven.compiler.release` property instructs the compiler configuration to use `--release`.

To express it directly on the plugin, use the `encoding` configuration:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <encoding>UTF-8</encoding>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is a **snippet inside the `<project>` element of an existing POM**. In a project that already configures the plugin, update that configuration rather than creating two conflicting plugin declarations. Plugin settings may come from a parent POM, profiles, or command line; when diagnosing, inspect the effective POM and actual compiler invocation.

Example check after saving the configuration:

~~~bash
mvn clean compile
~~~

Note that `project.build.sourceEncoding` is used by several other Maven plugins as their default encoding (such as resource processing per plugin config), yet **`javac`'s `-encoding` serves only Java source code**. Specific resources, templates, or runtime data have their own encoding configurations and require explicit handling.

## 7. Configuration in Gradle

With Gradle Groovy DSL (`build.gradle`):

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

With Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

Both snippets are **build configuration**, not Java code passed directly to `javac`. They apply encoding to `JavaCompile` tasks, covering Gradle-managed Java source sets. Development setup must ensure Gradle uses a JDK supporting Java 17, such as via Java toolchains.

Run:

~~~bash
./gradlew compileJava
~~~

On Windows, use `gradlew.bat compileJava`. The Gradle wrapper must exist in the repository. When annotation processors, source generators, Kotlin, or custom compilation tasks exist, check the encoding of the **corresponding tool**; `options.encoding` applies to `JavaCompile` and does not automatically determine the encoding of every plugin.

## 8. Ensuring source files are genuinely UTF-8

Adding `-encoding UTF-8` is only right when files are actually saved as UTF-8. A sound workflow includes:

1. **Standardize the convention:** all `.java` files use UTF-8, preferring no BOM. Apply to both developer-written and generator-produced sources.
2. **Configure editors/IDEs:** set project and file encoding to UTF-8. If receiving legacy files, choose *convert encoding* to rewrite bytes; *reopen with encoding* only changes display decoding and may not save changes.
3. **Configure the build:** Maven/Gradle and `javac` scripts use explicit encoding.
4. **Verify in CI:** build on a clean machine with supported JDKs; include test strings containing accented characters to catch mojibake compilation errors.
5. **Inspect during transcoding:** review diffs of accented characters, comments, string literals, annotations, and text blocks; if source already contains `cafÃ©`, then even as valid UTF-8, the data is still wrong.

Java source files should normally be saved as **UTF-8 without BOM**. A BOM consists of marker bytes that can cause issues for some compiler versions or pipelines; no BOM is needed for `javac -encoding UTF-8` to recognize UTF-8. BOM handling varies across tools, so adopt one consistent, tested convention.

A file containing only ASCII characters cannot distinguish UTF-8 from many ASCII-compatible encodings. Therefore, compiling cleanly with `-encoding UTF-8` does not conclusively prove every file was transcoded properly.

### `.editorconfig` to reduce drift

You can add an `.editorconfig` file at the project root:

~~~ini
root = true

[*.java]
charset = utf-8
end_of_line = lf
~~~

This configures editors or tools **that support EditorConfig**; it does not replace `javac -encoding UTF-8` and does not automatically transcode old files. `end_of_line = lf` standardizes line endings in source to reduce cross-environment diffs, though line endings are a separate concern from character encodings.

## 9. Diagnosing encoding errors by layer

| Symptom | Possibility / Check | Resolution |
| --- | --- | --- |
| `javac` reports `unmappable character` | Bytes in source do not match the declared charset | Verify original encoding; convert file or set matching `-encoding`. |
| Compiles successfully yet string becomes `cafÃ©` | UTF-8 read as ISO-8859-1/Windows-1252 or already corrupted beforehand | Inspect raw source bytes and compiled string value; fix source if already mojibake. |
| `java` prints garbled text yet unit tests comparing strings pass | Terminal charset, font, or stdout pipeline differs | Check terminal encoding and output decoding. Do not arbitrarily change `javac -encoding`. |
| IDE works, CI fails | Different compiler invocation, JDK, default charset, or source generation | Pin encoding in build, inspect toolchain and CI logs. |
| Only generator-produced files fail | Generator writes a different charset than `javac` reads | Set encoding when **writing source**, then set encoding when compiler **reads source**. |
| `.properties`, CSV, JSON resources fail | Resource reader or parser follows different encoding rules | Configure plugins and data read/write APIs separately. |
| Legacy file breaks after setting UTF-8 | Bytes remain in old encoding | Actually transcode the file, then inspect diff and run tests. |

Concise isolation steps:

- **Step A:** Inspect raw bytes of the `.java` file, especially segments with accented characters; in UTF-8 `café`, the `é` bytes must be `C3 A9`.
- **Step B:** Inspect the compiler command or build configuration; confirm `UTF-8` is genuinely passed to `javac`.
- **Step C:** Check the string value inside a JVM test, rather than concluding solely from terminal display.
- **Step D:** If errors happen only when reading files/printing outputs at runtime, investigate I/O APIs and console settings; compile-time `-encoding` does not control that step.

In runtime Java code, when reading a UTF-8 file, pass the charset explicitly, for example:

~~~java
String content = java.nio.file.Files.readString(
        java.nio.file.Path.of("data.txt"),
        java.nio.charset.StandardCharsets.UTF_8);
~~~

This is a **snippet placed inside a method** and the method must declare/handle `IOException`. It serves **runtime file I/O**, a different role from `javac -encoding UTF-8`. Even on Java APIs defaulting to UTF-8 (JDK 18+), writing it explicitly documents project intent.

## 10. Common mistakes and boundaries of the solution

**Changing only the machine's default encoding.** This inadvertently couples builds to system-wide or personal IDE settings. Set `-encoding UTF-8` in compiler options or build scripts and standardize source files.

**Tuning only `-Dfile.encoding`.** This is a JVM system property whose configuration/behavior varies across Java generations and does not specifically describe source encoding. Pass `-encoding` directly to `javac`. Do not confuse it with streams created by the application at runtime.

**Changing only the flag without converting files.** If a file is actually Windows-1252, adding `-encoding UTF-8` can worsen errors. Source bytes and compiler declaration must match.

**Inferring correctness from absence of compile errors.** Many encodings yield wrong characters while remaining valid Java syntax. Test important string contents, especially messages, UI labels, regexes, and comparison strings.

**Thinking `-encoding` controls the terminal.** A properly compiled class can still render incorrectly due to terminal/font/charset issues. Conversely, a terminal may render `cafÃ©` “very clearly”—precisely showing the corrupted data compiled into the program.

**Confusing with Unicode escapes in Java code.** Escapes like `\u00E9` use ASCII characters to represent `é` and are handled by Java lexical rules. They can help in special cases, yet replacing all accented text with escapes fails to standardize files and harms readability. Unicode escapes are also processed very early, even in some comment locations, so they are not a general transcoding tool.

**Assuming every tool shares one charset.** Editors, compilers, build resources, processors, scripts, and runtimes must align; the goal is configuring encoding everywhere text is actually read or written.

## 11. Rollout workflow for an active project

1. **Choose UTF-8** for all Java sources; check whether legacy files with non-ASCII text need conversion.
2. **Transcode legacy files under review** to UTF-8 and inspect diffs to avoid corrupting literals/comments.
3. **Record configuration in the build:** `-encoding UTF-8`, `project.build.sourceEncoding` in Maven, or `JavaCompile.options.encoding` in Gradle.
4. **Sync IDEs/editors** so new files are created as UTF-8; consider `.editorconfig`.
5. **Run clean compilations** on supported JDKs in CI and local machines, checking generator-produced sources too.
6. **Run tests with real Unicode** (e.g. `"café"`, accented Vietnamese, non-Latin-1 characters), while distinguishing runtime/terminal bugs from compiler bugs.
7. **Keep configurations in the repository** so everyone and CI enforce the exact same rules.

### Self-check

**Question 1.** A source file is saved in UTF-8 and contains `café`. Does `javac -encoding ISO-8859-1` necessarily fail compilation? **No.** Code may still compile while turning the string into `cafÃ©`.

**Question 2.** When using JDK 21 which defaults to UTF-8, should encoding still be declared in the build? **Yes.** It states project requirements explicitly and protects pipelines running different JDKs or custom compiler invocations.

**Question 3.** Does adding `-encoding UTF-8` make `Files.readString` interpret every data file as UTF-8? **No.** Compile-time source decoding and runtime I/O are two separate concerns.

**Question 4.** A source is currently saved in Windows-1252; what is the right way to standardize on UTF-8? **Actually transcode the file's bytes**, verify the content, and then configure the compiler to read UTF-8.

**Question 5.** If console output shows garbled accents yet unit tests asserting the string value pass, should `-encoding` be changed immediately? **Not yet.** Check terminal encoding/font and stdout transport first.

**Core takeaway:** `-encoding` defines how `javac` converts **bytes of a `.java` file into Unicode characters**. Use `-encoding UTF-8` alongside source files genuinely saved in UTF-8, configure it directly in the build, and test with Unicode data to avoid machine-, OS-, or JDK-dependent results.