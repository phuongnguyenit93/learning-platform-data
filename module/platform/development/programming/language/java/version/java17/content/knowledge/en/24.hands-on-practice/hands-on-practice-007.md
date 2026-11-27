# Calling HTTP/2 Services and Handling Errors and Timeouts in Java 17

Java 17 includes the official HTTP Client API in the `java.net.http` package. This API lets applications invoke HTTP services synchronously or asynchronously, send requests with headers and bodies, receive responses, and select a preferred HTTP version. With services supporting HTTP/2, the client can use multiplexing to send multiple requests over a single connection; if HTTP/2 is not negotiated, the connection can fall back to HTTP/1.1.

A reliable service call must address four parts:

1. **Protocol and connection:** preferring HTTP/2, reusing the client, and understanding fallback and TLS/ALPN.
2. **Timeouts:** bounding connection establishment time and per-request duration.
3. **HTTP outcomes:** distinguishing success status codes, client errors, and server errors.
4. **Transport errors and recovery:** handling timeouts, DNS, TLS, closed connections, interruptions, and bounded retries.

This lesson uses `HttpClient`, `HttpRequest`, and `HttpResponse` built into JDK 17. Examples use illustrative HTTPS endpoints; replace them with the actual addresses and API contracts of the services you call.

## 1. HTTP/2 in Java 17

HTTP/2 is a version of the HTTP protocol using binary framing and supporting multiplexing of multiple request/response streams over a single connection. Compared to traditional HTTP/1.1, multiplexing can reduce the need to open multiple connections when a client sends concurrent requests.

Java 17 supports HTTP/1.1 and HTTP/2 through `java.net.http.HttpClient`. This class manages connections and can be reused across many requests.

### 1.1. Preferring HTTP/2

Create the client:

```java
import java.net.http.HttpClient;

HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

`version(HttpClient.Version.HTTP_2)` sets the client's preferred version. This is not a guarantee that every request will use HTTP/2. The actual version depends on the server, TLS, ALPN, and any proxies or load balancers in the path.

### 1.2. Confirming the Actual HTTP Version

After receiving a response, inspect `response.version()`:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

System.out.println("HTTP version: " + response.version());
```

The result is `HttpClient.Version.HTTP_2` or `HttpClient.Version.HTTP_1_1`.

Distinguish between:

- `client.version()` reports the preferred version configured on the client.
- `response.version()` reports the version actually used for that response.

If the client prefers HTTP/2 yet the response uses HTTP/1.1, inspect the server and network infrastructure. Over HTTPS, HTTP/2 is typically negotiated during TLS via ALPN. If the server, proxy, or gateway does not support HTTP/2 on that connection, the client can use HTTP/1.1.

### 1.3. Reusing HttpClient

Create a shared `HttpClient` for requests targeting the same service group or connection policy:

```java
private static final HttpClient HTTP_CLIENT =
        HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();
```

`HttpClient` is designed to be reused and to manage connection pooling. Creating a new client for every request forfeits connection reuse and increases TCP/TLS handshake overhead.

HTTP/2 multiplexing does not mean every request will always be faster in every scenario. Throughput and latency also depend on the server, max concurrent streams, network conditions, payloads, flow control, and load. Measure on real workloads.

## 2. Configuring Timeouts: Connect and Request

An HTTP call can stall at multiple stages: establishing a connection, TLS handshake, sending the request, waiting for response headers, or reading the body. The Java HTTP Client exposes two key timeout configurations.

| Timeout | Configured on | Purpose |
| --- | --- | --- |
| Connect timeout | `HttpClient.Builder.connectTimeout(Duration)` | Limits how long establishing a new connection may take. |
| Request timeout | `HttpRequest.Builder.timeout(Duration)` | Sets a deadline for a specific request; if the response is not received in time, the call may fail with `HttpTimeoutException`. |

### 2.1. Connect Timeout

Configured at the client level:

```java
import java.time.Duration;
import java.net.http.HttpClient;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .version(HttpClient.Version.HTTP_2)
        .build();
```

If a connection cannot be established within this duration, the call can fail with a timeout error. Connect timeout applies when opening a new connection; if the client reuses an existing pooled connection, there is no connect phase for this timeout to govern.

### 2.2. Request Timeout

Configured per request:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/status"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();
```

Request timeouts prevent requests from waiting indefinitely when a service fails to respond in time. Each request can specify a different deadline depending on the operation: lightweight queries can use short timeouts, while large file transfers may need longer ones.

Do not confuse request timeout with the end-to-end SLA of a business operation. If an application makes sequential calls, retries, or performs post-processing, total execution time can exceed a single request timeout. Enforce an overall deadline at the business layer when the entire workflow must be bounded.

### 2.3. Choosing Timeout Values

Timeout values should reflect normal latency, tail latency, SLAs, and acceptable recovery time.

Illustrative examples:

| Request type | Connect timeout | Request timeout |
| --- | ---: | ---: |
| Service health/status check | 2–3 seconds | 3–5 seconds |
| Typical data query | 2–3 seconds | 5–10 seconds |
| Long-running task submission | 2–3 seconds | Per business contract |
| Large file download | 2–5 seconds | Based on expected size and throughput |

These are not mandatory defaults. If timeouts are too aggressive, valid requests may fail during load spikes. If too generous, threads and resources remain tied up longer, growing queues and impacting other requests.

## 3. Sending Synchronous GET Requests and Reading Responses

`send()` dispatches the request and blocks until the response completes according to the body handler. This suits execution flows that wait directly for results.

Example:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetServiceExample {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/v1/users/42"))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = CLIENT.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println("HTTP version: " + response.version());
        System.out.println("Content-Type: "
                + response.headers()
                        .firstValue("Content-Type")
                        .orElse("not provided"));
        System.out.println(response.body());
    }
}
```

Steps:

1. Create and reuse an `HttpClient` with a preferred HTTP version and connect timeout.
2. Build an `HttpRequest` with URI, request timeout, headers, and method.
3. Call `send(request, BodyHandlers.ofString(...))`.
4. Inspect status code, HTTP version, headers, and body.

`BodyHandlers.ofString(StandardCharsets.UTF_8)` reads the response body into a `String`. This is convenient for JSON or moderately sized text. For large payloads, write directly to a file or consume as a stream.

The `api.example.com` endpoint is illustrative only. Real endpoints may require authentication, query parameters, or specific contract headers.

## 4. HTTP Status Codes Do Not Automatically Throw Exceptions

An important detail of `HttpClient` is that responses with status `404`, `429`, or `500` are still valid HTTP responses at the protocol layer. `send()` does not throw an exception merely because the status code indicates an error.

The application must check `response.statusCode()`:

```java
int status = response.statusCode();

if (status >= 200 && status < 300) {
    System.out.println("Request succeeded");
} else {
    System.err.println("HTTP error: " + status);
}
```

A rough classification:

| Status group | Meaning | Typical handling |
| --- | --- | --- |
| 2xx | Request succeeded | Process the response body according to the API contract. |
| 3xx | Redirect | Check redirect policy or handle `Location`. |
| 4xx | Request/client/authentication problem | Fix request, permissions, or payload; usually do not retry automatically. |
| 5xx | Server/gateway error | Can retry with bounds if the operation is safe and the error appears transient. |

Notable status codes:

- `400 Bad Request`: invalid request syntax or payload.
- `401 Unauthorized`: missing or invalid authentication credentials.
- `403 Forbidden`: identity authenticated, but access is not permitted.
- `404 Not Found`: resource does not exist or is not exposed.
- `408 Request Timeout`: server/proxy did not receive the complete request in time.
- `409 Conflict`: business state conflict.
- `422 Unprocessable Content`: syntactically valid content that violates processing rules.
- `429 Too Many Requests`: rate limit exceeded.
- `500 Internal Server Error`: server-side processing failure.
- `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`: error or overload at an upstream gateway or intermediate service.

Status codes must be interpreted per the API contract. For example, some APIs return `404` to avoid leaking the existence of unauthorized resources.

## 5. Creating an Exception for Error HTTP Statuses

Applications can translate non-2xx responses into a custom exception so callers handle them uniformly.

Example:

```java
public final class RemoteServiceException extends RuntimeException {

    private final int statusCode;
    private final String responseBody;

    public RemoteServiceException(int statusCode, String responseBody) {
        super("Remote service returned HTTP " + statusCode);
        this.statusCode = statusCode;
        this.responseBody = responseBody;
    }

    public int statusCode() {
        return statusCode;
    }

    public String responseBody() {
        return responseBody;
    }
}
```

Response-checking helper:

```java
import java.net.http.HttpResponse;

static String requireSuccess(HttpResponse<String> response) {
    int status = response.statusCode();

    if (status < 200 || status >= 300) {
        throw new RemoteServiceException(
                status,
                response.body()
        );
    }

    return response.body();
}
```

Usage:

```java
HttpResponse<String> response = CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

String json = requireSuccess(response);
```

Preserving the status and part of the error body aids diagnostics. However, never log the entire body unconditionally: error responses may contain tokens, personal data, or internal details. Truncate logged bodies, scrub sensitive fields, and restrict log access.

Never assume error response bodies are always JSON. A proxy might return HTML or plain text; inspect `Content-Type` and parse according to the API contract.

## 6. Handling Timeouts and Network Errors with send()

`HttpClient.send()` declares two main checked exception types:

- `IOException`: I/O failures while sending or receiving.
- `InterruptedException`: the waiting thread was interrupted.

`HttpTimeoutException` is a subclass of `IOException` thrown when a request times out.

Common exceptions you may encounter:

| Exception | Possible scenario |
| --- | --- |
| `HttpTimeoutException` | Request did not complete within the configured timeout. |
| `ConnectException` | Could not establish a connection to the host/port. |
| `UnknownHostException` | Hostname could not be resolved. |
| `SSLHandshakeException` | TLS handshake failed, e.g., untrusted certificate or incompatible protocol. |
| `IOException` | Connection closed, read/write error, or other network failure. |
| `InterruptedException` | Thread waiting on the request was interrupted. |

Handling example:

```java
import java.io.IOException;
import java.net.http.HttpTimeoutException;

try {
    HttpResponse<String> response = CLIENT.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    String body = requireSuccess(response);
    System.out.println(body);

} catch (HttpTimeoutException ex) {
    System.err.println("HTTP request timed out: " + ex.getMessage());

} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "HTTP request was interrupted",
            ex
    );

} catch (IOException ex) {
    System.err.println("HTTP transport failure: " + ex.getMessage());
}
```

Catch `HttpTimeoutException` before `IOException` because it is a subclass. When catching `InterruptedException`, restore the interrupt flag via `Thread.currentThread().interrupt()` unless rethrowing the `InterruptedException` itself. Never swallow an interrupt and continue as if the request succeeded.

Status errors were converted into `RemoteServiceException` by the earlier helper; they are distinct from transport errors. Keep both categories separate to avoid misconfigured retries.

## 7. Sending JSON POST Requests and Handling Responses

To send a request body, use `HttpRequest.BodyPublishers`. Example sending JSON:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class PostServiceExample {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    public static void main(String[] args)
            throws Exception {

        String json = """
                {
                    "name": "Lan",
                    "role": "developer"
                }
                """;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/v1/users"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json; charset=UTF-8")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json,
                        StandardCharsets.UTF_8
                ))
                .build();

        HttpResponse<String> response = CLIENT.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        if (response.statusCode() < 200
                || response.statusCode() >= 300) {
            throw new RemoteServiceException(
                    response.statusCode(),
                    response.body()
            );
        }

        System.out.println("HTTP version: " + response.version());
        System.out.println(response.body());
    }
}
```

`Content-Type` describes the request body format; `Accept` indicates the response format desired by the client. `ofString(json, UTF_8)` encodes the body as UTF-8.

Text blocks make multi-line JSON readable, but they do not serialize or validate objects. For dynamic payloads, use a proper JSON serialization library rather than manual string concatenation.

### 7.1. Other Body Publishers

| Publisher | Purpose |
| --- | --- |
| `BodyPublishers.ofString` | Send text or JSON. |
| `BodyPublishers.ofByteArray` | Send binary data already in memory. |
| `BodyPublishers.ofFile` | Stream content from a file. |
| `BodyPublishers.noBody` | Request without a body. |
| `BodyPublishers.fromPublisher` | Supply body content via a reactive `Flow.Publisher`. |

Example uploading a file:

```java
import java.nio.file.Path;

HttpRequest upload = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/files"))
        .timeout(Duration.ofMinutes(2))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(Path.of("report.bin")))
        .build();
```

Set the timeout according to file size and upload SLA. Avoid reading an entire large file into a byte array unnecessarily.

## 8. Choosing an Appropriate BodyHandler

A response body can be read as text, a byte array, a file, or a stream.

| BodyHandler | Body type | When appropriate |
| --- | --- | --- |
| `ofString(UTF_8)` | `String` | Moderately sized JSON or text. |
| `ofByteArray()` | `byte[]` | Small binary payloads processed in memory. |
| `ofFile(path)` | `Path` | Downloading a file to disk. |
| `ofInputStream()` | `InputStream` | Streaming processing with manual read/close control. |
| `discarding()` | `Void` | Response body is not needed. |

Example downloading a file:

```java
import java.nio.file.Path;

HttpResponse<Path> response = CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofFile(Path.of("download.bin"))
);

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    System.out.println("Saved: " + response.body());
} else {
    throw new RemoteServiceException(
            response.statusCode(),
            "File download failed"
    );
}
```

When downloading directly to a final path, check the status code and clean up invalid files if the server returned an error. For stronger safety, download into a temporary file, verify status/content/checksum, and then move it to the final destination.

With `ofInputStream()`, the application must close the stream after reading:

```java
HttpResponse<java.io.InputStream> response = CLIENT.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

try (java.io.InputStream input = response.body()) {
    byte[] firstChunk = input.readNBytes(4096);
    System.out.println("Read: " + firstChunk.length);
}
```

This example reads at most the first 4096 bytes. Real code must read until EOF or hand the stream off to an appropriate processor. Closing the stream releases underlying resources.

## 9. Redirects and HTTPS

By default, `HttpClient` does not follow redirects automatically. You can configure this:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Policies:

| Value | Behavior |
| --- | --- |
| `Redirect.NEVER` | Never follow redirects automatically; this is the default. |
| `Redirect.NORMAL` | Follow redirects, except downgrading from HTTPS to HTTP. |
| `Redirect.ALWAYS` | Follow all redirects, including HTTPS to HTTP downgrades. |

For requests carrying tokens or sensitive data, exercise caution with redirects because the target may be a different host or scheme. Avoid permitting HTTPS-to-HTTP downgrades when transmitting credentials.

You can inspect prior responses via `previousResponse()` when the client follows a redirect chain.

## 10. Calling HTTP Asynchronously with sendAsync()

`send()` blocks the calling thread while waiting. `sendAsync()` returns a `CompletableFuture<HttpResponse<T>>` so the application can continue other work.

Example:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncHttpExample {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    static CompletableFuture<String> getUser() {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/v1/users/42"))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        return CLIENT.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                )
                .thenApply(response -> {
                    if (response.statusCode() < 200
                            || response.statusCode() >= 300) {
                        throw new java.util.concurrent.CompletionException(
                                new RemoteServiceException(
                                        response.statusCode(),
                                        response.body()
                                )
                        );
                    }

                    return response.body();
                });
    }

    public static void main(String[] args) {
        getUser()
                .thenAccept(body -> System.out.println(body))
                .exceptionally(error -> {
                    System.err.println("Request failed: " + error);
                    return null;
                });
    }
}
```

`sendAsync` initiates the request and returns a future. `thenApply` validates the status and maps the response to its body. If the status is unsuccessful, the code completes the future exceptionally with `RemoteServiceException` wrapped in `CompletionException`.

When handling asynchronous failures, inspect the underlying cause inside `CompletionException` or `ExecutionException` depending on how the future is consumed. Avoid logging only the wrapper message and losing the root cause.

### 10.1. Combining Multiple Requests

You can dispatch multiple independent requests and wait for all to complete:

```java
CompletableFuture<HttpResponse<String>> first =
        CLIENT.sendAsync(request1, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> second =
        CLIENT.sendAsync(request2, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all =
        CompletableFuture.allOf(first, second);

all.thenRun(() -> {
    System.out.println(first.join().statusCode());
    System.out.println(second.join().statusCode());
});
```

Requests run concurrently. `allOf` completes when all component futures complete; if any future fails, the combined future also completes exceptionally. Inside the `all` callback, child futures have completed, so `join()` retrieves their values.

HTTP/2 multiplexing and `sendAsync` are separate concepts:

- HTTP/2 is a protocol version capable of multiplexing streams over one connection.
- `sendAsync` is an asynchronous API so callers do not block the current thread.

You can use `sendAsync` over HTTP/1.1 or `send` with an HTTP/2-preferring client.

## 11. Handling Errors in CompletableFuture

When `sendAsync` fails, the future completes exceptionally. Errors are typically wrapped in `CompletionException` across pipeline stages or when retrieving results.

Example unwrapping the cause:

```java
import java.util.concurrent.CompletionException;

static Throwable unwrap(Throwable error) {
    if (error instanceof CompletionException
            && error.getCause() != null) {
        return error.getCause();
    }

    return error;
}
```

Usage:

```java
getUser().whenComplete((body, error) -> {
    if (error == null) {
        System.out.println("Success: " + body);
        return;
    }

    Throwable cause = unwrap(error);

    if (cause instanceof java.net.http.HttpTimeoutException) {
        System.err.println("Request timed out");
    } else if (cause instanceof RemoteServiceException remote) {
        System.err.println(
                "HTTP status: " + remote.statusCode()
        );
    } else {
        System.err.println("Transport/processing error: " + cause);
    }
});
```

Not every error in a future is a network failure. Callbacks such as JSON parsing or response mapping can also throw exceptions. Separate transport failures, HTTP status errors, and application-level data processing errors.

Keep setting request timeouts on `HttpRequest`. Do not rely solely on waiting on the future or applying callback-level timeouts without managing the in-flight request.

## 12. Classifying Errors to Choose the Right Action

Good designs categorize failures into clear groups:

### 12.1. Configuration or Request Errors

Examples include invalid URIs, invalid headers, or invalid request builder arguments. These usually require fixing code or configuration; retrying does not help.

### 12.2. Transport Errors

Examples include DNS failures, connection refused, connection reset, TLS handshake failures, or timeouts. Some failures may be transient, but check the error type and operation safety before retrying.

### 12.3. HTTP Error Responses

The server returned a response, but its status lies outside the success range. Use the status code and API contract to decide whether to fix the request, re-authenticate, honor a rate limit, or report an error.

### 12.4. Parse/Validation Errors

A response may be HTTP `200` yet have a malformed schema, missing fields, or invalid values. This is a data-handling error, not a connection error. Never infinitely retry a malformed response.

Suggested mapping:

| Category | Examples | Handling approach |
| --- | --- | --- |
| Request/configuration | Invalid URI/header | Fix input/configuration. |
| Authentication | `401` | Refresh credentials/token via security flow; retry with bounds if appropriate. |
| Authorization | `403` | Check permissions; do not retry blindly. |
| Business/client error | `400`, `404`, `409`, `422` | Return business error or fix request. |
| Rate limit | `429` | Inspect `Retry-After` and apply backoff. |
| Transient service error | `502`, `503`, `504` | May retry if operation is safe and deadline remains. |
| Network/timeout | `IOException`, `HttpTimeoutException` | Evaluate idempotency, retry policy, and request state. |
| Response processing | JSON parse/validation failure | Investigate contract/schema; generally do not retry immediately. |

## 13. Bounded and Safe Retries

Retries can recover from transient failures, yet misconfigured retries can overload services or execute an action multiple times.

### 13.1. Retry Only Safe Operations

Methods with HTTP idempotent semantics are generally safer to retry when the API actually honors those semantics:

- `GET`: reads data.
- `PUT`: sets resource state to the supplied representation.
- `DELETE`: requests resource deletion.
- `HEAD`/`OPTIONS`: queries metadata/capabilities.

`POST` is usually not idempotent. If the server processed a `POST` and the response was lost, retrying can create a duplicate order or transaction. Only retry `POST` if the API supports an idempotency key/deduplication mechanism and the client follows that contract.

Never rely solely on the HTTP verb name. An API might implement non-standard semantics; verify actual business behavior.

### 13.2. Use Bounded Exponential Backoff

A retry policy typically includes:

1. Maximum number of attempts.
2. Increasing backoff between attempts.
3. Jitter so multiple clients do not retry in lockstep.
4. Overall deadline.
5. Explicit allowlist of retryable errors/statuses.
6. Idempotency precondition.
7. Honoring `Retry-After` when provided by the server.

Example schedule:

| Attempt | Illustrative base backoff |
| --- | ---: |
| Attempt 1 | No wait |
| Attempt 2 | 200 ms |
| Attempt 3 | 400 ms |
| Attempt 4 | 800 ms |

Actual delays should add jitter and enforce an upper cap. Do not treat the table above as universal defaults for every system.

### 13.3. Status Codes Eligible for Retry Consideration

- `429`: respect rate limits and `Retry-After` if present.
- `502`/`503`/`504`: may indicate transient gateway or service issues.
- `408`: may be retryable depending on contract and request state.
- Selected transport errors: may retry if the request is idempotent and deadline remains.

Do not blindly retry all `5xx` codes. A `500` can be a deterministic logic bug; repeated retries merely amplify load. `4xx` responses usually require fixing the request or permissions, not automatic retries.

### 13.4. Retry-After

The `Retry-After` header may specify a delay in seconds or an HTTP-date timestamp. When the server sends it, honor it per API/rate-limit policy while still enforcing the application's maximum wait cap and overall deadline.

Do not retry earlier than the server requested just because an internal backoff interval is shorter.

### 13.5. Avoiding Retry Storms

If many instances retry simultaneously when a service is overloaded, traffic surges and worsens the outage. Use bounded retries, jitter, architectural circuit breakers/bulkheads where appropriate, and concurrency limits. Never write unbounded retry loops inside callbacks or executors.

## 14. Redirects, Authentication, and Sensitive Headers

Requests can carry `Authorization`, API keys, or cookies. When configuring redirects, understand which headers are forwarded and whether a redirect target may point to another host or scheme.

Principles:

- Send credentials only to trusted hosts and schemes.
- Avoid redirecting from HTTPS down to HTTP.
- Never log tokens or API keys.
- Never hardcode secrets in source code.
- Use a secret manager or secure configuration mechanism.
- Validate responses before trusting returned data.

Example setting a bearer token:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/profile"))
        .timeout(Duration.ofSeconds(5))
        .header("Authorization", "Bearer " + accessToken)
        .header("Accept", "application/json")
        .GET()
        .build();
```

`accessToken` must come from a secure source and never appear in logs or exception messages. When a token expires, refresh it according to the authentication protocol; do not keep retrying with the expired token.

## 15. TLS and Certificate Errors

For HTTPS URIs, `HttpClient` uses the JDK's default SSL/TLS configuration unless customized. Handshake failures can stem from:

- Expired certificate or untrusted certificate chain.
- Hostname mismatch against the certificate.
- Server supporting only protocols or cipher suites disallowed by client policy.
- Missing CA in the trust store.
- Proxies or TLS inspection altering the certificate chain.
- Mutual TLS requiring a client certificate that is not configured.

Never disable certificate verification or accept all hostnames as a "quick fix". Fix the certificate chain, hostname, trust store, or server configuration instead.

In production, never log private keys or credentials. When diagnosing issues, log the exception and necessary endpoint/certificate metadata per security policy.

## 16. Bounding Bodies and Handling Large Payloads

`BodyHandlers.ofString()` and `ofByteArray()` buffer the entire body in memory. This is convenient for small responses, but can cause heap pressure when responses are huge or many requests run concurrently.

For large payloads:

- Use `BodyHandlers.ofFile(path)` to save to disk.
- Use `ofInputStream()` and read in buffered chunks for streaming processing.
- Enforce size limits at the application or gateway layer.
- Inspect `Content-Length` if present, without relying on it as the sole guarantee.
- Verify `Content-Type` and validate payload contents.
- Close streams and file resources properly.

If an API returns massive JSON payloads, consider a streaming parser instead of materializing the entire JSON string in the heap.

## 17. Complete Example: Synchronous Client with Timeouts and Error Classification

The example below reuses the client, prefers HTTP/2, configures connect and request timeouts, checks status codes, and preserves interrupts:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class UserApiClient {

    private final HttpClient client;

    public UserApiClient() {
        this.client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public String getUser(String userId) {
        URI uri = URI.create(
                "https://api.example.com/v1/users/" + userId
        );

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8
                    )
            );

            if (response.statusCode() < 200
                    || response.statusCode() >= 300) {
                throw new RemoteServiceException(
                        response.statusCode(),
                        response.body()
                );
            }

            System.out.println("HTTP version: " + response.version());
            return response.body();

        } catch (HttpTimeoutException ex) {
            throw new IllegalStateException(
                    "User service timed out",
                    ex
            );

        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "User request was interrupted",
                    ex
            );

        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot communicate with user service",
                    ex
            );
        }
    }
}
```

`RemoteServiceException` is the exception defined earlier. In production code, validate `userId` before appending it to the URI or use a URI builder to encode path segments properly. This example focuses on invocation and response handling.

## 18. Complete Example: Asynchronous Calls with HTTP/2

A service client can return a `CompletableFuture` to its callers:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class AsyncUserApiClient {

    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    public CompletableFuture<String> getUser(String userId) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "https://api.example.com/v1/users/" + userId
                ))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                )
                .thenApply(response -> {
                    if (response.statusCode() < 200
                            || response.statusCode() >= 300) {
                        throw new CompletionException(
                                new RemoteServiceException(
                                        response.statusCode(),
                                        response.body()
                                )
                        );
                    }

                    return response.body();
                });
    }
}
```

The caller decides how to compose the future into its workflow:

```java
client.getUser("42")
        .thenAccept(body -> processUserJson(body))
        .exceptionally(error -> {
            Throwable cause = error instanceof CompletionException
                    && error.getCause() != null
                    ? error.getCause()
                    : error;

            logRequestFailure(cause);
            return null;
        });
```

`processUserJson` and `logRequestFailure` are illustrative application functions. Avoid blocking with `join()` right after `sendAsync()` when the goal is asynchronous execution.

## 19. Production Readiness Checklist for HTTP/2 Clients

Before deploying a client to production, verify:

- The client is reused rather than recreated per request.
- Preferred HTTP version is configured appropriately.
- `response.version()` is checked when confirming HTTP/2 negotiation.
- Servers, proxies, and load balancers support HTTP/2/ALPN as expected by the architecture.
- Connect timeout and request timeout are tuned to SLAs.
- Status codes are checked explicitly.
- Transport exceptions and HTTP status errors are categorized separately.
- `InterruptedException` is handled properly.
- Retries are bounded with backoff/jitter and idempotency checks.
- `Retry-After` is respected under rate limiting.
- Redirects do not leak credentials or downgrade HTTPS to HTTP.
- TLS certificates and hostnames are validated.
- Body handlers match expected payload sizes.
- Streams are closed after processing.
- Logs exclude tokens, secrets, and sensitive bodies.
- Metrics capture latency, status codes, timeouts, retries, and error rates.

## 20. Common Issues

| Issue | Possible cause | Resolution |
| --- | --- | --- |
| Configured HTTP/2 but response is HTTP/1.1 | Server/proxy did not negotiate HTTP/2 or fell back. | Inspect `response.version()`, TLS/ALPN, and infrastructure. |
| Requests hang too long | Missing request timeout or overly generous timeout. | Set `HttpRequest.timeout` per SLA. |
| Cannot connect to host | DNS, routing, firewall, or port issue. | Verify endpoint and network path. |
| TLS handshake fails | Certificate, hostname, truststore, or protocol/cipher mismatch. | Fix trust, certificate, or server config; never disable verification. |
| HTTP 404 yet no `IOException` | HTTP status is a valid transport-level response. | Check `statusCode()`. |
| Retry creates duplicate transactions | `POST` is not idempotent or server already processed the first attempt. | Use an idempotency key/deduplication or do not retry. |
| Async error is hard to inspect | Exception wrapped in `CompletionException`. | Unwrap `getCause()` and classify the root cause. |
| CPU/heap spikes downloading files | Reading whole body into `String` or `byte[]`. | Use file/stream handlers and enforce size limits. |
| Token sent to unexpected redirect target | Permissive redirect policy and credential handling. | Restrict redirects and protect credentials. |
| Many simultaneous request timeouts | Overloaded service, connection pool/network saturation, or overly tight deadlines. | Correlate metrics, server load, retries, and concurrency. |

## 21. Practice Exercises

### Exercise 1 — GET with HTTP/2 Preference

Create a client preferring `HTTP_2` and send a `GET` to an HTTPS endpoint supporting HTTP/2. Print status, body, and `response.version()`. Try an endpoint supporting only HTTP/1.1 to observe the actual behavior.

### Exercise 2 — Distinguishing the Two Timeouts

Configure a 2-second connect timeout and a 5-second request timeout. Target test endpoints that either refuse/drop connections or delay responses. Record the exceptions thrown and explain which timeout triggered.

### Exercise 3 — Handling Status Codes

Call endpoints returning `200`, `404`, `429`, and `503`. Write a response classifier function. Verify that error statuses are handled even though `send()` does not throw `IOException` for those statuses.

### Exercise 4 — POST JSON

Build a `POST` request using `BodyPublishers.ofString` with UTF-8. Set `Content-Type` and `Accept` appropriately. Check both response body and status code.

### Exercise 5 — Asynchronous Calls

Use `sendAsync`, `thenApply`, and `exceptionally`. Distinguish HTTP status errors from transport failures. Do not call `join()` immediately after dispatching the request.

### Exercise 6 — Safe Retries

Create a `GET` request targeting an endpoint that returns transient `503` responses. Implement up to three retries with exponential backoff and jitter. Never blindly retry `400`/`401`/`403`/`404`.

### Exercise 7 — POST and Idempotency

Simulate a resource-creating `POST`. Explain the scenario where the server processed the request but the response was lost. Design an idempotency key per the API contract so retries do not create duplicate resources.

### Exercise 8 — Downloading Files

Use `BodyHandlers.ofFile` or `ofInputStream` to download a large file. Check status, size, and checksum; ensure streams are closed and temporary files are handled on failure.

### Exercise 9 — Redirects and TLS

Create clients with `Redirect.NEVER` and `Redirect.NORMAL`. Compare responses on a redirecting endpoint. Verify certificate/hostname validation and ensure credentials are never sent to untrusted targets.

## 22. Quick Reference

| Need | API |
| --- | --- |
| Build client preferring HTTP/2 | `HttpClient.newBuilder().version(HttpClient.Version.HTTP_2)` |
| Connect timeout | `HttpClient.Builder.connectTimeout(Duration)` |
| Request timeout | `HttpRequest.Builder.timeout(Duration)` |
| Synchronous send | `client.send(request, bodyHandler)` |
| Asynchronous send | `client.sendAsync(request, bodyHandler)` |
| Create `GET` | `HttpRequest.Builder.GET()` |
| Create JSON `POST` | `POST(BodyPublishers.ofString(json, UTF_8))` |
| Check status | `response.statusCode()` |
| Check actual HTTP version | `response.version()` |
| Read text response | `BodyHandlers.ofString(UTF_8)` |
| Download file | `BodyHandlers.ofFile(path)` |
| Stream response | `BodyHandlers.ofInputStream()` |
| Follow redirects | `followRedirects(Redirect.NORMAL)` |
| Read response headers | `response.headers()` |
| Handle timeout | `HttpTimeoutException` |
| Preserve interrupt | `Thread.currentThread().interrupt()` |
| Async error cause | `CompletionException.getCause()` |

**Core principle:** Reuse a single `HttpClient` configured to prefer HTTP/2, and verify the negotiated protocol via `response.version()`. Set a connect timeout on the client and a request timeout on each request. Always inspect status codes because HTTP `4xx`/`5xx` responses do not automatically throw exceptions; handle transport failures, timeouts, and business errors separately. Retry only with bounds when operations are safe, honor `Retry-After` and deadlines, and safeguard TLS, credentials, and response bodies.
