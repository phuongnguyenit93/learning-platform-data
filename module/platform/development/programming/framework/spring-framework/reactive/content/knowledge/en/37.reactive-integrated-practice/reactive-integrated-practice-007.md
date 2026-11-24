# Verifying Errors, Cancellation, Resources, and Per-Request Context in Project Reactor

## 1. Goals

A reactive request can traverse multiple operators, threads, and dependencies. When a request errors, times out, or the client disconnects, the application must return the right result, release resources, and preserve the metadata belonging to that exact request.

This practice combines four dimensions:

1. **Error:** errors propagate to the right subscriber, are deliberately classified/mapped, and are never swallowed.
2. **Cancellation:** when downstream no longer needs data, upstream receives cancel and resources are cleaned up per contract.
3. **Resource lifecycle:** each subscription opens its own resource and releases it on the matching complete, error, or cancel branch.
4. **Per-request Context:** request IDs and tenant metadata never mix across concurrent requests or when a pipeline switches Schedulers.

We use Reactor Context, `Mono`/`Flux.usingWhen`, `StepVerifier`, `PublisherProbe`, `TestPublisher`, virtual time, `doFinally`, and an observable resource ledger. The goal is to practice tenant isolation and request isolation through repeatable tests.

Invariants:

- Each request reads only the Context of its own subscription.
- Each opened resource is released exactly once.
- Complete, error, and cancel execute the right cleanup branch.
- Business errors are never unintentionally turned into success.
- `take`/`timeout` can cancel upstream while downstream completes/errors.
- `ThreadLocal` is not the source of truth for request metadata in a reactive chain.

## 2. Lifecycle Model

~~~text
HTTP request
    |
    v
WebFilter: validate/generate requestId
    |
    v
contextWrite(requestId, tenant/principal)
    |
    v
Controller -> Service
    |
    v
usingWhen(open resource)
    |
    +---- ContextView: read request metadata
    |
    +---- dependency call / async boundary
    |
    +---- complete ------> asyncComplete(resource)
    |
    +---- error ---------> asyncError(resource, error)
    |
    +---- downstream cancel -> asyncCancel(resource)
    |
    v
HTTP response / stream ends
~~~

| Scenario | Upstream | Downstream |
| --- | --- | --- |
| Flux completes naturally | ON_COMPLETE | ON_COMPLETE |
| Flux emits an error | ON_ERROR | ON_ERROR or mapped error |
| take(n) receives enough items | May CANCEL | ON_COMPLETE |
| timeout expires | CANCEL original source | ON_ERROR(TimeoutException) |
| Client cancels stream | CANCEL if adapter propagates | No terminal from cancelled source |

You cannot look solely at the HTTP status or terminal signal in the controller and assume every upstream operator is in the same state.

## 3. Request Context Belongs to the Subscription

### 3.1. Declaring Keys

~~~java
public final class RequestContext {
    public static final String REQUEST_ID = "app.requestId";
    public static final String TENANT_ID = "app.tenantId";

    private RequestContext() {}
}
~~~

Reactor Context is an immutable key-value map attached to a Subscriber/subscription. Pick namespaced keys to avoid collisions; never use a static mutable variable to hold the current request ID.

### 3.2. Writing and Reading Context

~~~java
Mono<String> identify() {
    return Mono.deferContextual(view -> {
        String requestId = view.get(RequestContext.REQUEST_ID);
        String tenantId = view.get(RequestContext.TENANT_ID);
        return Mono.just(requestId + "|" + tenantId);
    });
}

Mono<String> result = identify()
    .contextWrite(context -> context
        .put(RequestContext.REQUEST_ID, "req-101")
        .put(RequestContext.TENANT_ID, "tenant-A")
    );
~~~

`deferContextual` reads `ContextView` at subscription time. If a required key is missing, `view.get(key)` throws an error; for optional keys, use `getOrDefault`/`getOrEmpty`.

### 3.3. Context Across an Async Boundary

~~~java
Mono<String> identifyAfterDelay() {
    return Mono.delay(Duration.ofMillis(10))
        .then(Mono.deferContextual(view ->
            Mono.just(
                view.get(RequestContext.REQUEST_ID)
                    + "|"
                    + view.get(RequestContext.TENANT_ID)
            )
        ));
}
~~~

`Mono.delay` may run on a different Scheduler. Context still belongs to the subscription regardless of which thread executes callbacks.

### 3.4. Visibility Direction of contextWrite

Data signals flow from upstream to downstream, whereas Context is provided from the subscriber side and seen by operators **upstream of `contextWrite`**.

~~~java
Mono<String> flow = Mono.deferContextual(view ->
        Mono.just(view.get(RequestContext.REQUEST_ID))
    )
    .contextWrite(context ->
        context.put(RequestContext.REQUEST_ID, "req-102")
    );
~~~

`deferContextual` is upstream so it reads `req-102`. Placing `contextWrite` in the wrong position can prevent other operators from seeing the key. When debugging, trace the chain by operator position.

## 4. ThreadLocal and MDC Are Not Request Context

MDC and some imperative libraries rely on `ThreadLocal`. In WebFlux, a request can switch threads, and a single thread can serve multiple requests.

~~~text
Request A -> reactor-http-nio-1 -> parallel-2
Request B -> reactor-http-nio-1
Request C -> reactor-http-nio-1 -> boundedElastic-1
~~~

If you call `MDC.put("requestId", "A")` without restoring it, a reused thread can carry the stale ID into another request.

Principles:

- Reactor Context holds custom request metadata inside the pipeline.
- MDC is merely a logging adapter at the moment of logging.
- Micrometer Context Propagation requires proper accessors and reset/removal.
- Do not call `subscribe()` on a separate task and expect Context/cancellation/errors to stay coupled to the main subscription.
- Never capture a request object or a `SecurityContext` containing secrets into static fields.

A manual MDC scope saves the previous value and restores it in `finally`:

~~~java
static void withMdc(String requestId, Runnable action) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", requestId);
        action.run();
    }
    finally {
        if (previous == null) {
            MDC.remove("requestId");
        }
        else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

This scope lasts only for the synchronous callback; it does not automatically propagate `ThreadLocal` across async boundaries.

## 5. Verifying Errors: Propagate, Map, and Recover

### 5.1. Error Is a Terminal Signal

~~~java
Mono<String> source =
    Mono.error(new IllegalStateException("database unavailable"));

StepVerifier.create(source)
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().equals("database unavailable")
    )
    .verify();
~~~

Do not check only "an error occurred." Verify the exact exception type, message, or error code expected by callers.

### 5.2. onErrorMap Translates Error Types

~~~java
Mono<String> publicResult = source
    .onErrorMap(
        IllegalStateException.class,
        error -> new DependencyFailure(
            "CATALOG_UNAVAILABLE",
            error
        )
    );
~~~

Translate technical errors into domain/application exceptions while preserving the cause. Never create a new exception that drops the root cause when investigation is needed.

### 5.3. onErrorResume Recovers Using Another Publisher

~~~java
Mono<String> result = source
    .onErrorResume(
        TimeoutException.class,
        error -> Mono.just("fallback")
    );
~~~

Recover only error types that have a valid fallback. If an unavailable database returns an empty List, callers may misinterpret it as no data existing.

### 5.4. doOnError Only Observes

~~~java
Mono<String> result = source
    .doOnError(error ->
        log.error("operation failed", error)
    );
~~~

`doOnError` does not consume the error and does not turn it into success. To recover, use `onErrorResume` or an equivalent operator.

Do not swallow cleanup errors with `onErrorResume(error -> Mono.empty())` if doing so hides connection-close or rollback failures. Ignore only with an explicit policy, metrics, and clear justification.

## 6. Cancellation Is Upstream Control

Subscribers can call `Subscription.cancel()` when data is no longer needed: client closes HTTP/SSE/WebSocket, `take(n)` receives enough items, `timeout` expires, `switchMap` replaces an inner Publisher, or `Disposable.dispose()` is called.

Cancel is not `onComplete`/`onError`. Nor does it automatically roll back already-executed remote side effects.

### 6.1. doOnCancel and doFinally

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() ->
        log.info("subscription cancelled")
    )
    .doFinally(signal ->
        log.info("ended: {}", signal)
    );
~~~

`doOnCancel` runs when cancellation passes that operator's position. `doFinally` receives `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. For complete/error, the `doFinally` callback may run after the terminal signal reaches downstream; test async callbacks with latches or await mechanisms.

### 6.2. take Can Complete Downstream While Cancelling Upstream

~~~java
Flux<Integer> firstTwo =
    Flux.range(1, 100)
        .doFinally(signal ->
            log.info("source signal={}", signal)
        )
        .take(2)
        .doFinally(signal ->
            log.info("result signal={}", signal)
        );
~~~

`take(2)` emits two values and completes downstream; it can cancel the source because the remainder is not needed. The two hooks can observe `CANCEL` and `ON_COMPLETE` respectively.

### 6.3. timeout Cancels the Original Source Then Emits an Error

~~~java
Mono<String> result = remoteCall()
    .timeout(Duration.ofSeconds(2));
~~~

On timeout, the upstream `remoteCall` typically receives `CANCEL`, while downstream receives `TimeoutException`. If a fallback exists, downstream can continue and complete with the fallback result.

## 7. Resource Lifecycle with usingWhen

When a resource needs asynchronous release, use `usingWhen` instead of calling `closeReactive().subscribe()` inside `doFinally`.

~~~java
Mono.usingWhen(
    resourceSupplier,
    resource -> useResource(resource),
    resource -> cleanupOnComplete(resource),
    (resource, error) -> cleanupOnError(resource, error),
    resource -> cleanupOnCancel(resource)
);
~~~

| Resource closure branch | Cleanup callback |
| --- | --- |
| Complete | cleanupOnComplete |
| Error | cleanupOnError |
| Downstream cancel | cleanupOnCancel |

`Flux.usingWhen` has a similar structure. `Mono.usingWhen` fits a single result; `Flux.usingWhen` fits multi-element streams.

### 7.1. Per-Subscription Resource Supplier

~~~java
Mono.usingWhen(
    Mono.fromSupplier(connectionFactory::openLease),
    lease -> executeQuery(lease),
    Lease::closeAsync,
    (lease, error) -> lease.rollbackAsync(),
    Lease::closeAsync
);
~~~

Each subscription receives a lease. Never open a connection once at assembly time and let multiple requests share and close it together.

### 7.2. No Fire-and-Forget Cleanup

Wrong:

~~~java
.doFinally(signal ->
    lease.closeReactive().subscribe()
)
~~~

This cleanup subscription is detached from the original pipeline. Cleanup errors are not composed; cancellation may finish while the release task is still running.

Let `usingWhen` accept the cleanup Publisher and coordinate by lifecycle branch. If multiple code paths can request release, guard state with `AtomicBoolean`, while still maintaining one clear owner.

### 7.3. Resource Release Is Not Business Rollback

Closing a connection does not necessarily mean a transaction rolled back properly. With R2DBC, use `TransactionalOperator`/`R2dbcTransactionManager` or a transaction API with explicit contracts. Test commit, rollback, and close whenever business rules require those guarantees.

## 8. Resource Ledger and Invariants

In this practice, `ResourceLedger` counts:

- `opened`: number of opened leases.
- `completed`: number of leases released via the complete branch.
- `failed`: number of leases released via the error branch.
- `cancelled`: number of leases released via the cancel branch.
- `active`: number of leases not yet released.

Invariant after tests finish:

~~~text
opened = completed + failed + cancelled + active
~~~

When no request is active, `active` must equal 0. If each lease is released only once, the sum of the three outcomes equals the number of closed leases.

This is a test/diagnostic tool. Production can use corresponding Micrometer metrics, without attaching high-cardinality request IDs as metric tags.

## 9. Integrated Example: RequestScopedFlow

The demo application creates a resource per subscription and reads Context across an async boundary.

Three flows:

- `complete()`: opens a lease, awaits an async hop, reads request context, returns the result, and runs complete cleanup.
- `fail()`: opens a lease, reads context, emits `DomainFailure`, and runs error cleanup.
- `stream()`: opens a lease and emits infinite ticks; when downstream `take(2)` or client cancel occurs, runs cancel cleanup.

Context carries `requestId` and `tenantId` to verify tenant isolation.

### 9.1. Project Structure

~~~text
reactor-request-verification/
├── pom.xml
└── src/
    ├── main/java/com/example/verification/
    │   └── RequestScopeDemo.java
    └── test/java/com/example/verification/
        └── RequestScopeTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-request-verification</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example runs with **Java 17+** and **Reactor 3.8.8**. Maven compiler release is set to 17.

### 9.3. RequestScopeDemo.java

~~~java
package com.example.verification;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.ContextView;

public final class RequestScopeDemo {

    public static final String REQUEST_ID = "app.requestId";
    public static final String TENANT_ID = "app.tenantId";

    private final ResourceLedger ledger =
        new ResourceLedger();

    public Mono<String> identifyAfterAsyncHop() {
        return Mono.delay(Duration.ofMillis(5))
            .then(Mono.deferContextual(context ->
                Mono.just(render(context))
            ));
    }

    public Mono<String> complete() {
        return Mono.usingWhen(
            Mono.fromSupplier(ledger::open),
            lease -> identifyAfterAsyncHop(),
            ledger::complete,
            ledger::failed,
            ledger::cancelled
        );
    }

    public Mono<String> fail() {
        return Mono.usingWhen(
            Mono.fromSupplier(ledger::open),
            lease -> Mono.delay(Duration.ofMillis(5))
                .then(Mono.deferContextual(context ->
                    Mono.<String>error(
                        new DomainFailure(
                            "DOWNSTREAM_FAILURE",
                            "Simulated dependency failure"
                        )
                    )
                )),
            ledger::complete,
            ledger::failed,
            ledger::cancelled
        );
    }

    public Flux<String> stream() {
        return Flux.usingWhen(
            Mono.fromSupplier(ledger::open),
            lease -> Flux.deferContextual(context ->
                Flux.interval(Duration.ofMillis(10))
                    .map(tick -> render(context) + "|" + tick)
            ),
            ledger::complete,
            ledger::failed,
            ledger::cancelled
        );
    }

    private static String render(ContextView context) {
        String requestId = context.get(REQUEST_ID);
        String tenantId = context.get(TENANT_ID);
        return requestId + "|" + tenantId;
    }

    public ResourceLedger.Snapshot snapshot() {
        return ledger.snapshot();
    }

    static final class Lease {
        private final AtomicBoolean released =
            new AtomicBoolean();
    }

    static final class ResourceLedger {

        private final AtomicInteger opened = new AtomicInteger();
        private final AtomicInteger completed = new AtomicInteger();
        private final AtomicInteger failed = new AtomicInteger();
        private final AtomicInteger cancelled = new AtomicInteger();
        private final AtomicInteger active = new AtomicInteger();

        Lease open() {
            opened.incrementAndGet();
            active.incrementAndGet();
            return new Lease();
        }

        Mono<Void> complete(Lease lease) {
            return release(lease, completed);
        }

        Mono<Void> failed(Lease lease, Throwable error) {
            return release(lease, failed);
        }

        Mono<Void> cancelled(Lease lease) {
            return release(lease, cancelled);
        }

        private Mono<Void> release(
            Lease lease,
            AtomicInteger outcome
        ) {
            return Mono.fromRunnable(() -> {
                if (lease.released.compareAndSet(false, true)) {
                    outcome.incrementAndGet();
                    active.decrementAndGet();
                }
            });
        }

        Snapshot snapshot() {
            return new Snapshot(
                opened.get(),
                completed.get(),
                failed.get(),
                cancelled.get(),
                active.get()
            );
        }

        record Snapshot(
            int opened,
            int completed,
            int failed,
            int cancelled,
            int active
        ) {}
    }

    public static final class DomainFailure
            extends RuntimeException {

        private final String code;

        DomainFailure(String code, String message) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        RequestScopeDemo demo = new RequestScopeDemo();

        String identified = demo.identifyAfterAsyncHop()
            .contextWrite(context -> context
                .put(REQUEST_ID, "req-001")
                .put(TENANT_ID, "tenant-A")
            )
            .block();

        System.out.println("identify=" + identified);

        String completed = demo.complete()
            .contextWrite(context -> context
                .put(REQUEST_ID, "req-002")
                .put(TENANT_ID, "tenant-A")
            )
            .block();

        System.out.println("complete=" + completed);

        try {
            demo.fail()
                .contextWrite(context -> context
                    .put(REQUEST_ID, "req-003")
                    .put(TENANT_ID, "tenant-B")
                )
                .block();
        }
        catch (DomainFailure error) {
            System.out.println("error=" + error.code());
        }

        var values = demo.stream()
            .take(2)
            .contextWrite(context -> context
                .put(REQUEST_ID, "req-004")
                .put(TENANT_ID, "tenant-B")
            )
            .collectList()
            .block();

        System.out.println("stream=" + values);
        System.out.println("ledger=" + demo.snapshot());
    }
}
~~~

### 9.4. Service Explanation

- `identifyAfterAsyncHop()` awaits an async boundary and then reads `ContextView`, rather than pulling IDs from `ThreadLocal`.
- `complete()` uses `Mono.usingWhen` and runs complete cleanup.
- `fail()` produces `DomainFailure` after an async hop; `usingWhen` runs the `failed` branch.
- `stream()` uses `Flux.usingWhen` with an infinite interval source.
- `take(2)` completes with two items while cancelling the upstream stream; `usingWhen` invokes the `cancelled` branch.
- `ResourceLedger` guards release with `AtomicBoolean` so each lease increments exactly one outcome counter.
- `snapshot()` lets tests verify `active` returned to 0.

In a real application, a lease might be a connection, cursor, file handle, or broker subscription. Cleanup methods return Publishers that perform appropriate commit/rollback/close work.

### 9.5. RequestScopeTest.java

~~~java
package com.example.verification;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.*;

class RequestScopeTest {

    private static final String REQUEST_ID =
        RequestScopeDemo.REQUEST_ID;
    private static final String TENANT_ID =
        RequestScopeDemo.TENANT_ID;

    @Test
    void contextSurvivesAsyncBoundary() {
        RequestScopeDemo demo = new RequestScopeDemo();

        StepVerifier.create(
                demo.identifyAfterAsyncHop()
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-A")
                        .put(TENANT_ID, "tenant-A")
                    )
            )
            .expectNext("req-A|tenant-A")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void concurrentRequestsKeepIndependentContexts() {
        RequestScopeDemo demo = new RequestScopeDemo();

        Mono<List<String>> results =
            Flux.range(1, 40)
                .flatMap(index ->
                    demo.identifyAfterAsyncHop()
                        .contextWrite(context -> context
                            .put(REQUEST_ID, "req-" + index)
                            .put(TENANT_ID, "tenant-" + index)
                        ),
                    8
                )
                .collectList();

        StepVerifier.create(results)
            .assertNext(values -> {
                assertEquals(40, values.size());
                for (int index = 1; index <= 40; index++) {
                    assertTrue(values.contains(
                        "req-" + index + "|tenant-" + index
                    ));
                }
            })
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void completePathReleasesResource() {
        RequestScopeDemo demo = new RequestScopeDemo();
        var before = demo.snapshot();

        StepVerifier.create(
                demo.complete()
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-complete")
                        .put(TENANT_ID, "tenant-A")
                    )
            )
            .expectNext("req-complete|tenant-A")
            .expectComplete()
            .verify(Duration.ofSeconds(2));

        var after = demo.snapshot();

        assertEquals(before.opened() + 1, after.opened());
        assertEquals(before.completed() + 1, after.completed());
        assertEquals(before.failed(), after.failed());
        assertEquals(before.cancelled(), after.cancelled());
        assertEquals(before.active(), after.active());
    }

    @Test
    void errorPathPreservesFailureAndReleasesResource() {
        RequestScopeDemo demo = new RequestScopeDemo();
        var before = demo.snapshot();

        StepVerifier.create(
                demo.fail()
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-error")
                        .put(TENANT_ID, "tenant-B")
                    )
            )
            .expectErrorSatisfies(error -> {
                assertInstanceOf(
                    RequestScopeDemo.DomainFailure.class,
                    error
                );
                var failure =
                    (RequestScopeDemo.DomainFailure) error;
                assertEquals("DOWNSTREAM_FAILURE", failure.code());
            })
            .verify(Duration.ofSeconds(2));

        var after = demo.snapshot();

        assertEquals(before.opened() + 1, after.opened());
        assertEquals(before.failed() + 1, after.failed());
        assertEquals(before.active(), after.active());
    }

    @Test
    void takeCompletesDownstreamAndCancelsResourceScope() {
        RequestScopeDemo demo = new RequestScopeDemo();
        var before = demo.snapshot();

        StepVerifier.create(
                demo.stream()
                    .take(2)
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-cancel")
                        .put(TENANT_ID, "tenant-C")
                    )
            )
            .expectNext(
                "req-cancel|tenant-C|0",
                "req-cancel|tenant-C|1"
            )
            .expectComplete()
            .verify(Duration.ofSeconds(2));

        var after = demo.snapshot();

        assertEquals(before.opened() + 1, after.opened());
        assertEquals(before.cancelled() + 1, after.cancelled());
        assertEquals(before.active(), after.active());
    }

    @Test
    void timeoutCancelsTheOriginalPublisher() {
        PublisherProbe<String> remote =
            PublisherProbe.of(Mono.<String>never());

        StepVerifier.withVirtualTime(() ->
                remote.mono().timeout(Duration.ofSeconds(30))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(30))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));

        remote.assertWasSubscribed();
        remote.assertWasCancelled();
    }

    @Test
    void takeCancelsThePublisherItNoLongerNeeds() {
        PublisherProbe<Integer> source =
            PublisherProbe.of(Flux.range(1, 100));

        StepVerifier.create(source.flux().take(2))
            .expectNext(1, 2)
            .expectComplete()
            .verify(Duration.ofSeconds(2));

        source.assertWasSubscribed();
        source.assertWasCancelled();
    }

    @Test
    void testPublisherCanDriveAnErrorDeterministically() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.next("accepted"))
            .expectNext("accepted")
            .then(() -> source.error(
                new IllegalArgumentException("bad event")
            ))
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                    && "bad event".equals(error.getMessage())
            )
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void missingRequiredContextFailsClearly() {
        RequestScopeDemo demo = new RequestScopeDemo();

        StepVerifier.create(demo.identifyAfterAsyncHop())
            .expectError()
            .verify(Duration.ofSeconds(2));
    }
}
~~~

### 9.6. What the Tests Prove

| Test | Evidence |
| --- | --- |
| contextSurvivesAsyncBoundary | ContextView remains readable after delay |
| concurrentRequestsKeepIndependentContexts | 40 subscriptions never mix requestId/tenantId |
| completePathReleasesResource | asyncComplete increments, active does not grow |
| errorPathPreservesFailureAndReleasesResource | DomainFailure is preserved and failed branch runs |
| takeCompletesDownstreamAndCancelsResourceScope | downstream completes, cancel cleanup is invoked |
| timeoutCancelsTheOriginalPublisher | TimeoutException downstream, PublisherProbe sees upstream cancel |
| takeCancelsThePublisherItNoLongerNeeds | take(2) stops the source from continuing |
| testPublisherCanDriveAnErrorDeterministically | TestPublisher emits item then error per scenario |
| missingRequiredContextFailsClearly | Missing required Context fails explicitly |

### 9.7. Running the Program

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=com.example.verification.RequestScopeDemo
~~~

Expected output:

~~~text
identify=req-001|tenant-A
complete=req-002|tenant-A
error=DOWNSTREAM_FAILURE
stream=[req-004|tenant-B|0, req-004|tenant-B|1]
ledger=Snapshot[opened=3, completed=1, failed=1, cancelled=1, active=0]
~~~

Run tests:

~~~bash
mvn clean test
~~~

Expected: 9 JUnit tests PASS. This is the expected output from the presented code; run Maven in your project environment to confirm actual results.

## 10. Injecting Request Context in Spring WebFlux

`WebFilter` is the right boundary to validate/generate a request ID and put it into Reactor Context.

~~~java
@Component
public class RequestContextWebFilter implements WebFilter {

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Request-ID");

            String requestId =
                incoming != null
                    && SAFE_ID.matcher(incoming).matches()
                    ? incoming
                    : UUID.randomUUID().toString();

            exchange.getResponse().getHeaders().set(
                "X-Request-ID",
                requestId
            );

            return chain.filter(exchange)
                .contextWrite(context ->
                    context.put(
                        RequestScopeDemo.REQUEST_ID,
                        requestId
                    )
                );
        });
    }
}
~~~

Required imports: `Pattern`, `UUID`, `Component`, `ServerWebExchange`, `WebFilter`, `WebFilterChain`, and `Mono`. This is an illustrative Spring WebFlux adapter; the pure Reactor project above does not depend on Spring.

### 10.1. Tenant Must Come from a Trusted Source

Do not read tenant ID from an arbitrary client header and use it as a security boundary. In production, derive tenant from the authenticated principal/claims or a trusted gateway, then write it into Context via `contextWrite`.

### 10.2. Response Headers and Controllers

Returning `X-Request-ID` helps callers provide an ID when reporting errors. If a browser must read custom response headers via CORS, expose the header according to CORS policy. Never include stack traces, secrets, or internal info in responses.

Controllers must return Publishers:

~~~java
@GetMapping("/orders")
public Flux<OrderDto> orders() {
    return service.findOrders();
}
~~~

Do not call `subscribe()` or `block()` inside a controller. The WebFlux adapter owns the subscription and can propagate cancellation when the HTTP client disconnects.

## 11. Error Handling at the HTTP Boundary

A `@RestControllerAdvice` class can map domain errors into stable statuses and bodies:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DomainFailure.class)
    public ResponseEntity<ApiError> handle(
        DomainFailure error
    ) {
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError(
                error.code(),
                "The operation could not be completed"
            ));
    }

    public record ApiError(
        String code,
        String message
    ) {}
}
~~~

This snippet is annotation-API compatible with Spring MVC/WebFlux; supply imports and your application's `DomainFailure`.

Do not arbitrarily return `error.getMessage()` if it might contain hostnames, SQL, tokens, or internal data. Log details server-side with the request ID; return a safe error code to the client.

## 12. Integrating WebClient and Dependencies

When calling downstreams, request context is read at subscription time and translated into headers per contract.

~~~java
ExchangeFilterFunction requestIdFilter =
    (request, next) ->
        Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                RequestScopeDemo.REQUEST_ID,
                "missing"
            );

            ClientRequest outgoing =
                ClientRequest.from(request)
                    .headers(headers ->
                        headers.set("X-Request-ID", requestId)
                    )
                    .build();

            return next.exchange(outgoing);
        });
~~~

This is a client-side `WebClient` filter. In production, handle missing request IDs explicitly rather than using a shared `"missing"` string across requests. When using Micrometer Tracing, let the tracing framework propagate `traceparent`; custom `X-Request-ID` requires its own contract.

`WebClient` cancellation tries to stop unnecessary I/O, but does not prove the remote service has not committed a side effect. For order creation/payment operations, use idempotency keys and reconciliation.

## 13. Verifying Cancellation and Resources in Tests

### 13.1. StepVerifier

`StepVerifier` can:

- `expectSubscription()` verifies subscription.
- `thenRequest(n)` controls demand.
- `expectNext`/`expectError`/`expectComplete` verifies signals.
- `thenCancel()` actively cancels.
- `verify(Duration)` sets a real-time ceiling.
- `withVirtualTime()` tests timeouts/delays without waiting in real time.

Do not use unbounded `verify()` with `Flux.never()`.

### 13.2. PublisherProbe

`PublisherProbe` verifies whether a specific source was subscribed, requested, or cancelled. Place the probe at the exact boundary to prove, especially when `take`/`timeout`/`switchMap` cancels upstream or an inner Publisher.

### 13.3. TestPublisher

`TestPublisher` lets tests deterministically emit `next`/`error`/`complete` on demand. It is suited for simulating dependency failures or signal sequences without sleeping.

### 13.4. Async Cleanup Must Be Awaited

If cleanup runs on another Scheduler, verifying cancellation does not necessarily wait for external fire-and-forget tasks. Use `CountDownLatch`, `CompletableFuture`, or cleanup Publishers composed via `usingWhen`. Avoid `Thread.sleep` because timing depends on CI machines.

### 13.5. Verify Each Resource Is Released Exactly Once

Count open/complete/error/cancel and active. After tests, check:

~~~text
active = 0
opened = completed + failed + cancelled
~~~

If the system allows leases to outlive a request, design a separate lifecycle model and assert against expected state rather than forcing `active` to immediately hit 0.

## 14. Retries, Timeouts, and Request Context

Retries resubscribe upstream. If a request ID represents a logical request, keep the ID stable across attempts; if attempts must be distinguished, add a separate attempt number.

~~~java
Mono.deferContextual(context ->
    remoteCall()
        .retryWhen(retryPolicy)
        .doOnError(error ->
            log.error(
                "requestId={} failed after retries",
                context.get(RequestScopeDemo.REQUEST_ID),
                error
            )
        )
);
~~~

This snippet requires `remoteCall` and `retryPolicy`. Timeouts can cancel the original source. Retrying after a timeout creates a new attempt; each attempt needs a clear deadline and budget. Never blindly retry validation, authentication, or business rejection errors.

A subscription's Context should not be replaced with a new ID on every retry unless system semantics specifically require a per-attempt ID.

## 15. Context Loss at Boundaries Outside Reactor

Reactor Context does not automatically propagate across all Java mechanisms:

- `new Thread(...)`.
- `CompletableFuture.supplyAsync(...)`.
- Uninstrumented `ExecutorService`.
- Callbacks from legacy libraries.
- Independent message broker listeners.
- A separate `subscribe()` creating a new subscription.

For tasks outside Reactor, pass the request ID explicitly or use Micrometer Context Propagation/`ContextSnapshot` and appropriate executor decorators.

If a job is processed minutes later or in another process, send structured metadata in message headers and construct a new Context at the consumer. Do not send raw request objects or security credentials just to preserve correlation.

## 16. Common Design Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Request A logs Request B's ID | Global `ThreadLocal` without restore | Reactor Context per subscription |
| `ContextView` missing key | `contextWrite` misplaced or key absent | Inspect chain order and fail fast |
| Resource leak on client disconnect | Cleanup only on complete/error | `usingWhen` `asyncCancel` |
| Cleanup runs twice | Multiple owners closing the same resource | Single owner, idempotent release |
| Error turned into success | `onErrorResume` returning empty/fake value | Recover only valid error types and preserve semantics |
| Cleanup error lost | Separate `subscribe` or swallowed error | Compose cleanup Publisher |
| `take(2)` does not show complete | Test expects upstream terminal instead of downstream | Measure the right side of the operator |
| Timeout test waits too long | Using real clock | `StepVerifier.withVirtualTime` |
| Flaky tests | `Thread.sleep` and races | Latches, probes, verify timeouts |
| Remote still executes POST after cancel | Server already received side effect | Idempotency/reconciliation |
| One request overwrites another's Context | Static mutable map/`ThreadLocal` | `contextWrite` per subscription |
| `active` resource never returns to 0 | Missing release branch or failing release | Ledger, metrics, heap/thread dump |
| MDC not cleaned up | Missing `finally`/reset accessor | Scope restore/remove |
| Tenant data leaks across users | Trusting client-supplied tenant header | Derive tenant from authenticated identity |
| Excessive stack traces in logs | Every layer logs full exceptions in `doOnError` | Choose one boundary for detailed logging |

## 17. Reactive Request Review Checklist

1. Is the request ID validated or generated at the boundary?
2. Is the tenant/principal obtained from a trusted source?
3. Is metadata written into Reactor Context using `contextWrite`?
4. Are operators that read Context placed properly relative to `contextWrite`?
5. Is `ContextView` read at subscription time instead of static `ThreadLocal`?
6. Do concurrent requests A and B remain isolated?
7. Are errors propagated/mapped to the right domain types?
8. Could recovery accidentally hide a real error?
9. Does timeout cancel upstream?
10. Does client disconnect cancel the stream?
11. Are resources created per subscription?
12. Does `usingWhen` cover complete/error/cancel cleanup?
13. Is async cleanup composed and are its errors observable?
14. Is release idempotent when required by contract?
15. Do active resources return to the expected state after tests?
16. Do retries preserve the logical request ID?
17. Does `WebClient` forward request ID/trace context per contract?
18. Are there zero hidden `subscribe()`/`block()` calls in controllers/services?
19. Do MDC scopes restore/remove properly?
20. Do tests have finite timeouts and avoid `Thread.sleep`?
21. Are integration tests present for real adapters/drivers when needed?
22. Are metrics present for active resources, failures, timeouts, and cancellations?

## 18. Practice Exercises

**Exercise 1 — Context:** pass `requestId` and `tenantId` with `contextWrite`; read them with `deferContextual` after `Mono.delay`.

**Exercise 2 — Isolation:** run 100 concurrent subscriptions with different IDs; verify no `requestId`/`tenantId` pair mixes.

**Exercise 3 — Missing context:** omit a required key and verify an explicit error instead of a generic fallback.

**Exercise 4 — Error mapping:** translate `DependencyException` into `DomainFailure`, preserving cause and error code.

**Exercise 5 — Error recovery:** fall back only on `TimeoutException`; verify validation errors still propagate.

**Exercise 6 — Resource complete:** open a lease with `usingWhen`, complete, and verify `active` returns to its initial value.

**Exercise 7 — Resource error:** emit an error from the resource closure and verify `asyncError` runs once.

**Exercise 8 — Resource cancel:** use `Flux.interval` + `take(2)`, verify downstream completes while `asyncCancel` runs.

**Exercise 9 — Timeout:** use virtual time to trigger `TimeoutException` and `PublisherProbe` to verify upstream was cancelled.

**Exercise 10 — TestPublisher:** deterministically emit an item then an error; verify signal ordering.

**Exercise 11 — MDC:** open a scope, throw an exception, and verify `ThreadLocal` is restored.

**Exercise 12 — WebFilter:** validate `X-Request-ID`, generate a UUID when missing/invalid, and echo it in the response header.

**Exercise 13 — WebClient:** forward the request ID into a downstream header; verify using a mock server.

**Exercise 14 — Retry:** keep the same request ID across three attempts and add a separate attempt number.

**Exercise 15 — Integration:** client cancels SSE mid-stream; check server cleanup and active resources.

**Exercise 16 — Security:** derive tenant from the authenticated principal; do not trust client-sent `X-Tenant-ID`.

## 19. Takeaways

A reactive request must be verified across four dimensions: **errors, cancellation, resource lifecycle, and Context isolation**.

Reactor Context scopes metadata per subscription, so requests A and B can run on the same thread while keeping distinct IDs. `StepVerifier` and `PublisherProbe` verify signals and upstream cancellation. `usingWhen` ties cleanup to the three branches: complete, error, and cancel. A resource ledger or metrics help prove each lease was released exactly once.

Never use MDC/`ThreadLocal` as the source of truth for a request in WebFlux, never manually subscribe side tasks, never swallow cleanup errors, and never treat client cancellation as a remote side-effect rollback. Concurrency tests, error tests, timeout tests, and cancellation tests must check both downstream results and resource state.

## 20. References

- Project Reactor Reference — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor Reference — Cleanup and Discard: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Project Reactor Reference — Testing: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Core API — Flux.usingWhen: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core API — Mono.usingWhen: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Test API — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test API — PublisherProbe: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html
- Reactor Test API — TestPublisher: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html
- Spring Framework Reference — WebFlux WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux-webfilter.html
- Spring Framework Reference — WebClient Filters: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
- Spring Framework Reference — Reactive Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Micrometer Context Propagation — Purpose and Usage: https://docs.micrometer.io/context-propagation/reference/
- Reactive Streams Specification: https://www.reactive-streams.org/
