# Handling Errors During Plugin Shutdown and Ensuring Deterministic Behavior on Repeated Close

## 1. Why Is Stopping a Plugin Harder Than Calling close()?

Plugins in a Java application commonly own executors, threads, schedulers, sockets, connections, listeners, file handles, native resources, or registrations in the host's registry. When stopping, a cleanup step may throw an exception; if the host halts at the first exception, the remaining resources are never released. Furthermore, the same plugin can receive stop requests multiple times: application-wide shutdown, reload, timeout, or an error callback firing concurrently. Thus stopping a plugin requires **deterministic behavior** even when cleanup fails.

A sound design must distinguish:

- **Idempotent stop/close:** subsequent calls do not re-run the same cleanup or produce new side effects.
- **Best-effort cleanup:** attempts to release independent resources even if one step fails.
- **Error aggregation:** preserves the first error and attaches subsequent errors with `addSuppressed`, or reports a structured status.
- **Concurrency:** prevents two threads from stopping the same resource simultaneously and causing double-close/races.
- **Lifecycle observability:** knows the final state and stop reason, never claiming “cleanly closed” when errors occurred.

Idempotence does **not** mean the first close always succeeds; it means subsequent close calls yield an outcome defined by the contract rather than unexpectedly re-executing cleanup.

## 2. State Machine Design

```text
NEW --start()--> STARTING --success--> RUNNING
                         | failure        | stop()/close()
                         v                v
                       FAILED          STOPPING
                                          |
                                cleanup success/failure
                                          v
                                        STOPPED
```

In many systems, `FAILED` during start must also be cleaned up: every resource allocated before the failure needs stopping. A stricter state machine may separate `STOPPED` (no more tasks accepted) and `CLOSED_WITH_ERRORS` (cleanup had errors). The design must specify which states are terminal, which allow retries, and when the host stops routing requests to the plugin.

Minimum invariants:

1. Upon entering `STOPPING`, accept no new requests.
2. A single thread executes cleanup; other callers wait or receive the completed result.
3. Cleanup is attempted once per resource, in an explicit order.
4. Cleanup errors do not mask the primary error that triggered shutdown.
5. All callers after stop completes observe the same final outcome or the same failure summary.

## 3. Safe Shutdown Order

For a plugin with in-flight requests:

1. Mark **quiescing** and remove the plugin from routing/registry to reject new requests.
2. Stop schedulers, inbound callbacks, and sources of new tasks.
3. Wait for running tasks to finish with a timeout; if needed, cancel per policy and manage interrupts.
4. Flush/commit or roll back in-progress work according to plugin semantics.
5. Run resource cleanup in reverse dependency order (LIFO can fit well).
6. Unregister listeners, drivers, hooks, metrics, resource callbacks, and drop host references.
7. Clean up thread-context-classloader (TCCL) and `ThreadLocal`s on plugin-managed worker threads.
8. After the provider is no longer in use, close the classloader if its loader type supports `close`; drop strong references so GC can reclaim it.

Do not treat `URLClassLoader.close()` as a command that stops the entire plugin: it does not stop threads, clear registries, or free all objects on its own. Likewise, `ModuleLayer` has no `close()` to unload modules.

## 4. Java 17+ Example: Single-Flight Close and Error Aggregation

The example below uses `AtomicReference<CompletableFuture<Void>>` as a **single-flight close**: one caller creates the future representing the shutdown outcome; remaining callers wait on that same future. It stores failures too, so calling `close()` again after an error receives the same cause rather than pretending to succeed or re-running cleanup.

File `PluginShutdownDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicReference;

public final class PluginShutdownDemo {
    interface Step {
        void run() throws Exception;
    }

    static final class Plugin implements AutoCloseable {
        private final List<Step> cleanup;
        private final AtomicReference<CompletableFuture<Void>> closing =
                new AtomicReference<>();

        Plugin(List<Step> cleanup) {
            this.cleanup = List.copyOf(cleanup);
        }

        @Override
        public void close() throws Exception {
            CompletableFuture<Void> created = new CompletableFuture<>();
            if (closing.compareAndSet(null, created)) {
                Exception first = null;
                for (int i = cleanup.size() - 1; i >= 0; i--) {
                    try {
                        cleanup.get(i).run();
                    } catch (Exception ex) {
                        if (first == null) first = ex;
                        else first.addSuppressed(ex);
                    }
                }
                if (first == null) created.complete(null);
                else created.completeExceptionally(first);
            }

            try {
                closing.get().join();
            } catch (CompletionException ex) {
                Throwable failure = ex.getCause();
                if (failure instanceof Exception exception) throw exception;
                if (failure instanceof Error error) throw error;
                throw new IllegalStateException(failure);
            }
        }
    }

    public static void main(String[] args) {
        List<String> log = new ArrayList<>();
        Plugin plugin = new Plugin(List.of(
                () -> log.add("close-A"),
                () -> { log.add("close-B"); throw new Exception("B failed"); },
                () -> log.add("close-C")
        ));

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                plugin.close();
            } catch (Exception ex) {
                System.out.println("attempt " + attempt + ": "
                        + ex.getMessage());
            }
        }
        System.out.println("cleanup=" + log);
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 PluginShutdownDemo.java
java PluginShutdownDemo
```

Output:

```text
attempt 1: B failed
attempt 2: B failed
cleanup=[close-C, close-B, close-A]
```

Explanation: `List.copyOf` fixes the cleanup order; the loop runs from back to front, following LIFO order. B fails, yet A is still attempted. The error outcome is stored in the future, so the second close call does not re-run any step. With multiple errors, secondary failures are available in `getSuppressed()` on the first exception.

**Example scope:** each `Step` is assumed to be short, non-hanging forever, and never re-entrantly calling `plugin.close()` from inside cleanup. Calling close recursively on the cleanup thread itself would deadlock waiting on its own future. Production systems must explicitly define reentrant shutdown and timeouts. `Error`/`Throwable` outside `Exception` also needs a strategy so the future is never left incomplete; the next section explains how to harden it.

## 5. What Happens If Multiple Threads Call close() Simultaneously?

With `AtomicReference` in the example, only one caller succeeds at `compareAndSet(null, created)` and executes cleanup. Other callers that lose the CAS wait on `closing.get().join()`. Still, for full production readiness you must handle:

- **Thread interrupted while waiting:** `CompletableFuture.join()` does not throw `InterruptedException`; if your contract needs interrupt responsiveness or timeouts, use `get(timeout, unit)` with explicit handling.
- **Hanging cleanup:** if cleanup has no timeout, concurrent callers can all wait forever; set deadlines and classify cancelable steps.
- **Exception vs. Error:** catching `Exception` will not catch `OutOfMemoryError`, `StackOverflowError`, or other severe errors. Consider `try/finally` completing the future with failure if any `Throwable` escapes; never swallow critical JVM errors.
- **Reentrant close:** you may need to check the shutdown thread owner or design cleanup so it never calls `close` again.
- **Closing under locks:** do not execute user/plugin cleanup inside a long-held synchronized lock; callbacks can call back into the host and deadlock.

An alternative is lock + state enum + `CountDownLatch`, though you still need a mechanism for subsequent callers to receive the prior state/failure. Merely using `AtomicBoolean.compareAndSet(false, true)` and returning immediately when already closing satisfies basic idempotence, yet **does not guarantee the second caller waits for cleanup to actually finish**.

## 6. Aggregation: Never Lose Cleanup Errors

Suppose a plugin owns three resources: A, B, and C. If both C and B fail, stop must still try to close A while reporting both errors. A common pattern:

```java
Exception primary = null;
for (AutoCloseable resource : resources) {
    try {
        resource.close();
    } catch (Exception ex) {
        if (primary == null) primary = ex;
        else if (primary != ex) primary.addSuppressed(ex);
    }
}
if (primary != null) throw primary;
```

This is an illustrative snippet inside a method that has `resources` and an appropriate ordering policy. If closing in reverse allocation order is required, iterate backward. Avoid calling `addSuppressed` on the same exception object itself because Java forbids self-suppression.

**Try-with-resources** automatically closes `AutoCloseable`s in reverse order and preserves suppressed exceptions. However, when a plugin holds resources across multiple requests or lifecycle phases, dedicated shutdown coordination is required and not every resource can be created inside a single `try-with-resources` scope.

## 7. Primary Error and Shutdown Errors

An important case: a plugin encounters a business error while processing a request, the host begins stopping the plugin, and cleanup also fails. **Do not let cleanup failure mask the primary error.** You can attach cleanup errors as suppressed on the primary error, or build a `PluginFailure` holding two parts: `cause` for the primary failure and `cleanupFailures` for teardown errors.

Illustrative example:

```java
Throwable original = failureFromPlugin;
try {
    plugin.close();
} catch (Exception cleanupFailure) {
    if (original != cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
}
throw original;
```

This snippet is pseudocode at a method boundary with an appropriate `throws` signature, not a complete Java method. In production code, you can wrap in a domain exception to avoid losing checked exceptions and preserve correlation IDs for the request/plugin.

## 8. Idempotence Is Not Default Cleanup Retry

There are two valid policies that must be kept distinct:

1. **At-most-once cleanup:** each step runs at most once; repeated closes return the same outcome. Pros: avoids double-close or unsafe side effects. Cons: failed steps are not retried automatically.
2. **Retryable cleanup:** allows controlled retries for steps proven idempotent (such as calling a delete API with a request ID). This requires per-resource state, attempt counts, backoff/deadlines, and clear rules; it cannot share the same simple contract as at-most-once.

For instance, `Socket.close()` can usually be called repeatedly, whereas a plugin calling `flushAndCommit()` or `unregisterAndCharge()` is not necessarily idempotent. Do not assume every cleanup step is safe to retry. If a step is still running, never start a second attempt in parallel.

## 9. Terminal States and Operational Reporting

To avoid misleading conclusions, terminal states may include:

| State | Meaning |
| --- | --- |
| `STOPPED` | Stopped accepting work and cleanup completed successfully per contract |
| `STOPPED_WITH_ERRORS` | Attempted cleanup steps, at least one step failed; some resources may remain unreleased |
| `STOPPING` | Cleanup in progress; later callers must wait or receive an in-progress status |
| `FAILED_START` | Startup failed; allocated resources still require cleanup |

Logging should include plugin ID, version, lifecycle transition, duration, resource name, error class, suppressed error count, and timeouts. Never log just `close completed` when errors occurred. For leaks, track live thread counts, listener/registry entries, sockets, file descriptors, and references retaining classloaders.

## 10. Required Test Cases

- **Double-close:** call `close()` twice; each cleanup step runs exactly once.
- **Concurrent-close:** multiple threads call concurrently; exactly one thread runs cleanup and all callers receive the same outcome.
- **First-step failure:** the last step in teardown order fails, and remaining steps are still attempted.
- **Multiple failures:** primary and suppressed exceptions are preserved intact.
- **Start partially failed:** resources allocated before startup failed are cleaned up; never marked RUNNING.
- **Timeout:** a blocking cleanup does not hang application-wide shutdown forever when a deadline is configured.
- **Reentrant close:** callbacks do not cause self-deadlock; policy is explicit.
- **Interrupt:** interrupt status is preserved and terminal state does not transition wrongly.
- **Reload:** new requests route to the new plugin; old plugin drains before close.

## 11. Common Design Mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| `catch(Exception e) {}` in stop | Resource leaks go unnoticed | Aggregate and report errors |
| Exiting stop on the first step failure | Remaining cleanup skipped | Best-effort per step |
| Re-running cleanup after failure | Double-release/side effects | Specify at-most-once or retryable policy |
| Only setting boolean `closed=true` before cleanup | Callers think stop already finished | Separate STOPPING and terminal; let callers wait |
| Holding locks while invoking plugin callbacks | Deadlocks, latency | Single-flight state + cleanup outside locks |
| `close()` succeeds while requests still route | Races against closed resources | Quiesce and drain before cleanup |
| Only closing the classloader | Threads/listeners/sockets remain alive | Comprehensive lifecycle cleanup |
| Marking STOPPED despite cleanup failure | Misleading state reporting | `STOPPED_WITH_ERRORS` and metrics |

## 12. Checklist

- [ ] Explicit state transitions: RUNNING → STOPPING → terminal.
- [ ] Stop accepting tasks before teardown; drain with a deadline.
- [ ] Only one caller executes cleanup; other callers receive the same completion/failure.
- [ ] Cleanup follows resource dependency order; attempt all independent steps.
- [ ] Aggregate suppressed exceptions without masking the primary error.
- [ ] Explicit decision between at-most-once and retryable cleanup.
- [ ] Handle timeouts, interrupts, reentrancy, and `Error` in production.
- [ ] Remove registrations, stop threads, restore TCCL, drop classloader references.
- [ ] Log state and cleanup errors; never falsely report success.
- [ ] Test double-close, concurrent-close, and multiple failures.

**Conclusion:** stopping a plugin is a lifecycle protocol requiring idempotence, ordering, and explicit error handling. Designing with single-flight stop, best-effort cleanup, exception aggregation, and consistent terminal result publication ensures repeated `close()` calls behave deterministically without hiding resource leaks.
