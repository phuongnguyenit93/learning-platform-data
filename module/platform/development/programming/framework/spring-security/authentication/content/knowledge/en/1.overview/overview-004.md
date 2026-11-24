# Credentials, Identity Evidence, and Trust Boundaries

In Spring Security, a request carrying a username, password, cookie, or token **does not automatically become a trusted request**. The system must determine where that data came from, what it proves, who has the authority to verify it, whether it is still valid, and which access decisions are allowed based on the result. This is the foundation of authentication and also the starting point for understanding trust boundaries in web applications.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **identity**, **identifier**, **credential**, **evidence**, **authentication**, and **authorization**.
2. Explain what passwords, passkeys, OTPs, session cookies, API keys, and JWTs actually prove; recognize what they **do not** prove.
3. Identify trust boundaries among the browser, reverse proxy, Spring Security application, identity store, and Identity Provider (IdP).
4. Trace the path from client-supplied evidence to a verified `Authentication` and `SecurityContext`.
5. Propose evidence-verification steps, anti-spoofing/anti-replay controls, and positive and negative tests for each boundary.

## 2. Six Concepts That Must Be Kept Separate

| Concept | Meaning | Examples and limits |
| --- | --- | --- |
| **Identity** | The entity the system refers to: a person, service, device, or application account. | Employee account `u-123`; having an account does not mean legal identity has been verified. |
| **Identifier** | A value used to look up or reference an identity within a defined scope. | Username, email, account ID, or an OIDC `(issuer, sub)` pair. Email can change or be reassigned; do not assume it is a global key. |
| **Credential / authenticator** | A secret, key, or medium that a principal uses to prove control. | Password, passkey private key, client certificate, API key. Self-declared login info is unverified input. |
| **Evidence / assertion** | Data and verification outcomes supporting a claim about a principal. | Password matching a hash, valid challenge signature, JWT with valid signature and matching audience. Trust level depends on issuance and verification processes. |
| **Authentication** | The process by which the system checks evidence against policy and binds an authenticated principal to the processing context. | After a valid login, the app knows the request was presented by a party controlling the account's authenticator; it does not necessarily know who is physically at the keyboard in real life. |
| **Authorization** | Deciding whether the identified principal is allowed to perform a specific action on a specific resource. | `ROLE_USER` can read their own profile; being logged in does not allow reading another account's profile. |

**Identity proofing** (verifying identity at registration, e.g., checking government ID) differs from **authentication** (re-verifying control over an authenticator at login). Email verification usually proves only the ability to receive mail at that mailbox at check time; it does not by itself prove a person's name, profession, or legal status. In the NIST model, assurance levels for identity proofing, authentication, and federation are evaluated along separate dimensions. Never write a single `verified=true` flag to imply all of them.

Similarly, `Authentication.getName()` is the principal name accepted by the authentication mechanism; it is not independent proof. A request sending `{"userId":"admin"}` must never be allowed to decide on its own that the principal is `admin`.

## 3. What Does Identity Evidence Actually Prove?

A trustworthy system does not merely ask "is there a token/password?" but asks "**to which principal, purpose, target system, and point in time is this evidence bound?**"

| Medium | What can be proven after proper verification | What must not be inferred automatically | Risks to address |
| --- | --- | --- | --- |
| Password | The client knows the secret associated with the account. | The person typing is definitely the real-life account owner; the password has never been leaked. | Credential stuffing, phishing, brute force; safe password hashing, TLS, rate limiting, and appropriate MFA. |
| App/TOTP OTP | The client was able to obtain a code from a medium holding the TOTP secret at that time. | Complete phishing resistance or guarantee that the device is uncompromised. | Replay prevention within the validity window; manually entered codes can be relayed by attackers. |
| SMS/email OTP | The client received the code through the registered channel. | The channel is as secure as a passkey or proves legal identity. | SIM swapping, mailbox takeover, phishing, delays, and replay. |
| WebAuthn/passkey | The authenticator used a private key to answer a challenge for a valid relying party; server verifies signature, challenge, and origin/RP ID per protocol. | All passkeys have identical device or user-binding levels; the account owner cannot be tricked in other scenarios. | Key registration/revocation management, account recovery; use standard protocol validation. |
| Client certificate/mTLS | The connecting party possesses the private key corresponding to a certificate accepted by policy. | A service's certificate automatically implies the end user is permitted to do everything. | CA policy, subject name, certificate lifecycle and revocation. |
| API key or bearer token | The sender possesses the secret/token value accepted by the server. | The sender is the original subject at issuance time; the token was never stolen. | Scope, expiration, rotation, revocation, secret management, replay mitigation. |
| Session cookie | The browser sent a session identifier recognized by the server, or valid session data per design. | The password is being re-entered on every request; the cookie cannot be reused if stolen. | Session hijacking, session fixation, CSRF, timeouts, logout, and cookie attributes. |
| IdP ID token / assertion | A trusted issuer signed a statement about an authentication session/subject for a specific recipient, if validated per protocol. | Any token containing a `sub` field is a valid access token for your API. | Verify issuer, audience, signature, flow-specific nonce/state, time, and account mapping. |

**Bearer** means "whoever holds the value can use it" within the token's scope: a valid JWT signature proves integrity and signing origin, **not** that a stolen JWT cannot be replayed. Proof-of-possession mechanisms such as mTLS or DPoP add key-ownership verification; that property cannot be inferred from a standard bearer JWT.

**Distinguishing authentication from attribute verification:** An IdP may authenticate principal `sub=abc`; an application allowing a "money transfer" operation must still check permissions, account status, tenant, amount limits, and may require stronger authentication close to transaction time.

## 4. Trust Boundaries: Where a Claim Must Be Re-Verified

A trust boundary is the point where data crosses from a zone the receiver **has no default reason to trust** into a component that will make security decisions. Data crossing the boundary must be verified and normalized at the authoritative component.

```text
[User / browser / mobile app]
          |
          | (A) HTTP request: cookie, Authorization, body, header
          v
[Internet] --> [Gateway / reverse proxy / load balancer]
                          |
                          | (B) forwarded request; headers can be spoofed
                          v
                 [Spring Boot + Spring Security]
                    |      |        |
                    |      |        +--> [Policy / resource data]
                    |      +--> (C) [User store + password hash]
                    +---------> (D) [IdP / JWKS / OAuth2-OIDC]
```

- **A — client -> request-receiving infrastructure:** All parameters, cookies, headers, JSON bodies, client-side roles, hidden fields, and client-reported IP addresses are untrusted input. Use HTTPS/TLS and channel protection, but TLS only protects transport; it does not turn a client-filled `userId` into a trusted identity.
- **B — proxy -> application:** Accept identity headers inserted by a **verified, controlled proxy** only when the internal network, access paths, and duplicate/spoofed header stripping are all controlled. Never take `X-User-Id`, `X-Role`, or `X-Forwarded-User` from the Internet and create an `Authentication`. The proxy must also prevent clients from spoofing `Forwarded`/`X-Forwarded-*` headers that affect host, scheme, or redirects.
- **C — application -> user store:** The username entered by the client is only a lookup key. The user store returns the password hash, active/locked status, and authorities from an authoritative source; compare using `PasswordEncoder.matches(raw, encoded)`. Do not treat an existing username as authenticated, and never store/compare plaintext passwords.
- **D — application -> IdP/token issuer:** The application chooses **configured trusted issuers**, fetches verification keys over policy-compliant channels and metadata, and checks signatures and applicable claims. A JWKS URL or `iss` value nominated by the request itself must never be used to make trust decisions.
- **Application -> business resources:** After obtaining a principal, still check **permissions for the specific action and object**. An `accountId` in the URL/body is usually client-selected data, not automatically an account allowed for access.

Practical questions for every boundary: **Who created this value? Who has authority to sign/verify it? Can integrity, expiration, and intended recipient be verified? What data must still be checked against a trusted source?**

### The Chain of Trust Must Not Be Inverted

Wrong: "Header `X-User: alice` arrives at the API -> call `SecurityContextHolder` and set principal `alice` -> treat as logged in." Here the application promoted self-declared client data into trusted context without verification.

Right: "Client sends credential/token -> appropriate authentication mechanism verifies it -> map subject to account/tenant per policy -> create `Authentication` with appropriate status and authorities -> authorization checks action and resource." Only trusted components may promote unverified evidence into an authentication conclusion.

## 5. Lifecycle of Evidence: Login Differs from Subsequent Requests

### 5.1 Username/Password and Server-Side Sessions

1. The client sends username/password over an HTTPS connection to an abuse-protected login endpoint.
2. The server looks up the user by normalized identifier, checks account status, and checks the hashed password with an appropriate password encoder; if policy requires, verifies MFA as well.
3. On success, the system creates an authenticated principal and **establishes a session** according to the configured Spring Security mechanism. The session needs an unpredictable identifier, a clear lifecycle, and session ID rotation on login to mitigate session fixation.
4. The browser receives a session cookie with protective attributes, such as appropriate `Secure`, `HttpOnly`, and `SameSite`; the server maintains session state and principal binding per policy.
5. Subsequent requests send the cookie; the server **re-validates the session** and restores the user context, then authorizes the request. It does not re-check the password on every request by default.
6. Logout, expiration, or session revocation must cause the **server to reject** the old session identifier. Deleting the cookie only in the browser is insufficient if a copy of the cookie was stolen.

A session cookie is a kind of bearer credential. `HttpOnly` prevents JavaScript from reading the cookie directly, not replacing XSS defenses; `SameSite` mitigates some CSRF flows, not replacing proper CSRF protections; `Secure` requires HTTPS. For APIs using browser cookies sent automatically, evaluate CSRF even when endpoints only accept JSON.

### 5.2 Bearer Access Tokens for APIs

1. The client obtains an access token from the authorization server using an appropriate flow.
2. The API accepts tokens only via the prescribed channel, typically `Authorization: Bearer <token>` over HTTPS; **do not** trust token data just because Base64 decodes or JSON parses cleanly.
3. For self-contained JWTs, the resource server checks the signature under allowed algorithms/keys, `iss`, `aud`, `exp`, `nbf`, and related constraints (`scope`/`scp`, token type, tenant, revocation policy if any). For opaque tokens, use a trusted introspection mechanism per design.
4. Only after validation does the server map claims into principal and authorities; check **resource access permissions** on every request.
5. Token expiration does not mean every issued token can be revoked instantaneously; consider short lifetimes, revocation/introspection policies, key rotation, and account-status checks for risky cases.

JWT is a format; **JWT does not automatically mean OAuth2/OIDC, and not every JWT is meant for calling APIs**. An OIDC **ID token** is aimed at the client/relying party to describe a login outcome; an OAuth2 **access token** is issued to be presented to a resource server. An API must verify the token's audience targets **this API itself**, avoiding mistakenly accepting ID tokens or access tokens issued for other APIs.

### 5.3 Why Successful Authentication at Time T0 Is Not Enough Forever

Sessions can be stolen, permissions can be revoked, passwords can change, devices can be lost, and transactions can carry new risk. Designs require expiration, revocation, reauthentication/step-up policies for sensitive actions, and continuous authorization checks. Authentication assurance depends on the type of evidence and time of authentication, not an immutable boolean flag.

## 6. How Does Spring Security Turn Evidence into a SecurityContext?

In a **Servlet/MVC** application, the conceptual flow is:

```text
HTTP request
  -> SecurityFilterChain
  -> mechanism-appropriate filter (HTTP Basic, form login, bearer token, ...)
  -> Incoming Authentication token (may not be authenticated yet)
  -> AuthenticationManager / AuthenticationProvider or related decoder
  -> verify credential, token, and policy
  -> Authenticated Authentication: principal + authorities + details
  -> SecurityContextHolder holds SecurityContext for current processing turn
  -> AuthorizationFilter / method security decides permission
  -> controller/service
```

Some mechanisms use dedicated filters and validation components, so this diagram is a **mental model**, not a claim that every request passes through the exact same `AuthenticationProvider`. Key components to know:

- `SecurityFilterChain` determines which security filters apply to a request; chain order and request matchers affect which mechanism executes.
- `Authentication` can represent both an initial authentication request (principal + unverified credentials) and an authenticated result. `getPrincipal()` represents the subject, `getCredentials()` may be cleared after authentication; `getAuthorities()` holds assigned high-level authorities.
- `AuthenticationManager` (commonly `ProviderManager`) coordinates appropriate `AuthenticationProvider` instances such as username/password authentication. The provider validates evidence before returning a successful result.
- `SecurityContextHolder` provides `SecurityContext` in the processing context; by default Servlet uses `ThreadLocal`. Security filters are responsible for cleaning up the context properly. Never assume `ThreadLocal` carries over to async threads or the next request.
- `SecurityContextRepository` can load/save the context across requests per configuration; **being authenticated in the current request** does not automatically mean **a session was saved** for the next request.
- `GrantedAuthority` typically represents mapped roles or scopes. `ROLE_ADMIN` must never come directly from a client-supplied `role=ADMIN` parameter.
- The **anonymous authentication** mechanism may place an `AnonymousAuthenticationToken` in the context for unauthenticated requests. Therefore, merely checking `authentication != null` or even `authentication.isAuthenticated()` in business code **is not a reliable way to conclude a real user is logged in**; use `authenticated()`, `AuthenticationTrustResolver`, or proper Spring Security policy checks.

**Authentication differs from Authorization:** A principal may log in successfully and still receive HTTP `403 Forbidden` when lacking permission. With HTTP Basic, a request without valid credentials to a login-protected resource usually gets `401 Unauthorized` with a challenge; a `403` can also stem from CSRF or another security policy, so inspect the cause rather than guessing from status codes alone.

## 7. Runnable Example: An Authentication Boundary with Spring Security

The example below is a **Spring Boot Servlet** application using Java 17+, Spring Boot 3.x, and Spring Security 6.x with dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. Goal: public requests need no credentials; `/api/me` accepts only a principal authenticated via HTTP Basic. Single file `src/main/java/demo/AuthDemoApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-change-me"))
                .roles("LEARNER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "subject", authentication.getName(),
                "authenticated", authentication.isAuthenticated(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority).toList());
    }
}
```

Run using the Spring Boot project command after declaring the two starters, e.g. `./gradlew bootRun`; on Windows PowerShell use `.\gradlew.bat bootRun`. If creating an equivalent Maven project, the command is `./mvnw spring-boot:run`. This is a **Spring Boot example with dependencies**, not a program run solely with standard JDK `javac`.

Test from another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u learner:wrong http://localhost:8080/api/me
curl -sS -u learner:demo-change-me http://localhost:8080/api/me
```

Verifiable results:

| Request | Expected outcome | Reason |
| --- | --- | --- |
| `GET /public` | HTTP 200, body `public` | URL is configured with `permitAll()`. |
| `GET /api/me` without credentials | HTTP 401 | No valid principal for an endpoint requiring login. |
| `GET /api/me` with `learner:wrong` | HTTP 401 | Password does not match the account's hash. |
| `GET /api/me` with `learner:demo-change-me` | HTTP 200; JSON has `subject` = `learner`, `authenticated` = `true`, and `authorities` containing `ROLE_LEARNER` | Server verifies evidence and assigns authorities from the user store; JSON key order is not a fixed contract. |

**Interpretation:** The client could add header `X-User: admin`, yet the code does not read that header to construct the principal. `authentication.getName()` comes from Spring Security's verification result. `User.withUsername(...).roles("LEARNER")` assigns `ROLE_LEARNER` from server-side configuration, distinct from client-claimed roles.

The example uses a hardcoded password and in-memory user **only for local learning**. HTTP Basic sends Base64-encoded credentials, **not secure encryption**; production deployments always require HTTPS, secret management, storing hashes in a secure store, and brute-force protection. Default CSRF protection must still be considered for state-changing requests with cookies/sessions; never add `csrf.disable()` just to "make errors go away".

### 7.1 Reading Results Without Opening a Trust Vulnerability

The code below is a **logic illustration**, not a standalone runnable Java class:

```java
// In a service already protected by Spring Security:
String caller = authentication.getName(); // server-authenticated principal
String requestedAccount = request.accountId(); // client-chosen data

// Must check caller's permission on requestedAccount before reading.
authorizationService.checkCanRead(caller, requestedAccount);
return accountService.findById(requestedAccount);
```

A classic bug is replacing `checkCanRead(...)` with `if (authentication.isAuthenticated())` and returning any `accountId`; that is broken object-level authorization (IDOR/BOLA). Correct authentication cannot save broken authorization.

## 8. Four Before-and-After Scenarios

### Scenario A: "I put the username in a header"

- **Wrong:** API reads client-passed `X-User-Id`, calls `new UsernamePasswordAuthenticationToken(user, null, authorities)` with self-assigned authorities, and attaches it to the context.
- **Right:** API verifies a bearer token via a resource server, or trusts headers only when a protected authentication gateway and proxy **strip any client-sent copies** and the channel and access between gateway and app are controlled. In simple cases, let Spring Security verify credentials directly.

### Scenario B: "The JWT decoded to a sub, so it's authenticated"

- **Wrong:** Running Base64-decode on the payload, grabbing `sub` and `scope`, and granting access without checking the signature.
- **Right:** Resource server uses a **pre-configured** issuer/key, verifies signature, algorithm, timestamps, that `aud` is this API, and tenant/subject constraints before mapping scopes to authorities. If `aud` belongs to another service, return 401 even when the signature is valid.

### Scenario C: "Logged in means allowed to view the order"

- **Wrong:** Endpoint `GET /orders/{id}` only checks `authenticated()` and returns any order with that ID.
- **Right:** After authentication, the service checks `order.ownerId` or staff permissions and the principal's tenant against the order object. Return policy-appropriate errors when unauthorized, never leaking order data from another tenant.

### Scenario D: "A session cookie proves the user just entered their password"

- **Wrong:** Treating the presence of a cookie as high assurance and skipping re-verification.
- **Right:** The server checks session state, lifetime limits, and risk; sensitive operations may require reauthentication/step-up with a stronger factor. Logout must invalidate the old session on the server.

## 9. Verification and Secure Design at Each Boundary

### 9.1 Before Accepting Evidence

- **Source and purpose:** Identify which application, API, environment, and tenant the credential/token is meant for. Never let the client choose the issuer or trusted key endpoint.
- **Integrity and proof of possession:** Verify signatures/secrets/challenges with proper libraries and configuration; never roll your own JWT, hashing, or WebAuthn algorithms.
- **Expiration and anti-replay:** Check `exp`, `nbf`, nonce/challenge, session TTL, and protocol-appropriate revocation capabilities; never allow an OTP code to be reused.
- **Account binding:** Map the authentication result to a stable subject, account state, and correct tenant. With federation, use `(issuer, subject)` pairs or managed mapping rules; never merge two identities solely because emails match.
- **Credential storage:** Passwords require password hashes designed for passwords (such as properly configured bcrypt, Argon2id, PBKDF2), never raw SHA-256 or reversible encryption for storing passwords. Place tokens/secrets in a secret manager or equivalent secure vault; never log raw credentials.
- **Transport and sessions:** Always use HTTPS in production; session cookies `Secure`, `HttpOnly`, `SameSite` per architecture; CSRF protection where cookie-based automatic auth applies, plus defenses against XSS, session fixation, and session hijacking.
- **Least privilege:** Minimum required permissions; server-side authorization by action and object; never take roles from client-side UI.
- **Audit signals:** Record timestamp, mechanism, issuer, principal ID, and authN/authZ outcome with minimal data; avoid logging passwords, OTPs, cookies, Authorization headers, or full tokens.

### 9.2 Minimum Test Matrix

| Test case | Secure outcome required |
| --- | --- |
| Sending no credentials to an endpoint requiring login | Rejected before sensitive business logic executes. |
| Wrong, expired, revoked, or single-byte-modified credential | Produces no authenticated principal. |
| Valid JWT signature but wrong `iss` or `aud` | Rejected; no scopes/roles granted. |
| Client sends `X-User-Id: admin` or modifies `role` in body | Does not alter server-trusted principal or authorities. |
| Logged-in User A accesses `/accounts/B` | Denied by authorization if A has no permission on B. |
| Old session cookie after logout/expiration; reusing an OTP | Not accepted per session/anti-replay policy. |
| State-changing request originating from another site when using session cookies | Blocked by CSRF policy and appropriate SameSite/origin design. |
| Access token issued for API B sent to API A | API A rejects if audience is not A. |
| Account locked, permissions/tenant changed | Checkpoints reflect new state according to defined revocation and freshness design. |

### 9.3 Common Mental Traps

1. **"Authentication = verifying real-world identity":** In reality it may only verify control of an authenticator; identity proofing is a separate process.
2. **"Username in request = trusted principal":** Only a verified source and mapping policy yield a trusted identity.
3. **"Signed JWT = access to all APIs":** Must verify issuer, audience, expiration, scope, intended purpose, and data object.
4. **"Logged in = every action allowed":** Authentication only identifies the principal; authorization must decide per resource.
5. **"HttpOnly/SameSite/TLS solve everything":** Each mechanism mitigates one class of risks; CSRF, XSS, replay, phishing, and business permissions still need dedicated controls.
6. **"`isAuthenticated()` always means a real user logged in":** Account for anonymous tokens and use standard authorization rules instead of manual boolean checks.
7. **"JWT signature ensures the token cannot be stolen":** An exposed bearer token can still be replayed before it expires or is revoked.

## 10. Knowledge Self-Check

**Question 1.** A browser sends `{"accountId":"42","user":"admin"}`. Can the API use `user` to decide the caller is an admin?

**Answer:** No. JSON fields are client claims. The principal must come from a verified authentication mechanism; permissions on `accountId=42` still must be evaluated separately.

**Question 2.** A JWT has a valid signature and has not expired, but `aud` points to another billing service. Should the student-management API accept it?

**Answer:** No. The token was not issued for the receiving API; audience must be checked alongside issuer and other constraints.

**Question 3.** The API knows `authentication.getName() = "alice"`. Is Alice allowed by default to view Bob's order?

**Answer:** No. Authentication answers "who"; authorization must answer "is Alice allowed to read this order?" based on owner, tenant, and role/policy.

**Question 4.** Why does saving `SecurityContext` in a session not prove the client is re-entering their password on every request?

**Answer:** A session reuses the prior authentication outcome via cookie/session ID; accepting subsequent requests relies on the still-valid session, not a fresh password verification.

## 11. Standard References for Further Reading

- Spring Security — [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContextHolder`, `AuthenticationManager`, `AuthenticationProvider`, principal, and authorities.
- Spring Security — [OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying issuer, audience, timestamps, and signature for APIs.
- Spring Security — [Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder` and `DelegatingPasswordEncoder`.
- OWASP — [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): session lifecycle, cookies, and session risks.
- NIST — [SP 800-63 Digital Identity Guidelines](https://pages.nist.gov/800-63-4/): distinguishing identity proofing, authentication, and federation; phishing-resistant properties of authenticators.

**Key rule to remember:** Every request starts with data outside the trust boundary. Only a verification chain with a clear source and purpose is sufficient to promote it into a trusted `Authentication`; afterward, actions on each resource must still be authorized.