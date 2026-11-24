# Preparing, Validating, and Switching the Active Reference to a New Generation

**Safe plugin replacement at runtime is not overwriting a JAR, calling `ServiceLoader` again, or immediately assigning a new instance to a variable.** A plugin may be processing requests, holding resources, running background threads, maintaining its own class loader, caches, and state. To upgrade from version V1 to V2 without breaking in-flight requests, three phases must be cleanly separated:

1. **Prepare:** build a new *plugin generation* in a state not yet serving traffic: locate the artifact, load and configure code, initialize dependencies, and perform warm-up.
2. **Validate:** verify compatibility, configuration, permissions, connectivity, behavior/health, resource budgets, and cleanup capability; if it fails, discard only the candidate **without touching the active generation**.
3. **Publish / cutover:** publish **an active reference** pointing to the new generation via an atomic operation. New requests are routed to the new generation; requests that already entered V1 continue using V1. Then *retire → drain → close* V1 according to lifecycle policy.

This is the **prepare–validate–atomic switch–graceful retirement** model. This article explains how to build it with Java 17+, why in-flight requests must be managed, and common bugs when old class loaders, providers, resources, or state are still retained.

## 1. What is a “plugin generation” and why manage by generation?

A *generation* is an immutable-identity deployment unit within a single lifecycle. It may hold:

- `generationId` and `version` (or artifact hash), plugin ID, and compatibility-control metadata;
- its own loader: `URLClassLoader` or `ModuleLayer` along with the layer's modules/class loaders;
- implementation instances of the **host-owned API**;
- validated configuration, immutable routing table, codec list, endpoints, or capability metadata;
- resource handles: executors, caches, connections, listeners, streams, files/JARs, registry registrations;
- lifecycle state, number of active requests using it (reference count/lease), and cleanup mechanisms.

`Generation` does not necessarily have to store all of these inside a single class, but **must have a clear owner** responsible for initialization/closing. A conceptual representation:

```text
Host / PluginRegistry
    |
    | active (atomic reference)
    v
Generation V2  [ACTIVE]
    |- Plugin API instance
    |- ClassLoader / ModuleLayer V2
    |- Immutable configuration / routing
    |- Resources owned by V2
    +- In-flight lease count

Generation V1  [RETIRING]
    |- Plugin API instance
    |- ClassLoader / ModuleLayer V1
    |- Resources owned by V1
    +- In-flight lease count > 0  (not yet closed)
```

The same binary name `com.example.plugin.Handler` **does not mean the same class identity** across two different loaders. Java identifies a type by **(class name, defining class loader)**. For new plugin code, a new class loader/module layer is usually required; do not expect replacing a JAR file on disk to turn already-loaded V1 classes into V2.

**The active reference** is the gate selecting the current generation, not a method to unload classes or roll back data. V1 objects remain alive until no strong references exist; `URLClassLoader.close()` also does not immediately destroy already-created `Class` objects or instances.

## 2. State contract: PREPARING → VALIDATED → ACTIVE → RETIRING → CLOSED

A lifecycle flow should be defined before writing code:

| State | Meaning | Who may use it? | Valid actions |
| --- | --- | --- | --- |
| `PREPARING` | Loading/initializing candidate, not yet ready | Plugin management thread only | Configure, start, warm up; error → cleanup |
| `VALIDATED` / `READY` | Passed checks, not yet active | Plugin manager, controlled tests | Publish or discard candidate |
| `ACTIVE` | Generation selected by active reference to receive work | New requests and in-flight requests | Acquire lease, execute business logic |
| `RETIRING` | Accepts no new work; waits for old requests to exit | Holders of already-valid leases only | Drain, await completion, release |
| `CLOSED` | Resources closed and owner references dropped | Nobody | Must not invoke plugin or reuse generation |
| `FAILED` | Candidate failed prepare/validate or suffered lifecycle error | Management only for diagnostics and cleanup | Quarantine, close, log, retry from a **new** generation |

The state labels above are **an application model**, not a built-in JDK enum. Real systems may add `DISABLED`, `DEGRADED`, or `ROLLBACK_READY`. The essential point is that **a generation that has not reached READY must not be visible through the active pointer**.

An invariant to preserve:

> If a request has been accepted and holds a lease for V1, V1 must not close resources that the request still needs, even when `active` already points to V2.

Therefore `active.set(V2)` may suffice to *select a generation* but is **not enough to manage cleanup**.

## 3. Prepare phase: build a complete candidate without publishing

The plugin manager layer should build the candidate separately from the running generation, for example:

```text
Artifact V2 (JAR/module + metadata + checksum)
       |
       v
Policy / dependency / API compatibility checks
       |
       v
ClassLoader V2 or ModuleLayer V2
       |
       v
Discover provider / instantiate plugin / inject config
       |
       v
Start resources + warm-up + build routing snapshot
       |
       v
Candidate Generation V2 [not serving requests]
```

### What needs to be prepared

**Artifact and dependencies:** check plugin ID, version, and origin; verify checksums/signatures per policy, scan dependency/module conflicts, and confirm both metadata and JAR contents belong to the exact approved artifact. Avoid loading V2 from a directory undergoing in-place deployment where another writer is mutating files.

**Class loader/module:** keep **service interfaces or the host API** in a controlled shared loader; V1 and V2 implementations can live in separate loaders/layers. If a plugin loads its own copy of the service interface inside a child loader, the host may encounter `ClassCastException` despite identical class names. When using JPMS, verify `requires`, `uses`, `provides`, and the resulting module graph.

**Dependencies and configuration:** validate syntax/schemas/secret references, endpoints, permissions/capabilities, mappings, and compatibility policies. A generation's configuration snapshot should be immutable or modified only through a separate versioned mechanism.

**Initialization:** constructors, dependency injection, `start`, initialization, and warm-up can **execute plugin code**. Do not treat “not yet published” as a sandbox: a candidate can still open network connections, register listeners, or spawn threads during initialization. Side effects must have an owner and rollback/cleanup capability.

**Routing snapshot:** pre-build the map from command/service names to concrete handlers rather than letting requests scan `ServiceLoader`/classpath dynamically during handling. This reduces races between discovery and cutover.

### Responsibility illustration, not standalone code

```java
// Java-style pseudocode: the types are contracts defined by the application.
PreparedGeneration candidate = prepare(artifact, config);
try {
    validate(candidate);     // do not touch active pointer
    publish(candidate);      // atomic switch once ready
} catch (Exception failure) {
    if (!candidate.wasPublished()) {
        candidate.close();   // discard only the candidate
    }
    throw failure;
}
```

In production code, clear ownership/handoff is needed to avoid **accidentally closing the already-published candidate** when old cleanup fails *after* cutover. It is best to separate `prepare/validate` errors from `retire old` errors, and have only the manager know the exact moment ownership transfers from candidate to registry. The types/methods above are architectural illustrations, **not part of Java SE**.

## 4. Validate before cutover: from “loadable” to “ready to serve”

Succeeding at `ClassLoader.loadClass` or `ServiceLoader.findFirst` **does not prove** the plugin is ready. Depending on the API contract, checks may include:

| Check category | Question to answer | Failure policy |
| --- | --- | --- |
| Integrity | Does the artifact match approved hash, signature, and origin? | Reject immediately before loading |
| Compatibility | Do plugin API/ABI, Java version, dependencies, module reads/exports, and schemas align? | Reject |
| Configuration | Missing secrets, invalid endpoints, conflicting feature flags or mappings? | Reject before publishing |
| Discovery | Are required providers present? Duplicate provider IDs or conflicting service names? | Reject or select by explicit policy |
| Liveness/health | Does the plugin initialize and respond to probes within limits? | Reject/timeout candidate |
| Behavior | Smoke tests, contract tests, edge-case inputs, serialization formats | Reject if contract is violated |
| Resource budget | Does the candidate exceed limits for file descriptors, threads, connections, or heap? | Reject or defer rollout |
| Cleanup readiness | On close, does it stop threads, cancel registrations, release caches/streams? | Reject if lifecycle is unclear |
| Isolation | Does it have permission to access host/system APIs per trust policy? | Block; do not use class loaders as a sandbox |

**Warm-up and readiness tests should have isolatable or reversible side effects.** Avoid a “test” accidentally sending payments, emails, or mutating production data. If testing an external effect is unavoidable, use a test environment, idempotent requests, or a well-designed transaction mechanism.

### Pre-publish failure rule

If `prepare` or `validate` fails, `active` continues pointing to V1 and in-flight requests proceed. The candidate is cleaned up within its own scope, the reason is logged, and objects/loaders in an indeterminate state are never reused.

```text
V1 [ACTIVE] ---- still serving ----
              Candidate V2 [PREPARING]
                       |
                 validation FAIL
                       v
                 close/quarantine V2
V1 [ACTIVE] ---- unchanged -----
```

This is a major advantage of **“prepare completely before switching”** compared to tearing down V1 first and then attempting to load V2.

## 5. Atomic publication: switch only a fully initialized reference

The active generation can be held in:

```java
private final java.util.concurrent.atomic.AtomicReference<Generation> active =
        new java.util.concurrent.atomic.AtomicReference<>();
```

This is a snippet; `Generation` is an application type. After creating/validating V2 completely:

```java
Generation old = active.getAndSet(newGeneration);
retireWhenDrained(old);
```

This is also a snippet; `retireWhenDrained` is application-defined. `getAndSet` has atomic effect for the reference: readers see **V1 or V2**, never “half an object.” Appropriate atomic/volatile operations provide a **happens-before** relationship so data initialized by V2 before publication is properly observed by readers.

**What is atomic here is the reference pointer, not the entire system outside the JVM.** Switching `active` does not automatically migrate DB transactions, event subscriptions, caches, sockets, data schemas, or all running requests to the new version.

### Consistent snapshot per request

Each request should **read `active` once upon entry** and keep that exact generation throughout the operation:

```java
Generation current = active.get();
return current.plugin.handle(request);
```

This is a snippet **without lease/lifecycle safety**, illustrating only the snapshot principle. If a request reads `active` multiple times across different steps, it may use V1 in the first step and V2 in the final step; state, serialization, or transactions would mix generations.

If a registry holds multiple independent fields `activePlugin`, `activeConfig`, `activeLoader`, updating each field separately risks readers seeing the V2 plugin with V1 configuration. Bundle related items into **one immutable Generation/Snapshot** and publish *a single reference*.

### Multiple writers: an atomic pointer is not enough

Two threads deploying V2 and V3 concurrently can race. `getAndSet` remains atomic for each individual write, but without a policy, V3 could be overwritten by V2 after V3 already published, or cleanup could happen out of order. You should:

- **Serialize writers** with a lock or per-plugin-ID queue; or
- use `compareAndSet(expectedGeneration, candidate)` with an explicit state machine and cleanup for candidates that lose the race.

Only one thread/manager should decide which generation is valid to activate. In multi-instance/cluster systems, `AtomicReference` **only applies within a single JVM**; a separate control plane/rollout policy is required to coordinate multiple processes.

## 6. V1 cannot be closed immediately after setting active = V2

Suppose request A already acquired V1 and is using V1's sockets, codecs, or state. At that moment the manager switches to V2. Calling `V1.close()` immediately can cause A to hit:

- `IllegalStateException: closed` from the provider;
- errors on revoked sockets/files/database connections;
- callbacks/listeners unregistered mid-transaction;
- inconsistent data if A's workflow continues reading from V2 via a global registry.

The proper model is **graceful retirement**:

1. After cutover, V1 accepts no *new leases* for requests admitted past the boundary.
2. Requests already holding a V1 lease continue using V1 until completion, subject to timeout and error policies.
3. When the reference count reaches 0, the owner invokes V1 cleanup **once**.
4. Only after cleanup are strong references to V1's loader/layer/resources dropped so GC has a chance to reclaim them.

### Lease/reference count

This can be designed as:

```text
active -> V1
request A: acquire(V1) -> inFlight(V1)=1

prepare/validate(V2)
atomic active -> V2
retire(V1)          -> V1 accepts no new leases
request B: acquire(V2) -> inFlight(V2)=1

request A: release(V1) -> inFlight(V1)=0 -> close(V1)
request B: release(V2) -> V2 remains ACTIVE
```

The tricky part is **the race between reading `active` and acquiring a lease**. A reader might read the V1 reference before cutover, yet arrive late after the manager already retired V1. Therefore code must check state under the same synchronization mechanism of the generation, and may **recheck `active`** after acquiring to avoid accepting a generation that is no longer published.

If a system demands an **absolute boundary** where “every task starting execution *after the switch timestamp* must use V2,” even tasks that grabbed the reference beforehand but have not entered the method, `AtomicReference` + recheck alone does not give a completely locked point between check and invoke; an explicit *admission* point or an appropriate gate/read-write lock is required. Most systems treat requests already admitted onto V1 as *in-flight* and allow them to finish.

## 7. Standalone Java 17 example: validate → atomic switch → drain → cleanup

This example requires no real plugin JARs in order to **isolate and verify the exact generation-switching mechanics**. `DemoPlugin` acts as an implementation already loaded by a plugin manager. In a real application, `prepare` builds the loader/module layer, `ServiceLoader`, and provider; the `Registry` reference/lifecycle management still applies.

Features of the example:

- `Registry` publishes generations via `AtomicReference<Generation>`; all replacement operations are serialized by `synchronized`.
- `DemoPlugin.checkReady()` rejects an unhealthy candidate before publishing; failed candidates are closed and V1 remains untouched.
- Requests acquire a `Lease`; `Generation` protects `leases`/`retired` with a monitor, ensuring cleanup is claimed only once.
- When `replace` succeeds, V2 receives new requests; an already-entered V1 request is held with a `CountDownLatch` to prove V1 **is not closed prematurely**.
- When the V1 request releases the final lease, V1 closes; `shutdown` subsequently closes V2.

### 7.1. Source code: PluginGenerationDemo.java

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class PluginGenerationDemo {
    static final class DemoPlugin implements AutoCloseable {
        final String version;
        final CountDownLatch entered;
        final CountDownLatch resume;
        final boolean healthy;
        final AtomicBoolean closed = new AtomicBoolean();

        DemoPlugin(String version, CountDownLatch entered,
                   CountDownLatch resume, boolean healthy) {
            this.version = version;
            this.entered = entered;
            this.resume = resume;
            this.healthy = healthy;
        }

        void checkReady() {
            if (!healthy || !execute("probe").equals(version + ":probe")) {
                throw new IllegalStateException("health check failed: " + version);
            }
        }

        String execute(String input) {
            if ("hold".equals(input) && entered != null) {
                entered.countDown();
                try {
                    resume.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", ex);
                }
            }
            if (closed.get()) throw new IllegalStateException("already closed: " + version);
            return version + ":" + input;
        }

        @Override
        public void close() { closed.set(true); }
    }

    static final class Generation {
        final DemoPlugin plugin;
        private int leases;
        private boolean retired;
        private boolean cleanupClaimed;

        Generation(DemoPlugin plugin) { this.plugin = plugin; }

        synchronized Lease tryAcquire() {
            if (retired) return null;
            leases++;
            return new Lease(this);
        }

        void release() {
            DemoPlugin cleanup;
            synchronized (this) {
                if (leases <= 0) throw new IllegalStateException("unbalanced lease");
                leases--;
                cleanup = claimCleanup();
            }
            if (cleanup != null) cleanup.close();
        }

        void retire() {
            DemoPlugin cleanup;
            synchronized (this) {
                retired = true;
                cleanup = claimCleanup();
            }
            if (cleanup != null) cleanup.close();
        }

        // Only call while holding this generation's monitor.
        private DemoPlugin claimCleanup() {
            if (retired && leases == 0 && !cleanupClaimed) {
                cleanupClaimed = true;
                return plugin;
            }
            return null;
        }
    }

    static final class Lease implements AutoCloseable {
        final Generation owner;
        private final AtomicBoolean done = new AtomicBoolean();

        Lease(Generation owner) { this.owner = owner; }

        @Override
        public void close() {
            if (done.compareAndSet(false, true)) owner.release();
        }
    }

    static final class Registry {
        private final AtomicReference<Generation> active;

        Registry(DemoPlugin initial) {
            initial.checkReady();
            active = new AtomicReference<>(new Generation(initial));
        }

        String invoke(String input) {
            for (;;) {
                Generation current = active.get();
                if (current == null) throw new IllegalStateException("registry closed");
                Lease lease = current.tryAcquire();
                if (lease == null) continue;
                if (active.get() != current) {
                    lease.close();
                    continue;
                }
                try (lease) {
                    return current.plugin.execute(input);
                }
            }
        }

        // Serializes all writers. The candidate is checked before publication.
        synchronized void replace(DemoPlugin candidate) {
            try {
                candidate.checkReady();
            } catch (RuntimeException failure) {
                candidate.close();
                throw failure;
            }
            if (active.get() == null) {
                candidate.close();
                throw new IllegalStateException("registry closed");
            }
            Generation previous = active.getAndSet(new Generation(candidate));
            previous.retire();
        }

        synchronized void shutdown() {
            Generation previous = active.getAndSet(null);
            if (previous != null) previous.retire();
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch resume = new CountDownLatch(1);
        DemoPlugin first = new DemoPlugin("v1", entered, resume, true);
        Registry registry = new Registry(first);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> inFlight = pool.submit(() -> registry.invoke("hold"));
            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("old call did not start");
            }

            DemoPlugin bad = new DemoPlugin("bad", null, null, false);
            try {
                registry.replace(bad);
                throw new AssertionError("invalid candidate accepted");
            } catch (IllegalStateException expected) {
                System.out.println("rejected=" + bad.closed.get());
            }
            System.out.println("afterReject=" + registry.invoke("check"));

            DemoPlugin next = new DemoPlugin("v2", null, null, true);
            registry.replace(next);
            System.out.println("afterSwap=" + registry.invoke("check"));
            System.out.println("oldClosedBeforeDrain=" + first.closed.get());

            resume.countDown();
            System.out.println("inFlight=" + inFlight.get(5, TimeUnit.SECONDS));
            System.out.println("oldClosedAfterDrain=" + first.closed.get());

            registry.shutdown();
            System.out.println("newClosedOnShutdown=" + next.closed.get());
        } finally {
            resume.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
            registry.shutdown();
        }
    }
}
```

### 7.2. Running with Java 17

Save the file as `PluginGenerationDemo.java`. In the directory containing the file:

```bash
javac --release 17 PluginGenerationDemo.java
java PluginGenerationDemo
```

**Stdout verified with `javac --release 17` and `java`:**

```text
rejected=true
afterReject=v1:check
afterSwap=v2:check
oldClosedBeforeDrain=false
inFlight=v1:hold
oldClosedAfterDrain=true
newClosedOnShutdown=true
```

### 7.3. Detailed explanation of synchronization points

**Failed candidate does not affect active.** `DemoPlugin("bad", ..., false)` is rejected by `checkReady` and closed; `afterReject=v1:check` proves `Registry` is still routing to V1. In production, candidate cleanup must also close the class loader/resources it owns.

**Atomic cutover after readiness.** `registry.replace(next)` checks V2 first, and only then calls `active.getAndSet(new Generation(next))`. Thus `afterSwap=v2:check` while the old request still holds V1. `synchronized replace/shutdown` prevents two writers from racing; requests do not have to lock the entire registry on every invocation.

**Leases protected per generation.** `Generation.tryAcquire/release/retire` use the same monitor to update `leases` and `retired`. If V1 is already retired, it rejects new leases. If V1 is not yet retired but the pointer changed, `Registry.invoke` detects `active.get() != current`, releases the just-acquired lease, and retries with the new generation.

**Closed exactly once.** `cleanupClaimed` is updated under the monitor in `claimCleanup`; only the last thread to claim it successfully calls `plugin.close()`. In the example, `close` merely sets an `AtomicBoolean` without performing slow work. In production, log/isolate close errors and run heavy shutdown outside locks so other tasks are not delayed.

**Old request preserved.** `CountDownLatch` ensures the V1 request has already entered `execute("hold")` before cutover, then pauses it. `oldClosedBeforeDrain=false` shows V1 has not been closed yet. Once the latch is released, the V1 request completes, `Lease.close` decrements the count to 0, and V1 closes; `oldClosedAfterDrain=true` verifies that state.

**Shutdown respects draining.** `Registry.shutdown()` clears the active pointer and marks V2 retired. In the demo there are no remaining in-flight V2 requests at that moment, so V2 closes immediately. If leases remained, by the same logic V2 would close only when the last lease released.

**Intentional limitations:** this example uses a simple in-process plugin and does *not* implement JAR/module isolation, distributed rollout, drain timeouts, persistent state migration, or crash recovery. `DemoPlugin.checkReady` is designed with no side effects; real applications must define their own safe health probes. `DemoPlugin` has simple thread-safe behavior within the scope of the example; arbitrary plugins do not automatically become thread-safe merely because `Registry` uses leases.

## 8. Important race conditions to understand

### Race A — Reader grabs V1 before switch but acquires after retire

```text
Request R                         Writer W
-------------------------------   ------------------------------
g = active.get() -> V1
                                  active.getAndSet(V2)
                                  V1.retire()
lease = V1.tryAcquire() -> null
R retry -> active.get() -> V2
```

Because V1 is already `retired`, the request cannot create a new lease for V1; it retries with V2.

### Race B — Reader acquires V1 right before switch

```text
Request R                         Writer W
-------------------------------   ------------------------------
g = active.get() -> V1
lease = V1.tryAcquire() -> OK
                                  active.getAndSet(V2)
R sees active.get() != g
R releases V1; retries V2         V1.retire() / drain
```

**Rechecking `active`** reduces the risk of a request being misrouted to an old generation during the reference-read → acquire window. If the recheck succeeds and the writer switches afterwards, that request is considered admitted on V1; it holds its lease until completion. To strictly block even that case, a stronger admission/switch mechanism is needed, such as a gate or read/write lock wrapping the start of the call.

### Race C — Last release and retire happen concurrently

```text
Request R                         Writer W
-------------------------------   ------------------------------
release(V1): leases from 1 -> 0
                                  retire(V1): retired = true
         or in reverse order
Both update under the same V1 monitor
=> only one thread claims cleanup
=> close is called once
```

If in-flight counts are tracked with an `AtomicInteger` separated from `retired` without a clear protocol, close can occur while another thread has just incremented the lease. Use a proper monitor/CAS state machine instead of ad-hoc counter arithmetic.

### Race D — Managers run two replacements simultaneously

```text
Writer A: prepare V2
Writer B: prepare V3
Writer B: publish V3
Writer A: publish V2    (unintended downgrade)
```

`AtomicReference.getAndSet` **does not prevent this business scenario**. The demo locks all writers with `synchronized`; multi-worker systems need an additional version/sequence policy: only publish a candidate against an expected generation or an approved rollout epoch. On a failed `compareAndSet`, clean up the unpublished candidate and report a conflict rather than retrying endlessly against the wrong version.

## 9. When a candidate fails vs when the new active fails: two different policies

| Failure time | Active serving | Handling |
| --- | --- | --- |
| Loading artifact or building V2 loader fails | V1 | Keep V1; close partially initialized V2 pieces |
| V2 validation/health fails | V1 | Reject V2, record diagnostics, keep V1 |
| Writers contend and candidate loses publish right | Generation chosen by another writer | Discard losing candidate, do not overwrite |
| V2 publish succeeds, V1 cleanup fails | V2 | **Do not** treat V2 as unpublished; log/manage V1 cleanup retries per policy |
| V2 starts serving then exhibits behavioral errors | V2 (already has requests) | Investigate, throttle traffic, consider rolling back with a valid generation |
| Process crashes mid-way | Depends on step and restart policy | Must have a manifest/desired version and recovery independent of RAM variables |

**Post-cutover failures cannot be handled unconditionally by saying “just assign the pointer back to roll back.”** Generation V1 may be retired, have closed resources, or no longer be safe to resume. For fast rollback:

- you can **keep V1 in a standby/rollback-ready state** for a period, *unclosed*, with its own owner/lifecycle, while capping resources and disallowing new requests to V1 unless reactivated per protocol;
- or **prepare + validate a new generation** from the known-good V1 artifact and publish it as a normal cutover;
- ensure V1 remains compatible with database schemas, data, or messages already written by V2. Rolling back code **does not automatically roll back data**.

If V2 already produced external side effects (transactions, published events, external API calls), removing the V2 pointer does not undo those effects. Transactions, idempotency, compensation, or an appropriate data migration plan are needed.

## 10. Data versioning, long sessions, and cross-generation behavior

For simple stateless plugins, request-scoped leases are usually enough. However, many plugins retain sessions or state across requests:

- a user session was created by V1, yet the next request routes to V2;
- tokens, caches, serialized payloads, or database records created by V2 cannot be read by V1;
- multi-step workflows require the same policy/schema version;
- a queue message began processing in V1, yet an async callback completes after cutover.

In these cases, define the **scope** of generation pinning:

| Case | Suggestion |
| --- | --- |
| Independent, stateless HTTP request | Per-request lease |
| Stateful session | Pin session to a generation or perform versioned migration |
| Long-running job / async callback | Lease covers the entire job, including callbacks and completion |
| Streaming connection | Lease lasts the stream's lifetime; dedicated timeout/drain |
| Plugin-created scheduled task | Task tied to owning generation; must stop/join on retire |
| Multi-step transaction | Pin the same generation across the transaction or design a compatibility protocol |

Do not “re-read `active` in every method” inside a stateful workflow. Pass the snapshot/lease down the processing layers so it uses only the single selected generation.

### State migration and compatibility

If V2 must inherit state from V1, pick a clear procedure:

- **Externalized state:** state lives in a datastore with a shared schema/version, and each generation uses a compatible adapter; usually easier to cut over.
- **Snapshot/restore:** capture V1 state at a consistent point and verify V2 can read it; may require pausing writes/admissions so cutover is no longer fully zero-downtime.
- **Dual read/dual write or versioned data:** requires migration, reconciliation, and rollback logic; risk increases when two generations operate simultaneously.
- **Session stickiness:** keep V1 for old sessions until they expire and route new sessions to V2; must bound the maximum retention time of old loaders/resources.

**An atomic pointer only solves generation routing**, not atomic state transitions in external storage systems. Determine compatibility windows, migration order, rollback cutoffs, and handling of unmigrated V1 state in advance.

## 11. Integrating with a real Java plugin loader: shared API, isolated implementation

In a Java application, the host should define service/plugin interfaces in a shared class loader and expose only a stable API to plugins. Conceptual pipeline:

```text
Host interface (parent loader)
          ^
          | implements
Plugin V1 implementation (loader L1)
Plugin V2 implementation (loader L2)

PluginManager:
  prepare V2 -> create L2 -> discover provider -> validate
  publish Generation(V2, L2)
  retire V1 -> drain -> close provider/resources/L1
```

Building a candidate with classpath SPI typically looks like this **snippet**:

```java
URLClassLoader candidateLoader = new URLClassLoader(
        new URL[] {pluginJar.toUri().toURL()},
        PluginApi.class.getClassLoader());

ServiceLoader<PluginApi> discovery =
        ServiceLoader.load(PluginApi.class, candidateLoader);

List<PluginApi> found = new ArrayList<>();
for (PluginApi provider : discovery) {
    found.add(provider);
}
// Select provider by plugin ID/version/capabilities; validate before publish.
// Candidate owner must close the loader and provider resources if rejected.
```

The snippet above requires `PluginApi` and `pluginJar` to be defined along with imports for `URLClassLoader`, `URL`, `ServiceLoader`, `ArrayList`, and `List`; it is **not a standalone runnable program**. The plugin JAR needs `META-INF/services/<fully-qualified-API-name>` SPI metadata on the classpath; with named modules it uses `provides`/`uses` and `ModuleLayer`. `ServiceLoader` is not a generation manager; it only assists discovery. Do not share a single `ServiceLoader` instance across concurrent threads while reloading/discovering.

### Parent-first and class identity hazards

- Loader V2 may still pick up classes/resources from the parent loader on name collisions due to parent-first delegation. Isolate implementation namespaces and test that the right artifact is selected.
- `PluginApi` must not have one copy loaded by the parent and another private copy in the child that gets cross-cast. The host API should belong to the shared parent, and the implementation to the plugin loader.
- With module layers, verify `ModuleFinder`, `Configuration.resolve/resolveAndBind`, and the class loader mapping; a new `ModuleLayer` does not automatically replace an old layer.
- `ClassLoader`/`ModuleLayer` can retain classes/metadata until no references remain; generation-based hot swapping is not class redefinition.

### Cleaning up loaders, providers, and external-JVM resources

A real owner typically must manage:

1. Stop accepting new jobs/timers/callbacks for V1, halt scheduling, and unregister event listeners.
2. Wait for in-flight tasks, streams, and async callbacks to complete or hit a deadline.
3. Call `close()` on the provider per contract; flush/roll back owned resources, and properly close DB/network clients.
4. Shut down/join plugin-created executors; clean up `ThreadLocal`, TCCL, and references holding the plugin class loader.
5. Unregister MBeans, JDBC drivers, registries, or relevant caches if registered by the plugin.
6. Close `URLClassLoader` once all activity needing its managed resources has finished. `close()` **does not guarantee immediate unloading of loaded classes**.
7. Drop host strong references to plugin instances, loaders, reflection `Method`s, `Class`es, lambdas, caches, or threads.
8. Monitor heap/metaspace/class unloading and close failures; do not “swallow” cleanup errors that leave broken generations alive forever.

Avoid spawning unbounded background threads carrying V1's context class loader: even after the registry drops the V1 pointer, a live thread can retain the old loader. Likewise, callbacks registered in a host singleton can retain plugin objects through listener references.

## 12. Cutover and cleanup should not share one failure boundary

A production design should separate **the moment cutover commits** from the cleanup steps that happen afterwards. For example:

```text
prepare V2 ──> validate V2 ──> atomic publish V2
     |               |                  |
     | FAIL          | FAIL             | SUCCESS (committed)
     v               v                  v
  close V2         close V2          schedule retire/drain V1
  V1 active        V1 active         V2 active
                                          |
                                  close V1 may fail
                                          |
                                  record / retry cleanup
                                  DO NOT treat the publish as cancelled
```

If `old.retire()` runs synchronously and the old plugin's `close()` throws an exception after `getAndSet`, the replacement method may throw to the caller even though V2 **is already active**. Calling code must not interpret that exception as “V2 did not go live.” A better contract separates the cutover outcome from cleanup status, or runs cleanup asynchronously under policy with clear logs/metrics.

In Section 7's example, `DemoPlugin.close()` merely sets a boolean and never throws; thus the main flow illustrates cutover logic cleanly. With arbitrary plugins, isolate `close` exceptions and ensure shutdown does not invoke arbitrary code while holding a state-protecting monitor.

### How long should old resources wait before closing?

There are two main policies:

- **Unbounded graceful drain:** avoids cutting off requests, but risks keeping V1's class loader/connections alive indefinitely if a request hangs.
- **Deadline-bounded graceful drain:** waits for a configured interval, then performs cancellation/cooperative stop or process isolation. Within the same JVM, there is no general safe way to forcibly kill arbitrary running Java plugin threads. If requests are still using resources, calling a forced close can cause errors; this risk and its handling must be specified.

When hard deadlines are required for untrusted plugins, consider running each generation in a separate **worker process**: route new requests to the V2 process, wait for V1 to drain, and after the deadline terminate the V1 process via OS mechanisms. Process boundaries bound CPU/RAM/IO and isolate crashes, though idempotency and external side effects still need management.

## 13. Observability and testing to trust an upgrade pipeline

Useful metrics/logs should include at least `pluginId` and `generationId`:

- Duration of `prepare`, `validate`, warm-up, cutover, drain, and cleanup.
- Rejected candidate count, invalidity reasons, artifact hash/version, provider ID.
- Current active generation, requested/running versions, and rollout conflict count.
- In-flight leases per generation, age of old requests, count of `RETIRING` generations.
- Exception/error rate, latency, and output quality of V1 vs V2 after cutover.
- Remaining live executors/threads, connections/file descriptors, heap/metaspace after close.
- Rollback count and reasons, state/schema drift, cache migration errors.

**Do not log secrets, tokens, customer data, or sensitive plugin code** just for debugging. Audit events should answer *who requested*, *which artifact was validated*, *which generation was published*, *when it was retired*, and *whether cleanup completed*.

### Minimum test suite

| Test | What it must prove |
| --- | --- |
| Prepare fails | V1 stays active, candidate is closed, no partial publish |
| Contract/health fails | Active pointer unchanged; old requests unaffected |
| Cutover succeeds | New requests see V2 consistently; never half V1/half V2 |
| V1 request still running | V1 not closed while lease > 0; request completes on V1 |
| Last release vs retire | Cleanup runs exactly once under different interleavings |
| Acquire before/after cutover | No new leases issued to retired generation; retry logic works |
| Two competing writers | Serialization/CAS/version policy enforced; no unlawful downgrade |
| Shutdown concurrent with requests | New requests rejected, leased requests drained per policy |
| Plugin holds background thread/listener | Cleanup actually unregisters/stops and drops references |
| V1 cleanup throws exception | V2 still recorded as active; cleanup error tracked |
| Rollback after cutover | Never reuses CLOSED generation; state/schema compatible |
| Class loader isolation | No duplicate API identity, correct artifact/version, old loader GC-eligible |
| Async/stream/session | Lease covers entire lifecycle, not released prematurely |
| Rapid repeated upgrades | No buildup of RETIRING generations or resource leaks |

**Do not test solely with arbitrary `Thread.sleep`.** Use `CountDownLatch`, `CyclicBarrier`, `Phaser`, or barrier-synchronized test coordination to force exact interleavings; Section 7's example uses latches to confirm the old request entered the plugin before cutover.

## 14. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Unloading or closing V1 **before** validating V2 | V2 failure causes service outage | Prepare and validate candidate independently; V1 stays active |
| Updating `activePlugin`, then `activeConfig`, then `activeLoader` sequentially | Requests see data mixed from two versions | Publish one immutable generation/snapshot |
| `active = newPlugin` on a plain field without synchronization | Fails to guarantee proper visibility/publication | `AtomicReference`, `volatile`, or lock per JMM |
| Atomic switch followed immediately by closing V1 | In-flight requests still using V1 fail | Retire, block new leases, drain, then close |
| Reading `active` without holding a lease | Cleanup races with requests | Admission + lease tied to request/job |
| Counting active requests without a retire protocol | Race causes premature close or double close | Shared monitor/CAS state machine |
| Re-reading `active` across multiple processing steps | A single request mixes V1/V2 | Pin generation to the unit of work's scope |
| Creating V2 with the same old loader expecting classes to change | Java keeps using the old class definition | New loader/layer when a new version is needed |
| Calling `ServiceLoader.reload()` and assuming hot swap happened | Clears discovery cache without updating all references/layers | Build a new generation and publish atomically |
| Assigning pointer back to a CLOSED V1 to roll back | Calls into cleaned-up objects/resources | Keep rollback-ready with ownership or rebuild V1 as a new generation |
| Ignoring class identity and static caches | `ClassCastException`/metaspace leaks | Shared API parent, isolate plugin code, drop strong references |
| Candidate health test has real side effects | Unpublished version produces external mutations | Use harmless tests/probes or transactional/isolated sandboxes |
| Cleanup error causes publish method to report failure | Callers retry and may deploy repeatedly | Distinguish cutover commit from cleanup errors |
| Unbounded drain | V1 holds threads/sockets/metaspace forever | Deadlines, monitoring, cooperative cancellation, or process isolation |
| Treating a class loader as a security sandbox | Plugin still has JVM-level permissions | Trust validation, least privilege, process boundaries if untrusted |

## 15. Step-by-step implementation checklist

**Before prepare**

- [ ] Lock down `PluginApi` contract, version/capabilities, and host-owned namespaces.
- [ ] Define separate class loaders/module layers per generation when needed; ensure host/plugins share the exact interface.
- [ ] Load artifacts only from approved sources; verify checksums/signatures, compatibility, and dependency graph.
- [ ] Specify resource owners and scopes for executors, connections, listeners, caches, and files/class loaders.

**Prepare and validate**

- [ ] Build V2 completely without publishing; keep V1 serving.
- [ ] Execute readiness/contract checks and warm-up without mutating production data unexpectedly.
- [ ] Failed candidates must be closed/quarantined without altering the active pointer.
- [ ] Version/schema/state compatibility must be approved prior to cutover.

**Cutover**

- [ ] Enforce a per-plugin writer policy: lock or CAS with expected generation/version.
- [ ] Combine plugin instance + config + routing + loader reference into an immutable generation/snapshot.
- [ ] Publish a single `AtomicReference`/volatile pointer **after** validation finishes.
- [ ] Requests read and pin the generation, acquire a lease, and avoid re-reading `active` arbitrarily mid-workflow.
- [ ] Define exactly at which admission point a request is “accepted” to reason about concurrency accurately.

**Retire and post-verification**

- [ ] Stop admitting new work to V1, drain all requests/jobs/streams/sessions holding V1.
- [ ] Clean up V1 exactly once after leases drop to zero; never close class loaders/resources still in use.
- [ ] Have deadlines, logs, metrics, and recovery when drain/close fails.
- [ ] Rollback must never reuse a CLOSED generation; verify state/data compatibility.
- [ ] Verify threads, context class loaders, static caches, registrations, and class unloading after repeated upgrades.
- [ ] Test interleavings of prepare-fail, concurrent writers, cutover, last-release, shutdown, and rollback.

### Related Java 17 documentation

- [`AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [`AutoCloseable` and try-with-resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`URLClassLoader.close()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [`CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Conclusion:** a reliable plugin replacement mechanism must **build and validate the candidate first**, then **atomically publish an active reference** to the new generation, and only then **retire and drain** the old generation. An atomic switch ensures readers pick a consistent snapshot; leases and lifecycles ensure resources are not closed prematurely. Rollback, state migration, class loader unloading, and external side effects are separate responsibilities that must be designed explicitly rather than inferred from a single reference assignment.