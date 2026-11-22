# Replacing a Plugin Version with a New Loader in Java

> **Java Core → ClassLoader → Plugin Architecture.** When a plugin is updated from version V1 to V2, the right way to obtain **new runtime classes** is usually to create a **new-generation class loader**, load and verify the new version, switch the request flow over to the new generation, and then stop and release the old generation. Do not call `defineClass` a second time in the old loader, do not expect `URLClassLoader.close()` to unload all classes on its own, and do not close the loader before tasks currently running with the old plugin have completed.

## 1. Short Answer

Recommended workflow:

~~~text
     Host + Shared API (lives across multiple updates)
                      |
                      v
                Plugin Registry
                      |
       currently active version: Generation V1
                      |
   (1) prepare V2 in a NEW URLClassLoader
   (2) verify artifact / load / instantiate / health check
   (3) atomic routing cutover: active = V2
   (4) accept no new requests for V1
   (5) drain in-flight V1 / stop timers / unregister callbacks
   (6) close V1 instances and V1 loader-owned resources
   (7) drop strong references to V1
                      |
                      v
            Generation V2 serving
~~~

**Key invariants:**

1. Every runtime class is identified by **(binary name, defining loader)**. The class `plugin.impl.Handler` defined by loader V1 and `plugin.impl.Handler` defined by loader V2 are **two different runtime types** even though their names are identical.
2. The **shared API types** used for host↔plugin communication must be defined by **a common loader** (usually host/parent), if you want to cast and invoke interfaces normally.
3. Do not modify a JAR on disk and expect the JVM to automatically use the new bytecode for an existing `Class<?>`. The JVM does not treat a file change as a command to redefine a class.
4. The time of **publishing V2** and the time of **retiring V1** are different. If V1 requests are currently running, you must not close V1 resources/loader without coordination.
5. `URLClassLoader.close()` releases the file/JAR handles belonging to the loader; classes and created instances **may still work** if references to them are kept. There is no guaranteed deadline for class unloading.
6. If preparing V2 fails, **keep V1 as active**; if V2 has already been published but V1 cleanup fails, that is a **retirement failure**, and does not mean V2 was not published.

## 2. Why Replace the Loader Instead of Calling `loadClass` Again?

With a normal `ClassLoader`, loading a binary name multiple times with the same loader must keep the **same runtime `Class<?>`**. For example:

~~~java
Class<?> first = loader.loadClass("plugin.impl.Handler");
Class<?> again = loader.loadClass("plugin.impl.Handler");

System.out.println(first == again); // true if both succeed
~~~

This is a **snippet** that requires the `loader` variable. Rebuilding the JAR and overwriting the `Handler.class` file does not make `again` become a new runtime class, because the loader has already loaded that name.

Attempting to call `defineClass` a second time with the same binary name **in the same defining loader** will be rejected (typically with a `LinkageError`). `resolveClass` only requests linking; it does not reset state or the static initializer. `Class.forName` is not a reload API either.

Conversely:

~~~java
Class<?> oldType = loaderV1.loadClass("plugin.impl.Handler");
Class<?> newType = loaderV2.loadClass("plugin.impl.Handler");

System.out.println(oldType.getName().equals(newType.getName())); // true
System.out.println(oldType == newType);                            // false
~~~

**The last line is only guaranteed to be false if each loader actually defines its own copy of the class.** If both loaders delegate the name `plugin.impl.Handler` to the parent, both may return the same `Class<?>`. When designing a hot swap, you must know the actual **defining loader**, not merely create two loader objects with different names.

### 2.1. Distinguishing Versioned Runtime Classes from JVM Instrumentation

Java agents/instrumentation provide `redefineClasses`/`retransformClasses` within specified constraints, mainly to replace method bytecode on already loaded classes. That is a **different** mechanism and is not a general way to update a plugin with changes to APIs, constructors, fields, module/package layout, or dependencies.

For typical application plugin architectures, **a new loader for a new generation** provides clearer isolation of static fields, dependency graphs, and class identity. However, a new loader by itself does **not** perform data migration, routing switches, cleanup, or guarantee thread safety.

## 3. Host ↔ Plugin Boundary: Keeping a Single Shared Contract

Suppose the host knows the interface:

~~~java
package api;

public interface Plugin extends AutoCloseable {
    String version();

    @Override
    default void close() { }
}
~~~

**File `api/Plugin.java`** on Java 17+; in production, `close()` may need to release resources and have an explicit error contract. This `Plugin` interface must be loaded by the **shared/host loader** that both the host and the plugin use.

Architecture:

~~~text
                          Host loader
                    defines api.Plugin
                         /         \
                        /           \
              Plugin loader V1    Plugin loader V2
              defines:             defines:
              plugin.impl.Versioned plugin.impl.Versioned
              libraries V1         libraries V2

           Host's Plugin.class == V1's Plugin.class
           Host's Plugin.class == V2's Plugin.class

           Versioned.class in V1 != Versioned.class in V2
~~~

Rules:

- **Shared contracts:** interfaces, DTOs, annotations, and exceptions that actually cross the boundary should reside in the host/shared loader with explicit versioning.
- **Implementation and private dependencies:** reside in each plugin generation's loader; versions may differ between V1 and V2.
- **Do not repackage the host's API into the plugin JAR** in a way that causes a child-first loader to define `api.Plugin` itself, if the host needs to cast the plugin to `api.Plugin`.
- **Do not arbitrarily share objects of a private V1 class with V2:** V1's `plugin.impl.Versioned` cannot be cast to the same-named `Versioned` in V2.
- If communication between generations is needed, use **shared types**, stable primitives, schemas/messages, or explicitly versioned serialization; do not use a Java class name as proof of compatibility.

### 3.1. Parent-First and Implementation Versions

By default, `URLClassLoader` searches the **parent first** and only then the child's URLs. If `plugin.impl.Versioned` is accidentally included on the host classpath as well, loaders V1 and V2 may return the **class already defined by the parent**: you appear to have swapped, yet old code still runs.

For a simple architecture:

- The host classpath contains only the **shared API + host runtime**.
- The plugin implementation JAR is placed only in the URLs of the generation loader.
- The parent of the plugin loader is the defining loader of the shared API.
- If child-first delegation is needed to isolate different library versions, it must be scoped **by package**; never apply child-first across `java.*` or the shared API.

Always verify:

~~~java
System.out.println(implementationType.getClassLoader());
System.out.println(Plugin.class.isAssignableFrom(implementationType));
System.out.println(implementationType.getModule());
~~~

This is a snippet using an existing `implementationType`. A class with the same name but a different loader still has a different runtime identity.

## 4. Java 17+ Hands-On: Hot Swapping V1 → V2 with a New Loader

The experiment consists of one shared API, two JARs containing the **same binary name** whose method returns two different versions, and a host using `ReentrantReadWriteLock` to ensure **synchronous requests** do not execute while the old generation is being replaced/closed.

### 4.1. Directory Structure

~~~text
plugin-swap-lab/
├── src/
│   ├── api/api/Plugin.java
│   ├── v1/plugin/impl/Versioned.java
│   ├── v2/plugin/impl/Versioned.java
│   └── host/HostMain.java
└── build/                         (generated when running commands)
    ├── api/
    ├── v1/
    ├── v2/
    ├── host/
    ├── v1.jar
    └── v2.jar
~~~

File **`src/api/api/Plugin.java`**:

~~~java
package api;

public interface Plugin extends AutoCloseable {
    String version();

    @Override
    default void close() { }
}
~~~

File **`src/v1/plugin/impl/Versioned.java`**:

~~~java
package plugin.impl;

import api.Plugin;

public final class Versioned implements Plugin {
    @Override
    public String version() {
        return "v1";
    }
}
~~~

File **`src/v2/plugin/impl/Versioned.java`**:

~~~java
package plugin.impl;

import api.Plugin;

public final class Versioned implements Plugin {
    @Override
    public String version() {
        return "v2";
    }
}
~~~

These are **two source files located in two separate directory trees**, having the **same package and class name** and **different implementations**. They must be compiled into **two independent JARs**, not into the same output directory.

### 4.2. Host Managing Generations and Switching Routing

File **`src/host/HostMain.java`**:

~~~java
import api.Plugin;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class HostMain {

    static final class Generation implements AutoCloseable {
        final URLClassLoader loader;
        final Plugin plugin;
        final Class<?> type;

        private Generation(
                URLClassLoader loader,
                Plugin plugin,
                Class<?> type) {
            this.loader = loader;
            this.plugin = plugin;
            this.type = type;
        }

        static Generation open(Path jar) throws Exception {
            URL url = jar.toAbsolutePath().toUri().toURL();
            URLClassLoader loader = new URLClassLoader(
                new URL[] {url},
                Plugin.class.getClassLoader());

            try {
                Class<?> type =
                    loader.loadClass("plugin.impl.Versioned");
                Plugin instance = Plugin.class.cast(
                    type.getDeclaredConstructor().newInstance());
                return new Generation(loader, instance, type);
            } catch (Exception | LinkageError failure) {
                try {
                    loader.close();
                } catch (IOException closeError) {
                    failure.addSuppressed(closeError);
                }
                throw failure;
            }
        }

        @Override
        public void close() throws Exception {
            // Close the plugin first, then close the loader's file/JAR handles.
            // try-with-resources preserves suppressed exceptions if both fail.
            try (URLClassLoader closing = loader) {
                plugin.close();
            }
        }
    }

    static final class Registry implements AutoCloseable {
        private final ReentrantReadWriteLock lock =
                new ReentrantReadWriteLock(true);
        private Generation active;

        Registry(Generation initial) {
            active = initial;
        }

        String request() {
            lock.readLock().lock();
            try {
                return active.plugin.version();
            } finally {
                lock.readLock().unlock();
            }
        }

        Class<?> activeType() {
            lock.readLock().lock();
            try {
                return active.type;
            } finally {
                lock.readLock().unlock();
            }
        }

        void replace(Path newJar) throws Exception {
            // PREPARE: done outside the write lock so V1 requests can keep running.
            Generation prepared = Generation.open(newJar);

            Generation previous;
            lock.writeLock().lock();
            try {
                previous = active;
                active = prepared;  // CUTOVER
            } finally {
                lock.writeLock().unlock();
            }

            // Once the write lock is acquired, all old request() calls under
            // the read lock have completed; V1 can now be retired.
            if (previous != null) {
                previous.close();
            }
        }

        @Override
        public void close() throws Exception {
            Generation previous;
            lock.writeLock().lock();
            try {
                previous = active;
                active = null;
            } finally {
                lock.writeLock().unlock();
            }
            if (previous != null) {
                previous.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (Registry registry = new Registry(
                Generation.open(Path.of("build/v1.jar")))) {
            Class<?> oldType = registry.activeType();

            System.out.println("before=" + registry.request());
            registry.replace(Path.of("build/v2.jar"));

            Class<?> newType = registry.activeType();
            System.out.println("after=" + registry.request());
            System.out.println("same implementation class="
                    + (oldType == newType));
            System.out.println("shared contract="
                    + (Plugin.class == newType.getInterfaces()[0]));
        }
    }
}
~~~

### 4.3. Compiling and Running

From the `plugin-swap-lab` directory, using a **POSIX shell** (Linux/macOS, Git Bash) and JDK 17 or higher:

~~~bash
mkdir -p build/api build/v1 build/v2 build/host

# The API is on the host classpath.
javac --release 17 -d build/api src/api/api/Plugin.java

# Two implementations with the same name, built separately.
javac --release 17 -cp build/api -d build/v1 \
    src/v1/plugin/impl/Versioned.java
javac --release 17 -cp build/api -d build/v2 \
    src/v2/plugin/impl/Versioned.java

jar --create --file build/v1.jar -C build/v1 .
jar --create --file build/v2.jar -C build/v2 .

# The host MUST NOT put v1.jar/v2.jar on the classpath.
javac --release 17 -cp build/api -d build/host \
    src/host/HostMain.java

java -cp "build/api:build/host" HostMain
~~~

On Windows PowerShell/CMD, replace the classpath separator with `;` and create directories using the appropriate commands. Run command:

~~~powershell
java -cp "build/api;build/host" HostMain
~~~

**Verified stdout with OpenJDK 21 when compiled with `--release 17`:**

~~~text
before=v1
after=v2
same implementation class=false
shared contract=true
~~~

Analysis:

1. `v1.jar` is defined by the V1-generation `URLClassLoader`. `Plugin` is the shared type defined by the host's loader.
2. `Generation.open(v2.jar)` creates **a new URLClassLoader**, looks up the same name `plugin.impl.Versioned`, and instantiates a new object. It does not touch V1's `Class<?>`.
3. `Registry.replace` acquires the write lock only after V2 is successfully prepared, swaps the `active` reference, and then closes V1 resources.
4. `oldType != newType` because the two implementation classes were created by two different defining loaders.
5. `Plugin.class == newType.getInterfaces()[0]` because the V2 implementation uses the exact shared API defined by the parent loader.
6. `oldType` remains a local variable holding V1's `Class<?>`. Therefore, the demo **does not prove unloading** after `close()`; it only demonstrates version swapping and type identity.

**Very important lab limitations:** The code is a **synchronous, single-administrator** example with `request`/`replace`/`close` operations. It does **not yet** handle multiple threads calling `replace`/`close` concurrently, a STOPPING state, plugins spawning their own background jobs, state migration, multithreaded callbacks, or timeout policies. You should not copy it straight into an internet-facing product without the production lifecycle pieces covered in the following sections.

### 4.4. Why Does a Read/Write Lock Resolve the Race in This Example?

In `request()`, the read lock is held for **the entire call into the plugin**. When `replace` acquires the write lock, no old request is still holding the read lock; updating `active` happens at a clear linearization point. Any new request arriving after the write lock will use V2.

This is a trade-off: requests may wait during cutover, and a very long-running V1 request will make the write lock wait for a long time. However, the example never closes the V1 loader mid-flight. In high-throughput systems, you can replace the read/write lock with generation **leases/reference counts** backed by an atomic retirement protocol, but you must never perform a bare reference swap and immediately close.

## 5. Production Lifecycle Design: Prepare → Publish → Retire

A plugin generation should have a minimal **state machine**:

~~~text
NEW
 |
 +-> PREPARING
 |      |
 |      +-> PREPARED -- health-check --> READY
 |      |                            |
 |      |                            v
 |      |                         ACTIVE
 |      |                            |
 |      |                            v
 |      |                         DRAINING
 |      |                            |
 |      |                            v
 |      |                         CLOSED
 |      |
 |      +-> FAILED -> CLEANUP -> CLOSED
 |
 +-> FAILED
~~~

This is not a built-in JDK API; it is a **container/host convention** that needs to be implemented with locks, an immutable generation descriptor, and permitted transitions.

### 5.1. PREPARE — Building V2 Without Breaking V1

A complete preparation step typically includes:

1. Receiving the V2 artifact from a **versioned/immutable path** (for example, a filename containing a hash or version, without overwriting the currently running v1.jar).
2. Verifying source checksum/signature, content trust, minimum Java runtime version, and dependency compatibility.
3. Creating a new `URLClassLoader`/custom loader whose parent is the shared API loader, explicitly maintaining the list of JAR dependencies.
4. Loading V2's entry point; verifying `Plugin.class.isAssignableFrom(implType)` using **runtime Class identity**, not merely comparing names.
5. Initializing the plugin/Dependency Injection context, verifying configuration, required connections, and **health checks** within a rollback-capable resource scope.
6. Ensuring callbacks/resources created during PREPARE have a cleanup mechanism if any step fails.
7. Not publishing V2 to the request router until it reaches the READY state.

**Warning:** `ClassLoader.loadClass(name)` by itself is not required to run the static initializer; however, `new`, `Class.forName(name,true,loader)`, constructors/DI, and certain reflection APIs can trigger `<clinit>` and side effects. Preparing V2 may consume resources or call external services **before cutover**. Therefore, PREPARE must not be advertised as "check-only, with absolutely no side effects."

### 5.2. COMMIT/PUBLISH — The Traffic Switch Point

Once V2 is READY, the host swaps the **active-generation reference** using an atomic operation or a guarded critical section. Every request must follow the convention of using **exactly one generation** throughout the operation. Do not read active at the beginning, read it again mid-request, and accidentally mix V1 classes with V2 state/callbacks.

In the lab in section 4, the write lock serves as an explicit publish point. In a multi-instance/multi-process system, an `AtomicReference` inside a single JVM does **not** perform an atomic cutover across the entire cluster; you need load balancer/routing/version coordination and system-level rollout/rollback policies.

### 5.3. RETIRE — Cleaning Up V1 Once Old Work Is Done

Once V2 is active:

1. Mark V1 as **DRAINING** and stop issuing new handles/requests to V1.
2. Wait for V1 **leases/in-flight requests** to finish or cancel according to timeout/policy; do not force-close while V1 classes/resources are being looked up.
3. Stop plugin-owned timers, executors, watchers, and long-running background jobs.
4. Unregister event listeners, MBeans, HTTP routes, scheduled callbacks, ServiceLoader/DI caches, and any host registries holding V1 objects.
5. Invoke the `close()`/`stop()` lifecycle methods on V1 provider instances in the appropriate resource order.
6. Close V1's `URLClassLoader` and its file/JAR handles, handling `IOException` that may include suppressed exceptions.
7. Drop strong references retaining `Class<?>`, `Method`, plugin objects, the classloader, and `ThreadLocal` values; restore the TCCL to the previous loader.
8. Observe GC/class unloading in an **observable** way; do not rely on `System.gc()` to promise immediate unloading.

**Do not close the parent/shared loader** when V1 ends: the parent continues serving the host and V2.

## 6. Subtle Concurrency Bug: `AtomicReference` Does Not Protect Lifetime by Itself

An error-prone pattern:

~~~java
// PSEUDOCODE: wrong if V1 is retired concurrently.
Generation generation = active.get();
return generation.plugin.call();
~~~

Concurrently, the admin might do:

~~~java
Generation old = active.getAndSet(newGeneration);
old.close();
~~~

Faulty interleaving:

~~~text
Request R                         Admin
  g = active.get() => V1
                                    active = V2
                                    V1.close()
  g.plugin.call()                 <-- calls V1 after it has been closed
~~~

**An atomic swap only protects the reference**; it does not grant a "usage right" (lifetime lease) to a request that has already read V1. If closing V1 shuts down a network client, executor, or resource that the method needs, the request will fail even though V1's `Class<?>` still exists.

There are two design approaches:

- **Read/write lock across the entire synchronous call:** as in the lab; the update acquires the write lock before closing. Simple and easy to prove correct, but long requests hold the read lock and prolong cutover.
- **Protocol-correct generation lease/reference counting:** a request must **acquire a lease atomically with the non-retired state**, and then release it in `finally`. The admin switches active, marks V1 retired, waits until the remaining lease count reaches 0, and only then closes V1. If acquiring V1 fails after V1 has been retired, the request retries to obtain V2. Do not merely call `AtomicInteger.incrementAndGet` after `active.get()` while skipping the state check: a race window still remains.

### 6.1. Conceptually Correct Lease Scheme

~~~text
Request:
  repeat:
      gen = active.get()
      lease = gen.tryAcquireUnlessRetired()
  until lease succeeds

  try:
      return gen.invoke(request)
  finally:
      lease.release()

Admin:
  newGen = prepare(version2)
  oldGen = atomicPublish(newGen)
  oldGen.markRetired()
  wait until oldGen.activeLeases == 0
  oldGen.stopAndClose()
~~~

This is **pseudocode**, not built-in Java methods; `tryAcquireUnlessRetired` and `markRetired` must be designed as an atomic or properly locked state machine. Depending on policy, the admin may also need to prevent a request from acquiring oldGen during the **swap→retire** interval via gating or marking the generation no longer active; otherwise, cutover semantics are delayed even though closing can still be safe while waiting for leases.

**For async tasks:** The lease must remain alive until the `CompletionStage`, callback, coroutine/virtual thread, or background work **actually finishes**, not merely when the method returns a `Future`. If the plugin spawns its own threads outside the request lifecycle, they must be stopped/quiesced separately.

### 6.2. May a Single Request Mix V1 and V2?

You should choose one of two explicit contracts:

- **Request-affinity:** a request acquires a generation at the start and uses that exact generation until completion; callbacks belonging to the request also hold a lease. Suitable for hot reloads without interrupting in-flight requests.
- **Hard cutover/cancel:** the admin blocks new requests, cancels/drains old requests according to a timeout, and then switches versions. Suitable for incompatible protocol/state changes.

Do not write code that calls `PluginService old` and then `PluginService new` within the same transaction without data compatibility rules. The fact that classes can coexist in the JVM does not mean business state can be interchanged.

## 7. Rollback, Failure Modes, and Proper Handling

| Failure Point | System State | Handling |
| --- | --- | --- |
| V2 download/checksum/signature fails | V1 remains ACTIVE | Do not create/publish a new generation |
| V2 fails to load a class/dependency | V1 remains ACTIVE | Close the newly created V2 loader and record the cause |
| V2 constructor/`<clinit>` throws an error | V1 remains ACTIVE if not yet published | Clean up V2 resources already created; do not overwrite V1 |
| V2 health check fails | V1 remains ACTIVE | Mark V2 FAILED, clean up, and keep the V1 router |
| V2 is published, V2 request encounters a business error | V2 ACTIVE | If rolling back, use a **policy to switch back to V1** while V1 is still suitable, or create a fresh generation of a stable release |
| V2 publish succeeds, closing V1 fails | V2 remains ACTIVE | Report RETIREMENT_FAILED, continue cleanup/auditing; **do not pretend cutover did not happen** |
| V1 has long-running requests | V2 may already be ACTIVE | DRAIN with lease/timeout; do not close early |
| JVM crash/process restart | No old runtime state exists | Recover from artifacts + external persisted state; do not rely on the classloader |

### 7.1. Before Publish: Rollback by Discarding V2

The simplest case: PREPARE fails. The host does not swap `active`, so all requests continue using V1. However, "rollback" does not mean undoing every **side effect** that V2's constructor/start has already performed. If V2 writes to a database or sends messages before publish, you need idempotency, transactions, compensating actions, or a dedicated staging policy.

### 7.2. After Publish: Do Not Treat a Close Failure as a Rollback

In the lab, `replace` sets `active=prepared` and then calls `previous.close()`. If `previous.close()` throws an exception, **V2 is still active**. Caller code invoking `replace` may see an exception, so a production API should distinguish at least:

- `PREPARE_FAILED`: not yet published;
- `PUBLISHED_CLEANUP_PENDING`: V2 published, V1 cleanup not yet finished;
- `COMPLETE`: V2 published, V1 retired.

If you use a single boolean success/fail for all three states, operations tooling may accidentally trigger a second retry/cutover and create an additional loader leak.

### 7.3. Practical Version Rollback

If V2 exhibits a business logic bug after receiving traffic:

- When V1 is **still alive/not retired** and schema-compatible, the host can route traffic back to V1 using the corresponding protocol.
- If V1 is **already closed**, do not assume it can still continue loading dependencies; instead, **create a new loader** from the immutable V1 artifact if you want to start V1 again.
- Database schemas/messages/APIs may have already changed for V2; rolling back bytecode without rolling back/migrating state is not necessarily safe.
- Keep versioned artifacts immutable so they can be reproduced. Avoid modifying a JAR directly while a loader is using it (on Windows, renaming/deleting may even fail due to open file handles).

## 8. `URLClassLoader.close()`: Resources Are Closed, Classes Do Not Disappear

The Javadoc describes `URLClassLoader.close()`:

- Prevents the loader from continuing to load **new classes/resources that it finds/defines itself** via the URL path.
- Previously loaded classes/resources **remain accessible**; classes from parent delegation also remain accessible.
- For `jar:`/`file:`, closes the file/JAR handles opened by the loader to the extent supported by the implementation.
- If one thread is loading a class while another thread calls `close()`, **the result of the load is unspecified** — never use this as a shutdown protocol.
- `close()` can throw `IOException`; if multiple errors occur while closing files, subsequent errors may become **suppressed exceptions**.
- Calling `close()` again after it has already been closed has no further effect.

**Do not infer that:**

- `oldInstance.method()` will immediately throw an error because the old class "has been deleted." An already loaded method can still execute; however, if it requests loading another class/resource belonging to the closed loader for the first time, it may fail.
- V1's static state automatically resets.
- Background threads created by V1 automatically stop.
- Caches/static registries/ThreadLocals holding V1 are automatically cleared.
- `URLClassLoader.close()` automatically calls `close()` on each provider, DB connection, HTTP client, executor, watcher, or file stream that **application code** opened directly.
- Class unloading or Metaspace reclamation occurs synchronously right at close time.

For a custom `ClassLoader` that does not extend `URLClassLoader`, **there is no standard `ClassLoader.close()` method**. If the loader itself holds `JarFile` instances, channels, or sockets, you must provide an explicit `AutoCloseable` owner.

### 8.1. Distinguishing Closing a Loader from Class Unloading

V1's runtime classes can only **potentially** be unloaded when no applicable roots/reachable objects remain and the JVM/GC decides to perform unloading. References that retain V1 include:

- A `Class<?>`, `Method`, `Constructor`, or instance cached by the host.
- A V1 provider object in a `ServiceLoader`/DI container registry.
- Running thread stack frames currently executing V1 bytecode.
- `Thread.currentThread().getContextClassLoader()` on a long-lived worker.
- A `ThreadLocal` value/key retaining a plugin class or object.
- A `static` map in the host loader, or a callback/listener/event queue retaining a V1 lambda/object.
- Still-alive executors, schedulers, async tasks, logging appenders, JDBC drivers, and native/JNI references.
- ModuleLayer/ClassLoader references or framework metadata caches.

`System.gc()` is only a hint; it provides no SLA for immediate unloading. On HotSpot with supported logging, you can observe class loading/unloading via `-Xlog:class+load=info,class+unload=info` and use heap dumps/`jcmd` to find the **strong reference path** retaining the loader.

## 9. TCCL, ServiceLoader, and Easily Forgotten Plugin Resources

### 9.1. Context Class Loader (TCCL)

A plugin host may set the TCCL so that a parent-loader framework discovers providers in the plugin loader:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    frameworkCall();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is a **snippet** requiring the `pluginLoader` variable and `frameworkCall` method in your project. If `finally` is omitted, a thread pool worker can retain the V1 loader after swapping to V2, causing **wrong-version provider discovery** and blocking class unloading.

`new Thread(...)` normally inherits the TCCL at **thread construction time**; pre-created pool workers **do not automatically inherit** the submitter's TCCL on each `submit`. Do not use a worker's accidental TCCL as the source for determining the active generation.

### 9.2. ServiceLoader Cache and Provider Identity

`ServiceLoader.load(Service.class)` uses the TCCL at the time the ServiceLoader object is created. `ServiceLoader.load(Service.class, pluginLoader)` uses an explicit loader, which is usually better suited for a plugin manager. `ServiceLoader`'s provider cache does not automatically switch to V2 when you swap the active loader.

- When replacing a generation, create a **new ServiceLoader** with the V2 loader/layer if you need to discover V2 providers.
- `reload()` clears the current ServiceLoader's provider cache; it does **not** turn a loaded V1 class into a V2 class.
- Drop references and unregister V1 providers on the host; `close(pluginLoaderV1)` does not automatically remove all registrations.
- A `ServiceLoader` instance is not thread-safe; do not iterate over and reload it concurrently across multiple threads without synchronization.

### 9.3. ThreadLocal, JDBC, Logging, and Background Jobs

A hot reload bug often does not lie in `loadClass`, but in **resource ownership**:

- Plugin registers a JDBC driver with `DriverManager`, an MBean with the platform server, or a metrics exporter with the host registry — these must be unregistered.
- Plugin creates an executor/scheduler: stop tasks, await termination, handle interrupts, and do not leave V1's TCCL on shared workers.
- Plugin uses `ThreadLocal`: remove entries when the context scope ends; if the value references a V1 object, a long-lived host worker may retain the V1 loader.
- Plugin registers an event listener/callback on a host singleton: unregister/cancel it to avoid retaining V1 lambdas.
- Plugin uses JNI/native libraries: closing the Java loader does not mean the OS library is immediately unloaded; check native lifetime constraints.
- Plugin writes logs through its own appender/file watcher: close it according to the logging library's own lifecycle; do not expect URLClassLoader to manage it.

## 10. Dependency Versioning, Package Split, and Class Identity

A V2 plugin may use a different library version than V1. A new loader isolates dependencies if they are actually defined by each plugin loader. However, this is not always safe:

- If the host parent has already loaded `com.example.lib.Client`, a parent-first child may receive the **host's copy** instead of the plugin's copy. Separate packages or adjust the loader policy if a private version is needed.
- If the host exposes a public API using `com.example.lib.Client` in a method signature, this type is part of the **shared contract** and its defining loader cannot be arbitrarily changed across generations.
- If same-named DTOs are defined separately by V1/V2, direct casting/serialization can fail. Use a shared DTO, a stable schema, common JSON/protobuf/records, or explicit mapping.
- `Package sealing` and signer/certificate consistency still apply when loading signed JARs; arbitrary child-first delegation can collide with package semantics.
- With JPMS, adding `module-info.java` changes resolution as well as `requires/exports/opens`; maintain the proper module graph/layer alongside classloader identity.

### 10.1. Do Not Use `getName()` to Check Compatibility

~~~java
// Wrong: two classes can have the same name yet cannot be cast.
boolean looksEqual =
        oldType.getName().equals(newType.getName());

// Right for runtime identity:
boolean sameType = oldType == newType;

// Right for shared contract:
boolean implementsApi =
        Plugin.class.isAssignableFrom(newType);
~~~

This is a snippet using existing `oldType`/`newType` variables. `isAssignableFrom` helps verify that a class implements the right host interface, but it does not replace checks for binary compatibility, constructors, method behavior, resource ownership, and module permissions.

## 11. ModuleLayer and Plugin Versions in JPMS (Java 9+)

If plugins are deployed as **named modules**, merely creating a new `URLClassLoader` for a JAR is not sufficient to automatically replace a module already resolved in the boot layer. JPMS provides a **ModuleLayer** and module configuration model:

1. Locate V2 module artifacts via `ModuleFinder`.
2. Resolve the module graph against the appropriate parent configuration; handle `requires`, `exports`, `opens`, and `provides/uses`.
3. Create a **new ModuleLayer** binding the modules to one or more loaders using `defineModulesWithOneLoader`/`defineModulesWithManyLoaders` as appropriate.
4. Publish V2 layer service objects only after validation.
5. Retire the V1 layer by **dropping all references** to the layer/loader/classes/providers once no work remains; there is no general Java SE operation like `ModuleLayer.unload()`.

The calls below are **structural pseudocode**, not a verbatim runnable program:

~~~java
ModuleFinder finder = ModuleFinder.of(version2ModulePath);
Configuration config = parentLayer.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("plugin.module"));

ModuleLayer v2 = parentLayer.defineModulesWithOneLoader(
        config, sharedApiLoader);
~~~

This requires importing `java.lang.module.ModuleFinder`/`Configuration` and `java.util.Set`, along with existing `version2ModulePath`/`parentLayer`/`sharedApiLoader` variables. Not every module graph/layer can be resolved arbitrarily if packages/names/dependencies conflict. A new `ModuleLayer` does not by itself guarantee V1 unloading or state migration.

**Architectural choice:** If the application only needs classpath plugin JARs with SPI, `URLClassLoader` + a shared API parent is usually simpler. If you want strong encapsulation/module descriptors/services under JPMS, use module layers and check module access separately.

## 12. Do Not Turn a ClassLoader into a Security Sandbox

A new ClassLoader for generation V2 solves **class identity and dependency isolation** within the same JVM; it does not restrict files/network/CPU/threads that plugin code is allowed to use. On JDK 24+, the Security Manager has been permanently disabled (JEP 486). If a plugin is untrusted, run it in a process/OS sandbox with appropriate permissions, resource limits, and IPC protocols; hot swapping inside the same JVM is not a security boundary.

## 13. QA Checklist Before Allowing Version Swaps

**Artifact / compatibility**

- [ ] V2 JAR path is immutable/versioned; checksum/signature/provenance have been verified.
- [ ] Java bytecode version, dependency versions, and module/JAR metadata match the runtime.
- [ ] Shared API is defined by the host parent, with no duplicate copy of the API redefined by the child.
- [ ] Entry point has a public constructor or factory permitted by the contract; API is compatible.
- [ ] Health check distinguishes verification/configuration from side effects caused by `<clinit>`/constructors.

**Cutover / concurrency**

- [ ] There is an **atomic/locked publish point** for the active generation.
- [ ] How far are requests/callbacks that already acquired V1 allowed to run? There is a lease/read lock/cancellation policy.
- [ ] V1 is not closed while `loadClass`/`getResource` or methods are still running without coordination.
- [ ] Concurrent admin/swap/close operations are serialized and state checks are accurate.
- [ ] There is a timeout when draining V1; if it times out, cleanup is not declared complete.
- [ ] Async callbacks retain the right generation and do not mix V1/V2 within the same transaction when incompatible.

**Cleanup / observability**

- [ ] V1 stops timers/executors, unsubscribes listeners, and unregisters SPI/registries.
- [ ] Provider instances, sockets, DB pools, watchers, and file handles are closed by the proper owner.
- [ ] Worker TCCLs are restored; ThreadLocals holding V1 objects are removed.
- [ ] V1's URLClassLoader is closed after quiescing; suppressed exceptions are logged.
- [ ] The host drops references to old `Class`, `Method`, ServiceLoader cache, plugin instance, and ModuleLayer.
- [ ] Loaders/threads/Metaspace/file handles are measured across multiple swaps rather than relying on a single GC.
- [ ] Reporting distinguishes PREPARE_FAILED from PUBLISHED_CLEANUP_PENDING and COMPLETE.

## 14. Recommended Test Plan for a Plugin Manager

| Test | Expected Result to Prove |
| --- | --- |
| V1→V2 same binary name, new loader | Method returns V2 behavior and `oldType != newType` |
| Shared API identity | `Plugin.class.isAssignableFrom(v2Impl) == true` |
| Attempting to update the JAR file while keeping the old loader | No assumption that the JVM automatically creates a new class |
| Invalid V2 JAR or missing entry point | Not published; V1 continues serving requests |
| V2 constructor/health check fails | Created V2 resources are closed; active is not switched |
| 100 V1 requests running during a swap | V1 is not closed before in-flight work finishes according to policy |
| Requests arriving after cutover | Receive V2 and are not randomly routed back to V1 |
| V1 close() throws an error | V2 remains active; retirement failure is clearly reported |
| Hot reload repeated 100+ times | No uncontrolled upward trend in threads/loaders/handles |
| TCCL on executor workers | No remaining reference to the V1 loader after stop |
| V1 provider in ServiceLoader/DI cache | Registry/cache cleanup works properly; provider is not called after retirement |
| Rollback V2→stable V1 artifact | A new loader is created; external schema/state are compatible |
| Two concurrent admins calling replace/close | No orphaned loader; no publishing after shutdown |
| JPMS V2 layer if applicable | Module graph/services/access are correct; V1 layer is not retained |

### 14.1. Observing Class Loading and Unloading

On a HotSpot JDK supporting unified logging:

~~~bash
java -Xlog:class+load=info,class+unload=info \
    -cp "build/api:build/host" HostMain
~~~

The log reports load/unload events when they occur; a demo that still holds `oldType` may leave V1 classes ineligible for unloading. `-Xlog` is a JVM implementation mechanism, not a Java language API requiring every vendor to use the same format.

You can use `jcmd`/Java Flight Recorder/heap dumps and thread dumps to trace loader retention. Check which tools are available in your JDK before using them, and keep generation id + artifact hash + loader identity in diagnostic logs to distinguish V1/V2.

## 15. Misconceptions to Avoid

1. "Copying a new JAR over V1.jar makes the JVM automatically pick up the new code." — **False** for already loaded classes.
2. "Calling `loader.loadClass` again will redefine the class." — **False**; the same loader normally returns the same `Class<?>`.
3. "Changing `ProtectionDomain` or `CodeSource` can reset class identity." — **False**.
4. "Creating a new loader when the parent already has V1 classes still guarantees V2." — **False**; delegation may return the parent's copy.
5. "Having the same name `api.Plugin` means the host can cast to it." — **False** if the defining loaders differ.
6. "Calling `URLClassLoader.close()` immediately unloads old classes." — **False**.
7. "Closing the loader automatically shuts down all plugin threads/DB connections." — **False**.
8. "`AtomicReference.getAndSet` followed immediately by closing V1 is safe for all requests." — **False** if requests still hold references to V1.
9. "Preparing V2 means there are no side effects yet." — **False**; static initializers/constructors/start methods may have already executed.
10. "A failure to close V1 after publish means V2 is not yet active." — **False**; commit results and cleanup results must be distinguished.
11. "`ServiceLoader.reload()` hot-reloads bytecode from a new JAR." — **False**; it resets the provider cache.
12. "A new loader automatically resolves all DB schema/API incompatibilities." — **False**; separate migration/versioning is needed.
13. "ModuleLayer has an unload method to call when a plugin is finished." — **There is no** such Java SE unload API.
14. "Separating classloaders provides a safe sandbox for untrusted plugins." — **False**, especially on JDK 24+ where the Security Manager is gone.
15. "Running `System.gc()` once without seeing unloading proves a memory leak." — **False**; you need to find strong roots and observe over the longer term.

## 16. Self-Check Exercises

1. V1 and V2 both define `plugin.impl.Versioned` from two new `URLClassLoader` instances. Are they the same runtime class? **No**, if each loader actually defines that class itself.
2. Plugin V2 implements `api.Plugin` defined by the host parent; can the host cast it? **Yes**, when the implementation is compatible and access is valid.
3. Why shouldn't the V1 implementation JAR be placed on the host classpath in the lab? **Parent-first delegation may return the V1 class to both loaders**.
4. `Generation.open(V2)` fails while V1 is active; should V2 be published? **No**; keep V1 and clean up V2.
5. When `active` has just switched to V2, how should an unfinished V1 request be handled? **Draining/lease or locking; do not close V1 prematurely**.
6. Does `URLClassLoader.close()` delete already loaded `Class<?>` objects? **No**.
7. If closing V1 fails after the swap, what is active? **V2**; the retirement failure must be reported separately.
8. Why not simply use `AtomicReference` for all operations? **An atomic swap does not protect the lifetime of an object read prior to the swap**.
9. Does hot swapping automatically stop V1's background executor? **No**, a separate lifecycle mechanism is needed.
10. Will a `ServiceLoader` instance currently caching V1 providers automatically switch to V2 when the TCCL changes? **No**.
11. If you want to roll back to V1 after the V1 loader has already closed, what should you do? **Initialize a new generation from the immutable V1 artifact**.
12. Why can a host static map cause a classloader leak? **It retains plugin classes/objects, extending the lifetime of the defining loader**.
13. Do you need to close the shared parent loader after each plugin update? **No**, the parent belongs to the host and other generations.
14. On Java 24+, can plugins still be restricted using Security Manager/ProtectionDomain as before? **No**, other boundaries must be used if needed.
15. When using named modules, what else must be managed? **ModuleLayer/configuration/readability/exports/opens/provider resolution**.

## 17. Official References

1. [JVMS 5.3 — Loading, Defining Loader, and Runtime Type Identity](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): class name + defining loader, initiating loaders, loading constraints.
2. [JLS 12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.2): good classloader consistency and the requirement that the same name returns the same runtime Class within a loader.
3. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): delegation, `findLoadedClass`, `defineClass`, `loadClass`, resource lookup.
4. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): `close`, already-loaded classes, file/JAR handles, concurrent close limitations.
5. [AutoCloseable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): cleanup and try-with-resources.
6. [ReentrantReadWriteLock — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): read/write lock and concurrency policy.
7. [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): TCCL and thread inheritance.
8. [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider discovery/cache, `reload`, and classloader/module layers.
9. [ModuleLayer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): loading a module configuration in a new layer.
10. [JEP 486 — Security Manager permanently disabled](https://openjdk.org/jeps/486): why `ClassLoader`/`ProtectionDomain` cannot act as a security sandbox for plugins on JDK 24+.

**Conclusion:** Replacing plugin V1 with V2 means **switching an entire generation**, not updating a single `Class<?>` in isolation. Use a **new loader**, preserve **shared API identity**, prepare/test V2 before publishing, switch routing under a **protocol safe for in-flight requests**, and then retire V1 according to resource ownership. `URLClassLoader.close()` closes JAR handles, but it does **not** automatically stop threads, automatically unload classes, or replace a lifecycle/rollback policy.
