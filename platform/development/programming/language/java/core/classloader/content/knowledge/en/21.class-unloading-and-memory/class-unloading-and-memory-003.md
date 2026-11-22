# Distinguishing Losing Object References, Closing a Loader, and Class Unloading

In a Java application with plugins, the following three phenomena are easily confused as one:

1. **Losing references to an object:** code no longer holds the object via any *strong reference* path. If the object is no longer kept alive according to reachability rules, the garbage collector (GC) **may** reclaim that object.
2. **Closing a URLClassLoader:** calling `loader.close()` to stop finding new classes/resources from the loader's URL search path and close the file/JAR handles opened by the loader. Closing **does not destroy already loaded objects or classes**.
3. **Class unloading:** the JVM **may** unload class-related metadata/state if the class's **defining class loader** is eligible for GC reclamation. This is JVM-dependent behavior; there is no Java SE command that guarantees "immediate unloading".

**There is no automatic implication `object = null` ⇒ `loader.close()` ⇒ `class unloaded`.** These are three concerns belonging to different layers of memory, resource, and runtime type management.

This article belongs to the **Class Unloading and Memory** group of Java core – classloader. The goal is to understand the actual conditions under which a class can unload, see firsthand that `close()` does not remove classes, use `WeakReference` and JVM tools properly, identify class loader leaks in plugin/hot-reload systems, and manage lifecycles in a safe order.

## 1. Quick comparison of the three actions

| Criterion | Object losing references | `URLClassLoader.close()` | Class unloading |
| --- | --- | --- | --- |
| Primary target | Instance on the heap, loader object, or another object | A specific `URLClassLoader` | Runtime definition/metadata of a class or interface |
| Nature | Reachability changes | Closes the class/resource sources and file handles managed by the loader | Class reclamation optimization decided by the JVM |
| Is it GC? | No: losing a reference differs from being reclaimed; GC may run later | No | Tied to the reclaimability of the defining loader |
| Happens immediately? | The reference can be dropped immediately; reclamation is not guaranteed | The call executes immediately and may throw an I/O exception | No guaranteed deadline |
| Prevents using old objects? | If the object still has another reference, it can still be used | Does not automatically invalidate already loaded objects/classes | The JVM must not unload a class while the loader is still potentially reachable |
| Closes plugin-specific resources? | No | Only resources within the URL loader's responsibility | Not a general cleanup API |
| Causes new classes to be loaded? | Not directly | After close, no new classes are found/defined from the loader's URL search path | Unloading is not class loading |
| Appropriate evidence | GC roots, heap dump, WeakReference with limitations | Observing close, handles, and lookups after close | Class unloading logs, classloader stats, GC analysis |

From this table, separate two common questions: **"Has the JAR been closed?"** and **"Have the plugin's classes been unloaded?"**. The answer to the first does not determine the second.

## 2. Losing object references: does not mean the object has been reclaimed

Java example:

```java
Object a = new Object();
Object b = a;
a = null;
System.out.println(b != null);
```

Stdout:

```text
true
```

`a = null` only removes **one** reference. Variable `b` still holds a reference to the original object, so we can still use that object.

Even when no strong references remain, the GC is not obligated to reclaim the object at a time you specify. The JVM may optimize liveness, classify references (strong/soft/weak/phantom), and decide when to perform GC. Do not equate the end of a variable's scope with an immediate heap deallocation event.

### Understanding reachability through GC roots

```text
GC roots
  |
  +-- Java thread stack -> local variable -> Object A
  |
  +-- Host static field -> registry -> Object B
  |
  +-- JNI global ref ---------------------> Object C

Object D ----> Object E
   ^                |
   +----------------+
   (no strong path from GC root)
```

- A, B, and C may still be kept alive due to reference paths originating from a root.
- D and E may be eligible for reclamation if there are genuinely no other paths keeping them alive.
- The cycle `D → E → D` by itself does **not** prove a memory leak: the GC can reclaim the entire unreachable cluster.
- An object dropped from a local variable but still present in a collection/static registry can still be reachable.

When diagnosing, the question is **"is there still a path from a root to the object?"**, not merely "has the line `variable = null` been seen yet?".

### Does `System.gc()` force reclamation?

No. `System.gc()` expresses a request for GC; the JVM has policies that decide whether and when to execute it. Do not write programs based on the assumption:

```java
plugin = null;
System.gc();
// Wrong to assume plugin classes are definitely unloaded from this point.
```

This is an **illustrative snippet**, assuming the `plugin` variable has already been declared. To stop a plugin properly, you must manage tasks, callbacks, resources, and the loader first; GC is not a lifecycle API.

## 3. `URLClassLoader.close()`: closes URL sources and handles, does not remove class definitions

In Java 17, `java.net.URLClassLoader` is a class loader that searches for classes/resources from URLs pointing to directories or JARs. It implements `Closeable` and has the method:

```java
public void close() throws IOException
```

The Java SE 17 API contract states:

- After close, the URL loader can no longer be used to load **new classes/resources defined by that loader itself from URL sources**.
- **Already loaded** classes/resources can still be accessed.
- Classes/resources defined by the **parent** can still be accessed via delegation.
- For `jar:`/`file:` URLs, the loader attempts to close the files/JARs it has opened.
- If one thread is loading a class **concurrently** while another thread calls close, the outcome of the in-progress load is **unspecified** according to the JavaDoc. The host must coordinate stop/await before closing.
- Close may throw `IOException`; closing an already closed loader has no additional effect.

What `close()` **does not do**: remove `Class<?>`, destroy instances, reset static fields, halt execution of already loaded methods, stop the plugin's executors/threads, close all sockets/DB connections, or request immediate GC/class unloading.

### Why do methods of an old class still run?

Because the bytecode and runtime metadata of a loaded class do not reside in an "open JAR stream" in a way where closing the file would invalidate the object. The JVM may already have loaded/linked the class, created the object, and resolved the method to be called.

However, **not every method of an old class is guaranteed to succeed after close**. The JVM may only resolve a dependent class when the method is invoked for the first time. If that dependency has not been loaded yet and only exists in the URLs of the closed loader, the program may encounter `NoClassDefFoundError` or an appropriate linkage error.

Distinguish:

- **Already loaded Class A:** can usually still be accessed after close.
- **Class B that only exists as a file on disk and has not been loaded:** the closed loader cannot newly locate B from that URL.
- **Class from parent:** can continue to be accessed after close if provided by the parent.
- **Object still referenced:** does not automatically turn into `null` or "destroyed".

## 4. Class unloading: JLS 17 conditions

Java Language Specification `12.7` specifies that a class/interface **may be unloaded if and only if its defining class loader may be reclaimed by the GC**. Classes/interfaces loaded by the **bootstrap loader** are not unloaded under this rule.

The phrase "**may**" is very important:

- **Eligibility is not mandatory.** The JVM may not have run GC yet, may not have performed class unloading yet, or may keep memory committed for reuse.
- **Closing the loader is not a sufficient condition.** A closed `URLClassLoader` can still be reachable from host objects, thread pools, or caches.
- **Losing instance references is not a sufficient condition.** The loader may still define many other classes and still be retained by the host.
- **Must not be unloaded while the defining loader is still potentially reachable.** If the VM unloaded a class while the loader was still alive, the class might have to be reloaded, breaking the consistency of static state, object identity, and native interactions.
- **There is no Java SE method `Class.unload()` or `loader.unloadClass(name)`** for an application to call to force unloading an individual class inside a living loader.

### The loader receiving the request is not necessarily the defining loader

```java
Class<?> stringType = pluginLoader.loadClass("java.lang.String");
System.out.println(stringType.getClassLoader() == null);
```

This is an **illustrative snippet**, assuming `pluginLoader` exists and the method handles checked exceptions. In standard Java SE, stdout is `true`: `String` is defined by the bootstrap loader even though the request originated at the plugin loader. Closing the plugin loader does not cause `String` to be unloaded.

For `plugin.Widget`, which is actually defined by `PluginLoader`, the VM evaluates the reclaimability of **PluginLoader** to determine whether the class can be unloaded.

**Type identity** in the JVM depends on **binary class name + defining class loader**. Therefore, two independent loaders can define two classes with the same name yet produce two different runtime types. Hot reloading with a new loader can cause v1 and v2 **to coexist** if the v1 loader is not yet eligible for reclamation.

## 5. Java 17+ example with verified stdout

This example intentionally **retains** references to the instance/class/loader even after close, in order to demonstrate that close does not remove old classes. Do not use this example to claim that class unloading has been measured.

### Project structure

```text
loader-lifetime-demo/
├── src/plugin/
│   ├── Alive.java
│   └── Later.java
├── LoaderLifetimeDemo.java
├── plugin-classes/       (plugin class output)
└── host-classes/         (host class output)
```

Create the two output directories if they do not exist and run the commands from `loader-lifetime-demo`. When running the host, **do not include `plugin-classes` in `-cp`**.

### Plugin class loaded before close

`src/plugin/Alive.java`:

```java
package plugin;

public final class Alive {
    private final int value = 41;

    public int plusOne() {
        return value + 1;
    }
}
```

`src/plugin/Later.java`:

```java
package plugin;

public final class Later {
    public static String text() {
        return "late";
    }
}
```

`Alive` will be looked up and instantiated before close. The `Later.class` file exists on disk, but it has not been requested to load yet.

### Host and URLClassLoader

`LoaderLifetimeDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.Method;

public class LoaderLifetimeDemo {
    public static void main(String[] args) throws Exception {
        URL directory = Path.of("plugin-classes").toUri().toURL();

        URLClassLoader loader = new URLClassLoader(
                new URL[]{directory},
                ClassLoader.getPlatformClassLoader());

        Class<?> type = loader.loadClass("plugin.Alive");
        Object instance = type.getConstructor().newInstance();
        Method method = type.getMethod("plusOne");

        System.out.println("plugin defining loader="
                + (type.getClassLoader() == loader));
        System.out.println("before close=" + method.invoke(instance));

        loader.close();

        System.out.println("after close=" + method.invoke(instance));
        System.out.println("cached class="
                + (loader.loadClass("plugin.Alive") == type));

        try {
            loader.loadClass("plugin.Later");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("unloaded? no; new class not found");
        }

        System.out.println("instance still alive="
                + (instance.getClass() == type));
    }
}
```

The parent here is the platform class loader: it can help locate core platform classes, but it does not contain `plugin.Alive`/`plugin.Later`. As a result, `Alive` is defined by the child URL loader itself.

### Compile/run (JDK 17+)

```bash
javac --release 17 -d plugin-classes src/plugin/Alive.java src/plugin/Later.java
javac --release 17 -d host-classes LoaderLifetimeDemo.java
java -cp host-classes LoaderLifetimeDemo
```

Exact stdout verified from compiling/running:

```text
plugin defining loader=true
before close=42
after close=42
cached class=true
unloaded? no; new class not found
instance still alive=true
```

### Output line explanations

1. `plugin defining loader=true`: the plugin class was actually created/defined by the URL loader.
2. `before close=42`: the instance works before close.
3. `after close=42`: the existing instance and method still run after close.
4. `cached class=true`: the loader looks up the already loaded class again; it does not load a new definition from the URL.
5. `unloaded? no; new class not found`: class `Later` was never loaded, so after close there is no URL source to locate a new class; the parent does not have that class either. This is **not evidence** that `Alive` has been unloaded.
6. `instance still alive=true`: the object and `Class<?>` are still present, while the variables `loader`, `type`, `instance`, and `method` are also still referenced in code.

**Conclusion of this limited test:** close is not equivalent to unload. The test **neither forces nor proves** a class unloading event.

## 6. How Object, Class<?>, and ClassLoader link to one another

An object instance has its own runtime class; `instance.getClass()` returns the `Class<?>` mirror of that definition; `Class.getClassLoader()` indicates the **defining loader** (which may be `null` for bootstrap). If the host still retains a plugin instance or mirror, the JVM must preserve the corresponding runtime type.

Example retention path: `host registry → instance → class → plugin defining loader`. However, **losing a single reference** to an instance is not enough to prove there are no remaining paths from GC roots; the article on the `Class`–instance–loader relationship goes deeper into the graph and type identity.

## 7. WeakReference: observe, do not force unloading

`WeakReference<ClassLoader>` **does not keep the loader alive via a strong reference**. It can help observe whether the loader is still kept alive or the referent has been cleared; however, it **does not prove** unloading from a single run.

This Java 17 illustrative program can compile if `plugin-classes/plugin/Alive.class` was already created in the demo above:

```java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class UnloadProbe {
    static WeakReference<ClassLoader> runAndRelease(URL[] urls)
            throws Exception {
        URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader());

        try {
            Class<?> type = loader.loadClass("plugin.Alive");
            Object instance = type.getConstructor().newInstance();
            type.getMethod("plusOne").invoke(instance);
        } finally {
            loader.close();
        }

        return new WeakReference<>(loader);
    }

    public static void main(String[] args) throws Exception {
        URL[] urls = {
            Path.of("plugin-classes").toUri().toURL()
        };

        WeakReference<ClassLoader> ref = runAndRelease(urls);
        System.gc(); // Only a GC request/hint.

        System.out.println("loader cleared? " + (ref.get() == null));
    }
}
```

Compile/run:

```bash
javac --release 17 -d host-classes UnloadProbe.java
java -cp host-classes UnloadProbe
```

Output is **not guaranteed**: it may print `loader cleared? true` or `loader cleared? false`.

Why?

- `System.gc()` does not guarantee that it will run and collect the loader by the time of the check.
- The loader may still be retained by a reference in the JVM, another task/registry, or may not yet be eligible for reclamation.
- JIT and runtime liveness can affect when local references are considered still needed.
- Even when the weak referent has been cleared, that is **not a direct measurement** that all bytes of class metadata/metaspace or all OS handles have been returned.

### Proper interpretation

| Observation | What can be concluded | What cannot be asserted |
| --- | --- | --- |
| `ref.get() != null` | The loader has not been cleared at the time of reading | Not necessarily a leak; GC may simply not have processed it yet |
| `ref.get() == null` | The weak referent was cleared via reference processing or by the code itself | Does not assert that all metaspace/native memory has been returned to the OS |
| No class unload log | The corresponding unload event has not been observed | Does not prove close was done incorrectly |
| Heap decreases after GC | Heap objects changed according to the metric being measured | Does not prove that the class loader/class metadata has unloaded |

To verify class unloading, combine **loader liveness**, **heap retaining-path analysis**, and **VM class unloading events/stats** rather than relying solely on WeakReference.

## 8. Heap, metaspace, and JAR handles are not the same resource

| Resource type | Example | Primary handling mechanism |
| --- | --- | --- |
| **Java heap** | Instances, arrays, `URLClassLoader` object, collections/caches | GC when objects are no longer kept alive |
| **Class metadata/metaspace** | Metadata of classes defined by the loader, on HotSpot | JVM class unloading and metaspace management |
| **JAR/file handles** | `plugin.jar` opened by `URLClassLoader` | `URLClassLoader.close()` per contract |
| **Plugin network/database/files** | `Socket`, DB connection, `FileInputStream` opened by the plugin itself | The plugin must close them according to each resource's API |
| **Threads/executors** | Workers, schedulers, task queues | Cancel/stop/shutdown/await according to lifecycle |
| **JNI/native resources** | Native allocations, JNI global refs, library state | JNI/native subsystem cleanup; do not rely on automatic class unloading |
| **JIT/code cache** | Compiled native instructions and VM caches | Managed by the VM, not equivalent to `Runtime.freeMemory()` |

Metaspace is a common term/mechanism of **HotSpot**; Java SE does not mandate every JVM to use the same memory organization as HotSpot.

Even if class metadata is unloaded, process RSS or committed/reserved memory may **not drop immediately**, as the VM may keep memory for reuse. Therefore:

**Increases/decreases in `Runtime.getRuntime().freeMemory()` are not a direct measurement of class unloading.** It relates to the heap and does not replace classloader statistics, GC logs, and inspecting retaining paths.

## 9. How to measure class unloading on Java 17+

With compatible HotSpot/OpenJDK builds, you can enable unified logging:

```bash
java -Xlog:class+load=info,class+unload=info -cp host-classes LoaderLifetimeDemo
```

Explanation:

- `class+load` records class-loading events.
- `class+unload` records events when the JVM actually unloads a class.
- A short demo may **not print unload events** because references are still alive and GC has not run.
- Do not use "saw class+load" as evidence for "already unloaded".
- Specific tags/logging capabilities and formats depend on the JVM build.

If you have a long-running JVM server, the `jcmd` tool can help:

```bash
jcmd <PID> VM.classloader_stats
```

This is **illustrative syntax**: replace `<PID>` with the actual process ID; the tool and command are only available if the JDK/runtime build supports them and you have the corresponding attach permissions.

You should combine:

1. **Classloader statistics:** number of loaders/classes, metadata/metaspace usage before and after multiple deployments.
2. **Heap dump:** find the **retaining path from a GC root to PluginClassLoader** or to an instance/class.
3. **Thread inspection:** which loader is held by thread pools, schedulers, TCCL, or ThreadLocal.
4. **JFR (if appropriate):** class-loading/unloading events with appropriate recording settings.
5. **OS file handles:** verify which component still has a file/JAR open.
6. **GC logs/metrics:** understand reclamation timing and distinguish class unloading from object collection.

Do not let the observation test itself create a leak: a static debug list holding `Class<?>` or loaders will prevent old classes from being easily reclaimed.

## 10. Losing references in a plugin host: common leak sources

Common reference sources are host static registries/caches, listeners/callbacks, reflection metadata, worker threads (TCCL and `ThreadLocal`), pending jobs, `ServiceLoader`, and framework registrations. Each source must be removed at its actual owner; calling `close()` does not clean them up automatically.

Investigate the `path to GC roots` of the **old loader generation** and cross-check it against the plugin lifecycle. The articles on caches, threads, and listeners in this chapter provide in-depth inspection techniques.

## 11. Proper lifecycle to give a plugin a chance to unload

**Quiesce → Stop/clean up → Close URL loader → Release references → Observe.** Reject new tasks, handle in-flight work, and unregister callbacks before closing the loader; clean up `ThreadLocal` on the right threads, close private resources, and then drop registries/caches of the old generation.

This sequence helps make the loader **eligible for reclamation** once the entire retaining graph is severed. There is no promise that the JVM will unload it within a specific GC cycle.

## 12. Hot reload: create a new loader, do not "reset the old loader"

Replacing `.class` files or JARs on disk does not update runtime definitions already loaded by the old loader. To use new bytecode for the same binary name, applications typically use a **new defining loader**, switch traffic to the new generation, and then retire the old generation.

Existing instances remain bound to the old runtime class; they do not automatically change type simply because the loader or source file was closed/replaced.

## 13. Table of common scenarios and misconceptions

| Scenario | Correct conclusion |
| --- | --- |
| `object = null`, heap has not decreased | References may still exist or GC may not have run yet; does not mean a loader leak |
| `loader.close()` succeeds, plugin method still runs | Follows contract; close does not automatically unload objects/classes |
| After close, `loadClass` for an unloaded class fails | The loader closed its URL sources for new classes; does **not** prove old classes unloaded |
| JAR remains locked despite close | Handles may be held by another component or close encountered an I/O error |
| `System.gc()` runs, WeakReference is still non-null | Insufficient to conclude; check strong retaining paths and GC timing |
| WeakReference cleared but RSS stays high | The JVM may retain committed native/metaspace memory for reuse |
| Metaspace grows across hundreds of reloads | Suspect a classloader leak or unloading not keeping up; measure loaders/classes/roots |
| Plugin object is gone but `Class<?>` remains in host cache | `Class<?>` can still keep the defining loader alive |
| Old loader and new loader contain classes with the same name | Different runtime types if defined by two different loaders |
| Duplicate module/plugin interface causes `ClassCastException` | Share the API via a parent loader; do not expect close/GC to fix it |
| Java object is reclaimed but socket is not closed in time | Manage external resources with explicit close/stop |
| No unloading log in a short demo | Not required to happen; absence of event ≠ close failure |

## 14. Q&A and self-check exercises

**Q1.** `Object a = new Object(); Object b = a; a = null;` Is the original object eligible for GC yet?

*Answer:* While `b` remains a live strong reference, it cannot be said that the object has lost all references. `a = null` only removes one reference path.

**Q2.** Why does `method.invoke(instance)` after `loader.close()` still succeed in the demo?

*Answer:* The class, method, and instance were already loaded/created; close does not destroy them or delete runtime bytecode.

**Q3.** If `loader.loadClass("plugin.Later")` throws `ClassNotFoundException` after close, can we conclude that `plugin.Alive` has unloaded?

*Answer:* No. `Later` is a class that was never loaded, whereas `Alive` is still retained and in use. Failing to locate a new class only proves that URL lookup has been closed.

**Q4.** Does `loader = null; System.gc();` guarantee class unloading?

*Answer:* No. Registries, `Class<?>`, instances, TCCL, ThreadLocal, or other native references may still retain the loader. GC/unloading also has no deadline.

**Q5.** A static map in a class defined by the host system loader is holding `plugin.Entry.class`. How do you fix this?

*Answer:* Remove the relevant entry from the host static cache/registry when stopping the deployment, then verify there are no remaining retaining references to the old loader.

**Q6.** Why can't the JVM unload a class while its defining loader is still potentially reachable?

*Answer:* The loader could be used to resolve/load classes referencing the old class. Arbitrary unloading would create the risk of class reloading altering identity, static state, and side effects, violating the JLS transparency requirement.

**Q7.** Is `String.class` unloaded when closing a child plugin loader?

*Answer:* No. `String` is normally defined by the bootstrap loader; the JLS does not allow unloading bootstrap-defined classes.

**Q8.** Does a cleared WeakReference to a loader confirm that all metaspace has been returned to the OS?

*Answer:* No. This is only a signal that the referent has been cleared; class unloading/committed memory must be measured using separate JVM diagnostics.

**Q9.** Why should `Runtime.freeMemory()` not be used to conclude class unloading?

*Answer:* It reflects heap status and does not directly measure HotSpot metaspace or unload events.

**Q10.** A plugin JAR needs to be deleted/updated on Windows. Is having closed the URLClassLoader enough?

*Answer:* Close is an important step to release file/JAR handles opened by the loader; however, other streams/handles may also be holding the file. Stop work, close owned resources, and investigate OS locks if it still cannot be deleted.

**Q11.** A thread pool worker keeps TCCL = oldPluginLoader after undeploy. What is the consequence?

*Answer:* It can keep the old loader alive, causing a classloader leak and making another task's service discovery use the wrong namespace. It must be restored in the worker using `finally`.

**Q12.** After reload, the same `plugin.Widget` has two versions and a `ClassCastException` occurs. Why?

*Answer:* Class identity consists of binary name + defining loader. Two loaders define two distinct types. Use shared interfaces/DTOs in the parent so the host and plugin communicate via a common contract.

## 15. Checklist when preparing to unload a plugin

Before retiring, identify the defining loader and ensure shared APIs continue using a consistent runtime type; reject new work, drain tasks, and unregister listeners and caches; clean up TCCL/`ThreadLocal` on the appropriate threads; close I/O handles and the URL loader; and drop strong roots holding the old generation.

Finally, monitor logs/heap retaining paths across multiple cycles to verify unloading conditions. Do not turn the return of `System.gc()` into a pass condition.

## Conclusion

**Losing object references** is a matter of **reachability**; **`URLClassLoader.close()`** is a matter of **closing the loader's class/resource search path and file handles**; **class unloading** is a matter of **the JVM being able to reclaim class definitions when the defining loader becomes eligible for GC**. There is no mandatory implication arrow from one event to the next.

In plugin/hot-reload systems, the sustainable approach is **stop → unregister and cleanup threads/resources → restore context → close loader → release strong references → observe GC/unloading if needed**. Do not take a single `System.gc()` call, a local variable assigned `null`, or a closed JAR as proof that class metadata disappears immediately.

**Java SE 17 standard documentation:**

- [`URLClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, already loaded classes/resources, and file/JAR handles.
- [JLS 17 `12.7` — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): rules on the defining loader being eligible for GC reclamation.
- [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, and parent delegation.
- [`WeakReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability and clearing.
- [`System` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `gc()` and the limitations of requesting GC.
- [Java 17 `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnosing running JVMs when supported by the environment.
