# Preventing Redirects to Untrusted Addresses and Testing the Login Flow

> **Context:** Spring Security **Servlet**, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson focuses on **form login** and returning `Location`/redirect targets after login success or failure—especially when clients supply `next`, `returnUrl`, `redirect`, or `destination`. The goal is to prevent **open redirects** without breaking login, CSRF, sessions, authorization checks, and legitimate navigation. The Spring examples below belong to a Boot project with Maven/Gradle and matching dependencies; the Java 17 example at the end runs standalone.

## 1. What Is an Open Redirect and Why Does It Relate to Login?

An **open redirect** happens when an application issues a redirect response to an address controlled by an untrusted user, without restricting the destination via a trusted policy. Because the browser passes through the legitimate website's URL before being sent elsewhere, an attacker can leverage your domain's reputation for phishing, deceiving users, or chaining with other authentication/authorization flaws.

Example of an application with a trusted endpoint:

~~~text
GET https://app.example.test/login?next=https://fake-login.example/collect
                              |
                              v
                    User logs in properly
                              |
                              v
HTTP/1.1 302 Found
Location: https://fake-login.example/collect
~~~

If the app takes raw `next` as `Location`, the initial URL appears to belong to the legitimate site while the final destination sits outside the trust boundary. This is an **insecure flow example**, not a safe implementation.

**Security note:** An open redirect does not mean the origin website's session cookie is automatically sent to arbitrary external domains. Cookies still obey domain/path/`SameSite` and browser rules. The authentication risks lie in origin confusion, phishing, vulnerability chaining, and sensitive data that might appear in URLs depending on the app; never claim every redirect automatically leaks all tokens.

### Trust Boundaries

- **Trusted:** a path defined in application code, or a navigation key mapped **server-side** to an allowed path.
- **Untrusted:** query parameters, form fields, client-modifiable cookies, `Referer`, unnormalized `Host`, `X-Forwarded-Host` from untrusted hops, and any request-derived URL even if named `safeUrl`.
- **Necessary condition:** a URL looking "same-domain" or "starting with `/`" **is not enough** to prove safety, because browsers/proxies can interpret `//host`, backslashes, encoded characters, control characters, and userinfo URLs differently.

## 2. Four URL Patterns Commonly Seen in Login

| Pattern | Example | What to watch out for |
| --- | --- | --- |
| Server-chosen fixed target | `/app` | Safe when the app controls routes and never derives it from arbitrary input. |
| Same-app relative target | `/orders` | Reasonable when inside an allowlist; account for context path. |
| External absolute URL | `https://evil.example/collect` | Never use directly as a post-login redirect. |
| Scheme-relative URL | `//evil.example/collect` | Browsers interpret it as an external host, **not** an internal path. |

Dangerous inputs go beyond `https://evil.example`. Several values must be rejected if supplied as redirect targets:

~~~text
//evil.example/path
https://trusted.example.evil.example/path
https://trusted.example@evil.example/path
javascript:alert(1)
/\evil.example
%2F%2Fevil.example
%252F%252Fevil.example
../admin
/orders?next=https://evil.example
\r\nLocation: https://evil.example
~~~

The list above describes **payloads to include when testing policies**, without claiming all web servers/browsers parse every string identically. With `\r\n`, CR/LF characters could be exploited if code concatenates raw headers; modern HTTP frameworks usually block header injection, yet you must never rely on that to accept unvalidated URLs.

For domains, string checks like `startsWith("https://trusted.example")` are wrong because they also match `https://trusted.example.evil.example`. Host checks like `endsWith("example.com")` can mistakenly accept `notexample.com`. If business rules truly require external origins, normalize the URI and validate **scheme + exact host + port + empty userinfo + redirect policy** against an approved list; never use string-concatenation tricks.

## 3. Where Does Spring Security Decide Post-Form-Login Redirects?

A typical form login:

~~~text
Browser
    |
    |  POST /login, username/password, CSRF token
    v
FilterChainProxy -> SecurityFilterChain
    |
    v
UsernamePasswordAuthenticationFilter
    |    creates unauthenticated UsernamePasswordAuthenticationToken
    |    -> AuthenticationManager / AuthenticationProvider
    |
    +-- failure: failure handler, typically /login?error
    |
    +-- success:
         updates SecurityContext + session strategy/repository per config
         AuthenticationSuccessHandler decides response
             -> 302 Location: <permitted target>
~~~

**`AuthenticationSuccessHandler`** is the right extension point when an app defines its post-login redirect policy. It receives request, response, and the authenticated `Authentication`; password verification **has already been performed by the provider** before the success handler runs. Never mark a request authenticated yourself just to trigger a redirect.

APIs to distinguish:

- `formLogin(login -> login.defaultSuccessUrl("/app", true))`: sets a **fixed target** with `alwaysUse` enabled, so `SavedRequest` does not take priority. Ideal when all users should land on `/app`.
- `defaultSuccessUrl("/app")` (without `true`): by default still **restores the pre-login request** via `SavedRequestAwareAuthenticationSuccessHandler`; it does not always redirect straight to `/app`.
- `successHandler(customHandler)`: takes full control of success handling; when writing your own, you must explicitly govern `RequestCache`, destinations, and responses. Do not assume a custom handler automatically keeps the old `SavedRequest` behavior.
- `targetUrlParameter`: a feature allowing a parameter name to specify the destination on certain handlers; if configured carelessly, it opens a channel for client-controlled URLs. Never enable it and trust raw request values.
- `useReferer`: `Referer` may be absent or untrusted. Never use it as an unverified redirect URL source.
- `failureUrl("/login?error")` and `logoutSuccessUrl("/login?logout")`: should use fixed routes or similar allowlists. Redirect policy applies outside the success branch too.

Spring Security includes many built-in safeguards, yet **you must not assume every custom success handler is safe**. In particular, calling `response.sendRedirect(request.getParameter("next"))` feeds client input directly into navigation decisions.

### What Is `SavedRequest`?

If an unauthenticated user visits `GET /orders`, the security entry point can store a `SavedRequest` in `RequestCache` and direct the user to the login page. After success, the default `SavedRequestAwareAuthenticationSuccessHandler` can redirect back to the saved request.

~~~text
GET /orders (unauthenticated)
  -> /login
  -> POST /login (succeeds)
  -> /orders (restores request, if policy/handler uses SavedRequest)
~~~

Restoration helps UX, yet remember that the original request is still client-originated input. Apps behind reverse proxies, forwarded headers, or multiple hosts must avoid trusting unverified `Host`/`X-Forwarded-*` headers when reconstructing URLs. If business rules allow **only** a few post-login destinations, you can **discard `SavedRequest`** and redirect strictly to an internal allowlist, as shown in section 5.

## 4. Three Safe Strategies by Complexity

### Option A — One Fixed Target, Fewest Branches

If every user should go to a single main screen:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(form -> form
            .defaultSuccessUrl("/app", true)
            .permitAll());
    return http.build();
}
~~~

This is a **code fragment** for a `@Configuration` class needing `HttpSecurity`, `SecurityFilterChain`, and `@Bean` imports. Because `true` enforces always using the default target, the handler ignores any `next` parameter. The app needs a handler/controller for `GET /app`. This keeps **authentication** and **authorization** intact; it only constrains **where the browser goes after successful login**.

When deploying under a non-root context path, verify the resulting URL and configure `RedirectStrategy`/reverse proxy settings to avoid wrong prefixes. Never assemble protocol/host manually from client headers.

### Option B — Limited Choices via a **Navigation Key**

When users can land on `/app`, `/orders`, or `/profile`, accept a **key** such as `home`, `orders`, or `profile` and let server code map it. Never accept raw URLs:

~~~text
Client: destination=orders
Server: "orders" -> "/orders"

Client: destination=https://evil.example/
Server: unknown key -> "/app"
~~~

This is safer than parsing free-form URL strings because targets are predefined. Pick keys strictly per app requirements rather than creating so many keys that the allowlist becomes unmanageable.

### Option C — Dynamic Internal URLs with Strict Validation

Use only when genuinely required. For example, to return users to individual order pages, accept an **order ID**, verify permissions, and construct the path **on the server**:

~~~text
Client: orderId=12345
Server: validate ID, authenticated user, and permission to view order 12345
Server: construct path "/orders/12345" using standard URL builder/escaping
~~~

Never let clients send `returnUrl=/orders/12345?redirect=https://evil.example` and forward the raw string. Checking authorization on resource IDs is equally vital: a URL may be same-site yet point to a resource the user is forbidden to view. If using opaque state to preserve destinations across multi-step login/SSO, sign or bind state to the session with expiration, nonce, and allowlist policy; Base64-encoding a URL does not make it trustworthy.

**Recommendation for internal form login:** prefer A when there is one destination, B when there is a small approved set; C requires clear business justification plus extra testing and monitoring.

## 5. Complete Spring Boot Example Using Option B: Destination Key Only

The example uses **one security chain**, an in-memory user for testing, and internal routes. In production, replace the demo user with a real user store and secret policy; **never** hardcode passwords. Dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`; tests use `spring-boot-starter-test` and `spring-security-test`.

Assuming package `com.example.safeformlogin` on Java 17+, with the classes below scanned by `@SpringBootApplication`. The demo uses Spring Security's default form login at `GET /login`. The generated form **has no destination field**, so normal browser flows go to `/app`. To send a destination from a custom UI, a custom form can add a hidden `destination=orders` field, while still treating that value as **untrusted** because clients can tamper with it.

### 5.1. `AllowlistedLoginSuccessHandler.java`

~~~java
package com.example.safeformlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.DefaultRedirectStrategy;
import org.springframework.security.web.RedirectStrategy;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;

public final class AllowlistedLoginSuccessHandler
        implements AuthenticationSuccessHandler {

    private static final String DEFAULT_PATH = "/app";

    private static final Map<String, String> ROUTES = Map.of(
            "home", "/app",
            "orders", "/orders",
            "profile", "/profile"
    );

    private final RequestCache requestCache;
    private final RedirectStrategy redirectStrategy =
            new DefaultRedirectStrategy();

    public AllowlistedLoginSuccessHandler(RequestCache requestCache) {
        this.requestCache = requestCache;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) throws IOException {

        String suppliedKey = request.getParameter("destination");

        // Map.of does not accept null keys: check first.
        String target = suppliedKey == null
                ? DEFAULT_PATH
                : ROUTES.getOrDefault(suppliedKey, DEFAULT_PATH);

        // Example policy: do not restore SavedRequest URLs.
        // Remove old saved request so it is not reused later.
        requestCache.removeRequest(request, response);

        // Only literal paths in ROUTES/DEFAULT_PATH reach this point.
        redirectStrategy.sendRedirect(request, response, target);
    }
}
~~~

**Why does this handler prevent open redirects via `destination`?**

- Request input is used **solely** as a lookup key in the server's `Map`; it is never placed directly into `Location`.
- Values like `https://evil.example`, `//evil.example`, `%2F%2Fevil.example`, `javascript:...`, or unknown strings **do not** match any valid key ⇒ fall back to `/app`.
- Permitted values map to **fixed paths** starting with a single `/`, carrying no client scheme/host and no unexpected query string.
- `RequestCache.removeRequest(...)` makes the design explicit: **never** restore unapproved saved URLs. If an app wants `SavedRequest` restoration, it must implement an explicit policy rather than dropping this call and assuming it is safe.
- `DefaultRedirectStrategy` performs the framework's redirect; it does not magically sanitize arbitrary client URLs. The `target` input must already be an approved destination.

**Notable property:** If an attacker sends `destination=admin`, it goes to `/app` because `admin` is not a valid key. If one day you add `"admin" -> "/admin"`, adding the route does not grant admin permissions: authorization for `GET /admin` must still be enforced in filters/controllers. The **redirect policy** and **authorization policy** complement each other without replacing one another.

### 5.2. `SecurityConfig.java`

~~~java
package com.example.safeformlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // For learning/testing only. Do not place real credentials in source.
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("training-only"))
                .roles("LEARNER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    RequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    AuthenticationSuccessHandler safeLoginSuccessHandler(
            RequestCache requestCache) {
        return new AllowlistedLoginSuccessHandler(requestCache);
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            AuthenticationSuccessHandler safeLoginSuccessHandler,
            RequestCache requestCache) throws Exception {

        http
            .requestCache(cache -> cache.requestCache(requestCache))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .successHandler(safeLoginSuccessHandler)
                .failureUrl("/login?error")
                .permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"));

        return http.build();
    }
}
~~~

In this example:

1. `formLogin(...)` uses the default filter/login page, while the **success** branch is delegated to `AllowlistedLoginSuccessHandler`.
2. `.failureUrl("/login?error")` is a fixed server target for failed logins; it does not read `destination` on failure.
3. `.requestCache(...)` shares the exact `RequestCache` that the success handler clears. This pattern intentionally avoids keeping `SavedRequest` to choose post-login targets.
4. `@Bean` methods for `UserDetailsService` and `PasswordEncoder` provide illustrative username/password storage, not part of the redirect policy itself.
5. The `/admin` endpoint has `hasRole("ADMIN")` to show that **redirecting to a path does not grant permission to access that path**.
6. Logout POST with CSRF enabled must supply a CSRF token; logout-success redirect settings do not remove CSRF obligations.

In real apps, there may be multiple `SecurityFilterChain` beans, login handlers, or reverse proxies; verify the right chain handles `POST /login`. If an API token chain accidentally matches `/login`, this success handler will not run.

### 5.3. `PageController.java`

~~~java
package com.example.safeformlogin;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/app")
    public String app() {
        return "app";
    }

    @GetMapping("/orders")
    public String orders() {
        return "orders";
    }

    @GetMapping("/profile")
    public String profile() {
        return "profile";
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
~~~

If a main class is needed for the demo project, create:

~~~java
package com.example.safeformlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeFormLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeFormLoginApplication.class, args);
    }
}
~~~

`GET /public` requires no login; `GET /app`, `/orders`, and `/profile` require an authenticated user; `/admin` requires `ROLE_ADMIN`, whereas the demo user only has `ROLE_LEARNER`.

### 5.4. Reading the Flow Correctly

~~~text
GET /orders while unauthenticated
   -> security requires authenticated
   -> request may be saved by RequestCache
   -> browser redirects to /login

POST /login (username=learner, password=training-only, valid CSRF)
   -> Spring Security verifies credentials
   -> authenticated result, session saved per configuration
   -> AllowlistedLoginSuccessHandler runs
   -> destination=orders -> Location: /orders
      destination=https://evil.example -> Location: /app
      no destination -> Location: /app
   -> clears SavedRequest since this policy does not use it

GET /orders after login with valid session cookie
   -> HTTP 200, body "orders"

POST /login wrong password
   -> failure handler -> Location: /login?error
   -> success handler is NOT called for that failed attempt
~~~

With default form login, the framework-generated HTML page sends no `destination`, so normal navigation goes to `/app`. To offer a selectable destination in the UI, you must build your own form (with proper CSRF token) or use a server-controlled entry flow. Even if the UI hides that field, attackers can modify form fields, so the allowlist must live on the server.

**You do not need to modify Spring Security to test redirect policies:** `MockMvc` can pass any `destination` parameter in tests. That directly simulates a client sending untrusted input.

## 6. Testing Real HTTP Behavior with Spring Security Test

Create `src/test/java/com/example/safeformlogin/LoginRedirectSecurityTest.java`. Test dependencies: `spring-boot-starter-test`, `spring-security-test`.

~~~java
package com.example.safeformlogin;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LoginRedirectSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validKeyRedirectsToApprovedOrdersPage() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "training-only")
                    .param("destination", "orders"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/orders"))
                .andExpect(authenticated().withUsername("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/orders").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("orders"));
    }

    @Test
    void missingKeyUsesSafeDefault() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "training-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/app"))
                .andExpect(authenticated().withUsername("learner"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "https://evil.example/path",
            "//evil.example/path",
            "https://trusted.example.evil.example/",
            "https://trusted.example@evil.example/",
            "javascript:alert(1)",
            "%2F%2Fevil.example",
            "%252F%252Fevil.example",
            "/\\evil.example",
            "../admin",
            "orders?next=//evil.example",
            "orders/",
            ""
    })
    void unapprovedValueCannotInfluenceRedirect(String supplied)
            throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "training-only")
                    .param("destination", supplied))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/app"))
                .andExpect(authenticated().withUsername("learner"));
    }

    @Test
    void badCredentialsDoNotUseSuccessRedirect() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "incorrect")
                    .param("destination", "orders"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void formLoginRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "learner")
                    .param("password", "training-only")
                    .param("destination", "orders"))
                .andExpect(status().isForbidden());
    }
}
~~~

Tests use real `post("/login")` requests through the servlet security filter chain with `.with(csrf())` to simulate valid form POSTs, rather than disabling CSRF in config. After authentication, `redirectedUrl(...)` checks **the returned target**, and `authenticated()` confirms the success branch actually established a Spring Security-authenticated principal.

The final test verifies that login POSTs **without a CSRF token** are blocked in the demo setup; that checks an independent protection layer separate from redirect policy.

**Why do bad-input tests still assert `authenticated()`?** Because the username/password in those tests are valid. What must be denied is **control over the redirect address**, not necessarily rejecting a legitimate user merely for submitting an unapproved destination field. This example policy falls back to `/app`. If business rules require failing the entire request on an invalid key, you can return an explicit error instead, provided it is defined and tested consistently.

**Also check `Location` under HTTPS/reverse proxies:** in root-context tests, `redirectedUrl("/orders")` represents an internal route. In deployments with context paths, forwarded headers, and reverse proxies, assert the final URL per actual config, including accepting only trusted hosts.

Run in a project with test dependencies installed:

~~~bash
./mvnw test
~~~

On Windows PowerShell, typically run `.\mvnw.cmd test`. Build output varies by tool and environment; no fixed stdout is shown. To run the demo server:

~~~bash
./mvnw spring-boot:run
~~~

Note: in production do not use the in-memory `learner/training-only` user; passwords here are test data only.

## 7. Standalone Java 17: Verifying Redirect Decision Correctness

The server-side allowlist logic can be understood without Spring libraries. Create `RedirectPolicyDemo.java`:

~~~java
import java.util.Map;

public final class RedirectPolicyDemo {

    private static final String SAFE_DEFAULT = "/app";

    private static final Map<String, String> DESTINATIONS = Map.of(
            "home", "/app",
            "orders", "/orders",
            "profile", "/profile"
    );

    static String resolve(String key) {
        if (key == null) {
            return SAFE_DEFAULT;
        }
        return DESTINATIONS.getOrDefault(key, SAFE_DEFAULT);
    }

    static void print(String supplied) {
        String display = supplied == null ? "<missing>" : supplied;
        System.out.println(display + " -> " + resolve(supplied));
    }

    public static void main(String[] args) {
        print("orders");
        print("home");
        print("https://evil.example/path");
        print("//evil.example");
        print("%2F%2Fevil.example");
        print(null);
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac RedirectPolicyDemo.java
java RedirectPolicyDemo
~~~

**Exact** stdout:

~~~text
orders -> /orders
home -> /app
https://evil.example/path -> /app
//evil.example -> /app
%2F%2Fevil.example -> /app
<missing> -> /app
~~~

This program **only decides a path**; it performs no HTTP redirects, creates no sessions, verifies no passwords, and uses no Spring Security APIs. It demonstrates the principle: clients choose **one key from a server-defined set**, rather than arbitrary URLs. The exact same mapping can be unit-tested standalone and reused inside the success handler.

## 8. When Must You Validate Internal URLs Yourself?

Occasionally an app must preserve a dynamic path such as `/orders/123?tab=history`. When not using navigation keys or server-constructed IDs, a strict redirect policy must guard against **all URL parsing interpretations**.

Common requirements to permit only *local paths*:

1. The value starts with **a single** `/`, never `//`.
2. No scheme, host, userinfo, or port.
3. Contains no `\`, CR/LF, NUL, or ASCII control characters.
4. Contains no `..` path traversal or encoded variants that resolve to traversal after normalization/decoding.
5. Handle percent-encoding consistently across all layers; never validate once and let another layer decode a second time into `//` or `../`.
6. Enforce that routes match a **tightly defined** list of path prefixes/patterns. Do not use boundary-less `startsWith("/admin")` or `startsWith("/orders")` when paths differ in meaning; `/orders-admin` is not under `/orders/`.
7. Validate query parameters against an allowed schema. Never blindly allow nested `returnUrl` or `redirect` params to chain into another handler.
8. If the route targets a specific resource, enforce access permissions; redirect policy **does not** replace authorization.

With `java.net.URI`, parsing helps extract scheme, authority, path, and query, yet **URI parsing alone does not prove safety**. Browsers and reverse proxies normalize inputs differently, especially around backslashes, percent-decoding, and Unicode. Therefore, applications without dynamic URL needs should pick a *key → literal path* allowlist instead of introducing a complex, hard-to-verify custom URL parser.

If approved external origins are mandatory (e.g., specific corporate domains), store exact origins in server config, enforce HTTPS, canonical/IDNA hostnames, exact ports, empty userinfo, no unexpected schemes, and allowed paths/queries; use battle-tested libraries and dedicated tests. Never match string prefixes or trust `Referer`.

### Redirecting with Query Parameters or IDs: Safe Construction

Instead of accepting `/orders/123?returnTo=https://evil.example`, accept `orderId=123`, parse it as a supported number/UUID, verify the user is authorized to view that order, and build:

~~~java
String safePath = "/orders/" + orderId;
redirectStrategy.sendRedirect(request, response, safePath);
~~~

This is an **illustrative snippet**, not standalone: `orderId` must already be format-validated and authorized; `redirectStrategy` is the Spring Security component available in the handler. If an ID can contain special characters, properly URL-encode the *path segment* via a URI builder rather than raw string concatenation. With strictly parsed integer IDs, constructing the path from the validated number is simpler and keeps arbitrary client URLs out of redirects.

## 9. Watch Out for `RequestCache`, `Host` Headers, and Reverse Proxies

If you still want the "return after login to the page the user tried to open" feature:

- `SavedRequestAwareAuthenticationSuccessHandler` and `HttpSessionRequestCache` are the standard components supporting this flow.
- Use them only with URLs validated under deployment-appropriate local/same-origin rules, never arbitrary request URLs manipulable by attackers via proxies/`Host` headers.
- Apps behind proxies need an accurate list of valid hosts and **trusted proxies**. Never blindly trust `X-Forwarded-Host` or `Forwarded` sent by Internet clients.
- If an app serves multiple hostnames (admin/internal/public) or different context paths, check both the authority and where the browser will be redirected.
- With multiple security chains, clarify which chain writes/reads the request cache and which handles login.
- If policy demands always landing on the dashboard, use `defaultSuccessUrl("/app", true)` or a safe success handler with explicit `removeRequest`. Never leave an old `SavedRequest` sitting around to trigger unexpectedly later.

**One test worth adding:** start with an unauthenticated request to `/orders` to create a saved request, then log in with an invalid `destination`. Under section 5's policy, the destination must still be `/app`; if it redirects using an unapproved `SavedRequest`, the handler or request cache violates expectations. Also test this across session expiration, login retries, and multiple tabs.

### Open Redirects via Login Failure / Logout / OAuth2

Do not test `successHandler` alone:

- If a failure handler reads `errorRedirect` from the client, apply an equivalent allowlist; default to a fixed URL.
- If logout success is configured to accept `postLogoutRedirect`, never let clients redirect to arbitrary hosts.
- With OAuth2/OIDC, `redirect_uri` and post-logout redirect URIs usually follow strict identity provider rules; never turn `state`/callback URLs into an open redirect by accepting arbitrary app URLs. That is a different topic from form login, yet shares the same trusted-target principle.
- If a frontend SPA router reads a `next` query param to navigate, check **client-side redirects** as well, not only Spring Security's `Location` header.

## 10. Anti-Patterns to Catch in Code Reviews

### Wrong: Passing `next` Directly to `Location`

~~~java
String next = request.getParameter("next");
response.sendRedirect(next);
~~~

This is an **unsafe anti-pattern**. It can permit external absolute URLs, network-path references, or parser differentials; never ship this to production.

### Wrong: Checking Only That It Starts with a Single Slash

~~~java
if (next.startsWith("/")) {
    response.sendRedirect(next);
}
~~~

`//evil.example` also starts with `/` and can be treated by browsers as a URL to another host. This is only an **anti-pattern**, not safe validation.

### Wrong: Accepting Any String Containing a Trusted Domain

~~~java
if (next.contains("trusted.example")) {
    response.sendRedirect(next);
}
~~~

A URL containing `trusted.example` in its path, userinfo, or spoofed subdomain does not mean the actual host is allowed. Avoid substring domain checks; for internal-only apps, external URLs are unnecessary to begin with.

### Wrong: Trusting the `Referer` Header to Return to the Previous Page

`Referer` can be stripped by policy, spoofed by user agents, or altered by other flows/software, and may itself point off-site. Never pass raw `request.getHeader("Referer")` into `Location` inside a login handler.

### Wrong: Validating First and Decoding Again Later

If validation sees `%2F%2Fevil.example` and lets it pass, and then later code or another layer decodes it to `//evil.example` before redirecting, the policy is bypassed. Multi-pass decoding/normalization designs are error-prone; key allowlists avoid this entire bug class.

### Wrong: Dropping Security Layers Just to Test Redirects

Never disable CSRF just to make `POST /login` tests run. Never switch `/admin` to `permitAll` just to test redirecting there. Never allow plaintext passwords in production tests. A valid HTTP 302 does not prove the principal was authenticated; tests must assert both authentication and follow-up endpoint behavior.

## 11. Complete Pre-Release Test Plan

| Test group | Input / scenario | Expectation |
| --- | --- | --- |
| Valid target | `destination=orders` | Valid login, `302 Location: /orders`. |
| Remaining targets | `home` / `profile` | Only declared paths. |
| Missing target | No `destination` | Redirect `/app`. |
| External absolute URL | `https://evil.example` | Does not leave site; falls back to `/app`. |
| Scheme-relative | `//evil.example` | Does not switch to external host. |
| Userinfo / spoofed domain | `https://trusted.example@evil.example` | Rejected. |
| Encodings | `%2F%2F...`, double-encoded, backslash | Not treated as a valid route. |
| Case sensitivity, whitespace | `Orders`, ` orders ` | Do not implicitly broaden allowlist without defined policy. |
| Very long destination | Thousands-of-characters string | Not echoed into `Location` or logs; server enforces request-size limits. |
| Invalid credentials | Wrong password + `destination=orders` | Fixed failure branch, no success redirect. |
| Missing/invalid CSRF | Login POST without CSRF token | Blocked per CSRF policy. |
| Login session | Valid login, then GET permitted path | Right principal present; GET succeeds. |
| Insufficient permissions | Redirect to internal path needing another role | Authorization still denies; redirect is not permission. |
| Existing `SavedRequest` | GET protected path → login | Follows policy: either validated restoration or fixed target. |
| Logout | Successful logout | Uses only permitted logout-success routes. |
| Proxy / Host | Untrusted `Host`/forwarded headers | Clients cannot alter `Location` to unexpected hosts. |
| Multiple security chains | Form chain + API chain | Login POST enters right chain without another handler bypassing policy. |

Good tests verify **both** HTTP outputs and security semantics. For example, a `302` response can still be an open redirect if `Location` is wrong. Conversely, a `403` does not prove redirect policy works because CSRF may have blocked the request before it ever reached the handler. Tests should supply valid passwords **and** CSRF to exercise the success path.

When adding property-based/fuzz tests, you can generate Unicode strings, percent-encodings, slashes, very long paths, and control characters; still bound test resources and avoid logging malicious inputs. With a map-key policy, the expected invariant is simple: **every key outside the allowed set lands on `/app`**.

## 12. UX and Business Requirements

Preventing open redirects does not have to hurt usability:

- If most users land on one dashboard, a fixed URL is sufficient and easy to test.
- If choosing among a few screens is needed, use server-side keys like `orders`/`profile`.
- If remembering a pre-login blocked route is required, define `SavedRequest` policy clearly: allow app routes, validate proxy/host setup, avoid storing malicious URLs, and test in the real deployment.
- For error notices, keep `/login?error` or a fixed error route, avoiding revealing whether usernames exist or passwords were wrong.
- If an SPA frontend needs post-login routing, the server can return **a route enum/key** for the frontend to map to an internal route; never return arbitrary client URLs.

You can display friendly UI copy like "After signing in, continue to Orders," yet **UI text is not a security control**. Server-side enforcement is mandatory for every request, including `curl`, browser DevTools, or custom clients.

## 13. Quick Review Checklist

- [ ] Audit every use of `sendRedirect(...)`, `RedirectStrategy`, `Location`, `targetUrlParameter`, `SavedRequestAwareAuthenticationSuccessHandler`, `Referer`, and `next/returnUrl/redirect` parameters.
- [ ] Never use raw request URLs/hosts directly as redirect destinations after login, failure, or logout.
- [ ] For a single target, configure `defaultSuccessUrl("/app", true)` or a static handler.
- [ ] For multiple targets, use a server-side **key → literal internal path** allowlist.
- [ ] Keep `RequestCache` verified against policy, or clear it when unused.
- [ ] Keep CSRF enabled for cookie/session-based form login when required by the threat model.
- [ ] Keep authn/authz checks enforced; login success does not grant access to every page.
- [ ] Test external URL variants, encodings, missing/unknown destinations, wrong passwords, and CSRF.
- [ ] Test context paths, forwarded headers, and host allowlists when deploying behind proxies.
- [ ] Never put session IDs, access tokens, raw passwords, hashes, or sensitive data into redirect URLs or logs.
- [ ] Add regression tests whenever adding new handlers or routes later.

## 14. Self-Review Questions

**Q1. Why is `next=//evil.example` dangerous even though it starts with `/`?** Because `//host/path` is a scheme-relative URL with an authority in many browser contexts, capable of redirecting to another host. Checking `startsWith("/")` is insufficient.

**Q2. How does `defaultSuccessUrl("/app", true)` differ from the version without `true`?** Passing `true` enforces always using the fixed destination without prioritizing `SavedRequest`. Without `true`, the default handler can restore a pre-login saved URL.

**Q3. Why is using a `Map` key in `AuthenticationSuccessHandler` better than forwarding raw URLs?** Because the server defines the entire set of final targets; unmatched inputs cannot introduce new hosts, schemes, or paths.

**Q4. Is `SavedRequest` completely trustworthy just because Spring Security created it?** No. It originates from the client request and can be influenced by proxies/hosts/paths. Clear policy and deployment trust boundaries are required.

**Q5. On a failed login with `destination=orders`, should the user be redirected to `/orders`?** No. The failure branch must use the failure handler; the example returns fixed `/login?error`.

**Q6. If redirect policy allows `/orders`, what happens to a user who lacks permission to view `/orders`?** The redirect may still happen, yet the follow-up `GET /orders` goes through authorization; a redirect allowlist does not replace permission checks.

**Q7. Why do tests need `.with(csrf())`?** So the form POST passes the CSRF layer validly and actually exercises the success handler. Without CSRF, a `403` only reflects `CsrfFilter` rejecting the request.

**Q8. Is `response.sendRedirect(request.getParameter("next"))` safe if the app runs strictly over HTTPS?** No. HTTPS protects the transport channel; it does not turn a client-supplied URL into an allowed destination.

**Key takeaway:** **Post-login redirect targets are a server-side security decision.** Prefer a **fixed URL** or an **allowlisted navigation key**, clearly separate `SavedRequest` from custom success handlers, keep CSRF and authorization enabled, and verify both `Location` outputs and authenticated state in integration tests.
