# Logging Full Payloads and Credentials

A common security mistake when developing Spring gRPC services is writing entire requests, responses, or full metadata into logs for debugging convenience. Doing so can push access tokens, API keys, personal data, order details, and business content into log storage systems. Log records are routinely forwarded to multiple destinations such as centralized log servers, search platforms, alerting tools, APM systems, and backups. Consequently, a single log line meant only for debugging can become a copy of sensitive data that outlives the original data.

Logs should help operators answer questions such as which RPC was called, whether it succeeded or failed, how long it took, and where an error occurred. Most operational questions do not require storing full request contents or credentials. With Spring gRPC, design logging around data minimization: log only fields verified to be safe, for an explicit purpose, with an appropriate retention period.

## 1. What data can leak through logs

In a gRPC RPC, sensitive data can appear across multiple layers:

| Location | Examples | Risk when logged verbatim |
|---|---|---|
| Protocol Buffers request/response | Email, phone number, address, chat content, payment info, customer profile | Exposes personal data or business secrets; records can hold many nested fields |
| gRPC Metadata | `authorization`, API key, cookie, session ID, tenant ID, identity info | Credentials can be copied and used to impersonate clients |
| Status and trailers | Error descriptions, refresh tokens, diagnostic data, values returned by downstreams | Exposes internal data or sensitive information attached to errors |
| Exceptions | Messages, causes, stack traces containing URLs, queries, inputs, or downstream responses | Leaks data via error messages even when payloads are not logged directly |
| Traces and metric labels | Span attributes, events, baggage, tags by user/email/token | Data is replicated into observability platforms and may be indexed |
| Network or framework debug logs | HTTP/2 frames, headers, wire payloads, request dumps | May record binary payloads and credentials before the application can mask them |

Credentials are not just passwords. Treat access tokens, refresh tokens, API keys, session cookies, OTP codes, private keys, signing secrets, connection strings, and signed URLs as secret data. Identifiers such as user ID, tenant ID, or JWT subject may also qualify as personal or sensitive data under system policy.

### 1.1. Protocol Buffers payloads are not safe by default

Java classes generated from `.proto` provide `toString()` to aid debugging. Calling `request.toString()` or passing the object directly to a logger prints the message's fields, including nested fields. A future schema change may add a sensitive field, causing logs to start collecting it without the logger author realizing.

Unsafe example:

```java
// Do not do this: message may contain personal data or secrets.
log.debug("CreatePayment request: {}", request);

// Do not do this: response may contain tokens or customer data.
log.info("RPC response: {}", response);
```

Lowering the log level from `INFO` to `DEBUG` does not make the data any less sensitive. If the logger is enabled in production to investigate an incident, full payloads can still be persisted into active log sinks.

### 1.2. Metadata and trailers are also untrusted inputs

gRPC Java passes metadata via `io.grpc.Metadata`. Common keys include `authorization`, `cookie`, `x-api-key`, or internal system-defined keys. Binary metadata keys carry the `-bin` suffix; their values may contain binary data encoded in transit. Dumping all metadata is unsafe simply because values are not displayed as plain text.

Never log `headers`, `trailers`, entire `Metadata` objects, or `Authorization` values. Do not assume only server-created metadata is trusted: metadata arriving from clients and downstream systems can contain externally controlled data. `Status.getDescription()` and trailers can also carry information added by another layer; when logging errors, prefer the status code and standardized internal error codes.

TLS protects data on the wire. TLS does not stop the application, interceptors, loggers, or APMs from writing data once messages are decoded inside the process. Therefore, enabling TLS is never a reason to log full requests or metadata.

## 2. Why logging full payloads and credentials is dangerous

**Credentials can be replayed.** If an access token or API key appears in logs, anyone with log read access can use that credential to call services while the token remains valid. Refresh tokens, session cookies, or long-lived secrets pose an even greater risk.

**Log access scope is often broad.** Operations, development, support teams, and observability platform vendors may have differing access permissions. Someone who needs to inspect RPC failures is not necessarily authorized to view customer profiles or credentials.

**Logs exist in many copies.** Logs can be forwarded, indexed, exported, stored in object storage, snapshotted, or backed up. Deleting a line in a search UI does not guarantee every copy is gone.

**Sensitive data spreads across systems.** Once a payload is logged, attached to a trace, or sent to an error-tracking tool, purging it becomes much harder. Tags containing emails or tokens may also serve as grouping labels, causing high cardinality and exposing data through query interfaces.

**Logs can be forged or noisy.** Client-supplied metadata values can contain very long strings, newline characters, or content crafted to corrupt logs. Logged directly, attackers can perform log injection, inflate storage costs, or hamper investigations.

## 3. Designing safe RPC logging

### 3.1. Use an allowlist instead of logging everything and trying to mask later

Predefine which fields are permitted in logs. An operational RPC log entry typically only needs:

- The gRPC method name, e.g. `package.Service/Method`.
- Normalized outcome, such as `OK`, `INVALID_ARGUMENT`, `UNAUTHENTICATED`, or `INTERNAL`.
- Processing duration and, if reliable instrumentation exists, aggregate sizes or counts.
- A correlation ID or trace ID validated for format and approved by policy.
- Internal error codes containing no input data or secrets.

Never log payloads, credentials, full headers/trailers, raw JWTs, private keys, cookies, session IDs, or unvetted exception contents. If business context is needed for investigation, pick a pseudonymous reference code or an approved aggregate value; never arbitrarily log emails, phone numbers, or IDs linkable back to a person.

Allowlists are safer than denylists. Denylists can miss new fields, differently cased metadata keys, or sensitive fields nested inside messages. With an allowlist, new fields are excluded from logs by default until reviewed.

### 3.2. Log metadata selectively

If a correlation ID is needed, read a single explicitly defined metadata key instead of serializing the entire `Metadata`. Validate length and character set before logging, since clients can supply this value themselves. Even better, the server can generate an internal correlation ID and return it to the client via response metadata per system convention.

For example, extract only an ASCII `x-request-id`:

```java
private static final Metadata.Key<String> REQUEST_ID_KEY =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

private static String safeRequestId(String candidate) {
    if (candidate == null || !candidate.matches("[A-Za-z0-9._-]{1,64}")) {
        return "-";
    }
    return candidate;
}
```

Never add `authorization`, `cookie`, `x-api-key`, or `*-bin` keys to the log list. If a custom key looks harmless, verify its owner, meaning, and data classification before permitting logging.

### 3.3. Log status codes instead of full errors

With gRPC, `Status.Code` is usually sufficient to classify operational outcomes. You can log the method, code, duration, and internal event code. Avoid logging raw `Status.getDescription()`, trailer contents, or `StatusRuntimeException` if the message/cause might contain payloads, internal addresses, or responses from external systems.

Stack traces are helpful when investigating programming bugs, but vet which exceptions are allowed into logs. Never embed request objects, tokens, or user data inside exception messages. When exception messages cannot be guaranteed safe, log the event code and exception type; store sanitized diagnostics in a system with restricted access.

## 4. Example `ServerInterceptor` that logs only safe fields

A `ServerInterceptor` is a convenient place to record an RPC's outcome and duration. The interceptor below logs only the method name, status code, elapsed time, and validated request ID. It does not read payloads, dump metadata, or log status descriptions or trailers.

```java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class SafeRpcLoggingInterceptor implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRpcLoggingInterceptor.class);

    private static final Metadata.Key<String> REQUEST_ID_KEY =
            Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        String requestId = safeRequestId(headers.get(REQUEST_ID_KEY));
        long startedAt = System.nanoTime();

        ServerCall<ReqT, RespT> loggingCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt);

                        log.info(
                                "grpc_server_call method={} status={} elapsed_ms={} request_id={}",
                                method,
                                status.getCode(),
                                elapsedMs,
                                requestId);

                        super.close(status, trailers);
                    }
                };

        return next.startCall(loggingCall, headers);
    }

    private static String safeRequestId(String candidate) {
        if (candidate == null || !candidate.matches("[A-Za-z0-9._-]{1,64}")) {
            return "-";
        }
        return candidate;
    }
}
```

Register the interceptor using the extension mechanism supported by your project's Spring gRPC starter. Global interceptor registration differs across starters; do not copy annotations or configuration from another starter if your project does not use it.

This pattern illustrates logging the outcome when the server closes the call. For streaming RPCs, duration is measured from when the interceptor receives the call until the call closes; align with the operations team on how to interpret this metric. If per-message timing or byte counts are needed, use appropriate instrumentation and emit only approved aggregate metrics. Never attach a listener to print individual request/response messages.

On the client side, apply the same principle in `ClientInterceptor`: log method, status code, and duration; never log `CallOptions`, entire `Metadata`, requests, responses, or trailers. For errors, log only the status code and safe event codes. Correlation IDs must be propagated per controlled convention, never pulled arbitrarily from context and dumped into logs.

## 5. When payload debugging is needed, build a dedicated diagnostic record

Sometimes you need to know whether a request had an unusual shape or an invalid field value. In such cases, do not enable full Protobuf dumping. Build a dedicated diagnostic projection containing only fields classified as safe.

For example, on an order-creation RPC, you might log the line-item count and schema validation result if those figures are permitted by data policy:

```java
log.debug(
        "create_order_validation item_count={} has_note={} schema_valid={}",
        request.getItemsCount(),
        request.hasCustomerNote(),
        validationResult.isValid());
```

Never log `customerNote` content, payment details, addresses, or the entire `request`. Even counts or boolean flags must be evaluated in context; an aggregate value can still leak information when combined with other data.

If specific values must be inspected, use synthetic data in a test environment or create fixtures stripped of identifying data. Never copy production payloads into tickets, chats, attachments, or dev environments solely to reproduce bugs without an approval and de-identification process.

Avoid writing generic redaction helpers that walk every Protobuf field and mask a few familiar field names. That approach easily misses new fields, maps, repeated fields, nested messages, and sensitive data embedded in free-form strings. A per-use-case allowlisted projection is easier to review and test.

## 6. Controlling logs, traces, and observability tools

### 6.1. Apply the same policy to every sink

Data policies must apply uniformly across:

- Application logs from SLF4J/Logback or equivalent logging frameworks.
- Logs produced by interceptors, exception handlers, and gRPC libraries.
- Distributed traces, span attributes, span events, and baggage.
- Error tracking, APM, profilers, and request capture tools.
- Proxy, gateway, service mesh, ingress, and load balancer logs.
- CI logs, debug artifacts, dump files, and backups.

Never attach access tokens, emails, phone numbers, or payloads to span attributes for search convenience. Never put credentials into baggage, since baggage can propagate across many services and cross trust boundaries. Use trace IDs to correlate events; add only attributes with safe classification and appropriate cardinality.

### 6.2. Be cautious with debug mode and wire logging

Before enabling `DEBUG` logging or HTTP/2/Netty wire logging in production, know exactly which logger will output what, which sink receives the data, who can read it, and what the retention period is. Transport-layer debug settings can log headers or frames containing application-encrypted data or data already decrypted inside the process. Enable only temporarily under an incident procedure, with narrow scope, formal approval, and a clear shutoff time.

Never leave sensitive debug flags enabled long-term via environment variables, config servers, or deployment manifests. When reproducing bugs, prefer test environments with synthetic data.

### 6.3. Protecting log storage systems

Reducing logged data remains the most important control. Alongside it, log systems need role-based access control, strong authentication, encryption in transit and at rest, access auditing, retention limits, and policy-driven deletion workflows. Restrict log exports and sharing. Never assume masking a token in the UI removes that token from indexes, archives, or backups.

Redaction in the collection pipeline can act as an extra defense layer, but it does not replace preventing the application from emitting sensitive data. Regex filters can miss encoded tokens, variant field names, binary data, or strings inside exceptions. Controlling output at the source avoids data replication before filters ever run.

## 7. Testing to prevent log data leaks

Add tests for critical logging paths, especially interceptors and exception handlers. Put easily identifiable canary values such as `TEST_SECRET_DO_NOT_LOG` in metadata and payloads, execute the RPC, and verify captured logs contain none of that string.

Example test criteria:

1. Send a request with a sensitive field containing the canary string.
2. Send `authorization` and `x-api-key` metadata with canary values.
3. Have the RPC return an error whose mock description includes the canary to verify the logger does not record descriptions.
4. Collect logs from a test appender or test sink.
5. Verify the log still includes the required method, status code, and duration, while containing zero canary occurrences.

Beyond automated tests, review `.proto` schema changes, interceptors, exception handlers, and logging configurations for risky patterns such as:

```java
log.debug("request={}", request);
log.info("headers={}", headers);
log.error("RPC failed: {}", exception.getMessage());
log.debug("trailers={}", trailers);
```

Examine each pattern against real data and replace it with allowlisted logging. Source scanning is only an aid; canary tests prove behavior of the actual execution path and should be maintained as new RPCs are added.

## 8. Responding when credentials have appeared in logs

If a token, API key, or secret is discovered in logs, treat it as a credential exposure incident:

1. Identify the credential type, time window, services, and all sinks that received the records.
2. Revoke or rotate the credential; invalidate sessions/tokens if the auth mechanism supports it.
3. Audit log access and credential usage during the exposure window.
4. Restrict access and handle records and copies per incident response procedures, retention policies, and legal requirements.
5. Fix the logger at the source, add canary tests, and verify related pipelines no longer emit the data.
6. Document the blast radius and remediation evidence per internal procedures.

Deleting values from a single search screen is insufficient to conclude the incident is resolved. Check indexes, archives, exports, backups, and observability platforms receiving forwarded data. Deletion must follow evidence preservation procedures and organizational policy.

## 9. Pre-release review checklist

- [ ] No logger calls `toString()` on Protobuf requests/responses or serializes entire payloads.
- [ ] Full gRPC Metadata, headers, trailers, or `*-bin` values are never logged.
- [ ] Access tokens, refresh tokens, API keys, cookies, OTPs, and private keys never appear in logs.
- [ ] RPC logs contain only method, status code, duration, and validated correlation IDs or other allowlisted fields.
- [ ] Status descriptions, exception messages, and stack traces are vetted to avoid containing payloads or credentials.
- [ ] Trace attributes, events, baggage, and metric labels follow the same data policy.
- [ ] Production debug/wire logging has a temporary activation process, narrow scope, and shutoff after investigation.
- [ ] Log storage enforces access control, access auditing, encryption, and retention limits.
- [ ] Canary tests prove synthetic secrets never appear in logs across success and failure flows.
- [ ] A credential revocation and copy-remediation procedure exists if a leak is detected.

Good logging for Spring gRPC links an RPC to a trace and records the method, outcome, and duration. Payloads and credentials belong strictly inside controlled business flows; they must never become default data in the logging system.
