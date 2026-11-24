# Simulating Timeouts, Disconnects, and Transport-Layer Limits

## 1. Goals of HTTP Client Testing

An HTTP client does not merely need to send the right method, URL, headers, and body. In real environments, requests can also be slow, the server can stop responding, the connection can drop mid-flight, or the client can fail to acquire a connection from the connection pool.

These situations belong to different layers. Lumping all of them into one concept of "request failed" can cause tests to miss timeout misconfiguration, excessive retries, or mishandling of a response that had already started arriving.

An HTTP client test suite typically needs to verify:

- The client sends requests matching the contract: method, URI, headers, body, and content type.
- The client handles HTTP statuses such as 400, 404, 429, or 503 properly.
- The client reacts properly when no response arrives due to timeout or dropped connections.
- The client does not wait forever and enforces clear time limits.
- The client cancels requests and releases resources when the caller times out or cancels.
- Retries occur only according to the defined policy and do not create duplicate side effects.
- Transport-layer errors are translated into appropriate business errors for upstream services to handle.

It is important to distinguish an HTTP error response from a transport error. HTTP 503 is still a valid response: the server received the request and returned a status. A timeout or connection reset usually has no complete response for the client to inspect status or body.

## 2. Distinguishing Types of Timeouts

There is no single timeout covering every phase of a request. A request may pass through these steps:

~~~text
Acquire connection from pool
        |
        v
DNS lookup
        |
        v
TCP connect
        |
        v
TLS handshake (if HTTPS)
        |
        v
Send request
        |
        v
Wait for response headers
        |
        v
Read response body
        |
        v
Deserialize / process data
~~~

Common limits:

| Limit type | What it bounds | Example error or symptom |
|---|---|---|
| Connection pool acquire timeout | Time waiting for an available connection in the pool | Pool exhausted, requests queued waiting |
| DNS timeout | Time to resolve hostname | IP address cannot be resolved in time |
| Connect timeout | Time to establish TCP connection | Server does not respond to TCP handshake |
| TLS handshake timeout | Time to complete TLS negotiation | HTTPS connection hangs during handshake |
| Response/read timeout | Time waiting for data from the server after connecting | Server accepts request but responds too slowly |
| Overall request deadline | Total time for the entire operation | Request exceeds caller's time budget |

Exact names and implementations of each timeout depend on the HTTP connector. With Reactor Netty, **responseTimeout** bounds the interval between network reads; it does not equal the total duration of the entire publisher. You can use the **Mono.timeout(...)** or **Flux.timeout(...)** operator to set a deadline on the reactive stream.

With blocking clients, read timeout typically bounds how long to wait for data on the next read. It is not necessarily the total time from start to finishing the body either. A response trickling in steadily chunk by chunk can take longer than the read timeout value without violating the gap between two reads.

Define the requirement clearly: whether you want to bound connection establishment, wait time for the next byte, or the total duration business logic is willing to wait.

## 3. Choosing the Right Simulation Tool

Not every HTTP mocking tool can simulate transport errors.

| Tool | Suitable for testing | Real HTTP socket? |
|---|---|---|
| **MockRestServiceServer** | Request expectations, mock status/body/headers, and mocked request-factory-layer errors | No |
| **MockWebServer** | Real HTTP client calling local server; response delays, disconnects, partial response bodies | Yes |
| **WireMock** | HTTP stubs, delays, faults, mappings, and response scenarios | Yes |
| Service mock object | How higher-level services react to domain exceptions | No |
| Staging server/container | TLS, proxies, DNS, network policies, and deployment infrastructure characteristics | Yes, per that environment |

**MockRestServiceServer** is very useful when testing clients built with **RestClient** or **RestTemplate**. It checks requests and responses through Spring's mocking mechanism, keeping tests fast and free of network ports.

When you need to test connect timeouts, read timeouts, socket disconnects, or bodies cut off mid-stream, use a local server such as **MockWebServer** or **WireMock**. These tools let the HTTP client connect over real sockets and give control over how the server responds.

Do not use a mock service to conclude that an HTTP connector handled TCP resets properly. A mock service only simulates outcomes at the boundary where the test places it.

## 4. Verifying Request Contracts with MockRestServiceServer

With Spring Framework 6.1 and later, **MockRestServiceServer** can bind to **RestClient.Builder**. With **RestTemplate**, it can also bind directly to the instance under test.

Example verifying the request sent by `RestClient`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.GET;

class CatalogClientContractTest {

    @Test
    void shouldSendTheExpectedRequest() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo("https://catalog.example/items/42"))
                .andExpect(method(GET))
                .andRespond(withSuccess(
                        "{\"id\":42,\"name\":\"Keyboard\"}",
                        MediaType.APPLICATION_JSON
                ));

        String body = client.get()
                .uri("/items/42")
                .retrieve()
                .body(String.class);

        assertThat(body).contains("Keyboard");
        server.verify();
    }
}
~~~

This approach works well to verify that the client uses the right URI, method, headers, and response parsing. You can add expectations for request body, query parameters, or invocation counts.

`MockRestServiceServer` can also simulate some I/O errors via exception-throwing response creators. That is useful for verifying how the service translates errors, yet it does not produce a real TCP reset, measure socket connect/read timeouts, or exercise the connector's connection pool.

## 5. Preparing MockWebServer

MockWebServer belongs to the OkHttp library. Add the test dependency matching the OkHttp version managed by the project, then start the server on a random port.

~~~java
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class CatalogHttpClientTest {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws Exception {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws Exception {
        server.shutdown();
    }
}
~~~

Use the URL provided by the server instead of assigning a fixed port:

~~~java
String baseUrl = server.url("/").toString();
~~~

Each test can enqueue a different response:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":42,\"name\":\"Keyboard\"}"));
~~~

When the HTTP client sends a request, MockWebServer pops the next response from the queue and records the request so the test can verify method, path, headers, and body.

Shut down the server in **@AfterEach** or **try/finally** to avoid holding ports and threads after the test ends. Do not share a mutable response queue across tests running in parallel if they could consume each other's responses.

## 6. Simulating Read Timeout with RestClient or RestTemplate

With blocking clients, timeouts must be configured on the **ClientHttpRequestFactory** in use. The example below uses **SimpleClientHttpRequestFactory** with timeout values in milliseconds:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(300);
requestFactory.setReadTimeout(200);

RestClient client = RestClient.builder()
        .baseUrl(baseUrl)
        .requestFactory(requestFactory)
        .build();
~~~

The same request factory can be used with **RestTemplate**:

~~~java
RestTemplate restTemplate = new RestTemplate(requestFactory);
~~~

If the application uses Apache HttpComponents or the JDK HttpClient request factory, configure timeouts on the corresponding factory/connector. Do not assume a timeout configured on one factory automatically applies to another.

To simulate a slow-responding server, enqueue a response that delays headers:

~~~java
import java.util.concurrent.TimeUnit;

server.enqueue(new MockResponse()
        .setHeadersDelay(800, TimeUnit.MILLISECONDS)
        .setBody("{\"id\":42}"));
~~~

With a 200 ms read timeout, the blocking call should terminate with an I/O error instead of waiting the full 800 ms:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.web.client.ResourceAccessException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void shouldFailWhenResponseHeadersArriveTooLate() {
    server.enqueue(new MockResponse()
            .setHeadersDelay(800, TimeUnit.MILLISECONDS)
            .setBody("{\"id\":42}"));

    assertThatThrownBy(() ->
            client.get()
                    .uri("/items/42")
                    .retrieve()
                    .body(String.class)
    ).isInstanceOf(ResourceAccessException.class);
}
~~~

The example assumes **client** is configured with a read timeout shorter than the header delay. The connector may wrap the timeout error inside **ResourceAccessException** or another I/O exception depending on the request factory. If the test needs to verify the exact cause, check the root cause for the connector and version in use.

**setHeadersDelay(...)** controls the delay before the server sends response headers. **setBodyDelay(...)** can be used to delay the body after headers have already been sent. These two options distinguish timeouts while waiting for a response from timeouts while reading the body.

## 7. Simulating Timeouts with WebClient and Reactor Netty

WebClient commonly uses Reactor Netty as its HTTP connector. Connect timeout and response timeout can be set when creating **HttpClient**:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
        .responseTimeout(Duration.ofMillis(200));

WebClient webClient = WebClient.builder()
        .baseUrl(baseUrl)
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

**CONNECT_TIMEOUT_MILLIS** bounds the time to establish the TCP connection. **responseTimeout** configures the wait time for data between network-level reads. It is not an overall deadline for all steps of the request.

If business logic needs a maximum total wait time, apply a timeout on the publisher:

~~~java
Mono<String> result = webClient.get()
        .uri("/items/42")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(1));
~~~

When using both a connector timeout and a publisher timeout, tests should know which timeout is expected to fire. If the publisher deadline is shorter than the response timeout, the error may come from the Reactor operator before the connector timeout fires.

### Testing Response Timeout

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void shouldFailWhenServerDoesNotSendHeadersInTime() {
    server.enqueue(new MockResponse()
            .setHeadersDelay(800, TimeUnit.MILLISECONDS)
            .setBody("late"));

    StepVerifier.create(webClient.get()
                    .uri("/slow")
                    .retrieve()
                    .bodyToMono(String.class))
            .expectError()
            .verify(Duration.ofSeconds(2));
}
~~~

The test limits the `verify` duration so the test itself does not hang indefinitely if configuration is wrong. In real tests, you can wrap the call inside an application client method and assert the domain exception emitted by that method.

If the application maps connector errors into **CatalogUnavailableException**, test that exception at the service boundary. Do not force every test to depend on an internal Netty exception class if that detail is not a contract the application wants to expose.

### Testing Overall Deadline

Response timeout and overall deadline are two distinct behaviors. You can simulate a server sending the body slowly in chunks so the response timeout does not necessarily trigger, yet total time still exceeds the business deadline.

~~~java
Mono<String> operation = webClient.get()
        .uri("/slow-stream")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofMillis(500));
~~~

Tests for an overall deadline should verify that the publisher terminates within the allowed time and the operation is canceled. Do not use **Thread.sleep()** to guess when timeouts occur; use **StepVerifier.verify(Duration)** or Reactor's time-control tools when testing scheduler-based logic.

## 8. Simulating Server Disconnects

A server may close the socket after receiving a request but before sending a complete response. MockWebServer supports controlling socket behavior via **SocketPolicy**.

Example closing the connection right after receiving the request:

~~~java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.SocketPolicy;

server.enqueue(new MockResponse()
        .setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST));
~~~

WebClient receives neither a complete status nor body. The call typically terminates with a transport error; the exact exception class depends on the connector and when the socket closed.

~~~java
StepVerifier.create(webClient.get()
                .uri("/items/42")
                .retrieve()
                .bodyToMono(String.class))
        .expectError()
        .verify(Duration.ofSeconds(2));
~~~

With `RestClient` or `RestTemplate`, tests can verify that the I/O error is wrapped in a Spring exception such as **ResourceAccessException**. Importantly, do not treat this situation like an HTTP 500: the server never sent a complete HTTP response.

### Distinguishing Connection Refused from Connect Timeout

These two situations are not the same:

- **Connection refused:** the address is reachable, but no process is listening on the port, or the OS rejects the connection. Failure usually happens quickly.
- **Connect timeout:** the client sends a connection-establishment request and receives no TCP reply in time, such as when SYN packets are dropped by a firewall. The client waits until the connect timeout expires.

Shutting down MockWebServer and connecting to the closed port typically triggers connection refused, not a connect timeout. Verifying a real connect timeout requires a network environment that intentionally drops packets or a controlled proxy/network fault injector. Do not use a random public IP because outcomes depend on external networks and make tests flaky.

## 9. Simulating a Response Body Cut Off Mid-Stream

A server might send headers and part of the body and then close the connection. This differs from a server failing to answer at all.

MockWebServer has a policy to disconnect while sending the body:

~~~java
server.enqueue(new MockResponse()
        .setBody("partial response")
        .setSocketPolicy(SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));
~~~

The client may have already read part of the data before receiving the error. For JSON responses, the deserializer may report an incomplete body or parse error. For large streams, the application might already have processed some chunks before the connection dropped.

Tests should verify application-level behavior:

- The outcome is not treated as success if a complete body is required.
- Temporary resources or buffers are released.
- A half-populated domain object is not exposed if the application requires intact data.
- Retries run only when request semantics permit.
- If the application streams to a file, temporary files are deleted or marked incomplete.

A truncated-body error can happen after headers and initial bytes have reached the client. Therefore, the status may be 200 while reading the body still fails. Receiving status 200 must never be taken as proof that the entire response was read successfully.

## 10. Retries and the Risk of Executing an Operation Twice

When a request times out or loses connection, the client does not always know how far the server processed the request.

Example:

~~~text
Client sends POST /payments
          |
          v
Server receives request and creates payment
          |
          v
Server sends 201 response
          |
          X  Connection drops before client receives response
          |
          v
Client sees timeout, unsure whether payment was created
~~~

If the client automatically retries the POST, the server might create a second payment. This is an **uncertain outcome from the client's perspective**: the request may have executed while the response was lost.

Retries generally fit idempotent operations such as GET, or write operations carrying an idempotency key supported by the server. Do not rely on the HTTP method alone; understand endpoint semantics and ensure the server processes idempotency keys atomically.

A retry test should verify:

- How many requests are actually sent.
- Backoff intervals and maximum retry attempts.
- Which error types trigger retries, such as certain connection errors or transient statuses.
- Which errors are not retried, such as 400 validation errors.
- POST with an idempotency key does not create duplicate resources.
- Whether cancellation or overall deadline stops further retries.

Example with WebClient and Reactor Retry:

~~~java
Mono<String> result = webClient.get()
        .uri("/catalog/items/42")
        .retrieve()
        .bodyToMono(String.class)
        .retryWhen(
                reactor.util.retry.Retry.backoff(
                        2,
                        Duration.ofMillis(100)
                )
        );
~~~

This configuration allows up to two retries after the initial call, with increasing backoff. In real applications, filter which exception types are retried using **filter(...)** and set an overall deadline so retries do not exceed the caller's time budget.

You can verify request counts via **MockWebServer.takeRequest()** or the request count after the exchange finishes. For timing tests, avoid relying on fixed sleeps; use Reactor's virtual time scheduler when testing backoff logic independently of sockets, and use a local server when verifying HTTP interactions.

## 11. Connection Pools and Resource Limits

HTTP clients often reuse connections to reduce TCP/TLS setup cost. Connection pools have a limit on active connections and may queue callers waiting for a connection.

If all connections are busy, a new request may wait in the pool. This is a **pending acquire timeout**, distinct from a connect timeout: the client has not started a new connection yet because it has not obtained a connection from the pool.

With Reactor Netty, pools can be configured as follows:

~~~java
import java.time.Duration;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

ConnectionProvider provider = ConnectionProvider.builder("catalog-test")
        .maxConnections(1)
        .pendingAcquireTimeout(Duration.ofMillis(200))
        .build();

HttpClient httpClient = HttpClient.create(provider);
~~~

To test a pool timeout, the test must hold the single connection in use, then send a second request and verify it times out waiting to acquire. This is a concurrency test; explicitly coordinate when the first request starts and when it is allowed to finish. Do not use `sleep` hoping two requests overlap at the right moment.

When a test creates its own connection provider, dispose the provider after the test finishes to release the pool and associated event loop resources:

~~~java
provider.dispose();
~~~

You should also identify other limits such as maximum connections, concurrent request counts, response body size, byte buffer limits, and idle connection keep-alive duration. Load or concurrency tests can help surface pool exhaustion, provided they run with realistic configuration.

## 12. HTTP Error Statuses Are Not Connection Errors

An HTTP client may receive a complete 429, 500, or 503 response. This is an HTTP-layer outcome; the client successfully connected to the server and read the status line and headers.

With WebClient, **retrieve()** converts 4xx/5xx statuses into **WebClientResponseException** by default unless status handling is customized. You can assert the status and error body:

~~~java
StepVerifier.create(webClient.get()
                .uri("/unavailable")
                .retrieve()
                .bodyToMono(String.class))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(
                            org.springframework.web.reactive.function.client
                                    .WebClientResponseException.class
                    );
        })
        .verify();
~~~

If the application uses **onStatus(...)** to map error responses into domain exceptions, tests should verify that mapping. Do not write one test checking only **expectError()** for both HTTP 503 and TCP disconnect and conclude the two cases are handled identically; retry policies and user-facing error reporting may differ.

With `RestClient`, 4xx/5xx response statuses are handled through the status handler by default. You can configure a custom handler to convert responses into domain exceptions. I/O errors occurring before receiving a response are typically thrown as Spring or connector resource/connection exceptions.

## 13. Limitations of Transport-Layer Simulation

MockWebServer and WireMock run over local sockets, making them well suited to testing many real HTTP behaviors. Still, they do not fully represent a production network.

| What to verify | Is local simulation suitable? | When is a real environment needed? |
|---|---|---|
| Server delays headers or body | Yes | Usually not needed |
| Server closes socket before response | Yes | Usually not needed |
| Body cut off mid-stream | Yes | Needed if behavior depends on deployment proxy/connector |
| HTTP statuses 429/500/503 | Yes | Needed when verifying production server/gateway emits those statuses |
| Connect timeout from dropped SYN | Unreliable with MockWebServer alone | Needs controlled firewall or network fault injector |
| DNS timeout or changing DNS records | No | Needs DNS test environment |
| Expired TLS cert, wrong hostname, or trust chain | Local TLS server possible, but requires test certs | Needed when verifying environment trust stores, proxies, or certs |
| Proxy buffering, header rewriting, idle timeout | No if requests hit local mock server directly | Needs testing through corresponding proxy |
| Packet loss, jitter, and limited bandwidth | Not fully simulated | Needs network emulator or network test environment |
| Deployment HTTP/2, ALPN, and TLS negotiation | Depends on test server and connector | Needs production-equivalent environment |

Do not use the public Internet to simulate network errors. An external endpoint may change, rate-limit, or fail to respond at the desired moment. Tests become hard to reproduce and cannot isolate whether failures stem from the client, the external server, or the network.

For low-level network faults, use an isolated environment: local proxy, container network, temporary firewall rules, or a network fault-injection tool. Set test timeouts and always clean up rules/containers afterward.

## 14. Cancellation and Resource Release

With reactive clients, callers can cancel a subscription before the response completes. The client should propagate cancellation down to the HTTP exchange, stop reading the body, and release the connection or return it to the pool according to what the connector state allows.

You can test cancellation with a server keeping a response open, creating a subscription, and canceling it from the test. Tests should observe server-side or client-side hooks to verify the request was canceled; checking only that the subscriber receives no further items does not prove the socket was released.

With blocking clients, threads may be interrupted or callers may time out at an outer wrapper. Understand how far the request factory supports interruption/cancellation. Not every blocking HTTP implementation stops I/O immediately when a thread is interrupted.

For streaming responses, close the stream or response body after reading. Failing to drain or close the body can leave the connection in an unusable state and gradually exhaust the pool.

Tests should verify:

- Subscriptions are canceled when the overall deadline expires.
- Response bodies/streams are closed after processing.
- Connection pools do not leak held connections across repeated runs.
- Retries do not continue after cancellation.
- Background tasks do not keep writing into canceled resources.

## 15. Designing Stable and Diagnosable Tests

Timeout tests easily become flaky when intervals are too short or depend on machine load. A few principles keep results reliable:

- Use local MockWebServer/WireMock; do not call public services.
- Choose timeouts large enough to run reliably on CI yet smaller than the server's intentional delay.
- Use **StepVerifier.verify(Duration)** or test framework timeouts to bound total wait time.
- Use latches, barriers, or controlled publishers to synchronize requests and responses.
- Do not use **Thread.sleep()** to guess when the server received a request or when a timeout will fire.
- Distinguish HTTP status errors, connection errors, timeouts, deserialization errors, and cancellation.
- Verify request counts and request contents when testing retries.
- Close MockWebServer, WireMock, connection providers, and response streams after tests.
- Do not share response queues or mutable request recorders across parallel tests.

When a test fails, capture the received requests, sent responses, completion timing, and root-cause exception. Those details help distinguish application-layer bugs from connector or transport errors.

## 16. Tool and Error-Type Selection Matrix

| Goal | Tool to use |
|---|---|
| Test URI, method, headers, body, and mock HTTP status | MockRestServiceServer |
| Test service mapping I/O errors to domain exceptions | MockRestServiceServer or mock connector at appropriate boundary |
| Test read/response timeout over sockets | MockWebServer or WireMock |
| Test server closing connection after request | MockWebServer with SocketPolicy |
| Test truncated response body | MockWebServer/WireMock and real HTTP client |
| Test Reactor overall deadline and cancellation | StepVerifier, Reactor virtual time, and controlled server |
| Test connection pool acquire timeout | Reactor Netty ConnectionProvider and synchronized concurrency test |
| Test DNS, TLS, proxy, packet loss, or network policy | Corresponding network test environment |

No single mock simulates every layer. Use `MockRestServiceServer` to verify the request/response contract of Spring clients; use `MockWebServer` or `WireMock` to test HTTP connectors and reproducible socket faults; use real network environments when DNS, TLS, proxies, or infrastructure behavior must be verified.

A reliable HTTP client requires clear time limits, distinction between error responses and transport errors, proper disconnect and cancellation handling, and controlled retries. Tests at the right layers prove each of those behaviors without depending on random network outages.

