# Implementing Plugin Reloading with a New ClassLoader in Java 17

## 1. Practice Objectives

In a Java system that supports plugins, a "reload plugin" requirement typically means:

1. The host application is currently calling implementation version **v1**.
2. Version **v2** is released with the same binary name (for example, `plugin.EchoPlugin`) but new bytecode/behavior.
3. The host **prepares a new class loader** and creates an instance of v2.
4. The host switches new calls to the v2 instance in a controlled manner.
5. In-flight calls still running on v1 are completed or canceled according to policy, after which the resources and references of the **old loader** are released.
6. If preparing v2 fails, v1 continues serving instead of being unloaded prematurely.

**What not to do:** overwrite the `.class`/JAR file underneath the old loader and expect `loadClass` to replace the existing runtime definition. In the JVM, a runtime class is identified by **binary name + defining class loader**. A loader that has already defined `plugin.EchoPlugin` does not turn that class into v2 just because the file on disk changed its contents.

This lesson builds a **compilable and runnable Java 17** example: a shared `api.Plugin`, two v1/v2 implementations with the same binary name, each version placed in its own output directory, a new `URLClassLoader` for each generation, and a `Manager` using `ReentrantReadWriteLock` to avoid races between invocations and plugin replacement.

The practical results will demonstrate:

- Both versions implement the same interface known to the host.
- After reloading, v2 runs the new behavior and its static field starts from a fresh state.
- The v1 and v2 classes have the same binary name but are different `Class<?>` instances and have different defining loaders.
- If preparing a candidate from a missing path fails, v1 remains the active plugin.
- The v1 loader is closed after the manager switches to v2; **closing the loader does not prove that the class has been unloaded by the JVM**.

## 2. Reloading Must Create a New Runtime Definition

Calling `loader.loadClass("plugin.EchoPlugin")` repeatedly on the **same loader** usually yields the same recorded `Class<?>`. Overwriting the JAR or replacing bytes at the source does not overwrite an already-defined class; attempting to call `defineClass` again with the same binary name in the old loader can cause a `LinkageError`.

The lab therefore creates two **loader instances**:

```text
Host/App Loader
  └── api.Plugin (shared API)
       ├── L1 -> plugin.EchoPlugin v1
       └── L2 -> plugin.EchoPlugin v2

(plugin.EchoPlugin, L1) != (plugin.EchoPlugin, L2)
api.Plugin is always defined by the parent
```

| Change approach | Creates a new class identity? |
| --- | --- |
| Call method/loadClass again via L1 | No |
| Modify the file that L1 has already read | Does not replace the old runtime class; easy to mix resources/dependencies |
| Create L2 and let L2 actually define v2 | Yes, belongs to a different generation |
| Instrumentation/JVMTI hot swap | Separate mechanism with limitations, not a second `defineClass` |
| Restart JVM | New runtime, in exchange for different deployment costs |

**Having two generations coexist for a period of time is valid.** The focus is not merely on loading v2, but on protecting in-flight calls, publishing v2 only after prepare, and retiring v1 in a controlled manner.

## 3. Controlled Reload Architecture

```text
         Requests from host
                |
                v
          Plugin Manager
          active = v1
                |
                v
          Plugin v1 / L1
                |
                +------------------+
                                   |
                         Prepare v2 / L2
                         (not yet published)
                                   |
                 +-----------------+----------------+
                 |                                  |
           Prepare fails                     Prepare succeeds
                 |                                  |
         Active remains v1          Write lock / wait for v1 calls
                 |                                  |
          Do not close v1                Active <- v2 / L2
                                                    |
                                           Close plugin v1 / L1
                                                    |
                                           New calls -> v2
```

Two steps must be distinguished:

- **Prepare:** build the new loader, load/validate the implementation, and create the candidate instance; if it fails, only dispose of the candidate without touching the active plugin.
- **Activate/replace:** once the candidate is ready, block new calls briefly enough to swap the active reference, wait for old calls to finish, and close old resources according to policy.

In the example, `ReentrantReadWriteLock` is used as a **synchronization gate**:

- Each `invoke` holds the **read lock** for the entire duration of the plugin method call.
- `replace` and `close` acquire the **write lock**. The write lock is only acquired once all current read locks have been released.
- Therefore, when replacing v1 with v2, no v1 call is executing **through this manager**.
- After the swap, calls that acquire a new read lock will see v2.

**Limitation:** The lock only manages calls going through the manager. If a plugin spawns its own background threads, timers, or independent callbacks, this lock **does not automatically stop** them. In production, lifecycle hooks, task quiescing/draining, and corresponding cleanup are required.

## 4. Project Structure

Create the files:

```text
src/
  api/
    api/
      Plugin.java

  v1/
    plugin/
      EchoPlugin.java

  v2/
    plugin/
      EchoPlugin.java

  host/
    host/
      ReloadPluginDemo.java

out/
  api/
    api/
      Plugin.class
  v1/
    plugin/
      EchoPlugin.class
  v2/
    plugin/
      EchoPlugin.class
  host/
    host/
      ReloadPluginDemo.class
      ...
```

`out` is the **build output**; there is no need to create each `.class` file manually. The two source files `src/v1/plugin/EchoPlugin.java` and `src/v2/plugin/EchoPlugin.java` share the same declaration `package plugin; public final class EchoPlugin`; this is valid because they are compiled into **two separate directories**.

**Important invariant:** `api.Plugin` has only a single runtime copy in `out/api` defined by the host's shared loader. Do not put `out/v1` and `out/v2` on the application classpath when running the host.

## 5. Shared API — Stable Contract Between the Host and All Versions

File `src/api/api/Plugin.java`:

```java
package api;

public interface Plugin extends AutoCloseable {
    String execute(String input);

    @Override
    void close();
}
```

Explanation:

- `execute` is the entry point called by the host, returning a `String` from Java core without leaking plugin-private types through the signature.
- `AutoCloseable` represents the lifecycle; `Plugin.close()` overrides it and **declares no checked exceptions** in this shared interface.
- `URLClassLoader.close()` can still throw `IOException`; that is something the host must handle separately.
- This is the **contract**; both v1 and v2 plugins compile against `out/api` and delegate `api.Plugin` to the parent at runtime.

A real-world shared API might declare `start(PluginContext)`, `quiesce()`, `stop()`, health checks, DTO/request/response types, and domain exceptions. Those types must also be defined uniformly by the parent/shared loader if used across the boundary.

**Do not change the interface arbitrarily between reloads.** A plugin compiled against API v2 when the host only has API v1 can encounter `NoSuchMethodError`/`AbstractMethodError`/binary compatibility errors even when the separate class loaders are already working properly.

## 6. Plugin v1: Behavior and Static State of the First Generation

File `src/v1/plugin/EchoPlugin.java`:

```java
package plugin;

import api.Plugin;

public final class EchoPlugin implements Plugin {
    private static int calls;

    @Override
    public String execute(String input) {
        return "v1:" + input + ":" + (++calls);
    }

    @Override
    public void close() {
        System.out.println("CLOSE=v1");
    }
}
```

`calls` is a **static field** of `plugin.EchoPlugin` defined by defining loader L1. In the sequential demo, three calls to v1 will produce `:1`, `:2`, and `:3`.

**Production warning:** `++calls` is not thread-safe. We only use it in the demo to observe static class state after reloading; for plugins serving concurrent requests, consider `AtomicInteger`/synchronization and determine which state needs to be persisted/migrated.

`close()` prints a marker; in a real plugin, it typically releases streams, connections, threads/executors, listeners, schedulers, and resources. Merely printing a marker **does not unload the class**.

## 7. Plugin v2: Same Class Name, Different Implementation

File `src/v2/plugin/EchoPlugin.java`:

```java
package plugin;

import api.Plugin;

public final class EchoPlugin implements Plugin {
    private static int calls;

    @Override
    public String execute(String input) {
        return "v2:" + input + ":" + (++calls);
    }

    @Override
    public void close() {
        System.out.println("CLOSE=v2");
    }
}
```

Compared to v1:

- **Same binary name:** `plugin.EchoPlugin`.
- **Same shared interface:** the host's `api.Plugin`.
- **Different behavior:** `v2:` prefix.
- **Different static state:** the v2 class's `calls` is independent of the v1 class's static field due to different defining loaders.

If the host sees `v2:hello:1` after reloading, that is practical evidence that a new runtime generation is handling the call (combined with the `Class<?>` identity check below).

## 8. Java 17 Host: Creating a New Loader and Switching Generations

File `src/host/host/ReloadPluginDemo.java`:

```java
package host;

import api.Plugin;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class ReloadPluginDemo {
    static final class Generation implements AutoCloseable {
        final URLClassLoader loader;
        final Plugin plugin;
        final Class<?> type;

        Generation(URLClassLoader loader, Plugin plugin, Class<?> type) {
            this.loader = loader;
            this.plugin = plugin;
            this.type = type;
        }

        @Override
        public void close() throws IOException {
            try (loader) {
                plugin.close();
            }
        }
    }

    static Generation prepare(Path pluginDirectory) throws Exception {
        URL source = pluginDirectory.toUri().toURL();
        URLClassLoader loader = new URLClassLoader(
                "generation-" + pluginDirectory.getFileName(),
                new URL[]{source},
                Plugin.class.getClassLoader());

        try {
            Class<?> type = Class.forName(
                    "plugin.EchoPlugin", true, loader);

            Plugin instance =
                    (Plugin) type.getConstructor().newInstance();

            return new Generation(loader, instance, type);
        } catch (Exception | LinkageError failure) {
            try {
                loader.close();
            } catch (IOException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }

    static final class Manager implements AutoCloseable {
        private final ReentrantReadWriteLock gate =
                new ReentrantReadWriteLock(true);

        private Generation current;

        String invoke(String message) {
            gate.readLock().lock();
            try {
                if (current == null) {
                    throw new IllegalStateException("No active plugin");
                }
                return current.plugin.execute(message);
            } finally {
                gate.readLock().unlock();
            }
        }

        Class<?> activeType() {
            gate.readLock().lock();
            try {
                if (current == null) {
                    throw new IllegalStateException("No active plugin");
                }
                return current.type;
            } finally {
                gate.readLock().unlock();
            }
        }

        void replace(Generation next) throws IOException {
            gate.writeLock().lock();
            try {
                Generation previous = current;
                current = next;
                if (previous != null) {
                    previous.close();
                }
            } finally {
                gate.writeLock().unlock();
            }
        }

        @Override
        public void close() throws IOException {
            gate.writeLock().lock();
            try {
                Generation previous = current;
                current = null;
                if (previous != null) {
                    previous.close();
                }
            } finally {
                gate.writeLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (Manager manager = new Manager()) {
            manager.replace(prepare(Path.of("out/v1")));
            Class<?> oldType = manager.activeType();

            System.out.println("FIRST=" + manager.invoke("hello"));
            System.out.println("SECOND=" + manager.invoke("world"));

            try {
                Generation missing =
                        prepare(Path.of("out/missing"));
                manager.replace(missing);
            } catch (ClassNotFoundException expected) {
                System.out.println(
                        "PREPARE_FAILED=ClassNotFoundException");
            }

            System.out.println("STILL=" + manager.invoke("again"));

            Generation next = prepare(Path.of("out/v2"));
            manager.replace(next);

            Class<?> newType = manager.activeType();
            System.out.println("AFTER=" + manager.invoke("hello"));

            System.out.println("SAME_BINARY_NAME="
                    + oldType.getName().equals(newType.getName()));
            System.out.println("SAME_RUNTIME_CLASS="
                    + (oldType == newType));
            System.out.println("SHARED_API="
                    + (Plugin.class.isAssignableFrom(oldType)
                       && Plugin.class.isAssignableFrom(newType)));
            System.out.println("DIFFERENT_DEFINERS="
                    + (oldType.getClassLoader()
                       != newType.getClassLoader()));
        }
    }
}
```

### 8.1. Role of Each Component

**`Generation`** holds three objects belonging to the same plugin deployment:

- `URLClassLoader loader`: the dedicated class source for this generation.
- `Plugin plugin`: the implementation instance used by the host through the shared API.
- `Class<?> type`: the runtime class token, used for diagnosing identity.

`Generation.close()` calls `plugin.close()` and then closes the loader via try-with-resources. If `plugin.close()` throws a runtime exception, the try-with-resources structure still attempts to close the URLClassLoader. If closing JAR/URL resources throws an `IOException`, the caller may receive that exception; real-world handling requires proper logging and cleanup policies.

**`prepare`** creates **a new URLClassLoader per invocation**, with `Plugin.class.getClassLoader()` as its parent. In the example with a clean application classpath, the parent sees `api.Plugin` but does not see `plugin.EchoPlugin`, so the child loader defines its own implementation.

**`prepare` does not "merely read metadata"**: `Class.forName(..., true, loader)` can trigger static initialization, and the constructor invoked in `newInstance` executes plugin code. Therefore, only pass **trusted/verified** artifacts into the prepare phase; in production, do not equate "not yet activated" with "no plugin code executed yet".

If lookup/constructor/linking fails with one of the caught types, the candidate loader is closed and the exception is rethrown. `Manager.current` has not been replaced yet, so the old active version continues serving. The catch block only covers `Exception | LinkageError`; it does **not** turn every serious `Error` such as `OutOfMemoryError` into an error that can be safely rolled back.

**`Manager.invoke`** holds the read lock throughout the `plugin.execute` call. `replace` requires the write lock, so it waits for calls going through the manager to finish before swapping the active reference and closing the old generation.

**`Manager.activeType`** returns the runtime `Class<?>` to prove class identity. Returning the token outside the session allows the caller to **keep the old loader alive**; this is an operation intended for the test, not a production API recommended to be retained long-term.

**`Manager.close`** sets active to null and closes any still-active generation, preventing new requests from using the plugin through the manager.

### 8.2. Why Hold the Read Lock Across the Entire Plugin Call?

Suppose worker R1 is running v1's `plugin.execute`, while R2 requests a reload:

```text
R1: acquire readLock
R1: call v1.execute()
R2: request writeLock -> must wait
R1: return result, release readLock
R2: acquire writeLock
R2: current <- v2, close v1
R2: release writeLock
R3: acquire readLock -> call v2
```

This avoids a very common type of race: the host closing the old loader while a worker is still loading resources/classes or executing v1 code. Java SE 17 warns that concurrent `URLClassLoader.close()` alongside class loading has undefined results.

Drawback: a slow or hung plugin call can hold the read lock for too long and cause the reload to block. Production needs timeout/cancellation/operation tracking; reference-counted generations can be used instead of a read–write lock held across the invocation, provided you ensure **the generation is not closed while in-flight callers remain**.

### 8.3. Why Not Set current = null Before Preparing v2?

If active is cleared before the prepare phase, an error such as `ClassNotFoundException` or a v2 constructor exception leaves the host with **no plugin serving requests**, even though v1 could still operate.

In the demo, v2 is prepared first:

```java
Generation next = prepare(Path.of("out/v2"));
manager.replace(next);
```

As a result, when `prepare` fails, `replace` does not run and v1 is not replaced.

**Transaction note:** `replace` in the demo switches `current` to v2 **before** calling `previous.close()`. If shutting down v1 throws an error, v2 **has already been published** even though `replace` throws an exception. Therefore, this is an **atomic switch for calls going through the lock**, not a global transaction that guarantees rolling back all side effects. Production systems should separate the activation step from cleanup, report status separately, perform an idempotent stop, and define clear rollback/failover decisions.

## 9. Build and Run: Linux/macOS Bash

From the root directory containing `src`:

```bash
mkdir -p out/api out/v1 out/v2 out/host

javac -d out/api src/api/api/Plugin.java

javac -cp out/api -d out/v1 src/v1/plugin/EchoPlugin.java

javac -cp out/api -d out/v2 src/v2/plugin/EchoPlugin.java

javac -cp out/api -d out/host \
  src/host/host/ReloadPluginDemo.java

java -cp "out/api:out/host" host.ReloadPluginDemo
```

**Extremely important:** the `java` command's classpath contains only `out/api` and `out/host`. Do not include `out/v1` or `out/v2` on the application classpath when running; otherwise, parent-first delegation can cause the shared loader to find the implementation first and break generation independence.

The `javac` commands compile v1 and v2 **separately**, each time referencing `out/api` so they implement the exact shared interface.

## 10. Build and Run: Windows PowerShell

PowerShell uses `;` as the classpath separator:

```powershell
New-Item -ItemType Directory -Force out/api,out/v1,out/v2,out/host

javac -d out/api src/api/api/Plugin.java

javac -cp out/api -d out/v1 src/v1/plugin/EchoPlugin.java

javac -cp out/api -d out/v2 src/v2/plugin/EchoPlugin.java

javac -cp out/api -d out/host src/host/host/ReloadPluginDemo.java

java -cp "out/api;out/host" host.ReloadPluginDemo
```

Run in a new/clean working directory to avoid having a `plugin.EchoPlugin` class from another build on the parent classpath. If using an IDE, also check whether the **run configuration** accidentally adds v1/v2 to the host's classpath.

## 11. Expected Stdout and Practical Verification

With Java 17+ and a clean project as above:

```text
FIRST=v1:hello:1
SECOND=v1:world:2
PREPARE_FAILED=ClassNotFoundException
STILL=v1:again:3
CLOSE=v1
AFTER=v2:hello:1
SAME_BINARY_NAME=true
SAME_RUNTIME_CLASS=false
SHARED_API=true
DIFFERENT_DEFINERS=true
CLOSE=v2
```

This is the deterministic output of the **sequential demo**. The code was compiled and tested using OpenJDK 21 with Java 17-compatible APIs/syntax; the output matches the exact lines above. Testing on JDK 21 **does not mean** it was run specifically on JDK 17.

### Interpreting Each Group of Results

**First two v1 calls:**

```text
FIRST=v1:hello:1
SECOND=v1:world:2
```

The same `plugin.EchoPlugin` class from L1 uses the same static field `calls`.

**Preparing a nonexistent version:**

```text
PREPARE_FAILED=ClassNotFoundException
STILL=v1:again:3
```

`out/missing` does not contain the `plugin.EchoPlugin` class, nor does the parent classpath have that class. The candidate lookup reports `ClassNotFoundException`, and `prepare` cleans up the candidate loader. `replace` was not called, so the manager still points to v1.

**Swap:**

```text
CLOSE=v1
AFTER=v2:hello:1
```

The `CLOSE=v1` marker from the old plugin's lifecycle method appears when the manager replaces the generation. Then v2 handles the new call with a different prefix; the static `calls` of the v2 runtime class starts at 0, so the first call yields `:1`.

**Type identity:**

```text
SAME_BINARY_NAME=true
SAME_RUNTIME_CLASS=false
SHARED_API=true
DIFFERENT_DEFINERS=true
```

`oldType` and `newType` have the same `getName()` but different `Class<?>` identities. Both are assignable to the host's `api.Plugin`. The two `getClassLoader()` results are different, so there are two defining loaders.

**Final shutdown:**

```text
CLOSE=v2
```

The `Manager` try-with-resources closes generation v2. None of the lines prove that v1/v2 has been GC'd or that classes have been unloaded; the marker only proves that the `close()` callback was invoked.

## 12. Distinguishing Preparation, Activation, Stopping, and Class Unloading

A real reload consists of distinct events:

| Event | Occurs in demo | Guarantees class unloading? |
|---|---|---|
| Create L2 | `prepare(out/v2)` | No |
| Load v2 class | `Class.forName` with L2 | No |
| Instantiate v2 instance | Reflection constructor | No |
| Switch active from v1 to v2 | `Manager.replace` | No |
| Wait for old calls to finish | Write lock waits for read locks | No, only for calls through the manager |
| Call `v1.close()` | Lifecycle callback | No |
| Call `L1.close()` | `Generation.close()` | No |
| Drop references to L1 and v1 classes | Must track all references/roots | Creates conditions to make reclamation possible |
| GC/class unloading | JVM decision | No deadline |

### Class Unloading per JLS 17 §12.7

The JVM can unload a class/interface only if its **defining loader** can be reclaimed by the garbage collector; eligibility alone does not require the JVM to unload it immediately.

In the demo, the variable:

```java
Class<?> oldType = manager.activeType();
```

still retains the old `Class<?>` to perform the identity check after reloading. That **can keep L1 reachable**. This is an intentional choice for demonstration purposes, not a pattern to keep in production.

To give L1 a chance to be reclaimed, after verification you must also drop the `oldType` reference, all v1 instances/lambdas/reflection metadata, listener registries, cache entries, TCCL references, and corresponding background tasks; **do not conclude that "CLOSE=v1" means L1 has been GC'd**.

### Closing Does Not Terminate Running Code

`URLClassLoader.close()` closes the URL/JAR resource sources and affects looking up new classes/resources. Already-loaded runtime classes and created objects can still be used while reachable. If a plugin spawns another thread of its own and that thread still holds v1 code/objects, closing the loader does not automatically stop that thread.

**Recommendation:** implement `Plugin.close()` to perform real lifecycle cleanup, while the host tracks the plugin's workers/schedulers. If plugins are untrusted, class-loader isolation is not a security sandbox; process-level isolation is required when the threat model demands it.

## 13. Example of Why Modifying a JAR File In-Place Is Wrong

Suppose you deploy:

```text
plugins/current/plugin.jar
```

and the host uses a `URLClassLoader` pointing to that file. You overwrite `plugin.jar` with v2 while the host is still using loader L1.

Things that can happen:

- The already-loaded `plugin.EchoPlugin` class remains the v1 runtime class defined by L1.
- A not-yet-loaded `plugin.Helper` class might be read later from the newly replaced JAR bytes, causing one generation to mix v1 and v2 code.
- Resources/service descriptors might be read from a different version than the already-loaded classes.
- JAR handles/caching/file replacement semantics differ across filesystems/JDKs; on Windows, file locking issues can also occur.
- `NoSuchMethodError`/`NoSuchFieldError` or incorrect behavior due to an inconsistent ABI.

Do not use "finished copying the new JAR" as a synchronization protocol between the deployment process and the JVM runtime.

**A better approach:** each version is a separate **immutable release directory/JAR**:

```text
plugins/releases/plugin-1.0/plugin.jar
plugins/releases/plugin-2.0/plugin.jar
```

The host verifies the v2 artifact, creates a new loader from the v2 path, switches the active generation, and then stops/closes v1. Do not modify the old artifact while L1 can still load additional classes/resources.

## 14. Safe Release Deployment and Avoiding TOCTOU

For plugins obtained from a network source or shared directory, you must verify **the exact bytes that will be used for execution**. A production workflow:

1. **Build/package:** produce a consistent JAR/module artifact with a version and dependency manifest.
2. **Approve:** sign the manifest or pin the artifact digest from an independent approval source.
3. **Download/stage:** download to a directory managed by a trusted actor with restricted write permissions.
4. **Verify:** verify the signature/hash of the entire artifact/dependencies, not just the entry class.
5. **Snapshot:** store the verified artifact in an immutable location, preventing other actors from modifying it between check and load.
6. **Prepare candidate loader** from the v2 snapshot.
7. **Health-check candidate** before activation to the extent possible; avoid uncontrolled side effects.
8. **Activate:** coordinate requests/state and switch the generation.
9. **Observe/rollback:** monitor behavior and keep a fallback path ready if v2 fails.
10. **Retire old:** stop v1 tasks, unregister listeners, clear caches, close the loader, and drop references.

**Important note:** the demo's `prepare` uses `Class.forName(..., true, loader)` and creates an instance, so candidate code is already executed before publication. Artifacts must be trusted/verified **before** calling `prepare`; do not treat plugin preparation as a sandbox.

If immediate rollback is needed after v2 receives traffic, you can keep v1 temporarily for a **grace period** instead of closing it immediately, and then retire it once v2 meets health criteria. However, you must bound the number of generations kept alive to avoid a Metaspace leak caused by retaining old loaders indefinitely.

## 15. Why Must the Shared API Be in the Parent Loader?

At runtime:

```java
Plugin plugin = (Plugin) type.getConstructor().newInstance();
```

The cast succeeds because `plugin.EchoPlugin` in both loaders implements **the exact `api.Plugin` defined by the parent loader**.

If plugin v2 contains its own copy of `api.Plugin` and a custom child-first loader defines that copy itself, then:

```text
("api.Plugin", hostLoader) != ("api.Plugin", pluginLoader)
```

The implementation object may not be assignable to the host's `Plugin.class`, resulting in a `ClassCastException` or `LinkageError` due to loader constraints when linking reference types in method descriptors.

**Keep in the shared API loader:** interfaces, DTOs, exception contracts, and types that cross the host/plugin boundary. **Keep in the child plugin loader:** implementations and private dependencies that may have different versions. Avoid placing `lib.private.*` in the public method parameters or return types of `api.Plugin`.

With the Java module system (JPMS) and `ModuleLayer`, in addition to loader identity, you must also consider module readability, `exports`, and `opens`. The example here deliberately uses the **classpath** to focus on classloader reloading, without assuming that any rules of named modules are bypassed.

## 16. State Migration: Static State Does Not Automatically Transfer to a New Loader

V1 and v2 have separate classes, so:

```java
private static int calls;
```

in the two versions are **two independent static fields**. `AFTER=v2:hello:1` is a consequence of the demo code: v2 starts a new generation.

If a production plugin needs to preserve information such as user sessions, counters, checkpoints, subscriptions, or workflow state, an explicit protocol is needed:

```text
v1 quiesce()
  -> exportState() to shared DTO / serialized schema
  -> validate schema and version compatibility
  -> create v2
  -> importState(snapshot) before activation
  -> health check
  -> switch traffic
  -> stop v1, release loader
```

This is an illustrative architecture, **not existing methods** in the demo's `api.Plugin`. If you want to implement it, extend the shared API with a clear, versioned contract.

Do not pass v1's `Class<?>`, private objects, or lambdas directly across the boundary for v2 to retain. Those objects have runtime identities tied to L1; if v2 stores them, L1 remains reachable and type/ABI interpretation may be wrong. Parent-defined DTOs or classloader-independent serialization formats are usually easier to manage.

### When Migration Fails

If the v1→v2 state import fails, **do not publish the candidate** and let v1 continue serving. If v1 has already been quiesced, a careful resume/thaw procedure is required. Do not stop v1 before knowing that service can be restored.

**Idempotency and external side effects:** if v2 wrote to a database/message queue during the health check or prepare phase, rolling back the active pointer does not automatically reverse the side effect. Therefore, "atomic reload" should not be misunderstood as a transaction across all I/O.

## 17. Concurrency: From the Demo Lock to Production Drain

The demo's read–write lock is easy to understand, but it has limitations:

- The write lock waits for all read locks; a slow or hung method can delay reloading indefinitely.
- If the plugin keeps asynchronous work running after the `execute` method returns, the read lock has already been released, yet the old task may still be executing.
- The plugin may call back into the manager from a thread or reenter code, creating unexpected lock/lifecycle coupling.
- Closing the loader directly inside the write lock can increase the duration for which requests are blocked.
- If `plugin.close()` calls back into the manager, it can create reentrancy/deadlock issues, depending on the call path.

Another design uses **leases/reference counts**:

```text
Acquire active generation -> increment inFlight
Run plugin call
Release generation -> decrement inFlight

Reload:
  prepare v2
  atomically publish v2
  mark v1 retired
  refuse NEW leases for v1
  wait until v1.inFlight == 0
  close v1
```

This is pseudocode/an algorithmic diagram. If implemented, you must ensure that acquiring a lease and publishing retirement do not race: you cannot simply read an `AtomicReference` and then increment the counter too late, because retirement could close the loader before the increment happens. Use a proper state machine/lock/CAS protocol.

**Trade-offs:**

| Mechanism | Pros | Limitations |
|---|---|---|
| Read–write lock across invocation | Easy to prove no close happens while calls through the manager remain | Reload waits for synchronous calls to complete |
| Ref-counted generation leases | Fast swap, allows old calls to drain | Harder to get right; requires guarding atomicity between acquire/retire |
| Process-level rolling restart | Better isolation of loader/native/global state | Complex IPC/process orchestration |
| Stop-the-world plugin quiescence | Simpler for small workloads | Long downtime during stop/load |

For learning applications or plugins running in the same JVM with relatively short calls, a read–write lock is a good practical model. For high-concurrency production systems, dedicated SLAs and architecture are needed.

## 18. Task Cancellation, TCCL, and Preventing ClassLoader Leaks

Even after `Manager` closes L1, the v1 loader can still remain reachable if other components hold references:

| Long-lived root | Can retain L1 via | Required cleanup |
|---|---|---|
| Host static registry | `Class<?>`, `Method`, old Plugin instance | Remove the old generation's entry |
| Listener/event bus | Callback implementation defined by L1 | Unregister listeners |
| Worker thread pool | `Thread.contextClassLoader` = L1 | Restore TCCL within the worker itself |
| `ThreadLocal` | Value containing plugin context/instance | `remove()` on the worker thread |
| Scheduled future/executor | Runnable/lambda from plugin v1 | Cancel tasks, shut down executor, drain |
| Reflection cache | `Method`/`MethodHandle` of a v1 class | Clear per-generation cache |
| ServiceLoader/provider registry | Provider objects defined by L1 | Clear provider references |
| Old `Class<?>` token | Host retaining v1 class metadata | Drop the token after diagnostics |

Example when a framework requires TCCL:

```java
Thread worker = Thread.currentThread();
ClassLoader saved = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    // Run the operation that requires the plugin's TCCL.
} finally {
    worker.setContextClassLoader(saved);
}
```

This snippet requires an existing `pluginLoader` variable. TCCL must be restored on the **thread that actually runs the operation**, not just on the thread that submits the task.

**Do not assume `URLClassLoader.close()` clears all references or interrupts threads.** It closes resources managed by URLClassLoader; class unloading still depends on reachability and the JVM's decisions.

### The WeakHashMap Pitfall

`WeakHashMap<ClassLoader, Class<?>>` has **weak keys but strong values**. If the value is a class defined by the key loader, the value can keep the loader alive so the key is not GC'd as you expect. Do not simply replace a host static `HashMap` with a `WeakHashMap` and treat it as a complete fix.

Easier to control: cache `Class<?>`/`Method` inside **Generation** and clear them on retirement; do not keep strong references in the host registry after stop.

## 19. Observing Class Loading/Unloading During Reload

On HotSpot Java 17, run the demo with Unified Logging:

```bash
java -Xlog:class+load=info,class+unload=info \
     -cp "out/api:out/host" host.ReloadPluginDemo
```

For Windows PowerShell:

```powershell
java -Xlog:class+load=info,class+unload=info -cp "out/api;out/host" host.ReloadPluginDemo
```

The class-load log can contain **two events** for `plugin.EchoPlugin`: one when L1 defines v1, and one when L2 defines v2. Details of source, timestamp, tags, and log line format depend on the JVM. Do not infer from the class name appearing twice that it was defined twice in one loader; here there are two independent defining loaders.

**There is no guarantee that a class-unload event** will appear before the demo finishes. In particular, `oldType` is a strong local token kept to print the identity results; it may keep L1 reachable during that execution.

To investigate multiple hot-reload rounds on a real service:

1. Observe the number of active plugin generations.
2. Observe loader instances and the number of classes defined by each loader.
3. Compare Metaspace used/committed and heap references across multiple cycles.
4. Check TCCL, `ThreadLocal`, callbacks, static maps, and generated proxy/Method caches.
5. Use heap dumps/path-to-GC-root analysis when suspecting a classloader leak.
6. Remember that **a Metaspace increase or a missing unload log once** is not sufficient to conclude there is a leak; the VM may defer unloading and the allocator may retain memory for reuse.

## 20. Common Failure Scenarios

### 20.1. Still Calling v1 Behavior After Reloading

Possible causes:

- The parent application classpath already contains `plugin.EchoPlugin` v1; both parent-first L1 and L2 receive the parent's class.
- Candidate L2 accidentally points to the v1 directory/JAR.
- The host did not actually replace the active reference, only creating L2 and leaving it unused.
- A global `Class<?>`/`Method` cache returns the old class by binary name.
- Another request handler still holds the old plugin instance directly, bypassing the manager.

How to verify:

```java
Class<?> type = activePlugin.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

The snippet requires an `activePlugin` variable. Directly compare the v1/v2 `Class<?>` objects, the loader's URLs, and the implementation version actually being invoked.

### 20.2. ClassCastException When Casting to Shared Plugin

If a child-first L2 defines its own copy of `api.Plugin`, L2's implementation is not assignable to the host's `api.Plugin`. Place a single API artifact on the parent and have plugin loaders delegate `api.*` to that same shared loader. Signatures should use shared DTO/exception types, not plugin-private types.

### 20.3. NoSuchMethodError / AbstractMethodError

Plugin v2 may have been compiled against a different shared API version than the host. Even if L2 is created successfully and the classpath is correct, an ABI mismatch during linking/invoking can still cause errors. Compare `javap -s -p` output and dependency versions.

Do not fix this by catching `LinkageError` and trying to load bytes from unknown sources. Candidate preparation should include binary compatibility checks and integration smoke tests.

### 20.4. ClassNotFoundException in the Candidate

Possible causes:

- The v2 path is wrong or does not contain files yet.
- The JAR/directory layout does not contain the exact binary name `plugin.EchoPlugin`.
- A plugin dependency is missing from the loader graph.
- Incorrect parent/child policy, or unresolved JPMS modules if using named modules.

In the example, `out/missing` intentionally triggers `ClassNotFoundException` to test rollback in the **prepare phase**.

### 20.5. JAR File Locked After Stop

`URLClassLoader.close()` helps close the JAR files that the loader opened; however, if other streams or classpath users still hold file handles, the OS or framework may still block file deletion or renaming. Do not prematurely assume that closing the loader releases everything related to the file.

### 20.6. Metaspace Grows Continuously Across Multiple Reloads

Very likely the host is retaining old generations in a static registry, ThreadLocal/TCCL, event bus, executor, or reflection cache. Use a profiler and GC-root paths to confirm. Do not simply raise `MaxMetaspaceSize` while ignoring the source of retention.

### 20.7. Reload Succeeds but Fails After Running for a While

The candidate may pass its constructor but fail when processing real inputs, loading lazy dependencies/resources, or invoking untested methods. Production should have health checks/integration tests for critical paths and a rollback window. A constructor running successfully **does not prove the entire plugin is safe and compatible**.

### 20.8. Stop Hangs the Reload

Plugin code may block indefinitely inside `execute`, holding the read lock and causing the write lock to wait. Timeout/cancellation/cooperative shutdown is required, as well as a separate-process design if the code is untrusted or uncontrollable.

## 21. Mandatory Tests Before Production Use

| Test | Expectation |
|---|---|
| Start v1 | `FIRST=v1:hello:1` |
| Call v1 twice | State increments 1→2 |
| Nonexistent candidate | `ClassNotFoundException` is reported; v1 continues running |
| Prepare v2 | New loader created, interface cast succeeds |
| Replace v1→v2 | `CLOSE=v1` marker, next request goes to v2 |
| Static state of generation v2 | Starts at `:1` |
| Compare binary names | Both classes have the same name |
| Compare runtime class identity | The two classes are different |
| Check shared API | Both are assignable to the host's `api.Plugin` |
| Concurrency | Does not close v1 while a call through the manager has not completed |
| Cleanup | URLClassLoader closed, callbacks/threads/cache cleaned up |
| Multiple reloads | Does not accumulate old generations indefinitely |
| API evolution | v1/v2 contract is checked for binary compatibility |
| Artifact verification | Unapproved bytes are never executed |
| Rollback | Prepare failure does not remove active v1; post-activation failure has a dedicated policy |

### Notable Race Test

A thread T1 enters `Manager.invoke` and intentionally blocks inside v1 `execute`. Thread T2 calls `replace(v2)`. In the demo, T2 must wait for T1 to release the read lock before closing v1. If a concurrent test observes `CLOSE=v1` **before T1 completes**, there is a bug in ownership/lock management or the plugin is executing along a path outside the manager.

Concurrency tests should use `CountDownLatch`/`Phaser` to coordinate execution flow rather than relying only on `Thread.sleep` and timing measurements; sleep-based tests can be flaky.

## 22. Extended Exercises Beyond the Demo

### Exercise A — Add Version v3

Create `src/v3/plugin/EchoPlugin.java` with `v3:` behavior, compile into `out/v3`, then replace v2→v3 using `prepare(Path.of("out/v3"))`. Observe that the class identity differs across generations while the shared API remains unchanged.

**Check:** each version has its own static `calls`. You should not maintain a static `List<Class<?>> allOldTypes` just to compare all generations in production.

### Exercise B — Preserve Business State

Extend `api.Plugin` with `exportState()`/`importState(...)` via a shared DTO containing the call count. Before activation, migrate state with a schema/version guard. Do not pass an instance of `plugin.EchoPlugin` v1 directly to plugin v2.

**Check:** the new reload continues the expected counter and does not keep the old loader reachable via the state object.

### Exercise C — Simulate a Long-Running Call

In v1, use a `CountDownLatch` to hold an in-flight call. In another thread, prepare and replace with v2. Verify that v1 does not close before the call through the manager finishes. Do not rely on sleep/console output timing as the sole test condition.

### Exercise D — Close Failure

Make `Plugin.close()` throw a `RuntimeException` in v1 and observe `Manager.replace` behavior. In the demo design, v2 has already been published before closing v1; the exception does not roll back the active reference. Add separate error reporting and cleanup policies so the manager accurately reports "activation succeeded; retirement failed".

### Exercise E — JAR Packaging

Package both versions into two independent JARs using `jar --create`. Give the v1/v2 URLClassLoaders only their respective JARs; the application classpath contains only the shared API + host.

Example with compiled output:

```bash
jar --create --file plugin-v1.jar -C out/v1 .
jar --create --file plugin-v2.jar -C out/v2 .
```

When switching to JARs, `prepare` must receive **the exact URL of the JAR file**, no longer the URL of the containing directory. Do not modify the sample command while still using the `out/v1`/`out/v2` directories; the two modes of source URLs must match accordingly.

### Exercise F — Unload Diagnostics

Use `WeakReference<ClassLoader>` to track the old loader after retirement and dropping all strong references. Enable `-Xlog:class+unload=info` and compare. **Do not assert that the weak ref must be cleared after a single `System.gc()`** because GC/class unloading is non-deterministic. Learn how to analyze roots if the loader remains alive.

## 23. Misconceptions to Avoid

| Misconception | Reality |
|---|---|
| "Reloading means calling `loadClass` again on the old loader." | The old runtime class is usually reused; getting a new generation requires a new loader |
| "Modifying the JAR in-place is enough." | It can mix bytes/resources across generations |
| "Two classes with the same name are the same type." | The defining loader also determines runtime identity |
| "Creating L2 before L1 unloads is wrong." | Two runtime classes with the same name can coexist under two different loaders |
| "Each plugin should package the API itself." | Shared API types must be defined uniformly in the parent |
| "`URLClassLoader.close()` unloads classes immediately." | Close only manages loader resources; it does not command synchronous GC/unloading |
| "A successful v2 constructor means the plugin is health-checked." | A constructor does not verify all lazy paths/dependencies |
| "`prepare` does not execute plugin code." | `Class.forName(..., true, ...)` and the constructor can execute code |
| "The read/write lock also handles the plugin's background tasks." | It only protects calls through the manager; plugin-owned tasks need separate cleanup |
| "Swapping the active reference is a transaction that rolls back all side effects." | External side effects and cleanup errors require separate policies |
| "Static state from v1 automatically transfers to v2." | Each runtime class has its own static state; migrate via shared DTO/schema if needed |
| "I closed the session, so the loader is definitely GC'd." | All host cache/Class/Method/TCCL/ThreadLocal references must be dropped; unloading is non-deterministic |
| "A TTL alone solves old loader leaks." | You must invalidate by lifecycle and stop references/tasks belonging to the right owner |
| "Java ClassLoader is a sandbox for untrusted plugins." | No; process/OS isolation is needed for high threat models |

## 24. Self-Check Exercises

**Question 1.** Why is `new URLClassLoader(...)` for v2 more important than modifying `EchoPlugin.class` on disk?

**Answer:** A class already defined in L1 is bound to L1's runtime identity; replacing the file does not change that definition. L2 can define a new runtime class with the same binary name.

**Question 2.** Why is `Plugin.class.getClassLoader()` chosen as the parent of both plugin loaders?

**Answer:** So that v1/v2 both reference the exact `api.Plugin` used by the host; if each child defines a copy of the API, casts/loader constraints can fail.

**Question 3.** Why does reloading print `SAME_BINARY_NAME=true` yet `SAME_RUNTIME_CLASS=false`?

**Answer:** The name `plugin.EchoPlugin` is identical, but the defining loaders L1/L2 are two distinct objects, producing two runtime types.

**Question 4.** Why does the manager still print `STILL=v1:again:3` when `prepare(out/missing)` fails?

**Answer:** The candidate is built outside the manager; the failure occurs before `replace` runs, so active still points to v1.

**Question 5.** In the demo, what does the read/write lock solve?

**Answer:** It ensures `replace` waits for `invoke` calls currently holding the read lock to finish before publishing v2 and closing v1. It does not manage plugin background threads outside the manager.

**Question 6.** Why does `CLOSE=v1` not prove that the v1 class has been unloaded?

**Answer:** It is merely a marker from the plugin lifecycle method. The defining loader can still be reachable through Class tokens, instances, caches, and threads; the VM decides unloading.

**Question 7.** If v1's `Plugin.close()` throws an error after current has already been switched to v2, does it automatically roll back?

**Answer:** Not in the demo. Activation state and retirement errors must be distinguished, with separate production error reporting/rollback designed.

**Question 8.** Why does `AFTER=v2:hello:1` show different static state?

**Answer:** `calls` belongs to the v2 class defined by loader L2, independent of `calls` in v1/L1; v2's first call increments it from 0 to 1.

**Question 9.** If the host keeps holding `Class<?> oldType` after reloading, what is the impact?

**Answer:** That token can keep the runtime class and defining loader L1 reachable, preventing eligibility for class unloading. Only retain it temporarily for debugging/testing.

**Question 10.** Why should a plugin JAR be immutable once verified and passed to the loader?

**Answer:** To avoid TOCTOU, mixing class/resource bytes across multiple versions, and difficulty verifying provenance; each generation reads from a snapshot of the exact release.

**Question 11.** If v2 needs to preserve v1 state, should you cast the v1 instance directly to the v2 implementation class?

**Answer:** No. The two implementation types have different defining loaders/identities. Use a shared DTO or a versioned serialization schema to migrate state.

**Question 12.** If a plugin spawns a continuously running thread of its own, does using only the manager write lock guarantee that the old plugin stops?

**Answer:** No. There must be explicit shutdown/cancellation/await for plugin-owned threads/executors along with TCCL/ThreadLocal cleanup.

## 25. Summary and References

**Remember the proper workflow:**

1. **Keep the shared API in the parent.**
2. **Build v1/v2 into independent artifacts** with the same implementation binary name but different loader generations.
3. **Verify and prepare v2** before replacing active; if prepare fails, keep v1 serving.
4. **Quiesce/drain old calls** using properly designed locks or generation leases.
5. **Publish v2 in a controlled manner**, then retire v1 and close resources.
6. **Clear roots to the old generation** so the JVM has the opportunity to GC the loader and unload classes; do not demand immediate unloading.
7. **Observe and test** behavior, class identity, API compatibility, errors, and resource lifecycle.

Authoritative documentation:

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, delegation, `findLoadedClass`, runtime class identity.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): creating loaders from URLs, named constructor, `close()`, concurrency warnings.
- [Java SE 17 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): read/write locking for lifecycle handoff.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, `getClassLoader`, and runtime type tokens.
- [JLS 17 — §§12.2, 12.4, 12.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, initialization, and unloading.
- [JVMS 17 — §5.3 Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining/initiating loaders and loading constraints.
- [Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog:class+load`, `-Xlog:class+unload`, and JVM diagnostics.
