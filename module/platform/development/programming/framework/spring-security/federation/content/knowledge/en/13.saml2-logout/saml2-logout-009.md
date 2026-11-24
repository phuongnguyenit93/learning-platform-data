# Handling CSRF for User-Initiated Logout in SAML 2.0

> **Topic:** Spring Security – federation · **Group:** SAML2 Logout. This lesson focuses on **logout clicked by the user at the Service Provider (SP)** and how to preserve CSRF protection, while explaining why **SAML Single Logout (SLO) callbacks from the Identity Provider (IdP)** rely on signature/protocol verification rather than the SP's HTML form token. Spring Security examples target the Spring Boot 3.x / Spring Security 6.x Servlet stack, and the standalone Java example requires JDK 17+.

## 1. Why Must Logout Also Be Protected Against CSRF?

A user is authenticated via SAML SSO at `https://portal.example.org`. If the application implements `GET /logout` to immediately delete the session, another website can embed a link, image, iframe, or redirect to that address. The browser may attach the user's session cookie depending on context, logging them out even though they never clicked a button inside the application.

Example **attack pattern** to understand the cause, not recommended application code:

```html
<img src="https://portal.example.org/logout" alt="">
```

In an application with RP-initiated SAML SLO enabled, a forged action could even trigger a logout flow at the IdP or linked applications. This causes disruption, login loops, and can interrupt open business workflows.

**Core principle:** user-initiated logout is a state-changing action requiring **HTTP POST + a valid CSRF token**. Do not use GET to destroy sessions; nor treat POST or SameSite cookies as sufficient without a token.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **local logout**, **RP-initiated SAML SLO**, **AP/IdP-initiated SLO**, and the SLO response callback.
2. Explain why `POST /logout` requires a CSRF token, whereas `POST /logout/saml2/slo` from the IdP uses **SAML signatures and protocol checks**.
3. Configure Spring Security `saml2Logout()` **without disabling CSRF across the entire application**.
4. Build POST forms with CSRF tokens in Thymeleaf/MVC and understand JavaScript SPA considerations.
5. Scope CSRF exceptions strictly to the callback; never exempt `/logout/**` or user logout endpoints.
6. Test missing/invalid tokens, unsigned callbacks, session timeouts, SameSite, multi-node, and partial logout.

## 2. Distinguishing the Logout Flows

| Action | Initiator | Common SP Endpoint | Trust Condition |
| --- | --- | --- | --- |
| **Local logout** | User clicks logout in SP | `POST /logout` | SP CSRF token, valid session/cookie |
| **RP-initiated SAML SLO** | User clicks logout at SP, then SP builds LogoutRequest | `POST /logout` with default SLO; configurable to `POST /saml2/logout` | CSRF token on browser→SP request; then SAML signature |
| **IdP/AP-initiated SLO** | IdP emits SAML LogoutRequest | `POST /logout/saml2/slo` with `SAMLRequest` | SAML signature, issuer, destination, identity/session |
| **SLO response callback** | IdP replies to SP-sent LogoutRequest | `POST /logout/saml2/slo` with `SAMLResponse` | SAML signature, issuer, status, `InResponseTo`, request state |

**Do not confuse** `POST /logout` with `POST /logout/saml2/slo`. The first URL is a command from the user's web page; the second URL is the gateway receiving SAML protocol messages from the IdP via the browser.

### 2.1. RP-Initiated SLO from the Log Out Button

```text
User browser                Spring Security SP                  SAML IdP
     |                              |                              |
     | POST /logout + _csrf         |                              |
     |----------------------------->|                              |
     |       CsrfFilter verifies token                             |
     |       LogoutFilter / LogoutHandlers                         |
     |       end SP session, clear SecurityContext                 |
     |       Saml2RelyingPartyInitiatedLogoutSuccessHandler        |
     |       create/sign SAML LogoutRequest, save state            |
     |<-----------------------------| redirect/POST to IdP SLO     |
     |------------------------------------------------------------>|
     |                              |      IdP processes logout    |
     |<------------------------------------------------------------|
     | POST /logout/saml2/slo (SAMLResponse)                       |
     |----------------------------->|                              |
     |       Saml2LogoutResponseFilter                             |
     |       validate signature, status, InResponseTo              |
     |<-----------------------------| success/error UX             |
```

Per Spring Security documentation, the SP can end the local session **before** receiving the LogoutResponse. The IdP is not guaranteed to always reply, and SLO can fail partially. Never display "logged out everywhere" solely because the SP emitted a LogoutRequest.

### 2.2. IdP-Initiated SLO

```text
IdP -> Browser -> POST /logout/saml2/slo
                 form field SAMLRequest
                         |
                         v
                Saml2LogoutRequestFilter
                + SAML LogoutRequest validator
                         |
                 IdP signature valid?
                 Issuer/Destination match?
                 NameID/SessionIndex/session match?
                         |
           Valid   -> local session cleanup -> sign LogoutResponse
           Invalid -> reject, never log out arbitrarily
```

The SAML callback does not carry an SP-rendered `_csrf` token because the IdP does not possess that token. This **does not** allow any arbitrary POST to the callback to destroy sessions: the message must pass SAML validation. An unsigned `SAMLRequest` or one signed with an unknown key must never be trusted.

## 3. CSRF Mechanics in the Browser

CSRF (Cross-Site Request Forgery) happens when an untrusted website tricks a victim's browser into sending a state-changing request to an application holding an active session. The browser can send cookies automatically, so the attacker does not need to read cookies.

**POST alone is not enough:** a cross-site HTML form can also POST:

```html
<!-- Threat illustration, do not deploy -->
<form method="post" action="https://portal.example.org/logout">
  <button type="submit">Click</button>
</form>
```

The SP needs a token issued and verified only within the authorized session context. An ordinary attacker cannot read the token from the SP page due to the browser same-origin policy.

### 3.1. Invariants to Guarantee

- `GET /logout` never destroys a session, even when clicked by a user or prefetched by a browser.
- `POST /logout` or a custom RP user logout URL must carry a valid CSRF token.
- Missing, wrong, expired, or cross-session tokens are rejected **before logout handlers run**.
- Only when CSRF is valid may the SP destroy the local session and emit a signed SAML LogoutRequest if SLO is configured.
- The SLO callback does not use form tokens as proof of a valid IdP; it requires **signature/trust/issuer/destination/correlation**.
- Never log tokens, session cookies, secret RelayState, or raw SAML messages.

### 3.2. Concepts That Cannot Substitute for One Another

| Data | Purpose | Replaces the User Logout CSRF Token? |
| --- | --- | --- |
| `_csrf` or `X-CSRF-TOKEN` | Proves POST was submitted in an authorized browser/session context | **Is the token used** |
| `JSESSIONID` or `SESSION` | Identifies browser session | No; cookies can be sent automatically |
| `RelayState` | State linking SAML flow | No |
| `InResponseTo` | Correlates LogoutResponse with LogoutRequest | No |
| `SigAlg`/`Signature` or XML `ds:Signature` | Verifies SAML message from a trusted signer | Does not protect the initial user click |
| `SameSite` | Restricts contexts in which cookies are sent | Defense-in-depth; does not replace token |
| `Origin`/`Referer` | Additional origin check | Does not replace default token |
| CORS | Controls response reading and certain cross-origin requests | Does not block all cross-site form POSTs |

## 4. How Spring Security Handles Logout and CSRF by Default

In Spring Security Servlet, CSRF protection is enabled by default in standard configurations. `CsrfFilter` checks unsafe HTTP methods, including POST. For logout:

- `GET /logout` can display a **confirmation page** with a CSRF token without immediately logging out.
- Only `POST /logout` with a valid token is processed by `LogoutFilter`.
- `POST /logout` with a missing/invalid token normally returns `403 Forbidden`; the exact status depends on `AccessDeniedHandler`.
- Logout handlers can invalidate the session, clear `SecurityContext`, and clear the old CSRF token.

This is the intended behavior per Spring Security documentation, not a SAML bug.

### 4.1. Configuration to Avoid

```java
// ANTI-PATTERN: do not disable CSRF across the entire cookie/session application.
http.csrf(csrf -> csrf.disable());
```

Disabling CSRF can allow GET logout to mutate state under default/custom logout behavior, and strips protection from other POST/PUT/PATCH/DELETE endpoints. An IdP SAML callback lacking a token is not a reason to disable CSRF globally.

`permitAll()` is an **authorization** check; it does not disable CSRF by default. Do not confuse authorization, CSRF, and SAML signature validation.

## 5. Spring Security 6.x: Enabling SAML Single Logout While Keeping CSRF

Create `SamlLogoutSecurityConfig.java` in a Spring Boot app with SAML2 Service Provider dependencies:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a **Spring configuration class** with no `main` to run standalone with `javac`. To function, it needs a `RelyingPartyRegistrationRepository` bean, trusted IdP metadata, signing key/certificate, and an IdP supporting Single Logout. `csrf(Customizer.withDefaults())` expresses the requirement for CSRF protecting user-initiated logout commands.

`saml2Logout()` activates Spring Security's SLO flow. When logged in via SAML and the registration has SLO capability, a valid POST logout can be handled by Spring as RP-initiated SLO.

### 5.1. Example application.yml for Registration

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "https://login.example.org/metadata/saml"
```

This is an **illustrative configuration**, which will not run without actual keys/certs/files. IdP metadata must publish `SingleLogoutService` and verification certificates, and the SP must have a signing credential suited to its role. `singlelogout.url` is the **SP's SLO callback**, not the `POST /logout` submitted by the user.

`{baseUrl}` and `{registrationId}` are Spring Security URI placeholders requiring the exact public HTTPS host/port via a reverse proxy. Never use an internal HTTP host as an SLO destination in production.

### 5.2. Do Not Create a GET /logout Controller to Destroy Sessions

```java
// WRONG: GET can easily be triggered by another site/browser.
// @GetMapping("/logout")
// public String logout(HttpSession session) {
//     session.invalidate();
//     return "redirect:/login";
// }
```

This custom controller bypasses CSRF, bypasses Spring Security's standard handlers, and may fail to build SAML LogoutRequests properly.

## 6. Safe Logout Form

### 6.1. Thymeleaf

In a Thymeleaf page integrated with Spring Security/Spring MVC:

```html
<form th:action="@{/logout}" method="post">
  <button type="submit">Log out</button>
</form>
```

When `RequestDataValueProcessor`/CSRF support is properly integrated, Thymeleaf automatically adds a hidden CSRF input for POST forms. Confirm via rendered HTML in DevTools rather than blindly assuming the token is present.

Rendered HTML may look like:

```html
<form action="/logout" method="post">
  <input type="hidden" name="_csrf" value="SERVER_GENERATED_TOKEN"/>
  <button type="submit">Log out</button>
</form>
```

`SERVER_GENERATED_TOKEN` is only an illustrative string, not a real secret. Never hardcode tokens into templates. If using a view engine that does not auto-inject tokens, read the `CsrfToken` exposed by Spring Security in the `_csrf` request attribute and render a hidden input with the version-appropriate `parameterName` and `token`.

**Never put the token in a query URL**, as it can leak via access logs, browser history, referrer headers, monitoring, or screenshots.

### 6.2. Do Not Use a GET Link to Destroy Sessions

```html
<!-- Link may open a confirmation page, but must not destroy the session -->
<a href="/logout">Log out</a>
```

With CSRF enabled, GET usually only shows a confirmation page so the user can submit a POST form. If you want a single button, use a POST form. If you want link styling, JavaScript can submit a tokenized POST form with a non-JS fallback to the confirmation page.

### 6.3. Stale Tokens and Expired Sessions

Tokens may be cleared/rotated after login/logout; a form in an old tab may encounter 403. Handle this by refreshing the token or prompting to reload/re-login, not by dropping CSRF. CSRF tokens are not necessarily single-use in every repository; generation/storage/rotation policy depends on the Spring Security version and `CsrfTokenRepository`.

## 7. Separating Local Logout and RP-Initiated SLO Endpoints

You can offer two choices:

- "Log out of application" → clears SP session only.
- "Log out of SSO" → SP emits a LogoutRequest to the IdP if supported.

Spring Security allows separating URLs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SeparateLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout.logoutUrl("/logout"))
            .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));

        return http.build();
    }
}
```

This configuration class is an **alternative** to the class in section 5; do not declare both chains matching all URLs together.

| URL | Purpose | CSRF |
| --- | --- | --- |
| `POST /logout` | Local logout | **Token required** |
| `POST /saml2/logout` | RP-initiated SAML SLO | **Token required** |
| `POST /logout/saml2/slo` | IdP SAML callback | SAML signature/protocol validation; no form token |

Both forms can share the session's CSRF token:

```html
<form th:action="@{/logout}" method="post">
  <button type="submit">Local logout</button>
</form>

<form th:action="@{/saml2/logout}" method="post">
  <button type="submit">SSO logout</button>
</form>
```

**Both user-facing endpoints must keep CSRF**, even on a path named SAML.

### 7.1. Do Not Destroy the Session Early in a Custom Controller

RP-initiated logout needs principal/registration/`NameID`/`SessionIndex` details when applicable to build the LogoutRequest. If a controller invalidates the session before the framework executes `Saml2RelyingPartyInitiatedLogoutSuccessHandler`, that context can be lost.

Let Spring Security orchestrate `LogoutHandler` and the SAML logout success handler; avoid custom filters deleting state or intercepting the request prematurely.

## 8. CSRF and SAML Callbacks: Two Different Boundaries

`POST /logout/saml2/slo` receives `SAMLRequest` or `SAMLResponse` from the IdP via the browser. The IdP cannot know the SP page's CSRF token. Therefore the SAML callback may need a CSRF exception **strictly for the protocol endpoint**, while validators verify:

- Exact `SingleLogoutService` endpoint and HTTP binding.
- SAML XML/Redirect signature and certificate tied to the trusted IdP registration.
- `Issuer`/`Destination`, message structure, and NameID/SessionIndex/session matching when applicable.
- For LogoutResponse: `InResponseTo`/RelayState, pending `Saml2LogoutRequestRepository`, SAML Status, and time/replay policy.
- Perform local logout for the matching subject only after the request is trusted; never accept unsigned/forged LogoutRequests.
- Never load metadata/keys from browser input or trust arbitrary XML `KeyInfo`.

**A CSRF exception does not authorize logging out a user**: it merely lets the message reach the **SAML validation boundary**.

### 8.1. Exception Strictly for the Exact Callback

Spring Security `saml2Logout()` normally configures the matching protocol filters/matchers. In setups with custom chains/endpoints, check runtime behavior: is the callback blocked by CSRF before validation? If you must add an exception yourself, restrict it to the exact method/path and re-test.

Snippet for Spring Security 6.x when genuinely needed:

```java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

// Fragment for HttpSecurity. Use only when the callback is handled
// completely by SAML LogoutRequest/LogoutResponse validators.
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AntPathRequestMatcher("/logout/saml2/slo", "POST")
));
```

This is not a standalone runnable class. Depending on the major version, `AntPathRequestMatcher` may be deprecated or replaced by another API. If the DSL already configures the exception, do not add a duplicate rule. Most importantly: never allow another controller on the same path to handle non-SAML requests.

### 8.2. Anti-Patterns to Reject

```java
// WRONG: wildcard can include the user logout endpoint.
http.csrf(csrf -> csrf.ignoringRequestMatchers("/logout/**"));

// WRONG: disabling CSRF for the whole web app because SAML callback lacks _csrf.
http.csrf(csrf -> csrf.disable());
```

If the callback URL changes, synchronize IdP metadata, SAML request/response filter matchers, reverse proxy routes, and any narrow CSRF exception. Never use `permitAll()` to assume the callback is safe: authorization does not replace signature validation.

## 9. LogoutRequest and LogoutResponse Must Remain Correlated

Spring Security uses `Saml2RelyingPartyInitiatedLogoutSuccessHandler` to create, sign, and send LogoutRequests when a user logs out validly. The request has an ID/RelayState and is stored in `Saml2LogoutRequestRepository` per configuration to verify the returning LogoutResponse.

Callback acceptance requires more than "came from the IdP":

1. Signature and issuer belong to the trusted IdP.
2. `Destination`/SP SLO endpoint matches.
3. `InResponseTo` matches the emitted request, and state/RelayState is valid per the repository.
4. `Status` reflects the SLO outcome; never assume every response succeeded.
5. Protection against replay, duplicate IDs, and tenant/session confusion per profile.

Distinguish `Saml2LogoutRequestRepository` from `CsrfTokenRepository` and `Saml2AuthenticationRequestRepository` used for login. They store three different types of state and are not interchangeable.

### 9.1. IdP-Initiated Logout Must Not Log Out Randomly

When the IdP sends a LogoutRequest, Spring Security's `Saml2LogoutRequestFilter`/validator must identify the trusted issuer and exact principal or session context. Never use an unverified raw `NameID` to look up arbitrary sessions across the whole system and invalidate them. Never let `POST /logout/saml2/slo` with an empty form turn into a "logout all" endpoint.

### 9.2. SLO Can Complete Partially

The IdP may lack SLO support, the browser may close mid-flow, LogoutResponse may return an error, or another SP may fail to process the request. UI must distinguish **local session destroyed** from **federation SLO confirmed**. Never promise "logged out of all devices" when SAML SLO only targets sessions per IdP profile.

## 10. SameSite Cookies, CSRF, and Cross-Site POST

`POST /logout` from an SP page is usually same-origin so the browser sends SP cookies. `POST /logout/saml2/slo` from the IdP is usually a cross-site POST; `SameSite=Lax` or `Strict` cookies may be omitted. If the SLO callback needs session/request state, the result can be failing to locate the pending LogoutRequest.

How to investigate:

1. In browser tests, inspect `Set-Cookie` at the SP and the `Cookie` header on the callback (never copy cookie values into logs/tickets).
2. Confirm `SameSite`, `Secure`, `HttpOnly`, `Domain`, and `Path`.
3. Verify the public HTTPS host via trusted proxy headers; never put internal HTTP URLs into SAML metadata.
4. For flows requiring cookies on cross-site POSTs, consider `SameSite=None; Secure` per threat model, keeping CSRF tokens on all user-initiated actions.
5. When using shared sessions/Redis/multi-node, ensure callbacks hitting another pod still locate state and never fail open.
6. Never drop `InResponseTo`/signature validation or `POST /logout` CSRF to fix cookie issues.

**SameSite is a secondary layer**: `SameSite=None` makes cookies travel cross-site more easily, making CSRF tokens on browser logout even more essential. CORS does not replace CSRF because cross-origin HTML forms do not need to read responses to cause side effects.

## 11. SPAs and JavaScript Logout

A SPA using Spring Security cookies/sessions can send the CSRF token in a header:

```javascript
// Fragment: headerName and csrfToken are issued by the backend via the
// corresponding Spring Security mechanism; never hardcode tokens.
async function localLogout(headerName, csrfToken) {
  const response = await fetch("/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { [headerName]: csrfToken }
  });
  if (!response.ok) {
    throw new Error("Logout failed");
  }
}
```

**Note:** `fetch` does not automatically perform top-level browser navigation to the IdP. If `POST /logout` triggers RP-initiated SAML SLO, Spring Security may return a redirect or HTML form to the IdP, but handling it inside `fetch` does not guarantee the browser completes SLO. For SAML Web SSO, a **form POST from the main document** is usually more appropriate. SPAs need a dedicated navigation flow if SLO is desired—never treat `fetch` 200/302 as proof that all SPs/IdP logged out.

If the SPA reads the CSRF token from a cookie (`CookieCsrfTokenRepository`) or a dedicated endpoint, review deferred tokens and BREACH/XOR token handling per your Spring Security version. Do not extract raw tokens improperly and pair them with the wrong request handler. XSS can still defeat CSRF if an attacker runs same-origin script, so CSP/output encoding remain essential.

## 12. Plain Java 17: Checking the Semantics of CSRF on User Logout

The following program simulates a browser sending method/path/sessionId/token. This is an **educational model**, not Spring's `CsrfFilter`, and **contains no SAML XML/signature verification**. The illustrative strings are not high-entropy session IDs/tokens for production.

Save `UserLogoutCsrfDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

public class UserLogoutCsrfDemo {

    record Request(String method, String path,
                   String sessionId, String token) {}

    static boolean allowUserLogout(
            Request request, Map<String, String> tokens) {

        if (!"POST".equals(request.method())) {
            return false;
        }
        if (!"/logout".equals(request.path())
                && !"/saml2/logout".equals(request.path())) {
            return false;
        }

        String expected = tokens.get(request.sessionId());
        if (expected == null || request.token() == null) {
            return false;
        }
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8),
                request.token().getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) {
        Map<String, String> sessions = Map.of(
                "session-A", "token-A",
                "session-B", "token-B");

        System.out.println("GET logout: " + allowUserLogout(
                new Request("GET", "/logout", "session-A", "token-A"),
                sessions));
        System.out.println("POST missing token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", null),
                sessions));
        System.out.println("POST wrong token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", "wrong"),
                sessions));
        System.out.println("POST valid token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", "token-A"),
                sessions));
        System.out.println("Cross-session token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", "token-B"),
                sessions));
        System.out.println("SAML callback as user logout: " + allowUserLogout(
                new Request("POST", "/logout/saml2/slo",
                            "session-A", "token-A"),
                sessions));
    }
}
```

Compile and run with JDK 17+:

```bash
javac UserLogoutCsrfDemo.java
java UserLogoutCsrfDemo
```

**Exact** stdout:

```text
GET logout: false
POST missing token: false
POST wrong token: false
POST valid token: true
Cross-session token: false
SAML callback as user logout: false
```

Explanation: GET does not mutate state; POST with missing/wrong/cross-session token is rejected; only POST to a user logout endpoint with a matching token is permitted to proceed. Callback `/logout/saml2/slo` is not treated as user logout; it must pass through dedicated SAML validators.

**Limitation:** `MessageDigest.isEqual` only illustrates byte comparison; dummy session/token data has no cryptographic protection, and a `true` result does not prove the user is authenticated. Do not use this snippet in place of Spring Security's `CsrfTokenRepository` or SAML signature/issuer/NameID/SessionIndex/`InResponseTo` validation.

## 13. Testing with Spring Security MockMvc

With `spring-security-test` and a `MockMvc mvc` configured with security filters, you can verify missing/wrong tokens are blocked. Snippet:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mvc.perform(post("/logout").with(user("alice")))
        .andExpect(status().isForbidden());

mvc.perform(post("/logout")
        .with(user("alice"))
        .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
```

This snippet is **not a standalone runnable JDK class**; it requires Spring Test/MockMvc. When a custom `AccessDeniedHandler` returns a redirect or custom status, assert "did not log out" via session/handler side effects rather than only hardcoding 403.

For valid tokens and RP-initiated SLO, a plain mock principal `user("alice")` is **not a `Saml2AuthenticatedPrincipal`**. You need a real SAML authentication context, test registration/IdP, and signed LogoutRequest/Response fixtures to verify real SLO.

### 13.1. Essential Test Matrix

| Scenario | Expectation |
| --- | --- |
| `GET /logout` with CSRF enabled | Does not invalidate session |
| External image/link GET logout | No forced logout |
| `POST /logout` without token | Rejected before logout handlers |
| `POST /logout` wrong token | Rejected |
| `POST /logout` token from another session | Rejected |
| `POST /logout` valid token with SAML principal | Initiates logout per SLO config |
| `POST /saml2/logout` without token in split-URL config | Rejected |
| `POST /saml2/logout` valid token | RP-initiated SLO |
| `POST /logout` in split-URL config | Local logout; emits no LogoutRequest |
| IdP sends signed SAMLRequest to protocol callback | SAML validator accepts without form token |
| IdP sends unsigned/bad-signature SAMLRequest | Rejected; no arbitrary logout |
| Callback SAMLResponse wrong `InResponseTo` | Rejected |
| SAMLResponse replay or issuer differs from registered IdP | Rejected |
| POST callback without valid SAML field | Does not invoke local logout |
| SameSite cookie blocks callback | Do not bypass correlation; fix cookie/state |
| LogoutRequest created on pod A, response hits pod B | Shared state or fail closed |
| Expired session/stale token | Safe rejection; UI prompts reload |
| Logout URL falls under CSRF-exempt wildcard | Security test must fail; fix matcher |
| Local-only SLO yet UI claims logged out everywhere | UX test fails; display real scope |
| Logs contain CSRF tokens/cookies/SAMLResponse | Security QA fails |

### 13.2. End-to-End Browser Test

1. Log in via a test IdP with SLO enabled and a test user.
2. Inspect the logout form rendering the token (without sharing the value).
3. `GET /logout` confirms the session remains active.
4. POST with missing/wrong token confirms rejection and **no** LogoutRequest sent.
5. POST with valid token confirms local logout and signed LogoutRequest, if SLO is enabled.
6. IdP returns LogoutResponse; SP verifies `InResponseTo` and status.
7. IdP sends both valid and forged/unsigned LogoutRequests; SP processes only valid requests.
8. Test cross-site POST callbacks, SameSite cookies, and different pods.
9. Verify no tokens/sessions/raw SAML appear in logs/APM/WAF.
10. Verify UI messages distinguish local logout from federation SLO completion.

## 14. Troubleshooting Incidents

| Symptom | Primary Possibility | How to Handle |
| --- | --- | --- |
| Clicking logout returns 403 | Missing/wrong/stale token, session timeout | Render valid token, refresh/reload; never disable CSRF |
| GET logout only shows confirmation | Safe behavior | Submit POST form |
| GET logout immediately clears session | Custom GET logout or CSRF disabled | Restore POST+CSRF |
| POST with valid token triggers no SLO | `saml2Logout()` not enabled, IdP lacks SLO metadata, non-SAML principal | Check registration/SLO/handlers |
| IdP callback gets CSRF 403 | Custom matcher/chain blocks protocol POST | Scope exception strictly to callback; no wildcards |
| Unsigned callback still logs user out | Bypassing SAML validator | Restore filters/trust/signature/identity checks |
| SLO Response `InResponseTo` mismatch | Lost state/session/tenant/routing | Inspect LogoutRequest repository and cookies |
| SP logged out, re-login skips password | IdP session still alive | Distinguish local vs. SLO |
| SPA fetch does not navigate to IdP | Fetch does not replace top-level navigation | Use form POST/appropriate navigation flow |
| SLO partial failure | IdP/another app did not complete | Report real status; never promise global logout |
| CSRF token in URL/logs | Wrong UI or tracing | Move to hidden field/header; scrub logs |
| Multiple filter chains leave user logout without CSRF | Wrong matcher/priority | Test exact chain and endpoints |

**Do not diagnose solely by status code:** 403 may come from CSRF or authorization, 400 from SAML validators, 302 may be an IdP redirect or login page. Investigate in order: browser logout POST → CSRF → logout handlers → SAML request → IdP → SAML response callback. Use event/reason codes rather than raw SAML payloads.

## 15. Production Checklist

- [ ] User logout uses POST; GET never mutates the session.
- [ ] Spring Security CSRF tokens are rendered, submitted, and verified.
- [ ] Both local logout and custom RP-initiated logout URLs require tokens.
- [ ] No `csrf.disable()` and no wildcard ignoring `/logout/**`.
- [ ] `saml2Logout()` and IdP `SingleLogoutService`/SP credentials are properly configured.
- [ ] Callback `/logout/saml2/slo` is handled only by SAML validation, with no open custom logout controller.
- [ ] If a CSRF exception is needed, it targets only the exact callback method/path and rejects forged POSTs.
- [ ] Signed LogoutRequest/LogoutResponse verify trust/issuer/destination/NameID/`InResponseTo`/status/replay.
- [ ] `RelayState` is never used as a CSRF token or open redirect.
- [ ] SameSite/cookies/sessions/HTTPS/proxies are tested with cross-site POSTs.
- [ ] Multi-node LogoutRequest state is preserved or fails closed.
- [ ] Stale CSRF tokens/session timeouts are handled without bypasses.
- [ ] SPAs use proper browser navigation for SAML SLO.
- [ ] Local logout and SLO completion are accurately reflected in UI.
- [ ] Logs, metrics, APM, and WAF contain no CSRF/session tokens, raw SAML messages, or private keys.
- [ ] Tested GET, missing/wrong/cross-session tokens, unsigned SLO, wrong issuer, bad InResponseTo, replay, and lost cookies.

## 16. Review Questions

**1. Why must logout be protected against CSRF?**  
The browser can automatically attach session cookies on requests initiated by another site; the attacker does not need to read cookies.

**2. Is requiring POST alone sufficient?**  
No. Cross-site HTML forms can submit POSTs. A valid CSRF token is required.

**3. Does the IdP callback `POST /logout/saml2/slo` need a `_csrf` form token?**  
No. It is a SAML protocol callback; you must verify signatures/trust and SAML conditions rather than relying on an SP form token.

**4. Can we exempt `/logout/**` to fix an IdP callback error?**  
No. A wildcard can drop CSRF on the user logout endpoint itself; exempt only the exact callback if genuinely needed.

**5. Is `GET /logout` showing a confirmation page a bug?**  
No. It is how GET is prevented from directly destroying sessions, using a tokenized POST form instead.

**6. Does the SAML LogoutRequest signature replace the CSRF token for `POST /logout`?**  
No. The SP only builds the signed message **after** receiving the browser command; the initial command still requires CSRF.

**7. Does `SameSite=Lax` guarantee the IdP callback receives the session cookie?**  
No, cross-site POSTs may omit the cookie. Browser testing and cookie/state policies are needed.

**8. Does successfully emitting an SLO request guarantee all other SPs logged out?**  
No. It depends on the IdP response, profile, and each application's capabilities.

**9. Does a SPA calling `fetch` POST `/logout` automatically navigate the tab to the IdP?**  
Not reliably. SAML SLO is a browser flow and normally calls for a top-level form POST.

**10. Should a validly signed LogoutResponse with a wrong `InResponseTo` be accepted?**  
No. It must correlate with the exact stored LogoutRequest and satisfy protocol checks.

## 17. References

- [Spring Security 6.5 — Performing Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html): RP/AP SLO, endpoints, LogoutRequest/Response, and separating local/SLO.
- [Spring Security — CSRF protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): logout CSRF, forms, session timeout, SPA.
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET confirmation and POST logout/handlers.
- [Spring Security — Testing CSRF with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` and invalid tokens.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): LogoutRequest/Response, InResponseTo, and Status.
- [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Single Logout Profile.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-POST/Redirect and RelayState.
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF tokens and defense in depth.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): sessions/cookies/logout.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): SAML signatures/trust and validation.

**Remember:** **User clicks Log Out at SP → POST with CSRF token**. **IdP sends SAML LogoutRequest/LogoutResponse → SLO callback verifies signature and protocol**. The two mechanisms complement each other and never replace each other. Never disable CSRF globally, never wildcard-exempt user logout, and never claim federation-wide logout without knowing the SLO outcome.