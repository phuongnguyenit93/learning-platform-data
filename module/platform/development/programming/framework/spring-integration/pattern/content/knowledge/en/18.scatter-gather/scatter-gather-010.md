# Limiting Branch Count and Resources

## 1. Why does Scatter-Gather need limits?

An order-pricing system receives a `QuoteRequest` and concurrently queries three sources:

1. **Inventory**: is stock available?
2. **Pricing**: current price and discount tier.
3. **Shipping**: shipping fee and delivery time.

Then the system **gathers** the three results into a `QuoteResult`. If each request spawns three branches, 200 requests/second can create **600 branch tasks/second**. When Pricing slows down from 100 ms to 2 seconds, pending tasks surge; if the system uses unbounded queues and holds message groups indefinitely, memory, thread pools, and response times can degrade even while routing logic remains correct.

~~~mermaid
flowchart LR
    Q["QuoteRequest"] --> SC{"Scatter"}
    SC --> A["Inventory"]
    SC --> B["Pricing"]
    SC --> C["Shipping"]
    A --> G{"Gather"}
    B --> G
    C --> G
    G --> R["QuoteResult / Gateway reply"]
~~~

**Limiting branch count and resources** means designing **controlled fan-out**: each request dispatches only to valid branches, executing and queued work are bounded, and Gather has clear deadlines/cleanup. The goal is not only avoiding `OutOfMemoryError`, but ensuring a slow branch or high-volume tenant **cannot congest the entire system**.

This lesson belongs to the **Scatter gather** chapter of the **SPRING_INTEGRATION_PATTERN** module, serving the goal of learning to implement **Enterprise Integration Patterns** with Spring Integration: building loosely coupled, extensible message flows; practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, alongside testing and monitoring processing branches.

After this lesson, you can distinguish branch count from concurrency, plan resources for Scatter-Gather, configure bounded flows, encode errors/deadlines into the Gather contract, bound retries and duplicates, and test overload, missing branches, or late responses.

## 2. Scatter-Gather has two halves and two kinds of cost

**Scatter** sends one request to multiple recipients. **Gather** matches related replies by correlation and release strategy. In Spring Integration, this pattern includes `ScatterGatherHandler` with a scattering side (often based on `RecipientListRouter` or `PublishSubscribeChannel`) and a gathering side (Aggregator).

| Phase | What is consumed? | Risk if unbounded |
|---|---|---|
| Building recipient list | Route config, selection logic | Fan-out inflated excessively or manipulated |
| Scatter | Dispatch, serialization, connections, threads | One request triggers a message storm or too many tasks |
| Branch execution | CPU, DB pools, HTTP connections, broker consumers | Slowness, timeouts, rate limits, resource contention |
| Gather | Message groups, correlation metadata, memory/store | Holding too many incomplete groups, resource leaks |
| Reply | Gateway threads, deadlines, output queues | Caller timeouts, late results, double emission |
| Retry/recovery | Schedulers, queues, DLQs, state stores | Load amplification and duplicates |

**One-sided limits are not enough**: capping at four recipients per request can still spawn tens of thousands of tasks if ingress is wide open; bounding a thread pool can still cause `OutOfMemoryError` if queues/gather stores are unbounded; setting a Gateway timeout can still leave workers making network calls and creating side effects.

## 3. Distinguishing fan-out, concurrency, queue, and pending groups

Four quantities are frequently confused:

| Quantity | Symbol | Meaning |
|---|---:|---|
| **Fan-out** | `F` | Number of branches selected for *one* request |
| **Concurrency** | `C` | Number of branch tasks actively running at once |
| **Queued work** | `Q` | Number of accepted tasks not yet running |
| **Pending groups** | `G` | Number of Gather runs still waiting for results |

Example:

~~~text
1 request → F = 3 branches
10 concurrent requests → up to 30 branch tasks running or queued
Thread pool with 8 workers → actual C capped around 8 tasks
Queue of 100 tasks → Q capped at 100 if bounded
10 requests missing replies → G = 10 pending groups
~~~

Adding threads does not increase database connection limits. Reducing branches cuts task count yet does not replace timeouts. Meanwhile, bounding `G` must be handled separately if some branches never reply.

**Separate "request accepted" from "request completed":** accepting a request into a channel does not prove all three branches ran; completion must be measured by Gather logic, not `send()`'s boolean return value.

## 4. Three different architectures: synchronous, parallel, and broker-backed

| Deployment style | Characteristics | Limits to prioritize |
|---|---|---|
| **In-JVM synchronous Scatter** | Branches may run sequentially on the same thread | Total blocking time, Gateway deadline, branch timeout |
| **Scatter with Executor/Queue** | Branches run on worker threads | Bounded executor, queues, admission control, error paths |
| **Scatter over broker/services** | Each branch crosses an independent transport | Broker quotas, consumer concurrency, in-flight requests, reply correlation, durable state |

Do not interpret the word **scatter** as "runs in parallel automatically". A `PublishSubscribeChannel` without an executor can invoke subscribers synchronously. `RecipientListRouter` also does not automatically turn every handler into parallel jobs. Concurrency requires configuring execution boundaries (executors, queues, or independent consumers/services).

Conversely, **adding an executor does not solve everything**: if selecting 20 recipients with an 8-thread executor and a 1,000-slot queue, requests can still dump 20 tasks each into the backlog. The system must decide whether to admit or reject new requests when capacity runs short.

## 5. Principles for bounding fan-out before sending

**Never accept an arbitrary list of channels from an external payload or header.** The application should pick recipients from a configured, versioned, and tested set:

~~~text
Allowed branches:
  INVENTORY → quote.inventory
  PRICING   → quote.pricing
  SHIPPING  → quote.shipping
  FRAUD     → quote.fraud (high-risk orders only)

Normal order:    3 branches
High-risk order: 4 branches
Hard limit:      no more than 4 branches
~~~

**Mandatory branches** must never be dropped arbitrarily to meet load limits if doing so bypasses safety checks. For example, if fraud evaluation is mandatory for high-risk orders, never silently skip `FRAUD` because its queue is full and report success.

A *scatter plan* should be created **once per request**, carrying `requestId`, tenant scope, expected branch list, and deadline. Gather must know **this branch set** to determine when results are complete; never hardcode recipient count as a constant when branches toggle conditionally.

## 6. Java: creating a bounded branch plan without accepting free-form channel names

Minimal data model (Java 17+):

~~~java
enum QuoteBranch {
    INVENTORY, PRICING, SHIPPING, FRAUD
}

record QuoteRequest(
    String requestId,
    String tenantId,
    boolean highRisk,
    int lineCount
) {}

record ScatterPlan(
    String requestId,
    String tenantId,
    Set<QuoteBranch> required,
    Instant deadline
) {
    ScatterPlan {
        required = Set.copyOf(required);
    }
}
~~~

Building the plan from domain rules:

~~~java
final class ScatterPlanner {
    static final int MAX_BRANCHES = 4;

    ScatterPlan plan(QuoteRequest request,
                     Instant now,
                     Duration totalBudget) {
        if (request.requestId() == null
                || request.requestId().isBlank()
                || request.tenantId() == null
                || request.tenantId().isBlank()) {
            throw new IllegalArgumentException("MISSING_IDENTITY");
        }
        if (request.lineCount() <= 0
                || request.lineCount() > 500) {
            throw new IllegalArgumentException("INVALID_LINE_COUNT");
        }
        if (totalBudget.isZero() || totalBudget.isNegative()) {
            throw new IllegalArgumentException("INVALID_BUDGET");
        }

        EnumSet<QuoteBranch> branches = EnumSet.of(
            QuoteBranch.INVENTORY,
            QuoteBranch.PRICING,
            QuoteBranch.SHIPPING);
        if (request.highRisk()) {
            branches.add(QuoteBranch.FRAUD);
        }
        if (branches.size() > MAX_BRANCHES) {
            throw new IllegalStateException("TOO_MANY_BRANCHES");
        }
        return new ScatterPlan(
            request.requestId(),
            request.tenantId(),
            branches,
            now.plus(totalBudget));
    }
}
~~~

Points to note:

- `EnumSet` and `MAX_BRANCHES` guarantee no more than four branches in **one plan**.
- `Set.copyOf` creates a snapshot, preventing callers from mutating the list after dispatching the request.
- `requestId` must be issued stably at a trusted boundary and can be paired with attempt/revision when needed.
- `tenantId` only carries authorization meaning if authenticated; never trust client-asserted tenant IDs.
- `highRisk` is the output of a trusted evaluation step. If clients could set `highRisk=false`, the rule skipping FRAUD would be unsafe.
- `lineCount` has a cap to stop a request from bloating in size independently of fan-out.

**This is application planning code**, not an API provided automatically by Spring Integration. The next step must map each enum to the exact channel defined in config, never building bean names from raw strings sent by clients.

## 7. Content-based fan-out must not explode with item count

A common bug is placing Scatter-Gather **inside a Splitter** without accounting for item count:

~~~mermaid
flowchart TD
    IN["Order: 500 lines"] --> S["Splitter: 500 line messages"]
    S --> SC["Scatter each line to 4 services"]
    SC --> OUT["Up to 2,000 branch tasks"]
~~~

One external request can generate:

\[
F_{\mathrm{effective}}
= N_{\mathrm{items}}\times F_{\mathrm{perItem}}
\]

With 500 items and 4 branches per item, internal load hits **2,000 tasks** even though per-message fan-out never exceeded four.

To prevent unintended amplification:

1. Cap **item count** and **fan-out depth**.
2. If APIs support bulk queries, batch `N` items into chunks and query each chunk once.
3. Use shared caches or batch lookups with TTL/versioning and tenant scoping.
4. Compute **total expected tasks for the request**, not just direct recipients.
5. Block unbounded recursion or routing loops.

**A local limit does not prove the entire flow is bounded** when Splitters, Nested Routers, retries, and multi-layer fan-out exist.

## 8. Estimating concurrency from throughput and latency

A capacity model using Little's Law:

\[
C_{\mathrm{inflight}}
\approx \lambda_{\mathrm{requests}}
\times F_{\mathrm{average}}
\times W_{\mathrm{branch}}
\]

Where `λ_requests` is requests/second, `F_average` is average branches/request, `W_branch` is average residence time of one branch task (seconds), and `C_inflight` is average concurrent tasks executing/awaiting reply.

Example **100 requests/second**, each with **4 branches**, average branch time **0.25 seconds**:

\[
C_{\mathrm{inflight}}\approx100\times4\times0.25=100
\]

That is an **average estimate**, not a recommendation to provision exactly 100 threads. Systems must account for p95/p99, bursts, contention, resource types, and queue delays. I/O-bound branches can wait a long time with little CPU; CPU-bound branches should be bounded near core counts.

If branch latency rises eightfold while traffic stays flat, pending task count can rise roughly proportionally before backpressure or timeouts kick in. Therefore **timeouts and admission control are part of capacity planning**, not optional extras.

## 9. Placing concurrency limits at the exact resource

A system may need multiple **bulkheads**:

| Resource | Sample limit | Risk when shared without isolation |
|---|---|---|
| Inventory HTTP client | 40 in-flight calls | Slow Pricing exhausts connection pool |
| Pricing service | 20 in-flight calls | Price requests pile up backlog and time out |
| Shipping provider | 12 in-flight calls | Hit by provider rate limits |
| Fraud service | 8 in-flight calls | High-risk branch starves for resources |
| Per-tenant requests | 10 active scatter plans | One tenant consumes all system capacity |
| Global scatter operations | 100 pending plans | Memory/store grows due to waiting groups |

Numbers are **illustrative**, not universal recommendations. Choose limits from real measurements and SLOs.

**Do not rely on just one global Semaphore** when branches have differing priorities. A separate bulkhead for Pricing stops slow Pricing from eating all of Inventory's slots. Still, maintain a **global ceiling** so the sum of independent bulkheads cannot exceed actual JVM/DB/network capacity.

If using a shared thread pool across all branches, one slow blocking branch can occupy most workers. Consider separate executors or async I/O clients with appropriate connection and in-flight limits.

## 10. Executors and queues: merely adding threads is not a solution

An `ExecutorChannel` or `PublishSubscribeChannel` with an executor moves dispatch onto worker threads. Yet **bounding threads does not mean bounding backlog**:

~~~text
Producer: generates 500 tasks/sec
Workers: complete 300 tasks/sec
Unbounded queue:
  backlog grows ~200 tasks/sec
  after 60 seconds: ~12,000 unrun tasks
~~~

As backlog grows, tasks can retain large payloads, headers, and object references. Simultaneously Gather holds many groups waiting for replies: memory usage climbs from **both queues and the group store**.

Sample bounded executor:

~~~java
@Bean(destroyMethod = "shutdown")
ThreadPoolExecutor branchExecutor() {
    return new ThreadPoolExecutor(
        8,                        // core threads
        8,                        // maximum threads
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(128),
        new ThreadPoolExecutor.AbortPolicy());
}
~~~

Once 8 workers and 128 queue slots fill, the executor **rejects new tasks** with `RejectedExecutionException`. That is a **capacity signal**; never catch it and silently spawn unbounded threads elsewhere.

**Distinguish carefully:** the executor ceiling in the example bounds **tasks accepted by this executor**, not all tasks across Kafka consumers, async HTTP clients, or other schedulers. Across separate adapters, each boundary needs consistent capacity policies.

## 11. Java: admission control must hold permits until tasks truly finish

A Semaphore bounds total accepted branch operations at a given moment. For example, acquire a permit **before submission** and release it when the worker finishes:

~~~java
record BranchOutcome(
    String requestId,
    QuoteBranch branch,
    boolean success,
    String value,
    String reasonCode
) {
    static BranchOutcome unavailable(
            String id, QuoteBranch branch, String reason) {
        return new BranchOutcome(
            id, branch, false, null, reason);
    }
}

final class BoundedBranchDispatcher {
    private final Semaphore permits = new Semaphore(64);
    private final Executor executor;

    BoundedBranchDispatcher(Executor executor) {
        this.executor = executor;
    }

    CompletableFuture<BranchOutcome> dispatch(
            QuoteRequest request,
            QuoteBranch branch,
            Function<QuoteRequest, BranchOutcome> operation) {
        CompletableFuture<BranchOutcome> result =
            new CompletableFuture<>();

        if (!permits.tryAcquire()) {
            result.complete(BranchOutcome.unavailable(
                request.requestId(), branch, "CAPACITY_EXCEEDED"));
            return result;
        }

        try {
            executor.execute(() -> {
                try {
                    result.complete(operation.apply(request));
                } catch (Exception failure) {
                    result.completeExceptionally(failure);
                } finally {
                    permits.release();
                }
            });
        } catch (RejectedExecutionException rejected) {
            permits.release();
            result.complete(BranchOutcome.unavailable(
                request.requestId(), branch, "EXECUTOR_REJECTED"));
        }
        return result;
    }
}
~~~

**What this code illustrates:** when no permit is available or the executor queue is full, the coordinator still receives a **structured outcome** to feed Gather or fail the request. Without an outcome, Gather could wait on a branch that was never submitted.

**Boundaries to complete for production:**

- The code uses one illustrative semaphore; apply **per-service/per-tenant/global** limits as needed.
- `CompletableFuture` here is **pure Java application code**, not the `ScatterGatherHandler` API. Bridge properly to message replies and correlation contracts.
- Permits are released in the worker's `finally`, **not released merely because a caller cancels a future** while the background task still runs.
- Define handling for severe errors on executor threads and never treat `CAPACITY_EXCEEDED` as a successful business value.
- If an operation can block forever, the semaphore stays held forever: **HTTP/DB client timeouts** and operational watchdogs are mandatory.
- Verify the executor's rejection policy does not run the task before rejecting; this holds for `ThreadPoolExecutor.AbortPolicy` shown here.

Never use fixed `Thread.sleep` as backpressure. It ties up threads without reducing admitted work or freeing memory.

## 12. Request-level admission control to avoid half-dispatched plans

Suppose a quote requires three mandatory branches. If the coordinator sends Inventory and Pricing successfully and then discovers no capacity remains for Shipping, it must handle **a partially executed plan**.

Two strategies:

| Strategy | Advantage | Cost |
|---|---|---|
| **Reserve budget for the whole plan** before Scatter | Avoids partial dispatch followed by quota refusal | May reserve capacity for a branch not yet running |
| **Admit per branch** and return failure outcome when full | Uses capacity flexibly | Gather must understand partial dispatch and failure outcomes |

If requiring *all-or-nothing*, **check capacity before scattering** and track plan state. If partial acceptance is valid, any un-dispatched branch must carry an official `SKIPPED_CAPACITY` or `FAILED_CAPACITY` status rather than "vanishing".

Pseudo-workflow example:

~~~text
Plan = [INVENTORY, PRICING, SHIPPING]

admit plan? NO
  → reject/429/503 per API contract or bounded queue
  → do not create an indefinite pending gather group

admit plan? YES
  → persist/record expected branches + deadline
  → scatter
  → gather each branch outcome
  → release per policy
~~~

**Do not equate 429 with 503 in every case:** HTTP status codes depend on cause and public contract. With message brokers, overload may lead to nack/requeue/DLQ requiring different policies; the same `RejectedExecutionException` in Java does not automatically dictate broker ack behavior.

## 13. Selecting recipients by policy, not arbitrary producer control

A dangerous input:

~~~json
{
  "requestId": "Q-101",
  "recipients": [
    "quote.inventory",
    "quote.pricing",
    "admin.internalChannel"
  ]
}
~~~

Never let clients control internal bean/channel lists directly. An API may allow **feature flags** such as "include shipping calculation?", yet the final decision should rest on:

- Authenticated caller and tenant permissions.
- Business invariants: mandatory branches cannot be disabled arbitrarily.
- Allowlists: fixed channels/recipients or ones registered via an approved control plane.
- Max fan-out and fan-out depth per request.
- Per-tenant limits and rate limits.
- Plan version so retries do not silently target a different branch set.

**The scatter plan is part of the correlation contract.** When branches vary dynamically, Gather must use **the expected recipients locked at dispatch time**, rather than reading the latest recipients from a changed config version.

## 14. Spring Integration: configuring bounded Scatter-Gather

In Spring Integration, the scatterer can use a **Recipient List Router** or **Publish-Subscribe Channel**; the gatherer uses an **Aggregator** mechanism. Exact configuration depends on your project's Java DSL/API version, yet the architecture should anchor these control points:

~~~mermaid
flowchart TD
    IN["quotes.in"] --> V["Filter / validate QuoteRequest"]
    V --> P["ScatterPlanner: 3 or 4 recipients"]
    P --> ADM{"Admission control"}
    ADM -->|"Insufficient capacity"| REJ["Overload outcome / reject"]
    ADM -->|"Admitted"| SC["ScatterGatherHandler"]
    SC --> I["inventory requests"]
    SC --> PR["pricing requests"]
    SC --> SH["shipping requests"]
    SC --> FR["fraud if mandatory"]
    I --> GA["Gather: expected branches, deadline"]
    PR --> GA
    SH --> GA
    FR --> GA
    GA --> OUT["quotes.result"]
~~~

Example **shell flow** for ingress and admission before Scatter-Gather:

~~~java
@Configuration
@EnableIntegration
class QuoteIngressFlow {

    @Bean
    IntegrationFlow validateAndAdmitQuotes(
            QuoteAdmissionService admissionService) {
        return IntegrationFlow.from("quotes.in")
            .filter(QuoteRequest.class,
                request -> request.requestId() != null
                    && !request.requestId().isBlank(),
                f -> f.throwExceptionOnRejection(true))
            .handle(QuoteRequest.class,
                (request, headers) ->
                    admissionService.prepareAndReserve(request))
            .channel("quotes.scatter.ready")
            .get();
    }
}
~~~

`QuoteAdmissionService` is **an application service you define**; `prepareAndReserve()` must return an appropriate non-null payload/message containing the plan, deadline, and lease/correlation metadata for the next flow. It must ensure resource leases are released **after Gather reaches a terminal outcome**, including timeouts/errors; the snippet above does not yet implement the lease lifecycle.

The subsequent `ScatterGatherHandler` must be configured with a bounded recipient list, error handling, reply channel, and gather timeout per **the actual API of your Spring Integration version**. Never accept raw target bean names or expressions from public payloads. There is no need to create separate channel subscriptions per tenant when governance-layer policies can handle it.

**Practical point:** when using a pub/sub scatterer, verify how sequence headers are marked; when using a recipient list, verify recipient count configuration and whether subscribers return replies. Never assume both produce identical metadata and release behavior without testing.

## 15. A request must have a clear **expected reply set**

Gather can only conclude "complete" if it knows which branches were actually required.

~~~text
Plan Q-101:
  expected = {INVENTORY, PRICING, SHIPPING}

Arrived replies:
  INVENTORY: OK
  PRICING:   OK
  SHIPPING:  TIMEOUT/FAILED
~~~

If `FRAUD` is conditional, never apply a fixed release count across all plans; if `SHIPPING` was never dispatched due to capacity, do not pretend it is a "lost reply" — record why it was not dispatched.

A result structure:

~~~java
record BranchReply(
    String requestId,
    QuoteBranch branch,
    boolean success,
    String value,
    String reasonCode
) {}

record QuoteGatherResult(
    String requestId,
    Set<QuoteBranch> expected,
    Map<QuoteBranch, BranchReply> received,
    boolean complete,
    String overallStatus
) {}
~~~

**Each branch contributes at most one valid result** to the same logical request (unless the contract supports multiple result versions). Validate `BranchReply` for `requestId`, tenant scope, branch membership, and schema; messages from unknown branches must never count toward "enough replies".

When branches can retry, add `attemptId` and a rule to pick the branch's **valid final outcome** instead of adding all retries into group size.

## 16. Release by branch set, not simply message count

Too weak a release implementation:

~~~java
.releaseStrategy(group -> group.size() == 3)
~~~

Suppose Inventory replies twice due to broker redelivery, Pricing replies once, and Shipping has not finished:

~~~text
Group Q-101:
  INVENTORY - attempt 1
  INVENTORY - duplicate attempt 1
  PRICING   - attempt 1

group.size() = 3, yet SHIPPING is missing
~~~

**Never release as complete** just because three messages exist. An application-level model:

~~~java
final class ExpectedBranchRelease {

    boolean ready(Set<QuoteBranch> expected,
                  Collection<BranchReply> replies) {
        if (expected == null || expected.isEmpty()) {
            throw new IllegalArgumentException("INVALID_EXPECTED_SET");
        }
        for (BranchReply reply : replies) {
            if (!expected.contains(reply.branch())) {
                throw new IllegalArgumentException("UNEXPECTED_BRANCH");
            }
        }
        Set<QuoteBranch> received = replies.stream()
            .map(BranchReply::branch)
            .collect(Collectors.toSet());
        return received.equals(expected);
    }
}
~~~

This example illustrates **counting unique branches**, yet does not yet fully handle conflicting duplicate content or replies with the wrong `requestId`. In production, compare against a **locked manifest/plan**, validate request/tenant, and enforce duplicate-conflict and timeout/partial policies.

If a branch returns a structured `FAILURE_RESULT`, it can still count as **having an outcome** for that branch; however, **overallStatus** must be `FAILED` or `PARTIAL` per contract, never `SUCCESS`.

## 17. Correlation must distinguish request, tenant, and plan version

One tenant may request multiple quotes for the same order; two tenants may share an `orderId`. If Gather only uses orderId or customerId, replies from different requests can mix.

| Identity | Role | Safe as standalone group key? |
|---|---|---|
| `MessageHeaders.ID` | Spring message ID at one point | Unstable across rebuild/replay |
| `orderId` | Business order ID | Can have multiple quotes/revisions |
| `requestId` | One logical quote evaluation | Good if unique and properly issued |
| `tenantId` | Authorization/customer scope | Must accompany request/group ID |
| `planVersion` | Branch set / rules version | Needed when the same request can have different plans |
| `traceId` | Observes entire call chain | Does not replace business correlation |
| `sequenceNumber/size` | Scatter/gather metadata | Does not replace membership or idempotency |

Example key:

~~~text
tenant-A | quote-Q101 | plan-v3
tenant-A | quote-Q101 | plan-v4
tenant-B | quote-Q101 | plan-v3
~~~

**Do not turn `correlationId` into a fresh UUID in each branch handler.** A stable group ID must be created and recorded **before scattering**. When retrying the same logical evaluation, policy may preserve the group ID alongside a separate attempt ID; when intentionally changing plans, define versioning/migration and never mix replies from two plans.

Over Kafka/AMQP, header mappers may drop or convert certain headers. Expose business correlation in the wire contract while still authenticating tenant and reply source; a matching string ID is not proof of authorization.

## 18. Overall deadline and per-branch timeouts are two different things

Suppose the API has a **1-second** deadline:

~~~text
T0 = request received
Overall deadline = T0 + 1,000 ms

Inventory: 300 ms timeout
Pricing:   700 ms timeout
Shipping:  600 ms timeout
Gather:    must not wait past overall deadline
~~~

Do not configure a 1-second timeout per branch and then let Gather wait another second, because total duration can breach the Gateway SLO. Compute remaining budget:

\[
T_{\mathrm{remaining}}
= \max(0,\ T_{\mathrm{deadline}}-T_{\mathrm{now}})
\]

A downstream decision should respect the **overall deadline**, using HTTP client/DB call timeouts less than or equal to the remaining budget. If queue wait already consumed 800 ms, do not grant a fresh 700 ms timeout just because Pricing normally gets that budget.

**Important:** `gatherTimeout` or `groupTimeout` does not replace remote branch timeouts. When the caller stops waiting, background tasks may keep running; cancellation, client aborts/timeouts, and group cleanup must be designed separately.

## 19. How does one slow branch affect the whole quote?

With an *all responses required* Gather, response time approximates **the slowest branch** (plus scatter/gather overhead), not the sum of all branch latencies if they truly run in parallel:

\[
T_{\mathrm{all}}\approx
\max(T_{\mathrm{inventory}},T_{\mathrm{pricing}},T_{\mathrm{shipping}})
+T_{\mathrm{overhead}}
\]

If the three branches **run sequentially**, total time approaches the sum of branch durations. Therefore verify actual topology and executors before expecting latency gains.

One slow branch creates three kinds of pressure:

1. **Branch capacity:** HTTP connections, threads, or permits held longer.
2. **Gather state:** message groups and correlation/pending metadata remain alive.
3. **Caller:** Gateway threads or request futures blocked waiting for results.

Adding a semaphore on a branch does not solve group retention if admitted requests still cannot conclude. You need deadlines, timeout handling, release strategies, and overload outcomes aligned with the business contract.

## 20. PARTIAL, FAILED, and TIMEOUT statuses must be kept separate

Not every use case requires all three branches to succeed.

| Policy | Meaning | Example |
|---|---|---|
| **All required** | All mandatory branches must return valid results | Do not quote without shipping fee |
| **Partial allowed** | Result may emit with some branches missing | Show provisional price, shipping pending |
| **Quorum** | Enough valid sources reached to decide | Cross-check multiple independent data sources |
| **First-success** | Use first successful result | Query across equivalent mirrors |
| **Fail-fast** | A specific error renders the whole request invalid | Fraud concludes block |

**Never silently relax release policy under overload.** If Shipping is mandatory, dropping Shipping and returning `SUCCESS` is not "graceful degradation".

An aggregated result should express completion state:

~~~json
{
  "requestId": "Q-101",
  "status": "PARTIAL",
  "expectedBranches": ["INVENTORY", "PRICING", "SHIPPING"],
  "receivedBranches": ["INVENTORY", "PRICING"],
  "missingBranches": ["SHIPPING"],
  "reasonCode": "SHIPPING_TIMEOUT"
}
~~~

With `QUORUM`, prove the counted replies truly came from **authorized independent sources**; three duplicates from one source must never count as three votes.

## 21. Capacity-rejected branches are not successfully completed branches

When a worker pool is full, there are at least three ways to handle it:

1. **Reject the whole quote before scatter:** caller receives overload/too-busy per contract.
2. **Emit a failure outcome for the unadmitted branch:** Gather can conclude `FAILED/PARTIAL`.
3. **Bounded queueing:** request is admitted, yet deadlines must include queue wait time.

Behavior to avoid:

~~~text
Shipping has no permit left
  → skip sending
  → keep expected=3
  → Gather waits forever because Shipping never replies
~~~

Or:

~~~text
Shipping has no permit left
  → lower expected from 3 to 2
  → report SUCCESS even though Shipping is mandatory
~~~

The right approach is an **error-coded outcome** and explicit rule: `CAPACITY_EXCEEDED` might not retry, might retry briefly while deadline remains, or might fall back if business allows. All must be tracked separately from data and network errors.

## 22. Message sizes and byte budgets also need limits

Branch count is only one axis of resource consumption:

~~~text
1 QuoteRequest payload = 10 MiB
4 branches copy/serialize the same payload
→ can trigger multiple copies, encodings, queueing, and GC
~~~

With large payloads, even small fan-out causes memory pressure. You should:

- Cap request sizes at adapters and item counts inside payloads.
- Send an appropriate **projection** to each branch rather than copying all fields/PII.
- For large data, pass authorized object references/storage keys instead of duplicating blobs.
- Bound queued bytes in brokers/executors, not just task counts.
- Verify native header mappers; never serialize `replyChannel`, `errorChannel`, or arbitrary Spring internals.
- Measure payload bytes **after serialization**, since encoding and headers make wire size differ from in-RAM Java objects.

If Scatter uses `PublishSubscribeChannel` in the same JVM, subscribers may share references to a **mutable** payload. One branch mutating the object in place can affect another branch. Use immutable messages/payloads, or clone intentionally, especially when running concurrently.

## 23. Per-tenant limits: preventing one customer from starving the pool

A multi-tenant system must define **fairness**:

~~~text
Global concurrent budget = 100 branch calls
Tenant A traffic spikes
Tenant B still needs normal quote processing
~~~

With only a global semaphore, Tenant A can consume every permit. A better design combines:

- **Global admission limit** to protect the JVM/cluster.
- **Per-tenant concurrency/rate quota** to isolate load.
- **Per-branch bulkheads** for Pricing, Shipping, Inventory.
- **Priority classes** for critical traffic, while preventing starvation of normal traffic.
- **Bounded queueing** and timeouts suited to each service tier.

Never use `tenantId` from a raw client header as a quota key unless authenticated. Per-tenant quotas must bind to a verified principal/credential.

Avoid creating an unbounded thread pool per tenant: with thousands of tenants, thread, queue, and monitoring overhead can be worse than the original problem. Use shared bounded pools with per-tenant accounting/fair scheduling.

## 24. How do retries amplify fan-out?

Suppose a quote has 4 branches, and each branch retries up to 3 attempts:

~~~text
1 quote
  → 4 logical branches
  → up to 12 branch attempts (if each branch runs all 3 times)
~~~

If **the whole Scatter-Gather** also retries 3 times from the top, max attempts can reach **36** in the example unless previously succeeded steps are reused/deduplicated. That is many times the original 4 branches.

\[
A_{\mathrm{worst}}
\le F\times R_{\mathrm{branch}}\times R_{\mathrm{wholeFlow}}
\]

Where `R` is **total attempts**, not "extra retries". This is an **illustrative upper bound** when retry layers nest; actual behavior depends on advice placement and cancel/dedup policies.

To prevent retry storms:

1. Define retries at **one clear ownership boundary**.
2. Retry only transient errors while deadline remains.
3. Cap attempts and use backoff + jitter.
4. Enforce **global/per-tenant retry budgets**.
5. Do not resend branches that already produced valid outcomes if the contract allows reuse.
6. Protect side effects with idempotency keys keyed by `requestId + branch + operation`.
7. Add circuit breakers/bulkheads for persistently failing dependencies.

A `Gateway timeout` does not prove branches caused no side effects. Retrying the whole quote without idempotency can make multiple branches repeat actions.

## 25. Late replies, duplicate replies, and group cleanup

A quote has a 1-second deadline; Pricing finishes after 1.3 seconds:

~~~text
T+000 ms  Scatter plan Q-101, expected={I,P,S}
T+250 ms  Inventory reply
T+400 ms  Shipping reply
T+1000 ms Gather timeout → QuoteResult(TIMEOUT)
T+1300 ms Late Pricing reply
~~~

**Never treat a late reply as a new request and emit a second summary** if business rules allow only one final result. With `MessageGroupStore`/Gather:

- Retain a **completed/expired group marker** for an appropriate TTL.
- Use durable state with conditional `WAITING → COMPLETED/EXPIRED` transitions.
- For late replies, define audited **ignore/quarantine/correction event** handling.
- For duplicates, accept only one valid final outcome per branch; conflicts must be detected.
- Delete/expire timed-out waiting groups; groups waiting forever fill memory/stores.

Spring Integration settings around `groupTimeout`, `expireGroupsUponCompletion`, partial release, and message group stores have version- and topology-dependent semantics. **Never assume merely setting a timeout makes the framework cancel remote calls, wipe pending state, or block all late replies.**

## 26. MessageGroupStore: bounding pending groups and storage capacity

Gather may retain data for many concurrent requests:

| State type | Grows with | Policy needed |
|---|---|---|
| Pending group metadata | Incomplete quotes count | Max pending, timeout, cleanup |
| Collected replies | Branches that already replied | Payload size, store/retention |
| Duplicate detection | Branch outcome IDs count | TTL/window, uniqueness |
| Completed group markers | Completed quotes still remembered | Bounded retention |
| Error/quarantine | Failed requests count | Quotas, paging, ownership |

An **in-memory `MessageGroupStore`** does not survive restarts; a **persistent store** supports recovery yet requires transactions, cleanup, and locking when multiple instances aggregate concurrently. Sharing a database does not prevent double release on its own if group updates are uncoordinated.

A useful ceiling is **maximum pending groups per flow/tenant**, paired with a time budget. When hitting the ceiling, the application must **reject or slow ingress** intentionally. Letting the store grow silently causes issues to surface late and obscures the original failing branch.

**Never delete groups arbitrarily just to free RAM** before emitting an outcome to the caller/coordinator. Deleting state of an active quote turns subsequent replies into orphans that never produce a result.

## 27. Error chain: from branch to error channel and Gateway

A branch failure can happen before or after an async boundary:

| Scenario | What can the caller see? | Who handles it? |
|---|---|---|
| Synchronous Scatter, handler throws exception | Exception propagates through channel/caller | Synchronous error boundary |
| Executor branch throws exception | Publisher finished sending; error on worker | Error handler/error channel |
| Broker branch hits redelivery | Caller may have timed out | Listener/container + recovery |
| Over capacity before scatter | Overload/rejection outcome | Admission service |
| Over capacity on one branch | Failure outcome or branch-level error | Bulkhead/branch coordinator |
| Gather waits past deadline | Timeout/partial/fail per policy | Gather/coordinator |
| Error publishing summary | Result computed right yet never reached downstream | Output retry/outbox/idempotency |

**An error channel does not automatically mean "a failed branch reply" to the Aggregator.** If a branch handler throws an exception before replying, Gather may **receive zero messages from that branch**. To close the group intentionally, convert errors into `BranchReply(success=false, reasonCode=...)` with matching correlation, or let a timeout/fail-fast coordinator mark terminal state.

**Never log every exception as "scattered successfully".** Separate ingress validation, capacity, branch execution, correlation mismatch, gather timeout, and output publication errors.

## 28. Unit tests for planner and release

JUnit 5 tests for branch bounds:

~~~java
@Test
void normalQuoteHasThreeBranches() {
    QuoteRequest request = new QuoteRequest(
        "Q-101", "tenant-a", false, 10);
    ScatterPlan plan = new ScatterPlanner().plan(
        request, Instant.parse("2026-11-21T03:00:00Z"),
        Duration.ofSeconds(1));

    assertEquals(3, plan.required().size());
    assertFalse(plan.required().contains(QuoteBranch.FRAUD));
}

@Test
void highRiskQuoteRequiresFraudAndIsStillBounded() {
    QuoteRequest request = new QuoteRequest(
        "Q-102", "tenant-a", true, 20);
    ScatterPlan plan = new ScatterPlanner().plan(
        request, Instant.parse("2026-11-21T03:00:00Z"),
        Duration.ofSeconds(1));

    assertEquals(4, plan.required().size());
    assertTrue(plan.required().contains(QuoteBranch.FRAUD));
    assertTrue(plan.required().size()
        <= ScatterPlanner.MAX_BRANCHES);
}

@Test
void rejectsUnboundedInputSize() {
    QuoteRequest request = new QuoteRequest(
        "Q-103", "tenant-a", false, 100_000);
    assertThrows(IllegalArgumentException.class,
        () -> new ScatterPlanner().plan(
            request, Instant.now(), Duration.ofSeconds(1)));
}
~~~

Testing Gather must not equate duplicates with complete replies:

~~~java
@Test
void duplicateInventoryDoesNotReplaceMissingShipping() {
    Set<QuoteBranch> expected = Set.of(
        QuoteBranch.INVENTORY,
        QuoteBranch.PRICING,
        QuoteBranch.SHIPPING);
    List<BranchReply> replies = List.of(
        new BranchReply("Q-101", QuoteBranch.INVENTORY,
            true, "YES", null),
        new BranchReply("Q-101", QuoteBranch.INVENTORY,
            true, "YES", null),
        new BranchReply("Q-101", QuoteBranch.PRICING,
            true, "100", null));

    assertFalse(new ExpectedBranchRelease().ready(
        expected, replies));
}
~~~

This snippet checks basic membership; production needs validation for `requestId/tenantId/planVersion`, conflicting duplicate values, and manifests from trusted sources. Tests need no Spring context when testing pure Java planner/release logic.

## 29. Testing bounded executors and resource leaks

A resource test should be deterministic, not relying on random delays:

1. Use `CountDownLatch` to hold workers inside a mock branch.
2. Send enough requests to exhaust permits.
3. Try sending more; verify `CAPACITY_EXCEEDED` or `EXECUTOR_REJECTED` outcomes per policy.
4. Release the latch; verify tasks finish and permits are returned.
5. Ensure cancellation/timeouts **do not release permits early** while tasks still run.
6. Verify no group waits indefinitely because a branch was rejected.
7. Repeat with exceptions from branch handlers, verifying permits release in `finally`.

Directional example:

~~~java
CountDownLatch entered = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

Function<QuoteRequest, BranchOutcome> slowBranch = request -> {
    entered.countDown();
    try {
        if (!release.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("TEST_WAIT_TIMEOUT");
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(interrupted);
    }
    return new BranchOutcome(
        request.requestId(), QuoteBranch.PRICING,
        true, "OK", null);
};
~~~

This is a **test fixture**, not a complete test. When wiring into `BoundedBranchDispatcher`, submit enough tasks to hit the dispatcher/executor ceiling, then release the latch in the test's `finally` so failed assertions never hang the test runner.

**Measure active threads, queued tasks, memory, and pending Gather groups too.** A test verifying `RejectedExecutionException` occurred does not prove the request received a rejection outcome or that no orphaned pending state remained.

## 30. Integration testing: multiple concurrent quotes, out-of-order replies

Testing Scatter-Gather in a Spring context should include test channels/handlers counting actual invocations and verifying correlation. Simulate:

~~~text
Q-101: INVENTORY fast, PRICING slow, SHIPPING medium
Q-102: INVENTORY slow, PRICING fast, SHIPPING medium

Interleaved replies:
  Q-101/INVENTORY
  Q-102/PRICING
  Q-102/SHIPPING
  Q-101/SHIPPING
  Q-101/PRICING
  Q-102/INVENTORY
~~~

Expectations:

- Each `QuoteResult` holds **its exact `requestId`/tenant/`planVersion`** and its own branch set.
- Q-102's first reply is never used to complete Q-101.
- Never release as complete just because message count matches while a branch is missing.
- If a branch times out, the result carries status/missing branches per policy.
- Broker redelivery or duplicate replies never emit a second `QuoteResult` violating the contract.

### Required test matrix

| Case | Simulation | What to prove |
|---|---|---|
| Normal quote | 3 recipients | Exactly 3 branch requests, all 3 outcomes |
| High-risk quote | 4 recipients | Fraud not dropped, Gather waits for exact set |
| Dynamic recipients | Plan v2 differs from v1 | Never applies new expected set to old request |
| One slow branch | Pricing misses deadline | Overall TIMEOUT/PARTIAL/FAILED per policy |
| Executor saturated | Queue and workers full | No unbounded queue, rejection result emitted |
| Admission rejected | No global permit | Does not scatter and leave group waiting |
| Branch exception | Shipping throws error | Correlated error path/outcome |
| Duplicate reply | Inventory sends twice | Duplicate never counted as two branches |
| Late reply | Pricing arrives after terminal state | Never emits a second final result |
| Concurrent requests | Q-101/Q-102 interleaved | No cross-request mixing |
| Cross-tenant | Same request ID on tenant A/B | No cross-tenant mixing |
| Mixed protocol | Across broker/header mapper | Correlation and deadlines preserved |
| Nested Splitter | 500 lines × 4 branches | Total work budget enforced |
| Restart | Pending groups in durable store | Recovery per contract |
| Retry storm | Whole-flow + branch retries | Bounded attempts, no double side effects |
| Empty recipient plan | Plan has no valid branches | Reject/terminal result, never wait forever |

Tests should use `CountDownLatch`/barriers/test queues, finite timeouts, and a real Spring context. Never rely on `Thread.sleep` "hoping" branches return in order. When testing brokers, test real ack/redelivery, error handlers, header mappers, and transactions; mock unit tests do not prove those semantics.

## 31. Observability: visibility into fan-out and resource consumption

A Scatter-Gather dashboard should include these metric groups:

| Suggested signal | What to detect |
|---|---|
| `scatter.requests.count` | Ingress traffic |
| `scatter.branch.count` | Branches/request; unexpected spikes |
| `scatter.tasks.created.count` | Total internal work generated |
| `scatter.admission.rejected.count` | Requests rejected before Scatter |
| `scatter.branch.capacity.rejected.count` | Branches unadmitted due to saturation |
| `branch.active.count` per service | In-flight load |
| `branch.queue.depth` and queue age | Backlog/latency |
| `branch.duration` p95/p99 | Slow branches |
| `gather.pending.groups` | Groups awaiting completion |
| `gather.group.age` | Groups at risk of timing out |
| `gather.timeout.count` | Timeouts per flow/branch |
| `gather.partial.count` | Results missing branches |
| `gather.duplicate.reply.count` | Redelivery/dedup rate |
| `gather.late.reply.count` | Replies arriving after terminal state |
| `retry.attempts.count` | Retry amplification |
| `message.store.size.bytes` | Group store/broker pressure |

These are **suggested metric names**, not claimed default meters in Spring Integration. With Micrometer/observation, choose low-cardinality tags such as `branchType`, `outcome`, `flowName`, `reasonCode`; **never use request ID or customer ID as metric tags**.

In access-controlled traces/logs, keep `requestId`, authenticated `tenantId`, `planVersion`, branch identity, attempt ID, and deadline. Never log full sensitive payloads/headers. When a quote times out, you must be able to tell whether it was **unadmitted**, **queued**, **executing in a branch**, **replied yet mismatched**, or **waiting on Gather release**.

## 32. Runbook when Scatter-Gather overloads

When p99 quote latency rises and pending groups accumulate:

1. **Measure actual fan-out:** was a new branch enabled or did a nested Splitter increase tasks/request?
2. **Identify the slow branch:** is Pricing, Shipping, or Inventory holding connections/threads?
3. **Inspect queues:** is there an unbounded queue or queue age exceeding deadlines?
4. **Check admission:** are global/per-tenant/per-branch quotas exceeded?
5. **Inspect Gather:** have branches replied, is correlation intact, did groups expire?
6. **Check retries:** is there a retry storm or both whole-flow and branch-level retries firing together?
7. **Shed load intentionally:** rate limits, circuit breakers, queue bounds, canary traffic reduction, or fallbacks only when contracts permit.
8. **Protect data integrity:** never drop mandatory branches to report "success"; emit proper overload/failure/partial outcomes.
9. **Recover:** reconcile pending groups, late replies, and side effects before replaying.
10. **Prevent recurrence:** re-run load tests with bursts, slow dependencies, broker redeliveries, and measured limits.

**Never try to solve every incident just by enlarging the thread pool.** If downstream only handles 20 concurrent calls, raising the pool from 20 to 200 can make the service fail harder, amplify retries, and drag down the entire system.

## 33. Practice exercise: designing bounded quote fan-out

Build a **BoundedQuoteScatterGather** flow following these steps:

1. **Contract:** define `QuoteRequest`, `ScatterPlan`, `BranchReply`, `QuoteGatherResult`, and deadlines.
2. **Rules:** three mandatory branches, Fraud branch on high-risk; `MAX_BRANCHES=4`.
3. **Admission:** enforce request-level and per-branch ceilings; never dispatch half a plan without an outcome.
4. **Executor:** use a bounded thread pool/queue; slow down one mock branch to observe saturation.
5. **Gather:** release by **expected branches set**, not just message count.
6. **Correlation:** preserve request/tenant/plan identity across Splitter, Router, Transformer, and broker.
7. **Deadlines:** 1-second overall, per-branch timeouts; build `TIMEOUT/PARTIAL/FAILED` policies.
8. **Retries:** cap attempts, add backoff/jitter and idempotency for side-effectful branches.
9. **Late/duplicate:** send replays/late replies after terminal state; verify no double publishing.
10. **Multi-tenant:** generate a burst from Tenant A; verify Tenant B retains capacity per policy.
11. **Load test:** compare 3/4/8 recipients at 50/100/200 requests/s; observe active tasks, queue depth, and pending groups.
12. **Runbook:** document how to locate where a request is waiting and when rollback/cancel/retry is permitted.

**Completion criteria:** branch counts are enforced per policy; no unbounded queues or waiting groups; every branch produces an outcome or deadline; overload is an observable state; duplicate/late replies do not corrupt Gather; total concurrency respects chosen limits; tests prove zero resource leaks after timeouts or exceptions.

## 34. Common mistakes

**"Scatter-Gather runs in parallel automatically."** Not necessarily. Concurrency depends on executors/channels/transports, and synchronous branches may execute sequentially.

**"Capping at four branches/request prevents overload."** False. Ingress rate, nested Splitters, retries, and concurrent requests can still make total tasks huge.

**"An 8-worker thread pool guarantees bounded memory."** False if queues, payloads, or pending `MessageGroupStore` entries are unbounded.

**"Skipping Shipping dispatch means Gather knows only two branches remain."** False. The expected set must be locked; an undispatched branch needs an explicit failure/cancel outcome.

**"Increasing timeout fixes every group missing results."** False. `void` handlers, Filter drops, or correlation mismatches may never emit replies.

**"Three messages means done."** False when duplicate branch replies or messages from unknown branches enter the group.

**"Gateway timeout means all branches stopped."** False. Remote tasks may still run and create side effects.

**"Catching `RejectedExecutionException` and continuing as success."** False. Capacity exhaustion must appear in request/group status.

**"Retries help systems recover faster when dependencies are already overloaded."** Not always. Unbounded retries create request storms that prolong outages.

**"Reusing `replyChannel` as business `requestId` across brokers."** False. Internal return addresses and correlation identities serve different roles.

**"A persistent `MessageGroupStore` suffices for exactly-once."** False. You still need idempotency, transactions/locking, and late-reply/double-release controls.

**"Tenant ID from request body suffices for quotas and permissions."** False. Quotas and tenant scope must bind to verified identities.

## 35. Key takeaways

**Safe Scatter-Gather is more than scattering fast and waiting for replies.** You must bound **branches per request, concurrent work, queue backlog, pending Gather groups, payload bytes, retry attempts, and per-tenant resources**. No single limit replaces the others.

In **Spring Integration**, build a **scatter plan** from an allowlist before sending, use executors/channels/adapters with backpressure, keep **correlation and expected recipient sets** stable, release Gather by true branch identities, enforce **overall deadlines + per-branch timeouts**, and define outcomes for overload, partial failures, and late/duplicate replies. Combining **Gateway, Filter, Router, Transformer, Splitter, Aggregator, error channel, and retry** with concurrency/overload/cleanup tests lets flows scale without sacrificing correctness.

### References

- Spring Integration Reference, **Scatter-Gather**: https://docs.spring.io/spring-integration/reference/scatter-gather.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Messaging Endpoints**: https://docs.spring.io/spring-integration/reference/endpoint.html
- Enterprise Integration Patterns, **Scatter-Gather**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
