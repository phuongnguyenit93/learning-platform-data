# 16.4 Configuring `CompilationTask`, class path, module path, `--release`, and annotation processing

## 1. Runtime Java compilation is not just calling `javac`

In Java 17, the `javax.tools` package (module `java.compiler`) allows a Java program to invoke the Java compiler via API. Common scenarios are code editors, template engines, build tools, plugin runtimes, online judges, or services that convert Java source into `.class` while the application is running.

The main axis of the API is:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
JavaCompiler.CompilationTask task =
    compiler.getTask(out, fileManager, diagnostics,
                     options, classes, compilationUnits);
Boolean success = task.call();
~~~

This is an **illustrative snippet**, not a standalone program; the input variables need to be created. `CompilationTask` is **a configured compilation run**: inputs, class path, module path, platform target `--release`, annotation processing mechanism, and where to write output must all be decided **before calling `call()`**. `call()` executes the work, returning `true` on success, `false` if the compilation process fails. Some misconfigurations can throw an exception immediately when creating the task or at runtime instead of returning false.

This lesson distinguishes the exact responsibilities:

- **`JavaCompiler`**: creates the compilation task.
- **`StandardJavaFileManager`**: manages source/bytecode, reads classes/JARs/modules, maps paths.
- **`DiagnosticCollector`**: receives ERROR/WARNING/NOTE messages with source, position, and error code.
- **`options` of the task**: options corresponding to `javac` such as `-classpath`, `--module-path`, `--release`, `-d`, `-processorpath`, `-processor`, `-proc:none`.
- **`compilationUnits`**: the set of `JavaFileObject`s to compile.
- **`classes`**: names of classes to be processed by **annotation processing**, not a way to set the class path or specify output.
- **Runtime class loader**: a separate step after compilation; `CompilationTask` produces `.class` files but does not automatically load them into the application's class loader.

All demonstration programs use Java 17+, with no IDE dependency. The examples have been tested with `javac --release 17` and a newer JDK running the Java compiler API in target 17 mode.

## 2. The parameters of `getTask` are not interchangeable

Standard signature:

~~~java
JavaCompiler.CompilationTask getTask(
    Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
)
~~~

This is an **API declaration for explanation**, not a function you need to implement.

| Parameter | What is it used for? | Example |
| --- | --- | --- |
| `out` | Where to write **additional information** that does not go through `DiagnosticListener`; `null` uses the default output | `new StringWriter()` |
| `fileManager` | Source and output files, JAR/class path, module locations, processor discovery | `compiler.getStandardFileManager(...)` |
| `diagnosticListener` | Collects diagnostics during compilation | `DiagnosticCollector<JavaFileObject>` |
| `options` | Valid compiler options, passed **as separate strings** | `List.of("--release","17","-d","out")` |
| `classes` | Names of classes for annotation processing to process; usually `null` when compiling from source | `null` |
| `compilationUnits` | `JavaFileObject`s of kind SOURCE to compile; can be `null` when using `-m` to select source modules | `manager.getJavaFileObjectsFromPaths(List.of(source))` |

### Recommended lifecycle

~~~text
ToolProvider.getSystemJavaCompiler()
          |
          v
Does compiler exist? (requires jdk.compiler at runtime)
          |
          v
Create DiagnosticCollector + StandardJavaFileManager
          |
          v
Configure source paths, output, dependencies, processors
          |
          v
Build List<String> options and JavaFileObject inputs
          |
          v
JavaCompiler.getTask(...)
          |
          v
CompilationTask.call() -> Boolean success
          |
      +---+---+
      |       |
     true    false
      |       |
      v       v
  .class   Read DiagnosticCollector
      |
      v
Load/run class (if the application needs it)
~~~

**Do not reuse the same `CompilationTask` to call `call()` multiple times.** Each new compilation pass should create a new task. You can reuse `JavaCompiler` or a `StandardJavaFileManager` sequentially to leverage JAR/file-system caching per the API contract, but you must manage lifecycle and path state consistently.

**Do not assume a JDK always has a compiler**: `ToolProvider.getSystemJavaCompiler()` can return `null` if the runtime image does not contain the `jdk.compiler` module (for example, a custom `jlink` image). Java 17 `java.compiler` provides the API, but the actual compiler implementation resides in `jdk.compiler`. For an application that needs dynamic compilation, check for the compiler on startup and deploy with a JDK/runtime image that includes the compiler.

## 3. Two ways to configure file locations

You can set locations via **compiler options** or via **`StandardJavaFileManager`**. You should not configure both places conflictingly and expect the compiler to guess your intent.

| Purpose | `javac` option when using `getTask` | `StandardLocation` when using file manager |
| --- | --- | --- |
| Where to find non-modular dependencies | `-classpath` / `--class-path` | `CLASS_PATH` |
| Where to find compiled named modules | `--module-path` | `MODULE_PATH` |
| `.class` output | `-d` | `CLASS_OUTPUT` |
| Where to write Java source generated by processors | `-s` | `SOURCE_OUTPUT` |
| Processor path on class path | `-processorpath` / `--processor-path` | `ANNOTATION_PROCESSOR_PATH` |
| Processor path as named modules | `--processor-module-path` | `ANNOTATION_PROCESSOR_MODULE_PATH` |
| Regular Java sources | `--source-path`, or `compilationUnits` | `SOURCE_PATH` |
| Multiple named module sources | `--module-source-path` | `MODULE_SOURCE_PATH` |

A configuration via file manager (this is a **snippet**, not standalone):

~~~java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null,
                                        java.nio.charset.StandardCharsets.UTF_8)) {
    manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        java.util.List.of(java.nio.file.Path.of("libs/dependency.jar")));
    manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        java.util.List.of(java.nio.file.Path.of("build/classes")));

    // Create the task using the configured manager itself.
}
~~~

If you choose this approach, pre-create the necessary directories and clearly determine whether the path corresponds to a file/JAR or an output directory. `setLocationFromPaths` is supported by `StandardJavaFileManager` on `Path`s of a compatible file system; it is not a way to pass a single `Path` parameter into `getTask`.

For small programs, using `List<String> options` is easier to cross-reference with command-line `javac`. For build tools with many compilation passes, the file manager and `StandardLocation` allow managing locations in a more structured way.

## 4. Class path: how to compile a project without JPMS

**Class path** contains directories/JARs with classes in the **unnamed module**. If Java source `app.App` imports compiled `lib.Helper`, the task needs to know where `Helper.class` is located. `-classpath` belongs to the **compiler resolution** step, distinct from the class loader when running the application.

The following example creates two source files itself, compiles the library, intentionally compiles the app **without a class path** to collect diagnostics, then adds the class path and runs the resulting class using a separate class loader. It also verifies that `--release 17` produces bytecode class-file major version **61**.

### Example 1 — `CompilationTaskDemo.java`

Save all the code below:

~~~java
import javax.tools.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.io.*;
import java.net.*;
import java.util.*;

public class CompilationTaskDemo {
    static Path write(Path base, String relative, String source)
            throws IOException {
        Path file = base.resolve(relative);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
        return file;
    }

    static boolean compile(
            JavaCompiler compiler,
            Path file,
            List<String> options,
            DiagnosticCollector<JavaFileObject> reports)
            throws IOException {
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        reports, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> inputs =
                    manager.getJavaFileObjectsFromPaths(List.of(file));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    new StringWriter(), manager, reports,
                    options, null, inputs);
            return Boolean.TRUE.equals(task.call());
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires JDK");

        Path root = Path.of(args[0]);
        Path library = write(root, "src/lib/Helper.java",
                "package lib; public class Helper { " +
                "public static String hi(String n){return \"Hi-\"+n;} }");
        Path app = write(root, "src/app/App.java",
                "package app; import lib.Helper; " +
                "public class App { public static String run(){ " +
                "return Helper.hi(\"Ada\"); } }");
        Path wrong = write(root, "src/app/Broken.java",
                "package app; public class Broken { int n = \"wrong\"; }");

        Path libOut = root.resolve("libOut");
        Path appOut = root.resolve("appOut");

        var d1 = new DiagnosticCollector<JavaFileObject>();
        boolean libOk = compile(compiler, library,
                List.of("--release", "17", "-proc:none",
                        "-encoding", "UTF-8",
                        "-d", libOut.toString()), d1);
        System.out.println("libCompiled=" + libOk);

        var missing = new DiagnosticCollector<JavaFileObject>();
        boolean withoutCp = compile(compiler, app,
                List.of("--release", "17", "-proc:none",
                        "-d", appOut.toString()), missing);
        System.out.println("withoutClassPath=" + withoutCp);
        System.out.println("missingErrors=" +
                missing.getDiagnostics().stream()
                        .filter(x -> x.getKind() ==
                                Diagnostic.Kind.ERROR).count());

        var d2 = new DiagnosticCollector<JavaFileObject>();
        boolean appOk = compile(compiler, app,
                List.of("--release", "17", "-proc:none",
                        "-classpath", libOut.toString(),
                        "-d", appOut.toString()), d2);
        System.out.println("withClassPath=" + appOk);

        byte[] compiled = Files.readAllBytes(
                appOut.resolve("app/App.class"));
        int major = ((compiled[6] & 0xff) << 8) |
                    (compiled[7] & 0xff);
        System.out.println("classMajor=" + major);

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{appOut.toUri().toURL(),
                          libOut.toUri().toURL()}, null)) {
            Class<?> type = loader.loadClass("app.App");
            System.out.println(
                    "call=" + type.getMethod("run").invoke(null));
        }

        var invalid = new DiagnosticCollector<JavaFileObject>();
        boolean badOk = compile(compiler, wrong,
                List.of("--release", "17", "-proc:none",
                        "-d", root.resolve("badOut").toString()),
                invalid);
        System.out.println("invalidCompiled=" + badOk);
        System.out.println("invalidErrors=" +
                invalid.getDiagnostics().stream()
                        .filter(x -> x.getKind() ==
                                Diagnostic.Kind.ERROR).count());
    }
}
~~~

Run from any working directory where you have write permission, with JDK 17 or later:

~~~sh
javac --release 17 CompilationTaskDemo.java
java CompilationTaskDemo work/basic
~~~

**Verified stdout with a JDK running the compiler API at `--release 17`:**

~~~text
libCompiled=true
withoutClassPath=false
missingErrors=2
withClassPath=true
classMajor=61
call=Hi-Ada
invalidCompiled=false
invalidErrors=1
~~~

**Warning about diagnostic counts:** 2 and 1 are the number of ERROR messages in the tested example environment; compiler implementation/JDK and how the source is written can cause **diagnostic counts to vary**. The invariants to verify are `withoutClassPath=false`, `withClassPath=true`, `invalidCompiled=false`, class version 61, and the result `Hi-Ada` when compilation/runtime are correct.

Analysis:

1. The Compiler API is obtained from `ToolProvider`. `compile(...)` creates a file manager with `UTF-8` and closes it via try-with-resources.
2. `getJavaFileObjectsFromPaths(List.of(file))` turns a `Path` into a source compilation unit for the task. `classes=null` because this pass does not require annotation processing on class names.
3. `lib.Helper` is compiled into `work/basic/libOut`.
4. The first compilation pass for `app.App` intentionally **omits `-classpath libOut`**, so the `lib.Helper` import cannot be resolved; `CompilationTask.call()` returns false and errors go into `DiagnosticCollector`.
5. The second pass adds `-classpath libOut`, so compilation succeeds into `work/basic/appOut`. Library output does not automatically become the compiler class path just because it exists in a directory.
6. Bytecode major 61 matches Java 17. `--release 17` also restricts syntax and Java SE/JDK APIs published for release 17; it does not just set the major version.
7. `URLClassLoader` with two URLs allows loading both the app and the library in a separate runtime layer. **CompilationTask does not automatically inject bytecode into the current class loader.**
8. `Broken.java` has an `int` field receiving a String, so compilation fails; the program counts diagnostics without printing locale-dependent messages.

**Do not use a class loader that has already loaded `app.App` as an unlimited "replace with the same name" mechanism:** the JVM binds class identity by binary name + defining loader. To reload a different version of the same name, you usually need a new class loader or a specialized instrumentation/redefinition mechanism; recompiling alone does not make the class change on its own.

## 5. `--release`: syntax, platform API, and class-file version

`--release 17` is not simply the two flags `-source 17 -target 17`. It instructs the compiler to:

- Check **Java 17 language** (disallow Java 18+ syntax).
- Emit bytecode compatible with **class-file major version 61**.
- Compile against **Java SE/JDK APIs published for release 17**, preventing accidental calls to APIs only available on newer JDKs while producing major 61 class files.
- Restrict certain compiler options used to open access to JDK internals of the target release.

Common class-file milestone table:

| `--release` | Class-file major |
| --- | ---: |
| `11` | 55 |
| `17` | 61 |
| `21` | 65 |

**Do not mix `--release` with `-source`/`-target` in the same task**; `javac` rejects conflicting configurations. When compiling modules targeting 17, `--release 17` still supports JPMS, but appropriate module source path/module dependencies must be provided.

In `getTask`, place the option and its value in **two separate elements**:

~~~java
List<String> options = List.of(
    "--release", "17",
    "-encoding", "UTF-8",
    "-proc:none",
    "-d", "build/classes"
);
~~~

This is a **configuration snippet**, not a standalone program. Do not write `List.of("--release 17", "-d build/classes")` and expect the compiler to parse it like a pre-split shell command; `Iterable<String> options` must contain the tokens as `javac` receives them.

**Verify actual compatibility:** test-run the application on the target JDK 17. `--release` does not cover every third-party dependency, native code, reflection internals, deployment module graph configuration, or operating system environment.

## 6. Class path and module path are not the same thing

| Aspect | Class path | Module path |
| --- | --- | --- |
| Primary target | Classes/JARs in the **unnamed module** | Named modules: module descriptors and package exports/readability |
| Options | `-classpath`, `--class-path` | `--module-path`, `-p` |
| Module descriptor | Does not require `module-info.java` | Has `module-info.class` or automatic module metadata if using automatic JARs |
| Package access | Java public/package rules and loader context | In addition to Java visibility, there are `requires`/readability and `exports` |
| How source modules are specified | `compilationUnits` of regular source files | `--module-source-path` and `-m module.name` to compile multiple modules |
| Typical output | `build/classes/p/Foo.class` | `mods/m.name/p/Foo.class` when compiling multiple modules |

**`-classpath` does not replace `--module-path`** when Java source resides in a named module and dependencies must be resolved through the module graph. Conversely, placing a non-modular JAR on the module path can turn it into an **automatic module** whose name must be clearly determined, and it should not be assumed to have the same access semantics as the class path.

If you only need to compile a single module, you can pass the module's `JavaFileObject`s in `compilationUnits` and configure `--module-path` for compiled dependencies. If you need to compile **multiple modules from one source tree**, `--module-source-path` combined with `-m` is the clear way to express it.

### Example 2 — `ModuleTaskDemo.java`

The program creates two named modules:

~~~text
work/modules/src/
  m.lib/
    module-info.java
    lib/Greeter.java
  m.app/
    module-info.java
    app/Main.java
~~~

`m.lib` declares `exports lib`. `m.app` declares `requires m.lib`, then calls `lib.Greeter.hello()`. Instead of manually obtaining a `JavaFileObject` for each file, the task passes the option `-m m.lib,m.app` and `compilationUnits=null`; the compiler will traverse the module sources from `--module-source-path`.

Save **`ModuleTaskDemo.java`**:

~~~java
import javax.tools.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class ModuleTaskDemo {
    static void write(Path root, String name, String source)
            throws Exception {
        Path file = root.resolve(name);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires JDK");

        Path root = Path.of(args[0]);
        Path src = root.resolve("src");
        Path mods = root.resolve("mods");

        write(src, "m.lib/module-info.java",
                "module m.lib { exports lib; }");
        write(src, "m.lib/lib/Greeter.java",
                "package lib; public class Greeter {" +
                "public static String hello(){return \"module-hi\";} }");
        write(src, "m.app/module-info.java",
                "module m.app { requires m.lib; }");
        write(src, "m.app/app/Main.java",
                "package app; import lib.Greeter;" +
                "public class Main { public static void main(String[] a) {" +
                "System.out.println(Greeter.hello()); } }");

        var diagnostics = new DiagnosticCollector<JavaFileObject>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, null, StandardCharsets.UTF_8)) {
            List<String> options = List.of(
                    "--release", "17", "-proc:none",
                    "--module-source-path", src.toString(),
                    "-d", mods.toString(),
                    "-m", "m.lib,m.app");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, null);

            System.out.println("modulesCompiled=" +
                    Boolean.TRUE.equals(task.call()));
        }

        System.out.println("libModuleInfo=" +
                Files.exists(mods.resolve("m.lib/module-info.class")));
        System.out.println("appClass=" +
                Files.exists(mods.resolve("m.app/app/Main.class")));
    }
}
~~~

Run:

~~~sh
javac --release 17 ModuleTaskDemo.java
java ModuleTaskDemo work/modules
java --module-path work/modules/mods -m m.app/app.Main
~~~

**Stdout of the two `java` commands:**

~~~text
modulesCompiled=true
libModuleInfo=true
appClass=true
module-hi
~~~

Why does the example succeed?

1. `--module-source-path work/modules/src` maps `m.lib`, `m.app` to the two source directories.
2. `-m m.lib,m.app` tells the compiler to compile those modules. In **`getTask`**, the fifth parameter `classes` remains `null`, because `-m` is handled under `options`. Do not confuse `classes=List.of("m.lib")` with module selection.
3. `m.app` reads `m.lib` via `requires`, and package `lib` is exported by `m.lib`. The module source path is sufficient for `javac` to resolve between modules within the same compilation task.
4. Output is `work/modules/mods/m.lib/...` and `work/modules/mods/m.app/...`.
5. When running `java`, you still must provide **`--module-path` for the runtime**, separate from the compile task settings.

**Distinguishing `--module-source-path` and `--module-path`:** the former points to **module sources being compiled**; the latter points to **existing module dependencies** (directories/JARs containing named modules) when needed. They can appear together in a task that has both new source modules and compiled module dependencies.

## 7. Annotation processing: what code runs at compile time?

An annotation processor is a piece of Java code that executes **during compilation**, using the `javax.annotation.processing` and `javax.lang.model` APIs to inspect elements seen by the compiler and optionally generate source/resource files via `Filer`.

This differs from **runtime reflection**: the processor runs before class output is used, having access to the model of source declarations across rounds. A processor can generate `GeneratedFoo.java`, and then the compiler compiles the new file along with the rest in subsequent rounds.

Distinguish the components:

| Component | Role |
| --- | --- |
| `AbstractProcessor` / `Processor` | Plugin running at compile time |
| `@SupportedAnnotationTypes` | Set of annotation names the processor accepts; `"*"` is a wildcard |
| `@SupportedSourceVersion(SourceVersion.RELEASE_17)` | Processor declares support for the Java 17 source model |
| `RoundEnvironment` | Elements and state of a processing round |
| `Filer.createSourceFile(...)` | Creates new Java source; usually triggers a subsequent processing round |
| `Messager` | Emits compiler diagnostics from the processor |
| `-processor` | List of processor classes invoked **explicitly** |
| `-processorpath` | Where the compiler **looks for processor code and its dependencies** on the classpath |
| `--processor-module-path` | Where to look for **modular processors** on the module path |
| `-proc:none` | Disables annotation processing |
| `-proc:only` | Runs processing but **does not compile sources into `.class` files** afterward |
| `-s` | Directory containing generated `.java` files |
| `-d` | Directory containing compiled `.class` files |

**Separate the three paths:** `-classpath` for **application compile dependencies**; `-processorpath` for **processor code running at compile time**; `-s` is the Java source output from the processor. They can be completely different. If a processor uses its own dependency, that dependency must be on the processor path, not only on the application's class path.

For named-module processors, use `--processor-module-path` according to packaging/module declaration requirements. Do not simultaneously set conflicting processor path and processor module path. If you want to select processors without relying on auto-discovery, `-processor tooling.GenerateProcessor` or `task.setProcessors(...)` are two explicit selection mechanisms, with lifecycles and class loading that need to be managed.

### Security concerns of annotation processing

**A processor is executable code, not passive annotation data.** When enabled, a processor can execute code during compilation with the privileges of the process/host. Therefore:

- Do not automatically run processors from an untrusted dependency.
- In services receiving external source, proactively choose `-proc:none` by default when code generation is not needed.
- If processing is needed, pin processor and dependency versions, set the processor path explicitly, and run in a sandboxed environment/restricted-privilege process when code is untrusted.
- Do not treat `DiagnosticCollector` as a sandbox. It only receives diagnostics; it does not limit CPU, RAM, I/O, network, or processor behavior.

**Do not rely on default discovery as a stable contract across all JDKs.** `javac` versions can differ in whether annotation processing is enabled by default; explicitly configure `-proc:none` or `-processor` when reproducible behavior is needed.

## 8. Example 3 — a processor that generates Java source during compilation

This example intentionally makes a user class depend on `GeneratedMsg`, which does not exist yet:

~~~java
package client;
public class UseGenerated {
    public static void main(String[] args) {
        System.out.println("message=" + GeneratedMsg.message());
    }
}
~~~

This snippet is **only the source content that the demo program will write to a file itself**; compiling it alone will fail if `GeneratedMsg` has not been created yet. The program below performs three exact steps:

1. Compile the processor with `-proc:none` to avoid processor discovery while **building the processor itself**.
2. Compile `UseGenerated.java` **without the processor** to show that compilation fails.
3. Compile with `-processorpath`, `-processor`, and `-s` so the processor generates `client.GeneratedMsg`, and then the compiler automatically compiles the generated source into a class.

Save all of **`ProcessorTaskDemo.java`**:

~~~java
import javax.tools.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.io.*;

public class ProcessorTaskDemo {
    static Path write(Path base, String name, String source)
            throws IOException {
        Path file = base.resolve(name);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
        return file;
    }

    static boolean compile(
            JavaCompiler compiler, Path source, List<String> options)
            throws IOException {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, null, StandardCharsets.UTF_8)) {
            var units = manager.getJavaFileObjectsFromPaths(
                    List.of(source));
            var task = compiler.getTask(
                    new StringWriter(), manager, diagnostics,
                    options, null, units);
            return Boolean.TRUE.equals(task.call());
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires JDK");

        Path root = Path.of(args[0]);

        Path processor = write(
            root, "src/tooling/GenerateProcessor.java", """
                package tooling;
                import javax.annotation.processing.*;
                import javax.lang.model.*;
                import javax.lang.model.element.*;
                import javax.tools.*;
                import java.io.*;
                import java.util.*;

                @SupportedAnnotationTypes("*")
                @SupportedSourceVersion(SourceVersion.RELEASE_17)
                public final class GenerateProcessor
                        extends AbstractProcessor {
                    private boolean written;

                    @Override public boolean process(
                            Set<? extends TypeElement> annotations,
                            RoundEnvironment round) {
                        if (written || round.processingOver())
                            return false;

                        written = true;
                        try (Writer out = processingEnv.getFiler()
                                .createSourceFile("client.GeneratedMsg")
                                .openWriter()) {
                            out.write(
                                "package client; public class GeneratedMsg {" +
                                "public static String message() {" +
                                "return \\"generated\\"; } }");
                        } catch (IOException ex) {
                            throw new UncheckedIOException(ex);
                        }
                        return false;
                    }
                }
                """);

        Path user = write(
            root, "src/client/UseGenerated.java", """
                package client;
                public class UseGenerated {
                    public static void main(String[] args) {
                        System.out.println(
                            "message=" + GeneratedMsg.message());
                    }
                }
                """);

        Path procClasses = root.resolve("processors");
        Path classes = root.resolve("classes");
        Path generated = root.resolve("generated");

        boolean procReady = compile(compiler, processor,
                List.of("--release", "17", "-proc:none",
                        "-d", procClasses.toString()));
        System.out.println("processorCompiled=" + procReady);

        boolean disabled = compile(compiler, user,
                List.of("--release", "17", "-proc:none",
                        "-d", root.resolve("noProc").toString()));
        System.out.println("withoutProcessor=" + disabled);

        boolean enabled = compile(compiler, user,
                List.of("--release", "17",
                        "-processorpath", procClasses.toString(),
                        "-processor", "tooling.GenerateProcessor",
                        "-s", generated.toString(),
                        "-d", classes.toString()));
        System.out.println("withProcessor=" + enabled);

        System.out.println("generatedSource=" +
                Files.exists(generated.resolve(
                        "client/GeneratedMsg.java")));
        System.out.println("generatedClass=" +
                Files.exists(classes.resolve(
                        "client/GeneratedMsg.class")));
    }
}
~~~

Compile and run with JDK 17+:

~~~sh
javac --release 17 ProcessorTaskDemo.java
java ProcessorTaskDemo work/processing
java -cp work/processing/classes client.UseGenerated
~~~

**Stdout of the two `java` commands:**

~~~text
processorCompiled=true
withoutProcessor=false
withProcessor=true
generatedSource=true
generatedClass=true
message=generated
~~~

### Why is this real annotation processing?

- The processor is compiled by the compiler into `work/processing/processors/tooling/GenerateProcessor.class`.
- In the second compile task, `-proc:none` disables processing. The source `UseGenerated` references `GeneratedMsg`, which does not exist yet, so the compiler reports an error.
- In the third task, `-processorpath work/processing/processors` brings the processor code into the compiler environment, and `-processor tooling.GenerateProcessor` requests running it **explicitly**.
- The processor implements `process(...)`, calls `Filer.createSourceFile("client.GeneratedMsg")`, creating the file `work/processing/generated/client/GeneratedMsg.java`.
- The compiler runs the necessary processing rounds, then compiles `UseGenerated` and the generated `GeneratedMsg` into `work/processing/classes`. Compiling the generated class is part of the compile task; there is no need to invoke `javac` again for the generated file.
- The command `java -cp ... client.UseGenerated` is **runtime execution after compilation**, not annotation processing. It prints `message=generated`.

**Why is the `written` variable needed?** A processor can be called across multiple rounds. If it always creates the same file in every round, `Filer` will report an error due to a duplicate file. The example uses `written` to generate only once in the processor's lifecycle.

**Why `return false`?** It allows other processors to continue seeing the corresponding annotations. `return true` means the processor claims the annotations it handles; it does not mean "the compile task succeeded"—the compile result is in `CompilationTask.call()`.

**Regarding `@SupportedAnnotationTypes("*")`:** the wildcard allows the demo to run without defining a custom annotation, but production processors should declare specific annotations to avoid unexpected execution and coordinate properly with other processors.

## 9. `-proc:only`, `-proc:none`, and processor selection mechanisms

Three modes to remember:

| Configuration | Compile application classes? | Run annotation processors? | Scenario |
| --- | --- | --- | --- |
| `-proc:none` | Yes | No | Normal compilation, controlling processor risks |
| `-proc:only` + configured processor | Does not perform class compilation phase after processing | Yes | Only generate source/metadata or validate annotations |
| `-processor X` (and processor path) | Yes, if `-proc:only` is not set | Yes, invokes X | Code generation in a build |
| No processing options specified | Depends on compiler version and configuration | May not auto-discover in newer JDKs | Should not rely on defaults |

For JDK 17, the syntax is clearly documented for `-proc:none` and `-proc:only`. Do not attach the `-proc:full` flag to examples required to run on Java 17 without verifying support on the **specific compiler**; for the task here, specifying `-processor` is sufficient for processing to run alongside compilation.

### How does `task.setProcessors(...)` differ from `-processor`?

`CompilationTask` also has:

~~~java
task.setProcessors(
    java.util.List.of(new MyProcessor())
);
~~~

This is a **snippet**, assuming a class `MyProcessor` implementing `javax.annotation.processing.Processor` already exists. This API provides **processor instances directly**, instead of letting the compiler discover them via class/module path. It is suitable for applications that already manage the lifecycle/constructor/dependencies of processors, but it does not mean processors are sandboxed or allowed to execute anything by default.

Do not mix `setProcessors(...)` with conflicting `-processor` configurations. Choose **one explicit control method**: explicit instances or explicit processor names + processor path.

### Processor module path

If a processor is packaged as a **named module**, use `--processor-module-path` along with module provider metadata (e.g., `provides javax.annotation.processing.Processor with ...`). It differs from the `--module-path` of the application you are compiling. The processor needs to be loaded into the **compiler host** environment, whereas the application's module path is used to resolve the module graph of the **source being compiled**.

Using `--module-path` for application dependencies **does not automatically grant** processor discovery like `--processor-module-path`. Separate the paths to avoid unexpected compile-time code execution.

## 10. Diagnostics: reporting output reliably

`DiagnosticCollector<JavaFileObject>` stores each `Diagnostic` with the fields:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`.
- `getSource()`: the corresponding `JavaFileObject`, which can be `null` if the diagnostic is not attached to a file.
- `getLineNumber()`, `getColumnNumber()`, `getStartPosition()`, `getEndPosition()`: positions when provided by the compiler; may be `Diagnostic.NOPOS`.
- `getCode()`: diagnostic code provided by the compiler; useful for grouping, though not a complete public contract across different compilers.
- `getMessage(Locale)`: locale-specific message; avoid using **the compiler's English string** as the sole logic key.

**Snippet for handling diagnostics of a task** (assuming `diagnostics` already exists):

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
        JavaFileObject file = diagnostic.getSource();
        String at = file == null
                ? "<unknown>" : file.getName();

        System.out.println(at + ":" + diagnostic.getLineNumber()
                + " [" + diagnostic.getCode() + "] "
                + diagnostic.getMessage(java.util.Locale.ROOT));
    }
}
~~~

This is not a standalone program; it requires a `DiagnosticCollector<JavaFileObject> diagnostics` variable created for a compilation task. When outputting to an API response, you should escape and limit the number of diagnostics/total bytes to prevent spam and avoid leaking internal system paths.

**`Boolean.FALSE` differs from an exception**: syntax/type errors in source usually make the task return false and produce ERROR diagnostics. Invalid options can cause `getTask(...)` to throw `IllegalArgumentException`; errors in user-supplied processors/file managers may be wrapped in a `RuntimeException`. Do not design code that only catches `false` and ignores all exceptions.

## 11. Common errors when configuring a compile task

| Symptom | Common cause | How to investigate/fix |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime image does not contain the compiler implementation | Use a JDK with `jdk.compiler`; check `java --list-modules`/runtime image |
| `package ... does not exist` | Missing classpath or module graph | Check `-classpath`/`--module-path` and named module `requires`/`exports` |
| Library compiles successfully but app compilation fails | Library output is not on the app task's classpath | Add the library's output dir/JAR to `-classpath` |
| `class file has wrong version` at runtime | Running on a JVM older than the target bytecode | Compile with the appropriate `--release` and check the runtime JDK |
| Compiles on a newer JDK but JDK 17 runtime lacks a method | Used only `-source/-target` and accidentally referenced a newer API | Use `--release 17` |
| Compiler rejects `--release` with `-source/-target` | Overlapping release selection methods | Choose only one way, preferring `--release` |
| `module not found` | Missing `--module-path` or module source path | Verify module name, `module-info`, source layout |
| `module-info.java` appears in classpath build but API doesn't see it | Mixing modular and classpath compilation modes | Explicitly choose module mode and place files in proper module source layout |
| Processor does not run | `-proc:none`, wrong processor path, unspecified, or discovery changed | Use `-processor` or `setProcessors`; set path explicitly |
| `Annotation processor ... not found` | Processor not compiled yet or class path/processor path is incorrect | Build processor first, check class name and dependencies |
| `FilerException: Attempt to recreate a file` | Processor regenerates the same source across multiple rounds | Use one-shot state, check `processingOver()` |
| Generated source exists but class is missing | `-proc:only`, different output path, compile task failed | Check `-proc`, `-d`, diagnostics, generated classes |
| Processor generates classes or resources in the wrong place | Confused `-s` and `-d`/file manager locations | `-s` for source, `-d` for classes |
| New Java source compiled successfully but old class still runs | Old class loader already defined the same binary name | Use a new loader, versioned class name, or appropriate reload mechanism |
| Build service is slow/unstable | Too many tasks/file managers, processor code has side effects, unbounded input | Cache appropriately, control resources, external timeout/sandbox |

### Paths on Windows and Linux/macOS

`-classpath` accepts **a single path string** after the option. If there are multiple entries, join them with `File.pathSeparator` (Windows is usually `;`, Linux/macOS is usually `:`), instead of hardcoding the OS-specific separator.

Snippet:

~~~java
String deps = java.util.List.of(
        java.nio.file.Path.of("build/libs/core.jar"),
        java.nio.file.Path.of("build/classes"))
    .stream()
    .map(java.nio.file.Path::toString)
    .collect(java.util.stream.Collectors.joining(
            java.io.File.pathSeparator));

List<String> options = List.of(
    "--release", "17",
    "-classpath", deps,
    "-proc:none",
    "-d", "build/output");
~~~

This snippet is not a standalone program, but `List<String> options` has the exact format to pass into `getTask`. Similarly, `--module-path` and `-processorpath` accept path lists separated according to platform rules.

### In-memory sources and output

Writing `.java` sources to disk is not mandatory. `SimpleJavaFileObject` can wrap a `String` and provide `getCharContent(...)`; `ForwardingJavaFileManager` can intercept output class bytes into memory. When using that technique, you still must handle **classpath/modulepath**, how class bytes are loaded, security, and versioning. `CompilationTask` does not solve those boundaries on its own.

Minimal `SimpleJavaFileObject` example (**snippet**, not standalone):

~~~java
class SourceFromString extends SimpleJavaFileObject {
    private final String source;

    SourceFromString(String binaryName, String source) {
        super(java.net.URI.create(
                "string:///" + binaryName.replace('.', '/')
                        + JavaFileObject.Kind.SOURCE.extension),
              JavaFileObject.Kind.SOURCE);
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
~~~

When using it, add `import javax.tools.*;`, create a `SourceFromString("demo.Hello", source)`, and pass it in `compilationUnits`; avoid accepting uncontrolled input source and running it directly in the host process.

## 12. Reliability and security for on-demand compilation

1. **Classify sources:** internal generated code differs from untrusted user source. The Java compiler API is not a sandboxing mechanism.
2. **Limit resources:** set limits on file sizes, number of source units, number of diagnostics, and CPU/time/memory/disk at the process/sandbox level. `CompilationTask.call()` is a blocking call; the API has no built-in timeout.
3. **Do not automatically run compiled bytecode:** The compiler only validates that classes are valid per Java/JVM rules; **it does not validate business safety**. A separate `ClassLoader` does not provide a security sandbox on its own.
4. **Do not run unknown annotation processors:** `-proc:none` by default in pipelines that do not need processors; use an explicit allowlist and processor path when needed.
5. **Isolate outputs between builds:** do not overwrite class output of a previous build while it is running to avoid stale artifacts/races.
6. **Identify builds:** store source hash, compiler version, release target, options, dependency versions, and processor versions so results are reproducible.
7. **Manage the file manager:** close `StandardJavaFileManager` with try-with-resources; if caching/reusing across multiple sequential tasks, ensure no simultaneous mutation and close when done.
8. **Handle diagnostics and exceptions:** `call() == false` does not mean every error is Java syntax; also log diagnostics and `RuntimeException` causes, distinguishing I/O, module access, and processor failures.
9. **Separate compile and run:** run in a process/container with an independent policy; bytecode may reference libraries/platforms valid at compile time but missing at runtime.
10. **Do not rely on default annotation discovery:** it can change across JDKs/flags; explicit options help avoid surprises.

## 13. Self-check exercises

**Question 1.** To compile `app.App` which uses `lib.Helper` already compiled into `libOut`, what is needed in the new task?

**Answer:** Add `-classpath libOut` (or configure `StandardLocation.CLASS_PATH`) so the compiler sees `Helper.class`. The output directory of a previous task is not automatically added to the class path.

**Question 2.** In `getTask(out,fm,diag,options,classes,units)`, is the `classes` parameter where you put `List.of("app.App")` to run the class immediately after building?

**Answer:** No. `classes` is for class names needing annotation processing; `units` is the source to compile. Running the class is a separate step after compilation.

**Question 3.** What does `--release 17` do that `-target 17` alone does not guarantee?

**Answer:** It selects the language level, class-file version 61, and restricts the platform API to release 17. `-target` alone mainly selects the bytecode version.

**Question 4.** When do you use `--module-source-path` and `--module-path`?

**Answer:** `--module-source-path` locates **module source roots** to be compiled; `--module-path` locates existing **named module dependencies** for resolution. Both can be used when appropriate.

**Question 5.** How does `-processorpath` differ from `-classpath`?

**Answer:** The processor path finds and loads compiler plugins that execute at compile time; the class path is for dependencies of the application source. Separate them to manage dependencies and execution privileges.

**Question 6.** If `-proc:none` is used with source `UseGenerated` depending on a missing `GeneratedMsg`, will the task automatically generate `GeneratedMsg`?

**Answer:** No. `-proc:none` blocks processors; the compiler fails if it cannot find that source/bytecode class via other paths.

**Question 7.** Does `-proc:only` produce application `.class` files like a normal compile pass?

**Answer:** No. It only performs annotation processing and source/resource generation, without compiling application classes after processing.

**Question 8.** `task.call()==false`; how do you know if the error is in the source file, classpath, or processing?

**Answer:** Use `DiagnosticCollector`, inspect `Kind.ERROR`, code/source/line/message. Also check options/locations and processor logs; do not infer from the boolean alone.

**Question 9.** A JDK 21 application compiles using `--release 17`; what is the class bytecode major version?

**Answer:** 61. However, third-party APIs and runtime dependencies must be checked separately, because `--release` does not control every external JAR.

**Question 10.** After compiling version B of class `demo.Plugin`, can you ask the same class loader that loaded version A to automatically replace the definition by calling `CompilationTask` again?

**Answer:** No. The compiler produces bytes; class identity/definition is managed by the loader/JVM. Use a new class loader or appropriate instrumentation/redefinition to update at runtime.

## 14. Authoritative Java 17 sources

- `JavaCompiler`, `getTask`, `CompilationTask`, `DiagnosticCollector`, and file manager examples: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- `ToolProvider.getSystemJavaCompiler()` and the requirement for `jdk.compiler` to be present: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- `StandardJavaFileManager` and `getJavaFileObjectsFromPaths`/`setLocationFromPaths`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- `StandardLocation`, the standard file-manager locations: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardLocation.html
- `JavaCompiler.CompilationTask` and `setProcessors`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- `javax.annotation.processing.Processor`, `AbstractProcessor`, `RoundEnvironment`, `Filer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- JDK `javac` options (`--release`, `-classpath`, `--module-source-path`, `--module-path`, `-processorpath`, `-proc:none/only`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- `Diagnostic`, error codes and positions: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html

**Core summary:** `CompilationTask` is an **explicitly configured** compilation job. Class path resolves non-modular dependencies; module path and module source path resolve named modules; `--release` constrains all of Java language/API/bytecode target; annotation processors are code **that runs at compile time**, and must be controlled via `-proc`, processor path, and processor selection. Reading `DiagnosticCollector`, controlling output locations, and separating **compile** from **load/run** keep a dynamic Java compilation system correct and maintainable.