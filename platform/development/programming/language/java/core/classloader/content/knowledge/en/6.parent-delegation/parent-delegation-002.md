# Default Sequence: findLoadedClass, Parent Loader, and findClass

## 1. Core Question: When Requested to Load a Class, Where Does a ClassLoader Look First?

In Java, a call requesting to load a class, such as `loader.loadClass("example.Plugin")`, **does not by default immediately read the `Plugin.class` file from the location that loader manages**. With the default implementation of `java.lang.ClassLoader.loadClass(String, boolean)`, the JVM/loader performs the following sequence:

1. **`findLoadedClass(name)`**: checks whether the class has already been recorded as loaded with the loader being queried.
2. **Delegate to the parent loader**: if step 1 has not found it, ask the parent first. If `parent == null`, use the JVM's built-in bootstrap loader.
3. **`findClass(name)`**: only when the parent/bootstrap does not find it does the current loader attempt to locate and define the class itself.
4. **`resolveClass(c)` if `resolve == true`**: requests linking of the found class; returns the `Class<?>` object.

This is **parent-first delegation**, also known as the default delegation model.

```text
loadClass("example.Plugin", resolve)
│
└─ synchronized(getClassLoadingLock(name))
   │
   ├─ 1. findLoadedClass(name)
   │    └─ found? ── Yes ────────────────┐
   │                                     │
   ├─ 2. parent.loadClass(name)          │
   │       or bootstrap when parent=null │
   │    └─ found? ── Yes ────────────────┤
   │                                     │
   ├─ 3. findClass(name)                 │
   │    ├─ found → define/load ──────────┤
   │    └─ not found → ClassNotFoundException
   │                                     │
   └─────────────────────────────────────┘
                                         │
                               resolve? ─┤
                                  Yes → resolveClass(c)
                                  No → skip this step
                                         │
                                      return c
```

**Key takeaway:** the three-step class lookup order is **already loaded → parent → self-lookup**. `findClass` is not the first step in the default model. This order is the **behavior of the default implementation**; a custom ClassLoader can override `loadClass` and change the policy, so do not apply the parent-first rule unconditionally to every class loader.

## 2. From API to Execution Flow

The two overloads of `ClassLoader` have different roles:

```java
public Class<?> loadClass(String name)
        throws ClassNotFoundException

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException
```

- `loadClass(String name)` is the public API; for a typical `ClassLoader` implementation, it calls `loadClass(name, false)`.
- `loadClass(String name, boolean resolve)` is the protected API; the **default implementation** contains the cache-check/delegation/self-lookup/resolve algorithm.
- `name` is a **binary name**, for example `com.acme.PluginService`, not the path `com/acme/PluginService.class` or a JAR filename.
- The `resolve` flag only controls calling `resolveClass` after obtaining the class; it **does not mean** the class must be initialized or its static initializer invoked.

The following pseudocode illustrates the **logic** of the default implementation in modern JDKs. `bootstrapLookup` below is a placeholder name for explanation, **not a public API method**:

```java
// PSEUDOCODE — not a compilable ClassLoader definition
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> found = findLoadedClass(name);

        if (found == null) {
            try {
                found = (parent != null)
                        ? parent.loadClass(name)
                        : bootstrapLookup(name);
            } catch (ClassNotFoundException notFoundInParent) {
                // Not found by parent; try the current loader itself.
            }

            if (found == null) {
                found = findClass(name);
            }
        }

        if (resolve) {
            resolveClass(found);
        }
        return found;
    }
}
```

For a loader that does not override `loadClass`, synchronization via `getClassLoadingLock(name)` protects the class-check/creation sequence against concurrent requests. `getClassLoadingLock` may return a shared lock on the loader instance or a per-class-name lock if the loader is registered as parallel capable; do not assume every loader uses only a single monitor.

**Read the flow accurately:** `findLoadedClass` checks the already-recorded state; parent delegation is another load request going up the loader chain; `findClass` is the extension point for **defining** a class yourself from your own source. There is no automatic call to `findClass` after the parent has already returned a successful result.

## 3. Step 1 — findLoadedClass: Has This Class Already Been Loaded?

API declaration:

```java
protected final Class<?> findLoadedClass(String name)
```

The method returns:

- `Class<?>` if the JVM has already recorded the current loader as an **initiating loader** of the class with that binary name.
- `null` if there is no matching record yet.

A common point of confusion is **initiating loader** versus **defining loader**:

- **Defining loader**: the loader that actually called `defineClass` (or performed an equivalent defining mechanism) to create the runtime class.
- **Initiating loader**: the loader recorded by the JVM as having initiated loading of the class by that name. It may have **successfully delegated** to another defining loader.

Therefore, `findLoadedClass(name) != null` **does not prove that the current loader read the bytes or defined the class itself**; the class may have been defined by the parent or bootstrap loader. `Class<?>.getClassLoader()` reports the defining loader in the normal case (with bootstrap represented as `null`).

### Why Check First?

- Avoids repeating the work of finding the class and creating a new definition on subsequent calls.
- Ensures that successful loads of the same binary name through the same initiating loader return the already-recorded `Class<?>` object, without defining another class with a duplicate identity.
- Guards against `LinkageError` errors such as attempting to `defineClass` a duplicate binary name within the same defining loader.

For example, if a plugin loader has already defined `plugin.Greeter` once, calling `loadClass("plugin.Greeter")` again under the default sequence will find the already-loaded class in step 1. The second call **does not invoke `findClass`** for that name and does not need to re-read the bytecode file.

**Note:** `findLoadedClass` checks for an already-recorded class; it does not check whether the `.class` source file on disk has been newly modified. For the same runtime class, replacing the bytecode file after loading **does not automatically update** the already-defined class. True hot reload requires an appropriate mechanism (such as a new runtime class via a new defining loader, or instrumentation within JVM limits), not merely calling `loadClass` again.

## 4. Step 2 — Delegating to the Parent Loader

If not found in step 1, the default ClassLoader calls `parent.loadClass(name)` first. Each parent in turn applies its own policy; in a parent-first chain, the request typically travels from the child loader up to higher loaders until one loader finds the class.

```text
CustomPluginLoader
       │ ask parent first
       ▼
Application ClassLoader
       │ ask parent first
       ▼
Platform ClassLoader
       │ parent/boot access mechanism
       ▼
Bootstrap / built-in JVM loader
       │
       └─ if none of them finds it:
          fall back to trying findClass on the appropriate loader
```

The diagram is a **conceptual model**. On JDK 9+, the default loaders and the module system have their own lookup details; you should not assume the classpath and module graph are always represented purely as a chain of physical paths. For application/custom loaders that inherit the default implementation, the key idea remains **prioritizing the parent before the child loader defines a new class**.

### Why Prioritize the Parent?

1. **Reuse shared definitions:** for example, a plugin referencing `java.lang.String` must use the same standard runtime definition instead of constructing a separate copy.
2. **Maintain consistent type identity** for shared libraries/APIs between the main application and plugins when the parent provides them.
3. **Reduce accidental shadowing** of a class already found by the parent: if both parent and child contain a `com.acme.Api.class` file, the parent wins by default.
4. **Support separation of responsibilities:** the parent provides the platform/shared libraries; the child looks up its own classes when the parent does not have them.

This is a lookup rule, **not** an absolute guarantee against malicious code or version conflicts. A custom ClassLoader can change this policy; the JVM also enforces rules around packages/modules, accessibility, package sealing, bytecode, and runtime types.

### What Happens If the Parent Does Not Find It?

When parent is non-`null`, by default a `ClassNotFoundException` reporting not found from the parent is used as the signal to continue trying the child's `findClass`. If the parent **finds** it, the child immediately returns that class. If the parent throws another error such as `LinkageError` or `SecurityException`, do not infer that the default implementation will swallow all errors and silently search in the child: normal fallback is specifically for the **not-found** case.

If `parent == null`, the default ClassLoader uses the JVM's built-in bootstrap mechanism to check first, **not `ClassLoader.getSystemClassLoader()` as a substitute parent**.

## 5. Step 3 — findClass: The Current Loader Finds Bytecode Itself

API declaration:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException
```

This is the **primary extension point** when writing a custom loader that preserves parent-first delegation. The base `ClassLoader` implementation of `findClass(String)` simply throws `ClassNotFoundException`; to read classes from a directory, ZIP/JAR, network, generated code, or a custom data store, a subclass needs to override this method.

The steps in a custom `findClass` typically are:

1. Convert the binary name into the corresponding source location, for example `plugin.Greeter` → `plugin/Greeter.class`.
2. Read the **exact bytes** of the class file.
3. Call `defineClass(name, bytes, 0, bytes.length)` so the JVM defines the runtime class with the corresponding name.
4. Return the resulting `Class<?>`; if the data cannot be found, throw `ClassNotFoundException` (possibly with an I/O cause).

`defineClass` only defines the class from bytes; it **does not mean running `<clinit>`** for that class. Bytecode, module/package, access, and binary compatibility constraints are still enforced by the JVM.

### Why Typically Override findClass Instead of loadClass?

When you only override `findClass` and inherit `loadClass`, you automatically get:

- The default implementation's parent-first order.
- Checking `findLoadedClass` first, avoiding duplicate loading.
- Synchronization via `getClassLoadingLock(name)` during loading.
- Calling `resolveClass` when the protected overload is invoked with `resolve=true`.
- The error handling and fallback rules already specified by Java.

Overriding `loadClass` is appropriate only when **a different policy is genuinely needed** (such as child-first for a group of plugin namespaces), and in that case the author must explicitly handle already-loaded checks, protecting core platform classes, synchronization locks, fallback, and resolution.

## 6. Runnable Example 1: Parent Wins Before findClass

The following short example lets you observe the fallback without having to generate bytecode files yourself.

Create the file `ParentFirstDemo.java`:

```java
public class ParentFirstDemo {
    static final class TraceLoader extends ClassLoader {
        TraceLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("findClass: " + name);
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        TraceLoader loader = new TraceLoader(
                ParentFirstDemo.class.getClassLoader()
        );

        Class<?> core = loader.loadClass("java.lang.String");
        System.out.println("String defined by bootstrap: "
                + (core.getClassLoader() == null));

        try {
            loader.loadClass("my.example.DoesNotExist");
        } catch (ClassNotFoundException ex) {
            System.out.println("No such class");
        }
    }
}
```

Run with JDK 17+:

```bash
javac ParentFirstDemo.java
java ParentFirstDemo
```

Expected exact stdout on a standard Java SE JVM:

```text
String defined by bootstrap: true
findClass: my.example.DoesNotExist
No such class
```

**Explanation:**

- For `java.lang.String`, the parent/platform loader chain finds the class. `TraceLoader.findClass("java.lang.String")` **does not run**, so there is no `findClass: java.lang.String` line.
- For `my.example.DoesNotExist`, the parent does not find it; only then does the algorithm call `TraceLoader.findClass`, and we see the message before `ClassNotFoundException` is propagated back to the program.
- `String.class.getClassLoader() == null` is used by the JVM to represent a class defined by the bootstrap loader. The `null` value here **does not mean** `String` lacks a loader or failed to load.
- In this example, `findClass` intentionally does not define any class; the next example will load real bytes.

## 7. Runnable Example 2: Define a Class Yourself, Then Reuse It from findLoadedClass

We create a plugin class **not on the main program's classpath** and let a custom loader find it from a separate directory. This is a typical parent-first scenario: the parent does not have the plugin, so the child calls `findClass`.

### 7.1. Plugin File

In an empty working directory, create the file `Greeter.java`:

```java
package plugin;

public final class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public static String greet() {
        return "Hello from plugin";
    }
}
```

### 7.2. Host Program File

In that same working directory, create `PluginHost.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PluginHost {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class"
            );
            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }

            System.out.println("findClass: " + name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader = new DirectoryLoader(
                Path.of("plugin-classes"),
                PluginHost.class.getClassLoader()
        );

        Class<?> first = loader.loadClass("plugin.Greeter");
        System.out.println("defined by child: "
                + (first.getClassLoader() == loader));

        Class<?> second = loader.loadClass("plugin.Greeter");
        System.out.println("same Class object: " + (first == second));

        System.out.println("before first active use");
        Object result = first.getMethod("greet").invoke(null);
        System.out.println(result);
    }
}
```

### 7.3. Compile and Run

Create a separate output directory and compile:

```bash
mkdir plugin-classes
javac -d plugin-classes Greeter.java
javac PluginHost.java
java -cp . PluginHost
```

After the build step, the two parts are separated as follows:

```text
working-directory/
├── Greeter.java
├── PluginHost.java
├── PluginHost.class
├── PluginHost$DirectoryLoader.class
└── plugin-classes/
    └── plugin/
        └── Greeter.class
```

**Important:** When running the host, the classpath is `.`; do **not** add `plugin-classes` to the host classpath. If you add this path to the classpath and the parent can find `plugin.Greeter`, parent-first will return the parent's class, and `DirectoryLoader.findClass` may not run.

Exact stdout with the build structure above:

```text
findClass: plugin.Greeter
defined by child: true
same Class object: true
before first active use
Greeter initialized
Hello from plugin
```

### 7.4. Why Do the Lines Appear in This Exact Order?

1. `PluginHost.class` is loaded by the application loader. `DirectoryLoader` receives the host's loader as its parent.
2. On the `loader.loadClass("plugin.Greeter")` call: the `findLoadedClass` step does not have the class yet; the parent does not find it because `plugin-classes` is not on the classpath; `findClass` reads the bytes and calls `defineClass`.
3. The result of `first.getClassLoader() == loader` is `true` because **DirectoryLoader defined** the plugin class.
4. The second `loadClass` call returns the same `Class<?>`. `findClass` is not printed again: this class has already been recorded by the JVM with that loader.
5. `loadClass(name)` does not necessarily run the static block. The `Greeter initialized` line is printed only when reflection `Method.invoke` calls `greet()`, causing the JVM to require **initialization** of Greeter. Only after that is the string returned.

The example demonstrates all three aspects: **parent-first fallback**, **caching via `findLoadedClass`**, and the difference between **load** and **initialize**.

In production code, a loader that takes class names from external input must control namespaces, paths, source code, access permissions, packages/modules, and bytecode sources; this educational example only illustrates loading from a trusted directory.

## 8. Distinguishing findLoadedClass, findClass, and defineClass

| API | Responsibility | Return / Error | Key Point to Remember |
|---|---|---|---|
| `findLoadedClass(name)` | Look up a class already recorded with the initiating loader | `Class<?>` or `null` | Does not re-read bytecode, does not automatically call the parent |
| `parent.loadClass(name)` | Ask the parent loader to find the class | `Class<?>` or error | Prioritized before local lookup in parent-first delegation |
| `findClass(name)` | Hook to find/define a class from the child's source | `Class<?>` or `ClassNotFoundException` | Called in the default algorithm only when the parent does not find it |
| `defineClass(...)` | Define a runtime class from bytecode | `Class<?>` or format/linkage error | Does not automatically execute the class's initializer |
| `resolveClass(c)` | Request linking of the runtime class | `void` | Not `Class.forName(..., true, ...)` and does not mean initialization |
| `loadClass(name)` | Invoke the public class-lookup flow | `Class<?>` or error | Equivalent to requesting `loadClass(name, false)` on the API |

One commonly overlooked detail: `findLoadedClass` is `final`; you **cannot override** it to replace the cache. Ordinarily, you also **do not call `findClass` directly from application code**, because doing so bypasses the parent-first chain and the locking/already-loaded-class lookup mechanism of `loadClass`.

## 9. What If the Same Class Name Exists in Both Parent and Child?

Suppose two sources both contain the binary name `com.example.Engine`:

```text
Application ClassLoader:
  com/example/Engine.class    (version A)

Custom Child ClassLoader:
  com/example/Engine.class    (version B)
```

With the default `loadClass`, the child always asks the parent first. If the parent finds `com.example.Engine`, the child receives **version A**, even though the child's directory contains **version B**. The child's `findClass` is not called for that name.

This is **parent-first shadowing**: the parent retains priority over the name. When building plugins, you need to clearly design which namespaces are shared APIs and which namespaces are private to the plugin. If child-first is genuinely needed for a set of packages, you must write a conditional loading policy and ensure you do not accidentally reload core/shared classes in a way that causes `ClassCastException`, `LinkageError`, or breaks type identity.

**A class's runtime identity is not just its name string:** two classes with the same binary name defined by two different defining loaders are two distinct runtime classes. Parent-first helps shared classes be defined from a single parent, while plugin-specific classes defined by the child still have identities tied to the child.

Do not fix this conflict by replacing the bytecode file and calling `loadClass` repeatedly: after a successful load, the `findLoadedClass` branch prioritizes the already-recorded result.

## 10. Lookup Order Does Not Mean Initialization Order

`ClassLoader.loadClass("package.Type")` retrieves `Class<?>` and may link the class according to JVM policy, but **does not by itself require executing `Type.<clinit>`**.

Using `Greeter` from section 7 as an example:

```java
Class<?> type = loader.loadClass("plugin.Greeter");
// Does not yet request running Greeter's static initializer.

Object greeting = type.getMethod("greet").invoke(null);
// Calling a static method ⇒ requires initializing Greeter.
```

The code above is a **snippet** from the full example rather than a standalone Java file.

Conversely:

```java
Class<?> type = Class.forName(
        "plugin.Greeter",
        true,
        loader
);
```

With `initialize=true`, `Class.forName` requests initialization of the specified class if it has not yet been initialized. `Class.forName(name, false, loader)` does not request that. You should not use output from `static { System.out.println(...) }` to deduce the exact moment `findLoadedClass`, verification, or resolution runs; a static log only proves that **initialization** has occurred.

The `resolve=true` flag on the protected `loadClass(name, resolve)` method is also **not** an `initialize` flag. `resolveClass` links the class, while the JVM may defer resolution of certain symbolic references until they are actually used, according to the specification rules.

## 11. Distinguishing "Not Found" Errors from Definition/Linkage Errors

When attempting to load a class using parent-first delegation, not every error indicates that the `findClass` step should proceed:

| Symptom | Typical Meaning | What to Check |
|---|---|---|
| `ClassNotFoundException` | Parent and child could not find the binary name through the current loading path | Binary name, classpath, plugin directory, loader source |
| `NoClassDefFoundError` | The JVM needed a class during linking/execution, but its definition is missing or the class could not be initialized | Cause, dependencies, class that failed initialization earlier |
| `UnsupportedClassVersionError` | The bytecode requires a JVM supporting a newer major/minor version | `javap -verbose`, actual runtime JDK |
| `ClassFormatError` / `VerifyError` | Invalid class file data or bytecode | Source file, transformer, compiler |
| `LinkageError` due to duplicate definition | A custom loading path called `defineClass` multiple times for the same class in one loader | Find where `loadClass` is overridden, synchronization, duplicate defines |
| `ClassCastException` despite identical class names | Two runtime classes with the same name but different defining loaders | Check `getClassLoader()` on both sides |
| `SecurityException` | Violation of permission checks, package/module rules, or specific definition rules | JVM policy, namespace, bytecode source |

**Key rule of fallback:** by default, **control passes from the parent to `findClass` only when the parent cannot find the class**. `ClassNotFoundException` is the typical signal. A `LinkageError` or an error from the parent's bytecode structure can propagate straight out; do not interpret it as a reason for the child loader to try "another version".

If `findClass` reads a nonexistent path, you should convert the appropriate `IOException` into `ClassNotFoundException(name, cause)` to preserve lookup semantics. If bytes are available but do not form a valid class, defining it may throw a different error; do not mask that root cause with a generic "file not found" message.

## 12. Synchronization and Concurrent Requests for the Same Name Across Multiple Threads

The `synchronized(getClassLoadingLock(name))` block in the default implementation exists because two threads may call `loadClass("plugin.Greeter")` at the same time. If both see it as not yet loaded and then concurrently call `defineClass` with the same binary name on the same loader, at least one path could fail due to duplicate definition or produce an undesirable state.

By default, looking up the loaded class, delegation, fallback, and `resolveClass` are placed under the lock provided by `getClassLoadingLock`. For a properly registered **parallel capable** class loader, the lock can be per class name so independent names load concurrently; otherwise, synchronization typically happens on the loader object itself.

When a custom loader overrides `loadClass`, the author must independently review the synchronization and delegation rules. Arbitrarily having multiple loaders call into one another can also lead to deadlocks; you should not simply "remove synchronized to make it faster".

**Do not confuse these two loading cases:**

- Multiple threads concurrently requesting the **same binary name + same loader**: require coordination so there is no duplicate definition.
- Two **different defining loaders** defining the same binary name: produce two distinct runtime classes and can be valid for a plugin model, but are not interchangeable as the same Java type.

## 13. Some Limitations of the Default Model

- **Custom ClassLoaders can override `loadClass`:** frameworks/containers needing isolation or child-first behavior may choose a different policy. To know which order is actually used, inspect the specific loader's implementation.
- **Module-aware loading:** JDK 9+ has `findClass(String moduleName, String name)` and loaders serving named modules; how built-in loaders locate classes may consult the module graph rather than only simple file paths. This lesson describes the default `loadClass(String, boolean)` method of `java.lang.ClassLoader`.
- **Class resources differ from class loading:** `getResource`/`getResources` have related resource-lookup rules, but you cannot infer that class bytecode will definitely be defined merely because a resource URL of the same name is found.
- **Having bytecode does not mean having permission to define:** `defineClass` can be rejected due to class format, package name, module/package sealing, and other protection rules.
- **Do not confuse the app namespace with bootstrap:** `getClassLoader()==null` on core Java platform classes is how the bootstrap defining loader is represented, not a null-value bug to fix.

## 14. Procedure for Debugging Which Loader a Class Was Loaded From

When a plugin "is using the wrong class" or a child loader is not reading its plugin file, follow these steps in order:

1. Record the **binary name** passed into `loadClass` and which **loader object** receives the request first.
2. Check whether the class was previously **initiated/loaded** by that loader; if so, subsequent calls return the old class instead of reading a new file.
3. Inspect the **parent**: `loader.getParent()` and the caller class's loader chain, plus the actual JVM/module path/classpath. If the parent can find that name, the child's `findClass` may not run.
4. If the parent does not find it, inspect `findClass`: how the name is mapped to a path, the file bytes, `defineClass`, and any caught/wrapped errors.
5. For the returned class, log `type.getName()` and `type.getClassLoader()`. This is how you determine the name and **defining loader**; do not rely solely on the class name to prove that two `Class<?>` objects share the same identity.
6. If a runtime error occurs after loading completes, determine whether it is a **linking**, **initialization**, or program logic error before altering the class loading order.

Example JDK diagnostic command on a HotSpot JVM supporting unified logging:

```bash
java -Xlog:class+load=info -cp . PluginHost
```

The log can be very long and its format varies across JDK/VM versions. It helps observe where a class is **loaded** from, but should not be treated as guaranteeing that every `findLoadedClass`, `findClass`, or static initializer operation will be represented by a corresponding log line.

## 15. Self-Check

1. **After `loadClass("x.A")` has already been called successfully through the same loader, what does it check first by default next time?** `findLoadedClass("x.A")`; if already recorded, it returns that class.
2. **The child has its own copy of `x.A`, but the parent can also find `x.A`; which copy is used by default?** The copy loaded/returned by the parent.
3. **When is `findClass` called?** When it has not been found in `findLoadedClass` and the parent/bootstrap could not find that name.
4. **What happens if `findClass` is not overridden and the parent also does not find it?** The default `ClassLoader.findClass` implementation throws `ClassNotFoundException`.
5. **Does `findLoadedClass(name) != null` prove that the loader is the defining loader?** No; the initiating loader may have delegated definition to another loader.
6. **Does `loadClass(name)` run the static initializer?** Not necessarily; the public version is equivalent to `loadClass(name, false)`, which does not request initialization.
7. **Is `resolve=true` equivalent to `initialize=true` in `Class.forName`?** No; `resolveClass` performs linking, whereas initialization is a separate step.
8. **Why does the second `loadClass("plugin.Greeter")` call not print `findClass` in the example?** `findLoadedClass` already found the class defined by that loader on the previous call.
9. **If the parent throws `LinkageError` instead of `ClassNotFoundException`, is the child guaranteed to have `findClass` called?** No; the default implementation's fallback is for the class-not-found path.
10. **If you want a parent-first custom loader that reads bytes from a separate directory, what should you override?** `findClass(String)`; inherit `loadClass` to use the built-in cache-check, delegation, and locking flow.

## Official References

- [Java SE 21 API — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): describes the default order of `loadClass(String, boolean)`, `findLoadedClass`, `findClass`, `defineClass`, and `resolveClass`.
- [Java SE 26 API — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): the modern API contract, including differences related to modules and parallel-capable loaders.
- [Java Virtual Machine Specification — §5.3 Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): the meaning of defining/initiating loaders and class identity.
- [Java Language Specification — §§12.2–12.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): loading, linking, and initialization are steps with distinct meanings.

**Remember the default sequence:** `findLoadedClass` → **parent** (or bootstrap when there is no parent) → `findClass` → `resolveClass` if requested → return `Class<?>`. When writing a custom loader that follows the delegation model, overriding **`findClass`** is the most sensible starting point.
