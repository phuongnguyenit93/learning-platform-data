# Handling `call()` Results, Diagnostic Output, and Configuration Errors in the Java Compiler API

When a Java application calls the **Java Compiler API** to compile a program, it does not simply receive a string of messages like when running `javac` from the terminal. The `javax.tools.JavaCompiler` API returns a **`CompilationTask`** object; the application can obtain the **`Boolean` result** of `call()`, collect **structured diagnostics** via `DiagnosticListener` or `DiagnosticCollector`, and receive **additional output** via a `Writer`. Besides errors in source code reported in the usual way, the call can also fail due to **compiler configuration, invalid options, paths, file manager, or a user-installed component**.

Distinguishing these three output channels is a prerequisite for writing IDEs, online compile services, test frameworks, code-generation tools, or build plugins without wrongly concluding that "no exception means compilation succeeded".

This lesson uses Java 17 or newer, preferring the public Java Compiler API in module `java.compiler` and distinguishing API specifications from display details of a specific `javac` build.

## 1. Architecture of a Single Compilation via the API

A common sequence of operations:

```text
ToolProvider.getSystemJavaCompiler()
           |
           v
JavaCompiler instance
           |
           +-- DiagnosticCollector<JavaFileObject>
           +-- StandardJavaFileManager
           +-- sources: JavaFileObject / compilationUnits
           +-- options: --release, -d, -cp, ...
           +-- Writer: additional compiler output
           |
           v
compiler.getTask(...)
           |
           v
JavaCompiler.CompilationTask
           |
           v
task.call()
   |                    |                    |
   v                    v                    v
Boolean result      Diagnostics list      Possible exceptions
true / false        ERROR, WARNING, ...   configuration/SPI failures
   |
   v
close file manager, inspect class output, report status
```

**`getTask(...)` creates an unexecuted compilation task**; `call()` triggers compilation. Returning `true` means all processed files have **no compilation errors** per the task's contract. Returning `false` means compilation did not complete successfully due to errors, usually with related diagnostics.

**Do not use `task.call() != null` as the success criterion.** For `CompilationTask` under the API, `Boolean.TRUE.equals(task.call())` is the explicit expression, avoiding mistaking a `Boolean.FALSE` object (which is non-`null`) for success.

### Objects to Understand

| Component | Role | Note |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Retrieves the compiler bundled with the current platform | May return `null` if the image/runtime lacks a compiler, e.g. missing module `jdk.compiler` |
| `JavaCompiler.getTask(...)` | Creates a compilation task with file manager, listener, options, and inputs | May throw `IllegalArgumentException` if input/option configuration is invalid |
| `JavaCompiler.CompilationTask.call()` | Executes compilation and returns `Boolean` | Each task **can only be `call`ed once** |
| `DiagnosticCollector<JavaFileObject>` | Collects diagnostics into a list | Includes kind, code, source, line/column/message if present |
| `Writer out` of `getTask` | Receives **additional output** of the compiler | Does not completely replace the diagnostic listener |
| `StandardJavaFileManager` | Manages source files, output locations, and classpath reads | Must be closed properly, suitable for `try-with-resources` |
| `JavaFileObject` | Models Java source/class input/output | Can represent a real file or source from an in-memory string |

Unlike running `javac` with `ProcessBuilder`, the Compiler API does not need to spawn a new OS process for each compile run. It runs inside the JVM calling the compiler and uses the objects passed to the task, so **exceptions from annotation processors, file managers, or listeners** can directly affect the orchestrating program.

## 2. `CompilationTask.call()` Result: True/False Semantics

`JavaCompiler.CompilationTask` extends `Callable<Boolean>`. Java SE 17 specifies:

- `call()` performs the compilation work; **returns `true` if and only if all files compiled without errors**.
- `false` indicates compilation had errors per the API; commonly occurs with syntax errors, type checking, missing classes, or invalid source constructs.
- **Calling `call()` a second time on the same task** throws `IllegalStateException`. To compile again, **create a new task**.
- `call()` may throw `RuntimeException` if an unrecoverable error occurs in a **user-supplied component**, with the actual cause attached as the cause.

Example in principle:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        additionalOutput,
        fileManager,
        diagnostics,
        options,
        null,
        compilationUnits
);
boolean ok = Boolean.TRUE.equals(task.call());
```

This is a **code fragment inside a method** with corresponding variables and imports, not a standalone program. Note the checking pattern:

```java
if (!ok) {
    // Report compilation failure; inspect diagnostics and additional output.
}
```

Do not write `try { task.call(); success = true; } catch (...) { ... }` because **many source errors merely make `call()` return `false`**, without throwing any exception at all.

### One Task Used Once, File Manager Reusable Multiple Times

The API documentation emphasizes `CompilationTask.call()` **is only once**, yet a `StandardJavaFileManager` is supported for multiple **sequential compilations** if managed properly. Therefore you can:

1. Use the same `JavaCompiler` to create task A, calling A exactly once.
2. Create a brand-new task B and call B exactly once.
3. Reuse the file manager if wanting to cache paths/JARs, yet avoid unguarded concurrency and keep each task's diagnostics/output separate.
4. Close the file manager after finishing.

The main example below creates a new file manager each time to clarify lifecycle, rather than optimizing prematurely.

## 3. Structured Diagnostics: Why Not Read Only stderr Strings?

`DiagnosticCollector<JavaFileObject>` is a `DiagnosticListener` implementation that stores `Diagnostic` items in a list. Instead of parsing locale/version-dependent text lines, each property can be accessed:

| Property of `Diagnostic` | What Is It Used For? |
| --- | --- |
| `getKind()` | Classifies `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER` |
| `getCode()` | Compiler-defined diagnostic code; useful for logs yet not a stable standard code across all compilers |
| `getMessage(Locale.ROOT)` | Formatted diagnostic content; language/phrasing may vary |
| `getSource()` | Related source `JavaFileObject`; **may be `null`** for errors not attached to a specific file |
| `getLineNumber()` | Source line if available |
| `getColumnNumber()` | Source column if available |
| `getStartPosition()` / `getEndPosition()` | Character range if provided by the compiler |
| `getPosition()` | Preferred character position if available |

If position information is absent, the API has special values like `Diagnostic.NOPOS`; line/column are **not** always positive numbers. Do not pass `diagnostic.getSource().toUri()` directly without checking `getSource() != null`.

Example of safely iterating diagnostics:

```java
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    String where = d.getSource() == null
            ? "<no source>"
            : d.getSource().toUri().toString();
    System.out.printf(
            "%s code=%s file=%s line=%d col=%d%n",
            d.getKind(), d.getCode(), where,
            d.getLineNumber(), d.getColumnNumber());
    System.out.println(d.getMessage(Locale.ROOT));
}
```

This is an **illustrative logic snippet** inside a program that has already declared `diagnostics` and imports; order, messages, or diagnostic count **must not be treated as fixed output**. When an IDE needs highlighting, use the range only if it is not `NOPOS` and convert line/column according to its GUI API.

### `getDiagnostics()` Is Not Synonymous with Everything the Compiler Printed

The `JavaCompiler` documentation states explicitly: if a diagnostic listener is provided, appropriate diagnostics will be passed to the listener. **Yet there are still some messages/diagnostics that cannot be represented as a `Diagnostic`** and may be written to the **additional output Writer**. Therefore, for applications needing complete logging:

1. **Task result:** `Boolean` from `call()`.
2. **Structured diagnostics:** `DiagnosticCollector` or custom listener.
3. **Additional output:** `Writer` passed to `getTask(...)`.
4. **Exceptions:** configuration/runtime/SPI errors arising during setup or execution.

Do not assume one channel is a complete copy of the other three channels.

### WARNING Is Not Automatically an Error

If the compiler reports `Diagnostic.Kind.WARNING` or `MANDATORY_WARNING`, `call()` can still be `true` **if there are no errors**. If the `-Werror` policy is enabled, emitted warnings can cause compilation to fail under compiler rules. Do not invent `diagnostics.getDiagnostics().isEmpty()` as the sole criterion confirming build success: notes/warnings can exist even when `call()` returns true.

If policy control is needed, explicitly configure lint/warning options and use the result of `call()` as the confirmation source for compile success.

## 4. Distinguishing `Writer out`, Listener, and stdout/stderr

Signature of `JavaCompiler.getTask`:

```java
JavaCompiler.CompilationTask getTask(
        Writer out,
        JavaFileManager fileManager,
        DiagnosticListener<? super JavaFileObject> diagnosticListener,
        Iterable<String> options,
        Iterable<String> classes,
        Iterable<? extends JavaFileObject> compilationUnits)
```

This is an **illustrative API declaration** (type names may be presented with full generic wildcards). Parameters:

- **`out`**: `Writer` receiving **additional output** of the compiler. If `null`, the compiler uses default output, usually `System.err`.
- **`fileManager`**: file manager reading/writing sources, classes, outputs, and locations. If `null`, the compiler uses the standard file manager.
- **`diagnosticListener`**: receives structured diagnostics. If `null`, the compiler formats diagnostics itself and sends them to default output.
- **`options`**: list of **compiler options** functioning like `javac` flags; `null` means no flags passed.
- **`classes`**: **names of classes for annotation processing**, not all source files to compile; usually pass `null` when compiling regular Java sources.
- **`compilationUnits`**: list of `JavaFileObject` of type SOURCE to compile; in a source compilation operation, do not shove path `String`s in here.

If **both a listener and a Writer** are provided, there is no guarantee that source errors will be printed as text in the Writer. They usually go through the listener/collector. Conversely, **an empty Writer does not prove there are no errors**, and **an empty Collector does not prove all other outputs are empty**.

### When Should `StringWriter` Be Used?

`StringWriter` is convenient for the compiler API because it can store additional output in RAM:

```java
StringWriter otherOutput = new StringWriter();
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

JavaCompiler.CompilationTask task = compiler.getTask(
        otherOutput, fileManager, diagnostics, options, null, units);
boolean success = Boolean.TRUE.equals(task.call());
String extra = otherOutput.toString();
```

This is a **snippet**, not a complete file. `StringWriter` does not replace `DiagnosticCollector`. When supplying user-written components, avoid letting custom listeners or Writers throw unusual errors unsupervised.

### When Should a Custom `DiagnosticListener` Be Used?

A lambda can be passed:

```java
DiagnosticListener<JavaFileObject> listener =
        diagnostic -> {
            if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                // Send null/NOPOS-checked diagnostic data to the UI.
            }
        };
```

This is also an **illustrative fragment**. The listener is invoked while the compiler is processing; avoid throwing unchecked exceptions, long blocking, or modifying files/sources being used by the compiler inside the callback. Collectors are usually easier to test and process in batches.

## 5. Complete Java 17 Example: One Success and One Source Error

The following practical example intentionally compiles **two string-based source programs in memory**, without needing to create input files `Hello.java`/`Broken.java`. The host application still writes the compiled class of the successful case into a separate output directory.

### 5.1. Creating the Program `CompilerApiDemo.java`

Save the file with the exact name **`CompilerApiDemo.java`**:

```java
import java.io.IOException;
import java.io.StringWriter;
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

public final class CompilerApiDemo {
    private static final class StringSource
            extends SimpleJavaFileObject {
        private final String source;

        StringSource(String className, String source) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static void compile(
            JavaCompiler compiler,
            String label,
            String className,
            String source,
            Path output)
            throws IOException {

        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        StringWriter otherOutput = new StringWriter();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-encoding", "UTF-8",
                    "-d", output.toString());

            JavaCompiler.CompilationTask task =
                    compiler.getTask(
                            otherOutput,
                            manager,
                            diagnostics,
                            options,
                            null,
                            List.of(new StringSource(className, source)));

            boolean success = Boolean.TRUE.equals(task.call());
            boolean hasErrors = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind()
                            == Diagnostic.Kind.ERROR);

            System.out.println(label + ": success=" + success
                    + ", hasErrors=" + hasErrors);

            // Print diagnostics in a real product using getKind(),
            // getCode(), getSource(), positions, and getMessage().
            // Do not parse message text to determine success.
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                    "No system Java compiler available");
        }

        String good =
                "package demo;\n"
                + "public class Hello {\n"
                + "  public static int twice(int n) {\n"
                + "    return n * 2;\n"
                + "  }\n"
                + "}\n";

        String bad =
                "package demo;\n"
                + "public class Broken {\n"
                + "  public static void wrong() {\n"
                + "    int value = \"text\";\n"
                + "  }\n"
                + "}\n";

        compile(compiler, "valid", "demo.Hello", good,
                Path.of("build", "api-valid"));
        compile(compiler, "invalid", "demo.Broken", bad,
                Path.of("build", "api-invalid"));
    }
}
```

### 5.2. Compiling and Running the Host

Using a JDK that has a compiler and supports Java 17, from the directory containing `CompilerApiDemo.java`:

```sh
javac --release 17 -encoding UTF-8 CompilerApiDemo.java
java CompilerApiDemo
```

**Exact expected stdout from the program above** (without printing detailed diagnostics):

```text
valid: success=true, hasErrors=false
invalid: success=false, hasErrors=true
```

Explanation:

1. `ToolProvider.getSystemJavaCompiler()` retrieves the system compiler, checked for non-`null` before use.
2. `StringSource` is a `SimpleJavaFileObject` with `Kind.SOURCE` and URI `string:///demo/Hello.java` or `string:///demo/Broken.java`; `getCharContent` returns content for the compiler to read.
3. `getStandardFileManager` uses `Locale.ROOT` and UTF-8 for better control over reading/formatting for the lesson; options also specify `-encoding UTF-8` for input sources.
4. Each `compile(...)` call creates a new `CompilationTask` and **calls `call()` exactly once**, without reusing an already-run task.
5. `-proc:none` disables annotation processing so the example focuses solely on compiler results/diagnostics, preventing processors from automatically altering the result.
6. The `Hello` source is valid, so `call()` returns true with no `ERROR`.
7. The `Broken` source assigns `String` to `int`, so it has a type error, `call()` returns false, and `DiagnosticCollector` contains at least one `ERROR`.
8. The two output directories are separated to avoid misidentifying valid class files left over from another compile run.
9. The file manager closes automatically via try-with-resources even if the task throws an exception; the output directory is created before calling `getTask`.

From `build/api-valid`, `demo/Hello.class` can be found. For `build/api-invalid`, **do not infer there will be a class file for `Broken`**. In real projects, compilation may generate **some outputs** before detecting errors; do not treat a `call=false` result as a transaction automatically rolling back all written files.

### 5.3. Viewing Actual Diagnostics Instead of Only the Boolean

To explore error details, add **inside the `compile` method after `task.call()`**:

```java
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    String sourceName = d.getSource() == null
            ? "<none>" : d.getSource().toUri().toString();

    System.out.printf(
            "%s at %s:%d:%d [%s]%n",
            d.getKind(),
            sourceName,
            d.getLineNumber(),
            d.getColumnNumber(),
            d.getCode());
    System.out.println(d.getMessage(Locale.ROOT));
}
```

This is an **extension fragment**, not code run by the original program. The statements above may print multiple lines because `Broken` has a type error; **do not hardcode messages and positions verbatim** as a mandatory result for every compiler/JDK. Properties like `getSource` and positions may be absent or `NOPOS` in other diagnostics.

### 5.4. If Wanting to Run a Class Compiled in Memory

The example's compiler **reads source from a string**, yet **writes class output to disk** thanks to `-d` and the standard file manager. This does **not** mean `Hello` is loaded into the host JVM after `call()` succeeds. Calling `Hello.twice` at runtime requires a class loader seeing the output (or a properly designed custom in-memory file manager and class loader).

For instance, running `Hello` directly will not work because this class **does not have `public static void main(String[])`**. If wanting a runtime demo, create a `Main` class with `main` calling `Hello.twice`, and run with a classpath containing the corresponding output.

## 6. How to Classify the Three Major Error Groups

| Scenario | `getTask(...)` | `call()` | What Needs Handling? |
| --- | --- | --- | --- |
| Valid Java source, valid options | Creates task | `true` | Inspect output if wanting to use artifacts |
| Java source has syntax/type error | Usually creates task | `false` | Read `ERROR` diagnostics, do not attribute to "system crash" |
| Missing dependency/source class | Usually creates task | `false` | Check classpath/module path and diagnostics |
| `-Werror` when warnings are treated as errors | Creates task | May be `false` | Distinguish warning policy from source errors |
| Invalid option | **May throw `IllegalArgumentException`** per `getTask` contract | Uncertain whether a task exists to call | Validate options/avoid unsupported options |
| Input `JavaFileObject` is not `Kind.SOURCE` | **`IllegalArgumentException`** per `getTask` contract | No valid task | Supply proper compilation units |
| Output path/fileManager error | May fail in file manager setup or during compile | May throw exception/failed task depending on cause | Check directory, permissions, disk, path provider |
| Compiler runtime lacks `jdk.compiler` | `compiler == null` from `ToolProvider` | Cannot create task | Run on a JDK/runtime image containing the compiler |
| Custom listener/Writer/file manager/processor throws unrecoverable exception | May fail in getTask or call | May throw `RuntimeException` with cause | Log cause, investigate custom callbacks |
| Calling the same task again | Task already ran | **`IllegalStateException`** | Create a new task |

**Do not force everything into "`call()` returns false"** and do not force everything into "throws `Exception`". Source errors are normal compilation results; configuration/SPI errors may be exceptions during setup or execution. What matters is knowing **at which phase the error arose**.

### `IllegalArgumentException` When Options Are Invalid

According to `JavaCompiler.getTask` Javadoc, invalid options or compilation units other than SOURCE may throw `IllegalArgumentException`. For example, an option completely unrecognized by the compiler may be rejected immediately upon creating the task:

```java
List<String> options = List.of("-this-option-does-not-exist");
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics,
                         options, null, units);
```

This is a **negative snippet** to understand configuration errors, not a standalone program. Do not rely on fixed exception message text because each implementation may differ. A recognized option that **conflicts with another option** can also be reported by the compiler through another channel depending on details; handle both exceptions and results/diagnostics.

You can check preliminarily with `compiler.isSupportedOption(option)` from the `OptionChecker` interface to determine support and the number of arguments the compiler expects, yet this check **does not replace validation of the full option combination**, and does not guarantee paths exist or target releases are valid.

### File Manager and Output Location

If using `StandardJavaFileManager.setLocationFromPaths`, create **an actually existing output directory** before setting the location:

```java
Path output = Path.of("build", "classes");
Files.createDirectories(output);
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(output));
```

This is a **fragment inside code having `manager` and appropriate imports**, not a standalone file. Java SE 17 specifies `setLocationFromPaths` may throw `IOException` if the output location does not point to an existing directory; `IllegalArgumentException` if the output location has the wrong number of paths or a path is unsupported by the file manager.

For one output location, specify **exactly one directory**. If output has already been configured with `setLocationFromPaths(StandardLocation.CLASS_OUTPUT, ...)`, there is no need to simultaneously pass `-d` in options; use one consistent mechanism to reduce confusion.

### When `ToolProvider` Returns `null`

`ToolProvider.getSystemJavaCompiler()` can return `null` when the runtime image lacks a compiler, such as an application running on a minimal environment that stripped `jdk.compiler`. That is a **host application environment error**, not a syntax error in compiled code.

`java -version` only tells you which JVM is running; it does not guarantee `jdk.compiler` is available. When needing the Compiler API in production, configure a JDK or custom runtime image with the compiler module and check before accepting compile requests.

## 7. Safe Result-Handling Model in a Compilation Service

When designing a service, distinguish system status from source status:

```text
REJECTED_CONFIG
    - compiler unavailable, invalid option, invalid input kind
COMPILATION_FAILED
    - call() == false; diagnostics and logs saved per request
COMPILED
    - call() == true; artifacts inspected before publishing
INTERNAL_FAILURE
    - runtime exception from callback/custom component,
      I/O failure, or severe environment error
```

This is a **suggested status model**, not standard constants of the Java Compiler API. It can be mapped to HTTP status/error codes or a job queue system per product requirements, yet do not mix compiler-source errors with server errors.

Suggested Java structure:

```java
try {
    // Check system compiler, sources, options, and file locations.
    // Create a new task, call once.
    boolean success = Boolean.TRUE.equals(task.call());
    if (!success) {
        // Return compilation failed, along with filtered diagnostics.
    }
} catch (IllegalArgumentException invalidConfig) {
    // Invalid configuration/input.
} catch (IllegalStateException invalidLifecycle) {
    // Wrong task lifecycle or invalid access state.
} catch (RuntimeException unexpected) {
    // Inspect cause from custom compiler component.
} // Handle IOException from file manager/Files in the appropriate scope.
```

This is only **pseudo-structure**: do not copy verbatim into a project while missing variable `task`, result, and `catch IOException` if the method has checked I/O. Distinguish client-provided configuration from host-originated errors; the same exception type may require different reporting depending on the source.

### Do Not Swallow Errors from `close()`

`StandardJavaFileManager` is `Closeable`. Use try-with-resources, and if close throws `IOException`, handle it per I/O policy. If compilation finishes yet output was not properly flushed/closed or storage failed, **do not rush to publish artifacts** based solely on `call() == true`. Exceptions from closing resources after `call()` can occur; that is part of the end-to-end operation result.

### Separating Success from Artifact Publishing

`call() == true` is the success of **the compilation task**, not a guarantee that:

- The artifact has been uploaded, signed, published, or deployed successfully.
- Output contains no warnings.
- There is exactly one single class file.
- All runtime dependencies are compatible with the target JVM.
- Compiled code is safe or contains no malicious behavior.

In trusted applications, generate output into a per-request directory, verify contents, and only then move artifacts to the publishing area. For untrusted sources, see the security section below.

## 8. How Should Diagnostic Output Be Recorded/Logged?

A minimal diagnostic record structure for UI or JSON can contain:

```text
severity: ERROR | WARNING | MANDATORY_WARNING | NOTE | OTHER
code: compiler-specific string
source: URI if present
line: long or NOPOS
column: long or NOPOS
message: localized text
```

Features that should be included:

1. **Do not parse the `getMessage()` string to determine severity.** Use `getKind()`.
2. **Keep the diagnostic code** to aid correlation, yet do not treat internal compiler codes as a compatibility contract across all JDKs.
3. **Filter sensitive paths** when returning diagnostics externally; server source paths may appear inside URIs.
4. **Limit log volume** and diagnostic counts if needed; do not let users generate millions of errors exhausting memory.
5. **Separate output channels:** structured diagnostics, additional writer output, host exception stack traces.
6. **Do not modify diagnostic sources** while the listener is being called; avoid unpredictable side effects.
7. **Report errors matching the specific invocation**; do not take the previous request's `DiagnosticCollector` and merge it as the current status.
8. **Understand positions do not necessarily exist:** option or file manager error diagnostics may not attach to a specific source line.

### Why Not Simply Turn All `System.err` into Errors?

If `diagnosticListener` is `null`, the compiler formats diagnostics to default output, usually `System.err`. In applications with many concurrent requests, redirecting JVM-wide `System.err` is unsafe because it mixes logs from other tasks. Instead, **provide an explicit listener/collector and Writer** for each task, and control host-owned components.

The Compiler API also **does not guarantee every custom annotation processor will stay silent on `System.out`/`System.err`**. Third-party processors may print directly; if absolute isolation of logs and errors is required, execute in a separate controlled process instead of replacing `System.setErr` globally.

## 9. Configuring Classpath, Module Path, and Annotation Processing

The main example uses `-proc:none` to disable annotation processing, thereby testing only the compile pipeline. In real projects, options may include:

- `--class-path`/`-cp`: where to find dependencies outside the JDK.
- `--module-path`: named modules.
- `--release 17`: select target source, classfile version, and Java 17 platform APIs.
- `-d`: output class directory.
- `-s`: generated source directory.
- `-processor`, `-processorpath`: select/load annotation processors.
- `-Xlint:...` and `-Werror`: warnings and error policy.

Compiler options must be passed as **properly separated element strings**:

```java
List<String> options = List.of(
        "--release", "17",
        "-classpath", "libs/example.jar",
        "-d", "build/classes");
```

This is an **options list fragment**, not a separate compilation program. Do not pass a single string `"--release 17 -d build/classes"` as one `List<String>` element and expect the compiler to run a shell parser. `getTask(...)` does not accept PowerShell/bash command syntax; it accepts **option tokens**.

### Annotation Processors Can Break a Task Differently from Source Errors

A user-provided processor can report `Diagnostic.Kind.ERROR`, causing compilation to return false under the normal model. Yet a processor **throwing an unhandled unchecked exception**, or a custom `JavaFileManager`/`DiagnosticListener` hitting a runtime error, can cause the compiler to throw `RuntimeException` whose cause is the error in the component. Record the cause and prevent a buggy processor from crashing the entire host service.

To try compiling multiple sequential tasks, use a file manager that supports reuse; **do not** call `CompilationTask.call()` twice on the same instance. When serving multiple concurrent requests, each request should have its own diagnostics, input/output locations, and not share mutable buffers/paths without thread-safety guarantees.

## 10. Common Configuration Mistakes and Quick Diagnosis

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| `compiler == null` | Runtime image lacks compiler module | Run on a JDK or image containing `jdk.compiler` |
| `IllegalArgumentException` at `getTask` | Invalid option, compilation units are not SOURCE | Check option tokens and `JavaFileObject.Kind` |
| `IllegalStateException` calling `call()` a second time | Reusing an already-executed task | Create a new `CompilationTask` for each compilation |
| `call() == false`, collector has `ERROR` | Source has errors, missing dependency, violates Java language rules | Read `getKind`, `getSource`, line/column/message |
| `call() == false` with `-Werror` | Warnings treated as build errors | Inspect both warnings and compiler diagnostics |
| `call() == true` yet collector has `WARNING` | Warnings do not fail compilation by default | Report success with warnings per policy |
| Empty `Writer` yet compile failed | Diagnostics were delivered to `DiagnosticListener` | Rely on `call()` and collector |
| Compiler failed yet collector is empty | Config/IO incident or diagnostics not representable as `Diagnostic` | Check Writer and exceptions; do not claim "no errors" |
| `NoClassDefFoundError` / processor load failed | Processor path or runtime missing dependency | Check classpath, processor path, module graph |
| `IOException` when setting output location | Output directory missing/invalid write permissions | Create/verify directory beforehand and close resources |
| Compilation finished yet app does not run | Wrong runtime target/classpath or class has no `main` | Separate compilation success from runtime testing |
| Logs from multiple requests mixed | Global `System.err`/collector or global output directory | Isolate per-request resources and outputs |

If an exception occurs when creating the task, **there is no valid `call()` result to reference**. If an exception occurs inside `call()`, preserve the stack/cause for host debugging, yet do not try to interpret it as a Java syntax error without evidence.

## 11. Required Test Cases in a Compiler API System

A basic test suite:

1. **Valid source:** `call()==true`, no `ERROR`, class output appears in the right location.
2. **Source with syntax/type error:** `call()==false`, collector contains at least one `ERROR`, location can be determined.
3. **Warnings without `-Werror`:** compilation can succeed, warnings are still reported.
4. **Warnings with `-Werror`:** build fails per configuration; do not rely on an exact warning count across versions.
5. **Invalid option:** verify handling of `IllegalArgumentException` or appropriate compiler notification channel.
6. **Compiler absent:** host returns configuration status instead of `NullPointerException`.
7. **Output location missing or unwritable:** I/O is reported separately from source errors.
8. **Calling `call()` twice:** confirm `IllegalStateException`; fix by creating a new task.
9. **Custom listener/file manager throws:** do not lose cause; application does not mistake it for `call()==false`.
10. **Multiple requests:** diagnostics and Writer do not mix; output directories are isolated.
11. **Task creates artifacts yet fails:** do not publish outputs of an unsuccessful compilation.
12. **Different target JDKs:** run tests with Java 17, 21 when the project requires; option/diagnostic text may differ.

In particular, test **source error cases** and **configuration error cases** separately. Testing only syntax-broken sources may leave host code unable to handle exceptions in `getTask`; testing only invalid options does not prove the collector works properly.

## 12. Security When Compiling Untrusted Code

**Compiling untrusted Java source inside the same JVM as the service host is a major security decision.** A compiler task can read files according to process permissions, annotation processors/plugins can execute Java code at compile time, and custom `JavaFileManager` or compiler components can access host resources.

If the application accepts sources from users:

- Do not rely on `-proc:none` as a **comprehensive sandbox**; it only disables annotation processing, without solving all other risks.
- Prefer a separate process/container limited in CPU, memory, disk, network, and filesystem permissions, created fresh per job or appropriately isolated.
- Do not let users arbitrarily choose classpath, processor path, or arbitrary compiler options in an environment containing secrets.
- Control file names/paths, prevent path traversal, and avoid writing to shared output directories.
- Consider timeouts and resource monitoring at the orchestration layer; `CompilationTask.call()` does **not** itself provide a standard timeout API to safely interrupt an ongoing compile via a single call.
- If needing to run newly compiled bytecode, **isolate a separate runtime**; one successful compilation does not prove bytecode is safe to run inside the host process.

This relates directly to error handling: when a process/container runs out of resources or is killed, status must be recorded as **infrastructure failure**, without fabricating a `Diagnostic.Kind.ERROR` corresponding to source code.

## 13. Checklist When Calling the Compiler API

- [ ] Checked `ToolProvider.getSystemJavaCompiler() != null`?
- [ ] Each request has its own `CompilationTask`, calling `call()` exactly once?
- [ ] Handled `Boolean.TRUE.equals(task.call())` properly instead of inferring from exceptions?
- [ ] Provided `DiagnosticListener` or `DiagnosticCollector` to retrieve structured errors/warnings?
- [ ] Kept `Writer` for additional compiler output and avoided confusing it with the collector?
- [ ] Checked null for `Diagnostic.getSource()` and `Diagnostic.NOPOS`?
- [ ] Passed options as individual tokens, knowing which options are supported?
- [ ] Verified `compilationUnits` are `JavaFileObject.Kind.SOURCE`?
- [ ] Prepared output location before using `StandardJavaFileManager`?
- [ ] Closed file manager with try-with-resources and handled I/O?
- [ ] Distinguished source errors, invalid configuration, callback exceptions, and JVM runtime errors?
- [ ] Checked output, avoiding publishing leftover files from a failed task?
- [ ] Used the right compiler/runtime versions and configured classpath/module path?
- [ ] For untrusted sources, isolated compile/runtime operations from the host JVM?

**Conclusion:** `CompilationTask.call()` is the **success/failure signal of the compilation process**, `DiagnosticCollector` provides **structured diagnostics**, `Writer` holds **additional output**, while exceptions represent **errors in setup phases or execution components** that cannot simply be reduced to source syntax errors. Handle each channel according to the API contract, close the file manager, inspect artifacts, and design separate error states for the application host.

## Official Reference Documentation

- Java SE 17, `JavaCompiler` and `getTask(...)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17, `JavaCompiler.CompilationTask` and `call()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Java SE 17, `DiagnosticCollector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Java SE 17, `Diagnostic` and `Diagnostic.Kind`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Java SE 17, `ToolProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Java SE 17, `StandardJavaFileManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- Oracle JDK 17, *The javac Command*: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html