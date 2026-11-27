# 11.8. Matching nonce Against the Original Authorization Request

## 1. Why Does an ID Token with a Valid Signature Still Need a nonce Check?

When a **Spring Security OAuth 2.0 OIDC Client** application authenticates users via OpenID Connect (OIDC), the identity provider (*OpenID Provider*, OP) can issue a digitally signed **ID Token**. The client can verify the token's signature, issuer, audience, and expiration to confirm the token was issued by the right provider for the application.

However, consider this scenario:

- A user starts a new login from the browser.
- There is an ID Token issued during an **older transaction** that has not yet expired.
- If the client relies solely on the signature and static claims, the old token can look completely valid.
- The client needs to bind the received ID Token to **the specific authorization request just initiated**, rather than only to an issuer/client in general.

This is the role of **`nonce`** (*number used once*): an unpredictable value placed by the OIDC client in the authentication request; when issuing the ID Token, the OP places the corresponding value into the `nonce` claim. The client matches it against the context stored when the transaction started.

**Core point:** the signature answers "who issued this ID Token and was it tampered with?"; the nonce answers "was this ID Token issued for **the authentication request currently being processed**?" The two questions complement each other.

In practice, never treat nonce as the sole security mechanism. It must work alongside `state`, Authorization Code + PKCE, ID Token validation, HTTPS, and proper session management.

## 2. What Is a Nonce in OpenID Connect?

### 2.1. Nonce Appears on Both Sides of the Transaction

An OIDC client authorization request might contain:

~~~http
GET /authorize?response_type=code
    &client_id=portal-web
    &scope=openid%20profile
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
    &state=STATE_RANDOM_VALUE
    &nonce=NONCE_RANDOM_VALUE
    &code_challenge=PKCE_CHALLENGE
    &code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

The request above is wrapped across lines for illustration; real URLs must be properly encoded. The client stores the nonce value or enough data to recover the value **actually sent** to the OP.

After exchanging the authorization code, the token endpoint returns an OIDC response containing `id_token`. The decoded ID Token payload might contain:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "subject-3c91",
  "aud": "portal-web",
  "exp": 1925003600,
  "iat": 1925000000,
  "nonce": "NONCE_RANDOM_VALUE"
}
~~~

**The client may accept the `nonce` claim only after the token has been processed/verified per OIDC requirements**; Base64URL-decoding the payload is not a security check.

### 2.2. Matching Condition

Verification logic:

~~~text
Initial authorization request:
  nonce sent to OP = "N-ABC"
  state sent to OP = "S-123"
  registration = "company"

Callback and token exchange:
  returned state = "S-123"
  verified ID Token has nonce = "N-ABC"

=> Nonce matches the transaction just initiated.
~~~

Conversely:

~~~text
Initial authorization request:
  nonce = "N-ABC"

Received ID Token:
  nonce = "N-OLD"

=> Mismatch. Reject OIDC authentication for this transaction.
~~~

If the client sent a nonce in the request, it **must verify** the matching `nonce` claim in the ID Token. An ID Token missing a nonce or carrying a different nonce must not be accepted in that transaction.

### 2.3. Is Nonce Mandatory in Every OIDC Flow?

OIDC Core defines nonce usage by **response type/flow**:

| Flow | Role of nonce |
| --- | --- |
| **Authorization Code flow** (`response_type=code`) | The `nonce` parameter is **optional per OIDC Core**; if the client sends it, it must verify the corresponding claim in the ID Token |
| **Implicit flow** (ID Token returned via front channel) | Nonce is a required component per that flow's rules to bind the ID Token |
| **Hybrid flow** | Specific requirements depend on the response type and whether the ID Token is returned on the front channel or token endpoint |

This lesson focuses on **Spring Security Servlet OIDC Login with the Authorization Code flow**, typically combined with PKCE. Even though `nonce` is not mandatory for every Authorization Code request by the spec, using nonce is a helpful extra layer of defense; whenever it is used, **the verification step must never be skipped**.

Do not take Implicit/Hybrid rules and claim all Authorization Code requests lacking a nonce are invalid. Conversely, do not use the fact that nonce is optional in the Code flow as an excuse to skip verifying a nonce that was sent.

## 3. Distinguishing nonce, state, PKCE, and Authorization Code

These values often appear together in a single login transaction, yet protect different boundaries.

| Value | Where Created/Sent? | Where Checked? | Purpose |
| --- | --- | --- | --- |
| `state` | Client sends in authorization request; OP returns in authorization response | Client handling callback | Binds callback to the prior request; helps prevent authorization response/login CSRF |
| `nonce` | Client sends in OIDC authorization request; OP echoes in **ID Token** | OIDC client after receiving ID Token | Binds the ID Token to **a specific authentication request**; prevents certain replay attacks |
| `code_verifier` / `code_challenge` (PKCE) | Client retains verifier, sends challenge on authorize | Token endpoint verifies verifier when exchanging code | Binds the authorization code to the party that initiated PKCE |
| Authorization code | OP returns to browser on successful callback | Token endpoint receives code via backend | Exchanged for tokens; short-lived and single-use |
| Client session cookie | Browser sends to application | Servlet/session infrastructure | Locates user context and pending authorization request |

### 3.1. Three Correlations, Three Questions

~~~text
state:
  "Is this callback the response to the saved authorization request?"

PKCE:
  "Does the party exchanging the authorization code hold the matching code_verifier?"

nonce:
  "Does this ID Token correspond to that OIDC authentication request?"
~~~

**Do not swap their purposes:** `state` does not replace nonce; nonce does not replace `state` matching; PKCE does not replace verifying the ID Token's signature, issuer, and audience.

### 3.2. Do Not Reuse the Same String for All Parameters

By design, generate independent random values for state, nonce, and PKCE verifier, managed by the framework or a trusted security library. Never use a fixed string like `nonce=login`, a timestamp, an email, or a user ID. Predictable values do not provide reliable transaction binding.

### 3.3. Nonce Is Not an Access Token or Session ID

Nonce **does not grant API access**, does not prove a user holds any role, and is not a session key used to access user data. A nonce may appear in the authorization URL sent through the browser; never pack application secrets, personal data, or sensitive claims into it.

## 4. End-to-End Flow: Save Nonce Before Redirect, Verify After Token Exchange

An OIDC Servlet application must maintain the link between the **pre-redirect request** and the **post-callback ID Token**:

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Boot Servlet OIDC Client
    participant R as AuthorizationRequestRepository
    participant OP as OpenID Provider
    B->>C: GET /oauth2/authorization/company
    C->>C: Generate state, nonce, PKCE context
    C->>R: Save OAuth2AuthorizationRequest
    C-->>B: 302 to authorization endpoint (state, nonce, challenge)
    B->>OP: Login / consent
    OP-->>B: 302 callback code + state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>R: Load/consume original request
    C->>C: Verify state, registration, and callback
    C->>OP: POST token endpoint (code + PKCE verifier)
    OP-->>C: access_token + id_token
    C->>C: Verify signature, iss, aud, exp, nonce
    alt Nonce matches
        C-->>B: Establish valid Authentication/session
    else Nonce missing or wrong
        C-->>B: Authentication failure; no new login
    end
~~~

Internal filter execution order can vary across versions; the diagram depicts **logical constraints**. JWKS keys may already be cached rather than fetched anew for every ID Token.

### 4.1. Outbound Leg: Creating the Authorization Request

When a user accesses:

~~~text
/oauth2/authorization/company
~~~

Spring Security uses `ClientRegistrationRepository` to pick the `company` registration and build an `OAuth2AuthorizationRequest`. For OIDC, parameters may include `scope=openid`, `state`, `nonce`, and PKCE when enabled/supported.

A conceptual structure:

~~~text
OAuth2AuthorizationRequest
  authorizationUri: https://id.example.com/authorize
  clientId: portal-web
  responseType: code
  redirectUri: https://portal.example.com/login/oauth2/code/company
  scopes: [openid, profile, email]
  state: random-state-1
  additionalParameters:
    nonce: value-sent-to-provider
    code_challenge: ...
    code_challenge_method: S256
  attributes:
    registration_id: company
    nonce_context: data-for-verification
    code_verifier: secret-for-PKCE
~~~

This is **not a fixed serialization schema**. Spring Security may store the raw nonce or data to compute/compare the nonce inside `attributes`; internal key names and representations depend on the version.

### 4.2. Inbound Leg: Recovering the Right Request

When the browser returns on the callback, Spring Security must retrieve the prior authorization request. For standard Servlet OAuth2 Login, `HttpSessionOAuth2AuthorizationRequestRepository` stores the request in the HTTP session, while the session cookie lets the server identify the original session.

The client verifies `state` and client context before processing tokens. Once an ID Token arrives:

1. Identify the trusted issuer and client registration configuration.
2. Verify the signature/algorithm or corresponding encryption requirements.
3. Verify `iss`, `aud`, `azp` if applicable, `exp`, and other OIDC conditions.
4. If the authorization request sent a nonce, properly derive/read the **expected nonce** from the saved request.
5. Compare it against the ID Token's `nonce` claim.
6. Only produce an OIDC login result when all mandatory checks succeed.

If the authorization request cannot be recovered, the application **has no trusted context to check the nonce**. Never "just accept the ID Token because its signature is valid" while skipping correlation.

### 4.3. Why Must the Request Be Consumed Once?

Authorization Codes must be short-lived and single-use. The client must also remove or mark the pending request as consumed so the same authorization request cannot be reused as a fresh transaction multiple times.

Nonce helps prevent replay, but does not replace **single-use authorization codes**, **`state` checks**, session TTLs, and authorization-request consumption policies. If a callback is replayed, the framework should reject it because the request has been consumed or the code is no longer valid.

## 5. Generating Nonces Securely

### 5.1. Properties a Nonce Should Have

A nonce protecting a transaction should:

- Be generated by a **cryptographically secure random number generator (CSPRNG)**.
- Have enough entropy to be practically unpredictable; modern applications can choose at least 128 bits of entropy.
- Be distinct across independent authentication requests.
- Never contain passwords, emails, user IDs, or configuration secrets.
- Be stored or bound securely long enough to verify the callback, but not retained indefinitely.
- Be compared against the **nonce sent to the OP**, not a value guessed by the client when the callback arrives.

Java example **illustrating only how to generate a nonce**:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class NonceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String randomNonce() {
        byte[] bytes = new byte[32]; // 256 bits of entropy
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }
}
~~~

This example does not require writing your own nonce generator when using Spring Security; the framework normally supplies an appropriate mechanism. The URL-safe Base64-encoded value is a random string, **not a JWT**.

### 5.2. Can a Nonce Be Transformed Before Sending?

A frequent source of confusion during debugging: **how the nonce is stored internally** and **the `nonce` value appearing in the authorization URL** may not be identical verbatim.

Some implementations retain a random nonce value in an internal attribute while sending **its hash** to the provider, then recompute the expected value to compare against the ID Token's `nonce` claim. Illustrative example:

~~~text
client_internal_nonce = random-256-bit-value
nonce_sent_to_provider = BASE64URL(SHA-256(client_internal_nonce))

Authorization request:
  nonce = nonce_sent_to_provider

ID Token claim:
  nonce = nonce_sent_to_provider

Client:
  expected = BASE64URL(SHA-256(saved_internal_nonce))
  compare expected with id_token.nonce
~~~

The key requirement is not that the client must always hash the nonce: **OIDC requires the `nonce` claim to match the value placed in the Authentication Request**. Whether to hash is an implementation choice; if Spring Security handles this for you, application code must not compare the claim against an internal value in a different representation and reach the wrong conclusion.

**Do not design a custom validator that "just grabs `request.attributes.nonce` and compares directly with `token.nonce`" without understanding how your Spring Security version's request resolver created the nonce.** It is safer to let Spring Security's OIDC authentication provider perform the verification.

### 5.3. Comparing Nonces Safely

In principle, compare the **exact expected string** against the ID Token's claim string — no fuzzy matching, no ignoring whitespace, no trimming prefixes or changing letter case. If implementing a specialized protocol handler yourself, use an appropriate comparison mechanism for security values and avoid leaking secrets via logs/exceptions.

Do not use:

~~~java
// ANTI-PATTERN — never use:
if (idTokenNonce != null) {
    acceptLogin(); // Only checks presence of nonce, not its value!
}
~~~

And do not use:

~~~java
// ANTI-PATTERN — never trust an expected value from the browser:
String expected = request.getParameter("nonce");
if (expected.equals(idTokenNonce)) {
    acceptLogin();
}
~~~

The **expected nonce** must originate from the authorization request/binding **reliably stored by the client**, never from a fresh parameter sent by the browser on the callback.

## 6. How AuthorizationRequestRepository Preserves Nonce Context

### 6.1. The Repository Bridges Two HTTP Requests

In Spring Security Servlet, `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` is responsible for saving, retrieving, and consuming pending authorization requests awaiting callbacks. Methods:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository;

repository.saveAuthorizationRequest(authRequest, request, response);

OAuth2AuthorizationRequest pending =
    repository.loadAuthorizationRequest(request);

OAuth2AuthorizationRequest consumed =
    repository.removeAuthorizationRequest(request, response);
~~~

This snippet illustrates the API; `authRequest`, `request`, and `response` are assumed to exist in a Servlet flow. Under default configuration, Spring Security invokes these methods; the application **does not need to call the repository manually in controllers**.

The repository must preserve **the attributes needed for the callback**: state, registration/context, redirect URI, PKCE verifier, and nonce data when present. A custom implementation that saves only `state` and drops `additionalParameters`/`attributes` can break nonce or PKCE verification.

### 6.2. HttpSessionOAuth2AuthorizationRequestRepository

Spring Security Servlet OAuth2 Login normally uses:

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;

HttpSessionOAuth2AuthorizationRequestRepository repository =
    new HttpSessionOAuth2AuthorizationRequestRepository();
~~~

On the outbound leg:

~~~text
Browser B
  Cookie: JSESSIONID=S123

Application HTTP Session S123
  pending OAuth2AuthorizationRequest
    state: S-NEW
    nonce context: N-NEW
    PKCE context: V-NEW
    registration: company
~~~

On the return leg, the browser must carry the matching session cookie. If the cookie is lost, has the wrong domain/path, the session expired, or the callback hits a node that cannot read the session, the framework cannot recover the request and cannot verify correlation as expected.

**Do not fix this by disabling state/nonce checks or accepting the ID Token when no request exists.** Instead, investigate why the session was lost, cookie/proxy configuration, or storage architecture.

### 6.3. Multi-Node Sessions and Multi-Tab Logins

| Case | Risk | Design Solution |
| --- | --- | --- |
| Single Spring Boot instance | In-memory session usually works for demos | Protect session cookie and TTL |
| Multiple instances behind load balancer | Outbound leg on node A, callback on node B cannot find request | Spring Session / shared store or controlled session affinity |
| User logs in across two tabs | Pending request may be overwritten by newer request, depending on repository | If product requires concurrency, use a repository supporting multiple states per session |
| User spends many minutes at IdP | Pending session/request expires | Display login failure and let user restart |
| Replayed callback | Authorization request already consumed or code expired | Reject; never auto-restore old requests |

If a custom repository uses Redis or a database to store multiple requests, the lookup key must bind **state and browser/session context**, with a TTL and single-use consumption behavior. Keying solely by `state` in a shared store does not guarantee isolation across browsers.

### 6.4. Do Not Log Nonce or Callback State

While debugging, you may need to know "was a nonce present?", "did the repository find the request?", or "did nonce validation fail?", but **never log nonce values, state, PKCE verifiers, authorization codes, tokens, or session cookies**.

Example safe metadata log:

~~~text
event=oidc_login_failure
registration_id=company
stage=id_token_validation
reason=nonce_mismatch
correlation_id=internal-trace-7b12
~~~

`reason=nonce_mismatch` is an illustrative log code and is not guaranteed to match exact exception codes across all Spring Security versions. `correlation_id` must be independent of OAuth/OIDC credentials.

## 7. Integrating Spring Security Servlet OIDC Client

### 7.1. Dependencies

A Spring Boot 3.x application using Servlet MVC and OIDC Login can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

With Spring Boot 4.x, modularized starter names are `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client` respectively. Choose the right branch per your project's Spring Boot BOM; never mix Spring Security versions manually.

### 7.2. ClientRegistration Configuration

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

`openid` requests OIDC. `issuer-uri` lets Spring Security discover OP metadata when the provider supports discovery and binds the issuer. Replace URIs and credentials with real values; never commit secrets. The public Redirect URI must match the client registration configured at the OP.

### 7.3. SecurityFilterChain Using the Repository

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

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
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)))
            .build();
    }
}
~~~

This example highlights the repository extension point; in practice **you do not need to declare a repository bean yourself** when using the default. What matters is that Spring Security manages the same request context across both the authorization redirect and the callback.

`oauth2Login()` handles Servlet OAuth2/OIDC authentication. You do not need to write a controller mapping `/login/oauth2/code/company` to parse `code` and `id_token` manually: callbacks are handled by Spring Security's filter.

### 7.4. Where Does Spring Security Get the Expected Nonce?

During OIDC Login, the component handling Authorization Code authentication uses the **retained authorization request** alongside the provider's ID Token data. Depending on version, the nonce is generated by the default authorization request resolver/customizer for OIDC and stored in an internal attribute of `OAuth2AuthorizationRequest`.

Conceptual flow:

~~~text
DefaultOAuth2AuthorizationRequestResolver
  -> builds authorization request
  -> state, OIDC nonce context, PKCE context when applicable
  -> AuthorizationRequestRepository.save(...)

OAuth2LoginAuthenticationFilter
  -> receives authorization code callback
  -> loads saved authorization request
  -> OAuth2/OIDC authentication provider
  -> receives and verifies ID Token
  -> if nonce was sent: matches ID Token nonce with request context
  -> Authentication succeeds/fails
~~~

Class names and default behavior may vary across versions or under customization; rely on the contract of the Spring Security version in use. **Applications should not write their own post-login controller nonce check** to replace authentication-provider verification.

### 7.5. Reading the Principal After Login

A controller can access the ID Token that passed through OIDC login:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("subject", user.getSubject());
        result.put("issuer", user.getIdToken().getIssuer().toString());
        result.put("idTokenHasNonceClaim",
            user.getIdToken().getClaims().containsKey("nonce"));
        return result;
    }
}
~~~

The boolean field `idTokenHasNonceClaim` merely observes **whether the claim is present**, **not the outcome of a manual nonce check**. In the Code flow, lacking a nonce may be valid for a request that did not send one; to know whether nonce binding is enforced properly, inspect the actual request/validator.

Never return `user.getIdToken().getTokenValue()`, nonce, Access Token, or session cookies to the browser for debugging.

## 8. Pseudocode: Checking Nonce If Building a Custom OIDC Client

With standard Spring Security, use the built-in validator. If a specialized system truly has to implement a custom OIDC handler, the validation order must guarantee:

~~~text
handleOidcCallback(callback, browserContext):
    pendingRequest = repository.consume(
        browserContext.session,
        callback.state
    )
    if pendingRequest == null:
        reject("authorization_request_not_found")

    if callback has OAuth authorization error:
        reject("authorization_denied_or_failed")

    tokenResponse = exchangeAuthorizationCode(
        callback.code,
        pendingRequest.redirectUri,
        pendingRequest.pkceVerifier,
        configuredClientAuthentication
    )

    idToken = tokenResponse.id_token
    if idToken == null:
        reject("missing_id_token")

    claims = verifyIdToken(
        idToken,
        trustedIssuer,
        expectedClientId,
        allowedSignatureAlgorithms,
        allowedJwks,
        currentTime
    )

    if pendingRequest.nonceWasSent:
        expected = deriveExactlyWhatWasSent(
            pendingRequest.savedNonceContext
        )
        if claims.nonce is missing or claims.nonce != expected:
            reject("nonce_validation_failed")

    // Remaining OIDC constraints must still be processed.
    authenticate(issuer=claims.iss, subject=claims.sub)
~~~

This is **pseudocode illustrating order**, not a production implementation. A compliant OIDC client must handle many additional conditions: issuer/audience/authorized party, algorithm and key restrictions, expiration/time claims, nonce, multi-audience cases, response types, token hash claims when required, protocol errors, and transaction state storage.

Do not substitute the pseudocode above for a mature library's ID Token verifier.

### 8.1. Why Must Nonce Be Checked After Verification?

An attacker can craft a string whose JSON payload includes `nonce=expected-value` if the application only decodes without verifying signatures. Nonce **does not turn an unverified JWT into a trusted JWT**. The client must ensure the token was genuinely issued by the trusted OP for the right audience, and only then use nonce to confirm transaction binding.

In real implementations, a library may order internal checks differently, yet it must never **accept login** before all mandatory conditions are satisfied.

## 9. How Should Nonce Failures Be Handled?

When the nonce mismatches, is missing even though the request sent a nonce, or the authorization request context cannot be recovered, the application must **fail closed**: never create a new login session from that ID Token.

In Spring Security Servlet, failures normally result in an `AuthenticationException` within the OAuth2/OIDC login mechanism. The application can configure an `AuthenticationFailureHandler` to send the browser to a friendly page.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class OAuthFailureConfig {

    @Bean
    SecurityFilterChain oauthFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/auth/failed", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .failureHandler(new SimpleUrlAuthenticationFailureHandler(
                    "/auth/failed")))
            .build();
    }
}
~~~

The `/auth/failed` page should display a neutral message such as "Unable to complete login; please try again," avoiding exposing nonce/ID Token values or sensitive technical errors. **Do not automatically redirect back to the provider in an infinite loop**, because lost-session or broken-callback conditions could repeat endlessly.

Note that this example is **an alternative `SecurityFilterChain` illustrating error handling**, not a block to place alongside the chain from the previous section. When wiring a real application, configure the failure handler on the same chain handling OAuth2 callbacks.

### 9.1. Distinguishing Nonce Errors from Other Errors

| Symptom | Possible Error Source | Action |
| --- | --- | --- |
| Nonce claim differs from expected nonce | ID Token does not belong to active request, or provider/custom resolver mismatch | Reject login; inspect provider and request context |
| ID Token missing nonce though request sent nonce | Provider failed to echo nonce, or wrong converter/token | Reject login; fix integration |
| Authorization request not found | Lost cookie/session, state mismatch, multi-node/multi-tab | Reject callback; fix correlation/session |
| ID Token expired | Clock/token issue | Reject token; inspect clocks and issuer |
| Invalid signature or issuer | Wrong JWKS, key rotation, tenant, or untrusted token | Reject; fix trust configuration |
| `aud` lacks client ID | ID Token issued for another client | Reject; check client registration |
| Token endpoint returns `invalid_grant` | Used/expired code, PKCE/redirect mismatch | Investigate token exchange; do not blame nonce |
| Provider returns `error=access_denied` | User/admin declined authorization | Handle consent failure; no successful token exists to check nonce |

A log line or exception mentioning "nonce" is only a clue to the failure point; never disable nonce checks just to "get login working" when a provider is returning the wrong claim.

## 10. Common Mistakes When Customizing Spring Security

### 10.1. Hardcoding a Fixed Nonce on Every Request

~~~java
// ANTI-PATTERN — do not use:
authorizationRequestBuilder.additionalParameters(
    params -> params.put("nonce", "fixed-nonce")
);
~~~

If a nonce repeats across transactions, its ability to bind an ID Token to a specific login attempt is weakened. Nonces must be generated individually via CSPRNG, not hardcoded per environment.

### 10.2. Generating the Nonce at Callback Time Instead of Authorization Time

A nonce generated after receiving the ID Token **cannot be the value originally sent to the OP**, so it provides no correlation. The expected value must originate from the initial request and be stored/recoverable.

### 10.3. Saving Only State and Losing Nonce and PKCE

A custom `AuthorizationRequestRepository` that serializes only `state` and `clientId` often lacks the data Spring Security needs to complete token exchange and nonce validation. Preserve all required `OAuth2AuthorizationRequest` state and consume the context properly.

### 10.4. Comparing ID Token Nonce Against State

`state` and `nonce` serve different purposes. A system sending `state=ABC`, `nonce=XYZ` must compare the ID Token nonce against `XYZ`, not `ABC`. If the request resolver hashes the nonce, compare against the exact representation sent.

### 10.5. Skipping Nonce When the ID Token Signature Is Valid

A valid signature does not prove the ID Token belongs to **the latest request**. If a nonce was requested, skipping the check opens the door to token replay or session mix-ups.

### 10.6. Skipping Signature Verification Because Nonce Matched

A JSON payload with any nonce can be forged by an attacker. If the ID Token has not been verified, the `nonce` claim **is untrusted**. The two check groups are independent.

### 10.7. Reading Expected Nonce from an External Request Parameter

A normal OAuth2 callback does not expect a fresh `nonce` parameter from the browser to verify the ID Token. If the application uses `request.getParameter("nonce")` as the expected value, an attacker controls the reference value. Always use the request context stored on the client side.

### 10.8. Storing the Request in a Shared Singleton Variable

~~~java
// ANTI-PATTERN — dangerous with multiple users:
static OAuth2AuthorizationRequest lastRequest;
~~~

Two concurrent users can overwrite each other's state/nonce. Use a repository scoped to the session/browser; never use a global variable holding only the last request.

### 10.9. Enabling a Custom Authorization Request Resolver Without Preserving Default Logic

If you replace the entire `OAuth2AuthorizationRequestResolver`, ensure it still preserves OIDC scopes, state, PKCE, nonce, redirect URI, and required attributes. A custom resolver that drops nonce context can cause validation failures; worse still is modifying the authentication provider to skip checks as a "workaround."

When needing extra parameters like `prompt`, `login_hint`, or `acr_values`, prefer extending the built-in resolver rather than rebuilding the whole Authorization Code flow.

### 10.10. Displaying Nonce or ID Token to Assist Users

Never send these values to error pages or browser logs. When investigating, use an internal correlation ID and categorized error codes. Never log full authorization URLs with `state`, callbacks with `code`, or ID Tokens for easier debugging.

## 11. Multi-Provider and Multi-Registration Scenarios

A Servlet application can support login across multiple OIDC Providers:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employee:
            provider: corp-oidc
            client-id: ${EMPLOYEE_CLIENT_ID}
            client-secret: ${EMPLOYEE_CLIENT_SECRET}
            scope: [openid, profile]
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope: [openid, email]
        provider:
          corp-oidc:
            issuer-uri: https://id.example.com/realms/company
          partner-oidc:
            issuer-uri: https://login.partner.example.net
~~~

Each authorization request has:

- Its corresponding trusted registration/issuer.
- Its own `state`.
- Its own `nonce`, if the request uses nonce.
- Its own PKCE context if enabled.
- A Redirect URI matching the client's registration.

If a user initiates login with `employee` and the callback returns a token issued by `partner`, issuer/audience validation must reject it. If the token comes from the right issuer yet carries a nonce from another request, nonce validation must reject it.

### 11.1. Two Parallel Login Tabs

~~~text
Tab A: /oauth2/authorization/employee
  state=A-STATE
  nonce=A-NONCE

Tab B: /oauth2/authorization/partner
  state=B-STATE
  nonce=B-NONCE
~~~

The repository must retain the right context for each transaction. With storage designs that allow only one pending request per session, B may overwrite A, causing callback A to fail. If concurrent logins are required, design the repository keyed by state **plus session binding**; each callback uses only its corresponding request's nonce, never "the session's latest nonce."

If callback A no longer has a matching request, **fail** and let the user restart rather than borrowing B's nonce.

### 11.2. Reverse Proxies and Distributed Sessions

A single login can traverse multiple Spring Boot instances. If HTTP sessions are not shared, the callback may fail to recover the request. When using Spring Session/Redis, ensure request data serializes safely and has an appropriate TTL.

Check cookie `Secure`, `HttpOnly`, `SameSite`, domain/path, and public callback URLs. For top-level GET Authorization Code callbacks, `SameSite=Lax` is usually suitable; if using cross-site POST response modes, design cookie policy separately. Never blindly switch to `SameSite=None` without evaluating CSRF and HTTPS configuration.

## 12. Testing Nonce Matching

Testing should distinguish two levels:

1. **Controller tests with mocked `OidcUser`:** verify application code after the user is authenticated, yet **do not prove protocol signature/nonce validation**.
2. **Integration tests with real OIDC login or a controllable test provider:** verify creating the authorization request, storing context, receiving tokens, verifying the ID Token, and rejecting bad nonces.

### 12.1. Scenarios to Simulate

| Scenario | Authorization Request | Returned ID Token | Expected Result |
| --- | --- | --- | --- |
| Valid nonce | Sent `nonce=N1` | `nonce=N1` claim and valid token | Proceed with login if all other checks pass |
| Wrong nonce | Sent `nonce=N1` | `nonce=N2` claim | Reject login |
| Missing nonce in ID Token | Sent `nonce=N1` | No `nonce` claim | Reject login |
| Code flow without sending nonce | Did not send nonce, compliant with config/spec | Token has no nonce | Do not automatically treat as nonce error; must still pass other OIDC checks |
| Invalid signature | Sent `nonce=N1` | Nonce matches yet signature invalid | Reject login |
| Wrong issuer | Sent `nonce=N1` | Nonce matches yet different issuer | Reject login |
| Wrong audience | Sent `nonce=N1` | Nonce matches yet `aud` is another client | Reject login |
| Lost session | Original request was lost | Token has seemingly matching nonce | No trusted context; reject |
| Multiple tabs | Two requests N1/N2 | Callback for A has N1 | Use only request A; never borrow N2 |
| Replayed callback | Request already consumed | Old unexpired token | Do not re-authenticate from an already-completed transaction |

### 12.2. Integration Testing with a Mock Provider

A valuable OIDC test should control:

- Metadata discovery or registration with trusted issuer/JWKS.
- Authorization endpoint returning code and state.
- Token endpoint returning a test-signed ID Token whose nonce is set to **matching, mismatched, or absent** per test case.
- Session/browser context between outbound leg and callback.
- Resulting `SecurityContext`, success/failure handler, and HTTP response.

A "wrong nonce" test must keep **all other conditions valid** — signature, issuer, audience, and expiration — if it aims to prove that nonce specifically caused the rejection. Conversely, a "valid nonce, invalid signature" test ensures the application does not treat nonce alone as sufficient.

Do not simulate login by manually placing an `OidcUser` into `SecurityContext` and concluding the nonce validator works; that bypasses the very flow under test.

### 12.3. User Clicks "Back" or Closes the Consent Tab

A user may leave the provider screen, close the tab, or return to the application without a valid callback. The failure handler does not have to run because **there was no response from the OP**. The pending authorization request expires per session/TTL; the UI should offer a way to restart and never grant login automatically.

## 13. Debugging When Spring Security Reports a Nonce Mismatch

A symptom-based reasoning table:

| Symptom | Likely Causes to Check | Resolution |
| --- | --- | --- |
| ID Token has nonce yet validator rejects it | Provider echoed a different nonce; client stored a different representation; custom resolver hashed/altered nonce wrongly | Check nonce creation/recovery logic in framework and provider contract without logging real values |
| Fails only when logging in across multiple tabs | Pending request overwritten or wrong state retrieved | Inspect repository and support for multiple requests per state/session |
| Fails only after multi-node deployment | Sessions not shared or callback routed to different node | Check distributed session / sticky routing and serialization |
| Sometimes no `nonce` claim appears | Provider didn't echo parameter, request didn't send nonce, or different flow used | Check OIDC flow and scope/authorization-request configuration |
| Callback reports authorization request not found | Lost cookie/session or state mismatch | Check `AuthorizationRequestRepository`, cookies, TTL, proxy |
| Valid token from provider A yet login used registration B | Wrong issuer/client/registration mapping | Check issuer, audience, token endpoint, and routing |
| Token expired / invalid signature simultaneously | ID Token validation failing before or alongside nonce | Fix key source, clock, issuer; never disable validators |
| Custom OAuth2 request resolver present | Did not preserve internal nonce/PKCE attributes | Build on Spring's resolver and preserve full request context |
| Callback processed twice | Pending request/code already consumed | Avoid auto-retrying old callbacks; initiate a fresh transaction |

### 13.1. Sensible Investigation Order

1. Identify the **registration ID** and **trusted configured issuer** — never read an issuer from an unverified token and trust it immediately.
2. Confirm whether the request is actually OIDC, includes `scope=openid`, and sent a nonce.
3. Confirm whether Spring Security recovered the authorization request for the **matching state and session**.
4. Check whether any custom resolver/repository preserved nonce context and PKCE attributes.
5. Check whether the provider returned an ID Token with the right issuer/audience and the `nonce` claim matching the request sent.
6. Check for multiple tabs, duplicate callbacks, session timeouts, reverse proxies, or multiple instances.
7. Fix the integration based on the specific root cause; never disable nonce/state/signature validation.

Log only categorized metadata. Never copy ID Tokens, nonces, states, client secrets, authorization codes, or cookies into public support tickets.

## 14. Real-World Scenario Analysis

### Scenario A: Valid Signature on ID Token, Nonce from Older Transaction

The new request sent nonce `N-NEW`, while the ID Token carries nonce `N-OLD`, with the same issuer and audience, and the token is unexpired.

**Conclusion:** reject. Signature and expiration do not prove the token belongs to the new transaction; the sent nonce must match.

### Scenario B: OIDC Provider Omits Nonce in Code Flow Even Though Client Sent It

The client's authorization request included nonce `N-123`. The token endpoint returns an ID Token without a `nonce` claim.

**Conclusion:** reject login in this transaction. Check scope configuration and provider behavior; never alter the application to waive verification already activated by the client.

### Scenario C: Code Flow Without Sending Nonce

A compliant OIDC Authorization Code flow configuration does not set a nonce parameter. The ID Token contains no nonce and passes all other checks.

**Conclusion:** do not automatically treat an absent nonce as an error if the transaction genuinely did not request one and the flow permits it. That is never a reason to skip issuer, audience, signature, state, or PKCE checks.

### Scenario D: Custom Repository Saves State but Drops Attributes

After callback, `state` matches yet nonce/PKCE data is gone. Token exchange may lack the verifier, or nonce validation cannot run properly.

**Conclusion:** fix the repository to save and restore the complete `OAuth2AuthorizationRequest`, rather than comparing the ID Token against `state`.

### Scenario E: Two Users Share a Global Nonce Variable

User A starts login with `NA`; User B starts afterward and overwrites the global variable with `NB`. A's callback arrives later.

**Conclusion:** concurrency and session-boundary bug. Use per-request state, store per session/browser, and never hold the expected nonce in a singleton field.

### Scenario F: Session Cookie Fails to Return After Redirect

The IdP returns the callback with a valid state, yet the browser lost its session cookie so the server cannot find the original request.

**Conclusion:** cannot accept login based on the ID Token alone. Check cookie `Domain`/`Path`/`SameSite`/`Secure`, reverse proxy, TTL, and distributed session setup.

### Scenario G: Matching Nonce, Wrong Audience

The ID Token has the matching nonce, trusted issuer, and valid signature, yet `aud` is another application's client ID.

**Conclusion:** reject. Nonce does not replace checking that the token was issued **for the current client**.

### Scenario H: User Declines Consent

The provider returns `error=access_denied` on the authorization callback; no successful token response exists.

**Conclusion:** handle OAuth2/OIDC login failure and consent-denial UX. Do not run nonce validation on a nonexistent ID Token.

## 15. References

- OpenID Connect Core 1.0 — Authentication Request and ID Token Validation: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Core 1.0 — Authorization Code Flow: https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth
- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — `AuthorizationRequestRepository` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/AuthorizationRequestRepository.html
- Spring Security — `OAuth2AuthorizationRequest` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html
- Proof Key for Code Exchange (RFC 7636): https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 16. Conclusion

In OpenID Connect, a nonce is not merely a random string appearing inside an ID Token. Its security value exists only when it is **generated for the original authorization request, stored with full context, sent to the OP, and matched accurately when verifying the ID Token**.

~~~text
OIDC Client
  1. Generate state + nonce + PKCE context (per config/flow)
  2. Save OAuth2AuthorizationRequest in repository
  3. Send authorization request with nonce to OP
  4. Receive callback code + state
  5. Restore exact request and verify correlation
  6. Exchange authorization code for ID Token
  7. Verify signature, iss, aud, exp, nonce if sent...
  8. Accept Authentication only when all mandatory checks pass

If original request is missing, nonce mismatches, or ID Token is invalid:
  => Reject login; do not bypass security.
~~~

**Let Spring Security perform OIDC validation via the framework's standard mechanisms**, unless there is a carefully designed customization requirement. When using a custom authorization request resolver or repository, preserve **state, nonce, PKCE, session, and registration** bindings. Nonce adds protection against ID Token mix-ups and replays, yet is effective only alongside proper ID Token checks and a compliant Authorization Code flow.
