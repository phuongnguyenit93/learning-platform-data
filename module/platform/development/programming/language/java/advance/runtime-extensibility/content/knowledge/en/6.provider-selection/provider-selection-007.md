# Distinguishing Service Discovery from Dependency Management and Plugin Lifecycle in Java

## 1. Three Distinct Responsibilities of an Extensible System

In Java, an application (*host*) can allow installing additional implementations (*service provider*, *extension*, *plugin*) to extend functionality. When **selecting a provider**, three questions must be distinguished:

1. **Service discovery:** Which classes claim to implement a service contract and can currently be found?
2. **Dependency management/resolution:** What other APIs, libraries, services, or plugins does the selected provider need; do they exist and are they compatible?
3. **Plugin lifecycle management:** When is a provider instantiated, allowed to receive requests, stopped, and cleaned up?

They are related, yet **they are not the same mechanism**. `java.util.ServiceLoader` primarily handles finding and instantiating providers declared via Java SPI; it does not automatically download dependencies from repositories, determine startup order for dependent plugins, invoke business methods like `start()` or `stop()`, or enforce a mechanism to upgrade/unload running plugins.

| Aspect | Service discovery | Dependency management | Lifecycle management |
| --- | --- | --- | --- |
| Question | “Which providers exist for this contract?” | “What does the provider need to work properly?” | “What state is the provider in and what is it allowed to do?” |
| Typical inputs | Service interface, SPI descriptor, module declaration, class loader | Metadata/version, JARs and libraries, module graph, host services, plugin relations | Provider instance, configuration, resources, readiness, in-flight requests |
| Tools/approaches | `ServiceLoader`, `META-INF/services`, `uses/provides` | Maven/Gradle at build time, runtime classpath/module resolution, plugin dependency resolver, DI | Plugin manager, state machine, `start/stop/close`, dispatcher and registry |
| Output | One or more candidate providers | Compatible dependency set, loadable/supplied | `ACTIVE` instance, or `STOPPED`/`FAILED` with cleanup |
| Typical errors | No provider, broken SPI declaration | Missing class, wrong version, dependency conflict, dependency cycle | Start failure, request after stop, thread/resource leak |
| Can `ServiceLoader` do it? | Yes: finds and instantiates providers per SPI rules | Not a general dependency resolver | Does not orchestrate application-defined lifecycles |

**Example:** The host finds `PdfExporter` via SPI. That **does not prove** the PDF library version required by the provider is present, nor does it **prove** a storage connection has been provided. After verifying dependencies, the host still has to decide whether to enable the provider, supply required configuration and services, start it, add it to the registry, monitor it, and stop it according to policy.

In this lesson, “service discovery” means **in-process Java provider discovery** via SPI/Module System. This is a different concept from finding network service instances via DNS, Kubernetes Services, or a service registry.

## 2. Service Discovery: Java SPI and `ServiceLoader`

### 2.1. Service Contract and Provider Declaration

Suppose the host publishes an interface:

```java
package app.api;

public interface Plugin {
    String id();
    String process(String input);
}
```

This is only a **contract illustration snippet**; the runnable example in section 6 adds lifecycle APIs. An implementation class `app.ext.UppercasePlugin` can register with SPI on the classpath via the file:

```text
META-INF/services/app.api.Plugin
```

Contents:

```text
app.ext.UppercasePlugin
```

The filename is the *fully qualified name* of the service interface; each valid line in the file points to one provider class per SPI rules. With JPMS named modules, a provider can register via `provides app.api.Plugin with app.ext.UppercasePlugin;` and the consuming module declares `uses app.api.Plugin;`.

The host finds providers with:

```java
ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);
for (Plugin plugin : loader) {
    System.out.println(plugin.id());
}
```

This snippet illustrates usage requiring `import java.util.ServiceLoader;` and the corresponding interface. `ServiceLoader.load(Plugin.class)` uses the thread's context class loader; there is an overload `ServiceLoader.load(Plugin.class, specificLoader)` when the host manages plugins via a designated class loader. `ServiceLoader.load(layer, Plugin.class)` supports lookup from a module layer.

### 2.2. “Discovered” Can Mean Different Levels

Do not lump every operation into the single word “load”:

- **Artifact discovery:** seeing a JAR/manifest in the plugin directory; may not have touched any plugin classes yet.
- **Service declaration discovery:** identifying provider names via `META-INF/services` or module metadata.
- **Class loading:** the JVM finds, defines, and links required classes via a class loader; loading does not mean invoking constructors or the application's `start` method.
- **Provider instantiation:** `ServiceLoader` may instantiate providers when iterating `iterator()` or calling `Provider.get()`; at this point constructors/relevant static initializers may run.
- **Business activation:** the host explicitly invokes the startup method defined by the contract; this is not an automatic duty of `ServiceLoader`.

`ServiceLoader` is *lazy*: creating the loader object does not force all providers to be instantiated immediately. `findFirst()` returns `Optional<Plugin>`, suitable when the application simply needs any available provider:

```java
Optional<Plugin> first =
    ServiceLoader.load(Plugin.class).findFirst();
```

However, **the first provider is not by default the best provider**. Iteration order can be affected by classpath, module configuration, and registration sources. When selecting providers by ID, capability, version, or priority, the host must build its own selection rules. `Optional.empty()` only indicates no provider was found after a normal traversal; it does not substitute for dependency or readiness validation.

### 2.3. `findFirst()` and `stream()` Serve Different Needs

| API | Return type | Purpose |
| --- | --- | --- |
| `loader.findFirst()` | `Optional<Plugin>` | Obtain the first provider instance |
| `loader.stream().findFirst()` | `Optional<ServiceLoader.Provider<Plugin>>` | Obtain the first provider handle |
| `Provider.type()` | `Class<? extends Plugin>` | Inspect provider type without proactively calling `Provider.get()` |
| `Provider.get()` | `Plugin` | Request/obtain the provider instance |

For example:

```java
Optional<Plugin> selected = loader.stream()
    .filter(p -> p.type().getName().equals("app.ext.UppercasePlugin"))
    .findFirst()
    .map(ServiceLoader.Provider::get);
```

This snippet illustrates selecting by class name to show the difference between a *handle* and an *instance*. Inspecting type via `type()` may still require loading classes/metadata; **discovery must not be treated as safe on untrusted code**. If you want to select by ID/capability before instantiation, keep host-controlled metadata/manifests instead of having to call constructors just to read properties.

### 2.4. Discovery Does Not Automatically Resolve Configuration Errors

An SPI file may declare a provider that does not exist, does not belong to the service interface, cannot be instantiated, or lacks dependencies. In that case, iterating `ServiceLoader` can throw `ServiceConfigurationError`. Distinguish:

- No providers at all: `findFirst()` returns `Optional.empty()`.
- Providers declared but unusable: usually a configuration/loading/instantiation error; must be diagnosed and fixed, not turned into “empty”.
- Providers exist but fail selection policy: the host can return “no matching provider”, even though SPI still discovered other providers.

## 3. Dependency Management: “Seeing a Provider” Is Not Enough to Run It

### 3.1. Four Common Dependency Types

**1. Library/code dependencies:** the provider needs external libraries or a specific Java/JAR version. For example, `PdfExporter` needs a PDF generation library, yet `ServiceLoader` does not fetch that library for you. Maven/Gradle resolve dependencies during build/packaging; the runtime environment still needs the right classes/modules present. Missing dependencies can cause `ClassNotFoundException`, `NoClassDefFoundError`, or `LinkageError`.

**2. Shared API dependencies:** the host and plugin must understand the same service contracts/DTOs. In the JVM, a class's identity consists of **fully qualified name + defining class loader**. If a plugin JAR bundles its own copy of `app.api.Plugin` loaded by a different class loader, the host can hit cast or linkage errors despite identical class names. Typically the host/parent loader owns stable contracts; plugin loaders load only implementations and private dependencies.

**3. Host service dependencies:** the provider needs a logger, clock, repository, configuration, or HTTP client. The host must create, select, configure, and supply those services via interfaces/context or DI. `ServiceLoader` has no idea how a provider needs an `AuditLog` or a database connection unless the application designs the contract and dependency-provision flow.

**4. Inter-plugin dependencies:** for example, the `Report` plugin needs the `Storage` plugin to be `ACTIVE`; the `Export` plugin in turn needs `Report`. The host must know dependency edges, check versions/capabilities, and start them in valid order.

### 3.2. Dependency Graph and Startup Order

Suppose:

```text
Export ──requires──► Report ──requires──► Storage
```

If `A → B` denotes “A depends on B”, startup order should be:

```text
Storage → Report → Export
```

On shutdown, reverse it:

```text
Export → Report → Storage
```

A plugin manager can apply **topological sort** to the dependency graph, and then:

1. Read dependency/capability lists and version constraints.
2. Verify each mandatory dependency is present and compatible; optional dependencies follow a clear policy.
3. Detect dependency cycles, such as A needing B and B needing A, to report actionable diagnostics.
4. Prepare class loaders/module layers and required services.
5. Start dependencies first, activating waiting plugins only when mandatory prerequisites are ready.
6. Stop in reverse order, avoiding closing a dependency while another plugin still uses it.

This is a host/framework policy, **not a built-in feature of `ServiceLoader`**. In particular, a `for (Plugin p : ServiceLoader.load(Plugin.class))` loop never guarantees putting plugins in proper dependency order.

### 3.3. How Do Maven/Gradle, JPMS, and Dependency Injection Differ?

| Mechanism | What it resolves | What it does not resolve automatically |
| --- | --- | --- |
| Maven/Gradle | Declaring, fetching, and packaging dependencies at build time | Deciding which plugins are `ACTIVE`, running runtime plugin `start/stop` |
| Classpath and class loaders | Loading/finding classes from provided sources | Downloading missing dependencies from repositories, verifying versions per business policy |
| JPMS `requires` and module resolution | Enforcing readability and resolving module dependencies when configuring layers | Bringing plugins to business `READY` state, awaiting in-flight requests, closing resources |
| DI container/factory | Building object graphs and injecting dependencies per configuration | Auto-discovering arbitrary external providers or orchestrating hot swaps if unconfigured |
| Custom plugin manager | Can combine metadata, graph resolution, DI, state, health checks, and cleanup | Only enforces the policies the application actually implements |

**JPMS clarifies dependencies at the module level**, yet configuring module layers and runtime lifecycles still requires active host management. **DI resolves relationships between objects**, while service discovery finds candidate providers. Many applications combine both.

### 3.4. Dependency Conflicts in Dynamic Plugins

If two plugins require incompatible versions of the same library, putting both on one classpath can cause failures. One strategy is a dedicated class loader per plugin, placing shared APIs in the parent and managing policies for private dependencies. This requires examining:

- Effective parent-first/child-first boundaries and overlapping packages.
- Avoiding re-packaging host contracts inside plugins.
- Shared vs. isolated dependencies; JNI/native libraries have their own constraints.
- Which threads, callbacks, `ThreadLocal`s, or caches might retain an old class loader after reload.
- Resource access rights: **class loader isolation is not a security sandbox**. Plugins running in the same process generally hold the process's privileges.

## 4. Lifecycle Management: Providers Must Be Activated and Stopped Explicitly

### 4.1. A Reasonable State Machine

```text
DISCOVERED
    │
    ▼
VALIDATED / DEPENDENCIES_RESOLVED
    │
    ▼
INSTANTIATED
    │
    ▼
STARTING ──error──► FAILED ──cleanup──► STOPPED
    │
  success
    ▼
ACTIVE ──stop new requests──► QUIESCING
                                  │
                            wait inflight
                                  ▼
                               STOPPING
                                  │
                                  ▼
                                STOPPED
```

These state names are an **application-level design**; the JVM provides no built-in state machine like this for SPI. The host decides who gets called when:

- Publish a plugin into the request-serving registry only after `start` and readiness checks succeed.
- Block new calls as soon as transitioning to `QUIESCING`.
- Let in-flight calls finish within a deadline, then apply cancellation/rollback policies.
- Call `stop()`/`close()`, unregister listeners, close executors/threads, streams, sockets, and plugin-owned resources.
- Remove the plugin from registries, callbacks, and caches; close host-created class loaders when appropriate.

A common lifecycle contract:

```java
public interface ManagedPlugin {
    String id();
    void start(HostServices services);
    Object execute(Object request);
    void stop();
}
```

This is an **API design illustration**, not a complete runnable program. The contract should specify thread safety, idempotency of `stop`, partial-failure handling when `start` fails, and deadlines when waiting for requests to finish.

### 4.2. Instantiation Differs from Business Startup

When `ServiceLoader` instantiates a provider, constructors and class initialization logic may run. However, `ServiceLoader` **never automatically calls** a `start` method that you declare.

For instance, a `StoragePlugin` has a no-arg constructor. Even if `ServiceLoader.findFirst()` finds an instance, the host still has to supply configuration/connections before placing the plugin into the router. If the constructor triggers heavy side effects, the host can hardly control or roll them back; keep constructors lean and put active initialization in `start`.

When `start` fails after allocating some resources, the plugin should release what it allocated; the host does not mark it `ACTIVE` and avoids routing requests to that instance. When another plugin depends on this instance, the manager must block startup or mark the dependency state failed per policy.

### 4.3. Stopping a Plugin Does Not Mean Unloading Classes

`URLClassLoader.close()` closes files/JARs opened by the loader; it **does not kill threads**, does not stop existing plugin objects from running, and does not guarantee class unloading. Class loaders/classes can only be collected by GC when no live references retain them. Common retention sources include threads, TCCL (`Thread.currentThread().getContextClassLoader()`), `ThreadLocal`, static caches, listeners, callbacks, executors, and registries.

For **hot reload**, a typical flow uses a new loader + new instance, checks compatibility, starts and health-checks, shifts traffic, drains old requests, stops the old instance, clears old references, and then closes the old loader. `ServiceLoader.reload()` only clears the `ServiceLoader` object's provider cache; it does not replace classes already loaded by the JVM via the old loader and does not call `stop`.

## 5. When Selecting Providers, How Do the Three Mechanisms Fit Together?

A typical operational pipeline:

```text
[1] Receive artifact / metadata
          │
          ▼
[2] Validate source, version, capability, required dependencies
          │
          ▼
[3] Resolve dependency graph, configure class loader/module layer
          │
          ▼
[4] SPI discovery: ServiceLoader → candidate providers
          │
          ▼
[5] Selection policy: enabled/disabled, ID, capability, priority, compatibility
          │
          ▼
[6] Instantiate, supply HostServices, invoke start and readiness check
          │
          ▼
[7] Publish only ACTIVE providers to the request-serving registry
          │
          ▼
[8] Quiesce → stop → cleanup in dependency order
```

The exact execution order depends on architecture: classpath providers may bundle dependencies upfront, making runtime resolution nearly invisible; dynamic JAR-loading systems must verify metadata and libraries **before** letting provider code execute. The core point is that the host must distinguish **“discovered”**, **“eligible for selection”**, and **“ready to serve”**.

### Selection Policy Must Be Explicit

If two providers implement the same interface, do not merely call `findFirst()` when the business requires deterministic selection. The host can:

- Filter by `id` and verify there are no duplicate IDs.
- Filter by capability (for example `supports("pdf")`).
- Check contract version, enable/disable flags, and trusted-source policy.
- Prioritize based on defined configuration/priority, with a stable tie-breaker.
- Select only providers whose dependencies are satisfied; dispatch only after readiness.

For **missing** providers, distinguish “optional feature → skip/fallback”, “mandatory feature → report clear error”, and “provider exists but dependency/config is broken → do not silently fall back”. If multiple providers share the same ID, the manager should reject the ambiguous configuration or apply an explicit conflict rule.

## 6. Runnable Java 17+ Example: SPI Discovery, Host-Supplied Dependencies, and Lifecycle Management

The example below intentionally separates the three responsibilities into three visible operations:

1. **Discovery and selection:** `ServiceLoader` finds `Plugin` implementations from a JAR and the host selects by `id`.
2. **Dependency supply:** the host creates `AuditLog` and passes it into `start(AuditLog)`. `ServiceLoader` does not supply this dependency.
3. **Lifecycle:** the host explicitly invokes `start`, `process`, and `stop` inside `finally`.

The example uses only one plugin to keep code easy to follow. A production plugin manager needs to add a resolver for plugin-to-plugin relations, version checks, state synchronization, timeouts, and partial-startup failure handling as explained above.

### 6.1. Structure

```text
demo/
├── src/
│   └── app/
│       ├── api/
│       │   ├── AuditLog.java
│       │   └── Plugin.java
│       ├── host/
│       │   └── App.java
│       └── ext/
│           └── UppercasePlugin.java
└── resources/
    └── META-INF/
        └── services/
            └── app.api.Plugin
```

### 6.2. Contract Provided to Both Host and Plugin

**`src/app/api/AuditLog.java`**

```java
package app.api;

@FunctionalInterface
public interface AuditLog {
    void record(String event);
}
```

**`src/app/api/Plugin.java`**

```java
package app.api;

public interface Plugin {
    String id();
    void start(AuditLog audit);
    String process(String input);
    void stop();
}
```

`AuditLog` is a **host-supplied plugin dependency**, not a service that `ServiceLoader` automatically knows how to instantiate and inject.

### 6.3. Implementation Packaged in a Separate JAR

**`src/app/ext/UppercasePlugin.java`**

```java
package app.ext;

import app.api.AuditLog;
import app.api.Plugin;
import java.util.Locale;
import java.util.Objects;

public final class UppercasePlugin implements Plugin {
    private AuditLog audit;
    private boolean active;

    // Default no-arg constructor, usable with SPI.
    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public void start(AuditLog audit) {
        if (active) {
            throw new IllegalStateException("Plugin already active");
        }
        this.audit = Objects.requireNonNull(audit, "audit");
        active = true;
        audit.record("start uppercase");
    }

    @Override
    public String process(String input) {
        if (!active) {
            throw new IllegalStateException("Plugin not active");
        }
        return input.toUpperCase(Locale.ROOT);
    }

    @Override
    public void stop() {
        if (!active) {
            return;
        }
        active = false;
        audit.record("stop uppercase");
        audit = null;
    }
}
```

`active` in the example serves only to verify sequential lifecycle checks; it is **not** a thread-safety solution for applications handling concurrent requests. In production, state transitions and in-flight tracking require proper synchronization/coordination.

### 6.4. Host Discovers, Selects, Injects Dependency, and Stops

**`src/app/host/App.java`**

```java
package app.host;

import app.api.AuditLog;
import app.api.Plugin;
import java.util.Optional;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        String desiredId = args.length == 0 ? "uppercase" : args[0];

        // (1) Discovery: SPI instantiates providers as the stream is traversed.
        // (2) Selection: ID policy is decided by the host.
        Optional<Plugin> selected = ServiceLoader.load(Plugin.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .filter(plugin -> desiredId.equals(plugin.id()))
            .findFirst();

        if (selected.isEmpty()) {
            System.out.println("Không có provider: " + desiredId);
            return;
        }

        Plugin plugin = selected.orElseThrow();

        // (3) Dependency management: host creates and supplies AuditLog.
        AuditLog audit = event -> System.out.println("[audit] " + event);

        // (4) Lifecycle management: ServiceLoader does not call start/stop automatically.
        try {
            plugin.start(audit);
            System.out.println("Kết quả: " + plugin.process("Java SPI"));
        } finally {
            // Plugin contract must allow cleanup even if start fails.
            plugin.stop();
        }
    }
}
```

Here `map(ServiceLoader.Provider::get)` instantiates candidates visited before filtering by ID. If there are many plugins and you want to select **before instantiation**, you need external metadata or a policy based on `Provider.type()`; do not instantiate everything just to read IDs when instantiation is expensive. This snippet intentionally keeps the selection model simple.

### 6.5. SPI Declaration

Create file **`resources/META-INF/services/app.api.Plugin`** containing:

```text
app.ext.UppercasePlugin
```

The file must be placed inside the provider JAR at the right path; the service interface `app.api.Plugin` belongs in the host/API and should not be duplicated inside the provider JAR.

### 6.6. Compiling and Running on Windows PowerShell

Stand in the `demo` directory with JDK 17+ (`javac`, `java`, and `jar` on `PATH`):

```powershell
New-Item -ItemType Directory -Force build/host, build/provider | Out-Null

# Compile contract and host, without putting implementation on classpath.
javac -encoding UTF-8 -d build/host src/app/api/AuditLog.java src/app/api/Plugin.java src/app/host/App.java

# Provider is compiled separately, depending on the API in build/host.
javac -encoding UTF-8 -cp build/host -d build/provider src/app/ext/UppercasePlugin.java

# Package SPI descriptor and provider class into a JAR.
New-Item -ItemType Directory -Force build/provider/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/app.api.Plugin build/provider/META-INF/services/app.api.Plugin
jar --create --file build/uppercase-plugin.jar -C build/provider .

# Test without provider:
java -cp build/host app.host.App

# Test with provider:
java -cp 'build/host;build/uppercase-plugin.jar' app.host.App
```

**Run 1 (without provider)** — exact stdout:

```text
Không có provider: uppercase
```

**Run 2 (with provider JAR)** — exact stdout:

```text
[audit] start uppercase
Kết quả: JAVA SPI
[audit] stop uppercase
```

Explanation across the three responsibilities:

- **Discovery:** Run 1 lacks the descriptor/provider on the runtime classpath, so `selected.isEmpty()` is `true`; Run 2 finds the descriptor, and SPI instantiates `UppercasePlugin`.
- **Dependency:** the host creates the `AuditLog` lambda and **passes it explicitly** into `plugin.start(audit)`. No line in `ServiceLoader` injects `AuditLog`.
- **Lifecycle:** `start` and `stop` log through the dependency; `process` runs only between those two calls. If you skip `start` and call `process`, the implementation throws `IllegalStateException("Plugin not active")`.

To test ID selection with the JAR present, run:

```powershell
java -cp 'build/host;build/uppercase-plugin.jar' app.host.App unknown
```

Stdout:

```text
Không có provider: unknown
```

At this point **SPI still discovered `UppercasePlugin`**, yet the host did not select it because the ID did not match. This clearly distinguishes “no provider registered” from “provider exists but does not match selection criteria”.

On Linux/macOS use `mkdir -p`/`cp` instead of `New-Item`/`Copy-Item` and a colon `:` instead of a semicolon `;` between classpath entries; for example `java -cp 'build/host:build/uppercase-plugin.jar' app.host.App`.

### 6.7. Limitations of the Example

The example does not use an external dependency resolver, does not start multiple plugins according to a dependency graph, does not manage dedicated class loaders, and does not hot swap. Within **the same JVM and a single run**, `ServiceLoader` finds providers already present on the classpath. To install new JARs while the host is running, you must manage class loaders/module layers, API versions, related libraries, and old/new instance lifecycles. The demo only proves that discovery, dependency injection, and lifecycle are separate responsibilities.

In the example, `stop` can be called repeatedly without side effects. For plugins that open resources midway through `start` and then fail, the contract must require cleaning up partially opened resources (in `start` or `stop`). In complex applications with many plugins, the host should also catch cleanup errors individually so it can continue cleaning up other components.

## 7. Real-World Scenarios and How to Design for Them

### Scenario A: ServiceLoader Finds a Provider, but a Library Is Missing

A `CsvExporter` provider is properly declared for SPI, yet references a different library version than the runtime environment provides. During iteration, the JVM may throw `NoClassDefFoundError`, `LinkageError`, or `ServiceConfigurationError` depending on where the failure happens.

**How to handle:** verify artifacts/dependencies/bytecode and version policies; fix runtime packaging or the resolver. Do not assume calling `findFirst()` again or `reload()` is enough. Do not convert provider instantiation errors into `Optional.empty()` to silently fall back.

### Scenario B: Two Providers Implement the Same Contract

`FastCompressor` and `SafeCompressor` both implement `Compressor`. `findFirst()` merely gives “the first traversed provider” and knows nothing about performance or safety needs.

**How to handle:** the host defines a selection policy based on ID, supported formats, feature flags, priority, compatibility, and required constraints. If using priority, specify tie handling and do not rely on SPI order stability.

### Scenario C: A Provider Depends on Another Plugin

`ReportPlugin` requires `StoragePlugin` to be in the `ACTIVE` state. `ServiceLoader` can find both, yet has no idea `StoragePlugin` must start first.

**How to handle:** manage a dependency graph, check presence/versions, resolve order, and publish `ReportPlugin` to the registry only when its dependencies are ready. On shutdown, stop `ReportPlugin` before `StoragePlugin`.

### Scenario D: A Provider Fails to Start

`PaymentPlugin.start()` opens a connection and fails due to missing configuration. Succeeding at discovery does not mean the plugin is eligible to receive requests.

**How to handle:** transition the state machine to `FAILED`, do not publish the instance, log the error, and roll back opened resources. The host service should report health status rather than continuing to invoke an unstarted instance.

### Scenario E: Upgrading a Plugin in a Running JVM

A plugin JAR was loaded via an old loader. Replacing the file on disk and calling `ServiceLoader.reload()` does not switch running code to the new version.

**How to handle:** load the new version via an appropriate loader/layer, verify dependencies and API, start and health-check, shift traffic, drain old requests, stop the old version, clean up callbacks/threads, and close the old loader. Do not assume classes have been unloaded merely because `URLClassLoader.close()` was called.

## 8. Common Mistakes When Conflating Responsibilities

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| “`ServiceLoader` manages dependencies.” | It finds/instantiates providers, does not download JARs or resolve business plugin graphs | Use appropriate build dependency resolvers and runtime plugin resolvers |
| “Having a provider means ready to run.” | The constructor may succeed while config/readiness is missing | Verify dependencies, call start, publish only when ACTIVE |
| “`findFirst()` guarantees the right provider.” | Discovery order is not a business policy | Select by ID/capability/priority and check for duplicates |
| “`Optional.empty()` and `ServiceConfigurationError` are the same.” | One is normal absence; the other is a declaration/instantiation failure | Report config errors separately; never swallow errors |
| “A DI container equals plugin discovery.” | DI builds objects from configuration; SPI discovers providers from declarations | Explicitly connect discovery with dependency injection |
| “`start` runs automatically when ServiceLoader instantiates.” | SPI knows nothing about application-named business methods | Host explicitly invokes start/stop and controls state |
| “`reload()` upgrades code in place.” | It clears the provider lookup cache, does not replace already-defined classes | Use new loader/instance along with traffic-switching procedures |
| “Closing the loader stops plugins/unloads classes.” | Old instances/threads/callbacks can remain alive | Quiesce, stop, clean up, clear references, then close the loader |
| “Class loaders are a security sandbox.” | Plugins in the same JVM normally run with process privileges | Run untrusted code in isolated processes with restricted OS privileges |

## 9. Checklist for Plugin System Designers

- [ ] Clear service contract, stable API/version, and not duplicated across incompatible class loaders.
- [ ] Discovery mechanism properly declared (SPI descriptor or JPMS `uses/provides`).
- [ ] Deterministic provider selection policy: ID, capability, enabled state, version, priority; never implicitly rely on traversal order.
- [ ] Separate “not found” errors from descriptor/class-loading/constructor errors.
- [ ] List library, host service, and inter-plugin dependencies; verify versions, optional dependencies, conflicts, and cycles.
- [ ] Plugin manager determines start/stop order via dependency graph, supplies minimal context, and publishes only after readiness.
- [ ] Invocation controls concurrency, timeouts, input/output contracts, errors, and metrics.
- [ ] Shutdown blocks new requests, drains in-flight work, cleans up thoroughly, and leaves no references pinning old loaders.
- [ ] Hot reload (if needed) has a new-loader/instance strategy, traffic switching, rollback, and leak checks.

**Key takeaway:** `ServiceLoader` answers **“who can supply the service?”**; dependency management answers **“what does the provider need to run?”**; lifecycle management answers **“when is the provider allowed to run and how must it stop?”**. A host that selects providers properly needs all three, with clear policies at each boundary.

**References:** [`ServiceLoader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`ServiceConfigurationError` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html), [`URLClassLoader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [`ModuleLayer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).