# Prefer Overriding findClass When Keeping the Default Delegation Mechanism

## 1. Core Rule

When building a **custom class loader** in Java, if the goal is only to find and define classes from a new source (a directory, a private bytecode repository, or a special JAR/plugin source) while **still keeping the parent-first delegation mechanism**, the design recommended by the `ClassLoader` documentation is:

> **Extend `ClassLoader`, override `findClass(String name)`, and keep the superclass's `loadClass(String, boolean)` unchanged.**

Reason: the base class already provides a cached class lookup flow, parent delegation, synchronization locking, and an optional linking step. You only need to write the part **"when the parent cannot find the class, where does my loader get the bytecode and how does it define the class?"**. That part is the contract of `findClass`.

Division of responsibilities:

| Component | Primary Role | When Writing a Parent-First Loader |
| --- | --- | --- |
| `ClassLoader.loadClass(String)` | External API used to request a class by binary name; equivalent to `loadClass(name, false)`. | **Keep unchanged.** |
| `ClassLoader.loadClass(String, boolean)` | Coordinates caching, parent delegation, `findClass`, and optionally calls `resolveClass`. | **Usually keep unchanged.** |
| `findLoadedClass(String)` | Checks whether this loader has already been recorded by the JVM as an initiating loader for a class with the same name. | Already called by the default `loadClass`. |
| `findClass(String)` | Finds/defines a class from the **current loader's own source** after the parent fails to find it. | **This is where you should override.** |
| `defineClass(...)` | Turns valid bytecode into a `Class<?>` object, bound to the defining loader. | Called from `findClass` after reading the matching bytes. |
| `resolveClass(Class<?>)` | Requests linking of the class if needed. | Let the default `loadClass` call it when `resolve=true`. |

**Do not confuse:** `findClass` is not a general API for applications to call directly in order to bypass the parent. External code should call `loader.loadClass("pkg.Type")` (or an appropriate higher-level API), so that the entire standard workflow is applied.

## 2. Parent-First Delegation: Why Is Overriding Only findClass Enough?

The default algorithm of `ClassLoader.loadClass(String, boolean)` as described in Java SE 21:

1. Call `findLoadedClass(name)` to avoid finding/redefining an already known class with the same name.
2. If not yet loaded, call the parent's `loadClass`. If the parent is `null`, use the JVM's built-in bootstrap loader.
3. If the parent cannot find it, call `findClass(name)` on the current loader.
4. Once found and if `resolve == true`, call `resolveClass(c)`.
5. Return the `Class<?>` object; or throw `ClassNotFoundException` if it is not found anywhere.

~~~text
                loader.loadClass(name)
                         |
                         v
              findLoadedClass(name)?
                    /         \
                yes           not yet
                 |               |
                 |         parent.loadClass(name)
                 |            /      \
                 |        found     not found
                 |         |           |
                 |         |     findClass(name)
                 |         |       (override)
                 |         |           |
                 +---------+-----------+
                           |
                  return found Class<?>
                           |
             resolve=true? -> resolveClass(c)
~~~

This is the **logical model**; the actual mechanism also involves locking via `getClassLoadingLock(name)`, exception handling, and other JVM/JDK rules. The key point is that `findClass` **is called in the fallback step**, so you do not have to rewrite the entire algorithm yourself.

Example where the parent is the application loader and the child is a loader for a plugin directory:

~~~text
Application/System Loader (parent)
  ├── FolderLoaderDemo
  └── java APIs provided by parent/bootstrap
              ^
              |
        delegate first
              |
Custom FolderClassLoader (child)
  └── source root:
      out/plugin/
         plugin/Greeter.class
~~~

- `child.loadClass("java.lang.String")` receives the core class through delegation; there is no need for the child's `findClass` to redefine it.
- `child.loadClass("plugin.Greeter")` queries the parent first; only if the parent does not have the plugin does the child read `out/plugin/plugin/Greeter.class` in `findClass`.
- If the parent **already** has `plugin.Greeter`, the child receives the parent's version. Overriding `findClass` does not invert priority to the child.
- If the child has already received that class before, subsequent calls can return the recorded `Class<?>` without reading the class file again.

The **defining loader** is the loader that actually defines the class via `defineClass`; the **initiating loader** may merely be the loader that initiated the request that was delegated to the parent. The two concepts are not always the same object.

## 3. The findClass(String) Contract: What Name Does It Receive, What Result Does It Return?

Common signature:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    // Find the bytecode by binary name, then defineClass.
}
~~~

This is an illustrative skeleton, not a complete method. Important rules:

- `name` is a **binary name**, for example `plugin.Greeter`, not `"plugin/Greeter.class"` or a file path.
- If reading from a class file tree, map the name according to its package: `plugin.Greeter` → `plugin/Greeter.class`; the path is resolved **under the root** owned by the loader.
- If the name **does not exist in the loader's own source**, throw `ClassNotFoundException(name)`, optionally preserving a `cause` such as `NoSuchFileException`.
- If reading the file encounters an `IOException`, you can wrap it in `ClassNotFoundException` with the original cause for caller diagnostics; do not silently return `null` from this single-parameter overload.
- Once the bytes are found, use `defineClass(name, bytes, 0, bytes.length)` with the **exact matching name and bytes**. Do not pass the name of class A with bytecode declaring class B.
- Do not convert `ClassFormatError`, `VerifyError`, or `LinkageError` into `ClassNotFoundException` via a generic `catch(Throwable)`. Those errors do not mean "file not found".
- The default `findClass` in `ClassLoader` simply throws `ClassNotFoundException`; overriding it is where you implement your custom source lookup logic.

### Why Call defineClass Instead of Just Returning Bytes?

`defineClass` creates the `Class<?>` object according to the JVM contract. Once the class is successfully defined, this loader becomes the **defining loader** of that normal class. The runtime identity of a class/interface depends on the pair of **binary name and defining loader**, not just the package name.

Therefore, do not maintain an independent cache like `Map<String, Class<?>>` and accidentally return a class defined by another loader without a clear reason. `findLoadedClass` and the standard algorithm already coordinate with the JVM to prevent multiple definitions within the same loader.

## 4. Standalone Java 17+ Example: A Loader Reading Bytecode from a Directory

This example has **two Java source files** compiled into **two separate output directories**. The plugin class is **not on the host's classpath** at runtime, proving that the child actually uses `findClass`.

### Project Structure

~~~text
example/
├── source/
│   ├── plugin/
│   │   └── Greeter.java
│   └── host/
│       └── FolderLoaderDemo.java
└── output/
    ├── plugin/          <-- after compilation
    │   └── plugin/
    │       └── Greeter.class
    └── host/            <-- after compilation
        ├── FolderLoaderDemo.class
        └── FolderLoaderDemo$FolderClassLoader.class
~~~

### File `source/plugin/Greeter.java`

~~~java
package plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public static String greet() {
        return "Hello from plugin";
    }
}
~~~

### File `source/host/FolderLoaderDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class FolderLoaderDemo {
    static final class FolderClassLoader extends ClassLoader {
        private final Path root;

        FolderClassLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path classFile = root.resolve(
                    binaryName.replace('.', '/') + ".class").normalize();

            if (!classFile.startsWith(root)) {
                throw new ClassNotFoundException(binaryName);
            }

            final byte[] bytes;
            try {
                bytes = Files.readAllBytes(classFile);
            } catch (NoSuchFileException e) {
                throw new ClassNotFoundException(binaryName, e);
            } catch (IOException e) {
                throw new ClassNotFoundException(
                        "Cannot read class: " + binaryName, e);
            }

            System.out.println("findClass: " + binaryName);
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("plugin root");
        }

        ClassLoader parent = FolderLoaderDemo.class.getClassLoader();
        FolderClassLoader loader =
                new FolderClassLoader(Path.of(args[0]), parent);

        Class<?> jdk = loader.loadClass("java.lang.String");
        System.out.println("parent class: " + (jdk == String.class));

        Class<?> plugin = loader.loadClass("plugin.Greeter");
        System.out.println("plugin defined by child: "
                + (plugin.getClassLoader() == loader));

        System.out.println("cached Class: "
                + (plugin == loader.loadClass("plugin.Greeter")));

        System.out.println("method: "
                + plugin.getMethod("greet").invoke(null));

        try {
            loader.loadClass("plugin.Missing");
        } catch (ClassNotFoundException expected) {
            System.out.println("missing: ClassNotFoundException");
        }
    }
}
~~~

Decisive point: **`FolderClassLoader` only overrides `findClass`**; it does not override `loadClass`. Every call path through `loader.loadClass(...)` uses the built-in caching, parent-first delegation, and standard synchronization mechanism of `ClassLoader`.

`Path.toAbsolutePath().normalize()` uses the current directory at the time the loader is created to determine the plugin root. `Files.readAllBytes` is convenient for small `.class` files in experiments; production code must enforce size limits and input validation if the source is untrusted. Checking `classFile.startsWith(root)` prevents escaping the root after syntactic path normalization, but it is not a **complete symlink/path traversal defense** for untrusted sources; production requires dedicated filesystem controls and a security model.

### Running on Linux/macOS

From the `example` directory:

~~~bash
mkdir -p output/plugin output/host

javac --release 17 -d output/plugin source/plugin/Greeter.java
javac --release 17 -d output/host source/host/FolderLoaderDemo.java

java -cp output/host FolderLoaderDemo output/plugin
~~~

Do not add `output/plugin` to the `-cp` argument of the final `java` command. If added, the parent would find `plugin.Greeter` on its own, causing the child's `findClass` not to be called.

### Running on Windows PowerShell

In the `example` directory:

~~~powershell
New-Item -ItemType Directory -Force output\plugin, output\host | Out-Null

javac --release 17 -d output\plugin source\plugin\Greeter.java
javac --release 17 -d output\host source\host\FolderLoaderDemo.java

java -cp output\host FolderLoaderDemo output\plugin
~~~

### Exact Stdout

~~~text
parent class: true
findClass: plugin.Greeter
plugin defined by child: true
cached Class: true
Greeter initialized
method: Hello from plugin
missing: ClassNotFoundException
~~~

The code was compiled with `javac --release 17` and executed with actual Java; stdout matches the output above.

### Output Analysis

1. **`parent class: true`** — the call to load `java.lang.String` through the child is satisfied by the parent/bootstrap loader. There is no `findClass: java.lang.String` line, so the child does not define its own copy of the JDK class.
2. **`findClass: plugin.Greeter`** — the parent cannot find the plugin, so the default `loadClass` calls the child's `findClass` override to read the bytecode from `output/plugin/plugin/Greeter.class`.
3. **`plugin defined by child: true`** — the class was created via `FolderClassLoader`'s `defineClass`.
4. **`cached Class: true`** — calling `loader.loadClass("plugin.Greeter")` a second time returns the same `Class<?>` object; the `findClass` log line does not appear again.
5. **`Greeter initialized`** — `loadClass` does not automatically run the static initializer; invoking `greet` via reflection is an active use of a `static` method, so the JVM initializes the class before the invocation.
6. **`method: Hello from plugin`** — the return value from the `greet` method body.
7. **`missing: ClassNotFoundException`** — `plugin.Missing` is present in neither the parent nor the child directory, so `findClass` throws a class lookup exception and `loadClass` propagates that error to the caller.

The example uses reflection so that the host does not need to compile directly against the `plugin.Greeter` type. If the host had `import plugin.Greeter;` and compiled with the plugin on the compile classpath, you would have to carefully manage the runtime classpath and loader resolution; that is a more complex dependency topic. Here, the focus is on **the right place to override when preserving parent-first**.

## 5. Why Should You Not Override loadClass Unnecessarily?

If you override `loadClass(String, boolean)`, you must manually guarantee many invariants that the superclass already handles:

| Easily Forgotten Responsibility | If `loadClass` Is Overridden Carelessly |
| --- | --- |
| Checking `findLoadedClass(name)` | May redefine the same binary name → `LinkageError` or other errors. |
| Querying the parent first | Breaks parent-first, potentially creating incompatible duplicate API/JDK classes. |
| Falling back to `findClass` | Loses custom source lookup or improperly swallows `ClassNotFoundException`. |
| Using `getClassLoadingLock(name)` | Two threads attempt `defineClass` simultaneously; risk of races, errors, and deadlocks. |
| Handling `resolve` | Forgets `resolveClass(c)` when `resolve == true`, altering the contract with callers. |
| Preserving original errors | Swallows `LinkageError`/`SecurityException` and falsely reports "class not found". |
| Respecting the parent loader | Results in the class being defined in a loader other than what the rest of the system expects. |

**Illustrative error scenario** (do not use in real programs):

~~~java
@Override
public Class<?> loadClass(String name) throws ClassNotFoundException {
    byte[] bytes = readBytes(name); // illustrative method, does not exist
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

This code is **intentionally incorrect and not standalone runnable**. It bypasses caching, parent delegation, and class loading locks; it may repeatedly look up and define already loaded classes. It also risks attempting to define core classes or shared interfaces instead of receiving them from the parent.

**Proper fix when parent-first is still needed:** remove the unnecessary `loadClass` override and move the `readBytes(name)` + `defineClass(...)` logic into `findClass(name)` as in the Section 4 example.

### Parent-First Is Especially Useful for Shared APIs

Suppose the host defines `api.Plugin` and the child defines `plugins.GreetingPlugin implements api.Plugin`. When the child queries the parent first, it uses the **exact same `Class<?>` of `api.Plugin`** that the host sees. If the child loader defines a separate copy of `api.Plugin` with the same name, casting the plugin object to the host-side API can result in a `ClassCastException` or type linkage error.

Parent-first helps unify the platform and shared interfaces while still allowing the child to read its own classes from `findClass`. However, if the host parent already has a library with the same binary name as the plugin, parent-first will prefer the parent's version. **If you truly need to isolate two versions, you must design a dedicated loader policy**, rather than simply forcing every case through `findClass`.

## 6. Important Knowledge About Concurrency and Caching

The default `loadClass(String, boolean)` synchronizes during loading using the monitor returned by `getClassLoadingLock(name)`. Class loaders registered as **parallel capable** can have per-name locks, but subclasses have their own appropriate registration requirements; do not assume that all child loaders are automatically parallel capable just because the `ClassLoader` superclass is registered.

In the `FolderClassLoader` example, `loadClass` is not overridden, so the base locking logic remains active. `findClass` still must **not create uncontrolled threads/races** or dangerously write bytecode concurrently into the directory.

A successful `defineClass` call binds the class to its defining loader. Redefining the **same name within the same loader** can cause a `LinkageError`, even if you modified the bytes on disk. To load a new version in an independent class namespace, you typically create a **new loader** and manage the lifecycle of old objects/classes. Modifying the `.class` file in place does not cause an already loaded class to automatically update.

Distinguish carefully:

- `findLoadedClass` queries the JVM as to whether this class loader has already been recorded as loading a class by that name; it is not a `Map` that you are allowed to modify directly.
- `defineClass` turns bytecode into a runtime class and can throw `LinkageError`/`ClassFormatError` if invalid.
- `resolveClass` is the linking step requested by the overload with `resolve=true`; it is not a command to run the static initializer.
- `loadClass(name)` is equivalent to the `resolve=false` overload, though the JVM still retains the right to link classes at any valid point according to the specification.

## 7. Exception Handling in findClass

For a file-reading loader, a tricky question is "when the class cannot be found or the bytecode is invalid, what should be thrown?":

| Scenario | Appropriate Outcome | Why? |
| --- | --- | --- |
| `plugin/Missing.class` does not exist | `ClassNotFoundException(name)` | The loader cannot find the class by its binary name. |
| Reading file throws `NoSuchFileException` | Wrap as `ClassNotFoundException(name, cause)` | Preserves the filesystem root cause. |
| File exists but cannot be read due to I/O error | `ClassNotFoundException(..., cause)` in the illustrative file loader | The caller sees the lookup failure along with its original cause; production may need a clearer policy. |
| Corrupted bytecode | `ClassFormatError` | Do not mistakenly turn it into a missing file error. |
| Passed name does not match the name defined in the bytes | `NoClassDefFoundError` may be thrown by `defineClass` | "Wrong name" is a different error from file not found. |
| Attempting to redefine a name already present in the same loader | `LinkageError` | Duplicate class definition. |
| Attempting to define a name starting with `java.` from an application loader | `SecurityException` | The JVM protects the platform namespace per the `defineClass` contract. |
| Class has another dependency missing during resolution | Possibly `NoClassDefFoundError` at the time the JVM needs that class | Does not necessarily occur right when `findClass` returns. |
| Plugin's static initializer throws an exception | Possibly `ExceptionInInitializerError` when the class is initialized | This is not the responsibility of `findClass`. |

Do not mask all errors with `catch (Throwable e) { throw new ClassNotFoundException(name); }`. Doing so loses the cause and hides critical runtime errors. In the example, only **I/O** errors when reading bytes are wrapped; Java linkage/format errors determined by the JVM are left intact.

## 8. What If You Want to Load Resources?

`findClass(String)` **only handles classes**. It does not automatically make the loader find other resources such as `plugin/config.yml`:

~~~java
Class<?> pluginType = loader.loadClass("plugin.Greeter");
URL resource = loader.getResource("plugin/config.yml");
~~~

The snippet above is illustrative, assuming a loader and resource exist. The default `getResource` also has its own parent-first mechanism; to find resources from the plugin directory, you may need to override `findResource(String name)` or choose an existing loader such as `URLClassLoader`. Distinguish clearly:

- `findClass("plugin.Greeter")`: binary name using `.` separators, returns `Class<?>`.
- `findResource("plugin/config.yml")`: resource name using `/` separators, typically returns a `URL` or `null`.
- `findResources(String name)`: can return multiple matching URLs when multiple resources with the same name are needed, depending on the implementation.

Overriding only `findClass` does not automatically create a custom resource search mechanism; however, loaded Java classes can still access resources provided by the parent according to the loader's capabilities. When the actual task is to load both classes and resources from a **JAR or directory**, `URLClassLoader` generally involves less code and lower risk than writing a custom file loader.

## 9. When Do You Actually Need to Override loadClass?

A valid reason is **wanting to change the class lookup policy**, not merely changing the bytecode source. Examples:

- **Child-first** for a specific plugin namespace: look up the plugin version before the parent, while continuing to use the parent for JDK/shared APIs.
- **Reverse delegation or multi-parent** in complex container/module designs, where simple parent-first is insufficient.
- **Blocking/filtering binary names** according to system rules, though the consequences for type linkage and platform APIs must still be considered.
- **Customizing parallel/synchronized loading** when having a genuinely specialized loader architecture and a team with a deep understanding of the `ClassLoader` contract.

In such cases, you must design the complete algorithm: `synchronized(getClassLoadingLock(name))` or an equivalent locking strategy, `findLoadedClass(name)`, lookup order, parent fallback, `resolveClass` if needed, class identity, shared interfaces, failure handling, and deadlock avoidance. Class loaders with **non-strictly-hierarchical** delegation relationships require special consideration for **parallel capability** according to the documentation.

A child-first policy **does not automatically mean** that every parent can see the child's dependencies. Use explicit loaders or shared SPIs/interfaces to communicate across layers. Do not accidentally override `loadClass` just because you want to read bytes from a new directory: that is precisely the job of `findClass`.

## 10. Common Mistakes and How to Fix Them

**Mistake 1: Overriding both loadClass and findClass when only changing the source directory.** Unnecessary. Put the byte-reading logic into `findClass`; keep the default delegation/caching and synchronization.

**Mistake 2: Calling super.findClass(name) inside findClass expecting a parent search.** The default `super.findClass` throws `ClassNotFoundException`; it is not a parent lookup algorithm. The parent has already been tried by `loadClass` before the `findClass` override is called.

**Mistake 3: Passing the path `plugin/Greeter.class` to loadClass.** The API expects the binary name `plugin.Greeter`. Convert the name to a file path **inside findClass**, not at the API caller.

**Mistake 4: The plugin class is accidentally on the application classpath.** Parent-first will find the plugin first; the child's `findClass` will not run. When testing a custom loader, keep the plugin in a separate directory and pass only the host classpath at runtime.

**Mistake 5: Reading class bytes and calling defineClass with the wrong name.** This can cause a wrong-name `NoClassDefFoundError`. The binary name must match `this_class` inside the class file.

**Mistake 6: Reading from the filesystem without limits.** `Files.readAllBytes` is simple but unsuitable for overly large files or untrusted sources. Enforce size limits, control symlinks, and only use bytecode from trusted sources.

**Mistake 7: Assuming closing a file or deleting the `.class` file makes the JVM unload the class.** An already defined class has its own lifecycle; when an update is needed, create a new loader and manage old references.

**Mistake 8: Expecting a findClass override to automatically handle resources and native libraries.** The relevant hooks are `findResource/findResources` and `findLibrary`; choose the API that matches your needs.

**Mistake 9: Compiling the host against plugin classes and then dropping the runtime classpath without considering resolution.** Classes defined by the parent cannot find dependencies that exist only in the child loader. Use reflection or shared interfaces defined by the parent to design plugin boundaries.

**Mistake 10: Catching `Exception` or `Throwable` and reporting every error as ClassNotFoundException.** Keep linkage/format/security errors with their proper types and causes for diagnostics.

## 11. Decision Checklist

Before coding a custom loader, answer these sequentially:

1. Do I only need to **change the byte source**, or must I **change the delegation order**? If only changing the source, override `findClass`.
2. Is the class file root correct? `plugin.Greeter` resides at `root/plugin/Greeter.class`, not `root/Greeter.class`.
3. Which parent is needed to share the JDK and common APIs? Is there a class with the same name on the parent classpath?
4. Do callers invoke `loadClass(binaryName)` rather than calling `findClass` directly to bypass delegation?
5. Does `findClass` map names to paths accurately, validate source files, and return `Class<?>` from `defineClass`?
6. Do missing-file/I/O errors preserve `ClassNotFoundException` with their cause? Are linkage/format errors preserved with their proper types?
7. Do concurrent calls use the superclass's original synchronization algorithm? Is there any risk of duplicate self-definition?
8. Does the loader need its own resources/JARs? Should `URLClassLoader` be used instead of writing a custom `findClass`?
9. Is a new class in a new loader needed for hot reload? An already loaded class cannot simply be "redefined" into the same loader.
10. Have you verified `getClassLoader()`, stdout, compile/runtime classpaths, and the `ClassNotFoundException` behavior for a non-existent class?

### Self-Check Questions

**Question 1.** Why does `findClass("plugin.Greeter")` not print a log when the parent already has `plugin.Greeter`?

**Answer:** Because `loadClass` follows parent-first and queries the parent first. If the parent returns a class, it does not call the child's `findClass`.

**Question 2.** Why does only one `findClass` log appear after calling `loader.loadClass("plugin.Greeter")` twice?

**Answer:** The loader/JVM has already recorded that class; `findLoadedClass` allows the subsequent call to return the existing `Class<?>` without redefining it.

**Question 3.** If you want to load two versions with the same binary name in two independent plugins, should you define both in the same loader?

**Answer:** No. You need **two separate defining loaders** and an appropriate communication API design to avoid invalid casts across two namespaces.

**Question 4.** If you want to load classes from a JAR without a special policy, is it mandatory to write a custom findClass using `JarFile`?

**Answer:** No. `URLClassLoader` already supports directories and JARs; a custom `findClass` is appropriate when special control over the bytecode source is needed while preserving parent-first.

## Official References

- [Java SE 21: ClassLoader.loadClass(String, boolean)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)): default algorithm and recommendation to override `findClass`.
- [Java SE 21: ClassLoader.findClass(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#findClass(java.lang.String)): contract for finding classes when the parent cannot find them.
- [Java SE 21: ClassLoader.defineClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#defineClass(java.lang.String,byte%5B%5D,int,int)): defining a class from bytes, binary names, and exceptions.
- [Java SE 21: URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): built-in solution for directories/JARs.
- [JVMS Java SE 21 §5.3: Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): defining loader, initiating loader, and class identity.
