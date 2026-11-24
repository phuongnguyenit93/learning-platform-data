# Limits of Class Loader Isolation on Process State and Permissions

## 1. What Can a Class Loader Isolate?

In a Java system that supports plugins or dynamic library loading, an application can use multiple `ClassLoader` instances to load different versions of libraries. Each class in the JVM is identified by its **binary name and defining class loader**. Thus, two different loaders can define two classes with the same name, such as `com.vendor.JsonCodec`, without those two classes sharing the same identity.

This mechanism solves a practical set of problems:

- Plugin A can use a different version of the `codec` library than plugin B.
- A plugin's internal classes do not need to share a namespace with the host's internal classes.
- When designed properly, the host can share only a stable SPI API while implementations use private dependencies.
- A new version of a plugin can be loaded with another loader and references to the old loader dropped when the plugin's lifecycle ends.

However, **a classloader does not create a new process, a new OS memory space, or a permission sandbox**. All Java code running inside the same JVM still shares many critical resources. A classloader is strictly a boundary for identifying and locating classes; it does not by itself control permissions to read files, create threads, make network calls, read environment variables, or halt the JVM.

## 2. Boundary Model: Different Namespaces, Still One Process

```text
                       One JVM Process
+------------------------------------------------------------+
| Heap, GC, system properties, System.out, process resources |
| Native libraries, threads, sockets, files, environment     |
|                                                            |
|  Host / parent classloader                                 |
|    com.example.api.Plugin       <-- shared API             |
|                                                            |
|  Plugin A loader              Plugin B loader              |
|    com.vendor.Codec v1          com.vendor.Codec v2        |
|    com.example.a.PluginA        com.example.b.PluginB      |
|                                                            |
|  Separate class namespace != separate memory/process/sec   |
+------------------------------------------------------------+
```

In the diagram, the two `Codec` copies can have the same name yet different class identities. Even so, both A and B are still code running inside one JVM process. If one plugin calls `System.setProperty(...)` or mutates an object shared by the host, the other plugin can observe that change.

A common misconception is "two different classloaders mean completely independent static state." A more accurate statement is: **static fields belong to a runtime class identified by both class name and defining loader**. If two loaders genuinely define two separate copies of a class, each copy has its own static fields. However, the static state of classes loaded by the parent/shared loader remains shared. Moreover, static variables are only one part of process state.

## 3. Static State: Separable in Private Classes, Not in Shared Classes

Suppose both plugin A and plugin B have a class named `plugin.Counter`, and each class is defined by its own loader. When two loaders genuinely create two distinct runtime classes, the two `Counter.value` fields are also separate.

Conversely:

```java
// This class is defined by the host/parent loader:
package com.example.host;

public final class SharedRegistry {
    public static final java.util.Map<String, String> VALUES =
            new java.util.concurrent.ConcurrentHashMap<>();

    private SharedRegistry() {}
}
```

If plugins A and B both see `SharedRegistry` from the parent loader, both operate on **the same map**. `ConcurrentHashMap` provides thread safety for concurrent access at the collection level; it does not enforce authorization or prevent one plugin from deleting/modifying another plugin's entries.

Common forms of shared state:

| State source | Automatically isolated per classloader? | Why |
| --- | --- | --- |
| Static fields on classes defined by each child loader | Yes, between two genuinely distinct runtime classes | Runtime class identity comprises class name and defining loader |
| Static fields on classes in the parent loader | No | Plugins use the same class defined by the parent |
| `System.getProperties()` | No | These are JVM-wide properties |
| `System.out` / `System.err` | No | Standard streams of the process |
| Heap objects passed by the host to a plugin | No | Same object reference |
| Files, sockets, databases, out-of-process caches | No | Permissions and connections depend on OS and configuration |
| Threads created by a plugin | No | Threads belong to the process; they can outlive the plugin lifecycle |
| Thread context classloader | Not automatically isolated | A thread's context loader can retain references to a plugin loader |

Even when dependencies are completely isolated, a plugin can still corrupt data shared by the host via APIs, or exhaust the JVM's memory/CPU.

## 4. Java 17+ Example: Two Classloaders, Two Static Counters, One System Property

The following example creates one plugin JAR containing `demo.plugin.Counter`. The host loads **the same JAR through two separate URLClassLoader instances**, using the platform classloader as their parent so the plugin class is not preloaded by the parent/application loader. It demonstrates two things: static fields of classes defined in each loader are separate, whereas `System` properties are shared.

Directory structure:

```text
demo/
  plugin/demo/plugin/Counter.java
  host/Host.java
```

`plugin/demo/plugin/Counter.java`:

```java
package demo.plugin;

public final class Counter {
    private static int count;

    public static int increment() {
        return ++count;
    }

    public static String loaderName() {
        return String.valueOf(Counter.class.getClassLoader());
    }
}
```

`host/Host.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Host {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin.jar").toAbsolutePath().toUri().toURL();
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loaderA =
                     new URLClassLoader(new URL[] {pluginUrl}, parent);
             URLClassLoader loaderB =
                     new URLClassLoader(new URL[] {pluginUrl}, parent)) {

            Class<?> classA = Class.forName(
                    "demo.plugin.Counter", true, loaderA);
            Class<?> classB = Class.forName(
                    "demo.plugin.Counter", true, loaderB);

            System.out.println("Same runtime class: " + (classA == classB));
            System.out.println("A counter: "
                    + classA.getMethod("increment").invoke(null));
            System.out.println("A counter: "
                    + classA.getMethod("increment").invoke(null));
            System.out.println("B counter: "
                    + classB.getMethod("increment").invoke(null));

            System.setProperty("demo.shared", "written-by-A");
            System.out.println("Shared property: "
                    + System.getProperty("demo.shared"));
        } finally {
            System.clearProperty("demo.shared");
        }
    }
}
```

From the `demo` directory, run in a bash shell (with `javac`, `jar`, `java`):

```bash
mkdir -p out/plugin out/host
javac -d out/plugin plugin/demo/plugin/Counter.java
javac -d out/host host/Host.java
jar --create --file plugin.jar -C out/plugin .
java -cp out/host Host
```

Output:

```text
Same runtime class: false
A counter: 1
A counter: 2
B counter: 1
Shared property: written-by-A
```

**Why?** `loaderA` and `loaderB` see the same bytecode, yet each loader defines `demo.plugin.Counter` itself, so `classA != classB` and the static counters are separate. However, `System.setProperty` writes to a JVM-wide properties table, so the value is readable within the same process regardless of which loader performed the operation.

In the example, the host itself calls `System.setProperty` to illustrate a shared resource. If a plugin invokes this API, the effect is also JVM-wide; classloaders cannot block it. `URLClassLoader.close()` closes access to JAR resources opened by the loader, yet **does not delete loaded classes or guarantee immediate GC**.

### A Note on Parent Delegation

Under the standard parent-first model, if the parent loader has already defined `demo.plugin.Counter`, a load request through a child can return the parent's class itself. In that case `classA == classB` may be `true`, and static fields are not separated. To isolate dependencies, design package boundaries, classpaths, and parent delegation consistently. Do not write a sweeping child-first loader without addressing package sealing, resource loading, protected packages, class identity, and SPI API sharing.

## 5. Process Permissions: Same OS Identity, No Default Sandbox

Every plugin running in the same standard JVM operates with whatever permissions the JVM process already holds. Classloaders do not assign a separate UID, user account, network namespace, or ACL per plugin.

Capabilities that can affect the entire process include:

- **File system:** reading/writing data that the account running the JVM is permitted to access.
- **Networking:** opening connections or sockets if OS/container/network policy permits.
- **Environment/config:** reading environment variables and system properties visible to the process; modifying system properties can affect other code.
- **Processes:** calling APIs to spawn child processes, and in some contexts halting the JVM.
- **CPU, memory, and threads:** causing heavy resource consumption, hanging, or impacting GC for other plugins.
- **Native code:** calling JNI/FFM/native libraries depending on runtime capabilities and configuration; native code can corrupt memory for the entire process.

The Java Security Manager was once used as part of permission control in some legacy systems, yet it is not a sandbox solution you can rely on for modern Java. The Security Manager was permanently disabled in JDK 24; in Java 17 it was marked deprecated for removal. Do not design new plugin security around attaching a Security Manager per classloader.

**Consequence:** for untrusted plugins, isolate at the process/OS/container/VM level with appropriate privileges and resource limits. A dedicated `URLClassLoader` does not replace those mechanisms.

## 6. State-Sharing Channels to Watch Out For

### A. Host APIs or Singletons

Plugins often need references to host-provided APIs, such as `PluginContext` and `Logger` interfaces. If the host hands a plugin a mutable object containing database or registry access, the plugin can manipulate it even though the plugin's classes were loaded separately.

To limit risk with **trusted plugins**, you can design narrow APIs, immutable snapshots, capability-style interfaces, and boundary validation. However, these are **application-architecture constraints**, not a mechanism preventing malicious Java code in the same process from accessing other APIs.

### B. ThreadLocal and Thread Pools

`ThreadLocal` stores values per **thread**, not per classloader. If the host reuses a thread pool across plugins, uncleaned ThreadLocal data can persist across multiple tasks. Classes loaded by a plugin and objects referenced by threads can prevent the loader from being garbage collected.

Proper ThreadLocal usage typically requires `try/finally`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void process(String id) {
    REQUEST_ID.set(id);
    try {
        doWork();
    } finally {
        REQUEST_ID.remove();
    }
}
```

This is an illustrative snippet placed inside a class that has a `doWork()` method; it is not a standalone program. The static field `REQUEST_ID` belongs to the runtime class that defines it, yet a thread's ThreadLocal data and thread lifetime have a broader reach than closing a URLClassLoader.

### C. Thread Context Classloader (TCCL)

Many frameworks and `ServiceLoader.load(S.class)` use the thread context classloader to locate providers. A plugin can alter `Thread.currentThread().setContextClassLoader(...)`; if not restored, subsequent tasks on the same thread may accidentally use another loader.

Restoration pattern:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    invokePlugin();
} finally {
    thread.setContextClassLoader(old);
}
```

This snippet is placed inside a method where `pluginLoader` and `invokePlugin()` already exist. It helps preserve correctness of the host runtime; it does not turn a classloader into a sandbox.

### D. Shutdown Hooks, Listeners, Caches, and Native Libraries

A plugin can register shutdown hooks, listeners, JMX MBeans, schedulers, executors, drivers, or caches in singletons held by the parent loader. If not unregistered/closed, those references keep plugin classes/loaders alive, causing memory leaks and interfering with reload operations. JNI/native libraries also carry JVM-wide crash or conflict risks.

## 7. Closing a Classloader Does Not Mean Stopping a Plugin

`URLClassLoader.close()` primarily releases resources the loader opened to load classes/resources; it is not a command to unload classes or stop all plugin threads.

To remove a plugin cleanly, the host needs a lifecycle contract:

1. Stop accepting new requests for the plugin.
2. Wait for in-flight work to finish or cancel per timeout/policy.
3. Call the provider's `close()`/`stop()`; shut down executors, file handles, and sockets.
4. Unregister listeners, shutdown hooks, timers, drivers, and host registry entries.
5. Restore TCCL, clear ThreadLocals, and drop strong references in the host.
6. Close the classloader, drop references, and observe whether the JVM can reclaim the loader.

Dropping references creates the **conditions** for the garbage collector to reclaim the classloader and class metadata; it does not guarantee GC timing or immediate unloading. If a static reference from a shared parent class holds onto a plugin object, the loader can still be kept alive.

## 8. When Is a Classloader Enough, and When Is a Separate Process Needed?

| Goal | Dedicated classloader | Separate process/container |
| --- | --- | --- |
| Using two versions of the same library | Usually suitable when the dependency tree is controlled | Possible, though higher overhead |
| Avoiding class name conflicts | Suitable with a properly designed loader graph | Yes |
| Separating static fields belonging to plugin-private classes | Yes, if truly defining separate classes | Yes, due to separate heaps |
| Preventing plugins from modifying shared `System` properties | No | Yes, since each JVM has its own properties |
| Preventing plugins from overusing CPU/memory | Provides no quotas | Quotas can be configured at OS/container level |
| Restricting files/network for untrusted plugins | No | OS/container/network permissions can be enforced |
| Preventing a plugin's native crash from taking down the host | No | Fault isolation at process level, depending on environment |
| Deterministically unloading a plugin | No | Stopping a process is a clearer boundary |
| Trusted plugins with differing dependency versions | Usually a sensible choice | May be unnecessary |

Note: a separate process also **does not automatically guarantee safety**. If run as the same user with the same file read permissions, same mounts, and open network, the process can still access many of the host's resources. Combine user identity, filesystem permissions, resource limits, seccomp/AppArmor/SELinux, or network policies according to the deployment environment.

## 9. Two-Tier Plugin Architecture

A practical design can support two modes:

**Trusted plugins requiring direct invocation performance:**

```text
Host JVM
  ├── Shared SPI API (parent loader)
  ├── Plugin A loader + private dependencies
  └── Plugin B loader + private dependencies
```

Here the goal is dependency isolation, controlled reload, and lifecycle governance. Accept only trusted JARs with controlled release provenance.

**Untrusted plugins or plugins requiring fault/permission limits:**

```text
Host JVM
    |
    +---- IPC (HTTP/gRPC/stdin-stdout/message queue)
    |
Plugin process/container
    +---- restricted OS user
    +---- filesystem/network permissions
    +---- CPU/memory limits
```

The application must validate/inspect IPC messages, enforce timeouts, bound inputs and payload sizes, and handle state when a plugin crashes. A process boundary enables clearer permission and fault boundaries while adding operational and communication overhead.

## 10. Common Design Mistakes

| Misconception | Real issue | How to fix |
| --- | --- | --- |
| "Each plugin loader is a sandbox" | Code still runs with JVM permissions | Use OS/process isolation for untrusted plugins |
| "Statics are always separate per plugin" | Classes in parent/shared loaders share statics | Check the defining classloader of each class |
| "Closing a loader means unloading" | Threads, caches, and registries hold references | Design stop/close and clean up references |
| "One plugin cannot affect another plugin" | Heap, process properties, resources, and services are shared | Restrict shared APIs; use separate processes if needed |
| "TCCL belongs privately to a plugin" | TCCL is per-thread state | Restore TCCL using finally |
| "Child-first definitely isolates everything" | Duplicate APIs/class identity, package sealing, framework conflicts | Design parent delegation and API boundaries |
| "A separate process is completely safe" | The process may still have the same OS permissions | Configure permissions and resource quotas |

## 11. Checklist for Deploying Safe Dependency Isolation

- [ ] Clearly state whether the goal is **isolating dependency namespaces** or **isolating untrusted execution**.
- [ ] Keep shared SPI APIs in the parent loader and verify `Class<?> ` identity between host and providers.
- [ ] Control versions/dependencies loaded through each child loader.
- [ ] Identify shared mutable objects, singletons, properties, thread pools, and registries visible to plugins.
- [ ] Implement a `start/stop/close` lifecycle; clean up ThreadLocal, TCCL, listeners, and executors.
- [ ] Do not rely on classloaders to enforce file/network/process permissions.
- [ ] When plugins are untrusted, run them in processes/containers with least-privilege OS permissions and appropriate quotas.
- [ ] Test two dependency versions with identical names, test unload/reload, and monitor for leaks.
- [ ] Inspect the actual packaged artifacts, especially when shading/relocating or including native libraries.

**Conclusion:** a classloader is an essential tool for managing **class identity and dependency isolation**. It does not separate heap, threads, system properties, OS permissions, or native faults of a plugin from the host JVM. Whenever the requirement involves security, resource limits, or strong fault tolerance, push the isolation boundary down to the process/OS/container level and operate it as a separate component.