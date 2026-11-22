# JavaCompiler and the Components of javax.tools

Instead of always invoking the `javac` process from a terminal, Java provides a public **Compiler API** that lets a Java program control source compilation, collect diagnostics, choose where class files are read/written, and even supply source from an in-memory string. The primary API resides in the `javax.tools` package of the standard module `java.compiler`; the system compiler implementation typically resides in the JDK module `jdk.compiler`.

This is an article on **tooling programming with the compiler**, not learning basic Java syntax. We will understand the components and lifecycle of a compilation task, run Java 17+ examples compiling source on disk and in memory, receive errors via `DiagnosticCollector`, control the file manager, handle annotation processors, observe the AST when needed, and avoid risks when turning the compiler into an online service.

## 1. When to Use the Compiler API Instead of Invoking javac?

Using `javac` directly is usually the simplest:

~~~bash
javac --release 17 -d out src/demo/Hello.java
~~~

If your application needs to **invoke the compiler itself**, `JavaCompiler` is useful in these situations:

- An IDE/editor must compile a source snippet the user just typed and display errors by position and error kind.
- A grading tool or playground dynamically creates source code and needs to know whether compilation succeeded or failed.
- A custom build tool wants to split tasks and specify classpath, module path, release, and output directory in Java code.
- A code generator wants to verify whether generated `.java` output is valid.
- A static analysis tool wants to access syntax trees via the API of the `javac` implementation.
- A program needs to store source or compilation results in a backend other than regular files, via an appropriate file manager.

**Do not use the Compiler API merely to run a normal build** if Maven or Gradle already handles dependencies, caching, incremental compilation, testing, and packaging. The Compiler API provides **a single compilation run**, not a replacement for a build system.

Important distinction: calling `JavaCompiler` does not mean Java has "dynamically executable safe code". Compilation and execution are two separate activities, whereas annotation processors can execute code **during compilation itself**.

## 2. Map of Core Components

~~~text
                     Java program / IDE / tool
                                │
                 ToolProvider.getSystemJavaCompiler()
                                │
                                ▼
                      JavaCompiler instance
                                │
           ┌────────────────────┼──────────────────────┐
           │                    │                      │
           ▼                    ▼                      ▼
  Compilation Units       JavaFileManager       DiagnosticListener
  (JavaFileObject)             │                      │
           │           read source/class/JAR    receive ERROR/WARNING/NOTE
           │           write .class/.java              │
           └────────────────────┼──────────────────────┘
                                │
                    JavaCompiler.getTask(...)
                                │
                                ▼
                     CompilationTask.call()
                                │
                ┌───────────────┴─────────────────┐
                ▼                                 ▼
          Boolean success                Diagnostics + output
                │                                 │
             true/false                  class files / source generated
~~~

| Component | Package/type | Role |
| --- | --- | --- |
| `ToolProvider` | `javax.tools.ToolProvider` | Locates the platform-provided compiler or documentation tool |
| `JavaCompiler` | Interface | Creates compilation tasks and standard file managers; also has `run(...)` via `Tool` |
| `JavaCompiler.CompilationTask` | Interface | Represents **one** compilation task; configure and call `call()` |
| `JavaFileObject` | Interface | Abstracts a source/class/HTML/other file; not necessarily a file on disk |
| `FileObject` | Interface | General file abstraction; `JavaFileObject` is a specialization |
| `StandardJavaFileManager` | Interface | Standard file manager for File/Path/JAR, creates compilation units from paths |
| `JavaFileManager` | Interface | Mechanism for finding inputs and opening outputs for the compiler |
| `StandardLocation` | Enum | Logical locations such as `CLASS_PATH`, `CLASS_OUTPUT`, `SOURCE_PATH`, `SOURCE_OUTPUT`, `MODULE_PATH` |
| `Diagnostic` / `DiagnosticListener` | Interfaces | Represents/receives errors, warnings, notes, and source positions |
| `DiagnosticCollector` | Class | Built-in `DiagnosticListener` that collects diagnostics for later processing |
| `SimpleJavaFileObject` | Class | Convenient base class for source in a string or custom output |
| `ForwardingJavaFileManager` | Class | Wraps an existing manager and overrides selected operations |
| `Tool` / `OptionChecker` | Interfaces | General tool interface and option support level checker |

In Java 9+, the public **API** is in module `java.compiler`; the standard JDK **javac implementation** is in module `jdk.compiler`. These are two different modules. Both are distinct from the `java` process running the compiled program.

## 3. Locating the Compiler: ToolProvider and the null Case

Common entry point:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Runtime khong co system compiler");
}
~~~

This is a **snippet** placed inside a method, not a standalone class. On a full JDK containing `jdk.compiler`, the call typically returns the `javac` implementation. However, `getSystemJavaCompiler()` **can return `null`** if the environment does not provide a system compiler, such as a custom runtime image with `jdk.compiler` stripped out. Do not check for compiler presence by looking at the `java.version` string and assuming it is guaranteed.

Verify yourself with:

~~~bash
java -version
javac -version
java --list-modules
~~~

Running `java --list-modules` on a runtime that has the `jdk.compiler` module usually shows that module in the list. In a minimal runtime image, the compiler is not necessarily included. `javac -version` only succeeds when the compiler executable is actually installed and found on the environment PATH.

Distinguish two classes with the same name:

- `javax.tools.ToolProvider` has `getSystemJavaCompiler()` returning `JavaCompiler`.
- `java.util.spi.ToolProvider` belongs to the general service-provider API for tools by name; do not accidentally import the wrong one and try calling the other's method.

If the tool has a `module-info.java` file and only uses the `javax.tools` API, it needs to read module `java.compiler`:

~~~java
module my.build.tool {
    requires java.compiler;
}
~~~

A module that merely `requires java.compiler` to compile source **does not guarantee** the runtime image will always contain the `jdk.compiler` provider. Check the compiler instance at runtime and package the runtime image appropriately. If using `com.sun.source.util.JavacTask` to observe the compiler, the `jdk.compiler` module is also involved; see the section on the AST API.

## 4. Creating a Task: Understanding All Six Parameters of getTask

Simplified API declaration:

~~~java
JavaCompiler.CompilationTask getTask(
    java.io.Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
~~~

This is **an illustrative signature from JavaCompiler**, not a method you need to define yourself.

| Parameter | Meaning |
| --- | --- |
| `out` | Destination for tool messages that do not go through the listener; `null` uses the default destination |
| `fileManager` | Manages reading files, JARs, and writing output; `null` lets the compiler pick a standard file manager |
| `diagnosticListener` | Receives structured diagnostics; if `null`, the tool reports in its default manner |
| `options` | Sequence of option tokens such as `"--release", "17", "-d", "out"`; `null` means no extra options passed |
| `classes` | Class names for annotation processing according to tool convention; **not a regular source file list** |
| `compilationUnits` | `JavaFileObject` instances representing the actual `.java` sources to compile |

`CompilationTask task = compiler.getTask(...);` only **creates the task**; it does not compile yet. Call `task.call()` to execute the compilation and obtain a `Boolean` indicating success or failure.

Example using options properly:

~~~java
List<String> options = List.of("--release", "17", "-proc:none");
JavaCompiler.CompilationTask task =
        compiler.getTask(null, fileManager, diagnostics, options, null, units);
boolean success = task.call();
~~~

You need to declare `compiler`, `fileManager`, `diagnostics`, and `units` in a concrete context as in the complete example below. With `getTask`, source paths **are passed in `compilationUnits`**, rather than putting a filename string into options as when copying a shell command verbatim.

A `CompilationTask` **is single-use**. Do not call `call()` twice on the same task to recompile. If you need multiple compilation runs, create a new task; you can reuse the standard file manager **sequentially** to benefit from JAR caching where appropriate.

## 5. Complete Example: Compiling a .java File on Disk

Create a small project:

~~~text
compiler-api-demo/
├── DiskCompileDemo.java
├── src/
│   └── demo/
│       └── Hello.java
└── out/                      # created when running DiskCompileDemo
~~~

**`src/demo/Hello.java`:**

~~~java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from compiled code");
    }
}
~~~

**`DiskCompileDemo.java`:**

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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class DiskCompileDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need a JDK with jdk.compiler");
        }

        Path output = Path.of("out");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of("src/demo/Hello.java")));

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none"
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, units);

            boolean success = task.call();
            System.out.println("compiled=" + success);

            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                System.err.println(
                        diagnostic.getKind() + ": "
                                + diagnostic.getMessage(Locale.ROOT));
            }
        }
    }
}
~~~

From the `compiler-api-demo` directory, run:

~~~bash
javac --release 17 DiskCompileDemo.java
java DiskCompileDemo
java -cp out demo.Hello
~~~

With JDK 17+ containing a system compiler and valid source, the output of the executed commands is:

~~~text
compiled=true
Hello from compiled code
~~~

The lines above are **stdout from the two `java` commands combined in order**; the `javac DiskCompileDemo.java` command normally produces no stdout on success. If the toolchain emits warning diagnostics, the loop may additionally print to **stderr**; this simple example intentionally generates no warnings.

What actually happens:

1. `ToolProvider` obtains the available compiler.
2. `DiagnosticCollector` retains structured error/warning messages.
3. `StandardJavaFileManager` receives the source path and class output location.
4. `getTask` receives options `--release 17` and `-proc:none`, along with the JavaFileObject for `Hello.java`.
5. `task.call()` compiles the source; the compiler writes `out/demo/Hello.class`.
6. The `java -cp out demo.Hello` command **executes the bytecode in a separate step**; `task.call()` does not invoke main itself.

`-proc:none` is used in the demo to make behavior more deterministic, preventing external processors from running accidentally. In real builds that need annotation processors, configure them explicitly instead of disabling them.

## 6. StandardJavaFileManager: More Than a File List

`StandardJavaFileManager` supports reading `Path`/`File`, JARs, classpaths, source paths, and writing outputs. It is the default choice when working with ordinary source/JAR trees. Some important operations:

~~~java
manager.getJavaFileObjectsFromPaths(List.of(Path.of("src/demo/Hello.java")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(Path.of("out")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(Path.of("libs/util.jar")));
~~~

These three statements are a **snippet**, assuming `manager` has already been created and the paths exist. `CLASS_OUTPUT` specifies where `.class` files are written, whereas `CLASS_PATH` specifies where to look for dependency classes or JARs. Do not confuse `SOURCE_OUTPUT` with `CLASS_OUTPUT`: `SOURCE_OUTPUT` is for source files generated by annotation processors when `-s` or an equivalent configuration is present.

Some common locations:

| Location | Typical usage |
| --- | --- |
| `CLASS_PATH` | External libraries used for type resolution |
| `SOURCE_PATH` | Searching for Java sources when needed |
| `CLASS_OUTPUT` | Destination for `.class` files |
| `SOURCE_OUTPUT` | Destination for extra `.java` files generated by codegen |
| `MODULE_PATH` | Searching for named module dependencies |
| `ANNOTATION_PROCESSOR_PATH` | Locating and loading processors/dependencies in the classpath model |

You can choose **either approach**: configure locations via the file manager, or pass corresponding options such as `-classpath`, `--module-path`, `-d`, `-s`. Avoid duplicate and conflicting configurations between the manager and options; know which configuration takes precedence in the actual implementation.

`StandardJavaFileManager` implements `Closeable`. Use `try-with-resources` to release file handles and related resources. A standard file manager can be used for **multiple sequential compilation tasks**, but should not by default be used concurrently by multiple tasks across threads; synchronization design and thread safety must be evaluated separately.

**Source encoding:** the charset parameter in `getStandardFileManager(listener, locale, charset)` specifies how the file manager reads files. The example uses `StandardCharsets.UTF_8`. This differs from encoding of bytecode output: a class file is a binary format, not a UTF-8 text file.

## 7. DiagnosticCollector: Receiving Errors Programmatically

When code is invalid, `JavaCompiler` can emit diagnostics with properties such as:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`.
- `getSource()`: the file associated with the error; **may be `null`** when the error concerns options or environment.
- `getLineNumber()` and `getColumnNumber()`: line/column position, if available.
- `getStartPosition()`, `getEndPosition()`, `getPosition()`: position offsets; if unavailable, the value `Diagnostic.NOPOS` is used.
- `getCode()`: a compiler-implementation-dependent diagnostic code, which can be useful for tooling.
- `getMessage(Locale)`: message formatted for the locale, not an immutable error code.

Note: `DiagnosticCollector.getDiagnostics()` returns the list of diagnostics received by the collector, but **does not guarantee** that every piece of compiler output has a `Diagnostic` object: some messages that do not fit the diagnostic model may be written to the writer/default destination. Do not parse `getMessage()` wording as a stable error-code API.

### Runnable example: compile-time error from in-string source

File **`DiagnosticsDemo.java`**:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticsDemo {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String className, String code) {
            super(URI.create("string:///" + className + ".java"), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need jdk.compiler");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        String source = "public class Bad { int n = \"oops\"; }";

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, null)) {

            JavaFileObject input = new StringSource("Bad", source);

            boolean success = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(input)).call();

            boolean hasError = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

            System.out.println("compiled=" + success);
            System.out.println("hasError=" + hasError);
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 DiagnosticsDemo.java
java DiagnosticsDemo
~~~

Stdout:

~~~text
compiled=false
hasError=true
~~~

Because `int n = "oops";` is a **type mismatch**; the Java syntax is valid, yet attribution/type checking rejects it. The demo **does not print the full diagnostic sentence** to avoid depending on JDK/locale wording. To display it to users, iterate through `diagnostics.getDiagnostics()`, printing `getKind()`, filename, line/column, and message with null checks.

Note that `StringSource` provides a source file in **memory**; the compiler does not need a `Bad.java` file on disk. However, if compiling valid source in this example, the standard file manager may still emit class files to disk per default configuration; **in-memory source does not imply in-memory output**.

## 8. JavaFileObject and SimpleJavaFileObject: Source Need Not Be on Disk

`JavaFileObject` represents a compilation unit or class file in the compiler's model, supporting operations such as `getCharContent(boolean)` or `openInputStream()` appropriate to its `Kind`. Key `JavaFileObject.Kind` values include:

| Kind | Example |
| --- | --- |
| `SOURCE` | Java source content from a file or string |
| `CLASS` | Class file / bytecode output |
| `HTML` | HTML file in tool environments that support it |
| `OTHER` | Resources not belonging to the kinds above |

`SimpleJavaFileObject` is a base class for implementing the methods your data source actually supports. Source from a String can override:

~~~java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return sourceCode;
}
~~~

In this example, `sourceCode` is a field of type `String`. Since the compiler reads characters directly, the `ignoreEncodingErrors` flag has no role in decoding bytes from a source file as in a regular file manager.

Internal URIs typically take forms such as:

~~~text
string:///demo/Hello.java
mem:///demo/Hello.class
~~~

The URI must be valid and should reflect the package/class name and matching Kind; it does **not** have to point to an actual file on disk. If a public class is named `Hello`, ensure the compilation unit name matches, otherwise the compiler may report that the public class name does not match the filename.

Do not turn every file into a single `SimpleJavaFileObject` and assume the compiler resolves dependencies by itself: the file manager remains responsible for locating other classes/sources on the classpath/module path, while compilation units only describe the inputs fed to the task.

## 9. Compiling Entirely in Memory: Custom JavaFileManager

To keep both source **and bytecode** in memory, you need not only `SimpleJavaFileObject` as source, but also to **intercept where the compiler writes class output**. `ForwardingJavaFileManager` wraps the standard manager, overriding only the needed target operations.

Complete **`MemoryCompileDemo.java`** file:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
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
import javax.tools.ToolProvider;

public class MemoryCompileDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, ByteArrayOutputStream> compiled = new HashMap<>();

        MemoryManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {

            if (kind != JavaFileObject.Kind.CLASS) {
                throw new IllegalArgumentException("Expected class output");
            }

            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            compiled.put(className, bytes);

            URI uri = URI.create("mem:///" + className.replace('.', '/')
                    + kind.extension);

            return new SimpleJavaFileObject(uri, kind) {
                @Override
                public OutputStream openOutputStream() {
                    return bytes;
                }
            };
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need jdk.compiler");
        }

        String code = """
                package sample;
                public class Answer {
                    public static int value() {
                        return 42;
                    }
                }
                """;

        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(null, null, null)) {

            MemoryManager manager = new MemoryManager(standard);
            JavaFileObject source = new Source("sample.Answer", code);

            boolean success = compiler.getTask(
                    null, manager, null,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(source)).call();

            System.out.println("compiled=" + success);
            System.out.println("classFound="
                    + manager.compiled.containsKey("sample.Answer"));
            System.out.println("bytecodeNonEmpty="
                    + (manager.compiled.containsKey("sample.Answer")
                       && manager.compiled.get("sample.Answer").size() > 0));
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
~~~

Stdout:

~~~text
compiled=true
classFound=true
bytecodeNonEmpty=true
~~~

Explanation:

- `Source` presents `sample.Answer` as Java source via URI and `getCharContent()`.
- `MemoryManager` retains the output class by name; `getJavaFileForOutput(...)` returns a `JavaFileObject` on which the compiler can call `openOutputStream()` to write bytes.
- `MemoryManager` inherits most operations from `StandardJavaFileManager`, so platform classes/dependencies are still read using the built-in mechanism.
- Compiling internal source does not require creating `sample/Answer.java` on disk. In the demo `-d` is unnecessary because class output is handled by the custom manager.
- The `compiled` map holds the byte arrays after `call()`; the class file **is not automatically loaded into the JVM**.

**Limitations:** this is a demo for class output. A compiler pipeline can also emit sources/resources via annotation processing, so if you want "all output in-memory", handle all required output locations and file kinds (source, class, resource), not just `Kind.CLASS`. The demo includes `-proc:none` to bypass the annotation processing branch. Do not use an unbounded global map in a server accepting arbitrary inputs; large sources and outputs can exhaust memory.

To **execute** a class from a byte array, you need an appropriate `ClassLoader` (for example, a custom loader using `defineClass`) and an isolation policy. Merely having bytes in `compiled` does not invoke `Answer.value()`. **A custom ClassLoader is not a security sandbox**; do not run untrusted user code merely because you swapped the file manager.

## 10. Custom DiagnosticListener and Handling Error Positions

`DiagnosticCollector` is suitable when you want all diagnostics after `task.call()`. If you need to stream diagnostics per error, implement `DiagnosticListener<JavaFileObject>`:

~~~java
DiagnosticListener<JavaFileObject> listener = diagnostic -> {
    String file = diagnostic.getSource() == null
            ? "<no source>"
            : diagnostic.getSource().getName();

    System.err.println(
            diagnostic.getKind() + " " + file
                    + ":" + diagnostic.getLineNumber()
                    + ":" + diagnostic.getColumnNumber()
                    + " " + diagnostic.getMessage(Locale.ROOT));
};
~~~

This is a **snippet**; you need to import `javax.tools.DiagnosticListener` and `java.util.Locale`, and pass `listener` as the third argument to `getTask(...)`.

Position values may be absent; the number `-1` corresponds to `Diagnostic.NOPOS` in that case. When building an IDE, do not use position `-1` as an offset into a source buffer; perform bounds checks. `getSource()` can also be `null` for option/configuration diagnostics.

**Separate severity and policy:** `Kind.ERROR` typically causes compilation to fail; `WARNING` does not necessarily do so. A tool can pass `-Werror` to treat warnings as errors under its build policy. Do not assume `success=true` just because the collection has no `ERROR` without checking the result of `task.call()`.

**Be careful with messages:** locale, JDK version, and compiler implementation can change message text. User interfaces should display messages while avoiding classification logic based on fixed English phrasing. When testing, verify kind, position, code (when supported), and compilation result.

## 11. Tool's run(...) vs. getTask(...)

`JavaCompiler` extends `Tool`, which provides `run(InputStream in, OutputStream out, OutputStream err, String... arguments)`. It resembles CLI-style `javac` invocation: pass arguments as when invoking the tool and receive an **`int` exit code**.

Example **snippet** when the source file and output directory already exist:

~~~java
int exit = compiler.run(
        null,
        System.out,
        System.err,
        "--release", "17",
        "-d", "out",
        "src/demo/Hello.java"
);
System.out.println("exit=" + exit);
~~~

With valid source, typically `exit=0`. However, `run(...)` does not offer the same level of customization of `JavaFileObject`, `JavaFileManager`, and `DiagnosticCollector` as `getTask(...)`. If the tool needs structured errors, in-memory source, or custom class output, choose `getTask`.

| Criterion | `compiler.run(...)` | `compiler.getTask(...).call()` |
| --- | --- | --- |
| Invocation style | CLI-like, takes string arguments | Component API with file objects, manager, and listener |
| Result | `int` exit code | `Boolean` success/failure |
| Diagnostics | Primarily via output/error streams | Supports `DiagnosticListener`/`DiagnosticCollector` |
| In-memory source | Not the primary mechanism | Uses custom `JavaFileObject` |
| In-memory output | Not the primary mechanism | Uses custom `JavaFileManager` |
| Controlling annotation processors | Via arguments | Via options and `CompilationTask.setProcessors(...)` |
| Multiple runs | Re-invoke the tool | Create a new task each time; manager can be reused sequentially |

With `run(...)`, do not neglect path sanitization if arguments come from user input: options can control classpath, output, processor path, or filesystem access.

## 12. Annotation Processing via the Compiler API

`CompilationTask` supports `setProcessors(Iterable<? extends Processor> processors)` to configure **processor instances**, replacing javac's normal discovery mechanism when direct control is needed. `Processor` resides in `javax.annotation.processing`, inside module `java.compiler`.

**Illustrative snippet**, assuming class `MyProcessor` implements `Processor` and the task has not yet run:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics, options, null, units);
task.setProcessors(List.of(new MyProcessor()));
boolean success = task.call();
~~~

The processor must match the source language and annotations; do not assume calling setProcessors alone makes source with annotations valid. For processors discovered via service/provider mechanisms, you can select them using compiler options `-processor`, `-processorpath`, or `--processor-module-path` depending on artifact kind.

When a processor generates source via `Filer`:

- New sources can participate in subsequent processing rounds.
- `StandardLocation.SOURCE_OUTPUT`/option `-s` determines where sources are written depending on the file manager.
- Classes are compiled into `CLASS_OUTPUT`/`-d` in normal compilation mode.
- `-proc:only` performs annotation processing only, without proceeding to normal bytecode compilation.
- `-proc:none` disables processing — useful for a compiler playground that must avoid running processors unintentionally.

**Security:** an annotation processor is Java code that can execute inside the compiler process, with permissions to read/write files or cause side effects depending on the environment. Do not feed processor JARs from untrusted sources into a compiler server. Starting in JDK 23, the implicit annotation processing activation mechanism changed toward requiring more explicit configuration; tools should select processors explicitly rather than assuming any JAR on the classpath will run automatically.

## 13. Modules, Classpath, and Target Release in the API

The options passed to `getTask` serve the same purpose as `javac` options:

~~~java
List<String> options = List.of(
        "--release", "17",
        "--class-path", "libs/dependency.jar",
        "-d", "out",
        "-proc:none"
);
~~~

This is a **snippet** requiring the corresponding paths to already exist. You can also configure `StandardJavaFileManager` via `StandardLocation.CLASS_PATH` and `CLASS_OUTPUT`. When using named modules, options such as `--module-path`, `--module-source-path`, and appropriate outputs must match the project structure. If the app is in a named module, the module using the `javax.tools` API needs `requires java.compiler`; if the tool reads ASTs in `com.sun.source.*`, the extended API/implementation in `jdk.compiler` may also need to be declared in the descriptor.

**Compiler runtime differs from target release**:

- Running the tool with JDK 21 and `--release 17` means **the compiler implementation runs in Java 21**, while source/output conform to Java 17 according to javac's support.
- Annotation processors also run in the compiler JDK environment; a processor requiring JDK 21 cannot run when processing on JDK 17, regardless of whether the target source is Java 8 or 17.
- `--release 17` controls the Java language, class-file version, and Java platform APIs; it **does not automatically downgrade external dependency JARs to Java 17**.
- `ToolProvider.getSystemJavaCompiler()` is not an arbitrary cross-compiler: the list of supported releases depends on the actual JDK implementation.

To verify the release target on disk output, use `javap -verbose` to inspect the class-file major version. For Java 17, the major version is **61**. However, a major 61 class file does not prove the whole program is compatible with a Java 17 runtime if dependencies require a higher class version or different runtime APIs/modules.

## 14. Observing the Compiler via JavacTask When AST Access Is Needed

`javax.tools.JavaCompiler` is the portable API for compilation services. When using the JDK's **system javac**, the returned task object can usually be treated as `com.sun.source.util.JavacTask`, which belongs to the public tooling API in the `jdk.compiler` module.

Example **snippet for the javac implementation**, not guaranteed to apply to every custom compiler provider:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics, options, null, units);

if (task instanceof com.sun.source.util.JavacTask javacTask) {
    javacTask.setTaskListener(new com.sun.source.util.TaskListener() {
        @Override
        public void started(com.sun.source.util.TaskEvent event) {
            System.out.println("START " + event.getKind());
        }

        @Override
        public void finished(com.sun.source.util.TaskEvent event) {
            System.out.println("END " + event.getKind());
        }
    });
}

boolean success = task.call();
~~~

`TaskEvent.Kind` includes high-level events such as `PARSE`, `ENTER`, `ANALYZE`, `GENERATE`, `ANNOTATION_PROCESSING`, `ANNOTATION_PROCESSING_ROUND`. Do not equate events with every internal javac pass or assume every file has exactly one event of each kind.

`JavacTask` also provides APIs for syntax tree analysis, such as `parse()`, `analyze()`, and `Trees` in appropriate workflows. This is **a deeper compiler tooling area**, and if you actively call phase methods, you must understand task lifecycle. **Do not** invoke `parse()/analyze()` and also drive `call()` as two independent paths without understanding task state.

Using internal implementation classes `com.sun.tools.javac.*` is a further step, often requiring module-opening options and prone to change across JDKs. If your needs are simply compiling and displaying errors, prefer `javax.tools`.

## 15. CompilationTask and Program Errors: Limits of Boolean success

When `task.call()` returns `true`, we only know **the compilation pass reported success** according to the compiler. This does **not** mean:

- The `main` method has been executed.
- The bytecode has been test-loaded by the JVM with all runtime dependencies.
- The program has no logic bugs, deadlocks, NPEs, or environment errors.
- Every annotation processor is "correct" according to business rules.
- The output has been packaged into a JAR or deployed.

When `task.call()` returns `false`, compile diagnostics are typically present; retrieve them to explain the failure. However, **exceptions** raised by the file manager, invalid options, processors, or system failures may be thrown instead of returning `false` in some cases. Do not conflate every exception from compiler tool code with "normal source code errors".

A well-designed service should distinguish states:

| Status | Meaning |
| --- | --- |
| `COMPILED` | `call() == true` and output processed successfully |
| `SOURCE_ERROR` | `call() == false` and diagnostics report source errors |
| `CONFIG_ERROR` | Option, classpath, module path, or compiler unavailable |
| `TOOL_FAILURE` | Exception from processor, manager, or compiler infrastructure |
| `RUNTIME_FAILURE` | Only when the app is executed separately and encounters an error |

If a compiler server accepts multiple requests, each request should have its own diagnostics, output, timeout/quota, and clear concurrency policy. Use a new `CompilationTask` per request; do not share mutable collectors and file managers across concurrent requests without proven thread safety.

## 16. Sequential Compilation Runs and File Manager Caching

By contract, a standard file manager may be reused across **multiple sequential compilation tasks**. The benefit can be reduced JAR metadata reading or filesystem scanning; there is no guarantee it will be faster in every scenario.

Idea (Java pseudocode, not a standalone class):

~~~java
try (StandardJavaFileManager manager =
         compiler.getStandardFileManager(null, null, null)) {

    for (BuildRequest request : requests) {
        Iterable<? extends JavaFileObject> units =
                manager.getJavaFileObjectsFromPaths(request.sources());

        JavaCompiler.CompilationTask task = compiler.getTask(
                null, manager, null, request.options(), null, units);

        boolean ok = task.call();
        // Record the result and diagnostics for each request.
    }
}
~~~

`BuildRequest` is an **imaginary model type** to illustrate the loop and does not exist in the JDK; to run, you must define it yourself. If requests use different classpaths or output locations, update the file manager/task configuration accordingly and prevent old outputs from affecting new runs.

**Do not** reuse a single `CompilationTask` for multiple `call()` invocations. **Do not** assume a standard file manager can be shared across parallel compiler calls on multiple threads. Depending on design, using a separate file manager per request can be safer and simpler.

## 17. Performance, Resource Management, and Security

Compiling code can consume significant CPU, RAM, file descriptors, and time, even when the source contains no infinite loops. A system allowing users to upload/enter Java code should consider:

1. **Limit source size and file count**; validate encoding, URIs, and package/class names.
2. **Restrict permitted options**: do not allow arbitrary input to control `-processorpath`, `-d`, `--patch-module`, `-J`, or unauthorized system paths.
3. **Dependency policy**: download JARs from trusted sources, pin versions, and audit licenses and vulnerabilities.
4. **Resource limits**: worker processes/isolated environments with reasonable CPU, memory, disk, and time quotas. A Java thread is not a sandbox boundary.
5. **Disable annotation processing when not needed** with `-proc:none` to reduce the risk of uncontrolled processor execution.
6. **Do not execute post-compile code** in the same process as sensitive resources if the code comes from an untrusted source; use a dedicated isolated environment.
7. **Isolate output per request**, avoiding overwriting class files of other requests; clean temporary outputs according to policy.
8. **Do not trust `ClassLoader` as a sandbox**. Real security must rely on OS/container-level isolation and appropriate constraints; the Java Security Manager is no longer a reliable solution in modern JDKs.
9. **Collect diagnostics safely**, avoiding excessive log output or leaking absolute paths/secrets from the build environment.
10. **Report the succeeded stage accurately**: compile-only, test, execution, packaging, and deployment are distinct states.

If you must use the API in production, define clear policies for each source tier: trusted (internal tools), semi-trusted (controlled user plugins), or untrusted (public playgrounds). Configuration and isolation levels will differ significantly.

## 18. Common Errors and Troubleshooting

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime image lacks `jdk.compiler` | Check the actual JDK, module image, and toolchain |
| `getTask(...)` reports invalid option | Wrong option token or conflicting `--release`/`--source` | Check `javac -help`, task options, and compiler version |
| `call() == false` | Source syntax/type/import errors | Read `DiagnosticCollector` and source locations |
| `getSource() == null` in diagnostic | Error not tied to a specific source | Allow nullable source; do not call `toUri()` immediately |
| Compiled successfully but `.class` missing from expected path | `CLASS_OUTPUT`/`-d` or custom file manager | Check output location and provider implementation |
| In-memory source yet class appears on disk | Only custom input; output still handled by standard manager | Override `getJavaFileForOutput` if in-memory output is needed |
| Class has bytecode but cannot run | Class not loaded, wrong runtime classpath/dependencies | Separate compilation and execution phases |
| `ClassCastException` casting task to `JavacTask` | Compiler provider is not a compatible javac implementation | Check `instanceof`; avoid blind casting |
| Processor runs unexpectedly | Processor discovery/configuration in the environment | Use `-proc:none` or a controlled processor path |
| File handle leaks or locked JARs | Forgot to close `StandardJavaFileManager` | Use `try-with-resources` and a clear lifecycle |
| Encoding errors on non-ASCII source | Inconsistent charset | Specify UTF-8 rather than relying on the default charset |
| Errors compiling multiple requests concurrently | Unsafe sharing of mutable manager/collector/task | Isolate state or synchronize according to contract |
| Old output classes "mask" new errors | Output not isolated or cleaned | Separate directory per request; record build artifacts |

Not every failure requires changing compiler options. Many issues stem from **file manager locations**, the runtime image, dependencies, or confusing the compile phase with runtime. Start debugging with a small valid source, a defined output directory, and structured diagnostics.

## 19. Practical Working Checklist with javax.tools

- Have a real **JDK/compiler implementation**, not merely assumed from a version string.
- Distinguish `javax.tools.ToolProvider` from `java.util.spi.ToolProvider`.
- Create a valid `JavaFileObject` for each compilation unit with accurate source file names/packages.
- Use `StandardJavaFileManager` when sources/targets are regular files/JARs; customize `ForwardingJavaFileManager` only when extending behavior.
- Configure classpath/module path, `--release`, and output locations consistently.
- Pass source units into the last parameter of `getTask`; do not treat `classes` as a source filename list.
- Provide a `DiagnosticCollector` or listener for messages; check `getSource()`/`NOPOS` before using them.
- Call `call()` **once per task**; check the `Boolean`, exceptions, and output.
- Close the file manager and resources; do not share mutable state across threads uncontrollably.
- Configure annotation processing explicitly; disable with `-proc:none` if not needed.
- With in-memory sources, decide **where output will go**; custom input does not imply custom output.
- Do not treat successful compilation as having tested/run the program or having a sandbox.
- Test on the exact JDK, classpath, module graph, and runtime where the tool will be deployed.

## 20. Self-Check Questions

**Question 1.** Does `ToolProvider.getSystemJavaCompiler()` returning `null` mean the Java source is wrong?  
**Answer:** No. That is an environment condition where no system compiler is provided; typically a runtime image/JDK with `jdk.compiler` is needed.

**Question 2.** In `getTask(out, manager, listener, options, classes, units)`, is the filename `Hello.java` passed in `classes` or `units`?  
**Answer:** Create a `JavaFileObject` from the source and pass it in `units`. `classes` is not a substitute parameter for regular compilation units.

**Question 3.** Why does `call() == true` not mean the program runs properly?  
**Answer:** The compiler API generates class files; the JVM has not necessarily loaded/launched the classes and dependencies yet.

**Question 4.** How are `DiagnosticCollector` and `DiagnosticListener` related?  
**Answer:** `DiagnosticCollector` is a `DiagnosticListener` implementation that collects `Diagnostic` instances into a list, whereas a custom listener can handle each error immediately.

**Question 5.** Is it possible to compile source from a string while class files are still emitted to disk?  
**Answer:** Yes. An in-memory `SimpleJavaFileObject` input is independent of the output manager; without customizing output, the standard manager can still write to disk.

**Question 6.** To write bytecode into a `Map<String, byte[]>`, what point needs to be customized?  
**Answer:** The `JavaFileManager`—usually overriding `getJavaFileForOutput` via `ForwardingJavaFileManager` and returning a `JavaFileObject` with an appropriate `openOutputStream()`.

**Question 7.** Should `task.call()` be called multiple times on the same object?  
**Answer:** No. A task is for a single run only; create a new task, and you can reuse the standard file manager sequentially if appropriate.

**Question 8.** A compiler server receiving untrusted Java source has `-proc:none` enabled; is it completely safe?  
**Answer:** No. Disabling processors only reduces one code-execution vector; compilation still consumes resources and has numerous attack surfaces. If generated classes are executed, strict isolation is even more necessary.

**Question 9.** How can you observe `PARSE`/`GENERATE` events when using javac?  
**Answer:** With system javac, you can use `JavacTask`/`TaskListener`; it is a high-level observation API, not a universal API across every compiler provider.

## 21. Key Takeaways and Official Documentation

**`JavaCompiler`** creates compiler tasks; **`JavaFileObject`** describes source/class files; **`JavaFileManager`** determines how files are located/written; **`DiagnosticListener`**/`DiagnosticCollector` handle errors; **`CompilationTask.call()`** executes compilation. Keep **compile inputs**, **compiler options**, **class output**, **diagnostics**, and **runtime execution** cleanly separated.

If you only need to compile Java sources on disk, use `StandardJavaFileManager`. If the source is a String, use `SimpleJavaFileObject`. If bytecode must also stay in memory, use a custom `JavaFileManager`. If observing AST/phases, check the `JavacTask` API in the `jdk.compiler` module when supported by the implementation. Do not treat compilation success as a guarantee of runtime correctness or security isolation.

Official sources for deeper study:

- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html).
- [ToolProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html).
- [StandardJavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html).
- [JavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html).
- [SimpleJavaFileObject — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html).
- [JavacTask — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html).