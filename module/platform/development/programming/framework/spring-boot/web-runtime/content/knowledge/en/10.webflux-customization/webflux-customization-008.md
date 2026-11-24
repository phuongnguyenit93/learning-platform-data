# Distinguishing Reactive Server Configuration from WebClient Configuration in Spring Boot

## 1. Purpose and Scope

A Spring Boot WebFlux application often **receives HTTP requests** from callers while simultaneously **sending HTTP requests** to other services. Both traffic directions may use Reactor Netty, yet they are **not governed by a single configuration system**.

This lesson clarifies:

- **Reactive HTTP server (inbound)**: the application listens on an address/port, accepts requests, runs WebFlux handlers, and produces responses.
- **WebClient (outbound)**: the application actively opens HTTP(S) connections to an upstream, sends requests, and receives and decodes responses.
- Server factory mechanisms vs. client builder/connector mechanisms; the scopes of `server.*`, `spring.webflux.*`, `spring.http.reactiveclient.*` (Boot 3.5), and `spring.http.clients.*` (Boot 4.x).
- How **resource sharing** works for Reactor Netty/Jetty without conflating server and client settings.
- Common adjustments: bind port, base URL, connect/read/response timeouts, SSL, proxies, headers, codecs, metrics, and testing.

Primary examples use **Spring Boot 3.5.x, Java 17+, and Reactor Netty**, so Java imports and property names in the examples follow that release line. For Boot 4.x, check the starters, packages, and HTTP client property namespaces before copying.

## 2. One Process, Two Network Roles

~~~text
                   SPRING BOOT WEBFLUX APPLICATION
  External client
       |
       | GET http://service:8088/api/proxy
       v
  [HTTP SERVER / INBOUND]
       | TCP listener created by embedded Reactor Netty
       | server.port, server.address, server.ssl.*, ...
       v
  WebFlux HttpHandler -> Router/Controller
       |
       | Controller calls WebClient.get(...)
       v
  [HTTP CLIENT / OUTBOUND]
       | baseUrl, request headers, ClientHttpConnector,
       | connect timeout, read timeout, TLS trust, proxy...
       v
  Another upstream service (or loopback to this server)
       |
       v
  Upstream response -> Mono/Flux -> response to original caller
~~~

On the inbound side, Spring Boot creates a **ReactiveWebServerApplicationContext**, chooses a **ReactiveWebServerFactory**, and starts a listening server. On the outbound side, Spring Boot can supply a pre-configured **WebClient.Builder**, allowing you to build `WebClient` instances with an appropriate **ClientHttpConnector**.

Both can run on Reactor Netty event loops and share certain resources. That **does not turn** `HttpServer` into `HttpClient`, does not turn `server.port` into an upstream target address, and does not make one-way TLS settings apply automatically in the other direction.

## 3. Core Comparison Table

| Aspect | Reactive server (inbound) | WebClient (outbound) |
|---|---|---|
| Who initiates the connection? | External clients connect to the app | The app connects out to target services |
| Spring Boot / Spring Framework API | `ReactiveWebServerFactory`, `WebServerFactoryCustomizer` | `WebClient.Builder`, `WebClientCustomizer`, `ClientHttpConnector` |
| Underlying Reactor Netty API | `reactor.netty.http.server.HttpServer` | `reactor.netty.http.client.HttpClient` |
| Primary address/port | `server.address`, `server.port` | `WebClient.Builder.baseUrl(...)` and request URIs |
| TLS | Certificate/private key to **accept** HTTPS, e.g., `server.ssl.*` | Trusted CA, optional client cert, hostname verification to **call** HTTPS |
| Timeouts | Idle/request/read on incoming connections (server-dependent) | Connect/read/response/request pipeline timeouts on outgoing calls |
| HTTP proxy | Reverse proxy in front of server, forwarded headers | Forward proxy used by the outbound client |
| Routing | `@GetMapping`, `RouterFunction`, `spring.webflux.base-path` | `WebClient.get().uri(...)`, base URL, filters |
| Headers | Incoming HTTP request and outgoing HTTP response | Outgoing HTTP request and upstream HTTP response |
| Codecs | WebFlux decodes request bodies and encodes responses | WebClient encodes request bodies and decodes upstream responses |
| Resources | Listeners, accepted sockets, event loops | Outgoing connections, connection pools, event loops |
| Startup | Usually tied to the Spring application context lifecycle | Beans can be created upfront, while network calls run on subscribe |
| Testing | `@SpringBootTest(RANDOM_PORT)` or `WebTestClient` | Test outbound calls via mock HTTP servers or real test upstreams |

**Rule of thumb:** the server is where **others call you**; `WebClient` is how **you call others**. The word "reactive" describes the non-blocking programming model—not that every Netty setting applies to both directions.

## 4. Configuring the Reactive Server: Properties, Factory, Lifecycle

### 4.1. Using server.* for Common Needs

Sample properties for the embedded reactive server:

~~~properties
server.port=8088
server.address=127.0.0.1
server.compression.enabled=true
# Inbound HTTPS example (enable only after configuring certificate and key):
# server.ssl.enabled=true
# server.ssl.bundle=my-server-bundle
~~~

- `server.port`: port on which the server **listens**, not `WebClient`'s remote port.
- `server.address`: server bind address—for example, `127.0.0.1` restricts access to loopback. It does not select the source IP for outbound connections.
- `server.compression.*`: compresses server HTTP responses subject to size/content-type thresholds; does not force upstreams to return compressed responses.
- `server.ssl.*`: **server-side** TLS; does not tell `WebClient` to trust an upstream certificate.

Specifically, `server.port=0` asks the OS to assign an available ephemeral port for the real server; `server.port=-1` disables the main HTTP listener while keeping the web application context. Neither disables `WebClient`, since outbound calls depend on whichever services or runners invoke it.

### 4.2. Scope of spring.webflux.*

Settings like `spring.webflux.base-path`, static resource mappings, and WebFlux configuration affect **server routing**. They do not set `WebClient`'s remote base URL. For instance, with:

~~~properties
spring.webflux.base-path=/v1
~~~

a handler mapped at `/api/hello` becomes reachable at `/v1/api/hello`. Meanwhile, a `WebClient` configured with `baseUrl("https://payments.example")` still calls that host directly; Spring Boot does not prepend `/v1` to outbound URIs.

Similarly, `WebFluxConfigurer` is the extension point for server-side handlers/mappings/formatters. It **does not replace** `WebClient.Builder`. Always clarify whether you are modifying the inbound router or the outbound HTTP client.

### 4.3. When Properties Aren't Enough: WebServerFactoryCustomizer

In Spring Boot 3.5, you can declare:

~~~java
import java.time.Duration;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
WebServerFactoryCustomizer<NettyReactiveWebServerFactory> nettyServerCustomizer() {
    return factory -> factory.addServerCustomizers(
            server -> server.idleTimeout(Duration.ofSeconds(20)));
}
~~~

This is a **method snippet inside a `@Configuration` class**, not a complete Java file. `NettyReactiveWebServerFactory` builds the server, and `addServerCustomizers` adds a callback customizing the Reactor Netty **`HttpServer`**. Here `idleTimeout` caps how long a server-side HTTP connection waits for the next request—**not** `WebClient`'s timeout waiting for an upstream.

Use `addServerCustomizers` when **appending**; `setServerCustomizers` can replace existing customizers. Normally, before writing code, check whether `server.*` or `server.netty.*` properties in your Boot version already cover the requirement.

Unlike Servlet MVC factories, reactive web server factories have their own interfaces and lifecycles. If running WebFlux on Jetty or Tomcat, a `WebServerFactoryCustomizer<NettyReactiveWebServerFactory>` will not apply to those factories. Never infer solely from a Netty JAR on the classpath that the WebFlux server is actually running Netty.

### 4.4. Avoid Replacing the Entire Factory

If you declare a custom `ReactiveWebServerFactory` bean, the auto-configuration branch creating the default factory backs off. Boot can still apply matching auto-configured `WebServerFactoryCustomizer`s to your factory, but you must ensure type compatibility and required server configuration. Use this only when replacing how the server itself is constructed, not just to change a timeout or port.

## 5. Configuring WebClient: Builder, Connector, and Upstream URI

### 5.1. Recommended Approach in Spring Boot

Spring Boot 3.5 provides an auto-configured prototype `WebClient.Builder` bean. **Inject the builder** and create a `WebClient` per upstream/service:

~~~java
@Bean
WebClient catalogWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://catalog.example")
            .defaultHeader("X-Client-Name", "inventory")
            .build();
}
~~~

This is an illustrative method for a `@Configuration` class with appropriate imports. `baseUrl` specifies where **outbound** HTTP requests go and is unrelated to `server.port`. `defaultHeader` sets a default header on `WebClient` requests, not a response header returned by the Spring WebFlux server.

A built `WebClient` is immutable and safe to reuse across requests. The **builder** itself is stateful: mutating a builder affects clients built from it afterward. When creating multiple clients from one builder inside a method, consider `builder.clone()` so one client's `baseUrl` or headers do not leak into another.

Static `WebClient.create()` or `WebClient.builder()` calls do not automatically inherit all configurations Spring Boot applies to the injected builder. That can drop shared HTTP resources, codec customizers, observability, or framework client settings. Avoid creating clients directly unless you have an explicit reason.

### 5.2. HTTP Client Implementation Need Not Match HTTP Server

Boot can select a `ClientHttpConnector` for `WebClient` based on HTTP client libraries on the classpath; in Boot 3.5, the precedence order is Reactor Netty, Jetty RS client, Apache HttpClient, and JDK HttpClient. The WebFlux starter brings Reactor Netty in for both the HTTP server and—potentially—the HTTP client.

Functionally, however, the two choices are independent:

- A WebFlux server running on **reactive Tomcat** can still use `WebClient` + **Reactor Netty `HttpClient`**.
- A WebFlux server running **Reactor Netty** can still call APIs using `WebClient` with a **Jetty client connector** when dependencies and configuration match.
- A Spring MVC/Servlet app can also use `WebClient` for outbound calls; that does not convert the server to WebFlux.
- If multiple client connector implementations sit on the classpath, verify which one was auto-configured rather than guessing from the first dependency listed.

### 5.3. WebClient Timeouts in Spring Boot 3.5

Official Spring Boot 3.5 documentation supports configuring HTTP clients under:

~~~properties
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
spring.http.reactiveclient.redirects=dont-follow
~~~

These properties configure Boot's auto-configured **HTTP client connector** and do not change the idle/read timeouts of the inbound server.

- **Connect timeout**: caps time spent establishing a connection to the target.
- **Read timeout**: corresponding read timeout on the HTTP client per connector behavior.
- **Redirect policy**: whether the client automatically follows redirect responses.
- Every timeout has connector-specific semantics. Never equate connect timeout, time-to-first-byte, full body download duration, and the **overall business deadline**.

To cap the total duration of a specific reactive pipeline, attach a Reactor operator:

~~~java
Mono<String> body = webClient.get()
        .uri("/v1/data")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(5));
~~~

This is an illustrative method snippet requiring `webClient` and imports. `timeout(Duration)` bounds the **Publisher pipeline** starting at subscription; it is not a server accept timeout and not a full substitute for socket-level connect/read timeouts.

**Version warning:** Spring Boot 4.x reorganizes the HTTP client property namespace. Per 4.1 documentation, general client settings use `spring.http.clients.connect-timeout`, `spring.http.clients.read-timeout`, and reactive connector selection uses `spring.http.clients.reactive.connector`. Do not copy Boot 3.5's `spring.http.reactiveclient.*` keys verbatim into 4.x without checking the target version's property metadata.

### 5.4. Customizing a Reactor Netty HttpClient Directly

When properties are insufficient, you can configure an `HttpClient` and pass it to **`WebClient`**:

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(4));

WebClient specialClient = builder.clone()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://partner.example")
        .build();
~~~

This is a **Java snippet** requiring imports for `reactor.netty.http.client.HttpClient`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`, and `java.time.Duration`; `builder` is the injected `WebClient.Builder`.

- `HttpClient.create()` is the **client**, not `reactor.netty.http.server.HttpServer`.
- `responseTimeout` tunes how that specific client waits for an HTTP response; it does not affect the server's port or idle timeout.
- `clientConnector(...)` replaces the connector for the built client. This can bypass part of Boot's auto-configured connector, SSL, and resource management; verify carefully when overriding.
- To apply a change across many clients, consider Boot-level client connector customizers available in your **exact version** rather than manually instantiating `new` connectors per service.

Never call `.block()` on an event-loop thread inside a WebFlux controller. The section 8 example returns a non-blocking `Mono<String>`; `.block()` appears only in the JUnit test running on a test thread.

### 5.5. Outbound Proxy vs. Inbound Reverse Proxy

**Inbound reverse proxy:** Nginx, a gateway, or a load balancer stands in front of Spring Boot; configure `server.forward-headers-strategy`, trusted proxies, and forwarded headers so the server resolves external scheme/host correctly.

**Outbound forward proxy:** `WebClient` connects outward through an HTTP proxy; configure the **HTTP client connector** itself. For instance, Reactor Netty offers `HttpClient.proxy(...)` and supports proxy authentication as needed. Do not set `server.forward-headers-strategy` and expect `WebClient` to start routing through a proxy.

When target service URLs derive from user input, enforce hostname/IP allowlists, redirect controls, and DNS checks to prevent SSRF. Outbound HTTP client configuration is a separate security boundary from inbound routing.

## 6. TLS, mTLS, and SSL Bundles: Two Different Trust Directions

When the application **serves HTTPS**, the server needs a certificate and private key to prove its identity to callers. Settings typically live under `server.ssl.*` or a server SSL bundle, matching your server implementation and Boot version.

When **`WebClient` calls HTTPS**, the client must verify the target service's certificate; if the upstream requires mTLS, the client must also present an appropriate client certificate. Having an HTTPS endpoint on your server **does not make `WebClient` use that certificate**, and adding a trusted CA for outbound calls **does not enable HTTPS on your server**.

In Boot 3.5, you can inject `WebClientSsl` and apply a declared SSL bundle, as in this configuration method snippet:

~~~java
@Bean
WebClient partnerClient(WebClient.Builder builder, WebClientSsl ssl) {
    return builder.baseUrl("https://partner.example")
            .apply(ssl.fromBundle("partner-trust"))
            .build();
}
~~~

Importing `org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl` applies to **Boot 3.5**. A real bundle requires truststore/certificate configuration and secrets managed via a secrets mechanism; this snippet will not run without a configured bundle named `partner-trust`.

Never disable hostname verification or install a trust-all TrustManager to "fix" SSL errors in production. Always verify certificate chains, SAN/hostnames, expiration, CAs, and the distinction between mTLS client identity and server identity.

## 7. What Can Be Shared Between the Server and WebClient?

Spring Boot can create a `ReactorResourceFactory` or `JettyResourceFactory` to manage HTTP resources. When **the same technology** backs both client and server and the client is built from **Boot's auto-configured `WebClient.Builder`**, Netty/Jetty resources can be shared to reduce overhead.

What can be shared:

- Event-loop resources and underlying I/O resources managed by Spring Boot.
- Resource lifecycle/shutdown wiring connected by Boot to the application context.
- Certain codec configurations when both the WebFlux server and Boot-built `WebClient` use Boot auto-configuration.

What you **must not assume** is shared:

- The inbound listening port and outbound remote ports.
- Server listening sockets and outbound client connection sockets.
- Server SSL identity and client trust settings.
- Server idle timeout and `WebClient` response timeout.
- Inbound authorization policies and outbound call credentials.
- Inbound request headers and headers sent out by `WebClient`.

**Common trap:** declaring a custom `ReactorResourceFactory` bean can affect **both client and server** if both consume that resource bean. Conversely, building a `WebClient` with a custom `ReactorClientHttpConnector` may opt out of Boot's sharing model. Thus functional independence **does not mean** all resource settings are completely isolated.

If you manage connection pools or `LoopResources` yourself, verify ownership and close resources when the application context stops. Spawning unbounded event loops or pools per request leaks threads/sockets and degrades performance.

## 8. Complete Example: One App Acting as Both WebFlux Server and WebClient

This example runs on Spring Boot **3.5.16**, Java 17+, and Reactor Netty. To avoid depending on an external upstream, `WebClient` calls back into a separate endpoint **inside the same application**. That is still a genuine outbound HTTP call over the loopback network stack, clearly illustrating both independent roles.

### 8.1. Project Structure

~~~text
reactive-server-client/
  pom.xml
  src/
    main/
      java/com/example/reactive/ServerClientDemoApplication.java
      resources/application.properties
    test/
      java/com/example/reactive/ServerClientDemoTest.java
~~~

### 8.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-server-client</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Do not add `spring-boot-starter-web`: having MVC and WebFlux together can cause Boot to infer web application type **SERVLET** instead of `REACTIVE`. This sample project intentionally includes only the WebFlux starter to keep the reactive web server and controllers running as designed.

### 8.3. application.properties

~~~properties
# HTTP SERVER: application accepts requests on loopback port 8088.
server.address=127.0.0.1
server.port=8088
server.compression.enabled=true

# HTTP CLIENT: URL of the service called by WebClient.
# Demo calls the server above to avoid depending on external APIs.
demo.upstream.base-url=http://127.0.0.1:8088

# HTTP CLIENT: applies to Spring Boot 3.5 property API only.
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
spring.http.reactiveclient.redirects=dont-follow
~~~

`server.port=8088` and `demo.upstream.base-url=http://127.0.0.1:8088` share the port **only because the demo calls loopback**. Changing the server port to 8099 **does not automatically** update `WebClient`'s base URL. In real systems, the upstream is normally a different host, so the two settings must be managed independently.

`server.compression.enabled=true` does not guarantee a short `inbound-ok` response will be compressed, because size thresholds and content-type rules also apply; do not use this example to verify compression via the `Content-Encoding` header.

### 8.4. Complete Java File

Save as `src/main/java/com/example/reactive/ServerClientDemoApplication.java`:

~~~java
package com.example.reactive;

import java.time.Duration;

import reactor.core.publisher.Mono;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootApplication
public class ServerClientDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServerClientDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class HttpRolesConfiguration {

    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
    inboundServerCustomizer() {
        return factory -> factory.addServerCustomizers(
                server -> server.idleTimeout(Duration.ofSeconds(20)));
    }

    @Bean
    WebClient upstreamWebClient(
            WebClient.Builder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {

        return builder.baseUrl(baseUrl)
                .defaultHeader("X-Demo-Client", "client-demo")
                .build();
    }
}

@RestController
class DemoController {
    private final WebClient upstream;

    DemoController(@Qualifier("upstreamWebClient") WebClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/api/hello")
    Mono<String> hello() {
        return Mono.just("inbound-ok");
    }

    @GetMapping("/upstream/data")
    Mono<String> upstream(
            @RequestHeader(name = "X-Demo-Client",
                           required = false) String marker) {
        return Mono.just("upstream-ok|marker="
                + (marker == null ? "none" : marker));
    }

    @GetMapping("/api/proxy")
    Mono<String> proxy() {
        return upstream.get()
                .uri("/upstream/data")
                .retrieve()
                .bodyToMono(String.class)
                .map(body -> "proxy:" + body);
    }
}
~~~

**Part-by-part explanation:**

1. `inboundServerCustomizer()` adds configuration to the **server factory**, capping server-side idle connection time. It does not configure outbound `WebClient` read timeouts.
2. `upstreamWebClient(...)` accepts **Boot's auto-configured builder** and creates a client with its own base URL and default header. It creates no server listener and does not change the inbound HTTP port.
3. Controller `/api/hello` responds directly from the server; no outbound call occurs.
4. Controller `/upstream/data` acts as the upstream endpoint in the demo. It echoes back the header sent by **`WebClient`** in the response string so you can observe it.
5. Controller `/api/proxy` makes a new outbound HTTP request with `WebClient` to `/upstream/data`, reads the body, and returns it prefixed. It returns `Mono<String>` without calling `block()` on a reactive request thread.
6. One application can use the same Reactor Netty runtime for both roles; **two separate HTTP requests** still occur and can be logged or metered independently.

This is a demo application. In production, having `WebClient` call back into the same server is unnecessary outside specialized architectures; replace `baseUrl` with your real upstream and manage access tokens, timeouts, retries, circuit breakers, and DNS/proxy rules properly.

### 8.5. Running and Checking Output

Requires Maven and JDK 17+; in the project directory run:

~~~bash
mvn spring-boot:run
~~~

Or use `./mvnw spring-boot:run` if the project has a wrapper (Windows: `mvnw.cmd spring-boot:run`).

Send requests:

~~~bash
curl -sS http://127.0.0.1:8088/api/hello
curl -sS http://127.0.0.1:8088/upstream/data
curl -sS http://127.0.0.1:8088/api/proxy
~~~

Exact expected bodies in order:

~~~text
inbound-ok
upstream-ok|marker=none
proxy:upstream-ok|marker=client-demo
~~~

Each line represents the body of **one separate command**, not combined stdout guaranteed to print on three lines in a shell: the controllers return strings without trailing newlines, and `curl -sS` does not append newlines automatically.

Observe what this shows: `/api/hello` proves the server handles inbound traffic, `/upstream/data` shows the incoming header when called directly, and `/api/proxy` shows `WebClient` issued **a new outbound request** carrying `X-Demo-Client`. That the proxy endpoint works does not mean the client reads `server.port`; it works only because `demo.upstream.base-url` points to loopback 8088.

### 8.6. Automated Testing on a Random Port

In HTTP integration tests, use a random port to avoid conflicts. Create `src/test/java/com/example/reactive/ServerClientDemoTest.java`:

~~~java
package com.example.reactive;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServerClientDemoTest {

    @LocalServerPort
    int port;

    @Autowired
    WebClient.Builder clientBuilder;

    @Test
    void serverPortAndOutboundClientAreIndependent() {
        assertTrue(port > 0);

        WebClient testClient = clientBuilder.clone()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        String response = testClient.get()
                .uri("/api/hello")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(5));

        assertEquals("inbound-ok", response);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

`@SpringBootTest(RANDOM_PORT)` starts a real embedded reactive server on an OS-assigned port, and `@LocalServerPort` receives the actual port. The test builds a separate outbound `WebClient` targeting that port via `builder.clone()`. It **does not assume** `server.port` is always 8088.

Note: the application's `upstreamWebClient` bean still uses `demo.upstream.base-url=...:8088` in this test. The test calls `/api/hello`, not `/api/proxy`; to test `/api/proxy` under a random port, configure the upstream URL dynamically to that port or start an independent mock upstream HTTP server. This illustrates why remote endpoint configuration should stay decoupled from `server.port`.

`block(Duration)` on a **JUnit test thread** is acceptable to retrieve the result for assertion; never copy that blocking pattern into production WebFlux handlers.

## 9. Common Misconfigurations

### Mistake 1. Changing server.port expecting WebClient to call a different upstream

~~~properties
server.port=9090
~~~

This property changes only the port on which **the application listens for requests**. To point `WebClient` to a new destination, change the value passed to `WebClient.Builder.baseUrl(...)`, the request URI, service discovery, or HTTP client configuration.

### Mistake 2. Tuning HttpServer timeouts expecting WebClient timeouts to change

`NettyReactiveWebServerFactory.addServerCustomizers(server -> server.idleTimeout(...))` configures only the server. To adjust connect/read/response timeouts on outgoing calls, configure the HTTP client connector or reactive operators in the right place. There is no single "Netty timeout" that governs both traffic directions.

### Mistake 3. Creating an HttpClient expecting the server to use it

`HttpClient.create()` belongs to Reactor Netty outbound. Passing an `HttpClient` into `ReactorClientHttpConnector` applies only to `WebClient`s using that connector. The HTTP server is still initialized by Spring Boot from the reactive server factory.

### Mistake 4. Setting server.ssl.* to make WebClient trust an upstream CA

A server's SSL certificate/private key does not replace `WebClient`'s truststore. When an upstream presents an untrusted certificate, configure a client SSL bundle/trust chain properly instead of disabling TLS verification.

### Mistake 5. Using WebFluxConfigurer to change WebClient baseUrl

`WebFluxConfigurer` configures WebFlux server-side request handling, not HTTP client factories. Create/inject `WebClient.Builder` and configure upstream base URLs separately.

### Mistake 6. Calling WebClient.create() and expecting Boot to apply all customizers

Spring Framework's static factory methods do not automatically inherit Boot auto-configuration. When you want shared HTTP resources, codecs, observability, and standard connector setup, prefer Boot's injected builder.

### Mistake 7. Treating shared resources as shared business configuration

Even when client and server share a `ReactorResourceFactory`, they maintain independent auth, TLS, routes, timeouts, and error handling. If you replace the shared resource bean, test both server and client behavior.

### Mistake 8. Calling .block() inside a WebFlux handler

Blocking on a Netty event loop can trigger `IllegalStateException` or starve request processing. Return `Mono`/`Flux` or compose with `map`/`flatMap`. For unavoidable blocking libraries, offload onto an appropriate scheduler and evaluate resource impact.

### Mistake 9. Mixing HTTP client errors with HTTP server errors

`WebClient.retrieve()` emits an error signal by default on 4xx/5xx upstream responses. An upstream failure can bubble up as a server error if unhandled, yet its origin is an **outbound HTTP call**. Separate server-side 5xx logs/metrics from client-side timeouts, DNS, SSL, or upstream statuses. Design error mapping and circuit breakers deliberately.

### Mistake 10. Using Boot property namespaces from a different version

Boot 3.5: `spring.http.reactiveclient.*`. Boot 4.1: `spring.http.clients.*`, with reactive connector selection via `spring.http.clients.reactive.connector`. Always check **Common Application Properties** for your exact build and verify with integration tests, especially during major upgrades.

## 10. Diagnosing from Real Symptoms

| Symptom | Which side to check first? | Signals / actions |
|---|---|---|
| Cannot curl `localhost:8088` | Inbound server | `server.port`, `server.address`, web application type, startup logs, firewall |
| Local route returns 200 but calling upstream fails | Outbound client | `baseUrl`, DNS, proxy, TLS trust, connect/read timeouts, auth |
| Changed `server.port` but `WebClient` still calls old port | Client config | Separate remote base URL or service discovery configuration |
| `Connection refused` from `WebClient` | Outbound | Wrong host/port, upstream not listening, network |
| `DataBufferLimitException` decoding response | Client codecs / buffering | Check `WebClient` codec limit, payload size, and streaming |
| 502/504 at gateway in front of app | Gateway + server path | Timeouts and upstream health at reverse proxy; correlate with server logs |
| Reactor Netty threads/pools not released | Shared resources / lifecycle | `ReactorResourceFactory`, custom connectors/pools, context shutdown |
| SSL handshake error calling remote HTTPS | Client TLS | CA, hostname, mTLS client certificate, client SSL bundle |
| SSL handshake error from browser into app | Server TLS | `server.ssl.*`, certificate/private key, binding, reverse proxy |
| After switching to Jetty/Tomcat server, `WebClient` still uses Netty | Not necessarily a bug | HTTP server and HTTP client select connectors independently |
| Server HTTP response lacks gzip | Server compression policy | Content type, response size threshold, client `Accept-Encoding` |
| `RANDOM_PORT` test passes `/api/hello` but fails `/api/proxy` | Outbound config | Proxy client still calls fixed port 8088 rather than dynamic test port |

## 11. Safe Production Design Process

1. **Map each traffic direction.** Explicitly diagram inbound requests into the app and outbound calls to downstreams; document host/port/TLS/trust/timeouts at every boundary.
2. **Configure the server with properties first.** `server.port`, `server.address`, SSL, compression, forwarded headers; only when insufficient, use `WebServerFactoryCustomizer` for your server engine.
3. **Configure clients per upstream.** Inject Boot's `WebClient.Builder`, configure dedicated `baseUrl`, credentials/headers, and policies; avoid sharing one mutable global builder across unrelated clients.
4. **Bound resources and timeouts.** Connect/read timeouts, overall request deadlines, connection pooling; verify whether each setting applies to `HttpClient` or `HttpServer`.
5. **Apply TLS and security in the right direction.** Server has its own certificate; client has its own trust policy; enforce SSRF protections, redirect policies, proxy rules, authentication, and authorization.
6. **Verify resource sharing.** If using `ReactorResourceFactory` or custom connectors, verify lifecycle and pool/loop settings for both roles.
7. **Write matching tests.** Test inbound via random ports and outbound via mock upstream servers/contract tests; cover errors, timeouts, SSL, and connection leaks.
8. **Observe both roles separately.** Distinguish inbound request metrics, outbound client metrics, trace ID propagation (under explicit policy), timeouts, and upstream statuses.
9. **Verify version differences before migrating.** Especially Boot 3.5 → 4.x, where HTTP client property names, `NettyReactiveWebServerFactory` imports, starters, and customization APIs may differ.

**Conclusion:** The reactive server and `WebClient` are **two components operating in opposite directions**: the server receives HTTP and is configured via `server.*`/reactive server factories; `WebClient` initiates HTTP and is configured via builders/`ClientHttpConnector`/client settings. They can share I/O resources, yet they never automatically share base URLs, ports, TLS identities, timeouts, or security policies.

## Official Documentation for Reference

- Spring Boot 3.5 — Reactive Web Applications and Customizing Reactive Servers: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Embedded Web Servers and `WebServerFactoryCustomizer`: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — Calling REST Services / WebClient Runtime / HTTP Connector Configuration: https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.1 — Reactive Web Applications (server factory API packages may change): https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot 4.1 — Calling REST Services / HTTP clients namespace: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Framework — WebClient configuration, codecs, clientConnector, resources: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Boot 3.5 API — NettyReactiveWebServerFactory: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html
- Reactor Netty — HTTP Server Configuration/Timeout: https://projectreactor.io/docs/netty/release/reference/http-server.html