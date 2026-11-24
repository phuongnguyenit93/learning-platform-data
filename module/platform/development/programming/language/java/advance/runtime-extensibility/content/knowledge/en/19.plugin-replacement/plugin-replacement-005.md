# Handling In-Flight Requests, State Transitions, and Rollback During Plugin Replacement

Replacing a plugin in a Java application serving live traffic **is not as simple as unloading the old JAR and loading the new JAR**. At the moment of version cutover, some requests may already hold references to the old plugin, some may still be queued, and some tasks may run asynchronously or hold long-lived connections. A new version may pass startup checks yet fail under real traffic; the host then needs to **roll back**, routing new requests back to the previous version **without corrupting requests and data that already passed through the new version**.

For the runtime extensibility module, three questions must be solved simultaneously:

1. **How are in-flight requests handled?** Let them finish on the plugin generation they selected, or cancel them cleanly under policy, rather than closing the class loader or destroying resources currently in use.
2. **How are state transitions handled?** Prepare, validate, activate, stop admitting new work, wait to drain, and retire the old version using clear states and synchronization boundaries.
3. **How is rollback handled?** Keep an older plugin generation usable within a rollback window, switch routing atomically, and verify compatibility of state, data, APIs, and side effects.

This lesson presents the **generation + request lease + atomic cutover + graceful drain + controlled rollback** model, illustrated with a standalone Java 17 program, then extends it to real systems with HTTP, queues, long-running jobs, databases, and plugin class loaders.

## 1. Why does hot-swapping a plugin easily drop requests?

Suppose the host provides a **Formatter** service. The running generation is v1, and we are preparing to replace it with v2. At a given moment, the following requests may exist:

~~~text
                                    +--------------------+
Request already entered v1 -------->| Plugin v1 running  |----->
                                    +--------------------+
                                             ^
                                             | holds reference/lease
                                             |
                        cutover point -------|--------------------
                                             |
New request --------------------->+--------------------+
                                  | Plugin v2 running  |----->
                                  +--------------------+
~~~

If the host merely replaces a `currentPlugin` variable with v2 and immediately calls stop/close on v1, a request that already started with v1 may hit an unloaded file, pool, service, or module. Failures appear mid-flight even though reassigning `currentPlugin` looked successful on the surface.

Conversely, if the host locks the entire application while waiting for every request to finish before swapping the plugin, long requests or streaming connections can stall deployments and cause prolonged outages. The system needs to **stop admitting new work to the old version while allowing already-admitted work to proceed**, backed by deadlines and handling for tasks that fail to finish.

The core distinction is:

- **Request admission**: at acceptance time, pick the currently `ACTIVE` generation.
- **Request execution**: execute on the selected generation, even if the `current` variable later moves to another generation.
- **Completion/release**: return the lease once all processing has truly finished, so the old generation is cleaned up only when no consumers remain.

Swapping a pointer without managing in-flight requests, state, and data is usually an **unsafe hot switch**, not a complete hot replacement.

## 2. Objects needed in the design

A host can use the following concepts:

| Component | Responsibility | Example |
| --- | --- | --- |
| **Plugin generation** | One specific load of a plugin, with ID/version, instance, class loader, configuration, resources, and state | formatter-v2 / generation-42 |
| **Routing pointer** | Selects the generation receiving **new** requests | activeGeneration |
| **Lease / in-flight counter** | Tracks which requests are using which generation; released only upon actual completion | v1.inFlight = 3 |
| **Lifecycle controller** | Defines states, guards, timeouts, and activate/rollback/retire decisions | PREPARED → ACTIVE → DRAINING |
| **Readiness/health gate** | Verifies the plugin is ready for traffic, dependencies exist, and operational metrics pass | health checks, error rate |
| **Rollback candidate** | Older generation kept alive and compatible for reactivation when needed | v1 held in STANDBY |
| **State/data compatibility plan** | Ensures outputs written by v2 do not make v1 unreadable on rollback | expand–contract migration, versioned events |

A **generation** is not synonymous with a single semantic version. The same v2 may be reloaded into multiple generations with different class loaders, different resources, or different configurations. What must be managed is **the generation identity held by requests**, not just the string `"2.0"`.

### What counts as in-flight?

A request is considered in-flight from the moment **the host grants a lease** to begin using a generation until all work for that request finishes and the lease is released. Depending on the application, this can be:

- Synchronous HTTP request: from when routing picks the plugin until the response is sent and cleanup completes.
- `CompletableFuture`: until the future completes or finishes via error/cancellation per policy.
- Message consumer: until processing and commit/ack or dead-letter/retry routing per rules.
- Streaming/gRPC/WebSocket: may span the entire session if the session holds plugin resources/logic.
- Scheduled job or long workflow: minutes or hours, potentially needing checkpoints and handoff to another generation under a custom protocol.

**Never** release a lease right after calling a method returning a `Future` if asynchronous callbacks still access the plugin. Similarly, do not count only HTTP connections if a single connection can send multiple requests; count the actual work using the generation.

## 3. Plugin replacement state machine

A straightforward model to use:

~~~text
         load JAR + config + dependencies
                     |
                     v
                 PREPARED
                     |
           readiness / smoke tests
                     |
                     v
                 ACTIVATING
                     |
               atomic cutover
                     |
                     v
                   ACTIVE
                     |
          another generation replaces it
                     |
                     v
                  DRAINING
                     |
             inFlight drops to 0
                     |
                     v
                  STANDBY
                  /     \
       rollback     /       \ rollback window expires
                  v           v
                ACTIVE       CLOSED
                              |
                       close resources,
                      drop strong references
~~~

This is a **reference design model**. No built-in JDK enum manages states for application plugins; the host must implement, audit, and validate state transitions.

Meaning of each state:

- **PREPARED**: artifact located, signature/trusted origin verified, configuration and API compatibility checked, and loaded in its own scope; **not** yet receiving production requests.
- **ACTIVATING**: running required guards and preparing to publish the route; public admission into the generation is not open before readiness.
- **ACTIVE**: valid generation for admitting **new requests**; all incoming requests acquire leases here.
- **DRAINING**: admits no new requests, while previously admitted requests continue using the old instance and resources.
- **STANDBY**: no requests are running, resources required for rollback are kept intact; the generation can be reactivated if compatible.
- **CLOSED**: admits no new requests, no leases remain, resources are closed per contract, and the generation cannot be reactivated via fast rollback.

In the runnable Java example in Section 6, **ACTIVATING** is folded into a short-locked `activate` operation for simplicity. In real systems with health checks and distributed coordination, preparation and verification run outside critical sections; only **publishing the pointer/routing rule** needs to be atomic.

### Invariants that must always hold

1. **A `CLOSED` generation must never issue a new lease.**
2. **For a given route/tenant at any point in time, only generations allowed by admission policy accept new requests.** With canary releases, multiple weighted `ACTIVE` generations may exist; this must be specified explicitly.
3. **Every lease is immutably pinned to one generation**, never switching mid-flight when the pointer cuts over.
4. **Never close a generation with `inFlight > 0`**, except in emergency situations with a defined cancellation/forced-stop policy.
5. **Never roll back to a generation that is `CLOSED` or incompatible with current state.**
6. **Route switching and lease acquisition must coordinate synchronously**, leaving no race window where new requests enter a generation whose admission already stopped.
7. **Rollback does not erase side effects** already produced by the faulty version; data and transactions must be assessed separately.

Failing to protect these invariants can cause memory/resource leaks, calls against closed plugins, dropped requests, or rollbacks producing unreadable data.

## 4. Four phases of a controlled replacement

### Phase A — Prepare, without touching live traffic

- Load the new version into a **new generation**, without directly modifying classes/instances in the old generation.
- Verify artifact provenance, API version, dependency graph, configuration, and permitted capabilities.
- Instantiate objects and required resources; if the plugin has `start()`, invoke it per startup contract.
- Run readiness/smoke tests on controlled test data. Synthetic traffic or shadow requests may be tried, provided **shadowing does not write real side effects** where duplicate transactions are dangerous.
- Verify the plugin can read the current data schema, emit events compatible with old/new consumers, and does not require migrations that destroy the rollback path.
- Mark the new generation `PREPARED`/`READY` and record generation ID, config hash, artifact checksum, and health baseline.

If preparation fails, **do not switch routes**: close the partially initialized resources of the new generation, keep v1 `ACTIVE`, and report the deployment error. This is the simplest rollback: **cutover never committed**.

### Phase B — Activate/cutover

Within a brief synchronization boundary:

1. Ensure the candidate is ready and not closed.
2. Read the currently `ACTIVE` generation.
3. Mark the old generation as no longer accepting new requests.
4. Publish the route/pointer to the new generation.
5. Mark the new generation `ACTIVE` and record the cutover ID/timestamp.

Selecting a generation and incrementing `inFlight` for a request **must share the same synchronization protocol** as the cutover step. For example, use `synchronized` on a shared monitor or a properly designed CAS+refcount protocol. **`AtomicReference.set(newGeneration)` alone is not enough** if a request reads the pointer before cutover and increments refcount after the system closed v1; admission must be verified/enforced after acquiring the lease.

The desired outcome is that **requests already holding a v1 lease keep running on v1**, while **new requests after cutover receive a v2 lease**. The system does not force old requests to swap business logic mid-transaction.

### Phase C — Drain the old generation

v1 moves to `DRAINING`, without closing the class loader, thread pool, connection pool, or state still used by v1 requests. The in-flight counter decreases as each request completes. Once at 0, v1 can enter `STANDBY` for the rollback window.

During draining, monitor:

- `v1.inFlight`, `v2.inFlight` per generation, route, and tenant.
- Age of lingering old requests, request types, and latency on the old generation.
- Futures/callbacks/timers/consumers or streams still holding references to v1.
- Overall rollout deadline and escalation mechanism for hung requests.

If draining takes too long, options depend on the contract:

- **Wait longer up to a deadline** when requests are valid and the system has sufficient resources.
- **Stop admitting into long-lived workloads or migrate new sessions** under an explicit draining policy.
- **Cancel with confirmed termination** for cancellable jobs; release resources only after work actually stops.
- **Checkpoint/retry** at idempotent boundaries when plugins support progress handoff across versions.
- **Restart a dedicated worker/process** via a forced procedure if the plugin is uncooperative; do not treat closing a class loader inside the same JVM as a safe way to kill threads.

### Phase D — Commit or rollback

After cutover, observe v2 over the chosen window: latency, errors, timeouts, memory, resource usage, business outcomes, and data compatibility. If v2 is stable and the rollback window expires, retire v1 once no in-flight or rollback dependencies remain.

If problems appear in v2, **roll back the route** to a compatible generation (v1 still alive), move v2 into `DRAINING`, let requests already holding v2 leases finish or cancel cleanly, and only then clean up v2. Rollback does not automatically revert the entire world to its state before v2 served traffic: **DB writes, sent emails, charges/payments, published events, and cache updates** may already have occurred.

## 5. Timeline illustrating three requests

~~~text
Time        App / route              Request A         Request B         Request C
----------  -----------------------  ----------------  ----------------  ---------------
t0          active = v1              acquire v1
t1          prepare v2               processing v1
t2          cutover: active = v2     still processing v1
t3          v1 DRAINING              complete v1       acquire v2
t4          v1 inFlight = 0                            processing v2
t5          v1 STANDBY                                 complete v2
t6          v2 health bad            --                --                --
t7          rollback: active = v1                                        acquire v1
t8          v2 DRAINING/STANDBY                                          complete v1
t9          v2 CLOSED after drain
~~~

At t2, request A is not switched to v2. At t7, requests that already received a v2 lease before rollback continue processing on v2 under the default policy, while request C gets a v1 lease. When a business path cannot allow v2 to continue producing hazardous side effects, an additional **stop/cancel/quarantine** policy is required beyond just swapping the pointer.

This table shows **logical progression**, not a guarantee that requests always finish in a fixed order. Across multiple workers/processes, timestamps t0–t9 must be coordinated via a deployment coordinator and epoch identifiers.

## 6. Runnable Java 17 example: lease, cutover, draining, and rollback

This standalone example models two generations v1/v2 of a plugin. Its purpose is to prove state ordering and preservation of old requests across cutover **without depending on a web server, database, or external JAR files**.

**Scope note:** the example simulates request processing with `String` functions and controls progress sequentially so stdout is deterministic. It uses a shared monitor to illustrate atomic coordination between **admission and cutover**; it is not yet a production plugin manager, does not stop threads automatically, integrates no network health checks, and has no real `URLClassLoader` cleanup yet. Subsequent sections explain how to expand it.

### 6.1. File PluginCutoverDemo.java

~~~java
public final class PluginCutoverDemo {

    enum State {
        PREPARED, ACTIVE, DRAINING, STANDBY, CLOSED
    }

    @FunctionalInterface
    interface Handler {
        String handle(String input);
    }

    static final class Generation {
        final String version;
        final Handler handler;
        State state = State.PREPARED;
        int inFlight;

        Generation(String version, Handler handler) {
            this.version = version;
            this.handler = handler;
        }
    }

    static final class Router {
        private final Object gate = new Object();
        private Generation current;

        Router(Generation initial) {
            if (initial.state != State.PREPARED) {
                throw new IllegalArgumentException("Not prepared");
            }
            initial.state = State.ACTIVE;
            current = initial;
        }

        Lease acquire() {
            synchronized (gate) {
                Generation g = current;
                if (g == null || g.state != State.ACTIVE) {
                    throw new IllegalStateException("No active generation");
                }
                g.inFlight++;
                return new Lease(this, g);
            }
        }

        Generation activate(Generation candidate) {
            synchronized (gate) {
                if (candidate.state != State.PREPARED) {
                    throw new IllegalStateException("Candidate not prepared");
                }

                Generation previous = current;

                previous.state = previous.inFlight == 0
                        ? State.STANDBY : State.DRAINING;

                candidate.state = State.ACTIVE;
                current = candidate;
                return previous;
            }
        }

        void rollbackTo(Generation previous) {
            synchronized (gate) {
                if (previous == current ||
                        (previous.state != State.STANDBY &&
                         previous.state != State.DRAINING)) {
                    throw new IllegalStateException(
                            "Previous generation not reusable");
                }

                Generation failed = current;
                failed.state = failed.inFlight == 0
                        ? State.STANDBY : State.DRAINING;

                previous.state = State.ACTIVE;
                current = previous;
            }
        }

        void release(Generation generation) {
            synchronized (gate) {
                if (generation.inFlight <= 0) {
                    throw new IllegalStateException("Lease underflow");
                }
                generation.inFlight--;

                if (generation.inFlight == 0 &&
                        generation.state == State.DRAINING) {
                    generation.state = State.STANDBY;
                }
            }
        }

        void markClosed(Generation generation) {
            synchronized (gate) {
                if (generation == current ||
                        generation.state != State.STANDBY ||
                        generation.inFlight != 0) {
                    throw new IllegalStateException(
                            "Generation is still in use");
                }
                generation.state = State.CLOSED;
            }
        }

        State stateOf(Generation generation) {
            synchronized (gate) {
                return generation.state;
            }
        }
    }

    static final class Lease implements AutoCloseable {
        private final Router router;
        private final Generation pinned;
        private boolean closed;

        Lease(Router router, Generation pinned) {
            this.router = router;
            this.pinned = pinned;
        }

        String execute(String input) {
            if (closed) {
                throw new IllegalStateException("Lease closed");
            }
            return pinned.handler.handle(input);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                router.release(pinned);
            }
        }
    }

    public static void main(String[] args) {
        Generation v1 = new Generation(
                "v1", input -> "v1:" + input);
        Generation v2 = new Generation(
                "v2", input -> "v2:" + input);

        Router router = new Router(v1);

        // Request A acquired v1 lease before cutover.
        try (Lease pending = router.acquire()) {
            router.activate(v2);

            System.out.println(
                    "ongoing=" + pending.execute("A"));

            // Request B arrives after cutover and is routed to v2.
            try (Lease newer = router.acquire()) {
                System.out.println(
                        "new=" + newer.execute("B"));
            }

            System.out.println(
                    "old-while-inflight=" + router.stateOf(v1));
        }

        // Request A finishes, v1 lease is released.
        System.out.println(
                "old-after-drain=" + router.stateOf(v1));

        // Assume health gate decides v2 fails.
        router.rollbackTo(v1);

        try (Lease after = router.acquire()) {
            System.out.println(
                    "after-rollback=" + after.execute("C"));
        }

        System.out.println(
                "v2-after-rollback=" + router.stateOf(v2));

        router.markClosed(v2);
        System.out.println(
                "v2-after-retire=" + router.stateOf(v2));
    }
}
~~~

### 6.2. Compiling and running on Java 17+

Save as **PluginCutoverDemo.java** in UTF-8 encoding, then use JDK 17 or newer:

~~~bash
javac -encoding UTF-8 PluginCutoverDemo.java
java PluginCutoverDemo
~~~

**Deterministic stdout:**

~~~text
ongoing=v1:A
new=v2:B
old-while-inflight=DRAINING
old-after-drain=STANDBY
after-rollback=v1:C
v2-after-rollback=STANDBY
v2-after-retire=CLOSED
~~~

### 6.3. Why is the example right about admission/drain?

**Initial stage:** the router points to v1. Request A acquires a `Lease` for v1 and increments `v1.inFlight` inside the same gate. Then `activate(v2)` switches the pointer, yet Lease A keeps holding the reference `pinned=v1`.

**After cutover:** Request B calls `acquire` and sees v2 `ACTIVE`, so `execute` returns `v2:B`. Request A continues running `v1:A`; v1 is `DRAINING`, accepting no new requests yet still has `inFlight=1`.

**When A finishes:** try-with-resources invokes `Lease.close()`, decrementing v1's `inFlight` from 1 to 0. `release` transitions v1 from `DRAINING` to `STANDBY`. The lesson is to **close the lease after the work**, not close the plugin immediately upon switching the pointer.

**On rollback:** `rollbackTo(v1)` moves v2 to `STANDBY` (since Request B already finished), reactivates v1, and switches the pointer back to v1. Request C gets v1 and returns `v1:C`.

**On retire:** `markClosed(v2)` transitions only the **modeled state** to `CLOSED` once v2 has no in-flight requests and is no longer the `ACTIVE` pointer. In a real system, you must also call stop/close on actual resources (once no consumers or rollback dependencies remain) and handle cleanup exceptions.

### 6.4. Intentional limitations of the demo

- The demo does not launch two concurrent Java threads; it proves by logical sequencing that a request already holding v1 before cutover still uses v1 after cutover. Real concurrency tests must use thread pools, barriers, and dedicated timeouts.
- Each `Lease` in the demo is owned by **a single processing flow**. The `closed` field is a plain boolean with no protocol for multiple threads closing/calling concurrently on the same `Lease`. A production host needs ownership rules or a thread-safe lease implementation.
- Handlers here hold no resources or side effects. Production must scope DB connections, SDK handles, background jobs, and callbacks to the generation.
- `Router` manages only **a single process**. Switching multiple instances in a cluster requires a version/epoch coordinator, health gating, and synchronized rollback.
- `rollbackTo` checks only the modeled state. Production also needs **schema compatibility**, artifact trust, permissions, data state, and a rollback window policy.
- Never use `Thread.stop`, directly unload classes, or close a class loader while requests are running.

This program is for **learning lifecycle invariants**, not a complete hot-replacement solution with all operational conditions.

## 7. With async tasks, leases must stay alive until true completion

The difference between synchronous and async APIs easily causes bugs. For a method returning `CompletableFuture`, the following code is **broken with respect to lifecycle**:

~~~java
// DANGEROUS example: illustrative logic; not a standalone program.
try (PluginLease lease = router.acquire()) {
    return lease.plugin().startAsync(input);
}
// Lease closes immediately when returning future, while plugin is still running.
~~~

`PluginLease` is a hypothetical host-defined interface, not a built-in Java API. In the snippet above, try-with-resources calls `close` **before the future completes**; the host may see `inFlight=0`, close the generation, and break the async work.

A more appropriate pattern:

~~~java
// ILLUSTRATIVE CODE: assumes lease, router, input, Response are already defined.
// CompletionStage<Response> is the result returned by the plugin.
PluginLease lease = router.acquire();

try {
    return lease.plugin()
            .startAsync(input)
            .whenComplete((value, failure) -> lease.close());
} catch (RuntimeException | Error failure) {
    lease.close();
    throw failure;
}
~~~

Hold the lease until the completion stage finishes, on both success and exception. However, watch these subtleties:

1. **Cancellation** does not necessarily stop underlying work immediately; release only when policy confirms the plugin is no longer using generation resources, or when a wrapper owning all invoked work finishes.
2. Completion callbacks can run on any thread; production needs **idempotent and thread-safe `close`** to avoid decrementing counters twice if cancellation, timeout, and completion arrive together.
3. If the stage completes while fire-and-forget async side effects remain unrepresented by the stage, the lease still releases early. Tie all real work to the lifecycle.
4. If `close` throws an exception inside the callback, log and handle it per API without accidentally overwriting or masking the original business error.
5. Executors and scopes/contexts can propagate generation, request ID, and tenant information across threads.

Do not migrate an in-flight request to the new version by re-invoking the handler on v2 inside an arbitrary callback. That could execute the same business logic twice if v1 already produced partial side effects.

## 8. When to cancel requests and when to let them finish?

A good replacement policy classifies workloads rather than applying a single uniform timeout.

| Workload type | Usually suitable drain policy | What must be preserved |
| --- | --- | --- |
| Short HTTP request | Let complete within grace period | Return response matching the admitted version |
| Idempotent read | Can cancel/retry on clear timeout | Avoid duplicate responses or wrong data |
| DB write or payment | Prefer completing/committing transaction; retry with idempotency key | Avoid double-charge/double-write |
| Message queue consumer | Pause fetching new messages, finish/ack in-flight; use retry/DLQ appropriately | At-least-once semantics and deduplication |
| Multi-hour batch job | Checkpoint at stable boundary, resume with protocol | No lost progress or uncontrolled partial re-runs |
| Long-lived WebSocket/gRPC stream | Drain session, signal reconnect, or keep old generation until deadline | Do not sever connections arbitrarily |
| Background timers/scheduled callbacks | Stop scheduling new runs, wait for active callbacks and clean handles | Do not retain old loader after plugin retires |
| Untrusted/uncooperative plugin | Isolate in a restartable/cancellable worker process | Do not hang host JVM or crash the whole system |

**`inFlight=0` is trustworthy only if you count every form of usage.** Plugin-supplied handles stored by the host in caches, event listeners, thread locals, timer tasks, or static registries can continue holding references even when zero HTTP requests remain. They must be inventoried and included in the stop/unregister protocol.

### Rules for timeouts and graceful shutdown

- Set deadlines both per request and per rollout. When the deadline expires, distinguish tasks that **can be safely cancelled** from tasks in a commit phase that cannot be cancelled arbitrarily.
- Do not use `Thread.stop` to forcibly halt plugin code in the same JVM: it can corrupt monitors and shared state.
- `Thread.interrupt()` or `cancel(true)` only sends a cooperative signal; it does not guarantee plugin code stops immediately.
- For plugins with native code, unbounded I/O, or untrusted scripts, a worker process with CPU/RAM/time limits and kill/restart capability usually provides stronger isolation.
- Past the deadline, if in-flight work has not stopped, never falsely mark `CLOSED` and close the loader. Instead move the rollout to **BLOCKED/DEGRADED**, continue monitoring, or apply forced termination at a process boundary.

## 9. Route rollback is not data rollback

This is the most important limitation of hot replacement. While v2 was `ACTIVE`, it may have:

- Written new rows to the database under the v2 schema.
- Published events that v1 consumers do not understand.
- Marked a transaction as processed or sent notifications.
- Created cache entries in a new format.
- Called third-party APIs causing hard-to-reverse side effects.
- Mutated file or session state outside the plugin class loader.

Switching the pointer back to v1 **only decides where new requests go**. It **does not undo** those changes.

### 9.1. Expand–contract migration

During the rollback window, prefer data changes with **backward/forward compatibility**:

1. **Expand**: add new optional columns or fields; both v1 and v2 can still read the shared format.
2. **Transition**: v2 writes a compatible format or performs controlled dual-write/dual-read; versioned payloads and adaptive consumers.
3. **Observe**: verify both v1 and v2 handle critical data/events during the rollback window.
4. **Contract**: remove old columns/fields or apply breaking migrations **only after** the rollback window ends and v1 is no longer needed.

For example: v1 understands a JSON payload with `id` and `amount`, and v2 adds an optional `currency` field. If v1 ignores unknown fields and the data contract allows it, rollback is easier. If v2 changes `amount` from a number to an incompatible object schema and writes production data, v1 may fail to read it after rollback; a verified down-migration plan is required or automatic rollback must be blocked.

**Migrations reduce risk; they are not a guarantee:** compatibility depends on ORMs, validation, API schemas, queries, events, and actual business behavior. Do not simply run a SQL schema migration and conclude rollback is safe.

### 9.2. Idempotency and request handling in the overlap zone

During cutover/rollback, retries may hit a different generation. If a request already wrote to the DB via v2 yet the client missed the response and retried into v1, the host must prevent executing the same transaction again.

Typical measures:

- Assign a clearly scoped request ID / idempotency key.
- Store transaction/deduplication state in a store shared across generations, not solely in plugin memory.
- Use a transactional outbox or durable protocol when DB and event consistency are required.
- Apply versioned events, ensuring old consumers tolerate event types emitted during the rollback window.
- Distinguish safe retries, compensation/sagas, and irreversible transactions.

A retry **is not** a rollback. Compensation (if business rules permit) must be designed and verified separately with auditing.

### 9.3. Stateful plugins and state handoff

If a plugin is a pure function over inputs, rollback is fairly straightforward. If the plugin keeps state in RAM, sessions, caches, connections, or actors, you must decide:

- **Sticky/pinned sessions**: old sessions continue on v1 until they end, new sessions go to v2; rollback may need to route new sessions back to a supported version.
- **State snapshot**: serialize state under a versioned schema and restore into another generation following a tested procedure.
- **Shared external state**: both v1 and v2 access a compatible store with locking/versioned transactions to avoid races.
- **Dual-run/shadow**: v2 receives copies of inputs to evaluate outputs without performing real side effects; do not arbitrarily shadow write transactions.
- **Irreversible state**: if v2 changed state in a way v1 cannot recover from, disable automatic rollback and fall back to an appropriate remediation runbook.

Never serialize objects from class loader v2 and deserialize them directly in v1 if class identities or Java schemas differ. Use DTOs/JSON/Protobuf or version-controlled durable formats rather than assuming Java `Serializable` solves hot swapping.

## 10. Readiness, health gates, canary, and decision criteria

There are two distinct kinds of checks:

- **Pre-cutover readiness**: plugin initializes cleanly, dependencies are available, API contract is valid, required connections work, and smoke tests cause no unintended side effects.
- **Post-cutover health**: the new version withstands live traffic with error rates, latencies, resource levels, and business success rates within defined thresholds.

A plugin can pass readiness and still fail upon receiving a rare request type or high concurrency. Therefore use a health window and rollback criteria defined **before deployment**.

Example policy (numbers are illustrative only; tune to real SLOs):

~~~text
PREPARE:
  validate artifact, API, dependencies
  warmup and smoke test isolated candidate

ACTIVATE:
  switch 5% eligible new requests to v2
  pin each request to its chosen generation

OBSERVE:
  compare v1/v2 error rate and latency
  inspect business outcomes, queues and saturation
  preserve v1 as rollback candidate

PROMOTE:
  increase traffic gradually when gates pass

ROLLBACK:
  route new requests back to v1 if gates fail
  drain already-started v2 requests
  retain evidence, preserve versioned state

RETIRE:
  close old generation only after rollback window,
  zero leases and dependency checks
~~~

**Canary** means two generations may accept new requests concurrently under weighted policies; the state machine must expand from a single active pointer to a **versioned/epoch-based routing table**, while each request still acquires **a single lease on one generation**. Requests in the same session/transaction may require sticky routing; random 5% per-message splitting is not always valid.

### Suggested telemetry and audit records

Record at a minimum:

- plugin ID, generation ID, artifact hash, config revision, host API version;
- generation routed for each request, idempotency key, and rollout/cutover epoch;
- in-flight count, new request count per generation, latency, errors, timeouts, cancellations;
- activation/rollback/retirement: timestamp, deciding actor or policy, reason;
- business effectiveness and data compatibility signals;
- uncleaned resource counts, class loader references, live background tasks.

Do not collect sensitive payloads solely for debugging unless necessary; control log access. Operational evidence must be sufficient to distinguish a new-plugin bug, an external dependency outage, and a bug in the cutover mechanism itself.

## 11. Class loader and resource boundaries during rollback

In Java, each plugin generation is typically loaded by its **own class loader** or an appropriate `ModuleLayer`. To keep v1 available for rollback, the host must intentionally retain references to its instance, loader, config, and required resources, while **preventing those references from leaking forever** once the rollback window ends.

### Share the API, isolate the implementation

Architectural example:

~~~text
Host / parent loader
└── Plugin API: com.example.spi.Formatter
     |
     +-- Generation v1 loader → FormatterImpl v1, deps v1
     |
     +-- Generation v2 loader → FormatterImpl v2, deps v2

Host router:
  ACTIVE → v2
  STANDBY → v1
  leases(v1) = 0
  leases(v2) = 3
~~~

The service interface must share the exact same **Class identity** between host and provider; avoid letting a child-first plugin loader define a separate API copy that triggers `ClassCastException` or `ServiceConfigurationError`. The host should not retain static references to v1 implementation classes after retirement if the class loader is meant to be garbage-collected.

### What does URLClassLoader.close() mean?

In Java 17, **`URLClassLoader.close()`** closes file/JAR resources opened by the loader per contract and stops supporting loading **new classes/resources** resolved by that loader; previously defined classes remain alive and accessible. **`close()` does not unload classes immediately** and does not automatically stop threads executing plugin code.

A class can stay alive if strong references remain to the `Class`, instances, thread context class loader, `ThreadLocal`, callbacks, listeners, scheduled tasks, or singleton caches. Never close a loader while a thread is actively loading classes through it, as the outcome of concurrent class loading during close is unspecified under the contract. Close only after all work and loading paths are controlled.

Similarly, **`ServiceLoader.reload()`** only clears the provider cache of that `ServiceLoader` object; it does not switch routes, wait for in-flight requests, undo side effects, or guarantee unloading a generation. Production hot replacement requires a host-side lifecycle manager.

### Controlled retirement order

1. Stop new admissions to the retiring generation.
2. Wait for leases to reach 0 or apply a confirmed cancellation policy.
3. Unregister listeners, timers, scheduled jobs, and generation-specific callbacks.
4. Invoke `plugin.stop()/close()` with an appropriate timeout/error policy, outside critical routing locks.
5. Close resources and the class loader once no loading operations remain.
6. Clear references in the router, registry, caches, and `ThreadLocal`; check for memory/classloader leaks.
7. Mark `CLOSED` and record cleanup/audit results. If cleanup fails, record **cleanup pending/failed** rather than falsely reporting a clean close.

In production, steps may have their own prepare/commit mechanisms and failure handling; the Java example only models the guard before marking `CLOSED`, without implementing full resource teardown.

## 12. Multi-instance, multi-thread, and cluster rollback

The Java example uses one monitor in one JVM. If an application runs multiple replicas, each replica holds its own active pointer, so updating a single instance does not produce a cluster-wide consistent cutover. You must define:

- **Rollout epoch/generation** in a central config store or control plane.
- Instances **prepare the same artifact and config**, reporting readiness individually before taking traffic.
- Load balancers/routers direct traffic by version, tenant/session, or deployment labels; avoid mixing incompatible results.
- **Fencing rules** when multiple actors issue activate/rollback commands, preventing a stale deploy command from overriding a newer directive.
- Health windows and metrics per replica/version so a single failing instance is not missed.
- Per-instance in-flight tracking; **global `inFlight=0`** may be concluded only with sufficient evidence across all relevant instances.
- When a partial rollout fails, a policy for halting or rolling back the already-switched portion and restoring traffic.

### Why is an atomic pointer not enough in a cluster?

`AtomicReference` creates an atomic selection **only inside the JVM that executed it**. It does not alter routing in other processes and does not synchronize side effects in databases. For rollback, drive it through the control plane and verify each instance or load balancer has applied the target version; handle disconnected replicas, command retries, and out-of-order commands.

When two controllers exist, every state transition command should carry **expected epoch** and **new epoch**; a controller commits only if the current state matches. This mechanism prevents a stale rollback from reverting the system to an unapproved version.

### Do not wait on long tasks inside the routing lock

Acquiring a lease and cutting over should be extremely brief. Never hold `synchronized(gate)` while:

- calling `plugin.processRequest`, `plugin.stop`, or `plugin.close`;
- running database queries, remote health checks, or network I/O;
- waiting on `Thread.join`, `Future.get`, or `inFlight` reaching 0;
- performing data migrations or data rollbacks.

Holding the lock too long can stall admission system-wide and cause deadlocks if a plugin calls back into the registry. The sample resolves this by **holding the gate only to swap pointers/counters/state**, while `Handler.handle` runs outside the lock.

## 13. Designing verifiable rollback

Reliable rollback must answer at least four groups of conditions:

1. **Is the old code still available?** Generation v1 is not `CLOSED`, artifacts and dependencies have not been deleted, and the instance remains ready/restartable.
2. **Is the data still compatible?** Database schemas, events, caches, and sessions from v2 can be handled by v1 or have a verified recovery path.
3. **What happens to in-flight requests?** How will remaining open v2 leases finish, cancel, or checkpoint? Could they still cause dangerous side effects once traffic returns to v1?
4. **Have routes actually switched?** Routers and load balancers on every replica use the right epoch/generation, with no node quietly admitting new requests to v2.

If rollback prerequisites are unmet, **do not blindly activate v1 just because v2 health looks bad**. You may need to pause traffic, switch to read-only mode, ship a compatible v2 patch, execute restore/compensation per runbook, or orchestrate a multi-step rollback. Clearly report that rollback was blocked due to unsafe data schema, state, or in-flight status.

### Automatic vs manual rollback

- **Automatic** fits when health gates give trustworthy signals, route reversal is tested, state is compatible, and there are no irreversible side effects requiring human judgment.
- **Manual** fits sensitive transactions, breaking migrations, third-party coordination, or high-impact task cancellations.

Either way, every rollback must have a reason code, source–target version/epoch, audit trail, and post-rollback continuation plan. Avoid endless auto-rollback/auto-promote oscillation from flapping health; use cooldowns and retry policies.

## 14. Common mistakes

| Symptom | Possible cause | Prevention / fix |
| --- | --- | --- |
| Old requests fail right after cutover | Closed v1 instance/loader before leases finished | Pin requests to generation, drain before closing |
| `inFlight` hits 0 while task still runs | Released lease when returning `Future` instead of on completion | Tie lease to actual completion, including cancellation |
| New requests still enter v1 after cutover | Uncoordinated reading of `current` and incrementing refcount | Share the same admission gate or standard CAS/refcount protocol |
| Cannot roll back despite v1 artifact existing | Already stopped/closed resources or deleted v1 state | Keep v1 `STANDBY` during rollback window |
| Route rollback succeeds yet v1 hits DB errors | v2 wrote incompatible schema/data | Expand–contract, versioned payloads, backward-compatibility tests |
| Retries create duplicate transactions | Request retried across v1/v2 without a shared key | Shared idempotency keys and deduplication store |
| Drain hangs indefinitely | Long streams/jobs, orphan callbacks, or lease leaks | Deadlines, per-generation metrics, cancellation/checkpoint policy |
| Used `ServiceLoader.reload()` thinking hot swap happened | Reloading cache does not change routing/lifecycle | Manage generations, loaders, and admission separately |
| OOM/metaspace grows after repeated swaps | `ThreadLocal`/listeners/class caches retain old loaders | Clean up all references, test unloading and memory leaks |
| Stale rollback command overwrites new deploy | Missing epoch/fencing | Versioned control-plane commands and expected-state checks |
| Plugin v2 enabled before readiness | Routing admits requests before dependencies are ready | Prepare/warmup and health gates before cutover |
| Rollback hides error yet side effects persist | Assuming rollback restores all data | Separate route rollback from compensation/DB restore |

### Things you should never do

- Directly replace singleton object v1 with v2 and immediately drop all v1 references while old requests still use it.
- Call `plugin.stop()` while holding a lock that in-flight requests need to finish or release their leases.
- Use a multi-second sleep as proof that `inFlight` reached 0; measure with counters and states that have clear ownership.
- Force a running request to switch business logic from v1 to v2 mid-execution without a state transfer protocol.
- Treat code rollback as the ability to roll back all transactions, events, and schemas.
- Keep every old plugin loader forever “just to be safe for rollback”; set a rollback TTL and retirement procedure.
- Use `Thread.stop` or `URLClassLoader.close` to forcibly kill in-flight request execution.

## 15. Testing strategy before release

A good hot-replacement system tests concurrency and failure, not just the happy path:

1. **Concurrent admission and cutover:** multiple threads acquire while the pointer swaps; every lease belongs to a valid generation, counters never go negative, and no new request enters a generation whose admission stopped after commit time.
2. **Long-held v1 request:** cut over to v2 while `v1.inFlight > 0`; v1 must not become `CLOSED` before leases release.
3. **Late-completing Future:** async requests keep counting toward `inFlight` until completion; exception/cancellation callbacks never double-release.
4. **Pre-cutover activation failure:** v1 stays `ACTIVE`, candidate is cleaned up, no route points to an unready generation.
5. **v2 fails after cutover:** roll back to live v1; new requests use v1; already-leased v2 requests follow an explicit drain/cancel policy.
6. **Rollback while v1 is still `DRAINING`:** the controller must have rules allowing re-admission or blocking if v1 resources were partially closed.
7. **Rollback blocked by incompatible schema:** do not silently switch to v1; emit status and transition the application to a recovery strategy.
8. **Two-controller race:** two activate/rollback commands with different epochs; the stale command is rejected.
9. **Drain timeout and leaked lease:** metrics, alerts, and escalation policies; never falsely report zero when tasks actually remain.
10. **Resources after retirement:** thread pools, listeners, timers, class loaders, JAR handles, and references are released with no persistent memory leaks.
11. **Cross-generation idempotency:** client retries after timeout do not create duplicate side effects when routes change.
12. **Canary and sticky sessions:** accurate version selection ratios and consistent policy across related requests in the same session.

For concurrency tests, use `CountDownLatch`, `CyclicBarrier`, `ExecutorService`, and controlled timeouts to induce rare interleavings, rather than relying purely on `Thread.sleep`. When testing plugins that might hang, run them in a worker JVM/process so the entire test suite does not stall.

Minimum rollback testing covers two sides: **route/lease state** and **data compatibility/side effects**. Passing a pointer-switch test alone is insufficient to declare production rollback ready.

## 16. Checklist when preparing plugin replacement

- **Generation identity**: each load has its own ID, artifact hash, config, and resource scope.
- **Prepare**: verify dependencies, API type identity, permissions, compatibility, and readiness before accepting load.
- **Admission**: new requests receive leases per routing policy atomically with cutover.
- **Pinning**: already-started requests continue using their assigned generation.
- **Async lifecycle**: leases end only when all underlying work completes or cancels with confirmation.
- **Drain**: old generation stops accepting new work yet keeps resources while `inFlight > 0`; enforce timeouts and escalation.
- **Rollback candidate**: keep v1 `STANDBY` long enough without closing/GC-ing before the rollback window expires.
- **Rollback guard**: check whether schemas/data/events/caches/sessions are compatible with v1, and how v2 side effects are handled.
- **Health gates**: define error thresholds, latency, business metrics, canary rules, and audit logging before rollout.
- **Concurrency/cluster**: never use a local pointer to infer cluster-wide cutover; use epochs/fencing.
- **Retire**: once no leases or rollback dependencies remain, cancel callbacks/timers and close resources outside routing locks.
- **Observability**: metrics and logs include generation ID, request ID, state, cutover epoch, errors, and drain time.
- **Tests**: rehearse real cutover + rollback under load with compatible data.

**Conclusion:** Safe plugin replacement is **managing generation lifecycles and the requests holding them**, not merely loading new classes. Use leases to pin requests, atomic cutovers to switch new requests, bounded draining to preserve in-flight requests until completion, and guarded rollback to route traffic back to a compatible version. In stateful systems, **data and side-effect rollback capability must be designed before enabling v2**, and cannot be conjured simply by swapping a pointer after an incident occurs.

## References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): class/loader identity and class-loading contract.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()` and limitations regarding already-loaded classes.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): cache/reload, class loader, and provider discovery.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): releasing leases with try-with-resources.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion stages and `whenComplete` for async lifecycles.