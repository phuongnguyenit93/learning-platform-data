# Simple requests vs. preflight OPTIONS

## 1. What problem does CORS solve at the API Gateway?

Suppose a web page running at `http://localhost:5173` calls an API through **Spring Cloud Gateway Server WebFlux** at `http://localhost:8080`:

~~~javascript
const response = await fetch("http://localhost:8080/api/orders/42");
const order = await response.json();
~~~

The two addresses share the same hostname but have **different ports**, so they are **different origins**. The browser enforces **Cross-Origin Resource Sharing (CORS)** to decide whether JavaScript code from the web page origin is allowed to **read the response** from the API origin. Since the Gateway is the entry point to microservices, it is usually the right place to publish the CORS policy for public APIs.

This lesson belongs to the **CORS** chapter of the **SPRING_CLOUD_GATEWAY** module. After distinguishing requests that do not need a preflight from requests that must send `OPTIONS` first, you will understand why an API can have valid route predicates, filter chains, path rewriting, header transformations, and service discovery yet the frontend still reports "blocked by CORS policy." The topic also connects to authentication, rate limiting, circuit breakers, retries, TLS, and observability: these policies must work alongside CORS without mistakenly treating preflight requests as business requests.

Lesson objectives:

1. Understand **origins** and the boundary where CORS is enforced.
2. Know the exact conditions for a cross-origin request to **skip preflight** (commonly called a *simple request*).
3. Read an `OPTIONS` flow with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
4. Configure Global CORS in Spring Cloud Gateway **Server WebFlux** 4.2/4.3 and 5.x.
5. Test simple GETs, JSON POSTs, requests with custom headers, rejected origins, and `OPTIONS` route-mismatch errors.
6. Avoid common CORS pitfalls when combining Spring Security, cookies/sessions, proxies, and caches.

> **Scope:** This lesson covers **CORS in browsers and Gateway Server WebFlux**. Gateway Server MVC uses a different namespace and integration mechanism. Configuration snippets must be used with a Spring Boot/Spring Cloud BOM compatible with your running version.

## 2. What is an origin, and does CORS apply to every HTTP client?

An origin is defined by the triple **scheme + hostname + port**. For example, given the web page `https://app.example.test`:

| API URL | Compared to page origin | Reason |
| --- | --- | --- |
| `https://app.example.test/api/orders` | Same origin | Scheme, host, and default port all match |
| `https://api.example.test/orders` | Cross-origin | Different host |
| `http://app.example.test/orders` | Cross-origin | Different scheme |
| `https://app.example.test:8443/orders` | Cross-origin | Different port |
| `https://app.example.test:443/orders` | Same origin | Port 443 is the default HTTPS port |

**CORS is a mechanism enforced by the browser.** The Gateway and backend return CORS headers; the browser evaluates them before allowing JavaScript code to access the response. Clients such as `curl`, Postman, or service-to-service HTTP clients typically **do not block** responses based on CORS. A `curl` command returning 200 does not prove a browser will let the frontend read the response.

**CORS is not authentication or authorization.** Any non-browser HTTP client can still call the API if the network and security layer permit it. Never treat `Access-Control-Allow-Origin` as a list of users authorized to access data. For a "simple" request, the browser may **send the actual request to the server first** and only block JavaScript from reading the response afterward; therefore CORS does not replace CSRF protection either.

### Site vs. origin

`https://app.example.test` and `https://api.example.test` are cross-origin, yet they can be same-*site* under `SameSite` cookie rules. CORS controls **cross-origin response access**; `SameSite` controls **the context in which cookies are sent**. The two concepts are related but not interchangeable.

## 3. What is a simple request?

The name "simple request" is a historical term commonly used for a **CORS request that does not require a preflight**. A request must satisfy **all** relevant conditions of the Fetch/CORS specification, not merely use GET or POST.

### 3.1. Method must be in the allowed list

Only the following methods are CORS-safelisted:

- `GET`
- `HEAD`
- `POST`

`PUT`, `PATCH`, `DELETE`, and many other methods are **not** in this group, so a browser cross-origin call typically requires a preflight.

### 3.2. Application-set headers must be safelisted

Request headers that application code can normally set without triggering a preflight on their own—**provided their values also satisfy the spec's limits**—include:

| Header | Notes |
| --- | --- |
| `Accept` | Value must satisfy character and length limits |
| `Accept-Language` | Value must satisfy allowed character set rules |
| `Content-Language` | Same restrictions as `Accept-Language` |
| `Content-Type` | Only certain safelisted media types, see below |
| `Range` | Only a single validly formatted byte range |

Headers controlled automatically by the browser, such as `Origin` and certain connection headers, do not count as "you added a custom header" to trigger a preflight. Conversely, setting `Authorization: Bearer ...`, `X-Request-Id`, or `X-Api-Key` in application code usually forces the browser to **send a preflight**.

Value constraints such as forbidden characters, header length limits, `Range` rules, and Safari-specific behavior can make a request non-safelisted even when the **header name** is in the list. Thus, the table above is a baseline rule, not a blank check for any value.

### 3.3. Which Content-Types are allowed for POST?

For `Content-Type` used by a request to be safelisted, its media type must be one of:

~~~text
application/x-www-form-urlencoded
multipart/form-data
text/plain
~~~

Media type parameters (such as `charset=utf-8` or form boundaries) do not change the media type's category on their own, though header value limits still apply.

**`Content-Type: application/json` is not safelisted.** Consequently, a cross-origin JSON `POST` from `fetch` normally triggers a preflight even though `POST` is a safelisted method.

### 3.4. Other conditions

With `XMLHttpRequest`, attaching a listener on `xhr.upload` can disqualify the request from being simple. Using a `ReadableStream` as the request body can also trigger a preflight. To evaluate rare edge cases accurately, consult the Fetch/CORS documentation for your target browsers rather than relying on rules of thumb like "POST + text/plain is guaranteed simple."

### Quick classification table

| Cross-origin browser request | Preflight needed? | Why |
| --- | --- | --- |
| `GET /api/orders/42` with only safelisted headers | **Usually no** | Method and headers are safelisted |
| `HEAD /api/orders/42` | **Usually no** | HEAD is safelisted |
| `POST` with `Content-Type: application/x-www-form-urlencoded`, no custom headers | **Usually no** | POST and media type are safelisted |
| `POST` with `Content-Type: text/plain` | **Usually no** | Media type is safelisted, assuming other conditions hold |
| `POST` with `Content-Type: application/json` | **Yes** | JSON is not safelisted |
| `GET` with `Authorization: Bearer ...` | **Yes** | `Authorization` header is not safelisted |
| `GET` with custom `X-Request-Id` | **Yes** | Custom header |
| `PUT`, `PATCH`, or `DELETE` | **Yes** | Method is not safelisted |

> **Do not confuse:** A **same-origin** JSON `POST` does not need a CORS preflight because it is not a cross-origin CORS request. The rules above apply when the browser issues a CORS-scoped request, not universally to all HTTP requests.

## 4. Simple request flow: send first, then check the response

A simple cross-origin request proceeds like this:

~~~mermaid
sequenceDiagram
    participant P as Browser (http://localhost:5173)
    participant G as Gateway (http://localhost:8080)
    participant B as orders-service
    P->>G: GET /api/orders/42<br/>Origin: http://localhost:5173
    G->>B: GET /orders/42
    B-->>G: 200 + JSON
    G-->>P: 200 + JSON<br/>Access-Control-Allow-Origin: http://localhost:5173
    Note over P: Valid CORS → JavaScript reads response
~~~

Characteristics:

1. The browser sends the **actual request immediately**, without sending `OPTIONS` first.
2. The browser attaches `Origin` so the server/Gateway can evaluate it.
3. The Gateway handles routing/filtering as usual, and the backend actually receives the request.
4. The browser inspects the response, especially `Access-Control-Allow-Origin`. If disallowed, JavaScript **cannot read the response**, yet the request may **already have caused side effects on the backend**.

Example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Accept: application/json
~~~

Illustrative valid response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"id":"42","state":"READY"}
~~~

If the response lacks the required CORS header or returns a different origin, the browser can still receive **HTTP 200 at the network layer** while denying JavaScript access to the body. This explains why DevTools shows status 200 in the Network tab while the console reports a CORS error.

## 5. Preflight flow: the browser asks first with OPTIONS

For non-simple requests (such as a JSON POST or a request with custom headers), the browser sends an HTTP **`OPTIONS` preflight** to the target URL to ask the server whether it permits the **method and headers of the actual request**.

~~~mermaid
sequenceDiagram
    participant P as Browser
    participant G as Gateway WebFlux
    participant B as orders-service
    P->>G: OPTIONS /api/orders/42<br/>Origin: http://localhost:5173<br/>Access-Control-Request-Method: POST<br/>Access-Control-Request-Headers: content-type,x-request-id
    G-->>P: 200/204 + CORS allow headers
    Note over P: Valid preflight → send actual request
    P->>G: POST /api/orders/42<br/>Content-Type: application/json<br/>X-Request-Id: lab-42
    G->>B: POST /orders/42 + JSON
    B-->>G: 200 + JSON
    G-->>P: 200 + Access-Control-Allow-Origin
    Note over P: Check CORS on actual response before exposing to JS
~~~

### 5.1. What does an OPTIONS request look like?

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

Three core fields:

- `Origin`: origin of the calling page.
- `Access-Control-Request-Method`: method of the **actual request** the browser wants to send—here `POST`; the **preflight's** own method remains `OPTIONS`.
- `Access-Control-Request-Headers`: list of non-safelisted request header names the browser intends to send in the actual request; may be omitted if preflight was triggered solely by method.

**Preflight carries no business payload** and by specification **does not send credentials like session cookies**. Therefore, never require preflights to carry session cookies or tokens like the actual request.

### 5.2. What does a valid preflight response require?

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Status can be **200** or **204**, depending on the framework and configuration. What matters is protocol success and CORS headers permitting the corresponding origin, method, and headers. A successful preflight **is not** success of the actual POST: the browser still has to send the actual request and then check CORS on the actual response.

`Access-Control-Max-Age` tells the browser how long it may **cache the preflight result** (in seconds). Browsers may cap this value by internal policy; the preflight cache is **distinct** from normal HTTP response caching. Thus, not seeing an OPTIONS request before **every** JSON POST is normal: the browser can reuse an unexpired preflight entry.

### 5.3. Distinguishing a generic OPTIONS from a CORS preflight

HTTP `OPTIONS` does not automatically mean a CORS preflight. A valid preflight is normally identified by `Origin` **and** `Access-Control-Request-Method`. Calling:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42"
~~~

is just a plain OPTIONS request, **not** a complete preflight simulation. You must send the required headers to test the CORS policy.

## 6. Key CORS headers to read accurately

| Header | Where it appears | Meaning |
| --- | --- | --- |
| `Origin` | Actual request and preflight | Origin from which the browser is making the request |
| `Access-Control-Request-Method` | Preflight request | Method of the actual request |
| `Access-Control-Request-Headers` | Preflight request | Header names the actual request wants to use |
| `Access-Control-Allow-Origin` | Preflight response **and** actual response | Origin permitted to read the response |
| `Access-Control-Allow-Methods` | Primarily preflight response | Methods permitted by the server under CORS |
| `Access-Control-Allow-Headers` | Primarily preflight response | Accepted request headers |
| `Access-Control-Allow-Credentials` | Response when supporting credentials | Permits the browser to expose credentialed responses per CORS rules |
| `Access-Control-Expose-Headers` | Actual response | Non-safelisted response headers that JavaScript may read |
| `Access-Control-Max-Age` | Preflight response | Duration for caching the preflight result |
| `Vary` | Cacheable response | Distinguishes cached responses by origin/requested method/headers as needed |

### 6.1. Access-Control-Expose-Headers does not grant permission to send headers

`Access-Control-Allow-Headers` permits **request headers** that the frontend wants to send, such as `Authorization` or `X-Request-Id`. Meanwhile, `Access-Control-Expose-Headers` lets JavaScript **read response headers** such as `X-Gateway-Route` or `X-Trace-Id`. The two headers are not interchangeable.

For example, the browser normally cannot read `X-Gateway-Route` via `response.headers.get("X-Gateway-Route")` unless the response exposes it, even though the header is visible in the DevTools Network tab.

### 6.2. Credentials and wildcards

With cookies/sessions or requests using credentials mode:

- The frontend may need `fetch(..., { credentials: "include" })`.
- The CORS response needs `Access-Control-Allow-Credentials: true` if the browser is to expose a credentialed response.
- **Never** use `Access-Control-Allow-Origin: *` for credentialed responses; return a **specific origin** from the allowlist.
- Cookie `SameSite`/`Secure` policies, third-party cookie restrictions, and CSRF still apply independently of CORS.

Do not enable `allowCredentials: true` for all APIs just to "make CORS errors go away." For APIs using bearer tokens or API keys, determine how credentials are issued/attached and the actual security policy before choosing `allowCredentials`.

### 6.3. Null origin and wildcard configurations

Some contexts such as `file://` or sandboxed documents produce `Origin: null`. Never casually add `null` to an allowlist for sensitive APIs. Wildcard `*` is only suitable for certain public APIs without credentials or private access data; it is **not** a safe default for every Gateway.

## 7. Global CORS in Spring Cloud Gateway Server WebFlux

Spring Cloud Gateway supports **global CORS configuration** and **per-route CORS metadata**, built on Spring Framework's `CorsConfiguration`. With a Gateway sitting in front of multiple microservices, design **one clear source of CORS policy** so the Gateway and backends do not emit conflicting headers.

### 7.1. Gateway Server WebFlux 5.x configuration example

Suppose the frontend runs at `http://localhost:5173`, the Gateway at `localhost:8080`, and the backend at `localhost:9091`. Configuration in `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: cors-gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          globalcors:
            add-to-simple-url-handler-mapping: true
            cors-configurations:
              '[/api/orders/**]':
                allowedOrigins:
                  - http://localhost:5173
                allowedMethods:
                  - GET
                  - POST
                allowedHeaders:
                  - Content-Type
                  - X-Request-Id
                  - Authorization
                exposedHeaders:
                  - X-Gateway-Route
                allowCredentials: false
                maxAge: 600

          routes:
            - id: orders-route
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Gateway-Route, orders-route
~~~

Explanation:

- `globalcors.cors-configurations` defines the CORS policy by the **public path** called by the browser—here `/api/orders/**`.
- `allowedOrigins` permits **exact** `http://localhost:5173`. `https://localhost:5173` or `http://localhost:3000` are **different** origins.
- `allowedMethods` permits the browser to request GET/POST; **you do not need to add `OPTIONS` to this list just for POST preflight checks**.
- `allowedHeaders` allows `Content-Type`, `X-Request-Id`, and `Authorization` requested during preflight; this does not grant backend access permissions.
- `exposedHeaders` lets JavaScript read `X-Gateway-Route` from the actual response.
- `allowCredentials: false` fits this lab because no cookies/sessions are used; authenticated applications may require a different design.
- `maxAge: 600` suggests browser preflight caching for 600 seconds, subject to browser limits.
- `StripPrefix=1` causes the backend to receive `/orders/42`; CORS is still evaluated against the external request `/api/orders/42`.

### 7.2. Why is add-to-simple-url-handler-mapping needed?

The route above has the predicate:

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET,POST
~~~

A browser preflight sends the **`OPTIONS`** HTTP method, not GET/POST. Since `Method=GET,POST` **does not match**, the preflight request may not enter the standard route handler and therefore cannot locate that route's CORS config.

Spring Cloud Gateway provides:

~~~yaml
globalcors:
  add-to-simple-url-handler-mapping: true
~~~

so the same global CORS configuration is also registered with a **`SimpleUrlHandlerMapping`** in WebFlux, which helps when preflight **does not match a route predicate**. This refers to the framework class `SimpleUrlHandlerMapping` and **is unrelated to the CORS "simple request" concept** despite sharing the word "simple."

This property defaults to `false` in the referenced versions. When enabled, matching preflights can be answered at the Gateway/WebFlux layer **without forwarding a business `OPTIONS` request to the backend**.

> **Not a trick to open all OPTIONS:** You must still restrict allowed origins/methods/headers and paths. When using Spring Security, verify the security layer does not block preflights ahead of the CORS handler.

### 7.3. Gateway WebFlux 4.2.x / 4.3.x equivalent

Official WebFlux 4.2 and 4.3 documentation uses the `spring.cloud.gateway.globalcors` and `spring.cloud.gateway.routes` namespaces:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/api/orders/**]':
            allowedOrigins:
              - http://localhost:5173
            allowedMethods:
              - GET
              - POST
            allowedHeaders:
              - Content-Type
              - X-Request-Id
              - Authorization
            exposedHeaders:
              - X-Gateway-Route
            allowCredentials: false
            maxAge: 600
      routes:
        - id: orders-route
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
            - Method=GET,POST
          filters:
            - StripPrefix=1
            - AddResponseHeader=X-Gateway-Route, orders-route
~~~

Do not duplicate `routes` or `globalcors` definitions across both namespaces. **Choose the right version** and confirm the configuration is actually loaded by the Gateway. If using Gateway Server MVC, do not copy WebFlux configuration directly to MVC.

## 8. Per-route CORS and avoiding conflicting configurations

If the API serves multiple frontend groups or distinct policies, the Gateway supports CORS via route metadata:

~~~yaml
# Place this snippet inside an item under routes:
id: public-report
uri: http://localhost:9091
predicates:
  - Path=/api/reports/**
metadata:
  cors:
    allowedOrigins:
      - https://reports.example.test
    allowedMethods:
      - GET
    allowedHeaders:
      - Accept
    maxAge: 300
~~~

Place the route snippet above under the appropriate `routes` namespace for your version. Metadata CORS attaches to the matched route. For routes with narrow method predicates that exclude `OPTIONS`, **global CORS with `add-to-simple-url-handler-mapping`** is usually easier to verify for preflights.

Decide clearly which policies are owned by the **Gateway** and which by the **backend**. If both write `Access-Control-Allow-Origin` or `Access-Control-Allow-Credentials`, the response may contain **duplicate or conflicting headers** that cause the browser to reject it, even when the backend returns 200.

Spring Cloud Gateway includes `DedupeResponseHeader`, which can clean up duplicate CORS headers in certain cases. However, **deduplication does not resolve policy disagreements**: if the Gateway allows origin A while the backend allows origin B, fix the configuration on both sides rather than relying on deduplication to mask the discrepancy.

## 9. Lab: WebFlux backend with GET and POST endpoints

Create a Spring Boot backend application at `localhost:9091` with the `spring-boot-starter-webflux` dependency. The backend simply returns JSON so you can see that the **actual request** arrived. Do not add CORS configuration to the backend in this lab so the Gateway acts as the sole source of CORS policy.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091
~~~

`src/main/java/demo/orders/OrdersApplication.java`:

~~~java
package demo.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`src/main/java/demo/orders/OrdersController.java`:

~~~java
package demo.orders;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    @GetMapping("/orders/{id}")
    public Map<String, Object> getOrder(
            @PathVariable String id,
            ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", "GET");
        result.put("id", id);
        result.put("path", request.getPath().value());
        return result;
    }

    @PostMapping("/orders/{id}")
    public Mono<Map<String, Object>> updateOrder(
            @PathVariable String id,
            @RequestBody Mono<Map<String, Object>> body,
            ServerHttpRequest request) {
        return body.map(payload -> {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("method", "POST");
            result.put("id", id);
            result.put("path", request.getPath().value());
            result.put("requestId",
                    request.getHeaders().getFirst("X-Request-Id"));
            result.put("body", payload);
            return result;
        });
    }
}
~~~

This is an **echo endpoint** that stores no data; in production, never expose endpoints that echo sensitive bodies or headers. Since this exercise only verifies CORS, it does not require service discovery, load balancing, or sessions.

Run the backend and Gateway in **two separate terminals**:

~~~bash
# Inside the WebFlux backend project
./mvnw spring-boot:run

# Inside the Gateway WebFlux project
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run` or an installed Maven binary. The Gateway needs the WebFlux starter and a compatible BOM; newer versions typically name the starter `spring-cloud-starter-gateway-server-webflux`, whereas earlier versions used `spring-cloud-starter-gateway`.

### 9.1. Testing a simple GET with curl

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Accept: application/json"
~~~

Expect a 200 status, a body describing the order, and headers:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
X-Gateway-Route: orders-route
~~~

No separate `OPTIONS` occurs in this `curl` invocation; when a browser sends the same GET under simple conditions, it likewise typically skips preflight. For JavaScript to read `X-Gateway-Route`, the response can include:

~~~http
Access-Control-Expose-Headers: X-Gateway-Route
~~~

### 9.2. Simulating preflight for a JSON POST with X-Request-Id

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id"
~~~

Expect a **2xx** response (usually 200 with Spring/WebFlux) and allow headers:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Max-Age: 600
~~~

Ordering and casing of methods and headers may differ. The preflight should be handled by Gateway/WebFlux; **the backend does not need to receive the OPTIONS request** for the subsequent POST to be sent. Check backend access logs if you want to confirm this.

After preflight, send the actual request:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: lab-42" \
  --data-binary '{"quantity":2,"confirmed":true}'
~~~

Expect a response with `Access-Control-Allow-Origin: http://localhost:5173` and JSON similar to:

~~~json
{
  "method": "POST",
  "id": "42",
  "path": "/orders/42",
  "requestId": "lab-42",
  "body": {
    "quantity": 2,
    "confirmed": true
  }
}
~~~

**Limitation of curl:** These commands only simulate **two separate HTTP requests** and let you inspect headers. `curl` does not enforce browser CORS policy, nor does it automatically fire a POST after OPTIONS succeeds. To verify that a browser executes preflight, use a real page served from another origin.

### 9.3. Using the browser to observe both round-trips

In a web page running on `http://localhost:5173`, open DevTools → Network and run:

~~~javascript
// Simple GET: typically only a GET request.
const a = await fetch("http://localhost:8080/api/orders/42");
console.log(await a.json());

// JSON POST + custom header: typically sends OPTIONS before POST.
const b = await fetch("http://localhost:8080/api/orders/42", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "lab-42"
  },
  body: JSON.stringify({ quantity: 2, confirmed: true })
});
console.log(await b.json());
~~~

Observe the `OPTIONS` entry in the Network tab, the preflight `Access-Control-Request-*` headers, and the response `Access-Control-Allow-*` headers. If `OPTIONS` does not appear on a second call, the browser may be using its **preflight cache**. Try a different URL/header combination, a fresh browser context, or wait for the cache entry to expire to verify without disabling security controls.

### 9.4. Testing disallowed origins and headers

~~~bash
# Origin outside allowedOrigins
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:9999" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"

# X-Admin-Flag header not in allowedHeaders
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-admin-flag"
~~~

Spring may reject the preflight with **403 Invalid CORS request** depending on version/configuration; do not assume a single exact status across every setup. **What matters to confirm** is that the response does not grant invalid CORS permission, and that the browser does not send the actual POST request after an invalid preflight.

A simple GET from a rejected origin **can still reach the backend and return 200 over the network**, yet JavaScript is blocked from reading the response. This is the crucial difference between **blocking a preflight before the actual request** and **blocking response access on a simple request**.

## 10. Why does OPTIONS often return 401/403/404 in the Gateway?

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| `OPTIONS` 404 while GET returns 200 | Route has `Method=GET,POST` so OPTIONS does not match; CORS config is not on the handler receiving OPTIONS | Enable `globalcors.add-to-simple-url-handler-mapping=true` per version with the matching path pattern |
| `OPTIONS` 401 | Spring Security requires auth on preflight, which carries no cookies/session | Ensure CORS runs **before** authentication; configure Security/`CorsWebFilter` properly |
| `OPTIONS` 403 | Origin, requested method, or headers are disallowed; or rejected by security filter | Compare `Origin` and `Access-Control-Request-Method/Headers` against allowlist and logs |
| GET 200 yet browser reports CORS | Actual response lacks `Access-Control-Allow-Origin`, has duplicates, or origin mismatches | Inspect GET response headers and policies at Gateway/backend |
| CORS headers present yet browser rejects cookies | `Access-Control-Allow-Origin=*` with credentials, missing allow-credentials, or invalid SameSite/Secure/CORS credentials | Configure explicit origin + credentials and verify cookie storage |
| Only JSON POST fails | JSON triggers preflight; header or method is not yet allowed | Inspect OPTIONS first, then the actual POST |
| API succeeds with `curl` | `curl` does not enforce CORS | Test in a real browser from another origin |
| Intermittent CORS failures | CDN/reverse proxy caches responses without varying by Origin, or Gateway/backend emit duplicate headers | Check `Vary`, cache policies, and CORS ownership per layer |

### 10.1. Spring Security WebFlux must handle preflight in the right position

Spring Security documentation emphasizes that **CORS must be processed before Security** because preflight does not carry session cookies. If an `OPTIONS` request is blocked by the authentication layer before the CORS handler evaluates it, even a valid Gateway `globalcors` configuration may not suffice.

In **reactive WebFlux**, the relevant classes are `CorsWebFilter` and `SecurityWebFilterChain`; **do not copy Servlet MVC `CorsFilter` examples verbatim** into Gateway WebFlux. Ensure Spring Security integrates with the `CorsConfigurationSource`/CORS processor suited to your version, and avoid creating two competing CORS sources writing headers. You may need security-chain rules for preflight, but that does not mean permitting **all Internet OPTIONS traffic** to bypass non-CORS controls.

### 10.2. Is CORS tied to route predicates or filter order?

Yes. The Gateway applies **route-specific CORS metadata** only if a matching handler/route is resolved. When a `Method` predicate excludes `OPTIONS`, `add-to-simple-url-handler-mapping` ensures **global CORS** also covers requests not matched by route predicates.

Gateway filters such as `StripPrefix`, `SetRequestHeader`, or `Retry` **are not substitutes for a CORS processor**. In a proper flow, preflight is answered at the CORS layer **without forwarding OPTIONS to the microservice**; only the actual request proceeds through routes, filters, and the LoadBalancer when permitted.

If you require the backend to handle `OPTIONS`, ensure the request actually reaches the backend and returns proper headers; however, with the Gateway acting as an API facade, configuring CORS at the Gateway usually makes centralized policy enforcement easier.

## 11. Security and operational pitfalls

### 11.1. CORS does not prevent CSRF

A simple request can be sent by the browser **even when reading the response is disallowed**. A cross-site form POST can trigger side effects if the server relies solely on cookies without CSRF protection. A proper `SameSite` policy is a helpful defense-in-depth measure, not a replacement for CSRF tokens and authorization.

### 11.2. Access-Control-Allow-Origin is not a user list

Allowing `https://app.example.test` to read a response does not mean every user on that origin is authorized to view orders. The backend must still verify tokens/sessions, order ownership, and business authorization. Never trust the `Origin` header as an identity credential: non-browser clients can send any `Origin` they choose.

### 11.3. Cookies and CORS credentials are two independent controls

`Access-Control-Allow-Credentials: true` does not force the browser to send cookies blocked by `SameSite` or third-party cookie policies. Likewise, `credentials: "include"` on the frontend does not override cookie `Secure`/`Domain`/`Path` rules. For credentialed requests, return a specific origin and `Vary: Origin` whenever responses may be cached by origin.

### 11.4. Do not let Gateway and backend emit conflicting policies

If the Gateway returns `Access-Control-Allow-Origin: http://localhost:5173` while the backend also returns `Access-Control-Allow-Origin: *`, the response may contain multiple ACAO values and be rejected by the browser. Prefer **a single primary owner**. The Gateway offers the `DedupeResponseHeader` filter to resolve duplicates in some situations, but it cannot fix an incorrect or overly broad policy; fix the policy at the source.

### 11.5. Proxies, TLS, and caching

If HTTPS terminates at the ingress while the Gateway receives internal HTTP, the browser's public origin still uses the HTTPS scheme; CORS policies must match the **real frontend origin**, not the backend scheme. `Forwarded` and `X-Forwarded-*` headers must be normalized by trusted proxies; never use client-supplied headers to widen a CORS allowlist.

The preflight cache is managed by the **browser** under specific conditions and caps. Proxies/CDNs can also cache HTTP responses; adding `Vary: Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` where appropriate prevents serving cached responses for the wrong origin/method/headers combination.

### 11.6. Retries, rate limiters, and circuit breakers

Preflight is not an order-creation business request. Track it separately in metrics so it does not skew request volume/latency or consume business quotas improperly. If `OPTIONS` is forwarded and uselessly retried, backends receive unnecessary traffic; if a rate limiter blocks `OPTIONS` ahead of CORS, the browser may report a CORS error rather than a useful 429 status.

For actual POST requests, retries must still consider idempotency to avoid duplicate writes. Circuit breakers and discovery/load balancing manage paths to backends, not browser cross-origin access rights.

## 12. Pre-release verification checklist

- [ ] **Frontend origin** identified by scheme + hostname + port, not hostname alone.
- [ ] Identified which requests are simple vs. requiring preflight based on **method + headers + Content-Type + other conditions**.
- [ ] Using the right **Gateway Server WebFlux** 4.x or 5.x CORS namespace.
- [ ] Policy defines appropriate allowed origins, methods, headers, exposed headers, credentials, and max age; no arbitrary `*`.
- [ ] Tested `OPTIONS` with full `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
- [ ] For routes with `Method=GET,POST`, verified preflight is handled by global CORS via `add-to-simple-url-handler-mapping` when needed.
- [ ] Preflight is not blocked by auth filters or rate limiters before the proper CORS layer.
- [ ] Actual requests (GET/POST) hit the expected route, path rewrite, headers, and backend instance.
- [ ] Actual responses also include valid CORS headers, not only preflight responses.
- [ ] Credentialed response configurations never use `Access-Control-Allow-Origin: *`.
- [ ] Browser successfully reads the response in DevTools/JavaScript; not relying solely on HTTP 200 from curl.
- [ ] Gateway and backend do not emit duplicate or conflicting CORS headers.
- [ ] CSRF, authentication, and authorization are enforced independently of CORS.
- [ ] Metrics/traces distinguish preflights from actual requests; logs omit tokens, cookies, and sensitive data.

## 13. Official references

1. [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): simple request conditions, preflight, response headers, credentials, and browser examples.
2. [MDN — CORS-safelisted request header](https://developer.mozilla.org/en-US/docs/Glossary/CORS-safelisted_request_header): specific restrictions on header names, values, and lengths.
3. [Spring Cloud Gateway Server WebFlux 5.x — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html): globalcors, per-route metadata, and `add-to-simple-url-handler-mapping`.
4. [Spring Cloud Gateway Server WebFlux 4.3.x — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/cors-configuration.html): `spring.cloud.gateway.globalcors` namespace.
5. [Spring Cloud Gateway 4.2.x — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/cors-configuration.html): previous WebFlux version namespace.
6. [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): how HandlerMapping handles preflight and actual CORS.
7. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): `CorsWebFilter` and ordering CORS before Security.

**Takeaway:** **Simple cross-origin requests are sent directly by the browser**, which then checks CORS on the response. **Requests requiring preflight send `OPTIONS` first**, asking permission for the method/headers before sending the actual request if allowed. In Spring Cloud Gateway Server WebFlux, configure global CORS by origin/path, handle `OPTIONS` requests that miss predicates, coordinate properly with Spring Security, and always remember: **CORS does not replace authentication, authorization, or CSRF protection**.
