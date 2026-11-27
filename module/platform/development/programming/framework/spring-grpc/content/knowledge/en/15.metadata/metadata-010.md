# Do Not Log Credentials or Tokens

In Spring gRPC, authentication information typically travels through request metadata, such as `authorization: Bearer ...`, API keys, or credentials supplied by `CallCredentials`. Metadata helps the client prove its identity when calling a service, but credential values must remain secret throughout the entire processing lifecycle. **Never log credentials or tokens into logs, traces, metrics, exceptions, or diagnostic data.**

A useful log line can still show which RPC was called, what the outcome was, how long it took, and which request ID was involved. This operational information is sufficient to investigate most incidents without storing secrets. This lesson focuses on preventing leaks when handling metadata and building safe logging for gRPC clients and servers.

## 1. What Data Must Be Treated as Secret?

Bearer tokens are not the only data requiring protection. Treat the following data as secrets or sensitive information:

| Data | Example location | Logging rule |
| --- | --- | --- |
| Access token | `authorization: Bearer ...` | Do not log the value, partial token, or decoded string |
| Refresh token | Metadata, body, or login result | Do not log |
| API key | `x-api-key`, custom metadata | Do not log |
| Basic credentials | `authorization: Basic ...` | Do not log |
| Cookie/session ID | `cookie`, `set-cookie` | Do not log |
| Client certificate/private key material | TLS configuration or certificate loading errors | Never log private key contents; restrict certificate identifying info per policy |
| Password, one-time code | Message or metadata depending on app | Do not log |
| Signed URL | Upload/download URL with query signature | Do not log full URL; the signature can grant access |

A value remains a secret even if it is Base64-encoded, URL-encoded, converted to JSON, or placed in binary metadata. Transforming the format does not make a credential safe to log. With JWTs, the payload is usually only Base64URL-encoded rather than encrypted; decoding a token for debugging can also expose claims and personal data.

## 2. Where Can Credentials Leak?

Leaks often happen at points added for diagnostics:

- **Client interceptor:** logging the entire `Metadata` before sending a request, or logging credential objects.
- **Server interceptor:** logging all request headers upon receiving a call or all trailers when closing a call.
- **Service:** logging `request.toString()`, exceptions, or payloads containing credentials.
- **HTTP/2 and gRPC debug logging:** enabling overly verbose wire/transport logging in real environments.
- **Reverse proxy/API gateway:** access logs configured to capture the `authorization` header, cookies, or signed URLs.
- **Tracing:** copying all metadata into span attributes or baggage for easy searching.
- **Metrics:** putting tokens or user-specific values into labels.
- **CI/test reports:** printing test fixtures containing real tokens or exceptions containing credentials.
- **Crash reports/support bundles:** collecting requests, environment variables, or configurations holding secrets.

Flow diagram of paths to control:

```text
Client credentials
       |
       v
ClientCall / CallCredentials / ClientInterceptor
       |
       v
HTTP/2 request headers
       |
       v
Gateway / proxy access logs
       |
       v
ServerInterceptor / authentication
       |
       v
Service / exception handling
       |
       v
Application logs, traces, metrics, support reports

Secrets must be protected at every point; not just in the service's logger.
```

Dangerous examples:

```java
// DO NOT DO THIS: may log access token and all other metadata.
logger.debug("incoming metadata={}", headers);

// DO NOT DO THIS: request may contain passwords, tokens, or personal data.
logger.info("request={}", request);

// DO NOT DO THIS: exception may contain the raw credential value.
logger.warn("authentication failed: {}", exception.getMessage());
```

You cannot conclude this logging is safe merely because one current environment does not happen to print tokens. When a new interceptor, debug flag, or library is added, what gets logged can change.

## 3. Use an Allowlist Instead of Logging Everything and Trying to Mask Secrets

A safer approach is to **select only approved fields to log**. This is an allowlist:

| Loggable field (if policy permits) | Why it is useful |
| --- | --- |
| RPC full method name | Identifies the method such as `orders.v1.OrderService/GetOrder` |
| gRPC status code | Indicates whether the call succeeded or failed |
| Duration | Latency analysis |
| System-generated/validated request ID | Correlates logs across components |
| Client version | Compatibility analysis if it contains no personal data |
| Internal error category | Groups incidents without exposing sensitive messages |

Fields not logged by default:

- Entire `Metadata`, request messages, response messages, or trailers.
- Values of `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, and custom application credential keys.
- Raw tokens, token fragments, unapproved JWT claims, passwords, private keys, or signed URLs.
- Exception messages unless guaranteed not to contain sensitive input.
- Entire baggage or span attributes automatically copied from metadata.

**The allowlist must be enforced where logs are created.** A filter that only masks `authorization` while still logging other custom keys can miss secrets added by the application later. Never use a short denylist like `remove("authorization")` and log everything else.

## 4. Writing a Server Interceptor That Logs Only Safe Fields

The example below logs the RPC name, status code, duration, and a format-restricted request ID. It does not read or log `authorization`, does not print `headers`/`trailers`, and does not include `status.getDescription()` in logs.

```java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SafeRpcLoggingInterceptor implements ServerInterceptor {
    private static final Logger log =
        LoggerFactory.getLogger(SafeRpcLoggingInterceptor.class);

    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);
        // Only accept short IDs without control characters.
        if (requestId != null
                && !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            requestId = null;
        }

        final String safeRequestId = requestId;
        final String method = call.getMethodDescriptor().getFullMethodName();
        final long startedAt = System.nanoTime();

        ServerCall<ReqT, RespT> wrapped =
            new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(
                    call) {
                @Override
                public void close(Status status, Metadata trailers) {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - startedAt);

                    log.info(
                        "grpc_server_call method={} status={} duration_ms={} request_id={}",
                        method,
                        status.getCode(),
                        durationMs,
                        safeRequestId);

                    // Preserve gRPC status and trailers.
                    super.close(status, trailers);
                }
            };

        return next.startCall(wrapped, headers);
    }
}
```

This is a minimal logging interceptor, not an authentication interceptor. A client-sent request ID is still untrusted input; the regex only constrains format and prevents control characters, rather than proving identity. For public systems, generate IDs at a trusted gateway/server or use validated IDs before logging.

In production, you can add a standardized error category or tenant pseudonym if policy permits. Do not add `status.getDescription()`, `headers.toString()`, or `trailers.toString()` just to increase log verbosity.

## 5. Handling Authentication Errors Without Leaking Tokens

The server needs enough information to distinguish authentication failures, without logging credentials to do so.

| Scenario | Safe log | Unsafe log |
| --- | --- | --- |
| Missing credential | `auth_result=missing` | Dumping all headers to see if token is absent |
| Invalid token signature | `auth_result=invalid_signature` or fixed category | Printing token or JWT payload |
| Expired token | `auth_result=expired` | Printing full claims or token |
| Wrong audience | `auth_result=audience_mismatch` | Printing token and all auth details |
| Introspection backend unavailable | `auth_result=verification_unavailable` | Printing request/exception containing authorization value |
| Caller lacks permissions | `authz_result=denied`, policy code | Printing entire principal/token or resource data |

Error handling example:

```java
try {
    VerifiedPrincipal principal = tokenVerifier.verify(accessToken);
    // Continue processing with authenticated principal.
} catch (ExpiredTokenException ex) {
    logger.warn(
        "grpc_authentication_failed category={} rpc={}",
        "expired",
        methodName);
    throw Status.UNAUTHENTICATED
        .withDescription("Authentication required")
        .asRuntimeException();
} catch (InvalidTokenException ex) {
    logger.warn(
        "grpc_authentication_failed category={} rpc={}",
        "invalid",
        methodName);
    throw Status.UNAUTHENTICATED
        .withDescription("Authentication required")
        .asRuntimeException();
}
```

Exception names and `tokenVerifier` are application examples. Do not log `accessToken`, `ex`, or `ex.getMessage()` if the authentication library might embed input into error messages. Stack traces may be recorded in a controlled internal error system when certain the exception carries no secrets; by default, log standardized categories and error codes.

Never turn every error into `UNAUTHENTICATED`. If a dependent token verification service goes down, return an operational status such as `UNAVAILABLE` and log the dependency failure category. Never grant access when credentials cannot be verified.

## 6. Tracing, Baggage, and Metrics Must Also Avoid Secrets

Application loggers are not the only place that can store data. OpenTelemetry span attributes, baggage, events, and exporters may be retained long-term, widely searchable, and shipped to multiple systems.

- Never put bearer tokens, API keys, or passwords into span attributes.
- Never put tokens into W3C baggage; baggage propagates across services via propagators.
- Never copy all gRPC metadata into span attributes.
- Only add approved attributes such as RPC method, status code, and duration.
- Never use tokens, session IDs, or per-call request IDs as metric labels; they can cause leaks and very high cardinality.
- Verify processors/exporters have appropriate filtering/redaction mechanisms, while still preventing secrets at the source.

Trace IDs and span IDs are observability identifiers, not credentials. However, they can still correlate user activity; apply your observability platform's access control and retention policies.

## 7. Gateway, Proxy, and Spring Environment Configuration

A Spring gRPC application may be safe at the service layer yet still leak tokens at the gateway or proxy:

1. **Reverse proxy/API gateway:** configure access logs to record only approved headers. Strip or redact `authorization`, cookies, signed URLs, and custom credential headers from logs.
2. **Spring Boot logging:** avoid enabling comprehensive debug/trace logging for gRPC, authentication, or HTTP/2 in production without auditing log output.
3. **Client credentials:** use `CallCredentials` or appropriate integrations to attach tokens; never log credential objects or `Metadata` after attaching.
4. **Server interceptors:** separate authentication from logging. Authentication logs only standardized outcomes; the logging interceptor logs only the allowlist.
5. **Error handling:** never include credentials in `Status` descriptions, custom trailers, response messages, or exceptions returned to clients.
6. **Log storage:** restrict read permissions, retention periods, download capabilities, and attaching logs to tickets/support bundles.

There is no single default logging level safe for every starter or proxy version. Inspect actual configurations of deployed components, especially when enabling wire logging for troubleshooting.

## 8. Testing to Ensure Tokens Never Appear in Logs

A security test should use a unique **fake canary secret**, such as `test-secret-DO-NOT-LOG-7f3a`. Send it via metadata in tests, execute both successful and failing RPCs, and assert that all logs captured during the test do not contain that string.

| Test case | What to verify |
| --- | --- |
| RPC with valid bearer token | Logs contain no token, JWT fragment, or authorization header |
| Invalid/expired token | Logs contain only category/status, no token or sensitive exception message |
| Custom credential key | `x-api-key` and custom auth keys do not appear in logs |
| Sensitive binary metadata | No dumping of `byte[]`, Base64, or metadata objects into logs |
| Service exception | Request/exception `toString()` is not logged if it may contain secrets |
| Response trailers | Do not log full trailers; do not return credentials in custom metadata |
| Tracing | Span attributes and baggage do not contain the canary secret |
| Gateway/proxy | Access logs do not contain authorization, cookies, or signed URLs |
| CI/test reports | Test output, assertion messages, and fixtures contain no real secrets |

Example test idea using Logback `ListAppender`:

```java
String canary = "test-secret-DO-NOT-LOG-7f3a";

// Send canary via credentials/metadata to the test server.
// Execute both a successful RPC and an UNAUTHENTICATED RPC.

String capturedLogs = listAppender.list.stream()
    .map(event -> event.getFormattedMessage())
    .reduce("", (left, right) -> left + "\n" + right);

assertFalse(capturedLogs.contains(canary));
assertFalse(capturedLogs.contains("Bearer " + canary));
```

This is an outline; appender and logger setup depends on your project's logging backend. Tests should capture logs from loggers related to interceptors, authentication, and services. Also check trace exporters and proxy access logs in integration/security tests; checking a single logger alone does not prove the entire system is safe.

## 9. If a Token Has Already Been Logged

If a real credential is discovered in logs or traces:

1. **Revoke or rotate the credential** via the token/API key issuance mechanism. Treat the exposed token as usable until revoked or expired.
2. Identify the logging source and every system that received a copy: application logs, gateways, tracing backends, CI, tickets, support bundles, and exports.
3. Restrict access to the affected logs; redact/purge copies according to your organization's retention and incident response procedures.
4. Check for anomalous usage via audit events and non-sensitive metadata; do not keep copying the token into incident reports.
5. Fix the logging source and add a canary test to prevent recurrence.

Deleting a single line in application logs is insufficient if proxies or tracing exporters already stored copies. Evaluate every destination where the data was forwarded.

## 10. Practice Exercise

A Spring gRPC application uses `authorization: Bearer ...` to call `PaymentService.AuthorizePayment`. While investigating an error, the team discovers an interceptor logs `headers` at DEBUG level and the gateway also logs all request headers.

**Requirements:**

1. Identify leak points across the client interceptor, server interceptor, gateway, tracing, and exception handling.
2. Replace metadata dumping with an allowlist containing RPC method, status code, duration, and validated request ID.
3. Keep the token in the authentication flow while removing it from logs, trace attributes, baggage, and metrics.
4. Standardize logs for missing token, invalid signature, expired token, and unavailable verification dependency cases.
5. Write a canary-secret test verifying logs for both successful and failed RPCs contain no token.
6. Describe how to rotate tokens and locate copies if a real credential has already appeared in logs.

**Self-check questions:**

- Why does Base64-encoding or decoding a JWT not make a token safe to log?
- Why is an allowlist safer than logging everything and masking a few keys?
- Which components besides the application logger might store request metadata?
- Should tokens be placed into OpenTelemetry baggage or metric labels?
- Why should `exception.getMessage()` not be logged on every authentication failure?
- When a real token is found in logs, why must credentials be rotated and all copies audited?

**Key takeaway:** Never log credentials or tokens in any form. Keep secrets confined to the authentication flow, log only approved operational fields, lock down gateways/tracing/CI, and use canary secrets to test logs. If a real token is exposed, revoke or rotate it immediately and audit every system that received a copy.
