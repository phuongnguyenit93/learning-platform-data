# defaultSuccessUrl and Handling Successful Redirects

## 1. The Post-Form-Login Redirect Problem

When a user submits `POST /login`, Spring Security has two distinct tasks: **authenticating identity** and **deciding which page to open after authentication succeeds**. `AuthenticationManager`/`AuthenticationProvider` is responsible for checking username, password, and account status; `AuthenticationSuccessHandler` decides the next HTTP response, typically a redirect to a URL.

`defaultSuccessUrl(...)` sits inside `formLogin(...)` configuration and only sets **the redirect target upon successful login**. It does not create accounts, verify passwords, grant `ROLE_ADMIN`, or replace authorization at the target page.

Distinguish two cases:

- **Direct login:** the user intentionally navigates to `/login` from the nav bar, submits valid credentials, and wants to land on the main `/dashboard` page.
- **Login after being blocked:** the user tried to view `/orders/42` while anonymous, Spring Security prompted them to log in, and afterward they want to return to `/orders/42`.

If both cases are forced to the dashboard, the second user's workflow is interrupted. If the app always returns to the old URL, some products cannot enforce mandatory onboarding or terms-acceptance steps. **`defaultSuccessUrl` provides two overloads to choose the policy.**

### Learning Objectives

After this lesson you should be able to distinguish:

1. `defaultSuccessUrl("/dashboard")` vs. `defaultSuccessUrl("/dashboard", true)`.
2. `defaultTargetUrl`, `alwaysUseDefaultTargetUrl`, `SavedRequest`, `RequestCache`, and `AuthenticationSuccessHandler`.
3. Success redirect paths vs. `loginPage`, `loginProcessingUrl`, `failureUrl`, and logout.
4. The Browser → protected URL → login → old URL redirect flow, and why some logins land on the dashboard.
5. **Open redirect** risks when using unvalidated `next`/`returnUrl`/`Referer`.
6. How to write Spring Security 6.5.x configuration, a runnable Java 17+ example, predict stdout, and real integration testing strategies.

This lesson focuses on **Form Login** in the **Spring Security - authentication** module; it does not turn navigation into a new authentication or authorization mechanism.

## 2. Exact Meaning of the Two Overloads

Common configuration:

```java
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard"));
```

Politically equivalent to:

```java
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", false));
```

If a blocked request was saved in `RequestCache`, the default handler normally **prioritizes that request's URL**. Only when no prioritized saved request exists does it fall back to `/dashboard`.

Conversely:

```java
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", true));
```

`true` means **always use `/dashboard` upon success**, even if the session holds a prior saved request. `SavedRequestAwareAuthenticationSuccessHandler` also removes the relevant saved request when taking this forced branch.

| Option | With saved request `/reports/annual` | Without saved request |
| --- | --- | --- |
| `defaultSuccessUrl("/dashboard")` | Redirects to `/reports/annual`. | Redirects to `/dashboard`. |
| `defaultSuccessUrl("/dashboard", false)` | Redirects to `/reports/annual`. | Redirects to `/dashboard`. |
| `defaultSuccessUrl("/dashboard", true)` | Redirects to `/dashboard` and discards saved request. | Redirects to `/dashboard`. |

**Do not misread `false` as "do not redirect".** `false` means "do not force the default URL unconditionally"; it does not mean "skip the success handler".

**Do not misread `true` as automatically granting access to the dashboard.** The dashboard must still have a controller/view and a proper authorization policy for users directed there.

### Default When Unconfigured

Per `AbstractAuthenticationTargetUrlRequestHandler` in Spring Security 6.5, the initial default target is typically **`/`**. For form login, the standard handler is `SavedRequestAwareAuthenticationSuccessHandler`: if a valid saved request exists it takes priority; otherwise default-target logic applies. `/` is the application root, **not** the `/login` URL.

## 3. Why Do SavedRequest and RequestCache Exist?

Trace a request to a protected page:

```text
GET /orders/42 (unauthenticated user)
     |
     v
AuthorizationFilter: insufficient authentication
     |
     v
ExceptionTranslationFilter:
   - switches to initiating authentication
   - may ask RequestCache to save the original request
     |
     v
302 Location: /login
     |
     v
GET /login -> HTML form
     |
     v
POST /login (username/password)
     |
     v
UsernamePasswordAuthenticationFilter
     |
     v
AuthenticationManager -> authenticated result
     |
     v
SessionAuthenticationStrategy + SecurityContext
     |
     v
AuthenticationSuccessHandler
     |
     +-- saved request exists and alwaysUse=false:
     |        302 Location: /orders/42
     |
     +-- no saved request:
     |        302 Location: /dashboard
     |
     +-- alwaysUse=true:
              302 Location: /dashboard
```

`RequestCache` manages descriptions of requests awaiting restoration. The common implementation is `HttpSessionRequestCache`, storing `DefaultSavedRequest` in `HttpSession`. It is distinct from `SecurityContextRepository`, which stores `SecurityContext`/`Authentication` so subsequent requests know who is logged in.

| Component | What does it store? | Effect |
| --- | --- | --- |
| `SecurityContextHolder` | Current Authentication per context holder strategy | Code during processing reads identity. |
| `SecurityContextRepository` | SecurityContext into request/session or appropriate store | Restores authentication across requests per policy. |
| `RequestCache` | Request prior to authentication prompt | Picks the page URL to return to after login. |
| `SavedRequest` | Information about the saved request | Supplies `getRedirectUrl()` and matching data. |
| `AuthenticationSuccessHandler` | Not a data store; receives authentication result | Decides redirect, forward, or other response. |

**Note:** not every 401 response or redirect to login creates a saved request. It depends on `ExceptionTranslationFilter`, request matchers, cache configuration, and sessions. A `NullRequestCache` does not retain the original request.

### Which Requests Should Be Saved?

**GET** requests to protected resources are usually useful candidates for navigation restoration. Saving a POST with side effects does not mean the entire body is safely replayed after login; in particular, never use the request cache as a queue for money transfers, order creation, or business state mutations. Such APIs require dedicated idempotency, CSRF, action re-confirmation, and authorization.

Do not let favicons, CSS, background XHRs, or health endpoints accidentally overwrite the truly important target URL. You can configure `HttpSessionRequestCache.setRequestMatcher(...)` to choose which requests get saved per policy.

## 4. In What Order Does `SavedRequestAwareAuthenticationSuccessHandler` Choose the URL?

Spring Security 6.5.11 uses this handler in typical browser form-login scenarios. It extends `SimpleUrlAuthenticationSuccessHandler` and holds a `RequestCache` to inspect return URLs.

Key branches:

1. **`alwaysUseDefaultTargetUrl=true`:** uses `defaultTargetUrl` and clears any saved request.
2. **`targetUrlParameter` enabled and present with a value in the request:** uses that parameter to determine the target and clears any saved request. Allowing clients to specify targets requires security review.
3. **Saved request exists:** redirects to `savedRequest.getRedirectUrl()`. The saved request is normally **kept in cache at this step** so `getMatchingRequest(...)`/wrapper logic can process the browser's follow-up request after the redirect.
4. **No saved request:** falls back to base-handler logic, which may use the default URL, target parameter, or optional Referer depending on config.

| `alwaysUse` | Valid `targetUrlParameter` present | Saved request exists | Chosen target |
| --- | --- | --- | --- |
| `true` | Any | Any | **Default URL**, highest priority branch. |
| `false` | Has value | Yes/no | Target parameter per handler. |
| `false` | None | Yes | Saved request URL. |
| `false` | None | No | Default URL, or Referer if enabled. |

`targetUrlParameter` is **not enabled automatically** when you only declare `defaultSuccessUrl`. It is a handler option and can introduce an open redirect vulnerability if enabled without validation.

### Is the Saved Request Always Deleted on Successful Redirect?

**No.** When redirecting to the original saved URL, the handler may keep the entry in cache so the follow-up request can be handled by the matching wrapper. When forcing the default URL or using a target parameter, the old request is removed. Therefore, a unit test asserting that `RequestCache` is always empty immediately after every successful login can contradict the contract.

### HttpSessionRequestCache API

```java
HttpSessionRequestCache cache = new HttpSessionRequestCache();

cache.saveRequest(request, response); // saves when policy requires

SavedRequest saved = cache.getRequest(request, response); // reads without removing

cache.removeRequest(request, response); // discards stored request

HttpServletRequest matched =
        cache.getMatchingRequest(request, response); // wrapped request or null
```

This is an **excerpt** requiring real request/response objects and `SavedRequest`/`HttpServletRequest` imports. In Spring Security-managed flows, you usually do not call `saveRequest` manually in controllers. When debugging, you can inspect the `SPRING_SECURITY_SAVED_REQUEST` session attribute **using safe tools**, never printing sensitive URL contents or session IDs into public logs.

## 5. SimpleUrl, SavedRequestAware, and Custom AuthenticationSuccessHandler

| Handler | How it chooses response | When to use |
| --- | --- | --- |
| `SavedRequestAwareAuthenticationSuccessHandler` | Saved request prioritized unless overridden. | Traditional form login wanting to return to the pre-login page. |
| `SimpleUrlAuthenticationSuccessHandler` | Uses default URL, `alwaysUseDefaultTargetUrl`, target parameter, optional Referer. | Simple navigation without RequestCache restoration. |
| `ForwardAuthenticationSuccessHandler` | Server-side forward to an in-app path. | When you genuinely need a same-request forward instead of a browser redirect. |
| Custom `AuthenticationSuccessHandler` | App code decides redirect/JSON/status/forward. | API login, onboarding, role-specific landing, or custom workflows. |

`defaultSuccessUrl(...)` is a **shortcut to configure the success handler**. If you also call `successHandler(custom)`, do not assume a previously set `defaultSuccessUrl` still runs after your custom handler. Pick one clear response contract and test the actual handler installed on the filter.

### `setUseReferer(true)`

The base handler can fall back to the HTTP `Referer` if no higher-priority URL applies and the option is enabled. However, `Referer` is sent by the browser/client—it can be absent, forged, contain external URLs, or carry unwanted information. **Do not use `Referer` as trusted evidence to redirect to external domains.** Unless specifically needed, prefer saved requests/framework defaults or fixed targets.

### `setTargetUrlParameter("next")`

A form might submit `next=/inbox`. When the parameter is configured, the handler can use that URL for navigation. This mechanism demands **strict validation of the target source**. If an attacker crafts `/login?next=https://evil.example/phishing` and the app redirects after login without validating, they can exploit an **open redirect** for phishing. Do not enable it for convenience without a threat model.

## 6. Java Form Login Configuration in Spring Security 6.5

### 6.1. Use Saved Request If Present, Fall Back to Dashboard

```java
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/dashboard")
                .failureUrl("/login?error")
                .permitAll());

        return http.build();
    }
}
```

This is a **Spring Boot/Spring Security Servlet excerpt**, not a standalone runnable project: it still needs imports, a `UserDetailsService`/`AuthenticationManager`, `PasswordEncoder`, form template, MVC controller, and dashboard page. `GET /login` displays the form; `POST /login` is handled by the filter.

### 6.2. Always Go to Dashboard

```java
.formLogin(form -> form
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard", true)
    .permitAll())
```

Use this when the product requires passing through a dashboard/onboarding/terms-acceptance flow. Never use it as a substitute for authorization: after logging in, the user can still manually request other protected URLs.

### 6.3. Configuration with Built-In Login Form

```java
.formLogin(form -> form
    .defaultSuccessUrl("/dashboard"))
```

When no custom login page is specified and the filter chain is configured appropriately, Spring Security can render a default login form. Once you specify `loginPage("/login")`, the application becomes responsible for creating the GET page and ensuring the form POSTs to `loginProcessingUrl` with a valid CSRF token.

Illustrative static HTML snippet:

```html
<form action="/login" method="post">
  <label for="username">Username</label>
  <input id="username" name="username" autocomplete="username">
  <label for="password">Password</label>
  <input id="password" type="password"
         name="password" autocomplete="current-password">
  <!-- Real apps MUST include a framework-issued CSRF token -->
  <button type="submit">Sign in</button>
</form>
```

The HTML above **lacks a CSRF token and is not a complete deployable form**. With properly integrated Thymeleaf and `th:action`, Spring Security can help insert the token field automatically; with JS/AJAX forms, fetch and send the token per your real config. Never disable CSRF globally just to make redirects work.

### 6.4. Replacing the Success Handler Completely

For example, an API app wanting to return HTTP 204 instead of redirecting:

```java
.formLogin(form -> form
    .successHandler((request, response, authentication) -> {
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }))
```

This creates no automatic redirect. The client must understand the success contract and handle navigation if needed. Avoid writing JSON/204 and also calling `sendRedirect` after committing the response. Custom handlers must address request cache cleanup, error handling, and never serialize `Authentication.credentials` into the response.

## 7. `loginPage`, `loginProcessingUrl`, and `failureUrl` Are Not Success URLs

| API | Scope | Example |
| --- | --- | --- |
| `loginPage("/login")` | GET page where users see the form. | Controller/view renders HTML. |
| `loginProcessingUrl("/login")` | POST endpoint receiving username/password. | `UsernamePasswordAuthenticationFilter` handles it. |
| `defaultSuccessUrl("/dashboard")` | Destination after successful authentication, subject to saved-request rules. | 3xx redirect. |
| `failureUrl("/login?error")` | Destination on login failure. | Failure handler redirect. |
| `logoutSuccessUrl("/login?logout")` | Destination after logout if configured. | Logout success handler. |

Do not create a `@PostMapping("/login")` controller to process credentials while `UsernamePasswordAuthenticationFilter` owns the same URL. If you want custom JSON login, choose a strategy with well-designed filters, request parsing, CSRF, and persistence.

**Wrong passwords do not go through `defaultSuccessUrl`.** A `BadCredentialsException` in the form filter typically triggers `AuthenticationFailureHandler`. If users land on `/login?error`, inspect login failure causes (credentials, account status, CSRF, filter chain) rather than changing the default success target.

### Default Target Must Exist and Have Proper Permissions

If the app sets `defaultSuccessUrl("/dashboard")` without a matching controller/page, a successful redirect followed by a GET yields 404. If `/dashboard` requires `ROLE_ADMIN` while a regular user logs in validly, the redirect leads to 403. Target/authorization errors differ from failed login. Choose a landing page every authenticated user is allowed to view, or handle roles via a trusted policy.

## 8. Runnable Java 17: Testing the Real Handler Without a Web Server

The console program below uses **Spring Security Web 6.5.11**, **Spring Framework Test 6.2.12**, **Jakarta Servlet API 6.0**, Java 17+, and Gradle. It invokes the real `SavedRequestAwareAuthenticationSuccessHandler` with `MockHttpServletRequest`/`MockHttpServletResponse` to compare six scenarios.

The example uses `UsernamePasswordAuthenticationToken.authenticated(...)` solely to build a **simulated verified fixture** for the handler. In a real app, only a trusted `AuthenticationManager`/provider may verify credentials; never take username/authorities from a request and mark `authenticated=true`.

### 8.1. Directory Structure

```text
login-success-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SuccessRedirectDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'login-success-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.SuccessRedirectDemo'
}
```

### 8.2. `src/main/java/demo/SuccessRedirectDemo.java`

```java
package demo;

import jakarta.servlet.http.HttpSession;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;

public final class SuccessRedirectDemo {

    private static Authentication trustedFixture() {
        // Handler demo only: never read user/roles from client input.
        return UsernamePasswordAuthenticationToken.authenticated(
                "lan",
                null,
                AuthorityUtils.createAuthorityList("ROLE_READER"));
    }

    private static SavedRequestAwareAuthenticationSuccessHandler handler(
            HttpSessionRequestCache cache) {

        SavedRequestAwareAuthenticationSuccessHandler result =
                new SavedRequestAwareAuthenticationSuccessHandler();

        result.setDefaultTargetUrl("/dashboard");
        result.setRequestCache(cache);
        return result;
    }

    private static HttpSession saveOriginal(
            HttpSessionRequestCache cache) {

        MockHttpServletRequest original =
                new MockHttpServletRequest("GET", "/reports/2026");

        original.setScheme("https");
        original.setServerName("app.example.test");
        original.setServerPort(443);

        cache.saveRequest(original, new MockHttpServletResponse());
        return original.getSession(false);
    }

    private static MockHttpServletRequest loginRequest(
            HttpSession previousSession) {

        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");

        if (previousSession != null) {
            login.setSession(previousSession);
        }

        return login;
    }

    public static void main(String[] args) throws Exception {
        Authentication authenticated = trustedFixture();

        // A: saved request wins when alwaysUse=false.
        HttpSessionRequestCache savedCache = new HttpSessionRequestCache();
        MockHttpServletRequest savedLogin =
                loginRequest(saveOriginal(savedCache));
        MockHttpServletResponse savedResponse =
                new MockHttpServletResponse();

        handler(savedCache).onAuthenticationSuccess(
                savedLogin, savedResponse, authenticated);

        String location = savedResponse.getRedirectedUrl();

        System.out.println("saved.status302="
                + (savedResponse.getStatus() == 302));
        System.out.println("saved.original="
                + (location != null
                && location.contains("/reports/2026")));
        System.out.println("saved.stillCached="
                + (savedCache.getRequest(
                        savedLogin, savedResponse) != null));

        // B: no saved request -> dashboard.
        HttpSessionRequestCache emptyCache = new HttpSessionRequestCache();
        MockHttpServletRequest directLogin = loginRequest(null);
        MockHttpServletResponse directResponse =
                new MockHttpServletResponse();

        handler(emptyCache).onAuthenticationSuccess(
                directLogin, directResponse, authenticated);

        System.out.println("direct.dashboard="
                + directResponse.getRedirectedUrl()
                        .endsWith("/dashboard"));

        // C: alwaysUseDefaultTargetUrl=true -> dashboard and clears cache.
        HttpSessionRequestCache forcedCache = new HttpSessionRequestCache();
        MockHttpServletRequest forcedLogin =
                loginRequest(saveOriginal(forcedCache));
        MockHttpServletResponse forcedResponse =
                new MockHttpServletResponse();

        SavedRequestAwareAuthenticationSuccessHandler forced =
                handler(forcedCache);
        forced.setAlwaysUseDefaultTargetUrl(true);
        forced.onAuthenticationSuccess(
                forcedLogin, forcedResponse, authenticated);

        System.out.println("always.dashboard="
                + forcedResponse.getRedirectedUrl()
                        .endsWith("/dashboard"));
        System.out.println("always.cacheGone="
                + (forcedCache.getRequest(
                        forcedLogin, forcedResponse) == null));

        // D: param "next" takes priority if configured on handler.
        // /inbox is a fixed internal route, not arbitrary user input.
        HttpSessionRequestCache parameterCache =
                new HttpSessionRequestCache();
        MockHttpServletRequest parameterLogin =
                loginRequest(saveOriginal(parameterCache));
        parameterLogin.setParameter("next", "/inbox");
        MockHttpServletResponse parameterResponse =
                new MockHttpServletResponse();

        SavedRequestAwareAuthenticationSuccessHandler parameter =
                handler(parameterCache);
        parameter.setTargetUrlParameter("next");
        parameter.onAuthenticationSuccess(
                parameterLogin, parameterResponse, authenticated);

        System.out.println("parameter.inbox="
                + parameterResponse.getRedirectedUrl()
                        .endsWith("/inbox"));
        System.out.println("parameter.cacheGone="
                + (parameterCache.getRequest(
                        parameterLogin, parameterResponse) == null));

        // E: Referer illustrates the API only; not a trusted source.
        HttpSessionRequestCache refererCache =
                new HttpSessionRequestCache();
        MockHttpServletRequest refererLogin = loginRequest(null);
        refererLogin.addHeader("Referer", "/from-page");
        MockHttpServletResponse refererResponse =
                new MockHttpServletResponse();

        SavedRequestAwareAuthenticationSuccessHandler referer =
                handler(refererCache);
        referer.setUseReferer(true);
        referer.onAuthenticationSuccess(
                refererLogin, refererResponse, authenticated);

        System.out.println("referer.fromPage="
                + refererResponse.getRedirectedUrl()
                        .endsWith("/from-page"));

        // F: custom successHandler can return HTTP 204.
        AuthenticationSuccessHandler custom =
                (request, response, auth) -> response.setStatus(204);

        MockHttpServletResponse customResponse =
                new MockHttpServletResponse();

        custom.onAuthenticationSuccess(
                loginRequest(null), customResponse, authenticated);

        System.out.println("custom.status204="
                + (customResponse.getStatus() == 204));
        System.out.println("custom.noRedirect="
                + (customResponse.getRedirectedUrl() == null));
    }
}
```

### 8.3. Running the Program

With Java 17+ and Gradle (or a compatible Gradle Wrapper) in the directory containing `build.gradle`:

```bash
gradle run --quiet
```

**Program stdout** (excluding Gradle/runtime logs) from the APIs/fixtures above:

```text
saved.status302=true
saved.original=true
saved.stillCached=true
direct.dashboard=true
always.dashboard=true
always.cacheGone=true
parameter.inbox=true
parameter.cacheGone=true
referer.fromPage=true
custom.status204=true
custom.noRedirect=true
```

The demo uses boolean checks rather than printing raw URLs because `Location` representations may include host/scheme/context path depending on redirect strategy and Servlet environment. Still, each branch is verified via stable properties: original URL vs. dashboard vs. inbox, cache retained vs. cleared, and status 302 vs. 204.

### 8.4. Step-by-Step Explanation

- **`saved.status302=true`:** the default success handler uses an HTTP redirect (302 in this setup).
- **`saved.original=true`:** `HttpSessionRequestCache` retained `/reports/2026`, and `alwaysUse=false` does not force dashboard.
- **`saved.stillCached=true`:** when redirecting to a saved URL, the request stays cached for the follow-up matching wrapper; do not clear it prematurely in tests.
- **`direct.dashboard=true`:** with no prior URL, `defaultTargetUrl` is used.
- **`always.dashboard=true` + `always.cacheGone=true`:** forcing default overrides the saved request and removes it.
- **`parameter.inbox=true` + `parameter.cacheGone=true`:** the configured parameter beats the saved request; this is also where open-redirect validation must happen.
- **`referer.fromPage=true`:** with no saved URL, the base handler can use Referer if enabled. The API supports it, though clients do not supply a trusted "source of truth".
- **`custom.status204=true` and `custom.noRedirect=true`:** a custom handler can choose a non-redirect response; clients must be built around that contract.

**What the demo does not test:** password hashing, CSRF, filter order, session fixation, real proxy redirects, `SecurityContextRepository` persistence, target page authorization, and HTTP cookies. Those require integration tests with the full filter chain.

## 9. How Does Post-Login Redirect Relate to SecurityContext and Session?

A `302` causes the browser **to make a new HTTP request** to the target. For that follow-up GET to be recognized as authenticated, a reliable context-persistence mechanism is required:

```text
POST /login
  |
  +--> AuthenticationManager verifies valid credentials
  +--> SecurityContextHolder receives Authentication
  +--> SecurityContextRepository saves to session/request per config
  +--> success handler sends 302 Location: /dashboard
          |
          v
GET /dashboard (new request)
  |
  +--> browser sends session cookie if applicable
  +--> SecurityContextRepository restores Authentication
  +--> AuthorizationFilter checks permissions
  +--> controller renders page
```

If a custom login filter only calls `SecurityContextHolder.setContext(...)` without **saving** to a persistent repository, the browser may follow the redirect properly yet arrive at the next request as anonymous. In Spring Security 6, `SecurityContextHolderFilter` emphasizes **explicit save** for custom authentication flows.

**Do not change `defaultSuccessUrl` to fix session bugs.** Inspect the repository (typically HttpSession/Delegating for form login), `saveContext`, cookies, session fixation, path/domain, reverse proxies, and session stores.

### Session Fixation Protection

Spring Security typically invokes `SessionAuthenticationStrategy` after the manager succeeds; it can rotate the session ID to defend against session fixation. Custom login mechanisms must not omit the session strategy. `SavedRequest`, `SecurityContext`, and session data must survive the transition properly. If the session rotates or drops data improperly, redirects may fall back to dashboard instead of the original URL, or the post-login GET becomes anonymous.

### Session Cookie

Cookie attributes—`Secure`, `HttpOnly`, `SameSite`, `Path`, domain, and timeout—affect whether the browser sends the cookie on the new request. If a response redirects from HTTPS to HTTP or uses the wrong host behind a reverse proxy, persistence can fail or introduce security risks. Never build URLs by blindly trusting client-sent `Host`/`X-Forwarded-*` headers.

## 10. Why Not Use `defaultSuccessUrl` as Authorization?

A saved request might point to `/admin`. If a user logs in successfully with only `ROLE_READER`, the handler may still redirect to `/admin`. Subsequent authorization must return **403** (or another matching error policy) if permissions are lacking.

This is not a "bug" in saved requests. **A saved request is navigation intent**, not an access permit. Even if the handler always sends users to `/dashboard`, a user can still type `/admin` directly. Controllers, method security, URL rules, and domain authorization enforce permissions.

Likewise, `/dashboard` must exist and carry a sensible role policy. If it requires a role not held by all logged-in users, browsers will redirect straight into a 403. Never "fix" that by making sensitive pages `permitAll()` just to avoid a UX error.

## 11. Customizing Redirects by Role or Onboarding

An application may have rules such as:

- User hasn't accepted terms → force `/terms`.
- Admin → `/admin/home`.
- Regular user → `/dashboard`.
- User has a valid saved request and no mandatory onboarding → return to old URL.

A static `defaultSuccessUrl` cannot express all these branches. When needed, write a custom `AuthenticationSuccessHandler` reading roles/state from a **trusted server-side source**.

Minimal handler snippet:

```java
AuthenticationSuccessHandler roleLanding =
        (request, response, authentication) -> {

    boolean admin = authentication.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    String target = admin ? "/admin/home" : "/dashboard";
    response.sendRedirect(request.getContextPath() + target);
};
```

**This is not a complete production success handler.** It ignores saved requests and assumes roles were properly populated by the manager/provider. Behind reverse proxies or complex context paths, use proper URL construction and tests. If the product wants saved-request restoration prioritized over role landing, read `RequestCache` appropriately, validate allowed routes, and clear the cache at the right time.

Never trust a `role=admin` field from the login request or an unverified user profile. After any redirect, every URL must still undergo authorization.

### Allowing Selected Internal Target URLs

If a parameter like `next` is truly necessary, prefer an **internal route allowlist** over arbitrary raw URLs:

```java
static boolean allowedRedirect(String path) {
    return "/dashboard".equals(path)
        || "/account".equals(path)
        || "/inbox".equals(path);
}
```

This is a **conceptual target-restriction pattern**, not a full URL validation library. With dynamic paths/queries, proxies, and context paths, enforce strict parsing, canonicalization, and host/scheme/port allowlisting. Never use `startsWith("https://trusted.example")`; `https://trusted.example.attacker.test` can bypass such a naive check.

## 12. Open Redirect: Most Common Vulnerability with Client-Supplied URLs

An **open redirect** occurs when an attacker controls the URL to which the application redirects, such as:

```text
https://app.example.test/login?next=https://evil.example/phishing
```

If the handler copies `next` into `Location` unchecked, the legitimate site can bounce users directly to a phishing site right after login. Variants to account for:

- `//evil.example/path`: network-path reference that switches hosts without a scheme.
- `https://trusted.example@evil.example/`: actual host is the portion after `@`.
- URLs starting with unusual schemes or containing backslashes causing parser discrepancies.
- Encoded `%2F%2F`, double encoding, and flawed canonicalization.
- Host suffixes resembling a trusted domain yet belonging to a different origin.
- Redirect targets pointing to another internal page that itself performs an external redirect.
- Spoofed `Referer` and `Host` header poisoning planting unwanted domains in cached URLs.

**Defense:** use fixed server-side destinations whenever possible; if dynamic targets are needed, allow only allowlisted routes or origins, normalize URIs, validate scheme/host/port/context path after parsing, and never take URLs from untrusted input. Never place passwords, access tokens, reset tokens, or sensitive PII in query strings/`Location`.

**`defaultSuccessUrl("/dashboard", true)` lowers navigation complexity**, yet does not guarantee other controllers are free of open redirects.

## 13. Redirect vs. Forward and Status Codes 302/303/307/308

| Criterion | Post-login redirect | Server-side forward |
| --- | --- | --- |
| HTTP | 3xx response with `Location`. | Internal servlet forward within one request. |
| Browser address bar | Updates to target URL. | Usually still displays the original request URL. |
| New request | Browser issues a new request. | No new browser request required. |
| Auth/session | Context must be restored on the new request. | Same request may read context depending on filter/dispatch. |
| Avoiding form resubmission | Fits POST/Redirect/GET well. | Forwarding from POST can retain resubmit semantics. |

Spring Security's `DefaultRedirectStrategy` normally uses **302 Found**. Some clients switch from POST to GET when following a 302 redirect; if an API needs explicit "switch to GET after POST" semantics, consider **303 See Other** via an appropriate custom strategy/handler.

**Do not arbitrarily use 307/308** for post-login-POST redirects: those status codes preserve HTTP method and body semantics, risking re-sending login credentials to the target URL. Any customized redirect status must be tested against target browsers/clients.

As for `ForwardAuthenticationSuccessHandler`, do not treat it as a drop-in clone of `defaultSuccessUrl`; forwarding requires checking dispatcher types, displayed URLs, CSRF, and the forwarded request's filter chain.

## 14. Proper Testing: From Handler Level to Real HTTP Login

### 14.1. Handler-Level Tests

Use mock Servlet requests/responses as in Section 8 to check:

| Case | Saved request | Handler | Expectation |
| --- | --- | --- | --- |
| Direct login | None | Default handler with fallback URL | Dashboard. |
| Login after protected GET | `/private` present | `alwaysUse=false` | Original URL. |
| Forced landing | `/private` present | `alwaysUse=true` | Dashboard, cache cleared. |
| Target parameter enabled | Present | `targetUrlParameter("next")` | Parameter wins if valid, cache cleared. |
| Referer enabled | None | `useReferer=true` | Referer if present, fallback otherwise. |
| Custom 204 | Irrelevant | Custom handler | Status 204, no redirect. |

**Do not assert only status 302.** A redirect to a phishing site is still a valid HTTP 302 yet a security bug. In regression tests, verify the full URL, scheme/host/context path, query, and allowlist when client data is involved.

### 14.2. Spring Security + MockMvc Integration Tests

A real login test must pass through `UsernamePasswordAuthenticationFilter` and `AuthenticationManager`. Example snippet (assuming a valid user and `MockMvc` configured with Spring Security):

```java
@Test
void loginDirectlyGoesToDashboard() throws Exception {
    mockMvc.perform(formLogin()
            .user("demo")
            .password("correct-password"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/dashboard"));
}
```

This is **not a standalone JUnit class**; it requires `spring-security-test`, imports, a user fixture, and matching `formLogin` rules. If the user does not exist or the fixture hash mismatches the encoder, the request runs the failure handler instead of redirecting to dashboard.

To test saved requests, **keep the same `MockHttpSession`** between the blocked request and the login POST. Sequence overview:

```text
1. GET /private while anonymous.
2. Grab the HttpSession holding SavedRequest (if any).
3. POST /login with that session, valid credentials, and CSRF token.
4. Assert HTTP redirect to /private.
5. Follow redirect GET /private with matching session/cookie.
6. Assert Authentication persisted and authorization succeeds.
```

In tests with multiple filter chains, verify the request actually enters the intended chain, since a web chain's `defaultSuccessUrl` does not control an API login chain.

### 14.3. Additional Tests to Include

- Failed login → `failureUrl`/failure handler; success handler not called.
- Locked/disabled account → no `Authentication` granted; no success redirect.
- Login POST missing CSRF token → rejected per policy; success handler not invoked.
- Reader user with saved `/admin` → may redirect to `/admin`, yet follow-up GET gets 403.
- Saved URL with valid query string → query preserved intact without secret tokens.
- Target parameter pointing to external domain → denied or falls back per policy.
- Missing/expired session cookie → does not restore saved request or authentication unexpectedly.
- Context path `/app` and HTTPS reverse proxy → `Location` has right scheme/host/path.
- `alwaysUse=true` → does not reuse old saved request on later logins.
- Logout then log back in → no leaking of saved request/context from invalidated session.
- Custom JSON handler → response does not simultaneously set a `Location` redirect.
- Role-based landing → roles sourced from server; authorization still enforced.

### Why Is `@WithMockUser` Insufficient?

`@WithMockUser` is great for testing authorization/controllers because it populates the security context directly. It **does not prove** that the login filter verified username/password, the handler ran, or the saved request was restored. Real tests must hit the login endpoint or invoke the success handler directly with the right model.

## 15. When Should `NullRequestCache` Be Used?

For a stateless API using bearer tokens/JWT, browsers do not typically need to return to a saved URL after form login. `NullRequestCache` fits when you **do not want to store original requests** in the session. A successful API login might return JSON or HTTP 204 instead of redirecting.

This is **not** advice to make all form logins stateless: session-based browser form login normally uses request caching to restore pages and `SecurityContextRepository` to persist authentication. Choose based on endpoint architecture, not just to shave off a few HTTP redirects.

If you use `NullRequestCache` yet still need "return to previous page" in an SPA, the frontend can hold the internal route in safe state and navigate after receiving the login result. Never put arbitrary external URLs into state without validation.

## 16. Common Symptoms and Debugging

### 16.1. Login Succeeds Yet Always Goes to Dashboard

Check:

1. Is `defaultSuccessUrl("/dashboard", true)` set, or does a custom success handler always redirect to dashboard?
2. Was a saved request actually created in `RequestCache` when blocked before login?
3. Is `NullRequestCache` or `requestCache().disable()` configured?
4. Did the browser keep the same `HttpSession` between the protected GET and login POST?
5. Did the cache request matcher skip the original URL, or did background requests overwrite it?
6. Did `targetUrlParameter` or `Referer` override the handler?
7. Did multiple `SecurityFilterChain`s route the request into a different chain?

### 16.2. Login Succeeds Yet Follow-Up Request Is Anonymous

Check **`SecurityContextRepository`**, not just the target URL:

- Did the filter save `SecurityContext` under the explicit-save model?
- Did the session fixation strategy rotate the session ID properly?
- Was the `JSESSIONID` cookie returned and sent back?
- Are cookie `Secure`/`SameSite`/`Path`/domain flags accurate?
- Did a reverse proxy emit a `Location` with the wrong scheme or host?
- Is the session store synchronized across nodes?
- Does the target URL actually belong to the session-backed security chain?

### 16.3. Redirects to `/admin` Then Returns 403

The saved URL may be `/admin`, while the user only holds `ROLE_USER`. Authorization must deny it. Display a friendly 403 page or adjust product navigation policy—**never** open sensitive endpoints with `permitAll`.

### 16.4. Form Login POST Returns 403 Before Redirecting

Usually check CSRF: form missing token or cookie/session mismatch, wrong `loginProcessingUrl`/method, or unexpected filter chain. `defaultSuccessUrl` never runs when authentication has not succeeded.

### 16.5. Redirects to Internal Domain or HTTP

Check forwarded headers and reverse proxy trust, context path, absolute default target URLs, URLs inside saved requests, and `Host` headers. Never trust client-supplied `X-Forwarded-Host`. Use proper proxy configuration and test with real HTTPS requests.

## 17. Mistakes to Avoid

1. **"`defaultSuccessUrl("/dashboard")` always goes to dashboard."** False: saved requests take priority.
2. **"The `true` argument means do not redirect."** False: it forces using the default target.
3. **"`SavedRequest` and `SecurityContext` are the same thing."** False: one stores the URL, the other stores authentication.
4. **"A right redirect means durable authentication."** No; context/session can still be lost on the next GET.
5. **"Changing `defaultSuccessUrl` fixes login loops."** False when caused by cookies/repository/CSRF.
6. **"`failureUrl` is a success target."** False: it is for failed logins.
7. **"Putting client-supplied `next` directly into `Location` is fine."** Can introduce an open redirect.
8. **"`Referer` is always trustworthy."** No: it can be absent or spoofed.
9. **"`startsWith` is enough to check hosts."** No: parse, canonicalize, and allowlist.
10. **"A saved request permits accessing the saved URL."** Authorization still runs.
11. **"A POST with a saved request replays safely."** Never use request cache as a transaction queue.
12. **"Every successful login clears the saved request immediately."** False when redirecting back to the original URL.
13. **"Setting `alwaysUse=true` has no UX impact."** It drops the path back to what the user was viewing.
14. **"A custom `successHandler` automatically chains into the default handler."** No; the custom handler owns the response.
15. **"Returning 204 and then redirecting is fine."** Violates the contract and fails once response is committed.
16. **"Letting a browser-sent role decide the redirect."** Spoofing risk; use trusted `Authentication`.
17. **"Landing on `/admin` after login proves you are an admin."** No; handlers do not replace authorization.
18. **"Testing only with `@WithMockUser` is enough."** Does not test the login success flow.
19. **"No need to test context path/proxy because redirects are always relative."** Not guaranteed with absolute URLs or host rewrites.
20. **"CSRF has nothing to do with login redirects."** CSRF can block the POST before success ever runs.
21. **"Storing passwords/tokens in query strings to keep state is fine."** URLs leak via history, logs, and Referer.
22. **"`307` after login POST acts just like `302`."** 307 preserves method/body by HTTP semantics, risking credential re-submission.
23. **"Just `permitAll` the dashboard to fix 403."** Can expose sensitive data.
24. **"RequestCache must exist in stateless APIs."** No; use `NullRequestCache`.
25. **"The old session always survives session fixation protection."** Test your actual configuration.
26. **"Putting GET and POST `/login` in one controller works just like the default filter."** Not if POST is owned by the authentication filter.
27. **"Every HTTP 302 from login means success."** Failure handlers can also redirect; inspect `Location`.
28. **"Saved requests are always found on login POSTs without cookies."** No: sessions aren't linked.
29. **"Dynamic targets from unverified user profiles are safe."** Must check permissions and data provenance.
30. **"Having a fixed success URL guarantees every user has permission to view it."** Policy must be verified separately.

## 18. Self-Check Questions

**Q1.** How does `defaultSuccessUrl("/home")` differ from `defaultSuccessUrl("/home",true)`?

**Answer:** The single-argument overload prioritizes a saved request if present. The `true` variant always uses `/home` and discards any associated saved request.

**Q2.** An anonymous user tries to view `/orders/42` and is prompted to log in; where do they go after a valid login with `defaultSuccessUrl("/dashboard")`?

**Answer:** If `RequestCache` holds the saved `/orders/42` request, usually `/orders/42`; otherwise, it falls back to `/dashboard`.

**Q3.** What if a user opens `/login` directly with no saved request?

**Answer:** Redirects to the default target `/dashboard`.

**Q4.** Does `SavedRequestAwareAuthenticationSuccessHandler` clear the cache immediately on every login?

**Answer:** No. When redirecting to the original URL, it may retain the request for the matching wrapper. When forcing default or prioritizing target parameter, it clears it.

**Q5.** Does `defaultSuccessUrl` verify passwords?

**Answer:** No. Passwords are verified by the manager/provider; the handler merely receives the success outcome and navigates.

**Q6.** Why is `next=https://evil.example` risky?

**Answer:** Redirecting based on unvalidated client URLs creates an open redirect, enabling phishing and potentially leaking URL data.

**Q7.** How do `RequestCache` and `SecurityContextRepository` differ?

**Answer:** `RequestCache` stores the pre-login request/URL; `SecurityContextRepository` stores the authentication context to restore across session/request scope.

**Q8.** Login redirected to dashboard properly, yet the next GET is anonymous. What caused it?

**Answer:** Likely repository didn't save, cookie/session was lost, session fixation/proxy/path failed, or a different security chain matched—not necessarily `defaultSuccessUrl`.

**Q9.** Why can a saved `/admin` still return 403 after login?

**Answer:** Saved requests grant no permissions. Users only receive permissions tied to their verified `Authentication` and URL authorization rules.

**Q10.** What makes a reliable test for post-login redirects?

**Answer:** Send a login POST through the real filter/provider with valid user fixtures, assert 302 + `Location`, reuse the session from the pre-login protected request, test both `alwaysUse` true/false, and verify the post-redirect GET.

**Q11.** When using a custom JSON success handler, is `defaultSuccessUrl` still needed?

**Answer:** Usually no; the custom handler owns the response (200/204/JSON). It must honor its contract and clean up `RequestCache` appropriately.

**Q12.** Are `302` and `307` equivalent after a login POST?

**Answer:** No. On 302 most clients switch to GET; 307 preserves method and body, risking re-sending the password POST to the target URL, so do not pick it casually.

**Q13.** How do `loginPage` and `loginProcessingUrl` differ?

**Answer:** One is the GET page displaying the form; the other is the POST endpoint where the authentication filter receives credentials.

**Q14.** Does `alwaysUse=true` prevent users from manually navigating to other protected URLs?

**Answer:** No. It only picks the post-login landing URL; authorization on every URL remains enforced.

## 19. Official References

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): filter form handling, authentication success/failure, login page, and POST.
- [Spring Security 6.5.11 — AbstractAuthenticationFilterConfigurer](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): `defaultSuccessUrl(String)` and `defaultSuccessUrl(String,boolean)`.
- [Spring Security 6.5.11 — SavedRequestAwareAuthenticationSuccessHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): priority order and saved-request lifecycle.
- [Spring Security 6.5.11 — AbstractAuthenticationTargetUrlRequestHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html): default URL, alwaysUse, target parameter, and Referer.
- [Spring Security 6.5.11 — HttpSessionRequestCache](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/HttpSessionRequestCache.html): APIs for saving, reading, deleting, and matching requests.
- [Spring Security 6.5.11 — DefaultRedirectStrategy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/DefaultRedirectStrategy.html): computing `Location` and redirect HTTP status.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): saving `SecurityContext` for post-redirect requests.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explicit save and session fixation.
- [OWASP — Unvalidated Redirects and Forwards](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): preventing open redirects and allowing only trusted URLs.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): status codes 302, 303, 307, and 308.

**Conclusion:** `defaultSuccessUrl("/dashboard")` does not mean every user always goes to the dashboard. With `SavedRequestAwareAuthenticationSuccessHandler`, browsers typically return to the protected URL requested prior to login; dashboard is just the fallback. If the product requires landing on a fixed page, use `defaultSuccessUrl("/dashboard", true)` and accept discarding saved requests. Post-login navigation must go hand in hand with **real authentication**, session/context persistence, target-page authorization checks, CSRF, URL validation, and integration tests over the complete filter chain.