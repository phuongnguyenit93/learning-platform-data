# HTTP Status Codes and the Meaning of 2xx, 3xx, 4xx, and 5xx Groups

Every HTTP response carries a three-digit **status code**. This code tells the client the HTTP-level outcome of processing the request: success, further action needed, an issue with the request, or a server-side failure. In Spring Web, choosing the right status code enables browsers, mobile apps, API clients, proxies, and monitoring systems to handle responses consistently.

## 1. Objectives and How to Read Status Codes

After this lesson, you should be able to:
- Identify the general meaning of the **2xx**, **3xx**, **4xx**, and **5xx** groups and recognize **1xx** as informational interim responses.
- Distinguish commonly used codes such as `200`, `201`, `202`, `204`, `301`, `302`, `303`, `304`, `307`, `308`, `400`, `401`, `403`, `404`, `405`, `409`, `415`, `422`, `429`, `500`, `502`, `503`, and `504`.
- Choose status codes based on **the semantics of the situation**, HTTP method, resource state, and API contract.
- Return status codes using `ResponseEntity`, `@ResponseStatus`, or exception handling in Spring MVC.
- Diagnose errors by reading **status + headers + body** rather than looking at a single number alone.

A status code has the form `xyz`, where the first digit determines the class:

| Class | HTTP Name | General Meaning |
| --- | --- | --- |
| 1xx | Informational | Interim response during an exchange; mentioned here only for completeness. |
| **2xx** | Successful | The request was received, understood, and successfully processed per method/status semantics. |
| **3xx** | Redirection | The client needs further action, representation selection, or to use cached data/another address. |
| **4xx** | Client Error | The server indicates the request cannot be fulfilled under current conditions; usually relates to client data, authentication, permissions, resources, or limits. |
| **5xx** | Server Error | The server/gateway failed to fulfill an apparently valid request due to an infrastructure error or condition. |

**Important:** A status code is **HTTP semantics**, not a Java exception, error line number, or an arbitrary field inside JSON. For example, `HTTP/1.1 404 Not Found` is an HTTP response; `"status":404` inside JSON is just application data if defined by the server. In HTTP/2 and HTTP/3, the status resides in the `:status` pseudo-header, with no HTTP/1.1-style text status-line.

### Status code, reason phrase, headers, and body

Example HTTP/1.1 response:

~~~http
HTTP/1.1 201 Created
Location: /api/books/42
Content-Type: application/json

{"id":42,"title":"HTTP"}
~~~

In the example:
- `201` is the status code for programmatic handling.
- `Created` is the optional HTTP/1.1 reason phrase for human readers; do not compare this string in code.
- `Location` provides the URI of the newly created resource.
- `Content-Type` indicates the representation media type of the response body.
- JSON is the application body; **it is not a second status code**.

The status code does not reveal every error detail. The same `409 Conflict` can have multiple business causes; clients must read the error body per the API schema, along with relevant headers.

## 2. The 2xx Class — Request Processed Successfully

The 2xx class indicates success, yet **does not imply that background work is always finished or that a body is always present**.

| Code | Name | When to use |
| --- | --- | --- |
| **200 OK** | OK | Successful processing; e.g., GET returns a representation, POST returns a completed processing result. |
| **201 Created** | Created | The request completed and led to creating one or more resources; typically returns `Location` pointing to the primary new resource. |
| **202 Accepted** | Accepted | The request has been accepted for processing, but processing **has not completed**; it may succeed or fail later. |
| **204 No Content** | No Content | Processing succeeded and the server sends no message content; useful after DELETE or updates needing no body. |
| **206 Partial Content** | Partial Content | Server successfully fulfills a request for part of a representation, typically involving `Range`/`Content-Range`. |

### 2.1. 200 OK: success with method-dependent content

Example:

~~~http
GET /api/books/42 HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"HTTP"}
~~~

When GET succeeds on a resource, 200 typically carries the resource representation. For POST, 200 is also valid if the server returns a processing result without creating a new resource. For HEAD, 200 comes with no response content even though headers may describe the corresponding representation. Therefore, do not assume "200 always contains JSON".

### 2.2. 201 Created and Location

If POST actually **creates a resource that exists after the request**, 201 is an appropriate choice:

~~~http
HTTP/1.1 201 Created
Location: /api/books/42
Content-Type: application/json

{"id":42,"title":"HTTP"}
~~~

`Location` tells the client the URI of the primary created resource. This can be a relative URI, resolved against the request URI. The body is optional per the API contract; it may describe the new resource. Do not return 201 just because the method is POST: if POST executes a search or triggers an action that creates no resource, choose a status reflecting the actual outcome.

### 2.3. 202 Accepted: asynchronous and not yet finished

Example of an API enqueueing a report export request:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/report-jobs/abc

{"jobId":"abc","state":"queued"}
~~~

The client can poll the URL per the API contract to check progress. `202` **does not guarantee** the job will succeed; the final outcome must be communicated through a dedicated mechanism (status polling, callback, events...). Do not return 200 with "completed" text when the system has only accepted the request.

### 2.4. 204 No Content: no body

~~~http
HTTP/1.1 204 No Content

~~~

204 indicates processing succeeded with **no message content**, so clients should not invoke a JSON parser on an empty body. Do not attach `{}` JSON to a 204 response. Some frameworks/containers strip the body if you try to send one; the API must intentionally be designed properly.

### 2.5. 206 Partial Content

If a client sends `Range: bytes=0-99` and the server supports range requests, the response can return 206 with `Content-Range` specifying the actual byte range sent. 206 **does not mean "partial business success"**. If processing three operations and only two succeed, do not repurpose 206 as a generic code for "partial business success"; define an appropriate API contract instead.

## 3. The 3xx Class — Redirection, Selection, or Cache Reuse

3xx codes are often loosely grouped as redirects, yet **304 Not Modified is not an instruction to go to a new URL**.

| Code | Primary Meaning | Method after client follows `Location` |
| --- | --- | --- |
| **301 Moved Permanently** | Resource has a permanent new URI | Modern clients may change POST to GET for historical compatibility; do not rely on 301 when preserving method is mandatory. |
| **302 Found** | Temporarily at a different URI | Like 301, clients may change POST to GET for historical compatibility. |
| **303 See Other** | View result at another URI, commonly after POST | For standard redirection, uses GET or HEAD to retrieve the target resource. |
| **304 Not Modified** | Cached representation remains valid after a conditional request | Downloads no new response body; reuses the cached copy per cache rules. |
| **307 Temporary Redirect** | Temporary redirect | **Preserves the method** when automatically redirecting. |
| **308 Permanent Redirect** | Permanent redirect | **Preserves the method** when automatically redirecting. |

### 3.1. Redirect and Location

Example of migrating an endpoint during a transition period:

~~~http
HTTP/1.1 308 Permanent Redirect
Location: /api/v2/books/42

~~~

The client can resend the request to the new URI, keeping the method and body semantics under 308 rules. For a POST with side effects, keep in mind that **resending the request can execute it again**; redirects do not replace idempotency mechanisms in API design.

Example of **Post/Redirect/Get** in a browser form application: POST saves data successfully, the server returns 303 with `Location: /orders/42`, and the browser then GETs the result page. This avoids having a browser refresh on the result page directly resubmit the POST.

Do not use 301/308 casually for temporary URLs, because clients/caches may remember permanent redirects long-term.

### 3.2. 304 Not Modified and conditional caching

A standard example with ETag:

~~~http
GET /api/books/42 HTTP/1.1
Host: api.example.test
If-None-Match: "book-v7"

~~~

If the server determines the current representation matches the ETag:

~~~http
HTTP/1.1 304 Not Modified
ETag: "book-v7"

~~~

The client/cache uses the matching stored representation instead of receiving a new body. **304 contains no message content**, nor does it state "the resource has never changed". It only reflects the evaluation result of the request's condition at that time. If the cache lacks a corresponding representation, 304 alone is insufficient to construct the data.

### 3.3. API Redirects: three questions before choosing a code

1. Is the new URI **permanent** or only temporary? Consider 301/308 for permanent; 302/307 for temporary.
2. Must the **method/body be preserved** when the client follows up? If yes, 307/308 express that clearly.
3. Do you want the client to **GET a page/result after a POST**? 303 usually expresses that intent clearest.

Do not confuse HTTP 3xx redirects with Spring MVC returning a view name or an internal forward. Browsers only issue a new request when receiving a genuine redirect with an appropriate status and `Location`.

## 4. The 4xx Class — Request Cannot Be Fulfilled

4xx generally directs the client to **modify the request, supply appropriate credentials/permissions, or wait until conditions allow**. The label "Client Error" does not mean every 4xx error is necessarily caused by a frontend developer: security rules, resource existence, and API contracts all factor in.

| Code | Name | Typical Situation |
| --- | --- | --- |
| **400 Bad Request** | Bad Request | Request is malformed or invalid in a way the server cannot/will not process. |
| **401 Unauthorized** | Unauthorized | Missing or invalid authentication credentials for a protected resource; a proper 401 response should include `WWW-Authenticate`. |
| **403 Forbidden** | Forbidden | Server understands the request but refuses to authorize it, typically due to insufficient permissions. |
| **404 Not Found** | Not Found | Target representation/resource not found in a way the server is willing to disclose; can also intentionally hide forbidden resources. |
| **405 Method Not Allowed** | Method Not Allowed | The URI has a handler/resource, but the method is not supported at the target; response must include `Allow` listing currently supported methods. |
| **406 Not Acceptable** | Not Acceptable | Server cannot find a representation matching the client's content negotiation criteria and refuses to return another type. |
| **408 Request Timeout** | Request Timeout | Server did not receive a complete request within the time it was prepared to wait. |
| **409 Conflict** | Conflict | Request conflicts with the current state of the resource/system. |
| **410 Gone** | Gone | Resource is no longer available and that condition is likely permanent. |
| **412 Precondition Failed** | Precondition Failed | A precondition such as `If-Match` failed; often used to prevent overwriting concurrent updates. |
| **413 Content Too Large** | Content Too Large | Request content exceeds the size the server is willing to accept. |
| **415 Unsupported Media Type** | Unsupported Media Type | Media type/encoding of the request content is not supported by the endpoint. |
| **422 Unprocessable Content** | Unprocessable Content | Content type and syntax are understood, but cannot be processed due to semantic/content errors. |
| **429 Too Many Requests** | Too Many Requests | Client has sent too many requests in a given time window per rate-limit policy. |

### 4.1. Distinguishing 400, 415, and 422

A `POST /api/books` accepting JSON:
- **Malformed** JSON body such as `{"title":`: typically returns **400**, because it cannot be deserialized.
- Client sends `Content-Type: application/xml` when the endpoint only accepts JSON: typically returns **415**.
- Valid JSON with a structure the server understands, but violating a semantic rule (such as an unprocessable value): **422** may fit depending on the API contract. Many APIs use **400** for validation and are completely reasonable when consistent. Spring MVC does not automatically use 422 for all validation errors.

### 4.2. Distinguishing 401 and 403

- **401:** client provided no credentials or invalid credentials. With Bearer tokens, a server protecting an endpoint can return `WWW-Authenticate: Bearer`, with parameters where appropriate. HTTP calls this "Unauthorized" though it actually concerns **authentication**.
- **403:** server knows the request but refuses to execute it—for instance, an authenticated account lacking admin privileges. Adding a token will not necessarily fix it.
- **404:** a security system may intentionally return 404 instead of 403 to avoid disclosing whether a protected resource exists.

Do not infer an authentication policy solely from the status code of an unknown endpoint.

### 4.3. Distinguishing 404, 405, and 410

- `GET /api/books/999` when book 999 does not exist: typically **404**.
- `POST /api/books/42` when this endpoint only allows GET: typically **405** (if routing configuration has a matching route and the framework distinguishes the method).
- Document has been permanently deleted and the server knows it: **410** can express this more clearly; deleted resources are not required to return 410.

Some APIs return 404 even when a method/path has no route; check router configuration and `Allow` instead of guessing.

### 4.4. Distinguishing 409 and 412 for concurrent updates

**409 Conflict:** for example, a user tries to register with an already-taken username, or transitions an order to a state incompatible with its current state.

**412 Precondition Failed:** for example, a client fetches a resource with an ETag and then sends:

~~~http
PUT /api/books/42 HTTP/1.1
Host: api.example.test
If-Match: "book-v7"
Content-Type: application/json

{"title":"Revised"}
~~~

If the current representation has a different ETag, the server can return 412, preventing overwriting someone else's changes. 409 expresses a general state conflict; 412 emphasizes a failed **HTTP precondition**.

### 4.5. 429 and Retry-After

429 is appropriate when a client exceeds a rate limit policy; the response **may** include `Retry-After` indicating when to try again:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

`Retry-After: 60` means wait roughly 60 seconds before retrying, per the server's hint; it does not guarantee the next attempt will succeed. Clients need backoff, rate throttling, and idempotency considerations before resending requests with side effects.

## 5. The 5xx Class — Server or Infrastructure Failed to Complete the Request

5xx codes typically indicate an issue on the processing side, server, or an intermediary. Clients may retry in some cases, but blind retries risk side effects or overloading an already failing server further.

| Code | Name | Meaning |
| --- | --- | --- |
| **500 Internal Server Error** | Internal Server Error | Server encountered an unexpected condition and could not fulfill the request; this is the general catch-all when no more specific status applies. |
| **501 Not Implemented** | Not Implemented | Server does not support the functionality required to fulfill the request, such as not recognizing or supporting the method server-wide. |
| **502 Bad Gateway** | Bad Gateway | Gateway/proxy received an invalid response from an upstream server it needed to fulfill the request. |
| **503 Service Unavailable** | Service Unavailable | Service is temporarily unavailable, e.g., overloaded or under maintenance; `Retry-After` may be used. |
| **504 Gateway Timeout** | Gateway Timeout | Gateway/proxy did not receive a timely response from an upstream server. |

### 5.1. Distinguishing 500, 502, 503, and 504

Suppose the flow is:

~~~text
Mobile App → API Gateway → Spring Web → Database / Other Service
~~~

- **500:** an unhandled or improperly handled exception inside a Spring service can become a 500. For instance, an unexpected `NullPointerException` or broken error handling; actual behavior depends on the exception handler.
- **502:** the gateway receives a malformed or invalid upstream response and returns Bad Gateway.
- **503:** the backend temporarily stops serving due to maintenance/overload, or the gateway has no available backend and returns 503 per configuration.
- **504:** the gateway times out waiting for the upstream server.

**Do not automatically call every timeout a 504.** If a client connection drops without receiving an HTTP response, the client sees a network/timeout error with no status code. If the Spring application itself responds to a timeout under another contract, the code depends on the implementation.

**501 is not 405:** if the server understands the method but the target resource does not support it, 405 is appropriate; if the server lacks broader support for the capability/method, 501 may apply.

### 5.2. Smart retries

On 5xx:
1. Record the status, request ID/tracing ID (if present), timestamp window, and endpoint.
2. If `Retry-After` is present, respect that signal when appropriate.
3. Use exponential backoff with jitter, a retry limit, and explicit timeouts.
4. Automatically retry only requests whose duplicate delivery is **safe under the contract**. GET is usually suitable; transaction-creating POST requests need an idempotency key or deduplication mechanism before retrying.
5. On the backend, never return stack traces, access tokens, raw SQL details, or internal secrets to clients; use internal logs/tracing to investigate.

**A 5xx status does not prove the business operation did not happen.** The server might have committed data successfully and failed while building the response; blindly retrying POST without duplicate protection can create two records.

## 6. Choosing a Status for an API: From Semantics to Decision

The table below lists **common patterns**, not rigid rules tied to methods. The primary criterion remains the actual outcome of the request.

| API Scenario | Code to consider | Reason |
| --- | --- | --- |
| GET returning a resource representation | 200 | Successfully returns data. |
| POST creating a new resource that now exists | 201 | Succeeded and created a resource; include Location when appropriate. |
| POST accepting a job for later processing | 202 | Only accepted, final outcome not yet determined. |
| DELETE succeeded, returning no body | 204 | No response content. |
| Conditional GET, ETag still matches | 304 | Reuse cache; send no representation body. |
| GET for non-existent ID | 404 | Resource not found. |
| Malformed JSON request | 400 | Request data cannot be parsed. |
| Request missing authentication for protected resource | 401 | Authentication required with appropriate challenge. |
| User lacks permission | 403 | Action refused. |
| POST creating data with duplicate business key | 409 | Conflicts with existing state. |
| If-Match does not match current version | 412 | HTTP precondition failed. |
| Endpoint temporarily overloaded | 503 | Service unavailable. |

Helpful design distinctions:
- **200 or 201?** Choose 201 if the request created a resource and completed; POST does not always lead to 201.
- **200 or 204?** Choose based on whether there is a representation in the body, not on a subjective feeling that "the body has little info".
- **201 or 202?** A created and completed resource differs from a newly queued job.
- **400 or 422?** Establish a clear API contract separating syntax errors from semantic errors.
- **409 or 500?** Expected business conflicts are 409; unexpected internal errors can be 500.
- **404 or 204 on a second DELETE?** Both appear across different APIs; idempotent DELETE concerns the **intended effect on the resource**, and does not require identical statuses across calls.

## 7. Returning Statuses in Spring MVC: Runnable Example

This example uses **Java 17+ and Spring Boot 3 with the `spring-boot-starter-web` dependency** (including Spring MVC and standard JSON serialization). It is a minimal runnable application inside a configured Spring Boot project; it is not a standalone Java file compilable with `javac` without Spring libraries. Place all code in `src/main/java/demo/http/HttpStatusDemoApplication.java`:

~~~java
package demo.http;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class HttpStatusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpStatusDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {
    private final Map<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    @GetMapping("/{id}")
    public ResponseEntity<Book> find(@PathVariable long id) {
        Book book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build(); // 404
        }
        return ResponseEntity.ok(book); // 200 + JSON
    }

    @PostMapping
    public ResponseEntity<Book> create(@RequestBody CreateBook request) {
        if (request.title() == null || request.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "title must not be blank"); // 400
        }

        long id = nextId.incrementAndGet();
        Book book = new Book(id, request.title());
        books.put(id, book);

        URI location = URI.create("/api/books/" + id);
        return ResponseEntity.created(location).body(book); // 201 + Location
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (books.remove(id) == null) {
            return ResponseEntity.notFound().build(); // 404
        }
        return ResponseEntity.noContent().build(); // 204
    }

    record CreateBook(String title) {}
    record Book(long id, String title) {}
}
~~~

**How to run:** in a Spring Boot Gradle project with `implementation 'org.springframework.boot:spring-boot-starter-web'`, run the application using `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows. By default, the app typically serves on `http://localhost:8080` unless the port is reconfigured. The sample app stores data **in memory**, so restarting loses data; IDs start at 1 in a fresh run and depend on actual request order.

Test sequentially with `curl` in a POSIX-syntax shell terminal (or adjust quoting for PowerShell):

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -d '{"title":"HTTP Essentials"}'

curl -i http://localhost:8080/api/books/1

curl -i -X DELETE http://localhost:8080/api/books/1

curl -i http://localhost:8080/api/books/1

curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -d '{"title":""}'
~~~

On a **freshly started** application, with no other requests and the first POST succeeding, the expected outcomes are:

| Request | Status | Expected Meaning/Body |
| --- | --- | --- |
| POST creating a book with a valid title | **201 Created** | `Location: /api/books/1` and JSON `{"id":1,"title":"HTTP Essentials"}`. |
| GET `/api/books/1` | **200 OK** | JSON describing the newly created book. |
| DELETE `/api/books/1` | **204 No Content** | No response body. |
| GET the deleted book | **404 Not Found** | Empty body due to how `ResponseEntity.notFound().build()` is constructed in the example. |
| POST with an empty title | **400 Bad Request** | `ResponseStatusException` error; error body format depends on Spring Boot configuration. |

The framework/container may add other headers, and serialization may be affected by configuration. This example illustrates **HTTP status semantics**: using `ResponseEntity` to explicitly return statuses and bodies. Do not assume every response shares the same `Content-Length`, timing, or header set across environments.

### 7.1. Three ways Spring MVC sets status codes

**Approach 1 — `ResponseEntity`:** when the controller needs to control status, headers, and body simultaneously:

~~~java
return ResponseEntity.created(URI.create("/api/books/" + id))
                     .body(book);
~~~

**Approach 2 — `@ResponseStatus`:** when a handler has a relatively fixed status:

~~~java
@PostMapping("/ping")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void ping() {
    // Illustrative endpoint: succeeds with no body.
}
~~~

This snippet is an **isolated controller method example** and only works inside a Spring MVC controller with proper imports (`@PostMapping`, `@ResponseStatus`, `HttpStatus`); it is not a standalone Java program. `@ResponseStatus` can also be placed on certain exception types depending on design.

**Approach 3 — exceptions and centralized handling:** throw `ResponseStatusException` to attach a corresponding code, or use `@RestControllerAdvice` combined with `@ExceptionHandler` to map domain exceptions into standardized responses. For instance, a `BookConflictException` in business logic can be mapped to 409. Map only errors with **well-defined meaning**; avoid turning every exception into 200 or 400.

In Spring MVC, resolvers and exception-handling configuration determine the actual status. Spring Security, filters, proxies/gateways, and error response configuration can also affect the response. Therefore, log actual HTTP statuses at the application boundary when investigating issues.

### 7.2. Standardized error bodies: Problem Details

In the HTTP ecosystem, the **Problem Details** format (RFC 9457, updating RFC 7807) commonly uses the media type `application/problem+json` and standard fields such as `type`, `title`, `status`, `detail`, and `instance`.

Illustrative 409 example per a sample contract:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/book-conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Book identifier already exists",
  "instance": "/api/books/42"
}
~~~

**The response above is an API-chosen example**, not a guaranteed default body from Spring. Spring Framework 6 includes `ProblemDetail` and supports handling errors along these lines; whether bodies and fields are emitted automatically depends on Spring MVC/Spring Boot configuration and exception resolvers. The HTTP response status is the protocol-level status; the `status` field in the body provides descriptive error metadata aligned with the response.

Keep error messages helpful enough for clients without exposing stack traces, passwords, SQL queries, or tokens. For validation errors, return error details using a stable schema so callers can fix the exact field.

## 8. Debugging by Status Code and Request Path

When diagnosing an API, observe directly:

~~~bash
curl -i http://localhost:8080/api/books/42
~~~

- `-i` displays response headers along with the body, including the status-line when using HTTP/1.x.
- `-v` shows additional connection details and the request generated by curl.
- DevTools Network, HTTP clients, or tracing can show redirect chains, request/response headers, payloads, and timings.

A useful inspection sequence:

1. **Is there a status code?** If not, investigate DNS, TCP/QUIC, TLS, connection timeouts, proxies, and send/receive errors; do not assume 500.
2. **2xx yet the UI still errors?** Check whether the body matches the schema, whether content is actually valid, whether 204 is being wrongly parsed as JSON, or whether 202 is being treated as "job finished".
3. **3xx?** Inspect `Location` and `Cache-Control`/ETag where relevant; distinguish redirect chains from 304 caching. Check the method after redirection to avoid unintentionally turning POST into GET.
4. **4xx?** Inspect method, path, query, `Content-Type`, `Accept`, auth, permissions, body, ETag/preconditions, and rate-limit policies. 400/401/403/404/409 require different handling.
5. **5xx?** Check server and gateway/upstream logs/tracing. Compare 500/502/503/504 to pinpoint where the failure occurred; design bounded retries and proper idempotency.

In Spring Web, a routing or argument-conversion error occurs **before entering the business method**, so breakpoints placed only inside the controller may not be hit. Check exception handlers, filters, the security chain, the servlet container, and proxies when an unexpected status occurs.

## 9. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| “Every 2xx has a JSON response.” | 204 has no content; 202 only accepted work; 206 is a partial representation. |
| “POST always returns 201.” | 201 is when resource creation finishes; POST can return 200, 202, 204, or error codes depending on semantics. |
| “All 3xx codes redirect to another URL.” | 304 tells the client to reuse cache, not redirect to another URI. |
| “301, 302, 307, 308 only differ by number.” | Permanence and rules for preserving/changing methods are significant differences. |
| “401 means logged in but lacking permissions.” | 401 concerns authentication/challenges; 403 typically represents permission denial. |
| “404 definitely means the resource does not exist.” | Servers may use 404 to avoid disclosing the existence of forbidden resources. |
| “400 and 422 are completely interchangeable.” | They carry different semantics; use them consistently with the API contract. |
| “409 is a system error like 500.” | 409 usually represents a state conflict that the client can address. |
| “5xx means the operation definitely did not execute.” | The server may have saved changes and failed while responding; retries need duplicate protection. |
| “If there is a timeout, the server returned 504.” | A timeout with no HTTP response has no status code; 504 is a specific gateway response. |
| “Spring always automatically returns the exact error body I expect.” | Status/body depend on exception resolvers, Boot configuration, Security, and proxies. |

## 10. Self-Check Exercises and Explanations

**Exercise 1.** API `POST /payments` accepts a request, enqueues processing, and does not yet know the payment outcome. Should it return 201 or 202?

**Exercise 2.** A client GETs a document with `If-None-Match` and the server sees the ETag has not changed. What is the appropriate status? Is there a new document JSON body?

**Exercise 3.** A client has a valid token but lacks permission to delete books. Should the server return 401 or 403? What if the token is invalid?

**Exercise 4.** A gateway does not receive a timely upstream response. Distinguishing 500, 502, 503, and 504: which code describes this best?

**Exercise 5.** A client POSTs syntactically valid JSON that collides with a unique key, and the API wants the client to handle the conflict. Should it return 409 or 500?

**Exercise 6.** Deleting a record succeeds and the server does not need to return a representation. What is a sensible status? If a subsequent DELETE to the same URI returns 404, does that break DELETE idempotency?

### Answers

1. **202 Accepted**: processing has not finished; there must be a separate mechanism to track the final outcome beyond this status.
2. **304 Not Modified** when matching cache conditions are met; send no new representation body.
3. **403 Forbidden** when authentication is valid but permissions are lacking; **401 Unauthorized** with an appropriate challenge when authentication is missing/invalid. Security policies may intentionally use 404 to hide existence.
4. **504 Gateway Timeout**; 500 is a general server error, 502 is an invalid upstream response, and 503 is temporary service unavailability.
5. **409 Conflict** expresses an expected state conflict; avoid reporting 500 for known business errors.
6. **204 No Content** is appropriate. A subsequent call may return 404: idempotency describes the intended effect of repeated calls and does not require identical statuses across calls.

## 11. Core Knowledge Summary

When designing Spring Web APIs, reason from the **actual outcome of the request** to the status: **2xx** expresses success (including created, accepted, or no body), **3xx** expresses redirection/caching, **4xx** expresses that the request cannot be fulfilled under current conditions, and **5xx** indicates a server or intermediary failure. Then choose headers and bodies that match the status semantics—especially `Location` for 201/3xx, `WWW-Authenticate` for 401, `Allow` for 405, and `Retry-After` for 429/503 where applicable. In Spring MVC, use `ResponseEntity`, status annotations, and exception handling to respond consistently; always verify the actual status/headers/body from an HTTP client.

**Reference documents:** RFC 9110 (HTTP Semantics), RFC 9111 (HTTP Caching), RFC 9112 (HTTP/1.1), RFC 9457 (Problem Details), and Spring Framework Web MVC documentation on `ResponseEntity`, `@ResponseStatus`, and `ProblemDetail`.