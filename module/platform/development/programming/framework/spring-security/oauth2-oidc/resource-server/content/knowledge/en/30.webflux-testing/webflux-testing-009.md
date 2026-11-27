# Testing Timeouts, Cancellation, and Unexpected Blocking Operations

In a **Spring Security OAuth 2.0 / OIDC Resource Server running on WebFlux**, requests are typically processed by Reactor publishers such as `Mono` and `Flux`. A reactive pipeline is only truly safe when it handles three situations properly: **work taking too long (timeout), the subscriber no longer needing the result (cancellation), and code accidentally blocking a thread (blocking)**.

These three situations are related, yet distinct:

- **Timeout:** a time limit applied to a publisher or an I/O layer. When exceeded, the pipeline emits a timeout error or switches to a fallback; the operator typically cancels upstream.
- **Cancellation:** downstream actively signals that it no longer needs data. Reactor propagates the cancel signal upstream so components can stop and release resources.
- **Blocking:** a synchronous operation holds a thread until I/O or computation completes. In WebFlux, blocking on the event loop can slow down many concurrent requests at once.

An application might configure a timeout yet still fail to cancel underlying work; receive cancellation while a legacy JDBC library keeps running; or hit no timeout at all while a `block()` call stalls the event loop. Therefore, each behavior must be tested using **Reactor Test, StepVerifier, WebTestClient, TestPublisher, PublisherProbe, and BlockHound**.

This lesson belongs to the **WebFlux Testing** chapter, using **Java 17+, Spring Boot 3.x, Spring Security 6.x, and Project Reactor** as context. The focus is on reproducible timing checks, proving upstream cancellation, detecting unexpected blocking, and ensuring authentication dependency failures never cause requests to be accepted mistakenly.

## 1. Reactive Processing Model in WebFlux

A request passing through WebFlux typically looks like:

~~~text
HTTP request
    |
    v
WebFlux WebFilter chain
    |
    v
Spring Security WebFilter chain
    |
    +-- Bearer token authentication
    |      |
    |      +-- ReactiveJwtDecoder
    |      |
    |      +-- ReactiveOpaqueTokenIntrospector
    |
    v
Authorization
    |
    v
Controller returns Mono/Flux
    |
    v
Service -> WebClient / reactive database / other publisher
    |
    v
HTTP response
~~~

The controller typically returns a publisher so the framework can subscribe and write the response. When the client disconnects or the response is no longer consumed, cancellation can propagate down the pipeline. If the application manually calls `subscribe()`, `block()`, or dispatches work to an unmanaged thread, that control flow can break.

### 1.1. Reactive Does Not Mean Threadless

Reactor still uses threads and schedulers. The difference is that reactive I/O operations generally do not hold a thread for the entire wait duration. One event-loop thread can multiplex many connections; if one request performs blocking I/O on that thread, other requests sharing the event loop can also slow down.

### 1.2. Three Terminal Signals of a Publisher

A publisher can terminate via:

| Signal | Meaning | Observation operator |
| --- | --- | --- |
| `onComplete` | Normal completion. | `doOnComplete`, `doFinally(ON_COMPLETE)` |
| `onError` | Termination due to an error. | `doOnError`, `doFinally(ON_ERROR)` |
| `cancel` | Subscriber no longer needs results. | `doOnCancel`, `doFinally(CANCEL)` |

Cancellation is **not** an `onError` delivered to the subscriber. Once a subscriber cancels, it receives no further values or normal terminal errors from upstream; cancellation hooks are used for cleanup and measurement.

## 2. Distinguishing Timeout, Cancellation, and Blocking

~~~text
TIMEOUT
  Publisher exceeds deadline
       |
       +-- timeout operator cancels upstream
       +-- downstream receives TimeoutException or fallback

CANCELLATION
  Client/subscriber no longer needs result
       |
       +-- cancel propagates upstream
       +-- cleanup has a chance to run
       +-- downstream receives no further results

BLOCKING
  Code holds a thread while waiting
       |
       +-- event-loop cannot serve other requests
       +-- latency rises, throughput drops
       +-- may not trigger a timeout in time
~~~

A timeout typically triggers upstream cancellation, yet cancellation is not necessarily a timeout: a client can close the connection early, `take(1)` can cancel the source after the first item, or a test can explicitly call `thenCancel()`.

Blocking does not automatically imply a timeout either. A thread can be blocked for 200 ms while the timeout is 5 seconds; the request still succeeds, yet it added latency to other requests.

## 3. Timeout Layers That Must Be Tested Separately

An outbound request from WebFlux can wait across multiple stages:

~~~text
Subscribe
   |
   v
DNS resolution
   |
   v
TCP connect
   |
   v
TLS handshake
   |
   v
Send request
   |
   v
Wait for response / read body
   |
   v
Decode response
   |
   v
Application processing
~~~

A single overall timeout does not replace every transport-layer timeout. Conversely, configuring multiple independent timeouts without understanding their relationship can cause premature failures or hard-to-diagnose errors.

| Timeout | Limit | Control example |
| --- | --- | --- |
| DNS/connect timeout | Time to resolve address/establish TCP connection. | Resolver/HTTP connector configuration. |
| TLS handshake timeout | Time to complete the TLS handshake. | TLS client connector policy. |
| Response/read timeout | Time waiting for a response or next chunk of data. | Reactor Netty `responseTimeout`. |
| Publisher timeout | Time waiting for a `Mono` signal or `Flux` idle gap. | Reactor `timeout(Duration)`. |
| End-to-end deadline | Total time the use case is allowed to run. | Deadline propagated across service layers. |
| Test verification timeout | Maximum time the test is allowed to wait. | `StepVerifier.verify(Duration)`. |

**A test verification timeout is not a production timeout.** `verify(Duration.ofSeconds(2))` prevents tests from hanging indefinitely; it does not add a timeout to the publisher when the application runs in production.

### 3.1. Mono.timeout and Flux.timeout

For `Mono`, `timeout(Duration)` bounds the wait for the first item or terminal signal. For `Flux`, a timeout can trigger if no next item arrives within the configured interval; this limits the idle gap between items, not necessarily the total stream duration.

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .timeout(Duration.ofSeconds(2));

Flux<Event> events =
    eventRepository.findByOrderId(orderId)
        .timeout(Duration.ofSeconds(5));
~~~

In the second example, a stream emitting items steadily can live longer than 5 seconds because the timeout resets on each signal per operator semantics. If you need an **overall deadline**, apply a separate deadline across the whole pipeline.

### 3.2. Timeout Fallbacks

`timeout` can switch to a fallback publisher:

~~~java
Mono<Profile> profile =
    remoteProfileClient.fetch(userId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.just(Profile.unavailable()));
~~~

Fallbacks are only appropriate when business requirements clearly define a substitute result. For authentication, authorization, or sensitive data, **never use a fallback that creates a default principal or permission** when introspection/JWT verification times out.

### 3.3. Retries Can Increase Total Duration

~~~java
Mono<Response> response =
    remoteClient.call()
        .timeout(Duration.ofSeconds(2))
        .retry(2);
~~~

This snippet can perform multiple attempts, each with its own timeout. Total duration can exceed 2 seconds. For operations with side effects, retries can send commands multiple times. You need an overall deadline, retry budget, backoff, error classification, and idempotency keys.

## 4. Configuring Timeouts for WebClient/Reactor Netty

A `WebClient` using Reactor Netty can configure connect timeout and response timeout:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration
public class DownstreamHttpConfiguration {

    @Bean
    WebClient downstreamWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

`CONNECT_TIMEOUT_MILLIS` bounds establishing the TCP connection; `responseTimeout` controls the wait for a response in Reactor Netty. Check exact method names and scope against your actual Reactor Netty version.

### 4.1. Adding a Deadline for a Use Case

~~~java
public Mono<OrderSummary> getOrderSummary(String orderId) {
    return orderClient.getOrder(orderId)
        .flatMap(order ->
            inventoryClient.getAvailability(order)
                .map(inventory ->
                    OrderSummary.from(order, inventory)))
        .timeout(Duration.ofSeconds(5));
}
~~~

The pipeline deadline limits total time from subscription to result for this pipeline. If a request needs a shared deadline across multiple services, propagate the deadline/remaining budget across layers instead of letting each downstream configure a timeout longer than the overall SLA.

### 4.2. Do Not Apply Arbitrary Global Timeouts Across the Entire Application

An overly short global timeout can break legitimate downloads/streaming responses, Server-Sent Events, WebSockets, large uploads, long-running report calculations, or APIs with different SLAs.

Choose timeouts per endpoint/use case and I/O type. For long streams, distinguish **idle timeout** from **maximum session duration**.

## 5. Testing Timeouts with StepVerifier

`StepVerifier` lets you declare expected signals from a publisher in order. When testing timeouts, use **virtual time** so tests run fast and deterministically without waiting real seconds.

Test dependency:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

### 5.1. Testing Mono Timeout with Virtual Time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTests {

    @Test
    void emitsTimeoutWhenMonoDoesNotCompleteInTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .thenReturn("done")
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(1));
    }
}
~~~

Key points:

- Construct the publisher **inside the supplier** passed to `withVirtualTime`.
- `thenAwait` advances the virtual clock without actually waiting 3 seconds.
- `expectError` confirms timeout is the pipeline's outcome.
- `verify(Duration)` still puts a real ceiling on test execution time.

### 5.2. Why Must the Publisher Be Created Inside the Supplier?

Avoid:

~~~java
Mono<Long> delayed = Mono.delay(Duration.ofSeconds(10));

StepVerifier.withVirtualTime(() ->
        delayed.timeout(Duration.ofSeconds(3)))
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
~~~

A publisher or scheduler created before the virtual scheduler is installed may already capture the real scheduler. Creating the publisher inside the supplier lets operators obtain the scheduler after virtual time is configured.

### 5.3. Testing a Fallback After Timeout

~~~java
@Test
void switchesToFallbackAfterTimeout() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofSeconds(10))
                .thenReturn("remote")
                .timeout(
                    Duration.ofSeconds(2),
                    Mono.just("cached")))
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("cached")
        .verifyComplete();
}
~~~

This test checks a business fallback. It does not prove a fallback is security-appropriate; for token authentication, a fallback must never produce an authenticated identity when the authentication source has not responded.

## 6. Testing Explicit Cancellation with StepVerifier

`thenCancel()` cancels the subscription after previous expectations complete:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CancellationTests {

    @Test
    void propagatesCancellationToSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Mono<String> source = Mono.<String>never()
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source)
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(1));

        assertTrue(cancelled.get());
    }
}
~~~

What to verify: the subscriber subscribed, the test triggered cancel, `doOnCancel` ran, and no values or completions were emitted after cancellation.

### 6.1. Distinguishing doOnCancel and doFinally

~~~java
source
    .doOnCancel(() -> metrics.incrementCancel())
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            releaseCancellationResources();
        }
    });
~~~

- `doOnCancel` runs when the subscription is cancelled.
- `doFinally` runs when the publisher terminates via complete, error, or cancel.
- `doOnError` does not run simply on cancellation.
- `doOnSuccess` is not a cleanup hook for all termination types.

Do not place cleanup only inside `doOnSuccess` if resources still need to be released on error or cancel.

## 7. Proving That Timeout Cancels Upstream

A test that only asserts `TimeoutException` is insufficient. You must verify that the upstream source received cancellation.

`TestPublisher` lets you control upstream signals:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class TimeoutCancellationTests {

    @Test
    void timeoutCancelsUpstream() {
        TestPublisher<String> upstream =
            TestPublisher.create();

        StepVerifier.withVirtualTime(() ->
                upstream.mono()
                    .timeout(Duration.ofSeconds(2)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(1));

        upstream.assertCancelled();
    }
}
~~~

This test verifies an important behavior: when a timeout occurs, the operator cancels the source. In a real HTTP client, cancellation is typically propagated to the transport connector to abort the request/dispose the exchange, though how far server-side work stops depends on the protocol and server handling the request.

### 7.1. Testing That Fallback Is Subscribed and Source Is Cancelled

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

class TimeoutFallbackTests {

    @Test
    void cancelsSlowSourceAndSubscribesFallback() {
        TestPublisher<String> source = TestPublisher.create();
        PublisherProbe<String> fallback =
            PublisherProbe.of(Mono.just("fallback"));

        StepVerifier.withVirtualTime(() ->
                source.mono().timeout(
                    Duration.ofSeconds(1),
                    fallback.mono()))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("fallback")
            .verifyComplete();

        source.assertCancelled();
        fallback.assertWasSubscribed();
    }
}
~~~

`PublisherProbe` confirms the fallback branch was genuinely subscribed to. This is a better control-flow check than merely inspecting the final value when multiple branches could return the same value.

## 8. Cancellation Does Not Equal Rollback

~~~text
Client sends POST /payments
        |
        v
WebFlux service sends command to Payment Provider
        |
        v
Provider received and processed the command
        |
        v
Client closes connection / publisher is cancelled
        |
        v
Application stops waiting for the result

Yet the payment may already have been executed.
~~~

Cancellation is a control-flow signal. It does not automatically roll back side effects already committed to a database or remote system.

For operations with side effects:

- Use idempotency keys so retries do not create duplicate transactions.
- Persist operation state so outcomes can be queried if the client disconnects.
- Use transactions/outbox/sagas and compensation when business logic requires.
- Distinguish "the client did not receive a response" from "the server did not execute."
- Do not report a transaction as failed solely because the subscriber was cancelled.

### 8.1. Cancellation Can Arrive After Side Effects Have Started

~~~java
return paymentClient.createPayment(command)
    .timeout(Duration.ofSeconds(2));
~~~

A timeout may cancel the client publisher and stop waiting. The payment provider may still have received the request, or finished processing while the response arrived late. You need idempotency keys and a status-query API to determine the final outcome.

### 8.2. Cancellation Propagation Depends on the Source

| Upstream | Behavior on receiving cancel |
| --- | --- |
| `Mono.delay` | Cancels the timer. |
| Reactor Netty HTTP exchange | May dispose/cancel the exchange; the remote server may already have received the request. |
| Reactive database driver | May send cancellation to the database if the driver supports it. |
| JDBC over `boundedElastic` | Cancelling the subscriber does not guarantee the thread/JDBC statement stops immediately. |
| `Mono.fromFuture` | Behavior depends on the future and how bridging/cancellation is implemented. |
| Custom publisher | Depends on whether the implementation handles cancel and cleanup properly. |

Do not claim an operation stopped merely because `doOnCancel` ran at an outer layer. To be sure, test the specific driver/connector behavior and inspect actual resources.

## 9. Testing Cleanup When Cancellation Occurs

When a publisher manages resources such as files, streams, cursors, or connections, cleanup is needed on every terminal path:

~~~java
Flux<DataBuffer> body = downloadClient.fetch()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.incrementDownloadCancelled();
        }
    });
~~~

For complex resource lifecycles, prefer Reactor resource operators such as `using`/`usingWhen` per the appropriate API and driver so cleanup is bound to complete/error/cancel. Never store a resource in a shared field and rely on `doOnSuccess` to close it.

### 9.1. Testing Cleanup

~~~java
@Test
void releasesResourceWhenSubscriberCancels() {
    AtomicBoolean released = new AtomicBoolean();

    Mono<String> work = Mono.<String>never()
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                released.set(true);
            }
        });

    StepVerifier.create(work)
        .thenCancel()
        .verify(Duration.ofSeconds(1));

    assertTrue(released.get());
}
~~~

This test verifies the cleanup hook is invoked. For real connections/cursors/files, assert the actual resource state—such as a connection returned to the pool or a file handle closed.

### 9.2. Discarded Elements

Some operators may discard elements already requested yet no longer used downstream due to cancel/error/races. For resources held inside elements (such as buffers needing release), study `doOnDiscard` and operator ownership rules. Only release objects owned by the pipeline; double-releasing or releasing a buffer still in use by a consumer also causes bugs.

## 10. Detecting Blocking with BlockHound

**BlockHound** is a tool that detects blocking calls on threads marked as non-blocking, which is especially useful with Reactor event-loop/schedulers.

Test dependency:

~~~groovy
testImplementation 'io.projectreactor.tools:blockhound'
~~~

Install BlockHound once in the test JVM, following the guide for your version:

~~~java
import org.junit.jupiter.api.BeforeAll;
import reactor.blockhound.BlockHound;

class ReactiveBlockingTests {

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }
}
~~~

BlockHound relies on JVM instrumentation and may require test runtime configuration matching your JDK/agent. Install it once per test process; do not call `install` repeatedly in every test class if the suite shares a JVM.

### 10.1. A Blocking Operation on the Parallel Scheduler

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> bad = Mono.fromCallable(() -> {
        Thread.sleep(20);
        return "done";
    })
    .subscribeOn(Schedulers.parallel());
~~~

With BlockHound, a `Thread.sleep` call on a non-blocking scheduler can be caught and throw `BlockingOperationError`. Tests should confirm no blocking occurs across protected application paths.

Do not write a test solely to prove `Thread.sleep` is blocked and treat that as full coverage. Install BlockHound and exercise real service paths at risk of calling JDBC, the filesystem, or legacy SDKs.

### 10.2. Offloading Blocking APIs to boundedElastic

~~~java
public Mono<Customer> findCustomer(String id) {
    return Mono.fromCallable(() ->
            legacyJdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`boundedElastic` is designed to isolate bounded blocking work. It does not turn JDBC into non-blocking I/O, nor does it make a query automatically cancel when the subscriber cancels. Limit concurrency, configure JDBC/driver timeouts, and control pool sizes.

### 10.3. Do Not Use parallel for Blocking I/O

`Schedulers.parallel()` is meant for short CPU-bound work. Using it for `Thread.sleep`, JDBC, or file I/O can starve worker threads. For blocking bridges, use `boundedElastic` or a dedicated capacity-limited executor.

## 11. Frequently Overlooked Blocking Operations

`Thread.sleep` is not the only blocking operation:

- `Mono.block()` / `Flux.blockFirst()` / `blockLast()`.
- Synchronous JDBC/JPA repositories.
- `RestTemplate` or synchronous HTTP clients.
- `Files.readAllBytes`, `InputStream.read`, and filesystem operations.
- `Future.get()` / `CompletableFuture.join()` waiting for results.
- `CountDownLatch.await()` / `Semaphore.acquire()`.
- Synchronized locks or prolonged monitor contention.
- Third-party SDKs using synchronous network I/O.
- Slow synchronous logging appenders or writing to filesystem/network.
- Heavy JSON/XML processing or CPU-bound work on the event loop.

Not every computation is blocking I/O, yet heavy CPU work on the event loop also hogs the thread and causes starvation. For large CPU-bound tasks, use a separate bounded scheduler/executor and benchmark it.

### 11.1. Do Not Call block Inside Reactive Controllers/Services

~~~java
// DO NOT DO THIS.
public Mono<Order> getOrder(String id) {
    Order order = orderRepository.findById(id).block();
    return Mono.just(order);
}
~~~

Replace with:

~~~java
public Mono<Order> getOrder(String id) {
    return orderRepository.findById(id);
}
~~~

If the repository is synchronous JDBC, isolate it via `fromCallable(...).subscribeOn(boundedElastic())` and consider migrating to a reactive driver if the workload demands end-to-end non-blocking execution.

### 11.2. Do Not Manually Subscribe Inside Services

~~~java
// DO NOT DO THIS.
public Mono<Void> sendNotification(Event event) {
    notificationClient.send(event).subscribe();
    return Mono.empty();
}
~~~

`subscribe()` creates a subscription detached from the publisher managed by the controller/framework. The caller may receive a response before the notification finishes; cancellation, error handling, tracing, and security context propagation are no longer in the same lifecycle.

Replace with:

~~~java
public Mono<Void> sendNotification(Event event) {
    return notificationClient.send(event);
}
~~~

If a notification is a side effect meant to run independently after the request finishes, put it in a queue/outbox/background worker with its own lifecycle and retry policy; do not spawn arbitrary detached subscriptions.

## 12. Reactive Security: Never Block When Reading SecurityContext

In WebFlux, `SecurityContext` is propagated via the **Reactor Context**. Do not use Servlet-style `ThreadLocal` `SecurityContextHolder.getContext()` in a reactive pipeline.

You can retrieve the principal with:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
~~~

`ThreadLocal` does not automatically follow every Reactor thread switch. Use `ReactiveSecurityContextHolder` and keep access inside the reactive chain.

### 12.1. Do Not Turn an Authentication Timeout into an Authenticated Fallback

Suppose the Resource Server uses opaque token introspection. If the AS times out, the pipeline has no proof the token is active. Never write:

~~~java
// DO NOT DO THIS.
introspector.introspect(token)
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(error ->
        Mono.just(defaultAuthenticatedPrincipal()));
~~~

This is fail-open authentication. Timeout errors must remain authentication/dependency failures, or be mapped to a service error per the error contract; never create a default principal or permissions.

## 13. Timeouts for Reactive JWT Decoders and Opaque Introspection

Spring Security WebFlux uses reactive interfaces:

- `ReactiveJwtDecoder` returns `Mono<Jwt>`.
- `ReactiveOpaqueTokenIntrospector` returns `Mono<OAuth2AuthenticatedPrincipal>`.

If there is a specific timeout requirement for the authentication step, you can wrap the publisher:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

public final class BoundedJwtDecoder
        implements ReactiveJwtDecoder {

    private final ReactiveJwtDecoder delegate;
    private final Duration timeout;

    public BoundedJwtDecoder(
            ReactiveJwtDecoder delegate,
            Duration timeout) {
        this.delegate = delegate;
        this.timeout = timeout;
    }

    @Override
    public Mono<Jwt> decode(String token) {
        return delegate.decode(token)
            .timeout(timeout);
    }
}
~~~

Similarly for the introspector:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class BoundedOpaqueIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration timeout;

    public BoundedOpaqueIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration timeout) {
        this.delegate = delegate;
        this.timeout = timeout;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(
            String token) {
        return delegate.introspect(token)
            .timeout(timeout);
    }
}
~~~

These are illustrative decorators. In production, choose timeouts matching the AS SLA, distinguish timeouts from inactive tokens, measure latency, and handle upstream errors intentionally. Never use `onErrorResume` to turn a timeout into an active principal.

### 13.1. Authentication Timeout vs. Invalid Token

| Outcome | Meaning | How to handle |
| --- | --- | --- |
| Invalid JWT signature/claims | Token is invalid. | Authentication fails. |
| Introspection returns `active:false` | AS does not accept the token. | Authentication fails. |
| Introspection timeout | Status could not be verified. | Fail closed; record dependency timeout. |
| JWKS fetch timeout | Required signing key could not be fetched/refreshed. | Never accept the token by skipping signature checks. |
| Valid token, missing scope | Authentication succeeded, authorization insufficient. | 403 per policy. |

The HTTP status for a dependency timeout depends on exception translation and the application's error contract. You can choose a 5xx/503 response to express AS unavailability while invalid tokens return 401; configure and test this explicitly. What must never change is that **a timeout must never be treated as proof of a valid token**.

## 14. Testing a Reactive Resource Server with WebTestClient

`WebTestClient` tests a WebFlux application through an HTTP abstraction. You can bind it to the application context and apply Spring Security test support:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest
class OrdersWebFluxTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

When building the client manually from the application context, apply `springSecurity()` per the Spring Security reactive test support guide. When using test auto-configuration, verify the real security filter chain is attached to the test client.

### 14.1. Testing Authorization with mockJwt

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient.mutateWith(
        mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

`mockJwt()` builds a mock JWT Authentication for the test. It is useful for checking controller/authorization rules, yet **skips signature, timestamp, issuer, and audience verification by the real decoder**.

### 14.2. Testing Opaque Token Authorization

Reactive Security test support can supply mock opaque-token authentication:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

webTestClient.mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

This helper tests behavior once a test Authentication is in place; it does not call Authorization Server introspection. To test introspection timeouts, test the real decoder/introspector or a controllable reactive stub.

### 14.3. Distinguishing Authentication Tests from Timeout Tests

| Tool | What it tests well | What it does not prove on its own |
| --- | --- | --- |
| `mockJwt()` | Authorization by JWT principal/authorities. | Signature/time validation in the decoder. |
| `mockOpaqueToken()` | Authorization with a mock opaque principal. | HTTP introspection and `active` responses. |
| `StepVerifier` | Publisher signals, timeouts, cancel. | Full HTTP/TLS stack. |
| `WebTestClient` | HTTP response/filter/controller integration. | Blocking on every thread without BlockHound. |
| BlockHound | Blocking calls on non-blocking threads. | Business correctness and token policies. |
| Live server + HTTP client | Connection lifecycle, disconnect, transport behavior. | All production race conditions. |

## 15. Testing Timeouts of Reactive Authentication

You can stub `ReactiveJwtDecoder` to return a publisher that never emits a signal:

~~~java
ReactiveJwtDecoder slowDecoder = token -> Mono.never();
ReactiveJwtDecoder boundedDecoder =
    new BoundedJwtDecoder(
        slowDecoder,
        Duration.ofMillis(100));
~~~

When a protected request arrives with a Bearer token, the test must confirm the request does not receive an authenticated principal, the protected controller is never called, the timeout is recorded separately from invalid-token outcomes, no fallback creates a user/authority, and the response matches the defined error contract.

With an opaque introspector, use `Mono.never()` similarly. You can use `TestPublisher` to actively complete, error, or stay silent.

### 15.1. Testing with TestPublisher

~~~java
TestPublisher<Jwt> decoderResult = TestPublisher.create();

ReactiveJwtDecoder decoder =
    token -> decoderResult.mono();

// In the test, subscribe the request and drive decoderResult:
// - next(jwt) to return a JWT
// - error(exception) to simulate a failure
// - stay silent to trigger a timeout
~~~

When testing timeouts with virtual time, ensure the timeout operator uses a scheduler controlled by the virtual-time test. With full `WebTestClient` integration, test the decoder separately with `StepVerifier` first, then run an HTTP integration test with a short, explicit real timeout.

## 16. Testing for Absence of Unexpected Blocking

A practical test suite can install BlockHound once, run service publishers on the same schedulers used at runtime, call endpoints through `WebTestClient`, cover JWT decode/introspection and downstream `WebClient` paths, assert no blocking errors occur, and verify any legacy blocking adapter runs on `boundedElastic`/an allowed executor.

~~~java
Mono<String> safeLegacyCall =
    Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Tests should verify values/outcomes and scheduler isolation as designed. Do not broadly allowlist entire application packages in BlockHound just to make tests pass; if a library genuinely requires an allowlist entry, document the reason and keep its scope narrow.

### 16.1. BlockHound May Require Runtime Configuration

BlockHound instruments bytecode to detect blocking. Some JDKs/builds/test runners have agent/instrumentation requirements. If installation fails, that is a test runtime configuration error; never conclude the application has no blocking.

## 17. Event-Loop Starvation and Symptoms

Symptoms can include latency rising across multiple endpoints at once despite no downstream load increase, low CPU alongside growing event-loop pending tasks, a single request using JDBC/a blocking SDK slowing down many unrelated requests, widespread timeouts on unrelated requests, throughput collapsing as concurrency rises, or thread dumps showing `reactor-http-nio-*` waiting on synchronous I/O, locks, or `Future.get()`.

### 17.1. Distinguishing Slow Downstream from a Blocked Event Loop

| Observation | Slow downstream | Blocked event loop |
| --- | --- | --- |
| One specific downstream has high latency | Common | Possibly not |
| Multiple independent endpoints slow down together | Unlikely | Likely |
| Thread dump shows event-loop waiting synchronously | Not necessarily | Strong indicator |
| BlockHound detects blocking | Not necessarily | Likely |
| Increasing event-loop threads solves it | Unsustainable | Does not fix root cause |

Never increase event-loop thread counts or timeouts to mask an unhandled blocking call.

## 18. Cancellation When Clients Disconnect

When a client closes the connection before the response finishes, the server may receive a cancellation/disconnect and cancel the in-flight pipeline. Exact behavior depends on the server connector, protocol, and where the request is executing.

An integration test can use a live Reactor Netty server and an HTTP client to send a request to an endpoint returning a slow `Flux`, read part of the response or close the connection, verify the server-side publisher observes cancellation, verify cleanup/resource release, and ensure no unintended background tasks keep running.

`WebTestClient` fits most HTTP contract tests, but certain socket-disconnect behaviors require a **live server and real client** to simulate accurately.

### 18.1. Long Streams

~~~java
public Flux<ServerSentEvent<String>> streamEvents() {
    return eventPublisher.events()
        .map(value ->
            ServerSentEvent.builder(value).build())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.incrementStreamCancelled();
            }
        });
}
~~~

When a client closes a stream, cleanup must trigger. Do not apply a short total timeout to SSE/WebSockets if business rules require long-lived connections; use idle timeouts, heartbeats, and separate maximum lifetimes.

## 19. Cancellation, flatMap, and Concurrent Work

`flatMap` can subscribe to multiple inner publishers. When downstream cancels, Reactor propagates cancellation to inner subscriptions managed by the operator. However, if an inner task called a synchronous API or detached itself with `subscribe()`, it may keep running.

~~~java
Mono<List<InventoryItem>> result =
    Flux.fromIterable(skus)
        .flatMap(inventoryClient::findBySku, 8)
        .collectList()
        .timeout(Duration.ofSeconds(3));
~~~

Here concurrency is bounded to 8. On timeout, Reactor can cancel inner publishers; the transport/client must support cancellation to stop the corresponding I/O. For data writes or remote side effects, idempotency and business state tracking are still required.

### 19.1. Concurrency Limit Is Not a Timeout

`flatMap(..., concurrency)` limits how many inner publishers run concurrently, not how long each publisher takes. Combine concurrency limits, per-call timeouts/overall deadlines, backpressure strategies, connection pool limits, and cancellation cleanup.

## 20. Error Handling on Timeout

Timeouts typically emit `TimeoutException`. You can map it to a domain error:

~~~java
Mono<Order> order =
    orderClient.getOrder(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(
            TimeoutException.class,
            error -> new DownstreamUnavailableException(
                "Orders service timed out", error));
~~~

Do not catch all errors and return `Mono.empty()`:

~~~java
// DO NOT DO THIS.
source.onErrorResume(error -> Mono.empty());
~~~

This hides timeouts, authentication errors, and programming bugs, allowing an API to return a successful response with missing data or skip a security step.

### 20.1. Error Classification

| Category | Example | Handling |
| --- | --- | --- |
| Authentication invalid | Invalid JWT signature, inactive introspection. | 401 per security contract. |
| Authorization denied | Missing scope/role. | 403. |
| Dependency timeout | AS introspection/downstream unresponsive. | Fail closed; 5xx/503 response per contract. |
| Dependency unavailable | Connection refused, DNS, 5xx. | Bounded retry if safe; otherwise fail. |
| Client cancellation | Caller closed connection. | Cleanup; do not treat as a normal business failure. |
| Application bug | NPE, mapping bug. | Error path and alert; never fall back to success. |

### 20.2. Do Not Retry Every Timeout

A timeout may happen after a remote side effect has already executed. Before retrying, determine whether the operation is idempotent, whether an idempotency key is used, whether the remote service has a status query, whether retries could duplicate transactions, and whether enough deadline remains.

Even for introspection without business side effects, retries must still have a budget because they increase load on the AS and can worsen auth latency.

## 21. Testing Overall Deadlines and Retries

Suppose each downstream call has a 2-second timeout and up to two retries. Without an overall deadline, the request can stretch significantly:

~~~text
Attempt 1: up to 2s
Backoff:   200ms
Attempt 2: up to 2s
Backoff:   400ms
Attempt 3: up to 2s
-------------------
Total:     > 6s
~~~

An overall deadline ensures the request stays within SLA:

~~~java
Mono<Result> operation =
    callDownstream()
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(100))
                .filter(this::isTransient))
        .timeout(Duration.ofSeconds(3));
~~~

The outermost timeout sets the overall limit for the publisher. Account for backoff and cancellation of the in-flight attempt when the outer deadline expires.

### 21.1. Virtual-Time Testing for Retry/Backoff

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> callCounter.incrementAndGet() < 2
                ? Mono.error(new IOException("temporary"))
                : Mono.just("ok"))
            .retryWhen(
                Retry.backoff(1, Duration.ofSeconds(1))))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("ok")
    .verifyComplete();
~~~

The publisher is constructed inside the supplier so the retry/backoff scheduler uses virtual time. In real tests, also verify retry limits, exception filtering, and the outermost deadline.

## 22. Testing Cancellation Races and Timing

Races often arise when a timeout fires at the exact moment upstream emits a value, a client disconnects just as the response is completing, multiple requests cancel a shared publisher, a retry begins just as the overall deadline expires, or a cache hit completes concurrently with cancellation.

Do not write assertions that depend on an arbitrary thread ordering. Use `TestPublisher`, `PublisherProbe`, virtual time, or synchronization primitives strictly inside the test harness without blocking the event loop.

### 22.1. Verifying the Source Stops Emitting After Cancel

~~~java
TestPublisher<Integer> source = TestPublisher.create();
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> values = source.flux()
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(values)
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(1));

assertTrue(cancelled.get());
source.assertCancelled();
~~~

### 22.2. Do Not Use Sleep in Reactive Tests

Avoid:

~~~java
Thread.sleep(1000);
assertTrue(cancelled.get());
~~~

`Thread.sleep` makes tests slow and flaky. Use `StepVerifier`, virtual time, `TestPublisher`, or test-harness synchronization.

## 23. WebFlux Security Test Matrix

For a reactive Resource Server, timeout/cancellation/blocking tests should also cover the authentication pipeline:

| Scenario | Outcome to verify |
| --- | --- |
| Valid JWT, fast decoder response | Request authenticated and authorization works. |
| Expired JWT / future `nbf` | Authentication fails. |
| `ReactiveJwtDecoder` emits no signal | Timeout; protected controller never runs. |
| Opaque introspection `active=false` | 401 per contract. |
| Opaque introspection timeout | Fail closed; no fallback principal created. |
| JWKS fetch/refresh timeout | Signature validation is never skipped. |
| Valid token missing scope | 403. |
| Downstream `WebClient` timeout | Dependency error classified properly. |
| Request cancelled during downstream call | Upstream cancelled if connector supports it. |
| Client disconnects mid-stream | Cleanup invoked. |
| JDBC/legacy call on event loop | Caught by BlockHound. |
| JDBC/legacy call on `boundedElastic` | Event loop unblocked; concurrency still bounded. |
| Service manually calls subscribe | Tests/inspection catch detached lifecycle. |
| Timeout fallback | Only allowed business fallbacks used, never identity/permission fallbacks. |
| Retry after timeout | No duplicated side effects or exceeded overall deadline. |

## 24. Production Observability

Useful metrics:

- Request latency by endpoint.
- Timeout count by dependency/operation.
- Authentication latency (JWT decode, JWKS, introspection).
- Cancellation count by route/downstream.
- Active subscriptions/streams and open connection counts.
- `WebClient` connection pool pending acquires, active connections, and errors.
- Retry attempts, retry exhaustion, and overall deadline exceeded counts.
- Event-loop pending tasks/latency and scheduler queue depth.
- Blocking detector/test findings.

Never put raw Access Tokens, Refresh Tokens, Authorization headers, sensitive claims, or URL queries containing secrets into metrics/logs/traces.

### 24.1. Distinguishing Timeout from Cancellation in Telemetry

A timeout operator typically produces a `TimeoutException` downstream and cancels upstream. Counting only cancellations hides whether the cause was a deadline, client disconnect, or `take()`; counting only timeouts may hide whether upstream cleanup succeeded. Record separately which layer timed out, the cancellation reason when known, the dependency/route, and the cleanup/connection-release outcome.

Never use raw tokens or user identifiers as high-cardinality metric labels.

## 25. Common Pitfalls

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Assuming timeout rolls back remote work. | Side effects may already be committed. | Idempotency, status queries, compensation. |
| Testing only `TimeoutException`. | Unknown whether upstream was cancelled. | Assert cancellation with `TestPublisher`. |
| Using real wall-clock time for all timeout tests. | Slow and flaky. | `StepVerifier` virtual time. |
| Creating the publisher before `withVirtualTime`. | Operator may capture real scheduler. | Create publisher inside the supplier. |
| Treating `verify(Duration)` as a production timeout. | Runtime pipeline can still wait indefinitely. | Add timeout operators/transport config. |
| Using `Thread.sleep` in tests. | Slow, flaky, blocking. | Virtual time and publisher probes. |
| Calling `block()` on the event loop. | Starves many requests. | Keep the pipeline reactive. |
| Calling `subscribe()` in services. | Detached work, lost cancellation/error propagation. | Return the publisher to the caller. |
| Using JDBC directly in a reactive chain. | Blocks event loop. | Reactive driver or `boundedElastic` bridge. |
| Running blocking I/O on parallel scheduler. | Starves CPU workers. | `boundedElastic`/dedicated executor. |
| Treating cancellation as `onError`. | Wrong cleanup/metrics. | `doOnCancel`/`doFinally(CANCEL)`. |
| Assuming cancellation stops database queries. | Driver may keep executing. | Verify actual driver cancellation behavior. |
| Falling back on introspection timeout to an active principal. | Fail-open authentication. | Fail closed. |
| Retrying every timeout. | Duplicate side effects and higher latency. | Retry transient/idempotent calls with a budget. |
| Setting a short total timeout on SSE/WebSockets. | Valid streams get severed. | Dedicated idle timeouts and session policies. |
| Broadly allowlisting in BlockHound. | Hides blocking in the app. | Narrow allowlist with documented justification. |

## 26. Recommended Testing Workflow

1. **Test publishers at the service layer:** use `StepVerifier` to verify success, error, timeout, and cancellation.
2. **Use virtual time:** test delays, timeouts, and retry/backoff without waiting on a real clock.
3. **Assert upstream cancellation:** `TestPublisher` and `assertCancelled()`.
4. **Verify fallback branches:** `PublisherProbe` confirms fallback subscription.
5. **Install BlockHound:** exercise reactive services and catch blocking on non-blocking threads.
6. **Test blocking bridges:** confirm JDBC/legacy calls run on `boundedElastic`/a bounded executor.
7. **Test WebFlux HTTP:** `WebTestClient` + Spring Security test support for 401/403/response contracts.
8. **Test authentication dependencies:** stub slow, failing, or inactive `ReactiveJwtDecoder`/`ReactiveOpaqueTokenIntrospector`.
9. **Test real transport:** live server/client to check disconnects, connection disposal, and stream cancellation.
10. **Test side effects:** verify idempotency/status when cancellation arrives after remote work starts.
11. **Verify telemetry:** distinguish timeout, cancel, dependency error, and blocking.
12. **Keep tests deterministic:** never rely on sleep, wall-clock timing, or uncontrolled thread ordering.

**Key takeaways:** `timeout` sets a bound and typically cancels upstream; `cancel` signals the subscriber no longer needs results; blocking holds a thread and can stall the event loop. Use **StepVerifier with virtual time** to test timeouts, **TestPublisher/PublisherProbe** to prove cancellation and fallback branches, **WebTestClient** to test the HTTP/Security chain, and **BlockHound** to detect blocking. Cancellation does not roll back side effects, `verify(Duration)` is not a production timeout, and JWT/opaque introspection timeouts must **fail closed**, never granting Authentication without verifying the token.

## References

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [Project Reactor — Scheduler and Threading Model](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Reactor Test — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).
- [Reactor Test — TestPublisher API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html).
- [Reactor Test — PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html).
- [BlockHound](https://github.com/reactor/BlockHound).
- [Spring Framework — WebFlux Testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html).
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html).
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html).
