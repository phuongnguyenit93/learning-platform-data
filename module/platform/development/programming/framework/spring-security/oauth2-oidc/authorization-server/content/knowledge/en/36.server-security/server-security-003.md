# Per-Endpoint CSRF and Protecting User-Driven Actions

> **Chapter: Server Security.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, focusing on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. The goal is to classify endpoints by credential source, keep CSRF enabled for user browser actions, and exempt only endpoints that have appropriate independent authentication mechanisms.

## 1. What Is CSRF and Why Should an Authorization Server Care?

Cross-Site Request Forgery (CSRF) is an attack that exploits the fact that browsers automatically attach user credentials to requests sent to a website. If a user is logged into `https://login.example.vn`, the browser can automatically include the session cookie when a malicious page causes the browser to send a request to that domain.

For example, suppose a user has an active login session at the Authorization Server. An attacker creates a hidden form:

~~~html
<form action="https://login.example.vn/account/change-email" method="post">
    <input name="email" value="attacker@example.net">
</form>
<script>
    document.forms[0].submit();
</script>
~~~

If the endpoint relies solely on the session cookie to identify the user and does not validate a CSRF token, the browser may send the request with a valid cookie. The server sees a real authenticated session and may perform a change the user never intended.

In an Authorization Server, affected actions can include:

- Changing password, email, phone number, MFA, or account details.
- Creating, modifying, or deleting client registrations or redirect URIs.
- Approving consent, modifying permissions, or changing memberships.
- Revoking sessions, credentials, or authorizations.
- User and tenant administrative actions.
- Browser login/logout if endpoints lack proper protection.

CSRF differs from XSS. CSRF tricks the browser into sending an unintended request using automatically attached credentials; XSS allows malicious scripts to execute inside a trusted origin and read or use CSRF tokens. A CSRF token does not replace output encoding, CSP, or XSS prevention.

## 2. Identifying Endpoints at Risk of CSRF

The key question is: **does the browser automatically send credentials that the endpoint uses to authenticate the request?**

| Authentication mechanism | Does the browser auto-send credentials? | CSRF risk |
|---|---|---|
| Session cookie | Yes | High if the endpoint changes state |
| Cookie containing JWT/session state | Yes | Still present |
| HTTP Basic cached and auto-sent by browser | Potentially yes | Present |
| Bearer token explicitly attached by client in `Authorization` header | Typically no | Lower against traditional CSRF |
| Client authentication at back-channel token endpoint | Does not rely on browser session | Typically does not need a browser CSRF token |
| HMAC/mTLS for webhooks | Does not rely on browser session | Uses dedicated signatures and replay protection |
| API authenticating via cookies | Yes | Still requires CSRF, even for JSON APIs |

You cannot conclude an API is safe merely because it returns JSON, uses HTTPS, or is called via JavaScript. Browsers can still send cross-site forms, simple-content-type requests, or automatically attach cookies.

`SessionCreationPolicy.STATELESS` does not automatically eliminate CSRF either. A stateless application that authenticates using cookies is still vulnerable to CSRF because the browser sends that cookie automatically.

## 3. Principles for Classifying Endpoints

Before configuring `ignoringRequestMatchers`, list all endpoints and determine their credential source, action, and protection mechanism.

| Endpoint group | Example | Appropriate protection |
|---|---|---|
| Login and account forms | `/login`, `/account/email`, `/account/mfa` | Spring Security CSRF token |
| Administrative actions | `/admin/clients`, `/admin/users` | CSRF + authorization + re-authentication when sensitive |
| In-app consent forms | `/consent`, `/device/approve` | Application CSRF token or protocol state token |
| OAuth authorization endpoint | `/oauth2/authorize` | Authorization Server CSRF rules and consent protocol |
| Token/introspection/revocation | `/oauth2/token`, `/oauth2/introspect`, `/oauth2/revoke` | Client authentication, grant/token validation |
| PAR/device authorization | `/oauth2/par`, `/oauth2/device_authorization` | Client authentication and protocol validation |
| UserInfo | `/userinfo` | Bearer access token and scope |
| Webhook | `/integrations/provider/webhook` | HMAC/mTLS signature, timestamp, and replay prevention |
| Discovery/JWKS | `/.well-known/openid-configuration`, `/oauth2/jwks` | Read-only GET, does not mutate state |

Do not lump all of `/api/**`, `/oauth2/**`, or every POST request into a single exemption just because one endpoint does not use a CSRF token.

## 4. How Does Spring Security Handle CSRF by Default?

On the Servlet stack, Spring Security enables CSRF protection by default. `CsrfFilter` skips safe HTTP methods by default:

- `GET`
- `HEAD`
- `TRACE`
- `OPTIONS`

All other methods such as `POST`, `PUT`, `PATCH`, and `DELETE` require a valid token unless the request matches a configured exclusion.

By default, CSRF tokens are stored in `HttpSession` using `HttpSessionCsrfTokenRepository`. The server generates the token and compares it against the token submitted by the client in a form parameter or request header.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"GET / HEAD / TRACE / OPTIONS?"}
    B -->|Yes| C["No CSRF token required"]
    B -->|No| D{"Matches an excluded matcher?"}
    D -->|Yes| E["Skip CsrfFilter for this request"]
    D -->|No| F["Read token from session and request"]
    F --> G{"Token valid?"}
    G -->|Yes| H["Proceed to authorization and controller"]
    G -->|No| I["403 Access Denied"]
~~~

The fact that safe methods do not require a token does not mean a GET endpoint is allowed to mutate data. If `GET /account/delete` deletes an account or `GET /logout` terminates a session, the endpoint violates HTTP semantics and can be triggered via links, images, or navigations.

**Rule:** GET only reads data or renders pages. Every state-changing operation must use an unsafe method with matching protection.

## 5. Narrow CSRF Configuration in the Application SecurityFilterChain

The example below preserves CSRF for user browser actions and exempts only a webhook with independent signature verification.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    RequestMatcher signedPaymentWebhook = request ->
            "POST".equals(request.getMethod())
                    && "/integrations/payments/webhook"
                            .equals(request.getServletPath());

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .csrf(csrf -> csrf
            .csrfTokenRepository(new HttpSessionCsrfTokenRepository())
            .ignoringRequestMatchers(signedPaymentWebhook))
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults());

    return http.build();
}
~~~

`RequestMatcher` matches only `POST /integrations/payments/webhook`. Other requests, including POSTs to other endpoints under `/integrations`, still require a CSRF token if they use a browser session.

This code only defines the CSRF exemption. The webhook controller/filter must still verify the HMAC or mTLS signature, timestamp, raw request body, and replay/idempotency key before executing business logic. Never accept a webhook simply because the request carries an `X-Signature` header.

If the application has a context path or custom servlet mapping, check the actual `getServletPath()` and write tests for the matcher. A misconfigured path matcher can accidentally widen the exempted area.

### 5.1. Never Disable CSRF Across the Entire Application Chain

Never use the following configuration just to get one API or webhook working:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

This configuration strips protection from login forms, logout, account management, the admin console, and every other form in that chain. If an endpoint does not use browser credentials, create a narrow exemption for that endpoint or place it in a separate `SecurityFilterChain` with an explicit authentication model.

## 6. Separating Filter Chains by Application Type

A system may contain Authorization Server protocol endpoints, a browser application, a Resource Server API, and webhooks. You can separate filter chains so policies are easier to verify.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserApplicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

    return http.build();
}
~~~

The first chain handles Spring Authorization Server protocol endpoints. The second chain handles browser login and user-facing business operations. In the browser chain, CSRF remains enabled by default.

Spring Authorization Server 1.4.x/1.5.x automatically configures `csrf.ignoringRequestMatchers(endpointsMatcher)` inside `OAuth2AuthorizationServerConfigurer`. That means protocol endpoints are excluded from Spring Security's standard `CsrfFilter`. Do not interpret this as meaning the entire system needs no CSRF; protocol endpoints must rely on their respective OAuth/OIDC protections, while business forms outside the matcher must remain protected.

Never add `csrf.disable()` to the browser chain. If you change filter chain ordering or matchers, verify which chain actually handles each request using integration tests and security debug logs.

## 7. Protecting HTML Forms and Account Actions

For HTML forms, submit the CSRF token in a hidden input. Thymeleaf/Spring MVC exposes `CsrfToken` via the `_csrf` request attribute.

~~~html
<form method="post" action="/account/email">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <label for="email">New email</label>
    <input id="email" name="email" type="email" required>

    <button type="submit">Update email</button>
</form>
~~~

With Thymeleaf, you can use `th:name` and `th:value` to render the parameter name and token. Never put CSRF tokens in URLs, query strings, logs, or analytics because those locations can leak into browser history, proxy logs, and `Referer` headers.

Actions that must be protected include:

- Changing email/phone number, password, or profile details.
- Enabling/disabling MFA, registering passkeys, or rotating recovery codes.
- Creating or revoking API keys, refresh tokens, sessions, and trusted devices.
- Changing permissions, memberships, roles, or tenants.
- Creating/modifying/deleting OAuth clients, redirect URIs, and secrets.
- Approving or revoking consent.

A CSRF token proves the request carries a token matching the session; it does not replace authorization. The server must still verify that the user is authorized to perform that action on that specific account/client/tenant.

### 7.1. Login and Logout Also Require Protection

Spring Security protects login requests to prevent login CSRF, such as an attacker forcing a victim's browser to log into an attacker-controlled account. When the victim continues using the browser, private data could be recorded under the attacker's account.

Logout should also use POST with a CSRF token. Spring Security's `LogoutFilter` handles logout via POST by default when CSRF is enabled. Never turn logout into a GET just to provide a convenient link.

## 8. CSRF Tokens for JavaScript and SPAs

JavaScript applications can send the CSRF token in a request header instead of a form parameter. One option is `CookieCsrfTokenRepository`, commonly using the `XSRF-TOKEN` cookie and the `X-XSRF-TOKEN` header.

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

`HttpOnly=false` allows JavaScript to read the cookie to extract the token and attach it to the header. Use this option only when the frontend truly needs to read the token; keep the authentication session cookie `HttpOnly`.

Example request:

~~~javascript
const csrfToken = readCookie("XSRF-TOKEN");

await fetch("/account/email", {
    method: "POST",
    credentials: "same-origin",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ email: "new@example.vn" })
});
~~~

With recent Spring Security versions supporting the SPA CSRF handler, `csrf.spa()` can be used to apply the required handling for deferred tokens and BREACH protection. Match the exact Spring Security version used in your application. After authentication success and logout success, the old CSRF token may be cleared; the SPA must obtain a fresh token before the next state-changing request.

Never read the CSRF token from a cookie and send it as an authentication credential. The CSRF token is only one part of request verification; the session cookie must still be protected separately.

## 9. API Endpoints and Webhooks: When Can CSRF Be Exempted?

### 9.1. Bearer-Only Resource Server APIs

A request carrying an access token in an `Authorization: Bearer ...` header is generally not automatically attached by the browser like a session cookie. Spring Security Resource Server also automatically configures CSRF to ignore requests matching the Bearer token request matcher.

~~~java
@Bean
@Order(1)
SecurityFilterChain resourceApiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

This is a chain for APIs authenticating via Bearer tokens in headers. Do not add cookie-based authentication or HTTP Basic to the same API without re-evaluating CSRF. If the browser sends a session cookie to authenticate API calls, that endpoint remains vulnerable to CSRF even if the response is JSON.

Spring Security's `OAuth2ResourceServerConfigurer` uses a matcher for requests containing a Bearer token to bypass CSRF for those requests. The matcher is not a blanket exemption for `/api/**`: requests without a Bearer header must still go through the chain's authentication and CSRF policy.

Do not use `STATELESS` as sole proof that CSRF is unnecessary. A self-contained JWT stored in a cookie is still an ambient credential and can still be automatically sent by the browser.

### 9.2. Webhooks from External Systems

A webhook can be exempted from CSRF when it does not rely on a browser session and uses independent authentication:

- HMAC over the raw request body with a provider-specific secret.
- mTLS or asymmetric signatures when supported by the provider.
- Time-bounded timestamps and replay protection.
- Idempotency keys to handle duplicate deliveries.
- Body size limits, rate limits, and schema validation.
- Constant-time signature comparison when implementing HMAC verification manually.

Never allow a webhook request to mutate business state solely because it arrives from a purported provider IP. An IP allowlist can be an extra layer, never a replacement for signatures or mTLS.

### 9.3. CORS Does Not Replace CSRF

CORS determines which origins' JavaScript may read responses or perform certain cross-origin requests. CORS does not automatically block all form POSTs or navigation requests a browser can send.

An API with CORS enabled is still vulnerable to CSRF if it authenticates via cookies. Conversely, an API accepting only Bearer headers and no ambient credentials has a different CSRF model than a browser-session application.

## 10. CSRF in Spring Authorization Server Protocol Endpoints

Do not apply a single CSRF rule to all OAuth2/OIDC endpoints. Distinguish back-channel protocol calls from user browser interactions.

| Endpoint | Primary authentication/protection | How to evaluate CSRF |
|---|---|---|
| `/oauth2/authorize` | Authorization request validation, user authentication, and consent | GET is protocol navigation; consent POST uses SAS state token |
| `/oauth2/token` | Client authentication/identification by client type, authorization code/PKCE/refresh grant validation | Back-channel endpoint; does not rely on browser session cookie |
| `/oauth2/par` | Client identification/authentication by client type and pushed request validation | Back-channel; validates client and request parameters |
| `/oauth2/device_authorization` | Client identification/authentication per registration and device grant validation | Back-channel; not a user interaction form |
| `/oauth2/device_verification` | User code, authenticated resource owner, and consent | User interaction; consent flow uses SAS state token |
| `/oauth2/introspect` | Client authentication and token validation | Back-channel endpoint |
| `/oauth2/revoke` | Client authentication and token validation | Back-channel endpoint |
| `/userinfo` | Bearer access token | Header token; does not rely on session cookie |
| Discovery/JWKS | GET metadata/key set | Read-only endpoint |
| OIDC logout | `id_token_hint`, client, and post-logout redirect validation | RP-initiated browser navigation; evaluate logout CSRF separately |

### 10.1. Three Types of State/Tokens Not to Confuse

Three values can appear simultaneously in an Authorization Server application:

| Value | Who creates it | Purpose |
|---|---|---|
| OAuth `state` in authorization request | OAuth client | Binds the authorization response to the client's request; protects the client from response injection/CSRF |
| Consent `state` in SAS custom consent page | Spring Authorization Server | Protects the consent transaction; the form must submit `state` back on POST |
| Spring `_csrf` token | Spring Security application | Protects browser forms/requests using the application's session cookie |

An OAuth client `state` does not replace the CSRF token on admin forms. Nor does Spring `_csrf` replace the `state` required by Spring Authorization Server in the consent protocol.

### 10.2. Authorization Server Consent Page

Spring Authorization Server 1.5.8 supports configuring `authorizationEndpoint(...).consentPage(...)`. The custom consent page query string contains `client_id`, `scope`, and `state`. The API documentation defines `state` as the CSRF protection token for the consent flow.

The consent form must:

1. Use HTTP POST.
2. Submit to `AuthorizationServerSettings.getAuthorizationEndpoint()`.
3. Return the received `client_id`.
4. Return the received `state`.
5. Submit the scopes actually approved by the resource owner.

~~~html
<form method="post" th:action="${authorizationEndpoint}">
    <input type="hidden" name="client_id" th:value="${clientId}">
    <input type="hidden" name="state" th:value="${state}">

    <label th:each="scope : ${requestedScopes}">
        <input type="checkbox"
               name="scope"
               th:value="${scope.name}">
        <span th:text="${scope.description}"></span>
    </label>

    <button type="submit">Approve</button>
</form>
~~~

In the standard configuration, `OAuth2AuthorizationServerConfigurer` excludes the Authorization Server endpoint matcher from `CsrfFilter`. Therefore, SAS's consent `state` is a critical part of the protocol. Never omit `state`, never accept arbitrary `client_id` or scopes from the browser, and never generate authorization codes manually in a controller.

RFC 6749 §10.12 requires Authorization Servers to protect the authorization endpoint so a malicious client cannot obtain a resource owner's authorization without the user's awareness and explicit consent. OAuth client `state` primarily binds responses on the client side; it does not replace consent/interaction protection on the Authorization Server side. For third-party clients or sensitive scopes, enforce a consent policy ensuring user awareness and explicit approval; never skip consent automatically just because the request has a valid session cookie.

If your organization wants to add an application-level synchronizer token layer on top of consent interaction, design a dedicated integration with the filter/protocol flow and test both layers; merely adding `csrf.requireCsrfProtectionMatcher(...)` will not automatically reinstate requests already excluded by the endpoint matcher.

### 10.3. Device Authorization and Device Verification

Device Verification is a user-interactive endpoint: the user enters `user_code`, views the client name and scopes, and approves or denies. For a custom device consent page, Spring Authorization Server 1.5.8 provides `client_id`, `scope`, `state`, and `user_code`; the form must POST to `AuthorizationServerSettings.getDeviceVerificationEndpoint()` and return the required protocol values.

Do not auto-approve solely because `user_code` is valid. Clearly display the application/device requesting access, verify the user is authenticated, require explicit consent, and preserve the SAS `state`. If building a separate user-code entry page or interaction route, use a session-bound one-time interaction token bound to the current user code/session; never use a hidden `tenant_id` or `user_code` alone as CSRF proof.

### 10.4. OIDC Logout and Logout CSRF

Logout in a browser application should be a POST protected by Spring CSRF. OIDC RP-Initiated Logout is a protocol navigation to the end-session endpoint; the server must validate `id_token_hint`, client registration, and `post_logout_redirect_uri` per protocol.

An unintended logout request typically causes session termination/availability impact rather than data modification, yet it still belongs in the threat model. For sensitive logout actions or local account security, display a confirmation page and require explicit user action. `state` in RP-Initiated Logout correlates the post-logout response; do not confuse it with Spring `_csrf`.

## 11. Protecting High-Risk User Actions

A CSRF token only proves a request carries a token matching the session. It does not verify user permissions, prove intent for every action, or replace re-authentication.

| Action | Combined controls needed |
|---|---|
| Change email/phone number | CSRF + verify new address + security notification |
| Change password | CSRF + verify current password or step-up authentication |
| Enable/disable MFA, add passkey | CSRF + current re-authentication/MFA + confirmation |
| Create client or change redirect URI | CSRF + admin privileges + audit + policy approval |
| Grant admin role or change tenant membership | CSRF + strict authorization + step-up + audit |
| Revoke all sessions/tokens | CSRF + impact confirmation + audit |
| Rotate signing key or client secret | CSRF + privileged role + re-authentication + governance workflow |

Endpoints can be organized by resource and method:

~~~text
POST   /account/email
POST   /account/password
POST   /account/mfa/enroll
DELETE /account/mfa/{credentialId}
POST   /admin/clients
PATCH  /admin/clients/{clientId}
DELETE /admin/clients/{clientId}
POST   /admin/users/{userId}/roles
POST   /admin/sessions/revoke
~~~

Every mutating action must pass through authorization policy and CSRF validation if it uses a browser session. Never use GET to delete credentials, approve consent, change permissions, or revoke sessions.

## 12. Defense in Depth: SameSite, Origin, and Fetch Metadata

CSRF tokens are the primary protection for stateful browser applications. The following layers can be added:

### 12.1. SameSite Cookies

`SameSite=Lax` or `Strict` helps restrict browsers from sending cookies on cross-site requests. However:

- `Lax` still sends cookies on certain top-level safe navigations.
- Subdomains sharing the same registrable domain may be treated as same-site.
- State-changing GETs can still be triggered.
- Behavior varies across browsers and embedded user-agents.

Thus, `SameSite` is defense in depth, not a replacement for synchronizer tokens in session-based applications.

### 12.2. Origin/Referer Checks

For state-changing requests, the server can validate `Origin` and fallback `Referer` against the configured public origin. If the application sits behind a reverse proxy, trust forwarded headers only from authenticated proxies; the proxy must strip client-sent headers and emit canonical headers.

Never allow `Origin: null`, never use substring checks like `endsWith("example.vn")`, and never auto-accept requests missing both `Origin` and `Referer` unless a valid CSRF token or an explicitly designed fallback is present.

### 12.3. Fetch Metadata

The `Sec-Fetch-Site` header helps detect cross-site requests. For state-changing operations, you can reject `cross-site` and apply a fallback for browsers that do not send Fetch Metadata. Do not treat `same-site` as safe if your system hosts untrusted subdomains or tenant content.

### 12.4. Measures That Do Not Replace CSRF Tokens

- CORS does not block all form/navigation requests.
- HTTPS does not stop browsers from sending cookies on attacker-initiated requests.
- CAPTCHA does not bind requests to a session.
- Idempotency keys prevent duplicate processing, not forged request origins.
- Re-authentication/MFA increases assurance but does not replace form CSRF checks.

## 13. Per-Endpoint CSRF Test Matrix

| # | Scenario | Expected result |
|---|---|---|
| 1 | POST `/account/email` with session but missing CSRF token | 403 |
| 2 | POST `/account/email` with valid token | Passes to authorization/business validation |
| 3 | POST `/account/email` with invalid token | 403 |
| 4 | PUT/PATCH/DELETE account mutation missing token | 403 |
| 5 | GET `/account/email` used to modify data | No state change; endpoint design flagged as defect |
| 6 | Login form POST missing token | Rejected |
| 7 | Logout POST missing token | Rejected |
| 8 | Logout POST with valid token | Terminates local session |
| 9 | Admin modifying redirect URI missing token | 403 |
| 10 | Admin with token but lacking role | 403 from authorization layer |
| 11 | Webhook matching path, wrong HTTP method | Not exempted from CSRF |
| 12 | Webhook matching path/method but wrong signature | Rejected by signature validation |
| 13 | Webhook with valid signature but expired timestamp | Rejected by replay/time validation |
| 14 | POST `/integrations/other` | Still requires CSRF token |
| 15 | Bearer-only API with valid `Authorization` header | Authenticated per JWT/resource policy |
| 16 | API using cookie session instead of Bearer token | CSRF must still be enforced |
| 17 | Cross-site JSON request using `text/plain` | Not treated as safe just because it is a JSON API |
| 18 | Consent POST missing SAS `state` | Rejected by Authorization Server |
| 19 | Consent POST tampering with `client_id` | Does not grant consent to wrong client |
| 20 | Consent POST submitting scope outside requested scopes | Does not grant scopes outside request/policy |
| 21 | Consent POST to different issuer/tenant endpoint | Does not complete authorization transaction |
| 22 | Already-used or expired consent `state` | Transaction rejected |
| 23 | Invalid `user_code` in device verification | Device not authorized |
| 24 | Device consent missing `state` | Device authorization not approved |
| 25 | Device consent relying only on `user_code`, no user approval | Must not auto-approve |
| 26 | RP-Initiated Logout with invalid `id_token_hint` | Rejected or handled per OIDC error policy |
| 27 | Unregistered `post_logout_redirect_uri` | Does not redirect to that URI |
| 28 | Browser sends `Origin` different from configured origin | Sensitive request rejected |
| 29 | Request with `Origin: null` | Not automatically accepted |
| 30 | Request missing both `Origin`/`Referer` and CSRF token | Rejected |
| 31 | Request with `Sec-Fetch-Site: cross-site` to mutating endpoint | Blocked per policy |
| 32 | Same-origin request with valid CSRF token | Allowed to proceed |
| 33 | Expired session while form retains old token | CSRF validation fails; UI prompts reload/fresh token |
| 34 | Post-login SPA sends stale CSRF token | Client must fetch fresh token |
| 35 | Post-logout SPA sends stale CSRF token | Client must fetch fresh token |
| 36 | Two tabs using valid session tokens | Both flows work per token/session policy |
| 37 | Stateless API chain receives request without Bearer header | Not treated as authenticated |
| 38 | Request from sibling subdomain on same site | Still subject to token/origin policy |
| 39 | CSRF matcher ignores `/integrations/**` | Test catches overly broad exemption |
| 40 | CSRF disabled on entire application chain | Security configuration review must fail |

### 13.1. Example Test with MockMvc

Spring Security Test provides the `csrf()` request post-processor to test `CsrfFilter` behavior.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void accountMutationRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/account/email")
            .with(user("alice"))
            .param("email", "new@example.vn"))
        .andExpect(status().isForbidden());
}

@Test
void accountMutationAcceptsValidCsrfToken() throws Exception {
    mockMvc.perform(post("/account/email")
            .with(user("alice"))
            .with(csrf())
            .param("email", "new@example.vn"))
        .andExpect(status().is3xxRedirection());
}
~~~

The second test assumes the user is authorized and the controller redirects on success. If business validation or authorization policy differs, adjust the expected response while still proving that requests with a valid token pass through the CSRF layer.

You can use `csrf().useInvalidToken()` to test invalid tokens and `csrf().asHeader()` to test header-based tokens. For webhooks and Spring Authorization Server protocol endpoints, write integration tests that verify real signatures, client authentication, and protocol state; MockMvc's `csrf()` does not substitute for those checks.

## 14. Troubleshooting and Production Checklist

| Symptom | Possible cause | Resolution |
|---|---|---|
| Form POST returns 403 | Missing `_csrf` or token does not match session | Render hidden input and inspect session |
| SPA POST returns 403 after login | Old CSRF token cleared after authentication | Fetch fresh token after login |
| Webhook returns 403 from `CsrfFilter` | Matcher wrong path/method or request entered another chain | Check `servletPath`, chain order, and matcher |
| Webhook processed despite bad signature | Exempted CSRF but forgot signature validation | Verify HMAC/mTLS and replay protection |
| Bearer API request gets 403 CSRF | Request didn't match bearer matcher or uses cookie auth | Check `Authorization` header and auth model |
| Cookie-session API vulnerable to CSRF | Confused JSON API with bearer-only API | Enable CSRF for cookie-authenticated requests |
| Consent page returns 403 | Missing or lost SAS `state` | Preserve `client_id`/`state`/`scopes` and POST to right endpoint |
| Device consent rejected | Missing `user_code`/`state` or wrong verification flow | Check SAS form contract |
| Changed `csrf.disable()` yet still 403 in SAS | Configurer adds endpoint matcher to CSRF ignore during lifecycle | Check exact filter chain and SAS version |
| GET modifies state | Endpoint violates safe method semantics | Move mutation to POST/PUT/PATCH/DELETE |
| Origin check fails behind reverse proxy | Target origin derived from untrusted forwarded header | Configure trusted proxy and canonical origin |

### 14.1. Production Checklist

- [ ] Classify endpoints by credential source and interaction type.
- [ ] CSRF is enabled for browser applications and user-facing forms.
- [ ] Never use GET for state-changing operations.
- [ ] Never disable CSRF globally to fix one endpoint.
- [ ] Every `ignoringRequestMatchers` exemption has specific method/path and independent authentication.
- [ ] Webhooks verify HMAC/mTLS, timestamp, and replay protection.
- [ ] Bearer-only APIs do not accept cookie auth outside design.
- [ ] APIs using cookies/sessions keep CSRF protection enabled.
- [ ] Login, logout, account, admin, and consent forms are tested.
- [ ] SAS consent form preserves `client_id`, `state`, and the approved subset of scopes.
- [ ] Device verification requires explicit user approval and preserves protocol state.
- [ ] RP-Initiated Logout validates ID Token hint and post-logout redirect URI.
- [ ] `SameSite`, `Origin`/`Referer`, and Fetch Metadata are used only as defense in depth.
- [ ] Forwarded headers are trusted only from authenticated proxies.
- [ ] CSRF tokens never appear in URLs, logs, or analytics.
- [ ] SPA refreshes CSRF token after authentication/logout per framework behavior.
- [ ] High-risk operations enforce authorization, re-authentication/MFA, and auditing.
- [ ] Negative tests exist for every CSRF-exempted endpoint.
- [ ] Review filter chain order and matchers after every Spring Security/SAS upgrade.

**Self-Assessment Questions**

1. Why is `SessionCreationPolicy.STATELESS` insufficient to conclude an API does not need CSRF?
2. What is the difference between a synchronizer token, OAuth client `state`, and SAS consent `state`?
3. Why does a login form also require CSRF protection?
4. Why should logout use POST instead of GET?
5. When can a webhook be exempted from CSRF?
6. Why can a JSON API still be vulnerable to CSRF?
7. How should `ignoringRequestMatchers` be designed with respect to path and method?
8. Why should you not exempt all of `/api/**` from CSRF?
9. Which parameters does a Spring Authorization Server 1.5.8 custom consent page receive?
10. Which protocol values must a device verification consent page preserve?
11. Why does CORS not replace CSRF tokens?
12. What limitations does `SameSite` have with subdomains and top-level navigations?
13. When running behind a reverse proxy, what configuration does `Origin` validation require?
14. Why does a CSRF token not replace authorization or re-authentication?
15. Which negative test cases must be verified before exempting an endpoint from CSRF?

## References

- [Spring Security — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): default method matcher, token repositories, HTML forms, SPAs, and endpoint exclusions.
- [Spring Security — CSRF Considerations](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): when CSRF is needed, stateless cookie authentication, and CORS/JSON limitations.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization endpoint, consent form, state, and protocol endpoint extension points.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): custom consent page and form POST contract.
- [Spring Authorization Server 1.5.8 — OAuth2DeviceVerificationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2DeviceVerificationEndpointConfigurer.html): `user_code`, consent state, and device verification form contract.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): protocol endpoints, endpoint matcher, and Authorization Server configuration.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerConfigurer source](https://github.com/spring-projects/spring-authorization-server/blob/1.5.8/oauth2-authorization-server/src/main/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationServerConfigurer.java): configuration lifecycle of endpoint matcher and protocol chain CSRF exclusions.
- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 10.12](https://www.rfc-editor.org/rfc/rfc6749.html#section-10.12): CSRF threats and authorization endpoint protection requirements.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer tokens, `SameSite`, `Origin`/`Referer`, and Fetch Metadata.
