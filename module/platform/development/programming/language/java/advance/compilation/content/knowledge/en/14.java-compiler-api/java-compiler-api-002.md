# Obtaining the Compiler via ToolProvider and Handling When the Compiler Is Unavailable

Normally, developers compile Java using the `javac` command, an IDE, Maven, or Gradle. However, some tools need to **compile Java code directly from inside a running Java application**, such as assignment graders, code generators, or lightweight IDEs. The standard `javax.tools` API supports this. The common entry point is:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
~~~

Important issue: **the result can be `null`**. Not every Java runtime includes a compiler implementation. An application compiled on a full JDK may be deployed on a minimal runtime image meant only for running bytecode. In that case, calling `compiler.getTask(...)` directly without checking will cause a `NullPointerException`, whereas the real cause is that the environment has no system compiler.

This lesson explains how to use `ToolProvider`, how to detect a missing compiler, the difference between the API module and the implementation module, how to invoke `JavaCompiler` to compile source in-process, collect diagnostics, and structure options for fail-fast, graceful degradation, or external compiler fallback. Examples target **JDK 17+**.

## 1. What Does the Java Compiler API Provide?

Common types:

| API Type | Purpose |
| --- | --- |
| `javax.tools.ToolProvider` | Obtains certain Java tools provided by the runtime environment |
| `javax.tools.JavaCompiler` | Java compiler interface, providing `run(...)` and `getTask(...)` |
| `JavaCompiler.CompilationTask` | Compilation task, executed via `call()` |
| `StandardJavaFileManager` | Connects sources/outputs with standard files and paths |
| `JavaFileObject` | Source or class unit that the compiler works with |
| `DiagnosticCollector<JavaFileObject>` | Collects errors, warnings, and notes in a structured way |
| `Diagnostic` | Describes severity, source file, position, and diagnostic message |

General model:

~~~text
Running Java application
       |
       v
ToolProvider.getSystemJavaCompiler()
       |
       +-- returns null ------> handle missing compiler
       |
       v
JavaCompiler
       |
       +-- StandardJavaFileManager
       +-- source JavaFileObject
       +-- compiler options
       +-- DiagnosticCollector
       |
       v
CompilationTask.call()
       |
       +-- succeeds ----------> output classfile
       |
       +-- fails -------------> inspect diagnostics
~~~

This API operates at **compile time**. It does not automatically download dependencies, launch a debugger, prove code logic is correct, or automatically run the classfile after compilation. **Compilation**, **class loading**, and **class execution** are separate steps.

Specifically, `ToolProvider.getSystemJavaCompiler()` **is not equivalent** to calling `ProcessBuilder("javac")`. It does not simply search for an executable named `javac` on `PATH` and launch an external process; it obtains the tool through the API provided by the current runtime/JDK.

## 2. Obtaining the Compiler Properly and Checking for `null`

Inside a Java method, you can write:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // Compiler is not available in the current runtime.
}
~~~

This is an **illustrative snippet**, not yet a standalone file. `getSystemJavaCompiler()` is a `static` method on `ToolProvider`. Its return type is `JavaCompiler` when an implementation exists, or `null` when no suitable system compiler is available.

**Avoid**:

~~~java
ToolProvider.getSystemJavaCompiler().run(
        null, System.out, System.err, "Hello.java");
~~~

If the system compiler is missing, the expression before `.run(...)` evaluates to `null` and throws `NullPointerException`. That exception does not help users understand they need a runtime with a compiler.

### Runnable probe program on JDK 17+

Create **`CompilerProbe.java`**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerProbe {
    private CompilerProbe() {
    }

    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.err.println("NO_SYSTEM_COMPILER");
            System.exit(2);
        }

        System.out.println("SYSTEM_COMPILER_AVAILABLE");
    }
}
~~~

On a JDK with a compiler:

~~~sh
javac --release 17 -encoding UTF-8 CompilerProbe.java
java CompilerProbe
~~~

Exact stdout:

~~~text
SYSTEM_COMPILER_AVAILABLE
~~~

On a runtime that has the `java.compiler` API but lacks a compiler implementation, the **precompiled** program can print:

~~~text
NO_SYSTEM_COMPILER
~~~

This line goes to **stderr**, and the exit code is **2** due to `System.exit(2)`. You cannot use the compiler-less runtime itself to compile `CompilerProbe.java` right there; you must take `CompilerProbe.class` from a suitable build environment.

If the runtime also lacks the `javax.tools` API classes, the program may not even start up to the `null` check due to class loading/linking errors. Therefore, `null` handles missing implementations, not missing API module packaging.

### Handling `null` according to product requirements

There are two reasonable approaches depending on the application:

- **Compilation mandatory:** return an error status, halt the task, and instruct the user to use a JDK or runtime image containing an appropriate implementation.
- **Compilation optional:** disable the feature, inform the user, and allow other independent features to keep working.

A CLI can exit with a non-zero code like the probe. A Java library normally **should not call `System.exit` itself** because doing so terminates the entire host application process; the library should return a clear status result or throw a meaningful exception so the caller can decide.

## 3. `java.compiler` vs. `jdk.compiler`

Since Java 9, the JDK module system separates API from implementation:

- **`java.compiler`** is the standard module containing `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, and related compiler APIs.
- **`jdk.compiler`** is the JDK module providing the standard Java compiler implementation (`javac`).

Therefore, **having the `java.compiler` API is not enough to conclude a system compiler is present**. A runtime image created with `jlink` can include the API without including the compiler provider. A full JDK normally contains both.

You can inspect modules by running commands on the runtime you want to test:

~~~sh
java --list-modules
java --describe-module java.compiler
java --describe-module jdk.compiler
~~~

Lines from `--list-modules` typically show names like `java.compiler@17...` or `jdk.compiler@17...`, with version parts depending on the distribution. If `jdk.compiler` does not exist in the runtime image, that is a sign to investigate. **Conclusions about compiler availability should still rely on a probe run by the application's actual `java` executable.**

### Custom runtime without a compiler

On a machine with JDK 17+ and the `jlink` tool, you can create a test runtime:

~~~sh
jlink --add-modules java.base,java.compiler --output runtime-without-javac
~~~

Ensure the output directory does not already exist and experiment only in a location where you are permitted to create files. This image intentionally includes the `java.compiler` API without requiring `jdk.compiler`.

After compiling `CompilerProbe.java` using a full JDK, on Linux/macOS run:

~~~sh
runtime-without-javac/bin/java -cp . CompilerProbe
~~~

On Windows PowerShell:

~~~powershell
.\runtime-without-javac\bin\java.exe -cp . CompilerProbe
~~~

In the image lacking a compiler provider, the probe enters the missing-compiler branch and emits `NO_SYSTEM_COMPILER` to stderr. This hands-on exercise distinguishes **"a runtime capable of running classfiles"** from **"a runtime capable of compiling Java in-process"**.

Do not infer availability from the OS having `javac` installed or from the `JAVA_HOME` folder name without checking the executable used to launch the current process itself.

## 4. Complete Example: Compiling a `.java` File Using the Compiler API

This example creates source `GeneratedGreeting.java` with `Files.writeString`, then uses `JavaCompiler.getTask(...)` to produce the classfile. Finally, you can run the resulting class separately with `java`.

**File `InProcessCompileDemo.java`:**

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

public final class InProcessCompileDemo {
    private InProcessCompileDemo() {
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "System Java compiler not available; use a JDK");
        }

        Path root = Path.of("build", "compiler-api-demo");
        Path sourceDir = root.resolve("src");
        Path classDir = root.resolve("classes");
        Files.createDirectories(sourceDir);
        Files.createDirectories(classDir);

        Path source = sourceDir.resolve("GeneratedGreeting.java");
        String code = """
                public class GeneratedGreeting {
                    public static void main(String[] args) {
                        System.out.println("Hello from generated Java");
                    }
                }
                """;

        Files.writeString(source, code, StandardCharsets.UTF_8);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        List<String> options = List.of(
                "--release", "17",
                "-encoding", "UTF-8",
                "-d", classDir.toString());

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(List.of(source));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, units);

            boolean success = Boolean.TRUE.equals(task.call());
            System.out.println("Compilation success: " + success);

            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                System.err.println(diagnostic.getKind()
                        + ": " + diagnostic.getMessage(Locale.ROOT));
            }

            if (!success) {
                throw new IllegalStateException(
                        "Generated source did not compile");
            }
        }
    }
}
~~~

The code uses Java 17+ and includes all imports. Directories `build/compiler-api-demo/src` and `build/compiler-api-demo/classes` are created if they do not exist. The program requires write permission in the current working directory, and the compiler must support `--release 17`.

Compile and run the driver program:

~~~sh
javac --release 17 -encoding UTF-8 InProcessCompileDemo.java
java InProcessCompileDemo
~~~

In an environment with a compiler and where files are created successfully, **stdout**:

~~~text
Compilation success: true
~~~

Then run the classfile generated in the second compilation:

~~~sh
java -cp build/compiler-api-demo/classes GeneratedGreeting
~~~

Stdout:

~~~text
Hello from generated Java
~~~

Core point: running `InProcessCompileDemo` uses **the compiler object in the Java API** to compile `GeneratedGreeting.java`. It does not use `ProcessBuilder` or run a `javac` shell command from within code. The `javac` command at the beginning is only used to produce the classfile of **the demo program itself**.

### Parts of `getTask(...)`

| Object/parameter | Meaning |
| --- | --- |
| `compiler` | The `JavaCompiler` object already checked to be non-`null` |
| `manager` | `StandardJavaFileManager` working with sources/outputs |
| `diagnostics` | Collector receiving structured errors/warnings |
| `options` | Compiler flags such as `--release`, `-encoding`, and `-d` |
| `units` | List of `JavaFileObject` instances corresponding to source files |
| `task.call()` | Starts compilation and returns success/failure |

`getStandardFileManager(...)` accepts a locale and charset to resolve messages/encoding properly; `-encoding UTF-8` in options clarifies source reading encoding. `try-with-resources` ensures the file manager is closed upon completion even when errors occur.

`--release 17` controls the source level, bytecode format, and allowed platform APIs. It **does not turn a runtime lacking a compiler into one that has a compiler**.

`-d` specifies where to write classfiles. Do not mix the source directory and output directory in large builds; if multiple concurrent tasks share an output location, design to prevent overwriting or mixing classfiles.

### Does successful compilation mean zero warnings?

Not necessarily. When the compiler emits warnings, `DiagnosticCollector` can contain `WARNING` or `MANDATORY_WARNING` even though `task.call()` returns `true`. Conversely, the compiler can fail due to errors recorded in the collector under `ERROR`. If the `-Werror` option is used, the warning policy can cause compilation to fail.

Distinguish **the task result** from **the diagnostic list**; do not assume an empty collector on success or that a non-empty collector means failure.

## 5. Intentionally Triggering Errors to Inspect Diagnostics

In `InProcessCompileDemo.java`, try **replacing just the contents of the `code` variable** with the following invalid source code:

~~~java
public class GeneratedGreeting {
    public static void main(String[] args) {
        int count = "abc";
    }
}
~~~

This is **a sample source snippet to be written into `GeneratedGreeting.java`**, not a program that can compile/run successfully. Assigning a `String` to an `int` is invalid. When the compile task runs, `task.call()` returns failure status and the collector contains a diagnostic of kind `ERROR`.

You can expand the diagnostic-processing loop to:

~~~java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.err.println("Kind: " + d.getKind());
    System.err.println("Line: " + d.getLineNumber());
    System.err.println("Column: " + d.getColumnNumber());
    System.err.println("Message: " + d.getMessage(Locale.ROOT));
}
~~~

This **replaces the loop in the complete example**, using the already declared imports/variables. Do not expect exact positions and full diagnostic wording to be identical across all JDKs. If an error is not tied to a location in source, `getLineNumber()` and `getColumnNumber()` may return `Diagnostic.NOPOS`.

In the example with an `ERROR` diagnostic, the program will print `Compilation success: false` and then throw `IllegalStateException` per the chosen fail-fast policy. **This is not the `compiler == null` situation:** the compiler existed and actually checked the code, but the source was invalid.

## 6. Classifying Statuses by Root Cause

Treat these states as independent:

| Case | Symptom | Handling |
| --- | --- | --- |
| Missing compiler implementation | `getSystemJavaCompiler() == null` | Report that the environment lacks a compiler; do not call `getTask` |
| `java.compiler` API also absent | API class loading/linking error or module fails to resolve | Fix the runtime image/module setup |
| Compiler present but source invalid | `task.call() == false` with corresponding diagnostics | Display source errors, line, column, and message |
| Compiler present and succeeds | `task.call() == true` | Record classfile location, handle warnings if any |
| Cannot create/read files | `IOException` or file manager error | Fix permissions, paths, or resources |
| Unsupported compiler option | Appropriate exception/diagnostic | Check `--release`, `-d`, classpath, and JDK |
| Runtime fails to execute output | `NoClassDefFoundError` or version error | Check runtime classpath and bytecode target |

If a user supplies invalid source code, **do not advise "install a JDK"** when `compiler` is already non-`null`. Conversely, when `compiler == null`, **do not report "syntax error"** because the compiler has not processed the source.

A useful internal API should return structured information: status `UNAVAILABLE` / `SUCCESS` / `COMPILATION_FAILED` / `ENVIRONMENT_ERROR`, diagnostics, and output path if available. In a web app/service, translate these states into appropriate messages or error codes rather than throwing one vague exception for every situation.

## 7. `JavaCompiler.run(...)` vs. `getTask(...)`

Besides `getTask(...)`, `JavaCompiler` has a command-line-tool-style `run(...)` method. The following example assumes `compiler` has been checked and the files from section 4 already exist:

~~~java
int exitCode = compiler.run(
        null, System.out, System.err,
        "-encoding", "UTF-8",
        "-d", "build/compiler-api-demo/classes",
        "build/compiler-api-demo/src/GeneratedGreeting.java");
~~~

This is an **illustrative snippet inside a method**, not a standalone Java file. `run(...)` returns **an integer code**; `0` typically indicates success, while non-`0` indicates failure.

Comparison:

- **`run(...)`:** passes strings like `javac` arguments and supplies output/error streams, convenient for simple tasks.
- **`getTask(...)`:** works with a file manager, `JavaFileObject`, and `DiagnosticCollector` to handle structured data/diagnostics, suited to tools needing finer control.
- **Both:** require a real `JavaCompiler` object. Neither method can overcome a `null` return from `ToolProvider`.

Also do not confuse `JavaCompiler.run(...)` with `Runtime.exec(...)` or `ProcessBuilder`. The first is an in-process compiler object API, while the latter two orchestrate OS child processes.

## 8. Configuring Compiler Paths and Dependencies

Obtaining the compiler is only a **necessary condition**. For source code importing external dependencies, the compiler task also needs the appropriate classpath/module path.

For example, source using `org.example.lib.Greeter` may fail with:

~~~text
package org.example.lib does not exist
~~~

even when `getSystemJavaCompiler()` returns a valid object. In that case the issue is **the compile classpath**, not "system compiler missing". You can configure paths using appropriate compiler options or locations in the file manager.

Source/target parameters, `--release`, JDK version, encoding, output directory, and annotation processing can also affect results. A working compiler does not automatically discover every library in a project; build tools like Gradle/Maven typically manage these dependencies for you.

After successful compilation, the JVM running the result still needs the proper **runtime classpath/module path**. Bytecode produced for a higher Java level than the target JVM can cause `UnsupportedClassVersionError`. Analyzing errors by **phase** helps you avoid treating the wrong cause.

## 9. Running in Containers, Services, or a `jlink` Runtime

A single machine can simultaneously have:

- A JDK on the development machine providing both `java` and `javac`.
- Another JDK used by the IDE or Gradle daemon.
- A container carrying only a minimal runtime image to run the app.
- A Java runtime built by `jlink` without the `jdk.compiler` module.

Therefore, merely running `javac -version` in a terminal **is not enough to prove** your application itself runs inside a runtime that has a compiler.

### Gathering information from the process itself

In Java code, you can diagnose:

~~~java
System.out.println("java.version = "
        + System.getProperty("java.version"));
System.out.println("java.home = "
        + System.getProperty("java.home"));
System.out.println("compiler available = "
        + (ToolProvider.getSystemJavaCompiler() != null));
~~~

This is an **illustrative snippet inside a method** with the appropriate `ToolProvider` import. Paths/versions depend on the environment, so there is no fixed stdout. Observing them from **the actual process** is more valuable than only checking `JAVA_HOME` in another terminal.

### Modular Java applications need `requires java.compiler`

If code calling `javax.tools` belongs to an **explicit named module** with a descriptor, declare the API dependency:

~~~java
module demo.compiler.client {
    requires java.compiler;
}
~~~

This is an illustrative `module-info.java`, not a complete project. `requires java.compiler` grants the application module access to the standard API; it **does not guarantee the runtime image contains a compiler implementation**. For applications requiring dynamic compilation inside a `jlink` runtime, ensure the appropriate module/provider is also distributed.

### What happens if only `java.compiler` is present?

The runtime can load the `ToolProvider` API yet `getSystemJavaCompiler()` still returns `null`. This is why you must check the provider rather than only looking at the API module. A runtime missing even `java.compiler` fails differently, such as with `NoClassDefFoundError`/a module resolution error before ever reaching the check.

## 10. Choosing Fail-Fast, Graceful Degradation, or Fallback

**Fail-fast** fits when the application is fundamentally a compiler service or code grader: lacking a compiler is a fatal operational error. Clearly report the missing runtime capability, return failure status, and terminate the task.

**Graceful degradation** fits when compilation is a secondary feature: mark the feature unavailable and let the application continue with business logic that does not depend on the compiler. If there is a UI, show a clear message instead of letting users click and hit a `NullPointerException`.

**Fallback to an external tool** is only appropriate if the system explicitly supports a configured `javac` path or a dedicated build service. When using `ProcessBuilder`, handle executable path, exit code, stdout/stderr, timeout, classpath, OS permissions, and compiler version. Do not blindly use whatever `javac` appears in PATH when a stable version is required or source is untrusted.

**Safety:** The Compiler API is not a sandbox. Compiling, loading, or executing user-supplied code, or running third-party annotation processors, can consume resources or cause unintended side effects. Do not use `JavaCompiler` as an isolation mechanism for untrusted code; independent permission and resource restriction architectures are required.

## 11. Ordered Diagnostic Procedure

When an application fails to compile dynamically, follow these steps in order:

1. **Check `getSystemJavaCompiler()`.** If `null`, stop the compilation branch and report the missing compiler.
2. **Identify the exact runtime.** Print `java.home` and `java.version` from the running process; do not guess from another terminal.
3. **Check API/provider modules.** For Java 9+, inspect `java.compiler` and `jdk.compiler` in the runtime image; the difference between API and implementation is crucial.
4. **Run the probe in the target environment.** Compile `CompilerProbe.class` on a JDK with a compiler and run it with the deployment executable.
5. **If the compiler exists, check sources and options.** Inspect the source file, `JavaFileObject`, `--release`, classpath/module path, and output directory.
6. **Read diagnostics.** For source errors, examine `ERROR` and positions; for warnings, check `-Werror` policy if present.
7. **Verify runtime output.** After successful compilation, run the classfile in a compatible environment with required dependencies.
8. **Test on the actual deployment artifact.** Check the container or `jlink` image, not only a developer laptop.

What not to do: catch `NullPointerException` to guess a missing compiler; print a generic "compile failed"; return success before creating a classfile; or run user-provided code on a production server without safety controls.

## 12. Practice Exercises

**Exercise 1 — Probe.** Create `CompilerProbe.java`, compile/run it on a JDK, and explain why `SYSTEM_COMPILER_AVAILABLE` appears. Replace the null branch with a clearly messaged exception if building a library rather than a CLI.

**Exercise 2 — Runtime image.** If `jlink` is available, create an image containing only `java.base` and `java.compiler`. Use the JDK-compiled probe classfile to test missing-compiler behavior; distinguish it from a runtime missing even the API.

**Exercise 3 — Compile in-process.** Run `InProcessCompileDemo.java` and then run `GeneratedGreeting`, verifying the two corresponding stdout lines across **two runs**.

**Exercise 4 — Intentional error.** Modify `GeneratedGreeting` to assign a `String` to an `int`. Predict `task.call()`, the diagnostic severity, and how it differs from `compiler == null`.

**Exercise 5 — Write permissions.** Change the output directory to a non-writable location in a test environment; describe how to classify the error instead of telling the user to reinstall the JDK.

**Exercise 6 — Library with dependencies.** Write Java source requiring a class in an external JAR. Have the compiler available without a compile classpath, then add the proper path. Why does having a compiler not automatically make all imports valid?

**Exercise 7 — API comparison.** If a tool needs typed errors with line/column/kind for IDE display, should it use `run(...)` or `getTask(...)` with a collector? Explain.

### Self-assessment questions

1. **Which API obtains the system compiler?** — `ToolProvider.getSystemJavaCompiler()`.
2. **What does a `null` value mean?** — The runtime environment does not provide a system Java compiler via the API.
3. **Which module is `JavaCompiler` in?** — The API is in `java.compiler`; the standard JDK implementation is in `jdk.compiler`.
4. **Does having `javac` in PATH guarantee the API returns non-`null`?** — No, the process may be running on a different runtime.
5. **Does `task.call()` returning `false` mean the compiler does not exist?** — No, the compiler ran the task, and the task failed.
6. **Which tool collects structured errors/warnings?** — `DiagnosticCollector` and `Diagnostic` instances.
7. **Does `getTask(...)` automatically download external libraries?** — No; dependencies and appropriate search paths must be configured.
8. **When should you fail-fast?** — When compilation is a mandatory capability of the application.
9. **When should you degrade gracefully?** — When compilation is only an optional capability and other features do not depend on it.
10. **Can the Compiler API be used to run untrusted code safely?** — No; separate isolation and control mechanisms are required.

**Conclusion:** Obtaining the compiler with `ToolProvider` is a small step with major architectural significance. **Do not confuse the API existing with the implementation existing**, and do not confuse an unavailable compiler with source code that fails to compile. Check for `null`, choose a transparent handling policy, use `JavaCompiler` and structured diagnostics, and verify on the exact runtime to be deployed.