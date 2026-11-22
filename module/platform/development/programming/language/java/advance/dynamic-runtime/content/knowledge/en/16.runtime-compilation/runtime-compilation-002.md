# 16.2. Finding the compiler with ToolProvider and handling environments missing jdk.compiler

## Learning objectives

After this lesson, you can:

1. Locate the **system Java compiler** at runtime using `javax.tools.ToolProvider.getSystemJavaCompiler()` and understand why the result can be `null`.
2. Distinguish the **`java.compiler` module** (APIs such as `JavaCompiler`, `JavaFileObject`, `ToolProvider`) from the **`jdk.compiler` module** (the `javac` compiler implementation in the JDK).
3. Distinguish two easily confused `ToolProvider` types: `javax.tools.ToolProvider` and `java.util.spi.ToolProvider`; understand which one returns `JavaCompiler` and which one finds a CLI tool by the name `"javac"`.
4. Detect a full JDK environment, a runtime image created by `jlink`, a program with limited modules, or a runtime-only container; produce clear diagnostic messages when the compiler is missing.
5. Write a Java 17+ program that **still runs when `java.compiler` is absent from the boot layer**, through an entrypoint that relies only on `java.base` and a conditionally loaded helper containing `javax.tools` code.
6. Execute a simple compilation task using `JavaCompiler.getTask(...)` with diagnostics, options, a file manager, and a temporary output directory.
7. Decide when to **fail fast**, when to package `jdk.compiler`, when to move compilation to build-time/an external service, and understand the security limitations of runtime compilation.

**Context:** In chapter **16. Runtime compilation**, an application may generate Java code while running (plugins, DSLs, rule engines, template compilers, testing tools). Not every JVM running the application has a compiler. An application that runs well on a JDK development machine may fail when deployed into a slim runtime image, a minimal container, or an environment using `--limit-modules`. The first step before any compile task is **detecting the compiler and choosing a fallback policy**.

## 1. "Being able to run Java" does not mean "being able to compile Java"

Since Java 9, the runtime is organized into **JPMS modules**. Distinguish three components:

| Component | Module | Role | Question to ask |
| --- | --- | --- | --- |
| Basic Java runtime | `java.base` | Runs bytecode, class loaders, collections, filesystem, process, `ModuleLayer`... | Can the Java program run? |
| Compiler APIs | `java.compiler` | Contains `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, file managers, and diagnostics | Can the code access the Java compiler **API**? |
| System compiler implementation | `jdk.compiler` | Implements `javac`/the system `JavaCompiler` and some internal compiler APIs | Does the current runtime have a **compiler implementation** to compile with? |

In a standard runtime image with full JDK modules, `javax.tools.ToolProvider.getSystemJavaCompiler()` usually returns a `JavaCompiler`. However, if **`jdk.compiler` is missing or unavailable**, this method can return `null`, even if the `java.compiler` module and its API interfaces are still present.

For example:
- A development machine with a full JDK → usually has both `java.compiler` and `jdk.compiler` → the compiler is found.
- A `jlink` runtime image containing only `java.base` and some application modules → may lack both `java.compiler` and `jdk.compiler`.
- An image that has `java.compiler` to load code referencing the API but does **not** have `jdk.compiler` → the system compiler is unavailable.
- A JVM running with `--limit-modules` can **hide a module from the current launch**, even though the module's files are still in the JDK on disk.

**Practical conclusion:** Do not infer from `java -version`, `java.home`, vendor name, having a Java runtime, or an environment having had a JDK in CI that `getSystemJavaCompiler()` is guaranteed to be non-`null`. **Check the actual result**.

## 2. Two ToolProviders with the same name but different contracts

This is a common import mistake.

### 2.1. `javax.tools.ToolProvider` — getting the compiler API

In the `java.compiler` module:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // No system Java compiler available through this API.
}
```

This is an illustrative snippet placed inside a method. The `getSystemJavaCompiler()` method returns **`JavaCompiler` or `null`**. According to the Java SE 17 implementation note, it uses the compiler provided by `jdk.compiler` if that module is available; otherwise it returns `null`.

`JavaCompiler` provides operations such as:
- `getTask(...)`: builds a `CompilationTask` that can collect diagnostics, options, units, and annotation processing.
- `run(...)`: a convenience call style per the `javax.tools.Tool` interface, taking input/output streams and options, returning a status code.
- `getStandardFileManager(...)`: creates a standard file manager to read/write source/class files, manage the filesystem, classpath, and module path depending on configuration.

### 2.2. `java.util.spi.ToolProvider` — finding a tool by name

In the `java.base` module there is **another interface**:

```java
boolean javacToolFound =
        java.util.spi.ToolProvider.findFirst("javac").isPresent();
```

It looks up a **system tool provider** named `"javac"` through the service provider mechanism. If found, the tool can be run via this interface's `run(PrintWriter out, PrintWriter err, String... args)` method.

**It does not return `javax.tools.JavaCompiler`**. A `java.util.spi.ToolProvider` object cannot be blindly cast to `JavaCompiler`. Use fully qualified names when both are needed in one file to avoid wrong imports.

| Need | API | Value type |
| --- | --- | --- |
| Compile via file manager, JavaFileObject, diagnostic listener | `javax.tools.ToolProvider.getSystemJavaCompiler()` | `JavaCompiler` or `null` |
| Check if a tool named `javac` is registered | `java.util.spi.ToolProvider.findFirst("javac")` | `Optional<ToolProvider>` |
| Spawn a full OS `javac` process | `ProcessBuilder` (if allowed and the binary actually exists) | `Process`; not synonymous with JSR 199 |
| Get a third-party compiler provider | `ServiceLoader.load(JavaCompiler.class)` when `java.compiler` is present | Registered provider; not necessarily the system compiler |

The first two lookup approaches in the table can **coexist** when `jdk.compiler` is available, but they serve two different APIs and do not substitute for each other in every case.

### 2.3. Outdated detection approaches

Avoid relying on `tools.jar` or `com.sun.tools.javac.Main` as a stable public API. `tools.jar` is tied to older pre-JPMS JDKs and is not the Java 17 model. `ToolProvider.getSystemToolClassLoader()` has been deprecated and as of Java SE 17 returns `null`; it is not the standard way to "find javac" on Java 17+.

## 3. Environment states to distinguish

A basic diagnostic has three independent checks:

```java
boolean api = ModuleLayer.boot()
        .findModule("java.compiler").isPresent();
boolean impl = ModuleLayer.boot()
        .findModule("jdk.compiler").isPresent();
boolean tool = java.util.spi.ToolProvider
        .findFirst("javac").isPresent();
```

This is an illustrative snippet inside a method; all three checks above **use only `java.base`**, without needing to import `javax.tools`.

`ModuleLayer.boot().findModule(...)` reports whether a module is **resolved in the boot layer** of the running JVM, **not** simply asking whether the module file exists in the installed JDK. Therefore it is suitable for observing the current execution environment, but should not be treated as an inventory tool for every loadable module on disk.

| State | `java.compiler` | `jdk.compiler` | Meaning |
| --- | --- | --- | --- |
| Both API and implementation available | Yes | Yes | Can try `getSystemJavaCompiler()`; still **check for null** |
| Compiler API only | Yes | No | Can load `javax.tools` but the system compiler is usually `null` |
| No compiler API | No | No | Code depending directly on `javax.tools` may fail to load/link; must avoid calling the helper |
| `javac` provider via SPI | Depends on configuration | Usually yes | `java.util.spi.ToolProvider.findFirst("javac")` is independent evidence of a command-tool provider, not `JavaCompiler` |

**Safe decision order:**

1. If `java.compiler` is not in the boot layer: do not call code that depends on `javax.tools`.
2. If the API is present: you may call `javax.tools.ToolProvider.getSystemJavaCompiler()`.
3. If the compiler returns `null`: handle it as **compiler unavailable**, do not dereference.
4. Only when the compiler is non-`null` should you create a file manager and compilation task.
5. If the system allows an alternative compiler, look up the provider/remote service **according to a configured policy**, do not silently use any tool with a similar-looking name.

**Note:** For an application using a **named module** and declaring `requires java.compiler;`, the JVM will require this module at startup; if missing, the boot layer may fail **before entering `main`**. This runtime guard pattern is only useful when the packaging allows the application to start without that module, such as a classpath entrypoint relying on `java.base` and a conditionally loaded helper.

## 4. Quick checks with the CLI

These commands are environment diagnostic operations, not a substitute for checks in code:

```bash
java -version
java --list-modules
javac -version
```

- `java -version`: shows the running JVM, does not confirm that a compiler provider exists in the **actual application runtime image**.
- `java --list-modules`: lists the modules of the runtime image currently selected by this `java` binary. Check whether `java.compiler@...` and `jdk.compiler@...` are present.
- `javac -version`: shows whether a `javac` executable can be found via the shell's `PATH`. It **may belong to a different JDK** than the Java process actually running the application.
- With Windows PowerShell, you can use `Get-Command java` and `Get-Command javac` to see the selected paths; with a Unix shell use `command -v java` and `command -v javac`.

Because `JAVA_HOME`, `PATH`, absolute paths, and container images may not match, **do not** treat the success of `javac -version` on an admin shell as proof for the app process.

### 4.1. `--limit-modules` to simulate missing modules

You can use a launcher flag to **limit visible modules** during testing:

```bash
java --limit-modules java.base,java.compiler CompilerDiscoveryDemo
java --limit-modules java.base CompilerDiscoveryDemo
```

The commands above assume the `CompilerDiscoveryDemo` class is already compiled and on the current classpath. `--limit-modules` does not delete modules from the JDK; it limits the modules observed/resolved in **that run**, which is convenient for testing fallback. In the first scenario, the API is still present but the `jdk.compiler` provider implementation is hidden. In the second scenario, only `java.base` is available.

In a modular app whose module descriptor requires a module outside the limit, the program may fail at the module resolution step; the classpath demo example avoids that dependency in the entrypoint.

## 5. Minimal check pattern: do not skip null

With a runtime that already has the `java.compiler` module, a concise way to write it is:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerCheck {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.err.println(
                    "System Java compiler unavailable: "
                    + "run with jdk.compiler or disable runtime compilation.");
            return;
        }

        System.out.println("System Java compiler is available.");
    }
}
```

This standalone **`CompilerCheck.java`** file compiles when the compiler API is present at compile time, but it is **not a safe pattern for a runtime that also lacks `java.compiler`**, because the class directly references types from that module. If the app truly must run in a minimal runtime image with only `java.base`, use the entrypoint/helper separation pattern in section 6.

Do not write:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
compiler.getStandardFileManager(null, null, null);
```

This is an **anti-example** placed inside a method that has imported the classes; when `compiler` is `null`, the second line will throw `NullPointerException`. This error easily misleads users into thinking their code has a problem with the file manager, when the real cause is **the runtime is missing the compiler**.

### 5.1. Null is a valid result by contract

`ToolProvider.getSystemJavaCompiler()` **is allowed to return null**. Therefore, a null-check is an essential component, not a workaround for a JDK bug. Return meaningful errors such as:
- `COMPILER_UNAVAILABLE`;
- instructions to check the `jdk.compiler` module;
- how to use a full runtime or switch to build-time;
- which configuration is requiring the compilation feature.

Do not automatically run `System.exit(1)` inside a library. A library should return an exception/result with context; the application entrypoint or service policy decides whether to terminate the process.

## 6. Standalone Java 17+ program, safe across three environments

The following **`CompilerDiscoveryDemo.java`** file:

- The entrypoint uses the `java.base` module API to check the boot layer first.
- Only calls the nested helper `CompilerApi` when the `java.compiler` module is resolved.
- The nested helper holds the `javax.tools` references and checks `getSystemJavaCompiler() == null` before compiling.
- If the compiler is available, compiles a `GeneratedGreeting` class from **in-memory source code**, writes the class output into a **temporary directory**, collects diagnostics, closes the standard file manager, and deletes the temporary files.
- Does not use `javac` from PATH and does not load/run the newly created class; it only verifies compilation capability.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class CompilerDiscoveryDemo {
    public static void main(String[] args) throws Exception {
        boolean apiPresent = ModuleLayer.boot().findModule("java.compiler").isPresent();
        boolean implPresent = ModuleLayer.boot().findModule("jdk.compiler").isPresent();
        boolean toolPresent = java.util.spi.ToolProvider.findFirst("javac").isPresent();

        System.out.println("java.compiler=" + apiPresent);
        System.out.println("jdk.compiler=" + implPresent);
        System.out.println("javac.tool=" + toolPresent);

        if (!apiPresent) {
            System.out.println("status=API_ABSENT");
            return;
        }
        CompilerApi.run();
    }

    static final class CompilerApi {
        static void run() throws Exception {
            javax.tools.JavaCompiler compiler =
                    javax.tools.ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                System.out.println("status=COMPILER_UNAVAILABLE");
                return;
            }
            System.out.println("status=COMPILER_AVAILABLE");

            String code = "public class GeneratedGreeting {"
                    + " public static String message() { return \"hello\"; } }";
            javax.tools.JavaFileObject source = new javax.tools.SimpleJavaFileObject(
                    java.net.URI.create("string:///GeneratedGreeting.java"),
                    javax.tools.JavaFileObject.Kind.SOURCE) {
                @Override
                public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                    return code;
                }
            };

            javax.tools.DiagnosticCollector<javax.tools.JavaFileObject> errors =
                    new javax.tools.DiagnosticCollector<>();
            Path directory = Files.createTempDirectory("compile-discovery-");
            try {
                try (javax.tools.StandardJavaFileManager manager =
                        compiler.getStandardFileManager(
                                errors, Locale.ROOT, StandardCharsets.UTF_8)) {
                    List<String> options = List.of(
                            "--release", "17", "-proc:none",
                            "-d", directory.toString());
                    Boolean result = compiler.getTask(
                            null, manager, errors, options, null,
                            List.of(source)).call();
                    System.out.println("compile.ok=" + Boolean.TRUE.equals(result));
                    System.out.println("diagnostics=" + errors.getDiagnostics().size());
                    System.out.println("class.exists="
                            + Files.exists(directory.resolve("GeneratedGreeting.class")));
                }
            } finally {
                Files.deleteIfExists(directory.resolve("GeneratedGreeting.class"));
                Files.deleteIfExists(directory);
            }
        }
    }
}
```

**Compile on a development environment with JDK 17+**:

```bash
javac --release 17 CompilerDiscoveryDemo.java
```

If you are in the directory containing the newly compiled class, run:

```bash
java CompilerDiscoveryDemo
java --limit-modules java.base,java.compiler CompilerDiscoveryDemo
java --limit-modules java.base CompilerDiscoveryDemo
```

### 6.1. Output when the compiler is available

```text
java.compiler=true
jdk.compiler=true
javac.tool=true
status=COMPILER_AVAILABLE
compile.ok=true
diagnostics=0
class.exists=true
```

This is **verified stdout** on OpenJDK 24 with code compiled using `javac --release 17`. When running on a compatible full JDK 17+, the output is similar if the module provider and filesystem match.

### 6.2. Output when the API is present but jdk.compiler is missing

Command:

```bash
java --limit-modules java.base,java.compiler CompilerDiscoveryDemo
```

**Verified stdout:**

```text
java.compiler=true
jdk.compiler=false
javac.tool=false
status=COMPILER_UNAVAILABLE
```

Explanation:
- The `javax.tools` types are still present, so the nested helper `CompilerApi` is allowed to run.
- However, `getSystemJavaCompiler()` returns `null` because the JDK provider implementation is unavailable in the limited module graph.
- The program prints a clear status and does **not** create a file manager/compilation task.
- There is no `NullPointerException` and no class file is generated.

**Key takeaway:** Having the **API** does not mean having the **implementation**. The `java.compiler` module contains the public contract, while `jdk.compiler` contains the system `javac` implementation.

### 6.3. Output when java.compiler is also missing

Command:

```bash
java --limit-modules java.base CompilerDiscoveryDemo
```

**Verified stdout:**

```text
java.compiler=false
jdk.compiler=false
javac.tool=false
status=API_ABSENT
```

The entrypoint only uses `java.base`; it checks the module before **referencing the helper** containing `javax.tools`. Therefore in this example, the helper class **is not loaded** when `java.compiler` is absent.

If you move `javax.tools.` imports along with `JavaCompiler`/`JavaFileObject` types into the public signature, superclass, or initialization logic of the main class, the application may fail at the class loading/verification/linkage step before it can check. Keep the boundary between the core runtime and the optional feature part clear.

### 6.4. Why doesn't the example write output to the source tree?

`JavaCompiler.getTask(...)` in the example takes:
- a `JavaFileObject` containing source code from `getCharContent(...)`;
- `-d` pointing to a temporary directory;
- a `DiagnosticCollector` to collect errors;
- a `StandardJavaFileManager` closed with try-with-resources.

This limits generated files in the project when you only want to probe. `Files.deleteIfExists(...)` is used because the expected output is known to be just a single simple class; **do not** copy this cleanup snippet for a compiler job that may generate multiple classes/packages or annotation-processor files without designing a safe resource cleanup mechanism.

### 6.5. Why use `-proc:none`?

`-proc:none` disables annotation processing in the check example. Compilation and annotation processing are **two different things**. If an unwanted processor is left on the classpath/module path, compilation can execute the processor's logic right inside the process. This is one reason to control options, dependencies, and inputs when accepting untrusted source code.

`-proc:none` does **not** turn the entire compile into a safe sandbox. The parser/type checker still processes untrusted input and consumes JVM resources; compilation can still consume time/memory or create files outside the controlled area if the file manager is loosely configured.

## 7. Analyzing JavaCompiler.getTask(...) properly

The main API signature (shortened for readability):

```java
JavaCompiler.CompilationTask getTask(
    Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
```

This is a **reference signature**, not code to redeclare. Meaning:

| Parameter | Role |
| --- | --- |
| `out` | Writer for compiler output information if needed; `null` chooses the default output depending on the API |
| `fileManager` | Path to source, classpath, output; use `StandardJavaFileManager` or a custom file manager |
| `diagnosticListener` | Receives errors, warnings, source positions, and messages |
| `options` | javac options such as `--release`, `-classpath`, `-d`, `-proc:none` |
| `classes` | Class names for processing when appropriate; for a source-only example pass `null` |
| `compilationUnits` | Source code units, for example `SimpleJavaFileObject` containing in-memory source |

`CompilationTask.call()` returns a `Boolean` indicating whether compilation succeeded. Check safely with `Boolean.TRUE.equals(result)`. If `false`, **read diagnostics** to explain why. Do not use a diagnostic count of 0 as the sole condition to assert success: the compiler may emit warnings and still compile successfully; there are cases where an error occurs at another layer before diagnostics are produced.

### 7.1. Getting full diagnostics

A compile error handling pattern:

```java
Boolean ok = compiler.getTask(
        null, manager, diagnostics, options, null, units).call();

if (!Boolean.TRUE.equals(ok)) {
    for (javax.tools.Diagnostic<? extends javax.tools.JavaFileObject> d
            : diagnostics.getDiagnostics()) {
        System.err.printf(
                "%s:%d:%d: %s: %s%n",
                d.getSource() == null ? "(unknown)" : d.getSource().getName(),
                d.getLineNumber(),
                d.getColumnNumber(),
                d.getKind(),
                d.getMessage(java.util.Locale.ROOT));
    }
    throw new IllegalStateException("Compilation failed");
}
```

This is an **illustrative snippet inside a method** that has `compiler`, `manager`, `diagnostics`, `options`, `units`. Because `Diagnostic` may indicate a null source or an unknown position, you should not assume every diagnostic has a valid line/column.

**Do not swallow a compile failure** and then try to load an old class file from the same output directory. That situation can execute a previous version even though the current job failed.

### 7.2. `run(...)` vs `getTask(...)`

`JavaCompiler.run(in, out, err, String... arguments)` is a convenient tool-style API returning a **numeric status code** (usually 0 on success). It is useful if you need CLI-like behavior. However:
- it is harder to integrate diagnostics and a file manager than with `getTask`;
- it still requires a non-`null` compiler object;
- it does not spawn an independent `javac` process by default.

Do not confuse calling `java.util.spi.ToolProvider.run(...)` with `JavaCompiler.getTask(...)`: these are two different tool interfaces.

### 7.3. Version compatibility and options

If the application runs on JDK 17, `--release 17` is valid. If running on a newer JDK that supports target release 17, `--release 17` is also valid. But on a JDK **older than 17**, that option may not be supported. If the system must support multiple compiler generations, you should check the actual compiler version, the accepted `--release` choices, and the module dependencies system.

`--release` helps compile against the target release's public API/platform, but it does **not** automatically bundle all non-JDK libraries, does not handle classloaders, and does not guarantee the generated program is compatible with every application dependency version.

## 8. Handling a missing compiler: choose a policy instead of a quick patch

### 8.1. Approach 1 — Fail fast with guidance (preferred when the feature is required)

When runtime compilation is a core part of the service, detect the absence of the compiler **right at feature initialization** and return an error with guidance:

```text
COMPILER_UNAVAILABLE
Runtime Java compiler is not available.
Check the selected Java runtime image and resolved module jdk.compiler.
Deploy a Java 17+ image with jdk.compiler, or disable runtime compilation.
```

This is a **sample message**, not output from the program in section 6. Advantages: no half-broken error state, no running an empty compiler, no hiding the root cause under a `NullPointerException`.

If the compile feature is optional, disable it while letting the rest of the service keep running. Clearly define a capability flag/health check so callers know the compile endpoint is not ready.

### 8.2. Approach 2 — Package jdk.compiler into the runtime image

With `jlink`, you must select the implementation module when building the image. Example on JDK 17+ with `jlink`:

```bash
jlink --add-modules java.base,jdk.compiler,jdk.zipfs --output compiler-image
```

The command is illustrative: output paths and application modules need to be adjusted per deployment. `jdk.compiler` has a dependency on `java.compiler`, so selecting `jdk.compiler` will pull the API module in through the module graph. `jdk.zipfs` is useful when the compiler needs to access JAR filesystems; in a real image, check all required providers/dependencies rather than assuming these three modules alone are sufficient for every compilation workload.

When running the app, you may need to ensure `jdk.compiler` **is resolved**. If the app runs on the classpath or module path with a special configuration, it can be run with `--add-modules jdk.compiler` matching the existing module graph. **You cannot make an unpackaged module appear** just by adding a flag when the module file is not in the image.

After creating the image, you must test using the image's own binary:
- inspect the image's modules;
- run discovery code;
- perform a real compilation task with classpath and `--release` like production;
- check JAR/module path reading needs, file permissions, temp dir, and memory.

### 8.3. Approach 3 — Move compilation to build-time

If the generated source code can be known before deployment:
- generate source during build;
- run the compiler in the CI/build environment;
- package the compiled bytecode;
- at runtime, simply load the verified artifact.

Benefits:
- smaller runtime image, no need for `jdk.compiler`;
- easier to separate build duties from request handling;
- reduced CPU/memory spikes and attack surface of runtime compilation.

Do not choose compile-at-runtime just because the JavaCompiler API looks interesting; weigh the actual necessity of changing code while the application is running.

### 8.4. Approach 4 — External compiler worker/service

If code must be compiled on demand but you do not want the compiler in the main process, use a separate **build/compile worker** that has a JDK:
- clear API contract for input/version/dependencies;
- limits on CPU, RAM, disk, time, and network;
- sandbox/isolation and policy for user code;
- artifact validation/signing/checksum;
- transport, retry, timeout, and audit.

Compiling in a worker **does not by itself make the generated code safe to execute**. If loading and running user classes, appropriate isolation and security policy must be added.

### 8.5. Approach 5 — Another compiler implementation

When `java.compiler` is present, you can discover registered `javax.tools.JavaCompiler` providers via `ServiceLoader` (if the application truly supports an alternative compiler).

```java
java.util.Optional<javax.tools.JavaCompiler> alternative =
        java.util.ServiceLoader
                .load(javax.tools.JavaCompiler.class)
                .findFirst();
```

This is an illustrative snippet inside a method that has the `java.compiler` module. Do not confuse `ServiceLoader.load(JavaCompiler.class)` with `java.util.spi.ToolProvider.findFirst("javac")`. A third-party provider has its own configuration, language limitations, options, module support, and binary dependencies. Do not rely on a provider's presence without testing actual compilation.

**If `java.compiler` is absent:** you cannot simply use the normal JavaCompiler SPI without providing the API module. An external compiler process/service is a separate approach that needs to be explicitly designed/authorized.

## 9. Named modules: requires, requires static, and runtime images

When writing your own module:

```java
module com.example.dynamiccompiler {
    requires java.compiler;
}
```

This is an **illustrative module-info.java file**. `requires java.compiler;` is a **mandatory runtime dependency**. If the runtime image lacks that module, module resolution will not complete; `main` code never gets a chance to run a null-check.

If compilation is only an **optional feature**:
- you can separate the compiler implementation into a **separate module** that is only resolved when the feature is available;
- or use an appropriate optional dependency, considering `requires static java.compiler;` when the dependency is needed at compile time but optional at runtime;
- regardless of how flexible the module-info configuration is, you must **not load classes that depend on the compiler API** when the module is absent.

`requires static` does not mean the JVM automatically downloads or creates `jdk.compiler`. Nor does it guarantee the `java.compiler` module is pre-resolved just because the code compiled successfully once. Test the exact module graph in the deployment image.

### 9.1. Why can't jdeps predict every dynamically used provider?

`jdeps` analyzes module dependencies that bytecode can reference. If code only imports `javax.tools.JavaCompiler`/`ToolProvider`, the tool may point out the dependency on `java.compiler`; it **does not necessarily infer** the need for the `jdk.compiler` provider implementation from calling `getSystemJavaCompiler()` at runtime.

Therefore, in a `jlink` pipeline, there must be a step to **check service provider needs** or explicitly declare `jdk.compiler` per build policy, instead of relying solely on a static dependency scan.

### 9.2. --limit-modules differs from removing modules from an image

`--limit-modules` helps simulate a module being hidden during a run, but does not prove the runtime image's filesystem has removed the module. With `jlink`, the module may truly **not exist** in the image. Both cases can cause `getSystemJavaCompiler() == null`, but the fixes differ:
- Module is in the image but not resolved → check launcher/module graph configuration and `--add-modules`.
- Module is not in the image → must **rebuild the image** or use another runtime.
- API is present but provider is broken or configuration is unusual → diagnose service/module loader, do not just copy commands adding flags.

## 10. Common error diagnostic table

| Symptom | Possible explanation | How to check/fix |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | System compiler implementation unavailable | Check `jdk.compiler`, runtime image, launcher flags; fail fast or use another configured compiler |
| `NoClassDefFoundError: javax/tools/JavaCompiler` | `java.compiler` is not present/not resolved, but a class being loaded depends on the API | Separate optional feature; check module graph; package API module when needed |
| Startup module resolution failure | Named module has `requires java.compiler` but the image lacks the module | Build image with proper dependencies or change optional module design |
| `ToolProvider.findFirst("javac")` empty | CLI-tool provider not in current service discovery | Check `jdk.compiler`/provider and module resolution; do not infer JavaCompiler availability |
| `javac` on PATH but compiler null | Shell `javac` belongs to a different runtime/JDK, or current process modules do not contain the provider | Compare JVM/process paths, `java.home`, module graph |
| Compiler non-null but `getTask().call()` returns false | Source code error, classpath/module path, target release, or options | Read `DiagnosticCollector`; report accurate source/line |
| `IllegalArgumentException` when creating task | Invalid options/compilation units or wrong API contract | Check arguments, compilation units, option support |
| `ServiceConfigurationError` when finding provider | Broken service provider metadata/class | Check provider artifacts, loader, module descriptors |
| `ClassNotFoundException` when loading newly compiled class | Output directory not in appropriate classloader or compilation failed | Check `class.exists`, package paths, classloader, artifact policy |
| `UnsupportedClassVersionError` when loading class | Bytecode compiled for a higher release than the runtime | Choose compatible `--release`, test on target runtime |
| Cannot read JAR dependency | Classpath/module path, file permissions, or missing `jar:` filesystem provider | Check `jdk.zipfs` and dependency paths |
| Build runs on dev machine but fails in container | Image/container missing modules, different JDK path, read-only filesystem, or insufficient resources | Run probe and compile test **directly inside the final container image** |

Not every error is solved by "installing a newer JDK". If `-d` points to a read-only directory or the classpath is wrong, a full JDK still cannot complete the job. Always distinguish **discovery failure** from **compilation failure**.

## 11. Security and operations when compiling at runtime

### 11.1. Runtime compilation is not a sandbox

`JavaCompiler.getTask(...)` compiles source; it does not guarantee the input source is trusted or the compiled code is safe to execute. An application accepting source from users also needs to:
- authenticate permission to invoke compile;
- limit source size, file count, time, and CPU/memory;
- control classpath/module path;
- disable or allowlist annotation processors;
- use a separate output directory, not overwriting artifacts of other requests;
- inspect generated code before loading;
- isolate the **execution** of arbitrary code in an appropriate environment.

Do not treat `-proc:none` as a complete sandbox. With untrusted sources, **compiling in an isolated worker/process** is usually a safer choice than running the compiler in the main request-serving process.

### 11.2. Do not automatically ProcessBuilder fallback on null

An anti-pattern:

```java
if (javax.tools.ToolProvider.getSystemJavaCompiler() == null) {
    // Automatically run "javac" from PATH for every request.
}
```

This is an **anti-example**, placed inside a method that has the compiler API. Risks:
- `javac` from PATH does not match the runtime or is an unwanted binary;
- user input may be misused as CLI arguments;
- resources and outputs are not isolated;
- security/audit policies are unaware of the fallback;
- custom images may not have that executable.

If you truly use an external compiler, configure a **verified absolute path**, build arguments with `ProcessBuilder(List<String>)` (do not concatenate into a shell command), use timeouts/resource bounds, and take full responsibility for reading stdout/stderr. This is **a separate architecture**, not a side effect of `getSystemJavaCompiler() == null`.

### 11.3. File manager, class loader, and cache

- Close `StandardJavaFileManager` when the job finishes; avoid leaving file handles open.
- Have a policy to clean up output files even when compilation fails.
- Do not share mutable compiler state/file managers across multiple threads unless thread safety of the implementation and usage is confirmed.
- Ensure stale bytecode is not loaded when the compiler returns false; each job should use a separate output/scope.
- Cache compiler results only when input source, toolchain version, options, classpath, and dependency state all match.
- Changing the compiler/runtime may change diagnostics and generated bytecode; test reproducibility if the project requires deterministic build results.

## 12. Testing discovery and fallback functionality

A reliable test suite should include:

| Case | How to create the scenario | Expected result |
| --- | --- | --- |
| Full JDK | Use JDK17+ with `jdk.compiler` available | `getSystemJavaCompiler() != null`, simple source compiles successfully |
| API only | `--limit-modules java.base,java.compiler` with classpath demo | Does not crash; prints `COMPILER_UNAVAILABLE` |
| Basic runtime only | `--limit-modules java.base` with classpath demo | Does not load compiler helper; prints `API_ABSENT` |
| Invalid Java source | Use a test source with intentional syntax error | `getTask().call()` is false and diagnostics contain errors |
| Classpath missing dependency | Source references a class not on the compile path | Reports diagnostic, does not load stale bytecode |
| Unwritable output directory | Control write permissions | Reports clear I/O/compilation error, cleans up |
| Packaged runtime image | Run the `java` binary of the final image | Has all actual required modules and dependencies |
| Wrong target version | Use `--release` beyond the compiler's capability | Reports option error, guides supported versions |

**Specifically:** Tests using `--limit-modules` to simulate missing modules need to run on the **class path** as instructed by the demo. Do not take a named module that has `requires java.compiler` and expect it to start normally with `--limit-modules java.base`; that tests a different scenario: module resolution failure.

### 12.1. Do not check using only two booleans

`apiPresent && implPresent` is a supporting signal, **not a guarantee that compilation will succeed**. A reliable system also needs to test:
- `ToolProvider.getSystemJavaCompiler() != null`;
- a compilation task with proper options;
- diagnostics and output;
- filesystem/temp/classpath/module path;
- class loading/execution after compilation if the feature actually needs it.

Factors such as `jdk.zipfs` and library dependencies can cause compiling real sources to fail even when finding the provider succeeds.

### 12.2. Minimal useful logging

When the compile feature is initialized, you can log:
- `Runtime.version()` and `System.getProperty("java.home")` (if logging paths complies with policy);
- `ModuleLayer.boot().findModule("java.compiler")` / `findModule("jdk.compiler")`;
- `ToolProvider.getSystemJavaCompiler() == null`;
- number of source units, target release, and task result;
- safely processed diagnostics.

Do not log the full verbatim user source if it contains sensitive data. For multi-tenant services, separate log contexts/IDs while avoiding exposing internal paths or secret compilation options.

## 13. FAQ and common misconceptions

**Q1. The machine has `java`, so why is JavaCompiler null?**

Because a Java runtime is not required to provide a compiler implementation. `java.compiler` is the API; `jdk.compiler` is the JDK's provider. A custom runtime image may omit the implementation.

**Q2. With only `java.compiler`, can `JavaCompiler.getTask` be called?**

There is no `JavaCompiler` object from `getSystemJavaCompiler` if the provider is unavailable. The interface existing does not create a compiler by itself. Another registered provider may be considered, but it must be configured/tested separately.

**Q3. Is `java.util.spi.ToolProvider.findFirst("javac")` equivalent to `javax.tools.ToolProvider.getSystemJavaCompiler()`?**

No. The first returns an Optional of a CLI tool provider interface in `java.base`; the second returns a compiler API object in `java.compiler` or `null`.

**Q4. Do I need to add `jdk.compiler` to `module-info.java` using `requires`?**

Do not do that automatically just to use `javax.tools`; API programs usually declare `requires java.compiler`, while the JDK implementation is provided/resolved by the runtime image and service mechanism. When building an image without a compiler, you may need to **add `jdk.compiler`** to `jlink`'s root modules or appropriate flags; do not confuse the API and implementation modules.

**Q5. Why doesn't `jdeps` show `jdk.compiler` yet running still needs it?**

Because the code references the compiler **API**, while the implementation may be discovered dynamically via ToolProvider/service. Static dependency analysis does not always cover runtime provider needs.

**Q6. Does adding `--add-modules jdk.compiler` fix an image that stripped the module?**

No. The flag only helps resolve a module **already present** in the runtime/module path. If the image truly lacks `jdk.compiler`, you must rebuild the image/deploy a different runtime.

**Q7. Can `ToolProvider.getSystemToolClassLoader()` be used to bypass null?**

No. This method is deprecated and as of Java SE 17 always returns `null`. That is not the modern compiler discovery mechanism.

**Q8. Does not using annotation processors guarantee absolute safety?**

No. `-proc:none` only disables annotation processing. Compiling arbitrary source still consumes resources and the compiled classfile can still contain malicious code if loaded/run.

**Q9. JavaCompiler is non-null yet the source still fails, is it a ToolProvider bug?**

Not necessarily. Check `getTask().call()`, `DiagnosticCollector`, classpath, module path, release, file manager, and output path first.

**Q10. Does the single-file example in this lesson truly not crash when java.compiler is missing?**

Yes, with the classpath program verified on OpenJDK24 and compiled with `--release 17`: the entrypoint only uses `java.base`, checks the module, and only then references the helper class containing `javax.tools`. If converted to a named module or if the class loading structure is changed, it must be retested in that runtime image.

## 14. Exercises and answers

### Exercise 1 — Distinguish modules

An app runs on a runtime that has `java.compiler` but not `jdk.compiler`. Predict `getSystemJavaCompiler()`.

**Answer:** With a standard JDK 17 implementation, it returns `null`. The presence of the API module does not guarantee the system compiler implementation.

### Exercise 2 — Which import is correct?

To call `getSystemJavaCompiler()` and receive `JavaCompiler`, use:

```java
import javax.tools.ToolProvider;
import javax.tools.JavaCompiler;
```

**Answer:** Correct. `java.util.spi.ToolProvider` is a different CLI tool interface; `findFirst("javac")` does not return `JavaCompiler`.

### Exercise 3 — Explain the three outputs

Why can the same `CompilerDiscoveryDemo.class` print:
- `COMPILER_AVAILABLE` on a full JDK;
- `COMPILER_UNAVAILABLE` when limited to `java.base,java.compiler`;
- `API_ABSENT` when limited to only `java.base`?

**Answer:** The three states correspond to different module graphs and provider discovery. The entrypoint does not directly reference `javax.tools`, so it does not have to load the helper when the API is absent. When the API is present but the provider is absent, the compiler lookup method returns null.

### Exercise 4 — Packaging

A service needs to compile source on demand inside a runtime image created by `jlink`. `jdeps` only suggests `java.compiler`. State at least three steps to ensure the service can compile.

**Answer:** Add `jdk.compiler` to the image root modules, add supporting providers such as `jdk.zipfs` if the workload needs JAR filesystems; verify the module graph/`getSystemJavaCompiler` on the **final image**; run a real compile test with options and classpath; prepare a fallback if compilation is not a mandatory feature.

### Exercise 5 — Diagnose compile failure

`getSystemJavaCompiler() != null`, but `getTask().call()` returns `false`. Should you report "JDK is missing compiler"?

**Answer:** No. The compiler was already found. Read `DiagnosticCollector` and check source/options/dependencies/file manager. Do not replace a compilation error with a discovery error.

### Exercise 6 — Designing an optional feature

An application wants to run normally on an image with only `java.base`, but has an optional "compile Java" endpoint. Should all `JavaCompiler` types be placed in the public signatures of the main class?

**Answer:** No, if you want to ensure the main class loads safely when the API module is absent. Separate compiler-specific code into an optional class/module and only load it when the environment check succeeds; test directly on the minimal runtime.

### Exercise 7 — Difference between CLI and API

A machine has the `javac` executable on PATH; the app still gets `getSystemJavaCompiler() == null`. State two causes.

**Answer:** `javac` on PATH may belong to a **different JDK** than the JVM running the app; or the `jdk.compiler` module is unavailable/not resolved in the app's module graph (even when the `javac` binary exists on the OS). Do not use PATH as sole proof.

### Exercise 8 — Fallback policy

A user submits an untrusted Java source snippet to compile. The runtime lacks `jdk.compiler`. Should you arbitrarily run `ProcessBuilder("javac",...)` on whatever executable is found?

**Answer:** No. There must be a clear policy, a verified tool path, input and CLI argument controls, resource limits, output isolation, timeouts, and security. A sandboxed compile worker should be considered. If the feature is unsupported, return a clear capability error.

## Official documentation

- [Java SE 17 — javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler` and the condition for returning `null` when `jdk.compiler` is missing.
- [Java SE 17 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `getStandardFileManager`, and the compilation task contract.
- [Java SE 17 — javax.tools package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html): Compiler SPI and service providers.
- [Java SE 17 — java.compiler module](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/module-summary.html): Compiler APIs and language model.
- [Java SE 17 — jdk.compiler module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/module-summary.html): javac implementation, compiler tool provider, and `jdk.zipfs`.
- [Java SE 17 — java.util.spi.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ToolProvider.html): `findFirst("javac")` and command tool SPI.
- [Java SE 17 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): File manager lifecycle and compilation inputs/outputs.
- [Java SE 17 — jlink tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): Building custom runtime images with the right modules.

## Conclusion

`javax.tools.ToolProvider.getSystemJavaCompiler()` is the standard way to find the **system Java compiler** in code, but **`null` is a valid result** when the implementation is not provided. `java.compiler` contains the **API**, `jdk.compiler` contains the JDK's **actual compiler**, while `java.util.spi.ToolProvider` is a different interface for finding a **CLI tool** named `javac`. Check the module graph, avoid loading `javax.tools` when the API module is absent, always null-check the compiler, test a real compilation task, and choose a clear fail-fast/build-time/JDK-packaging/worker policy. For runtime images created by `jlink`, you need to verify **the final deployment image itself**, rather than inferring from the development machine or from `java -version` alone.
