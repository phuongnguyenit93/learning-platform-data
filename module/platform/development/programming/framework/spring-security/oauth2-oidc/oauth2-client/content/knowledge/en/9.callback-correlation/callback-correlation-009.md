# 9.9. Duplicate Callbacks, Spent Codes, and Replay Protection Boundaries

## Objectives

In **Spring Security OAuth 2.0 / OIDC Client**, the callback is where the application receives the response from the Authorization Server (AS) or OpenID Provider (OP). With the **Authorization Code flow**, the callback typically carries `code` and `state`. This is data belonging to a specific authorization transaction, not a URL that can be reprocessed arbitrarily.

After this lesson, you will be able to:

- Distinguish valid callbacks from duplicate callbacks caused by refreshes, retries, two tabs, expired sessions, and replay attempts.
- Explain why **authorization codes must be short-lived and single-use**.
- Distinguish the anti-replay/correlation roles of `state`, `nonce`, and PKCE.
- Describe how Spring Security Servlet saves the Authorization Request before the callback, then retrieves and removes that state upon receiving the callback.
- Analyze `invalid_grant`, missing original requests, mismatched states, and race conditions.
- Design safe recovery behavior without re-exchanging spent codes or bypassing protocol checks.
- Understand the boundary between anti-replay at the callback and anti-replay for tokens, sessions, APIs, and business actions.

## 1. The Callback Is the Final Step of an Authorization Code Transaction

Suppose **Employee Portal** is built with Spring Boot using OIDC login with registration ID `corporate`. A user visits a page requiring authentication, and Spring Security starts the flow:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: portal.example.com
~~~

Spring Security generates and saves the details needed to correlate the OP's response, then redirects the browser to the authorization endpoint. After successful authentication, the browser is redirected back to:

~~~http
GET /login/oauth2/code/corporate?code=CODE_A&state=STATE_A HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=SESSION_A
~~~

`CODE_A`, `STATE_A`, and `SESSION_A` are illustrative placeholders, not real secrets.

On a valid callback, the application performs:

1. Identifies registration `corporate` and locates the **initiated Authorization Request**.
2. Verifies `state` and callback/correlation conditions.
3. Exchanges the code at the token endpoint with client authentication, plus the PKCE verifier if the flow uses PKCE.
4. For OIDC Login, verifies the ID Token for issuer, audience, expiration, signature, and nonce when used.
5. Builds an `Authentication` with the OIDC principal and stores `SecurityContext` per application session policy.
6. Redirects the browser to an application page such as `/dashboard`.

These steps are meant to happen **once per authorization transaction**. Once the first request succeeds, the authorization code has been spent.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant App as Spring Boot OIDC Client
    participant Provider as OP / Authorization Server
    User->>Browser: Open page requiring login
    Browser->>App: GET /oauth2/authorization/corporate
    Note over App: Create state, save Authorization Request
    App-->>Browser: Redirect to OP
    Browser->>Provider: Authorization Request
    Provider->>User: Authenticate if needed
    Provider-->>Browser: Redirect code=CODE_A and state=STATE_A
    Browser->>App: First callback
    Note over App: Match state and original request
    App->>Provider: Token request with CODE_A
    Provider-->>App: Valid token response
    Note over App: Validate OIDC, establish SecurityContext
    App-->>Browser: Redirect to /dashboard
    Browser->>App: Old callback resubmitted
    Note over App: No pending request left or code already spent
    App-->>Browser: Fail safely
~~~

Duplicate callbacks can arrive after a login session already exists. Thus, **having a valid session** does not mean **an old code can still be exchanged for tokens**.

## 2. Why Can a Callback Be Sent Multiple Times?

| Situation | Manifestation | Underlying nature |
|---|---|---|
| Callback refresh | User reloads `/login/oauth2/code/corporate` | Same URL submitted again |
| Back/Forward | Browser reopens an old callback from history | Flow already completed |
| Network retry | First response lost, proxy/client resends request | Backend may already have succeeded |
| Duplicate redirect | Frontend or middleware triggers navigation twice | Two nearly simultaneous callbacks |
| Two login tabs | Tab A has state A, Tab B has state B | Two separate flows, potentially contending for session |
| Expired session | Callback arrives after original request was purged | Correlation lost |
| Load balancer | Login started on node A, callback hits node B | Missing state if session store is not shared |
| Intentional replay | Someone replays a captured callback URL | Attempting to reuse protocol values |

**A callback sent twice is not enough to conclude an attack is occurring.** Conversely, a request that looks valid at the HTTP layer does not mean it is still valid at the OAuth/OIDC protocol layer.

## 3. Authorization Code: Short-Lived and Single-Use

### 3.1. Why Must a Code Be Single-Use?

An authorization code is a value issued by the AS allowing the client to exchange it for tokens. The code:

- Has a short lifetime.
- Can only be used **once**.
- Is bound to the client it was issued to.
- Is bound to the redirect URI per flow conditions.
- May be linked to a PKCE `code_challenge`.

It is not an access token and must never be sent to a Resource Server.

Example:

~~~text
T0  OP issues CODE_A
T1  Portal sends CODE_A to token endpoint
T2  OP verifies and returns valid tokens
T3  Portal or another party resends CODE_A
T4  OP rejects because code was already consumed
~~~

A response may look like:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant"
}
~~~

### 3.2. `invalid_grant` Does Not Only Mean "Code Already Used"

The token endpoint error `invalid_grant` can indicate the code:

- Was already used.
- Has expired.
- Is invalid.
- Does not match the redirect URI.
- Was issued to a different client.
- Violated another grant condition.

Therefore, **never diagnose replay with certainty from `invalid_grant` alone**. Inspect the preceding flow, registration, callback, error code, session state, and token request timing—without logging real tokens or codes.

### 3.3. The AS Is Responsible for Enforcing Single-Use

If two requests arrive at the token endpoint with `CODE_A`, the AS must guarantee one code cannot be exchanged for two valid token issuances. OAuth 2.0 requires rejecting code reuse; upon detecting code reuse, the AS should consider revoking tokens previously issued from that code where feasible.

This is the AS's responsibility. The RP still must protect **its own state correlation and side effects**.

A single-use code does not make `HttpSession`, access tokens, or business operations single-use as well.

### 3.4. Network Timeouts and Uncertain Outcomes

If Portal sends a token request and times out, any of the following may have happened:

1. The AS never received or processed the code.
2. The AS processed the code and issued tokens, yet the response failed to reach the client.
3. The code expired or was invalid for another reason.

Blindly retrying with the same code does not solve every case; if the AS already consumed the code, retries will fail. When a reliable result cannot be completed, the app must usually **start a fresh authorization flow**, generating new state, code challenge/verifier, and protocol parameters.

## 4. `state`: Binding the Callback to the Initial Request

### 4.1. State Is Generated Before Redirecting

In the Authorization Request, the client creates a random, unpredictable `state`. Pending request data may include:

~~~text
registrationId: corporate
state:          STATE_A
redirectUri:    https://portal.example.com/login/oauth2/code/corporate
scope:          openid profile email
nonce:          NONCE_A (if used)
PKCE data:      verifier/challenge (if used)
~~~

The OP echoes `state` in the authorization response. Spring Security must verify that response matches a request saved in the login context.

### 4.2. State Helps Prevent Login CSRF

If an RP accepts any authorization code sent to its callback without matching it to an initiated request, another party could force a victim's browser to process an authorization result from outside the victim's flow.

`state` is part of the **correlation** mechanism letting the RP answer:

> Did this callback originate from an authorization request initiated by this exact current browser/session?

Never set `state` to a fixed value derived from `userId`, email, or client ID. Those values are predictable or fail to distinguish separate transactions.

### 4.3. Mismatched State Must Be Rejected

Suppose the app holds a pending request with `STATE_A`, yet the callback sends:

~~~text
code=CODE_X&state=STATE_UNKNOWN
~~~

The RP must never:

- Ignore `state` and try exchanging the code anyway.
- Partially match `state`.
- Try the code against multiple clients/providers.
- Use the most recent request regardless of `state`.
- Trust a user ID submitted by the browser in place of correlation.

Without a matching original Authorization Request, there is no basis to trust the callback as a response for the current flow.

### 4.4. Spent State Must Stop Being a Pending Request

A valid flow:

~~~text
Before callback:
    STATE_A -> Pending Authorization Request A

Callback #1:
    STATE_A matches
    A is processed/removed from pending state

Callback #2:
    STATE_A is no longer a pending request
    RP rejects callback
~~~

Consequently, duplicate callbacks can fail **before token exchange**. In that case there will not necessarily be an `invalid_grant` from the OP because the request never reached the token endpoint.

## 5. `nonce` and PKCE Protect Different Steps

### 5.1. OIDC Nonce

`nonce` binds an ID Token to an Authentication Request when used.

~~~text
Authorization Request:
    state = STATE_A
    nonce = NONCE_A

ID token:
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-123",
  "aud": "portal-web",
  "nonce": "NONCE_A"
}
~~~

This is merely an illustrative payload, not a valid signed ID Token.

- `state`: binds the **callback** to the Authorization Request.
- `nonce`: binds the **ID Token** to the OIDC Authentication Request.
- Authorization code: **single-use token-exchange** value.
- PKCE: proves the party exchanging the code holds the matching verifier.

Nonce does not replace state. An ID Token with a valid nonce from an earlier login **does not allow an old code to be reused**.

When OIDC uses nonce, the RP must verify nonce along with other token requirements. The ID Token must have its signature, issuer, audience, timestamps, and related conditions verified before trusting any claim.

### 5.2. PKCE

In Authorization Code flow with PKCE:

1. Client creates an unpredictable `code_verifier`.
2. Client sends `code_challenge`, typically using method `S256`, in the Authorization Request.
3. AS binds the challenge to the issued code.
4. When exchanging the code, client sends the verifier.
5. AS verifies the verifier matches the challenge.

~~~text
Authorization Request:
  code_challenge=CHALLENGE_A
  code_challenge_method=S256

Token Request:
  code=CODE_A
  code_verifier=VERIFIER_A
~~~

PKCE mitigates **code interception**: capturing the code without the verifier is insufficient to exchange for tokens. It does not replace `state`, callback binding, or client authentication when required.

### 5.3. Comparing the Mechanisms

| Mechanism | Responsibility | Does not replace |
|---|---|---|
| Single-use code | AS refuses to issue tokens multiple times from one code | State, PKCE, business logic |
| `state` | RP binds callback to the created request | PKCE, ID Token validation |
| `nonce` | RP binds ID Token to the OIDC request | State, single-use code |
| PKCE | AS binds code exchange to the verifier | State, redirect URI |
| Client authentication | Confidential client proves identity at token endpoint | PKCE and correlation |
| HTTPS | Protects protocol data in transit | Protocol logic checks |

Layering each mechanism in its proper role makes the system much harder to hijack via stolen codes or swapped responses.

## 6. Which Components Handle Callbacks in Spring Security?

With the Servlet stack, default URLs are typically:

~~~text
Login start: /oauth2/authorization/corporate
Callback:    /login/oauth2/code/corporate
~~~

Key components:

| Component | Responsibility |
|---|---|
| `ClientRegistration` | Client info, grant, redirect URI, and provider |
| `OAuth2AuthorizationRequestRedirectFilter` | Performs redirect to the OP |
| `OAuth2AuthorizationRequestResolver` | Builds the Authorization Request |
| `OAuth2AuthorizationRequestRepository` | Saves, looks up, removes pending requests |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `HttpSession`-backed implementation, typical in Servlet OIDC Login |
| `OAuth2LoginAuthenticationFilter` | Receives and processes callbacks |
| OAuth2/OIDC authentication providers | Token exchange and required validation steps |
| `SecurityContextRepository` | Saves and restores Authentication after login |
| `OAuth2AuthorizedClientService` / `Repository` | Manages issued tokens per client/principal |

**No custom controller is needed for `/login/oauth2/code/corporate`** when using `oauth2Login()`'s default callback.

### 6.1. Authorization Request Repository

The repository interface defines the operations:

~~~java
OAuth2AuthorizationRequest loadAuthorizationRequest(
        HttpServletRequest request);

void saveAuthorizationRequest(
        OAuth2AuthorizationRequest authorizationRequest,
        HttpServletRequest request,
        HttpServletResponse response);

OAuth2AuthorizationRequest removeAuthorizationRequest(
        HttpServletRequest request,
        HttpServletResponse response);
~~~

The snippet above shows the key operation signatures, not a complete Java class.

- `saveAuthorizationRequest` persists data before redirecting to the OP.
- `loadAuthorizationRequest` finds the matching pending request.
- `removeAuthorizationRequest` removes the processed request per the implementation's contract.

If a custom repository fails to delete pending state after processing, an old callback can continue finding the original request, creating correlation or side-effect risks. **The repository does not replace the AS's single-use code rule.**

### 6.2. Why Can an Old Callback Fail Even While the Session Is Alive?

A Servlet session may still hold `SecurityContext` after login, while the Authorization Request has already been consumed. They are two distinct pieces of data:

~~~text
HttpSession
├── Authenticated SecurityContext
└── Pending Authorization Request
      (may already have been removed after callback)
~~~

Do not assume that because `HttpSession` exists, an old callback must still be valid. Conversely, an `HttpSession` can be created before login without containing an `Authentication` yet.

## 7. Duplicate Callback Scenarios

### 7.1. Second Callback Arrives After First Callback Succeeded

~~~text
Callback #1:
    state matches pending request
    code accepted by AS
    Spring Security creates Authentication
    browser redirected to /dashboard

Callback #2:
    state no longer has a pending request
    or code is no longer usable
    authentication flow cannot succeed a second time
~~~

The second callback may be blocked at the repository or at the token endpoint. The user may see an error page even though the first attempt established a valid login session.

The application should handle this experience **without leaking codes/states**, letting the user return to the app if a valid session exists or start a fresh login.

### 7.2. Two Concurrent Callbacks

~~~text
Request A: looks up STATE_A -> found
Request B: looks up STATE_A -> may also see it
Request A: proceeds to process
Request B: proceeds to process
AS: only one exchange of CODE_A can succeed
~~~

If the repository uses separate read-then-delete operations, two threads can both observe the state before either removes it.

When building a custom repository for concurrent environments, design for **atomic consume**: only one request should succeed in retrieving and consuming the pending state. The exact mechanism depends on the session store, database, Redis, or synchronization strategy used.

The AS still enforces single-use codes; the RP must additionally guard its own side effects.

### 7.3. Two Tabs, Two Separate Authorization Requests

~~~text
Tab A:
  state=STATE_A
  verifier=VERIFIER_A

Tab B:
  state=STATE_B
  verifier=VERIFIER_B
~~~

These are **two distinct flows**, not necessarily a replay. However, if the repository only keeps one pending request per `HttpSession`, Tab B may overwrite Tab A's request. Tab A's callback will then fail to find its original request.

If the product requires parallel logins across multiple tabs, the repository must support multiple pending requests keyed by `state`, with TTLs, count caps, and session binding. **Never disable state checking** to support multiple tabs.

### 7.4. Stale Session or Wrong Browser

If the browser deletes cookies, the session expires, or the callback is opened in a different browser, Portal loses the original Authorization Request. Even if the URL carries `code`/`state`, the callback must never be guessed into another session.

Recovery means creating a new Authorization Request with a fresh state, verifier, and nonce if needed.

### 7.5. Retry After Timeout

A proxy may resend a callback if the first response was lost. The backend might already have processed and saved `Authentication` successfully, yet the retry sends the old code and gets rejected.

Thus, the callback is a GET endpoint **with single-transaction protocol semantics**. Never blindly retry simply because the HTTP method is GET.

## 8. Race Conditions When Storing State Yourself

A custom repository might implement:

~~~text
request = store.get(state)
if request exists:
    process(request)
    store.delete(state)
~~~

With two concurrent requests:

~~~text
A: get(STATE_A) -> found
B: get(STATE_A) -> found
A: process
B: process
A: delete
B: delete
~~~

Both requests pass the initial check. To prevent this, systems with high concurrency requirements should use **atomic get-and-delete**, transactions, or appropriate locking.

When designing a pending-request store, evaluate:

- Does `state` have sufficient entropy and binding to a trusted session/browser?
- Are client registration and redirect URI preserved in context?
- Are expired states cleaned up?
- How many pending requests can one session hold at most?
- Is consumption safe across multiple instances?
- Do errors or cancellations leave stale state accidentally reusable?

An in-memory map inside a single JVM does not provide cross-node synchronization.

## 9. Load Balancers and Session Stores

Suppose:

~~~text
Browser
  |
Load balancer
  |----- Portal A
  |----- Portal B
~~~

A tab initiates login through Portal A, which saves the pending request in local `HttpSession`. The callback lands on Portal B, which lacks that session data.

The outcome can be an **authorization request not found** error, even though `code` and `state` were validly issued by the OP.

Options:

- Shared/synchronized session store, such as an appropriate Spring Session deployment.
- Session affinity when it genuinely fits architectural requirements, understanding its limits during instance failures/scaling.
- Consistent cookies, domain/path, `Secure`/`SameSite`, and reverse proxy configuration.
- Exact public Redirect URI registered with the OP.
- Protecting forwarded headers so URLs are never built from untrusted hosts.

Never drop `state` to "fix" sessions being lost across instances.

## 10. Spring Boot and Servlet Login Configuration

### 10.1. Dependency and Client Registration

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

An example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/company
~~~

`corporate` is the registration ID in Spring; the actual callback must be permitted by the OP. `openid` indicates OIDC Login, while client ID/secret are provisioned during client registration at the provider.

### 10.2. Default Filter Chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login-error", "/assets/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Spring Security handles the callback per flow; the app does not need to write a custom controller reading `code` and calling the token endpoint.

### 10.3. Redirecting After Successful Login

One way to reduce callback refreshes is moving the browser to a normal URL after login. Example success URL config:

~~~java
http.oauth2Login(login -> login
        .defaultSuccessUrl("/dashboard", true));
~~~

This method goes inside `HttpSecurity` configuration when the app always wants to redirect to `/dashboard`. To return to the saved request instead, keep the default behavior.

The browser is moved off the sensitive URL:

~~~text
/login/oauth2/code/corporate?code=...&state=...
~~~

and sent to:

~~~text
/dashboard
~~~

Refreshing `/dashboard` does not reuse the authorization code.

### 10.4. Handling Error Callbacks with a Failure Handler

You can configure a generic login error page:

~~~java
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

http.oauth2Login(login -> login
        .failureHandler(
                new SimpleUrlAuthenticationFailureHandler("/login-error")));
~~~

This is an illustrative configuration snippet inside `HttpSecurity`, not a standalone complete class. The `/login-error` page should display a neutral message:

> Your sign-in request is no longer valid or could not be completed. Please try signing in again.

Never place `code`, `state`, `code_verifier`, ID tokens, access tokens, or session cookies in the error page query string or user-facing message.

**The failure handler is not a place to retry an old code.** To recover, start a fresh flow with a fresh state/verifier.

## 11. Distinguishing Callback Errors

| Symptom | Detection layer | Possible cause |
|---|---|---|
| Missing/mismatched `state` | RP/repository | Wrong flow, forged callback, stale session |
| No original request | RP/repository | Already processed, session expired, or state lost between nodes |
| `invalid_grant` | AS token endpoint | Spent code, expired code, wrong client/redirect URI, or other invalid grant |
| Wrong PKCE verifier | AS token endpoint | Verifier does not match challenge |
| `invalid_client` | AS token endpoint | Incorrect client authentication |
| Wrong ID token `nonce` | RP/OIDC validation | Token does not match original request |
| Wrong ID token `iss`, `aud`, signature | RP/OIDC validation | Untrusted authentication result |
| `access_denied` | AS authorization response | User declined or OP denied permission |

Do not automatically conclude "we're being hacked" upon seeing `invalid_grant`, nor ignore it if errors spike abnormally.

### 11.1. Second Callback Shows an Error Even Though First Succeeded

A stale callback may cause the UI to show an error while the session from the first request remains valid, or failure handling depending on config may affect other state.

Sensible handling:

1. Never treat an old callback as a valid new login request.
2. Never re-exchange a spent code.
3. Offer a link on the error page to return to the app or start a fresh login.
4. When checking the current session, trust only an `Authentication` actually established by Spring Security.
5. Never wipe all business data merely because an old callback URL was reloaded.

Avoid redirecting errors to a protected URL that immediately re-triggers login, creating a redirect loop.

## 12. Limits of Anti-Replay at the Callback

### 12.1. An Access Token Is Not an Authorization Code

After exchanging the code, the client may receive an access token to call APIs. **A single-use code does not make a bearer access token single-use.**

If an access token leaks, whoever holds it can try reusing it until it expires, unless the Resource Server or a token-binding mechanism prevents it.

The Resource Server must enforce its own policies on token signature/validation, issuer, audience, scopes, expiration, and business permissions. Sender-constrained tokens such as mTLS/DPoP can be used where supported.

### 12.2. Refresh Tokens Have Their Own Replay Policies

A refresh token, if issued, has a different lifecycle and usage rules from an authorization code. Some Authorization Servers use **refresh token rotation** and reuse detection.

Never assume every refresh token is single-use merely because the callback code is single-use.

### 12.3. `state` Does Not Replace Business CSRF Protection

`state` guards against login CSRF/correlation issues in the authorization flow. It does not by itself protect:

- State-changing forms authenticated by session cookies.
- Approval or payment POST requests.
- Session fixation.
- Per-record authorization checks.
- Bearer access token replay attacks.

Session-based web apps still need proper CSRF policies; APIs still must validate tokens and permissions.

### 12.4. Successful Login Does Not Make Business Logic Idempotent

A success handler might provision an internal user or write audit records. Those side effects need their own rules:

- Use `issuer + subject` as the proper account-linking key.
- Enforce unique constraints/upserts for account creation.
- Use a correlation ID or idempotency key when duplicate business writes must be prevented.
- Never trigger money transfers or order approvals simply because an OIDC callback succeeded.

Even though each authorization code is single-use, a user can still initiate **multiple valid fresh login flows**. Business logic must enforce idempotency independently of OAuth/OIDC.

## 13. Safe Observability and Diagnostics

When troubleshooting callback issues, track:

- Flow start timestamp and callback timestamp.
- Registration ID, environment name, instance handling the request.
- Whether a matching pending Authorization Request existed.
- Normalized error category and detection layer.
- Whether multiple callbacks arrived close together or multiple flows existed in the same session.
- Load balancer, session store, cookies, and public redirect URI.
- A dedicated non-credential correlation ID.

**Never log verbatim**:

~~~text
authorization code
state
code_verifier
nonce
access token
refresh token
ID token
client secret
session ID or session cookie
~~~

If telemetry needs to spot duplicate callbacks, use a dedicated event identifier or controlled fingerprint that cannot act as a credential.

### Investigation Sequence

1. Did the browser refresh `/login/oauth2/code/...` or `/dashboard`?
2. Did the first callback already establish Authentication/session successfully?
3. Was the subsequent callback blocked due to missing state, or did it send a token request to the OP?
4. If `invalid_grant`, test hypotheses: expired code, spent code, wrong client/redirect URI/PKCE.
5. Were there two flows from two tabs, or the same callback sent twice?
6. Are sessions shared across instances, and do cookies reach the backend?
7. Did a custom repository or failure/success handler drop state or create side effects?

Diagnose using sanitized state; never put real codes/tokens into logs.

## 14. Practical Scenarios

**Scenario A — Callback refresh:** Browser resends `code=CODE_A&state=STATE_A` after login succeeded. Keep state/code checks intact, return an appropriate error or recovery page, and route the browser to a post-login application page.

**Scenario B — Two tabs:** Tabs A and B have different states. If the repository does not support concurrent pending requests, one tab's callback can fail. A multi-state repository with TTL and single-use consumption is needed if product requirements demand both tabs.

**Scenario C — Two nodes:** Node A saves the Authorization Request, and Node B cannot see it when the callback arrives. Fix the session store or routing; never drop correlation.

**Scenario D — Two simultaneous callbacks:** Two threads both read `state` before deletion. The AS still enforces single-use codes; the RP's custom repository must guard against races and control side effects.

**Scenario E — `invalid_grant` on first try:** Never assume replay by default. Check expiration, redirect URI, client registration, PKCE, parallel requests, and token request timing.

**Scenario F — Callback URL leaked:** A spent code will not issue tokens a second time. For an unspent code, PKCE, client authentication, redirect URI binding, and HTTPS mitigate code capture; avoid logs/referrers exposing query strings.

## 15. Self-Check Questions

**1. Can an authorization code be exchanged for tokens twice?**  
No. Codes are short-lived and single-use; the AS must reject spent codes.

**2. How do `state` and `nonce` differ?**  
`state` binds the callback to the Authorization Request; `nonce` binds the ID Token to the OIDC Authentication Request when nonce is used.

**3. Do duplicate callbacks always reach the token endpoint and receive `invalid_grant`?**  
No. The RP's repository may reject them earlier because the original Authorization Request is no longer found.

**4. Does `invalid_grant` prove a replay attack?**  
No. Expired codes, wrong client/redirect URIs, or other grant conditions can also produce this error.

**5. Why can callbacks fail when running two instances?**  
The pending request/session may only exist on the instance that initiated login; shared state or proper routing is required.

**6. Can we disable state checks to support two tabs?**  
No. Design a repository storing multiple pending requests bound by state and session.

**7. Does a single-use code prevent replay across all APIs?**  
No. Access tokens and APIs have their own protection mechanisms.

**8. Why is business-level idempotency needed even though OAuth codes are single-use?**  
Because users and systems can resubmit business operations or initiate multiple distinct valid login flows; a single-use code does not guarantee a business action runs only once.

**9. What should be done when an old callback is no longer valid?**  
Never retry the old code; return the user to the app if a valid session already exists or start a fresh authorization flow.

## Key Takeaways

An **Authorization code** is short-lived and exchanges for tokens only once. **`state`** binds the callback to a pending request at the RP. **`nonce`** binds the ID Token to the OIDC request when applicable, and **PKCE** binds the code to the verifier during token exchange.

Spring Security Servlet provides filters and `OAuth2AuthorizationRequestRepository` to handle correlation. When a custom repository is needed for multiple tabs, multiple nodes, or parallel callbacks, enforce TTLs, session binding, and single-use state consumption. After successful login, redirect the browser to a normal app URL; duplicate callback errors must recover safely.

These measures protect **the login flow**. They do not replace bearer token protection at the Resource Server, session management, web application CSRF protection, or business operation idempotency.
