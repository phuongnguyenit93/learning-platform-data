# DelegatingAuthenticationEntryPoint: Choosing Authentication Responses by Request Group in Spring Security

## 1. Lesson Objectives

A Spring Boot application may serve both **HTML pages using form login** and **REST APIs for JavaScript/mobile**. When a user is not yet authenticated, these two request types usually need different responses:

- Someone visiting `/web/private` with a browser expects to be **redirected to the login page** (typically HTTP 302 to `/login`).
- A client calling `/api/orders` usually expects **HTTP 401 Unauthorized** and a structured error body; an HTML redirect to `/login` breaks the API contract.
- An OAuth 2.0 Bearer client also needs **`WWW-Authenticate: Bearer`** per RFC 6750, not simply an HTML redirect.
- A user who is **authenticated yet lacks permission** must usually receive **403 Forbidden**, rather than being sent to log in again.

In Spring Security Servlet, **`DelegatingAuthenticationEntryPoint`** handles **selecting an `AuthenticationEntryPoint` based on the failing request's `RequestMatcher`**. On its own, it does not verify passwords, does not perform authorization, and does not replace filter chains; it only chooses **how to initiate authentication or how to return an unauthenticated error**.

After this lesson, you should be able to:

1. Understand the path `ExceptionTranslationFilter` → `AuthenticationEntryPoint.commence(...)` and when it is actually invoked.
2. Distinguish `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `AuthenticationFailureHandler`; assign HTTP 401, 302, 403, and challenge headers properly.
3. Use `LinkedHashMap<RequestMatcher, AuthenticationEntryPoint>` with `setDefaultEntryPoint(...)` on the Spring Security 6.5.x baseline.
4. Design rules **putting specific ones first**, avoiding overlaps, classifying APIs by path, and checking `Accept` when appropriate; never rely on an easily spoofed header to grant permissions.
5. Configure a `SecurityFilterChain` using `HttpSecurity.exceptionHandling(...)`, with a Java 17+ example and hands-on checks.
6. Know when `ExceptionHandlingConfigurer.defaultAuthenticationEntryPointFor(...)` is a cleaner shorthand, and when to use **multiple filter chains**.
7. Preserve **Bearer/Basic/form login** semantics, handle request cache, CSRF, saved requests, CORS, JSON/Problem Details, and WebFlux equivalents.
8. Write tests proving which group goes to which entry point, including unmatched cases, rule ordering, 401, and 403.

**Technical scope:** Java 17+, Spring Boot 3.x, Spring Security 6.5.x **Servlet** for the full example; WebFlux has analogous classes with a different API. Paths and responses in this lesson are illustrative; verify against your actual version if upgrading to Spring Security 7.x.

## 2. Request Groups and Response Contracts: Lock Down Requirements Before Coding

Suppose an application serves three groups:

| Request Group | Example | No Valid Authentication | Authenticated but Lacking Permission |
| --- | --- | --- | --- |
| HTML page requiring login | `GET /web/private`, `Accept: text/html` | HTTP 302/303 navigating to `/login` per flow | HTTP 403 or "access denied" page; **do not** force re-login by default |
| REST API | `GET /api/items`, with or without `Accept` | HTTP 401; Problem Details JSON if the API contract requires it | HTTP 403 with a safe body |
| AJAX/fetch outside `/api` | `GET /web/private`, `Accept: application/json` | HTTP 401 JSON so JS decides UI handling | HTTP 403 or corresponding error body |
| Bearer-protected resource server | `GET /v1/data`, `Authorization: Bearer ...` | 401 with Bearer challenge when applicable per RFC 6750 | 403/`insufficient_scope` when lacking scope |
| HTTP Basic-only machine client | `GET /internal/resource` | 401 with `WWW-Authenticate: Basic realm=...` | 403 when credentials are valid yet lack permission |

This table is the **desired contract**, not defaults Spring Security always infers automatically. Actual outcomes also depend on filter chains, exception handlers, authentication mechanisms, request matchers, and request caches.

### Two Separate Decisions

1. **Is access allowed?** — decided by authentication and authorization logic, e.g. `authorizeHttpRequests(...).authenticated()` or `hasAuthority(...)`.
2. **When requirements are not met, how to respond?** — when an error falls into a case eligible for an authentication entry point, `DelegatingAuthenticationEntryPoint` picks the right branch.

Choosing 401/302 by path **does not alter permissions** for that path. If a request is `permitAll()`, it does not go through the entry point merely because `Accept` or path matches a rule.

## 3. AuthenticationEntryPoint and ExceptionTranslationFilter

### 3.1. What Is AuthenticationEntryPoint?

In Servlet, the interface lives at:

```java
org.springframework.security.web.AuthenticationEntryPoint
```

Main method:

```java
void commence(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException authException
) throws IOException, ServletException;
```

An `AuthenticationEntryPoint` can:

- Return `401` so the client knows credentials are needed.
- Set `WWW-Authenticate` for HTTP Basic or OAuth Bearer.
- Redirect to `/login` to initiate the form-login flow.
- Return error JSON per the API contract.
- Perform other actions fitting the active authentication mechanism.

It does **not** accept passwords to verify, issue `Authentication` itself, or run authorization. It decides the response at the **authentication/unauthenticated error boundary**.

### 3.2. How Does ExceptionTranslationFilter Coordinate?

In a Servlet `SecurityFilterChain`, `ExceptionTranslationFilter` handles security exceptions raised **downstream in the filter chain**. Overview:

```text
Incoming HTTP request
        |
        v
Security filters -> Authentication filters -> AuthorizationFilter
                                            |
                                            +-- protected + no valid auth
                                            |      |
                                            |      v
                                            |   ExceptionTranslationFilter
                                            |      |
                                            |      v
                                            |   AuthenticationEntryPoint
                                            |      |
                                            |      +-- browser -> 302 /login
                                            |      +-- API     -> 401 JSON
                                            |
                                            +-- valid auth, insufficient authority
                                                   |
                                                   v
                                                AccessDeniedHandler
                                                   |
                                                   +-- 403
```

Understand both branches when the filter catches an error:

- **`AuthenticationException`:** calls `AuthenticationEntryPoint`.
- **`AccessDeniedException`:** if the request is not sufficiently authenticated per the trust resolver (e.g. anonymous), Spring Security can initiate authentication via the entry point; if the principal is authenticated yet lacks permissions, it forwards to `AccessDeniedHandler`.

Do not assume 100% of 401 errors are handled by `ExceptionTranslationFilter`. For instance, `UsernamePasswordAuthenticationFilter` has `AuthenticationFailureHandler` for wrong form login submissions; `BearerTokenAuthenticationFilter` also has its own authentication failure handling path. This matters when debugging why a JSON entry point was not invoked for a request carrying a bad Bearer token.

### 3.3. RequestCache and SavedRequest

With form login, Spring can save the blocked request in `RequestCache` so after logging in the user is redirected back to the original URL. When the entry point returns 302 to `/login`, saved requests usually make sense.

For REST APIs, storing thousands of saved requests in HTTP sessions just to return 401 is typically **useless** and can create unwanted sessions. Stateless API designs must decide request caching separately; do not equate switching an entry point to 401 with disabling all session creation mechanisms.

## 4. Which Rules Does DelegatingAuthenticationEntryPoint Use to Pick a Branch?

Servlet class:

```java
org.springframework.security.web.authentication
    .DelegatingAuthenticationEntryPoint
```

In Spring Security 6.5, the common constructor is:

```java
DelegatingAuthenticationEntryPoint(
    LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mappings)
```

After creating it, call:

```java
delegating.setDefaultEntryPoint(fallbackEntryPoint);
```

`LinkedHashMap` preserves **insertion order**. When `commence(request, response, ex)` runs, the delegating entry point:

1. Iterates through `RequestMatcher`s in order.
2. At the first matcher returning `true` → invokes its corresponding `AuthenticationEntryPoint.commence(...)` and stops.
3. If no matcher matches → invokes the configured `defaultEntryPoint`.

```text
                        DelegatingAuthenticationEntryPoint
                                       |
                        Matcher 1: /api/** ?
                         /           \
                       yes            no
                       /               \
             JSON 401 / Bearer?     Matcher 2: Accept JSON?
                                     /              \
                                   yes               no
                                   /                  \
                              JSON 401            default entry point
                                                       |
                                                       v
                                                  Redirect /login
```

This is **first-match-wins**; there is no automatic "pick most specific matcher" if you put a broad matcher first. A matcher like `AnyRequestMatcher.INSTANCE` placed at the top of the list can prevent all subsequent matchers from ever running.

### 4.1. Fallback Rules

For the constructor above, **the default entry point must be non-null**. If unconfigured or if the map is empty, Spring can throw a configuration error during initialization / `afterPropertiesSet()` validation. Never "leave it blank hoping Spring figures it out".

With `HttpSecurity.exceptionHandling().defaultAuthenticationEntryPointFor(...)`, the DSL may use the first registered entry point as a fallback when nothing matches, depending on configuration; thus **registration order also carries policy meaning**. Setting an explicit fallback in the demo makes the decision easy to verify.

### 4.2. Spring Security 7.x Differences

In 6.5.x, the `LinkedHashMap` constructor and `setDefaultEntryPoint(...)` are still the documented Javadoc API. In newer 7.x lines, the map constructor and setter are marked deprecated for removal; the API recommends a new constructor taking `RequestMatcherEntry` or the `DelegatingAuthenticationEntryPoint.builder()` builder. Hence the example in this lesson intentionally uses **6.5.x**; when upgrading versions, do not "copy verbatim and ignore deprecations"—migrate to that line's API.

## 5. Choosing RequestMatchers: URL First, Accept Second

### 5.1. Path Is the Clearer Contract Boundary

If an organization defines **every route under `/api/**` as a JSON API**, match on path first. Do not let an attacker-sent `Accept: text/html` switch an API endpoint into an HTML login flow.

However, path matching must align with servlet mappings, context paths, reverse proxies, and normalization. In the default Boot Servlet example, `request.getServletPath()` is used for illustration. For complex systems, use `PathPatternRequestMatcher` / matchers recommended by your Spring Security version rather than string checks on `getRequestURI()`, which can break under context paths or URL encoding.

### 5.2. Accept Can Assist AJAX Outside the API Group

A request carrying `Accept: application/json` may expect JSON errors even when the path is not under `/api/**`. Spring Security provides `MediaTypeRequestMatcher` paired with a content negotiation strategy:

```java
MediaTypeRequestMatcher jsonMatcher = new MediaTypeRequestMatcher(
        new HeaderContentNegotiationStrategy(),
        MediaType.APPLICATION_JSON
);
jsonMatcher.setIgnoredMediaTypes(Set.of(MediaType.ALL));
```

Meaning: an `Accept: */*` request is not automatically treated as JSON in this example. However:

- `Accept` **is client-controlled**; it is only a hint for formatting responses, not proof that the user is trusted or authorized.
- Browsers commonly send multiple media types; test concrete content negotiation.
- `application/problem+json` or vendor `+json` types may require extra matchers/rules; do not assume every `+json` suffix is automatically matched by `MediaType.APPLICATION_JSON`.
- If an API sits at a fixed path, ensure the API is matched by a **path matcher** even if a client sends `Accept: text/html`.
- Request `Content-Type` describes the **body the client sends**, unlike `Accept` which describes the **response the client wants**; never use Content-Type instead of Accept for this decision.

### 5.3. Arbitrary Headers Should Not Affect Authorization

For example, an HTTP header `X-Requested-With: XMLHttpRequest` is sometimes used to guess AJAX requests. That header is trivial for clients to forge and untrustworthy for protecting endpoints. It may be used for presentation in controlled environments, but never to grant permissions or bypass authentication, CSRF, or trust boundaries.

## 6. Two Common Entry Points: Status 401 and Login Redirect

### 6.1. HttpStatusEntryPoint

`HttpStatusEntryPoint` has a constructor taking `HttpStatus`:

```java
AuthenticationEntryPoint api401 =
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);
```

It returns an HTTP status, suitable for clients that do not want browsers opening a Basic dialog or redirecting to HTML. If the API contract requires a JSON body, use a custom `AuthenticationEntryPoint` to write the body safely.

### 6.2. LoginUrlAuthenticationEntryPoint

`LoginUrlAuthenticationEntryPoint` initiates form login by redirecting to a configured URL:

```java
AuthenticationEntryPoint browserLogin =
        new LoginUrlAuthenticationEntryPoint("/login");
```

Requirement: `/login` must be an accessible login page endpoint, generated by Spring Security `formLogin` or provided by you. If it redirects to a route that also requires login without a page-rendering mechanism, the application can enter a redirect loop.

### 6.3. Basic and Bearer Have Their Own Challenge Semantics

`BasicAuthenticationEntryPoint` generates `WWW-Authenticate: Basic realm=...`. `BearerTokenAuthenticationEntryPoint` generates a Bearer challenge matching OAuth resource servers when configured properly. Replacing a Bearer entry point with `HttpStatusEntryPoint(401)` can drop the challenge header required by the API contract/RFC.

**Do not choose 401 merely because it "looks like an API".** Determine whether that API uses cookie-based auth, HTTP Basic, OAuth Bearer, or multiple mechanisms; the response must tell clients how to proceed under the right protocol.

## 7. Complete Example: Spring Boot Servlet Returning 401 JSON for APIs and 302 for Web Pages

This example uses **Java 17+, Spring Boot 3.x + Spring Security 6.5.x** on the Servlet stack, one filter chain, and demo account `alice`. Normal form login works at `/login`. When unauthenticated:

- `/api/**` returns **401 Problem JSON**, regardless of `Accept`.
- A non-API page with `Accept: application/json` returns **401 Problem JSON**.
- Remaining pages default to **302 redirect to `/login`**.

The **logged-in but lacking role** error is still handled by the `AccessDeniedHandler` branch (usually 403).

### 7.1. Gradle Dependencies

In a Spring Boot project created with Java 17:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Use a Servlet web application; do not add WebFlux just to copy config into the next section. If Spring Boot's dependency management selects a Spring Security version other than 6.5.x, check the API before running.

### 7.2. Full Java File

Save at `src/main/java/demo/entrypoint/EntryPointDemoApplication.java`:

```java
package demo.entrypoint;

import java.util.LinkedHashMap;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.accept.HeaderContentNegotiationStrategy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.servlet.http.HttpServletResponse;

@SpringBootApplication
public class EntryPointDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EntryPointDemoApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}local-demo-only")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        // Demo assumes default DispatcherServlet mapping "/".
        // Production: prefer version-recommended framework RequestMatcher.
        RequestMatcher apiPath = request -> {
            String path = request.getServletPath();
            return path.equals("/api") || path.startsWith("/api/");
        };

        MediaTypeRequestMatcher acceptsJson = new MediaTypeRequestMatcher(
                new HeaderContentNegotiationStrategy(),
                MediaType.APPLICATION_JSON);
        acceptsJson.setIgnoredMediaTypes(Set.of(MediaType.ALL));

        // RFC 9457 / Problem Details style, without leaking exceptions.
        AuthenticationEntryPoint apiProblem = (request, response, ex) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(
                    "{\"type\":\"about:blank\","
                    + "\"title\":\"Unauthorized\","
                    + "\"status\":401}");
        };

        AuthenticationEntryPoint browserLogin =
                new LoginUrlAuthenticationEntryPoint("/login");

        LinkedHashMap<RequestMatcher, AuthenticationEntryPoint> mappings =
                new LinkedHashMap<>();
        // Put path before Accept so /api never gets HTML redirects.
        mappings.put(apiPath, apiProblem);
        mappings.put(acceptsJson, apiProblem);

        DelegatingAuthenticationEntryPoint delegating =
                new DelegatingAuthenticationEntryPoint(mappings);
        delegating.setDefaultEntryPoint(browserLogin);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(delegating))
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String index() {
            return "Public home";
        }

        @GetMapping("/web/private")
        String privatePage() {
            return "Private HTML-like page";
        }

        @GetMapping("/api/items")
        String apiItems() {
            return "Items for signed-in user";
        }

        @GetMapping("/api/admin")
        String apiAdmin() {
            return "Admins only";
        }
    }
}
```

### 7.3. Explanation of Each Group

- `apiPath`: every request to `/api` or `/api/...` selects JSON 401 when **unauthenticated**, regardless of user agent/Accept header.
- `acceptsJson`: other routes where the client explicitly requests JSON also receive JSON 401.
- `LinkedHashMap`: **first matching rule wins**; both rules point to `apiProblem`, yet the order expresses prioritizing the URL contract over content negotiation.
- `browserLogin`: defaults to redirecting to `/login` when no rule matches; invoked only when authentication needs to start.
- `.formLogin(...)`: enables Spring Security form login and the default login page; this is a session-based Servlet demo.
- `.authorizeHttpRequests(...)`: access permissions are decided **before** choosing the response style. `/api/admin` requires `ROLE_ADMIN`, while Alice's account has only `ROLE_USER`.
- `apiProblem`: uses a static body to avoid exposing `AuthenticationException.getMessage()`, usernames, passwords, tokens, or stack traces.
- `.exceptionHandling(ex -> ex.authenticationEntryPoint(delegating))`: explicitly sets the entry point for `ExceptionTranslationFilter`.
- `{noop}` is strictly a **local demo password**. Production must use an appropriate password encoder, HTTPS, secret management, and account policies. Never store plaintext passwords in real repositories.

The "HTML-like page" returns text for easy demonstration. In a real MVC application, the `/web/private` controller could render a Thymeleaf template; entry point selection stays the same.

### 7.4. Running the Application

In a project with the Spring Boot Gradle plugin:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. The application listens on `http://localhost:8080` by default unless `server.port` is changed.

Use `curl -i` to inspect statuses/headers; requests without username/password demonstrate the difference clearly:

```bash
# 1. API: 401 JSON, no redirect even if client wants HTML.
curl -i -H 'Accept: text/html' \
  http://localhost:8080/api/items

# 2. Browser: redirect to login.
curl -i -H 'Accept: text/html' \
  http://localhost:8080/web/private

# 3. AJAX requesting JSON on a non-API route: 401 JSON.
curl -i -H 'Accept: application/json' \
  http://localhost:8080/web/private

# 4. Public route: 200 without invoking entry point.
curl -i http://localhost:8080/

# 5. Admin API when unauthenticated: 401 JSON.
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/admin
```

Expected results:

| Request | Status | Typical Header/Body |
| --- | --- | --- |
| `GET /api/items`, `Accept: text/html`, anonymous | 401 | `Content-Type: application/problem+json`, `{"status":401}` in body |
| `GET /web/private`, `Accept: text/html`, anonymous | 302 | `Location` pointing to `/login` (may be absolute/relative URL) |
| `GET /web/private`, `Accept: application/json`, anonymous | 401 | Problem JSON |
| `GET /`, anonymous | 200 | `Public home` |
| `GET /api/admin`, anonymous | 401 | Problem JSON |
| `GET /api/admin`, Alice authenticated via form | 403 | Lacking `ROLE_ADMIN`, not an "unauthenticated" error |

**Do not use `curl -L` when observing redirects**, because `-L` automatically follows `302` to `/login` and shows the final response, making it hard to see the initial redirect.

The demo code does not enable HTTP Basic; to test Alice's account, visit `/login` in a browser or use MockMvc in section 8. **Do not** assume `curl -u alice:...` works as configured login, since only form login is enabled. If Basic is also needed, enable it explicitly and re-test entry point behavior and realm.

## 8. Automated Testing with MockMvc

Unit/integration tests must assert **status**, **Location/Content-Type**, **matcher order**, and the authentication/authorization boundary. Section 7's project already includes `spring-security-test`.

File `src/test/java/demo/entrypoint/EntryPointDemoApplicationTests.java`:

```java
package demo.entrypoint;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class EntryPointDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void apiGets401JsonEvenWithHtmlAccept() throws Exception {
        mvc.perform(get("/api/items").accept(MediaType.TEXT_HTML))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith(
                        "application/problem+json"))
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void browserGetsLoginRedirect() throws Exception {
        mvc.perform(get("/web/private").accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().exists("Location"));
    }

    @Test
    void jsonClientOutsideApiGets401() throws Exception {
        mvc.perform(get("/web/private").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.title").value("Unauthorized"));
    }

    @Test
    void publicRouteNeverRequiresAuthentication() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public home"));
    }

    @Test
    void authenticatedButMissingAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin").with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserCanCallApi() throws Exception {
        mvc.perform(get("/api/items").with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("Items for signed-in user"));
    }
}
```

Test command:

```bash
./gradlew test --tests demo.entrypoint.EntryPointDemoApplicationTests
```

Expect **6 PASSing tests** when project/Java/Spring Security versions match and code is placed in the right file name/package. `with(user("alice").roles("USER"))` is a **Spring Security Test fixture**, which does not perform network form login or verify passwords. The 403 test checks the authorization branch; it does not prove Alice's password authentication flow.

### 8.1. What Additional Tests Are Needed in Production?

- `Accept: */*` on browser routes → which fallback runs? In the example, ignored media types send it to redirect.
- JSON accept with `q` weights and multiple media types; are vendor media types/`application/problem+json` mapped properly?
- API routes with/without trailing slashes, context paths, servlet prefixes, and forwarded headers.
- Requests sending an invalid Bearer token or wrong Basic credentials: which failure handler handles them?
- Logged-in user lacking a role → 403, not 302/login.
- Logged-in browser: `/web/private` returns page content without entry point interference.
- `AuthenticationException` raised in service/method security when unauthenticated; is it translated properly by the Security filter?
- Test multiple `SecurityFilterChain` beans and `@Order` if the application has multiple chains.
- Error body contains no paths/credentials/stack traces outside policy.
- After 401 API requests, no unwanted session storing saved requests is created under the system's stateless configuration.

## 9. Concise Configuration Using defaultAuthenticationEntryPointFor

You do not necessarily have to construct `DelegatingAuthenticationEntryPoint` manually. In Spring Security 6.5, `ExceptionHandlingConfigurer` provides:

```java
defaultAuthenticationEntryPointFor(
    AuthenticationEntryPoint entryPoint,
    RequestMatcher preferredMatcher)
```

With multiple matchers/entry points, the DSL can build a delegating entry point automatically. The snippet below merely illustrates **replacing** section 7's `.exceptionHandling(...)` block, assuming `apiPath`, `acceptsJson`, `apiProblem`, and `browserLogin` already exist:

```java
.exceptionHandling(ex -> ex
    .defaultAuthenticationEntryPointFor(apiProblem, apiPath)
    .defaultAuthenticationEntryPointFor(apiProblem, acceptsJson)
    .defaultAuthenticationEntryPointFor(
            browserLogin, AnyRequestMatcher.INSTANCE))
```

`AnyRequestMatcher.INSTANCE` is placed **last** as a fallback for all unmatched requests; in the explicit delegating demo, `setDefaultEntryPoint(browserLogin)` expresses this even more clearly.

Points to remember:

- `defaultAuthenticationEntryPointFor` adds a candidate to the list; if there is only **one** candidate, it can become the default directly.
- With multiple candidates, delegation mechanisms like `DelegatingAuthenticationEntryPoint` are used.
- `authenticationEntryPoint(entryPoint)` specifies an explicit entry point and may **override selection among default candidates** in exception handling; do not register multiple defaults and also call another explicit entry point expecting the rules to keep working.
- Other configurers such as `formLogin`, `httpBasic`, or `oauth2ResourceServer` can also register preferred entry points. Explicit configuration like section 7 is often easier to audit in complex mixed apps.
- Always test end-to-end because defaults and configurer ordering can change across versions or during security upgrades.

## 10. AuthenticationEntryPoint, AccessDeniedHandler, AuthenticationFailureHandler: Three Different Roles

| Component | When Is It Used? | Input/Object | Example |
| --- | --- | --- | --- |
| `AuthenticationEntryPoint` | Starts auth for unauthenticated/insufficiently authenticated requests | `AuthenticationException` | 302 login, 401 Basic/Bearer, 401 JSON |
| `AccessDeniedHandler` | Authenticated yet lacking authorization for resource | `AccessDeniedException` | 403/Problem JSON, 403 page |
| `AuthenticationFailureHandler` | A specific auth filter handles bad credentials, e.g. form submit | Failure from authentication filter | Redirect `/login?error` or return 401 login API |
| `AuthenticationSuccessHandler` | Authentication filter succeeds | Verified `Authentication` | Redirect saved request, return JSON, or set up session per flow |

An HTTP request **does not necessarily** pass through `AuthenticationEntryPoint` when authentication fails inside a login filter:

```text
POST /login
   -> UsernamePasswordAuthenticationFilter
   -> AuthenticationManager rejects wrong password
   -> AuthenticationFailureHandler (typically login?error)
   -> NOT necessarily DelegatingAuthenticationEntryPoint
```

Similarly with an invalid Bearer token:

```text
Authorization: Bearer invalid
  -> BearerTokenAuthenticationFilter
  -> AuthenticationManager rejects token
  -> configured AuthenticationFailureHandler / Bearer response
  -> NOT necessarily ExceptionTranslationFilter branch
```

Therefore, if product requirements demand **uniform error formatting across every authentication mechanism**, configure **each mechanism's failure handler as well**, not just `ExceptionTranslationFilter`.

### 10.1. Why Should 403 Not Be Turned into 401 for Logged-In Users?

A user authenticated with a `ROLE_USER` account calls `/api/admin`: authentication already succeeded, only permission is missing. Returning 401 can make the UI log out or enter an endless login loop. Returning **403** lets the client tell them apart: pick a different account/role or contact an admin, rather than re-entering the same password.

### 10.2. When Anonymous Encounters AccessDeniedException

An authorization rule `hasRole("ADMIN")` also denies anonymous callers. `ExceptionTranslationFilter` detects the user is not sufficiently logged in and invokes the authentication entry point; thus **anonymous hits on /api/admin usually return 401**, while `ROLE_USER` Alice receives 403. This is correct behavior, not a contradiction.

## 11. Choosing a JSON Error Format Without Leaking Information

When an API returns 401, the response can follow [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457):

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Unauthorized","status":401}
```

This is a minimal illustrative structure. Real apps may add `instance` or a correlation ID **containing no credentials**. Never return raw exception stack traces, passwords, Bearer tokens, session IDs, unverified usernames, or internal reasons like "user john@example.org is disabled".

### 11.1. Headers to Preserve per Mechanism

- OAuth Bearer: if a resource server blocks a missing/invalid token, return `WWW-Authenticate: Bearer` and error parameters when appropriate per RFC 6750.
- HTTP Basic: requires `WWW-Authenticate: Basic realm="..."` so clients understand the challenge.
- Cookie/session browser: 302 to login usually makes sense for navigation; 401 JSON may make more sense for XHR/fetch.
- CORS: `OPTIONS` preflight must be handled properly by the CORS layer when permitted; never let browsers see a failed preflight and assume bad credentials.
- No-store: sensitive error JSON should set an appropriate cache policy, especially when carrying auth or identity metadata.

`HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` sends only status; if you want a JSON body or specialized headers, use a wrapper/custom entry point or the protocol's built-in implementation such as Bearer.

### 11.2. Status 302 Can Be Auto-Followed by Fetch

An SPA calling `fetch("/web/private")` can follow a 302 redirect in the background and receive an HTML login page (sometimes with final status 200). JavaScript expecting JSON fails parsing. Therefore, route/API contracts should prefer 401 and let the frontend perform top-level login navigation intentionally instead of auto-redirecting every sessionless request.

## 12. With a Bearer Resource Server, Use the Protocol's Proper Entry Point

If the API is actually an OAuth2 Resource Server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

This configuration requires full `JwtDecoder`/issuer/JWKS setup; the snippet is purely illustrative DSL, **not a runnable file**. If using introspection/opaque tokens, configure `oauth2.opaqueToken(...)` accordingly.

For Bearer-protected endpoints, there is `BearerTokenAuthenticationEntryPoint`:

```java
AuthenticationEntryPoint bearer =
        new BearerTokenAuthenticationEntryPoint();
```

This entry point knows standard Bearer challenge semantics instead of sending headerless JSON 401. For example, if a browser group also exists, you can map path `/api/**` → `bearer` and default → `LoginUrlAuthenticationEntryPoint`; any custom JSON body must maintain challenge semantics.

**Configuration boundary note:** `BearerTokenAuthenticationFilter` has its own failure handler mechanism for a Bearer token **present in the request yet invalid**. To ensure all Bearer errors follow the contract, verify the resource server configuration as well, not just `ExceptionTranslationFilter`'s mapping.

### 12.1. Multiple Credentials on One Request

When a client sends both a session cookie and `Authorization: Bearer`, explicitly decide credential ordering and scope per security chain. Never let an invalid token silently "fall back" to a browser session if the API strictly requires Bearer. Use separate filter chains or explicit request rules when security requires isolation.

### 12.2. Basic Authentication

`BasicAuthenticationEntryPoint` carries realm/challenge semantics and can cause browsers to display a username/password dialog. If the frontend is a JavaScript app, `HttpStatusEntryPoint`/JSON might offer better UX — **but** it is not protocol-equivalent to HTTP Basic. Define the client contract and test `WWW-Authenticate` before replacing it.

## 13. Multiple SecurityFilterChains or One DelegatingAuthenticationEntryPoint?

There are two main architectures.

### 13.1. One Chain, Multiple Response Types

Use one `SecurityFilterChain` and a delegating entry point as in section 7 if:

- The groups share core session/authentication logic.
- They differ only in **how to respond when unauthenticated**.
- Authentication/authorization rules can be expressed safely within the same chain.
- You do not need major differences in CSRF, request cache, session creation, CORS, or Basic/Bearer filters.

### 13.2. Multiple Chains When Security Models Truly Differ

For instance, `/api` uses stateless Bearer JWT, while `/web` uses session form login. Here **multiple `SecurityFilterChain`s with `securityMatcher(...)` and `@Order`** are usually clearer:

```java
// Spring Security Servlet snippet; requires JwtDecoder/issuer config.
// @Order(1) ensures the API chain is evaluated before the catch-all chain.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .sessionManagement(s -> s
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(o -> o
                    .jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

The above is a **configuration illustration**, lacking imports and JwtDecoder/issuer config so it is not a standalone project; the API chain also needs CORS/CSRF/request cache per requirements. It illustrates **filter chain scope**, rather than directly using a delegating entry point.

**Key distinction:**

| Mechanism | Question | Timing |
| --- | --- | --- |
| `SecurityFilterChain.securityMatcher(...)` | "Which filter chain applies to this request?" | Before running the selected chain's filters |
| `RequestMatcher` inside `DelegatingAuthenticationEntryPoint` | "When an authentication entry point is needed, which response to return?" | **After** an authentication error / insufficient authentication |
| `authorizeHttpRequests.requestMatchers(...)` | "Which path requires which permission?" | At the authorization step |
| `AuthenticationManagerResolver` | "Which authentication manager/provider to use?" | When processing credentials per config |

Do not use a delegating entry point to "fake" isolation between Bearer and cookie-based sessions. It **does not remove** the current chain's filters, sessions, or authentication mechanisms.

## 14. RequestMatcher Order, Overlap, and Fallback: Common Bugs

### 14.1. Broad Matcher Placed Before Narrow Matcher

```java
// WRONG: matches every request; subsequent rules are never evaluated.
mappings.put(AnyRequestMatcher.INSTANCE, browserLogin);
mappings.put(apiPath, apiProblem);
```

In `DelegatingAuthenticationEntryPoint`'s constructor map, rules are evaluated in order; putting a generic matcher first can make APIs redirect to HTML login. Put specialized matchers first, with fallback via `setDefaultEntryPoint(...)` or at the end of the list.

### 14.2. Classifying Solely by Accept

```text
GET /api/orders
Accept: text/html
```

If you have `acceptsJson -> JSON 401` and a login-redirect fallback, the client above could receive 302 despite calling an API. Choose path-first to preserve the contract: **the API still returns 401**.

### 14.3. Forgetting Trailing Slashes / Context Paths

`/api`, `/api/`, `/api/items`, and `/context/api/items` behave differently depending on servlet path/context root. Test routes under `server.servlet.context-path`, dispatcher mappings, reverse proxy prefixes, and URL normalization. Never take an unnormalized request URI and check `startsWith("/api")` (as it would also match `/apiary`).

### 14.4. Missing or Wrong Fallback

No rule matches → default entry point. If the fallback is 401 JSON for the entire web app, browser navigation loses redirects. If the fallback is 302 login for all requests, unmatched XHR receives HTML. Choose based on a **request inventory** and test the default path rather than letting behavior accidentally hinge on the first matcher.

### 14.5. Redirect Loop to Login

If `/login` also requires authentication and no form-login page filter serves it, requests to login can redirect back to themselves. Ensure the login route is permitted and uses the right path. With a custom login page, explicit `permitAll()` / matching form login config is usually required.

## 15. RequestCache and Session Side Effects

An anonymous API request:

```http
GET /api/items
Authorization: (absent)
Accept: application/json
```

You expect 401. Yet because `ExceptionTranslationFilter` can save the request before invoking the entry point, the API could unintentionally create a session/cookie or overwrite a saved request used for browser login. When a stateless API is required, configure an appropriate **request cache** and session policy for the API:

```java
// Illustrative snippet for a stateless API chain, not the whole app:
http
    .requestCache(cache -> cache
            .requestCache(new NullRequestCache()))
    .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

In a mixed chain, applying `NullRequestCache` to the **entire chain** can break returning to the original HTML page after login. In that case, prefer separate chains or `HttpSessionRequestCache` with a matcher saving only browser navigations. Never tweak the request cache just to "pass a 401 test" while forgetting browser UX.

**Test this for real:** no unwanted new session after repeated API 401s, no sensitive saved requests, and successful browser login still returns to the right page per policy. Choosing the right redirect alone does not prove request caching is right.

## 16. JSON and Error Content: Security, Consistency, Observability

### 16.1. Do Not Leak Internal Authentication Reasons

In a custom entry point:

```java
// DO NOT DO THIS: can expose exception internals to the internet.
response.getWriter().write(
        "{\"error\":\"" + authException.getMessage() + "\"}");
```

Reason: messages can contain internal details, account info, providers, tokens/claims, or characters needing JSON escaping. Concatenating user input directly into JSON easily produces malformed bodies or injection. Use a static/generic body while auditing details in controlled logs. In production, the framework's `ProblemDetail`/JSON serializer can standardize formatting if integrated properly at the filter level.

### 16.2. CORS, Cookies, CSP, and Caching

- Browser preflight `OPTIONS` requests do not carry cookies/credentials like real requests; if CORS does not run first, preflight can get 401/302 and break the API. Configure `CorsFilter`/`http.cors(...)` with explicit allowed origins/headers/methods.
- A cross-origin frontend using session cookies needs appropriate `SameSite`, `Secure`, and CORS credentials policies; never combine `Access-Control-Allow-Origin: *` with credentialed requests.
- API 401/403 responses may be unreadable by JS if CORS headers are missing, even when the server returns the right status.
- Never set `Cache-Control: public` on error bodies containing identity/authorization metadata; consider `no-store`.
- With HTML login redirects, allow only configured/controlled redirect targets; avoid using query `returnUrl` to introduce an **open redirect**.
- `Accept` is an easily spoofed request header; switching response format by Accept is fine, but never alter security policy.

### 16.3. Observability

Minimum logs/metrics: request correlation ID, matcher group (api/json/browser), normalized authentication failure type, 401/302/403 status, and latency. Never log full `Authorization`, cookies, session IDs, or raw exceptions containing secrets. To see which matcher won, enable Spring Security debug logs in test environments, but **disable sensitive logging** in production.

## 17. WebFlux: Equivalent Classes Do Not Share Servlet Names

In WebFlux/reactive security, **do not use** Servlet `DelegatingAuthenticationEntryPoint`, `HttpSecurity`, or `jakarta.servlet.http.HttpServletResponse`.

Equivalent types:

| Servlet | WebFlux |
| --- | --- |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| `DelegatingAuthenticationEntryPoint` | `DelegatingServerAuthenticationEntryPoint` |
| `RequestMatcher` | `ServerWebExchangeMatcher` |
| `ExceptionTranslationFilter` | `ExceptionTranslationWebFilter` |
| `HttpSecurity.exceptionHandling(...)` | `ServerHttpSecurity.exceptionHandling(...)` |
| `LoginUrlAuthenticationEntryPoint` | `RedirectServerAuthenticationEntryPoint` |
| `HttpStatusEntryPoint` | `HttpStatusServerEntryPoint` |

In WebFlux, `commence(ServerWebExchange, AuthenticationException)` returns **`Mono<Void>`** and must not block the event loop. Configuration snippet **illustrated inside a `@Configuration` class**, not a standalone runnable project:

```java
ServerAuthenticationEntryPoint api401 =
        new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

ServerAuthenticationEntryPoint browserLogin =
        new RedirectServerAuthenticationEntryPoint("/login");

var api = new DelegatingServerAuthenticationEntryPoint.DelegateEntry(
        ServerWebExchangeMatchers.pathMatchers("/api/**"), api401);

DelegatingServerAuthenticationEntryPoint delegating =
        new DelegatingServerAuthenticationEntryPoint(api);

delegating.setDefaultEntryPoint(browserLogin);

return http
        .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .exceptionHandling(ex -> ex
                .authenticationEntryPoint(delegating))
        .build();
```

Place inside a method returning `SecurityWebFilterChain` with injected `ServerHttpSecurity http` and the corresponding Spring Security WebFlux 6.5 imports. WebFlux has a different model for sessions/request cache/CSRF/failure handlers; do not port Servlet code to WebFlux by swapping `HttpSecurity` for `ServerHttpSecurity` while keeping `RequestMatcher`.

If a WebFlux API uses Bearer, `BearerTokenServerAuthenticationEntryPoint` supports the corresponding challenge semantics; if a Problem JSON body is wanted, write a non-blocking reactive `ServerAuthenticationEntryPoint` that preserves valid headers.

## 18. Test Matrix by Request Group and Security State

| # | Group | Auth State | Expectation |
| --- | --- | --- | --- |
| 1 | `/api/items`, `Accept: application/json` | Anonymous | 401 JSON |
| 2 | `/api/items`, `Accept: text/html` | Anonymous | 401 JSON, because API path takes priority |
| 3 | `/api/items`, no Accept | Anonymous | 401 JSON |
| 4 | `/api/admin` | Anonymous | 401 JSON, not 403 |
| 5 | `/api/admin` | Alice with ROLE_USER | 403 |
| 6 | `/api/admin` | Admin with ROLE_ADMIN | 200 from controller if authentication is valid |
| 7 | `/web/private`, `Accept: text/html` | Anonymous | 302/Location login |
| 8 | `/web/private`, `Accept: application/json` | Anonymous | 401 JSON |
| 9 | `/web/private`, `Accept: */*` | Anonymous | Fallback redirect per example's rule |
| 10 | `/web/private` | Authenticated | 200 |
| 11 | `/login` | Anonymous | Login page/flow works, no redirect loop |
| 12 | `/` public | Anonymous | 200, entry point not called |
| 13 | `/apiary` | Anonymous | Not confused with `/api/**` |
| 14 | Application context path `/app` | Anonymous | Routes match real servlet mapping, no prefix bug |
| 15 | API sending invalid Bearer | Invalid credential | RFC 6750 challenge/401 per resource server config |
| 16 | Basic-protected endpoint | Missing Basic | 401/`WWW-Authenticate: Basic` if Basic is chosen |
| 17 | Login POST wrong password | Auth failure | Failure handler, do not assume delegating handles it |
| 18 | Cross-origin `OPTIONS` | No credentials | CORS preflight per policy, no unwanted HTML redirect |
| 19 | Repeated API 401s | Anonymous | No unwanted session/saved request created against policy |
| 20 | Browser login then return to page | Authenticated | Valid saved request/redirect if feature enabled |
| 21 | Overlapping matchers | Anonymous | First rule wins, test fixed ordering |
| 22 | No matcher matches | Anonymous | Explicit fallback executes |
| 23 | Failure response | Anonymous | No logging/returning tokens, passwords, or stack traces |
| 24 | Multi-chain mapping | Anonymous | API path hits right chain, never falls into browser chain |

**Test with browsers, MockMvc/WebTestClient, and HTTP clients**: browsers may auto-follow redirects; MockMvc shows the initial status; `curl` behavior changes with `-L`. For 403, use an authenticated test principal lacking the role to prove the authorization branch.

## 19. Troubleshooting: Symptom → Inspection Path

### API Receives HTML Login Page Instead of 401

Try `curl -i` without following redirects. Check whether the initial response is `302 Location: /login` or a 200 of the login page after the client followed it. Verify `apiPath` matches the right servlet path/context path, whether `AnyRequestMatcher` appears too early in matcher order, which chain handles it, and whether explicit `authenticationEntryPoint` was overridden by another configurer.

### Browser Receives 401 JSON Instead of Login Redirect

Check the actual `Accept` header (frontends sometimes send `application/json` on every request), whether the path accidentally matched `/api/**`, and whether the fallback entry point is `LoginUrlAuthenticationEntryPoint`. Adjust matchers only for presentation; never let browser paths skip auth to "avoid 401".

### API Receives 403 Despite Not Logging In

Check whether the request is truly anonymous/remember-me/fully authenticated per Spring Security's trust resolver, whether a custom `AccessDeniedHandler` forces status, whether multiple chains exist, or whether an error handler at another layer ran. Never turn authorization rules into `permitAll()` recklessly; trace filters and authentication state.

### Low-Privilege User Receives Login Redirect Instead of 403

If already authenticated yet redirected, check whether the app is re-initiating authentication, whether the user principal is treated as anonymous/remember-me, or whether a custom entry point was misconfigured. Distinguish resource GET requests from login POST failures. For missing roles, the default is AccessDeniedHandler, not a login redirect.

### Map Declared Yet App Fails to Start

Read the `DelegatingAuthenticationEntryPoint` startup exception: does the map have at least one matcher? Is `defaultEntryPoint` set? Is there a null entry point or wrong bean lifecycle? In Spring Security 6.5, the class implements `InitializingBean` and validates invariants on initialization.

### Second Matcher Is Never Invoked

An earlier rule matches everything, or `MediaTypeMatcher` is too broad. Use `LinkedHashMap`, put specific paths first, and test priorities. Never use `HashMap` when entry point selection order must stay deterministic.

### Invalid Bearer Responds Differently from Missing Bearer

This can happen because `BearerTokenAuthenticationFilter` routes invalid credentials through its failure handler, whereas missing credentials let authorization throw `AccessDeniedException` and go through exception translation. Check **both paths**, status/header/body, and JWT/opaque validation.

### Browser Reports CORS Even Though Backend Returns JSON 401

Check whether the response/preflight contains required CORS headers. For credentialed fetches, the server must allow the specific origin and matching credentials policy; a well-formed JSON 401 lacking CORS headers is still blocked from JavaScript by the browser.

### Unable to Return to Pre-Login Requested URL

If `NullRequestCache` or stateless session policy was applied across the entire chain including browsers, old requests are not saved. Separate browser and API chains when requirements differ; do not fix it by storing every API request in sessions.

### Using Spring Security 7 and Constructor Reports Deprecated

Migrate to `DelegatingAuthenticationEntryPoint.builder()` or the new constructor taking `RequestMatcherEntry` per the 7.x Javadoc. Do not guess method names; verify the exact artifacts on the classpath.

## 20. Standalone Java 17 Exercise: Illustrating First-Match-Wins

To see the priority mechanism without running all of Spring Boot, the program below models **matcher selection logic** in plain Java. It does not instantiate real `AuthenticationEntryPoint`s and performs no authentication.

Save `EntryPointRoutingModel.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Predicate;

public class EntryPointRoutingModel {
    record Request(String path, String accept) {}

    static String select(
            Request req,
            LinkedHashMap<Predicate<Request>, String> rules,
            String fallback) {
        for (Map.Entry<Predicate<Request>, String> entry
                : rules.entrySet()) {
            if (entry.getKey().test(req)) {
                return entry.getValue();
            }
        }
        return fallback;
    }

    public static void main(String[] args) {
        var rules = new LinkedHashMap<Predicate<Request>, String>();

        rules.put(
                r -> r.path().equals("/api")
                        || r.path().startsWith("/api/"),
                "401 JSON");

        rules.put(
                r -> "application/json".equals(r.accept()),
                "401 JSON");

        System.out.println(select(
                new Request("/api/items", "text/html"),
                rules, "302 /login"));
        System.out.println(select(
                new Request("/web/private", "text/html"),
                rules, "302 /login"));
        System.out.println(select(
                new Request("/web/private", "application/json"),
                rules, "302 /login"));
        System.out.println(select(
                new Request("/reports", "*/*"),
                rules, "302 /login"));
    }
}
```

Compile and run:

```bash
javac EntryPointRoutingModel.java
java EntryPointRoutingModel
```

**Exact** stdout:

```text
401 JSON
302 /login
401 JSON
302 /login
```

The exercise demonstrates **matcher ordering** only. Comparisons here intentionally use `String.equals("application/json")` for clarity and do not replace `MediaTypeRequestMatcher` or real content negotiation. Do not use simulation code to enforce access permissions or handle Bearer tokens.

Try reordering the rules by putting a "match all requests" rule first and watch every request receive the first rule's outcome. Then restore **specific before general** ordering.

## 21. Production Checklist

1. **Inventory:** list every request group (browser navigation, API, SPA fetch, Basic/Bearer, health, static assets, OAuth callbacks) and each group's 401/302/403 contract.
2. **Authentication vs authorization:** verify the entry point handles only unauthenticated requests; authenticated users lacking permissions use AccessDeniedHandler.
3. **Match strategy:** path-first for API contracts; Accept is a formatting signal, not security proof; matchers are stable across context/servlet mappings.
4. **Order:** LinkedHashMap and specific rules first; explicit default, never AnyRequestMatcher as the first rule.
5. **Protocol correctness:** RFC 6750 Bearer challenges; Basic realms; form login redirects; check failure handlers of every authentication filter.
6. **Error body:** standardized Problem Details/JSON without leaking exception details, tokens, or PII; accurate status and headers.
7. **Single vs multi-chain:** if only the response differs, delegation works; if mechanisms/sessions/CSRF/cache differ, consider separate chains.
8. **Sessions:** verify request caching and session creation; stateless APIs do not store saved requests unintentionally, while browser navigation keeps good UX.
9. **CSRF/CORS:** preserve CSRF on cookie-based writes; handle preflight and cookie/allowed-origin boundaries cleanly.
10. **Safety:** never use `Accept`/`User-Agent`/arbitrary headers to elevate privileges, skip authentication, or route clients to weaker endpoints.
11. **Tests:** MockMvc/WebTestClient, redirect vs JSON, 401 vs 403, overlapping matchers, default, Basic/Bearer, context path, multi-chain, CORS, and failure handlers.
12. **Version:** note your Spring Security baseline; when upgrading to 7.x, review constructor/builder deprecations and run regression tests.
13. **Observability:** metrics by request group/status; audit errors without logging Authorization/cookies/credentials; watch for redirect loops and 401/403 spikes.
14. **Documentation:** frontend/mobile teams know what to do upon 401; never assume a fetch following a redirect means login succeeded.

**Conclusion:** `DelegatingAuthenticationEntryPoint` does **not** decide "who has permission" — it decides **"when Spring Security requires starting authentication, what response should this client receive?"**. Use `RequestMatcher`s in intentional order, return protocol-compliant 401 for APIs, 302 for browser form login, and leave 403 to the authorization branch. That prevents APIs from receiving HTML login pages while preserving friendly sign-in UX for web users.

## 22. Official References

- [Spring Security 6.5.11 — DelegatingAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationEntryPoint.html): `LinkedHashMap` constructor, `commence`, and `setDefaultEntryPoint`.
- [Spring Security 6.5.11 — ExceptionHandlingConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/ExceptionHandlingConfigurer.html): `authenticationEntryPoint`, `defaultAuthenticationEntryPointFor`, and `accessDeniedHandler`.
- [Spring Security — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html): `commence` interface and HTTP response effects.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): AuthenticationException/AccessDeniedException, request cache.
- [Spring Security — Servlet Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): web filter architecture, exception handling, and authorization.
- [Spring Security — HttpStatusEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/HttpStatusEntryPoint.html): generic 401 status.
- [Spring Security — LoginUrlAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/LoginUrlAuthenticationEntryPoint.html): form login redirect.
- [Spring Security — MediaTypeRequestMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/MediaTypeRequestMatcher.html): content negotiation and ignored media types.
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): Bearer challenge.
- [Spring Security — DelegatingServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/DelegatingServerAuthenticationEntryPoint.html): entry point selection in WebFlux.
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): sessions, saved requests, and logout.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `WWW-Authenticate`, 401/403, and `insufficient_scope`.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): JSON Problem Details.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic errors and avoiding information leakage.
