# 8.7. Applying PKCE for Public Clients and Confidential Clients

## 1. Where Does PKCE Fit in the Authorization Code Flow?

In **Spring Security OAuth 2.0/OIDC Client**, the Authorization Code Grant lets an application send a user to the Authorization Server (AS) or OpenID Provider (OP) for authentication and authorization. On success, the AS redirects the browser back to the application with an **authorization code**. The client uses that code to call the **token endpoint** and exchange it for an access token and, with OpenID Connect, typically an ID Token as well.

The security problem: **an authorization code can be intercepted, stolen, or delivered to the wrong recipient** while traveling through browser redirects. If having the code alone were enough to exchange for tokens, another party obtaining the code could attempt to redeem it at the token endpoint, especially when the client has no way to safely keep a long-lived secret.

**PKCE — Proof Key for Code Exchange**, pronounced roughly like "pixy", is a mechanism standardized in RFC 7636 to bind **the initial authorization request** to **the token request exchanging the code**. PKCE allows the Authorization Server to verify that the party redeeming the code holds a random value created earlier by the party that initiated the request.

PKCE was originally designed for **public clients**, yet modern OAuth 2.0 best practices also recommend applying it to **confidential clients**. PKCE does not require changing the grant type: `response_type=code` is still used at the authorization endpoint and `grant_type=authorization_code` at the token endpoint.

Roles in this lesson:

- **Public client:** an application that cannot reliably keep a long-lived client secret, such as a native app or a Single Page Application (SPA) running in the browser.
- **Confidential client:** a backend application capable of protecting client credentials, such as a Spring Boot web server acting as an OAuth2/OIDC Client.
- **Authorization Server:** provides the authorization endpoint and token endpoint; must understand, store, and verify PKCE data.
- **Resource Server:** the API consuming the access token after authorization; not the party checking PKCE during code exchange.

The goal is to understand PKCE properly, distinguish its role from client authentication, `state`, and OIDC `nonce`, and apply it in Spring Security configuration.

## 2. Why Is a Client Secret Alone Not Enough?

Distinguish two separate questions:

1. **Who is the client calling the token endpoint?** A confidential client can prove its identity via `client_secret_basic`, `private_key_jwt`, or a corresponding client authentication method.
2. **Is that client the exact party that initiated the authorization request that produced this code?** PKCE creates a link between the authorize request and the code-exchange request.

For a public client, **a client secret cannot be treated as secret** if embedded in JavaScript or an application distributed to user devices. The same shared secret can be extracted, so it cannot serve as the primary protection for authorization codes. PKCE solves this with a short-lived secret generated **freshly for each authorization transaction**.

For a confidential client, the client secret proves application identity but does not by itself protect against every **authorization code interception or code injection** scenario. If an attacker obtains a code, or injects a code generated in another context into the client's flow, adding PKCE forces the code to match the verifier from the exact originating transaction. Therefore **client authentication and PKCE should be combined**, rather than choosing one over the other.

| Question | Client Authentication | PKCE |
|---|---|---|
| Is the party calling the token endpoint authenticated as a registered client? | **Yes**, if the client has an appropriate authentication method. | Not directly. |
| Does the party exchanging the code hold the verifier from the authorization request that produced the code? | Not directly. | **Yes**, when verified properly by the AS. |
| Long-lived secret or per-transaction? | Usually a long-lived secret/key or longer lifecycle. | Random verifier **per authorization request**. |
| Used for public clients? | No confidential-style trustworthy secret. | **Yes**, essential mechanism. |
| Used for confidential clients? | Yes, per registered method. | **Yes**, strengthens code exchange protection. |
| Replaces CSRF protection and OIDC token validation? | No. | Should not be treated as a catch-all solution for every requirement. |

## 3. Two Core Values: `code_verifier` and `code_challenge`

PKCE uses two closely related values:

- **`code_verifier`:** a high-entropy random string generated when the client initiates an authorization request. The client retains this value to send later at the **token endpoint**.
- **`code_challenge`:** a value derived from the verifier, sent to the **authorization endpoint** along with the authorization request. The server associates the challenge with the issued authorization code.

When exchanging the code, the client sends back the original `code_verifier`. The server derives the challenge from the verifier and compares it with the challenge stored alongside the code. If they do not match, the code exchange must be rejected.

### 3.1. Rules for `code_verifier`

RFC 7636 defines `code_verifier` as a character string:

- Length **43–128 characters**.
- Uses unreserved characters: letters A–Z/a–z, digits 0–9, and `-`, `.`, `_`, `~`.
- Generated by a cryptographically secure random number generator with high entropy. A common recommendation is **32 random bytes** Base64URL-encoded without padding, yielding a 43-character string.

The verifier is a **short-lived transaction secret**, not a user password or client secret. Each authorization request initiation must generate a new verifier; never reuse a fixed verifier across all users, windows, or logins.

### 3.2. How to Generate an `S256` `code_challenge`

The recommended PKCE method is **`S256`**:

~~~text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)

code_challenge_method = S256
~~~

Notes:

- Hash the **ASCII string** of `code_verifier` with SHA-256.
- Encode the hash digest with Base64URL, **without `=` padding**.
- Use the Base64URL alphabet, **not** standard Base64 with `+` and `/`.
- **Never send `code_verifier` in the authorization request**; it is sent in the token request.
- `code_challenge` may appear on the front-channel URL; it **does not need to be kept secret** like the verifier.

An example pair published in RFC 7636:

~~~text
code_verifier:
  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
  E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

The pair above is only for illustration or verifying the algorithm. **Never copy this example pair as a hardcoded verifier in a real application.**

### 3.3. The `plain` Method and Why `S256` Is Preferred

RFC 7636 also describes the `plain` method, where `code_challenge` equals `code_verifier` directly. However, if both the challenge and verifier could be observed on the front channel, protection is significantly weakened.

**Prefer `S256`** whenever supported by client and AS; a modern implementation should never downgrade from `S256` to `plain` just to work around a configuration issue. If an AS does not support S256, review the AS's security policy and contract rather than silently dropping PKCE.

## 4. End-to-End Authorization Request and Token Request with PKCE

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User / Browser
    participant C as OAuth2/OIDC Client
    participant AS as Authorization Server
    participant API as Resource Server

    Note over C: Generate verifier V; challenge C = BASE64URL(SHA256(V))
    U->>C: Initiate login
    C-->>U: Redirect to authorization endpoint with C, method=S256, state
    U->>AS: Authorization request
    Note over AS: Store C, S256 and bind to code
    AS->>U: Login / consent
    AS-->>U: Redirect back to client with code=K and state
    U->>C: Callback with K, state
    Note over C: Match state, retrieve exact verifier V of initial request
    C->>AS: POST token endpoint: K, V; client auth if confidential
    Note over AS: SHA256(V) == challenge bound to K?
    alt Valid and conditions met
        AS-->>C: Access token; ID Token if OIDC
        C->>API: Authorization: Bearer access_token
        API-->>C: Authorized resource
    else Verifier mismatch / invalid code
        AS-->>C: OAuth2 error, e.g. invalid_grant
    end
~~~

This diagram applies to both public clients and confidential clients. The main differences lie in **who executes the token request** and **whether the client can authenticate with a long-lived secret credential**.

### Step 1 — Generate Verifier and Challenge Before Redirecting

The client generates a fresh verifier `V1` for transaction `G1` and computes challenge `C1`. The client must retain that exact transaction's verifier until the callback returns.

For example, in a server-side Spring Security application, the verifier can be stored in the attributes of `OAuth2AuthorizationRequest`, alongside session/authorization request data. In an SPA, the OAuth2 client library must manage the verifier in the browser environment using an appropriate security model. Never put the verifier into a redirect URL or send it to the IdP during authorize.

### Step 2 — Authorization Request Sends the Challenge

OIDC request example, wrapped across lines for readability:

~~~http
GET /authorize?response_type=code
  &client_id=spring-web-client
  &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo
  &scope=openid%20profile
  &state=STATE_RANDOM_1
  &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  &code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

When actually sent over HTTP, the query string is **a single valid URL** with no formatting line breaks.

The PKCE parameters are solely:

~~~text
code_challenge=<Base64URL-encoded SHA-256 value>
code_challenge_method=S256
~~~

The remaining parameters are still required for the Authorization Code Flow: `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`, and possibly `nonce` in OIDC.

The Authorization Server validates the request and **binds `code_challenge` and method to the authorization code** if a code is issued. This ensures the verifier is verified against the exact transaction, never compared against the challenge of another request.

### Step 3 — Callback Returns the Authorization Code

After the user completes authentication/consent:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=CODE_ABC&state=STATE_RANDOM_1
~~~

The client receives the callback, looks up the initiated authorization request, and checks `state`. At this point, the client must retrieve **that exact request's verifier**, never generating a new verifier.

If the browser loses the cookie/session linking the request, the callback may fail to find the verifier. Then the token request will lack a verifier or send the wrong one, causing a PKCE failure; the proper handling is to safely restart the flow.

### Step 4 — Token Request Sends the Original Verifier

Example confidential client using `client_secret_basic`:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&code=CODE_ABC&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

At this step:

- `grant_type=authorization_code` selects the code-exchange grant.
- `code` is the authorization code received at callback.
- `redirect_uri` is sent again per protocol requirements and must be consistent with the authorization request.
- `code_verifier` is the value generated for this transaction.
- `Authorization: Basic ...` illustrates **client authentication specific to a confidential client**.

For a public client without a client secret, the request might look like:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=public-browser-client&code=CODE_XYZ&redirect_uri=REGISTERED_REDIRECT_URI&code_verifier=VERIFIER_FOR_THIS_FLOW
~~~

Details may vary depending on client type and registration with the AS. A public client never embeds an extractable `client_secret` in JavaScript. PKCE does not turn a public client into a confidential client.

### Step 5 — AS Verifies Challenge, Code, and Client

When receiving the token request, the AS must verify all of the following together:

1. The authorization code exists, has not expired, and has not been used.
2. The code was issued to the matching client, and `redirect_uri` satisfies the constraint used during authorize.
3. For a code issued with PKCE, `code_verifier` is present, syntactically valid, and its derived hash matches the stored `code_challenge`.
4. If the client is confidential, client authentication succeeds per the registered method.
5. All other AS conditions (client, grant, token issuance policies) are met.

If the verifier is wrong, the AS rejects the request, usually with the OAuth2 error `invalid_grant`. The AS **must never treat successful secret-based client authentication as a reason to skip PKCE verification** when the code was bound to a challenge.

### Step 6 — Tokens Are Issued for Their Proper Purpose

After verification succeeds, the AS may return:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile",
  "id_token": "SIGNED_ID_TOKEN_VALUE"
}
~~~

`id_token` appears in the appropriate OIDC context; `refresh_token` may or may not be issued depending on policy. PKCE only protects **the authorization code exchange**; it does not determine granted scopes or access token lifetime.

The client proceeds to validate the ID Token per OIDC rules when using OIDC Login, and uses the **access token** to call APIs with corresponding permissions.

## 5. Public Clients: When a Client Secret Cannot Be Kept

### 5.1. What Is a Public Client?

An OAuth2 **public client** is an application that cannot protect a long-lived client authentication secret. Typical examples:

- Browser-based JavaScript applications (SPAs).
- Native/mobile applications distributed to user devices.
- Interactive desktop or CLI applications, if credentials embedded in the binary can be extracted.

A secret hardcoded in JavaScript code or a mobile app bundle **does not provide trustworthy client authentication**, because any user can inspect and copy the value.

A public client still has a `client_id`, authorization grant, redirect URI, and registered scopes. It is simply that **`client_id` is not a secret**.

### 5.2. Why Is PKCE Especially Critical for Public Clients?

If a public client simply sent an authorization code at the token endpoint with neither client authentication nor PKCE, an attacker who intercepted the code could try to exchange it by sending the same client ID and redirect URI.

With PKCE:

~~~text
Initiator:
    code_verifier = V1
    code_challenge = SHA256(V1)

Authorization Server issues code K1 and binds it to V1's challenge.

Attacker intercepting K1:
    Has K1.
    Does not know V1.

Attacker sends:
    code=K1
    code_verifier=V2

Authorization Server checks:
    SHA256(V2) != SHA256(V1)
    => Rejects code exchange.
~~~

This is the core point: **a code is not enough to obtain tokens without the matching verifier**.

### 5.3. How Should an SPA Handle This?

An SPA running directly in the browser should use a suitable OAuth2/OIDC client library implementing **Authorization Code Flow with PKCE**. The library must manage the verifier, state, callback, token lifetimes, and token-leakage mitigations according to the application architecture.

Never copy `client_secret` from backend configuration into the frontend. Never try to replace PKCE with "an arbitrary JavaScript-generated token" that the AS does not know how to verify.

PKCE does not eliminate risk if malicious JavaScript runs on the same origin: if an SPA suffers XSS or a compromised script, it can read whatever verifier/tokens the frontend can access. So you still need CSP, dependency hygiene, XSS defenses, proper token storage policies, and callback protection.

An alternative architecture is **Backend For Frontend (BFF)**: a Spring Boot backend holds tokens and client credentials while the browser interacts with the app over a session cookie. In the BFF model, the backend acts as a confidential client and **should still use PKCE**.

### 5.4. How Should Native/Mobile Clients Handle This?

Native clients typically open the system browser for the user to sign in, receive the callback via a registered redirect URI, and exchange the code using the verifier retained in the app.

Redirect URIs may use loopback, claimed HTTPS, or custom URI schemes depending on platform and AS rules. PKCE alone **is not enough** to secure redirect URIs: the app must also follow native app callback protection guidance, manage `state`, avoid insecure embedded webviews, and protect tokens on the device.

### 5.5. Can a Spring Boot Server Be Registered as a Public Client?

Yes. A server-side Spring Boot application can still use a registration without a secret if the AS registers that client as public. However, **client type is determined by credential-holding capability and registration model**, not merely because the program is written in Java or runs on a server.

For a backend web application you control that can protect secrets or keys, the confidential client model is usually more appropriate. Whichever type you choose, PKCE is still used to protect the authorization code.

## 6. Confidential Clients: Client Authentication + PKCE

### 6.1. What Is a Confidential Client?

A confidential client has a more trustworthy environment for holding client authentication secrets, typically a backend server:

~~~text
User browser
    |
    | Redirect / callback containing authorization code
    v
Spring Boot backend
    |
    | POST /token with client authentication + code_verifier
    v
Authorization Server
~~~

Normally the backend keeps the client secret in a secret manager or environment variable; the browser never sees it. The client may use `client_secret_basic`, `client_secret_post`, `private_key_jwt`, or another method permitted by the AS.

### 6.2. What Does PKCE Add?

In a confidential client, client authentication already reduces the chance of another application exchanging a code on the client's behalf. Even so, PKCE remains valuable because it:

- Protects the binding of a code to the exact authorization request that initiated it.
- Mitigates certain front-channel authorization code interception/injection scenarios.
- Aligns the security model across client types.
- Complies with Authorization Servers that require PKCE for every Authorization Code Grant.
- Provides per-transaction proof that a long-lived client credential cannot express.

A confidential client should send both client authentication and `code_verifier` in the token request when the flow uses PKCE. Do not omit the verifier simply because a client secret is present.

### 6.3. PKCE Does Not Protect a Compromised Client Secret

If a client secret or private key leaks, rotate or revoke the credential per AS policy. PKCE does not make a stolen long-lived credential harmless; it only protects individual code exchanges bound to a verifier.

Conversely, rotating the client secret does not replace generating a separate random verifier for every transaction.

## 7. Comparing Implementation Between Public and Confidential Clients

| Criterion | Public Client | Confidential Client |
|---|---|---|
| Common examples | SPA, native/mobile, desktop | Spring Boot backend, BFF |
| Client ID | Yes; not a secret | Yes; not a secret |
| Long-lived client secret/signing key | Cannot store secrets reliably | Can store in backend/secret manager |
| Client authentication at token endpoint | Usually registered as `none` | Performed per registered method |
| PKCE | **Must be used** in modern Authorization Code Flow | **Should be used** and may be required by AS |
| `code_verifier` | Kept per transaction in client environment | Kept per transaction in backend/session |
| `code_challenge` | Sent in authorization request | Sent in authorization request |
| When `code_verifier` is sent | Token request | Token request |
| Distinct risks | XSS, local malware, redirect interception, token storage | Secret leakage, session handling, proxy/callback misconfiguration |
| Can state, HTTPS, or OIDC validation be skipped? | No | No |

**Remember:** the biggest difference is the ability to authenticate the *client*, whereas **PKCE S256 works by the exact same principle for both client types**.

## 8. Applying PKCE in Spring Security OAuth2 Client

Spring Security supports PKCE when constructing the authorization request and sending the corresponding `code_verifier` in the token request. In a Spring Boot application, the core dependencies typically include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Examples use Spring Boot 3.x with a **Servlet/MVC** application. On Spring Boot 4.x, recommended starter names include `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`. Keep your BOM/plugins and configuration style consistent with your Spring Boot line.

A WebFlux application uses corresponding reactive classes such as `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ReactiveClientRegistrationRepository`. Do not mix `HttpSecurity` with reactive classes in the same Servlet code sample without migrating the entire configuration.

### 8.1. Configuring Two `ClientRegistration` Entries for One OIDC Provider

To illustrate the difference between the two client types, suppose the AS defines **two separate client registrations**:

1. `public-demo` — public client, with no client secret.
2. `server-demo` — confidential web client, issued a client ID and secret.

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          public-demo:
            provider: example-idp
            client-id: ${PUBLIC_CLIENT_ID}
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
          server-demo:
            provider: example-idp
            client-id: ${SERVER_CLIENT_ID}
            client-secret: ${SERVER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          example-idp:
            issuer-uri: https://id.example.com
~~~

Prerequisites to run this example:

- `https://id.example.com` is a valid OIDC issuer with discovery metadata supporting Authorization Code Flow with PKCE S256.
- Each `client-id` is registered with the matching client type at the AS.
- The AS allows the corresponding callbacks, such as `https://app.example.com/login/oauth2/code/public-demo` and `https://app.example.com/login/oauth2/code/server-demo`.
- `SERVER_CLIENT_SECRET` resides only on the backend and is protected.
- `PUBLIC_CLIENT_ID` and `SERVER_CLIENT_ID` are two real values from the AS, not Spring-invented registration IDs.

This example shows **two registrations in one Spring Boot backend** to observe configuration; it does not replace running a JavaScript SPA with a frontend PKCE library.

### 8.2. Public Client: Spring Security Supports Automatic PKCE

In Spring Security OAuth2 Client, when a `ClientRegistration` uses `authorization_code` and `client-authentication-method: none`, the authorization request resolver's default behavior can **automatically apply PKCE** for the public client. The initiation request to the AS then carries `code_challenge` and `code_challenge_method=S256`, while the token request sends the matching `code_verifier`.

With Servlet OAuth2 Login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Users initiate the authorization request via:

~~~text
/oauth2/authorization/public-demo
~~~

Spring Security uses `ClientRegistration` to construct the request, manage per-session/per-transaction data, and handle the default callback:

~~~text
/login/oauth2/code/public-demo
~~~

**Do not invent a custom controller to receive the code** when already using default `oauth2Login()`. Callback handling, `state`, PKCE, and token exchange are coordinated by Spring Security's components.

Because automatic support and behavior can vary by version or custom resolver, verify the outgoing authorization request against your configuration in real deployments. More importantly, the AS must **enforce PKCE** for this client; a client sending a challenge while the AS ignores the verifier does not provide the intended protection.

### 8.3. Confidential Client: Explicitly Enabling PKCE with a Customizer

For a confidential client, having a client secret **does not mean every Spring Security version or default configuration turns on PKCE automatically**. You can explicitly attach `OAuth2AuthorizationRequestCustomizers.withPkce()` to the resolver.

Complete example for the **Servlet stack**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PkceSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations,
                "/oauth2/authorization"
            );

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce()
        );

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)
                )
            );

        return http.build();
    }
}
~~~

This configuration **replaces** the `SecurityFilterChain` in the previous example—do not put both similar beans into the application just to test two approaches.

Key points:

- `DefaultOAuth2AuthorizationRequestResolver` looks up `ClientRegistration` by `registrationId` from the URL.
- `withPkce()` adds PKCE data to the authorization request where applicable; Spring Security retains the verifier in request metadata for reuse during code exchange.
- Base URI `/oauth2/authorization` matches the default initiation endpoint in the example.
- `oauth2Login(...authorizationRequestResolver(resolver))` configures Spring Security to use the PKCE-customized resolver.
- When a user visits `/oauth2/authorization/server-demo`, the authorization request for the confidential client includes `code_challenge` and `code_challenge_method=S256`.
- When the callback arrives at `/login/oauth2/code/server-demo`, the token exchange needs both client authentication and the original verifier.

If a project already has a customizer or resolver for parameters such as `prompt`, `login_hint`, or `audience`, **combine** that logic with PKCE in the same resolver. Avoid replacing the resolver with a new configuration that drops required fields or introduces inconsistent handling.

### 8.4. Must Every Confidential Client Be Enabled This Way?

Do not treat a single Java snippet as the sole answer across all Spring Security versions. Defaults, built-in PKCE behavior, and customization APIs can vary across releases and client types. In any concrete project, what you must verify is:

1. The authorization request contains `code_challenge` and `code_challenge_method=S256`.
2. The AS accepts and stores the challenge with the code.
3. The token request includes the matching `code_verifier`.
4. For confidential clients, client authentication is still performed.
5. When a token request lacks a verifier or sends an invalid verifier, the AS rejects it.

The official Spring Security documentation for your version and your AS configuration determine the right API. Avoid skipping PKCE protection just because "we already have a secret."

### 8.5. Beans That Store the Authorization Request

Spring Security must keep state across two HTTP requests:

~~~text
Request 1: /oauth2/authorization/server-demo
       -> generates state, verifier, challenge
       -> saves authorization request
       -> redirects to AS

Request 2: /login/oauth2/code/server-demo?code=...&state=...
       -> retrieves original authorization request
       -> verifies state
       -> retrieves saved verifier
       -> exchanges code for tokens
~~~

In Servlet, the component saving the initiation request is usually `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`; an HTTP session-based implementation is a common choice. A custom repository backed by cookies, a database, or distributed sessions must **preserve all required PKCE data**, especially the verifier placed in request attributes by the framework.

If custom code serializes only URL parameters and drops `code_verifier` or correlation data, token exchange can fail with `invalid_grant` even though the initial authorization request had a valid challenge.

**Never log the verifier or an entire authorization request containing secrets**. Never send the verifier via browser redirect to the AS when initiating authorization.

## 9. Generating Verifier and Challenge in Java to Understand the Algorithm

In normal Spring Security applications, let the framework manage PKCE automatically. To understand S256 clearly, you can inspect how Java generates both values with `SecureRandom`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceValues {

    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceValues() {
    }

    public static String newCodeVerifier() {
        byte[] randomBytes = new byte[32];
        RANDOM.nextBytes(randomBytes);

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(randomBytes);
    }

    public static String s256Challenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "SHA-256 is required for PKCE S256", exception);
        }
    }
}
~~~

Algorithmic usage:

~~~java
String verifier = PkceValues.newCodeVerifier();
String challenge = PkceValues.s256Challenge(verifier);

// Authorization request: send challenge and method S256.
// Token request: send this exact verifier.
~~~

Key details to observe:

- `SecureRandom` produces 32 high-entropy random bytes.
- Unpadded Base64URL creates a verifier with valid characters.
- `SHA-256` turns the verifier into a 32-byte digest.
- The challenge uses unpadded Base64URL.
- **Verifier and challenge are generated once per transaction**, then the verifier must be stored in the right place for the callback.

This Java snippet is only for illustrating the formula; **do not combine it with `withPkce()` and generate a second verifier**. Once using Spring Security's PKCE customizer, let the framework manage a single consistent data source.

## 10. PKCE, `state`, and `nonce`: Three Mechanisms Not to Confuse

In an OIDC Authorization Code Flow, all three may appear together:

~~~http
GET /authorize?response_type=code
  &client_id=spring-web-client
  &scope=openid%20profile
  &state=RANDOM_STATE
  &nonce=RANDOM_NONCE
  &code_challenge=S256_CHALLENGE
  &code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

| Value | Where Initially Sent | Where Verified Later | Purpose |
|---|---|---|---|
| `state` | Authorization request | Authorization response/callback | Binds response to initiated request; mitigates CSRF/transaction mix-ups. |
| `code_challenge` + `code_verifier` (PKCE) | Challenge at authorize, verifier at token endpoint | Token request | Binds authorization code to the holder of the initial request's verifier. |
| `nonce` in OIDC | Authorization request | `nonce` claim of ID Token when used | Binds ID Token to the corresponding OIDC authentication attempt, mitigating replay. |

### 10.1. Does PKCE Completely Replace `state`?

Modern OAuth2 guidance treats PKCE as a critical mechanism that can also help mitigate certain CSRF vectors when Authorization Server and client protections are met. However, in a Spring Security application with sessions/callbacks and potentially multiple providers, **continuing to use `state` per the default workflow remains appropriate** for correlating authorization responses.

Do not arbitrarily drop `state` after enabling PKCE. Nor does PKCE replace distinguishing the right issuer, client registration, redirect URI, or solving all login mix-up risks.

### 10.2. Does PKCE Validate the ID Token?

No. PKCE protects the authorization code exchange; the OIDC ID Token must still be validated for:

- signature or corresponding token protection method;
- `iss` matching the trusted OpenID Provider;
- `aud` containing the application's client ID;
- `exp` and time conditions;
- `nonce` if requested;
- other OIDC constraints as applicable.

An attacker may be prevented from exchanging a code thanks to PKCE, yet the client must not skip ID Token verification on that account.

### 10.3. Is PKCE Code Encryption?

No. The authorization code still normally appears in the callback URL; `code_challenge` appears in the authorization request. PKCE **binds** code exchange to a verifier—it does not "encrypt" the code or remove the code from the front channel.

Therefore you still need HTTPS, exact callback URIs, short-lived/single-use codes, logging hygiene, and measures to prevent URL leakage.

## 11. Additional Protection Layers for Public and Confidential Clients

PKCE is only one layer in the Authorization Code Grant security model.

### 11.1. Redirect URIs Must Be Controlled

The provider must enforce an allowlist and safe redirect URI matching rules for the client. If a callback can be redirected to a URL outside the application, the code can leak before the client ever gets to exchange it.

PKCE reduces the impact of code interception, yet **never validates an overly permissive redirect URI**.

### 11.2. HTTPS and Client Authentication Still Matter

Use TLS for authorization/token endpoints and appropriate production redirect URIs. Public clients lack trustworthy secrets; confidential clients must keep secrets/private keys on the backend. HTTP Basic with a client secret is merely a credential transport format—**Base64 is not security encryption**.

### 11.3. Authorization Codes Must Be Short-Lived and Single-Use

The AS must bind the code to the client, callback, and challenge, and reject expired, reused, or invalid codes. A single code must never be exchangeable for tokens repeatedly, even if the verifier matches.

### 11.4. Keep the Verifier Out of Unnecessary Places

Never put `code_verifier` in:

- the authorize URL;
- callback query parameters;
- URLs sent to third-party sites;
- logs, monitoring events, or public exception messages;
- public JavaScript in a backend confidential client architecture.

The verifier remains on the client side that initiated the transaction and is sent only in the token request to the intended AS.

### 11.5. Reject PKCE Downgrades

An AS supporting PKCE must enforce that the verifier matches the challenge attached to the code. If a client is registered as public and the AS requires PKCE, an authorization request missing a challenge must be handled under mandatory enforcement rather than silently issuing an unbound code.

If an attacker can strip the challenge during authorize and the AS still accepts a code without PKCE, code-interception protection can be downgraded. Thus **both client and AS share responsibility for upholding PKCE enforcement**.

### 11.6. Tokens and Application Sessions Still Need Protection

After code exchange, access tokens and refresh tokens (if any) must be protected according to the architecture. In a Spring Boot backend, tokens belong in the appropriate authorized client store rather than being pushed unnecessarily to the browser. Session cookies should be securely configured.

PKCE does not prevent someone who already stole an access token from using that token everywhere. When sender-constrained tokens are required, systems can adopt dedicated mechanisms such as DPoP or mTLS if supported by the AS/API; those address a different threat and are not replaced by PKCE.

## 12. Inspecting the Authorization Request in Spring Security to Understand PKCE

From the browser, initiate login:

~~~text
http://localhost:8080/oauth2/authorization/public-demo
http://localhost:8080/oauth2/authorization/server-demo
~~~

Assume the provider permits localhost callbacks in development. Using browser network tools, you will typically observe a redirect sequence:

~~~text
GET /oauth2/authorization/server-demo
    302 Location: https://id.example.com/authorize?...

GET https://id.example.com/authorize
    response_type=code
    client_id=...
    state=...
    code_challenge=...
    code_challenge_method=S256

GET /login/oauth2/code/server-demo?code=...&state=...
    Spring Security handles the callback
~~~

Values to verify in the authorization request:

- `response_type=code`: using the Authorization Code Flow.
- `code_challenge_method=S256`: client uses PKCE with SHA-256.
- `code_challenge`: challenge should differ across requests with distinct verifiers.
- `state`: used by Spring Security to correlate the callback.
- `redirect_uri`: matches the callback permitted by the AS.
- `client_id`: matches the provider-side registration.

**You cannot rely solely on browser DevTools to conclude the token request sent the right verifier in a server-side model.** The `POST /token` request is made directly by the Spring Boot backend to the AS. Confirm via controlled logging, secret-masked trace data, or inspecting valid requests in a test environment—avoid printing `code_verifier` or access tokens to console or production logs.

### 12.1. Do Not Manually Exchange a Code to "Test PKCE" in Production

If you copy a code from a callback and replay it against the token endpoint, Spring Security may already have redeemed and invalidated it once. The second request will fail with `invalid_grant`, which is not necessarily a PKCE error.

To verify PKCE behavior, start a fresh transaction in a test environment using approved tooling per system policy. Do not record live codes, tokens, or secrets in reports or documentation.

## 13. Security Scenario Analysis

### Scenario A — Public Client with PKCE, Attacker Only Captures the Code

Suppose the client creates verifier `V1` and challenge `C1`, and the AS issues code `K1`. An attacker intercepts `K1` but does not have `V1`.

If the AS enforces PKCE properly, a code-exchange request with a guessed verifier `V2` is rejected. This is the primary scenario PKCE is designed to mitigate.

### Scenario B — Confidential Client with Secret but Without PKCE

The client uses valid client authentication when exchanging the code, yet the authorization code is not bound to a per-authorize-request verifier.

The client secret helps protect the token endpoint from unauthenticated callers, but does not provide the same **per-authorization-request** proof as PKCE. In modern architectures, add PKCE for confidential clients as well.

### Scenario C — Confidential Client with Both Secret and PKCE

An attacker obtains an authorization code without knowing the verifier. Even if some misconfiguration allowed a request from a valid client, the AS still requires a verifier matching the code's challenge before issuing tokens.

This provides an independent verification layer alongside client authentication.

### Scenario D — Verifier Stored Under the Wrong Transaction

A user opens two login attempts close together:

~~~text
Transaction G1: verifier V1 -> challenge C1 -> code K1
Transaction G2: verifier V2 -> challenge C2 -> code K2
~~~

If custom code mistakenly retrieves `V2` to exchange `K1`, the AS rejects it even though both verifiers are syntactically valid. Therefore never store the verifier in a global variable shared across requests.

### Scenario E — AS Ignores the Verifier

The client sends a challenge during authorize, yet the AS issues tokens for the code even when `code_verifier` is missing or wrong.

This is a **server-side PKCE enforcement bug on the Authorization Server**. Enabling a customizer on the client alone does not guarantee safety if the AS does not enforce verification.

### Scenario F — SPA Hit by XSS

PKCE helps defend against an attacker who only intercepts an authorization code via redirect, yet if malicious JavaScript runs inside the SPA's own origin, the attacker can read whatever data the SPA can access.

Defenses must include XSS mitigation, safe token management, trusted OAuth2 libraries, and proper browser configuration. PKCE does not replace these controls.

### Scenario G — Client Uses PKCE, but Callback Comes from Wrong Issuer

An application integrates multiple IdPs and receives a response from a provider that does not match the initiated request.

PKCE does not replace binding to the right issuer/provider. The application must tie the authorization request to the right registration, verify `state`, verify issuer/ID Token per protocol, and prevent provider mix-up.

## 14. Common Errors When Configuring PKCE

| Symptom | Possible Cause | How to Address |
|---|---|---|
| Authorization endpoint reports missing PKCE | Client did not send `code_challenge` or `code_challenge_method` | Enable PKCE S256 in resolver/client library; confirm AS policy. |
| Token endpoint returns `invalid_grant` | Wrong/missing verifier, expired/reused code, wrong redirect URI, or client mismatch | Check transaction correlation and each condition; do not assume PKCE alone. |
| Callback reports `invalid_state` | State mismatch or lost authorization request/session | Check cookies, session, load balancer, callback path, and request repository. |
| Public client sends client secret and AS rejects it | Client registered as `none` or invalid secret | Remove embedded secret in public client; use client ID and PKCE per registration. |
| Confidential client sends PKCE but token request lacks secret/key | Misconfigured client authentication | Enable the registered authentication method; PKCE does not replace client auth. |
| `withPkce()` enabled, yet verifier is missing at callback | Custom `AuthorizationRequestRepository` dropped request attributes or session was lost | Preserve authorization request data between redirect and callback. |
| Verifier changes before token request | Regenerated or stored in a global variable shared across logins | Generate once per transaction and store keyed to state/request. |
| `S256` challenge mismatches despite seemingly right verifier | Used standard Base64, kept padding, hashed wrong encoding, or trimmed verifier | Use ASCII + SHA-256 + unpadded Base64URL; never alter verifier after generation. |
| AS only accepts `plain` | Legacy AS or incompatible configuration | Review capabilities and upgrade policy; do not silently downgrade. |
| Spring Security uses Servlet but reactive classes were configured | Wrong stack APIs imported | Use `HttpSecurity`/`SecurityFilterChain` for Servlet; reactive classes for WebFlux. |
| OIDC login succeeds but API returns `401` | Invalid/wrong-audience or expired access token | Check access token and resource server config; not a PKCE error if code exchanged. |
| Login lost when callback crosses instances | Local in-memory session or misconfigured cookie/forwarded headers | Use shared session store and proper routing; ensure callback sees initial request. |
| Client `server-demo` not found | Missing registration ID or different name | Align `/oauth2/authorization/{registrationId}` URL with repository. |
| Callback URL is `http` instead of `https` behind reverse proxy | `{baseUrl}` uses internal scheme/host | Configure trusted forwarded headers and registered redirect URI. |

### 14.1. Distinguishing PKCE Errors from Client Authentication Errors

An `invalid_client` error usually relates to client authentication: wrong secret/key, wrong authentication method, missing header, or invalid registration.

An `invalid_grant` error can stem from an invalid code, mismatched redirect URI, wrong PKCE verifier, or other conditions. Inspect **the error description and AS behavior in a secure context** rather than guessing from the error code alone.

### 14.2. Order of Incident Isolation

When login fails, step through in order:

1. Did the client send the authorization request with the right registration ID?
2. Is an S256 challenge present?
3. Does the AS require and store the challenge with the code?
4. Did the callback hit the right redirect URI and state?
5. Did the client retrieve the right authorization request/verifier?
6. Did the token request send the verifier together with the code and proper client authentication?
7. What error did the AS return, and at which step?
8. After receiving tokens, did OIDC validation and application authorization succeed?

This is the order for tracing the protocol flow, not a procedure for printing secrets in logs. When enabling trace/debug logs, mask codes, tokens, verifiers, and credentials.

## 15. Applying PKCE in Applications with Multiple Client Registrations

An application can have both public registrations and confidential registrations, or multiple confidential registrations across different providers:

~~~text
Registration "mobile":
  Client type: public
  Client authentication: none
  PKCE: S256

Registration "web":
  Client type: confidential
  Client authentication: client_secret_basic
  PKCE: S256

Registration "enterprise":
  Client type: confidential
  Client authentication: private_key_jwt
  PKCE: S256
~~~

Registrations may share the `authorization_code` grant while differing in client ID, callback, scopes, and token endpoint. **The PKCE verifier must belong to the exact authorization request and registration**. Never reuse one verifier across all three registrations or pull a challenge from another request.

Spring Security selects the registration from the initiation path `/oauth2/authorization/{registrationId}` and saved metadata; custom resolvers must maintain accurate correlation so the callback uses the right registration.

In multi-issuer applications, also guard against issuer mix-up via provider correlation and issuer verification on tokens. PKCE alone does not prove a token came from a trusted issuer.

## 16. Configuration Choices by Scenario

### 16.1. Spring Boot MVC App with Backend Holding Secrets

**Goal:** users log into a portal via OIDC; the backend holds access tokens and sessions.

Approach:

- The registration is a **confidential client**.
- Spring Security Servlet `oauth2Login()` handles the Authorization Code Flow.
- The token endpoint uses the registered client authentication.
- Enable PKCE S256, e.g. via `withPkce()` when needed to guarantee it on your current version/configuration.
- Store authorization requests/verifiers per session and protect cookies/sessions.
- Validate the OIDC ID Token and manage authorized clients/tokens on the backend.

This is typically the right design for a Spring Boot web application capable of keeping secrets.

### 16.2. SPA Served Statically by Spring Boot but Running in the Browser

**Goal:** JavaScript code running in the browser performs the OAuth2 authorization code flow itself.

Approach:

- The browser app is a **public client** and cannot hold a client secret.
- The SPA uses an OAuth2/OIDC client library supporting Authorization Code + PKCE.
- The AS must enforce PKCE, register the SPA's redirect URI, and configure CORS/token endpoint policies appropriately.
- Do not assume backend `oauth2Login()` controls token exchanges executed by the SPA; those are two distinct client models.

If replaced by a BFF so tokens stay on the server, the Spring Boot backend becomes the confidential OAuth2 client for that flow.

### 16.3. Spring Boot Integrating an Internal IdP Requiring PKCE for All Clients

**Goal:** regardless of confidential web or public client, the AS mandates S256.

Approach:

- Configure each client registration with `authorization_code` grant and the appropriate client authentication method.
- Enable S256 for every authorization request.
- Ensure every token request carries the right `code_verifier` for each code.
- The AS rejects authorization requests missing a challenge or token requests with a wrong verifier per policy.
- Observe the flow during deployment, especially custom resolvers and session stores.

Never ignore a mandatory AS policy simply because a library once had a different default.

## 17. A PKCE Thought Exercise

Suppose two login requests are initiated concurrently:

~~~text
G1: verifier = V1, challenge = C1, code = K1
G2: verifier = V2, challenge = C2, code = K2
~~~

**Question 1.** Can `V2` be used to exchange `K1`?

**Answer:** No. The AS must compare the challenge derived from `V2` against `C1` bound to `K1`; the two values do not match, so it must reject the exchange.

**Question 2.** If the client is confidential and sends the right client secret, can it omit `V1` to exchange `K1`?

**Answer:** No, if `K1` was issued with PKCE. Client authentication and PKCE verification are complementary conditions.

**Question 3.** If the client exchanges `K1` successfully and then resends `K1` with `V1`, will it receive another token?

**Answer:** No. Authorization codes must be single-use; a matching verifier does not allow re-exchanging an already used code.

**Question 4.** Knowing `C1` from the authorize URL, can an attacker recover `V1`?

**Answer:** When the verifier is generated with sufficient randomness and S256 is used, reversing the challenge back to the verifier is infeasible under the expected threat model. If the client uses a predictable or fixed verifier, protection weakens.

**Question 5.** In OIDC, if PKCE matches, can `nonce` or ID Token signature checks be skipped?

**Answer:** No. PKCE verifies continuity of the code exchange; `nonce` and ID Token validation protect separate objectives.

**Question 6.** If an SPA has a client ID and a hardcoded client secret in JavaScript, is it considered a confidential client?

**Answer:** No. A secret hardcoded in JavaScript cannot be reliably protected; the SPA remains a public client.

**Question 7.** Does `code_challenge_method=S256` go in the authorization request or the token request?

**Answer:** In the authorization request alongside the challenge. The token request carries the original verifier for the AS to hash and compare.

**Question 8.** Does an `invalid_grant` error on the token request always mean PKCE failed?

**Answer:** No. An expired or reused code, wrong redirect URI, or mismatched client binding can also produce this error.

## 18. Summary by Component

| Component / Value | Public Client | Confidential Client |
|---|---|---|
| `response_type=code` | Yes | Yes |
| `code_challenge` and `code_challenge_method=S256` | Sent at authorize | Sent at authorize |
| `code_verifier` | Generated uniquely, retained per transaction | Generated uniquely, retained per transaction |
| `state` | Generated and verified at callback | Generated and verified at callback |
| `client_id` | Yes | Yes |
| `client_secret`/private key | No trustworthy long-lived secret stored | Stored on backend and used per registration |
| Token request | `code` + `code_verifier` and required parameters | `code` + `code_verifier` **and** client authentication |
| Entity enforcing PKCE | Authorization Server | Authorization Server |
| After receiving tokens | Protect tokens per public environment | Protect tokens on backend, manage sessions |
| OIDC ID Token validation | Still mandatory for OIDC | Still mandatory for OIDC |

The key takeaway is that **PKCE is not a new grant**. It adds **per-transaction proof** to the Authorization Code Grant. The client sends `code_challenge` when initiating authorization and sends the original `code_verifier` when exchanging the code; the AS must bind both to the same authorization code. **Public clients need PKCE** because they cannot rely on secrets embedded in the app, while **confidential clients should use PKCE alongside client authentication** for stronger protection.

In Spring Security OAuth2/OIDC Client, leverage the framework's PKCE support, configure the proper `ClientRegistration` type, and ensure authorization request data is persisted through the callback. For Servlet, `OAuth2AuthorizationRequestCustomizers.withPkce()` combined with `DefaultOAuth2AuthorizationRequestResolver` provides an explicit way to enable PKCE for confidential clients; for public clients, Spring Security supports PKCE in unauthenticated client registration flows. In both cases, **final enforcement must be performed by the Authorization Server**.
