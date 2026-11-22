# Comparison Table of `loadClass`, `forName`, `defineClass`, and `resolveClass` in Java

## 1. At a Glance: Four APIs That Do Different Things

When working with class loaders, plugins, reflection, or class linkage errors in Java, these four API names are easily mistaken for four equivalent ways to "load a class". In reality, they serve distinct roles: **finding/loading a class**, **finding a class with optional initialization**, **defining a class from bytecode**, and **requesting linking of an existing class**.

The table below uses Java SE 17 semantics, specifically for `java.lang.ClassLoader` and `java.lang.Class`. Internal JVM details, the timing of linking individual symbolic references, and diagnostic logs may vary depending on the implementation.

| API | Location and Access | Primary Inputs | Primary Responsibility | Requests Initialization on Its Own? | Result |
|---|---|---|---|---|---|
| `loader.loadClass(String name)` | `ClassLoader`, `public` | Binary name and the invoked loader | Finds/loads the class using the loader's algorithm, equivalent to `loadClass(name, false)` | **No** | `Class<?>` |
| `loader.loadClass(String name, boolean resolve)` | `ClassLoader`, `protected` | Binary name and `resolve` flag | Finds/loads; when `resolve=true`, calls `resolveClass` on the found class (in the default implementation) | **No** | `Class<?>` |
| `Class.forName(String name)` | `Class`, `public static` | Class name; **the defining loader of the calling class** is used per the specification | Finds/loads and requests **initialization** if not yet initialized | **Yes** | `Class<?>` |
| `Class.forName(String name, boolean initialize, ClassLoader loader)` | `Class`, `public static` | Name, initialize flag, and specified loader | Finds/loads using this loader; `true` requests initialization, `false` does not | **Depends on flag** | `Class<?>` |
| `defineClass(String name, byte[] bytes, int off, int len)` | `ClassLoader`, `protected final` | Expected name and class file bytes | Converts bytecode into a **runtime class defined by this loader** | **No** | `Class<?>` |
| `resolveClass(Class<?> c)` | `ClassLoader`, `protected final` | Existing `Class` | **Links** the already-defined class; if already linked, does nothing further | **No** | `void` |

**Key point:** `resolve` in `loadClass(name, true)` means **linking**, not "initialize = true". The two flags `resolve` and `initialize` belong to **two different phases**. Calling `defineClass` only creates the runtime definition; it is not equivalent to "calling the static initializer". And `Class.forName` does not itself create an instance via a constructor.

In addition to the overloads above, Java 9+ also provides `Class.forName(Module module, String name)`: this is an API that looks up a class by **module**, returning `null` if not found; according to the Javadoc, this overload **does not link and does not run the class initializer**. Do not apply the assumption "every `forName` initializes" by default to the `Module` overload.

## 2. Placing Them in the Class Lifecycle to Avoid Terminology Confusion

A practical way to visualize this:

```text
Binary name of the class, e.g., sample.ProbeTarget
                 │
                 ▼
       ClassLoader.loadClass(name)
                 │
     ┌───────────┴───────────┐
     │ Already loaded?       │
     ├─ Yes ─► return Class  │
     │ No                    │
     ▼                       │
 Parent delegation / findClass
     │
     ▼
 Read bytes from an appropriate source
     │
     ▼
 defineClass(name, bytes, ...)
     │
     └───────────► Class<?> ───────────────┐
                                         │
                                         ▼
                               resolveClass(c)
                                         │
                                         ▼
                                 Linking / verification,
                                 preparation and resolution
                                         │
                    upon active use or initialization request
                                         ▼
                              Initialization (`<clinit>`)
```

This is a **conceptual diagram**, not a guarantee that the JVM must execute every step in full in a single rigid log order. Linking consists of verification, preparation, and resolution; resolution of some symbolic references may be performed lazily. The JVM may also load dependent classes when needed.

Distinguishing the three outcomes:

- **Loaded/defined:** a `Class<?>` representing a runtime class. It may still be **not yet initialized**.
- **Linked:** the JVM has performed the linking steps according to the required semantics. This does **not** mean that every class referenced in the source code has been loaded/initialized.
- **Initialized:** the JVM executes the class initialization procedure, including static initializers and static field initializers when needed. A class may have been loaded and linked beforehand without being initialized yet.

**Runtime class identity** is determined by **its binary name and defining class loader**. Two loaders can define two different `Class<?>` objects with the same name `sample.ProbeTarget`. Having the same class name does not mean having the same Java type when passing objects between two loaders.

## 3. `ClassLoader.loadClass`: Finding and Loading According to Loader Strategy

### `loadClass(String)`: Commonly Used Public API

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.example.Plugin");
```

The snippet above is an **illustrative code fragment**, assuming `getContextClassLoader()` is non-`null` and `com.example.Plugin` can be found by the loader. It obtains a `Class<?>`, **does not create an instance**, and simply calling `loadClass` does not request class initialization.

For the default implementation of `ClassLoader`, `loadClass(name)` is equivalent to calling `loadClass(name, false)`. If the class is already loaded, the loader can return the existing `Class`; it does not necessarily reopen the JAR or read the class bytes again.

### `loadClass(String, boolean)`: Protected Overload

The Javadoc describes the default algorithm of `loadClass(name, resolve)` in order:

1. `findLoadedClass(name)` checks whether the corresponding class has already been loaded within the scope known to this loader.
2. If not, delegates to the parent loader; if there is no parent, uses the VM's built-in loader mechanism.
3. If the parent cannot find it, calls `findClass(name)` — the common place for a custom loader to load bytes and call `defineClass`.
4. If found and `resolve=true`, calls `resolveClass(c)` on the resulting `Class`.

This is the **default behavior**; a subclass can override `loadClass` to change the lookup or delegation strategy. Therefore, do not assume every plugin loader is always parent-first: you need to read the actual implementation. In most standard delegation-based loaders, overriding `findClass` is a safer and better-designed extension point than completely rewriting `loadClass`.

```java
public final class MyLoader extends ClassLoader {
    public MyLoader(ClassLoader parent) {
        super(parent);
    }

    // Abbreviated example: returns the result of the protected overload.
    public Class<?> loadAndLink(String binaryName)
            throws ClassNotFoundException {
        return super.loadClass(binaryName, true);
    }
}
```

Class `MyLoader` illustrates exposing the `protected` call through a method provided by the subclass; this example does not implement `findClass`, so it is not yet a plugin loader that locates bytecode on its own.

**Do not confuse `resolve=true` with `initialize=true`.** The two flags are different, and `loadClass(name, true)` still does not itself request execution of `<clinit>`. Renaming the `resolve` variable to "initialize" in code does not change the actual semantics.

## 4. `Class.forName`: Choosing Optional Initialization

### `Class.forName(String name)`

```java
Class<?> driver = Class.forName("com.example.Driver");
```

This is an illustrative code fragment, assuming the class exists. The single-argument overload **requests initialization** of the class if it has not yet been initialized. According to the Java SE 17 Javadoc, it is equivalent to `Class.forName(name, true, currentLoader)`, where `currentLoader` is **the defining loader of the class making the call**. You cannot by default substitute it with the "system loader", "thread context loader", or "loader of all libraries".

A common example is a framework/plugin running under a different class loader than the caller. Calling the single-argument overload may **fail to find the plugin class**, even though the dedicated plugin loader knows about that class. In that case, you need to explicitly specify the appropriate loader.

### `Class.forName(String name, boolean initialize, ClassLoader loader)`

```java
ClassLoader pluginLoader = /* properly created loader */;
Class<?> loaded = Class.forName(
        "com.example.Plugin", false, pluginLoader);

Class<?> initialized = Class.forName(
        "com.example.Plugin", true, pluginLoader);
```

This is **illustrative code in a context where the `pluginLoader` variable exists**, not a standalone program. If the class has not yet been loaded, both calls can cause it to be loaded. Key differences:

- `initialize=false`: **does not request running the initializer** for the target class on that call; it does not mean the JVM guarantees "nothing has been linked yet".
- `initialize=true`: the JVM ensures initialization according to Java rules if the class has not yet been initialized. During that process, superclasses and certain superinterfaces may also be initialized according to the JLS.
- If the class is already initialized, calling `forName(..., true, ...)` again on the **same runtime class** does not re-run `<clinit>`.
- If `loader == null` in this overload, the Javadoc specifies using the **bootstrap class loader**, not "picking the current loader".
- If `name` is the name of an array class, its component type may be loaded but **is not initialized merely by that call for the array**.
- A string such as `"int"` does not return `int.class`; this API is not a way to look up primitive class objects by name.

For applications that need to **inspect metadata while limiting the side effects of static initializers**, choosing `forName(name, false, correctLoader)` is often useful. Even so, subsequent reflection and operations (such as invoking a static method) can still trigger initialization.

### `forName` and Reflection Errors

`Class.forName` can throw `ClassNotFoundException` when the loader cannot find the class, `LinkageError` if linking fails, and `ExceptionInInitializerError` if the static initializer fails where applicable. Do not treat catching `ClassNotFoundException` as sufficient to handle all binary/API mismatches.

## 5. `defineClass`: Defining a Class from Bytecode

`defineClass` is a **`protected final`** method of `ClassLoader`. Commonly used overloads:

```java
// Code inside a ClassLoader subclass.
Class<?> type = defineClass(binaryName, bytecode, 0, bytecode.length);
```

JDK 17 also has overloads accepting a `ProtectionDomain` or a `ByteBuffer`. `defineClass` turns valid class file data into a `Class<?>` **defined by the current loader**, subject to binary name, package, and protection rules.

A custom loader typically does the following:

```java
@Override
protected Class<?> findClass(String name) throws ClassNotFoundException {
    try {
        byte[] bytes = readBytecodeFor(name);
        return defineClass(name, bytes, 0, bytes.length);
    } catch (java.io.IOException e) {
        throw new ClassNotFoundException(name, e);
    }
}
```

This is **Java pseudocode** purely illustrating the pattern: `readBytecodeFor(name)` is undeclared and must be provided by the implementer. A complete, runnable example is in section 7.

Essential notes:

- `defineClass` **does not itself decide how to search the classpath, does not itself implement parent delegation, does not call constructors, and does not request initialization**. It only processes the bytes provided by the caller.
- In a delegation-compliant class loader, the normal path is `loadClass → findClass → defineClass` when the parent cannot find the class. Calling `defineClass` directly to "force-replace" a class already defined by that loader violates the model.
- The same **binary name** cannot normally be defined twice by the same defining loader; a duplicate definition results in a linkage error, such as `LinkageError`.
- An expected name that does not match the class bytes, invalid data, or package restrictions can lead to `NoClassDefFoundError`, `ClassFormatError`, `SecurityException`, or the corresponding linkage error. An application loader is not allowed to define classes in packages starting with `java.`.
- `defineClass` with an overload that does not specify a `ProtectionDomain` uses the API's default protection domain. When designing a production loader, you must consider permissions, code sources, signer/certificate consistency, and package lifecycle; do not use this minimal template as a complete security solution.
- Defining a class creates a runtime identity tied to the loader. Two different loaders can define the same class bytes into **two different runtime types**.

**When to use it?** When you are **writing a custom ClassLoader** and need to turn bytecode from a file/JAR/network/generated output into a runtime class. Ordinary business code should almost never call this protected API directly.

## 6. `resolveClass`: Linking, Not Running `<clinit>`

`resolveClass(Class<?> c)` is also a **`protected final`** method of `ClassLoader`. The Javadoc describes it as the operation that **links the specified class**; if the class is already linked, it simply returns. The method name can be misleading: the Java VM has the concept of **resolution** of symbolic references, yet some resolutions can be deferred until use; do not interpret `resolveClass` as "loading and resolving the entire dependency graph" or "running the static initializer".

Example exposing the API from a subclass:

```java
final class LinkingLoader extends ClassLoader {
    void link(Class<?> type) {
        resolveClass(type);
    }
}
```

This is an illustrative code fragment: `link` only makes sense if `type` comes from an appropriate class loading/definition path; the snippet above does not itself supply bytes to create a class. In a custom loader, a common pattern is:

```text
bytes → defineClass(...) → Class<?> type → resolveClass(type)
                                │
                                └─ Only later does an active use / forName(true)
                                   request initialization
```

**`resolveClass` has no public overload** for arbitrary code to call directly outside a subclass, unlike `Class.forName`, which is a static public API. `loadClass(name, true)` calls `resolveClass` in the default implementation; therefore, **the two APIs are related but not synonymous**.

## 7. Java 17+ Example: Comparing Three Loaders, Four APIs, and Initialization Order

The following experiment deliberately compiles the plugin class **outside the host program's classpath**, so that the class is only defined by the custom loader. We observe via deterministic output that `loadClass`, `defineClass`, `resolveClass`, and `loadClass(name, true)` **do not request initialization**, whereas `forName(..., true, loader)` causes each runtime class to initialize.

### Structure

```text
working/
├── ClassLoadingComparison.java
├── plugin-src/
│   └── sample/
│       └── ProbeTarget.java
└── plugin-classes/
    └── sample/
        └── ProbeTarget.class  (generated by javac)
```

File **`plugin-src/sample/ProbeTarget.java`**:

```java
package sample;

public final class ProbeTarget {
    static {
        System.out.println("ProbeTarget initialized");
    }

    public static int value() {
        return 42;
    }
}
```

File **`ClassLoadingComparison.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassLoadingComparison {
    private static final String NAME = "sample.ProbeTarget";

    static final class ByteLoader extends ClassLoader {
        ByteLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(
                        Path.of("plugin-classes", "sample", "ProbeTarget.class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }

        Class<?> defineDirectly(String name)
                throws ClassNotFoundException {
            return findClass(name);
        }

        void link(Class<?> type) {
            resolveClass(type);
        }

        Class<?> loadAndResolve(String name)
                throws ClassNotFoundException {
            return super.loadClass(name, true);
        }
    }

    public static void main(String[] args) throws Exception {
        ByteLoader a = new ByteLoader();
        System.out.println("A: loadClass");
        Class<?> first = a.loadClass(NAME);
        System.out.println("A: forName(false) same Class = "
                + (first == Class.forName(NAME, false, a)));
        System.out.println("A: forName(true)");
        Class.forName(NAME, true, a);
        System.out.println("A: value = "
                + first.getMethod("value").invoke(null));

        ByteLoader b = new ByteLoader();
        System.out.println("B: defineClass");
        Class<?> second = b.defineDirectly(NAME);
        System.out.println("B: resolveClass");
        b.link(second);
        System.out.println("B: forName(true)");
        Class.forName(NAME, true, b);
        System.out.println("A and B different = " + (first != second));

        ByteLoader c = new ByteLoader();
        System.out.println("C: loadClass(resolve=true)");
        c.loadAndResolve(NAME);
        System.out.println("C: forName(true)");
        Class.forName(NAME, true, c);
    }
}
```

### Compiling and Running

In the `working` directory, create the `plugin-src/sample` and `plugin-classes` directories beforehand; place the two files as shown above, then run:

```bash
javac -d plugin-classes plugin-src/sample/ProbeTarget.java
javac ClassLoadingComparison.java
java -cp . ClassLoadingComparison
```

**Do not add `plugin-classes` to `-cp .`**: if the plugin is on the host program's classpath, a parent/another class loader may load it and the experiment will no longer accurately demonstrate the `ByteLoader.defineClass` path. With this command, the `.` represents **a single** entry, so it is used the same way on Windows and Unix.

The **exact** application output (without JVM logging enabled):

```text
A: loadClass
A: forName(false) same Class = true
A: forName(true)
ProbeTarget initialized
A: value = 42
B: defineClass
B: resolveClass
B: forName(true)
ProbeTarget initialized
A and B different = true
C: loadClass(resolve=true)
C: forName(true)
ProbeTarget initialized
```

Step-by-step explanation:

- **Loader A:** `a.loadClass(NAME)` returns `Class` without printing `ProbeTarget initialized`. `forName(NAME, false, a)` returns the **same `Class`** and likewise does not request initialization. `forName(NAME, true, a)` triggers the static initializer; the reflection call to `value()` afterward returns `42`.
- **Loader B:** `defineDirectly` calls `findClass`, in which `defineClass` defines a new class from the same bytes. `b.link(second)` calls `resolveClass` without printing from the static initializer. `forName(true)` afterward causes B's class to initialize for the first time.
- **Two loaders A/B:** `first != second` is `true` despite the same `sample.ProbeTarget` and the same `.class` file: different defining loaders create different runtime class identities.
- **Loader C:** `loadAndResolve` goes through `super.loadClass(name, true)`, which is the loader API's resolve flag. It **does not initialize**. Only the subsequent `forName(true)` call causes the static initializer of C's class to run.

Each loader defines a **separate runtime class**, so seeing three `ProbeTarget initialized` lines is valid; it is not the JVM reinitializing **the same** class three times.

The example is designed to demonstrate the public/protected APIs; it is **not** a production custom loader. `defineDirectly` deliberately bypasses the search/delegation path purely to distinguish `defineClass` from `loadClass`. In production, you should prefer a loader implementation with proper locking, lookup policy, and standard package/protection domain management.

### Adding JVM Logs for Observation

On HotSpot JDK 17+:

```bash
java -Xlog:class+load=info,class+init=info -cp . ClassLoadingComparison
```

Look for lines containing `sample.ProbeTarget` and the `[class,load]` or `[class,init]` tags. The logs may include many JDK classes and dynamic information (timestamps, addresses, loader data); do **not** claim that every HotSpot build produces a byte-for-byte identical log stream. If you need to save to a file:

```bash
java -Xlog:class+load=info,class+init=info:file=class-events.log:time,uptime,level,tags -cp . ClassLoadingComparison
```

Enable class logging during **observation runs**, and avoid using timing results from logged runs as performance comparison benchmarks because I/O/logging introduces overhead. The log tags help confirm when a class is actually loaded and initialized, without turning resolution into initialization.

## 8. API Selection Table by Scenario

| Scenario | Recommended API | Reason |
|---|---|---|
| Want the loader to find and return a class following its delegation policy, **without needing init side effects yet** | `loader.loadClass(name)` | Public API, does not request initialization |
| Want explicit control over the loader and initialization timing | `Class.forName(name, false/true, loader)` | Explicitly specifies the class loader and initialize flag |
| Want to call `forName` using the caller class's own loader | `Class.forName(name)` | Javadoc specifies the current loader and init=true |
| Want to write a custom loader from bytecode files/network/generated bytes | `defineClass` inside `findClass` | Converts bytes into a runtime class of the current loader |
| Want the class loader to proactively **link** an existing class | `resolveClass(c)` or `loadClass(name, true)` in a subclass | Linking is the loader's responsibility, separate from initialization |
| Want to look up a `Class` by a named module without initializing and allowing `null` return | `Class.forName(module, name)` | The module overload has its own semantics |
| Want to create an object, run a constructor, and use dependencies | Obtain the `Class`/type and then use the corresponding constructor/API | The four APIs in the table **do not create instances on their own** |
| Want to unload a class/plugin | Manage the loader's lifecycle and references, and observe GC/unloading | None of the four methods is "unloadClass" |

Note that `loadClass(name)` and `forName(name, false, loader)` are often used to "only load", but you **should not claim** these two paths are strictly equivalent for all custom loaders: `forName` has `Class`-specific rules, whereas a subclass's `loadClass` implementation may alter the default behavior or have its own side effects.

## 9. Errors, Access Restrictions, and Common Misconceptions

### Distinguishing Binary Names from Source Names

Methods that accept a class name as a string typically use a **binary name**, for example `java.util.Map$Entry` for the nested type `Map.Entry`. For class `com.example.Demo`, the correct name is `"com.example.Demo"`, not the path `"com/example/Demo.class"`. With the `Class.forName(String, boolean, ClassLoader)` overload, array names also take descriptor-like forms such as `"[Ljava.lang.String;"`, so you must check the API contract before concatenating strings yourself.

`defineClass(name, bytes, ...)` requires the bytecode contents to match the expected binary name. You cannot take the bytes of `com.example.A`, request to define it under the name `com.example.B`, and expect the VM to automatically rename it in the constant pool.

### `ClassNotFoundException`, `NoClassDefFoundError`, and `LinkageError`s

- `ClassNotFoundException` is a common checked exception when **requesting a class lookup by name** and the loader cannot find it.
- `NoClassDefFoundError` is a `LinkageError` that typically occurs when the runtime needs a class definition that was expected to exist but cannot be found/loaded at that point; it can also appear when a class previously failed initialization and is used again.
- `ClassFormatError`, `UnsupportedClassVersionError`, and other linkage errors relate to invalid bytes/class versions, runtime incompatibility, or the linking process.
- `ExceptionInInitializerError` typically indicates that a static initializer/initialization failed, and may only appear when `forName(..., true, loader)` or the first active use runs.
- `ClassCastException` when passing an object between two runtime types with the same name but different defining loaders is not necessarily a "class not found" error.

Do not try to solve the errors above by calling `resolveClass` repeatedly or arbitrarily adding `Class.forName`. You need to check the exception type, classpath, loader delegation, binary identity, and version.

### `protected` Does Not Mean Public API

`defineClass`, `resolveClass`, and `loadClass(name, boolean)` are protected methods of `ClassLoader`; `defineClass`/`resolveClass` are also final. Ordinary business code outside a subclass **cannot call** protected methods directly through an arbitrary object. In the example code, `ByteLoader` exposes its own wrappers (`defineDirectly`, `link`, `loadAndResolve`) for illustration and observation. Those wrappers are **not standard Java APIs**.

Do not try to bypass Java module/access protection or reflect into `ClassLoader#defineClass` just to load a plugin; that approach can be blocked by `java.base` module encapsulation and makes your design depend on runtime internals.

### Resolve Is Not Initialize; Initialize Does Not Mean "Instantiate"

- `resolveClass(c)` → links the class per the specification; **does not execute `new`/constructors**.
- `Class.forName(name, true, loader)` → requests class initialization, including static initialization; **does not invoke instance constructors**.
- `Class.forName(name, false, loader)` → does not request initialization; **does not guarantee that all metadata/dependencies have not yet been processed by the VM**.
- `ClassLoader.loadClass(name)` → looks up/loads without being required to execute `<clinit>`; **must not be confused with `Class.forName(name)`**.
- `defineClass(...)` → creates a `Class` defined from bytes; **does not replace runtime JARs globally**, and does not redefine the same class already defined by that loader.

If you need an object, you must choose the appropriate constructor/factory API and handle the access/reflection steps separately. Initializing a class may trigger initialization of its superclass first, according to JLS `12.4` rules.

## 10. Debugging Workflow When a Class Loader Produces Unexpected Results

1. **Record the exact API being called:** `loadClass(name)`, `forName(name)`, `forName(name, false, loader)`, `defineClass`, or `resolveClass`. Specifically note the `initialize` or `resolve` flag.
2. **Verify the defining loader:** inspect `type.getClassLoader()`; `null` can represent the bootstrap loader. Do not infer it solely from the package/class name.
3. **Check byte sources and delegation:** classpath/module path, JAR order, parent/child loaders, `findClass`. In a plugin environment, the parent may load a different version than the plugin file.
4. **Confirm load/init events:** on HotSpot, enable `-Xlog:class+load=info,class+init=info` before reproducing; class load logs differ from class init logs.
5. **Read the full exception and stack trace:** distinguish missing classes, invalid bytecode, linkage conflicts, and `<clinit>` errors. Do not catch one type and assume every error is caused by the classpath.
6. **Check the JVM and bytecode versions:** the class file major version must be supported by the runtime; changing dependencies at runtime does not make a loader already holding old `Class` objects automatically forget them.
7. **Fix at the right boundary:** adjust dependency/loader policy, align API implementations, or create a new loader in the plugin lifecycle where appropriate; do not use `System.gc()` to "fix" conflicting class definitions.

Example of quickly printing loader identity in Java code once you already have `Class<?> type`:

```java
System.out.println("Class name = " + type.getName());
System.out.println("Defining loader = " + type.getClassLoader());
System.out.println("Module = " + type.getModule().getName());
```

This is a snippet **illustrating the use of an existing `type` variable**, not a standalone program. An unnamed module can have a `null` name; a class defined by the bootstrap loader also has a `null` loader. With the same `getName()` but different loaders, two `Class<?>` objects are still distinct.

## 11. Self-Check Questions

**Question 1.** Do `loader.loadClass("X")` and `Class.forName("X")` provide the same guarantee for class initialization?  
**Answer:** No. `loadClass(String)` does not request initialization; `Class.forName(String)` requests initialization and uses the caller's defining loader.

**Question 2.** Is the `resolve=true` flag equivalent to `initialize=true`?  
**Answer:** No. `resolve=true` requests linking via `resolveClass` in the default loader; `initialize=true` requests class initialization according to `Class.forName` semantics.

**Question 3.** Can you call `defineClass` twice to "overwrite" the same class already defined by a loader?  
**Answer:** No. A defining loader cannot define the same binary name again in that way; creating another loader produces a different runtime class rather than replacing the old one.

**Question 4.** Is `Class.forName("int")` the same as `int.class`?  
**Answer:** No. According to the Javadoc, the string-name overload is not used to obtain a primitive `Class` from a primitive name.

**Question 5.** Why does the example print `ProbeTarget initialized` three times?  
**Answer:** Three different `ByteLoader` instances defined three runtime classes with the same binary name; each class was requested to initialize separately.

**Question 6.** What should you use when you want to check that a class has loaded without running `<clinit>` yet?  
**Answer:** `loadClass(name)` or `Class.forName(name, false, loader)`, and observe the `class+load` log versus `class+init`; watch out for side effects from custom loaders and subsequent operations.

## 12. Source References

- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass(String)`, `loadClass(String, boolean)`, `findClass`, `defineClass`, `resolveClass`, and the delegation mechanism.
- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): the three `forName` overload groups with `String`, `String/boolean/ClassLoader`, and `Module/String`.
- [JLS 17 — Chapter 12: Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): definitions of loading, linking, initialization, and unloading.
- [JVMS 17 — Chapter 5: Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): VM semantics and linking timing.
- [JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog` syntax for observing class loading and initialization on HotSpot.
