# Obtaining JavaCompiler via ToolProvider and Handling a Null Result

Java supports **compiling Java code while an application is running** using the API in the `javax.tools` package. The common entry point is **ToolProvider.getSystemJavaCompiler()**, which returns a `JavaCompiler` object for the current runtime **if a compiler is available**. This call **can return null**: a runnable Java application does not mean that environment has the capability to compile Java source.

This is a critical concern in a **runtime extensibility** system: the host may receive plugin source code, compile it into bytecode, and load the new class. If the host runs on a slimmed-down runtime image, a deployment environment lacking the compiler module, or the wrong Java runtime, this feature must handle it cleanly instead of throwing a `NullPointerException`.

Learning outcomes after this lesson:

1. Know how to obtain **javax.tools.JavaCompiler** properly from **javax.tools.ToolProvider** and check for null **before** using it.
2. Understand why a Java runtime may exist without a Java compiler, especially with JDK 9+ and runtime images built with **jlink**.
3. Choose a handling policy when the compiler is absent: **fail-fast**, **disabling the feature with a clear message**, or using an intentionally implemented alternative compilation strategy.
4. Distinguish **compiler unavailable** from **compiler available but compilation failed**; collect diagnostics, close the file manager, and manage outputs/class loaders.
5. Run a complete Java 17 example with deterministic results in both the compiler-present and compiler-absent cases.

## 1. What Do JavaCompiler and ToolProvider Actually Do?

Two types to import:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
~~~

From Java 9 onward, these APIs belong to **module java.compiler**. They are the interfaces and tool-lookup mechanism; **the java.compiler module is not synonymous with the compiler implementation module**. In standard JDK 17 distributions, the system compiler is provided by **module jdk.compiler**.

Basic invocation:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // The current runtime does not provide a system Java compiler.
} else {
    // You can proceed to configure and invoke the compiler.
}
~~~

The return contract has two cases:

| Result | Meaning | Next Action |
| --- | --- | --- |
| Non-null | The current runtime provides the system compiler object | Choose inputs, outputs, options; call `getTask` or `run`; handle result |
| null | The current runtime **does not provide** a system compiler obtainable by ToolProvider | Execute fallback policy or report unsupported; **do not** call methods on null |

According to Java SE 17 documentation, the JDK implementation returns the compiler provided by **jdk.compiler** if that module is available, and otherwise returns **null**. The API allows a Java environment to include `javax.tools` without requiring a compiler implementation.

**Points to distinguish:**

- **JavaCompiler** is a programmatic API, not an object automatically present in every JVM.
- **ToolProvider.getSystemJavaCompiler()** looks up **the compiler of the runtime running the current Java process**; it does not scan the `PATH` variable to execute `javac.exe` or an arbitrary `javac` command.
- A program already compiled into `.class`/`.jar` only needs a JVM capable of executing bytecode; that does not prove the runtime has a compiler to produce new bytecode.
- You can use `ServiceLoader` to discover other `JavaCompiler` implementations explicitly supplied by the application, but **this cannot be treated as an automatic fallback** of `getSystemJavaCompiler`. If a fallback exists, the application must select/verify it explicitly.

### Do Not Confuse This ToolProvider with Similarly Named APIs

In the code above, the exact type is **javax.tools.ToolProvider**. Java also has other tool-providing APIs in the JDK, including `java.util.spi.ToolProvider` and individual tool providers. They are not direct replacements for the **javax.tools.JavaCompiler** contract and may have different invocation mechanisms. When designing a plugin host that uses `JavaCompiler.CompilationTask`, import the `javax.tools` package specifically.

## 2. Why Does getSystemJavaCompiler() Return Null?

A null result **is not necessarily a bug in your Java code**. It is a signal that the runtime environment lacks a suitable system Java compiler.

### 2.1. Running on a Runtime Without a Compiler

In older Java systems, learners often encountered an application launched with a **JRE** instead of a **JDK**. On Java 9+, the distribution model changed: typical JDK distributions include a compiler, yet you can build a **custom runtime image** containing only the modules needed to run the application. Such an image may contain module `java.compiler` (the API) while **lacking `jdk.compiler`** (the implementation).

For example, an application normally only needs web features and file I/O; operators may build a `jlink` image to reduce footprint. When a plugin uploads new source, the host suddenly needs a compiler, but the image lacks it. If the code immediately calls `compiler.getTask(...)`, the typical result is a `NullPointerException` at runtime.

### 2.2. The Process Uses a Different Java Binary Than What You Checked in the Terminal

On a machine with multiple JDKs/runtimes, the `java` binary that the IDE, Docker entrypoint, service manager, or container actually runs **may differ** from the `java`/`javac` you type in a terminal.

For example:

~~~text
Developer's shell:
  javac -version  -> javac 17.x

Application container:
  /opt/app-runtime/bin/java ...  -> custom runtime without jdk.compiler

Result:
  ToolProvider.getSystemJavaCompiler() inside container -> null
~~~

The lines above are an **illustrative scenario**, not fixed stdout of a command. `ToolProvider` is governed by the runtime **inside the process**, not a compiler an administrator happens to find in another directory.

### 2.3. Modules or Packaging Exclude the Compiler

On JDK 17, module **jdk.compiler** is part of the compiler installation. When building an image with `jlink`, or restricting the modules observable to the runtime, the compiler module may be unavailable. The application may also run under native image/embedded JVM modes whose tooling differs from a development JDK.

Checking `java.version` or "Java 17" alone is not enough to conclude a compiler is present. The **definitive check per the API contract** remains calling `ToolProvider.getSystemJavaCompiler()` and checking for null.

## 3. Simplest Check Before Using the Compiler

Create file **CompilerProbe.java**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerProbe {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println(compiler == null
                ? "SYSTEM_COMPILER_UNAVAILABLE"
                : "SYSTEM_COMPILER_AVAILABLE");
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 CompilerProbe.java
java CompilerProbe
~~~

If the running runtime has a system compiler:

~~~text
SYSTEM_COMPILER_AVAILABLE
~~~

If not:

~~~text
SYSTEM_COMPILER_UNAVAILABLE
~~~

These are **two conditional branches**; not a single run that always prints both lines. The application used to generate `.class` files can be compiled on a build machine, and then **the `.class` file** can be copied to a minimal image to test the null branch.

Why does the example separate compilation from execution? Because a runtime without a compiler can still **execute `CompilerProbe.class`** if it has `java.base` and `java.compiler`. That is the exact meaning of the null case: **can run Java code**, but **cannot compile new Java code** via the system compiler.

## 4. Handling Null Properly for Business Needs: No Single Policy Fits All Systems

The `getSystemJavaCompiler()` call does not know whether runtime compilation is **mandatory** or **optional**. The host must decide the policy itself.

### 4.1. Fail-Fast When Plugin Source Compilation Is Mandatory

If the system cannot serve requests without a compiler, fail immediately during configuration validation or when initializing the compilation service; avoid deferring failure until a user uploads a plugin.

~~~java
// Illustrative snippet, placed inside the application's compilation service class.
private static JavaCompiler requireSystemCompiler() {
    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null) {
        throw new IllegalStateException(
                "No system Java compiler is available in the current runtime; "
                + "run with a JDK/runtime image that includes jdk.compiler");
    }
    return compiler;
}
~~~

Advantage: deployment misconfiguration is detected early with a clear error. Avoid replacing this with `Objects.requireNonNull` and a generic message if administrators need to understand which module is missing; the exception message should indicate how to fix it.

If the application runs on a cluster, you can run a capability check during health/startup validation and advertise the compile service as available only when the check passes. Even if a compiler is present at startup, errors in subsequent compilations must still be handled separately.

### 4.2. Graceful Degradation When Compilation Is Only Optional

If the application can still load/run precompiled plugins without compiling source, disable **only** the compilation feature rather than crashing the application.

~~~java
// Illustrative snippet inside a service method.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    return "COMPILE_FEATURE_DISABLED";
}

// Continue using compiler when non-null.
~~~

The snippet above only illustrates a control-flow branch and assumes the method returns `String`; **it is not a standalone runnable program**. When integrating into a real host, use a typed result such as `CompileResult` with status **UNAVAILABLE** instead of free-form string codes.

For instance, an API response might be HTTP 503 when the feature is configured as temporarily unavailable, or a specific configuration/feature-flag error if this environment intentionally does not support compilation. Do not pretend compilation succeeded, and do not turn a "no compiler" error into "user source is invalid."

### 4.3. Fallback Mechanisms Must Have Clear Boundaries

Other options:

- **Build before deployment**: CI uses a JDK to compile plugins, and the runtime only loads signed/verified artifacts.
- **Dedicated compiler service**: the host sends source to a separately managed compilation worker/service and receives an integrity-verified artifact.
- **Another compiler implementation**: use only if a vetted implementation supporting `javax.tools.JavaCompiler` is intentionally integrated.

Do not casually write a fallback like **`Runtime.exec("javac ...")`** and assume the system is safe: that uses a different process/toolchain than `ToolProvider`, requiring you to define the executable path, classpath, timeouts, stdin/stdout/stderr, OS permissions, input sources, resource limits, and security policy. Do not handle null by "installing a compiler at runtime" if the production host lacks the corresponding permissions/software lifecycle.

### 4.4. Avoiding a Common Programming Mistake

~~~java
// WRONG: may throw NullPointerException immediately on a runtime without a compiler.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
compiler.run(null, System.out, System.err, "-version");
~~~

Correct version:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    System.err.println("No system compiler in this runtime");
} else {
    int exitCode = compiler.run(null, System.out, System.err, "-version");
    if (exitCode != 0) {
        System.err.println("Compiler tool returned " + exitCode);
    }
}
~~~

Both code snippets are **snippets** to be placed inside `main` or a suitable method; they are not two standalone classes. The **-version** argument only illustrates calling the `run` API; for actual compilation workflows, use **getTask** and diagnostics to control inputs/outputs. For `run`, the result is represented as an **int exit code**; for `getTask(...).call()`, it is a **Boolean** per the `CompilationTask` contract. Do not mix the two result types.

## 5. Standalone Java 17 Example: Obtaining the Compiler, Compiling Source at Runtime, and Loading a Class

The example below combines everything:

1. Call **ToolProvider.getSystemJavaCompiler()**.
2. If null: print a message and **do not** create a file manager or call `getTask`.
3. If non-null: create a `JavaFileObject` containing controlled source code.
4. Compile the source into a temporary directory using **JavaCompiler.getTask(...)**.
5. Check **Boolean.TRUE.equals(task.call())** and inspect diagnostics on failure.
6. Load the generated `.class` file with a `URLClassLoader` and invoke a static public method.
7. Close `StandardJavaFileManager` and `URLClassLoader`, then delete the temporary directory.

This example is for **trusted source generated by the application itself**, not a sandbox pattern for compiling/running source from untrusted users.

### 5.1. Complete File: RuntimeCompilerDemo.java

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
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

public final class RuntimeCompilerDemo {

    private static final String CLASS_NAME = "generated.Hello";

    private static final String SOURCE = """
            package generated;

            public final class Hello {
                public static String message() {
                    return "Hello dynamic";
                }
            }
            """;

    private RuntimeCompilerDemo() {
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.out.println("compiler=unavailable");
            return;
        }

        System.out.println("compiler=available");
        Path outputDir = Files.createTempDirectory("java-compile-demo-");

        try {
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();

            JavaFileObject sourceFile =
                    new SourceFromString(CLASS_NAME, SOURCE);

            boolean compiled;

            try (StandardJavaFileManager manager =
                         compiler.getStandardFileManager(
                                 diagnostics, Locale.ROOT,
                                 StandardCharsets.UTF_8)) {

                List<String> options = List.of(
                        "--release", "17",
                        "-proc:none",
                        "-d", outputDir.toString());

                JavaCompiler.CompilationTask task =
                        compiler.getTask(
                                null, manager, diagnostics,
                                options, null, List.of(sourceFile));

                compiled = Boolean.TRUE.equals(task.call());
            }

            System.out.println("compile=" +
                    (compiled ? "success" : "failure"));

            if (!compiled) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + ": " +
                            d.getMessage(Locale.ROOT));
                }
                return;
            }

            URL classesUrl = outputDir.toUri().toURL();
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] { classesUrl },
                    RuntimeCompilerDemo.class.getClassLoader())) {

                Class<?> generated =
                        Class.forName(CLASS_NAME, true, loader);

                Object result = generated
                        .getMethod("message")
                        .invoke(null);

                System.out.println("loaded=" + result);
            }

        } finally {
            deleteDirectory(outputDir);
        }
    }

    private static void deleteDirectory(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths
                    .sorted(Comparator.reverseOrder())
                    .toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    private static final class SourceFromString
            extends SimpleJavaFileObject {

        private final String source;

        SourceFromString(String className, String source) {
            super(URI.create(
                    "string:///" +
                    className.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return source;
        }
    }
}
~~~

**Save the file with the exact name `RuntimeCompilerDemo.java`**, UTF-8 encoding. The example uses Java text blocks, `List.of`, and `Stream.toList()`, so it requires **JDK 17+** to compile the example program itself.

### 5.2. Compile and Run Commands

In the directory containing `RuntimeCompilerDemo.java`:

~~~bash
javac -encoding UTF-8 RuntimeCompilerDemo.java
java RuntimeCompilerDemo
~~~

With a **full JDK 17**, system compiler available, writable temporary directory, and the example's trusted source unchanged, exact stdout is:

~~~text
compiler=available
compile=success
loaded=Hello dynamic
~~~

When the same `RuntimeCompilerDemo.class` file runs on a runtime **that has the `java.compiler` API but lacks a compiler implementation**, stdout is:

~~~text
compiler=unavailable
~~~

Only **one of the two branches** runs at a time. I/O errors, write permissions, class loading, or other system issues are separate failures that can cause the program to throw an exception; this example intentionally declares `throws Exception` so learners can observe clearly. In production, convert them into typed results, telemetry, and appropriate lifecycle handling.

### 5.3. Key Points Explained

**The null check happens before any compile operation.** That way no code calls `compiler.getStandardFileManager` when `compiler` is null. This step also avoids unnecessary I/O when compilation is unavailable.

**SourceFromString** is a `JavaFileObject` with `Kind.SOURCE` and a URI like `string:///generated/Hello.java`. It describes input for the compiler; it is not a dynamic class already loaded by the JVM. The compiler generates actual bytecode when `task` is invoked.

**StandardJavaFileManager** is obtained from the compiler and closed via try-with-resources. The `JavaCompiler` API allows reusing a file manager across multiple compilation tasks, yet the host must manage lifecycle and thread safety by design rather than sharing it arbitrarily across concurrent tasks.

**--release 17** tells the compiler to target Java 17 platform code; **-d** chooses where `.class` files are written; **-proc:none** disables annotation processing for this demo compilation. Disabling annotation processing does not turn the compiler into an absolute sandbox.

**Boolean.TRUE.equals(task.call())** avoids depending on the task returning a specific boxed `Boolean`; it checks whether compilation succeeded. This is the result **after already having a compiler**, completely different from `compiler` potentially being null at the start.

**URLClassLoader** loads the class file from the temporary directory. The `Class` object is defined in a new loader and does not automatically appear on the application's system classpath. Manage loaders per plugin version and avoid retaining class/instance references after the plugin ends. Calling `Class.forName(name, true, loader)` can initialize the class and execute code, so only use **trusted** source in this example.

**Cleanup** closes the loader first, then deletes `.class` files and the temporary directory from deepest path to shallowest. In a real system, add handling for deletion failures, process crashes, or artifacts cached beyond a request's lifetime.

## 6. Distinguishing Three Error Layers: Absent Compiler, Invalid Source, and Compilation Environment Failure

The issues below are often conflated even though their fixes differ:

| Layer | Observed Symptom | Meaning | Appropriate Handling |
| --- | --- | --- | --- |
| **Capability** | `ToolProvider.getSystemJavaCompiler() == null` | Runtime does not provide a system compiler | Fail-fast or disable compilation, fix runtime/deployment, choose configured fallback |
| **Compilation task** | Compiler is non-null but `task.call()` fails | Source, options, dependencies, classpath/module path, or annotation processing failed | Collect diagnostics, report contextual error, keep runtime stable |
| **Infrastructure/lifecycle** | `IOException`, file manager failure, directory creation failure, class loading, `LinkageError`, reflection, or I/O | Compilation may have succeeded, but filesystem, dependencies, class loader, or loaded code failed | Classify error, clean up, log, retry only when safe |

A non-null compiler object **does not prove** arbitrary source will be accepted. Conversely, lacking a compiler **is not** a source syntax error. When logging or returning API responses, use distinct result codes.

Example status data type:

~~~java
// COMPONENT DESIGN PATTERN, NOT A STANDALONE PROGRAM.
enum CompileStatus {
    UNAVAILABLE,
    SUCCESS,
    COMPILATION_FAILED,
    INFRASTRUCTURE_ERROR
}
~~~

Using an enum and a `CompileResult` containing diagnostics distinguishes failures more cleanly than returning just a boolean. If compilation succeeds but the subsequent class-loading step fails, record a separate **LOAD_FAILED** status, as that belongs to a different stage than compilation.

### 6.1. JavaCompiler.run vs. getTask.call

A simpler way to invoke the compiler:

~~~java
// This snippet assumes compiler is non-null.
int status = compiler.run(
        null, System.out, System.err,
        "-d", "build", "src/demo/Example.java");
~~~

- **run(...)** accepts String paths/options similar to the command-line tool and returns an **int**: 0 indicates success per tool convention; non-zero indicates failure.
- **getTask(...)** accepts `JavaFileObject`, `DiagnosticListener`, file manager, options, and classes; returns a `CompilationTask` whose **call()** produces a `Boolean`.
- If you need in-memory compiler inputs and source-location error reporting, **getTask + DiagnosticCollector** is usually more suitable.
- **Do not** treat `ToolProvider`'s null state the same as a compilation result being null or false. They occur at two different layers.

The `run` snippet above only illustrates the API; when actually run, `src/demo/Example.java` and a valid writable directory/path must exist; it **is not a standalone program**.

### 6.2. Diagnostics Enable More Accurate Source Error Reporting

`JavaCompiler` can report error kind, file, line, column, and message:

~~~java
DiagnosticCollector<JavaFileObject> errors =
        new DiagnosticCollector<>();

// Requires a valid JavaCompiler and JavaFileManager to create the task.
// After task.call():
for (Diagnostic<? extends JavaFileObject> d
        : errors.getDiagnostics()) {
    System.out.println(d.getKind()
            + " at line " + d.getLineNumber()
            + ": " + d.getMessage(Locale.ROOT));
}
~~~

This is a **diagnostic snippet** placed after an actual task using the `errors` collector, not standalone code. Passing `Locale.ROOT` makes message behavior more predictable, yet it **does not** guarantee an identical verbatim diagnostic string across every compiler/vendor/JDK version. Do not write brittle tests asserting exact English diagnostic text.

Source diagnostics can leak user data, filenames, classpath entries, or temporary paths. On a server, cap diagnostic size, redact sensitive details in logs, and return diagnostics only to principals authorized to view the source.

## 7. Diagnosing a Null Compiler at Runtime

When a production application reports no compiler is available, follow this order:

### Step 1 — Identify the Actual Running Runtime

Run the exact executable or enter the process/container running the application:

~~~bash
java -version
java --list-modules
~~~

With an appropriate JDK distribution and permissions, you can also check:

~~~bash
javac -version
~~~

**Note:** the `javac` command in a shell only confirms the `javac` binary that the shell finds. It **is not proof** that `ToolProvider` inside the server process can return a `JavaCompiler`; the two processes may use different runtimes or images.

In running code, log the minimal permitted information:

~~~java
// Diagnostic snippet, placed in a running host method.
System.out.println("java.version=" +
        System.getProperty("java.version"));
System.out.println("java.home=" +
        System.getProperty("java.home"));
System.out.println("compiler.present=" +
        (ToolProvider.getSystemJavaCompiler() != null));
~~~

This snippet is for diagnostic support. Do not expose full paths, environment variables, or sensitive configuration in public responses.

### Step 2 — Check the Compiler Module

In JDK 17, **javax.tools** resides in **java.compiler**, while the system compiler implementation resides in **jdk.compiler**. Look for the module in the **java --list-modules** output of that exact runtime. You can check the boot layer at runtime:

~~~java
// Only an auxiliary check, not a replacement for ToolProvider.
boolean compilerModuleResolved =
        ModuleLayer.boot().findModule("jdk.compiler").isPresent();
~~~

A runtime lacking `jdk.compiler` typically lacks a system Java compiler. However, do not write application logic that decides solely by module name: **`getSystemJavaCompiler() == null`** remains the direct public API check.

If the code is packaged as a named module and imports `javax.tools`, the descriptor typically needs:

~~~java
module demo.runtime.compiler.host {
    requires java.compiler;
}
~~~

**requires java.compiler** allows the host module to read the `javax.tools` API. It does not guarantee the packaged image contains a compiler implementation. Avoid declaring `requires jdk.compiler` merely to use `JavaCompiler`: that is a tool implementation module, whereas host code only needs the public API from `java.compiler`; packaging and provisioning compiler availability is a separate runtime/deployment decision.

### Step 3 — Inspect Custom Image / jlink

From a full JDK 17, you can build an image containing only the `javax.tools` API **without** the system compiler to test the null branch:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.compiler \
  --output image-no-compiler

./image-no-compiler/bin/java -cp . CompilerProbe
~~~

If `CompilerProbe.class` was precompiled with a full JDK, the expected output is:

~~~text
SYSTEM_COMPILER_UNAVAILABLE
~~~

To build an image with the compiler implementation, add **jdk.compiler**:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.compiler,jdk.compiler \
  --output image-with-compiler

./image-with-compiler/bin/java -cp . CompilerProbe
~~~

On a full JDK 17 with a properly built image, the expected output is:

~~~text
SYSTEM_COMPILER_AVAILABLE
~~~

The two `jlink` commands represent **two separate image builds**. Output directories must not already exist; `JAVA_HOME` must point to a JDK containing `jmods` and `jlink`; run in Bash on Linux/macOS/Git Bash. On Windows, use the appropriate path syntax, environment variables, and executable. For a real application's module graph, include all additional required modules rather than just the minimal set from the demo.

**Do not use `jlink` as a runtime "hotfix."** Update the image in your build/deploy pipeline, test it in a production-like environment, and redeploy. A slim production image only needs compilation **before packaging** if you do not want a compiler installed at runtime.

### Step 4 — Check Launcher and Container Deployment

In your Dockerfile, entrypoint, service unit, and IDE configuration:

- Verify the **java executable** that actually starts the host, not just `JAVA_HOME` on a developer laptop.
- Verify the runtime image/container includes **jdk.compiler**, or that compilation has been offloaded to a dedicated build/worker service.
- If using multiple runtime layers, verify every workload requiring compilation runs in the corresponding image.
- Check options that restrict modules or create module layers; do not infer from JAR files sitting on disk.
- After fixing the image, run `CompilerProbe` with **the exact deployed executable** before enabling the compile feature for users.

## 8. Testing the Null Branch Even When the Dev Machine Has a Compiler

If a developer machine always runs a full JDK, the null branch can easily go unexecuted. A good way to test is to **inject compiler retrieval**, rather than trying to break `PATH`.

Short example:

~~~java
import java.util.function.Supplier;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerPolicyDemo {
    private static String status(Supplier<JavaCompiler> supplier) {
        return supplier.get() == null ? "UNAVAILABLE" : "AVAILABLE";
    }

    public static void main(String[] args) {
        System.out.println("simulated=" + status(() -> null));
        System.out.println("actual=" +
                status(ToolProvider::getSystemJavaCompiler));
    }
}
~~~

Compile:

~~~bash
javac -encoding UTF-8 CompilerPolicyDemo.java
java CompilerPolicyDemo
~~~

The first line is **always**:

~~~text
simulated=UNAVAILABLE
~~~

The second line depends on the runtime: **actual=AVAILABLE** or **actual=UNAVAILABLE**. This tests the null-handling policy independently of whether the dev machine has a compiler. In real unit tests, inject a `Supplier`/`CompilerProvider` into a `CompileService` and assert that the `UNAVAILABLE` branch does not invoke the file manager, writes no output, and returns the right error status. You do not need to mock `JavaCompiler` itself just to test a simple null branch.

At the same time, include an integration test using a **runtime image without a compiler** as in Section 7 to verify actual deployment conditions, because a test with a fake `Supplier` does not prove the production image is packaged correctly.

### Recommended Test Matrix

| Case | Expectation |
| --- | --- |
| Full JDK 17, valid source | Non-null compiler, compilation succeeds, valid artifact produced |
| Full JDK 17, source with syntax error | Non-null compiler, compilation fails, diagnostics contain errors |
| Custom image with `java.compiler` but missing `jdk.compiler` | `ToolProvider` returns null; host reports `UNAVAILABLE`/disables per policy |
| Valid source, unwritable output directory | Reports infrastructure error; cleans up, does not conclude compiler is absent |
| Compilation succeeds, class loading fails | Reports separate load/link error, does not conflate with null compiler |
| Two concurrent compile requests | Separate inputs/outputs, valid file manager/lifecycle, no artifact overwrite |
| Untrusted plugin | Do not execute generated source/classes in the host process without an appropriately evaluated isolation boundary |

## 9. JavaCompiler Lifecycle in a Plugin System

For a host that frequently compiles dynamic code, checking for null is **the first step**, not a substitute for lifecycle design.

### 9.1. When to Check?

- **At startup**: if the host requires a compiler, check early and refuse to enable the feature when missing.
- **At capability/feature initialization**: if optional, record compilation capability so UI/REST APIs reflect it accurately.
- **Before each use in the service**: code should still keep an explicit guard, especially at integration boundaries and in tests.

Do not cache a boolean at startup and omit usage-site checks if code can run in multiple modes or receive different compiler instances. Conversely, no need to look it up redundantly on every line; a service initialized with either a compiler or an `UNAVAILABLE` state makes the dependency clear.

### 9.2. Do Not Mix Files and Class Loaders Across Plugins

Each compilation should have:

1. Clearly identified input sources (binary class name, package).
2. A fixed, controlled set of options: `--release`, classpath/module-path, `-d`, `-proc:none` if annotation processors are unwanted.
3. A dedicated output directory or in-memory `JavaFileManager` for that compilation.
4. Diagnostics tied to the right request/tenant.
5. A class loader or module layer tied to the plugin version; shared APIs properly shared to avoid duplicating types.
6. An artifact commit/rollback workflow, closing managers/loaders and cleaning temporary files.
7. Load limits, request limits, source/artifact size caps, and latency observability.

One `JavaCompiler` instance can create multiple `CompilationTask` objects, but do not assume a file manager can be freely shared across threads. At scale, understand the implementation's specific contract and coordinate compile jobs; it is usually **simpler for each task to have its own file manager/output scope**.

### 9.3. Distinguishing Compiler from Class Loader

**Successful compilation** produces `.class` files; it does not automatically install classes into the application class loader. To execute a freshly compiled plugin, the host must also pass the artifact to an appropriate class loader or module layer, verify type compatibility, lifecycle, and code permissions. This happens after `JavaCompiler`.

Do not try to use `ToolProvider` to "hot reload" a `Class` already defined by an old loader: the same defining loader cannot normally redefine a class simply by overwriting `.class` files on disk. Perform plugin updates using a new versioned class/loader or a dedicated instrumentation mechanism; release old version references per policy.

## 10. Security When Compiling at Runtime

**Having `JavaCompiler` does not mean it is safe to compile or load arbitrary source.** If source comes from untrusted users:

- The **compilation** phase itself can consume significant CPU, RAM, disk, and classpath information. Annotation processors can execute code, so consider **-proc:none** when processors are not needed; if processors are needed, trust only an allowlisted set and source of processors.
- The **bytecode loading or execution** phase is another risk: code can read files, access the network, use reflection, or invoke host APIs with the process's privileges. Using `URLClassLoader` alone **is not a sandbox**.
- Do not treat Java `SecurityManager` (deprecated in modern JDKs) as a general security boundary across versions; you need process/container/VM-level isolation, OS policies, resource limits, and a controlled execution environment.
- Do not let source arbitrarily choose classpath/module path, compiler flags, output directory, or file paths; validate inputs, block path traversal, and prevent overwriting critical artifacts.
- Enforce timeouts, quotas, diagnostic limits, temporary file cleanup, compilation job tracking, and cancellation/isolation policies when limits are exceeded. **`CompilationTask.call()` has no built-in timeout parameter**; if you need to abort a malicious/hung compilation, isolating it in a worker process allows safer bounding and termination.
- When using an external compiler service, authenticate requests, verify returned artifacts, record compiler versions, and protect secrets; service failures are not equivalent to `ToolProvider` returning null.

Even for internally generated code, define output paths and cleanup rules to prevent operational issues; the strength of security controls depends on trust level of sources, dependencies, and where plugins execute.

## 11. Common Misconceptions

**“Running Java 17 guarantees `javac` is in the API.”** False. Java SE guarantees the required interfaces, not that every runtime ships a compiler. Custom images can omit `jdk.compiler`.

**“Adding `import javax.tools.ToolProvider` is enough.”** False. Importing and having the `java.compiler` module do not create a compiler implementation. Always check the return value.

**“If `javac` is on the machine's `PATH`, `getSystemJavaCompiler` cannot be null.”** False. The API looks up the system tool of the current runtime, not by running a shell to find `javac`.

**“A null `JavaCompiler` is caused by invalid Java source syntax.”** False. When it is null, no compilation task even exists yet; source errors only appear after obtaining a compiler and compiling.

**“A non-null compiler means the task is guaranteed to succeed.”** False. Syntax, classpath, dependencies, annotation processors, I/O, or options can still make the task fail.

**“Just `requires java.compiler` guarantees a compiler exists.”** False. That directive lets the module read the `javax.tools` API; the implementation may be absent from the image.

**“You can work around null with `java.util.spi.ToolProvider` or `getSystemToolClassLoader`.”** Incorrect as a general fallback. Those are different APIs/paths; in JDK 17, `javax.tools.ToolProvider.getSystemToolClassLoader()` is deprecated and its implementation always returns `null`, so do not rely on it.

**“Disabling annotation processing makes user code safe.”** Incorrect. It closes one code-execution vector during compilation, yet provides no protection when compiled code is loaded/run. You still need trust boundaries and isolation.

**“Once compiled, the class automatically appears in the application.”** False. After compilation comes loading bytecode through the right loader/module layer, checking API identity, and managing lifecycle.

## 12. Deployment Checklist

Before enabling runtime plugin compilation, verify:

- **Runtime**: identify the exact Java executable running the host and the actual runtime image layout.
- **API**: use `javax.tools.ToolProvider` and `javax.tools.JavaCompiler` properly.
- **Null guard**: check for null before any `getStandardFileManager`/`getTask`/`run` call.
- **Policy**: decide whether compilation is mandatory or optional; provide distinct messaging and status for `UNAVAILABLE`.
- **Modules**: named-module applications declare `requires java.compiler`; images needing a system compiler include module `jdk.compiler`.
- **Inputs**: source, encoding, binary name, release target, and dependency paths are controlled.
- **Results**: distinguish null compiler, `false` compilation, and infrastructure exceptions.
- **Diagnostics**: collect errors with valid locations, bound logged data, and avoid relying on exact vendor/JDK diagnostic wording.
- **Resources**: close file managers, class loaders, and output streams; clean temporary directories and handle cleanup errors.
- **Security**: never run untrusted user bytecode directly in the host process; apply appropriate isolation/quotas/timeouts.
- **Testing**: test on full JDK, compiler-less image, valid/invalid sources, output failures, and class loading; monitor the feature after rollout.

**Summary:** `ToolProvider.getSystemJavaCompiler()` is the direct way to ask the runtime whether it provides a **system Java compiler**. **null is a valid API result** that must be handled as a system-capability branch; only when the compiler is non-null should you create a compilation task, evaluate its result, and proceed to load the plugin. Proper design also requires an appropriate runtime image, clear diagnostics, resource closing, and security boundaries for dynamic code.

## Official References

- [Java SE 17 — javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler()` contract and null return conditions.
- [Java SE 17 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `run`, `getStandardFileManager`, and `CompilationTask`.
- [Java SE 17 — javax.tools package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html): tools/diagnostics framework and API scope.
- [JDK 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): building modular runtime images.
