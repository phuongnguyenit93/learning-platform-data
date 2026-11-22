# Bytecode Generation, Dynamic Compilation, and ClassLoader Management Responsibilities in Java

Java can create additional classes **at runtime**, rather than only using pre-packaged `.class` files. An application can generate source code from a template and compile it using `javax.tools.JavaCompiler`, or generate bytecode directly via a dedicated library and supply the bytes to the JVM. Then a **ClassLoader** (or an appropriate class-definition mechanism) is responsible for converting the class-file format into a **runtime `Class<?>`**.

These steps address **three different tasks**:

1. **Code generation / bytecode generation:** produces the data representing the class, typically `.java` source or a valid class-file `byte[]`.
2. **Compilation / transformation:** uses a Java compiler, code generator, or bytecode transformer to produce bytes with the correct format, Java version, dependencies, and method signatures.
3. **Type definition / loading:** the JVM requires a **defining loader** and performs the corresponding name, package, loading-constraint, verification/linking, and security checks before the runtime class is used.

There is **no equivalence** between “I have generated the bytecode”, “the class has been loaded by the JVM”, and “the class has been initialized/instantiated”. This article explains the end-to-end processing flow, the responsibilities that cannot be offloaded entirely to JavaCompiler or the JVM, and also includes a Java 17+ program that **compiles source in memory, defines classes itself, creates objects, and compares two loader generations**.

## 1. Overview Model

~~~text
                         Host application
                               |
                +--------------+--------------+
                |                             |
        Source generation               Bytecode generation
        String / .java                  ASM, Byte Buddy, etc.
                |                             |
        JavaCompiler API                     byte[]
                |                             |
       class-file byte[]                     |
                +--------------+--------------+
                               |
                         Loader generation
                               |
                 findClass -> defineClass
                               |
                          JVM Class<?>
                    (name, defining loader)
                               |
                   Linking / Initialization
                               |
                     Reflection / Interface
                               |
                         Object instance
~~~

These are **two different input branches** for obtaining bytes, yet the final output in both cases is subject to the JVM's class-loading constraints. If a code generator has already produced valid bytecode, there is no need to run `javac` again. If only a source string has been generated, an appropriate compiler is needed to obtain class-file bytes.

| Concept | Data/API | What Not to Confuse It With |
|---|---|---|
| Java source | `String`, `.java`, `JavaFileObject.Kind.SOURCE` | Not yet a runtime class |
| Java compilation | `JavaCompiler.getTask(...).call()` | Returns compilation result; does not automatically instantiate |
| Class-file bytes | `byte[]`, `JavaFileObject.Kind.CLASS` | Not yet guaranteed to be verified/linked/initialized |
| Custom loader | `ClassLoader.findClass` and `defineClass` | Defines a type by loader identity |
| Runtime class | `Class<?>` | A representation of the type, not an object of the class |
| Instance | `Constructor.newInstance()` or calling `new` in linked code | Has its own constructor/initialization behavior |
| New-generation reload | **New loader instance** | Does not replace an existing class in the old loader |

### Type Identity Is the Foundational Question

According to the JVM, **runtime class/interface identity** is tied to:

~~~text
(binary name, defining class loader)
~~~

For example, two generations both have `generated.Hello`:

~~~text
("generated.Hello", LoaderA) -> Class A
("generated.Hello", LoaderB) -> Class B

ClassA.getName().equals(ClassB.getName()) == true
ClassA == ClassB                       == false
~~~

Therefore, a program **cannot “overwrite” the same class name in the same loader** by calling `defineClass` a second time. If a new version is needed, one typically creates a new loader and transitions traffic/references according to the lifecycle.

## 2. Approach 1: Source Code Generation and Dynamic Compilation with `javax.tools`

The `javax.tools` package belongs to the standard **`java.compiler`** module; it provides interfaces for supplying input sources, retrieving output, collecting errors, and customizing where files are stored. A full JDK typically provides the system compiler via:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system Java compiler");
}
~~~

This is an illustrative snippet, not a standalone program. **`compiler == null` is a case that must be handled**, for example when a runtime image created with `jlink` does not include the required module/compiler provider or when the environment only has a minimal runtime. Do not assume every JVM has a compiler for generating source code at runtime.

### Components of the Pipeline

| API | Role |
|---|---|
| `ToolProvider.getSystemJavaCompiler()` | Obtains the system Java compiler if available |
| `JavaFileObject` | Represents a source or class-file unit |
| `SimpleJavaFileObject` | Convenience class for implementing an in-memory file object |
| `StandardJavaFileManager` | Manages locations/classpath/output according to the compiler contract |
| `ForwardingJavaFileManager` | Intercepts or delegates file-manager calls to a custom implementation |
| `JavaFileManager.getJavaFileForOutput` | Determines where the compiler writes class-file output |
| `DiagnosticCollector<JavaFileObject>` | Collects errors/warnings with source locations |
| `JavaCompiler.getTask(...).call()` | Runs the compilation task, returning a `Boolean` indicating success/failure |

**Important:** `JavaCompiler.getTask` creates the task, while **`call()` actually performs the compilation**. Successful compilation also only indicates that the compiler produced valid output according to compiler rules; when the JVM loads it, dependency/linkage/runtime errors can still be detected.

### In-Memory Source

Instead of creating a `Hello.java` file on disk, we can use:

~~~java
final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///"
                + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
~~~

This is an **illustrative class fragment** requiring imports for `java.net.URI` and `javax.tools.SimpleJavaFileObject`; it has no `main`. A URI of the form `string:///generated/Hello.java` lets the compiler see a file name matching `public class Hello` without needing a real file system path.

### In-Memory `.class` Output

One way to create custom output:

~~~java
final class BytesFile extends SimpleJavaFileObject {
    private final ByteArrayOutputStream buffer =
            new ByteArrayOutputStream();

    BytesFile(String binaryName, Kind kind) {
        super(URI.create("mem:///"
                + binaryName.replace('.', '/')
                + kind.extension), kind);
    }

    @Override
    public OutputStream openOutputStream() {
        return buffer;
    }

    byte[] snapshot() {
        return buffer.toByteArray();
    }
}
~~~

This is an **illustrative fragment** with imports `ByteArrayOutputStream`, `OutputStream`, `URI`, `SimpleJavaFileObject`. The compiler writes bytes via `openOutputStream()`; after `call()` succeeds, the code takes a snapshot with `buffer.toByteArray()`. A single source can generate **multiple class files**, such as an inner class, local class, or auxiliary class; output must be stored by **binary class name**, not just a single `byte[]`.

## 3. Approach 2: Direct Bytecode Generation

Dedicated libraries (such as ASM or Byte Buddy) can produce a `byte[]` structured as a class file without writing source code and running `JavaCompiler`.

~~~text
DSL / metadata / schema
           |
           v
 bytecode generator
           |
           v
   JVM class-file bytes
           |
           v
 defineClass / Lookup.defineClass
           |
           v
        Class<?>
~~~

Advantages:

- Avoids the source-text parse/compile cycle when the generator only needs specific bytecode structures.
- Generates proxies, adapters, accessors, framework-generated subclasses, instrumentation, or method bodies on demand.
- Can manipulate JVM bytecode structures that are difficult to express in ordinary Java source.

Responsibilities:

1. **Valid class-file format**, constant pool, stack-map frames, access flags, signatures, and version supported by the target JVM.
2. **Identifiers and package** matching the binary name, loader, and package/module context.
3. **Bytecode verification and linkage**; `ClassFormatError`, `VerifyError`, or `LinkageError` may occur.
4. **Source provenance**, integrity, and input bounds; an unsafe generator can produce invalid classes or allow unintended code execution.
5. **Caching and loader lifecycle**; do not create unbounded unique classes or loaders indefinitely.

You should not assemble byte arrays manually to build complex class files in production when libraries that already understand the JVM specification exist; the following example uses the **built-in JavaCompiler**, without depending on external bytecode libraries.

### `ClassLoader.defineClass` and `MethodHandles.Lookup.defineClass`

The two APIs have different scopes:

- `ClassLoader.defineClass(String, byte[], int, int)` is **protected final**. Application code cannot invoke it arbitrarily on just any ClassLoader; a custom subclass typically exposes it indirectly via `findClass`.
- `MethodHandles.Lookup.defineClass(byte[])` is a mechanism available since Java 9 that uses a **Lookup with sufficient access** to define a class in the **same package and defining loader** as the lookup class. It is **not** an API for creating an arbitrary class name/package/loader.
- `Lookup.defineHiddenClass(...)` supports **hidden classes** for certain runtime/framework mechanisms. Hidden classes have distinct discoverability/lifecycle characteristics and are not regular named classes for callers to locate with `Class.forName(binaryName)`.

Choose the approach based on your goal: a dedicated loader for **unloadable plugins/generations**, or `Lookup` when generating additional types in the package/loader of a host class with appropriate access. Do not choose `Lookup` merely to work around classloader/package constraints.

## 4. The `defineClass` Contract: Names, Packages, and Class Loading

A custom loader can accept a map of class bytes:

~~~java
final class ByteArrayLoader extends ClassLoader {
    private final Map<String, byte[]> definitions;

    ByteArrayLoader(Map<String, byte[]> definitions,
                    ClassLoader parent) {
        super(parent);
        this.definitions = definitions;
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        byte[] bytes = definitions.get(name);
        if (bytes == null) {
            throw new ClassNotFoundException(name);
        }
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

This is an **illustrative API skeleton**; it requires importing `Map` and adding a snapshot/immutability policy if the map/bytes may be modified by another thread. In the complete example, we perform a snapshot and copy the bytes.

### Why Override `findClass` Instead of Rewriting `loadClass`?

The default implementation of `ClassLoader.loadClass`:

1. Uses `getClassLoadingLock(name)` to coordinate requests according to the parallel-capable policy.
2. Checks `findLoadedClass(name)`.
3. Queries parent/bootstrapping first.
4. Calls `findClass(name)` when the parent cannot find the class.
5. Calls `resolveClass` when requested.

If the only requirement is changing **where bytecode is located**, overriding `findClass` is the appropriate extension point, inheriting standard delegation and class-loading locking. Overriding `loadClass` manually without preserving `findLoadedClass`/locking can cause two threads to call `defineClass` for the same binary name simultaneously, resulting in a `LinkageError`.

### `defineClass` Does Not Mean Initialization

~~~java
Class<?> type = loader.loadClass("generated.Hello");
Object object = type.getConstructor().newInstance();
~~~

The first call asks the loader to find the class, **without automatically requiring static initializers to run**. The subsequent reflection call creates an instance and will require initialization according to Java rules if the type has not yet been initialized.

Related APIs:

| API | Expected State |
|---|---|
| `loader.loadClass(name)` | Requests loading; does not automatically require initialization |
| `Class.forName(name, false, loader)` | Finds/loads/links without requiring initialization |
| `Class.forName(name, true, loader)` | Finds the type and requires initialization |
| `defineClass(...)` | Defines a runtime class from class-file bytes; does not invoke the constructor |
| `resolveClass(type)` | Requests linking (resolution); does not mean creating an instance |
| `getConstructor().newInstance()` | Creates an instance and executes the constructor |

**A binary class name can only be defined once within the same defining loader**. Attempting to call `defineClass` again with the same name in the same loader results in an invalid duplicate definition. To change bytecode after deployment, create a **new generation loader** or use instrumentation/redefinition, which has its own limitations.

### Binary Name Matching the Actual Class File

`defineClass("generated.Hello", bytes, ...)` requires that the class-file bytes actually describe that exact name. A name mismatch can cause `NoClassDefFoundError` or a corresponding class-format/linkage error.

Do not define classes with the `java.` prefix from a custom loader: the JDK imposes special restrictions on core platform packages and may throw a `SecurityException`. In addition, if classes within a package use package-private access, those classes must be in the proper **runtime package**, which depends on **package name + defining loader**.

## 5. Complete Java 17+ Example: Compiling in RAM and Loading Two Versions

The **`DynamicCompilationDemo.java`** program below:

1. Builds source strings for the `generated.Hello` class in two versions: `dynamic-v1` and `dynamic-v2`.
2. Calls `ToolProvider.getSystemJavaCompiler()` and `JavaCompiler.getTask(...)` to produce class bytes.
3. Uses `SimpleJavaFileObject` and `ForwardingJavaFileManager` so that **no dynamic `.class` files are written to disk**.
4. Creates **two custom ClassLoader instances**, each holding the bytecode of one version.
5. Uses reflection to instantiate objects, invoke methods, and check class identity and defining loaders.
6. Demonstrates that the same binary name with different loaders produces **two distinct runtime types**; within the same loader, calling `loadClass` a second time returns the same `Class<?>`.

### 5.1. The `DynamicCompilationDemo.java` File

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DynamicCompilationDemo {

    private static final String CLASS_NAME = "generated.Hello";

    // 1. Source resides in memory.
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///"
                    + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    // 2. Output .class file resides in memory.
    static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();

        Bytecode(String binaryName, Kind kind) {
            super(URI.create("mem:///"
                    + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] snapshot() {
            return buffer.toByteArray();
        }
    }

    // 3. Compiler writes class files into a map instead of to disk.
    static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, Bytecode> outputs =
                new LinkedHashMap<>();

        MemoryFiles(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            Bytecode output = new Bytecode(className, kind);
            outputs.put(className, output);
            return output;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            for (var entry : outputs.entrySet()) {
                result.put(entry.getKey(), entry.getValue().snapshot());
            }
            return result;
        }
    }

    // 4. Loader defines the classes whose bytes are in the map.
    static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> definitions = new HashMap<>();

        MemoryLoader(Map<String, byte[]> bytes, ClassLoader parent) {
            super(parent);
            bytes.forEach((name, data) ->
                    definitions.put(name, data.clone()));
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] data = definitions.get(name);
            if (data == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, data, 0, data.length);
        }
    }

    private static String sourceFor(String label) {
        return "package generated;\n"
                + "public final class Hello {\n"
                + "  public String message() {\n"
                + "    return \"" + label + "\";\n"
                + "  }\n"
                + "}\n";
    }

    private static Map<String, byte[]> compile(
            JavaCompiler compiler, String code) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            MemoryFiles files = new MemoryFiles(standard);
            JavaFileObject source = new Source(CLASS_NAME, code);

            Boolean success = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(source)
            ).call();

            if (!Boolean.TRUE.equals(success)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + " at line "
                            + d.getLineNumber() + ": " + d.getMessage(
                                    Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }

            return files.snapshot();
        }
    }

    private static String message(Class<?> type) throws Exception {
        Object instance = type.getConstructor().newInstance();
        return (String) type.getMethod("message").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK compiler is required");
        }

        Map<String, byte[]> v1 =
                compile(compiler, sourceFor("dynamic-v1"));
        Map<String, byte[]> v2 =
                compile(compiler, sourceFor("dynamic-v2"));

        ClassLoader parent = DynamicCompilationDemo.class.getClassLoader();

        MemoryLoader loader1 = new MemoryLoader(v1, parent);
        MemoryLoader loader2 = new MemoryLoader(v2, parent);

        Class<?> first = loader1.loadClass(CLASS_NAME);
        Class<?> second = loader2.loadClass(CLASS_NAME);

        System.out.println("compiler available: true");
        System.out.println("v1: " + message(first));
        System.out.println("v2: " + message(second));
        System.out.println("same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("same runtime type: " + (first == second));
        System.out.println("v1 defined by loader1: "
                + (first.getClassLoader() == loader1));
        System.out.println("v2 defined by loader2: "
                + (second.getClassLoader() == loader2));
        System.out.println("repeat load same class: "
                + (loader1.loadClass(CLASS_NAME) == first));
        System.out.println("generated in unnamed module: "
                + !first.getModule().isNamed());
    }
}
~~~

### 5.2. Compiling and Running

Save the file as **`DynamicCompilationDemo.java`** in its own directory. Using JDK 17+:

~~~bash
javac -encoding UTF-8 DynamicCompilationDemo.java
java DynamicCompilationDemo
~~~

The initial `javac` command compiles the **host utility**; meanwhile, the `generated.Hello` class is compiled by **JavaCompiler inside the application** from a source string at runtime. There is no `javac generated/Hello.java` step and no need to write a `generated/Hello.class` file to disk.

**Expected stdout when running on a full JDK with JavaCompiler:**

~~~text
compiler available: true
v1: dynamic-v1
v2: dynamic-v2
same binary name: true
same runtime type: false
v1 defined by loader1: true
v2 defined by loader2: true
repeat load same class: true
generated in unnamed module: true
~~~

### 5.3. Why Does It Produce This Output?

- Both compilation tasks receive a source named `generated.Hello`, but the source of the `message()` method differs.
- `JavaCompiler` writes bytes into the `Bytecode` objects provided by `MemoryFiles.getJavaFileForOutput`; the v1/v2 maps do not share class objects.
- `MemoryLoader.findClass` retrieves bytes from the map and calls `defineClass`. Because the app loader does not have `generated.Hello` on the example's classpath, parent-first delegation does not shadow the class to be defined.
- `first.getClassLoader() == loader1` and `second.getClassLoader() == loader2` are `true`: there are two different defining loaders.
- `first.getName().equals(second.getName())` is `true` while `first == second` is `false`, demonstrating type identity.
- Within **the same loader1**, the subsequent `loadClass(CLASS_NAME)` call finds the already-loaded class and returns the existing `Class<?>` object; `defineClass` is not called a second time.
- Both generated classes belong to the **unnamed module of their defining loaders** when defined using the standard ClassLoader mechanism. A custom map of bytes does not automatically resolve into a named JPMS module.
- `message(first)` invokes the constructor and a public method via reflection. This requires the class to be defined successfully and have appropriate access; in this example, the generated class and method are `public`.

### 5.4. Analyzing the Roles of the Helper Classes

**`Source`** does not create a file on the filesystem: the `URI` only supplies a synthetic name compatible with the compiler. `getCharContent` provides the actual source.

**`Bytecode`** receives the data written by the compiler through `openOutputStream`. Snapshot creates an independent byte[] from the output stream after compilation finishes.

**`MemoryFiles`** extends `ForwardingJavaFileManager` to preserve most of the input/classpath logic of the standard file manager while redirecting **class outputs** to memory. It stores entries by class name, allowing the compiler to produce multiple distinct outputs if the source contains inner/anonymous classes.

**`MemoryLoader`** does not know how to compile by itself; it only defines already-generated bytes. The `data.clone()` copy reduces the risk of external code mutating the data after the loader has received it.

**`compile(...)`** creates a **new diagnostics/file manager per compilation**, then closes the standard file manager via try-with-resources. Do not share a file manager across multiple concurrent compilation tasks without an explicit synchronization design.

**`--release 17`** instructs the compiler to emit bytecode/APIs targeting Java 17 even when the program runs on a newer JDK (if that JDK supports target 17). **`-proc:none`** disables annotation processing in the demo to reduce reliance on processors that might happen to be on the classpath.

### 5.5. Intentional Limitations of the Example

1. Each compilation has only one Java source with the binary class name `generated.Hello`. Production systems may require multiple sources and output files.
2. The source is generated from **controlled labels**. Do not concatenate arbitrary source code from user input and treat the result as safe.
3. The parent is the application loader; if `generated.Hello` already exists in the parent, parent-first delegation will win. To isolate duplicate names, a separate namespace or an appropriate loader policy is required.
4. `MemoryLoader` retains the byte[] arrays in its map for its entire lifetime to keep the example simple. Production code can evict bytes after definition if caching is not needed.
5. `MemoryLoader` does not implement `Closeable` because it opens no URL/JAR handles. It also has no `unload()` method; when class unloading happens is determined by the JVM/GC.
6. Resource names via `getResource`/`getResourceAsStream` are not served from the memory map. This is a **class-file bytes** cache, not a general-purpose resource lookup mechanism.
7. Only the main results are printed from `main`; when input or compilation fails, the diagnostic message and exception will depend on the specific error and are not part of the standard output shown above.

## 6. Compiling Source That Depends on Host APIs

The `generated.Hello` example above only used `String` and APIs from `java.base`. A real-world plugin typically implements a **shared interface** from the host, for example:

~~~java
package api;

public interface Greeting {
    String message();
}
~~~

If the generated source uses:

~~~java
package generated;

public final class Hello implements api.Greeting {
    @Override
    public String message() {
        return "hello";
    }
}
~~~

These are **two illustrative Java files** for the API and implementation, not drop-in replacements for the standalone demo in Section 5.

### Compile-Time Classpath Differs from Runtime Defining Loader

When using `JavaCompiler`, the compiler must be able to see `api.Greeting` in the input classpath/module path:

~~~java
List<String> options = List.of(
        "--release", "17",
        "-proc:none",
        "-classpath", System.getProperty("java.class.path")
);
~~~

This is a **configuration-dependent illustrative snippet**; it assumes the API is already on the application classpath and the corresponding property is set. For named-module applications or custom plugin layers, you must design the **module path, classpath, and file manager** appropriately; do not treat `java.class.path` as representing everything the JVM has loaded through custom loaders.

After compilation, the loader defining the generated class must also **see the exact runtime `api.Greeting`** from its parent:

~~~text
Application loader
  defines api.Greeting
          |
          v
MemoryLoader (parent = application loader)
  defines generated.Hello
  generated.Hello implements api.Greeting from parent
~~~

If a custom loader defines its own `api.Greeting` with different bytecode under the same name, the JVM treats it as a **different interface**, and casting the generated object to the host's `api.Greeting` can fail. Having the same source/bytecode for the two API classes is not enough; they must share the **defining loader identity**.

### Boundaries When Compiling with Separate Dependencies

A plugin might compile against library v2 while parent-first delegation at runtime loads v1 instead. If a method signature does not exist in v1, a `NoSuchMethodError` can occur during linking/invocation. Therefore:

- Choose a compile classpath/module path that **matches** the dependency generation used at runtime.
- Place shared APIs in the parent.
- Isolate private dependencies in appropriate namespaces if different versions are needed.
- Do not allow private dependency types to leak into public signatures across the boundary.
- Test code generation under multiple runtime configurations, not merely “compile succeeded”.

## 7. How Does Dynamic Compilation with Files on Disk Differ from In-RAM Compilation?

A simple way to try dynamic compilation is to write the source to a temporary directory and invoke the compiler:

~~~text
generated-src/generated/Hello.java
             |
          javac
             |
          generated-out/generated/Hello.class
             |
       URLClassLoader
             |
        generated.Hello
~~~

This approach is easy to debug: you can open the `.java` and `.class` files and inspect them with `javap`. However, it creates temporary files, requiring safe cleanup, restricted access permissions, and management of URLClassLoader/file handles.

Using memory:

~~~text
String source
     |
JavaCompiler / JavaFileObject
     |
byte[] map
     |
MemoryLoader
     |
Class<?> / object
~~~

This reduces intermediate I/O and is convenient for runtime templates/generation. In return, debugging stack traces/class-file metadata and handling resource lookup must be explicitly designed.

| Criterion | Disk output + URLClassLoader | In-memory JavaFileObject + MemoryLoader |
|---|---|---|
| Inspecting class files while debugging | Easier | Must explicitly dump bytes/logs |
| Requires temporary files | Yes | No for generated output |
| Resource/JAR integration | URLClassLoader has built-in URL mechanisms | Must be implemented separately if needed |
| Cleanup | File/JAR handles, temp directory, streams | Byte map and references/lifecycle |
| Loader ownership | URLClassLoader instance | MemoryLoader instance |
| Bytecode verification | Still performed by the JVM | Still performed by the JVM |
| Reloading a class with the same binary name | Typically a new loader generation | New loader generation |
| Compiler diagnostics support | Compiler API | Compiler API |

It is **not** the case that “in-memory is always safer and faster”. Complex source templates, large numbers of classes, annotation processors, or large constant pools all carry significant compilation, caching, and Metaspace costs.

## 8. Compilation Errors: Do Not Turn Everything into `ClassNotFoundException`

If `getTask(...).call()` returns `false`, this is first and foremost a **compilation failure**, such as a syntax error, missing imported type, incompatible method signature, or unsupported option.

`DiagnosticCollector` can provide:

~~~java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.println(d.getKind());
    System.out.println(d.getLineNumber());
    System.out.println(d.getColumnNumber());
    System.out.println(d.getMessage(Locale.ROOT));
}
~~~

This is an **illustrative code snippet**, not a standalone runnable example; it requires the `diagnostics` variable and appropriate imports.

You should retain the following information:

- Generated source identifier, such as `string:///generated/Hello.java`.
- Compiler options and target `--release`.
- Length-bounded compilation diagnostics (kind, line/column, message).
- Artifact/template version and dependency classpath/module path.
- Number of generated class files and hash of the bytes.
- Do not include source code containing secrets or sensitive user data in public logs.

**Distinguishing errors by stage:**

| Stage | Example Error | Investigation Direction |
|---|---|---|
| Source generation | Template produces mismatched braces | Template/generator version logs and safe source |
| Compilation | `error: cannot find symbol` | Compile classpath/module path and source |
| Class-file output | `IOException` from file manager | OutputStream/location/capacity/lifecycle |
| Class loading | `ClassNotFoundException` | Bytes map, binary name, parent delegation |
| Class definition | `ClassFormatError` | Invalid class-file bytes |
| Verification/linkage | `VerifyError`, `NoClassDefFoundError`, `NoSuchMethodError` | Stack maps, dependencies, method signature/version |
| Access/package | `IllegalAccessError`, `SecurityException` | Runtime package, module exports/opens, package ownership |
| Initialization | `ExceptionInInitializerError`, `NoClassDefFoundError` after init failure | `static` code and root cause |
| Reflection/instance | `NoSuchMethodException`, `InvocationTargetException` | Actual constructor/method and target cause |

**Do not catch `LinkageError` and arbitrarily call `defineClass` again**, because the error may result from the class name already being defined in the loader. Understand the cause and decide on an appropriate generation strategy.

## 9. Package, Protection Domain, and Module Constraints

### Package and Loading Constraints

`defineClass` takes a **binary name** and bytes. The JVM requires a matching class file and performs package/security/linkage checks. A loader cannot define two classes with the same name within itself to “update a version”.

If two classes in the same package require package-private access, the JVM considers them part of the same runtime package only when both **package name and defining loader** match. Using two different loaders can cause `IllegalAccessError` even when both sources declare `package generated;`.

### ProtectionDomain and CodeSource

`ClassLoader.defineClass` has an overload accepting a `ProtectionDomain`:

~~~java
Class<?> defineClass(
    String name, byte[] data, int offset, int length,
    ProtectionDomain protectionDomain)
~~~

This is an **illustrative signature** of the `protected final` overload, not an invocation on a ClassLoader from external code.

- Protection domain, CodeSource, certificates/signers, and package-sealing policies each have distinct runtime semantics.
- If a custom loader distributes classes from a signed JAR, it must maintain **certificate consistency within the package** in accordance with the ClassLoader contract.
- A source URL/code origin for an in-memory class does not appear automatically; if auditing is needed, record origin/generation/hash explicitly in loader metadata.
- **Do not view ProtectionDomain as a built-in sandbox** capable of safely executing untrusted code. In modern Java, stronger isolation is required at the process/OS boundary.

### Named Modules

A custom `MemoryLoader` defines regular classes in the **unnamed module** associated with that loader. Having `module-info.class` in the source or bytes does not mean every class immediately becomes a JPMS-resolved named module.

If named modules are genuinely required, use the module path, `ModuleFinder`, `Configuration`, `ModuleLayer`, and appropriate loader mappings. `exports`/`opens`/`requires` declarations govern other aspects of accessibility; loader visibility does not automatically bypass JPMS.

### Classes in `java.*`

The JDK does not allow an ordinary custom class loader to arbitrarily define classes under `java.*`. `defineClass` may throw a `SecurityException` for such names. Do not use the `java.` namespace when experimenting with code generation.

## 10. Resource Management and Resource Lookup

Runtime code may also need non-class-file data: configuration files, templates, `META-INF/services`, or library resources.

**A class-bytes map is not automatically a resource registry.** `MemoryLoader.findClass` in the demo only uses the map to locate class bytes; `ClassLoader.getResource(...)`/`getResourceAsStream(...)` have their own policies and hooks. If you want to serve resources from memory, you can:

1. Build a **dedicated resource API** that returns a fresh stream from an immutable bytes cache.
2. Override resource lookup according to the contract, providing a URL/URL handler when `URL` semantics are genuinely required, and managing data lifetimes.
3. Package the plugin as a JAR and use `URLClassLoader` if built-in resource/JAR/manifest mechanisms are needed.
4. When using named modules, follow module resource encapsulation rules and `opens`.

**Do not cache and share a single `InputStream` across multiple callers**, because a stream maintains a read cursor and closed state. Cache immutable byte[] or source metadata and return **a new stream each time**.

With `ServiceLoader`, provider files in `META-INF/services` or JPMS `provides` declarations must reside in the proper lookup scope. A custom in-memory loader does not automatically perform provider discovery when you only implement `findClass`.

### Resource and Class Loading Policies Are Two Separate Branches

~~~text
Class loading:
  loadClass("generated.Hello")
       -> parent / findClass -> defineClass

Resource lookup:
  getResource("generated/config.txt")
       -> parent / findResource -> URL / stream
~~~

Overriding `loadClass` to be child-first does not make `getResource` child-first. This discrepancy is especially dangerous when the host and plugin contain resources with the same name. Both mechanisms must be tested separately.

## 11. Concurrency and Caching When Multiple Threads Request Classes Simultaneously

For a custom `ClassLoader`, class loading uses `getClassLoadingLock(name)` by default to coordinate contention. If you only override `findClass` as in the demo, the loader framework continues checking whether the class is already loaded and defining the class with proper synchronization.

However, a **custom compiler/file manager remains shared mutable state** if shared across threads. Do not infer that having a class-loading lock makes the entire compiler pipeline thread-safe.

A production design might look like this:

~~~text
Concurrent requests for template T, version V
                      |
                      v
       Cache key = (T, V, compiler options, deps hash)
                      |
                 single-flight
                      |
                 compile once
                      |
             immutable bytes snapshot
                      |
         +------------+-------------+
         |                          |
  Loader Generation A        Loader Generation B
         |                          |
   own Class<?> A              own Class<?> B
~~~

The cache key should include:

- Template/source hash.
- `--release` / compiler version/options (if they affect the emitted bytes).
- Classpath/module-path/dependency artifact versions.
- Annotation processing or bytecode transformer version.
- Plugin generation/security policy, if applicable.

You can share **immutable bytecode bytes** across loaders when generation/source match, but **never share a `Class<?>` runtime object** as if it were defined by every loader.

### `ConcurrentHashMap.computeIfAbsent` Does Not Replace Classloading Locks

`computeIfAbsent` creates cache entries atomically, but it **does not replace** `ClassLoader.getClassLoadingLock(name)`, `findLoadedClass`, or `defineClass` rules. Do not invoke a mapping callback that performs long-running I/O or recursively updates the same map and expect everything to avoid blocking or deadlocking.

If compilation is slow, use a single-flight placeholder such as `FutureTask<byte[]>` or `CompletableFuture` with a well-defined lifecycle/retry policy. When compilation fails:

- Do not cache `null` in ConcurrentHashMap.
- Do not retain a failed future forever unless intentionally designing a negative cache/TTL.
- Distinguish between permanent source errors and transient I/O/cache failures.
- Do not return a partial output map if the compiler has not reported success.
- Do not pass the same mutable byte[] to code that might modify it while a loader is calling `defineClass`.

### Parallel-Capable Loader

If you genuinely load many **distinct binary class names** in parallel, a subclass can register as parallel-capable via `registerAsParallelCapable()` during class initialization; all superclasses in the hierarchy (except `Object`) must also satisfy the registration requirement. This allows the loader to lock per class name rather than locking the entire loader in the default `loadClass`.

A small demo with only a few class names does not need to register as parallel-capable, and doing so **does not automatically make the compiler, file manager, or resource cache thread-safe**.

## 12. Loader Lifecycle, Class Unloading, and Hot Reload

An easy mistake to make is writing:

~~~java
loader = new MemoryLoader(newBytes, parent);
~~~

and assuming the old class has been unloaded. In reality:

- The old class remains alive if any `Class<?>`, object instance, static cache, MethodHandle, Method/Constructor reflection object, running thread, or other reference keeps it or its defining loader alive.
- A loader lacking `close()` does not mean its lifecycle can be ignored. The demo's MemoryLoader holds a map of bytes and related Java runtime objects.
- `URLClassLoader.close()` closes file/JAR handles; **it does not force the JVM to unload classes immediately**.
- The JVM can unload classes when the defining loader and related objects become eligible for garbage collection; the exact timing is not guaranteed upon application command.
- If source or generated code changes, a **new loader generation** is typically the standard way to create a new runtime class with the same binary name.

A practical lifecycle:

~~~text
Generation 1 (ACTIVE)
       |
       +--> stop accepting new plugin work
       |
       v
     DRAINING
       |
       +--> finish ongoing requests
       +--> stop plugin threads/scheduled tasks
       +--> close streams/JAR handles
       +--> unregister callbacks/services/listeners
       +--> clear caches holding Class/instance/loader
       +--> restore thread context loader
       |
       v
     RETIRED (eligible for GC when references disappear)

Generation 2 (ACTIVE)
       |
       +--> new loader + new generated classes
~~~

**Note:** for uninterrupted hot reload, the host may need an **immutable shared API** in the parent and an **atomic generation handle** pointing to the new set of providers. Existing requests continue using the old generation until completion, and new requests use the new generation; afterward, old references are cleared. Do not swap individual class names inside the same loader and expect the JVM to update immediately.

## 13. When to Use a Compiler, Bytecode Generator, or Proxy?

| Requirement | Appropriate Approach | Considerations |
|---|---|---|
| Generating classes from developer-controlled Java source/templates | `JavaCompiler` API | Compiler must be available; compilation cost and diagnostics |
| Generating many high-performance adapters/proxies | Byte Buddy/ASM or an appropriate runtime framework | Understanding bytecode verification, packages, and loader lifecycle |
| Creating an interface implementation backed by a handler | `java.lang.reflect.Proxy` | Limited to interfaces; method invocation handler |
| Creating a class in the same loader/package as a lookup class | `MethodHandles.Lookup.defineClass` when permitted by the contract | Lookup privileges, same package/loader |
| Short-lived classes serving a runtime framework | Hidden class APIs when appropriate for the use case | Not usable as regular classes discoverable by binary name |
| Plugins/JARs with many resources/dependencies | `URLClassLoader` + an appropriate policy | Managing URL/JAR handles, resources, and parent delegation |
| Java 17+ runtime without a compiler | Precompile ahead of time, use compiled artifacts or another technique | Do not assume `ToolProvider` always returns a compiler |
| Untrusted plugins | Process/container isolation | Classloaders are not sandboxes |

Sometimes **no class generation is needed**: using lambdas, the strategy pattern, reflection, `MethodHandle`, or data-driven configuration can be simpler. Dynamic compilation should be chosen when the flexibility genuinely outweighs the memory, CPU, and type/lifecycle complexity costs.

## 14. Security: Do Not Compile and Run Arbitrary Source in the Host JVM

**Design warning:** accepting Java source from untrusted users, invoking `JavaCompiler`, and then loading/executing it in the same JVM **is not safe isolation**.

Reasons:

- The compiler can consume CPU/heap/disk and access the classpath/module path in unintended ways.
- Annotation processors can execute code during compilation if configured/permitted. The demo uses `-proc:none` to disable processors, but **this does not sandbox the compiled code**.
- Loaded bytecode can call filesystem, network, or reflection APIs, or access process resources permitted by Java/the OS.
- A class with a static initializer, infinite thread, deep recursion, or references retained to the loader can disrupt the host's lifecycle.
- Dynamic generation can create an unbounded number of unique classes, putting pressure on Metaspace/heap and making class unloading difficult.

If you must serve untrusted code:

1. Use a separate process/container with least-privilege permissions and CPU/memory/time limits.
2. Do not expose an application classpath containing secrets/internal APIs to an untrusted compiler.
3. Limit source size, number of classes, dependencies, and compilation time.
4. Control annotation processing, plugins/compiler options, and artifact provenance.
5. Verify signatures/hashes when accepting prebuilt bytecode from external sources.
6. Communicate over RPC/schema rather than casting untrusted classes directly into the host's object graph.
7. Do not treat SecurityManager or a dedicated ClassLoader as a default security sandbox layer on Java 17+.

## 15. Debugging from Compiler Output to Defining Loader

If a new class “does not work”, diagnose it **stage by stage** instead of changing the classpath at random.

### Step 1 — Is the Compiler Available?

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
System.out.println(compiler != null);
~~~

If `false`, verify whether the running runtime includes a compiler provider and the `java.compiler` module; you may need to run with a full JDK or reconfigure the runtime image.

### Step 2 — What Do the Compiler Diagnostics Say?

Inspect `DiagnosticCollector`: error kind, line, column, message, and source URI. If the compile task returns `false`, execution has not even reached the class-loading step.

### Step 3 — Is the Expected Class-File Output Present?

~~~java
Map<String, byte[]> generated = files.snapshot();
System.out.println(generated.keySet());
~~~

This is an **illustrative snippet** requiring the `files` file manager object from the pipeline. If the needed class is `generated.Hello`, there must be an entry under that binary name. If the compiler generates nested classes, those additional entries must also be stored.

### Step 4 — Is the Parent Shadowing the New Class?

~~~java
Class<?> actual = loader.loadClass("generated.Hello");
System.out.println(actual.getClassLoader() == loader);
~~~

If `false`, parent-first delegation may have returned a class with the same binary name from the parent. Having the right class name does not prove the newly generated bytes were used.

### Step 5 — Inspect Metadata and Origin

~~~java
Class<?> type = loader.loadClass("generated.Hello");
System.out.println("type=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

These diagnostic snippets require the `loader` variable and appropriate imports.

When using classes from source/JARs, you can inspect `type.getProtectionDomain().getCodeSource()` if present; **generated in-memory classes do not automatically have a trustworthy CodeSource URL**. You should explicitly record the logical generation ID, source hash, compiler options, and bytecode hash in host-managed metadata/logs.

### Step 6 — If an Error Appears at Runtime

Distinguish between:

- `ClassNotFoundException`: the loader could not find the binary name.
- `NoClassDefFoundError`: a dependency could not be found during resolution, there is a class-name mismatch, or a prior initialization failed.
- `ClassFormatError`/`VerifyError`: the bytes/generator did not satisfy the JVM class format/verifier.
- `NoSuchMethodError`: the runtime dependency signature does not match the compiled version.
- `IllegalAccessError`: runtime package/module access is invalid.
- `ExceptionInInitializerError`: `static` initialization code ran and threw an error.
- `ClassCastException`: often related to runtime type identity when host/plugin have duplicate type definitions.

Do not treat all of the above as compiler bugs. Inspect the stack trace, cause chain, defining loader, source/bytes metadata, and the timing of load/link/initialize.

## 16. Common Mistakes

1. **“Generating a `byte[]` means you already have a runtime class.”** False: class definition in the JVM is still required.
2. **“`JavaCompiler.getTask` compiles immediately on its own.”** False: `call()` is what executes the task.
3. **“Successful compilation means all runtime dependencies are valid.”** False: the runtime loader may see a different version.
4. **“`defineClass` creates an object and runs the constructor.”** False: it defines the Class, whereas instance creation is a separate step.
5. **“A loader can redefine the same name to reload.”** False: a new generation loader or a specialized redefinition API is needed.
6. **“The same binary name and bytecode yield the same runtime type.”** False if the defining loader differs.
7. **“Any class can call `defineClass` directly on the system loader.”** False: it is protected final; a valid mechanism must be used.
8. **“`Lookup.defineClass` can define into any package/classloader.”** False: Lookup is tied to access privileges, package, and defining loader.
9. **“Classes defined by a custom loader automatically become named JPMS modules.”** False: they normally belong to the loader's unnamed module.
10. **“Resource lookup automatically reads the class-bytes map.”** False: `findClass` and `findResource` are separate API paths.
11. **“The compiler file manager is thread-safe because ClassLoader is thread-safe.”** False: these objects/states have separate concurrency contracts.
12. **“Caching `Class<?>` globally by name is good practice.”** False: it breaks loader identity and keeps old loaders alive.
13. **“`URLClassLoader.close()` immediately unloads all classes.”** False: it only closes loader resources; unloading depends on GC and references.
14. **“`-proc:none` makes user-supplied source safe.”** False: it only disables annotation processing during compilation; it does not sandbox runtime code.
15. **“`ToolProvider.getSystemJavaCompiler()` is guaranteed to be non-null.”** False for runtime images lacking the compiler.
16. **“`ClassNotFoundException` and `NoClassDefFoundError` are identical.”** False: they differ in stage and cause.
17. **“Adding `-classpath` to the compiler is sufficient for a named-module runtime.”** False: module resolution, layers, and readability/exports still apply.
18. **“The file `generated.Hello.class` is the class name to pass to `loadClass`.”** False: call it with `generated.Hello`; entry paths use `/`.
19. **“A class loader is a sandbox for running guest code.”** False: process/OS boundaries are needed if the code is untrusted.
20. **“Keeping generated classes in a static map forever has no consequences.”** False: it can cause Metaspace/heap pressure and plugin classloader leaks.

## 17. Production Checklist

- [ ] Clearly choose between **source compiler**, **bytecode generator**, or **proxy**; do not use generation when a simple strategy object suffices.
- [ ] Verify the compiler exists in the target runtime image; `--release` is compatible with the target JVM.
- [ ] Source name and public class/binary name match; the compiler output map includes all nested/helper classes.
- [ ] Diagnostics include line/column/message and do not leak sensitive data.
- [ ] File managers/streams are properly closed, with no uncontrolled sharing of mutable state.
- [ ] The parent loader defines shared interfaces/DTOs per the contract.
- [ ] Compilation classpath and runtime loader have compatible dependency versions.
- [ ] Generated bytes are an immutable snapshot before being handed to the loader.
- [ ] `loadClass`/`getClassLoadingLock`/`findLoadedClass` are not improperly bypassed.
- [ ] `defineClass` uses the correct binary name without abusing the protected API.
- [ ] Runtime module/package/access constraints are verified.
- [ ] Tests cover generated bytecode across different versions, corrupted class files, missing dependencies, and duplicate definitions.
- [ ] Compilation cache has bounds and single-flight behavior if multiple requests share the same source.
- [ ] Limits exist for CPU/heap/Metaspace, class count, source size, and compile timeout.
- [ ] Do not compile/load untrusted code in the same process.
- [ ] Have a generation/version ID and a transition mechanism that does not break in-flight requests.
- [ ] Have shutdown/drain logic to stop threads/plugin tasks and remove references to old loaders.
- [ ] Resources, SPI, TCCL, and caches are tested separately from class loading.
- [ ] JFR/JVM classloading metrics or logs are available to help diagnose leaks when needed.

## 18. Self-Check Exercises

**Question 1.** The Java source for `generated.Hello` is already in a String. Which API turns the source into bytes without manually writing the class-file format?

**Answer:** `javax.tools.JavaCompiler` with a `JavaFileObject` and an appropriate file manager. Call `getTask(...).call()` and collect the `.class` output.

**Question 2.** You need to load bytes into the JVM as a runtime class. Can you call `defineClass` directly on any ClassLoader?

**Answer:** Not from code without access rights, because `defineClass` is protected final. Typically you create a custom ClassLoader and override `findClass`, letting the standard `loadClass` coordinate loading.

**Question 3.** Two versions of the same binary name `generated.Hello` are compiled and defined in two separate loaders. Are the two `Class<?>` instances equal under `==`?

**Answer:** No. The JVM includes the defining loader in runtime type identity.

**Question 4.** A new class compiles successfully, but using it triggers `NoSuchMethodError`. What should you investigate?

**Answer:** The runtime dependency's defining loader/version, the compiled method descriptor, and binary compatibility—not just compiler diagnostics.

**Question 5.** Does replacing the `byte[]` in an old loader's map update an already-defined `Class<?>`?

**Answer:** No. You can create a new loader generation; instrumentation/redefinition has its own rules.

**Question 6.** A generated class implements a host SPI, yet the host cast fails even though the interface name is identical. What is the likely cause?

**Answer:** The two SPI versions were defined by different loaders. The shared API should be defined by a common parent.

**Question 7.** Why can `ToolProvider.getSystemJavaCompiler()` return `null`?

**Answer:** The compiler provider/module is absent from the runtime image or the environment does not provide a system compiler; a full JDK or a different configuration is needed.

**Question 8.** Does setting `-proc:none` in the demo make executing the generated code safe?

**Answer:** No. It only disables annotation processing during compilation; runtime code still runs with the process's permissions.

**Question 9.** Is `ClassLoader.close()` an API on every ClassLoader?

**Answer:** No. The base `ClassLoader` does not have `close()`; `URLClassLoader` implements `Closeable`. A custom loader storing bytes in RAM must manage references and its lifecycle appropriately.

**Question 10.** When compiled source also contains an inner class `Hello$Inner`, which outputs must be stored?

**Answer:** All class files emitted by the compiler, including `generated.Hello` and `generated.Hello$Inner` when present, keyed by binary names so the loader can locate them when the JVM needs them.

## 19. Decision Model

~~~text
Need dynamic behavior generation?
          |
          v
  Is a new Class needed?
      /             \
    No              Yes
      |               |
Lambda/strategy   Java source or direct bytecode?
                      /                   \
                   Source              Bytecode
                      |                   |
                JavaCompiler         ASM/... generator
                      |                   |
               Diagnostics +          validate class
               classfile bytes        file version
                      +---------+---------+
                                |
                         Loader generation
                                |
                    shared API from parent?
                                |
                    defineClass with exact name
                                |
                      Class<?> and instance
                                |
                 verify type identity/linkage
                                |
                metadata/cache/resource/lifecycle
                                |
                retire loader generation when done
~~~

**Summary:** Source/bytecode generation is the **data creation** step; JavaCompiler is the **class-file bytes production** step; ClassLoader is the **runtime type identity establishment** step. A sound dynamic class generation system must simultaneously design compiler diagnostics, classpath/versions, package/module access, loader concurrency, resource sources, and generation retirement mechanisms. Two classes with the same name can coexist thanks to two loaders, but you cannot “overwrite” an old class in the same loader like replacing a text file.

### Official Documentation

- [Java SE 17 — JavaCompiler API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 17 — JavaFileManager API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html)
- [Java SE 17 — SimpleJavaFileObject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [Java SE 17 — ClassLoader / defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — MethodHandles.Lookup.defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineClass(byte%5B%5D))
- [JVMS 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
