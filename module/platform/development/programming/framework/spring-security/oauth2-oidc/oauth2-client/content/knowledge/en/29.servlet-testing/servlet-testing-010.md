# 29.10. Testing Success Handlers, Failure Handlers, and Saved Requests

## 1. The Problem: OIDC Login Succeeds, Yet Users Are Sent to the Wrong Page

A portal runs **Spring Security OAuth 2.0/OIDC Client on the Servlet stack**. While unauthenticated, a user opens:

~~~text
GET /reports/quarterly?year=2026
~~~

Spring Security saves this request, redirects to the login page, and then initiates the OAuth2 Authorization Code Flow at the OpenID Provider (OP). Once the user authenticates successfully, the product expects them to return to the exact report they opened.

However, a change to <code>AuthenticationSuccessHandler</code> sends every user to <code>/home</code>. Someone else tries to fix it by reading <code>next</code> from the query string and redirecting directly, introducing an **open redirect** vulnerability. Meanwhile, a test running <code>mockMvc.perform(get("/home").with(oidcLogin()))</code> stays green, misleading the team into thinking the success handler was tested.

Another issue: the OP returns <code>access_denied</code> or the callback carries a bad state. The application must invoke the **authentication failure handler**, must not create an authenticated session, must not reflect unvalidated <code>error_description</code> values, and must not reuse a stale saved request to send a user into another account's page.

To test properly, separate three responsibilities clearly:

1. **Authentication success handler** determines behavior after successful authentication, especially redirects.
2. **Authentication failure handler** determines behavior when authentication fails, such as redirecting to the login page with a safe message.
3. **RequestCache/SavedRequest** remembers the URL the user tried to visit **before** being redirected to login.

> **Key point:** <code>SecurityMockMvcRequestPostProcessors.oidcLogin()</code> or <code>oauth2Login()</code> attaches a simulated authentication to the **request under test**. They are useful for testing controller authorization, yet **do not execute the Authorization Code callback and do not invoke the OAuth2 Login success/failure handlers**.

## 2. Lesson Objectives

After this lesson, you will be able to:

1. Describe the lifecycle: unauthenticated protected request -> request cache -> OAuth2 Login -> success handler -> original URL.
2. Distinguish <code>SavedRequest</code>, <code>RequestCache</code>, <code>OAuth2AuthorizationRequestRepository</code>, and <code>SecurityContext</code>.
3. Intentionally use <code>SavedRequestAwareAuthenticationSuccessHandler</code>, <code>SimpleUrlAuthenticationSuccessHandler</code>, and custom success handlers.
4. Test <code>SimpleUrlAuthenticationFailureHandler</code> or a custom <code>AuthenticationFailureHandler</code> without leaking data from the OP.
5. Write unit tests for handlers using <code>MockHttpServletRequest</code>, <code>MockHttpServletResponse</code>, and <code>MockHttpSession</code>.
6. Use <code>MockMvc</code> to verify protected URLs are saved in <code>HttpSessionRequestCache</code> when the user is unauthenticated.
7. Understand the limits of <code>oauth2Login()</code> and <code>oidcLogin()</code>, and design integration tests that pass through the real OAuth2 Login filter.
8. Test branches: with/without saved request, default target, always-use-default, target parameter, account switching, and logout.
9. Control redirect URLs, query parameters, state, session fixation, multiple tabs, and multiple instances.
10. Diagnose errors such as <code>authorization_request_not_found</code>, redirect loops, stale saved requests, and HTTP 403s unrelated to the success handler.

## 3. End-to-End Flow Diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant R as Reports Controller / Spring MVC
    participant S as Spring Security Filter Chain
    participant C as RequestCache
    participant OP as OpenID Provider

    U->>B: Open /reports/quarterly?year=2026
    B->>S: GET /reports/quarterly?year=2026
    S->>S: No valid Authentication yet
    S->>C: Save original protected request
    S-->>B: Redirect /login
    B->>S: GET /oauth2/authorization/company
    S->>S: Create state/nonce/PKCE; save authorization request
    S-->>B: Redirect OP Authorization Endpoint
    B->>OP: Authorization request
    OP->>U: Authentication/consent
    OP-->>B: Authorization response code + state
    B->>S: GET /login/oauth2/code/company?code=...&state=...
    S->>S: Correlate state, exchange code, validate OIDC identity
    S->>S: Save SecurityContext / authorized client
    S->>C: Lookup original SavedRequest
    S-->>B: SuccessHandler redirects to /reports/quarterly?year=2026
    B->>S: GET /reports/quarterly?year=2026
    S->>R: Authenticated request
    R-->>B: Report response
~~~

If the OP denies consent or callback validation fails:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant OP as OpenID Provider
    participant F as OAuth2LoginAuthenticationFilter
    participant H as AuthenticationFailureHandler
    U->>OP: Deny consent
    OP-->>B: Redirect error=access_denied&state=...
    B->>F: GET /login/oauth2/code/company
    F->>F: Handle callback error / correlation
    F->>H: AuthenticationException
    H-->>B: Redirect /login?error=oauth2
    Note over B: No new authenticated session created
~~~

An application should have **separate tests** for the request cache, success handler, failure handler, and OIDC protocol; never confuse a mocked logged-in user with testing the entire sequence above.

## 4. Components to Distinguish

| Component | Typical type/implementation | Where is it stored or executed? | Purpose |
|---|---|---|---|
| <code>RequestCache</code> | <code>HttpSessionRequestCache</code> | Spring Security web infrastructure | Saves the initial protected request |
| <code>SavedRequest</code> | <code>DefaultSavedRequest</code> | HTTP session via RequestCache | Holds the redirect URL and matching request snapshot |
| <code>OAuth2AuthorizationRequestRepository</code> | <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | OAuth2 Login initiation/callback | Stores authorization request + state/PKCE correlation |
| <code>SecurityContextRepository</code> | Depends on config/version | Post-authentication | Persists SecurityContext/Authentication |
| <code>OAuth2AuthorizedClientRepository</code> | Session-backed or custom | Token/authorized-client lifecycle | Stores access/refresh tokens per registration/principal |
| <code>AuthenticationSuccessHandler</code> | <code>SavedRequestAwareAuthenticationSuccessHandler</code> | After successful authentication | Redirects and handles login success |
| <code>AuthenticationFailureHandler</code> | <code>SimpleUrlAuthenticationFailureHandler</code> or custom | Authentication failure | Redirects and handles login errors |

### 4.1. `SavedRequest` Is Not an Authorization Request

After visiting a protected URL:

~~~text
HttpSessionRequestCache
    SavedRequest:
       /reports/quarterly?year=2026
~~~

After clicking Login:

~~~text
HttpSessionOAuth2AuthorizationRequestRepository
    OAuth2AuthorizationRequest:
       clientRegistrationId = company
       state = random-state
       redirectUri = /login/oauth2/code/company
       nonce/PKCE attributes when applicable
~~~

Both objects have **different lifecycles**.

- `SavedRequest` helps **return to the requested page**.
- `AuthorizationRequest` helps **verify the login result belongs to the original OAuth2 request**.

Never use a saved URL in place of `state`. Never use `state` directly as a return URL, and certainly never trust a browser-supplied redirect query parameter instead of a `SavedRequest` captured from a protected request.

### 4.2. `SavedRequest` Is Not `SecurityContext`

`SavedRequest` may be saved before the user is authenticated. It **does not prove the user is authorized** to access that URL. After login, when the browser visits that URL again, Spring Security **must evaluate authorization again** against the newly authenticated principal.

For example, user B logs in without permission to open <code>/reports/finance</code>: the redirect to that route may happen, yet the backend must still return 403 if B lacks the permission.

### 4.3. Request Cache Differs from Saved-Request-Aware Handler

<code>HttpSessionRequestCache</code> saves and retrieves requests; <code>SavedRequestAwareAuthenticationSuccessHandler</code> picks the right target URL after login.

If you configure the handler without a `RequestCache` saving requests, the handler falls back to its default target. If `RequestCache` saves requests while a custom handler always redirects to <code>/home</code>, the saved request goes unused.

## 5. Default Mechanics of Spring Security OAuth2 Login

Spring Security Servlet typically involves:

~~~text
ExceptionTranslationFilter
    ↳ handles unauthenticated protected request
    ↳ RequestCache.saveRequest(...)
    ↳ AuthenticationEntryPoint → login page / OAuth2 authorization initiation

OAuth2AuthorizationRequestRedirectFilter
    ↳ /oauth2/authorization/{registrationId}
    ↳ builds request with state and redirects to OP

OAuth2LoginAuthenticationFilter
    ↳ /login/oauth2/code/{registrationId}
    ↳ receives authorization response
    ↳ authentication success / failure

RequestCacheAwareFilter
    ↳ matches post-redirect request with saved request per RequestCache policy
~~~

This is a role diagram, **not an absolute ordering of every filter** across all Spring Security versions or `SecurityFilterChain` setups.

### 5.1. URLs and Roles

| URL | Who calls it | Meaning |
|---|---|---|
| <code>GET /reports/quarterly</code> | Browser | Protected resource; eligible for caching |
| <code>GET /login</code> | Browser | Provider selection page if app defines one |
| <code>GET /oauth2/authorization/company</code> | Browser | Initiation for registration <code>company</code> |
| <code>GET /login/oauth2/code/company</code> | OP redirect via browser | Callback code + state |
| <code>GET /reports/quarterly</code> after success | Browser | Fresh request to the protected resource |

<code>/oauth2/authorization/company</code> is **not** a URL that should be saved as the original protected request when the user was viewing a report. If the request cache gets overwritten by login/authorization URLs, users can end up in redirect loops.

### 5.2. `SuccessHandler` Does Not Perform OIDC Validation

The success handler is called **after authentication infrastructure has already accepted the login**. It does not replace:

- Verifying OAuth2 `state`.
- Exchanging the code at the right Token Endpoint.
- Checking PKCE/nonce where applicable.
- Verifying ID Token signature/issuer/audience/expiration.
- Saving the authorized client and `SecurityContext` per policy.

Never invoke the success handler directly with a mock `Authentication` and claim you tested the OIDC protocol.

## 6. `SavedRequestAwareAuthenticationSuccessHandler`

Class:

~~~java
org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler
~~~

This handler uses <code>RequestCache</code> to send users back to the URL they requested before login.

### 6.1. Target URL Selection Rules

Common options:

1. When **alwaysUseDefaultTargetUrl=true**, the handler prefers the default target; the saved request may be removed.
2. When **targetUrlParameter** is configured and the request carries a parameter accepted by the handler, the target parameter can take precedence.
3. If a <code>SavedRequest</code> remains, use <code>SavedRequest.getRedirectUrl()</code>.
4. If there is no saved request or override, use the default target.

Cleanup, matching, and redirect strategy details depend on version, yet this priority order is the core contract to test.

### 6.2. Safe Configuration

~~~java
import org.springframework.security.web.authentication
    .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;

SavedRequestAwareAuthenticationSuccessHandler handler =
    new SavedRequestAwareAuthenticationSuccessHandler();

handler.setRequestCache(requestCache);
handler.setDefaultTargetUrl("/home");
handler.setAlwaysUseDefaultTargetUrl(false);
~~~

In this snippet, <code>requestCache</code> is a provided bean or dependency.

When a `SavedRequest` exists:

~~~text
GET /reports/quarterly?year=2026
    ↓
Login success
    ↓
Redirect /reports/quarterly?year=2026
~~~

When the user opens the login page directly:

~~~text
GET /login
    ↓
Login success, no SavedRequest
    ↓
Redirect /home
~~~

### 6.3. Why Should `targetUrlParameter` Not Be Enabled Arbitrarily?

A configuration like:

~~~java
handler.setTargetUrlParameter("next");
~~~

can make the handler treat <code>next</code> from the request as the redirect target, depending on configuration and version. If a browser or attacker supplies an unvalidated absolute URL, an **open redirect** risk emerges.

Never treat <code>next=https://attacker.example</code> as a valid target simply because it appeared in the query string. If `returnTo` is required, enforce an internal-route allowlist, relative-URL validation, protected transaction state, and post-login authorization checks.

### 6.4. When You Always Want to Land on `/home`

~~~java
handler.setAlwaysUseDefaultTargetUrl(true);
handler.setDefaultTargetUrl("/home");
~~~

This policy fits systems that must route users through a dashboard after login, yet is **unsuitable** if the requirement is resuming a protected URL. Tests must mirror the product decision.

## 7. `AuthenticationFailureHandler` and Error Types

Interface:

~~~java
org.springframework.security.web.authentication.AuthenticationFailureHandler
~~~

A common implementation:

~~~java
org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler
~~~

### 7.1. What Does a Failure Handler Do?

When authentication fails, the handler can:

- Redirect to the login page with a stable error marker.
- Forward or return an HTTP error per contract.
- Record filtered metric/log categories.
- Clean up or retain temporary flow state per policy.
- **Never create an authenticated session** from an unverified token.

### 7.2. Never Expose Raw `OAuth2Error`

An OP may return:

~~~text
error=access_denied
error_description=Policy details from OP
error_uri=https://op.example.org/help
~~~

Never pass the raw description or URI straight to the browser:

~~~text
/login?error_description=<untrusted upstream text>
~~~

URLs enter browser history, `Referer` headers, and access logs. Descriptions can leak policy details or become reflected XSS if rendered unencoded.

### 7.3. Distinguishing User Denial, State Mismatch, and Outage

| Error | Nature | Handling |
|---|---|---|
| <code>access_denied</code> | User/OP denied authorization | Safe message, allow choosing login again |
| State mismatch | Callback cannot be correlated to an authorization request | Reject; never disable state validation |
| <code>invalid_grant</code> code exchange | Expired/reused code, wrong PKCE/redirect | Investigate OP integration; do not retry code endlessly |
| Bad ID Token signature/issuer | Untrusted authentication proof | Fail closed; alert on anomalies |
| OP network timeout/5xx | Upstream temporarily unavailable | Integration-level retry policy, neutral user message |

The failure handler should not map every failure to "Wrong password", because an OAuth2 Client does not handle the OP's passwords directly.

## 8. Sample Servlet Application Configuration

Assuming Java 17, Spring Boot 3.x, and Spring Security 6.x on the MVC/Servlet stack. APIs may differ in 7.x; consult the reference docs for your project's version.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

No need to add WebFlux just to test Servlet OAuth2 Login. If you also test downstream `WebClient` calls in the same app, choose dependencies/stacks separately.

### 8.2. OIDC `ClientRegistration`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

In integration tests, use a test/stub OP with dedicated issuer, keys, and endpoints; never use production client secrets or ID Tokens. The URLs above illustrate configuration, not a live OP.

### 8.3. `SecurityFilterChain` with `RequestCache` and Handlers

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication
    .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.authentication
    .SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
public class WebSecurityConfig {

    @Bean
    RequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    AuthenticationSuccessHandler oauth2SuccessHandler(
            RequestCache requestCache) {

        var handler = new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/home");
        handler.setAlwaysUseDefaultTargetUrl(false);
        return handler;
    }

    @Bean
    AuthenticationFailureHandler oauth2FailureHandler() {
        return new SimpleUrlAuthenticationFailureHandler(
            "/login?error=oauth2");
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestCache requestCache,
            AuthenticationSuccessHandler oauth2SuccessHandler,
            AuthenticationFailureHandler oauth2FailureHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/home", "/error", "/assets/**")
                    .permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().authenticated())
            .requestCache(cache ->
                cache.requestCache(requestCache))
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .successHandler(oauth2SuccessHandler)
                .failureHandler(oauth2FailureHandler))
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Note:** This is an illustrative `SecurityFilterChain`. If you define multiple chains, ensure the protected resource, login initiation, and OAuth2 callback are all handled by the right chain. <code>.requestMatchers("/reports/**").authenticated()</code> inside authorization rules **is not equivalent** to <code>securityMatcher(...)</code> for selecting a chain.

### 8.4. Sample Login Page and Controller

~~~java
package example.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PortalController {

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/home")
    @ResponseBody
    String home() {
        return "Welcome";
    }

    @GetMapping("/reports/{reportId}")
    @ResponseBody
    String report(
            @PathVariable String reportId,
            @RequestParam(required = false) String year) {
        return "Report " + reportId + ", year=" + year;
    }
}
~~~

This assumes a <code>login</code> view template rendering:

~~~html
<a href="/oauth2/authorization/company">
  Sign in with Company SSO
</a>
~~~

If not using a template engine, a static HTML page or another controller can serve it.

## 9. Three Testing Levels to Keep Separate

| Level | Tools | What it tests | What it does not test |
|---|---|---|---|
| **Handler unit test** | Mock request/response/session, calling handler directly | Redirect targets, errors, request-cache branches, sanitization | OIDC callback and Token Endpoint |
| **MockMvc filter-chain slice/integration** | MockMvc + Spring Security filters | Unauthenticated request cached, entry point, session, authorization rules | Does not run OAuth2 callback merely by using <code>oidcLogin()</code> |
| **OIDC end-to-end integration** | MockMvc + test OP/Token Endpoint, valid JWKS/ID Token, session correlation | Authorization initiation, code exchange, state/nonce validation, real handler invocation | Browser cookies/SameSite if MockMvc only |

Do not use a unit test to claim the entire OAuth2/OIDC flow works. Conversely, you do not need to boot a test OP just to verify whether the handler redirects to `SavedRequest`.

## 10. Unit Testing `SavedRequestAwareAuthenticationSuccessHandler`

A handler test can call <code>onAuthenticationSuccess(...)</code> directly with mock servlet objects. This tests redirect logic **without needing an OP**.

### 10.1. Test Setup

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.web.authentication
    .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest
    .HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;

import static org.junit.jupiter.api.Assertions.*;

class SavedRequestSuccessHandlerTest {

    private HttpSessionRequestCache requestCache;
    private SavedRequestAwareAuthenticationSuccessHandler handler;

    @BeforeEach
    void setUp() {
        requestCache = new HttpSessionRequestCache();
        handler = new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/home");
    }

    @Test
    void redirectsToOriginalProtectedUrlWhenSavedRequestExists()
            throws Exception {

        var original = new MockHttpServletRequest(
            "GET", "/reports/quarterly");
        original.setScheme("https");
        original.setServerName("portal.example.org");
        original.setServerPort(443);
        original.setQueryString("year=2026");

        // Simulate Security filter having saved the protected request.
        requestCache.saveRequest(
            original, new MockHttpServletResponse());

        SavedRequest saved = requestCache.getRequest(
            original, new MockHttpServletResponse());
        assertNotNull(saved);

        var callback = new MockHttpServletRequest(
            "GET", "/login/oauth2/code/company");
        callback.setSession(
            (MockHttpSession) original.getSession(false));
        var response = new MockHttpServletResponse();

        var authenticated = new TestingAuthenticationToken(
            "alice", "ignored", "ROLE_USER");

        handler.onAuthenticationSuccess(
            callback, response, authenticated);

        assertEquals(
            saved.getRedirectUrl(),
            response.getRedirectedUrl());
        assertEquals(302, response.getStatus());
        assertTrue(
            response.getRedirectedUrl()
                .contains("/reports/quarterly"));
        assertTrue(
            response.getRedirectedUrl()
                .contains("year=2026"));
    }
}
~~~

In this test:

- <code>original</code> simulates the pre-login GET.
- <code>HttpSessionRequestCache</code> saves the protected request.
- <code>callback</code> shares **the same `MockHttpSession`**, so the success handler finds `SavedRequest`.
- <code>TestingAuthenticationToken</code> is simply an authenticated object sufficient for **unit testing the redirect handler**; this test does not claim OIDC signatures/nonces were validated.
- Comparing against <code>SavedRequest.getRedirectUrl()</code> avoids hardcoding scheme/port/query encoding in case the implementation normalizes URLs.

### 10.2. Why Must the Callback Use the Same Session?

If <code>callback</code> does not share <code>original</code>'s session:

~~~text
Original request → SavedRequest in session S1
Callback request → session S2 or no session
SuccessHandler → SavedRequest not found
Redirect → /home
~~~

In production, cookie path/domain/SameSite, Spring Session, load balancers, and session fixation protection affect correlation. In unit tests, we intentionally pass the same session to isolate redirect logic.

### 10.3. Requests Without a Saved Request

Add test:

~~~java
@Test
void fallsBackToHomeWithoutSavedRequest() throws Exception {
    var request = new MockHttpServletRequest(
        "GET", "/login/oauth2/code/company");
    var response = new MockHttpServletResponse();
    var authenticated = new TestingAuthenticationToken(
        "alice", "ignored", "ROLE_USER");

    handler.onAuthenticationSuccess(
        request, response, authenticated);

    assertEquals("/home", response.getRedirectedUrl());
}
~~~

This simulates a user opening the login page directly with no prior protected URL saved.

### 10.4. Testing `alwaysUseDefaultTargetUrl`

~~~java
@Test
void alwaysUseDefaultTargetOverridesSavedRequest()
        throws Exception {

    handler.setAlwaysUseDefaultTargetUrl(true);

    var original = new MockHttpServletRequest(
        "GET", "/reports/quarterly");
    requestCache.saveRequest(
        original, new MockHttpServletResponse());

    var callback = new MockHttpServletRequest(
        "GET", "/login/oauth2/code/company");
    callback.setSession(
        (MockHttpSession) original.getSession(false));

    var response = new MockHttpServletResponse();
    handler.onAuthenticationSuccess(
        callback,
        response,
        new TestingAuthenticationToken(
            "alice", "ignored", "ROLE_USER"));

    assertEquals("/home", response.getRedirectedUrl());
    assertNull(requestCache.getRequest(
        callback, new MockHttpServletResponse()));
}
~~~

This test should reflect the behavior of your actual Spring Security version. <code>SavedRequestAwareAuthenticationSuccessHandler</code> removes the saved request when the always-default branch is selected.

### 10.5. Is `SavedRequest` Removed Immediately in Every Branch?

Never claim <code>SavedRequest</code> always disappears immediately once the success handler redirects. In the saved-request branch, the implementation may retain the request for the upcoming GET so <code>RequestCacheAwareFilter</code>/<code>RequestCache.getMatchingRequest</code> can replay or clear it according to configuration.

Therefore, proper tests focus on:

- Which target URL was chosen.
- Whether the subsequent request runs under the new `Authentication`.
- Ensuring `SavedRequest` is not reused repeatedly outside policy.

Do not assert that the session attribute is already deleted the instant the success handler returns as if that were a universal contract across all versions.

## 11. Unit Testing `AuthenticationFailureHandler`

### 11.1. `SimpleUrlAuthenticationFailureHandler`

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication
    .SimpleUrlAuthenticationFailureHandler;

import static org.junit.jupiter.api.Assertions.*;

class OAuth2FailureHandlerTest {

    @Test
    void redirectsToFixedLocalLoginErrorUrl() throws Exception {
        var handler = new SimpleUrlAuthenticationFailureHandler(
            "/login?error=oauth2");

        var request = new MockHttpServletRequest(
            "GET", "/login/oauth2/code/company");
        var response = new MockHttpServletResponse();
        var failure = new OAuth2AuthenticationException(
            new OAuth2Error(
                "access_denied",
                "Sensitive upstream explanation",
                "https://other.example/help"));

        handler.onAuthenticationFailure(
            request, response, failure);

        assertEquals(
            "/login?error=oauth2",
            response.getRedirectedUrl());
        assertEquals(302, response.getStatus());
        assertFalse(
            response.getRedirectedUrl()
                .contains("Sensitive"));
        assertFalse(
            response.getRedirectedUrl()
                .contains("other.example"));
    }
}
~~~

This test focuses on the **redirect URL**; it does not mean the exception object is absent from the session. <code>SimpleUrlAuthenticationFailureHandler</code> can store the exception in the session depending on implementation/configuration for view rendering; the error page **must never render raw, unfiltered messages or descriptions verbatim**.

### 11.2. Why Is Checking "Got a 302" Not Enough?

A redirect to:

~~~text
https://attacker.example/capture?message=<raw idp error>
~~~

also returns 302, yet is unsafe.

Assert instead:

1. The redirect target stays within permitted internal domains/routes.
2. Only a bounded error marker is included.
3. No raw upstream description or URI appears.
4. No authorization code, access/refresh tokens, or session cookies are leaked.
5. Failure never turns into a successful `Authentication`.

### 11.3. Custom Failure Handler by Error Code

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public final class SafeOidcFailureHandler
        implements AuthenticationFailureHandler {

    private static final Logger log =
        LoggerFactory.getLogger(SafeOidcFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        String category = "login_failed";

        if (exception instanceof OAuth2AuthenticationException oauth2) {
            String code = oauth2.getError().getErrorCode();
            if ("access_denied".equals(code)) {
                category = "user_denied";
            } else if ("invalid_grant".equals(code)) {
                category = "grant_rejected";
            }
        }

        // Emit bounded category to telemetry, never the raw error.
        log.warn("oidc_login_failed category={}", category);

        response.sendRedirect(
            request.getContextPath() + "/login?error=oauth2");
    }
}
~~~

This is an **alternative** to <code>SimpleUrlAuthenticationFailureHandler</code> in section 8.3. Never register two competing failure handlers on the same chain expecting them to run sequentially on their own.

## 12. Unit Testing a Success Handler with Logging/Audit

When custom logic such as logging a "Login succeeded" event is needed, never erase `SavedRequest` behavior by hardcoding a fixed redirect.

### 12.1. Decorator Pattern

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;

public final class AuditingSuccessHandler
        implements AuthenticationSuccessHandler {

    private final AuthenticationSuccessHandler delegate;
    private final LoginAudit audit;

    public AuditingSuccessHandler(
            AuthenticationSuccessHandler delegate,
            LoginAudit audit) {
        this.delegate = delegate;
        this.audit = audit;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) throws IOException {

        audit.recordSuccessfulLogin(authentication);
        delegate.onAuthenticationSuccess(
            request, response, authentication);
    }
}
~~~

<code>LoginAudit</code> is an **application-defined interface** (for example <code>void recordSuccessfulLogin(Authentication authentication)</code>), not a built-in Spring Security class.

If auditing fails, decide explicitly whether login should fail; never let a slow network telemetry call without timeouts hang login. Auditing must never log raw ID Tokens, access/refresh tokens, or full OIDC claims.

### 12.2. Testing That the Delegate Is Invoked

~~~java
import static org.mockito.Mockito.*;

@Test
void auditThenDelegateSuccess() throws Exception {
    AuthenticationSuccessHandler delegate =
        mock(AuthenticationSuccessHandler.class);
    LoginAudit audit = mock(LoginAudit.class);

    var handler = new AuditingSuccessHandler(delegate, audit);
    var request = new MockHttpServletRequest();
    var response = new MockHttpServletResponse();
    var auth = new TestingAuthenticationToken(
        "alice", "ignored", "ROLE_USER");

    handler.onAuthenticationSuccess(request, response, auth);

    var order = inOrder(audit, delegate);
    order.verify(audit).recordSuccessfulLogin(auth);
    order.verify(delegate).onAuthenticationSuccess(
        request, response, auth);
}
~~~

This test verifies call order inside the decorator, **not the OIDC flow**. Pair it with the `SavedRequestAware` handler test to ensure redirects remain intact.

## 13. MockMvc: Verifying Unauthenticated Requests Are Saved

Goal of this test: when an unauthenticated user hits a protected URL, Spring Security saves the original request so the success handler can use it afterward.

### 13.1. `@SpringBootTest` + `@AutoConfigureMockMvc`

Assuming the application has the configuration from section 8:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProtectedRequestCacheIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RequestCache requestCache;

    @Test
    void unauthenticatedRequestIsSavedForLaterLogin() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/reports/quarterly")
                    .queryParam("year", "2026"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        var session = (MockHttpSession)
            result.getRequest().getSession(false);
        assertNotNull(session);

        SavedRequest saved = requestCache.getRequest(
            result.getRequest(),
            result.getResponse());

        assertNotNull(saved);
        assertTrue(saved.getRedirectUrl()
            .contains("/reports/quarterly"));
        assertTrue(saved.getRedirectUrl()
            .contains("year=2026"));
    }
}
~~~

**Condition:** the test application context must have a valid `ClientRegistrationRepository` or suitable test OP config to initialize OAuth2 Login; however, the test **does not need to call the Token Endpoint**, as it only checks that the protected URL is saved prior to the authorization flow.

### 13.2. Why Must Spring Security Filters Be Enabled?

MockMvc can run without the filter chain if test configuration intentionally disables filters, for example:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Then controller tests may return 200 or redirect on their own while skipping <code>ExceptionTranslationFilter</code> and <code>RequestCache</code>. Never use such tests to claim Spring Security's saved-request behavior was verified.

### 13.3. Is `@WebMvcTest` Enough?

<code>@WebMvcTest</code> is a slice focused on MVC components. It may not automatically pull in `ClientRegistrationRepository`, security beans, and token clients as in production.

You can use <code>@WebMvcTest</code> with <code>@Import(TestSecurityConfig.class)</code> and a specific test registration to keep scope small, while ensuring **the real chain and `RequestCache` are loaded**.

Never use <code>@WithMockUser</code> or <code>.with(oidcLogin())</code> in this protected-request caching test, because the goal is testing behavior while **unauthenticated**.

## 14. Why Does `oidcLogin()` Not Test the Success Handler?

Example:

~~~java
mockMvc.perform(get("/reports/quarterly")
        .with(oidcLogin()))
    .andExpect(status().isOk());
~~~

With import:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

This test is suitable for verifying that a route accepts a simulated OIDC principal, Spring Security authorization policies, or that a controller reads OIDC claims.

However, it **does not execute**:

~~~text
/oauth2/authorization/company
  → OP Authorization Endpoint
  → /login/oauth2/code/company?code=...&state=...
  → OAuth2LoginAuthenticationFilter
  → successHandler.onAuthenticationSuccess(...)
~~~

<code>oidcLogin()</code> merely prepares the test request with a matching authentication. No callback occurs and no filter authentication-success event fires as in the real flow.

### 14.1. `oauth2Login()` Has the Same Limitation

~~~java
mockMvc.perform(get("/reports/quarterly")
        .with(oauth2Login()))
    .andExpect(status().isOk());
~~~

This test also **does not prove** saved-request-aware redirection ran. It only places an `OAuth2AuthenticationToken` into the request context.

### 14.2. Pick the Test Matching Your Goal

| Test question | Use |
|---|---|
 Does the controller receive <code>OidcUser</code>? | <code>oidcLogin()</code> |
 Are role/scope authorization rules accurate? | <code>oidcLogin()</code>/<code>oauth2Login()</code> with matching authorities |
 Does the success handler pick `SavedRequest` or `/home`? | Invoke the handler directly with mock request/session |
 Is the protected URL saved by `RequestCache`? | MockMvc unauthenticated + security filters |
 Does callback `code`/`state` create an authenticated session and invoke the success handler? | Integration test with OP/Token Endpoint stub |
 Does OP error `access_denied` invoke the failure handler? | Handler unit test + callback error integration test |

## 15. What Does a Real OAuth2 Callback Integration Test Require?

To prove Spring Security genuinely calls the success/failure handler after OAuth2/OIDC Login, requests must traverse <code>OAuth2LoginAuthenticationFilter</code> and the authentication provider.

### 15.1. Components to Simulate

1. <code>ClientRegistration</code> with test issuer, Client ID, and authorization/token/JWK endpoints.
2. Browser session/cookie and saved request created before login.
3. <code>OAuth2AuthorizationRequestRepository</code> holding the request with `state`, redirect URI, and PKCE verifier/nonce where applicable.
4. Test OP returning authorization response <code>code</code> and <code>state</code>.
5. Test Token Endpoint returning an access token and valid ID Token matching the client registration.
6. Test JWK Set allowing Spring Security to verify the ID Token signature.
7. <code>OidcUser</code> produced after validation.
8. Real success handler/failure handler beans injected (optionally spied).

No production OP is needed. Use **WireMock**, **MockWebServer**, a test container/mock authorization server, or a controllable sandbox OP. What matters is that the stub's contract matches the flow.

### 15.2. Test OIDC ID Tokens Must Be Valid

A hand-built JWT like:

~~~json
{
  "sub": "alice",
  "email": "alice@example.org"
}
~~~

is not a valid ID Token. Sign the JWT with a test key and include claims such as:

~~~text
iss = exact test issuer
sub = test subject
aud = test client_id
iat, exp = valid
nonce = expected nonce when flow requires it
~~~

Additionally, the response/request must carry valid `state`, PKCE, and client authentication. Never disable signature/issuer/audience/nonce validation just to make tests easier to run.

### 15.3. Verifying Handlers with Spies

An integration test with a spied handler bean per your test framework can assert:

~~~java
verify(successHandler, times(1))
    .onAuthenticationSuccess(
        any(HttpServletRequest.class),
        any(HttpServletResponse.class),
        any(Authentication.class));
~~~

This is **only meaningful after** MockMvc executes a valid callback through the filter and you confirm the spy wraps the exact bean wired into <code>oauth2Login()</code>. Calling the handler method directly would also pass `verify`, without proving callback integration.

For a failure callback test:

~~~java
verify(failureHandler, times(1))
    .onAuthenticationFailure(
        any(HttpServletRequest.class),
        any(HttpServletResponse.class),
        any(AuthenticationException.class));
~~~

This is an **assertion pattern**, not a complete test class. Set up the OP stub, session, and bean spy according to your Spring Boot/Spring Security/Mockito versions.

### 15.4. Failure Callback Tests Must Not Skip `state`

For an error callback:

~~~text
/login/oauth2/code/company?error=access_denied&state=S1
~~~

a matching authorization request `S1` must exist if you want to test **valid error response processing**. With a wrong `state` or missing request, the framework may raise a different error; tests should distinguish:

- User/OP denied authorization.
- Callback arrived in the wrong session or with mismatched `state`.

Never forge an `Authentication` or disable `state` validation for failure-path tests.

## 16. `SavedRequest`: What Is Saved and When?

<code>DefaultSavedRequest</code> can capture the redirect URL, HTTP method, query parameters, and additional request details per implementation. <code>HttpSessionRequestCache</code> is used by default for requests requiring authentication.

### 16.1. Protected GET

~~~http
GET /reports/quarterly?year=2026 HTTP/1.1
Host: portal.example.org
~~~

Typical flow:

~~~text
Unauthenticated → redirect login → successful login → redirect original GET
~~~

### 16.2. Protected POST Should Not Be Blindly Replayed

Suppose an unauthenticated browser sends:

~~~http
POST /orders/confirm HTTP/1.1
Content-Type: application/json

{"orderId":"123"}
~~~

After login, a standard redirect URL triggers a **new navigation request**, without guaranteeing replay of the original body or HTTP method. Blindly replaying POSTs with stale payloads can cause:

- Duplicate transactions.
- CSRF bypass.
- Stale order state.
- Skipped re-verification of price, tenant, or ownership.

For side-effecting actions:

1. Require login before submission, or save a pending action **server-side** with a TTL and verification context.
2. After login, send the user to a GET page to **review and confirm**.
3. Submit a fresh POST with a valid CSRF token, idempotency key, and authorization.
4. Never auto-execute an unconfirmed POST.

### 16.3. `SavedRequest` Does Not Grant Permissions

If a user logs in with an OIDC account lacking permission for the earlier report, the redirect target must still pass Spring Security authorization, method security, and business policy.

A success handler must never do:

~~~java
response.getWriter().write(fetchReportForOriginalUser());
~~~

using an unverified identity attached to a saved request. It should only redirect per policy; the protected route evaluates the current principal.

## 17. Testing Query Strings and URL Encoding

A saved URL may contain:

~~~text
/reports/quarterly?year=2026&format=csv
~~~

Tests should not only assert <code>contains("/reports/quarterly")</code>; verify required query parameters survive the redirect.

### 17.1. Sample Assertions

~~~java
assertTrue(
    response.getRedirectedUrl()
        .contains("year=2026"));
assertTrue(
    response.getRedirectedUrl()
        .contains("format=csv"));
~~~

If queries contain Unicode, spaces, <code>&amp;</code>, or encoded slashes, use a URI parser/URL encoder matching your contract instead of fragile substrings. Ensure queries are not double-decoded or turned into open redirects.

### 17.2. Avoid Saving URLs with Credentials

Never design:

~~~text
/reports/view?access_token=...
~~~

because URLs end up in logs, browser history, `Referer` headers, and `SavedRequest`. Never put access tokens in query strings to "remember auth" across login.

### 17.3. Preventing Open Redirects

If the app permits <code>next</code>:

~~~text
/login?next=https://attacker.example
~~~

never redirect straight to an untrusted absolute URL on success.

Sound policies:

- Prefer `SavedRequest` captured from a server-received protected request.
- Allow only allowlisted or path-normalized internal return paths.
- Reject URLs with unusual schemes/hosts, <code>//evil.example</code>, or encoded open-redirect bypasses.
- Authorize the destination URL on the post-login request.
- Fall back to a safe default target if the return path is rejected.

Even `SavedRequest` warrants validation if the app exposes internal redirect endpoints accepting arbitrary destinations.

## 18. Failure Handlers and Leftover Session State After Errors

### 18.1. `SavedRequest` Present When Login Fails

Example:

~~~text
GET /reports/quarterly
  → SavedRequest
  → OAuth2 Login
  → OP access_denied
  → /login?error=oauth2
~~~

Depending on policy, `SavedRequest` may remain in the session so the user can retry. This makes sense when the user denied consent and then decides to retry. However, if the user switches accounts or a sensitive route carried prior context, keeping saved requests indefinitely can create UX and authorization confusion.

### 18.2. Policies for Clearing Cache After Failure

Options:

| Policy | Advantage | Risk |
|---|---|---|
| Keep `SavedRequest` after any error | Retrying login returns to the original URL | Stale redirects, multiple providers/accounts |
| Clear after every error | No stale targets retained | User must navigate again |
| Clear by error category/mode | Balances UX and security | Requires custom handler and tests |
| TTL/identity-bound saved target | Bounds long-lived requests | More complex; requires secure context storage |

No single policy fits every product. Define it explicitly and test accordingly.

### 18.3. Testing Cleanup via `RequestCache`

A custom failure handler can inject <code>RequestCache</code> and call:

~~~java
requestCache.removeRequest(request, response);
~~~

for flows that must cancel pending redirects. This is a deliberate choice, not behavior to apply blindly to every OIDC failure.

In tests, reuse the same session and assert:

~~~java
assertNull(requestCache.getRequest(
    callback, new MockHttpServletResponse()));
~~~

after the handler removes it. If the success handler needs `SavedRequest` to resume after a retry, do not perform this cleanup on every error.

## 19. Session Fixation and `SavedRequest` After Login

Spring Security applies session fixation protection upon successful authentication; on Servlet 3.1+, it typically uses <code>changeSessionId</code> as the framework default.

### 19.1. Changing Session ID Does Not Mean Losing Session Attributes

Process:

~~~text
Before authentication:
    HTTP session ID = S1
    SavedRequest = /reports/quarterly

After successful authentication:
    HTTP session ID = S2 (rotated)
    SecurityContext = authenticated user
    SavedRequest = available per session strategy/policy
~~~

Under standard framework configuration, session attributes are preserved across the session fixation strategy, allowing `SavedRequest` to drive the post-login redirect. Custom session management or repositories, however, may alter this behavior.

### 19.2. Integration-Level Verification

A valid end-to-end test should observe:

1. The user has a pre-login session holding `SavedRequest`.
2. A real OIDC callback establishes authentication.
3. The session fixation strategy runs.
4. `SavedRequest` is still honored properly.
5. The browser reaches the original protected URL under the new authenticated session.

Do not hardcode that the session ID must change to a specific value across every deployment; <code>SessionCreationPolicy</code> and fixation settings can vary.

### 19.3. Never Copy Old Session Cookies Manually

Never work around test failures by reattaching an old session cookie to an `Authentication` whose user changed. If security context/session rotation breaks, inspect the session strategy, session repository, and proxies.

## 20. Multiple Providers and Account Switching

An app has:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

An unauthenticated user opens <code>/reports/company</code>, then picks Partner. `SavedRequest` still points to a Company URL.

### 20.1. Never Use `SavedRequest` to Bypass Authorization

If the Partner principal lacks permission, the backend must deny access. The success handler only redirects; it grants neither roles nor scopes.

### 20.2. Stale `SavedRequest` During Account Switching

A user logged in as Alice chooses to switch to Bob. If the app retains a `SavedRequest` pointing to Alice's URL/data, Bob could be redirected to that stale route post-login.

Options:

- Clear `SavedRequest` when initiating an explicit account switch.
- Redirect to a neutral <code>/home</code> page after switching.
- Distinguish normal login from identity switching via server-side transaction state.
- Re-check tenant/role/cache when the new user hits the route.

Do not enable <code>alwaysUseDefaultTargetUrl(true)</code> globally if normal login needs URL resumption. Choose the policy based on the authenticated operation and transaction state.

### 20.3. Account Linking Differs from Switching

If a logged-in user A wants to **link identity B**, do not arbitrarily invalidate Authentication A before the callback; linking requires a transaction proving user A intentionally initiated attaching B. This is a security-sensitive flow needing its own CSRF/step-up and identity validation, not a simple `SavedRequest` redirect.

## 21. Multiple Tabs and Concurrent Login Flows

In the browser:

~~~text
Tab A: GET /reports/a → saved target A
Tab B: GET /reports/b → saved target B
Tab A: login Company
Tab B: login Partner
~~~

If `RequestCache` stores a single `SavedRequest` in the session, the newer request can **overwrite or alter** the earlier tab's target. <code>HttpSessionOAuth2AuthorizationRequestRepository</code> uses its own state/correlation; its concurrency behavior must also be tested.

### 21.1. Never Use `SavedRequest` as OAuth `state`

`state` must carry high entropy and bind to the authorization request, whereas `SavedRequest` is a navigation target. With multiple tabs open, never fix callback failures by doing:

~~~text
Ignore state, use whichever SavedRequest exists
~~~

That opens login CSRF and mix-up vulnerabilities.

### 21.2. UX Strategies

- Notify users when concurrent login/switch flows occur.
- Store server-side transactions keyed by `state` or a protected flow ID if concurrent flows must be supported.
- Bound lifetimes and maximum pending requests.
- After callback, pick the target tied to that specific flow if business rules require it.
- Never redirect user B to user A's private URL after an account switch.

### 21.3. Testing Race Conditions

1. Trigger two protected requests in the same session.
2. Observe the final `SavedRequest` per repository policy.
3. Initiate two OAuth2 authorization requests.
4. Call back each `state` against the test OP.
5. Confirm `state` checks are never skipped and `ClientRegistration`s never mix.
6. Verify the final target matches the intended UX.

Not every default Spring Security `RequestCache` guarantees isolated per-tab targets.

## 22. Multi-Instance Deployments and Spring Session

System behind a load balancer:

~~~text
Browser
   |
Load Balancer
   |------------------|
Instance A         Instance B
   |------------------|
        Redis
   Spring Session Store
~~~

The protected GET may hit A, while the OAuth2 callback hits B. If `SavedRequest` or `OAuth2AuthorizationRequest` lives only in A's memory, B cannot recover it.

### 22.1. Two Sources of Session State

~~~text
Spring Session shared store:
    SavedRequest                → original protected URL
    OAuth2AuthorizationRequest  → state/nonce/PKCE correlation
    SecurityContext             → authenticated principal
~~~

Properly shared HTTP sessions let all nodes handle this state when repositories use the session. However, <code>OAuth2AuthorizedClientService</code> or custom token stores may reside separately.

### 22.2. Writing Cross-Node Tests

1. Protected URL hits instance A.
2. Login initiation hits A or B.
3. Code/state callback hits B.
4. Success handler on B finds the right `SavedRequest`.
5. Browser redirects to the original URL and is authorized under the new principal.

If the callback reports <code>authorization_request_not_found</code>, it is normally a session/cookie/authorization-request-repository issue, not a failure handler redirect bug.

### 22.3. Do Not Assume Sticky Sessions Are the Only Durable Option

Session affinity can hide issues during testing, yet during node replacements or rolling deploys, callbacks can still hit a different node. In HA architectures, test shared session stores and session serialization compatibility.

Never bypass OAuth `state` validation just to make callbacks succeed on any node.

## 23. `SavedRequest` and CSRF

### 23.1. CSRF Tokens Differ from Saved Requests

A single HTTP session can simultaneously hold:

~~~text
SecurityContext
SavedRequest
OAuth2AuthorizationRequest
CsrfToken
~~~

Each has a distinct responsibility:

- The CSRF token proves a browser form/state-changing request originated in a valid context.
- OAuth <code>state</code> correlates the authorization response.
- `SavedRequest` remembers the original protected URL.

Never use the query <code>state</code> as a CSRF token for business POSTs, and never use `SavedRequest` as proof of a valid OAuth callback.

### 23.2. Logout Should Use POST + CSRF

After local user logout, stale saved targets may need clearing. Local logout must obey the browser's CSRF policy:

~~~html
<form action="/logout" method="post">
    <input type="hidden" name="_csrf"
           value="CSRF_TOKEN_FROM_SERVER">
    <button type="submit">Sign out</button>
</form>
~~~

The CSRF value must be generated by Spring Security/template rendering, never hardcoded.

### 23.3. GET Callbacks Do Not Need a Form CSRF Token

OIDC Authorization Code GET callbacks are protected by OAuth2 <code>state</code> and protocol token/ID Token validation. Do not require <code>_csrf</code> on default GET callbacks.

If using <code>response_mode=form_post</code>, check Spring Security version support, `SameSite` session cookies, and a narrow CSRF exemption for the callback POST. Never disable CSRF app-wide just because a callback or login handler hits a 403.

## 24. Success Handler Branches to Test

| Condition | Expected target | Test focus |
|---|---|---|
| `SavedRequest` present and not overridden | Original protected URL | <code>saved.getRedirectUrl()</code> |
| No `SavedRequest` | <code>/home</code> | Default target |
| Always-use-default enabled | <code>/home</code> | Saved target not preferred |
| Target parameter permitted by policy | Validated internal route | No open redirect |
| Saved target flagged invalid | Safe fallback | Never redirects to external domain |
| User switched accounts | Neutral target per UX | No stale URL from old identity |
| User logged in via wrong provider | Authorization must still run | No protected data leaked |
| Login succeeds after session ID rotation | Original target intact | Session state lifecycle |
| Login succeeds on another node | Original target intact | Shared session |

### 24.1. Asserting Redirect Status Alone Is Not Enough

A test like:

~~~java
.andExpect(status().is3xxRedirection());
~~~

does not tell you:

- Where did it redirect?
- Was `SavedRequest` used?
- Are query strings preserved?
- Is there an open redirect?
- Does the new principal have permission for the target?

Better: assert <code>Location</code> or <code>getRedirectedUrl()</code> along with the behavior of the subsequent request.

### 24.2. Session Attribute Cleanup

Exactly when `SavedRequest` is removed depends on handler branch, `RequestCache`, and next-request matching. Tests should target the real contract rather than relying on an internal session attribute name staying constant across every version.

## 25. Failure Handler Branches to Test

| Failure | Expected response/behavior |
|---|---|
| OP returns <code>access_denied</code> | Safe login error page, unauthenticated |
| Callback state mismatch | Rejected; never bypass correlation |
| Token Endpoint <code>invalid_grant</code> | Authentication fails, no endless code retries |
| OP HTTP 503 | Safe error UX, observability |
| Bad ID Token issuer/signature | Fail closed |
| Unknown custom `OAuth2Error` | Fallback category, no rendering exception |
| <code>error_description</code> contains HTML | No reflected XSS |
| External <code>error_uri</code> | No open redirect |
| Failure with existing `SavedRequest` | Retained or cleared per tested policy |
| Account switching fails | Never restores prior identity from browser params |

### 25.1. Do Not Test with Unmatched Mock Exceptions and Guess Causes

A unit test can pass:

~~~java
new OAuth2AuthenticationException(
    new OAuth2Error("access_denied"));
~~~

to verify the failure handler processes that code. However, to prove Spring Security constructs the right exception when an OP denies consent, write a **callback integration test** with a valid state/session.

### 25.2. Never Log Raw Exception Messages Automatically

An OAuth2 failure can carry <code>error_description</code> or callback details inside nested causes. If logs/traces write <code>exception.getMessage()</code> unchecked, upstream data or PII can leak. Log a normalized category + correlation ID and restricted diagnostics per policy.

## 26. Testing `AuthorizationFailure` Outside Login Failures

Post-login, a backend request needs to refresh an access token. The Token Endpoint returns <code>invalid_grant</code>, throwing <code>OAuth2AuthorizationException</code>.

This is not a login callback failure; <code>oauth2Login().failureHandler(...)</code> normally **does not run**.

### 26.1. Unit Testing Authorized-Client Manager Failure

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

class AuthorizedClientFailureTest {

    @Test
    void refreshFailureIsHandledInServiceLayer() {
        OAuth2AuthorizedClientManager manager =
            mock(OAuth2AuthorizedClientManager.class);

        var request = OAuth2AuthorizeRequest
            .withClientRegistrationId("company")
            .principal("user-123")
            .build();

        when(manager.authorize(request))
            .thenThrow(new OAuth2AuthorizationException(
                new OAuth2Error("invalid_grant")));

        var failure = assertThrows(
            OAuth2AuthorizationException.class,
            () -> manager.authorize(request));

        org.junit.jupiter.api.Assertions.assertEquals(
            "invalid_grant",
            failure.getError().getErrorCode());
    }
}
~~~

This test simulates a manager failure. It **does not prove** a real Token Endpoint returned an error, does not run the browser login success/failure handlers, and does not test persistence. To test token cleanup, use storage mocks/fixtures, failure handlers, or dedicated integration tests.

### 26.2. Do Not Delete Every Token When Refresh Fails

Suppose two replicas refresh token R0 concurrently:

~~~text
Node A: refreshes R0 successfully → saves R1
Node B: refreshes R0 and fails → invalid_grant
Node B: calls removeAuthorizedClient by principal?
~~~

An unconditional delete on B can wipe out R1 just saved by A. In a cluster, use coordination, re-read state under a lock, and CAS/versioned conditional removal where high reliability is required.

Never cite a simple MockMvc success handler test as proof that token refresh races are solved.

## 27. Troubleshooting by Symptom

| Symptom | Likely cause | Resolution |
|---|---|---|
| Always redirects to <code>/home</code> post-login | Handler `alwaysUseDefault` enabled or missing `SavedRequest` | Check handler config, `RequestCache`, session |
| `SavedRequest` exists yet still goes to <code>/home</code> | Different handler bean injected, different session, override priority | Check bean wiring, callback session |
| Redirects to old URL repeatedly | `SavedRequest` cleanup/matching misconfigured | Check `RequestCacheAwareFilter`, cache policy |
| Redirect drops query string | Request cache target saving or URL encoding | Inspect `saved.getRedirectUrl()` |
| Redirects to external website | Unvalidated `targetUrlParameter`/`returnTo` | Enforce allowlist, relative-path policy |
| Login succeeds yet protected route returns 403 | User lacks permissions for target | Check authorities/tenant |
| Login fails yet handler does not run | Request missed OAuth2 Login filter, wrong chain matcher | Check `SecurityFilterChain` and callback filter |
| MockMvc <code>oidcLogin()</code> passes yet redirect is wrong | Mock does not run success handler | Write handler unit + callback integration tests |
| Callback reports <code>authorization_request_not_found</code> | Lost state repository/session/cookie | Check Spring Session, browser, proxies |
| After scale-out callback works intermittently | Local session without shared store | Use shared session/affinity |
| Tab A logs in and lands on Tab B's saved URL | Single `SavedRequest` overwritten in session | Define concurrent UX/request policy |
| Picked Partner yet redirects to Company URL | Stale saved target during switch flow | Clear cache per switch policy |
| Failure handler prints raw OP error | Unsafe exception rendering | Fixed redirect, sanitized message |
| `access_denied` failures paged as critical | Expected user outcomes uncategorized | Categorize and tune alert thresholds |
| MockMvc returns 200 when unauthenticated | Security filters disabled in test | Enable real filter chain |
| Callback returns HTTP 403 | Possible CSRF/`form_post` or chain mismatch | Distinguish from state/nonce errors |
| GET logout mutates session | Logout CSRF | Require POST + CSRF |
| `SavedRequest` lost after session rotation | Custom session strategy/repository | Inspect fixation/session attributes |

### 27.1. Diagnostic Flow

~~~text
Did the user hit a protected URL before login?
    |
    +-- No → no SavedRequest; default target is expected
    |
    +-- Yes → Did the filter chain actually cache the original URL?
                  |
                  +-- No → check RequestCache, entry point, matchers
                  |
                  +-- Yes → Do authorization initiation and callback share the same session?
                               |
                               +-- No → check cookies, session store, proxies
                               |
                               +-- Yes → Did OAuth2 Login succeed?
                                            |
                                            +-- No → check state/PKCE/Token/ID Token,
                                            |         failure handler
                                            |
                                            +-- Yes → Which SuccessHandler is wired?
                                                        |
                                                        +-- SavedRequestAware?
                                                        +-- alwaysUseDefault?
                                                        +-- target parameter?
                                                        +-- stale cache?
~~~

Never fix failures by removing <code>state</code> validation or letting the browser pass arbitrary target URLs.

## 28. Logging, Metrics, and Test Isolation

### 28.1. Useful Log Fields

~~~text
event=oidc_login_success_redirect
providerAlias=company
redirectKind=saved_request
redirectRoute=/reports/{reportId}
correlationId=...

event=oidc_login_failed
providerAlias=company
category=user_denied
callbackStage=authorization_response
correlationId=...
~~~

Never log:

~~~text
authorization_code
code_verifier
real state / nonce
id_token / access_token / refresh_token
session cookie / client secret
raw error_description
~~~

### 28.2. Recommended Metrics

| Metric | Meaning |
|---|---|
| <code>oauth2_login_success_total{provider,redirect_kind}</code> | Saved/default/explicit safe target |
| <code>oauth2_login_failure_total{provider,category}</code> | Login failures by category |
| <code>saved_request_created_total{route_group}</code> | Cached requests |
| <code>saved_request_missing_total{provider}</code> | Login success with missing saved request |
| <code>saved_request_rejected_total{reason}</code> | URLs rejected by safety policy |
| <code>oauth2_callback_state_failure_total{provider}</code> | Correlation errors |
| <code>oauth2_login_redirect_latency_seconds{provider}</code> | Latency from success to redirect |

Never use raw URLs with PII queries, raw emails, session IDs, or `state` as metric labels; use bounded-cardinality route templates and categories.

### 28.3. Test Isolation

When running multiple tests:

- Create a fresh <code>MockHttpSession</code> for each independent test.
- Reset mock handlers/spies between tests when sharing contexts.
- Never use production OPs or real tokens.
- Never hardcode a JWT signing private key shared with production.
- Never rely on test method execution order.
- When using database/Redis test containers, clean up test data properly to avoid stale saved requests or authorized clients.

## 29. Self-Practice Exercises

### Exercise 1 — What Is `SavedRequest` Used For?

An unauthenticated user opens <code>/reports/quarterly</code>.

**Answer:** `RequestCache` can save the protected request so the post-login success handler redirects the user back to that exact URL. `SavedRequest` neither authenticates the user nor grants permission to view the report.

### Exercise 2 — Is `state` a `SavedRequest`?

An OAuth callback carries <code>state=S1</code>.

**Answer:** No. `state` correlates the authorization response with the original authorization request; `SavedRequest` remembers the pre-login protected URL. Never use them interchangeably.

### Exercise 3 — Does `oidcLogin()` Test the Success Handler?

~~~java
mockMvc.perform(get("/reports/quarterly")
    .with(oidcLogin()));
~~~

**Answer:** No. This test injects an authenticated OIDC principal into the request without running the OAuth2 Login callback or triggering the success handler as an authentication event.

### Exercise 4 — Does Testing `SavedRequest` Need a Real OP?

**Answer:** No. You can unit test <code>SavedRequestAwareAuthenticationSuccessHandler</code> with `MockHttpServletRequest`/Response/Session and `HttpSessionRequestCache`; callback integration tests require a valid test/stub OP.

### Exercise 5 — No Saved Request

A user navigates straight to <code>/login</code> and signs in successfully.

**Answer:** The success handler uses the default target <code>/home</code> if no other override applies.

### Exercise 6 — Always Use Default

<code>alwaysUseDefaultTargetUrl=true</code> while the session holds saved target <code>/reports/a</code>.

**Answer:** The handler prefers the default target and does not resume the saved target. Tests must match product intent.

### Exercise 7 — Open Redirect

The frontend passes <code>next=https://attacker.example</code> to the success handler.

**Answer:** Never redirect to that URL without allowlist/validation. Prefer saved requests from protected routes and internal fallbacks.

### Exercise 8 — User Clicks Deny

The OP returns <code>error=access_denied</code>.

**Answer:** Authentication fails; the failure handler renders a safe login error page without logging raw descriptions or creating an `Authentication`.

### Exercise 9 — Login Fails While `SavedRequest` Remains

**Answer:** Retaining or clearing depends on retry UX and policy. Test explicitly; sensitive account switches may require clearing stale targets.

### Exercise 10 — Two Tabs

Tab A requests `/reports/a`, Tab B requests `/reports/b` in the same session.

**Answer:** The default `RequestCache` may not keep separate targets per tab; test concurrency/UX policy, and never drop OAuth `state` validation.

### Exercise 11 — Multi-Instance

Protected GET hits A, callback hits B; success handler sends user to `/home` instead of `/reports`.

**Answer:** Inspect session/cookie/shared `RequestCache` state, handler wiring, and session repository. Never assume two nodes share local `HttpSession` state automatically.

### Exercise 12 — Redirect Succeeds, Yet Report Returns 403

**Answer:** This can be the right behavior: the newly logged-in principal lacks permission for the report. Success redirects never bypass protected-route authorization.

### Exercise 13 — Callback `state` Mismatch

Callback code/state does not match the original request.

**Answer:** Reject authentication. Never invoke the success handler to "keep UX flowing" or skip `state` validation.

### Exercise 14 — Protected POST

An unauthenticated user submits a state-changing POST and gets redirected to login.

**Answer:** Never blindly replay raw POSTs post-login. Use a review/confirm page, fresh CSRF/idempotency, and fresh authorization.

### Exercise 15 — Direct Handler Test vs. Filter Integration

**Question:** Why does calling <code>handler.onAuthenticationSuccess()</code> directly not prove the OIDC callback works?

**Answer:** It skips `OAuth2LoginAuthenticationFilter`, Token Endpoint, ID Token validation, and session strategy; it only tests the handler's own logic.

### Exercise 16 — Failure Handler and Session Exception

**Question:** If `SimpleUrlAuthenticationFailureHandler` stores `AuthenticationException` in the session, is it safe for the view to print <code>exception.message</code> directly?

**Answer:** No. The message may contain upstream data. Only display mapped/sanitized messages; never expose raw `OAuth2Error` descriptions.

### Exercise 17 — MockMvc Missing Filters

<code>@AutoConfigureMockMvc(addFilters=false)</code> causes protected URLs to return 200.

**Answer:** The test no longer verifies Spring Security's `RequestCache`/entry point. Enable filters and test unauthenticated requests.

### Exercise 18 — Testing Session Rotation

**Task:** Design an integration test verifying the session ID follows the session-fixation strategy while `SavedRequest` still works post-login.

**Hint:** Hit a protected URL, retain the browser session, execute a valid OAuth2 callback against a test OP, observe session/redirect and the post-login request; never copy a session ID from another account.

### Exercise 19 — Comprehensive Testing

Build a Spring Boot Servlet app with:

1. OIDC `ClientRegistration` <code>company</code>.
2. Protected route <code>/reports/{reportId}</code>.
3. Custom login page <code>/login</code>.
4. <code>HttpSessionRequestCache</code> configured as a bean.
5. <code>SavedRequestAwareAuthenticationSuccessHandler</code> defaulting to <code>/home</code>.
6. Failure handler that does not reflect <code>error_description</code>.
7. Unit tests for saved request, no saved request, always-use-default, and failure redirect.
8. MockMvc test verifying unauthenticated routes are cached.
9. <code>oidcLogin()</code> test for controller authorization, noting it does not run callbacks.
10. OP stub integration tests for valid callbacks and error callbacks.
11. Tests for multiple tabs, multiple providers, account switching, and multiple instances.
12. Tests for original URLs with queries and rejecting off-domain `returnTo` values.
13. Tests confirming protected routes post-redirect still enforce role/tenant checks.
14. Logs/metrics free of tokens, codes, `state`, or session cookies.

Explain why **unit-testing the handler + testing `RequestCache` + testing real callbacks** form three complementary layers.

## 30. Summary

- **SavedRequest** records the pre-login protected URL; **OAuth2AuthorizationRequest** holds OAuth2 state/nonce/PKCE correlation data; **SecurityContext** holds authentication state.
- **<code>HttpSessionRequestCache</code>** saves/retrieves requests; **<code>SavedRequestAwareAuthenticationSuccessHandler</code>** picks the redirect target after success.
- The success handler can prioritize `SavedRequest`, default URL, always-use-default, or a target parameter per configuration; test every branch.
- The failure handler must handle OAuth2/OIDC Login errors safely without leaking raw OP descriptions, tokens, or untrusted error URIs.
- **<code>oidcLogin()</code>/<code>oauth2Login()</code> in MockMvc simulate an authenticated principal on a request** without triggering success/failure handlers or code exchange.
- Handler unit tests can use <code>MockHttpServletRequest</code>, <code>MockHttpServletResponse</code>, <code>MockHttpSession</code>, and <code>HttpSessionRequestCache</code> without an OP.
- MockMvc with security filters enabled verifies unauthenticated protected URLs are cached before login.
- Real callback integration tests require saved authorization request/`state`, test Token Endpoint/JWKS, and valid ID Token validation; never bypass OAuth2 `state` or OIDC validation just to make tests easier.
- Redirecting to `SavedRequest` **does not grant permissions**: protected routes post-login must still authorize the new principal.
- `SavedRequest` should never replay side-effecting POSTs; require CSRF, idempotency, and fresh confirmation.
- Guard against open redirects, stale saved URLs after account switches, multi-tab conflicts, and lost session state across replicas.
- Session fixation, Spring Session/Redis, cookies/`SameSite`, and multiple `SecurityFilterChain`s all affect whether handlers find saved requests; never drop security validations to work around session bugs.
- Logs/metrics should record provider alias, redirect category, failure category, and correlation ID; never log raw OAuth2 credentials or sensitive URLs.

### References

- **Spring Security Reference — Servlet OAuth2 Login:** authorization initiation, callback, success/failure handlers, and login flow.
- **Spring Security Reference — Servlet Authentication:** <code>AuthenticationSuccessHandler</code>, <code>AuthenticationFailureHandler</code>, <code>SimpleUrlAuthenticationFailureHandler</code>.
- **Spring Security Java API — SavedRequestAwareAuthenticationSuccessHandler:** default target, target parameter, `SavedRequest`, and `RequestCache` precedence.
- **Spring Security Java API — HttpSessionRequestCache / DefaultSavedRequest:** saving/getting/matching/removing requests and redirect URLs.
- **Spring Security Reference — Servlet RequestCache:** <code>ExceptionTranslationFilter</code>, <code>RequestCacheAwareFilter</code>, saved request behavior.
- **Spring Security Reference — Spring Security Test (MockMvc):** <code>oauth2Login()</code>, <code>oidcLogin()</code>, <code>MockMvc</code> request post-processors.
- **Spring Session Reference — Redis HTTP Session:** sharing session attributes and distributed session store behavior.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Flow, `state`, and error responses.
- **RFC 7636 — Proof Key for Code Exchange:** PKCE and authorization code binding.
- **OpenID Connect Core 1.0:** ID Token validation, `nonce`, issuer, audience, and OIDC Login.
- **OWASP Authentication Cheat Sheet / Session Management Cheat Sheet:** redirect safety, session lifecycle, and session fixation.
- **OWASP Unvalidated Redirects and Forwards Cheat Sheet:** validating redirect targets and preventing open redirects.
