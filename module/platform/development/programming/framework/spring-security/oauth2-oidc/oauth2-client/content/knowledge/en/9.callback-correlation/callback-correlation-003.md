# 9.3. Binding the Callback to Saved State, Nonce, and PKCE Verifier

## 1. The Problem: Does the Callback Truly Belong to a Login Initiated by the Application?

In a **Spring Security OAuth 2.0/OIDC Client** application, logging in with Authorization Code does not happen within a single HTTP request. The application builds an **authorization request**, sends the browser to the Authorization Server/OpenID Provider, and then receives a **callback** containing an authorization code or an error. Between those two browser hits to the application, many steps may occur: the user enters a password, completes MFA, selects an account, or grants consent.

The critical security question is:

> **How does the application know the callback just received is the result of the exact authorization request it initiated, and that the tokens received belong to that same transaction?**

Three mechanisms complement one another:

1. **`state`:** helps the application link the **authorization response on the callback** to the saved **authorization request** and defend against redirect flow forgery.
2. **OIDC `nonce`:** if the application sent a nonce in an OIDC authentication request, the application must bind the received **ID Token** to the nonce value of the **initial request**.
3. **PKCE `code_verifier`:** the application holds a random secret *per authorization request*; the Authorization Server only allows exchanging the authorization code for tokens when `code_verifier` matches the `code_challenge` bound to the code.

These are three checks at **different points** in the flow. You should not treat `state`, `nonce`, and `code_verifier` as three names for the same string, nor think checking one is enough to replace the other two.

**Lesson scope:** OAuth2 Client using Authorization Code, especially **OAuth2 Login/OIDC Login** in Spring Security Servlet and WebFlux. An application using only `client_credentials` to call APIs has no browser callback, so it has no `state`/nonce/PKCE lifecycle of this kind.

## 2. Sequence and Checkpoints

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Security OAuth2 Client
    participant R as Request repository / Session
    participant P as Authorization Server / OIDC Provider

    B->>C: GET /oauth2/authorization/corporate
    C->>C: Create state, PKCE verifier/challenge, OIDC nonce (if used)
    C->>R: Save OAuth2AuthorizationRequest and correlation data
    C-->>B: 302 Location: /authorize?...&state=...&code_challenge=...&nonce=...
    B->>P: GET Authorization Endpoint
    P->>P: Authenticate user / consent
    P-->>B: 302 redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/corporate?code=...&state=...
    C->>R: Load original request by session/state; single-use
    R-->>C: Saved authorization request
    C->>C: Verify state and request context
    C->>P: POST Token Endpoint: code + code_verifier + client authentication
    P->>P: Verify verifier against received challenge
    P-->>C: Access token, ID Token (OIDC), ...
    C->>C: Verify ID Token; match nonce if sent
    C-->>B: Login succeeded / establish session
~~~

In a sound flow, **never regenerate these random values on callback**. The application must retrieve the data belonging to **that exact prior authorization request**. If the saved data is lost, the callback no longer has sufficient grounds to be trusted.

| Value | Where is it created? | Where is it sent? | Where is it stored? | Who verifies it? |
| --- | --- | --- | --- | --- |
| `state` | OAuth2 Client when initiating the flow | Authorization Request query; provider echoes it on callback | Authorization request repository or protected storage | **OAuth2 Client** upon receiving callback |
| `nonce` | OIDC Client when initiating an auth request with nonce | Authorization Request; provider places `nonce` claim in ID Token per flow | Initial OIDC request data, on client side | **OIDC Client** when verifying ID Token |
| `code_verifier` | OAuth2 Client when applying PKCE | **Token Request**, after callback; not sent in authorization URL | Data attached to authorization request, on client side | **Authorization Server** against stored challenge |
| `code_challenge` | OAuth2 Client computed from `code_verifier` | Authorization Request | Authorization Server bound to authorization code | **Authorization Server** upon receiving verifier |
| Authorization `code` | Authorization Server after user grants consent | Callback to `redirect_uri`, then Token Request | Usually short-lived, single-use | Authorization Server checks code, client, redirect URI, PKCE |
| ID Token | Provider after token exchange in OIDC Code Flow | Token Response via back-channel | Client processes/protects as needed | **OIDC Client** checks signature, issuer, audience, expiration, nonce when present |

The table above reflects the **responsible parties**. Details of whether Spring Security stores the request in the session, stores the PKCE verifier as an attribute, or uses another repository may vary by configuration and version; the invariant principle is that **data needed for correlation must persist from initiation to the exact verification step**.

## 3. `OAuth2AuthorizationRequest`: The Central Context Holder

Spring Security uses `OAuth2AuthorizationRequest` to represent a specific authorization request:

~~~java
org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest
~~~

This object has important properties:

| Getter | Role in callback/correlation |
| --- | --- |
| `getState()` | Random `state` sent to the provider and checked on callback |
| `getClientId()` | Client ID used by the initial request |
| `getRedirectUri()` | Redirect URI selected for the transaction, which must remain consistent during code exchange |
| `getAuthorizationUri()` | Authorization Endpoint used to initiate the flow |
| `getScopes()` | Requested scopes |
| `getAdditionalParameters()` | Extra parameters added to the Authorization Endpoint, such as `code_challenge` or `nonce` if configured |
| `getAttributes()` | **Internal** metadata needed for callback/token exchange, such as the PKCE verifier depending on configuration |
| `getAuthorizationRequestUri()` | Complete URL used to redirect the browser to the provider |

Important distinctions:

- **`additionalParameters`** are the parameters included in the Authorization Request sent to the provider after Spring Security constructs and encodes the URL.
- **`attributes`** are internal data of `OAuth2AuthorizationRequest` and do **not automatically** become URL query parameters.
- **`ClientRegistration`** describes the registered client/protocol configuration, whereas `OAuth2AuthorizationRequest` holds data **specific to a single authorization attempt**, including random values meaningful only within that transaction.

During OAuth2 Login, the application must preserve `OAuth2AuthorizationRequest` (or an equivalent protected dataset) from redirect until callback. If a customizer or custom repository accidentally drops the `attributes` holding the PKCE verifier, token exchange may fail to send the matching verifier even when `state` is still valid.

## 4. Binding the Callback with `state`

### 4.1. What Does `state` Prevent?

Suppose an application has a callback:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

During login, the browser returns:

~~~http
GET /login/oauth2/code/corporate?code=AUTH_CODE&state=RANDOM_STATE HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=...
~~~

If the application simply sees `code` and immediately exchanges it for tokens **without matching against an initial flow**, an attacker could inject a callback from a different transaction into a victim's session. This falls under **login CSRF**, authorization response injection, or login session confusion risks.

`state` enables the client to determine whether the callback belongs to an authorization request initiated in the right context:

1. When starting login, the client generates an **unpredictable** value suitable for correlation.
2. The client saves the authorization request along with this value in a repository bound to the proper context, typically the browser's HTTP session.
3. The client sends `state` in the authorization URL query string.
4. The provider echoes `state` back on the callback per protocol.
5. The client loads the original authorization request and **compares the callback's state value** against the saved state.
6. If no matching request is found, or `state` is missing or mismatched, the client must **reject the callback** rather than guessing and continuing to token exchange.

A long or neatly formatted `state` string provides no security if it is hard-coded or predictable. `state` must be freshly generated per transaction with sufficient entropy.

### 4.2. Why Is Checking State Format Alone Insufficient?

Two values that are both syntactically valid are not enough:

~~~text
Session A saved state:     HJae2...mK1
Callback received state:   hfd99...zQ7
~~~

Even though both are random strings, the callback above must be rejected because they **do not match**. The decisive check is whether the client has a trusted initial authorization request to compare against.

Conversely, if you see a `state` in a callback without finding the original request, never allow the callback by synthesizing a new request using the state from the URL: doing so turns the correlation mechanism into a meaningless check.

### 4.3. Can `state` Be Used to Remember the Post-Login Return Page?

Business requirements often want to return to the original page, such as `/orders/123`. **You should not use the random `state` as an externally supplied redirect URL.**

A common design is to keep the **validated return URL** in the session or protected storage associated with the transaction. After a valid callback, use that internal information to redirect the user to an allowed path.

If an application embeds structured data inside `state`, it must implement integrity protection, replay protection, session/tenant binding, and proper open-redirect handling. Do not invent a custom state mechanism to replace the default without a clear architectural requirement.

## 5. PKCE: Retaining `code_verifier` to Exchange the Right Authorization Code

### 5.1. What Binding Mechanism Does PKCE Add?

**Proof Key for Code Exchange (PKCE, RFC 7636)** ensures an authorization code can only be exchanged for tokens when the party exchanging the code proves it knows the `code_verifier` used to derive `code_challenge` at the start.

With the `S256` method:

~~~text
code_verifier  = random per-transaction value meeting RFC 7636 requirements
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Example given in RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

In the **Authorization Request**:

~~~http
GET /authorize?response_type=code&client_id=portal-web&state=...&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

In the **Token Request**, after callback:

~~~http
POST /token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTH_CODE&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

The HTTP snippet above only illustrates the grant body; **client authentication** must also be applied per client configuration and the Authorization Server contract. Confidential clients may require `client_secret_basic`, `client_secret_post`, private-key JWT, or another method. Never embed secrets in the Authorization URL.

Keep in mind:

- **`code_challenge` appears at the Authorization Endpoint** and is designed to be public.
- **`code_verifier` must not be sent in the Authorization Request**; the client retains it until making the Token Request.
- **The Authorization Server is the party that verifies PKCE** during code exchange. The client does not prove a verifier is right by comparing it locally with the challenge; a successful token response from a compliant server reflects the server's verification.
- Both verifier and challenge must be **bound to the same transaction**. Generating a new verifier on callback will fail to match the original challenge.
- `S256` is the preferred method; do not downgrade to `plain` to work around provider errors without understanding the risks and compatibility implications.

### 5.2. Can PKCE Replace `state`?

You should not drop `state` when using PKCE simply because both help protect the authorization flow.

- **`state`** binds the authorization response on the browser callback to the saved request and initiating session/context.
- **PKCE** binds the authorization code to the verifier held by the client, reducing the impact of code theft/injection.
- Both mechanisms are checked at **different steps** and provide defense in depth.

There are standardized protocol profiles or alternative protections, but in typical Spring Security OAuth2 Login applications, keeping the safe default behavior is the sensible implementation.

### 5.3. When Does Spring Security Add PKCE?

In modern Spring Security versions, the default resolver may automatically apply PKCE for certain clients, notably **public clients** configured with authentication method `none`. For a confidential client where you want to explicitly enable PKCE and the provider supports it, you can customize the resolver.

Servlet example:

~~~java
@Configuration
class LoginSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
            OAuth2AuthorizationRequestCustomizers.withPkce().accept(builder));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

The types in this example belong to Spring Security Servlet: `HttpSecurity`, `SecurityFilterChain`, `ClientRegistrationRepository`, `DefaultOAuth2AuthorizationRequestResolver`, and `OAuth2AuthorizationRequestCustomizers`. `@Bean`/`@Configuration` come from Spring. `import` statements are omitted to focus on the flow.

The `withPkce()` customizer manages adding the challenge/method and internal verifier data per Spring Security's contract. When using it, **do not generate a separate verifier in callback-handling code**. If a provider does not support PKCE or requires a specific policy, decide based on the IdP's metadata/documentation.

## 6. OIDC `nonce`: Binding the ID Token to the Authentication Request

OIDC extends OAuth2 to standardize identity authentication. In the OIDC Code Flow, after the client successfully exchanges the authorization code, the Token Endpoint can return an **ID Token** alongside the access token.

Suppose the Authorization Request sends:

~~~text
response_type=code
scope=openid profile
state=RANDOM_STATE
nonce=RANDOM_NONCE
~~~

The provider issues an ID Token containing the matching claim:

~~~json
{
  "iss": "https://idp.example.com/realms/employees",
  "sub": "248289761001",
  "aud": "portal-web",
  "exp": 1910000000,
  "iat": 1909999700,
  "nonce": "RANDOM_NONCE"
}
~~~

This payload illustrates the claims; **do not use sample timestamps to test real tokens**.

The OIDC Client must verify the ID Token per standard policy, including **signature/trusted keys, issuer, audience, expiration**, and **nonce** if the request sent `nonce`. Additional checks such as `azp` or other policies should be applied when required by the profile/token.

Key distinctions:

- `state` resides in the **authorization response on the callback**.
- `nonce` resides in the **ID Token** issued after token exchange, when `nonce` was sent.
- An ID Token may be a JWT, but **parsing its JSON payload does not mean the token is valid**.
- `nonce` does not replace signature, `iss`, `aud`, `exp`, or other OIDC validation checks.
- Never use an **access token** as an ID Token just because the access token also happens to be a JWT.

### 6.1. How Is Nonce Stored and Matched?

At the authorization request stage, the client must retain enough data to identify the **original nonce of that login attempt**. At the callback stage, after exchanging the code for tokens and performing the appropriate ID Token checks, the client compares the nonce from the token against the expected value.

If a customizer adds `nonce` to the Authorization Request, it must also ensure the OIDC token validation component **is provided the matching expected value**. Simply writing:

~~~java
builder.additionalParameters(params ->
    params.put("nonce", "MY_NONCE"));
~~~

**does not guarantee** the entire nonce lifecycle is securely integrated: without saving/matching the corresponding nonce, that query parameter is merely data sent out without full correlation.

Some implementations may transform how `nonce` is represented when sent versus stored internally; developers should rely on **Spring Security/IdP standard capabilities** or an explicit, consistent mechanism rather than assuming the raw nonce always lives under a self-invented attribute key.

### 6.2. Is Nonce Mandatory in Every OAuth2 Flow?

No. `nonce` is a concept of the **OIDC authentication request**, not a mandatory parameter for every OAuth2 Authorization Code request. In the **OIDC Authorization Code Flow**, `nonce` can be optional depending on the standard case; when the client has sent a nonce, the ID Token must carry the matching nonce and the client must verify it per OIDC requirements.

In other OIDC flows, rules around `nonce` may differ. This lesson focuses on the **Authorization Code callback** of Spring Security OAuth2/OIDC Client and does not assume every flow shares the exact same parameter set.

## 7. Where Correlation Data Is Stored in Spring Security Servlet

### 7.1. Participating Components

A Servlet application using `oauth2Login()` typically coordinates:

| Component | Job |
| --- | --- |
| `ClientRegistrationRepository` | Looks up provider/client configuration by `registrationId` |
| `OAuth2AuthorizationRequestRedirectFilter` | Handles the authorize initiation endpoint and issues the redirect |
| `OAuth2AuthorizationRequestResolver` | Builds the request, including `state` and required parameters |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Saves/loads/removes the authorization request across the redirect phase |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Default common implementation persisting requests via HTTP session |
| `OAuth2LoginAuthenticationFilter` | Receives the callback, coordinates authorization response authentication |
| OAuth2/OIDC authentication provider, token response client | Exchanges code for tokens, completes authentication/validation |
| `SecurityContext` and session storage | Holds Authentication after successful login per web app architecture |

Three types of data are commonly confused:

1. **`ClientRegistration`:** relatively static client configuration; cannot replace the per-login authorization request.
2. **`OAuth2AuthorizationRequest`:** temporary state of a transaction awaiting callback; holds `state`, PKCE, and OIDC data as applicable.
3. **`OAuth2AuthorizedClient`:** data **after** tokens are issued, binding a registration with access token/refresh token. It is not where the app retrieves the original `state` to validate the callback prior to token exchange.

### 7.2. Default Storage via HTTP Session

When the filter initiates authorization, Spring Security can save `OAuth2AuthorizationRequest` in `HttpSessionOAuth2AuthorizationRequestRepository`. The request is retrieved when the callback returns with a matching `state`.

Configuration example illustrating the dependency:

~~~java
@Configuration
class OAuth2SessionCorrelationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var requestRepository =
            new HttpSessionOAuth2AuthorizationRequestRepository();

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(requestRepository)));

        return http.build();
    }
}
~~~

This snippet simply configures the session repository explicitly, equivalent to the common default choice; **you do not need to declare it manually** in every application. Its main value here is making explicit **where the request is stored between the two HTTP turns**.

Never store PKCE verifiers or raw nonces in an application-wide `static` variable. When multiple users log in concurrently, shared values get overwritten and can cause cross-transaction mix-ups. Nor should you place them in an arbitrarily modifiable cookie without proper integrity/confidentiality protections.

### 7.3. Between the Two Browser Turns, the Session Must Reconnect

Example:

~~~text
Turn 1: GET /oauth2/authorization/corporate
    Browser receives Set-Cookie: JSESSIONID=abc...; Secure; HttpOnly; ...

Turn 2: GET /login/oauth2/code/corporate?code=...&state=...
    Browser sends Cookie: JSESSIONID=abc...

Backend uses the matching session to find the original authorization request.
~~~

Common failures when the session does not reconnect:

- `Secure` cookie affected by HTTPS termination or wrong public scheme configuration.
- `SameSite` incompatible with the callback's redirect/HTTP method; for instance, `form_post` callbacks have different cookie behavior than top-level GET.
- Cookie domain/path does not cover the callback.
- Reverse proxy or load balancer routes the callback to an instance that cannot access the saved session.
- Session expires while the user is entering a password/MFA.
- Browser clears, blocks, or partitions cookies due to browser policy, profile, or storage partitioning.
- Creating a new authorization request mid-flow causes pending login data to be replaced depending on repository behavior.

Some applications store sessions in **Spring Session + Redis** or shared storage so multiple instances can read them. In such setups, protect the session and configure lifetimes compatible with the login lifecycle. A shared store must still isolate sessions per user/browser; never use the same request-storage key/namespace across all sessions.

### 7.4. Multiple Concurrent Login Tabs

Suppose a user opens two tabs and starts two flows:

~~~text
Tab A → state=A1, verifier=VA, nonce=NA
Tab B → state=B2, verifier=VB, nonce=NB
~~~

If the repository only holds **one pending authorization request per session**, request B may overwrite request A. When Tab A's callback arrives, Spring no longer has the original request and login fails.

This differs from an attack: a state mismatch can arise from legitimate concurrency. When multiple concurrent flows must be supported, a custom repository must manage multiple entries using **unpredictable state keys** bound to the appropriate session/tenant, enforce TTLs, and ensure proper entry deletion. Never fix this error by skipping `state` comparison.

## 8. Where Correlation Data Is Stored in WebFlux

WebFlux uses corresponding reactive interfaces/filters:

| Servlet | WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizationRequestRedirectFilter` | `OAuth2AuthorizationRequestRedirectWebFilter` |
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |

Basic WebFlux example:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveLoginSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/static/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

In WebFlux, the authorization request can be stored in **WebSession** via `WebSessionOAuth2ServerAuthorizationRequestRepository` or an application-provided implementation. You must still guarantee **the same transaction from authorization redirect to callback**.

If customizing a WebFlux repository, use APIs operating on `ServerWebExchange` and returning appropriate `Mono` types. Avoid blocking code (`.block()`, unisolated synchronous JDBC) on the reactive event loop.

WebFlux and Servlet differ in filter and repository types, but the security semantics are identical: **from the callback you must locate the original request; from the original request you must obtain the exact state and data to complete token/ID Token validation**.

## 9. Step-by-Step: What Must Happen During the Callback?

From the application's perspective, a callback follows this logical sequence. Spring Security executes these steps inside its corresponding filters/providers; you do not need to write all of them by hand when using the defaults.

### Step 1 — Receive the Authorization Response

Typically one of two forms:

~~~http
GET /login/oauth2/code/corporate?code=AUTH_CODE&state=S123 HTTP/1.1
~~~

or:

~~~http
GET /login/oauth2/code/corporate?error=access_denied&state=S123 HTTP/1.1
~~~

`code` is a short-lived, single-use credential for requesting tokens. Never log the full code.

### Step 2 — Find the Saved Authorization Request

Based on the session and `state`/callback context as implemented by the repository, Spring Security must locate the initial `OAuth2AuthorizationRequest`. If missing, an error such as `authorization_request_not_found` or an equivalent correlation error may occur depending on configuration/version.

**Do not** accept a callback merely because the query has `code` or because a client registration exists. `ClientRegistration` is static configuration and does not prove the browser initiated the transaction.

### Step 3 — Verify `state` and Identify the Transaction's Client/Provider

Spring Security must bind the response to **the exact initial request**, rather than using an arbitrary registration solely based on untrusted data supplied by the callback. If `state` does not match or the request is missing, reject the callback.

Complex deployments using multiple Authorization Servers/issuers must also defend against **authorization-server mix-up**: responses must be bound to the provider/client the request targeted, and when required by protocol/config, the authorization response's issuer or an equivalent binding must be verified. This is an additional layer of defense, not a replacement for `state`.

### Step 4 — Token Exchange with the Saved PKCE Verifier

Once the callback passes request correlation, the backend sends a Token Request to the corresponding Authorization Server. With PKCE, the request must send the `code_verifier` **generated at initiation**, never synthesizing a new verifier.

Fundamentally:

~~~text
POST {token-uri}
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
code=<code-from-callback>
redirect_uri=<same-redirect-uri-when-required>
code_verifier=<original-verifier>
+ client authentication per client registration
~~~

The provider validates the authorization code, client, redirect URI, validity/single-use, and PKCE when present; failures may surface as `invalid_grant` or another specific error code.

### Step 5 — Verify Tokens, Including OIDC Nonce if Sent

For OIDC Login, Spring Security verifies that the ID Token was issued by the right provider and for the right client. If the authorization request included `nonce`, the expected value must be matched per OIDC; a mismatch must fail authentication.

Never use `nonce` to validate an API access token: `nonce` belongs to the OIDC ID Token contract, whereas access tokens are verified by the Resource Server for issuer/audience/scope/signature or via introspection as appropriate.

### Step 6 — Complete Authentication and Handle Single-Use Data

When all required steps succeed, the application establishes `Authentication` and may store tokens in `OAuth2AuthorizedClient`. Pending authorization request data should no longer be reusable as an incomplete transaction.

On failure, the application should return an error/error redirect as configured and avoid allowing an already processed request to be accepted again unchecked. Request deletion mechanics must align with the repository lifecycle and retry requirements per application design.

## 10. Baseline Spring Boot OIDC Login Configuration

Example for a Spring MVC/Servlet application:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corp-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp-oidc:
            issuer-uri: https://idp.example.com/realms/employees
~~~

~~~java
@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login-error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Login is initiated at:

~~~text
https://portal.example.com/oauth2/authorization/corporate
~~~

Spring Security OAuth2 Login's default callback is typically:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

The callback must match the URI registered with the IdP. When using `{baseUrl}` behind a reverse proxy, the system must securely recognize the external hostname and HTTPS scheme; the browser must send back the session cookie for the matching domain/path.

Spring Security handles creating/saving the authorization request and correlating the callback by default. The application **does not need to write a custom `/login/oauth2/code/corporate` controller just to read `state` or `code`**. Intercepting the callback with a custom controller easily bypasses state, PKCE, and OIDC token validation.

## 11. Customizing the Authorization Request While Preserving Correlation

### 11.1. Adding a Provider Parameter Without Losing PKCE/State

For example, adding `prompt=select_account` for an OIDC provider while intentionally enabling PKCE:

~~~java
@Configuration
class CustomLoginSecurity {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            clientRegistrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder -> {
            OAuth2AuthorizationRequestCustomizers.withPkce().accept(builder);

            builder.additionalParameters(parameters ->
                parameters.put("prompt", "select_account"));
        });

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

`DefaultOAuth2AuthorizationRequestResolver` still constructs the flow, including `state`, client registration, and core parameters. The PKCE customizer lets Spring Security store the verifier in the manner used by token exchange. `prompt` is an extension parameter for OIDC providers that support it.

**Do not do the following inside a customizer:**

- Overwrite `state` with a constant or a value taken directly from the browser request.
- Add `code_verifier` to the authorization URL query string instead of `code_challenge`.
- Drop `attributes` containing internal metadata when rebuilding `OAuth2AuthorizationRequest`.
- Arbitrarily alter `redirect_uri` to a client-supplied URI or another provider.
- Modify `nonce` without ensuring it is stored and matched at the ID Token verification step.

### 11.2. Why Are `attributes` Easily Forgotten When Copying a Request?

A developer might take the default request and build another containing only `clientId`, `redirectUri`, `scopes`, and `state`. The redirect URL looks fine, yet the original request's internal data may be lost: for example, the PKCE verifier is no longer present for the Token Request.

If you truly need to copy/modify a request, understand how the builder preserves data:

~~~java
OAuth2AuthorizationRequest updated =
    OAuth2AuthorizationRequest.from(original)
        .additionalParameters(params -> params.put("prompt", "login"))
        .build();
~~~

This illustrates modifying from **`original`** to preserve the request's original fields, rather than building an entirely new request missing other attributes. The `original` object must originate from Spring Security's valid request-creation flow. Never use this pattern to fabricate a callback/request when `state` does not match.

### 11.3. Customizing the Repository: Non-Negotiable Responsibilities

When replacing `HttpSessionOAuth2AuthorizationRequestRepository` with custom storage, ensure you:

- Store the **complete correlation object/request** required for `state`, PKCE, and OIDC.
- Bind records to the **right browser session**, initiator, or an equivalent secure mechanism.
- Prevent other users/tenants from reading or completing a flow.
- Keep `state` as an unpredictable random key; enforce a TTL and single-use deletion/consumption.
- Have a strategy for **multiple tabs** or multiple pending logins.
- Protect sensitive data, especially the PKCE verifier and any security-sensitive internal metadata.
- Operate correctly across multi-instance deployments and session rotation/expiration.
- Never store tokens/credentials in browser cookies or URLs without proper encryption, authentication, replay protection, and risk review.

**Cookie-based stateless repositories:** feasible in certain architectures, but never treat a cookie as safe merely because it has `HttpOnly`. If a cookie holds a verifier or correlation data, you must protect integrity, confidentiality where needed, TTL, scope, replay, `SameSite`, and cookie size limits. Server-side storage is typically easier to manage in traditional web applications.

## 12. Common Correlation Errors and Root-Cause Identification

| Symptom | Suspected stage | Common cause | What to check |
| --- | --- | --- | --- |
| `authorization_request_not_found` | Loading initial request | Lost session, callback hit another instance, request expired/deleted, repository did not retain request | Cookies, session store, instance routing, TTL, callback path |
| `invalid_state_parameter` or state mismatch | State comparison | Callback does not belong to flow, session overwritten, multiple tabs opened, request tampered with | Hidden flow ID correlation, session, and number of login initiations |
| Callback has only `error=access_denied` | Authorization Endpoint | User denied consent or IdP policy disallowed access | Inspect protocol error response; do not attempt token exchange |
| Token Endpoint returns `invalid_grant` | Code/token request | Code expired/reused, different redirect URI, wrong PKCE, clock skew | Verify matching original request, verifier, code lifecycle |
| Provider reports `invalid_request` when PKCE is present | Authorization Endpoint | Provider does not support/enable the challenge method or invalid parameter | Check IdP configuration and PKCE customization |
| ID Token validation fails due to nonce | OIDC verification | Nonce mismatch, original request lost, custom nonce not saved/checked properly | Check nonce generation/storage flow and validator |
| Login succeeds but wrong account expected | Session/login binding | Improper binding of state/provider, login CSRF, or flow mix-up; or user chose another account | Verify correlation and verified identity from ID Token |
| Fails only after multi-instance deployment | Session/storage | Request data resides only in one instance's memory | Shared session store/appropriate routing design |
| Fails only after reverse proxy change | Cookie/redirect | Wrong hostname/scheme/path, `SameSite`/`Secure`, headers, callback URL | Observe browser redirects and cookies along the new route |
| Intermittent failures when opening multiple SSO tabs | Concurrency | Repository holds only one pending request or request got replaced | Design safe multi-state storage per session if needed |
| Request had `code_challenge` but token exchange lacks `code_verifier` | Request attributes/token response client | Customizer/copy dropped verifier or token client failed to send it | Inspect builder, authorization-request storage, token response client |
| `401`/`403` when calling API after login | Post-callback stage | Invalid access token/missing scope or API denied permission | Inspect token used for Resource Server; do not tamper with state |

A flow can fail due to **storage context issues** even when the provider is healthy. Thus you must distinguish **request correlation** from **token issuance** and **API authorization**.

### 12.1. Separating Legitimate Errors from Attack Behavior

A state mismatch is a signal to reject the callback, though not every occurrence indicates an attack. It can result from:

- Browser back/forward navigation or repeated login clicks.
- Two tabs initiating SSO concurrently.
- Session expiration while taking too long on MFA.
- Cookies/sessions dropped across a proxy during callback.
- Inconsistent initiation/callback URI configuration.
- Request already consumed on an earlier callback and then replayed.

Regardless of the cause, **the safe behavior remains rejecting callbacks without a valid request**, then offering a way to re-initiate login. Never disable validation just to reduce user-facing errors.

### 12.2. Why Is Retrying an Old Callback Not a Recovery Method?

Authorization codes are typically **short-lived and single-use**; authorization requests in the repository also have a single-use lifecycle. Refreshing the callback URL can lead to `invalid_grant` or a missing authorization request, even when the first attempt already processed.

When a retry is needed, the application should **initiate a fresh authorization request** via the login initiation endpoint. Never reuse a code, state, or PKCE verifier from an old flow.

## 13. Observing and Testing Bindings Without Exposing Secrets

### 13.1. Properly Observing a Flow in Development

You can verify that the login initiation endpoint returns a valid `302 Location`:

~~~bash
curl -i --max-redirs 0 \
  http://localhost:8080/oauth2/authorization/corporate
~~~

The result may include:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.com/oauth2/authorize?response_type=code&client_id=portal-web&state=<redacted>&code_challenge=<redacted>&code_challenge_method=S256
Set-Cookie: JSESSIONID=<redacted>; HttpOnly
~~~

This is a **redacted illustration**, not a literal request you can send verbatim to a provider. Depending on design, the application may not send `nonce` or may use a different cookie/session mechanism. The next step is verifying that the callback uses the same session and whether the framework loads the saved request.

Never log or share raw `code`, `state`, `nonce`, `code_verifier`, tokens, session cookies, or client secrets.

### 13.2. Security-Layer Test Cases

| Test case | Expected result |
| --- | --- |
| Valid authorization request and callback with same session/state | Framework proceeds to token exchange and authentication |
| Callback missing state when flow requires state | Rejected |
| State from flow A sent inside flow B's session | Rejected |
| Callback with fabricated/random unsaved state | Rejected |
| Callback replayed after processing | Does not re-establish authentication from used code/request |
| Attempt to use code from flow A with verifier from flow B | Token Endpoint rejects |
| PKCE challenge modified while original verifier kept | Token Endpoint rejects |
| ID Token nonce mismatch when request sent nonce | OIDC Client rejects authentication |
| Expired ID Token, wrong issuer/audience, or invalid signature | OIDC Client rejects authentication |
| Session cleared before callback | Rejects callback due to missing matching request |
| Multiple login tabs in the same session | Behaves per repository design; if multiple pending requests are unsupported, context-less flow is safely rejected |
| Token request missing code verifier when authorization request had PKCE | Token Endpoint rejects |
| Callback configuration altered mid-flow | Detected or rejected per redirect URI/client binding |

Never claim "tests passed" merely because a single happy-path login succeeded. Negative test cases matter because they verify that mis-correlated callbacks **are blocked at the right place**.

### 13.3. Recording Per-Transaction Telemetry

When incident observability is needed, log non-sensitive metadata:

- `authorization_started` and `callback_received` milestones with an **internal correlation ID separate from `state`**.
- `registrationId`, grant type, endpoint hostname (do not log full URL query strings).
- Name of the failing step: request load, state comparison, token exchange, ID Token validation.
- Sanitized failure reason: session expired, provider error, timeout, request not found.

In production, avoid enabling DEBUG/TRACE across the entire HTTP stack if there is any risk of logging `Authorization` headers or queries/bodies containing tokens, codes, verifiers, and cookies. Redaction should also be enforced at reverse proxies, gateways, and APMs.

## 14. Misconceptions to Avoid

**“The callback has `state`, so the callback is valid.”** No. It must be compared against the state of an authorization request initiated and stored by the client in the proper context.

**“PKCE verifier and challenge are the same value.”** No. With `S256`, the challenge is a derived value. The verifier is the secret kept by the client to send in the token request.

**“Since PKCE is used, the verifier can be stored in the authorization URL.”** No. Doing so exposes the verifier on the front channel, defeating PKCE's protection against authorization code interception.

**“Nonce can replace state since both are random strings.”** No. `nonce` binds the **ID Token** at the OIDC verification step, whereas `state` binds the **authorization response** prior to token exchange.

**“On each callback, just generate a new verifier and recompute the challenge.”** No. The Authorization Server already bound the code to the prior challenge; the **original verifier** must be sent.

**“Manually adding a nonce query parameter guarantees Spring Security verifies it.”** You cannot assume that. You must ensure the original nonce is saved/mapped into the actual OIDC validation pipeline in your implementation.

**“ClientRegistration alone is enough to process the callback.”** No. `ClientRegistration` is long-lived configuration; the callback also requires the transaction-specific authorization request and correlation data.

**“The callback returning `code` means the user logged in successfully.”** No. State matching, successful token exchange, OIDC ID Token validation where applicable, and all mandatory checks are still required.

**“If the session is lost, we can skip the state check so users don't have to log in again.”** No. When the session/authorization request is lost, a new flow must be initiated; never weaken security protections just to work around operational errors.

## 15. Practical Scenarios

### Scenario A — Opening Two Login Tabs

A user clicks SSO in Tab A, then opens Tab B and clicks SSO again. Tab A's callback reports a missing authorization request.

**Analysis:** The two flows have different states, verifiers, and possibly nonces. If the repository stores only one pending request per session, request B may replace request A. Decide whether concurrent login flows should be supported; if so, implement per-state storage with TTL and safe single-use consumption. Never accept a mismatched state.

### Scenario B — Token Endpoint Returns `invalid_grant` Despite Matching State

The callback matches `state` correctly, yet exchanging the authorization code fails. A developer reconstructed `OAuth2AuthorizationRequest` manually, copying only `state` and client ID while omitting `attributes`.

**Analysis:** The original PKCE verifier may have been lost. The token request lacks the verifier or sends a wrong one, so the Authorization Server rejects it. Keep the original request and use standard customizers to add parameters instead of rebuilding the object, while also checking redirect URI and code expiration.

### Scenario C — ID Token Has Valid Signature but Nonce Mismatch

The IdP returns a properly signed ID Token with matching issuer/audience, yet the `nonce` claim does not match the nonce tied to the authorization request.

**Analysis:** If the client sent a nonce, **it must reject the ID Token/login**. A valid signature only proves the token came from a trusted issuer; a nonce mismatch indicates the token is not properly bound to the expected authentication request or the flow was mishandled.

### Scenario D — Deployed Behind Ingress, Callback Loses Session

Local login works, while production intermittently reports a missing authorization request on callback. The browser is redirected back to the public hostname, yet the session cookie is not sent to the callback.

**Analysis:** Inspect `Secure`, `SameSite`, cookie domain/path, forwarded headers, redirect URI, HTTPS termination, session store, and multi-instance routing. The fix is repairing session/flow persistence, **not removing state matching**.

### Scenario E — A Service Using Only `client_credentials`

A backend runs a nightly job to request a service token and call a Reporting API. A developer wants to add `state`, `nonce`, and `code_verifier` to the configuration for "extra security."

**Analysis:** `client_credentials` has no browser authorization redirect/callback like authorization code. The three correlation values in this lesson do not apply to that flow. Focus on protecting client credentials, the Token Endpoint, TLS, and using access tokens with proper audience/scopes.

## 16. Review Questions

**1. On callback, can the client trust the `state` value sent by the browser without looking up the saved authorization request?**

No. `state` must be bound to and matched against **a prior request created by the client itself** within a secure context.

**2. Who verifies the PKCE `code_verifier`?**

The **Authorization Server** verifies the verifier at the Token Endpoint by computing the challenge and comparing it against the challenge originally bound to the authorization code.

**3. Why is `code_verifier` never sent in the authorization URL?**

The verifier is the secret proving the right to exchange the code. Putting it on the front channel defeats PKCE's protection against authorization code theft.

**4. If an OIDC authorization request sent a nonce but the ID Token lacks the matching nonce, how should it be handled?**

The OIDC Client must **reject** the ID Token/login because it fails to satisfy the authentication request's nonce binding.

**5. Besides an attack, what can cause a callback to lose `OAuth2AuthorizationRequest`?**

Session expiration, cookies dropped across a proxy, multiple tabs overwriting the pending request, the request already being consumed/single-use, or instances not sharing a unified session store.

**6. Does `OAuth2AuthorizedClient` replace `AuthorizationRequestRepository` for checking state?**

No. The authorized client holds tokens **after authorization is granted**, whereas the request repository holds **pre-callback** data for correlation and token exchange.

**7. How can PKCE be added in Servlet while still using Spring Security's standard flow?**

You can use `DefaultOAuth2AuthorizationRequestResolver` with `OAuth2AuthorizationRequestCustomizers.withPkce()`, then attach the resolver to `oauth2Login(...).authorizationEndpoint(...)`. Check your exact version/components and provider PKCE support.

**8. If the callback is valid but the ID Token has the wrong issuer, should login succeed because the nonce matches?**

No. **Issuer, audience, signature, expiration**, and nonce when present are independent constraints. A matching nonce does not compensate for an untrusted ID Token.

## 17. Official References

- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — OAuth 2.0 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security Reference — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html)
- [Spring Security API — HttpSessionOAuth2AuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Authentication Request and ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)

**Key takeaway:** A secure callback must belong to **an authorization request that the application created and still holds**. `state` binds the **callback** to the original request; `code_verifier` binds the **authorization code** to the client that created the challenge; `nonce` binds the **OIDC ID Token** to the initiating authentication request. In Spring Security, preserve the default correlation mechanisms, protect your session/repository, and customize only while keeping the full lifecycle of each value intact.
