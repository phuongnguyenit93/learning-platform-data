# Conditions for a Class and Its Defining Loader to Be Collected

## 1. Why Does “An Object Is No Longer Used” Not Mean “The Class Has Been Unloaded”?

In Java, the lifecycles of an **instance**, a **runtime class**, and a **class loader object** are three distinct things. The garbage collector (GC) can reclaim an instance when it is no longer reachable, while the metadata of the class that created that instance still remains because the JVM still needs that class. For a class defined by a custom loader to become a candidate for **class unloading**, the condition relates to the class's **defining loader**.

According to the **Java Language Specification 17, `12.7`**:

- A Java implementation **may** unload classes/interfaces.
- A class/interface **may be unloaded if and only if its defining class loader can be reclaimed by the garbage collector**.
- Classes/interfaces loaded by the **bootstrap loader** are not unloaded.
- Unloading is a **memory optimization**, not an operation that a Java program can request and wait for at a guaranteed time.

This is a condition of **eligibility**, not a guarantee that GC will definitely occur. Even once all references to the custom loader are gone, the JVM may still delay or not perform class unloading during a particular run.

A mental model:

```text
Application still holds instance / Class<?> / loader / method handle
                         |
                         v
          Custom defining loader remains reachable
                         |
                         v
      Classes of the loader are not yet eligible for unloading

Application drops all strong roots to plugin + loader
                         |
                         v
         Defining loader can become unreachable
                         |
                         v
      Classes of the loader can become eligible for unloading
                         |
                         v
              JVM/GC may perform unloading
          (no guarantee of timing or frequency)
```

We must distinguish between the **necessary/sufficient condition for eligibility** and the **execution decision**: only when the defining loader can be reclaimed can the class be unloaded, yet the fact that the loader can be reclaimed **does not require** the VM to unload immediately.

## 2. What Is a Defining Loader, and How Does It Differ from an Initiating Loader?

The JVM identifies a runtime class by **binary name + defining class loader**. For example, the same `plugin.Task` can be defined by custom loaders A and B as two different classes:

```text
("plugin.Task", LoaderA) ≠ ("plugin.Task", LoaderB)
```

Where:

- **Defining loader**: the loader that directly defines the runtime class (typically via `defineClass`, or the corresponding VM mechanism).
- **Initiating loader**: the loader recorded by the VM as having initiated the loading of the class; it may simply delegate to its parent.
- **Parent loader**: the loader that a `ClassLoader` typically queries first under parent delegation.

For example, `child.loadClass("java.lang.String")` may return the exact `String.class` defined by the bootstrap loader. The child is where the code invokes the lookup, but it **does not become the defining loader** of `String`. Class unloading pertains to the **actual defining loader**, not simply a loader that returned `Class<?>`.

For an ordinary class:

```java
ClassLoader owner = someClass.getClassLoader();
```

`someClass` must be a validly obtained `Class<?>`. This method reveals the defining loader observable through the Java API; `null` represents the bootstrap loader for an ordinary class defined by bootstrap. Primitive/void/array types have their own rules, so do not infer that there is always a class file read by the bootstrap loader.

### Why Are a Loader’s Classes Not Unloaded While the Loader Is Still Alive?

Suppose loader L is still reachable. Later, code could ask L to load a class D that has not yet been loaded, and D in turn references a class C that previously existed. If the JVM had previously unloaded C while still keeping L, reloading C could introduce changes that are not transparent: static state, initialization side effects, native state, or `Class<?>` identity could differ. JLS `12.7` therefore ties a class's unloading condition to the ability to reclaim its **defining loader**.

Key implications:

- **You cannot request to unload an arbitrary single class within a still-live loader** by clearing a reference variable.
- **A long-lived loader** typically retains the set of classes it has defined for the lifetime of that loader.
- **To load a new version** of the same binary name, plugin systems typically create a **new defining loader**, rather than trying to redefine the class in the old loader.

## 3. What Does “Can Be Collected by GC” Mean?

A Java object becomes eligible for GC when it is no longer reachable from **GC roots** according to the VM's reachability mechanism, taking into account the special rules for references. A class loader is also an object. If there is a **strong reachability path** to the loader, or to an object/class that forces the loader to be kept alive, the loader cannot yet be collected.

Common sources that keep a loader alive:

| Source holding a reference | Example | Why does it affect class unloading? |
|---|---|---|
| Long-lived application variables/data structures | `static Map<String, ClassLoader>` | The host registry holds a strong reference to the loader |
| Instance of a class defined by the plugin loader | Plugin instance remaining in a host cache | A live object needs its corresponding runtime class |
| `Class<?>` token | `static Class<?> cached = pluginClass;` | Class metadata/token is being referenced by live code |
| Reflection handles | `Method`, `Constructor`, `Field`, method handle, or lookup bound to a plugin class | Can keep the declaring class/related types reachable |
| Thread context class loader (TCCL) | Worker thread calls `setContextClassLoader(pluginLoader)` and does not restore it | The live thread retains the loader |
| Thread-local state | `ThreadLocal` value containing a plugin instance | A long-lived worker continues to hold the object |
| Thread created by the plugin | `Runnable`/stack/callback or thread state still referencing the plugin | Code/objects belonging to the plugin are still in use |
| Executor/scheduled task | Plugin job/callback lambda still in the queue | The scheduled reference retains classes/instances/loader |
| Event listeners | Host listener registry containing a plugin listener | The host becomes a root to the plugin |
| JVM/native integrations | JNI global references, native handles still storing Java objects | References from the native side can retain the loader graph |
| Caches in shared libraries | Host singleton holding reflection metadata or a plugin proxy | Parent/shared code holds references to the child's classes |

**Not every reference is strong.** A `WeakReference` to a loader/class **does not by itself** keep its referent alive. `SoftReference` and `PhantomReference` have different semantics; they should not be treated as a mechanism for confirming immediate unloading. A `WeakReference` only helps **observe** GC, not command GC.

### Reachability Paths Are Often Indirect

It does not require a variable named `pluginLoader` to still be alive. The path retaining the loader can go through multiple objects:

```text
GC root
   |
   v
Host static Registry
   |
   v
Plugin listener instance
   |
   v
Runtime Class of the listener
   |
   v
Defining PluginClassLoader
```

In real systems, the path can be more complex due to reflection, class mirrors, method handles, class-loader data, and JVM structures. The key is the **entire graph**, not just the loader's variable name.

## 4. Having Instances Collected While the Class Remains Loaded Is Normal

Suppose:

```java
PluginTask task = new PluginTask();
task.run();
task = null;
```

This is an illustrative snippet, requiring a `PluginTask` class and appropriate `run()` handling. The line `task = null` only changes the value of **one variable**; it does not prove there are no other references to the object. Even if that instance is actually collected by the GC, the defining loader may still be retained by a registry, running code, other `Class<?>` tokens, other instances from the same loader, and so on.

Similarly, a class defined by a loader may have no instances at all and still not be unloaded, because its defining loader remains reachable.

| State | Well-founded inference |
|---|---|
| An object is collected by GC | That object is no longer reachable; this does **not** prove class unloading |
| No observable instances remain | **Insufficient**; `Class<?>`/loader/code/cache may still remain |
| A strong `Class<?>` reference is still alive | The class cannot disappear in a way that breaks semantics; typically keeps the defining loader alive |
| The defining loader is still strongly reachable | Classes defined by it are **not eligible** for unloading under the JLS |
| The defining loader can now be reclaimed | Classes defined by the loader **may** be eligible; the VM decides |
| `System.gc()` is called | Only requests GC; **does not guarantee** that GC has run, that unloading occurred, or that RAM was returned to the OS |

Do not use a `null` variable as proof of class unloading; identify the **strong GC roots** to the loader and classes.

## 5. Do Static Fields Always Cause a Class Loader Leak?

**No.** A static field belonging to a class defined by the plugin loader can hold objects within the same lifecycle; if this entire group is no longer reachable from GC roots, an internal reference cycle does not by itself create a leak. The dangerous case is when a **long-lived host or library** retains a plugin's class, instance, `Method`, or callback in a static registry/cache.

Example of a reference path causing retention: `host static map → plugin instance → runtime class → defining loader`. Dropping the local `pluginLoader` variable does not break this path. The article on static fields and reflection caches further analyzes `WeakHashMap`, `ClassValue`, and generation-based caches.

## 6. ClassLoader.close Is Not Class Unloading

`URLClassLoader.close()` primarily prevents reading new classes/resources from the source URLs managed by the loader and releases the corresponding file/JAR handles. **Already-loaded classes and existing objects can still continue to function**; whether the JVM unloads classes depends on the reclaimability of the defining loader and the GC's decision.

We must distinguish `close` at the I/O/resource level from eligibility at the runtime class level. The article distinguishing reference loss, `close()`, and unloading verifies these three actions with runnable experiments.

## 7. How Does Metaspace Relate to Class Unloading?

On **HotSpot JDK 17+**, class metadata is largely managed in Metaspace, distinct from the Java heap that holds object instances and `Class<?>` mirrors. If each reload creates an additional defining loader while the old loaders remain reachable, class metadata can accumulate and lead to Metaspace pressure.

Unloading, when performed by the JVM, can free/reuse the metadata of the old generation; there is no guarantee that `committed` memory or RSS will drop immediately. The **Method area** of the JVMS is a logical concept, whereas **Metaspace** is a HotSpot implementation detail. A dedicated article on Metaspace explains `used/committed/reserved`, NMT, and OOME investigation.

## 8. Java 17 Demo: Creating a Custom Defining Loader, Keeping Only WeakReference When Leaving Scope

The following demo loads a class **that exists only on the plugin's URL path**, obtains a `WeakReference` to the loader and `Class<?>`, and then exits the method to drop the strong local references. Whether the VM collects/unloads them in a specific run is **non-deterministic**.

### 8.1. Directory Structure

```text
src/
  plugin/
    demo/
      Entry.java
  host/
    UnloadEligibilityDemo.java
out/
  plugin/
  host/
```

File `src/plugin/demo/Entry.java`:

```java
package demo;

public final class Entry {
    public static String value() {
        return "plugin-alive";
    }
}
```

File `src/host/UnloadEligibilityDemo.java`:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadEligibilityDemo {
    private record Watch(
            WeakReference<ClassLoader> loader,
            WeakReference<Class<?>> type) {
    }

    private static Watch loadOnce() throws Exception {
        URL directory = Path.of("out/plugin").toUri().toURL();
        ClassLoader parent =
                UnloadEligibilityDemo.class.getClassLoader();

        URLClassLoader pluginLoader = new URLClassLoader(
                "plugin-v1", new URL[]{directory}, parent);

        try (pluginLoader) {
            Class<?> type = Class.forName(
                    "demo.Entry", true, pluginLoader);

            WeakReference<ClassLoader> loaderRef =
                    new WeakReference<>(pluginLoader);
            WeakReference<Class<?>> classRef =
                    new WeakReference<>(type);

            System.out.println("Defined by plugin loader: "
                    + (type.getClassLoader() == pluginLoader));

            System.out.println("Class lookup reused: "
                    + (pluginLoader.loadClass("demo.Entry") == type));

            System.out.println("Method: "
                    + type.getMethod("value").invoke(null));

            System.out.println("Weak refs populated before return: "
                    + (loaderRef.get() != null
                       && classRef.get() != null));

            // Ensure strong references remain live up to this point.
            Reference.reachabilityFence(type);
            Reference.reachabilityFence(pluginLoader);

            return new Watch(loaderRef, classRef);
        }
    }

    public static void main(String[] args) throws Exception {
        Watch watch = loadOnce();
        System.out.println("Returned from loader scope");

        // This is ONLY a GC request, not an unload command.
        System.gc();

        System.out.println("Loader weak ref cleared: "
                + (watch.loader().get() == null));
        System.out.println("Class weak ref cleared: "
                + (watch.type().get() == null));
    }
}
```

### 8.2. Compiling and Running

On Linux/macOS, from the directory containing `src`:

```bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/demo/Entry.java
javac -d out/host src/host/UnloadEligibilityDemo.java
java -cp out/host UnloadEligibilityDemo
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/plugin,out/host
javac -d out/plugin src/plugin/demo/Entry.java
javac -d out/host src/host/UnloadEligibilityDemo.java
java -cp out/host UnloadEligibilityDemo
```

**Very important:** only `out/host` is on the application classpath at runtime. Do not add `out/plugin` to `-cp`, because the parent loader could find `demo.Entry` before the custom `URLClassLoader`, causing the example to no longer demonstrate a class defined by pluginLoader.

### 8.3. Which Results Are Deterministic, and Which Are Not?

The first four lines of stdout:

```text
Defined by plugin loader: true
Class lookup reused: true
Method: plugin-alive
Weak refs populated before return: true
Returned from loader scope
```

**The last two lines depend on GC/JVM/timing** and look like:

```text
Loader weak ref cleared: false
Class weak ref cleared: false
```

or they may print `true` for one/both cases if the collector has reclaimed the corresponding referent before being read. **There is no single stdout guaranteed by the Java specification for the last two booleans**, even with `System.gc()`. This is the point of the example: measuring the phenomenon rather than assuming GC has fulfilled an unloading promise.

Analysis:

1. `Class.forName("demo.Entry", true, pluginLoader)` causes `pluginLoader` to find and define the class `demo.Entry` from `out/plugin` because the parent does not see that name.
2. `type.getClassLoader() == pluginLoader` being true proves the **defining loader**.
3. Calling `loadClass` afterward returns the same runtime `Class<?>`; it does not define it repeatedly.
4. `type.getMethod("value").invoke(null)` returns the string declared in the plugin code.
5. The weak references are created while the strong references are still alive; they do not by themselves keep the class/loader alive.
6. After `loadOnce()` returns, the strong local references in that method leave their required scope; only the weak references held by `Watch` remain **in the example's design**.
7. `try-with-resources` closes the URLClassLoader, but it does not trigger class unloading as a synchronous command.
8. `System.gc()` sends a GC request. If the loader weak reference is not yet cleared, that is **not yet** proof of a leak — the VM may not have reclaimed it at the time of inspection.

With a program that is too short, the VM may exit before observable class unloading takes place. Do not modify the code into an infinite loop calling `System.gc()` to “force” `true` to appear.

### One Distinction to Make When Observing a WeakReference

If `watch.loader().get() == null`, the loader weak referent has been processed by the collector as no longer strongly reachable according to `WeakReference` semantics. That is an **observation about the loader referent**; it does not by itself prove that a specific class-unload log event appeared at the same time, nor does it say how much RAM has been returned to the OS.

If the class token weak ref is not yet cleared during a single observation, you must not assert that the VM definitely has a leak. GC state and lifetime liveness are not deterministically controllable from Java user code.

## 9. Java 17 Example: A Thread’s TCCL Can Keep a Loader Alive

A long-lived worker thread may hold a `contextClassLoader` that still points to the plugin loader after the plugin stops. The path `GC root → live Thread → TCCL → plugin loader` can keep that generation alive.

In tasks that temporarily set the TCCL, restore the previous loader in `finally`; clean up `ThreadLocal` on **the exact worker thread** that stored the value and stop unfinished tasks. The article on Thread/ThreadLocal/TCCL implements an independent experiment on an executor to verify this retention.

## 10. Class Unloading Does Not Mean Hot Reloading a Class in the Same Loader

For example, plugin A has loaded `plugin.Entry` version 1 via loader L1. After deploying new code at the same file path, the application calls:

```java
Class<?> next = L1.loadClass("plugin.Entry");
```

In a properly designed loader, this call typically returns **the class already recorded** by L1, rather than reloading version 2 bytecode. A defining loader must not repeatedly define a class with the same binary name as two independent runtime classes within that same loader; a duplicate `defineClass` attempt can cause a `LinkageError`.

A proper reload cycle typically works as follows:

```text
Version 1:
  L1 -> plugin.Entry v1
  Host uses plugin v1
  Host stops plugin, drops references, and closes L1 resources
  L1 can become unreachable

Version 2:
  L2 (new loader) -> plugin.Entry v2
  Host uses plugin v2 via shared API
  L2 has its own runtime class identity

Class unloading of L1 (if any) does not need to occur
before L2 loads a class with the same binary name.
```

**You do not need to wait for L1 to be garbage-collected before creating L2.** Two runtime classes with the same binary name can coexist in parallel if their defining loaders differ and loading constraints/app contracts continue to be respected.

Conversely, if the host retains a `Class<?>` or an instance from L1 after switching to L2, the class metadata of both generations can persist long-term. This is a source of Metaspace growth during hot deployment.

## 11. Leak Sources That Are Easy to Miss

To check whether a defining loader can be reclaimed, trace from **GC roots** to the loader instead of only looking for a `loader` variable. Common reference paths include a host static `Map<String, Class<?>>` or `Map<String, Method>`, event listeners/callbacks, `ServiceLoader` caches, threads/TCCL/`ThreadLocal`, pending `CompletableFuture`/executor tasks, and JDBC/JMX/logging registries.

**There is no single universal cleanup command for every framework.** Remove the exact registration handles, cache entries, and thread state according to the owner of each resource. The articles on static caches, threads, and ServiceLoader separately explain each category, how to measure it, and failure scenarios.

## 12. Parent–Child Loaders: Reference Direction Determines Collectibility

A custom loader typically retains its parent:

```text
Child PluginLoader ---> Parent SharedApiLoader
```

This **does not require** the parent to retain the child. If there is only an arrow from the child to the parent, a live parent **does not by itself** keep the child alive.

However, a registry/layer/framework can create a reverse path:

```text
Host root
   |
   v
PluginManager
   |
   v
Child PluginLoader
   |
   v
SharedApiLoader (parent)
```

The path `Host → PluginManager → Child` is why the child is not GC'd, not the `Child → Parent` relationship by itself.

With JPMS `ModuleLayer`, the layer/loader objects have a reference graph that depends on how they are created and retained. If the host still retains the layer object, modules, service providers, or plugin objects, you should not expect `pluginLoader = null` alone to be enough. You must analyze the **actual references held by the implementation**, rather than asserting that every layer has the same retention structure.

## 13. Which Classes Should Not Be Expected to Unload in Normal Applications?

According to JLS `12.7`, **classes/interfaces defined by the bootstrap loader are not unloaded**. Classes such as `java.lang.String` in the standard JDK belong to this core runtime group.

For the default platform/application loader of a running JVM, the loader is typically a long-lived part of the runtime/application. Consequently, classes defined by them **are usually not targets for mid-run unloading**, unless special implementation-specific reachability conditions allow it.

This explains why the program:

```java
for (int i = 0; i < 1000; i++) {
    Object o = new SomeClass();
}
```

can GC thousands of instances while `SomeClass` remains loaded. `SomeClass` in an app loader that lives for the duration of the program is not a class that gets unloaded every time its instances are gone.

Applications that benefit most from class unloading:

- Application servers with frequent deploys/redeploys.
- Plugin managers that create a separate loader for each plugin/version.
- Runtimes that create/define dynamic proxies or generated classes under short-lived loaders.
- Code evaluation frameworks and embedded scripting/runtimes when they use dynamic defining loaders.

**This does not mean every application that loads many classes experiences unloading**: if all classes are defined by a loader that stays alive until the process exits, dropping a few instances does not make that loader eligible.

## 14. How to Observe Class Unloading on HotSpot JDK 17

On HotSpot, you can launch the JVM with `-Xlog:class+load=info,class+unload=info` to observe events. The appearance of an unload log entry is evidence that the JVM has unloaded a specific class; **the absence of logs in a single run** does not prove that the loader is leaked. `System.gc()` is a request, not evidence.

When investigating, combine event logs, class-loader counts, and heap retaining paths; compare across multiple reloads with the same workload. The article on observing unloading analyzes the experimental procedure, how to read counters, and the limitations.

## 15. A Safer Plugin Stop/Reload Procedure

A plugin generation only has a chance to retire properly when the host **blocks new tasks → drains/cancels in-flight work → unregisters listeners/registries → cleans up threads, TCCL, `ThreadLocal`, and caches → closes resources and the URL loader → drops strong references**.

Do not use a successful `close()` call or the number of `System.gc()` calls made as the confirmation condition for class unloading. Depending on the architecture, you must coordinate the shutdown sequence to prevent other tasks from concurrently loading classes from the loader being closed.

## 16. Common Misconceptions

| Misconception | Fact |
|---|---|
| “When no instances remain, the class is definitely unloaded.” | Class unloading depends on the **defining loader** being reclaimable, not just the instances. |
| “Setting `loader = null` is enough.” | Only drops one reference; a registry, TCCL, Class<?>, listener, etc., may still remain. |
| “`URLClassLoader.close()` will unload all classes immediately.” | `close` manages resources/lookups; class unloading is decided by the GC/VM. |
| “Calling `System.gc()` will return `true` in a WeakReference test.” | `System.gc()` is a request with no guarantee of timing or execution. |
| “Any static field in a plugin causes a leak.” | A strong path from a long-lived root is required; internal cycles do not by themselves pin the graph. |
| “Classes of the bootstrap loader can be unloaded if they have no instances.” | JLS `12.7` excludes classes/interfaces loaded by the bootstrap loader. |
| “An increase in Metaspace is sufficient proof of a leak.” | You need to examine used/committed/reserved, workload, and GC/loader stats. |
| “When a class unloads, OS RSS drops immediately byte for byte.” | The VM allocator may retain/reuse memory; RSS is not a direct measure of class unloading. |
| “If the parent loader is alive, all child loaders stay alive.” | The child typically retains the parent; the parent does not automatically retain the child. |
| “TCCL is unrelated to class unloading.” | A worker thread holding a loader via TCCL is a very common strong reference. |
| “Caching a Method does not retain the class/plugin.” | Reflection metadata can keep the declaring class and loader graph reachable. |
| “Giving loaders the same name allows reusing class identity.” | A loader's name does not determine runtime identity. |
| “Unloading is the same as hot replacement in the same loader.” | A new loader is typically needed; the old class can still exist until GC. |
| “Not seeing an unload log after a single run means a leak.” | Unloading is an optimization with no deadline; a short demo may exit before GC. |

## 17. Self-Check Exercises

**Question 1.** A `PluginTask` instance has been collected by GC, yet the host still keeps the `Class<?>` of `PluginTask` in a static map. Is the class eligible for unloading yet?

**Answer:** Not yet. The `Class<?>` still held by the host can continue keeping the class/defining loader reachable. Losing the instance alone is not enough.

**Question 2.** A class's defining loader can be reclaimed. Is the JVM required to unload the class immediately during the next GC?

**Answer:** No. JLS `12.7` permits class unloading as an optimization; being **eligible** does not guarantee GC/unloading timing.

**Question 3.** Are `URLClassLoader.close()` and `System.gc()` two equivalent ways to unload classes?

**Answer:** No. `close()` closes resources and affects lookups; `System.gc()` requests GC without guaranteeing execution; class unloading is a separate VM mechanism based on eligibility.

**Question 4.** If a child loader holds a reference to its parent loader, does a live parent automatically keep the child alive?

**Answer:** Not by default. A reference pointing from child to parent is not equivalent to one from parent to child. A strong reference path from a root to the child is required.

**Question 5.** A static field in a plugin holds another object that also belongs to the plugin. Does that by itself prevent GC of all the plugin's classes?

**Answer:** Not solely because of that internal relationship. If the entire graph has no remaining strong path from external roots, internal cycles can be handled by the collector.

**Question 6.** A worker thread still holds `Thread.currentThread().getContextClassLoader() == oldPluginLoader` after a redeploy. What can happen?

**Answer:** The live thread keeps the old loader reachable, making the old loader's classes ineligible for unloading; you should restore the TCCL on the right worker thread in `finally`.

**Question 7.** In the `UnloadEligibilityDemo` demo, why do the two values `Loader weak ref cleared` and `Class weak ref cleared` not have fixed stdout output?

**Answer:** They depend on GC/timing and reachability state at the moment of inspection; `System.gc()` does not promise synchronous collection/unloading.

**Question 8.** Can plugin v1 and v2 coexist with the same binary name `plugin.Entry`?

**Answer:** Yes, if the two defining loaders are different and the shared API/loading constraints align properly. There is no need to wait for the v1 class to unload before creating loader v2.

**Question 9.** Do a plugin's `Class<?>` token, `Method`, and `MethodHandle` sitting in a host cache relate to class unloading?

**Answer:** Yes. They can keep runtime classes/the loader graph reachable, so you must examine the lifecycle of reflection/call-site caches.

**Question 10.** Metaspace used decreases after class unloading, but OS RSS stays the same. Is there a contradiction?

**Answer:** No. The VM allocator can keep/commit memory for reuse; the metrics are not identical.

**Question 11.** A program does not have unload logging enabled, yet heap usage is seen increasing on each reload. What should be concluded?

**Answer:** You cannot yet conclude there is a classloader leak. You must inspect GC roots, loader count, class metadata, heap caches, a profiler, and logging/GC configuration; heap growth has many causes.

**Question 12.** Why does the JLS forbid unloading a class while its defining loader is still potentially reachable?

**Answer:** A live loader may later be asked to resolve/load classes. If a class were unloaded and then reloaded under the same loader, differences in static state, initialization side effects, class identity, or native state could allow the program to observe the unloading, violating the transparency requirement.

## 18. Summary and Official Documentation

**Keep five key points in mind:**

1. **Class unloading is only possible when the defining loader can be reclaimed**; this is an eligibility condition, not a promise that the JVM will unload immediately.
2. **Reachability depends on the entire GC-root graph**: instances, `Class<?>`, reflection metadata, TCCL, threads, registries, and caches are all worth checking.
3. **Closing resources ≠ unloading classes**: `URLClassLoader.close()` does not synchronously free defined runtime classes.
4. **Hot reload typically uses a new loader** for the same binary name; the old loader only gets a chance to be collected after all live references are cleaned up.
5. **Observe multiple signals instead of guessing**: weak refs, class unload logs, loader stats, and Metaspace numbers serve different roles; no single signal replaces GC root analysis.

**Official references:**

- [JLS 17 — `12.7` Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): defining loader condition and class unloading limits.
- [JVMS 17 — `5.3` Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining loader, initiating loader, and class identity.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findLoadedClass`, `defineClass`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, class/resource lookup, and URL/JAR resources.
- [Java SE 17 — WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak-reference reachability/clearing.
- [Java SE 17 — Reference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): `reachabilityFence` and reference operations.
- [Java SE 17 — java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog:class+unload` and `-Xnoclassgc` on HotSpot.
