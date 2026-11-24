# Prerequisite Knowledge and Learning Path: From Trust Models to SSO Integration

> **Context:** Spring Security – federation / Federation Overview. This lesson is for developers who already know Java application development and want to understand why an application can trust an identity authenticated by another system, and then implement Single Sign-On (SSO) properly. Practical examples use a **Spring MVC/Servlet** application, Java 17, and Spring Boot 3.5.x (Spring Security 6.x).

## 1. Learning Outcomes

After this lesson, the learner will be able to:

1. Draw the **trust boundaries** among the user, browser, application, Identity Provider (IdP), and APIs.
2. Distinguish **federation, SSO, OAuth 2.0, OpenID Connect (OIDC), and SAML 2.0**; choose the right protocol for login versus API access.
3. Explain how an application trusts an identity message based on **issuer, audience, signature, verification keys, validity, session state, and registered configuration**, rather than trusting a parameter sent by the browser.
4. Trace the OIDC Authorization Code flow and SAML Web Browser SSO; recognize anti-forgery and anti-replay requirements.
5. Configure a Spring Security application as an **OIDC Relying Party (OAuth2 Client)**, test sign-in via an IdP, and know where to configure SAML 2.0 or a Resource Server when expanding.
6. Plan testing, troubleshooting, and hardening for SSO integration before going to production.

## 2. Background Knowledge Needed Before Studying Federation

| Area | What to Know | Why It Is Needed |
| --- | --- | --- |
| Java/Spring | Java 17+, Maven/Gradle, Spring Boot, YAML config, Beans, Spring MVC | Read and run `SecurityFilterChain` configs and test endpoints |
| Spring Security | `Authentication`, `SecurityContext`, `GrantedAuthority`, `SecurityFilterChain`, `authenticated()`/`hasAuthority()` rules | Separate **authenticated** from **authorized to access** |
| HTTP and browsers | HTTPS, 302 Redirect, GET/POST, cookies, `SameSite`, server sessions, callback URLs | Understand why login involves multiple redirects between app and IdP |
| Web security | CSRF, XSS, session fixation, secret protection, reverse proxies | Avoid bypassing defenses just because SSO is used |
| Basic cryptography | Public/private keys, digital signatures, X.509 certificates, JWT, JWKS, expiration | Distinguish **issuer verification** from **decoding**, knowing when a token/assertion is trustworthy |
| System architecture | Domains, DNS, tenants, dev/test/prod environments, user management | Design trust targets and callback paths accurately per environment |

**Self-check:** If `GET /orders` arrives while unauthenticated, explain why Spring Security blocks the request, sends the user to authenticate, and creates `Authentication` after the callback. If you cannot explain this yet, review the Spring Security filter chain, sessions, and CSRF before configuring an IdP.

## 3. Trust Model: Starting with "Who Trusts Whom?"

**Identity federation** is a technical and administrative agreement allowing one system to use identity authentication results from another system. **SSO** is the experience where users can access multiple applications without usually signing in again while the IdP session remains valid. Federation is the mechanism that establishes trust; SSO is a capability often built on top of that mechanism. Signing in once at the IdP does not mean every application automatically has permission to view every resource.

Actors:

- **End user / User Agent:** the user and browser traversing redirects. The browser is a data transport medium, **not an identity certification authority**.
- **Identity Provider (IdP):** where credentials, MFA policies, access conditions, and authentication info are verified and issued. In OIDC, commonly called **OpenID Provider (OP)**; in SAML, called **Asserting Party/IdP**.
- **Relying application:** **Relying Party (RP)** in OIDC, or **Service Provider (SP)** in SAML. Spring Security plays this role when `oauth2Login()` or `saml2Login()` is enabled.
- **Authorization Server (AS):** issues OAuth 2.0 access tokens. Often the same product as the IdP, though functionally not required to be the same component.
- **Resource Server (RS):** an API accepting access tokens and enforcing resource access permissions; typically configured with `oauth2ResourceServer()`.

**Minimum trust path:**

```text
User ──browser/redirect──> Application RP/SP
  │                                │
  └──sign in/MFA at IdP/OP<────────┘
                                   │
                    RP verifies result issued by IdP
                                   │
                        Creates application session
                                   │
                     Enforces resource permissions

API Resource Server <── access token from client ──> API caller
        │
        └── independently verifies access token for the API
```

The application and IdP must have **pre-configured trust relationships**: exact issuer/entity ID addresses, client/SP registration, registered redirect/ACS URLs, trusted keys or metadata, and user mapping rules. HTTPS protects transport, but **HTTPS alone does not confirm a token was issued for the right application**.

### Login, Authorization, and Resources Are Three Different Problems

| Technology | Primary Role | Core Data | What Not to Assume |
| --- | --- | --- | --- |
| OAuth 2.0 | Grants resource access between client and authorization server | Authorization code, access token, scope | OAuth 2.0 itself is **not** a user identity authentication protocol |
| OIDC (built on OAuth 2.0) | Standardized identity login | **ID Token**, `iss`, `sub`, `aud`, optionally UserInfo | ID Token is **not** an access token to call APIs |
| SAML 2.0 Web Browser SSO | Federated login common in enterprises | SAML `AuthnRequest`, `Response`, `Assertion`, XML signature | Assertions are not JWTs; validation and endpoints differ from OIDC |
| Spring Security session | Records login state **in the application** | `SecurityContext`, session cookie | Having an app session does not guarantee the IdP session still exists |
| OAuth2 Resource Server | Protects APIs with access tokens | JWT or opaque token | APIs should not accept an ID Token just because its signature is valid |

**Example:** A company uses one IdP for the employee portal and the reporting system. Both RPs are registered with the same IdP. An employee authenticates at the IdP when entering the portal; when opening reports, the browser redirects to the IdP and can receive a fast login result because the IdP session is active. Even so, reports must still enforce its own role policy; an employee is not automatically allowed to view financial reports.

## 4. Conditions That Make "Trust" Verifiable

1. **Valid issuer:** OIDC/JWT verifies `iss` matches the configured issuer; SAML verifies the IdP entity ID. Never use an issuer suggested by the token itself to dynamically add a new provider to the trust list.
2. **Correct recipient:** OIDC ID Token has `aud` containing the RP's `client_id`; API access tokens must match the API's audience; SAML Assertions have audience/recipient matching the SP.
3. **Integrity and signing source:** verify signatures using trusted keys of the corresponding issuer (OIDC uses JWKS/metadata; SAML uses certificates in metadata). Reject unsigned tokens, disallowed algorithms, or keys fetched arbitrarily from untrusted content.
4. **Correct context and time:** check `exp`, `nbf` when applicable, and reasonable clock skew; OIDC Authorization Code uses `state`, `nonce` when appropriate, and PKCE; SAML validates `InResponseTo`, `Destination`, `SubjectConfirmationData`, time conditions, and replay protection matching the profile/flow.
5. **Exact return address:** OIDC redirect URI must match configuration at the OP; SAML ACS/entity ID must match metadata at the IdP. Never build redirects from an unvalidated `returnUrl` parameter.
6. **User identity and mapping:** with OIDC, the durable identifier key is usually the **(`iss`, `sub`)** pair; do not default to email as the primary key because emails can change or be reassigned. With SAML, choose NameID/attributes per agreed data contract.
7. **Application permissions:** group/role mapping must have a trusted source, least privilege by default, and tenant control. **A successful sign-in does not automatically grant ADMIN permissions.**

Two separate boundaries must be drawn: (a) **IdP → RP:** RP verifies identity and establishes a session; (b) **AS → Resource Server:** API verifies access tokens intended for it. They may share an issuer while having **different verification targets**.

## 5. Learn the OIDC Flow First: Authorization Code and App Login

For server-side web applications with interactive login:

1. **Registration:** RP has `client_id`, client authentication method (e.g., securely stored secret), redirect URI set, `issuer-uri`, and scopes including `openid`. OP publishes discovery metadata and JWKS.
2. **Initiation:** user visits a protected page. RP redirects the browser to the authorization endpoint with `response_type=code`, `client_id`, `redirect_uri`, scope, `state`, and depending on config `nonce`/PKCE.
3. **IdP authenticates:** OP performs login, MFA, consent, or reuses an SSO session. RP **never receives the password** from the OP's login screen.
4. **Callback:** OP returns the browser to the registered URI with an authorization code and state. RP matches state against the pending transaction, rejecting callbacks not tied to a valid request.
5. **Token exchange:** RP backend sends the code to the token endpoint over a protected channel; with PKCE, sends `code_verifier`, and authenticates the client per registration. RP receives an ID Token, typically alongside an access token.
6. **Validation and session:** RP verifies the ID Token (issuer, audience, signature, expiration, nonce when applicable), obtains `sub`, maps account/permissions, and creates `Authentication` and the application login session.
7. **API access:** if the app calls an API, it uses an **access token appropriate for the API**, per granted scopes/audience and authorization. The API has independent token validation and permission checks.

```text
Browser            RP (Spring Security)         OIDC Provider
  | GET /me                |                         |
  |----------------------->|                         |
  |<--- 302 authorize -----|                         |
  |------------ authorization request ------------->|
  |<----------- login / MFA / code -----------------|
  | GET callback?code=...  |                         |
  |----------------------->|--- POST token(code) --->|
  |                        |<-- ID/access tokens ----|
  |                        |-- validate ID token    |
  |<-- session cookie -----|                         |
  | GET /me + cookie       |                         |
  |----------------------->|                         |
  |<-- app returns data ---|                         |
```

**Inspecting in DevTools:** watch the URLs `/oauth2/authorization/{registrationId}`, the OP's authorization endpoint, and `/login/oauth2/code/{registrationId}`; inspect HTTP statuses and cookies. Never log or share codes, access tokens, ID Tokens, session cookies, or client secrets. `state` correlates requests/responses and prevents login CSRF; PKCE binds the code to the initiator. Public clients must use PKCE; confidential clients should also use it when supported by the provider.

## 6. Place Alongside SAML 2.0 to See Commonalities and Differences

In **SP-initiated SAML Web Browser SSO**:

1. SP and IdP exchange metadata containing **entity ID**, SSO endpoints, **Assertion Consumer Service (ACS)**, and verification certificates/keys; both sides configure the trust relationship.
2. When a user accesses a protected resource, SP generates an `AuthnRequest` and redirects the browser to the IdP.
3. IdP authenticates and sends a **SAML Response/Assertion** via the browser, typically using HTTP POST to the SP's ACS.
4. SP verifies valid signature on the Response or Assertion per configured requirements, issuer, audience, recipient/destination, `InResponseTo` if preceded by a request, time conditions, and replay protection.
5. SP maps NameID/attributes to an account and `Authentication`, then establishes an application session.

In Spring Security, **RP/SP is configured via `RelyingPartyRegistration`**, using `saml2Login()`. The default flow typically starts at `/saml2/authenticate/{registrationId}`; ACS handles `POST /login/saml2/sso/{registrationId}`. `saml2Metadata()` can publish metadata to register the SP at the IdP. With SAML, it is especially important to understand **XML signatures, certificate rotation, request correlation, Assertion conditions, and IdP-initiated flows**, which are harder to correlate to transactions than SP-initiated flows.

**Pragmatic comparison:** OIDC is usually more convenient for modern web/mobile applications and the OAuth API ecosystem; SAML is common in legacy enterprise integrations. Both support SSO, while message formats, callback mechanisms, verification keys, and logout operations differ. Choose based on IdP and organizational requirements, not merely protocol familiarity.

## 7. Ordered Learning Sequence and Completion Criteria

| Stage | Study and Practice | Evidence of Understanding |
| --- | --- | --- |
| 1. Foundations | Protect `/me` with Spring Security; distinguish 302/401/403, sessions, CSRF, and authorities | Can trace request → filter → `Authentication` → authorization |
| 2. Trust boundaries | Draw User–Browser–RP–OP–API diagram; list issuer, audience, redirect, keys, tenant | Can point out who signs, who verifies, and which token is for whom |
| 3. Protocols | Study OAuth2 Authorization Code, OIDC ID Token/JWKS; compare SAML Request/Response/Assertion | Never confuses ID Token with access token or SAML Assertion |
| 4. IdP setup | Create a test tenant/realm, OIDC client, callback, test user, and MFA config if available | Has exact issuer URL, client registration, and test user |
| 5. Spring OIDC Login | Add `spring-boot-starter-oauth2-client`, `oauth2Login()`, configure issuer/secret via env vars | Accessing `/me` requires login; after callback receives exact `iss` and `sub` |
| 6. Identity & roles | Map (`iss`, `sub`) to internal user, tenant policy, backend authorities | User lacking role still gets 403 on restricted endpoints |
| 7. API protection | Add Resource Server on **API service**; verify access token, `iss`, `aud`, expiration, scope | Right API access token succeeds; ID Token or wrong-API token is rejected |
| 8. SAML comparison | Try SP registration, metadata, ACS, signature, and attribute mapping if IdP supports SAML | Can draw SAML flow and explain differences from OIDC |
| 9. Production readiness | Error & security testing, key/secret rotation, logout handling, TLS/proxy, auditing | Has negative test matrix, key rotation runbook, and rollback plan |

**Recommended order:** complete stages 1–5 before expanding to multiple IdPs or SAML; stages 6–7 are mandatory if the application needs real authorization and API calls. Learners already experienced with OIDC may do stage 8 earlier, without skipping trust verification.

## 8. Minimal OIDC Login Practice with Java 17

This is an illustrative **Spring MVC (Servlet)** application using Spring Boot **3.5.0**. The example compiles when Java 17, Maven, and **a real OIDC Provider** with valid issuer, client ID/secret, and redirect URI are present. It does not perform sign-in without an IdP configured; environment variables are required.

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>sso-practice</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email
        provider:
          corporate:
            issuer-uri: ${OIDC_ISSUER_URI}
```

**File `src/main/java/demo/sso/SsoApplication.java`:**

```java
package demo.sso;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SsoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoEndpoints {
    @GetMapping("/")
    String index() {
        return "Open /me to sign in with OIDC";
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "issuer", user.getIdToken().getIssuer().toString(),
                "subject", user.getIdToken().getSubject());
    }
}
```

**IdP preparation:** create an OIDC **confidential web client**, register the exact callback `http://localhost:8080/login/oauth2/code/corporate`, grant `openid` (plus `profile`, `email` if policy allows), and obtain `client_id`, secret, and issuer URL. With Keycloak, the issuer takes the form `http(s)://<host>/realms/<realm>`; use the actual path/host published by the IdP and ensure an exact `iss` match. In real environments, use HTTPS for the callback.

**Example run on Unix/macOS terminal** (replace values with test credentials, never commit secrets):

```bash
export OIDC_ISSUER_URI='https://idp.example.org/realms/demo'
export OIDC_CLIENT_ID='my-web-client'
export OIDC_CLIENT_SECRET='replace-with-real-secret'
mvn spring-boot:run
```

On PowerShell, set `$env:OIDC_ISSUER_URI`, `$env:OIDC_CLIENT_ID`, and `$env:OIDC_CLIENT_SECRET` accordingly before running Maven. **The domains/secrets above are illustrative only**: a real issuer and client are needed to sign in.

Open `http://localhost:8080/` to test the public endpoint; open `http://localhost:8080/me` or `http://localhost:8080/oauth2/authorization/corporate` to start sign-in. After successful authentication, `/me` returns JSON with the **issuer** and **subject** of the verified ID Token, e.g., shaped like `{"issuer":"https://...","subject":"..."}`. Specific values are issued by the IdP so there is no fixed stdout. Without a session, the browser may see a login selection page before redirecting to the OP. This sample **does not yet implement business authorization, internal accounts, or federated logout**.

**Code explanation:** `spring-boot-starter-oauth2-client` provides the OIDC/OAuth2 client; `issuer-uri` enables endpoint and key discovery from metadata; `oauth2Login()` integrates the login flow and establishes `Authentication`; `SecurityFilterChain` exposes only `/` and `/error`, while `/me` requires authentication. `OidcUser` represents the principal after login; the ID Token in the example is used only to read identity at the RP, **not sent as a bearer token to APIs**.

**When adding a separate API:** the API needs `spring-boot-starter-oauth2-resource-server`, configuring JWT with the **API's** issuer and audience, for example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
          audiences: api://orders
```

This YAML snippet describes **configuration for a Resource Server API service**, rather than adding directly to the Login sample above and assuming every endpoint is protected by Bearer Tokens. The API needs an appropriate filter chain, `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` or compatible default configuration, and authorization rules per its scopes/roles. For opaque access tokens, use introspection instead of JWT decoding.

## 9. If SAML Integration Is Required Instead of OIDC

The mindset from sections 3–4 remains the same, while switching to **SP/Relying Party** configuration in Spring Security:

1. Add dependency `spring-security-saml2-service-provider` and configure `RelyingPartyRegistration`/IdP metadata.
2. At the IdP, declare the **SP entity ID**, **ACS URL**, and SP signing certificate if required by policy.
3. In `SecurityFilterChain`, use `saml2Login(Customizer.withDefaults())` (alongside appropriate access rules).
4. Test the `AuthnRequest` → `SAMLResponse` → ACS flow; ensure signatures and Assertion conditions are verified before creating a session.
5. Map SAML NameID/attributes to internal identity per contract; test both certificate rotation and IdP downtime.

**Do not copy OIDC parameters over to SAML:** OIDC has `client_id`, redirect URI, JWKS/ID Token; SAML has SP/IdP entity ID, ACS, XML metadata, and X.509 signatures. If the IdP requires signed requests or encrypted Assertions, corresponding signing/decryption credentials must be provided. For SAML, prefer configuration via managed, change-controlled metadata rather than pasting certificates manually in multiple places.

## 10. Test Matrix Before Calling It "Working SSO"

| Scenario | Expected Behavior |
| --- | --- |
| Unauthenticated user visits protected page | Redirects to login flow; session created only after success |
| Valid login at OP/IdP | Valid ID Token/Assertion, accurate identity, application session established |
| Issuer/entity ID not on trusted list | Authentication rejected |
| Invalid signature, untrusted key, or expired token/assertion | Authentication rejected |
| ID Token with wrong `aud`, access token for another API, missing scope | Rejected at the corresponding recipient |
| OIDC callback with wrong `state`, reused code, wrong PKCE | Login fails to complete |
| Replayed SAML Response/Assertion, wrong audience/recipient or correlation | Session not created |
| User logged in but lacks business permission | Returns 403 on restricted resource; never self-elevates |
| One user using multiple IdPs/tenants | Identities are not conflated; (`iss`, `sub`) and tenant verified |
| Key/certificate rotated | Only valid keys accepted per rotation schedule; metadata update and rollback plan ready |
| OP/IdP temporarily down or callback error | Clear error, verification never bypassed, no invalid session created |
| App logout / IdP logout | Clearly specifies which sessions are cleared and SLO/front-channel/back-channel support per protocol and IdP |

**Manual verification approach:** inspect secret-redacted network traces, selective Spring Security debug logs, registration config at the OP, and session state after callback; cross-check issuer/audience with metadata. Perform negative testing in a test environment; never tamper with token signatures or send test payloads to production services.

## 11. Common Errors and How to Reason About Them

- **`redirect_uri_mismatch`:** actual callback differs from registered URI (scheme/host/port/path or reverse proxy). Compare the actual value from the authorization request with the IdP client registration; configure trusted forwarded headers properly and never trust `X-Forwarded-*` from external clients.
- **`invalid_client` or token endpoint error:** wrong client ID/secret, client auth method, or rotated secret; check in the secret store, never print secrets to logs.
- **`invalid_issuer`, audience mismatch, or signature invalid:** wrong realm/tenant, wrong `issuer-uri`, mismatched JWKS, clock skew, or newly rotated key. Never "quick fix" by disabling verification.
- **Logged in yet getting 403:** authentication succeeded, but the app did not map roles/authorities or the token lacks scopes; fix rules and mapping sources deliberately rather than granting broad access.
- **Login loop:** session cookie not returned, mismatched `SameSite`/`Secure`, proxy wrong scheme, multiple instances not sharing sessions, or callback unable to restore the saved request; inspect cookies and the redirect chain.
- **Using an ID Token to call an API:** Resource Server receives the wrong token type or audience; send an access token issued for the API and validate `aud`/scope at the API.
- **Confusing local logout and Single Logout:** clearing the RP session does not necessarily end the IdP session; design OIDC RP-Initiated Logout/SAML SLO if business truly requires it and the IdP supports it.
- **SAML invalid response:** wrong ACS, entity ID, certificate, Assertion timestamps, recipient, signature, or `InResponseTo`; cross-check metadata on both sides and sanitized logs.

## 12. Closing Exercises and Passing Criteria

**Exercise A – design:** Given two applications `portal.example.org` and `reports.example.org` sharing one IdP, draw the login flow for both; mark clearly where the IdP session can be reused and where each RP must verify the message, establish a session, and enforce authorization itself. Explain why SSO does not prove permission to view reports.

**Exercise B – integration:** Run the application in section 8 with a test OIDC Provider. Record the issuer, `client_id`, callback, and redirect steps (without storing tokens or secrets). Visit `/me` in a fresh browser and prove `iss`/`sub` appear only after login finishes.

**Exercise C – security testing:** Try a wrong callback registration and an unconfigured issuer; observe login failing. Add an endpoint requiring an authority the user lacks and verify receiving 403 after login. Explain why an API must verify `aud` even when an ID Token has a valid signature.

**Pass criteria:** able to fully explain **who issues → who verifies → trust evidence → who creates session → who checks permissions** for both OIDC and SAML; able to run a real OIDC login in a test environment; and able to present at least five authentication or authorization rejection scenarios. This lays the foundation for advanced federation topics: multiple IdPs, tenant routing, provisioning/SCIM, step-up MFA, account linking, and session lifecycles.

## Official Reference Sources

- Spring Security – OAuth2 Login Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Client Authorization Grants/PKCE: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OpenID Connect Core 1.0 – ID Token Validation: https://openid.net/specs/openid-connect-core-1_0.html
