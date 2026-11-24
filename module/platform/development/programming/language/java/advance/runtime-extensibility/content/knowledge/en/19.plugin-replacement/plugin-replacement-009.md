# Limits of Plugin Replacement Compared to Instrumentation or Process Restart

## 1. Three ways to update running Java code

A Java application extensible via plugins may need to swap an implementation while the process is still serving requests. However, **replacing a JAR on disk does not mean the JVM automatically replaces already-loaded classes**. Three independent strategies must be distinguished:

1. **Plugin replacement via a new class loader/module layer:** load a new implementation under a new class identity, shift traffic to it, and retire the old version.
2. **Instrumentation/redefinition/retransformation:** use `java.lang.instrument.Instrumentation` and JVM support to modify definitions of already-loaded classes within runtime constraints.
3. **JVM/process restart:** stop the old process, start a new process from a fixed artifact set, and initialize all state via startup procedures.

These three approaches differ in class identity, heap state, API compatibility, downtime, rollback complexity, and failure boundaries. None automatically guarantees zero downtime or rolling back all side effects.

## 2. Quick comparison

| Criterion | New plugin, new loader | Instrumentation | Process restart |
|---|---|---|---|
| Changing implementation | Yes, with new classes and new routing | Yes, within JVM class redefinition limits | Yes, via new artifact/process |
| Changing class structure/schema | Possible in new version, provided cross-boundary API is compatible | Standard HotSwap typically restricts adding/removing/changing fields/methods, superclasses, or interfaces; depends on VM capability | Yes when new binaries/configs/dependencies are compatible |
| Class identity | Old and new are two distinct classes if defining loaders differ | Preserves identity of the class being redefined | Creates fresh identities in a new JVM |
| Existing state | Must be migrated or kept outside the plugin | Existing objects stay alive; semantics may not change completely | Must restore from storage/checkpoints or accept losing in-memory state |
| Old resources | Must close threads, sockets, listeners, registries, and class loader | New bytecode does not automatically free created resources | OS reclaims process resources on exit, yet external side effects remain |
| Rollback | Can switch routing back if the old version remains live | Harder: must redefine backwards and handle mutated state | Usually re-runs the previous release/process per deployment policy |
| Fault isolation | Same process as host unless workers are separated | Same process | New process isolates crashes from old process, still needs safe deployment |

Do not equate class loader isolation with a security sandbox. A plugin shares process permissions and can break the entire system even when running in its own loader.

## 3. Replacing plugins via a new class loader: strengths and limits

Java allows a new loader to define a class with the same binary name as a class in an old loader. These two classes are **two distinct runtime types**, even if their source and package names match. This is why a host can keep two plugin versions simultaneously, yet also a source of `ClassCastException` if API classes get mixed across loaders.

A sound model:

```text
Host/Application Loader
   |-- stable plugin-api.jar (shared interfaces + DTOs)
   |
   +-- PluginLoaderV1 --> implementation v1 + dependencies v1
   |
   +-- PluginLoaderV2 --> implementation v2 + dependencies v2

Router: active = service instance from V2
```

Host and plugin **must share exactly one definition of the contract interface**. If each plugin loader redefines `demo.api.Service`, a V2 instance is not necessarily assignable to the host's `demo.api.Service`. A common strategy is parent-first for API packages, isolating only implementations and private dependencies inside plugin loaders.

### 3.1. Replacing a JAR on disk does not replace running classes

Loaded classes are not redefined simply because bytes inside a JAR file change. Many JVMs/class loaders cache classes and hold JAR handles; modifying a file currently in use can also trigger I/O errors or file locks on some operating systems.

Proper plugin replacement typically involves: staging the new-version artifact at **a versioned path**, verifying checksums/signatures, creating a new loader, loading the new plugin, running health checks, switching the router, waiting for old requests to finish, cleaning up plugin v1, and closing loader v1. Avoid overwriting a JAR actively used by a loader.

### 3.2. Class unloading is non-deterministic

Closing a `URLClassLoader` via `close()` helps release some loader-managed resources, yet **does not force the JVM to unload classes immediately**. Classes and loaders can remain reachable through:

- Plugin-created threads, thread context class loaders, or thread-local values.
- Static registries/singletons or callback listeners held by the host.
- Scheduled tasks, executors, timers, or shutdown hooks.
- Proxies, `MethodHandle`s, reflection metadata, or caches holding `Class<?>`.
- Plugin objects still referenced by in-flight requests.
- JNI/native libraries and specialized resources.

GC/class unloading depends on reachability and JVM mechanisms; `System.gc()` also makes no promise of immediate unloading. When investigating memory leaks, search for references retaining the old loader rather than just counting deleted `.jar` files.

### 3.3. In-flight state and transactions

If an order-processing plugin holds in-memory sessions or active transactions, switching to V2 can lose state or cause two versions to write concurrently to the same data source. Determine:

- Which session/state is stored inside the plugin versus external services.
- Whether migration or versioning of serialized data is required.
- Whether in-flight V1 requests are drained or cancelled, and with what timeout.
- Whether V1 and V2 can serve simultaneously against the same data schema.
- Whether idempotency keys are needed to prevent duplicate processing during cutover.

Do not discard loader V1 before confirming all associated requests and callbacks have completed.

## 4. Java 17+ example: swapping instances while keeping a shared contract

This small example illustrates routing between two implementations built under **the exact same interface contract**. It does not load JARs itself; separate class loaders are described in the next section. The goal is to clarify that swapping instances is a separate step from class redefinition.

Create file `SwitchPlugin.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class SwitchPlugin {
    public interface Service { String apply(String input); }

    public static final class V1 implements Service {
        public String apply(String input) { return "v1:" + input; }
    }

    public static final class V2 implements Service {
        public String apply(String input) { return "v2:" + input; }
    }

    public static void main(String[] args) {
        AtomicReference<Service> active = new AtomicReference<>(new V1());
        System.out.println(active.get().apply("hello"));

        Service candidate = new V2();
        if (!candidate.apply("health").equals("v2:health")) {
            throw new IllegalStateException("candidate failed health check");
        }
        active.set(candidate);
        System.out.println(active.get().apply("hello"));
    }
}
```

Compile and run:

```bash
javac SwitchPlugin.java
java SwitchPlugin
```

Exact stdout:

```text
v1:hello
v2:hello
```

The example shows `AtomicReference` can switch the implementation serving **new lookups**, yet does not transfer state or finish calls still holding the V1 reference. Production requires in-flight tracking and quiescence; you cannot simply call `set()` and immediately close all of V1.

### 4.1. Sketch for loading a new-version JAR

The snippet below is **illustrative and not standalone**, as it requires a shared `Service` and real implementation class:

```java
URL jar = Path.of("plugins/plugin-v2.jar").toUri().toURL();
URLClassLoader loader = new URLClassLoader(
        new URL[] {jar}, Service.class.getClassLoader());

Class<?> type = Class.forName("demo.plugin.ServiceImpl", true, loader);
Service newService = (Service) type.getDeclaredConstructor().newInstance();
```

Imports needed are `java.net.URL`, `java.net.URLClassLoader`, and `java.nio.file.Path`. The parent loader must supply the shared `Service` contract; the plugin JAR must not define its own copy of this interface. If the candidate fails, the host must release resources and close the newly created loader. On success, keep the loader alive until the plugin stops completely.

## 5. Instrumentation: modifying loaded classes instead of creating new identities

`java.lang.instrument.Instrumentation` is an API for Java agents to transform class files during loading or redefine/retransform already-loaded classes. This mechanism differs from updating a JAR on disk and does not arise automatically from `ClassLoader` or `ServiceLoader`.

### 5.1. Key APIs

- `addTransformer(ClassFileTransformer, canRetransform)` registers a transformer.
- `retransformClasses(Class<?>...)` requests retransformation of supported classes.
- `redefineClasses(ClassDefinition...)` supplies new class bytes to redefine specific classes.
- `isRedefineClassesSupported()`, `isRetransformClassesSupported()` check whether the VM supports the respective capabilities.
- `isModifiableClass(Class<?>)` checks whether a specific class can be modified.

These APIs require an instrumentation agent, not a general plugin-update API. A Java agent can be loaded at JVM startup via `-javaagent:agent.jar`; dynamic agent attachment support and policies depend on the JDK/runtime and deployment configuration.

### 5.2. Limits of redefinition

Under standard JVM HotSwap, redefining loaded classes typically does not support schema changes such as adding/removing fields/methods or changing names, modifiers, superclasses, or interfaces. Certain commercial tools or specialized runtimes offer stronger capabilities, which should not be assumed as standard across every JDK.

Even when redefinition succeeds:

- Already-created object instances retain their identity and state; constructors **do not re-run**.
- Static initialization (`<clinit>`) is not automatically re-executed solely due to redefinition.
- Active stack frames can continue executing the old method version's bytecode until returning from the frame; new invocations can use the new definition.
- Replacing bytecode does not perform data migration or update protocols with external systems.
- Bugs in an agent can impact the host JVM; instrumentation is not a process-isolation boundary.

Instrumentation suits monitoring, profiling, bounded method-body hotfixes, and tooling; it is not the default choice for upgrading full plugins when APIs/schemas change.

### 5.3. Example checking capabilities via an agent

This is an **illustrative** example of an agent entrypoint; it does not provide a complete agent JAR:

```java
import java.lang.instrument.Instrumentation;

public final class CapabilityAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("redefine: " + inst.isRedefineClassesSupported());
        System.out.println("retransform: " + inst.isRetransformClassesSupported());
    }
}
```

To use `premain`, the agent manifest must declare `Premain-Class: CapabilityAgent`; calling redefine/retransform APIs requires declaring the corresponding capability attributes per `java.lang.instrument` documentation, and VM support. Do not infer from this example that `isRedefineClassesSupported()` always returns `true` on every Java 17 distribution.

## 6. Process restart: a cleaner boundary for dependencies and class schemas

Starting a fresh JVM is a straightforward way to apply a complete set of artifacts: all class loaders, the module graph, static state, and native resources in the new JVM are initialized cleanly. Instead of trying to swap live classes, deployment can start a new-version process, verify health, and shift traffic.

Advantages:

- Class structures, library versions, and JVM flags can all be updated consistently.
- The dependency graph is built from scratch, avoiding stale class loader caches.
- Each process has its own lifecycle and memory; internal faults do not automatically bring down other processes.
- Rollback can re-run a previously verified release/process, provided schema/data compatibility allows.

Yet restart does not solve everything automatically:

- In-memory sessions/caches are lost unless persisted/restored.
- Database schema migrations might not be backward-compatible.
- External requests, message acks, or side effects can be duplicated without idempotency.
- The old process needs graceful draining before stopping to minimize disruption.
- Multiple versions running concurrently during rolling deployments may require two-way API/data compatibility.

### Rolling/blue-green deployment

A reliable operational strategy is running the new process in parallel, verifying health/readiness, switching the router/load balancer, draining the old process, and then stopping it. This is **orchestrated restart**, not in-JVM hot replacement. It can achieve very low disruption when designed properly, though it still depends on session routing and data compatibility.

## 7. Choosing a strategy by scope of change

| Type of change | Usually suitable approach | Reason |
|---|---|---|
| Changing internal plugin algorithm, stable contract | New plugin loader | Can run V1/V2 in parallel then switch routing |
| Changing plugin internal dependencies | New plugin loader if dependencies isolate cleanly | Avoids shared-loader conflicts |
| Changing a method body to fix a bug with same class identity | Instrumentation if VM and agent support it | Avoids creating new instances/versions, subject to schema limits |
| Adding/removing public API, changing binary contract | Restart or versioned interface/loader migration | Callers and state must align on contract |
| Changing JVM flags, native libraries, core framework | Process restart | Requires a completely fresh JVM environment |
| Requiring clear crash/resource boundaries | Separate process per plugin or restart | Class loaders do not isolate heap/process |
| Wanting fast rollback without losing in-memory state | Consider keeping V1/V2 plugin loaders alive with separated state | Requires controlling quiescence and compatibility |

These are guidelines, not absolute rules. If a plugin holds native state or unclosable threads, even swapping in a new loader may not be clean; restart is usually more reliable. If only a method body changes and an agent is already integrated, instrumentation can save time, though it still demands strict testing.

## 8. Controlled plugin update workflow

1. **Validate artifact:** verify version, checksum/signature, API contract compatibility, dependency versions, and policies before loading.
2. **Stage separately:** place the JAR at a path that does not overwrite the active artifact; create a new loader/module layer.
3. **Initialize candidate:** instantiate the plugin, initialize resources, and run self-tests and health checks before accepting traffic.
4. **Cutover:** switch routing for new requests; ensure consumers holding old instances keep running under an explicit policy.
5. **Drain:** wait for old in-flight tasks, background jobs, and callbacks to finish or time out.
6. **Stop and clean up:** stop the old plugin in dependency order, remove listeners, cancel tasks, and close resources and the loader.
7. **Observe:** monitor loader leaks, thread counts, errors, latency, and external state.
8. **Rollback:** if V2 fails, switch back to a still-healthy V1 or deploy the previous release per procedure; remember side effects already produced under V2.

**Never promise 100% rollback solely by swapping an `AtomicReference`.** State outside the JVM, written data, or emitted events do not automatically reverse.

## 9. Common errors

| Symptom | Cause | Recommendation |
|---|---|---|
| Replaced JAR yet old code still runs | Classes already defined by JVM and cached by loader | Create a new loader or restart |
| `ClassCastException` between host and plugin | API defined by multiple loaders | Keep shared API contract in parent loader |
| Metaspace grows after repeated reloads | Old loader remains reachable via threads, listeners, static registries | Audit references, resource cleanup, and GC roots |
| JAR file locked during update | Loader still holds open JAR/file handles | Use versioned artifacts; close loader after draining |
| HotSwap reports unsupported schema change | Instrumentation supports only limited modifications | Use a new loader or restart when changing class schemas |
| V2 healthy yet sessions lost | State lived inside V1 instances | Move state to independent storage or implement migration |
| Rollback fails due to new DB schema | External data is incompatible with V1 | Apply expand/contract migrations; test backward compatibility |
| Plugin refuses to stop | Threads/native resources not properly lifecycle-managed | Design explicit close/cancel or move plugin into a separate process |

## 10. Release checklist

- [ ] A contract/version policy exists for the host and plugins.
- [ ] The new plugin loader is created from an artifact that does not overwrite the running copy.
- [ ] Shared APIs are not redundantly loaded by plugin loaders.
- [ ] Health checks run before cutover and in-flight requests drain after cutover.
- [ ] Cleanup handles all threads, executors, listeners, resources, and the loader of the old version.
- [ ] Class unloading/metaspace is tested under repeated reload workloads.
- [ ] Instrumentation is used only when VM capabilities and schema change scope permit.
- [ ] Restarts/rolling deployments include session/data migration and release rollback plans.

**Conclusion:** Replacing a plugin via a new loader creates a new implementation without mutating already-loaded class definitions; instrumentation swaps bytecode of existing classes within VM constraints; restarting rebuilds the entire JVM from new artifacts. Choose an update strategy based on contract compatibility, state migration, resource lifecycles, and uptime requirements—not merely on whether a JAR file on disk can be overwritten.