# Choosing an SSO Protocol for Web Applications, Intranets, and Partners

**Context:** Spring Security – federation → SSO Protocols. The goal is to choose a federated login protocol suited to the application type, identity infrastructure, and trust boundaries, while knowing how to implement and verify that choice in the Spring Security ecosystem.

## 1. Distinguish SSO, Federation, Authentication, and Authorization

- **SSO (Single Sign-On)**: a user already logged into an identity system can access multiple applications within the same identity session without re-entering a password each time. SSO does not mean all applications share the same cookie or the same logout session.
- **Federation**: an application trusts authentication evidence issued by another organization or identity system. For example, a partner portal trusts a partner enterprise's IdP under a technical agreement.
- **IdP/OP (Identity Provider/OpenID Provider)**: the component that authenticates users and issues login evidence. **RP/client** in OIDC is the application consuming the identity; **SP/RP** in SAML is the application receiving assertions.
- **Authentication** determines who the user is; **authorization** decides what operations they are allowed to perform. Successful login does not automatically grant admin privileges.
- **OAuth 2.0** is a resource access authorization framework; OAuth 2.0 itself **does not define a user authentication standard**. **OpenID Connect (OIDC)** adds the identity layer on top of OAuth 2.0, including ID Tokens and validation rules.
- **LDAP/Active Directory** is a directory/identity service, not a web SSO protocol equivalent to OIDC or SAML. **SCIM** supports account provisioning/deprovisioning, and does not replace a login flow.

Two flows must be distinguished: **a user logging into a web app** (OIDC/SAML/Kerberos) and **a service calling an API** (typically an OAuth 2.0 access token). Do not take an OIDC ID Token as a Bearer token for an API merely because both are JWTs.

## 2. Protocol Selection Matrix by Environment

| Scenario | Default choice | Why | When to switch approach |
| --- | --- | --- | --- |
| Modern web serving employees/customers; Spring Boot apps | **OIDC – Authorization Code**, using PKCE per client type and security policy | Fits web, mobile, APIs, with discovery/JWKS and standard claims | IdP mandates SAML or legacy apps only support SAML |
| Browser-based SPA with a backend | **OIDC Code + PKCE**; prefer the **BFF** pattern when possible to keep tokens on the server | Limits tokens residing in JavaScript and simplifies session management | Pure SPA without a backend: public client + PKCE, carefully evaluate token storage |
| Internal app strictly for domain-joined Windows machines on an intranet | **Kerberos over HTTP Negotiate/SPNEGO** if infrastructure exists and is maintainable | Leverages Windows login tickets; passwordless experience | Non-domain devices, mobile, Internet, or multiple IdPs: use OIDC via an IdP/broker connected to AD |
| Multi-device, hybrid, VPN/Internet internal portal | **OIDC with enterprise IdP**; the IdP can use AD/Kerberos behind the scenes | Decouples apps from keytabs, domain join, and browser policies | Use Kerberos directly only in a closed scope where SPNEGO conditions are stable |
| B2B partner requiring SAML 2.0, e.g. traditional enterprise IdP | **SAML 2.0 Web Browser SSO** | Compatible with partner metadata, certificate, and assertion contracts | If both sides support OIDC and SAML is not mandated, consider OIDC to simplify modern web integration |
| B2B partner supporting OIDC | **OIDC Code** with per-partner issuer/client configuration | Leverages JSON/JWT, discovery/JWKS, and clean API integration | Partner only publishes SAML metadata or requires a SAML flow |
| Backend calling backend with no user | **OAuth 2.0 Client Credentials** or appropriate workload identity mechanism | Machine authentication/authorization, **not user SSO** | If acting on behalf of a user, evaluate delegated access/token exchange rather than impersonating user accounts |
| Legacy app only understanding CAS or WS-Federation | Keep the protocol at an **identity broker/gateway** or plan an upgrade | Reduces the number of protocols new apps must implement directly | Integrate directly only when compatibility is required and maintained libraries exist |

**Selection principle:** partner IdP compatibility requirements and the user environment are the primary constraints; then balance security, device support, operability, certificate/key lifecycle, and login experience. No single protocol wins in every case.

## 3. Understand the Mechanisms Before Making a Decision

### 3.1. OIDC: Primary Choice for Web and Cross-Platform Systems

Typical flow using **Authorization Code**:

1. The user opens a login-protected resource on the RP (Spring application).
2. The RP redirects the browser to the OP's authorization endpoint with `client_id`, `redirect_uri`, `scope=openid`, `state`, and PKCE parameters if applicable; `nonce` is used per OIDC flow/policy.
3. The OP authenticates the user (via MFA, Windows SSO, or other methods) and redirects the browser back to the registered callback with an authorization code.
4. The RP exchanges the code for tokens over a server-to-server channel when acting as a confidential client, validates the ID Token, establishes the application session, and applies internal authorization policies.
5. When API calls are needed, the client/backend uses an **access token** intended for that API; the API validates the token independently in its resource server role.

OIDC provides the application with an identity based on `iss` (issuer), `sub` (subject), and verified claims. **The `(iss, sub)` pair** should be the durable federated identifier key; email or display name can change, be reused, or be unverified.

Core checks include trusted signature/algorithm, `iss`, `aud` containing `client_id`, `exp`/timestamps, `nonce` when sent, and transaction binding. `state` prevents request mix-ups and CSRF in redirects; PKCE binds the code to the issuing client. Never write a custom token validator by merely Base64-decoding a JWT.

**Choosing the right client type:** server-rendered Spring MVC apps are typically confidential clients; SPAs/mobile apps are public clients. Public clients must use PKCE; confidential clients should also use PKCE. With an SPA using a BFF, the browser holds an `HttpOnly; Secure; SameSite` session cookie while the BFF keeps tokens server-side and enforces CSRF protection on cookie-authenticated requests. Do not use implicit flow or Resource Owner Password Credentials for building new SSO.

### 3.2. SAML 2.0: Widely Adopted Assertion Exchange Standard in B2B

In **SAML Web Browser SSO**:

1. The SP generates an `AuthnRequest` (usually via browser redirect) to the IdP.
2. The IdP authenticates the user per enterprise policy.
3. The browser posts a `SAMLResponse` containing an XML assertion to the SP's **Assertion Consumer Service (ACS)**, usually via HTTP POST.
4. The SP validates the signature using the trusted IdP certificate, checks issuer, audience, recipient/destination, expiration, `InResponseTo` (for SP-initiated requests), and assertion conditions before creating a login session.

Its strength is long-standing compatibility with enterprise IdPs and federation contracts via XML/X.509 metadata. Its operational overhead lies in managing metadata, signing/encryption certificates, clock skew, bindings, payload sizes, and differing claims/NameIDs across partners.

**Do not confuse** the IdP's assertion-signing certificate with the endpoint's TLS certificate. A valid XML signature is necessary, yet must be verified over the exact assertion/response actually used for authentication to avoid XML signature wrapping risks. Especially never accept an assertion issued by a different tenant merely because the email matches.

### 3.3. Kerberos/SPNEGO: Machine-Login-Based Intranet SSO

With domain-joined machines and browsers supporting HTTP Negotiate:

1. The application requests authentication via `WWW-Authenticate: Negotiate`.
2. The browser obtains a Kerberos service ticket for the service's SPN, such as `HTTP/portal.corp.example@CORP.EXAMPLE`, from the KDC/AD.
3. The browser sends `Authorization: Negotiate ...`; the server validates the ticket with the corresponding service principal/keytab and maps the principal to application users/groups.
4. The application can create an HTTP session to enforce authorization like other login mechanisms.

Its advantage is seamless SSO on configured corporate devices. Its limitations are dependence on DNS, SPNs, clock synchronization, KDC reachability, browser/OS configuration, and keytab protection; it does not work out of the box for non-domain or off-network devices. HTTP Negotiate does not mean "sending the Windows password over the web." Verify that the negotiated mechanism is actually Kerberos per policy, and not silently falling back to NTLM unintentionally.

Spring offers the **Spring Security Kerberos extension** for SPNEGO; this integration has a different configuration and lifecycle from `oauth2Login` or `saml2Login`. Evaluate Spring version compatibility, browsers, and the AD environment before choosing direct deployment.

## 4. Making Decisions by Application Group

### 4.1. Public Web or Multi-Device Web

**Prefer OIDC** when the organization has a trusted OP/IdP supporting OIDC. Implement the Code flow, register exact redirect URIs, enable HTTPS, configure MFA/authentication policies at the IdP, and use Spring Security libraries for verification. For example: an order portal with a Spring Boot backend receives login from the IdP; the user can proceed to another system using the same IdP without re-entering credentials while the IdP session remains active.

With multiple frontends or SPAs, decide clearly who owns the session: (a) a BFF holding tokens while the browser only holds a session cookie, or (b) an SPA using an OAuth public client + PKCE and managing tokens/refresh per IdP capabilities. Option (a) usually makes token control easier when a backend exists; never put a client secret into a frontend bundle. Avoid disabling CSRF by default just because the app uses OIDC; cookie-session CSRF and redirect `state` solve related but not identical problems.

**SAML** fits when the web app must connect directly to an enterprise IdP that only provides SAML or when procurement contracts mandate SAML. Do not switch to SAML solely because the audience is "enterprise": protocol choice must follow actual capabilities, constraints, and operational cost.

### 4.2. Internal Web, Active Directory, and Windows Machines

- **Strictly domain-joined Windows devices, IT-managed browsers, stable intranet:** Kerberos/SPNEGO is a strong candidate. Prepare SPN/keytab, accurate DNS, Kerberos realm trust, NTP, HTTPS, and browser configuration for trusted domains. Test on both domain-joined and non-domain machines to verify fallback behavior.
- **Remote employees, macOS/Linux, mobile, multiple domains/IdPs:** use OIDC via an enterprise IdP. The IdP can leverage Kerberos inside the network for employee SSO while the application simply acts as an OIDC RP. This decouples web logic from KDC/keytabs and supports unified MFA/conditional access.
- **Legacy internal apps using LDAP Bind:** direct LDAP password authentication does not provide cross-application web SSO. You can migrate to an AD-connected IdP and use OIDC/SAML; keep LDAP group lookups only when genuinely needed and ensure secure connections.

Example: an inventory portal previously ran only on a Windows LAN, and now needs mobile access during business travel. Inputs have changed; consider IdP + OIDC instead of trying to extend SPNEGO directly to every client.

### 4.3. Portals for External Partners (B2B)

**Start from each partner's protocol contract, rather than forcing one rigid model on everyone.**

- If the partner only has **SAML**: exchange SP entity ID, ACS URL, metadata, IdP entity ID, SSO URL, and verification certificate; agree on AuthnRequest signing requirements, assertion encryption, NameID, and released attributes. Test both IdP-initiated (if permitted) and SP-initiated flows against replay/mix-up policies.
- If both sides have **OIDC**: use per-partner issuer and client registrations, register fixed redirect URIs, define scopes/claims, sign/rotate keys via JWKS, and manage client credentials securely. Never rely solely on an email domain to decide which IdP to trust.
- In a **multi-tenant** model, user identity must include both **tenant/issuer and a stable subject**; map to an internal organization before assigning permissions. Prevent a partner A account from logging into B's space when name/email claims collide.
- Agree on non-login aspects: JIT provisioning vs. SCIM, account deactivation on offboarding, session revocation, group/attribute changes, incident SLAs, default permissions, certificate/secret rotation, and technical contacts.

An **identity broker** fits when dealing with dozens of partners using heterogeneous protocols: each partner talks to the broker via its own OIDC/SAML connection, while Spring applications speak a single unified protocol (typically OIDC) with the broker. The broker is a concentrated risk point and requires verifying tenant/identity mapping, MFA policies, and the trustworthiness of each identity source.

### 4.4. APIs and Service-to-Service Communication

APIs use access tokens with the right audience (`aud`) and scopes/roles; services do not perform interactive login via SAML browser redirects. Spring Security **Resource Server** supports JWT Bearer; configuring an issuer alone is insufficient to prove a token was issued for the API—enforce the expected audience when required. For daemons/jobs, consider OAuth Client Credentials or workload identity. When an API acts on behalf of a user, design delegated authorization explicitly rather than treating an ID Token as an access token.

## 5. Applying in Spring Security (Servlet / Java 17+)

The configuration snippets below are **configuration fragments integrated into a Spring Boot project** that already has dependencies, controllers, and a real IdP—**not standalone Java programs run with `javac` or producing fixed stdout**. URIs use example domains; replace them with configuration provided by your IdP. If using WebFlux, choose the corresponding reactive DSL (`SecurityWebFilterChain`), rather than copying servlet `SecurityFilterChain`.

### 5.1. OIDC Login – Spring MVC

Add `spring-boot-starter-security` and `spring-boot-starter-oauth2-client` dependencies to a compatible Spring Boot project. Register the client at the OP, e.g. redirect URI `https://app.example.com/login/oauth2/code/corp`. Sample `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-idp
            client-id: ${SSO_CLIENT_ID}
            client-secret: ${SSO_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corp-idp:
            issuer-uri: https://idp.example.com/realms/company
```

The `openid` scope causes Spring Security to handle login as OIDC when the OP supports the corresponding endpoints. Client secrets come from environment variables/secret managers, never committed to source control. Java configuration:

```java
package example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Once integrated, accessing a protected page redirects to the IdP; the default login initiation endpoint is `/oauth2/authorization/corp` and callback is `/login/oauth2/code/corp`. The configuration code does not map roles yet: it only marks the user as authenticated; entering business pages must check permissions from trusted data. Behind a reverse proxy, configure forwarded headers/HTTPS properly so redirect URIs are not constructed with the wrong host/scheme. Do not expect to run this with just `javac SecurityConfig.java` because it requires the Spring Boot classpath.

### 5.2. SAML 2.0 Login – Spring MVC

Add `spring-boot-starter-security` and `org.springframework.security:spring-security-saml2-service-provider` matching your project's BOM. Suppose the partner provides the IdP's issuer, SSO URL, and public certificate:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              entity-id: https://idp.partner.example/saml
              verification:
                credentials:
                  - certificate-location: classpath:partner-a-idp.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso
                sign-request: false
```

`sign-request: false` **is merely an illustrative value for an IdP that does not require signing AuthnRequests**; if partner policy requires signing, configure the SP's signing private key/certificate and enable signing per the metadata/contract. Never disable SAMLResponse signature verification. Java Config for an application **choosing SAML instead of OIDC**:

```java
package example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
```

This configuration is an **alternative option**; do not place it in the same `SecurityConfig` class as the OIDC sample when testing independently. Common initiation path is `/saml2/authenticate/partner-a`, default ACS is `/login/saml2/sso/partner-a`, and `/saml2/metadata/partner-a` publishes SP metadata when `saml2Metadata` is enabled. You must register the exact ACS/entity ID with the IdP and test SP-initiated flows, invalid signatures, and expired assertions. When integrating multiple partners, use multiple distinctly named registrations rather than reusing partner A's verification config for B.

### 5.3. Resource Server for APIs Using JWT

If the API portion is a separate application/filter route, add `spring-boot-starter-oauth2-resource-server` and configure:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/company
          audiences: https://api.example.com
```

Protect the API with `.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` in the API's `SecurityFilterChain`. This JWT configuration sample is for **validating access tokens on API calls**, and does not create an SSO login screen for users. Beans/filter chains and matchers must be designed carefully if both web cookie sessions and Bearer APIs coexist. Do not assume that sharing the same issuer means every token has permission to call every API.

## 6. Mandatory Controls Regardless of Chosen Protocol

**Trust boundaries and identity**
1. Identify and restrict which issuers/IdPs are trusted for each application or tenant; never automatically accept an arbitrary issuer from a request.
2. Map identity by a stable namespaced key (OIDC `iss+sub`; SAML `issuer+NameID` if NameID has an appropriate durable format), bound to an internal tenant; only use email as a contact attribute after satisfactory verification policies.
3. Separate business roles from login. Enforce least privilege, tenant isolation, and group/role assignment policies; do not implicitly trust every role claim sent by a partner.

**Exchange security**
4. Always use HTTPS; configure redirect URIs/ACS and reverse proxies accurately. OIDC verifies signature, issuer, audience, expiration, and state/PKCE/nonce per flow. SAML verifies signature, issuer, audience, recipient, destination, conditions, and replay protection.
5. Protect client secrets, private keys, and keytabs in a secret manager/file permissions; rotate with overlap periods. OIDC uses controlled JWKS/metadata; SAML updates certificates on schedule and tests both signing and encryption.
6. Enable MFA/risk policies at the IdP per required assurance level. SSO only reuses authentication state; if sensitive operations require fresh authentication, design appropriate re-authentication/step-up.

**Sessions and operations**
7. Configure session idle/absolute timeouts, Secure/HttpOnly/SameSite cookies, CSRF for cookie-based flows, rate limits, and permission revocation. Application logout, IdP logout, and cross-application single logout can behave differently; verify each case.
8. Plan for IdP/AD or network outages, timeouts, and circuit breakers at appropriate points; never fail open ("allow access when IdP errors"). Synchronize server clocks since assertions/tokens are time-bounded.
9. Log login/failure events with correlation ID, tenant/issuer, and sanitized error codes; never log raw tokens, SAML assertions, passwords, private keys, or keytabs. Monitor redirect errors, signature failures, clock skew, and metadata changes.

## 7. Implementation and Decision Verification Checklist

| Question to answer before finalizing | Evidence / acceptance criteria |
| --- | --- |
| Do users access via browser, SPA, mobile, or server? Are there domain-joined machines? | Client inventory, access environment, browser/VPN constraints |
| Who is the IdP, and which protocol is published/contractually required? | OIDC discovery or SAML metadata, technical owner, and key-rotation process |
| Is the connection intra-enterprise or multi-tenant B2B federation? | Issuer → tenant mapping, stable identity, permission boundaries |
| What do login, API authorization, account provisioning, and logout require? | Flows and protocols specified for each part; do not conflate OAuth, OIDC, SCIM |
| Who manages MFA, sessions, passwords, secrets/certificates, and revocation policies? | Responsibilities of IdP, application, and operations teams documented |
| Have attacks and edge cases been tested? | Wrong issuer/audience, expiration, replay, bad signature, tenant mismatch, cert rotation, IdP outage, disabled user all blocked/handled properly |

**Minimum post-integration test matrix:**
- Valid user enters the right application/tenant → authentication succeeds, permissions scoped strictly.
- Unauthenticated user → redirected to the right IdP, valid callback; after login accesses original resource.
- Code/token/assertion with wrong issuer, audience, signature, or expired → rejected, no new session created.
- Partner A attempts to use an assertion/token to access tenant B → blocked even if email matches.
- IdP key/certificate rotation per procedure → system adopts new key in a controlled manner without skipping verification.
- Disabled user, expired session, or logout request → behavior matches design, without mistaking local logout for global logout across all apps.
- For intranet SPNEGO: test domain-joined and non-domain machines, hostname aliases, wrong SPN, clock skew; fallback uses only approved methods.
- For SPA: test redirect/PKCE code, refresh token/cookie, CSRF, and token leakage risks in URLs, storage, or logs.

## 8. Three Practical Decision Examples

**Scenario A – New web sales portal with Spring Boot + React, employees and customers on many devices:** Choose OIDC Authorization Code; consider BFF so the browser only holds a session cookie. The IdP handles MFA and login; the backend holds sessions, and APIs use access tokens with the right audience. Do not choose Kerberos because customers/personal devices are outside the domain; add SAML only if a partner IdP requires it.

**Scenario B – LAN timekeeping tool for domain-joined Windows employees:** If devices, hostnames, browsers, and AD are tightly controlled by IT, Kerberos/SPNEGO leverages existing Windows tickets. If the roadmap includes mobile/Internet access, choose OIDC via an AD-connected IdP to avoid tying the web app directly to intranet mechanics. Retain per-application authorization checks even though SSO skips password prompts.

**Scenario C – Portal for 20 suppliers with heterogeneous IdPs:** Per-partner SAML/OIDC contracts; prefer an identity broker if it reduces protocol configurations in the application. Map each issuer/tenant to its organization, permission policy, and separate account locking; test cross-tenant attacks, certificate rotation, and JIT/SCIM. Never treat email or user domain as sufficient evidence to merge accounts.

## 9. Reference Standards for Implementation Verification

- [Spring Security – OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): client registration, callbacks, and `oauth2Login`.
- [Spring Security – SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): asserting party, relying party, ACS, and SAML Response verification.
- [Spring Security – Kerberos extension](https://docs.spring.io/spring-security-kerberos/reference/index.html): SPNEGO/Kerberos and configuration patterns.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, audience, JWT validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) and [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700.html): security requirements for login/authorization flows.

**Rule of thumb when choosing:** cross-platform web typically uses **OIDC**, centrally managed Windows intranets can use **Kerberos/SPNEGO**, and B2B follows what the partner IdP actually provides (**SAML or OIDC**). Every option requires dedicated authorization design, cross-tenant identity mapping, account lifecycle management, and session protection.