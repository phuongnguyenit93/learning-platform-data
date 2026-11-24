# Determining Which Steps Belong to ServiceLoader and Which Are Managed by the Host Application

## 1. Separating Two Responsibilities: Finding Providers and Operating Plugins

A Java extensibility system typically has two components working side by side that perform very different jobs:

- **ServiceLoader** is the standard JDK mechanism for *finding declared service providers*, loading and instantiating them on demand, maintaining a cache scoped to a ServiceLoader instance, and allowing that lookup cache to be cleared.
- **The host application (host/plugin manager)** is the component responsible for deciding *which plugins are allowed to be installed, activated, handle tasks, monitored, stopped, updated, revoked, or rolled back*. These decisions belong to business logic and operational policy, and are not built into the JDK.

For example, the host needs a **Plugin** interface and two providers implementing it. ServiceLoader helps the host discover which valid providers exist according to the metadata it can see, and instantiate objects. **ServiceLoader does not pick which provider matches a customer request, does not call start(), does not monitor HEALTHY status, and does not call stop() on application shutdown.** If the Plugin contract defines those methods, the host is the orchestrator.

The central question of this article: **which steps are handled automatically by the JDK under the ServiceLoader contract, and which steps must be designed by the host?**

Making this distinction avoids a serious architectural mistake: treating ServiceLoader as a full-featured plugin platform with lifecycle management. In reality, it is only **a discovery/instantiation component** inside a plugin platform.

## 2. Responsibility Split Table: ServiceLoader or Host?

| Lifecycle Step | Provided by ServiceLoader | Host Must Manage |
| --- | --- | --- |
| Receiving JAR file / source / plugin package | No | Verify provenance, permissions, version, policy, and store the artifact |
| Installing, uninstalling, updating artifacts | No | Manage storage location, class loader/module layer, dependencies, metadata |
| Declaring providers | Reads per SPI registration | Developer/provider publishes META-INF/services or provides; host ensures proper deployment |
| Finding providers visible to a loader/layer | Yes | Choose the right class loader/layer and plugin scope |
| Parsing service configuration, reading provider metadata | Yes | Enforce declaration policy, avoid untrusted sources |
| Basic provider checks | Yes, during locate/load/instantiate | Check **semantic** compatibility, versions, permissions, capabilities |
| Loading classes and instantiating provider objects | Yes, **lazily** when requested by API | Decide when to request, how to use, and how to handle errors |
| Caching providers within a ServiceLoader instance | Yes | Manage the lifetime of the ServiceLoader and every instance the host retains |
| Clearing ServiceLoader's cache | Yes: **reload()** | Decide when, synchronize threads, and decide whether a new artifact/loader is needed |
| Listing providers before instantiation | Possible via **stream()** and Provider.type() | Select/filter by metadata, version, priority, or custom policy |
| Choosing a provider for a tenant or feature | No | Selection rules, conflict resolution, fallbacks, priority order |
| Configuring dependencies/credentials | No | Supply only required data/permissions via interfaces/config |
| Calling init()/start()/activate() | No | Coordinate resource initialization, readiness, and state |
| Invoking business methods | No | Host/service consumer uses the provider via the SPI |
| Health checks, timeouts, retries, circuit breakers | No | Measurement, protection, and fault-isolation policies |
| Stopping tasks, draining requests, and stop()/close() | No | Host manages ordered shutdown and resource reclamation |
| Unloading classes/plugins, closing URLClassLoader | No | Host manages references, loaders, threads, caches, rollbacks |
| Logging, auditing, metrics, tracing | No platform policy | Host attaches plugin ID/version and operates telemetry |
| Ensuring plugin code safety | No | Trust boundaries, permission controls, and process isolation |

**Rule of thumb:** a step phrased as “**find classes/providers from SPI registration**” falls under ServiceLoader's capabilities; a step phrased as “**decide whether this plugin is allowed to be used or manage its state**” belongs to the host. There is some overlap: ServiceLoader can instantiate objects, but **the host decides when to request instantiation and what to do with the instance afterward**.

## 3. Lifecycle Stage Model of a Plugin

~~~text
Provider Development Team           Host / Plugin Manager                   ServiceLoader
          |                                  |                                   |
Write implementation + descriptor            |                                   |
          |                                  |                                   |
Publish plugin.jar  -----------------------> |                                   |
                                             | Verify artifact / dependencies    |
                                             | Choose loader or ModuleLayer      |
                                             | Create ServiceLoader ------------>|
                                             |                                   | Locate metadata (lazy)
                                             | Iterator / stream --------------->|
                                             |                                   | Load type
                                             |                                   | Create instance when requested
                                             | <---------------- Provider -------|
                                             | Validate ID / version / policy    |
                                             | Select / configure / start        |
                                             | Serve requests, monitor, retry    |
                                             | Drain / stop / release resources  |
                                             | Plan update/rollback              |
                                             | Create new loader/layer if needed |
                                             | reload cache per scenario ------->| Clear own cache
                                             | Close old loader when safe        |
~~~

This is a **responsibility diagram**, not a rigid sequence for every framework. One host might load providers to inspect metadata before selecting; another might inspect JAR information before creating a class loader. What remains constant is that **ServiceLoader has no install, activate, health, deactivate, or uninstall APIs**.

A typical host-defined state model:

~~~text
DISCOVERED
    |
    v
VERIFIED ----> REJECTED (invalid artifact/contract)
    |
    v
SELECTED
    |
    v
STARTING ----> FAILED (if init/start fails)
    |
    v
ACTIVE -----> DEGRADED (poor health)
    |
    v
DRAINING
    |
    v
STOPPING
    |
    v
STOPPED
    |
    v
RETIRED (references, loader, and resources managed/reclaimed)
~~~

ServiceLoader **does not store these states**. It does not know whether a provider is ACTIVE or STOPPED. Having an instance in cache also **does not mean the plugin has been activated by the host**.

## 4. What Exactly Can ServiceLoader Do?

### 4.1. Finding Registered Providers

A provider is published under two primary models:

- **Classpath/unnamed module:** a text file **META-INF/services/<binary name of the SPI>** in a JAR or classpath directory. Its contents are provider class names, one per line. For example, **META-INF/services/demo.api.Plugin** contains **demo.provider.UpperPlugin**.
- **Explicit named JPMS module:** the provider module's **module-info.java** contains **provides demo.api.Plugin with demo.provider.UpperPlugin;**. The consuming module has **uses demo.api.Plugin;** where ServiceLoader is called, along with the necessary requires/exports for the API.

ServiceLoader looks up providers **visible to the configured class loader or module layer**. Merely having a JAR present on disk **does not cause ServiceLoader to discover it** if it is not on the load path of the appropriate loader/layer.

A classpath provider class must typically be a public class, assignable to the service type, with a public no-arg constructor. With explicit named modules, there is also a valid **public static provider()** factory mechanism. These are **provider registration/instantiation** requirements, not complete plugin quality standards.

### 4.2. Instantiating Providers on Demand

A call like:

~~~java
// Illustrative snippet in the host: Plugin is the published SPI.
ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);
~~~

**Does not mean all provider constructors run immediately.** ServiceLoader locates and instantiates providers lazily when iteration or an API requesting a specific provider is executed. When using **iterator()**, **hasNext()** and **next()** perform discovery/loading work and thus can throw **ServiceConfigurationError**. These errors do not necessarily occur on the line that creates the ServiceLoader object.

Iterating over providers:

~~~java
// Illustrative snippet in a host with valid Plugin and loader.
for (Plugin candidate : loader) {
    System.out.println(candidate.id());
}
~~~

When you need to **inspect provider types only before creating objects**, you can use:

~~~java
// Illustrative snippet in a host with valid Plugin and loader.
loader.stream()
      .map(ServiceLoader.Provider::type)
      .forEach(System.out::println);
~~~

**Provider.type()** can help filter providers by metadata/type without invoking the provider constructor. However, with a named-module provider factory, type may be the **return type of provider()**, not necessarily the factory class named in `provides`. Only when **Provider.get()** is called is the provider supplied according to engine/provider rules; do not treat calling type() as a health check or a guarantee regarding side effects during later instantiation.

### 4.3. Caching Iterated Providers

A **ServiceLoader** instance remembers providers loaded/instantiated per the API rules. With an iterator, subsequent iterations first return **cached instances**, and only then lazily locate and instantiate remaining providers.

This is useful for avoiding re-instantiating providers on every loop, but it also causes confusion:

- The cache does not represent RUNNING/STOPPED state managed by the host.
- The host may hold a reference to a stopped instance even though ServiceLoader still caches it.
- You must not assume re-iterating will automatically spot a new JAR dropped into a directory not watched by the loader.
- Do not share one JVM-wide ServiceLoader across multiple tenants/layers without considering class loaders and data scope.

With the Stream API, ServiceLoader also has its own caching rules; do not equate a **Provider.get()** call with “the same singleton started by the host”. Manage selected instances under the host's own contract.

### 4.4. reload() Only Clears ServiceLoader's Cache

~~~java
// Illustrative snippet: loader is ServiceLoader<Plugin>.
loader.reload();
~~~

**reload()** clears the provider cache of **that specific ServiceLoader instance**, causing the next lookup/iteration to search for providers from scratch along its load path. It **does not**:

- Download a new JAR file from the Internet or automatically modify the application classpath.
- Directly update class definitions already loaded by the JVM.
- Initialize or call start() on all new providers.
- Call stop(), close(), or dispose() on old objects.
- Interrupt threads created by plugins or clear application caches.
- Close URLClassLoader, unload a ModuleLayer, or guarantee class unloading.
- Route in-flight requests to a new version or automatically roll back if the new version fails.

If the host still holds **Plugin old**, `old` remains a normal object after **reload()**. If the same class loader already loaded the provider class, a new instance will typically still use **the same class definition version**, rather than magically turning into new bytecode on disk.

**Note on old iterators/streams:** when reload() is called, previously obtained iterators/streams must be discarded. In Java 17, using them after the cache has been cleared can cause a **ConcurrentModificationException**. That is why the host must coordinate reload and lookup consistently.

### 4.5. Reporting SPI Configuration Errors, Not Handling Incidents for the Host

Provider configuration/instantiation errors can surface as **ServiceConfigurationError** (a subclass of **Error**, not a checked exception):

- Malformed META-INF/services file or I/O error reading it.
- Provider class name does not exist or is not visible through the loader.
- Provider class does not conform to the SPI or lacks a valid constructor/provider method.
- Constructor or provider method throws an exception.
- Dependency linkage errors preventing the provider from being loaded or initialized.

ServiceLoader **reports the error**; it does not know whether the host should halt the system, isolate the faulty plugin, use an alternate provider, quarantine it, or roll back. Those decisions must be designed by the host.

## 5. What the Host Must Manage

### 5.1. Installing, Validating, and Selecting Plugins

The host manages artifact sources, versions, checksums, signatures if any, publisher permissions, API compatibility levels, required dependencies, and authorization policies. **ServiceLoader only sees providers registered along its load path**; it does not verify signatures or evaluate business trust.

When multiple providers exist, the host needs a selection policy:
- Explicit selection by **plugin ID**, version, and capabilities.
- Rejecting providers incompatible with the contract, schema, or permissions.
- Priority explicitly defined in metadata/registry, rather than accidentally depending on JAR order.
- Clear fallback when no provider meets requirements.
- Separating system-wide selection from per-tenant selection in multi-tenant environments.

**findFirst() does not mean “the best provider”.** Provider order can depend on discovery/classloader/module graph; it is not a business ranking.

### 5.2. Activating/Starting and Executing Work

If the SPI interface defines methods such as:

~~~java
// Illustrative contract snippet, drawing on the idea from the full example below.
void start();
String handle(String input);
void stop();
~~~

Then **the host** must call them. ServiceLoader does not know the signatures or semantics of custom application methods. It only requires the object to be a valid provider of the corresponding interface/service.

A plugin may:
- Create a connection pool, threads, schedulers, or caches during start().
- Register callbacks with the host.
- Read host-supplied config and check readiness.
- Process multiple requests while ACTIVE.
- Drain in-progress work, close connections, and unregister callbacks during stop().

The host must know **when**, **how many times**, **on which thread**, and **in what order** to call each step. Clear semantics should be defined: is start() called at most once per activation or is it idempotent? Is stop() called after a partially failed start()? Can the same instance be restarted? All of these are questions of the **host contract**, not JDK ServiceLoader.

### 5.3. Monitoring, Recovery, and Decommissioning

The host decides health checks, readiness, metrics, logging, tracing, timeouts, retries, backpressure, and circuit breakers. If a plugin throws an exception during handle(), ServiceLoader does not automatically remove the provider from the registry or call stop().

For applications serving concurrent requests:
1. The host tracks the number of requests currently using the plugin.
2. When replacing with a new version, prevents new requests from going to the old version.
3. Waits for or cancels in-flight requests per policy.
4. Calls stop()/close() appropriately and verifies resources are returned.
5. Only then considers closing the loader and dropping all references.

A newly discovered provider must not become ACTIVE before passing the validation/readiness steps required by the host.

## 6. Complete Java 17 Example: Seeing the Responsibility Boundary Clearly

The example uses **one SPI and one provider in a separate JAR**, with no external library dependencies. The provider's constructor prints to stdout **solely to illustrate when ServiceLoader instantiates the object**; in real production code, constructors should be lightweight and avoid heavy side effects.

The exercise verifies four behaviors:
1. Simply creating ServiceLoader does not trigger the constructor.
2. When the host iterates providers, ServiceLoader creates the instance.
3. The host handles selection, start(), handle(), and stop() itself.
4. Caching causes subsequent iteration to return the same instance; reload() clears the cache but **does not start the provider**.

### 6.1. Directory Structure

~~~text
demo/
├── src/
│   └── demo/
│       ├── api/Plugin.java
│       ├── provider/UpperPlugin.java
│       └── app/Main.java
├── resources/
│   └── META-INF/services/demo.api.Plugin
├── out/
│   ├── host/                  # Generated by javac
│   └── provider/              # Generated by javac, including descriptor
└── plugin.jar                 # Generated by jar
~~~

The host is compiled **without requiring the UpperPlugin class on the compile classpath**. The SPI and Main go into `out/host`; the provider is compiled separately against the API and packaged into `plugin.jar`. At runtime, the descriptor inside the JAR enables ServiceLoader to find the provider.

### 6.2. Shared Host API

**src/demo/api/Plugin.java**

~~~java
package demo.api;

public interface Plugin {
    String id();
    void start();
    String handle(String input);
    void stop();
}
~~~

This is the **application contract**. The **id/start/handle/stop** methods are agreed upon by the host and plugin developer; Java ServiceLoader does not mandate these methods. In larger systems, the contract can be extended with metadata, semantic versioning, and health checks, without attaching those meanings to the ServiceLoader API.

### 6.3. Provider: Valid Class and Concrete Behavior

**src/demo/provider/UpperPlugin.java**

~~~java
package demo.provider;

import demo.api.Plugin;
import java.util.Locale;

public final class UpperPlugin implements Plugin {
    public UpperPlugin() {
        System.out.println("Provider: constructor");
    }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public void start() {
        System.out.println("Provider: start");
    }

    @Override
    public String handle(String input) {
        return input.toUpperCase(Locale.ROOT);
    }

    @Override
    public void stop() {
        System.out.println("Provider: stop");
    }
}
~~~

The provider implements **demo.api.Plugin**, is a public class, and has a public no-arg constructor. The constructor logs **Provider: constructor** to mark when the object is instantiated. **start()** and **stop()** log separately to distinguish **Java object instantiation** from **plugin resource activation**; `handle()` converts input to uppercase.

The descriptor **resources/META-INF/services/demo.api.Plugin** has just one line:

~~~text
demo.provider.UpperPlugin
~~~

This is a **binary class name**, not a command to start the plugin. ServiceLoader uses that registration to locate and instantiate the provider when requested.

### 6.4. Host Using ServiceLoader While Controlling Lifecycle

**src/demo/app/Main.java**

~~~java
package demo.app;

import demo.api.Plugin;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Plugin> loader =
                ServiceLoader.load(Plugin.class, Plugin.class.getClassLoader());
        System.out.println("Host: ServiceLoader created");

        Plugin selected = null;
        for (Plugin candidate : loader) {
            if ("upper".equals(candidate.id())) {
                selected = candidate;
                break;
            }
        }
        if (selected == null) {
            throw new IllegalStateException("Required provider not found");
        }
        System.out.println("Host: selected " + selected.id());
        System.out.println("Host: cached same instance: " +
                (loader.iterator().next() == selected));

        boolean started = false;
        try {
            System.out.println("Host: starting");
            selected.start();
            started = true;
            System.out.println("Host: result " + selected.handle("hello"));
        } finally {
            if (started) {
                System.out.println("Host: stopping");
                selected.stop();
            }
        }

        System.out.println("Host: clearing ServiceLoader cache");
        loader.reload();
        Plugin fresh = loader.iterator().next();
        System.out.println("Host: new instance after reload: " +
                (fresh != selected));
    }
}
~~~

Notable points:

- **ServiceLoader.load(Plugin.class, Plugin.class.getClassLoader())** uses the loader that currently sees the SPI to discover providers. This class loader choice is explicitly made by the host; complex plugin applications may require a different loader.
- After the line **Host: ServiceLoader created**, **Provider: constructor** has not appeared yet. Because ServiceLoader is lazy, there is no ACTIVE lifecycle yet.
- **for (Plugin candidate : loader)** requests providers. ServiceLoader then instantiates and populates the cache; **the host** compares **candidate.id()** to select.
- **loader.iterator().next() == selected** demonstrates that the provider instance was cached and not recreated on that pass.
- **Host: starting** then **selected.start()** are **calls made by the host**, completely outside ServiceLoader.
- **Host: result HELLO** comes from **selected.handle("hello")**, likewise.
- **Host: stopping** then **selected.stop()** are called by the host in `finally` after start succeeds.
- **loader.reload()** causes the subsequent iteration to create a new instance, but **no start() call occurs** on that new instance.

**Intentional limitations:** the example has only one provider and does not implement auditing, isolation, true hot swap, health checks, or selection among multiple versions. Failure handling for `start()` is only a simple model; production requires defining cleanup even when `start()` allocates partial resources and then throws.

### 6.5. Compiling, Packaging, and Running

Run from the **demo/** directory with the files created per the structure above.

**Linux/macOS (bash):**

~~~bash
mkdir -p out/host out/provider out/provider/META-INF/services

javac --release 17 -d out/host \
  src/demo/api/Plugin.java src/demo/app/Main.java

javac --release 17 -cp out/host -d out/provider \
  src/demo/provider/UpperPlugin.java

cp resources/META-INF/services/demo.api.Plugin \
  out/provider/META-INF/services/demo.api.Plugin

jar --create --file plugin.jar -C out/provider .

java -cp "out/host:plugin.jar" demo.app.Main
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/host,out/provider,out/provider/META-INF/services | Out-Null

javac --release 17 -d out/host src/demo/api/Plugin.java src/demo/app/Main.java

javac --release 17 -cp out/host -d out/provider src/demo/provider/UpperPlugin.java

Copy-Item resources/META-INF/services/demo.api.Plugin out/provider/META-INF/services/demo.api.Plugin

jar --create --file plugin.jar -C out/provider .

java -cp "out/host;plugin.jar" demo.app.Main
~~~

For the **java -cp** command, Linux/macOS uses **:** between classpath entries; Windows uses **;**. The provider **does not need to be on the classpath when compiling the host**, only present when launching the example. If implementing dynamic installation after the host is already running, an appropriate plugin loader mechanism must be used; this example verifies **discovery and lifecycle**, and does not itself demonstrate loading a new JAR into a fixed classpath.

**Exact standard output:**

~~~text
Host: ServiceLoader created
Provider: constructor
Host: selected upper
Host: cached same instance: true
Host: starting
Provider: start
Host: result HELLO
Host: stopping
Provider: stop
Host: clearing ServiceLoader cache
Provider: constructor
Host: new instance after reload: true
~~~

### 6.6. Reading Output by Ownership

| Output Line | Who Triggered It? | Meaning |
| --- | --- | --- |
| Host: ServiceLoader created | Host | Lookup object created; provider not yet created |
| Provider: constructor | ServiceLoader requested instantiation; constructor ran | Provider object instantiated lazily |
| Host: selected upper | Host | Host decided to choose provider ID `upper` |
| Host: cached same instance: true | ServiceLoader cache; host observed | Re-iterating returned the cached provider |
| Host: starting | Host | Host begins activation |
| Provider: start | Host called; provider executed | Not a method automatically called by ServiceLoader |
| Host: result HELLO | Host called handle; provider executed | Business logic processed |
| Host: stopping | Host | Host decides shutdown |
| Provider: stop | Host called; provider executed | Cleanup belonging to the plugin contract |
| Host: clearing ServiceLoader cache | Host | Host decides to refresh lookup |
| Provider: constructor (second time) | ServiceLoader instantiated during new iteration | Old cache was cleared |
| Host: new instance after reload: true | Host | New object, does not mean new bytecode/plugin version was loaded |

There is no **Provider: start** line after the second constructor. This is clear evidence that **reload() is not activate()**. Nor is there any **Provider: stop** generated automatically by ServiceLoader; stop appears because the host called the plugin's own method.

## 7. ServiceLoader.reload() Is Completely Different from Plugin Hot Reload

A common mistake is seeing **reload()** and concluding “the JAR/plugin has been updated”. In Java, at least three distinct layers must be separated:

1. **ServiceLoader**: holds its own lookup state and provider cache.
2. **ClassLoader or ModuleLayer**: determines which class/module definitions can be loaded and under what identity.
3. **Plugin instance and resources**: already-instantiated objects, threads, connections, callbacks, file handles, and in-flight requests.

**ServiceLoader.reload() only affects layer 1.** It does not directly modify layer 2 or close/release layer 3.

A real upgrade workflow might look like:

~~~text
Plugin v1 ACTIVE on loader L1
       |
       | Host receives, verifies plugin v2 artifact
       v
Host creates new loader L2 / module layer (when needed)
       |
       v
Host creates new ServiceLoader bound to L2/layer v2
       |
       v
ServiceLoader discovers and instantiates provider v2
       |
       v
Host validates version/contract and starts v2
       |
       +---- v2 fails --> stop/clean up v2; keep v1; report error
       |
       v
Host routes new requests to v2
       |
       v
Host drains v1 requests, stops v1
       |
       v
Host closes L1 when safe, removes references/callbacks/threads
       |
       v
v2 ACTIVE; v1 eligible for GC/unloading when conditions are met
~~~

**Classes already defined by loader L1 are not automatically replaced by bytecode of the same name just via reload().** For applications using URLClassLoader, the common way to replace definitions is to create a new loader and ensure shared API/SPI types remain defined by the parent loader.

**Closing a URLClassLoader** releases resources managed by the loader, but does not guarantee immediate class unloading. If the thread context class loader, static registries, callbacks, thread pools, tasks, or objects created by the plugin still hold references to the old loader, the classes can remain reachable. The host must manage and verify reclamation.

**Rollout safety:** do not stop v1 before proving v2 passes required checks, unless the architecture tolerates downtime. For stateful plugins, you must have a state migration policy, data compatibility, and a rollback mechanism; ServiceLoader handles none of these steps.

## 8. ClassLoader, TCCL, and ModuleLayer Are Host Configuration

On the classpath, how you choose the loader directly affects which providers are visible:

~~~java
// Two illustrative snippets, where the host already has Plugin and pluginClassLoader.
ServiceLoader<Plugin> explicit =
        ServiceLoader.load(Plugin.class, pluginClassLoader);

ServiceLoader<Plugin> byContext =
        ServiceLoader.load(Plugin.class);
~~~

The second call uses the **thread context class loader (TCCL)** at the time ServiceLoader is created. If the host manages multiple plugin loaders, explicit selection is usually easier to reason about and test. When temporarily setting TCCL, the host must restore it in **finally** and avoid letting thread pools retain references to retired loaders.

Two classes with the same binary name defined by different defining class loaders **do not automatically share the same type identity**. If the host and plugin accidentally load two copies of the Plugin interface, instantiation may succeed in one loader yet **not be assignable** to the host's SPI. The host designs a **parent loader holding the shared API**, and then creates child loaders for implementations and private dependencies.

For **JPMS explicit named modules**:
- **API module** needs to export the package containing the SPI to consumers/providers.
- **Consumer module** containing the ServiceLoader call must declare **uses** for the service; and **requires** the API module when referencing the type.
- **Provider module** declares **provides service with provider** and any required `requires`.
- **Host** decides which module graph/layer is resolved, selected, and used; **ServiceLoader.load(layer, service)** discovers providers in that layer and parent layers per API rules.

ServiceLoader **does not create a new ModuleLayer from a plugin JAR** for the host. If runtime extensibility requires loading additional named modules, the host/framework must resolve the module configuration, class loaders, and lifecycle for that layer.

**Do not misuse service discovery as a security boundary.** Finding a provider via ServiceLoader does not guarantee it is trustworthy or lacks filesystem/network access; such controls belong to the host's deployment/policy/isolation.

## 9. Distinguishing Provider.type() and Provider.get() in Selection Architecture

With **ServiceLoader.stream()**, the host can inspect **Provider<S>** before calling get():

~~~java
// Illustrative snippet; Plugin and loader already exist.
java.util.List<ServiceLoader.Provider<Plugin>> types =
        loader.stream().toList();

for (ServiceLoader.Provider<Plugin> provider : types) {
    System.out.println(provider.type().getName());
}
~~~

**provider.type()** returns the Class associated with the provider type per the API contract; annotations or type metadata can be used to aid selection before instantiation. **provider.get()** requests an instance; depending on the provider constructor/factory mechanism, this can have side effects.

Thus a plugin manager wanting to reject disallowed providers **before the constructor** can use safe external JAR metadata or type-level inspection when appropriate. However, keep in mind:

- **type() does not prove code safety**, nor does it check all dependencies or business contracts.
- With an explicit module provider factory, type() may be the **return type of provider()**, not the factory class.
- Some inspections can cause the JVM to load/verify classes; do not assume listing types is free of operational side effects in every environment.
- Traversing the stream can also throw **ServiceConfigurationError**; the host must handle it before activating plugins.
- Interleaving Stream and Iterator across reload/concurrency must follow ServiceLoader rules; avoid holding onto stale views for long.

If you need a verification process that must not load untrusted code into the host, inspect artifacts/signatures and metadata in an isolated environment **before** creating a ClassLoader/ServiceLoader.

## 10. Error Handling: JDK Reports Errors, Host Decides Policy

| Incident | What Can ServiceLoader Do? | What Must the Host Do? |
| --- | --- | --- |
| No provider | Empty iteration or findFirst() returns Optional.empty | Decide required vs. optional; fail-fast or fallback |
| Malformed descriptor | Throws **ServiceConfigurationError** during iteration | Record plugin/version; reject artifact or quarantine |
| Provider lacks valid constructor/method | Throws **ServiceConfigurationError** | Check package, constructor, factory, metadata, and release |
| Provider constructor throws exception | May wrap in **ServiceConfigurationError** | Report init failure, avoid start, and decide rollback |
| Provider created but ID/version mismatches | Unaware of host policy | Host rejects or moves to another candidate |
| start() throws exception | Does not call start(), does not handle | Host cleans up per partial-init contract; marks FAILED |
| handle() fails | Not involved | Host timeout/retry/response mapping/circuit breaker |
| stop() fails | Does not call stop() | Host logs, continues controlled cleanup, tracks leaks |
| Plugin v2 unhealthy | Unaware of health | Host keeps v1 or rolls back |
| Old class loader still referenced | Does not unload and does not observe | Host clears TCCL/threads/callbacks/caches, measures resource leaks |

**ServiceConfigurationError is an Error:** catching it specifically at the **provider discovery/instantiation** boundary is appropriate when the host needs to manage plugin configuration errors. Do not use a system-wide **catch(Throwable)** that swallows critical JVM errors; and do not treat every ServiceConfigurationError as a situation that can proceed via infinite retries.

Example of handling at the discovery boundary:

~~~java
// Illustrative snippet in the host: Plugin and pluginClassLoader already exist.
try {
    ServiceLoader<Plugin> loader =
            ServiceLoader.load(Plugin.class, pluginClassLoader);

    for (Plugin candidate : loader) {
        // Host verifies ID, version, permissions, health, and selects candidate.
    }
} catch (java.util.ServiceConfigurationError configurationFailure) {
    // Host records plugin error and applies reject/rollback policy.
}
~~~

On Java 17, the javadoc explains that after a ServiceConfigurationError, the iterator only makes a **best effort** to proceed to other providers; recovery is not guaranteed. Therefore, a host should not iterate unboundedly to “skip errors and look for a good provider” without limits and dedicated design.

**start/stop failures differ from ServiceConfigurationError:** if the provider has already been instantiated and a host-invoked method throws RuntimeException, that error belongs to **the host-orchestrated lifecycle** rather than automatically becoming a ServiceLoader error.

## 11. Concurrency, Caching, and Rules That Must Not Be Inferred

**ServiceLoader is not designed to be thread-safe.** Do not share a ServiceLoader instance across multiple threads to concurrently iterate, call stream, and reload without external synchronization. The host should coordinate discovery during a controlled phase and store selected providers in the host's own registry.

Example of one design approach:

- **Discovery phase:** a single thread iterates ServiceLoader and builds an immutable candidate list for the plugin version.
- **Validation phase:** the host confirms ID, compatibility, policy, and resource contracts.
- **Activation phase:** the host calls start() in order and records an explicit ACTIVE state.
- **Serving phase:** multiple threads invoke the provider at the concurrency level permitted by the contract.
- **Shutdown/replace phase:** the host stops accepting new requests, drains, stops, and releases the loader.

The fact that ServiceLoader caches instances **does not mean those instances are thread-safe**. Constructors, **handle()**, and provider state require their own concurrency contract; the host may need to serialize calls, provide a pool, or instantiate per request if the design allows.

**Discovery order is not business priority order.** When multiple providers serve an SPI, the host should use plugin IDs and controlled metadata/priority to decide. Using **findFirst()** is appropriate only when the business rule itself says “pick the first provider under a controlled lookup configuration”, or when only one provider is deployed and that condition is tested.

**The cache is not a version registry either.** ServiceLoader caching is a convenience mechanism for lookup within a loader instance; the host still needs a registry managing artifact versions, activation state, lease/reference counts, health, and when retirement is allowed.

## 12. Three Decision Scenarios

### Scenario A: One Stable SPI, One Single Provider

The application provides **Formatter** and only one JAR registers a provider. ServiceLoader locates and instantiates Formatter; the host uses it to process requests. If the provider manages no resources, the host might not need complex start/stop. **But the absence of start/stop is a contract decision**, not because ServiceLoader cleans up automatically.

**Belongs to ServiceLoader:** locate descriptor, load class, instantiate.
**Belongs to host:** choose class loader, call format(), handle exceptions, and close any created resources.

### Scenario B: Multiple Providers for Multiple Tenants

Both ProviderA and ProviderB are valid for an SPI. Tenant A may only use ProviderA due to data policy; Tenant B needs ProviderB for a different feature.

**ServiceLoader has no concept of tenant identity.** It can list both. The host must define metadata, authorization, routing, quotas, and how to prevent state leakage between tenants. Never simply grab the first provider and treat that as a valid decision.

**Belongs to ServiceLoader:** discover visible providers.
**Belongs to host:** check permissions, select per tenant, isolate data, observe errors, and route traffic.

### Scenario C: Updating a Plugin Without Stopping the Host

Operations installs plugin v2. Calling ServiceLoader.reload() on the old loader only refreshes the lookup cache. To load v2 code when the old loader already defined v1 code, the host needs a suitable loader/layer architecture, prepares v2, validates/starts v2, switches requests, stops v1, and drops old references. **ServiceLoader has no authority to decide when v2 is healthy enough.**

**Belongs to ServiceLoader:** discover providers in the v2 loader/layer and instantiate when requested by the host.
**Belongs to host:** artifact updates, loaders/layers, validation, rollout, cutover, rollback, cleanup, and observability.

## 13. Plugin Manager Implementation Checklist

### Before Discovery
- [ ] A stable published API/SPI with consistent class identity in a shared loader or API module.
- [ ] Artifacts verified for provenance, version, checksum/signature, and appropriate dependency policy.
- [ ] Correct ClassLoader or ModuleLayer selected for the target plugin.
- [ ] Provider properly registered in **META-INF/services** or **module-info provides**, and consuming named module has **uses**.
- [ ] Explicit decision on which plugins are allowed to load per tenant/process and trust boundary.

### Discovery and Selection
- [ ] Host handles **no provider** and **ServiceConfigurationError** at the proper boundary.
- [ ] Do not treat **findFirst()** as business ranking when multiple providers exist.
- [ ] Instantiate only when needed; consider **stream().type()** if inspecting types beforehand is helpful.
- [ ] Policy in place to verify ID, version, contract, capabilities, and access permissions.
- [ ] Host registry explicitly records which instance is **SELECTED** and **ACTIVE**, independent of ServiceLoader's cache.

### Operations
- [ ] Host calls start()/stop()/close() if defined by the SPI; cleanup plan exists when start fails partially.
- [ ] Health checks, timeouts, retries, and blast-radius reduction when a plugin fails.
- [ ] Concurrency rules defined for instances; do not infer thread safety from caching.
- [ ] Logs/metrics/traces include provider ID, version, and loader/layer to investigate class identity and resource leaks.

### Updating and Decommissioning
- [ ] Do not equate **ServiceLoader.reload()** with version upgrade/hot swap/unload.
- [ ] Do not use old iterators/streams after reload().
- [ ] Plan exists for new loader/layer, starting new version, shifting traffic, draining, stopping old version, cleanup, and rollback.
- [ ] Remove references/TCCL/threads/callbacks/registries pointing to the old plugin before expecting class unloading.
- [ ] Tests cover lifecycle and failures at every step, not just whether the provider is discovered.

## 14. Self-Check Questions

**1. If ServiceLoader finds a provider but the host has not called start() yet, is the plugin ACTIVE?**  
No. An instantiated object does not prove the plugin has passed validation/readiness or been activated by the host.

**2. If reload() is called, does the JVM immediately replace bytecode from plugin-v1.jar with plugin-v2.jar?**  
No. reload() clears ServiceLoader's own cache; class definitions and plugin lifecycle are managed by loaders/layers and the host.

**3. If a provider constructor fails, who reports it? Who decides the fallback?**  
ServiceLoader may throw ServiceConfigurationError during instantiation; the host is responsible for logging/policy/fallback/rejection.

**4. If start() or stop() throws an error, does ServiceLoader automatically retry?**  
No. Those are methods defined by the SPI/host; the host decides retries, cleanup, and state transitions.

**5. When two providers exist, who decides which provider to use?**  
ServiceLoader enables discovering providers; the host selects based on ID, version, capability, priority, authorization, and business requirements.

**6. Why shouldn't a ServiceLoader using TCCL be kept as a JVM-wide singleton?**  
Each application/tenant may have a different TCCL, yielding a different set of providers; keeping a loader/provider around too long can also retain old class loaders and cause leaks.

**7. In the runnable example, who calls the constructor, who calls start, and who calls stop?**  
The constructor runs while ServiceLoader instantiates the provider upon iterator demand; start and stop are called directly by the host.

## 15. Conclusion

**ServiceLoader provides the mechanism for a host to locate and obtain providers of a registered SPI; it is not a plugin lifecycle manager.** Discovery/loading/instantiation/caching belong to ServiceLoader's scope. Provenance verification, authorization, provider selection, configuration, activation, health, request handling, shutdown, version upgrades, rollbacks, and resource reclamation are the responsibility of **the host application**.

If you remember a single rule: **“ServiceLoader answers which providers can be obtained; the host answers which provider is allowed to run, when it runs, how it runs, and when it stops.”**

### Official Java 17 Documentation

- ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- ServiceLoader.Provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- ServiceConfigurationError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html
- URLClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
