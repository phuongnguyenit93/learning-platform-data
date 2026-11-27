# Propagating Trace Context and Exporting Telemetry from Java Applications

## Learning objectives

After this lesson, you will be able to:

- Distinguish traces, metrics, and logs, and understand how the three signals complement one another during incident investigation.
- Explain traces, spans, parent-child relationships, span links, trace IDs, span IDs, sampling, and baggage.
- Describe W3C Trace Context (`traceparent`, `tracestate`, `baggage`), B3, and AWS X-Ray headers (`X-Amzn-Trace-Id`).
- Propagate trace context across HTTP, Spring MVC/WebFlux, `@Async`, executors, Reactor, and message queues.
- Use Spring Boot Actuator, Micrometer Observation/Tracing, and OpenTelemetry to instrument applications.
- Choose between Spring Boot Micrometer, the ADOT Java agent, or manual OpenTelemetry APIs without generating duplicate spans.
- Create custom observations/spans, attach controlled attributes, and inject trace IDs/span IDs into log MDC.
- Instrument AWS SDK for Java 2.x, S3/SQS, and understand propagation via message attributes/system attributes.
- Configure OTLP exporters and Collectors, sending traces to AWS X-Ray/CloudWatch Transaction Search, metrics to CloudWatch, and logs to CloudWatch Logs.
- Configure sampling, resource attributes, batching/retries, IAM, networking, and telemetry protection.
- Test propagation, verify telemetry, and diagnose lost context, duplicate spans, exporter timeouts, or `AccessDenied`.
- Understand the migration path from AWS X-Ray SDK/Daemon to OpenTelemetry.

**Module context:** This lesson belongs to the **Java and Spring Boot Applications** chapter in `CLOUD_PROVIDERS_AWS`. An AWS request can traverse API Gateway/ALB, a Spring Boot service, SQS/SNS, workers, databases, and S3. Trace context links these steps into an investigable journey; metrics show health trends; logs record detailed events.

> **Scope:** Examples use Spring Boot 3.5.x/4.x, Micrometer, OpenTelemetry, AWS Distro for OpenTelemetry (ADOT), AWS SDK for Java 2.x, Amazon CloudWatch, and AWS X-Ray. Dependencies/properties change across releases; always use the BOM and reference docs for your exact version. Service names, Regions, queues, accounts, and endpoints in examples are illustrative.

## 1. The problem: why does the API succeed yet the worker still fail?

A customer places an order. Orders API receives the request, saves data, and publishes an event to SQS. A worker consumes the message, calls the payment service, and stores an invoice in S3.

The API returns HTTP 202, yet minutes later the worker times out. Logs merely record `Payment gateway timeout`, with nothing linking the original request, message, worker instance, or retry attempt.

~~~mermaid
flowchart LR
    Client[Mobile / Web] --> API[Orders API]
    API --> DB[(Orders DB)]
    API --> Q[(SQS orders-events)]
    Q --> Worker[Payment worker]
    Worker --> Pay[Payment provider]
    Worker --> S3[(S3 invoices)]
    API -. logs .-> Logs[CloudWatch Logs]
    Worker -. logs .-> Logs
~~~

If every component invents its own request ID or drops trace context, operators see only disconnected log fragments. With proper propagation and instrumentation, one trace captures the HTTP server span, database/client spans, SQS producer/consumer spans, payment HTTP span, and S3 client span.

~~~mermaid
flowchart TD
    Root[Trace: create-order] --> HTTP[HTTP server span]
    HTTP --> Save[Save order span]
    HTTP --> Publish[SQS producer span]
    Publish --> Consume[SQS consumer span]
    Consume --> Payment[Payment HTTP client span]
    Consume --> Invoice[S3 PutObject span]
    Payment --> Error[Timeout event / error status]
~~~

**Core takeaway:** tracing helps only when context crosses process, thread, and message boundaries and components emit spans under a shared trace context.

## 2. Three observability signals

| Signal | Question answered | Example |
| --- | --- | --- |
| **Traces** | Which steps did a request take? Which step was slow or failed? | Trace ID, span duration, parent span |
| **Metrics** | How is the system behaving over time? | Request rate, error rate, p95 latency, queue depth |
| **Logs** | What happened at a specific moment? | Exception, business event, validation failure |

Investigation example:

| Data | Finding |
| --- | --- |
| Metric | p95 `POST /orders` jumped from 120 ms to 2.4 s |
| Trace | 1.9 s spent inside the SQS Send span due to throttling |
| Log | AWS SDK reported `ThrottlingException` with request ID and trace ID |
| Conclusion | API slowed due to message publish retries, not the database |

~~~mermaid
flowchart LR
    App[Java / Spring Boot] --> SDK[Micrometer / OpenTelemetry]
    SDK --> OTLP[OTLP]
    OTLP --> Collector[ADOT / CloudWatch Agent]
    Collector --> XRay[AWS X-Ray / Trace Search]
    Collector --> CWMetric[CloudWatch Metrics]
    Collector --> CWLogs[CloudWatch Logs]
~~~

Telemetry is observational data emitted by an application. Exporters send telemetry to an endpoint; Collectors/Agents receive, process, batch, filter, sample, and forward it to backends.

## 3. Traces, spans, trace IDs, and span IDs

A **Trace** represents the end-to-end journey of an operation across multiple components. A trace consists of **spans**. Each span carries an operation name, Trace ID, Span ID, Parent Span ID (if any), start/end timestamps, span kind, attributes, events, status, and links.

~~~text
Trace ID: 4efaaf4d1e8720b39541901950019ee5

Span A: POST /orders                 SERVER
  Span B: orders.validate            INTERNAL
  Span C: INSERT orders              CLIENT
  Span D: SQS SendMessage             PRODUCER

Span E: orders-events receive        CONSUMER
  Span F: payment.authorize           CLIENT
  Span G: S3 PutObject                CLIENT
~~~

- **Child span:** an operation invoked within a parent's context; common for HTTP clients, DB calls, or sub-methods.
- **Span link:** links a span to one or more other span contexts without forcing a parent-child hierarchy; useful for batch consumers or fan-in.
- **New root trace:** used when an operation is independent or policy requires trace separation.

A message consumer may continue the producer's trace or attach a link depending on semantics, framework, and batch behavior. Never force all messages in a batch under a single parent if they originated from different traces.

## 4. Trace context and W3C Trace Context

Trace context is metadata identifying which trace and parent span a request belongs to. With W3C Trace Context, standard headers are:

~~~http
traceparent: 00-4efaaf4d1e8720b39541901950019ee5-00f067aa0ba902b7-01
tracestate: vendor=value
baggage: tenant-tier=gold,workflow=checkout
~~~

`traceparent` structure:

~~~text
00 - 4efaaf4d1e8720b39541901950019ee5 - 00f067aa0ba902b7 - 01
|    |                                  |                  |
|    |                                  |                  +-- trace flags
|    |                                  +-- parent span ID
|    +-- trace ID (32 hex chars)
+-- version
~~~

- `trace-id`: trace identifier; must not be all zeros.
- `parent-id`: Span ID of the preceding operation; must not be all zeros.
- `trace-flags`: bit flags, where `sampled` indicates the sampling decision.
- `tracestate`: optional vendor-specific state.
- `baggage`: key/value pairs propagated across services independently of `traceparent`.

### Correlation ID is not trace context

A custom `X-Correlation-ID` helps grep logs, yet carries no parent or sampling metadata to build a distributed trace. Nor is a Trace ID an authentication token, session ID, or authorization claim.

## 5. W3C, B3, and AWS X-Ray propagation

| Format | Headers | Environment |
| --- | --- | --- |
| W3C Trace Context | `traceparent`, `tracestate`, `baggage` | Standard industry default |
| B3 single | `b3` | Zipkin/Brave and legacy systems |
| B3 multi | `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled` | Legacy systems |
| AWS X-Ray | `X-Amzn-Trace-Id` | AWS services integrated with X-Ray |

X-Ray header example:

~~~http
X-Amzn-Trace-Id: Root=1-5759e988-bd862e3fe1be46a994272793;Parent=53995c3f42cd8ad8;Sampled=1
~~~

- `Root`: X-Ray trace ID;
- `Parent`: parent segment/subsegment ID;
- `Sampled`: sampling decision.

AWS X-Ray supports W3C-generated trace IDs, though exporters must translate IDs into X-Ray format when sending trace documents. Older X-Ray exporters/Collectors may validate embedded timestamps in trace IDs and reject W3C IDs. Use a supported ADOT/Collector release.

The ADOT Java auto-instrumentation agent supports W3C, B3, and `X-Amzn-Trace-Id` out of the box. If a request arrives carrying multiple headers with differing trace IDs, services may pick different formats and split the trace. Choose produce/consume formats per architecture and verify both ends.

## 6. Propagation over HTTP

When an API receives a request, instrumentation extracts context from inbound headers, opens a server span, and binds the span context to the execution context; when calling the next service, the HTTP client injects context into outbound headers. The target service extracts context and starts a child span.

~~~mermaid
sequenceDiagram
    participant Client
    participant A as Orders API
    participant B as Inventory API
    Client->>A: POST /orders + traceparent
    A->>A: Extract parent context
    A->>A: Create SERVER span
    A->>B: GET /stock + new traceparent
    B->>B: Extract parent context
    B->>B: Create SERVER span
    B-->>A: Response
    A-->>Client: Response
~~~

### Use Spring Boot's HTTP client builders

Spring Boot auto-configures builders so trace context is injected automatically. `RestClient` example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
            .baseUrl("https://inventory.internal")
            .build();
    }
}
~~~

`RestClient.Builder` is auto-configured by Spring Boot. Never call `RestClient.builder()` manually and expect Spring's tracing instrumentation to attach.

With WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveHttpConfiguration {

    @Bean
    WebClient paymentWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://payments.internal")
            .build();
    }
}
~~~

When using `RestTemplate`, inject the auto-configured `RestTemplateBuilder`. When using Apache HttpClient/OkHttp/Feign/custom transports, verify instrumentation modules for that exact stack.

## 7. Propagation across message queues

Message queues introduce a temporal boundary: the producer finishes before the consumer runs. Producers must inject trace context into message metadata; consumers extract it to open linked spans.

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant SQS
    participant W as Payment worker
    API->>SQS: SendMessage + trace metadata
    SQS-->>W: Deliver message + trace metadata
    W->>W: Extract context / create CONSUMER span
    W->>W: Process payment
    W-->>SQS: DeleteMessage / acknowledge
~~~

- SNS fan-out to multiple SQS queues can spawn multiple consumer branches.
- Batch consumers can receive messages from distinct traces; use span links where appropriate.
- Retries/DLQs should retain event IDs and metadata needed for investigation.
- Delay queues/scheduled jobs may start a new root trace linked back to the original trace.

Trace context never replaces idempotency keys, message group IDs, or business transaction IDs.

## 8. AWS X-Ray trace headers and SQS system attributes

AWS SDK for Java 2.x instrumentation can inject context into outbound AWS API requests as `X-Amzn-Trace-Id`, which AWS managed services recognize.

With SQS `SendMessageBatch`, when X-Ray propagation is enabled, instrumentation can attach per-message context to each entry's `AWSTraceHeader` system attribute. This carrier is independent of HTTP request headers and does not consume one of the maximum 10 user message attributes.

This matters because HTTP request headers cover only the API call to SQS, whereas message system attributes carry context attached to each individual message. Exact behavior depends on AWS SDK version, OTel AWS SDK instrumentation version, and X-Ray propagation settings. Check the support matrix when using `SendMessage`, `SendMessageBatch`, SNS, or manually built SDK clients.

## 9. Spring Boot Observability: Micrometer Observation and Tracing

Spring Boot uses **Micrometer Observation** as a unified API for metrics and traces. An Observation is a named operation carrying context and key-values. Handlers turn observations into metrics, spans, and logging/correlation metadata.

| Component | Role |
| --- | --- |
| `ObservationRegistry` | Registry for observations |
| `Observation` | Measured/traced operation |
| Micrometer Tracing | Implementation-agnostic tracer API |
| `micrometer-tracing-bridge-otel` | Bridges Micrometer to OpenTelemetry |
| OpenTelemetry SDK | Manages spans, context, samplers, and exporters |
| OTLP exporter | Sends telemetry to Collector/backend |

Spring Boot auto-instrumentation creates observations for HTTP servers/clients and select integrations. Not every method or AWS SDK call generates spans automatically; verify instrumentation coverage.

## 10. Choosing an instrumentation strategy

| Strategy | How it works | When suitable |
| --- | --- | --- |
| Spring Boot + Micrometer Tracing | Actuator auto-configuration, Observation API, and tracer bridge | Spring Boot apps wanting Spring conventions, metrics, and traces |
| OpenTelemetry/ADOT Java agent | `-javaagent` instruments bytecode of supported frameworks/clients | Wanting broad auto-instrumentation, including AWS SDK where supported |
| Manual OpenTelemetry API | Creates spans/attributes for custom business operations | Tracing domain logic invisible to auto-instrumentation |

### Avoiding duplicate instrumentation

Do not enable two auto-instrumentation systems simultaneously producing the same server/client spans. Spring Boot Micrometer Tracing and the OTel Java agent can both instrument HTTP servers/clients depending on version and configuration.

- **Spring-first:** Actuator + Micrometer Tracing + OTel exporter; add AWS SDK instrumentation if needed.
- **Agent-first:** ADOT Java agent instruments HTTP/JDBC/AWS SDK; add OTel APIs only for manual spans.
- **Controlled hybrid:** Spring Micrometer for metrics/observations and agent for uninstrumented libraries; verify spans do not duplicate.

When an agent already provides an `OpenTelemetry` instance, manual instrumentation should acquire the global instance per agent guidance. Never initialize a second global OTel SDK.

## 11. Dependencies for Spring Boot 3.5.x

Spring Boot 3.5 uses Actuator and the Micrometer bridge. Maven example:

~~~xml
<dependencies>
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
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Let the Spring Boot BOM pick compatible versions. If not using the Micrometer OTLP registry, omit it and configure the metrics exporter matching your backend. Never pin separate versions on individual Micrometer/OpenTelemetry modules when managed by the BOM.

## 12. Dependencies for Spring Boot 4.x

Spring Boot 4.x introduces a dedicated OpenTelemetry starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-opentelemetry</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot 4.x manages OpenTelemetry tracing integration and the OTLP trace exporter via auto-configuration. Metrics across the Spring portfolio continue to be collected by Micrometer; `micrometer-registry-otlp` exports Micrometer metrics over OTLP.

| Setting | Spring Boot 3.5 | Spring Boot 4.2 |
| --- | --- | --- |
| Tracing OTLP endpoint | `management.otlp.tracing.endpoint` | `management.opentelemetry.tracing.export.otlp.endpoint` |
| Sampling probability | `management.tracing.sampling.probability` | `management.tracing.sampling.probability` |
| Metrics OTLP URL | `management.otlp.metrics.export.url` | `management.otlp.metrics.export.url` |
| Resource attributes | `management.opentelemetry.resource-attributes.*` | `management.opentelemetry.resource-attributes.*` |

Never copy `application.yml` verbatim between Boot 3.5 and Boot 4.x without checking configuration metadata.

## 13. Resource attributes: identifying service and environment

Resource attributes describe the telemetry-emitting source, not an individual request.

Common attributes: `service.name`, `service.namespace`, `service.version`, `deployment.environment`, `cloud.provider`, `cloud.region`, and `service.instance.id`.

~~~bash
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment=staging,cloud.provider=aws,cloud.region=ap-southeast-1
~~~

Or Spring Boot configuration:

~~~yaml
management:
  opentelemetry:
    resource-attributes:
      service.name: orders-api
      service.namespace: commerce
      service.version: 1.8.0
      deployment.environment: staging
      cloud.provider: aws
      cloud.region: ap-southeast-1
~~~

Keep `service.name` consistent across all replicas of the same service. Never use pod IDs, request IDs, or user IDs in `service.name`, as that fragments grouping and inflates service entities.

## 14. Configuring tracing for Spring Boot 3.5

Example exporting spans to an OTLP HTTP Collector on port 4318:

~~~yaml
spring:
  application:
    name: orders-api

management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
      transport: http
  observations:
    key-values:
      cloud.region: ap-southeast-1
      deployment.environment: staging
~~~

Spring Boot 3.5 samples 10% of requests by default. Set probability to `1.0` in tests to observe every trace, but never default to 100% in production.

You can configure propagation to consume W3C/B3 and produce W3C. For AWS X-Ray propagation, use the ADOT/X-Ray propagator or instrumentation supporting AWS headers.

## 15. Configuring tracing for Spring Boot 4.x

With Spring Boot 4.2, configure OTLP under the OpenTelemetry namespace:

~~~yaml
spring:
  application:
    name: orders-api

management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
          transport: http
          compression: gzip
    resource-attributes:
      service.name: orders-api
      service.namespace: commerce
      deployment.environment: staging
      cloud.provider: aws
      cloud.region: ap-southeast-1
~~~

You can set a shared `management.opentelemetry.otlp.endpoint` and let Boot append signal paths for HTTP. Trace-specific endpoints take precedence if declared.

## 16. Creating custom observations with Micrometer

Spring Boot recommends `ObservationRegistry` for business operations needing both metrics and traces.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ObservationRegistry observations;
    private final PaymentGateway paymentGateway;

    public PaymentService(ObservationRegistry observations,
                          PaymentGateway paymentGateway) {
        this.observations = observations;
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult authorize(String orderId, long amount) {
        return Observation.createNotStarted("payment.authorize", observations)
            .lowCardinalityKeyValue("payment.provider", "primary")
            .lowCardinalityKeyValue("payment.operation", "authorize")
            .highCardinalityKeyValue("order.id", orderId)
            .observe(() -> paymentGateway.authorize(orderId, amount));
    }
}
~~~

- `payment.authorize` is the observation name.
- `payment.provider` and `payment.operation` have small bounded sets, suitable for metric tags.
- `order.id` has high cardinality; include it in traces only when needed and free of sensitive data.

Low-cardinality values attach to both metrics and traces; high-cardinality values belong strictly in traces. Never place emails, customer IDs, request UUIDs, URLs with query params, or raw SQL into metric labels.

## 17. Creating manual spans for specialized business operations

Example business step not auto-instrumented by the framework:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

@Component
public class FraudDecision {

    private final Tracer tracer;

    public FraudDecision(Tracer tracer) {
        this.tracer = tracer;
    }

    public boolean evaluate(String orderId) {
        Span span = tracer.nextSpan()
            .name("fraud.evaluate")
            .tag("fraud.engine", "rules-v2")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            boolean approved = runRules(orderId);
            span.tag("fraud.result", approved ? "approved" : "rejected");
            return approved;
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }

    private boolean runRules(String orderId) {
        return true;
    }
}
~~~

End spans in `finally` so exporters receive accurate duration and status. Never catch and swallow exceptions; record the error and preserve business operation semantics. A span should represent a meaningful operation, not every getter or setter.

## 18. Context propagation across @Async and thread pools

In synchronous code, context lives in the active scope. When hopping threads, the caller thread's `ThreadLocal` does not automatically appear on worker threads.

Spring Boot Context Propagation supports:
- For auto-configured `AsyncTaskExecutor`, enabling `spring.task.execution.propagate-context=true` in releases supporting this property.
- For custom executors, attaching `ContextPropagatingTaskDecorator`.
- For Reactor, enabling `spring.reactor.context-propagation=auto` when `ThreadLocal` restoration inside reactive operators is needed.

Custom executor example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("orders-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

If context disappears, inspect the actual executor used by `@Async`, task decorators, custom `CompletableFuture` executors, Reactor chains, and agent instrumentation. Never copy trace IDs into custom static `ThreadLocal`s, which risks leaking context across requests.

## 19. Context propagation in Reactor/WebFlux

Reactive execution hops across threads. `ThreadLocal` is not a reliable context source inside every operator.

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

With automatic propagation enabled, Spring Context Propagation bridges observation context between Reactor `Context` and `ThreadLocal` along managed lifecycles. If writing custom Reactor operators, use Context/Observation APIs and test concurrent requests to catch context leakage.

## 20. Log correlation with traceId and spanId

Spring Boot with Micrometer Tracing populates `traceId` and `spanId` into MDC within the active scope. Log patterns can include correlation IDs:

~~~yaml
logging:
  pattern:
    correlation: "[orders-api,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Log example:

~~~text
[orders-api,4efaaf4d1e8720b39541901950019ee5,00f067aa0ba902b7] INFO PaymentService - authorization started
~~~

MDC correlates logs inside a single process only. Crossing the network requires dedicated propagation headers or message metadata.

## 21. Baggage: passing metadata across services

Baggage is key/value metadata attached to trace context that can propagate to downstream services.

~~~http
baggage: workflow=checkout,tenant-tier=gold
~~~

Micrometer Tracing can create baggage:

~~~java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

@Component
class WorkflowContext {

    private final Tracer tracer;

    WorkflowContext(Tracer tracer) {
        this.tracer = tracer;
    }

    void execute() {
        try (BaggageInScope ignored =
                 tracer.createBaggageInScope("workflow", "checkout")) {
            performWork();
        }
    }

    private void performWork() {
        // Work performed while baggage is in scope.
    }
}
~~~

Baggage propagates automatically when the active propagation format supports it. W3C transmits baggage via the `baggage` header. Never put passwords, access tokens, emails, addresses, or personal data into baggage. Allowlist permitted keys/values and bound sizes.

## 22. Instrumenting AWS SDK for Java 2.x

AWS SDK calls are often central to traces: S3 Get/PutObject, SQS Send/Receive, DynamoDB Get/Put, STS AssumeRole, and SNS Publish.

The ADOT/OpenTelemetry Java agent automatically instruments supported AWS SDK v2 clients. Without the agent, use the OpenTelemetry AWS SDK v2 instrumentation library.

Example instrumenting a specific DynamoDB client:

~~~java
import io.opentelemetry.instrumentation.awssdk.v2_2.AwsSdkTelemetry;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

AwsSdkTelemetry telemetry =
    AwsSdkTelemetry.create(openTelemetry).build();

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .overrideConfiguration(
        ClientOverrideConfiguration.builder()
            .addExecutionInterceptor(
                telemetry.createExecutionInterceptor())
            .build())
    .build();
~~~

For SQS, instrumentation may require additional wrappers on synchronous/async clients per instrumentation docs:

~~~java
SqsClient sqs = telemetry.instrument(
    SqsClient.builder().build()
);

SqsAsyncClient sqsAsync = telemetry.instrument(
    SqsAsyncClient.builder().build()
);
~~~

When using Spring Cloud AWS auto-configured clients, never create a duplicate second client solely to attach interceptors. Use the agent or customizers/bean configuration so instrumentation applies to the exact client Spring injects.

## 23. SQS/SNS: per-message propagation

When publishing SQS messages, consumer processing must link back to the producer operation. The HTTP request to SQS and message delivery are two separate boundaries.

Verify:
- Producer instrumentation injects context into message system attributes/message attributes;
- Consumer instrumentation extracts the matching carrier;
- `SendMessageBatch` attaches individual context per entry;
- SNS-to-SQS subscriptions preserve metadata across the flow;
- DLQs/redrives preserve event IDs and required metadata;
- Batch listeners use span links when handling messages from multiple traces.

With AWS SDK v2 OTel instrumentation and X-Ray propagation enabled, `SendMessageBatch` can inject per-message context into the `AWSTraceHeader` system attribute. If custom integrations lack native support, propagate W3C `traceparent`/`tracestate` in message attributes following messaging instrumentation conventions.

Use a dedicated event ID for idempotency, trace context for correlation, and `MessageGroupId` for FIFO ordering. Never use a trace ID as a deduplication ID.

## 24. Sampling: deciding which traces to keep

| Sampling | How it works | When to use |
| --- | --- | --- |
| Always on | Keeps every trace | Local tests, tiny workloads |
| Always off | Drops every trace | Intentionally disabling tracing |
| Trace ID ratio | Samples a percentage based on trace ID | Cutting volume/cost |
| Parent-based ratio | Children follow parent; roots sample by ratio | Distributed services |
| Tail sampling | Collector decides after inspecting completed trace | Retaining errors/slow traces per policy |

Spring Boot Micrometer Tracing samples 10% of requests by default. Example:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Parent-based sampling prevents downstream services from making conflicting decisions that fracture traces.

ADOT Java agent direct export to CloudWatch may sample 100% unless a sampler is configured. Example setting 5%:

~~~bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.05
~~~

Tail sampling requires the Collector to receive all spans of a trace. When running multiple Collector replicas, route by trace ID so spans do not split across Collectors.

## 25. Metrics with Micrometer

Spring Boot uses Micrometer as its metrics API. Useful metrics include HTTP request/duration, JVM memory/GC/threads, DB connection pools, SQS queue age/listener errors, and business counters.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
class OrderMetrics {

    private final Counter created;

    OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
            .description("Number of orders created")
            .tag("channel", "web")
            .register(registry);
    }

    void orderCreated() {
        created.increment();
    }
}
~~~

Use tags with small bounded sets such as `channel=web/mobile/partner`. Never use `orderId`, `userId`, `requestId`, raw URLs, or exception messages as metric labels.

### Metrics exemplars

Exemplars attach a sampled trace context to a metric sample. Operators viewing a histogram or latency spike can jump straight to an associated outlier trace. The backend must support exemplars.

## 26. Exporting OTLP metrics from Spring Boot

Example Micrometer OTLP registry sending metrics to a Collector:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        enabled: true
~~~

Metrics export periodically, unlike trace spans which export upon span completion. Pick `step` based on observability needs and ingestion volume.

When relying on a Collector to SigV4-sign requests to CloudWatch, the application sends internal OTLP to the Collector. Never point an exporter without SigV4 support straight at AWS OTLP endpoints.

## 27. Logs: structured logging and trace correlation

Log records should carry `trace_id`, `span_id`, `service.name`, `deployment.environment`, `level`, `timestamp`, `logger`, and controlled event/request IDs.

~~~json
{
  "timestamp": "2026-11-20T10:15:30.120Z",
  "level": "ERROR",
  "service": "orders-api",
  "trace_id": "4efaaf4d1e8720b39541901950019ee5",
  "span_id": "00f067aa0ba902b7",
  "message": "Payment authorization failed",
  "error.type": "TimeoutException"
}
~~~

Spring Boot Micrometer Tracing injects trace/span IDs into MDC so logger patterns print correlation IDs. To emit `LogRecord`s over the OpenTelemetry Logs API, configure the matching logging bridge/appender or ADOT agent log instrumentation.

Do not assume Spring Boot automatically bridges every Logback/Log4j log event to an OpenTelemetry `LoggerProvider`. MDC trace correlation and OTLP log export are separate configurations.

## 28. OTLP and Collectors

OTLP is the protocol for transporting traces, metrics, and logs across SDKs/agents, Collectors, and backends.

| Transport | Endpoint | Port |
| --- | --- | --- |
| OTLP/gRPC | `http://otel-collector:4317` | `4317` |
| OTLP/HTTP protobuf | `http://otel-collector:4318` | `4318` |
| Traces path | `/v1/traces` | HTTP |
| Metrics path | `/v1/metrics` | HTTP |
| Logs path | `/v1/logs` | HTTP |

The Collector can run as a sidecar in an ECS task, a DaemonSet/Deployment in EKS, or an agent on EC2. With CloudWatch, the Collector handles SigV4 signing, batching, retries, and exporting to each OTLP endpoint.

## 29. Collector config: exporting all three signals to CloudWatch OTLP

Example Collector receiving OTLP from a Java app and exporting metrics, logs, and traces to CloudWatch. Substitute Region, log group, and stream for your environment:

~~~yaml
extensions:
  sigv4auth/metrics:
    service: monitoring
    region: ap-southeast-1
  sigv4auth/logs:
    service: logs
    region: ap-southeast-1
  sigv4auth/traces:
    service: xray
    region: ap-southeast-1

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 20
  batch:
    send_batch_size: 200
    send_batch_max_size: 1000
    timeout: 10s

exporters:
  otlphttp/metrics:
    metrics_endpoint: https://monitoring.ap-southeast-1.amazonaws.com/v1/metrics
    compression: gzip
    auth:
      authenticator: sigv4auth/metrics

  otlphttp/logs:
    logs_endpoint: https://logs.ap-southeast-1.amazonaws.com/v1/logs
    compression: gzip
    headers:
      x-aws-log-group: /apps/orders
      x-aws-log-stream: default
    auth:
      authenticator: sigv4auth/logs

  otlphttp/traces:
    traces_endpoint: https://xray.ap-southeast-1.amazonaws.com/v1/traces
    compression: gzip
    auth:
      authenticator: sigv4auth/traces

service:
  extensions: [sigv4auth/metrics, sigv4auth/logs, sigv4auth/traces]
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/metrics]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/logs]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/traces]
~~~

Before running:
- Create CloudWatch Log Group `/apps/orders` and Log Stream `default`;
- Attach an IAM role to the Collector for SigV4 signing;
- Enable CloudWatch Transaction Search when using the X-Ray OTLP endpoint;
- Ensure network paths to CloudWatch endpoints;
- Pin the Collector image/version in production—never use `latest`;
- Protect receivers on `4317`/`4318` with private networking, Security Groups, or inbound auth if needed.

CloudWatch OTLP endpoints support HTTP only, not gRPC on the AWS endpoint side. The Collector can accept gRPC from applications and export over OTLP/HTTP.
## 30. ADOT Java agent: auto-instrumenting Spring Boot

The ADOT Java agent provides zero-code instrumentation. It instruments supported libraries and frameworks via bytecode instrumentation at JVM startup.

~~~bash
OTEL_RESOURCE_ATTRIBUTES=service.name=orders-api,service.namespace=commerce,deployment.environment=staging \
java -javaagent:/opt/aws-opentelemetry-agent.jar -jar orders-api.jar
~~~

With Docker:

~~~dockerfile
COPY aws-opentelemetry-agent.jar /opt/aws-opentelemetry-agent.jar
ENV JAVA_TOOL_OPTIONS="-javaagent:/opt/aws-opentelemetry-agent.jar"
~~~

Pin the agent version and review release notes and supported libraries. The agent does not automatically instrument every library on the classpath.

The ADOT Java agent defaults to the OTLP exporter and typically targets a Collector/CloudWatch Agent on `localhost` port `4317`. Override with `OTEL_EXPORTER_OTLP_*` environment variables.

## 31. ADOT direct export to CloudWatch: traces and logs

ADOT Java agent version 2.11.2 and later supports exporting traces and logs directly to CloudWatch OTLP endpoints without a separate Collector. Example:

~~~bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/aws-opentelemetry-agent.jar"

export OTEL_RESOURCE_ATTRIBUTES="service.name=orders-api,deployment.environment=prod"
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.ap-southeast-1.amazonaws.com/v1/traces

export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://logs.ap-southeast-1.amazonaws.com/v1/logs
export OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-log-group=/apps/orders,x-aws-log-stream=default
~~~

The Log Group and Log Stream must exist before exporting. ADOT uses the AWS credentials provider for authentication; on ECS/EC2/EKS, prefer IAM task/instance/pod roles.

For metric/log correlation in CloudWatch, you can add `aws.log.group.names=/apps/orders` to `OTEL_RESOURCE_ATTRIBUTES`. For trace/log correlation to work, the application logger must also emit trace ID/span ID per CloudWatch guidance.

Per current ADOT Java agent guidance, traces and logs can export directly, whereas metrics require CloudWatch Agent or a Collector. If you want only traces/logs from the agent, set `OTEL_METRICS_EXPORTER=none`; Spring Boot metrics can export via Micrometer's OTLP registry to a Collector.

Direct trace export may sample at 100% by default. Configure a ratio sampler appropriate for production and control costs.

## 32. CloudWatch Application Signals and X-Ray

CloudWatch Application Signals offers an application-centric view of service health, dependencies, and SLOs. ADOT Java auto-instrumentation produces telemetry enabling Application Signals to monitor HTTP services and downstream dependencies.

| Component | Role |
| --- | --- |
| ADOT Java agent | Instruments the Java application |
| CloudWatch Agent / ADOT Collector | Receives, processes, and exports telemetry |
| CloudWatch Application Signals | Health, dependency map, SLO-oriented view |
| X-Ray / Trace Search | Searches and displays distributed traces |
| CloudWatch Metrics | Metrics and alarms |
| CloudWatch Logs | Log records and queries |

Do not confuse enabling Application Signals with telemetry appearing automatically without IAM, networking, or agent configuration. Verify agent injection, role permissions, resource attributes, and Transaction Search setup.

## 33. IAM permissions, networking, and endpoints

The Collector/agent needs an identity permitted to write telemetry:

| Signal | Typical permissions |
| --- | --- |
| Traces | `xray:PutTraceSegments`, `xray:PutTelemetryRecords`, or `AWSXrayWriteOnlyPolicy` |
| Metrics | `cloudwatch:PutMetricData` |
| Logs | `logs:PutLogEvents`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams` |

Scope policies to minimum Region/resource requirements and check managed policy versions before attaching. Never grant `AdministratorAccess` merely to make telemetry export work.

Network requirements:
- Application → Collector: `4317`/`4318` inside private network;
- Collector → X-Ray OTLP endpoint: HTTPS `443`;
- Collector → CloudWatch metrics endpoint: HTTPS `443`;
- Collector → CloudWatch Logs endpoint: HTTPS `443`;
- Private subnets: NAT or appropriate VPC endpoints;
- Verify DNS, TLS certificates, proxies, Security Groups, NACLs, and endpoint policies.

CloudWatch OTLP endpoints using SigV4 with short-term credentials are recommended for AWS workloads. Bearer tokens/API keys are a separate option for non-AWS environments and must be managed/rotated as secrets.

## 34. Sampling, cardinality, performance, and cost

Telemetry incurs ingestion, storage, query, and network costs. Unbounded instrumentation inflates bills or degrades application latency.

### Controlling trace volume
- Use parent-based sampling;
- Sample 100% in local/test when needed;
- Pick a ratio matched to production traffic;
- Use tail sampling when retaining errors/slow traces;
- Avoid overly granular spans;
- Use batch exporters and Collectors;
- Monitor dropped spans, queue sizes, and export failures.

### Controlling metric cardinality

Avoid metric labels like `user.id`, `order.id`, `request.id`, raw URL paths containing IDs, exception messages, or full SQL queries. Use route templates like `/orders/{id}`, status classes, and normalized operation names.

### Controlling payload/logs

Never record sensitive request/response bodies, access tokens, authorization headers, passwords, full SQS payloads, or presigned URLs in spans or logs. Allowlist attributes and cap span sizes.

## 35. Testing trace propagation and telemetry export

Send a valid `traceparent` to the API:

~~~bash
curl -H "traceparent: 00-4efaaf4d1e8720b39541901950019ee5-00f067aa0ba902b7-01" \
  http://localhost:8080/orders
~~~

When the API and downstream clients are properly instrumented, the trace preserves the same trace ID while creating fresh span IDs for each operation.

### Cases to test
- HTTP server span is created;
- Outbound `RestClient`/`WebClient` injects trace context;
- Custom executors preserve context;
- Reactor pipelines preserve context;
- AWS SDK S3/SQS calls emit spans;
- SQS consumers link messages back to producers;
- Logs include `traceId`/`spanId`;
- Metrics use expected names, tags, and low cardinality;
- Collector receives OTLP and exports cleanly;
- CloudWatch/X-Ray displays expected service/resource attributes.

Use in-memory or test exporters for manual OTel SDK tests, mock HTTP servers to verify headers, and the Collector debug exporter locally to inspect telemetry. LocalStack cannot replace every propagation/instrumentation test on real AWS.

## 36. Troubleshooting: lost traces or missing telemetry

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Every service generates a new trace ID | Inbound context not extracted or outbound context not injected | Check `traceparent`, propagation formats, HTTP client builders |
| Server span exists, client span missing | Manually created client lacking instrumentation | Use auto-configured builder or agent/library |
| Context lost in `@Async` | Executor does not propagate context | Enable context propagation/task decorator |
| Trace lost in Reactor | `ThreadLocal` not restored into reactive pipeline | Enable `spring.reactor.context-propagation=auto` |
| Logs lack `traceId`/`spanId` | MDC integration/logger pattern misconfigured | Check Micrometer Tracing and MDC |
| Duplicate spans emitted | Both Spring Boot and Java agent instrumenting | Disable one instrumentation path |
| SQS consumer not linked to producer | Message carrier not injected/extracted or unsupported version | Check `AWSTraceHeader`/message attributes |
| Traces missing in X-Ray | Transaction Search disabled, wrong endpoint/Region | Check CloudWatch setup and Collector logs |
| OTLP returns 404 | Wrong path or HTTP/gRPC mismatch | Verify `/v1/traces`, `/v1/metrics`, `/v1/logs` |
| OTLP returns 403 | Wrong SigV4 service/Region or missing IAM permission | Check `sigv4auth` and Collector role |
| Logs rejected | Missing Log Group/Stream or missing headers | Create group/stream and set `x-aws-log-group`/`x-aws-log-stream` |
| Metrics throttled | Too many series/TPS/oversized batches | Reduce cardinality, batch size, step |
| Trace missing service name | Missing `service.name` resource attribute | Set `OTEL_SERVICE_NAME`/`OTEL_RESOURCE_ATTRIBUTES` |
| Spans dropped | Export queue full, timeouts, or throttling | Check Collector queue, retries, and `memory_limiter` |
| Abnormal trace durations | Host/container clock drift | Synchronize NTP |
| Agent breaks app startup | Agent/library version conflict | Inspect logs, pin versions, disable conflicting instrumentation |
| Logs show wrong trace ID across requests | MDC/context not cleared or restored | Check thread reuse and custom `ThreadLocal`s |

### Investigation workflow

~~~text
1. Identify the instrumentation strategy: Spring Boot, ADOT agent, or manual SDK.
2. Check service.name, environment, Region, and agent/dependency versions.
3. Verify inbound trace context extraction.
4. Check HTTP clients, executors, Reactor, and message propagation.
5. Inspect spans in the Collector debug exporter.
6. Verify OTLP endpoint, protocol, path, and networking.
7. Verify SigV4, IAM role, Region, and CloudWatch Transaction Search.
8. Check exporter queues, batching, retries, and dropped telemetry.
9. Check sampling, cardinality, and size limits.
10. Verify with a fixed traceparent request in a test environment.
~~~

Never enable debug logs that capture `Authorization` headers, AWS credentials, secret payloads, or customer data.

## 37. Securing trace context, baggage, and telemetry

Trace context is correlation metadata, not proof of identity. External clients can send arbitrary headers if ingress does not sanitize them.

- Never use trace IDs for authentication or authorization;
- Never trust client-supplied sampling flags as a security policy;
- Consider stripping/re-initializing context at untrusted trust boundaries;
- Allowlist baggage keys and cap sizes;
- Never place secrets, PII, payment data, or raw user input into attributes;
- Restrict access to CloudWatch Log Groups;
- Never expose OTLP receivers publicly without network/auth controls;
- Use TLS and short-term IAM role credentials;
- Configure appropriate retention and access policies on traces/logs.

AWS X-Ray tracing headers can originate from client requests. If clients should not dictate trace roots or sampling state, strip or sanitize headers at the edge per policy and AWS guidance.

## 38. Migrating from AWS X-Ray SDK to OpenTelemetry

AWS announced that AWS X-Ray SDKs/Daemon entered maintenance mode on **February 25, 2026**, receiving only limited releases for security issues. For new or actively developed applications, evaluate migrating to OpenTelemetry/ADOT.

| X-Ray SDK concept | OpenTelemetry |
| --- | --- |
| Segment | Server span |
| Subsegment | Client/internal span |
| Annotation | Span attribute mapped appropriately to searchable annotations |
| Metadata | Span attributes/structured events |
| X-Ray recorder | `Tracer`/`TracerProvider` |
| X-Ray SDK instrumentation | OTel instrumentation libraries/Java agent |
| X-Ray Daemon | ADOT Collector or CloudWatch Agent |
| X-Ray sampling rules | OTel samplers/ADOT X-Ray remote sampling where supported |

### Migration roadmap
1. Inventory X-Ray SDK modules, recorder configs, plugins, and interceptors.
2. Verify agent/OTel instrumentation coverage for Spring, HTTP, JDBC, and AWS SDK v2.
3. Choose either the ADOT Java agent or Micrometer/OTel SDK approach.
4. Configure W3C/X-Ray propagation compatible with upstreams and downstreams.
5. Replace segment/subsegment code with Observations or spans.
6. Map annotations/metadata to span attributes with controlled cardinality and privacy.
7. Switch exporters/daemon to the ADOT Collector or CloudWatch OTLP endpoints.
8. Test traces across ALB/API Gateway, SQS/SNS, AWS SDK, and workers.
9. Run controlled parallel verification in staging; avoid emitting duplicate spans in production.
10. Roll out service by service and remove X-Ray SDK/Daemon once dependencies are gone.

## 39. Practice exercises and self-check questions

### Exercise 1 — Trace splits between two services

Orders API receives a W3C `traceparent`, yet Inventory API generates a brand-new trace ID.

**Task:** Check inbound extraction, auto-configured `RestClient`/`WebClient` builders, propagation formats, and manually instantiated HTTP clients. Draw the parent-child spans.

### Exercise 2 — Context lost during @Async

Logs on the request thread contain the trace ID, while logs on the worker thread do not.

**Task:** Explain `ThreadLocal`/context propagation; configure `ContextPropagatingTaskDecorator` or the matching property; test two concurrent requests to catch context leakage.

### Exercise 3 — SQS message not linked to producer

The API sends an SQS message, yet the worker starts an entirely new trace.

**Task:** Distinguish HTTP API headers from message carriers; inspect `AWSTraceHeader`, AWS SDK v2 instrumentation, and consumer extraction. Explain when to use span links for batches.

### Exercise 4 — Choosing an instrumentation strategy

A Spring Boot service uses MVC, JDBC, S3, SQS, and a custom thread pool. The team enabled both Micrometer Tracing and the ADOT Java agent.

**Task:** Identify duplicate spans, choose either Spring-first or agent-first, describe how to instrument any missing AWS SDK calls, and verify zero duplicates.

### Exercise 5 — Sampling and cost

An API serves 10,000 requests/second. ADOT direct export currently samples 100%.

**Task:** Propose parent-based ratio sampling, compare volume when reduced to 5%, identify which traces (if any) should be kept at 100%, and prevent split traces across services.

### Exercise 6 — CloudWatch OTLP export returns 403

The Collector receives traces/metrics/logs, yet CloudWatch returns 403.

**Task:** Check SigV4 service names (`xray`, `monitoring`, `logs`), Region, IAM permissions, workload role, and Transaction Search setup.

### Exercise 7 — Cardinality

Metric `orders.duration` carries labels `orderId`, `customerId`, and `requestId`.

**Task:** Explain time-series explosion; move IDs to controlled trace attributes and keep metric labels low-cardinality.

### Exercise 8 — Migrating off the X-Ray SDK

An application uses the X-Ray recorder and daemon and needs to migrate to ADOT.

**Task:** Map segments/subsegments/annotations/metadata to spans/attributes; choose agent/SDK, Collector, and a rollout plan.

### Short questions

1. **What makes up a trace?** Multiple spans linked by trace context.
2. **How does Span ID differ from Trace ID?** Trace ID identifies the entire journey; Span ID identifies one operation.
3. **What are the main parts of `traceparent`?** Version, trace ID, parent span ID, and flags.
4. **What is `tracestate` used for?** Vendor-specific trace state.
5. **Is baggage an authorization token?** No.
6. **Does a Correlation ID replace trace context?** No.
7. **Which API does Spring Boot use for observations?** Micrometer `Observation`/`ObservationRegistry`.
8. **What does the Micrometer Tracing OTel bridge do?** Bridges Observation/Tracing APIs to OpenTelemetry.
9. **What does the ADOT Java agent do?** Auto-instruments supported frameworks and libraries.
10. **Should you enable two overlapping auto-instrumentations?** No.
11. **Why use the auto-configured `RestClient.Builder`?** To attach observation/trace propagation to outbound requests.
12. **Why can `@Async` lose trace context?** Context does not jump threads automatically unless the executor propagates it.
13. **Does MDC replace propagation headers?** No.
14. **Where must SQS carry context?** Message attributes/system attributes or supporting instrumentation.
15. **What is `AWSTraceHeader`?** An SQS system attribute carrying X-Ray trace context.
16. **What should low-cardinality tags contain?** Bounded values such as operation, channel, region.
17. **Where do high-cardinality attributes belong?** In traces when needed—avoid metric labels.
18. **Which ports do OTLP receivers typically use?** `4317` for gRPC and `4318` for HTTP.
19. **Do CloudWatch OTLP endpoints support HTTP or gRPC?** HTTP.
20. **Which SigV4 service does the CloudWatch trace endpoint use?** `xray`.
21. **Which service does the metrics endpoint use?** `monitoring`.
22. **Which service does the logs endpoint use?** `logs`.
23. **Why is Transaction Search required for X-Ray OTLP traces?** It is a prerequisite of the CloudWatch trace ingestion path.
24. **Is ADOT direct metrics export identical to traces/logs?** No; the current Java agent direct path requires a Collector/CloudWatch Agent for metrics.
25. **When did the X-Ray SDK/Daemon enter maintenance mode?** February 25, 2026.

## 40. Pre-production checklist

- [ ] Instrumentation strategy chosen: Spring Boot Micrometer, ADOT Java agent, or manual OTel.
- [ ] Zero duplicate server/client spans.
- [ ] `service.name`, namespace, version, environment, and Region are consistent.
- [ ] Inbound W3C/B3/X-Ray context extracted per policy.
- [ ] Outbound `RestClient`/`WebClient` uses auto-configured builders or matching instrumentation.
- [ ] Context propagates across `@Async`, custom executors, and Reactor.
- [ ] SQS/SNS producer/consumer context verified across message carriers, batches, and retries.
- [ ] AWS SDK v2 clients instrumented cleanly for the exact version.
- [ ] Logs include `traceId`/`spanId` correlation and contain no secrets or PII.
- [ ] Metric labels stay low-cardinality; IDs appear only in traces when needed.
- [ ] Baggage keys are allowlisted and size-bounded.
- [ ] Parent-based sampling tuned; never accidentally exporting 100% of production traces.
- [ ] OTLP exporters configured with batching, timeouts, retries, and queue bounds.
- [ ] Collector configured with `memory_limiter`, private receivers, and health monitoring.
- [ ] CloudWatch Transaction Search enabled if sending X-Ray OTLP traces.
- [ ] CloudWatch Log Group/Stream exist before exporting logs.
- [ ] Collector role holds least-privilege IAM permissions.
- [ ] VPC endpoints, DNS, TLS, Region, and networking verified.
- [ ] Agent/Collector versions pinned and release notes tracked.
- [ ] Test profiles never export telemetry into production accounts.
- [ ] Dashboards and alerts cover error rate, latency, queue age, exporter failures, and dropped spans.
- [ ] Runbooks cover context loss, `AccessDenied`, `429`, and exporter timeouts.
- [ ] X-Ray SDK/Daemon migration plan evaluated in light of maintenance mode.
- [ ] Ingestion, retention, query, and cardinality costs monitored.

## 41. Summary

Distributed tracing relies on **context propagation** so multiple processes, threads, and messages share a single trace. W3C Trace Context is the standard format; AWS X-Ray uses `X-Amzn-Trace-Id` and supports interoperability with W3C via compatible exporters and Collectors.

In Spring Boot, Micrometer Observation/Tracing provides APIs for observations, spans, metrics, and log correlation. Use auto-configured HTTP builders, configure Context Propagation for executors and Reactor, and instrument AWS SDK v2 and message queues so traces never break at AWS boundaries.

Telemetry spans traces, metrics, and logs. OTLP carries them; the ADOT Java agent auto-instruments Java; Collectors/CloudWatch Agents handle batching, SigV4, retries, and exporting to CloudWatch/X-Ray. Sampling, cardinality, baggage, IAM, networking, and log hygiene determine reliability, cost, and security.

Key points to remember:

1. Trace ID identifies the journey; span ID identifies an operation; `traceparent` carries parent context over HTTP.
2. Baggage is propagation metadata—never store secrets or PII in it.
3. MDC links logs to traces within a process; it never replaces network or message propagation.
4. Use Spring Boot auto-configured builders and Context Propagation to keep context alive across HTTP, async, and Reactor.
5. Use ADOT/OTel instrumentation for AWS SDK v2 and verify SQS/SNS message carriers.
6. Use Micrometer for Spring metrics, OpenTelemetry/ADOT for traces, and Collectors for telemetry pipelines.
7. CloudWatch OTLP endpoints require SigV4, HTTP, and matching service/Region; enable Transaction Search when sending traces.
8. Govern sampling, cardinality, retention, baggage, and exporter queues.
9. AWS X-Ray SDK/Daemon entered maintenance mode on February 25, 2026; plan your OpenTelemetry migration roadmap.

### Official documentation

- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Boot 4.x — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — Metrics and OTLP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OpenTelemetry Java instrumentation ecosystem](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [OpenTelemetry Java agent](https://github.com/open-telemetry/opentelemetry-java-instrumentation)
- [OpenTelemetry AWS SDK v2 instrumentation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/tree/main/instrumentation/aws-sdk/aws-sdk-2.2)
- [ADOT Java auto-instrumentation](https://aws-otel.github.io/docs/getting-started/java-sdk/auto-instr/)
- [ADOT Java manual instrumentation](https://aws-otel.github.io/docs/getting-started/java-sdk/manual-instr/)
- [ADOT Collector — Getting started](https://aws-otel.github.io/docs/getting-started/collector/)
- [AWS X-Ray concepts and trace headers](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html)
- [AWS X-Ray — Migrating to OpenTelemetry Java](https://docs.aws.amazon.com/xray/latest/devguide/xray-migration-opentelemetry.html)
- [AWS X-Ray SDK and Daemon Support timeline](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html)
- [CloudWatch OTLP endpoints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html)
- [CloudWatch — Export telemetry directly with ADOT](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLP-UsingADOT.html)
- [CloudWatch — Send metrics, logs and traces with Collector](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/GettingSetup.html)
- [CloudWatch Application Signals](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals.html)

**Note:** Spring Boot 3.5 and 4.x differ in properties and dependencies; AWS SDK/ADOT/Collector instrumentations release independently. Pin tested versions, verify the support matrix, test trace propagation across every boundary, and verify Collector exports in a non-production account before rolling out.
