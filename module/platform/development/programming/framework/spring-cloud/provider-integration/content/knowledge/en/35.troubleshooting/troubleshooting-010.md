# Isolating failures with request IDs and collecting secret-redacted evidence

When a Spring Boot application encounters an error with a managed service on AWS, Azure, or Google Cloud, logs often show only an application-side exception. To find the root cause, you must connect which services the request traversed, which operation the SDK called, what error the provider returned, and where that exact call was recorded. At the same time, evidence shared with operations or cloud support must be sufficient without leaking credentials, tokens, personal data, or business payloads.

No single identifier can represent every layer. A **Request ID** identifies one request to an application; a **correlation ID** links a business flow across multiple requests or services; **trace ID/span ID** describe the path and timing of operations; a **provider request ID** helps look up a single API call at the cloud provider; a **message/event ID** identifies a business message. Recording the right ID types and keeping them linked together drastically shortens investigation time.

This lesson guides you through designing identifiers, propagating trace context across HTTP and messaging, collecting provider metadata, producing structured logs, redacting secrets via allowlists, and packaging safe evidence for a production incident.

After this lesson, you can:

- Distinguish request ID, correlation ID, trace ID, span ID, provider request ID, message ID, and idempotency key.
- Generate and propagate IDs safely across Spring Boot, HTTP clients, and message brokers.
- Use Micrometer Tracing/OpenTelemetry to correlate logs with distributed traces.
- Capture AWS, Azure, and Google Cloud request IDs using the appropriate APIs/SDKs.
- Collect logs, traces, metrics, runtime configuration, and version details without exposing secrets.
- Prepare an evidence bundle with timestamps, request IDs, operations, errors, and reproduction steps for operations teams.

## 1. Identifier types and their roles

| Identifier | Scope | Who creates it? | What is it used for? |
|---|---|---|---|
| Request ID | One request to one service | Ingress/gateway or receiving service | Finding logs of a request within a specific service |
| Correlation ID | A business flow possibly spanning multiple services/requests | Gateway, first service, or business producer | Linking operations belonging to the same business operation |
| Trace ID | One distributed trace | Tracing SDK/instrumentation | Finding an entire trace of multiple spans across services and dependencies |
| Span ID | One operation inside a trace | Tracing SDK/instrumentation | Identifying a specific service/client operation and parent-child relationships |
| Provider request ID | One specific request to a cloud provider API | Cloud service | Looking up a request in provider logs/telemetry or a support case |
| Message ID | One message recognized by a broker | Producer/broker depending on service | Tracking a message send/delivery at the broker layer |
| Event ID | One business event | Application producer | Identifying an event across publish, retry, consumer, and redelivery |
| Idempotency key | An intent to perform a retryable operation | Client or business service | Preventing side effects from being applied multiple times on retries |

These IDs relate to one another but are not interchangeable. A single trace may contain multiple requests to the same provider; each retry may generate a different provider request ID. A single event may be delivered multiple times with the same event ID yet different message delivery metadata. A single correlation ID may span multiple traces if a workflow runs over time or splits into independent requests.

```mermaid
flowchart TD
    U[Client request] --> G[API Gateway]
    G --> A[Spring Boot Service A]
    A --> B[Spring Boot Service B]
    B --> SDK[Cloud SDK call]
    A --> Q[Message Broker]
    Q --> C[Spring Boot Consumer C]
    C --> DB[(Managed Database)]
    subgraph IDs[Identifiers and telemetry]
      R[Request ID per service]
      K[Business Correlation ID]
      T[Trace ID and Span IDs]
      P[Provider request ID per API attempt]
      E[Event ID / Message ID]
    end
    G -. attaches .-> R
    A -. preserves correlation .-> K
    A -. creates span .-> T
    SDK -. receives from response .-> P
    Q -. carries metadata .-> E
```

## 2. Rules for generating and using IDs

### 2.1. Request ID

A Request ID should be generated at the ingress or first service receiving the request. It helps locate logs within one service. When a request traverses multiple services, each service may generate its own request ID while preserving the correlation ID and trace context to link segments together.

Some gateways already generate `X-Request-ID` or a similar header. If trusting the gateway, configure the gateway to strip any client-supplied header and overwrite it with a fresh ID before forwarding to the application. If the application accepts requests directly from the Internet, never blindly trust a client-supplied ID; clients can deliberately send duplicate IDs to pollute logs. The application can generate a new internal ID and store any external ID in a separate validated field.

A Request ID is not an authentication credential. Never use it to grant permissions, access data, bypass rate limits, or identify users.

### 2.2. Correlation ID

A Correlation ID connects operations belonging to the same business workflow, such as a checkout creating an order, reserving inventory, publishing an event, and sending a notification. The ID should remain stable throughout the workflow, even when messages are retried or processed asynchronously minutes later.

If the system already has an `orderId`, `workflowId`, or `operationId`, an appropriate business ID can serve as the correlation ID, provided you avoid putting sensitive or guessable identifiers into public logs. Never use emails, phone numbers, personal customer codes, or business content as a correlation ID.

### 2.3. Trace ID and span ID

Distributed tracing models parent-child relationships among operations. One trace ID is propagated across services; each span has its own span ID. HTTP client instrumentation can create spans for outbound calls; cloud SDKs require dedicated instrumentation or interceptors if per-operation spans are desired.

W3C Trace Context defines common headers:

- `traceparent`: carries trace ID, parent span ID, and trace flags.
- `tracestate`: carries vendor-specific tracing state when needed.
- `baggage`: carries metadata propagated across the trace; include only non-sensitive details and cap size.

Do not manually build or mutate `traceparent` via string concatenation when using a tracing SDK. The SDK handles validation, span ID generation, and sampling/context management.

### 2.4. Provider request ID

A Provider request ID is returned by the cloud service or SDK response metadata. It is often the single most important piece of information when opening a support case because the provider uses it to locate the request internally. Record the exact value, service, operation, region, and UTC timestamp.

A Provider request ID typically identifies one API call attempt, not the entire business operation. If the SDK retries three times, there can be three provider request IDs. Record each attempt when clients/interceptors permit; do not keep only the last attempt's ID when investigating throttling or intermittent errors.

## 3. Propagating correlation and trace context in Spring Boot

### 3.1. Creating a request ID at servlet ingress

In a Spring MVC/Servlet application, a `OncePerRequestFilter` can generate a request ID, read a correlation ID from a trusted gateway that overwrote the header, populate MDC, and return the IDs to the client:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class RequestContextFilter extends OncePerRequestFilter {
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {
        String requestId = UUID.randomUUID().toString();
        String incoming = request.getHeader("X-Correlation-ID");

        // Only keep incoming when ingress is configured to strip/overwrite
        // client-supplied headers and forward a validated ID.
        String correlationId = incoming != null && SAFE_ID.matcher(incoming).matches()
            ? incoming
            : requestId;

        MDC.put("requestId", requestId);
        MDC.put("correlationId", correlationId);
        response.setHeader("X-Request-ID", requestId);
        response.setHeader("X-Correlation-ID", correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
            MDC.remove("correlationId");
        }
    }
}
```

Register the filter with `@Component` or `FilterRegistrationBean` per your application architecture. The regex restricts characters and length to prevent log injection/oversized values; validation alone does not prove the sender is trustworthy. If no trusted gateway overwrites the header, ignore client-sent `X-Correlation-ID` and generate an internal correlation ID.

MDC relies on thread-locals. With Servlet async, custom executors, or Reactor/WebFlux, execution can hop threads and MDC does not propagate automatically in every case. Use Micrometer Context Propagation/Observation or compatible tracing instrumentation; never manually copy MDC across threads without clearing context in `finally`, because thread pools reuse threads across requests.

### 3.2. Using Micrometer Tracing/OpenTelemetry

In Spring Boot applications, prefer Micrometer-integrated tracing over writing a custom `traceparent` parser. With Spring Boot 3.x, a common setup uses Actuator, the OpenTelemetry bridge, and the OTLP exporter:

```xml
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
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Use Spring Boot's dependency management/BOM to select compatible versions; do not pin standalone Micrometer/OpenTelemetry versions without verifying the compatibility matrix. Tracing sampling configuration can be set in `application.yml`:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

A sampling rate of `0.1` is just an example, sampling roughly 10% of traces under the corresponding head-sampling strategy. Pick the ratio based on volume, cost, and diagnostic requirements. For rare incidents, consider tail sampling at the collector or elevated error-sampling policies; head sampling can drop a trace before knowing it will fail.

### 3.3. Propagation via HTTP clients

When using Spring Boot's auto-configured `RestClient.Builder` or `WebClient.Builder` with observation/tracing instrumentation, Micrometer propagates W3C trace context automatically as configured. Inject the Spring-managed builder instead of calling `WebClient.builder()` directly or creating an uninstrumented HTTP client.

Example:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryClient {
    private final WebClient client;

    public InventoryClient(WebClient.Builder builder) {
        this.client = builder
            .baseUrl("https://inventory.internal")
            .build();
    }

    public InventoryResult find(String sku) {
        return client.get()
            .uri("/v1/items/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResult.class)
            .block();
    }
}
```

This snippet only demonstrates injecting the auto-configured builder. In reactive WebFlux, never call `.block()` on the event loop; return `Mono<InventoryResult>` and let the pipeline orchestrate execution. In MVC apps requiring synchronous calls, choose the appropriate client and execution model. Verify outbound requests actually carry `traceparent` and generate spans; do not assume every third-party SDK is instrumented automatically.

### 3.4. Propagating correlation IDs separately

Tracing instrumentation normally propagates `traceparent`, while a business correlation ID is a separate field. For a synchronous `RestClient` running on servlet threads, an interceptor can attach the correlation ID from MDC:

```java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class PartnerRestClientConfiguration {
    @Bean
    RestClient partnerRestClient(RestClient.Builder builder) {
        return builder
            .requestInterceptor((request, body, execution) -> {
                String correlationId = MDC.get("correlationId");
                if (correlationId != null) {
                    request.getHeaders().set("X-Correlation-ID", correlationId);
                }
                return execution.execute(request, body);
            })
            .build();
    }
}
```

This interceptor fits synchronous flows where MDC is already populated. For async executors or Reactor, obtain the correlation ID from context propagation/command context and pass it explicitly; never read thread-local MDC assuming it is always intact. Send correlation IDs only to internal services or partners that have agreed on this header. Keep `traceparent` managed by Micrometer/OpenTelemetry; do not overwrite it in the interceptor.

## 4. Propagating IDs through message brokers and async jobs

An HTTP trace ends when the response is returned, yet business processing may continue inside a consumer. When publishing messages, pass event ID, correlation ID, and trace context in message headers/attributes per your broker or binder mechanism.

| Field | Purpose | Rule |
|---|---|---|
| `eventId` | Business event identifier | Generate once and preserve across publish retries |
| `correlationId` | Links steps within one workflow | Preserve across producer, broker, and consumer |
| `traceparent` | Links traces across messaging boundaries | Use W3C propagation/instrumentation, never manual string concatenation |
| `tracestate` | Vendor tracing state | Propagate only when managed by tracing SDK and supported by broker |
| `messageId` | Broker-level message identifier | Record broker-returned ID or received metadata |
| `idempotencyKey` | Prevents duplicate side effects | Stable per business operation, backed by unique constraints or downstream support |

Never put tokens, emails, phone numbers, AccessKeys, or sensitive data into baggage or message headers. Headers can be persisted in brokers, displayed in consoles, or forwarded across systems outside the application boundary.

With Spring Cloud Stream, binders generally support message headers; exact mapping and W3C context propagation depend on the binder/version. Verify actual messages at the consumer. When using SDKs directly, attach metadata via the corresponding message attribute/header APIs and extract it in the consumer.

## 5. Collecting provider request IDs from AWS, Azure, and Google Cloud

### 5.1. AWS

AWS SDKs normally expose response metadata or exception metadata containing a request ID. Depending on SDK generation and service, response headers may be `x-amzn-RequestId`, `x-amz-request-id`, or service-specific headers. S3 commonly uses `x-amz-request-id` and `x-amz-id-2`; do not assume one single header across every AWS API.

When using AWS SDK for Java v2, read the request ID from response metadata when supported by the response type (for example `response.responseMetadata().requestId()` on the corresponding AWS response). For exceptions, retain request ID/status/error code provided by the SDK. An SDK execution interceptor can capture each attempt and response metadata; avoid logging request headers containing `Authorization` signatures or session tokens.

Information to store: AWS service, operation, region, account/resource alias, SDK request ID, extended request ID if present, status/error code, attempt, and UTC timestamp. A request ID does not replace an ARN/resource name or trace ID.

### 5.2. Azure

Many Azure services return headers such as `x-ms-request-id` and `x-ms-correlation-request-id`; some SDKs/APIs support client request IDs or request correlation metadata. Azure Service Bus can provide a `TrackingId`/diagnostic identifier per operation. Exact headers and metadata vary by service.

When using the Azure SDK for Java, extract response headers/diagnostic metadata from the corresponding response or exception. If sending a client request ID, generate a safe ID and record both the client value and the service-returned request ID; do not confuse them. For HTTP responses, you can log `x-ms-*` headers specified in service docs, but allowlist headers and never dump all response headers.

Information to store: subscription/tenant alias, resource/namespace, region, operation, `x-ms-request-id`, correlation/`TrackingId` if present, status/substatus, retry-after, and SDK version. Never log bearer tokens or full SAS URLs.

### 5.3. Google Cloud

Google Cloud does not have a single uniform response request ID header across every API. Metadata depends on the service and client library. Some APIs return request/operation identifiers in responses or exceptions; inspect `ApiException`/response metadata and headers documented for the exact service. For Cloud Storage, upload/sessions and JSON/XML APIs have distinct metadata; do not apply one header name across all products.

For distributed tracing, use W3C `traceparent` or library-supported propagation mechanisms. Cloud Logging has a trace resource field linking logs to traces; the trace resource format typically includes the project ID and trace ID. The `X-Cloud-Trace-Context` header appears in some legacy environments/integrations, but avoid generating it alongside W3C context if instrumentation already manages propagation.

Information to store: project/resource alias, region, service/method, status/error reason, SDK diagnostic metadata, operation ID for async APIs, trace ID, and UTC timestamp. If no explicit provider request ID exists, record that field as unavailable rather than inventing a value and mislabeling it as a Google Cloud ID.

### 5.4. Quick reference table

| Provider | Commonly useful metadata | Where to obtain |
|---|---|---|
| AWS | SDK `requestId`; `x-amzn-RequestId` or `x-amz-request-id`; S3 may include `x-amz-id-2` | AWS SDK response/exception metadata or service-specific response headers |
| Azure | `x-ms-request-id`, `x-ms-correlation-request-id`, client request ID, or Service Bus `TrackingId` depending on service | Azure SDK response/exception diagnostics or allowlisted response headers |
| Google Cloud | API-specific request/operation metadata; trace resource/trace ID; client library diagnostics | Google Cloud client response/exception metadata and Cloud Logging/Trace |

Do not collapse everything into a single `requestId` field and lose its origin. Use distinct fields such as `providerRequestId`, `providerOperationId`, `traceId`, and `requestId`; include `provider`/`service` to identify which system owns the ID.

## 6. Structured logging for investigation

Free-form text logs are hard to query under thousands of concurrent requests. Structured logging enables filtering by field without parsing prose.

Example of a sanitized log event:

```json
{
  "timestamp": "2026-11-24T04:15:32.481Z",
  "level": "ERROR",
  "service": "order-service",
  "environment": "production",
  "region": "ap-southeast-1",
  "requestId": "b6f8d2a0-7d5d-4d34-8f3d-7c3a3a7f9c10",
  "correlationId": "checkout-7f29d6a1",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "provider": "aws",
  "providerService": "dynamodb",
  "operation": "UpdateItem",
  "providerRequestId": "sample-provider-request-id",
  "resource": "orders-table-prod",
  "statusCode": 400,
  "errorCode": "ProvisionedThroughputExceededException",
  "attempt": 2,
  "durationMs": 184,
  "retryAfterMs": 250,
  "outcome": "throttled"
}
```

The IDs and request IDs in this example are illustrative placeholders, not real IDs. The `resource` field uses an alias instead of a full ARN if the ARN contains an account identifier or sensitive name. In real systems, log schemas should be consistent across services and validated by the logging pipeline.

### 6.1. Logging a provider attempt

An SDK call log should include these minimum fields:

- Provider, service, operation, and region.
- Current trace ID/span ID.
- Business correlation ID.
- Returned provider request ID or `null` if no response was received.
- Attempt number and total attempts if known.
- Status/error code, latency, and retry delay.
- Resource alias and payload size, never the payload itself.

If a request times out before receiving a response, a provider request ID may be absent. Log `providerRequestId: null`, `failurePhase: connect|read|unknown` if determinable, and keep the client exception. Never populate the provider request ID field with your application's own request ID.

### 6.2. Attaching trace/span to logs

With Micrometer Tracing, log correlation patterns can include `traceId` and `spanId` on every log line. Exact pattern configuration depends on the Spring Boot version and logging backend. If using MDC manually, ensure context is cleared after requests and propagated properly across async boundaries. In Reactor/WebFlux, prefer context propagation over relying solely on thread-local MDC.

You do not need to log all headers to achieve correlation. Log only allowlisted headers such as request IDs, trace context, and provider request IDs; exclude `Authorization`, `Cookie`, `Set-Cookie`, proxy auth, and token-bearing headers.

## 7. Redacting secrets and sensitive data

An evidence bundle needs enough detail to investigate while obeying the principle **allowlist first, redact second**. Collect only explicitly required fields; never dump entire requests/responses, environment variables, HTTP headers, JVM properties, or Spring configs and hope regex redaction catches every secret afterward.

### 7.1. Never include the following in logs or tickets

- `Authorization`, `Proxy-Authorization`, bearer tokens, OAuth refresh/access tokens, and cookies/session IDs.
- AWS AccessKeys/SecretKeys/session tokens, Azure client secrets/SAS tokens, Google service account private keys or access tokens.
- Private keys, keystore passwords, truststore passwords, or certificate material containing private keys.
- Full signed URLs (presigned URLs/SAS URLs), since query strings carry access grants.
- Database URLs containing usernames/passwords, Redis connection strings with credentials, or broker connection strings.
- Business payloads, files, emails, phone numbers, addresses, identity data, or payment details unless strictly necessary.
- `baggage` contents, message headers, or exceptions that could contain tokens/PII.

### 7.2. Fields to collect via allowlist

| Category | Appropriate fields |
|---|---|
| Timing | UTC timestamps, start/end times, durations, clock offset if known |
| Identifiers | Request ID, correlation ID, trace ID, span ID, provider request ID, approved event/message IDs |
| Application | Service name, environment, release/build version, pod/instance alias, JDK and SDK versions |
| Cloud | Provider, region, service/API, resource alias, operation |
| Outcome | HTTP/status code, provider error code, exception class, retry attempt, retry-after, outcome |
| Connectivity | Hostname stripped of query/userinfo, port, proxy alias, TLS version, certificate issuer/expiry if needed |
| Performance | Latency, payload size, pool active/idle/pending, queue depth, CPU/memory summary |
| Evidence | Sanitized stack trace, trace link, access-controlled dashboard link |

### 7.3. Redacting URLs and headers

When logging URLs, keep only scheme, hostname, port, and a sanitized path template. Strip userinfo and query strings by default. Example:

```text
Before: https://user:secret@storage.example/bucket/file?sig=abc123&token=xyz
After:  https://storage.example/bucket/{object}
```

Do not log `Authorization` and mask part of the token with `***`; it is safer not to log that header at all. For headers that must be kept, use an explicit allowlist:

```text
ALLOW:
  traceparent
  tracestate (if content has been verified)
  x-request-id
  x-correlation-id
  x-amzn-requestid / x-amz-request-id
  x-ms-request-id

DENY BY DEFAULT:
  authorization
  proxy-authorization
  cookie
  set-cookie
  x-api-key
  x-amz-security-token
  all unknown headers
```

Provider-specific header names must be allowlisted per service. Do not treat the list above as an exhaustive filter for every cloud SDK; the safe default is never logging unapproved headers.

### 7.4. Exceptions and stack traces

Stack traces are helpful, yet exception messages can contain full URLs, SQL, payloads, credentials, or sensitive resource names. Before logging, classify exceptions and log only sanitized messages. Keep cause chains in access-controlled internal logs when needed, applying redaction at appenders/collectors and restricting access.

Never return stack traces or provider request IDs along with internal details to end users. Public API responses should include a public error code and an application-generated request ID; keep technical details in internal logs/traces.

## 8. Building an evidence bundle for an incident

A good evidence bundle enables others to reconstruct the timeline without needing direct access to production data.

### 8.1. Recommended contents

| Artifact | Contents | Security notes |
|---|---|---|
| Incident summary | Symptom description, impact, start/end times, and scope | Exclude unnecessary user data |
| Request timeline | Request ID, correlation ID, trace ID, span ID, provider request ID, and UTC timestamps | Distinguish internal IDs from provider IDs |
| Sanitized logs | Relevant JSON logs, exception classes/error codes, and reviewed stack traces | Strip secrets, PII, payloads, and signed URLs |
| Trace export/link | Span tree, dependency latencies, retries, and error spans | Verify access controls and retention of the tracing backend |
| Metrics snapshot | Error rates, latency, throttling, pools, queues/backlogs, resource utilization | Use consistent time ranges and timezones |
| Runtime context | Service version, JDK, SDK/client versions, region, instance alias | Never dump full env or system properties |
| Sanitized config | Timeouts, retries, pool sizes, endpoint hostname/port, relevant feature flags | Redact passwords, tokens, and private endpoints if policy requires |
| Network/TLS evidence | DNS results, TCP tests, certificate issuer/SAN/expiry, proxy alias | Never attach private keys or full proxy credentials |
| Reproduction | Reproduction steps, sanitized sample request, expected/actual results | Use synthetic data and test endpoints when available |

### 8.2. Standardizing on a UTC timeline

Services may run across multiple regions/timezones. Use ISO 8601 UTC timestamps, e.g., `2026-11-24T04:15:32.481Z`. Ensure hosts/containers synchronize clocks via NTP or platform mechanisms. With large clock skew, log ordering can look wrong even when trace context is intact.

When investigating, pick a tight window around the provider request ID first, then widen it to capture retries and downstream effects. Explicitly state inclusive/exclusive time ranges, timezone, and timestamp precision. Never compare client and provider timestamps while ignoring clock skew.

### 8.3. Evidence summary example

```text
Incident: INC-2026-1124-017
Service: order-service
Environment: production
Region: ap-southeast-1
Window (UTC): 2026-11-24T04:15:00Z .. 2026-11-24T04:20:00Z
Symptom: DynamoDB UpdateItem intermittently throttled
Request ID: b6f8d2a0-7d5d-4d34-8f3d-7c3a3a7f9c10
Correlation ID: checkout-7f29d6a1
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Provider request ID: sample-provider-request-id (attempt 2)
Provider error: ProvisionedThroughputExceededException
Observed retry-after/backoff: 250 ms
Impact: 1.8% checkout requests exceeded 2 s latency
Evidence: sanitized log excerpt, trace link, throttling metrics, SDK version
Secrets/payload: omitted
```

The IDs and values above illustrate formatting only. Omit real account IDs, table keys, or order payloads from tickets unless strictly necessary.

## 9. Isolation workflow starting from a request ID

When given a request ID by a user or gateway:

1. Determine which service owns the ID and which ID type it is. An `X-Request-ID` is not automatically a provider request ID.
2. Search the service's ingress logs within the UTC window; extract the correlation ID and trace ID.
3. Open the distributed trace and locate spans with errors or high latency; identify the service/client operation.
4. Search SDK logs by trace/span/correlation ID; extract provider, service, operation, region, and provider request ID.
5. If retries occurred, list every attempt chronologically with its individual request ID.
6. Look up the provider request ID in the appropriate tooling/telemetry/provider support flow; also supply timestamp, region, operation, and resource alias.
7. Cross-check metrics in the same time window to distinguish an isolated error, throttling, quota, pool saturation, or a broad outage.
8. Assemble a redacted evidence bundle and verify access permissions before sharing.

### 9.1. If the request ID is not found

A missing ID can have several causes:

- Request never reached the application (DNS, TLS, load balancer, ingress, or gateway rejected it earlier).
- Gateway generated an ID without forwarding it, or renamed the header.
- Logs were sampled, filtered, expired by retention, or routed to a different logging backend.
- ID was searched in the wrong service, environment, region, or time window.
- ID was truncated, normalized, or altered by a proxy.
- Request timed out before the provider replied, leaving no provider request ID.

Broaden the search using correlation ID, trace ID, timestamp, route, service version, and status code. Inspect ingress/gateway access logs and load balancer metrics. Never conclude a request never happened solely because one service lacks a log entry.

### 9.2. If multiple provider request IDs exist

One trace can invoke multiple provider APIs; one SDK call can retry multiple times. Build a per-attempt timeline table:

| UTC timestamp | Span/operation | Attempt | Provider request ID | Result | Duration |
|---|---|---:|---|---|---:|
| 04:15:32.100Z | DynamoDB UpdateItem | 1 | `req-a` | Throttled | 82 ms |
| 04:15:32.350Z | DynamoDB UpdateItem | 2 | `req-b` | Throttled | 184 ms |
| 04:15:32.800Z | DynamoDB UpdateItem | 3 | `req-c` | Success | 96 ms |

This example shows request IDs changing per attempt while correlation/trace still links them to the same business operation. When opening a support case, include all related request IDs and note which attempts succeeded or failed.

## 10. Tools and log querying patterns

Tool names vary by platform, yet query practices stay consistent:

- Start with exact `requestId` or `correlationId`.
- Open the trace by `traceId`, then find spans with `status=ERROR`, `exception`, or abnormal latency.
- Filter SDK logs by `providerService`, `operation`, `providerRequestId`, and time range.
- Compare error rates/latency/pools/backlogs across the same window.
- Check releases/config changes/secret rotations/deployment events right before errors began.

Conceptual query example (actual syntax depends on your log backend):

```text
service = "order-service"
AND correlationId = "checkout-7f29d6a1"
AND timestamp BETWEEN "2026-11-24T04:15:00Z" AND "2026-11-24T04:16:00Z"
```

Never put IDs capable of accessing sensitive data into public dashboard URLs. Trace/log links may grant access to payloads or metadata; share them only with authorized people and use expiring links if supported by your platform.

## 11. Common mistakes

| Mistake | Consequence | Right approach |
|---|---|---|
| Using one `requestId` across every service and every retry | Cannot distinguish individual requests/attempts | Keep per-service request IDs, cross-system trace IDs, and per-attempt provider request IDs |
| Calling a correlation ID a provider request ID | Support cannot find the request at the cloud provider | Store separate fields and record ID provenance |
| Trusting client-sent headers without validation | Log spoofing, CRLF injection, or muddled investigations | Overwrite headers at gateway; validate charset/length; never use for auth |
| Logging all request/response headers | Leaks tokens, cookies, SAS/presigned URLs | Allowlist required headers, deny-by-default |
| Sending entire `.env`, env dumps, or `application-prod.yml` to support | Exposes secrets and internal topology | Build sanitized configs containing only relevant properties |
| Saving only the final retry's request ID | Loses evidence of earlier throttling attempts | Log every attempt and its individual request ID |
| Using `orderId`/email as metric labels | High cardinality and data leakage | Keep IDs in logs/traces; use stable values for metric tags |
| Assuming no trace means no request occurred | Sampling or broken propagation can omit traces | Check logs, gateways, metrics, and trace sampling policies |
| Sharing dashboard links without checking permissions | Recipients may view out-of-scope data | Enforce least privilege, scoped links, and redacted evidence |

## 12. Security checklist before sending evidence

- [ ] Audience and purpose are confirmed; share only the minimum necessary scope.
- [ ] UTC timestamps, request IDs, correlation IDs, trace IDs, and provider request IDs are placed in the right fields.
- [ ] Service, environment, region, operation, error code, duration, and attempt are recorded.
- [ ] Exact provider request IDs are preserved; never substitute internal IDs.
- [ ] `Authorization`, cookies, API keys, access tokens, secrets, private keys, and passwords are removed.
- [ ] Presigned URL/SAS queries, payloads, PII, and payment data are removed.
- [ ] URLs contain only host/path templates; queries/userinfo are stripped.
- [ ] Exceptions/stack traces are reviewed for sensitive content.
- [ ] No `.env`, environment dumps, heap dumps, or unreviewed full configs are attached.
- [ ] Dashboard/trace links have restricted access and appropriate expiration.
- [ ] Evidence files are stored in a controlled location with proper retention and auditing.
- [ ] A second reviewer verified redaction before sending outside the organization.

## 13. Conclusion

Isolating incidents with request IDs works when every identifier has a clear role and stays connected across logs, traces, SDKs, and brokers. Request IDs locate requests inside one service; correlation IDs link business flows; traces/spans reveal execution paths; provider request IDs enable cloud-side lookup; event/message IDs track asynchronous processing. An evidence bundle should capture timestamps, operations, attempts, error codes, provider metadata, and related metrics while collecting only approved fields. Applying allowlists, stripping secrets at the source, and controlling sharing permissions let engineering teams investigate quickly without creating new data exposure risks.

## References

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent` and `tracestate` specifications.
- [W3C Baggage](https://www.w3.org/TR/baggage/): propagating metadata in distributed traces and security limitations.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, propagation, and sampling.
- [Micrometer Tracing](https://micrometer.io/docs/tracing): traces/spans, bridges, and context propagation.
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/): propagating trace context across process boundaries.
- [AWS SDK for Java 2.x — Logging and metrics](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/logging-slf4j.html): SDK logging and diagnostics.
- [Azure SDK for Java — Logging](https://learn.microsoft.com/azure/developer/java/sdk/logging-overview): logging, diagnostics, and request metadata.
- [Google Cloud — Structured logging](https://cloud.google.com/logging/docs/structured-logging): structured log fields and trace correlation.
- [Google Cloud — Correlate logs with traces](https://cloud.google.com/trace/docs/trace-log-integration): linking logs with traces in Cloud Logging.
