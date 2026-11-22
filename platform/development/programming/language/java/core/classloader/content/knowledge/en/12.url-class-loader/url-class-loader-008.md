# Impact of close on JAR Handles and In-Progress Loading Operations

## 1. Why `URLClassLoader.close()` Matters

A `URLClassLoader` can load classes and resources from one or more directories/JARs. When a plugin, extension module, or dynamically loaded toolkit is no longer needed, the application often wants to release resources associated with those JARs. Java provides:

~~~java
URLClassLoader loader = new URLClassLoader(urls, parent);
loader.close();
~~~

`URLClassLoader` implements `Closeable`/`AutoCloseable` and provides the method `public void close() throws IOException`. According to the Java 17 documentation, `close()` renders the loader **no longer usable for loading new classes or resources defined/found by this loader itself from its URLs**, and closes the files it has opened for `jar:` and `file:` URLs. Already loaded classes remain accessible; classes/resources from the **parent** can still be requested through delegation.

Two points must be learned together:

- **Closing the loading source ≠ removing already loaded classes.** The JVM does not "roll back" class definitions when `close()` is called.
- **Closing the loader ≠ guaranteeing all running tasks have finished.** If another thread is loading a class when `close()` occurs, the API specification states that **the result of that load is undefined**. Do not rely on that race to implement hot reload.

In this lesson, "JAR handle" refers to the files/I/O structures opened by the loader to read JARs; it is **not** every object/class reference, nor does it mean the JVM frees all memory associated with the plugin.

## 2. Before and After `close()`: Behavior Table

Suppose `child` is a `URLClassLoader` with a URL pointing to `plugin.jar`; the parent does not contain the plugin's own classes/resources.

| Operation | While loader is open | After `child.close()` |
|---|---|---|
| Load a class never loaded by child from `plugin.jar` | Can succeed if bytecode is valid | Cannot expect child to find/define a new class from its URLs; `loadClass` typically throws `ClassNotFoundException` |
| Use an instance of an already defined class | Works according to program logic | Can still work if no additional missing classes/resources are needed |
| Call `loadClass` for a class already recorded by the loader as loaded | Returns the known class | Can return the same already loaded class, via the `findLoadedClass` check path |
| Load a class defined by the parent, e.g. `java.lang.String` | Delegation to parent/bootstrap | Parent can still find/return that class |
| `findResource` / `findResources` for a resource only in the plugin JAR | Searches along child's URLs | Respectively not found or yields no new elements from those URLs |
| `getResource` via child | Queries parent first, then child's source | Parent can still return its resources; closed child source is no longer a source for new lookups |
| Read an `InputStream` opened by `URLClassLoader.getResourceAsStream` | Readable while stream/loader are valid | Loader closes the streams opened by this method; do not continue using them |
| Rename/delete the JAR on disk | May be blocked by file handles held by the loader or other components | Loader attempts to release **its** handles; file operation outcome still depends on the OS and other handles |
| Class unloading | Depends on object/classloader lifecycle | **Does not happen automatically just because of close** |

Do not turn this table into a guarantee that every operation after `close()` will always fail: already loaded classes and parent classes remain accessible; whether an instance continues running also depends on dependencies whose bytecode might need to be loaded **for the first time** at a later point at runtime.

## 3. Basic Lifecycle of JARs and Class Sources

`URLClassLoader` accepts a `URL[]` array, for example:

~~~java
URL[] urls = {Path.of("plugins/hello.jar").toUri().toURL()};
ClassLoader parent = Host.class.getClassLoader();
// Illustrative code: requires the Host class and appropriate imports.
URLClassLoader loader = new URLClassLoader(urls, parent);
~~~

It typically opens a JAR **on demand** when reading a class or resource, rather than necessarily opening every JAR as soon as the constructor runs. Once a JAR handle is obtained, some runtimes/configurations may keep that source open to serve subsequent lookups.

~~~text
Create URLClassLoader
       |
       v
Not yet required to open all JARs
       |
       v
loadClass / getResource
       |
       v
Open JAR on demand, read bytecode or resource
       |
       v
Class defined; JAR handle may be held open
       |
       v
close()
  ├─ Stops ability to find new classes/resources from own URLs
  ├─ Attempts to close file/JAR handles opened by the loader
  └─ Preserves already defined classes and parent loader

Class unloading: a separate process, not a direct close operation.
~~~

Practical consequence: if an application updates a plugin JAR, it should **stop tasks using the plugin**, close the old loader and any resources still in use, and then create a **new loader** for the new version. Simply replacing the JAR's bytecode on disk does not change the contents of a `Class<?>` already defined by the JVM through the old loader.

## 4. Complete Java 17+ Example: Loaded Class, New Class, and Resource After Close

The experiment will create a JAR with:

- `demo.plugin.Early`: a class loaded **before** closing.
- `demo.plugin.Late`: a class **not yet loaded** at the time of closing.
- `plugin/data/label.txt`: a resource belonging only to the child's JAR.

The host loads via `URLClassLoader` using reflection so as **not** to accidentally place plugin classes on the application classpath.

### 4.1. Project Structure

~~~text
close-demo/
├── host-src/
│   └── CloseDemo.java
├── plugin-src/
│   └── demo/plugin/
│       ├── Early.java
│       └── Late.java
└── plugin-resources/
    └── plugin/data/
        └── label.txt
~~~

The file `plugin-resources/plugin/data/label.txt` contains the exact line:

~~~text
FROM_JAR
~~~

When compiling, outputs are separated into `build/host` and `build/plugin`, then packaged into a JAR at `dist/plugin.jar`. Only `build/host` is on `-cp` when running the program.

### 4.2. Early-Loaded Plugin Class

File **`plugin-src/demo/plugin/Early.java`**:

~~~java
package demo.plugin;

public final class Early {
    public Early() {
    }

    public String message() {
        return "EARLY_OK";
    }
}
~~~

The `message()` method only returns a string literal and does not need to resolve any other plugin implementation classes. This is important: when calling the method after `close()`, we deliberately avoid having the method itself request a new class from the closed JAR.

### 4.3. Class Loaded Only If Requested Late

File **`plugin-src/demo/plugin/Late.java`**:

~~~java
package demo.plugin;

public final class Late {
    public Late() {
    }

    public String message() {
        return "LATE_OK";
    }
}
~~~

The host **does not call `loadClass("demo.plugin.Late")` before closing the loader**. Once the loader is closed, a new lookup from the child's JAR will not succeed.

### 4.4. Host Controlling the Close Timing

File **`host-src/CloseDemo.java`**:

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CloseDemo {
    private CloseDemo() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: CloseDemo <path-to-plugin.jar>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Plugin JAR not found");
        }

        URL[] urls = {jar.toUri().toURL()};
        ClassLoader parent = CloseDemo.class.getClassLoader();

        try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
            Class<?> earlyClass = loader.loadClass("demo.plugin.Early");
            Object earlyObject =
                    earlyClass.getConstructor().newInstance();

            System.out.println("Before close: "
                    + earlyClass.getMethod("message").invoke(earlyObject));

            try (InputStream in =
                         loader.getResourceAsStream("plugin/data/label.txt")) {
                if (in == null) {
                    throw new IllegalStateException("Missing resource");
                }
                System.out.println("Resource before close: "
                        + new String(
                                in.readAllBytes(),
                                StandardCharsets.UTF_8).strip());
            }

            // Close the loading source before attempting subsequent lookups.
            loader.close();

            System.out.println("Existing object after close: "
                    + earlyClass.getMethod("message").invoke(earlyObject));

            System.out.println("Already loaded Class identity: "
                    + (loader.loadClass("demo.plugin.Early") == earlyClass));

            boolean lateUnavailable;
            try {
                loader.loadClass("demo.plugin.Late");
                lateUnavailable = false;
            } catch (ClassNotFoundException expected) {
                lateUnavailable = true;
            }
            System.out.println("Late class unavailable: "
                    + lateUnavailable);

            System.out.println("Own resource unavailable: "
                    + (loader.getResource("plugin/data/label.txt") == null));

            System.out.println("Parent String available: "
                    + (loader.loadClass("java.lang.String") == String.class));

            // Calling close() a second time has no new effect.
            loader.close();
            System.out.println("Second close completed");
        }
    }
}
~~~

**Why use both `try-with-resources` and an explicit `close()` call?** Because the experiment needs to observe lookups *immediately after closing*. `try-with-resources` still guarantees cleanup if an exception occurs before reaching the `close()` call. Upon exiting the block, Java calls `close()` again; the API specifies that closing an already closed loader is a no-op.

**Why not keep the `InputStream` and try reading it after close?** `URLClassLoader.getResourceAsStream` has a documented behavior: streams opened by the loader through this method are closed when the loader closes. Reading after close is unsafe, and the exact error message depends on the stream/URL implementation. Therefore, the example reads and closes the stream **before** `loader.close()`.

### 4.5. Compile, Package, and Run

Using **JDK 17 or later**, open a terminal in the `close-demo/` directory containing all files.

**Bash (Linux, macOS, Git Bash):**

~~~bash
mkdir -p build/host build/plugin dist

javac -encoding UTF-8 \
  -d build/plugin \
  plugin-src/demo/plugin/Early.java \
  plugin-src/demo/plugin/Late.java

javac -encoding UTF-8 \
  -d build/host host-src/CloseDemo.java

jar --create --file dist/plugin.jar \
  -C build/plugin . \
  -C plugin-resources .

java -cp build/host CloseDemo dist/plugin.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/plugin,dist | Out-Null

javac -encoding UTF-8 -d build/plugin plugin-src/demo/plugin/Early.java plugin-src/demo/plugin/Late.java

javac -encoding UTF-8 -d build/host host-src/CloseDemo.java

jar --create --file dist/plugin.jar -C build/plugin . -C plugin-resources .

java -cp build/host CloseDemo dist/plugin.jar
~~~

Verify that the JAR contains three entries:

~~~text
demo/plugin/Early.class
demo/plugin/Late.class
plugin/data/label.txt
~~~

You can inspect it with `jar --list --file dist/plugin.jar`; the JAR may also contain a manifest and directory entries.

**Expected stdout on Java 17+ with standard URLClassLoader:**

~~~text
Before close: EARLY_OK
Resource before close: FROM_JAR
Existing object after close: EARLY_OK
Already loaded Class identity: true
Late class unavailable: true
Own resource unavailable: true
Parent String available: true
Second close completed
~~~

The section after `close()` illustrates three boundaries: **already loaded classes remain usable**, **child's URLs are no longer a source for loading new classes/resources**, and **the parent can still provide classes**.

Do not change the run command to `java -cp "build/host:dist/plugin.jar" ...`. When the plugin JAR is already on the parent's classpath, `parent-first delegation` can load `Late` through the parent, making the demo output no longer representative of a closed child loader.

## 5. What Still Works After Closing?

### 5.1. Loaded Classes Are Not "Destroyed"

`Class<?>`, reflection metadata, and instances created before `close()` can still be used as long as they do not need to look up additional classes/resources from the closed URLs. In the experiment, `Early.message()` only returns a literal to illustrate this. Another method might fail when it first needs a lazy dependency after close; therefore, do not continue serving a plugin through a closed loader.

### 5.2. The Parent Remains a Valid Source

`loader.loadClass("java.lang.String")` can still succeed thanks to the bootstrap/parent loader. Resources owned by the parent can also be found; do not assume every `loadClass` or `getResource` call fails after close.

### 5.3. Do Not Confuse with JVM Class Unloading

Closing I/O handles does not remove `Class<?>` objects or force GC. Host caches, listeners, TCCL, or live tasks can keep the defining loader reachable; unloading is decided by the JVM when eligibility conditions are met.

## 6. JAR Handles: Why Windows and Linux Can Differ

When `URLClassLoader` opens a JAR, a handle/descriptor to that file may exist. On some operating systems, especially Windows, an open handle can cause operations to **rename, overwrite, or delete** the JAR file to be rejected. On many Unix-like filesystems, you can unlink/rename while the process still holds the handle, but the bytecode/resource content still being read by the process does not automatically synchronize with the new file on disk.

When `close()` is called:

1. The loader attempts to close the files that **it opened** via `jar:`/`file:` paths.
2. OS resources associated with those files can be released.
3. The application can attempt to replace the JAR more safely, **after tasks using the loader have been stopped**.
4. There is no guarantee the file can be immediately renamed/deleted: another loader, another `JarFile`, another `InputStream`, another process, or an antivirus/file scanner may still hold a handle.

**Do not test close by assuming `Files.delete(pluginJar)` will run and expecting identical results across all OSes.** Observe file handles with OS tools when needed, and rely on the Javadoc as the contract for the loader closing the files it opened.

An old URL from `loader.getResource(name)` is also not a "safe pointer that can be read forever" after close. If the caller uses `url.openStream()`, it may open **a new connection** according to the URL handler; this is the URL/resource's own behavior and does not prove the loader is still open. Therefore, do not use the ability to re-read an old URL as a test of whether `URLClassLoader` is closed.

## 7. What If Another Thread Is Loading a Class During Close?

This is the most important limitation in this lesson. The Java 17 Javadoc specifies that if **a thread is currently performing a class load** when another thread calls `close()` on the same `URLClassLoader`, the result of that load is **undefined**.

~~~text
Thread A                                Thread B
────────                                ────────
loader.loadClass("plugin.NewType")
   reading/linking class
        │                                    │
        └──────────── overlaps ──────────> loader.close()
                                             │
                                      closes JAR source
        │                                    │
   load result is not guaranteed by API
~~~

Do not hard-predict a single outcome:

- You cannot assert it will always throw `ClassNotFoundException`.
- You cannot assert it will always complete successfully.
- You cannot assert that simply synchronizing `close()` and `loadClass()` with an arbitrary `synchronized` block in the caller is sufficient for all code/libraries in the system: other threads and APIs also use the loader.
- Do not create a test race and treat a single "successful" run as proof of a correct lifecycle.

**Safe design pattern:** Do not call `close()` while the system can still trigger new class/resource loading operations from that loader. To close a loader, first **block new requests and wait for all tasks depending on the loader to finish**.

## 8. Proper Plugin Shutdown Sequence

A host can structure the lifecycle as follows:

~~~text
RUNNING
   |
   | 1. Block new requests to the plugin
   v
DRAINING
   |
   | 2. Wait for in-flight requests/tasks using the plugin to finish
   | 3. Unregister listeners/callbacks/schedulers, stop dedicated threads
   | 4. Close streams, sockets, JarFiles, and resources opened by the plugin
   v
QUIESCED
   |
   | 5. Restore TCCL and clear all host references to the old loader
   | 6. Call oldLoader.close() to release the loader's file/JAR handles
   v
CLOSED
   |
   | 7. Replace JAR and create a NEW loader to load the new plugin version
   v
RUNNING with new plugin
~~~

The order of `5` and `6` depends on the design: when closing the loader, the host must still hold a reference to `oldLoader` to call `close()`; only after closing should it drop the final reference. The invariant is **never let the loader close while tasks may still need to load additional classes/resources through it**.

### An Application-Level Synchronization Example

A simple model in which the host controls all tasks:

~~~java
// Illustrative code, not a standalone runnable file.
// These methods/scopes represent contracts provided by the application.
stopAcceptingNewTasks();
waitForInFlightTasksToFinish();
unregisterPluginCallbacks();
closePluginOwnedResources();
restoreOrClearThreadContextLoaders();
oldLoader.close();
oldLoader = null;
~~~

If using an `ExecutorService`, `shutdown()` only means **no new tasks are accepted**; that call alone does not wait for tasks to complete. You must combine it with `awaitTermination(...)`, `Future.get()`, or an appropriate in-flight counting mechanism. If waiting times out, **do not blindly close the loader** while tasks may still use it; transition to a timeout/cancel handling procedure and confirm quiescence.

Beyond actively executing methods, a task may use:

- `Class.forName(name, true, pluginLoader)`, reflection, or dynamic proxies requiring new classes.
- `ServiceLoader` with discovery/lazy provider initialization.
- `pluginLoader.getResources(...)` or `getResourceAsStream(...)`.
- Dynamic bytecode generation, class annotation scanning, or framework dependency injection.
- A thread context class loader (`TCCL`) pointing to the plugin loader.

Therefore, merely "seeing no plugin methods currently running" is not enough if tasks or lazy-loading from other code still exist.

## 9. `try-with-resources`, Idempotence, and Close Errors

`URLClassLoader` implements `AutoCloseable`, so you can write:

~~~java
try (URLClassLoader loader =
             new URLClassLoader(urls, parent)) {
    // Load and use the plugin within this scope.
}
// loader.close() is called automatically.
~~~

This is an **illustrative snippet** using pre-prepared `urls` and `parent` variables. In production environments, only use `try-with-resources` if **all tasks needing the loader finish before exiting the block**. If the plugin must persist across multiple requests, tie the loader to the plugin's lifecycle and close it during the coordinated shutdown phase.

Several documented properties:

- Calling `close()` multiple times: if the loader is already closed, subsequent calls have no effect.
- `close()` can throw `IOException`. The JVM attempts to close all opened files, catching `IOException`s along the way; if multiple `IOException`s occur, subsequent ones are added to the **suppressed exceptions** list of the first exception.
- `close()` does not catch all `RuntimeException`s or `Error`s.
- In runtimes still using a `SecurityManager` and corresponding policy, a `SecurityException` may be thrown if permission to close the classloader is lacking.
- In `try-with-resources`, if both the `try` body and the close operation throw an exception, the close exception may be **suppressed** onto the primary exception per `try-with-resources` semantics.

**Do not ignore `IOException` from close.** It indicates that at least one file failed to close; log it, track remaining handles, and decide whether it is safe to update the JAR yet.

Illustrative error-handling pattern:

~~~java
// Illustrative code; not a standalone program.
try {
    quiescePlugin();
} finally {
    try {
        loader.close();
    } catch (IOException ex) {
        // Log ex and ex.getSuppressed() in full.
        reportCloseFailure(ex);
    }
}
~~~

This pattern is only meaningful if `quiescePlugin()` actually reaches a state where no work is using the loader. Do not use `finally` as an excuse to close the loader while tasks are still running.

## 10. Closing Streams and URL Resources at the Right Time

There are at least three resource layers to distinguish:

| Layer | Examples | Who is responsible for closing? |
|---|---|---|
| ClassLoader | `URLClassLoader` | Host/plugin lifecycle manager calls `close()` |
| Resource stream | `InputStream` from `getResourceAsStream` | Caller closes as soon as possible; URLClassLoader also closes streams opened by this method itself upon `loader.close()` |
| Plugin-owned resources | Self-opened `JarFile`, sockets, threads, executors, JDBC pools | Code that owns/creates them is responsible for closing or shutting down |

**Do not treat `loader.close()` as a replacement for every `try-with-resources` in the application.** For example, if plugin code creates an independent `new JarFile(...)`, the loader has no obligation to know about or close it.

Nor should you keep a stream open and immediately close the loader:

~~~java
// Illustrative dangerous anti-pattern.
InputStream stream = loader.getResourceAsStream("plugin/config.txt");
loader.close();
// Do not read the stream here: the loader may have already closed it.
~~~

The right approach is to finish reading before closing the loader:

~~~java
// Illustrative code; loader remains open within the block.
try (InputStream in = loader.getResourceAsStream("plugin/config.txt")) {
    if (in != null) {
        byte[] bytes = in.readAllBytes();
        // Process bytes.
    }
}
// Only close the loader after all operations using it have finished.
~~~

Because reading resources from a JAR may use caches/file handles specific to the URL handler, do not try to guess the exact moment the OS releases all file descriptors solely from whether a `URL` object still exists.

## 11. Difference Between Class Reloading and Plugin Reloading

Replacing `dist/plugin.jar` after the old loader has already defined `demo.plugin.Early` does not change the bytecode or runtime `Class<?>` of that definition. A **new** loader can define the same name as a new runtime type. The plugin transition process needs to stop and drain v1, close resources, deploy the verified JAR, initialize loader v2, and only route requests to v2 once ready.

During a phase where two generations are active simultaneously, manage tasks/callbacks/loaders separately. Do not close loader v1 while tasks may still need lazy loading.

## 12. Relation to Parent Delegation and Class Identity

`URLClassLoader` uses parent-first delegation by default. `loadClass("java.lang.String")` through a closed loader can still return the bootstrap class; conversely, `loadClass("demo.plugin.Late")`, if present only in the child JAR and not yet loaded, cannot be newly defined from the closed URLs. In tests, avoid placing the plugin JAR on the parent application classpath because the parent can mask the scenario being measured.

Two loaders that each define the same binary name produce two distinct runtime types. Share interfaces/DTOs from the parent and inspect the defining loader via `Class.getClassLoader()` when communicating across generations.

## 13. Diagnosing Close / JAR Handle Issues

| Symptom | Possible Explanation | How to Check and Handle |
|---|---|---|
| Windows reports the JAR is in use | A loader, `JarFile`, stream, or process still holds a file handle | Quiesce the plugin, close all sources; inspect handles with OS tools |
| `loadClass` for a new plugin class fails after close | Loader no longer searches its own URLs | Create a new loader when loading a new version |
| Old plugin objects keep running after close | Loaded classes remain reachable | Valid behavior if no additional dependencies/resources are needed |
| Old method fails the first time it uses a new dependency | Dependency was not loaded by child before close | Do not close before the plugin truly finishes; do not assume all dependencies are eager-loaded |
| `ClassNotFoundException` when parent lacks the class | After close, cannot find new classes from child URLs | Check class source and loader state |
| A close/load race happens to succeed once | Result of concurrent class loading and close is undefined | Do not treat as a contract; coordinate stopping and waiting for tasks |
| `getResourceAsStream` read fails after close | Stream opened by the loader was closed | Read and close the stream before `loader.close()` |
| `close()` throws `IOException` | A file could not be closed | Log the main exception and suppressed exceptions; check handle status |
| Old plugin does not unload despite close | Host/thread/cache still holds references | Clean up callbacks, TCCL, ThreadLocal, executors, object/plugin references |
| Old URL can still be reopened | URL handler can create an independent new connection | Do not treat reading an old URL as proof that URLClassLoader is still open |
| Using `URLClassLoader` in try-with-resources and returning an async task | Scope exits before the async task finishes using the loader | Transfer loader ownership to a manager and close after tasks complete |

### Environment Observation Tips

On Java 17, commands that can help analyze class loading (specific values depend on the JVM and configuration):

~~~bash
java -Xlog:class+load=info -cp build/host CloseDemo dist/plugin.jar
~~~

JVM logging output contains many lines and is not stable in order or paths, so **do not** treat it as the standard stdout of the example. For file lock issues, OS tools like Process Explorer (Windows) or `lsof` (Unix-like) can help find the process/file descriptor holding the JAR. Never arbitrarily delete a JAR currently in use by a process to "force unload".

## 14. Design Pitfalls to Avoid

**Avoid 1: Closing immediately when "disable plugin" is clicked while tasks are still running.** Disabling should block new work and wait for draining; it does not mean all threads have finished.

**Avoid 2: Closing the loader in each request's `finally` block.** If the loader is shared across multiple requests, request A can close resources while request B is loading classes. The loader's owner must be the **plugin lifecycle manager**, not an arbitrary request.

**Avoid 3: Assuming `URLClassLoader.close()` is a reload mechanism.** It only closes sources/releases handles; it does not load new bytecode into old runtime classes.

**Avoid 4: Assuming `close()` guarantees every JAR can be deleted on every OS.** Descriptors/handles from other components may still remain.

**Avoid 5: Catching `ClassNotFoundException` to "automatically retry on the closed loader."** The old loader is not designed to be reopened via `loadClass` after close; create a new loader with explicit URLs.

**Avoid 6: Mixing shared APIs into the reloadable JAR and expecting old objects to cast to new classes.** Classes with the same name defined by different loaders have different identities; shared APIs should reside in the parent so both host and plugin recognize them.

## 15. Self-Check

**Question 1.** Loaded `Early`, created an instance, and called `loader.close()`. Is the old instance immediately invalidated?

**Answer:** No. Already created classes/objects can still be used. However, if an operation after close requires a dependency in the child JAR that has not been loaded yet, it may fail.

**Question 2.** Does `URLClassLoader.close()` force the JVM to unload classes and run GC immediately?

**Answer:** No. It closes the loader's loading sources/JAR handles; class unloading and GC are separate mechanisms.

**Question 3.** Why can `loader.loadClass("java.lang.String")` still work after close?

**Answer:** The parent/bootstrap loader can still provide the class. Closing the child does not close the parent.

**Question 4.** What does the API guarantee if one thread is loading a class while another thread calls `close()`?

**Answer:** The result of that concurrent class load is **undefined**. There is no guarantee that it will always succeed or always fail in a fixed manner.

**Question 5.** If an `InputStream` opened via `loader.getResourceAsStream(...)` is still around, should you continue reading it after `close()`?

**Answer:** No. The `URLClassLoader` API closes streams opened through that method when the loader closes.

**Question 6.** Why might a JAR still not be deletable on Windows after closing?

**Answer:** Handles may still be held by another loader, resource stream, `JarFile`, another process, or external tools outside the JVM. Close only handles files opened by this loader.

**Question 7.** When an application hot-reloads a plugin, when is it safe to call `oldLoader.close()`?

**Answer:** After stopping new work, ensuring tasks using the old loader have finished, and properly cleaning up related resources/callbacks/threads.

## 16. Official Documentation

- [Java SE 17 — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()): closing the loader, JAR/file handles, loaded classes, parent delegation, and undefined results when closing concurrently with class loading.
- [Java SE 17 — URLClassLoader.getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#getResourceAsStream(java.lang.String)): resource streams opened by the loader are closed when the loader closes.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResource`, `getParent`.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): cleanup with try-with-resources.
- [Java Virtual Machine Specification 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, and runtime type identity lifecycle.

**Key takeaway:** `URLClassLoader.close()` is an operation that **terminates new loading sources and attempts to release the loader's file/JAR handles**, not a command to remove already loaded classes. To close safely, **quiesce all tasks and loading activities**, read/close streams at the right time, and then close; never gamble on the outcome of `close()` happening concurrently with class loading.