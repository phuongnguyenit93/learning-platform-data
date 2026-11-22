# Capturing Bytecode with ForwardingJavaFileManager During In-Memory Java Compilation

The Java Compiler API allows a Java program to invoke the compiler without spawning an external `javac` process. When you want to **capture the compilation result as byte arrays** instead of letting the compiler write `.class` files to a directory, the design supported by Java SE is to create a **`ForwardingJavaFileManager`** wrapping `StandardJavaFileManager` and override the class-file output method.

The core idea: the compiler asks the file manager, “I need to write a class with binary name `demo.Hello`; give me a `JavaFileObject`”. The custom file manager returns an object whose `openOutputStream()` provides a `ByteArrayOutputStream`. After `CompilationTask.call()` completes, the application retrieves `byte[]` from each class to analyze, store according to its own policy, or load with a class loader.

This lesson uses Java 17+ and the practical example has been tested on JDK 21, covering nested classes, error diagnostics, lifecycle management, and an important limitation: **capturing bytecode in RAM does not mean the entire compilation process is isolated from the filesystem, classpath, or annotation processor code.**

## 1. Why do we need a ForwardingJavaFileManager?

`javax.tools.JavaCompiler` handles compilation, but it needs a `JavaFileManager` to read and write data units. `StandardJavaFileManager` works well with source files, output directories, JARs, classpath, and module path. However, when an application wants to receive bytecode directly, it should not have to create temporary files and read them back into RAM only to delete them afterward.

`ForwardingJavaFileManager<M extends JavaFileManager>` is a utility class using **delegation**: by default most operations are forwarded to the underlying file manager; you only override the operations you want to customize.

```text
JavaCompiler
    |
    | getTask(..., customManager, ...)
    v
ForwardingJavaFileManager
    |
    +-- compiler needs to read Java platform classes/JARs
    |       |
    |       +--> forwards to StandardJavaFileManager
    |
    +-- compiler generates demo.Hello.class
            |
            +--> getJavaFileForOutput(CLASS_OUTPUT,
                                      "demo.Hello", CLASS, sibling)
                      |
                      +--> InMemoryClassFile
                              |
                              +--> openOutputStream()
                                      |
                                      +--> ByteArrayOutputStream
                                              |
                                              +--> byte[] in Map
```

We **do not rewrite** the parser, type checker, or compiler. We only intercept how the compiler obtains an object to write the class file to.

Several APIs to distinguish:

| Component | Role |
| --- | --- |
| `JavaCompiler` | Initializes compilation tasks and executes compilation |
| `StandardJavaFileManager` | Underlying file manager used for classpath, platform classes, source files, and built-in locations |
| `ForwardingJavaFileManager<StandardJavaFileManager>` | Wraps the underlying manager, overriding specific necessary operations |
| `SimpleJavaFileObject` | Base class for custom representations of source or output class |
| `getJavaFileForOutput(...)` | Point where the compiler requests a destination to write a Java source/class file |
| `openOutputStream()` | Where the compiler actually writes bytes for the output object |
| `ByteArrayOutputStream` | Growable buffer in RAM; `toByteArray()` copies the written content |
| `DiagnosticCollector<JavaFileObject>` | Collects structured diagnostics such as errors, warnings, notes |

## 2. Where must the output be intercepted?

Key method on `JavaFileManager`:

```java
JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException;
```

This is an **illustrative API signature**, not a standalone method you can paste and run.

When `javac` wants to emit a class, the arguments typically carry these meanings:

- `location`: target location, e.g. `StandardLocation.CLASS_OUTPUT`.
- `className`: **binary name**, such as `demo.Hello` or `demo.Hello$Nested`; not the path `demo/Hello.class`.
- `kind`: `JavaFileObject.Kind.CLASS` for class files; `Kind.SOURCE` for source files.
- `sibling`: related object that the compiler may use as a location hint; may be `null`. Do not use it as the class identifier.

A safe conditional override for capturing class bytecode:

```java
if (location == StandardLocation.CLASS_OUTPUT
        && kind == JavaFileObject.Kind.CLASS) {
    // Return a JavaFileObject with openOutputStream() writing into RAM.
}
return super.getJavaFileForOutput(location, className, kind, sibling);
```

This is a **snippet inside a subclass method**, not a standalone Java file.

Reason to check location/kind: the file manager can also be asked to generate sources in `SOURCE_OUTPUT` or other file types. If you intercept every request and pretend they are all class files, annotation processing and other outputs may break. A compiler may provide separate locations for modules; this lesson focuses on a simple program **without module declarations**.

## 3. Complete Java 17+ example: compiling source and capturing all .class files in RAM

Save the entire program below to **`MemoryBytecodeDemo.java`**. Only JDK 17 or higher is required, with no external library dependencies.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
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

public class MemoryBytecodeDemo {

    // 1. Java source in RAM.
    static final class SourceFile extends SimpleJavaFileObject {
        private final String source;

        SourceFile(String className, String source) {
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

    // 2. A class output written by the compiler to a ByteArrayOutputStream.
    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream data =
                new ByteArrayOutputStream();

        ClassFile(String className, Kind kind) {
            super(URI.create("mem:///"
                    + className.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return data;
        }

        byte[] bytes() {
            return data.toByteArray();
        }
    }

    // 3. Most operations are delegated; only class output is kept in RAM.
    static final class CaptureManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, ClassFile> classes =
                new LinkedHashMap<>();

        CaptureManager(StandardJavaFileManager delegate) {
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
                ClassFile result = new ClassFile(className, kind);
                classes.put(className, result);
                return result;
            }

            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            classes.forEach((name, file) ->
                    result.put(name, file.bytes()));
            return result;
        }
    }

    // 4. Load the generated class from RAM to verify the result.
    static final class BytesLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        BytesLoader(ClassLoader parent, Map<String, byte[]> classes) {
            super(parent);
            this.classes = Map.copyOf(classes);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = classes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler required");
        }

        String source = """
                package demo;
                public class Hello {
                    public static String text() { return "ready"; }
                    static class Nested {}
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        Map<String, byte[]> bytes;

        try (CaptureManager manager = new CaptureManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT,
                        StandardCharsets.UTF_8))) {

            JavaFileObject input =
                    new SourceFile("demo.Hello", source);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(input));

            success = Boolean.TRUE.equals(task.call());
            bytes = manager.snapshot();
        }

        long errors = diagnostics.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();

        System.out.println("success=" + success);
        System.out.println("classCount=" + bytes.size());
        System.out.println("classes=" + new TreeSet<>(bytes.keySet()));
        System.out.println("errors=" + errors);

        if (success) {
            BytesLoader loader = new BytesLoader(
                    MemoryBytecodeDemo.class.getClassLoader(), bytes);
            Class<?> klass = loader.loadClass("demo.Hello");
            System.out.println("result="
                    + klass.getMethod("text").invoke(null));
        }
    }
}
```

Compile and run the driver program:

```bash
javac --release 17 -encoding UTF-8 MemoryBytecodeDemo.java
java MemoryBytecodeDemo
```

**Exact** stdout on the sample program (verified with JDK 21):

```text
success=true
classCount=2
classes=[demo.Hello, demo.Hello$Nested]
errors=0
result=ready
```

The `javac` command above compiles **`MemoryBytecodeDemo.java`** into a class on the filesystem, because we invoke the compiler from the terminal. However, when running the `MemoryBytecodeDemo` program, **the inner compilation pass** creates the two classes `demo.Hello` and `demo.Hello$Nested` **in RAM**, without writing `demo/Hello.class` or `demo/Hello$Nested.class` to the normal output directory.

`Nested` still generates a class file even though it is not called. The Java compiler emits artifacts for declared classes, including nested classes; therefore the map must store **multiple results** instead of keeping only the main class. `TreeSet` in the print statement keeps the name order stable even though the order in which the compiler invokes callbacks may vary.

## 4. Analyzing SourceFile: Java source in RAM

`SourceFile` extends `SimpleJavaFileObject` with `Kind.SOURCE` and stores a string:

```java
super(URI.create("string:///"
        + className.replace('.', '/')
        + Kind.SOURCE.extension), Kind.SOURCE);
```

With `className = "demo.Hello"`, the URI takes the form `string:///demo/Hello.java`. This URI is the **logical identifier** of the file object, not an assertion that a real file exists in the `demo` directory.

Overriding:

```java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return source;
}
```

lets the compiler read the source from `String`. The compiler continues processing Java text like a normal source. Once the text is already a `String` in RAM, earlier source byte decoding no longer belongs to `SourceFile`; if the original input came from a file/network, the caller must decode it with the proper charset before constructing the string.

The logical file name and package/class declarations should be consistent, especially when there is a public top-level type. If the source has `public class Hello`, the class name passed to the file object should be `demo.Hello` with the corresponding package.

There is no need to override `openInputStream()` for a string source because the example uses `getCharContent()`. With a different kind of file object, choosing among stream, reader, and char content depends on the contract the compiler uses; implement the method matching the kind and goal.

## 5. Analyzing ClassFile: where bytes are actually stored

`ClassFile` also extends `SimpleJavaFileObject`, but uses `Kind.CLASS` and URI `mem:///demo/Hello.class`. Most importantly:

```java
@Override
public OutputStream openOutputStream() {
    return data;
}
```

When the compiler is given the file object as output, it writes class-file bytes into this stream. `ByteArrayOutputStream` accumulates the bytes. After `task.call()`, call `data.toByteArray()` to obtain a **copy** of the contents.

Do not confuse the two steps:

- `getJavaFileForOutput(...)` **selects the destination to write to**; merely returning the object does not mean complete bytecode exists yet.
- `openOutputStream()` is the **byte-receiving path** the compiler uses during code generation and file writing.

The byte array is not UTF-8 source code. It is a **JVM class file** in binary format; you should not convert it via `new String(bytes, UTF_8)` to read as text. If you need to inspect class contents, use a class-file analysis tool, `javap` once an artifact exists, or a suitable bytecode library.

A valid class file starts with the magic bytes `CA FE BA BE`; however, checking the first four bytes **is not enough** to prove the class is valid in full structure and loadability. Compiler status and actually loading/reading the bytecode are deeper checks.

## 6. Why is Map<String, ClassFile> needed instead of a single byte[]?

One compilation can emit:

- A top-level class, e.g. `demo.Hello`.
- Nested/member classes, e.g. `demo.Hello$Nested`.
- Anonymous classes, e.g. `demo.Hello$1`.
- Auxiliary classes generated from enums, records, or other constructs depending on the Java source.
- Multiple top-level classes when one compilation unit contains multiple declarations or when there are multiple source files.

Map keys should use the **binary class name** passed by the compiler into `getJavaFileForOutput`. For nested classes, the binary name usually has the `$` character, not the string `demo.Hello.Nested`.

If you only keep a single `byte[] output` variable and overwrite it on each callback, the previous class's result will be lost. The map preserves a separate byte array for each class. In the example, `classes.put(className, result)` happens before the compiler writes bytes into the stream; after `task.call()` finishes, `snapshot()` takes a copy.

To ensure stable output, code should check the **expected key set** and reasonable sizes rather than relying on callback order. If a compilation task emits the same binary name again, map-overwriting behavior can mask a design bug; production tools should detect collisions and report a diagnostic/failure instead of silently keeping the last class.

## 7. Forwarding and delegation mechanism

`ForwardingJavaFileManager<StandardJavaFileManager>` does not replace every feature of the standard file manager. Only one method is overridden:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {

    if (location == StandardLocation.CLASS_OUTPUT
            && kind == JavaFileObject.Kind.CLASS) {
        // Capture class output.
    }

    return super.getJavaFileForOutput(
            location, className, kind, sibling);
}
```

Everything else — such as built-in Java SE types, JARs on the classpath, option handling, or reading sources from default locations — is handled by the underlying manager according to its contract.

**Note on Java 18+:** `JavaFileManager` added output methods accepting originating files, such as `getJavaFileForOutputForOriginatingFiles(...)`. The current `ForwardingJavaFileManager` specifies that if a subclass overrides `getJavaFileForOutput(...)`, the originating-files variant delegates to that override; otherwise, it delegates directly to the underlying manager. When using a different compiler implementation or optimizing for a specific release, check the corresponding JDK contract and test all output paths the compiler uses. The interception in the example relies on APIs documented for Java 21.

If the application also needs to keep **generated source** or resources in RAM, intercepting only `CLASS_OUTPUT` is insufficient. You must look at `getJavaFileForOutput(...)` for sources, `getFileForOutput(...)` for resources, and locations like `SOURCE_OUTPUT`; sometimes you also need to implement methods to **read back** generated source/classes from RAM. That is an extension of the problem, not an automatic consequence of a single override.

## 8. JavaCompiler.getTask and the execution workflow

In the example:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, List.of(input));
```

The parameters have the following roles:

| Parameter | Value in demo | Meaning |
| --- | --- | --- |
| Writer | `null` | Uses the default output writer for information not routed through the listener |
| File manager | `manager` | Forwarding manager intercepting class output |
| Diagnostic listener | `diagnostics` | Collects structured errors/warnings/notes |
| Options | `--release 17`, `-proc:none` | Compiles targeting Java 17, without running annotation processors |
| Classes | `null` | Does not specify separate class names for annotation processing |
| Compilation units | `List.of(input)` | One source file object read by the compiler in RAM |

`getTask(...)` **creates the task**, while `task.call()` actually performs compilation. A task should only be called **once**; to compile another set of sources, create a new task.

`Boolean.TRUE.equals(task.call())` returns a boolean indicating success per the JavaCompiler API. When a task fails, the manager may already have received some temporary/partial outputs prior to the error; therefore, you should not “publish” captured bytes if `success != true`.

Using `-proc:none` isolates the exercise from annotation processors that might be on the classpath. If you genuinely want to run annotation processors, you must also manage the processor path, processing rounds, and generated files. Starting from JDK 23, default processing activation behavior changed; explicit options help make demo results less environment-dependent.

## 9. Reading DiagnosticCollector instead of parsing stderr

`DiagnosticCollector<JavaFileObject>` collects diagnostics emitted by the compiler or processors. Each diagnostic has:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, or `OTHER`.
- `getSource()`: related source if known, may be `null`.
- `getLineNumber()`, `getColumnNumber()`, `getPosition()`: position if known, otherwise `Diagnostic.NOPOS`.
- `getMessage(Locale)`: message for human readers, **not** a stable schema for a program to parse.
- `getCode()`: compiler-supplied code if available; **implementation-dependent**, should not be relied upon as a universal standard across all JDKs.

With input as `SimpleJavaFileObject`, the source name is supplied by the file object, not necessarily a real path on disk.

In real applications, use compilation status and diagnostic kind for classification. To display errors to users, show the message along with source/line/column if available; do not tie business logic to an exact English sentence from `javac`.

An intentionally invalid source example:

```java
package demo;
public class Broken {
    int value = "not an integer";
}
```

If you replace `source` in the demo with the string above while using `new SourceFile("demo.Broken", source)`, the task will report an error that `String` is incompatible with `int`. There is no rule that “whenever the compiler hits an error the class map is completely empty” across all multi-file compilations; you must check `success` before using the bytes.

This is **error-illustration code**, not a standalone runnable class. Error wording can vary by compiler/locale. Do not try to assert the full stderr text in unit tests.

## 10. Loading bytecode with ClassLoader: why is this a separate step?

After compilation, a byte array is just data. To execute the class, the JVM must be instructed to define/load the class via a class loader or a related mechanism.

In the example, `BytesLoader` overrides `findClass`:

```java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] bytes = classes.get(name);
    if (bytes == null) {
        throw new ClassNotFoundException(name);
    }
    return defineClass(name, bytes, 0, bytes.length);
}
```

`defineClass` turns bytecode into a `Class<?>` defined by that loader, which can trigger verification/linking under JVM rules. Then:

```java
Class<?> klass = loader.loadClass("demo.Hello");
Object result = klass.getMethod("text").invoke(null);
```

is used to verify that the public `text()` method returns `ready`.

**Warning:** `ClassLoader.loadClass` follows the usual **parent-first delegation** mechanism. If the parent already has a class with the same binary name, `loadClass` may use the parent's class instead of the newly captured class; in that case, a test might think it is running the new bytes while actually running the old artifact. The demo picks `demo.Hello` which is not on the application classpath. For systems supporting hot reload, loader namespace/identity and lifecycle must be designed very carefully.

Class identity in the JVM is not just the binary name; it also depends on the **defining class loader**. Two loaders defining two classes with the same name still produce two distinct runtime types and cause `ClassCastException` when mixed. A custom class loader also does not make bytecode from untrusted sources inherently safe.

## 11. Multiple interdependent classes: is capturing output alone enough?

For **a single task** compiling `demo.A` and `demo.B` together, the compiler usually has enough symbols from the compilation units to check dependencies; the map receives the corresponding class outputs. However, if the first compilation only captures `A.class` in RAM and a second pass needs to compile `B.java` depending on `A`, keeping `A` in a map **does not make `StandardJavaFileManager` automatically read it**.

You need to design a file manager that also supports **input**:

- `getJavaFileForInput(...)`: returns a `JavaFileObject` containing compiled class bytes for the matching name and location.
- `list(...)`: when the compiler lists classes in a package, supplies the in-memory class objects according to the contract.
- `inferBinaryName(...)`: returns the proper binary name for custom file objects.
- `hasLocation(...)`, module-aware methods, or related methods depending on the goal; do not assume every case uses the same lookup path.

That is more complex than intercepting output. For learning programs, the simple approach is to put all sources needing compilation **into the same compilation task**. If you truly need an incremental in-memory compiler, design and test every symbol lookup path per the `JavaFileManager` contract, including packages, nested types, generated sources, and classpath/module path.

Do not describe an output-capturing `Map<String, byte[]>` as a complete “in-memory classpath”. It is only a **result store**, not yet providing the full lookup interface the compiler needs.

## 12. When using annotation processors or generated sources

An annotation processor can:

1. Read root elements and annotations of sources.
2. Call `Filer.createSourceFile(...)` to generate Java sources in `SOURCE_OUTPUT`.
3. Create additional resource or class files via the `Filer` API.
4. Trigger subsequent processing rounds so the compiler reads the newly generated sources.

If the forwarding manager only intercepts:

```java
location == StandardLocation.CLASS_OUTPUT
        && kind == JavaFileObject.Kind.CLASS
```

then it **does not guarantee all generated sources/resources stay in RAM**. Some outputs may be delegated to the underlying manager and written to the filesystem, or fail if no valid location has been configured.

To build a **fully in-memory** pipeline, you must extend `getJavaFileForOutput` handling for `SOURCE_OUTPUT`, `getFileForOutput` for resources, and input/lookup for new files if the compiler needs to read them in later rounds. You also need to pay attention to origin-aware APIs from JDK 18, stream closing, and returning file objects of the proper kind.

For exercises, use `-proc:none` to avoid this scenario. When integrating real processors, write integration tests: whether the processor was invoked, whether sources were generated properly, whether the next round could read the files, and whether the final classes were completely captured.

## 13. The file manager may still access the filesystem

The term “in-memory” in this lesson applies to the **`String` source** and **class byte output**. The file manager still delegates the following tasks to `StandardJavaFileManager`:

- Looking up platform classes from the JDK.
- Reading JARs/classpath if required by options or the environment.
- Reading dependent sources from sourcepath/classpath in broader configurations.
- Accessing file/location metadata or opening JARs as needed.
- Writing other outputs if no corresponding override exists.

Therefore this **is not a sandbox**. Compiling untrusted user sources also carries risk if annotation processors/plugins execute arbitrary code inside the process. Using `-proc:none` to disable standard annotation processing does not lock down all system permissions or create a secure environment for the compiler/toolchain.

If a multi-tenant application needs to run code after compilation, it must enforce CPU/RAM limits, proper isolation, filesystem/network permissions, and class loader policies; using `ForwardingJavaFileManager` alone is not enough.

## 14. Resource and lifecycle management

`CaptureManager` in the example extends `ForwardingJavaFileManager` and implements `Closeable` via `JavaFileManager`. `try-with-resources` closes the manager at the end:

```java
try (CaptureManager manager = new CaptureManager(
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT,
                StandardCharsets.UTF_8))) {
    // Create compilation task, call call(), copy byte[].
}
```

`ForwardingJavaFileManager.close()` forwards the close operation to the underlying manager, releasing handles managed by `StandardJavaFileManager`. In the example, `snapshot()` copies `ByteArrayOutputStream` into `byte[]` before the manager is closed, so the results remain independent after the `try` block.

Some operational rules:

- Create a **new `CompilationTask` for each pass**; do not re-invoke a finished task.
- Running multiple sequential tasks can reuse a standard file manager per its contract with careful state control; for output capture, create a separate map or clear outputs per run.
- Do not assume your file manager or map is thread-safe. If compiling concurrently, isolate instances per task or synchronize properly.
- `ByteArrayOutputStream` grows in memory with total bytecode; if compiling many classes, enforce total size limits/quotas and release maps after use.
- Do not publish bytes from a failed compilation as verified artifacts.
- If you want to save to a JAR/disk afterward, that must be a separate step, following the entry-naming rule `demo/Hello.class` corresponding to the binary name, not writing bytes as text.

## 15. Diagnosing common errors

| Symptom | Cause Worth Checking | How to Handle |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` returns `null` | Runtime lacks a system compiler | Use a JDK/runtime image with the required compiler |
| `getJavaFileForOutput` is not called | Task did not run, error occurred before codegen, or compiler used a different output path | Check `task.call()`, diagnostics, location/kind |
| Map has only one class when multiple were expected | Not stored by each binary name, or source did not generate extra classes | Log key names and map per output |
| Class is captured but bytes are empty | Stream not written/closed yet, snapshot read too early, or compilation failed | Snapshot after `call()` and check status |
| Source does not compile | Wrong package/class name, syntax/type error, options, classpath | Read `DiagnosticCollector`; check source string |
| `IllegalArgumentException` from URI | Invalid logical URI, malformed characters, or wrong scheme/path | Use `URI.create` with a valid URI, normalize class names |
| `ClassNotFoundException` when loading | Loader lacks bytes for the requested class | Check map keys and `findClass` |
| `NoClassDefFoundError` when using class | Missing a runtime dependency, possibly nested/other dependency | Supply bytes for all dependencies or an appropriate parent loader |
| `ClassCastException` between two classes of the same name | Classes defined by two different loaders | Control classloader identity and shared interfaces |
| `.class` files still appear on disk | Unintercepted output request, processor creating files, or stale files | Check `location/kind` and clean output |
| Multiple compilations see stale bytes | Reusing map across passes or not resetting manager | One manager/map per task, update with clear lifecycle |
| OOM during large builds | Byte arrays accumulating in RAM | Enforce quotas, stream by policy, delete unneeded artifacts |
| Compiles successfully but class loading fails | Linkage/verification, missing classpath, or JDK mismatch | Read root throwable, check `--release` and dependencies |

Distinguish **compiler diagnostics**, **class output capture**, and **class loading**. These three steps can fail independently. Seeing `byte[]` in the map does not yet prove the code has been linked/loaded and run successfully.

## 16. Design mistakes to avoid

**Returning the same ByteArrayOutputStream for every class.** Multiple class files will have their bytes mixed together, producing corrupted artifacts. Each binary name needs its own object/stream.

**Using the class name as an arbitrary file path without normalization.** For `demo.Hello`, the logical URI should be built following the package path. Nested classes can have the `$` character in the binary name.

**Forgetting to intercept the right output location.** `CLASS_OUTPUT` is the standard class file destination in the demo. Other outputs must be handled according to their function; do not blindly intercept every `getFileForOutput`.

**Losing the ability to read dependencies.** Replacing `JavaFileManager` entirely with an implementation missing `list`, `inferBinaryName`, and platform-class handling can prevent the compiler from resolving names. Forwarding lets you keep standard capabilities and change only where classes are written.

**Keeping bytecode on compilation failure and sending it to runtime.** The compiler may produce partial artifacts before failing; only publish after status and diagnostics are handled.

**Calling `new String(classBytes)` to store bytecode.** A class file is binary, not UTF-8 text. Write raw bytes when saving, or use Base64 if passing over a text protocol.

**Using a parent-first class loader while expecting automatic replacement of loaded classes.** If the parent already has the binary name, the new class may not be selected. Design loader isolation and versioning for hot-reload systems.

**Assuming compilation never touches the filesystem.** The compiler can still read the JDK/JARs and manage other outputs; do not use byte-capturing tricks as security isolation.

## 17. Exercises and answers

**Exercise 1.** The compiler requests writing `demo.Hello$Nested`. Why should you not store it into a single `byte[] helloBytes` variable?

**Answer:** One source generates multiple classes. You must store by each binary name so nested or other classes are not lost.

**Exercise 2.** Is overriding `getJavaFileForOutput(...)` enough to make the compiler read class bytecode captured from a **previous task**?

**Answer:** Not yet. You need to provide appropriate **input/lookup** paths such as `getJavaFileForInput`, `list`, and `inferBinaryName`, or put all sources in the same task.

**Exercise 3.** Which stream does `ClassFile.openOutputStream()` return to store in RAM?

**Answer:** A `ByteArrayOutputStream` belonging to that specific class output object; retrieve a copy using `toByteArray()` after compilation.

**Exercise 4.** If the compiler generates a resource file via an annotation processor, does an override specifically for `CLASS_OUTPUT + Kind.CLASS` guarantee the resource stays in RAM?

**Answer:** No. You must also handle output locations and file objects for resources.

**Exercise 5.** `task.call()` returns `false`, yet the map contains some bytes. Can those results be returned as a successful build?

**Answer:** No. They may be partial outputs; you must rely on compilation status and diagnostics.

**Exercise 6.** Why can `LoaderA.loadClass("demo.Hello")` and `LoaderB.loadClass("demo.Hello")` produce two distinct runtime types?

**Answer:** Class identity includes the defining class loader, not just the binary name.

**Exercise 7.** Why must `TreeSet` be used in the demo when printing the list of class names?

**Answer:** You should not rely on the order in which the compiler invokes callbacks. `TreeSet` sorts keys for stable text output.

**Exercise 8.** What is the actual output of the `MemoryBytecodeDemo` program verified on JDK 21?

**Answer:** `success=true`, `classCount=2`, `classes=[demo.Hello, demo.Hello$Nested]`, `errors=0`, `result=ready`.

## 18. Checklist for production systems

1. Determine whether you need to **capture final class files**, generated sources, or dependency class inputs too; these requirements demand different levels of customization.
2. Use `ToolProvider.getSystemJavaCompiler()` and check that the compiler is available.
3. Use `StandardJavaFileManager` as the delegate to preserve the ability to locate JDK classes/JARs.
4. Create source `SimpleJavaFileObject` instances with a logical URI and `getCharContent()`, or use real source files if needed.
5. Override `getJavaFileForOutput` specifically for `CLASS_OUTPUT` and `Kind.CLASS`.
6. Create **one output object per binary class name**, separate streams, and separate maps per task.
7. Call `compiler.getTask(...)`, passing explicit options and `DiagnosticCollector`.
8. Call `task.call()` exactly once; do not publish results if it fails.
9. Snapshot all `byte[]` after the task completes; close the manager.
10. If runtime execution is needed, use an appropriate class loader and verify dependencies; do not assume parent-first always picks the new bytes.
11. If incremental compilation or processors are needed, extend the input/output contract and test processing rounds, locations, and nested classes.
12. For untrusted/multi-tenant environments, design isolation and quotas independently of the file manager.
13. Test on the actual JDK/toolchain; keep `--release` aligned with the Java target.
14. Use build results, `Diagnostic.Kind`, and artifacts for testing; do not depend on verbatim compiler stdout/stderr.

## 19. Conclusion and official documentation

`ForwardingJavaFileManager` is the **delegation-based** way to extend the Java Compiler API: keep all normal capabilities of `StandardJavaFileManager`, and change only how specific requests are handled. For bytecode capture, **override `getJavaFileForOutput`**, return a `SimpleJavaFileObject` whose `openOutputStream()` writes into a `ByteArrayOutputStream`, then retrieve the bytes after `CompilationTask.call()`. This is a verifiable pipeline: **source → compiler → output object → bytes map → optional class loader**.

The key is keeping the boundaries clear: a bytecode map only captures **output**, does not automatically provide an **in-memory input classpath**, does not automatically manage generated sources/resources, and does not become a sandbox. Within those boundaries, this technique is useful for analysis tools, dynamic compilers, code generation systems, and tests that want to inspect bytecode without managing temporary class files.

References:

- [Java SE 21 ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): delegation contract and output methods.
- [Java SE 21 JavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): `getJavaFileForOutput`, input/list/inferBinaryName, locations.
- [Java SE 21 SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): creating file objects from URIs, overriding char/byte I/O.
- [Java SE 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `getStandardFileManager`, compilation lifecycle.
- [Java SE 21 DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): collecting structured compiler diagnostics.
