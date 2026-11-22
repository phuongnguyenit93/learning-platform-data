# Checking Diagnostic Positions and Severities via the Java Compiler API

> **Topic:** Java Advance – compilation → Compilation testing. This lesson focuses on writing tests that actively compile Java sources, collect `Diagnostic` instances, and verify **severity** (`ERROR`, `WARNING`, etc.) along with **position** (file, line, column, offset). This approach is suitable for negative compilation tests, annotation processors, code analysis tools, and quality pipelines.

## 1. Why is checking only “compile succeeded/failed” not enough?

A program can fail compilation as expected yet for an **entirely different reason** from what the test requires. For instance, you want to detect assigning a `String` to an `int` on line 4; if the sample code has a syntax error on line 1, asserting `task.call() == false` will still falsely “pass”. Valuable tests must also verify at least:

1. **Overall outcome:** whether the compilation task succeeded or failed.
2. **Diagnostic severity:** whether there is at least one `Diagnostic.Kind.ERROR` matching the scenario.
3. **Position:** which source the diagnostic belongs to, and whether the line/column/range corresponds to the faulty code.
4. **Content/issue category:** when needed, check the error group via `getCode()` or a normalized message, recognizing that these values depend on the compiler and JDK version.

For warnings, you cannot look only at `task.call()`: a successful compilation can still emit `WARNING` or `MANDATORY_WARNING`. If `-Werror` is enabled, warnings can cause compilation to fail. Therefore **success** and **diagnostics** are two distinct pieces of information that must be evaluated separately.

## 2. Core APIs: `javax.tools`

The relevant classes reside in the standard `java.compiler` module, package `javax.tools`. A compiler implementation is required in the runtime; standard JDKs provide `javac` in the `jdk.compiler` module, whereas custom Java runtimes may omit the compiler.

| API | Role in Testing |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Retrieves the system Java compiler; may return `null` if unavailable |
| `JavaCompiler` | Creates and runs compilation tasks |
| `JavaCompiler.CompilationTask` | Represents one compilation pass; `call()` returns the result |
| `JavaFileObject` / `SimpleJavaFileObject` | Represents input sources as files or in-memory strings |
| `StandardJavaFileManager` | Manages source/classpath/output files and charsets |
| `DiagnosticListener<JavaFileObject>` | Receives each diagnostic as the tool reports it |
| `DiagnosticCollector<JavaFileObject>` | Built-in listener collecting diagnostics into a list |
| `Diagnostic<? extends JavaFileObject>` | A single error/warning/note with severity and location |

Execution flow:

```text
Source JavaFileObject(s)
         │
         ▼
JavaCompiler.getTask(options, fileManager, listener)
         │
         ▼
CompilationTask.call()
         │
         ├── boolean success/failure
         │
         └── DiagnosticCollector
                  ├── kind: ERROR, WARNING, ...
                  ├── source URI
                  ├── line / column
                  ├── start / position / end offset
                  └── code / localized message
```

Create a **new collector for each compilation task** so diagnostics from a previous run do not mix in. Close `StandardJavaFileManager` using `try-with-resources`. A compiler task should only have `call()` invoked once; to compare two source versions, create two separate tasks.

### 2.1. Severity levels in `Diagnostic.Kind`

| Kind | Meaning | Typical Expectation |
| --- | --- | --- |
| `ERROR` | Compilation error | Usually required when testing negative compilation |
| `WARNING` | Standard warning | May appear when enabling appropriate `-Xlint` flags |
| `MANDATORY_WARNING` | Warning that the tool is obligated to report under relevant rules | Should be grouped under “warning” in policies |
| `NOTE` | Informational/note | Do not treat as an error unless your policy explicitly requires it |
| `OTHER` | Message outside the categories above | Record during analysis without assuming severity |

Do not lump every non-`ERROR` into `WARNING`. Classify explicitly:

```java
static boolean isWarning(Diagnostic.Kind kind) {
    return kind == Diagnostic.Kind.WARNING
            || kind == Diagnostic.Kind.MANDATORY_WARNING;
}
```

The snippet above is a **helper method** used inside a class importing `javax.tools.Diagnostic`; it is not a standalone Java program.

## 3. Interpreting positions accurately: file, line, column, and offset

A diagnostic is not guaranteed to be attached to a source or position. Read the API contract carefully:

| Method | Definition |
| --- | --- |
| `getSource()` | Associated `JavaFileObject`, may be `null` |
| `getLineNumber()` | Line number starting from **1**, or `Diagnostic.NOPOS` |
| `getColumnNumber()` | Column number starting from **1**, or `Diagnostic.NOPOS` |
| `getPosition()` | Character offset from the start of the source starting from **0**, or `NOPOS` |
| `getStartPosition()` | Start offset of the problematic region, or `NOPOS` |
| `getEndPosition()` | End offset of the problematic region, or `NOPOS` |
| `getCode()` | Implementation-defined diagnostic code, may be `null` |
| `getMessage(Locale)` | Message that may be localized |

When valid positions exist, the API guarantees:

```text
getStartPosition() <= getPosition() <= getEndPosition()
```

**`Diagnostic.NOPOS` is a sentinel value** (equal to `-1`), **not line 0/column 0**. Position methods return `NOPOS` when no suitable position exists. Do not write `source.getCharContent(...).charAt((int) d.getPosition())` without checking `getSource() != null` and `getPosition() != Diagnostic.NOPOS`, as well as string bounds.

**Character offset differs from UTF-8 byte offset.** When a source contains Vietnamese or Unicode characters outside the BMP, never use `getPosition()` as an index into the file's byte array. If you use `String.charAt()` / `substring()` on read Java sources, ensure identical content, newlines, and the compiler's indexing convention. Column position is a coordinate in the source, not necessarily the “visual column” when rendering tabs or Unicode characters; highlighting calculations must rely on the original source data.

For fixtures testing **exact line/column**, lock down the inputs:

- Fixed source code, UTF-8, and consistent newlines (typically LF), avoiding templates that insert prefixes or drop lines.
- Be intentional about **text block indentation**: Java automatically strips incidental whitespace in text blocks; verify the actual string before asserting line/column.
- Pin the target compiler/JDK for tests; the highlighted target position may shift across compiler versions even while the error-kind requirement holds.
- If testing multiple errors, distinguish the **root error** from cascading errors. Do not assume diagnostic order or count is always identical.

For example, a diagnostic at line 4, column 25 means **the fourth line and 25th column in the source seen by the compiler**; it is unrelated to that line's position in the host Java file containing the text block.

## 4. Complete Java 17+ example: catching an error on line 4

Goal: the `DiagnosticAudit` program invokes the compiler to compile a class `demo.Broken` containing `int count = "wrong";`. There is no need to create `Broken.java` on disk; the source is passed into `SimpleJavaFileObject` as a string. The test checks:

- Compilation fails.
- At least one `ERROR` diagnostic is present.
- An `ERROR` appears on **line 4**, with a valid column and belonging to the right source URI.

**File `DiagnosticAudit.java`:**

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticAudit {
    static final class StringSource extends SimpleJavaFileObject {
        private final String contents;

        StringSource(String className, String contents) {
            super(URI.create("string:///" + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.contents = contents;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return contents;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Cần chạy bằng JDK có module jdk.compiler");
        }

        String program = """
                package demo;
                public class Broken {
                    public static void main(String[] args) {
                        int count = "wrong";
                    }
                }
                """;

        JavaFileObject source = new StringSource("demo.Broken", program);
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                 compiler.getStandardFileManager(
                         null, Locale.ROOT, StandardCharsets.UTF_8)) {

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    files,
                    collector,
                    List.of("--release", "17",
                            "-encoding", "UTF-8", "-proc:none"),
                    null,
                    List.of(source));

            boolean ok = Boolean.TRUE.equals(task.call());

            long errorCount = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            boolean hasLine4Error = collector.getDiagnostics().stream()
                    .anyMatch(d ->
                            d.getKind() == Diagnostic.Kind.ERROR
                            && d.getLineNumber() == 4
                            && d.getColumnNumber() >= 1
                            && d.getSource() != null
                            && d.getSource().toUri().toString()
                                    .endsWith("/demo/Broken.java"));

            System.out.println("Biên dịch thành công: " + ok);
            System.out.println("Số lỗi >= 1: " + (errorCount >= 1));
            System.out.println("Lỗi ERROR ở dòng 4: " + hasLine4Error);
        }
    }
}
```

**Run from the directory containing the file**, using JDK 17 or higher:

```bash
javac --release 17 -encoding UTF-8 DiagnosticAudit.java
java DiagnosticAudit
```

**Stdout when running with standard system `javac` on JDK 17+:**

```text
Biên dịch thành công: false
Số lỗi >= 1: true
Lỗi ERROR ở dòng 4: true
```

The example has been verified with `javac`/`java` on OpenJDK 24. Do not assert the exact error wording because message language and phrasing are implementation-dependent. If you need a test that fails when properties are wrong, replace the print statements with assertions or throw `AssertionError` based on the results. Keeping `JavaFileObject` in memory also avoids errors from accidentally creating external source files, while the URI still lets you inspect which file caused the error.

**Note when writing sources on Windows:** the source must genuinely be UTF-8. Windows PowerShell 5.1 with `Set-Content -Encoding UTF8` often adds a UTF-8 BOM; `javac` may report an illegal `\ufeff` character at the start of the file. Use an editor saving UTF-8 without BOM or an API writing UTF-8 without BOM. This issue is **different** from the data-type error diagnostic the example intends to check.

## 5. Explaining the sequence of operations in the example

### 5.1. In-memory source is a valid Java file to the compiler

`StringSource` creates the URI `string:///demo/Broken.java` with `Kind.SOURCE`. `getCharContent()` returns the exact source code. Because the public class is named `Broken` in package `demo`, the URI should reflect the path `demo/Broken.java`; that keeps the diagnostic source stable. When switching to real files, use the file manager instead of constructing URIs manually.

When snapshotting errors, take the source name from `d.getSource().toUri()`, but canonicalize any absolute path segment so CI on Windows and Linux does not differ due to workspace paths. With an in-memory URI like above, comparing the `/demo/Broken.java` suffix is clear enough for a fixture; multi-file build systems need more careful source identification to avoid two files sharing the same suffix.

### 5.2. Collector receives diagnostics, `call()` returns status

The third parameter of `compiler.getTask(...)` is `DiagnosticListener`. `DiagnosticCollector` implements this interface and stores `Diagnostic` elements as the compiler reports them. After `task.call()`, read `collector.getDiagnostics()` to verify the outcome; the list can include warnings and notes, not only errors.

`Boolean.TRUE.equals(task.call())` avoids relying on unboxing a nullable result. A `false` tells nothing about **the reason**; therefore the test also checks for `ERROR` on line 4.

### 5.3. Compiler flags lock down the test environment

- `--release 17` pins the target Java 17 language/platform APIs (when supported by the compiler).
- `-encoding UTF-8` controls the charset when the compiler reads real files; for `StringSource` the content is already Unicode in memory.
- `-proc:none` disables annotation processing so the example is unaffected by processors accidentally on the classpath. **If testing an annotation processor, definitely remove this flag** and configure the processor path explicitly.
- The file manager is automatically closed inside `try-with-resources`; each pass should create its own collector/task.

Key lesson: **do not take a compiler log from stdout/stderr to parse error lines** when structured `Diagnostic` objects are already available. Text logs depend on locale, compiler, options, terminal width, and caret rendering.

## 6. Verifying severity: ERROR, WARNING, and policy

### 6.1. Testing compilation errors

A good assertion pattern (snippet used in tests, with `collector` and `ok` already present):

```java
if (ok) {
    throw new AssertionError("Fixture phải biên dịch thất bại");
}

boolean rightError = collector.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR
                && d.getLineNumber() == 4);
if (!rightError) {
    throw new AssertionError("Không tìm thấy ERROR ở dòng 4");
}
```

This is a **snippet**, not a standalone program; place it after `task.call()` in a compilation fixture like section 4.

When testing compiler rejection, include `getSource()` and an identifying feature of the error if possible, especially when the fixture has multiple issues. Do not assert `getDiagnostics().size() == 1` unless the test truly wants to guarantee **no other diagnostics at all**; notes and cascading errors can frequently appear.

### 6.2. Testing warnings: creating an intentional warning

Example of valid source calling a method annotated with `@Deprecated`:

```java
class Legacy {
    @Deprecated static void oldApi() {}
}

class Client {
    void run() {
        Legacy.oldApi();
    }
}
```

When compiled with `javac` and `-Xlint:deprecation` enabled, a `WARNING` can be captured at the `Legacy.oldApi()` call. In a separate test, put this source snippet into `StringSource("Client", sourceText)`; use options such as:

```java
List.of("--release", "17",
        "-encoding", "UTF-8",
        "-proc:none", "-Xlint:deprecation")
```

After `task.call()`, you can verify:

```java
boolean hasWarning = collector.getDiagnostics().stream()
        .anyMatch(d ->
                d.getKind() == Diagnostic.Kind.WARNING
                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING);

if (!ok || !hasWarning) {
    throw new AssertionError(
            "Mong đợi biên dịch thành công nhưng có warning");
}
```

These `collector`/`ok` snippets use variables from a separate compilation task, **not reusing the collector of the failing fixture in section 4**. To test warning level at a specific line, add a `getLineNumber()` check after pinning the exact fixture and toolchain version.

A warning might not appear if the lint option is omitted, the source has `@SuppressWarnings`, the compiler does not emit that same kind of warning, or the snippet no longer uses a deprecated API. Thus warning tests must explicitly specify the **flag**, **compiler version**, and **trigger source**.

### 6.3. `-Werror` does not change the nature of every diagnostic

With `-Werror`, the compiler can reject compilation due to warnings. This does not mean `WARNING` elements automatically turn into `ERROR` at the same position; the compiler may emit an additional general error because warnings are treated as errors. Tests should separate:

- Testing “warning exists”: assert `WARNING` or `MANDATORY_WARNING`.
- Testing “policy forbids warnings”: enable `-Werror` and assert compilation fails.
- Do not assume `-Werror` forces an `ERROR` to share the same line/column as the original warning.

### 6.4. Reading diagnostic codes when truly necessary

`d.getCode()` can be more useful than `getMessage(Locale)` for distinguishing “incompatible types” from “cannot find symbol” within the same JDK/toolchain. However, **the Diagnostic API does not standardize codes**: another compiler may choose different codes or return `null`. If tests must run across multiple vendors/major JDKs, prefer assertions by kind + source + position, combined with small fixtures and checking compilation outcome. Only snapshot exact codes when the project intentionally **pins the compiler implementation/version**.

## 7. Evaluating location safely and producing useful diagnostics

A diagnostic can originate from compiler option errors, annotation processors, file managers, or contexts not tied directly to a specific source. Do not always force `getLineNumber() > 0`.

Safe handling pattern (snippet placed in a method having `Diagnostic<? extends JavaFileObject> d`):

```java
String sourceName = d.getSource() == null
        ? "<no-source>"
        : d.getSource().toUri().toString();

String location = d.getLineNumber() == Diagnostic.NOPOS
        ? "<no-position>"
        : d.getLineNumber() + ":" + d.getColumnNumber();

String display = d.getKind() + " " + sourceName + ":" + location;
```

If `getLineNumber() != NOPOS`, under the standard `Diagnostic` contract `getColumnNumber()` must also have a position. Another implementation may be unable to determine a location for a global error; in that case test by kind/outcome and problem description at an appropriate level.

### 7.1. Computing the highlight span from offsets

When wanting to highlight a source span, use `getStartPosition()` and `getEndPosition()` **after** checking conditions:

```java
long start = d.getStartPosition();
long end = d.getEndPosition();
String text = d.getSource() == null
        ? null
        : d.getSource().getCharContent(true).toString();

if (text != null
        && start != Diagnostic.NOPOS
        && end != Diagnostic.NOPOS
        && start >= 0
        && start <= end
        && end <= text.length()) {
    String highlighted = text.substring((int) start, (int) end);
    // Use highlighted to explain the span marked by the compiler.
}
```

This snippet resides inside a method that can throw `IOException` or handle exceptions from `getCharContent()`; `StringSource` in the first example does not throw. When switching to real sources, confirm offsets match **the exact content the compiler read** (not text with normalized CRLF, inserted BOM, or altered indentation). Different compilers pick wider or narrower spans, so character-by-character highlight snapshots break easily on JDK upgrades.

### 7.2. Line and column may not match what a UI displays

- `getLineNumber()` and `getColumnNumber()` are 1-based logical positions; UI editors sometimes use **0-based** row/column indices. Convert explicitly: `uiLine = line - 1`, `uiColumn = column - 1` when positions exist.
- Tabs and Unicode characters can make “display column” differ from “character column”; never mechanically add spaces up to the column number to draw a caret.
- If results are sent over JSON/LSP, specify the position encoding; many editor systems use **UTF-16 code units**. Measure and convert instead of assuming byte indices.
- With multi-file compiler tasks, verify the source URI as well, not just the line number: two different files can both have an ERROR on line 4.

## 8. Testing multiple diagnostics of the same kind or across multiple files

When faulty code produces cascading diagnostics, a good strategy is checking for the existence of the **required subset** rather than asserting the entire list.

Suppose a project has files `A.java` and `B.java`; we can require:

1. At least one `ERROR` for file `A.java` in the expected region.
2. No `ERROR` for file `B.java` (valid fixture).
3. No compiler crash or config error.
4. Additional warnings categorized and reported for analysis.

To test “zero warnings” for a completely clean source set, intentionally enable lint options and assert:

```java
boolean anyWarning = collector.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.WARNING
                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING);
if (anyWarning) {
    throw new AssertionError("Build không được có warning");
}
```

The balance: test the **contract on error kind and source location** tightly enough to prevent false positives, while avoiding asserting details not guaranteed by the API standard (exact text, diagnostic order, secondary error count unless needed).

## 9. Real source files, classpath, and task handling

In-memory examples help learn the API, whereas real projects often need to compile sources on disk. In that case:

```java
// Snippet inside a method that already has JavaCompiler compiler.
try (StandardJavaFileManager files =
         compiler.getStandardFileManager(
                 null, Locale.ROOT, StandardCharsets.UTF_8)) {
    Iterable<? extends JavaFileObject> sources =
            files.getJavaFileObjectsFromPaths(
                    List.of(java.nio.file.Path.of("src/test/fixtures/Broken.java")));

    DiagnosticCollector<JavaFileObject> collector =
            new DiagnosticCollector<>();

    JavaCompiler.CompilationTask task = compiler.getTask(
            null, files, collector,
            List.of("--release", "17", "-encoding", "UTF-8",
                    "-proc:none", "-d", "target/compiler-fixtures"),
            null, sources);

    boolean succeeded = Boolean.TRUE.equals(task.call());
    // Check collector.getDiagnostics() here.
}
```

The snippet above is an **illustrative snippet**, requiring the fixture file and output directory `target/compiler-fixtures` to already exist (or be created before running); depending on the compiler, a non-existent output path may trigger an option error instead of the expected Java error diagnostic. For builds on Windows, macOS, and Linux, use `Path`/file manager to avoid manually concatenating separators. When fixtures have dependencies, pass `-classpath` with specific paths and `File.pathSeparator` or configure StandardJavaFileManager locations; do not let the test runner's default classpath unintentionally affect results.

Note how to distinguish errors:

| Scenario | Symptom | How to Handle in Tests |
| --- | --- | --- |
| Java source has type/syntax error | `ERROR` with matching source/location | Test negative compile by kind + source + line |
| Missing classpath dependency | `cannot find symbol`/`package ... does not exist` | Pin classpath and fixtures |
| Invalid `-d`, bad option | Task may throw `IllegalArgumentException` or report setup error | Treat as **test infrastructure** error, not a pass |
| Runtime lacks system compiler | `getSystemJavaCompiler() == null` | Fail-fast with a message requiring a JDK |
| Missing or broken processor | Diagnostics from processor or missing generated classes | Declare processor path and test separately |
| Compilation succeeds with warnings | `ok == true`, list contains `WARNING` | Check severity separately against policy |
| No source position | `source == null` or `NOPOS` | Record global diagnostic, avoid blind line/column access |

If using annotation processors in the test suite, enable `-proc:full` or declare the processor in a JDK-compatible way, then check diagnostics from the processor. For pure core-compiler tests, `-proc:none` reduces noise.

## 10. Designing stable assertions for CI

A good compilation test suite has two layers:

**Layer 1 – Stable API contract:**

- Task outcome (true/false) with the chosen JDK.
- `Diagnostic.Kind` is the expected enum value.
- `getSource()` points to the right fixture file; line/range is verified when part of the contract.
- `Diagnostic.NOPOS` is explicitly handled for global diagnostics.
- Diagnostic appears at least once; do not assume list ordering not guaranteed by the use case.

**Layer 2 – Compiler-specific details:**

- `getCode()` per pinned `javac` version.
- `getMessage(Locale.ROOT)` or English text for display/logging.
- Exact column/highlight/caret and ordering of multiple diagnostics.
- Warning counts with `-Xlint`, processors, or `-Werror` enabled.

Only snapshot Layer 2 if needing to test the **specific behavior of a compiler** or pinned toolchain. If the product's goal is “the system reports errors at the right place”, Layer 1 assertions combined with minimal fixtures are a more durable choice.

### 10.1. Reporting assertion failures with sufficient context

When the expected diagnostic is not found, the failure report should print what was collected in a structured format:

```text
Expected:
  ERROR, source=demo/Broken.java, line=4
Observed:
  kind, source URI, line, column, code, message (debug-only)
Build environment:
  JDK version, compiler options, source fixture hash
```

This is a **recommended report format**, not fixed stdout from Java. Escape newlines in `getMessage()` if printing each diagnostic on a single line. Do not use a specific message translation as golden output when CI runs across different JDKs/locales.

### 10.2. Preventing “false passes” in negative compilation

If asserting only “at least one ERROR on line 4”, a complex file could have two different errors on the same line. When a test has strict requirements, narrow the fixture to **a single type-assignment error** like the main example, verify the URI, and add code or message fragments **after pinning the compiler**. Do not write generic assertions like “any error occurred”.

For warning tests, include a “positive control”: recompile with `-Xlint:deprecation` disabled or using fixed source, to ensure the warning disappears for the right reason. Similarly, changing `int count = "wrong";` to `int count = 1;` and verifying compilation succeeds can catch bugs in the harness.

## 11. Quick troubleshooting

| Issue | Typical Cause | Action |
| --- | --- | --- |
| `compiler == null` | Runtime image lacks `jdk.compiler`, running on JRE-only environment | Run with a full JDK or provide compiler explicitly |
| Compilation fails yet collector is empty | Tool failed before receiving task, invalid options, setup exception | Distinguish exceptions, check output writer and options |
| Expected line 4 but got a different line | Text block indentation, newlines, source differs from fixture | Print actual source with line numbers; enforce LF |
| Column differs between IDE and javac | IDE uses different compiler or rules, different tab/Unicode handling | Pin compiler, normalize source, prefer line for portability |
| Warning present yet task still true | Warnings are not errors by default | Assert `Kind` or enable `-Werror` per policy |
| `getSource()` is null | Global diagnostic, not tied to a file | Handle `NOPOS` and fail explicitly if test requires a source |
| Deprecated warning not seen | `-Xlint:deprecation` not enabled, source no longer calls old API | Check flags/source/annotations |
| Message differs on CI | JDK/vendor/locale changed | Use `Locale.ROOT` for logging and do not assert full sentences |
| Test fails due to missing third-party class | Wrong task classpath | Supply explicit classpath/module path, version, and file manager |
| Diagnostic order changes | Compiler phases and cascading errors vary | Filter/map by kind + source + line, do not index `[0]` |
| Java test source has BOM character | Encoding when saving file | Save UTF-8 without BOM and read sources with explicit charset |

## 12. Self-check exercises

1. Change the assignment on line 4 from `"wrong"` to `1`. Verify `ok == true`, `errorCount == 0`, and `hasLine4Error == false`. Run the test twice, using a new collector each time.
2. Add an erroneous statement on another line. Filter out both `ERROR`s by line without relying on order; observe that the compiler may emit additional cascading errors.
3. Run the deprecated fixture in section 6 with and without `-Xlint:deprecation`; compare `Kind` and position, then enable `-Werror` to observe the task result.
4. Write a helper returning a list of `(kind, sourceUri, line, column, code)` records; handle `null`/`NOPOS` and sort before comparing snapshots.
5. Test a diagnostic with no location (for example, a real configuration error); verify your formatter does not throw `NullPointerException` or `StringIndexOutOfBoundsException`.
6. Test a source file with Vietnamese characters or emoji before the error line; distinguish UTF-8 byte offsets from character offsets and avoid corrupting surrogate pairs.

**Passing criteria:** an error/warning is captured with the exact severity and position in the fixture, missing-location cases are handled safely, and tests do not depend on natural-language messages unnecessarily.

## Official API documentation

- Java SE 17 – `javax.tools.Diagnostic`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Java SE 17 – `javax.tools.JavaCompiler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17 – `javax.tools.DiagnosticCollector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Java SE 17 – `javax.tools` package: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html
- Java SE 17 – `ToolProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Java SE 17 – `javac` options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html