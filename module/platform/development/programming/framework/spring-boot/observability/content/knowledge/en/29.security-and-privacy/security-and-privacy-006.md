# Masking Response Bodies

In the **Security and Privacy** chapter of the **SPRING_BOOT_OBSERVABILITY** module, response body masking is the technique of removing or replacing sensitive data in HTTP responses before the contents are written into logs, traces, or other telemetry. Responses can contain access tokens, emails, account numbers, addresses, personal data, payment details, or internal business results. If an application logs entire bodies for debugging, that data can be replicated to multiple observability systems with different access permissions and retention windows.

It is essential to identify where response bodies are captured. Spring Boot and Micrometer Observation do not record full bodies of every HTTP response into metrics or spans by default. Risks typically originate from custom logging filters/interceptors, HTTP client debug logging, gateway/proxy logs, exception handlers, or additional instrumentation. Masking must be placed directly before the point where data is recorded, while minimizing capture upfront.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain response body masking and the risks of logging raw bodies.
2. Identify response body capture points across Spring MVC, WebFlux, HTTP clients, and gateways.
3. Distinguish between masking, redaction, truncation, and omission.
4. Design an allowlist of data permitted to be logged.
5. Mask JSON fields structurally rather than via ad-hoc string replacement.
6. Handle streaming, binary, multipart, and large responses.
7. Understand the impact of response wrappers on buffering, memory, and response commitment.
8. Ensure exception/error responses also comply with the masking policy.
9. Prevent response bodies from entering trace attributes, baggage, and metric tags.
10. Test using canary values and establish a leakage incident response procedure.

## 2. What Can a Response Body Expose?

An HTTP response usually contains data sent to the client, but that does not mean it is safe to store in logs.

~~~json
{
  "customer": {
    "id": "C-9182",
    "email": "alice@example.com",
    "name": "Alice Nguyen"
  },
  "accessToken": "eyJhbGciOi...",
  "account": {
    "number": "001234567890",
    "balance": 1250000
  }
}
~~~

If this response is logged verbatim, logs can contain:
- Access/refresh tokens, session identifiers, and API keys.
- Emails, names, phone numbers, addresses, and personal identifiers.
- Account numbers, payment details, and financial data.
- Confidential business contents or internal data.
- Error details, stack traces, or downstream payloads.
- Data that can be combined with other fields to identify an individual.

Response bodies may be recorded in application logs, reverse proxies, API gateways, ingress, service meshes, APM agents, HTTP client wire logs, or test/debug tooling. Inspect the entire data path, not just controller code.

## 3. Masking, Redaction, Truncation, and Omission

| Technique | How It Works | When Appropriate |
| --- | --- | --- |
| Masking | Replaces part/all of a value with fixed characters or masks. | Preserving structure for debugging, e.g., email as `a***@example.com`. |
| Redaction | Removes the value and replaces it with a label like `[REDACTED]`. | Secrets or data prohibited from storage. |
| Truncation | Limits content length. | Reducing log volume after policy has been applied. |
| Omission | Does not capture or does not log the body. | Streaming, binary, sensitive endpoints, or when debugging is unnecessary. |
| Allowlisting | Logs only approved fields. | Diverse response schemas or sensitive data by default. |

Truncation is not masking: keeping the first 2 KB of a response can still preserve tokens or emails intact. Full-text regex replacement also cannot guarantee safety when JSON contains nested objects, arrays, escaped strings, or field aliases. For sensitive data, allowlisting and omission are usually safer choices.

## 4. Identifying Where Response Bodies Are Captured

Before writing masking code, locate every place capable of reading or logging response bodies:

- Spring MVC filters, `HandlerInterceptor`s, response advice, and exception handlers.
- WebFlux `WebFilter`s, `ExchangeFilterFunction`, and response decorators.
- `RestTemplate`/`RestClient` interceptors.
- `WebClient` filters and connector-level wire logging.
- Reverse proxies, API gateways, ingress, and service meshes.
- OpenTelemetry Java Agent extensions or APM agents.
- Logging appenders, structured logging processors, and log shippers.

Micrometer HTTP observations normally record method, URI, status, outcome, and duration. They do not need the response body to produce basic metrics. Avoid adding bodies to span attributes solely for debugging convenience.

~~~mermaid
flowchart TD
    Handler["Controller / downstream client"]
    Response["HTTP response body"]
    Capture["Optional capture point"]
    Policy["Response data classification"]
    Mask["Allowlist / structural masking"]
    Log["Safe structured log"]
    Trace["Trace attributes"]
    Store["Log / trace backend"]
    Handler --> Response --> Capture --> Policy --> Mask
    Mask --> Log --> Store
    Mask --> Trace --> Store
~~~

Unless there is a specific operational requirement, do not capture the body. When capture is necessary, emit only a safe representation after classification and masking.

## 5. Prefer Allowlists Over Logging Whole Responses

Response schemas can evolve across versions or gain new fields. If using a denylist, a newly added field may be logged inadvertently before the policy is updated. An allowlist selects only the fields genuinely needed.

Example safe log representation:

~~~json
{
  "event": "http.response.completed",
  "route": "/orders/{orderId}",
  "status": 200,
  "response": {
    "result": "accepted",
    "itemCount": 3
  }
}
~~~

Never log whole response objects using `toString()`, default JSON serialization, or generated `toString()`. Those approaches can pull sensitive fields into logs without the author noticing.

The policy should define which endpoints/routes are captured, which content types are handled, which fields are kept/masked/redacted, maximum sizes, which responses must be skipped, and which roles may read the logs.

## 6. Structural JSON Masking

If part of a JSON payload must be kept for investigation, parse the body into a JSON tree and process fields by name/path. Avoid full-text regex substitution.

| JSON Path | Handling |
| --- | --- |
| `$.accessToken` | Redact completely. |
| `$.refreshToken` | Redact completely. |
| `$.customer.email` | Mask per email policy. |
| `$.customer.name` | Omit or mask. |
| `$.account.number` | Keep only suffix if policy permits. |
| `$.account.balance` | Omit or bucket, depending on purpose. |
| `$.result` | Allowlist if a fixed enum. |
| `$.itemCount` | Allowlist if non-sensitive. |

Illustrative Java example using Jackson:

~~~java
@Component
class ResponseBodySanitizer {

    private final ObjectMapper objectMapper;

    ResponseBodySanitizer(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    JsonNode sanitize(byte[] body) throws IOException {
        JsonNode root = objectMapper.readTree(body);

        if (root instanceof ObjectNode object) {
            object.remove("accessToken");
            object.remove("refreshToken");

            JsonNode customerNode = object.get("customer");
            if (customerNode instanceof ObjectNode customer) {
                customer.put("email", "[REDACTED]");
                customer.remove("name");
            }

            JsonNode accountNode = object.get("account");
            if (accountNode instanceof ObjectNode account) {
                account.put("number", "[REDACTED]");
                account.remove("balance");
            }
        }
        return root;
    }
}
~~~

This is a minimal example for a known schema. Real applications must handle nested arrays, multiple objects with the same schema, JSON primitives, malformed payloads, and content types. On parse failure, the safe option is to skip logging the body or log non-sensitive metadata; never fall back to logging the raw body.

A token field can appear at multiple nesting levels or inside arrays. Policies must handle recursive paths and aliases such as `access_token`, `refresh_token`, `authorization`, `cardNumber`, and equivalent names. Better yet, use a dedicated allowlisted logging schema/DTO instead of reusing the full response DTO.

## 7. Response Masking in Spring MVC

In the Servlet stack, the response body is usually written by an `HttpMessageConverter` after the controller returns. If capturing the body for logging is required, `ContentCachingResponseWrapper` can be used, though this wrapper buffers the response contents and requires copying the body back to the actual response after reading.

~~~java
@Component
class SafeResponseLoggingFilter extends OncePerRequestFilter {

    private final ResponseBodySanitizer sanitizer;

    SafeResponseLoggingFilter(ResponseBodySanitizer sanitizer) {
        this.sanitizer = sanitizer;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        ContentCachingResponseWrapper wrapped =
                new ContentCachingResponseWrapper(response);
        try {
            filterChain.doFilter(request, wrapped);
            byte[] body = wrapped.getContentAsByteArray();

            if (shouldCapture(request, wrapped, body.length)) {
                JsonNode safe = sanitizer.sanitize(body);
                logSafeResponse(request, wrapped.getStatus(), safe);
            }
        } finally {
            wrapped.copyBodyToResponse();
        }
    }

    private boolean shouldCapture(
            HttpServletRequest request,
            ContentCachingResponseWrapper response,
            int size) {
        return size <= 16384
                && response.getContentType() != null
                && response.getContentType().contains("application/json");
    }

    private void logSafeResponse(
            HttpServletRequest request, int status, JsonNode safeBody) {
        // Log metadata and the sanitized safeBody.
    }
}
~~~

This example illustrates wrapper lifecycle management, not a complete production filter. You must restrict routes/content types/size, skip streaming, and handle exception paths. Never log the body if the sanitizer throws an error. `copyBodyToResponse()` must be called at the right point in the lifecycle so the client still receives the response body.

### Limitations of ContentCachingResponseWrapper

- Content is buffered in memory, increasing memory pressure.
- Large responses can cause high allocations or `OutOfMemoryError`.
- Streaming/SSE can lose streaming benefits or behave improperly.
- File downloads/binary payloads should not be parsed as JSON.
- Already-committed responses or async dispatches require careful lifecycle handling.
- Filter order affects what content the wrapper sees.
- Forgetting to copy the body back to the response can leave the client with an empty body.

Do not use a response caching wrapper for every production request without measuring memory and latency. If only certain endpoints need debugging, use a route allowlist and byte cap.

## 8. WebFlux and Reactive Responses

WebFlux uses reactive streams and `DataBuffer`; response bodies can be emitted in multiple chunks and are not necessarily available as a complete byte array. Buffers are reference-counted and must be released properly. Joining all `DataBuffer`s to mask can break streaming, increase memory usage, and cause leaks if mismanaged.

Principles:
- Never buffer SSE, streaming JSON, video, files, or large responses just to log.
- Decorate responses only when genuinely required and the content type is allowlisted.
- If transforming `DataBuffer`s, preserve ownership/release semantics strictly.
- Never subscribe separately to a publisher just to log; doing so can consume the body twice or duplicate side effects.
- When parsing fails or buffers exceed limits, abandon body capture.

With `WebClient`, the response body can typically be consumed only once. If a filter reads the body to log, it must rebuild the response body so downstream callers can still read it. This is complex and connector-dependent; prefer logging metadata/status/route and leaving the body untouched.

## 9. Streaming, Binary, and Multipart

Response types that should not be captured by default:
- `text/event-stream` (Server-Sent Events).
- `application/octet-stream`.
- PDFs, images, audio, video, and archives.
- Multipart responses.
- Streaming JSON/NDJSON.
- Content with unknown or very large size.

For these responses, log metadata such as content type, status, content length if available, route template, and duration. Never log the first few bytes as a form of masking, since tokens or PII can sit right at the start of the body.

If business requirements mandate inspecting part of the content, design dedicated metadata with a clear schema and size bounds; do not turn the HTTP body into a log payload.

## 10. Error Responses and Exception Handlers

Error responses often contain even more sensitive data than success responses: validation inputs, stack traces, database errors, internal hostnames, or downstream error bodies. The masking policy must apply to both success and failure paths.

Places to inspect:
- `@ExceptionHandler` and `@ControllerAdvice`.
- Problem Details (`ProblemDetail`) and custom error DTOs.
- Servlet error dispatch and container error pages.
- WebFlux exception handlers.
- HTTP client error bodies when downstream returns 4xx/5xx.
- Whether retry/dead-letter logs serialize response payloads.

Never return stack traces, SQL messages, or raw downstream bodies to clients merely because logs were masked. Response sanitization and client-facing error handling are two separate policies. Return only intentionally designed public error codes/messages; log internally using error categories and correlation IDs.

## 11. Never Put Response Bodies Into Spans, Baggage, or Metric Tags

Distributed traces are shared across multiple services and backends. Response bodies are not default span attributes needed for HTTP instrumentation. Never add raw bodies to span attributes, span events, baggage, metric tags, MDC, or unsanitized structured log fields.

If you need to trace a specific error, use HTTP method, route template, status, outcome, stable error type, safely managed correlation/request IDs, and link to masked log records per access policy.

Metric tags must be low-cardinality. Response fields like order ID, user email, token, or error details are both sensitive and capable of creating millions of series.

## 12. Size Limits and Performance

Body capture incurs CPU, allocation, memory, and latency costs. Define upfront:
- Capture only allowlisted content types.
- Limit maximum bytes read and processed.
- Limit JSON nesting depth and array element counts if the parser supports it.
- Do not compress/decompress payloads unnecessarily for logging.
- Avoid parsing the body multiple times across multiple filters.
- Use sampling for debug capture, while remembering sampling never replaces masking.
- When limits are exceeded, record `body_captured=false` and safe metadata.

Example metadata when skipping the body:

~~~json
{
  "event": "http.response.completed",
  "route": "/reports/{reportId}",
  "status": 200,
  "contentType": "application/octet-stream",
  "bodyCaptured": false,
  "bodyCaptureReason": "unsupported-content-type"
}
~~~

Ensure `bodyCaptureReason` is a fixed set of values, not an arbitrary exception message.

## 13. Testing Response Masking with Canary Values

Create synthetic values strictly for tests to make leaks easy to spot:

~~~text
CANARY_ACCESS_TOKEN=canary-token-DO-NOT-LOG
CANARY_EMAIL=canary-user@example.invalid
CANARY_ACCOUNT=9999000011112222
~~~

Tests should verify:
1. Responses sent to clients still match the API contract.
2. Log representations contain no canary secrets/PII.
3. Allowlisted fields remain present when policy expects them.
4. Nested objects and arrays are handled.
5. Malformed JSON leads to omitting the body, not raw logging.
6. Large responses exceeding limits safely skip capture.
7. Binary/streaming/multipart payloads are not buffered for parsing.
8. Exception/error responses are also masked.
9. No canary values appear in span attributes, baggage, or MDC.
10. `copyBodyToResponse()` is invoked even when the sanitizer fails.

Example unit test for the sanitizer:

~~~java
@Test
void removesSecretsFromResponseJson() throws Exception {
    byte[] body = """
            {
              "accessToken": "canary-token-DO-NOT-LOG",
              "customer": {
                "email": "canary-user@example.invalid"
              }
            }
            """.getBytes(StandardCharsets.UTF_8);

    JsonNode safe = sanitizer.sanitize(body);
    String output = objectMapper.writeValueAsString(safe);

    assertThat(output).doesNotContain("canary-token-DO-NOT-LOG");
    assertThat(output).doesNotContain("canary-user@example.invalid");
}
~~~

This is only a sanitizer test; integration tests at the filter/client logging boundary are needed to verify no other component logs the raw body before the sanitizer runs.

## 14. Retention, Access, and Incident Response

Application-level masking is one defense layer. Exported logs/traces also need role- and purpose-based RBAC, encryption in transit/at rest, appropriate retention, query/export auditing, download/sharing restrictions, and procedures to delete/contain data when leakage is detected.

If sensitive response bodies are found in logs:
1. Identify the affected fields/values, service, timeframe, and receiving sinks.
2. Stop continued capture via controlled config/code changes.
3. Restrict access permissions and pause export/forwarding if appropriate.
4. Determine retention/deletion capabilities of the log/trace backends.
5. Execute the incident process and evaluate notification obligations per policy.
6. Rotate tokens/credentials if secrets were exposed.
7. Test with canary values after the fix and review other services using the same logging pattern.

Do not assume deleting logs in one backend means data has disappeared from replicas, archives, indexes, backups, or downstream SIEMs.

## 15. Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Client receives empty response body | Wrapper did not copy body back to actual response. | Check `copyBodyToResponse()` inside `finally`. |
| Large responses spike memory | `ContentCachingResponseWrapper` buffers too much. | Limit capture size/route/content type or stop capturing. |
| JSON log still contains token | Field alias/nested path not handled by policy. | Use a structural sanitizer and test nested arrays. |
| Masking applies only to 200 responses | Error handlers/container dispatch take a different path. | Check exception advice and error dispatches. |
| WebFlux body consumed twice | Filter subscribes/consumes publisher separately for logging. | Decorate/rebuild lifecycle properly or skip body capture. |
| SSE/streaming slows down or stalls | Entire response is buffered. | Skip capture for streaming content types. |
| SQL/downstream error appears in body log | Exception handler serializes raw exception/downstream payload. | Use safe error DTOs and sanitize at the boundary. |
| Span contains response body | Custom instrumentation or agent captures payload. | Inspect span processors, agent config, and custom attributes. |
| Body truncated yet secret still leaks | Truncation used instead of masking. | Mask before truncating or omit body. |
| Sanitizer tests pass but logs still leak | Another component logs raw body before sanitizer. | Locate filters, wire logs, gateways, and agent capture. |

## 16. Runbook: Response Body Written to Telemetry

1. Identify the affected service, route, response content type, and log/trace sink.
2. Locate the capture source: filter, interceptor, HTTP client, gateway, agent, or wire logger.
3. Determine data classification and the canary/secret values recorded.
4. Disable body capture or narrow the allowlist at the source following change control.
5. Apply structural masking before serializing log/trace events.
6. Skip capturing streaming, binary, multipart, and oversized bodies.
7. Check error responses and exception handling paths.
8. Audit span attributes, baggage, MDC, and metric tags.
9. Test using canary values at application and gateway boundaries.
10. Identify affected log/trace indexes, archives, backups, and access permissions.
11. Rotate credentials if access tokens/API keys were exposed.
12. Document incident findings and add regression tests/policies.

## 17. Self-Check Exercises

### Exercise 1 — Truncation

A filter logs only the first 1 KB of a response. Can this be considered masking?

**Answer:** No. Tokens, emails, or account data can reside in the beginning. Truncation only limits length; you must mask/redact per policy or omit the body.

### Exercise 2 — Allowlist or Denylist?

A response schema changes frequently and may add sensitive fields. Which strategy should be chosen?

**Answer:** Allowlist the fields permitted to be logged. New fields are excluded from logs by default, reducing the risk of accidental data recording.

### Exercise 3 — Streaming Responses

Should `ContentCachingResponseWrapper` be used to parse and mask an entire SSE response?

**Answer:** No. SSE is streaming; buffering the whole response can break streaming, increase memory, and add latency. Log safe metadata instead of the body.

### Exercise 4 — WebFlux

A `WebClient` filter reads the body to log, and afterward the service receives an empty body. Why?

**Answer:** Reactive response bodies can typically be consumed only once. The filter consumed the publisher without rebuilding the body for downstream consumers.

### Exercise 5 — Error Responses

`ControllerAdvice` constructs a `ProblemDetail` from an exception and logs that object. What must be checked?

**Answer:** Ensure `properties`/`detail` do not contain raw exception messages, SQL, hosts, or downstream payloads; use safe error codes and apply the masking policy to the error path.

### Exercise 6 — Canary Test

Sanitizer unit tests no longer contain the canary token, yet production logs still have the token. What are possible causes?

**Answer:** Another filter, gateway, HTTP client wire logger, or agent records the raw body before or after the sanitizer. Inspect all capture points and the export pipeline.

## 18. Implementation Checklist

- [ ] Listed all response body capture points.
- [ ] Do not capture bodies without a clear operational need.
- [ ] Allowlist defined for routes and content types permitted for processing.
- [ ] Field/schema allowlist used for safe log representation.
- [ ] JSON masked structurally, including nested objects and arrays.
- [ ] Secrets, tokens, PII, payment data, and account identifiers redacted/omitted.
- [ ] Malformed/unsupported payloads result in omission, never raw body fallback.
- [ ] Streaming, binary, multipart, and large responses not arbitrarily buffered.
- [ ] Response wrappers always preserve body and proper lifecycle.
- [ ] Error responses/exception handlers enforce the same privacy policy.
- [ ] Response bodies never placed into span attributes, baggage, or metric tags.
- [ ] Capture size, parser depth, CPU, and memory overhead bounded.
- [ ] Canary tests verify zero leakage at log/trace boundaries.
- [ ] Logs/traces have appropriate RBAC, encryption, retention, and auditing.
- [ ] Incident runbook and credential rotation exist for secret exposure.
- [ ] Gateways, agents, and downstream telemetry sinks reviewed.

**Takeaway:** Response body masking starts with deciding whether capture is needed at all. If needed, keep only allowlisted fields, mask JSON structurally, and skip streaming/binary or unsupported payloads. Place sanitization before every log/trace export, preserve response lifecycles, test with canary values, and govern access/retention at the backend. Basic metrics and traces rarely need stored response bodies to deliver useful observability.
