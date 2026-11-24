# Creating JShell, Configuring Classpath, Compiler Options, and I/O Streams

## 1. What Is Embedded JShell and Where Does Configuration Happen?

`JShell` can be used as a command-line tool (`jshell`) or **embedded inside a Java application** via the API in the `jdk.jshell` module. In embedded mode, the host does not need to emulate a terminal REPL: it creates a `JShell` state engine, submits Java code fragments (*snippets*) via `eval(String)`, reads results as `SnippetEvent`s, preserves state across evaluations, and closes the engine when finished.

A real-world application may need to:

- Add host libraries/APIs to the **snippet classpath** so submitted code can import and call them.
- Configure **compiler options** used when JShell parses and compiles snippets.
- Configure **JVM options for the snippet execution process** (for execution engines that use a remote VM).
- Separate snippet `System.in`, `System.out`, and `System.err` streams from the host console streams so the app can supply input, capture logs, or render output in a UI.
- Read snippet **status, compile errors, and exceptions** through the API rather than just scraping console strings.
- Manage the lifecycle, prevent concurrent snippet execution on a single `JShell` instance, and handle the risks of running dynamic Java code.

**This topic focuses specifically on initializing and configuring embedded JShell:** `JShell.create()` / `JShell.builder()`, `compilerOptions`, `remoteVMOptions`, `addToClasspath`, `in`, `out`, and `err`. Evaluation and diagnostics are covered just enough to verify that the configuration works.

> **Key point:** The host JVM, the snippet compiler/analyzer, and the snippet **execution** environment can each have separate configurations. Do not treat `compilerOptions`, `remoteVMOptions`, and `addToClasspath` as three ways of writing the same setting.

## 2. Components in an Embedded JShell Application

Typical data flow with the default execution engine:

~~~text
Host JVM
  |
  +-- Java code calls JShell.builder() / JShell.eval()
  |       |
  |       +-- compiler / source analysis
  |       |      +-- compilerOptions(...)
  |       |      +-- classpath for snippet
  |       |
  |       +-- SnippetEvent, Diag, status, exception
  |       |
  |       +-- execution engine (default: remote process)
  |                +-- remoteVMOptions(...)
  |                +-- System.in  <-- Builder.in(...)
  |                +-- System.out --> Builder.out(...)
  |                +-- System.err --> Builder.err(...)
  |
  +-- host code handles logging, UI, data persistence, timeout, close
~~~

In Java 17's default configuration, the engine spawns a **remote execution process** for snippets, and the documentation requires closing `JShell` to release resources. However, the `JShell.Builder.executionEngine(...)` API lets you swap the engine; therefore, you should not assume every custom configuration creates a remote process just like the default.

To use the API in a program, the core types include:

~~~java
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import jdk.jshell.Diag;
~~~

These are illustrative imports (not a standalone program). The module containing these types is `jdk.jshell`, not `java.base`. If the host uses an **explicit named module**, it must declare a dependency on `jdk.jshell` in `module-info.java`:

~~~java
module demo.host {
    requires jdk.jshell;
}
~~~

In the classpath/unnamed-module examples below, we compile and run with `--add-modules jdk.jshell` to explicitly bring this tool module into the module graph. Minimal runtime images packaged with `jlink` might not include `jdk.jshell`: verify module availability instead of assuming every slimmed-down JRE includes this API.

## 3. Quick Initialization and Customized Initialization

### 3.1. Default: `JShell.create()`

If no special configuration is needed:

~~~java
try (JShell shell = JShell.create()) {
    shell.eval("int x = 2 + 3;");
}
~~~

This snippet requires importing `jdk.jshell.JShell` and placing it inside a method. `JShell.create()` is equivalent to `JShell.builder().build()`. `JShell` implements `AutoCloseable`, so use `try-with-resources` to ensure `close()` is called even when an exception occurs.

By default, `JShell.Builder.out` and `err` use the controller's `System.out` / `System.err`; **the snippet input defaults to an empty stream** (it is not bound to the host's `System.in` by default). Consequently, a snippet reading `System.in` without host-configured input may hit EOF or fail while waiting for a line.

### 3.2. Customized: `JShell.builder()`

~~~java
JShell shell = JShell.builder()
        .in(snippetInput)
        .out(snippetOutput)
        .err(snippetError)
        .compilerOptions("-Xlint:deprecation")
        .remoteVMOptions("-Ddemo.mode=embedded")
        .build();
~~~

This is an **API integration snippet**, not a standalone program: `snippetInput` must be an `InputStream`, and `snippetOutput` and `snippetError` must be `PrintStream`s. Create streams before building, and close the engine and streams according to an appropriate lifecycle.

`Builder` configuration methods can be chained; calling `build()` to instantiate the JShell state engine is separate from submitting snippets via `eval`.

| Method | Purpose | Do Not Confuse With |
|---|---|---|
| `JShell.create()` | Quick initialization with defaults | JShell CLI with a prompt |
| `JShell.builder().build()` | Equivalent to `create()` with no configuration | Auto-loading external libraries |
| `Builder.in(InputStream)` | `System.in` source for evaluated code | The snippet string passed to `eval(String)` |
| `Builder.out(PrintStream)` | Destination where snippets write `System.out` | `SnippetEvent.value()` |
| `Builder.err(PrintStream)` | Destination where snippets write `System.err` | Compiler `Diag` list |
| `Builder.compilerOptions(String...)` | Extra compiler options when parsing/analyzing/generating snippets | Remote JVM startup arguments |
| `Builder.remoteVMOptions(String...)` | VM options for the engine launching the remote JVM | Compiler flags or host JVM arguments |
| `JShell.addToClasspath(String)` | Appends a path to the classpath used by `eval` | Adding a JAR to the running host JVM's classpath |
| `Builder.fileManager(...)` | Customizes the Java file manager for compilation/source analysis when truly needed | Simply adding a JAR with `addToClasspath` |
| `Builder.executionEngine(...)` | Selects or configures the execution control engine | A way to change compiler flags |

The APIs above are **real Java APIs**, not pseudo-configuration. Do not copy JShell CLI command syntax like `/env` or `/open` and expect them to be valid Java statements in `eval(String)`.

## 4. Configuring Classpath So Snippets See Libraries

### 4.1. Why Can the Host See a Library While Snippets Cannot?

An application may run on the host JVM with its own classpath, while snippets are compiled and executed in JShell's environment. You **should not assume** that every class loader, module, JAR, or path of the host is automatically visible to JShell.

The right API when you need to add a library to the classpath for `eval` is:

~~~java
shell.addToClasspath(pathToLibrary);
~~~

Where `pathToLibrary` is an appropriate path string, such as a directory of compiled `.class` files or a JAR path. The `addToClasspath(String)` API **appends the path to the end of the classpath used for `eval()`**. Call it before snippets that depend on the path so order-of-evaluation verification stays clear and mid-session state changes are minimized.

Integration code example:

~~~java
Path library = Path.of("lib", "example-api.jar").toAbsolutePath();
shell.addToClasspath(library.toString());
shell.eval("import com.example.api.Greeting;");
~~~

The snippet above requires `java.nio.file.Path`, an open `JShell shell`, and a real JAR containing that package/class; this code is illustrative only and will not work if the JAR does not exist.

### 4.2. Directory Paths vs. JAR Paths

Two common forms exist:

~~~text
lib-classes/
  demo/lib/TextTools.class
~~~

or:

~~~text
libs/example.jar
  demo/lib/TextTools.class
~~~

For a class directory, pass the **root of the package tree** (e.g., `lib-classes`, not `lib-classes/demo/lib`); for a JAR, pass the path to the JAR file. Use `Path.toAbsolutePath()` to avoid working-directory ambiguity.

Note: `JShell.addToClasspath` is a **class lookup path for evaluation**, not a file-copy operation, and it does not compile `.java` files automatically. Libraries must be compiled to `.class` files or packaged as a JAR beforehand. It does not replace `--module-path`/module resolution when the application uses named modules; the main example below uses the classpath to avoid mixing in JPMS resolution issues.

### 4.3. `addToClasspath` and `compilerOptions` Are Not Equivalent

`compilerOptions` passes extra flags to the compiler invocations involved in JShell's parsing, analysis, and code generation. Even though some `javac` flags relate to class lookup paths, **the dedicated and controllable way** to add JARs/directories for snippets is `addToClasspath`. The specification warns that compiler options interfering with JShell's operation are unsupported and have undefined effects.

Do not use `compilerOptions("-classpath", "...")` as an unconditional substitute for `addToClasspath(...)`, or assume that `--class-path` on the host's `java` command will automatically carry the entire classpath over to a remote engine.

### 4.4. When Should Classpath Be Added?

In a runnable example, the sequence is:

~~~text
1. Compile TextTools.java → lib-classes/
2. Initialize JShell via Builder
3. shell.addToClasspath(lib-classes)
4. shell.eval("import demo.lib.TextTools;")
5. shell.eval("System.out.println(TextTools.transform(\"java\"));")
6. Read events, captured stdout
7. close()
~~~

Separating the two compilation phases keeps things transparent: the **library** is compiled by `javac` first; the **snippet** is compiled by JShell during `eval`. If the package name or class directory is wrong, the import statement may be rejected; check `Snippet.Status` and diagnostics rather than just watching the console.

## 5. Compiler Options: Affecting Snippet Analysis and Compilation

`JShell.Builder.compilerOptions(String... options)` adds options for the compiler that JShell uses to parse, analyze, and generate code. The option used in the full program below is:

~~~java
.compilerOptions("-Xlint:deprecation")
~~~

This is an example of an extra lint option compatible with JShell in the tested runtime environment. It does **not** mean snippets or the host are required to enable lint, nor will warnings appear unless the code actually uses a deprecated API.

Guidelines:

- Pass only options supported by the Java compiler/JShell in that context.
- Do not put JVM options like `-Xmx256m` or `-Ddemo.mode=embedded` into `compilerOptions`. Those are VM options, not `javac` flags.
- Do not assume every flag from the standalone `javac` command is valid for JShell's embedded compiler. The Java 17 API explicitly states that **options interfering with JShell have undefined effects**.
- When changing source/target language policy, module accessibility, or annotation processing, test on the target JDK; do not treat `--release`/`--module-path` combinations as universal solutions without verification.
- `compilerOptions` is configured via `Builder` before `build()`. When you only need to add classpath dependencies **after** building, use `shell.addToClasspath(...)`.

This distinction is especially important because the example program below has **two separate compilation phases**: `javac --release 17` is used externally to compile the host and library, while `compilerOptions("-Xlint:deprecation")` configures the **compiler inside JShell**.

## 6. Remote VM Options: Affecting Where Snippets Execute

With the default execution engine that uses a remote process, `Builder.remoteVMOptions(String... options)` sets extra JVM options for the snippet execution process:

~~~java
.remoteVMOptions("-Ddemo.mode=embedded")
~~~

Therefore, inside a snippet:

~~~java
System.out.println(System.getProperty("demo.mode"));
~~~

can print:

~~~text
embedded
~~~

This is a Java snippet running in the evaluation environment; calling `System.getProperty` on the host JVM may return something different, because **the host and remote VM are two separate environments**. Printing `embedded` only holds when using that Builder option on the same session with an execution engine that launches a corresponding remote VM.

Comparison:

| Where You Set the Option | Example | Target Affected |
|---|---|---|
| Host JVM launch command | `java -Xmx512m -cp out EmbeddedShellDemo ...` | Host JVM |
| `Builder.remoteVMOptions(...)` | `"-Ddemo.mode=embedded"` | Remote execution VM launched by the engine |
| `Builder.compilerOptions(...)` | `"-Xlint:deprecation"` | Compiler processing snippets |
| `shell.addToClasspath(...)` | Path to `lib-classes` or JAR | Classpath for snippet evaluation |

Not every custom execution engine spawns a remote VM: the `jdk.jshell.spi.ExecutionEnv` specification describes extra VM options as suggestions to the engine; an engine might not create a remote process. Therefore, do not claim that `remoteVMOptions` affects all engines identically.

For memory/resource limits, apply them to the exact process being constrained. A `-Xmx` flag on the **host** does not automatically cap the heap of the **remote process** where snippets execute.

## 7. Configuring `System.in` for Snippets

### 7.1. Input Is for Evaluated Code, Not Source Code

`Builder.in(InputStream in)` maps a host-provided `InputStream` as `System.in` for the evaluated code:

~~~java
.in(new ByteArrayInputStream(
        "Ada\n".getBytes(StandardCharsets.UTF_8)))
~~~

This is an integration Builder snippet; it requires importing `java.io.ByteArrayInputStream` and `java.nio.charset.StandardCharsets`. A snippet can then read:

~~~java
System.out.println(
    "input=" + new java.util.Scanner(System.in).nextLine());
~~~

With a stream containing `Ada\n`, the snippet prints `input=Ada`. Conversely, the string passed to `JShell.eval(String source)` is **Java code**, not data pushed into `System.in`.

### 7.2. If `in` Is Not Configured

According to the Java 17 Javadoc, by default the Builder supplies an **empty input stream** for evaluation. If a snippet calls `Scanner.nextLine()` when no line is available, it may throw `NoSuchElementException`; code using `BufferedReader.readLine()` may receive `null`. The host should configure input whenever the application genuinely requires interactive input.

Do not carelessly pass the host's `System.in` into `Builder.in` in a program where the host simultaneously reads from the console: the Javadoc warns that sharing `System.in` between snippet input and application input can conflict. A UI or HTTP server typically uses a dedicated queue or managed stream with per-session data-feeding rules.

### 7.3. Interrupting Input Reads

The Javadoc allows `InputStream.read` to throw `InterruptedIOException` to signal that the user canceled input; the running snippet can then be stopped according to JShell's mechanism. However, do **not** treat this as a hard timeout guarantee or a way to stop arbitrary Java code. A snippet in a long loop or blocked in another library may require timeout enforcement at the execution engine or process level.

## 8. Configuring `System.out` and `System.err`

`Builder.out(PrintStream)` and `Builder.err(PrintStream)` route output and error output **written by evaluated code**. By default they use `System.out` and `System.err`, though an embedded application can write to buffers, log files, or a UI bridge.

Minimal snippet:

~~~java
ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
ByteArrayOutputStream stderrBytes = new ByteArrayOutputStream();

try (PrintStream jsOut = new PrintStream(
             stdoutBytes, true, StandardCharsets.UTF_8);
     PrintStream jsErr = new PrintStream(
             stderrBytes, true, StandardCharsets.UTF_8);
     JShell jshell = JShell.builder()
             .out(jsOut)
             .err(jsErr)
             .build()) {

    jshell.eval("System.out.println(\"Hello from snippet\");");
    jshell.eval("System.err.println(\"Error stream from snippet\");");
}
~~~

This is an **integration Java snippet**, requiring imports for `ByteArrayOutputStream`, `PrintStream`, `StandardCharsets`, and `JShell`. The host reads `stdoutBytes.toString(StandardCharsets.UTF_8)` and `stderrBytes...` after evaluation/closing.

**Distinguish three kinds of output:**

1. **Standard output** from `System.out.print*` inside a snippet → `Builder.out`.
2. **Error output** from `System.err.print*` inside a snippet → `Builder.err`.
3. **JShell status, expression values, diagnostics, and exceptions** → `SnippetEvent`, `JShell.diagnostics(Snippet)`, `SnippetEvent.value()`, `SnippetEvent.exception()`; these are **not automatically** printed by JShell as a REPL transcript to the output stream.

For example, when calling `jshell.eval("1 + 2")`, the API can emit an expression event whose `event.value()` is the string `"3"`; do not assume a line `3` automatically appears on `Builder.out` like a console REPL. If a UI wants to display values, the host must build a presentation layer around the events.

Use a consistent encoding, such as UTF-8 for both `PrintStream` and `ByteArrayOutputStream.toString(StandardCharsets.UTF_8)`. When rendering in a UI, never let multiple users share one mutable output stream within a session without routing and concurrency control.

## 9. Complete Java 17+ Example: Separate Library + Embedded JShell

This example verifies four requirements simultaneously:

1. Compile a `demo.lib.TextTools` library **outside the host classpath** and add it to the snippet classpath using `addToClasspath`.
2. Use `compilerOptions("-Xlint:deprecation")`.
3. Set a remote VM system property with `remoteVMOptions("-Ddemo.mode=embedded")`.
4. Redirect snippet `System.in`, `System.out`, and `System.err` to host-managed streams and inspect events.

### 9.1. Directory Structure

~~~text
embedded-jshell/
  demo/
    lib/
      TextTools.java
  EmbeddedShellDemo.java
  lib-classes/     (created by javac)
  out/             (created by javac)
~~~

Both source files are valid Java 17. No Maven/Gradle, custom reflection, or external JARs are used.

### 9.2. Library: `demo/lib/TextTools.java`

~~~java
package demo.lib;
import java.util.Locale;

public final class TextTools {
    private TextTools() {}

    public static String transform(String source) {
        return "lib:" + source.toUpperCase(Locale.ROOT);
    }
}
~~~

`TextTools.transform("java")` returns `lib:JAVA`. The host JVM will run with a classpath containing only `out`, so this library must be supplied separately to JShell's evaluation environment. `Locale.ROOT` keeps upper-casing deterministic regardless of the OS default locale.

### 9.3. Host: `EmbeddedShellDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;

public final class EmbeddedShellDemo {
    public static void main(String[] args) throws Exception {
        Path libraryClasses = Path.of(args[0]).toAbsolutePath();
        ByteArrayOutputStream capturedOut = new ByteArrayOutputStream();
        ByteArrayOutputStream capturedErr = new ByteArrayOutputStream();

        try (PrintStream snippetOut = new PrintStream(capturedOut, true, StandardCharsets.UTF_8);
             PrintStream snippetErr = new PrintStream(capturedErr, true, StandardCharsets.UTF_8);
             JShell shell = JShell.builder()
                     .in(new ByteArrayInputStream("Ada\n".getBytes(StandardCharsets.UTF_8)))
                     .out(snippetOut)
                     .err(snippetErr)
                     .compilerOptions("-Xlint:deprecation")
                     .remoteVMOptions("-Ddemo.mode=embedded")
                     .build()) {
            shell.addToClasspath(libraryClasses.toString());
            check(shell, "import demo.lib.TextTools;");
            check(shell, "System.out.println(TextTools.transform(\"java\"));");
            check(shell, "System.out.println(\"mode=\" + System.getProperty(\"demo.mode\"));");
            check(shell, "System.out.println(\"input=\" + new java.util.Scanner(System.in).nextLine());");
            check(shell, "System.err.println(\"snippet-warning\");");
        }

        System.out.println("snippet stdout:");
        System.out.print(capturedOut.toString(StandardCharsets.UTF_8).replace("\r\n", "\n"));
        System.out.println("snippet stderr:");
        System.out.print(capturedErr.toString(StandardCharsets.UTF_8).replace("\r\n", "\n"));
    }

    private static void check(JShell shell, String source) {
        List<SnippetEvent> events = shell.eval(source);
        if (events.isEmpty() || events.stream().anyMatch(e ->
                e.status() != Snippet.Status.VALID || e.exception() != null)) {
            throw new IllegalStateException("JShell eval failed: " + source);
        }
    }
}
~~~

### 9.4. Compiling, Running, and Verified Output

From the `embedded-jshell/` directory, using Bash (Linux, macOS, or Git Bash):

~~~bash
mkdir -p lib-classes out

javac --release 17 -d lib-classes demo/lib/TextTools.java
javac --release 17 --add-modules jdk.jshell -d out EmbeddedShellDemo.java

java --add-modules jdk.jshell -cp out EmbeddedShellDemo lib-classes
~~~

Notes:

- `lib-classes` contains only the library; `out` contains the host. When running `java -cp out`, the library is absent from the host application's classpath; the `lib-classes` path is passed to `main` as an argument and then supplied to `shell.addToClasspath(...)`.
- `javac --release 17` ensures the source APIs and syntax are Java 17-compatible. The `--add-modules jdk.jshell` flag resolves the module containing the embedded API when compiling/running on the classpath.
- The final argument `lib-classes` is **a single path**. If replacing it with a directory path containing spaces, make sure to quote the argument per shell rules.
- Use JDK 17+ that includes the `jdk.jshell` module; a minimal runtime image missing this module will fail to run.

Actual output verified when compiling with `javac --release 17` and running on JDK 24:

~~~text
snippet stdout:
lib:JAVA
mode=embedded
input=Ada
snippet stderr:
snippet-warning
~~~

The output above clearly demonstrates:

- `lib:JAVA`: the snippet successfully imports `TextTools` **only after `addToClasspath`**.
- `mode=embedded`: the JVM executing the snippet receives the property from `remoteVMOptions`.
- `input=Ada`: `Scanner(System.in)` in the snippet reads from the `ByteArrayInputStream` supplied by the Builder.
- `snippet-warning`: the snippet writes `System.err` to a separate buffer without mixing into stdout.
- The `snippet stdout:` / `snippet stderr:` lines are **printed by the host itself** after JShell closes, not prompts or default output from the JShell CLI.

`check(shell, source)` asserts that each example snippet only yields `VALID` status and no exception. This helper is **intentionally strict** for five very simple snippets; a full REPL host should support multiple event types, statuses like `RECOVERABLE_DEFINED`, and dependency updates rather than treating every non-`VALID` event as a fatal error.

### 9.5. Why Use `try-with-resources`?

`JShell` implements `AutoCloseable`. With the default execution engine, `build()` creates a remote process; closing the engine releases resources when the program finishes or encounters an error. Output streams are also closed after the session; in this example the byte buffers remain readable after closing the `PrintStream`s.

When integrating into a server application, manage lifecycles per session/user. Do not open a new JShell per keystroke, do not leave remote processes running indefinitely, and do not call `close()` while snippets are still using the session without a clear stop/timeout policy.

## 10. Reading Events, Diagnostics, and Exceptions Instead of Guessing from Stdout

`JShell.eval(String)` returns `List<SnippetEvent>`, rather than directly returning a CLI-like transcript string. Each event has:

- `status()`: e.g., `VALID`, `REJECTED`, `RECOVERABLE_DEFINED`, `OVERWRITTEN` (depending on context).
- `snippet()`: the associated snippet object; use with `shell.diagnostics(snippet)`.
- `value()`: string representation of an evaluated value when applicable; can be `null` for snippets that produce no value.
- `exception()`: exception from runtime evaluation per the API mechanism; can be `null`.
- `causeSnippet()` and related details to distinguish direct changes from dependency-driven changes.

When an import or expression is invalid, the host can inspect diagnostics as follows:

~~~java
List<SnippetEvent> events = shell.eval("import missing.pkg.Type;");
for (SnippetEvent event : events) {
    System.out.println("status=" + event.status());
    shell.diagnostics(event.snippet())
         .forEach(d -> System.out.println(
                 d.getMessage(java.util.Locale.ROOT)));
}
~~~

This is an **illustrative snippet inside a method** with a `JShell shell` variable and imports for `jdk.jshell.SnippetEvent` and `java.util.List`. Do not treat compiler error text as stable output across JDK versions; when building a UI, display the status, diagnostic code, position, and message obtained directly from the API.

### Multiple Snippets in One Input

The `JShell.eval` specification expects the input to be **one complete Java snippet** (declaration, expression, statement, import, etc.). If a user submits a buffer containing multiple snippets, do not dump the whole string into `eval` assuming the engine will split it properly. Use `JShell.sourceCodeAnalysis().analyzeCompletion(...)` to split and check completeness before calling `eval`. This is distinct from `Builder.in`: **`eval` input is code**, whereas the `in` stream is **runtime data** read by that code.

### Why Not Just Read `Builder.err`?

Snippet compile errors and user code writing to `System.err` are two separate channels. A snippet can be `REJECTED` without a single line being "printed" to `Builder.err`; conversely, a `VALID` snippet can intentionally call `System.err.println("warning")`. Combining **events + diagnostics + output streams** provides the complete data needed to render an embedded JShell session.

## 11. Advanced Builder Options: Use Only When Needed

Beyond the core settings, Java 17 provides:

### `fileManager(Function<StandardJavaFileManager, StandardJavaFileManager>)`

Used to customize the Java file manager for compilation and source analysis; useful when an application has special file/directory/library mechanisms and needs to intercept how the compiler sees sources or outputs. For adding ordinary Java libraries, **`addToClasspath` is simpler**.

API signature example:

~~~java
JShell.Builder builder = JShell.builder()
        .fileManager(existing -> existing);
~~~

This is an illustrative snippet using an identity mapping that does not change behavior; it is not a classpath mechanism. Writing a custom file manager requires understanding `javax.tools.JavaFileManager` and JShell's compiler conventions.

### `executionEngine(...)`

Used to select a provider or execution control spec when you intentionally need an engine other than the default. Set at most **one `executionEngine` overload** on a Builder. When swapping engines, I/O routing, remote VM options, process isolation, and snippet stopping depend on that engine's contract.

### `idGenerator(...)` and `tempVariableNameGenerator(...)`

These APIs control naming/IDs for snippets and temporary variables. They are not classpath, compiler flag, or I/O configurations. Generator callbacks have restrictions against accessing `JShell` while state is updating; do not arbitrarily call `eval` back inside a callback.

For applications just getting started with embedded JShell, start with `builder().in().out().err().compilerOptions().remoteVMOptions().build()` and `addToClasspath`; extend the Builder only when a specific technical requirement arises.

## 12. Common Errors and Troubleshooting Guide

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `package jdk.jshell does not exist` or JShell API not found | Compiled on a runtime image/JDK missing `jdk.jshell` or module not in the graph | Verify JDK 17+, `java --list-modules`, and `--add-modules jdk.jshell`/`requires jdk.jshell` |
| `ToolProvider` works but `JShell.build()` fails | Missing JDK/engine components or environment cannot launch execution environment | Inspect `IllegalStateException` cause, check runtime image and process creation permissions |
| `import com.example.X` is `REJECTED` | Library not on snippet classpath or wrong package/class name | Compile dependency, pass package tree root or JAR via `addToClasspath`, inspect diagnostics |
| Host can import a class but snippets cannot see it | Host classpath/loader differs from the evaluation environment | Configure the **snippet's** classpath, not just the host classpath |
| `compilerOptions("-Dkey=value")` has no expected effect | Mixing JVM options with compiler options | Move to `remoteVMOptions` when the property is needed in the remote execution VM |
| `remoteVMOptions("-D...")` set, but host `System.getProperty` unchanged | Option targets the snippet execution VM, not the host | Inspect the property from a snippet; distinguish the two JVMs |
| Snippet calling `Scanner(System.in).nextLine()` hits EOF | Default `Builder.in` is an empty stream or the provided stream is exhausted | Supply dedicated input with properly formatted data and manage read positions |
| Expression result not visible even though `eval` returned events | Value is in `SnippetEvent.value()`, not printed automatically to stdout | Read events and build the host transcript |
| No compiler errors in `Builder.err` | Compiler diagnostics are not snippet `System.err` | Use `shell.diagnostics(event.snippet())` |
| Two users' outputs get mixed together | Shared buffer/stream/session without coordination | Allocate per-session streams, serialize evaluations, and apply limits |
| Host hangs on a long-running snippet | Synchronous `eval` waits for execution or code is blocked on input/I/O | Enforce policy timeouts and engine/process resource limits; `stop()` is best-effort |
| Remote VM ignores `-D...` with a custom engine | Engine does not spawn a remote VM or handles options differently | Consult `ExecutionControlProvider`/`ExecutionEnv` docs and verify the actual engine |
| Calling `eval` after `close` | JShell is closed | Do not reuse; create a new session if needed |
| Updated classpath points to a replaced JAR, yet old classes appear | Classes are already loaded and state/loader retains them | Create a new session/loader; do not expect already-defined class bytecode to swap |

An effective debugging practice is to log **separate pieces of state**: the actual classpath added to the shell, Builder options, `SnippetEvent.status`, diagnostics, exceptions, captured stdout/stderr, and the exact snippet executed. Do not infer compilation failure just because "nothing was printed."

## 13. Lifecycle, Multithreading, and Safety Boundaries

### 13.1. `JShell` Is Not Thread-Safe

The Javadoc notes that `JShell` is **not thread-safe**, except for specific documented operations. A web server must not let multiple requests call `eval`, `drop`, or `addToClasspath` concurrently on the same engine. Use a per-session executor/queue, synchronize at the host layer, and ensure outputs/diagnostics are correlated to the right request. To serve multiple independent users, use separate sessions with clear quotas.

### 13.2. Do Not Treat JShell as a Sandbox

JShell executes dynamic Java code; snippets can use APIs to read files, make network calls, spawn threads, or consume CPU/memory within granted permissions. Spawning a separate process via the default engine **does not guarantee safety on its own**, because that process may still run with the host's OS privileges.

For untrusted content, add OS/container controls, restricted user accounts, filesystem/network policies, CPU/memory/time quotas, and process management. `JShell.stop()` only attempts to stop a running snippet; the Javadoc explicitly notes cases where it cannot stop execution, such as blocking on I/O. Do not rely on `stop()` as an unconditional guarantee.

### 13.3. Managing Streams and Memory

`ByteArrayOutputStream` is convenient for small demos, but if a snippet prints endlessly, the buffer can exhaust host heap memory. Production systems should use bounded streams, backpressure, or quota-enforced log appenders with strategies to retain head/tail output slices. Do not retain every `SnippetEvent` and all output unboundedly.

When a session ends, `close()` `JShell` to release resources. If a UI cancels an evaluation, coordinate stopping/closing the engine and handling the final state—do not close a session while allowing another request to reuse it.

### 13.4. Distinguishing Data Input from Code Input

- `shell.eval("...")`: **Java source code** being evaluated.
- `Builder.in(input)`: **runtime byte stream** read by that code via `System.in`.
- `Builder.out/err(stream)`: **runtime byte/output channels** of the snippet.
- `SnippetEvent` and `Diag`: **metadata and results** retrieved by the host via API.

These are four distinct channels. Defining contracts for each channel avoids confusion over permissions, line endings, encodings, and stream lifecycles.

## 14. Embedded JShell Implementation Checklist

1. Have you chosen a JDK/runtime image that includes `jdk.jshell`?
2. Are you using `JShell.builder()` instead of just `create()` when I/O, compiler, or remote VM options are needed?
3. Are host-provided input/output/error streams isolated with clear lifecycles?
4. Have you identified which classes/JARs **snippets need to see** and passed the right paths via `addToClasspath`?
5. Do you distinguish `compilerOptions` from `remoteVMOptions` and host JVM options?
6. If snippets read `System.in`, have you supplied a non-empty stream or a dynamic input feeding mechanism?
7. Are you handling `SnippetEvent.status/value/exception` and `JShell.diagnostics` rather than just printing stdout/stderr?
8. Are you splitting input into complete snippets before calling `eval`?
9. Are operations on the same `JShell` serialized to avoid race conditions?
10. Do you close JShell and streams and enforce timeouts/quotas, especially for externally submitted code?
11. Have you tested on the actual target JDK, OS, and execution engine?

## 15. Quick Self-Check

**1. Which call creates an embedded JShell with default settings?**  
`JShell.create()` or `JShell.builder().build()`.

**2. You have `libs/extra.jar` and want snippets to `import` classes inside it. Which API do you use?**  
`shell.addToClasspath(pathToJar)`, then inspect the `SnippetEvent` and diagnostics for the import.

**3. Does `compilerOptions("-Xlint:deprecation")` replace `remoteVMOptions("-Dapp.name=demo")`?**  
No. One configures the compiler for snippets; the other configures the VM executing snippets.

**4. The input stream for `Builder.in` contains `Ada\n`, while `eval` receives `System.in.read()`. Are these two inputs the same?**  
No. `eval` receives Java code; `in` feeds runtime data to that code when executed.

**5. Without calling `Builder.in`, will a snippet using `Scanner(System.in).nextLine()` always read from the host console?**  
No. The default input stream for evaluation is an empty stream.

**6. Does `Builder.out` automatically print the result value of every expression?**  
No. `SnippetEvent.value()` provides the expression value when applicable; the host decides how to present it.

**7. When a snippet is `REJECTED`, should you read stderr logs or diagnostics?**  
`JShell.diagnostics(snippet)` and the event status are the accurate sources for compile diagnostics.

**8. Does `remoteVMOptions` affect the host's `System.getProperty`?**  
Not by default. With a remote engine, the options target the VM executing snippets.

**9. Should multiple web requests call `eval` concurrently on a single `JShell`?**  
Not arbitrarily; `JShell` is not thread-safe. Serialize access or allocate separate sessions.

**10. Is closing JShell important even if the host application keeps running?**  
Yes. The default execution engine spawns a remote process, and `close()` releases session resources.

**Remember:** to embed JShell properly, use `Builder` to construct the engine with appropriate streams and options, add classpath entries **for snippets** via `addToClasspath`, evaluate complete snippets one by one, retrieve results using **events + diagnostics + captured I/O**, and then close the session. Compiler configuration, host JVM, and remote execution VM are three separate scopes to keep distinct.

## References

- [Java SE 17 — `JShell`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html): `create`, `builder`, `eval`, `addToClasspath`, `diagnostics`, and `close`.
- [Java SE 17 — `JShell.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.Builder.html): `in`, `out`, `err`, `compilerOptions`, `remoteVMOptions`, `fileManager`, and `executionEngine`.
- [Java SE 17 — `SnippetEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SnippetEvent.html): status, value, and exception per event.
- [Java SE 17 — `SourceCodeAnalysis`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SourceCodeAnalysis.html): splitting source into complete snippets.
- [Java SE 17 — `ExecutionEnv`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/spi/ExecutionEnv.html): I/O streams and extra remote VM options for the execution engine.
