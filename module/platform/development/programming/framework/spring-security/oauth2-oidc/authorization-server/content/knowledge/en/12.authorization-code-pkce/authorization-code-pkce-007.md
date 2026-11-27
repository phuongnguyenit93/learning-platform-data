# Applying PKCE for Public and Confidential Applications

## 1. Context and Learning Objectives

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Boot, Spring Security, and Spring Authorization Server**, many types of applications can share the **Authorization Code grant**: browser-based SPAs, mobile apps, desktop apps, backend websites, or Backends for Frontends (BFF).

A common misconception is: **"PKCE is only for public clients; confidential clients already have a client secret, so they don't need PKCE."** In reality, the two mechanisms solve **two different problems**. PKCE binds the authorization code to **the initiated transaction**; client authentication proves the client is authorized to use its credentials at the Token Endpoint. Under OAuth Security Best Current Practice (RFC 9700), public clients **MUST** use PKCE and confidential clients are **RECOMMENDED** to use PKCE to prevent code injection/misuse.

Within the **Authorization Code and PKCE** chapter, this lesson helps you:

1. Distinguish public vs. confidential clients and the independent role of PKCE compared to client authentication.
2. Generate `code_verifier` and `code_challenge` using **S256**, bound to each Authorization Code transaction.
3. Configure `RegisteredClient` with `ClientSettings.requireProofKey(true)` for **both** client categories.
4. Understand the responsibilities of the **Authorization Server** side and the **OAuth2 Client** side (especially when both are built with Spring).
5. Test defenses against missing verifiers, wrong verifiers, code replay, code injection, and PKCE downgrades.

**Scope limits:** This lesson focuses on Authorization Code + PKCE in Servlet/Spring Boot applications. API examples follow **Spring Authorization Server 1.5.x and Spring Security 6.x**; starting with **Spring Security 7.x**, Authorization Server is integrated into Spring Security and some defaults may change. Do not copy configurations across generations without checking documentation for your exact version.

## 2. Public, Confidential, and PKCE: Three Independent Questions

### 2.1. Classifying Clients by Credential Protection Capability

| Criterion | Public Client | Confidential Client |
|---|---|---|
| Typical runtime environment | JavaScript SPA, native mobile, user-distributed desktop/CLI | Web backend, BFF, server-to-server with secure credential storage |
| Can it keep a shared client secret confidential from end users long-term? | **Not reliably** | **Yes**, with proper infrastructure and secret management |
| Client authentication at Token Endpoint | Typically `none` with Authorization Code + PKCE | `client_secret_basic`, `private_key_jwt`, mTLS, or suitable method |
| PKCE with Authorization Code | **Mandatory per RFC 9700** | **Recommended per RFC 9700**; should be enabled by default policy |
| Where `code_verifier` is held | Short-lived client transaction state, protected from URL/log leakage | Server-side state of BFF/backend, bound to the browser session |

**Warning:** Bundling a `client_secret` into a JavaScript bundle, mobile APK/IPA, or desktop binary does not turn a public client into a confidential one. End users can still extract that secret. Conversely, a web app using server-side sessions/BFF can be confidential even though its UI runs in a browser, because **the actual OAuth client exchanging codes and holding the secret resides on the backend**.

### 2.2. How Does PKCE Differ from Client Authentication?

| Mechanism | What Does It Prove? | Value/Data Sent | When Is It Checked? |
|---|---|---|---|
| **Client authentication** | Request to Token Endpoint carries valid client credentials | Shared secret, signed JWT assertion, mTLS certificate… | Token Endpoint |
| **PKCE** | The party exchanging the code knows the `code_verifier` tied to the authorize request that produced the code | `code_challenge` first, `code_verifier` later | Authorization Endpoint + Token Endpoint |
| **`state`** | Authorization response belongs to a pending browser request/session | Random string or securely bound transaction data | Matched by client at callback |
| **OIDC `nonce`** | ID token is bound to the authentication session/authorization request | Nonce in authorization request and claim in ID token | Checked by OIDC client on ID token |

PKCE **is not a client authentication mechanism** and does not replace secrets, mTLS, or JWT client assertions when a confidential client is required to authenticate. Nor does it replace `redirect_uri` validation, `state`/CSRF checks, `nonce`, user authentication, consent, TLS, or token validation.

### 2.3. Why Do Confidential Clients Still Benefit from PKCE?

Suppose a BFF keeps its client secret safely on the server. An attacker might still:

- Inject or swap an authorization code into a callback/login transaction, causing **authorization code injection** or logging the victim into the wrong account if transaction binding is missing.
- Attempt to feed a valid code from another transaction to the client backend.
- Exploit an application that fails to bind the response to the browser session that initiated it.

A client secret only proves **the BFF holds valid credentials** at the Token Endpoint. It does not by itself prove the code being exchanged was created within **the current user's exact transaction**. When the BFF holds a per-transaction verifier and the Token Endpoint verifies S256, a code from another transaction will not match the verifier the BFF sends. Thus, PKCE adds an extra layer of protection for **confidential clients as well**.

## 3. PKCE Technical Rules per RFC 7636

### 3.1. Two Values: Verifier and Challenge

The client generates a **high-entropy random `code_verifier`** for **every authorization transaction**:

```text
code_verifier:  random string 43–128 characters long from set
                A-Z, a-z, 0-9, "-", ".", "_", "~"

code_challenge_method: S256

code_challenge = BASE64URL-ENCODE( SHA256( ASCII(code_verifier) ) )

Note: base64url WITHOUT "=" padding.
```

RFC 7636 recommends generating at least **256 bits of entropy**, such as 32 bytes from a CSPRNG followed by unpadded base64url encoding. With 32 bytes, the verifier is typically **43 characters** long, and the SHA-256 S256 challenge is also **43 characters** long.

**Never use** user passwords, client secrets, repeated session UUIDs, current timestamps, usernames, `state`, or a constant shared across requests as a verifier. Never place the verifier in the Authorization Endpoint query string: **only the challenge** is sent initially.

### 3.2. Why Choose S256 Instead of `plain`?

RFC 7636 defines two transformations:

- `S256`: `code_challenge = BASE64URL(SHA-256(ASCII(verifier)))`.
- `plain`: `code_challenge = verifier`; intended only for rare compatibility cases where a client cannot compute S256 and knows the AS supports plain.

**Default practice: use S256 only**. If `code_challenge_method` is omitted, RFC 7636 defines the default as `plain`, so an application capable of S256 must **explicitly send `code_challenge_method=S256`**. Never "fall back" from S256 to plain when a request fails.

Note: `requireProofKey(true)` requires a proof key per client policy, but **does not automatically imply every setup accepts only S256**. If system policy requires blocking `plain` altogether, verify the validator behavior of your Spring Authorization Server version and add tested validation where needed rather than assuming the PKCE flag means "S256-only".

### 3.3. Java Example for Generating Verifier and Challenge

This illustrative code runs on the **OAuth2 Client** (not processing logic inside the Authorization Server):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceUtil {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL_ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private PkceUtil() {}

    public record Pair(String verifier, String challenge) {}

    public static Pair newPair() {
        byte[] randomBytes = new byte[32]; // 256-bit entropy
        RANDOM.nextBytes(randomBytes);
        String verifier = URL_ENCODER.encodeToString(randomBytes);
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(StandardCharsets.US_ASCII));
            String challenge = URL_ENCODER.encodeToString(digest);
            return new Pair(verifier, challenge);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }
}
```

Usage example:

```java
PkceUtil.Pair pkce = PkceUtil.newPair();
// pkce.challenge() is sent in /oauth2/authorize with method=S256.
// pkce.verifier() is stored safely per client login transaction,
// then sent later at /oauth2/token; NEVER log either value in production.
```

Java 17+ code using `record`, SHA-256, unpadded Base64 URL encoder, and random entropy. If you already use `spring-security-oauth2-client` for login, **prefer its built-in PKCE support** instead of writing your own verifier helper unless you truly need to drive a custom OAuth client.

## 4. End-to-End Authorization Code + PKCE Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser / User
    participant C as OAuth2 Client (SPA or BFF)
    participant AS as Authorization Server
    participant DB as OAuth2AuthorizationService
    C->>C: Generates random verifier, challenge=S256(verifier)
    C->>C: Saves verifier with state and login session
    C-->>U: Redirects to /oauth2/authorize
    U->>AS: client_id, redirect_uri, state, code_challenge, S256
    AS->>AS: Checks client, redirect URI, PKCE, user/consent
    AS->>DB: Saves authorization code + bound challenge/method
    AS-->>U: Redirect callback?code=...&state=...
    U->>C: Sends authorization code + state to callback
    C->>C: Matches state; retrieves transaction verifier
    C->>AS: POST /oauth2/token (code, code_verifier, client auth if needed)
    AS->>DB: Looks up authorization code and initial PKCE data
    AS->>AS: Verifies code, S256 verifier, client, redirect, and expiry
    AS->>DB: Marks code used; saves token state
    AS-->>C: Access token (+ ID/refresh token if applicable)
```

**Some internal steps vary by grant/version**, but the boundaries stay constant: the verifier must not be exposed on the front channel when requesting a code; the AS binds the challenge to the authorization; only the matching verifier can exchange the code for tokens.

### 4.1. Step 1: Initiating the Authorization Request

Example client `spa-ui`:

```http
GET /oauth2/authorize?response_type=code
  &client_id=spa-ui
  &redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback
  &scope=openid%20profile
  &state=STATE_BOUND_TO_THIS_LOGIN
  &code_challenge=S256_CHALLENGE_BASE64URL
  &code_challenge_method=S256
```

Strings like `STATE_BOUND_TO_THIS_LOGIN` and `S256_CHALLENGE_BASE64URL` are **placeholders**, not runnable values. In real requests, they must be generated from secure randomness and bound to a single login attempt. OIDC clients must also send and validate `nonce` when required by profile/flow.

Authorization Server:

1. Looks up `RegisteredClientRepository.findByClientId("spa-ui")`.
2. Verifies `authorization_code` grant, exact callback, scopes, and client status per policy.
3. Checks PKCE requirements (presence of challenge and accepted method).
4. Performs user authentication and consent when required.
5. Creates a short-lived authorization code and **stores the challenge/method bound to the authorization** for verification during code exchange.

**Important:** when `client_id` or `redirect_uri` is invalid, the Authorization Server must never redirect authorization errors to an unverified URI. PKCE **does not** replace redirect URI validation.

### 4.2. Step 2: Authorization Server Redirects the Code

When the request is approved:

```http
HTTP/1.1 302 Found
Location: https://spa.example.com/callback?code=AUTHORIZATION_CODE&state=STATE_BOUND_TO_THIS_LOGIN
Cache-Control: no-store
```

The code is a **short-lived, single-use** credential. The client receiving the callback must verify `state` before completing the code exchange; never assume a code is trustworthy simply because the callback arrived from a browser.

### 4.3. Step 3: Exchanging Code for Tokens — Public Client

A public client does **not** send a shared client secret:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&client_id=spa-ui
&code=AUTHORIZATION_CODE
&redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback
&code_verifier=THE_ORIGINAL_SECRET_VERIFIER
```

Line breaks in the body are for readability; an actual HTTP form request must be properly URL-encoded and formatted as a standard request body. `client_id` is sent because the client does not authenticate with a secret. `code_verifier` must match the challenge stored for that exact transaction.

At the Token Endpoint, the AS verifies the code is unused/unexpired, client/redirect match, and:

```text
BASE64URL(SHA256(ASCII(received_code_verifier)))
    == stored_code_challenge
```

If this fails, the Token Endpoint **issues no tokens** and typically returns OAuth error `invalid_grant`. Knowing `client_id` does not bypass PKCE.

### 4.4. Step 3: Exchanging Code for Tokens — Confidential Client

A confidential client uses **both** client authentication and PKCE:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=AUTHORIZATION_CODE
&redirect_uri=https%3A%2F%2Fbff.example.com%2Flogin%2Foauth2%2Fcode%2Fbff
&code_verifier=THE_ORIGINAL_SECRET_VERIFIER
```

`Authorization` here is an **illustration** of `client_secret_basic`; never use placeholder strings as real credentials. With `private_key_jwt` or mTLS, how client identity is proven differs, yet **the verifier must still be sent** whenever the transaction uses PKCE.

The Token Endpoint checks **two independent conditions**:

1. The confidential client's credentials are valid and permitted for the grant.
2. Code + verifier belong to the exact authorization transaction, with matching client, callback, and status.

A valid client secret **never allows skipping the verifier** when the registration requires PKCE.

## 5. Configuring `RegisteredClient` in Spring Authorization Server

### 5.1. Two `RegisteredClient`s Both Enabling PKCE

Sample Java configuration for demo/testing (Spring Authorization Server 1.5.x):

```java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration(proxyBeanMethods = false)
public class PkceClientRegistrationConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClients(
            PasswordEncoder passwordEncoder,
            @Value("${PKCE_BFF_SECRET}") String bffSecret) {

        RegisteredClient publicSpa = RegisteredClient
                .withId("spa-internal-id")
                .clientId("spa-ui")
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("https://spa.example.com/callback")
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        RegisteredClient confidentialBff = RegisteredClient
                .withId("bff-internal-id")
                .clientId("bff")
                .clientSecret(passwordEncoder.encode(bffSecret))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://bff.example.com/login/oauth2/code/bff")
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(publicSpa, confidentialBff);
    }
}
```

Details:

- **Public SPA**: `ClientAuthenticationMethod.NONE`, **no** client secret, uses Authorization Code + PKCE.
- **Confidential BFF**: `CLIENT_SECRET_BASIC` **and** `requireProofKey(true)`; uses a secret injected from environment/secret manager, never plaintext in source code.
- Both clients share **the same PKCE protocol** while using **different client authentication methods**.
- `requireAuthorizationConsent(true)` illustrates consent policy and **is not a prerequisite for PKCE to work**.
- `InMemoryRegisteredClientRepository` is only suited for demos/tests; production needs persistence, credential rotation, and secret protection. If the project already defines a `PasswordEncoder` bean, avoid accidentally registering a duplicate bean with the same name.

**Version-dependent defaults:** **Spring Authorization Server 1.5.x** Javadoc states `ClientSettings.isRequireProofKey()` defaults to **`false`**; **Spring Security 7.x** documentation states the default is **`true`** for Authorization Code. Therefore, in systems where PKCE must never be turned off, **explicitly set `requireProofKey(true)` for each client** and write actual tests instead of relying on library defaults.

### 5.2. Declaring via `application.yml` (Spring Boot 3.x)

When using the appropriate starter/auto-configuration and **not replacing `RegisteredClientRepository` with a custom bean**, clients can be declared via Boot properties:

```yaml
spring:
  security:
    oauth2:
      authorizationserver:
        client:
          spa:
            registration:
              client-id: spa-ui
              client-authentication-methods:
                - none
              authorization-grant-types:
                - authorization_code
              redirect-uris:
                - https://spa.example.com/callback
              scopes:
                - openid
                - profile
            require-proof-key: true
            require-authorization-consent: true

          bff:
            registration:
              client-id: bff
              client-secret: "${PKCE_BFF_SECRET_HASH}"
              client-authentication-methods:
                - client_secret_basic
              authorization-grant-types:
                - authorization_code
                - refresh_token
              redirect-uris:
                - https://bff.example.com/login/oauth2/code/bff
              scopes:
                - openid
                - profile
            require-proof-key: true
            require-authorization-consent: true
```

`PKCE_BFF_SECRET_HASH` must hold a value **recognized by `PasswordEncoder`** (e.g., an encoded hash with the corresponding algorithm prefix) and be managed through secure configuration. This is not the plaintext secret used by the client. With the Java bean in the previous section, the encoder hashes the secret when registering, so **do not use both client registration sources simultaneously expecting Boot to merge them**.

**Note:** When you explicitly declare a `RegisteredClientRepository` bean, Boot may not create a repository from `spring.security.oauth2.authorizationserver.client.*`. Inspect the active beans in `ApplicationContext`; YAML only takes effect where auto-configuration still applies.

## 6. Spring Security OAuth2 Client Must Also Proactively Send PKCE

A common integration error is:

> The Authorization Server enabled `requireProofKey(true)`, but the OAuth2 Client does not send `code_challenge`, causing the authorization request to be rejected.

**Configuring the Authorization Server only makes the AS enforce PKCE.** The software acting as the **OAuth2 Client** must generate the verifier/challenge for each transaction and retain the verifier for the Token Endpoint.

### 6.1. Public Client Using Spring Security OAuth2 Client

With Spring Security OAuth2 Client on the Servlet stack, configure the client with `client-authentication-method: none`, no client secret, and grant `authorization_code`. Spring Security supports automatic PKCE for appropriately configured public clients. Example YAML **in the client application** (not on the Authorization Server):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          spa-proxy:
            provider: my-as
            client-id: spa-ui
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          my-as:
            issuer-uri: https://auth.example.com
```

**Do not confuse:** This YAML describes **a client consuming the Authorization Server**. The `spring.security.oauth2.client.registration.*` prefix is completely distinct from `spring.security.oauth2.authorizationserver.client.*` on the server. The client's redirect URI must **match the URI registered on the AS**; in this example, the AS registration would need to match the `/login/oauth2/code/spa-proxy` callback path if running the snippet directly.

For a JavaScript SPA running directly without a Spring Security Servlet client, you need a compatible OIDC/OAuth SDK to generate and bind verifier/challenge in the browser. You cannot rely on a bean on the Authorization Server to generate the verifier for the client.

### 6.2. Confidential Client Using Spring Security `oauth2Login`

If the RP is a Spring Boot backend/BFF, security configuration can explicitly enable PKCE on the **OAuth2 Client** via `OAuth2AuthorizationRequestCustomizers.withPkce()`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain relyingPartySecurityFilterChain(
        HttpSecurity http,
        ClientRegistrationRepository clientRegistrations) throws Exception {

    DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                    clientRegistrations, "/oauth2/authorization");
    resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .authorizationEndpoint(endpoint ->
                endpoint.authorizationRequestResolver(resolver)));

    return http.build();
}
```

Here:

- This code belongs in the **Relying Party application**, not the Authorization Server's filter chain configuration.
- The resolver generates `code_challenge` for the redirect and stores `code_verifier` in the authorization request's attributes for transaction-bound code exchange.
- Client authentication (such as `client_secret_basic`) still runs at the Token Endpoint; PKCE **does not disable** the client secret.
- The application still needs `ClientRegistrationRepository`, `spring.security.oauth2.client.registration.*`, user sessions, redirect URIs, and matching provider/issuer settings.

In newer Spring Security versions, `ClientRegistration.clientSettings.requireProofKey` may support enabling PKCE directly for confidential clients. Check the model/version you are using; the explicit resolver example clearly expresses **intent to enable PKCE on the client side** and must be integrated consistently with any existing custom login resolver.

### 6.3. When Does a BFF Make Sense?

For SPAs handling sensitive data, a BFF can:

1. Act as a confidential client at the Token Endpoint.
2. Keep the client secret and access/refresh tokens **server-side**.
3. Generate and store the PKCE verifier in **server-side transaction state**, bound to a secure session cookie.
4. Expose only an appropriate `HttpOnly; Secure; SameSite` session cookie to the browser and proxy internal APIs through the BFF.

This reduces exposing OAuth tokens/secrets to JavaScript. However, a BFF must still defend against **CSRF, XSS, session fixation**, protect cookies, and validate proxy/forwarded headers. PKCE alone does not solve those issues.

## 7. Which Attacks Does PKCE Mitigate—and Which Does It Not?

### 7.1. Interception: Attacker Captures the Authorization Code

A code leaked through a less-trusted environment, malicious extension, or misconfigured callback should not suffice to obtain tokens. If an attacker knows only the code and **not the transaction's verifier**, the Token Endpoint rejects it. This is the core scenario PKCE was designed to solve.

### 7.2. Code Injection and Login CSRF

An attacker may try to inject a code from another transaction into a user's callback. If the backend fails to bind the transaction, that code could be redeemed with the backend's valid credentials, causing session mix-up. PKCE creates a transaction-specific binding via the verifier; `state` (and OIDC `nonce` when applicable) must still be checked and tied to the browser session.

**RFC 9700:** public clients **MUST** use PKCE; confidential clients are **RECOMMENDED** to use PKCE, helping prevent code injection/misuse and providing strong CSRF protection when bound properly. Some confidential OIDC clients have nonce-based alternatives under additional conditions, yet **PKCE S256 is a sensible default for new architectures**.

### 7.3. Limits of PKCE

| Risk | Does PKCE Solve It Alone? | Complementary Control |
|---|---|---|
| Client secret leaked from frontend | **No** | Classify public clients accurately; never embed secrets in frontend; consider BFF |
| Attacker knows only authorization code | **Strongly helpful** if verifier is safe | Short-lived, single-use code, TLS, redirect validation |
| Attacker knows both code **and verifier** via XSS | **Not sufficient** | Prevent XSS, CSP, protect storage/transactions, BFF |
| Redirect URI has an open redirect | **No** | Exact redirect URI matching; eliminate dangerous redirectors |
| Access token stolen after issuance | **No** | Token TTL, audience/scopes, sender-constraining/rotation where applicable |
| Unbound CSRF/login transaction | **Not guaranteed** if PKCE is misused | Bind verifier to transaction/browser; validate `state`/`nonce` |
| Confidential client uses weak secret | **No** | Secret manager, rotation, `private_key_jwt`/mTLS where appropriate |
| Refresh token replayed | **No** | Refresh rotation/replay detection or sender constraints |
| Token issued to disallowed client/grant | **No** | Registration, client authentication, scopes, authorization policy |

### 7.4. Preventing PKCE Downgrades

An integration vulnerability occurs when a client/server accepts an **Authorization Code without a bound challenge**, yet at the Token Endpoint allows exchanging it as a non-PKCE flow (or "check verifier if present, skip if absent").

To prevent this:

- Set `requireProofKey(true)` on every `RegisteredClient` using Authorization Code per project policy.
- Reject authorization requests missing a policy-compliant challenge/method.
- When a code is bound to PKCE, **never issue tokens if the verifier is missing or wrong**; allow no "fallback" to code-only.
- If policy requires S256-only, enforce and test requests carrying `plain` or omitting `code_challenge_method`.
- Avoid having multiple code paths (legacy/new endpoints) enforcing different rules; apply consistently across public and confidential clients.
- Keep codes single-use and validate client/redirect URI before issuing tokens.

## 8. Common Errors at the Authorization Endpoint and Token Endpoint

| Symptom | Possible Cause | Fix |
|---|---|---|
| Authorization request rejected when challenge missing | Client registered `requireProofKey(true)` but did not send PKCE | Check OAuth2 Client resolver/SDK; generate S256 challenge per login |
| `invalid_request` for malformed `code_challenge` | Wrong challenge format or unsupported method | Generate with CSPRNG + SHA-256 + unpadded base64url |
| `invalid_grant` on code exchange | Wrong/missing verifier, expired/used code, client or redirect mismatch | Trace per-transaction correlation; never log verifiers/tokens |
| `invalid_client` at BFF Token Endpoint | Wrong client secret, method, or auth key | Check client authentication **independently** of PKCE |
| Public client sends `client_secret` and fails | Confused public with confidential | Use `none` and never send a secret from the browser |
| Challenge sent, but token request lacks verifier | Client failed to keep verifier across callback or lost session | Check `OAuth2AuthorizationRequestRepository` / transaction storage |
| Wrong verifier after opening multiple tabs | Shared global verifier or overwritten state | Separate verifier per authorization transaction, mapped by `state` |
| Login succeeds, callback fails | Client's redirect URI differs from URI registered on AS | Match exact scheme/host/port/path of the URI |
| Works in staging, fails in production | Cookie/`SameSite`, proxy, issuer, or session store differences | Check HTTPS, forwarded headers, and session storage |
| Code exchanges for tokens without PKCE | Server/registration does not enforce it, legacy policy | Enable `requireProofKey(true)`, update client, run downgrade tests |
| Uses secret yet still vulnerable to code injection | Client auth does not bind code to transaction | Enable PKCE on confidential client and AS; validate `state` |

**Exact errors may vary by version/branch under test.** For invalid `client_id` or `redirect_uri`, the Authorization Server must avoid redirecting error responses to an untrusted URI. Never rely solely on HTTP status or error code names to conclude PKCE is enforced properly.

## 9. Integration Testing Both Client Types

### 9.1. Essential Test Matrix

| ID | Client Type | Scenario | Expected Outcome |
|---|---|---|---|
| P01 | Public | Authorization Code + valid S256/verifier | Exchanges code for tokens within granted scopes |
| P02 | Public | Missing `code_challenge` | Authorization request rejected; no code issued |
| P03 | Public | Verifier does not match challenge | Token Endpoint rejects; no tokens issued |
| P04 | Public | Exchange code successfully, then reuse | Second attempt rejected |
| P05 | Public | Fixed challenge or reused verifier | Blocked by policy/tests or flagged as design violation |
| P06 | Public | Sends unregistered secret | Does not become confidential / does not bypass policy |
| C01 | Confidential | Valid secret **and** valid PKCE | Code exchange succeeds |
| C02 | Confidential | Valid secret, missing verifier | No tokens issued |
| C03 | Confidential | Valid secret, wrong verifier | No tokens issued |
| C04 | Confidential | Wrong secret, valid verifier | No tokens issued because client authentication fails |
| C05 | Confidential | Transaction A's code + B's verifier | No tokens issued |
| C06 | Confidential | Valid code, redirect URI differs from URI bound to code | Rejected per protocol |
| S01 | Both | `code_challenge_method=plain` when policy allows only S256 | Rejected |
| S02 | Both | Method omitted (defaults to `plain` per RFC 7636) | Rejected if policy is S256-only |
| S03 | Both | Unregistered redirect URI | Never redirects to untrusted URI |
| S04 | Both | Multiple tabs, callbacks arrive out of order | Verifier and `state` match each transaction |
| S05 | Both | Restart / scale 2 nodes between authorize and token | Authorization state and client verifier remain accessible per architecture |
| S06 | Both | Code leaked without verifier | Attacker cannot exchange for tokens |

**Test P05 cannot prove real entropy from a single request.** Unit-test the verifier generator for length, character set, and negligible collision rate across many samples, alongside code review confirming CSPRNG usage. Avoid overly tight statistical thresholds in tests that make CI flaky.

### 9.2. Protocol Testing Over HTTP

Tests for valid authorization requests must use **dynamically generated verifiers/challenges**, not placeholders:

```text
1. Client generates verifier V via CSPRNG.
2. Client computes C = BASE64URL(SHA256(ASCII(V))).
3. GET /oauth2/authorize
     ?response_type=code
     &client_id=spa-ui
     &redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback
     &state=<STATE_BOUND_TO_BROWSER>
     &code_challenge=<C>
     &code_challenge_method=S256
4. User authenticates/consents; browser receives redirect with code + state.
5. Client verifies state, POSTs /oauth2/token with code + V.
6. Verify tokens issued; reusing code or changing V must fail.
```

For a **confidential BFF**, add client authentication at the Token Endpoint, then test **two independent failure modes**: valid credentials / wrong verifier and wrong credentials / valid verifier. That provides concrete proof that **both PKCE and client authentication are enforced**.

### 9.3. Application-Level Assertions

Beyond HTTP status codes, verify:

- Public registered client has `ClientAuthenticationMethod.NONE` and `ClientSettings.isRequireProofKey() == true`.
- Confidential registered client has an appropriate auth method and `isRequireProofKey() == true`.
- Client callback completes only when `state` matches the transaction and the corresponding verifier is present.
- No raw `code_verifier`, `client_secret`, authorization code, or access/refresh tokens appear in application logs, traces, or app-constructed URLs.
- Authorization codes are redeemed only once, persisted in `OAuth2AuthorizationService`, and consistent across nodes.
- All redirect URIs match registration exactly with no fallback to another callback.

## 10. Operating and Rolling Out PKCE for Legacy Confidential Clients

A system with many OAuth clients may have legacy confidential clients using Authorization Code **without PKCE**. Immediately flipping `requireProofKey(true)` on the server before clients support it will break logins. Perform a controlled rollout:

1. **Inventory** clients using `authorization_code`, their auth method, SDK/version, callbacks, and environments; classify public vs. confidential.
2. **Prioritize public clients**: never allow missing PKCE; fix incompatible clients via SDK/architecture upgrades, **never** by lowering security.
3. **Upgrade confidential clients**: configure clients to generate S256 verifiers/challenges and store them per transaction; verify both `/oauth2/authorize` and `/oauth2/token` requests.
4. **Canary/staging testing**: catch wrong/missing verifiers, multi-tab flows, login redirects, reverse proxies, session stores, and restarts.
5. **Enable server enforcement** of `requireProofKey(true)` on the target registrations while keeping existing client authentication intact.
6. **Monitor and triage errors**: track categorized authorization failures / `invalid_grant` / `invalid_request` rates without logging raw credentials.
7. **Tighten S256-only policy** if required; ensure no legacy code path skips PKCE or falls back to `plain`.

When client data is stored in JDBC, update `RegisteredClient.clientSettings` via your migration/management mechanism; do not assume editing YAML updates existing JDBC records. Keep `RegisteredClient.id` stable so existing authorization and consent links remain intact.

### 10.1. Multiple Instances and Sessions

Storing challenges typically lives with the authorization in `OAuth2AuthorizationService` on the Authorization Server, while the verifier is held **on the OAuth2 Client side** in the transaction/login session. Both sides require suitable storage across node hops and restarts:

```mermaid
flowchart LR
    BR["Browser"] --> RP1["RP/BFF node 1"]
    BR --> RP2["RP/BFF node 2"]
    RP1 --> RS[("RP transaction/session store<br/>state → verifier")]
    RP2 --> RS
    RP1 --> AS1["Authorization Server node 1"]
    RP2 --> AS2["Authorization Server node 2"]
    AS1 --> AUTH[("Authorization store<br/>code → challenge/method")]
    AS2 --> AUTH
```

If the verifier is overwritten in the RP session or `OAuth2AuthorizationService` is not shared across AS nodes, valid codes can fail with `invalid_grant`. That is a **state/persistence** issue and must not be "fixed" by disabling PKCE.

### 10.2. Production Security Checklist

- [ ] Classify clients accurately as public/confidential based on **ability to hold credentials**, not UI style.
- [ ] All public Authorization Code clients enforce PKCE and never embed shared secrets in frontend code.
- [ ] Confidential Authorization Code clients enable PKCE alongside client authentication.
- [ ] Every transaction uses a CSPRNG verifier, 43–128 characters, high entropy, generated **fresh each time**.
- [ ] Challenge uses **S256**, SHA-256 of ASCII verifier, **unpadded** base64url.
- [ ] Verifier is sent only at the Token Endpoint; never included in the Authorization Endpoint or callback URLs.
- [ ] `requireProofKey(true)` is declared and verified on real registrations.
- [ ] Tested missing challenge, wrong verifier, code replay, and PKCE downgrade scenarios.
- [ ] Client binds `state`/verifier to the browser session; OIDC `nonce` when applicable.
- [ ] Exact redirect URI matching, TLS, issuer, and endpoint URLs are consistent.
- [ ] BFF keeps secrets and OAuth tokens server-side; cookies/sessions are protected against CSRF/XSS.
- [ ] Verified Spring version behavior, persistence, and multi-node operation rather than relying on unverified defaults.

## 11. Self-Check Questions

1. **If a confidential client already uses `client_secret_basic`, does PKCE still add value?** Yes: PKCE binds the code to the transaction; the secret only authenticates the client during code exchange.
2. **Does PKCE make an SPA confidential?** No: an SPA still cannot reliably hold a shared secret.
3. **What if a client sends `code_challenge_method=S256` but exchanges the code with a different verifier?** The Token Endpoint must reject it.
4. **Once a code has been exchanged for tokens, can the right verifier exchange it again?** No; an authorization code is single-use.
5. **Does `requireProofKey(true)` equate to client authentication?** No; confidential clients still need credentials per their registered method.
6. **Why does a Spring Security confidential client need PKCE configured in two places?** The server must **enforce**, while the RP/OAuth2 Client must **generate and send** the verifier/challenge.
7. **How can you detect code injection across multiple tabs?** Verify per-transaction `state`/verifier binding and test swapping codes between two flows.
8. **If you see `invalid_grant`, should you disable PKCE as a quick fix?** No; inspect the verifier, code expiry, single-use state, redirect, client, and state storage.

## 12. References

- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): verifier format, `S256` transformation, flow, and code interception defense.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice, $2.1.1](https://www.rfc-editor.org/rfc/rfc9700): **public clients MUST use PKCE**, **confidential clients are recommended to use PKCE**, preventing code injection and CSRF.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): PKCE in mobile/desktop/native apps and redirect protection.
- [Spring Authorization Server 1.5.x — SPA with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): registering public clients with `none` and `requireProofKey(true)`, and refresh token restrictions for public clients in this implementation.
- [Spring Authorization Server 1.5.x — ClientSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.html): `isRequireProofKey()` and version defaults.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings`, and authorization state.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): PKCE in client apps and `DefaultOAuth2AuthorizationRequestResolver`.
- [Spring Security — OAuth2 Client Authentication](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/client-authentication.html): public client `none` and client authentication methods.
- [Spring Security — OAuth2AuthorizationRequestCustomizers API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html): `withPkce()` and storing verifier in attributes.

**Conclusion:** For the **Authorization Code grant**, PKCE S256 **binds each authorization code to a specific initiated transaction**. Public clients must use PKCE; confidential clients should use **both PKCE and client authentication**. In Spring Authorization Server, declare `ClientSettings.requireProofKey(true)` on the registration; in the OAuth2 Client, generate, store, and send the verifier/challenge per transaction. They are two complementary halves, not interchangeable alternatives.
