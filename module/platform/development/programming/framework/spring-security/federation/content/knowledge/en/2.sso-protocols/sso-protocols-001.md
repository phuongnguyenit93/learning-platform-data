# SAML 2.0, OpenID Connect, CAS, and Kerberos in the Identity Ecosystem

> **Context:** SSO (Single Sign-On) protocols in the Spring Security ecosystem and enterprise identity management. The goal is to understand authentication flows, component roles, integration approaches, and protocol selection criteria; do not treat the four protocols as interchangeable token-issuing mechanisms.

## 1. Foundations: SSO, Authentication, and Identity Federation

**SSO** allows a user to log in once within a trusted domain and access multiple linked applications without re-entering credentials in each application. SSO typically relies on a session at the identity provider (**IdP**) and a mechanism to convey the authentication result to the application.

Important distinctions:

- **Authentication:** Who are you? For example, the IdP verifies a password, MFA, security key, or Windows domain credentials.
- **Authorization:** What are you allowed to do in the application? Permissions to read reports, modify data, or administer the system are still determined by the application's or access management's policy.
- **Federation:** Establishing a trust relationship so another organization or application accepts authentication results from the chosen identity system.
- **Provisioning:** Creating, updating, and disabling accounts (for example, via SCIM or directory synchronization). Provisioning is distinct from SSO login.
- **Session:** After successful authentication, web applications typically still create their own session and cookie. Single sign-on does **not** mean the four protocols share a single cookie or automatically log out together.

Reference model:

~~~text
User + browser
        |
        v
  Application (Spring Security) ----> Application authorization policy
        |
        | Authentication request via appropriate protocol
        v
  IdP / OP / CAS Server / KDC
        |
        +---- Account source: AD, LDAP, database, MFA
        |
        +---- Can act as an identity broker between Kerberos, SAML, and OIDC
~~~

In practice, **Active Directory/LDAP** is commonly the identity source; **AD FS, Keycloak, Okta, Microsoft Entra ID, or Apereo CAS** can act as a login/federation gateway depending on configuration. The **KDC** (Key Distribution Center) is the infrastructure that issues Kerberos tickets. A single IdP product can support multiple protocols simultaneously, but each application connection still requires its own trust configuration.

## 2. Map of the Four Protocols

| Protocol | Two main parties | Authentication evidence transferred | Typical scenarios | Characteristics |
|---|---|---|---|---|
| **SAML 2.0** | IdP (Asserting Party) ↔ SP (Service Provider/Relying Party) | XML `SAMLResponse` containing an assertion, usually digitally signed | B2B SSO, enterprise SaaS/applications, integration with legacy systems | XML metadata, X.509 certificates, HTTP Redirect/POST |
| **OpenID Connect (OIDC)** | OpenID Provider (OP) ↔ Relying Party (RP/client) | `id_token` and optionally `access_token`/`refresh_token` | Modern web/mobile, cloud IdP, API integration | Identity layer on top of OAuth 2.0, JSON/JWT, discovery/JWKS |
| **CAS protocol** | CAS Server ↔ CAS-enabled Service | Opaque Service Ticket (ST), verified over a back channel | Universities, portals, and applications with existing CAS support | `service` URL must match, ST is typically single-use |
| **Kerberos V5 + SPNEGO** | Client ↔ KDC ↔ service principal | Kerberos service ticket in HTTP `Negotiate` | Windows domain, intranet, AD-joined desktop/browser | KDC, realm, SPN, keytab, clock/DNS synchronization |

**Important rule:** OAuth 2.0 by itself is an authorization framework and does **not** guarantee user identification. OIDC adds the authentication layer (notably the `id_token`). Conversely, a SAML assertion, CAS ST, or Kerberos ticket is **not** an OAuth 2.0 access token for calling arbitrary APIs.

## 3. SAML 2.0 — Federation via XML Assertions

### 3.1. Components and SP-Initiated Flow

- **SP/Relying Party:** the application receiving the user; in Spring Security, the application using `saml2Login`.
- **IdP/Asserting Party:** the party that authenticates the user and signs the SAML response/assertion.
- **Metadata:** XML document exchanging `entityID`, SSO/ACS endpoints, bindings, and trust certificates.
- **ACS (Assertion Consumer Service):** endpoint on the SP that receives `SAMLResponse`, typically via HTTP POST.

Typical flow:

1. The browser visits a protected page on the SP.
2. The SP creates an `AuthnRequest` and redirects the browser to the IdP (typically HTTP-Redirect binding).
3. The IdP authenticates the user or reuses an existing SSO/MFA session.
4. The IdP sends `SAMLResponse` through the browser to the SP's ACS (typically HTTP-POST binding).
5. The SP verifies the signature, issuer, audience, recipient/destination, validity window, request correlation, and assertion constraints; it then creates an `Authentication` and an application session.
6. The application evaluates access permissions from the mapped identity/attributes.

**SP-initiated** has an `AuthnRequest` to correlate the response with the request; **IdP-initiated** may lack this correlation, so replay protection, unexpected sessions, and login CSRF risks must be carefully evaluated before enabling it.

Key SAML fields worth understanding:

- `Issuer`: the issuing party; must match the trust configuration.
- `Subject/NameID`: user identifier; not guaranteed to be stable or global by default.
- `AudienceRestriction`: which SP the assertion is intended for.
- `NotBefore/NotOnOrAfter`: validity window, requiring clock synchronization.
- `InResponseTo`: links to the request in an SP-initiated flow.
- `AttributeStatement`: user/group attributes; must be mapped to permissions in a controlled manner.

**Digital signing** authenticates the integrity and origin of the assertion/response; **assertion encryption** protects the content when configured, and does not happen automatically just because it is signed. Verification certificates and rotation must be managed; never accept a signature using an arbitrary certificate supplied by the client.

### 3.2. Spring Security with SAML

Spring Security supports an application acting as a **SAML Service Provider**; it does not turn an application into a SAML IdP merely by calling `saml2Login()`. The main components are `spring-security-saml2-service-provider` and `RelyingPartyRegistrationRepository`. With Spring Boot, IdP metadata can be declared as follows:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          enterprise-saml:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
~~~

This is an **illustrative configuration**: the URL must be actual metadata from a trusted IdP; the SP must be registered on the IdP along with its entity ID, ACS URL, and signing/encryption policy. Metadata fetched over the network requires an appropriate source/trust chain. Some deployments must explicitly declare SP certificates and signing keys, or adjust the ACS for a reverse proxy.

Common default Spring Security endpoints:

- `/saml2/authenticate/{registrationId}`: initiates the login request.
- `/login/saml2/sso/{registrationId}`: receives the response at the ACS.
- `/saml2/metadata/{registrationId}`: exposes SP metadata when `saml2Metadata` is enabled.

Production flows require verifying metadata and SP registration on both sides. With OpenSAML-based libraries, build configuration may require the Shibboleth Maven repository depending on the version documentation in use.

## 4. OpenID Connect — Authentication on OAuth 2.0

### 4.1. Definitions and Tokens

OIDC is an additional authentication layer for OAuth 2.0. The application is the **Relying Party/client**; the identity provider is the **OP**.

- **Authorization code:** a short-lived code received via redirect; the application exchanges it at the token endpoint, does not treat it as an identity, and does not use it as an access token.
- **`id_token`:** a JWT containing claims about the authentication event, intended for the **client/RP**. Verify `iss` (issuer), `aud` (client ID), signature/JWKS, `exp`, and `nonce` if requested.
- **`access_token`:** intended for the **resource server/API**; may be JWT or opaque, and should not be assumed decodable as a JWT by default. Validate the token according to the resource server's policy.
- **`refresh_token`:** if issued, used to request new tokens and must be stored/protected more strictly; not an identity token.
- **`scope=openid`:** marker requesting OIDC; `profile` and `email` are optional scopes as needed. `sub` is a stable identifier within the issuer's scope and according to the OP's policy.

OIDC discovery at `/.well-known/openid-configuration` helps clients retrieve authorization/token/UserInfo URLs, JWKS, and OP capability information.

### 4.2. Authorization Code Flow with PKCE

1. The RP generates `state` for CSRF protection and PKCE `code_verifier`/`code_challenge`; it may generate `nonce` to bind the ID Token.
2. The browser is redirected to the OP's authorization endpoint with `client_id`, `redirect_uri`, `response_type=code`, `scope=openid`, `state`, and PKCE.
3. The OP authenticates the user (potentially using an existing SSO/MFA session) and redirects the browser back to the registered redirect URI with `code`/`state`.
4. The RP verifies `state`, then sends the code and `code_verifier` to the token endpoint over a back channel; a confidential client also performs client authentication if required.
5. The RP verifies the ID Token and creates an application login session; it sends the access token only to APIs matching the audience/scope.

**PKCE** prevents an attacker from intercepting the authorization code and exchanging it for tokens; it should be used for both public clients and modern code flows when supported by the OP. Prefer exact registered redirect URIs, HTTPS, and secure cookies; do not casually place access tokens or ID tokens in localStorage or URLs.

### 4.3. Spring Security with OIDC

In a Spring Boot application with `spring-boot-starter-oauth2-client`, minimal configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise-oidc:
            provider: enterprise-oidc
            client-id: demo-client
            client-secret: REPLACE_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          enterprise-oidc:
            issuer-uri: https://idp.example.org/realms/company
~~~

The `client-id`/`client-secret` values are placeholders and must be replaced via a secure configuration/secret source; do not commit real secrets. When `issuer-uri` is valid, Spring can use discovery. Common defaults include:

- `/oauth2/authorization/enterprise-oidc`: initiates login.
- `/login/oauth2/code/enterprise-oidc`: redirect URI handling the authorization code.

Spring Security uses `oauth2Login()` for user login; `oauth2ResourceServer()` is a **different** feature for APIs to validate access tokens. When using the `openid` scope, Spring Security selects the OIDC processing path, making `OidcUser` and trusted claims accessible after authentication.

**OIDC logout** includes local logout, RP-Initiated Logout, and—depending on OP capabilities—back-channel logout. Never assume that clearing the Spring cookie terminates the session at the OP or all other applications.

## 5. Spring Boot Integration Example: SAML and OIDC in One Application

Below is **complete application-level Java code**, using Java 17+ and Spring Boot supporting Spring Security 6/7. This is not a standalone `javac` program: a Spring Boot project, dependencies, a running IdP, and registered client/SP configuration are required to perform actual logins.

Create a Spring Boot project with the corresponding dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, `spring-security-saml2-service-provider`. Use dependency management matching the compatible Spring Boot/Spring Security line.

File `src/main/java/com/example/sso/FederationDemoApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FederationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederationDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/saml2/metadata/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SSO demo";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

The `application.yml` configuration can combine the `spring.security.oauth2.client` and `spring.security.saml2.relyingparty` branches shown above. Run command inside the **Maven project directory containing the Maven Wrapper**:

~~~bash
./mvnw spring-boot:run
~~~

Verify that `GET /` returns the exact response string `SSO demo`; accessing `GET /me` while unauthenticated triggers the authentication flow. After successful login, `/me` returns the name in `Authentication` (the actual value depends on the IdP's principal/mapper). Neither console stdout nor the user's identity can be predetermined without a real IdP environment.

**Explanation:** `SecurityFilterChain` requires authentication for `/me`; `oauth2Login` and `saml2Login` register the two corresponding authentication mechanisms; `saml2Metadata` exposes SP metadata for registration with the IdP. Both flows are not invoked simultaneously for a single login: the user selects the appropriate registration/mechanism, and the application uniformly receives a Spring Security `Authentication`. When deploying behind a load balancer/reverse proxy, control `X-Forwarded-*` headers from trusted proxies and verify the external base URL/ACS/redirect URI.

## 6. CAS — Central Authentication Service

### 6.1. CAS Server, TGC, TGT, and Service Ticket

**CAS** is both the name of a ticket-based SSO protocol and the name of the **Apereo CAS** software ecosystem. CAS Server can support OIDC/SAML via corresponding modules, but the **CAS protocol** uses its own service ticket flow.

Typical flow:

1. The user opens a service, such as `https://app.example.org/login/cas`.
2. The service redirects the browser to `https://sso.example.org/cas/login?service=<encoded-service-url>`.
3. CAS Server authenticates the user or uses an existing SSO session. The TGT is managed on the CAS server side; the browser holds the **TGC** cookie linked to the SSO session, rather than carrying the TGT directly to the application.
4. CAS redirects the browser back to the exact `service` with query parameter `ticket=ST-...`.
5. The **service's backend** calls a validation endpoint such as `/cas/serviceValidate` with the ticket and the **exact declared service URL**.
6. If validation succeeds, the service creates an internal session and assigns identity/roles. An ST is typically bound to one service and single-use; do not store an ST as a long-lived credential.

HTTP flow example (illustrative URLs, not a real ST):

~~~http
GET https://sso.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas

HTTP/1.1 302 Found
Location: https://app.example.org/login/cas?ticket=ST-example-once

GET https://sso.example.org/cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-example-once
~~~

Do not assume encoded URLs are identical from slightly different `service` strings (scheme/host/port/path). CAS can support **Proxy-Granting Ticket/Proxy Ticket** for one service to access another service on the user's behalf; allowed proxies must be restricted, never enabled to accept any proxy by default.

### 6.2. Spring Security and CAS Integration

Spring Security provides CAS components such as `CasAuthenticationEntryPoint` (redirect), `CasAuthenticationFilter` (receiving tickets), `CasAuthenticationProvider` (calling the validator), and `ServiceProperties` (defining the service URL). It is typically paired with the Apereo CAS client library to validate the ST. Configuring CAS is **not** just calling `oauth2Login()`; you must declare the CAS server, service URL/validator, and wire filters/providers according to the exact version.

Configuration sequence:

1. Register the exact HTTPS service URL on the CAS Server.
2. Configure the entry point to redirect to CAS login; the filter to capture the ticket callback; and the provider to validate over the back channel via HTTPS and load/map authorities.
3. Test initial login, SSO cookie reuse, expired tickets, replayed tickets, mismatched `service`, session timeout, and logout paths.
4. If the organization has already enabled OIDC/SAML on Apereo CAS, consider using Spring `oauth2Login`/`saml2Login` against CAS as an IdP/OP for new applications.

**Single Logout:** CAS server can send logout notifications to linked services, but session/cookie handling, browsers, and network failures must be verified. Logging out locally from one service does not necessarily clear the SSO session on CAS.

## 7. Kerberos V5 and SPNEGO — Intranet Ticket-Based SSO

### 7.1. Realm, KDC, TGT, and Service Ticket

Kerberos uses symmetric-key cryptography and tickets issued by a **KDC**. In a Windows domain, the domain controller typically provides the Kerberos service. An identity formatted as `alice@EXAMPLE.ORG` is a **principal**; an HTTP service has an SPN such as `HTTP/app.example.org@EXAMPLE.ORG`.

Two stages to distinguish:

1. After authenticating with the KDC's **Authentication Service (AS)**, the client receives a **Ticket-Granting Ticket (TGT)**. The TGT allows requesting service tickets without resending the password each time.
2. The client asks the **Ticket-Granting Service (TGS)** to issue a **service ticket** for a specific SPN. The browser/HTTP client sends the ticket to the server via the **SPNEGO/HTTP Negotiate** mechanism. The server uses the principal's key (typically from a **keytab**) to verify it.

Illustrative HTTP exchange example (the token string is opaque and cannot be used to authenticate):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate

GET /private HTTP/1.1
Host: app.example.org
Authorization: Negotiate <opaque-spnego-token>
~~~

The browser must be permitted to use Integrated Windows Authentication/Negotiate for the host; SPN, DNS, domain trust, KVNO/keytab, encryption mechanisms, and clock synchronization must all be correct. Being logged into the same domain account does **not** automatically prove that every browser will perform SPNEGO with every website.

### 7.2. Spring Security Kerberos Integration

With **Spring Security 7**, Kerberos is part of the Spring Security line, with artifacts `spring-security-kerberos-core` and `spring-security-kerberos-web`; older project versions may use different extension coordinates and must be checked against the documentation for the actual version.

In a servlet web app, `SpnegoAuthenticationProcessingFilter` reads HTTP `Authorization: Negotiate` and passes the token to the configured authentication provider/Kerberos service validator. Remaining requirements:

- Service principal/SPN with the exact FQDN; a keytab with the matching key granted only minimal read permissions for the server.
- KDC/realm, DNS, NTP synchronization, domain trust, and supported encryption mechanisms.
- HTTP challenge/entry point configuration, filter chain, and mapping principal → account/permissions.
- Fallback option for non-domain devices or unsupported browsers; the fallback must have a clear policy.

On a domain-joined machine, `klist` helps inspect current tickets; use OS-appropriate Kerberos traces/tools to distinguish missing TGT, wrong SPN, or wrong keytab errors from Spring authorization errors.

**Key difference:** Kerberos is optimized for network SSO within a realm/trust domain. It is not a protocol for passing identity assertions over the internet like OIDC/SAML. Logging out of a web app does not automatically destroy the TGT in the operating system.

## 8. Four Protocols Coexisting in the Enterprise

### 8.1. Identity Broker and Trust Boundaries

For example: Windows workstations authenticate via Kerberos with AD; an identity broker uses Windows Integrated Authentication upstream and then issues **OIDC ID Tokens** or **SAML assertions** to cloud applications. The Spring Security application only needs to trust the **registered issuer/IdP**, without directly handling external users' browser Kerberos tickets.

~~~text
Windows user --Kerberos/SPNEGO--> AD/KDC + Identity Broker
                                           |
                           +---------------+-----------------+
                           |                                 |
                      OIDC (OP)                           SAML (IdP)
                           |                                 |
                   Spring web/mobile RP                Spring SAML SP
                           |
                 API Resource Server (access token)
~~~

CAS can also sit between legacy systems using CAS tickets and new applications using OIDC/SAML. **Broker/translation** performs one authentication and issues new evidence under the issuer's policy; it is not simply changing an ST string suffix into a JWT or trusting any assertion from any party.

### 8.2. Choosing a Protocol by Use Case

| Need | Evaluate first | Explanation |
|---|---|---|
| New application, web/mobile/cloud IdP, API calls | **OIDC** | Authorization Code + PKCE, discovery, tokens/claims, and OAuth resource-server |
| B2B SSO with partners already using SAML, enterprise SaaS | **SAML 2.0** | Federation via metadata/digital signatures; broad enterprise ecosystem |
| Legacy applications/academic portals already using CAS | **CAS protocol** or CAS as broker | Preserves ST/validator compatibility; can modernize via OIDC |
| Windows intranet, domain-joined users | **Kerberos + SPNEGO** | No password re-entry when KDC/SPN environment is properly configured |
| Multiple client/legacy types simultaneously | **Identity broker** | Reduces the number of trust relationships and unifies MFA/policy |

The decision also depends on actual clients, MFA requirements, logout capabilities, operations teams, auditing, key/certificate lifecycle, cross-organization identities, and ability to modify legacy apps.

## 9. Identity Mapping, Authorization, and User Lifecycle

A single person may appear as a **NameID** (SAML), an **issuer + sub** pair (OIDC), a CAS username, and a **UPN/principal** (Kerberos). Do not treat every `email` or `username` value as a global user key: emails can change, collide across organizations, or be reassigned.

Practical design:

1. Choose the federated identity key by **issuer + stable identifier** and tenant/realm; store the mapping to the internal user.
2. Normalize attributes/claims/groups from an **authenticated** source, restrict privileges, and handle locked accounts or users no longer belonging to the organization.
3. Separate login decisions from permission-granting decisions. "Logged in with the IdP" does not grant `ROLE_ADMIN` by default.
4. Control JIT provisioning, SCIM, account deactivation, session/token revocation, and re-granting permissions; an offboarding plan does not stop at deleting a password.
5. Distinguish the user principal from API-calling credentials. APIs must validate access tokens against the **API's own** issuer, audience, expiry, and scope/permissions.

## 10. Security and Testing Checklist

| Failure/Attack | What to verify |
|---|---|
| Trusting the wrong IdP or forged assertion/token | Pin trusted issuer/metadata/JWKS/certificates; verify signatures, allowed algorithms, and rotation |
| Replay or uncorrelated login response | SAML `InResponseTo`/conditions/time/replay cache; single-use CAS ST; OIDC `state`/PKCE/nonce where applicable; Kerberos replay protection |
| Token misused in the wrong place | Do not use OIDC `id_token` to call APIs; resource server checks audience/scope; do not treat CAS ST as a long-lived bearer token |
| Misconfigured redirect/leaked cookie | HTTPS, matching callback/ACS/service URI, trusted reverse proxy, appropriate HttpOnly/Secure/SameSite, session fixation protection |
| Missing permissions despite successful auth | Verify group/role mapping, tenant, stable principal, and account status |
| Clock and key issues | NTP synchronization, expiry/not-before, SAML cert/JWKS rotation, Kerberos keytab/KVNO, secret lifecycle |
| Inconsistent logout | Test local logout, IdP logout, SAML SLO/CAS SLO/OIDC logout depending on support; Kerberos TGT persists independently |
| IdP/KDC failure or unsupported browser | Emergency access procedure, bounded timeout/retry, operational alerting, policy-backed fallback |

**Minimum test scenarios** for an integration:

- Unauthenticated user → redirected to the correct IdP/OP/CAS or receives proper HTTP Negotiate challenge.
- Successful login → session created only in authorized applications; accessing resources requires the right authority.
- Existing SSO session → logging into a second app requires no credential re-entry if policy permits.
- Wrong issuer/audience/ACS/service/redirect URI, invalid signature/cert, invalid state, or used/expired ticket → rejected.
- User lacking a role or disabled → cannot access resources even if the prior authentication flow succeeded.
- Logout, timeout, MFA step-up, key/certificate rotation, clock skew, and temporary IdP outage → outcome matches policy with logs/metrics for diagnosis.

## 11. Comprehension Check Questions

1. **How does a SAML assertion differ from an OIDC ID Token?** Both convey an authentication result, but they differ in format, role set, endpoints, authentication mechanisms, and validation rules; applications cannot swap them directly.
2. **Why does OAuth 2.0 not equate to identity SSO?** OAuth 2.0 solves authorization; OIDC defines identity authentication via `id_token` and OP/RP constraints.
3. **Why shouldn't a CAS ST be stored for reuse?** An ST is bound to a service and designed for single-use verification; reuse is a sign of replay.
4. **How does a Kerberos TGT differ from a service ticket?** A TGT is used to request tickets for services from the TGS; a service ticket is presented to the target SPN through an application protocol/SPNEGO.
5. **What if a company has AD and many Spring cloud applications?** Typically consider a broker/IdP integrating AD/Kerberos upstream and delivering OIDC/SAML to applications; design authorization and logout separately.

## 12. Official Documentation for Version-Specific Reference

- Spring Security — SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — OAuth 2.0/OIDC Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- Spring Security — CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security — Kerberos: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Apereo CAS — CAS Protocol Specification: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html

Artifact names, custom endpoints, and DSLs may change between Spring Security 6, 7, and subsequent releases. In actual implementation, lock dependency versions and consult the exact documentation for that version.
