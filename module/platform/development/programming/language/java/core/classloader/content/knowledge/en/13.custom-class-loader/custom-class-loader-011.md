# Preserving Type Identity Invariants and Closing Loader-Owned Resources

> **Java Core → ClassLoader → Custom Loader.** When writing or operating a class loader for plugins, you must protect the **identity of each runtime type** so that APIs exchanged between host and plugin always belong to the same type, and you must have a clear **resource-closing lifecycle**. Successfully loading a class is only the first step: cast errors between two classes with the same name, JARs retaining file handles, thread/context class loaders preventing plugins from unloading, or attempting to use a loader after close are all common design mistakes.

## 1. Two Independent Yet Related Goals

**Type identity invariant:** For normal classes/interfaces, the JVM distinguishes a runtime class by its **binary name and defining class loader**. Two different loaders both defining `example.Plugin` produce **two different runtime types**, even if the bytecode is completely identical. A single loader also must not define the same class name twice within the same namespace. When the host and a plugin need to exchange objects via an interface, both must see **the same `Class` object** for that interface.

**Resource ownership/lifecycle invariant:** A loader or plugin may open JARs, files, URL streams, sockets, native libraries, worker threads, executors, watchers, caches, or registries. The system needs to know **who creates them**, **who has the right to close them**, **when to block new work**, **when to wait for running work**, and **how to release them**. For `URLClassLoader`, `close()` has a specific contract regarding the JAR/file sources it opened; for a pure custom `ClassLoader`, the Java API **does not provide a common `close()`** for all loaders.

Summary:

~~~text
HOST (long lifecycle)
  |
  +-- Shared API/DTO, loaded by host parent loader
  |       |
  |       +------ Contract.class: only ONE runtime identity
  |
  +-- Plugin loader A -----> PluginImpl.class (identity A)
  |       + resources: JAR, streams, tasks, listeners
  |
  +-- Plugin loader B -----> PluginImpl.class (identity B)
          + resources: JAR, streams, tasks, listeners

Stopping plugin A:
quiesce tasks -> unregister/cancel -> close owned resources/loader
-> drop strong references -> GC can unload classes afterward
~~~

Key point: `close()` is not `unloadClass()`. I/O resources may already be closed, yet loaded `Class` types, objects, methods, or static state **still remain** if references are still held.

## 2. Type Identity Must Remain Consistent Across the Plugin Lifecycle

For normal classes/interfaces, the JVM identifies a runtime type by the pair **(binary name, defining loader)**. Two loaders can return the same name via `getName()`, yet `Class<?> a == Class<?> b` is `false` if they actually define two different copies. Conversely, two child loaders that delegate to the same parent can receive **the same type**.

- **The defining loader** is the owner of the class definition, inspected via `type.getClassLoader()`; an **initiating loader** may have merely initiated a request and then delegated to its parent.
- Two implementations with the same name defined by two independent loaders have separate static state and cannot be cast to each other. A shared API/SPI must be seen by both the host and plugins through the same defining loader.
- For a loader that has already initiated a class name, the default `loadClass` looks up/reuses the result; calling `defineClass` a second time to update the same name can throw a `LinkageError`.
- To load a new generation of a plugin, you typically need a new loader and to transfer objects through a stable parent API; do not assume that replacing the JAR on disk updates an existing `Class<?>`.

This article uses that principle to decide **who holds references and who releases resources** when a plugin is stopped or replaced. The next section specifies loader boundaries; closing and reclamation steps are verified separately in the lifecycle sections.

## 3. Defining API Boundaries and Loader Ownership

In a plugin system, place interfaces, DTOs, exceptions, or annotations exchanged with the host in a **shared API loader**, so that plugins delegate to it when needed. Implementations and private dependencies can belong to each plugin's own loader. If child-first loading is needed for an implementation package, scope that policy by namespace; never define `java.*` or host-owned API contracts yourself.

For a parent-first custom loader that only changes the bytecode source, prefer overriding `findClass`: the default `loadClass` already handles locking, `findLoadedClass`, delegation, and optional resolution. When a custom `loadClass` is truly necessary, you must preserve those steps and distinguish `ClassNotFoundException` from linkage/security errors. An interface with the same name but defined by a child loader can cause `isAssignableFrom` to fail on the host side.

Beyond `Class<?>` identity, a loader must also maintain **runtime packages, module access, certificate/signing, and package sealing** according to the rules. When loading from JARs, `URLClassLoader` helps handle much of the metadata and I/O out of the box. Do not treat `ProtectionDomain` or parent isolation as a sandbox; what matters for lifecycle management is identifying **which loader owns each resource** and being able to stop using it before closing.

## 4. Runnable Example: Same Name, Two Loaders, Two Identities

The goal is to verify firsthand that **the same JAR loaded by two separate loaders** produces two runtime classes. Do not place the plugin JAR on the host classpath.

Structure:

~~~text
identity-demo/
├── plugin-src/plugin/entry/Widget.java
├── host-src/IdentityDemo.java
├── plugins/               (to be created)
└── out/                   (to be created)
~~~

File **`plugin-src/plugin/entry/Widget.java`**:

~~~java
package plugin.entry;

public class Widget {
    public Widget() { }
}
~~~

File **`host-src/IdentityDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugins", "widget.jar").toUri().toURL();
        Class<?> leftType;
        Object leftObject;

        try (URLClassLoader left = new URLClassLoader(
                    new URL[] {jar},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader right = new URLClassLoader(
                    new URL[] {jar},
                    ClassLoader.getPlatformClassLoader())) {

            leftType = left.loadClass("plugin.entry.Widget");
            Class<?> rightType = right.loadClass("plugin.entry.Widget");
            leftObject = leftType.getDeclaredConstructor().newInstance();
            Object rightObject =
                    rightType.getDeclaredConstructor().newInstance();

            System.out.println("same name="
                    + leftType.getName().equals(rightType.getName()));
            System.out.println("same class=" + (leftType == rightType));
            System.out.println("same loader="
                    + (leftType.getClassLoader()
                       == rightType.getClassLoader()));
            System.out.println("left accepts right="
                    + leftType.isInstance(rightObject));
            System.out.println("right accepts left="
                    + rightType.isInstance(leftObject));
        }

        // close() has run; the loaded Class<?> is not "deleted".
        System.out.println("old instance still valid="
                + leftType.isInstance(leftObject));
    }
}
~~~

Compile, create the JAR, and run inside the `identity-demo` directory using Java 17+ (POSIX shell):

~~~bash
mkdir -p out/plugin out/host plugins
javac --release 17 -d out/plugin \
    plugin-src/plugin/entry/Widget.java
jar --create --file plugins/widget.jar -C out/plugin .
javac --release 17 -d out/host host-src/IdentityDemo.java
java -cp out/host IdentityDemo
~~~

Stdout:

~~~text
same name=true
same class=false
same loader=false
left accepts right=false
right accepts left=false
old instance still valid=true
~~~

**Line-by-line explanation:** Both `URLClassLoader` instances use the same URL, but because their parent is the platform loader and `plugin.entry.Widget` is not in the parent, each loader **defines its own** copy of the class. They share the same binary name but have different defining loaders. Cross-loader `isInstance` checks return false. After the `try-with-resources` block, `URLClassLoader.close()` has been called; existing objects/classes remain valid as long as references are still held.

**Demo constraints:** Do not put `plugins/widget.jar` on the host's classpath if you want to properly test the loader boundary. Do not use `ClassLoader.getSystemClassLoader()` as the parent merely for convenience when the host also happens to contain the same class. If a plugin needs a host-defined interface, you must use a parent that can find the right shared interface; this is explained in the next section.

## 5. Sharing a Contract Without Duplicating `Class`

A practical plugin architecture typically requires the host to receive a service object. Example shared contract:

~~~java
package api;

public interface PluginService extends AutoCloseable {
    String name();

    @Override
    void close();
}
~~~

This is the file **`api/PluginService.java`**, part of a project, not a program with `main`. A plugin can implement it:

~~~java
package plugin.impl;

import api.PluginService;

public final class PluginServiceImpl implements PluginService {
    @Override
    public String name() {
        return "plugin-A";
    }

    @Override
    public void close() {
        // Close resources owned by this instance.
    }
}
~~~

This is the file **`plugin/impl/PluginServiceImpl.java`**, also without `main`. To cast safely on the host:

1. Compile and place `api.PluginService` in the **host/shared API loader**.
2. Compile the plugin against that contract, but do not bundle a copy of the API that would be redefined by a child-first loader.
3. Create the plugin loader with the **host/shared loader as its parent**, and keep parent-first delegation for the `api` package.
4. The host obtains the implementation class from the plugin loader, invokes its constructor according to the contract/module access, and casts it to the host-defined `api.PluginService`.
5. The host calls the lifecycle `service.close()` before closing the plugin loader, and then drops object/loader references.

If the plugin and host **each redefine `api.PluginService`** with the same name, you may encounter a `ClassCastException` or `LinkageError`, even if the source text is identical. Merely having "the same JAR named api.jar" is not enough; the requirement is **the same runtime `Class<?>`**.

### 5.1. Checks When Receiving a Plugin

~~~java
Class<?> impl = pluginLoader.loadClass("plugin.impl.PluginServiceImpl");
if (!PluginService.class.isAssignableFrom(impl)) {
    throw new IllegalArgumentException("Wrong shared API loader");
}
PluginService service = PluginService.class.cast(
        impl.getDeclaredConstructor().newInstance());
~~~

This is a **snippet requiring the `PluginService` class, the `pluginLoader` variable, and valid access conditions**. Checking `isAssignableFrom` alone does not guarantee a public constructor, module opens, a trusted artifact, dependency resolution, or plugin lifecycle correctness. Do not use `getName().equals(...)` instead of a type check to "fix" a two-loader error.

## 6. What Does `URLClassLoader.close()` Actually Guarantee?

`URLClassLoader` implements `Closeable`/`AutoCloseable`, so it can be used with `try-with-resources`. According to the Javadoc:

- `close()` prevents the loader from **newly loading classes/resources that it defines/finds itself** through its URL path.
- Previously loaded classes/resources **can still be used**; classes/resources resolved via parent delegation **remain accessible**.
- For `jar:`/`file:` URLs, the loader **closes the files it opened** on a best-effort basis, including the corresponding JAR handles.
- `getResourceAsStream` is overridden by `URLClassLoader`: streams opened by this method are tracked/closed when the loader closes, according to the Javadoc.
- `close()` can throw an `IOException` if an error occurs while closing a file; if multiple IOExceptions occur, subsequent ones may be attached as suppressed exceptions.
- Calling `close()` again on an already-closed loader has no effect.
- If **a thread is loading a class concurrently with close**, the Javadoc states that the result of the in-progress load operation is **undefined**. Therefore, the lifecycle must prevent concurrency before closing.

**Not guaranteed:**

- `Class` objects and instances immediately disappear.
- `static` singletons are reset.
- The JVM immediately unloads classes or reclaims Metaspace.
- Threads/executors, sockets, JDBC connections, files opened **outside the loader**, logger appenders, HTTP clients, timers, listeners, and caches close automatically.
- URLs/InputStreams opened directly by the application via `URL.openStream()` or `Files.newInputStream()` are automatically cleaned up merely because the loader was closed.
- Native/JNI libraries loaded by the plugin are unloaded immediately; VM/OS and class loader constraints may still apply.

**There is no universal `close()` for all `ClassLoader`s**. If you subclass `ClassLoader` directly and open JARs/sockets/channels yourself, design your own `AutoCloseable`/`Closeable` implementation, or have another owner manage those resources. `URLClassLoader` has built-in I/O lifecycle handling because of its URL search path nature, not because all loaders work the same way.

## 7. Resource Ownership Management Patterns

For every resource, answer three questions: **Who creates it? Who closes it? When is it closed?** Examples:

| Resource | Appropriate owner | Close/release step |
| --- | --- | --- |
| `URLClassLoader` and its JAR handles | Plugin runtime / host plugin manager | `loader.close()` after no class-loading tasks remain |
| File streams/JarFile opened directly by plugin code | The component that directly opened them | `try-with-resources` or `close()` in its own lifecycle |
| Plugin executor/thread/timer | Plugin instance or the host manager overseeing the pool | `shutdown`, cancel, `awaitTermination`; avoid leaving tasks running |
| WatchService, sockets, DB pool | The plugin component that created them | Close using the corresponding API; handle errors on a best-effort basis |
| ServiceLoader and provider instance cache | Host/plugin container | Drop references, clear registry, do not retain providers after unload |
| `Thread.currentThread().getContextClassLoader()` | Each task/worker that sets the loader | Restore the previous loader in `finally` |
| ThreadLocal value holding a class/plugin | The code that sets the value | Call `remove()` per lifecycle rules, especially on thread pools |
| Static registry/listener on the host holding plugin objects | Host registry | Unregister listeners/callbacks/caches before unload |
| JNI/native library | Plugin/native runtime with its own contract | Release handles via the native API; do not expect `close(loader)` to suffice |

**Ownership principle:** If a loader is a child of a shared parent, **never call `close()` on the parent just because a plugin ends**, unless the plugin truly owns that parent. Closing a parent loader while other plugins still depend on it can break the system.

### 7.1. Using try-with-resources for Short Lifecycles

~~~java
URL location = Path.of("plugins", "task.jar").toUri().toURL();

try (URLClassLoader pluginLoader =
         new URLClassLoader(new URL[] {location},
                            ClassLoader.getSystemClassLoader())) {
    Class<?> pluginType = pluginLoader.loadClass("example.Task");
    // Run plugin work and close resources created by the plugin.
}
~~~

This is a snippet that requires imports for `java.net.URL`, `java.net.URLClassLoader`, `java.nio.file.Path`, and exception handling. The `example.Task` class and JAR must exist, so do not treat this as a standalone runnable program. The `try` block only auto-closes **pluginLoader**; objects created by the plugin may need their own lifecycle close **before** exiting the block.

### 7.2. Long Plugin Lifecycle: `stop → drain → close → release`

~~~text
ACTIVE
  -> STOPPING: reject new work, remove from discovery/routing
  -> DRAINING: cancel or await in-flight tasks; stop timers/threads
  -> CLEANUP: unregister callbacks/listeners; close plugin instances
  -> CLOSE LOADER: close JAR/file handles owned by the loader
  -> RELEASE: drop references to Class, Method, objects, caches, TCCL
  -> ELIGIBLE FOR GC: VM can unload classes when conditions are met
~~~

This is a **lifecycle management model**, not a state machine provided automatically by Java. You must define when a request is considered complete, the timeout/cancellation policy, how cleanup continues if a step throws an error, and how to prevent other actors from continuing to use the old plugin.

A pragmatic cleanup sequence:

1. Stop publishing the plugin and accepting new work; lock registration according to your contract.
2. Cancel/await background tasks and requests currently invoking plugin code; do not call `close()` on the loader while they are still resolving additional classes/resources.
3. Unregister callbacks, listeners, schedulers, MBeans, metrics hooks, and shutdown hooks/registries that the plugin registered with the host.
4. Call `close()` on the plugin service, release file/socket/DB pools, clean up ThreadLocals, and restore TCCL on workers.
5. Close loader-owned resources, including `URLClassLoader.close()`.
6. Drop all references the host still holds to plugin objects/classes/loader and any captured lambdas.
7. Observe GC/class unloading **without imposing a hard deadline**; verify via logs/profiler and repeat start/stop cycles during testing.

If a cleanup step throws an exception, record it and continue cleaning up **the remaining independent resources**, then aggregate the errors. Use `try/finally`, `try-with-resources`, or an appropriate suppressed-exceptions mechanism; avoid swallowing errors in a way that makes operations believe the plugin closed safely.

## 8. TCCL, Worker Threads, and Classloader Leaks

In a plugin system, a thread can hold a **strong reference** to a plugin loader via `Thread.contextClassLoader`. This is especially prone to happening with **long-lived executor threads**.

~~~java
Thread worker = Thread.currentThread();
ClassLoader previous = worker.getContextClassLoader();

try {
    worker.setContextClassLoader(pluginLoader);
    // Invoke ServiceLoader, resource lookup, or plugin callback.
} finally {
    worker.setContextClassLoader(previous);
}
~~~

This is a snippet requiring the `pluginLoader` variable and the actual callback logic. **Restore in `finally`** so that an exception does not cause the worker to retain the old loader. Do not assume that a task submitted to an `ExecutorService` will automatically inherit the TCCL from the submitter: a pre-created worker may have a different TCCL or one left over from a previous task.

A utility can wrap each task, capture the desired loader at the boundary, and restore the previous loader after the task. However, the plugin design must examine **who actually needs which loader**, rather than capturing a TCCL already polluted by a previous task.

Other roots include:

- `ThreadLocal` keys/values on a thread pool containing a plugin object/Class/Method.
- Host `static` maps, service registries, listeners, caches, and timers holding instances/classes.
- `ServiceLoader` or framework registries holding cached providers across multiple generations.
- Running threads executing methods of plugin classes, stack frames, and callbacks.
- Java native handles or JNI references within their respective lifetimes.
- A `Class<?>` or `Method` held by the host can retain the loader indirectly.

**Do not confuse:** Having plugin instances on the heap is not necessarily a memory leak if the plugin is still active. A "leak" is when the plugin **has already stopped** by design yet objects/loaders remain unexpectedly retained; you need heap dump/dominator paths and lifecycle evidence to draw that conclusion.

## 9. Class Unloading: What to Do and What Cannot Be Promised?

The VM **can** unload a class when VM/GC conditions allow, usually tied to the defining loader and its associated classes/objects no longer being reachable. However:

- The Java API does not provide a standard `ClassLoader.unloadClass(name)` method.
- `URLClassLoader.close()` does not force class unloading; loaded classes remain alive if `Class<?>` or objects are still referenced.
- `System.gc()` is only a GC hint and does not guarantee that GC will run or that classes will unload immediately.
- Do not judge it an "unload failure" just because a single GC cycle did not show the event; references may still remain, GC timing/runtime policies may differ, or the class may simply not unload during that observation window.

On HotSpot with unified logging support, you can inspect:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp out/host IdentityDemo
~~~

This command is a **HotSpot diagnostic**, not a universal contract across all JVMs. Depending on the JDK, you can use `jcmd <pid> VM.classloader_stats`, a heap dump, or Java Flight Recorder to inspect live loaders. Before using `jcmd`, check `jcmd <pid> help` to see which commands are supported. In a short lab, simply closing the loader while still holding `leftType`/`leftObject` will **not** prove that a class must be unloaded.

### 9.1. A Rigorous Experiment to Check for Leaks

Design a test loop:

1. Create a new loader for the plugin JAR and load/initialize the plugin.
2. Invoke plugin methods, and register and then unregister any required hooks.
3. Stop tasks and close resources; drop strong references in the host.
4. Use `WeakReference<ClassLoader>`/`ReferenceQueue` or profilers **for observation**, without treating an immediate result as conclusive proof.
5. Run multiple iterations, checking the number of classes/loaders, Metaspace, threads, and JAR file handles; compare trends.
6. If the loader remains reachable, trace strong reference paths such as TCCL, thread-locals, static caches, listeners, or providers.

Avoid using `finalize()` or finalizers as a cleanup contract: their timing is unpredictable, and finalization is unsuitable for enforcing a deterministic resource lifecycle. Prefer `AutoCloseable` and explicit lifecycle management.

## 10. Closing Self-Managed Resources in a Custom `ClassLoader`

If a custom loader reads JARs manually, you have two design options:

**A. Read class bytes within a short scope**, closing `InputStream`/`JarFile` with try-with-resources directly inside `findClass`. The loader does not need to keep the JAR open between lookups (at the potential trade-off of I/O cost). Ensure `defineClass` is called after the bytes are completely read.

**B. Keep `JarFile`/file channels/caches open longer** for fast loading. In that case, the loader/container must implement `AutoCloseable` and maintain a lifecycle state of `OPEN → CLOSING → CLOSED`, blocking new loads and synchronizing closing against in-flight loads.

Resource pseudocode:

~~~java
final class ResourceOwner implements AutoCloseable {
    private final java.util.jar.JarFile jar;
    private boolean closed;

    ResourceOwner(java.nio.file.Path path) throws java.io.IOException {
        jar = new java.util.jar.JarFile(path.toFile());
    }

    synchronized byte[] entryBytes(String name) throws java.io.IOException {
        if (closed) {
            throw new IllegalStateException("owner closed");
        }
        var entry = jar.getJarEntry(name);
        if (entry == null) {
            throw new java.io.FileNotFoundException(name);
        }
        try (var input = jar.getInputStream(entry)) {
            return input.readAllBytes();
        }
    }

    @Override
    public synchronized void close() throws java.io.IOException {
        if (!closed) {
            closed = true;
            jar.close();
        }
    }
}
~~~

This is a **standalone Java class that compiles on Java 17+** without `main`; it only illustrates a `JarFile` owner rather than a complete `ClassLoader`. `synchronized` serializes read/close operations in this example; another implementation could use a read/write lock, reference counting, or a state machine to avoid races. You must ensure that in-flight reads do not encounter a file being closed mid-operation.

**Do not use `finalize` or rely solely on GC to close files.** When a resource remains in the OPEN state even after the plugin business logic has stopped, file handles can keep the JAR locked (especially visible on Windows), causing artifact upgrade/removal failures.

## 11. Avoiding Races Between `close()` and Class Loading

For `URLClassLoader`, the API documentation states plainly: if one thread is loading a class while another calls `close()`, **the result of the load is undefined**. Therefore, you should separate responsibilities:

- Block issuing plugin handles / accepting new requests before shutdown.
- Wait for requests/background jobs that may load classes/resources to finish.
- Do not issue `close()` from a cleanup thread while a plugin scanner is still calling `loadClass`.
- If a stop error or timeout occurs, transition the state to FAILED/QUARANTINED according to container policy, and do not claim that resources were cleanly released.
- Synchronize state (lifecycle lock/counter/phaser) according to your system's concurrency rules; a standalone `AtomicBoolean closed` **is not enough** to guarantee that all loads have completed before closing.

Treat the plugin runtime as the single resource owner, rather than exposing `URLClassLoader` across multiple modules where anyone could call `close()`. In the host API, expose operational interfaces and centrally managed lifecycle controls.

## 12. Preserving Binary/Source Compatibility During Reload

Between two plugin generations, dependency versions may differ. Check:

1. **Shared API types are not accidentally shaded/relocated by the plugin** into a separate copy at runtime.
2. Host code does not retain `Class<?>`/method handles from the old generation when switching routing to the new generation.
3. Serialized objects, reflection, service interfaces, and callbacks must handle version boundaries; do not cast a gen A object to a gen B class based merely on name.
4. Have a closeability contract: providers implement `AutoCloseable`, or the plugin manager runs close hooks in order.
5. Old-generation JARs/resources are closed before deleting/replacing files, while references are still managed to prevent unload leaks.
6. Do not arbitrarily switch from `parent-first` to `child-first` across all packages to fix dependency versions; define package ownership clearly.

JPMS adds the concepts of module identity/access/layer; loading the right class file may still not be enough due to `requires`/`exports`/`opens` and module layer rules. Closing a loader does not automatically "remove a module" from a layer that is still referenced.

## 13. Common Errors and How to Fix Them

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `Plugin cannot be cast to Plugin` | Two classes with the same name but different defining loaders | Share the contract through the parent; inspect loader identity |
| `LinkageError: attempted duplicate class definition` | Repeatedly calling `defineClass` for the same binary name in one loader | Use `findLoadedClass`, locking, and do not redefine |
| `NoClassDefFoundError` after the loader has closed | A component still needs a new class after shutdown | Block activity, wait/drain tasks, and close only when safe |
| `IOException` from `URLClassLoader.close()` | Failure closing file handles | Handle/log it, check suppressed errors, retry per policy, but do not assume a clean close |
| JAR cannot be deleted/renamed on Windows | `JarFile`/stream/loader is still open | Close the owner and URLClassLoader, and find the actual open handles |
| Old plugin does not unload after GC | TCCL, threads, ThreadLocal, or host registries/caches retain the loader | Shutdown/unregister/remove, and inspect the heap dominator path |
| Parent API version mismatch between host and plugin | Incorrect dependency packaging/shading | Use a shared API loader and contract tests |
| `IllegalAccessError` in a module | JPMS readability/exports/opens | Fix the module graph/access rather than bypassing by class name |
| Child-first loader deadlock | Circular delegation, coarse locking, or flawed concurrency | Use getClassLoadingLock/parallel-capable policy and simplify the graph |
| ServiceLoader does not discover provider | Wrong TCCL, missing SPI metadata, or provider type from a different loader | Use a shared interface, the right loader, and proper cache/lifecycle handling |
| Native library remains retained | JNI/OS/native references and lifecycle differ from class loading | Close native resources via their API; do not trust `close(loader)` to unload them automatically |

## 14. Implementation and Review Checklist

- [ ] Define **shared API packages** and **plugin-private packages**; test `sharedContractFromHost == sharedContractFromPlugin`.
- [ ] Do not define duplicate binary names in the same loader; use delegation, `findLoadedClass`, and appropriate locking.
- [ ] Control parent-first/child-first per package, and prevent child loaders from redefining `java.*` or host APIs.
- [ ] Clearly identify the owner of the loader, `JarFile`, InputStreams, executors, sockets, watchers, native handles, and listeners.
- [ ] Short-lived resources use `try-with-resources`; long-lived owners have an explicit `close()` with idempotence tested.
- [ ] Plugin shutdown follows **quiesce → drain → cleanup → close → release**, handling errors at each step.
- [ ] Every task that changes the TCCL restores it in `finally`; clean up ThreadLocals/registries.
- [ ] Do not use the loader after `close` to look up **new classes/resources defined by the loader itself**.
- [ ] Do not expect `close()` to make loaded `Class` objects, instances, or native resources disappear.
- [ ] Test repeated reloads, observe loader retention/file handles, and distinguish transient GC behavior from real leaks.
- [ ] Review module access and cross-version class compatibility; do not treat `getName()` as proof of castability.

## 15. Self-Check Exercises

1. Two `URLClassLoader` instances have identical URLs and the same platform parent loader, and each defines `plugin.Widget` itself. Are the two `Class` objects `==`? **No**.
2. Two child loaders both delegate `api.Contract` to their parent. Are the two `Class` objects returned by `loadClass` `==`? **Yes**, if the parent actually defines the same runtime type.
3. Does `URLClassLoader.close()` invalidate existing objects of already-loaded classes? **No**.
4. Can you call `close()` while another thread is loading classes and expect deterministic behavior? **No**, you must quiesce/drain first.
5. Is there a standard `ClassLoader.close()` for every custom loader? **No**.
6. If the plugin manager drops its reference to the loader, yet an executor thread still has its TCCL pointing to the loader, is class unloading guaranteed? **No**.
7. Should you call `System.gc()` to "force unloading"? **No**, it is only a hint.
8. How do you avoid duplicate classes in a custom loader? **findLoadedClass + class loading lock + define once**.
9. `ServiceLoader` has cached an old plugin provider and you only close the loader: will the provider object disappear automatically? **No**, you must clear the cache/references.
10. What is the purpose of `parent-first` for a shared API? **To keep the contract in the same defining loader seen by both the host and plugins**.
11. Is a JNI native library guaranteed to unload when URLClassLoader closes? **No**, native lifecycles are separate.
12. How do you verify a memory leak? **Inspect strong reference roots and run repeated stop/reload cycles, rather than looking at a single GC**.

## 16. Specifications and API Documentation

- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity, defining/initiating loaders, loading constraints.
- [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `findLoadedClass`, `defineClass`, `getClassLoadingLock`, and `registerAsParallelCapable`.
- [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): URL search path, `close`, JAR/file handles, and concurrent close behavior.
- [AutoCloseable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): scoped resource cleanup.
- [JarFile — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/jar/JarFile.html): native JAR file owner and I/O lifecycle.
- [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): context class loader references.
- [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider discovery/cache and loader selection.

**Conclusion:** A proper custom loader does more than just load bytecode; it must **preserve the same runtime identity for shared contracts** and **properly close the resources it owns** under a managed lifecycle. `URLClassLoader.close()` helps release file/JAR handles, but it **is not a class-unloading command**, does not stop plugin threads, and does not clear all strong references. Design type boundaries, concurrency, and cleanup up front so that plugin reloading does not become a source of hard-to-reproduce bugs.
