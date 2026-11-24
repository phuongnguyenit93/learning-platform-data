# Preparing Source Units with StandardJavaFileManager

## 1. Role in the Runtime Java Compilation Pipeline

The Java Compiler API (`javax.tools`, located in module `java.compiler`) lets a host compile Java source without spawning an external `javac` process. A key step is converting `.java` file paths into `JavaFileObject` instances to pass into `JavaCompiler.CompilationTask`. `StandardJavaFileManager` provides these operations according to filesystem conventions and compiler configuration.

Typical workflow:

```text
ToolProvider.getSystemJavaCompiler()
      |
      v
JavaCompiler.getStandardFileManager(...)
      |
      +--> set CLASS_PATH / CLASS_OUTPUT (when needed)
      |
      +--> getJavaFileObjectsFromPaths(...)
      |             |
      |             v
      |       Iterable<? extends JavaFileObject>
      |
      v
compiler.getTask(..., fileManager, ..., compilationUnits)
      |
      v
task.call() --> inspect diagnostics and .class output
```

In a plugin system, the host can accept source files from an allowed directory, convert them into compilation units, and then produce classes for a new plugin. **Preparing compilation units** is distinct from compiling, loading classes, instantiating providers, or executing plugin code; those are separate steps requiring control.

## 2. Objects You Need to Understand

| Object | Role |
|---|---|
| `JavaCompiler` | Compiler obtained via `ToolProvider.getSystemJavaCompiler()`; creates compilation tasks |
| `StandardJavaFileManager` | Standard adapter between the compiler and filesystem; creates `JavaFileObject` and manages file locations |
| `JavaFileObject` | Abstraction of a source/class file; `Kind.SOURCE` represents a source unit |
| `Iterable<? extends JavaFileObject>` | Collection of compilation units passed into `getTask` |
| `StandardLocation.CLASS_PATH` | Where the compiler searches for dependencies on the class path |
| `StandardLocation.CLASS_OUTPUT` | Where `.class` files are written when the compiler succeeds |
| `DiagnosticCollector<JavaFileObject>` | Collects error/warning details with source, line, and column when available |

`StandardJavaFileManager` extends `JavaFileManager` and `Closeable`: it must be closed when no longer in use. Do not confuse a file manager with a class loader: the file manager helps the compiler locate/read/write files; loading and running `.class` files after compilation must be designed separately.

## 3. Obtaining StandardJavaFileManager

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system Java compiler available");
}

DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
try (StandardJavaFileManager files = compiler.getStandardFileManager(
        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    // Configure locations, prepare JavaFileObjects, call getTask.
}
```

This is an **illustrative code snippet**; it needs imports for `javax.tools.*`, `java.util.Locale`, and `java.nio.charset.StandardCharsets`, placed inside a method with exception handling. `getSystemJavaCompiler()` is normally available when running on a JDK with module `jdk.compiler`; in a minimal runtime image without a compiler, it can return `null`. `java.compiler` only defines the APIs; it does not guarantee a compiler provider is always present.

The three parameters of `getStandardFileManager` are the diagnostic listener, locale, and charset, respectively. When compiling Vietnamese source or files containing Unicode literals, specify an explicit charset so source reading is consistent across machines. `Locale.ROOT` mainly affects how diagnostic messages are formatted, without changing program semantics.

## 4. Converting Source Files into JavaFileObject

Key methods on `StandardJavaFileManager`:

```java
Iterable<? extends JavaFileObject> units =
    files.getJavaFileObjectsFromPaths(List.of(
        Path.of("src/demo/Hello.java"),
        Path.of("src/demo/Helper.java")
    ));
```

These `.java` files must actually exist and belong to a scope permitted by the host. `getJavaFileObjectsFromPaths` converts each `Path` into a Java file object; it does not automatically discover every source across an entire directory according to a plugin convention. If you want to compile an entire source tree, the host must walk the directory itself, filter `.java` files, intentionally sort inputs, and pass the list of paths.

Other variants include: `getJavaFileObjects(File...)`, `getJavaFileObjectsFromFiles(Iterable<? extends File>)`, and `getJavaFileObjectsFromStrings(Iterable<String>)`. When code already uses `java.nio.file.Path`, prefer `getJavaFileObjectsFromPaths` to avoid converting back and forth between `Path` and `File`.

**Contract guarantee:** The compiler does not accept arbitrary bytecode or `class` files as source compilation units. Only `JavaFileObject.Kind.SOURCE` should be passed; if a source file does not exist, cannot be read, or has a name mismatched with its package/public class structure, the compiler will report an appropriate error.

## 5. Complete Example, Compilable on Java 17+

The example creates a Java source file on disk beforehand, uses `StandardJavaFileManager` to construct compilation units, and compiles `.class` files into an output directory. The goal is to verify unit preparation and compilation in isolation.

Initial directory tree:

```text
compile-demo/
├── src/
│   └── demo/
│       └── Greeter.java
└── CompileSources.java
```

`src/demo/Greeter.java`:

```java
package demo;

public class Greeter {
    public static void main(String[] args) {
        System.out.println("Hello from compiled source");
    }
}
```

`CompileSources.java`:

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

public final class CompileSources {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is unavailable");
        }

        Path source = Path.of("src/demo/Greeter.java");
        Path output = Path.of("build/classes");
        if (!Files.isRegularFile(source)) {
            throw new IOException("Missing source: " + source);
        }
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(List.of(source));

            List<String> options = List.of("--release", "17", "-encoding", "UTF-8");
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, units);

            boolean ok = Boolean.TRUE.equals(task.call());
            System.out.println("compiled: " + ok);

            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                    System.err.println(d.getKind() + " line "
                            + d.getLineNumber() + ": " + d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }
        }
    }
}
```

From the `compile-demo/` directory, run on JDK 17+:

```bash
javac -encoding UTF-8 CompileSources.java
java CompileSources
java -cp build/classes demo.Greeter
```

Exact output when the source is valid and a compiler is available:

```text
compiled: true
Hello from compiled source
```

The first line comes from `CompileSources`; the second comes from the newly compiled `demo.Greeter` program. The resulting file is `build/classes/demo/Greeter.class`. The compiler program **does not automatically execute** this class during `task.call()`; the `java -cp` command is a separate step.

### Why Does the Example Use setLocationFromPaths?

`manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(output))` configures where `.class` files are generated at the file manager level. It is similar to passing `-d build/classes` to the compiler, and you do not need to set `-d` a second time in `options`. Other locations such as `CLASS_PATH` and `SOURCE_PATH` can be configured depending on dependencies and project layout; avoid both configuring the file manager and passing conflicting flags that make verification difficult.

## 6. Preparing Multiple Compilation Units

In a real project, a plugin may consist of multiple files in the same package or importing one another. You must pass the collection of `JavaFileObject` instances into the same compilation task so the compiler can check source dependencies.

Java 17+ example (placed in a method that already has `manager`):

```java
List<Path> sourceFiles = List.of(
        Path.of("src/demo/Greeter.java"),
        Path.of("src/demo/Util.java"));

Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(sourceFiles);
```

This example is **not standalone**; it requires `src/demo/Util.java` to actually exist. A common mistake is passing only an entry-point file and expecting all sources outside the source path to be discovered automatically. When compiling an entire plugin module, explicitly define input files, source path, and dependency path according to the build graph.

### Collecting Sources Safely from a Directory

```java
Path root = Path.of("src").toAbsolutePath().normalize();
List<Path> sourceFiles;
try (var paths = Files.walk(root)) {
    sourceFiles = paths
            .filter(Files::isRegularFile)
            .filter(p -> p.toString().endsWith(".java"))
            .sorted()
            .toList();
}
```

The snippet above is part of a program that already imports `Files`, `Path`, and `List` and must handle `IOException`; it is not a standalone program. `Files.walk` returns a stream that must be closed. In a plugin host accepting sources from users, you must also check symlinks, allowed directory bounds, file count/total size, and canonical paths. `normalize()` only normalizes path syntax; it **does not** resolve symlinks or guarantee a file stays inside a trusted root.

## 7. Class Path, Module Path, and Dependencies

The standard file manager can configure different locations. When plugin code imports the contract API:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(Path.of("lib/plugin-api.jar")));
```

This is an illustrative snippet in a context that already has `manager`. The compiler looks up `plugin-api.jar` on the class path when resolving symbols. If the API belongs to a named module and the plugin compiles as a JPMS module, configure `MODULE_PATH` and appropriate source/module options; do not confuse the compile class path with the module path.

For code running at runtime, dependency visibility depends on the host's class loader/module layer. That `javac` finds a library at compile time does not guarantee the plugin's loader at execution time sees that exact same artifact. In a plugin architecture, the contract API should be shared consistently and avoid duplicate packaging that causes class identity conflicts.

## 8. Diagnostics and Error Flow

`DiagnosticCollector` accumulates errors, warnings, and notes from the compiler. `Diagnostic` can provide kind, message, source, line, and column, though some diagnostics carry `NOPOS` and are not tied to a specific file. When displaying errors in a UI, do not assume every error has a valid line number.

```java
for (Diagnostic<? extends JavaFileObject> diagnostic :
        diagnostics.getDiagnostics()) {
    String name = diagnostic.getSource() == null
            ? "<compiler>"
            : diagnostic.getSource().getName();
    System.out.println(name + ":" + diagnostic.getLineNumber()
            + " " + diagnostic.getKind());
}
```

This snippet is placed in the example's context and is not standalone. Before exposing diagnostic contents to a UI or logs, consider stripping absolute paths and private information. Avoid using verbatim compiler messages as stable keys for business logic decisions since they can differ across JDKs/locales.

Distinguish the cases:

- `compiler == null`: runtime lacks a system Java compiler.
- `task.call()` returns `false`: normal compilation error occurred; inspect diagnostics.
- `getTask(...)`, the file manager, or I/O throws an exception: configuration/file-read or tool error to handle separately.
- `task.call()` may throw a runtime exception for abnormal failures; do not conflate every exception with a source syntax error.

## 9. Managing the StandardJavaFileManager Lifecycle

The file manager may cache file metadata or resources for the compiler. Use `try-with-resources` to close it right after the compilation batch. Do not reuse the same file manager across concurrent tasks without verifying the implementation's thread safety.

A standard file manager can be used across multiple sequential compilation tasks to leverage caching. However, each task may only be called once; create a new task for the next compilation. When implementing a long-lived compile service, clearly specify when to create, reuse, and close file managers to prevent leaks and keep configuration state from one plugin from affecting another.

In particular, `getJavaFileObjectsFromPaths(...)` returns file objects tied to the manager; do not keep them after the manager is closed and expect to continue reading sources. Compilation units are normally prepared and consumed within the same manager scope.

## 10. Compiling a Plugin Does Not Mean Safe Execution

In a user-supplied plugin system, the Java Compiler API **is not a sandbox**. Source code can contain dangerous code, and compilation itself can trigger annotation processors if unrestricted. When using the compiler with untrusted sources:

- Accept sources only from permitted locations; enforce limits on file count, size, and compile timeout.
- Control the class path, module path, and annotation processors; if annotation processing is not needed, set `-proc:none`.
- Avoid running compilation in the same process with overly broad privileges when handling untrusted sources; consider a separate process with resource limits and OS isolation.
- Do not automatically load or initialize freshly compiled classes without an evaluation step.
- Verify runtime dependencies and contract version before activating the plugin.

Filesystem, network, and library access at runtime still depend on process/OS permissions and isolation design, and are not automatically restricted by `StandardJavaFileManager` alone.

## 11. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
|---|---|---|
| `getSystemJavaCompiler()` returns null | No system compiler provider in the runtime image | Run on a full JDK or a runtime image containing `jdk.compiler` |
| Cannot find `src/demo/Greeter.java` | Wrong working directory/path | Verify the working directory and use validated `Path` objects |
| `package demo does not exist` | Missing dependency or source path | Configure `CLASS_PATH`/`MODULE_PATH` properly and include all sources |
| No `.class` generated in expected directory | `CLASS_OUTPUT` not set or wrong output configuration | `setLocationFromPaths(CLASS_OUTPUT, List.of(output))` |
| `.java` file with Vietnamese text is misread | Inconsistent input charset | Specify UTF-8 on both the file manager and compiler options |
| Source has a public class with mismatched filename | `.java` filename does not match the public top-level class | Name file/package properly per Java rules |
| Calling `task.call()` multiple times | A compilation task executes only once | Create a new task from the compiler for the next compilation |
| File descriptor leak | File manager or directory-walk stream not closed | Use try-with-resources |
| Compiles OK but fails at runtime with ClassNotFound | Runtime class path/loader cannot see output | Configure the loader/runtime module path after compilation |

## 12. Practical Checklist

1. Verify that the system compiler exists.
2. Validate source roots and each input path; identify the `.java` files to compile.
3. Create `DiagnosticCollector` and `StandardJavaFileManager` with an explicit charset.
4. Create the output directory and configure `StandardLocation.CLASS_OUTPUT`.
5. Configure the appropriate `CLASS_PATH`/`MODULE_PATH` dependencies.
6. Convert `Path`s to `Iterable<? extends JavaFileObject>` via `getJavaFileObjectsFromPaths`.
7. Pass compilation units into `getTask` along with explicit compiler options.
8. Call `task.call()` exactly once; handle the Boolean result and diagnostics.
9. Close the file manager; inspect `.class` outputs and load the plugin only in a separate activation stage.

**Conclusion:** `StandardJavaFileManager` is the standard bridge between the filesystem and `JavaCompiler`. Properly preparing compilation units ensures the compiler receives the required source files, resolves dependencies, and writes class output to a controlled location. It is the foundational step for a runtime plugin compilation system, but it does not replace class loader management, module layers, or security controls when activating compiled code.
