# Observing HTTP Calls and Propagating Traces Through Managed Builders in Spring Boot

When a request traverses multiple services, knowing that the server received a request is not enough. We also need to know where the application made outbound HTTP calls, what status codes returned, how long each took, whether errors or timeouts occurred, and how to **connect calls across multiple services into a single distributed trace**. In Spring Boot, the least error-prone path is creating **RestClient**, **RestTemplate**, or **WebClient** from **Spring Boot–managed, auto-configured builders**. These builders receive HTTP client settings, Micrometer Observation, and trace-context propagation; instantiating clients directly can silently drop instrumentation even while the HTTP logic still runs.

This lesson belongs to the **Spring Boot - web-runtime** module, parent topic **HTTP client**. Examples focus on **Spring Boot 3.3.13, Java 17, Spring MVC, RestClient.Builder, Spring Boot Actuator, Micrometer Observation, Micrometer Tracing, and OpenTelemetry/Zipkin**. Specific code and packages belong to the Spring Boot 3.3 branch; do not copy Spring Boot 4 packages into a 3.3 project. Security and operational requirements around trace propagation, sensitive data, timeouts, sampling, and production environments are woven throughout.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **logs, metrics, and traces**, along with **observation**, **span**, **trace ID**, **span ID**, **parent span**, and **trace context**.
2. Explain why injecting an auto-configured **RestClient.Builder** automatically records **http.client.requests** and propagates context when Micrometer Tracing is configured.
3. Know when to pick **RestClient** (synchronous), **RestTemplate** (legacy), or **WebClient** (reactive) and their corresponding builders.
4. Build a runnable project: the server receives **GET /demo/entry**, uses a managed `RestClient` to call **GET /demo/target**, and both requests share the same trace ID with different spans.
5. Spin up a dev tracing backend and inspect **Zipkin**, **Actuator metrics**, correlation IDs in logs, and the **traceparent** header.
6. Distinguish **instrumentation** from **exporting**: having local metrics or spans does not guarantee traces successfully reached the collector.
7. Write HTTP-client behavior tests with **@RestClientTest + MockRestServiceServer**, and understand why slice/MockMvc tests alone do not prove network trace propagation.
8. Avoid anti-patterns like **RestClient.create**, **RestClient.builder**, **new RestTemplate**, and **WebClient.create** bypassing Boot builders on paths requiring tracing.
9. Customize clients additively through builders/customizers without overwriting `ObservationRegistry` or context propagators.
10. Diagnose lost traces across thread boundaries, WebFlux Reactor, proxies, retries, sampling, and mismatched propagation header formats.

Prerequisites: Java 17+, Spring Boot, REST controllers, Maven, HTTP clients, JSON, HTTP headers, and basic logging concepts.

## 2. What Is HTTP Call Observability?

### 2.1. Three Pillars of Observability

| Pillar | Data | Example | Question answered |
| --- | --- | --- | --- |
| **Logs** | Discrete events with messages and fields, often carrying trace ID / span ID. | Client called catalog and timed out at 12:30. | What happened? |
| **Metrics** | Aggregated numbers over time with cardinality-controlled tags. | Count, duration, and status of **http.client.requests**. | How do request rate, latency, and error rate shift over time? |
| **Traces** | Spans linked by parent/child relationships within one trace. | GET /orders → client GET /catalog → catalog server. | Which steps did the request take, and which part was slow? |

**Micrometer Observation** is the unified abstraction for wrapping an operation with a lifetime and metadata. An observation can feed **metrics**, **tracing**, or both via observation handlers. A **Metric** is not a **Trace**; metrics aggregate across many requests, while a trace shows the execution tree of one specific request.

### 2.2. Trace ID, Span ID, and Parent/Child

~~~text
Browser GET /demo/entry
         |
         v
Spring MVC server span (A)
    traceId = T
    spanId  = A
         |
         v
RestClient outbound HTTP span (B)
    traceId = T
    spanId  = B
    parent  = A
         |
         +-- HTTP request with propagation headers -->
                 Spring MVC /demo/target span (C)
                      traceId = T
                      spanId  = C
                      parent  = B
~~~

All three spans share the **same trace ID** while having **different span IDs**. One trace can contain dozens of spans. Never expect the incoming server span ID and outgoing client span ID to match. If an app simply prints a random request ID per service without context propagation, logs may resemble tracing but lack parent/child structure.

### 2.3. What Is Propagation?

Over HTTP, client instrumentation **injects** trace context into request headers. Downstream server instrumentation **extracts** the context, starts the next server span, and links it to the upstream parent span. With W3C Trace Context, headers look like:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor-data-if-present
~~~

Meaning of the four parts of `traceparent`:
- **00**: format version.
- **32 hex characters**: trace ID.
- **16 hex characters**: parent span ID sent by the caller.
- **2 hex characters**: trace flags, such as the sampled bit.

The **tracestate** header may be absent. Outside W3C, some systems use **B3** or B3 multi-header formats. Spring Boot 3.3 exposes **management.tracing.propagation.consume/produce/type**, defaulting typically to consuming W3C/B3 and producing W3C as documented. Do not force emitting every format simultaneously without an interoperability need; changing formats requires checking the entire service chain and gateways.

**A Trace ID is not a credential**; it never replaces authentication/authorization or user identity. Never trust a client-supplied `traceparent` for access decisions or treat arbitrary baggage as trusted input.

### 2.4. Not All HTTP Headers Appear Automatically

Depending on classpath and configuration:
- Only **Spring Web**: the client makes HTTP calls, without metrics/tracing automatically.
- **Spring Boot Actuator** + metrics infrastructure: HTTP-client observations can produce **http.client.requests**.
- **Micrometer Tracing bridge + tracer implementation + exporter**: creates trace spans, MDC correlation IDs, and exports traces to a backend.
- Using **auto-configured client builders**: key customizers, including instrumentation, attach to the client.
- Using manually constructed clients bypassing Boot builders: customizers may be skipped; requests still return HTTP 200 without spans or `traceparent`.

Never assume "tracing is broken" just because a span does not show up in the UI; sampling, exporter failures, network, backend indexing, or test slices may explain it.

## 3. Managed Builders Are the Central Hub

### 3.1. Three APIs and Their Builders

| HTTP client | Right Spring Boot builder | Model | When to use |
| --- | --- | --- | --- |
| **RestClient** | Inject **RestClient.Builder** | Blocking / imperative, fluent API | Spring MVC apps, synchronous service code. |
| **RestTemplate** | Inject **RestTemplateBuilder** | Blocking / legacy | Existing projects or libraries relying on RestTemplate. |
| **WebClient** | Inject **WebClient.Builder** | Reactive / non-blocking | WebFlux/Reactor, reactive services, appropriate streaming. |

**Spring Boot 3.3** creates and configures a **prototype `RestClient.Builder`**, so each injection point normally gets a builder pre-wired by auto-configuration. `WebClient.Builder` is likewise configured as a prototype when WebFlux client support is on the classpath. For **RestTemplate**, Boot supplies **RestTemplateBuilder** instead of registering a single default `RestTemplate` bean.

A Boot-configured builder integrates:
- HTTP message converters/codecs and request factory/connector.
- Client, SSL, and resource settings matching the version/classpath.
- **ObservationRegistry** and Micrometer HTTP client instrumentation.
- **Trace context propagation** onto downstream requests when tracing is enabled.
- Application- or framework-registered customizers.

Injecting the builder does not guarantee every trace is stored by the backend: sampling decisions, exporters, and collectors still govern delivery.

### 3.2. Right and Wrong

**Recommended in a Spring-managed bean:**

~~~java
@Service
public class PartnerService {
    private final RestClient client;

    public PartnerService(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://partner.example.test")
                .build();
    }
}
~~~

This snippet illustrates injection only and **is not a standalone compilable file**, lacking imports and service methods. The runnable project in Section 6 provides complete files.

**Ways to lose auto-configuration easily:**

~~~java
RestClient clientA =
        RestClient.create("https://partner.example.test");

RestClient clientB =
        RestClient.builder()
                .baseUrl("https://partner.example.test")
                .build();

RestTemplate template = new RestTemplate();

WebClient webClient =
        WebClient.create("https://partner.example.test");
~~~

These are valid Spring APIs, not syntax errors. However, calling them directly **does not automatically include Spring Boot's Observation customizers and trace propagation**. You can attach instrumentation manually if truly needed, but the burden falls on you. For typical Boot apps, injecting the managed builder is far less error-prone.

### 3.3. Builder State and Customization Scope

**RestClient.Builder/WebClient.Builder** are stateful: calling `baseUrl`, `defaultHeader`, `filter`, `requestFactory`, etc., affects clients built from that builder afterward. Thus:

- In **constructor injection** of a `@Service`, configuring the builder for one dedicated client and calling `.build()` is clean.
- If one place needs multiple different configs from the same injected builder, call **clone()** before customizing each client.
- Never mutate a shared mutable builder across threads or components expecting independent client configurations.
- With `RestTemplateBuilder` in Boot 3.3, configuration methods typically return **a new builder**; do not apply `RestClient.Builder` mutability assumptions.
- For application-wide config, declare **RestClientCustomizer**, **RestTemplateCustomizer**, or **WebClientCustomizer** beans instead of rebuilding an empty builder.

**Never declare a fresh empty `@Bean RestClient.Builder`** just to set a base URL, as that can override Boot's builder and lose customizers. If you must define a custom builder bean, use compatible configurers/customizers; preferably, inject Boot's builder and register a `RestClient` bean instead.

### 3.4. Instrumentation Does Not Make Every Custom Header Safe

An HTTP request interceptor/filter used to log or inject headers can:
- leak `Authorization`, `Cookie`, `Set-Cookie`, or payloads;
- consume the body stream so downstream receives an empty body;
- emit duplicate spans if wrapping observation redundantly at the HTTP client layer;
- record high-cardinality URLs into metrics;
- overwrite `traceparent`/`tracestate` and break parent spans.

Rely on the framework's built-in instrumentation; only add non-sensitive, bounded business metadata.

## 4. Spring Boot Actuator, Micrometer Observation, and Micrometer Tracing

### 4.1. Dependencies by Goal

| Goal | Core dependency | Outcome |
| --- | --- | --- |
| HTTP client execution | `spring-boot-starter-web` or matching `webflux` | HTTP request/response handling. |
| Observation and metrics | `spring-boot-starter-actuator` | Micrometer Observation and metrics instrumentation. |
| Distributed tracing (OpenTelemetry) | `micrometer-tracing-bridge-otel` | Bridges Observation to the OTel tracer. |
| Export traces to Zipkin | `io.opentelemetry:opentelemetry-exporter-zipkin` | Sends spans to Zipkin when backend is ready. |
| Export traces to OTLP | `io.opentelemetry:opentelemetry-exporter-otlp` | Alternative export to an OTLP collector. |
| REST client tests | `spring-boot-starter-test` | JUnit, `@RestClientTest`, `MockRestServiceServer`. |

In real projects, pick **one consistent tracer/exporter stack** rather than mixing Brave, the OTel Java Agent, Spring Boot Micrometer instrumentation, and uncoordinated auto-instrumentations. If using an external Java agent, check for duplicate spans and coordinate configuration.

### 4.2. ObservationRegistry and Metric Name

Spring Boot Actuator instruments **RestClient, RestTemplate, and WebClient** when built via managed builders. Per Boot 3.3 documentation, the default client metric is typically named:

~~~text
http.client.requests
~~~

HTTP client observations usually attach tags such as HTTP method, status, URI template, host/client name, and outcome/exception depending on Spring Framework and instrumentation versions. These tags are not a rigid domain API contract; verify against your exact version before relying on specific tag names.

For the HTTP server, the counterpart metric is typically **http.server.requests**—do not confuse it with outbound HTTP calls. A single `GET /demo/entry` can produce **one server observation**, **one client observation**, and **one downstream server observation**, not just one total request metric.

### 4.3. Tracing Bridge and Sampling

Spring Boot 3.3 supports Micrometer Tracing with OpenTelemetry or Brave. Dev configuration example:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Boot 3.3 defaults sampling roughly to **10%**. Set **1.0** in the lab so every request is easy to find in the backend; production must pick a rate matching traffic volume, storage cost, forensic needs, and sampling policy. A trace missing from Zipkin under low sampling **does not prove propagation is broken**.

**Sampling governs whether spans are recorded/exported**, while propagation metadata may still flow depending on tracer and upstream decisions. Never invent a brand-new trace ID when `sampling=false`; inspect headers and trace context in compatible systems to verify.

### 4.4. Baggage and Correlation IDs

**Trace ID** links spans together; **span ID** identifies each segment. **Correlation IDs in logs** let you filter logs for a trace; with Micrometer Tracing active, Spring Boot 3.3 typically populates `traceId`/`spanId` into MDC and the default log pattern. Never use a **session ID** or access token as a correlation ID.

**Baggage** is extra metadata propagated with the context and can cross service boundaries. Never put passwords, session cookies, access tokens, emails, or sensitive personal data into baggage. Baggage headers can traverse third parties if outbound propagation isn't restricted. Use standardized service/tenant identifiers reviewed by security if genuinely needed.

## 5. Trace Context on the Wire: W3C and B3

### 5.1. A Request Carrying `traceparent`

~~~http
GET /demo/target HTTP/1.1
Host: localhost:8080
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-8d8cf3d2b21814db-01
~~~

**traceId** normally stays unchanged across hops of the same trace. The **parent span ID** inside the outbound `traceparent` is the ID of the span representing the outbound call (or injected context), not necessarily the downstream server span ID. When the server receives the request, it starts a new span whose parent is the client's span.

**Never assert that `traceparent` keeps the same 16-character spanId before and after a hop**; each new span needs its own identifier. In the lab, verify that the incoming trace ID matches the downstream trace ID and inspect the span hierarchy in Zipkin.

### 5.2. B3 and Mixed Formats

In legacy Spring Cloud Sleuth systems, B3 headers were common. Spring Boot 3.3 lets you configure consume/produce propagation formats. If service A emits W3C while gateway B only forwards B3, downstream may start a new trace. Clarify the propagation contract:
- which format upstream sends;
- which headers gateways/proxies preserve or strip;
- which formats downstream tracers consume;
- whether trust boundaries require starting a fresh trace;
- how sampling flags and baggage are preserved or capped.

Never convert formats manually by copying `traceId` into a single custom header; that does not produce a distributed trace with parent/child links.

### 5.3. W3C Headers Are Not Authentication

`traceparent` and `tracestate` are **caller-supplied data**, not cryptographic signatures. Receiving services must still enforce authentication and authorization independently. To prevent trace spoofing or flooding, enforce trust-boundary policies at ingress—never treat a trace ID as a session or token.

### 5.4. Proxies and Gateways

A reverse proxy or API gateway may:
- participate in the trace if instrumented;
- pass `traceparent`/`tracestate` through untouched;
- emit its own span;
- start a new trace if policy resets untrusted headers at the boundary;
- drop headers or translate to B3.

If a service emits HTTP metrics yet traces fail to link, inspect **actual outbound headers** and intermediate proxies before blaming controllers. Never log all headers in production to debug, as that leaks credentials.

## 6. Designing the Runnable Demo

The project simulates three spans in **a single JVM** by having `/demo/entry` call `/demo/target` over a real HTTP request. This loopback self-call is **strictly a lab technique**, never a production architecture. The goal is clearly observing the **inbound server span**, **outbound client span**, and **target server span**.

~~~text
curl /demo/entry
     |
     v
Tomcat server: /demo/entry
     |
     v
RemoteDirectoryClient
   (managed RestClient.Builder)
     |
     +--- HTTP GET http://localhost:8080/demo/target
               traceparent injected
                          |
                          v
                  Tomcat server: /demo/target
                      extract context
                          |
                          v
                  JSON: traceId, spanId
     |
     v
/demo/entry JSON with upstream and downstream traceIds
~~~

**Expected result:** both trace IDs in the JSON **match**; the downstream span ID differs from the upstream server span ID. Hex IDs are randomized per trace, so do not expect fixed literal stdout like an algorithm exercise. Zipkin displays the linked spans when the exporter/backend is running.

### 6.1. Directory Structure

~~~text
trace-client-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/httptrace/
    HttpTraceApplication.java
    TargetReply.java
    RemoteDirectoryClient.java
    TracingDemoController.java
  src/main/resources/
    application.yml
  src/test/java/com/example/httptrace/
    RemoteDirectoryClientTest.java
~~~

Uses **Java 17**, Maven, and Spring Boot **3.3.13** matching the packages/classes below. If generating from Spring Initializr, select **Spring Web**, **Spring Boot Actuator**, and **Spring Boot Starter Test**, then add the tracing bridge and exporter from the POM below.

### 6.2. `pom.xml` — Versions and Dependencies

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>trace-client-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-exporter-zipkin</artifactId>
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

**Do not pin separate versions of Micrometer, OpenTelemetry, or Spring Framework** when using the Spring Boot BOM. Version 3.3.13 is a fixed learning baseline, not a recommendation to run an end-of-support patch in production. When upgrading major versions, re-check packages and properties; Boot 4 examples use different APIs.

### 6.3. `application.yml` — Dev Tracing and Metrics

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: trace-client-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

**Explanation:**
- **spring.application.name** serves as the service identity in observability/tracing when applied.
- **server.port: 8080** must match `RemoteDirectoryClient`'s base URL for the loopback lab.
- **metrics endpoint** is exposed here only for learning locally. In production, never expose all Actuator endpoints to the public Internet.
- **sampling probability=1.0** is convenient when testing a few requests. In production, pick a lower rate matching traffic and cost.
- **management.zipkin.tracing.endpoint** targets local Zipkin. If Zipkin is not running yet, the HTTP API **still works**, though the exporter may log warnings/errors when shipping spans; do not mistake that for an application request failure.

If you do not want to run Zipkin, you can temporarily drop the exporter dependency/config and study observations/metrics alone; to inspect parent/child spans in the UI as shown here, run Zipkin.

### 6.4. Main Class

**src/main/java/com/example/httptrace/HttpTraceApplication.java**

~~~java
package com.example.httptrace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpTraceApplication.class, args);
    }
}
~~~

### 6.5. Data Model for the Response

**src/main/java/com/example/httptrace/TargetReply.java**

~~~java
package com.example.httptrace;

public record TargetReply(
        String message,
        String traceId,
        String spanId) {
}
~~~

Java **record** is built-in since Java 16, so Java 17 runs it cleanly. Jackson provided by `spring-boot-starter-web` serializes/deserializes it. **traceId/spanId** appear in the response **only because the demo intentionally returns them for verification**; production APIs typically log correlation IDs per policy rather than exposing full trace metadata to callers.

### 6.6. The Key HTTP Client: Injecting the Managed Builder

**src/main/java/com/example/httptrace/RemoteDirectoryClient.java**

~~~java
package com.example.httptrace;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class RemoteDirectoryClient {
    private final RestClient client;

    public RemoteDirectoryClient(RestClient.Builder builder) {
        // Builder from Boot already has ObservationRegistry/customizers wired.
        this.client = builder
                .baseUrl("http://localhost:8080")
                .build();
    }

    public TargetReply fetchTarget() {
        return client.get()
                .uri("/demo/target")
                .retrieve()
                .body(TargetReply.class);
    }
}
~~~

**Why this code is the core of the lesson:**

1. **RestClient.Builder** is a Boot-auto-configured bean; constructor injection obtains the container-configured instance.
2. We **do not call** `RestClient.builder()` or `RestClient.create()` manually.
3. Actuator's **ObservationRestClientCustomizer** attaches the registry and instrumentation.
4. Tracing HTTP client instrumentation creates a client span and injects context into outbound headers. When the receiving server has compatible tracing instrumentation, it joins the same trace.
5. Build one client in the constructor and reuse it; avoid creating a new client per request.
6. **URI** is a fixed path here; for dynamic IDs, use **URI templates** like `.uri("/orders/{id}", orderId)` so metrics do not record unbounded raw paths.
7. The client uses a loopback endpoint for demo purposes; real deployments must load base URLs from environment config and configure network timeouts, retries, TLS, and authentication/authorization.

**Do not add `traceparent` headers manually** inside `fetchTarget`. Auto-instrumentation owns emitting headers consistent with the active span.

### 6.7. Controller Receiving and Propagating the Trace

**src/main/java/com/example/httptrace/TracingDemoController.java**

~~~java
package com.example.httptrace;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class TracingDemoController {
    private static final Logger log =
            LoggerFactory.getLogger(TracingDemoController.class);

    private final RemoteDirectoryClient client;
    private final Tracer tracer;

    public TracingDemoController(
            RemoteDirectoryClient client,
            Tracer tracer) {
        this.client = client;
        this.tracer = tracer;
    }

    public record EntryReply(
            String entryTraceId,
            String targetTraceId,
            String targetSpanId) {
    }

    @GetMapping("/entry")
    public EntryReply entry() {
        String currentTrace = traceId();
        log.info("Demo entry started");

        TargetReply remote = client.fetchTarget();

        log.info("Demo entry completed");
        return new EntryReply(
                currentTrace,
                remote.traceId(),
                remote.spanId());
    }

    @GetMapping("/target")
    public TargetReply target() {
        log.info("Demo target received request");
        return new TargetReply(
                "target-ok",
                traceId(),
                spanId());
    }

    private String traceId() {
        Span span = tracer.currentSpan();
        return span == null
                ? "no-active-span"
                : span.context().traceId();
    }

    private String spanId() {
        Span span = tracer.currentSpan();
        return span == null
                ? "no-active-span"
                : span.context().spanId();
    }
}
~~~

**Note:** the controller injects the auto-configured Micrometer Tracing **Tracer** bean. If you omit the tracing bridge and exporter from the POM, depending on auto-configuration, no `Tracer` bean may exist to inject—requiring changes to the controller. Use the code above with the **complete POM dependencies**.

`log.info` executes inside the server observation scope, so with tracing enabled logs can display MDC `traceId`/`spanId`. Those IDs aid diagnostics and contain no passwords, cookies, or payloads.

**/demo/entry** handles the inbound request; `RestClient` issues a **real outbound request** to **/demo/target**. The tracer at `/target` observes the second request's server span; **entryTraceId** and **targetTraceId** must match when propagation works, and `targetSpanId` differs from the entry server span ID under normal tracing.

### 6.8. Launching Zipkin in the Lab Environment

If Docker is available, run:

~~~bash
docker run --rm -p 9411:9411 openzipkin/zipkin
~~~

Open **http://localhost:9411** for the Zipkin UI. If the container is not ready, the exporter may log connection failures; check local port 9411 and networking. This command has no production security hardening and is meant only for labs or controlled environments.

Without Docker, point to an organization-approved Zipkin/OTLP collector and update the endpoint and exporter accordingly. **Never ship traces containing internal data to unapproved public services.**

### 6.9. Running the Application

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/trace-client-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvnw.cmd clean package
java -jar target/trace-client-demo-0.0.1-SNAPSHOT.jar
~~~

Use **mvn clean package** if no Maven wrapper is present. Run from the project root and ensure port **8080** is free. If you change the server port, also update the client's base URL in the demo; otherwise calls fail with connection refused.

### 6.10. Calling the Endpoint and Reading the Response

~~~bash
curl -i http://localhost:8080/demo/entry
~~~

Expect HTTP **200 OK** with a body **structured** like:

~~~json
{
  "entryTraceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "targetTraceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "targetSpanId": "00f067aa0ba902b7"
}
~~~

**The hex values above are format illustrations only**; every request generates new IDs. The two trace ID fields must match; do not expect the literal example `targetSpanId`. JSON property order can vary, and the controller does not echo `traceparent` as a response header. Seeing **no-active-span** signals a tracing configuration issue to fix, not a valid output.

In the Zipkin UI, select service **trace-client-demo** and search around the request time; you should see the `/demo/entry` server span, the HTTP client span, and the `/demo/target` server span linked in one trace. Exact span names can vary by instrumentation convention—verify against your version rather than assuming fixed names/statuses.

### 6.11. Verifying Inbound W3C Propagation

Send a valid `traceparent` from the client to the server:

~~~bash
curl -i \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  http://localhost:8080/demo/entry
~~~

With Micrometer Tracing/OpenTelemetry W3C propagation configured as in the lab, a valid incoming `traceparent` sets **entryTraceId** to **4bf92f3577b34da6a3ce929d0e0e4736**, and downstream preserves that trace ID when builder instrumentation is active. **Span IDs do not stay equal** to caller span ID `00f067aa0ba902b7`: the server creates a new span.

Headers from external clients never prove identity or permissions; never use them for authorization. Incompatible propagation formats or proxies stripping headers will cause the service to start a new trace.

### 6.12. Reading HTTP Client Metrics via Actuator

After calling **/demo/entry** at least once, query:

~~~bash
curl -i http://localhost:8080/actuator/metrics/http.client.requests
~~~

With Actuator metrics enabled, measurements/timers appear for recorded HTTP client observations. Before the first outbound call, the meter may not exist yet and Actuator may return **404**; that does not mean auto-configuration is broken. If it is still missing after calling `/demo/entry`, check the classpath, builder usage, and metrics settings.

You can check inbound metrics separately:

~~~bash
curl -i http://localhost:8080/actuator/metrics/http.server.requests
~~~

Do not assume there is only one single time series: the metric splits across tags such as method, URI template, status, and exception. For sustainable dashboards, keep tags low-cardinality (HTTP method, route template, service name)—never put raw user IDs, emails, tokens, or full query strings into low-cardinality tags.

**Actuator exposes `health/info/metrics` solely for the lab.** Production must lock down management endpoints via network isolation, authentication, and approved monitoring pipelines.

## 7. Testing REST Clients with @RestClientTest

### 7.1. Purpose of the Test Slice

Spring Boot 3.3 offers **@RestClientTest** to test HTTP client beans without starting a real web server. It auto-configures **RestClient.Builder**, **RestTemplateBuilder**, and **MockRestServiceServer**. The test below proves endpoint URLs and JSON mapping when the client makes HTTP calls. **It does not prove network distributed trace propagation**: a test slice does not replace real HTTP servers, span exporters, and wire propagation headers.

### 7.2. Runnable Test Class

**src/test/java/com/example/httptrace/RemoteDirectoryClientTest.java**

~~~java
package com.example.httptrace;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(RemoteDirectoryClient.class)
class RemoteDirectoryClientTest {

    @Autowired
    RemoteDirectoryClient client;

    @Autowired
    MockRestServiceServer server;

    @Test
    void fetchTargetDeserializesJsonResponse() {
        server.expect(requestTo(
                "http://localhost:8080/demo/target"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                "{\"message\":\"target-ok\",\"traceId\":\"t1\",\"spanId\":\"s1\"}",
                MediaType.APPLICATION_JSON));

        TargetReply result = client.fetchTarget();

        assertEquals("target-ok", result.message());
        assertEquals("t1", result.traceId());
        assertEquals("s1", result.spanId());
        server.verify();
    }
}
~~~

**Meaning:**

- `@RestClientTest` creates a narrow context for `RemoteDirectoryClient`, JSON converters, and the mock server.
- `MockRestServiceServer` intercepts requests built by the client, so neither port 8080 nor Zipkin needs to be running.
- `requestTo(...)` verifies URL, `method(GET)` verifies HTTP method, and `withSuccess` supplies a stub JSON response.
- Assertions verify record deserialization; status and content are mocked, so this does not prove what an external server actually returns.
- This test **does not verify propagation headers** because there is no real incoming span or network server; it is a client functional test.
- Code uses Spring Boot 3.3 packages; do not copy `@RestClientTest` package names from Boot 4.

### 7.3. Why `@SpringBootTest` May Not Export Traces by Default

Per Spring Boot 3.3 docs, tracing reporting components **are not auto-configured by default inside `@SpringBootTest`**. When needed in full integration tests, add **@AutoConfigureObservability** on a real Spring Boot test. On sliced tests, that annotation may provide a **no-op Tracer** and does not export spans from slices. Therefore:

- Test client contracts with `@RestClientTest`.
- Test end-to-end trace propagation with **real HTTP servers**, a collector/backend, or by inspecting headers on the receiving service.
- Do not report "missing spans in `@RestClientTest`" as a bug in your production builder.
- If testing automatic header injection in-process, configure controlled test tracing instrumentation with an explicit tracer, active Observation, and parent context.
- Avoid `Thread.sleep` for tracing exporters as a hard timing assertion; exporters typically batch asynchronously.

### 7.4. Runtime Verification

In a dev environment, run:

~~~bash
./mvnw test
./mvnw spring-boot:run
curl -i http://localhost:8080/demo/entry
curl -i http://localhost:8080/actuator/metrics/http.client.requests
~~~

Expect tests to pass, HTTP 200 on `/demo/entry`, matching trace IDs for `/demo/entry` and `/demo/target`, client metrics populated afterward, and linked spans in Zipkin when the exporter is connected. Do not conflate functional tests, metrics, and distributed trace export into one single check.

## 8. RestTemplateBuilder: Legacy Projects Still Get Instrumentation

In Spring Boot 3.3, **RestTemplate** is the classic synchronous client. Boot does not auto-create a single `RestTemplate` bean, but it provides an auto-configured **RestTemplateBuilder**. In existing projects using `RestTemplate`, avoid calling **new RestTemplate()** when auto-configured trace propagation is desired.

Standalone class example **when placed in the same package and demo project**:

~~~java
package com.example.httptrace;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LegacyDirectoryClient {
    private final RestTemplate template;

    public LegacyDirectoryClient(RestTemplateBuilder builder) {
        this.template = builder
                .rootUri("http://localhost:8080")
                .build();
    }

    public TargetReply fetchTarget() {
        return template.getForObject(
                "/demo/target", TargetReply.class);
    }
}
~~~

**`RestTemplateBuilder` in Spring Boot 3.3 is in `org.springframework.boot.web.client.RestTemplateBuilder`.** Newer Boot versions may relocate packages, so stick to your target version.

`RestTemplateBuilder` returns a new builder after each configuration method. It configures request factories, timeouts, basic auth, interceptors, SSL bundles, and customizers. Using Boot's builder lets Actuator attach HTTP observations instead of expecting auto-detection of manually constructed `RestTemplate` instances.

**You do not have to rewrite every `RestTemplate` to `RestClient` just to get traces.** As long as you build through the managed builder, legacy code remains instrumented. Migrating to `RestClient` is a separate API/maintainability decision—just ensure observability is preserved during any migration.

## 9. WebClient.Builder: The Reactive Client

When using **spring-boot-starter-webflux** or Reactor, **WebClient** is the non-blocking choice. Spring Boot provides a prototype **WebClient.Builder**; inject it when metrics and traces are required.

**Optional** class example that compiles only when **spring-boot-starter-webflux** is in the Spring Boot project; do not drop this into the initial Maven demo without adding the dependency:

~~~java
package com.example.httptrace;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDirectoryClient {
    private final WebClient client;

    public ReactiveDirectoryClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://localhost:8080")
                .build();
    }

    public Mono<TargetReply> fetchTarget() {
        return client.get()
                .uri("/demo/target")
                .retrieve()
                .bodyToMono(TargetReply.class);
    }
}
~~~

**WebClient.Builder** receives Boot's codecs, client connector/reactor resources, and observation integration when matching dependencies are present. **WebClient.create(...)** normally bypasses auto-configuration and customizers. Never drop casually from non-blocking into `.block()` during reactive request processing.

### 9.1. Context Propagation in Reactor

Tracing span context often lives in **ThreadLocal**, whereas reactive pipelines hop across threads. In Spring Boot 3.3, the property:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

can enable automatic context restoration across reactive operators via Micrometer Context Propagation and Reactor. Test it on your actual pipeline rather than assuming every custom scheduler, callback, or executor is covered automatically. If traces split across **publishOn, subscribeOn, or custom schedulers**, inspect Reactor Context, instrumentation, and context propagation rather than injecting `traceparent` manually.

### 9.2. Not Every Reactive Pipeline Is HTTP

A WebFlux app may also use Kafka, R2DBC, messaging, scheduled jobs, or timers; each integration has its own context semantics. HTTP client builders solve outbound HTTP instrumentation, not propagation into uninstrumented queues or workers.

## 10. Customizing Managed Builders Without Breaking Tracing

### 10.1. Customizing at the Injection Point

For a partner API:

~~~java
public PartnerApiClient(RestClient.Builder builder) {
    this.client = builder
            .baseUrl("https://partner.example.test")
            .defaultHeader("Accept", "application/json")
            .build();
}
~~~

This is a **constructor snippet inside a class with a `client` field**, not a standalone compilable file. It preserves Boot's customizers already applied to the builder. Use URI templates for variable paths and configure timeouts per network SLA. Never hardcode `traceparent`, authorization tokens, or sensitive tenant IDs in `defaultHeader`.

### 10.2. Application-Wide `RestClientCustomizer`

Spring Boot 3.3 provides **RestClientCustomizer** in **`org.springframework.boot.web.client`**. To add a non-sensitive header to every `RestClient` built from Boot's builder:

~~~java
package com.example.httptrace;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OutboundClientDefaults {

    @Bean
    RestClientCustomizer userAgentCustomizer() {
        return builder ->
                builder.defaultHeader(
                    "User-Agent", "trace-client-demo/1.0");
    }
}
~~~

This is an **optional, standalone compilable file** when added to the same project. The customizer applies to auto-configured builders, **not automatically to clients created via `RestClient.create`**. Restrict global customizers to genuinely shared settings; partner-specific basic auth or client certs belong on that partner's client.

When defining multiple `RestClient` beans with different base URLs, keep builder mutations local or clone the builder. Never share one mutable `RestClient.Builder` singleton and mutate `baseUrl` dynamically at runtime across hosts.

### 10.3. Never Override `ObservationRegistry` with an Empty One

Boot's **ObservationRegistry** holds observation handlers, conventions, and tracing integrations. If you create:

~~~java
ObservationRegistry registry =
        ObservationRegistry.create();
~~~

that is just a blank registry object. **Replacing the auto-configured registry with a fresh one** strips Boot/Micrometer Tracing handlers and causes spans/metrics to disappear. In application beans, **inject `ObservationRegistry`** from Spring and preserve the auto-configured HTTP client builder. If a special use case demands a custom registry, wire equivalent handlers and test thoroughly.

### 10.4. Creating Business Observations at the Service Layer

An HTTP client span measures outbound call duration, whereas a service may want a higher-level span/metric such as "lookup partner data" covering cache checks, validation, mapping, and retries. Example **optional class you can add to the demo**:

~~~java
package com.example.httptrace;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedLookupService {

    private final RemoteDirectoryClient client;
    private final ObservationRegistry registry;

    public ObservedLookupService(
            RemoteDirectoryClient client,
            ObservationRegistry registry) {
        this.client = client;
        this.registry = registry;
    }

    public TargetReply lookup() {
        return Observation.createNotStarted(
                "demo.directory.lookup", registry)
                .lowCardinalityKeyValue(
                        "partner", "local-demo")
                .observe(client::fetchTarget);
    }
}
~~~

**Observation.observe(Supplier)** starts/stops the observation and closes the scope even when an exception is thrown. This business observation can create a parent span wrapping the HTTP client span plus metrics when handlers are wired. Avoid manually wrapping the HTTP client's own observation at the exact same layer, which creates duplicate spans.

**Low-cardinality keys** must have a bounded set of values like `partner=local-demo`. To attach per-request IDs, never put `userId`/`email`/`orderId` into metric tags; consider **high-cardinality trace attributes** subject to security review and retention rules.

## 11. Crossing Thread and Async Boundaries

### 11.1. Why Does Context Get Lost?

Micrometer Tracing relies heavily on the thread's **current scope**. When a server request hands work off to another thread **without** propagating context, even a managed `RestClient` builder cannot see the lost parent observation and will start a fresh root span instead of a child span.

~~~text
Request thread:
  current trace T
       |
       +-- submit async task without propagation
                    |
                    v
             worker thread:
               no active trace context
                    |
                    v
             managed RestClient call
             may start unrelated trace
~~~

The builder cannot reconstruct parent context that was dropped before the call began.

### 11.2. `ContextPropagatingTaskDecorator`

When managing a Spring `TaskExecutor`, use Spring Framework's **ContextPropagatingTaskDecorator** to capture and restore context:

~~~java
package com.example.httptrace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncObservationConfiguration {
    @Bean
    ThreadPoolTaskExecutor traceAwareExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("trace-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

This is an **optional file**, unused in Section 6's synchronous HTTP lab unless you add async tasks. If used, submit tasks explicitly to **that `traceAwareExecutor`** (or wire the decorator onto `@Async`'s active executor)—simply declaring a bean does not instrument arbitrary thread pools.

Some Boot/TaskExecutor auto-configs can also enable propagation via configuration; check your version and thread boundaries. Never stash a `ThreadLocal`/Tracer span in a static global variable across threads, which cross-contaminates user requests and leaks context.

### 11.3. Scheduled Jobs Without an Incoming Trace

A scheduled job naturally has no parent server span. When it issues an outbound HTTP call, **starting a new root trace** is expected. Do not treat every root span as a bug; investigate only when a parent context existed and was dropped across a boundary.

### 11.4. Retries, Async, and Message Queues

- **Retries** can emit multiple client spans (one per attempt) or one logical observation wrapping retries, depending on where instrumentation and libraries sit.
- **Circuit breakers** can reject calls before sending HTTP; having no outbound HTTP span on an open-circuit rejection is normal.
- **Queues/Kafka** have their own header/context propagation; HTTP client builders do not inject context into message brokers.
- **CompletableFuture** using the ForkJoin common pool does not automatically carry `ThreadLocal` context.
- **WebClient/Reactor** requires verifying Reactor Context and configuration.

When debugging, compare trace IDs at every boundary and confirm "did an actual HTTP request leave the process?".

## 12. Logs, Metrics, and Traces: Reading Output Properly

### 12.1. Log Correlation Without Manually Inserting Trace IDs

With Micrometer Tracing, Spring Boot 3.3 typically adds MDC correlation IDs to logs in its documented format. Illustrative example:

~~~text
INFO ... [4bf92f3577b34da6a3ce929d0e0e4736-08beba2a4cf9e1d2] Demo entry started
INFO ... [4bf92f3577b34da6a3ce929d0e0e4736-5c45a01df13d9d7f] Demo target received request
~~~

**Values and format are illustrative only**; real logs include timestamps, app names, logger/class names, and more. Do not treat this exact log text as a brittle golden test. Two log lines sharing the same `traceId` with different `spanId`s demonstrate distributed correlation working properly.

**Never use a session ID, JWT, or `Authorization` header as a trace ID.** Traces and logs are often retained longer and viewed by broader operational teams.

### 12.2. Metrics by URI Template

When calling:

~~~java
client.get()
    .uri("/api/orders/{orderId}", 12345)
    .retrieve()
    .toBodilessEntity();
~~~

This is an **illustrative snippet on an already-built client**, not a standalone runnable program. Using URI templates lets observation conventions record the tag **/api/orders/{orderId}** instead of raw paths per order ID. Concatenating full URLs such as `/api/orders/12345` causes **high cardinality** and explodes metric time series.

Good low-cardinality tags include HTTP method, status family, route template, and service name. Avoid raw query parameters, user IDs, emails, account numbers, or large tenant sets. Even high-cardinality trace span attributes must follow security rules.

### 12.3. Client-Side and Server-Side Metrics Do Not Measure Identical Things

- **http.client.requests** measures from the caller's viewpoint, including network transit and waiting for response per instrumentation.
- **http.server.requests** measures from the server's viewpoint, excluding network transit before the request reaches the server.
- If a client times out, the server may still finish processing and record a successful status later; the two sides can report different outcomes.
- Proxies/gateways introduce their own queueing, retries, TLS handshakes, and connection reuse. Distributed tracing clarifies hops, though clocks are not synchronized to the nanosecond across machines.

### 12.4. Exporters and Collectors

Created spans are typically exported **asynchronously in batches**. When Zipkin is unreachable, spans may be dropped per retry/buffer policy while the HTTP app keeps serving responses. Never equate a health endpoint returning `UP` with a healthy tracing pipeline. In production, monitor:
- exporter errors and dropped spans;
- collector availability and backpressure;
- sampling rates and `serviceName`;
- network TLS/authentication to the tracing backend;
- log correlation and trace query latency;
- storage cost and retention.

Never ship user bodies or tokens to the tracing backend just to "debug more easily".

## 13. Step-by-Step Verification Scenario

### 13.1. Verify Dependencies and Builder Beans

1. Maven build succeeds on Java 17.
2. Spring `ApplicationContext` contains the auto-configured `RestClient.Builder`.
3. `RemoteDirectoryClient` constructor receives the builder rather than calling static factories.
4. Actuator is enabled and the HTTP client metric appears after a request.
5. Micrometer Tracing bridge + exporter are on the classpath when testing distributed traces.
6. Zipkin backend listens on port 9411 if inspecting the span tree.

If `/demo/entry` returns 500 because it cannot connect to `localhost:8080`, check which port the app is listening on and the client's `baseUrl`; that is not a tracing bug.

### 13.2. Positive Trace Test

1. Call `GET /demo/entry` from `curl`.
2. Receive 200 JSON and check **`entryTraceId == targetTraceId`**.
3. Open Zipkin and search service `trace-client-demo`.
4. Verify the incoming server span, outbound client span, and target server span appear in one trace.
5. Filter logs by trace ID and observe logs from both endpoints.
6. Query `/actuator/metrics/http.client.requests` afterward to inspect the recorded metric.

Key takeaway: the real HTTP call between endpoints flows through the managed builder rather than code copying a trace ID into the JSON manually.

### 13.3. Controlled Negative Comparison

In a **copy of the lab** (never modify production), temporarily replace `RemoteDirectoryClient`'s constructor with:

~~~java
public RemoteDirectoryClient() {
    this.client = RestClient.create(
            "http://localhost:8080");
}
~~~

This is an **illustrative replacement constructor for comparison**, not a separate class. HTTP calls still succeed, yet because it bypasses Boot's builder, auto Observation/customizers are not applied by default. Under the lab tracing config, `/demo/target` will likely receive **a different root trace** because no trace context travels on the outbound request, and HTTP client observations may be missing. **Do not claim from this comparison that `RestClient.create` can never be instrumented**: external Java agents or manual instrumentation can behave differently.

Once understood, restore the managed builder. Never leave modified lab/production code that breaks trace correlation.

### 13.4. Inbound `traceparent` Case

1. Send a request with a W3C `traceparent` from `curl`.
2. Verify `entryTraceId` matches the supplied trace ID when W3C consumption is configured.
3. Verify `targetTraceId` still equals `entryTraceId`.
4. In Zipkin, verify all spans share the trace with proper parent/child links.
5. Never use an external client's `traceparent` for authentication or authorization.

## 14. Common Mistakes and Fixes

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| `RestClient` sends HTTP fine, but **http.client.requests** is missing | Client built via `RestClient.create`/manual builder; missing Actuator/registry | Inject Boot-managed `RestClient.Builder`; verify Actuator and metrics config. |
| Metrics appear, yet trace ID is missing | Missing Micrometer Tracing bridge/tracer or sampling/exporter | Check POM, `management.tracing.enabled`, sampling, tracer bean. |
| Caller and downstream show different trace IDs | Context not injected, proxy stripped headers, W3C/B3 mismatch | Check managed builder and actual outbound/ingress `traceparent`. |
| `@RestClientTest` exports no spans to Zipkin | Test slice does not start reporting components | Test client contract separately; use `@AutoConfigureObservability` and runtime HTTP tests when needed. |
| Zipkin shows no trace despite HTTP 200 | Collector down, exporter error, sampling, wrong service name/time window | Check exporter logs, endpoint, sampling, collector health. |
| Span IDs differ while trace IDs match | Normal parent/child span behavior | Inspect the span tree; never expect identical span IDs. |
| Valid `traceparent` header ignored | Backend only consumes B3, proxy strips it, parser rejects format | Check `management.tracing.propagation.consume/produce/type`. |
| Trace lost after `@Async`/`CompletableFuture` | `ThreadLocal` scope not propagated across executor | Use `ContextPropagatingTaskDecorator`/proper executor instrumentation. |
| Trace lost inside Reactor pipeline | Context not restored across operators/custom schedulers | Enable `spring.reactor.context-propagation=auto` and test Reactor Context. |
| Duplicate HTTP client spans | Java agent + Micrometer both instrumenting, or custom interceptor creating extra span | Pick one instrumentation owner, adjust config, inspect span tree. |
| Metrics cardinality explodes | URI tag records raw IDs/queries or custom user tags | Use URI templates; remove PII/IDs from low-cardinality tags. |
| Request timed out while server logged 200 | Client timed out while server kept running | Compare client vs. server metrics and network/proxy timelines. |
| Outbound calls from newly created `RestTemplate` lose traces | `new RestTemplate()` bypassed auto-configured builder | Use Boot's `RestTemplateBuilder`. |
| `WebClient.create` is untraced | Bypassed `WebClient.Builder` customizers | Inject managed `WebClient.Builder`. |
| Tracing exporter logs many WARNs | Backend unreachable or misconfigured | Ensure collector reachable, fix egress, tune retries/batching. |
| Failures after Spring Boot major upgrade | Package APIs, builder config, and actuator properties changed | Consult version-specific docs; Boot 3.3 differs from Boot 4. |
| Logs lack `traceId` | Logged outside active span, missing instrumentation, or overridden log pattern | Check Micrometer Tracing MDC, log pattern, and scope. |

**Ordered debugging approach:** start from **how the client is built** → observation instrumentation → tracer activation → active span → outbound propagation headers → downstream extraction → sampling/exporter/backend. Never blame the collector before verifying `traceparent` actually left the caller.

## 15. Security and Operations

### 15.1. What Data Is Safe to Put in Traces?

Include only attributes needed for operations:
- service name, environment, route template;
- HTTP method, status, controlled outcome/exception class;
- low-cardinality peer service category or partner code;
- correlation IDs independent of credentials;
- business tags vetted by privacy/security review.

Never include:
- `Authorization` bearer tokens, Basic credentials;
- `Cookie`, `Set-Cookie`, `JSESSIONID`/`SESSION`;
- passwords, API keys, refresh tokens, CSRF tokens;
- card numbers, bank accounts, health records, and personal payloads;
- query strings containing sensitive data;
- default full request/response bodies of HTTP calls.

**The tracing backend is a data store with its own security risks**: enforce IAM, TLS, retention, masking, auditing, and access controls.

### 15.2. Never Trust `traceparent` as Proof of Identity

External clients can forge `traceparent` or trace IDs. Backends must never rely on them to grant permissions or bypass auth checks. To defend against spoofing and trace flooding, ingress proxies can restrict headers, sampling, and rate limits at the trust boundary while preserving consistent internal propagation per policy.

### 15.3. HTTP Client Reliability Is Separate from Observability

**Tracing does not replace** timeouts, retries, circuit breakers, or idempotency:
- Configure connect/read timeouts matching service SLOs.
- Retry only when requests are safe/idempotent with backoff/jitter/budgets.
- Never blindly retry side-effecting POSTs without an idempotency key.
- Protect DNS, TLS verification, proxies, and SSRF when URLs involve user input.
- Separate business 4xx from 5xx/timeouts and network errors.
- Monitor pool saturation and connection reuse in the HTTP client runtime.

Boot builders can be customized with timeouts, SSL, and request factories while preserving observation customizers; never use a trust-all `SSLContext` to "work around connection errors".

### 15.4. Sampling and Cost

One trace can hold hundreds of spans. **100% sampling** under high production traffic creates heavy cost and storage overhead. Tailor sampling to the environment:
- small demo/staging traffic: `1.0` for easy visibility;
- production: balanced rate per SLO and budget;
- preserve accurate log correlation;
- never assume every single request is stored in the trace backend;
- consider error-focused or tail sampling if your collector supports and validates it.

When sampling rates are low, aggregated metrics remain essential for tracking SLOs.

### 15.5. Managing Actuator

In the lab, **/actuator/metrics** is exposed for learning. In production, never blindly expose **env, configprops, heapdump, or httpexchanges** to the public Internet. Use a dedicated management port/network boundary, authentication, and approved Prometheus/monitoring pipelines.

## 16. Pre-Merge Quality Checklist

- [ ] Use Boot-auto-configured `RestClient.Builder` / `RestTemplateBuilder` / `WebClient.Builder` for all outbound HTTP needing observation.
- [ ] Never construct `RestClient`/`RestTemplate`/`WebClient` via static factories expecting automatic tracing.
- [ ] Configure Spring Boot Actuator and metrics registry/`ObservationRegistry` properly.
- [ ] Include Micrometer Tracing bridge + matching tracer/exporter when distributed tracing is required.
- [ ] Keep dev sampling high enough to observe and production sampling within budget.
- [ ] Verify inbound and outbound spans share the same trace ID with parent/child links.
- [ ] Ensure W3C/B3 propagation headers are supported end-to-end and not stripped or overwritten by proxies.
- [ ] Ensure HTTP client tags use URI templates rather than raw IDs or query PII.
- [ ] Confirm logs show `traceId`/`spanId` correlation without leaking tokens or cookies.
- [ ] Apply builder customizers additively without overwriting the registry or swapping in an empty builder.
- [ ] If using `@Async`/Reactor, verify context propagation across real threads and schedulers.
- [ ] Confirm **http.client.requests** metrics populate after calls and compare with server metrics.
- [ ] Ensure the Zipkin/OTLP collector works and exporter errors/drops are monitored.
- [ ] Cover URL, method, and JSON mapping with `@RestClientTest`, and real trace propagation with HTTP integration tests.
- [ ] Configure appropriate timeouts, retry/backoff/idempotency, and TLS verification.
- [ ] Restrict Actuator endpoints in production.
- [ ] Keep credentials and sensitive request bodies out of span attributes, baggage, and logs.
- [ ] Re-verify API packages and property names when changing Spring Boot major versions.

## 17. Self-Check Questions

**1. Can you create a `RestClient` with `RestClient.create()` and assume Spring Boot trace propagation works out of the box?** No. Direct creation bypasses the auto-configured `RestClient.Builder` and its customizers by default.

**2. What should you inject to get a `RestTemplate` with metrics/traces?** Inject Spring Boot's auto-configured **RestTemplateBuilder** and build the `RestTemplate`. Never use `new RestTemplate()` when auto-instrumentation is needed.

**3. Why do two different span IDs still belong to one trace?** They represent distinct operations linked via parent/child relationships under the same trace ID.

**4. If `http.client.requests` appears yet Zipkin has no spans, is the builder definitely wrong?** No. You might lack a tracer, sampling might exclude the trace, the exporter/collector might be failing, or the UI search window might differ.

**5. Is the propagated `traceparent` header a service authentication mechanism?** No. Any caller can send it; authentication and authorization are independent.

**6. Does `@RestClientTest` prove trace propagation between two real HTTP servers?** No. That slice uses a mock request server; end-to-end network/tracer integration tests are needed.

**7. Why can calling a managed `RestClient` inside `CompletableFuture` still start a new root trace?** The parent context may be lost when switching threads unless `ThreadLocal`/observation context is propagated.

**8. When upgrading from Boot 3.3 to a new major version, can you keep the exact same `RestTemplateBuilder` package?** Never assume so. Verify against the new version's docs and Javadoc.

**9. Should the tracing backend store passwords or authorization headers for easier debugging?** No. Those are sensitive credentials; traces and logs must restrict, mask, and protect them.

**10. Is leaving 100% sampling enabled forever the best approach?** No. It fits labs, whereas production must balance SLOs, cost, privacy, and storage capacity.

## 18. Official Documentation

1. [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): `RestClient.Builder`, `RestTemplateBuilder`, `WebClient.Builder`, prototype scope, and customization.
2. [Spring Boot 3.3 — HTTP Client Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): `http.client.requests` and observation customizers.
3. [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html): Micrometer Tracing, auto-configured builders, propagation, sampling, exporters, MDC correlation.
4. [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html): `ObservationRegistry`, low/high-cardinality key values, and Reactor Context.
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@RestClientTest`, `MockRestServiceServer`, and `@AutoConfigureObservability`.
6. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `management.tracing.*`, propagation formats, and actuator settings.
7. [Spring Framework 6.1 — HTTP Client Observability](https://docs.spring.io/spring-framework/reference/6.1/integration/observability.html): HTTP client observation context, conventions, and handler semantics.
8. [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`, and format/semantics of distributed tracing headers.

**Conclusion:** In Spring Boot applications needing outbound HTTP observability, **always inject Boot-managed builders** instead of manually instantiating `RestClient`, `RestTemplate`, or `WebClient`. This keeps auto-configuration and observation customizers intact, enabling **http.client.requests**, Micrometer Tracing, and context propagation to work seamlessly when dependencies are properly wired. Verify tracing by checking **the same trace ID across spans**, parent/child links, and collector data—and validate logs, metrics, thread boundaries, sampling, and security before shipping to production.