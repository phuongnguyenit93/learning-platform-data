# Learning OAuth 2.0, OpenID Connect, and Identity Federation Next When Needed

> **Place in the roadmap:** After understanding authentication, authorization, `SecurityFilterChain`, sessions, and endpoint protection with Spring Security, learn OAuth 2.0, OpenID Connect (OIDC), or federation when a system genuinely needs login via an external identity provider, token-based API calls, or shared identities across multiple applications.

## 1. Why Is This a Conditional Next Step?

Spring Security fundamentals answer “is this request authenticated and what is it allowed to do?”. The following requirements add the questions “who issues the identity?”, “who grants access permissions?”, and “which systems does the application trust?”:

- Users log in with corporate accounts, Google, or an Identity Provider (IdP).
- Multiple applications need **Single Sign-On (SSO)** so users do not have to re-enter passwords in every app.
- A web app needs to call another API **on the user's behalf** without knowing their password for that API.
- A backend needs to **receive and validate access tokens** issued by an Authorization Server.
- Two services exchange data **without an interactive user**, using the application's own identity.
- An application needs to trust an IdP belonging to another organization (federation).

If the current project only needs local login and a few authorization rules, you do not have to implement OAuth2/OIDC immediately. Before picking a technology, define the user flow, clients, APIs, trust organizations, and security requirements clearly.

## 2. Three Very Commonly Confused Concepts

| Concept | Purpose | What to learn |
| --- | --- | --- |
| **OAuth 2.0** | Delegating authorization so a `client` accesses limited resources via an `access token` | Authorization Server, Resource Server, grants, scopes, token lifecycle |
| **OpenID Connect (OIDC)** | Standardized user authentication built on top of OAuth 2.0 | ID token, `openid` scope, issuer, subject, audience, nonce, UserInfo |
| **Identity federation** | Trust relationship letting system A accept identities authenticated by system B | IdP/Relying Party, trust, account mapping, policy, OIDC or SAML |

**OAuth2 by itself is not an identity login protocol.** An access token normally represents authorization for an API, whereas an **ID token** in OIDC conveys information about the authentication event to the client application. Some OAuth2 providers expose a user-info API and Spring Security supports logging in with them via provider-specific wiring, but OIDC standardizes identity assertions much more cleanly.

**SSO is not the name of a protocol.** SSO is the login experience shared across multiple applications; federation is the trust model; OIDC and SAML 2.0 are protocols that can implement it. SAML is not “an old version of OAuth2”; many enterprise systems still use SAML federation.

### Roles in OAuth 2.0

1. **Resource Owner:** the entity owning access to the resource, usually the end user in an interactive delegation flow.
2. **Client:** the application requesting access; can be a web app, mobile app, or service.
3. **Authorization Server:** authenticates/evaluates policy and issues tokens.
4. **Resource Server:** the API accepting access tokens and protecting resources.
5. **OpenID Provider (OP):** an IdP supporting OIDC. An application relying on an OP for authentication is called a **Relying Party (RP)**.

One application can play multiple roles across different flows. For example, a backend acts as an OAuth2 Client when calling an external API, yet acts as a Resource Server when it exposes its own API accepting bearer tokens.

## 3. Learning Track Selection Table by Problem

| Practical need | Learn first | Spring Security feature |
| --- | --- | --- |
| “Sign in with corporate account” for a web app | OIDC Authorization Code, redirects, sessions, PKCE | `oauth2Login` and `ClientRegistration` |
| Web app calling an API on a user's behalf | OAuth2 Client, scopes, token refresh | `oauth2Client` and `OAuth2AuthorizedClientManager` |
| Backend protecting a REST API receiving Bearer tokens | OAuth2 Resource Server, JWT/opaque tokens, issuer, audience | `oauth2ResourceServer` |
| Service A calling Service B with no user | Client Credentials, application acts as principal | OAuth2 Client with `client_credentials` |
| Two organizations needing federated login | OIDC/SAML federation, trust, account linking | OIDC Login or SAML2 depending on provider |
| Issuing tokens yourself and managing clients/consent | Authorization Server, signing keys, token policies | Dedicated Authorization Server/IdP system |

**Decision point:** logging in users, calling APIs, and issuing tokens are three distinct responsibilities. Pick the matching feature and avoid rolling your own token issuer or custom redirect handling unless genuinely required.

## 4. The OIDC Authorization Code + PKCE Flow

Suppose a Spring Boot Servlet application wants to log in with a company IdP:

1. The user visits a protected page requiring login. The app prepares an authorization request containing `client_id`, `redirect_uri`, `scope=openid ...`, `state`, and related parameters.
2. The browser is redirected to the Authorization Endpoint. The user authenticates **at the IdP**; the app never sees their password.
3. The IdP redirects back to the registered callback URI with an authorization **code** and `state`.
4. The backend validates binding to the original request and exchanges the code for tokens at the Token Endpoint. With PKCE, `code_verifier` must match the previously submitted `code_challenge`.
5. For OIDC, the client validates the ID token per the OIDC contract, including signature, issuer (`iss`), audience (`aud`), expiration, and `nonce` where applicable.
6. The application creates a local session or appropriate login-persistence mechanism; Spring Security then runs **authorization** for application requests and resources.

```text
Browser              Spring Boot (RP / OAuth2 Client)             OIDC Provider
    |--- GET /private -------->|                                  |
    |<------- redirect --------|                                  |
    |---------------------- authorization request ---------------->|
    |<--------------------- login / consent -----------------------|
    |-------- callback + code ->|                                  |
    |                           |---- code + PKCE verifier ------->|
    |                           |<---------- tokens ---------------|
    |<------ app session -------|                                  |
    |--- GET /private --------->|-- app authorization rules ------>|
```

This is a conceptual diagram, omitting some requests and cookies. Never place a client secret in the browser.

### Why Are These Protections Needed?

- **`state`:** binds the callback to the initial request, mitigating CSRF and session mix-ups in the OAuth2 flow.
- **`nonce`:** binds the ID token to the specific OIDC authentication attempt, mitigating token replay in flows using nonce.
- **PKCE:** binds the authorization code to the client that initiated the flow via `code_verifier`. Essential for public clients; worth considering for confidential clients too if the IdP supports it.
- **Redirect URI:** must be registered and matched strictly; never accept arbitrary user-supplied redirect targets.

Details such as `state`, PKCE, and ID token validation should be handled by a trusted OIDC/OAuth2 library. Simply exchanging a code and storing tokens ad hoc does not complete a secure login flow.

## 5. Distinguishing Access, ID, and Refresh Tokens

| Token | Who uses it? | Meaning |
| --- | --- | --- |
| **Access token** | API/Resource Server targeted by audience | Permission to access resources, lifetime, and scopes; may be JWT or opaque |
| **ID token** | OIDC Client/Relying Party | Result of user identity authentication; **do not** use instead of an access token to call APIs |
| **Refresh token** | Authorized confidential/permitted Client | Obtains new access tokens; protect and rotate/revoke per policy |

**JWT is a token format**, not another name for OAuth2 or OIDC. A JWT typically contains claims such as:

- `iss`: issuer; must belong to a trusted issuer.
- `sub`: subject identifier within the issuer's context.
- `aud`: intended recipient(s) of the token; the API must check the token is meant for it.
- `exp`, `nbf`: time validity bounds.
- `scope`/`scp`: granted permissions, claim name varies by IdP.
- `nonce`: binds the OIDC request when nonce is used.

**Base64URL decoding does not equal token verification.** APIs must verify signature or introspection, issuer, timestamps, audience, and policy permissions. A logged-in account does not automatically hold business permissions either: `Authentication` only says who was authenticated, while `Authorization` decides what they may do.

## 6. Example A: OIDC Login for a Spring Boot Servlet Application

This example is **configuration inside an existing Spring Boot application**, suitable for learning with Java 17+. It depends on Spring Boot/Spring Security, not a standalone Java file compiled with `javac`; it has no fixed stdout. Choose dependency versions matching your project.

With Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

`application.yml` for an IdP supporting OIDC Discovery:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope: openid, profile, email
        provider:
          corp:
            issuer-uri: "https://idp.example.org/realms/company"
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

- `registration.corp` is a client registration; `provider.corp.issuer-uri` lets the framework discover OIDC metadata, endpoints, and public keys.
- `oauth2Login` uses Authorization Code. The default initiation endpoint is typically `/oauth2/authorization/corp`; the callback is typically `/login/oauth2/code/corp`. The callback must be registered accurately at the IdP.
- `authorizeHttpRequests` still controls access to **application** resources, independently of the IdP having authenticated the user.
- `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` values come from environment variables or a secret manager; the example hostname must be replaced with the real issuer. Never commit secrets.
- For browser login using sessions/cookies, keep appropriate CSRF and cookie security controls; never disable them just for a demo.

With a valid test IdP, run the Boot app, open a protected route, and verify redirect → IdP → callback → local session. Successful login alone is not enough: test an endpoint requiring a permission the user **lacks** to verify post-login authorization.

## 7. Example B: Resource Server for an API Receiving JWTs

This is **a separate API application** illustrating a Resource Server. Add the dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Configure the API to trust the issuer providing metadata and JWT verification keys:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.org/realms/company"
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Meaning:

- Resource Server processes the `Authorization: Bearer <access-token>` header; verifies the JWT against the issuer's public keys/metadata and configured security constraints.
- Scope `reports.read` is mapped to authority `SCOPE_reports.read` under the appropriate default JWT scope converter. Check the exact claim emitted by your real IdP.
- Missing, expired, or invalid tokens typically result in **HTTP 401**; valid tokens lacking the required authority typically result in **HTTP 403**.
- **The API's audience (`aud`) must be checked/configured as required**, rather than assuming every JWT from the same issuer is intended for this API. Consider adding specific validators per project policy.
- The example shows security only; you need a Boot app, controllers, and a real issuer/token to run it. For stateless APIs using only bearer tokens, evaluate CSRF against your credential model and threat model before altering configuration.

If the API receives **opaque tokens**, learn token introspection instead of direct JWT verification. If the application needs to **obtain tokens itself to call other APIs**, that is the OAuth2 Client role, not a Resource Server feature.

## 8. OAuth2 Client, Client Credentials, and Calling APIs

When a backend needs to call an API on a user's behalf, learn `authorization_code`, authorized client management, and refresh tokens. Spring Security provides `OAuth2AuthorizedClientManager` and integrates with HTTP clients such as `RestClient`/`WebClient` depending on the stack.

Conversely, for service-to-service communication without a user, `client_credentials` yields a token representing the **application**. Never use a service-to-service token as proof that a specific end user authorized an action. Token permissions should follow least privilege, and APIs must clearly distinguish an application principal from a user principal.

A sensible hands-on sequence: acquire a token with the right grant → call a test API → test a denied scope request → test token expiry/refresh → revoke credentials → inspect logs and retry logic to ensure tokens are never leaked.

## 9. When Is Identity Federation Needed?

Identity federation models commonly arise in organizations with multiple IdPs, partners, or tenants:

```text
User
    |
Application / Relying Party
    |
    | OIDC or SAML over configured trust
    v
IdP / Identity Broker
    |-- Employee Directory
    |-- Partner IdP
    |-- Other Tenant IdP
```

You must design **trust and account relationships** beyond callback configuration:

1. **Identity source:** which organization authenticates users, enforces MFA policy, and disables departing employees?
2. **Account linking key:** with OIDC, use a stable identifier such as the `(iss, sub)` pair. Emails can change, be reused, or be unverified, so never merge accounts across two issuers automatically by email alone.
3. **Tenant-level authorization:** group/role claims from the IdP are inputs; the application must define which groups are trusted and which business permissions apply.
4. **Account/session lifecycle:** offboarding, revocation, logout, timeouts, and auditing still require explicit design; SSO does not automatically revoke every session across every app instantaneously.
5. **Data sharing:** request only necessary claims, limit retention, and check privacy requirements.
6. **Provisioning:** synchronizing user/directory lifecycles (possibly via SCIM) is a separate problem from login federation.

If a provider only supports SAML, use the appropriate SAML integration or a managed identity broker; do not try to force every federation scenario into an `oauth2Login` configuration.

## 10. Common Mistakes and How to Verify Yourself

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Using an access token as an ID token | Confusing API authorization with user authentication | Use OIDC and ID tokens for identity |
| Sending an ID token to a REST API | Wrong token recipient | APIs accept access tokens targeted at the API |
| Decoding a JWT without verifying it | Trusting forged/expired/wrong-issuer tokens | Verify signature, issuer, timestamps, audience, and policy |
| Trusting email/group directly as admin | Wrong user linking or privilege escalation | Map identities and authorities by issuer, tenant, and policy |
| Omitting state/nonce/PKCE, overly broad redirect URIs | Elevated replay and code interception risk | Use standard flows/frameworks and strict URIs |
| Storing secrets/refresh tokens in frontend, URLs, or logs | Credential leakage | Backend/secret stores, log filtering, rotation |
| Using Client Credentials instead of user delegation | Loss of user context and consent | Use the appropriate grant |
| Assuming OIDC Login grants all permissions | Missing business authorization | Enforce authorization at endpoints and domain layer |
| Running your own Authorization Server when you only need SSO | Higher risk around signing keys, tokens, consent, and ops | Use a dedicated IdP/Authorization Server when appropriate |

**Minimum verification test suite:**

- **Web OIDC:** unauthenticated users redirect to the IdP; valid callbacks succeed; callbacks with invalid state are rejected; logged-in users lacking permissions cannot access restricted resources.
- **API:** missing token → 401; invalid/expired/wrong-issuer token → 401; valid token missing scope → 403; valid token with right audience + scope → permitted. To verify audience properly, configure an audience validator for the API.
- **Federation:** users from untrusted IdPs are rejected; matching emails across two issuers do not auto-merge accounts; disabled accounts cannot obtain fresh access; tenant policies are enforced.

## 11. Recommended Next Learning Path

1. **Review fundamentals:** `Authentication`, `SecurityContext`, `GrantedAuthority`, sessions, CSRF, API protection, and HTTP 401/403.
2. **Pick the right roles:** diagram Client → Authorization Server/OP → Resource Server and label which token goes to which component.
3. **Go deep only on the matching track:** OIDC Login for web login; OAuth2 Client for calling APIs; Resource Server for APIs accepting bearer tokens; federation when cross-org trust is needed.
4. **Stand up a test environment:** test IdP, valid redirect URIs, credentials outside source code, one public route, and one authority-protected route.
5. **Test failure paths too:** expiry, wrong issuer/audience, missing scopes, logout, and offboarding; successful authentication does not prove authorization is correct.
6. **Then advance further:** custom claim mapping, multi-tenant issuers, refresh/revocation, account linking, token exchange, SAML, or running an Authorization Server if the problem demands it.

**Mastery criteria:** you can explain “OAuth2 grants authorization, OIDC authenticates identity, federation establishes trust”; pick `oauth2Login`/`oauth2Client`/`oauth2ResourceServer` accurately; distinguish access/ID/refresh tokens; and verify that an API rejects invalid tokens rather than testing only the happy path.

## 12. Authoritative Reference Documentation

Choose documentation matching the exact **Spring Boot/Spring Security version** your project uses; APIs and defaults can change across releases.

- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot — OAuth2](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [OpenID Foundation — How OpenID Connect Works](https://openid.net/developers/how-connect-works/)

**Guidance:** learn these standards as real requirements demand, while keeping access-control responsibility inside the application. SSO or a valid token never replaces business permission checks and data protection.
