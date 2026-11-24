# Initializing in Dependency Order and Rolling Back on Partial Success

## 1. The Plugin Lifecycle Problem

In a host that supports multiple plugins, one plugin may depend on services provided by another. For example, `storage` creates a repository, `cache` requires `storage`, and `report` requires both `cache` and `storage`. If the host calls `start()` in arbitrary order, `report` may start before its dependencies are ready. Conversely, if the third plugin fails after the first two have opened files, sockets, or threads, the host must **roll back the parts that initialized successfully**, avoiding a half-initialized state.

A proper design must solve three distinct problems:

1. **Dependency graph:** which plugins must run before which others?
2. **Lifecycle transaction:** which steps have succeeded, and in what order must they be rolled back?
3. **Failure semantics:** when initialization or cleanup fails, how does the host report the cause and keep state consistent?

There is no automatic distributed transaction for plugins: `start()` can produce irreversible side effects, so rollback is a **compensating action** based on the `stop()`/`close()` contract and the actual resources involved.

## 2. Dependency Model: Directed Acyclic Graph

Treat each plugin as a vertex. With the relation `report -> cache`, meaning **report depends on cache**, `cache` must complete before `report` starts. A valid ordering for the example:

```text
storage  ---> cache  ---> report
    \___________________^
```

Here the arrows mean “must initialize before”: `storage → cache`, `storage → report`, `cache → report`.

### 2.1. Topological Sorting

For a DAG (Directed Acyclic Graph), topological sorting returns an order where every dependency precedes its dependent plugins. You can use DFS with `WHITE/GRAY/BLACK` coloring or Kahn's algorithm with in-degrees.

Conditions to check **before calling `start()`**:

- Unique plugin IDs with no registry duplicates.
- All required dependencies exist with compatible versions/contracts.
- No cycles (`A` requires `B` and `B` requires `A`, including longer cycles).
- Clear policy for optional plugins: is a missing optional dependency allowed to be skipped?
- Deterministic ordering among independent plugins when stable results are needed (e.g., sorting by ID).

If the graph contains a cycle, no topological order exists; the host should fail before creating any resources. Do not attempt to “try starting anyway” and deal with circular dependency errors later.

### 2.2. Enforcing Version and Capability Checks

Checking only the dependency ID is rarely sufficient. A provider may require `storage-api` version 2 or a specific capability. The host must verify requirements at the resolution stage (before activation) and provide **a single consistent API contract** across class loaders; otherwise, a plugin may finish starting yet fail on its first service call.

## 3. Lifecycle State Machine

A useful model:

```text
DISCOVERED -> RESOLVED -> STARTING -> ACTIVE -> STOPPING -> STOPPED
                              |                     |
                              v                     v
                            FAILED              STOP_FAILED
```

`DISCOVERED` means metadata/JAR is visible; `RESOLVED` means dependencies match; `STARTING` allows initialization; `ACTIVE` means start succeeded; `STOPPING`/`STOPPED` covers release. State names vary by system, but the host must distinguish **starting initialization** from **fully active**.

**Important:** if `start()` creates some resources and then throws an exception, that plugin has not been recorded as ACTIVE. Even so, it still owns partial resources and needs cleanup. Therefore `start()` should either clean up all resources it allocated before throwing, or the host needs an `abortStart()`/`close()` mechanism that is safe for partially initialized objects.

## 4. Rollback Principles

Suppose the activation order is:

```text
start storage : OK
start cache   : OK
start report  : FAIL
```

The host must stop the already-active plugins in **reverse** order:

```text
stop cache
stop storage
```

You should not call `stop storage` before `stop cache`, because `cache` might still need `storage` to flush or persist state during shutdown. A stack of plugins that started successfully is the natural structure for LIFO rollback.

To preserve the original cause when cleanup also fails:

- Keep the exception thrown by `start report` as the **primary failure**.
- Attach cleanup errors via `Throwable.addSuppressed(...)` or report them in an equivalent structure.
- Continue cleaning up the remaining plugins even if one `stop()` fails; never abort rollback on the first cleanup error.
- Only mark `STOPPED` when cleanup reaches the desired state; do not claim rollback “completely succeeded” when resources may still be running.

## 5. Standalone Runnable Java 17+ Example: Topo Sort + LIFO Rollback

The example below uses a simple `Plugin` interface with `List<String>` dependency metadata and no framework. The `report` plugin is intentionally made to fail to demonstrate rollback in action.

Create the file **`PluginLifecycleDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class PluginLifecycleDemo {
    interface Plugin {
        String id();
        List<String> dependencies();
        void start();
        void stop();
    }

    static final class DemoPlugin implements Plugin {
        private final String id;
        private final List<String> deps;
        private final boolean failStart;

        DemoPlugin(String id, List<String> deps, boolean failStart) {
            this.id = id;
            this.deps = List.copyOf(deps);
            this.failStart = failStart;
        }

        public String id() { return id; }
        public List<String> dependencies() { return deps; }

        public void start() {
            System.out.println("start " + id);
            if (failStart) throw new IllegalStateException("failure in " + id);
        }

        public void stop() {
            System.out.println("stop " + id);
        }
    }

    static List<Plugin> topologicalOrder(List<Plugin> plugins) {
        Map<String, Plugin> registry = new HashMap<>();
        for (Plugin p : plugins) {
            if (registry.putIfAbsent(p.id(), p) != null) {
                throw new IllegalArgumentException("Duplicate ID: " + p.id());
            }
        }

        List<Plugin> order = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        Set<String> visiting = new HashSet<>();

        for (String id : registry.keySet().stream().sorted().toList()) {
            visit(id, registry, visited, visiting, order);
        }
        return order;
    }

    static void visit(String id, Map<String, Plugin> registry,
                      Set<String> visited, Set<String> visiting,
                      List<Plugin> order) {
        if (visited.contains(id)) return;
        Plugin p = registry.get(id);
        if (p == null) throw new IllegalArgumentException("Missing: " + id);
        if (!visiting.add(id)) {
            throw new IllegalArgumentException("Dependency cycle at " + id);
        }

        for (String dep : p.dependencies().stream().sorted().toList()) {
            visit(dep, registry, visited, visiting, order);
        }
        visiting.remove(id);
        visited.add(id);
        order.add(p);
    }

    static void startAll(List<Plugin> plugins) {
        List<Plugin> ordered = topologicalOrder(plugins);
        Deque<Plugin> started = new ArrayDeque<>();
        try {
            for (Plugin p : ordered) {
                p.start();
                started.push(p);
            }
            System.out.println("all active");
        } catch (RuntimeException failure) {
            System.out.println("startup failed: " + failure.getMessage());
            while (!started.isEmpty()) {
                Plugin p = started.pop();
                try {
                    p.stop();
                } catch (RuntimeException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            throw failure;
        }
    }

    public static void main(String[] args) {
        List<Plugin> plugins = List.of(
            new DemoPlugin("report", List.of("cache", "storage"), true),
            new DemoPlugin("storage", List.of(), false),
            new DemoPlugin("cache", List.of("storage"), false)
        );

        try {
            startAll(plugins);
        } catch (RuntimeException ex) {
            System.out.println("caught: " + ex.getMessage());
            System.out.println("suppressed: " + ex.getSuppressed().length);
        }
    }
}
```

Compile and run:

```bash
javac PluginLifecycleDemo.java
java PluginLifecycleDemo
```

**Exact stdout**:

```text
start storage
start cache
start report
startup failed: failure in report
stop cache
stop storage
caught: failure in report
suppressed: 0
```

Explanation: `topologicalOrder` requires `storage` before `cache`, and then `report`, regardless of input declaration order. `started.push(p)` is **called only after `start()` returns successfully**. When `report.start()` throws, the rollback stack contains only `cache` and `storage`, stopping them in exact reverse order.

### Intentional Limitations of the Example

This example assumes a plugin whose `start()` fails will **clean up its own partially allocated resources** before throwing an exception. That is a contract that must be specified explicitly. If plugins cannot guarantee that, the host must call cleanup on the failing plugin or provide a dedicated transactional resource scope; you cannot stop only the plugins already pushed onto `started`.

None of the `stop()` calls in the demo throw exceptions, so the suppressed count is 0. In production, rollback must also handle checked exceptions, `Error` where appropriate, and cleanup operations that require timeouts. Do not blindly use a catch-all `catch(Throwable)` and keep running when the JVM may already be in a broken state.

## 6. Handling Partial Initialization Inside Each Plugin

Suppose `report.start()` performs three steps: creating a network client, opening a cache, and registering a listener. If registering the listener fails, the client and cache that were already created must be released.

Designing a plugin to clean itself up before reporting failure:

```java
final class ReportPlugin {
    private java.net.http.HttpClient client;
    private AutoCloseable subscription;

    void start() throws Exception {
        AutoCloseable newSubscription = null;
        try {
            client = java.net.http.HttpClient.newHttpClient();
            newSubscription = registerListener();
            subscription = newSubscription;
        } catch (Exception ex) {
            if (newSubscription != null) {
                try { newSubscription.close(); }
                catch (Exception cleanup) { ex.addSuppressed(cleanup); }
            }
            client = null;
            throw ex;
        }
    }

    AutoCloseable registerListener() {
        return () -> {};
    }

    void stop() throws Exception {
        if (subscription != null) {
            subscription.close();
            subscription = null;
        }
        client = null;
    }
}
```

**Illustrative snippet**, not a standalone application: `HttpClient` here merely simulates a dependency created beforehand; on Java 17, you should not claim `HttpClient` closes itself via `close()` like the `AutoCloseable` support in newer Java versions. In this example `client = null` only drops the reference; if a real resource needs closing, use that resource's proper close/stop API. `registerListener()` illustrates an `AutoCloseable` subscription.

Instead of scattering cleanup logic across multiple fields, you can use a `Deque<AutoCloseable>` inside `start()`: after each resource is created, push a cleanup action; if any step fails, pop and close them all. This pattern enables local rollback in reverse order and can be reused for `stop()`.

## 7. Resource Scope and Shutdown in Dependency Order

A host-level design pattern is to record each resource that has been successfully allocated:

```java
Deque<AutoCloseable> undo = new ArrayDeque<>();
try {
    AutoCloseable db = openDatabase();
    undo.push(db);
    AutoCloseable listener = registerListener(db);
    undo.push(listener);
    // Initialization complete: transfer undo ownership to the lifecycle manager.
} catch (Exception ex) {
    while (!undo.isEmpty()) {
        try { undo.pop().close(); }
        catch (Exception cleanup) { ex.addSuppressed(cleanup); }
    }
    throw ex;
}
```

This snippet is **illustrative only** because `openDatabase()` and `registerListener(...)` are hypothetical APIs and not standalone. The key idea: *register the undo action immediately after each step succeeds*, instead of waiting until the end to build a list of resources. Once initialization succeeds, resource ownership must be explicitly transferred to the lifecycle manager; do not automatically close them at the end of the scope as a design bug.

With multiple plugins, system-wide shutdown order is the reverse of topological order: dependents first, dependencies afterward. However, shutdown is not just `stop()`; it may also require quiescing requests, rejecting new tasks, draining queues, flushing data, waiting for threads to finish, and releasing external resources.

## 8. When One Plugin Needs Multiple Dependencies Simultaneously

A plugin may depend on multiple services, for example:

```text
billing -> storage
billing -> audit
audit   -> storage
```

Valid topological order: `storage`, `audit`, `billing`. If `audit` fails, `billing` must not run. If `billing` fails, roll back `audit` before `storage`.

Version/capability requirements should be verified before `startAll`. If a plugin is optional, the host must determine whether it can be skipped and which dependents must also be disabled, rather than letting missing services surface at runtime.

### Parallel Startup?

In a DAG, plugins independent in dependencies can be initialized in parallel, but rollback becomes more complex because completion order does not match topological order. You must track which plugins started successfully, wait for/cancel in-progress startup tasks, and then stop according to dependency relationships. Implement parallel startup only when there is a clear need and a lifecycle coordinator handles races, timeouts, and failure aggregation.

## 9. Idempotency, Retry, and Failed Rollbacks

A good `start()` should have an explicit contract regarding multiple invocations. Do not assume idempotency automatically; the host needs a state machine prohibiting two concurrent `start()` calls on the same instance. `stop()` should be safe to call in an already-stopped or failed-start state if the architecture requires repeated cleanup, while still clearly recording unrecoverable errors.

Distinguish:

- **Retry**: re-attempting initialization after a transient cause is resolved.
- **Rollback**: undoing side effects of steps that succeeded.
- **Recovery**: returning the system to a state capable of accepting a new start attempt.

Do not retry using the same failed instance if it retains partial state. Consider creating a new instance after cleanup, ensuring old resources are closed and dependencies remain `ACTIVE`.

When rollback fails, the host must retain a `FAILED_CLEANUP` marker or equivalent state. The `STOPPED` state should be used only when resources are known to have been released sufficiently per the contract. If a resource involves external transactions (DB, message broker, filesystem), compensation may not completely reverse side effects; idempotency keys or explicit compensating actions are required.

## 10. Lifecycle Monitoring and Logging

To diagnose production failures, each plugin activation should record:

- Plugin ID, version, API version, and dependent IDs.
- Start/end timestamps of each `start` and `stop`.
- Dependency path to the failing plugin.
- Primary cause and suppressed cleanup errors.
- Final state after rollback and any resources not confirmed released.

Example structured log (illustrative):

```text
event=plugin_start id=storage status=SUCCESS
event=plugin_start id=cache status=SUCCESS
event=plugin_start id=report status=FAILED reason=CONFIG
event=plugin_stop id=cache status=SUCCESS rollback=true
event=plugin_stop id=storage status=SUCCESS rollback=true
```

Do not log credentials, tokens, URLs containing secrets, or full plugin configuration. For sensitive resources, use safe identifiers and bounded telemetry.

## 11. Common Mistakes

| Mistake | Harm | Fix |
|---|---|---|
| Starting in the order JARs were scanned | Dependents may run before dependencies | Topological sort using dependency metadata |
| Not detecting cycles before start | Deadlocks/late error logs | Validate graph and report cycles clearly |
| Pushing plugin onto stack before `start()` finishes | Rollback calls `stop` on an unready instance | Push only after success; handle partial-start separately |
| Not rolling back when the third plugin fails | Leaks resources of already-active plugins | Roll back in reverse order |
| Stopping rollback as soon as one `stop()` fails | Remaining plugins never get cleaned up | Continue cleanup, use `addSuppressed` |
| Catching exceptions and continuing to serve | System runs with missing services | Fail startup or degrade under controlled policy |
| Reusing a failed-start instance for retry | Partial state and leftover old resources | Clean up, create a new instance or formal reset mechanism |
| Calling `stop()` without respecting dependencies | Dependencies closed while dependents still use them | Shut down in reverse topological order |

## 12. Pre-Release Checklist for a Plugin Host

- [ ] Plugin metadata describes ID, version, and required/optional dependencies.
- [ ] Host validates missing IDs, duplicate IDs, cycles, and API compatibility before activation.
- [ ] Topological start order produces deterministic results when multiple plugins are independent.
- [ ] `start()` has a contract for partial failure; resource ownership is explicit.
- [ ] Host marks a plugin ACTIVE after success and rolls back in LIFO order.
- [ ] Cleanup errors are attached to the primary failure without blocking cleanup of remaining plugins.
- [ ] Timeout/quiescence/retry policies and an explicit state for cleanup failures exist.
- [ ] Integration tests cover: all succeed, missing dependency, cycle, mid-way failure, and cleanup failure.

**Conclusion:** Reliable plugin lifecycle management begins with a dependency graph verified before activation. Start in topological order, record each success, roll back in reverse order, and clean up partial initialization states as well. This is the foundation that lets a host start consistently and recover when only part of the plugin system initializes successfully.
