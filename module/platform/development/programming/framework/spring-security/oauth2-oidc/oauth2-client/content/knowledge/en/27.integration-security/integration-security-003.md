# 27.3. PKCE, `nonce`, `state`, and Corresponding Replay Protection Mechanisms

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** application, the browser typically leaves the application for the Authorization Server (AS) or OpenID Provider (OP), then returns to the application with an authorization response. An attacker may attempt to **inject a response from another transaction**, **steal an authorization code**, **replay an ID Token**, or **use a leaked token to call an API**.

Three common mechanisms used to protect Authorization Code / OIDC Login are:

- **`state`**: correlates the authorization response with the **original authorization request** within the appropriate client/browser context; helps prevent login CSRF and transaction mix-ups.
- **PKCE (Proof Key for Code Exchange)**: establishes a cryptographic link between the **authorization request** and the **token request** via a `code_challenge` / `code_verifier` pair; protects against a party obtaining an authorization code without possessing the verifier.
- **OIDC `nonce`**: binds the **ID Token** to the initiated **authentication request**; prevents using an ID Token that does not belong to the current request in applicable flows.

These mechanisms **complement each other and cannot be arbitrarily substituted for one another**. Nor do they **by themselves prevent a stolen access token from being replayed** at the Resource Server; that requires token validation, audience/scope/lifetime limits, token storage protection, and, where appropriate, sender-constrained tokens such as DPoP or mTLS.

A typical flow may look like:

```text
Browser opens /oauth2/authorization/company
    |
    v
Spring Security generates:
    state = S-opaque-random
    code_verifier = V-secret-random
    code_challenge = BASE64URL(SHA256(V))
    nonce = N-unique (when OIDC flow uses it)
    |
    v
Authorization request -> OP
    state=S
    code_challenge=...
    code_challenge_method=S256
    nonce=...
    |
    v
Browser returns to callback:
    code=C
    state=S
    |
    v
Client verifies correlation via state
    |
    v
Token request:
    grant_type=authorization_code
    code=C
    code_verifier=V
    |
    v
OP verifies PKCE, issues tokens if valid
    |
    v
Spring Security validates ID Token:
    signature, issuer, audience, expiry, nonce when applicable
    |
    v
Valid Authentication is finally created
```

This lesson belongs to **Chapter 27. Integration Security**, using Spring Security 6.x on Servlet as the primary example, with comparisons to Reactive WebFlux. The goal is to understand **which protection layer blocks which type of replay**, how Spring Security stores correlation data, and how to implement these flows without accidentally disabling security checks.

> **Scope:** Java 17+, Spring Boot 3.x / Spring Security 6.x, OAuth 2.0 Authorization Code + OIDC. Hostnames like `example.test` and placeholder token values `REDACTED` are illustrative only. Standalone random-generation snippets are exercises to understand PKCE; in production, prefer Spring Security's built-in generators and validators.

---

## 1. First: What Is Replay?

In authentication and authorization, a **replay attack** occurs when an attacker resubmits an existing message, credential, or token so that the system accepts it outside its original context.

Different examples include:

| Replayed artifact | What the attacker wants | Related protection layers |
| --- | --- | --- |
| Authorization response containing `code` | Log in with a response outside the current browser flow or exchange an intercepted code | `state`, PKCE, one-time code, redirect URI/client binding |
| Intercepted authorization code | Exchange the code for an access token at the token endpoint | **PKCE**, client authentication, code binding, code lifetime |
| Old ID Token | Make the client accept an ID Token from another request | **OIDC nonce**, ID Token validation, session/correlation binding |
| Stolen access token | Call the Resource Server impersonating the subject/token holder | Sender-constrained tokens, TLS, audience/scope/expiry, storage protection |
| Stolen refresh token | Mint new access tokens over an extended period | Refresh rotation/reuse detection, sender-constraining, secure storage |
| Browser callback URL in history | Attempt to re-process an old code/state | State consumption, one-time authorization code, expiry, PKCE |

**There is no single "anti-replay" mechanism covering every row.** For example, OIDC's `nonce` is not automatically used by the Resource Server to reject a replayed access token.

### 1.1. Distinguishing Authorization CSRF from Token Theft

- **Login CSRF / authorization response injection:** an attacker tries to make the victim's browser complete a login flow controlled by the attacker. The result may be logging the victim into the attacker's account or linking the wrong identity.
- **Code interception:** an attacker obtains an authorization code from a redirect or another flaw and tries to exchange it ahead of the legitimate client.
- **ID Token replay:** a previously valid ID Token is reused in another authentication context.
- **Bearer token replay:** anyone holding the token can use it at the API if there is no sender binding and the token is still valid.

These scenarios have **different entry points and trust boundaries**. That is why Spring Security uses multiple protections simultaneously.

## 2. Comparison Table: `state`, PKCE, and `nonce`

| Criterion | `state` | PKCE | OIDC `nonce` |
| --- | --- | --- | --- |
| Primary standard | OAuth 2.0 / security BCP | RFC 7636 / OAuth Security BCP | OpenID Connect Core |
| Client-generated value | Opaque random state | Random `code_verifier` | Unique nonce |
| Sent in authorization request? | Yes | **`code_challenge`** and method | Yes in OIDC request when used |
| Returned in authorization response? | **Yes**, `state` | Verifier is not returned on callback | Not a standard code-flow callback parameter |
| Used in token request? | Usually no | **`code_verifier`** | Not a standard code-exchange parameter |
| Where is it verified? | **Client/RP** against original authorization request | **Authorization Server** at the token endpoint | **Client/RP** against ID Token's `nonce` claim |
| Primary defense | Callback/request correlation, login CSRF | Code interception, unauthorized code exchange | ID Token replay/cross-request substitution |
| Verifies user identity alone? | No | No | No; full ID Token validation is needed |
| Prevents bearer access token replay? | No | No | No |
| Can be arbitrarily omitted if another exists? | Not arbitrarily | Not arbitrarily | Depends on OIDC flow/policy; do not omit if flow uses it |

**Key takeaway:** `state` is **verified when the callback returns**, PKCE is **verified by the AS during code exchange**, and `nonce` is **verified by the RP inside the ID Token**. All three operate in the same browser flow, yet at three distinct verification points.

### 2.1. Who Trusts Whom?

```text
state:
  RP trusts original request data in RP's own repository/session
  RP does not trust an arbitrary "state" supplied only by the callback

PKCE:
  AS remembers code_challenge bound to the authorization code
  AS only accepts a token request carrying a matching code_verifier

nonce:
  RP stores expected nonce context bound to the authentication request
  RP verifies the nonce claim in the ID Token from a trusted OP
```

Skipping any one of the three checkpoints weakens its corresponding boundary.

---

## 3. Complete Authorization Code + PKCE + OIDC Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant RP as Spring Security OAuth2 Client
    participant Store as Authorization Request Store
    participant OP as OpenID Provider
    participant API as Resource Server

    Browser->>RP: GET /oauth2/authorization/company
    RP->>RP: Generate state S, verifier V, challenge H(V), nonce N
    RP->>Store: Save original request + correlation context
    RP-->>Browser: 302 /authorize?state=S&code_challenge=H(V)&nonce=N
    Browser->>OP: Authorization request
    OP->>User: Authentication + consent (when needed)
    OP-->>Browser: Redirect /login/oauth2/code/company?code=C&state=S
    Browser->>RP: GET callback, code=C, state=S
    RP->>Store: Look up/consume original request by browser + state
    alt Not found / state mismatch
        RP-->>Browser: Login failure; do not use code
    else Valid correlation
        RP->>OP: POST /token {code=C, code_verifier=V}
        OP->>OP: Verify one-time code, client, redirect URI, PKCE
        alt Invalid PKCE/code
            OP-->>RP: OAuth2 error invalid_grant
            RP-->>Browser: Login failure
        else Valid token request
            OP-->>RP: Access Token + ID Token
            RP->>RP: Verify ID Token iss/aud/signature/exp/nonce
            alt Invalid ID Token
                RP-->>Browser: Login failure
            else Valid ID Token
                RP->>RP: Create Authentication
                RP-->>Browser: Valid authenticated session
                RP->>API: API call with access token for right audience
            end
        end
    end
```

This diagram shows **security logic**, not every implementation detail. For instance, Spring Security may represent the OIDC nonce using internal attributes rather than storing a plain string exactly as illustrated.

## 4. PKCE: How Does It Prevent Authorization Code Theft?

PKCE stands for **Proof Key for Code Exchange** (RFC 7636). Before the browser goes to the OP, the client generates an unpredictable **`code_verifier`**, then computes **`code_challenge`**.

With the recommended **`S256`** method:

\[
\text{code\_challenge} = \operatorname{BASE64URL\_NO\_PADDING}(\operatorname{SHA256}(\operatorname{ASCII}(\text{code\_verifier})))
\]

In the authorization request, the client sends the **challenge**, not the verifier. When exchanging the authorization code for tokens, the client sends the **verifier**.

### 4.1. Why Are Two Values Needed?

```text
Client:
  V = random code_verifier
  C = S256(V)

Front-channel via browser:
  GET OP /authorize?code_challenge=C&code_challenge_method=S256

Back-channel:
  POST OP /token
    grant_type=authorization_code
    code=AUTHORIZATION_CODE
    code_verifier=V

OP:
  Verify S256(V) == C attached to authorization code
```

An attacker who only intercepts the authorization code or sees the challenge **cannot feasibly derive the verifier** if the verifier has sufficient entropy.

### 4.2. PKCE Parameters and Data Transmission Boundaries

| Name | Where does it appear? | Should it be kept secret? |
| --- | --- | --- |
| `code_verifier` | Held by Client, sent in token request | **Yes**; never put in browser callbacks/logs |
| `code_challenge` | Authorization request via browser | Does not need secrecy, but must bind to the authorization code |
| `code_challenge_method` | Authorization request | Typically `S256` |
| Authorization code | Callback via browser, token request | Short-lived credential; protect, do not log |
| Client secret | Client authentication at token endpoint, if confidential client | **Yes**; never send to the browser |

**The OP never "guesses" the verifier from the challenge.** It checks the verifier value sent by the client during the token exchange.

### 4.3. Verifier Must Be Sufficiently Random

Per RFC 7636, `code_verifier`:
- Has length **43 to 128 characters**;
- Uses unreserved characters such as letters, digits, hyphen, period, underscore, and tilde;
- Must be unpredictable, generated via a **CSPRNG**;
- Preferably generated from at least **32 random octets** encoded as Base64URL without padding.

Do not use:
- Username or email;
- Simple timestamps;
- Sequential counters;
- `Math.random()`;
- A UUID without verifying entropy suitability as the sole mechanism;
- A fixed verifier reused across all logins.

### 4.4. `S256` or `plain`?

PKCE defines `plain` and `S256`. With `plain`, the challenge is the verifier itself and can be exposed via the front channel. **Prefer `S256`**, and never silently fall back from `S256` to `plain` on OP rejection without explicitly confirming the contract and threat model.

If an OP does not support `S256`, that is a signal to review the security posture of the integration; do not treat disabling PKCE as a default workaround.

### 4.5. PKCE Protects Both Public Clients and Confidential Clients

A misconception is "since the client already has a client secret, PKCE is unnecessary." Client authentication and PKCE solve different problems:

- **Client authentication** verifies client identity at the token endpoint.
- **PKCE** binds the token request to the authorization request that produced the challenge.

OAuth 2.0 Security Best Current Practice recommends PKCE broadly, including for many confidential client scenarios. Do not omit PKCE merely because the backend has a `client_secret`.

### 4.6. PKCE Alone Does Not Prevent All Code Injection

PKCE makes **exchanging an intercepted code without the verifier** difficult, yet the client still needs:
- `state` correlation;
- Exact client/redirect URI matching;
- Binding the authorization code to the right AS;
- Preventing authorization server mix-up;
- Checking the response and OIDC token against the expected issuer.

An attacker who leaks both the verifier and the authorization code can bypass PKCE. Thus, session/transport/storage security remains mandatory.

---

## 5. Java Code Illustrating How to Generate PKCE S256

This is an **educational example** to understand the formula. In Spring Security production code, prefer `OAuth2AuthorizationRequestCustomizers.withPkce()` and the framework's verifier storage.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceExample {

    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceExample() {}

    public static String newCodeVerifier() {
        byte[] randomBytes = new byte[32]; // 256 bits
        RANDOM.nextBytes(randomBytes);

        // 32 bytes -> 43 unpadded Base64URL characters.
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(randomBytes);
    }

    public static String s256CodeChallenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (java.security.NoSuchAlgorithmException e) {
            // SHA-256 is a standard algorithm available in Java SE.
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    public static void main(String[] args) {
        String verifier = newCodeVerifier();
        String challenge = s256CodeChallenge(verifier);

        System.out.println("Verifier length: " + verifier.length());
        System.out.println("Challenge length: " + challenge.length());

        // Never print verifiers/challenges or real authorization URLs
        // from a production login session to console/logs.
    }
}
```

**Key points:**

- Use `SecureRandom`, not UI randomness.
- Use **unpadded** Base64URL, not standard Base64 with `+`, `/`, `=`.
- SHA-256 hashes the ASCII bytes of the verifier, since the verifier contains only valid ASCII characters.
- The challenge may be public; the verifier must be protected.
- Every new authorization request must have a **fresh verifier**.

### 5.1. Never "Test" a Verifier by Comparing Raw Strings

Wrong:

```java
boolean valid = codeVerifier.equals(codeChallenge);
```

With `S256`, the OP must recompute **S256(verifier)** and compare it to the challenge bound to the authorization code. **The client must never assume a browser-side check replaces OP verification**.

### 5.2. The Authorization Server Must Enforce PKCE

The client sending a challenge creates no security if the Authorization Server **ignores the verifier at the token endpoint**. The OP/AS must:
1. Store the challenge and method with the authorization transaction/code;
2. Require the corresponding verifier in the token request;
3. Verify `S256`;
4. Reject if mismatched or missing when the code is bound to PKCE;
5. Enforce code expiration, one-time use, and client/redirect binding.

When encountering an AS that implements PKCE incorrectly, fix/switch the provider or record an explicit security decision; never claim "we are safe because the client sends PKCE parameters."

## 6. `state`: Correlation and Login CSRF Prevention

`state` is a value the client sends in the authorization request and receives back in the authorization response.

```text
Authorization request:
    response_type=code
    client_id=portal-client
    redirect_uri=https://app.example.test/login/oauth2/code/company
    state=3jV2y...random

Callback:
    code=C123
    state=3jV2y...random
```

Spring Security must compare the callback's `state` with the original request data stored in `AuthorizationRequestRepository`.

### 6.1. Why Must `state` Be Bound to the Browser/Session?

Suppose an attacker starts a login in their own browser, obtains a valid authorization response, and tries to feed that response into the victim's browser. If the RP accepts `code` without checking correlation, the app might complete a login contrary to the victim's intent.

```text
Attacker browser:
  start login -> state=S_attacker, code=C_attacker

Victim browser:
  no matching request/state in its own session

Attempted injected callback:
  /login/oauth2/code/company?code=C_attacker&state=S_attacker

Secure RP:
  lookup victim session for S_attacker -> no match
  reject callback
```

**`state` must be verified within the client/browser context that initiated the flow**, not merely checked as a syntactically valid string.

### 6.2. Does `state` Need to Be an Absolute Secret?

`state` travels through the **front channel**: authorization URL and callback URL. Hence it can appear in browser history or proxy logs and should not be treated as a secret that can never be observed.

Its protection relies on:
- An unpredictable value;
- The original request stored in a trusted store;
- Browser/session binding or a threat-modeled equivalent mechanism;
- Exact value comparison;
- Expiration and one-time consumption;
- Rejecting callbacks missing or mismatching `state` in flows requiring `state`.

**Never use `state` as an access token**, and never grant privileges based on `state` matching a format.

### 6.3. Be Careful When Embedding URLs in `state`

Some projects encode a return URL or tenant context inside `state`. If doing this yourself:
- Do not allow `state` to hold an arbitrary redirect URL and redirect the user to it;
- Protect the integrity and binding of the metadata;
- Do not put PII/secrets into URLs;
- Allowlist return paths;
- Enforce TTL and one-time use.

In typical Spring Security apps, **there is no need to encode the entire session into `state`**; storing the authorization request in a server-side repository is simpler.

### 6.4. `state` Differs from a POST Form CSRF Token

The CSRF token on `POST /logout` or a state-changing form belongs to **Spring Security CSRF protection**. OAuth2 `state` protects the authorization redirect flow.

Both values help prevent CSRF, yet **cannot replace one another**:
- OAuth2 `state` is not a token you submit on every form;
- A form CSRF token does not replace authorization request state at the OIDC callback.

---

## 7. `nonce`: Binding the OIDC ID Token to the Authentication Request

OIDC introduces an **ID Token**, distinct from an OAuth2 access token. An ID Token contains claims such as:

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "user-123",
  "aud": "portal-client",
  "iat": 1760000000,
  "exp": 1760000600,
  "nonce": "N-unique-value-from-request"
}
```

In this example, timestamps and nonce are illustrative data, not real tokens.

If the client sends `nonce` in the authentication request, the OP must return the corresponding value in the ID Token per the OIDC contract, and the RP must verify it.

### 7.1. The `nonce` Flow

```text
RP:
  create nonce N
  store expected nonce for authentication request

Authorization request:
  nonce=N (or representation generated by framework per contract)

OP:
  issue ID Token including nonce claim corresponding to request

RP:
  validate ID Token signature / issuer / audience / expiry
  validate nonce matches expected value for this transaction
  accept Authentication only when all checks pass
```

If an attacker presents an **old ID Token** from another transaction with nonce `N_old` while the current transaction expects `N_new`, the RP must reject it.

### 7.2. Is `nonce` Mandatory in the OIDC Code Flow?

Per OIDC Core:
- In the **Authorization Code Flow**, `nonce` in the authentication request is **optional by spec**, though if sent, the ID Token must be properly verified.
- In the **Implicit Flow** and some **Hybrid Flows**, `nonce` is mandatory per profile/flow.

Even though Authorization Code + PKCE is the modern choice, **do not conclude `nonce` is useless**. OIDC `nonce` is a valuable ID Token binding layer, especially since OPs and Spring Security support it automatically.

### 7.3. Do Not Compare `nonce` with Hand-Rolled Logic If the Framework Uses an Internal Representation

Some frameworks generate a random nonce, store one representation in authorization request attributes, and send a derived representation (e.g., a hash) to the OP. On callback, the framework knows how to match it against the ID Token claim.

Therefore, do not write:

```java
// DO NOT DO THIS: assuming Spring Security's internal nonce storage format.
String storedNonce = request.getAttribute("nonce");
String returnedNonce = idToken.getClaimAsString("nonce");
if (storedNonce.equals(returnedNonce)) {
    // Allow login immediately?
}
```

This snippet can both mismatch the representation and bypass ID Token signature/issuer/audience/expiry checks. **Prefer Spring Security's built-in OIDC validators** rather than re-implementing nonce logic with a standalone comparison.

### 7.4. `nonce` Is Not `state`

```text
state:
  authorization response <-> authorization request

nonce:
  ID Token <-> OIDC authentication request
```

`state` is returned in the **authorization response**. `nonce` is returned in the **ID Token claim**, not as an arbitrary callback query parameter trusted by the RP.

### 7.5. `nonce` Does Not Replace Checking Other Claims

A matching `nonce` does not prove the ID Token is valid if:
- The signature is invalid;
- `iss` is an untrusted OP;
- `aud` does not match the client;
- `exp` has passed;
- `azp` requires validation and fails;
- The JWT algorithm is disallowed;
- Tokens are mixed across clients/providers.

**OIDC login succeeds only when every applicable validation passes**.

---

## 8. Protection Steps in Spring Security Servlet

A basic OIDC login configuration:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

To function, the app needs a valid OIDC client registration. Spring Security coordinates several components:

| Component | Responsibility |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Initiates authorization request and redirects to AS |
| `OAuth2AuthorizationRequestResolver` | Builds request including state, redirect URI, scopes, and PKCE/nonce when enabled |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Stores authorization request/correlation across browser redirects |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Default Servlet implementation using HttpSession |
| `OAuth2LoginAuthenticationFilter` | Receives callback, restores authorization transaction, and authenticates |
| `OAuth2LoginAuthenticationProvider` | Handles OAuth2 code login |
| `OidcAuthorizationCodeAuthenticationProvider` | Handles OIDC code flow and ID Token validation |
| `ClientRegistrationRepository` | Configures trusted clients/providers |
| `OAuth2AccessTokenResponseClient` | Exchanges authorization code for tokens per grant |
| `JwtDecoder` / OIDC token validator | Verifies JWT signature/claims per provider |

**Not every component above needs to be written by the application.** Spring Security provides defaults suited to common flows. Replacing filters/providers yourself just to "add one parameter" often increases risk.

### 8.1. Automatic PKCE in Default Cases

In Spring Security 6.x, the client authorization infrastructure supports PKCE and enables it automatically in appropriate scenarios, especially for **public clients** with `client-authentication-method: none`. For confidential clients, PKCE can be explicitly enabled via a customizer if the OP supports it.

Never assume "having `spring-boot-starter-oauth2-client` means every registration uses S256." Verify the actual requests per registration in tests and confirm the AS's PKCE policy.

### 8.2. OIDC `nonce` Coordinated by the Framework

When a registration includes the `openid` scope, Spring Security OIDC Login supports nonce binding and ID Token verification per flow. **Let the framework manage nonce and correlation metadata** instead of appending an arbitrary nonce to the URL and skipping verification.

### 8.3. The Repository Connects Two HTTP Requests

```text
GET /oauth2/authorization/company
    -> OAuth2AuthorizationRequest
       state=S, PKCE verifier in attributes, nonce context when used
    -> HttpSession authorization request repository

GET /login/oauth2/code/company?code=C&state=S
    -> repository loads/removes authorization request
    -> checks correlation
    -> token endpoint with verifier
    -> OIDC ID Token validation
```

If the browser fails to send back the same session cookie, or the session store lacks the original request, the callback **must not be accepted**.

## 9. Explicitly Enabling PKCE via `OAuth2AuthorizationRequestCustomizers`

A confidential client app can proactively add PKCE to the authorization code flow using Spring Security APIs:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PkceSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint ->
                    endpoint.authorizationRequestResolver(resolver)))
            .build();
    }
}
```

When the resolver builds an authorization request for an eligible registration, the customizer:
- Generates `code_verifier`;
- Computes `code_challenge` and sets `S256`;
- Adds public PKCE parameters to the authorization request;
- Stores the verifier in client-side metadata of the authorization request for the token exchange.

**Note:** the example mounts the resolver at `/oauth2/authorization`, the default path. If the app changes the base URI, update the resolver, links, and `SecurityFilterChain` in sync. Never mutate the authorize URL after the resolver constructs the request, as that can desynchronize `state`/`nonce`/PKCE.

### 9.1. PKCE Still Requires OP Support

If the AS does not support PKCE or skips verifying it, adding a builder customizer is not enough to stop code interception. Verify that the AS actually rejects token requests with a wrong or missing verifier.

### 9.2. Do Not Call `withPkce` by Dropping `state`/`nonce`

`withPkce()` focuses specifically on PKCE. It **does not mean `state` is omitted**, nor is it a **nonce customizer**. Never write a new resolver that discards `state` or OIDC security attributes just to enable PKCE.

### 9.3. What Benefit Does PKCE Give a Confidential Client?

Even when a client secret is used at the token endpoint, binding the code to a specific verifier still reduces code injection/interception risks under the threat model conditions PKCE covers. Keep both client authentication and PKCE whenever the OP allows it.

---

## 10. Illustrative `application.yml` for OIDC + PKCE

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
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
          company:
            issuer-uri: https://id.example.test/realms/company
```

`issuer-uri` lets Spring Security fetch trusted metadata from the OP when supported. The authorization endpoint, token endpoint, JWK Set URI, and PKCE policy must be consistently supported by the provider.

In the configuration above:
- `openid` is the OIDC scope; the app expects an ID Token.
- `authorization_code` is the primary grant, distinct from `refresh_token`.
- `client_secret_basic` is the client authentication method, **not a substitute for PKCE**.
- `redirect-uri` must match the URI registered at the OP.
- `client-secret` is a backend secret and must never be sent to the browser.
- The resolver with `withPkce()` in Section 9 shows how to enable PKCE explicitly if needed.

### 10.1. What About Public Clients?

A public client cannot hold a client secret. Spring Security supports `client-authentication-method: none`, combined with Authorization Code + PKCE per framework configuration. Never embed a fake client secret in an SPA/mobile app or assume a frontend code verifier is completely immune to XSS.

### 10.2. Browser-Based Apps and BFF

When the application is a **Backend-for-Frontend (BFF)**:
- The browser holds the BFF session cookie;
- The backend holds access/refresh tokens and the PKCE verifier server-side;
- The Authorization Code callback is processed by the backend;
- The browser never needs to touch the refresh token.

A BFF reduces browser token exposure but still requires CSRF/cookie protection, `state`, PKCE, and OIDC `nonce`/ID Token validation.

---

## 11. Where Are `state`, `code_verifier`, and `nonce` Stored?

In Spring Security Servlet, **`HttpSessionOAuth2AuthorizationRequestRepository`** is typically the default repository keeping `OAuth2AuthorizationRequest` across redirects.

Logical model:

```text
Browser cookie:
  JSESSIONID = opaque-session-id

Server HttpSession:
  pending OAuth2AuthorizationRequest:
    registrationId  = company
    state           = S
    redirectUri     = https://app.example.test/login/oauth2/code/company
    scopes          = [openid, profile]
    attributes      = [PKCE verifier, OIDC nonce context, ...]
    additionalParams = [code_challenge, code_challenge_method, nonce, ...]
```

Do not assume every Spring Security version uses the exact same **attribute key names** or nonce representation inside `attributes`; internal framework handling can vary.

### 11.1. Why Not Put the Verifier in a Plaintext Cookie?

If an app creates its own cookie:

```text
Set-Cookie: code_verifier=<secret>
```

and relies on the browser sending the verifier without proper integrity/session binding, exposure and tampering risks increase. For a Servlet confidential client, storing it in the server-side authorization request repository is more practical and appropriate.

### 11.2. `state` Must Match the Browser's Session

The RP session-identifier cookie lets the callback find the original request. If the cookie differs or is missing:

```text
Start login:
  Session A -> state S

Callback:
  Session B -> state S, but no matching original request
```

Safe behavior: **reject** and require starting a new flow; never query a global map by `state` while ignoring session boundaries.

### 11.3. Never Use an Infinite Timeout

A pending authorization request is a short-lived transaction. If building a custom repository/database:
- Set a TTL;
- Bound the number of pending flows;
- Delete once completed/consumed;
- Protect stored data;
- Handle concurrency;
- Never store raw authorization requests in client-side `localStorage`.

A long session timeout does not keep an authorization code/nonce valid forever; the AS still enforces code lifetime and its own constraints.

### 11.4. Session Fixation and Cookies

When a user logs in successfully, Spring Security provides session fixation protection and security context persistence. However, the `state`/`nonce` flow happens **before the user is authenticated**, so creating/holding the pending session must still be protected:
- HTTPS;
- `Secure` and `HttpOnly` cookie attributes in production;
- `SameSite` compatible with the OIDC callback;
- Exact cookie domain/path;
- Session ID never exposed in URLs/logs;
- Prevent attackers from fixing a victim's session ID.

---

## 12. Callbacks Must Be Single-Use and Fail Closed

A secure workflow:

```text
GET /login/oauth2/code/company?code=C&state=S
        |
        v
Load matching authorization request from session
        |
        +-- None -> reject callback
        |
        v
Confirm state matches and transaction context valid
        |
        v
Remove/consume pending request
        |
        v
Exchange C with correct verifier V
        |
        +-- invalid_grant -> reject
        |
        v
Validate ID Token (+ nonce when used)
        |
        +-- invalid token -> reject
        |
        v
Create Authentication
```

**Removing** the authorization request limits the client from reprocessing a callback. However, the **AS must also enforce one-time authorization codes**; removing `state` on the client does not replace one-time code enforcement at the AS.

### 12.1. Replaying a Callback URL

First time:

```text
/login/oauth2/code/company?code=C1&state=S1
```

completes; the original request is consumed. If the same URL arrives again:

```text
/login/oauth2/code/company?code=C1&state=S1
```

the client should find no pending transaction to re-authenticate. If the token endpoint is ever called anyway, the AS must also reject the already-used code.

**Never write fallback logic like "state was already used, but try the code anyway"**.

### 12.2. Callback Errors Also Require Exact Correlation

The OP may return:

```text
/login/oauth2/code/company?error=access_denied&state=S1
```

Even though it is an error, it is still an authorization flow response. Do not use raw `error_description` to determine which user is logging in, and do not skip `state` binding merely because the OP returned an error.

### 12.3. Reject When the Request Is Lost

A browser holding a callback URL from yesterday no longer has the `HttpSession` or pending request. Never "recover via the code" or look up a global collection by raw `state` without session binding; ask the user to start a fresh flow.

---

## 13. Multiple Tabs and Parallel Authorization Flows

A browser can initiate two flows:

```text
Tab A -> Company, state=A, verifier=V_A, nonce=N_A
Tab B -> Partner, state=B, verifier=V_B, nonce=N_B

Callback B returns first
Callback A returns later
```

If a repository **only keeps a single pending request slot in the session**, flow B may overwrite A. When callback A arrives, `state` mismatches. This can be a **storage/concurrency limitation**, not an AS sending the wrong token.

### 13.1. Do Not "Solve" Multi-Tab by Skipping Matching

Wrong:

```text
If state mismatches -> grab latest request -> try latest code_verifier
```

This can mix codes/verifiers/nonces across requests or providers, opening the door to login CSRF, account mix-up, and authorization failures.

If the product needs multi-tab/parallel authorization:
- Check the repository behavior of your specific Spring Security version;
- Key the store by **(session, state)** or equivalent;
- Enforce clear TTLs and maximum pending requests;
- Remove only the matched entry;
- Perform atomic updates to prevent lost writes;
- Never let a callback pick an arbitrary session;
- Ensure one flow cannot overwrite another flow's PKCE verifier/nonce.

### 13.2. Multiple Providers Must Not Share One Set of Values

Do not generate a global `state` or `code_verifier` shared across Company and Partner. Each authorization request must have its own context; provider identity/issuer must be bound to the exact request.

### 13.3. Triaging Multi-Tab Errors

If callback A hits a state mismatch while OP A is healthy, do not mark OP A as unavailable. Investigate browser sessions, cookies, repository model, and concurrency before blaming the provider.

## 14. Multiple Providers: Preventing Authorization Server Mix-Up

A system may integrate:

```text
company -> issuer https://id.company.example.test
partner -> issuer https://id.partner.example.test
```

Each provider has its own:
- Authorization endpoint;
- Token endpoint;
- Client ID and client authentication;
- Redirect URI/policy;
- JWKS;
- Issuer;
- ID Token validation;
- Per-flow `state`/`nonce`/PKCE context.

**Authorization Server mix-up** is a class of attacks/bugs where the client mistakes which AS started the flow and sends the code/token to the wrong endpoint or trusts a response from a different provider.

### 14.1. `state` Alone Does Not Verify the Issuer

`state` binds the callback to the saved request, yet the client must also determine **which issuer/provider the original request belonged to**. A multi-AS implementation must bind the authorization response to the right AS, rather than trusting just a path or browser-supplied input.

Risk mitigations include:
- Fixed/trusted `ClientRegistration`s;
- Exact token endpoint mapping;
- Authorization response issuer identification (e.g., `iss` per RFC 9207 when AS supports it);
- Distinct redirect URIs where appropriate;
- ID Token issuer/audience validation;
- Never taking the token endpoint from a query parameter;
- Never switching registrations after the callback arrives.

### 14.2. PKCE Does Not Prove the Issuer

A verifier protects the code exchange, but it does not prove "this is definitely Company OP" if the client sends the authorization code and verifier to the **wrong endpoint**.

AS endpoint selection must come from trusted registration/context, never from an attacker-controlled callback parameter.

### 14.3. `nonce` Does Not Replace Issuer

An ID Token with a matching `nonce` whose `iss` does not match the configured OP must still be rejected. Never accept an ID Token from another provider merely because subject or email matches.

### 14.4. Subject Identity

An OIDC user identifier is at least:

```text
(issuer, subject)
```

Never use `sub` alone or email as a global identity key across providers. That is a major account mix-up risk that `state`/`nonce`/PKCE do not solve at the business layer.

---

## 15. What Do PKCE, `state`, and `nonce` Still Protect When an Attacker Has Other Pieces?

| Attacker controls/obtains | How does `state` help? | How does PKCE help? | How does `nonce` help? | What else is needed? |
| --- | --- | --- | --- | --- |
| Knows only authorization code | Binds callback | Hard to exchange code without verifier | ID Token binding after exchange | One-time code, AS binding |
| Has callback URL from browser history | Rejected when transaction is no longer pending/same session | Verifier is not in URL | ID Token bound to request | Session binding, TTL, log redaction |
| Has code + challenge | Correlation still needed | Challenge cannot reveal verifier under S256 | Does not handle code exchange | CSPRNG, TLS, protected verifier |
| Has code + verifier | Still needs state/callback binding | PKCE may be bypassed | Protects ID Token use if different request | Client authentication, AS one-time/redirect binding |
| Has old ID Token | Not directly used to validate ID Token | Does not stop ID Token replay | Can reject old nonce in new transaction | Signature/iss/aud/exp validation |
| Has valid bearer access token | No | No | No | DPoP/mTLS, expiry, scope/audience, secure storage |
| Has refresh token | Not directly | Not directly | Not directly | Rotation, reuse detection, sender binding |
| Controls wrong token endpoint URL | Does not fully solve | Code/verifier may leak to wrong endpoint | Does not fully solve | Trusted registration, issuer/mix-up protection |
| XSS in SPA | Session/browser may be compromised | Verifier can be stolen | Nonce can be exposed/manipulated | CSP, XSS defense, BFF/token containment |
| Has client secret | Does not protect callback itself | Adds barrier to code replay | Does not replace ID Token validation | Secret rotation, least privilege |

**A real threat model matters more than checking "do all three parameters appear in the URL?"**

## 16. Access Token Replay Is a Separate Problem

Bearer access tokens normally have the property: **anyone holding a valid token can call the API within the token's permissions**.

```text
Attacker steals access token T
        |
        v
GET https://api.example.test/v1/report
Authorization: Bearer T
        |
        v
Resource Server decides whether to accept T
```

At that point, the Resource Server usually does not see:
- Login `state`;
- `code_verifier`;
- ID Token `nonce`.

Therefore, you cannot claim "since we use PKCE and nonce, access tokens cannot be replayed."

### 16.1. Measures to Mitigate Bearer Token Replay

- **TLS/HTTPS** across the entire transport path;
- Never place tokens in URL query strings;
- Never log `Authorization` headers or token responses;
- Store tokens on the backend or in an appropriate secure store;
- Reasonable access token lifetimes;
- Least-privilege scopes and audiences;
- Resource Server verification of issuer, audience, signature/expiry, or introspection;
- Revocation/token lifecycle policies;
- Consider **sender-constrained access tokens** such as DPoP (RFC 9449) or OAuth 2.0 mTLS (RFC 8705);
- Protect XSS/CSRF/sessions for browser-based apps.

### 16.2. What Is DPoP?

**DPoP (Demonstrating Proof of Possession)** binds a token to a client key pair and requires a proof when calling the API. The Resource Server verifies the DPoP proof, HTTP method/URI, timestamp, unique identifier, and key binding per spec.

DPoP also has its own **proof replay** protection, typically via `jti`, timestamp, and a DPoP nonce when required by the AS/RS.

**A DPoP nonce is different from an OIDC nonce.** Never reuse an OIDC ID Token nonce as a DPoP proof nonce, even though both share the name `nonce`.

### 16.3. mTLS Sender-Constrained Access Tokens

In OAuth mTLS, tokens can be bound to a client certificate. The Resource Server checks the certificate when receiving the token; an attacker possessing only the token without the matching private key/certificate cannot easily reuse it.

Implementation depends on the AS, RS, and infrastructure. Spring Security OAuth2 Client does not automatically make all tokens sender-constrained simply because you enabled PKCE.

### 16.4. Refresh Token Rotation

To mitigate refresh token replay, the OP can issue `R2` when the client uses `R1`, invalidating `R1` and detecting reuse.

```text
R1 -> refresh -> A2 + R2
R2 -> refresh -> A3 + R3

Attacker retries R1:
  AS detects reuse / invalid_grant
  may revoke token family according to policy
```

Refresh token rotation requires careful concurrency handling on the client because two requests refreshing the same token concurrently can trigger false reuse detection and session loss.

---

## 17. ID Token Replay and Complete Validation

An ID Token can be a signed JWT, yet **a valid JWT signature does not mean the token belongs to the current login flow**.

The client must verify:
- **`iss`**: exact issuer of the registered OP;
- **`aud`**: application's client ID is present in the audience;
- **`azp`**: authorized party when required by OIDC conditions;
- **`exp`** and time constraints;
- **Signature**: trusted algorithm/keys of the right OP;
- **`nonce`**: when sent/required by flow, must match expected nonce;
- Other OIDC constraints appropriate to the response type/flow;
- UserInfo **`sub`** must match the ID Token if UserInfo is used.

### 17.1. Why Not Accept a Raw ID Token from the Client Browser?

An arbitrary endpoint:

```http
POST /api/login
Content-Type: application/json

{"id_token":"JWT_FROM_BROWSER"}
```

does not become an OIDC Authorization Code Login simply because the JWT signature is valid. It may lack state/nonce/transaction context, and the token may have been issued for a different client.

If a system builds a custom login/token-exchange flow, it must apply an appropriate trust model/nonce/audience/issuer/anti-replay design rather than manually parsing a JWT and creating an unverified Authentication.

### 17.2. A Valid `nonce` Does Not Bypass Expiry

An old ID Token whose `nonce` happens to match due to verifier/nonce reuse or broken transaction storage must still obey expiration and all other checks. **All validations are conjunctive (AND)**, not OR.

### 17.3. `c_hash` and `at_hash` in OIDC

Certain OIDC flows, especially **Hybrid/Implicit**, include `c_hash` or `at_hash` claims to bind the authorization code/access token to the ID Token per OIDC Core.

These are **additional mechanisms** for their respective flows, not the same as PKCE `code_challenge`:
- `c_hash` is computed from the authorization code per the specified algorithm;
- `at_hash` is computed from the access token;
- PKCE challenge is the hash of **`code_verifier`**;
- `state` is the correlation string from the authorization request;
- `nonce` is the authentication-request-binding claim.

Never apply the PKCE S256 formula to `c_hash` or vice versa. With modern Authorization Code Flow, prefer framework OIDC validations rather than writing validations for unused response types.

---

## 18. Spring Security Reactive WebFlux: Comparison

In WebFlux, the protocol is the same, but the API classes differ:

| Servlet | Reactive WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |
| `AuthorizationRequestRepository` | `ServerAuthorizationRequestRepository` |
| `OAuth2AuthorizationRequestRedirectFilter` | `OAuth2AuthorizationRequestRedirectWebFilter` |
| `OAuth2LoginAuthenticationFilter` | Reactive OAuth2 code login filters/converters |
| Blocking result | Reactor `Mono` |

Basic `SecurityWebFilterChain` example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Spring Security WebFlux uses `ServerOAuth2AuthorizationRequestResolver` and a reactive repository to create/save/correlate authorization requests. To customize PKCE or nonce, use the **Reactive extension points**—never copy Servlet's `DefaultOAuth2AuthorizationRequestResolver` into `ServerHttpSecurity`.

### 18.1. Reactive Save/Load/Remove Must Be Composed

```java
Mono<Void> saved =
    repository.saveAuthorizationRequest(authRequest, exchange);
```

Merely constructing a `Mono` and ignoring it **does not guarantee the request is saved**. The standard framework composes the publisher before redirecting.

```java
// Correct concept:
return repository.saveAuthorizationRequest(authRequest, exchange)
    .then(redirectToProvider());
```

`redirectToProvider()` is a pseudocode method returning `Mono<Void>`, not a built-in API. Never call `.block()` on the event loop.

### 18.2. `WebSession` and Multiple Instances

If the auth flow begins on node A and the callback arrives at node B, you need a suitable `WebSession` store, such as Spring Session/Redis, or a proven deployment strategy. Lost session ⇒ lost `state`/PKCE verifier/`nonce` context ⇒ **reject callback**.

### 18.3. Never Treat PKCE as a Replacement for `WebSession`

Even though the OP checks PKCE, the RP must still correlate the callback with the original authorization request and the right principal/browser. Never drop `state` handling simply because the Reactive client has PKCE.

## 19. Reverse Proxies, `SameSite` Cookies, and Correlation Errors

A production environment:

```text
Browser https://app.example.test
    |
    v
Ingress / TLS termination
    |
    v
Spring Boot http://app-internal:8080
```

If `redirect_uri` is built as `http://app-internal:8080`, the OP may reject with `redirect_uri_mismatch`, or the callback may return to a different origin, losing cookies.

### 19.1. Forwarded Headers

Spring Boot may require:

```yaml
server:
  forward-headers-strategy: framework
```

Use this only if a trusted proxy **sanitizes/overwrites `Forwarded`/`X-Forwarded-*` headers**. Never trust raw `X-Forwarded-Host` from the Internet to construct redirect URIs.

### 19.2. `SameSite` Cookies

In the standard OIDC Authorization Code Flow, the OP redirects the browser via a **top-level GET** to the callback. A `SameSite=Lax` cookie is typically compatible here.

With `response_mode=form_post` (cross-site POST), `Lax` may cause the browser to withhold the session cookie. Then the callback cannot find the `state`/verifier/`nonce` context.

**Never "fix" this by disabling `state` validation.** Check response mode/CSRF/cookie policy and browser behavior. With `SameSite=None`, modern browsers generally require `Secure`; base the decision on your threat model.

### 19.3. Session Timeout

If the user spends too long at the OP:
- The pending authorization request may expire;
- The cookie/session ID may change;
- The callback `state` no longer matches.

The right behavior is to report an expired login session and start a new flow. Never relax correlation to accept stale callback URLs.

---

## 20. Do Not Leak Security Data in Logs

Authorization redirects/callbacks can contain:
- `code`;
- `state`;
- `code_challenge`;
- `nonce`;
- Provider error descriptions.

Token endpoint requests contain:
- `code_verifier`;
- `client_secret` or client assertion;
- Authorization code;
- Refresh token.

Token endpoint responses contain:
- Access token;
- ID Token;
- Refresh token.

**Never log raw request/response bodies and headers** for these endpoints in production.

### 20.1. Minimal Logging

Example event:

```json
{
  "event": "oidc_login_flow",
  "registration_id": "company",
  "phase": "callback_validation",
  "outcome": "state_mismatch",
  "trace_id": "internal-correlation-id"
}
```

This is an application schema, not Spring Security's default log output. Never use raw OAuth2 `state` as a trace ID.

### 20.2. Do Not Print `nonce` Even Though It Is "Not an Absolute Secret"

`nonce` passes through the browser, yet it remains correlation context. Logging raw `nonce` unnecessarily links transaction details and increases telemetry exposure. Log only the event category.

### 20.3. Avoid Query Strings in Access Logs

A request may be:

```text
/login/oauth2/code/company?code=SECRET_CODE&state=S123
```

Web servers, reverse proxies, CDNs, and APMs can all record paths/queries. Redact `code`, `state`, and sensitive fields. Never send raw callback URLs to analytics or error reports.

### 20.4. Do Not Expose `OAuth2AuthorizedClient` in JSON

A debug controller:

```java
// DO NOT return objects containing access/refresh tokens.
@GetMapping("/debug/token")
public OAuth2AuthorizedClient debug() { ... }
```

can expose tokens. Return filtered metadata (`registrationId`, token `expiresAt` if policy allows) and protect diagnostic endpoints.

## 21. Design Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Fixed `state` | Predictable/reusable correlation | Generate unpredictable `state` per flow |
| Fixed verifier | PKCE loses uniqueness | Use CSPRNG, fresh verifier per request |
| Using `plain` without reason | Verifier exposed in challenge | Prefer `S256` |
| Sending `code_verifier` in authorize URL | Leaks PKCE secret via browser | Send only the challenge |
| Sending verifier in callback query | Leaks verifier and breaks token request boundary | Keep server-side |
| Storing state/verifier in unprotected JS `localStorage` | XSS can steal credentials | BFF/server-side session where suitable |
| Not storing authorization request | No baseline to verify state/nonce | Use trusted repository |
| Allowing callback without `state` | Login CSRF/injection | Fail closed |
| Reusing an already-processed callback | Replay/login mix-up | Remove pending state, one-time code |
| Using `nonce` as sole `state` without flow analysis | Drops callback correlation | Follow framework/BCP properly |
| Checking only `nonce` without ID Token signature | Forged tokens trusted | Verify signature/iss/aud/exp |
| Dropping `nonce` validation after sending `nonce` | ID Token replay risk | Keep OIDC validation |
| Accepting ID Token from provider A for B | Mix-up/identity confusion | Issuer-specific trust |
| Using email to link users across OPs | Account takeover/mix-up | `(issuer, subject)` + linking policy |
| Using PKCE instead of client authentication | Confidential client unauthenticated | Use both when applicable |
| Silent fallback `S256` → `plain` | Weakens protection | Check OP support, do not silently downgrade |
| Retrying `invalid_grant` infinitely | One-time code, rate limits | New flow/controlled recovery |
| OP timeout ⇒ drop `state` check | Authentication bypass | Fix availability/session |
| Disabling CSRF just to make OIDC login work | Increases form and logout CSRF risk | Configure CSRF/endpoints properly |
| Storing only one pending flow when multi-tab needed | Overwrites state/verifier/nonce | Repo keyed by `(session, state)` |
| Callback on another node lacks session store | Correlation fails | Shared session/persistence |
| Leaked access token assumed safe due to PKCE | Bearer replay at API | Sender-constrained tokens and token hygiene |
| Stolen refresh token addressed only by incrementing nonce | Does not stop refresh replay | Rotation/reuse detection and secure storage |
| Logging callback query strings | Leaks code/state | Redact logs/APM |
| Letting user choose token endpoint | Credential exfiltration/SSRF | Trusted `ClientRegistration` and allowlist |
| Ignoring XSS that breaks PKCE security | Browser context compromised | CSP, input sanitization, secure architecture |

---

## 22. Attack Scenario Analysis

### Scenario A — Attacker Only Obtains Authorization Code

The attacker sees `code=C` in a leaked callback but **does not have `code_verifier`**.

**How does PKCE help?**

> The AS bound `code_challenge=S256(V)` to the code. When the attacker calls the token endpoint without `V`, the token request is rejected. Client authentication and other bindings remain necessary per flow.

### Scenario B — Attacker Has `code` and `code_challenge`

The attacker sees the code and public challenge in the browser URL.

**Can the verifier be derived?**

> With `S256` and a high-entropy verifier, deriving `V` from the SHA-256 challenge is infeasible under the assumed security model. Never use `plain` or a weak verifier.

### Scenario C — Authorization Response Injected into Another Browser

The attacker initiates a flow with `state=S_A` and sends the callback URL to the victim.

**How does `state` help?**

> The victim has no matching authorization request in their session. The client rejects the callback and never authenticates with the attacker's code.

### Scenario D — `state` Lost Due to Cookie

The user starts login, then the callback omits `JSESSIONID`.

**Should we accept the code anyway if PKCE is still enabled?**

> No. The client must locate the original authorization request/correlation context; fix `SameSite`, cookie domain/path, session persistence, or start a new flow.

### Scenario E — Valid ID Token from an Old Login

The attacker supplies an ID Token with a valid signature, right `iss`, unexpired `exp`, but a `nonce` from another request.

**How does `nonce` help?**

> Because the RP expects the current transaction's `nonce`, the stale token's `nonce` mismatches and is rejected. However, signature/issuer/audience/expiry must still be checked alongside it.

### Scenario F — Valid `nonce` but Wrong Issuer

The ID Token has a matching `nonce`, but `iss` belongs to a different OP.

**Should login succeed?**

> No. `nonce` does not replace issuer validation. Reject any ID Token not belonging to the provider registered for that flow.

### Scenario G — Stolen Access Token

A valid token `T` was issued, and the attacker obtains `T` and calls the API.

**Do PKCE/`state`/`nonce` directly help?**

> No. The Resource Server normally never sees those values. You need token lifetime/audience/scope/TLS/storage protections and sender-constrained tokens where appropriate.

### Scenario H — Authorization Code Used a Second Time

The client already exchanged code `C` for tokens, and later another request tries to exchange the same code `C`.

**Who must reject it?**

> The Authorization Server must enforce **one-time code use** and expiration. The client must also consume the original authorization request; never rely on `state` removal as the sole guard.

### Scenario I — Client Fails to Send `code_verifier`

The authorization request included a PKCE challenge, yet the token request omits `code_verifier`.

**Expected outcome?**

> The AS rejects it, typically with `invalid_grant` per proper error handling. Never "fix" this by disabling PKCE on token exchange.

### Scenario J — Using Another Tab's `code_verifier`

Tab A creates verifier `V_A`, Tab B creates `V_B`. Callback A accidentally uses `V_B`.

**Outcome?**

> PKCE mismatch; never try "iterating through all verifiers." The repository must store each flow independently.

### Scenario K — Switching Provider Token Endpoint from a Query Parameter

The app has Company and Partner; the callback receives `provider=partner` from the browser and sends Company's code to Partner's token endpoint.

**Risk?**

> Authorization server mix-up, leaking code/verifier/client credentials, and trust confusion. The token endpoint must come from the trusted stored registration/context, never raw callback input.

### Scenario L — Using `nonce` for OIDC Logout

A developer wants to reuse the ID Token's `nonce` as `state` for RP-Initiated Logout.

**Should they?**

> Not automatically. OIDC login `nonce` and logout-state correlation are two separate transactions. If the logout callback needs `state`, design it separately per the logout spec.

### Scenario M — Concurrent Refresh Token Rotation

Two requests refresh `R1` at the same time; the first receives `R2`, while the second gets `invalid_grant`.

**Is this a PKCE bug?**

> No. This is refresh-token lifecycle concurrency. Implement serialized refresh/locking/versioning and proper rotation/reuse detection handling.

### Scenario N — Replayed DPoP Proof

The Resource Server requires DPoP; an attacker copies a previously used proof.

**Does OIDC `nonce` prevent it?**

> No. DPoP uses a proof-specific `jti`, timestamp, and optionally a DPoP nonce required by the AS/RS. Do not confuse it with the OIDC authentication `nonce`.

### Scenario O — Authorization Endpoint Unreachable

The OP times out before redirecting back to the callback.

**Should we skip `state` in future attempts?**

> No. Availability and correlation are separate concerns. Let the user retry/start a new flow with appropriate timeouts/backoff; never weaken security to handle an OP outage.

### Scenario P — Two OPs Share the Same `sub` String

Company and Partner both issue `sub="42"`.

**Should they be treated as the same user?**

> No. Use the `(issuer, subject)` tuple and an account linking policy. `state`/`nonce` do not prove two accounts belong to the same person.

---

## 23. Designing Essential Tests

In a real Spring Security project, include integration tests with a **mock Authorization Server/OIDC test provider** to verify behaviors. These are **learning scenarios**, not an instruction to run repo tests while authoring the lesson.

### 23.1. PKCE Tests

| Test | Setup | Expected result |
| --- | --- | --- |
| `S256` request | Flow with PKCE enabled | Authorize URL has `code_challenge` + `code_challenge_method=S256` |
| Verifier generation | Two separate flows | Distinct verifiers, sufficient entropy/length |
| Token request | Callback for valid flow | Token endpoint receives exact `code_verifier` |
| Wrong verifier | Exchange code with different `V` | AS returns error; login fails |
| Missing verifier | Code bound to challenge | AS rejects |
| Plain downgrade | OP demands `plain` | Client does not silently downgrade |
| Intercepted code | Attacker has code without verifier | Cannot exchange for tokens |

### 23.2. `state` Tests

| Test | Setup | Expected result |
| --- | --- | --- |
| Happy path | Callback with matching `state`/session | Flow proceeds |
| Wrong state | Callback alters `state` | Rejected |
| Missing state | Callback omits `state` | Rejected if flow requires `state` |
| Wrong session | Callback from another browser | Request not found; rejected |
| Session timeout | Pending request expired | Callback cannot be reused |
| Replay | Resubmit callback after use | Cannot complete a second time |
| Multi-tab | Two pending flows | State/verifier/nonce never mixed |
| Unknown registration | Wrong callback URL/provider | Never fetches tokens from untrusted OP |

### 23.3. `nonce` & ID Token Tests

| Test | Setup | Expected result |
| --- | --- | --- |
| Matching nonce | ID Token from right request | Passes nonce validation when other checks pass |
| Wrong nonce | Token from another auth request | Rejected |
| Missing nonce | Flow sent nonce | Rejected per OIDC validation |
| Wrong issuer | Valid nonce but wrong `iss` | Rejected |
| Wrong audience | Valid nonce but wrong `aud` | Rejected |
| Expired ID Token | Valid nonce but expired `exp` | Rejected |
| Wrong signature | Valid nonce but invalid signature | Rejected |
| Wrong UserInfo `sub` | UserInfo subject differs from ID Token | UserInfo rejected |

### 23.4. Security Operations Tests

- No code/state/verifier/ID Token written to application/access logs.
- Session cookie has proper `Path`/`Domain`/`Secure`/`SameSite`.
- Callback behind reverse proxy builds the right public redirect URI.
- Session store works across multiple instances.
- Provider A failure does not cause OP B callbacks to be misprocessed.
- `invalid_grant` does not trigger a retry loop.
- When an access token is rejected, the Resource Server still enforces audience/scope.
- Each new authorization flow generates fresh `state`/verifier/`nonce`.

---

## 24. Symptom-Based Troubleshooting

| Symptom | Possibilities | What to check |
| --- | --- | --- |
| OP returns `invalid_grant` on token exchange | Code reused/expired, wrong verifier, redirect URI/client mismatch | Code lifetime, PKCE challenge/verifier, token request; do not log raw secrets |
| Callback has code but `authorization_request_not_found` | Session/state lost, wrong callback path | Cookies, session store, TTL, reverse proxy |
| One tab logs in, another gets state mismatch | Repository only holds one pending flow | Multi-tab design, key by state |
| Token endpoint does not receive verifier | PKCE not enabled or custom token client drops params | Request resolver, response client, `S256` |
| Authorize URL has `plain` | PKCE config/OP compatibility | Prefer `S256`, avoid downgrade |
| Client secret valid yet code exchange fails | PKCE verifier mismatch or code/redirect mismatch | Client auth does not replace PKCE |
| ID Token nonce mismatch | Mixed requests, old nonce, callback outside flow | Authorization request context, OIDC validation |
| ID Token issuer mismatch | Wrong OP, mix-up, issuer config | Registration, `iss`, JWK set |
| Cannot fetch JWKS | Network/OP outage or rotation | Cache policy, fail closed |
| Token validation passes but wrong user | Account linking by email/bare `sub` | Key by `(issuer, sub)` |
| Post-login API returns 401 | Wrong audience/expired/revoked token | Resource Server validation, right token |
| PKCE enabled yet API token replayed | Bearer token theft | Token hygiene/DPoP/mTLS |
| Token still works after logout | Logout does not auto-revoke | Token lifecycle/RS policy |
| Redirect callback points to `localhost` in production | Proxy/`baseUrl` misconfigured | Trusted forwarded headers, redirect registration |
| `form_post` callback missing session | `SameSite=Lax` on cross-site POST | Appropriate cookie/response mode |
| WebFlux callback cannot find request | Reactive publisher not composed or `WebSession` lost | `Mono` save/load/remove, session store |
| Custom provider selector reads raw query | Token endpoint/trust confusion | Backend-allowlisted registrations |
| Logs contain `code_verifier` | Debug HTTP body logging | Redaction/secrets handling |
| OP supports code but not PKCE `S256` | Legacy provider | Compatibility/security review; do not blindly disable PKCE |
| Callback replay succeeds | State not consumed, AS code reuse bug | One-time semantics, repository cleanup, AS validation |
| Raw nonce comparison fails in custom code | Framework uses internal representation | Use built-in OIDC validation |
| POST callback returns CSRF 403 | Response mode/filter configuration | Never disable CSRF globally; configure flow properly |
| Multi-instance fails intermittently | Unshared in-memory sessions | Spring Session/Redis or suitable routing |

### 24.1. Do Not Blame PKCE for Every `invalid_grant`

`invalid_grant` can be caused by:
- Expired/reused authorization code;
- Redirect URI mismatch;
- Wrong client registration;
- Code issued to another client;
- Wrong PKCE verifier;
- Other AS policies.

Therefore, log categorized outcomes and inspect redacted request metadata rather than immediately concluding "PKCE is broken."

### 24.2. Do Not Blame the OP for Every `nonce` Mismatch

If `nonce` mismatches:
- `state`/session/authorization request may be mixed up;
- A code may have come from another flow;
- Custom code may be comparing the wrong representation;
- The provider may be returning `nonce` contrary to contract.

**Never remove `nonce` validation** to diagnose the issue. Isolate each layer to find the root cause.

---

## 25. Integration Security Design Checklist

When reviewing a production OAuth2/OIDC Client, ask:

1. Does the Authorization Code Flow use PKCE `S256` when supported/required by the OP?
2. Is the verifier CSPRNG-generated, fresh per flow, and of sufficient length?
3. Is the verifier kept strictly in trusted transaction context and sent only to the token endpoint?
4. Does the AS actually verify the verifier matches the challenge bound to the code?
5. Does the callback verify `state` against the original browser/session-bound request?
6. Does the pending authorization request have a TTL and one-time consumption?
7. Does OIDC login preserve `nonce` binding without bypassing validation?
8. Is the ID Token verified for issuer, audience, signature, expiry, and relevant OIDC checks?
9. Do multi-provider setups enforce trust boundaries per registration/issuer?
10. Do APIs receiving access tokens validate issuer/audience/scope/expiry or introspection?
11. Are access/refresh tokens protected from logs/XSS and stored at the right layer?
12. Have sender-constrained tokens been evaluated if bearer replay is a high risk?
13. Are session cookies, `SameSite`, HTTPS, and reverse proxy compatible with callbacks?
14. Can multiple tabs/nodes cause loss of `state`/verifier/`nonce`?
15. Are authorization codes never auto-retried and consumed callbacks never reused?
16. Are provider switching and token endpoints prevented from following untrusted input?
17. Are email or bare `sub` avoided for cross-provider user linking?
18. Are negative tests present for `state` mismatch, verifier mismatch, and wrong `nonce`?
19. Does observability distinguish callback errors, PKCE errors, ID Token errors, and Resource Server errors?
20. Is recovery handled by initiating a **new flow**, never by lowering security?

These questions are **learning material / an architectural checklist**, not an instruction to execute STEP 5 QA or run tests while authoring Markdown.

---

## 26. Self-Check Questions

### Question 1. What does PKCE stand for and what does it protect?

> **Proof Key for Code Exchange**. It binds the token exchange to the authorization request that generated the challenge, mitigating the risk of an attacker exchanging a captured authorization code for tokens.

### Question 2. In `S256`, what is the `code_challenge` formula?

> `BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))`.

### Question 3. Is `code_verifier` sent in the authorization request or token request?

> **Token request**. The authorization request sends **`code_challenge`** and **`code_challenge_method`**.

### Question 4. When does the client check `state`?

> When receiving the authorization response/callback, comparing it against the original authorization request in the repository and appropriate browser/session context.

### Question 5. What is `nonce` compared against?

> Against the **`nonce` claim in the ID Token** issued by the OP, according to the flow/representation handled by the OIDC client framework.

### Question 6. Does a valid `nonce` allow skipping ID Token signature validation?

> **No.** `nonce` is an additional binding check; signature, issuer, audience, expiry, and other checks must still pass.

### Question 7. If you already have a client secret, can you drop PKCE?

> You should not reason that way. Client authentication and PKCE defend against different threats; use PKCE `S256` per AS support/policy.

### Question 8. Callback has a valid code but wrong `state`. Should we try calling the token endpoint?

> **No.** The callback does not belong to a verified original authorization request; reject the flow and never bypass correlation.

### Question 9. A JWT access token is stolen. Does PKCE block replay at the API?

> **Not directly.** PKCE protects the authorization code exchange. API token replay requires audience/scope/expiry validation and sender-constrained tokens like DPoP/mTLS where appropriate.

### Question 10. Why not reuse the same `code_verifier` for every login?

> It violates freshness/unpredictability of PKCE binding, weakens protection against code interception/injection, and creates unsafe correlation across flows.

### Question 11. Why not place `code_verifier` in the browser redirect URL?

> URLs can leak via browser history, proxy logs, referrers, or analytics; the verifier must be kept safe until the token request.

### Question 12. Does OIDC Code Flow always require `nonce` by spec?

> Not in every case: `nonce` is optional in the Authorization Code Flow per OIDC Core, yet **if the flow sends `nonce`, it must be verified properly**, and it provides an important protection layer. Other response types have their own `nonce` rules.

### Question 13. Which default repository does Spring Security Servlet use?

> **`HttpSessionOAuth2AuthorizationRequestRepository`**, implementing the `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` contract.

### Question 14. Which repository does Spring Security WebFlux use?

> **`WebSessionOAuth2ServerAuthorizationRequestRepository`**, implementing the `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` contract.

### Question 15. Parallel login in two tabs causes `state` to be overwritten. Should we accept callbacks even if they don't match?

> **No.** Design the repository to support multiple pending requests if the product requires it, preserving exact matching and one-time consumption.

### Question 16. Providers A and B both return `sub="123"`. Are they the same person?

> No. OIDC identity requires the issuer; use at least `(iss, sub)` with a dedicated account linking policy.

### Question 17. How does RFC 9207 relate?

> It defines **issuer identification in the OAuth2 authorization response**, helpful for preventing authorization server mix-up in multi-AS clients. It is a separate layer from PKCE/`state`/`nonce`.

### Question 18. How does a DPoP nonce differ from an OIDC `nonce`?

> A DPoP nonce belongs to proof-of-possession/replay management when calling an AS/RS; an OIDC `nonce` binds an ID Token to an authentication request.

### Question 19. If the token endpoint returns `invalid_grant`, should we disable PKCE and retry the code?

> **No.** Determine whether it is code expiry/reuse/redirect/PKCE mismatch and start a new flow when needed. Never lower security on error.

### Question 20. Why protect cookie `SameSite`/`Path`/`Domain`?

> Because the callback must return to the right session to locate the `state`/verifier/`nonce` context. Losing the cookie breaks correlation.

### Question 21. Why not verify only the JWT signature?

> A validly signed token may belong to another issuer, another client, be expired, or belong to an old transaction. Full issuer/audience/expiry/`nonce` and applicable OIDC checks are required.

### Question 22. When a user refreshes an old callback page, what should the app do?

> Reject the already-consumed callback and, if appropriate, guide the user to start a new authorization flow; never reuse an authorization code.

---

## 27. Summary by Verification Boundary

```text
Authorization Request
    |
    +-- state generated         [Client: callback correlation]
    |
    +-- verifier generated      [Client: kept private]
    |        |
    |        +-- challenge S256(verifier) ---> Authorization Server
    |
    +-- nonce generated         [Client: expected OIDC ID Token binding]
    |
    v
Browser / OP authorization flow
    |
    v
Authorization Response
    code + state
    |
    +-- Client: state matches stored request/session?
    |      |
    |      +-- NO -> REJECT
    |      +-- YES -> continue
    |
    v
Token Request
    code + verifier
    |
    +-- AS: code valid, unconsumed, for correct client/redirect?
    +-- AS: S256(verifier) matches stored challenge?
    |      |
    |      +-- NO -> invalid_grant
    |      +-- YES -> issue tokens
    |
    v
ID Token Validation (OIDC)
    |
    +-- Signature, iss, aud, exp, nonce and other applicable claims?
    |      |
    |      +-- NO -> REJECT
    |      +-- YES -> Authentication allowed
    |
    v
Resource Server API
    |
    +-- Access token must still pass audience/scope/expiry checks
    +-- Bearer replay is separate; DPoP/mTLS when appropriate
```

**Key takeaways:**

1. **`state`** binds the **authorization response to the original request**; it must be stored/matched in the right browser context and consumed per transaction.
2. **PKCE `S256`** binds the **token request to the authorization request** via verifier/challenge; a client secret does not replace this role.
3. **OIDC `nonce`** binds the **ID Token to the authentication request**; it does not replace signature, issuer, audience, or expiry validation.
4. Together these three reduce code/callback/ID Token replay, yet **do not by themselves prevent bearer access token replay**.
5. **Spring Security provides built-in filters, repositories, and validators**; prefer narrow customizers like `OAuth2AuthorizationRequestCustomizers.withPkce()` over re-implementing the protocol.
6. **Do not mix Servlet and WebFlux**: `HttpSession` authorization request repositories differ from `WebSession` reactive repositories.
7. **Multi-tab flows, session timeouts, `SameSite`, and reverse proxies** can break correlation; never remove `state`/`nonce`/PKCE to work around operational errors.
8. **Multiple providers require issuer-specific trust and mix-up protections**, without falling back to another provider's tokens/JWKs/registration.
9. **Replay protection must cover the full lifecycle**: one-time codes, `state` consumption, ID Token validation, refresh token rotation, and sender-constrained access tokens where appropriate.
10. **Fail closed and log safely**: never print codes, verifiers, nonces, ID Tokens, access/refresh tokens, or session cookies.

### References

- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security 6.5 — Servlet OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html)
- [Spring Security 6.5 — Servlet OAuth2 Login Core](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html)
- [Spring Security 6.5 API — OAuth2AuthorizationRequestCustomizers](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html)
- [Spring Security 6.5 API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html)
- [Spring Security 6.5 API — HttpSessionOAuth2AuthorizationRequestRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html)
- [Spring Security 6.5 — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/index.html)
