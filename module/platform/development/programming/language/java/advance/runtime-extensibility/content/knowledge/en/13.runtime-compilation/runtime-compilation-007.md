# Collecting Errors, Warnings, Source Locations, and Messages with DiagnosticCollector

When a Java program **compiles source code at runtime** using `javax.tools.JavaCompiler`, users need more than just `true` or `false`: **which file failed, at which line/column, what the error message is, and whether any warnings occurred even when compilation succeeded**. The `javax.tools.DiagnosticCollector` API collects those diagnostics as structured data for display in IDEs, rule editors, code generators, Java learning tools, or plugin systems.

The core distinction is:

- **Compilation task outcome**: `CompilationTask.call()` returns `Boolean.TRUE` when the compiler reports success and `Boolean.FALSE` when it reports failure; infrastructure or task-initialization errors can also surface as exceptions.
- **Diagnostic**: each error, warning, or note has a `kind`, `source`, location, and `message`. Multiple diagnostics can occur in a single compilation run.
- **DiagnosticCollector**: a built-in implementation of `DiagnosticListener` that stores diagnostics in a list for the application to read afterward or while the compiler reports issues.

Source code that **compiles successfully can still have WARNINGs**; conversely, do not infer the entire task succeeded merely because your counted error list is 0. The return status of `call()` is the task outcome, while diagnostics explain what happened.

## 1. Diagnostic Collection Pipeline

Typical flow on JDK 17+:

```text
Java source (.java or in-memory JavaFileObject)
                       |
                       v
            JavaCompiler.getTask(...)
             /          |           \
            /           |            \
StandardJavaFileManager  options    DiagnosticCollector
            \           |            /
             \          |           /
                 task.call()
                     |
       +-------------+-------------+
       |                           |
  boolean success          collector.getDiagnostics()
                                   |
                            Diagnostic<?>
                                   |
                kind / source / line / column /
                 position / code / message
                                   |
                  log / API / IDE / error report
```

The API types belong to the standard `java.compiler` module, package `javax.tools`:

| API | Role |
|---|---|
| `ToolProvider.getSystemJavaCompiler()` | Obtains the Java compiler present in the runtime; may return `null` if the image lacks a compiler |
| `JavaCompiler` | Creates compilation tasks; works with file managers and listeners |
| `JavaCompiler.CompilationTask` | Specific compilation task; `call()` executes one compilation pass |
| `StandardJavaFileManager` | Manages `JavaFileObject`s from files, classpath/module path, and output locations |
| `JavaFileObject` | Represents a Java source/output used by the compiler; can point to a file or be created in memory |
| `DiagnosticListener<S>` | Interface receiving diagnostics via the `report(...)` callback |
| `DiagnosticCollector<S>` | Listener that records diagnostics for retrieval via `getDiagnostics()` |
| `Diagnostic<S>` | A single diagnostic and its properties for display/analysis |

**Contrast with `compiler.run(...)`:** `run` is convenient as a command-line-style compile invocation taking input/output streams and returning an exit status. When you need a **structured list of errors**, use `getTask(...)` with `DiagnosticCollector`; do not parse `javac` console output with regex.

## 2. Initializing the Collector and Passing It Properly to the Compiler

Minimal setup pattern:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "A JDK containing the Java compiler is required");
}

DiagnosticCollector<JavaFileObject> collector =
        new DiagnosticCollector<>();

try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                collector, Locale.ROOT, StandardCharsets.UTF_8)) {

    Iterable<? extends JavaFileObject> units =
            manager.getJavaFileObjectsFromPaths(List.of(sourcePath));

    JavaCompiler.CompilationTask task = compiler.getTask(
            null,                         // writer for miscellaneous output
            manager,                      // file manager
            collector,                    // listener receiving diagnostics
            List.of("--release", "17"),   // compiler options
            null,                         // classes for annotation processing
            units);                       // source units

    boolean success = Boolean.TRUE.equals(task.call());
    List<Diagnostic<? extends JavaFileObject>> diagnostics =
            List.copyOf(collector.getDiagnostics());
}
```

This is an **illustrative snippet inside a method**, assuming `sourcePath` is an existing `Path` and classes from `javax.tools`, `java.nio`, and `java.util` are imported. A complete, compilable example is in Section 4.

Details to understand:

1. **Match the generic type.** For the Java compiler, `DiagnosticCollector<JavaFileObject>` matches the `JavaFileObject` type of compilation units. `getDiagnostics()` returns a list of `Diagnostic<? extends JavaFileObject>`.
2. **Pass the collector into `getTask`.** Without a listener, the compiler may send diagnostics to the writer/console stream, leaving the application without a structured list to inspect.
3. **Pass it into `getStandardFileManager` as well if you want to capture diagnostics from the file manager** when reading files or resolving locations. Using the same collector in both places centralizes notifications.
4. **One task is one compilation run.** Never invoke `call()` multiple times on the same `CompilationTask`. For two independent compilations, create a new task and preferably a new collector.
5. **Close the file manager** using `try-with-resources`. Having a `DiagnosticCollector` does not replace file manager resource management.
6. **Take a snapshot** if you need to keep results after the run: `List.copyOf(collector.getDiagnostics())` creates a list independent of the collector's view.

`getDiagnostics()` returns a **list view**, not a file format or JSON. You can iterate over it and map entries into your own DTOs for UI/API responses. The list may contain multiple diagnostics for one source and across multiple sources in a single compilation run.

## 3. Data Fields in Diagnostic

Each `Diagnostic<? extends JavaFileObject>` provides classification and location information.

| Method | Meaning | Notes |
|---|---|---|
| `getKind()` | `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, or `OTHER` | Not limited to `ERROR`/`WARNING` |
| `getSource()` | `JavaFileObject` associated with the diagnostic | **Can be `null`** when the diagnostic is global |
| `getLineNumber()` | Line number of the issue | Typically **1-based**; may be `Diagnostic.NOPOS` |
| `getColumnNumber()` | Column number of the issue | Typically **1-based**; may be `Diagnostic.NOPOS` |
| `getPosition()` | Character offset from the start of the source | **0-based**, not line/column or byte offset |
| `getStartPosition()` | Start offset of the source span identified by the compiler | Position may be unavailable |
| `getEndPosition()` | End offset of the identified source span | Do not assume every implementation highlights the exact same token |
| `getCode()` | Implementation-supplied diagnostic code | **Implementation-dependent**, may be `null` |
| `getMessage(Locale)` | Message explaining the error/warning per locale | Wording may vary by compiler/JDK/locale |

### 3.1. Classification: ERROR, WARNING, and MANDATORY_WARNING

```java
Diagnostic.Kind kind = diagnostic.getKind();

boolean isError = kind == Diagnostic.Kind.ERROR;
boolean isWarning =
        kind == Diagnostic.Kind.WARNING
        || kind == Diagnostic.Kind.MANDATORY_WARNING;
```

The snippet above illustrates classification logic where a `diagnostic` variable is in scope. If a dashboard only counts `WARNING`, it will **miss `MANDATORY_WARNING`**, a kind frequently emitted when `javac` warns about unchecked operations. `NOTE` can provide supplemental hints; `OTHER` covers diagnostics outside the common kinds.

**Warnings do not mean failure.** The compiler can complete with warnings. Conversely, with flags such as `-Werror`, compiler policy can turn a compilation with warnings into a failure. Applications should inspect **both `success` and the diagnostic list**, without altering the meaning of `call()`.

### 3.2. When Source or Position Is Absent

Some diagnostics are project-wide, module, option, or environment errors not tied to a specific token:

```java
String sourceName = diagnostic.getSource() == null
        ? "<global>"
        : diagnostic.getSource().getName();

long line = diagnostic.getLineNumber();
long column = diagnostic.getColumnNumber();

String location = (line == Diagnostic.NOPOS
        || column == Diagnostic.NOPOS)
        ? "unknown"
        : line + ":" + column;
```

Never call `diagnostic.getSource().getName()` without a `null` check. The value `Diagnostic.NOPOS` (typically `-1`) indicates **no valid position exists**; do not display it as "line -1, column -1" as if it were a real source location.

### 3.3. Character Offsets and Editor Display

- `getLineNumber()` and `getColumnNumber()` are display positions by line/column, normally 1-based.
- `getPosition()`/`getStartPosition()`/`getEndPosition()` are **character offsets** from the start of the `JavaFileObject`, not UTF-8 byte offsets. With Java `String`/`CharSequence`, UI code must account for UTF-16 code units, surrogate pairs, line endings, and tabs when mapping to cursor positions.
- The exact position and underline span chosen by the compiler can vary across versions. Do not blindly add or subtract 1 on every field.
- When displaying in an editor, use a source revision **matching the revision sent to compilation**. If a user edits the source while compilation is in flight, old diagnostic positions can point to the wrong lines.
- When source is created in memory, the `JavaFileObject`'s URI/name associates the diagnostic with a "virtual file"; that does not imply a real file exists on disk.

## 4. Runnable Java 17 Example: Collecting Errors and Warnings from In-Memory Source

This example uses `SimpleJavaFileObject` to pass string source code directly to the compiler without creating `Broken.java` or `Unchecked.java` on disk beforehand. Two independent compilation runs demonstrate:

- **ERROR** caused by assigning a `String` to an `int` variable.
- **Unchecked warning** caused by calling `add` on a raw `List` when `-Xlint:unchecked` is enabled.

In the example, the compiler emits class files into a temporary directory. Compiled classes **are not automatically loaded or executed**.

Save file **`DiagnosticCollectorDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DiagnosticCollectorDemo {

    // A JavaFileObject holding source code in memory.
    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String simpleName, String code) {
            super(URI.create("string:///" + simpleName + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private record Result(
            boolean success,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {}

    private static Result compile(
            JavaCompiler compiler, JavaFileObject unit, Path outputDir)
            throws IOException {

        // Use a fresh collector for each compilation task.
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-Xlint:unchecked",
                    "-d", outputDir.toString());

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, collector, options, null, List.of(unit));

            boolean success = Boolean.TRUE.equals(task.call());
            return new Result(
                    success,
                    List.copyOf(collector.getDiagnostics()));
        }
    }

    private static String position(long value) {
        return value == Diagnostic.NOPOS
                ? "unknown"
                : Long.toString(value);
    }

    private static void printResult(String label, Result result) {
        long errors = result.diagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();

        long warnings = result.diagnostics().stream()
                .filter(d ->
                        d.getKind() == Diagnostic.Kind.WARNING
                        || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING)
                .count();

        System.out.println(label + " success=" + result.success()
                + " errors=" + errors + " warnings=" + warnings);

        for (Diagnostic<? extends JavaFileObject> d :
                result.diagnostics()) {

            String source = d.getSource() == null
                    ? "<global>"
                    : d.getSource().getName();

            System.out.println("  kind=" + d.getKind()
                    + " source=" + source
                    + " line=" + position(d.getLineNumber())
                    + " column=" + position(d.getColumnNumber()));

            // Use Locale.ROOT to request messages independent of the OS locale.
            System.out.println("  message=" + d.getMessage(Locale.ROOT));
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                    "Java compiler is unavailable in this runtime");
        }

        JavaFileObject broken = new Source("Broken", """
                class Broken {
                    int number = "oops";
                }
                """);

        JavaFileObject unchecked = new Source("Unchecked", """
                import java.util.List;
                import java.util.ArrayList;
                class Unchecked {
                    void run() {
                        List raw = new ArrayList();
                        raw.add("hello");
                    }
                }
                """);

        Path outputDir = Files.createTempDirectory("java-diagnostics-");

        printResult("broken",
                compile(compiler, broken, outputDir));
        printResult("unchecked",
                compile(compiler, unchecked, outputDir));
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 DiagnosticCollectorDemo.java
java DiagnosticCollectorDemo
```

**Notable output:** on standard `javac` supporting `--release 17` and `-Xlint:unchecked`, the two summary lines look like:

```text
broken success=false errors=1 warnings=0
unchecked success=true errors=0 warnings=1
```

The program also prints diagnostic lines **immediately after each summary line**. Example diagnostics from those `javac` runs:

```text
  kind=ERROR source=/Broken.java line=2 column=18
  message=incompatible types: java.lang.String cannot be converted to int
```

and:

```text
  kind=MANDATORY_WARNING source=/Unchecked.java line=6 column=16
  message=unchecked call to add(E) as a member of the raw type java.util.List
```

**The output blocks above are separated for explanation, not a continuous stdout stream.** In actual stdout, `broken`'s error message appears before the `unchecked` summary line. The wording of `getMessage(Locale.ROOT)`, warning classification, or position details can change across implementations and JDK versions; do not treat message text as an immutable API contract.

### 4.1. Why Does This Data Appear?

1. `Source` extends `SimpleJavaFileObject`, using URIs `string:///Broken.java` and `string:///Unchecked.java`. The compiler reads the source via `getCharContent(...)`, so `Diagnostic.getSource()` still has a source object even without `.java` files on disk.
2. `--release 17` instructs `javac` to compile against Java 17 language features and APIs. The example uses Java text blocks and records, both supported in Java 17.
3. `-Xlint:unchecked` tells the compiler to report unchecked generic operations; calling `add` on raw `List` triggers a warning. In `javac`, that warning kind can be `MANDATORY_WARNING`, which is why the example counts both warning kinds.
4. `-proc:none` disables annotation processing during the demo so annotation processors do not introduce extra side effects.
5. Each compilation uses **its own collector**. Errors in `Broken` are not mixed into `Unchecked`'s diagnostics.
6. `Result` holds a snapshot of the diagnostic list before the file manager closes. `printResult` formats each diagnostic's kind, source, line, column, and message.
7. `outputDir` is where the compiler can write class files. The example only compiles and inspects without executing the generated class. Real applications must manage temporary directory lifecycles and delete outputs when no longer needed.

### 4.2. If You Need More Precise Positions

Inside the `for` loop in `printResult`, you can also read:

```java
long position = d.getPosition();
long start = d.getStartPosition();
long end = d.getEndPosition();
String code = d.getCode();

System.out.printf(
        "offset=%d start=%d end=%d code=%s%n",
        position, start, end, code);
```

This is an **addition for the loop** in the program above, not a standalone program. Use these offsets to highlight tokens/ranges in an editor when valid, while still handling `Diagnostic.NOPOS`. `getCode()` is useful for analyzers or telemetry within a specific compiler, yet **carries no compatibility guarantee across compilers or versions**.

## 5. Presenting Source Locations and Messages to Learners

A diagnostic should be mapped into its own data structure rather than serializing the entire `Diagnostic` object directly to JSON. Conceptual example:

```json
{
  "severity": "ERROR",
  "source": "Broken.java",
  "line": 2,
  "column": 18,
  "startOffset": 31,
  "message": "incompatible types: java.lang.String cannot be converted to int",
  "compiler": "javac",
  "sourceRevision": "revision-of-submitted-source"
}
```

This is a **DTO shape example**, not JSON output from the program in Section 4. In a real product, `startOffset` must come from the compiler's `getStartPosition()`, not be guessed from `line`/`column`; numeric values in the JSON are purely illustrative. `sourceRevision` is an **application-added** identifier so the UI matches diagnostics to the exact submitted source revision.

In an editor, an error can be rendered as:

```text
Broken.java:2:18 [ERROR]
    int number = "oops";
                 ^
incompatible types: java.lang.String cannot be converted to int
```

Line and column should map to the exact compiled source; tabs, CRLF, and Unicode characters can make visual columns differ from string offsets, so follow the editor's mapping rules. For diagnostics without a location, place the message in a "project errors" area instead of falsely attaching it to line 1.

**Locale and messages:** `diagnostic.getMessage(Locale.ROOT)` requests a message in the root locale; the API also accepts `Locale.forLanguageTag("vi")` or `Locale.getDefault()`. However, compilers **are not required to ship Vietnamese translations**. A UI may translate messages itself to aid learners, while retaining the original message for reference. Never parse meaning out of an English message string for business logic.

## 6. Multiple Sources, Multiple Compilations, and Aggregation Strategy

In a real dynamic compilation tool, a single task can take multiple `JavaFileObject`s:

```java
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(
                List.of(pathA, pathB, pathC));

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, collector, options, null, units);
Boolean success = task.call();
```

This is an **illustrative snippet** with `manager`, `collector`, `options`, `pathA`, `pathB`, and `pathC` already declared. A diagnostic attaches to its corresponding `JavaFileObject` when the compiler identifies a source. Do not assume every error's source is "the first file" or "the main class."

A system accepting Java sources typically needs these steps:

1. **Identify source snapshot**: source ID, filename, content/encoding, and hash or revision at submission time.
2. **Create a task/collector per job**: never mix two `call()` runs into the same result set without a job ID.
3. **Compile in a deterministic environment**: `--release`, classpath/module path, compiler options, and output location must match.
4. **Read results**: `success` and diagnostics—including `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`.
5. **Normalize display data**: map source names, convert `NOPOS` to `"unknown"`, cap message lengths, and attach compiler/version info.
6. **Persist/send to UI**: if sorting is needed, explicitly define sort order (file, line, column, severity) rather than relying on emission order as an invariant standard.
7. **Separate compile errors from infrastructure errors**: invalid compiler options, failure to open file manager, unwritable class output, or missing compiler each require distinct error codes.

### 6.1. When Do You Need Real-Time Diagnostic Streaming?

`DiagnosticCollector` is a simple listener for retrieving a list of diagnostics. If you want to **push each diagnostic as soon as the compiler reports it**, implement `DiagnosticListener<JavaFileObject>`'s `report(...)` method to forward entries to a UI/log queue, or record them while reporting progress. Avoid updating UI state from an inappropriate thread and avoid treating each individual callback as the final verdict on overall success.

Illustrative listener snippet:

```java
DiagnosticListener<JavaFileObject> listener = diagnostic -> {
    // Collect/forward diagnostic per application contract.
    // Do not treat a NOTE/WARNING as compilation failure.
    System.out.println(diagnostic.getKind() + ": "
            + diagnostic.getMessage(Locale.ROOT));
};
```

This snippet goes inside a method and requires importing `javax.tools.DiagnosticListener`, `javax.tools.JavaFileObject`, and `java.util.Locale`. When writing a custom listener instead of a collector, you are responsible for storage, thread safety, and error formatting. For "collect for post-compile analysis," `DiagnosticCollector` is usually sufficient.

### 6.2. Do Not Catch API Exceptions and Turn Them into Source Diagnostics

There is a major difference between:

- **Source code errors**: e.g., invalid types; the compiler emits `Diagnostic.Kind.ERROR` and `call()` reports failure.
- **Quality/type warnings**: e.g., unchecked operations; emitted as `WARNING` or `MANDATORY_WARNING` while compilation can still succeed.
- **Task configuration errors**: invalid options can throw `IllegalArgumentException` when creating the task; they do not automatically appear as source-line diagnostics.
- **Missing compiler**: `ToolProvider.getSystemJavaCompiler() == null`; there is no `CompilationTask` to run.
- **I/O errors**: missing sources, unwritable outputs, broken file manager; report environment errors and context, which can happen before or during task execution.
- **Post-compile execution errors**: `ClassNotFoundException`, `LinkageError`, or runtime exceptions from invoked methods belong to the **load/run stage**, not to compilation diagnostics.

Therefore, a dynamic compilation API should return a result containing at least: job status, compiler `success` when applicable, diagnostic list, infrastructure error type (if any), source version ID, and approved compiler options.

## 7. Compiler Options Affect Message Count and Kinds

The diagnostic set **is not fixed for the same source** if options or compiler versions change.

| Option | Effect |
|---|---|
| `--release 17` | Enforces language/API level corresponding to Java 17 |
| `-Xlint:unchecked` | Requests diagnostics for unchecked generic operations |
| `-Xlint:deprecation` | Enables additional warnings for deprecated API usage per lint policy |
| `-Werror` | Treats warnings as compilation errors per compiler policy, potentially causing `success=false` |
| `-proc:none` | Skips running annotation processors during the compilation |
| `-d <dir>` | Chooses output directory for class files |
| `-classpath` / `--module-path` | Affects type/module resolution and missing-dependency errors |

Do not assume a JDK accepts every future flag or flags specific to another compiler. In a service accepting user code, **do not let users pass arbitrary compiler flags**, especially flags altering classpath, modules, output paths, or annotation processing. Maintain an allowlist of options, validate inputs, and log the safe configuration.

## 8. Testing DiagnosticCollector for Its Intended Purpose

A practical test suite should cover both compiler status and diagnostic details:

| Case | What to Verify |
|---|---|
| Valid Java code, no warnings | `success=true`, zero `ERROR` diagnostics |
| Type mismatch or missing syntax token | `success=false` and `ERROR` pointing to the right source |
| Raw generic + `-Xlint:unchecked` | `WARNING` or `MANDATORY_WARNING` present, even when `success=true` |
| Same source, lint disabled | Warning set may be smaller; do not assert on message wording |
| Compiling multiple sources | `getSource()` maps to the corresponding source unit when available |
| Global diagnostic | `source=null` or `position=NOPOS` handled safely |
| Warning + `-Werror` | Do not infer success simply by counting `ERROR`s |
| Multi-line text with Unicode, tabs, CRLF | Display positions map accurately onto the source snapshot |
| Compiler absent | Returns meaningful environment error; no `NullPointerException` |
| Wrong classpath/module path | Distinguishes source errors, dependency errors, and task config errors |
| Two consecutive jobs | Separate collectors or job IDs; no cross-contamination |
| Source edited while job runs | Displayed diagnostics stay tied to the compiled source revision |

**Do not try to test an error message by matching a long English string verbatim.** Compilers/JDKs can rephrase wording while keeping meaning intact. Assert on `kind`, compile status, source name, valid locations, and properties important to your application contract. When testing exact line/column numbers, pin both the source and compiler version.

## 9. Security and Operational Limits

`DiagnosticCollector` helps **observe compilation results**; it **does not make source code safe**. Untrusted code that compiles successfully can still read the filesystem, open network connections, or spawn processes if executed with the application's privileges. Keep in mind:

- Accept source code only per policy; enforce limits on source size, file count, time/CPU/memory, and number of retained or UI-returned diagnostics.
- Restrict compiler options and read/write paths; never let classpath, annotation processors, or output directories be arbitrarily user-specified.
- If source is untrusted, consider **compiling/running inside an isolated process or container** with restricted OS privileges. A class loader **is not a sandbox**.
- Do not expose sensitive absolute paths, OS usernames, or secret configuration values via `getSource().getName()` or verbatim messages if they contain internal details; normalize exposed paths.
- Editor error checks should not recompile synchronously on every keystroke under heavy load; use debouncing, lifecycle job cancellation, and source revisions.
- After collecting diagnostics, still decide whether to allow loading the class into runtime using separate **business policies, code checks, and trust boundaries**.

## 10. Common Misconceptions

1. **“`DiagnosticCollector` compiles source itself.”** False: it receives diagnostics; the compiler and task perform compilation.
2. **“`compiler.run` returns a Java object list of errors.”** No: `getTask` with a listener is the structured collection path.
3. **“No ERROR means compilation succeeded.”** Insufficient: check `CompilationTask.call()` and account for infrastructure failures/`-Werror`.
4. **“Warnings are always only `Diagnostic.Kind.WARNING`.”** False: there is also `MANDATORY_WARNING`.
5. **“Every diagnostic has a source and line/column.”** False: `source == null` or `position == Diagnostic.NOPOS` can occur.
6. **“Line/column are byte offsets.”** False: line/column express line-and-column positions; character offsets come from other methods.
7. **“`getMessage(Locale)` is a stable error code.”** False: text depends on compiler and locale; `getCode()` is also implementation-dependent.
8. **“One shared collector works for all requests.”** That easily mixes results across compilations; bind a collector per job.
9. **“Successful source compilation means the class is loaded/running.”** False: output classes still require separate class loading/runtime mechanisms.
10. **“Collecting diagnostics is enough to sandbox dynamic code.”** False: runtime security and resource isolation are separate concerns.

### Java SE 17 Documentation

- [DiagnosticCollector — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [Diagnostic — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [DiagnosticListener — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticListener.html)
- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)

**Remember:** for each dynamic compilation run, create a `DiagnosticCollector<JavaFileObject>`, pass it to `JavaCompiler.getTask(...)`, call `call()`, and read `getDiagnostics()` to obtain **kind, source, line/column, offsets, and messages**. Always check for `null`/`Diagnostic.NOPOS`, distinguish warnings from errors, track the matching source revision, and use `success` to reflect the true compilation outcome.
