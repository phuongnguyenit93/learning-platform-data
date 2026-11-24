# JSON Responses for APIs and Error Pages for Browser Applications

## 1. Same Security Error, Two Ways of Communicating with Users

A Spring Security application can simultaneously serve **REST APIs** and **browser-based web pages**. When access is denied, both must adhere to the same authentication and authorization rules, yet **how the response is represented** should suit the recipient:

- **APIs** called by other programs: return the **right HTTP status code**, a machine-processable `Content-Type`, and a **JSON body with a stable structure**. Clients must be able to distinguish unauthenticated, insufficient permissions, and system errors without parsing HTML.
- **Browser web pages**: can **redirect to the login page** when there is no login session; when the user is logged in but lacks permissions, return **403 along with an HTML page explaining the error**. The browser displays content to the user while the status code remains accurate.

Key point: **the HTTP status code conveys the processing outcome**, whereas JSON or HTML is the **content format**. Never turn a 403 error into 200 just because the error page rendered successfully.

| Case | Typical API | Website Using Form Login |
| --- | --- | --- |
| Missing or invalid credentials | `401 Unauthorized`, JSON; with HTTP Basic include `WWW-Authenticate` | `302 Found` + `Location: /login` for the user to log in |
| Authenticated but insufficient permissions | `403 Forbidden`, JSON | `403 Forbidden`, HTML page "Access Denied" |
| Form login failed | Not applicable if API uses Basic/Bearer; dedicated JSON login endpoint depends on design | Usually `302` to `/login?error`, showing a message on the login page |
| Endpoint does not exist | `404 Not Found`, JSON per API contract | 404 HTML error page |
| Unhandled server error | `500 Internal Server Error`, JSON stripped of sensitive data | 500 HTML error page |

This table describes **a common design**, not mandatory default behavior for every Spring Security configuration. An API endpoint can redirect to HTML if it accidentally uses `formLogin`; a web page configured purely like an API can return JSON. We must configure explicitly for each URL group.

### HTTP Example: API Lacking Permissions

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to access this resource",
  "instance": "/api/admin"
}
```

`application/problem+json` is the **Problem Details** format standardized in RFC 9457. The fields above mean:

- `type`: identifies the error type; `about:blank` is used for ordinary HTTP errors.
- `title`: short name of the error type, e.g. `Forbidden`.
- `status`: corresponding HTTP code; must match the actual status in the response.
- `detail`: safe explanation for the client, without disclosing internal permission policies.
- `instance`: specific resource/request where the error occurred; include only information safe to expose.

The structure can add `requestId` or a stable application error code if clients need tracing support. Never stuff stack traces, tokens, session IDs, passwords, or sensitive principal content into error JSON.

### HTTP Example: Browser Encountering a 403 Error

```http
HTTP/1.1 403 Forbidden
Content-Type: text/html;charset=UTF-8

<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>403 - Access Denied</title></head>
<body>
  <h1>Access Denied</h1>
  <p>Your account is not permitted to open this page.</p>
  <a href="/web/open">Back to public page</a>
</body>
</html>
```

This is a **true 403 error page**: the browser receives status 403 and renders HTML, even though the user sees a complete page. Conversely, when unauthenticated and using form login, the browser may receive **302 → /login → 200**; the final 200 belongs to the **login page**, not the original resource.

## 2. Error-Handling Components in Servlet Spring Security

For Servlet-based Spring Boot 3.x / Spring Security 6.x applications, distinguish two layers:

1. **The Spring Security filter layer** handles authentication and authorization, often before the request reaches a controller.
2. **The Spring MVC layer and Spring Boot error page mechanism** handle errors inside controllers, MVC processing, and other application errors.

At the Security layer:

- `AuthenticationEntryPoint` decides **how to initiate authentication** when a request does not yet satisfy authentication requirements. APIs usually return 401; form-login web apps usually redirect to `/login`.
- `AccessDeniedHandler` decides **how to respond when access is denied**. APIs can return 403 JSON; web apps can return 403 and internally forward to an HTML page.
- `ExceptionTranslationFilter` routes `AuthenticationException` and `AccessDeniedException` thrown in downstream filters to the appropriate entry point or access-denied handler. It does not check passwords or grant roles itself.
- `BasicAuthenticationFilter` has its own authentication failure path: if configuring HTTP Basic, specify the entry point on `httpBasic(...)` **and** in `exceptionHandling(...)` so both invalid credentials and requests without credentials produce the expected API response.
- `CsrfFilter` also has its own CSRF error handling. A POST missing a CSRF token can receive 403 before reaching the controller; inspect this flow if you want every API 403 error to be uniform.

At the MVC layer:

- `@RestControllerAdvice` / `@ExceptionHandler` are suitable for standardizing errors thrown from **controllers, services, or MVC**. They **do not replace** `AuthenticationEntryPoint` and `AccessDeniedHandler` for exceptions already handled in security filters.
- Spring Boot has a general error-handling mechanism (`/error`) and supports HTML/template error pages. Do not treat MVC JSON configuration as sufficient to guarantee API security errors also return JSON.

### Routing by URL Rather Than Guessing from Headers

A clear approach is defining **two `SecurityFilterChain` beans**:

- `/api/**`: HTTP Basic or Bearer token, returning JSON on authentication/authorization errors; never redirects to a login UI.
- Web URLs: form login, redirect to login when unauthenticated, HTML for 403 after authentication.

Use `securityMatcher("/api/**")` to scope the **entire API filter chain**, then use `requestMatchers(...)` inside to define **permissions** per endpoint. Distinguishing these two matchers is critical: `requestMatchers("/api/**")` alone does not necessarily separate JSON response handling from the form-login flow.

Do not rely solely on `Accept: application/json`: not every client sends this header; `fetch` may send `*/*`, and modern web pages can call APIs too. Contracts by path or security chain are usually easier to verify. If content negotiation must be used, define explicit precedence and test actual headers.

## 3. Practical Spring Boot Example: Problem Details JSON and 403 HTML Page

The example uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet**. Create a project via Spring Initializr with `Spring Web` and `Spring Security`, choosing Gradle and Java 17 or newer. In `src/main/java/demo/security/SecurityResponseDemoApplication.java`, place the following class. This is **a complete Spring Boot program when run inside a project with those dependencies**; it cannot be compiled standalone with `javac` without Spring/Jackson libraries.

```java
package demo.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityResponseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityResponseDemoApplication.class, args);
    }

    @Bean
    AuthenticationEntryPoint apiEntryPoint(ObjectMapper mapper) {
        return (request, response, exception) -> {
            response.setHeader(
                "WWW-Authenticate",
                "Basic realm=\"demo-api\""
            );
            writeProblem(
                request, response, mapper, 401,
                "Unauthorized", "Authentication is required"
            );
        };
    }

    @Bean
    AccessDeniedHandler apiDeniedHandler(ObjectMapper mapper) {
        return (request, response, exception) ->
            writeProblem(
                request, response, mapper, 403,
                "Forbidden",
                "You do not have permission to access this resource"
            );
    }

    private static void writeProblem(
            HttpServletRequest request,
            HttpServletResponse response,
            ObjectMapper mapper,
            int status,
            String title,
            String detail) throws IOException {

        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");

        Map<String, Object> problem = new LinkedHashMap<>();
        problem.put("type", "about:blank");
        problem.put("title", title);
        problem.put("status", status);
        problem.put("detail", detail);
        problem.put("instance", request.getRequestURI());

        mapper.writeValue(response.getWriter(), problem);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiEntryPoint,
            AccessDeniedHandler apiDeniedHandler) throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/open").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(basic ->
                basic.authenticationEntryPoint(apiEntryPoint)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(apiEntryPoint)
                .accessDeniedHandler(apiDeniedHandler)
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/web/open", "/access-denied")
                    .permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .exceptionHandling(errors ->
                errors.accessDeniedPage("/access-denied")
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class DemoEndpoints {

        @GetMapping("/api/open")
        public Map<String, String> openApi() {
            return Map.of("message", "public api");
        }

        @GetMapping("/api/admin")
        public Map<String, String> adminApi() {
            return Map.of("message", "admin api");
        }

        @GetMapping(
            value = "/web/open",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String openWeb() {
            return "<!doctype html><html lang=\"en\">"
                + "<meta charset=\"UTF-8\"><title>Public Page</title>"
                + "<body><h1>Public Page</h1>"
                + "<a href=\"/web/profile\">Profile</a></body></html>";
        }

        @GetMapping(
            value = "/web/profile",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String profile() {
            return "<!doctype html><html lang=\"en\">"
                + "<meta charset=\"UTF-8\"><title>Profile</title>"
                + "<body><h1>Logged in</h1></body></html>";
        }

        @GetMapping(
            value = "/web/admin",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String adminWeb() {
            return "<!doctype html><html lang=\"en\">"
                + "<meta charset=\"UTF-8\"><title>Admin</title>"
                + "<body><h1>Admin Page</h1></body></html>";
        }

        @RequestMapping(
            value = "/access-denied",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public ResponseEntity<String> deniedPage() {
            String html = """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="UTF-8">
                  <title>403 - Access Denied</title>
                </head>
                <body>
                  <h1>Access Denied</h1>
                  <p>Your account is not permitted to open this page.</p>
                  <a href="/web/open">Back to public page</a>
                </body>
                </html>
                """;

            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .contentType(MediaType.TEXT_HTML)
                .body(html);
        }
    }
}
```

### Why Is It Configured This Way?

**The API chain** has `@Order(1)` and `securityMatcher("/api/**")`, so it processes URLs under `/api/` first. The web chain has `@Order(2)` and handles the remaining URLs. The `hasRole("ADMIN")` rule requires the actual `ROLE_ADMIN` authority; user `reader` only has `ROLE_USER`, so even when authenticated, calling `/api/admin` results in 403.

Two points for API errors must be configured explicitly:

1. `.exceptionHandling(...authenticationEntryPoint(apiEntryPoint).accessDeniedHandler(apiDeniedHandler))` handles unauthenticated requests and authorization denials in the exception translation flow.
2. `.httpBasic(basic -> basic.authenticationEntryPoint(apiEntryPoint))` ensures **invalid Basic credentials** are handled by the API's JSON entry point. Installing handlers only in `@RestControllerAdvice` does not achieve that goal.

`writeProblem(...)` uses `response.setStatus(...)` and writes JSON directly rather than calling `sendError(...)`. This avoids an unintended handoff to the default error page mechanism that could alter the body. `ObjectMapper` generates JSON with proper escaping; the program does not concatenate JSON strings by hand. When the API requires Basic authentication, `401` must include the `WWW-Authenticate` challenge; the code sets this header in the entry point. The error explanation stays generic so it does not disclose the authorization structure.

**The web chain** uses `formLogin` so unauthenticated users are directed to the default login page. When a user is authenticated but lacks permission to enter `/web/admin`, `accessDeniedPage("/access-denied")` performs an **internal forward** to the HTML content; the HTTP status remains 403. This differs from `sendRedirect(...)`, because a redirect creates a new request and easily results in 200 on the final page if the developer does not handle it deliberately.

`/access-denied` is `permitAll()` so the error page is not blocked by security rules themselves. In real applications, hardcoded HTML can be replaced with Thymeleaf/Freemarker templates or designed static pages; the example intentionally uses inline HTML so it only needs two dependencies and keeps focus on status/format mechanics.

**Do not disable CSRF in this example.** All test commands below are GET. For applications using sessions, cookies, or HTTP Basic that browsers may attach automatically, disabling CSRF indiscriminately creates risk. If deploying a truly stateless Bearer API, evaluate and configure CSRF separately according to the authentication model. By default, CSRF can reject POST/PUT/DELETE missing a token before MVC runs, and JSON generation for that error needs separate testing.

### Running and Testing the API

In the root directory of the project with Gradle Wrapper generated:

```bash
./gradlew bootRun
# On Windows:
# .\gradlew.bat bootRun
```

Call the endpoints from another terminal:

```bash
curl -i http://localhost:8080/api/open

curl -i http://localhost:8080/api/admin

curl -i -u reader:reader123 http://localhost:8080/api/admin

curl -i -u admin:admin123 http://localhost:8080/api/admin
```

Results to verify:

| Request | Status | `Content-Type` | Key Content |
| --- | --- | --- | --- |
| `GET /api/open`, no credentials | **200** | `application/json` | `{"message":"public api"}` |
| `GET /api/admin`, no credentials | **401** | `application/problem+json` | `title: Unauthorized`; includes `WWW-Authenticate: Basic ...` |
| `GET /api/admin`, valid `reader` credentials | **403** | `application/problem+json` | `title: Forbidden` |
| `GET /api/admin`, valid `admin` credentials | **200** | `application/json` | `{"message":"admin api"}` |
| `GET /api/admin`, wrong Basic password | **401** | `application/problem+json` | `title: Unauthorized`; includes Basic challenge |

Example body for `reader` lacking permissions (JSON is written with stable field ordering in the demo thanks to `LinkedHashMap`, though clients **must not depend on key order**):

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to access this resource",
  "instance": "/api/admin"
}
```

Other header details like `Date`, `Content-Length`, security headers, and absolute/relative addresses may differ by version, middleware, or configuration. Do not write tests relying on header order or details outside the API contract.

### Running and Testing in a Browser

In a **fresh browser or incognito window**:

1. Open `http://localhost:8080/web/open` while unauthenticated: the public HTML page appears with **200**.
2. Open `http://localhost:8080/web/profile`: the initial request receives **302** with `Location` pointing to `/login`; the browser follows the redirect and displays the login page.
3. Log in with `reader / reader123`: the saved profile page request may be restored, returning **200** HTML.
4. Open `http://localhost:8080/web/admin` in `reader`'s session: receive **403** and see the "Access Denied" HTML page.
5. Log in with `admin / admin123` in a new session: opening `/web/admin` returns **200** and admin content.

To view the **first 302 response** from a terminal, run:

```bash
curl -i http://localhost:8080/web/profile
```

Do not use `curl -L` when wanting to observe the initial status, because `-L` follows redirects automatically and may only show the final result. In browser DevTools, check the **Network** tab, enable preserving logs across redirects if needed, and match URLs to statuses. For `/web/admin` after logging in as `reader`, the status must be 403 even though the HTML page rendered.

These accounts and passwords are only for learning on `localhost`; `HTTP Basic` encodes credentials in Base64, which is **not encryption**. On real networks, use HTTPS and proper identity and secrets management; never ship these sample passwords to production.

## 4. Error Page Options for Browser Applications

The example above builds the 403 page with `@RequestMapping("/access-denied")` and `ResponseEntity` for easy execution. In systems with larger UIs, templates are usually used and content is separated from Java:

- **Forward to a 403 page**: configure `exceptionHandling(ex -> ex.accessDeniedPage("/access-denied"))`. The controller/view receives the forward and returns HTML with status **403**. Permit access to the error page path and ensure an actual template/resource exists.
- **Write HTML directly in `AccessDeniedHandler`**: immediate control over status, headers, and simple layout; suits small notice pages, but is inconvenient for maintaining complex UIs.
- **Spring Boot/MVC error pages**: use MVC-layer templates/pages for `404`/`500`. This is a different category from authentication/authorization; configure them to avoid leaking stack traces and system details.

A web app should not arbitrarily redirect every 403 to `/login`: a logged-in user lacking permissions should not be forced to re-login repeatedly. The 403 page message should explain that the action was denied and provide safe navigation or instructions for requesting access, without publishing detailed internal permission lists.

With custom form login, you must serve `GET /login` (or the configured URL), allow access to assets needed to render the page, and preserve CSRF token submission on the form. If the login page itself is protected, users may encounter redirect loops. When login fails, `AuthenticationFailureHandler` handles the login attempt's outcome; do not confuse it with lacking access permissions after logging in.

## 5. MVC Errors vs. Security Errors: Choosing the Right Formatting Spot

If Java services throw errors inside controllers/services, `@RestControllerAdvice` can standardize status codes and JSON bodies. The following example is a **partial illustration**, added to a project that has its own application business error `ResourceNotFoundException`:

```java
@RestControllerAdvice(assignableTypes = ApiResourceController.class)
class ApiErrorAdvice {

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(
            ResourceNotFoundException exception) {

        ProblemDetail body = ProblemDetail.forStatus(
            HttpStatus.NOT_FOUND
        );
        body.setTitle("Not Found");
        body.setDetail("The requested resource was not found");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"
            ))
            .body(body);
    }
}
```

`ApiResourceController` and `ResourceNotFoundException` in this snippet are **illustrative types** from another API, not part of the runnable `SecurityResponseDemoApplication` example above. The snippet's purpose is to show the **exception-handling boundary**: errors from MVC/controllers can be standardized in advice, whereas 401/403 errors from security filters need dedicated security handlers. Never apply `catch (Exception)` to turn every error into 200 JSON.

In a real system, you can standardize an API-wide error contract following Problem Details:

| Error Type | Appropriate Handler | Suggestion |
| --- | --- | --- |
| Unauthenticated / wrong Basic credentials | API `AuthenticationEntryPoint` | 401 JSON + Basic challenge |
| Authenticated but insufficient permissions | API `AccessDeniedHandler` | 403 JSON, no permission-policy leakage |
| Missing/invalid CSRF token | Dedicated CSRF and access-denied handling per app flow | 403, test actual response body |
| Missing resource in controller | `@ExceptionHandler` / `@RestControllerAdvice` | 404 JSON |
| Invalid input data in MVC | Validation/MVC handling | 400 JSON with usable error codes |
| Server error | General Boot/MVC error handling | 500 JSON/HTML without stack traces |
| Browser lacking permissions | Web `AccessDeniedHandler`, forward to view | 403 HTML |
| Browser unauthenticated | Web `AuthenticationEntryPoint` | 302 to login |

**Note on consistency:** JSON formatting for 401/403 in the example is guaranteed for **the demonstrated GET cases**. If the app adds CSRF, CORS, custom filters, method security, unmatched path errors, or a reverse proxy, each layer may generate its own response. To guarantee "every `/api/**` error is always JSON", test every error-producing point, including filters running before controllers and error dispatches. Do not conclude from a single handler alone.

## 6. Client Behavior Matching Response Types

For JavaScript clients calling `/api/**`:

- **401**: re-check authentication state; in token-based systems, trigger a single token refresh if the mechanism allows, or direct the user to log in. Do not loop token refreshes endlessly. With Basic, 401 includes a challenge and the client decides whether to supply credentials.
- **403**: session/credentials may be valid, but permissions are lacking. Display a notice from a safe message; do not automatically treat 403 as "token expired".
- **Unexpected 302/HTML**: if an API is designed to return JSON yet the client receives a login page, check whether the web chain or a proxy redirected it. Some `fetch` calls follow redirects automatically and end up receiving `200 text/html`; `response.ok` may then be true even though the body violates the contract completely.
- **5xx**: show a generic error message, log a tracking ID, and avoid passing stack traces down to the UI. Retry only when appropriate for the operation's semantics and idempotency.

A practical principle when writing clients:

```javascript
async function getAdminData() {
  const response = await fetch("/api/admin", {
    headers: { Accept: "application/problem+json, application/json" }
  });

  const mediaType = response.headers.get("Content-Type") ?? "";
  const isJson = mediaType.includes("json");

  if (response.status === 401) {
    throw new Error("Authentication required");
  }
  if (response.status === 403) {
    throw new Error("Access denied");
  }
  if (!response.ok) {
    throw new Error("Request failed: " + response.status);
  }
  if (!isJson) {
    throw new Error("API returned an unexpected format");
  }

  return response.json();
}
```

This is an example **client for an API designed to return JSON**, not Java code to compile in a Spring project. In the HTTP Basic example, a browser without credentials may show a challenge prompt, and `fetch` may be subject to browser CORS/cookie/authentication constraints. In production applications, token/cookie storage, credential handling, CSRF, and navigation must be clearly designed; this snippet focuses solely on **response classification**.

## 7. Verification Methods and Common Mistakes

1. **Check the first status**: `/web/profile` without a session is 302; the login page after redirect is 200. `/api/admin` without Basic auth is 401, not 302.
2. **Check `Content-Type`**: API errors must have the promised JSON type, e.g. `application/problem+json`; web error pages use `text/html`. Do not parse HTML as JSON.
3. **Check critical headers**: Basic 401 needs `WWW-Authenticate`; login 302 needs `Location`. For error responses that might contain sensitive details, consider `Cache-Control: no-store`.
4. **Check which filter chain is selected**: wrong `@Order`/`securityMatcher` configuration can cause APIs to receive form login and HTML; verify which matcher covers each URL.
5. **Check principal and authorities**: "logged in" does not prove "sufficient permissions". `hasRole("ADMIN")` checks `ROLE_ADMIN`; `hasAuthority("ADMIN")` is a different string check.
6. **Check CSRF for POST/PUT/DELETE**: 403 may come from a missing token, not a role. Do not fix by disabling CSRF application-wide.
7. **Check where the error is thrown**: filter errors are not solved by `@RestControllerAdvice` alone; MVC 404/validation errors need handling in MVC or the `/error` mechanism.
8. **Ensure the error page is accessible**: the URL used to forward/render the error must exist and be permitted; avoid creating redirect/forward loops.
9. **Keep the contract stable and safe**: body status matches HTTP status, JSON is properly escaped, no leaked stack traces, account info, or internal secrets. You can use a request ID to correlate with server logs.

### Automated Testing Suggestions

At the HTTP integration test level with `MockMvc` or a test client, verify **status + Content-Type + meaningful JSON/HTML fields**, rather than comparing full HTML or every version-dependent header. Core scenarios:

- `GET /api/admin` unauthenticated → 401, `application/problem+json`, with Basic challenge.
- `GET /api/admin` with `reader` → 403, `application/problem+json`, `status` in body equals 403.
- `GET /api/admin` with `admin` → 200, JSON data body.
- `GET /web/profile` without session → 302 to login.
- `GET /web/admin` with `reader` session → 403 and HTML.
- `GET /web/admin` with `admin` session → 200 and HTML.

Add tests for POST missing a CSRF token, non-existent path errors, MVC exceptions, and custom error pages when the product includes those cases.

## 8. Practical Conclusion

When building an application combining APIs and browser UIs, place **security rules** in Spring Security and define **response representations** by client group:

- **API:** 401/403 with consistent error JSON (such as Problem Details), never letting HTML login redirects leak into API clients.
- **Browser:** unauthenticated users may receive 302 to login; authenticated users lacking permissions should see a 403 HTML page with status still 403.
- **MVC/application:** handle 400/404/500 separately in `@RestControllerAdvice` or the error-page mechanism; do not expect them to replace security-filter entry points/access-denied handlers.
- **Verify with real HTTP:** status, Content-Type, WWW-Authenticate/Location, body, and redirect chains are the decisive evidence.

### References

- [Spring Security — Servlet Architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — SecurityFilterChain and securityMatcher](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
