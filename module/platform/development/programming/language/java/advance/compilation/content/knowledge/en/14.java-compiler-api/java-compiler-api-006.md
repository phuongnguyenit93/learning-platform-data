# Collecting Diagnostics with DiagnosticCollector, Error Positions, and Diagnostic Severity

## Objectives

After this lesson, you can:

1. Use the Java Compiler API to invoke the compiler from a Java program instead of only running `javac` in the terminal.
2. Attach `DiagnosticCollector<JavaFileObject>` to `JavaCompiler.CompilationTask` to retrieve errors, warnings, and notes as structured objects.
3. Explain `Diagnostic.Kind` and the differences among `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`.
4. Retrieve source files, line numbers, columns, offsets, and error spans using `getSource()`, `getLineNumber()`, `getColumnNumber()`, `getPosition()`, `getStartPosition()`, and `getEndPosition()`.
5. Properly handle `Diagnostic.NOPOS`, `null` sources, localized messages, and compiler-dependent diagnostic codes.
6. Practice two Java 17+ scenarios: compile-time type errors from an in-memory source string and generic warnings when compiling a Java file on disk.
7. Build reproducible diagnostic reports, distinguishing compile results from exceptions in an executed program.

The lesson focuses on **collecting compiler diagnostics, error positions, and diagnostic severity**. No third-party libraries or IDE are required.

## 1. How Does a Diagnostic Differ from Messages Printed to stderr?

When compiling Java source, the compiler may emit:

- Syntax errors: missing `;`, unclosed braces/parentheses.
- Type-checking errors: assigning a `String` to an `int` variable, calling a nonexistent method.
- Warnings: raw generics, unchecked conversions, deprecated APIs, behaviors with checks enabled via `-Xlint`.
- Notes: supplementary information from the compiler or an annotation processor.

On the command line, `javac` usually presents these messages as text containing a filename, line number, source snippet, and caret. Example of the **meaning** of an error (not fixed stdout):

~~~text
error: incompatible types: String cannot be converted to int
~~~

If you write an IDE, code-grading service, or build tool, parsing messages with regex matching words like `error:` or `warning:` is very fragile: text can change across JDKs, compiler providers, locales, and options.

The Java Compiler API provides the **`Diagnostic<S>`** interface, containing structured fields such as diagnostic kind, source, position, code, and message text. `DiagnosticCollector<S>` is a convenient listener that collects `Diagnostic` objects for you to read afterward.

~~~text
Source: JavaFileObject(s)
         |
         v
JavaCompiler.getTask(..., diagnosticListener, ...)
         |
         v
CompilationTask.call()
         |
         +--- boolean compile success / failure
         |
         +--- DiagnosticListener.report(diagnostic)
                      |
                      v
                DiagnosticCollector
                      |
                      v
               getDiagnostics()
                      |
                      +--- kind / code / message
                      +--- source file
                      +--- line / column / offsets
~~~

**Do not confuse them:** the collector does not fix code itself, does not recompile automatically, and does not run the compiled program. It only holds the diagnostics reported by the tool during the compilation task.

## 2. Components in the Java Compiler API

| API | Role |
| --- | --- |
| `javax.tools.ToolProvider` | Finds the system Java compiler if provided by the runtime |
| `javax.tools.JavaCompiler` | Creates compilation tasks via API |
| `JavaCompiler.CompilationTask` | A compiler task; `call()` executes the task |
| `javax.tools.DiagnosticListener<S>` | Receives each message via `report(...)` |
| `javax.tools.DiagnosticCollector<S>` | Listener implementation that stores a list |
| `javax.tools.Diagnostic<S>` | A structured error/warning/note |
| `javax.tools.JavaFileObject` | Represents a Java source/class file |
| `javax.tools.SimpleJavaFileObject` | Utility class for creating custom source objects |
| `javax.tools.StandardJavaFileManager` | Provides file objects and controls sources/outputs |
| `javax.tools.Diagnostic.Kind` | Enum classifying diagnostic severity |

These core APIs in package `javax.tools` belong to Java module `java.compiler`. The compile-time model and diagnostics are not Java runtime Reflection: there is no need to load the `Broken` class for the compiler to detect an invalid type assignment in its source.

### 2.1 Process of Attaching a Collector to a Task

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
DiagnosticCollector<JavaFileObject> collector =
        new DiagnosticCollector<>();

try (StandardJavaFileManager fileManager =
        compiler.getStandardFileManager(
                collector, Locale.ROOT, StandardCharsets.UTF_8)) {

    JavaCompiler.CompilationTask task = compiler.getTask(
            null, fileManager, collector, options, null, sources);

    boolean compiled = Boolean.TRUE.equals(task.call());

    for (Diagnostic<? extends JavaFileObject> diagnostic
            : collector.getDiagnostics()) {
        // Process each diagnostic.
    }
}
~~~

This is an **illustrative code snippet inside a method**, not a standalone runnable program: it needs imports, a `null` check on compiler, and `options` and `sources` variables. Full example in section 4.

Notes:

- `getTask(...)` creates the task; `task.call()` actually requests compilation.
- The listener argument in `getTask(...)` is what receives structured diagnostics.
- `getStandardFileManager(...)` accepts a listener for diagnostics belonging to the file manager mechanism.
- The first writer argument of `getTask` is for auxiliary tool output. DiagnosticListener is not synonymous with capturing all of `System.out` or `System.err`.
- `getDiagnostics()` returns collected diagnostics; to compare two compilations, there should be a **new collector for each task**.
- Close the file manager using `try-with-resources`; a task cannot be reused to `call()` a second time.

### 2.2 The Compiler Might Not Exist

`ToolProvider.getSystemJavaCompiler()` can return `null` when the runtime image does not provide a compiler, such as a custom Java runtime build. A full JDK usually includes a compiler, yet you should not assume every Java runtime environment has one.

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "Java compiler is unavailable in this runtime");
}
~~~

This snippet needs `JavaCompiler` and `ToolProvider` imports and must be placed inside a method. If building a source compilation service, this check helps report environment errors clearly instead of `NullPointerException`.

### 2.3 Task Result Differs from Diagnostics

Normally `Boolean.TRUE.equals(task.call())` is true when compilation succeeds and false when there are errors. Yet do not infer mechanically:

- Having warnings means the task is always false: **false**, warnings usually do not prevent compilation.
- Having no ERROR in the collector means the whole pipeline definitely succeeded: **false**, errors may occur outside the diagnostic stream.
- `getDiagnostics().isEmpty()` means the application will run correctly: **false**, that is only the information reported by the compiler.
- Every exception in a file manager or annotation processor is converted into `Diagnostic.Kind.ERROR`: **not guaranteed**.

When building tools, record **all** of: the task boolean, the diagnostics list, compiler options, and exceptions thrown outside the diagnostic stream.

## 3. Classifying Diagnostic.Kind

Basic kinds in Java 17:

| `Diagnostic.Kind` | Meaning | Classification in UI |
| --- | --- | --- |
| `ERROR` | Compilation error | Error |
| `WARNING` | Ordinary warning | Warning |
| `MANDATORY_WARNING` | Mandatory warning per tool rules | Warning |
| `NOTE` | Note, supporting information | Info |
| `OTHER` | Remaining diagnostic kind | Other/Info depending on policy |

If wanting to count the warning group, check **both** `WARNING` and `MANDATORY_WARNING`:

~~~java
long warnings = collector.getDiagnostics().stream()
        .filter(d ->
            d.getKind() == Diagnostic.Kind.WARNING
            || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING)
        .count();
~~~

This is a snippet, assuming `collector` is declared. Do not use the enum's `ordinal()` as a severity level: enum declaration order is not a display-priority contract.

### 3.1 Compiler Options Affect Diagnostic Counts

A source with raw generics may compile normally, yet when adding `-Xlint:unchecked` the compiler emits detailed warnings. A source calling a deprecated API may emit additional warnings with `-Xlint:deprecation`.

When adding `-Werror`, the build may **fail because of warnings**. Do not assume every `WARNING` has its `Kind` changed to `ERROR`: the compiler may report the original warning and add a diagnostic related to the warning-handling policy.

To compare statistics between two builds, you must know the same source, compiler version, classpath, `--release`, `-Xlint` options, and whether `-Werror` is set.

### 3.2 Notes from Annotation Processors

An annotation processor can emit:

~~~java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.NOTE,
        "Processed one element",
        element);
~~~

This is a snippet **inside a processor**, with variable `element` of type `javax.lang.model.element.Element`. `Messager` reports messages to the compile diagnostic mechanism. When javac forwards it to the listener, you may receive `NOTE` in the collector.

If the processor provides the element/annotation location, the compiler can associate the diagnostic with the source. However, not every `NOTE` has a file, line, and column; display code must handle missing positions.

## 4. Complete Example A: Capturing Errors of an In-Memory Source

We build a **valid Java driver** named `DiagnosticCollectorDemo`. The driver uses the Compiler API to compile another source named `sample.Broken`. The `Broken` source **intentionally has a type error** to produce `Diagnostic.Kind.ERROR`.

JDK 17 or newer is required. Check:

~~~bash
java -version
javac -version
~~~

### 4.1 Create DiagnosticCollectorDemo.java

~~~java
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

public class DiagnosticCollectorDemo {

    private static final class StringSource extends SimpleJavaFileObject {
        private final String sourceCode;

        StringSource(String className, String sourceCode) {
            super(
                    URI.create("string:///"
                            + className.replace('.', '/')
                            + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.sourceCode = sourceCode;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return sourceCode;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK with Java compiler required");
        }

        String brokenCode = String.join("\n",
                "package sample;",
                "public class Broken {",
                "    public static void main(String[] args) {",
                "        int number = \"wrong\";",
                "    }",
                "}"
        ) + "\n";

        JavaFileObject source =
                new StringSource("sample.Broken", brokenCode);
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        Path output = Files.createTempDirectory("compile-diagnostics-");

        try (StandardJavaFileManager fileManager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    fileManager,
                    collector,
                    options,
                    null,
                    List.of(source)
            );

            boolean compiled = Boolean.TRUE.equals(task.call());
            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            System.out.println("compiled=" + compiled);
            System.out.println("errors=" + errors);

            for (Diagnostic<? extends JavaFileObject> d
                    : collector.getDiagnostics()) {
                if (d.getKind() == Diagnostic.Kind.ERROR) {
                    System.out.println(
                            "ERROR at line " + d.getLineNumber());
                    System.out.println(
                            "positionKnown="
                            + (d.getPosition() != Diagnostic.NOPOS));
                }
            }
        }
    }
}
~~~

Explanation:

- `StringSource` extends `SimpleJavaFileObject` to supply source via `getCharContent`.
- The source URI is `string:///sample/Broken.java`; this is the logical name of the Java source, without requiring a file to exist on disk.
- `Files.createTempDirectory` creates a real output directory for the compiler. That path is not printed to stdout so expected output does not depend on random names.
- `-proc:none` disables annotation processing in the experiment, avoiding external processors generating extra messages.
- `--release 17` restricts the language, platform APIs, and class-file target to Java 17.
- `DiagnosticCollector` is passed into the compiler task. The driver counts errors and reads the line number on each `Diagnostic`.
- The `Broken` source is built with `String.join("\n", ...)` so lines have a clear order. The line with the type error is specifically **line 4**.
- The file manager is closed with `try-with-resources`. The temporary output directory may still remain after the run; a real tool should have an appropriate cleanup mechanism for the outputs it creates.

**Distinguish two layers:** the `DiagnosticCollectorDemo` program must compile and run successfully; the compiler task **inside** the program is designed to fail when compiling `sample.Broken`.

### 4.2 Compile and Run the Driver on Linux/macOS

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out DiagnosticCollectorDemo.java
java -cp out DiagnosticCollectorDemo
~~~

### 4.3 Compile and Run on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out DiagnosticCollectorDemo.java
java -cp out DiagnosticCollectorDemo
~~~

Stdout with a suitable JDK 17+ javac:

~~~text
compiled=false
errors=1
ERROR at line 4
positionKnown=true
~~~

Columns and full messages are excluded from expected output because **detailed position selection and message text may vary across compilers/providers**.

### 4.4 Try Fixing the Error to Compare

In the `String.join` code, replace the exact line:

~~~java
"        int number = \"wrong\";",
~~~

with:

~~~java
"        int number = 7;",
~~~

These are **two lines of code inside the Java driver**, not two separate programs. Recompile the driver and run; expected output:

~~~text
compiled=true
errors=0
~~~

The `for` loop prints only `ERROR` diagnostics, so after fixing there are no error detail lines. The before-and-after experiment fixes the compiler/options and changes only the compiled source.

## 5. Retrieving Source Name, Line, Column, and Error Position

A `Diagnostic<S>` object allows retrieving fields:

| Method | Meaning |
| --- | --- |
| `getKind()` | Diagnostic kind: error/warning/note... |
| `getSource()` | Source object attached to the diagnostic; may be `null` |
| `getLineNumber()` | Line number starting from **1**, or `NOPOS` |
| `getColumnNumber()` | Column number starting from **1**, or `NOPOS` |
| `getPosition()` | Character offset starting from **0**, or `NOPOS` |
| `getStartPosition()` | Start offset of the error span, may be `NOPOS` |
| `getEndPosition()` | End offset of the error span, may be `NOPOS` |
| `getCode()` | Compiler/provider-dependent diagnostic code, may be `null` |
| `getMessage(Locale)` | Message content localized according to compiler capability |

According to Java SE 17 `Diagnostic`, when a valid position is available:

~~~text
getStartPosition() <= getPosition() <= getEndPosition()
~~~

Line and column count from 1, whereas character offsets count from 0. `Diagnostic.NOPOS` is a sentinel value (in the current API it is `-1`). **Do not use 0 to represent "unknown"**, because offset 0 is the first valid character.

### 5.1 Safe Formatter When Position Is Absent

Example of a utility method you can put in your class:

~~~java
static void printDiagnostic(
        Diagnostic<? extends JavaFileObject> d) {

    String file = d.getSource() == null
            ? "(no source)"
            : d.getSource().getName();

    String where = d.getPosition() == Diagnostic.NOPOS
            ? "(no position)"
            : "line " + d.getLineNumber()
                    + ", column " + d.getColumnNumber();

    System.out.println(d.getKind()
            + " | " + file + " | " + where);
    System.out.println("code=" + d.getCode());
    System.out.println("message=" + d.getMessage(Locale.ROOT));
}
~~~

This is a snippet, requiring imports `javax.tools.Diagnostic`, `JavaFileObject`, and `java.util.Locale`. It is **not a standalone class with `main`**.

If source is absent, do not call `d.getSource().getName()` directly: you will hit `NullPointerException`. If position equals `NOPOS`, do not generate a link to line `-1` or guess that the diagnostic belongs to the first line.

### 5.2 When a Diagnostic Is Not Attached to a Source File

There are tool-level or configuration-level warnings/errors that do not reside in a specific source. In that case, information can look like:

~~~text
source: null
position: NOPOS
line: NOPOS
column: NOPOS
~~~

This is an **illustrative case**, not the fixed output of a specific command. When rendering UI, put the message in a task/project-level message pane instead of highlighting an arbitrary line.

A diagnostic can also have `getSource() != null` yet have no suitable position. Check each field; do not assume merely having a non-null source guarantees valid line/column.

### 5.3 Position Differs from File Byte Offset

The offset the API refers to is the character position in the source. You cannot arbitrarily use it as a **byte offset** in a UTF-8 file: Vietnamese characters can occupy multiple bytes. An editor may use positions based on UTF-16 code units, Unicode code points, or another format; proper mapping is required.

Points that must align when marking positions:

- The exact **source version** passed to the compiler, not a file subsequently edited by the user.
- Newline rules: LF or CRLF.
- Tabs may render visually as multiple columns yet are not simply multiple characters.
- Characters outside the BMP, surrogate pairs, and the editor's position encoding protocol.
- Start/end offsets of diagnostics have their own rules; check the contract and source length before slicing strings.

Do not assume `getStartPosition()` and `getEndPosition()` work directly in `source.substring(start, end)` without checking endpoints and editor conventions. If you only need to attach an initial marker, using verified line/column can be simpler.

### 5.4 Source May Be a Generated Source

An annotation processor can generate Java source and then the compiler reports an error in the newly generated file. Here `getSource()` points to the source analyzed by the compiler, not necessarily the file the user just opened. To link errors back to the source file that triggered the processor, additional information such as originating elements or source mappings maintained by your pipeline is needed. `DiagnosticCollector` does not build arbitrary source maps automatically.

## 6. Complete Example B: Collecting Warnings from a File on Disk

Example A had `ERROR`. Now we need a program that compiles successfully yet has warnings. We use raw generics and enable `-Xlint:unchecked`.

### 6.1 Create src/sample/UncheckedDemo.java

~~~java
package sample;

import java.util.ArrayList;
import java.util.List;

public class UncheckedDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList();
        System.out.println(values.size());
    }
}
~~~

`new ArrayList()` uses a raw type assigned to `List<String>`, causing javac to report an unchecked conversion when `-Xlint:unchecked` is enabled. Changing it to `new ArrayList<>()` removes this kind of warning.

### 6.2 Create FileDiagnosticDemo.java

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class FileDiagnosticDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Compiler unavailable");
        }

        Path output = Path.of("out", "classes");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> sourceFiles =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of("src/sample/UncheckedDemo.java")));

            List<String> options = List.of(
                    "--release", "17",
                    "-Xlint:unchecked",
                    "-proc:none",
                    "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, collector, options, null, sourceFiles);

            boolean compiled = Boolean.TRUE.equals(task.call());

            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            long warnings = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.WARNING
                            || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING)
                    .count();

            System.out.println("compiled=" + compiled);
            System.out.println("errors=" + errors);
            System.out.println("hasWarnings=" + (warnings > 0));
        }
    }
}
~~~

Explanation:

- `getJavaFileObjectsFromPaths` creates source units from real files; no need for `SimpleJavaFileObject` like the in-memory example.
- `Files.createDirectories` ensures the output directory exists.
- `-Xlint:unchecked` instructs the compiler to emit detailed warnings.
- `-proc:none` disables unintended annotation processing in the demo.
- The driver classifies warnings based on the enum, without parsing the word `warning` in the message.
- The source path is a **relative path**; run from the project root where `src/sample/UncheckedDemo.java` is located.

### 6.3 Build and Run

From the project root:

**Linux/macOS:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out FileDiagnosticDemo.java
java -cp out FileDiagnosticDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out FileDiagnosticDemo.java
java -cp out FileDiagnosticDemo
~~~

With a suitable JDK 17+ javac, stdout:

~~~text
compiled=true
errors=0
hasWarnings=true
~~~

This is important: **a warning is not synonymous with compilation failure**.

Run the application source compiled by the driver:

~~~bash
java -cp out/classes sample.UncheckedDemo
~~~

Stdout:

~~~text
0
~~~

Because `values` is an empty list, the size is 0. In a real application, generic warnings should be fixed by declaring consistent types, not just ignored.

### 6.4 When -Werror Is Enabled

If `"-Werror"` is added to `options` alongside `-Xlint:unchecked`, the compiler may treat warnings as a reason to fail the task. Depending on the compiler, the collector may receive the original warning **and** a summary error diagnostic from the warning-as-error policy.

Do not write logic saying "if `warnings > 0`, turn all warnings into ERROR yourself". Keep:

- `compiled` returned by the task;
- `errorCount`;
- `warningCount`;
- compiler options used.

That way a dashboard can accurately present: "Warnings present; build failed due to `-Werror` policy" instead of misdescribing an unchecked warning as a type error in the source.

## 7. Are Messages and Diagnostic Codes Stable?

### 7.1 getMessage(Locale)

~~~java
String message = diagnostic.getMessage(Locale.ROOT);
~~~

This is a snippet inside a method with variable `diagnostic`. The API accepts a `Locale` so the compiler can choose a display language if available. Yet it is not guaranteed that every Java compiler/JDK has a Vietnamese translation or identical wording across releases.

For example, `Locale.forLanguageTag("vi-VN")` can be passed, yet if the compiler lacks a corresponding translation, the message may still appear in another language. `Locale.ROOT` suits certain neutral reports, not a contract that every message is the exact same English string.

**Do not compare natural-language messages literally to determine error types.** Rely on `Kind` and structured fields; text is only for helping humans read.

### 7.2 getCode()

~~~java
String code = diagnostic.getCode();
~~~

Diagnostic codes are **implementation-dependent** and may be `null`. In javac there are internal codes starting with prefixes such as `compiler.err` or `compiler.warn`, yet applications must not assume this is a stable standard enum across every compiler, vendor, and release.

Codes can be used for statistics when a project pins a specific compiler, yet fallbacks are needed for `null` or unknown codes.

### 7.3 Code Differs from Severity

`getKind() == ERROR` speaks about **severity**. `getCode()` (if present) speaks about **the compiler's error category**. Both pieces of data are useful yet do not replace each other.

An application record could be designed as:

~~~text
severity       ERROR / WARNING / INFO
sourceUri      URI | null
line           1-based | null
column         1-based | null
position       0-based | null
compilerCode   string | null
message        localized string
buildId        identifier of compilation task
~~~

This is a **conceptual schema**, not a standard definition enforced by the Java Compiler API. If exporting JSON or LSP, offset/encoding types, null values, and data security rules must be clearly specified.

## 8. Writing a Custom DiagnosticListener for Immediate Handling

`DiagnosticCollector` is suitable for reading the list after compilation. If immediate feedback for the user is needed, a listener callback can be created:

~~~java
DiagnosticListener<JavaFileObject> listener = d -> {
    String source = d.getSource() == null
            ? "(no source)"
            : d.getSource().getName();
    System.out.println(d.getKind() + " | " + source
            + " | " + d.getLineNumber());
};
~~~

This is a snippet needing imports `DiagnosticListener` and `JavaFileObject`. Pass this listener into the corresponding parameter of `compiler.getTask(...)`.

To both collect a list and stream:

~~~java
DiagnosticCollector<JavaFileObject> collector =
        new DiagnosticCollector<>();

DiagnosticListener<JavaFileObject> listener = d -> {
    collector.report(d);
    System.out.println(d.getKind());
};
~~~

In the snippet above, the **wrapper listener** is passed to the task; there are not two independent listener parameters in `getTask`. Avoid sharing one collector across multiple compilation tasks without an isolation policy, especially if running in parallel.

Callbacks should not throw unexpected errors in a service; an exception in a listener can affect the compiler invocation. In real applications, consider buffering, thread safety, backpressure, and error-reporting strategies for the listener itself.

| Mechanism | Suitable When | Note |
| --- | --- | --- |
| `DiagnosticCollector` | Filtering, counting, and exporting final reports | Each task should have its own collector |
| Custom listener | Updating UI/logs as each message arrives | Manage callbacks, storage, and errors yourself |
| Wrapper listener + collector | Needing both streaming and a summary | Pass only the wrapper into the task |

## 9. Diagnostics Do Not Replace Exception Handling

Compiler diagnostics report issues **detected by the compiler in sources/tasks**. Some tool execution or environment errors must be caught through other paths.

| Scenario | Handling |
| --- | --- |
| Source has type error | Collect `Diagnostic.Kind.ERROR` |
| Unchecked warning | Collect warnings when relevant flags are enabled |
| ToolProvider lacks a compiler | Check `compiler == null` |
| Invalid task options | Handle exception per API contract; diagnostics are not guaranteed |
| Cannot read source file | Check file manager/IOException and related diagnostics |
| Annotation processor hits system error | Handle failure/exception outside normal diagnostics |
| Compiled code throws `NullPointerException` at runtime | Use runtime debugger/logs/exception handling, **not** the compiler collector |

Example task handling:

~~~java
boolean compiled;
try {
    compiled = Boolean.TRUE.equals(task.call());
} catch (RuntimeException ex) {
    // This may be an invocation/tooling error outside the diagnostic stream.
    throw ex;
}
~~~

This is a snippet, assuming variable `task` has been created. In real systems, also handle file manager resources, build status, and redacting sensitive data from error logs.

`getDiagnostics().isEmpty()` also does not prove the program works properly at runtime. Network, file, SQL, NPE, or runtime linkage errors are independent groups.

## 10. Choosing Exact Positions When Feeding into an Editor

An IDE/grading tool should do:

1. Receive the source and keep **the content version** passed into compilation.
2. Create a `JavaFileObject` with a stable URI or actual source file.
3. When a diagnostic arrives, associate `getSource()` with the corresponding document.
4. If `getPosition() == NOPOS`, display at the build/file level without fabricating coordinates.
5. If a position exists, verify the source content has not changed.
6. Convert offsets, lines, and columns to editor coordinates according to the agreed encoding.
7. Clearly render `ERROR`, `WARNING`, `NOTE`; do not drop uncommon kinds.
8. Record diagnostic codes/messages as supplementary details.
9. Retain compiler version and flags for reproducibility.
10. Do not require diagnostic output from every compiler to look identical to one `javac` version.

For example, if the compiler states line 4 at URI `string:///sample/Broken.java`, the editor must open **the exact source text corresponding to that URI/compilation version**, rather than automatically finding another `Broken.java` file on disk.

### Why Should Error Lines Not Be Highlighted by Message Substring?

A message like "cannot find symbol" can contain identifier names, types, generic context, and API details. They vary across compiler versions. `Diagnostic` already provides numeric positions; prefer structured data. If no position exists, display the message without fabricating a line.

### Errors from Generated Sources

An annotation processor can generate sources during a compile step. Diagnostics related to generated sources can point to `.java` files created by the processor, even though the user did not write those files directly. To navigate from generated sources back to original sources, pipeline metadata/mapping is needed; the collector **does not automatically recognize** the source-generation rules of every processor.

## 11. Comparing the Compiler API with javac CLI

Create an intentionally type-broken file `Broken.java`:

~~~java
public class Broken {
    public static void main(String[] args) {
        int number = "wrong";
    }
}
~~~

Compile with the command:

~~~bash
javac --release 17 -encoding UTF-8 Broken.java
~~~

The CLI can show file, line number, source line, and caret on stderr. The Compiler API collects the same type error via `Diagnostic.Kind.ERROR`, allowing applications to format it themselves.

More detailed CLI diagnostics can be requested:

~~~bash
javac -Xdiags:verbose --release 17 -encoding UTF-8 Broken.java
~~~

This is a separate test command; there is no need to assume log wording is always identical. `-Xdiags:verbose` can add context, while `DiagnosticCollector` mainly changes **how you receive messages**.

If using `-Xmaxerrs` or `-Xmaxwarns` to limit the diagnostic count, the number of collected elements may not represent all potential errors. The compiler may also stop analyzing parts of the source after severe syntax/type errors.

**Do not take the diagnostic count as the absolute definition of the error count in a project** when compiler flags/limits differ.

### 11.1 Watch Out for stderr and Tool Output

A diagnostic listener is not synonymous with capturing everything an annotation processor prints with `System.out.println` or `System.err.println`. File managers/compilers can have additional output or separate exceptions. If building a tool needing auditing, record three streams separately:

- Structured compiler diagnostics;
- Compiler/process logs or writer output;
- Exceptions and task results.

## 12. Common Troubleshooting Table

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime does not provide compiler | Use an appropriate JDK, check modules/runtime image |
| Task fails yet collector has few messages | Error outside diagnostic stream or compiler capped | Check exceptions, writer, file manager, processor |
| Compile true yet still has warnings | Warnings do not block compilation by default | Count warnings separately; check `-Werror` |
| Adding `-Werror` makes compile false | Warning-as-error policy | Record both result and compiler-emitted Kinds |
| No unchecked warning | `-Xlint:unchecked` not enabled or source already fixed | Check compiler options |
| `getSource()` returns null | Task-level diagnostic not attached to a file | Display message without a file |
| `getPosition() == NOPOS` | No suitable position | Do not create a link to line `-1` |
| Editor highlights wrong spot | Different source content/encoding, offset mapping mismatch | Synchronize version, LF/CRLF, Unicode, tabs |
| `getCode()` null or changes | Provider does not guarantee portable codes | Have a fallback |
| Message test fails after JDK upgrade | Wording/locale changed | Assert kind/source/line/task status |
| Two builds mix diagnostics | Reusing collector without lifecycle management | Create a collector per task |
| Error in generated source | Annotation processor creates new source | Check `getSource()`, generation source |
| Driver cannot find source file | Wrong working directory | Run at project root, check `Path` |
| Runtime error mislabeled as compiler error | Phase not distinguished | Separate runtime exceptions from compile diagnostics |

## 13. Exercises with Answers

### Exercise 1 — Which line has the type error?

With `DiagnosticCollectorDemo`, why does stdout have `ERROR at line 4` and `compiled=false`?

**Answer:** The source in `String.join` places `int number = "wrong";` on the fourth line. The compiler emits a type error, the task fails, and the collector stores a diagnostic with line number 4.

### Exercise 2 — Fix the source

Change it to `int number = 7;`, and recompile. What changes?

**Answer:** The task can succeed, `errors=0`, and the loop's ERROR detail lines disappear.

### Exercise 3 — Warnings present yet build still passes

With `FileDiagnosticDemo`, why is `hasWarnings=true` while `compiled=true`?

**Answer:** `-Xlint:unchecked` emits a warning for the raw generic, and there is no `-Werror` policy so compilation can succeed.

### Exercise 4 — Capturing all warning levels

Why not count only `Diagnostic.Kind.WARNING`?

**Answer:** The API also has `MANDATORY_WARNING`. When totaling the warning group, both usually need to be summed.

### Exercise 5 — Diagnostic without position

If `getSource()==null` and `getPosition()==NOPOS`, which file/line should the UI highlight?

**Answer:** Do not highlight any line automatically. Display the message at the project/task level.

### Exercise 6 — Message stability

A unit test compares javac's English message string against a fixed literal. Why is this fragile?

**Answer:** Wording, locale, and diagnostic codes depend on implementation/version. You should check Kind, appropriate positions, and task result.

### Exercise 7 — Runtime error

After compiling successfully, the application throws `NullPointerException`. Does the collector automatically capture that exception?

**Answer:** No. It collects diagnostics inside the compiler task, not errors from the JVM executing the application.

### Exercise 8 — Offset and UTF-8

An editor is reading a UTF-8 file, while the compiler returns `getPosition()=120`. Should the 120th byte be highlighted directly?

**Answer:** No. API offsets are by character position, not equivalent to UTF-8 byte offsets. Proper source and encoding mapping is needed.

### Exercise 9 — Null guard

Why can `d.getSource().getName()` cause an NPE?

**Answer:** The API allows `getSource()==null` for diagnostics not attached to a file. Check the source before calling `getName()`.

### Exercise 10 — Task with -Werror

If a task has warnings and `-Werror`, what should the application report?

**Answer:** Keep the actual `task.call()` result, errors/warnings according to the Kinds emitted by the compiler, and record the `-Werror` flag in compiler options; do not alter severity by guessing.

## 14. Checklist

- [ ] I understand `DiagnosticCollector` is a `DiagnosticListener` that stores a list.
- [ ] I pass the collector into `getTask` and call `call()` exactly once.
- [ ] I check for a `null` compiler.
- [ ] I can create an in-memory type-broken source example.
- [ ] I collect `ERROR` and know its corresponding line number.
- [ ] I can compile source with unchecked warnings using `-Xlint:unchecked`.
- [ ] I distinguish `WARNING` and `MANDATORY_WARNING`.
- [ ] I handle `getSource()==null` and `Diagnostic.NOPOS`.
- [ ] I understand line/column start from 1, offset from 0.
- [ ] I do not use message text or diagnostic codes as a portable contract.
- [ ] I separate compiler task result, diagnostics, and exceptions.
- [ ] I preserve the exact source version when displaying error positions.
- [ ] I use valid file managers, paths/encoding, and compiler options.
- [ ] I do not confuse compile diagnostics with runtime exceptions.

## API Reference Documentation

- [Diagnostic — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [DiagnosticCollector — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [DiagnosticListener — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticListener.html)
- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [ToolProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [javac options — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

## Remember

**`DiagnosticCollector` collects structured diagnostics from a compiler task**. `Diagnostic.Kind` indicates severity, `getSource()` identifies the source, and line/column and character positions point to where the issue occurred when available. Handle `null` and `NOPOS`, and do not rely on messages or diagnostic codes to determine error severity portably. Reliable diagnostic results always include **task success/failure, compiler options, source version, and tool-specific exceptions**.