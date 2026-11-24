# Configuring Classpath, Module Path, Output Directory, and --release When Compiling Java at Runtime

## 1. Context and Four Mandatory Configurations to Understand

In a Java system with *runtime extensibility*, the host application may receive plugin `.java` files, compile them using `javax.tools.JavaCompiler`, and load the newly generated `.class` files. Compiling inside an application differs from compiling in an IDE because **the host must explicitly decide** which dependencies are visible, the module model, where bytecode is placed, and the target Java version.

Four core parameters of this lesson:

| Configuration | javac Flag | Primary Role |
| --- | --- | --- |
| **Classpath** | `--class-path` / `-classpath` / `-cp` | Lets the compiler locate classes, packages, and JARs in the **classpath model** |
| **Module path** | `--module-path` / `-p` | Lets the compiler locate **compiled named modules** used in JPMS |
| **Output directory** | `-d` | Specifies the path to store `.class` outputs, potentially including `module-info.class` |
| **Target Java release** | `--release N` | Constrains syntax level, class-file version, and Java platform APIs to version N supported by javac |

For example, a host running on JDK 21 might want to produce a plugin usable on Java 17. `--release 17` prevents source code from using language features or Java platform APIs introduced only in Java 21. However, it **does not automatically pin the plugin's library versions** and does not guarantee the runtime JVM will find every dependency.

**Learning goal:** know when to use classpath vs. module path; pass them to `JavaCompiler.getTask`; choose a clean output directory; compile for the right release; verify outputs and load plugins without confusing compile time with runtime.

## 2. Separating Compilation from Loading

Overall workflow:

~~~text
Plugin .java file
      |
      v
JavaCompiler (javac)
      |  --class-path     -> where to find non-named-module classes/JARs
      |  --module-path    -> where to find named-module dependencies
      |  --release 17     -> syntax + bytecode + platform API
      |  -encoding UTF-8  -> charset for reading source
      |  -d build/output  -> root for generated .class files
      v
Class files in build/output
      |
      | host verifies artifacts and runtime dependencies
      v
Appropriate ClassLoader or JPMS module layer
      |
      v
Plugin loaded and invoked through shared contract
~~~

**Successful compilation is not successful loading.** The compiler needs paths to resolve types in source code. The JVM needs a loader or module graph to find classes at runtime. The `-d` flag only determines compiler output; it does not automatically add the output to the current process's classpath.

Before compiling, the host should determine whether the source is classpath code or named-module source, the actual compiler/JDK in use, the host API version the plugin is permitted to reference, trusted JARs/modules, and who owns the directories. These are explicit inputs for every build, rather than implicitly pulling in all host dependencies or the entire application classpath.

## 3. Classpath: Configuring Dependencies in the Traditional Model

Suppose the host publishes the following contract in `plugin-api.jar`:

~~~java
package demo.api;

public interface Transformer {
    String transform(String input);
}
~~~

The plugin provides an implementation:

~~~java
package demo.plugin;

import demo.api.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    public UppercaseTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

The snippets above are file contents used in the runnable example in Section 7. When compiling `UppercaseTransformer.java`, `javac` must locate `demo.api.Transformer`. If the API is inside `build/plugin-api.jar`:

~~~bash
javac --release 17 --class-path build/plugin-api.jar \
  -d build/generated/classes \
  src/plugin/demo/plugin/UppercaseTransformer.java
~~~

Where:

- `--class-path build/plugin-api.jar` is the **compile-time dependency**; it lets `javac` resolve `demo.api.Transformer`.
- `--release 17` selects Java 17 language features, class-file format, and Java platform APIs.
- `-d build/generated/classes` creates `build/generated/classes/demo/plugin/UppercaseTransformer.class` (assuming the root output directory is writable).

`--release` cannot substitute for the business library classpath: Java 17 does not inherently contain `demo.api.Transformer`. If the API JAR is missing, the compiler reports errors such as `package demo.api does not exist` or `cannot find symbol`.

### 3.1. Multiple Dependencies and Path Separators

A compile classpath can include multiple JARs or directories containing `.class` files. Use a path-list string joined according to the operating system:

| Operating System | Separator | Example |
| --- | --- | --- |
| Linux/macOS | `:` | `"build/plugin-api.jar:lib/helper.jar"` |
| Windows | `;` | `"build/plugin-api.jar;lib/helper.jar"` |

If the host constructs path strings in Java, use `File.pathSeparator` instead of hardcoding a colon. With code using the Java Compiler API, each option/value pair should be two separate list elements, e.g. `List.of("--class-path", cp)`.

Classpath wildcards, such as `lib/*`, can add JARs directly inside a directory to the classpath per Java tool rules, but they do not promise recursive scanning of subdirectories. Explicitly specify permitted APIs and libraries instead of scanning arbitrary JARs; dependency ordering and versions can affect resolution.

### 3.2. Compile-Time Classpath vs. Runtime Classpath

The plugin compiles into `build/generated/classes`, yet the running host **does not automatically see** the new classes. You can:

1. Start a new JVM with the output directory/JAR on the runtime classpath.
2. Use a `URLClassLoader` or dedicated class loader that sees the output directory.
3. For named modules, create a module layer or start the JVM with the appropriate module path.

If the compile classpath uses `plugin-api.jar` version A, while the host runtime only has an incompatible API version B, the plugin may suffer linkage/cast errors at runtime. Therefore builds should record versions and test against the real runtime API.

## 4. Module Path: JPMS Configuration Differs from Classpath

The **Java Platform Module System (JPMS)** since Java 9 uses `module-info.java` to describe named modules, `requires` dependencies, exported packages (`exports`), and services (`uses`/`provides`).

Three illustrative descriptors:

~~~java
// module-info.java file for module demo.api
module demo.api {
    exports demo.api;
}
~~~

~~~java
// module-info.java file for module demo.provider
module demo.provider {
    requires demo.api;
    provides demo.api.Transformer
            with demo.provider.UppercaseTransformer;
}
~~~

~~~java
// module-info.java file for module demo.host
module demo.host {
    requires demo.api;
    uses demo.api.Transformer;
}
~~~

These are **three separate files** (you cannot put all three declarations into one file). Section 8 provides complete source code and run commands.

`--module-path` points to **compiled named modules** inside modular JARs or exploded module directories. For example, if `demo.api` was compiled into `build/mods/demo.api`, compiling `demo.provider` can use:

~~~bash
javac --release 17 --module-path build/mods \
  -d build/mods/demo.provider \
  modsrc/demo.provider/module-info.java \
  modsrc/demo.provider/demo/provider/UppercaseTransformer.java
~~~

The compiler sees `module demo.provider` has `requires demo.api`, locates `demo.api` on the module path, and checks whether package `demo.api` is exported.

**Do not conflate** the following options:

| Option | Used For |
| --- | --- |
| `--class-path` | Classes/JARs in the unnamed-module and classpath model |
| `--module-path` | **Compiled** modules located by module name |
| `--module-source-path` | **Source** tree organized by module, typically used when compiling multiple modules together |
| `--add-modules` | Adding root modules to resolve |
| `--add-reads` | Adjusting module read edges for an intentional integration case |

A named module cannot write `requires unnamed` to automatically read classpath dependencies. When plugins and host use JPMS, place the API module properly on the module path or design an explicit bridge mechanism; avoid patching the module graph ad hoc.

A module path can contain multiple entries joined by `File.pathSeparator`. Its presence does not mean every module on disk is automatically resolved or every package is accessible. Distinguish **observable modules**, **resolved modules**, **`requires`/`reads` edges**, and **`exports`/`opens`**.

## 5. Output Directory -d and Artifact Management

`-d <dir>` specifies the root directory where `javac` writes `.class` files following the package hierarchy. For example:

~~~text
build/generated/classes/
  demo/
    plugin/
      UppercaseTransformer.class
~~~

With JPMS compiling per module, the output can look like:

~~~text
build/mods/
  demo.api/
    module-info.class
    demo/api/Transformer.class
  demo.provider/
    module-info.class
    demo/provider/UppercaseTransformer.class
  demo.host/
    module-info.class
    demo/host/ModHost.class
~~~

Directory `build/mods` holds exploded modules in its direct subdirectories. `module-info.class` resides at the root directory **of each module**.

Important rules when compiling at runtime:

- Create the output directory with `Files.createDirectories(output)` and verify write permissions. Never let user-supplied source dictate output paths outside host-controlled areas.
- Use separate paths per plugin/build/version to avoid mixing files from old compilations into new ones.
- A failed compilation can still emit **partial output**. Never publish or load this directory merely because `.class` files exist inside it.
- `-d` does not automatically turn the output into a runtime classpath/module path; the loader must be configured explicitly.
- `-s` is for generated sources from annotation processing; `-h` is for native headers when needed. Do not use `-d` to mix different output kinds in the same directory without control.
- When swapping plugin versions, compile into a new location and switch to that artifact only after QA passes. Avoid overwriting directories/JARs currently used by running plugin loaders or threads.
- Clean up outputs according to lifecycle once certain no reader, handle, class loader, or task still needs the old artifact.

The output directory serves as a **build artifact**, not implicitly as a source of truth or a free-for-all scratch area for any plugin to write files. If reproducibility is required, record source hash, compiler version, options, dependency versions, and build ID.

## 6. --release vs. -source/-target

`--release 17` instructs the compiler to generate class files compatible with Java 17 and allow only syntax and Java platform APIs supported in Java 17. For Java 17, the class-file major version is **61**.

| Configuration | Syntax | Bytecode | Java Platform API Restriction |
| --- | --- | --- | --- |
| `--release 17` | Java 17 | Java 17 | Yes: per release 17 APIs |
| `-source 17 -target 17` | Java 17 | Java 17 | Not guaranteed when `javac` runs on a newer JDK |
| No version flag | Default of the invoked `javac` | Default of `javac` | Can change when upgrading the compiler |

When using `-source 17 -target 17` on a newer JDK, code can still reference a Java platform method introduced in a newer release; emitting bytecode version 61 **does not prevent a Java 17 runtime from failing** because that method does not exist. `--release 17` is the standard way to constrain source, target, and platform APIs in a single option.

Notes:

1. Do not combine `--release` with `-source` or `-target` in the same compilation task.
2. A `javac` binary only supports the releases it advertises in `javac --help`; JDK 17 cannot compile with `--release 21`.
3. `--release 17` does not pin JAR versions outside the JDK. Dependencies compiled for Java 21 or mismatched host/plugin APIs can still break build/runtime.
4. `--release` is not a sandbox; it does not prevent sources, annotation processors, or loaded bytecode from having side effects at runtime.
5. If the host uses the `JavaCompiler` API, pass flags as separate option elements, e.g. `List.of("--release", "17")`. Avoid combining them into a single `"--release 17"` string passed to `getTask`.

For a plugin system, run **integration tests on the target runtime** in addition to compiling with `--release`.

## 7. Runnable Java 17 Program: Host Invoking JavaCompiler to Compile a Plugin

This example demonstrates classpath, `-d`, and `--release` in one realistic flow. Only the host and API are compiled upfront; the plugin source still has no `.class` file. At runtime, the host invokes the compiler, generates the class output, and actively loads it.

### 7.1. Directory Structure

~~~text
runtime-compiler-demo/
  src/
    api/demo/api/Transformer.java
    plugin/demo/plugin/UppercaseTransformer.java
    host/demo/host/CompileHost.java
  build/
    api/
    host/
    plugin-api.jar
    generated/classes/
~~~

The files below live at the exact paths shown above. The `build` directory is created while running the commands; there is no need to create `.class` files manually.

### 7.2. API Contract File

**`src/api/demo/api/Transformer.java`:**

~~~java
package demo.api;

public interface Transformer {
    String transform(String input);
}
~~~

### 7.3. Plugin Source File

**`src/plugin/demo/plugin/UppercaseTransformer.java`:**

~~~java
package demo.plugin;

import demo.api.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    public UppercaseTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

The interface belongs to the shared API; the implementation knows only the contract and the Java standard library. We have not used `javac` in the terminal to compile the plugin file yet.

### 7.4. Host File Invoking JavaCompiler API

**`src/host/demo/host/CompileHost.java`:**

~~~java
package demo.host;

import demo.api.Transformer;
import java.net.URL;
import java.net.URLClassLoader;
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

public final class CompileHost {
    private CompileHost() {
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with a system compiler is required");
        }

        Path source = Path.of(
                "src/plugin/demo/plugin/UppercaseTransformer.java");
        Path apiJar = Path.of("build/plugin-api.jar");
        Path output = Path.of("build/generated/classes");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        List<String> options = List.of(
                "--release", "17",
                "-encoding", "UTF-8",
                "-proc:none",
                "--class-path", apiJar.toString(),
                "-d", output.toString()
        );

        boolean compiled;
        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjectsFromPaths(List.of(source));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics, options, null, units);
            compiled = Boolean.TRUE.equals(task.call());
        }

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            System.err.println(
                    d.getKind() + ": " + d.getMessage(Locale.ROOT));
        }

        System.out.println("compiled=" + compiled);
        if (!compiled) {
            throw new IllegalStateException("Plugin compilation failed");
        }

        URL classesUrl = output.toUri().toURL();
        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{classesUrl},
                CompileHost.class.getClassLoader())) {

            Class<?> implementation = Class.forName(
                    "demo.plugin.UppercaseTransformer", true, loader);
            Transformer plugin = (Transformer) implementation
                    .getDeclaredConstructor().newInstance();

            System.out.println(
                    "result=" + plugin.transform("hello plugin"));
        }
    }
}
~~~

**Important points explained:**

1. `ToolProvider.getSystemJavaCompiler()` retrieves the system compiler on a suitable JDK. A runtime image without a compiler can return `null`; the host must report an explicit error.
2. `StandardJavaFileManager` converts `Path`s into `JavaFileObject`s, handles I/O, and is closed via try-with-resources. `DiagnosticCollector` records compile errors/warnings.
3. `--class-path build/plugin-api.jar` lets `javac` resolve `demo.api.Transformer` needed by the plugin. The host is not compiled against the plugin implementation.
4. `--release 17` targets Java 17; `-encoding UTF-8` ensures consistent source decoding. `-proc:none` disables annotation processing since the example uses no processors.
5. `-d build/generated/classes` specifies the output files. After compiling, the host creates a `URLClassLoader` pointing to that output.
6. The plugin loader's parent is `CompileHost`'s loader, which already knows `Transformer`, allowing casting to the shared interface.
7. The host loads the plugin only if the compilation task returns `true`. A task returning `false` must carry diagnostics; never reuse leftover classes from an earlier compile.
8. `URLClassLoader.close()` closes resources managed by the loader, yet does not automatically terminate plugin threads or guarantee immediate class unloading. Real plugins require an explicit lifecycle contract.

Relative paths are resolved against **the host process's working directory**. When running from another directory, compute absolute paths or pass explicit configuration. Do not build a shell command by concatenating user source paths: `getTask` takes an **option list**, allowing the host to validate each path and policy before invoking the compiler.

### 7.5. Compile and Run Commands

From the `runtime-compiler-demo` directory on Linux/macOS with JDK 17+, using Bash:

~~~bash
mkdir -p build/api build/host

# Compile the API and package it into a JAR.
javac --release 17 -encoding UTF-8 \
  -d build/api src/api/demo/api/Transformer.java
jar --create --file build/plugin-api.jar -C build/api .

# Host is compiled against the API without needing the plugin implementation.
javac --release 17 -encoding UTF-8 \
  --class-path build/plugin-api.jar \
  -d build/host src/host/demo/host/CompileHost.java

# Do not compile UppercaseTransformer in the terminal.
# CompileHost will invoke JavaCompiler at runtime.
java --class-path "build/host:build/plugin-api.jar" \
  demo.host.CompileHost
~~~

**Exact stdout on successful build:**

~~~text
compiled=true
result=HELLO PLUGIN
~~~

Since the source is valid, no diagnostics are printed to stderr in a successful run. After the host finishes, the following appears:

~~~text
build/generated/classes/
  demo/plugin/UppercaseTransformer.class
~~~

On Windows PowerShell, the corresponding launch command (after building the JAR and host classes) uses a semicolon:

~~~powershell
java --class-path "build/host;build/plugin-api.jar" demo.host.CompileHost
~~~

Multi-line Bash commands use backslash line continuations, whereas PowerShell should run `javac`/`jar` on a single line or use PowerShell syntax.

### 7.6. What Happens If Options Change?

- Omitting `--class-path build/plugin-api.jar` when compiling the plugin: `javac` cannot see `demo.api.Transformer` and reports package/symbol errors.
- Omitting `-d`: output may go to a default location other than where the host expects. With a runtime compiler, set an intentional location for easier control and cleanup.
- Using `--release 21` on JDK 17: the compiler does not support targets newer than itself; do not assume compilation will succeed.
- Pointing `-d` to an old directory still holding previous-version class files: a failed compile might still leave behind seemingly valid artifacts. Use a fresh output directory per build so compilations never get confused.
- Omitting `URLClassLoader` or misconfiguring the runtime classpath: compilation succeeds, yet the host does not automatically see classes in `-d`.
- Creating another copy of `Transformer.class` inside the plugin loader: risks two distinct class identities, causing subtype/cast failures.

## 8. Complete JPMS Example: Three Named Modules and Module Path

Now compile **a different program** using JPMS. There are three named modules: API, provider, and host. On the module path, the provider uses `provides` in its descriptor instead of `META-INF/services` as in classpath SPI.

### 8.1. Source Layout

~~~text
modsrc/
  demo.api/
    module-info.java
    demo/api/Transformer.java
  demo.provider/
    module-info.java
    demo/provider/UppercaseTransformer.java
  demo.host/
    module-info.java
    demo/host/ModHost.java
build/
  mods/                (created during compilation steps)
~~~

Module names in `module-info.java` must match the names referenced by `requires` and `--module`.

**`modsrc/demo.api/module-info.java`:**

~~~java
module demo.api {
    exports demo.api;
}
~~~

**`modsrc/demo.api/demo/api/Transformer.java`:**

~~~java
package demo.api;

public interface Transformer {
    String transform(String input);
}
~~~

**`modsrc/demo.provider/module-info.java`:**

~~~java
module demo.provider {
    requires demo.api;
    provides demo.api.Transformer
            with demo.provider.UppercaseTransformer;
}
~~~

**`modsrc/demo.provider/demo/provider/UppercaseTransformer.java`:**

~~~java
package demo.provider;

import demo.api.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    public UppercaseTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**`modsrc/demo.host/module-info.java`:**

~~~java
module demo.host {
    requires demo.api;
    uses demo.api.Transformer;
}
~~~

**`modsrc/demo.host/demo/host/ModHost.java`:**

~~~java
package demo.host;

import demo.api.Transformer;
import java.util.ServiceLoader;

public final class ModHost {
    private ModHost() {
    }

    public static void main(String[] args) {
        int count = 0;
        for (Transformer provider : ServiceLoader.load(Transformer.class)) {
            count++;
            System.out.println(
                    "module=" + provider.transform("hello module"));
        }
        if (count == 0) {
            throw new IllegalStateException("No provider resolved");
        }
    }
}
~~~

Module `demo.provider` does not need `exports demo.provider` for its service provider to be discovered by `ServiceLoader` once declared in `provides` and the module is resolved. The host uses only the API and `ServiceLoader`, without referencing the implementation name.

### 8.2. Compiling Each Module with --module-path

In a terminal in the directory containing `modsrc`, with JDK 17+:

~~~bash
mkdir -p build/mods/demo.api build/mods/demo.provider build/mods/demo.host

# 1. API module.
javac --release 17 -encoding UTF-8 \
  -d build/mods/demo.api \
  modsrc/demo.api/module-info.java \
  modsrc/demo.api/demo/api/Transformer.java

# 2. Provider module needs demo.api from the module path.
javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.provider \
  modsrc/demo.provider/module-info.java \
  modsrc/demo.provider/demo/provider/UppercaseTransformer.java

# 3. Host module also needs demo.api.
javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.host \
  modsrc/demo.host/module-info.java \
  modsrc/demo.host/demo/host/ModHost.java

# 4. Run host module, explicitly resolving the provider.
java --module-path build/mods --add-modules demo.provider \
  --module demo.host/demo.host.ModHost
~~~

**Stdout:**

~~~text
module=HELLO MODULE
~~~

`--add-modules demo.provider` ensures the provider module is included in the module graph in the demo. `demo.host` declares `uses demo.api.Transformer` and `demo.provider` declares `provides`, so `ServiceLoader` returns the implementation.

Compilation output:

~~~text
build/mods/
  demo.api/
    module-info.class
    demo/api/Transformer.class
  demo.provider/
    module-info.class
    demo/provider/UppercaseTransformer.class
  demo.host/
    module-info.class
    demo/host/ModHost.class
~~~

`build/mods` is the directory holding the exploded child modules, so pass it as `--module-path` for compiling/running. If multiple module-path entries are needed on Windows, join them with a semicolon; the current example has only **one** entry `build/mods`, so no separator is required.

### 8.3. Alternative: Compiling Multiple Modules via --module-source-path

With the layout `modsrc/<module-name>/...`, all three modules can be compiled **in a single `javac` invocation**, instead of the three separate compile commands above:

~~~bash
mkdir -p build/allmods
javac --release 17 -encoding UTF-8 \
  --module-source-path modsrc \
  -d build/allmods \
  --module demo.api,demo.provider,demo.host
java --module-path build/allmods --add-modules demo.provider \
  --module demo.host/demo.host.ModHost
~~~

The `--module-source-path` flag describes **where to find per-module sources**, whereas `--module-path` describes where to find **already-compiled modules**. When compiling all three modules from scratch, `--module-source-path` tells `javac` the layout and inter-module dependencies within a single task.

In the Java Compiler API, option configuration looks like (illustrative snippet, not a standalone program):

~~~java
List<String> moduleOptions = List.of(
        "--release", "17",
        "--module-source-path", "modsrc",
        "--module", "demo.api,demo.provider,demo.host",
        "-d", "build/allmods"
);
~~~

Use `JavaCompiler.getTask` with an appropriate file manager, or compile one module at a time across multiple tasks while updating the module path after each step. Do not neglect publishing outputs and configuring class loaders/module layers after compilation: newly compiled modules do not automatically enter the module graph of an already-started host JVM.

## 9. Mapping to the Java Compiler API

`JavaCompiler` belongs to package `javax.tools` in module `java.compiler`. The Section 7 example uses `getTask` with `StandardJavaFileManager` and `DiagnosticCollector`. On standard JDKs, the compiler is obtained via `ToolProvider.getSystemJavaCompiler()`.

| Need | Command-Line javac | getTask options List |
| --- | --- | --- |
| Classpath libraries | `--class-path cp` | `List.of("--class-path", cp)` |
| Module dependencies | `--module-path mp` | `List.of("--module-path", mp)` |
| Multi-module source layout | `--module-source-path src` | `List.of("--module-source-path", src)` |
| Select modules to compile | `--module names` | `List.of("--module", names)` |
| Class file output | `-d out` | `List.of("-d", out)` |
| Target platform release | `--release 17` | `List.of("--release", "17")` |
| Source charset | `-encoding UTF-8` | `List.of("-encoding", "UTF-8")` |
| Disable annotation processing | `-proc:none` | `List.of("-proc:none")` |
| Processor-generated source code | `-s generated` | `List.of("-s", generated)` |

Besides options, `StandardJavaFileManager` lets you configure locations such as `StandardLocation.CLASS_PATH`, `MODULE_PATH`, `CLASS_OUTPUT`, and `SOURCE_OUTPUT`. You can use the corresponding setters to configure paths programmatically; avoid passing options that conflict with locations set on the file manager. `getTask` accepts sources via `Iterable<? extends JavaFileObject>`, rather than concatenating shell commands and spawning a subprocess.

**Important regarding paths:** in a Java process, a relative path such as `build/plugin-api.jar` resolves against the working directory, not automatically relative to the source file's directory. The host should resolve paths, verify they stay within permitted zones, log normalized paths, and choose the OS-appropriate `File.pathSeparator` when building path lists.

**Diagnostics and results:** when a task returns `false`, `DiagnosticCollector` holds details that can include file, line, column, and severity. Log them under the build ID; do not load stale outputs. When a task throws an exception due to path, file manager, or option configuration, report a clear error as well. A compile run should only be declared successful when both the compiler result and the system's artifact checks pass.

## 10. Common Errors

| Symptom | Typical Cause | How to Inspect |
| --- | --- | --- |
| `package ... does not exist` / `cannot find symbol` | Missing API/dependency on classpath, or module package is not read/exported | Check `--class-path`, `--module-path`, `requires`/`exports` |
| `module not found` | Wrong module/output name or module missing from `--module-path` | Check `module-info.class` and module name |
| Compiles successfully, then `ClassNotFoundException` | Output `-d` is absent from runtime classpath/loader | Check class files, class loader URLs, runtime paths |
| Compiles successfully, then `NoClassDefFoundError` | Missing runtime dependency or class linkage failure | Inspect cause/stack trace and runtime dependencies |
| `UnsupportedClassVersionError` | Class compiled for a newer Java than runtime | Match `javac --release` with target JVM |
| Provider module exists, yet ServiceLoader is empty | Provider module unresolved or `uses`/`provides` mismatch | Check `--add-modules`, module graph, descriptors |
| Plugin throws `ClassCastException` | API defined by two class loaders or wrong type | Keep API shared; check defining loader |
| Output contaminated with stale files | Reused output directory after failed build or package rename | Use a clean directory per build/version |
| `ToolProvider.getSystemJavaCompiler() == null` | Running JVM lacks system compiler | Use a JDK/runtime image containing the compiler |
| API error on older Java runtime | Used `-source/-target` without constraining platform APIs, or external library too new | Use `--release` and test on real runtime |
| Compiler reports errors, yet host still loads | Did not check `CompilationTask.call()` / diagnostics | Fail-fast, roll back artifacts, never run stale classes |

If compilation fails, fix **compilation** errors first. If compilation succeeds yet loading fails, inspect **runtime paths, class loader identity, module resolution, and dependencies** rather than assuming the compiler ignored flags.

## 11. Operational Conventions for Dynamic Compilation

An implementation can enforce these policies:

1. **Inputs and versioning:** accept source, plugin ID, classpath/module mode, API version, `--release` target, and an allowlist of dependencies. Never pull in the entire host classpath indiscriminately.
2. **Output ownership:** the compiler service creates dedicated build directories without modifying directories in active use by running plugins. Structure outputs for traceability and lifecycle cleanup.
3. **Idempotency:** given identical pinned source, options, compiler, and dependencies, build results can be verified/matched by fingerprint. Prevent stale build files from altering outcomes.
4. **Build failures:** collect diagnostics, mark the build failed, never publish partial outputs, and never silently fall back to an old class.
5. **Publishing:** verify bytecode/manifest/dependencies before promoting a new plugin to active; maintain a rollback path to a verified artifact.
6. **Runtime boundary:** select the class loader/module layer only after compilation completes; check API compatibility and stop/cancel/close old plugins per contract.
7. **Safety:** disable processors when unneeded (e.g. `-proc:none`). Compilers/processors and loaded bytecode/plugins can run code with side effects; `--release`, `-proc:none`, and class loaders **are not a sandbox** for untrusted code. When needed, compile and run in an isolated process with OS, CPU, memory, and time limits.

A compile task running inside the host JVM can also consume substantial time and memory. Production systems should cap concurrent jobs, enforce contract timeouts/cancellations, and protect storage against unbounded outputs.

## 12. Quick Self-Check

1. `UppercaseTransformer.java` needs `demo.api.Transformer` from a JAR: which flag makes the API visible to `javac`? **`--class-path build/plugin-api.jar`**.
2. You want `.class` files in `build/generated/classes`: use **`-d build/generated/classes`**, and after compiling ensure the loader can see that directory.
3. You have `module-info.java` with `requires demo.api` and the API module is already compiled: use **`--module-path`** pointing to the module path containing `demo.api`.
4. You have a source tree `modsrc/demo.api`, `modsrc/demo.provider`, `modsrc/demo.host`: use **`--module-source-path modsrc`** to compile multiple modules in one pass.
5. Host runs JDK 21, plugin must run on Java 17: use **`--release 17`** and test dependencies/runtime on Java 17. `-target 17` alone is insufficient to constrain platform APIs.
6. Using `getTask`: each compiler option and its value must be passed as **separate elements** in `List<String>`; `"--release 17"` is not a valid single element replacing `"--release", "17"`.
7. You see `compiled=true` but the host cannot find the class: check **loader/runtime classpath or module layer**; `-d` only writes outputs.
8. A new build fails, leaving old classes in the directory: **never load those files**; use a fresh build directory per build and publish only qualifying artifacts.

**Conclusion:** When compiling plugins at runtime, correctly decide **classpath vs. module path**, pass explicit dependencies, specify a host-controlled **output directory**, and set **`--release`** matching the target runtime. Separating compilation from class loading—together with diagnostics and artifact management—lets a host gain extensibility without turning the compiler into an uncontrolled source of state.
