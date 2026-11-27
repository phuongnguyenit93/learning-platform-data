# Client Logs, Request IDs, and Tracing with Sensitive Data Redaction

When a Spring Data Elasticsearch application encounters an error or responds slowly, you must be able to correlate an operation in the API/service with the request received by Elasticsearch, client logs, and shard activity. Structured logs, request IDs, and distributed traces make that possible. However, raw request/response logs can leak passwords, API keys, personal data, document contents, or sensitive search terms.

A safe observability design must satisfy two goals simultaneously:

- **Sufficient context for investigation**: know who called at an appropriate technical identifier level, which operation, which index/alias, how long it took, what error type occurred, and which trace the request belongs to.
- **Limit logged data**: log only necessary metadata, mask or strip secrets/PII, and control log access and retention.

This lesson distinguishes logs, request IDs, and traces; shows how to generate and propagate correlation IDs across Spring, the Elasticsearch client, and Reactor; explains Elasticsearch's `X-Opaque-Id` header; and covers redaction, transport logging, slow logs, metrics, and testing data masking.

## 1. Logs, metrics, and traces answer three different questions

Observability typically combines three signal types:

| Signal | Question answered | Example |
|---|---|---|
| Log | What happened at a specific moment? | Bulk index write failed with HTTP 429 |
| Metric | How often is it happening? | 429 rate rose from 0.1% to 8% |
| Trace | Which services/spans did a request traverse, and where was time spent? | API → service → Elasticsearch search took 1.8 seconds |

Do not use logs to replace metrics, or use trace IDs as metric labels.

A useful log may include:

- Timestamp and log level.
- Service, environment, and version.
- Operation: search, index, update, bulk, delete.
- Index or alias.
- Request ID/correlation ID.
- Trace ID and span ID if distributed tracing is enabled.
- Duration, HTTP status, Elasticsearch error type.
- Retry attempt and outcome.

A log does not need to contain the request body, document source, or full response. Those make logs bulky, hard to control, and prone to leaking sensitive data.

## 2. Distinguishing request ID, correlation ID, trace ID, and span ID

These IDs are related but not synonymous:

| ID | Scope | Purpose |
|---|---|---|
| Request ID | One request at a boundary, usually an API/backend request | Find logs for a specific request |
| Correlation ID | A business flow that may span multiple messages/requests | Link steps belonging to the same task |
| Trace ID | One distributed trace | Group spans belonging to the same journey |
| Span ID | One operation inside a trace | Identify a specific step such as calling Elasticsearch |
| Elasticsearch opaque ID | A labeled Elasticsearch request/task | Find the Elasticsearch request in logs/task APIs |

Example of publishing a product:

~~~text
HTTP request
  requestId = req-8f2a
  traceId   = 4bf92f...
      |
      v
Product service
  spanId = a12...
      |
      +----> Database
      |       spanId = b31...
      |
      +----> Elasticsearch
              spanId = c45...
              X-Opaque-Id = req-8f2a-es-1
~~~

A trace can span multiple request IDs or correlation IDs as work continues through queues and workers. A request ID can be recorded across multiple services if propagated by contract. A span ID represents only one span and should not be manually regenerated on every log line.

Never treat a request ID as proof of authentication or authorization. Knowing an ID must never allow a caller to read documents or access traces.

## 3. Correlation flow from application to Elasticsearch

A typical observability flow:

~~~mermaid
flowchart LR
    A["HTTP client"] --> B["Request filter"]
    B --> C["Spring service"]
    C --> D["Spring Data Elasticsearch"]
    D --> E["HTTP client / transport"]
    E --> F["Elasticsearch"]
    B -. "requestId + trace context" .-> C
    C -. "trace span" .-> D
    E -. "X-Opaque-Id / traceparent" .-> F
    F -. "server logs / task metadata" .-> G["Operations"]
    C -. "structured logs" .-> H["Log platform"]
    D -. "trace spans" .-> I["Tracing backend"]
~~~

At every boundary, know which IDs are preserved, which are newly generated, and which are forwarded.

An easy-to-operate rule:

- Generate or validate a request ID at the ingress/API boundary.
- Use tracing instrumentation to manage trace/span context.
- Carry correlation IDs in message envelopes for asynchronous work.
- Attach an appropriate opaque ID to Elasticsearch requests when server-side lookup is needed.
- Do not generate a fresh ID at every layer and break the link to the original request.

## 4. Generating request IDs in Spring MVC

In Servlet applications, you can use `OncePerRequestFilter` to create a request ID if absent, put it into MDC, and return it in a response header.

Example:

~~~java
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class RequestIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Request-ID";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        String supplied = request.getHeader(HEADER);

        // You can always generate an internal ID; if accepting an upstream ID,
        // accept only strings whose length and characters match an allowlist.
        String requestId = supplied != null
                && SAFE_ID.matcher(supplied).matches()
                ? supplied
                : UUID.randomUUID().toString();

        try {
            MDC.put("requestId", requestId);
            response.setHeader(HEADER, requestId);
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Register the filter in the application context or security/filter chain in the order appropriate for your application.

Notes:

- If a trusted API gateway already generated a request ID, you can keep it after validation.
- If upstream sources are untrusted, generate a new internal ID and record the validated upstream ID in a separate field.
- Limit length and allowed characters to prevent log injection, newlines, or excessively long values.
- Always clear MDC inside `finally`; thread pools reuse threads across requests.
- Never use request IDs to make access-control decisions.

With Spring WebFlux, do not copy Servlet ThreadLocal/MDC usage directly into every reactive callback. Reactor can switch execution across threads; context must be propagated via Reactor Context or Micrometer Context Propagation.

## 5. Correlation IDs for messages and background jobs

An HTTP request may emit an event for a worker to process later. Once the request finishes, the worker no longer runs on the same thread or inside the same request context.

Propagate required metadata inside the message envelope:

~~~json
{
  "eventId": "evt-184",
  "correlationId": "order-flow-72a1",
  "causationId": "req-8f2a",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "eventType": "ProductPublished",
  "payload": {
    "productId": "P-1001"
  }
}
~~~

Meaning:

- `eventId`: event identifier, used for deduplication.
- `correlationId`: links steps belonging to the same business flow.
- `causationId`: indicates the action or message that produced this event.
- `traceparent`: W3C Trace Context if the tracing system propagates traces across messages.
- `payload`: minimal business data required by the consumer.

Do not use one field to replace all others. Event IDs serve uniqueness and idempotency; correlation IDs serve investigation; trace context serves latency analysis. Avoid putting emails, access tokens, or personal content into these IDs.

If your message broker/client already supports tracing header propagation, prefer standard instrumentation/propagators rather than manually parsing and concatenating `traceparent` strings.

## 6. Distributed tracing with W3C Trace Context

W3C Trace Context defines common headers:

- `traceparent`: carries version, trace ID, parent span ID, and trace flags.
- `tracestate`: carries vendor-specific details if present.

Example `traceparent` format:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Applications should generally not generate trace IDs and span IDs manually with UUIDs and call that distributed tracing. Trace backends require valid span relationships, timings, statuses, and parent-child contexts.

With Spring Boot, Micrometer Tracing and OpenTelemetry instrumentation can create/propagate trace contexts and inject trace/span IDs into logs per configuration. The Elasticsearch HTTP client must be supported by instrumentation or configured so outbound spans are created and context is propagated.

A trace helps separate:

- Time spent in controllers/services.
- Client-side mapping/conversion time.
- Request time across HTTP transport.
- Server time reported in the Elasticsearch response.
- Downstream processing time after search completes.

Do not treat trace span duration as equal to the Elasticsearch `took` field. Spans typically include network, connection pooling, serialization, and waiting time; `took` is the time Elasticsearch reports for processing the corresponding request portion.

## 7. Attaching X-Opaque-Id to Elasticsearch requests

Elasticsearch supports the `X-Opaque-Id` header to tag a request with a client-provided value. This value helps correlate requests with Elasticsearch server logs or tasks, depending on the API and configuration/version.

HTTP example:

~~~http
GET /products/_search
X-Opaque-Id: req-8f2a-es-search-1
~~~

Guidelines:

- Use short values without PII or secrets.
- You can include the request ID/correlation ID in the opaque ID.
- You can append an operation suffix to distinguish search, bulk, or update.
- Do not use the same fixed opaque ID for every request, as distinguishing requests becomes difficult.
- Do not treat opaque IDs as authentication tokens or access permissions.
- Confirm the header is sent by the client and received by the server in your active environment.

Opaque ID does not replace W3C `traceparent`. A value used to look up an Elasticsearch request does not automatically create trace spans or parent-child relationships.

## 8. Configuring headers in Spring Data Elasticsearch

Spring Data Elasticsearch provides `ClientConfiguration` to configure connections and default HTTP headers. In versions providing `withHeaders(...)`, you can add headers via a supplier:

~~~java
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.http.HttpHeaders;

ClientConfiguration clientConfiguration =
        ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .withHeaders(() -> {
                    HttpHeaders headers = new HttpHeaders();
                    headers.add("X-Opaque-Id", "integration-test");
                    return headers;
                })
                .build();
~~~

The example above uses a static value suitable for a test or dedicated client. The exact signature and behavior of the header supplier must be verified against your Spring Data Elasticsearch version.

If you want the opaque ID to vary per request:

1. Confirm the supplier is invoked when sending each request in your version.
2. Read the request context using an appropriate context propagation mechanism.
3. Do not read MDC ThreadLocal inside reactive flows without propagation.
4. If the API only supports static default headers, use an HTTP client/transport interceptor or request options supporting per-request headers.
5. Test that headers are actually sent per request and not leaked from a prior request.

Do not configure `X-Opaque-Id` as one constant string for all production traffic if your goal is distinguishing individual requests. A constant header only identifies the client/workload, not specific operations.

For trace propagation, prefer OpenTelemetry/Micrometer HTTP client instrumentation. Avoid hardcoding a static `traceparent` in `ClientConfiguration`; `traceparent` must reflect the active span.

## 9. Request IDs and trace context in Reactor

In Spring WebFlux or reactive Elasticsearch operations, a single request may run across multiple threads. ThreadLocal-based MDC does not automatically preserve context when Reactor switches schedulers.

Example flow:

~~~java
return productRepository.findByStatus("PUBLISHED")
        .flatMap(product -> enrichProduct(product))
        .doOnNext(product ->
                log.info("Product enriched")
        );
~~~

If the request ID was placed only in MDC on the initial thread, logs inside `flatMap` may miss the ID or pick up stale values if context is not propagated properly.

Solutions:

- Use Micrometer Context Propagation and configure Reactor integration matching your Spring Boot version.
- Store request/correlation metadata in Reactor Context.
- Use Micrometer Tracing/OpenTelemetry to manage trace context.
- Populate MDC values for logging only at boundaries supported by context propagation.
- Clean up ThreadLocals after use; never leave actor/request IDs lingering in thread pools.

Illustrating storing a value in Reactor Context:

~~~java
return productRepository.findByStatus("PUBLISHED")
        .contextWrite(context ->
                context.put("correlationId", correlationId)
        );
~~~

Reading context inside operators requires appropriate Reactor APIs such as `deferContextual`:

~~~java
Mono<String> currentCorrelationId =
        Mono.deferContextual(context ->
                Mono.just(context.get("correlationId"))
        );
~~~

This illustrates Reactor Context, not a complete MDC bridge. In real applications, use configured and tested instrumentation/context propagation rather than writing ad-hoc global hooks.

## 10. Structured logging instead of free-form string concatenation

Structured logs enable querying by fields, filtering by service/index/operation, and building dashboards.

Example JSON log:

~~~json
{
  "timestamp": "2026-11-13T10:15:30.123Z",
  "level": "INFO",
  "service": "catalog-api",
  "environment": "test",
  "message": "Elasticsearch search completed",
  "requestId": "req-8f2a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "operation": "search",
  "index": "products",
  "httpStatus": 200,
  "hitCount": 25,
  "durationMs": 42
}
~~~

You can log key-value details:

~~~java
log.info(
        "Elasticsearch operation completed: operation={}, index={}, durationMs={}, hitCount={}",
        "search",
        "products",
        duration.toMillis(),
        hitCount
);
~~~

If using a structured logging encoder, configure fields as JSON properties rather than emitting a single long message string.

Do not include the following in default logs:

- Full document `_source`.
- Full Query DSL if it contains emails, phone numbers, tokens, or sensitive search terms.
- Passwords, API keys, Authorization headers.
- Cookies, session tokens, private keys, or keystore passwords.
- URLs with userinfo or secrets in query parameters.
- Personal data unnecessary for operations.

## 11. Safe log field allowlist

An easily controllable practice is defining an allowlist of metadata permitted in logs:

| Field | Loggable? | Rule |
|---|---|---|
| `requestId` | Yes | Restrict length/characters |
| `traceId`/`spanId` | Yes | Obtain from tracing instrumentation |
| `operation` | Yes | Application-controlled enum/value |
| `index` | Conditional | Use normalized index names containing no secrets |
| `durationMs` | Yes | Technical measurement |
| `httpStatus` | Yes | Status number |
| `errorType` | Yes | Error type, after bounding length |
| `documentId` | Conditional | May be identifying data; hash/tokenize if needed |
| `tenantId` | Conditional | Log only if policy allows; consider pseudonymization |
| `queryBody` | No by default | Log only redacted version in controlled environments |
| `documentSource` | No by default | Do not log full payloads |
| `Authorization` | No | Always strip |
| `password/apiKey` | No | Always strip |

Allowlists are usually safer than denylists. Denylists easily miss newly introduced sensitive fields.

If you need to know which document failed, consider logging an ID hashed with HMAC using a separately managed key instead of writing raw IDs that may contain emails or customer numbers. Hashing usually does not replace full data classification; assess reversibility and retention policies as well.

## 12. Multi-layer redaction

Data redaction should happen before logs leave the application, rather than relying solely on dashboards or log access controls.

Layers to review:

1. **Application logging**: log only allowlisted metadata; do not log objects/query bodies by default.
2. **HTTP client logging**: disable or redact sensitive headers/bodies before writing.
3. **Exception logging**: check whether exception messages embed URLs, queries, or payloads.
4. **Proxy/gateway logs**: strip Authorization, Cookie, and sensitive query parameters.
5. **Elasticsearch slow logs**: restrict access and review query contents.
6. **Log pipelines**: apply additional masking as defense in depth, not as a substitute for source redaction.

Example safe log:

~~~json
{
  "message": "Elasticsearch request failed",
  "requestId": "req-8f2a",
  "operation": "index",
  "index": "products-v2",
  "httpStatus": 400,
  "errorType": "mapper_parsing_exception",
  "field": "price",
  "durationMs": 18
}
~~~

Example unsafe log:

~~~json
{
  "message": "Request failed",
  "authorization": "ApiKey ...",
  "password": "...",
  "document": {
    "customerEmail": "person@example.com",
    "phone": "+84...",
    "privateNotes": "..."
  }
}
~~~

Do not merely replace passwords with asterisks while leaving the Authorization header or full body intact. Secrets can appear in multiple formats across multiple layers.

## 13. Do not enable HTTP wire logging indiscriminately

HTTP wire logging can expose raw headers and request/response bodies. It is a deep diagnostic tool, but carries major risks:

- Exposes Authorization/API keys.
- Exposes document sources and personal data.
- Exposes search queries containing user input.
- Expands log volume very rapidly.
- Adds CPU/I/O overhead and alters request timing.
- Logs may be shipped to storage systems with broader access than Elasticsearch itself.

Enable it only briefly, in test/staging environments with synthetic data, with restricted log access and an explicit shutoff procedure.

Specific logger names depend on the HTTP client/transport and version, such as Apache HTTP client or Netty loggers. Do not copy a logger name from an old stack and assume it covers every transport.

If you need to inspect headers, prefer logging header names and presence/absence of credentials instead of header values. If you need to inspect bodies, use fake payloads or redacted, size-capped versions.

Do not use packet captures or wire logs to collect production credentials without proper purpose, authorization, and safeguards.

## 14. Elasticsearch server logs and slow logs

Client logs show what requests the application sent at a metadata level and what outcomes it received. Elasticsearch server logs show how nodes processed requests, shards, and tasks.

Useful sources:

- Elasticsearch server logs.
- Index search slow logs.
- Index indexing slow logs.
- Cluster/node stats and thread pool stats.
- Task API.
- Audit logs if security auditing is enabled and properly configured.

Slow logs can record query or source details depending on log type and configuration. Query DSL can contain user data; therefore, slow logs also require proper access controls, retention, and redaction.

An investigation workflow:

1. Obtain the request ID/opaque ID from application logs.
2. Search for the same value in Elasticsearch server logs or task metadata if your version/API records it.
3. Compare timestamps and indices.
4. Inspect slow logs or shard/node metrics around that time.
5. Correlate trace spans to separate client/network/server time.
6. Conclude the investigation with a measurable change rather than leaving wire logging enabled indefinitely.

Not all APIs or log formats record opaque IDs identically. Verify on the active Elasticsearch version before relying on it as a universal lookup key.

## 15. Correlating client duration with Elasticsearch took

Example log:

~~~json
{
  "operation": "search",
  "clientDurationMs": 820,
  "elasticsearchTookMs": 35,
  "httpStatus": 200,
  "hitCount": 50
}
~~~

Client duration being much larger than Elasticsearch `took` can point to time outside server execution:

- Waiting on the connection pool.
- DNS or opening a new connection.
- TLS handshake.
- Network/load balancer.
- Request serialization and response deserialization.
- Client-side retries.
- Scheduler queues or downstream backpressure.

If both are high, investigate query/shard/cluster load. If Elasticsearch `took` is low while the application is slow, do not jump to optimizing Query DSL; check transport, connection pools, and post-response processing.

These two measurements are not strictly identical because their measurement methods and scopes differ. Use trace spans and client metrics to analyze the gap.

## 16. Logging bulk operations per item without logging payloads

A bulk request can contain hundreds or thousands of items. Logging a single "bulk failed" line makes it hard to tell which items failed. Logging the whole body can expose all the data.

Log a summary plus per-item metadata outcomes:

~~~json
{
  "message": "Elasticsearch bulk completed with failures",
  "requestId": "req-import-51",
  "operation": "bulk",
  "index": "products-v2",
  "itemCount": 500,
  "successCount": 493,
  "failureCount": 7,
  "failureTypes": {
    "mapper_parsing_exception": 5,
    "version_conflict_engine_exception": 2
  },
  "durationMs": 640
}
~~~

For each failed item, log only essential fields:

- Item position or internal item reference.
- Protected document ID.
- Action type.
- Status/error type.
- Retry count.
- Event ID/correlation ID if non-sensitive.

Do not log the full source just to point out a mapping error. You can log the failing field name and classified expected/actual data types while avoiding personal values or secrets.

If a bulk batch is reprocessed, preserve the event ID/document ID to link retries back to the original attempt. Avoid issuing a brand-new request ID that severs the link to the original batch; you can assign a new request ID per resend while keeping a shared correlation ID.

## 17. Tracing for reactive and async requests

In reactive pipelines, trace context must follow publishers across schedulers and outbound clients. In async jobs, context must be propagated across executor/message boundaries via instrumentation or message propagators.

Scenarios needing attention:

- `@Async` spawning new threads.
- `CompletableFuture` executing on executors.
- Reactor `publishOn`/`subscribeOn`.
- Kafka/RabbitMQ listeners.
- Scheduled jobs.
- Retries creating multiple attempts.
- Bulk workers processing multiple events in one batch.

Do not manually copy only `traceId` into MDC and assume span relationships are preserved. The tracing framework must create child spans and manage context lifecycles.

For messages processed minutes or hours later, you can choose to continue the trace across messages or start a new trace linked to the previous context, depending on tracing design and retention. Business correlation IDs can still outlive traces.

## 18. Logging exceptions safely

When logging exceptions, preserve the stack trace for root-cause investigation, but scrutinize the exception message contents.

Example:

~~~java
try {
    operations.save(document, indexCoordinates);
} catch (RuntimeException ex) {
    log.error(
            "Elasticsearch write failed: requestId={}, operation={}, index={}, documentId={}",
            requestId,
            "save",
            safeIndexName,
            safeDocumentReference,
            ex
    );
    throw ex;
}
~~~

If an exception message embeds request URLs or bodies, the logger may inadvertently record sensitive data even when log arguments are safe. For a given client/exception version, determine what information exceptions retain and apply an appropriate sanitizer.

Do not write:

~~~java
log.error("Elasticsearch request failed: {}", requestBody, ex);
~~~

Also do not put `ex.getMessage()` into public HTTP responses. Detailed technical information belongs in access-controlled logs; clients receive stable error codes and a correlation ID for support lookup.

## 19. Log levels and diagnostic activation duration

A practical log-level policy:

| Level | Used for | Example |
|---|---|---|
| ERROR | Failed operations requiring attention | Search dependency unavailable |
| WARN | Incomplete outcomes or retries nearing limits | Bulk item failures, partial search shards |
| INFO | Significant business/operational milestones | Reindex started/completed |
| DEBUG | Redacted technical details | Query type, index, page size |
| TRACE | Short-lived deep diagnostics | HTTP transport details on test data |

Do not log an INFO line for every document in a bulk request under high-throughput ingestion. Use batch summaries and metrics to track counts.

If enabling DEBUG/TRACE via runtime logger configuration, establish:

- Enable/disable timeframe.
- Approver or investigation ticket if required by the environment.
- Specific service/index scope.
- Redaction verification before enabling.
- Automatic or manual restoration of log levels.
- Monitoring of log volume and access controls.

## 20. Metrics must not use request IDs as labels

Metrics are typically stored as time series, where labels create distinct series. If each request ID generates a label value, cardinality grows roughly linearly with requests and exhausts metrics memory.

Use labels with bounded value sets:

~~~text
elasticsearch_requests_total{
  operation="search",
  outcome="success"
}

elasticsearch_requests_total{
  operation="bulk",
  outcome="failure"
}

elasticsearch_request_duration_seconds{
  operation="search"
}
~~~

Do not do:

~~~text
elasticsearch_requests_total{
  request_id="req-8f2a"
}
~~~

Request IDs, trace IDs, and document IDs belong in logs/traces for looking up specific calls. Metrics should aggregate by operation, outcome, status class, index family, or normalized service.

## 21. Protecting logs, traces, and telemetry data

Logs and traces can contain sensitive data even without passwords. Search queries can contain emails, usernames, phone numbers, tenant IDs, or user-entered text. Trace attributes can inadvertently record URLs/paths containing personal data.

Define:

- Who has permission to view logs and traces.
- What data is allowed to be collected.
- Retention periods.
- Encryption in transit and at rest.
- How data is deleted/masked per policy.
- Procedures if credentials are accidentally logged.
- How to prevent secrets from appearing in alerts, dashboards, and CI artifacts.

Do not use trace baggage to carry tokens or PII. Baggage can propagate across many services and spread sensitive data further.

If associating a user with a request is required, prefer a pseudonymous ID with a clear policy over emails or full names. Do not embed user information in span names; span names should describe operations such as `Elasticsearch search products`.

## 22. Testing redaction and correlation

Do not rely solely on eyeballing logs in a single run. Write tests ensuring secrets do not appear in outputs.

Conceptual test example:

~~~java
@Test
void logsRequestMetadataWithoutCredentialOrDocumentSource() {
    // 1. Build a test request with a fake API key and a document containing fake sensitive data.
    // 2. Send the request through the service with an appender capturing logs to a buffer.
    // 3. Read the log output.
    // 4. Assert requestId/operation/index/status are present.
    // 5. Assert API key, password, email, and source body do not appear.
}
~~~

Scenarios to cover:

- Request ID is generated when header is missing.
- Overly long or newline-containing incoming request IDs are rejected/replaced.
- Request ID is returned in the response header per policy.
- Trace ID/span ID appear in logs when tracing is enabled.
- Opaque ID is sent to the Elasticsearch client if configured.
- Correlation ID propagates across message consumers.
- MDC is cleared after requests to avoid leaking to subsequent requests.
- Reactor context is preserved across scheduler boundaries.
- Authorization/API keys/passwords are redacted.
- Query/document payloads do not appear in default logs.
- Exceptions containing sensitive info are not echoed verbatim in public responses.

Use fake secrets with an easily searchable marker such as `TEST_SECRET_DO_NOT_LOG`. Tests can assert the marker does not appear in captured logs. Never use production credentials as test fixtures.

## 23. Procedure for investigating a slow or failed request

When given a request ID by a user or an alert:

1. Search for the request ID in application logs.
2. Retrieve the trace ID and open the corresponding distributed trace.
3. Locate the span calling Elasticsearch and its operation/index.
4. Read client duration, status, retries, and exception category.
5. Retrieve the opaque ID if attached to the Elasticsearch request.
6. Search related server logs, slow logs, or task metadata.
7. Compare Elasticsearch `took` with the client span duration.
8. Check shard failures, timeouts, thread pools, or mapping/authorization errors if present.
9. Check the bulk item summary if the operation was bulk.
10. Determine whether the fault lies in the application, transport, cluster, or downstream.
11. Fix the root cause and verify via traces/metrics after deployment.
12. Turn off temporary diagnostic logging and review retention/access of collected data.

Without a trace backend, request IDs and structured logs can still assist investigation. Without server-side opaque IDs, you can still correlate by timestamp, index, operation, and node logs, though precision will be lower.

## 24. Common mistakes

### Generating a new ID at every layer

Every service creating its own correlation ID breaks linkage. Preserve request/correlation IDs across boundaries and let the trace/span framework create child spans.

### Treating request ID as trace ID

A request ID does not build a span tree or timings. Use proper distributed tracing and keep request ID as supplementary metadata.

### Setting a static X-Opaque-Id

Every request sharing the same ID makes correlation hard. Use per-request values if the client supports per-request headers.

### Relying on MDC inside reactive flows

ThreadLocals may not follow publishers across schedulers. Use Reactor Context and Micrometer/OpenTelemetry context propagation.

### Logging full requests/responses

Can leak documents, queries, passwords, or API keys. Prefer metadata allowlists and source-side redaction.

### Masking only the Authorization header

Secrets can appear in exception messages, URLs, query parameters, environment dumps, or wire logs. Check multiple layers.

### Leaving HTTP wire logging enabled long term

Wire logs capture payloads, consume resources, and multiply sensitive data. Enable only short-term with synthetic data and restricted access.

### Using trace IDs as metric labels

Cardinality grows rapidly. Keep IDs in logs/traces and use bounded-value labels for metrics.

### Logging raw queries to debug search

Queries can contain personal info. Log query type, fields, page size, and duration; use redacted versions only when genuinely needed.

### Failing to clean up MDC

Thread pools reusing threads can carry stale request IDs onto new requests. Always clean up in `finally`.

### Treating dashboard-side log redaction as sufficient

Secrets still exist in raw logs or copies. Redact before writing and test actual output.

### Putting PII into opaque IDs

Opaque IDs can appear in logs/task metadata. Use random technical or pseudonymous IDs, never emails or tokens.

## 25. Implementation checklist

When setting up safe logging, request IDs, and tracing for Spring Data Elasticsearch:

1. Define distinct roles for request ID, correlation ID, trace ID, and span ID.
2. Generate or validate request IDs at the API boundary.
3. Use Micrometer Tracing/OpenTelemetry for distributed trace context.
4. Propagate correlation metadata across async executors and message envelopes.
5. Attach Elasticsearch `X-Opaque-Id` when server-side request lookup is needed.
6. Confirm the header mechanism is per-request if IDs must change per operation.
7. Use structured logging with a field allowlist.
8. Do not log sources, query bodies, or Authorization headers by default.
9. Redact exceptions, proxies, HTTP clients, and slow logs under the same policy.
10. Maintain proper MDC lifecycle and configure Reactor Context propagation.
11. Keep DEBUG/TRACE log levels time-bounded and narrowly scoped.
12. Use low-cardinality metric labels.
13. Restrict access and retention for logs/traces.
14. Test correlation, context propagation, and secret redaction.
15. Use request IDs/traces/opaque IDs to link client logs with Elasticsearch server logs during investigations.

## References

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Data Elasticsearch — Client configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Elasticsearch — X-Opaque-Id header](https://www.elastic.co/guide/en/elasticsearch/reference/current/api-conventions.html#api-opaque-id)
- [Elasticsearch — Search slow log](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-slowlog.html)
- [Elasticsearch — Indexing slow log](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-slowlog.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

## Conclusion

Structured logs show operations and outcomes; request/correlation IDs help locate related logs; trace/span IDs capture journeys and timings across services; Elasticsearch `X-Opaque-Id` tags server-side requests. In Spring Data Elasticsearch, propagate context across APIs, Reactor, and message boundaries using appropriate mechanisms, and confirm opaque ID headers are actually sent per request when needed. Use metadata allowlists, source-side redaction, and tests ensuring secrets/PII never appear in logs. Avoid logging raw bodies, Authorization, API keys, or long-term wire traffic; combine client durations, Elasticsearch `took`, slow logs, and traces to investigate without exposing sensitive data.
