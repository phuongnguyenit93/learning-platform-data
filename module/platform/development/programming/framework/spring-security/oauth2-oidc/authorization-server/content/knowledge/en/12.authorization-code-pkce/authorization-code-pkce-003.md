# Binding the Code to Client and redirect_uri

> **Chapter:** Authorization Code and PKCE  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Scope:** Designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot.  
> **Illustrated Versions:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.x (Servlet stack). For Spring Security 7.x, check the APIs, starters, and documentation for your exact version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why an **authorization code** must be bound to a **specific client** and a **verified redirect URI**.
2. Distinguish between `client_id` binding, confidential client authentication, and PKCE `code_verifier` proof.
3. Describe the checks across the two stages `GET /oauth2/authorize` and `POST /oauth2/token`, including parameter mismatch scenarios.
4. Understand what Spring Authorization Server stores in `OAuth2Authorization` and how `RegisteredClientRepository` coordinates with `OAuth2AuthorizationService`.
5. Configure `RegisteredClient` for confidential and public clients, enable PKCE, and set redirect URIs and authorization code lifetimes.
6. Design tests for code reuse, wrong client, wrong redirect URI, wrong verifier, and untrusted callbacks.

**Main takeaway:** An authorization code is not a generic "token exchange ticket" that any client can redeem. A code can only be used under **the exact conditions the Authorization Server (AS) recorded when issuing it**.

## 2. What Does an Authorization Code Represent?

In the Authorization Code Grant, the Resource Owner logs into the AS and approves permissions for the OAuth2 Client (if required by policy). The AS issues a **short-lived, single-use** authorization code through a registered callback.

The client receives the code and calls the token endpoint to request an access token and, in a valid OpenID Connect flow, potentially an ID token. Merely possessing the code string **is not enough** for the AS to issue tokens; the AS must also verify which client the code was issued to, which redirect URI was used, that the code is unexpired/unused, and whether PKCE checks pass.

An easy-to-remember model:

~~~mermaid
flowchart TD
    AR["Authorization request<br/>client_id + redirect_uri + code_challenge"]
    CR["RegisteredClient<br/>client_id + redirectUris + grantTypes"]
    UA["Authenticated User<br/>Consent / authorizedScopes"]
    AO["Stored OAuth2Authorization<br/>registeredClientId + code + metadata"]
    CODE["Authorization code sent via redirect"]
    TR["Token request<br/>code + redirect_uri + code_verifier<br/>+ client authentication if required"]
    CHECK{"AS verifies all<br/>bindings"}
    TOK["Issue tokens"]
    DENY["Reject: no tokens issued"]

    AR --> CHECK
    CR --> CHECK
    UA --> CHECK
    CHECK -->|"Issue code under valid conditions"| AO
    AO --> CODE
    CODE --> TR
    TR --> CHECK
    AO --> CHECK
    CHECK -->|"All redemption conditions valid"| TOK
    CHECK -->|"Invalid or code already used"| DENY
~~~

The diagram groups the authorize and token stages into a single check node for clarity; **each stage has its own validation checks**. The AS does not issue an access token directly from the authorization code callback.

### 2.1. Four Pieces of Information Bound to the Code

| Information | Purpose | Key Check |
| --- | --- | --- |
| **Client** | Which application was the code issued for? | The client at the token endpoint must be the client that received the code |
| **Redirect URI** | Which callback did the AS accept during the authorization request? | The `redirect_uri` in the token request must match the value in the authorization request when sent |
| **PKCE challenge** | Which client holds the matching `code_verifier`? | `S256(code_verifier)` must match the `code_challenge` bound to the code |
| **Code status** | Is the code still usable? | Unexpired, not yet exchanged for tokens, not invalidated; consumed with single-use semantics |

The AS also binds the authorization state to the Resource Owner, granted scopes, grant type, and metadata needed by the token endpoint. Never treat an authorization code as self-declared client data that you can simply decode and trust.

## 3. Full Binding Flow from Authorize to Token

Assume the system consists of:

- **Resource Owner:** Lan.
- **Confidential Client:** backend `booking-bff`.
- **AS:** `https://auth.example.test`.
- **Registered Callback:** `https://app.example.test/login/oauth2/code/booking-bff`.
- **Resource Server:** `booking-api`, receiving the access token after code exchange succeeds.

The `.example.test` domain and client IDs are illustrative only, not live endpoints.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant B as Browser
    participant C as Client (booking-bff)
    participant AS as Authorization Server
    participant STORE as Authorization Store

    C->>C: Generates state, code_verifier, code_challenge
    C-->>B: Redirects to /oauth2/authorize
    B->>AS: client_id + redirect_uri + state + PKCE challenge
    AS->>AS: Verifies RegisteredClient + redirect URI + scopes
    AS->>U: Authenticates user and consent if needed
    U-->>AS: Logs in / approves
    AS->>STORE: Saves authorization, code, client, redirect URI, PKCE
    AS-->>B: 302 callback?code=...&state=...
    B->>C: Callback carrying code and state
    C->>C: Verifies state and login context
    C->>AS: POST /oauth2/token + code + redirect_uri + code_verifier + client auth
    AS->>STORE: Loads authorization by code
    AS->>AS: Compares client, redirect_uri, PKCE, expiry, and status
    alt All valid
        AS->>STORE: Marks code as used
        AS-->>C: Access token (+ ID token if OIDC)
    else Invalid
        AS-->>C: OAuth2 error, no tokens issued
    end
~~~

Each request is a separate HTTP transaction. The AS uses the authorization store to link the two stages, **not a `ThreadLocal` from the earlier browser request** when the backend client calls the token endpoint.

## 4. First Binding: Authorization Code Belongs to the Right Client

### 4.1. `client_id` Is an Identifier, Not a Secret

`client_id` helps the AS locate the `RegisteredClient`, including attributes such as grant types, redirect URIs, client authentication methods, scopes, and PKCE policy.

Example:

~~~text
RegisteredClient A
  client_id: booking-bff
  redirect_uri: https://app.example.test/login/oauth2/code/booking-bff

RegisteredClient B
  client_id: reporting-web
  redirect_uri: https://reports.example.test/oauth2/callback
~~~

A code issued during an authorization request for `booking-bff` **cannot be valid when `reporting-web` brings that code to the token endpoint**. The AS must verify that the code belongs to the corresponding `RegisteredClient`.

Keep the wording exact: `client_id` **is public** in the authorization request and can be read by others; `client_id` alone does not prove the caller is a legitimate application. Protection relies on client authentication (when confidential), PKCE, registered redirect URIs, and code issuance checks.

### 4.2. Confidential Client Authenticates at the Token Endpoint

A backend can keep a secret safely on the server side; it is registered as a **confidential client** and typically uses an authentication method such as `client_secret_basic`.

At the token endpoint:

1. The AS authenticates the client using its registered method.
2. The AS looks up the issued code and verifies it belongs to **the exact `RegisteredClient`** just authenticated.
3. The AS verifies the redirect URI, PKCE if applicable, expiration, and code status.
4. Only when all conditions pass does the AS issue tokens.

If the secret is wrong, the AS may return `invalid_client`. If the client authenticates validly but sends a code issued to another client, the AS rejects the grant, typically with `invalid_grant`.

**Having a valid client secret does not grant permission to redeem every authorization code in the system.**

### 4.3. Public Client Identified by Client ID and Protected by PKCE

A mobile app or pure SPA **cannot hold a long-lived confidential client secret**. Public clients typically register `ClientAuthenticationMethod.NONE`, use Authorization Code + PKCE, and provide `client_id` in the token request via the supported mechanism.

At the token endpoint, the AS checks that the code belongs to that client ID and that `code_verifier` matches the challenge bound to the code. However, a public client **is not authenticated by a client secret**; anyone can know or send the same `client_id`. Therefore, PKCE is a non-negotiable binding to stop an attacker from exchanging a stolen code.

If an attacker captures both the code **and** the verifier, PKCE can no longer stop them. You still must protect the redirect URI, verifier memory/storage, `state`, TLS, and the overall application.

### 4.4. When One System Has Multiple Clients

A BFF, SPA, mobile app, and admin app should have **separate client registrations** if they differ in trust level, redirect URIs, grant types, or scopes. Do not share a single client ID just to save configuration when applications have different security needs.

Binding a code to its client prevents someone from taking a valid code from one client and redeeming it in another client's token request. It does not replace authorization enforcement at the Resource Server.

## 5. Second Binding: Exact `redirect_uri`

### 5.1. Why Is Redirect URI a Security Boundary?

The authorization code is delivered through **the browser** to the OAuth2 Client's callback. If the AS allows arbitrary callbacks, an attacker could supply an address they control and receive the user's code after the user logs in.

Therefore, before issuing a code, the AS must verify that `redirect_uri` **belongs to the URIs registered for that client** and satisfies applicable OAuth2/profile rules. The browser may only be redirected to a callback accepted by the AS.

Examples:

| Registered redirect URI | Request value | Safe outcome |
| --- | --- | --- |
| `https://app.example.test/callback` | `https://app.example.test/callback` | May be valid if other conditions pass |
| `https://app.example.test/callback` | `https://evil.example.test/callback` | Rejected |
| `https://app.example.test/callback` | `https://app.example.test.evil.test/callback` | Rejected |
| `https://app.example.test/callback` | `https://app.example.test/callback/` | Must not strip trailing `/` to allow it |
| `https://app.example.test/callback` | `http://app.example.test/callback` | Rejected due to scheme mismatch |
| `https://app.example.test/callback?flow=web` | `https://app.example.test/callback?flow=mobile` | Must not alter query parameters |
| `https://app.example.test/callback` | `https://app.example.test/callback#code` | Fragments are not allowed in registered redirect URIs |

Never use logic like `startsWith("https://app.example.test")` or hostname wildcards to validate callbacks. A URL that looks like a valid domain can still route to an attacker-controlled host.

### 5.2. How Does "Identical" Comparison Apply?

Under OAuth 2.0 (RFC 6749, Section 4.1.3), **if `redirect_uri` was sent in the authorization request, then `redirect_uri` is required in the token request and must be identical to the value originally sent**.

Example:

~~~text
GET /oauth2/authorize
  client_id = booking-bff
  redirect_uri = https://app.example.test/login/oauth2/code/booking-bff

POST /oauth2/token
  code = ...
  redirect_uri = https://app.example.test/login/oauth2/code/booking-bff
  => The two logical values match.
~~~

Distinguish between the **URI value** and its HTTP wire encoding: in an authorization request, the URL is typically percent-encoded in the query string; at the token endpoint, the URI is form-encoded in the body. Once the framework properly decodes the parameters, **the `redirect_uri` value must match the original value**.

Do not normalize into a "close enough" URI to let it pass—for instance, changing path casing, stripping slashes, dropping query strings, changing hosts, changing schemes, or adding ports. Specialized profiles like native apps using loopback redirects may have specific port rules under RFC 8252; those exceptions must be intentionally supported by the AS and strictly tested, never generalized into wildcards for websites.

### 5.3. What If the Authorization Request Omits `redirect_uri`?

The OAuth 2.0 specification has conditions under which omitting `redirect_uri` in the authorization request is allowed when a valid callback can be determined from registration per server profile. When the authorize request **does** include the parameter, the token request **must** send back the exact same URI; that is a critical rule to remember.

For clear control and fewer mistakes in Spring Authorization Server applications, **configure the exact URI in `RegisteredClient` and generally send the explicit URI in both steps**, unless a verified profile and API specify otherwise. Never intentionally omit the parameter to "loosen" matching.

### 5.4. Can `redirect_uri` Contain a Fragment?

An OAuth 2.0 registered redirect URI must not contain a fragment. A browser callback with an authorization code normally places `code` and `state` in the query string of the verified redirect URI (or another response mode supported by the profile). Do not put the code in a fragment out of habit from legacy flows, or construct links with the wrong response mode.

### 5.5. Never Redirect When the Callback Is Unverified

An authorization request with an unregistered `redirect_uri` must be **rejected at the AS**. The server **must never redirect the browser to an untrusted URI** to report an error, as that creates an open redirect and leaks information.

Once the redirect URI is safely verified, the AS can return an OAuth2 authorization error response to the callback in cases permitted by the specification.

## 6. Third Binding: PKCE Links the Code to `code_verifier`

### 6.1. What Does PKCE Add?

PKCE (Proof Key for Code Exchange, RFC 7636) prevents an attacker who intercepts an authorization code on the callback path from exchanging that code for tokens **when the attacker does not know the verifier**.

The client performs:

1. Generates a high-entropy random `code_verifier` adhering to standard character set and length rules.
2. Computes `code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))`, omitting padding, with `code_challenge_method=S256`.
3. Sends `code_challenge` in the authorization request, **never the verifier**.
4. The AS binds the challenge and method to the issued authorization code.
5. The client sends `code_verifier` at the token endpoint; the AS recomputes and compares it against the stored challenge.

An example pair from RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

This is a **standard test vector**—never reuse it as a static verifier in real login sessions. A fresh `code_verifier` must be generated for each authorization attempt and kept in a client context that can be matched on callback.

### 6.2. PKCE Does Not Replace Client Binding or Redirect Validation

| Protection | What It Prevents | Does It Replace Other Protections? |
| --- | --- | --- |
| Client binding | A code issued to Client A cannot be exchanged by Client B | Does not replace confidential client authentication |
| Redirect URI binding | Code is not sent to unregistered callbacks and token request cannot swap callbacks | Does not replace PKCE |
| PKCE | A party holding only the code without the verifier cannot exchange it for tokens | Does not replace redirect URI, client ID, or client secret verification |
| `state` | Client binds authorization response to the exact request it initiated; mitigates CSRF/mix-up by design | Does not replace `code_verifier` |
| OIDC `nonce` | Binds ID token to the authentication request per OIDC profile | Does not replace authorization code binding |

**S256** is the preferred method. Never choose `plain` just to avoid using a SHA-256 library, unless a specific compatibility constraint is permitted by protocol and policy. In modern deployments, require PKCE for both public and confidential clients whenever possible, as PKCE also mitigates certain code injection/leakage scenarios.

## 7. Two Separate Validation Stages in the Authorization Server

### 7.1. Authorization Endpoint — Deciding Whether to Issue a Code

At `/oauth2/authorize`, the system must verify:

- `client_id` points to a valid `RegisteredClient`.
- The client is allowed to use the Authorization Code Grant.
- `response_type` is valid for the grant being processed.
- `redirect_uri` is valid according to registration and profile.
- Requested scopes are permitted, and consent and Resource Owner authentication are satisfied.
- PKCE includes `code_challenge` and `code_challenge_method` if required by client/policy.
- No code is ever issued to an unverified browser callback.

When all conditions pass, the AS issues an authorization code, associates it with the client and required metadata, and redirects the browser to the valid callback.

### 7.2. Token Endpoint — Deciding Whether to Exchange the Code

At `POST /oauth2/token`:

- Read grant type `authorization_code` and the code.
- Identify/authenticate the client against `RegisteredClient` and its registered authentication method.
- Load the authorization from the store and verify the code belongs to **the same client**.
- Verify `redirect_uri` matches the value from authorize when that parameter was sent; follow applicable profile rules.
- Verify `code_verifier` against the challenge bound to the code.
- Verify the code is unexpired, unused, and the authorization has not been invalidated.
- Mark the code as consumed, issuing tokens only if all conditions are valid.

Under RFC 6749, an authorization code is a single-use artifact; if an already-used code is resubmitted, the AS must reject it, and the spec recommends revoking previously issued tokens from that code when reuse is detected. Replay control under concurrent load must be tested against real storage and transactions.

### 7.3. Check Order May Vary, but the Final Policy Must Be Consistent

Do not tie tests to **one exact internal error message** when multiple conditions fail at once. For instance, a request with both a wrong client secret and a wrong code may be rejected immediately at client authentication. Tests should hold all other assumptions valid and break one condition at a time.

What the test must prove: **no tokens are issued** whenever a required condition fails.

## 8. Complete HTTP Example: Confidential Client and PKCE

### 8.1. Authorization Request

The client registers callback `https://app.example.test/login/oauth2/code/booking-bff` and saves `state` and `code_verifier` in a secure session. It then redirects the browser:

~~~http
GET /oauth2/authorize?response_type=code&client_id=booking-bff&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fbooking-bff&scope=openid%20booking.read&state=state-unique-example&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
Accept: text/html
~~~

`state-unique-example` is only a placeholder. In a real application, generate a random state, save it, and verify it separately for each authorization attempt.

After login and consent, the AS returns:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/booking-bff?code=SHORT_LIVED_CODE&state=state-unique-example
Cache-Control: no-store
~~~

`SHORT_LIVED_CODE` is an illustrative symbol. The client must match `state` before exchanging the code, and also verify issuer/response protections against authorization server mix-up supported by the profile and application.

### 8.2. Token Request

The confidential client backend calls the AS directly over TLS:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64(booking-bff:client-secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=SHORT_LIVED_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fbooking-bff&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

This is a simplified HTTP example, not real credentials. With `client_secret_basic`, the Basic header is constructed per the client library's OAuth2/HTTP Basic encoding rules; never paste real secrets into logs, URLs, or shared tools. The backend must send **the same redirect URI** used at authorize and the verifier saved in that request's session.

### 8.3. Comparing Three Cases

| Token request parameters | Outcome |
| --- | --- |
| Valid `client_secret`, `code` belongs to `booking-bff`, matching URI/verifier | AS may issue tokens after remaining checks |
| Valid secret, but code belongs to `reporting-web` | AS rejects grant |
| Code belongs to right client, but `redirect_uri` differs or `code_verifier` is wrong | AS rejects grant |

If the Client calls the token endpoint with the wrong client authentication method, the AS may return `invalid_client`. If the client authenticates validly but the code or code bindings are invalid, the error is typically `invalid_grant`. Avoid revealing in error descriptions whether a specific code exists, which user it belongs to, or where it was redeemed.

## 9. Configuring `RegisteredClient` in Spring Authorization Server

In Spring Authorization Server 1.x, `RegisteredClient` is where you declare the client, callback, and PKCE policy. Below are **two separate registration examples**: a confidential BFF and a public client.

### 9.1. Confidential BFF Registration Example

~~~java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

public final class BookingClientRegistrations {

    private BookingClientRegistrations() {
    }

    public static RegisteredClient confidentialBff(
            PasswordEncoder passwordEncoder,
            String secretFromSecureConfiguration) {

        return RegisteredClient
            .withId("booking-bff-internal-registration-id")
            .clientId("booking-bff")
            .clientSecret(passwordEncoder.encode(
                secretFromSecureConfiguration))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "https://app.example.test/login/oauth2/code/booking-bff")
            .scope(OidcScopes.OPENID)
            .scope("booking.read")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
            .tokenSettings(TokenSettings.builder()
                .authorizationCodeTimeToLive(Duration.ofMinutes(3))
                .build())
            .build();
    }
}
~~~

Meaning:

- `clientId("booking-bff")`: public identifier of the client.
- `clientSecret(...)`: secret loaded from secure configuration and hashed with `PasswordEncoder`; never hardcode raw secrets in the repository.
- `CLIENT_SECRET_BASIC`: requires confidential client authentication at the token endpoint.
- `AUTHORIZATION_CODE`: client is allowed to use the code grant.
- `redirectUri(...)`: exact registered callback.
- `requireProofKey(true)`: requires PKCE when the client requests an authorization code.
- `requireAuthorizationConsent(true)`: enforces consent policy per configuration.
- `authorizationCodeTimeToLive(...)`: sets a short code lifetime.

This is a **registration factory**, not a complete Authorization Server configuration. You must register it in a `RegisteredClientRepository` and supply a password encoder, secret, authorization storage, user authentication, key management, issuer, and token/consent services. In persistent environments, manage the internal ID stably; do not create duplicate registration records on every startup.

### 9.2. Public Client Registration Example

Illustrative example of a public mobile client using an HTTPS callback verified on the mobile platform via App Links/Universal Links in real deployments:

~~~java
public static RegisteredClient publicMobileClient() {
    return RegisteredClient
        .withId("booking-mobile-internal-registration-id")
        .clientId("booking-mobile")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://mobile.example.test/oauth2/callback")
        .scope(OidcScopes.OPENID)
        .scope("booking.read")
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .requireAuthorizationConsent(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .authorizationCodeTimeToLive(Duration.ofMinutes(3))
            .build())
        .build();
}
~~~

This method can live in the same factory class as the previous example using the corresponding imports. A public client **has no client secret**. When exchanging a code, it uses `client_id` and `code_verifier` per the AS contract, and the token endpoint verifies that the code belongs to that client registration. Never embed a confidential client secret in a mobile app and claim it is secure.

For native apps, redirect URIs and callback handling must comply with RFC 8252. A plain HTTPS path **is not enough** to prove the OS binds the callback exclusively to the app; you must verify App Links/Universal Links and platform requirements. Loopback URIs or custom schemes should only be used when fully supported by the profile and AS.

### 9.3. Public Client Token Request Example

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=booking-mobile&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fmobile.example.test%2Foauth2%2Fcallback&code_verifier=VERIFIER_SAVED_BY_CLIENT
~~~

There is no `Authorization: Basic ...` header because the client is registered with authentication method `none`. `VERIFIER_SAVED_BY_CLIENT` must be the real value that generated the challenge in the authorization request, not a placeholder string. Public clients must still protect the verifier and state from being read or injected by untrusted code during authorization.

## 10. Where Does Spring Authorization Server Store and Check Bindings?

### 10.1. Client Registration

`RegisteredClientRepository` supplies the registered client to:

- Authorization endpoint: checks `client_id`, grant type, `redirect_uri`, and scopes.
- Token endpoint / client authentication: checks the client's authentication method.
- Token / grant processing: verifies the code belongs to the exact client registration.

Registrations are typically stored via `InMemoryRegisteredClientRepository` for experimentation or `JdbcRegisteredClientRepository` in persistent examples, depending on production architecture.

### 10.2. Authorization Record and Authorization Code

`OAuth2AuthorizationService` is where the AS stores `OAuth2Authorization`, including fields such as:

- `registeredClientId` (internal identifier of the `RegisteredClient`).
- `principalName` and grant type.
- Authorized scopes and request metadata/attributes.
- The authorization code, expiration, token state, and data needed for comparison during code exchange.
- PKCE and redirect URI metadata needed by providers to complete the grant.

Exact fields and attribute keys live in the API model of your Spring Authorization Server version. Never guess internal attribute keys when querying the database directly; **let the official providers store and retrieve them via `OAuth2AuthorizationService`**.

If you run `InMemoryOAuth2AuthorizationService` across multiple AS instances without shared state, a browser may receive a code from instance A while a token request hitting instance B cannot find the code. Production deployments require an appropriate shared/distributed store and transactional single-use code enforcement.

### 10.3. Providers Handling the Two Distinct Steps

| Step | Typical Class in SAS 1.x | Responsibility |
| --- | --- | --- |
| Authorization endpoint | `OAuth2AuthorizationCodeRequestAuthenticationProvider` | Validates request, client, URI, scopes, consent, and issues code via AS components |
| Token endpoint | `OAuth2AuthorizationCodeAuthenticationProvider` | Processes code exchange, verifies client and grant bindings |
| Client authentication at token endpoint | Corresponding client authentication providers | Verifies `client_secret_basic`, other methods, or identifies public clients per configuration |
| Grant state | `OAuth2AuthorizationService` | Stores/retrieves authorization code and bound metadata |
| Client configuration | `RegisteredClientRepository` | Provides client registrations and allowed settings |

Do not confuse `OAuth2AuthorizationCodeRequestAuthenticationProvider` with `OAuth2AuthorizationCodeAuthenticationProvider`. One handles **requesting the code**, while the other handles **exchanging the code**. Configuring an authorization request validator does not replace checking code ownership and PKCE at the token endpoint.

### 10.4. Do Not Overwrite Default Validations

When customizing `OAuth2AuthorizationEndpointConfigurer` and its provider, preserve the standard callback and scope validation logic. If you call `setAuthenticationValidator(...)` on `OAuth2AuthorizationCodeRequestAuthenticationProvider`, chain the default validators:

~~~java
Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
    OAuth2AuthorizationCodeRequestAuthenticationValidator
        .DEFAULT_REDIRECT_URI_VALIDATOR
    .andThen(
        OAuth2AuthorizationCodeRequestAuthenticationValidator
            .DEFAULT_SCOPE_VALIDATOR
    )
    .andThen(context -> {
        // Add only well-defined business policy checks.
        enforceAdditionalPolicy(context);
    });

codeRequestProvider.setAuthenticationValidator(validator);
~~~

`enforceAdditionalPolicy` and `codeRequestProvider` are application integration points, not beans/methods automatically declared in this snippet. The code intentionally demonstrates **how to append extra conditions without dropping default validations**.

Never alter custom converters/providers to accept unregistered URIs, skip PKCE, or issue codes based on an unverified `client_id`/URI.

## 11. Three Attack Scenarios to Recognize

### 11.1. Code Theft via Loose Redirect URI Validation

**Scenario:** The AS allows arbitrary `redirect_uri` values or prefix matching; an attacker directs the callback to a domain they control.

**Consequence:** The authorization code can be delivered to the attacker.

**Defense:** Register exact callbacks, validate the URI at authorize, never redirect to unverified URIs, and require PKCE and client authentication where appropriate.

### 11.2. Redeeming Client A's Code with Client B

**Scenario:** An attacker obtains a code from an authorization flow for `booking-bff`, then attempts to use `reporting-web`'s credentials/ID at the token endpoint.

**Consequence if AS does not bind code to client:** Tokens risk being issued to the wrong client, breaking consent and client authorization boundaries.

**Defense:** The AS loads the authorization record and checks that `registeredClientId` matches the identified/authenticated client; mismatches must be rejected. Each client uses its own redirect URIs and policies.

### 11.3. Code Theft Without the PKCE Verifier

**Scenario:** An attacker reads an authorization code from a callback path or log and sends it to the token endpoint. The token endpoint requires a verifier and the code is bound to a stored S256 challenge.

**Expected outcome:** Without the verifier, the attacker cannot complete the code exchange. The legitimate client must still protect `state`, redirects, sessions, and the verifier; PKCE cannot stop an attacker who has full control over the client environment or possesses both code and verifier.

### 11.4. Code Injection and Session Mix-Up

An attacker may try to inject a code from another authorization attempt into the client's callback. The client must verify `state`, issuer/AS identity (where supported by profile), PKCE, and the matching login request session. The AS must verify code/client/redirect bindings at the token endpoint. Never rely solely on "the code looks random" or URI allowlisting alone.

## 12. Security Testing by Condition Matrix

The test suite should intentionally break **one binding at a time** to confirm which check fires.

| Test Case | Action | Expected Result |
| --- | --- | --- |
| Valid flow | Matching client, URI, verifier, unused and unexpired code | Tokens issued per grant and policy |
| Wrong client at token endpoint | Code belongs to A, authenticated/sent as client B | Rejected; no tokens issued |
| Wrong client secret | Confidential client sends wrong secret | Client authentication fails, typically `invalid_client` |
| Public client missing `client_id` | Client cannot be properly identified | Rejected per protocol |
| Wrong callback at authorize | URI not in registration | Rejected at AS; never redirects to unknown URI |
| Wrong callback at token | URI differs from value sent at authorize | Grant rejected |
| Missing URI at token | URI was sent at authorize, omitted in token request | Rejected |
| Wrong `code_verifier` | Does not produce the stored S256 challenge | Grant rejected |
| Missing verifier when PKCE required | Fails to prove verifier possession | Rejected |
| Disallowed challenge method | `code_challenge_method` violates policy | Authorization request rejected |
| Expired code | Exchanged after TTL | Grant rejected |
| Code used twice | Exchanged once, then retried | Second attempt issues no tokens |
| Two concurrent requests with same code | Send parallel token requests | Must not issue tokens twice; tests storage atomicity |
| Code belonging to another user | Attempt to swap callback/state or authorization record | Cannot bypass established bindings; keeps client/PKCE checks intact |
| User denies consent | No permissions granted | No valid code issued |
| Request with scope outside registration | Impermissible scope | Rejected or handled per policy without over-granting |
| Valid client secret with wrong verifier | Client credentials valid, PKCE invalid | Grant still rejected |
| Token request over HTTP instead of HTTPS | Fails transport security | Unacceptable for production; endpoint must require TLS |

### 12.1. What Should an Integration Test Prove?

A proper integration test should:

1. Configure `RegisteredClient` A and B with distinct IDs/redirect URIs and PKCE enabled.
2. Initiate a valid authorization request for A, authenticate the Resource Owner, and complete consent.
3. Capture the code from A's redirect callback.
4. Attempt to exchange the code as client B (with B's valid credentials) → **no access token**.
5. Obtain another code for A and attempt exchange as A with a different URI → **no access token**.
6. Obtain another code for A and attempt exchange with the wrong verifier → **no access token**.
7. Obtain a fresh code, exchange it as A with the exact URI/verifier → **succeeds exactly once**.
8. Resubmit the consumed code → **rejected**.
9. Verify the authorization record and token store contain no tokens issued from failed requests.

Never reuse the same code across independent negative cases if an earlier test already succeeded, because later tests will fail due to **replay** rather than testing the target binding.

### 12.2. Writing a Negative Test at the Token Endpoint

Illustrative token exchange request with a wrong redirect URI:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials-for-booking-bff>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_FROM_VALID_AUTHORIZE&redirect_uri=https%3A%2F%2Fattacker.example.test%2Fcallback&code_verifier=VALID_VERIFIER_FOR_CODE
~~~

Outcome: The AS must reject the grant and **issue no tokens**. For code-binding failures, the token endpoint typically uses `invalid_grant` in the OAuth2 error response. Do not test merely by checking HTTP 400; assert that the response has no access token and logs/stores record no successful grant.

### 12.3. Testing a Public Client Without a Client Secret

Register a public client with `ClientAuthenticationMethod.NONE` and `requireProofKey(true)`. Test that a caller who knows `client_id` and the code **without the valid verifier** cannot exchange it for tokens. Also test that Client Credentials cannot be used by the public client if the registration does not allow that grant.

Mocking authentication directly at a controller/service bypasses the real OAuth2 filters. To test code binding, exercise both the **authorization endpoint + token endpoint** and AS providers in an integration test.

## 13. Operating and Observing in Multi-Instance Systems

### 13.1. Consistent Authorization Storage

In a multi-instance environment:

- The authorization endpoint may run on AS instance A.
- The token endpoint may hit AS instance B.
- Both must read and write authorization/code state with the same consistency guarantees.

If each instance uses `InMemoryOAuth2AuthorizationService`, instance B may fail to find a code issued by instance A. Use a durable, shared store—such as JDBC as documented by Spring Authorization Server—or a distributed design with equivalent guarantees. In production, test multiple instances, restarts, and failover.

Pay special attention to **two concurrent token requests using the same code**. Storage and transaction boundaries must enforce single-use semantics; test concurrency against real infrastructure, not just single-process memory.

### 13.2. TTL and Retries

Authorization codes should have short TTLs; `Duration.ofMinutes(3)` above is an **illustrative value** that should be tuned for UX, login/consent latency, policy, and infrastructure.

Never blindly "retry the token request with the same code" after a timeout without knowing whether the AS already processed the first request. The code may already be consumed; the client must handle the error and start a fresh authorization attempt when needed. That is another reason to distinguish network errors from `invalid_grant` and log safe trace IDs.

### 13.3. Protecting Codes, Verifiers, and Callbacks

- Use HTTPS for both the AS and web callbacks in production.
- Never write raw codes, verifiers, access tokens, refresh tokens, or client secrets to logs, traces, analytics URLs, or error pages.
- Reduce code exposure via browser history/referrers with appropriate callbacks, redirect flows, and `Referrer-Policy`/cache policies.
- Never accept dynamic `redirect_uri` values that end users can arbitrarily alter.
- For SPAs/mobile apps, keep the verifier and state scoped to the exact authorization attempt; avoid storing them where untrusted scripts can read them whenever safer options exist.
- Configure cookies/sessions/CSRF cleanly so state does not drift across multiple tabs or concurrent logins.
- Manage client registrations through migrations/approval workflows, auditing all changes to callbacks or grant types.
- Rotate client secrets per policy when a confidential client risks credential exposure; never treat a secret as a replacement for PKCE.

### 13.4. Diagnosing Errors Without Exposing Sensitive Data

When troubleshooting `invalid_grant` at the token endpoint, check in order:

1. Did the request reach the right AS issuer/token endpoint?
2. Which registration was the client identified/authenticated under?
3. Does the code exist and remain unexpired in the authorization store?
4. Is the code bound to the exact `registeredClientId`?
5. Does the redirect URI match the authorize request?
6. Does `code_verifier` match the challenge/method?
7. Was the code already exchanged or invalidated?
8. Is there clock skew, persistence failure, load balancer routing mismatch, or parallel retry?

Log only request IDs, controlled client IDs, error category/checkpoint, timing metadata, and correlation IDs. Never log full callback query strings, raw authorization codes, or verifiers for "quick debugging".

## 14. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `client_id` as a secret | Public clients can be impersonated at the token endpoint if PKCE is skipped | Enforce PKCE; authenticate confidential clients properly |
| Sharing one client ID across SPA, mobile, BFF | Redirect URI/grant/secret policies become hard to isolate | Register each client appropriately |
| Validating URIs with `startsWith(...)` | Open redirect, code leakage | Match URIs strictly per registration/profile |
| Checking URI only at authorize, skipping token check | Code can be exchanged in the wrong context | Bind and check the exact URI per RFC 6749 |
| Omitting `redirect_uri` at token when authorize sent it | Violates callback binding requirement | Resend the identical URI |
| Sending `code_challenge` in PKCE without verifying verifier | Stolen code can be exchanged for tokens | Verify S256 at the token endpoint |
| Defaulting to `plain` | Weakens protection against authorization request observation | Prefer S256 |
| Reusing verifier/state across attempts | Session mix-ups and increased exposure on leak | Generate fresh values per authorization attempt |
| Not marking code as used | Authorization code replay | Consume code once; test concurrency |
| Dropping default redirect validator when customizing policy | Unauthorized callbacks can slip through | Keep default validator and chain custom policy |
| Using in-memory authorization store across multiple AS instances | Token endpoint cannot find the code | Use consistent shared storage |
| Returning OAuth2 codes from a custom controller | Bypasses standard provider/client/PKCE/consent checks | Use standard Spring Authorization Server flow |
| Assuming user login replaces client authentication | Grants issued to the wrong application | Separate Resource Owner authentication from Client authentication |
| Treating an access token as an authorization code | Wrong endpoint and lifecycle | Codes only exchange for tokens; access tokens call Resource Servers |

## 15. Self-Check Questions

**Question 1.** Why can a client with a valid `client_secret` still not exchange a code issued to another client?

**Answer:** The AS must verify that the authorization code is bound to the exact client registration. Successful client authentication only proves the caller is that client; it does not grant access to another client's authorizations.

**Question 2.** If `redirect_uri` in the authorization request has a trailing slash, should a token request omitting that slash be accepted?

**Answer:** No. When `redirect_uri` was sent at authorize, the token request must resend the identical value per RFC 6749. Never normalize two different URIs into one merely because they appear to point to the same resource.

**Question 3.** A public client has no secret; how is code exchange protected?

**Answer:** The AS verifies the code belongs to the client ID and mandates PKCE. The caller must prove possession of the `code_verifier` matching the stored `code_challenge`, alongside redirect URI and code lifecycle checks.

**Question 4.** Can PKCE protect the flow if an attacker obtains both the code and the verifier?

**Answer:** No. PKCE protects against an attacker who only has the code; the client must also protect the verifier, state, callback, session, and execution environment.

**Question 5.** Why is reusing the same code across all negative tests flawed?

**Answer:** The code may already be consumed. Subsequent tests then always fail due to replay and fail to prove binding enforcement for client, URI, or PKCE.

**Question 6.** Why must a multi-instance Authorization Server use shared authorization storage?

**Answer:** An authorization code is issued during an authorize request but exchanged during a separate token request, which may land on a different instance. All instances must share client/code/PKCE state and enforce single-use redemption.

**Question 7.** Are `state` and `code_verifier` the same thing?

**Answer:** No. `state` lets the client correlate the callback with its authorization attempt, whereas `code_verifier` proves authority to exchange the code under PKCE. Both must be generated, stored, and verified for their distinct purposes.

## 16. Pre-Production Checklist

- [ ] Each OAuth2 client has its own registration tailored to its trust level and application.
- [ ] Redirect URIs are strictly registered and verified; no arbitrary callback wildcards exist.
- [ ] Authorization requests include `client_id`, `response_type=code`, profile-compliant `redirect_uri`, `state`, and appropriate PKCE challenge.
- [ ] `requireProofKey(true)` is enabled for clients using the code grant as required by policy.
- [ ] Public clients never embed client secrets in distributed code; they use PKCE S256.
- [ ] Confidential clients authenticate at the token endpoint and still apply PKCE per policy.
- [ ] Token endpoint validates the code against client registration, redirect URI, verifier, expiry, and single-use state.
- [ ] Client validates `state`/issuer context and binds the verifier to the specific authorization attempt.
- [ ] User authentication/consent is never confused with client authentication.
- [ ] Dedicated negative tests cover wrong client, URI, verifier, expired code, replay, and concurrent redemption.
- [ ] Authorization store survives across multiple instances/restarts with proper transactions for code lifecycle.
- [ ] HTTPS, cookies, logging, referrers, and secret handling protect codes and verifiers.
- [ ] End-to-end flow has been tested with Spring OAuth2 Client / Resource Server or the real client.

## 17. References and Conclusion

Consult the official documentation for your **exact library versions**:

- [RFC 6749 — OAuth 2.0 Authorization Framework, Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)

When designing Authorization Code + PKCE, treat **`client_id`, `redirect_uri`, and `code_challenge` as bindings recorded alongside the authorization code**. When exchanging the code, the AS verifies **the right client, the right URI, the right verifier, and an unexpired/unused code**. Together, these bindings preserve continuity across both requests and prevent tokens from being issued in the wrong context in an OAuth 2.0/OIDC system.
