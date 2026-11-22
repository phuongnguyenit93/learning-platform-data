# Configuring Dependencies and Output Locations for a Custom File Manager

In the Java Compiler API, placing source code in RAM only solves the **input** side of the compilation process. To build a useful compiler tool, you also have to tell the compiler **where to find dependencies** and **where to write generated sources, class files, and resources**. `JavaFileManager` is the interface responsible for both tasks. `StandardJavaFileManager` manages normal files/JARs; `ForwardingJavaFileManager` allows customizing specific input/output points while keeping the built-in path resolution capabilities.

The most common pitfall: configuring `CLASS_PATH` lets `javac` **know about a class during compilation**, but does not automatically make that class appear in the **runtime ClassLoader**. Similarly, a `JavaFileObject` holding source in memory does not mean output bytecode is also in memory. You must clearly distinguish input, resolution, output, and runtime.

This Knowledge lesson uses Java 17+ and provides a runnable project with a **dependency on disk, application source in RAM, application bytecode in RAM, and a custom ClassLoader for test execution**; it then expands to multiple compilation passes, annotation processing, modules, resources, and error handling.

## 1. Four questions to answer before writing a file manager

Each compilation pass needs to answer:

1. **Where do compilation units come from?** `.java` files on disk, `String` values, a database, an editor buffer, or a virtual filesystem?
2. **Where are dependencies found?** Platform APIs, classpath, module path, source path, or compiled class files in memory from a previous pass?
3. **Where is output written?** A `.class` directory on disk, byte arrays in RAM, a JAR, a generated-source directory, or another artifact store?
4. **Who loads and uses the bytecode after compilation?** A separate JVM running via `-cp`/`--module-path`, or a custom ClassLoader inside a controlled process?

Diagram:

~~~text
JavaFileObject (SOURCE)
  ├─ source file on disk
  └─ source text in RAM
                 │
                 ▼
         JavaCompiler.getTask(...)
                 │
         JavaFileManager
           ├─ CLASS_PATH / MODULE_PATH
           │     └─ reads .class, .jar, module libraries
           ├─ SOURCE_PATH
           │     └─ locates dependent sources if configured
           ├─ ANNOTATION_PROCESSOR_PATH
           │     └─ loads processors for the compiler
           └─ output hooks
                 ├─ CLASS_OUTPUT → .class on disk or RAM
                 ├─ SOURCE_OUTPUT → generated .java
                 └─ resources from annotation processors
                 │
                 ▼
            class files / bytes
                 │
                 ▼
         ClassLoader or runtime JVM
                 ├─ application bytecode
                 └─ dependencies needed at runtime
~~~

**Not every case has a single output location.** A processor may generate sources and resources, the compiler emits multiple classes from one compilation unit, a named module can have per-module outputs, and an application may need both directory/URL dependencies and RAM bytecode.

## 2. Main APIs in javax.tools

| API | Responsibility |
| --- | --- |
| `JavaCompiler` | Creates compilation tasks and standard file managers |
| `JavaCompiler.CompilationTask` | Represents a single compilation pass, calling `call()` once |
| `JavaFileObject` | Abstracts a source or class file; includes `Kind.SOURCE`/`Kind.CLASS` |
| `SimpleJavaFileObject` | Base class for custom source/string/class output implementations |
| `JavaFileManager` | Looks up inputs, receives outputs, resolves names, manages locations |
| `StandardJavaFileManager` | Standard file manager for `Path`, `File`, JARs, and output directories |
| `ForwardingJavaFileManager<T>` | Wraps another manager and overrides required operations |
| `StandardLocation` | Standard location names such as `CLASS_PATH`, `CLASS_OUTPUT` |
| `DiagnosticCollector` | Receives structured errors, warnings, and position information |
| `ToolProvider` | Retrieves the compiler provided by the runtime |

The public API belongs to the `java.compiler` module. On mainstream JDKs, the `javac` implementation belongs to the `jdk.compiler` module. `ToolProvider.getSystemJavaCompiler()` **can return `null`** if the runtime image lacks the system compiler; check this before creating a file manager.

Example of obtaining the compiler:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Requires a JDK with jdk.compiler");
}
~~~

This is a **snippet** requiring imports of `JavaCompiler` and `ToolProvider` from `javax.tools`, not a standalone file. A successful compiler task returns the compilation result; it **does not automatically run the `main` method**.

## 3. Distinguishing input and output locations

`StandardLocation` defines commonly used locations:

| Location | Read or Write? | Purpose |
| --- | --- | --- |
| `CLASS_PATH` | Read | Finds `.class` and JAR classpath entries, including library dependencies |
| `SOURCE_PATH` | Read | Finds dependent sources when the compiler is allowed to look them up |
| `MODULE_PATH` | Read | Finds named/automatic module dependencies |
| `CLASS_OUTPUT` | Write | Destination for emitting `.class` files for sources being compiled |
| `SOURCE_OUTPUT` | Write | Destination for `.java` files generated by annotation processors |
| `ANNOTATION_PROCESSOR_PATH` | Read | Finds processors and their dependencies to run processors |
| `ANNOTATION_PROCESSOR_MODULE_PATH` | Read | Finds processor providers as modules |
| `PLATFORM_CLASS_PATH` | Read in appropriate configurations | Platform classes in matching models/JDKs; do not set arbitrarily when using modern release/module APIs |

`CLASS_OUTPUT` and `SOURCE_OUTPUT` **do not replace each other**. With annotation processing, a compilation pass can generate `generated/demo/Helper.java` in source output and `classes/demo/Helper.class` in class output.

Most users should start with `StandardJavaFileManager`. Only write a custom manager when you genuinely need to alter input/output, such as saving bytecode into byte arrays to pass to a runtime engine.

## 4. Configuring dependencies using StandardJavaFileManager

`StandardJavaFileManager` allows associating search paths with a location:

~~~java
Path depClasses = Path.of("deps/classes").toAbsolutePath();
Path outputDir = Path.of("out").toAbsolutePath();

Files.createDirectories(outputDir);

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(depClasses)
);

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(outputDir)
);
~~~

This is a **snippet**, assuming `Path`, `Files`, `List`, and `StandardLocation` are imported and `standardManager` is created. The `CLASS_PATH` line points the compiler to the directory containing `.class` packages. The classpath directory can be replaced with a real JAR, or a list of multiple entries. Each entry is a separate `Path`.

**For standard output locations on disk, pass exactly one directory** to `setLocationFromPaths(CLASS_OUTPUT, ...)`, and create the directory beforehand. Input search locations can accept multiple path entries; an output directory is not a list to alternate writes across.

Suppose the dependency resides at:

~~~text
deps/classes/
└── library/
    └── Greeter.class
~~~

When the source writes `import library.Greeter;`, the compiler locates the class through `CLASS_PATH`. If the dependency is absent from the location and cannot be found elsewhere, importing the type name may report `package library does not exist` or `cannot find symbol`.

**The classpath path must point to the package root**, which here is `deps/classes`, not directly `deps/classes/library` or `Greeter.class`.

### When there are multiple dependencies

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(
                Path.of("deps/classes"),
                Path.of("libs/json.jar"),
                Path.of("libs/util.jar")
        )
);
~~~

This is a snippet for existing paths. Because the API accepts a `Path` collection, you do **not** concatenate strings using `:` or `;` into a single `Path`. By contrast, if using the `--class-path` option, you must use the OS-dependent separator. Pick one clear configuration mechanism rather than duplicating multiple sources of truth.

## 5. Configuring via compiler options or file manager?

There are two common approaches.

**Approach A — file manager locations:**

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(Path.of("deps/classes")));
standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(Path.of("out")));

List<String> options = List.of("--release", "17", "-proc:none");
~~~

**Approach B — compiler options:**

~~~java
List<String> options = List.of(
        "--release", "17",
        "-proc:none",
        "--class-path", "deps/classes",
        "-d", "out"
);
~~~

Both are **snippets**; in Approach B, `out` must be a suitable output directory and the paths must exist. Options are passed as the fourth parameter of `JavaCompiler.getTask(...)`, while sources must be supplied in the `compilationUnits` parameter. Do not put `.java` filenames into options as when calling the `javac` command line expecting the compiler to find source units automatically.

Do not mix `setLocationFromPaths(CLASS_OUTPUT, X)` with a conflicting `-d Y` option in the same task. An implementation may alter file manager locations when processing options, making it unclear where output is actually written. With a custom manager intercepting `CLASS_OUTPUT` to store in RAM, also avoid forcing `-d` on disk unless you intentionally designed how they combine.

### Do not confuse compile classpath with runtime classpath

If the compiler sees `deps/classes`, code using `library.Greeter` can compile successfully. However, when running via the launcher:

~~~bash
java -cp out app.Main
~~~

the runtime classpath in this command **does not contain `deps/classes`**. If the program needs `Greeter` and the class is not elsewhere, you may encounter `NoClassDefFoundError`. The dependency must be provided at runtime:

~~~bash
java -cp "out:deps/classes" app.Main
~~~

The `:` separator is for Linux/macOS shells; Windows uses `;`. This example assumes class files on disk; if `app.Main` only resides in RAM, `java -cp` cannot find it automatically.

## 6. Complete example: dependency on disk, application source and class in RAM

This example has **two distinct branches**:

1. Compile the library `library.Greeter` to the `deps/classes` directory using standard `javac`.
2. Run a Java program invoking `JavaCompiler`: it reads the app source from a `String`, locates the dependency in `deps/classes`, emits `app.Main` bytecode in RAM via `ForwardingJavaFileManager`, and then invokes the method through a custom ClassLoader that knows both the RAM bytecode and the dependency directory.

The example uses JDK 17+, requiring no Maven/Gradle or external libraries.

### 6.1. Directory structure

~~~text
memory-compiler-demo/
├── src/
│   └── library/
│       └── Greeter.java
├── MemoryCompileWithDependency.java
└── deps/
    └── classes/                # generated when building dependency
~~~

There is no need to create `app/Main.java` on disk because the app source content will be a Java text block inside the tool.

### 6.2. Dependency library: src/library/Greeter.java

~~~java
package library;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

The library imports no complex APIs; we can easily recognize missing-dependency errors and exact runtime results.

Compile using Bash from the project root:

~~~bash
mkdir -p deps/classes
javac --release 17 -d deps/classes src/library/Greeter.java
~~~

Afterward, `deps/classes/library/Greeter.class` exists. This file will serve as the dependency when the compiler compiles the in-RAM app source.

### 6.3. JavaCompiler tool: MemoryCompileWithDependency.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeSet;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class MemoryCompileWithDependency {
    static final class StringSource extends SimpleJavaFileObject {
        private final String source;

        StringSource(String className, String source) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    static final class MemoryClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        MemoryClassFile(String className, Kind kind) {
            super(URI.create("memory:///"
                    + className.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] getBytes() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, MemoryClassFile> outputs = new HashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                MemoryClassFile output = new MemoryClassFile(className, kind);
                outputs.put(className, output);
                return output;
            }

            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            outputs.forEach((name, file) ->
                    result.put(name, file.getBytes()));
            return result;
        }
    }

    static final class OutputClassLoader extends URLClassLoader {
        private final Map<String, byte[]> compiled;

        OutputClassLoader(URL dependencyUrl, Map<String, byte[]> compiled) {
            super(new URL[] {dependencyUrl},
                    ClassLoader.getPlatformClassLoader());
            this.compiled = compiled;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = compiled.get(name);
            if (bytes != null) {
                return defineClass(name, bytes, 0, bytes.length);
            }
            return super.findClass(name);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is required");
        }

        Path dependency = Path.of("deps/classes").toAbsolutePath();
        if (!Files.isDirectory(dependency)) {
            throw new IllegalStateException("Compile library dependency first");
        }

        String source = """
                package app;
                public class Main {
                    public static String run() {
                        return library.Greeter.hello("Ada");
                    }
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        Map<String, byte[]> bytecode;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, null)) {

            // Dependencies used at compile time:
            standard.setLocationFromPaths(
                    StandardLocation.CLASS_PATH, List.of(dependency));

            MemoryFileManager manager = new MemoryFileManager(standard);
            JavaFileObject input = new StringSource("app.Main", source);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(input));

            boolean success = task.call();
            System.out.println("compiled=" + success);

            if (!success) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + ": " + d.getMessage(Locale.ROOT));
                }
                return;
            }

            bytecode = manager.snapshot();
            System.out.println("memoryClasses="
                    + new TreeSet<>(bytecode.keySet()));
        }

        // Dependency resolution at runtime is a separate concern.
        try (OutputClassLoader loader = new OutputClassLoader(
                dependency.toUri().toURL(), bytecode)) {

            Class<?> app = loader.loadClass("app.Main");
            Object value = app.getMethod("run").invoke(null);
            System.out.println("result=" + value);
        }
    }
}
~~~

This is **a standalone Java class**. The inner classes implement the exact extension points needed:

- `StringSource` is a `SOURCE` compilation unit from a text block.
- `MemoryClassFile` holds the bytecode write stream using `ByteArrayOutputStream`.
- `MemoryFileManager` forwards all non-customized operations to the standard manager and **only intercepts `CLASS_OUTPUT` with kind `CLASS`**.
- `snapshot()` converts outputs into a map of class name → bytecode (`byte[]`).
- `OutputClassLoader` loads the app class from bytes and holds the URL for the `deps/classes` dependency.
- Annotation processing is explicitly disabled so the example does not need to handle generated sources/resources.

### 6.4. Execution commands and stdout

From the `memory-compiler-demo` root:

~~~bash
mkdir -p deps/classes
javac --release 17 -d deps/classes src/library/Greeter.java
javac --release 17 MemoryCompileWithDependency.java
java MemoryCompileWithDependency
~~~

Stdout from the last command:

~~~text
compiled=true
memoryClasses=[app.Main]
result=Hello, Ada
~~~

Conditions for the exact output: a JDK with the system compiler, a valid `deps/classes/library/Greeter.class`, and no interference outside the example. Successful `javac` commands typically print nothing to stdout. Any messages emitted by the compiler/diagnostics may go to stderr depending on the JDK and environment.

**Result explanation:**

1. When compiling the app, the library is looked up via `StandardLocation.CLASS_PATH`.
2. `getJavaFileForOutput(CLASS_OUTPUT, "app.Main", CLASS, ...)` is intercepted by the custom manager and writes bytes into RAM.
3. `snapshot()` shows the app class is available, with no `app/Main.class` file needing to be created on disk.
4. `OutputClassLoader` combines the `app.Main` class from RAM and `library.Greeter` from the dependency URL path.
5. The public static `run()` method is invoked via reflection, returning the exact string `Hello, Ada`.

**Security boundary:** the demo uses a custom ClassLoader to observe behavior, not as a sandbox. Do not load and run untrusted Java sources inside the same JVM containing sensitive resources. Annotation processors are also code executing during compilation, so the example disables `-proc` when unnecessary.

## 7. Why must dependencies be placed at both compile time and runtime?

These are two different worlds:

| Phase | Who Needs the Dependency? | Configuration in Demo |
| --- | --- | --- |
| Compile | `javac` must resolve `library.Greeter` in the app source | `standard.setLocationFromPaths(CLASS_PATH, ...)` |
| Run | JVM/ClassLoader must load `library.Greeter` when app code executes | `URLClassLoader` receives the `deps/classes` URL |
| Generated output | `javac` must write `app.Main` to the output JavaFileObject | `MemoryFileManager.getJavaFileForOutput` |
| Load app | ClassLoader must find the `app.Main` class | `OutputClassLoader.findClass` from byte map |

If you omit `CLASS_PATH` in the compiler task, the app fails to compile because the name `library.Greeter` cannot be resolved. If you keep only the compile path and omit the dependency URL in the loader, the app may compile, but fails when linking/executing the class (typically `NoClassDefFoundError`).

**Do not use the tool's context class loader or app class loader as a vague substitute for compile classpath**. The compiler locates types through the file manager and options; the runtime loader locates classes through class-loading delegation. The two mechanisms are related yet independent.

In Maven/Gradle projects, build tools typically organize compile classpath and runtime classpath differently according to dependency scopes. That is why a dependency declared `compileOnly` can be used for compilation but be missing at runtime if the application actually calls its classes.

## 8. Output classes can produce multiple files from one source

In the demo there is only `app.Main`. However, a compilation unit with nested classes, local classes, records, or synthetic helpers can produce **multiple** `.class` files. The file manager must treat the binary class name `className` on each `getJavaFileForOutput` call as a **separate output key**, rather than assuming one source corresponds to exactly one byte array.

Illustrative example:

~~~java
package app;

public class Outer {
    static class Nested {
    }
}
~~~

When compiling this source, there are typically at least `app.Outer` and `app.Outer$Nested`. Actual file/bytecode names are determined by the compiler according to code structure. A manager using `Map<String, MemoryClassFile>` can store multiple results, whereas a manager storing a single shared `ByteArrayOutputStream` will lose data or mix class files together.

In multi-module projects, **keying only by binary class name may not be enough** when modules require separate namespaces/outputs. Consider keying by module/location and binary name, using per-module locations, and not mixing outputs from unrelated compilation tasks.

### When to use byte[] instead of ByteArrayOutputStream?

While the compiler is writing, a stream receiving bytes is required. After the compiler closes the stream and `task.call()` completes, you should snapshot into `byte[]` (immutable in usage semantics) and drop unnecessary references where possible. Be careful not to expose mutable maps to other threads while compilation is still running.

## 9. If CLASS_OUTPUT on disk is desired, no override is needed

If the goal is **source in RAM yet class files on disk**, you only need `StringSource` and the standard file manager:

~~~java
Path classDir = Path.of("build/classes");
Files.createDirectories(classDir);

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(classDir));

JavaCompiler.CompilationTask task = compiler.getTask(
        null, standardManager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, List.of(new StringSource("app.Main", sourceText)));
boolean success = task.call();
~~~

This is a **snippet**, building on `StringSource` and the `compiler`, `diagnostics`, and `sourceText` variables declared as in the example lesson. With this configuration, `app/Main.class` is written by the standard manager to the corresponding directory. It differs from the demo in section 6, where `CLASS_OUTPUT` is intercepted to RAM.

If you have created a custom forwarding manager yet want **only some classes** written to RAM and others to disk, a precise output selection policy is required. A compiler can generate multiple class files itself; splitting output across RAM and disk depending on class name can complicate loading and packaging. It is usually better to choose **one consistent destination per compilation task**.

## 10. Generating sources with annotation processors: SOURCE_OUTPUT and CLASS_OUTPUT

When an annotation processor is enabled, it can call:

~~~java
JavaFileObject source =
        processingEnv.getFiler().createSourceFile("generated.Helper");
~~~

This is a snippet **inside a processor** with `processingEnv`. It is different from the compiler's class output.

With the standard file manager, to write generated sources to disk:

~~~java
Files.createDirectories(Path.of("build/generated"));
Files.createDirectories(Path.of("build/classes"));

standardManager.setLocationFromPaths(
        StandardLocation.SOURCE_OUTPUT,
        List.of(Path.of("build/generated")));

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/classes")));
~~~

The snippet above assumes an annotation processor is properly configured and `standardManager` is still open. `SOURCE_OUTPUT` is for generated `.java`; `CLASS_OUTPUT` is for `.class` files of both original and generated code.

### What if generated sources should also reside in RAM?

You need to manage **multiple output types**, not just override `CLASS_OUTPUT`:

- `getJavaFileForOutput(..., Kind.SOURCE, ...)`: for processors to create Java sources.
- The `SOURCE` `JavaFileObject` must support writing content, and then support reading it back so the compiler can parse/compile it in the next round (e.g., appropriate `openWriter`/`getCharContent`).
- `getJavaFileForOutput(..., Kind.CLASS, ...)`: keeps class bytecode in RAM.
- `getFileForOutput(...)`: for resources created by `Filer.createResource` in output locations.
- Operations to retrieve sources/classes if requested by the compiler, such as `getJavaFileForInput` and `list`, may need customization depending on the design.

**Never claim that overriding only `getJavaFileForOutput(..., CLASS, ...)` makes all annotation processing in-memory.** In section 6's example, `-proc:none` intentionally avoids processors generating sources and resources.

A practical design can **write generated sources/resources to a temporary directory** via the standard manager while keeping final class bytes in RAM. This hybrid approach is simpler than building a complete virtual filesystem if security and storage requirements permit.

## 11. Resources from processors: getFileForOutput is a separate branch

Annotation processors do not only generate sources or classes; they can create metadata files, such as a service descriptor:

~~~java
FileObject resource = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/services/example.Service");
~~~

This is an illustrative snippet, only valid when a processor is declared, `example.Service` exists for a real purpose, and the code handles file output appropriately. The resource is written using `openWriter()` or `openOutputStream()` per the API; calling `createResource` only creates the file object and does not write the complete content yet.

When keeping class outputs in RAM, **resources do not automatically appear in the class bytes map**. `getFileForOutput` is a different API from `getJavaFileForOutput`. If the application after compilation needs to load resources via `ClassLoader.getResourceAsStream` or Java `ServiceLoader`, the custom loader/bundle must also supply the corresponding resources.

A complete way to test the pipeline:

1. The processor creates source `generated.Helper` in `SOURCE_OUTPUT`.
2. The compiler creates `generated.Helper.class` in `CLASS_OUTPUT`.
3. The processor creates the `META-INF/services/...` resource.
4. At runtime, the loader can find both the class and the resource according to the deployed layout.

Step 2 succeeding alone is not enough to conclude that service loading will work.

## 12. Dependencies compiled into RAM in a previous pass

Advanced problem: task A compiles `lib.Api` into a byte map; task B compiles `app.Use` which has `import lib.Api;` while `lib.Api.class` **does not exist on disk**. In this case, overriding task A's output and passing the byte array as a ClassLoader to task B **is not enough**. Task B's compiler needs to see the class file as an **input dependency** inside the file manager.

~~~text
Task A:
  lib.Api.java ──compile──► map["lib.Api"] = bytes

Task B:
  app.Use.java
       │
       ├─ needs to resolve lib.Api name at compile time
       │   └─ file manager must expose lib.Api.class from map
       ▼
    compiled app.Use.class
~~~

Relevant extension points may include:

| Method | Effect |
| --- | --- |
| `getJavaFileForInput(location, className, CLASS)` | Returns an object representing a class file for a known specific name |
| `list(location, packageName, kinds, recurse)` | Lets the compiler list a package, especially when searching for types/imports |
| `inferBinaryName(location, file)` | Returns the proper binary name for a custom JavaFileObject |
| `hasLocation(location)` | Reports support for a location when required by the implementation |
| `getClassLoader(location)` | Supplies a loader for a location when needed (especially for processors or tooling) |
| `getJavaFileForOutput(...)` | Intercepts class/source output of the subsequent compilation pass |

The compiler does not always call only `getJavaFileForInput`: when analyzing wildcard imports or finding types in a package, it can use `list`/`inferBinaryName`. Therefore, a manager that both stores output bytes and acts as an **in-memory classpath for subsequent compilations** must implement the full resolution model, not just a single "map lookup by name" method.

### JavaFileObject template for input class bytes

~~~java
static final class BytecodeInput extends SimpleJavaFileObject {
    private final byte[] bytes;

    BytecodeInput(String binaryName, byte[] bytes) {
        super(URI.create("memory:///"
                + binaryName.replace('.', '/')
                + Kind.CLASS.extension), Kind.CLASS);
        this.bytes = bytes.clone();
    }

    @Override
    public InputStream openInputStream() {
        return new ByteArrayInputStream(bytes);
    }
}
~~~

This is a **snippet** for a nested class in a file importing `URI`, `InputStream`, `ByteArrayInputStream`, and `SimpleJavaFileObject`. It only solves reading the content of one class input; the file manager must still return it from `getJavaFileForInput` or `list`, while keeping the exact binary name/location.

If you do not yet need a completely in-memory compile chain, a simpler and more robust approach is to **pass sources A and B into the same compilation task**, or write dependency A to a temporary directory/JAR and use the standard manager for task B. Using a single task when the sources form a unified set usually lets the compiler handle type relationships without requiring a complex virtual file manager.

## 13. list and inferBinaryName: two methods very easy to miss

A file manager used for virtual dependencies cannot assume the compiler knows every class name from source. For example:

~~~java
import lib.*;
public class Use {
    lib.Api value;
}
~~~

When searching the `lib` package, the compiler may need to **list** available file objects and **infer the binary name** of each file. If the manager only overrides `getJavaFileForInput` for a specific name, wildcard imports or looking up nested/sibling types can fail unpredictably.

When overriding `list`, properly merge file objects from the underlying standard manager with objects in memory, avoiding duplicate ambiguous types. When overriding `inferBinaryName`, if the object was created by your manager, return the **actual binary name**, whereas file objects from the underlying manager must be delegated to the underlying manager.

Note that a binary name such as `lib.Outer$Nested` **differs** from the source name `lib.Outer.Nested` in certain contexts. Do not construct names from URIs using naive string concatenation and assume every class is top-level. Module-oriented locations complicate the problem further due to module identity and readability.

## 14. Post-compile ClassLoader does not automatically use JavaFileManager

A common misconception: because both the compiler and ClassLoader "find classes", many people try to pass `JavaFileManager` directly to the JVM to run code. However, they belong to two different APIs:

- `JavaFileManager` serves the compiler: finding source/class dependencies, creating output file objects.
- `ClassLoader` serves runtime: defining/loading classes and optionally finding resources.
- `ModuleLayer` and JPMS also have separate mechanisms for named modules at runtime.
- Launcher `java -cp` does not read an in-RAM bytecode map from another tool's process.

In section 6's example, `OutputClassLoader` receives a **snapshot** of class bytes and the dependency URL. When compiling a class with an in-RAM manager, there is no step that automatically puts the class into the parent class loader. Only when calling `loadClass`/reflection does the program use the output.

**Do not use a custom ClassLoader as a security boundary.** If compiling untrusted sources or executing the result, run inside an isolated environment with resource limits. `-proc:none` closes off one avenue of unintended code execution, but does not replace sandboxing and input validation policies.

## 15. Named modules differ from classpath applications

The main example uses the classpath/unnamed module for clarity. With JPMS, `--module-path` and module descriptors also govern resolution/readability/exports:

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.MODULE_PATH,
        List.of(Path.of("mods/libraries")));
~~~

This is a snippet for real module artifacts. When sources are named modules, the compiler may use module-specific locations and APIs such as `getLocationForModule`/`listLocationsForModules` and `setLocationForModule` as needed.

Configuring `MODULE_PATH` **is not the same** as `CLASS_PATH`. An automatic-module JAR and the same JAR on the classpath have different access models. A custom manager overriding `getJavaFileForOutput` for classpath `CLASS_OUTPUT` does not mean it already supports all output paths of multi-module compilation. For module outputs, you must properly handle the `Location` supplied by the compiler rather than forcing everything into a fake module.

A design principle: **if you do not yet need to customize module resolution, let StandardJavaFileManager manage the module path** and override only class output (as needed) for a compilation task. Re-implementing JPMS resolution inside a custom manager is major work and should not be done just to capture a few `byte[]` arrays.

## 16. Annotation processor path must be configured separately

A processor **runs at compile time**, not as a default runtime dependency of the app:

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.ANNOTATION_PROCESSOR_PATH,
        List.of(Path.of("libs/my-processor.jar")));
~~~

This is a snippet when a real processor artifact exists. Additionally, sources need annotation APIs on the appropriate compile classpath or module path. For modular processors, use `ANNOTATION_PROCESSOR_MODULE_PATH` or the `--processor-module-path` compiler option depending on the configuration.

Adding a processor JAR to `CLASS_PATH` does not necessarily activate the processor. Especially since JDK 23, `javac` no longer automatically runs processors by default merely upon discovering providers on the classpath; configure processing explicitly via `-processor`, processor path/module path, or the corresponding mode.

For a compiler service handling user sources, **disable processors** if unneeded:

~~~java
List<String> options = List.of("--release", "17", "-proc:none");
~~~

If the application requires annotation code generation, manage the processor version and output locations for generated sources/resources. Processors can execute code that reads/writes files while the compiler task runs, so they must be treated as trusted components of the build toolchain.

## 17. Design order for a good custom manager

Before overriding many methods, define a **policy table**:

| Data Type | Location/Kind | Source or Destination | Solution |
| --- | --- | --- | --- |
| Main source | `SOURCE` compilation units | RAM text editor | `StringSource` |
| Java platform API | System modules | JDK image | Delegate to standard manager |
| Third-party classes | `CLASS_PATH` | Directory/JAR | Standard manager location |
| Named module classes | `MODULE_PATH` | Modular JARs | Standard manager + descriptors |
| App bytecode | `CLASS_OUTPUT` + `CLASS` | RAM map | Override `getJavaFileForOutput` |
| Generated Java source | `SOURCE_OUTPUT` + `SOURCE` | Disk temp or memory | Delegate / intentional override |
| Generated resource | `CLASS_OUTPUT` + resource | Disk temp or RAM | `getFileForOutput`, loader/resource policy |
| Processor implementation | Processor path | Trusted JAR | Standard manager; explicit processor selection |
| Output loaded at runtime | ClassLoader | RAM bytecode + library URLs | Custom loader or packaging |

**Keep customization as minimal as possible.** If a system only needs to inspect class bytes from one task, the forwarding manager pattern in the demo is sufficient. If it needs incremental compilation, fully in-memory source/codegen/resources, a dynamic module graph, and multi-tier classloaders, design and test each API contract rather than adding ad-hoc overrides.

## 18. When must outputs be isolated per request?

In a compiler server, two users might both submit `package demo; public class Main { ... }`. If a global map keyed by `demo.Main` is used, the later compilation can overwrite bytes from the earlier request; the loader could load the wrong code and cause data leaks.

To avoid this:

1. Each compilation request has **its own manager, diagnostics, and output map**.
2. Create a separate `CompilationTask`, calling `call()` once.
3. Take output snapshots only after the task completes, avoiding reading objects while being written.
4. Create a new ClassLoader if executing results is needed, and close it when possible.
5. Do not keep all sources/bytecode in an unbounded cache; define TTL, quotas, and eviction.
6. Use keys combining request/build identity, module, and binary name if maintaining a shared store.
7. Enforce timeouts and memory/disk limits via process/container-level isolation for untrusted inputs.

`JavaCompiler` and file managers do not provide a built-in sandbox or complete incremental build system. Do not share the same task or mutable manager across threads without proving thread safety.

## 19. Diagnosing errors at the right layer

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `package library does not exist` | Compile classpath missing dependency | `CLASS_PATH`, JAR root, right `Path`, right package |
| `cannot find symbol` even though `.class` is in an older map | New task does not find in-memory input classes | `getJavaFileForInput`, `list`, `inferBinaryName`, or put in the same task |
| `compiled=true` yet no `.class` file on disk | `CLASS_OUTPUT` intercepted to RAM by design | `snapshot()`, output policy |
| In-memory source yet `.class` file appears on disk | Only source customized, output not intercepted | `getJavaFileForOutput`/`CLASS_OUTPUT` |
| `ClassNotFoundException: app.Main` | Loader lacks app bytecode | Map keys, loader delegation, class name |
| `NoClassDefFoundError: library/Greeter` | Runtime loader lacks dependency | Runtime URL/classpath/module graph |
| `UnsupportedClassVersionError` | Class from dependency/output requires higher Java than runtime | Class-file major version, `--release`, actual JDK |
| Generated `.java` is missing | Source output unconfigured or processor did not run | `SOURCE_OUTPUT`, processor path, rounds |
| `FilerException` | Processor creates duplicate files across rounds | Unique output names, output manager |
| ServiceLoader cannot find provider | `META-INF/services` resource missing at runtime | `getFileForOutput`, resources/URLClassLoader |
| File manager closed too early | Standard manager or streams already closed | `try-with-resources`, task lifecycle |
| JavaFileObject ignored by compiler | Invalid URI/kind/binaryName | URI, extension, `SOURCE`/`CLASS`, inferred name |
| Output location reports error | Directory does not exist or multiple output paths | Create directory first, correct cardinality |
| Compiler API returns `null` | Runtime image lacks `jdk.compiler` | `ToolProvider`, Java runtime image |

**Do not misread `compile=true` as `runtime=true`.** You must have a separate step to load, link, invoke, and verify actual output if the application needs to execute the generated classes.

## 20. Testing the custom manager as a component

A useful test suite does not cover only the happy path:

- **Valid source, valid dependency:** compiles successfully, output map has exact binary names, bytes are non-empty.
- **Missing compile dependency:** task fails and `DiagnosticCollector` contains an `ERROR` diagnostic.
- **Dependency missing only at runtime:** compilation task succeeds, but the appropriate runtime loader must error when the class is loaded/executed.
- **One source producing multiple classes:** map contains top-level and nested classes; each byte array has a valid class-file header.
- **Source syntax/type error:** task fails, do not publish the output map as a valid artifact.
- **Two sequential tasks:** manager or outputs are intentionally reset/isolated; do not reuse `CompilationTask`.
- **Processor generating sources/resources:** if supported, verify `SOURCE_OUTPUT`, `CLASS_OUTPUT`, and resources.
- **Unicode/encoding:** source strings with Unicode, source files using UTF-8 when read from disk.
- **Module dependencies:** verify against `module-info.java` and module locations if JPMS is in scope.
- **Concurrency:** distinct requests do not mix outputs and diagnostics; do not assume a shared manager is thread-safe.

When checking class bytes, you can read the first four bytes to check the `CAFEBABE` magic, but **a valid magic header does not prove the class is loadable or targets the right bytecode version**. You can use ASM, `javap` (if written to file), or an actual class loader/test as needed. Class-file version and dependency graphs must be verified separately.

## 21. Java 17+ implementation checklist

1. Clearly identify **compile units, dependencies, outputs, and runtime loader** before coding.
2. Verify `ToolProvider.getSystemJavaCompiler()` is non-null.
3. Prefer `StandardJavaFileManager` for files/JARs/modules on disk.
4. Configure `CLASS_PATH`/`MODULE_PATH` for dependencies; distinguish from the classpath of the JVM running the tool.
5. Configure `CLASS_OUTPUT`/`SOURCE_OUTPUT` per output policy and create directories if writing to disk.
6. When in-RAM bytecode output is needed, override `getJavaFileForOutput` for the right `Location`/`Kind`; delegate all other cases.
7. When RAM classes from a previous task are needed as dependencies for a later task, support **input/list/inferBinaryName**, not only class output.
8. When annotation processing is present, support generated sources and resources or explicitly disable with `-proc:none`.
9. Separate the **compiler manager** from the **runtime ClassLoader**; supply runtime dependencies independently.
10. Rely on diagnostics and the `call()` result, rather than inferring compile success from the number of files created.
11. Close the standard manager, streams, and URLClassLoader when appropriate; do not share tasks across threads.
12. Isolate compiler servers, restrict dependencies, and isolate runtime execution of untrusted sources.
13. Test on the exact JDK, `--release`, classpath/module path, and target runtime environments.

## 22. Self-check

**Question 1.** Source is supplied via `SimpleJavaFileObject.getCharContent`. Does bytecode automatically reside in RAM?  
**Answer:** No. Output is determined by `JavaFileManager` and output locations; the standard manager can write to disk.

**Question 2.** Do `StandardLocation.CLASS_PATH` and `StandardLocation.CLASS_OUTPUT` replace each other?  
**Answer:** No. One locates input class dependencies; the other writes class outputs.

**Question 3.** Dependency `library.Greeter` is already on the compiler classpath; why does running the app class still throw `NoClassDefFoundError`?  
**Answer:** The runtime JVM/ClassLoader does not have a search path to that dependency yet. The compile classpath is not automatically copied into the ClassLoader.

**Question 4.** To keep bytecode in RAM, what is the minimum method typically overridden in a forwarding manager?  
**Answer:** `getJavaFileForOutput(...)` for `StandardLocation.CLASS_OUTPUT` and `JavaFileObject.Kind.CLASS`, returning a JavaFileObject with an output stream.

**Question 5.** Why can `getJavaFileForInput` alone be insufficient when using in-RAM class bytes as a dependency for another task?  
**Answer:** The compiler may also need `list` and `inferBinaryName` when searching for types in packages, wildcard imports, or resolution.

**Question 6.** When a processor generates `Generated.java`, does storing only RAM class bytes already support full in-memory processing?  
**Answer:** Not yet. Generated sources must be writable/readable, output resources handled, and corresponding operations supported across rounds.

**Question 7.** Can `CLASS_OUTPUT` on disk accept a list of three folders and automatically distribute class files across them?  
**Answer:** Not in the standard manager; the standard output location requires exactly one directory path by contract.

**Question 8.** If the tool runs on Java 21 but passes `--release 17`, does the runtime ClassLoader automatically use Java 17?  
**Answer:** No. The compiler emits class files targeting Java 17, while the tool itself is running on Java 21. To confirm Java 17 runtime compatibility, run the artifact on an actual Java 17 runtime.

**Question 9.** Is a custom ClassLoader a sandbox for user code?  
**Answer:** No. It controls class-loading mechanics, and does not replace isolation and resource limits.

## 23. Key takeaways and official documentation

**`JavaFileManager` is the boundary between the compiler and data sources/output artifacts.** When customizing a manager, override only the behaviors that need to change and preserve `StandardJavaFileManager`'s resolution standards. `CLASS_PATH`/`MODULE_PATH` answers **“where does javac find dependencies?”**; `CLASS_OUTPUT`/`SOURCE_OUTPUT` answers **“where do the compiler and processor write outputs?”**; `ClassLoader` answers **“how does the JVM locate and execute classes after compilation?”**. These are three independent questions that must be configured consistently.

Official reference documentation:

- [JavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html).
- [StandardJavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html).
- [ForwardingJavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html).
- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html).
- [SimpleJavaFileObject — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html).
- [StandardLocation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardLocation.html).