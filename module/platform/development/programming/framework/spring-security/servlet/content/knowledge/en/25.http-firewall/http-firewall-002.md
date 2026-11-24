# StrictHttpFirewall vs. DefaultHttpFirewall in Spring Security Servlet

## 1. Why Does HttpFirewall Matter?

In a Java Servlet application, a URL can be interpreted by multiple layers: reverse proxy, servlet container, Spring Security, and Spring MVC. These layers do not always handle semicolons, paths with redundant slashes, URL-encoded characters, or `..` segments in the same way. If a security matcher evaluates one interpretation of a path while a controller processes another, resource-protection rules can be applied incorrectly.

Spring Security's **`HttpFirewall`** sits at the beginning of `FilterChainProxy` processing to inspect, restrict, and provide a request representation suitable for matching `SecurityFilterChain` instances. The two implementations to distinguish are:

- **`StrictHttpFirewall`:** used by default by Spring Security Servlet in modern configurations; actively rejects many abnormal or dangerous request forms.
- **`DefaultHttpFirewall`:** an older, less strict implementation; still performs unnormalized-path checks, but does not provide the same comprehensive restrictions as `StrictHttpFirewall`.

The goal of this lesson is to understand **their differences, impact on URLs/methods, `RequestRejectedException`, configuration, and testing**. You should never switch to a looser firewall merely because a client receives an error.

## 2. Where Does HttpFirewall Run in the Servlet Filter Chain?

`FilterChainProxy` is Spring Security's filter invoked as a servlet filter (typically via `DelegatingFilterProxy`). Overview flow:

```text
HTTP request
   |
   v
Servlet container / upstream filters
   |
   v
springSecurityFilterChain (FilterChainProxy)
   |
   +--> HttpFirewall.getFirewalledRequest(request)
   |       |
   |       +--> reject -> RequestRejectedException
   |       |                   -> RequestRejectedHandler / error handling
   |       |
   |       +--> accept -> FirewalledRequest
   |                             |
   |                             v
   |                  match SecurityFilterChain
   |                             |
   |                             v
   |               authentication / CSRF / authorization...
   |                             |
   |                             v
   +----------------> DispatcherServlet -> controller
```

When a request is valid, `HttpFirewall#getFirewalledRequest` returns a `FirewalledRequest` wrapper so Spring Security can perform path matching and processing. The wrapper has a `reset()` method to restore the request view for subsequent parts of the processing chain when needed. This is not a mechanism for bypassing authentication or arbitrarily rewriting business URLs.

When a request is rejected by the firewall, **the controller is normally never called**, and the error is `RequestRejectedException`, **not** `AuthenticationException` or `AccessDeniedException`. Therefore, diagnosis differs:

- Firewall rejection: the request has a shape/method/header disallowed by policy.
- Authentication failure: missing or invalid credentials.
- Authorization failure: the user is authenticated but lacks permissions.
- MVC 404/405: the request passed the firewall but has no matching route/method.

Do not conclude 403 insufficient permissions solely from a `RequestRejectedException` log entry.

## 3. Comparing StrictHttpFirewall and DefaultHttpFirewall

| Criterion | `StrictHttpFirewall` | `DefaultHttpFirewall` |
| --- | --- | --- |
| Role | Recommended default for modern Servlet applications | Legacy implementation, more compatible but less restrictive |
| Protection philosophy | Rejects disallowed URL/method representations with strict rules | Performs path normalization checks, but fewer strict rules |
| Abnormal paths | Rejects many abnormal forms by default such as semicolons, encoded slashes/backslashes, and unnormalized strings | Does not apply the same strict rule set; does not mean accepting all URLs |
| `;` in URL | Rejected by default; configurable option to allow if controlled | Has historical behavior regarding path parameters; verify actual container/version |
| HTTP methods | Has a default allowlist for commonly used methods | Does not enforce the same strict allowlist as Strict |
| Fine-tuning | Has selective setters: semicolon, encoded slash, methods, hostname... | Fewer granular options per request aspect |
| Diagnosis | Can raise `RequestRejectedException` before security chain/controller | Can also reject requests; not a "disable firewall" option |
| Recommendation | **Keep default; relax only one condition with justification and tests** | Consider only for verified compatibility constraints, not as a blanket bug fix |

**There is no exact table of "what Strict blocks, Default definitely lets through" across all environments.** Servlet containers, proxies, applications, and library versions may reject or normalize a request before it reaches the firewall. Conversely, if Default accepts a string, that does not guarantee downstream layers interpret it safely or consistently.

### Why Is Strict the Standard Choice?

A URL such as `/admin/../public`, `/api//users`, `/api/users;role=admin`, or one with unusual encoded characters can be parsed differently by proxies, servlet containers, and security matchers. That creates a **path confusion** risk: the permission-checking component sees one path while the execution component sees another.

`StrictHttpFirewall` aims to eliminate potentially ambiguous representations at the entry of `FilterChainProxy`. Still, this is **defense in depth**, not a substitute for reverse proxy configuration, consistent normalization, authentication, or endpoint authorization.

## 4. Specific Request Cases

### 4.1. Normal URL

```http
GET /api/products/42 HTTP/1.1
Host: app.example.test
```

The path is clear and the `GET` method is in Strict's default allowlist. If other layers permit it, the firewall has no reason to reject this URL. Whether the server ultimately returns 200/401/403/404 is determined by authentication, authorization, and routing.

### 4.2. Semicolons and Matrix/Path Parameters

```http
GET /api/products;version=2/42 HTTP/1.1
Host: app.example.test
```

`StrictHttpFirewall` disallows `;` in URLs by default. This can affect legacy apps using matrix variables, path parameters, or `;jsessionid=...`. Some environments passing session IDs in URLs may have legacy requirements, but **prefer session cookies** and avoid URL-based session tracking because URLs easily leak into logs, history, and referrers.

If an application genuinely has a matrix-variable protocol, you may consider `setAllowSemicolon(true)` on **`StrictHttpFirewall`** after testing matchers, Spring MVC routing, proxies, the servlet container, and path traversal possibilities. Allowing semicolons **does not automatically ensure safety**, and is no reason to switch the entire system to `DefaultHttpFirewall`.

### 4.3. Encoded Slash, Backslash, and Double Slash

Examples of request forms to examine:

```text
/api/items%2F42
/api/items%5C42
/api//items
/api/items/../admin
```

These forms can create divergence between the raw URL and the path seen by downstream layers. Strict generally rejects unsafe/unnormalized representations under its default rule set; in particular, `%2F` (encoded slash) is rejected by default. In applications with multi-layer encoding, allowing encoded slashes can cause proxies and controllers to disagree on segment boundaries.

If an API needs to pass a value containing `/`, prefer **placing that value in a query parameter or request body** per the appropriate protocol, or design segment IDs without slashes. Do not use `setAllowUrlEncodedSlash(true)` as a blanket fix. Even if the firewall allows it, the servlet container or reverse proxy may still reject or decode it earlier.

### 4.4. HTTP Methods

`StrictHttpFirewall` uses an allowed-method list; in Spring Security 6, the default typically includes:

```text
GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS
```

Other methods, such as `TRACE`, are not in the default allowlist. A `TRACE` request may be blocked by the firewall or container before reaching a controller. Use `setAllowedHttpMethods(...)` if you want to narrow the allowlist for production; account for `OPTIONS` for CORS preflight, `HEAD`, health checks, client SDKs, reverse proxies, and the API methods actually used.

Blocking a method at the firewall differs from **method authorization**. For example, allowing `POST` through the firewall does not mean everyone is allowed to create data; `CSRF`, authentication, and authorization still evaluate the request.

### 4.5. Host, Headers, and Parameters

Strict includes additional checks/extension points for the validity of hostnames, header names/values, and request parameters. For systems serving multiple domains or sitting behind a proxy, align hostname policy with `Host`, `Forwarded` / `X-Forwarded-*`, and proxy trust boundaries.

You can use `setAllowedHostnames(...)` to restrict hostnames permitted by the firewall, though that **does not replace** trusted-proxy configuration, TLS virtual hosts, host-header injection defenses, or application redirect rules.

Do not invent complex regexes across all headers/parameters just to be "stricter": many valid requests contain Unicode, punctuation, or encoding. If customization is necessary, test with real data, define the API contract, apply exact rules, and log blocked cases.

## 5. Configuration on Spring Boot 3 / Spring Security 6 (Java 17+)

The examples below are **classes belonging to a Spring Boot Servlet application** with `spring-boot-starter-web` and `spring-boot-starter-security`, alongside a `@SpringBootApplication` class. The code is not a standalone Java program runnable with `javac` without dependencies. A package declaration can be added per your actual project.

### 5.1. Keeping StrictHttpFirewall and Declaring an Allowlist

File `ServletSecurityConfig.java`:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class ServletSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .anyRequest().authenticated());
        return http.build();
    }

    @Bean
    WebSecurityCustomizer firewallCustomizer() {
        return web -> {
            StrictHttpFirewall firewall = new StrictHttpFirewall();

            // Illustrates an application implementing only GET/HEAD/POST.
            // If PUT, PATCH, DELETE, or CORS OPTIONS are used,
            // allow the exact methods the system actually requires.
            firewall.setAllowedHttpMethods(
                List.of("GET", "HEAD", "POST")
            );

            web.httpFirewall(firewall);
        };
    }
}
```

This example **narrows the method allowlist** to illustrate customization: the demo app explicitly uses only `GET`, `HEAD`, and `POST`. For REST APIs using `PUT`, `PATCH`, `DELETE`, or browsers sending `OPTIONS` preflight, this configuration will block legitimate requests. **Do not copy this allowlist into production without inventorying client methods.** If you have no special requirement, you can omit the entire `firewallCustomizer` bean to use the default `StrictHttpFirewall`.

`WebSecurityCustomizer#customize` receives `WebSecurity` and attaches the firewall at the `FilterChainProxy` level. Distinguish this policy from `SecurityFilterChain`: the security filter chain handles authentication/authorization/CSRF, whereas the firewall applies before chain selection. In apps with multiple `SecurityFilterChain`s, do not assume an individual chain makes the firewall less strict on its routes.

### 5.2. Simple Verification Endpoint

File `PingController.java`:

```java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
```

A normal request `GET /public/ping` when running the application with the configuration above passes the firewall, matches the permitted route, and returns JSON:

```json
{"status":"ok"}
```

This is the expected response body; the status is **200 OK** when the endpoint is served normally. If the URL is rejected by the firewall, `ping()` does not run. If the URL passes the firewall but misses a route, MVC may return 404/405; these are two distinct error categories.

### 5.3. When You Genuinely Must Allow Semicolons

A **higher-risk** change illustrating how to configure Strict properly, used only after design review:

```java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true);
// Register this firewall via web.httpFirewall(firewall)
// in the application's WebSecurityCustomizer.
```

This is a **configuration snippet**, not a standalone Java file. It relaxes **only** Strict's semicolon rule, not all abnormal URLs; the remaining rules still require verification. Ideally, design endpoints to avoid semicolons unless there is an established need. An alternative pattern: `GET /api/products/42?version=2` when `version` is an ordinary data parameter.

Do not confuse relaxing a single URL rule with switching to `DefaultHttpFirewall`. The latter changes a much broader set of protective behaviors and can introduce untested discrepancies.

### 5.4. Should You Switch to DefaultHttpFirewall?

Spring Security also provides `org.springframework.security.web.firewall.DefaultHttpFirewall`, which can be attached via `web.httpFirewall(...)`. However, using it to "make errors go away" without proving the root cause is a decision to **reduce input filtering**, not an equivalent patch.

Before considering it, you must determine:
1. Exactly **which rule** rejected the request—at the firewall or earlier at the proxy/container.
2. Whether it is a valid request under the API contract, and whether the client/route can be adjusted to use normalized URLs.
3. Whether equivalent URL/method validation exists at the proxy and application.
4. Whether all security matchers behave consistently with how the servlet container/MVC interprets paths.
5. Whether tests cover semicolon/encoded slash/backslash/traversal cases, auth, and authorization.

For most modern applications, **keeping the default `StrictHttpFirewall`** is the safer and more maintainable decision.

## 6. RequestRejectedException and HTTP Status

When Strict rejects a request, Spring Security throws `RequestRejectedException`. Depending on the Spring Security version, `RequestRejectedHandler` configuration, servlet container, and gateway, the client response can vary; in common Servlet setups, rejected requests typically become **HTTP 400 Bad Request**.

Do not assume this is a 401/403 error:

| Signal | Typical Handling Layer | Investigation Expectation |
| --- | --- | --- |
| `RequestRejectedException` with abnormal URL/method | `HttpFirewall` / `RequestRejectedHandler` | Request failed firewall policy; typically inspect HTTP 400 flow |
| `AuthenticationException` | Authentication filters / `AuthenticationEntryPoint` | Login/authentication failed; 401/redirect depending on API/web |
| `AccessDeniedException` | Authorization / `ExceptionTranslationFilter` | Insufficient permissions; typically 403 |
| No `@GetMapping` match | Spring MVC `DispatcherServlet` | Route 404 or method 405, not automatically firewall |
| Proxy returns 400/404 before application | Reverse proxy/servlet container | Application may never have seen the request; inspect edge logs |

`@ControllerAdvice` does not reliably cover exceptions occurring **before `DispatcherServlet`**, especially when the firewall blocks right inside `FilterChainProxy`. To customize firewall status/logging, use Spring Security's `RequestRejectedHandler` mechanism appropriate for your deployment version rather than trying to catch `RequestRejectedException` via controller advice or broadening a global catch.

When logging, record the error type, request/correlation ID, method, and **sanitized/truncated** route; never log session cookies, `Authorization` headers, secrets, or unfiltered raw query strings. Avoid letting error responses leak matcher rules or internal filter chain details. Never return 200 "for easier debugging" when a request is rejected by the firewall.

## 7. Testing StrictHttpFirewall Behavior

### 7.1. Direct Unit Tests Independent of Network/Container

With `spring-security-web` and `spring-test` (pulled in via `spring-boot-starter-test` in a Boot app), you can verify `HttpFirewall` directly. JUnit 5 example file `StrictFirewallTest.java` under `src/test/java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.FirewalledRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StrictFirewallTest {
    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    private MockHttpServletRequest req(String method, String uri) {
        return new MockHttpServletRequest(method, uri);
    }

    @Test
    void allowsOrdinaryGet() {
        FirewalledRequest accepted =
            firewall.getFirewalledRequest(req("GET", "/public/ping"));
        assertNotNull(accepted);
        accepted.reset();
    }

    @Test
    void rejectsSemicolonByDefault() {
        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(
                req("GET", "/public/ping;version=2")));
    }

    @Test
    void rejectsEncodedSlashByDefault() {
        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(
                req("GET", "/api/items%2F42")));
    }

    @Test
    void rejectsTraceMethodByDefault() {
        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(
                req("TRACE", "/public/ping")));
    }
}
```

These tests use **default Strict** to verify core rules without depending on statuses generated by a proxy or container. `MockHttpServletRequest` is a Spring Test mock request; it does not fully simulate Tomcat/Jetty/Undertow decoding rules, so integration tests remain necessary when modifying firewall settings or relying on special URL encoding.

To verify the `firewallCustomizer` bean from Section 5.1, add a test exercising the actual `FilterChainProxy`, because the test above instantiates a fresh default Strict instance. Do not treat the unit test above as proof that your customizer is wired into the application.

### 7.2. Manual Verification Against a Locally Running App

Once `/public/ping` exists and the app is running at `localhost:8080`, try:

```bash
# Normal URL: may return 200 with body {"status":"ok"}.
curl -i http://localhost:8080/public/ping

# URL with semicolon: default Strict rejects if container forwards to firewall.
curl -i --path-as-is 'http://localhost:8080/public/ping;version=2'

# Encoded slash: may be blocked earlier by container or rejected by Strict.
curl -i --path-as-is 'http://localhost:8080/api/items%2F42'

# TRACE: blocked by Strict or container depending on configuration.
curl -i -X TRACE http://localhost:8080/public/ping
```

These examples carry no credentials and should only be run in dev/staging environments you control. If you receive 400 without firewall logs, check Tomcat/proxy first because the request may have been rejected at a lower layer. If the request reaches the controller, verify `springSecurityFilterChain` registration and whether the app actually uses your designated firewall bean. Do not conclude the firewall rejected a request from HTTP status 400 alone.

### 7.3. Regression Matrix When Changing Policy

| Test Case | Expected Response / Path |
| --- | --- |
| Normal `GET /public/ping` | Firewall allows; controller can return 200 |
| `GET` containing semicolon | Default Strict rejects; controller not invoked |
| Encoded slash/backslash or unnormalized URL | Fails default Strict policy; may be blocked earlier by proxy/container |
| HTTP method `TRACE` | Fails default Strict allowlist |
| Valid API GET/POST | Not blocked for URL shape; auth/CSRF/authorization still apply |
| REST PUT/PATCH/DELETE actually used | Must be in custom allowlist if methods were narrowed |
| Browser OPTIONS preflight | If API uses CORS, must be handled properly; custom allowlist must not accidentally block it |
| Unauthenticated user on protected route | Passes firewall if URL is valid, then auth handles separately |
| Unauthorized user on protected route | Firewall allows valid URL, then authorization denies |
| Intentionally allowed matrix variables | Matchers, controller, and proxy interpret the same route without permission bypass |
| Multiple Spring Security chains | Firewall policy still applies at `FilterChainProxy` level, not per chain |
| Error logging/response | Does not leak raw credentials; distinguishes firewall, proxy, and 403 auth |

An essential end-to-end check: for **both an authorized and an unauthorized user**, test normal requests and URL representations treated as equivalent by the application. No variant may reach a sensitive endpoint when permissions deny it. That is why URL policy must align across proxy, container, security matchers, and MVC.

## 8. Investigation Workflow When an API Is Rejected by the Firewall

1. **Capture the actual request:** method, path, encoding, query, proxy routing, servlet context path, and response status. Mask cookies/tokens and minimize personal data before logging.
2. **Identify the rejecting layer:** proxy, servlet container, `FilterChainProxy`, or Spring MVC. Look for the exact exception type; `RequestRejectedException` is a much clearer firewall signal than status alone.
3. **Check version and configuration:** default `StrictHttpFirewall` or custom `HttpFirewall`; whether a `WebSecurityCustomizer` bean overrides settings; whether multiple `SecurityFilterChain`s exist.
4. **Analyze each abnormal character:** semicolon, encoded slash, backslash, double slash, dot segments, unusual method; verify whether a real business reason exists for that representation.
5. **Prefer fixing client/URL contract:** eliminate unnormalized paths, move values containing slashes to query/body, and normalize encode/decode once at the proper boundary.
6. **Relax only one specific rule when truly necessary:** e.g., semicolon for matrix variables; evaluate URL matching safety and add regression tests. Keep remaining Strict rules intact.
7. **Test from outside in:** run the same request through the proxy and directly against the app in a test environment; verify no path confusion or authorization bypass occurs.

### Common Pitfalls to Avoid

- Seeing HTTP 400 and immediately disabling the firewall or switching to `DefaultHttpFirewall`.
- Equating `RequestRejectedException` with CSRF 403, unauthenticated 401, or insufficient-permission 403.
- Assuming that enabling encoded slashes in Strict means Tomcat or the reverse proxy will definitely forward or interpret them identically.
- Using `setUnsafeAllowAnyHttpMethod(true)` to "fix" unusual methods without understanding the risk. This option should be avoided in ordinary applications.
- Allowing semicolons because one client builds malformed URLs instead of fixing the client or route contract.
- Creating an overly narrow HTTP method allowlist while forgetting `OPTIONS` preflight, `HEAD`, or active REST methods.
- Testing only controller/MVC and skipping proxy, container, `FilterChainProxy`, and filter chain registration.
- Logging full raw URIs/headers of rejected requests, leaking tokens and control characters into logs.
- Treating the firewall as a replacement for input validation and per-endpoint authorization.

## 9. Decision Checklist

- [ ] Use default `StrictHttpFirewall` unless a verified compatibility requirement exists.
- [ ] Understand that `DefaultHttpFirewall` still performs path checks but is less strict—not a shortcut to bypass all errors.
- [ ] Distinguish normalized paths, semicolons, encoded slashes, backslashes, and HTTP methods.
- [ ] Firewall runs before authentication/authorization logic; classify `RequestRejectedException` separately from 401/403.
- [ ] Do not arbitrarily enable `setAllow...` setters; require explicit justification, scope, and regression tests if needed.
- [ ] Test `StrictHttpFirewall` directly and run end-to-end tests through proxy/container when changing policy.
- [ ] Verify exact matchers, servlet context path, and controller routes across URL variants.
- [ ] Ensure firewall changes do not cause authorization bypass, wrong-route dispatch, or data leaks in logs.

**Conclusion:** `StrictHttpFirewall` is the tightly controlled default choice for Spring Security Servlet; `DefaultHttpFirewall` offers broader compatibility without the same level of protection. When a request is rejected, identify the exact rule and layer blocking it. Fix the URL contract or relax **only** the single condition genuinely needed on Strict, then test the entire chain: proxy → servlet → security → MVC.
