# Releasing JAR Handles and Avoiding File Locks After Reload

## 1. Why Can't a JAR Be Replaced or Deleted After Reloading a Plugin?

In a Java application that loads plugins from `plugin.jar`, components such as `URLClassLoader`, `JarFile`, or resource-reading streams can hold a **file handle** to the JAR. When redeploying (reloading), the application typically wants to replace JAR v1 with JAR v2; if those handles have not been closed, overwrite, rename, or delete operations may fail — especially on Windows.

Sometimes the JAR can be replaced, yet the program still runs the old code. That is a different issue: the JVM has already defined the class by its **binary name and defining class loader**, and does not automatically update the bytecode of an already loaded class just because the JAR file on disk changed.

Three goals must be distinguished:

1. **Releasing the file handle:** closing the loader/stream/archive/connection that owns the handle so the operating system can release the I/O resource.
2. **Loading the new version:** creating a **new loader** for the new version of the JAR instead of reusing the loader that defined the v1 classes.
3. **Unloading classes from memory:** having no remaining strong references to the classes, class loader, instances, and related structures; only then *may* the JVM collect/unload them if appropriate.

The three goals are related, but **not equivalent**. `URLClassLoader.close()` does not automatically unload classes, and `System.gc()` is not an API for closing JAR handles.

Symptoms:

| Symptom | Possible Problem Category |
| --- | --- |
| Windows reports the file is being used by a process | Handle from loader, JarFile, cache, stream, or another process |
| Linux allows deleting the file, but memory/FD usage increases | Unlinking does not guarantee the descriptor has been closed |
| Reloaded, but calling a method still returns the v1 value | The v1 class is still in use; not creating/routing to the v2 loader |
| After multiple reloads, metaspace grows | Old loader/classes are still referenced; heap/GC analysis needed |
| Reload only fails when concurrent requests are running | Closing the loader while another thread is still loading classes/resources |
| After closing the loader, the plugin still has running threads | `close()` does not automatically call plugin stop/shutdown |

## 2. The Exact Contract of URLClassLoader.close()

`java.net.URLClassLoader` implements `java.io.Closeable` and can be used in *try-with-resources*. According to the Java SE 21 Javadoc:

- `close()` closes the loader so that it can no longer load **new classes and resources defined by that loader itself**.
- **Already loaded classes** remain accessible; classes/resources defined by the parent can still be reached via delegation.
- For `file:` and `jar:` URLs, it attempts to **close the files opened by that loader itself**.
- If another thread is still performing class loading when `close()` is called, **the result of the in-progress operation is undefined** per the API contract.
- `close()` makes a best effort to close all files, preserving any `IOException` and suppressed exceptions when multiple errors occur.
- Calling close again on an already closed loader is a no-op.

What `close()` **does not promise**:

- It does not destroy instances created from the loader's classes.
- It does not guarantee that Class objects or metaspace will be collected immediately.
- It does not automatically stop plugin threads, executors, scheduled tasks, or callbacks.
- It does not automatically close every `new JarFile(...)` or every `URL.openStream()` opened by external libraries.
- It does not close the parent system/application loader or sibling loaders.
- It does not turn old class definitions into new bytecode.
- It does not guarantee the JAR file is released if **another owner** still holds a handle.

Therefore, after `close()` succeeds, you can only assert that **the close operation on that specific URLClassLoader has been performed**; you cannot infer that the entire process has stopped holding the JAR.

## 3. Managing Loader Lifecycle with try-with-resources

Basic example:

~~~java
Path jar = Path.of("plugins", "plugin-v1.jar")
        .toAbsolutePath().normalize();
URL url = jar.toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[]{url}, Host.class.getClassLoader())) {

    Class<?> impl = loader.loadClass("demo.Greeter");
    // Work with impl while the loader lifecycle is still open.
}
// loader.close() is called here.
~~~

This is a **non-standalone** illustrative snippet, assuming `Host` and imports are available. `try-with-resources` ensures the loader is closed when the block exits, even if an exception occurs. If `close()` throws an `IOException`, the caller must handle/log it; if the block also throws an exception, the close error may be attached in `getSuppressed()` of the primary exception.

**Important for long-lived servers/plugins:** do not wrap `try-with-resources` around **just the `loadClass` call** and then return the plugin instance for subsequent requests. Once the block exits, the loader is closed, so if the instance later needs to load additional dependencies or resources, new loading may fail.

Let the plugin manager own the loader for the **entire serving session**, and close it **after** the plugin stops operating.

### The Parent Is Not Owned by the Child

Do not accidentally close the application/system loader or a parent loader shared across multiple plugins. Calling `URLClassLoader.close()` on a child loader **does not** close the parent; that is the intended behavior. If the parent classpath also contains the same plugin JAR, closing only the child loader is not enough to release the handle owned by the parent — and may cause parent-first delegation to return the old version of the class.

## 4. Resource Streams and Independent Handles

Plugins often read configuration/resources directly from the JAR:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jarUrl}, parentLoader)) {

    try (InputStream in =
                 loader.getResourceAsStream("demo/config.txt")) {
        if (in == null) {
            throw new IllegalStateException("Missing demo/config.txt");
        }
        String config = new String(in.readAllBytes(),
                StandardCharsets.UTF_8);
        // Use config.
    }
}
~~~

This is illustrative code with `jarUrl`, `parentLoader`, and imports assumed. The proper order: **close the stream first, close the loader second**.

`URLClassLoader.getResourceAsStream` has a contract: when the loader is closed, resources opened by this method are closed. Even so, you should always close the stream itself immediately after use with *try-with-resources*, rather than letting it stay open for the entire lifetime of the loader.

A stream obtained from **another API** may have a different owner:

| How It Was Opened | Owning Object | Appropriate Management |
| --- | --- | --- |
| `loader.getResourceAsStream(name)` | The loader and the stream it opened | Close the stream when done, close the loader when the plugin stops |
| `url.openStream()` | URLConnection/stream; may use `jar:` handler cache | Close the stream, pay attention to connection/cache |
| `new JarFile(path)` | Separate JarFile | Close JarFile explicitly |
| `new ZipFile(path)` | Separate ZipFile | Close ZipFile explicitly |
| Framework-specific nested JAR reader | Separate framework/resource subsystem | Follow the framework's lifecycle |

Do not assume that `loader.close()` will scan every `JarFile` object on the heap and close them all.

### When Reading a JarFile Directly

~~~java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    JarEntry entry = jar.getJarEntry("demo/config.txt");
    if (entry == null) {
        throw new IllegalStateException("JAR entry missing");
    }

    try (InputStream in = jar.getInputStream(entry)) {
        String content = new String(in.readAllBytes(),
                StandardCharsets.UTF_8);
        // Process content.
    }
}
~~~

This snippet requires `JarFile`, `JarEntry`, `InputStream`, `StandardCharsets`, and a valid `jarPath` variable. The stream is closed before the JarFile. If a dependency opens a JAR this way on its own, closing the host's URLClassLoader does not take over responsibility for closing that JarFile.

## 5. Closing Is Not Class Unloading

Suppose loader L1 defines class `demo.Greeter` from v1:

~~~text
URLClassLoader L1
    |
    +--- opens plugin-v1.jar
    |
    +--- defines Class<demo.Greeter>
             |
             +--- v1 instances, static state, references
~~~

After `L1.close()`:

- Files owned by L1 have been put through the closing process per the contract.
- `Class<demo.Greeter>` v1 **is still a live runtime class** if it remains referenced.
- Already linked methods and already created objects may still be usable within their respective limits; however, lazy class loading from L1 is not guaranteed to work after close.
- `Class<?>`, instances, reflection method/constructor objects, callbacks, threads, or host registries can keep L1 alive.

To use the v2 class with the same binary name, create **L2**, because the JVM distinguishes classes by **binary name + defining loader**:

~~~text
demo.Greeter @ L1 = v1 definition
demo.Greeter @ L2 = v2 definition

same name, but two different runtime Class objects
~~~

You cannot force L1 to redefine `demo.Greeter` again by modifying the JAR in place and calling `L1.loadClass(...)`. The JVM does not replace already defined bytecode just because the filesystem changed.

`System.gc()` is not an instant class-unloading command. Class unloading depends on GC conditions and whether the loader/classes are still retained; do not use an infinite GC-calling loop to wait for file deletion.

## 6. Safe Hot Reload Workflow

When reloading a plugin that is continuously serving traffic, you should have a **lifecycle coordinator**:

~~~text
RUNNING (plugin v1)
    |
    | Start reload
    v
QUIESCING: block new requests/tasks to v1
    |
    | Wait for in-flight requests to complete
    v
STOPPING: plugin.stop(), cancel tasks, unregister handlers
    |
    | Close streams, connections, other JarFile/ZipFile instances
    v
CLOSING: URLClassLoader.close(), handle IOException
    |
    | No thread is still loading from loader v1
    v
RETIRED: drop references to v1, clean up old JAR when no handles remain
    |
    v
START v2: new loader, new instance, health check, accept requests
~~~

If you want zero downtime, you should **load v2 first in a separately named file**, run a health check, and then switch routing; only after that wait for v1 to stop completely and close the old loader:

~~~text
plugins/
    greeter-1.0.0.jar  <-- L1; old requests
    greeter-2.0.0.jar  <-- L2; new requests
~~~

This is **plugin-level blue/green deployment**, avoiding replacing a file currently held open by the old loader:

1. Deploy JAR v2 under an immutable versioned name.
2. Create an independent L2, initialize the new plugin, and run a health check.
3. Switch new requests to L2 using a synchronized pointer/registry.
4. Wait for v1 to finish in-flight tasks and stop all v1 resources.
5. Close L1, clean up references, and only then delete the v1 JAR file when no handles remain.

With a design that overwrites the same `live.jar` file, the replacement should happen **after closing** all owners of the old JAR. In production systems, placing new releases under versioned names is generally easier to roll back and less dependent on OS locking behavior.

## 7. Java 17+ Hands-On Exercise: Closing Loader v1 Then Replacing live.jar

This exercise has **two class sources with the same binary name** but different implementations, compiled into **two separate JARs**. The host runs with a classpath containing only host code, loads JAR v1 and then JAR v2 through two `URLClassLoader` instances, closing the stream and loader between the two runs.

### Source Structure

~~~text
example/
├── src/
│   ├── v1/demo/Greeter.java
│   ├── v2/demo/Greeter.java
│   └── host/ReloadDemo.java
├── out/
│   ├── v1/demo/...
│   ├── v2/demo/...
│   └── host/...
└── dist/
    ├── v1.jar
    ├── v2.jar
    └── live.jar
~~~

The two `Greeter.java` files intentionally share the same class name, so **do not compile them into the same output root**.

### File src/v1/demo/Greeter.java

~~~java
package demo;

public final class Greeter {
    public static String version() {
        return "v1";
    }
}
~~~

### File src/v2/demo/Greeter.java

~~~java
package demo;

public final class Greeter {
    public static String version() {
        return "v2";
    }
}
~~~

### File src/host/ReloadDemo.java

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class ReloadDemo {
    private static Class<?> usePlugin(Path jar, String label)
            throws Exception {
        URL url = jar.toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url},
                ReloadDemo.class.getClassLoader())) {

            Class<?> type = loader.loadClass("demo.Greeter");

            System.out.println(label + " defined by child: "
                    + (type.getClassLoader() == loader));

            System.out.println(label + " version: "
                    + type.getMethod("version").invoke(null));

            try (InputStream in =
                         loader.getResourceAsStream("demo/config.txt")) {
                if (in == null) {
                    throw new IllegalStateException("Missing config");
                }
                String value = new String(in.readAllBytes(),
                        StandardCharsets.UTF_8).trim();
                System.out.println(label + " config: " + value);
            }

            return type;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("live.jar next.jar");
        }

        Path live = Path.of(args[0])
                .toAbsolutePath().normalize();
        Path next = Path.of(args[1])
                .toAbsolutePath().normalize();

        Class<?> first = usePlugin(live, "before");

        Files.copy(next, live, StandardCopyOption.REPLACE_EXISTING);
        System.out.println("jar replaced");

        Class<?> second = usePlugin(live, "after");

        System.out.println("different runtime classes: "
                + (first != second));
    }
}
~~~

Notes:

- Each `usePlugin` call creates its own loader and closes it via try-with-resources.
- The resource stream is closed **before** closing the loader.
- The copy/replace step happens **between** the two calls, when loader v1 is already closed.
- Both `Class<?>` references are kept for identity comparison: this exercise **does not attempt to demonstrate class unloading**.
- The host classpath **must not** contain `demo.Greeter`; if the parent can see that class, parent-first delegation may return the parent's class.

### Compiling and Running on Linux/macOS

From the `example` directory:

~~~bash
mkdir -p out/v1/demo out/v2/demo out/host dist

javac --release 17 -d out/v1 src/v1/demo/Greeter.java
javac --release 17 -d out/v2 src/v2/demo/Greeter.java
javac --release 17 -d out/host src/host/ReloadDemo.java

printf 'config one\n' > out/v1/demo/config.txt
printf 'config two\n' > out/v2/demo/config.txt

jar --create --file dist/v1.jar -C out/v1 .
jar --create --file dist/v2.jar -C out/v2 .

cp dist/v1.jar dist/live.jar

java -cp out/host ReloadDemo dist/live.jar dist/v2.jar
~~~

### Compiling and Running on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\v1\demo, out\v2\demo, out\host, dist | Out-Null

javac --release 17 -d out\v1 src\v1\demo\Greeter.java
javac --release 17 -d out\v2 src\v2\demo\Greeter.java
javac --release 17 -d out\host src\host\ReloadDemo.java

Set-Content -Path out\v1\demo\config.txt -Value 'config one' -Encoding Ascii
Set-Content -Path out\v2\demo\config.txt -Value 'config two' -Encoding Ascii

jar --create --file dist\v1.jar -C out\v1 .
jar --create --file dist\v2.jar -C out\v2 .

Copy-Item dist\v1.jar dist\live.jar
java -cp out\host ReloadDemo dist\live.jar dist\v2.jar
~~~

Run inside the `example` directory with JDK 17 or later. The config resources contain ASCII text, so reading them as UTF-8 returns the same content on both operating systems.

### Verified Exact Stdout

~~~text
before defined by child: true
before version: v1
before config: config one
jar replaced
after defined by child: true
after version: v2
after config: config two
different runtime classes: true
~~~

This exercise was compiled with `javac --release 17` and actually run on OpenJDK 21 (Linux) with the same file layout. This proves that the new loader sees JAR v2 and the v2 JAR resource. **It does not prove that on every Windows installation all file locks are released**, because the file may still be used by another process, scanner, or library.

### Output Explanation

- `before defined by child: true`: L1 actually defined the v1 class.
- `before version: v1` and `before config: config one`: the first class/resource came from the live file containing v1.
- `jar replaced`: the `Files.copy` operation succeeded in the test environment after the first loader closed.
- `after defined by child: true`: L2 defined a new class rather than receiving it from the parent.
- `after version: v2` and `after config: config two`: the class/resource switched to the new JAR.
- `different runtime classes: true`: L1 and L2 are two different defining loaders, so the `Class<?>` objects do not match.

The example intentionally returns `Class<?>` v1 from `usePlugin` for comparison. In a real system where unloading is desired, **do not hold the v1 reference indefinitely**.

## 8. JarURLConnection and Caching: Another Source of JAR Retention

If code obtains a URL and directly opens a stream:

~~~java
URL resourceUrl = loader.getResource("demo/config.txt");
if (resourceUrl == null) {
    throw new IllegalStateException("Missing resource");
}
try (InputStream in = resourceUrl.openStream()) {
    // Read resource.
}
~~~

This is an illustrative snippet assuming an existing loader. A JAR entry URL may look like:

~~~text
jar:file:/path/to/plugin.jar!/demo/config.txt
~~~

The `jar:` protocol has `JarURLConnection`, a subclass of `URLConnection`. The `useCaches` property of `URLConnection` enables caching when `true`, and the default is typically enabled. An independent connection/cache can retain resources even after you have called `close()` on your own loader.

If you **manage a JarURLConnection yourself** and do not want to use caching for that connection:

~~~java
URL jarEntry = new URL(
        "jar:file:/path/to/plugin.jar!/demo/config.txt");
JarURLConnection connection =
        (JarURLConnection) jarEntry.openConnection();
connection.setUseCaches(false);

try (InputStream in = connection.getInputStream()) {
    // Read bytes.
}
~~~

This is **illustrative**; the URL string must be constructed validly for the actual system path. Call `setUseCaches(false)` **before** starting to use the connection. It affects that specific connection only and **does not** promise to close all other caches/handles across the entire JVM. Do not abuse changing the JVM-wide default cache setting to "fix" a JAR lock without understanding the impact.

If code opens a `JarFile` via its constructor, manage ownership explicitly with try-with-resources; if a connection or library uses a shared cache, follow the API contract properly and avoid recklessly closing a shared JarFile.

## 9. What Keeps the v1 Loader and Classes in Memory

Even after releasing the JAR handle, the old loader can remain alive due to **strong references**. Common sources:

| Reference Source | Symptom | How to Handle |
| --- | --- | --- |
| Host static map / registry | `Map<String,Object>` still holds plugin instances | Unregister/remove by version |
| `Class<?>` or reflection Method/Constructor cache | Host retains plugin class metadata long-term | Clear cache according to lifecycle |
| Runnable/executor | Plugin tasks remain queued or running | Cancel/shutdown and wait for completion |
| Plugin-created thread | Live thread holds Runnable/context loader | Shutdown/join per contract |
| TCCL on thread pool | Context loader is still the retired child | Restore TCCL in `finally` |
| ThreadLocal | Long-lived thread retains plugin object/class | Remove ThreadLocal from the right thread |
| Listener/event bus | Plugin registered a callback on a host singleton | Unregister on stop |
| MBean/JMX registry | MBean points to an implementation class | Unregister deliberately |
| Service/driver registry | Provider/driver/handler retained in registry | Clean up via the corresponding registration API |
| Resource/stream/archive | InputStream/JarFile/ZipFile still open | Close via the proper owner |
| Shutdown hook | Hook retains plugin object or loader | Remove when allowed and valid |

### TCCL Should Be Restored

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Call code/framework that needs to look up resources or SPI via TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is an illustrative snippet. With a thread pool, a thread can outlive a plugin by a long time; forgetting to restore the context loader will retain a reference to the old plugin version. However, restoring TCCL alone does not resolve every reference from threads/tasks/registries.

Class unloading depends on the JVM/GC and reference boundaries. `WeakReference<ClassLoader>` can help in tests to observe whether a loader can be collected, but **do not put hard timing assertions** requiring GC to unload within a few milliseconds. Heap dumps and class unloading logs help diagnose leaks.

## 10. When to Use Versioned JARs Instead of Overwriting live.jar

If you have the ability to redesign the system, versioned filenames are usually the better choice:

~~~text
plugins/
    service-1.0.0.jar
    service-1.1.0.jar
    service-1.2.0.jar
~~~

Benefits:

- No need to overwrite a file currently being used by the old loader.
- Old and new version loaders can run side by side while shifting traffic.
- Easy rollback because the v1 file has not been modified.
- Easy to log the exact version currently serving requests.
- Cleanup can happen after the associated loaders are closed and no handles remain.

If **atomic deployment** is required, download/copy the new version to a temporary file on the same filesystem, verify its checksum/version, and then rename it to the **final versioned** name before creating the new loader. Do not treat a single `Files.copy(..., REPLACE_EXISTING)` directly onto a live file as a complete rollout process with rollback/atomicity. Rename/atomic move mechanisms and file permissions depend on the OS/filesystem.

When the application handles multiple requests, use synchronized routing/registries to switch to loader v2. Do not close L1 immediately upon updating the registry if v1 requests are still active.

## 11. Diagnosing Files Still Held After Close

A practical checklist:

1. **Does the host launch command place the plugin JAR on the application classpath?** If so, the parent may have opened the JAR; closing the child does not close the parent.
2. **Are two URLClassLoaders pointing to the same JAR?** Closing one loader does not release the other loader's handle.
3. **Is there any independent reader?** Look for `new JarFile`, `ZipFile`, `getResourceAsStream`, `openStream`, or framework scanners.
4. **Is JarURLConnection caching active?** Check ownership and `useCaches`; do not assume every URL stream is managed by URLClassLoader.
5. **Is an IOException being ignored during close?** Log the cause and suppressed exceptions.
6. **Are requests/threads loading classes/resources during close?** Coordinate quiescing first rather than relying on undefined concurrent close behavior.
7. **Is a file watcher, antivirus, IDE, scanner, or another process touching the file?** Check with OS handle inspection tools.
8. **Is the current OS Windows or Linux?** They differ in how rename/unlink behaves when a file is open; "being able to delete" does not guarantee the FD is closed.
9. **Does the JAR belong to a custom/framework class loader?** The URLClassLoader API does not represent every nested-JAR loader.
10. **Is memory growing while file handles are not?** Look for strong references retaining the ClassLoader; do not treat that as the same kind of leak.

Tools like Resource Monitor/Process Explorer on Windows or `lsof` on Linux help identify which process actually holds handles. They do not replace Java APIs, but they help distinguish a loader bug from another process's lock. Conversely, class unload logs not reporting v1 classes as collected **do not** by themselves prove a JAR handle is still open.

### Typical Misconceptions

**"Closing URLClassLoader means the plugin has been unloaded."** No: closing a loader does not destroy objects/classes; the JVM only unloads when reachability/GC conditions are met.

**"Just call System.gc() and the file won't be locked."** No: GC is not a handle-release API; close the proper owner.

**"Modifying the JAR in place will update the bytecode of already loaded classes."** No: create a new class loader to get new runtime class definitions.

**"Streams opened by the loader can be left open because closing the loader will close them."** Even though URLClassLoader has a contract for `getResourceAsStream`, good design still closes streams immediately after reading.

**"Successfully deleting a file on Linux proves there is no leak."** No: a descriptor to the old content can still remain alive after unlinking.

**"Just close the loader and replace the JAR and it will definitely work on all Windows machines."** No: the file may still be held by another process/connection, or lack permissions.

**"Just creating a new loader per request is a simple reload."** No: it opens more handles, multiplies class namespaces, and increases memory/CPU usage. Use one loader per coordinated **plugin version/lifecycle**.

## 12. Production Checklist and Review Questions

Pre-deployment checklist:

- Reloadable plugin JARs are not on the long-lived application classpath.
- Each loader per version has a clear owner and lifecycle.
- A stop hook halts requests, executors, threads, callbacks, and registrations.
- No concurrent class loading occurs when `close()` is called.
- Every independent stream/JarFile/ZipFile uses try-with-resources or equivalent cleanup.
- `URLClassLoader.close()` is called, and `IOException` is not ignored.
- Old version files are cleaned up only after no owner holds a handle.
- New versions use a **new loader**, never reusing a closed loader.
- Shared APIs/interfaces are defined consistently by the parent loader.
- Caches, TCCL, ThreadLocals, and registries are cleaned up when the plugin retires.
- Logging/monitoring is in place for file handles, class loaders, and class unloading as needed.
- A versioned JAR, health-check, and rollback strategy is established.
- The workflow is tested on the target deployment OS/filesystem.

**Question 1.** Does `URLClassLoader.close()` guarantee unloading all defined classes?

**Answer:** No. It closes the loader for loading new classes/resources and closes files it opened per its contract; class unloading depends on the JVM/GC and references.

**Question 2.** Why can a JAR still be locked on Windows after closing a URLClassLoader?

**Answer:** A parent/sibling loader, JarFile/ZipFile, JarURLConnection cache, or another process may still hold a file handle; you need to find the actual owner.

**Question 3.** Why must a new URLClassLoader be created after replacing a JAR?

**Answer:** Classes already defined by the old loader do not automatically update their bytecode; a new loader allows defining the same binary name in a different namespace.

**Question 4.** Should `System.gc()` be used to guarantee file deletion?

**Answer:** No. Close streams/JARs/loaders using resource management APIs; GC provides no timing guarantees and does not replace `close()`.

**Question 5.** Why should JARs be deployed under separate versioned names?

**Answer:** To avoid overwriting a file currently in use by the old version, simplify traffic shifting and rollback, and delete the old version only after its lifecycle ends.

**Question 6.** What if the URLClassLoader is closed, but the host still holds a `Class<?>` from plugin v1?

**Answer:** The JAR handle may have been closed, but the v1 class is still referenced, so you cannot conclude it has been unloaded. The two states must be checked separately.

## Official References

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `close()`, `getResourceAsStream`, and concurrency behavior.
- [Java SE 21 — JarURLConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/JarURLConnection.html): `jar:` protocol and archive connections.
- [Java SE 21 — URLConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLConnection.html): `setUseCaches(false)` and cache policy.
- [Java SE 21 — JarFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): reading and closing JARs explicitly.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): class loading lifecycle.
- [JVMS Java SE 21 §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class definition, binary names, and defining loaders.
