# Closing URLClassLoader Releases Files Without Destroying Already-Loaded Classes

## 1. The problem of replacing plugins inside a single JVM

A Java host can create a `URLClassLoader` to load a plugin from a JAR, invoke plugin code, and later replace the plugin with a new version. When stopping the old plugin, the host should call `URLClassLoader.close()` to close files opened by the loader. However, **closing a classloader does not remove classes from the JVM or invalidate every object already created from those classes**.

This is an important distinction between two concepts:

- **I/O resource release:** closing the file/JAR handles opened by `URLClassLoader` so those resources are not held open indefinitely. Whether the file on disk can be renamed, deleted, or replaced still depends on the operating system, permissions, and any other processes/streams using the file.
- **Class unloading:** the JVM can reclaim classes defined by a classloader only when reachability, reference, and garbage collection conditions are satisfied. Calling `close()` does not force this to happen immediately.

Per the Java SE 17 contract, after `close()`, the loader cannot define additional **new classes or resources provided by itself**. Already-loaded classes/resources and anything coming from the parent loader remain accessible. If another thread is loading a class concurrently with `close()`, the outcome of that load is **undefined**, so the host must synchronize the lifecycle itself.

This lesson walks through understanding `close()` accurately, writing a Java 17 program to observe old objects continuing to work, distinguishing two versions with the same class name, and organizing plugin replacement without leaking file handles, threads, or references to the old loader.

## 2. What does URLClassLoader actually manage?

`java.net.URLClassLoader` is a classloader that locates classes and resources from a list of URLs, typically:

- The URL of a **JAR**: `file:/.../plugin-v1.jar`.
- The URL of a directory containing compiled `.class` files: `file:/.../classes/`, usually ending with `/`.
- A search path with multiple URLs in a specified order, after checking the parent under the default delegation model.

Typical loader creation:

~~~java
// Illustrative snippet: assume jarPath is already a Path to an existing JAR.
URLClassLoader loader = new URLClassLoader(
        new URL[]{jarPath.toUri().toURL()},
        HostApp.class.getClassLoader()
);
~~~

`jarPath` and `HostApp` here are illustrative symbols; the full example in Section 5 has real files and run commands. The loader may open a `JarFile` when looking up classes or resources. Merely instantiating `URLClassLoader` does not mean all JARs are opened or all classes are loaded.

### 2.1. What does close() do?

`URLClassLoader` implements `Closeable` and `AutoCloseable`, so it can be closed using try-with-resources. According to the Java 17 API:

1. `close()` stops locating/loading **new classes and resources defined by that loader**.
2. For `jar:` and `file:` URLs, it attempts to close files opened by the loader while loading classes or resources.
3. Already-loaded classes, already-obtained resources, and classes/resources reachable via the **parent** are not destroyed merely because the loader was closed.
4. Calling `close()` on an already-closed loader has no further effect (idempotent by contract).
5. Closing files is **best effort**: the method can throw `IOException` if closing a file fails, with additional I/O errors recorded as suppressed exceptions.
6. If `close()` runs concurrently with a thread loading a class through the loader, the outcome of that load is not guaranteed; do not use closing the loader as a synchronization primitive with running tasks.

Short-scoped example:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jarPath.toUri().toURL()},
        getClass().getClassLoader())) {
    // Use classes/resources found by the loader.
}
// close() is called even when exiting the block due to IOException/RuntimeException.
~~~

This is an **illustrative snippet inside an instance method**, not a standalone program. When a plugin runs long-term, the loader typically outlives a short code block; the plugin manager must retain the reference and call `close()` during a controlled stop step.

### 2.2. What does close() NOT do?

`close()` does **not**:

- Invoke an automatic destructor or “unload method” for every class.
- Set all created plugin objects to `null`, or throw exceptions on every method call to them.
- Reclaim a `Class<?>` or `Method` object still held by the host.
- Stop threads, executors, timers, scheduled tasks, or listeners created by the plugin.
- Clear `ThreadLocal` or restore `Thread.currentThread().getContextClassLoader()`.
- Close a `JarFile` opened independently by **other code**, or automatically clean up every socket/client/stream outside the loader's ownership.
- Delete, replace, or rename the JAR on disk, or guarantee GC/class unloading occurs immediately.
- Modify the classpath of an already-running system/application classloader.

Hence “close `URLClassLoader` to unload the plugin” is an **incomplete** shorthand. More accurately: the host stops plugin work, cleans up plugin-owned references and resources, and then closes the loader; afterwards the JVM **may** reclaim the loader and classes once nothing retains them.

## 3. Why do already-loaded classes still work?

In the JVM, a class is identified by its **binary name** together with its **defining classloader**. Two different loaders can define two versions of `demo.plugin.GreetingPlugin` and create **two distinct class identities**, even though the string names are identical.

Once bytecode has been loaded and defined as `Class<?>`, the class's method code does not depend on `URLClassLoader` keeping the JAR open to re-read **those already-loaded bytes**. An old instance can continue invoking ready methods, provided those instructions do not require the old loader to resolve additional new classes/resources and other linking conditions are met.

Distinguish the cases:

| Operation after `close()` | What can happen |
| --- | --- |
| Calling a method on an already-created instance using only ready classes | **Can still succeed**; Section 5's demo proves this case |
| Calling a method that causes the JVM to load an as-yet-undefined plugin class | May fail, often with a linking/class-loading error; do not rely on this to run stopped plugins |
| Calling `loader.loadClass(name)` for an already-loaded class or parent class | May still return the existing class due to caching/delegation |
| Calling `loader.loadClass(name)` for an unloaded class existing only in the closed loader's JAR | Cannot locate the new class from that JAR; typically throws `ClassNotFoundException` |
| Creating a new `URLClassLoader` pointing to a new-version JAR | Can define a new-version class with **a different identity**, if the parent does not “claim” that name |
| Calling `System.gc()` after `close()` | **Does not guarantee** GC runs or the old loader/classes are unloaded |

The fact that an old method runs after `close()` does **not** mean the host **should keep calling** a stopped plugin. It only shows that closing a loader is not a mechanism to revoke capabilities of live instances. A good plugin manager must prevent new calls via explicit state/lifecycle controls.

### 3.1. Parent delegation and shared API

A standard `URLClassLoader` searches through its parent first before searching its own URLs. If the host accidentally places `plugin-v1.jar` on the application classpath, the parent may define `demo.plugin.GreetingPlugin` first. When creating the v2 loader, calling `loadClass` may still return **the parent's class**, not the new version.

For real plugin systems:

- **Host and plugin** should share a common API/SPI (such as `Plugin`, `PluginContext`) defined by a parent loader.
- **Plugin implementations** reside only in the plugin version's loader; never put implementations on the application classpath.
- Avoid passing implementation/plugin-private types across the host boundary; use host-owned API types and DTOs.
- If child-first loading is needed for specific packages, design it deliberately and protect shared API packages; never override `loadClass` unconditionally.

Section 5's example intentionally uses reflection instead of a separate API JAR to focus on observing classloader close behavior. Production systems should still use a small, stable SPI.

## 4. File handles differ from already-loaded bytecode

Suppose loader 1 opens `plugin-v1.jar` and loads `GreetingPlugin.class`. The JAR may remain held open by the loader to locate subsequent classes/resources. `loader.close()` closes the files it opened, yet the bytecode of `GreetingPlugin` is already defined by the JVM and instances can still live on the heap.

~~~text
Before close:
    plugin-v1.jar --[file handle]--> URLClassLoader v1
                                        |
                                        +--> Class<demo.plugin.GreetingPlugin>
                                                   |
                                                   +--> instance held by host

After close:
    plugin-v1.jar --X [file handle managed by loader has been closed]
    URLClassLoader v1 --X [ability to locate new classes from its URLs]
    Class<demo.plugin.GreetingPlugin> ----> old instance is still referenced

After stop + dropping all references:
    loader/class/instance may become eligible for GC and class unloading
    (no unload timing guaranteed by the JVM)
~~~

The diagram above illustrates **two different kinds of relationships**. It does not prove every file handle is closed in every situation: a file might still be kept open by another `JarFile`, stream, monitoring tool, another JVM, or another process. When trying to replace JARs on Windows, watch closely for open handles; on Linux/macOS, unlinking/renaming an open file may succeed while the old handle still points to the previous inode.

For streams opened via `URLClassLoader.getResourceAsStream`, the API documentation notes that those streams are closed when the loader closes. Even so, **stream consumers should use try-with-resources themselves** and close promptly after reading rather than holding them until plugin shutdown. Do not treat `URLClassLoader.close()` as a way to clean up all third-party I/O resources.

## 5. Complete Java 17 example: old loader closed, old method still runs

The example uses two implementation JARs with **the same class name** returning two different messages, plus a class present only in JAR v1 that **has never been loaded**. The host performs:

1. Create loader v1, load `GreetingPlugin`, and call `message()`.
2. Close loader v1.
3. Call `message()` again on **the created instance** to observe it still works.
4. Try loading the unloaded `ExtraPlugin` via the closed loader v1; not found.
5. Create loader v2, load the same-named class from JAR v2, and compare class identity with v1.
6. Confirm the v1 instance still keeps v1 behavior because the host retains a reference to it.

**This is a demo of JVM mechanics, not a production lifecycle pattern.** In a real product, after stopping v1, the host should not keep calling it.

### 5.1. Directory layout

Create the following files under the working directory `loader-close-demo`:

~~~text
loader-close-demo/
  src/
    v1/demo/plugin/GreetingPlugin.java
    v1/demo/plugin/ExtraPlugin.java
    v2/demo/plugin/GreetingPlugin.java
    host/demo/host/LoaderCloseDemo.java
  build/
    classes/v1/
    classes/v2/
    classes/host/
    jars/
~~~

The `build` directories are created by the compile commands. The host is **not** compiled together with plugin sources and does **not** add the two plugin JARs to its own classpath.

### 5.2. Plugin version 1

**File `src/v1/demo/plugin/GreetingPlugin.java`:**

~~~java
package demo.plugin;

public final class GreetingPlugin {
    public GreetingPlugin() {
    }

    public String message() {
        return "hello-v1";
    }
}
~~~

**File `src/v1/demo/plugin/ExtraPlugin.java`:**

~~~java
package demo.plugin;

public final class ExtraPlugin {
    public static String id() {
        return "extra-v1";
    }
}
~~~

`ExtraPlugin` serves solely to test loading a **new** class after the loader is closed. In the host code, no class literal, reflection, or call loads it prematurely.

### 5.3. Plugin version 2

**File `src/v2/demo/plugin/GreetingPlugin.java`:**

~~~java
package demo.plugin;

public final class GreetingPlugin {
    public GreetingPlugin() {
    }

    public String message() {
        return "hello-v2";
    }
}
~~~

Despite sharing the name `demo.plugin.GreetingPlugin`, v2 will be defined by a different loader and return a different string. Putting the two JARs at two different paths avoids overwriting an already-open JAR in the example.

### 5.4. Host program

**File `src/host/demo/host/LoaderCloseDemo.java`:**

~~~java
package demo.host;

import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LoaderCloseDemo {
    private LoaderCloseDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path v1 = Path.of("build/jars/plugin-v1.jar");
        Path v2 = Path.of("build/jars/plugin-v2.jar");
        if (!Files.isRegularFile(v1) || !Files.isRegularFile(v2)) {
            throw new IllegalStateException("Plugin JAR missing");
        }

        ClassLoader parent = LoaderCloseDemo.class.getClassLoader();
        URLClassLoader loader1 = new URLClassLoader(
                new URL[]{v1.toUri().toURL()}, parent);

        Class<?> type1;
        Object instance1;
        Method message1;

        // try-with-resources will close loader1 when leaving the block.
        try (loader1) {
            type1 = loader1.loadClass("demo.plugin.GreetingPlugin");
            instance1 = type1.getDeclaredConstructor().newInstance();
            message1 = type1.getMethod("message");

            System.out.println(
                    "v1-before-close=" + message1.invoke(instance1));
        }

        // Already-obtained Instance and Method can still be used.
        System.out.println(
                "v1-after-close=" + message1.invoke(instance1));

        // This class is in JAR v1 but has not been loaded yet.
        try {
            loader1.loadClass("demo.plugin.ExtraPlugin");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("new-class-after-close=unavailable");
        }

        try (URLClassLoader loader2 = new URLClassLoader(
                new URL[]{v2.toUri().toURL()}, parent)) {
            Class<?> type2 =
                    loader2.loadClass("demo.plugin.GreetingPlugin");
            Object instance2 =
                    type2.getDeclaredConstructor().newInstance();
            Method message2 = type2.getMethod("message");

            System.out.println(
                    "v2=" + message2.invoke(instance2));
            System.out.println("same-class=" + (type1 == type2));
        }

        // Host still retains v1, so close does not mean invalidating it.
        System.out.println(
                "v1-still=" + message1.invoke(instance1));
    }
}
~~~

Explanation:

- `URLClassLoader loader1` is created with the host's application loader as parent. In the run command, the parent **does not contain** `demo.plugin.*`, so v1 is defined by `loader1`.
- `type1`, `instance1`, and `message1` are references kept outside the `try` block. Thus they remain usable after `loader1.close()` has run.
- `message()` only returns a string literal and needs no additional plugin-private classes. Hence both calls after closing `loader1` succeed in the demo.
- `ExtraPlugin` exists in JAR v1, yet was not loaded prior to closing; `loader1.loadClass` cannot read the new definition from that JAR. Nor does the parent have a class with that name, so `ClassNotFoundException` is thrown.
- `loader2` is newly created and sees `plugin-v2.jar`. It defines a class with the same binary name as `type1` but a **different defining loader**, so `type1 == type2` is `false`.
- No GC is invoked, nor is it claimed that the v1 file was deleted. The output lines prove **the ability to continue using already-loaded bytecode**, not that the loader was freed from the heap.

### 5.5. Compiling and packaging JARs

In `loader-close-demo`, using Bash with JDK 17+:

~~~bash
mkdir -p build/classes/v1 build/classes/v2 \
         build/classes/host build/jars

# Two classes of v1, packaged into a separate JAR.
javac --release 17 -encoding UTF-8 \
  -d build/classes/v1 \
  src/v1/demo/plugin/GreetingPlugin.java \
  src/v1/demo/plugin/ExtraPlugin.java
jar --create --file build/jars/plugin-v1.jar \
  -C build/classes/v1 .

# Class with same name but different implementation for v2.
javac --release 17 -encoding UTF-8 \
  -d build/classes/v2 src/v2/demo/plugin/GreetingPlugin.java
jar --create --file build/jars/plugin-v2.jar \
  -C build/classes/v2 .

# Host uses only the Java standard library; do not put plugin JARs on -cp.
javac --release 17 -encoding UTF-8 \
  -d build/classes/host \
  src/host/demo/host/LoaderCloseDemo.java

java -cp build/classes/host demo.host.LoaderCloseDemo
~~~

**Exact stdout:**

~~~text
v1-before-close=hello-v1
v1-after-close=hello-v1
new-class-after-close=unavailable
v2=hello-v2
same-class=false
v1-still=hello-v1
~~~

When using PowerShell on Windows, after compiling and creating the JARs, the equivalent launch command is:

~~~powershell
java -cp build/classes/host demo.host.LoaderCloseDemo
~~~

In this example the classpath has only one directory, so there is no `:` vs `;` separator issue. The Bash commands use backslashes for line continuation; in PowerShell, write `javac`/`jar` on full lines or use PowerShell's line-continuation syntax.

To confirm the JARs were built properly:

~~~bash
jar --list --file build/jars/plugin-v1.jar
jar --list --file build/jars/plugin-v2.jar
~~~

JAR v1 must contain `demo/plugin/GreetingPlugin.class` **and** `demo/plugin/ExtraPlugin.class`; JAR v2 must contain `demo/plugin/GreetingPlugin.class`. Adding plugin JARs to the host's classpath can alter the example results via parent delegation: avoid doing so.

### 5.6. Interpreting the limits of the demo

The example proves three independent points:

| Observation | Correct conclusion |
| --- | --- |
| `message1.invoke(instance1)` succeeds after `loader1.close()` | Already-loaded class code can still execute; close does not destroy instances |
| First load of `ExtraPlugin` after close fails | Closed loader does not define new classes from JAR v1 |
| `type1 != type2` and different messages | Same binary name yet two defining loaders produce two distinct class identities |

The example does **not** directly measure file descriptors, unloaded class counts, or GC conditions. Because the host still keeps `type1`, `instance1`, and `message1`, v1 remains referenced. To test GC/unloading eligibility in a separate experiment, move all strong references out of scope, stop threads/tasks, clean registries/caches, and observe with JVM tools; `System.gc()` is still not a guaranteed proof.

## 6. Why do method calls after close sometimes fail?

The takeaway is not “close the loader and keep calling the plugin normally.” There is a difference between **running code whose dependencies are already loaded** and **touching an as-yet-unloaded class/resource**.

Consider a plugin method:

~~~java
// Illustrative: this is only a method inside a plugin, not a standalone file.
public String format() {
    return new PluginFormatter().format("text");
}
~~~

Suppose `PluginFormatter` resides only in the plugin JAR and was never loaded before `loader.close()`. The first call to `format()` after close may force the JVM to resolve/load `PluginFormatter` and fail, commonly manifesting as a `LinkageError` such as `NoClassDefFoundError`, even though the initial instance still exists.

Likewise, calling `getResourceAsStream` to read a new resource after close may fail to locate the resource from the loader's URLs. This is very dangerous if the plugin still has background threads or callbacks running after the host closed the loader.

Therefore when **stopping a plugin**, do not rely on errors naturally occurring after close to block calls; use explicit state/lifecycle checks to reject new operations, wait for old operations to finish, and only then close.

## 7. Safe plugin replacement workflow

In production systems, replacing a plugin requires managing **two entities**: the active version and the version being prepared for activation.

A reference sequence:

1. **Prepare new version:** load the new JAR at **a separate path** (e.g., by ID/version), verify checksums/signatures per policy and API compatibility.
2. **Initialize v2 loader:** create a new `URLClassLoader` (or appropriate module layer mechanism), locate the implementation and instantiate it, and run validate/start steps. On failure, close v2 and keep v1 serving.
3. **Switch routing:** update the host's registry/entry point to v2 via a synchronized operation. In systems requiring zero downtime, coordinate in-flight calls and retryability per contract rather than simply swapping a variable.
4. **Quiesce v1:** stop admitting new requests, let running requests finish or cancel cleanly; stop v1 scheduled tasks and executors.
5. **Clean up v1 resources:** call `stop()/close()` lifecycle hooks, cancel listeners, callbacks, timers, and registrations; restore TCCL/`ThreadLocal` on the right threads and close streams/JarFiles/plugin-owned resources.
6. **Close v1 loader:** when no thread is using the loader to load more classes or resources, call `URLClassLoader.close()`. Handle `IOException` and suppressed exceptions instead of assuming every close succeeds.
7. **Drop references:** remove instances, providers, `Class<?>`, `Method`, `ServiceLoader`, lambdas, callbacks, and caches tied to v1 from host registries. Once no retaining references exist, the loader/classes become candidates for reclamation.
8. **Clean up old artifacts:** once handles are closed and nothing uses the old JAR, apply a deletion or archival procedure. Never overwrite an active JAR; keep a rollback path for verified versions.

This sequence does not require v2 to serve before v1 quiesces in every design; if state migration or exclusive resources exist, v1 may need to stop before v2 starts. Yet the invariant holds: **never close a loader while tasks might still need it**.

### 7.1. Plugin manager sketch (illustrative code)

~~~java
// Pseudocode - depends on lifecycle classes defined by the application.
PluginHandle candidate = prepareAndValidate(newJar);
PluginHandle previous = registry.switchTo(candidate);

previous.rejectNewCalls();
previous.awaitInFlightCalls();
previous.closeRegistrations();
previous.stopPluginOwnedExecutors();
previous.closePluginInstance();
previous.restoreOwnedThreadContexts();
previous.closeClassLoader();
registry.forget(previous);
~~~

This is **model code**, not a standalone Java program. These methods are not part of the JDK; implement them according to your application contract. In real systems, step ordering adapts to dependency relationships, timeouts, rollback, and error policies. If the candidate fails before switching, close the candidate and keep `previous` running; if stopping `previous` fails, report an incomplete cleanup state.

### 7.2. Closing plugin streams and resources before the loader

If a plugin opens its own `JarFile`:

~~~java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    // Read the plugin entry then close immediately once done reading.
}
~~~

This is **illustrative code** with `JarFile` imported from `java.util.jar` and `jarPath` as a `Path`. This file was not opened directly by `URLClassLoader`, so **you cannot expect `URLClassLoader.close()` to close it for you**. The same goes for streams from HTTP clients, database connections, watch services, zip readers, file readers, etc. Whoever opens or owns the resource must close it.

For resources obtained from a loader, close them promptly:

~~~java
try (InputStream in =
        pluginLoader.getResourceAsStream("plugin/config.json")) {
    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }
    byte[] content = in.readAllBytes();
    // Process content while the source remains open.
}
~~~

This is **illustrative code**: `pluginLoader` must exist and `InputStream` is imported from `java.io`. `readAllBytes()` suits only small, bounded files; large data must be read with buffers/limits. Never keep streams or `URL`s pointing into an old JAR inside caches that outlive the plugin session.

## 8. References that prevent a classloader from being reclaimed

Even after closing every file handle, an old loader can stay alive due to **strong references** from other parts of the application.

| Retaining source | Why it is dangerous | Remediation |
| --- | --- | --- |
| `Map<String, Object>` storing plugin instances | Host retains objects whose classes were defined by old loader | Remove providers/instances from registry on stop |
| `Class<?>`, `Method`, `Constructor<?>` in static cache | Retains reflective metadata of old-version classes | Evict cache by plugin ID/loader identity |
| `ServiceLoader` and provider lists | Caches providers/instances; `reload()` does not clear objects in other lists | Drop references to old service loaders/providers |
| `Thread.contextClassLoader` | Host thread pool still points to plugin loader | Restore TCCL in `finally` on that exact thread |
| `ThreadLocal` containing plugin context or instance | Worker thread retains value after request ends | `remove()` in `finally` on that exact thread |
| Plugin-owned threads, executors, schedulers | Long-lived threads retain classes, TCCL, stack frames | Cancel/stop/shutdown/await termination before close |
| Listeners, callbacks, timer registrations | Host singletons/event buses retain lambdas or plugin instances | Unregister and release registration handles |
| Lazy resource URLs, streams, JarFiles | File handles/connections can persist outside loader | Close by proper owner; retain no resources past stop |
| Stack frames executing plugin code | Unfinished calls still reference classes/loader | Quiesce and wait for in-flight calls |

Example of **properly scoped TCCL restoration**:

~~~java
ClassLoader original =
        Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    plugin.execute(context);
} finally {
    Thread.currentThread().setContextClassLoader(original);
}
~~~

This is illustrative code; `pluginLoader`, `plugin`, and `context` are variables from a real system. TCCL must be restored on **the exact thread that was modified**; you cannot fix thread A's TCCL by resetting TCCL on thread B.

If a plugin uses `ThreadLocal`:

~~~java
// Illustrative: REQUEST_CONTEXT is the application's ThreadLocal<?>.
REQUEST_CONTEXT.set(context);
try {
    usePlugin(context);
} finally {
    REQUEST_CONTEXT.remove();
}
~~~

A `static` field or cache owned by **the host** can pin an old loader for the lifetime of the JVM. Conversely, a static field inside a plugin class is not automatically a leak if the entire classloader/classes/instances have no remaining external references; inspect **reference paths from GC roots** rather than merely spotting the `static` keyword.

## 9. Common errors and how to diagnose them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Loader closed yet old method still runs | Loaded classes/instances/methods remain referenced | Valid JVM behavior; lifecycle gates needed to block new calls |
| `ClassNotFoundException` loading new class after close | Unloaded class exists only in closed loader's URLs | Use a new loader; do not reuse a closed loader |
| `NoClassDefFoundError` calling old instance | Method needs class not yet loaded by old loader, or missing runtime dependency | Inspect stack trace, stop ordering, and loaded dependencies |
| v2 plugin still returns v1 results | Host left implementation on parent classpath, or still calls v1 instance/cache | Check defining loader, routing, and artifact version |
| JAR cannot be deleted/renamed on Windows | Files/streams/JarFiles/loader still hold handles | Check open handles, resource ownership, and close errors |
| Live classloader count grows after reload | Caches, TCCL, threads, callbacks, in-flight requests retain loader | Inspect heap dominators, thread dumps, registries, loader counts |
| Resource not found after close | Resource lives in closed loader's URLs and wasn't opened/read earlier | Read completely and close stream before stop; do not open after close |
| Class loading concurrent with close gives flaky errors | Race between lifecycle stop and class loading | Synchronize quiescing; never close before all loads complete |
| `close()` throws `IOException` | One or more files opened by loader failed to close | Log suppressed exceptions too; handle cleanup status |

Useful diagnostic tools:

- **Thread dumps** and heap dumps: find threads, `ThreadLocal`s, callbacks, and GC roots retaining instances/classloaders.
- **JFR** or JVM class-loading/unloading logs: see whether specific classloaders get unloaded. On HotSpot, `-Xlog:class+unload=info` logs unload events; it is not a promise of when GC will unload.
- **`jcmd`** (if the JVM supports the corresponding diagnostic commands): inspect classloader statistics or heap histograms depending on version. Run `jcmd <pid> help` in the exact environment before using.
- **OS handle/file descriptor monitoring:** check whether JAR files are held open by the process, rather than using method-call success as an indicator.

Do not judge a classloader leak solely because total heap/metaspace failed to drop after one GC: the JVM may retain committed regions for reuse. Observe across multiple start/stop cycles and trace actual retaining paths.

## 10. Security limitations and version independence

`URLClassLoader` is a mechanism to load code into **the same JVM**, and does not automatically create a trustworthy security sandbox for untrusted plugins. A plugin can spawn threads, mutate shared state, or invoke APIs permitted to the process. Closing the loader later does not “undo” those side effects.

Additional policies are needed for JAR provenance, signatures/checksums, compatibility, dependency isolation, and lifecycle control. When two plugins use conflicting library versions, separate classloaders can help manage namespaces, provided the API contract is shared properly. A closed loader does not solve cross-loader reference leaks, plugin permissions, or native code cleanup.

In applications using **JPMS module layers**, module names, readability/exports, and module layer lifecycles differ from classpath URL loaders. Do not assume `URLClassLoader.close()` can “unload” an entire module layer; that is a separate topic. This lesson focuses on classpath JARs and `URLClassLoader`.

## 11. Checklist before replacing a JAR

- [ ] JAR v2 is built and verified at a separate versioned path, without overwriting the file read by loader v1.
- [ ] Shared API resides in the parent loader; implementations are never loaded accidentally from the parent classpath.
- [ ] New plugin is created, validated/started, and ready before switching routing (or uses an explicit stop/start sequence for exclusive resources).
- [ ] Host blocks new calls to v1 and waits/cancels running calls per contract.
- [ ] Plugin has shut down all owned executors, schedulers, threads, listeners, callbacks, connections, watchers, and streams.
- [ ] TCCL and `ThreadLocal` are restored/cleared on the exact threads used.
- [ ] `URLClassLoader.close()` is called after the plugin quiesces; handle `IOException` and suppressed exceptions.
- [ ] Host drops all v1 instances, `Class<?>`, reflection metadata, and registries/caches.
- [ ] Old files are deleted/archived only once no handles remain, without relying on loader GC.
- [ ] Test multiple v1→v2→v3 cycles, including failure branches and concurrent calls, monitoring loader/resource retention.
- [ ] Never interpret a post-close old method call as proof the plugin unloaded or that the loader can be reused.

## 12. Self-check

1. When `URLClassLoader.close()` is called, what happens to JAR files opened by the loader? **The loader attempts to close those files**; renaming/deleting the files still depends on other handles and the OS.
2. Does an already-created `GreetingPlugin` instance stop working immediately after close? **No.** While references remain and the method needs no new dependencies loaded, already-loaded code can still execute.
3. After close, can `loadClass` be called for a new class residing only in the old JAR? **No**, a closed loader does not define new classes from its URLs. Already-loaded classes or parent classes are different cases.
4. Why can v1 and v2 with the same class name coexist? **Different defining classloaders** produce distinct class identities.
5. Why is `System.gc()` not a “unload plugin” tool? **GC is not guaranteed to run on demand**, and a still-referenced loader is ineligible for collection.
6. Should the loader be closed immediately after routing switches to v2? **Not necessarily**; wait until v1 has no remaining in-flight calls or tasks needing its classes/resources.
7. If the host caches `Method` or retains v1's `Thread.contextClassLoader`, will `close()` eliminate the leak? **No**; caches must be cleared and contexts explicitly restored.
8. Why did the demo still print `hello-v1` after close? It only invoked an already-loaded method, not proving the loader was unloaded.

**Conclusion:** `URLClassLoader.close()` is **a class-loading/I/O resource cleanup step**, not a class-destruction command. To replace plugins properly, the host must stop work, reclaim plugin-owned resources and references, close the loader, and only then expect the JVM to reclaim old classes when GC runs appropriately. Loaded classes remaining usable after close is valid Java behavior and must be designed into the plugin replacement lifecycle.