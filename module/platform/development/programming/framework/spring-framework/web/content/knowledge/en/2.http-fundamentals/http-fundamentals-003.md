# HTTP Methods, Safety, and Idempotency

## 1. What Is an HTTP Method and Why Must We Understand It Correctly?

HTTP is a request/response protocol between client and server. An **HTTP request method** (also called an HTTP verb) expresses *the action the client wants to perform on the target resource*. In the following request, the method is `GET`, and the path is `/api/books/42`:

```http
GET /api/books/42 HTTP/1.1
Host: example.com
Accept: application/json
```

In a Spring Web application, the server can map a method and path to a controller method. However, the standard meaning of a method is an **HTTP contract** shared across clients, servers, browsers, proxies, caches, and network tools—not merely an annotation choice on a controller.

Three questions should be kept distinct:

1. **What is this method asking to do?** For example, `GET` reads a representation of the resource, `PUT` creates/replaces the target resource's state, and `DELETE` requests removing the resource's current representations.
2. **Is this method safe?** Is the client *requesting* a state change or not?
3. **Is this method idempotent?** Does repeating multiple identical requests have the same *intended effect* as sending a single request?

These questions directly impact API design, retries on network failures, caching, crawlers, security, and user experience.

## 2. Common HTTP Methods

| Method | Primary Meaning | Example | Safe under standard semantics? | Idempotent under standard semantics? |
|---|---|---|---|---|
| `GET` | Retrieve the current representation of a resource | `GET /products/42` | Yes | Yes |
| `HEAD` | Same as requesting metadata corresponding to GET, but the response contains no body | `HEAD /products/42` | Yes | Yes |
| `OPTIONS` | Query supported communication options | `OPTIONS /products/42` | Yes | Yes |
| `TRACE` | Perform a message loop-back test along the path | `TRACE /diagnostic` | Yes | Yes |
| `POST` | Request the target resource to process data according to its own semantics | `POST /orders` | No | Not guaranteed |
| `PUT` | Create or replace the resource state at the target URI with the submitted representation | `PUT /products/42` | No | Yes |
| `PATCH` | Apply a set of changes to a resource | `PATCH /products/42` | No | Not guaranteed |
| `DELETE` | Request removal of the current representations of the target resource | `DELETE /products/42` | No | Yes |
| `CONNECT` | Establish a tunnel to the target server via a proxy | `CONNECT example.com:443` | No | No |

**Scope note:** `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `OPTIONS`, `TRACE`, and `CONNECT` are defined in RFC 9110; `PATCH` is defined separately in RFC 5789. Most Spring Web application development focuses on `GET`, `POST`, `PUT`, `PATCH`, and `DELETE`. `OPTIONS` commonly appears when studying CORS. `HEAD` is useful for checking metadata. `TRACE` and `CONNECT` are not typical CRUD operations; many servers restrict or disable TRACE for security reasons.

Methods are **case-sensitive** at the HTTP layer: `GET` is the standard form; do not assume `get` is equivalent to `GET`. Nor do methods automatically dictate the response format: the same `GET` can receive HTML, JSON, an image, or another representation depending on the resource and content negotiation.

## 3. Safety: The Client Does Not Request State Changes

### 3.1. Definition

An HTTP method is **safe** when its defined semantics are essentially read-only: the client does not request and does not expect applying the request to alter state on the origin server. The safe methods designated by the HTTP standard are **GET, HEAD, OPTIONS, and TRACE**.

Example respecting safety:

```http
GET /api/products/42 HTTP/1.1
Host: shop.example
```

The client asks to read product 42. Reloading the page, opening a link, a crawler visiting, or a browser prefetching this URL should not turn into purchasing an item, charging money, deleting the product, or sending an email.

**Semantically incorrect** example:

```http
GET /api/orders/42/cancel HTTP/1.1
Host: shop.example
```

If fetching the URL actually cancels the order, this request performs a business state-changing action despite carrying the `GET` method. A proper design is an unsafe operation with appropriate authentication/authorization, such as `POST /api/orders/42/cancellation` or a state update explicitly modeled with a suitable method.

### 3.2. “Safe” does not mean zero side effects whatsoever

The server may write access logs, increment monitoring metrics, store telemetry, or record technical statistics when handling `GET`. That does not automatically make the method unsafe by definition: the client **did not request** those internal side effects, and they should not be treated as a user-initiated business transaction.

Distinguish:

- `GET /products/42` writing an access log: generally remains consistent with safe semantics.
- `GET /products/42` automatically deducting inventory, charging a fee, or deleting the product: violates safety expectations.
- `GET /products/42?operation=delete` actually deleting the product: a query parameter does not "turn GET into POST"; the server must prevent unsafe actions over safe methods.

**Safe does not mean no security needed.** `GET` can still read personal data, secrets, or resources restricted to authorized users. The server must enforce appropriate authentication/authorization. URLs and query strings can be saved in browser history, logs, and observability systems; do not put tokens or passwords into URLs.

### 3.3. Why does safety matter?

Browsers, search engines, proxies, and link checkers may access `GET` without expressing intent to trigger a transaction. Safe methods establish the expectation that those systems can retrieve resources without accidentally causing harm.

Therefore, an HTML link like `<a href="/delete-account">...</a>` must not have its GET request actually delete the account. State-changing actions must be triggered intentionally using an appropriate method and protective mechanisms, especially when cookie-based login sessions are involved.

## 4. Idempotency: Repeating the Same Request Achieves the Same Intended Effect

### 4.1. Definition and intuitive formula

A method is **idempotent** when the *intended server-side effect* of sending multiple identical requests is the same as sending a single request. You can picture the state transformation as `f`:

```text
f(f(state)) = f(state)
```

This formula is a conceptual model of the intended effect; it does **not** mean every byte of the HTTP response or every log line will be identical, nor does it guarantee isolation from concurrent requests by other clients.

Example of a product with state `published=false`:

```http
PUT /api/products/42 HTTP/1.1
Host: shop.example
Content-Type: application/json

{"name":"Java","published":true}
```

If the API defines this as a full replacement representation and the server applies proper PUT semantics, repeating the same request two or three times produces the same final business outcome: product 42 has `name="Java"` and `published=true`. The request may update data once or multiple times at the infrastructure level; the **effect requested by the user** is the same.

Conversely, an increment operation:

```http
POST /api/counters/visits/increment HTTP/1.1
Host: shop.example
```

If each request increases the value by one unit, executing it twice increases it by two units. This is a **non-idempotent** action.

### 4.2. Idempotent does not mean “identical response”

Suppose the first DELETE succeeds in deleting:

```http
DELETE /api/products/42 HTTP/1.1
Host: shop.example
```

The server may return `204 No Content` the first time and `404 Not Found` the second time, or return `204` both times depending on the API contract. The target state remains "the product no longer exists". Hence, **DELETE is still defined as idempotent by the HTTP standard** even if the status code differs across calls.

Similarly, `PUT` may return `201 Created` on the first call when creating the resource and `200 OK` or `204 No Content` on subsequent replacements. Responses do not all have to match to satisfy idempotency.

Like safety, idempotency refers to the **intended effect requested by the client**. Logs, revision history, infrastructure request counters, or retry tracking may still change with every request received. However, if a `PUT` endpoint is designed so that *each call adds money to an account*, it does not satisfy PUT's idempotent semantics even though the controller uses `@PutMapping`.

### 4.3. How are safety and idempotency related?

- Safe methods are also idempotent under standard semantics: repeating a read-only action requests no business state change.
- Idempotent **does not mean** safe: `PUT` and `DELETE` modify resources, yet repeating the same request still achieves the same intended effect.
- Unsafe and not guaranteed idempotent: `POST`, `PATCH`. A specific API **can** still design an idempotent POST or PATCH operation with explicit conditions/logic, but clients must not assume it based solely on the method.
- Idempotency is not synonymous with transactions, exactly-once delivery, atomicity, avoiding race conditions, or automatically preventing overwrites of another user's updates.

## 5. Individual Analysis of Key Methods

### 5.1. GET and HEAD

`GET` retrieves the current resource representation, not a command to create or modify a resource. When an API returns JSON, a successful response is usually `200 OK`; a missing resource is usually `404 Not Found`. `GET` and `HEAD` can participate in HTTP caching subject to response conditions and cache policies.

`HEAD` requests metadata corresponding to GET but **without a response body**. Headers such as `Content-Type`, `ETag`, and `Last-Modified` let clients check resource status without downloading the content. Do not expect every header produced by GET to appear identically in HEAD; HTTP permits exceptions for fields whose values are only determined when generating the body.

```bash
curl -i http://localhost:8080/api/counters/demo
curl -I http://localhost:8080/api/counters/demo
```

In Spring MVC, a standard `@GetMapping` generally supports appropriate HEAD handling as well; exact capability depends on application configuration and handlers.

### 5.2. POST

`POST` submits content for the target resource to process according to its own semantics. It is commonly used to create a resource with a server-assigned ID, submit forms, trigger business processes, or append a new event:

```http
POST /api/orders HTTP/1.1
Host: shop.example
Content-Type: application/json

{"productId":42,"quantity":1}
```

If each submission creates a new order, sending it twice can create **two orders**. Upon successful creation, the server typically responds with `201 Created` and `Location: /api/orders/<id>`. Whether a POST API supports deduplication is not a default property of POST.

POST can also be designed to be idempotent for a specific business workflow, for instance using a unique request ID or `Idempotency-Key`; that is an **explicit implementation commitment** that must be documented in the API spec.

### 5.3. PUT

`PUT` requests creating or **replacing the resource state at the target URI** with the representation sent by the client:

```http
PUT /api/users/42 HTTP/1.1
Host: shop.example
Content-Type: application/json

{"name":"Lan","active":true}
```

One application might allow PUT only on existing resources and return `404` if absent; another might allow creating a new resource at that URI according to its rules. If created, `201` is an appropriate success code; if replaced, it can be `200` or `204`.

Avoid confusing PUT with additive/incremental operations (`balance += amount`, `stock--`). Resending the exact same payload must preserve the intended effect. If an API uses PUT while updating only a few fields, the contract must be documented clearly; under standard semantics PUT creates/replaces the target representation, whereas partial updates usually fit PATCH better.

### 5.4. PATCH

`PATCH` sends a **set of instructions for a partial modification** of a resource. The change format depends on the media type and API contract, such as JSON Patch (`application/json-patch+json`) or JSON Merge Patch (`application/merge-patch+json`); a plain custom JSON DTO does not automatically conform to those two standard formats.

Two styles of PATCH have different effects:

```text
A. Assign a fixed value: set active = true
   Sending twice still leaves active = true → can be idempotent.

B. Increment balance: balance = balance + 100
   Sending twice adds 200 → not idempotent.
```

PATCH **is not guaranteed idempotent by general definition**; to retry safely you must know specifically whether the operation is idempotent and consider version preconditions to avoid conflicts.

### 5.5. DELETE

`DELETE` requests removing the current representations of the target resource; for example:

```http
DELETE /api/users/42 HTTP/1.1
Host: shop.example
```

Deleting the same resource multiple times still has the same desired effect: the resource no longer appears under the application's contract. Idempotent DELETE **does not force the system to perform an immediate physical deletion**; soft deletes, asynchronous processing, auditing, or business constraints should all be clearly documented.

If the server only accepts the task for later processing, `202 Accepted` may be appropriate. If deletion completes and no body is returned, `204 No Content` is commonly used.

### 5.6. OPTIONS, TRACE, and CONNECT

`OPTIONS` indicates supported communication options. An application may return an `Allow` header or other headers. **CORS preflight** is a special case using OPTIONS, typically carrying `Origin` and `Access-Control-Request-Method`, though not every OPTIONS request is a CORS preflight.

`TRACE` performs a loop-back path test; many servers keep it disabled due to the risk of exposing request details. `CONNECT` is primarily for proxies establishing tunnels, not as a CRUD method in regular controllers.

## 6. Designing APIs Around Resources and Methods

A product management API might be designed as follows:

| Business Need | Method and URI | Intended Effect |
|---|---|---|
| View product list | `GET /api/products` | Read the list |
| View a specific product | `GET /api/products/42` | Read product 42 |
| Create a product with server-assigned ID | `POST /api/products` | May create a new product each time |
| Create/replace a product at a known ID | `PUT /api/products/42` | Target state matches the payload |
| Update partial information | `PATCH /api/products/42` | Apply the described set of changes |
| Delete a product | `DELETE /api/products/42` | No current representation of the product remains per API |

Do not rigidly equate HTTP verbs with CRUD: `POST` can trigger business workflows; `GET` can return a representation aggregated from multiple sources; `PATCH` can represent a complex set of operations. The method conveys **communication intent**, while the URI and API documentation specify **resources, permissions, payloads, and concrete outcomes**.

Helpful conventions:

- URIs should describe resources using nouns where appropriate (`/orders/42`), while methods express actions per HTTP conventions.
- Do not use `GET /delete?id=42` or `GET /pay?id=42` to trigger business state changes.
- Choose status codes that reflect reality: `200 OK`, `201 Created`, `202 Accepted`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `412 Precondition Failed`, `405 Method Not Allowed`.
- When a method is recognized by the server but disallowed on the resource, `405` is usually accompanied by `Allow`; when the server does not recognize/implement the method, `501 Not Implemented` is a different situation.
- Authentication, authorization, validation, and CSRF protection (when using cookies/sessions and CSRF risk exists) depend on context; picking the right method does not automatically solve security.

## 7. Hands-on with Spring Web MVC

The example below is a **minimal Spring Boot MVC application** to clearly observe the difference between `GET`, `PUT`, `POST`, and `DELETE`. It uses Java records (Java 17+) and in-memory RAM storage, suitable for learning. To run it, you need a Spring Boot project with the web MVC dependency and a JSON converter, such as a project generated with Spring Initializr including the **Spring Web** dependency and a JDK compatible with the chosen Boot version.

Create `src/main/java/com/example/http/HttpMethodsApplication.java`:

```java
package com.example.http;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpMethodsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpMethodsApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/counters")
class CounterController {
    private final ConcurrentHashMap<String, Integer> counters =
            new ConcurrentHashMap<>();

    public record CounterValue(int value) {}

    @GetMapping("/{key}")
    public ResponseEntity<CounterValue> get(@PathVariable String key) {
        Integer value = counters.get(key);
        if (value == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new CounterValue(value));
    }

    @PutMapping("/{key}")
    public ResponseEntity<CounterValue> replace(
            @PathVariable String key,
            @RequestBody CounterValue body) {
        Integer previous = counters.put(key, body.value());
        HttpStatus status = previous == null
                ? HttpStatus.CREATED
                : HttpStatus.OK;
        return ResponseEntity.status(status).body(body);
    }

    @PostMapping("/{key}/increment")
    public ResponseEntity<CounterValue> increment(
            @PathVariable String key) {
        Integer value = counters.compute(
                key, (ignored, oldValue) ->
                        oldValue == null ? 1 : oldValue + 1);
        return ResponseEntity.ok(new CounterValue(value));
    }

    @DeleteMapping("/{key}")
    public ResponseEntity<Void> delete(@PathVariable String key) {
        counters.remove(key);
        return ResponseEntity.noContent().build();
    }
}
```

**Why does this code hit the key points?**

- `GET` only reads state; a `null` value yields `404`.
- `PUT` assigns a specific value using `counters.put(key, body.value())`. No matter how many times you send `{"value":5}`, the final state remains 5, provided no other operation intervenes.
- `POST /increment` uses `compute` to increment the current value on each request; `ConcurrentHashMap.compute` performs the per-key map update atomically. Two POSTs increment twice.
- `DELETE` uses `remove`; calling it again keeps the key in a non-existent state.
- `ResponseEntity` demonstrates different statuses (`201` when PUT creates a new key, `200` when replacing) without breaking idempotency.

This uses **in-memory** data, which is not persisted across restarts and does not demonstrate transaction handling, security, validation, or persistence of a real system. `Integer` also risks overflow if continuously incremented to the limit; production scenarios require choosing appropriate data types and validation rules.

### Running and sending requests

In a Gradle project with the Spring Boot plugin, run `./gradlew bootRun` (or `gradlew.bat bootRun` on Windows). If using the Maven Wrapper, run `./mvnw spring-boot:run` (or `mvnw.cmd spring-boot:run` on Windows). This source cannot be run standalone with plain `javac` because it requires Spring Boot and Spring MVC libraries.

Assuming the server is running at `http://localhost:8080`, run step by step:

**Step 1 — Read before creating**

```bash
curl -i http://localhost:8080/api/counters/demo
```

Expected status: `404 Not Found`.

**Step 2 — Send PUT the first time**

```bash
curl -i -X PUT "http://localhost:8080/api/counters/demo" -H "Content-Type: application/json" -d '{"value":5}'
```

Expected status: `201 Created`; JSON body contains `{"value":5}`.

**Step 3 — Repeat the same PUT**

```bash
curl -i -X PUT "http://localhost:8080/api/counters/demo" -H "Content-Type: application/json" -d '{"value":5}'
```

Expected status this time: `200 OK`, while the body and value in the map still correspond to `{"value":5}`. A different status **does not negate idempotency**.

**Step 4 — Send POST to increment twice**

```bash
curl -i -X POST http://localhost:8080/api/counters/demo/increment
curl -i -X POST http://localhost:8080/api/counters/demo/increment
```

Expected JSON bodies contain `{"value":6}` and `{"value":7}` respectively. The same POST request changes state further each time: not idempotent.

**Step 5 — Send DELETE twice**

```bash
curl -i -X DELETE http://localhost:8080/api/counters/demo
curl -i -X DELETE http://localhost:8080/api/counters/demo
```

Both responses are `204 No Content`, with no body. Afterward, GET returns `404 Not Found`.

**Shell note:** single-quote syntax for JSON in the `curl` examples works in Bash, zsh, or modern PowerShell depending on version. In Windows PowerShell 5.1, `curl` is often an alias for `Invoke-WebRequest`; to run curl CLI syntax, invoke `curl.exe` and adjust PowerShell JSON quoting, or use `Invoke-RestMethod`.

### Mapping to Spring MVC annotations

| Spring MVC Annotation | HTTP Method | What to keep accurate |
|---|---|---|
| `@GetMapping` | GET | Do not use to cause client-requested business state changes |
| `@PostMapping` | POST | Handles tasks with side effects; retries must have a strategy |
| `@PutMapping` | PUT | Sets/replaces resource per contract; identical requests preserve intended effect |
| `@PatchMapping` | PATCH | Clearly define patch semantics and retryability |
| `@DeleteMapping` | DELETE | Repeating the same request preserves the deleted state |
| `@RequestMapping(method = RequestMethod.OPTIONS)` | OPTIONS | Customize only when needed, as the framework/server can handle it automatically |

An annotation only registers a handler; it **cannot automatically turn a balance-increment operation into an idempotent one** or turn a delete action into a safe one if the inner logic violates method semantics.

## 8. Retries: Why Is Idempotency Valuable in Distributed Systems?

Suppose a client sends a request to the server. The server **completes processing successfully**, but the connection drops before the client receives the response:

```text
Client                          Server
  | -------- PUT --------------> |
  |                              | resource updated
  |       X response lost        |
  |                              |
  | -------- PUT (retry) ------> |
  |                              | re-apply the same state
  | <------- response ---------  |
```

The client does not know whether the server processed the first attempt. If PUT honors idempotency, retrying the same request can achieve the same desired effect. If the request is a POST creating an order and is resent without deduplication, the client risks creating **two orders**.

Practical guidelines:

1. Only retry automatically when you truly understand the operation's semantics. HTTP treats idempotent methods as suitable candidates for retry on communication errors; for non-idempotent methods, do not retry blindly just because no response arrived.
2. Retries require timeouts, retry limits, backoff, and proper error-code handling. Idempotency does not mean infinite retries; nor do retries fix invalid data or validation errors.
3. For transactions prone to duplication (placing orders, payments, issuing commands), consider an **idempotency key**: the client generates a unique key for *one business intent* and resends the same key on retries; the server stores processing state/results by key and returns or handles them consistently. This is an application contract that must be designed explicitly: key scope, retention TTL, same key with a different payload, mid-step failures, and concurrent duplicate requests. Do not rely solely on an in-memory map for financial operations.
4. An idempotency key helps prevent duplicate execution of **the same identified request**, but does not automatically guarantee "exactly-once" behavior across the entire distributed system.
5. GET/HEAD and safe methods can also be affected by caching. **Safe, idempotent, and cacheable are three distinct properties**: for example, PUT is idempotent, yet PUT responses are not cacheable by default; GET can be cached under HTTP rules; caching does not replace duplicate-request protection.

Illustrative example of an application-specific contract—not a guarantee that all APIs support this header:

```http
POST /api/orders HTTP/1.1
Host: shop.example
Idempotency-Key: order-request-abc123
Content-Type: application/json

{"productId":42,"quantity":1}
```

A supporting server can detect retries with the same key and same content under published rules, avoiding creating a second order. If the payload changes while reusing the key, the server must have clear conflict-handling rules.

## 9. Idempotency Does Not Prevent Concurrent Update Overwrites

Suppose Lan and Minh both read a product at version 7. Lan renames the product; then Minh uses stale data to PUT the full state. Even though both PUTs are idempotent, Minh's update can still **overwrite** Lan's change.

HTTP supports conditional requests using `ETag` and `If-Match`. An illustrative workflow:

```http
GET /api/products/42 HTTP/1.1
Host: shop.example
```

The server returns an ETag, such as `"v7"`. The client sends an update:

```http
PUT /api/products/42 HTTP/1.1
Host: shop.example
If-Match: "v7"
Content-Type: application/json

{"name":"New name","active":true}
```

If the current representation has changed and the condition no longer holds, the server should return `412 Precondition Failed` (per If-Match semantics) instead of silently overwriting. The application must actually implement and check the precondition; adding a header on the client does not make the server handle it automatically in every controller design. Conditional requests add concurrency control, whereas idempotency addresses repeated requests.

## 10. Common Misconceptions

**Misconception 1 — “Idempotent means read-only.”** Incorrect. PUT and DELETE can both modify state yet remain idempotent.

**Misconception 2 — “Idempotent means every call returns 200 and the same body.”** Incorrect. A creating PUT may return 201 and a subsequent replacement return 200; a subsequent DELETE may return 404 instead of 204.

**Misconception 3 — “POST always creates, PUT always updates, PATCH is definitely idempotent.”** Incorrect. POST asks a resource to process per its semantics; PUT can create or replace; PATCH is not guaranteed idempotent.

**Misconception 4 — “GET only hits the server once, so it can be used to deduct money.”** Incorrect. Browsers, crawlers, cache validators, or prefetching can issue extra GETs. Charging money requires a properly authenticated and protected unsafe action.

**Misconception 5 — “Using `@PutMapping` makes Java logic automatically idempotent.”** Incorrect. If the controller increments a counter or inserts a new record on each call, its behavior violates PUT expectations.

**Misconception 6 — “Idempotency prevents all concurrent request bugs.”** Incorrect. Competing updates from multiple users require optimistic locking, conditional requests, or appropriate synchronization. Single-request idempotency does not guarantee system-wide serialization.

**Misconception 7 — “GET is safe, so the API can be public to everyone.”** Incorrect. Safety concerns state-change semantics; data access control is a separate responsibility.

**Misconception 8 — “Retrying POST only needs putting the same ID in the body.”** Insufficient unless the backend has a mechanism to identify, store, and handle duplicate requests per contract. Distinguishing a retry from a new action must be explicitly designed.

## 11. Self-Check Exercises

**Question 1.** Endpoint `PUT /api/settings/theme` always sets the theme to `dark`. Is sending it twice idempotent?  
**Explanation:** Yes, if the server performs the state assignment `theme=dark`; sending the same request again does not alter the desired business effect.

**Question 2.** Can endpoint `PATCH /api/users/42` always setting `active=true` be idempotent?  
**Explanation:** It can be, under the specific semantics of that patch operation. However, PATCH is not guaranteed by the standard to be idempotent for all kinds of changes.

**Question 3.** The first DELETE returns 204, and the second returns 404: does this violate idempotency?  
**Explanation:** No. The outcome after both calls is still that the resource is deleted/no longer exists.

**Question 4.** A GET returns 200 but also sends a purchase confirmation email. Does this GET comply with safety?  
**Explanation:** No, if sending the confirmation email is a business action triggered by calling GET and the client did not merely request a read.

**Question 5.** Can you automatically retry a payment POST immediately upon timeout?  
**Explanation:** You should not, unless you know whether the previous request was already processed and have a deduplication contract; otherwise it can cause duplicate transactions. You need an idempotency mechanism, status query, or system-supported business recovery.

**Question 6.** Are two idempotent PUTs guaranteed not to overwrite each other's data?  
**Explanation:** No. Consider using ETag/If-Match, optimistic locking, or an appropriate concurrency strategy.

## 12. Standard References

- [RFC 9110 – HTTP Semantics, Section 9: Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9): especially Section 9.2.1 (Safe Methods), 9.2.2 (Idempotent Methods), and 9.3 (Method Definitions).
- [RFC 5789 – PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html): PATCH semantics and why PATCH is not idempotent by default.
- [Spring Framework Reference – Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): controllers, request mapping, and how Spring MVC handles HTTP.

**Key takeaway:** *Safe* concerns whether the client requests a state change; *idempotent* concerns the intended effect when repeating the same request. GET/HEAD/OPTIONS/TRACE are safe and idempotent; PUT/DELETE are unsafe but idempotent; POST/PATCH are not guaranteed idempotent. Controller design, retries, and concurrency handling must respect these semantics.
