# Tomcat, Jetty, Undertow, and Reactor Netty in Spring Boot

## 1. Objectives and Scope

Spring Boot can launch an HTTP server directly inside the application's JVM process. This server is called an embedded web server. Four commonly encountered names are Apache Tomcat, Eclipse Jetty, Undertow, and Reactor Netty. They are not completely interchangeable across all applications: choosing a server must match the Spring MVC (Servlet) or Spring WebFlux (reactive) model, the Spring Boot version, how the application handles I/O, and deployment requirements.

After this lesson, you will be able to explain the role of an embedded server; distinguish a Servlet container from a reactive HTTP server; understand the Tomcat and Reactor Netty defaults; choose Jetty or Undertow for the right version; swap dependencies safely; configure ports, threads, timeouts, and shutdown; verify which server is actually running; and avoid common misconceptions about performance.

**Version note:** Spring Boot 3.x supports Tomcat, Jetty, Undertow, and Reactor Netty in the appropriate web stack combinations. Spring Boot 4.0 removed Undertow integration and its corresponding starter due to the Servlet 6.1 baseline. Dependency snippets using starter names in this lesson are written for Spring Boot 3.x; before applying them to Boot 4.x, check the documentation for the exact version branch you are using. Do not use a Boot 3.x guide to assume that Undertow is still supported in Boot 4.x.

## 2. What Is an Embedded Server?

Previously, many Java web applications were packaged as WAR files and deployed into a separately installed Tomcat or application server. With Spring Boot, the common model is packaging the application as an executable JAR containing the libraries and bootstrap mechanisms needed to run an HTTP server directly inside the application process.

Basic startup flow:

1. The JVM calls the application's main method.
2. SpringApplication creates and refreshes the ApplicationContext.
3. Spring Boot detects the web application type from the classpath and configuration.
4. Auto-configuration registers the appropriate WebServerFactory.
5. WebServerFactory creates the embedded server; the server binds to an address/port.
6. Spring connects the web framework to the server and starts accepting requests.
7. When the application context closes, Spring stops the server and releases resources.

The embedded server handles network connections, the HTTP protocol, sockets, requests/responses, I/O resource management, and the communication mechanism with the web framework. It does not replace Spring MVC/WebFlux, business beans, services, repositories, or Spring Security.

Advantages of the embedded server model:

- Easy to run the same artifact on a laptop, virtual machine, or container.
- Can package and test the application close to the real runtime environment.
- The server version is usually managed together with the application's dependencies.
- No need for a WAR deployment process onto a standalone server in common scenarios.
- Easy to run multiple independent instances with separate ports and environment configurations.

However, "embedded" does not mean zero operations. You still need to configure TLS/proxies, resource limits, timeouts, logs, health, readiness, security, graceful shutdown, and update server versions when security vulnerabilities arise.

## 3. Distinguishing Between Web Stack and HTTP Server

There are two different questions:

1. **Which web programming model does the application use?** Spring MVC/Servlet or Spring WebFlux/reactive.
2. **Which component receives HTTP connections?** Tomcat, Jetty, Undertow, or Reactor Netty.

Spring MVC uses the Servlet API. Tomcat, Jetty, and Undertow are Servlet containers in the corresponding supported Spring Boot versions. Spring MVC can handle asynchronous processing in some cases, but it does not turn into WebFlux simply by changing the container.

Spring WebFlux uses reactive mechanisms and appropriate HTTP adapters. Reactor Netty is the common default server for WebFlux. WebFlux can also run on Tomcat/Jetty via adapters rather than requiring Reactor Netty. In Spring Boot 3.x, Undertow is also an option listed in that branch's documentation for reactive servers.

Two conceptual flows:

~~~text
Spring MVC / Servlet
Client -> embedded Servlet container
       -> Servlet Filter chain
       -> DispatcherServlet
       -> Handler / Controller
       -> Response

Spring WebFlux / reactive
Client -> embedded HTTP server (usually Reactor Netty)
       -> reactive HttpHandler / WebFilter chain
       -> DispatcherHandler or functional router
       -> Mono / Flux / response publisher
       -> Response
~~~

The difference does not stop at the server name: a Servlet filter is jakarta.servlet.Filter; a reactive filter is org.springframework.web.server.WebFilter. Spring Security MVC typically uses SecurityFilterChain, while WebFlux uses SecurityWebFilterChain. Thread management and the requirement to avoid blocking on the event loop also differ.

In particular, adding spring-boot-starter-webflux to an MVC project to use WebClient does not automatically turn the HTTP server into Reactor Netty. When both Spring MVC and WebFlux are on the classpath, Spring Boot usually chooses the MVC configuration by default. If your intention is a reactive application, design the dependencies and application type properly from the start.

## 4. Comparing the Four Technologies

| Technology | Typical role | Processing model | Spring Boot 3.x | Key takeaway |
| --- | --- | --- | --- | --- |
| Apache Tomcat | Default Servlet container for Spring MVC | Connector/NIO, Servlet requests, and worker threads | Has Tomcat starter; used with MVC and WebFlux adapter | Default choice, broad ecosystem |
| Eclipse Jetty | Alternative Servlet container to Tomcat | Connector, thread pool, Jetty async mechanisms | Has Jetty starter; used with MVC and WebFlux adapter | Suitable when already experienced/integrated with Jetty |
| Undertow | Servlet container/HTTP server | XNIO architecture, I/O threads and worker threads | Has Undertow starter; used in Boot 3.x supported configurations | **Boot 4.0 dropped embedded Undertow support** |
| Reactor Netty | Reactive HTTP server, default for WebFlux | Netty event loop combined with Reactor | Has Reactor Netty starter, commonly used with WebFlux | Not a Servlet container for running Spring MVC |

The table above describes common models and does not claim that one server is always faster than another. Performance also depends on business logic, database, connection pool, logging, TLS, workload type, core count, resource limits, and configuration.

### 4.1. Tomcat

Apache Tomcat provides the Servlet environment for Spring MVC. When using spring-boot-starter-web in Spring Boot 3.x, the Tomcat starter is usually present via transitive dependency. Spring Boot automatically creates TomcatServletWebServerFactory and registers DispatcherServlet along with the appropriate Servlets/Filters.

Tomcat uses a connector to listen for HTTP connections; in a typical Servlet configuration, synchronous requests use worker threads. Servlet asynchronous APIs are also supported by Tomcat, so Tomcat should not be described as only capable of blocking I/O.

When choosing Tomcat:

- Reasonable for standard MVC APIs and systems already using Servlet/Spring Security MVC.
- Usually reduces configuration effort because it is the default widely covered in Spring Boot documentation.
- Easy to find documentation on connectors, threads, access logs, sessions, proxies, and TLS.
- Measure real load before tuning the thread pool; blindly increasing threads can increase memory usage, context switching, and pressure on the database.

Some Spring Boot 3.x properties specific to Tomcat are server.tomcat.threads.max and server.tomcat.max-connections. Their meanings differ: the number of open connections does not equal the number of requests processed concurrently by worker threads.

### 4.2. Jetty

Eclipse Jetty is also a Servlet container and can be embedded directly into Spring Boot. Jetty has its own connector/handler architecture and thread pool, supporting Servlet and asynchronous HTTP scenarios.

You can choose Jetty when your team is already familiar with operating Jetty, when you must integrate Jetty-specific features, or when benchmarks on a real workload show it is a good fit. Switching to Jetty does not mean rewriting all MVC controllers; the Spring MVC API still handles requests.

You need to monitor the thread pool, connectors, backlog, timeouts, TLS, and Jetty-specific configuration. Properties like server.jetty.threads.max apply to Jetty; server.tomcat.* properties do not automatically take effect once the server has been switched to Jetty.

### 4.3. Undertow

Undertow is an HTTP server and Servlet container based on XNIO, typically separating I/O threads from worker threads. On synchronous Servlet configurations, blocking work needs to be dispatched to an appropriate worker; I/O threads must not be occupied by long waiting operations.

In Spring Boot 3.x, Undertow can replace Tomcat using spring-boot-starter-undertow. Commonly seen properties include server.undertow.threads.io and server.undertow.threads.worker. These are parameters to size according to CPU and load, not "bigger is always better" values.

**Mandatory compatibility limit:** Spring Boot 4.0 requires Servlet 6.1 and dropped embedded Undertow support. Do not add Boot 3.x's Undertow starter to a Boot 4.x project and expect auto-configuration to work. When upgrading from Boot 3.x with Undertow to Boot 4.x, you must plan a migration to a still-supported server such as Tomcat or Jetty, and re-verify dependencies, properties, APIs, and test results.

### 4.4. Reactor Netty

Netty is an event-driven networking toolkit; Reactor Netty integrates Netty with Project Reactor and provides an HTTP server/client for the reactive model. With spring-boot-starter-webflux, Reactor Netty is usually the default HTTP server.

Requests are processed via event-loop threads and an asynchronous pipeline. If a handler returns Mono/Flux yet calls blocking JDBC, Thread.sleep, or long-blocking APIs on the event loop, the system can still stall. To leverage reactive well, you need to examine the entire dependency chain and I/O handling.

Reactor Netty does not implement the Servlet API in the role of a Servlet container. Therefore, it is not an option where you can simply swap a dependency to run an existing Spring MVC application as-is. To migrate from MVC/Tomcat to WebFlux/Reactor Netty, you need to review controllers, filters, security, sessions, validation, data access, and every blocking call.

Note: An MVC application can use Reactor Netty as an HTTP client via WebClient in certain dependency configurations. That does not prove the application's incoming request server is running on Reactor Netty.

## 5. How Does Spring Boot Decide the Server?

Spring Boot combines several factors:

1. Web application type: SERVLET, REACTIVE, or NONE.
2. Starters and libraries actually present on the runtime classpath.
3. Auto-configuration conditions and already-existing beans.
4. Specific override configurations provided by the application.

In a typical Boot 3.x branch:

| Main dependency | Default web stack | Default HTTP server |
| --- | --- | --- |
| spring-boot-starter-web | Spring MVC / Servlet | Tomcat |
| spring-boot-starter-webflux | Spring WebFlux | Reactor Netty |
| Both web and webflux | Usually Spring MVC | Tomcat if the Tomcat starter is still present |
| Starter web with Tomcat replaced by Jetty | Spring MVC / Servlet | Jetty |
| Starter web with Tomcat replaced by Undertow | Spring MVC / Servlet | Undertow (supported versions only) |

This is the default model; dependency exclusions, application type, and custom WebServerFactory beans can change the outcome. Do not determine the server by guessing from the project name. Inspect runtimeClasspath and startup logs.

Important factories:

- ServletWebServerFactory is the contract for creating an embedded Servlet server.
- TomcatServletWebServerFactory, JettyServletWebServerFactory, and UndertowServletWebServerFactory are the corresponding implementations in supported branches.
- ReactiveWebServerFactory is the reactive server contract.
- NettyReactiveWebServerFactory is the factory for Reactor Netty; there are also factories for the Tomcat/Jetty reactive adapters in matching versions.

Spring Boot selects and configures the factory via auto-configuration. WebServerFactoryCustomizer allows customizing the factory before the server starts; use supported properties first, and only use a code customizer if properties do not cover the requirement.

## 6. Spring MVC Example Running Default Tomcat

The example below targets **Spring Boot 3.3.x, Java 17+**, using Gradle Groovy DSL in a project that already has Gradle Wrapper. A minimal reference build configuration:

File build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a standalone example running in a Gradle project with a compatible wrapper. In a real project, use the plugin/dependency versions managed by the project instead of copying sample versions into an already-configured build.

File src/main/java/example/web/EmbeddedServerApplication.java:

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EmbeddedServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(EmbeddedServerApplication.class, args);
    }
}
~~~

File src/main/java/example/web/StatusController.java:

~~~java
package example.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }
}
~~~

Run on Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

After startup succeeds, call:

~~~bash
curl -i http://localhost:8080/api/status
~~~

JSON body result:

~~~json
{"status":"ok"}
~~~

The expected HTTP status is 200. Startup log lines usually indicate that Tomcat has started listening on a specific port; exact wording varies by version. If the application fails to bind the port, look for the root cause in the exception log.

To package:

~~~bash
./gradlew test
./gradlew bootJar
~~~

Then run the actual JAR filename in build/libs using java -jar. The filename is determined by the project's version and artifact configuration, not a fixed name for every project.

## 7. Switching from Tomcat to Jetty in Spring MVC

You need to **exclude the Tomcat starter** from the web starter's transitive dependencies and **add the Jetty starter**. In build.gradle for Boot 3.x, replace the corresponding dependencies block with:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Keep the two Java files from section 6 unchanged. Rebuild and run the application again, inspect the logs to confirm Jetty actually started, and verify GET /api/status still returns the same JSON.

This is a swap of the embedded Servlet server implementation, not a migration from Spring MVC to Spring WebFlux. Servlet filters, MVC controllers, and Servlet-style security configurations remain the primary concerns.

For Maven, the idea is the same: place an exclusion for spring-boot-starter-tomcat inside the spring-boot-starter-web dependency, then declare the spring-boot-starter-jetty dependency. Do not simply add Jetty while leaving all of Tomcat intact and guess which server the framework will pick.

## 8. Switching from Tomcat to Undertow in Spring Boot 3.x

In a **Boot 3.x project that still supports Undertow**, use:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-undertow'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The MVC controllers from section 6 can remain unchanged. Check dependencies, startup logs, HTTP responses, and integration tests before concluding the server switch succeeded.

**Do not apply this snippet to Spring Boot 4.0 or later** because the embedded Undertow starter was dropped from official support in 4.0. If your environment is upgrading versions, pick a server supported by the target Spring Boot version and address the related configuration changes.

## 9. Spring WebFlux and Reactor Netty

To build a reactive application, create a project with spring-boot-starter-webflux and without the MVC web starter. On Boot 3.x, the dependencies block of a minimal reactive project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot will use Reactor Netty by default when the starter and auto-configuration are intact.

File src/main/java/example/web/ReactiveStatusController.java in a separate WebFlux project:

~~~java
package example.web;

import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveStatusController {
    @GetMapping("/api/reactive-status")
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

A reactive application still needs a main class annotated with @SpringBootApplication as in section 6. When running the project with only the WebFlux starter:

~~~bash
./gradlew bootRun
curl -i http://localhost:8080/api/reactive-status
~~~

Expected JSON body:

~~~json
{"status":"ok"}
~~~

Mono.just in the example only illustrates the response type; it does not magically turn a blocking operation into a non-blocking one. In real applications, avoid blocking the event loop with Thread.sleep, synchronous JDBC, synchronous HTTP calls, or long synchronous file writes. For parts that must block, offload them from the event loop using an appropriate scheduler mechanism and re-evaluate the reactive benefit.

### 9.1. Can Jetty/Tomcat Be Used with WebFlux?

Yes. Spring WebFlux has adapters to run on certain Servlet containers, so distinguish "which server technology" from "whether the framework is MVC or WebFlux". In supported versions, you can replace Reactor Netty with Jetty or Tomcat via dependency exclusion and the corresponding starter.

Example Boot 3.x Gradle configuration replacing Reactor Netty with Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

You still need to verify that the target Spring Boot branch supports that combination, inspect the runtime classpath, and run real HTTP tests. WebFlux running on a Servlet container still uses the WebFlux programming model; it does not turn controllers into Spring MVC.

### 9.2. What Happens If Both Starters Are Added?

When a project has both spring-boot-starter-web and spring-boot-starter-webflux, Boot usually prefers MVC. Many projects use WebClient inside an MVC application, and that case is completely valid. To build a reactive server application, configure dependencies explicitly and check the ApplicationContext type; do not take the mere presence of reactor-netty in the dependency tree as proof that the server has switched to Netty.

## 10. Common Embedded Server Configuration

Some properties apply to both Servlet and reactive servers, depending on version/framework support:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

This example is suitable for illustrating Boot 3.x configuration. In Spring Boot 4.x, graceful shutdown is enabled by default according to current branch documentation; check exact behavior per version.

Key concepts to understand:

- server.port: the HTTP port the embedded server attempts to bind; common default is 8080.
- server.port=0: requests an available ephemeral port, useful for tests.
- server.address: network interface address to bind to, if restriction is needed.
- server.compression.enabled: enables HTTP compression where appropriate.
- server.ssl.*: TLS/SSL properties; keep secrets/certificate passwords outside source code.
- server.shutdown and spring.lifecycle.timeout-per-shutdown-phase: shutdown policy and lifecycle wait duration.

With Spring MVC/Servlet, server.servlet.context-path sets the Servlet web application's context path. With WebFlux, use the corresponding WebFlux base path configuration; do not assume server.servlet.context-path will change reactive routes.

If running behind a reverse proxy or ingress, you must properly configure Forwarded/X-Forwarded-* header handling, TLS termination, and trust boundaries. Do not blindly trust every forwarded header sent directly by clients; configure trusted proxies for your environment.

In containers, do not hardcode ports or bind addresses based on a developer machine. Server configuration must align with port mappings, service discovery, health probes, and network policies.

## 11. Server-Specific Configuration

Spring Boot provides many common properties, but it cannot completely abstract every characteristic of all servers.

### Tomcat

Example illustrating a worker thread limit, not a default production recommendation:

~~~yaml
server:
  tomcat:
    threads:
      max: 120
~~~

Thread count should be decided through load testing, latency, CPU, and how blocking the business logic is. Increasing threads can put additional pressure on the database pool, memory, and CPU.

### Jetty

Illustrative example:

~~~yaml
server:
  jetty:
    threads:
      max: 160
~~~

Do not use server.tomcat.* properties to tune Jetty. Consult the application properties reference for the right version branch and observe real metrics.

### Undertow, Only Supported in Boot 3.x

Example illustrating the two thread types:

~~~yaml
server:
  undertow:
    threads:
      io: 4
      worker: 32
~~~

I/O threads and worker threads serve different purposes. If a handler runs blocking code directly on an I/O thread, a small stalled group of threads can affect a large number of connections. Adjust only after benchmarking and understanding the workload.

### Reactor Netty

Reactor Netty uses event loops and its own networking resources. There are specific properties under the server.netty.* namespace and Reactor Netty APIs/customizers; the exact property set depends on the Spring Boot branch. When tuning the event loop, connection pool, or TLS, check both the HTTP server and any WebClient/Reactor Netty clients that may share resources.

Do not transfer Tomcat thread counts one-to-one to Reactor Netty: thread-per-request and event-loop have different resource models. Properties unsupported by the running server may not produce the effect you expect.

## 12. Auto-Configuration and WebServerFactory

In Boot, web server factories are responsible for creating server instances. Spring Boot provides auto-configuration for Servlet or reactive contexts when dependencies and conditions match.

Conceptual cycle:

~~~text
Dependencies + WebApplicationType + Properties
                 |
                 v
        Spring auto-configuration
                 |
                 v
       WebServerFactory bean
                 |
                 v
         Embedded HTTP server
                 |
                 v
         HTTP handlers/adapters
~~~

When you need server-specific customization that properties cannot express, you can declare a WebServerFactoryCustomizer with the exact factory type. For Tomcat there is TomcatServletWebServerFactory; for Reactor Netty there is NettyReactiveWebServerFactory. A customizer targeting Tomcat has no effect on Jetty or Netty.

Do not create a custom WebServerFactory just to change the port or thread count when properties already exist. When declaring your own factory, you take responsibility for its impact on auto-configuration and version compatibility. Test real startup after every change.

When auto-configuration behaves unexpectedly:

1. Check runtime dependencies and whether a starter was accidentally excluded.
2. Check application type, active profiles, and effective properties.
3. Inspect bean condition reasons in the condition evaluation report if needed.
4. Confirm the server factory and startup logs.
5. Send a real request to the port the server is bound to.

## 13. Request Reception Flow and Thread Model

### 13.1. Spring MVC on Tomcat/Jetty/Undertow

An HTTP request arrives at the connector and enters the Servlet container. After the Servlet Filter chain, DispatcherServlet locates the Spring MVC handler, binds parameters, invokes the controller, and returns the response via message converters.

In a typical synchronous endpoint, the container thread handling the request may have to wait on database queries or synchronous HTTP clients. With many slow requests, queues and busy thread counts can rise. Servlet supports asynchronous processing, so you should not equate every MVC request with a simple blocking model in all scenarios.

Common risks: thread pool exhaustion, database pool exhaustion, timeouts, lock contention, large request bodies, or too many long-lived connections.

### 13.2. WebFlux on Reactor Netty

Netty manages sockets and event loops; Spring WebFlux processes event streams through a reactive chain. A pipeline meant to be end-to-end non-blocking requires compatible dependencies; if blocking calls are mixed into the event loop, response times of other requests can also suffer.

Common risks: blocking on the event loop, misunderstood backpressure, manual subscribe without lifecycle control, unmanaged cancellation, unsuitable connection pools, or holding resources across a reactive chain for too long.

You should not claim Reactor Netty is always faster than Tomcat. For business logic backed by synchronous libraries, switching to WebFlux without changing data access can increase complexity without improving throughput.

## 14. Verifying Which Server Is Actually Running

After modifying dependencies, perform checks in order.

**Inspect dependencies on the runtime classpath:**

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Look for the corresponding server starter and libraries. To investigate a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

If Tomcat unexpectedly remains in the dependency tree, inspect which transitive branch brings it in. When seeing reactor-netty as a client dependency in an MVC application, do not conclude that the HTTP server is Netty.

**Run the real application:**

~~~bash
./gradlew bootRun
~~~

Read the server name and port in the logs. Tomcat, Jetty, Undertow, and Netty typically have distinct indicators in startup logs, though exact log strings change by version and log level. Do not parse the server name by relying on a hardcoded log line.

**Call the endpoint:**

~~~bash
curl -i http://localhost:8080/api/status
~~~

Confirm the HTTP status, content type, and response body. Update the URL if using a different profile or port. When testing a server switch, repeat the end-to-end test suite and requests covering bodies, headers, timeouts, error mapping, and security.

**Check the port:**

If binding fails, inspect which process holds the port. server.port=0 helps tests avoid port collisions, but does not replace checking the configured port in production. With @SpringBootTest(webEnvironment = RANDOM_PORT), Spring Boot picks a random port for HTTP tests.

## 15. Testing When Changing Servers

Changing the web server is an infrastructure-layer change. Controller APIs may stay unchanged, yet runtime behavior still needs verification.

A reasonable smoke test matrix:

| Area | What to verify |
| --- | --- |
| Startup | Context initializes successfully; one server of the right type binds the port |
| Routing | GET/POST, path variables, query parameters, and request bodies |
| JSON | Content-Type, charset, converters, and error responses |
| Validation | 400 on invalid input; correct exception mapping |
| Security | 401/403, filter chain, and CORS work as designed |
| Session/cookie | Cookies, sessions, SameSite/Secure if used by the application |
| Long request | Timeouts, upload/download, streaming, or SSE if present |
| Observability | Access logs, application logs, health, metrics, traces |
| Shutdown | Server stops within the grace period and load balancer policy |
| Deployment | TLS/proxy headers, ports, container readiness, and resource limits |

With the code from section 6, you can add a real HTTP test using TestRestTemplate in Spring Boot 3.x:

File src/test/java/example/web/EmbeddedServerApplicationTests.java:

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class EmbeddedServerApplicationTests {

    @Autowired
    TestRestTemplate rest;

    @Test
    void statusEndpointReturnsOk() {
        ResponseEntity<String> response =
            rest.getForEntity("/api/status", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("{\"status\":\"ok\"}", response.getBody());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

This test starts a real HTTP server on a random port, unlike unit tests that call controller methods directly. For alternative servers, re-run the same test suite to verify the application contract; WebFlux in particular needs appropriate reactive tests and a WebFlux application configuration.

## 16. Running in Production

### 16.1. Timeouts and Connection Limits

Understand clearly what each timeout measures: waiting to establish a connection, waiting to receive a request, waiting to send a response, or downstream HTTP/database timeouts. Each server uses different property names and APIs for specialized limits.

Do not open excessively high connection/thread limits just because request volume increases. The real bottleneck may be SQL, cache, an HTTP client, or an auxiliary thread pool. Use load testing to identify saturation and set protective system limits.

### 16.2. HTTPS, Proxies, and Protocols

Normally clients pass through a load balancer/reverse proxy before reaching the embedded server. You must agree on where TLS terminates, how scheme/host/remote IP are passed, and which forwarded headers are trusted. If HTTP/2, WebSocket, or SSE are required, verify support and configuration for the exact server/Boot version.

Do not enable TLS or forwarded-header trust by randomly copying configuration from another environment; this can cause wrong redirect URLs, Secure cookies, client IPs, or security bugs.

### 16.3. Health and Readiness

Spring Boot Actuator can expose health and readiness/liveness probes when properly configured. Distinguish a live process from an instance ready to receive traffic. Do not expose sensitive operational endpoints to the untrusted Internet.

### 16.4. Graceful Shutdown

Spring Boot 3.x allows enabling:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

The goal is to stop accepting new requests in the manner supported by the server, allow in-flight requests to finish within the time limit, and close resources. New-request rejection details differ across Tomcat, Jetty, Undertow, and Reactor Netty; for example, Boot 3.3 documentation notes that Undertow can return 503 for new requests during shutdown.

In Boot 4.x, graceful shutdown is enabled by default according to current documentation. Regardless of version, verify real behavior inside your container or orchestrator because stop signals and platform timeouts can cut shutdown short.

### 16.5. Logging and Metrics

Observe the same set of metrics when comparing servers: throughput, p50/p95/p99 latency, error rate, CPU, heap, GC, open connections, active threads or event-loop pressure, pool saturation, and shutdown time. Separate application logs from HTTP server access logs.

When benchmarking, hold hardware, JVM, garbage collector, JDK, workload, data, concurrency, and dependencies constant. Warm up first, run multiple iterations, compare under identical conditions, and state variance ranges. Do not infer absolute performance rankings from a single test run.

## 17. Common Configuration Errors

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Application fails to start after changing server | Old starter remains on runtimeClasspath, conflicting auto-configuration/factory, or incompatible version | Check dependency tree, remove unused starter, cross-check Boot version support |
| Added WebFlux but still seeing Tomcat | MVC starter still present, MVC chosen by default | Decide whether the app needs MVC or reactive; reorganize dependencies/application type |
| Undertow starter not found on Boot 4 | Undertow was removed from official support in Boot 4.0 | Switch to an appropriate Tomcat/Jetty and re-test |
| Port 8080 already in use | Another process is bound to the port | Stop the conflicting process or configure another port |
| 404 even though server is running | Wrong path, context path/base path, or mapping | Check mappings and actual URL |
| High threads/rising latency in MVC | Blocking dependency, small pool, or requests waiting too long | Take thread dumps, check connection pool, timeouts, and per-dependency latency |
| Event loop blocked in WebFlux | Calling blocking APIs directly on the event loop | Use non-blocking dependencies or offload blocking calls to an appropriate executor |
| Increasing threads does not improve throughput | Downstream bottleneck, locks, CPU, or GC | Run load tests and locate actual saturation |
| Wrong scheme/client IP behind proxy | Incorrect forwarded headers or trust boundary | Configure proxy and forwarded-header strategy for the environment |
| Stopping container breaks in-flight requests | Insufficient grace period or SIGTERM not delivered properly | Check shutdown policy and timeouts in both app and orchestrator |

## 18. How to Choose a Server for a Project

There is no single best choice for every situation. Practical selection process:

1. **Identify the framework:** Servlet MVC or WebFlux; whether database and HTTP client libraries are primarily blocking or non-blocking.
2. **Identify the Spring Boot version:** especially when proposing Undertow, as Boot 4 removed it.
3. **Start from sensible defaults:** Tomcat for MVC, Reactor Netty for WebFlux.
4. **Switch servers only for measurable reasons:** integration requirements, organizational policy, specific capabilities, or benchmark results on a real workload.
5. **Check dependencies and runtime:** exclude unused default starters, verify the selected server.
6. **Test thoroughly:** routing, security, sessions, streaming, TLS, errors, health, and graceful shutdown.
7. **Monitor operations:** measure before/after, and keep rollback capability in case of regressions.

Three illustrative scenarios:

- CRUD API using Spring MVC + synchronous JPA/JDBC: start with Tomcat. You can try Jetty if there is a specific need; switching to Reactor Netty does not automatically make JDBC non-blocking.
- Gateway/event-streaming using Spring WebFlux and reactive clients: Reactor Netty is a sensible default; monitor backpressure, event loop, and timeouts.
- MVC application currently using Undertow on Boot 3.x preparing to upgrade to Boot 4.x: include migrating the server to Tomcat or Jetty in the upgrade plan, and run regression tests before rollout.

## 19. Verifiable Hands-On Exercise

Perform on isolated test projects or revertible branches:

1. Create the MVC application from section 6; run with default Tomcat.
2. Record the server/port in logs, GET /api/status response, test results, and related dependencies.
3. Replace Tomcat with Jetty following section 7, run the same test suite, and verify the new server.
4. If using a Boot 3.x version that supports Undertow, try the configuration from section 8 and compare startup and shutdown behavior.
5. Create a separate WebFlux project with Reactor Netty, run the reactive endpoint, and distinguish WebFlux code from Servlet controllers.
6. Simulate a port conflict to observe the bind error; try server.port=0 in tests.
7. Enable graceful shutdown and verify shutdown duration with a realistic-duration request in a test environment.
8. Record results in a table including Boot version, server, web stack, dependencies, startup, HTTP test, shutdown, errors, and resolutions.

The exercise passes when you can prove which server is running using runtime evidence, explain why it was selected, swap servers with the right dependencies, and avoid conflating Servlet MVC with reactive WebFlux.

## 20. Self-Check Questions

1. What does an embedded server do and how does it differ from Spring MVC?
2. Why does spring-boot-starter-web usually pull in Tomcat while spring-boot-starter-webflux usually pulls in Reactor Netty?
3. What do Tomcat, Jetty, and Undertow have in common regarding the Servlet API?
4. Why can't Reactor Netty simply replace Tomcat in an arbitrary MVC application?
5. Does WebFlux running on Jetty become Spring MVC? Why or why not?
6. What dependency changes are needed when switching from Tomcat to Jetty in Boot 3.x?
7. Why does Undertow require special attention when upgrading to Spring Boot 4.0?
8. How does the server.port property differ from server.tomcat.*, server.jetty.*, and server.undertow.* properties?
9. When both web and webflux starters are present, which framework is usually chosen?
10. How do you verify which server is running without guessing?
11. Why might increasing thread count fail to improve performance?
12. What must be checked when changing servers in production?

## Official References

- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 – Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Boot 4.0 – Embedded Web Servers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Boot 4.0 Migration Guide – Undertow removal](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)

Version-specific documentation links help avoid misapplying starters, APIs, and properties across Spring Boot 3.x and 4.x.