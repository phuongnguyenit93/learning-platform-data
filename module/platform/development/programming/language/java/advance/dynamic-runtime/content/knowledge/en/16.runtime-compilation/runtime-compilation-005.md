# 16.5 Collecting Diagnostics, Error Locations, and Compilation Status

**Context:** Java Advance → dynamic-runtime → 16. Runtime compilation.

When an application compiles Java code at runtime using the `javax.tools.JavaCompiler` API, the answer to "did compilation succeed or not?" is only **part** of the result. To support an IDE, playground, rule engine, code generation system, automated grader, or a server accepting Java source, we also need to know **why compilation failed, in which file, on which line, at which column, whether there are warnings**, and whether the error belongs to the source code or the compiler execution infrastructure.

Three key components:

- **`JavaCompiler.CompilationTask.call()`** returns the compilation task status, typically `true` when there are no compilation errors and `false` when there are errors.
- **`DiagnosticCollector<JavaFileObject>`** receives the `Diagnostic`s emitted by the compiler, including `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`.
- **`Diagnostic`** describes the severity, source, message, and location information: `getLineNumber()`, `getColumnNumber()`, `getPosition()`, `getStartPosition()`, `getEndPosition()`, `getCode()`, `getMessage(Locale)`.

This lesson presents the complete flow of collecting errors/warnings with **Java 17+**, verifies three real compilation cases (valid, type mismatch, and deprecated warning), how to use coordinates to display error locations, the meaning of the `task.call()` result, and how to avoid wrong assumptions about messages provided by the compiler.

## 1. A compilation pass produces three groups of results

A dynamic compilation system should treat the results as three related but non-uniform data layers:

| Group | Typical API | Question answered |
| --- | --- | --- |
| **Task status** | `CompilationTask.call()` | Did the task complete successfully according to the compiler? |
| **Diagnostics** | `DiagnosticCollector.getDiagnostics()` | How many errors, warnings, notes are there? Where? What content? |
| **Output artifacts / infrastructure** | `JavaFileManager`, output directory, `Writer`, API exceptions | Where are class files written? Did the file manager/options/compiler break? |

Diagram:

```text
String Java source / JavaFileObject
             |
             v
ToolProvider.getSystemJavaCompiler()
             |
             v
JavaCompiler.getTask(writer, fileManager,
                     diagnosticListener, options,
                     classes, compilationUnits)
             |
             +------ compiler reports ------> DiagnosticCollector
             |                                   |
             v                                   +--> ERROR / WARNING / NOTE
      CompilationTask.call()                     +--> source, line, column, offsets
             |
             +--> true / false
             |
             +--> class output via JavaFileManager
             |
             +--> may have infrastructure/configuration exceptions
```

For example, a piece of code with **a call to a deprecated API** can still be compiled successfully. Conversely, a piece of code assigning `String` to `int` causes an error and returns `false`. Therefore, **having diagnostics does not mean compilation failed**, and **an empty diagnostics list is not enough to conclude the task succeeded** if compilation did not run, was stopped, or threw an exception.

## 2. The responsible APIs

### 2.1 `ToolProvider.getSystemJavaCompiler()`

The API retrieves the `JavaCompiler` bundled with the Java runtime if the environment provides the `jdk.compiler` compiler module. On minimal runtime-only distributions or custom runtime images missing this module, the method can return **`null`**.

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("A JDK compiler is required");
}
```

This is a **snippet**; to compile, you must import `javax.tools.JavaCompiler` and `javax.tools.ToolProvider`, or use the complete program in section 5. Do not call `compiler.getTask(...)` on `null` and then report a "syntax error" to the user — that is an **environment error, not a Java source error**.

### 2.2 `JavaFileObject` representing source code

`JavaCompiler` processes `JavaFileObject` objects. You can use `StandardJavaFileManager.getJavaFileObjectsFromPaths(...)` for real files or extend `SimpleJavaFileObject` to provide content **directly in RAM**.

For example, a source object has:

- URI `string:///lesson/Broken.java`.
- `Kind.SOURCE`.
- String content `package lesson; ...` via `getCharContent(boolean)`.

The compiler uses the URI/name metadata to identify the file, and `Diagnostic.getSource()` can return the exact `JavaFileObject` associated with the error. In the example, the source name displays `/lesson/Broken.java` from `getName()`; **you should not assume every JavaFileManager returns names in the same format**.

### 2.3 `DiagnosticCollector<JavaFileObject>`

This is a `DiagnosticListener` that stores diagnostics sent by the compiler. Create a **new collector for each independent compilation pass** to avoid mixing errors/warnings from previous passes:

```java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
```

This is a snippet in code that has already imported `javax.tools`. When creating the task, pass this collector as the **third parameter** of `compiler.getTask`. After `task.call()`, read `diagnostics.getDiagnostics()` to see which diagnostics were emitted.

**The collector does not invoke the compiler itself, does not generate class files, and does not compute the success status.** It only receives diagnostic events. Also, do not reuse the same collector for a series of compilations and assume `getDiagnostics()` only contains errors from the last one.

### 2.4 `StandardJavaFileManager` and output

`JavaCompiler.getTask` needs a file manager to read compilation units, resolve dependencies/module path/classpath, and write outputs. `compiler.getStandardFileManager(...)` is the basic choice; it should be closed with `try-with-resources`.

When compiling from an in-memory source **without** providing a custom output manager, the compiler can still write `.class` files to the filesystem. In the example, `-d` points to a separate temporary directory and that directory is cleaned up when finished, avoiding generating class files into the repo/cwd.

If the system truly needs bytecode in RAM, you can implement `ForwardingJavaFileManager`/`JavaFileManager.getJavaFileForOutput` and a `JavaFileObject` that returns an `OutputStream` into a buffer. **In-memory source does not automatically mean in-memory output.**

## 3. `Diagnostic.Kind`: error, warning, and note

`Diagnostic.Kind` includes:

| Kind | Interpretation | Usage |
| --- | --- | --- |
| `ERROR` | Compiler error, e.g., type mismatch, missing symbol, invalid syntax | Display as an error; typically the task fails |
| `WARNING` | Non-mandatory warning, e.g., configured lint warning | Display as a warning; do not assume failure by default |
| `MANDATORY_WARNING` | Mandatory warning required by the compiler/JLS to be reported under appropriate circumstances | **Also a warning**, should be included in the warning total |
| `NOTE` | Additional information emitted by the compiler | Display as informational, do not treat as an error |
| `OTHER` | Diagnostic kind not belonging to the groups above | Handle as other information or preserve the kind |

**Common mistake:** Counting only `Diagnostic.Kind.WARNING` and missing `MANDATORY_WARNING`. In the program in section 5, with the tested OpenJDK compiler, the deprecated API diagnostic is reported as `MANDATORY_WARNING`, while compilation still succeeds.

How to count:

```java
long errors = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();

long warnings = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.WARNING
                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING).count();
```

This is a snippet where `diagnostics` already exists. The warning total does not automatically include `NOTE`/`OTHER`. If the product needs the total of all events, store `List<Diagnostic<...>>` separately and classify by all kinds.

## 4. Error location: file, line, column, and offsets

A `Diagnostic<? extends JavaFileObject> d` has these main data fields:

| API | Meaning | When unavailable |
| --- | --- | --- |
| `d.getSource()` | Source object associated with the error | Can be **`null`** |
| `d.getLineNumber()` | Line containing the primary position, usually presented starting from **1** | `Diagnostic.NOPOS` |
| `d.getColumnNumber()` | Column on the line, usually presented starting from **1** | `Diagnostic.NOPOS` |
| `d.getPosition()` | Character offset from the start of the source, **starting from 0** | `Diagnostic.NOPOS` |
| `d.getStartPosition()` | Start offset of the problem region | `Diagnostic.NOPOS` |
| `d.getEndPosition()` | End offset of the problem region | `Diagnostic.NOPOS` |
| `d.getKind()` | Severity level `ERROR/WARNING/...` | Kind provided by the diagnostic |
| `d.getCode()` | Implementation-dependent diagnostic code, **can be null** | Do not treat as a stable identifier across compilers |
| `d.getMessage(Locale.ROOT)` | Error message in the chosen locale | Wording depends on implementation/JDK |

The offsets are not UTF-8 file byte offsets: they are **character offsets** according to how the source is provided by the JavaFileObject. Java Strings store text as UTF-16 code units; for code with supplementary Unicode characters, tabs, CRLF, or strings with different normalization, the editor needs to **map offsets to UI coordinates** intentionally, without confusing them with UTF-8 byte indices.

According to the `Diagnostic` contract:

```text
startPosition <= position <= endPosition
```

When a location is present, `getPosition` is the offset of the primary position; `getStartPosition` and `getEndPosition` describe the span the compiler considers relevant. Do not assume every compiler always returns the same span: the highlight width can depend on the JDK/compiler and the error type.

### 4.1 Example of a concrete error

In the source:

```java
package lesson;
public class Broken {
    static int get() {
        int n = "oops";
        return n;
    }
}
```

This is a standalone source snippet passed to JavaCompiler without `public static void main`. When compiled, the error is **cannot assign `String` to `int`**. On the tested compiler version, the diagnostic appears at **line 4, column 17**, right at the `"oops"` literal.

Because columns start from 1, the position is marked after 16 characters on the line:

```text
        int n = "oops";
                ^
```

Counted from the start of the entire source (each line ends with `\n`), the reported position is `position=77`, `start=77`, `end=83` on the tested compiler. When integrating with an IDE, **do not hard-code 77 or column 17**; read the location dynamically from each actual `Diagnostic`.

### 4.2 Why is `getSource() == null` a normal situation?

Not every diagnostic is attached to a file. Some errors are caused by compiler options, environment, classpath/module path, annotation-processing setup, or whole-compilation state that does not point to a specific source token. When there is no appropriate position, `getPosition() == Diagnostic.NOPOS` (value `-1`) and line/column/start/end are unusable.

Therefore, presentation code must have a fallback:

```java
String source = d.getSource() == null
        ? "<no source>"
        : d.getSource().getName();

String location = d.getLineNumber() == Diagnostic.NOPOS
        ? "(global diagnostic)"
        : d.getLineNumber() + ":" + d.getColumnNumber();
```

This is a snippet in a context where variable `d` already exists, not a standalone program. When location is unavailable, display the message at the project/compilation level instead of randomly highlighting line 0 or -1.

### 4.3 Error locations in editors and code generators

With framework-generated Java code, sometimes the file reported by the compiler is `GeneratedSource.java` rather than the file the user typed. To provide good UX, the application needs to map:

1. The JavaFileObject seen by the compiler → generated URI/path.
2. The offset or line/column returned by the compiler → the exact **compiled source** version.
3. The position in the generated source → the original template/user input (if the system has a source map).
4. Message and severity → UI notification, per-field or per-file error.

You cannot simply take `getLineNumber` of the generated source and apply it to the user's raw textarea when the generator has added package/imports/wrappers. Similarly, if the editor normalizes CRLF to LF after compilation, offsets may no longer match. Keep an immutable source snapshot of that exact compilation pass and associate diagnostics with a version/snapshot ID.

## 5. Complete Java 17+ example: three compilation cases and diagnostics

The **`CompilerDiagnosticsDemo.java`** program uses `ToolProvider`, `SimpleJavaFileObject`, `DiagnosticCollector`, and `StandardJavaFileManager`. Three cases:

- **`valid`:** Valid Java source, compiles successfully, no diagnostics.
- **`invalid`:** assigns `String` to `int`, compilation fails, has an `ERROR` clearly indicating file/line/column/offsets.
- **`warning`:** calls an API marked `@Deprecated` with `-Xlint:deprecation`, compilation succeeds but has a warning.

The program does not load/run the compiled user code; it only creates class files in a temp directory and deletes them after each case. This helps separate compile-time diagnostics from errors when invoking runtime bytecode.

### 5.1 File `CompilerDiagnosticsDemo.java`

```java
import java.io.IOException;
import java.io.StringWriter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompilerDiagnosticsDemo {
    static final class Source extends SimpleJavaFileObject {
        final String text;

        Source(String binaryName, String text) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    static void compileCase(JavaCompiler compiler, String label, List<Source> sources)
            throws IOException {
        Path output = Files.createTempDirectory("compile-diagnostics-");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {
            var options = List.of("--release", "17", "-proc:none",
                    "-Xlint:deprecation", "-d", output.toString());
            boolean success = Boolean.TRUE.equals(compiler.getTask(
                    new StringWriter(), files, diagnostics, options, null, sources).call());

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
            long warnings = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.WARNING
                            || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING).count();
            System.out.println(label + ": success=" + success +
                    " errors=" + errors + " warnings=" + warnings);

            for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                String file = d.getSource() == null ? "<none>" :
                        d.getSource().getName();
                System.out.println("  " + d.getKind() + " " + file +
                        " line=" + d.getLineNumber() +
                        " column=" + d.getColumnNumber() +
                        " position=" + d.getPosition() +
                        " start=" + d.getStartPosition() +
                        " end=" + d.getEndPosition());
                System.out.println("  messagePresent=" +
                        !d.getMessage(Locale.ROOT).isBlank());

                if (d.getSource() != null &&
                        d.getLineNumber() != Diagnostic.NOPOS) {
                    String[] lines = d.getSource().getCharContent(true)
                            .toString().split("\\R", -1);
                    int index = Math.toIntExact(d.getLineNumber() - 1);
                    if (index >= 0 && index < lines.length) {
                        System.out.println("  source=" + lines[index].strip());
                    }
                }
            }
        } finally {
            try (Stream<Path> all = Files.walk(output)) {
                for (Path file : all.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(file);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        String good = "package lesson;\n" +
                "public class Good {\n" +
                "    public static int value() { return 7; }\n" +
                "}\n";
        String bad = "package lesson;\n" +
                "public class Broken {\n" +
                "    static int get() {\n" +
                "        int n = \"oops\";\n" +
                "        return n;\n" +
                "    }\n" +
                "}\n";
        String legacy = "package lesson;\n" +
                "public class OldApi {\n" +
                "    @Deprecated public static void old() {}\n" +
                "}\n";
        String client = "package lesson;\n" +
                "public class Client {\n" +
                "    public static void call() { OldApi.old(); }\n" +
                "}\n";

        compileCase(compiler, "valid", List.of(new Source("lesson.Good", good)));
        compileCase(compiler, "invalid", List.of(new Source("lesson.Broken", bad)));
        compileCase(compiler, "warning", List.of(
                new Source("lesson.OldApi", legacy),
                new Source("lesson.Client", client)));
    }
}
```

### 5.2 Compile and run

Create an empty directory, save the source file with the exact name, and run with **JDK 17 or higher**:

```bash
javac --release 17 -encoding UTF-8 CompilerDiagnosticsDemo.java
java CompilerDiagnosticsDemo
```

The code uses `List.of`, `String.strip`, and `Stream.toList` (available since Java 16), so `--release 17` is compatible. It requires an environment with a compiler (the `jdk.compiler` module): if run on a runtime image that only has `java.base` and lacks the compiler, `ToolProvider.getSystemJavaCompiler()` may return `null`.

**Verified stdout with OpenJDK 24, compiled with `--release 17`:**

```text
valid: success=true errors=0 warnings=0
invalid: success=false errors=1 warnings=0
  ERROR /lesson/Broken.java line=4 column=17 position=77 start=77 end=83
  messagePresent=true
  source=int n = "oops";
warning: success=true errors=0 warnings=1
  MANDATORY_WARNING /lesson/Client.java line=3 column=39 position=76 start=70 end=80
  messagePresent=true
  source=public static void call() { OldApi.old(); }
```

**Note on reproducibility:** The `success` and `errors` totals accurately reflect the three test cases; warnings from the compiler (including `WARNING` or `MANDATORY_WARNING`), exact warning positions, and diagnostic codes/messages may vary by JDK/vendor/options. Therefore, the program **does not print the verbatim message** to the sample stdout, and instead only confirms `messagePresent`. To display the actual content, call `d.getMessage(locale)` in your application (section 7). The columns/positions listed are verified results in the test environment, not hard API guarantees across all compilers.

### 5.3 Why are the results as shown?

1. `valid` receives a `JavaFileObject` for `lesson.Good` with valid source. `task.call()` returns `true`, the collector has no errors/warnings: `success=true errors=0 warnings=0`.
2. `invalid` compiles `lesson.Broken`. The line `int n = "oops";` has a type mismatch; the task returns `false`, and the collector has an `ERROR`.
3. `/lesson/Broken.java` is `Source.getName()` from the URI `string:///lesson/Broken.java`. This is an identity created by the source object, not a filesystem path that must exist.
4. `line=4 column=17` is the location where the compiler recorded the error in the provided source. `position=77 start=77 end=83` are character offsets from the start of the source.
5. `messagePresent=true` shows that `getMessage(Locale.ROOT)` returns a useful message; we intentionally do not rely on the exact wording because message text can change.
6. `warning` compiles **two source files in one task**: `lesson.OldApi` defines a deprecated method and `lesson.Client` calls it.
7. `-Xlint:deprecation` instructs the compiler to emit deprecation diagnostics. The compiler in the test case emits a `MANDATORY_WARNING` at `Client.java` line 3; the warning total is still 1.
8. `success=true` in the warning case proves that **warnings do not cause the task to fail by default**. If the project's policy is "warnings are errors", a separate rule or appropriate option must be applied.
9. `-proc:none` disables annotation processing for the three cases; it keeps the demo stable and reduces a source of code execution when compiling untrusted input.
10. `-d output` keeps class files in a temp directory. At the end of the case, `try-with-resources` closes the file manager and `finally` deletes the output directory. The source strings do not need to reside on the filesystem.

### 5.4 Note on `StringWriter`

The first argument of `compiler.getTask(...)` is a `Writer` to receive output **that does not go through the diagnostic listener**. The example provides `new StringWriter()` without printing it because the goal is to inspect `DiagnosticCollector`. In a real application, keep a reference:

```java
StringWriter compilerOutput = new StringWriter();
JavaCompiler.CompilationTask task = compiler.getTask(
        compilerOutput, fileManager, diagnostics, options,
        null, compilationUnits);
Boolean successful = task.call();

String extraOutput = compilerOutput.toString();
```

This is a **snippet**; it requires `compiler`, `fileManager`, `diagnostics`, `options`, and `compilationUnits`. `extraOutput` is different from the diagnostics list; you should not equate all text in the Writer with `Diagnostic.Kind.ERROR`. Use the collector for structured location/error-kind information, and the Writer to store additional messages outside the diagnostic channel if any.

## 6. What does `CompilationTask.call()` mean?

`JavaCompiler.CompilationTask` extends `JavaCompiler.CompilationTask` from the compiler API and implements `Callable<Boolean>`. The `call()` method **executes the compilation task** and returns a Boolean value indicating whether the task completed without errors according to the compiler.

In code:

```java
Boolean result = compiler.getTask(
        writer, fileManager, diagnostics, options, null, units).call();

boolean success = Boolean.TRUE.equals(result);
```

This is a snippet in a context where the corresponding variables already exist. `Boolean.TRUE.equals(...)` is useful to clearly specify that only `Boolean.TRUE` counts as success. Separate compilation tasks should be recreated if you want to recompile: do not call `call()` a second time on the same task object and expect the compiler to reset itself.

### Real-world statuses should be separated into multiple categories

| Case | `task.call()` / exception | Diagnostics | Suggested application status |
| --- | --- | --- | --- |
| Valid source, no warnings | `true` | May be empty | `SUCCESS` |
| Valid source with warnings | `true` | `WARNING`/`MANDATORY_WARNING` | `SUCCESS_WITH_WARNINGS` |
| Syntax or type error in source | `false` | Usually has `ERROR` | `COMPILE_ERROR` |
| Compiler configured to treat warnings as errors | May be `false` | May have warning with related error diagnostic | `COMPILE_ERROR` or `POLICY_REJECTED` depending on policy |
| No `JavaCompiler` available | Cannot create task | No compilation diagnostics | `COMPILER_UNAVAILABLE` |
| Invalid parameters/options/task setup | May throw exception before/during compile | May have no location | `SETUP_ERROR` |
| File manager / output I/O error | May throw exception or task fails | Not necessarily sufficient error location | `INFRA_ERROR` |
| Code compiles successfully but fails at runtime | Compilation `true` | Compile diagnostics may be empty | `RUNTIME_ERROR` of the execution phase, not a compile failure |

Labels like `SUCCESS_WITH_WARNINGS`, `COMPILE_ERROR`, etc. are **application-defined enums/policies**, not statuses returned directly by `CompilationTask`. `call()` only returns a Boolean (or does not return due to an exception); status mapping depends on system requirements.

**Do not use `errors == 0` alone as the status.** A task that did not run, threw an exception, or failed due to policy/IO may still have no `Diagnostic.Kind.ERROR` with a specific location. The source of truth for the compilation result is the task result together with API error information; the diagnostics list provides context, not a replacement for the status.

### `-Werror` and warnings

With the `javac` compiler, the `-Werror` option can turn warnings into a condition that causes compilation to be treated as failed. If enabled, `success` can be `false` even though the underlying issue has a warning kind. A review service should store **both the policy**, diagnostics, and `task.call()` to explain this to the user.

`-Xlint:deprecation` enables deprecation diagnostics on javac; different compiler configurations can change the number/content of warnings. Do not mix a test expecting "1 warning" with business logic requiring exactly one warning across all JDKs/vendors.

### A failed task may leave incomplete output

The compiler may have already written some class files before detecting another error. Therefore, `task.call()==false` does not necessarily prove the output folder is empty. In production applications, compile into a **separate staging/temp output**, and only publish artifacts if the task succeeds and policy permits. Do not let a class loader pick up incomplete output just because `.class` files appeared on the filesystem.

## 7. Displaying diagnostic messages without relying on fixed wording

`Diagnostic.getMessage(Locale)` provides the message for human readers; `getCode()` provides a compiler-specific code and **can be `null`**. Preserve both if the UI/debugger requires them, but **do not use the translated message string as a logic key**.

Snippet inside a `for (Diagnostic<? extends JavaFileObject> d : ...)` loop:

```java
String message = d.getMessage(Locale.ROOT);
String code = d.getCode(); // may be null, compiler-dependent
System.out.println("kind=" + d.getKind());
System.out.println("message=" + message);
System.out.println("code=" + code);
```

The complete program in section 5 only prints `messagePresent` to have stable stdout in the test environment. In a real UI, use `message` as the error text, and `kind` and `position` as classification and positioning data. If localization is needed, choose `Locale` intentionally (for example, `Locale.ROOT` for more consistent logs across configurations; however, there is **no guarantee** that wording remains completely unchanged across compiler versions).

### Do not parse compiler stderr manually to find line/column

A fragile approach is taking a text line like `Broken.java:4: error: incompatible types` from stderr and using regex to extract the line number. It depends on locale, compiler vendor, and message format. Since you are already using `javax.tools`, retrieve them directly:

```java
Diagnostic.Kind kind = d.getKind();
long line = d.getLineNumber();
long column = d.getColumnNumber();
long start = d.getStartPosition();
long end = d.getEndPosition();
```

This is a snippet using an existing `d`. Location data is separated from the natural-language message, making it easy to map to an IDE, JSON response, or event stream. Only use a text parser when working with another compiler that does not provide a structured diagnostic API.

## 8. Converting diagnostics to editor positions

### 8.1 Clear position contract

An editor typically uses:

- **File URI/path**: string or resource ID. `Diagnostic.getSource()` can be `null`.
- **Line**: 1-based from `getLineNumber()`; many editor APIs use 0-based, so convert at the boundary.
- **Column**: 1-based from `getColumnNumber()`; tabs can change visual display, so it is not simply equal to character index.
- **Character offsets**: 0-based from `getPosition()/getStartPosition()/getEndPosition()`; not UTF-8 byte offsets.
- **Message**: `getMessage(locale)` for human understanding.
- **Severity**: mapped from `Diagnostic.Kind`.

Example diagnostic in `Broken.java`:

```text
file:   /lesson/Broken.java
kind:   ERROR
line:   4
column: 17
start:  77
end:    83

        int n = "oops";
                ^^^^^^
```

The carets are used to illustrate the source span marked by the compiler in **the demo's source**; in a real UI, you must account for indentation, tab width, Unicode, and the editor's end-offset policy. If you call `strip()` to print a source line for readability as in the demo, the original column coordinates **no longer** match the display position of the stripped line. To highlight accurately, keep the original line content intact.

### 8.2 When the compiler reports an error without a position

Not every diagnostic can point to a token:

```java
boolean located = d.getPosition() != Diagnostic.NOPOS
        && d.getSource() != null;

if (!located) {
    // Attach diagnostic to the project / compilation level.
}
```

This is a snippet. Do not force command-option or classpath errors onto the first line of an arbitrary source file, because the user will edit the wrong place. For setup errors, the UI can show a general banner along with exception/option details instead of drawing an underline in the editor.

### 8.3 Sorting, grouping, and multiple files

`DiagnosticCollector` receives events in the order the compiler reports them, but an editor should group by source identity and sort by location:

1. Group by canonical URI/resource ID (not just the basename `Broken.java`).
2. For diagnostics with a position, sort by ascending `line` then `column`.
3. Handle diagnostics without source/position in a "project-level" group.
4. Preserve kind to display ERROR differently from WARNING/NOTE.
5. Preserve message and code (if any); do not merge two different errors just because they are on the same line.
6. Attach compilation ID/source version so diagnostics from an old compile pass are not mixed with a new buffer.

In code generation systems, maintain a source map between the generated file and the user's input. If a reliable mapping does not exist yet, clearly show the error for the generated source rather than claiming the error is on the corresponding line in the original source.

### 8.4 Conceptual sample API response

A service can return the following structure (this is a **data model**, not an object generated by JavaCompiler itself):

```text
CompilationResult
  status: COMPILE_ERROR
  compilerAvailable: true
  taskSucceeded: false
  errorCount: 1
  warningCount: 0
  diagnostics:
    - kind: ERROR
      sourceUri: string:///lesson/Broken.java
      line: 4
      column: 17
      position: 77
      startPosition: 77
      endPosition: 83
      message: text from getMessage(Locale.ROOT)
```

A JSON-based service needs to escape message content when serializing, rather than concatenating strings arbitrarily. For sensitive data, avoid returning full source and compiler internals beyond what is necessary; legitimate users only need the diagnostics associated with their request's source.

## 9. Why can warnings "disappear"?

Compiler options directly affect the type and quantity of diagnostics:

| Option/condition | Consequence |
| --- | --- |
| `-Xlint:deprecation` | Instructs javac to be more detailed about deprecated APIs |
| `-Xlint:all` | Enables many lint warning groups, which can make logs noisier |
| `-Werror` | Allows treating warnings as a cause of failure per compiler policy |
| `-proc:none` | Does not run annotation processors in this compiler pass |
| `--release 17` | Uses Java 17 source/API/target compatibility on JDKs supporting the option |
| Missing appropriate classpath/module-path | Can generate symbol/package/module errors |
| Choosing a different `Locale` | Can change the displayed message |
| Using a different compiler vendor or JDK version | Diagnostic code, message, position, and warning level may differ |

If the expected output is `WARNING` but the actual is `MANDATORY_WARNING`, this is **not necessarily a bug in the collector**. Warnings must still be counted under both Kinds. For deprecation, the compiler may report briefly that a method is deprecated or report at each call site depending on options and implementation.

**Do not configure `-Xlint:all` just for a simple test** if the product needs low-noise logs: enable the exact required lint key, then test with a fixed source. Do not turn every `NOTE` into a `WARNING` just because the message wording contains "warning" — Kind is structured data.

## 10. Handling errors during setup, compile, and run

A runtime compilation service typically has at least three steps:

```text
VALIDATE REQUEST
    |
    v
CREATE COMPILATION TASK
    |
    v
CALL COMPILER & COLLECT DIAGNOSTICS
    |
    +-- task true ----> stage compiled outputs
    |                   +-- warnings? report separately
    |
    +-- task false ---> return compiler diagnostics
    |
    +-- exception ----> return infrastructure/setup failure
    |
    v
(if authorized) LOAD/RUN BYTECODE --> runtime errors belong to another phase
```

Different errors need to be classified:

**Source code errors:** Java syntax/type/access errors are compiler diagnostics. `CompilationTask.call()==false` is an important signal; show diagnostic file/line/column to the source author.

**Compiler configuration errors:** Missing compiler, invalid option, file manager failed to initialize, output dir not writable, missing dependencies. You may receive an exception or a diagnostic without a source. Provide a setup/infra status; do not pretend there is an "error on line 1".

**Runtime errors:** Successful compilation does not prove the compiled class will load/link/run successfully. `ClassNotFoundException`, `NoClassDefFoundError`, `ExceptionInInitializerError`, business logic errors, timeouts, or security events when running code belong to a different phase. Do not put them into the `DiagnosticCollector` array as a fake compile error.

**Errors caused by diagnostic processing itself:** If formatting code tries to call `d.getSource().getName()` without checking `null`, or takes `getLineNumber()-1` and indexes an array without checking `Diagnostic.NOPOS`, the formatter can throw an exception even though the compiler worked properly. Separate formatter exceptions from compilation status if the system needs resilience.

## 11. Safe implementation techniques for dynamic compilation systems

### 11.1 Keep output per compilation pass

Each task should have its own source snapshot, collector, file manager, and output directory/target storage. Compile into staging and only publish class artifacts if the task succeeds **and application policy accepts them** (e.g., no severe warnings). The demo uses a temp directory; production code may have caching/versioning, but must not mix up outputs from two build requests.

Do not allow clients to pass arbitrary `-d`, `-classpath`, `--module-path`, `-Xplugin`, or processor paths if the service has a shared machine; whitelist compiler options. Annotation processors can execute code at compile time; `-proc:none` only mitigates that specific risk and does not replace a sandbox/resource limits.

### 11.2 Compiling untrusted code is a separate security issue

`JavaCompiler` is only a compiler API, **not a sandbox**. The fact that a source compiles successfully does not make it safe to execute. When accepting Java code from the internet/users:

- Limit CPU, memory, time, and filesystem/network permissions with appropriate isolation mechanisms.
- Disable annotation processing if not needed.
- Only allow defined classpath/modules and compilation options.
- Do not load/run artifacts in a JVM containing secrets or service credentials.
- Do not allow new code to directly access another user's class loader or output path.
- Keep logs controlled, avoiding storing full source or messages containing unnecessary sensitive information.

Separate **diagnostic collection** from **bytecode execution**; this lesson only creates and reads diagnostics.

### 11.3 Do not keep a collector across requests

If the same service compiles file A and then file B, the old collector may retain messages from A. With concurrent requests, reusing a collector/file manager without a clear protocol also causes mixed-up resource identities and races. Instantiate a new collector, a new result object, and a separate output scope on each independent pass.

If you want to sort/group diagnostics, you can copy the list after `call()` and close the file manager appropriately. Avoid holding huge source code in collector/source objects longer than necessary.

### 11.4 Rules for using diagnostics in CI/IDE

In an IDE, show compiler diagnostics attached to the exact buffer version; in CI, report status according to `task.call()`, warning policy, and artifact publish result; in an automated grader, distinguish compile errors from runtime test errors. When auto-fixing, use kind + source ranges + AST/semantics analysis; do not decide code fixes solely from a localized message.

## 12. Misconceptions and anti-patterns

| Misconception / mistake | Reality / fix |
| --- | --- |
| "`DiagnosticCollector` itself knows whether compilation succeeded." | The collector only stores diagnostics; status comes from `task.call()` and exception state. |
| "Having a warning means the task failed." | Warnings often accompany `success=true`; the `-Werror` policy is a separate case. |
| "No `ERROR` means guaranteed success." | The task may not have run or may have had an exception/config failure; check the Boolean and API errors. |
| "Only Kind `WARNING` is a warning." | Also need to count `MANDATORY_WARNING`. |
| "Every diagnostic has `getSource()`." | `getSource()` can be `null`; must have a compilation-wide fallback. |
| "Line and column start from 0." | The API usually returns **1-based** when a position exists; `getPosition` is a **0-based offset**. |
| "Offset is the byte count of the UTF-8 file." | No; it is a character offset on the source object. |
| "`getEndPosition` always has the same span in every javac version." | Diagnostic range depends on compiler/error type; do not hard-code. |
| "`getCode()` is a stable enum across all of Java." | Compiler-specific, can be null; do not use as a public stable protocol without versioning. |
| "`getMessage(Locale)` returns a fixed string." | Wording can differ by locale/implementation/JDK version. |
| "Using `StringJavaFileObject` means .class automatically stays in RAM." | In-memory **source** does not automatically become in-memory **output**; configure the file manager. |
| "A compiler task can only report errors via `Diagnostic`." | Missing compiler, option/file manager errors can throw exceptions or write to another channel. |
| "Compiler success means bytecode is guaranteed to run everywhere." | Runtime linkage/dependencies/security and bugs are a different phase. |
| "Using `d.getLineNumber()-1` to access an array is always safe." | There is `NOPOS` and out-of-range if source/line mapping differs; bounds checking is required. |
| "Take diagnostics from the previous task to show in the current editor." | Must associate the compiler result with a specific source snapshot/version. |
| "The compiler can safely run any user code." | No. Compiling and executing untrusted code requires isolation/security. |

## 13. A practical debugging checklist

If a dynamic compilation system returns `false` or the IDE screen does not highlight errors properly, check in order:

1. **Does the compiler exist?** `ToolProvider.getSystemJavaCompiler()!=null`, `jdk.compiler` module available.
2. **Is the source correct?** `JavaFileObject.getKind()==SOURCE`, URI/path, `getCharContent()` matches the snapshot just sent.
3. **Was the collector passed to the right task?** Third parameter of `JavaCompiler.getTask`.
4. **Did the task actually run?** Was `call()` invoked, catching setup/I/O exceptions.
5. **Are the options right?** `--release`, `-classpath`, `--module-path`, lint, annotation processing.
6. **What status was received?** `Boolean.TRUE.equals(task.call())`, not just counting errors.
7. **Were warnings summed across both Kinds?** `WARNING` + `MANDATORY_WARNING`.
8. **Which source does the diagnostic belong to?** `getSource()`, URI, class loader/file manager, source snapshot ID.
9. **Is there a position?** `getPosition()!=Diagnostic.NOPOS` and source is non-null.
10. **Do line/column map to the editor correctly?** 1-based vs 0-based; CRLF, tab, Unicode, generated wrapper.
11. **Is the message being parsed as a protocol?** Use `getKind()`, controlled `getCode()`, source ranges; messages are for human readers.
12. **Where are output artifacts?** `-d`, file manager, cleanup; do not publish when compile is false.
13. **Are there separate runtime errors?** Catch/expose in the execute phase, do not mix into compilation diagnostics.
14. **Are there concurrent requests?** Check separate collector/fileManager/output scopes.
15. **Do not trust hard-coded position tests of a single JDK:** If everything is right except column/warning kind on another JDK, check the JavaCompiler implementation before concluding a bug.

## 14. Self-check questions with answers

**Question 1.** Which parameter of `JavaCompiler.getTask` is `DiagnosticCollector` passed to?

**Answer:** The **third** parameter: `diagnosticListener`; in the order `(out, fileManager, diagnosticListener, options, classes, compilationUnits)`.

**Question 2.** `task.call()` returns `true` and the collector has a `MANDATORY_WARNING`. Is the compilation an error?

**Answer:** Not by default. The task succeeded, with a warning. The application can present `SUCCESS_WITH_WARNINGS`; if the policy is `-Werror` or custom rejection, the status may differ.

**Question 3.** The source has `int n = "oops";`, and the compiler reports `ERROR` at line 4, column 17. Are line and column 0-based or 1-based?

**Answer:** **1-based**. `getPosition()` is a **0-based** character offset in the source. If the editor needs a zero-based line index, subtract 1 after checking `NOPOS`.

**Question 4.** `getSource()` returns `null` and `getPosition()` returns `-1`. Should the application highlight at `line 0`?

**Answer:** No. This is a diagnostic without a specific source/location; show it at the compilation/project level.

**Question 5.** Can `getCode()` be used as a stable protocol code across compiler vendors?

**Answer:** Should not. `getCode()` is compiler-specific and can be `null`. Application versioning/mapping is needed if you must rely on it.

**Question 6.** Is `getMessage(Locale.ROOT)` guaranteed to be completely identical across JDK 17, 21, 24?

**Answer:** No. Message content depends on compiler implementation and version. Test semantics (reasonable kind/status/location), do not hard-code verbatim messages.

**Question 7.** When `getStartPosition`, `getPosition`, and `getEndPosition` all exist, what is their relationship?

**Answer:** Per the API, `start <= position <= end`. These are character offsets, not byte offsets.

**Question 8.** Does `-Xlint:deprecation` cause compilation to fail just for calling a deprecated method?

**Answer:** Not by default. It enables diagnostics for deprecated usage; to block warnings by policy, you can use `-Werror` or a post-check.

**Question 9.** `Source` is an in-memory JavaFileObject. Is running the compiler guaranteed not to create class files on disk?

**Answer:** No. Source in RAM and output are two separate things. With `StandardJavaFileManager`, `-d` will write class files to the output directory.

**Question 10.** `task.call()` reports `false` but the app still sees `.class` files in the output directory. Should it load them?

**Answer:** No. The compiler may write partial output before failing; only publish artifacts from staging when the task/policy succeeds.

**Question 11.** When displaying an error in a source where a generator added 30 lines of imports before the user's content, can you take `getLineNumber()` and highlight directly in the raw textarea?

**Answer:** Not directly. The line belongs to the **generated compilation unit**; a source map is needed to translate back to the user's input.

**Question 12.** Is it okay to share a `DiagnosticCollector` between two independent compiler tasks?

**Answer:** It can mix diagnostics from both passes, especially when running in parallel. Create a separate collector for each task and keep separate compilation IDs.

**Question 13.** Does `ToolProvider.getSystemJavaCompiler() == null` prove the source has a syntax error?

**Answer:** No. That means the compiler is unavailable in the runtime environment; the source has not been processed by the compiler yet.

**Question 14.** A Java source compiles successfully, but when loading the class a dependency is missing — which phase does the error belong to?

**Answer:** The runtime/linkage phase, not the initial compilation's `DiagnosticCollector`. Compile and execution statuses should be kept separate.

**Question 15.** The compiler can emit `NOTE` without `ERROR`/`WARNING`. Should `errorCount` be incremented?

**Answer:** No. Count `errorCount` only for `Diagnostic.Kind.ERROR`; keep `NOTE` as an informational event.

**Question 16.** If a service compiling user-submitted code uses `-proc:none`, is it completely safe?

**Answer:** Not yet. That is only one mitigation for annotation processors. You still need isolation, resource quotas, whitelisted options, classpath management, and must never run untrusted bytecode in a process containing secrets.

## 15. Takeaways

- **`DiagnosticCollector` collects diagnostics, `CompilationTask.call()` reports the result**; these two sources complement each other.
- **`ERROR` is different from `WARNING` and `MANDATORY_WARNING`**. Compilation can still succeed with warnings.
- **Locations do not always exist**: `getSource()` can be null; `getPosition()/getLineNumber()/getColumnNumber()` can be `Diagnostic.NOPOS`.
- **Line/column are usually 1-based; offsets are 0-based character offsets**, not UTF-8 byte positions.
- **Messages and codes are not a stable protocol:** `getMessage(Locale)` depends on implementation/locale/JDK, `getCode()` can be null.
- **Separate three phases:** compiler setup, compile diagnostics/artifacts, and runtime execution.
- **One compilation pass = one collector + file manager/output scope + source snapshot** to avoid stale results and races.
- **The JDK compiler must be present**, and annotation processors/options/classpath must be controlled, especially when compiling untrusted code.
- **Test success, error, and warning cases**; test the stdout of the specific environment and do not force the UI to depend on a fixed compiler message string.

### Official documentation (Java SE 17)

- [`javax.tools.JavaCompiler` — `getTask` and using `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [`javax.tools.Diagnostic` — kind, source, line/column, position, code, message](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [`javax.tools.DiagnosticCollector` — collecting the diagnostics list](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [`javax.tools.ToolProvider` — getting the system Java compiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [`javax.tools.JavaFileObject` and `SimpleJavaFileObject` — compilation sources](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [`javax.tools.StandardJavaFileManager` — input/output and resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html)
- [Java 17 `javac` options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
