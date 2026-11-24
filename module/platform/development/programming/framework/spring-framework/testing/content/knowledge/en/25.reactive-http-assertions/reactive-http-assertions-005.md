# returnResult to Access ExchangeResult

**Context:** Spring Framework Testing → Reactive HTTP Assertions.

When testing HTTP with **WebTestClient**, methods such as **expectStatus()**, **expectHeader()**, and **expectBody()** verify the response right inside a fluent chain. However, there are situations where you need to keep the full result to read multiple properties, pass data to a subsequent verification step, use AssertJ, or test a reactive stream.

The **returnResult(...)** method ends the expectation declaration and returns a result object. Depending on how the body is read, the result can be:

- **EntityExchangeResult<T>:** holds the response body decoded into a Java value, along with HTTP exchange metadata.
- **FluxExchangeResult<T>:** holds the response body as a Flux to inspect each element of the stream, suitable for streaming data.
- **ExchangeResult:** the base class providing request and response information such as URL, method, headers, status, cookies, and captured body data.

Understanding these result types helps you choose the right way to read the body, inspect metadata without sending the request a second time, and properly handle endpoints that stream data continuously.

## 1. Role of returnResult in WebTestClient

WebTestClient sends a request through a test client and exposes the response for verification. The client can be bound to a controller, application context, router function, or a real server. Regardless of the binding style, HTTP verification can still use the same expectation APIs.

Basic execution flow:

~~~text
WebTestClient request
        |
        v
exchange()
        |
        v
HTTP response / ExchangeResult
        |
        +--> expectStatus()
        |
        +--> expectHeader()
        |
        +--> expectBody(...)
        |       |
        |       +--> consumeWith(...)
        |       +--> returnResult() -> EntityExchangeResult<T>
        |
        +--> returnResult(Type) -> FluxExchangeResult<T>
~~~

**returnResult** lets you exit the expectation chain and retrieve the result for inspection in ordinary Java code. It is especially useful when you need to:

- Read multiple response headers or cookies.
- Extract the body into a DTO, list, or byte array.
- Pass the body to AssertJ assertions.
- Use **assertWithDiagnostics** to include request/response details when an assertion fails.
- Read a reactive stream and verify its elements with **StepVerifier**.
- Write helpers returning a specific result type for multiple tests.

Not every request needs returnResult. If you only need to verify status, content type, and a few JSON fields, direct expectations are usually shorter and easier to read.

## 2. ExchangeResult types

### 2.1. ExchangeResult

**ExchangeResult** is the base class representing information about an HTTP exchange. It stores request and response details observed by WebTestClient.

Commonly used methods:

| Method | Information |
|---|---|
| getUrl() | Request URI |
| getMethod() | HTTP method |
| getRequestHeaders() | Request headers |
| getResponseHeaders() | Response headers |
| getStatus() | HTTP status |
| getResponseCookies() | Cookies in the response |
| getRequestBodyContent() | Request body bytes if capturable |
| getResponseBodyContent() | Response body bytes if capturable |
| getLogPrefix() | Prefix used for logging |
| assertWithDiagnostics(...) | Runs assertions and attaches exchange details on failure |

ExchangeResult focuses on data at the HTTP boundary. It is not an object containing full internal server state. For instance, it does not replace ServerWebExchange, does not directly expose the bean/controller that handled the request, and does not automatically surface all internal application exceptions.

### 2.2. EntityExchangeResult<T>

**EntityExchangeResult<T>** extends ExchangeResult and adds the response body decoded into a Java value of type T.

Example:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .returnResult();

OrderResponse order = result.getResponseBody();
~~~

Here, OrderResponse.class specifies the type WebTestClient uses to read the body. If the JSON cannot be decoded into that type, an error occurs during body reading and the test fails before producing a complete entity result.

**getResponseBody()** returns the decoded object. You can use it with AssertJ, pass it to helpers, or inspect multiple properties without manually parsing JSON.

### 2.3. FluxExchangeResult<T>

**FluxExchangeResult<T>** also extends ExchangeResult, but the response body is exposed as a **Flux<T>**.

Example:

~~~java
FluxExchangeResult<OrderEvent> result = webTestClient.get()
        .uri("/orders/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(OrderEvent.class);

Flux<OrderEvent> events = result.getResponseBody();
~~~

This result type suits endpoints returning reactive or streaming data. Tests can use StepVerifier to check elements, order, count, errors, or stream completion.

Do not collect an unbounded stream into a List just to run simple assertions. For SSE or long-lived streams, verify the needed elements and intentionally cancel the subscription.

### 2.4. Which result type to choose?

| Need | Usage | Result type |
|---|---|---|
| Read a JSON object into a DTO | expectBody(OrderResponse.class).returnResult() | EntityExchangeResult<OrderResponse> |
| Read a finite JSON array into a List | expectBodyList(OrderResponse.class).returnResult() | EntityExchangeResult<List<OrderResponse>> |
| Read raw body as bytes | expectBody().returnResult() | EntityExchangeResult<byte[]> |
| Verify a reactive stream | returnResult(OrderEvent.class) | FluxExchangeResult<OrderEvent> |
| Verify Server-Sent Events | returnResult(ParameterizedTypeReference<ServerSentEvent<T>>) | FluxExchangeResult<ServerSentEvent<T>> |

The main rule is to distinguish a body already aggregated and decoded into a value from a body still supplied as a publisher. Endpoints returning a single JSON object usually fit EntityExchangeResult. Streaming endpoints usually fit FluxExchangeResult.

## 3. Getting EntityExchangeResult for a response DTO

### 3.1. Reading a JSON object

Suppose an endpoint returns:

~~~java
record OrderResponse(long id, String status) {}
~~~

The test can retrieve the result:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .returnResult();
~~~

Then verify the body and metadata:

~~~java
assertThat(result.getResponseBody())
        .isEqualTo(new OrderResponse(42L, "PAID"));

assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
assertThat(result.getResponseHeaders().getContentType())
        .isCompatibleWith(MediaType.APPLICATION_JSON);
~~~

The benefit is that the request is sent only once. The test gets both the decoded body and response metadata from the same result.

### 3.2. Reading JSON with a generic type

When the response has a generic type, such as an envelope wrapping data, provide the full type using **ParameterizedTypeReference** to avoid losing type information from type erasure.

~~~java
record ApiEnvelope<T>(T data, String requestId) {}

EntityExchangeResult<ApiEnvelope<OrderResponse>> result =
        webTestClient.get()
                .uri("/orders/42/envelope")
                .exchange()
                .expectStatus().isOk()
                .expectBody(
                        new ParameterizedTypeReference<
                                ApiEnvelope<OrderResponse>>() {})
                .returnResult();

ApiEnvelope<OrderResponse> envelope = result.getResponseBody();

assertThat(envelope.data().id()).isEqualTo(42L);
assertThat(envelope.requestId()).isNotBlank();
~~~

If you only pass ApiEnvelope.class, the type parameter T may not be preserved during deserialization. Use ParameterizedTypeReference when the response type has nested generics like ApiEnvelope<OrderResponse>, Map<String, List<OrderResponse>>, or similar structures.

### 3.3. Reading a finite list

For a JSON array, you can use **expectBodyList**:

~~~java
EntityExchangeResult<List<OrderResponse>> result =
        webTestClient.get()
                .uri("/orders")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(OrderResponse.class)
                .returnResult();

List<OrderResponse> orders = result.getResponseBody();

assertThat(orders)
        .extracting(OrderResponse::id)
        .containsExactly(41L, 42L, 43L);
~~~

The body is read into a List when the response completes. This approach works for endpoints returning finite collections. If the endpoint returns an unbounded Flux or continuous stream, waiting for the body to become a List may cause the test to hang.

### 3.4. Reading the raw body

If you need to inspect bytes, encoding, or a format without a DTO decoder, use untyped body reading:

~~~java
EntityExchangeResult<byte[]> result = webTestClient.get()
        .uri("/reports/export")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .returnResult();

byte[] bytes = result.getResponseBody();

assertThat(bytes).isNotEmpty();
assertThat(result.getResponseHeaders().getContentType())
        .isEqualTo(MediaType.APPLICATION_PDF);
~~~

You can convert bytes to a String when the body is genuinely text and the encoding is known:

~~~java
String body = new String(
        result.getResponseBody(),
        StandardCharsets.UTF_8
);
~~~

For binary files, do not convert to String for verification. Check byte content, content length, content type, checksum, or file structure using an appropriate library.

## 4. Accessing HTTP exchange metadata

An important reason to obtain ExchangeResult is to inspect multiple pieces of metadata without sending the request again.

### 4.1. Checking URL, method, and request headers

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .header("X-Request-Source", "integration-test")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

assertThat(result.getMethod()).isEqualTo(HttpMethod.GET);
assertThat(result.getUrl().getPath()).isEqualTo("/orders/42");
assertThat(result.getRequestHeaders().getFirst("X-Request-Source"))
        .isEqualTo("integration-test");
~~~

This information is useful when tests use a URI builder, base URL, default headers, or request variants. You can verify that the request was constructed with the expected method and headers.

### 4.2. Checking response headers

~~~java
HttpHeaders headers = result.getResponseHeaders();

assertThat(headers.getContentType())
        .isCompatibleWith(MediaType.APPLICATION_JSON);

assertThat(headers.getFirst(HttpHeaders.CACHE_CONTROL))
        .contains("no-store");
~~~

You can check headers such as:

- Content-Type and Content-Length.
- Cache-Control, ETag, and Last-Modified.
- Location for redirect responses.
- Correlation or request id headers.
- Security headers required by the API contract.

Do not assert that a header is always present if it only appears under a specific profile or server configuration. Tests should reflect the contract the endpoint actually guarantees.

### 4.3. Checking response cookies

ExchangeResult exposes response cookies as a MultiValueMap:

~~~java
MultiValueMap<String, ResponseCookie> cookies =
        result.getResponseCookies();

ResponseCookie sessionCookie = cookies.getFirst("SESSION");

assertThat(sessionCookie).isNotNull();
assertThat(sessionCookie.isHttpOnly()).isTrue();
assertThat(sessionCookie.isSecure()).isTrue();
~~~

This example is suitable when the application issues session or security cookies. In plain HTTP test environments, the Secure attribute may depend on HTTPS configuration or profile; configure the test to match the contract under verification.

Cookies may contain sensitive information. Do not print real cookie values into shared logs. When diagnosing, log only cookie names and safe attributes under inspection.

### 4.4. Distinguishing request body and response body content

ExchangeResult can provide raw request/response byte content when captured during that exchange:

~~~java
byte[] requestBytes = result.getRequestBodyContent();
byte[] responseBytes = result.getResponseBodyContent();
~~~

These methods are helpful for wire-level diagnostics or when inspecting raw bytes. If the body has already been decoded into a DTO, prefer EntityExchangeResult.getResponseBody() for business assertions. Do not re-parse bytes just to check a property already present in the DTO.

For streaming responses, do not assume the entire stream has been collected into a complete byte array. Use FluxExchangeResult and inspect the publisher as content is emitted incrementally.

## 5. Using assertWithDiagnostics when assertions fail

### 5.1. The issue when asserting after returnResult

After obtaining the result, you can write AssertJ assertions:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

assertThat(result.getResponseBody().status()).isEqualTo("PAID");
~~~

If the assertion fails, the message usually shows expected and actual values. However, looking only at the assertion may lack the request URI, method, status, or response headers needed to understand why the result was wrong.

### 5.2. Wrapping assertions with assertWithDiagnostics

**assertWithDiagnostics(...)** runs assertions and appends HTTP exchange details to the error message if an assertion throws AssertionError.

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

result.assertWithDiagnostics(() ->
        assertThat(result.getResponseBody())
                .isEqualTo(new OrderResponse(42L, "PAID"))
);
~~~

If the assertion fails, diagnostics can include the request and response associated with the ExchangeResult. This helps identify which request failed and what the actual response looked like.

Multiple related assertions can be grouped in a single Runnable:

~~~java
result.assertWithDiagnostics(() -> {
    assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
    assertThat(result.getResponseHeaders().getContentType())
            .isCompatibleWith(MediaType.APPLICATION_JSON);

    assertThat(result.getResponseBody().status())
            .isEqualTo("PAID");
});
~~~

Use one diagnostics block for assertions belonging to the same HTTP exchange. Do not put assertions from unrelated requests into the same block, because on failure it becomes hard to tell which request caused the error.

### 5.3. Combining with AssertJ and helpers

You can write a helper accepting ExchangeResult to reuse checks:

~~~java
void assertJsonResponseHeaders(ExchangeResult result) {
    result.assertWithDiagnostics(() -> {
        assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
        assertThat(result.getResponseHeaders().getContentType())
                .isCompatibleWith(MediaType.APPLICATION_JSON);
    });
}
~~~

Helpers should accept an already created result rather than sending requests internally. That way, the request executes only once and every assertion references the same response.

If you need to inspect a typed body, write a helper taking EntityExchangeResult<OrderResponse> instead of just ExchangeResult. The specific parameter type gives compiler support for accessing the body and avoids unnecessary casts.

## 6. returnResult for reactive streams

### 6.1. Why do streams need a different verification approach?

An endpoint may return a Flux instead of a single object or List. For example:

~~~java
@GetMapping(value = "/orders/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<OrderEvent> events() {
    return eventService.events();
}
~~~

A Flux can emit multiple elements over time and may never complete. If a test uses expectBodyList to collect all content, it waits for the stream to finish. With SSE or continuous event streams, that does not happen by design.

In this case, retrieve **FluxExchangeResult** to access the publisher and use **StepVerifier** to verify stream behavior.

### 6.2. Obtaining FluxExchangeResult

For a simple data type:

~~~java
FluxExchangeResult<OrderEvent> result = webTestClient.get()
        .uri("/orders/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(OrderEvent.class);
~~~

Then verify the stream:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                event.type().equals("ORDER_CREATED"))
        .expectNextMatches(event ->
                event.type().equals("ORDER_PAID"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

returnResult(OrderEvent.class) instructs WebTestClient to decode response items into OrderEvent and expose them through a Flux. StepVerifier subscribes to the Flux, verifies item order, and explicitly cancels after the expected events.

If the stream is finite, you can verify completion:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(3)
        .verifyComplete();
~~~

Only use verifyComplete() when the endpoint is expected to terminate. For long-lived streams, use thenCancel() after verifying the needed items.

### 6.3. Testing Server-Sent Events

If the endpoint returns SSE, the body can be decoded into ServerSentEvent<T>:

~~~java
FluxExchangeResult<ServerSentEvent<OrderEvent>> result =
        webTestClient.get()
                .uri("/orders/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                        new ParameterizedTypeReference<
                                ServerSentEvent<OrderEvent>>() {}
                );
~~~

Verify event name and data:

~~~java
StepVerifier.create(result.getResponseBody())
        .assertNext(event -> {
            assertThat(event.event()).isEqualTo("order-created");
            assertThat(event.data()).isNotNull();
            assertThat(event.data().orderId()).isEqualTo(42L);
        })
        .thenCancel()
        .verify();
~~~

Use ParameterizedTypeReference to retain the generic type of ServerSentEvent<OrderEvent>. Using raw ServerSentEvent.class alone may prevent the nested data type from being decoded as OrderEvent as intended.

### 6.4. Timeouts when verifying streams

A reactive test should have an appropriate timeout so it does not wait indefinitely when the server fails to emit data or the stream does not complete as expected.

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

The timeout should be large enough for CI environments yet short enough to catch hangs. Avoid setting timeouts so low that tests become flaky under high CI load.

For streams emitting events on a schedule, you can use StepVerifier's timing steps when emission timing is part of the contract. Avoid overly strict timing assertions if the scheduler or execution environment cannot guarantee that precision.

## 7. Distinguishing returnResult from consumeWith

WebTestClient provides both **consumeWith(...)** and **returnResult()** after the body reading step. Both allow inspecting the result, but fit different styles of test organization.

### 7.1. consumeWith

Example:

~~~java
webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .consumeWith(result -> {
            assertThat(result.getResponseBody().id()).isEqualTo(42L);
            assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
        });
~~~

**consumeWith** receives the result inside a callback. This fits when all assertions can execute right at the request call site and the result is not needed elsewhere.

### 7.2. returnResult

Example:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

assertOrderResponse(result);
~~~

**returnResult** returns the result outside a callback. This fits when:

- Multiple helpers must be called on the same result.
- Metadata needs to be inspected in several places.
- Integration with another assertion framework is needed.
- You want to return the result from a helper or factory.
- You need to pass ExchangeResult into a subsequent processing step.

Do not retrieve returnResult just to write a single simple assertion if a direct expectation already expresses it more clearly. Choose whichever approach keeps the test easiest to read.

## 8. Organizing helpers that return ExchangeResult

When multiple tests require the same request setup, you can create a helper returning a specific result type.

Example:

~~~java
EntityExchangeResult<OrderResponse> getOrder(long id) {
    return webTestClient.get()
            .uri("/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody(OrderResponse.class)
            .returnResult();
}
~~~

Test:

~~~java
@Test
void returnsPaidOrder() {
    EntityExchangeResult<OrderResponse> result = getOrder(42L);

    result.assertWithDiagnostics(() ->
            assertThat(result.getResponseBody().status())
                    .isEqualTo("PAID")
    );
}
~~~

The helper keeps shared request setup and expectations in one place. However, avoid putting too many business assertions into the helper if individual tests need to verify different things. The helper should establish baseline HTTP conditions, while tests retain scenario-specific expectations.

### 8.1. Returning generic types

If a helper needs to support multiple body types, it can accept Class<T>:

~~~java
<T> EntityExchangeResult<T> getEntity(
        String uri,
        Class<T> bodyType) {

    return webTestClient.get()
            .uri(uri)
            .exchange()
            .expectStatus().isOk()
            .expectBody(bodyType)
            .returnResult();
}
~~~

For complex generic types, create an overload accepting ParameterizedTypeReference<T>:

~~~java
<T> EntityExchangeResult<T> getEntity(
        String uri,
        ParameterizedTypeReference<T> bodyType) {

    return webTestClient.get()
            .uri(uri)
            .exchange()
            .expectStatus().isOk()
            .expectBody(bodyType)
            .returnResult();
}
~~~

Do not create a generic abstraction if only one or two tests use it. A helper with too many parameters or confusing overloads makes tests harder to read than direct request builders.

## 9. Limitations to understand when reading ExchangeResult

### 9.1. ExchangeResult is not MvcResult

MockMvc returns MvcResult with Servlet MVC details such as handler, ModelAndView, flash map, and resolved exception.

WebTestClient returns ExchangeResult from an HTTP client perspective: URL, method, headers, status, cookies, and body content. The two result types serve different test environments.

Therefore, do not look for equivalents to getHandler() or getModelAndView() on ExchangeResult. If you need to verify internal server behavior, use logs, instrumentation, tests at the appropriate layer, or application observability APIs.

### 9.2. Internal exceptions cannot be inferred solely from the HTTP response

If the server handles an exception via an exception handler and returns HTTP 404 or 500, ExchangeResult shows the response the client received. It does not necessarily expose the original exception thrown inside the server.

To investigate internal exceptions:

- Check server logs or test output.
- Inspect the error response contract.
- If using a mock application context, check exception handling configuration in the context.
- Write dedicated tests for the service or component throwing the exception if needed.

A 500 response does not by itself tell you whether the failure occurred in the controller, service, serialization, or infrastructure. ExchangeResult provides the HTTP trace, while server-side diagnosis requires corresponding observability sources.

### 9.3. A streaming body is not a completed object

With FluxExchangeResult, the body is a publisher. Obtaining the ExchangeResult does not mean all elements have been consumed or the stream has completed.

Tests must subscribe using StepVerifier or an appropriate reactive mechanism. Do not call block() indiscriminately in WebFlux tests when the goal is verifying publisher behavior; StepVerifier verifies reactive signals in sequence.

### 9.4. Do not send the request twice to retrieve metadata

A common design mistake is sending one request to verify status, then sending another request to fetch the body or headers. The two calls may receive different data due to state changes, timestamps, random IDs, or updated records.

Retrieve ExchangeResult from the very request already verified:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();
~~~

Then use the same result for all related assertions. This keeps all evidence tied to a single HTTP exchange.

## 10. Common mistakes when using returnResult

### Unable to decode the response body

Check:

- The response Content-Type.
- Does the decoder support the media type?
- Is the DTO type compatible with the actual JSON?
- Are generic types described with ParameterizedTypeReference?
- Does the codec or ObjectMapper have the necessary modules configured?

If an error happens during decoding, no complete typed EntityExchangeResult is produced for further assertions. Check the exception and captured response body content if available.

### Using expectBodyList for an unbounded stream

expectBodyList needs to read the body into a finite collection. With SSE or continuous streams, the test may wait forever or time out. Use returnResult(Type) to get FluxExchangeResult and verify the publisher with StepVerifier.

### Calling assertions after returnResult on the same ResponseSpec

returnResult is a terminal operation that ends the expectation chain and returns the result. Afterwards, continue verification using ExchangeResult APIs or the body object. Do not call expectStatus or expectHeader on an already terminated ResponseSpec.

### Body was already read yet the test tries to read from the same response again

The response body is typically consumed during decoding or stream subscription. Do not assume the same publisher can be re-read like an independent collection. If multiple assertions are needed, store the decoded object or use appropriate operators on the Flux; avoid subscribing multiple times to a one-shot source.

### Generic body decoded into a Map or unexpected type

When the response type has nested generics, use ParameterizedTypeReference. Raw Class cannot preserve full generic type parameters due to type erasure.

### Assertion fails without request/response context

Use assertWithDiagnostics for assertions run after returnResult. With direct expectations, WebTestClient usually reports the failing step; you can also use consumeWith callbacks or store ExchangeResult for extra context.

### Checking bytes of a streaming response as a complete body

Streaming responses are emitted item by item or event by event. Use FluxExchangeResult and StepVerifier to verify content by signal rather than assuming a full byte array is ready before the stream completes.

### Logging sensitive data

ExchangeResult can expose request headers, cookies, and body content. Do not write tokens, session cookies, personal details, or secret data into shared CI logs. Use dummy data and only log fields needed for diagnosis.

## 11. Comprehensive example: DTO, metadata, and stream

A test suite can verify an object response and a stream using two different result types.

### 11.1. DTO and metadata

~~~java
@Test
void capturesOrderResponseAndMetadata() {
    EntityExchangeResult<OrderResponse> result =
            webTestClient.get()
                    .uri("/orders/42")
                    .accept(MediaType.APPLICATION_JSON)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.APPLICATION_JSON)
                    .expectBody(OrderResponse.class)
                    .returnResult();

    result.assertWithDiagnostics(() -> {
        assertThat(result.getMethod()).isEqualTo(HttpMethod.GET);
        assertThat(result.getResponseBody().id()).isEqualTo(42L);
        assertThat(result.getResponseBody().status()).isEqualTo("PAID");
    });
}
~~~

Here, expectBody(OrderResponse.class).returnResult() creates **EntityExchangeResult<OrderResponse>**: the body is read and decoded into a DTO before the test inspects metadata and business properties.

### 11.2. Event stream

~~~java
@Test
void emitsOrderEvents() {
    FluxExchangeResult<OrderEvent> result =
            webTestClient.get()
                    .uri("/orders/events")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .exchange()
                    .expectStatus().isOk()
                    .returnResult(OrderEvent.class);

    StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                    event.type().equals("ORDER_CREATED"))
            .expectNextMatches(event ->
                    event.type().equals("ORDER_PAID"))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
}
~~~

This example illustrates the difference between retrieving a decoded entity and retrieving a publisher. The same returnResult method can produce different result types depending on where it is called: from BodySpec after expectBody to receive EntityExchangeResult, or from ResponseSpec with an element type to receive FluxExchangeResult.

## 12. Practical guidelines

1. Use returnResult when you need to keep the response to inspect multiple properties or pass it to helpers.
2. Use expectBody(Type).returnResult() for a single body decoded into a Java value.
3. Use expectBodyList(Type).returnResult() for finite collections.
4. Use expectBody().returnResult() when you need raw body bytes.
5. Use returnResult(Type) on ResponseSpec to receive FluxExchangeResult for reactive streams.
6. Use ParameterizedTypeReference for generic types and ServerSentEvent with generic data.
7. Use assertWithDiagnostics to attach request/response context when assertions on ExchangeResult fail.
8. Use StepVerifier for Flux and distinguish finite streams from long-lived streams.
9. Do not resend a request just to retrieve more metadata; keep one ExchangeResult for the same exchange.
10. Do not treat ExchangeResult like MvcResult or a way to access internal server state.
11. Do not collect unbounded streams into a List and do not repeatedly subscribe arbitrarily.
12. Keep diagnostic logging safe; avoid writing tokens, cookies, or sensitive data.

returnResult bridges the expectation chain to a strongly typed result object. EntityExchangeResult fits decoded bodies, FluxExchangeResult fits streaming publishers, and ExchangeResult provides general HTTP metadata. Choosing the right type for the response shape ensures tests verify both data and protocol while keeping the evidence needed to investigate when an assertion fails.

