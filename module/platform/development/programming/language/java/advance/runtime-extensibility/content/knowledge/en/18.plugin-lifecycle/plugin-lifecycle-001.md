# Designing Discovery, Verification, Initialization, Active, Stopping, and Failed States in the Java Plugin Lifecycle

## 1. Why Does a Plugin Need a State Model?

A plugin is an extension discovered and invoked by a host through a shared API contract. A plugin may be a class registered via Java SPI (`ServiceLoader`), a named module added to a `ModuleLayer`, or a JAR loaded by the host using a dedicated class loader. In all three cases, **finding a class** does not mean the plugin is **ready to receive requests**.

The system needs to answer accurately:

- Has the host **discovered** the plugin yet?
- Has the plugin been **verified** for identity, version, configuration, capabilities, and dependencies?
- Has the plugin **initialized** its resources and received configuration and services from the host?
- Is the plugin **active** and able to accept new commands?
- Is the plugin **stopping** or has it finished releasing resources?
- Why is the plugin in a **failed** state, and does cleanup/rollback need to be performed?

If only a `boolean loaded` flag is used, the host can easily run into bugs such as invoking a plugin before configuration completes, putting a broken instance into the registry, accepting new requests during shutdown, running `stop` twice, or retaining old threads/class loaders after an upgrade.

**Solution:** design a *finite-state machine* with **explicit states, valid state transitions, *guards*, trigger events, and cleanup actions**. This article focuses on the six core lifecycle phases: **discovery → verification → initialization → active → stopping**, with a **failed** branch that can arise from multiple phases.

> The state names in this article are a **host/plugin manager design**, not a standard enum automatically created by Java. `ServiceLoader`, `ModuleLayer`, and `ClassLoader` do not manage these business lifecycle states out of the box.

## 2. A Minimal Yet Complete State Model

The states can be named as follows:

| State | Meaning | Allowed to accept business requests? |
| --- | --- | --- |
| `DISCOVERED` — Discovered | The host has a discovered provider/metadata object; not all operating conditions have been verified yet | No |
| `VERIFIED` — Verified | Identity, contract, policy, configuration, and required dependencies have passed the appropriate checks | No |
| `INITIALIZED` — Initialized | The plugin has been given initial context/resources; not yet activated to handle requests | No |
| `ACTIVE` — Active | `start` and readiness checks succeeded; the plugin has been published to the dispatcher/registry | **Yes** |
| `STOPPING` — Stopping | The host blocks new requests, performs cleanup, unregisters listeners, and releases resources | No |
| `STOPPED` — Stopped | Cleanup completed according to contract; the instance can no longer be arbitrarily reused | No |
| `FAILED` — Failed | A transition/operation failed; the cause must be recorded and cleanup/recovery decided | No |

In production, you should add `DISCOVERING`, `VERIFYING`, `INITIALIZING`, `STARTING`, and **`QUIESCING`** (stopped accepting new requests, waiting for in-flight requests to finish) if these operations are long-running or asynchronous. The table above models **completed milestones** to keep the examples easy to follow.

### 2.1. State Diagram

```text
       [scan artifact / SPI / module finder]
                       │
                provider found
                       ▼
                  DISCOVERED
                       │ verify + policy checks
                       ▼
                   VERIFIED
                       │ initialize / inject context
                       ▼
                  INITIALIZED
                       │ start + readiness succeeds
                       ▼
                    ACTIVE ───────────► process request
                       │                       │
                       └──── stop requested ◄──┘
                               │
                               ▼
                            STOPPING
                               │ cleanup succeeds
                               ▼
                            STOPPED

  DISCOVERED / VERIFIED / INITIALIZED / ACTIVE
                   │ error occurred
                   ▼
                 FAILED
                   │ record cause, clean up allocated parts
                   ▼
                STOPPING
                   ├── cleanup succeeds ──► STOPPED
                   └── cleanup fails    ──► FAILED (terminal/needs intervention)
```

Here `FAILED` can be a **transient state to initiate cleanup** or a **terminal state if cleanup fails**. You must store **failure history** separately (`lastFailure`, `hadFailure`, timestamp, stage) because after cleanup succeeds, the object may transition to `STOPPED`; looking only at the final state would lose the information that the startup attempt just failed.

In systems using hot reload, you **should not** automatically transition `STOPPED → ACTIVE` on the same object if the implementation does not support restarting. The safe default is to **create a new instance** and re-run the verification/initialization pipeline.

### 2.2. Events and Transition Conditions

| Current State | Event | Success Condition | Next State | Action |
| --- | --- | --- | --- | --- |
| No instance yet | `provider discovered` | SPI/registry finds and instantiates the required provider | `DISCOVERED` | Attach ID, artifact, and provenance info |
| `DISCOVERED` | `verify` | ID, API/version, policy, metadata, and dependencies are valid | `VERIFIED` | Record verification result |
| `VERIFIED` | `initialize` | Context and initialization resources are successfully provided | `INITIALIZED` | Retain ownership/resource handles |
| `INITIALIZED` | `start` | Start and readiness complete | `ACTIVE` | Only now publish to accept requests |
| `ACTIVE` | `stop requested` | Stop accepting new requests; in-flight work is handled per policy | `STOPPING` | Quiesce and clean up |
| `STOPPING` | `cleanup completed` | Resources owned by the plugin have been released | `STOPPED` | Remove references/registry entry |
| Any non-terminal phase | `operation failed` | Verification, initialization, start, or critical invocation error occurs | `FAILED` | Preserve exception/cause, do not dispatch |
| `FAILED` | `cleanup requested` | Safe cleanup can be performed on partial state | `STOPPING` | Clean up opened resources |
| `STOPPING` | `cleanup failed` | Exception during stop | `FAILED` | Record cleanup error and escalate |

**Important:** Finding no provider is a **discovery outcome**, which can be reported as `NOT_FOUND` at the request/registry level **without creating a plugin instance marked `DISCOVERED`**. A provider that is declared but cannot be loaded or instantiated may cause `ServiceConfigurationError` or related JVM errors; that is not a normal `Optional.empty()`.

## 3. Invariants to Protect

A good state machine is not just state names; it has rules that always hold true:

1. **Only `ACTIVE` may accept new requests.** `DISCOVERED`/`VERIFIED`/`INITIALIZED` are not enough; `FAILED` and `STOPPING` must reject them.
2. **Do not publish prematurely.** The registry/dispatcher must only see the instance after `start` and readiness succeed; if `start` throws an error, the instance must not be published.
3. **Each step runs only in the allowed order.** No `DISCOVERED → ACTIVE` when verify and initialize are required.
4. **Errors must preserve the root cause.** Do not turn every error into “plugin not found”; keep the phase, stack/cause, and a meaningful error code.
5. **Cleanup is invoked on both success and failure.** Especially when `initialize`/`start` has opened partial resources and then throws.
6. **Cleanup must be safe when called multiple times by contract** (idempotent or guarded against duplicate calls in the manager). Plugins must not let repeated `stop` calls cause dangerous double-closes.
7. **`STOPPED` is the terminal state of an instance** in the default model. To run again, create a new instance rather than reusing an object with unpredictable state.
8. **State transition decisions must be atomic** when multiple threads concurrently request stop, run requests, or report errors. An enum field does not solve *race conditions* on its own without a synchronization/atomic protocol.
9. **Whoever owns a resource closes it.** The host closes executors/loaders created by the host; the plugin closes streams/listeners/connections belonging to the plugin; avoid both closing the same resource without a contract.
10. **Traceable history:** a final state of `STOPPED` must not erase the record of having been `FAILED`, startup attempt count, cleanup duration, and final outcome.

### 3.1. State vs. Event vs. Health

- **State (`State`):** which lifecycle milestone the plugin is currently at, e.g. `ACTIVE`.
- **Event (`Event`):** what happens to drive a transition, e.g. `START_SUCCEEDED`, `STOP_REQUESTED`.
- **Health/readiness:** the result of checking serving capability at a point in time. A plugin can be `ACTIVE` yet become *unhealthy* because a backend temporarily disconnects; the host must define a policy to remove it from routing or transition to failure/quiescing.
- **Desired state:** the target set by an operator, e.g. `ENABLED`/`DISABLED`; it is not equivalent to actual state. An operator may desire enabled while the plugin is `FAILED`.

If a single enum is used to mix all four concepts, the host will struggle to handle crashes, restarts, version replacements, or failing plugin dependencies.

## 4. Discovery: From Artifact to `DISCOVERED`

### 4.1. Discovery Can Occur at Multiple Layers

Plugins can be discovered via:

- **Java SPI**: `ServiceLoader.load(Extension.class)` discovers implementations registered in `META-INF/services` or declared via JPMS `provides`.
- **Artifact registry/manifest**: the host scans a JAR directory/module repository and reads metadata about plugin ID, version, dependencies, and capabilities.
- **JPMS**: `ModuleFinder` observes module artifacts; `Configuration.resolve(...)` resolves the module graph; `ModuleLayer` defines runtime modules.
- **Dedicated class loader**: the host configures a URL/class loader/module layer and then searches for classes matching the contract.

Those are technical mechanisms, not `ACTIVE` states. For example, `ServiceLoader.findFirst()` may return an `Optional<Extension>` containing a new instance, but **the constructor having run does not mean `start()` has been called**.

### 4.2. Beware of Code Running During Discovery

When `ServiceLoader` creates an instance, constructors or static initializers can run. Therefore, discovery is not necessarily completely “side-effect-free”. If you want to verify metadata before instantiating, the host can read the artifact/registry manifest or work with `ServiceLoader.Provider<S>` and `type()` before `get()`; even so, loading classes/metadata can still raise errors. **A class loader is not a sandbox**, so do not run untrusted plugins with the main process's privileges without a security boundary.

### 4.3. Distinguishing Absence from Provider Errors

```java
Optional<Extension> found =
    ServiceLoader.load(Extension.class).findFirst();

if (found.isEmpty()) {
    System.out.println("No extension provider");
}
```

This is an illustrative snippet requiring imports and the interface. `Optional.empty()` indicates no provider was found after normal traversal. A provider that is registered incorrectly or cannot be instantiated can cause `ServiceLoader` to throw `ServiceConfigurationError`. Do not catch all errors and return `Optional.empty()`; doing so hides misconfiguration.

If multiple providers exist, `findFirst()` does not guarantee selecting the intended one. The host must select by ID/capability/version/priority, verify policy, and only then instantiate/activate the plugin. Provider selection also **does not automatically manage dependencies or lifecycle**.

## 5. Verification: `DISCOVERED → VERIFIED`

The **verify** step must validate the conditions allowing the plugin to **attempt initialization**, not merely check that a class implements the right interface.

### 5.1. What Should Be Checked

| Category | Questions |
| --- | --- |
| Identity | Is the plugin ID valid and unique? Are the artifact name and source clear? |
| Integrity/provenance | Does the JAR come from a trusted source, with checksum/signature verified if required by policy? |
| Contract/API | Does the plugin use the right interface/binary API, minimum host version, and class identity? |
| Version | Do the plugin/dependency versions satisfy the compatibility matrix? |
| Dependencies | Are all required modules/JARs, host services, and dependent plugins in the required state? |
| Configuration | Are required keys, secret handles, namespace paths, and schemas valid? |
| Capability/permission | Is the plugin enabled in the current environment? Are requested features granted? |
| Policy | Tenant limits, CPU/memory limits, network/filesystem permissions if supported by the system? |

You cannot assume a single `plugin.verify()` call will check **all** of the above on its own. They require coordination between the plugin manager, metadata, and the host's security/configuration services.

### 5.2. Verify Before Granting Privileges

If verification relies on metadata inside the JAR, check whatever can be checked **before instantiating/executing code**. Data declared by the plugin itself may be incomplete or untrustworthy if the plugin comes from an unknown source. Separate clearly:

1. **Host pre-instantiation checks**: artifact identity, signature, manifest, compatibility, dependency graph.
2. **Plugin post-instantiation validation**: checking configuration or required capabilities after receiving a minimal context.

Do not use a class loader as a substitute for an OS sandbox against malicious code. A JAR permitted to execute code in the JVM does not automatically become safe once it passes module resolution.

### 5.3. What If Verification Fails?

If a required dependency is missing, an ID conflicts, the API is incompatible, or configuration is invalid, the manager:

- Records `FAILED` and the cause in the verify phase (or rejects the artifact before creating a plugin instance).
- Does not call `initialize`/`start`, and does not put the plugin into the request-receiving registry.
- Cleans up any resources actually opened during discovery/validation; do not assume nothing needs cleanup.
- Surfaces actionable error information: plugin ID, version, missing dependency, artifact source, stage.

## 6. Initialization: `VERIFIED → INITIALIZED`, Then Activating `ACTIVE`

### 6.1. Separating Constructor, Initialize, and Start

There are at least three milestones that are very easy to conflate:

- **Constructor/provider creation:** the JVM creates the object; keep it lightweight, without opening connections or spawning heavy threads.
- **`initialize(context)`:** the host passes configuration, logger, repositories, service facades, and resource handles; the plugin prepares its state.
- **`start()`:** the plugin registers listeners or starts required components; completes readiness; from here the manager allows accepting requests.

At the moment `initialize` completes, the state is `INITIALIZED`, not yet `ACTIVE`. The host may invoke an additional readiness check during `start` or split out a `STARTING` phase if needed.

### 6.2. Designing a Plugin Context

```java
public record PluginContext(
    java.util.logging.Logger logger,
    java.nio.file.Path configDirectory,
    java.time.Clock clock) {
}
```

This is an **API illustration**; visibility/ownership may need adjustment in your project. Instead of letting plugins guess the working directory or access global singletons, the host supplies dependencies through the context. The context should not grant the plugin more privileges than needed. Secrets can be supplied via a secret-management interface; never put tokens into logs or error messages.

### 6.3. Partial Initialization and Rollback

A realistic sequence:

```text
initialize
  ├── open connection pool  [OK]
  ├── create executor       [OK]
  ├── register listener     [FAILED]
  └── return                [not reached]
```

The plugin **failed before reaching `INITIALIZED`**, yet the first two resources still exist. The manager must invoke cleanup via a contract that is safe under partial initialization. Implementations should also use `try/finally` or `try-with-resources` inside `initialize` to immediately clean up already-created resources before throwing.

The interface should explicitly specify: `stop()` (or `close()`) **must be safe** if `initialize()` has not been called, did not finish successfully, `start()` failed midway, or stop has already run before. If that cannot be guaranteed, the plugin manager must accurately track resource handles and invoke cleanup based on allocation checkpoints.

## 7. Active: Only `ACTIVE` Accepts Requests

When the plugin is ready:

1. `start()` completes and the readiness check succeeds.
2. The manager transitions the state to `ACTIVE`.
3. The plugin is placed into the dispatch registry (must be coordinated atomically with the state).
4. New requests can be dispatched to the implementation.

Do not publish the plugin while it is still `INITIALIZED` or `STARTING`. Do not use `if (plugin != null)` to decide whether to run, because **an instance existing does not mean it is active**.

### 7.1. Request Handling Errors: Do All Errors Make the Plugin FAILED?

Not necessarily. Distinguish:

- **Recoverable business errors:** invalid input, unsupported request, single-request timeout. You can return an error for that request and keep the plugin `ACTIVE`.
- **Health/system failures:** broken connection pool, dead worker thread, invalid context, corrupted internal state. The manager may transition to `FAILED` or `QUIESCING` depending on policy and health checks.
- **Fatal JVM errors:** such as `OutOfMemoryError` or certain `LinkageError`s; do not catch `Throwable` and pretend the plugin is still operating normally.

The plugin manager needs an explicit **error policy**: which errors affect only a single request, which require a circuit breaker, and which force stopping the plugin.

### 7.2. Concurrency and In-Flight Requests

In production, thread A often handles requests while thread B receives a stop command:

```text
Thread A:  [check ACTIVE] ───► [processing] ───► [return result]
Thread B:                      [STOP REQUESTED] ─► [clean up resources]
```

If B closes a connection while A is still using it, the request can fail or corrupt data. The solution is a **quiescing** protocol:

```text
ACTIVE
   │ lock new-request gate (atomic)
   ▼
QUIESCING ── wait for inflight=0 / deadline ──► STOPPING
                                                  │
                                                  ▼
                                               STOPPED
```

The dispatcher should issue a *lease/in-flight token* only while the state is still `ACTIVE`, incrementing the in-flight request counter **within the same critical section** as the state check. When a request finishes, decrement the counter and wake up shutdown. Once the gate is closed, no new request receives a lease, and the host waits for the in-flight count to reach 0 or hit a policy deadline. Only then are resources used by requests cleaned up.

**It is not sufficient** to use two separate operations `if (state == ACTIVE)` followed by `inFlight++`, because `STOPPING` can interleave in between. A `volatile State` makes the new value visible, but **does not turn two operations into an atomic transition**.

## 8. Stopping: `ACTIVE/FAILED → STOPPING → STOPPED`

A sound shutdown sequence includes these steps:

1. Mark `QUIESCING` or `STOPPING` and withdraw the instance from the new-request dispatch list.
2. Wait for/cancel remaining in-flight requests under a controlled deadline.
3. Unregister listeners, scheduler tasks, callbacks, metric hooks, event subscriptions, and objects registered with the host.
4. Close connections, streams, file watchers, executors/threads, temporary files, and handles owned by the plugin.
5. Sever references from registries, caches, `ThreadLocal`/TCCL if created by the host/plugin.
6. If the host created a `URLClassLoader`, consider calling `close()` once no longer in use. **Do not** assume `close()` stops threads automatically or guarantees class unloading.
7. Record cleanup outcome, final state, and failure cause if one ever occurred.

If `stop()` is called repeatedly, there are two complementary safeguards:

- **Idempotent plugin:** repeated `stop()` is safe and does not send double-deletes or close resources it does not own.
- **Manager once-only guard:** ensures the same lifecycle instance starts only once and cleanup is scheduled only once. In asynchronous systems, the guard should use atomic compare-and-set or an appropriate lock.

### 8.1. Stopping in Dependency Order

Suppose `ReportingPlugin` needs `StoragePlugin` to flush data. At startup:

```text
Storage → Reporting
```

At shutdown, reverse the order:

```text
Reporting → Storage
```

Although `ServiceLoader` finds both providers, it does not resolve this ordering. The plugin manager needs a dependency graph. If Storage stops before Reporting, the flush step in Reporting can fail or lose data.

### 8.2. Closing a Class Loader Is Not Stopping a Plugin

Replacing a JAR and calling `ServiceLoader.reload()` only makes `ServiceLoader` forget its provider cache; it **does not** replace bytecode already loaded in the current loader, does not call `stop`, and does not close resources automatically. Hot reload requires a new instance/loader, compatibility verification, startup, traffic switching, quiescing the old instance, stopping, removing callbacks/threads/caches, and then cleaning up the old loader.

Layers/class loaders only help with code loading architecture; they **do not** automatically manage business lifecycle.

## 9. Failure: Designing `FAILED` Without Hiding the Cause

`FAILED` needs **accompanying information**, not just an enum label.

A record might include:

```text
pluginId: echo
pluginVersion: 1.4.0
phase: STARTING
state: FAILED
errorCode: START_FAILED
message: Backend unavailable
timestamp: 2026-11-01T10:00:00Z
retryable: false  (per host policy)
cleanupStatus: PENDING
```

This is **illustrative data** only, not log output from the demo below. Once cleanup completes, you may see `state=STOPPED` while `lastFailure` and `cleanupStatus=COMPLETED` remain stored so operators know the run failed.

### 9.1. Failure and Response Table

| Phase | Example Failure | Recommended Response |
| --- | --- | --- |
| Discovery | No provider found | Return “not found” at the host level; optionally use a fallback per policy |
| Discovery | Invalid SPI descriptor, provider cannot be instantiated | Report `ServiceConfigurationError`/classload failure; do not treat as “absent” |
| Verify | Wrong API version, missing dependency, duplicate ID | Mark failed or reject artifact; do not initialize |
| Initialize | Corrupted config file, partial connection creation | Do not publish; clean up opened parts, preserve cause |
| Start | Listener registration failed, readiness timeout | `FAILED`, roll back/stop, do not transition to `ACTIVE` |
| Active | Invalid input | Return per-request error; may remain `ACTIVE` |
| Active | Corrupted internal state or prolonged dependency loss | Quiesce/`FAILED` per policy; stop dispatching new requests |
| Stop | Resource close throws | Continue cleaning up other resources where possible; log cleanup error; escalate |
| Hot reload | New version fails to start | Keep old version active if not switched yet; clean up new version |

### 9.2. Should You Retry From `FAILED`?

Do not automatically call `start()` again on the old object when you do not know how many resources it already initialized. A safe default policy:

```text
FAILED instance
   → best-effort cleanup
   → STOPPED (keep failure history)
   → wait per backoff/policy
   → DISCOVER NEW instance
   → VERIFY → INITIALIZE → START
```

If a plugin supports restarting the same instance, that must be explicitly specified by the API contract and tested across every failure/resource path. All retries must be bounded in count, use backoff, and avoid infinite loops when a dependency remains broken.

## 10. Runnable Java 17+ Example: Explicit State Machine with SPI

The example includes:

- **`Extension`**: shared contract and a record containing host-supplied options.
- **`EchoExtension`**: provider registered via Java SPI; allows simulating `start()` success or failure.
- **`Main`**: host using `ServiceLoader.findFirst()` to discover, then orchestrating `VERIFIED → INITIALIZED → ACTIVE`, and whether succeeding or failing, cleaning up via `STOPPING → STOPPED`.

The example intentionally uses **one thread, one provider, one run** so state transitions and stdout are completely deterministic. It does not simulate production concurrency/quiescing and is not a sandbox.

### 10.1. Directory Structure

```text
demo/
├── src/
│   └── demo/
│       ├── api/
│       │   └── Extension.java
│       ├── impl/
│       │   └── EchoExtension.java
│       └── host/
│           └── Main.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.api.Extension
```

### 10.2. Contract: `src/demo/api/Extension.java`

```java
package demo.api;

public interface Extension {
    record Options(boolean failStart) {}

    String id();
    void verify() throws Exception;
    void initialize(Options options) throws Exception;
    void start() throws Exception;
    String invoke(String value) throws Exception;
    void stop() throws Exception;
}
```

**Contract semantics:**

- `verify` checks conditions the provider can self-verify; the host must still perform external policy checks.
- `initialize` supplies options/context and prepares resources.
- `start` activates the plugin; only on success does the host transition to `ACTIVE`.
- `invoke` may only be called when ACTIVE.
- `stop` is responsible for cleanup and **must be safe** even when `initialize` or `start` has not completed. The demo allows repeated calls.

In the example, `Options.failStart` is a failure-testing flag, not a complete configuration architecture. In real applications, replace it with a typed `PluginContext`, logger, config, host services, and permission-restricting policies.

### 10.3. Implementation: `src/demo/impl/EchoExtension.java`

```java
package demo.impl;

import demo.api.Extension;
import java.util.Objects;

public final class EchoExtension implements Extension {
    private Options options;
    private boolean active;

    public EchoExtension() {
    }

    @Override
    public String id() {
        return "echo";
    }

    @Override
    public void verify() {
        if (!"echo".equals(id())) {
            throw new IllegalStateException("invalid plugin id");
        }
    }

    @Override
    public void initialize(Options options) {
        this.options = Objects.requireNonNull(options);
    }

    @Override
    public void start() {
        if (options == null) {
            throw new IllegalStateException("not initialized");
        }
        if (options.failStart()) {
            throw new IllegalStateException("start refused");
        }
        active = true;
    }

    @Override
    public String invoke(String value) {
        if (!active) {
            throw new IllegalStateException("plugin not active");
        }
        return "ECHO: " + value;
    }

    @Override
    public void stop() {
        active = false;
        options = null;
        System.out.println("[plugin] cleanup called");
    }
}
```

`stop()` only resets state in the demo, but is written so it **does not require `start()` to have succeeded**. This allows the host to clean up after a `start refused` situation. In a real plugin, `stop()` must close the exact resources that were allocated and avoid double-close.

The `active` flag in the implementation is only an illustrative guard, **not thread-safe synchronization**. The manager owns the authoritative lifecycle state; the plugin can guard its own methods as a second line of defense.

### 10.4. Host/manager: `src/demo/host/Main.java`

```java
package demo.host;

import demo.api.Extension;
import java.util.Objects;
import java.util.Optional;
import java.util.ServiceLoader;

public final class Main {
    enum State {
        DISCOVERED,
        VERIFIED,
        INITIALIZED,
        ACTIVE,
        STOPPING,
        STOPPED,
        FAILED
    }

    static final class Lifecycle {
        private final Extension plugin;
        private State state = State.DISCOVERED;
        private boolean hadFailure;
        private boolean cleanupAttempted;
        private boolean runCalled;

        Lifecycle(Extension plugin) {
            this.plugin = Objects.requireNonNull(plugin);
            System.out.println("[host] state: " + state);
        }

        void run(boolean failStart) {
            if (runCalled) {
                throw new IllegalStateException(
                    "Lifecycle already used");
            }
            runCalled = true;

            try {
                // 1. VERIFIED: host policy + plugin-side checks.
                if (!plugin.id().matches("[a-z][a-z0-9-]*")) {
                    throw new IllegalArgumentException(
                        "invalid plugin ID");
                }
                plugin.verify();
                moveTo(State.VERIFIED);

                // 2. INITIALIZED: inject the test context.
                plugin.initialize(new Extension.Options(failStart));
                moveTo(State.INITIALIZED);

                // 3. ACTIVE only after start completes.
                plugin.start();
                moveTo(State.ACTIVE);

                System.out.println("[host] result: "
                    + plugin.invoke("Java"));
            } catch (Exception error) {
                hadFailure = true;
                moveTo(State.FAILED);
                System.out.println(
                    "[host] error: " + error.getMessage());
            } finally {
                shutdown();
                System.out.println(
                    "[host] had failure: " + hadFailure);
            }
        }

        private void shutdown() {
            if (cleanupAttempted) {
                return;
            }
            cleanupAttempted = true;

            moveTo(State.STOPPING);
            try {
                // Contract: stop is safe even after partial start.
                plugin.stop();
                moveTo(State.STOPPED);
            } catch (Exception error) {
                hadFailure = true;
                moveTo(State.FAILED);
                System.out.println(
                    "[host] cleanup error: " + error.getMessage());
            }
        }

        private void moveTo(State next) {
            boolean allowed = switch (state) {
                case DISCOVERED ->
                    next == State.VERIFIED
                    || next == State.FAILED
                    || next == State.STOPPING;
                case VERIFIED ->
                    next == State.INITIALIZED
                    || next == State.FAILED
                    || next == State.STOPPING;
                case INITIALIZED ->
                    next == State.ACTIVE
                    || next == State.FAILED
                    || next == State.STOPPING;
                case ACTIVE ->
                    next == State.FAILED
                    || next == State.STOPPING;
                case FAILED -> next == State.STOPPING;
                case STOPPING ->
                    next == State.STOPPED
                    || next == State.FAILED;
                case STOPPED -> false;
            };

            if (!allowed) {
                throw new IllegalStateException(
                    "Illegal transition: " + state + " -> " + next);
            }
            state = next;
            System.out.println("[host] state: " + state);
        }
    }

    public static void main(String[] args) {
        if (args.length > 1
                || (args.length == 1
                    && !args[0].equals("fail-start"))) {
            throw new IllegalArgumentException(
                "Usage: Main [fail-start]");
        }

        // SPI discovery. Without a provider, no Lifecycle is created.
        Optional<Extension> found =
            ServiceLoader.load(Extension.class).findFirst();

        if (found.isEmpty()) {
            System.out.println("[host] no provider discovered");
            return;
        }

        Lifecycle manager = new Lifecycle(found.orElseThrow());
        manager.run(args.length == 1);
    }
}
```

**Meaning of the guards in the host:**

- `Lifecycle` starts at `DISCOVERED` **after** SPI returns a valid instance. If there is no provider, no `Lifecycle` is created.
- `moveTo` validates every edge of the state graph. Illegal transitions throw `IllegalStateException` to catch programming mistakes.
- `runCalled` prevents accidental reuse of the same manager.
- `ACTIVE` is recorded only after `plugin.start()` returns successfully; `invoke` comes after that.
- `catch (Exception)` records failure and transitions to `FAILED`; `finally` calls `shutdown` even if `verify`, `initialize`, `start`, or `invoke` throws an exception.
- `cleanupAttempted` prevents calling cleanup multiple times from the host; the `stop()` implementation still needs to support safe cleanup after partial initialization.
- `hadFailure` preserves the failure history **even when the final state is `STOPPED`**.

This is a **synchronous, single-threaded** model. If operations occur across multiple threads, `runCalled`, `state`, `cleanupAttempted`, and `hadFailure` must be protected with locks/CAS, and shutdown must account for in-flight requests. Do not copy the demo code and treat it as a thread-safe production plugin manager.

Another limitation: severe errors belonging to `Error` (such as JVM/linkage errors) are not caught by `catch (Exception)`; the program does not pretend it can recover from every failure. `ServiceConfigurationError` during discovery also occurs **before** creating the manager and must be handled at the appropriate host boundary.

### 10.5. SPI Descriptor

**`resources/META-INF/services/demo.api.Extension`**

```text
demo.impl.EchoExtension
```

With classpath SPI, the filename must be the fully qualified name of the interface, and the content is the implementation class name. The descriptor must be packaged **inside the provider JAR** directly under `META-INF/services`. The host depends only on `demo.api.Extension` and does not import `EchoExtension`.

### 10.6. Compiling/Packaging the JAR and Running on Windows PowerShell

From the `demo` directory, **JDK 17+** is required:

```powershell
New-Item -ItemType Directory -Force build/host, build/plugin | Out-Null

# Host contains the contract and Lifecycle manager, without the provider.
javac -encoding UTF-8 -d build/host src/demo/api/Extension.java src/demo/host/Main.java

# Provider is compiled separately, referencing the same host API.
javac -encoding UTF-8 -cp build/host -d build/plugin src/demo/impl/EchoExtension.java

# Package the SPI descriptor into the plugin JAR.
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/demo.api.Extension build/plugin/META-INF/services/demo.api.Extension
jar --create --file build/echo-plugin.jar -C build/plugin .

# Case WITHOUT a provider on the runtime classpath.
java -cp build/host demo.host.Main

# Case WITH a provider and start SUCCEEDS.
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main

# Case WITH a provider but start FAILS.
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main fail-start
```

On Windows, `;` separates classpath entries. On Linux/macOS, change it to `:`, e.g. `java -cp 'build/host:build/echo-plugin.jar' demo.host.Main`, and replace the PowerShell directory-creation/copy commands with `mkdir -p` and `cp` respectively.

### 10.7. Exact Run Output: No Provider

Command:

```powershell
java -cp build/host demo.host.Main
```

Stdout:

```text
[host] no provider discovered
```

This is a **discovery outcome with no candidates**. Without an instance, there is no `DISCOVERED`, `FAILED`, or `STOPPED` for a specific plugin. The host can choose to log a notice, disable the feature, or fall back per policy.

### 10.8. Exact Run Output: Success Flow

Command:

```powershell
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main
```

Stdout:

```text
[host] state: DISCOVERED
[host] state: VERIFIED
[host] state: INITIALIZED
[host] state: ACTIVE
[host] result: ECHO: Java
[host] state: STOPPING
[plugin] cleanup called
[host] state: STOPPED
[host] had failure: false
```

Two things are easy to verify:

1. `result: ECHO: Java` appears only **after** the `ACTIVE` state has been recorded.
2. `cleanup called` appears **between `STOPPING` and `STOPPED`**; the host does not declare itself stopped before `plugin.stop()` finishes.

### 10.9. Exact Run Output: Start Failure and Cleanup

Command:

```powershell
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main fail-start
```

Stdout:

```text
[host] state: DISCOVERED
[host] state: VERIFIED
[host] state: INITIALIZED
[host] state: FAILED
[host] error: start refused
[host] state: STOPPING
[plugin] cleanup called
[host] state: STOPPED
[host] had failure: true
```

The failed run **has no `ACTIVE`**, because `plugin.start()` threw `IllegalStateException("start refused")`. Even so, `finally` still cleans up resources. The final state is `STOPPED`, but `had failure: true` reminds us that the plugin was never ready to receive requests during this run.

**This is the difference between failure and stopping:** `FAILED` records the fault; `STOPPING/STOPPED` records cleanup progress. Neither piece of information should be lost.

### 10.10. What the Example Does Not Assume

- Does not implement hot reload or unload loaded classes from the JVM.
- Does not treat `ServiceLoader` as a dependency resolver or plugin lifecycle manager.
- Does not guarantee safety when multiple threads concurrently call invoke/stop.
- Does not handle all errors outside `Exception` or guarantee JVM recovery after system errors.
- Does not detect untrusted plugins via signature/OS privilege policies; the demo verify step only checks the ID and a sample method.
- Does not automatically retry on the same instance after `FAILED`.

Each of the limitations above requires its own policy and testing in a real application.

## 11. Advanced Design for Production: Event-Driven State Machine

When a plugin has an asynchronous startup step, distinguish **transition request commands** from **completion events**:

```text
DISCOVERED
   │ VERIFY_REQUESTED
   ▼
VERIFYING
   ├── VERIFY_SUCCEEDED → VERIFIED
   └── VERIFY_FAILED    → FAILED

VERIFIED
   │ INITIALIZE_REQUESTED
   ▼
INITIALIZING
   ├── INITIALIZE_SUCCEEDED → INITIALIZED
   └── INITIALIZE_FAILED    → FAILED

INITIALIZED
   │ START_REQUESTED
   ▼
STARTING
   ├── READY  → ACTIVE
   └── ERROR  → FAILED

ACTIVE
   │ STOP_REQUESTED
   ▼
QUIESCING ── inflight=0 or deadline ──► STOPPING
                                          ├── STOP_OK → STOPPED
                                          └── STOP_ERR → FAILED
```

If `start` returns a `CompletionStage`, do not switch `STARTING → ACTIVE` as soon as the future is received; only switch when it completes successfully and the readiness check passes. If the future fails or times out, transition to `FAILED`/cleanup and ignore late callbacks matching the canceled generation.

### 11.1. Generation Numbers to Avoid Stale Callbacks

Suppose plugin version 1 is stopping while version 2 starts. An asynchronous callback from version 1 arriving after version 2 is already `ACTIVE` could erroneously update the registry. Tie transitions to `pluginId + generation/version + instanceId`, and accept a callback only if it still matches the **current generation**.

For example, state must be tied to a **specific instance**, not stored solely in a `Map<String, State>` without checking the instance ID when multiple versions are enabled in parallel.

### 11.2. Atomic Transition and Publish

A production protocol typically includes:

1. Locking/atomic CAS to transition state if the current state matches expectations.
2. Recording the event and cause with a sequence number/timestamp.
3. Publishing/unpublishing in the registry synchronously with the state transition.
4. Denying leases to new requests once quiescing starts.
5. Keeping cleanup callbacks once-only per instance and checking generation.

Example guard in **pseudocode** (not complete Java code):

```text
acquireRequestLease():
  lock
    require state == ACTIVE
    inFlight += 1
  unlock
  return lease whose close() decrements inFlight

beginStop():
  lock
    if state == ACTIVE:
      state = QUIESCING
      unpublish from dispatcher
    else:
      follow transition policy
  unlock
  wait for inFlight == 0 or deadline
  state = STOPPING
  cleanup()
```

This is an algorithmic sketch. In a real implementation, do not hold locks while waiting on I/O or calling plugin code that may block/re-enter the host; you must account for deadlocks, timeouts, and interruption policies. After a timeout, plugin code may still be running, so absolute safety cannot be assumed when closing shared resources; the application needs an appropriate isolation/cancellation strategy.

### 11.3. Persistence and Crash Recovery

If the host restarts mid-`INITIALIZING` or mid-`STOPPING`, in-memory state is lost. Distinguish:

- **Runtime state**: the state of a specific object inside the living JVM.
- **Durable desired state**: which plugins the operator asked to enable/disable, along with stored version and policy.
- **Recovery state**: traces of the previous startup attempt if the system needs auditing/compensation.

After a restart, you cannot simply restore an `ACTIVE` object from a database; the JVM must create a new instance, resolve dependencies, verify, initialize, start, and re-run readiness checks. For plugins with external side effects, idempotency keys/compensation are needed to avoid executing tasks twice.

## 12. Testing and Observability Strategy for Lifecycle

### 12.1. State-Based Test Matrix

| Test | Outcome to Verify |
| --- | --- |
| No provider | Host reports absence; does not create a state manager for a non-existent instance |
| Valid provider | `DISCOVERED → VERIFIED → INITIALIZED → ACTIVE → STOPPING → STOPPED` |
| Verify fails | Does not call initialize/start, cleans up per contract, preserves cause |
| Initialize fails midway | Not ACTIVE; closes already-allocated resources; no leaks |
| Start fails | `FAILED`, no dispatch; cleanup completes |
| Invoke while `INITIALIZED` | Rejected |
| Invoke while `ACTIVE` | Processed normally |
| Stop with in-flight requests | Accepts no new requests, waits/cancels per policy |
| Stop called twice | No double-close/double-published events |
| Stop throws exception | Records cleanup failure; does not lose initial failure cause |
| Retry after FAILED | Creates new instance/generation per policy, does not resurrect broken instance |
| Two plugins with dependency | Start in topological order, stop in reverse order |
| Hot reload new version fails | If not switched yet, old version keeps working; new version cleans up |
| Host restart | Does not “restore ACTIVE” solely from old state; re-runs pipeline |

You can use a fake plugin accepting `failOnVerify`, `failOnInitialize`, `failOnStart`, `failOnInvoke`, and `failOnStop` flags to test every edge; count start/stop invocations, keep a list of transitions, and assert the exact order. In concurrency tests, use latches/barriers instead of arbitrary sleeps to reproduce races between requests and stop.

### 12.2. Metrics and Diagnostics

Fields worth recording:

- Plugin ID, implementation/version, instance/generation, loader/module layer name if applicable.
- Previous/next state, event, transition reason, timestamp, and correlation ID.
- Duration of verify, initialize, start, quiesce, and stop.
- In-flight request count, timeouts, exceptions, retry count, and cleanup outcome.
- Readiness/health independent of lifecycle state.
- Last failure cause/code and resource cleanup outcome even when ending in `STOPPED`.

Logs should avoid exposing passwords, tokens, or sensitive data in config/exceptions. If plugins come from third parties, the host should normalize published information rather than letting plugins arbitrarily decide what messages are safe.

## 13. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using only `loaded=true` | Impossible to tell whether validating, initializing, or ACTIVE | Use a state enum + transition policy |
| Setting ACTIVE as soon as `ServiceLoader.findFirst()` returns a provider | Leads to invoking requests before start/readiness | Publish only after start succeeds |
| `DISCOVERED → ACTIVE` skipping verify/init | Loses control over config/dependencies | Enforce required order with guards |
| No FAILED state | Errors are hidden under “plugin stopped” or “not found” | Preserve cause, stage, and error code |
| Catching all `Throwable` and falling back | Masks critical JVM/linkage errors | Classify errors and handle deliberately |
| Skipping cleanup when start fails | Leaks threads/connections/listeners | Clean up after partial initialization |
| STOPPED erases failure history | Hard to investigate why the plugin is not running | Keep lastFailure/hadFailure |
| Calling stop multiple times from multiple threads | Double close, races, deadlocks | Idempotent contract + once-only atomic guard |
| Stop closes resources while old requests are using them | Request failures, data loss | Quiesce/in-flight leases, deadlines |
| Retrying the same object without a contract | Leftover state/resources from previous attempt | Create a new instance, backoff, and generation |
| Closing `URLClassLoader` and assuming the plugin stopped | Threads/callbacks/classes may still remain | Stop/clean up/clear references first |
| Relying on SPI order to manage dependencies | Dependent plugin starts before its dependency | Resolve graph, topological start / reverse stop |
| Assuming class loaders isolate security privileges | Plugin still has process-level privileges | Process isolation/OS policy for untrusted code |

## 14. Plugin Manager Design Checklist

- [ ] Distinguish discovery result “no provider” from provider configuration/loading errors.
- [ ] Have at least `DISCOVERED`, `VERIFIED`, `INITIALIZED`, `ACTIVE`, `STOPPING`, `STOPPED`, `FAILED`.
- [ ] Transition edges have guards; no shortcuts, no request invocation outside `ACTIVE`.
- [ ] Verify identity, API/version, dependencies, configuration, capabilities, and policy before activation.
- [ ] Lightweight constructor; initialize and start have clear boundaries and support rollback after partial errors.
- [ ] Registry publishes the instance **only after** start/readiness; unpublishes before cleanup.
- [ ] Cleanup has a contract handling uninitialized or failed-start cases; prevents double cleanup.
- [ ] Separate recoverable request errors from system errors requiring `FAILED`.
- [ ] Handle quiescing and in-flight requests safely under multithreading.
- [ ] On FAILED, store phase, cause, cleanup outcome, and history, even after STOPPED.
- [ ] Stop in reverse dependency order; check for class loader/callback/thread leaks during hot reload.
- [ ] Retries have a policy, backoff, and new instance/generation; avoid resurrecting broken objects.
- [ ] Have tests for every transition, illegal transition, partial failure, concurrency, timeout, and restart.

**Conclusion:** A **discovered** plugin is not yet a **verified** plugin; an **initialized** plugin is not yet an **active** plugin; a **failed** plugin may still need to go through **stopping** to clean up resources. Only when the state machine has clear guards, history, ownership, and cleanup can the host operate plugins safely, especially in systems with multiple providers, dependencies, and hot reload.

**Official Java SE 17 Documentation:** [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html), [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [`URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).
