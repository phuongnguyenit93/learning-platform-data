# Separating Lightweight Constructors from Resource Opening and Activation

In a Java system with runtime extensibility, a plugin may be **discovered**, **instantiated**, **prepared with resources**, **activated to accept work**, and finally **deactivated and have its resources released**. If all of these steps are crammed into the constructor, a simple operation like calling `new`, `ServiceLoader.Provider.get()`, or instantiating via dependency injection can already open sockets, start threads, register callbacks, modify files, or begin accepting requests. At that point, the host struggles to control startup order, handle mid-way failures, and ensure an unready plugin will not receive work.

Design principle: **the constructor only sets up identity and minimal configuration; `prepare()`/`initialize()` checks and opens resources; `activate()`/`start()` transitions the plugin into the serving state**. The host owns this sequence and always has a `close()`/`stop()` mechanism to roll back when a step fails.

This article focuses on the **plugin lifecycle** in Java 17+: why these three responsibilities must be separated, building a valid state machine, handling rollback on initialization failure, orchestrating multiple plugins, verifying with runnable code, and avoiding common resource leaks.

## 1. Distinguishing Three Actions with Different Meanings

Imagine a data-analysis plugin that needs a log file path, connection config, and a callback registered with the host:

| Phase | What It Should Do | What It Should Not Do |
| --- | --- | --- |
| **Construction** – constructor | Accept immutable config, perform cheap null and format checks, assign fields, create initial state object | Open sockets/files, spawn threads, connect to DBs, register listeners, or self-announce readiness |
| **Preparation** – prepare/init | Verify actual resources, open files/sockets/connections under granted permissions, load metadata, check dependencies, create operational components without taking traffic yet | Expose the plugin to requests before preparation completes; leak resources if prepare fails |
| **Activation** – activate/start | Start schedulers/consumers, register serving endpoints or callbacks, publish readiness once all conditions are met, transition to ACTIVE | Keep serving if an activation step has failed |
| **Deactivation/close** | Stop accepting work, drain/cancel in-flight work, unregister, close resources in order, and clear references | Close files/schedulers while handlers are still permitted to use them; treat close as equivalent to JVM class unloading |

A **lightweight constructor** does not mean doing nothing. It can validate the plugin name, normalize simple values, copy immutable configuration, and set state NEW. What must be avoided are **side effects that are hard to reverse or can block for a long time**. Calling `new` should not put load on external services or mutate global state.

**Prepare** is the phase where resources have been allocated, yet the plugin is **not ready to serve**. For example, a TCP connection is open or a file already has a writer; the host is still not routing requests to the plugin.

**Activate** is the point of operational commitment. A system requiring explicit readiness should not send traffic just because the constructor returned an instance.

## 2. Bad Design Example: Constructor Opens and Self-Activates

The sample below is an **anti-pattern illustration**, not a complete class:

~~~java
final class RiskyPlugin {
    private final java.net.Socket connection;

    RiskyPlugin(String host, int port) throws java.io.IOException {
        connection = new java.net.Socket(host, port); // I/O in constructor
        HostCallbacks.register(this);                 // publishes instance prematurely
    }
}
~~~

In this illustration, `HostCallbacks` is just an assumed host API and is not defined, so this snippet **does not compile standalone**. It demonstrates two distinct risks:

1. **I/O in the constructor:** instantiating an object merely to inspect metadata can already time out, throw `IOException`, or hold open a socket. If a subsequent step fails, the caller might not have a complete instance on which to call `close()`.
2. **Letting `this` escape from the constructor:** the registry may invoke callbacks while the object is still being constructed; fields or internal structures may not be initialized yet. This is a publication and initialization-order bug, not merely a performance issue.

Real-world situations are often harder: a constructor calls a third-party library, which creates an executor/thread or registers a JDBC driver underneath. If allocation has no central point and ownership is not recorded, the host struggles to know which resources need closing after a failure.

Instead, the constructor should only accept the required parameters:

~~~java
final class PluginConfig {
    final String id;
    final java.nio.file.Path outputFile;

    PluginConfig(String id, java.nio.file.Path outputFile) {
        this.id = java.util.Objects.requireNonNull(id);
        this.outputFile = java.util.Objects.requireNonNull(outputFile);
    }
}
~~~

This is a simple standalone class that can be placed in `PluginConfig.java`; it has not opened any file and has not activated any service. A Java 17 `record` can be used when the configuration data fits; note that a `Path` object is a path reference, **not proof that the file exists or is accessible**. Real I/O checks belong in `prepare`.

## 3. State Model for the Plugin Lifecycle

A typical model:

~~~text
                 create instance
                       |
                       v
                      NEW
                       |
                   prepare OK
                       v
                   PREPARED
                       |
                  activate OK
                       v
                     ACTIVE
                       |
              stop accepting requests
                       v
                    STOPPING
                       |
                 close resources
                       v
                     CLOSED
~~~

If an error occurs at any phase, the host needs to tear down already-allocated parts and move to a stopped/closed state. Failure and cleanup can be represented as:

~~~text
NEW ── prepare error ────────────┐
PREPARED ── activate error ──────┼──> cleanup/close ──> CLOSED
ACTIVE ── handler/stop error ────┘
~~~

This is a **conceptual diagram**, not forcing every implementation to use the exact same state names. The runnable example in Section 6 uses four states—**NEW, PREPARED, ACTIVE, CLOSED**—to keep the article uncluttered; `STOPPING`/`FAILED` are additional states commonly needed for runtimes with threads and long-running tasks.

### Invariants to Protect

- **NEW:** holds only configuration; does not yet own operational plugin resources.
- **PREPARED:** required resources have been opened successfully, but the plugin has not been published as ready.
- **ACTIVE:** serving conditions are met and the host may dispatch calls to the plugin.
- **CLOSED:** the plugin accepts no new work; resources it owns have been requested to be released.
- **Valid transitions:** `start`/`activate` must not be called before `prepare`; `handle` must not run when `NEW`/`PREPARED`/`CLOSED`; avoid calling `prepare` multiple times unless the API is explicitly designed to support it.
- **Rollback:** if `prepare`/`activate` fails, resources allocated prior to the failure point must also be reclaimed.
- **Idempotent close:** calling `close` a second time should be safe and must not re-open resources; if an earlier `close` failed, a mechanism is needed to track incomplete cleanup.

These invariants protect **orchestration behavior**, not security against untrusted plugins. A malicious plugin can still spawn threads or open sockets in its constructor despite any convention saying otherwise.

## 4. Lifecycle Interface: Host Controls, Plugin Executes

A contract can draw a clear separation:

~~~java
public interface ManagedPlugin extends AutoCloseable {
    String id();                    // lightweight metadata
    void prepare() throws Exception;  // open and verify resources
    void activate() throws Exception; // activate serving
    String handle(String input) throws Exception;
    @Override
    void close() throws Exception;    // cleanup
}
~~~

This is an **interface example** that can be saved in `ManagedPlugin.java`. Real systems should define specific exception types instead of `throws Exception` if you need to distinguish configuration errors, I/O errors, dependency errors, or activation errors. **Java `AutoCloseable`** fits `try-with-resources` or `finally`, but by itself it does not define `NEW`/`PREPARED`/`ACTIVE` states; host and plugin must agree on the contract.

Two-sided responsibilities:

**Host/plugin manager:**
- Selects or instantiates plugins only based on metadata, version, and compatibility.
- Decides when to `prepare`/`activate`, along with timeouts and resource limits.
- Does not publish the instance into the serving registry before `activate` succeeds.
- Catches errors, closes allocated resources, and records state.
- On shutdown: stops routing requests, waits for in-flight tasks to finish, closes the plugin, and releases the loader.

**Plugin implementation:**
- Keeps constructor cheap; does not self-register externally.
- Makes `prepare` atomic in cleanup: on failure, does not leave resources open unmanaged.
- In `activate`, does not report success before truly being capable of serving.
- Executes `handle` only in the `ACTIVE` state.
- Allows `close` to be called both when `prepare`/`activate` are incomplete and when active.

The key point is that **the host manages readiness**, rather than merely asking whether a plugin exists. A Java object successfully constructed with `new` is not proof that the plugin or its dependencies are ready.

## 5. Why Phase Separation Matters Especially with ServiceLoader and Dedicated Class Loaders

In an SPI-style extension model, the host may call:

~~~java
ServiceLoader<ManagedPlugin> loader =
        ServiceLoader.load(ManagedPlugin.class, pluginClassLoader);
for (ManagedPlugin plugin : loader) {
    // Iterating providers may instantiate the provider.
}
~~~

This is an illustrative snippet **placed inside a method that already has a valid `pluginClassLoader` and `ManagedPlugin` interface in a shared loader**; it requires importing `java.util.ServiceLoader` and is not a standalone runnable program. With the standard provider mechanism, calling `iterator.next()` or `ServiceLoader.Provider.get()` can **instantiate the provider**. If the constructor opens DB connections or starts threads on its own, a simple discovery operation turns into uncontrolled activation.

With a lightweight constructor:

1. The host discovers the list of providers and inspects metadata/capabilities.
2. The host decides which plugins are permitted to run and which resources to grant.
3. The host instantiates the provider without opening expensive resources yet.
4. The host calls `prepare()` in the required dependency order.
5. The host calls `activate()` once readiness conditions are satisfied.
6. Only then does the host place the plugin into the registry for clients to use.

In systems using **one ClassLoader per plugin**, constructors may run right after a JAR is loaded. If a constructor starts threads holding the context class loader, loads extra internal classes, or holds static references in the host, later unloading/reloading becomes difficult. A lightweight constructor **reduces** the window for side effects, but **does not guarantee class initialization won't run**: static initializers or provider factory logic can still have side effects. You must inspect static blocks and factory paths too, not just the constructor body.

Also distinguish **loading a class** from **initializing a class** and **instantiating an object**: they are related events, not identical ones. `ServiceLoader`'s laziness does not make a heavy constructor safe; it merely delays when the side effect occurs.

## 6. Runnable Java 17+ Example: Constructor Opens No Files, Prepare Opens, Activate Decides Readiness

The example below illustrates **two plugin instances** with independent log file configurations. The first plugin prepares and activates successfully. The second plugin prepares, then intentionally fails in `activate()`. Both are closed via `finally`. The output file is opened using `BufferedWriter` to verify that resource allocation happens in **prepare**, not in the constructor.

No external libraries outside the JDK and no network connections are required. The code runs on JDK 17+; temporary log files are deleted when `main` finishes.

### 6.1. Complete Source Code

Create a file **`PluginLifecycleDemo.java`** with the following content:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public final class PluginLifecycleDemo {
    enum State { NEW, PREPARED, ACTIVE, CLOSED }

    static final class FilePlugin implements AutoCloseable {
        private final String id;
        private final Path file;
        private final boolean failActivation;
        private BufferedWriter writer;
        private State state = State.NEW;

        FilePlugin(String id, Path file, boolean failActivation) {
            this.id = Objects.requireNonNull(id);
            this.file = Objects.requireNonNull(file);
            this.failActivation = failActivation;
        }

        synchronized State state() {
            return state;
        }

        synchronized void prepare() throws IOException {
            require(State.NEW);
            BufferedWriter candidate = Files.newBufferedWriter(
                    file, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            try {
                candidate.write("prepared " + id + "\n");
                candidate.flush();
                writer = candidate;
                state = State.PREPARED;
            } catch (IOException | RuntimeException failure) {
                try {
                    candidate.close();
                } catch (IOException cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
                throw failure;
            }
        }

        synchronized void activate() throws IOException {
            require(State.PREPARED);
            if (failActivation) {
                throw new IllegalStateException("activation rejected");
            }
            writer.write("activated " + id + "\n");
            writer.flush();
            state = State.ACTIVE;
        }

        synchronized String handle(String value) throws IOException {
            require(State.ACTIVE);
            String result = id + ":" + value.toUpperCase(Locale.ROOT);
            writer.write("processed " + result + "\n");
            writer.flush();
            return result;
        }

        private void require(State expected) {
            if (state != expected) {
                throw new IllegalStateException(
                        "expected " + expected + " but was " + state);
            }
        }

        @Override
        public synchronized void close() throws IOException {
            if (state == State.CLOSED) {
                return;
            }
            state = State.CLOSED;
            if (writer != null) {
                try {
                    writer.close();
                } finally {
                    writer = null;
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("plugin-lifecycle-");
        Path goodFile = dir.resolve("good.log");
        Path badFile = dir.resolve("bad.log");

        try {
            FilePlugin good = new FilePlugin("good", goodFile, false);
            FilePlugin bad = new FilePlugin("bad", badFile, true);

            System.out.println("constructorFiles=" +
                    Files.exists(goodFile) + "," + Files.exists(badFile));

            try {
                good.prepare();
                System.out.println("preparedExists=" +
                        Files.exists(goodFile));
                good.activate();
                System.out.println("result=" + good.handle("hello"));
            } finally {
                good.close();
            }
            System.out.println("goodState=" + good.state());

            try {
                bad.prepare();
                bad.activate();
            } catch (IllegalStateException failure) {
                System.out.println("badError=" + failure.getMessage());
            } finally {
                bad.close();
            }
            System.out.println("badState=" + bad.state());
            System.out.println("goodLog=" + String.join("|",
                    Files.readAllLines(goodFile, StandardCharsets.UTF_8)));
            System.out.println("badLog=" + String.join("|",
                    Files.readAllLines(badFile, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(goodFile);
            Files.deleteIfExists(badFile);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

`FilePlugin` models the lifecycle of a resource-backed plugin. The constructor only stores `id`, `Path`, and a failure-simulation flag; it **does not call `Files.newBufferedWriter`**, open sockets, create files, or self-publish the instance. These Java classes live in the same file so the article is easy to copy and run; in real projects, the interface, plugin implementation, and host can reside in different artifacts/modules.

### 6.2. Compiling and Running

From the directory containing `PluginLifecycleDemo.java`, using **JDK 17 or later**:

~~~powershell
javac --release 17 -encoding UTF-8 PluginLifecycleDemo.java
java PluginLifecycleDemo
~~~

The same two commands also apply on Linux/macOS terminals with `javac` and `java` installed. The program creates an OS temporary directory without depending on fixed Windows paths. Files created in the temporary directory are cleaned up by `main`'s `finally` block; in this lesson, the log files are read before deletion.

**Exact stdout when executed:**

~~~text
constructorFiles=false,false
preparedExists=true
result=good:HELLO
goodState=CLOSED
badError=activation rejected
badState=CLOSED
goodLog=prepared good|activated good|processed good:HELLO
badLog=prepared bad
~~~

This output has been verified with `javac --release 17` and actual Java execution.

### 6.3. Reading the Meaning of Each Stdout Line

- **constructorFiles=false,false:** after creating both plugins, neither `good.log` nor `bad.log` exists yet. This verifies that **the constructor did not create the two resource files**; only the temporary directory had been created earlier by the host.
- **preparedExists=true:** `good.prepare()` opened the log file via `Files.newBufferedWriter` and wrote the line `prepared good`. This is the resource-opening phase.
- **result=good:HELLO:** only after `activate()` succeeds is the `handle("hello")` call permitted to execute.
- **goodState=CLOSED:** `finally` guarantees `close` is called after the serving phase; state transitions to `CLOSED`.
- **badError=activation rejected:** `bad.prepare()` succeeded, but `activate()` intentionally threw `IllegalStateException`. The error is caught by the host while `close` is still called in `finally`.
- **badState=CLOSED:** the startup failure **does not leave a plugin in a serving state**; `close` has requested releasing the resource.
- **goodLog=prepared good|activated good|processed good:HELLO:** the resource was used sequentially during preparation, activation, and handling; the `|` symbol joins lines when printing for readability.
- **badLog=prepared bad:** the failing plugin only wrote data during `prepare`, never writing `"activated"` or `"processed"`. The file is kept just long enough to inspect the result, then the host deletes it on exit.

### 6.4. Why Does prepare Hold the Resource in a candidate Variable?

The code uses a local variable `candidate` before assigning to the `writer` field:

~~~java
BufferedWriter candidate = Files.newBufferedWriter(
        file, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
try {
    candidate.write("prepared " + id + "\n");
    candidate.flush();
    writer = candidate;
    state = State.PREPARED;
} catch (IOException | RuntimeException failure) {
    try {
        candidate.close();
    } catch (IOException cleanupFailure) {
        failure.addSuppressed(cleanupFailure);
    }
    throw failure;
}
~~~

**This is an excerpt found in the `prepare` method of the example**, not a standalone file. Its meaning: the newly opened resource is treated as **provisional** until preparation succeeds. If writing or flushing fails, the code closes `candidate` before rethrowing. If `close` also fails, the cleanup error is attached as a suppressed exception rather than accidentally masking the original cause.

That **does not guarantee the file is deleted** after an error. `CREATE_NEW` may already have created the file right before writing failed. Cleaning up leftover artifacts on the filesystem is a separate responsibility that may belong to the host/workspace manager. Distinguish **releasing a handle** from **rolling back every durable side effect**.

### 6.5. Why Must activate Not Assume prepare Has Already Run?

The `require(State.PREPARED)` method ensures activation happens only from a valid state. If the host calls `activate` right after `new`, the program reports `IllegalStateException` instead of raising an incidental error like `NullPointerException` when `writer` is still `null`.

Similarly, `handle()` calls `require(State.ACTIVE)` to prevent accepting work when the plugin is not yet activated or has already closed. Checking state at API boundaries helps catch orchestration bugs early.

From a testability perspective, having **three distinct points**—constructor → prepare → activate—makes it easier to write tests that pinpoint failure scope. Constructing an object does not mean an external service has been activated.

## 7. Rollback Rules When a Startup Phase Fails

Suppose a plugin needs three resources: a log file, a DB connection, and a consumer subscribed to a message broker. `prepare` might open the file and create the connection, while `activate` subscribes the consumer. If the second or third step fails, the resources already acquired **must still be reclaimed**.

A safe sequence looks like:

~~~text
new plugin
   |
   v
prepare()
   |-- open file
   |-- create connection
   |-- validate readiness
   |      |
   |      +-- if error: close what was opened; report failure
   v
activate()
   |-- register consumer / publish capability
   |      |
   |      +-- if error: undo partial registration, close connection/file
   v
ACTIVE / publish to host registry
~~~

Failures in `prepare`/`activate` may be checked exceptions, runtime exceptions, timeouts, or thread interruptions. Do not clean up resources only when a single specific `IOException` occurs.

### 7.1. Host Uses finally/try-with-resources at the Right Time

A minimal orchestration pattern:

~~~java
ManagedPlugin plugin = createPlugin();
boolean published = false;
try {
    plugin.prepare();
    plugin.activate();
    registry.publish(plugin.id(), plugin);
    published = true;
    // Plugin is now ACTIVE and managed by the registry.
} catch (Exception startupFailure) {
    if (published) {
        registry.unpublish(plugin.id());
    }
    try {
        plugin.close();
    } catch (Exception cleanupFailure) {
        startupFailure.addSuppressed(cleanupFailure);
    }
    throw startupFailure;
}
~~~

This is **algorithmic illustrative code**, not a standalone compilable Java snippet: `createPlugin`, `registry`, and the publish/unpublish policy must be defined, and it must sit in a method declaring appropriate `throws Exception`. A real host must ensure `registry.publish` is **atomic**, or roll back publication if publication can happen partially before throwing an exception. Do not treat a `published` boolean as a universal transactional solution for every registry.

The key design point is: **the host publishes the plugin only after `prepare` and `activate` succeed**; if any startup step fails, the host must close the instance and clean up any partially registered resources/callbacks.

When using `try-with-resources` to manage a plugin whose lifetime is scoped to a single method, Java automatically closes it upon leaving the block. However, for a long-lived plugin serving requests, you cannot wrap it in `try-with-resources` and then **return the plugin or register it in a runtime registry** without explicitly transferring lifecycle ownership; once the block exits, the plugin is already closed. When ownership is transferred to the manager, the manager is where `close` is called at shutdown.

### 7.2. If Cleanup Itself Throws an Error

A common mistake:

~~~java
catch (Exception original) {
    plugin.close();  // may throw another exception and mask the original error
    throw original;
}
~~~

This is an **illustrative anti-pattern**. If `close` throws `IOException`, the initial startup failure can be lost from the observable control path. Keep the startup error as the primary exception, attach resource-closing errors as suppressed, or use an appropriate `try-with-resources` structure.

If resource A depends on resource B, they usually need to be closed in **reverse order of opening** (after stopping incoming work). Ensure `close` attempts to release independent resources even if the first close call fails, while aggregating errors for diagnostics.

**Limitation note on the runnable example:** `FilePlugin` owns only a single `BufferedWriter`, so `close` can be simple. In systems with multiple resources, `close` should use multiple ordered `try`/`catch`/`finally` blocks; take care with `InterruptedException`, timeouts, and indeterminate network states.

## 8. Avoiding Implicit Activation in DI Containers, Frameworks, and Factories

`ServiceLoader` is not the only thing that instantiates plugins. Instances can appear because:

- A dependency injection container creates objects.
- A factory method or `Builder.create()` returns an implementation.
- Reflection invokes a constructor via `Constructor.newInstance()`.
- An SPI provider factory or `ServiceLoader.Provider.get()` runs.
- A test fixture creates an instance to inspect metadata/config.
- A classpath scanner or reload mechanism instantiates plugins.

If the constructor opens resources, **every instantiation path** must have full environment setup and cleanup ready. A framework calling a constructor to introspect metadata, or a test merely trying to create a mock object, could unintentionally open a DB connection.

Some frameworks support initialization hooks such as methods annotated with `@PostConstruct` or startup callbacks. Those hooks **can also be invoked early by the framework**, so understand exactly when they execute. If the host requires separating `prepare` from `activate`, do not simply move all constructor side effects into `@PostConstruct` and call that a complete solution.

A stronger approach is to provide an **explicit lifecycle contract** and let the host/plugin manager orchestrate it. The DI framework can instantiate the object first, while the plugin only serves once the manager confirms `ACTIVE`.

### Configuration Convention

The constructor can accept an immutable configuration such as:

~~~java
record PluginSettings(String id, Path outputPath) {
    PluginSettings {
        Objects.requireNonNull(id);
        Objects.requireNonNull(outputPath);
        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
    }
}
~~~

This is a standalone Java 17 illustration **requiring imports for `java.nio.file.Path` and `java.util.Objects`**, which can be placed in `PluginSettings.java` when the record is declared `public` or as a package-private record with an appropriate filename. This validates pure values in the constructor; it does not call `Files.exists()`, query a DB, or connect to the network. Checks requiring an I/O environment must be deferred to `prepare` because the environment can change between instantiation time and startup time.

## 9. Readiness to Serve Is Activation's Responsibility, Not Construction's

In a real system plugin, activation may include:

1. Starting to consume messages from a queue.
2. Registering callbacks on an event bus.
3. Publishing endpoints/capabilities in a registry.
4. Starting a scheduler or background worker.
5. Transitioning health/readiness to ready.

The point of publishing the **ACTIVE** state must occur after the necessary steps complete. If a callback can fire immediately upon registration, prepare all required internal state **before publishing the callback**. Do not do:

~~~text
publish plugin to registry
    |
    v
initialize connection
    |
    v
subscribe background worker
~~~

Under this flawed sequence, requests can arrive while the connection does not yet exist. If `initialize connection` fails, clients have already seen an unavailable plugin.

A sounder sequence:

~~~text
construct (no externally visible side effect)
    |
    v
prepare (resources acquired but not serving)
    |
    v
activate internal capability
    |
    v
publish readiness / open routing
~~~

**Note the boundary between activate and publish:** In some systems, registering a listener *is* the activation action, because events can arrive the instant it is registered. In that case, you need a mechanism blocking processing until `ACTIVE`, or design registration as atomic staging/enable. Simply reordering calls does not guarantee safety if the framework dispatches callbacks concurrently.

If activation has external side effects that cannot be completely rolled back (e.g., sending a payment command or emitting a durable event), separate **resource preparation** from **committing business tasks** and apply idempotency keys, a transactional outbox, or an appropriate recovery protocol. Lifecycle methods do not automatically create distributed transactions.

## 10. Concurrency: Do Not Close While Requests Are Still Running

Plugin runtime problems often involve multiple threads: the host is shutting down while a worker is executing `handle()`, or a new plugin is activating while the system receives requests. In those cases, a `State` enum and a few checks are unlikely to be enough.

The runnable example in Section 6 uses **`synchronized`** on `prepare`, `activate`, `handle`, `state`, and `close`. This serializes calls on **the same instance**, which works well for teaching the basic invariants. It does not solve every production issue:

- If `handle()` performs long I/O, `close()` blocks waiting on the lock and may miss the shutdown deadline.
- If callbacks spawned by the plugin's own threads do not call synchronized methods, they can continue running after `close`.
- If another plugin still holds a reference to the old instance, having the registry stop routing new requests is not enough.
- If a resource is used by another object without going through `FilePlugin`'s lock, `close` may happen while the resource is still in use.

A complete shutdown path:

~~~text
ACTIVE
  |
  | mark NOT_READY / remove from routing
  v
STOPPING
  |
  | wait for in-flight requests to drain
  | cancel/interrupt cooperative tasks if deadline expires
  | unsubscribe listeners / stop scheduler
  v
CLOSING
  |
  | close connections, streams, executors, caches
  v
CLOSED
~~~

Distinguish **quiesce** (stop accepting new work), **drain** (wait for existing work), and **close** (release resources). If a plugin uses an `ExecutorService`, design a `shutdown()`/`awaitTermination()`/`shutdownNow()` policy suited to the task types, rather than just closing sockets the instant the service begins stopping.

Lifecycle state must have proper synchronized visibility: `synchronized`, `volatile`, locks, `AtomicReference`, or a thread-safe state machine. All transitions must avoid non-atomic check-then-act patterns. For example:

~~~java
if (plugin.isActive()) {
    plugin.handle(request);
}
~~~

This is an **illustration of a race risk** if `isActive` and `handle` are not coordinated under the same synchronization mechanism: the plugin can transition to `CLOSED` in between. In a real system, the registry should issue a lease/in-flight permit or expose a `handle` API that checks state and controls lifecycle along the same call path.

## 11. Reload and ClassLoader Ownership

A Java `ClassLoader` is the unit of class namespace management; for plugins running in the JVM, a dedicated loader typically holds that plugin's implementation classes and private dependencies. A lightweight constructor alone is not enough for safe hot reload. When replacing a plugin version, you must:

1. Stop dispatching requests to the old plugin.
2. Drain or cancel in-flight tasks according to a deadline.
3. Call `stop`/`close` to terminate callbacks, executors, threads, sockets, files, and timers.
4. Unregister from the registry and drop references still holding instances/classes of the old plugin.
5. If the loader implements a `Closeable` contract like `URLClassLoader`, close the loader and its JAR resources.
6. Only then consider the old loader **eligible** for GC/unloading, provided no references remain; immediate unloading is not guaranteed.

Common sources of leaks:

- Long-lived threads retaining the plugin's **Thread Context ClassLoader**.
- `ThreadLocal`s or callbacks still stored in a host thread pool.
- Global registries holding plugin instances, `Method`s, `Class`es, or `ClassLoader`s.
- Unregistered JDBC drivers, logging adapters, shutdown hooks, or metrics listeners.
- Lambdas or scheduled tasks retained inside a host executor.
- Static singletons in shared libraries holding back-references to plugin classes.

If a plugin starts threads in its constructor, a very early initialization failure can keep the `ClassLoader` alive indefinitely. Separating construction from activation lets the host control when threads are created, when they are registered, and when they must stop.

**Security:** a dedicated class loader isolates dependencies/namespaces, not security privileges. Untrusted plugins can bypass any lifecycle convention. To run untrusted code, you must consider process isolation, file/network permissions, CPU/memory limits, and appropriate IPC mechanisms.

## 12. Test Lifecycle Behavior Properly, Not Just the Constructor

Useful tests for a plugin manager:

| Test | Expectation |
| --- | --- |
| Call constructor only | No files/sockets opened or callbacks registered; state NEW |
| Prepare succeeds | Required resources opened, state PREPARED, not accepting requests yet |
| Call handle before activate | Rejected with a clear state error |
| Activate succeeds | State ACTIVE; host can publish readiness |
| Prepare fails midway | Resources opened before the failure are closed; not published |
| Activate fails after prepare | Host cleans up resources, does not put plugin in routing |
| Close after prepare but before activate | Closes cleanly without pretending it was ACTIVE |
| Close after activate | Stops serving before closing resources |
| Close twice | Does not reopen resources or cause redundant side effects |
| Concurrent requests with stop | No new requests after quiesce; in-flight handled per policy |
| Repeated reloads | No unexpected growth in retained threads/file handles/classloaders |

The code example in Section 6 directly demonstrates four tests: constructor does not create log files, `prepare` creates the file, only successful `activate` handles work, and activation errors still trigger `close`. In production, use reproducible simulated connection/file failures rather than inducing faults in real external systems.

### Testing Prepare Failing Right When Opening a File

In the `FilePlugin` example, `prepare` uses `StandardOpenOption.CREATE_NEW`. If the target file already exists, `Files.newBufferedWriter` can throw `FileAlreadyExistsException`. In that case `writer` remains `null` and state remains `NEW`; if the host catches the error, it should call `close` to transition the instance to `CLOSED`, and then apply its policy for existing files.

This scenario is helpful because it proves **you must not handle a prepare failure by proceeding to activate**. If an existing file is a normal case, proactively adjust the file-opening policy (`CREATE`/`APPEND`/`TRUNCATE_EXISTING`), rather than silently switching from `CREATE_NEW` to overwriting inside an exception handler.

### Testing Errors After Opening a Resource

If writing or flushing the prepared data fails after `writer` was opened, the `catch` block in `prepare` attempts to close `candidate` and attaches any cleanup failure as suppressed when needed. This is the guarantee scope of **closing the handle in the illustrative code**. The file may still remain on disk and require cleanup outside the plugin. With multiple resources, rollback must be built for every allocated resource.

## 13. Common Design Mistakes and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| SPI discovery opens DB connections on its own | Constructor/factory performs I/O | Have constructor accept config; move I/O to `prepare` |
| Plugin appears in registry before it is ready | Published in constructor or before `activate` | Publish only after activation/health check |
| Startup failure leaks file descriptors/threads | No rollback of mid-way opened resources | Track ownership and close in `catch`/`finally` |
| Constructor blocks for a long time on DB/network trouble | Synchronous blocking I/O inside `new` | Move to `prepare` with timeout/cancellation |
| Activating after a failed prepare causes NullPointerException | Missing state transition guards | Require `PREPARED` before `activate` |
| Requests still arrive after close | Registry not quiesced, callbacks not unsubscribed | Stop routing, drain, then close |
| Close masks the original startup cause | Cleanup throws a new error | Preserve original error, attach suppressed or aggregate errors |
| Reload leaks ClassLoader | Threads/TCCL/caches/registries still hold references | Clean up lifecycle and drop references in the right order |
| Stop hangs | Handler blocks, holds locks, or ignores cancellation | Deadlines, drain, interrupt/cooperative stop, and monitoring |
| Restarting a CLOSED object leaves invalid resources | Restart lacks an explicit contract | Use a new instance and loader; allow restart only if the state machine is designed for it |

A noteworthy anti-pattern is **“constructor catches and swallows errors”**: in the constructor, code opens a resource, catches `IOException`, only logs it, and lets the instance be constructed successfully despite the missing resource. The host may think the plugin is ready. If the constructor only accepts configuration, this problem largely disappears; `prepare` returns a clear error and the host can transition the plugin to `FAILED`.

## 14. Decision Checklist for a New Plugin

Before accepting a plugin into the system, answer these questions:

1. **Does the constructor have side effects?** Does it open files, sockets, spawn threads, register events, call external APIs, start transactions, or mutate global state?
2. **Who owns the resources?** Where are files/sockets/executors created, which method closes them, and in what order?
3. **Does `prepare` guarantee atomic cleanup at the ownership level?** If it fails on the third step, are the two already-opened resources released?
4. **Where is the readiness-to-serve boundary?** Could the plugin be exposed by the registry before `activate` finishes?
5. **Can `handle` be called before `ACTIVE`?** The API must fail fast clearly, not rely on `NullPointerException`.
6. **What happens if `activate` fails?** Is there a cleanup workflow and is routing guaranteed to be removed?
7. **What happens if `close` fails?** Is the original error preserved, logged thoroughly, and any resource leak flagged for intervention?
8. **Does it run concurrently?** How are state, in-flight requests, callbacks, schedulers, and `close` coordinated?
9. **Is hot reload supported?** Are `ClassLoader`, TCCL, listeners, static references, and threads cleaned up properly?
10. **What must actually be tested?** Lightweight constructor, `prepare`, `activate`, failure rollback, `stop`, double-close, and reload.

## 15. Reference Documentation

- Java SE 17, **AutoCloseable** and close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- Java SE 17, **Files.newBufferedWriter**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)
- Java SE 17, **ServiceLoader** and provider instantiation timing: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17, **URLClassLoader.close**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()
- Java SE 17, **ExecutorService** and shutdown: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Conclusion:** a lightweight constructor lets you **create an object without simultaneously starting the plugin**. `Prepare` is responsible for **opening and verifying resources**. `Activate` defines **when the plugin is permitted to accept work**. `Stop`/`close` manages **reclaiming resources even when startup fails**. Separating these three phases gives the plugin host testable startup, observable state, reliable rollback, and a clear lifecycle during reload or shutdown.
