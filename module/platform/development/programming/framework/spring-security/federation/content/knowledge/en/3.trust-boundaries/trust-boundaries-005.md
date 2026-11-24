# Correlating the Login Request with the Response and Original Browser Session

In federation, an application (Relying Party/Service Provider, RP/SP) sends a user to an Identity Provider (IdP) and then receives a response through the browser. Having a response that **carries a valid signature and comes from a trusted IdP** is not enough to determine that **the exact browser session receiving the response is the one that initiated that login request**. The system must correlate three things: **the initial request → the returned response → the browser session that started the transaction**.

This is a critical trust boundary: **the browser and all callback parameters are untrusted inputs**; the application only accepts them when they match transaction state stored and verified on the server side. This lesson focuses on application-initiated login flows (*SP/RP-initiated login*), analyzing OAuth 2.0/OpenID Connect (OIDC) and SAML 2.0 in parallel.

## 1. Why Verifying the Response Is Still Not Enough

Suppose an attacker signs in to their own account at the IdP and then attempts to send **the attacker's login response** to the callback endpoint currently open in the victim's browser. If the application only checks that the response is valid without knowing who initiated the transaction, the victim's browser may be bound to the attacker's application session. This is a form of **login CSRF / session swapping**, which can cause the victim to inadvertently enter data into the attacker's account.

Different questions must be verified independently:

| Question | Evidence to Check | If Skipped |
| --- | --- | --- |
| Was the response issued by a trusted partner and is it still valid? | Signature, issuer, audience/client, timestamps, destination/recipient depending on protocol. | Token/assertion forgery or accepting a response intended for another application. |
| **Which login attempt** does the response belong to? | OAuth/OIDC: `state`, PKCE, `nonce` when used. SAML: AuthnRequest ID and `InResponseTo`. | Injecting or replaying a response into another transaction. |
| Was that transaction initiated by **this browser session**? | Transaction record stored server-side, bound to the original browser session/cookie. | A valid response gets injected into an unrelated browser session. |
| Has the response already been accepted? | One-time processing, delete transaction upon completion; protocol-level replay protection. | Reusing authorization codes, assertions, or login state. |

**Note:** `state`, `RelayState`, and `InResponseTo` carry different meanings. Never treat a parameter received from a URL/form as self-evident proof that the callback belongs to the current browser.

## 2. Login Transaction Model

~~~text
Browser A                 RP/SP App                        IdP
     |                         |                            |
     | 1. Login request        |                            |
     |------------------------>|                            |
     |                         | 2. Create random transaction
     |                         |    store in session A      |
     |                         |                            |
     | 3. Redirect/AuthnRequest|                            |
     |<------------------------|                            |
     |------------------------ browser navigates to IdP --->|
     |                         |                            |
     |<----------------- 4. IdP authenticates / sends resp -|
     |                         |                            |
     | 5. Callback + cookie A  |                            |
     |------------------------>|                            |
     |                         | 6. Load A's transaction    |
     |                         |    match correlation       |
     |                         |    verify response         |
     |                         |    consume once            |
     |<--- 7. App session -----|                            |
~~~

The application must store a short-lived **pending login transaction** bound to the exact browser session. At minimum, the transaction holds the information needed to look up the trusted partner, match request/response, and complete token/assertion exchange: IdP identifier, `state` or AuthnRequest ID, PKCE `code_verifier` for OAuth, `nonce` if required by the protocol or used by the app, creation time, and the validated return URI.

Transaction data must be stored/issued using tamper-resistant mechanisms, bound to the user session, and **never leak secrets**. Storing in server-side session is a common choice. If using a distributed store or cryptographically protected cookie, the design must preserve **unpredictability, integrity, time limits, single-use, and session binding**.

## 3. Correlation in OAuth 2.0 / OpenID Connect

### 3.1. `state` Correlates the Authorization Response with the Original Request

The application generates a sufficiently strong random `state` for **each transaction**, stores the expected state in browser session A, and includes `state` in the authorization request. A valid callback must return that exact value within session A's context. A key purpose is defending against login CSRF and preventing a foreign callback from being paired with another transaction.

Illustrative example (values shortened; **do not use as real randomness**):

~~~text
Browser A, session=sess-A
GET /oauth2/authorization/corporate

Application stores in sess-A:
  state = St-7g...A
  provider = corporate
  redirect_uri = https://rp.example.org/login/oauth2/code/corporate
  code_verifier = <random secret value>
  nonce = <random value, if used>
  created_at = <start time>

Callback:
GET /login/oauth2/code/corporate?code=...&state=St-7g...A

Application finds pending transaction in sess-A,
matches state, provider, and protocol parameters,
and only then processes code exchange and creates login session.
~~~

If browser **B** sends the same `state` while session B has no matching pending transaction, **it must be rejected**. If the response lacks a matching `state`, or the transaction has expired or already been used, it must also be rejected. Never create a new pending transaction from callback parameters to legitimize it.

### 3.2. PKCE and `nonce` Add Per-Transaction Binding

- **PKCE**: the client generates a random `code_verifier` and sends `code_challenge` to the Authorization Server; when exchanging the authorization code, it must present the matching verifier. This mitigates code interception/injection risks. For CSRF protection via PKCE, the verifier must truly be **bound to the client and initiating browser session**, and the Authorization Server must support and enforce PKCE; never replace a proper `state` with an arbitrary verifier string sent from the callback.
- **OIDC `nonce`**: when used, the application stores the expected nonce bound to the transaction and verifies the `nonce` claim in the ID token. Nonce helps bind the ID token to the authentication attempt and prevent replay. Whether nonce is required depends on the OIDC flow and configuration; never skip nonce verification if it was sent in the request.
- **ID tokens** must have their signature, issuer, audience, expiration, and relevant OIDC constraints verified. An **access token** cannot automatically substitute for OIDC client identity verification.
- **Authorization codes** are exchanged only at the token endpoint of the exact selected issuer, along with `redirect_uri`, client authentication, and PKCE per configuration. A callback must be rejected when the issuer does not match the authorization transaction (*mix-up defense*), especially for clients supporting multiple IdPs.

RFC 9700 recommends PKCE for confidential clients and requires it for public clients, along with binding the challenge/nonce to the transaction and user agent. The `state` value may also carry application state, but must be integrity-protected against tampering; ideally, store only a random key and look up sensitive state server-side.

### 3.3. Secure OIDC Callback Processing Flow

1. Receive the callback at the **exact registered redirect URI**, using HTTPS and proper reverse proxy configuration.
2. Identify the **current browser session from a trusted cookie/session**; never take a session ID from a user-supplied query parameter or request body.
3. Load the pending transaction belonging to that session; if missing, expired, or already used, reject it.
4. Compare `state`; check the transaction's IdP/issuer (and mix-up defenses), `redirect_uri`, and client registration.
5. Exchange the `code` with the PKCE verifier of **that exact transaction**; never use a verifier from an unprotected source.
6. Verify the ID token per OIDC, including `nonce` when used. Only create `Authentication` after all conditions pass.
7. Mark the transaction as consumed **atomically**, preventing concurrent callbacks from re-accepting it; protect the login session upon success with session fixation defenses, secure cookies, and least privilege.
8. If redirecting back to the page the user intended to open, use only a **validated/allowlisted path**, avoiding open redirects that leak codes or send users to phishing sites.

An error at any step must end with **unauthenticated**; you may log a correlation ID and error category at a safe level, while never logging raw authorization codes, tokens, cookies, or `code_verifier`.

## 4. Correlation in SAML 2.0 (SP-Initiated SSO)

In SAML, the SP application sends an **`AuthnRequest`** with a unique `ID`. The SP retains that request record in the initiating browser session. The IdP sends a **`Response`** to the Assertion Consumer Service (ACS), typically via HTTP POST, with `InResponseTo` referencing the request ID; the `SubjectConfirmationData` section of a bearer assertion may also contain `InResponseTo` per the profile.

Values to distinguish:

| Value | Source | Role |
| --- | --- | --- |
| `AuthnRequest/@ID` | Generated and stored by SP at start. | Identifies the authentication request. |
| `Response/@InResponseTo` | Returned by IdP based on AuthnRequest. | Correlates the response with the issued request. |
| `SubjectConfirmationData/@InResponseTo` | Inside the assertion per bearer SSO profile. | Binds the assertion to the matching AuthnRequest. |
| `RelayState` | Accompanies SAML request/response over binding. | Preserves app state/transaction routing; **does not prove session ownership by itself**. |
| Browser session cookie | Sent by browser to SP. | Enables SP to recover the transaction **initiated from this browser**. |
| `Destination`, `Recipient`, `AudienceRestriction` | Inside response/assertion. | Restricts the endpoint/software allowed to use the assertion; complements but does not replace session binding. |

**Standard verification for SP-initiated:** The SP must retrieve the original AuthnRequest from a trusted session-bound transaction and require `InResponseTo` to match; next, verify the response/assertion belongs to a trusted IdP, has a valid profile-compliant signature, matching issuer, `Destination`/ACS, `Recipient`, audience, validity window, and SubjectConfirmation. Assertion IDs/response IDs must be tracked for replay protection and accepted only once.

**IdP-initiated (unsolicited) SSO** has no prior SP-opened AuthnRequest and thus lacks the same `InResponseTo` binding. If the product permits it, that is a **separate flow with its own risk policy**. Never silently fall back from a failed SP-initiated check to unsolicited mode just to "make login succeed".

### 4.1. Very Common Mistake: Looking Up Only by `RelayState`

Suppose the SP stores all AuthnRequests in a shared cache and uses `RelayState` from the response as the lookup key for the request, **without proving the current browser initiated that request**. An attacker can use a callback carrying a valid reference code to attach their own flow to the victim's session. Therefore, a distributed cache must store evidence binding the browser session and re-verify that evidence at callback time; never blindly trust `RelayState` or `InResponseTo` arriving from a form POST.

If the browser loses cookies due to `SameSite` policies in cross-site SAML POST flows, the fix is to design the session/cookie or correlation store to fit the flow and security requirements. **Never fix it by skipping session or InResponseTo checks.**

## 5. Java 17 Illustration: Session Correlation and Single-Use Consumption

The example below **only simulates** server-side transaction checking; it does not implement OIDC/SAML, does not verify signatures, and does not replace Spring Security or protocol libraries. In a real application, the session name comes from a protected container/web session, data is persisted securely per deployment model, and full token/assertion verification must succeed before issuing an application session.

File `LoginCorrelationDemo.java`:

~~~java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class LoginCorrelationDemo {
    record Pending(String state, String idp) {}

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final ConcurrentMap<String, Pending> REQUESTS =
            new ConcurrentHashMap<>();

    static String begin(String browserSession, String idp) {
        byte[] random = new byte[32];
        RANDOM.nextBytes(random);
        String state = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(random);
        REQUESTS.put(browserSession, new Pending(state, idp));
        return state;
    }

    static boolean verifyAndConsume(
            String browserSession, String state, String idp) {
        Pending pending = REQUESTS.get(browserSession);
        return pending != null
                && pending.state().equals(state)
                && pending.idp().equals(idp)
                && REQUESTS.remove(browserSession, pending);
    }

    public static void main(String[] args) {
        String stateA = begin("session-A", "idp-corporate");

        System.out.println(verifyAndConsume(
                "session-B", stateA, "idp-corporate"));
        System.out.println(verifyAndConsume(
                "session-A", stateA, "idp-corporate"));
        System.out.println(verifyAndConsume(
                "session-A", stateA, "idp-corporate"));
    }
}
~~~

Run on Java 17 or higher:

~~~bash
javac LoginCorrelationDemo.java
java LoginCorrelationDemo
~~~

Deterministic output (even though the random value of `state` changes):

~~~text
false
true
false
~~~

Explanation: the callback from **B** is rejected because there is no pending request in session B; the first attempt from **A** is valid; the second attempt from A is rejected because the transaction was already consumed. The demo intentionally keeps only **one** pending request per session; a system supporting multiple parallel login tabs must create a **separate record per transaction** with a random key, expiration time, and atomic removal. Do not use the `ConcurrentHashMap` in this example as a real distributed transaction store.

## 6. How Does Spring Security Servlet Support This Binding?

Spring Security provides mechanisms for managing pending requests, so applications should typically configure the protocol through the framework and **keep the default verification/correlation layers intact**.

| Flow | Spring Security Component | Related Function |
| --- | --- | --- |
| OAuth 2.0/OIDC | `OAuth2AuthorizationRequestRedirectFilter`, `OAuth2AuthorizationRequestResolver` | Creates and sends the authorization request. |
| OAuth 2.0/OIDC | `AuthorizationRequestRepository` | Stores the request from initiation to callback; defaults to `HttpSessionOAuth2AuthorizationRequestRepository`. |
| OAuth 2.0/OIDC | `OAuth2LoginAuthenticationFilter` | Loads and verifies the matching transaction upon receiving the authorization response. |
| SAML 2.0 | `Saml2WebSsoAuthenticationRequestFilter` | Creates/sends `AuthnRequest`. |
| SAML 2.0 | `Saml2AuthenticationRequestRepository` | Stores `AuthnRequest`; defaults to `HttpSessionSaml2AuthenticationRequestRepository`. |
| SAML 2.0 | `Saml2WebSsoAuthenticationFilter` and OpenSAML authentication provider | Loads the transaction, parses and verifies the SAML response/assertion. |

Example configuration of **an OIDC Servlet application** with Spring Boot having dependencies `spring-boot-starter-security` and `spring-boot-starter-oauth2-client`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **configuration inside a Spring Boot project**, not a standalone `javac`-compilable file. Besides the configuration class, the application needs a valid `ClientRegistration`/issuer and client credentials via application properties or beans. Spring manages authorization requests in `HttpSession` by default; you do not have to build a custom callback controller that receives `state` and calls the token endpoint manually.

For a SAML application, the equivalent configuration is `saml2Login(Customizer.withDefaults())` with a `RelyingPartyRegistration` and valid IdP metadata/certificates. Keep default validation enabled, especially `InResponseTo`, audience, issuer, signature, validity window, and recipient/destination. Provider names and customization methods may vary by Spring Security/OpenSAML version; check the **exact version's** documentation if replacing repositories or validators.

### 6.1. Cookies, Reverse Proxies, and Multiple Instances

- Use HTTPS and session cookies with `Secure`, `HttpOnly`, and appropriate `SameSite` configuration. OAuth GET redirects and cross-site SAML POSTs have different cookie requirements; test on real browsers, especially when the IdP is cross-site.
- If a callback arrives at another instance, there must be a secure shared session/transaction mechanism or proper routing. Callbacks that cannot find a transaction **must fail safely**, never disable checks.
- When behind a reverse proxy, configure the public URI and forwarded-header handling from a **trusted** proxy; wrong scheme/host values can cause redirect URI or destination/recipient mismatches.
- With multiple IdPs or multiple tenants, resolve registration/issuer from the trusted transaction; avoid taking the entire IdP choice from a self-reported callback field.
- When a user opens two concurrent login flows in the same session, decide whether the repository stores one or multiple transactions; overwritten transactions or mismatched callbacks can cause login failures. Never "fix" this by accepting callbacks lacking correlation.

## 7. Checklist and Test Scenarios

| Test | Expected Secure Result |
| --- | --- |
| Callback returns valid `state` but cookie belongs to another session. | Rejected; no login session created. |
| Callback missing or wrong `state`. | Rejected; do not re-derive transaction. |
| Valid authorization code but missing/wrong PKCE verifier. | Code exchange fails; no session created. |
| ID token has `nonce` mismatching transaction. | OIDC authentication rejected. |
| Returning code from IdP B for a transaction started with IdP A. | Rejected by issuer/client/transaction binding. |
| SAML `InResponseTo` does not point to a pending AuthnRequest in **the same session**. | SP-initiated login rejected. |
| SAML response has valid signature but wrong audience/recipient. | Rejected; valid signature is not enough. |
| Replaying an already completed callback. | Rejected on the second attempt. |
| Callback arrives after transaction expired or session was cleared. | Rejected; require user to initiate a new login. |
| Attempting to send the user to an unapproved external `returnUrl`. | Do not redirect to an arbitrary third-party URL. |

**Signals to watch when debugging:** transaction not found, state/nonce mismatch, wrong issuer/registration, `InResponseTo` mismatch, callback lost cookie, expired request, code exchange failure. Log **a hashed transaction ID or safe internal identifier**, error category, timestamp, and configured IdP; avoid logging tokens, assertions containing PII, cookies, or verifiers.

## 8. Takeaways

1. **Partner trust** answers "who issued the response?"; **correlation** answers "which login attempt does this response belong to?"; **session binding** answers "which browser did that login attempt originate from?".
2. OAuth/OIDC uses `state` with securely stored transaction state, PKCE, and `nonce` when applicable; SAML uses AuthnRequest, `InResponseTo`, controlled `RelayState`, and session correlation.
3. Every callback must be verified and consumed only once. Never recover a login session from a callback parameter not bound to a browser session.
4. Spring Security libraries implement standard logic; any custom repository or callback logic must **preserve or strengthen** security checks, never drop validation for integration convenience.

## References

- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0 — state and nonce](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Authorization Code and AuthorizationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
