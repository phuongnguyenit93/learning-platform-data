# CSRF in Spring Security Servlet: Missing Token, Invalid Token, Expired Session, and Appropriate Error Responses

## 1. Context and Objective

CSRF (Cross-Site Request Forgery) is an attack that causes a logged-in user's browser to send an unintended state-changing request to an application. The browser usually attaches session cookies (`JSESSIONID` or authentication cookies) automatically, so having only the cookie does not prove the request was created by a legitimate UI. For **Spring Security Servlet applications using sessions/cookies**, the CSRF mechanism additionally verifies an unpredictable token bound to the right context.

This lesson explains four cases: **missing token, invalid token, expired session, and appropriate error responses**. After studying it, you should be able to distinguish what the server directly observes from inferred causes, pick accurate HTTP statuses, and resolve 403s without dropping CSRF protection.

## 2. How Does Spring Security Check CSRF?

By default, `CsrfFilter` protects HTTP methods **other than** `GET`, `HEAD`, `TRACE`, and `OPTIONS`. Methods like `POST`, `PUT`, `PATCH`, and `DELETE` normally require a valid token. Exempt methods must genuinely be safe and not alter state; for example, `GET /delete` remains dangerous even though the filter does not require a token.

A typical lifecycle for a session-based application:

1. The browser calls a safe `GET`, receiving a session cookie and CSRF token via an HTML form, a token-issuing endpoint, or framework integration.
2. The client sends a data-modifying request, attaching **the same session cookie** and the token via the `_csrf` form parameter or the corresponding header, typically `X-CSRF-TOKEN`.
3. `CsrfFilter` requests the expected token from `CsrfTokenRepository` (usually `HttpSessionCsrfTokenRepository`), then compares it with the token in the request.
4. If there is no expected token or the client token does not match, the filter blocks before the controller; by default it responds with **403 Forbidden**.

```text
Browser                             Servlet Security Filter Chain
GET /api/csrf --------------------> issue token + session cookie
              <------------------ token and cookie
POST /api/demo + cookie + token --> CsrfFilter
                                    |-- match -> controller -> 2xx
                                    |-- error -> AccessDeniedHandler -> 403
```

A CSRF token **differs from** a JWT/Bearer access token: a CSRF token neither authenticates identity nor represents permissions. APIs using only client-attached Bearer tokens in headers, without relying on browser auto-sent credentials, have a different threat model; CSRF exemptions must be based on the real architecture. Do not disable CSRF across an entire session-backed web app just because one request returned 403.

### Tokens Are Stored, Issued, and Rotated

- The session repository stores the expected token tied to `HttpSession`. When the session is lost, the expected token can also be lost.
- Spring Security 6 supports **deferred CSRF tokens**: a token may not be created/stored until actually accessed. A successful GET does not automatically guarantee an SPA has received a usable token.
- After login/logout or authentication lifecycle transitions, old tokens in an earlier tab may be cleared/invalidated. Multiple tabs holding stale cached tokens are a scenario that must be tested.
- Spring Security 6 uses a BREACH-mitigating handler for tokens exposed on requests. When pairing `CookieCsrfTokenRepository` with an SPA, there must be a `CsrfTokenRequestHandler` compatible with raw cookies/headers and masked tokens; do not assume every raw cookie token sent in a header is valid by default.
- For session cookies and tokens, the client must keep the same session. A token from tab/session A must not be paired with session B's cookie.

## 3. How Do Missing Token, Invalid Token, and Expired Session Differ?

| Scenario | What the filter observes | Typical outcome | Recovery approach |
| --- | --- | --- | --- |
| Server already has an expected token yet request sends no token | Submitted token is empty/mismatched; typically `InvalidCsrfTokenException` | 403 | Fix header/hidden input and token retrieval mechanism |
| Repository no longer has an expected token | Typically `MissingCsrfTokenException` | 403 | Inspect session lifecycle, issue a new token |
| Request sends a forged/wrong/stale token | `InvalidCsrfTokenException` | 403 | Resynchronize session and token; test multiple tabs |
| Session times out before POST request | Old session is gone; expected token may be lost | Can be 403 CSRF; depending on flow also 401/redirect | Re-authenticate if needed, refresh token, then resubmit under control |
| Not logged in, no CSRF error blocking earlier | `AuthenticationEntryPoint` | 401 for APIs or 302 to login for web forms | Authenticate |
| Logged in, valid token yet insufficient permissions | `AccessDeniedHandler` | 403 authorization | Obtain appropriate permissions; do not refresh token needlessly |

**Distinguishing the two exceptions accurately:**

- `MissingCsrfTokenException`: **no expected token was found from the repository**. You cannot conclude from the exception name alone that the client forgot a header. A timed-out session or a repository/session store losing data can both cause this state.
- `InvalidCsrfTokenException`: **the token from the request does not match the expected value**. The client may have sent a wrong value or sent no token at all while the server still holds an expected token.
- **Session expiration is not a separate CSRF exception type.** A CSRF 403 does not by itself prove the session expired. It could be due to CORS/credentials not sending cookies, a token issued in the wrong context, a load balancer routing to a node missing the session, token rotation after login, etc.

Diagnostic example: if GET issues a token and POST omits the header while keeping the same session, the server typically reports an invalid token. If a user spends too long filling a form, the session times out, and they submit POST with the old token, the server may report a missing expected token. Both requests get 403, yet their remediation paths differ.

## 4. Using Appropriate Statuses and Error Contracts

**403 Forbidden** is the default HTTP status when CsrfFilter rejects a request. **401 Unauthorized** should be reserved for cases where authentication determines the client must log in/re-authenticate; do not turn every CSRF failure into 401. Form login may redirect 302 to the login page depending on the entry point. Codes 419/440 are used by some systems for timeouts, but are not Spring Security's default standard statuses.

Example **application/problem+json** for an API:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Request did not pass CSRF verification.",
  "code": "CSRF_TOKEN_INVALID"
}
```

`code` is an **application-defined** code, not automatically emitted by Spring Security. Internal code `CSRF_TOKEN_MISSING` should be understood as "no expected token in repository", not assumed to mean "missing header"; `CSRF_TOKEN_INVALID` means the submitted value is invalid. Clients should rely on stable status/code fields rather than parsing message strings.

A good response should ensure:
- Never expose expected tokens, session IDs, stack traces, security keys, or session store details to the client.
- Inform the user just enough: "The form security token is no longer valid. Please reload the page or log in again if prompted."
- Do not diagnose "session expired" when only a CSRF exception occurred without independent authentication evidence.
- Log `requestId`, method, path, and **exception type**; avoid logging token values, cookies, or sensitive payloads.
- For data-modifying operations, do not retry infinitely. Prompt resubmission only when you know the previous operation was blocked before processing; critical operations need confirmation/idempotency keys.

## 5. Spring Boot 3 / Spring Security 6 Example (Java 17+)

The snippets below are **files inside a Spring Boot Servlet application** that already has a `@SpringBootApplication` class, `spring-boot-starter-web`, and `spring-boot-starter-security`; they are not standalone programs runnable with plain `javac`. `permitAll` endpoints exist only to isolate the CSRF test; real business endpoints must attach appropriate authentication/authorization rules.

### 5.1. SecurityFilterChain and Handler Returning 403 JSON

File `SecurityConfig.java`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.InvalidCsrfTokenException;
import org.springframework.security.web.csrf.MissingCsrfTokenException;

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            ObjectMapper mapper) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/demo").permitAll()
                .anyRequest().authenticated())
            .csrf(Customizer.withDefaults())
            .exceptionHandling(errors -> errors.accessDeniedHandler(
                (request, response, exception) -> {
                    String code = "ACCESS_DENIED";
                    if (exception instanceof MissingCsrfTokenException) {
                        code = "CSRF_TOKEN_MISSING";
                    } else if (exception instanceof InvalidCsrfTokenException) {
                        code = "CSRF_TOKEN_INVALID";
                    }

                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setCharacterEncoding("UTF-8");
                    response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
                    mapper.writeValue(response.getOutputStream(), Map.of(
                        "type", "about:blank",
                        "title", "Forbidden",
                        "status", 403,
                        "detail", "Request was rejected.",
                        "code", code
                    ));
                }));
        return http.build();
    }
}
```

The CSRF filter uses `AccessDeniedHandler` when a request is rejected; `exceptionHandling` configures the handler for the chain. Error codes can share a format with authorization errors, yet **never conflate the meaning** of `CSRF_TOKEN_INVALID` and `ACCESS_DENIED`. In applications with multiple `SecurityFilterChain` beans, ensure the exact chain matches `/api/**`. For HTML UIs, use an appropriate 403 page/UI message instead of applying the same JSON to all requests.

### 5.2. Token-Fetching Endpoint and POST Endpoint

File `CsrfDemoController.java`:

```java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfDemoController {
    @GetMapping("/api/csrf")
    Map<String, String> csrf(HttpServletRequest request) {
        Object value = request.getAttribute(CsrfToken.class.getName());
        if (!(value instanceof CsrfToken token)) {
            throw new IllegalStateException("CSRF token is unavailable");
        }
        return Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        );
    }

    @PostMapping("/api/demo")
    Map<String, String> demo() {
        return Map.of("result", "saved");
    }
}
```

Reading `token.getToken()` materializes the deferred token when needed. The client must send the exact cookie from the token GET when POSTing. The token-returning endpoint is a sensitive resource for trusted clients: use TLS, appropriate cache/CORS policies, and never expose tokens via logs or URLs.

Test with cURL after Spring Boot starts. Replace `TOKEN_FROM_GET` with the `token` field received in the first response, **keeping cookies.txt unchanged**:

```bash
# Fetch token and save session cookie.
curl -i -c cookies.txt http://localhost:8080/api/csrf

# Missing token: 403; controller did not execute.
curl -i -b cookies.txt -X POST http://localhost:8080/api/demo

# Wrong token: 403.
curl -i -b cookies.txt -X POST \
  -H 'X-CSRF-TOKEN: wrong-token' http://localhost:8080/api/demo

# Valid token and matching session cookie: 200.
curl -i -b cookies.txt -X POST \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_GET' http://localhost:8080/api/demo
```

For the example configuration, expected statuses are **403, 403, 200** respectively. A valid POST returns JSON containing `"result":"saved"`. A wrong-token POST must be blocked *before* the `demo()` method; no side effects occur.

### 5.3. HTML Form and JavaScript

With a server-rendered Thymeleaf form having `_csrf` in the request:

```html
<form method="post" action="/api/demo">
  <input type="hidden" th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}" />
  <button type="submit">Submit</button>
</form>
```

With an SPA using the token-fetching endpoint:

```javascript
const csrfResponse = await fetch("/api/csrf", {
  credentials: "same-origin",
  cache: "no-store"
});
if (!csrfResponse.ok) throw new Error("Cannot get CSRF token");
const csrf = await csrfResponse.json();

const response = await fetch("/api/demo", {
  method: "POST",
  credentials: "same-origin",
  headers: { [csrf.headerName]: csrf.token }
});
if (response.status === 403) {
  // Show instructions to refresh token / log in when needed.
}
```

`credentials: "same-origin"` preserves cookies for same-origin requests. Cross-origin frontend/backend setups need separate decisions on CORS, `credentials`, and cookie `SameSite`/`Secure` attributes. Do not put tokens in query strings or URLs since they easily leak into history, logs, and `Referer`.

## 6. Expired Session: Designing the Recovery Flow

Session loss can stem from timeouts, logout, the user clearing cookies, concurrent session policies, session store eviction, or nodes not sharing data. When the CSRF token lives in the session, a POST carrying an old token after timeout can receive 403; there is no reliable way to distinguish timeout from all other causes solely from `MissingCsrfTokenException`.

Recommended flow:

1. **HTML forms:** on 403, notify the user that the form must be reloaded; preserve user-entered data if security-appropriate, then generate a fresh form/token.
2. **SPA:** call a safe GET to receive a new token and synchronize cookie/session; if authentication actually expired, require logging in again. Only attempt to resend state changes when you are certain the previous POST never ran and have a strategy to prevent duplicate operations.
3. **Authentication:** endpoints requiring login should let `AuthenticationEntryPoint` decide 401 (API) or login redirect (web), but do not assume every session-expired POST reaches the entry point; `CsrfFilter` may reject earlier.
4. **Invalid session:** `invalidSessionStrategy` can handle invalid session IDs in suitable configurations, yet is not guaranteed to always run before CSRF on unsafe requests. Verify filter order and test real requests.
5. **After login/logout or session fixation protection:** fetch a new token per the framework mechanism. Tokens held in old tabs may no longer work.

In multi-node environments, verify sticky sessions or a shared session store, cookie domain/path, and consistent session timeouts. Never "fix" random 403s with `csrf(csrf -> csrf.disable())`.

## 7. Testing Missing Token, Wrong Token, and Valid Token

Add `spring-boot-starter-test` and `spring-security-test`. File `CsrfDemoTest.java` (inside the Spring Boot project):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDemoTest {
    @Autowired
    MockMvc mvc;

    @Test
    void noTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/demo"))
           .andExpect(status().isForbidden());
    }

    @Test
    void wrongTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/demo").with(csrf().useInvalidToken()))
           .andExpect(status().isForbidden());
    }

    @Test
    void correctTokenIsAllowed() throws Exception {
        mvc.perform(post("/api/demo").with(csrf()))
           .andExpect(status().isOk());
    }
}
```

`csrf()` here is a **Spring Security Test request post-processor**; `useInvalidToken()` intentionally supplies a wrong token. This test verifies the CSRF filter without manually constructing token strings. The demo endpoint is `permitAll` to avoid conflating with missing authentication; real endpoints must also verify access permissions.

Integration scenario table:

| Scenario | How to reproduce | What to verify |
| --- | --- | --- |
| Missing token from client | POST keeping session cookie while omitting header/input | 403; controller does not run; data unchanged |
| Wrong/stale token | POST with forged token or token from another session | 403; no side effects |
| Valid token | GET issues token then POST in same session | 2xx per business logic |
| Real session timeout | Fetch token, invalidate/expire session on server, re-POST old token | May be 403 CSRF; no side effects; client guided to recover |
| Logout/re-login | Keep old tab/form across authentication state transitions | Token re-issued properly; old form cannot be misused out of context |
| Unauthenticated | Endpoint requires authentication, valid token if method unsafe | 401 or login redirect per entry point |
| Insufficient permissions | Authenticated user, valid token, missing authority | 403 authorization; code/log distinct from CSRF |
| Multiple nodes | Send requests to different nodes per real infrastructure | Session/token still read consistently |
| Safe GET | GET without CSRF token | No token needed; GET causes no state change |

**Timeout tests must genuinely expire the server session.** Merely omitting the token header tests a missing token from the request, not a timeout. After every 403 test, confirm no data writes, emails, or business jobs occurred.

## 8. 403 Investigation Checklist and Common Mistakes

Procedure when encountering an error:

1. Check HTTP method, URL, the exact `SecurityFilterChain`, and CSRF protection/exception rules.
2. Compare session cookies between fetching the token and POSTing; verify the form hidden input/`X-CSRF-TOKEN` header is present. Avoid putting raw tokens/cookies into tickets or logs.
3. Check when the token is materialized, how the SPA holds tokens and `fetch.credentials`, and login/logout or multi-tab events.
4. Check `CsrfTokenRepository`, session timeout, cookie path/domain, load balancer, and session store.
5. Read the actual exception from server logs: expected token **does not exist** vs. request token **does not match**. Do not blame everything on timeout.
6. Run the tests from section 7; confirm 403 returns the API contract format with a safe correlation ID and no side effects.

Common mistakes: confusing CSRF tokens with JWTs; using 401 for all CSRF failures; treating `MissingCsrfTokenException` as certainly a missing request header; infinitely retrying POSTs; fetching a token with one session then POSTing with another cookie; keeping old tokens after login; sending tokens in URLs; logging tokens; globally disabling CSRF; using POST as a token-issuing endpoint; mutating data in GET; assuming `invalidSessionStrategy` always catches timeouts before CsrfFilter.

## 9. Implementation Checklist

- [ ] State-changing requests over session/cookie always send the token matching the right session; GET requests do not mutate data.
- [ ] Forms/SPAs have a path to re-issue tokens after login, logout, and long-lived tabs; deferred tokens are handled properly.
- [ ] CSRF 403 is distinguished from authorization 403; 401 is used only when authentication is required.
- [ ] APIs return structured errors without leaking secrets and without claiming session timeout lacking evidence.
- [ ] Dangerous business actions are not auto-retried, and no side effects occur when blocked by CSRF.
- [ ] Tests cover missing, invalid, valid, real timeout, login/logout, multi-node, and access permissions.

**Key takeaway:** In Spring Security Servlet, both missing and wrong tokens typically cause `CsrfFilter` to return **403 before the controller**. Session timeouts can produce similar symptoms, yet must be verified separately. Synchronizing token + session, returning honest errors, and testing the right paths is the solution.
