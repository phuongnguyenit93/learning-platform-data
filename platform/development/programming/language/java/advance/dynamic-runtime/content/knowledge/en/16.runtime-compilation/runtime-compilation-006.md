# 16.6 File Management via `StandardJavaFileManager` and `ForwardingJavaFileManager`

When using the Java Compiler API (`javax.tools`) to **compile Java at runtime**, the compiler does not necessarily read source directly from a `.java` file and write class files into a default directory. It works through an abstraction layer called **`JavaFileManager`**, with `FileObject` and `JavaFileObject` representing input/output resources.

Two components are especially important:

- **`StandardJavaFileManager`**: the compiler's built-in file manager, working with `File`/`Path`, directories, JARs, and source/class search locations. This is the usual choice when you want to read `.java`, declare classpath/module path, specify where to write `.class`, and reuse the file manager across compilations.
- **`ForwardingJavaFileManager<M extends JavaFileManager>`**: a **delegating (decorator)** class for compiler requests to another file manager. You can override certain operations, such as `getJavaFileForOutput(...)` to store `.class` bytecode in RAM or log it, while classpath, platform classes, source lookup, and module operations still **delegate** to the standard manager.

The essence of this lesson is not learning a new `javac` command, but understanding **how the compiler selects sources, resolves dependencies, creates outputs, and returns diagnostics through the file manager**. When designed properly, you can compile from files, from Java source strings, or a mix; collect outputs into a directory or RAM; and choose the exact points to customize without rewriting the compiler's entire file management system.

> **Practice scope:** Java 17+ with a JDK that has the `jdk.compiler` module. The five standalone `.java` examples in this lesson have been compiled with `javac --release 17` and run to verify stdout. The examples create temporary directories when needed and delete them in `finally`; no output is required in the project directory outside compiling the examples themselves. To keep things simple and output deterministic, the tasks use `--release 17` and `-proc:none` (no annotation processors).

## 1. Architecture Before Writing Code

Picture a compile call using the Java Compiler API:

```text
                     ToolProvider.getSystemJavaCompiler()
                                    |
                                    v
                               JavaCompiler
                                    |
                   getStandardFileManager(...)
                                    |
                                    v
                           StandardJavaFileManager
                             |                 |
                    read source/JAR      write .class to disk
                             |                 |
                             +--------+--------+
                                      |
                         (can wrap with decorator)
                                      |
                                      v
              ForwardingJavaFileManager<StandardJavaFileManager>
                 |                                     |
         override a few methods                   super.* -> delegate
                 |                                     |
         intercept .class output                  source/classpath/JDK
         write to RAM or log                      via standard manager
                 \                                     /
                  \                                   /
                   +-------------+-------------------+
                                 |
               JavaCompiler.getTask(..., manager, ...)
                                 |
                           task.call()
                                 |
                         Boolean + diagnostics
```

A file manager is not the compiler itself; it is the **storage/lookup service** the compiler uses. The compiler decides how to parse, resolve symbols, type-check, and generate bytecode. The file manager decides which `JavaFileObject` the compiler reads from and where it writes to. That is why wrapping the standard manager is usually simpler than implementing `JavaFileManager` from scratch.

### 1.1. Three APIs to Distinguish

| API | Role | Example |
| --- | --- | --- |
| `JavaCompiler` | Creates compilation tasks, coordinates the compiler | `ToolProvider.getSystemJavaCompiler()`, `getTask(...)` |
| `JavaFileManager` | SPI contract for reading/writing sources, classes, resources, and listing/finding files | `getJavaFileForOutput(...)`, `list(...)`, `inferBinaryName(...)` |
| `StandardJavaFileManager` | Standard filesystem-based `JavaFileManager` | `setLocationFromPaths(...)`, `getJavaFileObjectsFromPaths(...)` |
| `ForwardingJavaFileManager` | Delegating decorator, overrides extension points | `super.getJavaFileForOutput(...)` or returns a memory object |

`JavaFileObject` instances represent individual files or data regions; they do not necessarily correspond to real `java.io.File` objects on disk.

## 2. Standard Lifecycle of a Compilation Task

Common code pattern:

```java
// Illustrative fragment: "sourcePath" and "outputDir" were properly created beforehand.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Application requires a JDK with a compiler");
}
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager standard =
             compiler.getStandardFileManager(
                     diagnostics, java.util.Locale.ROOT,
                     java.nio.charset.StandardCharsets.UTF_8)) {
    standard.setLocationFromPaths(
            StandardLocation.CLASS_OUTPUT, java.util.List.of(outputDir));
    Iterable<? extends JavaFileObject> units =
            standard.getJavaFileObjectsFromPaths(java.util.List.of(sourcePath));
    Boolean ok = compiler.getTask(
            null, standard, diagnostics,
            java.util.List.of("--release", "17", "-proc:none"),
            null, units).call();
}
```

This is a **fragment**, not standalone runnable because `sourcePath`/`outputDir` are undeclared. Complete programs start in section 5.

Sequence:

1. Obtain `JavaCompiler` from `ToolProvider`. If no compiler is available in the current runtime, `getSystemJavaCompiler()` can return `null`; check early instead of hitting an NPE.
2. Create `StandardJavaFileManager` with a `DiagnosticListener` or `DiagnosticCollector`, `Locale`, and `Charset` if needed.
3. Specify the **output location** and/or input locations using the standard manager's APIs; ensure paths already exist when required by the API.
4. Convert `Path` or `File` into `JavaFileObject`, creating `compilationUnits`.
5. Call `compiler.getTask(out, fileManager, diagnostics, options, classes, compilationUnits)` to create **a new `CompilationTask`**.
6. Call `task.call()` exactly once; `Boolean.TRUE` indicates the compilation task succeeded. Read diagnostics even when the result is unsuccessful.
7. Close the file manager properly after finishing; if you need to load the compiled classes, use an appropriate class loader after output completes.

### 2.1. Six Parameters of `getTask`

| Parameter | Meaning |
| --- | --- |
| `Writer out` | Where the compiler writes messages not represented via diagnostics (or `null` for default) |
| `JavaFileManager fileManager` | Input/output files; can be a standard manager or a forwarding manager |
| `DiagnosticListener<? super JavaFileObject> diagnosticListener` | Receives structured errors/warnings, e.g. `DiagnosticCollector` |
| `Iterable<String> options` | Compiler options such as `--release`, `-proc:none`, `-classpath` |
| `Iterable<String> classes` | Class names related to annotation processing in certain modes; usually `null` when compiling sources |
| `Iterable<? extends JavaFileObject> compilationUnits` | Input sources; can come from paths or strings in RAM |

Do not confuse `classes` with `.class` output. It is a different API parameter; the file manager is what manages `JavaFileObject.Kind.CLASS` generated by the compiler.

### 2.2. `Compiler API` Does Not Automatically Load Compiled Classes

`task.call() == true` indicates that the compilation task succeeded, **not** that the new class has been loaded into a class loader ready for you to call immediately. If `StandardJavaFileManager` wrote to an output directory, a `URLClassLoader` or compatible loader needs to access that directory. If outputs are kept in RAM, you must have a loader that reads bytes and calls `defineClass(...)`, or forward bytes to another appropriate mechanism.

Compilation and execution are **two different phases**, with their own class loader, module, security, and lifecycle concerns. A compiler file manager is **not a sandbox** for running untrusted Java source.

## 3. `StandardJavaFileManager`: The Foundation for Reading/Writing Files and JARs

`StandardJavaFileManager` is an **interface**; obtain an instance via:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
StandardJavaFileManager fm =
        compiler.getStandardFileManager(null, null, null);
```

This is a valid Java fragment after appropriate imports, but a JDK environment is required so that `compiler` is non-null.

The standard manager can create `JavaFileObject` instances for:

- `.java` source files on the filesystem;
- `.class` files in directories or JARs;
- Certain resources in ZIP/JARs according to configured `Location`s;
- Sources/outputs used by the compiler when processing packages, modules, or annotation processors.

You do not instantiate the JDK standard manager's concrete class directly with `new`. The implementation is provided by the compiler. Therefore **you should not subclass its internal implementation** to customize it; `ForwardingJavaFileManager` is the standard contract-based wrapping approach, independent of `javac`'s internal classes.

### 3.1. Commonly Used Methods

| Method | Use when |
| --- | --- |
| `getJavaFileObjectsFromPaths(Collection<? extends Path>)` | You have a list of `.java` sources specified by `Path` |
| `getJavaFileObjects(File...)` / `getJavaFileObjectsFromFiles(...)` | You have `java.io.File` file objects |
| `getJavaFileObjects(String...)` / `getJavaFileObjectsFromStrings(...)` | You have file names as strings |
| `setLocationFromPaths(Location, Collection<? extends Path>)` | Configure directories/JARs for a location |
| `getLocationAsPaths(Location)` | Inspect paths assigned to a location |
| `setLocationForModule(...)` | Configure module-oriented location when doing module-aware compilation |
| `flush()` | Flush buffered output resources (does not close the entire manager) |
| `close()` | Release resources associated with the manager, such as JAR/file handles |

**Prefer the overload accepting `Collection<? extends Path>`** when using a list of `Path`s. The overload `getJavaFileObjectsFromPaths(Iterable<? extends Path>)` was deprecated in Java 13, in part to avoid accidentally passing **a single `Path`**: `Path` itself is an `Iterable<Path>` over its name elements, leading to unintended overload selection.

If you only have one `Path`, use `List.of(path)` or `getJavaFileObjects(path)` to clearly express "one file", rather than passing `getJavaFileObjectsFromPaths(path)` directly and expecting Java to treat it as a singleton.

### 3.2. Important `StandardLocation`s

| Location | Typical meaning | Notes |
| --- | --- | --- |
| `StandardLocation.CLASS_PATH` | Where the compiler looks for class/JAR dependencies for classpath compilation | In the compiler API, the environment classpath may differ from expectations; configure explicitly when needed |
| `StandardLocation.SOURCE_PATH` | Look up dependent/available sources on the source path | Different from `compilationUnits` passed directly |
| `StandardLocation.CLASS_OUTPUT` | Write `.class` output | Equivalent to `javac -d output`, but configured via the file manager |
| `StandardLocation.SOURCE_OUTPUT` | Write generated source, typically from annotation processors | May need separate interception if outputting to RAM |
| `StandardLocation.ANNOTATION_PROCESSOR_PATH` | Where to look for annotation processors when using classpath processors | Distinct from the classpath used to resolve types |
| `StandardLocation.MODULE_PATH` | Look up module dependencies | May require module-specific logic such as `getLocationForModule(...)` |

Input/output locations are **context** for the compiler/file manager interpreter to handle class and package names. Not every `Location` shares the same directory or supports the same operations. For example, `CLASS_OUTPUT` is an output location; do not use it as a list of arbitrary source files.

### 3.3. Classpath Is Not Identical to the Output Directory

When compiling multiple times sequentially outside the module mechanism:

- `CLASS_OUTPUT` specifies where to write class files;
- `CLASS_PATH` specifies where the compiler **reads** class files as dependencies.

If task B needs a type compiled into output by task A, explicitly configure `CLASS_PATH` to include the output (or pass `-classpath` accordingly), instead of assuming output will always be searched automatically. Oracle `javac` also recommends adding the output directory to the classpath when compilation is not module-based.

Example 4 does this properly: it uses the same manager for two sequential compilation tasks and sets both `CLASS_OUTPUT` and `CLASS_PATH` to the shared directory.

### 3.4. Encoding and Diagnostic Locale

`compiler.getStandardFileManager(listener, locale, charset)` supports setting the charset for reading sources and the locale for diagnostics. In the examples:

```java
compiler.getStandardFileManager(
        diagnostics, java.util.Locale.ROOT,
        java.nio.charset.StandardCharsets.UTF_8);
```

This is a fragment, requiring existing classes/imports. Choosing a charset helps avoid Windows/Linux differences when inputs contain Vietnamese characters. When the source is a `String` inside `SimpleJavaFileObject`, `getCharContent` returns Unicode chars directly; the charset is still useful for files/JARs read by the standard manager.

## 4. `FileObject` and `JavaFileObject`: The Contract Used by the Compiler

Two interfaces in `javax.tools`:

- `FileObject`: general file/resource, readable/writable via stream or reader/writer, with URI, display name, and modification timestamp;
- `JavaFileObject extends FileObject`: adds `Kind`, binary name/access level/nesting information, and operations specific to Java file types.

Common `JavaFileObject.Kind` values:

| Kind | Extension | Use case |
| --- | --- | --- |
| `SOURCE` | `.java` | Input compilation unit, generated source |
| `CLASS` | `.class` | Compiler-generated bytecode or class dependency |
| `HTML` | `.html` | HTML-formatted data related to file objects |
| `OTHER` | Not fixed | Other resources such as configs or non-Java artifacts |

A `JavaFileObject.Kind.CLASS` can be stored in RAM; it is **not** a `Path` pointing to a `.class` file on disk. This is how `ForwardingJavaFileManager` intercepts output.

### 4.1. Proper URI When Creating `SimpleJavaFileObject`

When creating a source from a Java string:

```java
// Fragment: binaryName = "demo.mem.MathBox"
java.net.URI uri = java.net.URI.create(
        "string:///" + binaryName.replace('.', '/')
        + JavaFileObject.Kind.SOURCE.extension);
```

The URI becomes `string:///demo/mem/MathBox.java`, with a **scheme**, root-based path, and matching Java file name. For output in RAM, you can use the scheme `mem:///...` and `Kind.CLASS`. The standard manager Javadoc requires URIs representing files to be absolute and normalized; when creating `SimpleJavaFileObject` yourself, keep a URI with a valid scheme so diagnostics and the compiler can clearly identify it.

A typical `Source extends SimpleJavaFileObject` overrides:

```java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return code;
}
```

For output, `ByteCode extends SimpleJavaFileObject` typically overrides:

```java
@Override
public java.io.OutputStream openOutputStream() {
    return byteStream;
}
```

Both snippets above are **fragments**, without full fields/constructors. All helper classes are written in full in examples 2–3.

### 4.2. Compiling Source from RAM Differs from Outputting to RAM

These are two separate decisions:

- Input from RAM: pass `List.of(new Source(...))` into `getTask(..., compilationUnits)`.
- Output to RAM: the file manager must return a `JavaFileObject` whose `openOutputStream()` writes into a memory buffer when the compiler calls `getJavaFileForOutput(...)`.

If you only create sources from strings and use the **unmodified standard manager**, the compiler can still write `.class` files to the filesystem. If you only intercept `CLASS` output while inputs are `Path`s, you can still compile **from disk files while producing RAM output**. Do not call either case "fully in-memory" without checking input, output, dependencies, and annotation processors.

## 5. Practice 1 — `StandardJavaFileManager` Reading `Path`, Writing `CLASS_OUTPUT`

This example creates a source in package `demo.disk` inside a temporary directory, runs the compiler with the standard file manager, and then loads the class from the output directory.

Create file **`DiskCompileDemo.java`**:

```java
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
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class DiskCompileDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        Path root = Files.createTempDirectory("standard-manager-");
        try {
            Path source = root.resolve("src/demo/disk/Greeter.java");
            Path output = Files.createDirectories(root.resolve("out"));
            Files.createDirectories(source.getParent());
            Files.writeString(source,
                    "package demo.disk; public class Greeter { "
                    + "public static String say(String name) { return \"Hi \" + name; } }",
                    StandardCharsets.UTF_8);
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
                manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(output));
                Iterable<? extends JavaFileObject> units =
                        manager.getJavaFileObjectsFromPaths(List.of(source));
                boolean ok = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, diagnostics,
                        List.of("--release", "17", "-proc:none"),
                        null, units).call());
                System.out.println("compiled: " + ok);
                System.out.println("class exists: "
                        + Files.isRegularFile(output.resolve("demo/disk/Greeter.class")));
                System.out.println("errors: " + diagnostics.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count());
                if (!ok) throw new IllegalStateException("Compilation failed");
            }
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{output.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> type = Class.forName("demo.disk.Greeter", true, loader);
                System.out.println("invoke: " + type.getMethod(
                        "say", String.class).invoke(null, "Ada"));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Commands (run in a separate test directory, with JDK 17+):

```bash
javac --release 17 DiskCompileDemo.java
java DiskCompileDemo
```

**Exact stdout:**

```text
compiled: true
class exists: true
errors: 0
invoke: Hi Ada
```

**Analysis:**

1. `ToolProvider.getSystemJavaCompiler()` provides the compiler. Without a compiler, the program proactively throws an error instead of encountering an NPE.
2. `Files.writeString(...)` creates a physical source under `root/src/demo/disk/Greeter.java`. In `getTask`, the source object is created by the standard manager from that exact `Path`.
3. `setLocationFromPaths(CLASS_OUTPUT, List.of(output))` causes the `demo.disk.Greeter` output to be placed at `out/demo/disk/Greeter.class`.
4. `--release 17` instructs the compiler to use appropriate Java 17 API/source/target; `-proc:none` disables annotation processors in the demo to avoid side effects.
5. `DiagnosticCollector` collects diagnostics; the successful run has no errors (error count is 0).
6. `URLClassLoader` reads the generated class after the compiler finishes and the standard manager is closed; `Class.forName(..., true, loader)` looks up the class by **binary name**.
7. The manager, loader, and temporary directory are all closed/deleted in order. The example does not leave a demo-created output directory around after a successful run.

**Note:** A successful compilation does not automatically synchronize a live class loader to replace an already loaded class of the same name. If you need to load a new version with the same binary name, you must design an appropriate loader/versioning strategy; `StandardJavaFileManager` is only the compiler's file management tool.

## 6. `ForwardingJavaFileManager`: Decorator Instead of Rewriting All of `JavaFileManager`

Conceptual declaration:

```java
public class ForwardingJavaFileManager<M extends JavaFileManager>
        implements JavaFileManager
```

This is an **API signature excerpt**, not standalone code.

The constructor `protected ForwardingJavaFileManager(M fileManager)` takes a file manager as a **delegate**. In subclasses, the `protected final M fileManager` field holds the delegate; non-overridden methods are forwarded to it by default according to the Javadoc.

The strength of this pattern is **customizing only where needed**, while complex capabilities like platform classpath, JAR handling, module path, package scanning, `list(...)`, and `inferBinaryName(...)` can use the standard implementation.

### 6.1. How to Wrap and What Matters When Configuring

```java
// Fragment: compiler has been initialized, output is an already-created Path.
StandardJavaFileManager standard =
        compiler.getStandardFileManager(null, null, null);
standard.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, java.util.List.of(output));
JavaFileManager decorated = new MyForwardingManager(standard);
```

This is only a fragment with `MyForwardingManager` undeclared. Understand that: `ForwardingJavaFileManager` **does not implement the `StandardJavaFileManager` interface** merely because it wraps a standard manager. When you hold a reference of type `JavaFileManager`, you cannot directly call `setLocationFromPaths(...)` of the standard manager through the wrapper variable. Make sure to:

- Configure `standard` before wrapping, or keep a reference to the standard manager for configuration.
- Pass the **wrapper** as `fileManager` to `compiler.getTask(...)` if you want overrides to be invoked.
- Close the wrapper so the delegate closes the underlying manager; avoid creating two uncoordinated close paths.
- Do not cast an ordinary `ForwardingJavaFileManager` to `StandardJavaFileManager` just because the generic type parameter `M` is `StandardJavaFileManager`.

### 6.2. Method for Intercepting Java Class Output

Common override:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {
    if (location == StandardLocation.CLASS_OUTPUT
            && kind == JavaFileObject.Kind.CLASS) {
        // Can log, or return a RAM-backed JavaFileObject.
    }
    return super.getJavaFileForOutput(
            location, className, kind, sibling);
}
```

This is a **fragment** to show the shape of the override, without an enclosing class. `className` is typically a **binary class name** such as `demo.mem.MathBox` or `demo.mem.MathBox$Inner`, not a `.class` file path. `kind` indicates whether the target is `SOURCE`, `CLASS`, etc.; `location` indicates the output context.

`sibling` is a hint about a related source, and may be null. The `JavaFileManager` contract allows implementations to use this hint when there is no explicit output directory, for example writing the class file next to the source. If you delegate, forward the parameters intact; if you manage output yourself, you must decide on a valid mapping from `className` and `location` to the file object.

### 6.3. Not Overriding Means Delegating, Not Losing Functionality

A `LoggingManager` that only overrides `getJavaFileForOutput` can continue to use:

- `list(...)` so the compiler finds classes in packages;
- `getJavaFileForInput(...)` to read dependencies;
- `inferBinaryName(...)` so the compiler infers class names;
- `getClassLoader(...)`/`handleOption(...)` via the delegate;
- `close()`/`flush()` via the delegate.

This only holds to the extent that the forwarding implementation actually delegates those methods; if you build a custom file manager **without using a decorator**, the SPI methods must be validly implemented—do not assume all methods work automatically.

## 7. Practice 2 — Override Output Only to Log, Still Writing Real Files

Create **`ForwardingLogDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class ForwardingLogDemo {
    static final class Source extends SimpleJavaFileObject {
        Source() {
            super(URI.create("string:///demo/log/Check.java"), Kind.SOURCE);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return "package demo.log; public class Check { "
                    + "public static class Child {} }";
        }
    }

    static final class LoggingManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final List<String> outputs = new ArrayList<>();

        LoggingManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                outputs.add(className);
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        Path root = Files.createTempDirectory("forwarding-log-");
        try {
            Path output = Files.createDirectories(root.resolve("out"));
            StandardJavaFileManager standard = compiler.getStandardFileManager(
                    null, null, StandardCharsets.UTF_8);
            try (LoggingManager manager = new LoggingManager(standard)) {
                standard.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(output));
                boolean ok = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, null,
                        List.of("--release", "17", "-proc:none"),
                        null, List.of(new Source())).call());
                Collections.sort(manager.outputs);
                System.out.println("compiled: " + ok);
                System.out.println("logged: " + manager.outputs);
                System.out.println("disk class: " + Files.isRegularFile(
                        output.resolve("demo/log/Check.class")));
                System.out.println("nested class: " + Files.isRegularFile(
                        output.resolve("demo/log/Check$Child.class")));
                if (!ok) throw new IllegalStateException("Compilation failed");
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Commands:

```bash
javac --release 17 ForwardingLogDemo.java
java ForwardingLogDemo
```

**Exact stdout:**

```text
compiled: true
logged: [demo.log.Check, demo.log.Check$Child]
disk class: true
nested class: true
```

**Analysis:**

- `Source` holds the source code right in a Java string, without needing a `Check.java` file on disk. The URI `string:///demo/log/Check.java` describes a matching name/package.
- `LoggingManager` only observes the two `JavaFileObject.Kind.CLASS` outputs, then calls `super.getJavaFileForOutput(...)` so the delegate performs the real file handling.
- The source declares **two binary class names**: `demo.log.Check` and `demo.log.Check$Child`. Therefore the compiler generates **two class files**, not one output for the whole source.
- The result proves the wrapper still delegates to the standard manager: `out/demo/log/Check.class` and `out/demo/log/Check$Child.class` actually exist on disk.
- The program sorts the `outputs` list before printing; it does not rely on the compiler reporting class files in a fixed order.
- The wrapper class holds `StandardJavaFileManager` under the generic `<StandardJavaFileManager>`, but you still configure locations on the `standard` reference. Seeing class names in the log does not automatically mean outputs were redirected to RAM.

**Design lesson:** A `ForwardingJavaFileManager` can work **purely to observe/restrict/log**, rather than always replacing the output storage strategy.

## 8. Compiling Completely in RAM: Need to Replace Both Source and Class Destination

To compile without writing generated class files into the project directory, we design three components:

1. **`Source extends SimpleJavaFileObject`**: carries the Java source string, overrides `getCharContent(...)`.
2. **`ByteCode extends SimpleJavaFileObject`**: carries a `ByteArrayOutputStream`, overrides `openOutputStream()`; the compiler writes `.class` bytes into the buffer.
3. **`MemoryManager extends ForwardingJavaFileManager<StandardJavaFileManager>`**: overrides `getJavaFileForOutput(...)` and returns `ByteCode` when the compiler wants to write `CLASS` at `CLASS_OUTPUT`. Other operations are delegated so standard platform types and dependencies are still used.

```text
Source "string:///demo/mem/MathBox.java"
         |
         | JavaCompiler.getTask(..., memoryManager, ...)
         v
      javac
         |
         | getJavaFileForOutput(CLASS_OUTPUT,
         |                      "demo.mem.MathBox", CLASS, sibling)
         v
      ByteCode "mem:///demo/mem/MathBox.class"
         |
         | openOutputStream()
         v
      byte[] stored in Map<String, ByteCode>

After compilation:
  ByteLoader.findClass("demo.mem.MathBox")
         |
         v
      defineClass(name, byte[], 0, len)
         |
         v
      Class<?> actually loaded by JVM and invokable
```

### 8.1. Why Must We Use a Map Keyed by Binary Name?

Because a single Java source can emit **multiple class files**: nested classes, local/anonymous classes, other classes in the same compilation unit (when valid), or generated classes. A single `ByteArrayOutputStream` would be overwritten or have data mixed. A map like `Map<String, ByteCode>` gives each `className` its own bytecode.

A class name can collide if you recompile; for multi-version systems, you need an appropriate version key/class loader and eviction design. The demo only runs one compilation task.

### 8.2. Why Is the Standard Manager Still Needed as a Delegate?

If you only replace output, the compiler still needs to:

- Look up `java.lang.Object`, `java.lang.String`, and platform APIs;
- Resolve classes/dependencies from classpath/module path;
- Perform `list(...)` and `inferBinaryName(...)` when searching existing classes;
- Read other valid resources/metadata.

`ForwardingJavaFileManager` inherits delegation, so you do not have to rewrite the entire mechanism for reading JDK modules/JAR files. This is the main advantage over implementing `JavaFileManager` from scratch.

### 8.3. Output in RAM Does Not Guarantee Compiling Against RAM Dependencies

Example 3 compiles **one task** containing the main class and a nested class, then loads both via `ByteLoader`. If you want a **subsequent task** to compile new source referencing the just-generated RAM bytecode, overriding only `getJavaFileForOutput` is **not enough**.

The new compiler task also needs to see RAM class bytes as **input**: you may have to properly override `getJavaFileForInput(...)`, `list(...)`, `inferBinaryName(...)`, `contains(...)`, and `getClassLoader(...)` paths when needed, so the compiler can discover/resolve RAM classes by binary name. Or write outputs to a searchable location like an output directory/JAR and place it on `CLASS_PATH` for the next task, as in example 4.

**Do not confuse:** `ByteLoader` used after compilation to run classes does not automatically become the compiler's **JavaFileManager**. The JVM's class loader and `JavaCompiler`'s file manager are two different SPIs.

## 9. Practice 3 — `ForwardingJavaFileManager` Collecting `.class` into RAM

Create file **`MemoryCompileDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class MemoryCompileDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class ByteCode extends SimpleJavaFileObject {
        final ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        ByteCode(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            buffer.reset();
            return buffer;
        }

        byte[] bytes() {
            return buffer.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, ByteCode> classes = new HashMap<>();

        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                ByteCode file = new ByteCode(className, kind);
                classes.put(className, file);
                return file;
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }
    }

    static final class ByteLoader extends ClassLoader {
        private final Map<String, ByteCode> classes;

        ByteLoader(Map<String, ByteCode> classes) {
            super(ClassLoader.getPlatformClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            ByteCode output = classes.get(name);
            if (output == null) throw new ClassNotFoundException(name);
            byte[] bytes = output.bytes();
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        String code = "package demo.mem; public class MathBox { "
                + "public static int sum(int a, int b) { return a+b; } "
                + "public static class Inner { "
                + "public static int triple(int n) { return n*3; } } }";
        StandardJavaFileManager standard = compiler.getStandardFileManager(
                null, null, StandardCharsets.UTF_8);
        try (MemoryManager manager = new MemoryManager(standard)) {
            boolean ok = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, null, List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source("demo.mem.MathBox", code))).call());
            System.out.println("compiled: " + ok);
            List<String> names = new ArrayList<>(manager.classes.keySet());
            Collections.sort(names);
            System.out.println("outputs: " + names);
            System.out.println("all bytes present: " + manager.classes.values().stream()
                    .allMatch(item -> item.bytes().length > 0));
            if (!ok) throw new IllegalStateException("Compilation failed");

            ClassLoader loader = new ByteLoader(manager.classes);
            Class<?> box = Class.forName("demo.mem.MathBox", true, loader);
            Class<?> inner = Class.forName("demo.mem.MathBox$Inner", true, loader);
            System.out.println("sum: " + box.getMethod(
                    "sum", int.class, int.class).invoke(null, 19, 23));
            System.out.println("triple: " + inner.getMethod(
                    "triple", int.class).invoke(null, 7));
        }
    }
}
```

Commands:

```bash
javac --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
```

**Exact stdout:**

```text
compiled: true
outputs: [demo.mem.MathBox, demo.mem.MathBox$Inner]
all bytes present: true
sum: 42
triple: 21
```

Detailed explanation:

1. `Source("demo.mem.MathBox", code)` creates a `JavaFileObject.Kind.SOURCE` from a string, with URI `string:///demo/mem/MathBox.java`.
2. `MemoryManager` receives all file manager calls from the compiler. For `getJavaFileForOutput(CLASS_OUTPUT, binaryName, CLASS, sibling)`, it returns an in-RAM `ByteCode` instead of calling the standard manager.
3. The compiler generates **two** class outputs: `MathBox.class` and `MathBox$Inner.class`. Each output is stored as a value in the map.
4. `ByteCode.openOutputStream()` returns an output stream to `ByteArrayOutputStream`. After `task.call()` succeeds, `bytes()` returns the classfile bytes.
5. `ByteLoader` is a custom loader with permission to call `defineClass(name, bytes, ...)`. `Class.forName(binaryName, true, loader)` can now **find the class in `ByteLoader`** because the classfile bytes have been defined into its namespace; this does **not** mean `Class.forName(name)` using the system loader will also find it.
6. `getMethod("sum", ...)` and `getMethod("triple", ...)` run the newly compiled code, returning `42` and `21`.
7. **No `MathBox.class`/`MathBox$Inner.class` output is written to disk by the standard manager** in this task because all `CLASS_OUTPUT` class outputs were intercepted. If annotation processors are enabled or resources/`SOURCE_OUTPUT` are generated, additional output paths must be controlled.

### 9.1. Limitations of the In-Memory Example

The example intentionally does **not** build a general-purpose compiler framework. In production systems, you need to:

- Ensure map/thread-safety if multiple tasks/threads can use the same manager. The demo uses `HashMap` for a single sequential task.
- Protect resources/memory: large class bytes, many nested classes, size limits, timeouts, eviction, and class loader lifecycle.
- Avoid binary name collisions when the parent loader already has a class with the same name. The example chooses package `demo.mem` and parent platform class loader for clean verification.
- Handle output stream failures, partial compilation, and `false` results. Do not load bytecode from a failed task.
- If processors, generated sources/resources, or compiler searches for RAM classes across tasks are needed, implement the corresponding SPIs instead of only storing `.class` in a map.
- Understand that `ClassLoader#defineClass` and executing arbitrary code **do not create a security sandbox**; proper isolation/permissions are required.

### 9.2. Why Should `ByteCode` Have a Separate URI for Each Class?

Each `JavaFileObject` describes a logical file with a URI and `Kind`; the compiler, diagnostics, and file manager may rely on that identity. Therefore a URI like `mem:///demo/mem/MathBox$Inner.class` is clearer than an unnamed object or reusing the same URI for all classes. `SimpleJavaFileObject` handles part of the default contract; subclasses only override the streams they need.

## 10. Extending `ForwardingJavaFileManager`: Choosing the Right Interception Points

### 10.1. `getJavaFileForOutput` vs `getFileForOutput`

`JavaFileManager.getJavaFileForOutput(Location, className, Kind, sibling)` creates file objects for **Java source/class** outputs. `getFileForOutput(Location, packageName, relativeName, sibling)` is for **arbitrary resources** at the corresponding location/package/relative path.

| Output to handle | Hook point typically needed |
| --- | --- |
| Compiler-generated `.class` | `getJavaFileForOutput(..., Kind.CLASS, ...)` |
| Processor-generated `.java` | `getJavaFileForOutput(..., Kind.SOURCE, ...)` at `SOURCE_OUTPUT` |
| Resources like `META-INF/...` | `getFileForOutput(...)` |
| Reading classes already in RAM | `getJavaFileForInput(...)` and/or `list(...)` plus name inference |
| Adjusting how the compiler recognizes class names | `inferBinaryName(...)` for custom file objects |
| Serving module-aware tools | `getLocationForModule(...)`, `listLocationsForModules(...)`, related methods |

If the implementation/compiler uses the newer `getJavaFileForOutputForOriginatingFiles(...)` or `getFileForOutputForOriginatingFiles(...)` overloads, check their delegation/default paths and override them if the pipeline requires it. Do not assume intercepting one overload always catches all outputs across every compiler and annotation processor version.

### 10.2. `sibling` and Originating Files Are Not Runtime Dependencies

`sibling`/`originatingFiles` provide related source information when deciding **output location** or file-generation relationships; they are not a list of classpath dependencies. If the output location has been explicitly set, the standard manager can ignore the source's location when choosing the output directory, as in demo 2. With a custom manager, you should still preserve appropriate metadata for annotation processing/incremental compilation if the framework needs it.

### 10.3. When Must You Override `list` or `inferBinaryName`?

If the file manager provides **classfile inputs outside disk**, the compiler may ask:

- `list(CLASS_PATH, packageName, kinds, recurse)` to find candidate file objects in a package;
- `inferBinaryName(location, file)` to determine the binary class name;
- `getJavaFileForInput(location, className, Kind.CLASS)` to read specific bytes.

If you return a custom `ByteCode` object without teaching the manager how to infer its binary name, the compiler may fail to resolve the class even though the object contains valid bytecode. This often appears when turning a single-task in-memory demo into a multi-task IDE/compiler service. **The output write path** and **the dependency read path** are two halves that must be designed together.

## 11. Reusing `StandardJavaFileManager` Across Multiple Tasks

According to the `JavaCompiler` Javadoc, the standard file manager is designed to **be reusable across multiple sequential compilation tasks**. This can save filesystem/JAR scanning. However:

- **Do not reuse the `CompilationTask` itself** after `call()` has been invoked; create a new task for each compilation.
- **You can reuse the same standard manager** across sequential tasks, as long as it has not been `close()`d.
- Configure the classpath appropriately so later tasks see class outputs from earlier tasks.
- Do not assume a manager is thread-safe for concurrent compile tasks. Isolate the manager per task/request, or verify implementation documentation and synchronize if sharing.
- You can call `flush()` between runs when needed to ensure outputs have been flushed to storage; `flush()` does not replace `close()`.

### 11.1. Practice 4 — Compiling Twice with the Same Standard Manager

Create **`ReuseManagerDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class ReuseManagerDemo {
    static final class Source extends SimpleJavaFileObject {
        final String content;

        Source(String name, String content) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        Path root = Files.createTempDirectory("reuse-java-manager-");
        try {
            Path out = Files.createDirectories(root.resolve("out"));
            try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                    null, null, StandardCharsets.UTF_8)) {
                manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(out));
                manager.setLocationFromPaths(StandardLocation.CLASS_PATH,
                        List.of(out));
                List<String> options = List.of("--release", "17", "-proc:none");
                boolean first = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, null, options, null, List.of(new Source(
                                "demo.chain.First",
                                "package demo.chain; public class First {"
                                + "public static int value() {return 40;} }"))).call());
                boolean second = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, null, options, null, List.of(new Source(
                                "demo.chain.Second",
                                "package demo.chain; public class Second {"
                                + "public static int value() {return First.value()+2;} }"))).call());
                System.out.println("first: " + first);
                System.out.println("second: " + second);
                System.out.println("second file: " + Files.isRegularFile(
                        out.resolve("demo/chain/Second.class")));
                if (!first || !second) throw new IllegalStateException("compile failed");
            }
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{out.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> second = Class.forName("demo.chain.Second", true, loader);
                System.out.println("result: " + second.getMethod("value").invoke(null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Commands:

```bash
javac --release 17 ReuseManagerDemo.java
java ReuseManagerDemo
```

**Exact stdout:**

```text
first: true
second: true
second file: true
result: 42
```

**Explanation:**

1. `Source` is a `SimpleJavaFileObject` in RAM, but the **outputs** of both tasks are real files in the `out` directory.
2. The first task generates `demo.chain.First.class` containing `First.value() == 40`.
3. The same standard manager is used for the **second task**. This task has source `demo.chain.Second` referencing `First.value()`.
4. `CLASS_OUTPUT` specifies where to write new classes; `CLASS_PATH` specifies where the compiler looks for previously generated classes. The second task compiles successfully because the first task's output is now on the classpath.
5. The program loads `demo.chain.Second` and calls `value()`, resulting in `40+2=42`.
6. Each `compiler.getTask(...)` creates a **separate task**, while `manager` is reused; that is the pattern recommended by the `JavaCompiler` API for sequential compilations.

### 11.2. When Do You Need to Replace `StandardJavaFileManager` with Forwarding Between Tasks?

If you want to leverage the standard manager's classpath/JAR caching while also having behaviors like storing outputs in RAM or recording metrics, you can wrap the same standard manager with a forwarding manager. However, all cached/in-memory state must be considered in terms of lifecycle:

- Output data after task A may not automatically appear in `list`/`getJavaFileForInput` of task B.
- Two tasks using the same wrapper may share the map; entries need to be cleared/managed when versions change.
- Only after implementing the additional read path do you truly have a "RAM classpath" for the compiler.
- If using on-disk output for the previous task, explicitly configuring `CLASS_PATH` is usually simpler and easier to debug.

## 12. Diagnostics: The File Manager Does Not Replace `DiagnosticCollector`

There are two separate channels:

- **File manager**: provides source/output `JavaFileObject`s and the file lookup model.
- **`DiagnosticListener` / `DiagnosticCollector`**: receives errors, warnings, recording source, kind, line/column/position/code/message from the compiler.

If compilation fails, `getTask(...).call()` typically returns `false` rather than producing valid classes. You need to read `DiagnosticCollector.getDiagnostics()`, not guess from whether there are a few bytes in the map or partial output files.

### 12.1. Practice 5 — Source in RAM and Structured Compile Errors

Create **`DiagnosticsDemo.java`**:

```java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        JavaFileObject broken = new SimpleJavaFileObject(
                URI.create("string:///demo/Broken.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return "package demo; public class Broken { "
                        + "int get() { return missingName; } }";
            }
        };
        DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(collector, null, null)) {
            boolean ok = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, collector,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(broken)).call());
            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
            System.out.println("compiled: " + ok);
            System.out.println("errors present: " + (errors > 0));
            System.out.println("source is known: " + collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .allMatch(d -> d.getSource() == broken));
        }
    }
}
```

```bash
javac --release 17 DiagnosticsDemo.java
java DiagnosticsDemo
```

**Exact stdout:**

```text
compiled: false
errors present: true
source is known: true
```

Analysis:

1. `JavaCompiler` compiles source `Broken` which has an undeclared variable name `missingName`.
2. The task returns `false`. `DiagnosticCollector` receives at least one `Diagnostic.Kind.ERROR`; the program does not print the exact message because wording/locale can vary by JDK.
3. Every error in the demo has `broken` as its source, showing that diagnostics link back to the source `JavaFileObject` even when the source does not exist as a physical file.
4. Do not run the class because compilation **failed**. For a file manager storing outputs in RAM or on disk, if an incomplete task has already produced artifacts, production code needs a rollback/cleanup policy before using them.
5. Passing `collector` to both `getStandardFileManager` and `getTask` does not mean the compiler will auto-fix errors or change semantics; those are just the two API places that take a listener to report diagnostics from their respective parts.

### 12.2. A `false` Result Differs from Compiler/File Manager Exceptions

Distinguish:

| Event | What is typically observed |
| --- | --- |
| Java source has syntax/type errors | `getTask(...).call()` returns `false` and `Diagnostic.Kind.ERROR` is present |
| File manager cannot read/write | `IOException` in the SPI may be reported by the compiler as diagnostics or thrown as an exception, depending on API/implementation |
| `compiler == null` | The environment does not provide a system compiler; cannot create a task |
| Invalid tool option | May produce `IllegalArgumentException`/diagnostics from `getTask` or at execution time, depending on the option |
| Exception in custom `SimpleJavaFileObject`/`ForwardingJavaFileManager` | Compilation may fail via exception or diagnostics; do not swallow errors and return a broken file object |
| Task already called `call()` and is called again | Do not reuse `CompilationTask`; create a new task |

In applications, handle **Boolean task result**, **diagnostics**, and **exceptions**. Simply seeing `.class` files exist is not enough to prove the build completely succeeded.

## 13. File Manager Issues in Systems with Annotation Processors

When annotation processing is enabled:

1. Processors can generate **sources** (`SOURCE_OUTPUT`), **classes** (`CLASS_OUTPUT`), and **resources** via `Filer`.
2. The compiler may use `getJavaFileForOutput` for Java sources/classes and `getFileForOutput` for resources.
3. In addition to overloads taking `sibling`, newer JDK APIs have `ForOriginatingFiles` variants to preserve source-to-output provenance; check the specific JDK.
4. If an in-memory manager only intercepts `getJavaFileForOutput(CLASS_OUTPUT, ..., CLASS, ...)`, generated sources/resources may **still be written to the filesystem**.
5. If a processor or compiler looks up generated classes within the same or another task, the manager must also ensure input/list/binary-name operations support resolution.
6. Output locations must be compatible with both the compiler and processors; do not turn every request—including resources/modules—into an undifferentiated RAM file object ignoring location/kind.

All examples in this lesson set `-proc:none` to focus solely on the file manager and avoid creating processor outputs outside the demo scope. When removing this option in real applications, test artifact-generation paths separately.

### 13.1. Modules and File Locations

Java 9+ provides module-oriented locations. When compiling modular code:

- Platform/user modules are looked up via the module path;
- You must account for locations depending on the module name;
- Methods such as `getLocationForModule` and `listLocationsForModules` may participate;
- `StandardJavaFileManager.setLocationForModule(...)` configures module-specific paths;
- A custom in-memory manager that only compares `CLASS_OUTPUT` by object identity may fail to catch **module-specific output locations**.

For module-aware compilation or different JDKs/toolchains, test the actual location contract instead of hard-coding assumptions from classpath-only examples.

## 14. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime does not provide system compiler/tool module | Run with a JDK that has `jdk.compiler` and the appropriate module |
| Task compiles source but no class appears in `out` | Wrong `CLASS_OUTPUT`, wrapper intercepted output, task failed, different module layout | Check task status, diagnostics, and the file manager being passed in |
| Source `Path` is misinterpreted as multiple path components | Accidentally called the `Iterable<Path>` overload with a single `Path` | Use `List.of(path)` or `getJavaFileObjects(path)` |
| `IllegalArgumentException` when configuring location | Invalid directory, wrong output location, unsupported `Path` | Create a valid directory/path, choose the right `StandardLocation` |
| `ClassNotFoundException` after `call() == true` | Classloader does not see directory/map or wrong class name | Load via the right loader, check binary package name |
| One source generates multiple classes, map has only one entry | Interception did not store per binary name | Use `Map<String, ByteCode>`, handle nested/anonymous classes |
| Source is in RAM but `.class` files still appear on disk | Only replaced input source, still using standard output | Intercept `getJavaFileForOutput(CLASS_OUTPUT, CLASS)` |
| RAM output succeeds but next task cannot resolve the class | Missing input read path `list`/`getJavaFileForInput` | Implement read SPI or put bytecode onto `CLASS_PATH` |
| Wrapper logs but does not capture bytes | Override logs and then `return super.getJavaFileForOutput` | Return a RAM-backed `JavaFileObject` if you truly want in-memory |
| `ForwardingJavaFileManager` lacks `setLocationFromPaths` | Wrapper does not implement `StandardJavaFileManager` | Configure via the `standard` reference, do not cast the wrapper |
| Compiler does not see previous task's output | `CLASS_OUTPUT` is not on classpath for the new task | Add output directory to `CLASS_PATH` or options |
| RAM bytecode only contains outer class, missing nested class | Did not store every `className` requested by the compiler | Intercept each call by binary class name |
| Diagnostics empty yet task fails | Error occurred in SPI, startup/options, or exception before collector recorded | Check exceptions/out/return value, not just error count |
| Closing manager before task finishes | File/JAR streams may already be closed | Keep manager open until after `task.call()` and flush/output completion |
| Loading generated code unsafely | File manager only manages I/O, does not sandbox code | Isolate execution and restrict permissions/resources at runtime |
| Memory leak due to `URLClassLoader`/`ByteLoader` retaining classes | Loader/class bytecode/cache remains reachable | Manage references, close `URLClassLoader`, monitor class unloading |
| Annotation processor generated resources leak to disk | Did not intercept `SOURCE_OUTPUT`/`getFileForOutput` | Extend wrapper for source/resource outputs |
| Same binary name but classloader returns old class | Parent delegation or class identity already loaded | Use an appropriate name/version/loader strategy |
| Overwriting classfiles of another task | Shared output directory or concurrent file manager | Separate output by task/version, do not share manager without synchronization |

### 14.1. Pitfalls with `super`, `fileManager`, and Recursion

In a subclass:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location, String name,
        JavaFileObject.Kind kind, FileObject sibling) throws IOException {
    // Proper delegate pattern:
    return super.getJavaFileForOutput(location, name, kind, sibling);
}
```

This is an illustrative fragment, missing class/import context. **Do not** call `this.getJavaFileForOutput(...)` from inside the override itself without a termination condition: that causes infinite recursion. `super...` calls the forwarding implementation to delegate to the underlying manager. If you need to log, log first and then delegate.

### 14.2. Pitfalls with `FileObject.toUri()` and Binary Names

`toUri()` is the identity of a file object, **not** the class name the JVM uses everywhere. `demo.mem.MathBox` is a binary class name, whereas `mem:///demo/mem/MathBox.class` is a URI. If you pass the URI string to `Class.forName`, no class with that name exists.

### 14.3. Pitfalls with File Manager and Loader Lifetimes

- The file manager manages **compilation**; the loader manages **class loading/execution**.
- Closing the file manager does not automatically unload already-loaded classes.
- Closing `URLClassLoader` releases loader resources but does not immediately unload classes that remain reachable.
- A retained in-memory bytes map can grow memory even when no compilation tasks remain.
- Multiple dynamic versions with the same binary name can be **different classes** if their defining classloaders differ; do not rely solely on a string name to identify a class across loaders.

## 15. Checklist for a Reliable Runtime Compiler

Before putting a runtime compiler into production:

1. **Environment:** verify compiler availability and valid version/release options.
2. **Sources:** choose `Path`/in-memory source and ensure `JavaFileObject.Kind.SOURCE`, URI, and binary name/package are consistent.
3. **Input dependencies:** configure `CLASS_PATH`, `MODULE_PATH`, `SOURCE_PATH` properly; avoid accidental dependence on the working directory.
4. **Output:** decide between file or RAM, choose the corresponding `getJavaFileForOutput`/`getFileForOutput` hook and `Location`.
5. **Multiple class outputs:** store per binary class name and location/version if needed.
6. **Wrapper:** keep the delegate, override only the operations that need changing; use `super` for the rest.
7. **Diagnostics:** collect errors/warnings; check `getTask(...).call()`; do not use partial bytes from a failed task.
8. **Annotation processing:** decide whether to enable/disable; if enabled, test generated sources/resources and output locations.
9. **Classloader:** choose the right loading strategy, avoid name collisions, support cleanup.
10. **Reuse:** share the manager **sequentially** when appropriate; never reuse `CompilationTask`; do not assume thread-safety.
11. **Resource safety:** try-with-resources, flush/close streams, temp cleanup, cache/lifecycle management.
12. **Security:** do not execute untrusted source in the same process merely because you control the file manager; proper isolation is required.

## 16. Self-Check Questions

**Question 1.** Is `StandardJavaFileManager` an implementation class you can `new` directly, or an interface whose instance is provided by the compiler? How do you obtain an instance?

**Question 2.** Does `ForwardingJavaFileManager` automatically become a `StandardJavaFileManager` because its generic type is `<StandardJavaFileManager>`?

**Question 3.** When you only want to log compiler outputs while still writing `.class` files to disk, what should you override and what should you return?

**Question 4.** To collect `.class` files into RAM, where must the object returned by the file manager write? Which method on `JavaFileObject` is key?

**Question 5.** How many class files can a source with a nested class generate? Why do we need a map keyed by `className`?

**Question 6.** Does `getTask(..., compilationUnits)` require physical `.java` files?

**Question 7.** Why must task 2 in `ReuseManagerDemo` see `CLASS_PATH` containing task 1's output directory?

**Question 8.** Should you call `task.call()` twice on the same compilation task? Can you reuse the standard manager?

**Question 9.** If the compiler source is in RAM with no `.java` file, can diagnostics still locate the source object/position?

**Question 10.** If an in-memory manager only overrides `getJavaFileForOutput(CLASS_OUTPUT, Kind.CLASS)`, are annotation processor generated resources guaranteed to stay in RAM?

**Question 11.** Why doesn't `ByteLoader` used in example 3 automatically let a subsequent compiler task resolve class bytes in RAM?

**Question 12.** Are `FileObject.toUri()`, binary class name, and `Path` the same concept?

**Question 13.** When compiling module-oriented code, why might checking only `StandardLocation.CLASS_OUTPUT` be insufficient?

**Question 14.** Once the file manager is closed, do classes already loaded by `URLClassLoader` automatically unload?

**Question 15.** Does wrapping the standard manager with `ForwardingJavaFileManager` make untrusted Java source safe to run?

**Question 16.** On Java 17, what is the clearest way to pass **a single `Path`** to `getJavaFileObjectsFromPaths`? Why?

### Suggested Answers

1. Interface; use `compiler.getStandardFileManager(listener, locale, charset)`.
2. No. The wrapper is still a `JavaFileManager`; to set locations using standard APIs, use the delegate reference.
3. Override `getJavaFileForOutput`; log and then `return super.getJavaFileForOutput(...)`.
4. Return a custom `JavaFileObject` whose `openOutputStream()` writes to a `ByteArrayOutputStream` or suitable storage.
5. Potentially multiple files: outer, nested, anonymous/local...; each binary class name needs its own output.
6. No; you can use a `SimpleJavaFileObject` containing a source string and a valid URI.
7. Because where classes are **written** is not automatically where the compiler **looks** for classes in the next task.
8. Do not reuse the task; the standard manager supports multiple **sequential** tasks.
9. Yes; `Diagnostic.getSource()` can return the in-RAM source `JavaFileObject` itself.
10. No; you must handle `SOURCE_OUTPUT`, resources/`getFileForOutput`, and possibly originating-files overloads.
11. The compiler uses `JavaFileManager`, while the JVM's loader is a different API; bytes must be exposed via the file manager's input/list paths.
12. No: URI identifies a file object, binary name identifies a class, and `Path` is a filesystem path.
13. Module-oriented locations can differ from the singleton `CLASS_OUTPUT`, requiring support for `getLocationForModule`/module outputs.
14. No; loading/unloading depends on the classloader, object references, and GC.
15. No; a file manager is not a sandbox.
16. `List.of(path)` in the `Collection<Path>` overload; avoids the deprecated `Iterable<Path>` overload and mistaking `Path` as an iterable of its components.

## 17. Official Documentation Sources

- [Java SE 21 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getStandardFileManager`, `getTask`, standard manager reuse, and diagnostics.
- [Java SE 21 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): `File`/`Path` support, URIs, `getJavaFileObjectsFromPaths`, and `setLocationFromPaths`.
- [Java SE 21 — `ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): delegate constructor, forwarding methods, and overriding capabilities.
- [Java SE 21 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): SPI contract for sources/classes/resources, locations, output hints, originating files, `list`, `inferBinaryName`.
- [Java SE 21 — `JavaFileObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileObject.html): `Kind.SOURCE`, `Kind.CLASS`, and binary-name metadata.
- [Java SE 21 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): base class for creating custom source/output file objects.
- [Java SE 21 — `StandardLocation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardLocation.html): `CLASS_PATH`, `CLASS_OUTPUT`, `SOURCE_OUTPUT`, `MODULE_PATH`.
- [Java SE 21 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): managing structured diagnostics.
- [JDK 21 `javac` command specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-d`, `--class-path`, `--release`, `-proc:none`, and how class outputs/dependencies are located.
- [Java SE 21 — `ToolProvider`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html): how to obtain the system compiler.

**Conclusion:** `StandardJavaFileManager` is the built-in foundation for the compiler to read/write files, JARs, and classpath/module paths, and it can be reused across compilation tasks. `ForwardingJavaFileManager` is a decorator that lets you **replace a few operations** such as `.class` output generation while keeping all delegated functionality intact. When building a runtime compiler, distinguish **input sources**, **where class outputs are stored**, **where the compiler looks for dependencies**, **where the JVM loads classes**, and **the diagnostics channel**; getting each role right avoids most errors in dynamic compilation systems.