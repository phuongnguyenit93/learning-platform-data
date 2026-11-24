# Saving Pre-Login Requests and Choosing a Safe Return Address

> **Scope:** Spring Security fundamentals → **Login and Logout**. This lesson explains how Spring Security remembers a resource a user wanted to access **before logging in**, returns them there after successful authentication, and controls the **redirect address** to avoid open redirects, information leaks, login loops, or returning to the wrong place. Main examples use **Spring MVC / Servlet, Spring Boot 3.x, Spring Security 6.x, and Java 17+**; WebFlux, stateless APIs, and SSO are compared at an architectural level.

## 1. The problem: after logging in, where does the user want to go back to?

An unauthenticated user clicks a link to a private report:

```text
GET /reports/7?view=summary
```

The application requires authentication. The browser is redirected to `/login`. After the user enters the right username/password, the desired experience is to return to **`/reports/7?view=summary`**, rather than always landing on the home page. However, if the user opens `/login` directly from a menu and logs in with no previously requested resource, the application should go to **`/dashboard`**.

Two scenarios:

```text
A. Deep link to a page requiring authentication

Browser
  ├─ GET /reports/7?view=summary
  ├─ Spring Security detects user is not logged in
  │    ├─ save original request in RequestCache
  │    └─ redirect to /login
  ├─ POST /login with credentials + CSRF token
  ├─ login succeeds
  ├─ success handler retrieves SavedRequest
  ├─ redirect to original URL
  └─ GET /reports/7?view=summary with authenticated session


B. Directly opening the login page

Browser
  ├─ GET /login
  ├─ POST /login with credentials + CSRF token
  ├─ login succeeds; no SavedRequest
  └─ redirect to /dashboard (safe fallback)
```

Crucial point: **the post-login return URL is a navigation decision, not an authorization decision**. After the redirect, the request to the report must still pass through HTTP authorization, method security, and object/tenant-level authorization. A URL saved before login must never grant permission to read someone else's report.

### 1.1. Functional and security requirements

1. Remember the **exact original destination** when the user opens a deep link requiring authentication.
2. Preserve URL parts needed for navigation such as path/query within policy bounds, without accidentally dropping page parameters.
3. If no saved request exists, use a known default destination, such as `/dashboard`.
4. Never take a string from `?next=`, `?returnUrl=`, the body, or `Referer` and put it directly into HTTP `Location`.
5. Never redirect users to an unintended host, including via URLs like `//host` or encoded variants.
6. Never automatically replay write operations (POST/PUT/DELETE) just because the user logged in.
7. Never let stale saved requests, other tabs, failed logins, expired sessions, or logouts cause misdirected redirects.
8. Include integration tests for both allowed and denied paths, not just checking "login 200."

## 2. Spring Security components to distinguish

| Component | Role |
|---|---|
| `ExceptionTranslationFilter` | When a request hits a situation requiring authentication to start, can ask `RequestCache` to save the request and invoke `AuthenticationEntryPoint` |
| `AuthenticationEntryPoint` | Begins the authentication process; with form login, typically redirects to `/login` |
| `RequestCache` | Contract for saving, finding, and removing a protected request |
| `HttpSessionRequestCache` | A common default `RequestCache` implementation on Servlet, using `HttpSession` |
| `SavedRequest` / `DefaultSavedRequest` | Data describing the original HTTP request, including URL/headers/parameters needed to continue |
| `SavedRequestAwareAuthenticationSuccessHandler` | After successful authentication, considers the saved request to determine the redirect URL |
| `RequestCacheAwareFilter` | When the request returns after redirect, coordinates with the cache to restore/wrap saved request information per the framework's mechanism |
| `SimpleUrlAuthenticationSuccessHandler` | Basic success handler to redirect to a URL per configured policy |
| `HttpSecurity.formLogin` | Configures form authentication, login URL, and success/failure handling |
| `defaultSuccessUrl` | Fallback destination, or forced destination if the `alwaysUse` option is enabled |

**Similar names do not mean the same job:** `RequestCache` saves the request; `AuthenticationSuccessHandler` picks the post-login destination; `AuthenticationEntryPoint` sends the user to log in beforehand; `SecurityFilterChain` protects URLs. If you customize one component and forget the others, returning to the old URL may stop working properly.

### 2.1. When is a request saved?

With a familiar form login configuration, an **unauthenticated** request to a URL requiring authentication passes through HTTP security. `ExceptionTranslationFilter` can save the request in `RequestCache` and start login. Requests to public pages generally do not need to be saved because no authentication challenge arises.

Saving depends on the **configured RequestCache**, session creation policy, cache matchers, exception handling, and authentication type. Not every request to `/login`, every 403 error, or every bearer-token API call automatically becomes a `SavedRequest`.

### 2.2. Saved request is stored in the session, not placed raw in the login query

With `HttpSessionRequestCache`, request details can be stored in the server-side `HttpSession` (the default attribute name is typically `SPRING_SECURITY_SAVED_REQUEST`). The browser only carries a session cookie; there is no need to pass a raw `returnUrl` to the login form by arbitrary string concatenation.

This is a **design benefit**, yet it is not an absolute guarantee that the stored URL is always safe: the initial URL still contains client-influenced parts, and deployments may have misconfigured Host/forwarded headers. You must verify trusted hosts, paths, proxies, and redirect URLs when designing a real application.

### 2.3. One session has only one "saved request" in the typical cache

By default, an `HttpSessionRequestCache` is not a multi-tab queue for all user actions. When tab A opens `/reports/7` and tab B opens `/profile` before logging in within the same session, the newer request can overwrite the older one. Do not build an assumption that "each tab has an independent SavedRequest" unless you design a corresponding mechanism.

If the product requires **multi-tab continuation**, build dedicated UX and state with expiration, transaction IDs, session binding, input validation, and concurrency tests; do not try to use `HttpSessionRequestCache` as unbounded storage.

## 3. Actual flow: before login and after login

On Servlet, the typical sequence is:

```text
GET /reports/7?view=summary (anonymous)
    |
    v
SecurityFilterChain
    |
    v
Requirement .authenticated() not satisfied
    |
    v
ExceptionTranslationFilter
    ├─ RequestCache.saveRequest(...)
    └─ AuthenticationEntryPoint → 302 /login
            |
            v
Browser GET /login
            |
            v
POST /login with username/password/CSRF token
            |
            +-- failure --> /login?error (no authenticated session)
            |
            +-- success
                    |
                    v
             AuthenticationSuccessHandler
                    |
                    +-- Has SavedRequest?
                    |      |
                    |      +-- Yes → redirect to saved target
                    |      |
                    |      +-- No → fallback /dashboard
                    |
                    v
             Browser sends new request to target
                    |
                    v
          HTTP + method + data authorization proceeds
```

When the success handler chooses the saved request, it redirects the browser to that URL. **Do not think the server automatically "replays" every side effect of the original request.** An HTTP 302 tells the browser to follow the redirect, usually as a **GET**. The saved request mechanism can restore metadata on the post-redirect request via a wrapper/filter, but it is not a mechanism to automatically resubmit a payment POST payload or resume a file upload stream.

### 3.1. Query strings can be preserved, but content must be controlled

The original target `/reports/7?view=summary` can be saved along with its query so the user returns to the exact report tab. Still, **never put credentials, access tokens, password reset tokens, or secrets into query strings**: URLs can be stored in browser history, proxy logs, analytics, Referer headers, and saved request/session state.

Some Spring Security 6 versions use a `continue` marker parameter for `RequestCache` to avoid accessing the session on every request. The post-login URL may include a query marker for the cache mechanism; target tests should check path + required query semantics rather than forcing every URL to match paper examples byte-for-byte. Verify exact behavior against your project's version and config.

### 3.2. What if there is no SavedRequest?

If the user directly opens `/login`, or the request cache is disabled, or login was initiated via another flow, the success handler needs a **stable default destination**, such as `/dashboard`. Do not try to infer the previous page from `Referer` without a security policy and verification: that header can be missing, forged, or point outside the origin.

A fallback URL must actually exist and be accessible to the user; if the fallback points to an endpoint requiring a permission the logged-in user lacks, the user may hit a 403 or a confusing redirect loop.

## 4. How does `SavedRequestAwareAuthenticationSuccessHandler` choose the URL?

According to the Spring Security 6 API, the branches to remember upon successful authentication are:

1. **`alwaysUseDefaultTargetUrl = true`:** always uses the configured default destination and removes the associated saved request.
2. **`targetUrlParameter` is configured and the request contains a non-empty matching parameter:** the base success handler may use the destination provided by that parameter while dropping the saved request. **This is especially dangerous if the parameter is unconstrained, as it can create an open redirect.**
3. **A valid `SavedRequest` exists in `RequestCache`:** uses the saved request's URL to redirect; the saved request record may temporarily remain in the cache for `RequestCacheAwareFilter` to process when the browser returns.
4. **No saved request:** falls back to the base handler's logic, typically the fallback destination.

Decision table:

| Scenario | Configuration | Expected target |
|---|---|---|
| Opened private report before login | `defaultSuccessUrl("/dashboard", false)` | Saved report URL |
| Opened `/login` directly | `defaultSuccessUrl("/dashboard", false)` | `/dashboard` |
| Opened private report, but config always forces default | `defaultSuccessUrl("/dashboard", true)` | `/dashboard`, ignoring saved request |
| Custom `successHandler` always sends `/home` | Developer-written handler | `/home`; may accidentally drop the SavedRequest flow |
| Configured `targetUrlParameter("next")` without validating `next` | User can supply any URL | Open redirect risk |
| RequestCache disabled via `NullRequestCache` | Does not save previous request | Fallback or other handler logic |

**Special note:** `defaultSuccessUrl("/dashboard", false)` does not mean "always redirect to dashboard." The boolean `false` means **do not force using the default destination** when a prior saved request exists. With `true`, deep links will be ignored.

Do not equate `targetUrlParameter` with `HttpSessionRequestCache`'s `matchingRequestParameterName`. One parameter **selects a request-supplied target URL**; the other can serve as a **marker controlling when to check for a saved request**. They do not share the same security semantics.

## 5. Runnable example: Spring Boot 3.x, Java 17+, form login

This sample includes:
- A public route `GET /public/ping`.
- An authentication-required route `GET /reports/{id}?view=...`.
- A fallback route `GET /dashboard`.
- Spring Security's default login.
- `defaultSuccessUrl("/dashboard", false)` to prioritize a saved request if present.
- An integration test suite verifying deep links, direct login, and spoofed redirect parameters.

The goal is **understanding the request cache and navigation target**; the example has no database and no per-report owner/tenant rules yet. In production, add object-level authorization checks in the service/repository layer.

### 5.1. Create the Gradle project

From Spring Initializr, create a Java 17+, Spring Boot 3.x project, selecting **Spring Web** and **Spring Security**. In the generated `build.gradle`, ensure this block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is **only the dependencies block**: keep plugins, repositories, and the rest from the generated project.

### 5.2. One Java file for the application

Create `src/main/java/example/savedrequest/SavedRequestDemoApplication.java`:

```java
package example.savedrequest;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SavedRequestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavedRequestDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/reports/*").authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/dashboard").authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form
                .permitAll()
                .defaultSuccessUrl("/dashboard", false))
            .build();
    }

    @Bean
    UserDetailsService demoUsers() {
        UserDetails user = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }
}

@RestController
class PageController {

    @GetMapping("/public/ping")
    public String ping() {
        return "ok";
    }

    @GetMapping("/dashboard")
    public String dashboard(Authentication authentication) {
        return "dashboard for " + authentication.getName();
    }

    @GetMapping("/reports/{id}")
    public Map<String, String> report(
            @PathVariable long id,
            @RequestParam(defaultValue = "summary") String view,
            Authentication authentication) {
        return Map.of(
            "reportId", Long.toString(id),
            "view", view,
            "username", authentication.getName());
    }
}
```

**Java structure:** The file contains one public class matching the filename and one package-private top-level controller class in the same package. The controller is picked up by Spring Boot component scanning at runtime; Spring Security receives authentication from session form login. `{noop}` **does not hash passwords** and is acceptable only in local demos, never in production.

In the configuration:

1. `/public/**` is public.
2. `GET /reports/*` and `GET /dashboard` require login; undeclared routes are denied by `denyAll`.
3. `formLogin(...).permitAll()` grants access to login endpoints configured by Spring Security, including `POST /login`; the framework provides a default login page when no custom page is declared.
4. `defaultSuccessUrl("/dashboard", false)` allows `SavedRequestAwareAuthenticationSuccessHandler` after login to prioritize a saved request, or fall back to dashboard if none exists.
5. The lesson does not add `targetUrlParameter("next")` and **does not read `next` directly to redirect**.

**Do not disable CSRF**: `POST /login` needs a valid CSRF token when protection is enabled. Integration tests will use `csrf()` from `spring-security-test`.

### 5.3. Manual run

In a project with the Gradle Wrapper, run:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Open a new browser window or private tab at:

```text
http://localhost:8080/reports/7?view=summary
```

While unauthenticated, the application redirects to the login form. Log in with `alice / demo123`. After successful login, the browser is redirected back to the requested report URL (possibly with a `continue` marker depending on version). The expected JSON contains:

```json
{
  "reportId": "7",
  "view": "summary",
  "username": "alice"
}
```

If you open `http://localhost:8080/login` directly without a prior saved request, logging in redirects to `/dashboard` with body:

```text
dashboard for alice
```

**Do not treat this as a report authorization test:** Any authenticated user passes the `authenticated()` rule in the demo. A real application must decide whether the user is permitted to view **report 7**.

## 6. Integration tests verifying return targets and open redirects

Create `src/test/java/example/savedrequest/SavedRequestDemoTest.java`:

```java
package example.savedrequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRequestDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void savedDeepLinkWinsOverFallback() throws Exception {
        // GET to a page requiring login.
        MvcResult entry = mvc.perform(
                get("/reports/7").param("view", "summary"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) entry.getRequest().getSession(false);
        assertThat(session).isNotNull();

        // POST login keeps the same anonymous session containing SavedRequest.
        MvcResult login = mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String target = login.getResponse().getRedirectedUrl();
        assertThat(target).isNotNull();
        assertThat(target).contains("/reports/7");
        assertThat(target).contains("view=summary");

        // Session ID may be rotated when authentication succeeds.
        MockHttpSession authenticatedSession =
            (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/reports/7")
                .param("view", "summary")
                .session(authenticatedSession))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.reportId").value("7"))
            .andExpect(jsonPath("$.view").value("summary"));
    }

    @Test
    void directLoginUsesKnownLocalFallback() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void untrustedNextParameterIsIgnoredByThisConfig()
            throws Exception {
        // Without targetUrlParameter: user input is not
        // automatically turned into a redirect target.
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123")
                .param("next", "https://attacker.example/collect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void anonymousDoesNotGetReportDirectly() throws Exception {
        mvc.perform(get("/reports/7"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Explanation of the tests:**

- The first test passes through the real Spring Security filter chain, giving `ExceptionTranslationFilter` and `RequestCache` a chance to save the pre-login request.
- The same `MockHttpSession` is passed to POST login; creating a different session would prevent the handler from finding the saved request and cause a wrong redirect to dashboard.
- `csrf()` makes POST login valid instead of being rejected by the CSRF filter before authentication.
- The test intentionally asserts only that the target **contains the right path and business query**, not a byte-for-byte URL match, to avoid depending on version-specific `continue` markers.
- The `next` test confirms that **the specific configuration in this example** ignores untrusted parameters. It is **not a blanket proof that every custom handler is safe**.
- When testing with a real browser, verify cookies, context path, and the redirect chain. MockMvc does not substitute for testing HTTPS/forwarded headers at the gateway.

## 7. Open redirect: the dangerous mistake when choosing a "return URL" manually

### 7.1. Why is an open redirect risky?

An open redirect happens when an application redirects the browser to an unconstrained URL controlled by an untrusted party. The initial link still belongs to a legitimate domain, so an attacker can abuse that domain's reputation to lead victims to a phishing site.

**Insecure approach** — for recognition only, never use in production:

```java
@GetMapping("/after-login")
public void redirectUnsafe(
        @RequestParam String next,
        HttpServletResponse response) throws IOException {
    response.sendRedirect(next); // Does not validate next!
}
```

The snippet above **is not a complete program**. If `next` receives a value like `https://attacker.example/login`, the HTTP response can point the browser externally. Do not implement this logic or pass `request.getParameter("returnUrl")` directly inside a success handler.

Examples of suspicious values:

| Input | Why dangerous/untrusted |
|---|---|
| `https://attacker.example/phish` | Absolute URL pointing to an external origin |
| `http://attacker.example/` | Redirects to another host, downgrades HTTPS if the browser follows |
| `//attacker.example/path` | Scheme-relative URL using the current scheme while changing the host |
| `\\attacker.example` or backslash variants | Some URL parsers/browsers may normalize differently |
| `javascript:...`, `data:...` | Schemes unsuitable for safe HTTP navigation |
| `%2F%2Fattacker.example` | Percent-encoded variant that can become `//` after decoding |
| `/logout?next=...` | Can trigger chained redirects and state changes |
| `/redirect?url=https://...` | Indirect redirect can still leave the origin |
| Strings with CR/LF or unusual encoding | Parser/response splitting risks if mishandled by APIs |
| Unverified `Referer` | Header may be absent or untrusted for navigation decisions |

Do not treat a naive `startsWith("/")` check as complete safety: `//host` also starts with `/`; multi-layer URL decoding, backslashes, context paths, and proxy normalization can create discrepancies between validation and the browser.

### 7.2. Simplest and strongest design: server-side allowlist

Instead of accepting free-form URLs, accept a finite server-defined **destination code**. For example, the user selects "Dashboard" or "Report" via an alias value:

```java
// Standalone Java 17+ utility; compilable code example.
public final class ReturnDestination {
    private ReturnDestination() {}

    public static String fromAlias(String alias) {
        if ("report-seven".equals(alias)) {
            return "/reports/7";
        }
        // Includes null, unknown values, and absolute URLs.
        return "/dashboard";
    }
}
```

Results:

| Parameter | Server-approved URL |
|---|---|
| `report-seven` | `/reports/7` |
| `dashboard` | `/dashboard` |
| `https://attacker.example/` | `/dashboard` |
| `//attacker.example/` | `/dashboard` |
| `null` or missing parameter | `/dashboard` |

**This is only a destination selector, not yet a custom success handler.** In a real application, if you need an alias at login success, integrate it with `AuthenticationSuccessHandler` in a clear priority order while still honoring endpoint authorization checks. Do not use a hardcoded `report-seven` value as proof that the user is authorized for report 7.

An allowlist provides stronger safety than regex validation on arbitrary URLs because you do not need to account for every URL variant. When dynamic URLs are needed, accept a validated route identifier or business object ID and construct the URL **server-side**, such as `"/reports/" + approvedReportId`; never concatenate client-controlled path segments where path traversal or URL parser confusion is possible.

### 7.3. What if cross-origin URLs must be supported?

Some OIDC, federation, or multi-domain applications need to redirect to another domain. In that case, maintain an **approved list of exact origins and callbacks**, compare the parsed/canonicalized URL by scheme, host, port, and path, disallow userinfo, avoid suffix wildcards like `endsWith("trusted.com")` (which matches `eviltrusted.com`), and reject unsafe schemes.

For **OAuth2/OIDC redirect URIs**, use standard authorization server/client validation against registered callbacks rather than inventing an arbitrary landing-page `next` parameter. OAuth2 `state` and PKCE serve different purposes; do not treat them as substitutes for a redirect URI allowlist.

## 8. Is `SavedRequest` inherently "trusted"?

A saved request is better than letting the user supply `returnUrl` at POST login because it is bound to the initial request in the session and managed by Spring Security. However, the initial path still originated from an HTTP client, so examine:

1. **Host header / forwarded headers:** An absolute redirect URL may derive scheme/host/port from the request. If a proxy trusts a malicious `Host` or `X-Forwarded-Host`, the recorded URL may have the wrong origin. Allowlist hostnames at the edge, configure trusted proxies properly, and never trust forwarded headers from the Internet.
2. **Paths with untrusted side effects:** Allowing return to `/account/delete` or a page with side effects via GET is a flawed design. GET must be safe/idempotent by semantics; otherwise returning to it can trigger unintended actions.
3. **Sensitive queries:** SavedRequest could retain a URL carrying a token/secret exposed via redirects, browser history, or logs; avoid passing credentials in query strings.
4. **No-longer-permitted paths:** If the user logs in without permission for the resource, they still receive 403/404 upon redirect. SavedRequest grants no authorization.
5. **Multiple tabs in one session:** A newer saved request can overwrite an earlier one, causing unexpected UX.
6. **Session fixation:** The session holding the saved request must be protected at login; Spring Security typically rotates the session ID upon successful authentication. Never disable fixation protection to "preserve the old request."
7. **Intentional external links:** A same-origin URL that passes through another open-redirect endpoint can still lead outside. Review redirect chains.
8. **Data leakage via logs/tracing:** Avoid logging raw session cookies, Authorization headers, sensitive query strings, or full DefaultSavedRequest objects if they contain private data.

**Recommended practice:** record valid hosts and test the redirect chain end-to-end through a browser when deploying behind a reverse proxy, rather than asserting only paths in unit tests.

## 9. Handling priority order when multiple "return addresses" exist

An application may have four sources:

- A saved request from a protected resource blocked due to being unauthenticated.
- A fixed post-login destination, such as `/dashboard`.
- A UI-chosen destination ("Reports" tab), as an **approved alias**.
- An external callback URL in a registered OAuth2/OIDC flow.

Do not let sources compete without a policy. One reference priority order:

```text
Authentication succeeds
       |
       +-- Valid saved request per trust policy?
       |      |
       |      +-- Yes → continue to protected route
       |
       +-- Valid UI alias from allowlist?
       |      |
       |      +-- Yes → fixed internal route
       |
       +-- No → /dashboard
```

Depending on the product, an alias might precede a saved request, but it must be decided **explicitly** and never allow an attacker's arbitrary parameter to force an external target. Do not use `Referer` as a priority source just for convenience.

In Spring Security, calling `formLogin(form -> form.successHandler(custom))` can **replace** the default SavedRequestAware handler. If the custom handler does not share the same `RequestCache` or delegate properly, deep links will be lost. If you only want to change the fallback, **prefer `defaultSuccessUrl("/dashboard", false)`**, as it is simple and preserves saved-request continuation.

### 9.1. When to use `defaultSuccessUrl(..., true)`?

`true` is useful when the product requirement is "always go to one landing page after login," such as mandatory onboarding confirmation screens. It **intentionally** ignores SavedRequest. Do not set `true` and still expect deep links to return as before.

If every user must complete MFA/terms/onboarding before accessing resources, resuming a saved request must depend on **full authentication state** and a designed policy; do not let a redirect after single-step authentication bypass required gates.

## 10. What happens to POST/PUT/PATCH/DELETE before login?

**Important question:** "A user is submitting an order, their session expires, the app requires login—does it automatically resubmit the order afterward?"

Do not assume so. An HTTP redirect is a navigation step, not an idempotent retry mechanism for every request.

- `302`/`303` typically causes the browser to issue a GET to the target URL. There is no guarantee the original POST body is resent.
- `307`/`308` have different method/body-preserving semantics, and **should not be used arbitrarily to "replay" a financial operation** after login.
- `SavedRequest` can store details about the request, yet it does not turn `POST /checkout` into a safe "resume transaction" workflow.
- Anything after login must re-verify CSRF, permissions, order state, idempotency keys, and business invariants.
- For interrupted write operations, the typical UX solution is **saving a server-side draft with a reference code**, bringing the user back to a review/confirm page after authentication and asking them to confirm again rather than automatically replaying side effects.
- For large uploads, build a dedicated upload/resume flow or expiration policy; never store whole file bodies in the session just to resume after login.

Example of a safe purchase flow:

```text
POST /checkout when session expired
    |
    v
Do not execute payment automatically
    |
    v
Save order draft under protected token/context
    |
    v
Login/MFA
    |
    v
GET /checkout/review?id=server-issued-draft-id
    |
    v
Check permissions + CSRF + balance + price + idempotency
    |
    v
User confirms once
    |
    v
POST /checkout/confirm
```

Separately evaluate the sensitivity of entered data, draft retention duration, access limits, and expired-session handling.

## 11. Intentionally enabling, disabling, and scoping `RequestCache`

In a form login application, `HttpSessionRequestCache` usually makes sense. Yet not every route should be saved, especially endpoints for API clients, polling, static assets, or health probes.

### 11.1. Configuring a custom `RequestCache`

The illustrative configuration snippet goes **in another configuration class** or replaces the bean in the main example; **it is not a standalone Java program**:

```java
@Bean
SecurityFilterChain configuredCache(HttpSecurity http) throws Exception {
    HttpSessionRequestCache cache = new HttpSessionRequestCache();

    // Only save GET under reports. Avoid saving POST
    // with side effects or certain technical routes.
    cache.setRequestMatcher(
        new AntPathRequestMatcher("/reports/**", "GET"));

    return http
        .requestCache(requestCache -> requestCache
            .requestCache(cache))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/reports/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(form -> form
            .permitAll()
            .defaultSuccessUrl("/dashboard", false))
        .build();
}
```

Requires imports for `HttpSessionRequestCache` and `AntPathRequestMatcher` from Spring Security 6.x. Note that in newer Spring Security versions, some matcher APIs may be deprecated or differ; use a matcher with compatible semantics for your project, or write a `RequestMatcher` tailored to your intent. **This snippet is illustrative only** and does not replace the main app since `/dashboard` is not opened in its rules. When applying in practice, open the fallback route properly and test. Cache versions/placement can affect both request saving and request matching.

To avoid depending on a specific pattern matcher, an equivalent readable `RequestMatcher` is:

```java
RequestMatcher reportsGet = request ->
    "GET".equals(request.getMethod()) &&
    request.getServletPath().startsWith("/reports/");
cache.setRequestMatcher(reportsGet);
```

This is a **minimal condition snippet**, not a complete URL canonicalization policy; verify context path, servlet mapping, trailing slashes, and real deployment behavior.

### 11.2. The `continue` marker and Spring Security 6

In Spring Security 6, `HttpSessionRequestCache` provides a `matchingRequestParameterName` option, typically `continue`, so `getMatchingRequest` only inspects the session when the URL contains the marker. The goal is to **reduce unnecessary session reads**. With a saved request, the redirect URL may include the marker depending on version/config to trigger restoration on the next GET.

Example of an explicit custom configuration:

```java
HttpSessionRequestCache cache = new HttpSessionRequestCache();
cache.setMatchingRequestParameterName("continue");
```

**Do not misunderstand:** the `continue` marker is not a secret, does not grant permission, and is neither `next` nor an anti-CSRF token. It is a signal to the request cache. Visiting `?continue` cannot replace authentication and authorization. When multiple proxies/SPA routers or URL rewrite logic exist, ensure the marker is neither stripped improperly nor misinterpreted as a business parameter.

### 11.3. `NullRequestCache` when you do not want to save requests

Some APIs using HTTP Basic, JWT bearer, or designed as stateless **do not want** to create an HttpSession just to hold deep links. You can use:

```java
.requestCache(cache -> cache
    .requestCache(new NullRequestCache()))
```

This is a DSL snippet inside `HttpSecurity`; import `org.springframework.security.web.savedrequest.NullRequestCache`. With JSON REST APIs, clients normally handle 401 and resume navigation themselves after authenticating, rather than the server redirecting through form login.

Do not apply `NullRequestCache` application-wide when session-based web pages still require deep-link return; if there are multiple `SecurityFilterChain`s, design the cache per chain and authentication mechanism.

## 12. WebFlux/reactive and SPA: same need, different APIs

The runnable example above is **Servlet**: `HttpSecurity`, `HttpSessionRequestCache`, `SavedRequestAwareAuthenticationSuccessHandler`. With WebFlux, Spring Security uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and corresponding reactive-stack request-cache/redirect components such as `ServerRequestCache`; do not copy Servlet `HttpServletRequest`/`HttpSession` directly to `WebSession`.

In an SPA with a JSON backend or OAuth2 login, "returning to the previous screen" may be managed by the client router. If the SPA stores the intended location in `sessionStorage` or URL state, that content remains **client-controlled data** that must be route-validated and prevented from redirecting to another origin. The backend must still verify API permissions regardless of which screen the frontend returns to.

| Architecture | Who typically holds return state? | Security concerns |
|---|---|---|
| Servlet form login + session | `HttpSessionRequestCache` on server | Session cookie, saved URL, success handler, trusted host |
| Server-rendered app with SSO | Authentication success handler and framework OAuth2/OIDC state | Registered callback URI, transaction binding, login success redirect |
| Spring WebFlux session app | `ServerRequestCache` / `WebSession` per config | Reactive flow, WebSession, redirect policy |
| SPA + bearer-token JSON API | SPA router/state depending on design | Validate local route, no open redirect, API must authorize |
| Machine-to-machine API | Usually does not redirect a browser | 401/403, retry semantics, token refresh, and idempotency |

With OAuth2/OIDC, **`redirect_uri`** is a protocol security callback, distinct from "the UI path to return to after login completes." Do not let clients arbitrarily change the callback for return-navigation convenience. In federation, use the framework's state/authorization request repository and valid callback allowlist.

## 13. Common implementation mistakes

| Statement or code | Consequence | How to fix |
|---|---|---|
| `formLogin(form -> form.defaultSuccessUrl("/dashboard", true))` while expecting deep-link return | Saved request is ignored | Use `false` when prioritizing saved requests |
| Custom success handler always calls `sendRedirect("/home")` | SavedRequest logic lost | Delegate properly or use default configuration |
| `response.sendRedirect(request.getParameter("next"))` | Open redirect/phishing | Server-side allowlist or alias |
| `startsWith("/")` is enough to validate URLs | Can accept `//evil` and parser mismatches | Prefer aliases; if using URLs, canonicalize and check strictly |
| Enabling `targetUrlParameter("next")` without checking trust boundaries | Users force external origins | Keep disabled unless needed; enforce allowlist |
| Using `Referer` as default return URL | Header missing or forged | Use RequestCache or safe fallback |
| Treating post-login redirect as permission to view data | IDOR/BOLA exposure | HTTP + method + object scope checks remain mandatory |
| Allowing GET to perform payments | Saved URL can trigger side effects | Safe GET, mutations via POST + CSRF/idempotency |
| Expecting request cache to auto-replay POST bodies | Forms/uploads/transactions are not safely restored | Draft/review/confirm with duplicate-prevention token |
| Asserting exact redirect URLs in tests | Tests fail due to `continue` or context path | Test path/query semantics and policy |
| Testing `/login` directly while expecting a saved request | Never hit a protected URL first | Test deep link first within the same session |
| Opening multiple browser tabs and assuming per-tab SavedRequests | Returns to the wrong tab | Define multi-tab UX/session state explicitly |
| Disabling CSRF so POST login tests pass | Weakens protection on browser sessions | Use `csrf()` and valid configuration |
| Not configuring trusted Host/proxy | Saved absolute URL may get wrong origin | Allowlist hosts, configure trusted forwarded headers |
| Logging full URLs with sensitive tokens/queries | Credential leakage | Redact logs, avoid tokens in URLs |
| Disabling request cache in a form-login app | Loses deep links | Disable only on APIs/chains that do not need it |
| Using free-form external URLs for SSO return | Redirect URI attack | Fixed registered callbacks, standard state handling |

## 14. Test matrix recommended before release

For an application with users, private routes, and form login:

1. **Anonymous + valid deep link:** `GET /reports/7?view=summary` leads to login, saved request is created, and successful POST login returns to the report.
2. **Direct login:** with no saved request, login returns `/dashboard`.
3. **Wrong credentials:** failed login never grants access to the report; the flow must not self-escalate privileges.
4. **Malicious redirect parameters:** POST login with `next=https://attacker.example`, `next=//attacker.example`, encoded variants, or an external Referer header never causes an external redirect.
5. **Query params:** valid parameters such as view/sort/page are preserved sufficiently to reopen the right screen; no secrets are stored.
6. **Unauthorized user:** after login, redirecting to an out-of-scope resource must be blocked by the service/DB, not bypassed by saved request.
7. **Custom login page:** CSRF token, form action, username/password fields, and save-request continuity all work properly.
8. **Custom success handler:** covers saved request, fallback, and allowlisted alias branches, testing priority order.
9. **Sensitive HTTP methods:** POST/PUT/PATCH/DELETE are not auto-replayed to cause side effects; file uploads have a separate recovery flow.
10. **Multi-tab:** open two protected URLs in the same session before login; behavior is documented and tested per product requirements.
11. **Expired session:** stale saved request is absent or invalid; redirects cleanly to fallback.
12. **Logout then login as another user:** saved request and related data do not leak cross-user information.
13. **Session fixation:** session ID changes after login per policy; the old anonymous ID cannot access private routes.
14. **Trusted host/proxy:** in staging behind a gateway, Location header uses the official HTTPS host, not a domain from spoofed Host/forwarded headers.
15. **Multiple security chains:** which chain redirects to a form, which returns 401 JSON, which enables/disables request cache; do not mix the two mechanisms.
16. **CORS/CSRF:** browser navigation differs from JSON clients; do not "fix redirects" by opening wrong matchers or disabling exploit protections.

Negative tests (unsafe targets, wrong permissions, different sessions, non-replayed side effects) are often as important as or more important than the happy path "log in and return to the right page."

## 15. Code review checklist for return URLs

- [ ] Identified the authentication mechanism: form session, OAuth2/OIDC, WebFlux, or stateless SPA/API?
- [ ] Protected URLs pass through the filter chain and `ExceptionTranslationFilter`/request cache as expected?
- [ ] `defaultSuccessUrl` uses `false` or `true` intentionally and is tested?
- [ ] Does a custom `successHandler` preserve/delegate SavedRequest functionality?
- [ ] Never assign `next`/`returnUrl`/`redirect`/`Referer` directly into `Location`.
- [ ] If UI-selected destinations are needed, prefer a **server-side alias allowlist**.
- [ ] If external callbacks are needed, enforce an exact origin/URI allowlist and standard protocol mechanisms.
- [ ] Host/forwarded headers are controlled by trusted proxies; no Host header poisoning.
- [ ] Post-login redirect does not replace endpoint/data authorization.
- [ ] Never replay POST/PUT/DELETE or uploads via redirect; provide clear draft/retry/idempotency if needed.
- [ ] Session/cookies and RequestCache remain valid across login, and session fixation protection is not disabled.
- [ ] Fallback route exists, is accessible to valid logged-in users, and creates no loop.
- [ ] SavedRequest does not hold queries with tokens/secrets, and logging applies redaction.
- [ ] Tests exist for: deep link, direct login, malicious next, wrong owner, multi-tab, expired session, and proxy.
- [ ] Tested against production topology (TLS termination, ingress, context path, hostname).

## 16. Self-check exercises

**Exercise 1.** A user opens `/reports/7?view=summary` while unauthenticated; after login the app uses `defaultSuccessUrl("/dashboard", false)`. Which destination takes priority?

**Answer:** When `RequestCache` has saved the request properly and the success handler can use saved requests, the original report URL takes priority. `/dashboard` is only the fallback.

**Exercise 2.** What happens if `false` is changed to `true` in `defaultSuccessUrl`?

**Answer:** The handler selects `/dashboard` even when a saved request exists; the related saved request is ignored/cleared per handler semantics. That is an intentional UX choice, not a random bug.

**Exercise 3.** What is the risk of calling `response.sendRedirect(request.getParameter("next"))` after login?

**Answer:** Open redirect if an attacker passes an external host or encoded variant. Use an alias allowlist or server-constructed routes.

**Exercise 4.** There is a SavedRequest to Bob's report, and Alice logs in successfully. Does Alice receive Bob's content?

**Answer:** Not merely from being redirected. The backend must still verify object/tenant read permissions at the target URL. SavedRequest grants no permissions.

**Exercise 5.** Why does testing POST login need `csrf()`?

**Answer:** When session-based Spring Security enables CSRF protection, form POST needs a valid token; if missing, the request can get 403 before authentication, preventing the test from checking the return URL.

**Exercise 6.** Why should a saved request not automatically retry a payment POST?

**Answer:** Redirects have no contract guaranteeing safe method/body replay, and auto-replaying mutations can cause duplicate transactions. Use draft/review/confirm, CSRF, and idempotency instead.

**Exercise 7.** In Spring Security 6, seeing `?continue` after a redirect—does that mean an attack occurred?

**Answer:** Do not conclude that. It can be a valid marker from `HttpSessionRequestCache` used to retrieve the saved request. It is not an authorization token and does not replace authentication. Check against your running configuration and version.

**Exercise 8.** If you want users to return to a UI-selected page, which solution minimizes URL parsing risks most?

**Answer:** Have the UI send a finite code like `dashboard`/`report-seven`; the backend maps the code to an approved local route. Do not accept arbitrary paths unless strictly necessary.

## 17. Official references

- [Spring Security 6.5 — Servlet Architecture, Saving Requests Between Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `ExceptionTranslationFilter`, `RequestCache`, `RequestCacheAwareFilter`, and session-checking configuration with `continue`.
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): priority order of default target, target parameter, saved request, and fallback.
- [Spring Security 6.5 — AbstractAuthenticationFilterConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): semantics of `defaultSuccessUrl(String, boolean)` and custom `successHandler`.
- [Spring Security 6.5 — FormLoginConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html): form login, login processing URL, and default login page.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF in browser sessions and testing.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): cookies, session fixation protection, login flow.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): open redirect risks, destination allowlists.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): protecting state-changing operations.

**Conclusion:** To preserve the deep-link experience after login, use the default `RequestCache` + `SavedRequestAwareAuthenticationSuccessHandler` before writing custom logic. Configure `defaultSuccessUrl("/dashboard", false)` when prioritizing the prior request with a safe fallback. Never turn client-supplied `next`/`returnUrl` into an arbitrary HTTP redirect; if destination choices are needed, use a server-side allowlist and protect permissions on the target URL like any normal request.
