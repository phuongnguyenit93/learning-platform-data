# Map of Login Methods: Password, Session, Token, Certificate, and Passkey

**Module:** Spring Security – authentication. **Scope:** Overview of proving identity, persisting login state, and authenticating individual requests.

## 1. Five Names, Yet Not on the Same Layer

**Authentication (AuthN)** verifies who the caller is based on trusted evidence. **Authorization (AuthZ)** decides whether that principal has permission to perform a specific action. Successful login does not imply permission to access every resource.

The concepts in the title actually sit on three distinct layers:

| Concept | Primary layer | Meaning | Often combined with |
| --- | --- | --- | --- |
| **Password** | Initial authentication evidence | User proves knowledge of a secret; server checks against stored hash | Session or token after login |
| **Session** | Persisting authentication result | Client holds a session ID; server holds/retrieves login state | Password, passkey, IdP login |
| **Token** | Presenting issued evidence | Client sends a bearer access token to an API; server validates token | Password, passkey, OAuth2/OIDC, or machine flows |
| **X.509 certificate** | Cryptographic proof at TLS layer | In mTLS, client proves possession of the private key for a trusted certificate | Service identity, internal systems; sometimes sessions |
| **Passkey (WebAuthn/FIDO2)** | Initial authentication evidence | Authenticator signs a challenge bound to the website; server verifies public key | Session or token after login |

You should not ask "choose password or session?": **password** answers how the user is verified initially, while **session** answers how the user is recognized on subsequent requests. Similarly, a passkey typically **does not replace** sessions/tokens; it replaces or supplements the **identity-proof step**.

~~~text
Step 1: PROVE IDENTITY
        password / passkey / client certificate / IdP
                           |
                           v
Step 2: AUTHENTICATE AND ATTACH APPLICATION IDENTITY
        principal + authorities -> Authentication -> SecurityContext
                           |
                           v
Step 3: SUBSEQUENT REQUESTS
        session cookie / bearer access token / mTLS
                           |
                           v
Step 4: AUTHORIZATION
        is the resource allowed or denied?
~~~

All credential-transmission methods require a properly configured TLS channel. **Standard HTTPS authenticates the server to the client** and secures transport; it does not automatically log the user in.

## 2. Password: The "Something You Know" Factor

Common form login flow in Spring Security Servlet:

1. The browser receives a form over HTTPS; the user enters username/email and password.
2. The login request enters the security filter chain. For standard username-password login, the filter creates an unauthenticated `Authentication` and passes it to `AuthenticationManager`.
3. `AuthenticationManager` (typically `ProviderManager`) picks an appropriate `AuthenticationProvider`. `DaoAuthenticationProvider` can load the user via `UserDetailsService` and use `PasswordEncoder` to check the password.
4. If evidence and account status are valid, `Authentication` is marked authenticated and holds the principal and authorities. Otherwise, an error is returned without leaking account existence details.
5. A post-login mechanism may set a session cookie or issue a token; subsequent requests use the chosen mechanism to re-establish identity appropriately.

**Storage:** Never store plaintext passwords; never use reversible encryption to recover them. Use dedicated salted password hashing such as Argon2id/bcrypt with strong parameters, upgrade parameters when needed, and do not confuse with plain SHA-256. Design login attempt rate limiting, credential-stuffing monitoring, password reset flows, and MFA; do not leak "username exists/does not exist" via errors.

**HTTP Basic is another variant:** The `Authorization` header carries Base64-encoded username/password on **every request**, unlike browser form + session. Base64 is not encryption; HTTPS is mandatory, and avoid using Basic in unsuitable environments.

**Main drawbacks of passwords:** guessable, reused, and stealable via phishing. MFA reduces impact, while passkeys/WebAuthn provide a stronger phishing-resistant login path.

## 3. Session: Keeping Login State on the Server

Sessions are typically for browser applications using cookies. When initial authentication succeeds, the server creates a session storing or retrieving `SecurityContext`. The browser receives a **random session ID** (such as a `JSESSIONID` cookie) and automatically sends the cookie on subsequent requests.

~~~text
POST /login + form
   -> password authentication succeeds
   -> create/update server-side session
   <- Set-Cookie containing session ID

GET /profile + Cookie containing session ID
   -> server looks up matching session
   -> restores SecurityContext/Authentication
   -> checks permissions -> controller or denial

POST /logout
   -> invalidates server-side session and handles cookie
~~~

**A session ID is a bearer secret:** anyone holding a valid ID can hijack the session without knowing the password. The ID must be unpredictable, generated from a secure random source, rotated appropriately after login to prevent session fixation, bounded by idle/absolute timeouts, and invalidatable upon logout or suspected risk.

For cookies, control **HttpOnly**, **Secure**, **SameSite**, Domain/Path, and HTTPS/HSTS according to architecture. `HttpOnly` prevents JavaScript from reading the cookie but does not stop all consequences of XSS. Because browsers attach cookies automatically, state-changing requests usually need **CSRF protection**; `SameSite` helps mitigate CSRF but does not always replace CSRF tokens. Also control concurrent sessions and behavior during password resets or account locking.

**Spring Security Servlet:** `SecurityContextRepository` reads/saves `SecurityContext` across requests. When writing a custom authentication filter/controller, merely placing `Authentication` into the current request's `SecurityContextHolder` may not be enough to persist login: the context must be saved according to the Spring Security version's contract. For standard form login, use Spring Security's built-in mechanisms instead of rolling custom session handling.

**When to use:** web app with same backend, server-rendered app, internal dashboard, or browser + BFF needing centralized sessions, fast logout/revocation, and server-side lifecycle control. With multiple instances, consider a shared session store, availability, and consistency.

## 4. Token: Access Credential for APIs

An **access token** is evidence issued by a trusted issuer to a client. With Bearer authentication, the client attaches the token in the `Authorization` header of an HTTPS request, and the resource server validates the token to determine identity/permissions. Tokens can be issued after a login with password, passkey, or federation; there are also service-to-service flows without a human user.

~~~text
Client -- login/authorize --> Authorization server
Client <-- access token ----- Authorization server
Client -- Bearer token -----> Resource server
                              -> validate token
                              -> create Authentication for request
                              -> authorize -> result
~~~

Two common types:

| Token type | Verification | Trade-offs |
| --- | --- | --- |
| **JWT access token** | Verify signature, allowed algorithms, issuer, audience, exp/nbf, and claim policies | Can be verified locally; immediate revocation before expiration requires extra mechanisms |
| **Opaque access token** | Typically introspection with the authorization server or trusted state lookup | Easy to reference central state; depends on verification system cost/availability |

A JWT that can be **read/decoded** does not mean **trusted**. Never simply decode the payload and accept roles. The server must verify the signature with trusted keys, algorithm policy, **iss** (issuer), **aud** (target API), timestamps, and context-appropriate permissions. An **OIDC ID token** lets the client understand the user-authentication outcome and is not automatically a valid **access token** for an API. Scopes can be mapped to authorities, yet business-level permission checks are still needed.

Exposed bearer tokens can be **replayed**. Design short-lived access tokens, least privilege, secure storage, refresh token handling/rotation, revocation, key rotation, logout, and stolen-token response. Putting tokens in auto-sent cookies still requires evaluating CSRF; storing tokens where JavaScript can read them, especially `localStorage`, risks theft under XSS. A **backend-for-frontend** can keep tokens on the server and issue only session cookies to the browser when appropriate.

Spring Security's Resource Server has mechanisms to handle bearer JWT/opaque tokens. **A resource server validates tokens**; a resource server configuration alone **does not issue** tokens. Issuance belongs to an authorization server or a separate credential-issuing mechanism.

**Stateless** means the API needs no HTTP session storing `Authentication` between requests; each request carries its own evidence and is verified. Yet JWTs do not make the entire system completely stateless: keys, revocation lists, changing permissions, and refresh tokens can still have state.

## 5. X.509 Certificate: Cryptographic Identity in Mutual TLS

Distinguish two cases:

- **Standard TLS/HTTPS:** the browser/client checks the **server's** certificate; this only authenticates the server's identity.
- **mTLS (mutual TLS):** the server requests a **client certificate**. The client proves possession of the private key bound to the certificate during the TLS handshake; the server verifies the certificate and trust policy.

Flow:

~~~text
Service / client possessing certificate + private key
    -> TLS handshake, server requests client certificate
    -> verify private-key possession and trust chain
    -> Spring Security X.509 receives TLS-verified client identity
    -> map certificate subject/SAN to principal + authorities
    -> authorize request
~~~

**A technically valid certificate does not automatically grant system permissions.** You must verify the right CA/trust anchor, validity period, appropriate key usage/extended key usage, real identity of the subject, and revocation policy if required. Only then map the principal and grant least privilege. Plan for rotation/renewal, private key protection, re-issuance, and revocation.

**Be careful with gateways:** If TLS terminates at a reverse proxy/load balancer, the app must not trust arbitrary client-sent headers carrying a subject/certificate name. The gateway must perform real verification, strip spoofed headers, and forward identity over a protected trusted hop. This is a clear trust boundary.

**When to use:** service-to-service calls, enterprise clients, managed devices, and workload identities where PKI and sound certificate operations exist. For general consumer browsers, installing and revoking client certificates is usually harder to operate than passwords/passkeys.

## 6. Passkey/WebAuthn: Public-Key Authentication

Passkeys use **WebAuthn/FIDO2**. The authenticator creates a private key and a public key; the service only needs to store the public key and credential metadata. The private key is never sent to the server. The browser ensures the credential is bound to the proper **RP ID/origin**, thereby resisting phishing attacks that steal passwords and replay credentials on fake domains.

**Credential registration phase:**

1. The server initiates a registration session after verifying the account via a trusted method, issuing a random challenge along with the RP ID and policy.
2. The browser calls WebAuthn create; the authenticator creates a new credential, potentially requiring a PIN/biometric/confirmation gesture.
3. The server verifies the response, challenge, origin, RP ID, and policies, then stores the credential ID + public key linked to the account.

**Login phase:**

1. The server issues a fresh random challenge with a limited lifetime that cannot be reused.
2. The browser calls WebAuthn get with RP/challenge info; the authenticator verifies the user as required and signs the data with its private key.
3. The server looks up the registered public key, checks the signature, challenge, origin, RP ID, user presence/user verification flags per policy, and checks replay protection.
4. If valid, the application creates an `Authentication`, and can then issue a **session cookie** or **access token**.

Phishing resistance comes from the **cryptographic binding to the website** and challenge, not from sending fingerprints/faces to the server. PINs/biometrics normally only unlock local operations on the authenticator. Passkeys can be **synced across devices** or **hardware-bound**; do not assume every passkey is non-syncable.

You must still protect: recovery flows when devices are lost, enrolling new passkeys, account changes, post-login session/token theft risks, and HTTPS/secure context configuration. An overly weak recovery portal can nullify the phishing-resistant advantage of passkeys.

**Spring Security** supports WebAuthn/passkeys with configuration and dependencies depending on version; check the documentation for your project's version. With distributed session stores and required user verification, always apply appropriate recent security patches to avoid published implementation flaws.

## 7. Practical Pairing and Selection Map

| Scenario | Common suitable pairing | Key controls |
| --- | --- | --- |
| Server-rendered website | Password **or passkey** -> session cookie | CSRF, session fixation, logout, timeouts, MFA/step-up |
| Browser SPA with backend | Password/passkey/IdP -> BFF or backend session | Cookie SameSite, CSRF, CORS, XSS, server-side token protection |
| Mobile and public API | Authentication flow -> access token -> resource server validates bearer | Issuer/audience, scope, token lifetime, refresh, storage |
| Service-to-service | Client cert mTLS and/or access token for workload | PKI, trust boundary, key rotation, least-privilege policy |
| Website needing phishing resistance | Passkey -> session or token | RP ID/origin, recovery, device enrollment, session protection |

~~~text
[BROWSER]
   |-- password or WebAuthn passkey --> [Spring Security AuthN]
   |                                        |
   |                                        +--> Authentication
   |                                        +--> server session
   +-- cookie session --------------------> [Web backend]
                                            +--> per-request AuthZ

[MOBILE / API CLIENT]
   |-- authenticate via supported flow --> [Authorization Server]
   +-- receive access token --------------+
   +-- Bearer access token --------------> [Resource Server]
                                           +--> validate + AuthZ

[SERVICE A with client certificate] -- mTLS --> [Gateway / Service B]
                                               +--> identity mapping + AuthZ
~~~

Do not choose a technology just because "microservices must use JWT" or "passkeys don't need cookies". Selection starts from **who calls the system**, **who performs initial authentication**, **what preserves state across requests**, **revocation/step-up requirements**, and **trust boundaries**.

## 8. Where Do Spring Security Components Sit?

For **Servlet/Spring MVC**:

~~~text
HTTP request
 -> FilterChainProxy / SecurityFilterChain
 -> appropriate Authentication filter or mechanism
 -> AuthenticationManager -> AuthenticationProvider (if needed)
 -> SecurityContext containing Authentication
 -> AuthorizationManager checks permissions
 -> Controller or 401/403/redirect depending on scenario
~~~

- **Authentication:** authentication result or request, holding the principal and `GrantedAuthority` instances.
- **AuthenticationManager/ProviderManager:** coordinates providers capable of authenticating the corresponding credential type.
- **AuthenticationProvider:** verifies evidence (e.g., password or JWT); does not make all business permission decisions itself.
- **SecurityContext/SecurityContextHolder:** carries identity in the request-processing flow; for Servlet, typically involves `ThreadLocal`.
- **SecurityContextRepository:** reads/saves context across requests when using a persistence model.
- **AuthenticationEntryPoint:** prompts the client to authenticate when unauthenticated, e.g., login redirect or 401.
- **AuthorizationManager:** enforces allow/deny decisions; insufficient permissions typically result in 403.

**Java/Spring Boot Servlet example:** this configuration class describes **password form + session**. It must be part of a Spring Boot application with web and security starters, controllers, and an application entry point; this file alone is **not** a standalone Java program run with `javac`/`java`. The in-memory user and static password are for learning only:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-only-change-this-secret"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

If the application has protected endpoints, an unauthenticated browser is redirected to the default login page; after authentication it can continue with a session. This configuration class has no stdout of its own or self-generated endpoints beyond the enabled security mechanisms. Never hardcode real account secrets and never keep demo users in production.

For an API receiving JWTs, the configuration direction is **OAuth2 Resource Server**, `JwtDecoder`/validators, and standard issuer/audience checks; if the API **only** receives bearer headers and does not use browser cookies, you can choose `SessionCreationPolicy.STATELESS`. Never copy a configuration that disables CSRF from a bearer API to pages using session cookies.

For **Reactive/WebFlux**, the corresponding classes are `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveAuthenticationManager`; reactive security context does not work like Servlet `ThreadLocal`. Never mix Servlet and Reactive configurations.

## 9. Misconceptions That Cause Security Vulnerabilities

1. **Password equals session:** false; password is a credential, session is how authentication is persisted.
2. **Session cookies always contain the password:** usually false; cookies carry a session identifier, and the server holds state.
3. **A decodable JWT is trustworthy:** false; you must validate signature, issuer, audience, timestamps, and policies.
4. **JWTs always encrypt data:** false; signed JWTs do not hide their payload from readers by default.
5. **OIDC ID tokens can substitute for API access tokens:** false; different purposes and target audiences.
6. **An exposed bearer token isn't dangerous because it expires soon:** false; a still-valid token can be replayed.
7. **JWT in a cookie needs no CSRF protection:** false; browsers can send cookies automatically when tricked.
8. **HttpOnly stops all XSS:** false; it primarily stops scripts from directly reading the cookie.
9. **A passkey is a fingerprint sent to the backend:** false; the backend verifies a signature/public key.
10. **Passkeys eliminate all session-hijacking risks:** false; after WebAuthn, cookies/tokens can still be stolen.
11. **Server HTTPS certificate authenticates the user:** false; mTLS or another login mechanism is needed for client identity.
12. **Browser-declared client-certificate headers can be trusted:** false; rely on trusted TLS/gateway termination.
13. **Successful authentication equals admin rights:** false; AuthZ is always separate from AuthN.
14. **Stateless is always faster/safer:** not by default; revocation, key management, and trust must be analyzed.
15. **Disabling CSRF is how to fix every 403 on POST:** false; first inspect the cookie model and CSRF token handling.

## 10. Exercises to Test Your Thinking

**Question 1.** A user logs in with a passkey and receives a session cookie. Must subsequent requests sign a WebAuthn challenge every time?  
**Answer:** Usually no. The server relies on the still-valid session; sensitive operations may require additional authentication.

**Question 2.** An API receives a JWT containing role ADMIN in its payload. Is that enough to grant admin permissions?  
**Answer:** No. You must verify the token is valid for this API, map claims to authorities per policy, and check authorization.

**Question 3.** TLS at the gateway validates a valid client certificate. Can the backend blindly accept an "X-Client-User: admin" header from the Internet?  
**Answer:** No. The gateway must strip self-declared headers, pass verified identity over a trusted channel, and the backend must check permissions.

**Question 4.** Protecting a website that uses session cookies with HttpOnly and SameSite guarantees no CSRF is possible?  
**Answer:** No. Evaluate CSRF based on cookie-sending behavior and protect state-changing requests.

**Question 5.** An enterprise wants phishing-resistant login yet needs immediate browser logout: what combination fits?  
**Answer:** Passkey/WebAuthn for initial authentication and server-controlled sessions, with appropriate lifecycle, CSRF, and AuthZ.

## 11. Further Study Resources

- [Spring Security: Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html) — manager, provider, principal, security context.
- [Spring Security: Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html) — form-based login and filters.
- [Spring Security: Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — SecurityContextRepository, persistence, sessions.
- [Spring Security: JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — JWT validation and claims.
- [Spring Security: X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html) — client certificates.
- [Spring Security: Passkeys](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html) and [MDN: Passkeys](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys) — WebAuthn, challenge, RP/origin.
- [OWASP: Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) and [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet) — practical risk controls.

**Key takeaway:** How to **prove identity**, how to **carry authentication results across requests**, and how to **determine permissions** are three separate architectural decisions; only combining them properly yields a secure login flow.