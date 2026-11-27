# HTTP Status Codes, Headers, and Response Data with Java 17

## 1. What Does an HTTP Response Contain?

When a Java application sends a request to a web server, the server returns an **HTTP response**. The response indicates the outcome of processing the request, provides metadata, and may carry data the application needs to use.

An HTTP response typically has three parts:

~~~text
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 46
Cache-Control: no-store

{"id":42,"status":"PAID","active":true}
~~~

| Part | Role | Example |
|---|---|---|
| Status code | Indicates the request processing result. | `200`, `404`, `503` |
| Headers | Describe the response, content, caching, authentication, redirection, etc. | `Content-Type`, `ETag`, `Location` |
| Body | Response payload if the status and method permit content. | JSON, HTML, image, file, or text |

In HTTP/2, the wire format is no longer a text status line like HTTP/1.1; the protocol uses pseudo-headers such as `:status` and transmits headers and body in frames. At the application level, however, you still work with status code, headers, and body. Java 17's HttpClient provides a unified API across the HTTP versions it supports.

In Java 17, prefer `java.net.http.HttpClient`, standardized in Java 11, to send requests and read responses. `HttpResponse<T>` holds the status code, headers, body, and related metadata.

## 2. Status Codes: Classifying Processing Outcomes

An HTTP status code is a three-digit integer. The first digit identifies the outcome category:

| Group | Meaning | How to interpret |
|---|---|---|
| `1xx` | Informational | Protocol progress information; typically not the final response the application processes. |
| `2xx` | Success | The request was received and processed successfully per the specific status semantics. |
| `3xx` | Redirection | The client needs to or may take action involving another resource or a cache. |
| `4xx` | Client error | The request has an issue, is unauthorized, or cannot be processed given the current resource state. |
| `5xx` | Server error | The server or gateway encountered an error while attempting to process a valid request. |

Do not check only whether the status equals `200`. A successful request may return `201`, `202`, or `204` depending on the operation.

### 2.1. Common success status codes

| Code | Name | Practical meaning |
|---:|---|---|
| `200` | OK | The request succeeded; usually includes a body with a representation or result. |
| `201` | Created | A new resource was created. The `Location` header may point to the newly created resource URI. |
| `202` | Accepted | The request was accepted for processing, though processing may not yet be complete. The client should not treat this as the final business outcome. |
| `204` | No Content | The request succeeded, but the response has no body. Common for update/delete operations that do not return a representation. |
| `206` | Partial Content | The server returns a portion of the representation, typically due to a `Range` request header. |

For example, when creating an order, an API may return `201 Created` with `Location: /orders/42` and a body describing the order. When requesting to delete a resource, an API may return `204 No Content`.

**Do not attempt to parse JSON when the response has no body.** For `204`, or responses with no content per contract, the application should inspect the status first and only parse the body if one is actually present.

### 2.2. Redirection status codes

| Code | Name | Notes |
|---:|---|---|
| `301` | Moved Permanently | The resource URI has moved permanently. |
| `302` | Found | Temporary redirection. |
| `303` | See Other | The client is directed to another resource, typically retrieved via GET. |
| `307` | Temporary Redirect | Temporary redirection preserving the request method. |
| `308` | Permanent Redirect | Permanent redirection preserving the request method. |
| `304` | Not Modified | The representation has not changed relative to the validator sent by the client; the client may use its cached copy. This is a 3xx status, not a redirect to a different URI. |

Redirection statuses usually include a `Location` header, except `304` which has caching semantics. Automatic redirect following is configured on `HttpClient`; do not assume every redirect is safe or desirable.

### 2.3. Client error status codes

| Code | Name | Common situation |
|---:|---|---|
| `400` | Bad Request | Request syntax or submitted data is invalid. |
| `401` | Unauthorized | Missing or invalid authentication credentials; response often includes `WWW-Authenticate`. |
| `403` | Forbidden | The server understands the request but refuses to fulfill it due to permissions or policy. |
| `404` | Not Found | The requested resource was not found, or the server declines to reveal its existence. |
| `405` | Method Not Allowed | The HTTP method is not supported for the resource; may include an `Allow` header. |
| `409` | Conflict | The request conflicts with the current state of the resource, such as updating a stale version. |
| `412` | Precondition Failed | A header precondition such as `If-Match` was not satisfied. |
| `415` | Unsupported Media Type | The server does not support the format of the submitted body. |
| `422` | Unprocessable Content | Content syntax is valid, but cannot be processed under business rules. |
| `429` | Too Many Requests | The client sent too many requests within a time window; may include `Retry-After`. |

`401` and `403` are not synonymous: `401` relates to *authentication*, whereas `403` denies permission (*authorization/policy*). However, applications should not infer excessive internal details from status codes alone.

### 2.4. Server error status codes

| Code | Name | Meaning |
|---:|---|---|
| `500` | Internal Server Error | An unhandled internal error that was not mapped to a specific business response. |
| `501` | Not Implemented | The server does not support the functionality required to fulfill the request. |
| `502` | Bad Gateway | A gateway/proxy received an invalid response from upstream. |
| `503` | Service Unavailable | The server is temporarily unavailable, possibly due to maintenance or overload. |
| `504` | Gateway Timeout | A gateway/proxy did not receive a timely response from upstream. |

A `5xx` status does not prove that the business operation definitely did not occur. The server may have persisted data successfully before the connection dropped ahead of delivering the response to the client. For write operations, blind retries can create duplicate records. Design an idempotency key or status-checking mechanism per the API contract when needed.

## 3. HTTP Headers: Request and Response Metadata

Headers are metadata fields accompanying HTTP messages. They can describe content type, caching behavior, authentication info, request preconditions, redirects, or rate limits.

### 3.1. Request headers

| Header | Purpose | Example |
|---|---|---|
| `Accept` | Media types the client can accept. | `application/json` |
| `Content-Type` | Data type of the request body. | `application/json; charset=UTF-8` |
| `Authorization` | Authentication credentials per agreed scheme. | `Bearer ...` |
| `User-Agent` | Identifies the client application. | Application name and version |
| `If-None-Match` | Cache precondition based on ETag. | `"v17"` |
| `If-Match` | Update precondition based on current ETag. | `"v17"` |
| `Range` | Requests a portion of a representation. | `bytes=0-999` |

`Accept` and `Content-Type` are often confused:

- `Accept` answers: "What content type does the client want to **receive**?"
- `Content-Type` answers: "What content type **represents** the current body?"

For a bodyless GET, typically set `Accept`. For a POST sending JSON, set `Content-Type: application/json` and optionally also set `Accept: application/json`.

### 3.2. Response headers

| Header | Purpose |
|---|---|
| `Content-Type` | Media type and possibly charset of the body. |
| `Content-Length` | Body size in bytes if supplied. |
| `Content-Encoding` | Content encoding such as gzip if present. |
| `Cache-Control` | Caching directives. |
| `ETag` | Validator identifying the representation version. |
| `Last-Modified` | Timestamp when the representation was last modified. |
| `Location` | URI related to a newly created resource or redirect target. |
| `Retry-After` | Time or duration the client should wait before retrying. |
| `WWW-Authenticate` | Authentication challenge in a `401` response. |
| `Allow` | Methods supported by the resource, often seen with `405`. |
| `Vary` | Request headers that influence representation selection/caching. |
| `Set-Cookie` | Directive to store a cookie on the client. |

Headers are metadata, not business data replacing the body. For example, `ETag` helps a client check whether a representation changed, but does not contain the full resource content.

### 3.3. Header names are case-insensitive

Per HTTP, header names are case-insensitive. `Content-Type`, `content-type`, and `CONTENT-TYPE` refer to the same header. Header values, however, follow each field's own semantics; do not automatically assume every header value is case-insensitive.

A header can appear multiple times or carry multiple values. For example, `Set-Cookie` often has multiple distinct fields; do not blindly join them into a single comma-separated string. When reading headers, use APIs that return a list of values.

## 4. Reading Status and Headers with Java 17 HttpClient

Java 17 provides these main types:

- `HttpClient`: configures and sends requests; reuse a single client across multiple requests.
- `HttpRequest`: URI, method, headers, timeout, and body publisher for a request.
- `HttpResponse<T>`: status, headers, body, and metadata of the response.
- `HttpHeaders`: unmodifiable set of headers returned in the response.
- `BodyHandlers`: chooses how to receive and convert the body into the desired type.

### 4.1. Sending GET and reading the response

The following example uses a hypothetical public API returning UTF-8 JSON at a configured URI:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class ReadHttpResponse {
    private ReadHttpResponse() {
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/orders/42"))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "application/json")
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            int status = response.statusCode();
            System.out.println("Status: " + status);
            System.out.println("HTTP version: " + response.version());
            System.out.println("Final URI: " + response.uri());

            String contentType = response.headers()
                    .firstValue("Content-Type")
                    .orElse("(not provided)");
            System.out.println("Content-Type: " + contentType);

            if (status >= 200 && status < 300) {
                System.out.println("Response body:");
                System.out.println(response.body());
            } else {
                System.out.println("Request was not successful.");
                System.out.println("Error body:");
                System.out.println(response.body());
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "HTTP request was interrupted", exception);
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Could not complete HTTP request", exception);
        }
    }
}
~~~

Replace the example URI with an endpoint for a service you are authorized to call. Key points:

1. `HttpClient` is created once beforehand and can be reused across requests.
2. `connectTimeout` limits connection establishment time.
3. `HttpRequest.Builder.timeout` limits response wait time for the request.
4. `header("Accept", "application/json")` declares the media type the client wishes to receive.
5. `BodyHandlers.ofString(StandardCharsets.UTF_8)` decodes the body into a string using the specified charset.
6. `statusCode()` returns the integer status; the application decides which statuses count as success per endpoint contract.
7. `firstValue("Content-Type")` retrieves the first value if present; `orElse` provides a fallback when the header is absent.

The example uses UTF-8 assuming the API returns UTF-8 JSON. If an endpoint uses a different charset, determine the charset per contract and valid response metadata before decoding. `ofString(UTF_8)` does not automatically convert an arbitrary body into a JSON object.

### 4.2. Reading multiple values of the same header

`HttpHeaders` provides:

- `firstValue(name)`: `Optional<String>` containing the first value.
- `allValues(name)`: a list of all values for the header.
- `map()`: maps header names to lists of values.

~~~java
HttpHeaders headers = response.headers();

headers.firstValue("Content-Type")
        .ifPresent(value -> System.out.println("Type: " + value));

List<String> cookies = headers.allValues("Set-Cookie");
cookies.forEach(cookie -> System.out.println("Cookie: " + cookie));

headers.map().forEach((name, values) ->
        System.out.println(name + " = " + values));
~~~

Header names are handled case-insensitively. The map and lists in `HttpHeaders` are read-only per the API; you cannot use them to mutate a received response.

In particular, `Set-Cookie` can have multiple values and each cookie must be parsed according to its own rules. Do not join the list into a single comma-separated string and parse it generically.

## 5. Reading Response Bodies by Data Type

The body may be JSON, HTML, plain text, images, PDFs, archives, or binary data. Choosing the right body handler prevents misreading data or wasting memory.

| Body handler | Body type | When appropriate |
|---|---|---|
| `BodyHandlers.ofString(charset)` | `String` | JSON, HTML, or moderately sized text. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Small binary data or payloads processed by another library. |
| `BodyHandlers.ofFile(path)` | `Path` | Downloading content directly to a file. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Streaming data yourself and controlling stream closing. |
| `BodyHandlers.discarding()` | `Void` | Only need status/headers, no need to keep the body. |

### 5.1. Text bodies

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

String body = response.body();
~~~

Only use this when the body is reasonably sized. A large response will be buffered in memory as a single complete string.

### 5.2. Byte bodies

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();
~~~

Use this when receiving images or binary data. Do not blindly convert arbitrary bytes into a `String` assuming UTF-8; rely on media type and file format instead.

### 5.3. Downloading directly to a file

~~~java
Path destination = Path.of("download.bin");

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(destination));

System.out.println("Saved to: " + response.body());
System.out.println("Status: " + response.statusCode());
~~~

`ofFile` writes the body to the file as the response arrives. In real applications, check the status and storage policy before treating the file as a successful download; use a temporary path and move it to the final location after verification when the data is valuable.

### 5.4. Streamed bodies

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] buffer = new byte[8192];
    int bytesRead;
    while ((bytesRead = input.read(buffer)) != -1) {
        // Process each chunk of data.
    }
}
~~~

When using `ofInputStream`, the application must close the `InputStream`. Streaming is useful for large data, but requires careful management of resources, timeouts, and read errors. Remember that the body could still be an error payload for a `4xx` or `5xx` status.
## 6. Status Code and Body Must Be Read Together

A common mistake is inspecting the body as if the request always succeeded. In practice, many APIs return JSON error bodies with status `400`, `401`, `404`, or `500`. The body can be helpful for displaying messages or controlled logging, yet the status is what tells you the HTTP outcome category.

Handling example:

~~~java
static void handle(HttpResponse<String> response) {
    int status = response.statusCode();

    if (status >= 200 && status < 300) {
        System.out.println("Success: " + response.body());
    } else if (status >= 300 && status < 400) {
        System.out.println("Redirection");
        response.headers().firstValue("Location")
                .ifPresent(uri -> System.out.println("Location: " + uri));
    } else if (status >= 400 && status < 500) {
        System.out.println("Client-side response: " + status);
        System.out.println("Error details: " + response.body());
    } else if (status >= 500 && status < 600) {
        System.out.println("Server-side response: " + status);
    } else {
        System.out.println("Other HTTP status: " + status);
    }
}
~~~

This snippet is a classification skeleton. In real applications, each endpoint should define its expected statuses and how error bodies map to domain error types.

**Java HttpClient does not automatically throw IOException just because the status is `404` or `500`.** When the server returns a valid HTTP response, `send` still returns an `HttpResponse`; you must read `statusCode()` to tell success from an HTTP error. `IOException` generally indicates communication, connection, TLS, or read/write errors—not merely an error status.

### 6.1. Handling `204 No Content`

Do not invoke a JSON parser on an empty body:

~~~java
if (response.statusCode() == 204) {
    System.out.println("Operation completed without a response body.");
} else if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    // Parse body according to Content-Type and API contract.
}
~~~

### 6.2. Handling `201 Created`

When creating a resource:

~~~java
if (response.statusCode() == 201) {
    URI createdResource = response.headers()
            .firstValue("Location")
            .map(request.uri()::resolve)
            .orElse(null);

    System.out.println("Created resource: " + createdResource);
}
~~~

The `Location` header may be a relative URI; resolve it against the response/request URI per the API contract if needed. Do not assume this header is always present.

### 6.3. Handling `429 Too Many Requests`

When receiving `429`, inspect `Retry-After` if provided by the server:

~~~java
if (response.statusCode() == 429) {
    response.headers().firstValue("Retry-After")
            .ifPresent(value ->
                    System.out.println("Retry guidance: " + value));
}
~~~

The `Retry-After` value can represent either a number of seconds to wait or an HTTP date. Do not always parse it as an integer. When implementing retries, respect server limits, use capped backoff, and only retry safe operations or operations with appropriate idempotency guarantees.

## 7. Cache-Related Headers and Conditional Requests

HTTP supports caching to avoid re-downloading unchanged representations. Two common validators are `ETag` and `Last-Modified`.

### 7.1. `ETag` and `If-None-Match`

The server may return:

~~~text
HTTP/1.1 200 OK
ETag: "order-v42"
Content-Type: application/json
~~~

On a subsequent request, the client sends:

~~~text
If-None-Match: "order-v42"
~~~

If the representation has not changed, the server may return `304 Not Modified`. The client uses its cached representation instead of re-downloading the body.

In Java:

~~~java
HttpRequest cachedRequest = HttpRequest.newBuilder(uri)
        .header("If-None-Match", "\"order-v42\"")
        .GET()
        .build();

HttpResponse<String> response = client.send(
        cachedRequest,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() == 304) {
    System.out.println("Use the cached representation.");
} else if (response.statusCode() == 200) {
    // Update cache with new body and ETag.
}
~~~

This example illustrates the validator flow; real applications must store the representation and ETag together from the same cache entry, and adhere to `Cache-Control`, `Vary`, and the resource's cache policy.

### 7.2. `Last-Modified` and `If-Modified-Since`

`Last-Modified` indicates when the representation was last modified. The client can send `If-Modified-Since` on the next request. The server may return `304` if nothing changed since that time.

ETag is generally a stronger validator for identifying representation versions, whereas Last-Modified has server-dependent time resolution and semantics. Do not assume the two validators are always equivalent.

### 7.3. `Cache-Control` and `Vary`

- `Cache-Control: no-store` instructs not to store the response in caches under the corresponding policy.
- `Cache-Control: max-age=60` specifies a freshness lifetime of 60 seconds under HTTP semantics.
- `Vary: Accept-Language` indicates the representation may vary depending on the `Accept-Language` request header; caches must distinguish variants.

Clients should not cache every response simply because it returned `200`. Follow caching directives, privacy rules, and the API's data policy.

## 8. Redirects, Timeouts, and HTTP Version in HttpClient

### 8.1. Configuring redirects

`HttpClient` supports:

| Policy | Behavior |
|---|---|
| `Redirect.NEVER` | Never follow redirects automatically. |
| `Redirect.NORMAL` | Follow normal redirects, except downgrading HTTPS to HTTP. |
| `Redirect.ALWAYS` | Follow all redirects per client policy. |

Example:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

The default is not to follow redirects automatically. Choose a policy based on security requirements and endpoint behavior. When a redirect occurs, `response.uri()` gives the final URI; `previousResponse()` can give the preceding response if present.

Redirects can alter how a request is handled depending on status and method. Specifically, `307` and `308` require preserving the request method; `301`/`302` have historically varied across clients. For requests carrying a body or credentials, review redirect behavior carefully before enabling automatic following.

### 8.2. Connect timeout and request timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(4))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(12))
        .GET()
        .build();
~~~

- `connectTimeout` limits connection establishment time.
- `HttpRequest.timeout` limits waiting for a response to the request.
- Timeouts can throw `HttpTimeoutException`, which is a type of `IOException`.

A timeout is not an HTTP status code. If a request times out before the client receives a response, there may be no status or headers to read.

### 8.3. Choosing the HTTP version

`HttpClient.Builder.version` sets the preferred version:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

The client may negotiate or use another version depending on the server and environment. After receiving the response, inspect `response.version()` to learn the actual version used. Do not assume an HTTP/2 preference is always honored.

## 9. POSTing JSON and Reading Status, Headers, and Body

When sending a body, the `Content-Type` header describes the request body format. The following example sends UTF-8 JSON:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class CreateOrderRequest {
    private CreateOrderRequest() {
    }

    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "customerId": "CUST-01",
                  "itemCode": "BOOK-17",
                  "quantity": 2
                }
                """;

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/orders"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .header("Content-Type", "application/json; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        System.out.println("Status: " + response.statusCode());
        response.headers().firstValue("Location")
                .ifPresent(value -> System.out.println("Location: " + value));

        if (response.statusCode() == 201) {
            System.out.println("Order created:");
            System.out.println(response.body());
        } else {
            System.out.println("API response:");
            System.out.println(response.body());
        }
    }
}
~~~

The endpoint above is only an illustrative URI; replace it with the actual service API and payload contract. The example shows that the request body and response body are two distinct directions:

- `BodyPublishers.ofString` builds the request body from a string.
- `Content-Type` describes the body being sent.
- `BodyHandlers.ofString` decides how to read the response body.
- `Accept` indicates the response type the client wants.
- `statusCode()` and `headers()` must still be read separately to determine the result.

Do not interpolate untrusted data into JSON using `String.formatted()` or string concatenation without proper JSON escaping. In real applications, use a JSON serializer to produce the request body.

## 10. HTTP Errors and Transport Errors Are Two Different Categories

When calling `client.send(request, handler)`, you can encounter two groups of problems:

| Category | Example | Is there an `HttpResponse`? |
|---|---|---|
| Valid HTTP response with error status | `400`, `401`, `404`, `429`, `500` | **Yes.** Read status, headers, and error body. |
| Communication/transport error | DNS failure, connection refused, TLS handshake, timeout, body read error | May have **no complete response**; typically throws an exception. |
| Interrupted request | Thread interrupted while waiting for response | Throws `InterruptedException`; restore the interrupt flag when handling. |

Example:

~~~java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

    if (response.statusCode() >= 400) {
        // This is still an HTTP response.
        System.err.println("HTTP error: " + response.statusCode());
        System.err.println(response.body());
    }
} catch (HttpTimeoutException exception) {
    System.err.println("Request timed out: " + exception.getMessage());
} catch (IOException exception) {
    System.err.println("Transport or body I/O error: "
            + exception.getMessage());
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    System.err.println("Request interrupted");
}
~~~

Do not catch every exception and fabricate a fake status like `500`. When no response is received, the application does not know how far the server progressed with the request. Represent transport errors separately from HTTP errors and preserve cause details for retries and observability.

## 11. Security and Reliability When Reading Responses

### 11.1. Do not trust the body merely because the status is `200`

A response can contain malformed data, oversized payloads, missing fields, or data violating the API contract. Be sure to:

- Check `Content-Type` before parsing as a specific format.
- Validate structure and values after deserialization.
- Enforce body size limits suitable for the application.
- Handle incomplete or malformed data.
- Never render raw HTML or untrusted content directly in a UI without escaping.

`Content-Length` may be absent or is not the only way body size is determined; do not rely on it as your sole defense against oversized responses.

### 11.2. Do not log secrets in headers

Headers such as `Authorization`, `Cookie`, and `Set-Cookie` can contain tokens or session data. Do not dump the entire header map into production logs without redacting sensitive values.

Similarly, error response bodies may contain personal data, internal information, or system details. Limit logged content, mask sensitive information, and avoid echoing raw error messages to end users.

### 11.3. Handle redirects cautiously

Redirecting to a different host can cross a trust boundary. Do not forward credentials or sensitive headers indiscriminately. Restrict target hosts, require HTTPS where appropriate, and verify `HttpClient` policies.

### 11.4. Conditional retries

Not every request should be retried:

- GET is generally safer to retry because it is designed not to change server state.
- PUT and DELETE have idempotent semantics in HTTP, though applications must still account for how the endpoint is implemented.
- POST is typically not idempotent; retrying can create duplicate resources if the first attempt succeeded but the response was lost.
- For `429` or `503`, check `Retry-After`, apply capped backoff, and avoid adding extra load when the service is already overloaded.

When the API supports an idempotency key, reuse the same key across retries of the same logical operation per the service contract.

## 12. Practice Exercises

### Exercise 1 — Classify statuses

Given codes `200`, `201`, `202`, `204`, `301`, `304`, `400`, `401`, `403`, `404`, `409`, `429`, `500`, and `503`, group them into status categories and describe which headers or body the application should inspect.

### Exercise 2 — Reading multi-valued headers

Make a request to a test endpoint that can return multiple `Set-Cookie` headers. Use `allValues("Set-Cookie")` to print the count and each value. Ensure real cookie tokens are never written to shared logs.

### Exercise 3 — Handling bodyless responses

Write a method handling a DELETE result. When the status is `204`, return a success message without calling a JSON parser. For error statuses, record the status and error body if present.

### Exercise 4 — Cache validators

Simulate a `200` response carrying an `ETag`. Send a follow-up request with `If-None-Match`. Describe how to handle `304` and why its body should not be parsed as fresh JSON.

### Exercise 5 — Distinguishing transport errors

Call an unreachable URI or set a very short timeout. Catch `IOException`/`HttpTimeoutException` and compare with a case where the server returns `404`. Explain why `404` still yields an `HttpResponse`.

### Exercise 6 — Reading Content-Type

Receive a response with a `Content-Type` header. Print the media type and charset if present. Test with `application/json; charset=UTF-8` and a response without a declared charset. State how to pick a decoder according to the API contract.

## 13. Workflow for Reading a Response in an Application

A processing flow applicable to many endpoints:

1. Send the request with appropriate `Accept` and `Content-Type` headers.
2. Configure connect timeout and request timeout aligned with SLAs.
3. Receive `HttpResponse` using a body handler matching the data type.
4. Read `statusCode()` before assuming the body has a success shape.
5. Read relevant headers: `Content-Type`, `Location`, `Retry-After`, `ETag`, or agreed business headers.
6. Distinguish success, redirection, client error, and server error statuses.
7. Parse the body only according to the media type and endpoint contract; handle bodyless statuses separately.
8. Separate HTTP errors from transport errors and interruption.
9. Retry only when allowed by method, idempotency, and server guidance.
10. Redact sensitive data before logging.

## 14. Key Principles to Remember

- An HTTP response has a status code, headers, and optionally a body.
- `2xx` indicates success, but `200` is not the only success status; `201`, `202`, `204`, and `206` have distinct semantics.
- `4xx` usually indicates request/permission/resource-state issues; `5xx` usually indicates server or gateway errors.
- `Accept` states what response type the client wants; `Content-Type` states the body type of the current message.
- Header names are case-insensitive; a single header can have multiple values.
- `HttpResponse.statusCode()` returns the numeric status; `headers()` reads metadata; `body()` has a type determined by the body handler.
- `4xx`/`5xx` do not automatically make `HttpClient.send` throw an exception. They are still valid responses.
- `IOException`/`HttpTimeoutException` and `InterruptedException` are communication/execution conditions distinct from HTTP statuses.
- HttpClient's default redirect policy does not follow redirects automatically; configure it intentionally.
- `204` and `304` do not supply a fresh body representation to parse as JSON.
- Text/bodies are untrusted; enforce size limits, validate data, and protect sensitive information.
- Retries must consider idempotency and `Retry-After`; never blindly retry POST or write operations.

### References

- [Java SE 17 API — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 17 API — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html).
- [Java SE 17 API — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Java SE 17 API — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111).
