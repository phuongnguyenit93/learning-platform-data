# Impact of Errors, Cancellation, and Backpressure on Security Tasks in Spring Security Reactive

## 1. Why Is This a Security Topic?

In Spring WebFlux, authentication, authorization, data queries, response emission, and event recording are typically chained as **Mono** or **Flux** streams. A stream does not just return values; it also carries error signals, cancellation signals, and data-demand coordination (**backpressure**). These signals determine whether a security task actually ran, completed, was aborted, or is putting pressure on resources.

For example:

- A permission-checking service fails. If a developer replaces the error with an "allow" value, confidential data can be exposed.
- A client closes the connection while the API has just written partial data. Security or audit steps attached at the end of the stream may never reach execution.
- A Flux emits too fast or processes too many requests concurrently. Permission checks, token decoding, or audit persistence can stall and exhaust resources even when authorization rules themselves are correct.

**Goal of this lesson:** understand Reactor semantics to preserve the **deny when no valid decision exists (fail closed)** principle, handle cancellation safely, and control resources under heavy traffic.

## 2. Foundation: Lifecycle of a Publisher

A Mono emits at most one value; a Flux can emit multiple values. After **subscribe**, the Subscriber receives a Subscription and coordinates data flow with **request(n)**. In a normal stream:

~~~text
subscribe
   |
   v
onSubscribe(Subscription)
   |
   +-- request(n) --> onNext(value) ... --> onComplete
   |
   +-- request(n) --> onNext(value) ... --> onError(error)
   |
   +-- cancel()   --> request to stop stream, release resources
~~~

Key points:

1. **onNext** carries data; **onComplete** marks normal completion; **onError** marks stream failure. onComplete and onError are mutually exclusive and terminate the signal sequence to the Subscriber.
2. **cancel()** is a command to cancel the Subscription, not an onError or onComplete delivered downstream to the Subscriber. In Reactor, **doFinally** can observe ON_COMPLETE, ON_ERROR, and CANCEL alike.
3. **request(n)** tells upstream how many elements downstream is ready to accept. It propagates upstream, though operators may reshape demand in their own way.
4. Publishers are usually **lazy**: describing a Mono/Flux does not mean the work has run. Subscribing triggers processing; there can be multiple subscriptions and multiple executions.
5. **Reactor Context** carries data along the subscriber chain, including the SecurityContext used by Spring Security Reactive. Do not treat ThreadLocal on the current thread as the source of truth for identity when a pipeline switches threads.

Distinction table:

| Signal/state | Stream outcome | Security risk to consider |
| --- | --- | --- |
| onComplete | Terminated normally | Record success only if all mandatory operations actually completed |
| onError | Terminated due to error | Never turn an authorization-check error into an allow outcome; handle HTTP and logging safely |
| cancel() | Downstream stopped caring / cancelled | End-of-stream audits may not run; remote writes may still have occurred |
| request(n) | Permits receiving at most n elements per demand at this point | Do not confuse backpressure with rate limiting or task-cost limits |
| timeout | Usually emits an error downstream and cancels the upstream source | Can trigger CANCEL in stages before timeout; never use timeout to default-grant access |

**Note:** doFinally placed in two different positions can observe two different SignalTypes. For instance, when timeout cancels upstream and emits TimeoutException downstream, upstream may observe CANCEL while downstream observes ON_ERROR. When recording metrics, state clearly where in the pipeline observation occurs.

## 3. How Do Errors (onError) Affect Authentication and Authorization?

### 3.1. Errors stop the stream, but recovery operators can replace the outcome

An error from ReactiveAuthenticationManager, JWT verification key retrieval, a policy service, or a data store used for owner/tenant checks travels via onError if unhandled. Operators like **onErrorResume**, **onErrorReturn**, and **onErrorComplete** can replace or swallow error signals. This is useful for ordinary business recovery, yet very dangerous if applied broadly around security decisions.

**Wrong, fail-open** example:

~~~java
// Faulty illustration: losing connection to the policy service is treated as permitted.
Mono<Boolean> allowed = permissionService.canRead(user, documentId)
        .onErrorReturn(true);

// Subsequent code sees true and emits the document even though policy never confirmed.
~~~

**Safer, fail-closed** example:

~~~java
// Integration illustration; services and variables are application components.
Mono<Boolean> allowed = permissionService.canRead(user, documentId)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Authorization decision unavailable")));

// Technical errors remain errors; false is still denied.
return allowed.flatMapMany(granted -> {
    if (!granted) {
        return Flux.error(new AccessDeniedException("Access denied"));
    }
    return Flux.defer(() -> documentRepository.readForUser(user, documentId));
});
~~~

**Condition that must hold in the example:** canRead returns a `Mono<Boolean>` with explicit true/false; `Mono.empty` must not be interpreted as true. **AccessDeniedException** is Spring Security's exception type. The snippet above is not a standalone Java file; it illustrates logic inside a service that already has the corresponding objects.

Do not turn every technical error into HTTP 403: a broken policy service may need to return 503 or a safely handled 500, yet it **must never return data when the decision has not succeeded**. Distinguish authentication failures (usually 401), authorization denials (usually 403), and system errors; actual HTTP behavior also depends on entry points and exception-handler configuration.

### 3.2. Do not accidentally invert the data-protection order

**Principle:** check permissions before starting to emit the protected resource. Use `thenMany` only when the permission-checking publisher obeys the contract: **completes only when allowed, emits an error when denied**.

~~~java
// Pseudocode: requireReadAccess returns Mono<Void>, errors when unauthorized.
return permissionService.requireReadAccess(user, documentId)
        .thenMany(Flux.defer(() ->
                documentRepository.streamReadableItems(user, documentId)));
~~~

Conversely, if `requireReadAccess` returned `Mono.empty` to mean "not allowed", `thenMany` would still run when the Mono completes: that is a contract design bug, not a protection mechanism. If using `Mono<Boolean>`, always inspect true/false explicitly as in the previous example.

Do not emit sensitive items first and check permissions at the end of the Flux. Once partial data has been sent over HTTP streaming, a subsequent error cannot recall bytes already transmitted.

### 3.3. Retries can repeat work multiple times

**retry** and **retryWhen** usually create a new subscription when the source errors. A retry can re-run queries, authentication, logging, or write actions if the pipeline places them inside the re-subscribed source.

- For **pure reads**, bounded retries with timeouts and selective error conditions can be appropriate.
- For **logins**, unbounded retries can overload the identity service, cause account lockouts, or skew audits.
- For **payments/transactions/permission grants**, retrying after a timeout can repeat an operation that the first attempt already performed. You need idempotency keys, transaction boundaries, and reconciliation strategies.
- Never retry `AccessDeniedException`: denied permission is not a transient error to keep retrying.

A call returning an error does not mean external system side effects did not occur. A timeout or dropped connection only tells the client it never saw the final result.

### 3.4. Place handlers at the right layer

- Authentication: keep authentication errors on Spring Security's error path; do not mask them into a fake principal.
- Authorization: preserve denial state; do not use fallbacks that return secrets or skip failed items.
- Business logic: handle selected technical errors gracefully, returning controlled errors without leaking credentials, stack traces, or internal data.
- Reactive programming: avoid **onErrorContinue** in security pipelines because skipping an errored element can drop a mandatory check or produce inconsistent results.
- Observability: **doOnError** suits incrementing counters or brief logging, without recovering the stream. Never log raw tokens, passwords, or sensitive data.

## 4. Cancellation and Security Operations

### 4.1. When does cancellation happen?

- The client closes the connection or cancels downloading the stream.
- An operator such as **take(n)** has received enough elements and cancels the remaining upstream.
- **timeout** cancels a slow source while downstream receives `TimeoutException`.
- **switchMap** cancels the previous task when a new value arrives; a search operation may be superseded.
- Lifecycle cancellation or explicit disposal of a subscription.

Cancel states that the receiver no longer wants more data. It does **not** mean external operations rolled back, all threads were interrupted, or all I/O stopped instantly. A command already sent to a database, message broker, or external API may still complete.

### 4.2. Choose the right observation hook

~~~java
Flux<Event> stream = eventService.findEvents()
        .doOnComplete(() -> metrics.recordCompleted())
        .doOnError(error -> metrics.recordFailed())
        .doOnCancel(() -> metrics.recordCancelled())
        .doFinally(signalType -> metrics.recordTerminal(signalType));
~~~

The illustrative snippet uses application-owned `Event`, `eventService`, and `metrics`. **doOnComplete** does not run on `onError` or `cancel`; **doOnError** does not run on `cancel`. **doFinally** observes all three termination modes and supplies the `SignalType`. These callbacks work well for lightweight metrics; avoid placing blocking I/O on the event loop.

**Important:** `doFinally` runs after the stream has emitted the terminal signal downstream, so in asynchronous streams, observing side effects in tests right after downstream completion may require proper synchronization. Nor should a `doFinally` callback be treated as a durable audit guarantee.

### 4.3. Do not put mandatory auditing at a step that can be skipped

Wrong pattern:

~~~java
// Wrong if writing the audit is a mandatory obligation.
return protectedService.process(request)
        .flatMap(result -> auditService.persistSuccess(result)
                .thenReturn(result));
~~~

If the client cancels while `process` is running, the subsequent `flatMap` step may never be subscribed; `auditSuccess` does not run. Calling `auditService` inside `doFinally` and manually subscribing also offers no guarantee of success, while creating work detached from the request lifecycle where errors and security context are hard to control.

Design according to business requirements:

1. **Best-effort metrics/telemetry:** count errors, cancellations, and latency with `doFinally`/`doOnCancel`; keep callbacks non-blocking and free of sensitive data.
2. **Auditing an authorization decision before emitting data:** chain the audit into the pipeline *before* the emitting source; allow data reading to begin only after the mandatory audit completes. If cancelled before then, data should not be sent.
3. **Auditing tied to committed writes:** use transactions and a **transactional outbox** or equivalent durable server-side mechanism. The audit event must be bound to the business commit, independent of whether the HTTP client stays connected.
4. **Resource cleanup:** use resource-closing constructs designed for error/cancel, such as **using**, **usingWhen**, or corresponding transaction APIs; inspect asynchronous cleanup semantics. Do not equate "cancel was sent" with "all cleanup definitely finished".

Distinguish **access attempt**, **authorization decision**, **business commit**, and **response delivered**. These are four distinct events, especially during timeouts, retries, or client disconnects.

### 4.4. Avoid losing SecurityContext via manual subscribe

In Spring Security Reactive, the request's identity propagates through Reactor Context. If a handler manually calls `subscribe()` for an audit or permission-check publisher, you create a separate subscription with a different lifecycle and context propagation. It may fail to receive the right user info, or its errors may be ignored.

**Return** or **compose** Mono/Flux so the framework manages the subscription; when durable work must outlive the request, pass the required authenticated business fields explicitly into an event/message and design a separate reliable worker.

## 5. How Does Backpressure Affect Security?

### 5.1. Backpressure actually controls elements, not every kind of load

In Reactive Streams, the Subscriber requests `n` elements via `request(n)`; sources and operators cooperate not to push beyond demand at that interface. Operators may use **prefetch** or buffering, so upstream work can differ from the final elements currently visible.

For example, a Flux is requested for only 2 elements: a source like `Flux.range` emits 2 elements and waits for more demand. Yet an upstream task may still hold connections, CPU, queues, or have already caused side effects.

Backpressure **does not mean**:

- Limiting HTTP requests per second (rate limiting).
- Limiting failed authentication attempts or credential stuffing.
- Capping bytes/CPU of a single request.
- Stopping non-compliant publishers, blocking APIs, or fast-sending clients.
- Permission to access a resource; that is the job of authorization.

### 5.2. Abnormal load is a security and availability issue

When an endpoint combines data queries, policy checks, and per-element audits, high concurrency can exhaust connection pools or build unbounded queues. This can lead to denial of service (**DoS**) or loss of security controls when software starts dropping logs/checks to "save performance".

Use the right tools for the right job:

| Mechanism | Effect | Limits/warnings |
| --- | --- | --- |
| `request(n)`, backpressure-aware streams | Regulates elements based on downstream demand | Does not replace HTTP request rate limiting |
| **flatMap(mapper, concurrency)** | Limits how many inner publishers are subscribed simultaneously | Account for prefetch, queues, and per-publisher cost |
| **concatMap** | Sequential processing, preserves source order | Lower throughput; not immune to timeouts |
| **limitRate** | Splits/batches upstream demand | Coordinates requests only, does not enforce account quotas |
| Bounded **onBackpressureBuffer** | Bounded buffer with explicit overflow policy | Unbounded buffers can exhaust the heap |
| **onBackpressureError** | Emits an error when the source cannot absorb pressure | Must distinguish load errors from authorization errors |
| **onBackpressureDrop/Latest** | Drops events when the consumer is slow | Never use to skip authorization decisions or mandatory audit events |
| Gateway rate limits, quotas, size limits, timeouts | Controls abuse per client/account/system | Requires configuration, monitoring, and anti-bypass policies |

**Specifically:** if every item must be authorized, never drop errored items or skip authorization records to "go faster". Any item passing through the permitted branch must still undergo its corresponding check. Queries should filter by principal/tenant right at the data source instead of loading every record and filtering later.

### 5.3. Bound concurrency for expensive operations

~~~java
// Illustration: tasks is Flux<TaskId>, policyService is an async reactive API.
// At most 8 processing tasks inside flatMap are subscribed concurrently.
return tasks.flatMap(taskId ->
        policyService.checkAndLoadForUser(user, taskId),
        8);
~~~

Condition: **checkAndLoadForUser** returns data only after the authorization check completes; errors/denials must never fall back to data. For write operations, resolve ordering and idempotency before adding retries or raising concurrency.

A Flux emitting few elements is not necessarily lightweight: a single element can trigger a huge query, expensive cryptographic verification, or external API calls. Measure request rate, in-flight tasks, response size, and processing time together.

## 6. Runnable Java 17+ Example: Three Signals in Reactor

The example below uses **Project Reactor** directly to isolate Reactor semantics from the HTTP framework. It simulates an authorization decision and verifies it with **StepVerifier**; Section 7 then connects this thinking to Spring Security WebFlux. The demo does not replace Spring Security authentication/authorization configuration.

Structure:

~~~text
reactor-security-signals/
├── settings.gradle
├── build.gradle
└── src/main/java/example/SecuritySignalDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'reactor-security-signals'
~~~

**build.gradle** (Gradle 8+, JDK 17+)

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.12'
    implementation 'io.projectreactor:reactor-test:3.6.12'
}

application {
    mainClass = 'example.SecuritySignalDemo'
}
~~~

**src/main/java/example/SecuritySignalDemo.java**

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

public final class SecuritySignalDemo {

    public static void main(String[] args) {
        // 1. Policy service fails: must not reveal sensitive data.
        Mono<String> protectedRead =
                Mono.<Boolean>error(new IllegalStateException("policy unavailable"))
                    .flatMap(allowed -> allowed
                            ? Mono.just("secret")
                            : Mono.<String>error(new SecurityException("denied")));

        StepVerifier.create(protectedRead)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "policy unavailable".equals(error.getMessage()))
                .verify();

        System.out.println("PASS 1: policy error did not reveal data");

        // 2. Subscriber receives only two items then cancels.
        AtomicInteger emitted = new AtomicInteger();
        AtomicInteger cancelled = new AtomicInteger();

        Flux<Integer> protectedStream = Flux.range(1, 100)
                .doOnNext(value -> emitted.incrementAndGet())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.incrementAndGet();
                    }
                });

        StepVerifier.create(protectedStream, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        if (emitted.get() != 2 || cancelled.get() != 1) {
            throw new AssertionError("Cancel state mismatch");
        }
        System.out.println("PASS 2: cancelled after two items");

        // 3. Demand arrives in batches; synchronous source honors request(n).
        AtomicInteger seen = new AtomicInteger();
        Flux<Integer> limited = Flux.range(1, 5)
                .doOnNext(value -> seen.incrementAndGet());

        StepVerifier.create(limited, 0)
                .expectSubscription()
                .thenRequest(1).expectNext(1)
                .thenRequest(2).expectNext(2, 3)
                .thenRequest(2).expectNext(4, 5)
                .verifyComplete();

        if (seen.get() != 5) {
            throw new AssertionError("Backpressure count mismatch");
        }
        System.out.println("PASS 3: demand 1+2+2 delivered five items");
    }
}
~~~

Run in the project directory:

~~~bash
gradle run
~~~

Output from the **demo program** (ignoring standard Gradle logs):

~~~text
PASS 1: policy error did not reveal data
PASS 2: cancelled after two items
PASS 3: demand 1+2+2 delivered five items
~~~

Explanation:

- **Case 1:** the policy source emits `onError`; `flatMap` is never invoked, so `"secret"` is never emitted.
- **Case 2:** `StepVerifier` requests exactly 2 elements and then cancels; synchronous `Flux.range` honors demand, and `doFinally` records `CANCEL` once.
- **Case 3:** no unbounded demand is sent; the source emits 1, then 2, then 2 elements.

In real systems, asynchronous I/O, prefetching operators, and out-of-process work make measurement more complex. The demo proves signal semantics on a synchronous source; it does not assert that cancellation always rolls back databases or that `request(n)` always equals the count of I/O work units.

## 7. Applying to Spring Security WebFlux

### 7.1. Placing an authorization gate before a data-emitting Flux

A reactive service can be structured as follows:

~~~java
// Illustrative integration snippet, not a standalone Java program.
// canReadAccount: Mono<Boolean>; false => forbidden, empty => no decision yet.
// Use Authentication obtained from Spring Security, not a self-declared username.
public Flux<DocumentDto> documents(Authentication principal, String accountId) {
    return permissionService.canReadAccount(principal, accountId)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("No authorization decision")))
            .flatMapMany(allowed -> {
                if (!allowed) {
                    return Flux.error(new AccessDeniedException("Forbidden"));
                }
                return Flux.defer(() ->
                        documentRepository.findReadableByPrincipalAndAccount(
                                principal.getName(), accountId));
            });
}
~~~

`DocumentDto`, services, and repositories must be defined in the application; `AccessDeniedException` belongs to Spring Security. Repository queries must enforce the authorized scope directly rather than merely trusting a client-supplied `accountId`. If the policy returns a technical error, this code emits no data. Before deploying to production, protect endpoints with `SecurityWebFilterChain` and/or appropriate reactive method security.

When using **@EnableReactiveMethodSecurity** and **@PreAuthorize**, Spring Security relies on Reactor Context to enforce security decisions inside the Mono/Flux pipeline. If you use operators that create separate subscriptions or manage context manually, verify the real context via integration tests.

### 7.2. For streaming responses, timing is critical

~~~text
Client ---- HTTP request ----> SecurityWebFilterChain
                                   |
                              Authentication
                                   |
                              Authorization
                                   |
                           Start data Flux
                                   |
                       item1 -> item2 -> item3 ...
                                   |
                        client cancel / error
~~~

- **Before the first item:** policy/permission errors can completely prevent emitting data. The HTTP status can still be mapped to 401/403/5xx depending on handlers and whether the response is committed.
- **After emitting item1/item2:** if an error occurs, bytes already sent cannot be "recalled"; the response may already be committed and changing the HTTP status becomes difficult. For sensitive data, prefer authorizing before streaming and avoid streaming across multiple unchecked authorization boundaries.
- **When the client disconnects:** upstream may be cancelled; do not interpret an incomplete response as a rolled-back business operation. Transaction audits must sit at a durable commit boundary.
- **When the source is too slow:** timeouts, cancellation, and retries must be designed around operation safety; adding unbounded retries can overload the security subsystem itself.

For long-lived streams (SSE/WebSocket), permissions can change while a connection remains open. A single check at handshake time only proves authorization at that moment. If business rules require immediate revocation or per-event authorization, design periodic re-checks/revocation mechanisms per policy.

## 8. Before–After Scenarios to Understand

### Scenario A: policy service is failing

**Wrong:** using `onErrorReturn(true)`, allowing by default because "the service is temporarily unavailable".

**Right:** stop emitting documents and return a safe technical error with monitoring alerts. Access policies may distinguish 403 and 503, yet must never turn an inability to decide into granted access.

### Scenario B: download is cancelled mid-way

**Wrong:** recording "downloaded successfully" on the first `doOnNext` or merely when the HTTP handler is called.

**Right:** distinguish started, streamed partially, completed, and cancelled. Use appropriate signal observation and measure byte counts if needed. Durable authorization/audit decisions must occur at the business-required moment, not solely on the assumption that the client received the whole response.

### Scenario C: audit sink is slow

**Wrong:** adding `onBackpressureDrop` to a mandatory audit stream to avoid hurting speed, leaving some actions untraced.

**Right:** apply durable queues, bounded concurrency, explicit backpressure, or reject/shed requests when mandatory auditing cannot be satisfied. The design must define what happens when the audit destination is unavailable.

### Scenario D: reading 50,000 objects

**Wrong:** calling unbounded `flatMap` for tens of thousands of permission checks and buffering all results in RAM.

**Right:** bound concurrency, paginate or stream with backpressure, query pre-filtered by tenant/owner, and enforce timeouts and quotas. If objects carry individual permissions, every returned object must undergo appropriate checks; never skip checks for speed.

## 9. Testing Terminal Paths Properly

A test checking only HTTP 200 on success is insufficient. At minimum, simulate:

| Case | What to verify |
| --- | --- |
| Missing credentials | Data requiring login is not returned; response matches entry point |
| Failed authentication | No trusted principal is created; no data is emitted |
| Policy returns false | 403/AccessDenied per configuration; protected data source is not called |
| Policy returns Mono.empty | Not automatically treated as allowed |
| Policy onError or timeout | No data emitted; error is handled and observed appropriately |
| Client cancels before authorization decision | No documents emitted; cancel metric recorded; no false assumption that audit/commit finished |
| Client cancels after several items | No false "all data delivered" log; no promise of rolling back external side effects |
| Retry with side effects | Operations are not duplicated; idempotency/transactions protect state |
| Subscriber request(1), request(2) | Demand-aware source does not emit beyond requested items at the test boundary |
| Heavy concurrent load | In-flight tasks, buffers, CPU, connections, and timeouts remain within design bounds |
| Multi-tenant data | Zero items outside the valid tenant/owner pass through the stream |
| Scheduler/context switch | Principal is read accurately from Reactor Context, never mixed across requests |

Appropriate tools: **StepVerifier** to verify Reactor signals, **WebTestClient** to test HTTP and security filters, integration tests for databases/queues/transactions, and controlled stress tests for concurrency/backpressure. In cancellation tests, use deterministic synchronization rather than random sleeps and guessing whether work stopped.

## 10. Design Checklist for Reactive Security Tasks

1. **Identify the gate:** after which exact step is data allowed to leave the system? Keep that gate ahead of sensitive data publishers.
2. **Define empty / false / error explicitly:** what does `Mono.empty` from the policy service mean? Never implicitly treat it as allow.
3. **Fail closed:** never wrap an authorization branch in `onErrorReturn(true)`, `onErrorComplete`, or fallbacks returning secrets.
4. **Review retries and timeouts:** operator placement, retry count, side effects, and idempotency. Know which source receives `CANCEL` when downstream times out.
5. **Observe all three termination paths:** complete, error, cancel. Lightweight metrics via `doFinally`; mandatory audits need durability matching business needs.
6. **Do not self-subscribe carelessly:** return `Mono`/`Flux` to WebFlux and preserve Reactor Context; design separate durable jobs when truly needed.
7. **Protect per object/tenant:** enforce checks at service/data layers; multi-item streams may require per-item checks or authorization-filtered queries at the source.
8. **Set load limits:** bounded concurrency, bounded queues/buffers, timeouts, request quotas, rate limits, payload limits; measure real limits.
9. **Never drop security decisions:** drop/skip is unsuitable for authorization or mandatory audits.
10. **Test failure/cancellation/backpressure:** abnormal paths matter just as much as the happy path.

## 11. Self-Check Questions

1. Why is `onErrorReturn(true)` on a permission-checking `Mono<Boolean>` a fail-open vulnerability?
2. How do `doOnComplete` and `doFinally` differ when a client cancels a stream?
3. What signal upstream of `timeout` can correspond to a downstream `TimeoutException`?
4. Why does cancelling an HTTP request not guarantee a database transaction rolled back?
5. Does `request(2)` protect an endpoint from 10,000 requests/s? Why or why not?
6. Why is `onBackpressureDrop` dangerous when applied to mandatory auditing or authorization?
7. Once a `Flux` has already sent several sensitive elements, can a later authorization error recall that data?
8. When retrying a write command after a timeout, why are an idempotency key or clear transaction boundaries needed?

**Suggested answers:** (1) policy errors turn into allow; (2) `doOnComplete` runs only on normal completion, whereas `doFinally` also observes error/cancel; (3) `CANCEL` upstream, `ON_ERROR` downstream; (4) I/O may already have started/committed and cancel is not rollback; (5) no, backpressure regulates elements rather than enforcing rate limits; (6) evidence/checks can be lost; (7) bytes already sent cannot be recalled; (8) retry creates a new subscription while the first attempt may already have succeeded.

## 12. Reference Material

- Project Reactor Reference Guide — Handling Errors: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor Reference Guide — Backpressure and Reshaping Requests: https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html
- Project Reactor Reference Guide — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html

**Conclusion:** All three properties—**error**, **cancel**, and **backpressure**—can alter when authorization checks and audits occur, whether they re-run or get cut short, and how many resources data sources consume. Design flows around real signals: authorization decisions before data, audits with business-appropriate durability, explicit load limits, and thorough testing of all termination paths.