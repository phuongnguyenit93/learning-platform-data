# HttpFirewall in FilterChainProxy and the Role of Request Normalization (Spring Security Servlet)

## 1. Context: Why Validate Paths Before Authorization?

Web applications often enforce authorization by URL—for example, `/public/**` is publicly accessible while `/admin/**` is restricted to administrators. This mechanism is trustworthy only when the **reverse proxy, servlet container, Spring Security, and Spring MVC agree on the same path**. In practice, the URL string sent by a client can contain percent-encoded characters, dots, repeated slashes, semicolons, backslashes, or variants that each layer interprets differently.

Imagine a path containing unusual components such as:

~~~text
/admin/../public/ping
/public//ping
/public;v=1/ping
/admin%2Freport
~~~

The four examples above are not automatically equivalent to a normal URL. A proxy may rewrite the path before forwarding; the container may decode or strip path parameters; Spring MVC has its own routing rules; a security request matcher may rely on `servletPath` and `pathInfo`. If the step that **selects the security filter chain** or **checks authorization** sees a different path from the step that **actually handles the request**, a URL can be misclassified.

**HttpFirewall** is the mechanism Spring Security places before security filter chain selection. It inspects HTTP Servlet requests, rejects unacceptable request forms, and provides contract-compliant request wrappers so matching behaves more consistently.

In Spring Security 6.x Servlet, the default implementation is **StrictHttpFirewall**. The most important point: `StrictHttpFirewall` typically **rejects** unusual paths; it is not a tool meant to silently "clean up and let through" arbitrary URLs. Whether a URL is blocked by a proxy or container before reaching Spring Security still depends on the infrastructure.

After this lesson, you will be able to:

- Locate `HttpFirewall` in `DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain`.
- Distinguish **validation/rejection**, **normalization for matching**, **MVC routing**, and **authorization**.
- Understand the risks of path traversal, semicolons, encoded slashes, non-canonical paths, and HTTP methods.
- Configure `StrictHttpFirewall` intentionally, avoiding relaxing policies merely to make HTTP 400 go away.
- Test the firewall in isolation and test the real request path through the container, proxy, and security filter chains.

Scope of this lesson: **Spring Security for the Servlet stack** (Spring MVC, Spring Boot 3.x, Spring Security 6.x, Java 17+). WebFlux has a different request-processing architecture; do not directly apply the beans/filters in this lesson to the Reactive stack.

## 2. Where Does HttpFirewall Sit in the Request Path?

Overview diagram:

~~~text
Client
  |
  v
Reverse proxy / API gateway (if any)
  |
  v
Servlet container (Tomcat, Jetty, ...)
  |
  v
DelegatingFilterProxy: "springSecurityFilterChain"
  |
  v
FilterChainProxy
  |
  +--> HttpFirewall
  |       |
  |       +--> Inspect request (method, URL/path, ...)
  |       +--> If violated: RequestRejectedException
  |       +--> If valid: FirewalledRequest/response wrapper
  |
  +--> Select matching SecurityFilterChain (by matcher)
  |       |
  |       +--> Security filters in the chain
  |               +--> Authentication / CSRF / Authorization / ...
  |
  v
Remaining Servlet filter chain
  |
  v
DispatcherServlet -> HandlerMapping -> Controller
~~~

**DelegatingFilterProxy** is the bridge from the servlet filter registration to the Spring Security bean named `springSecurityFilterChain`. This bean is usually **FilterChainProxy**, which manages a list of **SecurityFilterChain** instances. Each `SecurityFilterChain` has its own request matcher and set of security filters.

Inside `FilterChainProxy`, `HttpFirewall` processes the request **before `FilterChainProxy` decides which chain matches**. Thus, an invalid URL can be rejected immediately rather than leaving each `AuthenticationFilter` or `AuthorizationFilter` to decode paths on its own.

The core contract of the `HttpFirewall` interface consists of two operations:

~~~java
FirewalledRequest getFirewalledRequest(HttpServletRequest request);
HttpServletResponse getFirewalledResponse(HttpServletResponse response);
~~~

The snippet above is an **illustrative interface signature**, not a standalone runnable Java program. `FirewalledRequest` extends `HttpServletRequestWrapper` and provides a `reset()` operation used within the `FilterChainProxy` lifecycle. These wrappers help control how the request/response is handled while executing the filter chain. Specifically, a firewall implementation can validate values immediately upon wrapping or when getters are called.

**The actual order matters greatly:** the firewall runs before `SecurityFilterChain` selection and before authentication/authorization logic inside the chain. A `RequestRejectedException` caused by a disallowed URL should not be diagnosed as "wrong password," "missing role," or "CSRF blocked."

## 3. Understanding the Role of "Normalization" Accurately

In Spring Security documentation, `HttpFirewall` is often described as the layer ensuring URLs are handled consistently for safe request matching. However, the word **normalization** does not mean every implementation turns a dangerous URL into a prettier path.

Three concepts must be separated:

1. **Validation / rejection:** identifying unusual or disallowed requests and rejecting them. `StrictHttpFirewall` prioritizes this approach for dangerous path variants.
2. **Consistent matching view:** exposing the request through a firewall wrapper, ensuring `SecurityFilterChain` selection and security filter execution rely on the request view permitted by the firewall. Different implementations may handle path parameters differently.
3. **Application routing:** after the security filters, `DispatcherServlet` and `HandlerMapping` locate the controller. `HttpFirewall` neither replaces Spring MVC routing nor decides which principal is authorized to call an endpoint.

Example illustrating the difference:

~~~text
Original request: /admin/../public/ping

View A (before processing): /admin/../public/ping
View B (after normalization): /public/ping

If an authorization layer uses A and the handling layer uses B,
security rules risk misjudging the actual target.
~~~

With `StrictHttpFirewall`, paths not considered normalized are typically **rejected** instead of normalized and forwarded. This narrows the gap between interpretations and avoids authorization decisions based on ambiguous strings.

**Do not infer** that once a request passes the firewall, every URL string or query string is safe to use directly in SQL, shell commands, file paths, HTML, or templates. The firewall does not replace input validation and output encoding.

## 4. StrictHttpFirewall: Spring Security Servlet's Strict Default

**StrictHttpFirewall** inspects many request characteristics and rejects several abnormal patterns by default. Common categories to know include:

| Category | Example | Why Caution Is Needed |
| --- | --- | --- |
| Unnormalized paths | /a/../b, /a//b, /a/./b | May be normalized differently across layers. |
| Semicolons in paths | /products;v=1/42 | Matrix variables/path parameters may be handled differently by containers or matchers. |
| Encoded path separators | /admin%2Freport, /a%5Cb | Single or multiple decoding passes can alter path segments. |
| Suspicious encoded and control characters | Certain percent-encoding forms, NUL, CR/LF, control characters | Can create path ambiguity or break request-parsing boundaries. |
| HTTP methods not in the allowlist | TRACE, CONNECT, custom methods | Reduces methods outside the application's expected operation set. |
| Header or parameter values violating character rules | E.g., control characters in header names | Reduces malformed request data propagating downstream. |

The table above presents **validation categories**, not an exhaustive byte-level list for every version. Exact rules depend on the Spring Security version as well as the container/proxy. The same raw HTTP request may be blocked by a reverse proxy or servlet container before `HttpFirewall` ever observes it.

The HTTP methods accepted by `StrictHttpFirewall` by default typically include **GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS**. Other methods may be rejected at the firewall. This differs from authorization: a method accepted by the firewall **can still** be rejected with 405 by a controller, 401/403 by security filters, or restricted by API rules.

A normal request, such as `GET /public/ping`, does not automatically become "permitted" simply because the firewall accepts it. It must still match a `SecurityFilterChain` and satisfy authentication, authorization, and other checks.

### Why Are Semicolons Blocked by Default?

Some frameworks or servlet containers treat **;** in a URL as a path parameter. For example:

~~~text
/orders;region=eu/42
~~~

If one layer sees `/orders/42` while another evaluates the full string `/orders;region=eu/42`, path rules and routing data can diverge. Spring MVC provides matrix variables for certain legitimate needs, but enabling them system-wide must come with an explicit policy.

`StrictHttpFirewall` **disallows semicolons by default**. If an application genuinely needs matrix variables, you can configure `setAllowSemicolon(true)` only after thoroughly evaluating the proxy, container, matchers, authorization, and all relevant URLs. This relaxation expands the accepted request surface; it is not "fixing a Spring Security bug."

### Why Do Encoded Slashes Matter?

The sequence **%2F** represents a **/** character if percent-decoded. Depending on the infrastructure:

- A proxy may preserve `%2F` as-is.
- A container may reject, decode, or forward it according to its settings.
- A downstream framework may interpret path segment separators differently from an upstream one.

If an endpoint expects `/resource/{id}` and `id` contains `/`, the route design can create ambiguity. It is usually better to choose URL-safe IDs for path segments or pass complex data via another clearly validated location. Do not enable `setAllowUrlEncodedSlash(true)` just to unblock one specific URL without checking the entire processing pipeline.

## 5. HttpFirewall and Matchers: A Potentially Dangerous Mismatch

An application may contain scoped chains, for example:

~~~text
Chain 1: /api/admin/**  -> requires authentication + role ADMIN
Chain 2: /api/**        -> requires authentication
Chain 3: /**            -> default rule
~~~

`FilterChainProxy` selects the **first `SecurityFilterChain`** whose matcher matches. For normal requests, this is straightforward. However, if a path contains repeated slashes, path parameters, or encoded separators and different layers interpret them differently, it becomes hard to guarantee the request actually enters the intended chain.

`HttpFirewall` helps **immediately reject disallowed URL forms before chain selection**. It does not fix chain design by itself:

- If a chain is overly broad or permits too much public access, the firewall does not replace authorization.
- If a default chain is missing or ordered incorrectly, requests may receive an unintended set of filters.
- If an endpoint is mapped in MVC differently from the security matcher due to context path, servlet path, or version matchers, the matching rules still need fixing.
- If a reverse proxy rewrites the path before reaching the application, the firewall inspects only the request the application receives; it cannot know the exact original URL if the proxy already altered or rejected it.

**Best practice:** verify request matchers and controller mappings alongside actual container behavior; maintain explicit fallback rules such as `anyRequest().authenticated()` or `denyAll()` depending on policy, rather than hoping the firewall will catch every authorization bug.

### Does FilterChainProxy Restore Request Information?

The purpose of the firewall wrapper is to support matching and the filter flow within Spring Security's boundary. In some implementations, path parts processed for matching need to be **reset** when handing the request off to the underlying servlet chain; `FilterChainProxy` provides a mechanism using `FirewalledRequest.reset()` for that lifecycle.

Do not design an application assuming the firewall will permanently rewrite `getRequestURI()`, `getServletPath()`, or `getPathInfo()` into a specific format. Guaranteed behavior depends on the firewall implementation. With `StrictHttpFirewall`, the core idea is to **reject disallowed path variants** and control the request wrapper, not to guarantee URL rewriting into a canonical form across every layer.

## 6. Configuring Spring Security 6.x with StrictHttpFirewall

In Spring Boot 3.x using `spring-boot-starter-web` and `spring-boot-starter-security`, Spring Security normally uses `StrictHttpFirewall` by default. The example below declares it explicitly so you can see where the policy attaches to **WebSecurity / FilterChainProxy**.

File `src/main/java/demo/firewall/FirewallDemoApplication.java`:

~~~java
package demo.firewall;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FirewallDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FirewallDemoApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

File `src/main/java/demo/firewall/SecurityConfig.java`:

~~~java
package demo.firewall;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    HttpFirewall httpFirewall() {
        return new StrictHttpFirewall();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(HttpFirewall firewall) {
        return web -> web.httpFirewall(firewall);
    }
}
~~~

Key points of this configuration:

1. **SecurityFilterChain** defines authentication and authorization for valid requests. `GET /public/ping` is accessible without logging in; other URLs require an authenticated user.
2. **HttpFirewall** is a standalone bean; here the `StrictHttpFirewall` implementation keeps its default policy.
3. **WebSecurityCustomizer** attaches the firewall to `WebSecurity` so `FilterChainProxy` uses it before selecting a chain. This is the right place to tune firewall policy.
4. There is no reason to create a **GenericFilterBean** or use `http.addFilterBefore(...)` to add `HttpFirewall` as an ordinary security filter: the firewall is part of `FilterChainProxy`, not inside the filter list of an individual `SecurityFilterChain`.
5. Defining an `HttpFirewall` bean does not disable security headers, CSRF, session management, or other protections. Spring Security features remain governed by `HttpSecurity` and each chain.

The example uses **Java 17+** and Spring Boot 3.x. To run it in practice, create a Spring Boot project with Spring Web and Spring Security, and place both files in package `demo.firewall`. Command to run the application (when using the Gradle Boot plugin and a repository with the Gradle wrapper):

~~~bash
./gradlew bootRun
~~~

Once the server starts on the default port 8080, test the normal endpoint:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

When the application contains only the controller and configuration above, a valid response returns HTTP 200 with body **pong**. Do not use the status code of an unusual URL alone to immediately conclude which layer rejected the request: a proxy or servlet container may block it before the firewall.

## 7. When You Must Allow Semicolons or Special Methods

This commonly arises when an application uses Spring MVC matrix variables or legacy client protocols.

### 7.1. Conditionally Accepting Semicolons

Example policy replacing the body of the `httpFirewall()` bean:

~~~java
@Bean
HttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowSemicolon(true);
    return firewall;
}
~~~

The snippet above **changes only the semicolon policy**. The remaining checks of `StrictHttpFirewall` stay active at their defaults. Even so, allowing semicolons can cause the URL evaluated by security matchers and the URL mapped by MVC to differ, especially when the container strips or retains path parameters per its own configuration.

Before enabling it, verify:

- Are matrix variables genuinely required on specific endpoints, or can they be replaced with query parameters or a request body?
- How do the proxy, servlet container, Spring MVC, and Spring Security matchers interpret paths containing semicolons?
- Are all URLs carrying authorization semantics tested both with and without path parameters?
- Do separate chains for `/admin/**`, `/api/**`, and public paths continue to enforce permissions accurately?

Do not turn on all `setAllow...` flags or replace `StrictHttpFirewall` with another firewall merely to "avoid 400s" before understanding the specific URL variant being rejected.

### 7.2. Configuring the HTTP Method Allowlist (Only With Clear Justification)

If the application's protocol genuinely requires a different set of HTTP methods, `StrictHttpFirewall` provides `setAllowedHttpMethods(...)`. This example illustrates how to **restrict** methods, not a recommendation for every project:

~~~java
@Bean
HttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowedHttpMethods(
        java.util.List.of("GET", "HEAD", "POST", "OPTIONS")
    );
    return firewall;
}
~~~

This snippet is an **alternative** to the `httpFirewall()` bean in the earlier example—do not declare duplicate beans of the same type. With this policy, `PUT`, `PATCH`, and `DELETE` are rejected by the firewall even if a controller defines mappings for them. Be sure to test CORS preflight (`OPTIONS`), `HEAD`, API methods, and real clients before tightening the list.

**A firewall method allowlist differs from endpoint access rights.** Allowing `DELETE` at the firewall does not mean every user may delete data; authorization, CSRF, and business validation still apply. Conversely, a method rejected by the firewall never reaches the controller regardless of valid roles.

### 7.3. Should You Use DefaultHttpFirewall?

Spring Security also provides **DefaultHttpFirewall** with a different policy, often viewed as less strict on certain URL compatibility aspects. Do not treat switching to `DefaultHttpFirewall` as a default fix for routing or URL-encoding errors: first identify the true business requirement, infrastructure rules, matchers, and necessary exceptions.

If relaxation is needed, prefer adjusting **one controlled behavior** of `StrictHttpFirewall`, writing tests, and auditing the risk. Adjusting the firewall affects request interpretation across **every `SecurityFilterChain`** attached to `FilterChainProxy`, not just a single controller.

## 8. RequestRejectedException and Error-Code Diagnosis

When the firewall detects a violating request, it throws **RequestRejectedException**. This exception occurs early, before ordinary security filters execute. An application can configure `RequestRejectedHandler` to decide how to respond; many modern Spring Security configurations translate this case into **HTTP 400 Bad Request**, though exact handling and logging should be verified against your actual version and configuration.

Distinguish these symptoms:

| Symptom | Possible Cause | Layer to Inspect |
| --- | --- | --- |
| 400 for paths containing `;` or `%2F` | Firewall or container/proxy rejected the URL | Proxy/container access logs, Spring Security firewall logging |
| 400 for a normal URL | MVC input/parser/validation, another firewall rule, or proxy | Inspect response, exception, and logs to pinpoint source |
| 401 or redirect to login page | Missing authentication in the selected chain | `AuthenticationEntryPoint`, session, HTTP Basic |
| 403 | Authorization, CSRF, or another policy denied access | `AuthorizationFilter`, `CsrfFilter`, access denied handler |
| 404 | No matching mapping or request did not reach expected route | `DispatcherServlet`/`HandlerMapping`, proxy rewrites |
| 405 | Route exists but does not accept the HTTP method | Spring MVC method mapping |

**Not every 400 comes from `StrictHttpFirewall`.** For encoded slashes, the container may reject the request before `FilterChainProxy` runs. For an invalid request body, the controller layer can also return 400. You must determine whether the request reached Spring Security.

**`RequestRejectedException` is not `AccessDeniedException`.** Do not expect MVC `@ControllerAdvice` or `AccessDeniedHandler` to handle every request rejected by the firewall, because the point of failure may fall outside the ordinary handler/authorization flow.

In operations, record the rejection reason, method, request ID, and relevant route at an appropriate log level; avoid logging raw tokens, session cookies, sensitive information, or full malicious request payloads. If a legitimate client is blocked, prioritize fixing the client path, encoding, and proxy before relaxing the firewall.

## 9. Unit Testing StrictHttpFirewall with Spring Mock Servlet

Testing the firewall directly isolates URL filtering policy from container or Spring MVC behavior. This requires `spring-security-web`, `spring-test`, and JUnit 5 (typically provided by `spring-boot-starter-security` and `spring-boot-starter-test`).

File `src/test/java/demo/firewall/StrictHttpFirewallTest.java`:

~~~java
package demo.firewall;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StrictHttpFirewallTest {

    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    private static MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest req =
            new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        return req;
    }

    @Test
    void normalGetIsAccepted() {
        assertDoesNotThrow(() ->
            firewall.getFirewalledRequest(
                request("GET", "/public/ping")));
    }

    @Test
    void semicolonIsRejectedByDefault() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "/public;v=1/ping")));
    }

    @Test
    void encodedSlashIsRejectedByDefault() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "/admin%2Freport")));
    }

    @Test
    void unsupportedMethodIsRejected() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("TRACE", "/public/ping")));
    }

    @Test
    void semicolonCanBeAllowedExplicitly() {
        StrictHttpFirewall custom = new StrictHttpFirewall();
        custom.setAllowSemicolon(true);

        assertDoesNotThrow(() ->
            custom.getFirewalledRequest(
                request("GET", "/public;v=1/ping")));
    }
}
~~~

The test methods invoke `getFirewalledRequest()` directly with **MockHttpServletRequest**, verifying `StrictHttpFirewall` policy against the supplied paths. The first test confirms a normal URL is accepted by the firewall; the next tests confirm semicolons, encoded slashes, and `TRACE` are rejected by default; the last test confirms the exception for semicolons when configured explicitly.

**Limitation of this test:** `MockHttpServletRequest` does not simulate every URL decoding, canonicalization, and normalization behavior of Tomcat, Jetty, ingress, or an API gateway. A path with `%2F` may be rejected by the container before the firewall in a real HTTP request; passing unit tests do not guarantee the final HTTP status in production.

Run the tests with the project's Gradle wrapper if the project is configured for JUnit Platform tests:

~~~bash
./gradlew test
~~~

No assumed stdout needs to be printed here: Gradle output depends on dependencies, plugins, and other tests in the project. When tests run successfully, the five tests above pass; if they fail, inspect the assertions and actual Spring Security version rather than altering the firewall just to turn the tests "green."

## 10. End-to-End Integration Testing: Proxy, Container, Filter, and Controller

After unit tests, real HTTP checks are needed from outside the ingress path used in production. Some requests can be rejected at multiple layers; record **which layer returns the response** and what path the application actually receives.

Example `curl` commands for probing on localhost:

~~~bash
curl -i 'http://localhost:8080/public/ping'
curl -i --path-as-is 'http://localhost:8080/public;v=1/ping'
curl -i --path-as-is 'http://localhost:8080/public//ping'
curl -i --path-as-is 'http://localhost:8080/admin%2Freport'
~~~

The **--path-as-is** flag prevents `curl` itself from collapsing certain dots/segments before sending, though a reverse proxy or servlet container may still transform the request afterward. Do not assume 400 is the guaranteed status for every example: the container, proxy, or application may reject early with another code or never forward the request to Spring Security.

Verify in sequence:

1. Valid URLs reach the right route and return the expected status and response body.
2. Known abnormal URLs are blocked **before the controller** with no side effects or wrong-route access.
3. Access logs and Spring Security logs show the exact rejecting layer.
4. Rules for `/public/**` and `/admin/**` cannot be shifted from protected to public via path parameters, repeated slashes, or encoded delimiters.
5. Every servlet container, ingress, and CDN in the target environment is tested at an appropriate level.
6. Configurations that allow semicolons or special methods must include tests for both valid URLs and URLs exploited to hit the wrong security matcher.

If you need to observe Spring Security in development:

~~~properties
logging.level.org.springframework.security.web.firewall=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Exact logger names and detail levels depend on the version. Enable verbose logging only when diagnosing an issue; control log volume and sensitive request data. An HTTP 400 returned by a proxy will not necessarily emit any Spring Security logs.

### Testing Each Security Chain Separately

For multi-chain applications, write representative cases for every URL group and method. For example:

| Request | Business Expectation | What to Verify |
| --- | --- | --- |
| GET /public/ping | Public endpoint | Firewall accepts; matcher permits; controller returns `pong` |
| GET /admin/report | Authorized users only | Firewall accepts; hits protected chain/authorization |
| GET /public;v=1/ping | Rejected by default `StrictHttpFirewall` | No controller side effects |
| GET /admin%2Freport | Rejected by default if it reaches firewall in that form | Not routed into a public route |
| TRACE /public/ping | Rejected by default | Does not slip into GET/HEAD route via method confusion |

These rows state **test expectations**, not a single guaranteed status code across all environments. Use responses, logs, and tracing to identify the rejecting layer.

## 11. Common Design Misconceptions

### 11.1. Thinking HttpFirewall Is AuthorizationFilter

`HttpFirewall` determines **whether a request may proceed as a valid HTTP request**; `AuthorizationFilter` determines **whether a principal has permission to access a resource**. Both are important, but they solve different problems.

Allowing a URL at `HttpFirewall` does not mean granting access to the endpoint. Conversely, strict authorization does not guarantee safety if security chain selection and the router see different paths.

### 11.2. Thinking HttpFirewall Works Like a Web Application Firewall

The name "firewall" can be misleading. `HttpFirewall` in Spring Security does not provide rule sets to detect SQL injection, XSS, bots, DDoS, malware payloads, API abuse, or the full OWASP Top 10 like a dedicated WAF. It primarily governs **HTTP request validity and interpretation at the `FilterChainProxy` boundary**.

The application must still validate input, encode output, enforce authorization, protect against CSRF per its session model, enforce resource limits, and keep dependencies updated.

### 11.3. Rushing to Enable setAllowUrlEncodedSlash(true)

When seeing 400 on a URL containing `%2F`, the right fix is usually to revisit the identifier and request-path design. If an ID contains slashes, use a URL-safe representation or pass it in another field. Relaxing a firewall setting can create discrepancies between the proxy, container, and matchers, especially if each layer decodes differently.

### 11.4. Failing to Distinguish What the Server Receives From What the Client Sends

The path sent by a browser can differ from `requestURI`, `servletPath`, and `pathInfo` inside the application after passing through proxies and containers. Log/trace both the raw path at ingress and the path at the backend in a controlled manner during debugging, then check the source of truth at each step. Do not assume the firewall sees the raw bytes of the original HTTP request.

### 11.5. Ordering Chains Incorrectly

In `FilterChainProxy`, the first chain with a matching matcher wins. The firewall blocks certain abnormal URLs but does not fix chain ordering. Place specific chains before general chains, provide an appropriate fallback, and test real endpoints.

### 11.6. Ignoring Methods or Unusual Case Variations

A method like `TRACE` can be blocked at the firewall before the controller. An HTTP method allowlist is not a security policy for business operations; test API methods and CORS preflight separately. Do not add a global custom method just because one test client uses a non-standard protocol.

### 11.7. Enabling Relaxed Settings Across Multiple Apps Without Scope Assessment

The firewall is attached at the `FilterChainProxy` level and can apply before every `SecurityFilterChain` in the application. Allowing semicolons to serve one route can affect all routes. You must review security across the entire app and all endpoints sharing the host/servlet context.

### 11.8. Testing Only With MockMvc and Skipping Real Requests

`MockMvc` does not fully reproduce URL transformations performed by proxies, containers, or gateways. A configuration may pass `MockMvc` yet fail in production due to different slash encoding or semicolon handling. Integration testing on the deployment infrastructure is an essential step.

## 12. Troubleshooting Workflow for Suspected HttpFirewall 400 Errors

When a client reports that a valid endpoint suddenly returns 400, proceed step by step:

1. **Capture minimal request details**: method, hostname, raw path, and status, avoiding copying cookies/tokens into tickets.
2. **Confirm the request reached the backend**: inspect reverse proxy/container access logs first; if rejected at ingress, fix ingress instead of guessing Spring Security errors.
3. **If the request reached `FilterChainProxy`**, inspect `RequestRejectedException` and the reason message corresponding to your running version.
4. **Compare the URL against the canonical endpoint**: look for semicolons, repeated slashes, dot segments, encoded slashes/backslashes, encoded percents, and non-default methods.
5. **Review URL design**: did the client encode incorrectly? Can the ID use URL-safe characters or move to a query parameter/body?
6. **Verify matchers**: after fixing the URL, does the request enter the expected `SecurityFilterChain` and authorization rule?
7. **Only if a genuine exception is needed**, configure exactly one `StrictHttpFirewall` flag, then add regression tests for both valid requests and potential bypass variants.
8. **Retest end-to-end**, including proxy/container and application; inspect response side effects, not just HTTP status.

Do not add a rule at the reverse proxy such as "turn any 400 into 200/redirect" to silence errors: that can mask firewall-blocked requests and make the security path harder to observe.

## 13. Summary of Technical Choices

| Decision | Recommendation | Verification Condition |
| --- | --- | --- |
| Default firewall | Keep `StrictHttpFirewall` when no special requirement exists | Test valid routes, methods, auth, and ingress |
| URL containing slashes/encoded slashes in ID | Prefer URL-safe ID design or change transport location | No path-matching divergence across layers |
| App needs matrix variables | Consider `setAllowSemicolon(true)` intentionally | Audit proxy, container, MVC, and all security chains |
| Multiple `SecurityFilterChain`s | Order specific chains before general chains | Test chain selection and authorization outcomes |
| Unusual 400 responses | Identify the rejecting layer before fixing | Logs, request mapping, firewall exception, container |
| Firewall testing | Direct unit tests + real HTTP integration tests | Mock requests differ from raw HTTP requests via proxy |

## 14. Self-Assessment Knowledge Checklist

- [ ] Can explain why unusual URLs can cause discrepancies between security matchers and MVC/controller routing.
- [ ] Can trace the order `DelegatingFilterProxy → FilterChainProxy → HttpFirewall → SecurityFilterChain selection → security filters`.
- [ ] Distinguishes `StrictHttpFirewall` **rejecting** invalid URLs from **rewriting** every URL into canonical form.
- [ ] Knows default `StrictHttpFirewall` blocks semicolons, certain encoded slashes/abnormal paths, and disallowed methods.
- [ ] Knows how to attach `HttpFirewall` via `WebSecurityCustomizer` without disguising it as an `HttpSecurity` filter.
- [ ] Distinguishes `RequestRejectedException` from authentication/authorization/CSRF errors and reverse proxy/container errors.
- [ ] Can write direct tests on `MockHttpServletRequest` and real HTTP tests along the ingress path.
- [ ] Relaxes the firewall only after proving a business need, assessing scope, and adding regression tests.
- [ ] Maintains separate authorization and validation: the firewall does not replace a WAF, security matchers, or input validation.

**Technical conclusion:** `HttpFirewall` is the checkpoint located **inside `FilterChainProxy` but before `SecurityFilterChain` selection**. It keeps matching from depending on ambiguous URL variants; with `StrictHttpFirewall`, most unusual cases are **rejected** rather than "automatically fixed and let through." Understanding this exact position and boundary helps both preserve accurate access control and resolve 400 responses caused by invalid URLs with solid evidence.
