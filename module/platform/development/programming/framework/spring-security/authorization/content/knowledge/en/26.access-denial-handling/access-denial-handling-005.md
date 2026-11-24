# JSON Responses for APIs and Appropriate Navigation for Web Interfaces

In Spring Security (Servlet), the same access denial decision may require two different response formats: API clients need **HTTP status and structured JSON**, while users navigating a website typically need a **login page or an insufficient-permissions notice page**. This lesson belongs to the **Access Denial Handling** topic in Spring Security Authorization; the focus is handling denials at the security filter layer rather than confusing them with business error handling in controllers.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish **unauthenticated** from **authenticated with insufficient permissions**, choosing the right HTTP 401/403 status and browser behavior.
- Explain the roles of `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`.
- Configure APIs to return consistent JSON while websites use form login and a 403 page without leaking HTML responses into APIs.
- Separate API and website paths using two `SecurityFilterChain` beans; test status codes, headers, bodies, and navigation targets.

## 2. Two Types of Denials and the Response Contract

**Authentication** identifies who the caller is; **authorization** determines whether that identity is permitted to perform the operation. Not every security error should be treated as 403.

| Scenario | API (machine/SPA/mobile client) | Browser-navigated Web Page |
| --- | --- | --- |
| Not logged in / no valid credentials, calling a protected resource | Typically `401 Unauthorized` + JSON; with HTTP Basic/Bearer, requires the corresponding `WWW-Authenticate` header | `302` redirect to `/login` in form login; after login, can return to the original URL |
| Logged in, missing role/authority | `403 Forbidden` + JSON | `403` + page explaining access is denied; can *forward* to a 403 page |
| Public API path, no login required | `200` or the corresponding business status | Not applicable |
| User submits invalid credentials to the login form | Depends on API auth mechanism; Basic/Bearer have their own challenge behavior | Form login typically redirects to `/login?error`; this is a login failure, not a resource permission error |

Note: `401` means authentication is required or invalid; the English name "Unauthorized" is easily confused with authorization. `403` means access is denied. Regardless of 401/403 status, the client-facing content must be stable enough to handle without leaking authorization details, passwords, tokens, or stack traces.

For an API using Basic in the example below, a response might look like:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store

{"status":401,"error":"AUTHENTICATION_REQUIRED","message":"Authentication is required to use the API."}
```

If authenticated but lacking permission:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store

{"status":403,"error":"ACCESS_DENIED","message":"You do not have permission to access this resource."}
```

The `error` codes are an application-defined contract. Clients should rely on **HTTP status** first, then read `error` to display messages or select actions. Do not use status 200 with `"error": 403`, as middleware, clients, and monitoring systems will misinterpret it.

## 3. Where Does Spring Security Handle This?

In the Servlet flow, `FilterChainProxy` selects the matching `SecurityFilterChain`. Within the filter chain, `AuthorizationFilter` may deny access. `ExceptionTranslationFilter` converts applicable security exceptions into HTTP responses:

```text
HTTP request
  |
  v
FilterChainProxy -> matching SecurityFilterChain
  |
  v
ExceptionTranslationFilter
  |  invokes downstream filters/application
  +-- AuthenticationException / insufficiently authenticated caller
  |      -> AuthenticationEntryPoint
  |         API: 401 + JSON | Web: redirect to login
  |
  +-- AccessDeniedException, fully authenticated but lacking permissions
         -> AccessDeniedHandler
            API: 403 + JSON | Web: 403 page
```

This is a conceptual flow diagram, not an exhaustive list of every filter in order. When an `AccessDeniedException` occurs for an anonymous user (and in some cases remember-me without sufficient authentication level), Spring Security restarts the authentication process via `AuthenticationEntryPoint`. If the user is sufficiently authenticated, it calls `AccessDeniedHandler`. Therefore, do not hardcode a rule "whenever `AccessDeniedException` occurs, return 403" while ignoring authentication state.

- `AuthenticationEntryPoint`: decides how to prompt the caller to authenticate. `LoginUrlAuthenticationEntryPoint` suits form login; APIs can use an entry point returning JSON 401 or a Bearer/Basic entry point.
- `AccessDeniedHandler`: decides how to respond when authenticated but lacking permission. The handler can send a JSON status/body or route to a 403 page.
- `RequestCache`: for web apps, saves the request to return after login; for stateless APIs, saving requests in the HTTP session is usually unnecessary.
- `@ControllerAdvice` / `@ExceptionHandler`: useful for errors inside MVC controllers, but **not a reliable replacement** for denial handling at the security filter before the controller.

## 4. Choosing How to Separate API and Web

When paths are clearly separated (e.g., `/api/**` and the remaining pages), **two `SecurityFilterChain` beans** make the policy transparent:

1. A chain with `@Order(1)` and `securityMatcher("/api/**")` handles only the API. Declare JSON 401/403, API authentication strategy, request cache, and appropriate session settings.
2. The web chain omits `securityMatcher`, serving as the fallback configuration for the rest. Enable `formLogin`, permit access to the login page, and configure the 403 page.
3. Within each chain, `authorizeHttpRequests().requestMatchers(...)` defines who can access **within that chain's scope**. `securityMatcher` selects the chain, whereas `requestMatchers` selects authorization rules; the two concepts are not interchangeable.
4. Specific chains must precede general chains. If no chain matches a request, Spring Security does not protect that request; therefore, there should be a default catch-all chain.

Do not rely solely on the `Accept: application/json` header to infer that a request is an API call: many clients send `*/*`, browser `fetch()` may automatically follow 302 redirects, and proxies may alter headers. Distinct paths or endpoint contracts are usually more reliable. When the exact same URL genuinely serves both JSON and HTML, you can consider `defaultAuthenticationEntryPointFor(...)` and `defaultAccessDeniedHandlerFor(...)` with a `RequestMatcher`, but you must test missing/ambiguous header cases.

## 5. Runnable Java 17+ Example: JSON for /api/**, Appropriate Pages for Web

The example uses **Spring Boot 3.x / Spring Security 6.x (Servlet)**, Maven, and Java 17+. It intentionally uses HTTP Basic for GET-only API URLs for easy testing with `curl`; the website uses form login with sessions. In a real system, pick an appropriate API authentication mechanism (such as Bearer token/OAuth2 Resource Server) and use encoded passwords instead of demo accounts.

Create two files:

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-responses</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/denial/SecurityResponseApplication.java`**

```java
package com.example.denial;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityResponseApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityResponseApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader123")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin123")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http, ObjectMapper mapper)
            throws Exception {
        AuthenticationEntryPoint json401 = (request, response, exception) -> {
            // This is an HTTP Basic demo; the challenge header is part of the protocol.
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"api\"");
            writeJson(mapper, response, 401, "AUTHENTICATION_REQUIRED",
                    "Authentication is required to use the API.");
        };

        AccessDeniedHandler json403 = (request, response, exception) ->
                writeJson(mapper, response, 403, "ACCESS_DENIED",
                        "You do not have permission to access this resource.");

        http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(cache -> cache
                        .requestCache(new NullRequestCache()))
                .httpBasic(basic -> basic.authenticationEntryPoint(json401))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(json401)
                        .accessDeniedHandler(json403));

        // Keep default CSRF; demo only has GET APIs.
        // Review security section before adding POST/PUT/DELETE.
        return http.build();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/forbidden", "/error")
                        .permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .exceptionHandling(errors -> errors
                        .accessDeniedPage("/forbidden"));
        return http.build();
    }

    private static void writeJson(
            ObjectMapper mapper, HttpServletResponse response,
            int status, String error, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", status);
        body.put("error", error);
        body.put("message", message);
        mapper.writeValue(response.getWriter(), body);
    }

    @RestController
    static class DemoEndpoints {

        @GetMapping("/api/public")
        Map<String, String> publicApi() {
            return Map.of("result", "public");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Principal principal) {
            return Map.of("username", principal.getName());
        }

        @GetMapping("/api/admin/report")
        Map<String, String> adminReport() {
            return Map.of("report", "ready");
        }

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        String home() {
            return "<h1>Home</h1><a href='/admin/panel'>Admin panel</a>";
        }

        @GetMapping(value = "/admin/panel", produces = MediaType.TEXT_HTML_VALUE)
        String adminPanel() {
            return "<h1>Admin panel</h1>";
        }

        @GetMapping(value = "/forbidden", produces = MediaType.TEXT_HTML_VALUE)
        ResponseEntity<String> forbiddenPage() {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .contentType(MediaType.TEXT_HTML)
                    .body("<h1>403 - Insufficient Permissions</h1>"
                            + "<a href='/'>Back to home</a>");
        }
    }
}
```

**Explanation of key lines:**

- `apiChain` has high priority and matches only `/api/**`. All APIs not marked `permitAll` require login; `/api/admin/**` also requires `ROLE_ADMIN` (`hasRole("ADMIN")` automatically prepends `ROLE_`).
- `json401` is attached to **both** `exceptionHandling` and `httpBasic`. Since invalid credential errors can be handled directly by `BasicAuthenticationFilter`, attaching both keeps the JSON body consistent for both missing and wrong credentials. `WWW-Authenticate: Basic ...` preserves the proper HTTP Basic challenge.
- `json403` returns JSON 403 only for callers who are authenticated but fail the rule. The shared helper `writeJson` uses Jackson to properly escape strings, sends the right HTTP status, and prevents caching of error content.
- `STATELESS` and `NullRequestCache` avoid using sessions/request replay for the demo API. For the web chain, form login uses a session and the default request-saving mechanism so the browser can return to the requested page after login.
- `formLogin(Customizer.withDefaults())` uses the default login page provided by Spring Security, so no `GET /login` controller is needed. When building a custom form login with `loginPage("/login")`, you must provide that page yourself.
- `accessDeniedPage("/forbidden")` performs an **internal forward** to the HTML endpoint with HTTP 403. The URL in the address bar remains the denied resource. The `/forbidden` endpoint is permitted through security to render the error page and itself returns status 403.

Demo account `reader/reader123` only has `ROLE_USER`; `admin/admin123` has `ROLE_ADMIN`. The `{noop}` prefix is solely to simplify the learning example; never use it for real passwords.

### Running and Observing

From the directory containing `pom.xml`, with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

Test the public API:

```bash
curl -i http://localhost:8080/api/public
```

Result: `HTTP 200` with JSON `{"result":"public"}`.

Unauthenticated:

```bash
curl -i http://localhost:8080/api/me
```

Result: `HTTP 401`, `WWW-Authenticate: Basic realm="api"`, and JSON body with code `AUTHENTICATION_REQUIRED`. This is not the HTML of `/login`.

Authenticated but lacking permission:

```bash
curl -i -u reader:reader123 http://localhost:8080/api/admin/report
```

Result: `HTTP 403`, JSON `ACCESS_DENIED`. Meanwhile:

```bash
curl -i -u admin:admin123 http://localhost:8080/api/admin/report
```

Result: `HTTP 200` and `{"report":"ready"}`.

Unauthenticated web page:

```bash
curl -i -H "Accept: text/html" http://localhost:8080/admin/panel
```

Result: HTTP `302` with `Location` pointing to `/login`. Open `http://localhost:8080/admin/panel` in a browser, log in with `reader/reader123`: you receive an **HTML 403 page** because `reader` lacks admin permission. Log in with `admin/admin123`: the admin panel is displayed. Spring Security's form login includes a CSRF token; simulating login via `curl` requires handling the token and session cookie, not just sending username/password.

### Essential Test Matrix

| Case | Expected Status | Additional Checks |
| --- | --- | --- |
| `GET /api/public` no credentials | 200 | Public JSON |
| `GET /api/me` no credentials | 401 | JSON; challenge header; no `Location: /login` |
| `GET /api/me` wrong Basic credentials | 401 | Consistent JSON; no HTML returned |
| `GET /api/admin/report` with `reader` | 403 | JSON; code `ACCESS_DENIED` |
| `GET /api/admin/report` with `admin` | 200 | Report content |
| `GET /admin/panel` not logged in | 302 | Target is login |
| `GET /admin/panel` logged in as `reader` | 403 | HTML page; request forwarded to `/forbidden` |
| `GET /admin/panel` logged in as `admin` | 200 | Admin HTML page |

Additional headers such as `Content-Length`, `Set-Cookie`, and absolute/relative paths in `Location` may vary by environment; use status and the meaning of `Location` as primary criteria. When testing with `fetch`, remember that redirects are followed automatically by default: a request may end with **HTML 200 of the login page** after an **initial 302**, then throw an error in `response.json()`.

## 6. How Does Forwarding to a 403 Page Differ from Redirecting?

There are two common navigation approaches, with different observable HTTP statuses:

- **Forward** (e.g., `accessDeniedPage("/forbidden")`): the server handles the error page internally without requiring the browser to send a new request. It can preserve `403` and the original URL. Suitable for an "Insufficient permissions" page.
- **Redirect** (e.g., `response.sendRedirect("/forbidden")`): the server returns `302`, and the browser sends a new request to `/forbidden`. Consider the loss of `403` status on the first response, the URL change, and redirect loops if the destination page itself is blocked. Do not use redirects as a substitute for API 403 errors.
- **Login redirect** when unauthenticated is the proper behavior for **interactive HTML pages**, handled by form login's `AuthenticationEntryPoint`. For an SPA, you can keep the 401 JSON status and let the frontend navigate to the login screen after reading the status.

Also do not redirect to a URL supplied by a user parameter without validation, as this easily creates an **open redirect**. When implementing the UI, create an error page with a safe return link, an adequate explanation, and no sensitive information displayed.

## 7. Things to Check Before Real-World Deployment

**CSRF policy and authentication style.** The example above has GET APIs only and **keeps default CSRF**. Browser-sent HTTP Basic credentials or session cookies can suffer CSRF risks when state-changing endpoints exist. Do not blindly copy `csrf.disable()` into every API. For Bearer token APIs explicitly sent in the `Authorization` header and not relying on browser auto-sent credentials, a different CSRF configuration can be considered based on the threat model. When CSRF is enabled, a POST missing a token can result in 403 **even when logged in**: that is not necessarily a missing role.

**Protocol-compliant challenges.** With HTTP Basic, `401` needs `WWW-Authenticate: Basic ...`. With OAuth2 Resource Server/Bearer tokens, use `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` (or preserve standard headers/challenges when customizing the JSON body). Do not force every `401` to have the same Basic header if the app uses Bearer.

**Paths and filter chains.** If the API has multiple prefixes (e.g., `/api/v1/**` and `/internal/**`), declare full chain coverage without missing routes. Do not place a catch-all chain before the API chain. A URL not matched by any filter chain may bypass protection. Do not forget that login/logout endpoints provided by filters themselves must also reside in the appropriate chain.

**Unified error handling.** If the app uses `ProblemDetail`/RFC 9457 for business errors, you can design compatible 401/403 payloads; security-layer handlers are still needed. Test error codes, `Content-Type`, charset, and ensure no exceptions leak. Do not let the frontend probe permissions by relying on message strings that vary with localization.

**CORS, proxies, and content negotiation.** CORS preflight (OPTIONS) does not carry credentials like real requests; configure CORS properly rather than interpreting every preflight 403 as a missing role. With reverse proxies/context paths, verify login redirect URLs, HTTPS, and forwarded headers. Use explicit API routes or matchers so clients never receive unexpected HTML.

**Method security.** `@PreAuthorize`/`@PostAuthorize` rules can also throw `AccessDeniedException`. Verify the exception path through Spring Security and MVC in your real configuration, especially when custom `@ControllerAdvice` is present. The goal remains ensuring APIs receive proper JSON and web pages receive proper HTML.

## 8. Common Mistakes and Fixes

1. **API returns 302 to /login:** form login is applying to the API or the API chain did not match. Verify `@Order`, `securityMatcher`, and `AuthenticationEntryPoint`; do not just patch around it with `@ControllerAdvice`.
2. **All cases return 403:** failing to distinguish anonymous from authenticated users, or calling `sendError(403)` in a custom filter. Use an entry point for unauthenticated callers and a denied handler for insufficient permissions.
3. **API returns JSON when credentials are missing, but HTML when Basic password is wrong:** `exceptionHandling.authenticationEntryPoint` was configured, but `httpBasic`'s entry point was forgotten. Attach the same handler to both paths as in the example.
4. **403 page turns into 302 or 200:** using `sendRedirect` instead of a forward/403 response, or the error page endpoint resets the status itself. Inspect actual requests via DevTools Network rather than just looking at the rendered page.
5. **/login or /forbidden redirect loop:** the login/error page URL is not `permitAll` or the login endpoint lies outside the filter chain's scope.
6. **API POST gets 403 despite having ROLE_ADMIN:** investigate CSRF, CORS, authentication, and rules in order; do not jump to conclusions from the status alone.
7. **React/Vue encounters "Unexpected token <" when parsing JSON:** the API returned HTML (often after a login redirect). Check `response.redirected`, the final URL, `Content-Type`, and design the API to return 401 JSON.
8. **Client logic relies on framework error text:** messages can change across versions, languages, or exceptions. Maintain stable application error codes and log details on the server without sending stack traces externally.

## 9. Practice Exercise

Suppose an application has `GET /api/orders`, `DELETE /api/orders/{id}`, and `GET /admin/orders`. Define the contract:

- Unauthenticated API caller: HTTP 401 JSON matching the authentication mechanism in use.
- Authenticated API caller lacking delete permission: HTTP 403 JSON; **do not** redirect to the login page.
- Unauthenticated browser accessing `/admin/orders`: redirect to the login page; after login, navigate back to the appropriate page.
- Authenticated browser lacking admin permission: HTML 403, with a link to a safe page.
- For `DELETE`, verify CSRF according to **how credentials are sent**; do not check only roles.

Self-verify using the Network tab or an HTTP client: for each scenario, record **status, Location, WWW-Authenticate, Content-Type, body, and final URL**. If you cannot explain why a response came from `AuthenticationEntryPoint` or `AccessDeniedHandler`, trace the chain and `Authentication` state first.

## 10. Official References

- Spring Security — [Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter) (`ExceptionTranslationFilter`).
- Spring Security — [Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) (`securityMatcher` and multiple chains).
- Spring Security — [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) (authorization rules).
- Spring Security — [Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html) (web login).
- Spring Security API — [AccessDeniedHandlerImpl](https://docs.spring.io/spring-security/site/docs/6.1.x/api/org/springframework/security/web/access/AccessDeniedHandlerImpl.html) (403 and forward).

**Key takeaway:** Choose responses based on **authentication state and the endpoint contract**: APIs receive protocol-compliant status/JSON/challenges; websites receive navigation to login or a 403 page with a meaningful status.