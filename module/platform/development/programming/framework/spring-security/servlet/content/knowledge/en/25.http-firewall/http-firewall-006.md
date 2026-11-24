# RequestRejectedException and RequestRejectedHandler in Spring Security Servlet

> **Scope:** Spring Security 6.x on the Servlet stack (Spring MVC, typically paired with Spring Boot 3.x and Java 17+). This lesson focuses on errors caused when `HttpFirewall` rejects an HTTP request and the `RequestRejectedHandler` mechanism converts that error into an HTTP response. This is the Servlet flow; WebFlux has its own filters and request classes. Certain rejection decisions also depend on Spring Security version, Servlet container, and reverse proxy.

## 1. The Problem: Requests Blocked Even Before Authentication

We normally picture an HTTP request moving through Spring Security in order: extract credentials → check permissions → controller. However, there is an earlier inspection layer: **`HttpFirewall`**, used by `FilterChainProxy` to inspect and standardize how Spring Security observes the request before selecting and running a `SecurityFilterChain`.

A request with an unnormalized path, suspicious URL encoding, disallowed separator, or HTTP method outside the allowlist can be rejected by the firewall **from the very start**. In that case:

- The controller has not been invoked; `@GetMapping`, `@PostMapping`, or `@ExceptionHandler` in Spring MVC may never get a chance to run.
- The request has not been evaluated by ordinary `authorizeHttpRequests` rules.
- Spring Security throws `RequestRejectedException`; `RequestRejectedHandler` determines the HTTP response for that error.
- The common response code when using `HttpStatusRequestRejectedHandler` is **400 Bad Request**, not 401 for unauthenticated or 403 for insufficient permissions.

Distinguishing this case is especially useful when clients report "a URL worked on my machine but production returns 400," when a reverse proxy modifies the path, or when a request intentionally contains `;`, `%2F`, or repeated slashes causing inconsistent interpretation across the proxy, Spring Security, and controller layers.

## 2. Relationship Between HttpFirewall, Exception, and Handler

| Object | Responsibility | What Not to Confuse It With |
| --- | --- | --- |
| `HttpFirewall` | Interface that inspects/wraps the request and response before security filters. | Not an authorization rule. |
| `StrictHttpFirewall` | Common strict implementation blocking many non-standard requests or disallowed characters/methods. | Does not mean every URL with encoding is blocked; exact rules depend on input/version. |
| `RequestRejectedException` | Signal that **a request was rejected by the firewall**; carries the reason as an exception. | Distinct from `AuthenticationException` and `AccessDeniedException`. |
| `RequestRejectedHandler` | Handles the request/response after the exception is caught, e.g., returning 400 and logging appropriately. | Should never "let the request through" or treat it as valid access. |
| `FilterChainProxy` | Orchestrates the firewall, selects the security chain, and delegates rejections to the corresponding handler. | A single `SecurityFilterChain` does not assume the proxy's full role. |

Conceptual flow:

~~~text
HTTP client / browser
        |
        v
Servlet container / reverse proxy (may reject early)
        |
        v
DelegatingFilterProxy -> FilterChainProxy
        |
        +--> HttpFirewall.getFirewalledRequest(request)
        |        |
        |        +-- Valid --> FirewalledRequest
        |        |               |
        |        |               +--> select SecurityFilterChain
        |        |               +--> security filters
        |        |               +--> DispatcherServlet / controller
        |        |
        |        +-- Invalid --> RequestRejectedException
        |                                  |
        |                                  v
        |                          RequestRejectedHandler
        |                                  |
        |                                  +--> response 400 (example)
        |
        +--> HttpFirewall.getFirewalledResponse(response)
~~~

The diagram illustrates responsibilities, not the exact line-by-line source order of a specific version. Most importantly, **rejection happens within `FilterChainProxy`'s execution scope, before ordinary security and business processing**.

If a proxy or Servlet container already rejected the request before it reached Spring Security, the application may still return 400 without **any Spring Security `RequestRejectedException`**. You must determine where the response originated via logs and infrastructure inspection.

## 3. What Is `RequestRejectedException`?

`org.springframework.security.web.firewall.RequestRejectedException` is the exception indicating a request violated firewall requirements. Common examples under default `StrictHttpFirewall` or comparably strict configs:

1. **Unnormalized path:** path representations that cause layers to interpret differently, such as `..` variants, double slashes, or abnormal separator characters.
2. **Ambiguous URL encoding:** certain encoded forms such as encoded slashes (`%2F`), backslashes (`%5C`), or percent encodings tightly controlled by the firewall.
3. **Semicolons/matrix parameters:** `/items;version=1` can be blocked when semicolons are disallowed, preventing layers from parsing paths differently.
4. **Disallowed HTTP methods:** methods such as `TRACE` are outside `StrictHttpFirewall`'s default list.
5. **Suspicious header or parameter names/values:** control characters or data failing safety policy may be rejected in versions supporting those checks.

Not every example string reaches Spring Security in its original form. Containers, load balancers, and proxies may decode, normalize, or block the request earlier. Nor is every "URL containing `%`" guaranteed to be blocked. Always test **the exact path, exact method, exact configuration, and exact receiving layer**.

### Example: Why Does URL Normalization Relate to Security?

Imagine a proxy using the original path string to decide whether a route belongs to `/admin/**`, while another component decodes `%2F` or strips `..` before selecting a controller. If two layers perceive different paths, a request could pass a rule meant for a different endpoint. The firewall reduces this class of risk by rejecting ambiguous representations.

A clean, explicitly normalized path should always be preferred over relaxing the firewall merely to permit multiple equivalent encodings.

### Nature of the Exception

- The exception **does not prove the client is attacking**. It states that the request violated active firewall policy; it could stem from a legacy URL, double proxy encoding, a crawler, a buggy HTTP client, or a malicious actor.
- Never return raw `exception.getMessage()` as public response content. The message may contain request details and client-controlled data; reflecting it in the response risks configuration disclosure, log injection, or unnecessary exposure.
- Never "catch and ignore" to continue running `FilterChainProxy`. A request marked invalid must be handled at the firewall boundary, or else fix how the client/proxy constructs the request.

## 4. Where and How Does `RequestRejectedHandler` Handle the Exception?

`org.springframework.security.web.firewall.RequestRejectedHandler` is a functional interface in the web security layer. Core contract:

~~~java
void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        RequestRejectedException requestRejectedException)
        throws IOException, ServletException;
~~~

This signature is for explaining the API; real Java files need the Servlet/Spring Security imports. The handler is invoked when `FilterChainProxy` catches `RequestRejectedException` within its processing scope.

The handler is responsible for **deciding the response**:

- Set the HTTP status, typically 400.
- Write a consistent body if the API expects JSON, e.g., `application/problem+json`.
- Emit sanitized logs or metrics for operations.
- Do not include raw exception messages or raw URIs without log sanitization and clear security justification.

The handler is not responsible for granting permissions, performing authentication, checking CSRF, or parsing JSON bodies for controllers. Those belong to later pipeline stages.

### 4.1. Using the Built-In `HttpStatusRequestRejectedHandler`

If only an HTTP status is needed, `HttpStatusRequestRejectedHandler` is concise:

~~~java
RequestRejectedHandler handler =
    new HttpStatusRequestRejectedHandler(400);
~~~

This is an API fragment requiring imports for `org.springframework.security.web.firewall.RequestRejectedHandler` and `HttpStatusRequestRejectedHandler` in a Spring Security project. This handler sends an HTTP error with the configured status. Exactly what HTML/JSON body the server returns after `sendError` depends on the Servlet container, error dispatch, and application.

Modern Spring Security versions/configurations typically use a 400 response for firewall rejections. To avoid guessing default messages or bodies, check the actual response in your running version; if you need a fixed JSON body, write a custom handler.

### 4.2. Customizing: Stable JSON Without Exposing Request Content

An API might desire a fixed error payload:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json;charset=UTF-8

{"type":"about:blank","title":"Bad Request","status":400,"detail":"Invalid HTTP request"}
~~~

This is a **sample response from the custom handler** in Section 6, not a guaranteed body emitted automatically by Spring Security. Keep the message generic; omit the offending URI, tokens, cookies, or exception messages from the response.

## 5. How Does It Differ From 401/403 and MVC Errors?

| Scenario | Typical Handling Component | Typical Status |
| --- | --- | --- |
| Path/header/method rejected by firewall | `HttpFirewall` → `RequestRejectedException` → `RequestRejectedHandler` | 400 with standard status handler |
| Unauthenticated user on protected resource | `AuthenticationEntryPoint` | 401 or login redirect |
| Authenticated user lacking permission | `AccessDeniedHandler` | 403 |
| Session-cookie POST missing CSRF token | `CsrfFilter` and access denied handling | 403 |
| Controller request-body validation fails | Spring MVC exception handling | Typically 400 |
| Servlet container itself rejects malformed HTTP request | Container/proxy | Typically 400, not necessarily a Spring Security exception |

**Same status 400 does not mean same cause.** For firewall rejection, the controller and `@ControllerAdvice` may not have run at all. For `@Valid` or JSON parsing errors during controller argument resolution, handling usually occurs in MVC and uses MVC exception handlers.

Never try to resolve a 400 error by adding `permitAll()` to the blocked URL. `permitAll` is an authorization rule for requests that reach that stage; the firewall decides first whether to accept the request's shape at all.

## 6. Spring Boot / Spring Security 6 Configuration: Custom Handler

The example uses Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/Spring MVC, with dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. All files share package `com.example.firewalldemo`. These are **Spring Boot application Java files**, not a single-file program runnable with `javac` without dependencies.

### 6.1. Application Entry Point

**`src/main/java/com/example/firewalldemo/FirewallDemoApplication.java`:**

~~~java
package com.example.firewalldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FirewallDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FirewallDemoApplication.class, args);
    }
}
~~~

### 6.2. Creating a JSON-Returning `RequestRejectedHandler`

**`src/main/java/com/example/firewalldemo/JsonRequestRejectedHandler.java`:**

~~~java
package com.example.firewalldemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.RequestRejectedHandler;

public final class JsonRequestRejectedHandler implements RequestRejectedHandler {

    private static final Logger log =
            LoggerFactory.getLogger(JsonRequestRejectedHandler.class);

    private static final String BODY =
            "{\"type\":\"about:blank\","
          + "\"title\":\"Bad Request\","
          + "\"status\":400,"
          + "\"detail\":\"Invalid HTTP request\"}";

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            RequestRejectedException exception) throws IOException {

        // Never log raw URL, headers, query string, or exception message.
        log.warn("HttpFirewall rejected a request; exceptionType={}",
                exception.getClass().getSimpleName());

        if (response.isCommitted()) {
            // Cannot write a new status/body once the response is already committed.
            return;
        }

        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.getWriter().write(BODY);
    }
}
~~~

`RequestRejectedHandler.handle` permits declaring `IOException, ServletException`; this implementation needs only `IOException`. The code uses UTF-8, status 400, and a fixed body so the rejected URL is not exposed. Checking `response.isCommitted()` avoids writing to an already-sent response; in practice, a firewall rejection usually occurs before any response is committed.

The application may also record metrics using a normalized rule name, but watch **cardinality**: never use raw URLs/queries or exception messages as metric labels because an attacker can generate unbounded distinct values.

### 6.3. Wiring the Firewall and Handler Into `WebSecurity`

**`src/main/java/com/example/firewalldemo/SecurityConfig.java`:**

~~~java
package com.example.firewalldemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.RequestRejectedHandler;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class SecurityConfig {

    @Bean
    StrictHttpFirewall strictHttpFirewall() {
        // Keep strict default checks.
        return new StrictHttpFirewall();
    }

    @Bean
    RequestRejectedHandler requestRejectedHandler() {
        return new JsonRequestRejectedHandler();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(
            StrictHttpFirewall firewall,
            RequestRejectedHandler rejectedHandler) {

        return web -> {
            web.httpFirewall(firewall);
            web.requestRejectedHandler(rejectedHandler);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/hello").permitAll()
                .anyRequest().authenticated())
            .build();
    }
}
~~~

**Why use `WebSecurityCustomizer`?** `HttpSecurity` primarily builds one `SecurityFilterChain`. By contrast, `HttpFirewall` and `RequestRejectedHandler` attach to **`FilterChainProxy`**, the outer orchestrator wrapping the security chains. Configuring `WebSecurityCustomizer` places both components at the proper spot; `authorizeHttpRequests` configuration cannot replace them.

The application does not need to manually instantiate a `FilterChainProxy` or manually register an extra `CorsFilter`/`DelegatingFilterProxy` just to deploy this handler. Spring Security/Spring Boot constructs and wires the filter when the appropriate starters and security configuration are loaded.

### 6.4. Valid Controller for Comparison

**`src/main/java/com/example/firewalldemo/HelloController.java`:**

~~~java
package com.example.firewalldemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "ok");
    }
}
~~~

For a valid `GET /api/hello` request, the controller handler returns:

~~~json
{"message":"ok"}
~~~

For a request rejected by `StrictHttpFirewall` and dispatched by `FilterChainProxy` to the custom handler, the response has status 400 and the fixed JSON body described in Section 4. Having a `permitAll` controller does not make an abnormal URL acceptable.

### 6.5. How to Run the Project

Add the Spring Web and Security starters; Spring Boot 3.x uses the Jakarta Servlet API (`jakarta.servlet.*`). Place the files in the package above inside a Spring Boot project, then run with the project's build tool:

~~~bash
./gradlew bootRun
~~~

On Windows with the Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

These commands assume the project already has the Gradle wrapper and Spring Boot plugin. The Maven equivalent is `./mvnw spring-boot:run`. This lesson does not provide a one-size-fits-all `build.gradle` for every version; rely on dependency versions managed by the Spring Boot BOM so Spring Security and Spring MVC remain compatible.

## 7. Using the Built-In Handler Instead of Custom JSON

Not every application needs a custom-written JSON body. If only status 400 is required, you can use the built-in handler. This is an **alternative** to the `requestRejectedHandler` bean in Section 6; do not register two beans of the same type and expect Spring to choose one automatically:

~~~java
@Bean
RequestRejectedHandler requestRejectedHandler() {
    return new HttpStatusRequestRejectedHandler(400);
}
~~~

Relevant imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.firewall.HttpStatusRequestRejectedHandler;
import org.springframework.security.web.firewall.RequestRejectedHandler;
~~~

This is a fragment inside a `@Configuration` class whose `WebSecurityCustomizer` wires the handler. `HttpStatusRequestRejectedHandler` fits when clients only need an error status and do not require a uniform body. Error messages/HTML generated by the container after `sendError` should not be treated as a stable API contract without verification.

### When Should You Choose a Custom Handler?

- Public APIs with an explicit `application/problem+json` error contract.
- Safe logging or fixed metrics for blocked requests without leaking input.
- A uniform response structure across rejections occurring at the firewall.

Even when returning JSON, never turn the handler into a "normalizer" that silently rewrites the URL, strips characters, and re-executes the request. That can alter which endpoint the client actually hits.

## 8. Understanding `StrictHttpFirewall` Policy Before Relaxing

`StrictHttpFirewall` is designed to reject untrusted HTTP requests whose representations could produce discrepancies in path matching. Some legacy projects use matrix variables, encoded slashes, or custom HTTP methods; when default settings are active, previously accepted requests may turn into 400s.

Preferred resolution order:

1. Confirm whether the client truly needs that path/header/method form.
2. Confirm whether a reverse proxy is decoding/encoding/normalizing and altering the request.
3. If possible, update the client to canonical paths and avoid unnecessary percent-encoding.
4. Only when a mandatory compatibility requirement exists, evaluate one specific firewall option and confirm all layers interpret the path identically.
5. Maintain tests for valid URLs, malicious URLs, and path matching/authorization before and after the change.

Example solely to illustrate the `setAllowedHttpMethods` API—**unnecessary if the default meets business requirements**:

~~~java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowedHttpMethods(java.util.List.of(
    "GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"
));
~~~

The snippet above is a Java configuration fragment, not a standalone runnable class. Avoid allowing all methods via `setUnsafeAllowAnyHttpMethod(true)` to work around a faulty TRACE/OPTIONS case; widening the allowlist expands the protocol surface the application must handle safely.

Similarly, enable options such as semicolons or encoded slashes only after thoroughly testing behavior in the container, reverse proxy, Spring MVC, and security matchers. Allowing a character at the firewall **does not mean** authorization and the controller handle it identically, nor does it eliminate path traversal risks.

### `permitAll` and `web.ignoring` Are Not Fixes

- `permitAll` on a path affects authorization only **after the request passes the firewall**.
- Configuring a path to bypass certain security filters does not mean every request skips the firewall in `FilterChainProxy`; check your exact configuration and entrypoints.
- Never write a custom servlet/filter that catches every exception and returns 200 for a rejected request, as that undermines the protective policy.
- If a frontend produces incompatible `/api/items;session=…` URLs, prioritize fixing URL generation or session transport rather than enabling semicolons globally.

## 9. Unit Testing: Proving the Exception and Handler

For reliable tests, first test `StrictHttpFirewall` directly with `MockHttpServletRequest` and test the handler with `MockHttpServletResponse`. Add `spring-boot-starter-test` and `spring-security-test` in test scope if the project needs those libraries; Mock Servlet classes live in `spring-test`, while JUnit 5 is provided by the test starter.

**`src/test/java/com/example/firewalldemo/FirewallRejectionTest.java`:**

~~~java
package com.example.firewalldemo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FirewallRejectionTest {

    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    @Test
    void rejectsSemicolonInRequestUriByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/items;debug=true");

        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(request));
    }

    @Test
    void rejectsTraceMethodByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("TRACE", "/api/hello");

        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(request));
    }

    @Test
    void normalRequestIsNotRejectedByFirewall() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/hello");

        assertFalse(request.getRequestURI().contains(";"));
        // Does not throw an exception when the request has a valid shape.
        assertTrue(firewall.getFirewalledRequest(request) != null);
    }

    @Test
    void customHandlerWritesSanitized400Response() throws Exception {
        JsonRequestRejectedHandler handler =
            new JsonRequestRejectedHandler();

        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/hello");

        MockHttpServletResponse response = new MockHttpServletResponse();

        handler.handle(request, response,
            new RequestRejectedException("sensitive request details"));

        assertEquals(400, response.getStatus());
        assertTrue(response.getContentType()
                .startsWith("application/problem+json"));
        assertTrue(response.getContentAsString()
                .contains("\"detail\":\"Invalid HTTP request\""));
        assertFalse(response.getContentAsString().contains("sensitive"));
    }
}
~~~

These tests separate two responsibilities:

- The firewall tests verify that specific inputs throw `RequestRejectedException` **before any controller runs**.
- The handler test verifies the error contract returns a fixed 400 without reflecting the exception message.

Testing with `MockHttpServletRequest` tests the firewall directly; it is not an end-to-end Servlet container test. For any real application, add integration tests with `MockMvc` or an HTTP test server to confirm `WebSecurityCustomizer`, `FilterChainProxy`, the proxy, and the error response are wired as designed.

Run in a matching Gradle project:

~~~bash
./gradlew test
~~~

Or on Windows:

~~~powershell
.\gradlew.bat test
~~~

**Expectation:** all 4 tests pass with the proper configuration and dependencies. No fabricated stdout log is shown here because Gradle test logging varies per project.

### Testing With Real HTTP While Debugging

A request URL containing `;` can be tested in an internal environment permitted for testing:

~~~bash
curl --path-as-is -i "http://localhost:8080/api/items;debug=true"
~~~

`--path-as-is` instructs `curl` not to normalize certain path forms before sending. However, a proxy or Servlet container can still block or alter the request before Spring. If a 400 response bypasses Spring, direct handler tests still pass while not proving that production traffic reaches `FilterChainProxy`.

To distinguish a firewall 400 from a controller 404 due to a missing route, send a valid `/api/hello` request as a control; record the status, response body, and handler logger trace while avoiding logging URIs containing sensitive data.

## 10. Interactions With CORS, SecurityFilterChain, and Reverse Proxies

### CORS/Preflight

A valid `OPTIONS` request for CORS is normally inside `StrictHttpFirewall`'s allowed HTTP methods list. Yet a preflight with an abnormal path/method/header can still be rejected by the firewall **before `CorsFilter` processes CORS**. If the frontend reports a CORS failure when the server returns 400, check whether the request violated the firewall; adding `Access-Control-Allow-Origin` alone cannot fix it.

### Multiple `SecurityFilterChain`s

The firewall applies at the `FilterChainProxy` layer surrounding all chains; a `RequestRejectedHandler` configured on the proxy handles rejections occurring before chain selection. Therefore, adding `requestMatchers("/api/**").permitAll()` in a specific chain does not make a firewall-disallowed path valid.

If an application intentionally registers multiple proxy/filter chains across distinct entrypoints, determine which proxy a real request actually enters rather than guessing from a bean name alone.

### Reverse Proxies and Containers

An external request typically passes through:

~~~text
Client URL
  -> CDN/WAF (may filter)
  -> Reverse proxy / ingress (may decode/normalize path)
  -> Servlet container (may block URI/method/header)
  -> FilterChainProxy / HttpFirewall
  -> SecurityFilterChain
  -> Spring MVC
~~~

Which layer reports an error depends on the request and deployment. A 400 returned by nginx or Tomcat does not automatically invoke `RequestRejectedHandler`. Compare the request-target at the proxy with application logs, while protecting logs against log injection and secret exposure.

### Security and Operational Observability

- Returning 400 for invalid requests is usually a sensible default; choose another code only if an explicit API/infrastructure contract requires it.
- Never expose filter names, internal rules, Java stack traces, or detailed exception messages to clients.
- Emit rejection metrics grouped by authenticated/sanitized source, route group, or fixed error category; never use full URLs as metric tags.
- If rejections spike suddenly, investigate the origin, recent client rollouts, proxy path rewriting, and potential probing; never loosen policy automatically just to cut log volume.

## 11. Common Errors and Troubleshooting Table

| Symptom | Possibilities to Consider | How to Verify and Resolve |
| --- | --- | --- |
| API returns 400 even with `permitAll` | Firewall rejects before authorization. | Check `RequestRejectedException`/handler logs and path/method. |
| URI containing `;` worked before but returns 400 after upgrade | Strict firewall blocks semicolons or path parsing changed. | Fix URL or evaluate compatibility with strict tests. |
| URL with encoded slash `%2F` returns 400 | Firewall/container/proxy disallows this encoding. | Identify exact rejection layer; avoid requiring encoded slashes when possible. |
| Custom `@ControllerAdvice` does not catch it | Exception occurs in `FilterChainProxy`, before MVC. | Use `RequestRejectedHandler` in web security. |
| Logged-in user still gets 400 | Authentication does not determine whether a request is syntactically valid. | Fix encoding/headers/method; do not add roles. |
| Expected JSON yet received HTML status 400 | Container renders error page via `sendError` or default handler. | Use custom handler with fixed body; inspect gateway. |
| No custom handler log yet still 400 | Request blocked by container/proxy before Spring. | Inspect access/error logs of layers in front of the app. |
| Preflight OPTIONS returns 400 | Method/path/header may be rejected by firewall/container. | Inspect real OPTIONS request; distinguish from 403 CORS policy rejections. |
| One URL resolves to another endpoint after decoding | Path normalization differs between proxy and MVC. | Prefer canonical URLs and keep firewall strict; test authorization. |
| Logs contain line breaks / strange characters | Client-controlled raw URL or exception message was logged. | Sanitize, log fixed messages, and avoid sensitive data. |

### Short Investigation Sequence

1. Confirm whether the 400 status/body originated in the container/proxy or inside the application.
2. Check whether `RequestRejectedException` occurred and whether the custom handler ran.
3. Compare raw URL, post-proxy path, HTTP method, and headers/parameters for abnormal characters without leaking secrets.
4. Inspect `StrictHttpFirewall` configuration, `WebSecurityCustomizer` beans, and how `RequestRejectedHandler` is wired to `FilterChainProxy`.
5. Send a valid request to the same endpoint to rule out controller/authorization issues.
6. Change firewall policy only after tests prove routing and authorization cannot be bypassed.

## 12. Mistakes to Avoid

**"Every 400 is a RequestRejectedException."** False. Spring MVC, containers, proxies, and gateways can all emit 400 for different reasons.

**"RequestRejectedException is AccessDeniedException."** False. Rejection concerns HTTP request validity; access denied concerns authorization decisions after other security checks.

**"Just add `permitAll`."** False. The firewall runs before authorization; a request failing structural checks cannot be "authorized" by a downstream rule.

**"Disable StrictHttpFirewall for a quick fix."** Doing so can reintroduce ambiguous requests into path matching. Fix the URL/client and environment first, relaxing individual rules only with evidence.

**"Custom handlers should return the raw exception message for easier debugging."** Bad idea. Request URIs, encoded data, and client-controlled input can appear in the message. Error responses should remain stable and never leak sensitive details.

**"`@ControllerAdvice` catches everything."** False for exceptions outside `DispatcherServlet`/MVC. To customize firewall responses, handle them at `FilterChainProxy` via `RequestRejectedHandler`.

**"Passing handler unit tests means production returns the exact same response."** Handler tests prove only the handler's logic. Verify wiring, Servlet container, error pages, reverse proxy, and the real security chain.

## 13. Self-Check Questions

1. **In which step is `RequestRejectedException` typically created?** When `HttpFirewall` finds a request violates policy while `FilterChainProxy` prepares to process the request.
2. **What converts the exception into HTTP 400?** The configured `RequestRejectedHandler`; `HttpStatusRequestRejectedHandler` is a simple status-only option.
3. **Does `@ControllerAdvice` always see this exception?** No; rejection usually happens before the request enters Spring MVC.
4. **Why shouldn't a 400 request be "fixed" with `permitAll`?** Authorization does not change the firewall's request-acceptance rules.
5. **Should `exception.getMessage()` be returned to the client?** Not by default; the message may contain client input or internal details.
6. **When production returns 400 while local does not, what must be compared?** Actual URL/method/headers, Spring Security version, firewall config, Servlet container, and proxy/CDN normalization.
7. **Why avoid allowing all HTTP methods?** It increases the inputs that proxies, firewalls, route matching, and the application must handle consistently, potentially widening the attack surface.
8. **Which test verifies handler behavior independently of the filter chain?** Call `handler.handle(mockRequest, mockResponse, new RequestRejectedException(…))` directly, then assert status/body and absence of leaked messages.

**Key takeaway:** `RequestRejectedException` signals that *a request failed `HttpFirewall` policy*; `RequestRejectedHandler` is the HTTP response hook when `FilterChainProxy` catches that signal. Keep the firewall strict, diagnose the exact rejecting layer, return a safe 400 response, and relax policy only after proving necessity with tests.