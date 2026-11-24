# Layering Network, Server, Filter, Controller, and Business Errors in Spring Boot

A failed HTTP request does not necessarily mean that a controller ran and threw an exception. In a **Spring Boot web runtime** application, an error can occur from the moment the client resolves DNS, establishes a TCP/TLS connection, passes through a gateway or reverse proxy, enters the Servlet container, runs Servlet filters/Spring Security, is dispatched by `DispatcherServlet`, invokes the controller, all the way until the service executes business rules or accesses external systems.

Placing error handling at the **right layer** is the foundation for returning consistent HTTP statuses, avoiding leaking internal data, reducing duplicate logs, and diagnosing incidents accurately.

**Core classification:**

- **Network/transport errors:** DNS, TCP, TLS, dropped connections, network timeouts. In some cases, **no HTTP response exists**.
- **Proxy/web server/Servlet container errors:** invalid requests, size or connection limits, infrastructure routing, servlet mapping. These may be handled **before the controller**, or even before filters.
- **Servlet Filter / Spring Security errors:** requests blocked by authentication, authorization, CORS, rate limiting, or HTTP policies before Spring MVC.
- **Spring MVC / Controller errors:** unmatched route, unsupported HTTP method, body decode failure, binding/validation error, or controller throwing an exception.
- **Business / service / downstream errors:** resource not found, state conflict, rule violation, unavailable database or external service. These must be translated into an appropriate response at the HTTP boundary rather than turning every exception into a 500.

This article mainly describes **Spring Boot 3.x, Java 17+, Spring MVC on the Servlet stack**, and highlights differences when using **Spring WebFlux**. The standalone examples use a Spring Boot 3.x project. When upgrading major versions, check the corresponding APIs and configurations for Spring Security, the Servlet container, and Spring Framework.

## 1. Diagram of Layers Along the Request Path

~~~text
HTTP client
    |
    | DNS / TCP / TLS / HTTP
    v
Network / Load Balancer / Reverse Proxy
    |
    | Upstream connection, headers, URL rewrite, timeout, size limit
    v
Embedded Servlet container (Tomcat, Jetty, or Undertow)
    |
    | HTTP parsing, context path, servlet mapping, server errors
    v
Servlet FilterChain
    |
    +---- Logging/correlation filter
    +---- Spring Security filters
    +---- CORS/rate-limit/custom filter
    |
    v
DispatcherServlet (Spring MVC)
    |
    +---- HandlerMapping: resolve route/handler
    +---- HandlerAdapter: binding + validation + invoke handler
    +---- HttpMessageConverter: read/write body
    |
    v
@RestController / @Controller
    |
    v
Service (domain/business rules)
    |
    +---- Repository/Database
    +---- HTTP client/Message broker/Cache
    |
    v
Response travels back through MVC -> Filter -> Container -> Proxy
~~~

The diagram illustrates the typical Servlet MVC case. Some requests do not travel the full path: a reverse proxy may return an error immediately, the Servlet container may reject a malformed request, a filter may terminate the response, or DispatcherServlet may fail to find a handler.

### 1.1. Which Layers Can Create an HTTP Response?

| Layer | Error Example | Can It Create a Response? | Does It Go Through ControllerAdvice? |
|---|---|---|---|
| Client-side DNS/TCP/TLS | DNS resolution failure, connection refused | Not necessarily any HTTP response | No |
| Proxy/gateway | Upstream timeout, backend unreachable | Can return 502/503/504 | No if the request never reached the app |
| Servlet container | Request line/header too large, malformed HTTP parse | Can return 400/413/431 or close the connection | Usually no |
| Servlet Filter | Request blocked, auth/security | Can return 401/403/429 | Not automatically |
| Spring MVC mapping/binding | Wrong method, malformed JSON, validation failure | Usually 400/404/405/406/415 | Possibly, depending on the exception and MVC handling mechanism |
| Controller | Throws an exception while handling the request | Yes if handled by an MVC error resolver | Possibly |
| Business service | Not found, conflict, business rule | Controller/Advice translates into HTTP | Possibly if the exception passes through MVC |
| Downstream | DB timeout, HTTP client exception | App can translate into 5xx/503, or request timeout | Possibly if the exception passes through MVC and the response is not yet committed |

**Do not conclude** that a single status code always identifies a single layer. HTTP 400 can originate from a proxy, container, or MVC; HTTP 403 can come from a security filter or business logic. Always correlate logs and traces along the actual execution path.

## 2. Network Layer: DNS, TCP, TLS, and Connection Failures

Errors occurring **before a valid HTTP message exists** cannot be handled by the application's `@RestControllerAdvice`.

Examples:

- **DNS failure:** the client cannot resolve the hostname into an address to connect to.
- **TCP connection refused:** no service is listening on the target address/port, or the system rejects the connection.
- **TCP connect timeout:** the network, firewall, or destination does not respond within the connection timeout.
- **TLS handshake failure:** untrusted certificate, hostname mismatch, incompatible protocol/cipher, misconfigured SNI or mTLS.
- **Connection reset / premature close:** the connection is abruptly closed before or while transmitting the response.
- **Client-side read/response timeout:** the client waits too long for a response and gives up, even though the server might still be processing.

In these scenarios, the client may only receive an **exception from the HTTP client library**, with no 500/503 status code emitted by the application.

### 2.1. Distinguishing Connection Failures from HTTP Error Responses

~~~text
A. DNS fail -> TCP not established -> no HTTP response
B. TLS fail -> HTTP request never enters app -> no normal HTTP response
C. Gateway sends 504 -> HTTP 504 response from gateway
D. App returns 503 -> HTTP 503 response from application
~~~

Do not turn every network exception into an “HTTP 500 from the server”. When no HTTP response has been received, preserve information about the **transport error type** along with destination address, timestamp, retry count, and timeout; only attach an HTTP status when a response actually exists.

### 2.2. A Timeout Does Not Prove Business Execution Failed

Suppose a client sends a payment request, the server processes it successfully, but the response is dropped on the way back. The client sees a timeout, yet the payment command **may already have been executed**.

Do not automatically retry every POST request with side effects. For operations that are not safe to repeat, you need an **idempotency key**, durable transaction state, a result-checking mechanism, and clear retry rules.

## 3. Reverse Proxy, Ingress, and Load Balancer Can Be Error Sources

In real deployments, clients rarely call the embedded server directly. Many systems sit behind an API gateway, Nginx, ingress controller, load balancer, or service mesh:

~~~text
Client -> Gateway/Ingress -> Spring Boot Pod
                |
                +-- Route/rewrite URL
                +-- TLS termination
                +-- Request header/body size limits
                +-- Upstream connect/read timeout
                +-- Rate-limit or auth policy
~~~

Commonly observed status codes:

| Status | Common Meaning at Proxy/Gateway | What to Check |
|---|---|---|
| 400 | Invalid request at proxy | Headers, URL, HTTP syntax |
| 401/403 | Auth/policy at gateway | Gateway auth policy |
| 413 | Body exceeds proxy limit | Request body size limit |
| 429 | Rate limit | Quotas and rules at ingress/gateway |
| 502 | Gateway received invalid upstream response / could not connect | Backend health, protocol, resets |
| 503 | No upstream available or overloaded | Endpoints, service discovery, readiness |
| 504 | Gateway waited too long for upstream | Upstream timeout, downstream latency |

These are **common patterns**, not definitive proof of a status code's origin. The same 503 could be actively emitted by the application or returned by the gateway when no healthy backend is found.

Some proxies use status **499** to record that the client closed the request; it is a non-standard HTTP status code and is not supported by all servers.

**Important sign:** if a proxy returns an error before forwarding the request, Spring Boot has **no corresponding log or controller trace**. Check access logs at each hop and correlation/request IDs across both the proxy and the application instead of only looking for controller exceptions.

## 4. Servlet Container Layer: Errors Before FilterChain

In the Spring MVC Servlet stack, embedded Tomcat/Jetty/Undertow receives HTTP traffic, validates essential syntax, and determines the web application/servlet mapping.

Cases that may be handled early by the container:

- Invalid HTTP request line or headers.
- Headers too large, unacceptable request target.
- Too many connections, overloaded workers/connectors.
- Container-specific body or upload size limits.
- Wrong context path, servlet mapping, or listener/connector.
- TLS/HTTP protocol errors at the connector.

When a request **has not reached FilterChain**, your custom servlet filter or `@RestControllerAdvice` cannot catch that error.

### 4.1. An Open Port Does Not Guarantee Application Readiness

An application may have already opened its HTTP socket while not yet meeting business requirements to serve traffic, or while the container is overloaded. Therefore, distinguish between:

- **Liveness:** the process is alive and can recover via restart if stuck.
- **Readiness:** the instance is ready to accept requests under operational conditions.
- **Business health:** connectivity or capacity of critical dependencies.

You can configure Spring Boot Actuator health/readiness probes when appropriate, though they only work when the corresponding dependencies/configs are enabled. Do not treat “TCP port completes a handshake” as proof that endpoints/controllers are functioning normally.

### 4.2. Container Errors Do Not Necessarily Produce Standardized JSON

The container may close the connection or return an error page/body different from your API's JSON format. If the contract requires consistent JSON errors, standardization must happen at the ingress/proxy and application within each layer's boundaries; **you cannot use ControllerAdvice to catch every HTTP error before the Servlet container**.

## 5. Servlet FilterChain and Errors Raised Before DispatcherServlet

A `Filter` is invoked by the Servlet container before entering `DispatcherServlet`, and can be used for tracing, HTTP policy enforcement, request wrapping, rate limiting, or security.

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
) throws IOException, ServletException {
    // Logic before Servlet/DispatcherServlet
    chain.doFilter(request, response);
    // Logic on the response return path
}
~~~

This is a fragment of a class that `implements Filter`, requiring imports from `jakarta.servlet.*` in Spring Boot 3.x.

If a filter **does not call `chain.doFilter`**, the request stops before reaching the controller. A filter may return 403 or 429 on its own, which does not mean the corresponding controller ran.

### 5.1. Why Does @RestControllerAdvice Not Automatically Catch Filter Exceptions?

`@RestControllerAdvice` is an exception-handling mechanism within the MVC path coordinated by `DispatcherServlet`/`HandlerExceptionResolver`. Filters run **outside** that path.

~~~text
Filter
  |
  +--- exception thrown before chain.doFilter -> bypasses MVC exception resolver
  |
  +--- chain.doFilter -> DispatcherServlet -> Controller -> MVC resolver
  |
  +--- code after chain.doFilter is also outside MVC resolver
~~~

If a filter throws an exception before entering DispatcherServlet or after it returns, a typical `@ExceptionHandler` inside ControllerAdvice **has no opportunity** to directly catch that exception.

Filter errors must be handled in the filter, the security framework, or the Servlet error-handling pipeline. You can intentionally design error forwarding to a resolver, but you should never assume a global advice automatically handles the entire HTTP pipeline.

### 5.2. Filter Responses Must Be Constructed Responsibly

If you want to block a request:

~~~java
if ("true".equalsIgnoreCase(request.getHeader("X-Block-Request"))) {
    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    return;
}
filterChain.doFilter(request, response);
~~~

This is a fragment used inside `OncePerRequestFilter#doFilterInternal`, where request/response already have types HttpServletRequest/HttpServletResponse. As written above, the filter returns **403** without providing a JSON body. If the API requires standard JSON, the filter or security handler must safely build the response itself and verify content type/status.

Do not call `response.getWriter()` and then continue calling `chain.doFilter` unless intentional. Doing so can write duplicate responses, corrupt bodies, or commit the response so the status can no longer be changed.

## 6. Spring Security Lives in the Filter Layer but Has Its Own Error Handling

In the Spring Security Servlet stack, `DelegatingFilterProxy` and `FilterChainProxy` bridge the Servlet FilterChain with Spring Security's `SecurityFilterChain` instances. Authentication and authorization are typically decided **before controller execution**.

Key components:

- **AuthenticationEntryPoint:** typically initiates the response flow when an unauthenticated request requires authentication; may return 401 or redirect depending on the application type.
- **AccessDeniedHandler:** handles requests denied by access policy, typically 403 for authenticated users.
- **ExceptionTranslationFilter:** translates certain `AuthenticationException` and `AccessDeniedException` instances in the security filter chain into responses produced by the corresponding handlers.
- **SecurityFilterChain:** defines the security filters applied to a set of requests and their ordering.

Not every application using Spring Security returns exact 401/403 responses in all cases: browser logins may redirect, custom policies may differ, and CORS preflight also requires proper configuration.

**Do not try to solve 401/403 in security filters by adding `@ExceptionHandler(AuthenticationException.class)` and expecting controller advice to receive everything.** Instead, configure `AuthenticationEntryPoint` and `AccessDeniedHandler` (if you want to standardize API error bodies) alongside your security policy, then test them separately.

Authorization errors **inside controllers/services** when using method-level security also require checking how exceptions propagate in the framework; do not equate them with filter-level blocking before MVC.

## 7. DispatcherServlet Layer: Routing, Binding, Validation, and Converters

After the FilterChain, `DispatcherServlet` selects a handler via `HandlerMapping` and invokes it via `HandlerAdapter`. A request can fail **before entering the controller body**, even after reaching Spring MVC.

Common cases:

| MVC Stage | Error | Typical HTTP Status |
|---|---|---|
| HandlerMapping | No matching route | 404 |
| Method mapping | URL matches, HTTP method unsupported | 405 |
| Content negotiation | Accept incompatible with produces | 406 |
| Request media type | Content-Type does not satisfy consumes / reader | 415 |
| Argument resolution | Path variable cannot be converted to long | 400 |
| Request body decoder | Invalid JSON or unable to parse DTO | 400 |
| Bean Validation | DTO fails `@Valid` | 400 or per custom rule |
| Handler invocation | Controller throws exception | Per exception resolver / fallback |
| Response serialization | Unable to write response body | 5xx or other error, depending on response state |

Example controller accepting a `long` ID:

~~~java
@GetMapping("/api/products/{id}")
Product product(@PathVariable long id) {
    return productService.find(id);
}
~~~

This is a fragment used in a controller with a defined service/domain. A `GET /api/products/abc` request cannot bind `abc` to `long`. Spring MVC may return 400 before running `productService.find`.

**Implication:** If the controller produces no logs, it does not necessarily mean the request was blocked by a proxy or filter; it could have failed during MVC mapping, argument resolution, or validation.

### 7.1. What Can ControllerAdvice Handle?

`@RestControllerAdvice` combines `@ControllerAdvice` with `@ResponseBody` for `@ExceptionHandler` methods; Spring MVC uses it to handle many exceptions within DispatcherServlet's dispatch pipeline, including exceptions from controllers/services and many MVC framework exceptions.

You can extend `ResponseEntityExceptionHandler` to standardize many framework errors within MVC's scope, though you must understand its overridden methods and body structure for the Spring Framework version in use.

**Do not write an overly broad handler for `Exception.class` that returns 400/422 for everything.** Programming bugs, DB downtime, and serializer failures must not be “dressed up” as client errors. When a 500 fallback is needed, keep the response generic and log the exception internally once at an appropriate layer.

## 8. Business Errors: Domain Exceptions Must Be Translated to HTTP at the API Boundary

Services should speak in domain terms: product does not exist, insufficient stock, operation invalid in current state, improper ownership, or resource version has changed.

Avoid making every service directly aware of `HttpStatus` or `ResponseEntity`. One way to organize this:

~~~text
Controller  ---- calls ----> Service
   |                          |
   |                          +--> BusinessRuleException
   |                          +--> ProductNotFoundException
   |                          +--> DownstreamFailureException
   |
@RestControllerAdvice / Exception mapping
   |
   +--> HTTP 422 / 404 / 503 or 500 per API policy
~~~

### 8.1. Typical Mapping Table

| Scenario | Status to Consider | Notes |
|---|---|---|
| Malformed body, wrong param type | 400 Bad Request | Request syntax/format error |
| Invalid authentication | 401 Unauthorized | May come from security filter |
| Insufficient permissions | 403 Forbidden | Avoid leaking sensitive info |
| Resource does not exist | 404 Not Found | May also return 404 even when resource exists to intentionally hide access |
| State/version conflict | 409 Conflict | E.g., optimistic locking/duplicate state |
| HTTP preconditions not met | 412 Precondition Failed | When using If-Match/If-Unmodified-Since |
| Business rule violated | 422 Unprocessable Content | Depends on API design; not mandatory |
| Too many requests | 429 Too Many Requests | May come from gateway/filter |
| Dependency temporarily down | 503 Service Unavailable | Can include Retry-After when policy allows |
| Unexpected server error | 500 Internal Server Error | Do not expose stack trace/DB details |

These are **design suggestions**, not a rule forcing every business case to use those exact statuses. An API may use 400 instead of 422 under a unified contract; clients simply need to understand the error codes and retryability.

### 8.2. What Should Appear in an Error Response?

In Spring Framework 6 / Spring Boot 3, `ProblemDetail` models error responses based on the Problem Details standard (RFC 9457, succeeding RFC 7807). Core properties include:

- `type`: URI or identifier of the error type.
- `title`: short, stable description of the error type.
- `status`: HTTP status.
- `detail`: client-appropriate description without revealing sensitive information.
- `instance`: related resource/request instance, when appropriate.

You can add extension fields such as `code` (application error code), `traceId`, or `requestId`. Any trace ID included should come from actual tracing/propagation infrastructure rather than generating a random ID uncorrelated with logs.

**Do not include in public responses:** SQL queries, credentials, access tokens, stack traces, internal filesystem paths, sensitive raw upstream responses, or unvetted exception messages.

## 9. Runnable Example: Distinguishing Filter, Controller, and Service

The example uses **Java 17+**, **Spring Boot 3.x**, and the default embedded Tomcat from `spring-boot-starter-web`. The Java file has one public application class and package-private classes in the same package for easy reading.

Dependencies in a project `build.gradle` already configured with the Spring Boot plugin and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Create **src/main/java/demo/errors/ErrorLayersApplication.java**:

~~~java
package demo.errors;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class ErrorLayersApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorLayersApplication.class, args);
    }
}

record Product(long id, String name) {
}

class InvalidProductIdException extends RuntimeException {

    InvalidProductIdException(String message) {
        super(message);
    }
}

class ProductNotFoundException extends RuntimeException {

    ProductNotFoundException(String message) {
        super(message);
    }
}

class DemoInfrastructureException extends RuntimeException {

    DemoInfrastructureException(String message) {
        super(message);
    }
}

@Component
class RequestGateFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        if ("true".equalsIgnoreCase(
                request.getHeader("X-Demo-Block"))) {
            // Filter returns 403 and does not forward request to MVC.
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        chain.doFilter(request, response);
    }
}

@Service
class ProductService {

    Product find(long id) {
        if (id <= 0) {
            throw new InvalidProductIdException(
                    "Product id must be positive");
        }
        if (id == 42) {
            throw new ProductNotFoundException(
                    "Requested product was not found");
        }
        if (id == 99) {
            // Simulate an application/infrastructure failure.
            throw new DemoInfrastructureException(
                    "Simulated internal dependency failure");
        }
        return new Product(id, "product-" + id);
    }
}

@RestController
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/api/products/{id}")
    Product getProduct(@PathVariable long id) {
        return productService.find(id);
    }
}

@RestControllerAdvice
class ProductErrorAdvice {

    @ExceptionHandler(InvalidProductIdException.class)
    ProblemDetail invalidId(InvalidProductIdException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.UNPROCESSABLE_ENTITY, ex.getMessage());
        problem.setTitle("Business rule rejected");
        problem.setProperty("code", "INVALID_PRODUCT_ID");
        return problem;
    }

    @ExceptionHandler(ProductNotFoundException.class)
    ProblemDetail missing(ProductNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
        problem.setTitle("Product not found");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(DemoInfrastructureException.class)
    ProblemDetail internal(DemoInfrastructureException ex) {
        // Do not return ex.getMessage() to the client.
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Internal server error");
        problem.setTitle("Server error");
        problem.setProperty("code", "INTERNAL_ERROR");
        return problem;
    }
}
~~~

### 9.1. Why Is This an Example of Layering?

- `RequestGateFilter` runs **before DispatcherServlet**. If the client sends header `X-Demo-Block: true`, the filter sets status 403 and stops the chain. The controller and service **do not run**.
- `ProductController` handles HTTP routing and calls the service, without containing product lookup rules.
- `ProductService` classifies three business/simulated error cases via dedicated exceptions, without importing `HttpStatus`.
- `ProductErrorAdvice` converts exceptions from MVC request handling into `ProblemDetail`; business errors return 404/422, and the internal 500 error has a safe detail message.
- Exceptions from a **Filter** thrown before calling `chain.doFilter` are not automatically handled by ProductErrorAdvice. In the example, the filter directly returns 403 so it does not need to throw an exception.
- If a client calls `/api/products/not-a-number`, converting `@PathVariable` to `long` fails during MVC argument binding **before the controller body runs**, typically returning 400 via the framework mechanism.

**Do not treat `id=99` as a real DB failure.** It is only a simulated case to illustrate a service raising a 5xx error while the response hides internal exception details.

### 9.2. Running and Manual Verification

From a Gradle project with the Spring Boot plugin and wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows, use `gradlew.bat bootRun`. Assuming the server listens on `localhost:8080`, default context path, and no other Spring Security interfering, try these requests:

~~~bash
curl -i http://localhost:8080/api/products/1
curl -i http://localhost:8080/api/products/0
curl -i http://localhost:8080/api/products/42
curl -i http://localhost:8080/api/products/99
curl -i -H 'X-Demo-Block: true' http://localhost:8080/api/products/1
curl -i http://localhost:8080/api/products/not-a-number
~~~

Expected outcomes:

| Request | Status | Deciding Layer |
|---|---|---|
| GET `/api/products/1` | 200 | Controller → service |
| GET `/api/products/0` | 422 | Service exception → ControllerAdvice |
| GET `/api/products/42` | 404 | Service exception → ControllerAdvice |
| GET `/api/products/99` | 500 | Simulated service exception → ControllerAdvice |
| GET with `X-Demo-Block: true` | 403 | Servlet filter, before MVC |
| GET `/api/products/not-a-number` | Typical 400 | MVC path-variable conversion |

The 200 response body is JSON equivalent to:

~~~json
{"id":1,"name":"product-1"}
~~~

The 404 response from `ProductErrorAdvice` may have a Problem Details shape equivalent to:

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Requested product was not found",
  "instance": "/api/products/42",
  "code": "PRODUCT_NOT_FOUND"
}
~~~

`instance` may be populated by Spring or differ depending on Spring Framework/Boot configuration; do not rigidly assert this field when the example only configures `code`, `title`, and `detail`. JSON fields and key order may also vary.

**The filter's 403 response only sets the status**. Do not expect an automatic `ProblemDetail` body or error code from `ProductErrorAdvice` in that case.

## 10. Automated Testing with MockMvc

To protect the layering contract, test both HTTP status and indicators of the handling source, rather than only calling `ProductService.find` directly.

Add `spring-boot-starter-test` in `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

File **src/test/java/demo/errors/ErrorLayersApplicationTest.java**:

~~~java
package demo.errors;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorLayersApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulRequestReturnsProduct() throws Exception {
        mvc.perform(get("/api/products/1"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.id").value(1))
           .andExpect(jsonPath("$.name").value("product-1"));
    }

    @Test
    void businessRuleMapsTo422() throws Exception {
        mvc.perform(get("/api/products/0"))
           .andExpect(status().is(422))
           .andExpect(jsonPath("$.code").value("INVALID_PRODUCT_ID"));
    }

    @Test
    void missingProductMapsTo404() throws Exception {
        mvc.perform(get("/api/products/42"))
           .andExpect(status().isNotFound())
           .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void internalFailureHidesPrivateMessage() throws Exception {
        mvc.perform(get("/api/products/99"))
           .andExpect(status().isInternalServerError())
           .andExpect(jsonPath("$.detail").value("Internal server error"));
    }

    @Test
    void servletFilterCanStopRequestBeforeController() throws Exception {
        mvc.perform(get("/api/products/1")
                .header("X-Demo-Block", "true"))
           .andExpect(status().isForbidden());
    }

    @Test
    void mvcBindingErrorIsNotBusinessRule() throws Exception {
        mvc.perform(get("/api/products/not-a-number"))
           .andExpect(status().isBadRequest());
    }
}
~~~

This test file uses Spring Boot Test 3.x's `@AutoConfigureMockMvc` and Spring Test's `MockMvc`. With the demo configuration, without security filters or other custom error handling, the tests verify:

1. Successful controller/service flow.
2. Business exceptions translated into appropriate statuses/codes.
3. Internal error responses do not disclose the exception message.
4. Filter blocks requests with 403 before MVC.
5. Type conversion errors are handled by Spring MVC differently from service exceptions.

Run:

~~~bash
./gradlew test
~~~

**Limitation of MockMvc:** it executes servlet/MVC test infrastructure without **opening a real TCP socket**. Therefore, these tests do not prove DNS, TLS, reverse proxy 502/504, or Tomcat header limits work. To test container/proxy behavior, you must run integration tests over real HTTP or a production-like deployment environment.

## 11. Spring Boot `/error` Fallback and Servlet ERROR Dispatch

When an exception is not handled by `@ExceptionHandler` or an MVC exception resolver, Spring Boot provides fallback error handling. In a typical Spring MVC Servlet application, `/error` and `BasicErrorController` may participate depending on auto-configuration and container error dispatch.

Situations to distinguish:

- **Handled at ControllerAdvice:** MVC finishes creating the response; no fallback is needed for the same error.
- **Unhandled exception:** the error may be routed to container/Spring Boot error handling; the fallback response depends on `Accept`, configuration, and response state.
- **Servlet filter calls `response.sendError(...)`:** may trigger the Servlet container's error dispatch mechanism.
- **Filter only calls `response.setStatus(...)` and returns:** not automatically equivalent to `sendError`; do not assume the `/error` fallback always runs.
- **Response already committed:** status/headers/body may no longer be modifiable into a new JSON error.

With `ERROR dispatch`, some filters may run again if registered for the ERROR dispatcher type. `OncePerRequestFilter` has rules regarding async/error dispatches; the class name does not guarantee a piece of logic runs strictly once across every request lifecycle.

**Do not replace controller advice with a catch-all filter catching every exception.** Catching and turning every exception into JSON inside a filter can break MVC, Spring Security, and container handling logic, and cause writes after a response has already been committed.

## 12. Errors from Services Calling Databases or External APIs

A service may call a repository/JDBC or an HTTP client. Here you must distinguish **business errors** from **infrastructure errors**:

| Error Type | Example | Handling Approach |
|---|---|---|
| Business entity not found | Product ID does not exist | Domain exception → 404 |
| Invalid business rule | Order already closed, cannot modify | 409/422 depending on contract |
| Optimistic locking | Client version is stale | 409 or 412 depending on HTTP preconditions |
| DB connection timeout | Pool exhausted, DB unresponsive | Internal error/dependency unavailable, typically 5xx |
| Remote API returns HTTP 400 | Request sent downstream is invalid | Investigate contract; do not blindly pass 400 to client if app is at fault |
| Remote API returns HTTP 503 | Downstream unavailable | Can map to 503 with appropriate retry policy |
| Remote network timeout | Uncertain whether downstream received and processed it | Timeouts, idempotency, circuit breaker |
| Serialization error | DTO/ObjectMapper fails to write body | Technical error, typically 5xx |

**Do not mechanically translate** a `WebClientResponseException.NotFound` from another system into a 404 for the current API. A downstream 404 may mean the upstream URL was misconfigured, not that the client's domain resource does not exist. The service must understand the semantics of its dependency's errors.

### 12.1. WebClient Errors: Status vs. Transport

When Spring uses `WebClient`, there are two categories of scenarios:

- Downstream **returns an HTTP response with an error status**: in call styles like `retrieve()`, WebClient emits `WebClientResponseException` for 4xx/5xx by default; or code can intentionally handle response statuses directly.
- HTTP request **fails due to connection/transport**: you may see `WebClientRequestException` or a wrapped network exception. There may not even be an HTTP response/status from downstream.

Do not just catch `Exception` and return 503 for everything. Timeouts, authentication failures, malformed requests, and domain conflicts mean different things, especially for retries.

### 12.2. Retries Must Be Controlled

- Only retry errors that are likely transient and operations that are safe to repeat.
- Enforce maximum retry attempts, backoff, and jitter where appropriate.
- Respect the overall request deadline; do not let retries run indefinitely.
- Avoid retry storms when a DB/downstream service is down.
- For POST/payments, use idempotency keys or reconciliation.
- Use circuit breakers/bulkheads when workload and libraries support them; do not force every project to use one specific mechanism.

## 13. Distinguishing 4xx, 5xx, and Errors Without an HTTP Status

A responsible layering breakdown:

| Group | Meaning | Who Usually Needs to Act |
|---|---|---|
| 4xx due to client request | Malformed request, unauthorized, forbidden, conflict | Client/user or contract |
| 4xx due to app business policy | Business rule not satisfied | Client adjusts request or handles business state |
| Application 5xx | Bug, dependency failure, insufficient server resources | Operations/application team |
| Proxy 5xx | Backend unavailable or gateway timeout | Infrastructure and backend |
| Transport exception, no HTTP response | DNS/TCP/TLS/reset/timeout | Investigate client/network/server |

**Do not write a rule “never log 4xx, always alert on 5xx”.** You may need to monitor 401 brute force attempts, 403 abuse, 429 spikes, and sudden 400 increases caused by regressions. Conversely, some 404s for optional resources are normal business outcomes. Logging/alerting depends on your threat model and SLOs.

## 14. Designing a Consistent Error Contract Without Leaking Information

An error response should have stable meaning for clients, for example:

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Requested product was not found",
  "code": "PRODUCT_NOT_FOUND"
}
~~~

Considerations:

- `code` is a **stable business code** that clients can branch on instead of parsing detail text.
- `title` should be clear and not change arbitrarily.
- `detail` should be safe; it can be localized per API design.
- HTTP status is part of the protocol; do not wrap all errors in status 200 with a code inside JSON.
- `requestId` or `traceId` can help support investigations, but must come from actual tracing/logging.
- Do not return SQL table names, passwords, filesystem paths, internal hostnames, or stack traces.
- For requests that never reach the application, proxies/gateways may return a different body; a “single JSON format for all errors” contract requires multi-layer configuration, not just a `@RestControllerAdvice`.

### 14.1. CORS and Security Can Mislead Clients

Browser JavaScript may only see a CORS error or “network error” if preflight is blocked or the response lacks required CORS headers. The backend may actually have returned 403/500, yet the frontend cannot read the body.

Check the **Network tab, OPTIONS preflight, origin, CORS config, and filter ordering** instead of assuming the API sent no response just because fetch rejected.

## 15. Observing Errors: Request ID, Traces, and Layered Logs

To diagnose a production error, you need to correlate:

~~~text
client request id
      |
      v
gateway access log / upstream status
      |
      v
container access log
      |
      v
security/filter decision
      |
      v
MVC handler + exception resolver
      |
      v
service/downstream span
~~~

Practical guidelines:

1. **Correlation ID:** use a header issued/validated by a trusted system or standard tracing; do not blindly trust any client-supplied request ID as an authoritative identifier.
2. **Request context:** log HTTP method, route template, status, duration, dependency, trace/span ID; restrict paths/raw queries containing sensitive data.
3. **Log an error responsibly:** an exception may pass through service, controller advice, and gateway. Do not print full stack traces repeatedly at every layer.
4. **4xx can be an operational signal:** spikes in 401/403/429 or validation failures may indicate regressions or abuse.
5. **5xx must have internal investigation context:** log the exception safely with a trace, without returning stack traces to the client.
6. **Measure timeouts at each hop:** client deadline, proxy upstream timeout, server/controller timeout, DB/client timeout; know which layer terminates first.
7. **Use metrics/Actuator when enabled:** monitor request status distribution, p95/p99, routes, downstream latency, and pool saturation; do not assume every metric exists automatically if unconfigured.

**Note:** in async processing or WebFlux, a request may cross multiple threads. A standard `ThreadLocal`/MDC does not automatically propagate across all scheduler boundaries; use context propagation suited to your framework.

## 16. How Error Handling Differs in Spring WebFlux

The layering principles still apply, but the pipeline differs:

~~~text
Client -> Netty/TCP/TLS -> WebFilter -> DispatcherHandler
       -> HandlerMapping / HandlerAdapter
       -> Reactive controller -> Mono/Flux -> downstream
~~~

- With **Reactor Netty**, there is no Servlet FilterChain/DispatcherServlet as in Servlet MVC.
- `WebFilter` processes requests at the reactive web layer before the reactive handler.
- `@RestControllerAdvice` / `@ExceptionHandler` can still handle errors from annotated WebFlux controllers through the corresponding resolver mechanism.
- WebFlux also has `WebExceptionHandler` implementations and Spring Boot error handling (such as `ErrorWebExceptionHandler`) for errors unhandled at the handler layer.
- With **functional WebFlux routes**, handle errors via the reactive pipeline/router and global error handlers; do not assume an annotated controller's `@ExceptionHandler` covers all functional handlers.
- An error occurring after a streaming response has already sent part of its body may not be able to change status/headers into a new ProblemDetail response.
- A `Mono.error(...)` is only an error signal in a reactive pipeline; turning it into an HTTP status depends on the handler/error resolver wrapping that publisher.

In WebFlux, avoid `block()` on the Netty event loop. If a fallback error handler performs blocking JDBC or file I/O, error handling itself can stall the server. Blocking workloads must be offloaded appropriately or the architecture should use MVC.

## 17. Test Suite Needed for Each Layer

A complete testing strategy should not consist solely of unit tests for ControllerAdvice:

| Layer | Appropriate Testing Method | What to Verify |
|---|---|---|
| Network/TLS | Integration test with real client, wrong cert/port | Transport exception, no fake HTTP status |
| Proxy/gateway | Staging through ingress, timeout/size settings | 502/503/504/413 and access logs |
| Servlet container | Real server test, malformed/large-header requests | Whether requests are rejected before filters |
| Filter | MockMvc/Servlet integration | Response blocked, controller does not execute |
| Spring Security | Security test through filter chain | 401/403, anonymous/authenticated, body/headers |
| MVC mapping/binding | MockMvc | 400/404/405/406/415 for specific requests |
| Controller/Service | MockMvc + service tests | 200, 404, 409/422, 500 safe detail |
| DB/HTTP downstream | Integration stub/fault injection | Timeouts, retries, cancellation, pool limits |
| Async/Streaming | Server/client integration | Client abort, response already committed |

**Do not conflate test types:** `MockMvc` does not open real TCP/TLS connections, so it cannot verify DNS/TLS failures or reverse proxies. Run HTTP tests through the container/ingress for those paths.

### 17.1. Questions When Triaging an Incident

1. **Did the client receive an HTTP status or only a network exception?** If there is no response, start with DNS/TCP/TLS/client timeout.
2. **Does the gateway have an access log and upstream status?** If the gateway returned the error before the app, do not hunt for controller exceptions.
3. **Did the container receive the request?** If not, check ingress, port, listener, and routing.
4. **Did the Servlet FilterChain execute?** If blocked by security/filters, the controller was not invoked.
5. **Did HandlerMapping find a controller?** If method/path/headers were wrong, look at 404/405/406/415.
6. **Did execution enter the controller method body?** Binding and JSON decoding can fail earlier.
7. **Did the service throw a business error or a dependency failure?** Map the status semantically.
8. **Was the response already committed?** Streaming errors may not be able to change status.
9. **Is there a trace ID spanning all hops?** Use correlation to avoid confusing two different requests.
10. **Can the error be reproduced with a test at the right layer?** Do not treat a MockMvc test as proof of gateway/network behavior.

## 18. Common Mistakes

**Mistake 1 — Blaming the Controller for every error.** Many failures happen before the controller: proxy, container, security, routing, or body binding. Check the call path before changing business logic.

**Mistake 2 — Using ControllerAdvice to catch DNS/TLS/filter errors.** Impossible because those calls occur outside MVC exception resolution. Handle them at their respective layers.

**Mistake 3 — Assuming every timeout means the server never processed the request.** The request may have executed and lost its response. Use idempotency/reconciliation, especially for payments.

**Mistake 4 — Catching Exception and returning HTTP 200 with "success=false".** Breaks protocol semantics, hinders monitoring, caching, and client retries. Use proper HTTP statuses and stable error codes.

**Mistake 5 — Returning exception.getMessage() for all 500s.** Risks exposing SQL, internal hostnames, paths, or secrets. For internal errors, return a safe message and log details separately.

**Mistake 6 — Returning 500 for all business errors.** Missing resources, version conflicts, or business preconditions have more appropriate 4xx statuses depending on the contract.

**Mistake 7 — Turning every downstream 404/400 into a client error.** Understand the downstream contract; an upstream 404 may mean the app called the wrong URL.

**Mistake 8 — Writing a catch-all filter wrapping the entire request.** It can swallow exceptions that MVC/Security/container need to handle, modify committed responses, or lose traces.

**Mistake 9 — Assuming Spring Security 401/403 goes through @RestControllerAdvice.** Security handles many cases in the filter chain; use appropriate entry points and denied handlers.

**Mistake 10 — Testing only the happy path.** Test filter short-circuiting, type conversion 400s, domain not found/conflict, 500 safe detail, proxy timeouts, and request size limits.

**Mistake 11 — Always retrying on 503.** Can amplify load on a failing service. Retries must be bounded, with deadlines, idempotency, and backoff.

**Mistake 12 — Ignoring error dispatch and committed responses.** Streaming errors or filters re-running on ERROR dispatch can produce duplicate logs and invalid bodies.

## 19. Pre-Deployment Checklist

- Clearly identify whether the application uses Spring MVC Servlet or WebFlux Reactive.
- Map the path client → gateway → container → filter/security → MVC/WebFlux → service → downstream.
- Associate HTTP statuses with the **layer that actually created the response**, not by inferring from status alone.
- For network failures with no HTTP response, preserve transport exceptions rather than fabricating a 500.
- Place auth/authz responses in Spring Security properly.
- Place validation/mapping errors in Spring MVC, business rules in services, and status translation at the API boundary.
- Use `ProblemDetail` or a unified error contract for application-scoped errors.
- Do not expose stack traces, raw DB/network exceptions, tokens, or internal details.
- Verify `/error` fallback and ERROR dispatch instead of assuming one global advice catches everything.
- Only retry idempotent operations or those with side-effect controls.
- Maintain correlation IDs, metrics, and logs from proxy to application/downstream.
- Test each layer separately, including network/proxy/Servlet, not just MockMvc.
- Verify HTTP status/error bodies when responses have started streaming or clients disconnect.
- Monitor p95/p99 latency, 4xx/5xx distribution, client timeouts, and dependency failures by route/hop.

**Conclusion:** Web errors do not live in a single layer. **Network/proxies** can fail before HTTP or before the app; the **Servlet container** can reject requests before filters; **Filters/Spring Security** can stop requests before DispatcherServlet; **Spring MVC** can fail during matching, binding, or controller invocation; and **services** can detect business rule violations or unavailable infrastructure. Proper design means handling and recording errors at the **layer with sufficient context**, translating them into HTTP statuses/bodies only at the right boundary, and using tests and traces to prove the actual execution path.