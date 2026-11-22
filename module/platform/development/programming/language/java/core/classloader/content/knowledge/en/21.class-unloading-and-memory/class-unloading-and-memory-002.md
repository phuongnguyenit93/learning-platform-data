# Why Is There No Arbitrary Unload Operation for a Normal Class in Java?

In Java, you can request loading a class using `ClassLoader.loadClass(...)`, `Class.forName(...)`, or another runtime mechanism. However, Java **does not provide a symmetric API like `Class.unload()`, `ClassLoader.unloadClass("p.Name")`, or `System.unloadClass(...)` for an application to immediately remove a normal class already defined by the JVM**.

This is not an accidental omission. A runtime class is tied to **type identity, live instances, running methods, stack frames, linked field/method references, static state, reflection, and the class loader**. Removing a single arbitrary class at the application's discretion could break the consistency of a running program.

Instead, **class unloading is a JVM-dependent mechanism linked to whether the garbage collector (GC) can reclaim the defining class loader**. For normal classes/interfaces, the rule in the **Java Language Specification (JLS) `12.7`** is: a class/interface **can only be unloaded when its defining loader can be reclaimed by the GC**. However, eligibility for reclamation is not a promise that the JVM will unload it at a deterministic time. Class unloading is a memory-management optimization, and a valid program **must not depend on whether a class is unloaded**.

> Keep in mind upfront: **stop using the plugin → detach references → the loader can become collectible → the JVM may unload classes**. None of the arrows in this chain means “immediately and certainly”.

## 1. Distinguishing load, link, initialize, stop, close, and unload

The following terms are often used interchangeably:

| Concept | Practical meaning | Does it remove the runtime class? |
|---|---|---|
| **Loading** | The JVM finds/creates a `Class<?>` by binary name and loader | No |
| **Linking** | Verification, preparation, and possibly resolution according to the JVM | No |
| **Initialization** | Runs `<clinit>` logic: static initializers/field initializers when needed | No |
| **Stop plugin** | Business workflow to stop accepting requests, close services, and unregister handlers | Not automatically |
| **`URLClassLoader.close()`** | Releases resources/JAR/file handles managed by this loader within the scope of the API | **Does not** unload loaded classes |
| **`System.gc()`** | Hints to the JVM to perform GC; does not guarantee immediate execution, does not target specific classes | **Not** an unload command |
| **Class unloading** | The JVM frees class definitions/metadata according to its conditions and strategy | Yes, when the JVM decides |
| **`Instrumentation.redefineClasses`** | Replaces certain parts of a definition within instrumentation limits | **Not** removing a class |
| **`ClassLoader#defineClass` in a new loader** | Creates a runtime class belonging to a different loader namespace | Does not remove the old class |

**Key point:** `ClassLoader.close()` is a **loading-source** lifecycle operation, whereas **class unloading** is a **runtime class definition** management operation. They may be part of the same plugin removal plan, but they are **not synonymous**.

## 2. Why Can't You Simply “Remove a Class Name from the JVM”?

A class in the JVM is not just a `.class` file or a string name. For normal classes/interfaces, runtime identity is determined by:

```text
(binary name, defining class loader)
```

Example:

```text
Loader-A defines app.Plugin
  -> runtime type (app.Plugin, Loader-A)

Loader-B defines app.Plugin
  -> runtime type (app.Plugin, Loader-B)
```

These two runtime types are **different**, even though their binary names match and their bytecode may be identical. An object of version A does not automatically turn into an object of version B.

A defined class may be associated with:

1. **Instances on the heap**: The JVM must know the corresponding type, layout, virtual method dispatch, and metadata.
2. **Static fields**: one copy of static state per runtime class; values may reference objects, services, and resources.
3. **Currently executing methods**: the call stack may currently contain frames belonging to that class.
4. **References in other bytecode**: linked fields/methods/type descriptors, resolution, and loader constraints.
5. **Reflection**: `Class<?>`, `Method`, `Field`, `Constructor`, and `MethodHandle` objects may be bound to the type.
6. **Inheritance and interfaces**: subclasses/implementations may have already been loaded and be using that class.
7. **Runtime services**: proxies, serialization, JNI, exception handling, or framework caches may hold related metadata.

If there were an `unloadClass("app.Plugin")` API that returned success immediately, the JVM would have to handle what happens to live objects, running frames, and other code calling methods of this class afterward. Java avoids providing an action with such poorly defined semantics.

### Reasoning Example

```java
Object plugin = createPlugin();
Class<?> type = plugin.getClass();
Method method = type.getMethod("run");
```

This is an **illustrative snippet**, not standalone runnable yet because `createPlugin()` and the `run` method need to be defined.

If right after that you “delete the class by name”, `plugin` is still a Java object, `type` still represents the runtime type, and `method` can still be used to invoke code. A JVM cannot assume those references disappear on their own just because the application wants to replace a JAR.

**It is not that the JVM is completely unable to reclaim metadata**, but rather that the JVM must ensure class unloading occurs when **safe reclamation conditions** are satisfied, instead of at an arbitrary moment decided by a single line of application code.

## 3. Class Unloading Conditions According to JLS `12.7`

**JLS `12.7` — Unloading of Classes and Interfaces** specifies:

- An implementation **may** unload classes/interfaces.
- A class/interface **may only** be unloaded if **its defining class loader can be reclaimed by the garbage collector**.
- Classes/interfaces loaded by the **bootstrap loader** **cannot be unloaded** according to the JLS rule.
- Unloading is an **optimization**, and a program must not depend on unloading decisions.

Mental model:

```text
    Class p.A is defined by loader L
                   |
                   v
    Are there still references keeping L uncollectible?
                   |
          +--------+--------+
          |                 |
         Yes                No
          |                 |
          v                 v
    Not eligible      L may become eligible
    for unloading     for GC reclamation
                            |
                            v
                 The JVM may unload classes
                 defined by L, when appropriate
```

This is a **necessary-condition relationship**, not an exact GC algorithm. Do not assume that “no remaining local variable named `loader`” automatically proves L is no longer reachable: other references may still exist via objects/classes/threads/registries.

### “Defining loader” Differs from “the loader that called loadClass”

```java
Class<?> type = child.loadClass("java.lang.String");
```

A child loader may simply **delegate** up to its parent/bootstrap loader. For `String`, the defining loader on a typical JDK is the bootstrap loader; `type.getClassLoader()` returns `null`. Discarding the child loader **does not make `String` eligible for unloading**.

If you want to manage a plugin's lifecycle, you must identify **the loader that actually defines the plugin's private classes**, not just the loader that the plugin manager uses to call `loadClass`.

### Unloading Is the VM's Prerogative, Not a Mandatory Requirement

Even when a class loader has become unreachable and eligible for reclamation, the application still **cannot dictate the timing** of when GC runs or when class metadata is freed. Behavior that appears to succeed on one JDK/GC configuration may differ on another JDK/GC or workload. Therefore, business logic such as updating plugins, deleting files, and cleaning up registries must rely on an **application-controlled lifecycle**, not on “GC has already unloaded class X”.

## 4. Why Can Already-Loaded Classes Still Be Used After Closing URLClassLoader?

`URLClassLoader.close()` manages resources and the ability to locate new classes/resources from the loader's URLs. Classes that have already been defined **are not removed**, already-created instances still carry the old runtime type, and already-linked methods can continue to run as long as valid references remain.

That is why `close()` is not equivalent to `unloadClass`. The runnable example in section 5 verifies this, while also loading a new version using a different defining loader.

## 5. Java 17+ Demo: close Does Not Unload, a New Loader Creates a New Type

The demo has two source classes, in two separate output directories:

```text
class-unload-demo/
├── src/
│   ├── plugin/
│   │   └── Greeting.java
│   └── app/
│       └── UnloadDemo.java
└── out/
    ├── plugin/
    └── app/
```

**Key point:** The runtime classpath **contains only `out/app`**. The plugin class `plugin.Greeting` is defined from `out/plugin` by two different `URLClassLoader` instances.

### 5.1. File src/plugin/Greeting.java

```java
package plugin;

public final class Greeting {
    private static int visits;

    static {
        System.out.println("Plugin initialized");
    }

    public static String greet() {
        return "hello " + (++visits);
    }
}
```

`visits` is a **static field** belonging to the runtime class. Each defining loader will have an independent copy of `plugin.Greeting` and an independent `visits` value.

### 5.2. File src/app/UnloadDemo.java

```java
package app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadDemo {
    public static void main(String[] args) throws Exception {
        URL url = Path.of(args[0]).toUri().toURL();
        ClassLoader parent = UnloadDemo.class.getClassLoader();

        try (URLClassLoader first =
                new URLClassLoader(new URL[] {url}, parent)) {

            Class<?> original =
                    first.loadClass("plugin.Greeting");

            System.out.println("Same class in one loader: "
                    + (original ==
                       first.loadClass("plugin.Greeting")));

            System.out.println("First call: "
                    + original.getMethod("greet").invoke(null));

            // Release loader resources; the existing class remains usable.
            first.close();

            System.out.println("After close: "
                    + original.getMethod("greet").invoke(null));

            try (URLClassLoader second = new URLClassLoader(
                    new URL[] {url}, parent)) {

                Class<?> replacement =
                        second.loadClass("plugin.Greeting");

                System.out.println("Different classes: "
                        + (original != replacement));

                System.out.println("First loader identity: "
                        + (original.getClassLoader() == first));

                System.out.println("Second call: "
                        + replacement.getMethod("greet").invoke(null));
            }
        }
    }
}
```

### 5.3. Compile/Run

On Bash (Linux/macOS/Git Bash), from the `class-unload-demo` directory:

```bash
mkdir -p out/plugin out/app

javac --release 17 -d out/plugin src/plugin/Greeting.java
javac --release 17 -d out/app src/app/UnloadDemo.java

java -cp out/app app.UnloadDemo out/plugin
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out/plugin, out/app | Out-Null
javac --release 17 -d out/plugin src/plugin/Greeting.java
javac --release 17 -d out/app src/app/UnloadDemo.java
java -cp out/app app.UnloadDemo out/plugin
```

**Output compiled/run and verified** with `javac --release 17` on OpenJDK 24:

```text
Same class in one loader: true
Plugin initialized
First call: hello 1
After close: hello 2
Different classes: true
First loader identity: true
Plugin initialized
Second call: hello 1
```

### 5.4. Line-by-Line Explanation

1. **Same class in one loader: true** — calling `first.loadClass` again with the same binary name returns the same `Class<?>` already loaded by that loader; it does not define two copies with the same name in a single loader.
2. **Plugin initialized** — invoking the static method `greet` requires initialization of the runtime class defined by loader `first`.
3. **First call: hello 1** — the static field `visits` of the class in loader `first` increments from 0 to 1.
4. **After close: hello 2** — `first.close()` has been called, yet `original` is still a usable `Class<?>`, and the loaded method still runs; the static field continues from 1.
5. **Different classes: true** — loader `second` defines a **different** runtime class `plugin.Greeting` from `original`, even though the bytecode and binary name are identical.
6. **First loader identity: true** — `original.getClassLoader()` is still `first`; it is not changed to `second` by `close`.
7. **Plugin initialized** again — the class in `second` is a new runtime class, with its own initialization.
8. **Second call: hello 1** — the static field of the `second` version starts from 0, independent of the old version.

**What the example does not prove:** that `first` was garbage-collected or that `plugin.Greeting` V1 was unloaded. In fact, in the code, the `original` variable still holds V1's `Class<?>`, so expecting the JVM to remove V1 right after `close` is unreasonable. After `main` finishes, the demo process exits; that is JVM process termination, **not an empirical test of class unloading within the same JVM**.

### 5.5. Why Is Keeping `original` Important?

The experiment keeps a `Class<?>` object still reachable while also showing that the loaded class/loader is not “deleted” by `close`. Calling `System.gc()` while still holding the reference does not turn this object invalid either.

You should not try to force a test with `original = null` and then assert that the class will definitely unload; setting a local variable to `null` **does not prove** that all reference paths in the program/JVM have disappeared, and the GC is not forced to run at the exact time you want.

## 6. Class Unloading Is Not the Same as Object Garbage Collection

**Instance GC** reclaims objects on the Java heap when they are no longer reachable according to the collector's rules. **Class unloading** involves runtime classes/metadata and the defining loader; **closing JAR handles** belongs to the I/O resource lifecycle.

An instance can be reclaimed while the class remains usable; a loader can close its JAR without yet being eligible for reclamation. Do not infer unloading solely from `instance = null`, `close()`, or a single GC.

## 7. Things That Commonly Keep a Class Loader Alive

Host static caches, listener/event buses, reflection `Class<?>`/`Method` caches, thread pools, `ThreadLocal`, context class loaders, scheduled jobs, and provider caches are typical groups of references.

For example: `host registry → plugin callback → plugin Class<?> → defining loader`. You need to remove the reference at the actual **owner** instead of merely calling `loader = null`. Dedicated articles on caches, threads, and ServiceLoader explore each retention mechanism and how to handle it in depth.

## 8. Proper Plugin Lifecycle

To stop using a plugin in a controlled way, block new requests first; then complete/cancel in-flight work, unregister callbacks, clean up state on worker threads, close resources owned by the plugin, and finally close the URL loader if present.

Hot reload creates a new generation/defining loader for the same binary name when new code is needed. The JVM itself decides when to run GC/class unloading after the old generation is no longer reachable. This is an application lifecycle, **not an API that forces removal of a defined class**.

## 9. Reloading Classes Is Different from Unloading Classes

Three operations must be distinguished:

### A. Creating a New Loader for a New Plugin Version

```text
Plugin V1: (com.acme.Widget, LoaderV1)
Plugin V2: (com.acme.Widget, LoaderV2)
```

They can coexist in the JVM. The host selects the generation for new work and lets the old generation finish; afterward, it removes V1 references. This is the common approach for hot-reload based on classloader isolation.

### B. Instrumentation redefine/retransform

`java.lang.instrument.Instrumentation` has APIs:

```java
redefineClasses(ClassDefinition... definitions)
retransformClasses(Class<?>... classes)
```

These are **illustrative API method names**, not a standalone runnable program snippet. Instrumentation has strict limitations on redefinition/retransformation depending on the JDK/VM and the agent's capabilities.

These APIs **do not mean unloading a runtime class**. Class identity generally remains tied to the existing runtime class; instances and static state are not automatically deleted/reset just because you replace bytecode within the permitted limits. They are suited to agents/profilers/certain forms of hot code replace, **not** turning the application into a place that has `Class.unload()`.

### C. Restarting the Process/JVM

Terminating the JVM process frees the entire address space and runtime state through the operating system. This is a **deployment/lifecycle** solution distinct from “unloading a single specific class while the JVM stays running”.

An application that requires guarantees that all untrusted code is removed and system resources are isolated can use a **separate plugin process** and then terminate/restart the process. A ClassLoader alone is neither a sandbox nor a mechanism that guarantees clearing all side effects of code.

## 10. Why Can't the Same Loader Call defineClass a Second Time to “Update”?

For a defining loader `L` and binary name `p.Widget`, the runtime class identity is `(p.Widget, L)`. Once successfully defined, the JVM does not let you call `defineClass` again to create **another runtime class** with the same name in L simply by invoking it again with new bytes.

Attempting to define a duplicate name can lead to a `LinkageError` (duplicate class definition). Reading bytecode from a new JAR does not automatically replace the old class: the loader may return the already-recorded class via `findLoadedClass`/`loadClass`.

Pseudocode example:

```text
Loader L:
  defineClass("p.Widget", bytesV1) -> Class<p.Widget,V1>

  defineClass("p.Widget", bytesV2)
      -> duplicate definition error, DOES NOT replace V1
```

The way to switch **class generations** is a different loader (or using Instrumentation according to its contract if you genuinely need to replace body/behavior within its limits). Do not try to work around this by bypassing the cache/`findLoadedClass`: the JVM still manages identity and linked types.

### Why Should a Plugin Namespace Be Placed Under Its Own Loader?

Putting all plugins into a shared loader makes sharing classes easier, but updating a single implementation individually usually forces managing a new namespace for **the entire group**. With a per-plugin loader, you can replace the definitions of one plugin's private classes without changing the class identities of the remaining plugins, provided the shared API resides in the parent and lifecycle references are cleaned up.

In return, private types from V1/V2 cannot be cast to one another, so the host needs to communicate via **shared SPI/DTO**. An object belonging to `LoaderV1` does not automatically become an instance of the `LoaderV2` type even with the same class name.

## 11. Observing Class Unloading with Tools — Do Not Treat Logs as a Contract

On HotSpot, `-Xlog:class+unload=info` can record JVM class unloading events. An event is valuable as **empirical evidence** for that specific run, while not seeing an event does not prove a leak. Do not use `System.gc()` as a test step with a mandatory expected outcome.

The final article of the chapter presents a workflow for observing class count, loader generations, logs, and retaining paths along with the exact limitations of each signal.

## 12. Do Not Confuse Class Unloading with Other Kinds of “Unloading”

| Commonly confused operation | What does it do? | What does it NOT do? |
|---|---|---|
| Deleting `.class` or plugin JARs on disk | Removes bytes from the source for new loads | Does not remove already-defined runtime classes |
| `URLClassLoader.close()` | Closes resource/JAR handles according to its contract | Does not destroy already-loaded Class/instances |
| `ClassLoader.loadClass` on a new loader | Can create a different runtime class identity | Does not unload the old class |
| `System.gc()` | Requests/hints that GC be considered | Does not target a class for unloading |
| `WeakReference.clear()` | Clears the reference held inside the WeakReference object | Does not remove the actual class/loader |
| Clearing an application cache | Drops one strong reference path | Does not guarantee all other reference paths disappear |
| `ServiceLoader.reload()` | Clears the provider cache of **that ServiceLoader object** | Does not redefine/unload provider classes |
| `Instrumentation.redefineClasses` | Replaces supported definitions within VM limits | Does not turn existing objects into a different class |
| Clearing a `ModuleLayer` reference | Drops a reference that may retain the module/loader graph | Does not force classes in the layer to unload |
| Terminating the JVM process | Terminates the entire runtime process | Not an API that selects a single class inside a still-running runtime |

A JAR file may have already been deleted while code continues to run because the JVM has already defined the classes in memory. Conversely, closing the JAR handle may be necessary to update the file on some operating systems, but that is a **file-resource lifetime** issue, not evidence of class unloading.

## 13. Common Misleading Scenarios

### “I Set loader = null; Why Is the Class Still There?”

`loader = null` only clears one reference. A live `Class<?>` or plugin instance, a running thread, the TCCL, or a host registry may still retain the related loader/type. It is also possible that the JVM has not yet performed GC or class unloading even though the loader is eligible. Inspect the retaining paths.

### “I Already Closed the JAR; Why Can Methods Still Be Called?”

Because `URLClassLoader.close()` does not invalidate already-loaded classes; the JavaDoc explicitly states that existing classes/resources remain accessible. The demo in section 5 proves this.

### “V2 Was Deployed, Yet Users Are Still Running V1”

The host may still hold a reference to the V1 plugin object or cache V1's factory/`Class<?>`. The existence of loader V2 does not automatically replace all application references. You need a versioned service registry/atomic handoff/stopping old requests by design.

### “Metaspace Grows Every Time a Plugin Reloads”

Each loader generation defines new classes and has its own metadata/caches. If old loaders remain referenced, memory may continue to grow. Investigate classloader statistics, JFR, heap retention, TCCL, threads, caches, and native services. **Metaspace growth does not by itself prove a single type of leak**; normal activity or collector policy also affects observations.

### “There Are No Instances Left, So the Class Can Surely Be Unloaded”

Not sufficient: Java allows code to still hold `Class<?>`, reflection handles, or other runtime references. On the other hand, GC roots must be analyzed as a graph; not every class that has static fields lives forever.

### “There Is a Class Unloading Log, So the Plugin Has Stopped Cleanly”

Not necessarily. Class unloading speaks to runtime class metadata; it does not confirm that all external side effects (files, network, DB state, process-level properties, business data) have been rolled back. Host lifecycle cleanup must still be designed independently.

## 14. When Is Class Unloading Actually Useful?

Class unloading helps the VM free metadata for classes that are no longer needed when an application performs dynamic loading:

- **Application servers/containers** with many deploy/undeploy cycles.
- **Plugin systems** that create separate loaders for plugin versions.
- **Dynamic code generation** (proxy classes, scripting engines, compilers) with scoped loaders.
- **Hot reload/devtools** that create multiple class loader generations.
- **Long-running services** where avoiding retaining old class loaders helps control memory.

These systems generally do not call “unload class X”; they **end the usage scope** and remove references so that GC can reclaim a loader generation.

### Why Do Other Kinds of Classes Exist, Such as Hidden Classes?

Java also has **`MethodHandles.Lookup#defineHiddenClass`** for code-generated classes with semantics different from ordinary named classes. Hidden classes have their own discoverability/lifetime rules, such as options like `NESTMATE` and `STRONG`.

This is an advanced mechanism serving dynamic languages/frameworks; **it does not introduce an arbitrary unload API for normal classes**. Do not take hidden class behavior as evidence that `ClassLoader.unloadClass("p.Normal")` exists.

## 15. Decision Process When You Want to “Remove a Class” from a System

If the requirement is to **stop running code**:
- Stop dispatching, unregister services, and wait for/cancel active tasks according to the contract.
- There is no need to wait for class unloading before considering business execution stopped.

If the requirement is to **load a new version**:
- Use a new loader generation or an appropriate instrumentation mechanism with clear limits.
- Keep the shared API stable in the parent, and switch the registry to V2 in a controlled manner.

If the requirement is to **release resources/JAR handles**:
- Call `close` on supported loaders/resources and perform proper lifecycle cleanup.
- Do not claim that doing so automatically removes classes.

If the requirement is to **reduce memory/metaspace**:
- Identify where old loader generations are still reachable from, and clean up the strong references properly.
- Use logs/JFR/heap analysis to verify; do not try to “force unload” with GC loops.

If the requirement is to **isolate untrusted code**:
- A class loader is not enough; consider process isolation, OS permissions, container sandboxes, and IPC contracts.

## 16. Checklist Before Retiring a Plugin Loader

- [ ] The host has stopped creating **new work** related to the old plugin.
- [ ] Active requests/tasks are completed or safely canceled.
- [ ] Plugin `stop/close` has been called in the right order.
- [ ] Schedulers/executors/threads managed by the plugin have been stopped.
- [ ] The TCCL of threads is restored to an appropriate loader.
- [ ] `ThreadLocal`/event listeners/global registries are cleaned up.
- [ ] JDBC/MBeans/logging/caches/ServiceLoader provider references are unregistered/cleared when needed.
- [ ] Open files, sockets, and JAR handles/resources are closed.
- [ ] The host does not retain old `Class<?>`/`Method`/`MethodHandle`/plugin objects beyond scope.
- [ ] The new loader uses shared SPI/DTO contracts with the right runtime type identity.
- [ ] Per-generation metrics/logging are in place to find abnormal retention.
- [ ] “Unloading has occurred” is not used as a mandatory condition for request routing.

## 17. Self-Check Questions

**1. Does Java have `Class.unload()` or `ClassLoader.unloadClass(String)` for ordinary classes?** No such public API exists.

**2. What necessary condition does the JLS specify for class unloading?** The class's defining loader must be reclaimable by the GC.

**3. If a loader is collectible, is the JVM required to unload the class immediately?** No. Unloading is an optimization dependent on the implementation/GC.

**4. Why doesn't `URLClassLoader.close()` unload classes?** Because `close()` closes the loading source and file/resource handles; already-loaded classes still exist and remain usable while valid.

**5. Does creating a new loader with the same binary name update the old class?** No. It creates a new runtime type with a different defining loader.

**6. Is a static field shared between two copies of `plugin.Greeting` defined by two different loaders?** No; they are two runtime classes with separate static state.

**7. When no plugin instances remain, is the loader guaranteed to be GC'd?** Not necessarily; there may still be `Class<?>`, active threads, host registries, or other references.

**8. Does a static field inside a plugin automatically cause the loader to leak forever?** Not always; what matters is whether the graph is still reachable from external GC roots.

**9. Does `System.gc()` guarantee class unloading?** No. It is not an unload API and does not let the program choose a class to unload.

**10. Does `ServiceLoader.reload()` unload provider classes?** No. It clears the provider cache of the ServiceLoader object; the class lifecycle remains separate.

**11. Do plugin classes need to finish unloading before users can be switched to V2?** No. The host can route new requests to V2 after handling the handoff according to contract; V1 may remain in memory during cleanup/GC.

**12. What is a better way to debug loader retention than guessing?** Observe classloader statistics/JFR/heap retaining paths, TCCL, and registries; inspect actual references.

## 18. Official Sources

- **Java Language Specification (Java SE 17), `12.7` — Unloading of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- **Java Virtual Machine Specification (Java SE 17), `5.5/`5.3 — Initialization, defining/initiating loaders and runtime class identity:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **Java SE 17 API, `ClassLoader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API, `URLClassLoader.close()`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **Java SE 17 API, `System.gc()`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- **Java SE 17 API, `Instrumentation`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- **Java SE 17, `java` command, `-Xlog:class+unload`:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html

**Remember:** There is no **arbitrary unload operation for a normal class** because a runtime class must remain consistent with objects, executing code, class identity, and the loader graph. **The application controls the usage lifecycle; the JVM/GC controls unloading.** To hot-reload or reduce memory, manage loader generations, clean up references, and observe class unloading as an optimization — do not make it a business requirement.
