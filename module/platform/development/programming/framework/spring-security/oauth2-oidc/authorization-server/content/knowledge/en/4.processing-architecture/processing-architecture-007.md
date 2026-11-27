# SecurityContext, Principal, and Authorization Data in Each Request

> **Chapter:** Processing Architecture  
> **Module:** SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER  
> **Scope:** Request processing architecture in Spring Boot applications using Spring Security and Spring Authorization Server to build, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server.

## 1. Learning objectives

After completing this lesson, you will be able to:

1. Explain the relationship between `SecurityContextHolder`, `SecurityContext`, `Authentication`, `principal`, and `GrantedAuthority`.
2. Describe how Spring Security restores, authenticates, authorizes, and clears security state within **each HTTP request**.
3. Identify the `Authentication` at Authorization Server endpoints, especially the distinction between **user** and **client**.
4. Distinguish **per-request access rights** from **persisted OAuth 2.0 authorization state**.
5. Safely retrieve the principal in controllers, services, and a JWT Resource Server.
6. Design and test properly for session-based requests, Bearer-token requests, and asynchronous execution flows.

Core takeaway: **`SecurityContext` tells you whom Spring Security considers the authenticated subject while processing a request**, whereas **whether a specific operation is allowed** depends on policies and business data. In an Authorization Server, grant state persisted via `OAuth2AuthorizationService` is **a separate model**.

## 2. Objects to distinguish

In the **Spring Security Servlet stack**, a typical structure looks like this:

~~~mermaid
flowchart TB
    F["HTTP request"]
    P["FilterChainProxy / SecurityFilterChain"]
    H["SecurityContextHolder<br/>Accesses context bound to current execution thread"]
    C["SecurityContext"]
    A["Authentication"]
    R["principal<br/>Who is authenticated?"]
    D["credentials<br/>Authentication evidence"]
    G["authorities<br/>Roles / high-level permissions"]
    Z["AuthorizationManager / method security<br/>Decides whether the request may proceed?"]
    E["Controller / business logic"]

    F --> P
    P --> H
    H --> C
    C --> A
    A --> R
    A --> D
    A --> G
    P --> Z
    Z --> E
~~~

| Concept | Meaning | Do not confuse with |
| --- | --- | --- |
| `SecurityContextHolder` | Entry point to the current execution thread's `SecurityContext` under the configured strategy | Persistent login store |
| `SecurityContext` | Container holding the current `Authentication` | HTTP session or access token |
| `Authentication` | Represents the subject's authentication info and authorities at processing time | Always an end user |
| `principal` | Object identifying the authenticated subject | Always `UserDetails` or a user UUID |
| `credentials` | Evidence used during authentication, often erased afterward | A place to store passwords/tokens for reuse |
| `authorities` | Set of `GrantedAuthority` such as `ROLE_ADMIN`, `SCOPE_booking.read` | Per-record data ownership |
| `SecurityContextRepository` | Mechanism to restore/persist `SecurityContext` across requests when needed | `OAuth2AuthorizationService` |
| `OAuth2Authorization` | State of an OAuth 2.0 authorization/token grant | HTTP request thread context |
| `OAuth2AuthorizationConsent` | Approved consent details bound to a client and subject | Blanket permission for all future API requests |
| `AuthorizationDecision` / authorization result | Result of evaluating an access rule when invoked | Access token or authorization code |

### 2.1. `SecurityContextHolder` is where you read the current context

In a typical Spring MVC application, Spring Security binds the context to the request-handling **thread** (`MODE_THREADLOCAL` by default). Common lookup:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

This statement **does not query a user database**, does not verify a JWT signature, and does not issue tokens. It simply retrieves the current authentication result placed into the context by security filters/mechanisms.

Specifically:

- Before an authentication outcome exists, `getAuthentication()` may be `null`.
- When anonymous authentication is enabled, it may return an `AnonymousAuthenticationToken`; never treat this token as proof of a real logged-in user.
- After the request finishes, Spring Security must **clear the context from the thread** to avoid leaking identity to the next request when pooled threads are reused.
- This lookup applies to **Servlet/MVC**. WebFlux applications use a reactive context (`ReactiveSecurityContextHolder`) instead of ThreadLocal by default.

### 2.2. What does `Authentication` contain?

The `Authentication` interface represents two different situations:

1. **Before authentication:** input data, such as an unverified username/password, typically with `isAuthenticated() == false`.
2. **After authentication:** the result accepted by a trusted authenticator, carrying principal and authorities.

Key methods to know:

~~~java
Authentication authentication = SecurityContextHolder.getContext()
        .getAuthentication();

if (authentication != null) {
    Object principal = authentication.getPrincipal();
    String name = authentication.getName();
    Collection<? extends GrantedAuthority> authorities =
            authentication.getAuthorities();
    boolean authenticated = authentication.isAuthenticated();
}
~~~

**Never rely on `isAuthenticated()` alone to prove a real user logged in**: an anonymous token can also return `true`. When checking in code, use Spring's authorization policies or combine with an anonymous check via `AuthenticationTrustResolver`.

`credentials` can hold sensitive evidence prior to verification; systems usually erase this field after authentication succeeds. **Never print raw `authentication` or `credentials` to logs.**

### 2.3. Principals take many shapes

| Context | Common `Authentication` type | `getPrincipal()` is typically |
| --- | --- | --- |
| Form login in Authorization Server | `UsernamePasswordAuthenticationToken` | `UserDetails`, or custom principal |
| OIDC login in OAuth2 Client | `OAuth2AuthenticationToken` | `OidcUser` in OIDC |
| OAuth2 Resource Server receiving JWT | `JwtAuthenticationToken` | `Jwt` |
| Resource Server receiving opaque token | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |
| Client authentication at AS token endpoint | `OAuth2ClientAuthenticationToken` (SAS 1.x generation) | Principal representing the **client** per AS mechanism |
| Unauthenticated, anonymous enabled | `AnonymousAuthenticationToken` | Usually the string `"anonymousUser"` |

Exact types depend on extensions and Spring versions. Never write `(UserDetails) authentication.getPrincipal()` in code invoked across multiple endpoint types: on a JWT Resource Server the default principal is `Jwt`, while at the token endpoint it may be a client.

**`authentication.getName()`** is the logical identifier of the current principal: in a JWT Resource Server it defaults to `sub`, and in Client Credentials it may be the client ID. It is not necessarily an email, display username, user table primary key, or Resource Owner.

## 3. How does a request flow through Spring Security?

In the Servlet stack, a request traverses `DelegatingFilterProxy`, `FilterChainProxy`, and **one** matching `SecurityFilterChain`. Filters evaluate authentication/authorization before the request reaches a controller.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser / Client
    participant F as Security Filter Chain
    participant R as SecurityContextRepository
    participant H as SecurityContextHolder
    participant M as AuthenticationManager / Provider
    participant A as AuthorizationManager
    participant C as Controller

    B->>F: HTTP request
    F->>R: Load context per configuration
    R-->>F: Existing or empty SecurityContext
    F->>H: Set context for request
    opt Request carries credentials to verify
        F->>M: Authenticate credential / Bearer token
        M-->>F: Verified Authentication or error
        F->>H: Update Authentication
    end
    F->>A: Check access
    alt Permitted
        A-->>F: Granted
        F->>C: Invoke handler with current principal
        C-->>B: Response
    else Denied
        A-->>F: Denied
        F-->>B: 401 / 403 or appropriate redirect
    end
    opt Changes need persistence across requests
        F->>R: Save context per configured mechanism
    end
    F->>H: Clear context when processing ends
~~~

The diagram illustrates the **logical lifecycle**, rather than locking down the physical order of every filter or claiming every request calls save. For instance, `SecurityContextHolderFilter` loads context from the repository but **does not automatically save it**. When an authentication flow manages context manually, it must explicitly call `SecurityContextRepository.saveContext(...)` if reuse across subsequent requests is required.

Key conceptual steps:

1. **Select filter chain.** If the application defines multiple `SecurityFilterChain` beans, the first chain matching the request by matcher and priority applies. Chains are not combined.
2. **Initialize/restore context.** The repository can load context from an HTTP session or configured store; stateless APIs typically start with an empty context.
3. **Authenticate.** Filters read username/password, session, or Bearer token depending on endpoint and config, and set `Authentication`.
4. **Authorize.** Spring Security checks policies like `authenticated()` or `hasAuthority(...)`; business logic can verify resource-level permissions.
5. **Cleanup.** Context must never leak onto a reused thread; persistence across requests, when needed, belongs to the repository/session/token, not a ThreadLocal variable.

### 3.1. Why can two consecutive requests have different contexts?

For example:

- Initial `GET /login` without a user: context may be empty/anonymous.
- `POST /login` succeeds: context gets the user `Authentication`; the login mechanism persists the session accordingly.
- Redirected `GET /oauth2/authorize` from the same browser sending the cookie: the user is restored from session into the **new request's** context.
- `POST /oauth2/token` from the backend Client: this new request uses **client** authentication; it must not rely on the earlier login request's principal.

There is no global `SecurityContext` shared across all users or all requests. Even when the same session is restored, each subsequent request has a fresh context lifecycle.

## 4. How does SecurityContext differ from authorization information?

In OAuth 2.0/OIDC systems, the word "authorization" has **at least three meanings**:

| Information group | Question answered | Typical location | Lifecycle |
| --- | --- | --- | --- |
| **Current Authentication** | Who is this request's subject and how were they authenticated? | `SecurityContext` / `Authentication` | Request-scoped; may be restored from session or token |
| **Per-request authorization decision** | Is the current request allowed to call this endpoint, method, or view this object? | `AuthorizationManager`, `@PreAuthorize`, business checks | Evaluated at request time |
| **Issued OAuth2 authorization** | Which client was granted what permissions via which grant, and are tokens/codes still valid? | `OAuth2Authorization` in `OAuth2AuthorizationService` | Can outlive requests in an appropriate store |
| **Recorded Consent** | Which authorities/scopes did the Resource Owner approve for a client? | `OAuth2AuthorizationConsent` in `OAuth2AuthorizationConsentService` | Can persist across multiple requests/sessions |

Data flow diagram:

~~~mermaid
flowchart LR
    X["Request /oauth2/authorize<br/>User Authentication"]
    Y["Spring Authorization Server"]
    C["RegisteredClientRepository<br/>Client config"]
    O["OAuth2AuthorizationService<br/>Grant, code, token, authorizedScopes"]
    N["OAuth2AuthorizationConsentService<br/>Approval decisions"]
    T["Request /oauth2/token<br/>Client Authentication"]
    S["Resource Server<br/>API access decisions"]

    X --> Y
    T --> Y
    C <--> Y
    O <--> Y
    N <--> Y
    Y -->|"Issues access token"| S
~~~

In the **Spring Authorization Server 1.x** line, `OAuth2Authorization` contains fields such as `registeredClientId`, `principalName`, `authorizationGrantType`, `authorizedScopes`, tokens, and attributes. This data is persisted via `OAuth2AuthorizationService`. It **is not** `SecurityContextHolder.getContext()`.

For example, the client exchanges an authorization code at the token endpoint after the browser has left the login flow. The AS can still match the grant and resource owner details via the **`OAuth2Authorization` record**, without needing to "carry over the old request's ThreadLocal" to the code-exchange request.

`OAuth2AuthorizationConsent` typically records approved permissions for a client and resource owner pair. Having consent **does not guarantee** all subsequent API requests are allowed: the Resource Server must still validate tokens and enforce business rules.

## 5. Request-by-request breakdown of Authorization Code + PKCE

Assume four participants:

- **Resource Owner:** user Lan.
- **Client:** application `booking-web`.
- **Authorization Server:** `https://auth.example.test`, a Spring Boot/Spring Authorization Server application.
- **Resource Server:** `https://api.example.test`, a Spring Boot API.

The `.example.test` domain and details below are illustrative only.

### 5.1. Request A — `GET /oauth2/authorize`

The client redirects the browser to the AS with `client_id`, `response_type=code`, `redirect_uri`, `scope`, `state`, and `code_challenge`.

- **Who sends the HTTP request?** The user's browser.
- **Who needs to be authenticated?** The Resource Owner (Lan), per the flow.
- **What is in the context?** If Lan already logged in via session, Lan's `Authentication` can be restored; otherwise, the AS prompts for authentication.
- **What authorization info is involved?** The AS queries `RegisteredClientRepository`, validates OAuth2 parameters, client, and scopes, and checks consent policy.
- **Outcome?** May redirect to the login page, consent page, or return an authorization code.

**Pitfall:** having `client_id` in the query string does not mean this HTTP request was authenticated with a client secret. At the authorization endpoint, the system must verify client registration/redirect URI, but this never replaces client authentication at the token endpoint.

### 5.2. Request B — `POST /login`

Lan submits login credentials to the AS.

- The login filter uses the appropriate `AuthenticationManager` and `AuthenticationProvider`.
- Upon successful authentication, Lan's `Authentication` is placed in the context.
- The login/session mechanism persists the context per configuration so the subsequent redirected request recognizes Lan.
- Does not automatically issue an API access token just because form login succeeded.

**Pitfall:** never exchange the user's password directly for tokens via an unauthorized shortcut; Authorization Code + PKCE separates user login from client code exchange.

### 5.3. Request C — Returning to `/oauth2/authorize` and consent

The browser sends the session cookie. The AS restores principal Lan, enforces client and scope policies, and displays consent if required. After Lan approves, the AS may save `OAuth2AuthorizationConsent` and create an `OAuth2Authorization` holding the authorization code/grant state.

Key relationship:

~~~text
SecurityContext during authorization request
    -> Resource Owner Authentication (Lan)

Persisted OAuth2Authorization
    -> registeredClientId = booking-web
    -> principalName = Lan's identifier
    -> authorizedScopes = scopes actually granted
    -> authorization code / grant state
~~~

The next request can process the code thanks to this grant record. It does not need to re-read Lan's browser session on the same thread.

### 5.4. Request D — `POST /oauth2/token`

`booking-web`'s backend calls the token endpoint with `grant_type=authorization_code`, `code`, `redirect_uri`, and `code_verifier`. Confidential clients also use their registered client authentication method.

- **Authentication context at the token endpoint** may represent the **client** via `OAuth2ClientAuthenticationToken` or the equivalent API/version type.
- The AS authenticates the client and validates the code, PKCE, redirect URI, and stored authorization record.
- **The grant's Resource Owner** is resolved from the `OAuth2Authorization` record; never assume `SecurityContextHolder.getContext().getAuthentication()` on the token request is Lan.
- The AS may issue an access token, a refresh token per policy, and an ID token for valid OIDC flows.

**Major pitfall:** attaching a shared filter/logging handler that calls `getPrincipal()` and casts it to Lan's user type will crash or mislog the client ID as a user ID at the token endpoint.

### 5.5. Request E — `GET /api/bookings`

The client calls the Resource Server with the access token:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

At the **Resource Server**, the Bearer token is verified and Spring Security builds the appropriate `Authentication`, usually `JwtAuthenticationToken` for JWTs. The default principal is the `Jwt` object; valid scopes are typically mapped to authorities prefixed with `SCOPE_`.

The API checks:

1. Token validity by signature or introspection, issuer, expiration, and intended `audience`.
2. Matching scope/authority, such as `SCOPE_booking.read`.
3. Business permissions: is Lan allowed to read those specific bookings?

The Resource Server never inherits the Authorization Server's session or `SecurityContext` over the network.

### 5.6. Request F — OIDC UserInfo (if enabled)

OIDC UserInfo is an **access-token-protected resource**. Requests to this endpoint carry a Bearer token and are authenticated/authorized by the AS's corresponding mechanism. During that request, `Authentication` carries details derived from the access token; never assume it is the `UsernamePasswordAuthenticationToken` from the initial login session.

### 5.7. Summary table: "Who is the principal?"

| Request | Incoming evidence | Principal (reason carefully) | Governing authorization data |
| --- | --- | --- | --- |
| `GET /oauth2/authorize` | User session if logged in | **Resource Owner** or anonymous/empty | Client registration, requested scopes, consent |
| `POST /login` | Username/password or other login mechanism | Authenticated user | Login and session policies |
| Consent / resumed authorize | User session | **Resource Owner** | Consent, `OAuth2Authorization` |
| `POST /oauth2/token` | Client authentication + code/verifier or grant | Typically the **Client** in client auth step; not assumed to be user | Stored grant/token, client metadata |
| `GET /api/...` at RS | Access token | Subject from access token (user or client) | Token claims, audience, scope, business permissions |
| `GET /userinfo` | Access token | Subject per Bearer mechanism | Valid token, OIDC claims/scopes, and policy |

**There is no single rule that "principal is always the user" across all endpoints.** What `principal` represents depends on the `Authentication` type and request purpose.

## 6. Examples of reading the principal in Spring MVC

### 6.1. Injecting `Authentication` directly in a controller

In a Spring Security-protected controller:

~~~java
@RestController
@RequestMapping("/api")
public class ProfileController {

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
            "principalName", authentication.getName(),
            "authenticationType",
                authentication.getClass().getSimpleName()
        );
    }
}
~~~

This snippet only illustrates accessing the authentication object supplied by Spring MVC/Spring Security. Protect the endpoint with `authenticated()` or a stricter policy so `authentication` is guaranteed appropriate before use. In production, avoid exposing internal token, authority, or credential details on public diagnostic APIs.

### 6.2. Using `@AuthenticationPrincipal` on a JWT Resource Server

When you know the endpoint lives on a JWT Resource Server:

~~~java
@RestController
@RequestMapping("/api")
public class BookingController {

    private final BookingService bookingService;

    public BookingController(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    @GetMapping("/bookings")
    public List<BookingDto> myBookings(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        return bookingService.findVisibleBookingsForSubject(subject);
    }
}
~~~

Conditions for this pattern to be safe: the request has been JWT-authenticated by Spring Security Resource Server, the principal is `Jwt`, and `sub` is meaningful in your system. Never look up arbitrary records directly by `sub` without mapping issuer/tenant/internal user and checking permissions.

For an OIDC Client logging in via `oauth2Login()`, the client-side principal can be `OidcUser`:

~~~java
@GetMapping("/account")
public String account(@AuthenticationPrincipal OidcUser user) {
    return user.getSubject();
}
~~~

**Do not swap** `OidcUser` and `Jwt` across these two endpoint kinds: one handles **Client** OIDC login, while the other handles **Resource Server** Bearer access tokens.

### 6.3. Checking authorities and data-level permissions

The HTTP layer can use:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/bookings/**")
                .hasAuthority("SCOPE_booking.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

This example assumes a **standalone Resource Server** configured with `issuer-uri`, verification keys, required audience rules, and dependencies. `SessionCreationPolicy.STATELESS` ensures security mechanisms in this chain do not use an HTTP session to load context. `SecurityContext` still exists **for the duration of request processing**.

Add object-level checks in the service layer:

~~~java
@Service
public class BookingAuthorizer {

    private final BookingRepository bookingRepository;

    public BookingAuthorizer(BookingRepository bookingRepository) {
        this.bookingRepository = bookingRepository;
    }

    public boolean canRead(String bookingId, Authentication authentication) {
        if (authentication == null) {
            return false;
        }

        // Illustration: resolvePrincipal must securely map
        // issuer + subject + tenant to an internal identity.
        String internalUserId = resolvePrincipal(authentication);
        return bookingRepository.existsVisibleToUser(
            bookingId, internalUserId
        );
    }

    private String resolvePrincipal(Authentication authentication) {
        // Implement principal mapping in your real application.
        throw new UnsupportedOperationException("Application-specific");
    }
}
~~~

`resolvePrincipal` above is an **integration point left to implement**, not ready-to-run code. Its purpose is to show that scope `booking.read` is only one precondition; who may read which booking depends on data and business policy. In a full API, you can use `@PreAuthorize` with `@EnableMethodSecurity` or invoke the authorizer directly in the service.

## 7. Session, statelessness, and SecurityContext persistence

### 7.1. The authorization endpoint typically needs a user login session

Interactive browser login/consent requests usually rely on a **session** to recognize the Resource Owner across redirects. `SecurityContextRepository` can save/restore `Authentication` via `HttpSession` or an appropriate store.

Simple example:

~~~text
Request 1: POST /login
    authentication = Lan
    -> save context to session via login mechanism

Request 2: GET /oauth2/authorize
    JSESSIONID cookie
    -> restore Lan's authentication
    -> proceed to consent / issue code

Request 3: POST /oauth2/token (backend Client)
    -> authenticate client and validate authorization code
    -> NO need to inherit Request 2's ThreadLocal
~~~

When writing a custom authentication filter/controller and wanting to **persist login across subsequent requests** with `SecurityContextHolderFilter`, merely calling `SecurityContextHolder.setContext(...)` is usually **not enough**. You must call `SecurityContextRepository.saveContext(...)` per your configuration. Spring Security's built-in login filters already handle this in their flows.

### 7.2. The Resource Server can be stateless

A JWT Resource Server typically needs no login session on the AS. Each request carries a Bearer token; the RS verifies the token and creates the corresponding `Authentication` for that request. When the request ends, the context is cleared.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Resource Server
    participant V as JWT Validator
    participant B as Business Service

    C->>R: Request 1 + access token
    R->>V: Validate token
    V-->>R: Request 1 Authentication
    R->>B: Check scope + data permissions
    B-->>R: Result
    R-->>C: Response
    Note over R: Clear Request 1 SecurityContext

    C->>R: Request 2 + access token
    R->>V: Re-validate token per configured mechanism
    V-->>R: Request 2 Authentication
    R-->>C: Response
~~~

The token may remain valid across multiple requests, yet `SecurityContext` is not a shared global variable. With self-contained JWTs, the RS typically does not call the AS on every request; immediate revocation requires an additional strategy if demanded.

### 7.3. `OAuth2AuthorizationService` does not replace sessions

Distinctions to keep clear:

- **HTTP session**: can track the Resource Owner's login across requests to the AS.
- **`OAuth2AuthorizationService`**: persists authorization grant and token state for issuance, lookup, or revocation by the AS.
- **`OAuth2AuthorizationConsentService`**: persists consent decisions when required.
- **JWT access token**: can be verified directly by the RS; the token is not an AS session.
- **`SecurityContextHolder`**: access point for the current request's `Authentication`; does not replace any of the stores above.

In multi-instance production deployments, choose durable/distributed storage for authorizations, consents, and login sessions (if used), alongside proper key-signing/rotation policies. `InMemoryOAuth2AuthorizationService` is useful for development or testing; it does not share data across instances or survive restarts.

## 8. Threading, async, and safety considerations

### 8.1. ThreadLocal does not automatically follow async tasks

In the Servlet stack, `SecurityContextHolder`'s default strategy binds context to a thread. When dispatching work to an `ExecutorService`, `@Async`, or another thread, the request context is **not automatically present** as might be expected.

For work that needs the caller's identity, you can:

- Pass **explicitly validated information** as parameters, such as verified internal user ID and tenant.
- Use Spring Security context-propagation helpers like `DelegatingSecurityContextRunnable` or `DelegatingSecurityContextExecutor` when `Authentication` must be forwarded.
- Design queues/background jobs with their own service identity, storing necessary business fields rather than retaining the request context indefinitely.

Do not switch the whole app to `MODE_GLOBAL` to "access the principal everywhere": that can leak authentication across different users. `MODE_INHERITABLETHREADLOCAL` also requires caution with thread pools and task lifecycles.

### 8.2. The principal is not data to trust unconditionally

Values extracted from `Authentication` must come from a trusted verification source and be interpreted in context. Common mistakes:

- Reading a user ID straight from a query parameter/header and placing it into a principal without verification.
- Trusting `sub` without verifying `iss`, `aud`, or the access token's signature.
- Treating email as an immutable system ID, even though emails can change.
- Using `authentication.getName()` as a user ID on a Client Credentials token endpoint call.
- Writing entire JWTs, client credentials, authorization codes, credentials, or full `Authentication` objects to logs.
- Skipping tenant/object-level authorization merely because the principal has a valid role/scope.

### 8.3. Anonymous requests and HTTP errors

Keep three states distinct:

1. **No valid authentication:** typically results in `401 Unauthorized` on APIs requiring authentication, or a redirect to login on browser requests.
2. **Authenticated but lacking permission:** typically results in `403 Forbidden`.
3. **Permitted at the endpoint but lacking record-level access:** the service/authorizer must deny access per policy and never expose unauthorized data.

HTTP behavior may vary with custom error handlers, redirects, or existence-hiding policies, but data-level access control must always be enforced at the appropriate layer.

## 9. Testing SecurityContext and authorization data

### 9.1. Testing MVC/Resource Server policies

With `spring-security-test`, you can mock a principal with scopes in `MockMvc`:

~~~java
mockMvc.perform(get("/api/bookings")
        .with(jwt().jwt(jwt -> jwt.subject("user-123"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_booking.read")
            )))
    .andExpect(status().isOk());
~~~

This test verifies **endpoint mapping + authorization** when an appropriate `Authentication` is present. It **does not prove** that a real JWT has a valid signature/issuer/audience, because `jwt()` in `spring-security-test` creates a mock `Authentication` rather than running signature verification.

Also test the symmetric negative cases:

- Missing `jwt()` → authenticated request must be rejected.
- Mock JWT without `SCOPE_booking.read` → booking read request is rejected.
- Valid scope but booking belongs to a different user/tenant → business authorization denies it.
- Unmapped issuer, subject, or tenant → never confuse with another user's permissions.

### 9.2. Testing the Authorization Server

Key test cases:

| Context | What to verify |
| --- | --- |
| Unauthenticated call to authorization endpoint | AS redirects to login or returns appropriate protocol response; no code issued to unauthenticated user |
| Successful login then returning to authorization endpoint | New context restores the right Resource Owner from session |
| Invalid client or redirect URI | AS rejects; never relies on user principal to skip client checks |
| Consent grants only a subset of scopes | `OAuth2Authorization` stores the exact `authorizedScopes` |
| Token endpoint with valid client + valid authorization code | AS matches the persisted grant and authenticates the client properly |
| Token endpoint with another client or wrong `code_verifier` | No access token issued |
| Client Credentials | Principal/grant involves the client without a logged-in user |
| OIDC UserInfo with invalid/missing access token | Does not leak user claims |

In integration tests, use a real application context and an authorization store suited to the test goal. Tests relying solely on `@WithMockUser` exercise part of Spring Security authorization, yet **do not thoroughly test** login, OAuth2 grants, PKCE, token signatures, or session persistence.

### 9.3. Using logs for diagnosis without leaking secrets

For a denied request, diagnose in sequence:

1. Which **SecurityFilterChain** did the request match? Were AS and login/API chains mixed up?
2. Where did the filter obtain authentication info: session cookie, client credentials, or Bearer token?
3. What is the actual `Authentication` class? Does `getName()` denote a user or a client?
4. Which authorities were created/mapped? Do `ROLE_`/`SCOPE_` prefixes match policy?
5. Did authorization fail at the endpoint, method, or business-rule layer?
6. Were tokens, consents, and authorization codes saved/restored per the right configuration?

Log only minimal metadata such as request ID, chain name, endpoint, authentication type, rule name, and error code; never log raw Bearer tokens, client secrets, passwords, authorization codes, or unnecessary private claims.

## 10. Common architectural mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Treating `SecurityContextHolder` as a system-wide user store | Mixed-up requests, identity leaks across threads | Let Spring Security manage request lifecycle; use repositories/sessions or tokens for persistence |
| Assuming `getPrincipal()` is always `UserDetails` | `ClassCastException`, confusing Client with User | Check `Authentication` type and endpoint context |
| Assuming the token endpoint still holds the user principal from login | Wrong subject, broken code/claim handling | Use the grant model persisted via `OAuth2AuthorizationService` |
| Equating `OAuth2Authorization` with `SecurityContext` | Flawed state and persistence design | Keep request context separate from authorization records |
| Allowing access on `isAuthenticated()==true` alone | Anonymous users can slip past manual checks | Use `authenticated()` and standard Spring Security policies |
| Checking only scope without checking booking owner | Accessing others' data (BOLA/IDOR) | Enforce object-level access in the service layer |
| Not saving context after custom authentication | Next request loses login | Call `SecurityContextRepository.saveContext(...)` when cross-request persistence is needed |
| Using ThreadLocal principal in uncontrolled async tasks | Null/wrong principal or leaks across thread pool | Pass validated identity or use delegating security contexts with proper lifecycle |
| Trusting parsed JWT claims without verification | May accept forged or wrong-audience tokens | Validate tokens per specs and Resource Server policy |

## 11. Self-check questions

**Question 1.** Why can the same user have a different `SecurityContext` on two consecutive requests?

**Answer:** Each request has its own context lifecycle. Context may be restored from a session or populated from a token, but there is no continuous global ThreadLocal shared across all requests.

**Question 2.** Do `GET /oauth2/authorize` and `POST /oauth2/token` always have the same `principal`?

**Answer:** No. The authorization endpoint typically involves the Resource Owner; the token endpoint authenticates the client and matches the persisted grant. The current principal may represent the client.

**Question 3.** What is `OAuth2AuthorizationService` for if `SecurityContextHolder` already holds the user?

**Answer:** It persists authorization grants, tokens/codes, and metadata across multiple requests and potentially across sessions. The context holds the current request's `Authentication`, not grant state.

**Question 4.** If a JWT is validated and has `SCOPE_booking.read`, can it read every booking?

**Answer:** No. The Resource Server must enforce audience, scope, and per-record ownership/tenant permissions according to policy.

**Question 5.** Do `@WithMockUser` or `jwt()` in MockMvc prove production JWT signatures are valid?

**Answer:** No. They assist in testing rules against a mocked `Authentication`. You need integration tests verifying real tokens/metadata/keys to prove end-to-end protocol behavior.

**Question 6.** When writing a custom login controller where the user must stay logged in on the next request, is `SecurityContextHolder.setContext(...)` alone sufficient?

**Answer:** Not necessarily. Under explicit-save mechanisms, you must save to `SecurityContextRepository` per configuration; standard login filters handle this within their own flows.

## 12. Conclusion and references

For every request, answer in order: **which chain did the request enter; which mechanism created `Authentication`; is the current principal a user or a client; what do the authorities mean; and which rule decides access?** When the request hits the Authorization Server, also ask **which grant and consent were persisted**, because `OAuth2Authorization` is not `SecurityContext`.

In Spring Boot/Spring Security and Spring Authorization Server, distinguishing these layers lets you accurately implement, test, and operate login, consent, authorization codes, the token endpoint, OIDC UserInfo, and Resource Servers without conflating user login sessions with token grant state.

Official documentation to verify APIs for your exact project version:

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)

Examples are based on Spring Security Servlet concepts and the Spring Authorization Server 1.x line; if your application uses a Spring Security generation with integrated Authorization Server support, verify classes, APIs, and packages against that specific version's documentation.
