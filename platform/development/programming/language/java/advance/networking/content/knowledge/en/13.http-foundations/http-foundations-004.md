# Status Code Groups 2xx, 3xx, 4xx, 5xx and Distinguishing Them from Connection Errors in HTTP

**Topic:** Java Advance - networking  
**Knowledge Group:** HTTP Foundations

When a Java client calls an HTTP API, there are **two completely different kinds of outcomes**:

1. **Receiving an HTTP response** with a **status code** such as **200**, **302**, **404**, **429**, or **503**. This means at least one HTTP component (origin server, reverse proxy, API gateway, cache...) generated a response that the client received and could process. The response may indicate success, redirection, or failure at the HTTP/application layer.
2. **Failing to obtain a complete HTTP response per the client API in use**, due to DNS, TCP connect, TLS handshake, timeout, closed connection, protocol error, request cancellation, or body read error. This case is typically reported via an **exception** or an exceptionally completed future, **with no reliable HTTP status code for classification**.

**HTTP 404 and TCP Connection refused are not the same**. **HTTP 504 Gateway Timeout and HttpTimeoutException are not the same either**. This is the most important boundary when designing retries, operational observability, error handling, and user-facing messages.

This lesson explains the meaning of **2xx / 3xx / 4xx / 5xx**, commonly confused cases such as **204**, **304**, **401/403**, **408/429**, **502/503/504**, and a Java 17 example using **HttpClient** together with an HTTP server running on loopback for self-verification.

## 1. Status codes only exist when there is an HTTP response

An illustrative HTTP/1.1 response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2
Content-Length: 26

{"error":"maintenance"}
~~~

Here, **503** is an **HTTP status code** (sent by a server/proxy/gateway). **Retry-After: 2** suggests waiting at least 2 seconds before retrying in an appropriate context; it does **not** mean TCP failed to connect. HTTP/2 and HTTP/3 encode responses using mechanisms different from HTTP/1.1 (for example, HTTP/2 has the **:status** field), but the meaning of 2xx/3xx/4xx/5xx codes is still based on HTTP semantics.

Placing the layers side by side:

~~~text
Java Client
   │
   ├── DNS lookup ── cannot resolve ──> DNS error/IOException
   │
   ├── TCP connect ── refused/timeout ────> connection error/IOException
   │
   ├── TLS handshake (HTTPS)
   │       └── cert/hostname/protocol error -> SSLException
   │
   ├── Send HTTP request
   │
   ├── Receive HTTP response headers
   │       ├── status 2xx: Success class
   │       ├── status 3xx: Redirection class
   │       ├── status 4xx: Client Error class
   │       └── status 5xx: Server Error class
   │
   └── Receive HTTP body
           └── connection dropped/read error -> I/O exception may
                occur even if status was seen at a lower layer
~~~

**Subtle point:** An HTTP client calling the synchronous **send(...)** API can encounter an **IOException while receiving the body**, even though the response headers were already received underneath. When **send(...)** throws an exception, the caller does not receive a complete **HttpResponse** object from that call to reliably handle the status. You should not conclude "the server did not respond at all" in every exception case; whether the request was received/processed by the server or not may be **unknown**.

### Five status classes by leading digit

| Class | HTTP Class Name | Protocol-level interpretation | Application examples |
| --- | --- | --- | --- |
| **1xx** | Informational | Informational/intermediate response; usually not the final response | 100 Continue, 101 Switching Protocols, 103 Early Hints |
| **2xx** | Successful | The HTTP request was received, understood, and successfully processed according to the code's meaning | 200, 201, 202, 204, 206 |
| **3xx** | Redirection | Further action is needed or possible to complete the request/condition | 301, 302, 303, 304, 307, 308 |
| **4xx** | Client Error | The request has an issue or cannot be fulfilled under the client/request conditions | 400, 401, 403, 404, 409, 412, 429 |
| **5xx** | Server Error | The server/gateway failed to fulfill a valid request or encountered a processing issue | 500, 501, 502, 503, 504 |

A status code is a **three-digit number**. For example in Java:

~~~java
int status = response.statusCode(); // response is the received HttpResponse<?>.
int family = status / 100;           // 2, 3, 4, 5 (or 1).
boolean httpSuccessClass = family == 2;
~~~

This is a **snippet** that requires the **response** variable; it **does not run standalone**. Division by 100 classifies the group, not whether business logic completed. The HTTP status list is extensible by standards and applications may use other registered codes; do not just write a **switch** for 200/404/500 and default every other code to a transport failure.

## 2. The 2xx group: success at the HTTP layer, but meaning depends on each code

Do not equate every **2xx** with "all business work is complete". Always check **method, status, headers, body, and the API contract**.

| Code | Name | Primary meaning | How to handle |
| --- | --- | --- | --- |
| **200 OK** | OK | Request succeeded according to the method's semantics; usually has a representation/body | Parse content according to Content-Type and contract; GET/POST may carry different meanings |
| **201 Created** | Created | Request created one or more resources | Check **Location** if the server provides the new resource's URI |
| **202 Accepted** | Accepted | Accepted for processing, **not guaranteed that processing has completed** | Track job/status URL or callback per contract |
| **204 No Content** | No Content | Request succeeded, **no response content** | Do not force JSON parsing on an empty body |
| **206 Partial Content** | Partial Content | Server returns part of a representation for a matching range request | Check **Content-Range**, reassemble per protocol, do not treat as the entire file |
| **207 Multi-Status** | Multi-Status (WebDAV) | May contain statuses of multiple operations/resources | Read body structure per WebDAV protocol; a single 2xx does not guarantee every part succeeded |

### 200 OK is not always "business success"

A server can return **200 OK** with JSON such as:

~~~json
{
  "success": false,
  "errorCode": "OUT_OF_STOCK",
  "message": "Item cannot be reserved"
}
~~~

This is still **HTTP 200** at the status level. An application wanting to determine whether the order succeeded must **read the body contract**. Some APIs intentionally represent domain errors with 200; this can make status-based observability harder, yet the client must still handle the actual contract properly.

On the other hand, a server may return **201 Created** where the client must use **Location** to find the new resource, or return **202 Accepted** when a new job has only entered a queue. You should not report "processing complete" immediately upon seeing 202, unless the contract explicitly specifies so.

### 204: success with no body

With **204 No Content**, the response contains no content, regardless of whether the client expects JSON. A common mistake:

~~~java
// Buggy pseudocode: API returns 204 but code still forces JSON parsing.
if (response.statusCode() == 204) {
    parseJson(response.body()); // No JSON to parse.
}
~~~

Instead, when 204 is a valid result, handle the **no-body** branch and update application state per the contract. **HEAD** also returns response headers without a response body; therefore "no body" is not synonymous with an exception.

### 206: partial success

**206 Partial Content** is commonly encountered when downloading with **Range**. It differs from **200**, which returns the full representation. When downloading a large file in parts, you must verify **Content-Range**, length, and representation identity (e.g., ETag/If-Range) to avoid corrupting assembled data. 206 is not a kind of "connection error that happened mid-transfer"; it is an intentional HTTP response.

## 3. The 3xx group: redirection or conditional handling, not every code means "go to another URL"

| Code | Name | Meaning and notes |
| --- | --- | --- |
| **300 Multiple Choices** | Multiple Choices | Multiple representations/options exist; the client may need to choose |
| **301 Moved Permanently** | Moved Permanently | Resource has a different permanent address; many clients cache the redirect |
| **302 Found** | Found | Resource temporarily resides at another URI; historically clients may change POST to GET in some cases |
| **303 See Other** | See Other | Directs the client to retrieve another resource, typically via GET (except HEAD per rules) |
| **304 Not Modified** | Not Modified | Answers a conditional request: cached representation is still valid; **no response body** and **not an instruction to go to another URL** |
| **307 Temporary Redirect** | Temporary Redirect | Temporary redirect; the client **must not change the method** when auto-following |
| **308 Permanent Redirect** | Permanent Redirect | Permanent redirect; the client **must not change the method** when auto-following |

### Location and redirect policy

Example:

~~~http
HTTP/1.1 302 Found
Location: /v2/catalog
Content-Length: 0
~~~

The client can:

1. Return the raw **302** to the application so the application decides.
2. Automatically follow the redirect according to its **redirect policy** and return the **final response**, for example **200**, to the application.
3. Stop due to too many redirects, blocked scheme, redirect loop, security constraints, or a network error when accessing the new target.

**Java HttpClient** provides **HttpClient.Redirect.NEVER**, **NORMAL**, and **ALWAYS**. With **NEVER**, the application sees status 302 if the server returns 302; with **NORMAL**, the client can automatically follow allowed redirects and return the final status. **NORMAL** does not automatically allow downgrading from HTTPS to HTTP. Do not use **ALWAYS** while ignoring credential/security policies; redirecting across different domains requires evaluating tokens, cookies, and sensitive information.

**It is not guaranteed** that every 301/302 redirect preserves the method/body when the client auto-follows: historical rules allow certain POST → GET conversions. **307/308** were created to preserve the method when following. For requests with side effects, you must understand both client and server policies and avoid resending bodies blindly.

### 304 Not Modified is neither an error nor a response with a body

A client sends a conditional GET:

~~~http
GET /logo.png HTTP/1.1
If-None-Match: "v7"
~~~

The server may return **304 Not Modified**, meaning the cached representation is still valid. The client/browser can reuse the cached content per caching rules. **304 does not mean "the server stopped working"**; a client without a cache or one that does not handle conditional requests properly may encounter unexpected results. In Java **HttpResponse**, receiving 304 does not automatically supply the cached representation unless an appropriate cache layer handles it.

Do **not** attempt to parse a JSON body for 304; this is a code that contains no response content per HTTP semantics.

### A failed redirect along the way is still a connection error

If server A returns 302 pointing to server B, but DNS for B fails, a **client that auto-follows** may throw an exception. That is **different** from server A returning an HTTP 5xx. To diagnose accurately, log the redirect chain/target and the error type at the failed hop, rather than imposing a single status code on the entire journey.

## 4. The 4xx group: request/client has an issue or does not meet conditions

"Client Error" in the class name does **not** always mean a programming bug on the client side. It can be permissions, resource state, throttling, validation, or an explicit policy enforced by the server.

| Code | Name | When encountered | Appropriate action |
| --- | --- | --- | --- |
| **400** | Bad Request | Request syntax, framing, or certain parameters are invalid | Fix the request, schema, or serialization |
| **401** | Unauthorized | Valid authentication credentials are missing for the resource | Check **WWW-Authenticate**, refresh/login per protocol |
| **403** | Forbidden | Server understands the request but refuses to fulfill it | Check permissions, policy, tenant; do not retry blindly |
| **404** | Not Found | Resource does not exist at this URI or server does not wish to disclose it | Check path, ID, version; some APIs treat 404 as a valid outcome |
| **405** | Method Not Allowed | Method is not supported for the resource | Check the **Allow** header when appropriate; change method per contract |
| **408** | Request Timeout | Server did not receive a complete request within the time it was prepared to wait | Different from client-reported timeout; evaluate safe retry |
| **409** | Conflict | Current state conflicts with the operation | Refresh version/state and resolve the conflict |
| **410** | Gone | Resource is no longer available, intentionally | Do not repeat requests indefinitely; update references |
| **412** | Precondition Failed | Precondition such as If-Match was not met | Re-read ETag/version, handle optimistic concurrency |
| **413** | Content Too Large | Request content exceeds accepted limit | Adjust payload/chunking if the API supports it |
| **415** | Unsupported Media Type | Content-Type/representation is not supported | Send a format supported by the API |
| **422** | Unprocessable Content | Syntax/content type is understood, but content cannot be processed | Check business validation errors |
| **425** | Too Early | Server is unwilling to risk processing a request that might be replayed (TLS early data context) | Retry after full handshake per safety policy |
| **429** | Too Many Requests | Too many requests under rate-limit policy | Respect Retry-After if present, slow down, apply backoff and quota |

### 401 differs from 403

- **401**: usually missing valid credentials or re-authentication is needed; the response typically carries **WWW-Authenticate** per HTTP authentication.
- **403**: the server refuses to fulfill the request even though it understood it; resending the same credentials repeatedly will not make it succeed.

An API may use 404 to **avoid disclosing resources the caller has no permission to know about**. Therefore, the status only states what the server chooses to expose over HTTP; it is not absolute proof of internal state.

### 409, 412 are not like a broken connection

Optimistic locking example: the client updates a resource with **If-Match: "v3"**, the server is already at version **v4** and returns **412**. TCP and TLS can be completely healthy. **Retrying immediately with the same payload/ETag** will repeat the error. You must re-read the resource, merge, or report the conflict to the user according to business requirements.

### 408 and 429 relate to timeout/rate limit but are still HTTP statuses

**408 Request Timeout** is a server response, reflecting that the server did not receive a complete request fast enough under its conditions. **429 Too Many Requests** reflects rate limiting. Both are 4xx and can be handled via retry policies, but they do **not** mean a **SocketTimeoutException** or **HttpTimeoutException** occurred on the client.

**Retry-After** is a header designed to convey wait time; its value can be a **non-negative integer of seconds** or an **HTTP-date**. It commonly appears on 429/503 and may appear under other semantics. Do **not** assume the header is always present, always numeric, or expressed in milliseconds.

## 5. The 5xx group: server or gateway encountered a problem while processing

| Code | Name | Approximate meaning | Do not confuse with |
| --- | --- | --- | --- |
| **500** | Internal Server Error | Server encountered an error condition preventing it from fulfilling the request | "Broken TCP": an HTTP response was still received here |
| **501** | Not Implemented | Server does not support the functionality/method required to fulfill the request | 405 Method Not Allowed on a specific resource |
| **502** | Bad Gateway | Proxy/gateway received an invalid response from upstream | Client directly encountering Connection refused |
| **503** | Service Unavailable | Server is temporarily unable to handle the request due to overload, maintenance, or similar | 429 is typically throttling per request/client policy |
| **504** | Gateway Timeout | Proxy/gateway did not receive a timely response needed from upstream | **HttpTimeoutException** detected by the client itself |
| **505** | HTTP Version Not Supported | Server does not support the HTTP version used in the request | TLS protocol version error during handshake |

**5xx does not necessarily originate from the origin service.** A reverse proxy/API gateway/CDN can generate **502**, **503**, or **504**, even when the backend application sends no response. When debugging, distinguish gateway-generated statuses from backend-returned statuses using logs/trace IDs and metrics at each hop, not just by looking at the body.

**5xx does not prove the request caused no side effect.** For example, a POST creating a transaction already committed to the database, but the server failed while building the response and returned **500**; or the connection dropped after commit. If the client retries without an idempotency key, it can create a duplicate transaction. "Server Error" describes the HTTP response, **not** a rollback certificate.

### 502 and 504 are often misclassified

- **502 Bad Gateway**: gateway/proxy received an invalid response from upstream while serving the request.
- **504 Gateway Timeout**: gateway/proxy did not receive a timely appropriate response from upstream.
- **Client HttpTimeoutException**: **the HTTP client itself** exceeded its timeout; the gateway may not have returned 504 yet, or the request may have reached the backend.
- **TCP connect timeout** from client to gateway: the client has not established a connection yet; it does not automatically turn into a 504.

If there are multiple proxies/hops, a timeout at one layer can be **translated into a 504** by another layer. **The 504 status you receive** is the output of an intermediary HTTP system, whereas a timeout exception is the client's own evaluation against its own deadline.

### 503 and Retry-After

**503 Service Unavailable** is often temporary. If the server includes **Retry-After**, the client can schedule a retry **if** the method/operation is appropriate and the deadline allows. If the header is absent, use backoff+jitter and cap attempts. Do not retry all clients simultaneously as soon as 503 is received, as that easily worsens an overloaded system.

## 6. Direct distinction: HTTP status vs. connection/I/O errors

This table determines how you must log and handle the two separate branches:

| Phenomenon | Is there an HTTP status code from this call? | Java or network example | Meaning |
| --- | --- | --- | --- |
| HTTP 200 | Yes: **200** | **response.statusCode() == 200** | HTTP success per semantics |
| HTTP 404 | Yes: **404** | **response.statusCode() == 404** | Server does not provide a resource at that URI |
| HTTP 429 | Yes: **429** | **response.statusCode() == 429** | Rate limit, may include Retry-After |
| HTTP 503 | Yes: **503** | **response.statusCode() == 503** | Server/gateway returned Service Unavailable |
| HTTP 504 | Yes: **504** | **response.statusCode() == 504** | Gateway reported upstream timeout |
| DNS failure | No reliable HTTP status from the request | **UnknownHostException** or IOException with matching cause | Destination could not be resolved (or DNS resolver error) |
| TCP Connection refused | No | **ConnectException** / IOException | Could not connect to IP:port; no listener accepting or rejected by policy |
| TCP connect timeout | No | **HttpConnectTimeoutException** on HttpClient depending on situation | Timed out while establishing connection |
| TLS handshake/hostname failure | No normal HTTP response | **SSLHandshakeException**, **SSLException** | Could not establish/verify a valid TLS channel |
| Client-side HTTP request timeout | No complete **HttpResponse** returned by send | **HttpTimeoutException** | Client proactively expired wait per request timeout |
| Server closes connection mid-response | Headers may have arrived at network layer, but send API may still throw exception | **IOException**, EOF/protocol exception | Must not infer that the server did not process the request |
| Thread interrupted | No response returned from interrupted send call | **InterruptedException** | Client-side cancellation/interruption; must restore interrupt flag |
| Async future failed/cancelled | No successful HttpResponse from that future | **CompletionException**, **CancellationException**, related cause | Classify by cause, not by a fake status |

**Note on exception types:** The Java HTTP client may **wrap** causes, especially in asynchronous pipelines; exact subclasses/causes depend on failure timing, JDK, and code path. Do not treat exception names in the table as a guarantee that every failure of that kind will always throw one exact class.

### Why "status = 0" is not a good way to represent a network error

Some frameworks use **0**, **-1**, or a custom code to represent "no HTTP response". This is merely an **internal framework convention**, not an HTTP status code in 2xx/3xx/4xx/5xx. If you turn every exception into **status 500**, observability loses the ability to distinguish "server returned 500" from "client could not connect".

A clearer model:

~~~text
HttpOutcome
 ├─ ResponseReceived
 │    ├─ status: 200 / 404 / 503 / ...
 │    ├─ headers, body, final URI
 │    └─ response timing
 └─ TransportOrClientFailure
      ├─ phase: dns/connect/tls/request/response/cancel (if determinable)
      ├─ exception / cause
      └─ did the request reach the server? possibly UNKNOWN
~~~

It is not always possible to distinguish the exact phase from the exception. Details like hostname, request ID, redirect target, phase trace, timeout policy, and network logs help reach a firmer conclusion.

## 7. 408, 429, 503, 504, and client-side timeouts: all feel "slow" but differ in nature

| Outcome | Who reports the problem? | What actually happened at the observation level? | Retry? |
| --- | --- | --- | --- |
| **408 HTTP** | HTTP server | Server sent status because it took too long to receive the complete request | Consider idempotency and request state |
| **429 HTTP** | Server/gateway/rate limiter | Server returned status due to quota/rate limit | Usually backoff and respect Retry-After |
| **503 HTTP** | Server/gateway | Server/gateway returned temporarily unavailable status | Controlled retry possible |
| **504 HTTP** | HTTP gateway | Gateway returned status because upstream did not respond in time | Retry possible, but check duplicate risk |
| **HttpConnectTimeoutException** | Java client | Timed out establishing HTTP connection | Check endpoint/network and retry with limits |
| **HttpTimeoutException** | Java client | Request exceeded configured timeout; could be at various stages | Cannot be sure server did not process it |
| **SSLHandshakeException** | Java TLS layer | TLS handshake verification/negotiation failed | Do not retry blindly on trust/hostname misconfiguration |

For example, a **POST /payments** request may have reached the server and written to the database, yet the client throws **HttpTimeoutException** while waiting for the response. Retrying immediately could create a second payment. In this case, **idempotency key + transaction status lookup** matters more than just choosing a backoff.

**Distinguishing Java timeout configurations:**

- **HttpClient.Builder.connectTimeout(Duration)** limits connection establishment time when a new connection is needed; it is not an absolute timeout for the entire request/response and may not apply when reusing an existing connection.
- **HttpRequest.Builder.timeout(Duration)** sets a deadline for the request/response per the API; if exceeded, **HttpTimeoutException** (or a subclass) may be thrown.
- **Response Timeout** in some other frameworks may be a per-byte read timeout or full-body timeout; do **not** assume semantics identical to Java's HttpClient just because it is also called a timeout.

Seeing only "elapsed 10s" is not enough to know whether DNS, TCP, TLS, backend, or body reading took the time. To conclude, you need per-phase telemetry and a request/trace ID to correlate with server logs.

## 8. Java HttpClient 17+: reading status without turning 4xx/5xx into exceptions

With **java.net.http.HttpClient**, the common synchronous usage is:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items/42"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

int code = response.statusCode();
if (code >= 200 && code < 300) {
    // Success by HTTP class; need to evaluate method + API contract.
} else if (code >= 300 && code < 400) {
    // Redirect or conditional semantics (e.g., 304).
} else if (code >= 400 && code < 500) {
    // Client/request/permission/rate-limit outcome at the HTTP layer.
} else if (code >= 500 && code < 600) {
    // Server/gateway HTTP outcome.
}
~~~

This is a **snippet** requiring imports for **java.net.URI**, **java.net.http.HttpClient/HttpRequest/HttpResponse**, **java.time.Duration**, and a pre-created **client** variable; it is **not** a standalone program. **send(...)** does not throw an exception just because the status is 404 or 503. Those statuses are inside **HttpResponse** if the response is received/read successfully per the BodyHandler.

**Difference from the older HttpURLConnection:** **HttpURLConnection.getInputStream()** can throw an IOException when the server returns an HTTP error status, and code needs to handle **getResponseCode() / getErrorStream()**. Do not infer from the older API's behavior that **HttpClient.send(...)** also throws an exception by default for every 4xx/5xx. When using another HTTP library, read its contract: some libraries convert non-2xx into exceptions by design.

### Catching exceptions by appropriate type

~~~java
// Snippet: client and request are already created; catch subclasses first.
try {
    HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    System.out.println("HTTP status: " + response.statusCode());
} catch (java.net.http.HttpConnectTimeoutException e) {
    // Connect timeout; no response status from this send call.
} catch (java.net.http.HttpTimeoutException e) {
    // Request timeout; cannot assert the server did not process the request.
} catch (javax.net.ssl.SSLHandshakeException e) {
    // TLS certificate, hostname, protocol, or trust failure...
} catch (java.io.IOException e) {
    // DNS/connect/reset/broken stream/protocol... depending on cause.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Respect cancellation/shutdown.
}
~~~

This snippet **illustrates error handling** and does not run standalone without the client/request variables. A DNS error may appear through the **IOException cause chain**; there is no need to force every error into a top-level **UnknownHostException**. When using **sendAsync(...)**, exceptions are typically propagated through **CompletableFuture** (for example **CompletionException** on join) and need their cause unwrapped; the classification of HTTP status vs. network error remains unchanged.

### Redirects change the status the application sees

~~~java
HttpClient noRedirect = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER).build();

HttpClient withRedirect = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL).build();
~~~

Sending the same request to an endpoint returning 302: **noRedirect** can return **302**; **withRedirect** can automatically call the URI in Location and return the target's **200**. This is a **policy** difference, not two servers having different HTTP semantics. The demo verifies this exact behavior in the next section.

## 9. Complete Java 17+ example: receiving status groups and a real timeout

The example below runs a **local HTTP server on 127.0.0.1 with an OS-assigned port**, requiring no Internet connection. The server creates endpoints representing:

- **2xx:** 200 OK, 201 Created with Location, 204 No Content.
- **3xx:** 302 Found with Location and 304 Not Modified.
- **4xx:** 400 Bad Request, 404 Not Found, 409 Conflict, 429 Too Many Requests with Retry-After.
- **5xx:** 500 Internal Server Error, 503 Service Unavailable.
- **Automatic redirect:** the same 302 URI but with policy NORMAL receives final status 200.
- **Error with no HTTP response:** endpoint **/slow** delays processing past the request timeout, causing **HttpClient.send(...)** to throw **HttpTimeoutException**, instead of returning a 408/504 status.

Every response uses **HttpResponse.statusCode()** for grouping. The status codes are **concrete, deterministic numbers generated by the demo server**; timeout behavior can depend on scheduling/runtime, but the example uses a large gap between an 800ms sleep and a 150ms request timeout to verify that branch under normal running conditions.

### Source code: HttpStatusDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpStatusDemo {
    record Example(String path, int expected) {}

    private static String family(int code) {
        return switch (code / 100) {
            case 1 -> "1xx";
            case 2 -> "2xx";
            case 3 -> "3xx";
            case 4 -> "4xx";
            case 5 -> "5xx";
            default -> "other";
        };
    }

    private static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            String path = exchange.getRequestURI().getPath();
            int code = switch (path) {
                case "/ok" -> 200;
                case "/created" -> 201;
                case "/empty" -> 204;
                case "/redirect" -> 302;
                case "/unchanged" -> 304;
                case "/bad" -> 400;
                case "/missing" -> 404;
                case "/conflict" -> 409;
                case "/rate" -> 429;
                case "/error" -> 500;
                case "/busy" -> 503;
                case "/slow" -> 200;
                default -> 404;
            };

            if (code == 201) {
                exchange.getResponseHeaders().set("Location", "/resources/42");
            }
            if (code == 302) {
                exchange.getResponseHeaders().set("Location", "/ok");
            }
            if (code == 429) {
                exchange.getResponseHeaders().set("Retry-After", "2");
            }
            if (code == 503) {
                exchange.getResponseHeaders().set("Retry-After", "1");
            }

            if (path.equals("/slow")) {
                try {
                    Thread.sleep(800);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
            if (code == 204 || code == 304 || code == 302) {
                exchange.sendResponseHeaders(code, -1);
                return;
            }

            byte[] body = ("status=" + code).getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(code, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        }
    }

    private static HttpRequest request(URI base, String path) {
        return HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(2))
                .GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        server.createContext("/", HttpStatusDemo::handle);
        server.start();
        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/");
            HttpClient noFollow = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            Example[] cases = {
                new Example("/ok", 200),
                new Example("/created", 201),
                new Example("/empty", 204),
                new Example("/redirect", 302),
                new Example("/unchanged", 304),
                new Example("/bad", 400),
                new Example("/missing", 404),
                new Example("/conflict", 409),
                new Example("/rate", 429),
                new Example("/error", 500),
                new Example("/busy", 503)
            };
            for (Example sample : cases) {
                HttpResponse<String> response = noFollow.send(
                        request(base, sample.path()),
                        HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() != sample.expected()) {
                    throw new AssertionError("Unexpected HTTP status: " + sample.path());
                }
                System.out.println(sample.path() + "="
                        + response.statusCode() + " " + family(response.statusCode()));
                if (sample.path().equals("/rate")) {
                    System.out.println("retryAfter429=" +
                            response.headers().firstValue("Retry-After").orElse("absent"));
                }
            }

            HttpClient follow = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();
            HttpResponse<String> redirected = follow.send(
                    request(base, "/redirect"), HttpResponse.BodyHandlers.ofString());
            System.out.println("followedRedirectStatus=" + redirected.statusCode());

            HttpRequest slow = HttpRequest.newBuilder(base.resolve("/slow"))
                    .timeout(Duration.ofMillis(150)).GET().build();
            try {
                noFollow.send(slow, HttpResponse.BodyHandlers.ofString());
                throw new AssertionError("Expected timeout");
            } catch (HttpTimeoutException expected) {
                System.out.println("timeoutWasHttpResponse=false");
                System.out.println("timeoutWasException=true");
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

**About the environment:** **com.sun.net.httpserver.HttpServer** is a demo/testing HTTP server located in the **jdk.httpserver** JDK module, not a default production server. On a standard full JDK, the program compiles directly; if using a stripped-down JDK/runtime without **jdk.httpserver**, that module must be supplied. **java.net.http.HttpClient** is the standard HTTP client since Java 11; the record and switch expression syntax here is compatible with **Java 17**.

### Compile and run

~~~bash
javac --release 17 -encoding UTF-8 HttpStatusDemo.java
java HttpStatusDemo
~~~

**Stdout of a successful run** — compiled with **--release 17** and tested on **JDK 24**:

~~~text
/ok=200 2xx
/created=201 2xx
/empty=204 2xx
/redirect=302 3xx
/unchanged=304 3xx
/bad=400 4xx
/missing=404 4xx
/conflict=409 4xx
/rate=429 4xx
retryAfter429=2
/error=500 5xx
/busy=503 5xx
followedRedirectStatus=200
timeoutWasHttpResponse=false
timeoutWasException=true
~~~

### Analyzing what the demo shows

1. **HttpServer** binds to loopback port **0**, so the OS assigns an available port; the client builds its URI from **server.getAddress().getPort()**. There is no hardcoded port causing test conflicts.
2. **noFollow** receives status **302** itself, whereas **follow** automatically follows to **/ok** and receives **200**. The status seen by the application depends on the redirect policy.
3. **/empty** returns **204** without sending a response body. **/unchanged** returns **304**; both are valid HTTP responses, not I/O errors.
4. **/rate** returns **429** and **Retry-After: 2**; the client still receives it normally as an **HttpResponse**, reading the header via **response.headers().firstValue(...)**.
5. **/error** and **/busy** return **500** and **503**, respectively. **HttpClient.send(...)** does not throw an exception just because the HTTP class is 5xx.
6. **/slow** causes the request to time out on the client before the HTTP response completes. **catch(HttpTimeoutException)** proves this is an **exception**, not HTTP **408** or **504**. The server may still execute the handler internally, so you must not infer that the request was aborted.
7. The example uses **GET** and tiny response bodies to focus on status semantics. In real applications, configure HTTPS, trust policy, timeouts, method/idempotency, logging, limits, and body handling per the API contract.

**Do not infer that all networks always have the same timing:** if a machine is heavily overloaded or the test environment is unusual, timeouts may manifest at different points; this example illustrates **distinguishing outcome types properly**, not latency benchmarking. To test ConnectException, use an environment/network fixture with a controlled non-listening endpoint; do not rely on "pick a free port then close it" as a race-free assumption in production tests.

## 10. Retry rules: do not rely solely on status or solely on exception

**Retrying is not "always retry 5xx, always skip 4xx".** Base the decision on:

1. **Method and semantics:** is the request safe/idempotent per HTTP and the **actual business contract**?
2. **Known outcome:** was a clear HTTP response received or only an exception? What might the server have already done?
3. **Cause:** does 429/503 include Retry-After? Is 502/504 from a gateway? Is DNS/TLS a misconfiguration or temporary?
4. **Deadline/cadence:** how much time remains? Max retry attempts? Exponential backoff + jitter?
5. **Idempotency protection:** is there an idempotency key, unique business ID, or status inquiry API to prevent duplicates?
6. **Circuit breaker/rate limit:** could mass retries trigger a retry storm?

### HTTP methods and idempotency

| Common method | Basic property | Retry guidance |
| --- | --- | --- |
| **GET, HEAD, OPTIONS** | Defined as **safe** by HTTP semantics, so they must not be expected to cause business side effects | Usually retryable on transient failure, still requires a deadline and limit |
| **PUT, DELETE** | Defined as **idempotent** in intended effect of the method | Retryable per semantics, but consider secondary side effects and the specific contract |
| **POST** | Not idempotent by default | Avoid automatic retry unless the contract provides an idempotency key or equivalent guarantee |
| **PATCH** | Not idempotent by default | Must evaluate the specific operation, version/ETag, and contract |

**"Idempotent" does not mean "produces no extra logs/metrics".** Under HTTP semantics, sending multiple requests has the same intended effect on the resource, even though the server may log each call. Real-world applications sometimes implement semantics incorrectly, so critical clients still need business-layer controls.

### Dangerous example: POST creating an order

~~~text
Client: POST /orders (no idempotency key)
    │
    ├── Server writes orderId=42 to database successfully
    ├── Connection drops before client reads response
    ▼
Client: IOException / HttpTimeoutException
    │
    └── If retried without control → server may create orderId=43
~~~

You cannot equate an exception with "the server did not process it", nor rely on **500** to guarantee a rollback. Use an **idempotency key** defined by the API—for example a header named by the system's contract with a unique value per operation—or look up status by business request ID before retrying. Do not assume that every server supports a universal idempotency header.

### Combining Retry-After and backoff

**Retry-After** can be:

~~~http
Retry-After: 3
~~~

or:

~~~http
Retry-After: Wed, 21 Oct 2037 07:28:00 GMT
~~~

The first value is **delay-seconds**, not milliseconds; the second is an **HTTP-date**. Production code needs to parse both formats, compare against the clock, apply a max wait/deadline, add jitter when appropriate, and respect rate-limit policies. For 429 or 503 without Retry-After, bounded backoff is still better than immediate retry.

Do not automatically retry on **certificate mismatch/SSLHandshakeException**, 401/403 caused by wrong credentials/policy, or 400/422 caused by unfixed validation errors: they usually **do not disappear just by repeating the request**. Conversely, 404 may be considered a normal outcome for a resource existence check API; it does not necessarily warrant reporting a system error.

## 11. How does an HTTP client decide when receiving a status?

One approach is to **evaluate by contract** first, using status groups only for default routing:

~~~text
Send request
    │
    ├── throws exception / exceptional future
    │     └── log type + cause + phase/timing if available
    │           → retry/cancel/fail according to policy and idempotency
    │
    └── receives HttpResponse
          │
          ├── 2xx → check specific status, body, and business contract
          │           201: Location; 202: async job; 204: no body
          │
          ├── 3xx → redirect/conditional cache semantics
          │           302: Location; 304: use cached representation
          │
          ├── 4xx → auth, validation, conflict, quota...
          │           401: auth; 409: state; 429: backoff
          │
          └── 5xx → server/gateway error
                      503: capacity/maintenance, possibly Retry-After
                      504: gateway waited too long for upstream
~~~

### Multi-layer rule for evaluating success

There are at least three layers:

- **Transport success:** connected and transmitted/received the required bytes per the network protocol.
- **HTTP success:** server returned an appropriate status (typically 2xx) per HTTP semantics.
- **Business success:** the business contract was fulfilled, e.g., transaction confirmed, data committed, or job transitioned to completed.

For example: **202 Accepted** indicates the HTTP request was accepted, **not** that the job finished. **200 OK** may contain a domain error by API design. **503** indicates an HTTP server/gateway error, but does not prove the server caused no side effect.

### Logging/metrics notes

Separate the dimensions:

~~~text
HTTP RESPONSE:
method=GET
route=/items/{id}
http_status=503
status_family=5xx
exception_type=none
retry_after=1
duration_ms=...

TRANSPORT / CLIENT FAILURE:
method=GET
route=/items/{id}
http_status=absent
error_type=HttpTimeoutException
phase=unknown_or_recorded_phase
duration_ms=...
request_effect=unknown
~~~

Do not log tokens, passwords, cookies, queries containing personal data, or sensitive full response bodies. If the system uses internal codes like **HTTP_STATUS_UNAVAILABLE**, clearly mark that it is **not** a returned HTTP code. When distributed tracing is available, include the request ID/trace ID and correlate gateway/backend logs per policy.

## 12. Practical testing with HTTP client, curl, and fault injection

### When there is a response: inspect status and headers

~~~bash
curl -i http://127.0.0.1:8080/health
curl -v http://127.0.0.1:8080/missing
curl -i -L http://127.0.0.1:8080/redirect
~~~

These URLs are **examples if you have a server on port 8080**, **not** the URL of the port-0 auto-assigned demo; replace with the actual port. **-i** displays headers, **-v** displays network progress details, and **-L** automatically follows redirects. With cURL, the **--fail** option can make the command return a non-zero exit code when HTTP status >=400 (with protocol/context exceptions); this is tool behavior and **does not turn 404/503 into a TCP error**.

### When there is no response: check the network phase

If a connection cannot be established, check for DNS errors, wrong hostname, proxy, firewall, port, TLS cert, DNS cache, or timeouts. Do **not** take an application-assigned status code from catching an exception and work backwards to claim "the server returned that code".

To analyze the issue:

1. **DNS:** does the hostname resolve to the right IP? Is there an IPv4/IPv6 mismatch?
2. **TCP:** right host/port? Is there a listener? Firewall/NAT and routing?
3. **TLS:** is the certificate chain trusted? Does SAN match hostname? Are TLS version/ciphers compatible?
4. **HTTP:** did the request reach the server/gateway? Are there status, Retry-After, Location, or response body?
5. **Body/application:** is there a body read timeout, parse error, or business validation failure?

An **HTTP 404** should be debugged via URL/path/API contract and read permissions; a **Connection refused** should be debugged via host/port/listener. These are two different toolsets.

## 13. Common implementation mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| "404 means the server is unreachable." | Investigates the wrong network layer, wastes time | 404 is an HTTP response; check routing/resource/auth |
| "All 5xx come from the backend." | Misses gateway/proxy/upstream issues | Correlate edge/backend logs and traces |
| "504 and HttpTimeoutException are the same." | Unclear who actually timed out | Distinguish gateway-returned response from client deadline |
| "500 guarantees the transaction rolled back." | Retrying POST creates duplicate side effects | Idempotency key/business status inquiry |
| "Every 2xx contains JSON." | Parses empty body of 204/HEAD | Check status, method, and Content-Type |
| "304 is a redirect that needs Location followed." | Breaks caching/conditional requests | 304 is not-modified; use cache properly |
| "401 and 403 are the same." | Token refresh loops or request spam | Handle authentication vs. authorization separately |
| "429 is 5xx because the service is busy." | Wrong metrics and retry policy | 429 belongs to **4xx**, use Retry-After/quota |
| "send(...) always throws on 404." | Ignores response.statusCode() | Read java.net.http.HttpClient behavior properly |
| "Catch every IOException and turn it into 500." | Hides DNS/TLS/network errors | Separate transport exceptions from HTTP status |
| "Catching HttpTimeoutException means the request never reached the server." | Repeats non-idempotent operations | Assume outcome unknown and design deduplication |
| "Client always follows redirects." | Surprises with method/URL/security | Configure and test Redirect.NEVER/NORMAL |
| "Immediately retry every 503." | Causes a retry storm | Backoff+jitter, Retry-After, max attempts |
| "Status family alone is enough for UI." | Shows wrong message for 409/422/429 | Classify by specific code and business contract |
| "Longer timeout is always safer." | Users wait long, threads/connections exhausted | Intentional deadlines and resource limits |

## 14. Self-check exercises

1. Java **HttpClient.send(...)** receives an **HttpResponse** with status **404**. Should you catch **ConnectException** to handle 404? Why?
2. A POST creating an order returns **202 Accepted**, along with a status URL. Which state allows reporting "order completed"? How should polling/webhooks work per the contract?
3. The server returns **204 No Content** for DELETE. A JSON parser running unconditionally on the empty body throws an error. Is this a Connection Error?
4. The client receives **302 Found** from **/login** and auto-follows to **200 OK**. Why can logging only 200 lose redirect information? When should you choose Redirect.NEVER?
5. With **304 Not Modified**, what condition allows using the cached representation? Why is 304 not an HTTP server failure?
6. An API returns **401**, **403**, **404**, **409**, **422**, **429**. Write separate handlers for auth, permission, not-found, conflict, validation, and rate limiting. Which code can be retried without changing the request?
7. An API gateway returns **504 Gateway Timeout**, while another Java client throws **HttpTimeoutException** before the gateway can return a status. Who generated each outcome? Should both be recorded as **statusCode=504**?
8. POST /payments committed, and the response was lost in transit. The client receives **IOException**. Why can the question "was the payment executed?" not be answered from the exception alone? Design an idempotency key and status lookup.
9. Run the example and replace **HttpClient.Redirect.NEVER** with **NORMAL** in the requests. Observe the resulting status codes and paths. How can you log the final URI to debug redirects?
10. Change the **/busy** endpoint returning 503 with **Retry-After: 1** to 429/503 without that header. Design a retry policy with **deadline, exponential backoff, jitter**, and a maximum attempt limit.
11. Change **/slow** from 800ms to 10ms while keeping the 150ms timeout. Why can the outcome be **200** instead of HttpTimeoutException? What determines the outcome?
12. Read **RFC 9110** and explain: how 301/302 differ from 307/308 regarding method preservation, how 408 differs from a client timeout, how 429 differs from 503, and what 206 means when downloading a file in parts.

## 15. Summary checklist for coding and operations

- [ ] Do you distinguish **HTTP response** from **exceptions when a complete HttpResponse has not been obtained**?
- [ ] Do you classify 2xx/3xx/4xx/5xx while still handling specific codes per contract?
- [ ] Do you handle **201 Location**, **202 async**, **204 no body**, **206 Partial Content**?
- [ ] Do you handle **304 conditional/caching** separately from redirects?
- [ ] Do you know HttpClient's redirect policy and its impact on URL/method/credentials?
- [ ] Do you distinguish **401**, **403**, **404**, **409**, **412**, **422**, **429**?
- [ ] Do you distinguish **500/502/503/504** and gateway-originated errors?
- [ ] Do you recognize **408/429/503/504** as statuses and **HttpTimeoutException** as an exception?
- [ ] Do you preserve cause/exception and phase information when there is no status?
- [ ] Do you avoid assigning "500" or "0" as if it were a real HTTP response?
- [ ] Do you bound timeouts, retry attempts, backoff, jitter, and consider Retry-After?
- [ ] Do you have a mechanism to prevent duplicate effects for POST/payment when the outcome is uncertain?
- [ ] Do you read **response body/headers** according to method/status and the API contract?
- [ ] Do you separate network, HTTP, and business metrics without logging secrets?

**Remember:** **2xx/3xx/4xx/5xx is the status classification of an HTTP response.** Statuses **404, 429, 503, 504** are all **real HTTP responses**, not connection exceptions. Conversely, **DNS failure, Connection refused, TLS handshake failure, client-side timeout, and I/O failure** are situations that can prevent the Java API from returning an **HttpResponse**, leaving only an **exception/cause** to analyze. Determine first "whether there is a response or not" before deciding on messaging, retries, and logging; do not use the status code alone to guess business outcomes or side effects.

**References:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111), [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585), [HttpClient (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html), [HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html), [HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html), [HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html), [HttpServer (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).