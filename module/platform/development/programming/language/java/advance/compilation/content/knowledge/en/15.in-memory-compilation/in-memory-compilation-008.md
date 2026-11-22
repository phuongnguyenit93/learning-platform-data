# The boundary between compiling bytecode and loading or executing bytecode in Java

When compiling Java **in memory**, we typically start from a source code string, invoke `JavaCompiler`, and receive one or more byte arrays representing `.class` files. However, **having bytecode does not mean the class has been loaded by the JVM or that the program has been executed**. The three steps have different purposes, APIs, errors, and lifecycles:

1. **Compilation:** analyzes Java code, resolves names/types, performs semantic checks, and generates bytecode according to the class file format. APIs: `javax.tools.JavaCompiler`, `JavaFileObject`, `JavaFileManager`.
2. **Loading and linking:** the JVM locates or receives class bytes, defines a runtime class associated with a class loader, verifies/prepares, and resolves references when needed. Common APIs: `ClassLoader`, `defineClass`, `Class.forName`.
3. **Initialization and execution:** the JVM runs static initializers when the class is initialized, calls constructors/methods, and executes bytecode; Java can use reflection or normal static calls to trigger behavior.

Distinguishing these three steps is crucial in IDEs, sandboxes, REPLs, plugin systems, template engines, and tools that compile source at runtime. Code that **compiles successfully** can still fail at class loading, verification, linking, initialization, or method invocation; a valid `byte[]` also does not generate side effects by itself.

## 1. Comparison table: three non-equivalent states

| Question | Compiling bytecode | Loading/linking classes | Executing bytecode |
| --- | --- | --- | --- |
| Primary input | `.java` or `JavaFileObject` containing source | Binary name and `.class` bytes/class source | Ready class/method/object |
| Primary output | `.class` bytes, diagnostics | `Class<?>` with identity of name + defining loader | Return value, side effect, exception |
| Dominant component | `javac` / `JavaCompiler` | JVM + `ClassLoader` | JVM execution engine, threads, and program |
| Can occur without running `main`? | Yes | Yes | Yes: calling a method other than `main` |
| Can fail independently? | Yes: type/syntax error | Yes: class version, verification, dependencies | Yes: logic, exception, initialization, I/O |
| Loads generated class into current loader? | **Not automatically** | Possibly, when requested | Uses defined class or triggers loading when needed |
| Means static initializer ran? | No | Not necessarily | When the class is **initialized** per JVM rules |

General diagram:

~~~text
String / .java / JavaFileObject
             |
             |  JavaCompiler.CompilationTask.call()
             v
     .class bytes in memory
             |
             |  ClassLoader.defineClass(...) or find class from path/JAR
             v
       JVM runtime Class
             |
             |  verification / preparation / resolution
             |  (some steps may occur eagerly or lazily)
             v
        Initialization
             |
             |  <clinit> if class requires initialization
             v
     Call method / new object / execution
             |
             v
     Results, side effects, exceptions
~~~

**Note:** the diagram is only a learning model. The JVM specification distinguishes **loading**, **linking** (verification, preparation, resolution), and **initialization**; resolution may occur lazily on demand. Do not assume all method/field references of a class have already been resolved right after `defineClass`.

## 2. What does CompilationTask.call() actually do?

In the Java Compiler API:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
JavaCompiler.CompilationTask task = compiler.getTask(
        null, fileManager, diagnostics,
        options, null, compilationUnits);
boolean success = Boolean.TRUE.equals(task.call());
~~~

This is a **fragment**, assuming variables already have appropriate types/imports. `task.call()` triggers the compilation task and returns the compile result. It can:

- Read `JavaFileObject` instances containing `.java` source or source in RAM.
- Parse syntax and check declared names, types, generics, overloads, accessibility, and checked exceptions.
- Run configured annotation processors (if enabled/available), which may generate additional sources and resources.
- Create class files via `JavaFileManager.getJavaFileForOutput(...)`; the file manager may write to disk or hold in RAM.
- Emit `Diagnostic` instances such as `ERROR` or `WARNING`.

**It does not automatically invoke `main`, does not call constructors/static initializers of newly generated classes, and does not automatically load that class into the running JVM.** `JavaCompiler` itself is a compiler implementation; processors can execute Java code at build time, but that is **processor code**, not running the newly compiled application.

### Source code is not bytecode

From the source:

~~~java
public final class Hello {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
~~~

After compiling successfully, bytecode contains symbolic references to `java.lang.System.out` and `PrintStream.println`. The statement `System.out.println("hello")` **has not executed** while the compiler merely produced `Hello.class`.

The compiler can also create **multiple** `.class` files from a single compilation unit: nested classes, anonymous classes, local classes, records, enums, and helper types. Therefore an in-memory file manager usually needs to store a **binary name → byte[] map**, not just a single buffer.

## 3. JavaFileObject and file managers: where bytes sit does not determine execution

`JavaCompiler` reads files through `JavaFileObject` and writes results through `JavaFileManager`. You can supply:

1. **Source on disk**: `StandardJavaFileManager.getJavaFileObjectsFromPaths(...)`.
2. **Source in RAM**: extend `SimpleJavaFileObject`, override `getCharContent(...)`.
3. **Class output on disk**: `StandardJavaFileManager` writes to `CLASS_OUTPUT`.
4. **Class output in RAM**: `ForwardingJavaFileManager` intercepts `getJavaFileForOutput(...)` and returns a `JavaFileObject` whose `openOutputStream()` writes into a `ByteArrayOutputStream`.

Output in RAM only changes **the compiler's I/O destination**. The resulting `Map<String, byte[]>` is data held by the host application; the JVM has not automatically defined classes from those bytes.

Example of class output:

~~~text
compile("demo.Dynamic")
       |
       v
Map<String, byte[]>
  "demo.Dynamic" -> CA FE BA BE 00 00 00 3D ...
       |
       +--> Can save artifact, inspect with ASM/javap, sign, verify
       |
       +--> Can create a custom ClassLoader to call defineClass
       |
       +--> Can discard bytes if only diagnostics are needed
~~~

`CA FE BA BE` is the class file magic number; `00 00 00 3D` corresponds to minor 0, major 61 (Java 17). These bytes are **not** a Java source text string. Decoding them as UTF-8 and calling `eval` is not how the JVM loads classes.

## 4. Standalone Java 17 example: compile in RAM → load → initialize → execute

The following example uses only JDK 17+ APIs without writing generated sources or class files to disk. Just create **one host file `InMemoryBoundaryDemo.java`**; it invokes the compiler, holds bytecode in a `Map`, and creates two separate class loaders.

**Complete file `InMemoryBoundaryDemo.java`:**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
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

public final class InMemoryBoundaryDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String source;

        Source(String binaryName, String source) {
            super(
                    URI.create("string:///"
                            + binaryName.replace('.', '/')
                            + Kind.SOURCE.extension),
                    Kind.SOURCE
            );
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return source;
        }
    }

    static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();

        ClassBytes(String binaryName, Kind kind) {
            super(
                    URI.create("mem:///"
                            + binaryName.replace('.', '/')
                            + kind.extension),
                    kind
            );
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] copyBytes() {
            return buffer.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> output = new HashMap<>();

        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            ClassBytes file = new ClassBytes(className, kind);
            output.put(className, file);
            return file;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            output.forEach(
                    (name, file) -> result.put(name, file.copyBytes()));
            return Map.copyOf(result);
        }
    }

    static final class BytesLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        BytesLoader(Map<String, byte[]> classes) {
            super(ClassLoader.getPlatformClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] bytes = classes.get(binaryName);
            if (bytes == null) {
                throw new ClassNotFoundException(binaryName);
            }
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler is unavailable");
        }

        String source = """
                package demo;

                public final class Dynamic {
                    static {
                        System.out.println("initialized");
                    }

                    public static String message() {
                        return "Hello from bytes";
                    }
                }
                """;

        Map<String, byte[]> compiled;
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (MemoryManager manager = new MemoryManager(
                compiler.getStandardFileManager(
                        null, Locale.ROOT, StandardCharsets.UTF_8))) {
            JavaFileObject unit =
                    new Source("demo.Dynamic", source);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(unit)
            );

            boolean ok = Boolean.TRUE.equals(task.call());
            System.out.println("compiled: " + ok);

            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(d.getMessage(Locale.ROOT));
                }
                return;
            }

            compiled = manager.snapshot();
        }

        System.out.println(
                "bytes present: " + compiled.containsKey("demo.Dynamic"));

        BytesLoader firstLoader = new BytesLoader(compiled);
        Class<?> firstClass = Class.forName(
                "demo.Dynamic", false, firstLoader);
        System.out.println("loaded: " + firstClass.getName());

        Object result = firstClass.getMethod("message").invoke(null);
        System.out.println("result: " + result);

        BytesLoader secondLoader = new BytesLoader(compiled);
        Class<?> secondClass = Class.forName(
                "demo.Dynamic", false, secondLoader);
        System.out.println("same class: " + (firstClass == secondClass));
    }
}
~~~

Compile and run the **host**, from the directory containing the file on JDK 17 or higher:

~~~bash
javac --release 17 -encoding UTF-8 InMemoryBoundaryDemo.java
java InMemoryBoundaryDemo
~~~

**Exact stdout under standard JDK 17+ conditions:**

~~~text
compiled: true
bytes present: true
loaded: demo.Dynamic
initialized
result: Hello from bytes
same class: false
~~~

The outputs reflect **actual boundaries**:

1. `compiled: true` means `JavaCompiler` completed the compilation. There is no `initialized` line yet because `Dynamic`'s static initializer **does not run during compilation**.
2. `bytes present: true` shows the file manager stored `demo.Dynamic.class` in RAM and returned a copied byte array.
3. `Class.forName("demo.Dynamic", false, firstLoader)` requests finding/defining the class without **requiring initialization**. Hence `loaded: demo.Dynamic` appears before `initialized`.
4. `firstClass.getMethod("message").invoke(null)` invokes the `static` method. This is an **active use** causing the JVM to initialize the class if not yet initialized. The static initializer prints `initialized`, and then the method returns `Hello from bytes`.
5. `secondLoader` defines a **different** runtime class with the same binary name. The result `firstClass == secondClass` is `false` because **the defining class loaders differ**.

The example intentionally selects `ClassLoader.getPlatformClassLoader()` as the parent for the custom loader. Because `demo.Dynamic` depends only on JDK base classes, platform/bootstrap delegation resolves dependencies and the loader can independently define `demo.Dynamic`. In projects with application dependencies, you must choose parent delegation or an appropriate class-lookup mechanism so the new class can see the needed types.

### A detail about closing resources

`MemoryManager` extends `ForwardingJavaFileManager`, and `try-with-resources` closes the manager along with its standard delegate. `snapshot()` creates a **bytecode copy** before the file manager is closed. Therefore the loader can load classes after the compile session has ended.

This is a clean boundary between compilation and execution phases: **do not keep the file manager alive just so the JVM can keep running compiled code**. In long-lived systems, manage the lifecycle of class loaders and objects they define separately.

## 5. ClassLoader, defineClass, and type identity

`ClassLoader` receives a request to load a binary name. When a custom loader locates bytes and calls:

~~~java
return defineClass(binaryName, bytes, 0, bytes.length);
~~~

The JVM defines a new class from bytecode if the format/identity and loading rules permit. This is a **fragment** inside a valid `findClass` method, not an API callable arbitrarily from anywhere without access. `defineClass` is a protected API on `ClassLoader` and checks multiple conditions, such as valid names and bytes.

Concepts to distinguish:

| Concept | Meaning |
| --- | --- |
| Binary name | For example `demo.Dynamic` or `pkg.Outer$Inner` |
| Defining loader | The loader that actually invokes class definition via a valid mechanism |
| Initiating loader | The loader initiating a class load request; may receive a class defined by its parent |
| Runtime class identity | **The pair (binary name, defining loader)** |
| `Class<?>` object | Runtime representation of a class defined by the JVM |
| Class file byte array | Data used to define a class; **not** a `Class<?>` |

Two classes with the same binary name created by **two different defining loaders** are two distinct runtime types. They do not cast to each other automatically. In a plugin system, clearly design shared classes/interfaces supplied by the parent, and separate implementation classes defined by plugin loaders.

### Parent delegation can change the outcome

A default custom loader usually uses parent-first delegation: `loadClass` asks the parent first, and only calls `findClass` if the parent cannot return the class. If the parent has already defined `demo.Dynamic` with the same binary name, `findClass` on the custom loader may **not be called**. The experiment uses a dedicated `demo` package and platform parent to avoid that collision.

If implementing a child-first loader or overriding `loadClass`, you must understand thread safety, package sealing, code sources, security, and shared APIs; do not simply flip ordering to load any arbitrary class.

### "Not yet initialized" does not mean "not yet verified"

Calling `Class.forName(name, false, loader)` does not request class initialization, yet the JVM may perform verification/linking **before init** according to implementation rules. Therefore, you cannot say every class-file error only appears when invoking a method. A class with corrupted bytecode can be rejected immediately during define/link, whereas an invalid symbolic reference might only fail when the relevant instruction is resolved later.

## 6. Loading, linking, initialization according to the JVM Specification

Related phases:

### 6.1. Loading

The JVM receives a class request and looks up the class definition: from files/JARs/modules, or bytes supplied by a user-defined loader. The class file must have an acceptable format; a wrong class version can cause `UnsupportedClassVersionError`, and corrupted bytecode can cause `ClassFormatError`.

### 6.2. Linking

Typically divided into:

- **Verification:** verifies the class file/bytecode against JVM constraints; failures can raise `VerifyError`.
- **Preparation:** allocates/initializes default values for static fields (with exceptions/rules regarding constant values). **Does not mean running source static initializers**.
- **Resolution:** resolves symbolic references from the constant pool to corresponding classes/fields/methods; may be eager or lazy within specification bounds.

Errors such as `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, or `IncompatibleClassChangeError` arise during linking/resolution or when an instruction using a broken reference executes.

### 6.3. Initialization

When a class begins initialization under active-use rules, the JVM executes the class initialization method (`<clinit>`) if needed, running static field initializers and static blocks in the appropriate order. This is when the program may print text, spawn threads, open connections, or throw exceptions due to static initializer code.

Example:

~~~java
class Example {
    static int number = initialize();

    static int initialize() {
        System.out.println("init");
        return 42;
    }
}
~~~

Merely compiling this class does not print `init`. Class initialization triggers such as calling static method `Example.initialize()` can cause `init` to be printed before the method call finishes. This snippet is **illustrative** and lacks a `main` to run standalone.

**Not every reference to `Example` forces immediate initialization.** The class literal `Example.class` can obtain a Class object without initializing the class. `Class.forName(name, true, loader)` **requires initialization**; `Class.forName(name, false, loader)` does not.

## 7. Reflection: invoking loaded code, not compiling

Once you have a `Class<?>`, reflection can find and invoke constructors or methods:

~~~java
Class<?> type = Class.forName(
        "demo.Dynamic", false, myLoader);
Object result = type.getMethod("message").invoke(null);
~~~

This is a fragment inside a method with a valid `myLoader`; `message()` must be public, static, and parameterless for the call to match the example. `getMethod` finds a public method by name and parameters; `invoke` executes the method (with corresponding access checking and exception wrapping).

If the method throws an exception, reflection may throw `InvocationTargetException` wrapping the cause from the method; read `getCause()` to see the application error. Reflection **is not used to generate bytecode** and cannot "add methods" to a loaded class. It only finds/calls methods present in the runtime class.

### Reflection is not required to execute bytecode

You can compile source to `.class` files on disk, then run:

~~~bash
javac --release 17 Hello.java
java Hello
~~~

Or another class with an explicit compile-time type can call it directly:

~~~java
Hello.main(new String[0]);
~~~

The latter is a fragment and requires `Hello` to be on the compile/runtime classpath. Reflection is more necessary when the host **does not know the type in advance** or when classes are loaded from bytes via custom loaders. The difference lies in **how the API is invoked and linked**, not in how "real" bytecode execution is.

## 8. Valid ClassFile bytes do not guarantee runtime success

A byte array starting with `CAFEBABE` and having a runtime-supported major version can still fail:

| Phase | Scenario | Possible error |
| --- | --- | --- |
| Compile | Syntax error, type not found, unhandled checked exception | `ERROR` diagnostics, `task.call() == false` |
| Define/load | Truncated/corrupted or non-conforming class file | `ClassFormatError` |
| Define/load | Class file version higher than runtime JVM or mismatched preview | `UnsupportedClassVersionError` |
| Verification | Bytecode violates verifier constraints | `VerifyError` |
| Resolution/linking | Dependent class not found when needed | `NoClassDefFoundError` |
| Resolution | Method/field referenced by bytecode no longer exists | `NoSuchMethodError` / `NoSuchFieldError` |
| Resolution/access | Incompatible class/member change or inaccessible member | `IncompatibleClassChangeError` / `IllegalAccessError` |
| Initialization | Static initializer throws exception | `ExceptionInInitializerError` (along with failed-init rules) |
| Execution | Business exception thrown by executed code | E.g., `IllegalArgumentException` or `IOException` |
| Reflection invocation | Invoked code throws exception | `InvocationTargetException` wrapping cause |

**Do not treat the table as an absolute one-to-one mapping.** Some linkage errors occur eagerly or lazily depending on how the JVM resolves references; the same exception type can appear at multiple points. What matters is identifying **whether it belongs to compile time or runtime class loading/linking/execution** before attempting a fix.

For example, `task.call() == true` yet class loading throws `UnsupportedClassVersionError` if the compilation host targets a newer release than a different runtime. If the compiler and loader run on the same JDK 17 and target `--release 17` as in the experiment, that mismatch does not happen under normal conditions; other classpath or bytecode issues can still arise in complex builds.

## 9. Runtime errors from static initializers: proof the compiler does not run the application

Create the standalone file **`InitFailureDemo.java`**:

~~~java
public final class InitFailureDemo {
    static final class Broken {
        static {
            System.out.println("Broken initializing");
            if (System.nanoTime() != Long.MIN_VALUE) {
                throw new IllegalStateException("bad static state");
            }
        }

        static void run() {
            System.out.println("never reached");
        }
    }

    public static void main(String[] args) {
        System.out.println("before initialization");
        try {
            Broken.run();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("initialization failed");
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 InitFailureDemo.java
java InitFailureDemo
~~~

**Exact stdout when the program executes the failure branch:**

~~~text
before initialization
Broken initializing
initialization failed
~~~

This illustrates the initialization flow with a runtime condition almost certainly unequal to `Long.MIN_VALUE`; to avoid relying on a rare clock condition, you can replace the condition with a method always returning true that the compiler does not evaluate as a compile-time constant. In normal practice, `System.nanoTime() != Long.MIN_VALUE` holds. If you want **completely deterministic** output in every environment, use the following version:

~~~java
public final class InitFailureDemo {
    static final class Broken {
        static {
            System.out.println("Broken initializing");
            fail();
        }

        private static void fail() {
            throw new IllegalStateException("bad static state");
        }

        static void run() {
            System.out.println("never reached");
        }
    }

    public static void main(String[] args) {
        System.out.println("before initialization");
        try {
            Broken.run();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("initialization failed");
        }
    }
}
~~~

**This is a complete replacement for `InitFailureDemo.java`** with the exact same three-line output above. `javac` does not call `Broken.fail()` during compilation; only when `Broken.run()` becomes an active use does the JVM initialize `Broken` and the exception occurs. Do not put both versions in the same file.

When class initialization fails, the class is typically marked erroneous for its defining loader. Subsequent active uses may trigger `NoClassDefFoundError` with a cause linked to the earlier initialization failure; do not blindly create a retry loop on the same class loader expecting the static initializer to rerun.

## 10. In-memory compilation: multiple classes and dependency classpaths

The experiment in section 4 had one output class. Real projects may produce many types:

~~~text
source input:
  pkg.Service.java

generated bytecode:
  pkg.Service.class
  pkg.Service$Helper.class
  pkg.Service$1.class
~~~

Therefore the file manager should store outputs by **binary name** or a key containing location, kind, and name to avoid collisions. When a processor generates resources, you must also handle `getFileForOutput(...)` if keeping all outputs in memory. Overriding only `getJavaFileForOutput(...)` in the example suffices for **class output**, yet **is not a complete in-memory file manager for sources/resources generated by annotation processors**.

Points to distinguish:

- **Compiling new code against libraries already on disk**: a custom file manager can forward lookups to `StandardJavaFileManager`.
- **Compiling new code depending on classes just compiled in RAM in an earlier task**: the later compiler task will not automatically find those classes if the file manager only holds `byte[]` without exposing them to compiler lookup.
- **Running code compiled in RAM**: a custom class loader needs bytes of all related types and an appropriate parent for dependencies.
- **Keeping outputs isolated across compilation sessions**: manage versions/caches/identities and binary name collisions carefully.

Example: Task 1 generates `lib.Calculator.class` in a `Map`. Task 2 needs to import `lib.Calculator`. Simply putting that `Map` into the runtime `BytesLoader` **does not** cause task 2's `javac` to find `Calculator`. The file manager for task 2 must provide the corresponding `JavaFileObject.Kind.CLASS` (and lookup/listing when requested by the compiler), or compile the dependency to a valid classpath directory, or submit both sources in the same compilation task.

**Compile-time lookup and runtime class loading boundaries are independent.**

## 11. Separating compile sessions and load sessions in long-running applications

A REPL or IDE system typically has:

~~~text
[Source input v1] -> [Compiler task 1] -> [bytecode v1]
                                          |
                                     [Loader A]
                                          |
                                      Class A

[Source input v2] -> [Compiler task 2] -> [bytecode v2]
                                          |
                                     [Loader B]
                                          |
                                      Class B
~~~

If v2 shares the same binary name as v1, using the new version typically requires creating a **new loader** that defines the new class. Overwriting the byte array in the map of a loader that already defined the old class does not replace that definition.

The hard parts:

1. **Unloading an old class loader** is only possible once no live references remain from threads, instances, Class/Method objects, caches, ThreadLocals, static registries, and similar mechanisms. Class unloading is performed by the GC, not immediately when a method is called.
2. **Sharing interfaces/APIs between loaders**: place common interfaces in a stable parent/loader so plugin objects can be cast through shared interfaces.
3. **Resource isolation**: a class loader controls both class lookup and resource lookup; do not rely on an arbitrary context loader when requiring resources from specific bytes/plugins.
4. **Recompiling multiple dependent sources**: when an ABI changes, already-compiled v1 classes may be incompatible with v2 APIs even if the new loader loads them.
5. **Diagnostic and artifact lifecycles**: store by compilation ID, and never mix bytecode from a failed compilation with a previous build.

Do not use a single unversioned global map and swap bytes while threads are running; defining classes, resolving symbolic references, and executing code follow lifecycles distinct from map contents.

## 12. Security: compiling does not turn source into a safe sandbox

**This is a critical safety boundary.** A host program can compile user source without executing the new classes; that does not mean user source is always harmless, especially when **annotation processing** or compiler plugins are enabled. Processors can execute Java code during compilation.

And once the host deliberately loads/invokes bytecode, the new code can:

- Access files, network, or resources permitted to the host process.
- Spawn threads, consume CPU/memory, and mutate static/shared state.
- Call other APIs in the runtime depending on accessibility.
- Interact with the context class loader, reflection, or native libraries depending on configuration.

A custom `ClassLoader` **is not a sufficient security isolation mechanism** for running untrusted Java code. Class loaders primarily handle **namespaces and class lifecycles**. The Java Security Manager has been restricted/removed in modern releases; do not rely on it as a general sandbox for untrusted code.

For systems allowing third-party code compilation and execution, prefer **process/container isolation according to environment policies**: restrict file/network permissions, CPU/time/memory, process/thread counts, user privileges, temp directories, and lifetimes, while disabling untrusted annotation processors/plugins during compilation or running compilation inside an equivalently isolated environment. These measures are **system architecture**, not replaceable by `ClassLoader#defineClass`.

### Distinguishing processor compile-time activity from app runtime

`JavaCompiler` itself runs a compilation pipeline. If a processor is discovered/specified and runs inside the host JVM, **processor code** can produce side effects **during compilation**, even if you never load the compiled classes. Therefore, the phrase "compiling does not run code" must be understood precisely as **not running the newly compiled application's methods/initializers as a program**, not a guarantee that zero code is executed by the compiler/tooling.

To avoid unintended processor discovery in the simple example, the code uses `-proc:none`. This is an illustrative choice when annotation processing is unnecessary; in builds requiring processors, manage processor paths and trusted sources deliberately.

## 13. Modules, packages, and API limits when loading bytecode

### Package names and defineClass

`defineClass(binaryName, bytes, ...)` requires the bytecode to have the matching class name. If you pass bytes for `demo.Dynamic` with `binaryName` set to `demo.Other`, the JVM may throw class-name errors such as `NoClassDefFoundError: wrong name` or related errors. Do not use arbitrary filenames as binary names.

Classes in restricted packages such as `java.*` cannot be defined freely by user class loaders. Package sealing and signer/certificate constraints can also apply when multiple sources define classes in the same package.

### The JPMS module path does not transfer automatically to a custom loader

If new bytecode depends on a named module, the host must design module readability/exports/opens and module layers when needed; loading bytes through a custom class loader **does not automatically resolve the full module graph**.

A class defined normally via `defineClass` in a user-defined loader typically belongs to that loader's unnamed module, with corresponding module/access rules applying. Reflection remains subject to Java accessibility and module encapsulation. Seeing a method via `getDeclaredMethod` does not guarantee `invoke` is permitted without access rights.

### Hidden classes

Since Java 15, `MethodHandles.Lookup.defineHiddenClass(...)` provides a mechanism to define hidden classes for needs such as frameworks/language runtimes. They have different identity, lookup visibility, and lifecycles compared to classes with ordinary binary names. Hidden classes are **not needed** to learn the compiler → bytes → loader boundary in this lesson. If building complex dynamic runtimes, study the purpose-built API rather than blindly applying hidden classes as a simple replacement for a file manager.

## 14. Diagnosing by symptom

| Symptom | Boundary to check | Investigation direction |
| --- | --- | --- |
| `task.call() == false` | Compile | Read `DiagnosticCollector`, source level, dependencies, and JavaFileManager |
| Compilation succeeds but map is empty | File manager output | Was `getJavaFileForOutput` called? Right kind/location? Stream closed? |
| `ClassNotFoundException` on `Class.forName` | Load/lookup | Binary name, parent delegation, loader map, and dependencies |
| `NoClassDefFoundError` | Load/link/initialization | Dependent class available? Earlier class init error? Cause/stack trace |
| `ClassFormatError` / `VerifyError` | Define/verification | Are bytes valid? Truncated or written under wrong kind? |
| `UnsupportedClassVersionError` | Load | Inspect major/minor version, compare `--release` target and runtime JVM |
| `NoSuchMethodError` | Linking/ABI | Runtime class differs from compile-time API? Check method descriptor |
| `ExceptionInInitializerError` | Initialization | Static initializer/cause, first active use |
| `InvocationTargetException` | Reflective execution | Read `getCause()`; exception came from target method |
| Bytes changed yet behavior stays the same | Loader lifecycle | Class already defined; create a new loader or reload via valid mechanism |
| `ClassCastException` despite same class name | Loader identity | Compare defining loaders of both types |
| Runtime cannot find resource | Loader/resource lookup | `getResourceAsStream`, package path, and resource output in manager |
| Compiler task 2 does not see task 1 class | Compile-time class lookup | Forwarding file manager lacks RAM lookup or missing classpath |
| Process hangs/OOMs after invoke | Execution/isolation | Enforce time/resource limits at process boundary, not just class loader |

### Ordered debugging checklist

1. **Is the compiler available?** `ToolProvider.getSystemJavaCompiler()` can be `null` on a runtime image lacking a compiler.
2. **Are inputs correct?** `JavaFileObject` URI, source content, encoding, classpath/module path.
3. **Did the compile task succeed?** Check `Boolean.TRUE.equals(task.call())` and diagnostics (do not inspect just one log line).
4. **Are output bytes real?** Does the map contain the exact binary name, classfile header, and reasonable size? Are there other generated classes?
5. **Which loader is used?** Did parent-first pick up another class with the same name? Was `defineClass` invoked?
6. **Has the class initialized yet?** Use `Class.forName(name, false, loader)` when observing the pre-init loading phase.
7. **What did the first call fail with?** Distinguish `LinkageError`, `ExceptionInInitializerError`, and `InvocationTargetException`.
8. **Are runtime dependencies loaded/visible?** Compile classpath and loader classpath are two independent configurations.
9. **Is reloading happening?** When source changes, classes in the old loader do not update automatically.
10. **Is untrusted code involved?** Manage processors and runtime execution with appropriate process isolation/throttling.

## 15. Self-check exercises

**Exercise 1.** After `task.call() == true`, before creating a custom loader or calling `java`, has the static initializer in the newly compiled source run?

**Answer:** No, not from the compilation task alone. The compiler produces bytecode rather than actively initializing newly generated application classes. Note that annotation processors, if enabled, are tooling code that can run during compilation.

**Exercise 2.** `Class.forName("demo.Dynamic", false, loader)` returns `Class<?>`. Does that guarantee the static initializer has run?

**Answer:** No. `initialize=false` does not request class initialization. The JVM may still perform verification/linking as needed.

**Exercise 3.** The same `byte[]` defines `demo.Dynamic` across two different defining class loaders. Are the two `Class<?>` objects `==`?

**Answer:** No, when each loader defines its own class and does not delegate to a single parent definition. Class identity equals binary name + defining loader.

**Exercise 4.** Why doesn't a `Map<String, byte[]>` produced by task 1 automatically let task 2's `javac` find that class?

**Answer:** Compiler lookup operates through `JavaFileManager` and source/class search paths. Runtime BytesLoader is a separate mechanism; for task 2 to see the class, supply bytes via the file manager/classpath or compile the sources together.

**Exercise 5.** When calling a method with `Method.invoke` and the method throws `IllegalArgumentException`, what does host code typically catch?

**Answer:** `InvocationTargetException` wrapping the exception thrown by the target method; use `getCause()` to see the underlying error. Reflection itself may also throw distinct exceptions due to lookup/access/arguments.

**Exercise 6.** A new class was compiled with `--release 21`, while the JVM loader runs on Java 17. What can happen?

**Answer:** A Java 17 JVM does not support Java 21's major class file version 65, so it may throw `UnsupportedClassVersionError` when loading the class. Either target a compatible release or use a sufficiently recent runtime.

**Exercise 7.** Can a custom ClassLoader be treated as a secure sandbox for running untrusted Java source?

**Answer:** No. Loaders establish class namespaces and do not automatically restrict I/O, CPU, network, or native access under a security policy. For untrusted code, design isolation at the process/OS/container level.

**Exercise 8.** Why can `Class.forName(name, true, loader)` and `Class.forName(name, false, loader)` yield different output ordering with static blocks?

**Answer:** The `true` variant requests initialization, so the static block may run during that call; the `false` variant does not request initialization, so the static block typically runs upon a subsequent active use.

## Key takeaways

- **Successful compilation produces bytecode**; it does not automatically mean the JVM has loaded, linked, initialized, or executed that class.
- **In-memory file managers** store class files as bytes; a **ClassLoader** must be used to define classes; **method/constructor invocations** are what run application logic.
- **Loading/linking/initialization differ**: `Class.forName(..., false, ...)` lets you observe the boundary before init; reflectively invoking a static method can trigger init.
- **Runtime class identity = binary name + defining loader**. Identical bytes defined by two different loaders remain two distinct runtime types.
- **Compiler classpaths and runtime loader dependencies are independent**; when compiling multiple rounds in RAM, supply earlier outputs to compiler lookup as well if needed.
- **Compiling untrusted code still carries risks when processors/plugins execute**, and loading/executing bytecode does not become a sandbox merely via a custom class loader.
- When an error occurs, identify whether it belongs to **compile, define/load, verification/linking, initialization, or invocation** to address the true cause.