# Creating a New Loader or Layer Generation for a New Plugin Version

## 1. Why create a new “generation”?

A Java system extensible at runtime may be serving requests with plugin `report:v1` when release `report:v2` arrives. The goal is to load and test v2 without breaking v1 requests, then route new requests to v2, let v1 finish its work, and release resources.

**You cannot simply copy over the JAR and call `Class.forName` again.** The JVM identifies a runtime class by **its binary name and its defining ClassLoader**. If loader L1 already defined `com.example.report.ReportPlugin` from v1, that class does not turn into v2 bytecode when the JAR file on disk changes. The standard deployment mechanism is to create a **new defining loader L2**, or create a **new ModuleLayer with new loaders**, so the same binary name can coexist under two runtime identities.

~~~text
Host API / parent loader H
       |
       +-- Generation g101 → Loader L1 → Plugin v1 → old request R1
       |
       +-- Generation g102 → Loader L2 → Plugin v2 → new request R2

Implementation names may be identical;
(typeName, definingLoader L1) != (typeName, definingLoader L2).
Host API is defined by H, so both v1 and v2 implement contract H.
~~~

**A generation** is not just a version number. A generation must describe a consistent set: plugin artifact, dependency versions, classloader or module layer, class/provider instances, configuration, state, resources, and lifecycle. Two redeployments of **the same** `2.0.0` can have different generation IDs.

### Four easily confused operations

| Operation | Creates new runtime class identity? | Switches request routing? | Stops old plugin? |
| --- | --- | --- | --- |
| Replacing JAR on disk | No for already-defined classes | No | No |
| `ServiceLoader.reload()` on old service loader | No: only clears provider cache | No | No |
| `new URLClassLoader(...)` then loading new version | Yes if class is defined by new loader | No, must publish manually | No |
| `ModuleLayer.defineModulesWithOneLoader(...)` / `ManyLoaders(...)` on new configuration | Yes for modules/classes defined by new loaders | No, must publish manually | No |

Achieving **safe hot replacement** requires class identity, API boundaries, candidate validation, atomic publication, request draining, rollback, and cleanup.

## 2. Preconditions to lock down before upgrading

Before loading v2, the host should explicitly know:

- **Plugin ID and artifact:** name, version, digest/signature, and **immutable** JAR/module path. Do not mutate bytes in a JAR currently read by the old loader.
- **Host contract:** `Plugin` API, DTOs, exceptions, and event types must be defined in the parent loader or shared API module; do not mix duplicate contract copies inside plugin-private loaders.
- **Dependency graph:** which libraries are shared and which belong privately to each generation. Avoid placing library v1 in the parent if v2 needs a different version that parent-first delegation would override with v1.
- **Config/state:** does v2 need a new config schema, is old data backward compatible, and who performs migration?
- **Health/capability:** what conditions must be verified before publishing? E.g., API version, provider ID, dependency presence, constructor, database migration dry-run, warmup.
- **Lifecycle:** is the generation stateless or does it hold connections, thread pools, timers, listeners, thread-locals, caches, and native resources?
- **Traffic:** can we wait for v1 requests to finish; if a timeout occurs, do we cancel, keep v1 temporarily, or roll back?
- **Trust:** is the plugin trusted; classloaders/module layers are **not** a sandbox for executing malicious code.

A suggested generation record:

~~~text
Generation
  pluginId: report
  pluginVersion: 2.0.0
  generationId: report-2.0.0-iteration-4
  artifactDigest: SHA-256 of the actual JAR
  dependencyManifest: locked list of versions/digests
  loaderOrLayer: object defining classes for the generation
  providerInstances: selected services
  state: CREATED / READY / ACTIVE / RETIRING / STOPPED
  inFlight: number of requests holding a lease
  resources: executors, connections, listeners owned by the generation
~~~

**Separate plugin version from generation ID:** the same version can be reloaded multiple times after a rollback or config change. For logging and troubleshooting, record artifact digest, generation, and loader/layer identity.

## 3. Fundamentals: class identity, parent-first, and shared API

By default, `ClassLoader` delegates to its parent before defining a class itself. `URLClassLoader` uses this model for standard classpath loading.

~~~text
HostApiLoader H:   com.example.spi.Plugin, Request, Result
    |
    +-- PluginLoader L1:
    |     report-v1.jar, json-lib-v1.jar
    |
    +-- PluginLoader L2:
          report-v2.jar, json-lib-v2.jar
~~~

When both plugin implementations implement the exact interface defined by H, the host can invoke v1/v2 through `Plugin`. Conversely, if a plugin bundles and defines its own copy of `com.example.spi.Plugin` via uncontrolled child-first loading, the object may fail to cast to the host's `Plugin` even though `getName()` is identical. **Type identity is class name + defining loader, not class name alone.**

Do not place `report-v1.jar` or private v1 dependencies on the host parent classpath. If the parent has already defined the same class name, L2 will see the old class via delegation, defeating isolation. Use plugin-private JARs per generation; keep only sufficiently stable APIs/DTOs in the parent.

### 3.1. Do not pass private objects directly between two versions

Even if both v1 and v2 have a class `com.vendor.JsonNode`, if two loaders define them independently, their runtime types differ. A v1 `JsonNode` object cannot automatically be cast to v2. When transferring state or data, use host-owned stable DTOs, schema-governed serialized payloads, or explicit gateway APIs. Do not treat Java serialization of private objects across generations as safe migration by default.

### 3.2. What is isolated and what is not

Two loaders can have separate class metadata/static fields/caches for self-defined classes; v1 and v2 can coexist in the JVM. However, heap, CPU, native process resources, security permissions, and JVM crashes remain shared. To bound faults/resources at process level, use separate plugin worker processes/containers.

## 4. Workflow to create a new generation with URLClassLoader

For plugin JARs on the classpath or JARs not using named module layers:

1. **Stage artifact:** write v2 to a separate path `plugins/report-v2.jar`, verify checksum/signature, and lock dependency files. Avoid overwriting artifacts being read by loader v1.
2. **Create loader:** `new URLClassLoader(urlsOfV2, hostApiLoader)`. The URL list must contain v2 and the exact versions of private dependencies.
3. **Discover entrypoint:** `Class.forName(entryBinaryName, true, loader)` or `ServiceLoader.load(Plugin.class, loader)` if the JAR declares an SPI.
4. **Instantiate:** instantiate the v2 provider, casting only through the parent's shared API.
5. **Validate/warm up:** check ABI/API version, config, health, functionality, and resources. If validation fails, stop/close the candidate and keep generation v1 active.
6. **Publish:** the host updates the active registry/snapshot to v2 via a synchronization mechanism that selects the generation and issues leases.
7. **Drain v1:** old requests keep using v1 until completion or according to timeout/cancellation policy.
8. **Release v1:** stop the provider, unregister listeners, shut down executors/threads, restore TCCL, close `URLClassLoader`, and drop all strong references.

**Illustrative snippet, not standalone**:

~~~java
URLClassLoader candidateLoader = new URLClassLoader(
        new URL[] {Path.of("plugins/report-v2.jar").toUri().toURL()},
        Plugin.class.getClassLoader());

Class<?> impl = Class.forName(
        "com.example.report.ReportPlugin", true, candidateLoader);
Plugin instance = (Plugin) impl.getConstructor().newInstance();

// Validate instance before publishing.
// On failure branch or when stopping the generation: clean up instance + loader.
~~~

Creating a loader does not necessarily load all classes immediately; most loading is **lazy**. Therefore, validation must not check only the constructor: invoke representative execution paths to catch `NoClassDefFoundError`/`NoSuchMethodError` early rather than waiting for the first request.

### 4.1. close() is not a class-unloading command

`URLClassLoader.close()` closes file/resource handles opened by the loader per the API. Classes already defined and still referenced remain alive. `close()` does not automatically interrupt threads, call `Plugin.stop()`, or force GC/class unloading. If another thread is concurrently loading classes when `close()` occurs, the outcome of that load is undefined. **Close only after no work still needs classes/resources from the old generation.**

## 5. Runnable Java 17+ lab: same binary name, two independent generations

This lab has two separate JARs yet **the same class name `demo.impl.Greeter`**, one returning `v1` and the other `v2`. The host uses a single `demo.api.Plugin` interface, creates two `URLClassLoader`s, and swaps the active pointer.

**Lab scope:** runs sequentially to demonstrate class identity and publishing; `AtomicReference.getAndSet` in the lab is **not** a safe generation-closing solution for servers with concurrent requests (see Section 7).

### 5.1. Directory layout

~~~text
hot-swap-demo/
├── src/
│   ├── api/demo/api/Plugin.java
│   ├── host/HotSwapDemo.java
│   ├── v1/demo/impl/Greeter.java
│   └── v2/demo/impl/Greeter.java
├── out/                   # generated on compile
└── jars/                  # generated when creating JARs
~~~

File `src/api/demo/api/Plugin.java`:

~~~java
package demo.api;

public interface Plugin extends AutoCloseable {
    String version();
    String greet(String name);

    @Override
    default void close() throws Exception {
        // Hook for real generations; demo holds no resources.
    }
}
~~~

File `src/v1/demo/impl/Greeter.java`:

~~~java
package demo.impl;

import demo.api.Plugin;

public final class Greeter implements Plugin {
    @Override
    public String version() {
        return "v1";
    }

    @Override
    public String greet(String name) {
        return "Xin chao " + name + " tu v1";
    }
}
~~~

File `src/v2/demo/impl/Greeter.java` has **the same binary name**:

~~~java
package demo.impl;

import demo.api.Plugin;

public final class Greeter implements Plugin {
    @Override
    public String version() {
        return "v2";
    }

    @Override
    public String greet(String name) {
        return "Xin chao " + name + " tu v2";
    }
}
~~~

File `src/host/HotSwapDemo.java`:

~~~java
import demo.api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;

public final class HotSwapDemo {
    record Generation(String id, URLClassLoader loader, Plugin plugin)
            implements AutoCloseable {
        @Override
        public void close() throws Exception {
            try {
                plugin.close();
            } finally {
                loader.close();
            }
        }
    }

    static Generation prepare(String id, Path jar) throws Exception {
        URLClassLoader loader = new URLClassLoader(
                new URL[] {jar.toUri().toURL()},
                Plugin.class.getClassLoader());
        try {
            Class<?> type = Class.forName(
                    "demo.impl.Greeter", true, loader);
            Plugin plugin = (Plugin) type.getConstructor().newInstance();

            if (!id.equals(plugin.version())) {
                throw new IllegalStateException("Wrong plugin version");
            }
            return new Generation(id, loader, plugin);
        } catch (Exception | LinkageError failure) {
            loader.close();
            throw failure;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Pass plugin-v1.jar plugin-v2.jar");
        }

        try (Generation g1 = prepare("v1", Path.of(args[0]))) {
            AtomicReference<Generation> active =
                    new AtomicReference<>(g1);
            System.out.println("active-before="
                    + active.get().plugin().greet("Lan"));

            try (Generation g2 = prepare("v2", Path.of(args[1]))) {
                // Verify candidate before switching the active pointer.
                System.out.println("candidate="
                        + g2.plugin().greet("Lan"));

                Generation old = active.getAndSet(g2);
                System.out.println("active-after="
                        + active.get().plugin().greet("Lan"));
                System.out.println("old-reference="
                        + old.plugin().greet("Lan"));
                System.out.println("same-impl-class="
                        + (old.plugin().getClass()
                                == g2.plugin().getClass()));
                System.out.println("shared-contract="
                        + (old.plugin() instanceof Plugin
                                && g2.plugin() instanceof Plugin));

                // Lab has no concurrent requests; clear active pointer
                // before g2 closes at the end of try.
                active.compareAndSet(g2, null);
            }
            // g1 is kept until the end of the outer try before closing.
        }
    }
}
~~~

Explanation of key details:

- Host classpath `out\host` contains the API and `HotSwapDemo`, and **does not** contain `demo.impl.Greeter`. Therefore L1 and L2 can define separate implementations.
- `Plugin.class.getClassLoader()` is the shared parent: both v1 and v2 use the same runtime `Plugin` type, so casting is valid.
- `prepare` creates the loader, loads the class, instantiates it, and validates `version()` **before** returning `Generation`. If loading/validation fails, it cleans up the candidate loader.
- `AtomicReference.getAndSet` swaps the active pointer from g1 to g2. `old.plugin()` still exists because the old object has not been released yet, illustrating two coexisting generations.
- `old.plugin().getClass() == g2.plugin().getClass()` is `false` despite identical binary names: their defining loaders differ. Yet both are `Plugin` from the parent.
- Closing g1/g2 happens only after the illustrative calls; the lab has no background threads. Production must use leases/draining.

### 5.2. Compile and run commands

Run the commands in **PowerShell** inside the `hot-swap-demo` directory with **JDK 17+**:

~~~powershell
New-Item -ItemType Directory -Force out\host,out\v1,out\v2,jars | Out-Null

javac --release 17 -encoding UTF-8 -d out\host src\api\demo\api\Plugin.java src\host\HotSwapDemo.java
javac --release 17 -encoding UTF-8 -cp out\host -d out\v1 src\v1\demo\impl\Greeter.java
javac --release 17 -encoding UTF-8 -cp out\host -d out\v2 src\v2\demo\impl\Greeter.java

jar --create --file jars\plugin-v1.jar -C out\v1 .
jar --create --file jars\plugin-v2.jar -C out\v2 .

java -cp out\host HotSwapDemo jars\plugin-v1.jar jars\plugin-v2.jar
~~~

Expected stdout:

~~~text
active-before=Xin chao Lan tu v1
candidate=Xin chao Lan tu v2
active-after=Xin chao Lan tu v2
old-reference=Xin chao Lan tu v1
same-impl-class=false
shared-contract=true
~~~

These results depend on putting only `out\host` on the host classpath, building the two JARs from the proper sources, and ensuring the parent contains no implementation. If both implementation identities match, inspect the process classpath and parent delegation before concluding the JVM “shared” a class across plugins.

### 5.3. Why not hot-replace using the old classloader?

If `Class.forName("demo.impl.Greeter", true, g1.loader())` is called again after v1 is already loaded, the old loader still uses the v1 class identity. Replacing the contents of `plugin-v1.jar` on disk while the JVM is running is not a reliable update method: already-loaded classes do not change and resource lookups can be affected. **Use a new artifact path, a new loader, and a new generation lifecycle.**

## 6. JPMS: creating a new ModuleLayer for modular plugin versions

Plugins using **named modules** have `module-info.java` metadata with `requires`, `exports`, `opens`, `uses`, and `provides`. To bring a new version into the JVM, the host can build a new `Configuration` from a `ModuleFinder` and then define a **new ModuleLayer** with the corresponding loader mapping.

### 6.1. JPMS flow

~~~text
plugin-v2 modular JAR(s), separate module path
               |
        ModuleFinder.of(path)
               |
 stable parent layer (contains host API module)
               |
 parent.configuration().resolve(finder, afterFinder, roots)
               |
        Configuration v2 (module graph)
               |
 parent.defineModulesWithOneLoader(cf, parentLoader)
                OR
 parent.defineModulesWithManyLoaders(cf, parentLoader)
               |
         ModuleLayer v2 + loader(s)
               |
 provider discovery/instantiate/validate
               |
     registry publish + drain old layer
~~~

Illustrative Java method, **not a standalone program**; requires imports and a real module path:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

static ModuleLayer createPluginLayer(
        Path moduleDirectory, String rootModule) {

    ModuleLayer parent = ModuleLayer.boot();
    ModuleFinder finder = ModuleFinder.of(moduleDirectory);

    Configuration cf = parent.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of(rootModule));

    return parent.defineModulesWithOneLoader(
            cf, ClassLoader.getSystemClassLoader());
}
~~~

**Precondition:** the host API module that the plugin `requires` must exist in the parent configuration or be properly resolved. If the host uses a custom parent layer, replace `ModuleLayer.boot()` with the actual stable parent. `ModuleFinder.of` sees only the modules pointed to by the path; it does not perform deployment by itself.

`defineModulesWithOneLoader` creates one loader for the modules in the new configuration; `defineModulesWithManyLoaders` creates one loader per module. Both create **new** mappings; `defineModules` with a custom mapping suits advanced cases and requires tight control over delegation/readability.

### 6.2. Sibling layers instead of making v1 the parent of v2

When v1 and v2 use **the same module name** `com.example.greeter`, place both versions in **two separate module paths** and create **two sibling layers** from the stable API parent:

~~~text
           Stable parent layer (API)
             /                \
       Layer g101          Layer g102
       greeter v1          greeter v2
       Loader(s) L1        Loader(s) L2
~~~

If v2 is created as a child layer whose **parent is the v1 layer**, resolution may see the module already present in the parent and fail to bring v2 into the configuration as intended. The parent must represent the shared portion **excluding the version you want to replace**. Do not cram two modules of the same name into one configuration expecting JPMS to pick a version per request: module resolution is not a Maven dependency resolver.

### 6.3. Providers in a modular plugin

Example provider module descriptor:

~~~java
// module-info.java — descriptive example, not standalone.
module com.example.greeter {
    requires com.example.api;
    provides com.example.api.Plugin
        with com.example.greeter.Greeter;
}
~~~

If the shared API is a named module in the parent, the host can discover providers through the candidate layer:

~~~java
// Illustrative snippet, not standalone; Plugin is the host API,
// candidateLayer has been defined and validated.
ServiceLoader<Plugin> loader =
        ServiceLoader.load(candidateLayer, Plugin.class);
Plugin candidate = loader.findFirst().orElseThrow();
~~~

A caller module using `ServiceLoader` must declare `uses <service>` per JPMS. `ServiceLoader.load(layer, service)` can see providers in the layer and ancestor layers; **do not use `findFirst()` as a guaranteed policy to select v2** if multiple providers exist. Verify the provider module, ID/version, and ownership of the candidate after discovery.

A `ModuleLayer` **has no general `close()` method**. For an old JPMS generation to become eligible for GC/unloading, you must stop providers, release threads/resources, and drop references to the `ModuleLayer`, `Module`, loaders, and classes/instances. Do not infer immediate class unloading merely from removing the layer from the active registry.

### 6.4. When to choose OneLoader vs ManyLoaders?

| Criterion | `defineModulesWithOneLoader` | `defineModulesWithManyLoaders` |
| --- | --- | --- |
| Loaders per layer | One new loader for all modules of the configuration | One new loader per module |
| Type/shared state management | Modules share a loader yet still have JPMS boundaries | Modules have distinct runtime loader identities |
| Module package constraints | Can fail on invalid overlapping packages/split delegation | Greater loader separation, yet must still satisfy the module graph |
| Configuration/lifecycle | Simpler when multiple modules are released together | More flexible per module, but adds complexity |
| Plugin version isolation | Creates **new layer generation** | Creates **new layer generation** |

**One layer does not necessarily mean one plugin:** a layer can contain multiple plugin modules and dependencies. When replacing only one plugin in a group, you must know which configuration/loader group needs to be recreated. JPMS module readability does not replace state migration or request routing.

## 7. Shifting traffic with leases to avoid closing an in-use generation

### 7.1. AtomicReference is not enough with concurrent requests

Deceptively simple code:

~~~java
// Illustrates a race, DO NOT use as-is in production.
Generation g = active.get();
g.plugin().handle(request);

// Deployment thread runs while the request is still processing:
Generation old = active.getAndSet(candidate);
old.close(); // May close resources right underneath another thread's request!
~~~

Even though `getAndSet` swaps the pointer atomically, there is a window between the request reading `g` and registering usage. Thus if deployment closes `old` immediately, the request may encounter an already-closed connection/executor.

### 7.2. Designing lease issuance consistent with the swap

You must synchronize **selecting the active generation and incrementing the active-use counter** with swapping the active pointer. An easy-to-reason-about design is a read/write gate:

~~~text
Request thread                        Deploy coordinator
-----------------------------         ------------------------------
acquire read gate
  g = active
  g.inFlight++ (register lease)
release read gate
run g.plugin()                        build/validate candidate v2
                                      acquire write gate
                                        old = active
                                        active = v2
                                        old.state = RETIRING
                                      release write gate
request finishes
  g.inFlight--
                                      await old.inFlight == 0
                                      stop old background tasks/resources
                                      close old loader if appropriate
                                      drop strong references to old
~~~

This is an **algorithm, not a standalone Java program**. A `ReentrantReadWriteLock` can guard the pointer and lease acquisition, while the invocation itself runs **outside** the read lock so deployments are not blocked for the duration of requests. Counters/state require sufficiently strict synchronization or an atomic state machine. Once a generation is marked `RETIRING`, issue **no new leases** for it.

Every lease should be closed in `finally` or try-with-resources; if a request throws an exception or is cancelled, it must still release. Do not count only HTTP requests: plugins may hold timers, queue consumers, schedulers, subscriptions, JMX registrations, or long-lived callbacks. Those resources have their own lifecycles and ownership.

### 7.3. State machine

~~~text
CREATED
   |
   v
VALIDATING ---> FAILED ----> RELEASED
   |
   v
READY --------> ABORTED ---> RELEASED
   |
   v
ACTIVE
   |
   v
RETIRING
   |
   +---- inFlight > 0 → WAIT/DRAIN (with timeout policy)
   |
   v
STOPPED
   |
   v
RELEASED
~~~

Invariants:

- Only a `READY` candidate may be published.
- The swap for new requests must have a clear linearization point; do not publish half v1/half v2 in the same registry snapshot.
- The old generation remains alive for work accepted prior to the swap.
- Close the old generation only after ensuring no workload still needs it; timeouts must have safe handling rather than defaulting to forced `close()`.
- If plugins share dependency group resources, manage reference counts/lifecycles at **the group level**, and do not close a parent dependency loader while other children still use it.

## 8. Rollback: easier before publish than after publish

| Stage | On failure | Action |
| --- | --- | --- |
| Check artifact/config | Missing JAR, wrong signature or API version | Reject immediately, do not create candidate |
| Create loader/layer | Dependency/package resolution failure | Clean up candidate, v1 stays active |
| Instantiate/warm-up | Provider health or constructor failure | Abort candidate, v1 stays active |
| Publish | Inconsistent registry update | Do not accept partial state; apply atomic transaction/snapshot |
| After publish | v2 increases error rate or latency | Can switch back to v1 **if v1 is still valid and data is compatible** |
| v1 already closed | Need to revert to version v1 | Create a **new v1 generation**, do not “resurrect” a closed loader |
| v2 already wrote new data | v1 cannot read new schema | State/data migration or dedicated rollback policy, not just swapping pointers |

**Rollback does not undo side effects.** Plugin v2 may have written to databases, sent events, altered schemas, created files, or called external APIs. Before deploying, establish backward compatibility, idempotency, transactional boundaries, and a data migration strategy. If a rollback window must be maintained, the old generation can be kept in a standby state after draining, though not indefinitely due to memory/resource pressure.

### 8.1. State migration between two generations

~~~text
Plugin v1 state
   │ export via host-owned DTO/schema
   ▼
Stable serialized snapshot
   │ validate/transform versioned schema
   ▼
Plugin v2 import
   │ health checks + warmup
   ▼
Publish v2 → drain v1 → retire v1
~~~

Do not pass objects of L1-private classes directly to L2 and cast them: `ClassCastException` may occur. Depending on business needs, migration requires versioned snapshots, event replay, dual-read/dual-write, or external state storage. If two versions cannot operate on the same data, do not promise “zero-downtime.”

## 9. ServiceLoader, TCCL, and dependency visibility

### 9.1. ServiceLoader of the new generation

For classpath plugins registering `META-INF/services/<serviceFQCN>`:

~~~java
// Illustrative snippet, not standalone.
ServiceLoader<Plugin> discovered =
        ServiceLoader.load(Plugin.class, candidateLoader);

List<Plugin> candidates = discovered.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

For JPMS, use `ServiceLoader.load(candidateLayer, Plugin.class)` when service and provider modules are declared appropriately. Verify **which generation a provider belongs to**; parent classloaders/layers may expose additional providers from shared scopes. When multiple providers exist, `findFirst()` is not a stable priority mechanism under business policy.

**`ServiceLoader.reload()` only clears the provider cache** of that service loader; it does not change JAR URLs, define v2 classes over v1, or stop old provider instances. To truly get v2, use a **ServiceLoader bound to the new loader/layer** and create new provider instances per lifecycle.

### 9.2. Thread Context ClassLoader

Some frameworks/SPIs use `Thread.currentThread().getContextClassLoader()`. When invoking a plugin, the host may need that generation's TCCL:

~~~java
// Illustrative, not standalone: candidateLoader and task already exist.
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(candidateLoader);
    task.run();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

**Always restore in `finally`** when the thread returns to a pool. If a plugin spawns its own threads or `ExecutorService`, those threads can retain the old loader's TCCL, pinning it in memory. Stopping a generation must stop tasks and clean up resources registered in host/global registries.

### 9.3. Private dependencies

If v1 needs `json-lib:1.x` while v2 needs `json-lib:2.x`, the two generation loaders should contain only their own specific dependencies. If `json-lib` v1 is already in the host parent, parent-first delegation may cause v2 to still use v1. Keep the parent API **free of version-specific private types**; if the public API uses such a type, it becomes a shared version boundary requiring versioning/adapters.

With JPMS, build configurations for each generation from separate module paths and a stable parent. Do not assume the module version field in `ModuleDescriptor` can resolve Maven-style conflicts automatically; resolve the dependency graph before defining the layer.

## 10. Releasing the old generation and class loader leak bugs

A `URLClassLoader` or JPMS layer removed from the active pointer **can still stay alive** while strong references remain to any corresponding object/class/loader.

Common leak sources:

- requests/snapshots/registries still holding the v1 provider;
- `Thread.contextClassLoader`, `ThreadLocal`, daemon threads, executors, timers, scheduled jobs;
- event listeners/observers/callbacks registered in host singletons;
- unregistered JDBC drivers/JMX/logging providers/native libraries;
- `Class<?>`, `Method`, proxies, `MethodHandle`, reflection caches, or static global maps;
- dependency group loaders still in use by other plugins;
- open resources and in-flight class loading when `URLClassLoader.close()` is called.

### Recommended cleanup order

1. Mark `RETIRING`, blocking new lease issuance.
2. Wait for identified requests/background activities; handle timeouts per policy.
3. Call `Plugin.stop()/close()` and shut down executors, cancel timers, and unregister listeners.
4. Release connections/files/sessions, restore TCCL in thread pools.
5. Clear host registries/snapshots/caches holding references to instances or `Class<?>`.
6. For classpath `URLClassLoader`: call `close()` once no thread is loading classes/resources through it.
7. Drop all references to the old generation's loader/layer/modules/providers and private classes.
8. Observe heap, Metaspace, loaded/unloaded classes, and the reference graph. **Do not** assert immediate GC/unloading.

`ModuleLayer` has no `close()` equivalent to `URLClassLoader`; lifecycle shutdown is performed by the host/plugin, while reclaiming classes depends on the JVM/GC and references.

### Observing with JDK tools

~~~powershell
jar tf jars\plugin-v2.jar
jar --describe-module --file jars\plugin-v2.jar

java -Xlog:class+load=info -cp out\host HotSwapDemo jars\plugin-v1.jar jars\plugin-v2.jar

# For a running Java process; substitute the real PID before calling:
jcmd 12345 help
jcmd 12345 VM.classloaders
~~~

These are **illustrative diagnostic commands**. `jar --describe-module` may report an automatic module for non-modular JARs or show JDK dependency info; `jcmd` options vary by JVM. Heap dumps and thread dumps help locate strong references/TCCL retaining the old generation.

## 11. Comparison table and common mistakes

| Situation | Misconception | Correct approach |
| --- | --- | --- |
| v2 has same class name as v1 | Call `Class.forName` on L1 again | New loader/layer generation L2 |
| Overwrite old JAR | Will hot-swap loaded classes | Store immutable v2 artifact, point new loader/layer to v2 |
| Parent contains v1 implementation | L2 plugin prefers classes in v2 JAR | Parent-first may pick v1 class; fix loader boundary |
| Provider in v2 not found | Repeatedly call `ServiceLoader.reload()` on v1 | Create a service loader with L2/v2 layer and check SPI/module metadata |
| A thread is using v1, deploy closes immediately | Atomic swap is safe enough | Lease/refcount + drain/stop |
| Class cast fails despite same type name | Must be a JVM bug | Compare defining loaders, unify API in parent |
| v2 uses a dependency with a different ABI | JVM resolves the right version automatically | Verify classpath/module graph and API compatibility before publish |
| JPMS v2 has same module name as v1 | Defining v2 as a child of layer v1 is fine | Sibling layers from a stable API parent |
| v2 startup fails | Switch routing first then test | Validate/warm up candidate before publish |
| Rollback after DB migration | Switching pointer back to v1 is enough | Check data/side effects; have a migration/compat plan |
| `URLClassLoader.close()` is called | Classes must unload immediately | Drop references, monitor GC/Metaspace, stop threads |
| Untrusted user plugin | Classloader is sufficient security isolation | Process/container isolation and OS permissions |

## 12. Test matrix and deployment workflow

A generation-based architecture should pass the following tests:

| Test | Setup | PASS condition |
| --- | --- | --- |
| Parallel load | Load v1 and v2 with same binary name | Two implementation classes with different loaders; shared parent API |
| Candidate fail | v2 missing class, dependency, or config | v1 remains active; candidate is cleaned up |
| Health/warm-up | Check API version, call representative methods | Publish only when candidate is READY |
| Atomic routing | Deploy under many concurrent requests | Each request sticks to a consistent generation |
| Drain | Hold an unfinished v1 request during swap | Do not close v1 before lease release |
| Background task | v1 has a scheduler or listener | Stopped/unregistered by generation ownership |
| Early rollback | v2 fails immediately after publish | Revert to still-valid v1 without dropping requests |
| Late rollback | v1 already stopped/closed | Recreate v1 generation; data remains compatible |
| Dependency versions | v1 and v2 use different library versions | No confusion of API/private classes |
| TCCL/SPI | Provider discovery under a thread pool | Provider from right generation, TCCL restored |
| JPMS sibling layers | Same module name, v1/v2 in two separate layers | Accurate graph/layer/loader context |
| Repeated updates | V1 → V2 → V3 → V4 | No leaked threads, resource handles, or retained loaders |
| Cluster rollout | Multiple JVM instances | Clear routing/version labels on every instance |

### Production deployment workflow

~~~text
1. Artifact verified (v2 + dependencies)
2. Candidate loader/layer created
3. Instantiate + validate + warm up
4. READY → publish active generation atomically
5. New requests → v2, existing leases → v1
6. Observe metrics and rollback if policy requires
7. Drain v1 → stop providers/background tasks
8. Close resources / URLClassLoader, drop references
9. Mark old generation RETIRED; monitor leaks
~~~

**Canary/rollback:** if high safety is required, a portion of traffic can be routed to v2 and the ratio gradually increased; in that case the registry must support multiple active generations by rule and leases per generation, not a single pointer. When v2 affects data schemas, rollback also requires compatibility at the storage/protocol level.

### Useful metrics

Tag request logs with `pluginId`, `version`, `generationId`, artifact digest, and loader/layer identity. Track in-flight leases, startup/validation duration, error rate, p95/p99 latency, active background tasks, thread count, open file handles, heap, Metaspace, and class unloading. Across multiple JVMs, swapping in one process does not synchronize the remaining processes; an out-of-process rollout coordinator is needed.

## 13. Checklist before marking an upgrade complete

1. **Artifact:** version and dependency manifests locked, immutable JAR/valid checksum.
2. **Boundary:** API/DTOs defined in parent; private classes do not leak into parent classpath.
3. **Generation:** new loader/layer actually defines new classes; does not accidentally pick old implementation from ancestor.
4. **Validation:** constructor, SPI/service discovery, API compatibility, health, config, and representative methods pass.
5. **State:** import/export data via stable schema; rollback has clear conditions, without ignoring side effects.
6. **Publication:** consistent routing, request leases issued atomically with generation selection.
7. **Drain:** old requests/background work tracked, timeout policy does not corrupt data.
8. **Cleanup:** stop plugin, unregister resources, restore TCCL; close URLClassLoader if applicable; drop references.
9. **JPMS:** module configuration/parent layer and loader mapping correct; understand the limitation that `ModuleLayer.close()` does not exist.
10. **Monitoring:** per-generation logs and metrics sufficient to detect leaks or mismatches.
11. **Security:** run only trusted code in the JVM; do not use classloaders as a sandbox.
12. **Evidence:** test repeated deployments, rollbacks, and concurrency before declaring plugin replacement safe.

**Conclusion:** for a new plugin version to truly appear in the JVM, you must create a **new ClassLoader or ModuleLayer generation**, prepare and verify before publishing, coordinate requests by generation, and then drain/stop the old version. `ServiceLoader.reload()` does not replace already-defined bytecode; `URLClassLoader.close()` does not force class unloading; nor does `ModuleLayer` manage lifecycle automatically. Safe hot replacement is the combination of **class identity, dependency isolation, routing, rollback, and resource ownership**.

## 14. Java SE 17 References

- ClassLoader — delegation/class identity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- URLClassLoader — parent loader and close semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- ModuleLayer — layer definition, OneLoader/ManyLoaders: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- ModuleFinder — discovering modular JARs: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Configuration — module resolution: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- ServiceLoader — ClassLoader/ModuleLayer lookup, reload: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Module — runtime JPMS readability: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JVM Specification 17, chapter 5 — Loading/Linking/Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html