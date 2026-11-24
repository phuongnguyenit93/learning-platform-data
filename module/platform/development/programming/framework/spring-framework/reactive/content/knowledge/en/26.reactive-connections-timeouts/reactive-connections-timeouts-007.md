# HTTP/2 and Server and Connector Support Requirements in Spring WebFlux

## 1. Objectives

Spring WebFlux provides an asynchronous, non-blocking, and reactive HTTP processing model. However, WebFlux does not implement the transport-layer network protocol itself. Actual requests are received and sent by the **server connector** or **client connector** used by the application.

Therefore, having a controller return **Mono** or **Flux** does not mean requests are already running over HTTP/2. To use HTTP/2, verify all of the following simultaneously:

- Whether the server or client connector supports HTTP/2.
- Whether the Spring Boot, Spring Framework, and connector library versions are compatible.
- Whether TLS/ALPN is properly configured if using HTTP/2 over HTTPS.
- Whether proxies, ingresses, load balancers, and clients at each hop support the corresponding protocol.
- Whether the client actually negotiates HTTP/2 successfully rather than falling back to HTTP/1.1.

This lesson covers HTTP/2 at the level required for WebFlux deployments, how to enable it on the server with Spring Boot, requirements for Reactor Netty/Tomcat/Jetty/Undertow, how to configure WebClient, how to verify the protocol on the wire, and operational limits to monitor.

Examples use Java 17+ and compatible Spring Boot 3.5.x or 4.1.x. Dependency names and embedded server capabilities can change across Boot generations; always check against the exact release in use.

## 2. What Is HTTP/2?

HTTP/2 is the HTTP protocol version standardized in RFC 9113. It preserves HTTP semantics such as methods, status codes, headers, and bodies, while changing how messages are represented and transmitted over a connection.

HTTP/2 introduces key characteristics:

- **Binary framing:** data is split into binary-structured frames instead of HTTP/1.1's text syntax.
- **Streams:** each request/response exchange is associated with a stream having its own ID.
- **Multiplexing:** multiple streams can be interleaved over a single TCP connection.
- **Header compression:** HPACK compresses header fields to reduce repeated data.
- **Flow control:** controls how much data is sent per stream and across the entire connection.
- **Connection reuse:** one connection can serve multiple concurrent requests, reducing the need to open many TCP/TLS connections.

HTTP/2 still carries HTTP semantics. WebFlux controllers continue using `@GetMapping`, `@PostMapping`, `ResponseEntity`, `Mono`, and `Flux` as before. Changes sit at the connector and transport configuration, requiring no HTTP/2-specific controller code.

### 2.1. Comparing HTTP/1.1 and HTTP/2

| Feature | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Message representation | Text-based | Binary frames |
| Concurrent requests on one connection | Typically requires multiple connections; pipelining is rarely used | Multiple multiplexed streams on a single connection |
| Headers | Resends many repeated fields | HPACK header compression |
| Flow control | Mainly at the TCP layer | Connection- and stream-level flow control, alongside TCP |
| Connections | Often opens many connections to increase concurrency | Can share a single connection across multiple requests |
| Body framing | `Content-Length` or chunked transfer encoding | DATA frames and END_STREAM; does not use HTTP/1.1 chunked encoding |
| Security in browsers | HTTP and HTTPS | HTTP/2 over TLS |

HTTP/2 does not change the meaning of GET, POST, status codes, `Content-Type`, or JSON. It changes how messages are framed and multiplexed across a connection.

### 2.2. Streams and Multiplexing

Suppose a WebClient needs to call three endpoints on the same host:

```text
HTTP/1.1:
Connection A -> request 1
Connection B -> request 2
Connection C -> request 3

HTTP/2:
Connection A
  Stream 1 -> request 1
  Stream 3 -> request 2
  Stream 5 -> request 3
```

With HTTP/2, frames from multiple streams can interleave on a single TCP connection. A large response does not necessarily force smaller responses to wait for completion at the HTTP application layer. This reduces TCP/TLS handshake overhead and uses connections more efficiently.

Multiplexing does not mean the server processes an unlimited number of requests in parallel. Concurrent stream count is bounded by peer SETTINGS, connector limits, connection pools, server resources, and application concurrency.

### 2.3. Flow Control and TCP Limitations

HTTP/2 has two layers of flow control:

- **Stream-level window:** limits data in flight on a single stream.
- **Connection-level window:** limits total data in flight on the connection.

The receiver can send `WINDOW_UPDATE` to permit the sender to keep transmitting data. The goal is preventing a sender from pushing too much data into a slow receiver.

This is protocol-level flow control. Reactive Streams backpressure is an application-layer demand mechanism. The connector must coordinate these two layers; HTTP/2 flow control and Reactor backpressure should not be treated as a single mechanism.

Multiplexing eliminates part of HTTP/1.1's application-layer head-of-line blocking, yet HTTP/2 still runs over TCP. If a TCP packet is lost, subsequent bytes on the connection may have to wait for TCP retransmission before other streams can continue receiving data. HTTP/2 does not eliminate all forms of head-of-line blocking.

### 2.4. Header Compression and Framing

HTTP/2 uses HPACK to compress header fields. Frames can carry HEADERS, DATA, SETTINGS, WINDOW_UPDATE, PING, RST_STREAM, or GOAWAY.

An HTTP/2 request still has status and headers equivalent to HTTP/1.1, represented with pseudo-headers such as `:method`, `:scheme`, `:authority`, and `:path`.

HTTP/2 does not use HTTP/1.1 connection-specific headers such as `Connection`, `Keep-Alive`, `Proxy-Connection`, `Transfer-Encoding`, or `Upgrade`. Proxies translating between HTTP/2 and HTTP/1.1 must handle this difference properly.

## 3. Two Ways to Establish HTTP/2: h2 and h2c

HTTP/2 has two common identifiers:

| Protocol identifier | Transport | How It Starts | Use Cases |
| --- | --- | --- | --- |
| h2 | TLS | TLS handshake and ALPN negotiation | Public HTTPS, browsers, production APIs |
| h2c | Cleartext TCP | Prior knowledge; legacy HTTP/1.1 Upgrade was deprecated by RFC 9113 | Internal networks or hops behind a TLS-terminating proxy when controlled |

### 3.1. h2: HTTP/2 over TLS

When a client accesses an HTTPS URL, the client and server establish TLS. During the TLS handshake, both sides use **ALPN (Application-Layer Protocol Negotiation)** to agree on the application protocol.

The client can advertise protocols such as:

- `h2`: HTTP/2.
- `http/1.1`: HTTP/1.1.

If server and client agree on `h2`, subsequent requests use HTTP/2. Otherwise, both sides can use HTTP/1.1 if that protocol is also supported.

Important requirements:

- Valid certificate and private key.
- Hostname in the certificate matches the server name accessed by the client.
- TLS provider and connector support ALPN.
- Both client and server support HTTP/2.
- Proxies or load balancers do not strip protocol negotiation on the hop being inspected.

Java 17+ includes ALPN support in the JDK. On some older runtimes or configurations, the connector may need a native library such as Netty `tcnative` or Conscrypt. Check connector guidance rather than adding native libraries by default.

### 3.2. h2c: Unencrypted HTTP/2

`h2c` runs HTTP/2 directly over TCP without TLS. The client must know beforehand that the endpoint supports `h2c` and can send the connection preface via prior knowledge.

RFC 9113 deprecated upgrading HTTP/1.1 via the `Upgrade: h2c` header because that mechanism was not widely deployed. Therefore, when testing `h2c`, distinguish:

- **Prior knowledge:** the client knows the endpoint supports `h2c` and begins with the HTTP/2 connection preface.
- **Legacy HTTP/1.1 Upgrade:** the `Upgrade` token `h2c` mechanism deprecated in RFC 9113.

`h2c` can be useful when TLS is terminated at a proxy and the proxy opens a cleartext HTTP/2 connection to the backend. Use it only on controlled internal networks with proper network segmentation and security policies. Never treat `h2c` as a replacement for TLS on public connections.

### 3.3. HTTP/2 with TLS Does Not Mean End-to-End

A request may traverse multiple hops:

```text
Browser -- HTTPS / h2 --> Load balancer
Load balancer -- h2c --> WebFlux server
WebFlux server -- HTTP/1.1 --> Internal service
```

In this diagram, the client used HTTP/2 with the load balancer. The hop from load balancer to WebFlux also uses `h2c`. However, WebFlux calls the downstream service over HTTP/1.1.

Protocols are negotiated independently per connection. Therefore, you cannot inspect only the browser or one proxy and conclude every hop is using HTTP/2.

## 4. Roles of WebFlux, Server Connector, and Client Connector

Spring WebFlux builds on an HTTP handler abstraction and server adapters. The embedded server/connector handles port binding, TLS, protocol negotiation, frame reading, connection management, and response writing.

### 4.1. Server-Side

Common components:

- **HttpHandler:** low-level non-blocking HTTP processing contract.
- **HttpWebHandlerAdapter:** adapter connecting `WebHandler` to `HttpHandler`.
- **Server adapter:** integrates `HttpHandler` with Reactor Netty, Tomcat, Jetty, or compatible servlet containers.
- **Embedded server:** actually opens sockets, handles TLS/HTTP protocols, and dispatches requests into WebFlux.

Spring Boot WebFlux starter uses Reactor Netty by default. It can be swapped for Tomcat or Jetty; Boot 3.5 also supports Undertow in the reactive stack. Exact HTTP/2 capabilities depend on the server version and required modules/dependencies.

### 4.2. Client-Side

WebClient does not open sockets itself either. It uses a `ClientHttpConnector` to send requests and receive responses.

Common connectors/clients:

- Reactor Netty.
- JDK HttpClient.
- Jetty Reactive HttpClient.
- Apache HttpComponents.

Spring Boot can auto-detect a connector based on libraries on the classpath. If a specific protocol is needed, configure the corresponding underlying HTTP client. Simply adding `spring-boot-starter-webflux` does not mean every WebClient request automatically switches to HTTP/2.

### 4.3. Controllers Do Not Need to Know the Protocol

Example controller:

```java
@RestController
@RequestMapping("/api")
public class HelloController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of(
                "message", "Hello over HTTP",
                "framework", "Spring WebFlux"));
    }
}
```

This controller can be invoked over HTTP/1.1 or HTTP/2 if the server connector supports and negotiates it successfully. There is no need to create a separate method for HTTP/2.

## 5. Support Requirements by Server Connector

The table below summarizes Spring Boot 3.5 and 4.1 documentation. This is a guide for choosing a connector; verify against the exact BOM and server dependencies running in your project.

| Server in WebFlux | Boot 3.5 | Primary HTTP/2 Requirements | Notes |
| --- | --- | --- | --- |
| Reactor Netty | Yes, default | Supports `h2` and `h2c`; `h2` requires TLS/ALPN | Native `tcnative` can be used to optimize TLS |
| Tomcat 10.1.x | Yes | Supports `h2`/`h2c`; check native TLS support per runtime | Boot 4.1 uses Tomcat 11.x with `h2`/`h2c` support out of the box |
| Jetty | Yes | Requires `jetty-http2-server`; `h2` requires ALPN implementation | `h2c` does not need the same ALPN TLS dependencies |
| Undertow | Yes in Boot 3.5 reactive stack | Boot 3.5 docs note `h2` and `h2c` | Verify support when upgrading Boot majors; Boot 4.1 reactive server list focuses on Reactor Netty, Tomcat, and Jetty |

### 5.1. Reactor Netty

This is the default choice when using `spring-boot-starter-webflux`. Reactor Netty supports HTTP/2 over TLS and `h2c`. For `h2`, TLS must be configured; ALPN selects `h2` or HTTP/1.1 based on both sides' capabilities.

Boot documentation mentions the library:

```text
io.netty:netty-tcnative-boringssl-static
```

This library provides a native SSL implementation. It can improve performance or satisfy certain TLS environments; it is not always mandatory on modern JDKs that include ALPN.

### 5.2. Tomcat

Tomcat supports HTTP/2 at the connector layer. Exact capabilities depend on the Tomcat branch, JDK, TLS provider, and native libraries.

- Boot 3.5 uses Tomcat 10.1.x by default in the servlet stack; Boot docs note `h2`/`h2c`.
- Boot 4.1 uses Tomcat 11.0.x and notes `h2`/`h2c` out of the box.
- `libtcnative` can be used to support/optimize TLS depending on the environment.

Do not inspect only controller annotations. Inspect the Tomcat HTTP connector, SSL host config, ALPN, and native dependencies if the deployment requires them.

### 5.3. Jetty

Jetty requires the HTTP/2 server module:

```text
org.eclipse.jetty.http2:jetty-http2-server
```

To run `h2c`, Jetty does not need the same ALPN TLS dependency set. To run `h2` over TLS, an ALPN implementation is required, such as:

- `org.eclipse.jetty:jetty-alpn-java-server` to use JDK support.
- `org.eclipse.jetty:jetty-alpn-conscrypt-server` alongside the Conscrypt library.

When using Spring Boot, prefer versions managed by the BOM. Do not manually pick a Jetty version different from the one Boot manages.

### 5.4. Undertow

Spring Boot 3.5 documents replacing Reactor Netty with Undertow in the reactive stack and notes Undertow supports `h2c`/`h2`. When upgrading to Boot 4.x, re-check the list of supported server starters and compatibility status. Do not assume every server supported in Boot 3.x has an equivalent starter in Boot 4.x.

## 6. Enabling HTTP/2 on a Spring Boot Server

In Spring Boot, the primary property is:

```properties
server.http2.enabled=true
```

This property tells the embedded server to enable HTTP/2 if the current environment supports it. Choosing `h2` vs. `h2c` depends on SSL:

- If SSL/TLS is configured, the server can serve `h2`.
- If SSL is not enabled, Boot uses `h2c` according to HTTP/2 configuration docs.
- The server connector and deployment must still support the corresponding protocol.

### 6.1. Configuring HTTPS + HTTP/2

Example with PEM certificate/private key:

File `src/main/resources/application.properties`:

```properties
server.port=8443
server.http2.enabled=true
server.ssl.certificate=classpath:localhost.crt
server.ssl.certificate-private-key=classpath:localhost.key
```

The certificate must match the hostname clients use to connect. In production, the certificate must be issued by a CA trusted by clients and the private key must be protected.

You can use a PKCS#12 keystore instead of PEM:

```properties
server.port=8443
server.http2.enabled=true
server.ssl.key-store=classpath:server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=change-this-password
server.ssl.key-alias=server
```

These are illustrative values; in production, retrieve passwords from a secret manager or environment variables, and never commit real passwords to the repository.

### 6.2. Configuring h2c for Internal Networks

Example:

```properties
server.port=8080
server.http2.enabled=true
```

Do not configure `server.ssl` for this listener. Per Spring Boot configuration, the server uses `h2c` when SSL is not enabled.

`h2c` should be restricted to internal networks and configured consistently with proxies/ingresses. Clients need prior knowledge or a connector-supported mechanism. RFC 9113 deprecated the HTTP/1.1 `Upgrade` token `h2c`.

### 6.3. Enabling HTTP/2 Does Not Automatically Create Both HTTP and HTTPS Listeners

When configuring SSL via application properties, Boot normally configures an HTTPS connector. If you want both a cleartext HTTP listener and an HTTPS listener simultaneously, configure an additional connector via server-specific APIs. Do not assume setting `server.port` and `server.ssl.*` opens both ports automatically.

In production, ingress/load balancers usually manage public HTTP/HTTPS redirects and expose only the backend listener per network policy.

## 7. Complete Spring Boot WebFlux Server Example

The example uses Spring Boot 3.5.x, Java 17+, and default Reactor Netty.

### 7.1. Dependencies

File `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Use the Spring Boot Gradle plugin and dependency management to select compatible versions. The WebFlux starter brings Reactor Netty onto the classpath by default.

### 7.2. Application Class

File `src/main/java/demo/Http2Application.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Http2Application {

    public static void main(String[] args) {
        SpringApplication.run(Http2Application.class, args);
    }
}
```

### 7.3. Controller

File `src/main/java/demo/HelloController.java`:

```java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of(
                "message", "Hello over HTTP",
                "server", "Spring WebFlux"));
    }
}
```

The controller does not inspect the HTTP version. The server connector handles the protocol before the request reaches WebFlux.

### 7.4. Testing API Semantics

File `src/test/java/demo/HelloControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HelloControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void returnsHelloPayload() {
        client.get()
                .uri("/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello over HTTP")
                .jsonPath("$.server").isEqualTo("Spring WebFlux");
    }
}
```

This test verifies controller and HTTP response semantics. If `WebTestClient` is bound directly to the application context or test adapter, it does not prove TLS/ALPN negotiated HTTP/2 over a real socket. To verify the protocol, run the real server and inspect it with `curl`/`openssl` or an HTTP/2-capable client.

## 8. Configuring a Server Connector Other Than Reactor Netty

### 8.1. Switching to Jetty

Gradle example replacing Reactor Netty with Jetty:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'

    implementation 'org.eclipse.jetty.http2:jetty-http2-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Use the Jetty version managed by the Boot BOM. For `h2` over TLS, add the ALPN implementation per the guidance of the Jetty/Boot version in use. `server.http2.enabled=true` and SSL properties remain Boot's starting point.

### 8.2. Switching to Undertow in Boot 3.5

Dependency replacement example per Boot 3.5 documentation:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-undertow'

    modules {
        module('org.springframework.boot:spring-boot-starter-reactor-netty') {
            replacedBy(
                    'org.springframework.boot:spring-boot-starter-undertow',
                    'Use Undertow instead of Reactor Netty')
        }
    }
}
```

After swapping the server, check the WebClient connector separately. If you still want WebClient to use Reactor Netty, the Reactor Netty client dependency may still be needed; server and client are two independent connector choices.

### 8.3. Do Not Arbitrarily Mix Server Dependencies

If multiple server starters remain on the classpath, Boot may pick one via auto-configuration or encounter conflicts. Exclude the default server starter properly when changing connectors and inspect the dependency tree.

In particular, never pull in a newer Jetty/Tomcat/Netty version and override a single module outside the BOM. Connector, transport, TLS modules, and Spring Boot auto-configuration must remain compatible.

## 9. Configuring HTTP/2 for WebClient

WebClient uses `ClientHttpConnector` to execute requests. With Spring Boot, the connector can be auto-detected from the classpath. Reactor Netty is typically preferred when present alongside the WebFlux starter.

**The default client does not necessarily use HTTP/2 automatically.** With Reactor Netty, configure both protocol and TLS:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.HttpProtocol;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class Http2ClientConfiguration {

    @Bean
    WebClient http2WebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .protocol(HttpProtocol.H2)
                .secure();

        return builder
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Explanation:

- `HttpClient.create()` creates a Reactor Netty HTTP client.
- `protocol(HttpProtocol.H2)` requests HTTP/2.
- `secure()` enables TLS to use `h2` over HTTPS.
- `ReactorClientHttpConnector` attaches this client to WebClient.
- Requests sent with WebClient continue using the standard fluent API.

Configuring only `HttpProtocol.H2` as above will not fall back to HTTP/1.1. If you need to negotiate HTTP/2 while still allowing older endpoints, configure both protocols:

```java
HttpClient httpClient = HttpClient.create()
        .protocol(HttpProtocol.H2, HttpProtocol.HTTP11)
        .secure();
```

HTTP/2 is then preferred during ALPN negotiation; HTTP/1.1 can be chosen if the peer does not support `h2`.

### 9.1. WebClient h2c

For an internal endpoint confirmed to support `h2c` prior knowledge, you can configure the Reactor Netty client:

```java
HttpClient httpClient = HttpClient.create()
        .protocol(HttpProtocol.H2C);

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

Use an `http://...` URL and ensure the server actually supports `h2c` prior knowledge. Do not send `h2c` to an ordinary HTTP/1.1 endpoint.

### 9.2. Other Client Connectors

WebClient supports Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient, and Apache HttpComponents. HTTP/2 capabilities, how protocols are enabled, TLS, and connection pools differ across libraries.

If changing connectors, do not copy Reactor Netty's `HttpProtocol.H2` configuration verbatim to another connector. Use the API and official documentation of the JDK, Jetty, or Apache HttpComponents version in use.

## 10. HTTP/2 and the WebClient Connection Pool

HTTP/2 allows multiple streams to share a single connection. Reactor Netty uses a connection pool with a dedicated stream allocation mechanism for HTTP/2.

Important concepts:

- **maxConnections:** limits the number of connections in the pool.
- **minConnections:** minimum number of connections maintained on a best-effort basis.
- **maxConcurrentStreams:** limits concurrent streams per connection; the actual limit also depends on the server's SETTINGS.
- **strictConnectionReuse:** prefers reusing an existing connection with available stream capacity instead of opening a new one.
- **streamBatchSize:** number of streams that can be opened in a batch when strict reuse is enabled.

Do not inflate connection counts assuming HTTP/2 still needs one connection per request. Conversely, do not force a single connection to carry all traffic if the server or network cannot sustain it.

Measure:

- Active connections.
- Active/pending streams.
- Wait time to acquire a stream or connection.
- Reconnect/TLS handshake counts.
- p50/p95/p99 latency.
- Stream reset rate and GOAWAY errors.
- CPU, memory, network throughput, and server concurrency.

### 10.1. Multiplexing Is Not Unlimited Concurrency

The server sends `SETTINGS_MAX_CONCURRENT_STREAMS` to advertise its concurrent stream limit. The client must not open more streams than the peer permits. If there are more concurrent requests than a connection can carry, they may wait or the pool may open additional connections.

The application must still bound concurrency at the service layer. A WebClient firing hundreds of thousands of concurrent requests can exhaust connection pools, queues, CPU, or downstream resources even when HTTP/2 multiplexing is enabled.

### 10.2. Backpressure and HTTP/2 Flow Control

Reactor `Flux`/`Mono` uses demand to regulate publishers. HTTP/2 flow control uses window updates to regulate byte transfers on streams/connections.

The connector bridges these two mechanisms. However, if the application buffers the entire body in memory, calls `collectList()`, or uses blocking I/O, HTTP/2 does not automatically make the application streaming/non-blocking.

Design reactive pipelines and concurrency limits as usual; HTTP/2 is an additional transport layer.

## 11. Proxies, Ingress, and Load Balancers

In production systems, clients rarely connect directly to the embedded server. A request may pass through a CDN, WAF, reverse proxy, ingress controller, service mesh, and backend.

Each hop may use a different protocol:

| Client → edge | Edge → backend | Protocol received by backend |
| --- | --- | --- |
| h2 | h2 | HTTP/2 |
| h2 | h2c | HTTP/2 cleartext |
| h2 | HTTP/1.1 | HTTP/1.1 |
| HTTP/1.1 | h2 | HTTP/2 |
| HTTP/1.1 | HTTP/1.1 | HTTP/1.1 |

Thus, a browser showing `h2` does not prove the backend also receives HTTP/2.

When deploying behind a proxy:

1. Identify where TLS is terminated.
2. Check the client→proxy protocol.
3. Check the proxy→backend protocol.
4. If using internal `h2c`, expose that port only on the private network and restrict sources.
5. Check whether the load balancer's health check uses the appropriate backend protocol.
6. Ensure the proxy forwards headers properly and does not carry HTTP/1.1 connection-specific headers into HTTP/2.
7. Set timeouts, idle timeouts, and max concurrent streams appropriately.
8. Verify graceful shutdown and GOAWAY during rolling backend deployments.

If a proxy terminates TLS, the backend may receive HTTP/1.1 even though the client used `h2`. That is a valid setup; simply understand the protocol on each hop.

## 12. Verifying Whether the Server Uses HTTP/2

Do not check only declared properties. Verify the actual protocol on the socket.

### 12.1. Verify curl Supports HTTP/2

Run:

```bash
curl -V
```

The Features list must include `HTTP2`. If absent, the `curl` binary does not support HTTP/2; test results will not be meaningful.

### 12.2. Verify HTTPS + h2

Run against a local server on port 8443:

```bash
curl -vk --http2 https://localhost:8443/hello
```

In verbose output, look for ALPN info and the response status line:

```text
ALPN: server accepted h2
< HTTP/2 200
```

For self-signed certificates in local environments only, `-k` skips certificate validation for testing. Never use `-k` in production; production must validate the certificate chain and hostname.

Note: `curl --http2` may negotiate and fall back to HTTP/1.1 if the peer does not support `h2`. Read the actual protocol output rather than relying solely on `curl` returning status 200.

### 12.3. Verify h2c Prior Knowledge

If the server enables `h2c` on port 8080:

```bash
curl -v --http2-prior-knowledge http://localhost:8080/hello
```

The expected response contains:

```text
< HTTP/2 200
```

Depending on the `curl` version, the prior-knowledge option may be unavailable or named differently. Check `curl --help all` and `curl -V` before use.

### 12.4. Verify ALPN with OpenSSL

Run:

```bash
openssl s_client   -connect localhost:8443   -servername localhost   -alpn h2
```

If the TLS handshake succeeds and ALPN selects HTTP/2, the output includes something like:

```text
ALPN protocol: h2
```

If there is no ALPN protocol or the server picks `http/1.1`, check the certificate, TLS provider, server connector, and ALPN configuration.

### 12.5. Verify with a Browser

Open Developer Tools → Network → select the request → view the Protocol column. Chrome/Edge usually display `h2` when the request uses HTTP/2.

If the Protocol column is hidden, enable it in the Network table. Check the exact request and exact domain; a single page can load resources from multiple origins using different protocols.

### 12.6. Verify via Logs/Metrics

Reactor Netty provides metrics for active connections and HTTP/2 streams. You can use access logs, tracing, or server metrics to identify the protocol. Do not enable full wire logging in production without evaluating log volume and the risk of exposing headers/bodies.

## 13. How Does HTTP/2 Affect a WebFlux Application?

### 13.1. Controllers and Routers Need No Changes

Controllers can keep returning `Mono`/`Flux`. Functional endpoints also need no route changes simply because HTTP/2 is enabled.

### 13.2. It Does Not Automatically Make Every Request Faster

HTTP/2 can reduce connection counts, reduce handshake costs, and improve concurrency. Yet actual performance depends on:

- Latency and packet loss.
- Response size.
- Concurrent request count.
- CPU for TLS and header compression.
- Stream and connection pool limits.
- Proxies/load balancers.
- Backpressure and blocking code in the application.
- Downstream services and databases.

Benchmark with a representative workload. An API with low request counts, large payloads, or a slow backend may not see significant gains.

### 13.3. It Does Not Change Timeout Semantics

HTTP/2 has separate connections and streams. Timeouts at connect, TLS handshake, response/read, stream, and idle connection layers are not all identical.

When tuning timeouts, distinguish:

- TCP connect timeout.
- TLS handshake timeout.
- Response timeout.
- Read/write timeouts.
- Idle timeout for the connection pool.
- Stream timeout or application deadline.

Do not set an overly low timeout on the entire connection just to handle one slow request. Monitor timeouts per stage.

### 13.4. Handling Stream Resets and GOAWAY

HTTP/2 has stream-level and connection-level errors. One stream can be reset while other streams on the connection continue. `GOAWAY` notifies the client that the server is preparing to close the connection and which streams were processed.

During rolling server restarts, graceful shutdown is needed to avoid dropping in-flight requests. Clients should retry conditionally, especially for idempotent requests; do not automatically retry POSTs with side effects without an idempotency key and proper policy.

### 13.5. Connection Reuse and DNS/Load Balancing

HTTP/2 encourages connections to live longer. That reduces handshakes, yet can also pin a connection to a single backend longer than expected.

If DNS or a load balancer changes backends, open connections do not automatically migrate to another node. Design pool eviction, max connection age/idle timeout, and graceful drain suited to your infrastructure.

## 14. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Thinking reactive WebFlux means HTTP/2 | Requests may still use HTTP/1.1 | Verify server/client connectors and the actual protocol |
| Setting only `server.http2.enabled=true` without TLS | Boot uses `h2c`; public clients may not connect as intended | Configure SSL for `h2` or use `h2c` internally on purpose |
| Certificate does not match hostname | TLS handshake or certificate validation fails | Use a valid certificate and correct hostname |
| ALPN not supported/configured | Client and server cannot negotiate `h2` | Check JDK/TLS provider/connector/native dependencies |
| Jetty missing HTTP/2 server module | Server fails to start or lacks `h2` support | Add `jetty-http2-server` and the right ALPN implementation |
| Using default client and thinking WebClient is always `h2` | Client may keep using HTTP/1.1 | Configure the underlying `HttpClient`/connector |
| Configuring H2 when endpoint supports only HTTP/1.1 | Requests fail if no fallback exists | Allow H2 + HTTP11 or upgrade the endpoint |
| Browser uses `h2` while backend uses HTTP/1.1 | Misunderstanding end-to-end protocol | Inspect each proxy/backend hop |
| Using `h2c` on public networks | No TLS protecting transport | Use HTTPS/`h2` |
| Using HTTP/1.1 Upgrade `h2c` from old examples | Upgrade mechanism was deprecated by RFC 9113 | Use `h2` via ALPN or `h2c` prior knowledge in controlled networks |
| Allowing unbounded concurrency | Pool, server, or downstream overload | Bound concurrency and max streams |
| Forcing one connection to serve all load | Stream queueing or throughput drops when connection saturates | Tune pool and measure workload |
| Thinking HTTP/2 eliminates TCP head-of-line blocking | Packet loss can still stall data on the connection | Evaluate network behavior; HTTP/3 is a different protocol |
| Auto-retrying all stream errors | May execute side effects twice | Retry conditionally with idempotency keys |
| Testing with mock WebTestClient and concluding `h2` works | Test does not verify ALPN/socket protocol | Test the real server with `curl`/`openssl` |
| Checking only status 200 | Does not show which protocol was negotiated | Check HTTP/2 status line, ALPN, or DevTools |
| Enabling overly broad wire logging | Exposes headers/bodies and generates massive logs | Use metrics/tracing and redact sensitive data |

## 15. HTTP/2 Deployment Checklist

1. Determine whether HTTP/2 is needed on the inbound server, outbound WebClient, or both.
2. Verify the actual Spring Boot version, Spring Framework version, and embedded server/client dependencies.
3. Confirm the connector in use supports HTTP/2 in that release.
4. Choose `h2` over TLS or internal `h2c`.
5. For `h2`, configure certificate, private key, hostname, and ALPN.
6. For `h2c`, confirm client prior-knowledge and server support for the same mode.
7. Set `server.http2.enabled=true` if using Spring Boot's embedded server.
8. If switching connectors, exclude the default server dependency properly and add the required HTTP/2 modules.
9. If using WebClient, configure the underlying `ClientHttpConnector`/`HttpClient` to enable HTTP/2.
10. Inspect proxies/load balancers on every hop.
11. Verify using `curl`, `openssl`, or browser DevTools.
12. Measure active connections, active/pending streams, latency, and resets/GOAWAY.
13. Tune max concurrent streams, pool, idle timeouts, and concurrency based on real load.
14. Test graceful shutdown, retries, and idempotency.
15. Keep TLS/certificate validation and internal network security compliant with policy.

## 16. Official References

- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): framing, streams, multiplexing, flow control, `h2`, `h2c`, and TLS/ALPN.
- [Spring Boot 3.5 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.http2.enabled`, `h2`/`h2c`, and requirements for Tomcat, Jetty, Reactor Netty, Undertow.
- [Spring Boot 4.1 – Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): HTTP/2 configuration by embedded server in the newer Boot generation.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux server support and auto-configuration.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): WebClient runtime, connector auto-detection, and precedence order.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring Reactor Netty, JDK HttpClient, Jetty, and `ClientHttpConnector`.
- [Reactor Netty – HTTP Server Reference](https://projectreactor.io/docs/netty/release/reference/http-server.html): enabling H2/H2C, TLS, and server-side protocol selection.
- [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): enabling HTTP/2 on the client, ALPN, connection pools, and stream allocation.
- [Spring Framework – Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): `HttpHandler` adapters and server/client connector abstractions.

## 17. Key Takeaways

**HTTP/2 is the responsibility of the server/client connector, not controller annotations.** Spring WebFlux still handles requests with the same `WebHandler`, controllers, and Reactor publishers; the connector determines the protocol on the socket.

In Spring Boot, enable the server with `server.http2.enabled=true`. For HTTPS, TLS and ALPN are required to negotiate `h2`. If SSL is not enabled, Boot may use `h2c`; use cleartext HTTP/2 only on controlled internal networks and remember that RFC 9113 deprecated HTTP/1.1 Upgrade `h2c`. Reactor Netty, Tomcat, Jetty, and Undertow have different support requirements by version. WebClient also requires configuring its connector/client explicitly if you want outbound HTTP/2.

Multiplexing lets multiple streams share one connection, yet concurrent stream limits, flow control, and TCP head-of-line blocking still apply. Verify the actual protocol using `curl`/ALPN or browser DevTools, measure connection/stream metrics, and test across the entire path from proxy to backend before concluding HTTP/2 is properly enabled.
