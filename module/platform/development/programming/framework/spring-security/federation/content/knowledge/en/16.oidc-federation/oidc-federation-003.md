# Authorization Code, state, nonce, and PKCE at the Application Boundary in Brokered OIDC

## 1. Context: SAML Upstream, OIDC at the Application Door

A Spring Boot application previously signed users in directly via SAML 2.0. When an **identity broker** is introduced, the architecture can shift:

- The Spring Boot application acts as both an **OpenID Connect Relying Party (OIDC RP)** and an **OAuth 2.0 client**.
- The broker acts as an **OIDC OpenID Provider (OP)** and Authorization Server (AS) toward the application.
- The broker can act as a **SAML Service Provider (SP)** toward an upstream **SAML Identity Provider (IdP)**.
- The user traverses the browser, yet `state`, `nonce`, `PKCE`, and ID Token checks belong to the **OIDC transaction between the application and the broker**, rather than automatically carrying over into the SAML transaction.

This lesson belongs to **Spring Security - federation → OIDC and Brokering**, focusing on **Authorization Code, state, nonce, and PKCE at the application boundary**. It is not a guide to building an Authorization Server or replacing every federation protocol with OIDC.

### Learning Outcomes

After this lesson, you will be able to:

1. Describe the OIDC **Authorization Code Flow**, distinguishing the front-channel browser leg from the back-channel token exchange.
2. Explain four artifacts accurately: `authorization code`, `state`, `nonce`, and `code_verifier/code_challenge`.
3. Know the security checks enforced at the **client, broker, upstream SAML IdP**, and **resource server**.
4. Distinguish the responsibilities of **state** (CSRF/login response injection protection), **nonce** (binding the ID Token to the request), and **PKCE** (binding token exchange to the initiating request).
5. Configure Spring Security Servlet `oauth2Login()`, OIDC client registration, callback URIs, and PKCE when required.
6. Explain why OIDC `state` must not be shared with SAML `RelayState`, why a broker ID Token is not a SAML Assertion, and why callback-supplied issuer/subject values cannot be trusted unchecked.
7. Test `state mismatch`, `nonce mismatch`, `invalid_grant`, missing sessions, and IdP/Broker mix-up.
8. Handle return URLs/deep links safely, along with session cookies, multiple tabs, proxies, secrets, JWKS rotation, multi-tenancy, and disconnects.
9. Write a **standalone** Java 17 program to compute PKCE S256 and compare evidence, without mistaking learning code for a production OIDC client.

Examples target **Java 17+, Spring Boot 3.x, Spring Security 6.5+ Servlet/MVC**. Some APIs existed in earlier Spring Security releases; `ClientRegistration.ClientSettings` APIs have their version noted explicitly. For Spring Security 7.x, check the documentation for the exact release. URLs under `example.org` are illustrative only and are not live login providers.

## 2. Diagram of the Two Trust Boundaries

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant APP as Spring Boot OIDC client
    participant BROKER as OIDC broker OP/AS
    participant IDP as Upstream SAML IdP
    U->>APP: GET /reports/42 when unauthenticated
    APP->>APP: Save SavedRequest + OIDC transaction
    APP-->>U: 302 to broker /authorize (state, nonce, PKCE challenge)
    U->>BROKER: GET authorization endpoint
    opt Broker needs upstream SAML login
        BROKER->>BROKER: Create AuthnRequest, separate SAML RelayState
        BROKER-->>U: Redirect to SAML IdP
        U->>IDP: SAML AuthnRequest
        IDP-->>U: Form POST SAMLResponse
        U->>BROKER: POST to broker's SAML ACS
        BROKER->>BROKER: Validate SAML Signature/Issuer/Audience/Time
    end
    BROKER->>BROKER: Issue authorization code for OIDC client
    BROKER-->>U: 302 to APP callback with code + state
    U->>APP: GET /login/oauth2/code/broker?code=...&state=...
    APP->>APP: Restore OIDC transaction and compare state
    APP->>BROKER: POST token endpoint: code + code_verifier + client auth
    BROKER->>BROKER: Verify code, redirect_uri, client, PKCE
    BROKER-->>APP: Token response: ID Token + access token
    APP->>APP: Validate ID Token signature, iss, aud, exp, nonce...
    APP->>APP: Create application SecurityContext/HTTP session
    APP-->>U: Redirect to /reports/42 if still authorized
~~~

**There are two independent contracts:**

- **Upstream SAML:** The broker trusts the IdP via SAML metadata, signs/verifies SAML XML, and maintains its own `AuthnRequest ID` and `RelayState`.
- **Downstream OIDC:** The application trusts the broker via OIDC issuer/client registration/JWKS, manages `state`, `nonce`, and `PKCE`, and validates the ID Token.

The broker **cannot automatically turn a SAML state string into OIDC proof**. It must verify SAML first and then mint an ID Token **with the broker itself as issuer**, with subject/claims governed by the broker's security contract.

## 3. Four Values Commonly Confused

| Artifact | Where It Appears | Primary Holder/Verifier | Purpose |
| --- | --- | --- | --- |
| **Authorization Code** | Callback from Authorization Endpoint → client; then sent to token endpoint | Broker issues and checks; client uses once | Represents a short-lived authorization grant; exchanged for tokens |
| **state** | Authorization Request via browser and authorization callback | Client creates and stores per session/transaction; client verifies | Correlates callback; prevents CSRF/login code injection and binds browser flow |
| **nonce** | OIDC Authentication Request and `nonce` claim in **ID Token** if sent by client | Client creates/stores; broker echoes in ID Token; client compares after verify | Binds ID Token to transaction, mitigating replay/substitution |
| **code_verifier** | Client only and **back-channel POST token endpoint** | Client creates/stores; broker checks against challenge bound to code | Proof that the party redeeming the code is the one that opened the transaction |
| **code_challenge** | Authorization Request to broker | Broker stores with code; client derives from verifier | Public one-way commitment of the verifier for PKCE S256 |
| **SAML RelayState** | SAML Redirect/POST between broker and upstream IdP | Broker/SP issues and IdP echoes per SAML binding | Context for a **different SAML transaction**, not OIDC state |

**Never write "state = nonce = RelayState = PKCE"**. Although these strings may all be generated using `SecureRandom`, each has an **independent verification point and purpose**. Reusing the same value risks cross-binding, weakens transaction isolation, aids replay, and complicates logging.

## 4. Authorization Code: Front-Channel Receives Only the Code, Back-Channel Exchanges for Tokens

### 4.1 Authorization Request

The client initiates with an HTTPS redirect to the broker's authorization endpoint:

~~~http
GET /authorize?response_type=code
  &client_id=portal-client
  &redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker
  &scope=openid%20profile
  &state=OPAQUE_STATE
  &nonce=OPAQUE_NONCE
  &code_challenge=S256_BASE64URL_VALUE
  &code_challenge_method=S256 HTTP/1.1
Host: broker.example.org
~~~

This is an **illustrative query wrapped onto multiple lines for readability**, not literal syntax for a single raw HTTP request line. `OPAQUE_STATE`, `OPAQUE_NONCE`, and `S256_BASE64URL_VALUE` are descriptive placeholders; real values must be freshly generated by the client for every transaction.

Parameters:

- `response_type=code` selects Authorization Code.
- `client_id` identifies the OIDC client registered at the broker.
- `redirect_uri` must match the **registered redirect URI** per the AS's matching rules; never an arbitrary URL chosen by the browser.
- `scope=openid` turns an OAuth request into an **OpenID Connect authentication** request; `profile` is an optional extra scope per policy.
- `state` is an opaque value bound to the browser login transaction.
- `nonce` binds the ID Token to the request when sent by the client.
- `code_challenge + code_challenge_method=S256` activates PKCE.

**Important:** `client_secret` is **not** in this URL. Nor is `code_verifier` **ever sent** to the browser Authorization Endpoint; it is held back for the token exchange.

### 4.2 Callback to the Client

After the user authenticates/authorizes per policy, the broker redirects:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/login/oauth2/code/broker?code=CODE_VALUE&state=OPAQUE_STATE
~~~

The browser arrives at the callback. The application must **restore the stored authorization request**, check that the returned `state` matches the session/transaction just initiated, and apply appropriate issuer/AS mix-up checks.

This callback delivers only an **authorization code**, **not yet proof of who the user is**. Never do this:

~~~text
GET callback with code -> set session user=admin
~~~

Before establishing a SecurityContext, token exchange, ID Token verification, and business account policy must all succeed.

### 4.3 Server-to-Server Token Request

A client backend POSTs:

~~~http
POST /token HTTP/1.1
Host: broker.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-encoded>

grant_type=authorization_code&
code=CODE_VALUE&
redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker&
code_verifier=PRIVATE_VERIFIER_VALUE
~~~

`<client-credentials-encoded>` and the values shown are illustrative and contain no real credentials. Some clients/ASs use `private_key_jwt`, mTLS, or `client_secret_post` as registered; do not change the client authentication method arbitrarily to work around errors.

**The broker checks**:
- The code was issued to this exact `client_id` and has not yet been redeemed;
- The code is unexpired and has not been replayed;
- `redirect_uri` matches the authorization transaction (if sent/required);
- Client authentication matches the client type;
- The PKCE verifier matches the challenge bound to the code;
- AS policies on consent, redirect, and subject.

Codes are typically **short-lived and single-use**. A code is not an ID Token, access token, or refresh token. If token exchange fails, never use the failed code to "build a session anyway".

### 4.4 Token Response and Session Creation

The broker may return `id_token` and `access_token` for the OIDC Code Flow. The app must:

1. Verify the ID Token for **issuer, signature/JWKS, allowed algorithms, audience/client ID, timestamps**, and other OIDC claims.
2. If a nonce was sent, compare it with `nonce` in the ID Token per spec rules.
3. If the ID Token has multiple audiences, verify `azp` per profile/spec.
4. Use **`iss + sub`** as the logical identity key; never email alone.
5. Enforce local provisioning/tenant/account status and authorization.
6. Create the `Authentication` in the SP session only after all checks pass.

**The access token** is used to call resource servers per granted scopes/audience; **the ID Token** proves the authentication event **to the client**. Never send the ID Token as a Bearer token to arbitrary APIs simply because it is a JWT.

## 5. state: Preventing CSRF at the Callback Endpoint

The OAuth/OIDC authorization callback is a **browser-facing input endpoint**. An attacker can try delivering a code from the **attacker's own transaction** to a victim's browser, tricking the app into confusing identities (login CSRF/code injection). `state` defeats this by requiring the callback to belong to a login transaction **initiated from that browser**.

Flow:

1. The client generates an unpredictable `state` using a CSPRNG, fresh for each login initiation.
2. The client saves it in `AuthorizationRequestRepository` tied to the browser/session or another state store with **browser binding and TTL**.
3. The client sends the same state in the authorization request to the broker.
4. The broker echoes that exact value back on callback redirect.
5. The client restores the transaction from the **previously saved** state/session, verifies the match, and proceeds to token exchange only when valid.
6. Once used, consume/remove it per policy; never allow infinite reuse of state.

**Boundary:** `state` is created and checked by the **client**. The broker **echoes** it, yet must not treat it as proof of authorization or an allowed destination URL. Anything arriving on the callback remains untrusted input until the client matches it against its own stored transaction.

### Should state Embed a Return URL?

Never put raw `https://external.example/redirect` into `state` and redirect based on the callback value. Instead:
- Generate an **opaque state**;
- Store server-side `state → {browser/session, registration, originalLocalPath, createdAt, used=false}` (or use Spring's separate `SavedRequest`);
- After login, redirect only to an **approved local path** after host/scheme validation;
- Make `state` **single-use** with a TTL;
- Do not turn `state` into storage for secrets or personal data.

In Spring Security Servlet, `HttpSessionOAuth2AuthorizationRequestRepository` stores `OAuth2AuthorizationRequest` from request initiation through callback by default. That serves correlation. `RequestCache/SavedRequest` restores the **original HTTP URL**; the two objects are distinct.

### state Is Insufficient Without Browser Binding

A state sitting in a global cache that **any browser can submit** can open login CSRF/session swapping if browser binding and companion checks are missing. **Randomness does not equal binding**. When moving from HttpSession to Redis or a custom state repository, preserve:
- Binding to the initiating session/user-agent or equivalent CSRF defense;
- Short TTL and atomic one-time consumption;
- Binding to the exact client registration/issuer;
- Multi-tab collision/race protection;
- Never exposing state in public telemetry.

## 6. nonce: Binding the ID Token to the Authentication Request

`nonce` is an OIDC Authentication Request parameter. If the client sends a nonce, the OP must place that value in the `nonce` claim of the **ID Token**; the client must match it against the value saved for the transaction. The nonce must have high entropy and be unpredictable.

Example request:

~~~text
GET https://broker.example.org/authorize
  ?client_id=portal-client
  &response_type=code
  &scope=openid
  &nonce=RANDOM_NONCE_FOR_THIS_LOGIN
~~~

ID Token after token exchange; claim contents are **illustrative only after signature verification**:

~~~json
{
  "iss": "https://broker.example.org",
  "sub": "pairwise-user-42",
  "aud": "portal-client",
  "exp": 1794001200,
  "iat": 1794000900,
  "nonce": "RANDOM_NONCE_FOR_THIS_LOGIN"
}
~~~

`exp/iat` values are illustrative; never treat this raw JSON as a real ID Token since it has no JWT header/signature. Nonce verification **only has meaning inside a verified ID Token**, not as a query parameter a browser can supply on its own and pretend is valid.

### Is Nonce Mandatory?

- In pure **OIDC Authorization Code Flow**, the `nonce` parameter is **optional per OIDC Core**. If sent, it must be processed and matched per spec.
- In other response types such as Implicit/Hybrid, OIDC specifies different nonce requirements; do not copy Code Flow assumptions blindly across response types.
- In modern security design, nonce is used where appropriate to bind the ID Token, mitigate replay, and complement RFC 9700 code injection defenses. However, **nonce alone does not replace PKCE or state** across all threat models.
- If Spring Security uses its own nonce mechanism, **never hardcode a static nonce, and never strip/alter nonce in a custom AuthorizationRequestResolver while skipping validator checks**.

### nonce vs. state

`state` is returned in the **authorization response (callback)** and checked by the client against the transaction. `nonce` is returned in an **ID Token claim** and verified by the client after ID Token validation. When an IdP/broker returns no ID Token, plain OAuth 2.0 has no concept of nonce functioning as ID Token binding.

### nonce Does Not Prove MFA

A matching nonce proves only that the ID Token corresponds to the request. It **does not** indicate whether the user completed MFA, authenticated recently, or holds permission for an action. For step-up requirements, inspect `auth_time`, `acr`, `amr`, and IdP policy per contract, alongside standard issuer, audience, and signature verification.

## 7. PKCE: Preventing Use of Intercepted or Injected Authorization Codes

**Proof Key for Code Exchange (PKCE)** is defined in RFC 7636 and reinforced in OAuth 2.0 Security Best Current Practice RFC 9700.

### 7.1 Generating code_verifier

For each authorization request, the client generates a high-entropy random string:

- `code_verifier`: **43–128 ASCII characters** from the unreserved set `A-Z a-z 0-9 - . _ ~`.
- Practical recommendation: generate **32 SecureRandom bytes**, Base64url-encoded without padding to **43 ASCII characters**.
- Never put the verifier in the authorization URL, browser public local storage, or logs. It needs to persist only for the **token exchange** of that transaction.

### 7.2 Generating the S256 code_challenge

~~~text
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

`code_challenge` can safely appear in the Authorization Request; it cannot feasibly be reversed back to the verifier when entropy is sufficient. With S256, the client keeps the verifier secret from the broker initially and sends it only in the token request.

### 7.3 Broker Verification of the Verifier

The broker records the challenge bound to the authorization code. Upon receiving the token endpoint POST with the verifier, the broker recomputes SHA-256/Base64url and compares it with the stored challenge. On mismatch, it **rejects the token exchange** (typically `invalid_grant` or equivalent error) and issues no tokens.

**PKCE cannot be "self-checked" by the client while skipping server enforcement.** The Authorization Server/broker must genuinely enforce the verifier at token exchange; an AS that ignores PKCE defeats the protection.

### 7.4 Choose S256, Never Downgrade to plain

`plain` means the challenge equals the verifier itself; that exposes the verifier via the authorization request, weakening protection under URL-observation threats. In modern Java/Spring, **use S256**. RFC 9700 requires AS support for PKCE; clients should choose the non-exposing method and never downgrade.

### 7.5 Public Clients vs. Confidential Clients

- **Public client:** SPAs or native apps that cannot protect a client secret. Per RFC 9700, **PKCE is required**.
- **Confidential client:** server-side apps capable of safeguarding a secret/private key. RFC 9700 **recommends PKCE** to prevent code injection/misuse; client authentication and PKCE **complement each other**.
- **BFF (Backend for Frontend):** the browser holds a session cookie while the backend acts as the OAuth/OIDC client holding tokens/secrets; PKCE should still be used for Code Flow when supported/required.
- **Never embed a confidential client's `client_secret` in a JavaScript bundle or URL**. If a secret has been embedded in the browser, treat the client as public regarding secret-keeping capability and redesign accordingly.

### 7.6 PKCE Does Not Replace Remaining Checks

PKCE does not verify:
- ID Token signature, `iss`, `aud`, `exp`, `nonce`;
- Resource permissions;
- Redirect URI policy;
- Validity of an upstream SAML Assertion;
- Identity mapping between the broker and the application.

An app with solid PKCE can still suffer login mix-up or accept an ID Token from the wrong issuer if those checks are omitted.

## 8. Boundary Matrix: Who Checks What

| Check | App OIDC Client | Broker OIDC OP/AS | Upstream SAML IdP |
| --- | --- | --- | --- |
| Generate app transaction `state` | **Yes** | Echoes state on callback | Not directly involved |
| Match callback `state` to browser request | **Yes** | Does not replace client | No |
| Generate app-side `nonce` | **Yes** | Echoes in ID Token | No |
| Verify nonce in validated ID Token | **Yes** | Issues ID Token for right request | No |
| Generate `PKCE code_verifier/challenge` | **Yes** | Stores challenge with code | No |
| Verify code_verifier at token endpoint | Does not replace AS; sends verifier | **Yes** | No |
| Issue authorization code | No | **Yes** | No |
| Validate ID Token JWS/JWKS/issuer/audience | **Yes** | Broker signs tokens | No |
| Validate SAMLResponse XML Signature/issuer/audience | No if OIDC client only | **Yes**, when acting as SP | IdP signs assertion |
| Manage upstream `RelayState/AuthnRequest ID` | No | **Yes** | Echoes/checks per SAML |
| Authorize app access per active account/tenant | **Yes** | May issue claims, does not replace business policy | Not SP authorization |
| Manage app SP HTTP session | **Yes** | Does not own | Does not own |

Common broker protocol-translation pitfall: **a valid upstream SAML response does not automatically become a valid OIDC ID Token for every client**. The broker must mint a token with its own `iss`, the right `aud=client_id`, signed by a broker key published via trusted JWKS, and with governed subject mapping.

## 9. Distinguishing OIDC state, nonce, PKCE, and SAML RelayState

An enterprise may see both parameter sets in a single browser trace:

~~~text
APP -> BROKER /authorize:
  state=state-app-123
  nonce=nonce-app-456
  code_challenge=challenge-app-789

BROKER -> SAML IDP:
  SAMLRequest=...
  RelayState=relay-broker-ABC

SAML IDP -> BROKER:
  SAMLResponse=...
  RelayState=relay-broker-ABC

BROKER -> APP:
  code=code-for-portal
  state=state-app-123

APP -> BROKER /token:
  code=code-for-portal
  code_verifier=private-app-verifier
~~~

The strings above **are illustrative placeholders only** and lack sufficient entropy for real use. Each transaction has its own:
- Separate TTL and state store;
- Separate creator and verifier;
- Separate signatures and trust keys;
- Separate response/callback endpoints;
- Separate browser/session bindings;
- Separate error and replay handling.

**Never forward upstream SAML `RelayState` as the `state` returned to the app** merely because both contain the word "state". The broker must maintain server-side correlation between the **downstream OIDC transaction** and the **upstream SAML transaction**, with separate app nonce and code.

### Two Issuer Layers

- The SAML assertion has `Issuer=https://idp.example.org/entity` and Audience equal to the broker SP entity ID.
- The OIDC ID Token has `iss=https://broker.example.org` and `aud=portal-client`.

If the application speaks only OIDC, it validates the **broker OIDC issuer**. Never use an ID Token signed by another upstream to establish a session if it does not match the registered issuer and client registration.

## 10. Configuring Spring Boot for OIDC Code Flow

### 10.1 Dependencies in a Servlet Project

In a Spring Boot 3.x project with plugins/BOM already configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a snippet inserted into an existing `build.gradle`, not a complete build file. When an application **also** needs to act directly as a SAML SP, add the SAML module separately and route filter chains according to architecture. You do not need `spring-security-saml2-service-provider` just for an app to act as an **OIDC client of a broker**.

### 10.2 application.yml: Confidential Backend Client

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker-provider
            client-id: "portal-client"
            client-secret: "${OIDC_BROKER_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          broker-provider:
            issuer-uri: "https://broker.example.org"
~~~

This is a **sample configuration**, unusable for real logins against illustrative domains. In deployment:
- Register the exact `client_id` and redirect URI with the broker.
- Supply the secret via a **runtime secret manager/environment**; never commit real secrets.
- `issuer-uri` points to the OIDC issuer that the client **already trusts and approved**, allowing Spring to discover OP metadata/JWKS.
- The broker must provide OIDC-compliant discovery and token endpoints. Never enter an upstream SAML entity ID as the OIDC issuer.
- The `openid` scope is the OIDC boundary; if only OAuth API scopes are requested without `openid`, an ID Token is not guaranteed.
- The example `redirect-uri` uses Spring's template; the public URL behind a reverse proxy must match the registration at the broker. If public traffic is HTTPS while the backend sees internal HTTP, configure forwarded headers **from trusted proxies only**.
- Maintain policies for clock skew, SameSite/Secure cookies, session state, and allowed redirect URLs.

**PKCE note:** depending on the Spring Security version and client type, PKCE is applied automatically for public clients or configured via `ClientRegistration.clientSettings.requireProofKey` / request customizer. **Do not assume `authorization-grant-type=authorization_code` guarantees PKCE is enabled across every version or confidential client.** Inspect the actual outbound request.

### 10.3 SecurityFilterChain: Standard OAuth2/OIDC Login

File `src/main/java/com/example/portal/OidcLoginSecurityConfig.java`:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

**This is a Spring configuration class**, not standalone Java with `main()`. It runs only inside a Spring Boot application with dependencies, client registration, and a live broker. Spring Security handles initiating the authorization request, receiving the callback, exchanging the code, and validating the OIDC ID Token per version. There is no fixed stdout.

With the `broker` registration, typical paths observed are:
- Login start: `GET /oauth2/authorization/broker`.
- Callback: `GET /login/oauth2/code/broker?code=...&state=...`.
- After login, the destination URL is determined by the success handler/RequestCache and application authorization.

**Never** write a custom controller catching the callback and marking the user authenticated merely because `code` is present. Never disable `oauth2Login` validation to accommodate a misconfigured broker.

## 11. Enabling PKCE for Confidential Clients in Spring Security 6.5+

If the app is a confidential server-side client and security policy mandates PKCE, **Spring Security 6.5+** provides `ClientRegistration.ClientSettings#requireProofKey`.

An alternative configuration replacing Boot auto-registration, using issuer discovery and credentials injected via Spring properties:

File `src/main/java/com/example/portal/OidcPkceClientConfig.java`:

~~~java
package com.example.portal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class OidcPkceClientConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${oidc.broker.issuer-uri}") String issuer,
            @Value("${oidc.broker.client-id}") String clientId,
            @Value("${oidc.broker.client-secret}") String clientSecret) {

        ClientRegistration registration =
                ClientRegistrations.fromOidcIssuerLocation(issuer)
                        .registrationId("broker")
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(
                                "{baseUrl}/login/oauth2/code/{registrationId}")
                        .scope("openid", "profile")
                        .clientSettings(
                                ClientRegistration.ClientSettings.builder()
                                        .requireProofKey(true)
                                        .build())
                        .build();

        return new InMemoryClientRegistrationRepository(registration);
    }
}
~~~

Corresponding properties **when using the Java bean instead of Boot auto-registration**:

~~~yaml
oidc:
  broker:
    issuer-uri: "https://broker.example.org"
    client-id: "portal-client"
    client-secret: "${OIDC_BROKER_CLIENT_SECRET}"
~~~

**Do not register this bean alongside another custom ClientRegistrationRepository with the same `registrationId`**. Choose one approach:
- Use Boot YAML auto-registration and version-appropriate customization;
- Or use the Java bean above, where `requireProofKey(true)` is set intentionally.

**Limitations and prerequisites:**
- `ClientRegistration.ClientSettings` is an API in Spring Security **6.5+**; if the project runs Spring Security 6.0–6.4, use the `DefaultOAuth2AuthorizationRequestResolver#setAuthorizationRequestCustomizer(OAuth2AuthorizationRequestCustomizers.withPkce())` extension per your version's docs, or upgrade to a compatible release. Never import APIs that do not exist yet.
- `ClientRegistrations.fromOidcIssuerLocation(issuer)` calls OIDC discovery; it requires a trusted broker, valid HTTPS/TLS, and connectivity at startup. Never let users control `issuer` via query parameters to avoid SSRF/mix-up.
- The broker must **support and enforce PKCE** when receiving `code_challenge` and `code_verifier`. If the provider errors, investigate broker configuration; never drop PKCE in a system where policy mandates it.
- The secret uses `client_secret_basic` for a confidential backend; PKCE **does not replace** client authentication.
- Ensure your customizer does not accidentally drop nonce/state; never hardcode static nonce or `code_challenge` values in URLs.
- This code is Spring configuration only and has no stdout; running it requires the SecurityFilterChain from section 10 and a live broker.

## 12. Where Does Spring Security Store the Authorization Request and state?

On the Servlet stack, the key components are:

| Component | Role |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Initiates redirect to the Authorization Endpoint |
| `DefaultOAuth2AuthorizationRequestResolver` | Builds the authorization request from `ClientRegistration` and customizations |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Stores the transaction from request initiation until callback |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Default repository storing the authorization request in `HttpSession` |
| `OAuth2LoginAuthenticationFilter` | Processes `/login/oauth2/code/*` callbacks |
| `OAuth2AuthorizedClientRepository/Service` | Stores authorized client/access tokens for API calls when needed |
| `OidcIdTokenDecoderFactory` | Validates ID Token signatures per client registration/algorithm |
| `SecurityContextRepository` | Manages persistence of the authenticated SecurityContext in the app |

**Distinguish clearly:**
- The Authorization Request Repository holds `state` and related attributes (including the verifier attribute for PKCE) **before login**.
- The Authorized Client Repository/Service stores `access token/refresh token` after grant per policy, **never replacing** the request repository.
- HttpSession/SecurityContext holds the app's post-login authentication and does not represent the broker's upstream SAML session.
- SavedRequest/RequestCache restores the URL requested before login; never mix return URLs into unvalidated state.

### When the Session Is Lost at Callback

The browser returns to the app with `code` and `state`, yet HttpSession is gone (SameSite cookie, wrong Domain/Path, expired session, or callback routed to another node). Spring cannot find the authorization request and rejects the callback **before token exchange**.

**Never fix this by disabling state checks**. Inspect the session cookie, reverse proxy, distributed Spring Session/sticky sessions, and SameSite. For OAuth2 Code Flow GET callbacks, `SameSite=Lax` works in many top-level navigations; however, for cross-site POST response_mode, iframes, or strict browser privacy policies, do not assume Lax always suffices.

### Multi-Tab

If two tabs start two logins close together in the same browser, the repository/session implementation may experience state overwrites or transaction races depending on version, customization, and browser timing. Test multi-tab behavior if UX permits it; never solve it with a single static global state or by matching state without checking the browser session.

## 13. The ID Token Must Be Fully Verified

After the token response, the client receives `id_token`. A JWT typically consists of three Base64url-encoded parts: `header.payload.signature`. **Decoding the payload does not mean the token is trustworthy**.

OIDC verification checklist:

| Field / Property | Verification |
| --- | --- |
| JWT signature / alg / key | Verify using JWKS/key bound to the **trusted broker issuer**; never accept `alg=none` arbitrarily |
| `iss` | Exact match to the expected OIDC issuer in client registration/discovery |
| `aud` | Must include the application's client ID |
| `azp` | Enforce per OIDC rules if multiple audiences exist or the claim is present |
| `exp` | Unexpired, with bounded clock skew |
| `iat` | Reasonable issued-at timestamp per policy and clock |
| `nonce` | If the client sent nonce, the ID Token claim must match |
| `auth_time` | If `max_age`/freshness is required, enforce the corresponding policy |
| `acr`, `amr` | Use only when an assurance/method contract exists and is verified |
| `sub` | Stable subject within the issuer/client scope; use `iss + sub` for mapping |
| `at_hash/c_hash` | Verify if required by response type and profile; do not mechanically apply Implicit/Hybrid rules to pure Code Flow |

Do not map `email=admin@example.org` to admin privileges. Emails can change or be recycled, and `email_verified` does not confirm tenant or role membership. The broker may map from a SAML NameID to its own pairwise `sub`; the app must perform **controlled identity linking**.

### An ID Token Is Not an Access Token

- `ID Token`: target audience is the **OIDC client**, conveying user authentication details.
- `Access Token`: grants access to a **resource server** per audience/scope/policy.
- `Refresh Token`: allows the client to request fresh tokens when issued; a high-value secret not granted in every Code Flow.
- `Authorization Code`: short-lived **single-use** value; never sent as an API Bearer token.

If an API accepts JWTs, configure a Resource Server to validate **issuer/audience/signature/scope** on access tokens. Never misuse an OIDC ID Token as an API bearer token.

## 14. Defending Against Authorization-Server Mix-Up in Multi-Broker Environments

An application has two registrations:

~~~text
registrationId=broker-east
issuer=https://broker-east.example.org

registrationId=broker-west
issuer=https://broker-west.example.org
~~~

An attacker may try tricking the client into treating one broker's authorization response as coming from the other, causing **authorization server mix-up** or code leakage. Defenses require:
1. Storing the **expected registration/issuer** in transaction state, never picking the issuer from an unverified callback query parameter.
2. Binding the authorization response to the right request, client ID, and redirect URI.
3. When supported, checking the `iss` parameter in the Authorization Response per **RFC 9207**.
4. Where response issuer identification is unsupported, using anti-mix-up mitigations from RFC 9700 such as **distinct redirect URIs per Authorization Server**, alongside proper bindings.
5. Verifying OIDC ID Token issuer and audience **after token exchange**, while recognizing that alone does not prevent all pre-exchange code leakage.
6. Using a fixed issuer allowlist/trusted discovery, never constructing token endpoints from browser-supplied URLs.

**A matching state alone is insufficient** if the client loses track of which registration/AS the state belongs to or processes the callback against the wrong issuer.

## 15. Open Redirect Risk at Return-to URLs

After successful login, an application often wants to return to a deep link such as `/invoices/42`. Using a query parameter like:

~~~text
/login?returnUrl=https://attacker.example.org/phishing
~~~

and embedding it directly in `state` or a success handler for post-OIDC redirect lets an attacker execute an **open redirect** on a trusted domain.

Safe design:
- Store **`SavedRequest`** or a normalized internal path server-side before login.
- If using an opaque state handle, store only a lookup key and session binding.
- Redirect only to approved internal routes or fixed allowlisted origins, rejecting `//`-prefixed URLs, `javascript:` schemes, encoded double slashes, backslashes, and host spoofing.
- Trust `Forwarded / X-Forwarded-Host` only from trusted reverse proxies.
- Never use `Referer` or arbitrary `post_logout_redirect_uri` values as post-login destinations.
- Resource authorization is still enforced even when the destination is valid.

A URI inside `state` **must not be trusted automatically** just because the broker echoed `state`. Callback parameters arrive via the browser; the app must reconcile `state` against the server's saved record.

## 16. Securing Redirect URIs, HTTPS, and Callbacks

The **Redirect URI** is where the browser delivers the code back to the client. Key rules:
- Use HTTPS on a public domain in production; loopback exceptions apply only to native apps/local dev per spec.
- Register exact redirect URIs at the broker; avoid wildcards and disallow arbitrary changes to scheme/host/path or intermediate redirects.
- Spring receives OAuth2 Login callbacks at `/login/oauth2/code/{registrationId}` by default. If customizing `.redirectionEndpoint().baseUri(... )`, update the registered redirect URI/client config to match.
- Behind a reverse proxy, scheme/host must reflect the real public URL; never let the backend construct `http://internal:8080`.
- Apply state + transaction binding, PKCE, and AS mix-up defenses.
- Never cache callback codes; avoid logging query strings containing `code` in access logs/analytics, prevent Referrer leakage (`Referrer-Policy`), and never leak to other domains.
- Never pass codes, nonces, verifiers, refresh tokens, or ID Tokens to the frontend just to "debug".
- If a callback is replayed after the code was exchanged, the token endpoint should fail; the app must never reuse the transaction.

**Unlike SAML ACS:** OIDC Code Flow defaults to a **GET callback** with code/state, whereas SAML HTTP-POST profile uses a **POST ACS** with `SAMLResponse`. Configure SameSite/cookies/CSRF based on the **actual flow**, never copying cookie settings blindly between the two protocols without testing.

## 17. Standalone Java 17: Verifying RFC 7636 S256 and Generating Random Tokens

This program uses **only the Java Standard Library**, with no Spring. It:
1. Computes the S256 challenge from the official RFC 7636 example `code_verifier`.
2. Proves the challenge matches the test vector.
3. Generates a 32-byte verifier via `SecureRandom`, verifying unpadded Base64url length of 43 characters.
4. Demonstrates **distinct** random `state` and `nonce` values.
5. Does not print random tokens or secrets.

File `PkceAndOidcStateDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceAndOidcStateDemo {

    private static final SecureRandom RANDOM = new SecureRandom();

    static String randomBase64Url(int bytes) {
        byte[] value = new byte[bytes];
        RANDOM.nextBytes(value);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value);
    }

    static String challengeS256(String verifier) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hash);
    }

    public static void main(String[] args) throws Exception {
        String verifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String expected =
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

        System.out.println("RFC 7636 S256 matches: "
                + challengeS256(verifier).equals(expected));

        String freshVerifier = randomBase64Url(32);
        String state = randomBase64Url(18);
        String nonce = randomBase64Url(18);

        System.out.println("Verifier chars: " + freshVerifier.length());
        System.out.println("Verifier URL-safe: "
                + freshVerifier.matches("[A-Za-z0-9_-]{43}"));
        System.out.println("state bytes-ascii: "
                + state.getBytes(StandardCharsets.US_ASCII).length);
        System.out.println("nonce bytes-ascii: "
                + nonce.getBytes(StandardCharsets.US_ASCII).length);
        System.out.println("state and nonce differ: "
                + !state.equals(nonce));
    }
}
~~~

Compile and run:

~~~bash
javac PkceAndOidcStateDemo.java
java PkceAndOidcStateDemo
~~~

Expected stdout from program logic (fixed lengths; random values are not printed):

~~~text
RFC 7636 S256 matches: true
Verifier chars: 43
Verifier URL-safe: true
state bytes-ascii: 24
nonce bytes-ascii: 24
state and nonce differ: true
~~~

`state and nonce differ` holds with overwhelming probability when using independent 18-byte random draws; theoretically two random draws **still have a negligible collision probability**. Therefore, if **strictly deterministic** stdout is required, code should check and regenerate on collision. This demo illustrates randomness; production unit tests should never depend on random events "never colliding".

**This is not a complete OIDC client**: it creates no HTTP authorization request, handles no callback, verifies no JWT/JWKS, and uses no real OIDC keys. `challengeS256` demonstrates standard PKCE; real PKCE verification happens at the **broker's token endpoint**. In a Spring app, rely on framework libraries to generate/store verifiers rather than writing global static randoms or storing verifiers in JS-readable cookies.

## 18. Why Must Codes Be Bound to a Specific Transaction?

An application-managed server-side state entry might look like:

~~~text
transactionId: tx-opaque-001
browserBinding: session-backed-correlation
registrationId: broker
expectedIssuer: https://broker.example.org
stateHash: SHA-256(opaque-state)
nonceHashOrValue: tied-to-this-authorization-request
pkceVerifier: secret, only for token exchange
startedAt: UTC timestamp
expiresAt: short TTL
originalDestination: /reports/42
consumed: false
~~~

This is an **architectural model**, not Spring Security's internal session key format. In real implementations, avoid duplicating state/nonce/verifier when the framework repository already persists them properly; never rely on undocumented internal key names or private attributes.

Rules:
- One browser may have multiple transactions (multiple tabs); if allowed, each transaction needs its **own** state/nonce/verifier.
- State binds to the **exact client/issuer/registration and browser**.
- Nonce binds to the **ID Token of the initiated transaction**.
- Verifier binds to the **authorization code issued by the broker**.
- Short TTL; consume atomically to block repeated/replayed callbacks.
- After login or failure, delete single-use state and clean up sensitive tokens.
- If the session is lost, fail closed and require starting a fresh login; never accept a query `state` as a self-sufficient global cache key to log in.

## 19. What If the App Is Both a SAML SP and an OIDC Client?

A migration may temporarily run both paths:
- `/saml2/authenticate/corp` → direct upstream SAML login.
- `/oauth2/authorization/broker` → OIDC login via broker.

The two paths use different filters:
- SAML: `Saml2WebSsoAuthenticationRequestFilter` and `Saml2WebSsoAuthenticationFilter`.
- OIDC: `OAuth2AuthorizationRequestRedirectFilter` and `OAuth2LoginAuthenticationFilter`.

**Never mix repositories:**
- SAML AuthnRequest/RelayState state is not OIDC AuthorizationRequest/state.
- SAML ACS `/login/saml2/sso/{registrationId}` differs from OIDC callback `/login/oauth2/code/{registrationId}`.
- SAML verification uses the IdP X.509 certificate/trust from metadata; OIDC verification uses OP issuer/JWKS/ClientRegistration.
- SAML `NameID` does not automatically equal OIDC `sub`.
- SAML `SessionIndex` is not an OIDC session cookie.
- OIDC `state/nonce/PKCE` does not validate an unverified SAML Assertion.

When supporting both mechanisms concurrently, explicitly define **login precedence, principal mapping, logout semantics, request matchers, and tenant/account authorization**. Never let a user arriving via a lower-assurance login path receive authorities of a stronger login path without verification.

## 20. Identity Broker: Never "Launder" Trust

When a broker receives a SAML assertion with:
- `Issuer` equal to the upstream IdP;
- `Audience` equal to the broker SAML SP entity ID;
- `Subject NameID` that may be transient or persistent;
- `AuthnContext`, `AuthnInstant`, and group attributes carrying their own semantics.

The broker mints its own OIDC ID Token:
- `iss` is the broker issuer;
- `sub` is the broker-issued subject for the app;
- `aud` is the OIDC client ID;
- `acr/amr/auth_time` when the broker has an accurate contract and supporting evidence;
- Groups/permissions mapped according to broker policy.

**Four principles:**

1. The broker must verify the **upstream SAML response** against metadata/trust and constraints, not merely read NameID.
2. The broker must not turn an unnormalized/unapproved `group=admins` string into application admin privileges.
3. The app must validate the **broker ID Token** against expected issuer and audience while enforcing app authorization; never blindly trust upstream-supplied email/name.
4. To preserve assurance, the broker must map `SAML AuthnContext → OIDC acr/amr/auth_time` under an **explicit, verified contract**. Never treat the presence of PKCE as proof that the user completed MFA.

### Subject Mapping

OIDC `sub` can be issued **pairwise** per client/sector. One user may have different `sub` values across two applications even when logging into the same IdP. Identify accounts using `(issuer, subject)` and governed internal mapping. Never build a global user key from an empty/unverified email or a transient NameID that changes every session.

## 21. Upstream IdP Mix-Up and Multi-Tenancy

A broker accepts SAML from multiple IdPs. When a downstream client initiates "Login via Broker", the broker may let the user pick an IdP:
- The broker must preserve an exact link between the OIDC transaction and the SAML AuthnRequest.
- The upstream SAML Assertion must be verified only against the **exact IdP registration**, issuer, audience, and keys.
- The Spring client should accept only its configured broker issuer, never trusting a new issuer merely because login originated from an upstream IdP.
- Claims like tenant, group, and business role must be mapped by the broker per policy; the app retains internal tenant checks.
- If IdP A and IdP B both assert `alice@example.org`, never auto-merge the two accounts without a verified account-linking workflow.
- If a broker changes issuer/`sub` semantics during realm/tenant migration, plan identity migration and test thoroughly to prevent user takeover.

This risk differs from client-side **authorization server mix-up**, yet both require pinning issuer/transaction **at the right layer**.

## 22. CSRF, SameSite, and Session Cookies on the OIDC Callback

Spring Security uses the session in many OAuth2 Login configurations to store the authorization request. A cross-site GET callback from the broker back to the app can often carry a `SameSite=Lax` cookie on top-level safe navigation, however:
- `response_mode=form_post` callbacks are cross-site POSTs with different cookie rules.
- Browser privacy, iframes, or third-party cookie restrictions can block cookies.
- `SameSite=None; Secure` may be needed in certain architectures, but requires full CSRF evaluation.
- HTTPS proxies/offloading can break cookie Secure/Domain/Path flags and redirect URIs.
- With session replication, callbacks may land on a different node; the state repository must remain accessible.
- Browser login flows may span tabs or encounter interrupted redirect chains.

**CSRF on HTTP POST business APIs** still requires dedicated protection. Never interpret "we have OIDC state" as meaning every application POST is automatically CSRF-safe. `state` protects the **authorization callback**, whereas Spring CSRF tokens/SameSite/Origin checks protect application state-changing actions.

## 23. Common Errors and Reading the Right Layer

| Symptom | Likely Source | What to Check |
| --- | --- | --- |
| Callback arrives with `code` but reports invalid state | Lost/mismatched transaction, cookie, multi-tab, CSRF | Session repository, original state, browser binding |
| Callback missing `state` | Broker/response mode, wrong URL, modified query | Authorization Request and allowed callbacks |
| Broker returns `error=access_denied` | User declined consent or AS policy | Authorization response; do not call token endpoint |
| `invalid_grant` at token endpoint | Expired/reused code, wrong verifier, redirect URI mismatch | Token request and PKCE enforcement; never retry a used code |
| `invalid_client` | Missing/wrong client auth | Client ID/secret, auth method, broker registration |
| Missing `code_challenge` | PKCE not enabled for version/client type | ClientSettings/customizer, outgoing URL |
| Challenge sent yet broker ignores verifier | AS not enforcing PKCE properly | Broker config/conformance; do not assume PKCE protected you |
| ID Token `nonce` mismatch | Swapped transaction / wrong ID Token | ID Token validator, nonce repository, transaction binding |
| Invalid ID Token signature | JWKS/key rotation, wrong issuer/trust, tampered token | Broker discovery/JWKS, alg allowlist |
| Wrong ID Token `iss` | Mix-up/multi-tenant/issuer config | Expected issuer, not callback input |
| ID Token `aud` omits client ID | Token issued for another client | ClientRegistration and ID Token verification |
| `invalid redirect_uri` | Wrong public domain/proxy/registration | Exact redirect URI, forwarded headers |
| HTTP 302 loop | Session cookie not saved, login/authorization policy | Browser session, filter chain, SameSite |
| Broker SSO succeeds yet app lands on wrong user | Account linking/sub/email mismatch | `iss+sub` mapping, tenant, immutable identity |
| Broker SAML login reports invalid signature | Upstream SAML failure, **not PKCE** | SAML metadata/trust and broker ACS |
| App login succeeds yet API returns 403 | Insufficient authorization/scope/audience | Business permissions/resource server; do not drop OIDC checks |
| User logs out of app then immediately SSOs back in | Broker/IdP session still alive | OIDC logout/IdP SLO per contract |
| Repeated GET callback errors out | One-time code/state already consumed | Usually fail-safe behavior; never reuse token transactions |

**Never fix errors by** disabling state checks, skipping nonce validation, downgrading PKCE S256 to plain, accepting unsigned ID Tokens, trusting arbitrary unverified JWKS, or allowing wildcard redirect URIs.

## 24. Safe Callback Processing Mental Model

To understand what the framework performs, use the pseudocode below as an **architectural checklist**—do not copy it into a controller to replace Spring Security:

~~~text
on GET /login/oauth2/code/broker:
  if callback contains error:
      classify authorized error and fail safely
  transaction = authorizationRequestRepository.loadFromBrowserSession()
  require transaction exists, not expired, correct client/issuer
  require callback.state == transaction.state
  require appropriate AS mix-up protection
  exchange code once via broker /token:
      authenticate client if confidential
      send matching redirect_uri and PKCE code_verifier
  validate ID Token:
      signature, trusted issuer, audience/client_id, time, nonce
  resolve (iss, sub) into local account
  check tenant/account status and local authorization
  create application Authentication/HTTP session
  consume transaction; redirect to approved SavedRequest
~~~

**Do not assume this is the exact internal order across every Spring Security version**; it is a map of responsibilities, and providers/frameworks order verification steps appropriately. The security principle is that receiving a callback **never equates directly to an authenticated user**.

## 25. Minimum Integration Test Suite

### Test A — Code Flow Happy Path

1. Clear test app session and open `/reports/42`.
2. Browser redirects to `/oauth2/authorization/broker`.
3. Inspect authorization URL for `response_type=code`, `scope=openid`, right `client_id/redirect_uri`, state, and PKCE challenge if policy enables it.
4. If the client sends nonce, verify nonce differs across two independent logins; verifier never appears in the URL.
5. Authenticate successfully via the test broker/IdP.
6. Callback hits `/login/oauth2/code/broker` with code + matching state.
7. Backend exchanges code over HTTPS with verifier and client auth.
8. Spring verifies ID Token, creates session, and returns to the deep link.
9. Access the route per account authorization and observe the active login session.

### Test B — state Mismatch

- Start login A and alter the callback state to another value in the lab.
- Expect the client to reject/create no new session and never redeem an injected code.
- Never disable state checking to make the test pass.

### Test C — nonce Mismatch

- Have a test OIDC OP issue an ID Token with a different nonce than the request.
- Expect provider validation to reject if nonce was sent/checked per contract.
- Distinguish from callback state mismatch: two different verification moments.

### Test D — Wrong PKCE code_verifier

- Start a request with an S256 code challenge, and at token request supply another transaction's verifier.
- The broker must reject the token exchange.
- Do not expect the client to "fix itself" by dropping PKCE.

### Test E — Code Replay

- Exchange an authorization code once, then try reusing it in the lab.
- Expect `invalid_grant` or policy error, with no new tokens issued.
- One-time state consumption is also tested independently.

### Test F — Issuer Mix-Up

- Configure two OP registrations; simulate broker A's callback arriving at B's URI/transaction.
- Expect no code sent to the wrong issuer's token endpoint and no session created.
- Verify RFC 9207 `iss` response or separate redirect URIs per design.

### Test G — Lost Session Cookie

- Send a valid callback from a browser lacking the session that started the flow.
- Expect the state repository to miss the request and reject.
- Fix SameSite/Domain/Path/multi-node state rather than removing state validation.

### Test H — Invalid Broker Upstream SAML

- Broker receives a SAMLResponse with an invalid signature/issuer from a test IdP.
- Broker rejects upstream SAML and issues no valid authorization code to the app.
- The application never ingests SAML XML directly and creates no SecurityContext.

### Test I — Malicious Return URL

- Supply `https://evil.example.org` in a return-to/state query if the endpoint accepts input.
- Must never redirect to that host after login; allow only approved local destinations.

### Test J — Multi-Tab

- Start login in two tabs, each with its own state/nonce/verifier.
- Complete them in reverse order.
- Depending on whether the repository supports concurrent transactions, flows must succeed accurately or reject safely; never accept another tab's token merely due to a shared session.

## 26. Special Broker Security Considerations

### 26.1 Broker Does Not Permanently Sync User Permissions

A broker may emit group/role claims based on upstream SAML attributes at login time. Apps relying on those claims risk stale privileges if a user is revoked after login. Sensitive operations require live app authorization or revocation checks. Nonce and PKCE **do not solve** permission updates.

### 26.2 Logging In via One IdP Does Not Make Other IdPs Trusted

A multi-IdP broker may use a single OIDC issuer yet front many upstream IdPs. Apps need provenance/tenant mapping when policies distinguish assurance levels across upstream providers. Never merge accounts solely by email and allow a weak IdP to grant a strong IdP's permissions.

### 26.3 Authorization Code Is Never Sent to the Upstream SAML IdP

The code issued by the broker AS is **for the OIDC client** and redeemed at the **broker token endpoint**, not part of `SAMLResponse` or upstream RelayState. When the broker correlates SAML and OIDC context, it keeps that mapping in server-side broker state.

### 26.4 Client Secret, Nonce, and Verifier Have Different Sensitivity Levels

- `client_secret`: long-lived secret of a confidential client; keep on backend/secret manager.
- `code_verifier`: short-lived per-transaction secret; never expose to browser/logs, discard after use.
- `state/nonce`: random transaction-correlation values; sent via front-channel so **not considered absolute secrets**.
- `authorization code`: short-lived credential passing through the browser; keep out of logs, Referrer, and analytics.
- `ID Token/access token/refresh token`: sensitive tokens; control storage, transport, and scope of use.

### 26.5 CORS Does Not Replace OAuth/OIDC Security

Standard browser login relies on **HTTP redirects/navigation**, not exclusively XMLHttpRequest calls. CORS cannot replace state, PKCE, issuer/audience/nonce, session binding, or Redirect URI policies. If an SPA calls the token endpoint via fetch, CORS may be needed per provider, while PKCE and the public browser client threat model remain mandatory.

## 27. Comparing OIDC and SAML at the Application Boundary

| Aspect | OIDC Code Flow Between App–Broker | SAML Web SSO Between Broker–IdP |
| --- | --- | --- |
| Initial request | OAuth2/OIDC Authorization Request | SAML AuthnRequest |
| Browser context | `state`, session-bound OAuth2AuthorizationRequest | `RelayState`, AuthnRequest repository |
| ID Token binding | `nonce` | No OIDC nonce; uses SAML request ID, InResponseTo/SubjectConfirmation |
| Code interception defense | PKCE `code_challenge/code_verifier` | No authorization code to exchange; uses XML Signature/conditions |
| Authentication evidence | JWT ID Token from broker | XML SAML Assertion from IdP |
| Verifier | App OIDC client | Broker acting as SAML SP |
| Partner identity | OIDC issuer URI + client registration | IdP SAML entity ID + SP entity ID |
| Signature | JWS/JWKS ID Token; optional token binding | XML Signature/binding signature |
| Callback | `/login/oauth2/code/{registrationId}` | SAML ACS at broker |
| App session | Spring Security OIDC Authentication/session | Broker holds SAML session/upstream correlation |
| Logout | OIDC RP-initiated/back-channel per OP support | SAML Single Logout per IdP/SP profile |
| Permission updates | App policy/claims mapping + revocation | Broker maps upstream attributes per contract |

Never try building an ad-hoc filter that turns SAML XML into a JWT via Base64 decoding and arbitrary signing; an **identity broker** must enforce trust at both boundaries with audited account mapping and claim policies.

## 28. Production Deployment Checklist

- [ ] OIDC client knows the exact broker issuer, client ID, redirect URI, allowed JWS algorithms/JWKS, and trusted OIDC discovery.
- [ ] Uses Authorization Code with `scope=openid` for OIDC; never uses Implicit Flow just to avoid a backend.
- [ ] Authorization Request generates a fresh, unpredictable `state` bound to browser/session with TTL and one-time consumption.
- [ ] When using `nonce`, the client generates a fresh value per transaction and validates the claim inside the signed ID Token.
- [ ] PKCE `S256` works end-to-end at both authorization and token endpoints; mandatory for public clients, recommended for confidential clients.
- [ ] `code_verifier` never appears in authorization URLs, browser logs, or a confidential app's client bundle.
- [ ] Authorization Server enforces the verifier, single-use code, client ID, and redirect URI.
- [ ] Callback creates `Authentication` only after token exchange and ID Token validation.
- [ ] Uses `iss + sub` and verified tenant/account mapping; never trusts arbitrary provider email/roles.
- [ ] Enforces anti-mix-up defenses across multiple OPs/brokers; never selects the token endpoint from callback input.
- [ ] If the app uses an upstream SAML broker, the broker independently verifies SAML signature/issuer/audience/time/InResponseTo.
- [ ] Never reuses OIDC state/nonce/code_verifier as upstream SAML RelayState.
- [ ] Return URLs are approved local routes, SavedRequest, or opaque server-side handles; no open redirects.
- [ ] Session cookies, SameSite/Secure/Path, multi-node stores, and reverse-proxy public origins are tested.
- [ ] Client secrets, access/refresh tokens, verifiers, codes, and ID Tokens are never logged or exported in shared HARs.
- [ ] Negative tests cover state/nonce/PKCE mismatch, expired codes, wrong issuer/audience, lost sessions, and multiple tabs.
- [ ] Application authorization still verifies current permissions instead of treating an ID Token as access to all resources.
- [ ] Upgrade Spring Security/OpenSAML/OAuth2 stacks via the BOM; never apply 6.5 APIs to older projects without checking.

## 29. Review Questions with Answers

**Q1.** The authorization callback returns `code` yet `state` differs from the stored request. Should the client exchange the code to see who the user is before deciding?

**Answer:** No. Reject the callback before creating a login; state is a correlation/CSRF control, and token exchange must never be used to "work around" a mismatch.

**Q2.** `nonce` is sent to the Authorization Endpoint; where must it appear for the client to verify it?

**Answer:** In the `nonce` claim of the **ID Token** from the broker if the client sent nonce; the client compares the value after verifying the token signature, issuer, and audience.

**Q3.** How is the S256 `code_challenge` computed?

**Answer:** `BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))`. The random verifier is 43–128 characters, preferably using at least 32 bytes of entropy encoded as Base64url.

**Q4.** Does PKCE make an ID Token with the wrong issuer trustworthy?

**Answer:** No. PKCE protects authorization code exchange; it does not replace ID Token validation.

**Q5.** A confidential client keeps `client_secret` on the server. Is PKCE still useful?

**Answer:** PKCE is still recommended by RFC 9700 to guard against code injection/misuse; client auth and PKCE complement rather than replace each other.

**Q6.** The browser sees SAML RelayState from the IdP and OIDC state from the broker. Should the same string be reused for both?

**Answer:** No. They belong to two independent transactions and trust boundaries. The broker maintains server-side mapping if needed.

**Q7.** An upstream IdP issues a SAML Assertion whose Audience is the broker. Can the app use that Assertion directly as OIDC login proof?

**Answer:** No. The broker must validate SAML first and mint an ID Token from the **broker issuer** with Audience equal to the app client ID, which the app then validates.

**Q8.** Can `returnUrl=https://evil.example.org` be stored in `state` and redirected to after login?

**Answer:** Unsafe. Use an opaque state plus a server-side allowlisted target to prevent open redirects.

**Q9.** A callback returns the right `state` yet no `HttpSession` remains. Should we look up global state and create `Authentication` to preserve UX?

**Answer:** No, unless trusted browser/session binding exists. Fix session/cookie/repository handling and fail closed when the transaction cannot be verified.

**Q10.** The browser completed SAML login at the upstream IdP yet the app never received a code. Where should you investigate?

**Answer:** Check broker SAML ACS/validation, the broker OIDC authorization transaction, redirect URI, and browser/proxy. Upstream SAML success does not guarantee a downstream code was issued.

**Q11.** Is `email_verified=true` enough to map all accounts sharing the same email across two IdPs?

**Answer:** No. Require issuer, subject, tenant, account linking, and a verified policy.

**Q12.** Callback state and PKCE succeed, yet the app returns 403 after login. Does that prove OAuth/OIDC is broken?

**Answer:** No. Once `Authentication` is created, a 403 may come from application authorization/business policy; inspect current permissions.

**Q13.** On Spring Security 6.2, can you import `ClientRegistration.ClientSettings` as in 6.5 code?

**Answer:** Not out of the box; this API was introduced in 6.5. Use a version-appropriate request customizer or upgrade dependencies with testing.

**Q14.** Can `code_verifier`, client secret, ID Token, and access token be printed to logs for debugging?

**Answer:** No. Log only error codes, registration ID, redacted request correlation IDs, and per-step status—never leak credentials or tokens.

**Q15.** Why does the app verify the ID Token using the broker's issuer instead of the upstream IdP's SAML issuer?

**Answer:** The app receives an **OIDC token issued by the broker**, which is the OpenID Provider the app registered and trusts. The upstream IdP was verified by the broker in a separate SAML transaction.

## 30. Summary

An **Authorization Code** is a short-lived credential issued by the broker to the client, redeemable only at the token endpoint per policy. **state** binds the authorization callback to the initiating request/browser; **nonce** binds the ID Token to the authentication transaction when sent; and **PKCE S256** forces the party redeeming the code to prove possession of the verifier matching the initial challenge.

In a brokered federation, **each protocol has its own trust boundary**: the Spring Security app enforces OIDC state/nonce/PKCE/ID Token checks toward the broker, while the broker enforces upstream SAML RelayState/AuthnRequest and signature/conditions checks. These controls **complement** rather than replace one another. Success on one hop never automatically grants authorization or guarantees the other hop is valid.

### Standards and Spring Security Documentation

1. RFC 6749 — OAuth 2.0 Authorization Code Grant: https://www.rfc-editor.org/rfc/rfc6749.html
2. RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients, code_verifier/S256 and test vectors: https://www.rfc-editor.org/rfc/rfc7636.html
3. RFC 9700 — Best Current Practice for OAuth 2.0 Security, PKCE/state/nonce/mix-up: https://www.rfc-editor.org/rfc/rfc9700.html
4. RFC 9207 — Authorization Server Issuer Identification: https://www.rfc-editor.org/rfc/rfc9207.html
5. OpenID Connect Core 1.0, Authorization Code Flow, state, nonce, ID Token validation: https://openid.net/specs/openid-connect-core-1_0.html
6. RFC 10017 — OAuth 2.0 for Browser-Based Applications, browser/BFF architecture and PKCE: https://www.rfc-editor.org/rfc/rfc10017.html
7. Spring Security — OAuth 2.0 Login Core Configuration, ClientRegistration, callback: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
8. Spring Security — OAuth 2.0 Login Advanced Configuration, authorizationRequestRepository, redirect endpoint, and ID Token validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
9. Spring Security — OAuth 2.0 Client Authorization Grants, PKCE/HttpSessionOAuth2AuthorizationRequestRepository: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
10. Spring Security 6.5 API — ClientRegistration.ClientSettings.Builder.requireProofKey: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/registration/ClientRegistration.ClientSettings.Builder.html
11. Spring Security — SAML 2.0 Login Overview, upstream reference: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
