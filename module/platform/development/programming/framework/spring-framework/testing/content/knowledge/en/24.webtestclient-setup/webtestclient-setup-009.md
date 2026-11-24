# responseTimeout and Buffer Limits

WebTestClient is a tool for testing Spring WebFlux applications from an HTTP client's perspective. When testing slow endpoints, large responses, or streaming data, two settings must be understood separately: **response timeout** limits how long the client waits to receive a response per client configuration; **max in-memory size** limits how much data a codec is allowed to retain in memory when buffering or aggregating data is needed.

These two limits solve two different problems. Increasing the wait timeout will not allow reading a body that exceeds the buffer limit. Increasing the buffer limit will not make a slow endpoint respond faster. Proper configuration must be based on the characteristics of the endpoint and how the test consumes the response.

## 1. Where Does WebTestClient Operate During Testing?

WebTestClient provides an API very similar to WebClient but includes assertions for tests. It can invoke WebFlux handlers in a mock environment or send requests through an HTTP connector to a running server.

Common ways to create the client:

~~~java
// Bind directly to a controller.
WebTestClient controllerClient =
        WebTestClient.bindToController(new OrderController())
                .build();

// Bind to a WebFlux application context.
WebTestClient contextClient =
        WebTestClient.bindToApplicationContext(context)
                .build();

// Bind to a RouterFunction.
WebTestClient routerClient =
        WebTestClient.bindToRouterFunction(routerFunction)
                .build();

// Send requests over an HTTP connector to a real server.
WebTestClient serverClient =
        WebTestClient.bindToServer()
                .baseUrl("http://localhost:8080")
                .build();
~~~

The first binding modes fit in-process WebFlux tests without opening a network port. bindToServer() fits when you need to test HTTP communication over a connector and a running server, such as a Spring Boot integration test on a random port.

After creating a client from a controller, context, or router function, you can call configureClient() to configure the client side:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .configureClient()
        .baseUrl("/api")
        .build();
~~~

responseTimeout and client codecs belong to client configuration. When using bindToApplicationContext, the application also has its own server-side codec configuration. Distinguish these two sides when troubleshooting buffer errors.

## 2. What Is responseTimeout?

responseTimeout(Duration) configures how long the client waits for a response. On WebTestClient.Builder, the default response timeout is 5 seconds; you can set a different duration depending on test goals:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(10))
        .build();
~~~

In the example, the client allows a response wait time longer than 5 seconds. This is useful for endpoints performing long-running work whose completion time still has a known bound, such as report generation or integrated data queries.

For a client bound to a WebFlux application context:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ReportController(reportService))
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

This method configures the timeout on the test client side. It does not change timeouts of the database, HTTP clients used by services, schedulers, reverse proxies, or the server connector. If an internal dependency inside a service hangs, the dependency's timeout and the test client's timeout are separate layers of protection.

### 2.1. Timeout Is Not the Controller's Maximum Processing Time

Suppose an endpoint returns Mono<ReportResponse>:

~~~java
@GetMapping("/api/reports/{id}")
public Mono<ReportResponse> getReport(@PathVariable UUID id) {
    return reportService.generate(id);
}
~~~

The client can wait for a response for a finite period. If the response does not arrive in time, the test fails with a timeout. That does not prove the controller stopped executing or the service canceled its work. Subscription cancellation, request cancellation, and stopping downstream work depend on how the publisher, connector, and dependencies implement cancellation.

Do not treat test-side timeouts as production resource protection. If business logic needs time limits when calling databases or external services, configure timeouts on those dependencies or pipelines. If the server needs request processing time limits, configure policies at the server and relevant infrastructure layers.

### 2.2. Response Timeout vs. Body Consumption Timeout

Responses can be delivered in several forms:

- Small responses delivered completely in a short time.
- Large response bodies that take time to transmit and decode.
- Streaming responses emitted piece by piece over a long period.

responseTimeout is the wait limit for the response on the client connector side. It does not replace every time limit in a test. When a test actively consumes a Flux from a response, set a timeout for verifying the publisher, such as StepVerifier.verify(Duration). For timeouts on individual Reactor operators, you can use Mono.timeout(...) or Flux.timeout(...) if that is application behavior you want to test.

For long-lived streaming responses such as Server-Sent Events, a stream may be designed to continue sending data over an extended period. Do not apply a short timeout like a normal JSON endpoint and conclude the stream is broken. Clarify whether the test needs to wait for the first event, wait for a number of events, or verify the stream stays active for a period; each goal has its own wait limit.

## 3. Choosing Response Timeout Based on Test Goals

| Endpoint Type | How to Set Wait Time |
|---|---|
| Standard CRUD API | Keep the default or set a short limit with enough headroom for CI |
| Integration query or report generation | Set a duration greater than the endpoint's expected SLA |
| Endpoint simulating slow processing | Intentionally set a small timeout to verify timeout failure |
| Server-Sent Events or long-lived streams | Do not use a short request timeout meant for ordinary requests; limit event inspection time with an appropriate mechanism |
| Tests needing a limit on total execution time | Combine the client timeout with test runner or StepVerifier limits |

Example creating a client dedicated to a report endpoint test group:

~~~java
static WebTestClient reportClient(WebApplicationContext context) {
    return WebTestClient
            .bindToApplicationContext(context)
            .configureClient()
            .responseTimeout(Duration.ofSeconds(15))
            .build();
}
~~~

Avoid increasing the global timeout to several minutes just because one test is occasionally slow. First identify which endpoint needs longer execution, inspect schedulers and dependencies, and then assign a dedicated timeout to the corresponding client or test group. Overly long timeouts delay detection of hanging bugs and slow down CI.

## 4. What Is a Codec's Buffer Limit?

WebFlux uses codecs to encode requests and decode responses. Some codecs must buffer data before creating a Java object, such as when reading a single JSON value, string, or byte array. To prevent a request or response from forcing the application to hold too much data in memory, Spring limits how much data a codec is allowed to buffer.

In Spring WebFlux, the default value of maxInMemorySize is 256 KB for default codecs. When a buffering operation exceeds this limit, a DataBufferLimitException may be thrown.

This limit does not simply mean "every HTTP body must be smaller than 256 KB." It applies to the codec's buffering operation. With streaming data decoded incrementally, codecs can process items piece by piece; however, a single large item or an aggregation operation requiring large buffering can still exceed the limit. How the test consumes the response also affects how much data is held in memory.

For example, the following assertions typically require WebTestClient to read and aggregate the body for inspection:

~~~java
client.get()
        .uri("/api/export")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.items").isArray();
~~~

Or:

~~~java
client.get()
        .uri("/api/export")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(ExportItem.class)
        .hasSize(1000);
~~~

Operations that collect the body or decode a large structure can require significant memory. If the data exceeds the codec limit, the test can fail even though the server returned status 200.

## 5. Configuring the Client-Side Buffer Limit

When a response body is larger than the default limit and the test genuinely needs to decode that body on the client side, configure WebTestClient's codecs:

~~~java
int maxBytes = 2 * 1024 * 1024;

WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(10))
        .codecs(configurer ->
                configurer.defaultCodecs().maxInMemorySize(maxBytes))
        .build();
~~~

The example sets the client codec buffer limit to 2 MB. For a client bound to an application context, you can configure it similarly after configureClient():

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(10))
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

This configuration affects the client-side codecs used to encode/decode requests and responses during tests. It does not automatically change the server's codec limits.

### 5.1. Server-Side Configuration Is a Separate Concern

If the WebFlux server needs to receive or process large payloads, configure ServerCodecConfigurer on the application side:

~~~java
@Configuration
public class WebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

With Spring Boot, the spring.codec.max-in-memory-size property can be used to configure the default codec limit in Boot's supported way:

~~~yaml
spring:
  codec:
    max-in-memory-size: 2MB
~~~

When testing with bindToApplicationContext, WebTestClient uses the server handler and codecs configured in that context. When testing with bindToServer, the server is a separate process or application; changing codecs on WebTestClient affects only the client, not the running server's configuration.

If a response fails while WebTestClient decodes it, check the client-side codec limit. If a request is rejected while the server reads the body, check the server-side codec limit. Do not blindly raise both limits automatically, as that hides which side actually caused the failure and can substantially increase allowed memory usage.

## 6. maxInMemorySize Is Not a General HTTP Size Limit

The following limits belong to different layers:

| Configuration/Limit | Scope |
|---|---|
| Codec maxInMemorySize | Amount of data buffered by the codec during encode/decode |
| Gateway or reverse proxy body limit | Request/response size permitted by infrastructure |
| Multipart limits | Number of parts, file size, or temporary file storage behavior |
| HTTP connector header limit | Size of headers and request line |
| Database/client limits | Size of queries, results, or dependency payloads |
| JVM heap limit | Total memory the process can use |

Increasing maxInMemorySize does not make a reverse proxy accept larger requests and does not increase the JVM heap. Conversely, a request body smaller than the proxy limit can still fail the codec if decoding requires buffering more than the codec limit.

In particular, do not use maxInMemorySize as a replacement for upload size policies. For large file uploads, consider multipart, streaming, temporary file storage, or object storage; avoid reading the entire file into a byte array unless necessary.

## 7. Handling DataBufferLimitException

DataBufferLimitException indicates that a buffering operation exceeded the configured limit. The error can occur while the server reads the request body or while WebTestClient decodes the response. Where it occurs determines which configuration to adjust.

Some clues:

- Stack trace involves client-side codecs, decoders, or WebTestClient body assertions: check the client-side limit.
- Stack trace involves server request decoders or a handler reading the body: check the server-side limit.
- Error appears only when calling expectBody() or collecting many elements into a collection: check whether the test is aggregating the entire response into memory.
- Error appears only with a single huge JSON field or element: inspect per-element size and payload structure.

Do not catch DataBufferLimitException and return a success response or ignore the rest of the body. Doing so means the test no longer verifies the data received by the client. Decide clearly whether the API permits large payloads; if so, configure an appropriate finite limit and test both within-limit and over-limit cases.

## 8. Testing Large Responses with WebTestClient

Suppose an endpoint returns a JSON document containing many items:

~~~java
@RestController
@RequestMapping("/api/exports")
class ExportController {

    @GetMapping
    Mono<ExportResponse> export() {
        return exportService.createExport();
    }
}
~~~

The test can configure a client-side codec larger than the default:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExportControllerTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(15))
                .codecs(configurer ->
                        configurer.defaultCodecs()
                                .maxInMemorySize(4 * 1024 * 1024))
                .build();
    }

    @Test
    void returnsLargeExport() {
        client.get()
                .uri("/api/exports")
                .exchange()
                .expectStatus().isOk()
                .expectBody(ExportResponse.class)
                .value(response ->
                        assertThat(response.items()).isNotEmpty());
    }
}
~~~

This example assumes the application already configured server codecs sufficiently to build and send the response. The 4 MB setting in WebTestClient adjusts only the client side. If the server also buffers large data, server-side configuration must be handled separately.

When responses are large, you do not always need to decode the entire payload into a single object just to check a few properties. You can design endpoints to return paginated or streamed data, and then assert a few elements and termination conditions.

## 9. Testing Streaming Data Without Buffering the Entire Body

WebFlux is well suited to data emitted incrementally. If a test's goal is to verify a stream, obtain the publisher from the result instead of using an assertion that forces buffering the whole body.

Example endpoint emitting progress updates:

~~~java
@GetMapping(value = "/api/progress",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ProgressEvent> progress() {
    return progressService.events();
}
~~~

The test can obtain a FluxExchangeResult and verify several items:

~~~java
FluxExchangeResult<ProgressEvent> result = client.get()
        .uri("/api/progress")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(ProgressEvent.class);

StepVerifier.create(result.getResponseBody())
        .assertNext(event ->
                assertThat(event.status()).isEqualTo("STARTED"))
        .assertNext(event ->
                assertThat(event.progress()).isGreaterThan(0))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

returnResult(...) lets the test continue verifying the response body as a publisher. StepVerifier registers a subscriber and asserts the emitted items. thenCancel() ends the subscription after receiving enough data to check; verify(Duration) bounds how long the test waits on the publisher.

For long-lived streams, avoid calling collectList() or converting the whole publisher into a collection just to check a few events. Doing so defeats the benefit of streaming and can consume large amounts of memory. If you need to verify stream completion, use verifyComplete() with an appropriate timeout; if the stream is not meant to end, verify a few items and cancel.

## 10. Distinguishing Timeouts Across Layers

In a WebFlux test, multiple timeouts may coexist:

| Timeout | Where Applied | Purpose |
|---|---|---|
| WebTestClient.responseTimeout(...) | Test client | Limits response wait time per client configuration |
| StepVerifier.verify(Duration) | Test subscriber | Limits publisher verification time |
| Mono.timeout(...) / Flux.timeout(...) | Reactor pipeline | Fails the pipeline with a timeout error if the publisher does not signal in time |
| block(Duration) | Blocking code | Limits how long a thread waits for a result |
| JUnit @Timeout | Entire test method | Limits test execution time |
| HTTP/database client timeout | Outbound dependencies | Limits wait time for dependencies |
| Server/gateway timeout | Infrastructure or server | Limits processing/connection time per deployment policy |

Do not set every timeout to the exact same number without understanding their relationship. For example, if the JUnit timeout is shorter than the response timeout, the test runner may abort the test before WebTestClient reports a timeout. If a dependency timeout is longer than the endpoint timeout, the client may stop waiting while server-side work keeps running.

Choose durations according to an ordered budget: dependencies should have suitable limits, pipelines can have business deadlines, the test client needs enough time to receive results, and the test runner needs a larger overall limit to catch hanging tests.

## 11. Testing Timeouts Reliably

Do not use Thread.sleep(...) to simulate a slow endpoint. Sleeping simply blocks the test thread for a fixed period, does not synchronize with reactive signals, and easily causes flakiness when CI is slow.

You can create a publisher with an intentional delay:

~~~java
@RestController
class DelayedController {

    @GetMapping("/api/delayed")
    Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(500))
                .thenReturn("done");
    }
}
~~~

For normal tests, set a timeout large enough for the response to complete:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new DelayedController())
        .configureClient()
        .responseTimeout(Duration.ofSeconds(2))
        .build();

client.get()
        .uri("/api/delayed")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("done");
~~~

To test timeouts at the HTTP connector layer, use a client connecting to a real server or test server with the corresponding connector and set a response timeout shorter than the expected response time. This verifies the connector timeout behavior used by the application; a client bound directly to a controller cannot replace all differences in a network connector.

When testing timeouts, avoid comparing execution times down to exact milliseconds. Schedulers, CPU load, and CI environments all affect timing. Tests should verify timeout or success outcomes with a sufficiently generous margin rather than relying on exact execution durations.

## 12. Configuring Buffer Limits Responsibly

When responses or requests are larger than the default, you can raise maxInMemorySize to an appropriate finite value:

~~~java
private static final int TEST_CODEC_LIMIT =
        4 * 1024 * 1024;

WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .configureClient()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(TEST_CODEC_LIMIT))
        .build();
~~~

Avoid defaulting to an unlimited buffer just to make tests pass. An unexpectedly huge response can indicate a bug in the endpoint, test data, or an unintended payload-generating loop. A finite limit helps tests catch unexpected size regressions.

If a codec supports configuring maxInMemorySize(-1) to remove the limit, use it only with a clear reason and when data size is already bounded at another layer. An unlimited setting can cause tests or the application to consume massive heap if bodies grow unexpectedly.

Pick the value based on the largest valid payload the API commits to supporting, plus a reasonable margin. For streaming endpoints, prefer incremental processing designs over raising buffers to hold the whole stream.

## 13. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Test fails with timeout after a few seconds | Response is slower than client limit | Determine expected response time and set an appropriate responseTimeout |
| Test times out while service keeps running | Client-side timeout does not necessarily stop server/dependency work | Check cancellation and dependency timeouts separately |
| DataBufferLimitException when reading large JSON | Codec needs to buffer more than the limit | Identify whether the error is client-side or server-side, raise the finite limit on the right side, or change how it is read |
| Small-response test passes, large-response test fails | Data size exceeds buffer limit or how the test aggregates it | Inspect payload, codecs, and use streaming where appropriate |
| Raising client codec limit still leaves requests rejected | The failing limit is in the server codec or infrastructure | Configure the server/proxy side properly |
| SSE test never finishes | The stream is designed to be long-lived | Use StepVerifier, check the needed number of events, and cancel |
| Test using collectList() consumes lots of memory | The entire stream is collected into a list | Verify item by item or by termination conditions |
| Raising timeouts slows down CI | Overly large timeouts mask hanging endpoints | Separate slow tests, set suitable deadlines, and inspect dependencies |

## 14. Workflow for Choosing Configuration in a Test

When writing a test with WebTestClient, determine step by step:

1. Does the test bind directly to a controller/context or send requests to a real server?
2. Does the endpoint return small responses, large responses, or long-lived streams?
3. How long does the test need to wait for a response according to SLA or processing characteristics?
4. Does the test aggregate the body into an object, list, string, or byte array?
5. Does a buffer error occur in the client-side codec or the server-side codec?
6. Can data be verified incrementally instead of buffering the entire body?
7. Do timeouts of the client, publisher, dependencies, and test runner align sensibly?
8. Is the buffer limit finite and justified by the data contract?

For example, an API returning small JSON only needs default timeout and default codec limits. An API generating large reports may need a longer timeout and a larger client codec limit, alongside matching server configuration. An SSE API should be verified using its publisher and StepVerifier rather than buffering the entire stream in memory.

responseTimeout helps tests detect responses that fail to arrive within the allowed time. maxInMemorySize helps codecs control how much data to buffer. Choosing the right configuration layer and body consumption pattern keeps WebFlux tests stable while catching latency and payload-size issues in the API.
