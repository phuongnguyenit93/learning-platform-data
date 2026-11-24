# Checking Assignability and Instantiating Objects via an Appropriate Constructor

## 1. The Problem in an In-Memory Java Compilation Pipeline

When an application receives Java source code as a string, compiles it using `JavaCompiler`, and loads the bytecode through a dedicated `ClassLoader`, the result is usually just a `Class<?>` object. **Successful compilation** means the code is valid with respect to the compiler and visible dependencies; it **does not guarantee** that the compiled class is the implementation expected by the host, can be instantiated, or has a constructor matching the host's protocol.

For example, the host defines a contract:

~~~java
public interface Plugin {
    String greet(String name);
}
~~~

The host wants to create a plugin from a binary name such as `demo.generated.WithPrefix`, passing a configuration parameter `String prefix` if the class has that constructor, or a no-argument constructor if it does not. These questions must be handled in the proper order:

1. Did compilation succeed and actually produce bytecode?
2. Which loader defined the class from the bytecode? Does it share **the host's exact `Plugin` class/interface**?
3. Is the loaded `Class<?>` **assignable** to `Plugin`?
4. Can that class be instantiated (for instance, is it not an interface, abstract class, or enum that cannot be instantiated reflectively)?
5. Which constructor matches the **expected signature**, is accessible, and is permitted to be invoked?
6. Does `Constructor.newInstance(...)` execute successfully, and can the resulting instance be used according to the contract?

The type-safe workflow is:

~~~text
Source String
    │
    ▼
JavaCompiler + JavaFileManager
    │ succeeds and produces byte[]
    ▼
Memory ClassLoader (parent shares the Plugin API)
    │
    ▼
Class<?> candidate (loaded but not eagerly initialized)
    │
    ├── incompatible with Plugin → reject
    ├── interface/abstract/non-instantiable → reject
    ▼
Class<? extends Plugin> (asSubclass)
    │
    ├── select public constructor(String.class), if present
    └── otherwise select public constructor()
    │
    ▼
Constructor.newInstance(...)
    │
    ▼
Plugin instance → invoke methods via shared SPI
~~~

**Lesson scope:** how to check assignability and perform appropriate instantiation **after compiling/loading bytecode in memory**. The compiler, file manager, and loader are shown sufficiently to run the example, while the focus is the boundary `Class<?>` → `Class<? extends Plugin>` → `Constructor` → instance.

## 2. Checking Assignability Before Casting

### 2.1. Argument Order of `isAssignableFrom`

The right expression when you need an implementation of `Plugin`:

~~~java
boolean accepted = Plugin.class.isAssignableFrom(candidate);
~~~

Meaning: can a value of runtime type `candidate` be assigned to a variable of type `Plugin` via a valid reference conversion? If `candidate` implements `Plugin`, extends a class that implements `Plugin`, or is `Plugin` itself, the result is `true`. The case where `candidate` **is the `Plugin` interface itself** must be checked separately because an interface cannot be instantiated.

It is easy to write it backwards:

~~~java
boolean reversed = candidate.isAssignableFrom(Plugin.class); // Wrong goal
~~~

The reversed call asks "can a value of type `Plugin` be assigned to type `candidate`?", which is usually wrong when `candidate` is a concrete implementation. A reversed type check can reject valid implementations or mistakenly accept a superclass like `Object`.

Comparison:

| `candidate` | `Plugin.class.isAssignableFrom(candidate)` | Can an instance be created directly? |
|---|---|---|
| `WithPrefix implements Plugin` | `true` | Yes, if class/constructor are valid |
| `Defaulted implements Plugin` | `true` | Yes, if class/constructor are valid |
| `Unrelated`, does not implement `Plugin` | `false` | Must not enter the plugin instantiation branch |
| `Plugin` interface | `true` | No, an interface cannot be instantiated with `new` |
| Abstract class implementing `Plugin` | `true` | No, an abstract class cannot be instantiated |
| Enum implementing `Plugin` | `true` | An enum cannot be instantiated reflectively via a constructor |

`Class.isAssignableFrom` checks the **type relationship at JVM runtime**, not merely comparing class or package names. It does not guarantee a suitable constructor exists, that dependencies are working, or that instantiation will be free of side effects.

### 2.2. `asSubclass` Produces a Type-Bounded Class

After confirming:

~~~java
if (!Plugin.class.isAssignableFrom(candidate)) {
    throw new IllegalArgumentException("Incompatible class");
}
Class<? extends Plugin> implementation =
        candidate.asSubclass(Plugin.class);
~~~

`Class.asSubclass(Plugin.class)` verifies at runtime and returns `Class<? extends Plugin>`, allowing you to obtain `Constructor<? extends Plugin>` and create a properly typed instance **without unchecked generic casts**. If incompatible, `asSubclass` throws `ClassCastException`. Checking `isAssignableFrom` first helps return an intentional error and distinguish host policy from a cast error.

If you already have an **object** instead of a `Class<?>`, you can use `Plugin.class.isInstance(value)` and `Plugin.class.cast(value)`. However, `isInstance` requires an existing instance; in this lesson, we must evaluate the class **before calling the constructor**.

### 2.3. The Class Loader Determines Type Identity

In the JVM, a class's runtime identity consists of its **binary class name** and **defining class loader**. Two interfaces both named `demo.api.Plugin` but defined by two different loaders can be two incompatible types:

~~~text
Host parent loader:  demo.api.Plugin  (type A)
Plugin child loader: demo.api.Plugin  (type B)
                                 A != B
~~~

If `candidate` implements "Plugin type B" while the host checks "Plugin type A", `Plugin.class.isAssignableFrom(candidate)` returns `false` even though `candidate.getInterfaces()[0].getName()` looks identical. Therefore, **do not** validate using `getName().equals(...)`.

In typical plugin systems, the parent loader of the in-memory compilation loader should point to the loader that defined the **host's API/SPI** (for example, `Plugin.class.getClassLoader()`). The host avoids compiling/defining a duplicate copy of the contract interface inside the memory loader unless it has explicitly designed a bridge between two distinct identities.

## 3. Loading Classes at the Right Time, Avoiding Premature Initialization

After compilation, the host usually knows `binaryName` and has a new `ClassLoader`. You can use:

~~~java
Class<?> raw = Class.forName(binaryName, false, memoryLoader);
~~~

The `false` argument requests **not eagerly initializing the class** on this call. That lets you inspect the type, modifiers, and constructors before triggering the implementation's static initializer in the later instantiation step. It does **not** render loading/linking harmless: verification, resolution, lookup, and class-loader code can still fail or exhibit side effects.

Another option is `memoryLoader.loadClass(binaryName)`, which also typically does not initialize the class immediately. Do not use `Class.forName(binaryName)` without passing a loader when the application manages plugins in separate loaders: that overload uses the **caller's defining loader** and requests initialization by default, which can look up the wrong class or throw an error because that loader cannot see the bytecode.

Reading metadata before instantiating:

~~~java
if (raw.isInterface()
        || java.lang.reflect.Modifier.isAbstract(raw.getModifiers())) {
    throw new IllegalArgumentException("Not a concrete plugin");
}
~~~

Production systems should also consider rejecting `isEnum()`, anonymous/local classes, non-public implementations if the contract accepts only public classes, or types outside allowed packages/modules. **A passing assignability check does not replace instantiation policy checks.**

## 4. Choosing a Constructor Matching the Contract

### 4.1. `getConstructor` Finds a Public Constructor with an *Exact* Signature

If the host prefers a constructor taking `String`:

~~~java
Constructor<? extends Plugin> constructor =
        implementation.getConstructor(String.class);

Plugin plugin = constructor.newInstance("Xin chao");
~~~

`getConstructor(String.class)` looks up a **public** constructor with a single parameter declared as `java.lang.String`. It does not perform overload resolution according to the rules the Java compiler uses when you write a `new` expression in source code.

For example:

~~~java
public WithPrefix(String prefix) { ... }
public WithPrefix(CharSequence text) { ... }
public WithPrefix(int count) { ... }
~~~

Those three constructors are three distinct signatures. `getConstructor(String.class)` picks the exact `String` branch. `getConstructor(CharSequence.class)` is not equivalent to finding the `String` constructor, and `getConstructor()` finds the **no-arg** constructor without supplying default arguments automatically.

`Constructor.newInstance(args...)` invokes the chosen constructor and converts arguments according to reflection rules; if the argument count or types are wrong, it can throw `IllegalArgumentException`. Ideally, the host establishes a **specific constructor contract** upfront (e.g., `(Config)`, `(String)`, or `()`) and looks up that exact signature, rather than arbitrarily picking the first constructor from `getConstructors()`.

### 4.2. Reasonable Fallback: Only When the Preferred Constructor *Does Not Exist*

~~~java
try {
    Constructor<? extends Plugin> preferred =
            implementation.getConstructor(String.class);
    return preferred.newInstance(prefix);
} catch (NoSuchMethodException missingPreferred) {
    Constructor<? extends Plugin> fallback =
            implementation.getConstructor();
    return fallback.newInstance();
}
~~~

Key point: the `catch` block catches only **`NoSuchMethodException`** from **not finding the signature**. If the `String` constructor exists but fails during execution (for instance, throws an exception), **do not silently fall back to calling the default constructor**, because doing so masks the real error and can repeat side effects.

`getConstructor()` can also throw `NoSuchMethodException` if there is no public no-arg constructor. In that case, the host should return a clear "no matching constructor" error rather than falling back to `Class.newInstance()`.

### 4.3. `getDeclaredConstructor` and Module Access

`getDeclaredConstructor(...)` finds constructors **declared** on the class, including private/package-private ones; obtaining the descriptor does not automatically grant permission to invoke it. `getConstructor(...)` finds only public constructors by signature. In a public-SPI plugin model, prefer **public class + public constructor** to reduce reliance on reflection that breaks encapsulation.

`setAccessible(true)` or `trySetAccessible()` is not a universal fix for access errors. With JPMS named modules, deep reflection is also constrained by `opens`, caller modules, and access rules; missing permissions can raise `InaccessibleObjectException` or `IllegalAccessException`. Do not automatically open every package just because a plugin load failed.

### 4.4. Why Not Use `Class.newInstance()`?

`Class.newInstance()` has been deprecated since Java 9. It only invokes the no-arg constructor and handles checked exceptions less cleanly. The recommended APIs are `clazz.getDeclaredConstructor().newInstance()` when appropriate, or `getConstructor(signature...).newInstance(args...)` per contract. When you need to select an appropriate constructor, the `Constructor` API expresses the requirement far more accurately.

## 5. Complete Java 17+ Example: Compile Bytecode in Memory, Check Types, and Instantiate

The following example **compiles and runs standalone** with JDK 17+. It creates three dynamic classes from source strings:

1. `WithPrefix` implements `Plugin` and has a public `(String)` constructor.
2. `Defaulted` implements `Plugin` and has only a public no-arg constructor.
3. `Unrelated` does not implement `Plugin` and must be rejected **before calling any constructor**.

The host code `InMemoryCtorDemo` is compiled normally into the `out` directory; **the three dynamic classes** have their bytecode emitted into `ByteArrayOutputStream` by the compiler and defined by a custom loader, without writing `.class` files to disk.

### 5.1. Create the File

Save the entire code below into **`demo/InMemoryCtorDemo.java`** (the `demo` directory matches the `package demo` declaration). Java text blocks used here exist since Java 15 and are compatible with Java 17.

~~~java
package demo;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryCtorDemo {
    public interface Plugin {
        String greet(String name);
    }

    public static void main(String[] args) throws Exception {
        String withPrefix = """
                package demo.generated;
                import demo.InMemoryCtorDemo.Plugin;
                public final class WithPrefix implements Plugin {
                    private final String prefix;
                    public WithPrefix(String prefix) { this.prefix = prefix; }
                    public String greet(String name) { return prefix + ", " + name + "!"; }
                }
                """;
        String defaulted = """
                package demo.generated;
                import demo.InMemoryCtorDemo.Plugin;
                public final class Defaulted implements Plugin {
                    public Defaulted() {}
                    public String greet(String name) { return "Hello, " + name + "!"; }
                }
                """;
        String unrelated = """
                package demo.generated;
                public final class Unrelated {
                    public Unrelated() {}
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        Map<String, byte[]> classBytes;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8);
             MemoryManager manager = new MemoryManager(standard)) {
            List<JavaFileObject> sources = List.of(
                    new Source("demo.generated.WithPrefix", withPrefix),
                    new Source("demo.generated.Defaulted", defaulted),
                    new Source("demo.generated.Unrelated", unrelated));
            Boolean ok = compiler.getTask(null, manager, diagnostics,
                    List.of("--release", "17", "-classpath",
                            System.getProperty("java.class.path"), "-proc:none"),
                    null, sources).call();
            if (!Boolean.TRUE.equals(ok)) {
                diagnostics.getDiagnostics().forEach(System.err::println);
                throw new IllegalStateException("Compilation failed");
            }
            classBytes = manager.classBytes();
        }

        ClassLoader loader =
                new MemoryClassLoader(Plugin.class.getClassLoader(), classBytes);
        Class<?> with = Class.forName("demo.generated.WithPrefix", false, loader);
        System.out.println("WithPrefixAssignable=" + Plugin.class.isAssignableFrom(with));
        Plugin first = createPlugin(with, "Xin chao");
        System.out.println("WithPrefix=" + first.greet("Java"));

        Class<?> fallback = Class.forName("demo.generated.Defaulted", false, loader);
        System.out.println("DefaultedAssignable=" + Plugin.class.isAssignableFrom(fallback));
        Plugin second = createPlugin(fallback, "unused");
        System.out.println("Defaulted=" + second.greet("Java"));

        Class<?> other = Class.forName("demo.generated.Unrelated", false, loader);
        System.out.println("UnrelatedAssignable=" + Plugin.class.isAssignableFrom(other));
        boolean rejected = false;
        try {
            createPlugin(other, "unused");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("UnrelatedRejected=" + rejected);
    }

    private static Plugin createPlugin(Class<?> raw, String argument)
            throws ReflectiveOperationException {
        if (!Plugin.class.isAssignableFrom(raw)) {
            throw new IllegalArgumentException("Not a Plugin: " + raw.getName());
        }
        if (raw.isInterface() || Modifier.isAbstract(raw.getModifiers())) {
            throw new IllegalArgumentException("Not concrete: " + raw.getName());
        }

        Class<? extends Plugin> type = raw.asSubclass(Plugin.class);
        try {
            Constructor<? extends Plugin> constructor =
                    type.getConstructor(String.class);
            System.out.println("Chosen=" + raw.getSimpleName() + ":String");
            return constructor.newInstance(argument);
        } catch (NoSuchMethodException missingStringConstructor) {
            Constructor<? extends Plugin> constructor =
                    type.getConstructor();
            System.out.println("Chosen=" + raw.getSimpleName() + ":no-arg");
            return constructor.newInstance();
        }
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String source;
        Source(String binaryName, String source) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }
        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static final class ByteCode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        ByteCode(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }
        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }
        byte[] toByteArray() {
            return bytes.toByteArray();
        }
    }

    private static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ByteCode> compiled = new HashMap<>();
        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) {
            ByteCode output = new ByteCode(className, kind);
            compiled.put(className, output);
            return output;
        }
        Map<String, byte[]> classBytes() {
            Map<String, byte[]> result = new HashMap<>();
            compiled.forEach((name, output) ->
                    result.put(name, output.toByteArray()));
            return result;
        }
    }

    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> bytecode;
        MemoryClassLoader(ClassLoader parent, Map<String, byte[]> bytecode) {
            super(parent);
            this.bytecode = Map.copyOf(bytecode);
        }
        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = bytecode.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }
}
~~~

### 5.2. Compile and Run

From the **parent directory of `demo/`**, run in Bash (Linux/macOS or Git Bash on Windows):

~~~bash
mkdir -p out
javac --release 17 -d out demo/InMemoryCtorDemo.java
java -cp out demo.InMemoryCtorDemo
~~~

In PowerShell, create `out` with `New-Item -ItemType Directory -Force out`; the same two `javac`/`java` commands above also work if the JDK is on `PATH`. `--release 17` checks the host's syntax and API against Java 17; in the code, the dynamic compiler is also passed `--release 17`.

Standard output of the program:

~~~text
WithPrefixAssignable=true
Chosen=WithPrefix:String
WithPrefix=Xin chao, Java!
DefaultedAssignable=true
Chosen=Defaulted:no-arg
Defaulted=Hello, Java!
UnrelatedAssignable=false
UnrelatedRejected=true
~~~

Verified by compiling with `javac --release 17` and running on OpenJDK 24: the output matches **line for line** as above. On a runtime providing only minimal modules without a compiler, `ToolProvider.getSystemJavaCompiler()` can return `null`; the example requires a JDK/runtime image containing the `jdk.compiler` module.

### 5.3. Connecting Each Code Component to Java Mechanics

**`Source`** extends `SimpleJavaFileObject` with kind `Kind.SOURCE`. It supplies source content via `getCharContent` from a string, so the compiler does not have to read `WithPrefix.java` or `Defaulted.java` from disk.

**`ByteCode`** is an output `JavaFileObject`, returning a `ByteArrayOutputStream` when the compiler needs to write class bytes. **`MemoryManager`** is a `ForwardingJavaFileManager` that intercepts `getJavaFileForOutput` and stores `ByteCode` entries by **binary name**. If a source emits auxiliary classes (inner/anonymous classes), the file manager can receive additional corresponding outputs; the loader needs to retain those bytecodes, not just the top-level class.

**`compiler.getTask(...).call()`** runs the compiler. Check `Boolean.TRUE.equals(ok)` before loading any class. In a real system, you also inspect `DiagnosticCollector` to return line/column-located errors to the source author; never ignore compile failures or proceed with stale bytecode from an earlier compilation.

**`MemoryClassLoader`** holds a copy of the binary-name → bytecode map and overrides `findClass`. Its parent is `Plugin.class.getClassLoader()`, so the three dynamic classes see **the exact same `Plugin` interface** used by the host. `ClassLoader.loadClass` tries the parent first by default; `findClass` defines the class from bytes only when the parent does not have that class.

**`Class.forName(name, false, loader)`** gives the host a `Class<?>` for the dynamic class in the memory loader without eagerly initializing it. The host calls `Plugin.class.isAssignableFrom(raw)` to verify before calling `asSubclass`, then selects a public constructor. For `WithPrefix`, it uses `(String)`; for `Defaulted`, it falls back to `()`; and `Unrelated` is rejected before constructor reflection is used.

**`-classpath System.getProperty("java.class.path")`** in the dynamic compiler lets the compiler see the compiled bytecode of `demo.InMemoryCtorDemo.Plugin` in `out`. This is a simple approach suited to a **classpath** example; real applications using the module path, multiple loaders, or annotation processors need more explicit compiler/module-path/file-manager configuration. The `-proc:none` flag disables annotation processing in the example; you should not let the compiler execute untrusted processors inside the host process by default.

### 5.4. Why Write Generic `Class<? extends Plugin>`?

A dangerous pattern is:

~~~java
Class<?> raw = loader.loadClass(binaryName);
Object value = raw.getDeclaredConstructor().newInstance();
Plugin plugin = (Plugin) value;
~~~

This illustrative snippet has two problems: it **does not validate the class against the SPI before instantiating**, and it **only tries the no-arg constructor** even when a provider may require configuration. If the class is incompatible, the constructor may already have executed before throwing `ClassCastException` at the cast step. With an unintended plugin, constructor side effects could happen before the host can reject it.

The right workflow prefers:

~~~java
if (!Plugin.class.isAssignableFrom(raw)) {
    throw new IllegalArgumentException("Not a Plugin");
}
Class<? extends Plugin> type = raw.asSubclass(Plugin.class);
Constructor<? extends Plugin> ctor = type.getConstructor(String.class);
Plugin plugin = ctor.newInstance("Xin chao");
~~~

This is an **abbreviated illustrative snippet** for the case where the `String` constructor exists; the complete program includes the fallback branch when that constructor is absent.

## 6. Errors to Distinguish by Stage

| Issue | Common symptom/error | Resolution |
|---|---|---|
| Invalid Java source | Compiler returns `false`, with `Diagnostic.Kind.ERROR` | Read diagnostics; do not load bytecode from a failed compilation |
| Compiler unavailable | `ToolProvider.getSystemJavaCompiler() == null` | Run on a JDK/runtime image containing `jdk.compiler` |
| Loader lacks bytecode or dependency | `ClassNotFoundException` | Check binary name, bytecode map, and parent/classpath |
| A dependency is missing only during linking | `NoClassDefFoundError`/`LinkageError` | Inspect cause, loader, class/module path, and dependencies |
| Same-named interface with different defining loader | `isAssignableFrom == false` or `ClassCastException` later | Share the exact same `Plugin` class object between host and plugin |
| Candidate does not implement the SPI | `isAssignableFrom == false` | Reject before looking up constructors |
| Candidate is an interface/abstract class | `isAssignableFrom` may be `true` yet cannot be instantiated | Check modifiers; do not rely solely on type relationship |
| Missing constructor with required signature | `NoSuchMethodException` | Choose a well-defined fallback, or report a contract error if none |
| Public constructor, but class/package inaccessible | `IllegalAccessException` or JPMS access error | Verify public class, proper exports/opens, and caller module |
| Wrong argument types/count when invoking constructor | `IllegalArgumentException` | Pick the exact signature; verify arguments in order and type |
| Constructor itself throws an exception | `InvocationTargetException`; use `getCause()` | Log the real cause, treat as instantiation failure; do not fall back silently |
| Static initializer fails | `ExceptionInInitializerError`, possibly leading to `NoClassDefFoundError` later | Analyze initializer/cause and loader state; do not arbitrarily reuse a broken class |
| Class name defined twice in the same loader | `LinkageError` on duplicate definition | Manage bytecode maps, generations/versions, and create a new loader when swapping implementations |
| Using JARs/plugins from untrusted sources | No error guaranteed before execution | Isolate at process/container level; do not treat type checking as a sandbox |

### `InvocationTargetException`: Inspect the Root Cause

When a constructor **has been selected and invoked**, exceptions thrown by the constructor's code are normally wrapped in `InvocationTargetException`. An example of handling this specifically at the host layer:

~~~java
try {
    return constructor.newInstance(arguments);
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable original = e.getCause();
    // Log or translate into a domain error preserving the root cause.
    throw e;
}
~~~

This is an **integration snippet**: it assumes `Constructor<?> constructor` and `Object[] arguments` are already available. You must preserve the original cause for diagnostics. Never treat a constructor throwing an error as a signal to unconditionally try another constructor, because the constructor may already have mutated state before failing.

### `getDeclaredConstructor` Does Not Automatically Bypass JPMS

A class belonging to a named module whose package is not `exports` or `opens` to the host module can deny deep reflective access. Obtaining a `Constructor` object does not mean `newInstance` is allowed. When designing a public-contract plugin, provide a public constructor on a public class in a module/package with an appropriate access policy; if a framework-managed private constructor is required, design `opens` and access permissions explicitly.

## 7. Choosing Constructors When Real Systems Are More Complex

A production host typically has extensive dependency injection and configuration; you should not reflectively pick "the first constructor" and guess arguments.

- **Single-signature convention:** the provider interface requires a public constructor `(PluginConfig)` or factory method, and the host knows exactly how to supply `PluginConfig`. Advantage: clear deployment-time errors.
- **Priority-order convention:** try `(PluginConfig)`, and if *not found*, try `()`; enforce a fixed policy and log which constructor was chosen. The runnable lesson demonstrated this with `(String)` and `()`.
- **Metadata-driven selection:** a plugin descriptor declares the supported constructor style/factory identifier, though metadata must still be verified via reflection before invoking.
- **Use a factory/SPI:** if initialization is complex or needs many dependencies, let the plugin provide a factory registered via `ServiceLoader`; avoid forcing reliance on public constructors just because reflection is easy to write.
- **Varargs or primitive/wrapper constructors:** `getConstructor` looks up the **exact declared parameter type list**, without performing javac-style overload resolution. For example, `getConstructor(int.class)` differs from `getConstructor(Integer.class)`; handling argument conversion at invocation time is a separate step.
- **Non-static nested classes:** the reflective constructor of a non-static inner class also includes the enclosing outer instance parameter; without an explicit convention, plugins should be top-level classes or static nested classes.
- **Records/enums:** a record can have a public canonical constructor matching its signature, whereas an enum cannot be instantiated reflectively via a constructor; the service API should specify which provider kinds are accepted.

If you must support non-public constructors, state the module access requirements explicitly rather than calling `setAccessible(true)` indiscriminately on everything. If plugins must be reloaded, use a new class loader/layer; mutating the source string or bytecode map of a loader that already defined a class does not make the JVM replace the old class.

## 8. Validation Rules Before Activating a Plugin

For an in-memory compilation and automatic plugin creation step, a host can build a pipeline like this:

1. **Valid source:** class name, source size, dependencies, and compilation options pass policy checks; report errors from `DiagnosticCollector`.
2. **Compilation succeeds:** verify `getTask().call()` is `true`; know which bytecode was generated and which class is the entry point.
3. **Consistent loader:** create a loader with the right parent for the SPI; do not define duplicate copies of host interfaces in the child loader.
4. **Load class by exact name:** use the known binary name and specific loader, preferring not to initialize eagerly during validation.
5. **Type check:** `ExpectedService.class.isAssignableFrom(candidate)` in the right argument order.
6. **Instantiation policy:** class is not an interface/abstract/enum; visibility/module access is appropriate; select constructor per convention.
7. **Instantiate:** call `Constructor.newInstance(...)`, preserve the cause on exception, and do not retry another branch if the invoked constructor failed.
8. **Register/lifecycle:** verify the instance fulfills the contract before registering it with the host; have a stop/dispose flow when swapping versions.

Type checking **does not create a security boundary**. The Java compiler, class loader, and constructor can process code that later executes with the host process's privileges. For code submitted by untrusted users or third parties, you need separate isolation mechanisms, resource limits, dependency policies, and access evaluations.

In addition, the compiler/file manager must be closed after use. In systems compiling repeatedly, manage caches and class loaders per generation to avoid retaining bytecode, class objects, static state, threads, or listeners indefinitely. Dropping references so the JVM can garbage-collect the class loader is required for classes from old generations to be reclaimed.

## 9. Self-Check Questions

1. **Why is successful compilation not enough to cast `Class<?>` to `Plugin`?** Because the compiler only confirms the source is valid; the implementation may not implement the SPI or may use an interface with a different runtime identity.
2. **Which expression is right: `Plugin.class.isAssignableFrom(raw)` or `raw.isAssignableFrom(Plugin.class)`?** The first one, because you need to verify whether `candidate` can be assigned to a `Plugin` variable.
3. **Does `isAssignableFrom == true` guarantee instantiation will succeed?** No. The class might be abstract/an interface, lack a matching constructor, be access-restricted, or fail inside the constructor.
4. **Why use `raw.asSubclass(Plugin.class)`?** To obtain a runtime-verified `Class<? extends Plugin>`, eliminating unsafe generic casts.
5. **When is it valid to try the no-arg constructor?** When the contract allows a fallback and the preferred constructor **does not exist** (`NoSuchMethodException`), not when invoking it already failed.
6. **Does `getConstructor(String.class)` automatically match `(CharSequence)` or `(Object)` constructors?** No; it looks up the exact signature, unlike javac's overload resolution.
7. **What does changing `Class.forName(name, true, loader)` to `Class.forName(name, false, loader)` achieve?** It allows inspecting class metadata before eagerly initializing the class; it does not make untrusted code safe.
8. **Are two interfaces with the same binary name but defined by two different loaders equal?** No. Class identity depends on the defining loader.
9. **If `Constructor.newInstance` throws `InvocationTargetException`, what should you do?** Inspect `getCause()` and report an initialization error; do not automatically try another constructor.
10. **When changing source and recompiling, can you reuse the same loader that defined the old class to replace its bytecode?** You cannot just update the byte map and expect the already-defined class to change. You usually need a new loader/layer and explicit generation management.

**Key takeaway:** after in-memory compilation, **verify type compatibility before instantiation**, use **`asSubclass`** to safely narrow `Class<?>`, **select the right public constructor matching the agreed signature**, and handle missing-constructor errors separately from constructor execution failures. At the same time, the host and implementation must share **the exact same runtime identity of the SPI**, otherwise identically named classes still may not be assignable.

## References

- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isAssignableFrom`, `asSubclass`, `getConstructor`, `getDeclaredConstructor`, and `Class.forName`.
- [Java SE 17 — `Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance` and reflection exceptions.
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html) and [`ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): compiler tasks and in-memory output capture.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass`, and class identity.