# Cancelling Futures/Subscriptions vs. Server-Side Work in Cassandra Java Driver

> **Chapter:** Async and Reactive  
> **Focus:** When a Java application cancels a `CompletableFuture` or `Subscription`, what stops on the **client** side, what work can still run on **Cassandra coordinators/replicas**, and how to design deadlines, paging, idempotency, backpressure, metrics, and reconciliation. Examples target Java 17 + Apache Cassandra Java Driver **4.x** (aligned with 4.17–4.19) and Reactor 3.x where needed. Run labs only in authorized keyspaces and clusters.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between **cancelling client interest in a result** and **halting query execution** on Cassandra.
2. Distinguish `CompletionStage<AsyncResultSet>`, `CompletableFuture.cancel(...)`, dependent stages, `CancellationException`, and actual CQL outcomes.
3. Explain why `cancel(true)` is **not** an interrupt signal to Cassandra JVM threads.
4. Identify race windows: queued requests, unsent, sent, coordinator in progress, ACK arrived, and future already completed.
5. Use `AsyncResultSet.currentPage()` / `fetchNextPage()` to **stop fetching subsequent pages once the user no longer needs them**.
6. Understand that `executeReactive()` is **cold, unicast, and single-subscription-only**, and call `Subscription.cancel()` / Reactor `Disposable.dispose()` appropriately.
7. Contrast reactive **backpressure for SELECT paging** with concurrency/rate limits for **writes**.
8. Choose HTTP, service, and `basic.request.timeout` deadlines without treating cancellation as proof that "the write never happened."
9. Design idempotency keys and audit/reconciliation for cancelled, timed-out, or unacknowledged writes.
10. Observe `pool.orphaned-streams`, `pool.available-streams`, `pool.in-flight`, `cql-client-timeouts`, and Cassandra read/write latency.
11. Complete a CQL/Java async/reactive lab and explain the distinction between **cancellation outcome** and **data state**.

**Context in `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra stores wide-column data across natural replicas selected by partition key/token, replication factor (RF), consistency level (CL), and read/write paths. `Future`, reactive cancellation, and stream backpressure operate strictly on the client/driver side; they **do not alter RF, CL, compaction, repair, or already-processed mutations**.

## 2. One Rule More Important Than Any Line of Code

**Cancelling a Future or subscription changes whether the application *still wants the result*; it is not confirmation that Cassandra *stopped executing*.** Over the standard CQL native protocol v4/v5, there is no `CANCEL QUERY` command guaranteed to halt an already-sent query. The driver can stop tracking the request, avoid issuing further page requests, or discard a late response. Coordinators and replicas may still be reading SSTables, writing to commit logs/memtables, or returning responses.

~~~text
HTTP client             Java Driver               Cassandra coordinator/replicas
     |                       |                               |
     |---- GET/POST -------->|                               |
     |                       |--- QUERY/EXECUTE ------------>|
     |                       |                               | executing
     X disconnect            |                               |
     |                       |                               |
     |                  cancel Future/Subscription           |
     |                       X stops waiting for result      |
     |                       |                               | may still continue
     |                       |<---- late RESULT / ACK -------|
     |                       |   may be discarded            |
     |                       |                               |
     |               Cannot infer: server rolled back        |
~~~

This is grounded in [Speculative execution — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/): when the driver "cancels" a losing execution, it **ignores the response** if it arrives later; Cassandra does not support cancelling an in-flight request in that sense. [Native protocol v5](https://cassandra.apache.org/doc/latest/cassandra/reference/native-protocol.html) defines messages like `QUERY`, `EXECUTE`, `BATCH`, and `RESULT`, with no standard `CANCEL` frame for running queries.

### 2.1. Four Things Commonly Lumped Together as "Cancel"

| Mechanism | Reliable effect | What must **NOT** be inferred |
|---|---|---|
| `CompletableFuture.cancel(false)` | Completes the Future as cancelled if not already complete | Cassandra stopped reading/writing |
| `CompletableFuture.cancel(true)` | In JDK `CompletableFuture`, `mayInterruptIfRunning` cannot kill server work | Server thread was interrupted |
| Reactive `Subscription.cancel()` | Subscriber stops requesting/receiving items; driver stops requesting further pages as appropriate | All sent CQL statements were aborted by the server |
| Driver `DriverTimeoutException` | Client ran out of wait budget for one logical request | Mutation rolled back or no replica applied it |
| Not calling `fetchNextPage()` | **Does not initiate** subsequent page requests in the async flow | Already-sent query/page was recalled |

Separate two questions: **"Was the client-side result cancelled?"** and **"Did the effect occur in Cassandra?"**. The first can be checked via the Future/subscription; the second requires data checks, traces/metrics, consistency awareness, and proper auditing.

### 2.2. Cancellation Is Not a Transactional Rollback

~~~text
Client cancel ACK                     Does NOT prove:
  [x] client stopped caring             [ ] mutation was not applied
  [x] may skip fetching further pages   [ ] all replicas halted
  [x] future/stream emits no result     [ ] batch rolled back atomically
                                        [ ] TTL/tombstone was not written
                                        [ ] subsequent retry is always safe
~~~

For critical writes—orders, payments, inventory updates, CDC offsets—if cancellation occurs after dispatch, treat the result as **UNKNOWN_OUTCOME** until reconciled.

## 3. Lifecycle of an Asynchronous Request

~~~text
T0: Application builds statement, deadline/CL/idempotence
T1: session.executeAsync(statement) called
T2: Driver passes request through throttler/queue (if configured)
T3: Driver picks coordinator, borrows connection/stream ID
T4: Request frame written to network
T5: Coordinator executes, contacts natural replicas
T6: Replicas respond; coordinator aggregates per CL
T7: Response frame returns to driver, decoded
T8: CompletionStage<AsyncResultSet> completes
T9: Application processes rows / may call fetchNextPage()
~~~

Cancellation can hit at **any** step T1–T9:

- **Before T3/T4:** if the driver receives cancellation before sending, network/server work may be avoided. Races still exist, and propagation into the throttler **depends on driver version**.
- **After T4, before T8:** the server may keep executing; the client may miss the final outcome.
- **After T8:** the Future already completed; `cancel` normally returns `false` and **does not undo the result**.
- **After T9, with more pages:** the first-page request already finished. Stopping there avoids **unsent page requests**; any already-sent page request may still be running.

### 3.1. Why Exact Cancellation Timing Is Not Fully Observable

Operations span the caller JVM, driver queues, Netty I/O threads, TCP buffers, coordinators, and replicas, so there is no single clock saying "sent / writing / done." Checking `isCancelled()` inspects one Future's state, **not a server execution checkpoint**. Even if the client observes cancellation before any response, the server can finish executing right afterward.

### 3.2. Client Pre-Send vs. Post-Send Classification

| Stop point | What we know | What to do |
|---|---|---|
| Before calling `executeAsync` | This API never sent the request | Avoiding dispatch is the cleanest stop |
| Waiting in throttler | May not be sent yet, but verify whether cancel propagated | Check driver version/throttle metrics; don't assume |
| Verified not written to network | Coordinator never received this message | May record NOT_SENT only with **reliable evidence** |
| Frame sent, no response yet | **Unknown** whether mutation applied | Record UNKNOWN_OUTCOME if it's a write |
| Response arrived, Future completed | Driver knows request outcome per CL | Handle result normally; late cancel changes nothing |
| Reactive emitted several rows | Emitted rows reached the client | Do not assume all pages were read |

## 4. `CompletionStage` and `CompletableFuture`: Two Different Abstractions

Java Driver 4.x returns `CompletionStage<T>` instead of exposing a freely mutable Future. API:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import java.util.concurrent.CompletionStage;

CompletionStage<AsyncResultSet> stage =
    session.executeAsync(statement);
~~~

Per the [Java Driver 4.x FAQ](https://apache.googlesource.com/cassandra-java-driver/+/refs/tags/4.18.1/faq), `CompletionStage` steers callers toward **composition**, avoiding arbitrary external completion of driver-owned futures. `toCompletableFuture()` exists for JDK interop, **not** as a contract that cancellation halts the server.

### 4.1. Cancelling from the Application Layer

~~~java
import java.util.concurrent.CompletableFuture;

CompletionStage<AsyncResultSet> stage =
    session.executeAsync(statement);

CompletableFuture<AsyncResultSet> future =
    stage.toCompletableFuture();

boolean changed = future.cancel(false);

System.out.println("future cancelled now? " + changed);
System.out.println("future.isCancelled = " + future.isCancelled());
~~~

**Meaning of `changed=true`:** the Future was incomplete and transitioned to cancelled. **Does NOT mean:** Cassandra received a "STOP" message or the mutation didn't run. If the Future already completed, `changed=false`. A race exists between checking `isDone` and calling `cancel`, so rely on the actual cancel/observe outcome rather than assuming `if (!isDone())` guarantees success.

### 4.2. `cancel(true)` Does Not Interrupt Cassandra

~~~java
boolean changed = future.cancel(true);
~~~

In JDK's `CompletableFuture`, `mayInterruptIfRunning` **does not interrupt a worker thread** the way `FutureTask` on a thread pool might. With Cassandra, the coordinator runs in **another JVM**, so a client-side boolean flag certainly cannot interrupt a server thread. If your app uses a *different* framework `Future`, cancel/interrupt semantics belong to that framework; always check the owning abstraction.

### 4.3. `CancellationException` Is a Client Outcome

~~~java
future.whenComplete((result, error) -> {
    if (error == null) {
        System.out.println("Client received result");
    } else if (error instanceof java.util.concurrent.CancellationException) {
        System.out.println("Cancelled at client boundary");
    } else {
        System.out.println("Request failed: " +
            error.getClass().getSimpleName());
    }
});
~~~

In chains, errors may be wrapped in `CompletionException`; unwrap carefully for classification while keeping full stack/causes in internal logs. **Cancellation** is not `ReadTimeoutException`, `WriteTimeoutException`, `DriverTimeoutException`, or a transaction rollback error.

### 4.4. Completed Futures Cannot Be "Undone"

~~~java
CompletableFuture<String> done =
    CompletableFuture.completedFuture("PAID");

System.out.println(done.cancel(false));  // false
System.out.println(done.join());         // PAID
~~~

This runs in pure JDK without Cassandra. It shows cancellation is a **state transition on an incomplete Future**, not a reversal of finished results or backend data.

## 5. Cancelling a Dependent Stage Differs from Cancelling the Root Request

With `CompletableFuture`, a callback graph can look like:

~~~text
                          executeAsync(CQL)  [root]
                                  |
                    +-------------+-------------+
                    |                           |
              thenApply(parse)             whenComplete(metrics)
                    |
             thenCompose(next)
                    |
              HTTP response stage
                    |
              Client disconnected
                    |
                cancel(false)
~~~

**Cancelling a downstream stage does not propagate upstream to every parent stage by default** in the JDK, and certainly does not propagate to Cassandra. Two separate scopes exist:

1. **Graph cancellation:** which stages are marked cancelled and which downstream callbacks skip running.
2. **Driver request cancellation:** whether and when the driver stops tracking the root request.

### 5.1. Pure JDK Experiment

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> upstream = new CompletableFuture<>();
CompletableFuture<Integer> downstream =
    upstream.thenApply(String::length);

downstream.cancel(false);

System.out.println(downstream.isCancelled()); // true
System.out.println(upstream.isCancelled());   // false

upstream.complete("abc");
System.out.println(upstream.join());          // abc
~~~

This experiment proves **cancelling a child does not cancel its parent**. If an HTTP service only cancels a downstream `thenApply` while the upstream `executeAsync()` stays alive, the driver still receives the response. **Never design around cancellation propagation not guaranteed by your framework/JDK.**

### 5.2. Keeping Request-Owned Lifecycle Handles

A controller/service should maintain:

~~~text
RequestContext {
  cancelled flag
  overall deadline
  root CompletionStage (if still owned)
  paging loop state
  in-flight operations count
  business operation ID if write
}
~~~

When an HTTP client disconnects:

- Mark the context so it no longer needs a response.
- Stop issuing **unstarted page requests or follow-up operations**.
- Cancel application-level work safely according to the framework's **API contract**.
- For already-sent CQL, never report "DB halted" or "write definitely failed."
- Clean up subscriptions, timers, log correlation, and owned resources.

With Spring WebFlux/Reactor, cancellation can propagate across framework-managed operators, yet **never assume every transformed `CompletionStage` cancels automatically**. Write integration tests for your exact version and reactive adapter.

### 5.3. `completeOnTimeout` and `orTimeout`

~~~java
CompletableFuture<AsyncResultSet> f =
    session.executeAsync(statement).toCompletableFuture();

f.orTimeout(1, java.util.concurrent.TimeUnit.SECONDS);
~~~

`CompletableFuture.orTimeout` completes **that Future** with `TimeoutException` if still incomplete; `completeOnTimeout` completes it with a **fallback value**. Neither sends a **server-side CANCEL**. Applying them directly to a driver-supplied Future can also interact with internal lifecycle/cancellation hooks; do not equate them with `basic.request.timeout`. Prefer **application-level deadlines**, configured driver request timeouts, and reviewed tracing.

**Extremely dangerous for writes:** `completeOnTimeout(fakeSuccess, ...)` can trick the HTTP layer into reporting write success merely because the client substituted a default value. For reads, cached fallbacks are acceptable only if business policy explicitly discloses stale/fallback data.

## 6. Native Protocol, Stream IDs, and Late Responses

### 6.1. What Is a Stream ID?

Over each CQL native-protocol connection, the driver multiplexes parallel requests. Each message carries a **stream ID** to match responses to requests:

~~~text
TCP connection to coordinator A

  stream 5  -> SELECT partition P
  stream 9  -> INSERT partition Q
  stream 13 -> SELECT partition R
                   |
            Responses can arrive out of send order.
            Stream ID header maps each response to its request.
~~~

When a client cancels an **already-sent** request, the driver must still account for a **late-arriving response**. It cannot arbitrarily reuse that stream ID right away for a new request, or the old response could be misattributed to the new request.

### 6.2. Orphaned Streams

~~~text
T0:  stream 9 -> request A sent
T1:  A cancelled, or another speculative attempt wins
T2:  driver no longer cares about A's outcome
T3:  stream 9 becomes orphaned/pending until late response
T4:  response A arrives -> driver can reclaim stream 9
     or connection recycles per configured thresholds
~~~

See [Speculative execution — Stream ID exhaustion](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/): if many abandoned requests await late responses, `pool.orphaned-streams` rises, `pool.available-streams` drops, and the driver may **close and reopen connections**. Looking only at API-level cancellation hides this pool/churn cost.

### 6.3. Heavy Cancellation Does Not Retroactively Cut Dispatched Load

If an app fires 10,000 SELECTs/s and cancels 80% because users scroll fast:

| Event | Likely consequence |
|---|---|
| Many queries already passed T4 | Cassandra still processes what was dispatched |
| Subscribers stop requesting pages | Cuts **future unfetched pages** |
| Orphaned stream IDs climb | Pool loses capacity; connections may recycle |
| HTTP response rate appears lower | Does not prove server CQL QPS dropped proportionally |
| Retries / speculative attempts fire | Can multiply coordinator messages even further |

The real fix is **not firing unnecessary queries in the first place**: debounce, coalesce, cache, bound concurrency, query by partition key, and cap pages/rows. Cancel is an emergency brake after dispatch, not a substitute for admission control.

### 6.4. Closing Sockets to "Kill a Query"?

Never close a shared connection or the entire `CqlSession` just to cancel one CQL query. Doing so:

- Disrupts unrelated requests sharing that connection/session.
- Does not guarantee the coordinator aborts an already-received mutation.
- Triggers reconnect churn, prepared-statement re-prepares, and cascading failures.

`CqlSession` should be **reused** across requests and closed cleanly during application shutdown. A per-request `CancellationToken` must never call `session.close()`.

## 7. How Cassandra Work Continues After Cancellation

### 7.1. Write Path

~~~text
Client ---> coordinator
              |
              +-- resolves token / natural replicas
              +-- sends mutation to replicas
              |      |
              |      +-- commit log
              |      +-- memtable update
              |      +-- ACK when CL satisfied
              |
              +-- ACK/timeout back to client

Client cancellation can occur while any step is running.
~~~

If the app calls `cancel` before receiving an ACK, **one or more replicas may still apply the mutation**. The write may later satisfy CL or not; all you know is that the app **never received confirmation** on that tracked request. Never deduce "not written" or "definitely written" solely from `isCancelled`.

### 7.2. Read Path

The coordinator may be:

- Reading memtables and SSTables for the partition range.
- Merging cell versions by timestamp/TTL/tombstones.
- Contacting multiple replicas/digests to satisfy CL.
- Scanning extra SSTables due to tombstone density or wide partitions.
- Returning the already-computed first page; subsequent pages are separate requests.

If the client cancels after sending the first-page request, **the server may still finish computing the first page**. With async paging, **not calling `fetchNextPage()`** avoids launching later page requests. Reactive demand cancellation similarly curbs extra pages, without "rewinding" work already done.

### 7.3. CQL Write ACKs, Commit Logs, and Compaction

Even if an ACK returned before cancellation—or after—background storage work such as **memtable flushes, compaction, and replication maintenance/repair** continues. Neither ACKs nor client cancellation **tell storage layers to stop work on Java's command**.

**Separate three lifecycles:**

- **CQL request lifecycle:** individual read/write/ACK per CL.
- **Storage lifecycle:** memtable → SSTable → compaction, tombstone reclamation.
- **Replica convergence:** hints/repair/anti-entropy per topology/conditions.

Never treat cancellation as a way to "erase a write from disk" or "halt compaction."

## 8. Uncertain Write Outcomes and Idempotency

### 8.1. Order-Placement Case

~~~text
1. POST /orders receives order_id=O-123, tenant=T-1
2. Java sends INSERT ... order_id=O-123, status=NEW
3. HTTP client disconnects
4. Java cancels future; receives no ACK
5. Cassandra may have already saved row O-123
6. HTTP client retries POST
~~~

If the second POST generates a **different `order_id`**, two rows can appear, and side effects like inventory deduction or emails can duplicate. Therefore:

- Generate a stable **business operation ID / idempotency key** at the boundary.
- Design primary keys, event versions, and retry semantics for reconciliation.
- Use conditional updates/versions/outboxes/deduplication where business accuracy demands it.
- For client-cancelled writes, record `UNKNOWN_OUTCOME` or a reconciliation event—never mark it "FAILED, safe to retry."

### 8.2. The Idempotent Flag Does Not Make a Write Idempotent

~~~java
BoundStatement write = insertPrepared.bind(
        tenantId, orderId, "NEW")
    .setIdempotent(true);
~~~

Use `setIdempotent(true)` only after **verifying** that replaying the exact PK, values, timestamps, TTLs, and all business side effects is safe. Never set it to `true` for COUNTER increments, LIST appends, per-retry random UUIDs, or external side effects. The driver uses this flag to allow retries/speculative execution on certain error paths; the flag is **not** a transaction or deduplication mechanism.

### 8.3. Never Infer "Cancel = Zero Write" from an Immediate SELECT

Re-reading at CL `ONE` right after cancelling a write and seeing **no row** does not prove no replica wrote. Possible reasons:

- Mutation is still in flight at coordinator/replicas or awaiting replication.
- The queried replica does not yet hold the latest version.
- Tombstones, TTLs, or read conditions affect visibility.
- Query targeted the wrong partition, day bucket, or CL.

Reconciliation must use an **appropriate CL**, check event logs / sources of truth, compare versions/timestamps, and respect convergence windows; a single `ONE` read is **one observation**, not final proof.

### 8.4. Wrong vs. Right Examples

**Wrong:**

~~~java
future.cancel(true);
// "Since we cancelled, the INSERT definitely doesn't exist."
// generateNewOrderIdAndRetry();
~~~

**Right in principle:**

~~~java
future.cancel(false);
// Mark outcome as unknown if write had possibly been sent.
// Do not invent a new business key.
// Reconcile orderId against authoritative business state.
// Retry only via reviewed idempotency policy and within deadline.
~~~

This is **operational pseudocode**: the actual APIs to record state and reconcile live outside the Java Driver and depend on application architecture.

## 9. Async Paging: Where to Stop to Avoid Unstarted Work

In Java Driver 4.x, `session.executeAsync` returns an `AsyncResultSet` for **one page**. Iterating `currentPage()` never fetches the next page automatically; the application explicitly calls `fetchNextPage()`. See [Async paging — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/).

### 9.1. Reading One Page

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

CompletionStage<AsyncResultSet> first =
    session.executeAsync(statement);

first.thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getUuid("event_id"));
    }
    // Do not call fetchNextPage():
    // stops at the current page, even if page.hasMorePages() is true.
});
~~~

If the code does not call `fetchNextPage()`, **later pages are never requested** in this flow. However, the first page was already requested before `first` completed. **Do not** infer the server read zero data for the first page or left SSTables untouched.

### 9.2. Stopping on a Cancellation Flag

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

static CompletionStage<Integer> consumePages(
        AsyncResultSet page,
        AtomicBoolean cancelled,
        int previouslySeen) {

    int seen = previouslySeen;
    for (Row row : page.currentPage()) {
        if (cancelled.get()) {
            return CompletableFuture.completedFuture(seen);
        }
        // Counting only; business side effects inside callbacks
        // need their own idempotency controls if present.
        seen++;
    }

    if (cancelled.get() || !page.hasMorePages()) {
        return CompletableFuture.completedFuture(seen);
    }

    final int nextSeen = seen;
    return page.fetchNextPage()
        .thenCompose(next ->
            consumePages(next, cancelled, nextSeen));
}
~~~

Invoking from a service:

~~~java
AtomicBoolean cancelled = new AtomicBoolean(false);

CompletionStage<Integer> consumed =
    session.executeAsync(statement)
        .thenCompose(first ->
            consumePages(first, cancelled, 0));

// HTTP disconnect handler / job stop event:
cancelled.set(true);

consumed.whenComplete((count, error) -> {
    if (error != null) {
        System.err.println("Async read failed");
    } else {
        System.out.println("rows consumed before stop=" + count);
    }
});
~~~

**Important concurrency note:** a `fetchNextPage()` call may already have fired at the exact instant another thread flipped the flag. `AtomicBoolean` gives visibility and cross-thread coordination, **not atomicity** between checking the flag and sending a network request. Thus the code only promises **"will not deliberately start more pages after observing `cancelled=true`,"** not "zero messages remain in flight after cancel."

### 9.3. Cancelling the Future of an In-Flight Page Fetch

~~~java
CompletionStage<AsyncResultSet> nextStage =
    page.fetchNextPage();

CompletableFuture<AsyncResultSet> nextFuture =
    nextStage.toCompletableFuture();

nextFuture.cancel(false);
~~~

The next-page future transitions to cancelled, yet the **already-sent page request may still run**. With normal async paging, there is no API to "abort the whole SELECT on the coordinator and roll back read I/O." Combine with a cancellation flag so **no further pages are requested**.

### 9.4. Page Size and LIMIT Are Not the Same Concept

~~~java
BoundStatement read = prepared.bind(tenantId, day)
    .setPageSize(100)
    .setIdempotent(true);
~~~

`page-size=100` is a suggested page size, not the total result row count. If a user needs at most 50 rows, add **CQL `LIMIT 50`** and/or enforce an upper-layer API cap. With wide partitions and tombstones, even a 100-row page can trigger a large scan. When downstream cancels because it stopped reading, **never keep fetching all 100 pages "to clean up the server."**

### 9.5. When to Prefer Reactive Over Manual Async Paging

| Need | Async `fetchNextPage` | Reactive subscription |
|---|---|---|
| Explicit per-page processing | Well-suited | Less direct |
| Stop before the next page | Check flag before `fetchNextPage` | Cancel downstream demand |
| Feed a reactive HTTP stream | Needs an adapter | Fits naturally |
| User wants N rows | Manual loop/counter | `take(N)` can cancel upstream |
| Pace write concurrency | Manage futures/semaphores manually | Reactor `flatMap(..., concurrency)` |
| Know server halted upon cancel | **Not guaranteed** | **Not guaranteed** |

## 10. Reactive CQL: Executes Only Upon Subscription

Java Driver 4.x provides `CqlSession.executeReactive`, returning `ReactiveResultSet` (a `Publisher<ReactiveRow>`). For historical project reasons, reactive types live under `com.datastax.dse.driver.api.core.cql.reactive`, **yet still support Cassandra OSS**.

~~~java
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;

ReactiveResultSet publisher =
    session.executeReactive(statement);

// Not subscribed yet => no CQL sent by this publisher yet.
~~~

Per [Reactive Style Programming — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.1/core/reactive/), the default publisher is:

- **Cold:** does not execute CQL until subscribed.
- **Unicast:** one source for one consumer stream.
- **Single-subscription-only:** the same `ReactiveResultSet` cannot be subscribed twice.

### 10.1. Timeline Differs Completely from `executeAsync`

~~~text
executeAsync(statement):
  method call -> logical request begins
  returns CompletionStage -> await response / fetch pages

executeReactive(statement):
  method call -> publisher object (no CQL sent yet)
  subscribe -> execution starts
  request(n) -> subscriber demands at most n items
  cancel -> stops consumption / upstream demand
~~~

Therefore, creating a reactive publisher and **never subscribing** sends zero CQL to Cassandra. That is a much surer way to "avoid unnecessary requests" than cancelling after dispatch. Once **subscribed and dispatched**, however, the same no-server-kill rule applies.

### 10.2. Creating a Publisher Without Executing It

~~~java
ReactiveResultSet ignored = session.executeReactive(
    "SELECT release_version FROM system.local");

// Zero subscribers: zero CQL execution from ignored.
// Creating the object does not start the query.
~~~

Common bug in reactive writes:

~~~java
// WRONG: doOnNext only constructs ReactiveResultSet and discards it.
Flux.just(insertStatement)
    .doOnNext(session::executeReactive);
// Without subscribing to the ReactiveResultSet,
// this INSERT never executes in the pipeline above.
~~~

**Right way:** make the inner publisher part of a subscribed chain:

~~~java
Flux.just(insertStatement)
    .flatMap(s -> Flux.from(session.executeReactive(s)))
    .then();
// This is only a Mono<Void>; it must still be subscribed/returned to framework.
~~~

Again, **the entire chain** must be subscribed to (for instance by a reactive HTTP framework). Creating a `Mono<Void>` and discarding it still executes zero writes.

## 11. Reactive `Subscription.cancel()`: Stops Rows, Does Not Kill the Server

### 11.1. Pure Reactive Streams Code

~~~java
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;

ReactiveResultSet source = session.executeReactive(readStatement);

source.subscribe(new Subscriber<ReactiveRow>() {
    private Subscription subscription;
    private int seen;

    @Override
    public void onSubscribe(Subscription s) {
        subscription = s;
        s.request(1); // One row at a time.
    }

    @Override
    public void onNext(ReactiveRow row) {
        seen++;
        System.out.println(row.getUuid("event_id"));
        if (seen >= 2) {
            subscription.cancel();
        } else {
            subscription.request(1);
        }
    }

    @Override
    public void onError(Throwable error) {
        System.err.println(
            "Reactive request failed: " +
            error.getClass().getSimpleName());
    }

    @Override
    public void onComplete() {
        System.out.println("All requested results completed");
    }
});
~~~

In Reactive Streams, `cancel` normally **does not trigger `onComplete`**; it is a subscriber-side termination decision letting upstream stop. Callbacks above may execute on driver I/O threads, so **never put blocking I/O or heavy CPU inside `onNext`** in production. This example merely prints 2 rows in a lab; real apps offload processing to appropriate executors/schedulers.

### 11.2. Cancelling After the Query Was Already Sent

~~~text
subscribe()
    |
onSubscribe -> request(1)
    |
driver sends SELECT for first page
    |
coordinator executing
    |
onNext(row1)
    |
subscriber.cancel()
    |
driver has zero remaining demand
    |
already-sent first-page CQL MAY STILL finish
~~~

**Distinguish "no more demand" from "no more server work."** Cassandra's native protocol does not transmit per-subscriber `request(1)`/`cancel` commands to pause SSTable scanning; the driver uses backpressure to decide **when to fetch subsequent pages**.

### 11.3. Do Not Expect `onComplete` as an ACK After Cancelling

If a subscriber cancels on the second row, `onComplete` may never run even though **two rows were delivered**. Never treat "missing `onComplete`" as a failed query; it is often the normal result of client-initiated termination.

Conversely, `onComplete` on a reactive write (with zero rows) is the client's signal that **the Publisher completed successfully** per CL/request semantics—not a guarantee that downstream compaction or repair finished.

### 11.4. Never Subscribe to the Same `ReactiveResultSet` Twice

~~~java
ReactiveResultSet rs = session.executeReactive(readStatement);

Flux<ReactiveRow> first = Flux.from(rs);
Flux<ReactiveRow> second = Flux.from(rs);

// Subscribing to first then second on the same rs => second can throw
// IllegalStateException: single-subscription-only publisher.
~~~

If intentional retry/re-subscribe is needed:

~~~java
Flux<ReactiveRow> freshEachTime =
    Flux.defer(() -> Flux.from(
        session.executeReactive(readStatement)));
~~~

`Flux.defer` creates a new `ReactiveResultSet` per subscription. That also means **each subscription issues a fresh request**; never attach `retryWhen` carelessly to non-idempotent writes. For multi-consumer reads, consider size-bounded sharing/caching rather than caching giant tables onto the heap.

## 12. Reactive Backpressure and `take(N)`

### 12.1. Backpressure Is Not a Direct Wire Protocol to Cassandra

Reactive Streams provides `Subscription.request(n)` for downstream demand. **The CQL native protocol has no per-subscriber `REQUEST_N_ROWS` frame**, so the driver implements backpressure primarily by:

1. Holding back `onNext` emissions when subscriber demand is 0.
2. Requesting the **next CQL page** only when needed.
3. Skipping further page requests once the subscriber stops/cancels (except pages already in flight/racing).

For large SELECTs, this **paces page-fetch rates**, without forcing the server to read strictly 1 row for `request(1)`. The first page may already contain dozens or hundreds of rows computed by the server.

### 12.2. Reactor `take(2)`

~~~java
import reactor.core.publisher.Flux;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import java.time.Duration;
import java.util.List;

List<ReactiveRow> firstTwo =
    Flux.from(session.executeReactive(readStatement))
        .doOnCancel(() ->
            System.out.println("Upstream subscription cancelled"))
        .take(2)
        .collectList()
        .block(Duration.ofSeconds(5));
~~~

Once 2 rows arrive, `take(2)` cancels **upstream**, avoiding reading thousands more rows just to return two. Still, the first page was likely read and sent. Any prefetched second request already in flight may also still execute.

**Operator detail:** `doOnCancel` sits **before `take(2)`** in the pipeline to observe upstream cancellation. Putting only `doFinally` after `take` shows downstream `ON_COMPLETE` because `take` completed normally after N items; that does not mean upstream wasn't cancelled.

### 12.3. `take(N)` Differs from CQL `LIMIT N`

~~~text
SELECT ... LIMIT 2
   -> Cassandra limits the valid result set on the server.

Reactive take(2)
   -> App may issue a larger CQL query,
      then stop consuming after 2 items.

To optimize reads:
  use exact CQL LIMIT + strong partition keys,
  plus take/HTTP cancellation to halt further paging if the client leaves.
~~~

If CQL scans a wide partition full of tombstones, `take(2)` does not reduce the cost of the **first page** or coordinator work already done. Query-first data modeling remains foundational in Cassandra.

### 12.4. Reactive Demand Does Not Automatically Cap Write Concurrency

When an application **sends writes**:

~~~java
Flux<Statement<?>> writes = ...;

// Dangerous if upstream is huge and flatMap opens excessive concurrency.
writes.flatMap(session::executeReactive);
~~~

Cassandra cannot use client-side `Subscription.request(n)` to throttle incoming coordinator write rates directly. Enforce **bounded concurrency** and/or rate limiting:

~~~java
Flux<Statement<?>> writes = ...;

// At most 8 concurrent CQL write subscriptions
// in this operator (NOT 8 writes/second).
Flux<Integer> completions = writes.flatMap(
    statement ->
        Flux.from(session.executeReactive(statement))
            .thenReturn(1),
    8
);
~~~

`flatMap(..., 8)` bounds active inner publishers in that operator; the service may still run **multiple operators, jobs, and instances**, so check fleet-wide in-flight totals against cluster capacity. The value `8` is a lab illustration, not a general recommendation.

## 13. Reactive Writes Emit Zero Rows: When Are They Truly Done?

### 13.1. Normal `INSERT`s Create Rowless Publishers

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Void> writeCompleted =
    Flux.from(session.executeReactive(insertStatement))
        .then();
~~~

`Mono<Void>` completes **when the reactive source completes** (or errors). **You must subscribe** or return the `Mono` to the framework; merely constructing `writeCompleted` executes zero CQL.

Upon normal completion, the client received completion per driver/CL semantics. For logged writes, that is **not** a guarantee compaction/repair finished. If cancelled before completion, write state remains uncertain.

### 13.2. Mistakes with `next()` and `count()`

~~~java
// Do NOT count emitted rows to count INSERTs:
Flux.from(session.executeReactive(insertStatement))
    .count();
// A regular INSERT emits 0 data rows => count=0,
// even when the write succeeded.
~~~

Count **statement completions**, not rows. Example (only when each statement has its own idempotency and error policy):

~~~java
Flux<Statement<?>> statements = ...;

Mono<Long> completedWrites = statements
    .flatMap(
        s -> Flux.from(session.executeReactive(s))
            .thenReturn(1L),
        8
    )
    .reduce(0L, Long::sum);
~~~

On errors, the chain may terminate early while other in-flight inner writes continue on Cassandra. Never say "`flatMap` cancelled the rest ⇒ none of them wrote." Track **write IDs and outcomes** per item.

### 13.3. Cancellation in a Multi-Mutation Flow

~~~text
Publisher<Event> ---> flatMap(write, concurrency=8) ---> downstream
    |                            |
events 1..8               8 writes subscribed/sent
    |
Downstream cancels
    |
events 9..N unsubscribed: can be avoided
events 1..8 already sent: outcomes may be uncertain
~~~

Bulk write designs need per-event-ID manifests, per-record ACKs, error queues, backpressure, and recovery. **Never** use overall stream `onComplete` as proof every event wrote if a stream cancels or times out mid-way.

### 13.4. Reactor `doFinally` Logs Termination Reason

~~~java
Mono<Void> operation =
    Flux.from(session.executeReactive(insertStatement))
        .doFinally(signal ->
            System.out.println("client terminal signal=" + signal))
        .then();
~~~

`doFinally` sees `CANCEL`, `ON_ERROR`, or `ON_COMPLETE` depending on upstream. These describe **client-side stream lifecycle**, not transaction state. Never classify `CANCEL` as `WRITE_FAILURE_CONFIRMED`.

## 14. Reactor, Driver, Server, and HTTP Timeouts — Four Clocks

~~~text
HTTP gateway timeout
       |
Application workflow deadline
       |
Reactor timeout(Duration...)
       |
Driver basic.request.timeout / setTimeout(...)
       |
Cassandra server-side read/write timeouts
       |
Actual coordinator/replica work and storage lifecycle
~~~

These clocks can expire in **different orders**. Whichever fires first determines **what error the client observes**, not the server's final mutation state.

| Timeout / cancel | Typical signal | What it does NOT prove |
|---|---|---|
| Reactor `timeout` | Reactor `TimeoutException`; upstream cancelled | Cassandra halted CQL |
| `CompletableFuture.orTimeout` | JDK `TimeoutException` on Future | Driver/server recalled mutation |
| Driver `basic.request.timeout` | `DriverTimeoutException` | No replica wrote |
| Cassandra `read_request_timeout_in_ms` | `ReadTimeoutException` via coordinator | Client may safely "redo all writes" |
| Cassandra `write_request_timeout_in_ms` | `WriteTimeoutException` via coordinator | Write was not applied |
| HTTP disconnect | Cancels HTTP response pipeline | All downstream I/O / CQL stopped |

**Server-side timeouts** also vary by Cassandra version, operation type (read, write, range, CAS, counter, truncate), and cluster settings; no single timer covers all storage work.

### 14.1. Reactor Timeout on a `SELECT`

~~~java
import reactor.core.publisher.Flux;
import java.time.Duration;

Flux<ReactiveRow> stream =
    Flux.from(session.executeReactive(readStatement))
        .timeout(Duration.ofSeconds(2));
~~~

With Reactor's `Flux.timeout(Duration)`, the timer resets on each emitted item; **it is not a 2-second absolute deadline across 100 pages**. A stream emitting one row per second can run indefinitely. When a hard end-to-end deadline is required, enforce a **request-scoped absolute deadline** or wrap overall completion instead of merely timing gaps between items.

### 14.2. End-to-End Deadlines and Remaining Budget

Suppose the API SLO is 1500 ms:

~~~text
T0: HTTP request begins
T1: validation + auth takes 100 ms
T2: Cassandra query has 1400 ms remaining
T3: first page takes 700 ms
T4: user cancels, or 700 ms remains
T5: next page fetch starts ONLY if budget remains
~~~

Never fire 5 sequential requests each with a 2-second timeout and claim the API has a 2-second timeout. In your service:

- Track a monotonic deadline (e.g., `System.nanoTime`) to compute remaining budget.
- Check cancelled/deadline state before every step or `fetchNextPage()`.
- Bound `Statement.setTimeout` within remaining budget when appropriate.
- Halt unstarted work and return an allowed error or fallback.
- For already-sent writes, keep outcomes marked unknown for reconciliation.

### 14.3. Cancellation Does Not Erase `RetryPolicy` Entirely

Once the Driver starts a logical request, **retries via `DefaultRetryPolicy`** or speculative executions may run depending on timeouts, idempotence, and profiles. By the time app-level timeout/cancel fires, extra attempts may **already have been sent**. Never infer from "cancel fired before 2 seconds" that zero retries ran on the cluster.

## 15. Throttler Queues, Backpressure, and Cancellation Boundaries

### 15.1. Requests Can Time Out Before Ever Being Sent

Java Driver provides `advanced.throttler` (pass-through by default, plus concurrency or rate limiting). Under high load, requests may **wait in a queue** before selecting a coordinator or sending:

~~~text
session.executeAsync()
       |
  driver throttler queue (optional)
       |
   wait capacity
       |
   acquire pool/stream id
       |
   send to Cassandra
~~~

Per [Request throttling](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/throttling/), `basic.request.timeout` **includes time spent waiting in the throttler queue**. Requests can time out **before any network write occurs**. That differs from post-send cancellation, though claiming "never sent" requires reliable telemetry and version-verified contracts.

### 15.2. Bounded Config Example

~~~hocon
datastax-java-driver {
  basic.request.timeout = 2 seconds

  advanced.throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 128
    max-queue-size = 512
  }
}
~~~

**128/512 are illustrative**; tune for QPS, p99, nodes, connections, and topology. The driver throttler smooths bursts, **without replacing** overall HTTP/reactive operator limits or upstream rate limiting.

### 15.3. Does Cancelling a Queued Request Immediately Evict It?

Never assume a blanket yes across all 4.x releases: implementation and version determine cancellation propagation. The [Apache Java Driver 4.19 Changelog](https://github.com/apache/cassandra-java-driver/blob/trunk/changelog/README.md) lists **JAVA-3149 — Async Query Cancellation Not Propagated To RequestThrottler** as fixed in the 4.19 line. Therefore:

- Verify the exact **artifact/version** of Java Driver running.
- Test cancellation with throttling enabled in staging, checking `throttling.queue-size`, `throttling.errors`, cancelled futures, and actual sends.
- Never claim queued cancelled requests in 4.17 are evicted instantaneously.
- When you must guarantee **zero request creation**, avoid calling `executeAsync`/subscribing whenever a cancellation flag or deadline already tripped.

### 15.4. `RequestThrottlingException`

When the queue is full, the driver throws `RequestThrottlingException`. This is **client-side admission overload**, not proof Cassandra received the request. Never spin in a tight retry loop; apply backoff/rate limits or return HTTP 429/503 per service policy. Classify it separately from `DriverTimeoutException` and server `OverloadedException`.

## 16. Retries, Speculative Execution, and "Wasted" Dispatched Work

### 16.1. One Logical Request Can Trigger Multiple Executions

~~~text
Java logical SELECT
       |
  Coordinator A
       |
  A responds slowly
       |
  Speculative execution -> coordinator B
       |
  B responds first
       |
  Driver returns B's result
       |
  A is "cancelled" client-side
       |
  A may still be reading data / preparing response
~~~

Speculative execution **differs from retries**: the driver sends a second attempt **before** the first fails. [Speculative execution](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/) states that cancelling losing executions only means **ignoring late responses**, not stopping node A. This also contributes to rising `pool.orphaned-streams`.

### 16.2. Idempotence Is Required for Safe Speculative Execution

Driver 4.x disables speculative executions by **default**; when enabled, it runs only on statements marked **idempotent**. Never mark all writes idempotent just to chase tail latency:

| CQL / action | Safe to replay? | Risk if two attempts run concurrently |
|---|---|---|
| Pure point `SELECT` | Usually yes | Extra CPU/read I/O, no CQL side effects |
| `UPSERT` with stable PK, values, timestamp | Conditionally | Races with newer writes; TTL/timestamps shift |
| `COUNTER` increment | **No** | Double increment |
| `LIST` append/prepend | **No** | Duplicate elements |
| LWT `IF NOT EXISTS` | Inspect business outcome | Replay may return `[applied]=false` even if first applied |
| Write row then send email | Workflow not automatically idempotent | Duplicate notification |

Even on read-safe SELECTs, speculation sends **more physical requests**; if disk or GC is saturated, speculation worsens overload.

### 16.3. Cancelling Before Driver Retries Finish

While a logical request is retrying or speculating, application cancellation can occur when:

- Attempt A was sent, response pending.
- Attempt B is scheduled or sent.
- One attempt succeeded, yet the downstream Future hasn't processed it.

Never assume cancelling one app stage "recalls" concurrent server attempts. Bound attempts with strict policies and deadlines, monitor retry/speculation metrics, and apply application admission control **before** dispatch when certainty is needed.

### 16.4. Never Combine Default Retries with Unbounded Reactive Retries

~~~java
// DANGEROUS for non-idempotent mutations:
Flux.defer(() -> Flux.from(session.executeReactive(writeStatement)))
    .retry();  // retries endlessly on error, replaying mutations
~~~

Reactive `retry()` creates a **new subscription** on error. With `Flux.defer`, every subscribe fires a new CQL request—while the driver may **already have retried internally** within each request. Physical attempts can multiply rapidly. Enforce bounded retries, jittered backoff, time budgets, and error classification; for unknown write outcomes, reconcile before retrying.

## 17. Observability: Monitor Client and Server Together

### 17.1. Cancellation-Related Driver Metrics

Depending on driver version and metrics backend, you can enable:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      cql-requests,
      cql-client-timeouts,
      throttling.delay,
      throttling.queue-size,
      throttling.errors
    ]

    node.enabled = [
      cql-messages,
      pool.open-connections,
      pool.in-flight,
      pool.available-streams,
      pool.orphaned-streams,
      retries.total,
      speculative-executions
    ]
  }
}
~~~

These are **HOCON option names**, not guaranteed Prometheus series names across all exporters. Metrics may be off by default and require Micrometer/Dropwizard/registry wiring; verify your actual scrape endpoint before building dashboards. Consult [Java Driver metrics](https://apache.github.io/cassandra-java-driver/4.18.1/core/metrics/) and your binary's reference config.

### 17.2. Interpreting Metrics Accurately

| Metric / trace | Level | Question it answers |
|---|---|---|
| App `cancelled_http_requests` | Service | How many callers stopped waiting? |
| App `cancelled_future_count` | Service | How many futures transitioned to cancelled? |
| App `rows_delivered` / `pages_requested` | Query family | How many rows delivered and page requests issued? |
| `cql-requests` | Driver session | Logical CQL requests and latency |
| `cql-messages` | Driver node | Network messages/attempts to coordinators |
| `pool.in-flight` | Driver node | Messages awaiting responses |
| `pool.available-streams` | Driver node | Usable stream IDs left |
| `pool.orphaned-streams` | Driver node | Stream IDs not yet reclaimable after cancel/orphan |
| `speculative-executions` | Driver node | Extra attempts from speculation policy |
| `retries.total` | Driver node | Policy-triggered retries |
| `cql-client-timeouts` | Driver session | Expired driver deadlines |
| `throttling.queue-size` | Driver session | Requests waiting in throttler queue |
| Cassandra `ClientRequest.Read/Write.Latency` | Server | Actual coordinator request latency |
| Disk / GC / compaction / replica metrics | Server | Physical bottlenecks persisting after client cancel |

**Never use `cancelled_future_count` alone to claim how many server queries halted.** Likewise, `cql-requests` and `cql-messages` have different denominators under paging, retries, and speculation; align windows and scopes carefully.

### 17.3. Useful Ratios

Defined over the same service/query-family window:

\[
\text{cancelRatio} =
\frac{\text{client-cancelled logical requests}}{\text{started logical requests}},
\qquad
\text{extraAttemptRatio} \approx
\frac{\text{node messages}}{\text{logical requests}}.
\]

These are **reference indicators**, not exact equations for row counts or replica I/O, since each async page can be a logical request and metric scopes differ. Also watch:

- **Pages requested after client disconnect:** ideally near 0, allowing for in-flight races.
- **Cancel-to-response lag:** with tracing, how long after cancel late responses arrive.
- **Orphaned streams / available streams:** catches pool pressure from aborts/speculation.
- **Client vs. server QPS:** if cancels cut HTTP completions while CQL QPS stays high, too much work was dispatched before cancellation.
- **Unknown write outcomes:** count of operations needing reconciliation.

### 17.4. Read-Only Server-Side Commands

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool tablestats cancel_lab.events_by_day
~~~

`nodetool status` cannot tell whether a **specific request** committed; it checks ring and replica availability. `compactionstats` reflects storage backlog, not "uncancelled queries." To determine business outcome, reconcile against PKs, versions, or event logs.

### 17.5. Safe Tracing and Logging

~~~text
request_family=events.listByDay
mode=reactive
profile=history_read
client_cancelled=true
cancel_reason=http_disconnect
rows_delivered=2
pages_requested=1
cql_outcome=UNKNOWN_NOT_ACKNOWLEDGED
server_work_stopped=NOT_KNOWN
~~~

**Never** put raw CQL bind values, tenant IDs, emails, customer names, or payment IDs into metric labels. For correlation, use trace IDs or hashed/tokenized operation IDs per security policy, and avoid high-cardinality Prometheus dimensions.

### 17.6. Canary Measuring Reduction in Unnecessary Work

~~~text
Before:
  100 HTTP requests cancelled at 1 s
  500 CQL page requests dispatched

After:
  100 HTTP requests cancelled at 1 s
  150 CQL page requests dispatched

Defensible conclusion:
  Fewer pages were requested after the change.

Invalid conclusion:
  "Cassandra killed 350 running queries."
~~~

Keep monitoring Cassandra CPU/disk/latency and `pool.orphaned-streams` to verify the change reduced actual **server load** rather than just trimming small-query page traffic.

## 18. Lab CQL: Creating Data to Test Stopping Reads

**Goal:** Seed 5 rows in one partition to use `pageSize=2` and test stopping after 2 rows. Synthetic data only; do not inject faults or slow down nodes. Write-cancellation experiments only illustrate **races** and must not be treated as deterministic oracles.

### 18.1. Environment

- Cassandra 4.1/5.0 on a **single lab node** with working `cqlsh`.
- Java 17 and Java Driver 4.x, plus Reactor 3.x for reactive tests.
- Port `9042` and correct local DC, e.g., `datacenter1`; verify with `nodetool status`.
- Isolated keyspace `cancel_lab`; never touch production tables.

### 18.2. Create Keyspace and Tables

~~~sql
CREATE KEYSPACE IF NOT EXISTS cancel_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS cancel_lab.events_by_day (
  tenant_id text,
  day date,
  seq int,
  event_id uuid,
  status text,
  PRIMARY KEY ((tenant_id, day), seq)
) WITH CLUSTERING ORDER BY (seq ASC);

CREATE TABLE IF NOT EXISTS cancel_lab.operations_by_id (
  tenant_id text,
  operation_id uuid,
  status text,
  PRIMARY KEY ((tenant_id), operation_id)
);
~~~

`SimpleStrategy`/RF1 is strictly for the lab. In multi-DC production, use `NetworkTopologyStrategy`, RF, and CL matching your data contract. This lab tests cancellation, not consistency benchmarks.

### 18.3. Load 5 Stable Rows

~~~sql
CONSISTENCY ONE;

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 1,
        11111111-1111-1111-1111-111111111111, 'NEW');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 2,
        22222222-2222-2222-2222-222222222222, 'PAID');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 3,
        33333333-3333-3333-3333-333333333333, 'PACKED');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 4,
        44444444-4444-4444-4444-444444444444, 'SHIPPED');

INSERT INTO cancel_lab.events_by_day
  (tenant_id, day, seq, event_id, status)
VALUES ('tenant-a', '2026-11-21', 5,
        55555555-5555-5555-5555-555555555555, 'DELIVERED');
~~~

### 18.4. Baseline With `SELECT`

~~~sql
SELECT seq, event_id, status
FROM cancel_lab.events_by_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

Expect 5 rows ordered by `seq ASC`. If prior lab runs added extra data in the same partition, use a **controlled new lab keyspace/partition** or verify existing state first; never run `TRUNCATE` on unapproved data.

## 19. Lab Java Async: Controlling Page Fetches and Testing Cancel Races

### 19.1. Dependencies / API

For Java Driver 4.17, illustrative Maven dependency:

~~~xml
<dependency>
  <groupId>com.datastax.oss</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.17.0</version>
</dependency>
~~~

From 4.18 onward, Java Driver is maintained by the Apache Software Foundation; match the Maven coordinates/BOM of your exact version. This lesson provides sample code only—**do not generate extra project files or run Maven/Gradle** during STEP 4.

### 19.2. Complete Program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class CancelAsyncLab {
    private CancelAsyncLab() {}

    public static void main(String[] args) {
        // Replace datacenter1 with the REAL DC name from nodetool status.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement p = session.prepare(
                "SELECT seq, event_id, status " +
                "FROM cancel_lab.events_by_day " +
                "WHERE tenant_id = ? AND day = ?");

            BoundStatement read = p.bind(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setPageSize(2)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            // Step A: asynchronously consume 3 rows, stopping before extra pages.
            CompletionStage<Integer> firstThree =
                session.executeAsync(read).thenCompose(
                    page -> countAtMost(page, 3, 0));

            int observed = firstThree.toCompletableFuture().join();
            System.out.println("rows consumed=" + observed);
            if (observed != 3) {
                throw new IllegalStateException("Expected 3 rows");
            }

            // Step B: cancel an independent read request.
            // Small SELECT may complete before cancel -> nondeterministic.
            CompletableFuture<AsyncResultSet> future =
                session.executeAsync(read).toCompletableFuture();

            boolean cancelled = future.cancel(false);
            System.out.println("cancel returned=" + cancelled);
            System.out.println("isCancelled=" + future.isCancelled());

            // Never infer Cassandra stopped work.
            // Never call join() on a cancelled future.
            // Never close the session inside an I/O callback.
        }
    }

    private static CompletionStage<Integer> countAtMost(
            AsyncResultSet page, int maxRows, int previouslySeen) {

        int seen = previouslySeen;
        for (Row row : page.currentPage()) {
            if (seen >= maxRows) {
                return CompletableFuture.completedFuture(seen);
            }
            System.out.println("seq=" + row.getInt("seq"));
            seen++;
        }

        if (seen >= maxRows || !page.hasMorePages()) {
            return CompletableFuture.completedFuture(seen);
        }

        final int count = seen;
        return page.fetchNextPage()
            .thenCompose(next -> countAtMost(next, maxRows, count));
    }
}
~~~

### 19.3. Expected Output

~~~text
seq=1
seq=2
seq=3
rows consumed=3
cancel returned=true/false
isCancelled=true/false
~~~

The last two lines **have no single fixed value** because the query may complete before `cancel`. That race is exactly what to learn, **not a flaky test to "fix" by slowing Cassandra down**. The lab succeeds when you can explain:

- `page-size=2` still yields 3 rows after calling `fetchNextPage` once.
- The helper stops fetching once `maxRows=3` is hit; rows already in the current page are not rolled back.
- `cancel(false)` returning true/false is client Future state, not proof the coordinator stopped.
- `session.executeAsync(read)` already started the request **before** converting to `CompletableFuture` to cancel.

### 19.4. Adding a Cancellation Flag in Real Applications

In a REST service, replace the fixed row cap with `AtomicBoolean cancelled` and a deadline check before every `fetchNextPage()` as in section 9. Never let a disconnected client's loop keep reading an entire partition "just to finish"; that generates huge wasted QPS.

**On recursion:** for huge page counts, consider a loop/trampoline or bounded stream to avoid deep chains of dependent stages/callbacks. Never materialize an entire `AsyncResultSet` into `List<Row>` when the API only needs a few rows.

## 20. Lab Java Reactor: Cold Publishers, `take(2)`, and `dispose()`

### 20.1. Reactor Dependencies

In addition to `java-driver-core` 4.x and the Reactive Streams API, this example uses Reactor Core 3.x. The driver depends on Reactive Streams API, whereas **Reactor is not a mandatory driver dependency**; declare Reactor in your project if absent.

### 20.2. Complete Program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.LocalDate;
import java.util.List;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

public final class CancelReactiveLab {
    private CancelReactiveLab() {}

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT seq, event_id, status " +
                "FROM cancel_lab.events_by_day " +
                "WHERE tenant_id = ? AND day = ?");

            BoundStatement read = prepared.bind(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setPageSize(2)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            // Create publisher, WITHOUT querying yet.
            ReactiveResultSet cold =
                session.executeReactive(read);

            // Subscribing via block() ONLY for main lab illustration.
            List<ReactiveRow> rows = Flux.from(cold)
                .doOnCancel(() ->
                    System.out.println("upstream CANCEL"))
                .take(2)
                .collectList()
                .block(Duration.ofSeconds(5));

            System.out.println("rows delivered=" + rows.size());
            for (ReactiveRow row : rows) {
                System.out.println("seq=" + row.getInt("seq"));
            }

            // NEW publisher for testing Disposable cancellation.
            Disposable subscription =
                Flux.from(session.executeReactive(read))
                    .doOnCancel(() ->
                        System.out.println("explicit CANCEL"))
                    .subscribe(
                        row -> System.out.println(
                            "observed seq=" + row.getInt("seq")),
                        error -> System.err.println(
                            "error=" +
                            error.getClass().getSimpleName()));

            // RACE: may cancel before, during, or after response.
            subscription.dispose();

            // Never claim Cassandra killed the SELECT.
        }
    }
}
~~~

### 20.3. Expectations and What Not to Assert

Expected output for the `take(2)` branch on a clean lab partition:

~~~text
upstream CANCEL
rows delivered=2
seq=1
seq=2
~~~

`explicit CANCEL` in the `dispose()` branch **will not always print**: the stream may complete synchronously or before `dispose` executes. Never insert `Thread.sleep` inside I/O callbacks or overload the server just to force "pretty output."

### 20.4. Why Not Subscribe Twice to the Same Publisher?

`cold` is single-subscription-only. Calling `Flux.from(cold).blockLast()` a second time throws `IllegalStateException` by default. For a fresh query, call `session.executeReactive(read)` again; to reuse an **already-materialized dataset**, cache client-side only when truly small and footprint/freshness rules allow.

### 20.5. In WebFlux Applications

Controllers should **return** `Flux/Mono` so the framework manages subscriptions and HTTP disconnects rather than calling `subscribe()` manually and discarding the `Disposable`:

~~~java
public Flux<ReactiveRow> findEvents(
        CqlSession session, BoundStatement read) {
    return Flux.defer(
        () -> Flux.from(session.executeReactive(read)));
}
~~~

If the HTTP client cancels downstream, Reactor propagates `cancel` to the Cassandra publisher. This stops demand and paging, while **never** guaranteeing an already-sent query stopped. Outside a framework, ensure returned stages/`Flux`es are **subscribed exactly once** and never left running unowned in the background.

## 21. Pure JDK Deterministic Lab: Cancel a Future, Independent Task Still Runs

Real Cassandra labs have races so `cancel` sometimes returns true and sometimes false. To **prove the concept** cleanly without stressing a cluster, use two threads and latches below. This models **client and server separation**, not Cassandra's internal implementation or native protocol.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationIsNotRollback {
    public static void main(String[] args) throws Exception {
        ExecutorService simulatedServer =
            Executors.newSingleThreadExecutor();

        CountDownLatch accepted = new CountDownLatch(1);
        CountDownLatch resumeWork = new CountDownLatch(1);
        AtomicBoolean mutationApplied = new AtomicBoolean(false);
        CompletableFuture<String> response = new CompletableFuture<>();

        try {
            simulatedServer.execute(() -> {
                accepted.countDown(); // "server accepted request"
                try {
                    resumeWork.await(); // lab only, not a driver callback
                    mutationApplied.set(true);
                    response.complete("ACK");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    response.completeExceptionally(interrupted);
                }
            });

            if (!accepted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Simulated server not ready");
            }

            boolean cancelled = response.cancel(true);
            System.out.println("client cancel returned=" + cancelled);

            // Allow "server" to finish after client already cancelled.
            resumeWork.countDown();
            simulatedServer.shutdown();

            if (!simulatedServer.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server task still running");
            }

            System.out.println("future cancelled=" +
                response.isCancelled());
            System.out.println("mutation applied=" +
                mutationApplied.get());
        } finally {
            resumeWork.countDown();
            simulatedServer.shutdownNow();
        }
    }
}
~~~

**Expected output:**

~~~text
client cancel returned=true
future cancelled=true
mutation applied=true
~~~

Here `response.cancel(true)` does not interrupt the simulated task because `response` is a standalone `CompletableFuture`, not a `FutureTask` owning that thread. The task still finishes and `response.complete("ACK")` cannot undo the cancelled state. In **principle**, a cancelled client Future never proves a server mutation didn't happen. **Do not assume every cancelled Cassandra query always finishes**; outcomes depend on timeouts, errors, and server execution. This lab strictly proves cancellation does not guarantee rollback.

## 22. Write Cancellation Lab: An Unpredictable Outcome

### 22.1. Use Only Fixed Keys in the Lab Keyspace

Assuming `cancel_lab.operations_by_id` was created in section 18, use a fixed operation ID:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

UUID operationId = UUID.fromString(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");

PreparedStatement insert = session.prepare(
    "INSERT INTO cancel_lab.operations_by_id " +
    "(tenant_id, operation_id, status) VALUES (?, ?, ?)");

BoundStatement write = insert.bind(
        "tenant-a", operationId, "STARTED")
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .setIdempotent(false); // Conservative for illustration; no auto-retry.

CompletableFuture<AsyncResultSet> inFlight =
    session.executeAsync(write).toCompletableFuture();

boolean cancelled = inFlight.cancel(false);
System.out.println("write future cancelled=" + cancelled);

PreparedStatement lookup = session.prepare(
    "SELECT status FROM cancel_lab.operations_by_id " +
    "WHERE tenant_id = ? AND operation_id = ?");

Row observed = session.execute(
    lookup.bind("tenant-a", operationId)
        .setConsistencyLevel(DefaultConsistencyLevel.ONE)).one();

System.out.println(
    "immediate read=" +
    (observed == null ? "NOT_VISIBLE_YET" :
        observed.getString("status")));
~~~

**No fixed output.** Cancel can win or lose the race against the response; an immediate `SELECT` after cancel may or may not see the row. On an RF1 lab, writes often complete extremely fast. Even seeing `NOT_VISIBLE_YET`, you **cannot** conclude the row will never appear. If the lab ran earlier, the row may remain from the prior run; use a fresh operation ID **deterministically recorded for that attempt**, never randomizing on retries.

### 22.2. How NOT to "Force Seeing Cancel"

Never:

- Block networks with `iptables` in production.
- Intentionally fill disks or kill replicas.
- Lower Cassandra server timeouts to a few milliseconds to trigger mass failures.
- Run `TRUNCATE` to erase unreconciled state.
- Retry `INSERT`s repeatedly with a fresh operation ID each time.

To test cancellation deeply, run integration tests with an **authorized staging proxy/fault-injection harness**, driver/server instrumentation, and a source of truth; destructive server tests are not part of the basic lab.

### 22.3. Recording Outcomes Properly in Real Systems

~~~text
operation_id: aaaaaaaa-...
client_cancelled: true
request_maybe_sent: true
write_outcome: UNKNOWN
last_observation: SELECT at T1 (visibility dependent on CL)
next_step: reconcile with business event log + version
retry_allowed: only after idempotency decision
~~~

"Cancelled" is a **property of the client request**; "written" is a **property of data and replicas**. Both can be true simultaneously.

## 23. Real-World Scenarios: What to Do When Cancellation Happens

### Case 1 — User Closes Page After Clicking "View History"

**Scenario:** WebSocket/HTTP stream is sending rows; client disconnects at row 20 of 1,000.

**Right:** Propagate cancel to the stream, stop fetching unstarted pages, and cut downstream work. If the first 100-row page already returned to the driver, the coordinator still computed that whole page.

**Wrong:** Claiming "Cassandra stopped the SELECT at row 20," or continuing to fetch all 1,000 rows for an unowned cache.

### Case 2 — Using `take(1)` on a Wide Partition, Yet Cassandra CPU Stays High

**Cause:** The server already scanned tombstones/SSTables to build the first page; `take(1)` is a **downstream item limit**, not a fix for query shape or partitions. The query may lack a selective partition key.

**Fix:** Use proper `LIMIT`, partition bucketing, query-driven tables/indexes, tuned page sizes, and server metrics—not higher cancellation rates.

### Case 3 — Order-Creation POST Cancelled When HTTP Client Drops Network

**Risk:** The mutation was sent and written; the HTTP caller saw no ACK and retries creating another order.

**Fix:** Use a fixed idempotency key and operation ID, store outbox/dedup state, and reconcile before replaying; never return "order not created" solely from `Future.isCancelled()`.

### Case 4 — `Future.cancel` Returns `false` in the Lab

**Explanation:** The request finished too quickly, or the Future already hit another terminal state before `cancel`.

**Fix:** This is a normal race. Never inject `Thread.sleep` into Netty callbacks or artificially slow Cassandra just to force `true`. Use the pure JDK experiment in section 21 to demonstrate Future state transitions.

### Case 5 — `Future.cancel` Returns `true` Yet `SELECT` Sees the New Row

**Explanation:** The client stopped waiting for the response, while the server processed the mutation before or right after cancellation.

**Fix:** Do not file a bug claiming "Future was cancelled yet Cassandra still wrote." Check operation IDs, deadlines, write timestamps/CL, and reconciliation. This behavior **follows native protocol boundaries**.

### Case 6 — Cancelling a Trailing `thenApply` Fails to Reduce CQL QPS

**Cause:** Cancelling a child stage **does not necessarily** cancel the upstream `executeAsync`. The root already sent the CQL.

**Fix:** Maintain request ownership/context, propagate stop flags into paging loops, track where the root Future lives, and apply admission control before sending requests.

### Case 7 — Subscribing Twice to the Same `ReactiveResultSet`

**Symptom:** The second subscription throws `IllegalStateException`.

**Explanation:** `ReactiveResultSet` defaults to single-subscription-only.

**Fix:** Create a fresh publisher per query, or use size-bounded sharing/caching with clear freshness rules. Never misdiagnose second-subscription errors as Cassandra being unavailable.

### Case 8 — Reactive Write "Runs" Yet Writes Zero Data

**Cause:** The app constructed `ReactiveResultSet` inside `doOnNext` without subscribing, or built a `Mono<Void>` and discarded it without returning/subscribing.

**Fix:** Compose via `flatMap`/`then` with a terminal subscriber or framework owner. **Cold** means zero effect until subscribed.

### Case 9 — `dispose()` Logs `CANCEL` While Server Still Shows Write Metrics

**Explanation:** Multiple writes were already submitted before `dispose`; cancellation only skips unsubscribed/pending items.

**Fix:** Track outcomes per event ID, compare `cql-messages`/write latencies, and reconcile. Never mark all pending writes failed and blindly re-import them.

### Case 10 — `pool.orphaned-streams` Climbs Alongside Connection Churn

**Likely cause:** Heavy cancellations or speculative executions leaving late responses; stream IDs cannot be reused immediately.

**Fix:** Cut unnecessary requests upfront, review speculation thresholds, page prefetch, and overly tight timeouts; watch `pool.available-streams`, `pool.in-flight`, open connections, and Netty/OS sockets. Never close the session per user to "clear orphans."

### Case 11 — 2 s Reactive Timeout, Yet HTTP Responds After 30 s

**Cause:** `Flux.timeout(Duration.ofSeconds(2))` measures idle gaps between emitted items; steady row emissions keep resetting it, leaving total duration unbounded.

**Fix:** Enforce an **absolute end-to-end deadline** at the HTTP/service layer and check remaining budget before page/DB calls rather than treating idle timeouts as total SLAs.

### Case 12 — Driver Timeout While Request Still Sits in Throttler Queue

**Scenario:** `throttling.queue-size` is large, and the request exhausts `basic.request.timeout` before hitting a socket.

**Fix:** Tighten admission limits/rate control, backpressure, and capacity. Do not conclude the server timed out or mis-wrote; still verify with telemetry and driver version before claiming a request was definitely never sent.

### Case 13 — Async Cancellation Fails to Free Throttler Capacity in One 4.x Release

**Possibility:** Version-specific behavior; changelog 4.19 fixed `JAVA-3149` for cancellation propagation to the request throttler.

**Fix:** Verify your library version, run regression tests under throttler load, and compare queue/in-flight metrics before/after. Never generalize across all 4.x releases without testing.

### Case 14 — Speculative `SELECT` Wins on Node B While Node A Keeps Reading SSTables

**Explanation:** Driver-side "cancelling the losing execution" only discards node A's response; ordinary CQL has no server-side kill.

**Fix:** For CPU/I/O-heavy workloads, consider tuning down speculation and fixing hot partitions, GC, or disk contention; maintain proper idempotence and watch `orphaned-streams`.

### Case 15 — HTTP 504 Yet Cassandra Row Already Exists

**Cause:** The gateway/app deadline expired before the coordinator ACK or network response returned.

**Fix:** Return an operation ID and retry-safe/unknown status in the API contract so clients poll a status endpoint by event ID. Never let callers blindly mint a new operation ID after a 504.

### Case 16 — Reactive `retryWhen` Fires Extra `INSERT`s After Errors

**Cause:** Each re-subscription via `Flux.defer` calls `executeReactive` again, while the driver may also run internal retries/speculation.

**Fix:** Bound retries by error class and idempotency, enforce global rate limits and deadlines, disable automatic retries for non-idempotent mutations, and reconcile unknown outcomes.

### Case 17 — Batch App Terminates Mid-Way Through 1,000 Writes

**Risk:** Some events were never subscribed, some were sent, and some were ACKed; `Flux` ending does not classify every row under one flag.

**Fix:** Maintain per-event manifests (`confirmed`/`failed`/`unknown`), track source offsets, keep writer concurrency ≤ capacity, and on resume replay only per idempotency policies and reconciled checkpoints.

### Case 18 — DSE Continuous Paging Has Its Own `cancel()` API

**Distinction:** DataStax Enterprise's `ContinuousAsyncResultSet` provides a `cancel()` method specific to *continuous paging*. That is **not** evidence that Cassandra OSS `AsyncResultSet` or standard native CQL supports an equivalent `kill query` command. Never cross-apply DSE APIs onto Cassandra OSS 4.x/5.x. See [ContinuousAsyncResultSet Javadoc](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/dse/driver/api/core/cql/continuous/ContinuousAsyncResultSet.html).

### Case 19 — Service Shuts Down While Async CQL Is Still Running

**Risk:** A shutdown hook calls `session.close()` too early after cancelling HTTP responses, breaking hundreds of active requests; closing connections also does not roll back already-sent server writes.

**Fix:** Execute **graceful shutdown**: stop admitting new requests, stop issuing new pages/jobs, drain bounded in-flight work within a deadline, persist unknown outcomes, close the session per app lifecycle, and report operations needing reconciliation.

### Case 20 — Team Counts Cancels as Write Failures

**Wrong KPI:** `cancelled_futures = failed_writes` causes false alarms, blind retries, and duplicate writes.

**Right KPI:** Track `CANCELLED_CLIENT`, `ACKNOWLEDGED_SUCCESS`, `SERVER_ERROR`, `UNKNOWN_WRITE_OUTCOME`, and `RECONCILED_FINAL_STATE`. One operation can be **client-cancelled and server-succeeded**.

## 24. Runbook: Cancelling Requests While Protecting Data Correctness

### 24.1. Before Deployment

Document for each **query family**:

| Question | Example answer |
|---|---|
| Read or write? | `events.listByDay` is SELECT; `orders.create` is INSERT |
| Good partition key? | `(tenant_id,day)` plus clustering range |
| CL and RF per DC? | RF=3, `LOCAL_QUORUM` for critical orders |
| HTTP / service / driver deadlines? | 1500 / 1300 / 1000 ms aligned with retry/paging |
| Where can cancellation hook in? | Before execute, before `fetchNextPage`, reactive subscription |
| Idempotency key needed? | Writes subject to POST retries / unknown outcomes |
| Read cache/fallback allowed? | Only on APIs permitting stale data |
| Metrics confirming load reduction? | Pages requested, server QPS, orphaned streams, p99 |
| Library versions? | Java Driver 4.17/4.19, Reactor, Netty config |

**Never** attach a global HTTP cancellation handler that calls `session.close()`. Sessions are shared resources. Separate read-only queries (which can **stop fetching**) from writes (which need **reconciliation**).

### 24.2. Handling Flow When the Caller Stops Waiting

~~~text
                 HTTP / gRPC / job cancellation
                           |
                   Mark request cancelled
                           |
                   Has CQL started yet?
                  /                      \
                NO                       YES
                |                         |
        Skip execute              Is CQL read or write?
        or skip subscribe            /           \
                                   READ          WRITE
                                     |             |
                              Stop page demand   Possibly sent?
                              / fetchNextPage     /         \
                                     |          NO*          YES/UNKNOWN
                                     |           |             |
                              Does not kill     Drop        Mark UNKNOWN
                              server work    unsent work   + operation ID
                                     |                         |
                                     |                   Reconcile via
                                     |                   source of truth
                                     \                         /
                                      \                       /
                                       Metrics and guardrails
                                               |
                                         GO/HOLD/STOP

* NO only with reliable evidence, never inferred solely from cancel=true.
~~~

### 24.3. Timeline Fields to Log

~~~text
T0 request_started_utc
T1 query_family/profile/CL/partition_category
T2 executeAsync_called or reactive_subscribed
T3 page_requested_count / rows_delivered_count
T4 cancel_requested_utc + reason
T5 client terminal signal: CANCEL/ERROR/COMPLETE
T6 request stage outcome: ACK/ERROR/UNKNOWN
T7 business reconciliation result (if write)
T8 metrics window and rollback decision
~~~

**Never** log a synthetic `SERVER_STOPPED_AT_T4` timestamp unless the server actually reported it. Across Java async/HTTP nodes, client and server clocks skew; measure durations with monotonic deltas and use UTC timestamps for correlation.

### 24.4. GO / HOLD / STOP

| Observation | Action | Reason |
|---|---|---|
| Page fetches stop early; server QPS and p99 drop | **GO** expand canary | Cuts unsent work without altering data |
| Reactive `take` returns N rows, yet orphaned streams spike | **HOLD** | May be firing excessive in-flight requests before cancel |
| Cancel ratio climbs, CQL messages stay flat | **HOLD** | Cancelling too late or upstream stages not propagating |
| Write cancelled with no ACK and unreconciled | **STOP blind retry** | Outcome unknown |
| `completeOnTimeout(fakeSuccess)` used on writes | **STOP** | Masks real outcome dangerously |
| Driver throttler queue grows after cancel on older version | **HOLD** | Check version-specific propagation |
| Speculation/retries degrade node CPU/disk | **HOLD/ROLLBACK** | Extra physical attempts |
| Node DOWN, CL unmet, or data correctness wrong | **STOP/ESCALATE** | Cannot be fixed by Future cancellation |
| Canary confirms saved pages, stable p99, clean write audits | **GO** batch by batch | Backed by evidence and headroom |

Real thresholds must fit your QPS, SLOs, baseline, and sample size; a hardcoded "orphaned > 10" rule will not fit every pool size or driver version.

### 24.5. After a Rollback

If a paging-stop or timeout change caused an incident:

1. Restore config/feature flags from source of truth and verify **effective options** on the JVM.
2. Verify new requests show expected behavior; pre-rollback in-flight requests may still finish.
3. For cancelled or timed-out writes, retain the `UNKNOWN` list for reconciliation; **rolling back code never undoes Cassandra mutations**.
4. Check client p99/errors, `pool.orphaned-streams`/connections, and server latency/GC/disk.
5. Document root cause, reproduction steps, and regression tests (especially driver version/queue behavior).

### 24.6. Graceful Service Shutdown

~~~text
SIGTERM
   |
Stop admitting new HTTP / jobs
   |
Signal cancellations for service-owned streams
   |
Stop fetching new pages / scheduling new writes
   |
Bounded drain of in-flight tasks within deadline
   |
Persist UNKNOWN write outcomes + checkpoints
   |
Close shared CqlSession per lifecycle
   |
Exit with report of any remaining pending work
~~~

Never call `forceCloseAsync` or tear down sockets early as a supposed guarantee that writes rolled back. Shutdown manages **client resources**; knowing what data persisted relies on ACKs, CL, and reconciliation.

## 25. Code Review and Cancellation Operations Checklist

### 25.1. Async Futures and Lifecycles

- [ ] `CqlSession` reused; never created or closed per request.
- [ ] Team knows `executeAsync` **starts the request upon invocation**.
- [ ] Identifies root stage and lifecycle owner; never assumes cancelling a dependent stage propagates upstream.
- [ ] `CompletableFuture.cancel(true)` never mistaken for server-side thread interruption.
- [ ] Never calls `join/get` on a cancelled future without handling `CancellationException`.
- [ ] Distinguishes cancelled outcomes, error outcomes, and normal completions.
- [ ] Checks `AtomicBoolean`/deadline before every `fetchNextPage()`.
- [ ] Understands the race between flag check and next-page dispatch; never promises zero in-flight after cancel.
- [ ] Callbacks on driver I/O threads do zero blocking or heavy CPU work.
- [ ] Never uses `completeOnTimeout` to fabricate write success.
- [ ] Uses end-to-end deadlines rather than per-page request timeouts alone.
- [ ] When HTTP cancels a Future, metrics and unknown write outcomes are still recorded.

### 25.2. Reactive Streams / Reactor

- [ ] Team knows `executeReactive` returns a cold publisher that sends CQL **only upon subscription**.
- [ ] Every publisher has a real subscriber/owner; never constructed and discarded in `doOnNext`.
- [ ] `ReactiveResultSet` is single-subscription-only; retries create a fresh publisher under policy.
- [ ] `Subscription.cancel()` / `dispose()` controls only client stream/demand.
- [ ] `take(N)` never mistaken for CQL `LIMIT N` or a server-side kill.
- [ ] Rowless write publishers tracked via completion signals, not `onNext` counts.
- [ ] Bulk writes use `flatMap(..., boundedConcurrency)` or equivalent limits.
- [ ] Infinite `retry()` avoided, especially on non-idempotent mutations.
- [ ] `Flux.timeout(Duration)` understood as an inter-item idle timeout, not an API-wide deadline.
- [ ] HTTP handlers return `Mono/Flux` to the framework rather than calling unmanaged `subscribe()`.
- [ ] Millions of rows never `cache()`d or multicast on heap just to avoid re-subscribing.
- [ ] Metrics track cancelled subscriptions, rows delivered, pages requested, retries, and errors.

### 25.3. Cassandra Correctness

- [ ] Partition keys, CL, RF, and DC match access patterns.
- [ ] Write cancellations classified as **UNKNOWN_OUTCOME** whenever dispatch was possible.
- [ ] Idempotency keys / operation IDs stay stable across HTTP retries.
- [ ] Never set `idempotent=true` on counters, list appends, arbitrary LWTs, or unsafe side effects.
- [ ] Never use an immediate `ONE` `SELECT` after cancel as final proof a "write does not exist."
- [ ] Event audits, versions, and reconciliation align with business policy.
- [ ] Never assume compaction/flush/repair halt when a request cancels.
- [ ] Never lower CL or durability just to make timeouts vanish.
- [ ] Fault injection runs only in authorized staging with a rollback plan.
- [ ] PII, credentials, and raw CQL values never leak into cancellation logs.

### 25.4. Monitoring and Rollout

- [ ] Track driver version, especially request-throttling and cancellation fixes.
- [ ] Separate `cql-requests`, `cql-messages`, retries, and speculative executions.
- [ ] Enable `pool.orphaned-streams` / `pool.available-streams` / `pool.in-flight` if supported.
- [ ] Track `throttling.queue-size`, request/client timeouts, and HTTP cancel ratios.
- [ ] Track Cassandra server read/write latency, disk/GC, tombstones, and compaction.
- [ ] Compare canary vs. control under identical workloads and shared cluster resources.
- [ ] Base GO/HOLD/STOP on SLOs and correctness rather than one fixed threshold for all clusters.
- [ ] After rollback, verify **both app SLOs and unknown outcomes**, not just config files.

## 26. Self-Assessment Questions and Suggested Answers

**Q1.** Does `executeAsync(statement)` send CQL when called or wait for `thenApply`?  
**Hint:** Request execution begins when `executeAsync` is called; callbacks only consume the result.

**Q2.** Does calling `executeReactive(statement)` without subscribing send CQL?  
**Hint:** No; the default cold publisher executes only upon subscription.

**Q3.** Does `CompletableFuture.cancel(true)` send an interrupt signal to Cassandra server threads?  
**Hint:** No; a JDK Future flag cannot kill threads in a server JVM, and the native protocol has no ordinary CQL cancel frame.

**Q4.** What does `cancel(false)` returning `true` prove?  
**Hint:** The Future was incomplete and transitioned to cancelled; it does not prove the server didn't execute.

**Q5.** If `cancel(false)` returns `false`, did the query necessarily fail?  
**Hint:** No; the Future may have already completed normally or exceptionally before `cancel`.

**Q6.** Does cancelling a dependent `thenApply` stage automatically cancel the root `executeAsync`?  
**Hint:** No. JDK cancellation does not normally propagate upstream from child to parent.

**Q7.** If a Future is cancelled after sending an `INSERT`, can you tell the client "definitely not written"?  
**Hint:** No; mark the write outcome unknown and reconcile.

**Q8.** In native protocol v5, is there a standard `CANCEL QUERY` message for ordinary CQL execution?  
**Hint:** Not among standard opcodes; driver-side cancellation discards late responses and stops demand.

**Q9.** Why does a stream ID become orphaned after cancellation?  
**Hint:** The old request's response may arrive late, so the ID cannot be safely reassigned immediately.

**Q10.** What can rising `pool.orphaned-streams` lead to?  
**Hint:** Falling `pool.available-streams`, connection recycling/churn, and rising pool pressure.

**Q11.** When you read only `currentPage()` of `AsyncResultSet` without calling `fetchNextPage()`, what is avoided?  
**Hint:** Subsequent page requests are never initiated; the first page was still sent.

**Q12.** If a cancel flag flips at the same instant code calls `fetchNextPage()`, are you guaranteed zero new requests went out?  
**Hint:** No; checking the flag and sending the request can race.

**Q13.** Does `page-size=100` mean the entire query has at most 100 rows?  
**Hint:** No; page size sets target rows per page, distinct from CQL `LIMIT` and API caps.

**Q14.** Does reactive `Subscription.request(1)` tell Cassandra to read strictly one row from SSTables and stop?  
**Hint:** No; the driver paces row delivery and page fetches, and native CQL has no per-row demand protocol.

**Q15.** Does `Subscription.cancel()` force `onComplete()` to fire?  
**Hint:** No; cancellation stops the subscription and normally produces no terminal `onComplete`.

**Q16.** Reactor `take(2)` cancels upstream after 2 rows—did the server stop right at row 2?  
**Hint:** No; the server may have already computed/sent the entire first page.

**Q17.** How do reactive `take(2)` and `SELECT ... LIMIT 2` differ?  
**Hint:** `take` caps downstream consumption; `LIMIT` restricts CQL results on the server.

**Q18.** Can you subscribe twice to the same `ReactiveResultSet` to re-read it?  
**Hint:** Not under the default single-subscription-only publisher; create a new publisher or use bounded sharing/caching.

**Q19.** What does `Flux.defer(() -> session.executeReactive(stmt))` change for retries?  
**Hint:** Creates a fresh publisher/request per subscription, so retries re-execute CQL.

**Q20.** How many rows does a reactive `INSERT` normally emit?  
**Hint:** 0 rows; success is signaled by Publisher completion, not `onNext` counts.

**Q21.** Why isn't `Flux.from(insert).count()` a valid count of successful writes?  
**Hint:** It counts emitted row items, and successful `INSERT`s emit none.

**Q22.** If a `flatMap` write runs with `concurrency=8` and downstream cancels, are those 8 in-flight writes guaranteed halted?  
**Hint:** No; already-sent writes may keep running, while unsubscribed ones are avoided.

**Q23.** Why must a write-heavy reactive pipeline bound concurrency?  
**Hint:** Cassandra's native protocol does not apply Reactive Streams backpressure directly to server write ingress; excess messages overload the cluster.

**Q24.** Is `Flux.timeout(Duration.ofSeconds(2))` a hard 2-second deadline across a 100-page stream?  
**Hint:** Not by default; it typically measures idle intervals between emitted items.

**Q25.** Does `CompletableFuture.orTimeout` stop a server query?  
**Hint:** No; it completes the JDK Future with `TimeoutException`, not a server-side kill.

**Q26.** How do `DriverTimeoutException` and `ReadTimeoutException` differ?  
**Hint:** Client deadline vs. server/coordinator read timeout; both can appear under different failure conditions.

**Q27.** Why can an HTTP 504 still coincide with a newly written row in Cassandra?  
**Hint:** The gateway gave up waiting while the mutation/ACK still finished on the server.

**Q28.** Besides cancellation, what prevents a retried order-creation POST from creating two rows?  
**Hint:** Stable operation ID / idempotency key, source of truth, and versioning/dedup/outbox/reconciliation.

**Q29.** Does `setIdempotent(true)` magically make a counter increment idempotent?  
**Hint:** No; the flag only guides driver retries/speculation without changing CQL semantics.

**Q30.** Did a request that timed out in the throttler queue necessarily reach a coordinator?  
**Hint:** No; timeouts can occur before network writes, though telemetry/version evidence is needed to confirm a specific request was unsent.

**Q31.** Which async-cancellation bug was noted in the Java Driver 4.19 changelog?  
**Hint:** `JAVA-3149` — async query cancellation not propagated properly to the request throttler in earlier versions, fixed in 4.19.

**Q32.** Does `RequestThrottlingException` prove Cassandra returned `OverloadedException`?  
**Hint:** No; the client-side driver throttler rejected it, whereas `OverloadedException` comes from the server.

**Q33.** If speculative execution wins on node B, does node A definitely stop reading immediately?  
**Hint:** No; "cancelling" the losing execution mainly discards its late response on the client.

**Q34.** Why should you never call `CqlSession.close()` when one HTTP client disconnects?  
**Hint:** The session is a shared resource; closing it breaks other requests and does not guarantee server rollback.

**Q35.** When cancel ratio rises while CQL QPS stays flat, what should you investigate?  
**Hint:** Cancels may fire too late, fail to reach paging loops, cancel only child futures, or speculation/retries/prefetching may inflate message counts.

**Q36.** Which two metrics reveal stream ID pressure caused by cancels and speculation?  
**Hint:** `pool.orphaned-streams` and `pool.available-streams`, alongside `pool.in-flight`/connections.

**Q37.** An unsubscribed reactive statement logs "created publisher." Did the write run?  
**Hint:** No; publishers are cold and require subscription.

**Q38.** Why use monotonic time to compute remaining HTTP deadlines?  
**Hint:** Avoids wall-clock jumps/adjustments; UTC timestamps are for correlation, not duration math.

**Q39.** Does cancelling a reactive stream clear tombstones, flush queues, or compaction backlogs?  
**Hint:** No; storage lifecycle work continues inside Cassandra.

**Q40.** Can an operation be both `CANCELLED_CLIENT` and `RECONCILED_SUCCESS`?  
**Hint:** Yes; the client cancelled before ACK, and later business reconciliation confirmed the write applied.

## 27. Summary: Memorable Limits of Cancellation

~~~text
                     JAVA APPLICATION
                            |
                 Choose execution model
                    /             \
             ASYNC FUTURE        REACTIVE
              eager send       cold publisher
                    |               |
           executeAsync()       subscribe()
                    |               |
               request starts / sends CQL
                            |
                 Cancel/timeout/disconnect
                            |
              +-------------+-------------+
              |                           |
      CLIENT-SIDE OUTCOME           SERVER-SIDE WORK
      Cancel future/result         Coordinator/replicas
      Stop demand/paging           May have received CQL
      Discard late response        May be reading/writing
      Mark UNKNOWN write           ACK may arrive late
              |                           |
              +-------------+-------------+
                            |
                  Observability + audit
                            |
            READ: stop unstarted page fetches
            WRITE: reconcile by operation ID
                            |
                     SLO + correctness
~~~

### 27.1. Six Practical Principles

1. **Avoid unnecessary requests upfront:** check deadlines/cancellation before `executeAsync` or subscribing, and before every page fetch.
2. **Never confuse Future cancellation with server rollback:** `cancel(true/false)` and `dispose()` reflect client lifecycle only.
3. **Reactive `SELECT`:** backpressure paces **subsequent pages**, without halting server work already running for the current page.
4. **Reactive `WRITE`:** enforce concurrency/rate limits; stopping the subscriber never reverts already-sent mutations.
5. **Write outcomes:** design idempotency and reconciliation for disconnects, timeouts, and missing ACKs.
6. **Observe both sides:** pair app cancel/timeout metrics with node messages, orphaned streams, server read/write latencies, and business data state.

**Core message:** Cassandra Java Driver 4.x lets Java applications **stop waiting**, **stop consuming**, or **avoid dispatching** remaining work. Yet for CQL already sent over the native protocol, **you cannot treat a cancelled Future or subscription as confirmation that coordinators or replicas stopped**. Safety depends on dispatch timing, read/write semantics, idempotency keys, CL/RF, deadlines, and verifying final state.

## References

- [Apache Java Driver 4.18 — Async programming](https://apache.github.io/cassandra-java-driver/4.18.0/core/async/) — `CompletionStage`, I/O thread callbacks, and async error handling.
- [Apache Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/) — `AsyncResultSet.currentPage`/`fetchNextPage`, paging state, and read pagination.
- [Apache Java Driver 4.18 — Reactive Streams](https://apache.github.io/cassandra-java-driver/4.18.1/core/reactive/) — cold/unicast publishers, subscriptions, backpressure, bounded write concurrency, and retry/defer.
- [Apache Java Driver 4.18 — Speculative execution](https://apache.github.io/cassandra-java-driver/4.18.1/core/speculative_execution/) — cancelling losing executions, no server-side in-flight cancellation, `pool.orphaned-streams`.
- [Apache Java Driver 4.18 — Non-blocking](https://apache.github.io/cassandra-java-driver/4.18.1/core/non_blocking/) — I/O threads and async/reactive non-blocking guarantees.
- [Apache Java Driver 4.18 — Idempotence](https://apache.github.io/cassandra-java-driver/4.18.1/core/idempotence/) — retries/speculation and side effects.
- [Apache Java Driver 4.18 — Metrics](https://apache.github.io/cassandra-java-driver/4.18.1/core/metrics/) — session/node metrics, pool streams, retries, and speculative executions.
- [DataStax Java Driver 4.17 — Request throttling](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/throttling/) — client throttler, deadline including queue wait, `RequestThrottlingException`.
- [DataStax Java Driver 4.17 — Reference configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — request timeouts and Netty/metrics/throttler options.
- [DataStax Java Driver 4.17 — ReactiveResultSet Javadoc](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveResultSet.html) — Publisher contract, single subscription, I/O thread considerations.
- [DataStax Java Driver 4.17 — AsyncResultSet Javadoc](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/AsyncResultSet.html) — async pages and fetching next.
- [DataStax Java Driver 4.17 — DriverTimeoutException Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/DriverTimeoutException.html) — client deadline vs. server READ/WRITE_TIMEOUT.
- [Apache Java Driver — Changelog](https://github.com/apache/cassandra-java-driver/blob/trunk/changelog/README.md) — 4.19 fix `JAVA-3149` for async query cancellation / request throttler.
- [Apache Cassandra — Native protocol v5](https://cassandra.apache.org/doc/latest/cassandra/reference/native-protocol.html) — QUERY/EXECUTE/RESULT, stream IDs, and message model.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — coordinator, natural replicas, RF, CL, and token routing.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — server read/write latency, compaction, and thread pools.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-driven design, partitioning, and avoiding hotspots.
- [DataStax Enterprise — ContinuousAsyncResultSet](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/dse/driver/api/core/cql/continuous/ContinuousAsyncResultSet.html) — cancellation API **specific to continuous paging**, not ordinary Cassandra CQL.
