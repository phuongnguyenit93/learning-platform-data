# findClass: The Extension Point for Finding Bytecode in Java ClassLoader

## 1. Why Does Java Need `findClass`?

When the JVM needs a Java class, a `ClassLoader` may be asked to load the class by its **binary name**, such as `com.example.plugin.PaymentPlugin`. However, the class's bytecode may reside in a separate directory, a plugin JAR, a repository, an application-managed source, or a specialized loading mechanism. Java provides the **`findClass(String name)`** method so that a `ClassLoader` subclass can define how to **find and create a class definition from bytecode** when the loading algorithm chooses to use the loader's local source.

Three methods have different roles:

- **`loadClass(name)`**: the standard entry point for requesting a class; the default implementation handles already-loaded classes, delegates to the parent, and only then turns to `findClass`.
- **`findClass(name)`**: the *extension point* for finding a definition in the data source managed by the current loader. Subclasses typically override this method.
- **`defineClass(name, bytes, ...)`**: converts a sequence of bytes containing a valid class definition into a runtime `Class<?>` object associated with the **current defining loader**.

Therefore, **`findClass` is not another name for the entire class-loading operation**. This method is typically called when parent delegation does not find the class. Nor does it mean merely returning a `.class` file: if you implement `findClass` yourself to define a class, you typically have to read the bytecode and call `defineClass`.

### Guiding Question

Suppose the application writes:

```java
Class<?> c = pluginLoader.loadClass("plugins.Report");
```

At this point, there are at least two scenarios:

1. **The parent has `plugins.Report`:** the parent returns the `Class` object; the child loader may **never call** `findClass`. The defining loader is the parent.
2. **The parent does not have it, and the plugin loader has its own bytecode:** `loadClass` calls `findClass` on the child loader; `findClass` reads the bytecode and uses `defineClass`. The defining loader is the plugin loader.

Both scenarios are normal outcomes of parent-first delegation. The line calling `loadClass` does not by itself reveal where the class is defined.

## 2. API Signature, Defaults, and Override Access

In `java.lang.ClassLoader`:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException
```

This is an API signature used for illustration, not a standalone runnable program.

- **`protected`**: subclasses can override it to implement a bytecode source. Arbitrary code outside the class/appropriate access scope cannot call a loader's `findClass` directly.
- **Returns `Class<?>`**: returns the runtime definition found by the loader. The method does not return `byte[]` or `Path`.
- **`throws ClassNotFoundException`**: when the source the loader is responsible for does not contain the requested class, this exception is typically thrown. `ClassNotFoundException` is a checked exception.
- **Default implementation of `ClassLoader.findClass(String)`**: throws `ClassNotFoundException`. Therefore, a subclass that only calls `super(parent)` without overriding `findClass` will not automatically search for classes in arbitrary directories.
- **The method takes no parent argument**: querying the parent belongs to the logic flow of `loadClass`; `findClass` has a local responsibility once selected.

Minimal template:

```java
public final class BytecodeLoader extends ClassLoader {
    public BytecodeLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String binaryName)
            throws ClassNotFoundException {
        byte[] bytes = readOwnBytecode(binaryName);
        return defineClass(binaryName, bytes, 0, bytes.length);
    }

    private byte[] readOwnBytecode(String binaryName)
            throws ClassNotFoundException {
        throw new ClassNotFoundException(binaryName);
    }
}
```

This is a **structural outline**. The `readOwnBytecode` method intentionally lacks a data source implementation, so this is not a fully functional loader. In the hands-on section below, there is a complete, compilable, and runnable Java 17 program.

**Important:** if you only need to load classes from JAR/directory URLs, `URLClassLoader` already provides a suitable mechanism for many scenarios. Write `findClass` yourself when you need a different way of reading bytecode, or when you need explicit control over the source and lifecycle.

## 3. Where Does findClass Fit in the Parent-First Algorithm?

The default execution of `ClassLoader.loadClass(String, boolean)` can be explained as follows:

1. Acquire the appropriate class-loading lock for the requested name (the `getClassLoadingLock(name)` mechanism).
2. Call `findLoadedClass(name)` to check whether the loader has already been recorded as the initiating loader for that class.
3. If not found, try querying the **parent**. When there is no Java-level parent, a mechanism is used to look up the class in the bootstrap loader.
4. If the parent path cannot find the class and throws `ClassNotFoundException`, call **`findClass(name)`** on the current loader.
5. If the request has the parameter `resolve = true`, the JVM may execute `resolveClass(c)`; return the `Class<?>` object.

Diagram:

```text
Application / JVM requests: child.loadClass("plugin.Report")
                    |
                    v
        findLoadedClass("plugin.Report")
                    |
           found? --+--> return recorded Class
                    |
                not found
                    |
                    v
            parent.loadClass(...)
                    |
         succeeded? --yes--> return Class defined by parent/ancestor
                    |
             ClassNotFoundException
                    |
                    v
            child.findClass(name)
                    |
          find bytecode -> defineClass(...)
                    |
                    v
               return Class
```

Two misconceptions should be avoided:

- **`findClass` does not always run.** If the parent returns the class, the local search path does not need to be executed.
- **`findClass` should not call `loadClass(name)` with the very name being processed** to "try again"; this easily leads to infinite recursion or a class-lookup cycle. If another class needs to be loaded, only use the API appropriate for the specific dependency and delegation relationship.

The diagram describes the **default**, not a mandatory rule for every custom loader. A framework may override `loadClass` to prioritize child-first loading by package. In that case, the point where `findClass` is called changes according to the framework's algorithm.

## 4. From Class Name to Bytecode: Paths and Data Sources

If the binary name is `com.acme.plugin.Report`, the corresponding class file in a typical classes directory has the relative path:

```text
com/acme/plugin/Report.class
```

One way to obtain the path on a platform with `Path`:

```java
Path file = classesRoot.resolve(
        binaryName.replace('.', '/') + ".class");
```

This is an **illustrative snippet**; it assumes the variables `classesRoot` and `binaryName` are already available, not a standalone program.

Points to remember:

- `binaryName` differs from a file path: the method parameter is `com.acme.plugin.Report`, **not** `com/acme/plugin/Report.class`.
- Nested classes have binary names containing `$`, for example `Outer$Inner`. Do not convert `$` into `.` yourself.
- Not every class corresponds to an easily located file on disk: classes in JARs, module images, generated bytecode, hidden classes, and array classes have different mechanisms.
- The path must be constrained within the allowed root area. If the name/path source comes from configuration or user input, validate the binary name, normalize the path, and prevent escaping the root.
- `findClass` must close resources when reading data; appropriate I/O errors can be wrapped into `ClassNotFoundException` so the caller sees the class name and root cause.

For real-world JARs, consider using `URLClassLoader`, `JarFile`, or a managed library instead of manually extracting them while ignoring manifests, multi-release JARs, package sealing, or bundled resources.

## 5. Complete Java 17+ Experiment: Writing Your Own DirectoryClassLoader

The following program shows **the entire chain** from a load request to bytecode:

1. Temporarily create the source code of a plugin.
2. Use the compiler built into the JDK to compile the class into a temporary directory.
3. Instantiate a class loader whose `findClass` reads the `.class` file in that directory.
4. Call `loadClass` twice with the same name to observe the same `Class`.
5. Compare the invoked loader with the defining loader; check the case where the class is already available in the parent.
6. Use reflection to create an instance and invoke a method, without needing to link the plugin class into the project beforehand.

Create the file `DirectoryClassLoaderDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DirectoryClassLoaderDemo {

    static final class DirectoryLoader extends ClassLoader {
        private final Path root;
        int localSearches;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            localSearches++;

            Path file = root.resolve(
                    binaryName.replace('.', '/') + ".class").normalize();
            if (!file.startsWith(root)) {
                throw new ClassNotFoundException(binaryName);
            }

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException e) {
                throw new ClassNotFoundException(binaryName, e);
            }

            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("find-class-demo-");
        Path source = root.resolve("plugin/Greeter.java");
        Path bytecode = root.resolve("plugin/Greeter.class");

        try {
            Files.createDirectories(source.getParent());
            Files.writeString(source, """
                    package plugin;
                    public class Greeter {
                        public String message() {
                            return "Hello from plugin";
                        }
                    }
                    """);

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Run with a JDK");
            }
            int result = compiler.run(null, null, null,
                    "-d", root.toString(), source.toString());
            if (result != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            DirectoryLoader child = new DirectoryLoader(
                    root, DirectoryClassLoaderDemo.class.getClassLoader());

            Class<?> first = child.loadClass("plugin.Greeter");
            Class<?> again = child.loadClass("plugin.Greeter");

            System.out.println("definedByChild="
                    + (first.getClassLoader() == child));
            System.out.println("sameClass=" + (first == again));
            System.out.println("localSearches=" + child.localSearches);

            Object instance = first.getDeclaredConstructor().newInstance();
            Method method = first.getMethod("message");
            System.out.println("message=" + method.invoke(instance));

            Class<?> fromParent = child.loadClass(
                    DirectoryClassLoaderDemo.class.getName());
            System.out.println("hostDefinedByParent="
                    + (fromParent.getClassLoader()
                       == DirectoryClassLoaderDemo.class.getClassLoader()));
            System.out.println("searchesAfterParent="
                    + child.localSearches);

            Class<?> stringType = child.loadClass("java.lang.String");
            System.out.println("stringFromBootstrap="
                    + (stringType.getClassLoader() == null));

            try {
                child.loadClass("plugin.Unknown");
            } catch (ClassNotFoundException e) {
                System.out.println("missing=ClassNotFoundException");
            }
            System.out.println("searchesAfterMissing="
                    + child.localSearches);
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(bytecode);
            Files.deleteIfExists(root.resolve("plugin"));
            Files.deleteIfExists(root);
        }
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac DirectoryClassLoaderDemo.java
java DirectoryClassLoaderDemo
```

Expected stdout if there is no class with the same name on the classpath, the compiler successfully generates the bytecode, and there are no environment errors:

```text
definedByChild=true
sameClass=true
localSearches=1
message=Hello from plugin
hostDefinedByParent=true
searchesAfterParent=1
stringFromBootstrap=true
missing=ClassNotFoundException
searchesAfterMissing=2
```

### Detailed Explanation of Results

**`definedByChild=true`:** the `plugin.Greeter` class was only created in the temporary directory. The child's parent is not configured to search that directory; it fails, so the child falls back to `findClass`, reads the bytecode, and calls `defineClass`. Therefore, the defining loader of `Greeter` is `child`.

**`sameClass=true` and `localSearches=1`:** the first `loadClass` call creates the class definition and records the loaded state. The second call with the same loader and same name is satisfied by the already recorded class (by default via `findLoadedClass`); the file is not read again, and `defineClass` is not called a second time.

**`message=Hello from plugin`:** the application code does not import `plugin.Greeter`. Reflection on the `Class<?>` object returned by the loader can still create an instance and invoke its public method.

**`hostDefinedByParent=true`, `searchesAfterParent=1`:** the request to load `DirectoryClassLoaderDemo` is handled by the parent. The child does not need to call `findClass`, so the counter remains unchanged. The same `loadClass` API can return a class defined by another loader.

**`stringFromBootstrap=true`:** the request for `java.lang.String` goes through the platform class-lookup mechanism; `String.class.getClassLoader() == null` indicates the bootstrap loader.

**`missing=ClassNotFoundException` and `searchesAfterMissing=2`:** `plugin.Unknown` exists neither in the parent nor in the bytecode directory, so `findClass` fails to read it and throws `ClassNotFoundException`. The counter increments by one. The program only catches the exception for demonstration purposes and does not turn the failure into a dummy class.

**Execution requirements:** requires a JDK that includes `javax.tools.JavaCompiler`. The directory is created with `Files.createTempDirectory` and deleted after the experiment; the code does not interfere with existing project files. In another environment, if the parent already has `plugin.Greeter` or restricts creating temporary files, the output will change or the program will report an error.

## 6. defineClass Is the Definition Step, Not Just Reading Data

In the `findClass` just written:

```java
return defineClass(binaryName, bytes, 0, bytes.length);
```

This is an **excerpt** from the runnable example above. The call performs class definition using the class file bytes. Several consequences:

- The binary name passed in must match the actual definition in the bytecode. You cannot "arbitrarily rename a class" by supplying a different `name`.
- Invalid bytecode can cause `ClassFormatError`, `VerifyError`, or other linkage errors; you should not catch all of them and pretend the class does not exist.
- Defining a duplicate binary name within **the same defining loader** can cause a `LinkageError`. Do not bypass the reuse mechanism and attempt to call `defineClass` multiple times.
- The JVM enforces rules, including restricting a custom loader from defining classes in the `java.*` namespace and checks related to packages/certificates. Do not use a custom loader to try replacing JDK platform classes.
- Overloads of `defineClass` allow passing a `ProtectionDomain` when needed. Fetching bytecode from another source **does not automatically turn a class loader into a secure sandbox**; untrusted code sources require a dedicated security isolation model.
- A defined class may need to load its superclass, superinterfaces, and other dependencies when the JVM links or executes it. A successful `defineClass` call does not guarantee that every subsequent behavior of the class will succeed.
- `resolveClass(c)` (a protected/final method) relates to linking/resolution, **which is different from initialization**. Calling `loadClass` also does not mean the class's static initializer has already run.

If `Greeter.class` has the right name but references `plugin.Helper`, which cannot be found, `Greeter` may fail at another linking/usage step depending on the reference type and resolution timing. Therefore, a custom loader must know how to find all required dependencies as well, or design delegation for them.

## 7. Relationship with findLoadedClass: Why Not Redefine the Class Every Time?

`ClassLoader.findLoadedClass(String)` is a **protected final** method. It returns a `Class<?>` if the JVM has already recorded the corresponding loader as an initiating loader for the class with that binary name; otherwise, it returns `null`.

The default implementation of `loadClass` queries `findLoadedClass` **before** the parent and `findClass`. This brings two important points:

1. If a suitable class already exists, `loadClass` can immediately return the same `Class` object without reading the bytecode again.
2. What is reused is **the runtime definition**, not merely a result stored in an application-managed `Map<String, byte[]>`.

You should not turn every `loadClass("plugin.Greeter")` request into a new `defineClass` call; within a single loader, the same binary name cannot be repeatedly defined as independent versions.

### findLoadedClass Does Not Imply the Defining Loader

If the child loader was previously recorded by the JVM as an **initiating loader** of a class defined by the parent, `findLoadedClass` can return that class, yet `clazz.getClassLoader()` still returns the **parent**. Initiating loader recording is part of the JVM model, distinct from class identity (binary name + defining loader).

There is no direct public API on `Class<?>` to retrieve "all initiating loaders that have ever requested this class." Checking `clazz.getClassLoader() == child` tests for the defining loader, not whether child has ever submitted a request.

**Do not implement your own Map cache instead of findLoadedClass without understanding concurrency:** a self-managed cache can break when multiple threads load the same name, when delegation changes the outcome, or when the JVM records the loader as initiating a class via another path. If no special algorithm is required, keeping the default `loadClass` is simpler and safer.

## 8. Concurrency Across Multiple Threads: Where Should the Logic Live?

Multiple threads may concurrently call `loader.loadClass("plugin.Greeter")`. By default, `ClassLoader.loadClass(String, boolean)` uses `getClassLoadingLock(name)` to coordinate class loading; a loader registered as *parallel capable* can use a per-class-name lock instead of a single shared lock.

When overriding only **`findClass`**, you typically reuse the existing steps of `loadClass`: checking for already-loaded classes, synchronization, delegation, and resolution when requested. This is why you should override `findClass` if you only want to change the bytecode source.

If you decide to override **`loadClass`** itself to implement child-first loading, you must preserve the necessary rules yourself:

- Check whether the class has already been recorded as loaded before defining a new one.
- Synchronize appropriately so two threads do not simultaneously attempt `defineClass` for the same name.
- Keep mandatory shared namespaces shared, especially JDK classes and shared APIs/SPIs.
- Clearly specify when to call the parent, when to search locally, and how to report errors.
- Ensure linking, method signatures, and type identity do not conflict.

In a custom subclass, `getClassLoadingLock(name)` is the API for obtaining the synchronization lock used by the `ClassLoader` mechanism. However, simply writing a `synchronized` block is not enough to prove a custom child-first loader is safe; you must test race conditions, class circularity, and classloader constraints.

**Distinction:** synchronization of **class loading/definition** here is different from synchronization of **static initialization** `<clinit>`. The JVM also has separate rules to ensure a runtime class is properly initialized before active use.

## 9. findClass vs. findResource and Other Resources

Overriding `findClass` to read `plugin/Greeter.class` **does not automatically** make the following calls find all resources located in the custom directory:

```java
loader.getResource("plugin/config.properties");
loader.getResources("META-INF/services/example.Service");
```

The lines above are for illustration. `ClassLoader` has its own mechanisms including `getResource`, `findResource`, `findResources`, stream variants, and module interactions. If a plugin needs configuration files, images, metadata files, or ServiceLoader provider files, you must ensure resource lookup is also configured.

With `URLClassLoader`, much of the class and resource lookup behavior is already provided. If you write a custom loader yourself, you need to separate responsibilities:
- **Class loading:** map a binary name to bytecode and define the appropriate class.
- **Resource loading:** map a resource name to a valid URL/stream according to the designed priority order.
- **Service discovery:** determine which loader is used to locate providers and keep shared SPIs with the same runtime identity.
- **Package/module boundary:** preserve package relationships, sealing, and proper module configuration.

Do not arbitrarily turn resource lookup failures into class loading errors; the two API flows have different contracts and return types.

## 10. When Should You Use URLClassLoader Instead of Overriding It Yourself?

If the bytecode resides in **standard class directories or JARs**, `URLClassLoader` is usually the simpler choice. It already includes URL-based class lookup and handles the necessary resource/JAR processing.

Illustrative configuration example:

```java
try (java.net.URLClassLoader loader =
         new java.net.URLClassLoader(
             new java.net.URL[]{classesDir.toUri().toURL()},
             App.class.getClassLoader())) {

    Class<?> plugin = loader.loadClass("plugin.Greeter");
    System.out.println(plugin.getClassLoader() == loader);
}
```

**This is a snippet, not a standalone program**: `classesDir` and `App` must be provided by the application. The result is only `true` if the parent does not define `plugin.Greeter` and this loader actually defines the plugin class; it depends in practice on the classpath/URLs and delegation.

When you need a custom bytecode source such as in-memory generated data or an application-managed protocol, overriding `findClass` is often appropriate, but you must consider input validation, lifecycle management, whether the executed code is trusted, and testing concurrent loading.

### When Closing a Loader, Do the Classes Automatically Disappear?

`URLClassLoader.close()` releases managed resources, such as open JAR files. However, closing the loader does **not** guarantee immediate unloading of all classes it has defined. Class unloading depends on reachability: as long as any instance, `Class<?>` object, thread, thread context class loader, callback, static registry, or cache holds a reference to the loader/class, the JVM may still retain that definition.

If you need to "reload a plugin", creating a new class definition usually requires a **new class loader**, while releasing references to the old loader when stopping the plugin. Do not attempt to call `defineClass` again for the same binary name in the old loader to replace bytecode.

## 11. Errors and Diagnostic Signals

| Error/symptom | Hypothesis to check | Troubleshooting direction |
| --- | --- | --- |
| `ClassNotFoundException` from `findClass` | Bytecode not found in local source or I/O failed | Check binary name, root path, classpath, cause, and permissions |
| `NoClassDefFoundError` after finding the class | Required dependency missing, bytecode name mismatch, or prior class initialization failure | Read message/cause; check class name and actual dependencies |
| `ClassFormatError` / `VerifyError` | Invalid bytecode or violation of JVM constraints | Check compiler/class file format; avoid modifying bytecode arbitrarily |
| `UnsupportedClassVersionError` | Bytecode was compiled for a newer JVM than the current JVM | Run on an appropriate JVM or compile with a compatible target release |
| `LinkageError: duplicate class definition` | Attempted to call `defineClass` again for the same binary name in one loader | Keep default `loadClass`, use `findLoadedClass`, and synchronize appropriately |
| `SecurityException` when defining a class | Violated package/source/condition restrictions of `defineClass` | Do not attempt to define classes in JDK namespaces; review API contract |
| `findClass` is not observed being called | Parent already has the class or the loader previously recorded the class | Log the delegation path and `clazz.getClassLoader()` |
| `findClass` ran, but host API cannot cast | Plugin defined its own copy of the SPI with the same name instead of using parent's | Place shared interfaces/DTOs in a shared loader |
| `NoSuchMethodError` after loading class successfully | Runtime API version does not match compiled bytecode | Check which loader defined the class and inspect the actual JAR |
| Resources in plugin cannot be found | Custom loader only overrides `findClass` and does not implement resource lookup | Check `findResource`/`getResource` and the plugin mechanism |

### Concrete Investigation Workflow

1. **Record the full binary name** and the requested loader: `myLoader.loadClass(name)`.
2. **Observe `findClass`**: log the class name, checked location, file status, and IOException cause if present. Avoid dumping entire bytecode arrays into logs.
3. **If loading succeeds, print the defining loader** using `clazz.getClassLoader()`; parent-first may yield a loader different from the one requested.
4. **Check the definition count**: a loader should not redefine the same binary name on a second request.
5. **Inspect the exception cause**, specifically distinguishing missing bytecode, missing dependency, invalid bytecode, and failed initialization.
6. **Check the runtime JDK**: verify whether the class file version is compatible and whether the environment has all required classes/modules.
7. **If multiple plugins or loaders exist**, compare defining loaders at the SPI boundary to prevent two separate copies of a class with the same name.
8. **If errors appear after reload**, check lingering references and lifecycle design; the old class loader may not have been released.

On supported JVMs, you can use unified logging to observe class-loading events:

```bash
java -Xlog:class+load=info DirectoryClassLoaderDemo
```

This log does not replace tracing parent delegation and `findClass` inside a custom loader, because merely looking at the class file path does not fully explain why a specific loader was chosen.

## 12. Common Misconceptions

**"Overriding `findClass` means the application is guaranteed to prioritize the child loader's class."** False. Parent-first delegation in `loadClass` can still select the parent's class first.

**"`findClass` is called every time `loadClass` is called."** False. An already recorded class may be returned from `findLoadedClass`; the parent may also handle it first.

**"`findClass` must traverse the parent hierarchy itself."** That is not the default responsibility of this extension point; the standard `loadClass` algorithm already handles that.

**"Returning a byte array is enough for the class to be loaded."** False. There must be a valid runtime definition created through an appropriate API such as `defineClass`.

**"A single loader can define multiple versions of the same binary name."** No. Having two independent definitions with the same binary name requires different defining loaders, subject to JVM constraints and rules.

**"`ClassNotFoundException` and `NoClassDefFoundError` are always the same error."** False. One is a checked exception thrown when looking up a class via an API, whereas the other is a `LinkageError` with many causes, including missing dependencies or failed initialization.

**"Overriding `findClass` automatically loads resources and ServiceLoader provider metadata."** False. Resource lookup has its own APIs and flows.

**"A custom ClassLoader is a security sandbox."** False. A mechanism for defining classes from bytecode does not by itself create secure isolation for untrusted code.

## 13. Self-Check Questions

**Question 1.** `child.loadClass("api.Service")` succeeds, yet the child's `findClass` is not called. Could this be completely valid?

**Answer:** Yes. The parent or an already recorded result may satisfy the request before the local `findClass` branch runs.

**Question 2.** If `child.findClass("plugin.Greeter")` has successfully read the bytecode, what must it do to return the runtime class?

**Answer:** For a loader that defines classes in the standard way, call `defineClass` with the corresponding binary name and valid bytecode, then return `Class<?>`.

**Question 3.** Why does loading `plugin.Greeter` a second time in the `DirectoryLoader` example not increment `localSearches`?

**Answer:** By default, `loadClass` checks `findLoadedClass` first; the same runtime class has already been recorded, so it is returned instead of being defined a second time.

**Question 4.** What happens if a custom loader reads bytecode from `plugin/Greeter.class` but calls `defineClass("plugin.Other", ...)`?

**Answer:** The passed binary name does not match the definition; the JVM rejects it rather than renaming the class, typically manifesting as a linkage/name mismatch error.

**Question 5.** The child loader contains a newer version of `lib.Json`, while the parent already has an older `lib.Json`. Why is the child's `findClass` not called?

**Answer:** Parent-first delegation selects the parent's definition first. Proper boundaries and delegation policies must be designed instead of merely adding the JAR to the child loader.

**Question 6.** A plugin can load `Greeter.class` but cannot find `plugin/config.properties`. Should we conclude that `findClass` is broken?

**Answer:** Insufficient evidence. `findClass` handles classes; resource lookup requires `getResource`/`findResource` and resource source configuration.

**Question 7.** If two threads simultaneously request a class name, what is the benefit of overriding only `findClass`?

**Answer:** You can continue to leverage the class-loading lock, already-loaded class check, and delegation in the default `loadClass`, reducing the risk of duplicate definitions. You still need to ensure that your `findClass` implementation and data source are thread-safe under concurrent access.

## 14. Conclusion and References

`findClass(String)` is **the extension point for finding bytecode** so that a `ClassLoader` knows how to define a class from its own source. In the default model, `loadClass` decides **when to call** this extension point, while `defineClass` performs the **runtime definition** from bytecode. Clearly understanding these three responsibilities helps avoid duplicate definitions, wrong loaders, type identity conflicts, and confusion between class loading and resource loading.

Official documentation:

- Java SE 17 `ClassLoader` API, including `loadClass`, `findClass`, `findLoadedClass`, and `defineClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- JVMS 17 §5.3, *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
