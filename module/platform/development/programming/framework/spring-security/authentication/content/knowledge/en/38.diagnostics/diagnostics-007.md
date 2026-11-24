# Redirect Loops Caused by Login Endpoint, Error Page, or Matchers

> **Topic:** Diagnosing HTTP 3xx redirect loops in Spring Security Servlet — especially when **GET login page**, **/error page**, **ERROR/FORWARD dispatchers**, **request matchers**, or **`SecurityFilterChain`** are misconfigured. This lesson uses Java 17+, Spring Boot 3.x, and Spring Security 6.x; it separates standalone examples from configuration snippets meant to go into a project. The goal is not eliminating redirects by opening up the whole app, but pinpointing **the first request violating expectations** and fixing the right authorization boundary.

## 1. Phenomenon and Diagnostic Goal

A redirect loop occurs when the browser receives 301/302/303/307/308 responses and keeps following the `Location` header, yet the chain never reaches a stable final page.

~~~text
GET /private        -> 302 Location: /login
GET /login          -> 302 Location: /login
GET /login          -> 302 Location: /login
Browser             -> Too many redirects
~~~

Here, `GET /private` requiring login is normal; **`GET /login` for an unauthenticated user redirecting back to itself** is the fault. A more complex sequence:

~~~text
GET /private        -> 302 Location: /login
GET /login          -> 500: template/view rendering error
ERROR dispatch      -> /error
/error              -> 302 Location: /login
GET /login          -> 500 again, ERROR /error again...
~~~

And a situation that looks similar yet differs in nature:

~~~text
POST /login         -> 302 Location: /dashboard
GET /dashboard      -> 302 Location: /login
GET /login          -> 200, browser shows form
User submits again  -> same cycle
~~~

The last situation is often called a **login bounce**, which can result from losing `SecurityContext`/session/cookie or incomplete MFA, not necessarily an infinite 302 loop within one GET chain.

**After this lesson**, you should be able to distinguish: a protected login page, a login processing URL not intercepted by the form filter, a view error leading to a locked error handler, wrong chain matchers, missing cookies/sessions, and wrong proxy/SSO redirects. You will know how to collect traces, fix configurations, and write tests confirming no new vulnerabilities are introduced.

## 2. How Spring Security Generates Redirects to Login

~~~text
Browser anonymous GET /private
       |
       v
FilterChainProxy selects SecurityFilterChain
       |
AuthorizationFilter requires authenticated
       |
AccessDeniedException
       |
ExceptionTranslationFilter
       |
AuthenticationEntryPoint (usually LoginUrlAuthenticationEntryPoint)
       |
HTTP 302 Location: /login
       |
Browser GET /login
       |
       +-- permit /login -> MVC renders login -> 200
       |
       +-- /login also requires authenticated
                  |
            AuthenticationEntryPoint
                  |
              302 /login -> LOOP
~~~

Components and responsibilities:

| Component | Role | When Does It Cause a Loop? |
| --- | --- | --- |
| `FilterChainProxy` | Picks a filter chain from the ordered list | Login request enters an unexpected chain |
| `http.securityMatcher(...)` | Selects scope of **the entire chain** | Form-login filter never receives the `/login` path |
| `authorizeHttpRequests().requestMatchers(...)` | Defines rules **within the selected chain** | Anonymous users cannot access login/error |
| `AuthorizationFilter` | Enforces rules on requests and dispatches | `FORWARD`/`ERROR` gets denied |
| `ExceptionTranslationFilter` | When anonymous is denied, invokes entry point | Redirects even when the request is `/login` |
| `LoginUrlAuthenticationEntryPoint` | Sends browser to the login page | Target is itself blocked or controller redirects itself |
| `UsernamePasswordAuthenticationFilter` | Handles POST matching `loginProcessingUrl` | Form POSTs to a route not matching the filter |
| `AuthenticationFailureHandler` | Decides response for invalid credentials | Failure URL cannot be displayed |
| `AuthenticationSuccessHandler` | Chooses landing URL/saved request | Success target lacks permission/context |
| `SecurityContextRepository` | Persists authenticated context | Request after login is treated as anonymous |
| `RequestCache` | Stores original request to resume after login | Saved request is wrong or custom handler is unsafe |

**Do not conclude 302 means login succeeded.** A 302 can come from an entry point, success handler, failure handler, MVC controller, view resolver, proxy, or IdP. The first diagnostic check is inspecting `Location` and the request method.

## 3. Most Common Cause: Custom Login Page Is Protected

### Suspicious Configuration

~~~java
@Bean
SecurityFilterChain broken(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .formLogin(form -> form.loginPage("/login"))
            .build();
}
~~~

In a project with a custom `GET /login`, if the actual rules or chain do not permit anonymous users on that URL, the entry point sends the user to `/login` only to hit the authentication requirement again. Some `formLogin` setups permit related URLs automatically when calling `.permitAll()`, yet **you should not assume every chain/controller is permitted**. Always test the actual GET page.

### Properly Scoped Fix

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error",
                                "/css/**", "/js/**", "/images/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .failureUrl("/login?error")
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .build();
    }
}
~~~

This is a **configuration snippet for a Spring project**, not standalone Java runnable with `javac`. There must be an app-rendered `GET /login`, a `/dashboard` endpoint, a user store/password provider, and a POST form with valid CSRF. Public rules are restricted to login, error, and static assets; all other routes still require authentication.

**Notes:**

- `formLogin().loginPage("/login")` uses a **custom page**. Spring Security no longer generates its default HTML login page in the usual way; the app must implement the matching GET handler.
- `POST /login` is typically handled by `UsernamePasswordAuthenticationFilter` when `loginProcessingUrl` matches; no separate MVC POST controller is needed.
- `requestMatchers("/login?error")` is **not** a reliable way to permit the failure page; query strings are not paths. Match path `/login` and read the `error` query param in the UI.
- `.defaultSuccessUrl("/dashboard", true)` picks a fixed success target for the demo. It does not fix lost sessions; it merely makes happy-path tests deterministic.
- Never use `.anyRequest().permitAll()` or `web.ignoring("/**")` to break a loop because they weaken the system.

## 4. `GET /login` and `POST /login`: Two Different Owners

| Request | Typical Handler | What to Check |
| --- | --- | --- |
| Anonymous `GET /login` | App-provided MVC controller/template if custom `loginPage` | Does controller/view really exist? Is it public? |
| `POST /login` | `UsernamePasswordAuthenticationFilter` per `loginProcessingUrl` | Path, method, CSRF, username/password fields |
| `GET /login?error` | Same GET `/login` path with query | Can the public error page render? |
| `GET /dashboard` | Protected MVC route | Are `Authentication`/session present after login? |
| `GET /error` or `ERROR` dispatch | Spring Boot error controller / custom error renderer | Is the security entry point redirecting it back to login? |

If you configure custom `loginPage("/signin")` while the HTML form POSTs to `/login` and `loginProcessingUrl("/authenticate")`, the filter will not intercept the POST. The app may return 404/405, authorize it as a regular request, or dispatch to `/error`, making the browser think the password is always wrong.

~~~java
.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/authenticate")
        .failureUrl("/signin?error")
        .permitAll())
~~~

With the snippet above, the app must serve **GET /signin** and the form must submit **POST /authenticate**. By default input names are `username` and `password` unless configured otherwise. With cookie-based forms, POST requires a valid CSRF token.

**If `GET /login` = 404:** check controllers and templates; do not edit `PasswordEncoder`.  
**If `POST /login` = 403:** check CSRF or access rules; do not immediately blame a wrong password.  
**If `POST /login` = 302 `/login?error`:** now inspect auth errors and handlers (still not guaranteed the provider ran if a custom handler is involved).

## 5. `/error` and `ERROR`/`FORWARD` Dispatch: Root Bug Masked by Redirect

In Spring Boot, when a controller/template throws an error, the container can dispatch to `/error` under `DispatcherType.ERROR`. Spring Security's `AuthorizationFilter` applies across multiple dispatcher types, not only `REQUEST`.

~~~text
GET /login
   -> ViewResolver encounters missing template
   -> exception
   -> servlet ERROR dispatch /error
   -> AuthorizationFilter: anonymous forbidden on /error
   -> LoginUrlAuthenticationEntryPoint: 302 /login
   -> GET /login hits view error again
   -> LOOP
~~~

You must fix **two layers**: configure the error page/dispatch properly, and fix the **root cause** such as a missing template, controller bug, or wrong view path.

### Intentional `ERROR`/`FORWARD` Configuration

~~~java
import jakarta.servlet.DispatcherType;

@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .dispatcherTypeMatchers(
                            DispatcherType.ERROR,
                            DispatcherType.FORWARD).permitAll()
                    .requestMatchers("/login", "/error",
                            "/css/**", "/js/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .loginPage("/login")
                    .permitAll())
            .build();
}
~~~

This is an **alternative to the corresponding `web(...)` bean config**, not a second `web(...)` bean with overlapping rules. Spring Boot 3 uses `jakarta.servlet.DispatcherType`; do not copy `javax.servlet.DispatcherType` from Boot 2.

Explanation:

- `dispatcherTypeMatchers(ERROR, FORWARD).permitAll()` permits internal dispatches needed to render errors/views by design.
- `requestMatchers("/error").permitAll()` allows GET access to the error handler path.
- `GET /admin` with dispatcher `REQUEST` **still requires authentication** under `anyRequest().authenticated()`.
- Not every app wants all `FORWARD` dispatches permitted; consider scoping to specific endpoints/error renderers if your threat model requires it.
- If your error handler itself returns `redirect:/login` for all errors, it can still loop even after `/error` permissions are fixed. Check MVC handlers and proxies, not only `AuthorizationFilter`.

Sometimes the initial response is 500 while the browser ends up seeing 302. Read exception logs, request IDs, `DispatcherType.ERROR`, and `Location` at each hop so you do not mistake it for a credential error.

## 6. `securityMatcher` and `requestMatchers` Do NOT Mean the Same Thing

**`securityMatcher`** chooses whether a `SecurityFilterChain` runs for a request at all. **`requestMatchers`** inside `authorizeHttpRequests` only chooses an authorization rule **after that chain has already been selected**.

~~~java
@Bean
SecurityFilterChain scoped(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/secured/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .loginPage("/login")
                    .loginProcessingUrl("/login"))
            .build();
}
~~~

In this example `/login` **falls outside `/secured/**`**, so the entire chain never runs for GET/POST `/login`. Adding a `permitAll` rule **inside that chain** does not pull `/login` into the chain. The `POST /login` endpoint handled by this chain's form-login filter is also unavailable outside `securityMatcher`. Depending on other chains/controllers, the result can be 404, 403, or a redirect chain — **not necessarily a 302 loop**.

### Comparison Table

| Configuration | Scope | Test to Run |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Chain applies to `/api/**` | Do API requests enter the right chain? |
| `authorize.requestMatchers("/api/public").permitAll()` | Rule inside the selected chain | Was it intercepted by an earlier chain? |
| `anyRequest().authenticated()` | Catch-all within **the selected chain** | Does not protect URLs outside the chain |
| `@Order(1)` | Chain evaluated before others | Does an overly broad chain swallow `/login`? |
| Chain without `securityMatcher` | Usually fallback for remaining requests | Does it cover URLs unclaimed by earlier chains? |

If **no chain matches**, a URL can sit completely outside Spring Security's protection. That is a bigger security issue than a redirect loop; do not fix it by deleting matchers without checking coverage.

### Two-Chain Configuration With a Proper Fallback

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ChainConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error",
                                "/css/**", "/js/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .permitAll())
                .build();
    }
}
~~~

`/api/**` enters chain 1 with HTTP Basic; `/login` enters chain 2 with form login. The web chain has no restricting `securityMatcher`, so it handles requests not claimed by chain 1. Config snippets in other sections are **alternatives**; do not paste all `@Configuration` classes into one project creating colliding beans.

For a Bearer JWT API, replace HTTP Basic with OAuth2 Resource Server per contract; Basic here merely illustrates **an API that does not redirect to HTML login**. Verify anonymous `GET /api/private` returns 401 per API type rather than looping to `/login`.

## 7. Rule Order, HTTP Methods, and Query Strings

Authorization rules are evaluated in order. Place the catch-all rule **last**:

~~~java
// Clear configuration style:
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/login", "/error").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
~~~

Do not add `requestMatchers("/login").permitAll()` after `anyRequest()` expecting it to override the earlier rule; the DSL may reject it or the specific rule will not take effect as assumed.

**Query parameters differ from paths:** `/login?error` is a GET on path `/login` with query `error`. Common matchers inspect paths without queries. Never write `requestMatchers("/login?error")` to fix errors. Handle query params in the controller/template rather than opening a separate security path just because a URL has a question mark.

**GET differs from POST:** a permit rule for `HttpMethod.GET` does not automatically include POST. `formLogin().permitAll()` permits the related login endpoints per framework rules, yet you must verify the chain receives POST and a valid CSRF token. `loginProcessingUrl` must exactly match the form's `action` under URL mapping.

**Servlet path/context path:** when the app sits at `/app` or `DispatcherServlet` is mapped at `/web/*`, distinguish the external browser URL, context path, servlet path, and the path the matcher actually evaluates. Never prepend `/app` to every matcher blindly if the framework already strips context path; inspect the actual request and version-specific matcher API.

**Matcher implementations:** Spring Security evolves matcher APIs across versions; when using MVC and `PathPattern`, test paths, wildcards, and servlet mappings rather than guessing from `/**` strings. Also test trailing slashes, URL encoding, and case sensitivity if your system has special rules.

## 8. Success/Failure URLs and `RequestCache` Creating Other Loops

### Failure URL

~~~text
POST /login (wrong password)
     -> 302 /login?error
GET /login?error
     -> 302 /login
GET /login
     -> 302 /login?error
     -> ...
~~~

This loop can happen if a custom MVC controller redirects itself based on the presence/absence of `error`, a reverse proxy rewrites URLs, or a matcher guards the route. Verify directly that `GET /login` returns 200, and when `error` is present, the UI merely **renders** a generic message instead of redirecting endlessly.

### Success URL

~~~text
POST /login (right password)
     -> 302 /dashboard
GET /dashboard
     -> 302 /login
GET /login
     -> 200
~~~

In this example, the password may be right yet the authenticated context failed to persist or the browser omitted the cookie. If the user is authenticated yet lacks a role/MFA, the usual result is 403; only when the system still sees the user as anonymous or a custom handler redirects does it go back to login. Inspect `SecurityContext` on the subsequent request.

### `RequestCache`

Spring can save the original `/dashboard` request before sending an anonymous user to login, and then the success handler redirects back to that request. If the saved request is a bad/unauthorized route or a custom handler saves the wrong request, the flow can bounce.

- Inspect the saved request/redirect target in safe logs or tests.
- With `defaultSuccessUrl("/dashboard", true)`, the `true` flag forces the default destination instead of the saved request — useful for deterministic tests.
- Do not send all users to `/admin` if most only hold `ROLE_USER`.
- Never let clients specify arbitrary success URLs leading to open redirects; restrict to safe hosts/paths.
- Never put access tokens, recovery codes, or OIDC authorization codes into redirect queries.

A loop occurring even when `/login` is public can start from **an unsuitable landing URL**; never fix by making a protected landing URL `permitAll`.

## 9. Losing Session or `SecurityContext` After Login

If login POST succeeds yet the next request is anonymous again, check these causes:

| Layer | Typical Bug | Evidence |
| --- | --- | --- |
| Browser cookie | Fails to resend cookie; wrong `Path`/`Domain`/`Secure`/`SameSite` | Browser Network, `Set-Cookie`/`Cookie` (do not share raw secrets) |
| Context persistence | Custom auth sets `SecurityContextHolder` without `saveContext` | Next request is anonymous; session lacks context |
| Session fixation | Login rotates session ID yet proxy/browser keeps old cookie | Compare safe session references before/after |
| Stateless policy | Browser chain uses `SessionCreationPolicy.STATELESS` | No session created as expected |
| Multi-node | Pod A stores local session; pod B lacks it | Loops only when load balancer switches pods |
| Remember-me/OIDC | Cookie or auth request repository lost after callback | OIDC restarts login automatically |
| Partial MFA auth | Password right yet second factor still missing | Should route to `/mfa/challenge`, not private target |
| Auth exception | Session store or persistence commit fails after provider success | Audit logs provider success while login never completed |

With custom authentication on Spring Security 6, setting `SecurityContextHolder` can live for only one request. If the app handles login manually, use the matching `SecurityContextRepository` to save context:

~~~java
// Snippet inside custom login handler after full verification:
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

These variables come from your real flow; do not copy this snippet into default Spring form-login handlers. `verifiedAuthentication` must be proof verified by a provider, never constructed from `?authenticated=true` sent by the client. Session fixation protection, CSRF, MFA, timeouts, and authorization must still be designed properly.

**Never log raw `JSESSIONID` for tracking.** When correlation is needed, use a surrogate ID or HMAC reference in an access-controlled audit store. An app may also have an anonymous session for CSRF/request caching; **having a session** does not equal **successful login**.

## 10. Reverse Proxies and HTTPS Redirects Can Loop Before Spring

~~~text
Browser visits HTTPS /login
   -> Proxy terminates TLS, forwards HTTP to backend
   -> Backend thinks it is HTTP, returns 302 HTTPS /login
   -> Browser retries HTTPS, proxy forwards HTTP again
   -> Loop
~~~

Or the proxy rewrites `/app/login -> /login` while the app redirects `/login -> /app/login`. This can be a loop between **two infrastructure layers**, unrelated to `requestMatchers`.

When tracing, record:

- `http`/`https` scheme in `Location` and the request.
- Host, port, trailing slash, path prefix, context path.
- Stale cached 301/308 redirects vs temporary 302/303.
- `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix` emitted by a **trusted** proxy.
- `server.forward-headers-strategy` and actual ingress/proxy config; never pick blindly without a trust model.
- Cookie `Secure`, `SameSite`, `Domain`, `Path` across TLS termination.
- Differences between localhost and production HTTPS.

**Never trust `Forwarded` headers supplied by Internet clients.** Letting attackers control host/scheme enables malicious redirects or host-header poisoning; backends must trust only managed proxies that normalize headers.

If the browser cached a 301/308 from an old config, test with a clean/incognito profile and non-caching HTTP client before changing source code.

## 11. OIDC/OAuth2 Login Loops Need State and Callback Diagnostics

An OAuth2 Login loop typically looks like:

~~~text
GET /private
 -> /oauth2/authorization/provider
 -> IdP authorization endpoint
 -> /login/oauth2/code/provider?code=...&state=...
 -> local session/state not found
 -> /oauth2/authorization/provider
 -> IdP sends callback again
 -> ...
~~~

Common causes differ from form login:

1. `redirect_uri` at the IdP mismatches the app's scheme/host/path behind a proxy.
2. Callback fails to enter the chain with the `oauth2Login(...)` filter due to `securityMatcher`/`@Order`.
3. `OAuth2AuthorizationRequestRepository`/session saved state, yet the cookie was dropped across cross-site redirects.
4. Wrong `SameSite`, `Secure`, domain/path, load balancer, or multi-pod Spring Session.
5. Exchanging the authorization code or verifying the ID token fails, yet a custom failure handler restarts login automatically without bound.
6. IdP SSO already has a session while the local app fails to persist authenticated context, causing repeated reauthorization.
7. Callback has a trailing slash/prefix/method mismatch with the registered filter endpoint.

**Never skip `state`, nonce, PKCE, or JWT signature validation to stop a redirect loop.** Authorization codes and tokens are sensitive credentials; never paste full callback URLs or HARs containing codes/states into tickets. Redact traces and restrict access.

OIDC custom login pages also need `/oauth2/authorization/{registrationId}` URLs handled by the right chain. If the IdP login link renders fine yet the OAuth2 authorization endpoint itself is guarded or missed by the filter, the flow can bounce back to the login page.

## 12. HTTP Diagnostics From Browser and `curl`

In browser Developer Tools:

1. Open Network, enable **Preserve log**.
2. Load `/private` unauthenticated or reproduce the flow on a test account.
3. Inspect each request in order: Method, URL/path, Status, `Location`, initiator, redirect chain, and sent/received cookies (view only on the test machine).
4. Pinpoint the **first step breaking expectations**; e.g., `GET /login` returning 302 instead of 200.
5. Watch for `/error` requests, scheme changes, IdP callbacks, 403 CSRF, 404 missing routes, or 500 view errors.
6. Correlate with server request IDs and chain match logs; never share raw `Cookie`/`Authorization`/OTP/tokens.

Illustrative trace table:

| Step | Method/URL | Status | Location | Investigation Direction |
| --- | --- | --- | --- | --- |
| 1 | `GET /private` | 302 | `/login` | Valid entry point |
| 2 | `GET /login` | 302 | `/login` | Login page guarded / controller self-redirects |
| 1a | `GET /login` | 500 | ERROR `/error` | MVC/view error |
| 2a | `ERROR /error` | 302 | `/login` | Error page/dispatch guarded |
| 1b | `POST /login` | 302 | `/dashboard` | Password likely accepted |
| 2b | `GET /dashboard` | 302 | `/login` | Session/role/MFA/context |
| 1c | `POST /login` | 403 | — | CSRF/method/authorization |
| 1d | `GET /api/private` | 302 | `/login` | API likely hit the web chain by mistake |

### `curl` Commands

~~~bash
curl --silent --show-error --dump-header - \
  --output /dev/null https://portal.example.test/private

curl --silent --show-error --dump-header - \
  --output /dev/null https://portal.example.test/login
~~~

By default these two commands **do not follow redirects**, directly showing status and `Location`. To inspect the full chain, cap hops:

~~~bash
curl -v -L --max-redirs 8 \
  --output /dev/null https://portal.example.test/private
~~~

Run against authorized test hosts/environments. Never paste passwords on the command line, never use production accounts, and never share raw cookies/tokens in output. Use GET instead of `curl -I`'s default HEAD when targeting GET pages; security matchers can distinguish methods.

### Distinguishing HTTP Status Codes

| HTTP Status | What Not to Assume |
| --- | --- |
| 301/308 | May be cached by browser/proxy; not always a Spring redirect |
| 302/303 | Does not prove login succeeded |
| 307/308 | Preserves HTTP method, which can send POST to another path |
| 401 | API missing/unauthenticated credential, usually Basic/Bearer |
| 403 | CSRF or missing authority, not simply wrong password |
| 404/405 | Unhandled endpoint/method, possibly wrong login-processing chain |
| 500 | Controller/template/auth service error; error dispatch may be guarded |
| 502/503/504 | Proxy/upstream/server timeout; never relax permissions |

## 13. DEBUG Logs and `FilterChainProxy`

In test/staging environments, you can configure logging like this:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security.web.access: DEBUG
~~~

Look for:

- Which chain did `FilterChainProxy` select for `/login`, `/error`, `/dashboard`?
- Which matcher/rule did `AuthorizationFilter` use to deny GET login or ERROR dispatch?
- Which `AuthenticationEntryPoint` did `ExceptionTranslationFilter` invoke?
- Did POST login enter `UsernamePasswordAuthenticationFilter`?
- Which `Location` did the failure handler or success handler produce?
- Did `RequestCache` store an inappropriate URL or unauthorized target?
- Did the post-login request actually carry `Authentication`/context?
- Which filter chain mapped the ERROR dispatch?
- Did a proxy return a redirect before the request even reached Spring?

If TRACE is needed, enable it very briefly in a controlled environment since logs can hold sensitive metadata. **Never** log raw request bodies/passwords, JWTs, `Authorization`, cookies, session IDs, CSRF tokens, OAuth2 codes, OIDC state/nonce, or `Authentication.toString()`. Logs should carry request IDs and categories instead of secrets.

A common testing mistake is adding `@WithMockUser` on `GET /login` and seeing 200; that **does not prove anonymous users can reach it**. Always test the login page unauthenticated.

## 14. Standalone Java 17: Simulating a Redirect Graph and Loop

This snippet uses **plain JDK 17** with no Spring dependencies, sends no HTTP requests, and handles no credentials. It illustrates the logic of detecting a repeated URL in a `Location` chain.

File `RedirectLoopDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class RedirectLoopDemo {

    static String walk(Map<String, String> redirectRules, String start) {
        Set<String> seen = new HashSet<>();
        List<String> path = new ArrayList<>();
        String current = start;

        for (int hop = 0; hop < 10; hop++) {
            if (!seen.add(current)) {
                path.add(current);
                return String.join(" -> ", path) + " [LOOP]";
            }
            path.add(current);
            String next = redirectRules.get(current);
            if (next == null) {
                return String.join(" -> ", path) + " [END]";
            }
            current = next;
        }
        return String.join(" -> ", path) + " [LIMIT]";
    }

    public static void main(String[] args) {
        Map<String, String> loginGuarded = Map.of(
                "/private", "/login",
                "/login", "/login");

        Map<String, String> loginPublic = Map.of(
                "/private", "/login");

        Map<String, String> errorGuarded = Map.of(
                "/broken", "/error",
                "/error", "/login",
                "/login", "/error");

        System.out.println("login guarded: "
                + walk(loginGuarded, "/private"));
        System.out.println("login public: "
                + walk(loginPublic, "/private"));
        System.out.println("error guarded: "
                + walk(errorGuarded, "/broken"));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac RedirectLoopDemo.java
java RedirectLoopDemo
~~~

Exact stdout:

~~~text
login guarded: /private -> /login -> /login [LOOP]
login public: /private -> /login [END]
error guarded: /broken -> /error -> /login -> /error [LOOP]
~~~

**Limitations:** `walk` traverses a mock graph without checking HTTP methods, schemes, hosts, queries, cookies, authentication state, or status codes. With OIDC, each callback can carry a new `state` query parameter so full URLs differ even as the flow cycles; real investigations must **group by route and protocol step**. Never use this mock function as a reverse proxy or authorization decider.

## 15. Spring Boot 3 / Spring Security 6: Real Test Fixture

A Java 17 Maven Boot project with Boot parent/BOM needs these core dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-boot-starter-test` plus `spring-security-test` in test scope. This section consists of **multiple files in the same package**, not a single standalone file.

### File `RedirectTestingApplication.java`

~~~java
package example.redirect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedirectTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RedirectTestingApplication.class, args);
    }
}
~~~

### File `RedirectSecurityConfig.java`

~~~java
package example.redirect;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class RedirectSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(passwordEncoder.encode("local-test-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .failureUrl("/login?error")
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .build();
    }
}
~~~

`local-test-pass` is a **learning-fixture** password, BCrypt-encoded before storing in `UserDetails`; never use in real accounts. The login page and dashboard are chosen explicitly to test redirects. CSRF remains at its default.

### File `RedirectDemoController.java`

~~~java
package example.redirect;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RedirectDemoController {

    @GetMapping("/login")
    public String login() {
        return "login page";
    }

    @GetMapping("/dashboard")
    public String dashboard(Principal principal) {
        return "dashboard:" + principal.getName();
    }
}
~~~

This controller returns **plain text** to simplify route testing, **not a production HTML form**. In a real UI, `GET /login` must render a template with a POST form having the right action and CSRF. Spring's form-login filter handles `POST /login`, while the test controller handles only GET.

## 16. MockMvc: Verifying Redirect Chains and Session Continuity

File `RedirectFlowTest.java`:

~~~java
package example.redirect;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RedirectFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void privateRouteRedirectsButPublicLoginRenders() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));

        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string("login page"));

        mvc.perform(get("/login").param("error", ""))
                .andExpect(status().isOk());
    }

    @Test
    void validLoginSurvivesNextRequest() throws Exception {
        MvcResult result = mvc.perform(formLogin()
                        .user("learner").password("local-test-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/dashboard"))
                .andExpect(authenticated().withUsername("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("dashboard:learner"));
    }

    @Test
    void wrongPasswordFailsButFailurePageIsReachable()
            throws Exception {
        mvc.perform(formLogin()
                        .user("learner").password("wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());

        mvc.perform(get("/login").param("error", ""))
                .andExpect(status().isOk());
    }
}
~~~

**Why these three tests matter:**

- Anonymous `GET /dashboard` redirects to login while anonymous `GET /login` returns 200; that checks the common self-redirect guard condition.
- `/login?error` still loads, proving the failure handler does not send the browser to a locked route.
- `formLogin()` sends a POST per the Spring Security test contract with CSRF; it passes through the real filter/provider rather than bypassing with `@WithMockUser`.
- Valid login checks **the same session on the next request**; if GET dashboard redirects back to login, the test catches the persistence bug.
- Wrong password creates no `Authentication` in the flow test; failure response is clear with no infinite redirect.
- If the project changes form action/processing URL, adjust tests for the real endpoint; do not drop this fixture into OAuth2/JWT expecting the same 302s.

**Do not assert only status 302:** login success, login failure, and unauthenticated entry points can all return 302. Always assert `Location`, the subsequent GET status, and the principal.

## 17. Additional Specific Tests Needed

| Scenario | Valid Test |
| --- | --- |
| Custom login page missing GET handler | `GET /login` returns 404, not mistaken for auth failure |
| POST to wrong `loginProcessingUrl` | Creates no `Authentication`; check filter path/method |
| POST missing CSRF | 403 per CSRF policy, not counted as bad password |
| Login page view fails to render | `ERROR` dispatch renders error without looping `/error -> /login` |
| Overly broad `@Order(1)` custom chain | Which chain receives `/login` and `/api`? |
| Anonymous API request | 401 Basic/Bearer, no unexpected HTML login redirect |
| Error dispatch permitted | `DispatcherType.ERROR` request does not re-require login |
| Forward to template | View renders or errors cleanly without a guard loop |
| Session rotation | New cookie works on protected GET; old cookie is not trusted |
| Valid login missing required role | Returns 403 or authorized landing per policy |
| Partial auth / MFA | Protected resources blocked before factor 2; challenge does not loop |
| OIDC callback with different context path | Callback filter actually receives request; state and nonce verified |
| HTTPS proxy | No `https -> http -> https` loop; forwarded headers only from trusted proxy |
| Browser cached 301/308 | Test clean profile, real URL, and redirect host |
| Multi-pod session store | Post-login GET on another pod still sees authenticated context |
| Login static resources | Required CSS/JS are not redirected to login |
| Browser replays saved request | Target redirect respects authorization; no open redirect |

**MockMvc has limits with Servlet `ERROR` dispatches.** Some `/error` loops surface only when embedded Tomcat/Jetty performs a real error dispatch, so add `@SpringBootTest(webEnvironment=RANDOM_PORT)`/browser tests against a container and staging proxy when dispatch/proxies are involved. Do not treat a standalone MockMvc `GET /error` as proof the system has no error loops.

For multi-chain apps, write integration tests comparing `/login`, `/api/private`, `/error`, and callbacks under their real `@Order` rather than just checking bean presence. Verify fallthrough so no URL falls outside Spring Security entirely.

## 18. Symptom-Based Quick Diagnostic Table

| Symptom | Priority Check | Do Not Do |
| --- | --- | --- |
| `/private -> /login -> /login` | `GET /login` authorization, `loginPage` `permitAll`, MVC login | Open `anyRequest` |
| `/private -> /login -> /error -> /login` | View/controller exception + `ERROR` dispatcher | Only tweak passwords |
| `GET /login` = 404 | Missing custom controller/template or URL outside chain | Blame bad credentials |
| `POST /login` = 404/405 | Form action/`loginProcessingUrl` mismatch, chain misses it | Write a POST controller overriding filter blindly |
| `POST /login` = 403 | CSRF token, method/authorization | Disable CSRF app-wide |
| `POST /login` = 302 `/login?error` | Failure handler, provider/auth error | Assume login succeeded |
| `POST /login` = 302 `/dashboard`; `GET dashboard` = 302 login | Cookie/session/context, MFA, multi-node | Make dashboard anonymous |
| `GET /error` = 302 `/login` | Error route/dispatch guarded | Drop all authorization |
| API GET returns 302 HTML login | Chain order and authentication entry point | Use form login for all APIs |
| HTTPS loops at proxy | Scheme/host/prefix/forwarded headers | Trust `X-Forwarded-*` from Internet |
| OAuth2 reauthorizes repeatedly | Callback chain/state/cookie/`redirect_uri`/SSO | Disable nonce/state validation |
| First chain matches every path | `@Order`/`securityMatcher` | Assume later chains will run |
| Same URL works intermittently | Multi-node sessions, cache, proxy rewrites | Wipe all user sessions |
| `/login?error` and `/login` bounce back and forth | Controller redirects based on query | Create matcher containing `?error` |
| 500 turns into 302 login | `/error` dispatch guarded | Hide original exception logs |

## 19. Minimal-Change Remediation Workflow

1. Reproduce on a test account and capture a minimal 2–4 request sequence including method/status/`Location`.
2. Pinpoint the **first request violating expectations**: GET login 302 instead of 200, POST login 404, ERROR `/error` redirected, or authenticated session vanishing after login.
3. Reconcile the client URL against backend request path, servlet mapping, context path, and reverse proxy.
4. Trace filter-chain selection via `securityMatcher` and `@Order`, then inspect `requestMatchers` inside the selected chain.
5. If the login page is guarded, permit **precisely `/login` and required login endpoints** without touching private routes.
6. If `/error` is guarded, permit the error renderer and dispatcher per policy while **fixing the underlying controller/view error**.
7. If POST is missed by the filter, fix `loginProcessingUrl` or form action/method; keep CSRF intact.
8. If success bounces, inspect cookies/`SecurityContext`/session store, saved requests, and MFA state.
9. If a proxy alters scheme/host/path, fix forwarded-header trust/config and cookies without disabling TLS validation.
10. For SSO, verify `redirect_uri`/callback/state/session before letting the flow auto-restart.
11. Add regression tests for anonymous login GET, failure URL, valid POST, next-request session, error dispatch, and multi-chain routing.
12. Deploy via canary and monitor repeated redirect rates, 403 CSRF, 404 login, error-dispatcher failures, and session misses.

**Never use** `.anyRequest().permitAll()`, `csrf.disable()`, trust-all forwarded headers, or disabling session fixation protection as convenient workarounds. Stopping an endpoint from redirecting does not mean the system is properly secured.

## 20. Pre-Production Checklist

**Login Path**

- [ ] Anonymous `GET /login` or custom `loginPage` loads properly without redirecting to itself.
- [ ] `/login?error` displays a generic message without bouncing back and forth.
- [ ] POST login matches the filter/CSRF and issues a session only for valid credentials.
- [ ] Success URL/saved request respects roles and MFA state; never sends users to unauthorized routes.
- [ ] Protected GET after login uses properly persisted session/context.
- [ ] No login-processing route falls outside the `securityMatcher` of the chain holding the form filter.

**Error Page, Matchers, Proxy**

- [ ] `ERROR`/`FORWARD` dispatch has clear policy; `/error` never turns a 500 into a redirect loop.
- [ ] Specific rules precede catch-all rules; chain ordering is tested.
- [ ] Basic/Bearer APIs return API-contract auth codes instead of looping to HTML login.
- [ ] Required static assets are public without exposing private resources.
- [ ] Scheme/host/port/context path behind reverse proxy are right; only valid forwarded headers are trusted.
- [ ] OIDC authorization endpoint and callback live in the right chain with state/nonce/PKCE protection.

**QA and Observability**

- [ ] MockMvc tests cover 302 entry point, `GET /login` 200, failure URL 200, success, and next-request 200.
- [ ] CSRF 403 is tested separately, never treated as a password failure.
- [ ] Embedded server/browser tests cover `ERROR` dispatch, cookies/proxy, multi-chain, and OIDC if used.
- [ ] Request/trace IDs and debug matcher logs can be inspected without exposing credentials/session IDs.
- [ ] Post-fix verification confirms `/admin`/private/API routes did not accidentally become public.
- [ ] Alerts/monitoring track redirect cycles, login failures, 404 processing URLs, and context persistence.

**Conclusion:** A redirect loop must be solved using the **concrete HTTP sequence**, not guesswork. Spring Security redirecting anonymous users is normal, whereas redirecting **the login page itself**, **the error dispatcher**, or **the login-processing route** back to login means you need to inspect matchers and chains. If it bounces only after login, investigate `SecurityContext`/cookies/sessions, success URLs, MFA, and proxies. Fix the true root cause, keep authorization tight, and verify with consecutive requests so a UX bug never turns into an access-control hole.

## References

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Java Configuration, multiple HttpSecurity and filter chain endpoints](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Authorize HttpServletRequests, ERROR/FORWARD dispatch](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — MockMvc Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — FormLoginConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html)
- [Spring Boot — Spring MVC and error handling](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
