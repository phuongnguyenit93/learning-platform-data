# Invalid CSRF Token After Login, Session Expiration, or Multiple Open Tabs

> **Context:** Spring Security 6.x, Spring Boot 3.x, Java 17+, **Servlet stack** (Spring MVC, sessions/cookies, and server-rendered UIs or SPAs). The goal is **diagnosing** CSRF 403 errors after login, logout, session expiration, long-lived forms, or multi-tab usage; finding the exact cause and fixing it **without disabling CSRF protection**. This guide distinguishes server-stored tokens, browser-sent tokens, authenticated sessions, tokens cleared on authentication changes, and Spring Security 6's deferred loading and token masking mechanisms. Java/Spring examples require a project with matching dependencies; HTTP/JS code illustrates integration, not standalone Java SE programs.

## 1. Common Symptoms and Key Takeaways

Users may run into seemingly random failures:

- Immediately after logging in, clicking **Save** on a previously loaded form returns **403 Forbidden**.
- Leaving a tab open for a long time, entering data, and POSTing after session expiration: the action is denied, sometimes without redirecting to the login page as expected.
- Opening two tabs of the same app; logging out or signing in with a different account in tab B, returning to tab A and clicking **Submit**, getting a token error.
- An SPA performs GET requests normally, yet POST/PUT/DELETE after login, session refresh, or tab switching returns 403.
- The error occurs only on frontend POSTs, while a MockMvc test using `.with(csrf())` still passes.
- 403 errors coincide with switching load-balanced nodes or session cookie changes in the browser.

**Not every 403 is a CSRF error.** Spring Security also returns 403 when an **authenticated user lacks permission**; conversely, an unauthenticated request may get 401/302 in other flows. Determine whether the request was blocked by **`CsrfFilter`**, an authorization filter, session policy, or another handler.

**Opening multiple tabs by itself does not invalidate CSRF tokens.** Tabs sharing the same origin and browser profile normally share session cookies. As long as the same session remains valid and the server token has not been cleared/replaced, forms across multiple tabs can still use valid tokens. Failures happen when **shared state changes** (login/logout/session timeout/session regeneration, different session, or a request carrying the wrong token)—not because of the tab count.

## 2. CSRF and the Two Sides of a Check

CSRF (*Cross-Site Request Forgery*) exploits the fact that browsers **automatically attach credentials** (such as login cookies) to HTTP requests. A malicious site can cause the browser to submit unwanted actions to the target application. Spring Security's CSRF protection requires protected requests to carry an appropriate token value that an attacker site cannot arbitrarily obtain from the victim app.

On the Servlet stack with default session storage, visualize it as:

~~~text
Browser                 Spring Security Servlet
   | GET /form                 |
   |-------------------------->|
   |                  CsrfTokenRepository
   |                  get/generate expected token
   |<--- HTML form + token ---|
   |                          |
   | POST /transfer           |
   | Cookie: JSESSIONID=...   |
   | _csrf=token-sent         |
   |-------------------------->|
   |                          | CsrfFilter
   |                          | load expected token (from session)
   |                          | resolve actual token from form/header
   |                          | compare securely
   |                          |
   |<-- allowed or 403 -------|
~~~

This is a **conceptual diagram**: in Spring Security 6, tokens can be **lazily loaded (deferred)** and **masked (XOR/BREACH)** when exposed to clients. The string rendered in HTML/JSON **need not equal verbatim** the raw token stored in the session, even though both correspond to the same underlying token.

Distinguish three things:

| Concept | Where It Lives | Role |
| --- | --- | --- |
| **Expected token** | Server-side `CsrfTokenRepository`, typically tied to the HTTP session or a cookie repository per config. | Ground truth used to validate requests. |
| **Actual/presented token** | The `_csrf` form field or HTTP header such as `X-CSRF-TOKEN` sent by the browser. | Value presented by the client on the request. |
| **HTTP session / authentication** | Browser holds the session cookie; server holds session, `SecurityContext`, and session lifecycle. | Establishes context for loading the token and user; may change on login/logout/timeout. |

**A token does not prove user authorization.** Passing CSRF does not mean the user holds `ROLE_ADMIN` or may modify a record. Authorization must still check identity, roles, and object-level permissions.

### Which HTTP Requests Normally Require CSRF?

In Spring Security's default setup, *unsafe* HTTP methods such as `POST`, `PUT`, `PATCH`, and `DELETE` undergo CSRF checks; methods such as `GET`, `HEAD`, `OPTIONS`, and `TRACE` are treated as safe. This rule relies on **HTTP method semantics**. If an app uses GET to mutate data, that is a design bug to fix—default CSRF cannot protect side effects on GET.

**Note:** an API that accepts only an explicit Bearer token via `Authorization` and does not rely on browser-autosent credentials has a different threat model from session/cookie apps. Never disable CSRF solely because a route starts with `/api`; inspect the **actual authentication mechanism** and whether browsers can send credentials automatically.

## 3. Default CSRF Token Lifecycle in Spring Security 6

A typical Servlet configuration uses:

- `HttpSessionCsrfTokenRepository`: stores the expected token in the HTTP session.
- `CsrfFilter`: protects requests requiring CSRF by comparing the actual token against the expected token.
- `XorCsrfTokenRequestAttributeHandler`: in Spring Security 6, the default handler usually generates a **randomly masked** representation when exposing the token as a request attribute to mitigate BREACH.
- `DeferredCsrfToken`: loads/generates the token **on demand** instead of creating a session/token on every GET.
- `CsrfAuthenticationStrategy`: when a successful authentication flow executes this strategy, the existing CSRF token is cleared so a new token is generated for the post-login session/state.
- `CsrfLogoutHandler`: during standard logout handling, the token may be cleared so old tokens cannot be reused.

Do not treat “clearing the token at login” as a bug: it is **intentional behavior** so a token from an anonymous state or prior authentication does not carry over after identity changes.

### Timeline Table to Observe

| Moment | Session / State | Token in Old Tab's Form | Risk |
| --- | --- | --- | --- |
| Before login | Session A or an anonymous state holds expected token T1. | Tab A holds a representation of T1. | T1 may be valid within state A. |
| Login succeeds | Authentication strategy may rotate session ID and **clear the CSRF token**. | Tab A still holds T1 in DOM/JS. | POST using T1 can return 403. |
| GET new page/form | New token T2 is materialized when the view/controller needs it. | New tab holds a representation of T2. | Uses the token issued for the current state. |
| Session expires / new session | Expected token T2 may no longer exist in the session. | Old tab still holds T2. | Old POST can return 403 before business logic. |
| Logout | Session/authentication is cleared; CSRF token is typically cleared. | Open tab holds old token. | Must fetch a new token before next login/POST. |
| Two tabs without login/logout/timeout | Same session; expected token unchanged. | Each tab may show different strings due to XOR masking. | Both tokens remain valid. |

T1 and T2 here are **illustrative symbols**, not literal Spring Security output formats.

**An important detail:** Spring Security session fixation protection may rotate `JSESSIONID` via `changeSessionId`. However, never conclude “changing ID is the only reason the token failed”: **`CsrfAuthenticationStrategy` clearing the token** is an essential part of the login lifecycle. Analyze both session and CSRF strategies rather than tweaking a random session fixation property.

## 4. Why Does 403 Happen Right After a Successful Login?

### 4.1 Form Loaded Before Logging In

Scenario:

1. The user opens a page with a form and receives anonymous CSRF token T1.
2. The app requires login; the user signs in successfully.
3. Upon authentication success, the old CSRF token is cleared/rotated per Spring Security's strategy.
4. The un-re-rendered form submits T1.
5. `CsrfFilter` compares against the current expected token and rejects the request.

**How to handle:** after login succeeds, the app must **fetch a fresh CSRF token from the server** before sending state-changing requests. For server-rendered pages, redirecting/GETting to re-render the form is standard. For SPAs, call a dedicated `GET /csrf` endpoint and update the token in memory.

### 4.2 The Login Form Also Needs a CSRF Token

Another misconception: “Login happens before a session exists, so POST `/login` needs no CSRF”. In standard session/cookie form-login apps, login CSRF protection matters too, preventing login CSRF attacks. The token can be issued when rendering the login form or via GET `/csrf`. After login, that token may be cleared, so do not reuse it for subsequent business POSTs.

**Do not fix by calling `csrf.disable()` or exempting all of `/login` without a dedicated security analysis.** Ensure the login form sends a valid token and the frontend refreshes its token after authentication changes.

### 4.3 Authentication Does Not Leave the Session “Immutable”

Logging in can trigger session fixation protection, session attribute migration, `SecurityContext` persistence, concurrent-session control, and cookie updates. A browser/SPA holding a pre-login token in JavaScript can fall out of sync with the new state. The goal is **synchronizing the token with the current session**, not pinning `JSESSIONID` or keeping old CSRF tokens forever.

### 4.4 Successful Login Redirect Does Not Auto-Refresh Other Tabs

Tab A still holds its old HTML/JS snapshot even after tab B logs in and redirects to a new page. Browsers do not automatically re-render tab A. When tab A clicks Submit, the request sends the new session cookie paired with the stale actual token—a classic **token/session desynchronization**.

## 5. Why Does an Expired Session Cause CSRF 403 Instead of a Login Page?

With `HttpSessionCsrfTokenRepository`, the expected CSRF token lives in the session. Once the server removes the session due to timeout, invalidation, or session-store eviction:

~~~text
Tab opened before expiration:
  HTML has _csrf=T_old
  Browser still sends Cookie JSESSIONID=old...

Server:
  old session expired / does not exist
  old expected token is gone

Browser POST:
  body _csrf=T_old
  request may be seen as unauthenticated
  CsrfFilter finds token mismatch against current expected
  --> HTTP 403 (in typical configurations)
~~~

**Why not always 302 to login?** Filter ordering and exception handling can cause `CsrfFilter` to reject unsafe requests **before** the authentication entry point runs. A GET after timeout can 302 to login, while a POST with a stale token returns 403. Depending on configuration, that is expected behavior.

### UX Handling for Long-Lived Forms

- Warn users before session expiration if the app has reliable timing metadata.
- For large forms, safeguard drafts carefully on the client; **never store sensitive data in `localStorage`** unless your threat model explicitly permits it.
- On session/CSRF validation failure, prompt the user to re-authenticate or refresh the session and **obtain a fresh CSRF token**. Resubmit only after confirming user intent and validating the form data.
- Never auto-retry every POST that gets 403: 403 can also mean **insufficient permissions**. Auto-retrying state-changing requests can also cause **duplicate side effects** if a response was lost after server execution.
- For large edits, consider controlled autosaves, idempotency keys, and explicit recovery policies.

## 6. Multiple Tabs: Which Cases Actually Break the Token?

Tabs sharing a browser profile and origin normally share cookies, yet **each tab has its own DOM and JavaScript state**. Thus:

| Multi-Tab Scenario | Does CSRF Token Fail? | Explanation |
| --- | --- | --- |
| Tabs A and B load forms under the same session, with no auth change. | **Not necessarily.** | Both can use valid tokens; differing masked strings from XOR do not mean the expected token changed. |
| Tab B logs in; tab A holds an old pre-login form. | **Likely.** | Login clears the old token; tab A has not fetched the new one. |
| Tab B logs out; tab A holds a private form. | **Likely.** | Logout/session reset changes both token and authentication; tab A is stale. |
| Tab B logs in as another user in the same cookie jar. | **Likely and more sensitive.** | Principal and CSRF token in tab A no longer match current state; must refresh and confirm intent. |
| Tab A sits open past session timeout; tab B reopens the app. | **Likely.** | New session has a new token; tab A's form holds the stale token. |
| Tab B merely GETs a new page; session unchanged. | **Normally no.** | An ordinary GET does not rotate the expected CSRF token by default. |
| Two separate browser profiles / incognito windows. | Tokens are not interchangeable. | Separate cookie jars and sessions; taking a token from one profile to another fails. |
| Two app nodes with unsynchronized session stores. | **Likely.** | Request reads expected token on a node lacking the session state that created it. |

**Correct diagnosis:** determine **which session** the POST belongs to and when the expected token was cleared/replaced. Never blame “multiple tabs” and switch to a global token shared across all users.

### Hint for Syncing Tabs Without Broadcasting Secrets

The frontend can use `BroadcastChannel` or login/logout events to announce **“authentication state changed”** to same-origin tabs. Each tab independently calls `/csrf` to fetch a token for the current session. Never send sensitive tokens or cookies over broadcasts, and never trust broadcast messages as proof of authentication/authorization: browser state can be tampered with, whereas the server is the authority.

## 7. Deferred Tokens and XOR Masking in Spring Security 6: Common Debug Traps

In Spring Security 6 Servlet, CSRF handling has two easily misunderstood aspects:

1. **Deferred loading:** the token repository is not necessarily read or populated on **every GET**. The token is materialized when a page/form/controller actually accesses it. After login/logout clears the token, an SPA must explicitly request a fresh token before issuing unsafe requests.
2. **BREACH/XOR masking:** `XorCsrfTokenRequestAttributeHandler` can transform the raw token into a **randomly masked value** when exposing it to HTML or request attributes. Two renders can yield two different strings even while the underlying expected token **has not changed**.

Conceptual example:

~~~text
Expected raw token in session: R
GET /form tab A: masked token = M1
GET /form tab B: masked token = M2

M1 != M2
Yet both represent raw token R while still in the session
POST with M1 or M2 -> both can succeed
~~~

**Never compare token strings in HTML across two GETs and conclude Spring rotated the expected token.** Spring Security's handler decodes the masked actual token before comparing it with the raw expected token.

### Cookie Tokens vs. Request Attribute Tokens Differ

`HttpSessionCsrfTokenRepository` (common default) stores the expected token in the session; `CookieCsrfTokenRepository` stores it in a configured cookie. In SPAs, many teams read the `XSRF-TOKEN` cookie and send an `X-XSRF-TOKEN` header.

However, when `XorCsrfTokenRequestAttributeHandler` is active for BREACH protection, **the raw token read directly from the cookie** and **the masked token read from the request attribute** have different formats. An SPA setup needs an SPA-compatible `CsrfTokenRequestHandler` that handles both raw headers and masked form tokens, or an endpoint returning the masked token for the header so the default handler accepts it.

When using a cookie repository, do not blindly switch to the plain `CsrfTokenRequestAttributeHandler` without evaluating BREACH risk. Follow the SPA integration pattern matching **your exact Spring Security version** and test both forms and XHR.

**Remember:** a cookie holding a CSRF token is **not a login cookie**. A CSRF token never replaces a session ID, password, OAuth2 access token, or authorization.

## 8. Spring Security 6 Configuration Keeping Default CSRF

Example Boot 3.x app with form login and a session-backed API. Keep default CSRF protections; never disable them over 403 errors.

File `src/main/java/com/example/csrf/CsrfSecurityConfig.java`:

~~~java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CsrfSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/csrf", "/error")
                    .permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

- `.csrf(Customizer.withDefaults())` emphasizes using default CSRF—it does **not** create a global token and does **not** disable `CsrfFilter`.
- `.formLogin(form -> form.permitAll())` enables form login (using Spring Security's generated login page) and permits related login endpoints; form login POST also goes through CSRF under defaults.
- `GET /csrf` is public so the login page/SPA can fetch a token pre-login; it is a **session token**, not account data. Restrict caching, CORS/credentials, and never send tokens to untrusted origins.
- `/api/**` requires authentication, yet **does not enforce per-resource permissions yet**. Real apps need role/permission/owner/tenant authorization.
- Successful login may rotate the session ID and clear the old token; the `/csrf` controller next issues the current token on demand.
- `CsrfAuthenticationStrategy` and `CsrfLogoutHandler` tie into Spring Security's standard auth/logout lifecycle. If you replace authentication filters, session strategies, or logout handlers, test the actual token lifecycle rather than assuming it matches default form login.

### Dependencies for the Java Example

In a Spring Boot project using Maven parent/BOM and Java 17+, required dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is a **`pom.xml` fragment**, not a complete POM; let Spring Boot manage compatible dependency versions. If using Thymeleaf for Section 10, add `spring-boot-starter-thymeleaf`.

### Main Class for the Demo

File `src/main/java/com/example/csrf/CsrfDemoApplication.java`:

~~~java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
~~~

## 9. Issuing Fresh Tokens via GET /csrf for SPAs and Post-Login

A dedicated endpoint can accept `CsrfToken` from Spring Security's request and return what the client needs for headers/forms.

File `src/main/java/com/example/csrf/CsrfController.java`:

~~~java
package com.example.csrf;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    public record TokenView(
            String headerName, String parameterName, String token) {
    }

    @GetMapping("/csrf")
    public TokenView csrf(CsrfToken token) {
        return new TokenView(
                token.getHeaderName(),
                token.getParameterName(),
                token.getToken());
    }
}
~~~

**Key point:** calling `token.getToken()` yields the value processed by the handler for that request context and materializes any deferred token. With default XOR masking, the returned string may be a **masked token**. Clients must send back that exact value in the expected header/parameter; never decode it or copy tokens across sessions.

An **illustrative** JSON response might look like:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "value-issued-by-server-for-current-session"
}
~~~

The `token` value above is an **illustrative string**, not a real or usable token. Actual header/parameter names come from the response; with default `HttpSessionCsrfTokenRepository`, they are typically `X-CSRF-TOKEN` and `_csrf`.

### Do Not Turn /csrf Into a Shared Token Dispenser

- Issue tokens bound strictly to the active **request/session**; never cache tokens in singleton beans, static fields, or an application-wide map.
- Prevent CDN/browser caching of token JSON across requests; check `Cache-Control` and reverse proxies. `no-store` is appropriate when designing the endpoint.
- Never allow arbitrary origins to read credentialed responses; restrict CORS and cookie scopes.
- Guard against XSS and HTML/JS leaks. XSS can read same-origin data/tokens, so CSRF protection **never replaces** output encoding, CSP, and XSS defenses.
- When `GET /csrf` is public for anonymous callers so login works, do not include user profiles or sensitive data in the same response.

## 10. Server-Rendered Forms: Rendering Tokens with the Current Session

With Thymeleaf + Spring MVC integrated with Spring Security, POST forms rendered with `th:action` typically receive a hidden CSRF field from Spring Security's `RequestDataValueProcessor`.

Example `src/main/resources/templates/note-form.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Notes</title>
</head>
<body>
    <h1>Save note</h1>
    <form th:action="@{/api/notes}" method="post">
        <label for="text">Content</label>
        <input id="text" name="text" required>
        <button type="submit">Save</button>
    </form>
</body>
</html>
~~~

In standard Spring MVC/Thymeleaf setups, `th:action` plus Spring Security integration automatically inserts the hidden CSRF field when rendering the form. **Inspect the rendered HTML** to confirm `input name="_csrf"` and a valid value actually appear. Do not add a duplicate hidden field with the same name if integration already emits one, as sending multiple values complicates diagnostics.

With JSP or custom HTML, you can read the `_csrf` request attribute into a hidden input. Example template fragment when `_csrf` is available:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

This is a **standalone illustrative Thymeleaf fragment**; do not append it to a `th:action` form that already injects the token without inspecting the rendered output. In real Thymeleaf templates, use `th:name="${_csrf.parameterName}"` and `th:value="${_csrf.token}"` so the engine substitutes the current request's values; the `${...}` syntax in this example was written directly in Thymeleaf syntax prior to saving.

**For long-lived forms:** a server-rendered page holds only the token **from render time**. If the session changes, nothing updates hidden fields in stale DOMs. After login/logout or timeout, redirect via GET and re-render the form; for UIs preserving user input, store drafts carefully and restore them **after the user re-authenticates**.

### Session Timeouts Should Not Be Solved by Keeping Old Tokens Forever

Some developers try storing CSRF tokens in `localStorage` and reusing them across new sessions. That **does not** make an old token valid: the server's expected token is tied to the current session/repository. Persisting tokens long-term also widens exposure and confuses lifecycles. Always obtain the current token for the active session instead of reusing tokens from expired sessions.

## 11. SPA/Fetch: Refreshing Tokens After Authentication Changes

An SPA usually keeps the token in memory and sends it in an HTTP header. With the `GET /csrf` endpoint from Section 9, you avoid brittle cookie/raw-token handling by fetching the token **issued by Spring Security's handler for the request**.

~~~javascript
let csrfState = null;

async function refreshCsrf() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Failed to fetch CSRF token for current session");
  }

  const data = await response.json();
  if (!data.token || !data.headerName) {
    throw new Error("Invalid CSRF response");
  }
  csrfState = data;
}

async function createNote(text) {
  if (!csrfState) {
    await refreshCsrf();
  }

  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrfState.headerName]: csrfState.token
    },
    body: JSON.stringify({ text })
  });

  if (response.status === 403) {
    // 403 could be CSRF or insufficient permission; do not auto-retry POST.
    throw new Error("Request denied; check session and permissions");
  }

  if (!response.ok) {
    throw new Error("Failed to save note");
  }

  return response.text();
}
~~~

Proper usage:

1. The SPA initializes `refreshCsrf()` before issuing unsafe requests.
2. After **successful login** once the new session cookie is active, call `refreshCsrf()` again; never reuse pre-login tokens.
3. After logout, if the SPA renders a login POST form, call the token endpoint again in the **new** anonymous context.
4. Upon receiving a session-change signal from another tab, refresh the token, update UI state, and reflect the active account. Never continue submitting an old user's actions under a new user's session.
5. If POST returns 403, classify the error per server design (secret-free error codes/logs). Never blindly retry all 403s, especially for payments, deletes, submissions, and non-idempotent actions.

This is **browser JavaScript**, not standalone Node code. `createNote` assumes the backend handles POST `/api/notes`. When accepting JSON, configure controllers/services properly and **still enforce authorization**.

### Using CookieCsrfTokenRepository and the X-XSRF-TOKEN Header

Spring Security offers `CookieCsrfTokenRepository` for apps wanting to expose the CSRF token via a cookie. When JavaScript needs to read the cookie, a commonly cited snippet is:

~~~java
http.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

This is a **configuration fragment** inside `HttpSecurity` configuration requiring `org.springframework.security.web.csrf.CookieCsrfTokenRepository`. Use it only when the app **genuinely needs JS to read the CSRF cookie**; keeping `HttpOnly` enabled when JS does not need to read cookies is safer regarding token exposure.

**Important in Spring Security 6:** cookies normally contain raw tokens, whereas request attributes may be XOR-masked. If the frontend reads raw cookie `XSRF-TOKEN` and sends header `X-XSRF-TOKEN`, configure an SPA-compatible `CsrfTokenRequestHandler` (distinguishing raw headers from masked form tokens), and handle deferred tokens plus clearing on login/logout. **Swapping only the repository as above is not enough** for all SPA flows to work.

Never adopt `CookieCsrfTokenRepository` merely to evade session timeout errors; it carries its own lifecycle and risks. CSRF tokens must never act as access tokens, never replace authentication, and must be tested across session/authentication changes.

## 12. Example Application for Testing the Real Lifecycle

This section builds a minimal Java 17+ / Spring Boot 3.x app testing both login and CSRF. Classes live in `com.example.csrf`, alongside `CsrfSecurityConfig`, `CsrfDemoApplication`, and `CsrfController` from earlier.

### Demo User for Form Login

File `src/main/java/com/example/csrf/DemoUsers.java`:

~~~java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsers {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password(encoder.encode("local-demo-password"))
                    .roles("USER")
                    .build());
    }
}
~~~

`local-demo-password` is an **illustrative local test password**, never for production. Real passwords must be governed by secret/user stores and proper authentication policies. The demo omits MFA, LDAP, and IdPs.

### Endpoint Requiring CSRF and Authentication

File `src/main/java/com/example/csrf/NoteController.java`:

~~~java
package com.example.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NoteController {

    @PostMapping(value = "/api/notes",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> create() {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body("saved");
    }
}
~~~

This endpoint simply returns a string for testing and handles no sensitive data. Real applications must validate input, enforce server-side authorization/owner/tenant checks, and guard against duplicate side effects on client retries.

## 13. MockMvc Test: Stale Token After Login Is Rejected

This suite **does not use `@WithMockUser`** to simulate login, because the objective is observing the token being cleared by the authentication strategy inside the sample app's **real form-login filter chain**.

File `src/test/java/com/example/csrf/CsrfLifecycleTest.java`:

~~~java
package com.example.csrf;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    private record TokenData(
            String header, String parameter, String value) {
    }

    private TokenData fetchCsrf(MockHttpSession session)
            throws Exception {
        MvcResult response = mvc.perform(get("/csrf").session(session))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode body =
                json.readTree(response.getResponse().getContentAsString());

        return new TokenData(
                body.path("headerName").asText(),
                body.path("parameterName").asText(),
                body.path("token").asText());
    }

    private void login(MockHttpSession session, TokenData before)
            throws Exception {
        mvc.perform(post("/login")
                .session(session)
                .param("username", "alice")
                .param("password", "local-demo-password")
                .param(before.parameter(), before.value()))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void oldTokenIsRejectedAfterSuccessfulLogin() throws Exception {
        MockHttpSession session = new MockHttpSession();
        TokenData anonymous = fetchCsrf(session);

        login(session, anonymous);

        // Pre-login CSRF token is no longer valid.
        mvc.perform(post("/api/notes")
                .session(session)
                .header(anonymous.header(), anonymous.value()))
            .andExpect(status().isForbidden());

        // Fetch a fresh token in the authenticated session.
        TokenData current = fetchCsrf(session);
        mvc.perform(post("/api/notes")
                .session(session)
                .header(current.header(), current.value()))
            .andExpect(status().isCreated());
    }

    @Test
    void twoTabsWithSameSessionDoNotAutomaticallyInvalidateToken()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        login(session, fetchCsrf(session));

        TokenData tabA = fetchCsrf(session);
        TokenData tabB = fetchCsrf(session);

        // Two different XOR representations can both remain valid.
        mvc.perform(post("/api/notes")
                .session(session)
                .header(tabA.header(), tabA.value()))
            .andExpect(status().isCreated());

        mvc.perform(post("/api/notes")
                .session(session)
                .header(tabB.header(), tabB.value()))
            .andExpect(status().isCreated());
    }

    @Test
    void oldTokenIsRejectedWhenItsSessionIsGone() throws Exception {
        MockHttpSession oldSession = new MockHttpSession();
        TokenData oldToken = fetchCsrf(oldSession);

        // Simulate a request arriving in a new/different session.
        MockHttpSession newSession = new MockHttpSession();

        mvc.perform(post("/api/notes")
                .session(newSession)
                .header(oldToken.header(), oldToken.value()))
            .andExpect(status().isForbidden());
    }
}
~~~

Reading the tests:

1. `fetchCsrf(session)` sends a GET to force token materialization and reads the header/parameter/value provided by Spring Security.
2. `login(...)` sends a real POST through Spring Security's form-login filter with a **valid pre-login token**; after authentication, the CSRF strategy clears the used token.
3. `oldTokenIsRejectedAfterSuccessfulLogin` shows that submitting the old token gets 403, while a freshly fetched post-login token succeeds.
4. `twoTabsWithSameSessionDoNotAutomaticallyInvalidateToken` intentionally fetches two token representations under the same post-login session and POSTs both; never assume adding a tab invalidates tokens on its own.
5. `oldTokenIsRejectedWhenItsSessionIsGone` simulates a token from session A arriving in session B; this tests CSRF rejection, **not** wall-clock expiration or session store management.

**Limitations:** MockMvc simulates Servlet request/response and sessions inside a JVM test; it does not run a real browser, `SameSite` cookies, reverse proxies, TLS, or load balancers. To test real session timers and browser back navigation, add browser/server integration tests in a matching environment.

Run in a complete Maven project:

~~~bash
mvn test
~~~

Final pass/fail output must be observed on your actual project and version; never fabricate Maven stdout. If tests diverge due to custom filters, CSRF repositories/handlers, or Spring Security version, inspect the configuration instead of relaxing assertions to hide failures.

## 14. MockMvc Helps Test CSRF, Yet Does Not Prove Token Lifecycle Alone

Spring Security Test provides request post-processors:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/api/notes").with(csrf()))
   .andExpect(status().isCreated());

mvc.perform(post("/api/notes").with(csrf().useInvalidToken()))
   .andExpect(status().isForbidden());
~~~

This is an **illustrative test snippet**: for the first request to succeed, an appropriate `Authentication` (e.g., `@WithMockUser`) and Spring Security-integrated `MockMvc` are also needed. `csrf()` prepares a valid test CSRF token; `csrf().useInvalidToken()` injects an invalid token to verify filter rejection.

This tool is great for testing **CSRF policy at an endpoint**, yet does not prove real login clears tokens or session timeout invalidates them. To test lifecycle behavior, generate tokens through a **real request flow in the test context** as in Section 13.

### Choosing the Right Test Question

| Test Type | What It Can Prove | What It Does Not Prove |
| --- | --- | --- |
| `@WithMockUser` + `csrf()` | Endpoint denies/allows with synthetic identity and valid CSRF. | Login/filter rotation, passwords, session timeout. |
| `csrf().useInvalidToken()` | Requests with a wrong actual token are rejected by CSRF filter. | Why real user tokens became invalid. |
| MockMvc GET `/csrf` → POST `/login` → POST old token | Token flow/strategy in the Servlet test configuration. | Browser cookie policies or cluster session replication. |
| Server integration test with real timeout | Behavior after actual server session expiration. | All browser variants unless using a real browser. |
| Multi-tab browser E2E | Real behavior across login/logout/stale tabs/back-cache. | Every node/tenant/production topology if tested in another environment. |

**Avoid 403s passing for the wrong reason:** when testing authorization, supply a valid CSRF token. When testing CSRF, supply an authorized principal; otherwise the same HTTP 403 may come from a different cause.

## 15. Ordered Diagnosis: From Response to Session

When encountering a CSRF 403 incident, rather than disabling security, follow these questions:

### Step 1 — Pinpoint the Exact Failing Request

Record **HTTP method, URL, status, timestamp, tab, and preceding action**. Was the failing request login POST, form submit, XHR save, logout, or a management endpoint? Confirm the route traverses the Spring Security filter chain you think applies.

Never paste raw session cookies, passwords, CSRF tokens, or `Authorization` headers into public tickets.

### Step 2 — Check Whether 403 Is CSRF or Authorization

In test/dev environments with controlled logging, Spring Security can report whether `CsrfFilter` rejected for a missing/invalid token. Related exceptions include `MissingCsrfTokenException` and `InvalidCsrfTokenException` (depending on request/repository/handler). If it is an `AccessDeniedException` from authorities, fix permissions instead of refreshing CSRF blindly.

You can temporarily raise logging in dev/test:

~~~properties
logging.level.org.springframework.security.web.csrf=DEBUG
logging.level.org.springframework.security=DEBUG
~~~

Never enable verbose credential-exposing logs in production without review. When correlation is needed, log request IDs and **suitably hashed/redacted** session identifiers—never raw `JSESSIONID` or tokens.

### Step 3 — Inspect Session Cookies on the Failing Request

In DevTools Network (in permitted environments), observe:

- Was a session cookie sent? Did `JSESSIONID` change after login/logout?
- Do cookie `Path`, `Domain`, `Secure`, and `SameSite` match the URL? Is the app behind a reverse proxy changing hostnames/schemes?
- Did the browser block the cookie due to `SameSite`/third-party cookie policies?
- Did the request reach the expected host, protocol, context path, and node/cluster/session store?
- Had the session timed out or been invalidated by logout/re-login in another tab?

**Never paste raw cookies into logs or chat.** A changing session cookie can be legitimate login/session-fixation behavior or wrong cookie scope—not automatically an attack.

### Step 4 — Inspect the Token Actually Sent

For server-rendered forms, check whether the `_csrf` hidden field was rendered and submitted with the right name/value. For SPAs, check whether `X-CSRF-TOKEN`/`X-XSRF-TOKEN` appears in the request as expected.

Do not compare raw cookies and hidden token strings manually: the XOR handler makes them look different even when valid. Verify by replaying through Spring Security's handler rather than direct string comparison.

Common technical causes:

- Frontend fetches token only pre-login and never refreshes after login.
- JS holds a token in memory while another tab's logout/login changed the session.
- Server-rendered page was cached; browser returned to a stale form via back-forward cache.
- Form built as plain HTML without the hidden token.
- Wrong header name or stripped by proxy.
- CORS/preflight or credential mode prevented sending the session cookie.
- Cookie repository used with raw tokens while handler expects masked tokens.
- Session store lost state on load-balancer node switch, or session serialization failed.
- CSRF repository customized on a chain unknown to the frontend.

### Step 5 — Inspect Authentication Lifecycle

Determine whether login or logout happened between the form GET and the POST. With default Spring Security form login, authentication success can clear the CSRF token; logout can clear it too. If the app uses custom OAuth2/SAML login, custom filters, or API login, inspect **the actual token-clearing strategy** rather than assuming all logins behave identically.

With multiple tabs, identify which tab triggered the auth change. One tab signing in as user B switches tab A's cookie jar to principal B; **never** allow tab A's old action to silently proceed under user B.

### Step 6 — Verify the Fix with Negative and Positive Tests

Test that the stale token is rejected **and** the refreshed token succeeds. Testing only that a fresh token returns 200 does not prove stale tokens are blocked; testing only that an old token returns 403 could pass due to missing permissions or a malformed body. Test the same endpoint, same principal, and expected status/body per scenario.

## 16. Common Pitfalls and Remedies

| Symptom | Possible Cause | Fix / Verification |
| --- | --- | --- |
| POST right after login returns 403 while GET works | Pre-login token cleared; SPA/form did not refresh. | After login, GET fresh token or re-render form. Test old token 403 / new token 200. |
| Long-open form returns 403 after timeout | Expected token in old session is gone. | Detect expired session, re-authenticate, fetch fresh token, preserve draft safely. |
| Tab A fails after tab B logs in/out | Shared session/CSRF token changed while tab A still holds stale DOM/token. | Signal session change, refresh token/form, verify identity before submit. |
| Two tabs show different token strings | XOR masking produces distinct representations of the same token. | Do not treat differing strings as invalid; test both requests under the same session. |
| SPA reads `XSRF-TOKEN` cookie and sends header yet gets 403 | Raw token vs. masked handler mismatch or stale pre-auth token. | Use an SPA-compatible request handler / token endpoint; test GET/POST and login/logout. |
| POST `/login` returns 403 | Login form omitted CSRF token, used another session's token, or omitted cookie. | GET login/token under same session; do not blindly disable login CSRF. |
| 403 with no controller logs | `CsrfFilter` or URL authorization denied before reaching handler. | Debug filter chain and exception cause. |
| 403 despite valid CSRF | User lacks role/permission/ownership from `AuthorizationFilter` or method security. | Diagnose authorization separately; do not auto-refresh/retry POST. |
| Session ID rotates after login | Session fixation protection, not necessarily a bug. | Check CSRF clearing and token refresh instead of disabling session fixation protection. |
| Fails only after changing host/proxy | Cookie domain/path/scheme, forwarded headers, or header stripped by proxy. | Check public URL, cookie scope, and trusted proxy setup. |
| Fails only when cluster switches nodes | Unshared/non-sticky session state drops expected token. | Use synchronized session store or proper sticky sessions; test failover. |
| GET `/csrf` returns token yet POST misses cookie | `fetch` credentials mode, `SameSite`/`Secure`, browser cookie policy. | Use matching credentials mode, inspect origin and session cookies, never open CORS recklessly. |
| MockMvc `csrf()` passes while browser fails | Test injects valid token without testing lifecycle/cookies/browser behavior. | Add flow integration and multi-tab browser tests. |
| CSRF fails after logout | Old token cleared, yet frontend reuses it when logging back in. | Fetch a fresh token in the new anonymous session before POST login. |
| “Intermittent” 403 across concurrent async requests | Race between login/session refresh and in-flight POSTs using old token. | Serialize auth transitions with protected requests; block unsafe requests until the new token is ready. |

## 17. Bad Fixes to Avoid

**Never use these “403 fixes” without an appropriate security design:**

~~~java
// Anti-pattern for session/cookie applications:
http.csrf(csrf -> csrf.disable());
~~~

Disabling CSRF app-wide removes a vital defense. Other risky choices include:

- Exempting all `/api/**` even though browsers automatically send session cookies to that API.
- Accepting stale tokens from other sessions or storing a static system-wide token.
- Disabling session fixation protection merely because `JSESSIONID` rotates after login.
- Opening CORS to all origins with credentials and exposing token endpoints instead of fixing origins/cookies/handlers properly.
- Using GET instead of POST for writes/deletes to “dodge” `CsrfFilter`.
- Auto-retrying every unsafe request after 403 without verifying CSRF/authorization and preventing duplicate side effects.
- Putting CSRF tokens in URL query strings or redirect URLs, leaking them into history/logs/Referrer headers.
- Dropping role/owner checks because a POST returned 403 “even with a valid token”.
- Logging raw CSRF tokens, cookies, passwords, JWTs, SAML responses, or session IDs in production logs.

**The right fix is synchronizing the request's token with the active session state while keeping authorization and CSRF policies intact.**

## 18. Safe Diagnosis and Recovery Checklist

1. Determine via filter/exception evidence—not status alone—whether 403 is **CSRF** or **missing permission**.
2. Confirm the route/method is protected by `CsrfFilter`; test the exact unsafe request.
3. Identify whether expected tokens live in **`HttpSessionCsrfTokenRepository`** or **`CookieCsrfTokenRepository`**, and whether a custom handler is configured.
4. Trace the timeline: GET form/token → login/logout → POST; was the token cleared after authentication success?
5. Check session timeout and state restoration in load-balanced/clustered setups.
6. With multiple tabs, check whether another tab logged in/out or switched accounts. **Do not** assume opening a second tab is itself a bug.
7. For server-rendered forms, verify the hidden CSRF field exists in rendered HTML and pages re-render after login/session changes.
8. For SPAs, fetch tokens from a trusted endpoint after login/logout and send the right header/parameter; never send raw tokens to a masked-only handler without SPA-compatible config.
9. Verify `JSESSIONID`/`SESSION` cookies, `Path`/`Domain`/`Secure`/`SameSite`, `fetch` credentials, and reverse proxies/ingress.
10. Prevent the frontend from continuing a previous user's request once the principal has changed.
11. Test **stale-token rejection**, **fresh-token success**, and **two tabs in the same session not randomly invalidating each other**.
12. Keep CSRF tests separate from role/owner tests by holding other conditions valid.
13. Never auto-retry POST/DELETE/payment requests on unclassified 403s; use idempotency/draft recovery where appropriate.
14. Limit PII/secrets in logs; verify `Cache-Control` on token endpoints and strict CORS/credentials rules.
15. After fixing, retest login, logout, timeout, back button, reload, multi-tab flows, and cluster failover in an appropriate environment.

## 19. Self-Check Questions

**Question 1:** Two tabs in the same session receive different `_csrf` strings yet both POST successfully. Is Spring rotating the expected token on every GET?

**Answer:** Not necessarily. Under XOR masking, two renders can return **two distinct masked representations** of the same raw expected token. Inspect the server repository and session lifecycle before concluding the token rotated.

**Question 2:** After login, an SPA sends the pre-login token header and gets 403. Should we disable CSRF for `/api/**`?

**Answer:** No. Fetch a fresh token after authentication success, and verify session cookies and the request handler. If an API truly never uses browser-autosent credentials, perform a dedicated threat-model review before changing policy.

**Question 3:** After session expiration, a user's GET redirects to login, yet submitting an old form via POST returns 403. Why?

**Answer:** `CsrfFilter` can reject an unsafe request carrying a stale session token **before** the authentication entry point triggers a redirect. The two requests traverse different checks.

**Question 4:** A MockMvc test with `.with(csrf())` passes, yet actions in an old browser tab still get 403. Is that a contradiction?

**Answer:** No. `csrf()` supplies a valid token for that single test request; it does not simulate token clearing on login/logout, session timeouts, or browsers holding stale tokens. Lifecycle/E2E tests are needed.

**Question 5:** How do you prove a 403 is not merely a role error?

**Answer:** Using the same user and required endpoint, verify a request with a **fresh token** succeeds; check `CsrfFilter` logs/exception context and test authorization separately. A 403 status alone is not proof.

## 20. Summary

In Spring Security Servlet, the CSRF token must **match the repository/session's current expected token**. After **login** or **logout**, Spring Security strategies may **clear the old token**; after **timeout**, the token bound to the prior session disappears. **Multiple tabs do not fail on their own**, yet individual tabs can hold stale HTML/JavaScript state once the shared session changes. Furthermore, Spring Security 6 introduces **deferred tokens** and **XOR masking**, so “two token strings look different” does not automatically mean two different expected tokens.

**Safe strategy:** keep `CsrfFilter`, identify the exact repository/handler, refresh tokens after authentication changes, re-render forms or fetch tokens for SPAs, diagnose CSRF separately from authorization, and test both stale-token rejection and refreshed-token success. Never resolve 403 errors by disabling CSRF on applications using cookies/sessions.

## References

- Spring Security — CSRF protection, Servlet: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CSRF testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security API — CsrfFilter: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/web/csrf/CsrfFilter.html
- Spring Security API — CsrfAuthenticationStrategy: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/web/csrf/CsrfAuthenticationStrategy.html
- Spring Security API — XorCsrfTokenRequestAttributeHandler: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/web/csrf/XorCsrfTokenRequestAttributeHandler.html
