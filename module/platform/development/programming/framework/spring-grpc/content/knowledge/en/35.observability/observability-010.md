# Redacting Payloads in Logs

Logs help investigate failures and understand service behavior, but gRPC payloads often contain personal data, account details, authentication secrets, or business content. Writing raw requests/responses into logs can turn the observability system into a copy of sensitive data—retained longer and accessible to more people than the business system itself. Therefore, services must explicitly decide which fields may be logged, which fields must be masked or removed, and at which boundary redaction takes place.

**Redacting payloads in logs** means minimizing logged data and removing or transforming sensitive fields before they reach the logging backend. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on not logging raw Protobuf messages, classifying fields by schema, using allowlists for log projections, handling metadata/trailers, and testing to prove sensitive data does not leak.

## 1. Principle: Do Not Log Raw Payloads by Default

A Protobuf request can contain many types of data:

- Identifying information: name, email, phone number, address, date of birth.
- Financial information: account numbers, card numbers, amounts, payment details.
- Authentication secrets: access tokens, refresh tokens, API keys, passwords, cookies.
- Private content: notes, chat contents, attachments, medical records, or customer profiles.
- Business identifiers linkable to individuals: customer ID, order ID, tenant ID.

Avoid calling `request.toString()`, concatenating the request into a log message, or serializing the entire message with `JsonFormat.printer()` for logging. Protobuf `toString()` and JSON printers can output every populated field, including sensitive ones. Whether the payload is represented in text or binary does not change its sensitivity.

The safe default is logging operational metadata: method, request ID, status, duration, item counts, sizes measured at a defined boundary, and processing outcome. Only add payload content when there is a specific purpose, approved under data policy, and passed through a sanitizer.

## 2. Classify Fields Before Writing the Logger

You must know what the schema contains before deciding what to log. Fields can be classified into four groups:

| Group | Examples | Handling in Operational Logs |
| --- | --- | --- |
| Public/operational | RPC method, operation type enum, item count | May be logged if needed for operations. |
| Internal identifier | customer ID, order ID, tenant ID | Exclude by default or replace with controlled pseudonymized tokens. |
| Personal/confidential | email, phone, address, free-text note | Partially mask only if truly necessary; prefer removal. |
| Secret/authentication | password, token, API key, cookie, private key | Never log; remove completely. |

Classification must apply to both requests and responses, nested fields, repeated fields, maps, `oneof`, `Any`, `bytes`, and metadata. A newly added field in a Protobuf schema must not automatically become loggable data.

## 3. Allowlist Is Better Than Denylist

An allowlist specifies which fields are permitted to appear in logs. A denylist attempts to list fields to redact. As schemas evolve over time, a denylist easily misses new sensitive fields; an allowlist excludes unreviewed fields by default.

For example:

~~~text
Log projection for CreateOrder:
  grpc_method       allow
  request_id        allow if validated
  item_count        allow
  delivery_mode     allow if enum contains no sensitive data
  customer_email    exclude
  customer_phone    exclude
  payment_token     exclude
  delivery_address  exclude
  free_text_note    exclude
~~~

Create a dedicated log projection from the request, keeping only attributes with an operational purpose. Do not pass the entire Protobuf message to a logger and hope a generic regex strips out all secrets.

## 4. Masking, Removal, and Pseudonymization Are Different Techniques

- **Removal (redact/remove):** the field does not appear in logs. This is the preferred choice for secrets and unnecessary data.
- **Masking (partial mask):** keeps only part of a value, such as displaying the last two digits of a phone number when a use case genuinely needs partial recognition.
- **Pseudonymization:** replaces an identifier with a stable token to correlate events without logging the original identifier.
- **Aggregation:** logs counts, categories, or ranges instead of specific values.

Masking does not render data harmless; the remaining portion can still identify a user when combined with other data. Plain hashing also does not guarantee anonymity: IDs from small domains can be brute-forced via dictionaries. If a stable token is needed to correlate logs, use HMAC with a separately managed secret key, restricted access, and rotation; do not use HMAC output as a metric label if cardinality is unbounded.

## 5. Build a Log Projection Instead of Logging Protobuf Messages

The following example illustrates a log projection that keeps only item count and a shipping enum evaluated as safe. Getter names illustrate a specific generated request; replace them with actual fields from your application schema:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderRequestLogger {

    private static final Logger log =
            LoggerFactory.getLogger(OrderRequestLogger.class);

    public void logAccepted(
            String requestId,
            CreateOrderRequest request) {

        String deliveryMode =
                request.getDeliveryMode().name();
        int itemCount = request.getItemsCount();

        // Log only fields approved in the log projection.
        log.info(
                "order.request.accepted request_id={} grpc_method={} delivery_mode={} item_count={}",
                requestId,
                "orders.OrderService/CreateOrder",
                deliveryMode,
                itemCount);
    }
}
~~~

The example does not pass the request directly to the logger and does not serialize the whole message. `deliveryMode` should only be logged if the enum contains no free-form values or sensitive information. If an enum reflects customer tier or confidential segments, omit that field or map it to a broader category.

A log projection should be a small data type with explicit field names, reviewed alongside schema changes. When Protobuf adds a field, the projection does not automatically add it to logs.

## 6. Redaction Based on Protobuf Schema

When a shared sanitizer is needed across many messages, build a descriptor-driven policy rather than relying on `toString()` or regex string searches. Protobuf descriptors provide field names, types, field numbers, nested messages, and options; the application can map field paths to data policies.

Example policy:

~~~text
CreateOrderRequest.customer.email       -> REMOVE
CreateOrderRequest.customer.phone       -> MASK
CreateOrderRequest.payment.token         -> REMOVE
CreateOrderRequest.items[*].sku          -> ALLOW if SKU is non-sensitive
CreateOrderRequest.items[*].quantity     -> ALLOW
CreateOrderRequest.delivery.address      -> REMOVE
CreateOrderRequest.note                  -> REMOVE
~~~

A schema-aware sanitizer must handle:

- Nested messages: apply policy recursively by full field path.
- Repeated/map fields: apply policy to each element and cap the number of inspected elements.
- `oneof`: only the currently set field has a value; still apply the corresponding policy.
- `Any`: unpack only types in a known allowlist; drop payloads for unknown types.
- `bytes`: do not log raw bytes or base64 payloads without classification.
- Unknown/new fields: exclude by default in log projections.

Do not build a complex generic sanitizer if the application only has a few methods to log. Explicit per-method log projections are usually easier to review and less risky. For large schemas, use a descriptor-driven policy with test coverage for every field path.

## 7. Do Not Log Payloads in Generic Interceptors

`ServerInterceptor` and `ClientInterceptor` are convenient places to log method, status, request ID, and duration. However, generic interceptors should not log entire messages in `onMessage` or `sendMessage`: they may run for every service, every schema, and every data type.

A server interceptor that logs only operational details:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SafeGrpcAccessLogInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGrpcAccessLogInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        long started = System.nanoTime();
        AtomicBoolean terminalLogged = new AtomicBoolean();

        ServerCall<ReqT, RespT> monitored =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (terminalLogged.compareAndSet(false, true)) {
                            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                                    System.nanoTime() - started);
                            log.info(
                                    "grpc.server.completed grpc_method={} grpc_status={} duration_ms={}",
                                    method,
                                    status.getCode().name(),
                                    durationMs);
                        }
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitored, headers);

        return new io.grpc.ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                if (terminalLogged.compareAndSet(false, true)) {
                    log.info(
                            "grpc.server.cancelled grpc_method={}",
                            method);
                }
                super.onCancel();
            }
        };
    }
}
~~~

This interceptor does not read request messages and does not log arbitrary metadata. If the application already has an access-log interceptor, add safe fields to that mechanism rather than adding multiple loggers recording the same RPC twice. When registering with a Spring gRPC starter, use the server lifecycle managed by the starter.

## 8. Metadata and Trailers Can Also Contain Secrets

Protobuf payloads are not the only thing requiring redaction. Request metadata may contain:

- `authorization`, bearer tokens, or API keys.
- Cookies/session identifiers.
- Credentials injected by a service mesh or proxy.
- Custom headers carrying personal data or tenant identifiers.

Response trailers may contain error descriptions, debug details, or application-added data. Do not log all `Metadata.keys()` with their values; log only an allowlist of approved operational headers. For secrets, remove them completely rather than masking a few characters.

Example rules:

~~~text
Allow:
  x-request-id       if validated
  grpc-timeout       if needed for investigation and normalized

Never log:
  authorization
  cookie
  x-api-key
  session-token
  arbitrary custom metadata
~~~

Do not log raw `grpc-timeout` if the value could be confused between remaining deadline and initial timeout; if needed, log a parsed/normalized duration. Avoid logging raw error descriptions or exception messages because they may contain caller inputs.

## 9. Redacting Payloads in Streaming RPCs

With client-streaming, server-streaming, and bidirectional streaming, each stream can carry many messages. Logging every message drives up costs, produces huge volumes of sensitive data, and can bottleneck the logging pipeline.

Prefer to:

- Log one event when the stream starts and one when it ends.
- Record method, status, duration, and message count via metrics.
- If content debugging is necessary, use bounded sampling and redacted log projections.
- Cap the number of sampled messages per stream and total logged bytes.
- Never log unclassified messages, not even just the first message.
- Handle cancellations/exceptions so cleanup is never skipped and payloads are not logged on error paths.

For streams carrying sensitive data, never turn on payload logging via a global feature flag. If a special debug session is required, scope it to method, time window, caller, access permissions, and retention; keep it off by default and audit every activation.

## 10. Exceptions, Debug Details, and Audit Logs

Exception messages are not automatically safe. An exception may contain SQL fragments, request values, file paths, tokens, or downstream data. Do not log `Throwable.getMessage()` unchecked and never return stack traces in gRPC status descriptions.

Operational logs should prefer:

- Normalized error categories or exception classes.
- gRPC status code.
- Method, request ID, and trace ID if present.
- Approved dependency name and operation name.
- An internal error code containing no payload.

Audit logs serve a different purpose from application logs. If business requirements demand recording who performed which action, emit audit events with separate schemas, access controls, integrity, retention, and redaction. Never use raw gRPC payload logs as an audit trail.

## 11. Retention, Access Control, and Log Storage

Application-level redaction is an important safeguard, but it does not replace controls in the logging pipeline:

- Restrict log read permissions by role and environment.
- Separate production logs from dev/test environments.
- Set retention according to purpose and data policy.
- Encrypt logs in transit and at rest.
- Restrict exporting logs to third parties; evaluate data residency and data processing agreements.
- Audit access to or exports of sensitive logs.
- Do not accidentally write raw payloads into dead-letter logs, retry diagnostics, or crash dumps.

If redaction happens too late in a dashboard, raw payloads may still persist in agent buffers, collectors, archives, or exports. Perform data minimization before log events leave the process.

## 12. Testing Redaction

Tests must prove that sensitive values do not appear in any log event across both success and error paths:

1. Build a request containing email, phone, access token, address, and free-text note with easily searchable markers.
2. Invoke a successful RPC; check that the log projection contains only allowlisted fields.
3. Force validation or a downstream call to fail; verify exception/status descriptions do not expose markers.
4. Send `authorization`, `cookie`, and `x-api-key` metadata; verify the logger does not record their values.
5. Send nested/repeated/map/`oneof` fields with sensitive data; verify the sanitizer applies policies recursively.
6. Send `Any` with a type outside the allowlist; verify the payload is dropped.
7. Invoke a multi-message streaming RPC; verify logs contain no raw messages and event count is bounded.
8. Inspect the actual log encoder output, not just MDC objects or log arguments prior to serialization.
9. Modify the Protobuf schema with a new field; verify the new field does not automatically appear in the log projection.
10. Verify appenders, async logging queues, collector test sinks, and error paths if those components are within deployment scope.

For example, tests can use an in-memory appender to capture log events, then assert that secret markers do not appear in formatted messages or structured fields. Use a unique marker per data type to pinpoint exactly which field leaked.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Tokens appear in debug logs | Logging requests or metadata directly. | Never log raw messages/headers; use allowlist projections. |
| New field appears in logs after proto update | Serializing the entire Protobuf message. | Use explicit projections or a default-deny schema policy. |
| Regex masks email but misses other data | Redacting by string patterns instead of field semantics. | Classify by schema and nested field path. |
| Secrets appear in exceptions | Logging raw exception messages/descriptions. | Normalize error categories; redact exception data. |
| Streaming produces excessive logs | Logging every message at INFO level. | Use message metrics and lifecycle logs; bounded sampling. |
| Data still leaks in the collector | Redaction only happens at the final dashboard/collector. | Redact before events leave the process and control the pipeline. |
| Masked identifiers remain identifiable | Keeping too many characters or using easily guessed hashes. | Remove or use HMAC/tokenization with key management. |
| Redaction tests pass while JSON logs leak fields | Only checking log templates/MDC, not encoder output. | Test formatted events and actual structured JSON. |

## 14. Hands-On Exercises

1. Build a field classification table for a Protobuf request containing nested messages, repeated fields, and `Any`.
2. Create an allowlist log projection for a unary RPC; never pass the raw request to the logger.
3. Write a `ServerInterceptor` that logs only full method, status, duration, and validated request ID.
4. Configure a metadata allowlist; prove `authorization`/`cookie`/`API key` never appear in logs.
5. Implement a descriptor-based sanitizer or explicit projection for nested/repeated fields.
6. Test streaming RPCs to ensure per-message payloads are not logged and sensitive markers never leak.
7. Audit exceptions, trailers, async appenders, and collector sinks for data leak paths.
8. Define separate retention/access policies for application logs and audit logs.

After this lesson, you should know how to minimize logged data with allowlists, mask or remove sensitive fields by schema, keep interceptors at safe operational boundaries, and test actual log output. When payloads, metadata, and exceptions are all governed by the same data policy, a Spring gRPC system retains enough method/status/correlation fields for investigation without turning logs into a replica of business data.
