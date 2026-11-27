# 3.8. State, Nonce, and PKCE in the Login Flow

When a Spring Security application uses **OpenID Connect (OIDC)** to log users in via an identity provider, the browser is typically redirected from the application to the OpenID Provider (OP), and then back to the application with an **authorization code**. An important question arises: how does the application know that this callback belongs to a login request it initiated itself, that the received ID Token corresponds to that exact login attempt, and that the authorization code cannot be redeemed by another party?

Three complementary mechanisms answer that question:

- **`state`**: binds the **authorization response** to the original **authorization request**; it helps protect the redirect flow against CSRF / login CSRF.
- **`nonce`**: binds the **ID Token** to the **specific OIDC authentication request**, helping detect ID Token replay or substitution in applicable attack scenarios.
- **PKCE (Proof Key for Code Exchange)**: requires the party exchanging the **authorization code** at the token endpoint to prove possession of the **`code_verifier`** bound to the authorization request.

None of these three mechanisms replaces the other two. This lesson places them inside the **OIDC Authorization Code Flow** of a Spring Boot web application using Spring Security and explains how they travel across HTTP redirects, sessions, and the back-channel.

## 1. Why Are Three Layers of Protection Needed?

Suppose `https://app.example.com` provides a "Log in" button. Clicking it redirects the user to the OP `https://login.example.com`. The OP authenticates the user and redirects back to the callback:

```http
GET /login/oauth2/code/academy?code=AUTHORIZATION_CODE&state=STATE_RETURNED HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_ID
```

The risks involved are distinct:

| Risk | Problem to Solve | Directly Related Mechanism |
| --- | --- | --- |
| Forged callback or callback from an uninitiated login attempt | The browser is sent to the callback endpoint with a response initiated by another party | `state`, matched against the saved authorization request |
| ID Token replayed or swapped during authentication | The client receives an ID Token with a valid signature that does not match the current authentication request | `nonce`, checked inside the ID Token alongside other OIDC checks |
| Authorization code intercepted / stolen | A party holding the code attempts to call the token endpoint to obtain tokens | PKCE: `code_challenge` + `code_verifier` |
| Token issued by the wrong issuer or for the wrong client | Valid signature but wrong provenance or intended recipient | Validating `iss`, `aud`, signing keys, and provider bindings |
| Another website exploits a browser holding cookies to send state-changing requests | **Web application CSRF** outside the OIDC callback | CSRF tokens for state-changing requests, cookie and origin controls |

That final point is critical: **`state` protects message correlation across the OAuth2/OIDC flow**, whereas **Spring Security's CSRF protection** protects business requests using session cookies. Never disable `csrf()` simply because `state` is present.

## 2. Full Authorization Code Flow with `state`, `nonce`, and PKCE

In this example, the **Spring application is the OAuth 2.0 Client / OIDC Relying Party**, the OP is both the Authorization Server and ID Token issuer, and the browser is the user agent. The flow runs over HTTPS on public connections.

```mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Security OIDC Client
    participant P as OpenID Provider
    B->>C: GET /oauth2/authorization/academy
    Note over C: Generate state S, nonce N, verifier V<br/>challenge Cc = BASE64URL(SHA256(V))<br/>Store S, N, V with the login request
    C-->>B: 302 Location: OP /authorize?...<br/>state=S, nonce=N, code_challenge=Cc
    B->>P: GET /authorize?... over HTTPS
    P->>B: Authenticate user and consent if needed
    P-->>B: 302 /login/oauth2/code/academy?code=CODE&state=S
    B->>C: GET callback + session cookie
    Note over C: Load saved request; verify state
    C->>P: POST /token: code=CODE, code_verifier=V<br/>+ client authentication when applicable
    Note over P: Compare challenge derived from V<br/>against challenge bound to CODE
    P-->>C: access_token + id_token (+ other fields)
    Note over C: Validate ID Token: signature, iss, aud,<br/>expiration, nonce=N, and OIDC rules
    C-->>B: Create app login session; redirect to landing page
    B->>C: GET /account + session cookie
    C-->>B: Content for authenticated user
```

The verification order matters:

1. Before redirecting, the client **generates and stores** the data belonging to a single login attempt.
2. When the browser returns, the client **checks `state`** and locates the exact original authorization request.
3. When the backend exchanges the code for tokens, the OP **verifies PKCE**.
4. When the client receives the ID Token, the client **validates the token and `nonce`**.
5. Only after authentication succeeds does Spring Security establish `Authentication`/`SecurityContext` for the user.

`state` and `nonce` appear on the browser-facing authorization request, whereas **`code_verifier` must be retained by the client to send in the token request**, never included in the redirect URL to the OP.

## 3. `state`: Binding the Callback to the Original Login Request

### 3.1. How Does `state` Work?

`state` is a value generated by the client for an authorization request. The client includes it in the redirect to the OP while keeping matching state on the application side.

Example request to the OP (abbreviated):

```http
GET /authorize?response_type=code
    &client_id=academy-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
    &scope=openid%20profile
    &state=RANDOM_STATE
    &nonce=RANDOM_NONCE
    &code_challenge=CODE_CHALLENGE
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.com
```

After authentication, the OP returns:

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/academy?code=SHORT_LIVED_CODE&state=RANDOM_STATE
```

The application must not merely check "whether `state` is present in the callback". It must know **which `state` was issued for the pending authorization request**, compare it exactly, and consume the correlation record once. If `state` is wrong, missing, or no matching request exists, **the authentication flow must be rejected**.

An example of **login CSRF**: an attacker generates an authorization response tied to the attacker's own account and forces the victim's browser to submit that response to the application. If the client accepts the code and creates a session without binding the response to the victim's own request, the victim can be silently logged into an attacker-controlled account. `state` bound to the browser/session that initiated the flow prevents this attack.

### 3.2. Generating, Storing, Checking, and Consuming `state`

A proper design requires:

- **Unpredictable:** use a cryptographically secure random generator; never use timestamps, incrementing numbers, usernames, or fixed strings.
- **Fresh per authorization request:** never reuse the same `state` across login attempts.
- **Bound to the browser/client context:** store an authorization request record server-side and identify that context via a protected session cookie or equivalent mechanism.
- **Short-lived:** pending callback requests should not remain valid indefinitely.
- **Matched and consumed once:** clean up temporary state upon success or failure; never allow a response to be replayed to log in again.

`state` is **not an access permission**, **not an access token**, and does not prove user identity. Its value appears in URLs, so it must not be treated as a secret usable in place of a token. Its protection comes from unpredictability and **comparison against client-stored login state**.

If you need to redirect the user back to the page requested before login, use the framework's safe request-saving mechanism or allow only validated internal URLs. **Never embed an arbitrary user-supplied URL directly into `state` and redirect to it**, as that can introduce an open redirect vulnerability. `state` can serve as a lookup key to a server-side record rather than carrying navigation targets itself.

### 3.3. `state` Does Not Solve Everything

Matching `state` tells the client the callback belongs to a pending flow, yet it **does not replace**:

- PKCE to protect the authorization code exchange.
- Issuer and audience checks to prevent accepting tokens from the wrong OP/client.
- ID Token validation, including `nonce` if sent.
- CSRF defenses for application business requests.

For clients integrated with multiple OPs, each request must be bound to the **exact expected provider**. Issuer validation and defenses against *authorization server mix-up* remain necessary; `state` alone is insufficient.

## 4. `nonce`: Binding the ID Token to the OIDC Authentication Request

### 4.1. `nonce` Differs from `state` in Where It Is Checked

`nonce` is a random value generated by the **OIDC Client** and included in the authorization request:

```http
GET /authorize?...&scope=openid%20profile&nonce=RANDOM_NONCE HTTP/1.1
Host: login.example.com
```

When receiving the `nonce` parameter, the OP must include this value in the **`nonce` claim of the ID Token** issued for that request. The client compares the received claim against its stored nonce before accepting the ID Token.

Example ID Token payload *after decoding* (signature and fields illustrative only):

```json
{
  "iss": "https://login.example.com",
  "sub": "user-734",
  "aud": "academy-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "nonce": "RANDOM_NONCE"
}
```

Basic condition:

```text
nonce_sent_in_request == nonce_claim_in_ID_Token
```

In the OIDC Authorization Code Flow, `nonce` is not mandatory on every request per the OIDC Core spec, but **if the client sent a nonce, it must verify the matching claim value**. In modern OIDC practice, using `nonce` properly is a valuable safeguard; never assume a token with a valid signature automatically belongs to the current request.

### 4.2. What Attacks Does `nonce` Help Prevent?

An ID Token may be validly signed by the OP and unexpired, yet **generated for a different authentication event**. If the application does not check binding between the ID Token and the authorization request, an attacker might attempt to replay or substitute an ID Token under certain flows or error-handling scenarios. `nonce` binds the ID Token to the initiated login attempt.

Example:

1. The client initiates login A and sends `nonce=N_A`.
2. A different ID Token carrying `nonce=N_B` is injected into the processing of login A.
3. Even though the other token's signature, `iss`, and `exp` are valid, the check `N_A != N_B` forces the client to **reject the ID Token**.

**Nonce is not a password.** The browser can see the nonce in the authorization request URL. It must be unpredictable and fresh for each request; its protection relies on the OP echoing that value inside a verified ID Token and the client verifying it against the right session.

### 4.3. Beyond `nonce`, What Else Must Be Checked on an ID Token?

An ID Token with a matching nonce is still **not enough**. The OIDC Client must validate according to the actual flow and configuration, including at least the appropriate checks:

| Field / Check | Meaning |
| --- | --- |
| **Signature / algorithm** | The ID Token must be verified with an allowed key and algorithm from the trusted OP. |
| **`iss`** | The issuer must match the identity provider configured for the request. |
| **`aud`** | The audience must include the OIDC Client's `client_id`. |
| **`azp`** | When conditions trigger an authorized party check, evaluate per OIDC rules. |
| **`exp`, `iat`** | The token is unexpired and other applicable timing constraints hold. |
| **`nonce`** | If the authorization request included a nonce, the claim must be present and match the sent value. |
| **`auth_time`, `acr`, `amr`** | Additional checks when business rules or the authentication request demand specific recency/strength. |

Never use an **ID Token as an access token** to call APIs merely because it contains user info. The ID Token authenticates the login event for the client; the **access token** authorizes resource access per API policies.

## 5. PKCE: Binding the Authorization Code to the Initiating Party

### 5.1. Without PKCE, a Stolen Code Could Be Exchanged for Tokens

The Authorization Code Flow splits into two steps:

1. The browser returns to the client with a short-lived **authorization code**.
2. The client uses that code to call the **token endpoint** and receive tokens.

The code is a sensitive value: whoever obtains the code can try exchanging it for tokens. Client authentication, redirect URI binding, HTTPS, and single-use codes are important defenses, yet **PKCE adds cryptographic proof linking the authorization request to the token request**.

PKCE was originally designed to protect public clients (such as native apps) against authorization code interception. Modern OAuth 2.0 security guidance broadly recommends PKCE for the Authorization Code Flow, including many confidential clients. Depending on the provider, PKCE may be mandatory.

### 5.2. `code_verifier` and `code_challenge`

The client generates a long, unpredictable random **`code_verifier`**. The PKCE specification defines a verifier string of **43–128 characters** from the unreserved URL-safe character set. A common approach is generating **32 random bytes** and Base64URL-encoding without padding: the result is 43 characters.

With the **S256** method:

```text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

The client sends **`code_challenge`** and `code_challenge_method` in the authorization request, while keeping **`code_verifier`** for the token request.

```text
On the client at start:
  verifier V  --SHA-256 + Base64URL-->  challenge C

At the authorization endpoint:
  OP binds challenge C and method S256 to the authorization code

At the token endpoint:
  Client sends code + verifier V
  OP computes BASE64URL(SHA256(ASCII(V))) and compares with C
  Match + other token request checks => tokens may be issued
```

This makes it infeasible for an attacker who **intercepted only the authorization code** without the verifier to exchange it for tokens, even if they saw the challenge in the URL. With the hash function and sufficient verifier entropy, reversing the challenge is impractical.

### 5.3. How Do the Authorization Request and Token Request Differ?

**Front-channel via browser:**

```http
GET /authorize?response_type=code
    &client_id=academy-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
    &scope=openid
    &state=S
    &nonce=N
    &code_challenge=C
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.com
```

**Back-channel from backend to OP:**

```http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTH_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy&code_verifier=V
```

The POST example is abbreviated: a **confidential client** must also perform **client authentication** using an OP-supported method (e.g., `client_secret_basic`, `private_key_jwt`). `code_verifier` does not replace client authentication, and a client secret does not replace PKCE.

Crucially, **`code_verifier` must never be placed in the authorization redirect**, because the browser and anything observing front-channel URLs must not learn the verifier.

### 5.4. Generating Verifier/Challenge in Java (Illustrative)

When learning the algorithm, you can compute it yourself to understand the relationship; in real Spring Security applications, **prefer using the framework's built-in PKCE support** instead of re-implementing state/token exchange manually.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceDemo() {}

    public static String newVerifier() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static String challengeS256(String verifier)
            throws NoSuchAlgorithmException {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hash);
    }

    public static void main(String[] args) throws Exception {
        String verifier = newVerifier();
        String challenge = challengeS256(verifier);

        System.out.println("S256 challenge: " + challenge);
        // Never log the verifier in a real application.
    }
}
```

The verifier is 43 unpadded Base64URL characters when generated from 32 bytes. The S256 challenge is also 43 characters. **Never use `Math.random()`, system time, or fixed strings** to generate a verifier. Knowing only the challenge must never be accepted as sufficient proof to exchange a code for tokens.

### 5.5. Why Prefer `S256`?

PKCE defines a `plain` method in the spec for special compatibility cases, but `plain` exposes the verifier directly as the challenge and does not provide the same protection if the authorization request is observed. **S256 should always be used** when supported by the OP; modern deployments typically require it.

A client must not silently downgrade to a non-PKCE flow upon encountering an exchange error with the OP. **Protection must be enforced by both client and Authorization Server**: sending `code_challenge` from the client when the token endpoint does not bind the code to the challenge provides no protection.

### 5.6. PKCE Does Not Protect Against Every Risk

PKCE alone does not prevent:

- An attacker obtaining **both the code and the verifier**.
- XSS or server compromise leaking data stored on the client.
- Using an ID Token with the wrong issuer/audience/nonce.
- CSRF on post-login business operations.
- The OP issuing tokens with wrong audience/scope or an API validating tokens improperly.

Thus, PKCE is an **additional binding layer** that must be deployed alongside HTTPS, client authentication where applicable, `state` verification, and OIDC token validation.

## 6. Quick Comparison of the Three Values

| Criterion | `state` | `nonce` | PKCE `code_verifier` / `code_challenge` |
| --- | --- | --- | --- |
| Generated by? | OAuth2/OIDC Client | OIDC Client | OAuth2 Client |
| Sent in authorization request? | **state** | **nonce** | **challenge + method**, never the verifier |
| Sent/checked at callback? | `state` is returned with the code and compared to stored copy | Never use a callback parameter instead of stored nonce | Verifier is not checked at browser callback |
| Present in ID Token? | Not required / not used for this purpose | **`nonce` claim** if sent by client | No |
| Sent at token endpoint? | Normally no | Normally no | **`code_verifier`** |
| Primary verifier? | Client | Client upon receiving ID Token | Authorization Server at token endpoint |
| Primary threat | Callback/login CSRF, request–response binding | ID Token substitution/replay, ID Token–request binding | Context-specific authorization code interception/injection |
| Note | Must be unpredictable and bound to the right session | Must check claim inside ID Token after verifying token | Verifier must be unpredictable, single-request, and kept off front-channel |

**Remember by verification timing:** `state` is checked **when the browser returns**, PKCE is checked **when exchanging the authorization code for tokens**, and `nonce` is checked **when validating the ID Token**.

## 7. Where Does Spring Security Store and Process These Three Values?

In a **Spring MVC/Servlet** application using `oauth2Login()`, Spring Security already provides the necessary mechanisms. You do not need to write a custom callback endpoint, manually call the token endpoint, or manually decode ID Tokens to handle the standard login flow.

### 7.1. Components in the Login Flow

| Component | Responsibility |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Intercepts login initiation, builds the authorization request, and redirects to the Authorization Server. |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Stores the authorization request before redirect so the callback can restore correlation data. |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Standard/default repository implementation storing the OAuth2 request in the HTTP session. |
| `OAuth2LoginAuthenticationFilter` | Handles the `/login/oauth2/code/{registrationId}` callback and initiates authorization code authentication. |
| OAuth2/OIDC login authentication providers | Exchange the code for tokens, validate responses, and build the protocol principal/`Authentication`. |
| `SecurityContext` / session repository | Maintains the application login session after authentication succeeds. |

In the default configuration, the browser visits:

```text
GET /oauth2/authorization/academy
```

And then receives the callback:

```text
GET /login/oauth2/code/academy?code=...&state=...
```

Spring Security uses the saved authorization request to correlate the callback. For OIDC requests, ID Token processing applies OIDC rules, including `nonce` when used. The PKCE verifier is kept in the authorization request context to be sent on the token request when PKCE is enabled.

**Do not write a custom callback controller** overlapping `/login/oauth2/code/{registrationId}` unless there is a clear architectural reason; it easily bypasses the framework's built-in binding checks.

### 7.2. Example OIDC Client Configuration

Suppose the OP supports OIDC discovery and the client is registered with the matching callback.

**Maven Dependency** (Spring Boot application with dependency management):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

**`application.yml`**:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            provider: academy-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          academy-provider:
            issuer-uri: https://login.example.com/realms/academy
```

This is an illustrative domain; replace `issuer-uri` with the real issuer published by the OP. `scope=openid` is the key signal for an OIDC flow. Configure the client secret via environment variables or a secret store; never commit secrets to Git.

Basic **`SecurityFilterChain`**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

This configuration lets Spring Security manage redirects, callbacks, validation, and sessions via its built-in features. **Whether PKCE is enabled by default may depend on the Spring Security version and client registration type** (public/confidential). Never assume PKCE is active merely because `oauth2Login()` succeeds; verify the configuration or inspect the authorization request for `code_challenge`/`code_challenge_method=S256`.

### 7.3. Explicitly Enabling PKCE via a Request Customizer

In Spring Security versions offering `OAuth2AuthorizationRequestCustomizers.withPkce()`, you can apply the customizer to the authorization request resolver, even when the client has a secret:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2PkceConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
```

This example is an **alternative configuration** replacing `SecurityConfig` above—do not place both default-scoped `SecurityFilterChain` beans in the same application. It requires Spring Security and the OP to support PKCE for that client. The customizer instructs Spring Security to generate and retain the verifier alongside the authorization request, send the challenge, and send the verifier during code exchange; no JavaScript parameter generation is needed.

In real applications, customizations to the authorization request such as `prompt`, `login_hint`, extra scopes, or OP-specific parameters must be implemented so they **do not disable default `state`, `nonce`, and PKCE handling**. If you replace the resolver/repository entirely, preserve all corresponding security bindings.

### 7.4. Where Data Is Stored and Its Relationship with Sessions

With the default `HttpSessionOAuth2AuthorizationRequestRepository`, Spring temporarily stores the authorization request in the HTTP session. The browser stores the session cookie (typically `JSESSIONID`) and sends it back when hitting the callback.

```text
Browser                           Spring application
   |                                   |
   | GET /oauth2/authorization/...     |
   |---------------------------------->|
   |                                   | Temporarily save request in session:
   |                                   | state, nonce/PKCE info when used
   |<----------------------------------|
   | 302 Location: OP + Set-Cookie     |
   |                                   |
   | (goes through OP, back to callback)
   |---------------------------------->|
   | GET /login/oauth2/code/...?code...|
   | Cookie: JSESSIONID                |
   |                                   | Retrieve original request
   |                                   | Compare state, proceed to exchange code
```

If the browser fails to send the cookie back after the redirect, Spring cannot find the saved authorization request even when `state` in the URL looks right. Common causes: wrong cookie domain/path, poorly configured `Secure`/HTTPS or TLS proxy, `SameSite` policy, session expiration, routing the callback to an instance without shared session state, or concurrent login flows overwriting temporary storage in a given configuration.

**`SameSite=Lax` is generally compatible with top-level GET redirect callbacks**; if a provider uses `form_post` response mode, re-evaluate cross-site cookie behavior and appropriate CSRF protection. Never blindly enable `SameSite=None` without understanding its purpose and deployment topology.

## 8. Tracing One Login to See All Three Values Clearly

Consider an illustrative sequence of requests where:

- `S_A`: state for login attempt A.
- `N_A`: nonce for login attempt A.
- `V_A`: verifier kept on the application side.
- `C_A`: challenge computed from `V_A`.
- `CODE_A`: short-lived, single-use authorization code.

**Step 1 — Start**

```text
GET https://app.example.com/oauth2/authorization/academy

Spring temporarily stores in session:
  state         = S_A
  nonce         = N_A
  code_verifier = V_A
  provider      = academy-provider
  redirect_uri  = https://app.example.com/login/oauth2/code/academy
```

**Step 2 — Redirect to OP**

```text
GET https://login.example.com/authorize
  ?response_type=code
  &client_id=academy-web
  &redirect_uri=...
  &scope=openid%20profile
  &state=S_A
  &nonce=N_A
  &code_challenge=C_A
  &code_challenge_method=S256
```

The browser can see `S_A`, `N_A`, and `C_A`; it **does not need to know `V_A`**.

**Step 3 — Callback**

```text
GET https://app.example.com/login/oauth2/code/academy
  ?code=CODE_A
  &state=S_A
```

The client loads the saved authorization request, compares `state`, and checks that the request matches the selected provider. If the URL returns `state=S_B` or the browser no longer holds the session containing `S_A`, the callback must be rejected.

**Step 4 — Token request**

```text
POST https://login.example.com/token

grant_type=authorization_code
code=CODE_A
redirect_uri=https://app.example.com/login/oauth2/code/academy
code_verifier=V_A
(+ client authentication if applicable)
```

The OP recomputes the challenge from `V_A` and compares it against `C_A` bound to `CODE_A`. If the verifier was changed to `V_B`, the OP must reject the exchange request.

**Step 5 — ID Token verification**

The OP returns an ID Token containing `nonce=N_A`. Spring fully validates the ID Token and compares `N_A` against the stored nonce. If the token carries `nonce=N_B`, the ID Token does not belong to login attempt A and must be rejected.

**Step 6 — Establish login session**

Once authentication completes, the application creates or updates the login session. Temporary OAuth2 correlation data is consumed/cleaned up appropriately. Subsequent business requests rely on the application session; the browser **does not resend `state`, `nonce`, or `code_verifier`** on every page load.

## 9. Failure Scenarios and How to Narrow Them Down

| Observation | First Mechanism to Check | Common Causes |
| --- | --- | --- |
| Callback reports `invalid_state` or cannot find matching request | `state` + session storage | Cookie not sent, session expired, callback hit wrong host, session not shared across instances, auth request overwritten. |
| Token endpoint returns `invalid_grant` | PKCE or authorization code conditions | Wrong/missing verifier, redirect URI mismatch, expired code, already-used code, code belongs to another client. |
| OP says `code_challenge` is required | PKCE on authorization request | Client has not enabled PKCE or request customizer was not applied to the right chain/resolver. |
| ID Token rejected due to `nonce` | OIDC nonce binding | Nonce in token missing/different, wrong request context stored, or OP configuration issue. |
| ID Token signature valid yet rejected due to `iss`/`aud` | OIDC token validation | Wrong issuer, client ID, OP registration, or metadata/signing keys. |
| OP login succeeds, then returning to app loops back to login | Session/cookie | Browser lost cookie or SecurityContext/session was not persisted after login. |
| One tab logs in fine, another reports wrong state | Concurrent requests | Authorization request repository/configuration cannot hold multiple pending flows simultaneously; handle concurrency intentionally. |
| Valid callback fails only after placing app behind a reverse proxy | Redirect URI, TLS, cookies | `X-Forwarded-Proto` / `Forwarded`, external URL, `Secure` cookie, or public host not aligned. |

For `invalid_grant`, **do not immediately conclude PKCE is wrong**: under OAuth2, an OP can group many different errors under that same error code. Inspect OP logs without exposing tokens, and compare client configuration, code lifetime, and redirect URI; if inspecting token requests, redact secrets and credentials.

### 9.1. Inspecting Requests in the Browser and on the Server

In a learning environment, you can trace the flow using browser developer tools' Network tab:

1. Open `/oauth2/authorization/academy` with **Preserve log** enabled to see all redirects.
2. Check whether the URL to the OP contains `state`, `nonce` (when used), and `code_challenge_method=S256` / `code_challenge`.
3. Observe the callback containing matching `code` and `state`.
4. Remember that the **token request normally runs server-to-server**, so it will not appear in the browser's Network tab. Controlled backend tracing/logging is needed to observe it.
5. After a successful callback, visit a protected page to understand its relationship with the session cookie.

**Keep observed data private**: never post screenshots of full callback URLs, session cookies, tokens, `client_secret`, or `code_verifier` in issues or public chats. An authorization code is single-use yet remains a sensitive credential while valid.

### 9.2. Misguided "Quick Fixes"

- **Skipping `state` comparison** to make the callback succeed: breaks response–request binding.
- **Disabling PKCE** because the OP rejected `code_verifier`: verify instead that the client sends consistent challenge/verifier and the OP supports `S256`.
- **Skipping `nonce` validation** to accept the ID Token: removes the binding between the ID Token and the authentication session.
- **Disabling CSRF application-wide** when login fails: confuses callback protection with cookie-backed business request protection.
- **Disabling TLS certificate verification** because the token endpoint fails HTTPS: opens man-in-the-middle vulnerabilities.
- **Writing a custom callback controller that just reads `code`**: typically bypasses protections Spring Security already provides.

## 10. Advanced Cases to Keep in Mind

### 10.1. Confidential Client vs. Public Client

A **confidential client** is a backend component capable of keeping client credentials (such as a secret or private key) secure. A **public client**, such as an application running entirely in the browser or a mobile app, cannot protect embedded secrets.

- Public clients need PKCE because they cannot rely on a client secret as proof of possession for the code.
- Confidential clients **should still use PKCE when supported by the OP**, because PKCE adds per-request binding while separate client authentication is still enforced when required.
- PKCE's protection holds as long as the verifier is not leaked alongside the code; in a server-side Spring MVC app, the verifier can stay in server-side session state.

### 10.2. Multiple OPs and Mix-Up Risks

An application may configure `google`, `enterprise-sso`, and `academy` together. In that case, callbacks must be bound to the exact right registration/issuer. Beyond checking `state`, validate the ID Token/token issuer and authorization/token endpoint configuration. In scenarios vulnerable to *mix-up*, OAuth2 guidance recommends issuer identification mechanisms such as the authorization response `iss` parameter (RFC 9207) when supported, or equivalent provider-binding controls.

A valid ID Token signature from **OP B** must never automatically be treated as valid for a login session intended for **OP A**.

### 10.3. Multiple Tabs or Concurrent Authorization Requests

Some simple authorization request stores keep only one pending request per session at a time. When a user clicks login repeatedly or opens multiple tabs, correlation data for an older request may be overwritten and its callback will report a missing state.

If an application must support multiple concurrent flows, it needs an `AuthorizationRequestRepository` / storage model capable of distinguishing incomplete requests, preventing replay, and cleaning up properly. **Never drop `state` verification to support multiple tabs.**

### 10.4. Response Mode and Cookie Policies

Authorization Code Flow passing code/state in the query string is the common choice. OIDC can also use `response_mode=form_post`, causing the browser to POST the callback from the OP's site to the application's site.

If the browser withholds the session cookie due to cross-site rules, the application cannot find the saved authorization request and `state`. In such setups, carefully evaluate browser policies, `SameSite=None; Secure` when justified, CSRF strategy, and callback protection. Never assume changing cookie flags globally will automatically solve everything.

## 11. Thought Exercises

**Exercise 1 — Valid state, wrong PKCE.** The callback returns the expected `state`, yet the backend sends a `code_verifier` that does not match the original challenge. What happens?

> The client may pass the callback check, but the OP must reject the code exchange because PKCE fails. Valid `state` does not substitute for `code_verifier`.

**Exercise 2 — Valid PKCE, wrong nonce.** The OP accepts the verifier and issues tokens; the ID Token contains a different nonce from the one sent.

> The client must reject the ID Token per OIDC rules. A successful token request does not prove the ID Token belongs to that authentication attempt.

**Exercise 3 — Valid ID Token, mismatched state.** The token has valid signature, issuer, audience, and nonce, yet the callback does not match any authorization request in the session.

> The client must reject the callback before treating it as a valid login session. Token checks cannot cure an authorization response unbound to the initiated flow.

**Exercise 4 — Code leaked from callback URL.** An attacker knows `CODE_A` and `code_challenge=C_A`, but does not know `code_verifier=V_A`.

> If PKCE `S256` is implemented and properly enforced by the OP, the attacker cannot exchange the code using only the code and challenge. The client must still protect cookies, sessions, logs, tokens, and the back-channel.

**Exercise 5 — Website login succeeds, yet API returns `401`.** Should you send `state` or `nonce` in the `Authorization` header?

> No. APIs typically require an **access token** matching the API's audience, scopes, and policies. `state` and `nonce` serve the OIDC login flow, not API authorization.

## 12. Key Takeaways

These three values participate in a single login attempt yet belong to **three distinct verification checkpoints**:

```text
Before redirect:
  generate state + nonce + PKCE verifier/challenge
                    |
                    v
Authorization response returns to callback:
  compare state against saved authorization request
                    |
                    v
Token request from backend to OP:
  OP verifies code_verifier against saved code_challenge
                    |
                    v
ID Token received:
  client checks signature, issuer, audience, expiration,
  nonce, and relevant OIDC requirements
                    |
                    v
Create Authentication + application login session
```

With Spring Security OIDC Client, **let the framework manage these bindings**, configure client registration, redirect URI, session/cookies, issuer, and PKCE properly, and diagnose errors by verification checkpoint. Whenever customizing authorization requests, token exchange, or callbacks, ensure none of the existing protections are stripped away.

### References for Deeper Reading

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), especially `state` and the Authorization Code Grant.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636), defining verifier, challenge, and `S256`.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), security updates for authorization codes, PKCE, and clients.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html), requirements on nonce and ID Token validation.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207), protections involving multiple authorization servers.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [Spring Security Reference — Advanced OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html).
