# Safe request logging in Spring for GraphQL

Request logs help operations teams find root causes of errors, monitor performance, and detect anomalous behavior. However, a GraphQL request can carry a document, variables, extensions, and transport metadata. These parts often hold client-controlled data that may include passwords, access tokens, personal information, payment data, or business content.

Therefore, logging for GraphQL must be designed around the principle of **only logging explicitly permitted data**. Log enough metadata to trace an operation, measure duration, and classify outcomes; avoid logging full requests or responses. Data filtering must apply across the application, web server, reverse proxy, tracing backend, and centralized logging system.

## 1. Goals of request logging

A useful request log should answer operational questions:

- Which service received the request, and at what time?
- Which operation did the request belong to, and did it succeed or fail?
- How long did processing take?
- Can the log be correlated with a trace, other requests, or a specific error?
- Are there signs of limit violations, authentication failures, or anomalous behavior?

A good log does not need to contain all client-submitted data. For instance, to investigate a failed `PlaceOrder` call, you typically only need an operation label, request ID, outcome, duration, error category, and an order ID classified as safe to log. You do not need to store shipping addresses, card numbers, passwords, or access tokens.

Distinguish three goals:

| Log type | Goal | Typical content |
| --- | --- | --- |
| Operational log | Investigate errors and performance | Request ID, operation, outcome, duration, error count. |
| Security audit log | Record security and critical business events | Authentication failure, authorization denial, rate-limit event, administrative actions. |
| Trace/metric | Distributed tracing and statistics | Trace ID, span, operation type, field timing, low-cardinality outcome. |

Do not turn every request log into an audit log. Audit events require separate schemas, access controls, retention, and traceability per organizational requirements.

## 2. What data does a GraphQL request contain?

A GraphQL request has these core components:

~~~json
{
  "query": "mutation PlaceOrder($input: PlaceOrderInput!) { placeOrder(input: $input) { id status } }",
  "operationName": "PlaceOrder",
  "variables": {
    "input": {
      "customerId": "customer-42",
      "deliveryAddress": "12 Example Street",
      "paymentToken": "secret-payment-token"
    }
  },
  "extensions": {
    "clientTrace": "client-specific-metadata"
  }
}
~~~

These components do not carry the same safety level:

| Component | Spring GraphQL API | Risk when logged |
| --- | --- | --- |
| GraphQL document | `getDocument()` | May contain sensitive literals, internal field names, or client-submitted query content. |
| Operation name | `getOperationName()` | Client-controlled; may contain control characters or create very high cardinality. |
| Variables | `getVariables()` | May contain passwords, tokens, PII, payment data, and business inputs. |
| Extensions | `getExtensions()` | Protocol-dependent metadata; should not be assumed harmless. |
| HTTP headers | `getHeaders()` | May contain `Authorization`, `Cookie`, API keys, and identifying info. |
| Cookies | `getCookies()` | May contain session IDs or refresh tokens. |
| Request attributes/context | `getAttributes()` or `GraphQLContext` | May contain principals, tenants, claims, or internal data. |
| Response data | `getData()` | May contain personal data or protected business data. |
| GraphQL errors | `getErrors()` | Error messages may contain invalid inputs, literal values, or internal details. |

In Spring GraphQL, `GraphQlRequest` provides document, operation name, variables, and extensions. `WebGraphQlRequest` additionally provides URI, headers, cookies, and attributes from the HTTP request or WebSocket handshake.

Do not call `request.toMap()`, `response.toMap()`, or log request/response objects directly. Those approaches can serialize more fields than intended, and `toString()` is not a safe logging contract.

## 3. Data that should not be logged directly

By default, exclude from logs:

- `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`.
- Passwords, OTPs, API keys, client secrets, access tokens, refresh tokens, session IDs.
- Private keys, encryption keys, database URLs with credentials, and connection strings.
- Card numbers, CVVs, bank accounts, and payment data.
- Health data, identity documents, and sensitive personal information.
- Emails, phone numbers, addresses, dates of birth, and full names unless there is a valid purpose.
- GraphQL variables, raw request bodies, raw response data, and unclassified extensions.
- GraphQL documents containing inline literals or user-supplied content.
- Unvetted exception messages or GraphQL error messages.

Do not assume GraphQL variables named `id`, `filter`, or `search` are safe. Their values can still be emails, phone numbers, account numbers, or secrets. An input variable can contain many nested sensitive fields.

If you need to associate actions with a user, use an approved internal identifier or a pseudonymized value. Plain hashes of emails or phone numbers can be brute-forced via dictionaries; if stable pseudonymization is required, consider HMAC with a separately managed key. Pseudonymized values may still qualify as personal data and require protection.

## 4. Using an allowlist instead of trying to mask every sensitive field

A safer approach is to define a small log schema and include only approved fields. For example:

| Field | Purpose | Rule |
| --- | --- | --- |
| `event` | Event name | Fixed value, e.g. `graphql.request.completed`. |
| `service` | Service name | Taken from service configuration, not from the request. |
| `environment` | Environment | Configured value such as `prod`, `staging`. |
| `request_id` | Log correlation | Length-bounded and sanitized ID. |
| `trace_id` | Distributed trace correlation | Taken from the configured tracing context. |
| `operation` | Operation label | Use only an allowlist or the label `other`. |
| `outcome` | Result | Fixed enum such as `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR`. |
| `duration_ms` | Processing time | Non-negative integer. |
| `error_count` | Number of GraphQL errors | Integer; do not log messages. |
| `error_category` | Error classification | Enum/allowlist, not raw exception messages. |

Do not put request IDs, user IDs, tenant IDs, field paths, or arbitrary operation names into metric labels. Unbounded values explode cardinality and storage costs. If you need them for investigation, record them in traces/logs under a separate policy with access controls.

## 5. Logging with WebGraphQlInterceptor

Spring GraphQL's HTTP and WebSocket transports invoke the `WebGraphQlInterceptor` chain before the request reaches GraphQL Java. This is the right place to log request and response metadata without manually reading or serializing bodies.

The following example logs only request ID, allowlisted operation label, validity, error count, and duration:

~~~java
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class SafeGraphQlRequestLoggingInterceptor
        implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGraphQlRequestLoggingInterceptor.class);

    private static final Set<String> KNOWN_OPERATIONS = Set.of(
            "GetBook",
            "SearchBooks",
            "PlaceOrder");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        long startedAt = System.nanoTime();

        String requestId = safeRequestId(request.getId());
        String operation = operationLabel(request.getOperationName());

        log.info(
                "graphql.request.started requestId={} operation={}",
                requestId,
                operation);

        return chain.next(request)
                .doOnNext(response -> {
                    long durationMs =
                            (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                            "graphql.request.completed requestId={} operation={} valid={} errorCount={} durationMs={}",
                            requestId,
                            operation,
                            response.isValid(),
                            response.getErrors().size(),
                            durationMs);
                })
                .doOnError(error -> {
                    long durationMs =
                            (System.nanoTime() - startedAt) / 1_000_000;

                    log.warn(
                            "graphql.request.failed requestId={} operation={} durationMs={} exceptionType={}",
                            requestId,
                            operation,
                            durationMs,
                            error.getClass().getSimpleName());
                });
    }

    private static String operationLabel(String operationName) {
        if (operationName == null || operationName.isEmpty()) {
            return "anonymous";
        }

        if (operationName.length() > 64) {
            return "other";
        }

        if (operationName.isBlank()) {
            return "anonymous";
        }

        return KNOWN_OPERATIONS.contains(operationName)
                ? operationName
                : "other";
    }

    private static String safeRequestId(String value) {
        if (value == null || value.isEmpty()) {
            return "unavailable";
        }

        String bounded = value.substring(0, Math.min(value.length(), 128));
        if (bounded.isBlank()) {
            return "unavailable";
        }

        String sanitized = bounded.replaceAll("[^A-Za-z0-9._-]", "_");
        return sanitized.substring(0, Math.min(sanitized.length(), 64));
    }
}
~~~

In Spring Boot, declare the interceptor as a bean (for example via `@Component` as above) so Boot registers it in `WebGraphQlHandler`'s `WebGraphQlInterceptor` chain. If building `WebGraphQlHandler` manually, register the interceptor with `builder.interceptors(...)`.

Key points to understand:

- The interceptor does not read `getDocument()`, `getVariables()`, `getExtensions()`, headers, or cookies.
- `operationLabel` permits only known operation names; client-supplied names are not logged verbatim.
- `safeRequestId` strips control characters and bounds length to reduce log injection risk.
- `response.isValid()` indicates whether the response has valid data per the GraphQL contract. A response can still be valid while containing field errors; therefore, also log `errorCount`.
- `doOnError` logs only the exception type, not `error.getMessage()` or the entire exception into request logs.
- `System.nanoTime()` is used to measure duration, not to record wall-clock timestamps.

`request.getId()` is a transport-supplied ID for request correlation. In WebFlux, the default ID can correlate with server logs; in Spring MVC, an ID is generated separately; in WebSocket, the ID corresponds to the subscribe message. Treat it as a correlation value, not a user identity or credential. If you need a guaranteed server-issued ID, generate a new correlation ID at a trusted edge and propagate it through context in a controlled manner.

The `KNOWN_OPERATIONS` list in this example is illustrative. In applications with many operations, you can manage the allowlist via configuration or a persisted-operation registry. If an allowlist is not feasible, log only `named`/`anonymous` or `other` rather than logging arbitrary client-supplied operation names verbatim.

## 6. Distinguishing request errors and field errors when logging

GraphQL can return partial data alongside errors. A response with field errors is not necessarily a completely failed request.

Example response with partial data:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"]
    }
  ]
}
~~~

`isValid()` can still be `true` because the response has non-null data. Consequently, logs must record both outcome/validity and error count. Do not infer that `valid=true` means zero errors.

Operationally, you can classify outcomes:

| Scenario | Suggested log outcome |
| --- | --- |
| Response has data and no errors | `SUCCESS` |
| Request parse/validation error | `REQUEST_ERROR` |
| Response has partial data and field errors | `PARTIAL_ERROR` |
| Unhandled internal exception | `INTERNAL_ERROR` |
| Transport error before/after GraphQL execution | `TRANSPORT_ERROR` |

This is an application log schema, not a mandatory standard GraphQL enum. Map from responses and error categories explicitly and consistently.

Do not log `GraphQLError.getMessage()` by default. Parser errors can include client-submitted tokens; custom resolvers can inadvertently include input values or database details in messages. Logging `errorCount`, an allowlisted error category, and request ID suffices for most operational logs. When deep investigation is needed, use traces or access-controlled internal logs without putting sensitive data into shared logs.

## 7. How does Spring GraphQL already log exceptions?

Spring for GraphQL registers `DataFetcherExceptionHandler` to handle `DataFetcher` failures and supports multiple `DataFetcherExceptionResolver` instances.

Per the default behavior described in the Spring GraphQL documentation:

- Exceptions unhandled by resolvers are classified as `INTERNAL_ERROR` and return a generic message containing the execution ID.
- Unhandled exceptions are logged at `ERROR` level along with the execution ID to correlate with the response.
- Exceptions handled by resolvers are logged at `DEBUG` level.

This helps avoid leaking implementation details in responses sent to clients. Still, applications should review exception messages, custom resolvers, and production log levels. Avoid adding an interceptor that re-logs the entire exception or message if Spring already records the corresponding event.

Resolvers should return safe information to clients. Do not embed passwords, tokens, SQL, connection strings, or raw inputs into GraphQL error messages. If exception details must be logged for investigation, use an internal logger with restricted access, redact data before logging, and keep the execution ID for correlation. Never return stack traces or internal messages to clients.

## 8. Be careful with GraphQL Observation and tracing

Spring for GraphQL supports Micrometer Observation for requests as well as `DataFetcher`/`DataLoader` activities. `GraphQlObservationInstrumentation` creates observations such as:

- `graphql.request`: the entire GraphQL request.
- `graphql.datafetcher`: non-trivial `DataFetcher` execution.
- `graphql.dataloader`: `DataLoader` and `@BatchMapping` execution.

Default keys are divided by cardinality:

| Group | Example | Where used |
| --- | --- | --- |
| Low cardinality | `graphql.operation.type`, `graphql.outcome`, `graphql.field.name` | Metrics and traces. |
| High cardinality | `graphql.execution.id`, `graphql.operation.name`, `graphql.field.path` | Traces; should not be used as metric tags. |

GraphQL request observation events may contain full error messages. Error messages can contain parser tokens, literals, or invalid client-submitted inputs. Therefore, when exporting traces to a centralized backend, verify whether conventions, event attributes, and exporters are storing sensitive messages.

Guidelines when configuring Observation:

- Put only bounded-value operation types and outcomes into metrics.
- Do not put request IDs, user IDs, tenant IDs, raw operation names, or query text into metric tags.
- Include high-cardinality values in traces only with a clear purpose and appropriate retention policy.
- Do not assume error messages are safe data.
- Use a custom `ObservationConvention` to control `KeyValues` added by the application.
- Inspect span events, baggage, MDC, and exporters; logger redaction does not automatically redact traces.

Trace IDs help link logs and traces, but are not authentication secrets. Obtain trace IDs solely from the configured tracing context, not directly from arbitrary headers without validation.

## 9. HTTP GET can expose queries and variables

By default, Spring GraphQL accepts only HTTP POST. GET can be explicitly enabled if an application needs caching or `EventSource`, yet GraphQL requests will then travel in the query string:

~~~text
/graphql?query=...&operationName=SearchBooks&variables=...
~~~

Query strings commonly show up in:

- Reverse proxy and web server access logs.
- Browser history.
- HTTP `Referer` headers.
- Gateway, CDN, and network monitoring logs.

Therefore, if `variables` may contain sensitive information, do not enable GET for that endpoint unless all associated exposure paths have been addressed. GraphQL GET should only execute Queries; Mutations must use an appropriate method and must never execute via GET.

Even when the application uses POST exclusively, do not enable request-body logging at proxies, gateways, filters, or HTTP client/server debug layers without a redaction policy. `WebGraphQlInterceptor` runs after the transport; it cannot erase data already written to earlier access logs.

Verify separately:

- Whether reverse proxy / ingress access logs record query strings.
- Whether the API gateway logs request bodies.
- Whether the web server has wiretap or payload debug logging enabled.
- Whether WebSocket handshakes log headers/cookies.
- Whether RSocket interceptors log payloads.
- Whether APM agents automatically capture request/response bodies.

## 10. Log injection and client-controlled data

Operation names, request IDs, error text, and metadata can be client-controlled. If CR/LF characters or delimiters are logged verbatim, attackers can forge log lines or corrupt log structure.

Do not concatenate log strings with input data:

~~~java
// Unsafe: client data may contain CR/LF.
log.warn("GraphQL request failed: " + operationName);
~~~

Use a fixed message template and parameters:

~~~java
log.warn("GraphQL request failed operation={}", safeOperation);
~~~

Parameterized logging keeps the message template fixed, but does not automatically strip CR/LF from values. Use a structured JSON encoder with proper escaping, bound lengths, and normalize inputs before logging.

Example helper:

~~~java
public final class SafeLogValue {

    private SafeLogValue() {
    }

    public static String sanitize(String value, int maxLength) {
        if (value == null) {
            return "null";
        }

        int limit = Math.max(0, maxLength);
        String bounded = value.substring(0, Math.min(value.length(), limit));
        return bounded
                .replace('\r', '_')
                .replace('\n', '_')
                .replace('\t', '_');
    }
}
~~~

This helper handles only control characters and length. It is not a secret redaction function. Do not pass raw variables, headers, exception messages, or query text through this helper and assume they are safe.

With structured logging, let the logging framework encode strings properly into JSON. Do not assemble JSON via manual string concatenation.

## 11. Structured logging with Spring Boot

Structured logging writes each event as JSON or a clearly defined schema format. This enables centralized log systems to filter by request ID, service, outcome, and duration without parsing free-form strings.

Since Spring Boot 3.4, structured logging is supported with formats such as ECS and Logstash; newer versions also support GELF. Example ECS configuration:

~~~yaml
logging:
  structured:
    format:
      console: ecs
      file: ecs

spring:
  application:
    name: catalog-graphql
~~~

You can add service metadata:

~~~yaml
logging:
  structured:
    ecs:
      service:
        name: catalog-graphql
        version: 1.0.0
        environment: production
~~~

Structured logging does not make data safe on its own. If the application places a token into the message or MDC, the JSON encoder will still write that token as a field. Build an allowlist before calling the logger.

Spring Boot allows including/excluding/renaming certain JSON members. This is an auxiliary defense on output formatting, not a substitute for keeping sensitive data out of log events in the first place.

If using MDC to attach request IDs, ensure MDC is cleared after the request and propagated properly across async/reactive boundaries. With WebFlux, do not assume `ThreadLocal`/MDC automatically follows every step of a Reactor pipeline; use proper context propagation or pass correlation metadata in the Reactor Context.

## 12. Which interceptor fits each transport?

Spring GraphQL supports multiple transports, and each transport has its own interception point:

| Transport | Extension point | Scope |
| --- | --- | --- |
| HTTP | `WebGraphQlInterceptor` | GraphQL requests/responses over HTTP. |
| WebSocket | `WebGraphQlInterceptor` or `WebSocketGraphQlInterceptor` | Individual GraphQL requests and connection/subscription lifecycles. |
| RSocket | `RSocketQlInterceptor` | GraphQL requests/responses over RSocket. |

A `WebGraphQlInterceptor` is not the only place to audit. Proxy access logs, WebSocket handshake logging, and RSocket payload logging live at different layers.

For WebSocket, avoid logging `connection_init` payloads or headers containing tokens. For subscriptions, avoid logging each full event payload; log event counts, stream state, duration, cancellations, and error categories.

## 13. MDC and correlation IDs

Correlation IDs help locate all logs related to a single request. You can use the transport request ID, GraphQL execution ID, or configured trace ID.

Rules:

- Prefer IDs issued by the server or tracing system.
- If accepting an ID from clients, bound its length and characters; never use it for authentication.
- Do not let correlation IDs become unbounded metric tags.
- Do not embed tokens or user identities inside correlation IDs.
- When requests run asynchronously, ensure context is propagated and cleaned up properly.
- Log the ID at request start, completion, and internal errors for easy correlation.

Example safe log:

~~~text
event=graphql.request.completed
service=catalog-graphql
request_id=6d3f1f7a
trace_id=4bf92f3577b34da6
operation=SearchBooks
outcome=SUCCESS
error_count=0
duration_ms=42
~~~

This example contains no document, variables, authorization headers, or response data.

## 14. Which security events should be logged?

Do not log only technical errors. The following events are valuable for detection and investigation:

| Event | Appropriate data to log |
| --- | --- |
| Authentication failure | Timestamp, request ID, authentication method, outcome; never log credentials. |
| Authorization denial | Operation/field label, error category, actor pseudonym if permitted. |
| Query depth/complexity limit | Operation label, measured depth/cost, configured limit, outcome. |
| Rate limit | Client category or pseudonym, limit bucket, request ID, outcome. |
| Invalid persisted query | Classified persisted query hash, operation label if known. |
| Administrative mutation | Actor pseudonym, action, entity type, permitted entity ID, outcome. |
| Schema/introspection policy violation | Operation category, outcome, request ID. |
| Logging pipeline failure | Sink, retry count, degraded state; do not log request payloads to compensate. |

Security audit logs should capture meaningful events, not dump every request body. If logging actor or tenant identifiers, define purpose, data classification, and retention before deployment.

Do not read IP addresses from `X-Forwarded-For` blindly. Trust forwarded headers only from proxies configured as trusted; consider masking or pseudonymization if raw IPs are unnecessary for investigation.

## 15. Protecting logs after they are written

Logs can contain operational metadata and personal information. Protect logging across writing, transit, storage, and access:

- Restrict log read permissions by role and job need.
- Record and monitor log access activity.
- Encrypt logs in transit to centralized systems and at rest as required by policy.
- Protect integrity and detect unauthorized modification or deletion.
- Bound event sizes and write rates to prevent log flooding from filling disks.
- Configure alerts when the logging pipeline stalls or queues fill up.
- Define retention according to purpose, data classification, and legal obligations.
- Do not retain logs longer than approved periods; likewise, do not delete early while retention obligations apply.
- Protect copies, backups, exports, and temporary files under the same policy.
- When sending logs to third parties, review contracts, storage locations, and access controls.

Do not apply a single retention policy to all logs. Operational logs, security audit logs, and traces may require different retention windows.

## 16. Logging must not degrade request processing

Logging incurs CPU, I/O, and memory overhead. A single request can resolve hundreds of fields; logging every field or every `DataLoader` item can generate massive log volume.

Guidelines:

- Emit one event at request start and completion when needed, instead of logging every resolver.
- Use metrics/traces for latency and structured statistics.
- Bound lengths of client-controlled fields.
- Do not serialize entire variables/responses just to measure byte size.
- Consider sampling for high-volume success logs.
- Always retain mandatory security events per policy.
- Use bounded async appenders/queues and monitor dropped events.
- Avoid synchronous logging to remote sinks on request-handling threads.
- Have a policy for logging backend outages: operational logs should not fail normal requests; mandatory audits need durable mechanisms and a fail-open/fail-closed decision based on business requirements.

Sampling applies only to log types reducible by policy. Never arbitrarily sample mandatory security or audit events.

## 17. Testing safe logging

A good test must prove sensitive data does not appear in logs. Simply asserting that the interceptor was called is insufficient.

Cases to test:

1. Variables containing `password`, `accessToken`, `email`, or payment tokens do not appear in logs.
2. `Authorization` and `Cookie` headers do not appear.
3. Extensions are not automatically serialized.
4. Error messages containing raw inputs are not logged verbatim.
5. Unknown operation names are mapped to the `other` label.
6. Request IDs containing CR/LF are normalized and length-bounded.
7. Response data does not appear in logs.
8. Completed requests include duration and error count.
9. Transport failures include exception type without sensitive messages.
10. Trace IDs correlate properly without appearing in metric labels.
11. GET/access logs do not record query strings or sensitive variables.
12. WebSocket/RSocket logs do not record auth payloads or subscription event data.

Example sanitizer test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SafeLogValueTests {

    @Test
    void removesLineBreaksAndLimitsLength() {
        String result = SafeLogValue.sanitize(
                "SearchBooks\r\nforged-entry",
                16);

        assertThat(result).doesNotContain("\r", "\n");
        assertThat(result).hasSizeLessThanOrEqualTo(16);
    }
}
~~~

Interceptor tests should use a test appender or logger capture to inspect actual output. Create a request fixture with mock variables and headers containing secret markers, run it through the interceptor, then verify logs contain the request ID/outcome while containing none of the secret markers.

Do not use real secrets in tests; use synthetic placeholders such as `TEST_ONLY_SECRET_123`.

## 18. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Tokens appear in logs | Logging full headers or request bodies | Log only allowlisted metadata. |
| Passwords appear in traces | Variables or error messages exported as span events | Inspect Observation events and exception messages; strip sensitive data. |
| Forged multiline log entries | Client injects CR/LF into operation name or ID | Sanitize, bound lengths, and use a structured encoder. |
| Access logs contain queries/variables | GraphQL GET enabled or proxy logs query strings | Disable GET when variables are sensitive; configure proxy access logs. |
| Operation names explode metric cardinality | Using client-supplied operation names as metric tags | Use allowlist/enum labels or keep high-cardinality values in traces only. |
| Cannot trace requests across services | Correlation ID not propagated across transports | Use trace context and controlled request IDs. |
| Duplicate log entries | Interceptor, exception resolver, and transport all log the same failure | Assign a single responsible layer per event; correlate via request ID. |
| Disk fills up or log costs spike | Logging per field/event or large bodies | Apply controlled sampling, size bounds, and use metrics/traces. |
| MDC leaks across requests | `ThreadLocal` not cleared or context not propagated across async/reactive | Use context propagation and test under concurrency. |
| Missing logs when logging backend fails | Queue/sink failures are unmonitored | Add health signals, dropped-event metrics, and alerts. |
| Logs contain sensitive stack traces | Exception messages or suppressed exceptions contain inputs | Audit exceptions before logging; emit stack traces only to restricted sinks. |

## 19. Implementation checklist

1. Define separate goals for operational logs, security audits, and traces.
2. Define an allowlisted log schema and classify every field.
3. Never log raw GraphQL documents, variables, extensions, request bodies, or response data.
4. Never log `Authorization`, `Cookie`, API keys, passwords, tokens, or session IDs.
5. Use `WebGraphQlInterceptor` for HTTP/WebSocket and `RSocketQlInterceptor` for RSocket when needed.
6. Log request ID, allowlisted operation label, outcome, error count, and duration.
7. Sanitize all client-controlled values; enforce length bounds and CR/LF neutralization.
8. Use structured logging encoders; parameterized logging does not prevent log injection on its own.
9. Audit access logs, reverse proxies, APMs, debug logs, and GET query strings.
10. Review Observation events because error messages may be recorded into traces.
11. Never use high-cardinality values as metric labels.
12. Protect logs with access controls, encryption, integrity monitoring, and retention policies.
13. Bound log rates/sizes and monitor the logging pipeline.
14. Test with secret markers to prove sensitive data does not appear.
15. Document logging policies in operational runbooks and review them when schemas/transports change.

## 20. References

- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Logging and Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

Safe request logging in Spring for GraphQL starts with deciding what data is genuinely required for operations. Log structured, bounded, and traceable metadata; keep documents, variables, headers, cookies, response data, and error messages out of default logs. Combine transport-appropriate interceptors, controlled Observation, structured logging, log store protections, and secret-marker tests so you can investigate incidents while minimizing data leakage.
