# Java Extension Lifecycle: Discovery, Code Loading, Initialization, Invocation, and Shutdown

## 1. The Big Picture

A Java application with *runtime extensibility* allows adding behavior through separately deployed components (*plugins*, *extensions*, or *service providers*). For example, a document-processing tool can locate a JAR containing a format converter, verify compatibility, load the converter, invoke processing, and stop it when no longer needed.

Distinguish three responsibilities:

- **Contract (API/contract):** the interfaces and data types understood by both host and plugin, such as `Extension`, `HostContext`, request/response types, and error-handling rules.
- **Artifact:** the JAR or Java module containing code, resources, and provider declarations.
- **Host/manager:** discovers, selects, validates, loads, instantiates, starts, dispatches calls to, monitors, stops, and releases resources.

**Discovering a JAR does not mean code in the JAR has been loaded. Loading a class does not mean creating an instance; creating an instance does not mean the plugin is ready to serve. Calling `stop()` does not mean the JVM has unloaded the classes.** That is why the lifecycle must be modeled explicitly.

### Sample State Flow

```text
Artifact + metadata
   │
   ▼
DISCOVERED ──check source, version, dependencies──► VALIDATED
                                                      │
                                                      ▼
                                              LOADED (classes)
                                                      │
                                                      ▼
                                             CREATED (instance)
                                                      │
                                                      ▼
                                           INITIALIZING / start()
                                               │            │
                                       error/rollback     success
                                               ▼            ▼
                                             FAILED       ACTIVE
                                                            │
                                                    execute()/invoke
                                                            │
                                                            ▼
                                              QUIESCING (stop accepting work)
                                                            │
                                                            ▼
                                               STOPPED / close()
                                                            │
                                                drop all references
                                                            ▼
                                             MAY BE UNLOADED (GC)
```

This is an **application-designed state machine**, not built-in JVM state names. The `STOPPED` state only describes the logical lifecycle. Class unloading is a possibility that depends on the eligibility for garbage collection of the class loader and its associated classes.

| Milestone | What does the host do? | Transition condition |
| --- | --- | --- |
| Discovery | Locates artifacts, manifests, or provider declarations | Candidates exist to evaluate |
| Validation | Checks source, API/JDK version, dependencies, identity, policy | Only accepts eligible artifacts |
| Loading | Selects `ClassLoader`/`ModuleLayer`, loads and links required classes | No missing class or incompatibility errors |
| Creation | Creates instance via SPI/factory | Provider matches the contract |
| Initialization | Passes context, allocates resources, runs readiness checks | `start` completes |
| Invocation | Dispatches requests by ID/capability, manages errors and concurrency | Plugin remains `ACTIVE` |
| Quiesce/stop | Blocks new requests, waits for in-flight requests, cleans up resources | Plugin has stopped working |
| Cleanup | Removes from registry/callbacks, closes loader if owned | Retains no references causing leaks |

## 2. Designing a Stable Contract Before Using Runtime Loading

A minimal contract might look like:

```java
public interface Extension {
    String id();
    void start(HostContext context);
    String execute(String request);
    void stop();
}
```

This is a non-standalone illustration; a runnable Java 17+ program is in section 4. When building a real contract, decide:

1. **Identity and capabilities.** `id` must be unique within the host scope; there should be a version, task group/capabilities, and a policy when two plugins share the same ID. Do not rely on `ServiceLoader` order to pick a priority plugin.
2. **State and idempotence.** Only call `execute` after `start` succeeds, and make no new calls once stopping begins; `stop` should be safe if called again.
3. **Resource ownership.** The plugin is responsible for closing threads, executors, sockets, streams, watchers, and listeners it creates. The host is responsible for the registry, dispatcher, and loaders it creates.
4. **Scoped context.** Pass a small interface for permitted services (logger, configuration, necessary data); do not pass entire internal host objects.
5. **Binary/API compatibility.** An update to an interface, method signature, or dependency can cause `LinkageError` or `AbstractMethodError` even when class names do not change; version and run compatibility tests.
6. **Errors and rollback.** Define which errors disable a provider, retry conditions, startup/shutdown timeouts, and how to reclaim resources when `start` only partially completes.

Host and plugin must share **the exact same definition** of `Extension` and shared DTOs. In Java, type identity depends on **fully qualified class name + defining class loader**. Two classes with the same name defined by two different loaders cannot be cast to one another. Shared APIs are typically placed in a stable artifact owned by the host's or a parent's class loader; avoid accidentally bundling an extra copy of the API into each plugin JAR.

## 3. Stages and Practical Mechanisms

### 3.1. Discovery — Identifying Candidates

Common discovery approaches:

- **Registry/configuration:** the host reads a list of IDs, artifact paths, versions, and enable/disable permissions.
- **JAR directory:** the host lists files in an allowed directory. Listing files and reading manifests does not require executing code inside the JAR.
- **Java SPI on classpath/unnamed module:** place `META-INF/services/<fully-qualified-service-type>` in the JAR, with one provider class name per line.
- **JPMS named modules:** the providing module uses `provides service.Type with impl.Provider;`; the consuming module uses `uses service.Type;`. `ServiceLoader.load(layer, ServiceType.class)` can locate providers from the layer and its parent layers.

Example `META-INF/services/app.api.Extension` file:

```text
sample.HelloExtension
```

Do not scan every class and use reflection just to identify providers when a descriptor or module declaration already exists. `ServiceLoader` is **lazy**: creating the loader does not mean all providers are instantiated; iterating `iterator()` or `stream()` can trigger provider lookup and loading. `ServiceLoader.stream()` and `Provider.type()` help inspect the provider type before calling `get()` in appropriate cases, though this is not a security validation mechanism for third-party code.

`ServiceConfigurationError` can occur during iteration due to a malformed descriptor, missing/invalid provider, constructor failure, or inability to instantiate the provider. The order in which providers are discovered must not be treated as a business priority rule. `ServiceLoader.reload()` **only clears the loader instance's provider cache**, does not automatically stop old instances, and does not redefine already-loaded classes.

### 3.2. Code Loading (*class loading*) — Getting Class Loader Boundaries Right

| Approach | Suited For | Points to Watch |
| --- | --- | --- |
| Provider on classpath at startup | Fixed plugins packaged with the application | Shared classpath space, difficult to replace already-loaded JARs |
| Dedicated `URLClassLoader` | Loading plugin JARs while the program is running | Managing parent delegation, dependencies, cleanup, and leaks |
| `ModuleLayer` | JPMS plugins with explicit module configuration | Readability/exports, dependency resolution, and more complex module layering |

`ClassLoader.loadClass(...)` locates and loads a class via the loader mechanism; **it does not automatically invoke constructors or application-defined `start` methods**. The JVM also performs linking (*verification, preparation, resolution*) and class initialization when initialization triggers occur. Static initializers or constructors can fail **before** the host reaches `start`; therefore, avoid placing hard-to-rollback startup logic in static initializers.

With `URLClassLoader`, the host's parent loader typically supplies the `app.api.Extension` contract, while the child loader supplies `sample.HelloExtension` and private libraries. Parent delegation rules are not a plugin security mechanism. In particular, a plugin running **in the same JVM** can use the process's privileges; separating class loaders primarily addresses class lookup, dependency isolation, and relative lifecycle management.

### 3.3. Instantiation and Startup (*instantiate/start*)

Providers can be created via `ServiceLoader`, a factory, or a DI container. When using the classpath SPI, a normal provider class must meet `ServiceLoader`'s instantiation requirements (such as an appropriate no-argument constructor). `start(context)` is a **custom business convention**; neither Java nor `ServiceLoader` calls it automatically.

Inside `start`, the plugin can validate configuration, open connections, load resources, register listeners, and run readiness self-checks. The host adds the instance to the request-serving registry only once `start` succeeds. If it fails partway through, the plugin must clean up opened resources; the host marks it `FAILED`, avoids dispatching to it, and can disable the candidate while keeping the main application running.

If dependencies exist among multiple plugins, determine startup order, detect dependency cycles, and stop **in reverse order** so dependent plugins stop before service-providing plugins.

### 3.4. Business Invocation (*invoke*)

The host selects a provider through the registry based on `id`, capability, or policy. Before calling, verify the `ACTIVE` state and input contract. For production, clearly define:

- **Concurrency:** is a single instance thread-safe? Does the host synchronize, create instances per request, or allow concurrent calls across threads? `ServiceLoader` instances are not designed for arbitrary concurrent use across multiple threads.
- **Timeouts:** the host sets deadlines, concurrency limits, and backpressure. `Future.cancel(true)` primarily requests an interrupt; it does not guarantee terminating uncooperative plugin code.
- **Failure isolation:** distinguish returnable business errors from configuration/class-loading errors or fatal errors; log plugin ID, version, stage, and correlation ID; only retry operations with appropriate idempotency/safety.
- **TCCL:** some libraries use `Thread.currentThread().getContextClassLoader()` to locate resources/services. If the host temporarily swaps TCCL when calling a plugin, it must restore the original loader in `finally`.
- **Observability:** measure `start` duration, invocation latency, in-flight requests, errors, timeouts, state, and `stop` duration per plugin.

### 3.5. Quiescing, Stopping, and Cleanup (*quiesce/stop/close*)

Recommended sequence:

1. Transition to `QUIESCING`, remove from the router to block new requests.
2. Wait for in-flight requests to finish within a deadline; handle cancellation/handoff if the deadline is exceeded.
3. Call `stop()` or `close()`, unregister listeners/callbacks, and close all executors, threads, sockets, streams, watchers, or native resources owned by the plugin.
4. Remove references from registries, caches, callbacks, `ThreadLocal`, thread context class loaders, instances, and reflection objects pointing to plugin classes.
5. Close the `URLClassLoader` if the host owns it, recording status and any cleanup errors; do not let one cleanup failure mask other independent cleanup tasks.

`URLClassLoader.close()` releases files/JARs opened by the loader and prevents that loader from loading new classes/resources of its own; **already-loaded classes and objects may still remain usable**. Closing the loader does not automatically stop the plugin, and **does not guarantee class unloading**. Class unloading can only happen after no references retain the class loader/its classes and GC decides to collect them. Common leak sources include still-running threads, `ThreadLocal`, TCCL, static caches, listeners, schedulers, or lambdas/callbacks still held by the host.

**Hot reload** typically requires a new loader and a new instance: validate artifact → load/`start` new → readiness → shift traffic to new → drain old requests → `stop` old → drop references/close old loader. `ServiceLoader.reload()` does not replace this workflow. If state must transfer between versions, use a neutral format (JSON/stable API records) instead of implementation objects from the old loader.

## 4. Runnable Java 17+ Example: Plugin JAR via SPI

The example separates **host/API** from the **provider JAR**. The host dynamically loads the JAR with `URLClassLoader`, locates the provider via `ServiceLoader`, invokes `start → execute → stop`, and closes the loader. Uses JDK 17+; no Maven or Gradle required.

Structure:

```text
demo/
├─ src/
│  ├─ app/api/HostContext.java
│  ├─ app/api/Extension.java
│  ├─ app/host/Main.java
│  └─ sample/HelloExtension.java
└─ providers/
   └─ META-INF/services/app.api.Extension
```

**`src/app/api/HostContext.java`**:

```java
package app.api;

public interface HostContext {
    void log(String message);
}
```

**`src/app/api/Extension.java`**:

```java
package app.api;

public interface Extension {
    String id();
    void start(HostContext context);
    String execute(String request);
    void stop();
}
```

**`src/sample/HelloExtension.java`**:

```java
package sample;

import app.api.Extension;
import app.api.HostContext;

public final class HelloExtension implements Extension {
    private HostContext context;
    private boolean active;

    @Override
    public String id() {
        return "hello";
    }

    @Override
    public void start(HostContext context) {
        if (active) {
            throw new IllegalStateException("Already started");
        }
        this.context = context;
        active = true;
        context.log("started " + id());
    }

    @Override
    public String execute(String request) {
        if (!active) {
            throw new IllegalStateException("Plugin is not active");
        }
        return "Hello, " + request + "!";
    }

    @Override
    public void stop() {
        if (!active) {
            return; // Safe to call repeatedly
        }
        active = false;
        context.log("stopped " + id());
        context = null;
    }
}
```

**`providers/META-INF/services/app.api.Extension`** (exactly one provider line):

```text
sample.HelloExtension
```

**`src/app/host/Main.java`**:

```java
package app.host;

import app.api.Extension;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: java -cp build/host app.host.Main <plugin.jar>");
        }

        URL jarUrl = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { jarUrl }, Extension.class.getClassLoader())) {

            ServiceLoader<Extension> providers =
                ServiceLoader.load(Extension.class, pluginLoader);
            List<Extension> running = new ArrayList<>();

            try {
                for (Extension extension : providers) {
                    if (!"hello".equals(extension.id())) {
                        continue;
                    }

                    extension.start(message ->
                        System.out.println("[host] " + message));
                    running.add(extension);
                    System.out.println(extension.execute("Java"));
                }

                if (running.isEmpty()) {
                    throw new IllegalStateException("No hello provider found");
                }
            } finally {
                // Stop in reverse start order even if execute throws an error.
                for (int i = running.size() - 1; i >= 0; i--) {
                    try {
                        running.get(i).stop();
                    } catch (RuntimeException ex) {
                        System.err.println("Stop failed: " + ex);
                    }
                }
            }
        } // URLClassLoader.close() after stop.
    }
}
```

From the `demo` directory, open **PowerShell on Windows**. Ensure JDK 17+ `java`, `javac`, `jar` are in `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/plugin | Out-Null
javac -encoding UTF-8 -d build/host src/app/api/HostContext.java src/app/api/Extension.java src/app/host/Main.java
javac -encoding UTF-8 -cp build/host -d build/plugin src/sample/HelloExtension.java
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item providers/META-INF/services/app.api.Extension build/plugin/META-INF/services/app.api.Extension
jar --create --file build/hello-plugin.jar -C build/plugin .
java -cp build/host app.host.Main build/hello-plugin.jar
```

**Exact expected stdout:**

```text
[host] started hello
Hello, Java!
[host] stopped hello
```

Why does this work?

1. `build/host` contains the contract and host; `hello-plugin.jar` contains `sample.HelloExtension` and the `META-INF/services/...` descriptor, **without a duplicate copy** of `app.api.Extension`.
2. The parent of `pluginLoader` is the loader that loaded the host API. Thus `HelloExtension` genuinely implements the exact `Extension` known to the host.
3. `ServiceLoader.load(Extension.class, pluginLoader)` sets up provider lookup; the `for` loop iterates and creates the instance. `start` is an **explicit host call**, not automatic SPI behavior.
4. After `execute`, the `finally` block stops every started plugin and the `try-with-resources` block closes the loader. Output contains no message for closing the loader because `close()` does not print to stdout.

On Linux/macOS replace `New-Item`/`Copy-Item` with `mkdir -p`/`cp`; the Java commands stay the same. This sample is intentionally minimal: a production host must also verify the JAR source, timeouts, thread safety, readiness, rollback if `start` allocates resources before failing, and hot-swap rules.

## 5. Errors by Stage: Diagnosing the Root Cause in the Right Place

| Milestone | Symptoms | Checks |
| --- | --- | --- |
| Discovery | Provider not found | Does `META-INF/services/...` match the exact API name? Is the descriptor inside the JAR? Are `provides/uses` right for modules? |
| Loading/linking | `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedClassVersionError`, `LinkageError` | Missing library, wrong classpath/loader, bytecode for newer JDK, duplicate classes/API or dependencies |
| Instantiation | `ServiceConfigurationError`, constructor/static initialization error | Provider implements contract properly, has valid instantiation mechanism, avoid side effects in static initializers |
| `start` | Opens partial resources then throws error | Roll back each resource, do not insert plugin into registry, log stage and root cause |
| Invocation | Exception, wrong result, race, or hang | Input/output contract, thread safety, deadline, concurrency limit, logging and retry policy |
| `stop`/cleanup | Threads/files still alive, loader not GC'd | Block new calls, drain in-flight, close all executors/streams/callbacks, remove caches/TCCL/references |

Misconceptions to avoid:

- **"Finding the JAR means the provider has already run."** Discovery may only read metadata, while loading/initialization/invocation are separate steps.
- **"`ServiceLoader` will call `start()` and `stop()`."** No: the host/framework defines and calls its own lifecycle API.
- **"`reload()` will replace the currently running code."** No: it clears the provider lookup cache; old class definitions/instances do not change automatically.
- **"Closing the class loader will kill threads and unload classes."** No: threads/objects may persist; unloading is not guaranteed.
- **"Same class name means same type."** Not if the defining class loaders differ.
- **"A separate loader is a sandbox for untrusted code."** No: running untrusted code requires process boundaries, restricted OS privileges, and resource limits.

## 6. Safe Operations and Upgrades

To evolve from this example into a reliable plugin manager, you typically need to add:

- **Manifest/version compatibility:** plugin ID, version, API version, minimum JDK, dependencies, checksum/signature, source provenance, capabilities; reject mismatches early.
- **Synchronized state machine:** atomic state transitions, registry entry exposed only after readiness, reject new calls during `QUIESCING`.
- **Dependency lifecycle:** startup order by dependencies, reverse shutdown order; detect cycles and cascading startup failures.
- **Resource ownership:** host manages loaders; plugin manages its own resources; clean up thoroughly on success, mid-flight error, or hot reload.
- **Fault management:** timeouts, quotas, health checks, circuit breakers/quarantine, in-flight request handling, and retry policies.
- **Security:** accept artifacts only from verified sources. Class loaders do not restrict plugin privileges within the JVM; untrusted code requires separate processes.
- **Observability and leak checks:** measure init/stop latency, in-flight counts, error rates, number of old loaders still alive across upgrades; hunt for threads/TCCL/`ThreadLocal` retaining class loaders.

A hot-upgrade workflow is typically **validate new artifact → create new loader/instance → start and readiness → shift traffic → drain old requests → stop old → drop references, close old loader**. If the new version fails to become ready, keep the old version serving and clean up the partially started new version. Do not pass objects specific to the old class loader directly to the new version; transfer state through stable data/contracts instead.

### Self-Assessment Checklist

- [ ] Shared API is versioned and only a single definition is shared by host and plugins.
- [ ] Discovery, loading, class initialization, provider creation, business start, invocation, and stop are clearly separated.
- [ ] JAR source, metadata, dependencies, and compatibility are verified before activation.
- [ ] Host dispatches only to `ACTIVE` plugins; concurrency, timeouts, and error policies are defined.
- [ ] Plugins that fail to start roll back cleanly; shutdown blocks new requests before cleanup.
- [ ] No callbacks/threads/caches/TCCL retain the old loader across version swaps.
- [ ] Real testing covers: loading, processing, failures at start/invocation, stopping, loading a new version, and leak monitoring.

**Official API Documentation (Java 17):** [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).