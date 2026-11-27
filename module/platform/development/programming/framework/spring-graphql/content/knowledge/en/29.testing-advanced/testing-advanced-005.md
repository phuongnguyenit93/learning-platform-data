# Testing WebGraphQlInterceptor

## Objectives

After this lesson, you will be able to:

- Explain the position of `WebGraphQlInterceptor` in Spring for GraphQL's request pipeline.
- Distinguish between interceptor unit tests and integration tests through `WebGraphQlHandler`.
- Verify that an interceptor forwards `Chain.next(request)` and preserves the response.
- Test reading HTTP headers and propagating metadata into `GraphQLContext`.
- Verify that response headers are added properly.
- Use `WebGraphQlTester` to execute requests through the interceptor chain without starting an HTTP server.
- Use `WebTestClient` to test interceptors across real HTTP transport.
- Test errors, interceptor ordering, and invalid request cases.
- Control side effects, cancellation, and errors in the reactive pipeline.
- Write tests that ensure interceptors do not leak sensitive data.

## 1. Why test WebGraphQlInterceptor?

`WebGraphQlInterceptor` allows processing requests before and after GraphQL Java executes an operation. Interceptors are commonly used to read request metadata, populate `GraphQLContext`, record timing, add response headers, or normalize certain errors at the web GraphQL layer.

An interceptor can affect every Query, Mutation, and Subscription passing through the web GraphQL handler. If implemented incorrectly, it can drop request metadata, bypass GraphQL execution, unexpectedly alter responses, or break the reactive stream.

Interceptor tests should verify behavior at the right boundaries:

- Requests are forwarded to the next interceptor.
- Metadata is read and propagated into execution input properly.
- GraphQL responses are preserved intact when the interceptor only observes them.
- Response headers are added properly when required.
- Exceptions and cancellation propagate through the pipeline with the expected semantics.
- Sensitive data is neither logged nor returned to clients.

Do not merely assert that the interceptor method was called. Verify the observable effects on the request, execution context, and response.

## 2. Position of the interceptor in the request pipeline

Spring for GraphQL's HTTP and WebSocket transports invoke a chain of `WebGraphQlInterceptor` instances before passing the request to `ExecutionGraphQlService`.

~~~mermaid
flowchart TD
    A["HTTP or WebSocket request"] --> B["Web transport handler"]
    B --> C["First WebGraphQlInterceptor"]
    C --> D["Subsequent interceptors"]
    D --> E["ExecutionGraphQlService"]
    E --> F["GraphQL Java execution"]
    F --> G["WebGraphQlResponse"]
    G --> H["Interceptors process response"]
    H --> I["Transport sends response"]
~~~

An interceptor can perform work before calling `chain.next(request)`, after receiving the response from the chain, or both.

Example:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    // Process request before GraphQL execution.
    return chain.next(request)
            .doOnNext(response -> {
                // Inspect response after GraphQL execution.
            });
}
~~~

`chain.next(request)` passes the request to the next step. The result is a `Mono<WebGraphQlResponse>`, because a typical GraphQL request produces a single web GraphQL response.

A single interceptor can be tested in isolation using a mock chain. When you need to verify the full interceptor chain and GraphQL execution, use `WebGraphQlHandler` together with `WebGraphQlTester`.

## 3. The WebGraphQlInterceptor contract

The interface has one primary method:

~~~java
Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        WebGraphQlInterceptor.Chain chain);
~~~

Three key components:

| Component | Responsibility |
| --- | --- |
| `WebGraphQlRequest` | Exposes request ID, headers, URI, attributes, and execution input customization |
| `Chain` | Passes the request to the next interceptor or GraphQL execution |
| `WebGraphQlResponse` | Holds the GraphQL response, execution result, and response headers |

An interceptor typically returns the publisher from `chain.next(request)` or an alternative publisher when intentionally rejecting a request prior to execution.

Never call `subscribe()` inside an interceptor and return a different `Mono`. Manually subscribing detaches the work from the framework-managed lifecycle, making error and cancellation propagation unreliable.

Also avoid calling `block()` inside an interceptor. Keep all processing within the reactive pipeline.

## 4. Setting up test dependencies

In a Maven project, add `spring-graphql-test` in `test` scope:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot dependency management normally aligns compatible versions. If your project does not use Spring Boot's BOM, choose a `spring-graphql-test` version matching the Spring GraphQL runtime.

Common companion test dependencies:

- `spring-boot-starter-test` for JUnit Jupiter, Mockito, and AssertJ.
- `spring-graphql-test` for `WebGraphQlTester`.
- `spring-test` for `WebTestClient`.
- Reactor Test for `StepVerifier` when testing reactive publishers.

No HTTP server is needed for interceptor unit tests or tests executed directly through `WebGraphQlHandler`. Start a server only when verifying real HTTP transport integration.

## 5. Building a testable sample interceptor

The following example reads `X-Request-Id`, validates its format, generates a new ID if invalid, stores the ID in `GraphQLContext`, and returns it in a response header.

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;

import reactor.core.publisher.Mono;

class RequestIdInterceptor implements WebGraphQlInterceptor {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId = resolveRequestId(request.getHeaders());

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("requestId", requestId)
                ).build()
        );

        return chain.next(request)
                .doOnNext(response ->
                        response.getResponseHeaders()
                                .set("X-Request-Id", requestId)
                );
    }

    private String resolveRequestId(HttpHeaders headers) {
        String supplied = headers.getFirst("X-Request-Id");

        if (supplied != null && SAFE_ID.matcher(supplied).matches()) {
            return supplied;
        }

        return UUID.randomUUID().toString();
    }
}
~~~

This example illustrates three independently testable behaviors:

1. A valid incoming header is preserved as the request ID.
2. A missing or malformed header is replaced with a server-generated UUID.
3. The request ID is placed into `GraphQLContext` and returned in the response header.

A client-supplied request ID is correlation metadata only. Never treat it as an identity, authorization claim, or proof of authentication.

## 6. Unit testing with a mocked request and chain

Unit tests isolate the interceptor from the GraphQL schema, resolvers, and web server. Use Mockito to mock `WebGraphQlRequest`, `Chain`, and `WebGraphQlResponse`.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class RequestIdInterceptorTests {

    @Test
    void shouldForwardRequestAndAddResponseHeader() {
        RequestIdInterceptor interceptor = new RequestIdInterceptor();

        WebGraphQlRequest request = mock(WebGraphQlRequest.class);
        WebGraphQlInterceptor.Chain chain =
                mock(WebGraphQlInterceptor.Chain.class);
        WebGraphQlResponse response = mock(WebGraphQlResponse.class);

        HttpHeaders requestHeaders = new HttpHeaders();
        requestHeaders.set("X-Request-Id", "req-test-123");

        HttpHeaders responseHeaders = new HttpHeaders();

        when(request.getHeaders()).thenReturn(requestHeaders);
        when(response.getResponseHeaders()).thenReturn(responseHeaders);
        when(chain.next(request)).thenReturn(Mono.just(response));

        StepVerifier.create(interceptor.intercept(request, chain))
                .expectNext(response)
                .verifyComplete();

        verify(chain).next(request);
        assertThat(responseHeaders.getFirst("X-Request-Id"))
                .isEqualTo("req-test-123");
    }
}
~~~

This test verifies:

- The interceptor calls `chain.next(request)`.
- The publisher completes with the exact response returned by the chain.
- The `X-Request-Id` response header is set.

Because the mock chain returns `Mono.just(response)`, the test stays focused on interceptor behavior. It does not prove that real GraphQL execution receives the request ID; that requires the integration tests in the following sections.

## 7. Testing invalid request IDs

Client-supplied header values should not be accepted blindly. Values containing newlines or overly long strings can cause issues in logs or when echoed as response headers.

You can test the invalid header case:

~~~java
@Test
void shouldReplaceInvalidRequestId() {
    RequestIdInterceptor interceptor = new RequestIdInterceptor();

    WebGraphQlRequest request = mock(WebGraphQlRequest.class);
    WebGraphQlInterceptor.Chain chain =
            mock(WebGraphQlInterceptor.Chain.class);
    WebGraphQlResponse response = mock(WebGraphQlResponse.class);

    HttpHeaders requestHeaders = new HttpHeaders();
    requestHeaders.set("X-Request-Id", "invalid id with spaces");

    HttpHeaders responseHeaders = new HttpHeaders();

    when(request.getHeaders()).thenReturn(requestHeaders);
    when(response.getResponseHeaders()).thenReturn(responseHeaders);
    when(chain.next(request)).thenReturn(Mono.just(response));

    StepVerifier.create(interceptor.intercept(request, chain))
            .expectNext(response)
            .verifyComplete();

    String requestId = responseHeaders.getFirst("X-Request-Id");

    assertThat(requestId).isNotNull();
    assertThat(requestId).matches(
            "[0-9a-fA-F-]{36}"
    );
}
~~~

The assertion verifies that the interceptor generates a new UUID-formatted ID. Do not assert a fixed UUID value because it is randomly generated.

You should also add tests for a missing header and a header exceeding the length limit. The goal is to confirm that every code path produces a safe request ID before using it in logs or response headers.

## 8. Verifying the interceptor does not drop the response

For interceptors that only attach metadata, the response from `chain.next(request)` should remain intact. The test in section 6 uses `expectNext(response)` to confirm that the exact same response object is forwarded.

If an interceptor uses `map` to transform the response, explicitly test which parts are allowed to change:

- Is `data` preserved intact?
- Are `errors` preserved intact?
- Are `extensions` altered?
- Do response headers include the new header?
- Did it accidentally overwrite headers added by an earlier interceptor?

For example, when adding a single header, choose `set` or `add` according to the intended semantics. If multiple interceptors add headers that can hold multiple values, clarify whether to append or replace.

Avoid constructing a brand-new `WebGraphQlResponse` just to add a header when the API offers a method to update response headers directly. Minimal mutations reduce the risk of dropping execution results.

## 9. Testing propagation into GraphQLContext

Unit tests can verify that `configureExecutionInput` is invoked, but an integration test proves that a resolver actually reads the metadata.

A test resolver can return the request ID from the context:

~~~java
import graphql.GraphQLContext;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class RequestMetadataController {

    @QueryMapping
    String currentRequestId(GraphQLContext context) {
        return context.get("requestId");
    }
}
~~~

The interceptor places `requestId` into the GraphQL context before execution. When the resolver runs, that value can be read from `GraphQLContext`.

Never pass metadata through static fields or shared mutable variables. GraphQL requests can execute concurrently; context must remain scoped to its own execution so one request never sees another request's data.

## 10. Using WebGraphQlHandler to build an interceptor chain

`WebGraphQlHandler` bridges the interceptor chain and `ExecutionGraphQlService`. You can construct a handler in a test using the application's service:

~~~java
WebGraphQlHandler handler = WebGraphQlHandler.builder(executionGraphQlService)
        .interceptor(new RequestIdInterceptor())
        .build();
~~~

Then use `WebGraphQlTester` to send requests through the web GraphQL layer:

~~~java
WebGraphQlTester tester = WebGraphQlTester.create(handler);
~~~

This tests the interceptor chain without opening an HTTP server. It is well suited for verifying request headers, GraphQL context, response errors, and subscription execution at the server-side web layer.

In a Spring Boot application, `WebGraphQlHandler` is configured from the interceptor beans in the application context. Integration tests can inject the auto-configured handler to test the application's actual chain.

Do not use `ExecutionGraphQlServiceTester` if your primary goal is testing `WebGraphQlInterceptor`, because that tester invokes the execution service without going through the web interceptor chain.

## 11. Integration testing with WebGraphQlTester

The example below assumes the Spring application context has the schema, `RequestMetadataController`, and `RequestIdInterceptor` registered as beans.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

@SpringBootTest
class RequestIdInterceptorIntegrationTests {

    @Autowired
    WebGraphQlHandler handler;

    @Test
    void shouldPropagateRequestIdToGraphQlContext() {
        WebGraphQlTester tester = WebGraphQlTester.builder(handler)
                .headers(headers ->
                        headers.set("X-Request-Id", "req-test-123")
                )
                .build();

        tester.document("{ currentRequestId }")
                .execute()
                .path("currentRequestId")
                .entity(String.class)
                .isEqualTo("req-test-123");
    }
}
~~~

This test passes through `WebGraphQlHandler`, so the interceptor chain runs before the GraphQL resolver. The header is added to the tester's simulated request, the interceptor transfers it into context, and the resolver returns that value.

If the test fails, check in order:

1. Is the interceptor registered on the handler?
2. Is the header attached to the tester request?
3. Does `configureExecutionInput` set the right context key?
4. Does the resolver read the same `requestId` key?
5. Does the schema declare the `currentRequestId` field?

## 12. Registering interceptors in Spring Boot and testing the real chain

In Spring Boot, an interceptor can be registered as a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration
class GraphQlInterceptorConfiguration {

    @Bean
    WebGraphQlInterceptor requestIdInterceptor() {
        return new RequestIdInterceptor();
    }
}
~~~

Boot uses interceptor beans to configure the web GraphQL handler. When a test injects `WebGraphQlHandler`, it can verify that the interceptor is active in the application-configured chain.

If the application only needs to copy certain HTTP headers into `GraphQLContext`, Spring provides `HttpRequestHeaderInterceptor`. You can use this built-in interceptor instead of writing a custom implementation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Bean
HttpRequestHeaderInterceptor requestHeaderInterceptor() {
    return HttpRequestHeaderInterceptor.builder()
            .mapHeader("X-Correlation-Id")
            .build();
}
~~~

Tests for the built-in interceptor can likewise use `WebGraphQlTester` and a resolver reading the value from `GraphQLContext` or `@ContextValue`.

When an application has multiple interceptors, define ordering explicitly with Spring's ordering mechanism. Spring resolves interceptor beans via `ObjectProvider.orderedStream()`, so you can use `Ordered` or `@Order`. Test ordering whenever real dependencies exist between them—for instance, an authentication interceptor must run before an interceptor reading the principal.

Never rely on incidental component scan order. When order affects behavior, declare it explicitly and write a test verifying it.

## 13. Verifying response headers over HTTP transport

`WebGraphQlTester` runs through `WebGraphQlHandler` but does not replace the full HTTP transport. When you need to verify response headers actually sent to HTTP clients, use `WebTestClient` or `HttpGraphQlTester`.

Example header check:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;

webTestClient.post()
        .uri("/graphql")
        .header("X-Request-Id", "req-http-123")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "{ book(id: \"book-42\") { id title } }"
        ))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals("X-Request-Id", "req-http-123");
~~~

This test requires a running application or a `WebTestClient` bound to the web application context. The interceptor must be registered in the same application context used by the test.

Key distinction:

- `WebGraphQlTester` tests the web GraphQL interceptor chain without a transport server.
- `HttpGraphQlTester` tests GraphQL requests/responses over HTTP.
- `WebTestClient` directly verifies status codes, headers, cookies, content types, and HTTP transport details.

Choose the tester matching the boundary you want to verify; do not use one tester to infer behavior of another layer.

## 14. Testing errors from interceptors and GraphQL execution

An interceptor can inspect the response after execution and handle errors if required by the application. When testing, distinguish between:

- Exceptions thrown before `chain.next(request)` is called.
- Exceptions raised by a downstream interceptor.
- GraphQL errors embedded in `WebGraphQlResponse`.
- Reactive publishers emitting an error signal.

GraphQL errors do not necessarily cause `Mono<WebGraphQlResponse>` to emit an error signal. A transport-valid response can still contain `errors`. Tests should check both `response.getErrors()` and publisher signals.

Example checking a GraphQL error response with `WebGraphQlTester`:

~~~java
tester.document("""
        query {
            book(id: "missing-book") {
                id
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                error.getMessage().contains("Not found")
        )
        .verify();
~~~

If an interceptor transforms errors, test only the parts permitted to change and ensure error paths and public error codes still adhere to contract.

Never catch all exceptions and return an empty response. When transforming errors, retain server-side diagnostics and keep stack traces or internal details out of client responses.

## 15. Testing cancellation and reactive lifecycle

Interceptors should return the publisher created by the chain so the framework manages subscription and cancellation.

You can test error propagation or cancellation using mocked publishers in unit tests. Example with an error-emitting publisher:

~~~java
RuntimeException failure =
        new IllegalStateException("downstream unavailable");

when(chain.next(request)).thenReturn(Mono.error(failure));

StepVerifier.create(interceptor.intercept(request, chain))
        .expectErrorMatches(error -> error == failure)
        .verify();
~~~

This test confirms the interceptor does not accidentally swallow errors from the chain. If the interceptor uses `onErrorResume`, explicitly test the error-translation condition and the resulting response type.

For subscription operations, cancellation can happen when a client closes the operation or connection. Interceptors must not hold private resources without cleanup. If lifecycle tracking is needed, attach cleanup with operators like `doFinally` and test the `CANCEL` signal.

Do not rely solely on `doOnCancel` for complex resource management when a publisher must release resources across all terminal signals; ensure cleanup is safe on cancel, error, and completion.

## 16. Testing metadata and security

Interceptors frequently have access to headers and request metadata. This is an easy place to leak sensitive data accidentally if full requests are logged.

Security tests should verify:

- `Authorization`, cookies, session IDs, and tokens are never logged.
- Request IDs are length-bounded and stripped of control characters.
- Client-supplied headers are not trusted as authenticated principals or tenants.
- Context keys cannot overwrite critical security context entries.
- Response headers never contain tokens or internal secrets.
- Error responses never contain stack traces or unvetted exception messages.

When an interceptor needs user identity, obtain it from the Spring Security context using the mechanism appropriate to the servlet or reactive stack. Never trust `username`, `role`, or `tenantId` merely because they appear in arbitrary HTTP headers.

Security tests should test both malicious inputs and the resulting responses, rather than only verifying that a sanitize helper was called.

## 17. Testing multiple interceptors and execution order

When multiple interceptors are present, each can modify the request before calling the chain and inspect or modify the response after the chain returns.

For example, chain A then B executes in nested order:

~~~text
A before
  B before
    GraphQL execution
  B after
A after
~~~

This order matters whenever one interceptor attaches metadata consumed by a later interceptor.

You can use a recording interceptor to capture execution order into a test list:

~~~java
import java.util.List;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;

import reactor.core.publisher.Mono;

class RecordingInterceptor implements WebGraphQlInterceptor {

    private final String name;
    private final List<String> events;

    RecordingInterceptor(String name, List<String> events) {
        this.name = name;
        this.events = events;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        events.add(name + ":before");

        return chain.next(request)
                .doOnNext(response -> events.add(name + ":after"));
    }
}
~~~

In the test, register two interceptors in the expected order and assert the event list. Use a separate `List` per test to avoid shared state across parallel tests.

When tests depend on Spring bean ordering, configure `@Order` or `Ordered` explicitly. Never infer ordering from class names or file order.

## 18. Test matrix for WebGraphQlInterceptor

A practical test suite can be organized as follows:

| Category | Scenario | Expected outcome |
| --- | --- | --- |
| Chain | Valid request | `chain.next(request)` is invoked exactly once |
| Pass-through | Chain returns successful response | Interceptor returns the same response |
| Request metadata | Valid header | Context receives the expected request ID |
| Header validation | Missing or malformed header | Server generates a safe new ID |
| Response | Interceptor adds a header | Response contains the header per contract |
| GraphQL error | Resolver returns GraphQL errors | Errors are preserved or transformed per rules |
| Reactive error | Chain emits an error signal | Error propagates unless policy handles it |
| Cancellation | Subscriber cancels publisher | Cleanup runs properly |
| Ordering | Multiple interceptors | Before/after order matches configuration |
| Security | Header contains tokens or forged values | Arbitrary values are neither logged nor trusted |
| Integration | `WebGraphQlTester` runs through handler | Resolver receives context added by interceptor |
| HTTP | Request through live/mock endpoint | Response headers and status match contract |

Do not cram all cases into one oversized test. Each test should verify one primary behavior so failures point directly to the root cause.

## 19. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Interceptor does not run in test | Used `ExecutionGraphQlServiceTester` instead of web tester | Use `WebGraphQlTester` with `WebGraphQlHandler` |
| `chain.next` is never called | Interceptor returns a different publisher or exits early | Check pre-execution branch logic |
| `GraphQLContext` lacks request ID | Wrong execution input setup or mismatched context key | Check `configureExecutionInput` and resolver |
| Response header missing | Tested with a tester that does not observe HTTP headers | Use `WebTestClient` over HTTP transport |
| Test misses GraphQL errors | Only verified publisher completion | Assert `response.errors()` or use the tester errors API |
| Exceptions are lost | Interceptor catches errors without rethrowing or mapping cleanly | Check `onErrorResume` and error contract |
| Cancellation skips cleanup | Resources not tied to publisher lifecycle | Attach cleanup for cancel/error/complete |
| Unstable interceptor ordering | Ordering not declared | Use `@Order` or `Ordered` and test the chain |
| Request ID contains newlines | Trusted raw client header | Validate format and generate a new ID when invalid |
| Test context polluted with stale data | Used shared mutable list or state | Create fresh fixtures per test |
| Interceptor logs tokens | Logged all headers | Allowlist metadata and redact credentials |

## 20. Workflow for testing WebGraphQlInterceptor

When adding or modifying an interceptor, follow this sequence:

1. **Clarify responsibilities.** Document whether the interceptor modifies the request, execution input, or response.
2. **Write unit tests.** Mock `WebGraphQlRequest`, `Chain`, and `WebGraphQlResponse` to verify pass-through.
3. **Test metadata.** Verify valid headers, missing headers, and malformed headers.
4. **Test context propagation.** Use a resolver reading `GraphQLContext` to prove data reaches execution.
5. **Create web handler tests.** Use `WebGraphQlHandler` and `WebGraphQlTester` to run through the interceptor chain.
6. **Test errors.** Distinguish GraphQL errors from reactive error signals.
7. **Test lifecycle.** Verify cancellation and cleanup when managing private resources.
8. **Test ordering.** Verify ordering when multiple interceptors depend on one another.
9. **Test real HTTP.** Use `WebTestClient` or `HttpGraphQlTester` when status codes and response headers must be verified.
10. **Review security.** Confirm no tokens are logged, no arbitrary headers are trusted, and no internal exceptions leak.

## 21. Summary

`WebGraphQlInterceptor` sits between the web transport and `ExecutionGraphQlService`, enabling request processing before GraphQL execution and response handling afterward. Testing interceptors requires verifying `chain.next(request)`, request metadata, `GraphQLContext`, response headers, error propagation, and reactive lifecycle behavior.

Unit tests with a mocked chain verify local logic. `WebGraphQlTester` combined with `WebGraphQlHandler` tests the server-side interceptor chain without an HTTP server; `WebTestClient` or `HttpGraphQlTester` is suited when real HTTP transport verification is needed. Combining these testing levels catches bugs at the right boundaries and ensures interceptors never drop responses, metadata, or security controls.
