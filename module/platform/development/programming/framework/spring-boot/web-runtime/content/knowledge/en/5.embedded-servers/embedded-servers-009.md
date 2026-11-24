# Customizing NettyReactiveWebServerFactory and HttpServer in Spring Boot

## 1. Objectives

When Spring Boot runs a **Spring WebFlux** application with **Reactor Netty** as the embedded HTTP server, the central integration layer is NettyReactiveWebServerFactory. This factory creates NettyWebServer, while HTTP/TCP-layer settings are applied to **reactor.netty.http.server.HttpServer** before the server binds and begins accepting requests.

This lesson explains how to customize properly at both levels:

1. **Spring Boot web server factory level**: port, bind address, SSL, HTTP/2, compression, lifecycle, and Reactor Netty resources.
2. **Reactor Netty HttpServer level**: idle timeout, access log, wiretap, HTTP decoder, TCP/channel options, and Netty-specific hooks when needed.

Key principle: **prefer application.properties/application.yaml configuration; only use WebServerFactoryCustomizer when no suitable property exists; only replace the factory with a custom bean in genuinely special cases**. Do not spin up a separate HttpServer with HttpServer.create().bindNow() inside a customizer because it will not attach to the pipeline, port, and lifecycle managed by Spring Boot.

Examples in this lesson apply to **Spring Boot 3.3.x, Java 17+, Spring WebFlux, and Reactor Netty 1.1.x managed by Spring Boot**. Package names, APIs, and options can change in newer Spring Boot/Reactor Netty lines; verify the Javadoc for your exact version before porting code across versions.

## 2. Conditions for NettyReactiveWebServerFactory to Be Used

A typical reactive project declares:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

spring-boot-starter-webflux normally places Spring WebFlux and Reactor Netty onto the runtime classpath. When Spring Boot selects **WebApplicationType.REACTIVE**, matching auto-configuration provides a ReactiveWebServerFactory, which in the Reactor Netty case is NettyReactiveWebServerFactory.

**Note on stack selection:** If both spring-boot-starter-web (Spring MVC) and spring-boot-starter-webflux exist on the classpath, Spring Boot usually **prefers Servlet/Spring MVC**. In that situation, customizing NettyReactiveWebServerFactory will not customize the MVC HTTP server. You can explicitly select reactive via spring.main.web-application-type=reactive if dependencies and architecture genuinely fit.

Example forcing reactive when both starters are present:

~~~properties
spring.main.web-application-type=reactive
~~~

If only starter-webflux is present as in the complete example below, this declaration is usually unnecessary. Remember as well: Reactor Netty can be used as **WebClient's HTTP client** inside an MVC application; having Netty libraries on the classpath does not prove Netty is serving incoming requests to the application.

## 3. Related Classes and Hooks

~~~mermaid
flowchart TD
    A["SpringApplication / Reactive ApplicationContext"] --> B["ReactiveWebServerFactoryAutoConfiguration"]
    B --> C["NettyReactiveWebServerFactory"]
    D["server.* properties and factory customizers"] --> C
    E["WebServerFactoryCustomizer<NettyReactiveWebServerFactory>"] --> C
    C --> F["NettyServerCustomizer"]
    F --> G["Reactor Netty HttpServer builder"]
    C --> G
    G --> H["NettyWebServer: bind / start / stop"]
    H --> I["HTTP request -> Spring WebFlux HttpHandler"]
~~~

| Component | Role |
| --- | --- |
| ReactiveWebServerFactory | Interface creating an embedded reactive web server |
| NettyReactiveWebServerFactory | Spring Boot-provided factory for Reactor Netty |
| WebServerFactoryCustomizer<T> | Boot hook allowing factory adjustments before server creation |
| NettyServerCustomizer | Function customizing Reactor Netty's HttpServer; receives HttpServer, returns configured HttpServer |
| HttpServer | Fluent Reactor Netty builder defining server transport/HTTP settings |
| NettyWebServer | WebServer adapter whose lifecycle Boot manages and that attaches HttpHandler to Reactor Netty |
| HttpHandler | HTTP entry point of Spring WebFlux provided by the framework |

**Clear distinction:** NettyReactiveWebServerFactory belongs to package org.springframework.boot.web.embedded.netty; WebServerFactoryCustomizer belongs to org.springframework.boot.web.server; HttpServer belongs to reactor.netty.http.server. Spring Boot's NettyServerCustomizer is an adapter for transforming the HttpServer builder, not a Servlet Filter or WebFlux WebFilter.

## 4. Configuration Priority: Properties First, Customizer Second

### 4.1 Common Configuration via application.properties

~~~properties
# HTTP port and interface
server.port=8080
# Only use server.address if you genuinely need to bind a specific interface
# server.address=127.0.0.1

# Idle connection limit on Netty
server.netty.idle-timeout=30s

# HTTP request decoder
server.netty.max-initial-line-length=4KB
server.max-http-request-header-size=8KB

# Enable response compression when beneficial
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=application/json,text/plain,text/html
~~~

These values are tuning examples, not fixed recommendations for every system. Test with real requests, keep-alive connections, streaming, and proxy/load balancer policies. For many applications, properties like these are enough; no custom Netty code is needed.

Notable properties in Spring Boot 3.3:

| Property | Meaning |
| --- | --- |
| server.port | HTTP port; 0 requests the OS to select a free port |
| server.address | Network address the web server binds to |
| server.netty.idle-timeout | Maximum time a Netty channel stays idle; if unspecified it may wait indefinitely |
| server.netty.connection-timeout | Netty channel connection timeout; not the total business processing timeout |
| server.netty.max-initial-line-length | Maximum request-line length accepted by the HTTP decoder |
| server.netty.initial-buffer-size | Initial buffer size for HTTP request decoding |
| server.netty.validate-headers | Validate headers during decoding |
| server.netty.max-keep-alive-requests | Maximum requests allowed on a single connection |
| server.max-http-request-header-size | HTTP header size limit; exact enforcement depends on the embedded server |
| server.compression.* | Response compression settings, threshold, and media types |
| server.ssl.* / server.ssl.bundle | SSL/TLS, certificates, bundles |
| server.http2.enabled | Enable HTTP/2 support if server/protocol combination permits |
| server.shutdown | Graceful shutdown mechanism when configured accordingly |
| spring.lifecycle.timeout-per-shutdown-phase | Timeout per shutdown phase |

**Do not confuse timeouts:** connection timeout, idle timeout, read timeout, request timeout, and WebClient response timeout apply to different stages. There is no single all-purpose property limiting every kind of request/connection. Each Spring Boot version's property list is the authoritative source for exact names and semantics.

### 4.2 When Should You Write a Customizer?

Use a customizer when you need a Reactor Netty API without a matching Boot property, or need to apply a policy synthesized from multiple config values. Examples: conditionally enabling Reactor Netty access logging, controlled wiretap, TCP channel hooks, or customizing HttpServer construction.

Do not convert all server.* properties into code by default. Using properties provides clear benefits: per-environment configuration, easy auditing, changes without rebuilding, and simpler debugging.

## 5. WebServerFactoryCustomizer<NettyReactiveWebServerFactory>

Primary API:

~~~java
public interface WebServerFactoryCustomizer<T extends WebServerFactory> {
    void customize(T factory);
}
~~~

In Spring Boot, you can register a WebServerFactoryCustomizer as a Spring bean. It is invoked before the embedded server starts, allowing factory adjustments at the right moment.

Simple example for Spring Boot 3.3:

~~~java
package com.example.nettydemo;

import java.time.Duration;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.stereotype.Component;

@Component
public class NettyFactoryCustomizer
        implements WebServerFactoryCustomizer<NettyReactiveWebServerFactory> {

    @Override
    public void customize(NettyReactiveWebServerFactory factory) {
        factory.addServerCustomizers(httpServer ->
                httpServer.idleTimeout(Duration.ofSeconds(30))
                          .accessLog(true));
    }
}
~~~

Layer-by-layer explanation:

1. @Component makes the class a bean discovered by Spring Boot.
2. Generic NettyReactiveWebServerFactory restricts the customizer to the Reactor Netty reactive factory rather than accidentally applying to a Tomcat Servlet factory.
3. factory.addServerCustomizers accepts a lambda of type NettyServerCustomizer.
4. The lambda transforms the HttpServer builder with idleTimeout and accessLog; it **returns** the resulting builder so Boot can finish constructing the server.
5. There is no bindNow, no HttpServer.create call, and no second server started. Spring Boot continues orchestrating port, HttpHandler, resources, and lifecycle.

NettyServerCustomizer is an **HttpServer-level** hook, whereas WebServerFactoryCustomizer is a **factory-level** hook. Understanding this layering is essential; they are not two independent server frameworks.

### 5.1 addServerCustomizers or setServerCustomizers?

NettyReactiveWebServerFactory provides the methods:

~~~text
addServerCustomizers(NettyServerCustomizer...)
setServerCustomizers(Collection<? extends NettyServerCustomizer>)
getServerCustomizers()
~~~

- addServerCustomizers: **appends** customizers; suitable for most applications.
- setServerCustomizers: **replaces** the existing collection of customizers. Calling it carelessly can wipe out customizers added by Boot or other libraries.
- getServerCustomizers: returns a modifiable collection, though using addServerCustomizers usually expresses intent more safely and clearly.

Boot applies several framework customizers automatically. Per Spring Boot 3.3 documentation, Boot's auto-configured WebServerFactoryCustomizers typically have order 0 and run before application customizers unless you set an explicit order. When multiple customizers modify the same setting, the outcome also depends on **builder transformation order**; do not assume "properties always win" or "code always wins" in every scenario.

### 5.2 setPort and Factory-Level Settings

If an application needs to change the port programmatically:

~~~java
@Override
public void customize(NettyReactiveWebServerFactory factory) {
    factory.setPort(9090);
    factory.addServerCustomizers(server ->
            server.idleTimeout(Duration.ofSeconds(30)));
}
~~~

This snippet illustrates replacing the customize method body in the previous class; it is **not a standalone Java file**. For standard port changes, use server.port=9090 instead so the port is not hardcoded and RANDOM_PORT tests remain unaffected. If you use factory.setPort(9090), pay attention to ordering and its impact on Spring Boot tests, containers, and deployment environments.

The factory also exposes configuration for address, HTTP/2, compression, SSL, and lifecycle timeouts. For SSL/certificates, prefer properties and SSL bundles rather than building SslContext manually in code unless there is a special requirement.

## 6. Customizing Reactor Netty HttpServer Directly

A NettyServerCustomizer transforms the current HttpServer and must return the updated builder instance.

Illustrative example:

~~~java
factory.addServerCustomizers(httpServer ->
        httpServer.idleTimeout(Duration.ofSeconds(45))
                  .accessLog(true)
                  .wiretap(false));
~~~

This belongs inside customize(...), not a standalone program. wiretap(false) is shown to illustrate disabling it; it is usually off by default, so there is no need to declare it in standard setups.

Commonly used APIs:

| HttpServer API | Purpose | Things to watch |
| --- | --- | --- |
| idleTimeout(Duration) | Close connections idle too long | Not equivalent to service processing timeout |
| accessLog(boolean) | Enable/disable Reactor Netty HTTP access log | Do not log tokens or private data in custom formats |
| wiretap(boolean) | Log network-level details for debugging | Can produce massive logs and expose sensitive payloads/headers |
| compress(boolean) | Enable HTTP response compression in Netty | Usually prefer Boot's server.compression.* |
| httpRequestDecoder(...) | Customize request parser/decoder | Raising header/request-line limits carries security considerations |
| protocol(...) | HTTP server protocol options | Must align with HTTP/2, TLS, proxies, and clients |
| secure(...) | Configure TLS at the Netty level | Usually prefer Boot's server.ssl.* |
| doOnConnection(...) | Hook when a channel/connection is created | Mutating the pipeline requires understanding event loops and Netty |
| option(...) / childOption(...) | Set TCP/channel options | Only pick options valid for server channel/accepted channels |
| metrics(...) | Configure Reactor Netty metrics | Avoid unbounded-cardinality URI tags |

Some methods or overloads may differ between Reactor Netty 1.1.x and 1.2/1.3. To avoid compilation failures, check Javadocs and your project's dependency lock; do not copy snippets from newer documentation assuming they work on Spring Boot 3.3.

### 6.1 Immutable-Style Fluent Configuration

In Reactor Netty, HttpServer configuration steps follow a fluent pattern, generally returning an updated HttpServer. Thus the correct pattern is:

~~~java
factory.addServerCustomizers(server ->
        server.idleTimeout(Duration.ofSeconds(30)));
~~~

A common mistake is calling a method and discarding the returned builder:

~~~java
factory.addServerCustomizers(server -> {
    server.idleTimeout(Duration.ofSeconds(30));
    return server; // May drop the configuration on the returned builder!
});
~~~

Prefer expression lambdas so the configured HttpServer is always returned, especially when chaining multiple operations.

## 7. Complete Runnable Example with Java 17 and Gradle

The example below exposes a GET /ping endpoint using Spring WebFlux with Reactor Netty as the embedded server. We configure port and compression via properties, and idle timeout and access log via a factory customizer.

### 7.1 Project Structure

~~~text
netty-boot-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/nettydemo/
    │   │   ├── NettyBootApplication.java
    │   │   └── NettyFactoryCustomizer.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/nettydemo/
            └── NettyBootApplicationTests.java
~~~

### 7.2 File settings.gradle

~~~groovy
rootProject.name = 'netty-boot-demo'
~~~

### 7.3 File build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use only starter-webflux, **do not add starter-web**, so Boot does not default to Servlet/MVC. The Gradle plugin manages aligned dependencies in the Boot 3.3 family; avoid pinning different Reactor Netty/Netty versions without a tested compatibility reason.

### 7.4 File NettyBootApplication.java

~~~java
package com.example.nettydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class NettyBootApplication {

    public static void main(String[] args) {
        SpringApplication.run(NettyBootApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

A single Java file contains one public class NettyBootApplication and one package-private class PingController; both sit in the same package so component scan discovers the controller.

### 7.5 File NettyFactoryCustomizer.java

~~~java
package com.example.nettydemo;

import java.time.Duration;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.stereotype.Component;

@Component
public class NettyFactoryCustomizer
        implements WebServerFactoryCustomizer<NettyReactiveWebServerFactory> {

    @Override
    public void customize(NettyReactiveWebServerFactory factory) {
        factory.addServerCustomizers(server ->
                server.idleTimeout(Duration.ofSeconds(30))
                      .accessLog(true));
    }
}
~~~

When Spring Boot builds the reactive server, customize is invoked, adding the NettyServerCustomizer to the factory. Reactor Netty then receives idleTimeout and accessLog on the Boot-managed HttpServer builder.

### 7.6 File application.properties

~~~properties
server.port=8080
server.compression.enabled=true
server.compression.min-response-size=2KB
logging.level.reactor.netty.http.server.AccessLog=INFO
~~~

Do not declare server.netty.idle-timeout in this file because code already sets 30 seconds; this avoids two configuration sources affecting the same parameter in this exercise. The /ping endpoint returns only four characters, so there is no reason to expect the response to be compressed when min-response-size=2KB.

### 7.7 Running and Verifying

In the project directory, using installed Gradle or the Gradle wrapper if present:

~~~bash
gradle bootRun
~~~

In another terminal:

~~~bash
curl -i http://127.0.0.1:8080/ping
~~~

Expected result is HTTP 200 and response body:

~~~text
pong
~~~

Specific headers such as Date, Content-Type, Content-Length, and Connection can depend on server and request details, so do not assert a fixed header set across environments. Access logs are written by the Reactor Netty logger when logging configuration permits; exact formatting and flush timing depend on the logging system. Use logs to confirm the accessLog customizer actually took effect; do not treat an endpoint returning 200 as proof that every tuning property was applied.

To run on a different port, pass application arguments:

~~~bash
gradle bootRun --args='--server.port=9090'
~~~

Because the customizer does not call factory.setPort, server.port=9090 can change the port without modifying code.

## 8. Integration Testing: Real HTTP Server and RANDOM_PORT

Good tests should not require port 8080 to be free. Spring Boot tests can pick an ephemeral port and then use WebTestClient against the real server.

File NettyBootApplicationTests.java:

~~~java
package com.example.nettydemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NettyBootApplicationTests {

    @LocalServerPort
    private int port;

    @Test
    void respondsOverEmbeddedNetty() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get()
                .uri("/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

This test proves the reactive application starts a real HTTP server on an OS-allocated port and the endpoint returns the expected body. Verifying **an exact 30-second idleTimeout** requires a test holding a TCP connection idle and observing the server close it; a single HTTP GET is insufficient.

With @SpringBootTest(webEnvironment = MOCK), the server does not bind TCP as with RANDOM_PORT, making it unsuitable for testing Netty connection behavior.

## 9. Timeouts: Do Not Mix Up Four Concepts

### 9.1 Idle Timeout

HttpServer.idleTimeout(Duration) limits how long a connection stays open waiting for the next HTTP request while idle. Common setup:

~~~java
factory.addServerCustomizers(server ->
        server.idleTimeout(Duration.ofSeconds(30)));
~~~

Reasonable values depend on keep-alive clients and proxies. Setting it too short increases reconnects; too long keeps unnecessary connections open. Do not assume a controller taking longer than 30 seconds will always be cut off by idleTimeout; it is not a business-method execution timeout.

### 9.2 Connection Timeout

server.netty.connection-timeout is the Netty channel connection timeout as modeled by Spring Boot. It is not WebClient.connectTimeout, does not guarantee a cap on total HTTP body read duration, and does not replace business deadlines.

### 9.3 HTTP Request Read Timeout

When requiring limits on body read rate or total request read duration, inspect the HttpServer API for **your exact Reactor Netty version**. Newer docs may show readTimeout/requestTimeout, though you should not assume every overload exists in 1.1.x. If a newer API is unavailable, choose a 1.1.x-compatible solution (such as proper pipeline handlers or proxy limits) and test slow uploads, streaming requests, and keep-alive.

When adding a Netty pipeline handler like ReadTimeoutHandler, understand units, byte-receive intervals, add/remove conditions, HTTP/2 interactions, and pooling; do not drop in a generic handler by guesswork since it easily closes valid connections prematurely.

### 9.4 WebClient Timeout Is a Separate Configuration

WebClient uses Reactor Netty HttpClient to make **outbound** calls. Tuning server HttpServer does not alter the HTTP client. To limit connect/response times when calling upstream services, configure ReactorClientHttpConnector, HttpClient, or reactive timeouts rather than modifying NettyReactiveWebServerFactory.

## 10. Response Compression and HTTP Decoder

### 10.1 Response Compression

Spring Boot supports response compression directly via:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=application/json,text/html,text/plain
~~~

At the Reactor Netty level there is HttpServer.compress(boolean), yet prefer server.compression.* to keep behavior aligned with Boot. Compression only helps when the client sends a matching Accept-Encoding and the response satisfies size/media-type thresholds; small payloads may remain uncompressed.

Do not enable compression indiscriminately on already-compressed data, sensitive data exposed to side-channel risks, or streaming responses where benefit is low. Measure CPU, throughput, and latency before and after.

### 10.2 HTTP Request Decoder and Header Limits

Several limits are best configured via properties:

~~~properties
server.netty.max-initial-line-length=8KB
server.max-http-request-header-size=16KB
server.netty.validate-headers=true
~~~

Raising limits lets the app accept valid long URLs or headers, yet expands resource-consumption surface and exposure to malformed requests. Cross-check with proxies/API gateways. On Reactor Netty, header limits have different semantics from some servlet containers; do not naively compare byte numbers between Netty and Tomcat as equivalent.

You can use httpRequestDecoder(...) on HttpServer when specialized options outside Boot properties are required, only after confirming the overloads and syntax of the installed Reactor Netty version.

## 11. Access Log, Wiretap, and Observability

### 11.1 HTTP Access Log

To enable access logs via Reactor Netty's API:

~~~java
factory.addServerCustomizers(server -> server.accessLog(true));
~~~

This snippet must live inside the factory customizer's customize method; it is not a standalone class. You can configure the logger:

~~~properties
logging.level.reactor.netty.http.server.AccessLog=INFO
~~~

Access logs focus on HTTP requests: method, URI, status, size, and other fields depending on the formatter. Do not log full JWTs, Authorization headers, cookies/sessions, or personal data in custom log patterns. Under high traffic, consider async appenders, log rotation, and I/O cost.

Reactor Netty also supports enabling access logs via system property reactor.netty.http.server.accessLogEnabled where supported by the environment. When combined with programmatic accessLog(...), verify precedence on your exact Reactor Netty version.

### 11.2 Wiretap for Network-Level Debugging

HttpServer.wiretap(true) exposes detailed network data. It helps when investigating protocol errors, yet can generate huge logs and leak sensitive HTTP payloads or headers.

Example **to enable only in controlled test environments**:

~~~java
factory.addServerCustomizers(server -> server.wiretap(true));
~~~

Besides calling wiretap(true), enable the appropriate logging level on Reactor Netty loggers; otherwise expected output may not appear. Turn it off after debugging; never leave it enabled unrestricted in production.

### 11.3 Metrics and Tracing

Spring Boot Actuator/Micrometer and Reactor Netty offer distinct metrics capabilities. Using WebServerFactoryCustomizer does not automatically expose a /actuator/prometheus endpoint. If Prometheus is needed, add the dependency and configure exposure, registry, and access control appropriately. Never generate metric tags from raw URL paths containing unbounded IDs/UUIDs, which can cause cardinality explosions.

## 12. TLS, HTTP/2, and Reverse Proxies

### 12.1 TLS via Boot Configuration

For HTTPS, prefer Spring Boot SSL properties/SSL bundles:

~~~properties
server.port=8443
server.ssl.bundle=server
~~~

This snippet **is only an example referencing an SSL bundle named server**. The application must declare the actual bundle and supply valid certificates/keys; those two lines alone do not create certificates. Manage secrets through secret stores or deployment config, never commit passwords/private keys into repositories.

Spring Boot also supports server.ssl.key-store and related properties when using a Java KeyStore. Do not mix bundle config with incompatible standalone key-store properties.

### 12.2 HTTP/2

~~~properties
server.http2.enabled=true
~~~

Working HTTP/2 requires the right combination of protocol, TLS/ALPN if using h2 over TLS, dependencies, and client support. Reactor Netty can serve h2c and h2 depending on configuration. Do not just call protocol(...) on HttpServer while forgetting TLS or conflicting with Boot's settings.

### 12.3 Forwarded Headers Behind a Load Balancer

Behind a reverse proxy, the application may see internal remote addresses and schemes instead of client-facing HTTPS. Spring Boot provides forwarded-header strategies, for example:

~~~properties
server.forward-headers-strategy=framework
~~~

native and framework values behave differently depending on stack and version. NettyReactiveWebServerFactory also has setUseForwardHeaders(boolean), though avoid enabling overlapping mechanisms without understanding their interaction.

**Security warning:** never trust X-Forwarded-* or Forwarded headers from untrusted clients. Proxy configuration must strip/overwrite spoofed headers and pass forwarded information only from trusted hops; test scheme, host, redirect URLs, and client IP before shipping to production.

## 13. Netty Resources: Event Loop, Connections, and Memory

Netty relies on event loops and non-blocking I/O. Correct server configuration is not enough if controllers or services invoke JDBC/blocking HTTP/disk I/O directly on event-loop threads for long durations.

Considerations:

- Avoid block() and long blocking operations on the Netty event loop.
- When integrating blocking libraries, offload to an appropriate bounded scheduler and account for thread-hopping overhead.
- Monitor event-loop saturation, connection counts, direct memory, and heap as throughput scales.
- Tune event-loop counts, native transport, and Reactor Netty resources from load tests, not random numbers found online.
- Never create/dispose LoopResources inside request handlers; server resources must follow the application lifecycle.
- When customizing ReactorResourceFactory via factory.setResourceFactory(...), clarify ownership/lifecycle and resource sharing with HttpClient. Never override the resource factory merely to change port or idle timeout.

NettyReactiveWebServerFactory provides setResourceFactory(ReactorResourceFactory) and setLifecycleTimeout(Duration). These are advanced hooks. Boot's managed factory already coordinates server resources and shutdown; replacing them without a plan can lead to thread leaks, hung shutdowns, or inconsistent client/server configurations.

## 14. When and in What Order Are Customizers Applied?

WebServerFactoryCustomizer beans are processed early in the ApplicationContext lifecycle, before the factory binds the server. Boot uses a BeanPostProcessor to apply customizers, and then creates the server.

Key points:

1. **Customizer beans have an order**: @Order/Ordered can determine execution timing. Do not tweak order as a "quick patch" without knowing which customizer mutates the same setting.
2. **NettyServerCustomizers have an order inside the factory**: addServerCustomizers appends to the existing collection. Two callbacks setting idleTimeout can produce order-dependent results.
3. **Early bean instantiation**: avoid injecting a heavy bean graph into WebServerFactoryCustomizer if it triggers eager initialization, circular dependencies, or uses the web server before creation.
4. **Final customization** must be checked against server.* properties and auto-configured factory customizers.
5. **Declaring your own NettyReactiveWebServerFactory bean** is a last resort; auto-configured customizers may still run, while you take responsibility for lifecycle/resources and defaults.

There is no normal reason to call factory.getWebServer(...) manually from @Configuration or a service. That belongs to Boot when initializing the web application context.

## 15. When Does Netty Customization Have No Effect?

| Symptom | What to check |
| --- | --- |
| App reports embedded Tomcat instead of Netty | Is spring-boot-starter-web causing Boot to pick SERVLET? |
| Customizer bean is not called | Is the bean in component scan? Correct generic NettyReactiveWebServerFactory? Actually running Reactor Netty reactive? |
| Set idle timeout yet connections stay open long | Looking at HTTP server connections or WebClient connections? Proxy/keep-alive? HTTP/2 multiplexing? |
| Changing server.port has no effect | Is another factory.setPort customizer, CLI arg, or env var overriding it? |
| Enabled accessLog yet no logs appear | Are accessLog(true), INFO logger, and matching log appender configured? |
| wiretap enabled yet logs missing | Are logging level/category configured properly? |
| Overly long headers return HTTP 431/400 | Check decoder/header limits on the server and upstream proxy layers |
| HTTPS fails to run | Are certificates/SSL bundle valid, along with server.port and matching protocol? |
| HTTP/2 not working | HTTP/2 config, ALPN, TLS/h2c, proxy, and client |
| High CPU despite non-blocking Netty | Blocking on event loop, synchronous logging, compression/crypto, or high-cardinality metrics? |
| Startup fails missing ReactiveWebServerFactory | Check starter-webflux/reactor-netty runtime dependencies, WebApplicationType, and auto-configuration |
| Startup fails port already in use | Inspect listening port and PID; change port or stop the old instance |
| Wrong bean/port in tests | Use RANDOM_PORT, avoid hardcoding factory.setPort, and verify active test profile |

Distinguish **server failed to start** from **server started but requests do not reach the expected route**. Getting 404 on /unknown means the server may be healthy; check paths, mappings, and proxies before blaming the Netty factory.

## 16. How to Debug When Customization Does Not Take Effect

### 16.1 Check the Runtime Classpath

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Look for spring-boot-starter-webflux, spring-boot-starter-reactor-netty, and ensure spring-boot-starter-web is not pulled in accidentally if you expect Boot to pick REACTIVE automatically.

### 16.2 Inspect the Auto-Configuration Condition Report

~~~bash
gradle bootRun --args='--debug'
~~~

Check ReactiveWebServerFactoryAutoConfiguration, NettyReactiveWebServerFactory, web application type, and which auto-configurations matched. Debug logs may include sensitive settings; redact before sharing.

### 16.3 Check Listening Ports

On Linux:

~~~bash
ss -ltnp 'sport = :8080'
~~~

On Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

This command only shows sockets, not whether a Netty customizer ran. Combine with logs, endpoint tests, and targeted tests of the tuned behavior.

### 16.4 Verify Behavior Matching Each Customization

- Port change: curl the new port.
- Access log: enable logger, send a request, and inspect logs.
- Idle timeout: hold a keep-alive connection idle past the configured duration and observe close.
- Compression: send matching Accept-Encoding for a sufficiently large response; check Content-Encoding and CPU load.
- Header limit: send requests with headers near the limit, verifying responses without exhausting resources.
- TLS: verify certificate chain, hostname, and negotiated protocol with a standard client.
- HTTP/2: verify negotiated protocol via a matching client/proxy.

Avoid seeing a bean exist and marking "tuning successful"; test **observable runtime behavior**.

## 17. Design Mistakes to Avoid

### Mistake 1: Starting a Second Server Inside a Customizer

~~~java
// Wrong intent for a Spring Boot embedded web server:
HttpServer.create().port(9090).bindNow();
~~~

This opens a manually managed listener unattached to Spring WebFlux HttpHandler, lifecycle, Actuator, and Boot's server.port. Especially dangerous when invoked during bean startup and accidentally grabbing ports.

**Right:** register a WebServerFactoryCustomizer and return the customized HttpServer builder so Boot starts/stops the server.

### Mistake 2: Replacing the Entire Server Customizer Collection When Only Adding One Hook

~~~java
// Avoid when merely adding a setting if you do not mean to replace existing customizers:
factory.setServerCustomizers(java.util.List.of(
        server -> server.idleTimeout(Duration.ofSeconds(30))));
~~~

This snippet illustrates code inside customize. It can wipe out pre-existing customizers. Usually use addServerCustomizers.

### Mistake 3: Using Server Code to Configure WebClient

HttpServer and HttpClient are different APIs. Configuring server idleTimeout does not tune client response times for upstream calls.

### Mistake 4: Checking Classpath While Forgetting Application Type

Having WebFlux APIs and reactor-netty artifacts does not prove Spring Boot chose REACTIVE if starter-web is also present.

### Mistake 5: Leaving Wiretap Enabled Unrestricted in Production

Wiretap can log deeply detailed traffic, increasing I/O overhead and risking sensitive data exposure.

### Mistake 6: Accidentally Overriding Resource Ownership

Creating/disposing LoopResources or separate servers outside Boot can cause thread leaks, port conflicts, hung graceful shutdowns, or hard-to-trace startup ordering.

## 18. Practical Implementation Checklist

1. Confirm the application runs **WebFlux + Reactor Netty** (not just WebClient).
2. Try standard server.* properties first.
3. Only use WebServerFactoryCustomizer when deeper APIs are needed.
4. Use addServerCustomizers rather than overwriting the collection when only adding hooks.
5. Inside the lambda, return the transformed HttpServer; never call bindNow.
6. Document the reason and order of any customizers that might conflict.
7. Use properties/SSL bundles for port, SSL, HTTP/2, and compression where feasible.
8. Identify which connection/request/response stage each timeout covers.
9. Avoid logging tokens or sensitive payloads in access logs/wiretap.
10. Keep Boot-managed Reactor Netty resource lifecycles intact unless there is a special requirement.
11. Write a RANDOM_PORT + real HTTP request test.
12. Test each server feature by observable behavior, not just compilation.

## 19. Summary

**NettyReactiveWebServerFactory** bridges a Spring Boot reactive web application and the embedded Reactor Netty server. **WebServerFactoryCustomizer** modifies the factory before the server starts; **NettyServerCustomizer** is the right way to transform the **HttpServer builder** during server construction. By default configure server.* properties; reserve customizers for deeper needs. Let Boot retain ownership of creating/binding/starting/stopping the server and validate settings via real runtime behavior.

## 20. References

- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — NettyReactiveWebServerFactory Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Reactor Netty — HTTP Server Reference (pick the version matching Reactor Netty in your project): https://projectreactor.io/docs/netty/release/reference/http-server.html