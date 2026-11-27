# Timeout budgets across multiple downstream calls

## Lesson objectives

In **SPRING_GRPC**, an inbound request often calls multiple downstream services sequentially or in parallel. If each hop sets its own full timeout as if it were starting a brand-new request, total processing time can far exceed the deadline granted by the caller. Requests can keep running even after the caller has timed out, tying up threads, connections, and resources while the result will never be used.

This lesson focuses on **timeout budgets across multiple downstream calls**: understanding end-to-end deadlines, allocating time for queueing and local processing, propagating remaining deadlines to each RPC, enforcing per-dependency timeout caps, coordinating retries/backoff with the shared budget, cancelling work upon expiration, and testing the full call chain.

After this lesson, you will be able to:

1. Distinguish per-hop timeouts from end-to-end deadlines.
2. Calculate budgets for sequential and parallel downstream calls.
3. Read the active deadline from gRPC Context and propagate it to client stubs.
4. Apply per-dependency timeout caps without exceeding the parent request's deadline.
5. Reserve budget for queueing, serialization, and response delivery.
6. Stop retries when insufficient time remains or an operation is unsafe.
7. Propagate cancellation and release resources when deadlines expire.
8. Observe deadline exhaustion and test budgets across multiple services.

> **Scope:** Examples use gRPC Java, Spring, and generated stubs. Deadlines are represented by `io.grpc.Deadline`; remaining time is computed via a monotonic ticker. Per-dependency timeouts are application-defined policies, not default properties of every Spring gRPC starter.

## 1. Per-hop timeouts and end-to-end deadlines

A **timeout** is typically the time limit of a specific operation, such as connecting to a database or calling Inventory Service. A **deadline** is the absolute point in time by which the entire RPC must finish. When a request traverses multiple services, the end-to-end deadline is the budget that matters to the caller.

For example, an Order request has an 800 ms deadline and performs:

1. Queue/admission: 40 ms.
2. Profile lookup: up to 120 ms.
3. Inventory call: up to 250 ms.
4. Pricing call: up to 180 ms.
5. Processing and response serialization: 70 ms.

The expected worst-case sum is 660 ms. The remaining 140 ms is headroom for network jitter, scheduling, response delivery, and measurement error. If each downstream set its own 800 ms timeout, the sequential chain could stretch beyond 1.6 seconds, violating the caller's deadline.

| Concept | Meaning | Example |
| --- | --- | --- |
| Connect timeout | Time to establish a connection | DNS/TLS/channel connection |
| Per-call timeout | Dedicated limit for one dependency call | Inventory max 250 ms |
| End-to-end deadline | Final completion point from the caller | Total request no more than 800 ms |
| Queue timeout | Time waiting to enter a worker/pool | Never wait indefinitely |
| Idle timeout | Duration a stream has no activity | Bounding silent streams |
| Retry budget | Time/attempts allocated to retries | Retry only while time remains |

A hop's timeout must fit inside the parent request's deadline. A per-call timeout may be shorter than the remaining deadline, but must never extend the end-to-end deadline.

## 2. Building a budget along the critical path

For sequential operations, required time is approximately the sum of each step's duration:

```text
D_total >= Q + L_local + D1 + D2 + ... + Dn + S + R
```

Where:

- `Q`: queue/admission wait.
- `L_local`: local processing.
- `D1..Dn`: downstream call durations.
- `S`: serialize/deserialize.
- `R`: response delivery and safety reserve.

For parallel downstream calls, total duration of the parallel branch is governed by the slowest branch, not the sum of all branches:

```text
D_total >= Q + L_local + max(D1, D2, ..., Dn) + S + R
```

If parallel branches contain sequential dependencies internally, compute the critical path of each branch first and then take the largest branch. Do not sum all parallel durations, but also do not assume full parallelism if executors, connection pools, or rate limits force branches to wait on each other.

### 2.1. Example budget allocation

Suppose the inbound deadline has 900 ms remaining when the service starts:

| Phase | Target budget |
| --- | ---: |
| Admission/queue | 50 ms |
| Local processing | 80 ms |
| Customer downstream | 180 ms |
| Inventory downstream | 300 ms |
| Pricing downstream | 160 ms |
| Serialize and response | 50 ms |
| Safety reserve | 80 ms |
| Total | 900 ms |

If Inventory actually takes 260 ms, the remaining budget for subsequent steps shrinks accordingly. Do not reset the Pricing timeout back to 160 ms if earlier steps consumed more time than planned.

A budget is an upper bound and design target, not a promise that each hop gets to consume its entire allocation. If one dependency finishes early, the saved time becomes available to later steps within the parent deadline.

## 3. Deadline propagation in gRPC Java

gRPC Java stores the current RPC's deadline/cancellation in `io.grpc.Context`. Inside a server handler, read the active deadline via `Context.current().getDeadline()`. When creating downstream calls inside that context, gRPC Java can apply the context's deadline automatically; this relies on the context still being active when the call is created.

To make the budget explicit and easy to test, pass the deadline directly to the stub:

```java
Deadline inboundDeadline =
        io.grpc.Context.current().getDeadline();

if (inboundDeadline == null) {
    throw Status.FAILED_PRECONDITION
            .withDescription("Inbound RPC is missing a deadline")
            .asRuntimeException();
}

InventoryGrpc.InventoryBlockingStub inventoryStub =
        InventoryGrpc.newBlockingStub(inventoryChannel)
                .withDeadline(inboundDeadline);

GetStockResponse response =
        inventoryStub.getStock(request);
```

An API can adopt a default-deadline policy for callers that omit a deadline, but it must apply that policy immediately at the boundary and document it. For critical service-to-service APIs, requiring callers to send a finite deadline generally makes behavior more predictable.

Never store a deadline in a static field or mutable singleton state. A deadline belongs to one specific RPC and must stay attached to that request's execution context.

### 3.1. Do not reset timeouts at each hop

Anti-pattern:

```java
// Wrong: every hop gets a fresh 800 ms.
InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(channel)
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS);
```

If the request has already spent 500 ms before calling Inventory, this still grants another 800 ms. Downstream can keep running after the caller's deadline has expired.

The right pattern is passing the current absolute deadline:

```java
Deadline parentDeadline =
        io.grpc.Context.current().getDeadline();

InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(channel)
                .withDeadline(parentDeadline);
```

If you need a shorter per-dependency timeout, combine the parent deadline with a dependency cap as shown next. Never convert a deadline into a fresh fixed duration at each tier.

## 4. Applying per-dependency timeout caps

Each downstream service can have its own latency profile and SLA. For example, Inventory has a 300 ms cap and Pricing has a 150 ms cap. The effective deadline is the earlier of the parent deadline and the dependency cap.

gRPC `Deadline` supports taking the minimum of two deadlines:

```java
static Deadline effectiveDeadline(
        Deadline parent,
        Duration dependencyCap) {

    Deadline dependencyDeadline =
            Deadline.after(
                    dependencyCap.toNanos(),
                    TimeUnit.NANOSECONDS);

    return parent.minimum(dependencyDeadline);
}
```

Using it with a stub:

```java
Deadline parent =
        io.grpc.Context.current().getDeadline();

if (parent == null) {
    throw Status.FAILED_PRECONDITION
            .withDescription("Missing inbound deadline")
            .asRuntimeException();
}

Deadline inventoryDeadline =
        effectiveDeadline(parent, Duration.ofMillis(300));

InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(inventoryChannel)
                .withDeadline(inventoryDeadline);
```

If the parent deadline has 90 ms left, the effective deadline is still at most 90 ms. The 300 ms dependency cap cannot extend the parent deadline. If the dependency cap is shorter, the call stops early so the service still has a chance to fall back or return a response before the overall deadline.

### 4.1. Checking remaining budget before calling

You can read the remaining time:

```java
long remainingNanos =
        parent.timeRemaining(TimeUnit.NANOSECONDS);

if (remainingNanos <= minimumUsefulCallNanos) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Insufficient budget for downstream call")
            .asRuntimeException();
}
```

`minimumUsefulCallNanos` is an application policy threshold based on minimum useful latency and the time needed to process the result. Do not start a call that is almost guaranteed not to finish before the deadline.

Do not use `System.currentTimeMillis()` to compute deadline deltas manually. `io.grpc.Deadline` uses a monotonic ticker to avoid skew when the wall clock changes.

## 5. Reserving budget for queueing and local processing

A common mistake is granting nearly the entire deadline to downstream calls and leaving no time to process the response. The budget must be accounted from the moment the request arrives at the service, including:

- Admission control and waiting for a worker.
- Lock contention or semaphore waits.
- Request deserialization and validation.
- Business computation.
- Downstream RPC/database calls.
- Response serialization and delivery back to the caller.

If queue wait consumes 200 ms of a 500 ms budget, downstream no longer has 500 ms. When offloading work to an executor, preserve the deadline across thread boundaries and check it before starting the task.

Example passing gRPC Context to a worker:

```java
io.grpc.Context grpcContext =
        io.grpc.Context.current();

executor.execute(grpcContext.wrap(() -> {
    Deadline deadline = grpcContext.getDeadline();

    if (deadline != null && deadline.isExpired()) {
        return;
    }

    performBusinessWork();
}));
```

If the executor rejects the task, map the rejection per your capacity policy. If the task's deadline has already expired before execution starts, skip the work and release permit/queue accounting. Never keep expired tasks in a queue only to run them and discover the result is no longer useful.

## 6. Sequential and parallel downstream calls

### 6.1. Sequential calls

If the service calls Customer and then Pricing, the second call must use the deadline remaining after the first call. Passing the same absolute deadline is the simplest approach:

```java
Deadline deadline = Context.current().getDeadline();

Customer customer = customerStub
        .withDeadline(deadline)
        .getCustomer(customerRequest);

Price price = pricingStub
        .withDeadline(deadline)
        .getPrice(buildPriceRequest(customer));
```

Pricing receives the exact same absolute deadline, not the original duration again. If Customer takes longer, Pricing automatically gets less time. You can layer an individual cap using `minimum` as shown earlier.

### 6.2. Parallel calls

When calling multiple independent dependencies, initiate each call with the effective deadline derived from the same parent deadline. Await results using the shared remaining budget, not by awaiting each `Future` with a fresh full-budget timeout.

```java
Deadline parent = Context.current().getDeadline();

Future<Customer> customerFuture =
        executor.submit(() ->
                customerStub.withDeadline(parent)
                        .getCustomer(customerRequest));

Future<Price> priceFuture =
        executor.submit(() ->
                pricingStub.withDeadline(parent)
                        .getPrice(priceRequest));

long remaining =
        parent.timeRemaining(TimeUnit.NANOSECONDS);

Customer customer = customerFuture.get(
        remaining, TimeUnit.NANOSECONDS);

remaining = parent.timeRemaining(TimeUnit.NANOSECONDS);

Price price = priceFuture.get(
        remaining, TimeUnit.NANOSECONDS);
```

This is a simplified skeleton. Production code must handle `ExecutionException`, `TimeoutException`, cancellation, and cleanup of both `Future`s. If one branch fails and makes the overall result impossible to build, cancel the other branch if it is no longer needed. If both results are mandatory, the overall deadline must cover the critical path plus response processing.

Never call `Future.get()` sequentially with the same initial timeout duration; doing so can wait twice the budget. Always recompute remaining time from the parent deadline right before each wait.

## 7. Retries must consume the same budget

Retries must never create a fresh budget. The total time across attempts, backoff, queueing, and response delivery still sits inside the inbound deadline.

A retry policy should bound:

- Maximum attempt count.
- Total retry duration.
- Backoff and jitter.
- Retryable status codes.
- Idempotency or deduplication.
- Minimum remaining time needed for an attempt to be worthwhile.

Before each attempt, compute remaining time from the same parent deadline. If less than `minimumUsefulAttemptBudget` remains, stop retrying and return an appropriate final error.

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    long remaining =
            parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);

    if (remaining <= minimumAttemptBudgetNanos) {
        throw Status.DEADLINE_EXCEEDED
                .withDescription("Retry budget exhausted")
                .asRuntimeException();
    }

    try {
        return stub.withDeadline(parentDeadline)
                .getStock(request);
    } catch (StatusRuntimeException ex) {
        if (!isRetryable(ex.getStatus())
                || attempt == maxAttempts) {
            throw ex;
        }

        long backoff = computeBackoffWithJitter(attempt);
        if (backoff >= parentDeadline.timeRemaining(
                TimeUnit.NANOSECONDS)
                - minimumAttemptBudgetNanos) {
            throw ex;
        }

        sleepInterruptibly(backoff);
    }
}
```

This is Java-like pseudocode; `sleepInterruptibly` must preserve interrupt status and handle cancellation. In production, prefer a retry framework/client policy with deadline-aware scheduling over blocking sleep on a gRPC callback thread.

Never retry `INVALID_ARGUMENT`, `PERMISSION_DENIED`, or static payload errors. For `UNAVAILABLE`/`RESOURCE_EXHAUSTED`, retry only when the operation is safe and policy permits. Non-idempotent retries require an idempotency key or provider-side deduplication.

## 8. Cancellation when the deadline expires

When the inbound deadline expires or the caller cancels the RPC, the service should stop work that is no longer useful. gRPC `Context` carries a cancellation signal; downstream calls created inside the appropriate context can receive cancellation propagation. For tasks running on an executor, preserve the gRPC `Context` and provide a way to stop active work.

Principles:

1. Check `Context` cancellation before starting expensive steps.
2. Propagate the same deadline/cancellation context downstream.
3. When the parent call finishes, cancel any still-running `Future` or downstream operation that is no longer needed.
4. Release semaphores/permits and connections/resources exactly once.
5. Never invoke multiple terminal callbacks on the same observer.
6. Do not swallow interrupts if workers are designed to stop on interrupt.
7. Never continue retrying after deadline expiration/cancellation.

Example linking gRPC `Context` cancellation to a worker `Future`:

```java
io.grpc.Context rpcContext = io.grpc.Context.current();

Future<Result> work = executor.submit(
        rpcContext.wrap(this::performWork));

io.grpc.Context.CancellationListener listener =
        cancelledContext -> work.cancel(true);

rpcContext.addListener(listener, Runnable::run);
try {
    return work.get();
} finally {
    rpcContext.removeListener(listener);
}
```

This pattern illustrates workers that stop via interrupts. If the work uses async APIs, invoke the dependency's corresponding cancellation API. The listener must be removed on the terminal path; resource cleanup and permit release must be guarded to run only once.

Cancelling a `Future` does not guarantee every downstream library stops immediately. Database drivers, blocking I/O, or external APIs require their own timeout/cancellation support. Verify the actual semantics of each dependency.

## 9. Timeouts and status mapping

Status codes must distinguish causes:

| Situation | Common status | Meaning |
| --- | --- | --- |
| Inbound deadline expired | DEADLINE_EXCEEDED | Caller budget exhausted |
| Client actively cancelled | CANCELLED | Operation is no longer requested |
| Downstream temporarily unavailable | UNAVAILABLE | Dependency cannot serve temporarily |
| Capacity exhausted | RESOURCE_EXHAUSTED | Admission/quota/resource limit |
| Invalid request | INVALID_ARGUMENT | Fix input |
| Missing/invalid credentials | UNAUTHENTICATED | Authentication failed |
| Identity lacks permission | PERMISSION_DENIED | Do not retry with same identity |
| Unexpected failure | INTERNAL | Unclassified server failure |

Do not map every downstream timeout to `UNAVAILABLE`. If the overall deadline has expired, `DEADLINE_EXCEEDED` accurately reflects that the caller has no budget left. If a dependency cap was shorter than the overall deadline and expired first, the service can return `DEADLINE_EXCEEDED` or an appropriate domain status per the public API contract; keep the mapping consistent and record the detailed cause in telemetry.

Never return stack traces or internal hostnames/credentials in the `Status` description. Record redacted details in logs/traces.

## 10. Streaming RPCs and long-lived deadlines

Streaming RPCs have a longer lifecycle than unary calls. A deadline typically bounds the entire RPC stream rather than resetting per message. Distinguish:

- Overall stream deadline.
- Idle timeout between messages.
- Per-message processing budget.
- Downstream call budget triggered while handling a message.

Do not reset the overall deadline each time a message arrives unless the contract defines a new session. If each message calls a downstream service, use the stream's remaining deadline combined with a dedicated cap for that operation.

For long-running streams, clients may need to split sessions by time or reconnect/resume via a cursor. Never keep an unbounded stream open to evade deadlines. Apply flow control, bounded buffers, and cancellation to prevent streams from holding unbounded memory/threads/connections.

## 11. Configuring deadline policies in Spring

Per-dependency caps can be bound via `@ConfigurationProperties`. For example, the `app.grpc.deadlines` namespace is application-defined:

```yaml
app:
  grpc:
    deadlines:
      default-inbound: 2s
      minimum-useful-call: 25ms
      safety-reserve: 60ms
      dependencies:
        inventory: 350ms
        pricing: 180ms
        customer: 220ms
```

Values must be grounded in actual latency distributions, SLOs, and capacity. Do not copy one shared configuration across every method if workloads differ substantially.

A policy object can expose dependency caps and reserves:

```java
@ConfigurationProperties(prefix = "app.grpc.deadlines")
public record GrpcDeadlineProperties(
        Duration defaultInbound,
        Duration minimumUsefulCall,
        Duration safetyReserve,
        Map<String, Duration> dependencies) {
}
```

Validate that every `Duration` is positive, finite, and within allowed bounds. Verify that dependency caps do not exceed the service policy if that would be misleading; the effective deadline is always the minimum with the parent deadline anyway.

## 12. Observability for budgets

To see where deadline budget is spent, measure these checkpoints:

- Remaining inbound deadline when the service starts.
- Queue/admission wait time.
- Local processing duration.
- Each downstream call duration and remaining budget before the call.
- Retry count and backoff duration.
- Cancellation/deadline-exceeded counts.
- Total inbound RPC duration.
- Operations that continue running after cancellation, if measurable.

Record span events or low-cardinality attributes:

- `dependency.name`.
- `timeout.policy`.
- `retry.attempt`.
- `remaining_budget_ms` bucketed.
- `deadline.outcome`.

Never use raw request IDs, tenant IDs, or trace IDs as metric labels. Avoid recording absolute deadline timestamps unless needed; remaining duration and outcome are usually more informative.

Dashboards should separate individual downstream latencies from total inbound latency. If total latency is high while downstream spans are short, check queue waits, local locks, serialization, or response scheduling.

## 13. Testing timeout budgets

Testing a single downstream service in isolation is not enough. You must test multi-hop chains to prove deadlines are not reset.

Test scenarios:

1. **Sequential calls:** the first downstream consumes part of the budget; the second receives only the remaining deadline.
2. **Parallel calls:** total wait time is bounded by the parent deadline, not the sum of individual `Future` timeouts.
3. **Dependency cap:** a cap shorter than the parent deadline ends the call early.
4. **Shorter parent budget:** the parent deadline is shorter than the cap; the cap never extends the request.
5. **Queue delay:** a task waits too long; no downstream call starts once insufficient budget remains.
6. **Retry:** every attempt uses the same deadline; backoff never exceeds the budget.
7. **Cancellation:** caller cancels; downstream calls and workers are cancelled/cleaned up.
8. **Streaming:** overall deadline does not reset per message.
9. **Missing deadline:** default policy or rejection is applied consistently.
10. **Concurrent requests:** one request's deadline/context never leaks to another request.

Use `InProcessServerBuilder`/`InProcessChannelBuilder` for gRPC logic, plus latches and fake downstreams to control latency. Avoid fixed sleeps; use `CountDownLatch`, barriers, and bounded test timeouts. Use a fake clock/ticker if application policy code supports injection; gRPC `Deadline` also supports a test ticker when deterministic time behavior is required.

### 13.1. Asserting deadline propagation

You can record the remaining deadline at a fake downstream server when requests arrive and verify:

- Downstream deadline is no later than the parent deadline.
- Remaining budget decreases according to elapsed time.
- A downstream cap can be shorter than the parent.
- Calls are cancelled when the parent deadline expires.
- No new attempt starts after the retry budget is exhausted.

Do not assert exact milliseconds in CI because schedulers and transports introduce jitter. Assert relationships and upper bounds with reasonable tolerance.

## 14. Common issues and how to handle them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Three-hop chain exceeds caller deadline | Each hop sets a fresh timeout equal to the full budget | Propagate the absolute parent deadline |
| Downstream keeps running after caller times out | Context/cancellation not propagated or dependency ignores cancel | Preserve gRPC Context, cancel Future, and set dependency timeouts |
| Retries multiply total request duration | Each attempt uses a fresh timeout | Share the same deadline and retry budget |
| Parallel calls exceed budget | Each Future waits a full timeout sequentially | Recompute remaining from parent before each wait |
| Dependency cap makes overall request longer | Cap used instead of parent deadline | Take minimum of parent deadline and dependency deadline |
| Queue exhausts budget | Queue wait unmeasured or unchecked before worker runs | Admission control, bounded queue, and check remaining |
| Blocking sleep stalls callback thread | Retry/backoff runs on transport thread | Use scheduler/async retry policy |
| Streaming RPC never terminates | Overall deadline reset per message | Keep overall deadline and separate idle timeout |
| Inbound deadline missing | Caller sends no deadline | Apply default policy or require finite deadline |
| Inconsistent status mapping | All downstream errors mapped to UNAVAILABLE | Distinguish DEADLINE_EXCEEDED, CANCELLED, and UNAVAILABLE |
| Flaky tests | Sleep and exact timing assertions | Use latches/fake ticker and deadline relationships |
| Worker/permit leaked after timeout | Cleanup skipped on cancel/exception | Release in terminal path exactly once |

## 15. Practice exercises

1. Build an `OrderService` that calls Customer, Inventory, and Pricing sequentially.
2. Set a finite inbound deadline from the generated client stub.
3. Read the deadline from gRPC `Context` in the server handler.
4. Propagate the exact same absolute deadline to each downstream stub.
5. Add a dependency cap using the minimum of the parent deadline and the per-service deadline.
6. Reserve a safety margin for serialization/response and check minimum useful budget before each call.
7. Add retries for allowed transient errors using the same deadline and backoff/jitter.
8. Cancel downstream `Future`/calls when the inbound request is cancelled or its deadline expires.
9. Create a variant calling two downstreams in parallel and prove critical-path budgeting.
10. Add metrics/span events for remaining budget, queue wait, dependency duration, and retries.
11. Write integration tests for sequential, parallel, dependency cap, retry exhaustion, and cancellation scenarios.
12. Write a runbook analyzing `DEADLINE_EXCEEDED` hop by hop to pinpoint where budget is consumed.

### Self-check questions

- How does a per-hop timeout differ from an end-to-end deadline?
- Why must each downstream never be granted the full initial timeout again?
- How does the budget formula differ between sequential and parallel calls?
- Where does gRPC Java store the active deadline?
- Why is using an absolute `Deadline` better than recomputing deltas from the wall clock?
- How do you enforce a dependency cap without exceeding the parent deadline?
- Do queue wait and serialization need to be included in the budget?
- How do retries and backoff consume the budget?
- When must retries stop even if the status is retryable?
- How should inbound RPC cancellation affect downstreams and workers?
- How does a stream's overall deadline differ from an idle timeout and a per-message budget?
- How can a test prove deadlines are not reset across multiple hops?

## References

- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/): deadline, propagation, and timeout behavior.
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/): stopping RPCs and unneeded work.
- [gRPC — Retry](https://grpc.io/docs/guides/retry/): retry policies and backoff.
- [gRPC Java — Deadline](https://grpc.github.io/grpc-java/javadoc/io/grpc/Deadline.html): deadline and remaining time.
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): deadline/cancellation context.
- [gRPC Java — AbstractStub](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/AbstractStub.html): configuring deadlines on generated stubs.
- [Google SRE — Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): timeout, overload, and retry behavior.
- [Google SRE — Handling Overload](https://sre.google/sre-book/handling-overload/): admission control and capacity protection.
- [OpenTelemetry — Semantic Conventions for RPC](https://opentelemetry.io/docs/specs/semconv/rpc/): RPC observability and status attributes.

**Expected outcome:** Learners can design end-to-end timeout budgets for Spring gRPC across multiple downstream calls, propagate the remaining absolute deadline instead of resetting timeouts, enforce dependency caps, account for queueing/retries/serialization, cancel work when budget expires, and test sequential, parallel, and streaming chains without exceeding the caller's deadline.
