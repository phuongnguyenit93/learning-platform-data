# forward() to a Local Handler in the Web MVC Variant

## 1. Context: Handing Off Locally Instead of Calling Another HTTP Service

In a microservices system, **Spring Cloud Gateway** typically accepts requests at the entry point, selects routes via predicates, applies filter chains, modifies paths/headers, forwards to services via discovery/load balancing, and combines authentication, rate limiting, circuit breakers, retries, TLS, and observability. However, not every request needs to call another microservice over HTTP.

In some cases, you want a request to pass through an **edge controller**, check a simple business condition, and then **transfer handling to another MVC handler inside the exact same application**. For example:

- The client calls `GET /edge/products/42`.
- The edge controller validates the input and decides to use a local handler.
- The local handler `GET /internal/products/42` returns JSON.
- The client sees only the response of that single HTTP request, and the browser URL remains `/edge/products/42`.

In **Spring Cloud Gateway Proxy Exchange for Spring Web MVC**, the `ProxyExchange` object supports **`forward(String)`** for this style of handoff. This is the topic **“forward() to a Local Handler in the Web MVC Variant”**, in the **Proxy Exchange** chapter of the **SPRING_CLOUD_GATEWAY** module.

This lesson helps you:

1. Distinguish **Proxy Exchange MVC**, **Gateway Server Web MVC**, and **Gateway Server WebFlux**.
2. Understand how **server-side forward** differs from an HTTP redirect and a remote HTTP proxy.
3. Write a `@Controller` using `ProxyExchange<byte[]>` and `forward("/internal/...")`.
4. Write a local `@RestController` handler that serves the forwarded request in Spring MVC.
5. Understand HTTP methods, request bodies, Servlet request attributes, and response lifecycles during forwarding.
6. Test with `MockMvc`, HTTP integration tests, and `curl`; detect forward loops, mapping mismatches, missing security, and content negotiation bugs.
7. Decide when to use forwarding, when to use an HTTP proxy, and when to call a Java service directly.

> **Version scope:** current Spring Cloud Gateway docs distinguish two **flavors**: *Server* and *Proxy Exchange*. This example uses **Proxy Exchange Web MVC**, with artifact `spring-cloud-gateway-proxyexchange-webmvc` in recent releases (such as 4.3/5.x). Some older releases used `spring-cloud-gateway-mvc`. Do not confuse it with Gateway Server Web MVC's **`spring-cloud-starter-gateway-server-webmvc`** starter. APIs and packages must be verified against your active release train.

## 2. First: Three Forwarding Styles That Look Similar but Differ Fundamentally

### 2.1. Comparing Forward, Redirect, and Proxy

| Mechanism | Who Performs the Handoff? | New HTTP Request From Browser? | Crosses Network to Another Service? | Browser URL Changes? |
| --- | --- | --- | --- | --- |
| **MVC internal forward** | Server/Servlet container inside the same app | No | No, when targeting a local handler | No |
| **HTTP redirect 302/307/308** | Browser/client reads `Location` and re-requests | Yes | Depends on destination | Usually yes |
| **Remote proxy via `ProxyExchange.uri(...).get()`** | Gateway app makes an outbound HTTP call | No *second browser request*, but there is a Gateway-to-backend request | Yes | No |
| **Direct Java service call** | Controller calls a method/service in the same JVM | No | No | No |

A common point of confusion: both **forward** and **remote proxy** keep a single public URL visible to the client. However, **proxy** creates an extra outbound HTTP request subject to DNS/TLS, connection pools, timeouts, and upstream statuses. **Forward** dispatches to a local handler in the same Servlet application and needs no service discovery.

### 2.2. `forward()` Flow Diagram

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP Client
    participant D as Spring MVC DispatcherServlet
    participant E as Edge Controller
    participant I as Internal Controller
    C->>D: GET /edge/products/42
    D->>E: Match @GetMapping
    E->>D: proxy.forward("/internal/products/42")
    Note over D: Internal forward inside Servlet application
    D->>I: Dispatch GET /internal/products/42
    I-->>D: 200 + JSON
    D-->>C: 200 + JSON
    Note over C,D: No Location redirect and no second client GET
~~~

The diagram depicts the **logical processing path**. Exactly how Spring MVC resolves forward views and how the Servlet `RequestDispatcher` operates depends on the implementation and container/view-resolver configuration. Do not use this diagram to assume every `Filter`/Spring Security chain re-runs identically on the second dispatch.

### 2.3. Why Is `forward()` Not `forward:///...`?

Spring Cloud Gateway **Server WebFlux** has routes like `uri: forward:///localendpoint` and `ForwardRoutingFilter`, handled via the reactive `DispatcherHandler`. That is a **Server WebFlux API**.

In this lesson we use an **MVC controller argument**:

~~~java
ProxyExchange<byte[]> proxy
~~~

and the method:

~~~java
proxy.forward("/internal/products/42")
~~~

Both mechanisms target local handling, yet **do not share the same runtime, filter chain, or API**. Never drop WebFlux's `forward:///...` config into an annotation-based MVC controller expecting `ProxyExchange.forward()` to run automatically.

## 3. Distinguishing the Two “MVC” Branches of Spring Cloud Gateway

This is the easiest place to pick the wrong dependency:

| Aspect | **Proxy Exchange Web MVC** (This Lesson) | **Gateway Server Web MVC** |
| --- | --- | --- |
| Purpose | Add proxying/forwarding inside **annotation-based controllers** | Build a full **API Gateway Server** with route predicates/filters |
| Java entry point | `@GetMapping`, `@PostMapping`, `ProxyExchange<T>` | `RouterFunction<ServerResponse>`, `GatewayRouterFunctions.route()` |
| Signature local forward | `ProxyExchange.forward(String)` | Server MVC handler/filter mechanism, not this argument API |
| Remote proxy | `proxy.uri(url).get()`, `.post()`... | `HandlerFunctions.http()` with target URI/filters |
| Current artifact | `spring-cloud-gateway-proxyexchange-webmvc` | `spring-cloud-starter-gateway-server-webmvc` |
| Runtime | Servlet / Spring MVC annotation handlers | Servlet / Spring WebMvc.fn |
| Applies all Gateway Server filters? | **No** | Has Server MVC's filter/predicate ecosystem per version |
| Uses `spring.cloud.gateway.server.webmvc.routes` YAML? | Not required for `ProxyExchange` injection | Available in matching Server Web MVC versions |

**Proxy Exchange docs clearly state this is an alternative gateway style; Gateway Server docs do not automatically apply to it.** Therefore, adding the Proxy Exchange module to a Spring MVC application **does not automatically give you** Gateway Server's route-definition repository, `GatewayFilterChain`, `RedisRateLimiter`, or circuit breakers.

Even without those server filters by default, the app can still use **Spring Security MVC**, Servlet filters, Java services, validation, tracing, metrics, or other resilience libraries. However, they must be configured separately and tested.

## 4. Dependencies and Project Structure

### 4.1. Maven for Current Proxy Exchange Web MVC

In an application already managing compatible Spring Boot/Spring Cloud BOMs:

~~~xml
<!-- Spring MVC Servlet application -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<!-- Proxy Exchange for MVC annotation-based controllers -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>
~~~

Do not specify an independent version for the Gateway artifact when using the Spring Cloud BOM. Spring Boot and Spring Cloud are not libraries you can always upgrade piecemeal; pick a **compatible release train** matching your project's runtime (Java/Spring Framework).

In releases prior to the module rename, the dependency may be:

~~~xml
<!-- Old name, only when your release train actually uses it -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-mvc</artifactId>
</dependency>
~~~

Do not add **old artifact + new artifact + Gateway Server Web MVC** together into a lab just “to make sure forward works”: duplicate or mixed-flavor dependencies complicate startup and debugging.

### 4.2. Illustrative Java Class Organization

~~~text
src/main/java/example/proxy/
  ProxyForwardApplication.java
  EdgeForwardController.java
  InternalProductsController.java
~~~

The code blocks below are designed as one small application. Place them in the same base package `example.proxy`, or ensure component scan covers all controllers.

## 5. Complete Example: GET From Public URL to Local Handler

### 5.1. Spring Boot Application

~~~java
package example.proxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyForwardApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyForwardApplication.class, args);
    }
}
~~~

Optional port configuration:

~~~yaml
server:
  port: 8080
~~~

You do not need Redis, Eureka, Config Server, or another HTTP upstream to try **internal forwarding**. Both the edge controller and the target controller run inside **the same Spring MVC application**.

### 5.2. Edge Controller: Use `@Controller`, Not `@RestController`

~~~java
package example.proxy;

import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class EdgeForwardController {

    @GetMapping("/edge/products/{id}")
    public String product(
            @PathVariable("id") long id,
            ProxyExchange<byte[]> proxy) {

        if (id <= 0) {
            throw new IllegalArgumentException("Product ID must be positive");
        }

        return proxy.forward("/internal/products/" + id);
    }
}
~~~

**Explanation:**

1. `@GetMapping` tells Spring MVC the public URL and HTTP method.
2. `ProxyExchange<byte[]>` is supplied by Proxy Exchange's MVC argument resolver when the module and auto-configuration are aligned.
3. `proxy.forward(String)` accepts a **local path**; the example uses a fixed path with a validated `id` parameter.
4. The handler returns a **`String` representing a Spring MVC view name / forward instruction**.
5. `@Controller` matters because the returned `String` goes through **view resolution** rather than being serialized directly as a response body.
6. The target `/internal/products/{id}` must actually have a matching handler; otherwise, an application missing-handler/view error occurs.

**Do not put `@ResponseBody` on the forward method**, and do not change the class to `@RestController` just because the final endpoint returns JSON. With `@RestController`, a string like `forward:/internal/products/42` can be written literally into the response body instead of dispatching a forward. Forwarding relies on **MVC view resolution**.

> **Technical note:** `forward(String)` is an API present in **ProxyExchange MVC**. Javadoc for an older branch (4.1.x) lists `forward(String)`, and 4.3/5.x docs confirm local forwarding support. If behavior varies across versions, first verify the exact artifact/package and run an integration test; do not replace it with a `ResponseEntity` containing a raw `forward:` string.

### 5.3. Local Controller: Returning Regular JSON

~~~java
package example.proxy;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InternalProductsController {

    @GetMapping("/internal/products/{id}")
    public ResponseEntity<Map<String, Object>> product(
            @PathVariable("id") long id,
            @RequestParam(value = "lang", defaultValue = "vi") String lang) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", id);
        body.put("name", "Demo product");
        body.put("lang", lang);
        body.put("handledBy", "internal-mvc-handler");

        return ResponseEntity.ok()
                .header("X-Handler-Type", "local-forward")
                .body(body);
    }
}
~~~

**Why can the target use `@RestController`?** Because the target returns a `ResponseEntity<Map<...>>` as the **HTTP response body**. Only the method *initiating the forward* needs to return an instruction so MVC performs an internal dispatch. The two controllers intentionally use different annotations.

If a client calls:

~~~bash
curl -i http://localhost:8080/edge/products/42
~~~

we **expect** status 200 and JSON containing:

~~~json
{
  "id": 42,
  "name": "Demo product",
  "lang": "vi",
  "handledBy": "internal-mvc-handler"
}
~~~

The same response should include the header:

~~~http
X-Handler-Type: local-forward
~~~

This JSON/header output is the **expected result from the sample code**, not a live execution log. There is no outbound HTTP call from the Gateway to another host; no mock server on port 8081 is needed to test this case.

### 5.4. Do Not Substitute `uri("http://localhost")`

For local forwarding, do not write:

~~~java
// Wrong tool: uses HTTP proxy back to the app itself instead of internal forward.
return proxy.uri("http://localhost:8080/internal/products/42").get();
~~~

That snippet makes an **outbound HTTP call** to port 8080 through the networking stack even though it runs on the same host. It adds latency, consumes connections, and risks loops or timeouts. For local targets, use `forward("/internal/products/42")`—or simply call a Java service directly if HTTP dispatch semantics are unnecessary.

## 6. How Servlet Forward Preserves a Single Request

Server-side forwarding in Servlet is not equivalent to the client resending a request. In principle:

- The original request remains **one HTTP request from the client**.
- Internal dispatch operates within **the same request/response context** without changing the browser URL.
- The **HTTP method** remains the original method unless modified by custom wrappers/logic.
- **Request attributes** can be passed within the same request; the Servlet container also sets forward-related attributes.
- Headers, cookies, queries, and bodies follow Servlet dispatcher/target mapping rules and depend on whether prior filters consumed the body.
- The internal response is sent to the client once the pipeline completes, provided the response was not committed before forwarding.

### 6.1. Do Not Assume Query Strings Are Rebuilt Identically

If the client calls:

~~~http
GET /edge/products/42?lang=en HTTP/1.1
Host: localhost:8080
~~~

we may want the local controller to receive `lang=en`. With standard Servlet forwarding, original request parameters remain on the forwarded request, though **the forward path may also carry its own query** and parameter merging follows Servlet spec rules.

In the lab, actually test:

~~~bash
curl -i "http://localhost:8080/edge/products/42?lang=en"
~~~

and assert the body contains `"lang":"en"`. If a project has custom servlet mappings, URL encoding, forwarded path handling, or query manipulation, verify behavior on the running container.

### 6.2. Request Attributes and Request Scope

For example, a controller can attach metadata to the request before forwarding:

~~~java
@GetMapping("/edge/demo")
public String demo(ProxyExchange<byte[]> proxy,
                   jakarta.servlet.http.HttpServletRequest request) {
    request.setAttribute("edge.forward.reason", "local-handler");
    return proxy.forward("/internal/demo");
}
~~~

The target local handler can read it:

~~~java
@GetMapping("/internal/demo")
public Map<String, String> internalDemo(
        jakarta.servlet.http.HttpServletRequest request) {
    Object reason = request.getAttribute("edge.forward.reason");
    return Map.of("reason", String.valueOf(reason));
}
~~~

This is **local metadata within a single request**. It does not automatically travel to remote HTTP backends. For older Servlet apps (Spring Framework 5 / Java EE), imports may be `javax.servlet.*`; modern examples use **`jakarta.servlet.*`** per Spring Framework 6+/Boot 3+.

**Never store sensitive user data in attributes and automatically log all request attributes.** For authorization, obtain identity from `SecurityContext` or the authenticated principal, never trusting an attribute just because it has a nice name.

## 7. GET, POST, and Bodies During Forward

### 7.1. Forward Does Not Turn POST Into GET

A `302` redirect in a browser can trigger a follow-up request with the method changed to GET depending on user agent/semantics. However, **a Servlet internal forward is not a redirect**: the incoming HTTP method is normally preserved.

This means:

- A `@GetMapping("/edge/products/{id}")` controller forwarding to a `@GetMapping("/internal/products/{id}")` target works naturally.
- A `@PostMapping("/edge/echo")` controller must forward to a **target supporting POST** to keep the operation.
- Forwarding from POST to an endpoint supporting only GET can yield `405 Method Not Allowed` or another mapping outcome, rather than converting to GET automatically.

### 7.2. POST Body Read by the Target

Example added to the `@Controller` class:

~~~java
@PostMapping("/edge/echo")
public String echo(ProxyExchange<byte[]> proxy) {
    // Do not read @RequestBody here; let the target handler read the body.
    return proxy.forward("/internal/echo");
}
~~~

Added to the `@RestController` target:

~~~java
@PostMapping(
    path = "/internal/echo",
    consumes = "application/json",
    produces = "application/json")
public ResponseEntity<Map<String, Object>> echo(
        @RequestBody Map<String, Object> payload) {

    return ResponseEntity.ok(Map.of(
            "received", payload,
            "handledBy", "internal-echo"));
}
~~~

Additional imports for both snippets are `org.springframework.web.bind.annotation.PostMapping`, `RequestBody`, `org.springframework.http.ResponseEntity`, and `java.util.Map`.

Test it:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}' \
  http://localhost:8080/edge/echo
~~~

Expect a response body showing the message was received and processed by the local handler. **Test actual bodies and `Content-Type`s**, because an earlier Servlet filter may have already drained the `InputStream`, or the app may use a custom request wrapper/parser. Do not assume the body can be re-read indefinitely.

### 7.3. Why Not Read the Body in Both Edge and Target?

A Servlet request body is usually a **stream with limited re-readability**. If the edge controller or a filter consumes the raw input, the target may see an empty body or parsing error. Better patterns:

1. If you must validate the payload before forwarding, use a **size-bounded** request wrapper/cache and verify memory release.
2. If you already parsed it into a DTO and the next logic lives in the same JVM, consider **calling a Java service directly** instead of forwarding.
3. If you want to preserve POST semantics to a local MVC target, let the **target handler** parse the body where appropriate.
4. For large uploads/multipart requests, avoid unnecessary body reads/copies and check Servlet multipart limits.
5. Test wrong `Content-Type`, invalid JSON, empty bodies, charsets, and request cancellation.

**Do not conclude `ProxyExchange.forward()` provides body caching or multipart replay.** It is a local dispatch mechanism, not a free stream buffer.

## 8. Forward Paths and Avoiding Loops

### 8.1. Use Local Paths With Clear Ownership

Safe design:

~~~text
Public:
  /edge/products/{id}

Internal:
  /internal/products/{id}
~~~

Separating prefixes makes code review and testing easier. However, an `/internal` prefix **does not automatically make an endpoint private**. If the public application still accepts `GET /internal/products/42` directly, clients can bypass edge validation unless security and network routing are configured properly.

### 8.2. Dangerous Mistake: Forwarding to Yourself

~~~java
// ANTI-PATTERN: forward loop, do not run!
@GetMapping("/edge/loop")
public String loop(ProxyExchange<byte[]> proxy) {
    return proxy.forward("/edge/loop");
}
~~~

A request dispatched to a mapping forwards right back to itself. Depending on the Servlet container and exception handling, this causes errors, stack overflows, exceeding dispatcher depth, timeouts, or log floods. Do not assume a single fixed HTTP status.

Preventive rules:

- Never forward to the same path/mapping without a strictly proven guard.
- For any forwarding chain longer than one hop, maintain a **directed acyclic graph**, never a cycle.
- Cap forward depth by policy if using custom routing.
- Test boundary paths, queries, and encoded slashes.
- Never build `/edge/** -> /edge/**` routes using unchecked substrings.

### 8.3. Never Forward Using Client-Supplied Paths Directly

The following is very risky:

~~~java
// DO NOT use on public endpoints:
@GetMapping("/edge/go")
public String arbitrary(
        @RequestParam("next") String next,
        ProxyExchange<byte[]> proxy) {
    return proxy.forward(next);
}
~~~

A client could supply `next=/internal/admin`, `/actuator`, paths with `..`, encoded characters, or an unprotected mapping. Even though local forwarding **is not network SSRF**, it can cause **internal endpoint exposure** and bypass edge validation checks.

Use a fixed allowlist instead:

~~~java
@GetMapping("/edge/page")
public String page(
        @RequestParam("view") String view,
        ProxyExchange<byte[]> proxy) {
    return switch (view) {
        case "summary" -> proxy.forward("/internal/pages/summary");
        case "help" -> proxy.forward("/internal/pages/help");
        default -> throw new IllegalArgumentException("Unsupported view");
    };
}
~~~

Do not rely on `String.contains("internal")` or weak denylists as a policy. When multiple targets are needed, keep mappings in trusted code/config, validate URI/path normalization, and protect the actual targets with Spring Security.

## 9. Authentication and Authorization When Requests Are Forwarded

### 9.1. Do Not Treat Forward as a Security Layer

Suppose `/edge/products/42` is protected by Spring Security and the controller checks permissions, while `/internal/products/42` has a handler returning sensitive data. If clients can call `/internal/products/42` directly, protecting only `/edge/**` is **insufficient**.

A rule covering only `/edge/**` may leave direct requests to `/internal/**` exposed. Protect targets based on principal and business permissions.

### 9.2. What Does `DispatcherType.FORWARD` Mean?

Servlets define dispatcher types such as **REQUEST**, **FORWARD**, **INCLUDE**, **ASYNC**, and **ERROR**. Filters can register for specific dispatch types, and Spring Security behavior depends on version and filter-chain configuration.

Distinguish:

1. **Direct client request** to `/internal/**` with dispatcher type `REQUEST`.
2. **Internal forward** from `/edge/**` to `/internal/**` with dispatch type `FORWARD` inside the Servlet flow.

**Do not claim “Spring Security always re-checks every forward”**, nor claim “Spring Security always skips forwards” across every version. Path rules, filter registrations, or `dispatcherTypeMatchers` settings can alter how authorization runs. Verify with integration tests against your real filter chain.

### 9.3. Recommended Protection Model

- Public `/edge/**` must pass business authentication and authorization.
- If `/internal/**` must not be called directly from outside, ensure **direct client requests are denied** by security policy, not just by naming it “internal”.
- Never use `permitAll` on all of `/internal/**` just to make forwarding work.
- If `FORWARD` dispatch to internal targets is allowed by policy, document its limits and verify the request is a legitimate forward—never assume a client header proves it.
- For sensitive data, **authorization in the target service/handler** should still verify principal and object-level permissions.
- Never let clients pick forwarding paths.
- Test 401/403 and both direct and forwarded paths.

For example, an MVC app applies a **Servlet `SecurityFilterChain`** with `HttpSecurity`, not WebFlux's `SecurityWebFilterChain`. However, never copy a generic `permitAll(FORWARD)` snippet into production without a threat model and tests, as it may expose unintended targets.

### 9.4. CORS and CSRF Are Not “Solved” by Forwarding

- **CORS** restricts browser JavaScript requests from other origins; it does not grant resource access.
- **CSRF** matters when APIs rely on cookie/session credentials for writes; internal forwarding does not eliminate inbound POST CSRF risks.
- **TLS** at ingress protects only that network leg; it does not replace target access controls.
- **`Forwarded`/`X-Forwarded` headers** from trusted proxies must be handled at the trust boundary; never treat client-set headers as proof of verification.

## 10. Do Not Confuse `forward()` Behavior With Remote `get()`

In Proxy Exchange, the same controller can branch between local and remote under a **controlled policy**, yet the two calls behave very differently.

### 10.1. Local Forward

~~~java
@Controller
class LocalBranchController {

    @GetMapping("/edge/local")
    String local(ProxyExchange<byte[]> proxy) {
        return proxy.forward("/internal/demo");
    }
}
~~~

### 10.2. HTTP Proxy to Upstream

~~~java
@RestController
class RemoteBranchController {

    @GetMapping("/edge/remote")
    ResponseEntity<?> remote(ProxyExchange<byte[]> proxy)
            throws Exception {
        return proxy.uri("http://localhost:8081/demo").get();
    }
}
~~~

In the remote case:

- `uri(...)` specifies an **HTTP target**.
- `.get()` performs an outbound GET to server `8081`.
- HTTP status, body, and headers come from the upstream HTTP response (optionally adjusted by a mapper).
- Subject to network latency, DNS/connection failures, TLS verification, and client/config retries/timeouts.
- Proxy Exchange's sensitive/skipped headers have their own policy; per current docs, defaults include `cookie`, `authorization` and hop/framing headers that should not be copied blindly like `host`, `content-length`. Defaults can vary by version.

In the local case:

- No external URI configured.
- No outbound HTTP call to port 8081.
- No downstream HTTP proxy header processing; uses the Servlet request/response inside the same application.

### 10.3. ProxyExchange `header()` Is Not a `forward()` API

Proxy Exchange docs provide `header()`/`headers()` and mappers for `get()`, `post()`, etc., to adjust **downstream HTTP calls** or their responses. **Do not assume setting a header meant for outbound proxying automatically becomes a response header on a local-forward handler.**

If the local handler needs metadata, use request attributes or authenticated service-level context. If you want a response header, set it in the target handler or appropriate Servlet response API **before the response commits**.

## 11. When Can Forward Be Replaced by a Redirect or Service Call?

### 11.1. When to Forward

Use internal forward when:

- Both handlers run in **the same Servlet application**.
- You want a public endpoint to **delegate handling** to an existing MVC mapping.
- You do not want the browser to make a second HTTP request.
- You need to preserve the HTTP method and request context.
- Security policies cover both the entry point and the target.
- There is a clear reason to reuse **MVC handler mapping** rather than calling a Java method directly.

For example, mapping a legacy alias `/legacy/help` to local `/help` without changing the client URL—provided it is cleanly designed and tested.

### 11.2. When to Redirect

Use `302`/`307`/`308` when:

- You want the client to learn the new **canonical URL** or move to a different origin.
- You want the browser to update its address bar and history.
- You want to separate the initial and subsequent client requests.
- You have accounted for HTTP method semantics (`307`/`308` preserve methods more strictly than traditional redirects).

Do not use forward when the business contract expects the client to change URLs.

### 11.3. When to Call a Java Service Directly

If the edge handler only needs a local business method, often the simplest design is:

~~~java
@RestController
class EdgeProductApi {
    private final ProductQueryService products;

    EdgeProductApi(ProductQueryService products) {
        this.products = products;
    }

    @GetMapping("/edge/products/{id}")
    ProductView product(@PathVariable long id) {
        return products.findOne(id);
    }
}
~~~

This is an **illustrative pattern**, assuming `ProductQueryService`/`ProductView` exist in your application domain. It avoids depending on MVC forward/view resolution and makes business logic easier to unit-test directly. Use forward only when **reusing MVC handler dispatch** is genuinely needed.

### 11.4. When to Use Full Gateway Server

If requirements include:

- Route predicate/filter chains for hundreds of routes.
- Service discovery and load balancing across many upstreams.
- Centralized rate limiting, circuit breakers, retries, tracing, and TLS policies.
- Managing routes via config/DSL or dynamic refresh.
- Multiple Gateway replicas and a control plane.

evaluate **Spring Cloud Gateway Server Web MVC** or **Server WebFlux** instead of building route management out of `@Controller + ProxyExchange`. Proxy Exchange is helpful for a handful of proxy/forward handlers inside an MVC app, but **it is not marketed as a 1:1 drop-in replacement for all Gateway Server features**.

## 12. HTTP Response During Forward: Status, Headers, and Error Handling

### 12.1. No Intermediate HTTP 3xx Response

On a successful forward, the client normally receives only the **final response** produced by the target handler. For instance, the local target returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Handler-Type: local-forward

{"handledBy":"internal-mvc-handler","id":42}
~~~

There will be **no `Location: /internal/products/42`** redirect header because the browser is never asked to send another request. If you see 302/307, the app may be using `redirect:`, a Spring Security login entry point, or another interceptor—that is not inherent to `forward()`.

### 12.2. When the Target Returns an Error

For example, the target may return `404` when a product is missing or `403` when the principal lacks permission. The client sees that response on the public request unless an exception handler/filter alters it.

**Never force every error to `200 OK` just because MVC forwarding succeeded.** Forwarding is an internal dispatch step; it does not guarantee business logic at the target succeeded.

### 12.3. Committed Responses Cannot Be Forwarded Reliably

Once response headers/body are committed, calling forward or redirect can fail or produce corrupt output depending on the container. Never do:

~~~java
response.getWriter().write("partial response");
~~~

and then ask MVC to forward. Decide the target before writing to the response.

### 12.4. Exception Handling Can Catch Errors From the Target Handler

An appropriately scoped `@ControllerAdvice` can translate validation exceptions or domain errors from the local handler into consistent HTTP statuses/JSON. Keep in mind:

- The edge handler can fail **before forward**.
- The target handler can fail **after forward**.
- Servlet `Filter`s, Security, and `HandlerInterceptor`s may behave differently by dispatch type.
- Error dispatches can trigger additional handling.

Test every branch rather than assuming the same advice catches every exception across all configurations.

## 13. Logging and Observability: One Request, Two Handling Points

An internal forward can cause both the **edge** and **internal** handlers to log. If you count “user calls” by summing controller log entries, you will double-count.

Sanitized timeline example:

~~~text
requestId = req-123
clientMethod = GET
publicPath = /edge/products/42
forwardTarget = /internal/products/42
handlerTarget = InternalProductsController.product
finalStatus = 200
outboundHttpCalls = 0
~~~

This is an **example log design**, not a built-in Proxy Exchange metric. Ensure:

- One consistent request/trace ID across the whole request.
- A **client request count** metric at the ingress boundary.
- Separate metrics for handler latency or internal dispatch if desired.
- Never put raw request IDs into metric labels (high cardinality).
- Count outbound HTTP calls separately; a local forward is not an upstream attempt.
- Mask tokens, cookies, PII queries, and sensitive bodies.
- Monitor forward-loop errors, target 404/405s, exceptions, duration, and security denials.

If the Gateway includes ingress/service mesh layers, traces should distinguish **client → Gateway** from **Gateway → remote service**. With local forward there is no network span like a remote proxy, though internal handler instrumentation can still appear.

## 14. Testing With MockMvc

### 14.1. Conditions for Forward Tests to Work Properly

A `@WebMvcTest` slice initializes only part of the MVC context. Because `ProxyExchange<byte[]>` is a library argument type, **test slices may not automatically pull in full auto-configuration or its argument resolver**.

Two strategies:

- **Integration test with `@SpringBootTest` + `@AutoConfigureMockMvc`** to stay closest to real runtime behavior.
- **MVC slice test** explicitly importing the required argument-resolver configuration if you know your version's exact setup; never conclude `forward()` is broken from a slice test failing due to a missing resolver.

### 14.2. Test Checking the Forward Target

MockMvc test skeleton when the app context has MVC/Proxy Exchange:

~~~java
package example.proxy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProxyForwardMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void edgeRouteForwardsToInternalMapping() throws Exception {
        mvc.perform(get("/edge/products/42"))
                .andExpect(status().isOk())
                .andExpect(forwardedUrl("/internal/products/42"));
    }
}
~~~

**Explanation and caveats:**

- MockMvc's `forwardedUrl(...)` is useful for verifying the **forward target**, but how MockMvc handles subsequent dispatch to the target **differs from a real Servlet container**. Some setups only record `forwardedUrl` without actually invoking the target or returning JSON.
- If the test above verifies the forward instruction without seeing the final JSON body, **that alone does not mean the real runtime fails to return JSON**.
- Enabling Spring Security in tests may change expected HTTP statuses unless a mock principal/token is provided. Supply valid mock authentication or test per security policy.
- Requires compatible Spring Boot/Test and JUnit dependencies; this example requires a matching project setup and **was not executed in this lesson**.

### 14.3. Testing the Final Response With an Embedded Server

To verify **both edge and target working end-to-end**, boot the app with a real Servlet container:

- `@SpringBootTest(webEnvironment = RANDOM_PORT)`.
- HTTP client tests using `TestRestTemplate`, `RestClient`, HTTP-bound `WebTestClient`, or RestAssured depending on the project.
- Send GET to the real port.
- Assert `200`, JSON payload, and `X-Handler-Type`.
- Inspect any outbound HTTP client mock: **zero calls made to remote services**.
- Assert direct access to `/internal/products/{id}` is denied if required by business policy.

The gap between **MockMvc `forwardedUrl`** and a **real server final response** is an essential lesson in forward semantics.

## 15. Manual Testing With curl

### 15.1. Successful GET

~~~bash
curl -i "http://localhost:8080/edge/products/42"
~~~

Expected from sample code:

~~~text
HTTP 200
Content-Type: application/json
X-Handler-Type: local-forward

Body contains id=42 and handledBy="internal-mvc-handler"
~~~

Notice `curl -i` shows the final response directly, **with no redirect step**, because forwarding happens server-side.

### 15.2. Query Parameters

~~~bash
curl -i "http://localhost:8080/edge/products/42?lang=en"
~~~

Expect the body to contain `"lang":"en"` when forwarding and parameter handling match Servlet MVC configuration.

### 15.3. POST Body

After adding `@PostMapping("/edge/echo")` and the local target:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}' \
  "http://localhost:8080/edge/echo"
~~~

Expect the target to read the JSON payload accurately with zero outbound HTTP calls.

### 15.4. Direct Target Access

~~~bash
curl -i "http://localhost:8080/internal/products/42"
~~~

**In a demo app without Spring Security**, this request may be served directly by the internal controller. That is not a safe default for systems with sensitive data. Once security policy is added, assert that direct requests are rejected per requirements while **legitimate forwards** still succeed.

### 15.5. Do Not Mistake for a Redirect

~~~bash
curl -i "http://localhost:8080/edge/products/42"
~~~

If the response includes `Location` and a 3xx status, check:

1. Is the controller truly `@Controller`?
2. Does it return `proxy.forward("/internal/...")` rather than `"redirect:/internal/..."`?
3. Is there a Spring Security login redirect or an interceptor firing?
4. Is there a URL rewrite/redirect at ingress or a reverse proxy in front of the app?

A final 200 JSON response is expected when forwarding to a `@RestController`.

## 16. Key Testing Matrix

| Case | Action | Required Assertion |
| --- | --- | --- |
| F1 | GET `/edge/products/42` | Forwards to `/internal/products/42`; target JSON returned |
| F2 | GET same URL with `lang=en` | Query/parameters handled per contract |
| F3 | GET `/edge/products/0` | Validation rejects invalid ID |
| F4 | POST `/edge/echo` with JSON | POST method preserved; target receives exact payload |
| F5 | POST when target supports only GET | Method mismatch; does not silently turn POST into GET |
| F6 | Target returns 404 | Client sees proper error; not converted to 200 |
| F7 | Target returns 403 | Does not bypass object-level authorization |
| F8 | Direct call to `/internal/**` | Rejected if required by security contract |
| F9 | Mistaken `@RestController` on forward source | Test catches forward string returned as response body without dispatch |
| F10 | Forward target matches source mapping | Test detects/blocks forward loop |
| F11 | Client tries passing arbitrary path in query | Allowlist blocks forwarding to admin/local secrets |
| F12 | Gateway has only Proxy Exchange MVC | No implicit Gateway Server filter chain running |
| F13 | MockMvc test | `forwardedUrl` matches; do not infer final JSON if container didn't dispatch |
| F14 | Embedded server test | Final response accurate; no HTTP 3xx or new network hop |
| F15 | Security Filter with `FORWARD` dispatcher | Real tests of paths/principals and direct vs. forwarded access |
| F16 | Upstream Servlet filter reads body first | Detects drained stream or body parsing failure |
| F17 | Response already committed before forward | Disallows forwarding after commit |
| F18 | Different Servlet container / Spring version | Behavior and mappings stay consistent per supported release |

These cases represent a **test plan**, not executed results. Never run unbounded loop tests in production; test inside an isolated sandbox with timeout guards.

## 17. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `forward()` method does not exist | Picked ProxyExchange WebFlux or wrong artifact | Use `spring-cloud-gateway-proxyexchange-webmvc` matching version |
| `ProxyExchange` argument not resolved | Missing module/auto-configuration or wrong MVC stack | Check dependencies, argument resolver, and test context |
| Response prints literal `forward:/internal/...` string | Controller uses `@RestController` or `@ResponseBody` | Switch forward source to `@Controller` returning view instruction |
| `404 Not Found` after forward | Target path lacks mapping or wrong context path | Check target `@GetMapping` and request path |
| `405 Method Not Allowed` | Source is POST, target is GET only | Align HTTP methods between source and target |
| Client sees 302 | Using redirect or security login flow | Check `redirect:`, Security, and ingress |
| Empty JSON body on target POST | Servlet input stream was already consumed earlier | Control body consumption or use size-bounded caching wrapper |
| MockMvc shows `forwardedUrl` but no JSON | Mock lacks full container dispatch | Test final response on embedded server |
| Direct `/internal/**` returns sensitive data | Protected only the edge route | Protect target and test direct access |
| Odd permission handling after forward | `DispatcherType.FORWARD` and security mappings | Test Servlet filter registrations and `SecurityFilterChain` |
| Infinite requests / stack overflow | Forward loop | Block target matching source; add validation/graph checks |
| Client-supplied URI reaches admin handler | Forward target not allowlisted | Hardcode path mappings; deny sensitive targets |
| Route missing from Gateway Actuator | Using Proxy Exchange MVC, not Server routes | Inspect Spring MVC mappings/controllers |
| `GatewayFilter` not running | Proxy Exchange does not run Gateway Server filter chain | Use Servlet filters/security or switch to Gateway Server |
| Body/headers transformed unexpectedly | Filters, argument resolvers, or content negotiation | Inspect target and actual Servlet request |
| Forward to service in another pod fails | Forward is strictly for **local handlers** | Use HTTP proxy/discovery, not forward |
| CORS/CSRF errors | Missing Servlet Security/CORS/CSRF config | Configure per auth type and actual origin |
| Using `forward:///...` in `@Controller` | Confused Server WebFlux syntax | Use `proxy.forward("/path")` with MVC |
| 200 returned, but wrong target handled it | Different route/handler matched; weak test assertion | Assert `handledBy`, handler type, and logs |

## 18. End-of-Chapter Practice Lab

**Context:** A Spring MVC application has two endpoint groups: legacy API at `/legacy/products/{id}` and internal API at `/internal/products/{id}`; another endpoint uses an outbound HTTP proxy to a mock catalog service.

### Requirements

1. Use the **Proxy Exchange Web MVC** artifact compatible with your Spring Boot/Cloud BOM.
2. Create a `@Controller` accepting `ProxyExchange<byte[]>`.
3. Create `@GetMapping("/legacy/products/{id}")` forwarding to `/internal/products/{id}`.
4. Create a target `@RestController` returning JSON with the ID and a `handledBy` marker.
5. Verify with `curl -i` that there is no HTTP 3xx redirect and the body comes from the local handler.
6. Use `MockMvc` to assert `forwardedUrl`; use an embedded server to assert the final JSON and headers.
7. Test GET with query `lang=en` and confirm parameter propagation.
8. Add a POST echo forward and test request body and method preservation.
9. Add guards preventing forwards to `/actuator`, `/admin`, or client-chosen URLs.
10. Add a Spring Security Servlet policy: direct `/internal/**` is blocked per business contract while valid forwards keep authorization intact.
11. Write a separate remote handler using `proxy.uri("http://localhost:8081/...").get()` and measure outbound HTTP calls.
12. Compare error handling, latency, and metrics between local forwarding and remote proxying.
13. Test a non-existent target and a loop inside a timeout-protected sandbox—never deploy a loop to production.
14. Document what cannot be copied directly from Gateway Server WebFlux/MVC into Proxy Exchange.

### Pre-Production Verification Checklist

- [ ] Selected **Proxy Exchange Web MVC**, not confused with the Server Web MVC starter.
- [ ] Controller initiating forward uses `@Controller`, not `@RestController`/`@ResponseBody`.
- [ ] Uses `proxy.forward("/local-path")`, not WebFlux's `forward:///...`.
- [ ] Target handler actually exists within the same Servlet application.
- [ ] HTTP methods and target mappings match; POST is not accidentally converted to GET.
- [ ] Request bodies are read only as designed, without expecting uncached stream replay.
- [ ] Never forwards after response commit.
- [ ] Forward loops blocked and clients cannot pick arbitrary local targets.
- [ ] Direct access to internal paths verified by proper security checks.
- [ ] `DispatcherType.FORWARD`, Servlet filters, and Spring Security tested.
- [ ] Never treats “internal” in a URL as a security boundary.
- [ ] 400/401/403/404/405 errors handled consistently with the contract.
- [ ] Distinguished forward, redirect, remote proxy, and Java service calls.
- [ ] Outbound HTTP proxying uses URI allowlists, timeouts, TLS, and proper secret handling.
- [ ] Does not assume Proxy Exchange implicitly includes Gateway Server predicates/filters.
- [ ] Integration tests run on a real Servlet container.
- [ ] Logs/traces mask tokens, cookies, and PII; metrics never use raw request IDs as labels.
- [ ] Verified dependency/package compatibility for the active release train.

## 19. Summary and References

**`ProxyExchange.forward(String)` in Spring Cloud Gateway Proxy Exchange Web MVC** lets an **annotation-based MVC controller** dispatch a request to a **local handler** within the same Servlet application. It is not an outbound HTTP proxy, not an HTTP redirect, and not Gateway Server WebFlux's `forward:///...`.

In Java, the pattern to remember is:

~~~java
@Controller
class EdgeController {
    @GetMapping("/edge/products/{id}")
    String product(@PathVariable long id,
                   ProxyExchange<byte[]> proxy) {
        return proxy.forward("/internal/products/" + id);
    }
}
~~~

The target handler can be a `@RestController` returning JSON. The critical point is that **the source method returns a view/forward instruction**, rather than serializing the string as a response body via `@RestController`. To ensure correctness, test **zero redirects, exact target, preserved HTTP method/body, and security** across both direct requests and `FORWARD` dispatches.

When you need to call a remote microservice, use `proxy.uri(...).get()/post()` or Gateway Server with service discovery/load balancing; when you simply want to reuse Java logic, a direct service method call is often simpler. Making the right choice lets your microservices gateway combine authentication, rate limiting, retries, circuit breakers, TLS, and observability **without conflating routing mechanisms from different stacks**.

### References

- [Spring Cloud Gateway 5.x — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html).
- [Spring Cloud Gateway 4.3 — Proxy Exchange Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html).
- [Spring Cloud Gateway — Overview of Server and Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/intro.html).
- [Spring Cloud Gateway Server Web MVC — How It Works (to distinguish from Proxy Exchange)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html).
- [Spring Cloud Gateway Server WebFlux — Forward Routing Filter (different mechanism)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Framework — Spring Web MVC: View Resolution and Forwarding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html).
- [Spring Framework — Spring Web MVC Controller Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
- [Servlet API — RequestDispatcher.forward](https://jakarta.ee/specifications/servlet/).
