# Avoiding Protocols or Starters That Do Not Serve Application Needs

> **Context:** Spring Boot **web-runtime** → **Extending the Web Platform**. This lesson uses **Java 17+, Spring Boot 3.3.x, and Spring Framework 6.1.x**, focusing on not pulling WebFlux, WebSocket, STOMP, GraphQL, RSocket, gRPC, SOAP, template engines, or extra HTTP libraries into an application when actual requirements do not call for them. The goal is not "smallest JAR at all costs," but **a capable, understandable, well-tested, secure, and operable system**.

## 1. Learning Objectives

1. Separate four concepts: **communication protocol**, **web stack**, **HTTP client**, and **Spring Boot starter**.
2. Start from business requirements to choose the right starter for REST JSON, server-side rendering, reactive I/O, bidirectional WebSocket, one-way SSE, GraphQL schemas, RSocket, or contract-based SOAP/gRPC.
3. Explain the Spring Boot 3.3 rule: when both Spring MVC and Spring WebFlux are present, **MVC is typically prioritized as the default web application type**; having `WebClient` does not mean the server switched to Reactor Netty.
4. Recognize that starters pull in **transitive dependencies** and impact classpath, auto-configuration, codecs, beans, endpoint mappings, client connectors, CVE surface, and operational cost.
5. Compare minimal options, such as `RestClient` for blocking HTTP in an MVC app instead of adding WebFlux just to call a simple API.
6. Build a runnable Java 17+ Spring Boot MVC project with a Maven POM, Java controller, and HTTP integration test **without unnecessary protocols**.
7. Use `mvn dependency:tree`, `mvn dependency:analyze`, Gradle `dependencyInsight`, Boot's conditions report, and controlled tests to explain why a dependency is present or absent.
8. Make justified proposals to **add, keep, or remove** starters, backed by regression tests, security reviews, benchmarks, and rollback plans.

## 2. Protocol, Framework, Client API, and Starter: Separate Them Early

A **protocol** defines messages and communication rules between components. Examples: HTTP/1.1 or HTTP/2 for request/response, WebSocket for bidirectional communication, RSocket for reactive messaging, and gRPC for RPC over protobuf/service contracts.

A **web stack** defines how incoming requests are processed inside the application:

- **Spring MVC**: Servlet model, `DispatcherServlet`, `@RestController`, embedded Tomcat by default with `spring-boot-starter-web`.
- **Spring WebFlux**: reactive web stack, `Mono`/`Flux`, typically running on Reactor Netty; suited when request processing and key dependencies support non-blocking I/O end-to-end.

An **HTTP client** is what the application uses to **call outward**: `RestClient` (blocking), `WebClient` (reactive), `RestTemplate` (legacy), or Java `HttpClient`. Which client you pick **does not automatically decide** whether the inbound HTTP server runs MVC or WebFlux.

A **starter** is a dependency bundle provided by Spring Boot to group compatible libraries and enable auto-configuration. Starters have friendly names, yet **a starter is not a protocol** and **does not mean** endpoints for that technology are automatically exposed publicly.

~~~text
Business need: "customers view product catalog"
        |
        v
Communication: HTTP GET /api/products
        |
        v
Server stack: Spring MVC (sufficient?)
        |
        v
Dependency: spring-boot-starter-web
        |
        v
Auto-configuration from classpath + properties
        |
        v
Tomcat / DispatcherServlet / JSON conversion
        |
        v
Real tests: HTTP 200, auth, startup, resources
~~~

### Concept Comparison Table

| Term | Example | What It Is Not |
|---|---|---|
| HTTP/2 | `server.http2.enabled=true` with a supporting embedded server | Not RSocket or GraphQL |
| Spring MVC | `@RestController`, Servlet | Not HTTP/1.1-only; works with HTTPS/HTTP2 |
| Spring WebFlux | `Flux`, reactive routing | Does not make blocking JDBC non-blocking |
| `RestClient` | Blocking HTTP calls to a partner API | Not an inbound HTTP server |
| `WebClient` | Reactive HTTP calls to a partner API | Does not force switching the server to WebFlux |
| WebSocket | Long-lived bidirectional connection | Unnecessary just to push 1 update per minute |
| GraphQL | Query language, schema, resolvers | Does not replace the HTTP transport itself |
| RSocket | Reactive messaging protocol | Not an alias for HTTP/2 |
| Starter | `spring-boot-starter-graphql` | Not a fully configured ready endpoint |

**Core message:** "Adding a library" and "delivering a properly used capability" are two separate things. Design the contract first, and add dependencies afterward.

## 3. Start from Requirements, Not from Every Checkbox on Initializr

Consider a new product:

> An order management app has 8 JSON endpoints, uses Spring Data JPA for database queries, authenticates users, calls one partner REST API, and returns HTTP request/response payloads. There is no live chat, no GraphQL client, and no RSocket client.

The requirements show a need for an HTTP REST server, persistence/security, and an outbound client — yet **zero evidence** for opening a WebSocket endpoint, designing a GraphQL schema, starting an RSocket TCP listener, building gRPC services, or adding Thymeleaf, Mustache, and FreeMarker together.

A sensible baseline choice:

- **Spring MVC** for HTTP JSON controllers.
- **`RestClient`** for synchronous outbound HTTP if it meets latency/concurrency budgets.
- **Spring Security**, JPA, validation, migrations, and metrics when actually required — never strip security dependencies just to shrink artifact size.
- **One** embedded servlet server managed by `starter-web`, rather than installing multiple server runtimes unnecessarily.

Ask before adding any dependency:

1. Which client needs this technology? Browser, mobile, third-party, background job, or another service?
2. Is there a concrete protocol contract and an active consumer?
3. Do existing mechanisms (HTTP JSON, polling, SSE, `RestClient`) already satisfy the need?
4. Which SLO fails without it? Latency, concurrency, binary throughput, schema evolution, or bidirectional communication?
5. Will adding it alter request handling, security, ports, resource budgets, or deployment/proxies?
6. Who will maintain it, monitor versions/CVEs, and debug protocol failures?
7. Can we demonstrate its value with integration tests/benchmarks, or are we speculatively preparing for an unrequested need?

**Do not chase absolute minimalism blindly.** Starters for authentication, metrics, validation, or contract testing are justified when addressing real risks or capabilities. "No Java import found" does not prove a library is unused: the runtime may use it via reflection, SPI, or auto-configuration.

## 4. Starter Selection Table by Real Need

| Need | Suitable Spring Boot 3.3 Starter/API | Do Not Add Automatically | Verify Before Deciding |
|---|---|---|---|
| REST JSON with MVC | `spring-boot-starter-web` | webflux, websocket, graphql, rsocket | API clients, Servlet workload |
| Non-blocking reactive HTTP server | `spring-boot-starter-webflux` | `web` "just in case" | Genuine reactive pipeline, non-blocking drivers, event-loop safety |
| MVC calling synchronous APIs | `RestClient` already included in Spring Web | No separate webflux just for HTTP calls | Timeouts, retries, pooling, response bounds |
| MVC needing reactive `WebClient` | Add WebFlux dependencies intentionally | Does not switch server from Tomcat to Netty by default | `WebClient` bean/connector, MVC stays active |
| Server-rendered HTML | Pick one: `spring-boot-starter-thymeleaf`, FreeMarker, Mustache | Do not add all three if unused | View resolvers, template security |
| One-way server push | SSE over HTTP (`SseEmitter` / reactive SSE) | WebSocket/STOMP not mandatory | Reconnects, proxy buffering, concurrent connections |
| Real-time full-duplex chat/collab | `spring-boot-starter-websocket` for MVC or WebFlux WebSocket | GraphQL/RSocket not inherently required | Authentication, origin, scaling |
| GraphQL schema/query API | `spring-boot-starter-graphql` + web transport | Do not add WebSocket/RSocket if unused | Schema, resolvers, authorization, query limits |
| True RSocket transport | `spring-boot-starter-rsocket` | Not for enabling HTTP/2 | RSocket clients, routing/transport, network |
| SOAP/WSDL integration | `spring-boot-starter-web-services` | Do not replace with GraphQL just to look modern | SOAP contract, XML schemas, security |
| gRPC/protobuf interface | Appropriate gRPC/protobuf SDK/toolchain | Do not assume Boot 3.3 ships one mandatory official gRPC starter | Proto contract, codegen, TLS, deadlines |
| Hypermedia REST contract | `spring-boot-starter-hateoas` | Not required for every REST API | Link relations, client behavior |
| Needed Jakarta Bean Validation | `spring-boot-starter-validation` | Do not add when no validation use case exists | Constraints, error contract |
| Production management | `spring-boot-starter-actuator` | Do not expose diagnostics publicly | Endpoint exposure, security/monitoring |
| Unit/integration testing | `spring-boot-starter-test` in `test` scope | Never move to runtime just to get JUnit | Maven scopes, CI |

A starter is only the **starting point**. A working GraphQL endpoint still needs schemas and handlers; WebSocket needs handlers or STOMP broker config; gRPC needs proto services, generated stubs, listeners, and clients; RSocket needs transport/routing configuration. Never equate "dependency declared" with "feature working safely."

## 5. Changing the Classpath Can Change Auto-Configuration

Spring Boot evaluates conditions like `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and `@ConditionalOnWebApplication` to decide which beans and auto-configurations activate. A starter pulls transitive dependencies onto the **runtime classpath**, which can alter which conditions match.

~~~text
Maven pom.xml / Gradle dependencies
         |
         v
Resolved compile/runtime classpath
         |
         v
Spring Boot auto-configuration conditions
         |
         +--> match: registers corresponding beans/config/handlers
         |
         +--> no match: skips auto-configuration
         |
         +--> conflict/missing config: startup may fail
         |
         v
Runtime reality: context, ports, endpoints, resources
~~~

Impacts **can** include adding HTTP client connector candidates, message converters, serializers, beans, changed auto-config matches, extra startup work, or new endpoints once configured. Still, not every starter opens a listener or endpoint by itself; conditions and application code govern what activates.

### Why Does Adding WebFlux to MVC Not Switch the Server?

In Spring Boot 3.3, when only `spring-boot-starter-web` is present, the app runs Servlet MVC with Tomcat. When only `spring-boot-starter-webflux` is present, it runs a reactive web app with Reactor Netty. When **both** are present, Spring MVC is **prioritized** as the default web application type. This is intentional because many MVC apps include WebFlux solely to use outbound `WebClient`.

~~~text
starter-web                  -> Servlet MVC / default Tomcat
starter-webflux              -> Reactive WebFlux / default Reactor Netty
starter-web + starter-webflux -> Servlet MVC usually selected,
                                 WebClient remains usable outbound
~~~

Switching to reactive via `spring.main.web-application-type=reactive` works when appropriate, **yet is never a casual fix for a messy dependency graph**. Servlet filters, controller assumptions, and blocking dependencies must all be audited and migrated cleanly.

### Why Avoid Keeping Multiple Embedded Servers Together?

Servlet `starter-web` defaults to Tomcat; WebFlux defaults to Reactor Netty. To switch to Jetty or Undertow for operational reasons, swap the server dependency following Boot's documented exclusions and test thoroughly. Never keep Tomcat, Jetty, Undertow, and Netty together at runtime hoping "Boot will pick whichever fits": it creates confusion and compatibility maintenance for zero gain.

## 6. How to Decide Between MVC, WebFlux, and Outbound HTTP Clients

### Spring MVC Is Often Enough

Spring MVC/Servlet fits well when most code is REST JSON backed by JPA/JDBC or blocking SDKs, and measured throughput/latency meets SLOs. MVC also supports async request processing, HTTP streaming, and `SseEmitter` when needed. "Blocking" does not mean "unscalable"; measure thread/concurrency behavior, connection pools, DB latency, and HTTP proxy behavior.

### When Is WebFlux a Reasonable Choice?

WebFlux fits when high I/O concurrency and streaming are explicit requirements, downstream drivers are genuinely non-blocking, and the team understands `Mono`/`Flux`, backpressure, cancellation, pooled `DataBuffer`s, and reactive operations. Adding WebFlux while still calling blocking JDBC on the Netty event loop **does not** make I/O non-blocking.

### Only Calling External REST: Consider RestClient Before WebClient

Spring Framework 6.1 introduced the fluent blocking `RestClient` API. In an MVC app already using `starter-web`, you do not necessarily need `starter-webflux` just to call `GET /partner/health` synchronously.

**Snippet inside a service**:

~~~java
// Requires RestClient import and an application PartnerDto class.
private final RestClient client;

public PartnerService(RestClient.Builder builder) {
    this.client = builder
            .baseUrl("https://partner.example.test")
            .build();
}

public PartnerDto load(long id) {
    return client.get()
            .uri("/items/{id}", id)
            .retrieve()
            .body(PartnerDto.class);
}
~~~

This is **not a complete Java class**; it only shows how Boot injects `RestClient.Builder`. Production must still configure connect/read timeouts, TLS validation, response limits, SSRF defenses, 4xx/5xx mapping, and concurrency measurements. When true reactive composition or large streaming responses are needed, `WebClient` has clear value and justifies adding WebFlux dependencies.

## 7. Real-Time Does Not Automatically Mean WebSocket

If a dashboard only needs job progress updates every 3 seconds, compare options:

| Mechanism | Characteristics | Needs WebSocket Starter? |
|---|---|---|
| HTTP polling | Client GETs on an interval | No |
| Long polling | Server holds GET until event or timeout | No |
| SSE | `text/event-stream` for server→browser push | No |
| WebSocket | Continuous bidirectional full-duplex client↔server | In MVC, usually needs `spring-boot-starter-websocket` |
| STOMP over WebSocket | Destinations, subscriptions, broker semantics | Needs messaging/STOMP config beyond raw WS transport |
| RSocket | Binary/reactive messaging over its own transport | Distinct protocol from WebSocket/HTTP SSE |

**SSE in MVC** uses `SseEmitter`. Illustrative method:

~~~java
// Snippet inside an MVC @RestController, not a full app.
@GetMapping(value = "/api/progress",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter progress() {
    SseEmitter emitter = new SseEmitter(10_000L);
    try {
        emitter.send(SseEmitter.event()
                .name("progress")
                .data("done"));
        emitter.complete();
    } catch (Exception ex) {
        emitter.completeWithError(ex);
    }
    return emitter;
}
~~~

Imports needed: `org.springframework.http.MediaType`, `org.springframework.web.bind.annotation.GetMapping`, and `org.springframework.web.servlet.mvc.method.annotation.SseEmitter`. This shows **SSE already exists in MVC**; production must manage async threads, disconnects, heartbeats, proxy buffering, and connection counts.

If the application genuinely needs live chat, high-frequency client messages, co-editing, or full-duplex game state, WebSocket makes sense. Even then, design authentication, origin checks, heartbeats, idle timeouts, rate limits, and scaling rather than just adding the dependency. Adding `spring-boot-starter-websocket` in MVC **does not open a `/ws` endpoint** until a handler or broker mapping is configured.

## 8. When Does GraphQL Actually Serve the Product?

GraphQL solves **schema-driven** query/mutation/subscription use cases. It shines when diverse clients need flexible projections, schema evolution, or a domain graph that REST handles awkwardly. It also adds operational surface:

- `.graphqls` schemas and resolvers/data fetchers.
- Field/object-level authorization rather than relying solely on HTTP route rules.
- Query complexity/depth/cost limits, N+1/DataLoader handling, and timeouts.
- Error mapping, caching strategies, schema migrations, and tooling.
- Per-operation monitoring and public schema/docs policies.

Spring Boot 3.3 `spring-boot-starter-graphql` **requires a web transport** to expose HTTP GraphQL: `spring-boot-starter-web` for MVC or `spring-boot-starter-webflux` for reactive servers. GraphQL itself is transport-agnostic. The GraphQL WebSocket endpoint is **disabled by default**, requiring WebSocket transport support plus `spring.graphql.websocket.path` on Servlet. Never add GraphQL just because "the frontend currently makes 3 REST calls"; optimizing a REST endpoint or adding caching may be much simpler.

Minimal illustrative schema:

~~~graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
}
~~~

A schema without DataFetchers/`@QueryMapping`, transport, and security **is not a runnable standalone GraphQL API**. The distance between "starter added" and "safely operated API" belongs inside every dependency decision.

## 9. RSocket, gRPC, SOAP, and Other Options

### RSocket

RSocket is a non-HTTP protocol supporting request-response, request-stream, fire-and-forget, and request-channel. When consumers speak RSocket and reactive streaming/routing is a primary requirement, `spring-boot-starter-rsocket` fits. An ordinary REST JSON app does not need RSocket just because "backpressure" sounds appealing. Design must cover TCP/WebSocket transport, routes, authentication, ports/proxies, and codec versioning.

### gRPC

gRPC typically uses Protocol Buffers, generated stubs, and HTTP/2. It is **not** a setting inside Spring MVC, nor does it appear simply by setting `server.http2.enabled=true`. Spring Boot 3.3 does not mandate one single official gRPC starter for every project; integration libraries are chosen for contract and compatibility. Without protobuf/gRPC client requirements, avoid pulling `protoc` compilers, code generation, and extra listeners into the service.

### SOAP/Web Services

When integrating WSDL/XSD, SOAP security/headers, and existing SOAP clients, `spring-boot-starter-web-services` serves a concrete purpose. If an API only exchanges JSON, a SOAP runtime adds no value to GET/POST JSON.

### HATEOAS

HATEOAS helps when representations include links/affordances that clients actively follow to navigate workflows. If a simple API only exchanges JSON DTOs, `spring-boot-starter-hateoas` is not mandatory to "be RESTful."

### Template Engines

When rendering HTML server-side, pick Thymeleaf, FreeMarker, Mustache, or whichever engine fits your **UI needs**. For pure JSON `@RestController` services, omit template engines; adding them never speeds up REST and only complicates view resolution and configuration.

## 10. HTTP/2, HTTPS, and Compression Are Not New Protocol Starters

Compatible Spring MVC/Tomcat and WebFlux servers already support HTTP/2 given proper runtime conditions. Depending on deployment, you can set:

~~~properties
server.http2.enabled=true
~~~

This is a **server capability/configuration**; with HTTPS it requires valid TLS certificates, client/ALPN support, and verifying the negotiated protocol. It does not require an RSocket, gRPC, or GraphQL starter. Note that a client speaking HTTP/2 to ingress does not guarantee the ingress→backend hop also uses HTTP/2.

Compression:

~~~properties
server.compression.enabled=true
~~~

is an HTTP server setting saving bandwidth on eligible responses; there is no need for a new "compression protocol" just because JSON compresses well. Measure CPU vs. network tradeoffs, and verify MIME types, `Accept-Encoding`, and `Vary` when caching variants. Already-compressed images/videos/archives gain nothing from re-compression.

Likewise, HTTPS in Spring Boot 3.3 uses `server.ssl.bundle` and PEM/JKS bundles on the embedded server; never pull in a messaging starter just to configure TLS.

## 11. Runnable Lab: Spring Boot MVC Serving JSON with Minimal Starters

A standalone app with **one REST endpoint** and tests, using zero unnecessary protocols.

### 11.1. Directory Tree

~~~text
minimal-web/
  pom.xml
  src/
    main/
      java/
        example/
          minimalweb/
            MinimalWebApplication.java
      resources/
        application.properties
    test/
      java/
        example/
          minimalweb/
            MinimalWebApplicationTests.java
~~~

### 11.2. Complete Maven pom.xml (Boot 3.3.13, Java 17)

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>minimal-web</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`spring-boot-starter-test` sits in **test scope**, not runtime classpath. The Boot parent BOM manages aligned versions; you do not manually add `spring-webmvc`, Jackson, or Tomcat versions for the controller to work.

### 11.3. Complete Java Application

Create `src/main/java/example/minimalweb/MinimalWebApplication.java`:

~~~java
package example.minimalweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MinimalWebApplication {
    public static void main(String[] args) {
        SpringApplication.run(MinimalWebApplication.class, args);
    }

    public record Greeting(String message) { }

    @RestController
    static class GreetingController {
        @GetMapping("/api/greeting")
        public Greeting greeting() {
            return new Greeting("hello");
        }
    }
}
~~~

`@SpringBootApplication` scans the nested `@RestController` in the same package. Spring MVC handler mapping routes HTTP GET to the method, and Jackson from the web starter serializes the record to JSON. No WebFlux `Mono`, WebSocket broker, GraphQL schema, or template engine is needed.

### 11.4. application.properties

~~~properties
server.port=8080
~~~

Run from the project folder:

~~~bash
mvn spring-boot:run
~~~

Test from another terminal:

~~~bash
curl -i http://localhost:8080/api/greeting
~~~

Expected status **200 OK**, JSON body equivalent to:

~~~json
{"message":"hello"}
~~~

Headers such as `Content-Type`/`Date`/`Content-Length` vary in order and extra metadata. Do not assert immutable raw Maven or HTTP header stdout. One HTTP server port suffices for this use case.

### 11.5. Integration Test with a Real Embedded Web Server

Create `src/test/java/example/minimalweb/MinimalWebApplicationTests.java`:

~~~java
package example.minimalweb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class MinimalWebApplicationTests {
    @Autowired
    private TestRestTemplate http;

    @Autowired
    private ApplicationContext context;

    @Test
    void usesServletWebStack() {
        assertTrue(context instanceof
                ServletWebServerApplicationContext);
    }

    @Test
    void returnsGreetingJson() {
        ResponseEntity<MinimalWebApplication.Greeting> response =
                http.getForEntity("/api/greeting",
                        MinimalWebApplication.Greeting.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("hello", response.getBody().message());
    }
}
~~~

This is a **complete Java test file**, compatible with JUnit Jupiter/Spring Boot Test from `starter-test`. `RANDOM_PORT` runs the embedded server on an available port (without colliding on 8080 from `application.properties`). Asserting `ServletWebServerApplicationContext` confirms the app runs on the MVC/Servlet context; the second test verifies the HTTP endpoint and JSON serialization.

Run:

~~~bash
mvn test
mvn clean package
~~~

Assuming JDK 17/Maven and Maven Central access, both tests pass. Do not treat this minimal test as proof of production authorization or TLS; the lab intentionally omits security and DBs. When a product requires authentication/authorization, add the proper starter/config and integration tests — **never remove necessary controls** just because this lesson warns against superfluous dependencies.

## 12. Before-and-After Experiment: Adding an Unneeded Starter

On an experimental branch of the lab, add:

~~~xml
<!-- Added temporarily for study: no real WebSocket use case -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>
~~~

Then re-run:

~~~bash
mvn test
mvn dependency:tree
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Observe:

- Which libraries appeared in the dependency tree?
- Are there new matches in the Conditions Evaluation Report?
- Did the application context or server change?
- Was any WebSocket endpoint actually mapped?
- Do existing HTTP REST tests still pass?
- Did JAR size, startup time, or heap usage increase when measured?

Never claim **`starter-websocket` automatically opens a port** or `/ws` endpoint; you have not declared any WebSocket handler. After gathering evidence, remove the unused dependency instead of keeping it merely because startup did not fail.

Repeat the experiment with `spring-boot-starter-webflux`: Boot 3.3 normally still picks MVC when both starters exist. If you genuinely need `WebClient` for outbound I/O, document the reason with matching tests/metrics; otherwise drop the extra complexity.

## 13. Maven Dependency Tree: Direct vs. Transitive Dependencies

`pom.xml` lists only direct dependencies. `spring-boot-starter-web` brings Spring MVC, Jackson, the embedded servlet container, and supporting modules **via transitive dependencies**. Never exclude `spring-webmvc`, Tomcat, or Jackson just because your business code does not import each library explicitly.

~~~text
minimal-web app
  |
  +-- spring-boot-starter-web      [direct]
  |       |
  |       +-- Spring MVC            [transitive]
  |       +-- embedded Tomcat       [transitive]
  |       +-- JSON libraries        [transitive]
  |
  +-- spring-boot-starter-test     [test scope]
~~~

This is a conceptual diagram, **not exact output** from `mvn dependency:tree`. Inspect the real output via:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=org.springframework:spring-webflux
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-websocket
~~~

`-Dincludes` traces a specific library and who pulled it in. During audits, distinguish runtime, compile, and test scopes. Normal `test` dependencies do not ship inside the runtime executable archive.

### Gradle Equivalents

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

On Windows use `gradlew.bat`. `dependencyInsight` shows why a dependency entered `runtimeClasspath` and how its version was resolved.

### "Unused Dependency" Does Not Mean Safe to Remove

~~~bash
mvn dependency:analyze
~~~

Static analysis can flag dependencies as declared-unused when Spring uses them via auto-configuration, reflection, `ServiceLoader`, Jackson modules, annotations, or runtime wiring. Treat that report as **an investigative lead**, never an instruction to delete dependencies blindly. Removal decisions require integration and runtime tests, not merely passing compilation.

## 14. Conditions Evaluation Report: Which Auto-Configurations Actually Activated?

Pass `--debug` in a local environment:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

or on the built JAR:

~~~bash
java -jar target/minimal-web-0.0.1-SNAPSHOT.jar --debug
~~~

Spring Boot prints the **Conditions Evaluation Report** showing positive matches, negative matches, and reasons. Use it to answer:

- Did Servlet MVC auto-configuration match?
- Was WebFlux server auto-configuration skipped because of the web application type?
- Did any WebSocket/GraphQL/RSocket configs actually activate?
- Why was a bean or converter created or skipped?
- Did new dependencies affect HTTP client connector selection?

Do not search for a made-up report line named after a starter. The report lists real auto-configuration classes and condition evaluations for your Boot version.

If `spring-boot-starter-actuator` is present, `/actuator/conditions` provides the same report **when intentionally exposed and secured**. Spring Boot 3.3 does not expose all Actuator endpoints over HTTP by default. **Never enable `management.endpoints.web.exposure.include=*` publicly** just to debug dependencies; `conditions`, `beans`, and `configprops` expose internal structure and implementation details.

## 15. Measuring Impact: Dependency Cost Is More Than JAR Count

Potential costs include:

| Cost | Source | How to Measure |
|---|---|---|
| Executable JAR/image size | Extra transitive dependencies | Compare JAR/image byte sizes |
| Startup | Classpath scanning, auto-config, bean init | Startup timing and conditions report |
| Memory | Objects, codecs, caches, native buffers, pools | Heap/native memory, GC, threads |
| Network surface | New listeners/routes if enabled | Inspect open ports, mappings, ingress |
| Security | More component versions/CVEs, parsers | SBOM/SCA, CVE applicability |
| Upgrades | Version skew/conflicts, BOM maintenance | Dependency tree, compatibility tests |
| Operational burden | Logs, health, session state, proxies, timeouts | Runbooks/alerts/SLIs |
| Developer burden | Another stack and programming model | Training, code review, testing |

Inspect the built artifact:

~~~bash
mvn clean package
jar tf target/minimal-web-0.0.1-SNAPSHOT.jar
~~~

On Linux/macOS:

~~~bash
ls -lh target/*.jar
~~~

On Windows PowerShell:

~~~powershell
Get-ChildItem target -Filter "*.jar" |
    Select-Object Name, Length
~~~

Spring Boot executable JARs pack dependencies inside `BOOT-INF/lib`. Not every library on the classpath is initialized or slows the app down equally; only realistic workload benchmarks prove performance effects. A tiny dependency can still open a risky parser or endpoint if misconfigured, while a large dependency may be indispensable for correctness or security.

**SBOMs** and software composition analysis (SCA) track versions, licenses, and advisories. Never treat a raw CVE count from a scanner as proof of exploitability without checking versions, reachable code paths, and exposure. Still, dependencies delivering zero needed capability rarely justify long-term upgrade and security obligations.

## 16. Version Management: Let the Boot BOM Do Its Job

`spring-boot-starter-parent` or the `spring-boot-dependencies` BOM manages a tested, compatible set of library versions for Spring Boot. For managed dependencies, you normally **should not** pin custom versions for Spring MVC, Jackson, Tomcat, or Reactor/Netty.

Avoid this anti-pattern:

~~~xml
<!-- Illustrates the wrong idea: arbitrary version override,
     not a recommended dependency. -->
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webmvc</artifactId>
    <version>6.x.y-custom</version>
</dependency>
~~~

This is **not a runnable Maven snippet** because `6.x.y-custom` is an illustrative placeholder; the point is never to override versions without a compatibility and security plan. An emergency advisory might justify a temporary override, provided you include test coverage, a written rationale, and a schedule to drop the override on the next Boot upgrade.

**Lab version 3.3.13** is used here to reproduce the exact APIs in the lesson. Production should use a **maintained Spring Boot branch receiving security updates** per organizational policy, rather than staying on an old version just because an example used it.

## 17. Why Not Remove Transitive Dependencies Arbitrarily?

Suppose your source code never imports `ObjectMapper`, yet a controller returns a Java record as JSON. Spring MVC still relies on Jackson to serialize the body; removing it breaks the endpoint. Similarly, your app never imports `Tomcat` directly yet requires the embedded HTTP server. Spring Security, validation providers, and Jackson modules are often wired via reflection or auto-configuration with minimal direct imports in business code.

When swapping servers, use Boot's supported approach: for example, replace embedded Tomcat with Jetty or Undertow in the Servlet stack by **excluding the old starter cleanly and adding the matching server starter**, then verifying build, runtime, HTTP/2, TLS, cookies, sessions, and WebSockets. Never leave multiple servers around "waiting to be picked."

The target is **deliberate minimalism**, not lowest dependency count regardless of behavior. Whenever a real feature needs a library, that dependency is justified even if the JAR grows.

## 18. Verified Process for Adding a New Dependency or Starter

1. **State the use case in business terms.** Which client, what data, one-way or two-way, request/response or stream, schema/versioning?
2. **Evaluate existing capabilities.** Do REST JSON, SSE, `RestClient`, or async MVC already meet the SLO?
3. **Pick one candidate.** Never add 4 competing protocols into production "to compare later."
4. **Trace the data path.** Client→proxy→server, server→downstream, ports/protocols/TLS/authN/authZ.
5. **Inspect direct and transitive dependencies.** Check Maven/Gradle tree, BOM versions, licenses/CVEs.
6. **Check Boot conditions and runtime.** Web application type, beans, endpoint mappings, network listeners.
7. **Write acceptance tests.** Correctness, authenticated/unauthorized access, payload bounds, cancellation, and backpressure where relevant.
8. **Measure baseline vs. candidate.** Startup, heap/direct memory, threads, latency/throughput, CPU, artifact/image size.
9. **Plan operational rollout.** Config/ports/ingress, alerts/metrics, owners, rollback, deployment rollout.
10. **Record the decision.** Why this starter was chosen, Boot version, maintainer, and review date.

For example, for "progress updates every 5 seconds": try HTTP polling first, then SSE for one-way server push; consider WebSocket only for true bidirectional messaging or a contract polling/SSE cannot meet. Never cite unmeasured assumptions claiming WebSocket is faster in every scenario.

### Dependency Decision Record Template

~~~markdown
# Dependency Addition Decision

## Use case
- Consuming clients:
- Required contract/protocol:
- Latency/throughput/availability SLO:

## Alternatives considered
- Existing HTTP/API:
- Smaller library or existing client:
- New protocol/starter:

## Impact
- Direct + transitive dependencies:
- Auto-configuration, beans, routes, ports:
- Security/TLS/authn/authz:
- Memory/threads/startup/packaging:
- Observability and owner:

## Testing/Deployment
- Unit/integration/contract tests:
- Load/cancel/error tests:
- No unexpected public endpoints:
- Rollback plan:

## Decision
- Add/keep/reject:
- Rationale and review date:
~~~

This template is **decision documentation**, never a runtime configuration file. It ensures the team knows why a starter exists instead of seeing it left behind from an Initializr wizard selection.

## 19. Safely Removing a Starter That Serves No Need

When a starter looks unused, do not delete it hastily:

1. Check whether it is a **direct** or **transitive** dependency; trace its path in the tree.
2. Search Java/Kotlin imports, XML/config properties, generated code, SPI files, runtime reflection, and integration clients.
3. Ask public protocol/legacy client owners: a low-traffic WebSocket endpoint might still be an active contract.
4. Capture baselines: API/contract tests, dependency tree, actual port mappings, bean conditions, security controls, and metrics.
5. Remove **only that direct dependency** on a test branch; avoid unrelated edits in an audit change.
6. Run `mvn test`, packaging, e2e/security/contract tests, and runtime smoke checks.
7. Verify framework/HTTP client connector selection after the classpath changes; for example, `WebClient` might switch underlying HTTP connectors.
8. Measure real benefits (artifact, startup, memory/CVE scope) against regression risk.
9. Roll out via canary/staging if needed, watch metrics, and retain a rollback path.
10. Update the decision record and clean up orphaned properties/configs **only after** verifying they are genuinely unused.

**Never remove required security, validation, or observability** to shave off a few megabytes. "No code import" and "compile passed" never guarantee runtime reflection or external clients remain intact.

### When Should You Keep a Starter?

- Real consumers or committed contracts rely on it.
- Functionality operates via auto-config, runtime SPI, or generated code.
- Removal carries high risk and unmeasured benefit.
- The starter provides required security, validation, or operability.
- A scheduled migration with a deprecation date is safer than sudden removal.

## 20. CI and Review Guardrails to Prevent Dependency Sprawl

A CI pipeline/PR review can verify:

~~~text
1. Compilation and unit tests
2. Integration + contract tests
3. Dependency graph delta and SBOM
4. Vulnerability and license review
5. Auto-configuration/startup smoke
6. Actual endpoint/port inventory
7. Authorization/TLS/CORS checks where relevant
8. Performance smoke on representative load
9. Dependency decision rationale and rollback
~~~

Do not fail CI merely because total JAR count crossed an arbitrary number. Instead enforce clear policies on untrusted dependency sources, known exploitable advisories, manual version overrides, unreviewed new protocols, unexpected management endpoints, or open listeners. Important features justify larger dependencies; quality is measured by **risk vs. value**, not raw byte size alone.

Hypothetical inventory table:

| Dependency | Reason Present | Evidence | Action |
|---|---|---|---|
| `starter-web` | REST JSON MVC | HTTP integration tests | Keep |
| `starter-test` (`test` scope) | Regression suite | `mvn test` | Keep in test scope |
| `starter-webflux` | No `WebClient` or reactive server | No tests or use case | Investigate |
| `starter-websocket` | No handlers or duplex clients | No contract | Investigate |
| `starter-graphql` | No schema or consumers | No contract | Investigate |
| `starter-actuator` | SLO/production management | Monitoring + auth tests | Keep if required |

This is purely illustrative, **not the audit output of a real repository**. "Investigate" means evidence is still incomplete, not an order to delete immediately.

## 21. Misconceptions to Avoid

| Misconception | More Accurate Reality |
|---|---|
| "Microservices must use gRPC." | HTTP/JSON may suffice; gRPC needs matching contracts/clients/protobuf tooling |
| "Real-time means adding WebSocket." | Polling or SSE may suffice for one-way server push |
| "Adding WebFlux makes MVC non-blocking." | MVC stays prioritized by default when both are present |
| "Using WebClient forces the server onto Netty." | Outbound `WebClient` is independent of inbound MVC/Tomcat |
| "RSocket is just HTTP/2." | They are two distinct protocols |
| "GraphQL fixes all REST problems." | GraphQL introduces schemas, resolvers, and query auth/complexity management |
| "WebSocket starter opens an endpoint automatically." | Handler/broker mappings are still required |
| "Every starter opens a new port." | No; auto-config is conditional |
| "No direct import means unused dependency." | SPI, reflection, or auto-config may use it |
| "More starters mean better performance." | Measure first; complexity can increase |
| "Fewer starters always mean better security." | Never strip required security/validation |
| "Having a BOM means ignoring CVEs." | The BOM helps compatibility; patching policies still apply |
| "Passing compile means safe dependency removal." | Run integration, runtime, and external client tests |
| "Actuator exposes all endpoints by default." | Actuator HTTP exposure is restricted; secure anything extra you expose |
| "HTTP/2 requires GraphQL or gRPC." | HTTP/2 is a capability of HTTP servers and clients |
| "Adding the GraphQL starter creates a complete API." | Schema, resolvers, transport, and security are still required |
| "Every transitive dependency is bloat." | Many JARs are essential parts of the selected starter |

## 22. Exercises with Suggested Solutions

**Exercise A — REST-only:** a service has three GET and two POST JSON endpoints, calls a partner over blocking HTTP, and has no GraphQL/WebSocket clients. Choose the minimal starters.

*Guidance:* `starter-web` + `starter-test`, expanding intentionally for Security/Validation/DB/observability as product needs require. Use `RestClient`; do not add WebFlux server or RSocket.

**Exercise B — check web application type:** run the lab and verify `ServletWebServerApplicationContext`. Add `starter-webflux` on a test branch, re-run tests and the conditions report; the app still typically runs MVC. Explain why.

**Exercise C — real-time dashboard:** the server emits job progress every 5 seconds and the browser never sends messages over a persistent socket. Compare polling vs. SSE and identify what condition would actually demand WebSocket.

**Exercise D — GraphQL:** evaluate whether the frontend truly needs flexible cross-domain projections. If yes, design the schema, query complexity limits, field-level auth, and contract tests; if not, optimize REST first.

**Exercise E — dependency graph:** use `mvn dependency:tree` to trace how Tomcat and Jackson enter runtime. Run `mvn dependency:analyze` and explain why static analysis does not prove those libraries are unused.

**Exercise F — security review:** when adding any new protocol endpoint, list required checks: authN/authZ, TLS, payload bounds, CORS/origin for browsers, rate limits, connection lifecycles, timeouts/cancellation, logging redaction, and proxy routes.

**Exercise G — safe removal:** a service carries a WebSocket starter left over from an old prototype. Build a test/metric baseline and removal plan; never declare "nobody uses it" just because one package lacks a handler.

## 23. Review Questions

**1. Is a starter a new protocol?**  
No. A starter is a dependency bundle; a protocol is a communication contract.

**2. Why does Boot 3.3 usually pick MVC when both `web` and `webflux` are present?**  
Application-type precedence prioritizes Spring MVC when both frameworks are on the classpath, supporting MVC apps that use `WebClient` outbound.

**3. Does `RestClient` require `starter-webflux` in MVC?**  
No. `RestClient` comes with Spring Web 6.1 and works with `starter-web`.

**4. Does `WebClient` force an MVC server onto Netty?**  
No. The HTTP client and HTTP server are independent choices.

**5. Does SSE require the WebSocket starter?**  
No. SSE uses HTTP `text/event-stream`; MVC already supports `SseEmitter`.

**6. Does the GraphQL starter provide a complete schema and resolvers out of the box?**  
No. You still provide schemas, data fetchers, and transport/application configuration.

**7. Is RSocket the same as HTTP/2?**  
No. RSocket has its own protocol and interaction semantics.

**8. Does adding a starter guarantee opening another public port?**  
No. It depends on conditions and explicit configuration.

**9. What does Maven `dependency:tree` show?**  
Direct/transitive dependencies, scopes, and resolution paths; it does not prove a runtime feature is active.

**10. What does the Conditions Evaluation Report show?**  
Why Boot auto-configuration conditions matched or did not match in the real context.

**11. If source code has no imports, can you delete a dependency right away?**  
No. It may be used via reflection, auto-config, SPI, or runtime integrations.

**12. Why shouldn't you override Spring versions arbitrarily?**  
It risks breaking BOM-tested compatibility and runtime behavior.

**13. Why shouldn't you drop Spring Security or Validation just for artifact size?**  
Those controls enforce required security and correctness; balance risk properly.

**14. When is adding WebSocket justified?**  
When clients need a full-duplex contract, latency/message requirements warrant it, and connection lifecycles are properly operated.

**15. When is adding a starter right even if the artifact grows?**  
When a concrete requirement, test suite, security/operations owner, and evaluated benefit justify it.

**16. Does testing HTTP 200 alone prove removing a dependency is safe?**  
No. Also check security, error paths, runtime auto-config, external consumers, and performance.

## 24. Official Documentation

- [Spring Boot 3.3 – First Application](https://docs.spring.io/spring-boot/3.3/tutorial/first-application/): starters, classpath, and auto-configuration.
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC, Servlet stack, and embedded servers.
- [Spring Boot 3.3 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux, web application type, and having both starters.
- [Spring Boot 3.3 – Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): `RestClient`, `WebClient`, `RestTemplate`, and auto-configured builders.
- [Spring Boot 3.3 – Spring for GraphQL](https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html): GraphQL transports, WebSocket disabled by default.
- [Spring Boot 3.3 – RSocket](https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html): transports and server configuration.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Tomcat/Reactor Netty and swapping servers.
- [Spring Boot 3.3 – Build Systems](https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html): starters and dependency management.
- [Spring Boot 3.3 – Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): conditional configuration, conditions report.
- [Spring Boot 3.3 – Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposure and management security.
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): `dependency:tree`, `dependency:analyze`.
- [Gradle – Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencyInsight`.
- [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html): BOM version alignment.