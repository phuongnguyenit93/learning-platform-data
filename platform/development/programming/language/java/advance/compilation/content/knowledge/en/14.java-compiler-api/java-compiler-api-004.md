# Compiling Java Files Using StandardJavaFileManager

When using the `javac` command, the tool itself locates source files, reads their contents, looks up libraries, and writes `.class` files. For applications that need to invoke the compiler directly from inside Java—such as IDEs, source checkers, grading systems, code generators, or build tools—Java SE provides the **Java Compiler API** in module `java.compiler`. The key component for working with **real files on disk** is `javax.tools.StandardJavaFileManager`.

`StandardJavaFileManager` converts source `Path`/`File` inputs into `JavaFileObject` instances, manages locations for finding classes/sources and writing outputs. It works alongside `JavaCompiler`, `CompilationTask`, and `DiagnosticCollector`, enabling a Java program to compile files without spawning an external `javac` process.

This lesson uses **Java 17+**, prioritizes Java SE-supported APIs, provides complete runnable code, clear expected outputs, and notes on encoding, classpath, resource management, and common errors.

## 1. Component Diagram

```text
Path to .java source
        |
        v
StandardJavaFileManager
  - getJavaFileObjectsFromPaths(...)
  - setLocationFromPaths(CLASS_OUTPUT, ...)
  - setLocationFromPaths(CLASS_PATH, ...)
        |
        v
Iterable<? extends JavaFileObject>
        |
        v
JavaCompiler.getTask(...)
        |
        +----> CompilationTask.call() ------> true/false
        |
        +----> DiagnosticCollector --------> errors/warnings/positions
        |
        +----> StandardJavaFileManager ----> write .class
```

Roles that should not be conflated:

| Component | Responsibility |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Obtains the system Java compiler if present in the runtime |
| `JavaCompiler` | Provides methods to invoke the compiler programmatically |
| `StandardJavaFileManager` | Manages source/class files on the filesystem, JARs, and standard locations |
| `JavaFileObject` | Represents a file used by the compiler, such as a source or class file |
| `StandardLocation` | Standardized locations such as `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH` |
| `JavaCompiler.CompilationTask` | A compilation task configured with sources and options; `call()` executes it |
| `DiagnosticCollector<JavaFileObject>` | Receives diagnostics as objects rather than parsing stderr strings |

The word **standard** here refers to the file manager per the Java Compiler API; it does not imply every compiler implementation must handle every unusual path identically. The standard file manager provides a convenient way to work with ordinary files and paths.

## 2. Why Use a File Manager?

Suppose you want to compile `src/demo/Hello.java` into `out/demo/Hello.class`. One way is launching `javac -d out src/demo/Hello.java` via `ProcessBuilder`; however, if your software is already written in Java and needs control over diagnostics or input/output, the Java Compiler API is a better fit.

The file manager handles responsibilities such as:

- Wrapping a `.java` file into a `JavaFileObject` so the compiler can read it.
- Managing **source encoding** when converting bytes to characters.
- Setting **class output**, **classpath**, **source path**, and standard locations.
- Accessing class files or JARs the compiler needs for type resolution.
- Managing internal resources such as JAR handles; supporting `flush()`/`close()`.
- Allowing the compiler to write `.class` files at the proper package path rather than having the application construct every filename manually.

`JavaFileObject` is not source content already parsed. It is a **file abstraction object**. The compiler remains responsible for lexing, parsing, type checking, and code generation.

## 3. Complete Java 17+ Example: Create Files, Compile, and Verify Output

Save the file below as **`FileManagerCompileDemo.java`** in any working directory. The program creates `fm-demo/src/demo/Hello.java`, invokes the compiler, checks the class file, and prints verifiable results.

```java
import java.io.IOException;
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class FileManagerCompileDemo {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("fm-demo/src/demo/Hello.java");
        Path classes = Path.of("fm-demo/classes");

        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        String code = """
                package demo;

                public class Hello {
                    public static void main(String[] args) {
                        System.out.println("Xin chào, Java!");
                    }
                }
                """;

        Files.writeString(source, code, StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Cần chạy bằng JDK có system Java compiler");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT,
                    List.of(classes));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(source));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, units);

            success = Boolean.TRUE.equals(task.call());
        }

        long errors = diagnostics.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();

        System.out.println("success=" + success);
        System.out.println("classExists=" + Files.isRegularFile(
                classes.resolve("demo/Hello.class")));
        System.out.println("errors=" + errors);
    }
}
```

### Compiling and running the compiler driver program

In the directory containing `FileManagerCompileDemo.java`, using JDK 17+:

```bash
javac -encoding UTF-8 FileManagerCompileDemo.java
java FileManagerCompileDemo
```

Exact stdout when the environment has a compiler and file operations succeed:

```text
success=true
classExists=true
errors=0
```

The program also creates these files:

```text
fm-demo/
├── src/demo/Hello.java
└── classes/demo/Hello.class
```

Test the class file with the launcher:

```bash
java -cp fm-demo/classes demo.Hello
```

Exact stdout:

```text
Xin chào, Java!
```

The two `java` invocations are distinct: the first runs **the compiler driver program** `FileManagerCompileDemo`; the second runs **the newly generated class** `demo.Hello`.

If running the demo multiple times in the same directory, `Files.writeString` overwrites the generated source and the compiler may overwrite the class. When testing the completeness of a compilation run, start with a clean output so old `.class` files are not confused with newly generated ones. Do not delete other people's data folders when cleaning output.

## 4. Step-by-Step Analysis of the Example

**Step 1 — create real source.** `Path.of("fm-demo/src/demo/Hello.java")` locates the file relative to the current working directory. `Files.createDirectories(...)` creates the package directory and output directory. `Files.writeString(..., UTF_8)` writes the exact byte encoding.

**Step 2 — obtain the compiler.** `ToolProvider.getSystemJavaCompiler()` is the API entry point. If the runtime environment has no system compiler, it may return `null`; the program handles that explicitly. Do not infer from the class name `ToolProvider` that every minimal JRE includes `javac`.

**Step 3 — obtain the file manager.** `compiler.getStandardFileManager(diagnostics, Locale.ROOT, UTF_8)` configures the listener for non-fatal diagnostics, display locale, and charset for decoding files. The charset here matches the encoding used when writing the source.

**Step 4 — set output.** `setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(classes))` requests writing class files into an **existing output directory**. Package `demo` places the class under `demo/Hello.class`.

**Step 5 — pass source into the task.** `getJavaFileObjectsFromPaths(List.of(source))` converts the collection of `Path` values into `Iterable<? extends JavaFileObject>`. The parameter expects **files**, not a source root directory. The API provides an overload taking `Collection<? extends Path>`, preferred since Java 13.

**Step 6 — configure compilation.** `getTask(...)` accepts the file manager, diagnostic listener, compiler options, list of class names for annotation processing (passing `null` in the example), and compilation units. Options `--release 17` keep target Java 17; `-proc:none` disables annotation processing for the demo.

**Step 7 — execute.** `task.call()` is where compilation actually runs. Merely calling `getTask(...)` without calling `call()` does not produce class files.

**Step 8 — read the result.** `Boolean.TRUE.equals(task.call())` provides a clear boolean. `DiagnosticCollector` provides the structured list of diagnostics. `Files.isRegularFile(...)` checks the artifact; file existence alone does not prove the artifact was newly produced in the current run unless output was cleaned.

**Step 9 — close the file manager.** Try-with-resources calls `close()` even when errors occur. This releases file handles, especially when handling multiple JARs or running on Windows, where open file handles can block operations on artifacts.

## 5. JavaCompiler.getTask Signature Explained Parameter by Parameter

A common usage pattern:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        outWriter,
        fileManager,
        diagnosticListener,
        options,
        classes,
        compilationUnits);
```

This is a **signature illustration**, not a standalone program.

| Parameter | Meaning |
| --- | --- |
| `outWriter` | Writer for additional compiler output; `null` uses default output |
| `fileManager` | File manager for locating/writing files; `null` lets the compiler use the default |
| `diagnosticListener` | Receives diagnostics; `null` lets the compiler format messages in its default way |
| `options` | Compiler options such as `--release`, `-proc:none`; `null` means no additional options |
| `classes` | Class names for annotation processing in supported mode; usually `null` for source compilation |
| `compilationUnits` | `JavaFileObject` instances of kind SOURCE to compile |

Passing filenames into `classes` instead of `compilationUnits` misuses the parameter. `classes` is **not** a list of `.class` files to output and does not replace the input source set.

`getTask(...)` can throw `IllegalArgumentException` when an option is invalid or a compilation unit has a non-source kind. If a caller-supplied component hits an unrecoverable error, an exception may also be thrown. Do not assume all errors are reported as `CompilationTask.call() == false`.

A `CompilationTask` represents **a single compilation run**; do not reuse the same task object to call `call()` multiple times. Different tasks can be created with the compiler/file manager as needed, provided inputs, outputs, and lifecycles are managed clearly.

## 6. Choosing the Right getJavaFileObjects Method

`StandardJavaFileManager` provides several ways to create `JavaFileObject` instances:

| Method | When to use |
| --- | --- |
| `getJavaFileObjects(Path... paths)` | List of `Path` values passed as varargs |
| `getJavaFileObjectsFromPaths(Collection<? extends Path>)` | Already have a `Collection<Path>`; suitable for Java 17+ |
| `getJavaFileObjects(File... files)` | Already have `java.io.File` instances |
| `getJavaFileObjectsFromFiles(Iterable<? extends File>)` | Iterable of `File` instances |
| `getJavaFileObjects(String... names)` | Filenames/paths as strings |
| `getJavaFileObjectsFromStrings(Iterable<String>)` | Already have an iterable of path strings |

Equivalently intended example for `Hello.java`:

```java
Path path = Path.of("fm-demo/src/demo/Hello.java");

Iterable<? extends JavaFileObject> a =
        manager.getJavaFileObjects(path);

Iterable<? extends JavaFileObject> b =
        manager.getJavaFileObjectsFromPaths(List.of(path));
```

This is a **snippet within a scope having `manager`**, not a standalone Java file. Do not pass an entire directory in the source file list: the API may throw `IllegalArgumentException` when an input is a directory.

**Pitfall with the old overload:** the overload `getJavaFileObjectsFromPaths(Iterable<? extends Path>)` has been deprecated since Java 13. Use the overload accepting **`Collection`**, such as `List.of(path)`, or `getJavaFileObjects(path)`. Because `Path` itself implements `Iterable<Path>`, code accidentally calling the `Iterable` overload with a single `Path` could be interpreted as the path's segments rather than one source file.

If you need all `.java` files under a source root, the caller finds the matching files itself via `Files.walk(...)` (while closing the Stream), then passes the list of **actual file** `Path` instances. The file manager does not infer that a directory `Path` means "recursively compile every Java file".

## 7. StandardLocation: Classpath Differs from Output

Locations have distinct effects on how the compiler finds and writes files:

| Location | Purpose |
| --- | --- |
| `StandardLocation.CLASS_OUTPUT` | Directory where `.class` files are written |
| `StandardLocation.SOURCE_OUTPUT` | Directory where generated sources are written, typically by annotation processors |
| `StandardLocation.CLASS_PATH` | Roots/JARs used to search for classes on the classpath |
| `StandardLocation.SOURCE_PATH` | Roots used to search for additional sources |
| `StandardLocation.ANNOTATION_PROCESSOR_PATH` | Path to search for annotation processors on the processor classpath |
| `StandardLocation.MODULE_PATH` | Module path according to JPMS |
| `StandardLocation.SYSTEM_MODULES` | Platform/system modules defined by the toolchain |

These constants represent **different** locations. Setting `CLASS_OUTPUT` does not set `CLASS_PATH`; if the compiler needs to look up a dependency already built in another directory, an appropriate search path is needed.

With Java 17+:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/app-classes")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("build/lib-classes"),
                Path.of("lib/helper.jar")));
```

This is a **configuration snippet inside a program**, not a standalone command; output directories must exist beforehand and JARs must exist. `CLASS_PATH` entries are package roots or JARs, not specific class or package names.

`setLocationFromPaths(...)` **replaces** the previous search path of the selected location; it does not automatically append to a default classpath. If multiple entries are needed, pass the entire desired collection in one `Collection<Path>`.

For an output location, the API requires exactly **one** path, which must be an existing directory. Passing two output directories for `CLASS_OUTPUT`, or a path to a file rather than a directory, violates the contract.

Avoid configuring the same location twice via both `setLocationFromPaths(...)` and compiler options `-d` or `-classpath` without knowing the exact precedence. Choosing one consistent configuration method makes debugging and testing easier.

## 8. Compiling Multiple Files in One Task

If the program has:

```text
src/
  demo/
    Main.java
    Helper.java
```

then both files can be passed together:

```java
List<Path> sources = List.of(
        Path.of("src/demo/Main.java"),
        Path.of("src/demo/Helper.java"));

Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(sources);

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, units);

boolean success = Boolean.TRUE.equals(task.call());
```

This is a **snippet** using the already declared `compiler`, `manager`, `diagnostics` variables, not a standalone runnable file.

If `Main` requires `Helper`, listing both sources explicitly gives clear control over the input set. If only `Main.java` is passed and the compiler finds `Helper.java` via the source path, the compiler may perform **implicit source compilation** according to `javac` rules. Thus "only one `JavaFileObject` in compilationUnits" does not guarantee only one class is generated.

For reproducible builds, explicitly configure sources, sourcepath/classpath, output, and compiler options. Do not rely on class files left over from a previous run.

## 9. Compiling a Dependency Separately and Using CLASS_PATH for the Application

Suppose the library `demo.lib.Utility` has already been compiled into `build/lib-classes`; the application at `src/app/demo/app/Main.java` needs `Utility`. When creating the compilation task for the app:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/app-classes")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("build/lib-classes")));

Iterable<? extends JavaFileObject> appUnits =
        manager.getJavaFileObjectsFromPaths(List.of(
                Path.of("src/app/demo/app/Main.java")));

boolean ok = Boolean.TRUE.equals(
        compiler.getTask(
                null, manager, diagnostics,
                List.of("--release", "17", "-proc:none"),
                null, appUnits
        ).call());
```

This is a configuration snippet; output directories must be created before calling. Afterwards, runtime typically requires both locations:

- macOS/Linux: `java -cp "build/app-classes:build/lib-classes" demo.app.Main`.
- Windows: `java -cp "build/app-classes;build/lib-classes" demo.app.Main`.

**Compile-time classpath and runtime classpath are independent.** Compiler API success does not automatically make dependencies visible to the JVM launcher running the application.

Using `-cp` for simple applications is another way to configure the classpath, though code using a file manager should prefer one consistent method: set `StandardLocation.CLASS_PATH` or pass option `-classpath`; do not mix them and accidentally override the search path.

## 10. Charset: Why UTF-8 Must Be Configured Properly

There are two places involving encoding in the example:

```java
Files.writeString(source, code, StandardCharsets.UTF_8);

compiler.getStandardFileManager(
        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
```

The first statement writes the source file as UTF-8 bytes. The second tells the file manager to use UTF-8 to decode bytes back to characters when reading source. The two choices must match to avoid errors or corrupted Vietnamese text.

Since JDK 18 (JEP 400), UTF-8 is the default charset for most Java SE APIs; nevertheless, if the goal is consistent builds across JDKs and environments, specifying the charset explicitly remains clearer and more reliable, especially when inputs contain non-ASCII characters.

`Locale.ROOT` in `getStandardFileManager` affects how diagnostics emitted by the file manager are formatted; it is not an encoding. `UTF_8` is a `Charset` object, not a language name.

If a source file was written in UTF-16 while the file manager reads it as UTF-8, the source will not decode properly. Do not "fix" it by replacing every Unicode character with ASCII if the cause is a charset mismatch.

## 11. DiagnosticCollector: Reading Structured Errors

`DiagnosticCollector<JavaFileObject>` provides a list of diagnostics. You can categorize by `Diagnostic.Kind`, inspect source/line/column, and obtain messages for developers to read.

Processing example **inside a method that has `diagnostics`**:

```java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        String sourceName = d.getSource() == null
                ? "<unknown>"
                : d.getSource().getName();

        System.out.println(
                sourceName + " line=" + d.getLineNumber());
    }
}
```

`getLineNumber()` can return `Diagnostic.NOPOS` if the error is not associated with a specific line. `getSource()` can return `null`. `getMessage(Locale.ROOT)` is **implementation-dependent** descriptive text; do not parse it with a fixed regex to classify error kinds.

For example, if the source has `int count = "x";`, `task.call()` typically returns `false`, and the collector will contain a diagnostic of kind `ERROR`. To tally tool results, use kind/error count and build status; do not depend on the JDK's `"incompatible types"` string.

Having a diagnostic listener does not guarantee all compiler output appears as `Diagnostic` objects. Some messages that do not fit the diagnostic object model may go through the output writer. Thus a real tool must also manage writers/logs properly; however, **structured data** remains the primary path for editors or automation.

## 12. Example Testing a Compile Error via the API

Save `CompileFailureDemo.java`:

```java
import java.io.IOException;
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class CompileFailureDemo {
    public static void main(String[] args) throws IOException {
        Path src = Path.of("failure-demo/Bad.java");
        Path out = Path.of("failure-demo/classes");
        Files.createDirectories(src.getParent());
        Files.createDirectories(out);
        Files.writeString(
                src,
                "public class Bad { int count = \"wrong\"; }\n",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean ok;
        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {
            fm.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT,
                    List.of(out));
            Iterable<? extends JavaFileObject> sourceFiles =
                    fm.getJavaFileObjectsFromPaths(List.of(src));
            ok = Boolean.TRUE.equals(
                    compiler.getTask(
                            null, fm, diagnostics,
                            List.of("--release", "17", "-proc:none"),
                            null, sourceFiles
                    ).call());
        }

        boolean hasError = diagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

        System.out.println("success=" + ok);
        System.out.println("hasError=" + hasError);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CompileFailureDemo.java
java CompileFailureDemo
```

Expected stdout:

```text
success=false
hasError=true
```

The compiler driver program **compiles successfully**; inside it, the compiler is asked to compile an intentionally invalid source. Because diagnostics are collected instead of printed verbatim, the example can test against two stable booleans without depending on how `javac` formats errors in each version.

Do not confuse `java CompileFailureDemo` returning the driver program's exit code with the compilation result of `Bad.java`. In this example, the Java program does not call `System.exit(1)` when `ok == false`; if CI should fail, the driver program must decide its own exit code based on `ok`.

## 13. Resource Management: close, flush, and Reuse

`StandardJavaFileManager` extends `Closeable`, so you should use:

```java
try (StandardJavaFileManager fm =
             compiler.getStandardFileManager(
                     diagnostics, Locale.ROOT,
                     StandardCharsets.UTF_8)) {
    // Configure locations, create JavaFileObject instances, and compile.
}
```

Closing the file manager releases handles to files/JARs and internal resources. The `JavaCompiler` documentation also allows **reusing the same standard file manager for multiple sequential compilation tasks**, leveraging JAR/file metadata caching. However:

- Do not use **the same CompilationTask** to run multiple times.
- If reusing the same manager across tasks, re-verify `CLASS_OUTPUT`, `CLASS_PATH`, and `SOURCE_PATH` before each task to avoid leftover state.
- A file manager should not be shared concurrently across multiple threads/compilation tasks without an explicit thread-safety contract from the implementation.
- Do not reuse a `JavaFileObject` after the underlying files have been deleted/moved and assume it remains valid.
- In multi-user/multi-tenant builds, control where reads and writes occur; do not allow arbitrary input paths to overwrite critical files.

`flush()` flushes buffers per the file manager's contract when needed; `close()` ends the resource management lifecycle. Even though the standard file manager specifies defined behavior if accessed after close, a clean design closes it once and acquires a new manager when starting a new lifecycle.

## 14. Distinguishing Source Files, Output, Sourcepath, and Annotation Processors

Inside a compiler task, do not confuse these paths:

```text
src/app/demo/Main.java         --> explicit compilation unit
src/lib/...                    --> SOURCE_PATH when locating dependent sources
lib/dependency.jar             --> CLASS_PATH when locating dependent classes
generated-sources/...          --> SOURCE_OUTPUT for generated .java
build/classes/...              --> CLASS_OUTPUT for .class
processor jars                 --> ANNOTATION_PROCESSOR_PATH
```

If a Java file is read **implicitly** by the compiler via the source path, it can affect the set of generated classes; `javac` flags `-implicit:class`/`-implicit:none` have specific behavior regarding `.class` generation from implicit sources.

When annotation processing is enabled, processors can generate sources via `Filer`, and those files are processed by the compiler in subsequent rounds. `SOURCE_OUTPUT` typically corresponds to where generated files go; `CLASS_OUTPUT` is for class files. When focusing on basic `StandardJavaFileManager` usage, `-proc:none` keeps examples independent of any processor incidentally on the classpath.

Starting with JDK 23, annotation processing activation changed compared to some older JDK versions. If the application requires processors, explicitly configure processor path/module path, processors, and options according to the JDK; do not rely on default auto-discovery.

## 15. FileManager and JPMS: When Sources Belong to a Named Module

The examples above compile sources **without `module-info.java`** (classpath/unnamed module). For projects using JPMS, the file manager also supports locations such as:

- `StandardLocation.MODULE_PATH`: named modules/JARs on the module path.
- `StandardLocation.MODULE_SOURCE_PATH`: location of module sources.
- `StandardLocation.MODULE_CLASS_OUTPUT` (when supported by the compiler implementation in the corresponding contexts) and module-oriented locations published by `JavaFileManager`.
- `setLocationForModule(...)` in situations needing to bind a module name to a dedicated location.

Do not assume pure classpath options apply identically when `module-info.java` is present. Module readability, exports, and module output locations have their own rules.

When working with multiple modules, it may be simpler to let a build tool manage the module source path/graph or use compiler options `--module-source-path`, `--module-path`, `--module` instead of building a custom location mapping system. If specialized tooling is required, carefully read the contracts of `StandardJavaFileManager` and `JavaFileManager` on **the exact JDK**.

## 16. Common Errors and How to Fix Them

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime lacks a system compiler | Run with a JDK having the appropriate module/compiler |
| `IllegalArgumentException` when obtaining compilation units | Passed a directory or inappropriate file object kind | Supply concrete `.java` file paths |
| `IOException` when setting `CLASS_OUTPUT` | Output directory does not exist or is unusable | Call `Files.createDirectories(out)` and check permissions |
| Compilation succeeds but class is missing | Checking the wrong folder/package or misled by old class files | Read the actual `CLASS_OUTPUT`; check clean output |
| `package ... does not exist` | `CLASS_PATH`/`SOURCE_PATH` lacks the dependency | Configure classpath/sourcepath to the proper package root |
| `cannot find symbol` on dependent type | Source or class cannot be resolved | Check source file, type name, package, and classpath |
| `UnsupportedClassVersionError` at runtime | Runtime JVM is too old for the class file | Set `--release`/toolchain to the right target |
| Garbled Vietnamese strings or compiler reports invalid characters | Charset writing source differs from charset reading source | Use UTF-8 consistently on both ends |
| Warnings/errors not printed to console | `DiagnosticCollector` is capturing diagnostics | Read `getDiagnostics()` instead of checking stderr only |
| `getTask(...)` did not emit files | `CompilationTask.call()` not yet called | Execute the task and check the result |
| JAR file cannot be deleted on Windows | File manager still holds handles | Close the manager with try-with-resources |
| `class file for X not found` though X exists in another dependency | Classpath is missing a transitive dependency | Check complete classpath/task settings |
| Compile passes but launcher reports `NoClassDefFoundError` | Runtime classpath lacks classes | Specify all outputs/dependencies in `java -cp` |
| Different results across machines/CI | Different JDKs, classpaths, charsets, or stale output | Record options and JDK explicitly and build in clean output |

These error messages are illustrative and may vary by compiler and version. Rely on `Diagnostic.Kind`, file/line/column, and compilation status when automated analysis is needed, rather than locking logic to a fixed stderr phrase.

## 17. Design Mistakes When Building Compiler Tools

**Using SystemCompiler without handling null.** The application may run on a runtime that does not bundle a compiler. Clearly report that a JDK is needed or check the deployment image.

**Confusing write location with search location.** `CLASS_OUTPUT` does not replace `CLASS_PATH`. When compiling in multiple phases, put classes generated in an earlier phase onto the classpath of a later phase if the later phase depends on them.

**Passing a directory into getJavaFileObjectsFromPaths.** The API takes source file paths; it does not mean the compiler will recursively scan a directory.

**Not closing the file manager.** Easily accumulates open handles to JARs, causing issues on Windows or in long-running compilation services.

**Relying on compiler output text.** Messages can change with locale and formatting; use `DiagnosticCollector` and status when machine readability is required.

**Uncontrolled shared output across compilation runs.** Stale artifacts make file-existence checks unreliable. Each build run should have a managed output directory cleaned safely when appropriate.

**Ignoring security boundaries.** The Java Compiler API is not a sandbox for untrusted source. Compiled code might not execute immediately in the compiler, but annotation processors/plugins can run code during compilation; restrict processor paths, filesystem access, and isolation when processing user-supplied sources.

**Assuming CLASS_PATH automatically downloads Maven dependencies.** The file manager manages locations of existing files/JARs; downloading/resolving dependencies is the separate responsibility of a build tool or application.

## 18. Practical Workflow for Real Tools

1. Verify the **JDK** and compiler are available; choose source/bytecode version with `--release` if appropriate.
2. Select exact **source files** as `Path` values, and a dedicated **output directory**; create directories beforehand.
3. Choose encoding consistently; use `StandardCharsets.UTF_8`.
4. Obtain `JavaCompiler` and `DiagnosticCollector`.
5. Open `StandardJavaFileManager` via try-with-resources.
6. Configure `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH`, or module path if the task needs them; avoid conflicts with compiler options.
7. Convert source paths into `JavaFileObject` via `getJavaFileObjectsFromPaths(Collection)`.
8. Create a task via `getTask(...)`; pass appropriate compiler options.
9. Call `call()` exactly once on the task; capture the boolean build result.
10. Collect diagnostics and verify class files/artifacts in clean output.
11. Close the manager, keeping logs/compiler version for tracing failures.
12. If you need to **run** the compiled class, configure the launcher/class loader with a separate runtime classpath/module path and do not treat "compile pass" as full runtime proof.

## 19. Self-Check Exercises

**Exercise 1.** A program calls `getJavaFileObjectsFromPaths(List.of(Path.of("src")))`, where `src` is a directory. Does the compiler automatically compile all `.java` files underneath?

**Answer:** No. The API accepts file paths; a directory is not a valid compilation unit. List each source file explicitly.

**Exercise 2.** `CLASS_OUTPUT` is set to `build/classes`. If the source has `package demo; public class A {}`, where is the class file placed?

**Answer:** `build/classes/demo/A.class`.

**Exercise 3.** A file was written in UTF-8, yet the file manager is configured to read ISO-8859-1. What can happen?

**Answer:** Unicode characters can be decoded incorrectly and Java source/strings can become corrupted. Configure charsets consistently.

**Exercise 4.** You have a `CompilationTask`, yet no `.class` file appears. What should you check first?

**Answer:** Whether `task.call()` was called; then inspect status, diagnostics, and output location.

**Exercise 5.** Which overload should `List.of(sourcePath)` be passed to on Java 17+?

**Answer:** `getJavaFileObjectsFromPaths(Collection<? extends Path>)` or use `getJavaFileObjects(sourcePath)`; avoid the deprecated `Iterable` overload.

**Exercise 6.** One compilation run generates `build/lib-classes/demo/lib/Utility.class`, and the next run needs `Utility`. Is setting only the app's `CLASS_OUTPUT` enough?

**Answer:** No. The next run needs an appropriate `CLASS_PATH` or input/sourcepath resolving the dependency.

**Exercise 7.** Why can the `CompileFailureDemo` demo print `success=false` while the `java CompileFailureDemo` command itself exits normally?

**Answer:** The boolean is the result of **in-program compilation**; the application did not call `System.exit` with a failure code. The two result levels are separate.

**Exercise 8.** Which is better for automatically tallying errors: counting stderr lines containing `error:` or counting `Diagnostic.Kind.ERROR`?

**Answer:** Use the Diagnostic API and the task result; stderr text has no stable schema.

## 20. Summary and References

`StandardJavaFileManager` bridges **real source files** and the **Java Compiler API**. The developer provides `Path`/`File` instances, the file manager represents compilation units and manages search/write locations, `JavaCompiler` creates tasks, `call()` executes them, and `DiagnosticCollector` supplies structured error information.

Five points to remember: **(1)** pass a list of source files, not a directory as a compilation unit; **(2)** set `CLASS_OUTPUT` to an existing directory and distinguish it from `CLASS_PATH`; **(3)** specify charset explicitly; **(4)** read status and diagnostics instead of guessing from stderr; **(5)** close the file manager cleanly per its lifecycle. With these principles, Java compilation tools are easier to test, diagnose, and operate.

Official documentation:

- [Java SE 21 StandardJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html) — overloads handling `Path`/`File`, setLocationFromPaths, class/source locations.
- [Java SE 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html) — `getTask`, `getStandardFileManager`, diagnostic listeners, and manager reuse.
- [Java SE 21 StandardLocation](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardLocation.html) — role of standard locations.
- [Java SE 21 DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) — collecting diagnostics.
- [JDK 21 javac manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — compiler options such as `--release` and `-proc:none`.