# 9.1. AuthorizationRequestRepository and Saving the Initial Request

## 1. Why Must the Authorization Request Be Saved Before Redirecting?

In **Spring Security OAuth 2.0 OIDC Client** running on the Servlet stack, the **Authorization Code** login process does not complete within a single HTTP request. The application receives a request to initiate login, redirects the browser to the Authorization Server/Identity Provider (IdP), and only receives the callback back some time later. The two browser requests to the application may be separated by several seconds, or even several minutes.

Suppose a user is at `https://portal.example.com/orders` and chooses to sign in with a provider having `registrationId=company`. The application builds an `OAuth2AuthorizationRequest` and redirects the browser to the IdP. When the browser returns, Spring Security needs to know:

- **Which login attempt** and which client registration does the callback belong to?
- Does the returned `state` value match the value that was issued?
- What were the initial `redirect_uri`, scopes, and parameters?
- If **PKCE** is used, where is the secret `code_verifier` stored to exchange the authorization code?
- Has this callback already been processed, or is it being replayed?

That is the role of **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`**: saving the state of the **initial authorization request** on the client side before leaving the application, and then retrieving and consuming that state when the callback arrives.

**Without saving the initial request**, looking solely at `?code=...&state=...` from the browser is usually insufficient to bind it to a valid transaction. Having only the authorization code is also insufficient to securely recover the PKCE verifier, registration, and initial context.

> **Scope:** This lesson covers the repository for the **authorization request** in Spring Security **Servlet OAuth2/OIDC Login**. It is distinct from the repository that stores the Access Token after authorization is granted and distinct from `RequestCache`, which stores the URL the user wanted to access before logging in.

## 2. One Login Flow Has Two Legs and One Link

### 2.1. Outbound Leg: Create, Save, Then Redirect the Browser

The user opens the login initiation URL:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.com
~~~

Spring Security selects the `ClientRegistration` named `company`, builds the authorization request with `response_type=code`, `client_id`, `scope`, `redirect_uri`, `state`, and extension parameters such as PKCE/nonce when used.

Before returning HTTP 302, **the repository saves the request**:

~~~text
Browser -> Spring Security
              |
              v
       OAuth2AuthorizationRequest
              |
              v
       AuthorizationRequestRepository.save(...)
              |
              v
HTTP 302 Location: https://id.example.com/authorize?response_type=code&...
~~~

With the default repository, this information resides in the **server-side HTTP session**. The browser typically only holds a session cookie referencing that session, rather than receiving the entire `OAuth2AuthorizationRequest` object.

### 2.2. Return Leg: Correlate and Consume

After the user logs in and grants consent, the IdP sends the browser back to:

~~~http
GET /login/oauth2/code/company?code=AUTHORIZATION_CODE&state=STATE_VALUE HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=EXAMPLE_SESSION_ID
~~~

Spring Security retrieves the initial request information via the repository, verifies `state`, and proceeds to exchange the authorization code for tokens. During callback processing, the saved request must be **removed/consumed** according to the repository's semantics to prevent reuse.

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant F as OAuth2AuthorizationRequestRedirectFilter
    participant R as AuthorizationRequestRepository
    participant A as Authorization Server / OIDC Provider
    participant L as OAuth2LoginAuthenticationFilter
    B->>F: GET /oauth2/authorization/company
    F->>F: Resolve ClientRegistration, create request/state/PKCE
    F->>R: saveAuthorizationRequest(authRequest,...)
    R-->>F: Request saved per browser context
    F-->>B: 302 to authorization endpoint
    B->>A: Login and consent
    A-->>B: 302 callback?code=...&state=...
    B->>L: GET /login/oauth2/code/company?code=...&state=...
    L->>R: removeAuthorizationRequest(request,response)
    R-->>L: Authorization request matching state, or null
    alt Valid request
        L->>A: Exchange code at token endpoint, using PKCE if present
        A-->>L: Access Token (+ ID Token if OIDC)
        L-->>B: Login succeeded / establish session
    else No matching request
        L-->>B: Authentication error, no new login granted
    end
~~~

If the user **denies consent**, the provider may redirect to the callback with `error=access_denied` and `state`. Spring Security still must process the response in the context of the issued authorization request; an error callback is no reason to skip correlation.

## 3. What Information Is Actually Stored?

Spring Security's `OAuth2AuthorizationRequest` describes the transaction **before an authorization code exists**. It contains fields/structures such as:

| Authorization request property | Role | Needs to be restored on callback? |
| --- | --- | --- |
| `authorizationUri` | Provider's authorization endpoint | Identifies the initial request context |
| `responseType` | Typically `code` for Authorization Code flow | Verifies request structure |
| `clientId` | Client registered with the provider | Associates callback with the right client |
| `redirectUri` | Client's callback URI used when requesting the code | Reused during code exchange if required by protocol |
| `scopes` | Permissions requested by the client | Provides scope/grant context |
| `state` | Random value used to pair request and response | **Mandatory correlation check** |
| `additionalParameters` | Parameters sent to the authorization endpoint such as `code_challenge`, `nonce` when applicable | Supports the initiated flow |
| `attributes` | Internal attributes for the framework to continue processing | May contain registration ID, PKCE data, or other supporting info |
| `authorizationRequestUri` | Full constructed authorization URL | Used on the redirect leg |

A conceptual illustration of the stored record:

~~~text
OAuth2AuthorizationRequest
  authorizationUri: https://id.example.com/oauth2/authorize
  responseType: code
  clientId: portal-web
  redirectUri: https://portal.example.com/login/oauth2/code/company
  scopes: [openid, profile, email]
  state: randomly-generated-state
  additionalParameters:
    code_challenge: ...
    code_challenge_method: S256
    nonce: ...                 # if present in OIDC transaction
  attributes:
    registration_id: company  # used by framework to identify client
    code_verifier: ...        # if PKCE is enabled, must be kept secret
~~~

This is an **illustrative model**, not a formal storage format or stable attribute key contract across all Spring Security versions. PKCE values, nonce, and internal attributes depend on the request resolver/configuration mechanism in use.

**AuthorizationRequestRepository stores the initial request, not the tokens issued after login.** Access Tokens and Refresh Tokens belong to `OAuth2AuthorizedClient` and the `OAuth2AuthorizedClientRepository`/`OAuth2AuthorizedClientService` system.

### 3.1. State Is the Correlation Key

`state` is an unpredictable string generated per transaction. Spring Security sends `state` in the authorization request, and the authorization server returns the exact same value in the callback according to protocol rules.

Example:

~~~text
Outbound leg:
  /oauth2/authorization/company
  -> save(request with state = "sG1...v8")
  -> IdP receives state = "sG1...v8"

Return leg:
  /login/oauth2/code/company?code=...&state=sG1...v8
  -> repository finds request belonging to that transaction
  -> continues authentication

If callback carries state = "other-state":
  -> no matching request -> login fails
~~~

`state` is a **transaction-binding value**, not a username, Access Token, authorization code, or arbitrary redirect path. Do not use it to hold sensitive data in readable form or assume that merely seeing `state` in the query string is enough to grant a session.

### 3.2. Why Must the PKCE Verifier Be Retained?

With PKCE, the client generates a random `code_verifier` and sends a transformed `code_challenge` in the authorization request:

~~~text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
~~~

On the outbound leg, the browser/IdP receives the **challenge**, and must not receive the **verifier**. When the callback arrives, the client needs the original verifier to send to the token endpoint along with the authorization code.

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_VALUE&code_verifier=ORIGINAL_VERIFIER
~~~

If a custom repository only saves `state` and discards the associated PKCE attributes, the code exchange step can fail with `invalid_grant` or an equivalent error. **You must save and restore the full `OAuth2AuthorizationRequest` needed for the flow**, rather than building a record with only the three fields `client_id`, `scope`, and `state` and hoping the framework recovers everything else on its own.

PKCE may require configuration depending on the client type, Spring Security version, and provider. Do not assume every client registration enables PKCE in the same way; verify the configuration if your product requires PKCE S256.

### 3.3. State, Nonce, and Session Cookie Do Not Replace Each Other

| Component | Where is it generated/stored? | Primary purpose |
| --- | --- | --- |
| **`state`** | Authorization request; returned via callback | Binds the response to the previously initiated transaction, mitigating login CSRF and cross-transaction mix-ups |
| **`code_verifier`** | Kept secret in client context | Proves the client exchanging the code is the party that initiated PKCE |
| **`nonce`** in OIDC | OIDC request and authentication transaction | Binds the ID Token to the authentication request, helping prevent replay |
| **Session cookie** | Browser holds a session reference | Helps the backend locate the right session holding the request, when using the default repository |
| **Authorization code** | Provider returns on successful callback | Exchanged for tokens at the token endpoint; short-lived, single-use |

`state` does not replace verifying the ID Token's `nonce`. PKCE does not replace checking `state` or binding the callback to the session. A browser session cookie does not prove a callback is valid if `state` does not match.

## 4. Spring Security Servlet's AuthorizationRequestRepository Interface

In Spring Security, the generic type is:

~~~java
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
~~~

The three core operations can be visualized via the interface:

~~~java
public interface AuthorizationRequestRepository<T extends OAuth2AuthorizationRequest> {

    T loadAuthorizationRequest(HttpServletRequest request);

    void saveAuthorizationRequest(
        T authorizationRequest,
        HttpServletRequest request,
        HttpServletResponse response
    );

    T removeAuthorizationRequest(
        HttpServletRequest request,
        HttpServletResponse response
    );
}
~~~

This snippet illustrates the API contract; the corresponding Servlet imports in modern Spring Security are `jakarta.servlet.http.HttpServletRequest` and `HttpServletResponse`.

| Method | When it is used | Implementation responsibility |
| --- | --- | --- |
| `saveAuthorizationRequest(...)` | After Spring builds the authorization request, before redirect | Save the request along with information needed to retrieve it for the right browser/transaction |
| `loadAuthorizationRequest(request)` | When the request needs to be read back from the callback | Return the corresponding valid request, or `null` if absent |
| `removeAuthorizationRequest(request,response)` | When the callback must consume the saved request | Retrieve the matching request and safely delete/mark it as consumed |

Each method works with `HttpServletRequest` to inspect cookies, session, and callback parameters. `HttpServletResponse` allows the implementation to update sessions/cookies upon saving or removing. The repository **does not perform the token exchange itself** and does not decide whether the user is authorized to access business resources.

### 4.1. Separation of Responsibilities with Other Components

| Component | Responsibility |
| --- | --- |
| `OAuth2AuthorizationRequestResolver` | **Creates** the authorization request from the registration and HTTP request |
| `OAuth2AuthorizationRequestRedirectFilter` | Initiates the authorization flow, saves the request, then redirects the browser |
| `AuthorizationRequestRepository` | **Saves / loads / consumes** the initial request |
| `OAuth2LoginAuthenticationFilter` | Handles the callback, correlates the initial request with the response, authenticates login |
| OAuth2/OIDC authentication provider | Exchanges the code, verifies tokens/ID Token, and produces the authentication result |
| `OAuth2AuthorizedClientRepository` | Saves the authorized client and tokens after authorization is granted |
| `RequestCache` / `SavedRequest` | Remembers the page URL the user wanted to visit before logging in |
| `SecurityContextRepository` | Saves the `Authentication` context after login |

In particular, **`RequestCache` and `AuthorizationRequestRepository` are two different stores**:

- `RequestCache` may hold the `/orders` URL so that once the user finishes logging in, they are returned to the page they intended to open.
- `AuthorizationRequestRepository` holds the authorization request with `state`, redirect URI, and PKCE data needed to complete the callback.
- Losing `SavedRequest` may prevent the application from returning to the target page; losing `AuthorizationRequest` can prevent **login from completing**.

## 5. Default Repository: HttpSessionOAuth2AuthorizationRequestRepository

For standard Spring Security Servlet OAuth2 Login, the default implementation is **`HttpSessionOAuth2AuthorizationRequestRepository`**:

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;

HttpSessionOAuth2AuthorizationRequestRepository repository =
    new HttpSessionOAuth2AuthorizationRequestRepository();
~~~

This implementation uses **`HttpSession`** to store the pending authorization request awaiting callback and matches `state` upon retrieval. Data model:

~~~text
Browser
  Cookie: JSESSIONID=SESSION_ABC
         |
         v
Application / Session store
  SESSION_ABC
    pending OAuth2AuthorizationRequest
      state: sG1...v8
      registration: company
      redirect_uri: ...
      PKCE context: ...
~~~

The cookie name may be `JSESSIONID`, `SESSION`, or a name depending on the Servlet/Spring Session configuration. Internal session attribute keys are managed by Spring Security; **do not depend on private attribute names** when writing business logic.

### 5.1. Advantages of Server-Side Storage

- Avoids exposing the entire `OAuth2AuthorizationRequest` and PKCE verifier to the browser.
- Can leverage the session lifecycle to bound the callback waiting window.
- Keeps data bound to the same browser context that initiated login.
- Integrates with Spring Security defaults with minimal custom code, letting the framework handle state/callback correlation.

### 5.2. Conditions for the Return Leg to Find the Session

The browser must carry the right session cookie back to the **same application and context** where the request was saved. The following issues commonly cause session loss:

| Symptom | Impact |
| --- | --- |
| Cookie is blocked, deleted, or not sent on callback | Backend cannot find the session/initial request |
| Session expires before the user completes login | Pending authorization request no longer exists |
| Reverse proxy alters hostname/scheme/port/cookie path | Browser fails to send the right cookie or redirect URI mismatches |
| Load balancer routes callback to a node without the session | Callback cannot find the request without session sharing/sticky routing |
| User opens callback in another browser or private mode | Does not share the same session, so request cannot be restored |
| A new login attempt overwrites the previous pending state | Old callback may no longer match; depends on repository and storage mechanism |

This is why a callback with a syntactically valid `state` string that cannot locate the request on the server must still fail; both **the right state and the right storage context** are required.

## 6. Configuring the Repository in Spring Security Servlet

### 6.1. Basic OAuth2/OIDC Client Configuration

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

The configuration above illustrates an OIDC provider with discovery metadata. Replace the issuer, client ID, and secret with real values; the client secret must be stored securely. The client's redirect URI must be registered accurately at the provider.

### 6.2. Explicitly Using the Default Repository

If the application has no special storage requirements, Spring Security already provides the session-based repository. You can configure it explicitly to make the wiring point clear:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
            authorizationRequestRepository() {
        return new HttpSessionOAuth2AuthorizationRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Key configuration point:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestRepository(repository)))
~~~

This is the Spring Security Servlet DSL using `HttpSecurity` and `SecurityFilterChain`, not `ServerHttpSecurity` in WebFlux. Configuring the repository via the DSL ensures all components participating in the OAuth2 Login flow coordinate through the same save/load mechanism for the authorization request.

If you do not customize it, you can omit the repository bean and the `authorizationRequestRepository(repository)` block; Spring Security will still use the default OAuth2 Login mechanism. **You are not required to define a repository bean just to enable OIDC login.**

### 6.3. Default Initiation and Callback Endpoints

| URL | Function |
| --- | --- |
| `/oauth2/authorization/company` | Initiates the authorization flow for registration `company` |
| IdP's Authorization URI | Browser performs login/consent at the provider |
| `/login/oauth2/code/company` | Default callback for Spring Security to handle the code or OAuth2 error |

If you want to change the initiation or callback URLs, you must keep `authorizationEndpoint().baseUri(...)`, `redirectionEndpoint().baseUri(...)`, the registration's `redirect-uri`, and the allowed URI at the IdP synchronized. Changing only one side can prevent the callback from reaching the filter or cause the provider to reject `redirect_uri`.

**Do not create a custom controller handling `/login/oauth2/code/company`** just to read `code` and `state` when using standard `oauth2Login()`. Doing so easily causes route conflicts or bypasses security checks managed by Spring Security.

## 7. What Happens When the Callback Cannot Find the Initial Request

### 7.1. The “authorization request not found” Error

If a callback arrives but the repository cannot restore the request, Spring Security may throw an error similar to:

~~~text
OAuth2AuthenticationException:
  [authorization_request_not_found]
~~~

The exact error code and message may vary by version or exception wrapping. The meaning is that **there is no authorization request matching the current callback**.

Common causes:

1. **Session cookie did not return** after the browser redirected to the IdP.
2. **Session expired** because the user took too long on the consent screen.
3. **State mismatch**, such as a tampered callback, a callback from another flow, or a replayed callback.
4. **Multi-node without shared session**: the outbound leg was saved on node A, while the callback hit node B.
5. **Multiple concurrent tabs/login flows**: the current storage approach does not retain enough pending requests to handle them independently.
6. **Inconsistent custom repository**: the outbound leg saved under a different key/cookie than the return leg, or failed to restore full attributes.
7. **Mismatched domain, cookie path, SameSite, or reverse proxy** with the redirect/callback.

Do not “fix” this error by accepting callbacks without an initial request or disabling state verification. Doing so breaks the security binding between the initiating request and the response.

### 7.2. Symptom-Based Diagnostic Table

| Symptom | Likely area to inspect | Remediation direction |
| --- | --- | --- |
| Login works on localhost, callback fails after deploy | HTTPS/proxy/cookie/hostname differs from local environment | Check public base URL, trusted forwarded headers, cookie attributes, and redirect URI |
| Incognito browser fails to complete while regular browser works | Cookies restricted or session missing/not sent | Check browser storage policy and actual callback URL |
| One tab logs in fine, two tabs occasionally fail | Multiple authorization requests in the same session interfere with each other | Review how the repository supports pending requests; consider multi-state management |
| Error only appears across multiple instances | Session is stored locally in one node | Use a shared session store or appropriate routing/session architecture |
| Error after user stays at IdP too long | Session and request expired | Tune timeouts appropriately; provide an intentional retry path |
| Callback fails with `invalid_grant` after request is found | Authorization code expired/reused, wrong redirect URI, or wrong PKCE | Inspect token exchange; do not blame the repository for all errors |
| Provider returns `error=access_denied` | User or policy denied consent | Handle login failure/UX while preserving response correlation |
| Callback submitted twice | Request already consumed or code already used once | Subsequent attempt must fail; do not allow reuse |

### 7.3. What Role Does `state` Play on Error Callbacks?

The authorization server may return:

~~~text
/login/oauth2/code/company?error=access_denied&state=ORIGINAL_STATE
~~~

The application should interpret this as the transaction **not being authorized**, without blindly trusting the entire query string just because `access_denied` is present. Callback data passes through the browser and must be evaluated within the context of an issued authentication request.

An `AuthenticationFailureHandler` can display an error explanation page, but it **does not replace `AuthorizationRequestRepository` or the state-matching mechanism**. If the initial request does not exist, the handler must not create a new principal or authorized client on its own.

## 8. Session Cookies, SameSite, and Callbacks from the IdP

### 8.1. Why Are Cookies So Important?

A server-side HTTP session is typically accessed via a session ID stored in a browser cookie. When the browser navigates to the IdP and returns to `portal.example.com`, the cookie must be sent so the repository can see the saved data.

An illustrative session cookie:

~~~http
Set-Cookie: JSESSIONID=OPAQUE_SESSION_ID; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

- **`HttpOnly`** prevents browser-side JavaScript from reading the cookie via `document.cookie`.
- **`Secure`** requires the cookie to be sent over HTTPS (with browser-dependent exceptions/behavior for local development).
- **`SameSite=Lax`** is generally suitable for **top-level GET** callbacks from the IdP to the client, though you must verify the actual response mode.
- **`Path` and `Domain`** determine which URLs receive the cookie.

When callbacks use **`response_mode=form_post`** or cross-site POST flows, the SameSite policy may need to differ from standard GET callbacks. Do not switch cookies to `SameSite=None` indiscriminately; if cross-site cookies are genuinely needed, weigh `Secure`, CSRF, and browser/provider policies. Choose cookie settings based on the **actual response mode** and product architecture.

### 8.2. Reverse Proxies and Public Domains

If the browser sees `https://portal.example.com` while the backend actually runs at `http://internal-app:8080` behind a reverse proxy, you must configure trusted proxy/forwarded headers and the public base URL accurately.

If Spring generates `redirect_uri=http://internal-app:8080/login/oauth2/code/company`, the provider may reject the callback. If the cookie is issued with the wrong `Domain` or `Path`, the callback will not find the session. These are two distinct issues that often appear together right after deployment.

Ensure that:

- The provider has the exact public HTTPS redirect URI registered.
- The application only trusts forwarded headers from reverse proxies managed by your organization.
- The session cookie has appropriate domain, path, `Secure`, and `SameSite` settings.
- The callback reaches the right instance/session store holding the pending state.

## 9. Storing Sessions When the Application Has Multiple Instances

`HttpSessionOAuth2AuthorizationRequestRepository` stores data in `HttpSession`. With a single Spring Boot instance, the HTTP session can reside in the Servlet container's memory. When running multiple instances behind a load balancer, there are two main approaches:

| Deployment approach | Mechanism | Trade-offs |
| --- | --- | --- |
| Sticky session | Browser is generally routed back to the same instance | Simple, but routing-dependent and less resilient during node failures or rolling deploys |
| Shared/distributed session | Multiple instances read from a common session store such as Redis via Spring Session | Suited for scale-out; requires operating Redis, securing connections, TTL, and serialization |

One option in Spring Boot Servlet applications is **Spring Session** backed by Redis. When sessions are centrally managed, the default repository still interacts with `HttpSession`, while Spring Session maps the session into the shared store.

Example Gradle dependencies managed by Spring Boot's BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Example connection and session timeout configuration for a test environment:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
server:
  servlet:
    session:
      timeout: 15m
~~~

This is a conceptual implementation example, not a complete production configuration. Depending on the Spring Boot/Spring Session version, you may need different starters/config, Redis authentication, TLS, session namespaces, serialization, and a secret store. Never hard-code Redis passwords in the repository.

### 9.1. Aligning Storage Lifetimes

Once an authorization request has expired, late callbacks must be rejected. The HTTP session timeout, the authorization code lifetime at the IdP, and any custom request TTL should align sensibly with the login experience, while **never extending sessions indefinitely** just to avoid losing `state`.

If storing requests in an external store outside the session, enforce a dedicated TTL and deletion upon consumption so PKCE data and pending state do not persist longer than necessary.

### 9.2. Session Serialization Compatibility

When using distributed sessions, the storage library may serialize and deserialize session attributes. Any custom repository must ensure the types stored in the session are compatible with the chosen system's serialization. Never put non-serializable HTTP request/response objects, sockets, or application beans into `OAuth2AuthorizationRequest` attributes.

During rolling deploys across versions, changing how objects are serialized in the session can affect state readability between instances. This is part of session migration architecture, not something to solve by dropping state verification.

## 10. Multiple Tabs, Multiple Providers, and Multiple Pending Requests

A user may open two tabs:

~~~text
Tab A:
  /oauth2/authorization/company
  state = A123

Tab B:
  /oauth2/authorization/partner
  state = B456

Then callbacks arrive in order:
  /login/oauth2/code/company?state=A123&code=...
  /login/oauth2/code/partner?state=B456&code=...
~~~

A repository implementation must decide whether to allow **multiple incomplete authorization requests in the same session**. With a single-pending-request structure, request B may overwrite A, causing callback A to miss its `state`. Exact behavior depends on the repository version/customization; **do not assume every session repository supports multiple independent tabs**.

If your product requires concurrent logins or account linking across multiple tabs, you can design a repository storing **multiple requests keyed by state** with session binding, a cap on pending requests, and a TTL. When a callback arrives, the implementation must look up by the exact `state`, **atomically consume that specific request**, and preserve the remaining ones.

Conversely, if your product only permits one login transaction per browser session, you may keep single-request behavior while displaying a safe error and a restart option if the user opens multiple tabs.

### 10.1. Never Use Global State

An anti-pattern:

~~~java
// WRONG: all users share one variable, causing race conditions and transaction leaks.
private static OAuth2AuthorizationRequest lastAuthorizationRequest;
~~~

Storing requests this way allows user B to overwrite user A's state; callbacks from different users will contend for the same object. At a minimum, requests must be bound to the **session/browser** and **state**, never stored in an unkeyed singleton field.

### 10.2. Why Is Using State Alone as the Key Still Insufficient?

If a custom repository stores records in Redis under keys like `oauth2:state:<state>`, a callback carrying `state` still does not prove the browser was the party that initiated login. A secure system must also bind the request to the originating session/browser context, preventing an attacker from using their own `state` to trigger login CSRF in another user's session.

A sound design requires:

1. High-entropy random `state`, generated uniquely per authorization request.
2. Records bound to the initiating session/browser context.
3. Short enough TTL and a cap on pending requests.
4. Lookup matching both `state` **and** session/binding, not merely matching user-supplied query parameters.
5. Atomic removal/consumption so replayed callbacks cannot reuse the record.
6. Preserving all required PKCE and OIDC attributes intact.

## 11. When Should You Write a Custom AuthorizationRequestRepository?

The default session-based repository fits most server-side web applications. A custom repository can be useful when:

- The application requires multiple concurrent authorization flows within one browser session.
- Pending state needs to live in an external store with custom partitioning/TTL models.
- Special stateless callback management is required, while still upholding transaction binding and PKCE guarantees.
- Migration or cross-system session interoperability is required under a tightly controlled design.

Before writing your own, evaluate whether **Spring Session + the default repository** already satisfies your scale-out needs. Customizing OAuth2 request storage demands a thorough understanding of the contract, callback states, and security properties.

### 11.1. Skeleton of a Custom Repository

A custom repository must implement the interface:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public final class CustomAuthorizationRequestRepository
        implements AuthorizationRequestRepository<OAuth2AuthorizationRequest> {

    @Override
    public OAuth2AuthorizationRequest loadAuthorizationRequest(
            HttpServletRequest request) {
        // Look up the matching record by session/binding + state.
        // Never return a request belonging to another browser.
        throw new UnsupportedOperationException("Secure storage mechanism must be implemented");
    }

    @Override
    public void saveAuthorizationRequest(
            OAuth2AuthorizationRequest authorizationRequest,
            HttpServletRequest request,
            HttpServletResponse response) {
        // Save the full request needed for callback, with TTL and session binding.
        // Handle authorizationRequest == null according to the contract.
        throw new UnsupportedOperationException("Secure storage mechanism must be implemented");
    }

    @Override
    public OAuth2AuthorizationRequest removeAuthorizationRequest(
            HttpServletRequest request,
            HttpServletResponse response) {
        // Look up and consume the matching record, preventing callback replay.
        throw new UnsupportedOperationException("Secure storage mechanism must be implemented");
    }
}
~~~

This is a **responsibility-illustrating API skeleton**, intentionally not a runnable implementation. Do not copy and deploy this skeleton; you must design complete session binding, TTL, concurrency handling, secret protection, PKCE recovery, and deletion strategies. For typical needs, using the built-in repository is safer and simpler.

### 11.2. Why Is a Cookie-Based Repository Harder Than It Looks?

Some systems want to store the authorization request in a cookie to avoid server-side session requirements. However, cookies are **held and sent back by the browser**, meaning they can be tampered with, copied, replayed, or leaked through misconfiguration.

If you choose a cookie-based repository, you must evaluate:

| Requirement | Risk if omitted |
| --- | --- |
| Tamper resistance (integrity) | Attackers alter registration, redirect URI, or correlation info |
| Sensitive data protection (confidentiality) | PKCE verifier/attributes can leak if only Base64-encoded |
| Browser/transaction binding | Login CSRF or cross-transaction substitution |
| Expiration and cookie size limits | Stale cookies persist too long, overflow header limits, or get truncated |
| `HttpOnly`, `Secure`, `SameSite`, domain/path | Unintended scripts or requests receive the cookie |
| Rotation and cookie deletion after callback | Old state can be replayed |
| Key management for signing/encryption | Cross-node compatibility issues; key compromise affects all transactions |

**Base64 encoding is not encryption or a protective signature.** Never build a repository that stores JSON/Java objects in a cookie and merely compares `state` without integrity, confidentiality, and replay protection.

In practice, a **server-side session store** is usually the right choice for Spring MVC applications with OIDC login.

## 12. Interaction with FailureHandler and SuccessHandler

`AuthenticationSuccessHandler` and `AuthenticationFailureHandler` decide what response the browser receives after login succeeds or fails; the repository decides **whether the callback's context is valid to process**.

| Scenario | AuthorizationRequestRepository | Application-side outcome |
| --- | --- | --- |
| Callback with code, valid state, valid token | Restores/consumes initial request | Can create `Authentication` and invoke `SuccessHandler` |
| Callback `error=access_denied` for a valid request | Transaction still has context to handle the error | Reports that login/authorization did not succeed |
| Callback without a matching request | Cannot restore context | Does not create `Authentication`; takes appropriate failure path |
| Repeated callback after an earlier success | Request already consumed, code is single-use | Rejects reprocessing; does not issue a new session from old code |
| Already logged in, user opens URL requiring higher privilege | Does not necessarily re-initiate OAuth2 login | Application's `AccessDeniedHandler`/authorization policy |

Distinguish this from `AccessDeniedHandler`: a provider's `error=access_denied` callback is an **OAuth2 authorization/login failure**, whereas an HTTP 403 when an already authenticated user lacks permission for a resource is an **application authorization failure**. The two cases require different UX and handling mechanisms.

## 13. Observability and Diagnostics Without Leaking State

To support operations, you can emit the following events as **minimal metadata**:

~~~text
oauth2_authorization_started
  registration_id=company
  correlation_id=<internal-safe-id>

oauth2_callback_processed
  registration_id=company
  outcome=success
  correlation_id=<internal-safe-id>

oauth2_callback_failed
  registration_id=company
  reason=authorization_request_not_found
  correlation_id=<internal-safe-id>
~~~

This is an illustrative format, not Spring Security's default output. **Never log** `state`, `code`, `code_verifier`, `nonce`, session cookies, ID Tokens, Access Tokens, Refresh Tokens, or full callback URLs to logs/analytics. If using an internal correlation ID for investigation, generate and manage it independently from protocol credentials, with an appropriate TTL and access policy.

When diagnosing `authorization_request_not_found`, trace in sequence:

1. Did a request hit `/oauth2/authorization/{registrationId}` and save successfully?
2. Did the browser receive the session cookie on the outbound leg?
3. Did the callback arrive at the right hostname/path carrying the cookie for the same session?
4. Does the session exist on the node handling the callback, and is it still within its valid lifetime?
5. Does the response carry the `state` matching the initiated transaction?
6. Did a new flow, multiple tabs, or a repeated callback overwrite or discard the old request?
7. Is a custom repository, cookie attribute, or reverse proxy skewing behavior?

This is a **runtime debugging thought process**, not a reason to bypass any security step. Never resort to "if the request is missing, just try exchanging the code anyway," because the token endpoint may reject it and the application loses protection against login CSRF.

## 14. Case Studies

### Scenario A: Successful Login on a Single Machine

The browser calls `/oauth2/authorization/company`. Spring Security saves the authorization request in session `S1`. The IdP returns `code` along with the matching `state`, and the browser brings back the cookie for `S1`. The repository finds and consumes the exact request, and the framework proceeds with token exchange.

**Takeaway:** the callback must be linked to the initial request, not merely trusted based on the code or provider hostname.

### Scenario B: User Clears Cookies While at the IdP

The authorization request remains in the old session on the server, but the browser no longer has a reference to that session. The callback carries a valid `state` but cannot find the initial request.

**Expected outcome:** login fails, and the application lets the user explicitly start over. Do not try searching across the entire session store by `state` alone to grant login.

### Scenario C: Two Tabs Initiate Login Concurrently

Tabs A and B generate two different `state` values within one session. If the repository only retains a single pending request, the tab whose callback arrives first may find its record overwritten.

**Design approach:** when business requirements demand concurrent flows, use a repository capable of storing multiple requests keyed by `state` with session binding, TTL, and single-use semantics. If unsupported, present an appropriate error/UX for the superseded flow.

### Scenario D: Running Three Instances Behind a Load Balancer

Node A stores the request in an in-memory session, and the callback lands on Node C. Node C does not have the data.

**Design approach:** use a shared session store like Spring Session Redis or a controlled session routing strategy; never store authorization requests in global variables or disable state validation.

### Scenario E: Callback `state` Differs from the Saved Value

The browser sends `state=WRONG_VALUE`, while the session holds a request with `state=ORIGINAL_VALUE`.

**Expected outcome:** the repository does not return a request for the mismatched transaction, and Spring Security does not complete login. Never overwrite the session's `state` to "match" an incoming external callback.

### Scenario F: PKCE Enabled but Custom Repository Drops Attributes

The client only saves client ID, redirect URI, and `state`. When the callback arrives, Spring Security cannot recover the original verifier.

**Outcome:** token exchange may fail. The repository must preserve all necessary `OAuth2AuthorizationRequest` attributes intact, including PKCE data stored internally by the framework.

### Scenario G: Provider Returns `error=access_denied`

The user denies consent or the provider rejects the request. The browser returns with `error` and `state`, without a success code.

**Expected outcome:** do not create a new authorized client/token; handle the error within the context of the initial request and show an explanatory page, avoiding infinite redirect loops.

### Scenario H: OAuth2 Login Succeeded, but Target Page Was Not Restored

The framework authenticated properly and the principal exists, yet the user is taken to the home page instead of the original `/orders` URL.

**Analysis:** the authorization request was already restored, so the issue likely lies in `RequestCache`, `SavedRequest`, the success handler, or post-login redirect policy. Do not confuse this with an `AuthorizationRequestRepository` failure.

## 15. References

- Spring Security — Servlet OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth 2.0 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — AuthorizationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/AuthorizationRequestRepository.html
- Spring Security — HttpSessionOAuth2AuthorizationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange (RFC 7636): https://www.rfc-editor.org/rfc/rfc7636
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

## 16. Summary of the Initial Request Persistence Flow

~~~text
GET /oauth2/authorization/company
  -> OAuth2AuthorizationRequestResolver
       creates OAuth2AuthorizationRequest
       (client, redirect, scopes, state, PKCE context...)
  -> AuthorizationRequestRepository.saveAuthorizationRequest(...)
  -> HTTP 302 to IdP

Browser login / consent at IdP
  -> GET /login/oauth2/code/company?code=...&state=...
  -> OAuth2LoginAuthenticationFilter
       calls repository to retrieve and consume pending request
       correlates transaction/state
       reuses PKCE verifier, redirect URI, and matching registration
  -> Token endpoint
  -> OIDC validation / OAuth2 login
  -> Session Authentication and OAuth2AuthorizedClient

If request is not found or state does not match
  -> fail closed: do not create new login/token from callback.
~~~

**`AuthorizationRequestRepository` is the correlation link between the outbound and return legs of the OAuth2/OIDC Authorization Code flow.** For typical Spring MVC applications, `HttpSessionOAuth2AuthorizationRequestRepository` is the appropriate default choice. When scaling out to multiple nodes, multiple tabs, or alternative storage mechanisms, preserve the principles of **session binding, state verification, PKCE verifier protection, bounded TTL, and single-use consumption** so Spring Security's security guarantees remain intact.
