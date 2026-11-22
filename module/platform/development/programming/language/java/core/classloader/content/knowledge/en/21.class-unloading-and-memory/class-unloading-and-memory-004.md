# Relationships Between Class, Instance Objects, and ClassLoader During Class Unloading in Java

## 1. Central Question: What Remains Alive When a Plugin Stops Running?

In a plugin system, the application creates a dedicated `URLClassLoader`, asks it to load `plugin.Widget`, creates an instance, executes some methods, and then closes the loader. At that point, there are three types of objects/concepts to distinguish:

1. **`ClassLoader` instance:** the object that organizes finding and defining classes; it defines the runtime namespace for the classes it defines.
2. **`Class<?>` object:** the reflective representation (*class mirror*) for **a specific runtime class/interface**. It can be obtained via `Widget.class`, `instance.getClass()`, or the result of `loadClass`.
3. **Instance of a class:** a regular object created from that class via a constructor, reflection, factory, or another mechanism.

These three things are related, yet they are **not the same object**, nor do they share the same lifecycle conditions. Closing the ClassLoader's resources does not cause instances to disappear automatically, and clearing an instance reference variable does not mean the classes have been unloaded.

Key questions:

- Why does `object.getClass().getClassLoader()` identify the loader that defined the object's type?
- Why can retaining an instance, a `Class<?>`, or a thread executing plugin code prevent the class/loader from becoming eligible for reclamation?
- Why do two loaders using the same bytecode produce two different Java types?
- How do `URLClassLoader.close()`, garbage collection, class unloading, and Metaspace differ?
- How do you identify **GC root → object → class/loader** in a memory leak incident?

This is the core of the **Class ↔ instance ↔ loader** relationship in the context of **class unloading and memory**.

## 2. Visualizing the Three Entities and Their Links

Example source code:

```java
package plugin;

public final class Widget {
    public String message() {
        return "hello";
    }
}
```

This is the source of a sample class, not a standalone program with `main`.

When a custom loader `L` defines `plugin.Widget` and then creates two instances, this can be visualized as:

```text
Custom ClassLoader object L
        |
        | defining loader of runtime class
        v
Runtime class: ("plugin.Widget", L)
        |
        +-- Class<?> mirror C
        |       C.getName()          = "plugin.Widget"
        |       C.getClassLoader()   = L
        |
        +-- Instance A ---- A.getClass() == C
        |
        +-- Instance B ---- B.getClass() == C
```

The diagram is a **conceptual model**: the JVM may organize heap, mirrors, and metadata differently depending on the implementation. You should not infer that every arrow corresponds to a public Java field directly observable via reflection.

Comparisons that normally hold true when both objects are created from the same runtime class:

```java
Class<?> aType = a.getClass();
Class<?> bType = b.getClass();

System.out.println(aType == bType); 
System.out.println(aType.getClassLoader() == definingLoader);
```

This is a **snippet** (requiring variables `a`, `b`, and `definingLoader`). `Class<?>` represents a runtime definition, not a plain text descriptor and not an instance of `Widget`.

### Why is `Class<?>` an object, yet different from the object being studied?

`java.lang.Class` is a class belonging to the Java platform. `Widget.class` itself is a Java object of type `Class<Widget>` or `Class<?>`. In contrast, `new Widget()` is an **instance of `Widget`**. The differences:

- `Widget.class.getName()` queries the name of the type definition.
- `widget.getClass()` returns the class mirror of the instance's runtime type.
- `Widget.class.getClassLoader()` returns the **defining loader** of `Widget`.
- `Widget.class.getClass()` describes the class of the **class mirror**, which is normally `java.lang.Class`; it does not return `Widget`.
- The class literal `Widget.class` in host code requires the Widget type to be available to the host's loader/linkage; in a dynamic plugin system, the host usually cannot import a concrete implementation and instead works through a shared interface along with reflection.

**Do not equate** the statement "a Class is an object" with "a new class object is created for each instance". Two instances of the same runtime class normally return **the same `Class<?>` object** from `getClass()`.

## 3. Runtime Class Identity: Binary Name Plus Defining Loader

The JVM identifies a runtime class/interface by the pair:

```text
(binary name, defining ClassLoader)
```

Example:

```text
("plugin.Widget", PluginLoader#1) !=
("plugin.Widget", PluginLoader#2)
```

Even if two loaders read **the exact same bytecode byte-for-byte**, if each loader defines `plugin.Widget` itself, they are **two distinct runtime types**.

| Property | Class in Loader A | Class in Loader B |
| --- | --- | --- |
| `getName()` | `plugin.Widget` | `plugin.Widget` |
| `getClassLoader()` | A | B |
| `Class<?> ==` | Not equal to the one in B | Not equal to the one in A |
| Can an instance be cast to the other? | Not merely because the name/bytes match | Not merely because the name/bytes match |
| Static fields | Bound to runtime class A | Bound to runtime class B |
| Class initialization | Independent per class A | Independent per class B |

If a child loader calls `loadClass("plugin.Widget")` while the parent already has that class, the result can be the class **defined** by the parent. In that case, the child loader is only the **initiating loader**, not the defining loader. Many pieces of code confuse the loader that was invoked with the loader that establishes type identity.

### The Case of `java.lang.String` and the Bootstrap Loader

Core classes such as `java.lang.String` are defined by the bootstrap loader in a standard Java environment. Therefore:

```java
System.out.println(String.class.getClassLoader() == null);
```

typically prints:

```text
true
```

The `null` value returned by `Class.getClassLoader()` is the API representation for the **bootstrap loader**; it does not mean that the `String` type "has no loader" in the JVM model.

For **primitive types** such as `int.class` and `void.class`, `getClassLoader()` also returns `null` per the API, though you should not infer that these are class files defined by a regular bootstrap ClassLoader. For **array classes**, the JVM creates the array class according to its own rules; the defining loader is associated with the reference element type, or represented as bootstrap if the element type is primitive.

## 4. When an Instance Remains Reachable, What Is Kept Alive?

Suppose the host holds:

```java
Object pluginInstance = pluginType
        .getDeclaredConstructor().newInstance();
```

This is a snippet; `pluginType` is the Class mirror of the plugin implementation and the constructor is accessible.

While `pluginInstance` remains reachable, the JVM must retain enough of its runtime type to identify and use that object. If the defining loader and the runtime classes it defines were unloaded arbitrarily, the VM would no longer have a valid type/method dispatch model for the live instance.

For class unloading under the JVMS, a class/interface **can only** be unloaded when its defining ClassLoader can be reclaimed by the garbage collector. This is a **necessary condition**, not a command forcing the JVM to unload the class immediately after a Java reference is set to `null`.

References from the host that commonly keep a plugin from being ready for reclamation:

```text
GC Root (thread / static field / registry)
   |
   v
Host service registry
   |
   v
Plugin instance
   |
   v
Runtime class / JVM metadata
   |
   v
Defining ClassLoader
```

The arrows involving runtime class/loader represent a **VM-level reachability relationship diagram**, without assuming that a Java instance has a `ClassLoader loader;` field. The key point is that **a class definition cannot be unloaded while its instances are still needed**.

### What If a Class<?> Is Retained?

A reference from the host to a plugin class's `Class<?>` can also anchor the class definition and its defining loader. For example:

```java
static final Map<String, Class<?>> PLUGIN_CLASS_CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

This is a snippet requiring `Map` to be imported or fully qualified; the `Class<?>` from the plugin stored in a long-lived map will itself be a point to inspect when investigating a loader leak.

Similarly, `Method`, `Constructor`, `MethodHandle`, proxy metadata, lambdas, method references, and framework reflection caches can maintain reference paths that keep the old loader's code reachable. The exact degree of object retention depends on the implementation/API, yet **do not look only for direct references to the ClassLoader itself**.

## 5. Java 17 Example: Two Loaders, Two Class Objects, Instance Still Usable After Close

This experiment generates a class file at runtime using `JavaCompiler` (JDK 17+), and then reads the same bytecode directory through **two independent `URLClassLoader` instances**. We measure things that can be asserted **independently of GC**:

1. The same class name and the same bytecode do not produce the same runtime `Class<?>` if the defining loaders differ.
2. Each instance returns the exact class mirror defined by its corresponding defining loader.
3. Closing a URLClassLoader does not automatically cause an existing instance to lose the ability to execute methods that have already been defined.
4. Platform classes still come from bootstrap/parent delegation.

### 5.1. Full Code: `ClassInstanceLoaderDemo.java`

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class ClassInstanceLoaderDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use JDK 17+ with javac");
        }

        Path work = Files.createTempDirectory("class-instance-loader-");
        try {
            Path source = work.resolve("src/plugin/Widget.java");
            Path classes = work.resolve("classes");
            Files.createDirectories(source.getParent());
            Files.createDirectories(classes);

            Files.writeString(source, """
                    package plugin;
                    public final class Widget {
                        public String message() {
                            return "hello";
                        }
                    }
                    """);

            int exit = compiler.run(null, null, null,
                    "--release", "17",
                    "-d", classes.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            URL classesUrl = classes.toUri().toURL();
            ClassLoader parent = ClassLoader.getPlatformClassLoader();

            Class<?> typeA;
            Object instanceA;

            try (URLClassLoader loaderA = new URLClassLoader(
                        new URL[]{classesUrl}, parent);
                 URLClassLoader loaderB = new URLClassLoader(
                        new URL[]{classesUrl}, parent)) {

                typeA = loaderA.loadClass("plugin.Widget");
                Class<?> typeB = loaderB.loadClass("plugin.Widget");

                instanceA = typeA.getDeclaredConstructor()
                        .newInstance();
                Object instanceB = typeB.getDeclaredConstructor()
                        .newInstance();

                System.out.println("sameBinaryName="
                        + typeA.getName().equals(typeB.getName()));
                System.out.println("sameClass=" + (typeA == typeB));
                System.out.println("aDefiningIsA="
                        + (typeA.getClassLoader() == loaderA));
                System.out.println("bDefiningIsB="
                        + (typeB.getClassLoader() == loaderB));
                System.out.println("instanceClassIsA="
                        + (instanceA.getClass() == typeA));
                System.out.println("crossLoaderCompatible="
                        + typeA.isInstance(instanceB));
                System.out.println("stringBootstrap="
                        + (loaderA.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }

            // Both loaders have been closed, but instanceA/typeA
            // still have references in the current scope.
            Object result = typeA.getMethod("message")
                    .invoke(instanceA);
            System.out.println("afterClose=" + result);
        } finally {
            try (Stream<Path> stream = Files.walk(work)) {
                for (Path path :
                        stream.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ClassInstanceLoaderDemo.java
java ClassInstanceLoaderDemo
```

Expected stdout on JDK 17+ with a compiler and permission to create temporary files:

```text
sameBinaryName=true
sameClass=false
aDefiningIsA=true
bDefiningIsB=true
instanceClassIsA=true
crossLoaderCompatible=false
stringBootstrap=true
afterClose=hello
```

### 5.2. Line-by-Line Explanation

- **`sameBinaryName=true`:** both types carry the name `plugin.Widget` according to `Class.getName()`.
- **`sameClass=false`:** because two independent `URLClassLoader` instances defined that class separately; their `Class<?>` mirrors are different.
- **`aDefiningIsA=true` and `bDefiningIsB=true`:** class A is defined by loader A, and class B is defined by loader B. Sharing the same class directory URL does not merge them into one type.
- **`instanceClassIsA=true`:** instanceA belongs to runtime class A; `instanceA.getClass()` returns class mirror A.
- **`crossLoaderCompatible=false`:** instanceB is not considered an instance of class A, even though the source code and class name are identical.
- **`stringBootstrap=true`:** the `String` class is defined by the bootstrap loader rather than being defined separately by each plugin loader.
- **`afterClose=hello`:** after both `URLClassLoader` instances are closed by try-with-resources, `instanceA` and `typeA` still retain references and can invoke the already-loaded method. This demonstrates that **`close()` is not `unload()`**.

The program does not call `System.gc()` and makes no assumptions about when class unloading occurs, because GC/class unloading does not produce time-deterministic stdout.

### 5.3. Limitations of the Demo

- The `Widget` class does not depend on any other custom classes loaded lazily from the `classes` directory after the loader is closed. If a method needs to load an additional dependency that was not defined before `close()`, a loading error can occur after close. Do not infer that closing a URLClassLoader is harmless across all execution flows.
- The example retains `typeA` and `instanceA` via local references to **deliberately prevent concluding that unloading has occurred**.
- This is only an example of classes on the **classpath** via `URLClassLoader`, not a complete module layer or plugin framework implementation.
- Deletion of the temporary directory only occurs after both loaders are closed; it can fail if the environment denies file deletion, which is a resource cleanup error independent of class identity.
- The `--release 17` option ensures Java 17 bytecode for the generated class; the demo project runs on Java 17+ which includes text blocks and stream `toList()`.

## 6. ClassLoader.close() Is Not the Class Unloading Process

`URLClassLoader` implements `Closeable`, so it can be used with try-with-resources:

```java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    Class<?> plugin = loader.loadClass(binaryName);
    // Create instances and execute while the loader is open.
}
```

This is a snippet; the variables `urls`, `parent`, and `binaryName` must exist in the application.

**What does `close()` do?** According to the `URLClassLoader` API, it closes the JAR/resource files the loader has opened and prevents certain operations from finding additional new classes/resources from the URLs managed by the loader. It **does not**:

- Automatically call `Plugin.stop()` or `AutoCloseable.close()` on every plugin instance.
- Automatically close worker executors, sockets, JDBC connections, or event listeners created by the plugin.
- Automatically remove already-defined `Class<?>` objects, linked methods/fields, or still-reachable Java objects.
- Force `System.gc()` or guarantee that the JVM unloads immediately upon close.
- Turn live instances into "invalid" objects; already-loaded methods can continue running.
- Guarantee that an old loader is no longer retained by host static caches, TCCL, or framework metadata.

### When Does a Class Have a Chance to Be Unloaded?

The key rule from the JVMS is that a runtime class/interface may be unloaded **if and only if** its defining loader can be reclaimed by the GC. In practice, for a custom loader to become eligible for reclamation, the application must ensure there are no remaining strong reference paths from GC roots to the loader or to the classes/instances and runtime structures keeping the loader alive.

This does not mean:

```text
pluginLoader = null;
System.gc();
=> Class has finished unloading
```

The diagram above is **a false conclusion**, not code you can rely on. Setting a reference to null only removes **one edge**. GC is a process decided by the JVM; many other references may exist that keep the loader reachable.

### Why Might the JVM Keep Class Metadata in Metaspace?

On the HotSpot JVM, class metadata is typically stored in **Metaspace** (native memory), whereas `Class<?>` mirrors are Java objects under the runtime model. Reference paths from heap/thread/static roots can still keep the class/loader and related metadata alive.

Consequently, a plugin application may:

- Not grow the heap very much while Metaspace grows after hundreds of reloads.
- Produce a heap dump showing that loader/plugin classes are retained by listeners, caches, or threads.
- Reduce Metaspace pressure once classloaders that are genuinely no longer needed are unloaded, though how much OS memory is returned and when unloading happens depend on the JVM/GC and allocator.

**Do not equate** `OutOfMemoryError: Metaspace` with `OutOfMemoryError: Java heap space`. Both indicate memory pressure, yet the memory region and the root causes to investigate are different.

## 7. Reference Cycles Do Not Always Cause Leaks

A diagram that easily misleads beginners:

```text
Plugin ClassLoader
   -> runtime class / metadata
   -> static field
   -> plugin instance
   -> object using that class
   -> back link to runtime class
```

One might assume that "if there is a reference cycle, the GC cannot reclaim it." In reality, **the garbage collector is based on reachability from GC roots**, rather than simply counting references and rejecting all cycles.

If a group of objects only reference one another and are **no longer reachable from GC roots**, the GC can reclaim the entire group under the appropriate JVM conditions/mechanisms. The same reasoning applies when a loader and its classes/instances are no longer retained by the host, threads, registries, or other roots.

A reference cycle between a plugin instance and a callback becomes a serious problem **when the host event bus is a GC root or is reachable from a root**:

```text
GC Root
   -> static HostEventBus
   -> callback
   -> plugin instance
   -> plugin runtime class
   -> loader
```

Merely removing the plugin from a `PluginManager.map` **does not** eliminate the path through the event bus if the event bus still holds the callback. Therefore, unloading a plugin requires **unregistering wherever it was registered**.

## 8. Common Reference Paths That Retain a ClassLoader

Common retaining paths include **host cache → `Class<?>`/instance**, event bus → plugin callback, pool thread → TCCL/`ThreadLocal`, executor queue → pending task, and service/framework registry → provider instance.

Although they are all references to the plugin, their owners and cleanup mechanisms differ. Use a heap dump's `path to GC roots` to find the actual long-lived source; the lessons on static caches, threads, and ServiceLoader explain these root types with separate examples.

## 9. WeakReference<ClassLoader>: What Can and Cannot Be Observed?

`WeakReference<ClassLoader>` does not keep the loader alive solely through that reference itself, making it suitable for observing reclaimability. However, `weak.get() != null` after one attempt does not prove a leak; `weak.get() == null` indicates that the referent has been cleared, and **does not by itself provide logs for individual class unloads**.

Avoid holding `Class<?>`, an instance, a `Method`, or the loader in local variables when testing eligibility. The lesson on observing unloading distinguishes these signals from JVM events.

## 10. Reloading a Plugin Means Creating a New Defining Loader, Not Swapping Bytes in the Old Loader

A loader that has already defined `plugin.Widget` normally returns the same old `Class<?>` when `loadClass("plugin.Widget")` is called again. To use a new definition, create a new loader, safely transition lifecycle/traffic, and then retire the old loader.

An instance of the old version still belongs to the old runtime type; closing the URL loader does not alter the type identity or static state of a live class.

## 11. Common Errors Related to Class–Instance–Loader

A `ClassCastException` between two identical names usually indicates two different defining loaders. A `LinkageError` in the form of a loading constraint violation involves an API signature linked with two incompatible runtime types. An `IllegalAccessError` can reflect different runtime packages even when the source package names match.

To diagnose these, directly compare `Class<?>` and `getClassLoader()` on both sides. These errors relate to **type/linkage/access** and do not automatically prove class unloading or a memory leak.

## 12. Practical Diagnostic Tools and Strategies

### 12.1. Inspecting the Defining Loader from an Instance and Class Mirror

A helper used in the application:

```java
static void describe(Object instance) {
    Class<?> type = instance.getClass();
    System.out.println("type=" + type.getName());
    System.out.println("definingLoader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
```

This is a snippet (it must be placed inside a class and passed an appropriate instance). If the class was created by a custom loader whose display name is unstable, also log the loader ID assigned by the framework for the **version/plugin session**. `System.identityHashCode(loader)` only assists diagnosis and is not a collision-free global ID.

### 12.2. Observing Class Loading/Unloading

JDK/HotSpot can provide:

```bash
java -Xlog:class+load=info,class+unload=info -cp app/classes com.example.Main
```

The command uses spacing/arguments suitable for a Unix shell and the Java launcher; substitute app/classes and the main class name for your actual project. Logs when the JVM unloads classes do **not** necessarily appear immediately after close, because unloading is asynchronous with respect to the close API.

Some reference attach/statistics commands:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
```

These are example commands requiring `<pid>` to be substituted, and they depend on the JDK/VM, attach permissions, and operational overhead. Classloader stats can help reveal the count of classes/loaders; a thread dump helps show still-running plugin threads and associated TCCLs/stacks. A heap histogram helps inspect instance classes; no single command by itself proves that the entire disposal workflow is correct.

### 12.3. Analyzing GC Roots and Reference Paths

When a leak is suspected:

1. Identify a specific old loader that should have exited its lifecycle.
2. Check whether the class mirrors and instances it defined are still being retained.
3. Trace the **path to GC root** of the loader/instance using a heap dump/profiler.
4. Pay attention to static fields in the host, event bus, TCCL, ThreadLocal, and shared library caches.
5. Check for live threads executing plugin classes/code.
6. Verify that listener/route/metric/MBean/JDBC driver registrations have been unregistered.
7. Track trends across multiple load–stop–dispose cycles rather than drawing conclusions from a single snapshot.
8. If the loader is unreachable yet the classes have not unloaded, consider GC/VM behavior and evaluation conditions instead of immediately calling it a ClassLoader bug.

**Important:** a plugin may clean up threads properly yet still leak because of a host `Class<?>` cache. Conversely, a cache that does not hold class mirrors can still leak through a plugin instance. You must inspect the entire reference graph.

## 13. Comparing Plugin States with Memory States

| State | Instance | Class<?> | ClassLoader | Meaning |
| --- | --- | --- | --- | --- |
| Plugin ACTIVE | Typically reachable | Has runtime definition | Actively serving | Normal |
| Plugin STOPPED but registry not cleaned up | May still be reachable | Present | Usually still reachable | Risk of leak |
| Plugin DISPOSED, loader closed | May still have references in host/cache | May still be present | May still be reachable | Close does not prove unload |
| Plugin has no remaining strong reference path from roots | Can be reclaimed by GC if unreachable | Can be reclaimed by VM along with class metadata per rules | May be eligible for GC | **Has an opportunity** to unload, with no deadline |
| GC has actually reclaimed the defining loader | Cannot have instances requiring that runtime class in normal reachable heap | Related runtime class can unload per VM mechanism | Reclaimed | Result observed after GC, not directly caused by `close()` |

This is a conceptual table. Timing, allocator behavior, GC mode, class mirror layout, and class unloading support depend on the JVM; do not apply specific time/memory figures without measuring.

## 14. Common Misconceptions

**"Each object holds its own separate Class<?> copy."** False. Instances of the same runtime class normally return the same `Class<?>` mirror.

**"`instance.getClass().getClassLoader()` is always the loader that called `loadClass`."** False. If parent delegation returned the class, the defining loader may be the parent/bootstrap loader.

**"Two Classes with the same name created by two loaders are the same type."** False. Runtime type identity consists of both the binary name and the defining loader.

**"Once `URLClassLoader.close()` is called, all instances created by the loader must become unusable."** False. Existing classes/instances can continue to be used; only operations that need to look up not-yet-loaded classes/resources may fail.

**"Setting a local loader variable = null guarantees unloading."** False. Classes/instances/registries/threads can keep the loader alive, and GC has no mandatory execution time.

**"Class<?> only holds a name, so caching any number of them does not affect the loader."** False. Caching class mirrors is a form of strong retention that must be controlled.

**"If there is a reference cycle, the JVM cannot reclaim it."** False. Reachability from GC roots is what determines normal garbage collection.

**"System.gc() is a reliable way to measure unloading."** False. It is a GC request/hint, not a barrier that guarantees class unloading.

**"If Metaspace grows, you probably just need to call close() again."** False. You need to find the root paths retaining the loader and examine actual lifecycle/GC behavior; close does not automatically reclaim metadata.

**"ServiceLoader.reload() replaces all implementation classes."** False. It only affects the provider cache of that ServiceLoader instance and does not replace the defining loader.

## 15. Self-Check Exercises

**Question 1.** Two instances `a` and `b` are created from the same runtime class. What does the expression `a.getClass() == b.getClass()` normally return?

**Answer:** `true`. They share the same class mirror of a single runtime definition.

**Question 2.** Two independent `URLClassLoader` instances both read `plugin.Widget.class`. Why is `typeA == typeB` `false`?

**Answer:** Because their defining loaders are different, so they are two distinct runtime classes even though their name and bytecode are identical.

**Question 3.** After `loader.close()`, can an already-loaded `instance.message()` still run?

**Answer:** It can, provided the code and dependencies required for the call are already available. Closing the loader does not delete existing instances or already-defined classes; you should not infer that every call succeeds after close if loading a new class is required.

**Question 4.** The host holds a `Map<String, Class<?>>` cache of types from a stopped plugin. Could this be the cause of a classloader leak?

**Answer:** Yes. Strong references to `Class<?>` can keep the plugin's class/loader definitions and metadata alive.

**Question 5.** A WeakReference to the loader is not cleared immediately after setting the local loader variable to null. Does that prove a leak?

**Answer:** No. The JVM may not have run GC yet, or other references may remain; you must inspect GC roots, lifecycle, and multiple cycles.

**Question 6.** Why is a cycle `loader → static object → plugin instance → runtime class` not automatically a leak?

**Answer:** If the entire group is no longer reachable from GC roots, the garbage collector can reclaim the cycle. Only when a path from a root keeps the group alive is it actual retained data.

**Question 7.** Why can a host thread pool retain a loader even after the manager has removed the plugin from its registry?

**Answer:** A worker thread may hold a TCCL/plugin-defined ThreadLocal value or a runnable/callback waiting in the queue; cleanup must occur on the appropriate thread and close pending tasks/registrations.

**Question 8.** To reload `plugin.Widget` with new bytecode, should you continue calling `loadClass` on the old loader?

**Answer:** Not if you want to replace an already-loaded definition. You typically need a new defining loader, a shared API boundary, and a clear lifecycle handoff.

**Question 9.** If `String.class.getClassLoader() == null`, is that because `String` has no runtime class?

**Answer:** No. `null` represents the bootstrap loader in the API; `String` is still a normal Java runtime class.

**Question 10.** What is the necessary condition for class unloading in the JVMS?

**Answer:** The defining class loader of that class must be reclaimable by the garbage collector. This does not guarantee that the VM has already unloaded the class at the moment the application calls close or sets a reference to null.

## 16. Plugin Design Checklist to Avoid Unintentionally Retaining Classes/Loaders

Keep shared API interfaces in a stable loader; isolate implementations by generation and ensure every resource has a cleanup owner. Remove plugin instances, callbacks, caches, TCCL/`ThreadLocal`, queued tasks, and open resources upon retirement.

Inspect `instance.getClass()` / `Class.getClassLoader()` to accurately determine the runtime class and defining loader. To verify reclamation, observe the retaining graph and class unload events within the limits of the JVM.

## 17. Conclusion and Official References

**A ClassLoader defines a runtime class; `Class<?>` represents that runtime class; an instance is an object belonging to that runtime class.** They are linked in identity and lifecycle, yet are not all destroyed simultaneously when `URLClassLoader.close()` is called.

The condition for the JVM to have an opportunity to unload a plugin's classes is that **the defining loader must be eligible for reclamation by the GC**. Class mirrors, instances, threads, TCCL, callbacks, reflection caches, and external registries can keep the loader reachable. Proper plugin design must **stop activity, unregister, close resources, and drop strong references** before expecting GC/unloading to occur; even then, no unloading deadline is guaranteed by the API.

References:

- JVMS 17 §5.3, *Creation of Classes and Interfaces* (runtime class identity): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVMS 17 §5.5, *Initialization*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- JVMS 17 §5.5/§5.6/§5.7 (including *Unloading*): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java SE 17 `Class` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `URLClassLoader` API, `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `WeakReference` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
