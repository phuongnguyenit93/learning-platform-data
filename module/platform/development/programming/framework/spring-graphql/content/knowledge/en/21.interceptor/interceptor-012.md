# Blocking and Reactive Interceptors in Spring for GraphQL

Spring for GraphQL provides `WebGraphQlInterceptor` to intercept and augment processing around a GraphQL request at the web layer. This API has a reactive signature: the `intercept` method accepts `WebGraphQlRequest` and returns `Mono<WebGraphQlResponse>`. That signature stays the same whether the application runs on Spring MVC or Spring WebFlux.

What matters is the work performed by the interceptor. If an interceptor calls a blocking library such as JDBC, JPA, or a synchronous HTTP client, that call can hold up the executing thread. In WebFlux, this is especially dangerous if executed on an event-loop thread. For reactive work, chain publishers using `flatMap`, `map`, and Reactor operators instead of waiting for results with `.block()`.

## 1. Where Does WebGraphQlInterceptor Sit?

`WebGraphQlInterceptor` runs around the handling of a request entering GraphQL via a web transport. It is suitable for tasks scoped to the request/operation level, such as:

- Reading and validating metadata from the HTTP request.
- Putting principal, tenant, request ID, or locale into `GraphQLContext`.
- Logging, timing, and adding tracing.
- Checking request conditions before forwarding to the GraphQL engine.
- Observing or processing the response after GraphQL execution completes.

High-level flow:

~~~mermaid
flowchart TD
    A[HTTP or WebSocket request] --> B[WebGraphQlInterceptor 1]
    B --> C[WebGraphQlInterceptor 2]
    C --> D[WebGraphQlHandler]
    D --> E[GraphQL execution]
    E --> F[DataFetchers and controllers]
    F --> G[WebGraphQlResponse]
    G --> H[Interceptor response chain]
    H --> I[Transport response]
~~~

An interceptor can run logic before and after `chain.next(request)`. Each interceptor should call `chain.next` exactly once for a request it forwards. If the chain is not called, the request is not passed to subsequent interceptors or GraphQL execution.

## 2. The Interceptor Signature Is Always Reactive

The interface looks like:

~~~java
public interface WebGraphQlInterceptor {

    Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    );

    interface Chain {
        Mono<WebGraphQlResponse> next(WebGraphQlRequest request);
    }
}
~~~

Therefore, `WebGraphQlInterceptor` does not have two separate blocking and reactive interfaces. The same `Mono` contract is used across Spring for GraphQL's web integrations. The blocking vs. reactive difference lies in the work inside the interceptor and the transport's thread model.

Example of an interceptor that simply logs before and after GraphQL execution:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class GraphQlLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        log.debug("GraphQL request received: {}", request.getId());

        return chain.next(request)
                .doOnNext(response ->
                        log.debug("GraphQL request completed: {}", request.getId())
                );
    }
}
~~~

Short logging operations can usually run directly. If synchronously logging to a file, network, or remote system with significant latency, use an asynchronous appender or an appropriate reactive API to avoid turning the interceptor into a bottleneck.

## 3. Blocking vs. Reactive Depends on the Transport

Spring GraphQL can be integrated with Spring MVC or Spring WebFlux. Each stack has a different request-processing model:

| Environment | Thread Model | What to Watch Out For |
| --- | --- | --- |
| Spring MVC | Usually handles requests on servlet threads; can use async request processing | Blocking calls occupy the servlet thread while waiting |
| Spring WebFlux | Uses event-loop and reactive scheduling | Never run blocking calls on event-loop threads |
| `WebGraphQlInterceptor` | Always returns `Mono<WebGraphQlResponse>` | No separate blocking variant; must compose work per reactive contract |

`Mono` does not automatically turn a synchronous call into a non-blocking one. If you invoke a blocking service before constructing the publisher, the work has already run immediately on the current thread:

~~~java
// Don't: blockingCall() executes immediately when the expression is evaluated.
return Mono.just(blockingService.loadMetadata());
~~~

With Spring MVC, that call can hold the servlet thread. With WebFlux, if the current thread is an event loop, it can stall many other requests sharing that event loop.

## 4. Writing a Reactive Interceptor When Dependencies Are Also Reactive

If a dependency returns `Mono` or `Flux`, chain the publisher into the interceptor chain. Example of validating a token using a reactive client:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveAuthenticationInterceptor implements WebGraphQlInterceptor {

    private final ReactiveTokenService tokenService;

    public ReactiveAuthenticationInterceptor(ReactiveTokenService tokenService) {
        this.tokenService = tokenService;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String token = request.getHeaders().getFirst("Authorization");

        return tokenService.authenticate(token)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("Authentication is required")
                ))
                .flatMap(principal -> {
                    request.configureExecutionInput((input, builder) ->
                            builder.graphQLContext(context ->
                                    context.put("principal", principal)
                            ).build()
                    );
                    return chain.next(request);
                });
    }
}
~~~

`authenticate` is assumed here to return `Mono<Principal>`. `flatMap` waits for the authentication publisher to emit the principal before configuring the execution input and forwarding the request to GraphQL. There is no need to spawn a new thread when the token service already uses reactive I/O.

In a real system, authentication failures should be translated into responses conforming to security policy. Do not turn every network error or authentication system failure into a `null` result and let the request proceed anyway.

## 5. Calling Blocking Dependencies Inside an Interceptor

Sometimes an application cannot yet replace JDBC/JPA or a synchronous HTTP client with reactive APIs. In that case, wrap the blocking call with `Mono.fromCallable` and offload it to an appropriate scheduler.

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class BlockingAuthenticationInterceptor implements WebGraphQlInterceptor {

    private final BlockingTokenService tokenService;

    public BlockingAuthenticationInterceptor(BlockingTokenService tokenService) {
        this.tokenService = tokenService;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String token = request.getHeaders().getFirst("Authorization");

        return Mono.fromCallable(() -> tokenService.authenticate(token))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(principal -> {
                    request.configureExecutionInput((input, builder) ->
                            builder.graphQLContext(context ->
                                    context.put("principal", principal)
                            ).build()
                    );
                    return chain.next(request);
                });
    }
}
~~~

`Mono.fromCallable` defers calling `authenticate` until subscription. `subscribeOn(Schedulers.boundedElastic())` moves the blocking invocation onto a scheduler designed for I/O-bound waiting tasks. Once authentication finishes, `flatMap` continues the interceptor chain.

This is how a blocking dependency is integrated into a reactive pipeline. It does not make the dependency non-blocking; it isolates the waiting time on a worker thread to avoid blocking the event loop.

`boundedElastic` is a shared scheduler with thread/queue limits. For a dependency with its own concurrency limits, consider a dedicated scheduler or executor so blocking tasks in the interceptor do not compete uncontrollably with other blocking work. Never use `Schedulers.parallel()` for blocking I/O because that scheduler is intended for short CPU-bound computations.

## 6. Why Not Use Mono.just for Blocking Calls?

The following two styles behave differently:

~~~java
// Wrong: the blocking call runs before the Mono is even created.
Mono<Principal> unsafe = Mono.just(tokenService.authenticate(token));

// Better: the call executes upon subscription.
Mono<Principal> deferred = Mono.fromCallable(
        () -> tokenService.authenticate(token)
).subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.defer` also defers publisher creation, but by itself does not shift work onto another thread:

~~~java
// Only defers; the blocking call still runs on the subscribing thread.
Mono<Principal> stillBlocking = Mono.defer(() ->
        Mono.just(tokenService.authenticate(token))
);
~~~

When using `defer`, combine it with an appropriate scheduler:

~~~java
Mono<Principal> scheduled = Mono.fromCallable(
        () -> tokenService.authenticate(token)
).subscribeOn(Schedulers.boundedElastic());
~~~

## 7. subscribeOn vs. publishOn

Two operators that are frequently confused:

| Operator | Main Effect | When to Use |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Selects the scheduler for subscription and source emission | Offloading a blocking call inside `fromCallable` to a worker thread |
| `publishOn(scheduler)` | Switches downstream operators to the specified scheduler | Moving a subsequent processing step to another scheduler |

For a blocking source, `subscribeOn` is usually the direct choice:

~~~java
Mono.fromCallable(() -> repository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Placing `publishOn` after the source cannot prevent the initial blocking call from running on the subscribing thread. The following example can still block before switching schedulers:

~~~java
// Unsuitable for offloading repository.load(...).
Mono.fromCallable(() -> repository.load(id))
        .publishOn(Schedulers.boundedElastic());
~~~

## 8. Do Not Call block, blockFirst, or blockLast in Interceptors

Do not wait on reactive publishers using blocking calls inside an interceptor:

~~~java
// Never do this inside WebGraphQlInterceptor.
Principal principal = tokenService.authenticate(token).block();
return chain.next(request);
~~~

`block()` turns a reactive flow into synchronous waiting. In WebFlux, if called on an event loop, that thread is held until the publisher completes. Even in Spring MVC, blocking ties up a servlet thread and reduces concurrent request throughput.

Chain publishers using `flatMap`:

~~~java
return tokenService.authenticate(token)
        .flatMap(principal -> {
            putPrincipalInContext(request, principal);
            return chain.next(request);
        });
~~~

Do not use `.toFuture().get()`, `.join()`, `CountDownLatch.await()`, or `Thread.sleep()` to wait for results inside a reactive interceptor.

## 9. Combining Pre- and Post-GraphQL Execution Processing

An interceptor can add context before calling the chain and observe the response when the chain completes:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain
) {
    request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                    context.put("requestId", request.getId())
            ).build()
    );

    long startedAt = System.nanoTime();

    return chain.next(request)
            .doOnNext(response -> {
                long elapsedNanos = System.nanoTime() - startedAt;
                recordGraphQlDuration(elapsedNanos, response.getErrors().size());
            });
}
~~~

`doOnNext` is for short, synchronous side effects such as updating metrics. If a post-processing step needs to call another reactive service and wait for its result, use `flatMap` instead of `doOnNext`:

~~~java
return chain.next(request)
        .flatMap(response -> auditService.record(response)
                .thenReturn(response));
~~~

The snippet above assumes `auditService.record` returns `Mono<Void>`. If auditing is not a prerequisite for returning the response, you can design a separate asynchronous recording flow; ensure audit failures do not accidentally break the GraphQL response if application policy permits ignoring them.

## 10. Error Handling in Reactive Interceptors

Errors can originate from multiple sources:

- Authentication or authorization dependencies.
- Tenant or metadata lookup services.
- Context configuration logic.
- GraphQL execution inside `chain.next`.

GraphQL execution errors are normally represented inside `WebGraphQlResponse` as a list of GraphQL errors. Errors occurring in the interceptor pipeline before or after execution can terminate the publisher with an error signal.

Do not use `onErrorResume(error -> Mono.empty())` to swallow all errors. Doing so can leave the caller with a completed stream without a valid response. Categorize errors and preserve semantics:

~~~java
return tokenService.authenticate(token)
        .flatMap(principal -> {
            putPrincipalInContext(request, principal);
            return chain.next(request);
        })
        .doOnError(error -> log.warn(
                "GraphQL request failed before or during execution: {}",
                request.getId(), error
        ));
~~~

If authentication errors need to map to specific HTTP status codes, consider handling them in Spring Security or the appropriate transport layer. Never let an interceptor turn an error into a fake success response.

## 11. Ordering Multiple Interceptors

An application may register multiple `WebGraphQlInterceptor` instances, for example:

1. Correlation/request ID.
2. Authentication and principal resolution.
3. Tenant resolution.
4. Metrics/tracing.
5. GraphQL execution.

Order matters when a later interceptor needs data placed into the context by an earlier interceptor. You can use `@Order` on beans or configure interceptor order on `WebGraphQlHandler` depending on how the application registers them.

~~~java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdInterceptor implements WebGraphQlInterceptor {
    // Add requestId to GraphQLContext before the next interceptor.
}
~~~

Do not rely on unspecified component scan order. Declare explicit ordering whenever interceptors have data dependencies. Also avoid registering the same interceptor via both component scanning and manual configuration.

## 12. Distinguishing WebGraphQlInterceptor from Servlet Filters and HandlerInterceptor

The word "interceptor" can be confusing because Spring MVC also has `HandlerInterceptor`, Servlets have `Filter`, and WebFlux has `WebFilter`.

| Mechanism | Scope | When to Use |
| --- | --- | --- |
| `WebGraphQlInterceptor` | GraphQL web request and execution lifecycle | Adding GraphQLContext, processing GraphQL requests/responses, applying shared logic to GraphQL transports |
| Servlet `Filter` | HTTP servlet request/response | CORS, security filter chain, HTTP processing before entering Spring MVC |
| Spring MVC `HandlerInterceptor` | Spring MVC handler | Logic tied to MVC handlers and servlet requests |
| WebFlux `WebFilter` | Reactive web exchange | Low-level web logic before/after the WebFlux handler |

`Filter`, `HandlerInterceptor`, and `WebFilter` do not automatically provide GraphQL-specific context. If you need to put metadata into `GraphQLContext`, you can bridge at the web layer or use `WebGraphQlInterceptor` directly. For logic applying solely to GraphQL, `WebGraphQlInterceptor` usually expresses the scope more accurately.

## 13. Testing Reactive Interceptors

You can test with Reactor's `StepVerifier` at the unit level or `WebGraphQlTester` at the integration level. Example of verifying a request ID is added to the context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

class RequestIdInterceptorTests {

    private final WebGraphQlHandler handler = createTestHandler();

    @Test
    void putsRequestIdIntoGraphQlContext() {
        WebGraphQlTester tester = WebGraphQlTester.builder(handler)
                .headers(headers -> headers.set("X-Request-Id", "req-123"))
                .build();

        tester.document("{ requestId }")
                .execute()
                .path("requestId")
                .entity(String.class)
                .isEqualTo("req-123");
    }
}
~~~

`createTestHandler()` represents a test setup containing the required `GraphQlSource`, controllers, and interceptors. In application integration tests, you can inject `WebGraphQlHandler` from the application context instead of creating it manually.

To test that a blocking call was offloaded, use a mock service that captures `Thread.currentThread()` when invoked. The test verifies that the call ran on a scheduler worker rather than an event-loop thread. Do not assert exact internal thread names of `boundedElastic` if the test would depend on implementation details; use a controlled `ThreadFactory` or custom named scheduler instead.

Scenarios that should be covered:

1. Reactive dependencies complete and GraphQL execution starts only after successful validation/authentication.
2. Blocking dependencies are invoked inside `fromCallable` on an appropriate scheduler.
3. Errors from dependencies are not swallowed and are handled per policy.
4. Interceptor response hooks run after `chain.next` completes.
5. Multiple interceptors execute in configured order.
6. Cancelled requests leave no orphaned background tasks or unreleased resources.

Note: cancelling a subscription does not guarantee every in-flight blocking call stops immediately. Configure timeouts on clients/databases, release resources properly, and check interruption behavior of dependencies.

## 14. Common Pitfalls and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| WebFlux hangs or throughput drops | Calling a blocking dependency on an event-loop thread | Use a reactive client or `Mono.fromCallable(...).subscribeOn(boundedElastic())` |
| `Mono` is returned yet request still blocks | Blocking call executed before creating the `Mono` | Do not use `Mono.just(blockingCall())`; use `fromCallable` |
| Interceptor calls chain without waiting for result | Using `doOnNext` to invoke a downstream publisher | Use `flatMap` and return the chained publisher |
| Request enters GraphQL twice | Calling `chain.next(request)` multiple times | Call the chain exactly once per request |
| Metadata missing in resolver | Configuring context after calling the chain or mismatched key | Write context before `chain.next` and standardize keys |
| Errors disappear | Using `onErrorResume` returning `Mono.empty()` | Preserve the error signal or convert to an intentional error response |
| MVC servlet thread held too long | Performing long blocking I/O directly inside interceptor | Use async/reactive dependencies or offload blocking work |
| ThreadLocal has no data in resolver | Execution switched threads or ran asynchronously | Pass metadata via GraphQLContext or proper context propagation |
| Audit breaks response | Reactive post-processing chained as mandatory but audit service fails | Decide whether audit is required to return a response; handle errors per clear policy |

## 15. Workflow for Choosing How to Write an Interceptor

When implementing an interceptor in Spring for GraphQL:

1. Determine whether the logic belongs to GraphQL requests or general HTTP transport.
2. If the logic needs GraphQLContext or GraphQL responses, use `WebGraphQlInterceptor`.
3. If dependencies return `Mono`/`Flux`, chain directly with `flatMap`, `map`, and reactive operators.
4. If dependencies are blocking, prefer replacing them with reactive clients; if not yet possible, wrap with `Mono.fromCallable` and offload via `Schedulers.boundedElastic()` or an appropriate executor.
5. Never call `.block()`, `.join()`, or wait synchronously on the reactive pipeline.
6. Put metadata into `GraphQLContext` before calling `chain.next(request)`.
7. Use `flatMap` for asynchronous post-processing; use `doOnNext` for short side effects.
8. Define interceptor ordering and call the chain exactly once.
9. Test reactive completion, blocking offload, errors, cancellation, and context propagation.

`WebGraphQlInterceptor` has a reactive contract in both Spring MVC and WebFlux. Applications should choose execution strategies matching their dependencies and transport thread model: stay reactive end-to-end when possible, or isolate blocking work on a dedicated scheduler when synchronous libraries must be used.

## References

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — WebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlInterceptor.html)
- [Spring for GraphQL — WebGraphQlHandler API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlHandler.html)
- [Project Reactor — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html)
- [Project Reactor — Blocking call and boundedElastic](https://projectreactor.io/docs/core/release/faq.html#faq.wrap-blocking)
