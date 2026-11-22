# URLClassLoader.close() Does Not Mean Unloading Already-Loaded Classes

`URLClassLoader` can locate and define classes from directories or JARs according to a set of URLs. Because this class loader implements `Closeable`, we can call `close()` or use `try-with-resources`. However, **closing a loader is not a command to "remove all classes from the JVM"**, does not destroy already-created objects, does not reset static fields, and does not force the garbage collector to reclaim class metadata.

The Java SE 17 documentation clearly specifies: after `URLClassLoader.close()`, the loader can no longer be used to **define new classes from its own URL sources**, but **classes and resources that have already been loaded remain accessible**, and classes/resources defined by its parent remain accessible via delegation. On the other hand, **class unloading** is a JVM memory-management mechanism that can occur only when the defining class loader becomes eligible for garbage collection; even when eligible, the JVM **does not guarantee immediate unloading**.

This article belongs to the **URLClassLoader** topic in Java core – classloader. The focus is on distinguishing **close / stopping new loads / class unloading / releasing an entire plugin**, observing Java 17+ behavior with a runnable example, understanding the references that keep a class loader alive, and designing a plugin lifecycle that avoids JAR locking errors, memory leaks, or dependency access failures after closing.

## 1. Three Actions Commonly Conflated

| Action | What actually happens? | What is NOT guaranteed? |
| --- | --- | --- |
| **`URLClassLoader.close()`** | Closes resources opened by the URL loader, especially applicable files/JARs; stops finding/defining **new classes and resources from the loader's own URLs** | Does not unload already-defined classes; does not destroy objects, threads, static state, or any handles opened by the plugin itself |
| **Dropping Java references to the loader and classes/plugin** | May make the loader and the classes it defined eligible for GC | Does not guarantee that GC runs, that the loader is reclaimed, or that classes are unloaded immediately |
| **Class unloading** | The JVM may reclaim metadata/class-related state of a class when its defining loader can be reclaimed by GC | Not a Java API called directly by class name; cannot arbitrarily request unloading within a still-live loader |

**One sentence to remember:** `close()` **ends the activity of finding resources from the loader's URLs and releases handles owned by the loader**; whereas **unloading** depends on the liveness state of the entire object/Class/ClassLoader graph and the JVM's decisions.

`URLClassLoader` is a concrete `ClassLoader`. Not every subclass of `ClassLoader` has a `close()` method or the same resource-closing mechanism as `URLClassLoader`.

## 2. What Exactly Does the Java 17 JavaDoc Say About `close()`?

API signature:

```java
public void close() throws IOException
```

Key guarantees and caveats in Java SE 17:

1. **No more new loading from sources defined by the loader.** New classes/resources that the loader would have to find on its own in the URL search path will not be provided after close.
2. **Already-loaded classes/resources remain accessible.** In particular, `Class<?>`, resolved methods, already-created objects, and static state do not "disappear" on their own because of close.
3. **Parent delegation still works.** A class defined by the bootstrap/platform/system parent is not invalidated when a child URL loader closes.
4. **Closes files opened via the loader's URLs.** For applicable `jar:` or `file:` URLs, the API attempts to close the files/JARs that the loader opened while searching for classes/resources.
5. **If another thread is loading a class concurrently with close, the result of the in-progress load is undefined.** Do not use `close()` as a safe synchronization mechanism to "cancel" ongoing class loading.
6. **Repeatedly closing has no additional effect.** Calling close on an already-closed loader is not an error merely for calling it again.
7. **May throw `IOException`.** The loader attempts to close the files it opened; if multiple I/O errors occur, additional exceptions are attached as suppressed exceptions. Unchecked exceptions/errors are not guaranteed to be caught.

From the rules above, the following statement is **false**:

> "Once `loader.close()` has been called, certainly no method belonging to a plugin class can run anymore."

Closing the loader **does not** stop the CPU from executing bytecode that has already been loaded and linked. Nor does it broadcast a forced "destroy all instances" event. As long as external code still holds a `Class<?>` or a plugin object, the old code can still run.

Also avoid overclaiming the opposite: **that every method of an old class will continue to run fine after close**. A loaded method may **need to resolve/load an additional dependent class for the first time** when invoked later. If that dependency exists only in the closed loader's URLs, the call may fail even though the original method/class itself was loaded before close.

## 3. Verified Java 17+ Example: Old Classes Remain Usable

The following example runs standalone with JDK 17+ and intentionally separates the host's output from the plugin's output. Do not add the plugin directory to the host's classpath.

### 3.1 Structure

```text
url-close-demo/
├── source/
│   └── plugin/
│       ├── Hello.java
│       └── NotYet.java
├── CloseDemo.java
├── plugins/       (separate .class output for the plugin)
└── host/          (output for the host)
```

Create the directories if they do not already exist. `plugins` must not be included in `-cp` when running `CloseDemo`, because we want the plugin classes to be discoverable only through the dedicated `URLClassLoader`.

### 3.2 Two Plugin Classes

File `source/plugin/Hello.java`:

```java
package plugin;

public class Hello {
    public String message() {
        return "still alive";
    }
}
```

File `source/plugin/NotYet.java`:

```java
package plugin;

public class NotYet {
    public static String value() {
        return "new";
    }
}
```

`Hello` will be loaded **before** closing. `NotYet` still has its `.class` file present in the same URL directory, but is **not requested to be loaded before close**.

### 3.3 Host Creates and Then Closes URLClassLoader

File `CloseDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.Method;

public class CloseDemo {
    public static void main(String[] args) throws Exception {
        URL[] urls = {
            Path.of("plugins").toUri().toURL()
        };

        URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader());

        Class<?> cls = loader.loadClass("plugin.Hello");
        Object obj = cls.getDeclaredConstructor().newInstance();
        Method message = cls.getMethod("message");

        System.out.println("before close: " + message.invoke(obj));

        loader.close();

        System.out.println("after close: " + message.invoke(obj));
        System.out.println("same cached class: "
                + (loader.loadClass("plugin.Hello") == cls));
        System.out.println("parent class: "
                + (loader.loadClass("java.lang.String") == String.class));

        try {
            loader.loadClass("plugin.NotYet");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("new plugin class: not found");
        }
    }
}
```

Because `CloseDemo` only uses reflection to access `plugin.Hello`, it **does not need to import/compile a direct dependency** on the plugin class. `ClassLoader.getPlatformClassLoader()` serves as the parent so JDK classes can still be delegated to the platform, without providing `plugin.Hello`.

### 3.4 Compiling and Running

From the `url-close-demo` directory, create the `plugins` and `host` output directories and run:

```bash
javac --release 17 -d plugins source/plugin/Hello.java source/plugin/NotYet.java
javac --release 17 -d host CloseDemo.java
java -cp host CloseDemo
```

The example above has been verified with `javac --release 17` and run on a compatible JVM. Stdout:

```text
before close: still alive
after close: still alive
same cached class: true
parent class: true
new plugin class: not found
```

### 3.5 Line-by-Line Explanation

- **`before close: still alive`:** `loader.loadClass("plugin.Hello")` finds the class file in `plugins`, then the host creates an instance and invokes the method via reflection.
- **`after close: still alive`:** the object, `Class<?>`, and `Method` still hold valid references. `close()` does not destroy them; the already-ready method still runs.
- **`same cached class: true`:** with the default `loadClass` mechanism, a class whose loading was initiated by the loader can be found again via `findLoadedClass`, even when the URL search path has been closed. Do not interpret close as clearing the class cache.
- **`parent class: true`:** the closed loader can still ask its parent to find `java.lang.String`, which is a platform class not defined by the plugin loader.
- **`new plugin class: not found`:** `plugin.NotYet.class` exists in the `plugins` directory, but the URL loader is already closed and no longer searches/defines new classes from that URL. Since the parent does not have this class either, we get `ClassNotFoundException`.

The example intentionally calls `loader.loadClass("plugin.Hello")` after close to prove that an already-loaded class remains accessible. **Do not build an architecture around continuing to use a closed loader as a normal loader**; treat it as having finished its job of loading new classes.

### 3.6 Why Is This Not Enough to Conclude the Class Was Unloaded?

In the example, `loader`, `cls`, `obj`, and `message` still have live references in the method. In particular, the program itself is continuing to use them. The class `plugin.Hello` is not unloaded merely because of close, and **there is no GC check of any kind** in the example. It illustrates **the ability to keep using old classes**, not the lifetime of metadata after the program ends.

## 4. A Subtle Point: An Already-Loaded Class May Still Need an Unloaded Class

The JVM does not necessarily resolve all symbolic references of a class at the same time. Resolution can be performed on demand. Consider an example **illustrating the mechanism**, not a standalone runnable file:

```java
package plugin;

public class Entry {
    public void execute() {
        Dependency.run();
    }
}
```

If `Entry` was loaded before close but `Dependency` has not yet been found/resolved by the loader, the first call to `execute()` after close may need to load `plugin.Dependency`. At that point, the loader no longer being able to read the URL path can lead to a linking error such as `NoClassDefFoundError` or `ClassNotFoundException` reported in the specific context. The JVM has the right to resolve earlier, so **you should not rely on a single guaranteed timing for all dependencies**.

Therefore, these two statements are different:

- **Already-loaded classes can still be used after close.** Guaranteed by the JavaDoc at the level of existing classes/resources.
- **Every execution path of every already-loaded class will always succeed after close.** Not guaranteed, because there may still be lazy loading/resolution, resource lookups, or business logic using files/JARs later on.

A practical example: a plugin class is loaded early, but only on handling the 100th request does it instantiate an optional formatter/codec. If the URL loader is closed right after bootstrap, the optional feature can break in the future even though startup tests did not catch it.

## 5. Loading, Initialization, Close, and Unloading Are Four Different Moments

To avoid confusion in the lifecycle diagram, separate them into distinct events:

```text
Create URLClassLoader
       |
       v
Find Class<?> from URL / parent
       |
       v
Loading + Linking (on demand)
       |
       v
Initialization <clinit> (when a JVM operation requires it)
       |
       v
Objects / methods / static state are used
       |
       +------------> URLClassLoader.close()
       |                    |
       |                    +--> close the loader's handles
       |                    +--> stop new lookups from the loader's URLs
       |                    +--> does NOT automatically unload classes
       |
       v
Stop tasks, close own resources, drop references retaining the plugin
       |
       v
Defining loader may become unreachable
       |
       v
GC may reclaim the loader and unload the classes it defined
       (timing is not guaranteed by the JVM)
```

**Loading** creates/brings the class definition into the JVM. **Initialization** runs static initializers when required by the JVM. **`close()`** closes the sources/handles owned by the loader. **Unloading** is a memory-management optimization when GC conditions are met. There is no relationship of "call close ⇒ immediately afterward static fields revert to `null` or `0`".

`java.lang.Class` and its defining loader have a runtime identity relationship: the same binary name **defined independently** by two different loaders produces two distinct types, with separate static state. Therefore, when you need to reload a new version, the standard approach is to **create a new loader**, rather than expecting the old `URLClassLoader` instance to "forget" the classes it has loaded.

## 6. Class Unloading Conditions in JLS 17

Java Language Specification §12.7 states that the JVM **may** unload a class or interface if and only if **its defining class loader may be reclaimed by the garbage collector**. Classes loaded by the bootstrap loader are not eligible for unloading under this rule.

Practical interpretation:

- If a class defined by the plugin loader still has live object instances or a retained `Class<?>`, the metadata/class-loader graph is usually not yet eligible for reclamation.
- If the app/container still holds a **strong reference to the plugin loader**, directly or indirectly, the loader cannot be reclaimed by GC, so the classes it defined cannot be unloaded either.
- If **all relevant strong reference paths** have been released, the classes and loader *may* become eligible, but the JVM is not forced to run GC or unload on application demand.
- Assigning `null` to a local variable is not enough to prove the graph has no remaining references; class objects, instances, method handles, threads, stacks, and native roots may still retain it.
- Classes defined by the **bootstrap** loader such as `java.lang.String` are not unloaded under JLS 12.7, regardless of how many times a child URL loader has been closed.

**True:** "After stopping the plugin and dropping all related strong references, the JVM may unload classes defined by the plugin loader."

**False:** "`loader = null; System.gc();` will definitely free all plugin classes immediately."

`System.gc()` is a request/hint to the runtime subject to GC policy; it carries no contract guaranteeing immediate class unloading or unloading within a fixed time window. Nor should you build business logic around a `WeakReference` check turning `null` at an arbitrary point in time.

## 7. What Keeps a Class Loader Alive After Close?

A loader can be kept alive through many paths. Common reference-retaining sources in plugin/app-server applications:

| Retaining source | Example | How to handle when stopping the plugin |
| --- | --- | --- |
| **Plugin instance** | Host cache holding `Object plugin` or an interface implementation | Remove from registry/cache; do not keep objects alive beyond the lifecycle |
| **`Class<?>` / reflection** | `Map<String, Class<?>>`, `Method`, `Constructor`, `MethodHandle` | Clear metadata/caches tied to the old deployment |
| **Thread context class loader** | Thread pool worker still has `setContextClassLoader(pluginLoader)` | Restore the previous TCCL in a `finally` block inside the task; check long-lived workers |
| **Threads created by the plugin** | Thread running plugin code and holding runnable/task classes | Request stop, interrupt/await in a controlled manner before close; avoid unbounded threads |
| **`ThreadLocal` / inheritable context** | Thread pool holding values defined by the plugin | Remove at the point of creation; consider task scope and thread reuse |
| **Static registry in the host** | Event listener, callback, scheduler, SPI cache | Cancel registration, `remove` listeners and cache entries |
| **ServiceLoader/provider cache** | Host cache holding provider instances/classes | Clean up cache/scope per deployment; recreate an appropriate context |
| **Shutdown hooks** | Plugin hook thread/runnable registered with the runtime | Unregister the hook when permitted and before shutdown has begun |
| **JMX/MBean, logging, JDBC, driver registry** | Provider or listener still registered in a long-lived subsystem | Unregister/close according to the subsystem API |
| **Native/JNI refs, task stacks** | Code still running or a bridge holding objects/classes | Stop tasks safely and release refs managed by native code |

One easily overlooked point: **close and unload do not resolve each other in reverse order**. Stopping a plugin safely usually requires **blocking new requests**, completing/canceling running work, closing resources owned by the plugin, **then closing the loader**, and finally dropping the last references. If a thread is still loading a class during `close()`, the JavaDoc states that the result of that concurrent load is undefined.

### Why Do Static Fields Inside the Plugin Also Need Attention?

A static field belonging to a plugin class can hold other objects, including threads/tasks/registries. However, a reference cycle **solely within a cluster of unreachable objects** does not by itself prevent garbage collection: standard GCs can reclaim cycles not referenced from any root. The real danger lies in **a reference path from a GC root or a long-lived object outside the plugin** to the plugin's objects/classes/loader.

Therefore, do not conclude "there is a static cache in the plugin ⇒ guaranteed permanent leak". Analyze **whether there is a strong reference path from a root to the loader**.

## 8. Does WeakReference Prove the Loader Has Been Unloaded?

You can use `WeakReference<ClassLoader>` to roughly observe whether a loader is still held by strong references or has had a chance to be reclaimed. However, you must understand its limits:

```java
java.lang.ref.WeakReference<ClassLoader> reference =
        new java.lang.ref.WeakReference<>(loader);

// Only after stopping the plugin, removing all strong references,
// and exiting the scope that still holds the loader:
loader = null;

System.gc(); // Does not guarantee GC runs or reclaims the loader immediately.
System.out.println(reference.get());
```

This is an **illustrative snippet**, not a standalone unloading verification program. `reference.get()` may still be non-null because the loader is reachable or simply because GC has not occurred yet. If `get() == null`, you have evidence that the weak referent loader was cleared; that is **not an API guarantee of when all class metadata is reclaimed**, nor does it replace metaspace measurement tools and class-unload logs.

A common testing mistake is keeping `Class<?> klass` or a plugin instance in a local/static variable to "check if it has unloaded". Those very references can keep the class/loader alive. A more reliable test typically creates and uses the loader in a **separate method scope**, returns only the weak reference outside, and cleans up all registries/TCCLs/resources according to the lifecycle.

During real-world investigation, you can observe:

```bash
java -Xlog:class+unload=info -cp host CloseDemo
```

The logging syntax above is for HotSpot JVMs supporting unified logging, and output depends on actual GC events. **Not seeing unload logs does not prove `close()` is broken**; the program may not yet be eligible, no GC/unloading may have occurred, or it may have exited too early.

You can combine `jcmd` and heap dumps/classloader statistics depending on the JDK/runtime to find **retaining paths**. Do not use `-Xlog:class+load=info` as proof that classes were unloaded: `load` and `unload` are two different event types.

## 9. Does `close()` Release JAR Locks?

A practical reason to use `URLClassLoader.close()` is to **release the JAR/file handles the loader opened**. On Windows, a file whose handle is held by a process can cause replacing, deleting, or updating the JAR to fail; closing `URLClassLoader` according to its contract is an important step when undeploying/redeploying a plugin.

However, the following statements are **not** equivalent:

- **The URL loader has been closed:** the loader attempts to close the files/JARs belonging to resources it opened itself, per contract.
- **Every stream, socket, DB connection, and thread of the plugin is guaranteed to be closed:** no. The plugin may have opened them itself outside `URLClassLoader`.
- **Overwriting/deleting the JAR on every OS is guaranteed to succeed:** no. A handle may be held by another component, or `close()` itself may throw `IOException`.
- **All resources can continue to be read after close:** not guaranteed. Already-loaded/accessed resources may remain available, but streams tracked by the loader may be closed during close; a closed URL source no longer serves new resources in the normal way.

If plugin code calls `URLClassLoader.getResourceAsStream()`, the URL loader can track the corresponding streams to close them when the loader is closed. If the plugin directly opens `FileInputStream`, `Socket`, `JarFile`, or uses a JNI library, those resources **do not automatically belong to `URLClassLoader`'s close lifecycle**.

**Resource management rule:** whichever code opens a resource should **close it under its own contract**, unless API documentation explicitly states that ownership and responsibility are transferred.

### Handling `IOException` on Close

A safe example when a task genuinely only needs to load/read classes from the loader within one scope:

```java
URL[] urls = {Path.of("plugins").toUri().toURL()};

try (URLClassLoader loader = new URLClassLoader(
        urls, ClassLoader.getPlatformClassLoader())) {
    // Only perform operations that need classes and resources from the URLs.
    Class<?> type = loader.loadClass("plugin.Hello");
    System.out.println(type.getName());
} // loader.close() is called; IOException may be propagated.
```

This is an **illustrative snippet** and must be placed in a method with `throws Exception` or handle checked exceptions. `try-with-resources` can also record resource-closing errors as suppressed exceptions if the body already threw another exception.

Be careful: using `try-with-resources` for a plugin loader **right inside a factory** and then returning the plugin instance for the host to use for hours is a risky design. Once the factory returns, the loader is already closed; the old object may work on some code paths, but lazy dependency loading or resource lookups later on may fail.

## 10. Proper Plugin Lifecycle: Stop First, Close Next, Release References Last

A plugin host can use this conceptual lifecycle:

```text
CREATED
   |
   v
LOADING/STARTING
   |
   v
RUNNING
   |
   +-- stop accepting new work
   |
   v
STOPPING
   |
   +-- finish/cancel running tasks
   +-- clear temporary thread context loader
   +-- unregister listeners / scheduled tasks
   +-- plugin.stop(): close own resources
   +-- remove host providers/caches/registries
   |
   v
CLOSING_LOADER
   |
   +-- URLClassLoader.close(): close the loader's JAR/file handles
   |
   v
RELEASED
   |
   +-- drop remaining strong references
   |
   v
ELIGIBLE_FOR_GC (if no strong reference paths remain)
   |
   v
MAY_UNLOAD (JVM decides, no deadline)
```

Pseudocode illustrating the order, **not a standalone runnable class**:

```java
void unloadPlugin(PluginHandle handle) throws Exception {
    handle.rejectNewRequests();
    handle.awaitOrCancelRunningTasks();

    handle.unregisterCallbacks();
    handle.stopPluginResources();

    // Do not run new plugin tasks during close.
    handle.classLoader().close();

    handle.clearStrongReferences();
}
```

`PluginHandle` in the snippet above is an **illustrative interface/type designed by the application**, not a Java SE API. The snippet shows the lifecycle intent: coordinating threads, provider registries, and resource ownership—it does not mean `URLClassLoader.close()` calls those steps automatically.

**Do not close the loader while another thread is still loading.** The Java 17 JavaDoc warns that the result of a load concurrent with close is undefined. Stopping incoming requests and waiting for loading operations to finish before closing is an important operational requirement.

If a plugin supports a "running → stopped" state transition but still has registered objects called back by the host after shutdown, you must fix the callback contract and clear the registry. Close is not a mechanism to "immediately interrupt every function defined by the plugin".

## 11. Reloading a Plugin Requires a New Loader, Not Reopening the Old One

`close()` does not make a loader forget the classes it has defined, and Java SE has no API that guarantees unloading a specific class currently in use. Replacing the bytecode of `plugin.jar` and then calling `oldLoader.loadClass(name)` may still return the old class.

To transition from v1 to v2: stop v1 requests/tasks, unregister callbacks, close v1 resources and loader, release host references to old instances/`Class<?>`, and then create a **new loader** for v2. Keep shared API/SPI in the parent so the host recognizes the v2 provider; the implementation must be defined by each generation's loader, otherwise parent-first delegation may continue selecting the old version.

Two generations that independently define the same binary name are still two distinct runtime types; do not pass an old implementation object directly where a specific v2 class is expected.

## 12. Cases Where Developers Think `close()` "Succeeded" Yet the Plugin Still Consumes Memory

### 12.1 TCCL in a Thread Pool

`Thread.currentThread().setContextClassLoader(pluginLoader)` helps APIs that use TCCL discover the plugin. If not restored after the task, a still-alive worker thread can retain the old loader **after the plugin has closed**:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Run work/plugin SPI discovery in the right context.
} finally {
    thread.setContextClassLoader(previous);
}
```

This is an illustrative snippet assuming `pluginLoader` exists. With thread pools, you must manage TCCL on the **worker thread executing the task**, not only the submitting thread.

### 12.2 Host Static Registry

`HostEventBus.listeners` is a long-lived collection defined by a host class in the parent loader. If you add a listener object defined by the plugin loader and forget to remove it, the host still retains the listener even though the plugin loader has closed.

```text
GC root → host static registry → listener instance → plugin Class → PluginLoader
```

Fix: register with a registration token/handle and remove the registration in `stop()`. This cannot be solved merely by calling `loader.close()`.

### 12.3 Threads/Executors Created by the Plugin

If the plugin creates its own scheduler/threads and does not shut them down, the JVM may still have running tasks or threads waiting for work, along with stacks/contexts retaining the loader/classes/plugin instances. Shutting down schedulers, awaiting termination, and clearing task references are a separate part of the lifecycle.

### 12.4 Logging/JDBC/JMX and Framework Caches

A framework loaded in the parent may store class metadata, provider instances, callbacks, loggers/filters, MBeans, or driver registrations supplied by the plugin. On undeploy, you must call the framework's appropriate cleanup API. `URLClassLoader.close()` knows nothing about those registries.

### 12.5 File Resources Outside the Loader's Ownership

A plugin may itself call `new FileInputStream(...)` or `new JarFile(...)`, hold third-party streams, memory-mapped files, or native handles. These resources require separate cleanup. If the OS still reports a locked JAR after close, check **who is actually holding the file handle** instead of blaming `URLClassLoader` for everything.

## 13. Common Errors and How to Distinguish Them

| Symptom | Likely true interpretation | How to investigate |
| --- | --- | --- |
| Calling a plugin method after close still runs | Class/method already loaded; close does not unload bytecode | Are there still instance/`Class<?>`/method references? |
| `loader.loadClass("plugin.NewType")` after close throws `ClassNotFoundException` | Loader stopped looking up new classes from the URLs it manages | Was the class truly unloaded/not yet loaded? Is it in the parent? |
| Old class method fails due to a dependency after close | The dependency may only be lazy-loaded/resolved when the method runs | Look for `NoClassDefFoundError`/cause and resolution timing |
| JAR cannot be replaced on Windows despite close | Another handle still holds the file or close failed | Check suppressed `IOException`, streams, native handles |
| Metaspace stays high after multiple reloads | Old loader/plugin is still reachable or GC has not unloaded yet | Heap dump, TCCL, threads, static caches/registries, unload logs |
| Weak reference still present after `System.gc()` | Loader is not yet eligible or GC has not cleared the referent | Check retaining paths; do not treat a GC hint as a definitive test |
| V1 and V2 share the same class name but cannot be cast to each other | Different defining loaders, hence different runtime types | Separate shared API in parent, check class identity |
| Reloaded yet still getting old behavior | Parent defined the implementation or v1 cache/instance is still alive | Check `getClassLoader()`, namespaces, and registries |
| `IOException` on `close()` | Error closing a file opened by the loader | Handle/log it, inspect suppressed exceptions |
| Intermittent error while loader is being closed | Race between class loading and close | Synchronize lifecycle, stop/await before close |

Distinguish clearly:

- `ClassNotFoundException` typically appears in lookup APIs like `ClassLoader.loadClass` when finding a class fails.
- `NoClassDefFoundError` can appear when the JVM needs a dependent class during linking/execution and that class is unavailable, or when earlier initialization failed.
- `ClassCastException` between two classes with the same binary name usually relates to **two different defining loaders**, not directly to close.
- `OutOfMemoryError: Metaspace` in an application that reloads many times may relate to many unreclaimed loaders/class metadata, but requires evidence of retaining references and actual measurement before concluding.

## 14. How to Observe More Accurately When Investigating Leaks

Useful tools on a compatible JDK/HotSpot:

```bash
java -Xlog:class+load=info,class+unload=info -cp host CloseDemo
```

Depending on the environment, output may be very verbose or contain no unload events before the program exits. `class+load` helps observe classes being loaded; `class+unload` prints only when the runtime actually unloads.

You can use the `jcmd` command (when the tool is available and the process allows attach) to view loader statistics:

```bash
jcmd <PID> VM.classloader_stats
```

This is an **illustrative command**: replace `<PID>` with the real process ID without typing the angle brackets; commands/formats may differ across JDK versions or require appropriate permissions. Useful data includes **loader count, class count, and metaspace usage** across deploy/undeploy cycles.

To find the cause retaining a loader, you need a **heap dump and retaining-path analysis**. The goal is to find the reference chain leading from a GC root to the plugin loader or class/provider objects. During analysis, avoid keeping test references in the application itself or adding a new static debug cache that keeps the loader alive.

**Do not use `Runtime.freeMemory()` as a direct measure of class unloading.** Heap objects, native JAR handles, and metaspace class metadata are different kinds of resources. The JVM may retain already-allocated memory regions for reuse even after some loader/classes have been reclaimed.

## 15. Narrow-Scope vs. Long-Lived Loader Usage Examples

**Bounded task:** use `try (URLClassLoader loader = new URLClassLoader(urls, parent)) { ... }` when all loading and processing of classes/resources finishes inside the block; read and close streams before exiting.

**Long-lived plugin:** the manager retains both the loader and the instance throughout usage. Closing the loader inside a factory before returning the instance may allow existing methods to run while causing later lazy class/resource lookups to fail. Stop the plugin, wait for tasks to complete, clean up callbacks, close the loader, and then drop strong references.

The difference lies in **actual ownership scope**, not in the syntax of calling `close()`.

## 16. Self-Check Questions

**1.** After `URLClassLoader.close()`, do already-loaded classes disappear immediately from the JVM?

**Answer:** No. `close()` does not remove class definitions, objects, or static state. Class unloading relates to whether GC can reclaim the defining loader and is decided by the JVM.

**2.** Why does `message.invoke(obj)` in the example still return `still alive` after close?

**Answer:** The instance, `Class<?>`, and `Method` were already created/resolved before the loader closed. Close does not destroy already-loaded metadata/bytecode.

**3.** Can `URLClassLoader.loadClass("plugin.Hello")` after close return the same old `Class<?>`?

**Answer:** Yes, under the default mechanism when the class had its loading initiated by the loader and remains stored in lookup state (`findLoadedClass`). This is different from finding/defining a brand-new class from a URL after close.

**4.** Why does `plugin.NotYet.class` exist on disk yet loading it after close still reports not found?

**Answer:** The URL loader is closed, so it no longer uses its own URL sources to define new classes. The parent in the example does not provide that class either.

**5.** Why should you not close the loader and then let the plugin continue accepting requests?

**Answer:** Already-loaded methods may still work, but dependencies/resources that need to be loaded for the first time later may become inaccessible. Also, closing while a thread is racing to load produces undefined results.

**6.** Does `loader = null; System.gc();` guarantee that classes have been unloaded?

**Answer:** No. The loader may still be reachable via instances, class objects, caches, threads/TCCL, or registries; GC/unloading is also not forced to run immediately.

**7.** To reload JAR v2 with proper new type identity, what is typically required?

**Answer:** Create a **new `URLClassLoader`** after cleanly stopping/closing the v1 loader. If v1 and v2 are truly defined by two different defining loaders, the same binary name still yields two distinct runtime types.

**8.** If you use `try-with-resources` in a plugin factory function and then return the instance, what is the danger?

**Answer:** The loader closes before the plugin finishes operating. The plugin code may continue to work for a while, but will fail when it needs to lazy-load remaining classes/resources.

**9.** After close, the JAR is still locked. Can you conclude the JavaDoc is wrong?

**Answer:** No. There may be handles opened by the plugin or another library, or an I/O error during close. You need to investigate actual file handles and exceptions/suppressed exceptions.

**10.** A plugin's `Class<?>` is held in a static map in the host. Does `close()` help GC unload that class?

**Answer:** Close does not remove map entries. A strong reference from the host can keep the `Class<?>`/defining loader alive. You must clear caches/registries per lifecycle and verify no root references remain.

## 17. Checklist for Designing a Hot-Reloadable Plugin

1. **Loader scope:** Each deployment/version has its own loader, with shared APIs in an appropriate parent.
2. **Load phase:** Do not mix plugin classes into the application classpath where parent-first could pick the wrong class.
3. **Ownership:** Host/plugin define who manages threads, schedulers, listeners, drivers, MBeans, streams, and JAR handles.
4. **Stop:** Stop new requests; finish active tasks and ongoing class loading.
5. **Unregister:** Remove providers/listeners/caches/registrations from long-lived host objects.
6. **Context:** Restore TCCL, clear task `ThreadLocal`s, and inspect thread pools.
7. **Close:** Call `URLClassLoader.close()` once no work needs the URL sources, recording `IOException` and suppressed exceptions.
8. **Release:** Drop strong references to the old deployment's loader, instances, `Class<?>`, and reflection metadata.
9. **Reload:** Create a new loader for the new artifact/version, and verify class identity of shared APIs.
10. **Observe:** Monitor classloader stats, class unloading logs, metaspace, and heap retaining paths; do not use `System.gc()` as the sole success criterion.

## Conclusion

**`URLClassLoader.close()` ≠ unload classes ≠ shutdown plugin.** Close primarily closes sources/resources owned by the loader and prevents it from defining new classes from its URLs; **already-loaded classes can still be used**. For the JVM **to be able to** unload plugin classes, you must manage the full plugin lifecycle, drop strong references keeping the defining loader alive, and let GC decide when to reclaim it. There is no Java SE API that guarantees "close loader ⇒ classes disappear immediately".

**Authoritative References (Java 17):**

- [`URLClassLoader` Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html) — contract of `close()`, exceptions, URLs/JAR handles, behavior for already-loaded classes.
- [`ClassLoader` Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — `loadClass`, `findLoadedClass`, and parent delegation.
- [JLS 17 §12.7 – Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7) — conditions under which a class/interface may be unloaded.
- [JVMS 17 – Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — class identity, loaders, and resolution timing.
