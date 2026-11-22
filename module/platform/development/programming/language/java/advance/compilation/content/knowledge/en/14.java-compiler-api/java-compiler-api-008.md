# Managing File Managers, Resources, and Sequential Compilations with the Java Compiler API

When using `javac` from the terminal, the tool finds sources, libraries, and output destinations automatically. When embedding the Java compiler into **an IDE, build tool, code generator, test suite, or compilation service** via the `javax.tools` API, the application must explicitly manage those concerns: where Java files come from, where `.class` outputs are written, which resources are on the classpath, when outputs can be used, and the lifecycle of the file manager across **multiple sequential compilations**.

Core components:

- **`JavaCompiler`**: creates a compilation task to run the compiler.
- **`StandardJavaFileManager`**: maps `JavaFileObject`/`FileObject` to filesystem files, and manages source path, classpath, output locations, and compiler I/O resources.
- **`JavaFileObject` / `FileObject`**: abstracts Java source, bytecode, or resources that do not necessarily reside in a physical file.
- **`DiagnosticListener` / `DiagnosticCollector`**: receives warnings/errors of the compilation pass.
- **`JavaCompiler.CompilationTask`**: object representing **one** compile pass; not an object called repeatedly to compile multiple times.

This lesson uses Java 17+, including a complete example that **compiles a library in pass 1, compiles an application using that library in pass 2, writes a resource, and loads the results** using the standard API. Afterward, it analyzes common pitfalls when reusing a file manager, changing outputs, managing class loaders, and controlling resources.

## 1. Map of Important Interfaces

| Component | Main Responsibility | Practical Lifecycle |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Retrieves the compiler of the running JDK environment | Obtain before creating tasks; may return `null` |
| `JavaCompiler` | Creates tasks from options, file manager, and compilation units | One compiler can create multiple tasks |
| `JavaCompiler.CompilationTask` | Represents one compilation pass, has `call()` | **Create anew for each pass**; do not call `call()` a second time |
| `JavaFileManager` | File access interface for the compiler to locate classes, sources, and resources | Can have standard or custom implementations |
| `StandardJavaFileManager` | Standard file manager with APIs working with `Path`/`File` and locations | Reusable **sequentially**, needs proper `flush()`/`close()` |
| `JavaFileObject` | Java source/class, with `Kind.SOURCE` or `Kind.CLASS` | Input/output belonging to each task and file manager |
| `FileObject` | General file, including resources outside `.java`/`.class` | Read/write via reader, writer, or stream |
| `DiagnosticCollector<JavaFileObject>` | Collects diagnostics of one pass | Create separately per task to avoid mixing errors |
| `StandardLocation` | Standard location names: `CLASS_PATH`, `SOURCE_PATH`, `CLASS_OUTPUT`, `SOURCE_OUTPUT`... | Configured on the file manager according to purpose |

Flow of a compilation task:

~~~text
Source files / JavaFileObject
          |
          v
JavaCompiler.getTask(writer, fileManager, diagnostics, options, classes, units)
          |
          v
CompilationTask.call()
          |
          +--> FileManager: finds sources/classes/modules/resources
          |
          +--> Diagnostics: reports errors and warnings
          |
          +--> FileManager: writes .class and needed outputs
          |
          v
Result true / false
~~~

`task.call()` returns `Boolean.TRUE` when the compilation task succeeds per the tool contract. It is **not** synonymous with the classes already being loaded into the current JVM, the output files all being packaged into a JAR, or the program definitely running under every runtime classpath.

## 2. Initializing the Compiler from the Running JDK

Standard way to obtain the compiler:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "This runtime has no system Java compiler"
    );
}
~~~

The snippet above is a **fragment of a method**, not a standalone program.

`getSystemJavaCompiler()` can return `null` if the runtime does not provide the appropriate compiler module/tool. On Java 9+, the system compiler belongs to the JDK's `jdk.compiler` module; an application packaged with a minimal runtime image might omit that module. Install a full JDK or build a runtime image with the compiler if the program truly needs compilation at runtime.

Check the environment:

~~~bash
java -version
javac -version
~~~

Do not infer the compiler version from `System.getProperty("java.version")` without understanding modules/toolchains: with this API you use the compiler from the runtime loading it; an out-of-process build tool may use a different JDK.

### Why Use a File Manager Created by the Compiler?

~~~java
try (javax.tools.StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                null,
                java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8
        )) {
    // Create compilation tasks, read/write files.
}
~~~

- A `null` listener argument means the file manager does not receive a separate diagnostic listener at creation time.
- `Locale.ROOT` serves locale selection when messages are needed; it does not alter Java rules.
- `StandardCharsets.UTF_8` sets the standard file manager's encoding for character-based sources.
- `try-with-resources` invokes `close()` even when an exception occurs, avoiding holding file handles/JAR handles longer than necessary.

The standard file manager can cache JAR and file information to serve multiple **sequential** compilation tasks. Reusing it is usually more economical than creating new ones repeatedly, yet remember that its configured locations and caches still belong to the same manager. Do not assume this manager is thread-safe for multiple concurrent compilation tasks.

## 3. Locations Affecting Compilation and Resources

A `StandardJavaFileManager` maps `StandardLocation`s to paths or collections of paths:

| Location | Purpose | Illustrative Form |
| --- | --- | --- |
| `StandardLocation.CLASS_OUTPUT` | Output root for compiled classes | `build/classes` |
| `StandardLocation.SOURCE_OUTPUT` | Root for sources generated by annotation processors, if configured | `build/generated-sources` |
| `StandardLocation.CLASS_PATH` | Directories/JARs where the compiler searches for dependent classes | `build/classes`, `libs/tool.jar` |
| `StandardLocation.SOURCE_PATH` | Source root for the compiler to search for additional `.java` files | `src/main/java` |
| `StandardLocation.ANNOTATION_PROCESSOR_PATH` | Location to find annotation processors in appropriate configurations | `processors/processor.jar` |
| `StandardLocation.MODULE_PATH` | Location to find named modules | `mods`, `libs/module.jar` |
| `StandardLocation.PLATFORM_CLASS_PATH` | Platform classes in appropriate configurations; semantics vary by JDK | Should not be customized arbitrarily |

With the `Path`-based API:

~~~java
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        java.util.List.of(classesDirectory)
);
manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        java.util.List.of(classesDirectory, dependencyJar)
);
~~~

These two calls are a **fragment inside a method**, assuming `manager`, `classesDirectory`, and `dependencyJar` are all valid. The `classesDirectory` path must be the root containing the package tree of `.class` files. For example:

~~~text
build/classes/
└── example/
    ├── lib/Messages.class
    └── app/App.class
~~~

For the compiler to find `example.lib.Messages`, put **`build/classes`** on `CLASS_PATH`, not `build/classes/example/lib`. For the JVM to run `example.app.App`, the runtime classpath must also point to the corresponding root.

### Use Options or Configure on the File Manager?

There are two common ways:

- Pass CLI-style options such as `-d`, `-classpath`, `--release` to `compiler.getTask(...)`.
- Configure locations directly via the `StandardJavaFileManager.setLocationFromPaths(...)` API.

**Do not configure conflicting values for the same location in both ways** in one task. When using the file manager API, prefer one place as the source of truth for output paths, compile classpath, and module path. Language options such as `--release 17`, `-encoding UTF-8` can be passed separately.

## 4. Complete Example: Compiling in Two Passes, Reusing the File Manager

The following experiment requires only **JDK 17+** and a single external Java file named **`CompileTwiceDemo.java`**. The program:

1. Creates a temporary directory and sources for `example.lib.Messages` and `example.app.App`.
2. Uses a `StandardJavaFileManager` with `CLASS_OUTPUT` pointing to the `classes` directory.
3. Creates the first task to compile `Messages.java`.
4. Calls `flush()` on the manager, then adds the `classes` directory to `CLASS_PATH`.
5. Creates a **new task** compiling `App.java`, which depends on `Messages.class` from the previous pass.
6. Creates the resource `config/flag.txt` via the file manager inside `CLASS_OUTPUT`.
7. Closes the manager, and creates an isolated `URLClassLoader` to run `App.main` and read the resource.

**Complete `CompileTwiceDemo.java` file:**

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompileTwiceDemo {
    private static Path writeSource(
            Path sourceRoot, String relativeName, String source)
            throws Exception {
        Path file = sourceRoot.resolve(relativeName);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
        return file;
    }

    private static boolean compile(
            JavaCompiler compiler,
            StandardJavaFileManager manager,
            Path source) {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        Iterable<? extends JavaFileObject> units =
                manager.getJavaFileObjectsFromPaths(List.of(source));

        JavaCompiler.CompilationTask task = compiler.getTask(
                null,
                manager,
                diagnostics,
                List.of("--release", "17", "-encoding", "UTF-8"),
                null,
                units
        );

        boolean ok = Boolean.TRUE.equals(task.call());

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            System.err.println(
                    d.getKind() + " at line "
                            + d.getLineNumber() + ": "
                            + d.getMessage(Locale.ROOT)
            );
        }
        return ok;
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK 17+");
        }

        Path root = Files.createTempDirectory("compiler-api-");
        Path src = root.resolve("src");
        Path classes = root.resolve("classes");
        Files.createDirectories(classes);

        Path messagesSource = writeSource(
                src,
                "example/lib/Messages.java",
                """
                package example.lib;

                public final class Messages {
                    private Messages() {}

                    public static String text() {
                        return "compiled in pass 1";
                    }
                }
                """
        );

        Path appSource = writeSource(
                src,
                "example/app/App.java",
                """
                package example.app;

                import example.lib.Messages;

                public final class App {
                    public static void main(String[] args) {
                        System.out.println(Messages.text());
                    }
                }
                """
        );

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             null, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));

            boolean first = compile(compiler, manager, messagesSource);
            System.out.println("pass 1: " + first);
            if (!first) {
                return;
            }

            manager.flush();

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_PATH, List.of(classes));

            boolean second = compile(compiler, manager, appSource);
            System.out.println("pass 2: " + second);
            if (!second) {
                return;
            }

            Files.createDirectories(classes.resolve("config"));
            FileObject resource = manager.getFileForOutput(
                    StandardLocation.CLASS_OUTPUT,
                    "",
                    "config/flag.txt",
                    null
            );
            try (OutputStream stream = resource.openOutputStream()) {
                stream.write(
                        "managed-resource\n"
                                .getBytes(StandardCharsets.UTF_8));
            }
        }

        boolean bothExist =
                Files.exists(classes.resolve("example/lib/Messages.class"))
                        && Files.exists(
                                classes.resolve("example/app/App.class"));

        System.out.println("class files: " + bothExist);

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { classes.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> app = Class.forName(
                    "example.app.App", true, loader);
            app.getMethod("main", String[].class)
                    .invoke(null, (Object) new String[0]);

            try (InputStream resource = loader.getResourceAsStream(
                    "config/flag.txt")) {
                if (resource == null) {
                    throw new IllegalStateException("Resource not found");
                }
                System.out.print("resource: " + new String(
                        resource.readAllBytes(), StandardCharsets.UTF_8));
            }
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac -encoding UTF-8 CompileTwiceDemo.java
java CompileTwiceDemo
~~~

**Exact expected stdout on JDK 17+ in a normal environment:**

~~~text
pass 1: true
pass 2: true
class files: true
compiled in pass 1
resource: managed-resource
~~~

The temporary directory has a different name on each run, so the example **does not print the temporary path** to keep output stable. Diagnostics, if any, are printed to **stderr**, separate from stdout. After the experiment, the temporary directory still exists; real applications should have a policy to clean up temporary outputs intentionally when no longer needed.

### Why Does This Example Prove Multiple Compilation Passes?

The first pass generates:

~~~text
classes/example/lib/Messages.class
~~~

The subsequent pass uses that output as a compile dependency via `setLocationFromPaths(CLASS_PATH, List.of(classes))`, and then generates:

~~~text
classes/example/app/App.class
~~~

There is no need to invoke `javac` from the shell for each sub-file. Both tasks are created from **one** `JavaCompiler` and use **the same** `StandardJavaFileManager`, yet they are **two separate `CompilationTask` objects**.

`manager.flush()` helps the file manager release/flush buffers or caches depending on implementation before continuing configuration. Even so, the primary reason pass 2 finds `Messages` is that the class file from pass 1 was written and `classes` was added to `CLASS_PATH`. `flush()` **does not replace** setting the right classpath.

### Why Is a Separate Class Loader Needed to Run?

`JavaCompiler` creates `.class` files yet does not automatically load those classes into the current application's class loader. `URLClassLoader` with the `classes` URL and `ClassLoader.getPlatformClassLoader()` as parent allows the example to inspect the exact output just created, avoiding depending on classes of the same name that may already exist on the external application classpath.

Reflection invokes `main(String[])` using `invoke(null, (Object) new String[0])`: the `(Object)` cast keeps the string array as **one argument** of the reflective call. `URLClassLoader` is closed with `try-with-resources` when done.

## 5. Resource Management: Streams, Writers, File Managers, and Class Loaders

Objects participating in compilation often own I/O resources:

| Object | How Should It Be Managed? |
| --- | --- |
| `JavaFileObject.openInputStream()/openReader()` | Close stream/reader after reading |
| `JavaFileObject.openOutputStream()/openWriter()` | Close stream/writer after writing so contents are complete |
| `FileObject.openOutputStream()/openWriter()` | Close output/resource resources |
| `StandardJavaFileManager` | `flush()` between tasks when needed, `close()` when no longer used |
| `URLClassLoader` created by you | Close to release file/JAR handles when no longer needed |
| `DiagnosticCollector` | Does not need closing; yet create a new collector per task to keep errors separate |
| `CompilationTask` | Has no "reset task" lifecycle; create a new task for a new compile pass |

**`flush()` and `close()` differ:**

- `flush()` flushes/releases temporary resources that the file manager can handle, so subsequent operations see an appropriate state. It **does not delete outputs**, does not reset all locations, and does not automatically scan changed sources.
- `close()` ends usage of the file manager and releases resources held by the manager. After closing, do not continue using the manager for new tasks; create a new file manager if another compile session is needed.
- Closing a file manager does not automatically close other class loaders created by the application; they have their own lifecycles.
- If a build tool or processor creates resources, ensure output streams are closed **before** a JAR packaging tool reads those files.

On Windows, keeping a JAR handle open can cause replacing/deleting the JAR to fail. Therefore, closing file managers and class loaders at appropriate boundaries is critical in long-running applications such as IDEs or build servers.

## 6. Multiple Tasks: Reuse the Manager, Do Not Reuse the Task

**Right:**

~~~java
JavaCompiler.CompilationTask first = compiler.getTask(
        null, manager, firstDiagnostics, options, null, firstSources);
boolean firstOk = Boolean.TRUE.equals(first.call());

JavaCompiler.CompilationTask second = compiler.getTask(
        null, manager, secondDiagnostics, options, null, secondSources);
boolean secondOk = Boolean.TRUE.equals(second.call());
~~~

This is a **fragment** inside a method that already has compiler, manager, diagnostics, options, and source lists. If pass 2 depends on pass 1's output, ensure the manager sees the class output via `CLASS_PATH` as in the previous example.

**Wrong idea:**

~~~java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, sources);
task.call();
task.call(); // Not the way to perform a subsequent compilation.
~~~

A compilation task can only invoke `call()` once per the `JavaCompiler.CompilationTask` API contract (extending `Callable<Boolean>` with specific constraints). For a new compile pass, instantiate a **new task**. `StandardJavaFileManager` is designed to be reusable across **sequential compilations**, helping leverage the manager's file/JAR reading.

Do not call multiple `CompilationTask.call()` concurrently on the same `StandardJavaFileManager` without an explicit thread-safety contract. If running parallel builds, use separate file managers/compiler contexts and segregate output locations, avoiding concurrent writes to the same `.class` or resource.

### DiagnosticCollector Should Be Created Anew

A collector can retain diagnostics from completed tasks:

~~~java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
~~~

When compiling across multiple passes, creating a new collector helps distinguish which errors occurred in pass 1 or pass 2, even when the same filename is recompiled. Do not lump many warnings together and rely on sequence indices without knowing which compilation task they belong to.

## 7. When Sources Change Between Two Compilations

A common IDE requirement is **recompiling the same source after user edits**. For example:

~~~text
pass 1:
  Source A.java -> A.class

user edits A.java

pass 2:
  Source A.java -> new A.class
~~~

With the API, you create a new `CompilationTask` after changing source content. Depending on the file manager, ensure all streams are closed, use `flush()`, or create a new file manager when wanting clear cache boundaries. However, there are three independent issues:

1. **Old outputs may still exist**: the compiler does not automatically delete all invalid `.class` files when sources are deleted/renamed.
2. **Dependent classes may need recompilation**: the JavaCompiler API is not a full incremental build system. It does not automatically build a dependency graph and determine all sources needing rebuild.
3. **The JVM has already loaded the old class**: if a class loader has already defined `A`, merely rewriting `A.class` on disk does not automatically make the running class become the new version.

In real build systems, algorithms are needed to decide compilation units, manage stale artifacts, and select appropriate class-loading strategies. `StandardJavaFileManager` helps read/write files, **it does not provide all of the cache invalidation and dependency tracking** of Gradle, Maven, or IDEs.

### Recompilation and ClassLoader

For example, modifying source with a new method and recompiling to output `A.class` into the same directory. A class loader that already loaded `A` still references the old definition; to observe the new class in a simple experiment, use a **new class loader with an appropriate delegation boundary**, then close the old loader when safe. If old objects from loader A interact with classes from loader B, different type identities can lead to cast/linkage issues.

Do not solve reloading by repeatedly trying to call `Class.forName(...)` with the same loader and expecting the JVM to discard the already-defined class.

## 8. Configuring Multiple Search Paths Explicitly

When there is a JAR dependency:

~~~java
Path output = Path.of("build/classes");
Path library = Path.of("libs/example-lib.jar");

manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(output)
);

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(output, library)
);
~~~

This is a **fragment**. Paths must exist or match location/file manager requirements. The `output` directory is the package root of classes just compiled or about to be compiled; `library` is a specific JAR dependency.

The `setLocationFromPaths` API is helpful because you do not have to manually concatenate classpath strings with `;` on Windows and `:` on Linux. The `List<Path>` structure supplies each entry explicitly. If the application also builds `java -cp` commands manually, you still must use platform-specific entry separators there.

### Classpath Is Not Processor Path

- `CLASS_PATH` is used to resolve classes/types that sources need during compilation, including Java dependencies.
- `ANNOTATION_PROCESSOR_PATH` is the path to find processors to **run during compilation** if annotation processing is configured.
- `SOURCE_PATH` is the search path for additional source dependencies.
- `MODULE_PATH` is used for JPMS named modules; it is not a synonym for `CLASS_PATH`.
- `CLASS_OUTPUT` is the bytecode output destination; merely setting a `CLASS_OUTPUT` **does not mean** it is always a classpath input in the next compilation. If the next pass needs exported classes, configure the classpath explicitly.

If you run on a newer JDK yet need to target Java 17, set `--release 17` so the compiler aligns source level, target bytecode, and corresponding platform APIs. However, `--release` does not automatically verify whether every third-party library on the classpath can run on Java 17.

## 9. Diagnostics and Error Handling per Compilation Pass

`JavaCompiler.getTask(...)` accepts a `DiagnosticListener<? super JavaFileObject>`. With `DiagnosticCollector<JavaFileObject>`, after `call()` you can inspect:

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    System.out.println(
            diagnostic.getKind() + ": "
                    + diagnostic.getMessage(Locale.ROOT)
    );
}
~~~

This is a **fragment** using collector and `Locale` already present in the method. A diagnostic can contain:
- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`...
- `getSource()`: related `JavaFileObject` (if any).
- `getLineNumber()`, `getColumnNumber()`: position, may be `Diagnostic.NOPOS` if undetermined.
- `getCode()` and `getMessage(locale)`: compiler code and message.

When `task.call()` returns `false`, do not immediately run class output as a definitely valid build result: the compiler may leave partial output or stale output from a previous run. Use separate output directories per compilation or build in a staging directory and only replace main artifacts after the build succeeds if artifact-level atomicity is needed.

### Example of Scoped Error Reporting

Source `Broken.java`:

~~~java
public class Broken {
    public static void main(String[] args) {
        UnknownType value = null;
    }
}
~~~

This is a **source intentionally not compiling**. `JavaCompiler` will report that type `UnknownType` cannot be found if there is no matching declaration. The collector of the task compiling `Broken.java` must keep that error without mixing it with messages from subsequent tasks. Diagnostic positions and wording depend on the compiler/JDK; you should not hardcode a single verbatim stderr string for every environment.

## 10. JavaFileObject, FileObject, and Custom File Managers

`StandardJavaFileManager` works with files on disk. An IDE or service compiling from source code typed by a user into an editor may not want to create `.java` files on disk first. In that case, an **in-memory `JavaFileObject`** can be created.

Example **fragment** implementing an object for source:

~~~java
import java.net.URI;
import javax.tools.SimpleJavaFileObject;

final class StringSource extends SimpleJavaFileObject {
    private final String source;

    StringSource(String className, String source) {
        super(
                URI.create(
                        "string:///"
                                + className.replace('.', '/')
                                + Kind.SOURCE.extension
                ),
                Kind.SOURCE
        );
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
~~~

This is a **top-level helper class**, without `main`. You can pass `new StringSource("demo.Hello", "package demo; public class Hello {}")` into `compilationUnits` of `compiler.getTask(...)` to supply source not backed by a physical file.

Yet **in-memory source input does not mean class output is also in memory**. If still using normal `StandardJavaFileManager`, output is usually written according to `CLASS_OUTPUT`. To keep `.class` completely in RAM, you need a custom file manager, typically extending `ForwardingJavaFileManager<StandardJavaFileManager>`, overriding methods that receive class outputs (such as `getJavaFileForOutput` per compiler contract), and supplying a `JavaFileObject` writing bytes into a buffer.

Memory manager design must handle:
- Mapping binary name ↔ `JavaFileObject`.
- Outputs of annotation processors and resources via `getFileForOutput`/`Filer` when needed.
- Dependency and source lookup paths.
- Closing/flushing of streams, synchronizing data between passes.
- Turning byte arrays into classes loadable via a valid class loader.
- Isolation, file size, and memory limits.

Do not replace every `JavaFileManager` component with a simple stub when wanting to compile real code: JDK modules, classpath lookups, and JavaFileObject kinds still must be handled per compiler contract. `ForwardingJavaFileManager` helps reuse standard behavior in methods that do not need overriding.

## 11. Non-.class Resources: Reading, Writing, Packaging

Besides `.java` and `.class`, the compiler or annotation processors can generate **resources** such as:

~~~text
META-INF/services/com.example.spi.Plugin
config/feature.properties
META-INF/app/index.txt
~~~

`JavaFileManager.getFileForOutput(...)` is a mechanism at the file manager level to open output resources. Example in `CompileTwiceDemo`:

~~~java
FileObject file = manager.getFileForOutput(
        StandardLocation.CLASS_OUTPUT,
        "",
        "config/flag.txt",
        null
);
try (OutputStream output = file.openOutputStream()) {
    output.write("managed-resource\n".getBytes(
            StandardCharsets.UTF_8));
}
~~~

This is a **fragment excerpted from the runnable example**, placed in a method having manager and configured output. `location=CLASS_OUTPUT` puts the resource inside the class output tree; `pkg=""` means relative to the location root; `relativeName="config/flag.txt"` is the path inside the location.

Note for annotation processors: use **`ProcessingEnvironment.getFiler().createResource(...)`** to create new resources, because `Filer` manages ownership/output and detects duplicates within a processing run. File manager operates at the compiler I/O level; Filer operates at the standard annotation processing level. Do not use `FileManager.getFileForOutput` as a workaround to bypass `FilerException` rules.

### Packaging Resources into a JAR

If output under `build/classes` contains:

~~~text
build/classes/
├── example/app/App.class
└── config/flag.txt
~~~

The whole output tree can be packaged into a JAR:

~~~bash
jar --create --file build/app.jar -C build/classes .
jar --list --file build/app.jar
~~~

These commands are **examples**, only runnable when an appropriate `build/classes` structure exists. The `config/flag.txt` resource must be packaged along with the JAR if the runtime application wants to read it via `ClassLoader.getResourceAsStream("config/flag.txt")`. If the resource lies outside the packaged output, runtime will not find it automatically.

With multiple JARs containing identically named resources, `getResource(...)` may return one matching URL, while `getResources(...)` can list multiple URLs per loader; do not assume Java always merges resource contents. Some metadata like `META-INF/services` have dedicated consumption mechanisms via `ServiceLoader`.

## 12. When Using Annotation Processors and Source-Generation Passes

In a compilation task with annotation processing, a processor can create new sources with `Filer.createSourceFile(...)`, causing `javac` to run additional processing rounds. These are **rounds inside a single task**, differing from the application actively calling **`compiler.getTask(...)` twice**.

~~~text
Host application
  |
  +-- CompilationTask #1
  |      round 1 -> processor generates Generated.java
  |      round 2 -> compiler/processor sees new source
  |      final round -> finishes .class
  |
  +-- CompilationTask #2 (a new getTask)
         different input sources, file manager can be reused
~~~

Distinguish:

- **Processing round** is an iteration inside **one compilation** when annotation processors process annotated elements.
- **Compilation task** is the unit the host invokes via `JavaCompiler.getTask(...).call()`.
- **Source output** and **class output** must be configured appropriately for the build pipeline.
- Each processor instance holds state per corresponding processing environment/compilation, and cannot be safely shared across different tasks automatically.

File manager configuration uses the same way of setting locations for the compiler and processors, yet when a processor needs to generate files, the standard API is `Filer`. If a later task needs code generated by an earlier task, ensure the class/source output actually exists and is on the later task's search path.

## 13. Caching, Stale Output, and Build System Responsibilities

The standard file manager can cache file/JAR information to save work, yet **it is not a full incremental compiler**.

If the host creates multiple tasks on the same output:
- Old `A.class` files can remain when source `A.java` was deleted.
- A dependency may have changed its binary API, making classes compiled in a previous pass no longer compatible.
- A failing task may leave incomplete output unable to run while old classes still remain.
- A resource generated in a previous round can become stale data if the build does not clean properly.
- A custom file manager's cache may continue returning old contents even though files on disk have changed.

Practical approaches:

1. Separate outputs by version/build, or build in a staging directory and only publish artifacts after all tasks succeed.
2. Clean outputs when running a clean build; in incremental builds, track inputs → outputs to properly remove deleted/renamed files.
3. When dependencies change, determine which dependent sources need recompiling, not only the edited file itself.
4. Use `flush()` or create a new file manager when needing to cut cache boundaries; **do not** treat `flush()` as a replacement for a dependency graph.
5. Create a new class loader when needing to run new bytecode; do not assume the old loader automatically reloads class definitions.
6. If building multiple tasks in parallel, separate outputs to avoid race writes to the same files/resources.

### Ensuring "task 2 uses task 1's output" Is Truly Correct

Before task 2, verify:
- Task 1 returned success.
- `Messages.class` already exists at `classes/example/lib/Messages.class`.
- Task 2's file manager has `CLASS_PATH` containing `classes`.
- Task 2 uses class/module APIs compatible with the target release.
- Runtime classpath contains **both** `App.class` and `Messages.class`.

Those are distinct conditions. Having the right output yet wrong classpath still causes `cannot find symbol` at compile time; compiling successfully yet missing a dependency on the runtime classpath can still cause `NoClassDefFoundError` at runtime.

## 14. Common Mistakes When Working with File Managers

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime lacks appropriate compiler tool/module | Use a JDK with `jdk.compiler`, inspect runtime image |
| `task.call()` returns `false` | Source, classpath, module path, or option error | Collect task-specific diagnostics |
| Pass 2 reports `cannot find symbol` for type from pass 1 | Old output not added to `CLASS_PATH`, wrong output root, task 1 failed | Check `.class`, `CLASS_OUTPUT`, and `CLASS_PATH` |
| `getJavaFileObjectsFromPaths` cannot find source | Wrong source path, file not yet created, different working directory | Check `Files.exists(source)` and absolute path |
| Resource created yet runtime returns `null` | Written to wrong location/path, resource missing in JAR/classpath | Check `CLASS_OUTPUT`, use `jar --list` |
| `IOException`/file locked on rebuild | Writer/stream/manager/class loader still open | Use try-with-resources, close in proper order |
| Output does not update even when source changed | Custom manager cache, task did not receive new input, stale output | Create new task, flush/separate sessions, check inputs |
| Later pass repeats errors from earlier pass in logs | Reusing collector or mixing diagnostics without task attachment | New collector per pass |
| `IllegalStateException` when calling task | Task already executed/used with wrong lifecycle | Create new `CompilationTask`, do not call `call()` again |
| Compiled right yet running old class | Current class loader already defined old class | Create separate loader when reloading; manage type identity |
| Java code generates extra source yet has no class | Using `-proc:only` or pipeline has not compiled generated sources | Check annotation processing rounds, `-s`, `-d` |
| Runtime missing dependency present at compile time | Runtime classpath differs from compile classpath | Compare class lookup paths across both phases |
| Compile uses wrong encoding | File manager and compiler options inconsistent | Explicitly select UTF-8 for sources/resources |
| Using memory `JavaFileObject` yet output still on disk | Customized only input, not output manager | Need forwarding/custom manager for class output |
| Parallel build corrupts output files | Tasks write files concurrently to one location, manager lacks thread-safety guarantee | Separate managers/outputs and synchronize in host |

## 15. Checklist for Designing a Robust Compile API

1. **Choose compiler:** check `ToolProvider.getSystemJavaCompiler()` and target JDK.
2. **Prepare sources:** distinguish source files on disk and `JavaFileObject` in memory.
3. **Choose encoding:** consistently UTF-8 for sources and resources.
4. **Configure locations:** set output, classpath, source path, processor path/module path if needed; avoid conflicting configurations.
5. **Create task:** one `getTask(...)` per compilation, with separate options and diagnostics.
6. **Check result:** use `Boolean.TRUE.equals(task.call())`, read diagnostics, do not run results when the task fails.
7. **Between tasks:** ensure streams are closed, manage caches/flushing, add output of previous task to classpath when needed.
8. **After task:** verify output class files/resources, clean up stale outputs if that is the host's responsibility.
9. **When running generated bytecode:** create an appropriate loader and pay attention to class identity, loading classes from the right output.
10. **Close resources:** `try-with-resources` for file manager, streams, writers, and custom URLClassLoader.
11. **Package:** verify what appears in the JAR, including resources and runtime dependencies.
12. **In long-running systems:** control memory, temp directories, diagnostic logs, isolation/security, and concurrency per application policy.

## 16. Self-Check Questions

**Question 1.** After task 1, `classes/example/lib/Messages.class` exists. Why does task 2 not necessarily find `Messages` automatically just by using the same `CLASS_OUTPUT`?

**Answer:** `CLASS_OUTPUT` is the destination for writing; to use an existing class as a dependency, ensure it is on the appropriate class search path of task 2, such as setting `CLASS_PATH` to contain `classes`.

**Question 2.** Can you reuse the same `CompilationTask` and call `call()` twice to compile two groups of sources?

**Answer:** No. Create a new task for a new compilation pass. `StandardJavaFileManager` can be reused for sequential compilations.

**Question 3.** Why is closing `StandardJavaFileManager` after a build important?

**Answer:** The manager can hold file/JAR handles and I/O resources. Closing the manager releases them and sets clear usage boundaries.

**Question 4.** Does `manager.flush()` delete all old `.class` files and recompile all dependent sources?

**Answer:** No. `flush()` is a file manager management operation, not a clean build, dependency analysis, or class-loader reload.

**Question 5.** A processor wants to create resource `META-INF/app/index.txt` in the runtime artifact. What should it do?

**Answer:** In an annotation processor use `Filer.createResource(CLASS_OUTPUT, "", "META-INF/app/index.txt", origins...)`; close the stream and verify the resource is packaged into the JAR. When writing tools at the compiler I/O level, you can work through `JavaFileManager.getFileForOutput` with the corresponding location.

**Question 6.** Two tasks run concurrently sharing one manager and writing to the same `CLASS_OUTPUT`. Should this be assumed safe?

**Answer:** No. Do not assume the standard file manager is thread-safe for concurrent compilation operations, and concurrent file writes can make outputs inconsistent. Use separate sessions/outputs or appropriate synchronization coordination.

**Question 7.** Why does modifying `App.class` on disk not make `Class.forName("example.app.App")` from the same loader return the new definition?

**Answer:** A class is defined by binary name + defining loader; the loader may already hold the old definition. A valid reload mechanism/new loader is needed rather than just rewriting the file.

**Question 8.** Does merely creating `StringSource` in memory guarantee all class outputs are also in memory?

**Answer:** No. Input JavaFileObject and output file manager are two separate concerns. To keep bytecode output in RAM, handle `getJavaFileForOutput`/output streams with a custom manager.

## Remember

- **`JavaCompiler` creates tasks; `StandardJavaFileManager` manages I/O and locations; `CompilationTask` runs only once.**
- A file manager can be reused for **multiple sequential tasks**, yet classpath, buffers/caches, diagnostics, and close lifecycles must be managed.
- **`CLASS_OUTPUT` differs from `CLASS_PATH`**: output from an earlier pass must be on the subsequent pass's class search path to be used.
- Resources in `CLASS_OUTPUT` can be packaged into a JAR alongside `.class` files; annotation processors should generate resources via **`Filer`**.
- Successful compilation **does not** automatically load new classes, update old loaders, delete stale files, or verify runtime dependencies.
- Building reliable compilation tools requires **clear paths, closing all streams/managers, a fresh task per pass, and inspecting final bytecode/resources**.