# Choosing Protocols by Infrastructure and Non-Interchangeable Boundaries

## 1. Why Can't We Just Ask "Which Protocol Is Most Modern?"

In **identity federation**, organizations often must connect multiple systems: Active Directory (AD DS), LDAP directories, Windows intranets, Java web portals, SaaS apps, mobile apps, APIs, service-to-service traffic, and one or more Identity Providers (IdPs). Choosing an authentication method based solely on protocol buzzwords easily leads to architectural flaws.

A sound design starts with the question: **who needs to prove identity to whom, over which connection, using what evidence, and with what permissions?** Protocols differ in scope and prerequisites. You cannot arbitrarily swap an LDAP bind for a SAML assertion, a Kerberos ticket for an access token, or treat an ID Token as an API bearer token.

Foundational concepts:

- **Identity store/directory:** stores users, groups, devices, attributes, and linking keys. Examples include AD DS/OpenLDAP; these systems can be queried over LDAP.
- **Authentication:** proves the identity of a user, device, client, or workload. Examples include Kerberos, WebAuthn, password verification via LDAP bind, and mTLS client certificates.
- **Federated login/SSO:** an application trusts a login result issued by another identity system under a configured trust relationship. Examples include SAML 2.0 Web SSO and OpenID Connect.
- **Authorization/delegation:** grants a client permission to access a resource. OAuth 2.0 is an authorization framework; APIs validate access tokens/scopes/audience per policy.
- **Provisioning/lifecycle:** creates, updates, locks, and deletes accounts in target systems. SCIM is a common protocol for this purpose; it does not authenticate logins itself.
- **Application principal:** the identity recognized by the application after authentication, such as an internal user ID or service account; from that principal, roles/permissions are resolved.

**Overarching rule:** the same person may be recognized by AD, a SAML IdP, and an OIDC Provider, yet the evidence and identity extraction differ across all three. Only **controlled identity linking** decides that those identities map to the same application account.

## 2. Responsibility Diagram: Which Segment Does Each Protocol Solve?

~~~text
        [HR Source / Identity Governance]
                       |
               Provisioning: SCIM
                       |
          +------------v-------------+
          |  Directory / AD DS       |
          |  Users, Groups, Devices  |
          +--+----------+------------+
             |          |
         LDAP query   Kerberos / KDC
         & bind          |
             |          v
             |    Windows domain SSO / SPNEGO
             |          |
             +----+-----+                   +-------------------+
                  |                         | IdP / Federation  |
                  |     LDAP/Kerberos       | Gateway/Broker    |
                  +------------------------>|                   |
                                            +----+----------+---+
                                                 |          |
                                            SAML assertion  OIDC ID Token
                                                 |          |
                                       +---------v----------v---+
                                       | Web application / BFF  |
                                       | Spring Security        |
                                       +------------+-----------+
                                                    |
                                          user session / identity
                                                    |
                                       application authorization
                                                    |
                                                 [API]

   [Machine / workload] -- mTLS / OAuth2 client_credentials --> [API]
                                 proof of peer/client
                                     + audience/scope
~~~

The diagram shows options that **can work together**, not protocols that are all mandatory in every system. An IdP may authenticate a user via Kerberos or read a directory over LDAP behind the scenes, then issue an OIDC ID Token to a web app. The app only handles OIDC; the IdP's use of LDAP does not turn the web app into an LDAP client.

## 3. Quick Selection Matrix by Purpose and Infrastructure Prerequisites

| Infrastructure or Need | Usually Appropriate Choice | Prerequisites | What Not to Infer |
|---|---|---|---|
| Legacy system storing username/password in a directory | **LDAP bind over TLS** with directory/AD DS | Directory endpoint, search permission, user DN/filter, LDAPS/StartTLS | LDAP bind does not automatically provide browser SSO, MFA, or API tokens. |
| Domain-joined Windows machines, intranet app needing integrated login | **Kerberos/SPNEGO** or a gateway supporting Windows Integrated Authentication | KDC, SPN, keytab/service principal, DNS/time/browser policies | A Kerberos ticket is neither an OIDC ID Token nor a JWT for other APIs. |
| Enterprise partner/SaaS app supporting only SAML | **SAML 2.0 Web SSO** | IdP metadata, SP entity ID, ACS, signing certs, trust config | A SAML assertion is not an arbitrary OAuth2 access token for REST APIs. |
| New web app needing SSO with a cloud IdP | **OIDC Authorization Code** (PKCE per client type) | OIDC Provider, client registration, redirect URI, HTTPS, discovery/JWK | Issuing only an OAuth access token does not constitute OIDC login. |
| SPA/mobile external login | **OIDC Authorization Code + PKCE**, appropriate system browser/SDK | Public client, valid redirect scheme/URI, secure token handling | Do not use implicit/password grant as a default substitute. |
| REST API called by multiple clients | **OAuth2 Resource Server** validating JWT access tokens or opaque token introspection | Trusted Issuer/AS, API audience, scopes, token lifecycle | An ID Token for web login is not an API access token. |
| Backend service calling backend service | **mTLS**, **OAuth2 client_credentials**, or both per threat model | PKI/workload identity; AS/client authentication; token audience and policy | mTLS only authenticates the TLS peer; `client_credentials` usually carries no end-user identity. |
| Syncing accounts from IdP to SaaS | **SCIM 2.0** + separate login protocol | Provisioning API, CRUD, lifecycle, reconciliation | SCIM is not a user login protocol. |
| Wi-Fi/VPN network access-layer authentication | **802.1X/EAP, RADIUS** per device/infrastructure | Network access server, supplicant, AAA server | RADIUS does not directly replace OIDC/SAML Web SSO. |
| Phishing-resistant login via security key/passkey | **FIDO2/WebAuthn**, typically at IdP or application | Browser/device/authenticator and server support | WebAuthn is an authentication factor, not by itself a cross-app federation protocol. |

There is no "best protocol" independent of architecture. Having AD does not mean every web app should connect over LDAP; using OIDC does not mean every network appliance speaks OIDC natively.

## 4. LDAP: Directory Access and Bind Authentication

**LDAP** defines how a client searches, reads, and (when authorized) modifies directory entries, as well as the **bind** operation where the directory server authenticates the connection session's identity. With Spring Security, the LDAP bind pattern typically follows:

1. The user enters username/password in the application's UI.
2. The application locates the user's DN via an LDAP search or constructs the DN from an organization-approved pattern.
3. The application attempts a bind with the user's password over LDAPS/StartTLS.
4. If the bind succeeds, the application retrieves groups/attributes and creates a Spring `Authentication`.
5. Spring authorization decides which features the user may access.

~~~text
Browser ---> Form Login (user + password) ---> Spring Security
                                               |
                                               +-- LDAP search ----> Directory
                                               +-- LDAP bind ------> Directory
                                               |
                                               +-- local user/role mapping
~~~

Prerequisite: the application must reach the directory directly and handle credentials under an approved design. **Having an application accept employee passwords expands the password exposure surface**; enforce TLS, never log secrets, apply brute-force controls, and restrict service account privileges. LDAP bind does not turn the application into an OIDC Relying Party or SAML Service Provider.

### Do Not Use LDAP to "Replace" These Capabilities

- **Browser SSO:** LDAP bind normally checks a password whenever the app requests it; it does not automatically issue cross-app SSO cookies or inherit an existing IdP browser session.
- **OAuth2 API access:** LDAP does not issue access tokens with audience/scope/expiry for downstream resource servers to verify.
- **MFA:** a simple bind does not inherently enforce MFA, step-up, or device compliance policies. Directory-integrated MFA solutions depend on vendor products/infrastructure rather than being built-in LDAP protocol features.
- **Stable account linking:** a DN can change when a user is renamed or moved across OUs; use a schema-appropriate immutable directory key (in AD, typically `objectGUID`) and a formal account linking workflow.

Spring Security's LDAP configuration offers extension points such as `LdapBindAuthenticationManagerFactory`; adding `spring-security-ldap` does not add SAML/OIDC. For modern SSO systems, a usually better architecture is **having the IdP talk to AD/LDAP** while web applications talk to the **IdP via SAML or OIDC**.

## 5. Kerberos/SPNEGO: Domain- and Service-Principal-Based SSO

**Kerberos** uses tickets issued by a Key Distribution Center (KDC) so clients can prove identity to services holding a service principal. In Microsoft AD infrastructure, domain controllers typically host the KDC. For intranet browsers, **SPNEGO/Negotiate** can carry Kerberos over HTTP so domain-logged-in users get an SSO experience.

~~~text
Domain-joined workstation
         |
         |  TGT / Kerberos service ticket from KDC
         v
Browser -- HTTP Negotiate (SPNEGO token) --> Intranet application
                                               |
                                   accept ticket by SPN/keytab
                                               |
                                    map principal + authorities
~~~

Non-negotiable prerequisites:

- Clients and services must reach the domain/KDC, keep synchronized clocks, and have accurate DNS/SPNs.
- Service principals, keytabs, or delegated credential mechanisms must be securely managed.
- Browsers and OSes must have policies permitting Integrated Authentication to the target origin.
- Proxies, load balancers, and hostnames must be configured properly so a ticket minted for one SPN is not routed to the wrong service.
- If constrained delegation or calling backend services under the user's identity is needed, design that separately; a Kerberos ticket for service A cannot arbitrarily be reused at service B.

**Kerberos is not synonymous with LDAP.** AD can provide both LDAP and Kerberos; apps using LDAP bind send user/password to the directory, whereas SPNEGO relies on tickets. Spring Security supports Kerberos integration via dedicated modules, yet configuring `spring-security-ldap` alone does not enable Kerberos.

Kerberos works well on tightly managed intranets, yet is hard to use directly for public websites and non-domain-joined personal devices. To extend SSO to SaaS or external apps, organizations usually place an **IdP/federation gateway** in front: users authenticate to the IdP via Windows Integrated Authentication, while SaaS apps receive **SAML** or **OIDC** from the IdP.

## 6. SAML 2.0: Web Login Federation with XML Assertions

**SAML 2.0 Web Browser SSO** is widely used by enterprises and SaaS applications. Here, the **Identity Provider (IdP)** authenticates the user and issues a **SAML Response/Assertion**; the target app acts as the **Service Provider (SP)** and validates it under a trust relationship.

~~~text
Browser ---> SP (Spring web app)
     <--- redirect to IdP with AuthnRequest
Browser ---> IdP (login/MFA per policy)
     <--- SAMLResponse
Browser ---> SP Assertion Consumer Service (ACS)
             |
             +-- verify issuer, signature, conditions, recipient/audience
             +-- enforce request/response correlation, time, replay protection
             +-- map NameID / attributes -> internal account
             +-- create Spring session + authorities
~~~

A typical SAML trust relationship requires:

- **IdP entity ID**, SSO endpoint, and valid certificates/keys for signature verification.
- **SP entity ID**, **ACS URL**, and metadata/registration accepted by the IdP.
- Verification of **Issuer**, **AudienceRestriction**, **Recipient/Destination**, timestamps (`NotBefore`, `NotOnOrAfter`), and **InResponseTo** when applicable to the flow.
- Policies for signatures, encryption, key rotation, clock skew, RelayState, and replay protection enforced per the real profile.
- Selection of a stable **NameID format** or identity attribute. Email or transient NameIDs cannot automatically serve as immutable user keys.

**A SAML assertion is not an OAuth2 access token.** Assertions target an SP's audience/recipient within SAML flows; an application must never take an assertion issued for portal A and place it into `Authorization: Bearer` for API B without a properly designed **token exchange/bridge** issuing a new token.

Spring Security Servlet supports `saml2Login()` via `spring-security-saml2-service-provider`. Configuring `RelyingPartyRegistrationRepository` or metadata tells the SP which IdP it trusts. `Saml2AuthenticatedPrincipal` provides the principal/attributes after framework SAML validation, yet **the application remains responsible for account linking and business authorization**.

Note: SAML logout or single logout does not automatically work simply because login succeeds; it must be configured and tested with the IdP, session store, and actual topology.

## 7. OpenID Connect: Web/Mobile Federation on Top of OAuth 2.0

**OpenID Connect (OIDC)** adds a user authentication layer atop OAuth 2.0. In the **Authorization Code Flow**, the application (Relying Party/OIDC client) redirects the browser to the OpenID Provider, receives an authorization code, and exchanges it for tokens per client config. The `ID Token` serves as identity evidence for the **OIDC client** once fully verified.

~~~text
Browser -> Application -> OpenID Provider (Authorization endpoint)
               <--------- authorization code (redirect)
Application -> OpenID Provider (Token endpoint, code exchange)
            <- ID Token (+ access token, depending on scope/flow)
Application -> validate ID Token and map (iss, sub)
            -> internal principal/session
~~~

Key constraints:

- Verify **signature**, `iss`, `aud` (must contain the matching client ID), `exp`/timestamps, and `nonce` when required by the flow.
- Validate `state`/correlation on authorization responses; use **PKCE** to prevent code interception, especially for public clients like mobile/SPA.
- Bind users stably via the **`iss + sub` pair**; never link accounts solely by `email`, `name`, or `preferred_username`, as those claims can change or be recycled.
- Protect redirect URIs and secrets. Public clients must never treat an embedded client secret as confidential.
- If using UserInfo, verify `sub` matches the ID Token per OIDC rules.

In Spring Security Servlet, `oauth2Login()` belongs to the OAuth2 Client feature; when `scope=openid` is configured, Spring applies OIDC processing. This is a strong fit for cloud web/mobile apps with IdPs supporting OIDC discovery/JWK. On mobile, use the **system browser** rather than collecting IdP passwords inside embedded WebViews or custom screens.

OIDC **does not automatically replace** Kerberos for every Windows service, SCIM for provisioning, or OAuth2 Resource Server for every API. A Spring MVC web app can use OIDC login and then keep an **HTTP session**; a separate API can accept **OAuth2 access tokens** — two distinct models even under the same issuer.

## 8. OAuth 2.0: Authorization for Clients/APIs, Not a Generic Synonym for Login

OAuth 2.0 distinguishes four roles: **resource owner**, **client**, **authorization server**, and **resource server**. An access token grants resource access according to the authorization grant, scopes, audience, and policy. Plain OAuth 2.0 does not define a standardized end-user authentication payload like an OIDC ID Token.

**You cannot take an `access_token`, decode a `user` claim, and treat it as standard SSO** if the provider has not established a verified identity-authentication contract. An API must also confirm the token was issued **for that exact API** (audience), by a trusted issuer, is unexpired, and carries the required scopes/permissions.

Distinguish these scenarios:

| Flow / Subject | Evidence Received | Logical Principal |
|---|---|---|
| Browser OIDC login | ID Token for the OIDC client, paired with authorization response | User authenticated by the IdP; mapped to an app account. |
| API OAuth2 bearer JWT | JWT **access token** with signature, issuer, audience, expiry, scopes | User **or client**, depending on token/flow; API policy decides. |
| API OAuth2 opaque token | Opaque string; resource server introspects with the AS | Principal/attributes from trusted introspection results. |
| Machine-to-machine `client_credentials` | Access token for the client/service | Typically a **client identity**, with no end-user by default. |

Spring Security Resource Server provides `oauth2ResourceServer().jwt()` for JWT validation and `opaqueToken()` for introspection. Configure verifiers/issuers, audience checks, token types, issuer-specific validation, and scope/authority mappers. `JwtAuthenticationConverter` can map valid scopes/claims into `GrantedAuthority`. Never treat `scope=openid` as `ROLE_ADMIN`.

**Two APIs trusting the same issuer will not necessarily accept each other's tokens.** A token issued with `aud=payroll-api` must not be accepted at `billing-api` merely because `iss` matches. If service A must call API B on a user's behalf, design proper delegation/token exchange and trust boundaries rather than forwarding a token minted for a different audience.

## 9. mTLS/X.509: Transport-Level Peer Authentication, Not End-User Federation

**TLS** encrypts the channel and authenticates the server; **mTLS** additionally requires the client to present a certificate and prove private-key possession over the TLS handshake. This is well suited for identifying services/machines inside internal networks or service meshes.

However, when a **gateway/proxy terminates TLS**, the backend typically sees the **gateway** as the TLS peer on the new connection. The original user's client certificate does not automatically travel to the backend as a verified TLS attribute.

~~~text
User's client certificate -- mTLS --> Gateway
                                      | verifies original TLS peer
                                      | creates trusted identity assertion
                                      v
                                  Backend
                                      | verifies assertion provenance
                                      | maps internal user/role
                                      v
                                 Business API

Gateway certificate -- mTLS (new connection) --> Backend
      (this certificate authenticates the gateway, not the original user)
~~~

To pass user identity across a gateway, you need a **protected assertion mechanism**: proxy-backend mTLS + restricted network paths with proxy-overwritten headers, or signed tokens/assertions checked for signature, issuer, audience, and expiry. Never trust `X-User` or `X-Client-Cert` sent by arbitrary HTTP clients. When an app also enforces user-level roles, mTLS is **only one peer-proof layer**, while account mapping and authorization remain the application's or authorization service's job.

mTLS and OAuth2 can **combine**: mTLS authenticates the client to the token endpoint and/or binds access tokens to a certificate per profile, while the token carries scopes/audience. Turning on HTTPS client certificates does not magically produce `SCOPE_orders.write` in Spring Security.

## 10. Things Commonly Mistaken as Interchangeable

### 10.1. SCIM Cannot Replace SAML/OIDC

SCIM 2.0 is a REST-based protocol for **provisioning and managing Users/Groups**. A SaaS app may receive a user via SCIM on their start date, yet when the user clicks "Sign In", they still need **OIDC/SAML/password or an approved login mechanism**. Conversely, successful SSO does not automatically mean an account was provisioned or granted business permissions.

### 10.2. WebAuthn/Passkeys Are Not a Federation Protocol

WebAuthn uses public-key cryptography to authenticate to a single **Relying Party/origin**; an IdP can adopt WebAuthn as a phishing-resistant factor. Downstream SaaS apps still receive SAML/OIDC from that IdP. A WebAuthn credential from origin A cannot be handed directly as an access token to API B. The protocol solves **proof of identity at the login point**, not cross-application account linking.

### 10.3. AD DS Is Not Synonymous with an OIDC Provider

AD DS is directory/domain infrastructure; it provides LDAP and Kerberos, yet having a domain controller does not automatically provide a `/.well-known/openid-configuration` discovery endpoint or ID Tokens for cloud apps. You need a dedicated IdP/federation service with proper trust policies and configuration.

### 10.4. JWT Is a Token Format, Not a Login Protocol

A self-crafted JWT containing `{"sub":"admin"}` is merely a Base64URL-encoded string or something signed by some key. You must validate **issuer, signature, algorithm, audience, expiry, and token type**. Knowing a token is a JWT proves no identity. Conversely, SAML typically uses XML assertions, and OAuth2 opaque tokens need not be JWTs.

### 10.5. A Reverse Proxy Sending Headers Does Not Automatically Create SSO

If a gateway terminates SAML/OIDC and forwards a username to the backend, the backend must know exactly who is authorized to send assertions, prevent header spoofing, verify where signing/verification happens, know which account maps, and know when sessions expire. A header without a protected provenance boundary is **not** a substitute for SAML/OIDC.

### 10.6. MFA and Assurance Levels Are Not Encoded in Protocol Names

One system might use OIDC with passwords only, while another uses SAML with strong MFA. Authentication strength depends on IdP policy and appropriate signals such as `acr`/`amr` in OIDC (when defined, issued, and verified per contract) or `AuthnContext` in SAML. If an action requires step-up/MFA, explicitly require and verify the achieved assurance level rather than inferring it simply because a token is OIDC.

## 11. Selecting by Real-World Architecture Scenarios

### Scenario A: Java Intranet for AD-Domain-Joined Employees

**Context:** domain-joined workstations, internal KDC/AD, managed browsers, goal is SSO without re-entering passwords.

- Use Kerberos/SPNEGO directly at the service or via a gateway supporting Windows Integrated Authentication.
- If the organization already runs an IdP integrated with AD/Kerberos, new web apps can use **OIDC** with the IdP and still achieve SSO via the IdP infrastructure.
- Do not choose LDAP bind just because user records live in AD when the goal is "passwordless SSO experience".

**Dependencies to clarify:** SPNs, DNS, browser policies, network path to KDC, keytabs, proxies, and delegation. If users also connect from off-domain devices, OIDC via an IdP may fit better, paired with MFA/conditional access.

### Scenario B: Enterprise SaaS App Accepting Only SAML

**Context:** an HR SaaS platform supplies SAML metadata and an ACS, with no OIDC client registration.

- Configure a SAML IdP, assertion signing/verification, entity ID/ACS, released attributes, and a stable NameID.
- Internally, the IdP can authenticate users via AD, LDAP, or WebAuthn; the SaaS app need not support each upstream mechanism.
- If the organization's IdP only speaks OIDC, introduce a **federation broker** supporting both protocols that issues a fresh SAML assertion trusted by the SaaS app. You cannot POST a JSON ID Token to an ACS to "substitute" for SAML XML.

### Scenario C: New SPA/Mobile App + Spring Boot API

**Context:** frontend/mobile app logs in via an IdP; backend handles API calls.

- Choose OIDC Authorization Code + PKCE for login; protect browser/mobile flows and redirect URIs.
- Have the API use OAuth2 Resource Server to validate **access tokens** whose audience matches the API, or use a BFF/server-side session to avoid exposing tokens to browsers depending on architecture.
- ID Tokens are for the OIDC client; APIs must not accept ID Tokens as access tokens.
- The app must link `(iss, sub)` to an internal user and check account status, tenant, and resource permissions.

Successful login alone is not enough to approve records: actions may require `APP_APPROVE`, scopes, and record-level ownership checks.

### Scenario D: API-to-API Between Kubernetes Workloads

**Context:** `billing` service calls `inventory`, with no human user interaction.

- mTLS authenticates workload peers, fitting service meshes/PKI when the organization has certificate issuance/rotation infrastructure.
- Or OAuth2 `client_credentials` obtains an access token with audience/scopes targeting `inventory`.
- You can combine mTLS and tokens for both channel security and explicit authorization context.
- Never map `client_id=billing` to a human user `lan`; if user delegation is needed, use a dedicated delegation flow.

**Expected outcome:** authorization bound to service identity, e.g., `INVENTORY_READ`; successful mTLS alone never grants blanket permission to mutate all inventory.

### Scenario E: Legacy App Supports Only LDAP/Password, Business Wants MFA/SSO

**Context:** the application cannot be upgraded immediately and expects LDAP password accounts.

- Do not assume switching `ldap://` to `ldaps://` adds MFA; LDAPS only encrypts transport.
- Depending on the product, integrate an identity gateway/proxy/pre-auth or upgrade the app to support OIDC/SAML. Block legacy login paths bypassing the gateway if deploying a proxy.
- You can run a dual-run migration path and phase out direct password binds after verifying functionality, account linking, and rollback.

**Avoid:** inventing an arbitrary `X-Authenticated-User` header and calling it OIDC, or calling an HTTPS API with another service's Kerberos ticket.

## 12. Spring Security Examples: Each Protocol in Its Proper Role

In Spring Security **Servlet**, the DSLs below illustrate **distinct roles**, not a single config turning on every protocol at once. These snippets require matching dependencies and client/IdP/resource-server registrations; they are not standalone applications.

### 12.1. Browser SSO App via OIDC

Typical dependencies with Spring Boot (Gradle, versions managed by Boot):

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
~~~

~~~java
@Bean
SecurityFilterChain browserSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Configure `spring.security.oauth2.client.registration.*` and `provider.*.issuer-uri` along with redirect URIs and client credentials. `oauth2Login` manages web login sessions; **it does not turn the app into an OAuth2 Authorization Server or a REST JWT Resource Server**.

### 12.2. Browser SSO App via SAML 2.0

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-saml2-service-provider")
}
~~~

~~~java
@Bean
SecurityFilterChain samlWebSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Configure `RelyingPartyRegistrationRepository`, IdP metadata/certificates, SP entity ID, and ACS. Spring Boot supports `spring.security.saml2.relyingparty.registration.*` properties. Do not point the OIDC `issuer-uri` property at SAML metadata expecting the framework to switch protocols automatically.

### 12.3. REST API Accepting OAuth2 JWT Access Tokens

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
~~~

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Beyond default issuer/JWK validation, verify **audience, token purpose, and scopes** matching the API. For opaque tokens, configure introspection using `opaqueToken`. Never use `oauth2Login` in place of an API bearer-token validator.

**Example structure warning:** the three `SecurityFilterChain` methods above illustrate **three separate apps/variants**. Do not copy all three into one app with `anyRequest()` matching every URL: Spring Security selects the first matching filter chain, causing login/ACS/API routes to be handled unexpectedly. If one app needs both web SSO and APIs, design multiple chains using `securityMatcher`, `@Order`, distinct exception handling, and callback routes, and thoroughly test chain ordering.

### 12.4. LDAP Bind in a Password-Based Application

For apps requiring direct username/password input, LDAP authentication uses `spring-security-ldap` and a context source; `LdapBindAuthenticationManagerFactory` can search for a DN and bind. This is a **username/password authentication provider**, not a token verifier for OIDC/SAML. Do not scatter LDAP code into individual controllers.

### 12.5. Kerberos and X.509

Kerberos/SPNEGO needs dedicated integration components, SPN/keytab, and a KDC; X.509 needs TLS container/proxy trust policies and principal mapping after certificate verification at the right boundary. Spring Security provides appropriate X.509/pre-auth and Kerberos integrations, yet does not issue certificates, manage CAs, generate keytabs, or configure domains. When TLS terminates at a proxy, the backend does not automatically receive the original client certificate.

## 13. Linking Identities Across Protocols to One Application Account

External protocols determine the **evidence and identity namespace**; the application needs its own mapping table.

Example for the same employee, Lan:

| Source | Usable External Identifier | Preconditions Before Linking |
|---|---|---|
| OIDC | `iss + sub` pair from verified ID Token | Matching Client ID/audience, trusted issuer, unique link check. |
| SAML | `IdP entity ID` + persistent `NameID`/qualifiers or contracted ID attribute | Valid assertion, clear NameID format/issuer/profile and stability policy. |
| Kerberos | Principal with account/service principal + realm, from verified ticket | Verify realm/trust and policy-canonicalized principal; avoid cross-realm collisions. |
| LDAP/AD | Immutable directory object ID like `objectGUID` with directory namespace | Trusted bind/search, clearly defined schema and directory domain/forest. |
| X.509 | SAN URI/identity with trust domain/issuer/profile, or certificate fingerprint if binding a single cert | TLS/provenance verification, CA policy, planned rotation/revocation. |

The application may store tables such as:

~~~text
internal_users
  id       = usr-1042
  tenant   = company-a
  status   = ACTIVE

external_identity_links
  internal_user_id | scheme   | authority                         | subject
  -----------------+----------+-----------------------------------+-------------------
  usr-1042         | OIDC     | https://idp.example/realm/staff   | 4d1f8a
  usr-1042         | SAML     | https://saml.example/idp          | staff-294
  usr-1042         | KERBEROS | CORP.EXAMPLE                      | lan@CORP.EXAMPLE
~~~

**Never treat `staff-294`, `lan`, and `4d1f8a` as equivalent merely because usernames or emails match.** Multi-source linking must rely on evidence-backed enrollment: admin-provisioned links, a user actively verifying their current account before linking a new IdP, or an approved migration process. Internal accounts can still be locked independently even when the IdP authenticates them.

### Java 17: Simulating Identity Key Boundaries

The **standalone JDK 17** program below demonstrates why matching username/subject strings across protocols do not automatically mean the same person. It **does not verify tokens, SAML assertions, Kerberos tickets, or certificates**; inputs are assumed to have passed protocol-appropriate authentication.

~~~java
import java.util.Map;

public class ProtocolIdentityLinkDemo {
    record ExternalKey(String protocol, String authority, String subject) {}

    public static void main(String[] args) {
        Map<ExternalKey, String> links = Map.of(
            new ExternalKey("OIDC", "https://idp.example/staff", "lan"),
            "usr-1042",

            new ExternalKey("SAML", "https://saml.example/idp", "staff-294"),
            "usr-1042",

            new ExternalKey("KERBEROS", "CORP.EXAMPLE", "lan"),
            "usr-2099"
        );

        System.out.println("OIDC: " + links.get(
            new ExternalKey("OIDC", "https://idp.example/staff", "lan")));
        System.out.println("SAML: " + links.get(
            new ExternalKey("SAML", "https://saml.example/idp", "staff-294")));
        System.out.println("KERBEROS: " + links.get(
            new ExternalKey("KERBEROS", "CORP.EXAMPLE", "lan")));
        System.out.println("UNKNOWN: " + links.getOrDefault(
            new ExternalKey("OIDC", "https://other.example", "lan"),
            "UNLINKED"));
    }
}
~~~

Save as `ProtocolIdentityLinkDemo.java`, then run:

~~~bash
javac ProtocolIdentityLinkDemo.java
java ProtocolIdentityLinkDemo
~~~

Exact stdout:

~~~text
OIDC: usr-1042
SAML: usr-1042
KERBEROS: usr-2099
UNKNOWN: UNLINKED
~~~

The output shows that one OIDC pair and one SAML pair **can be intentionally linked** to the same internal user, whereas the string `lan` in a different Kerberos realm still points to a different account. Another issuer emitting `sub=lan` **must not** automatically merge into `usr-1042`.

In a production database, enforce unique keys over scheme/authority/subject/tenant, audit linking and unlinking, check account status, handle race conditions, and restrict who may perform linking.

## 14. "Protocol Translation" Means a Trust Bridge Issuing Fresh Evidence

When party A speaks only protocol X and party B speaks only Y, **never translate by changing file extensions or copying claims/headers**. Place a broker/IdP in the middle:

~~~text
Windows client -- Kerberos ---> IdP/Broker
                                  |
                                  | authenticate upstream
                                  | map user + policy
                                  | sign OIDC ID Token for the exact client
                                  v
                              OIDC Web App
                                  |
                                  | local account mapping
                                  v
                            Business session/role
~~~

Or:

~~~text
OIDC Client ---> Federation Broker ---> SAML-only SaaS
                     |
                verify OIDC login
                map namespace/user
                issue new SAML assertion
                audience = SaaS SP
                recipient = SaaS ACS
                sign with trusted SAML key
~~~

Mandatory components:

1. **Upstream trust:** the broker properly verifies incoming tickets/tokens/assertions/certificates, not merely parsing data.
2. **Identity correlation:** accurately maps users, issuers, tenants, and account lifecycles; never auto-links by email.
3. **New issuer:** the broker signs/issues downstream protocol evidence with the right audience, expiry, subject, signature/key, and assurance.
4. **Downstream validation:** the target app trusts **the broker as an authorized issuer**, never accepting an upstream token whose audience belongs to a different system.
5. **Audit, revocation, and sessions:** define when privileges are revoked, token/session TTLs, logout coordination, and broker outage handling.

A broker reduces point-to-point integrations yet becomes a **critical trust boundary**. Require HA, key rotation, scope/claim filtering, and explicit MFA/step-up policies. Never claim "multi-protocol SSO" if all you built is an endpoint forwarding a username header.

## 15. Protocol Selection Decision Tree

Follow this sequence when starting a project:

1. **Who is logging in?**
   - Employees/external users on browser/mobile → evaluate OIDC/SAML.
   - Domain-joined machines on managed intranets → evaluate Kerberos/SPNEGO or OIDC via IdP.
   - Workloads/backends → evaluate mTLS or OAuth2 client credentials.
   - Network/VPN devices → evaluate appropriate EAP/RADIUS/AAA.
2. **What is the receiving target?**
   - Web app needing a user login session → OIDC/SAML.
   - API accepting bearer access tokens → OAuth2 resource server + audience/scopes.
   - Directory needing user lookup or password check → LDAP.
   - SaaS needing account creation/locking → SCIM provisioning.
3. **Which endpoints/protocols does existing infrastructure actually support?**
   - AD DS has LDAP/KDC; it does not have OIDC by default.
   - An IdP may support OIDC, SAML, or both; check metadata, policies, and contracts.
   - SaaS apps may support only SAML, SCIM, or a configuration subset.
4. **Where are the trust boundaries?**
   - Does TLS terminate at the app or reverse proxy?
   - Who verifies issuer signatures, certificate chains, and SPN/KDC?
   - Is there a gateway/broker, and how are assertions protected?
5. **Where are stable identity and permissions handled?**
   - Choose a protocol-namespaced key and link to internal users.
   - Define permission sources, tenants, and cache/session lifetimes.
6. **What are the security/operational requirements?**
   - MFA/step-up, logout, rapid offboarding, revocation, failover, offline behavior, key rotation, auditing, BYOD devices.
   - If a requirement cannot be met with current infrastructure, add the right component or adjust the architecture rather than assuming a protocol has features it lacks.

## 16. Tests Proving Boundaries Are Not Conflated

| Test Case | Expected Result |
|---|---|
| LDAP bind succeeds, yet user lacks approval permission | Authentication succeeds; business action denied for missing authority. |
| Non-domain-joined browser attempts SPNEGO | Approved fallback login or clean rejection; self-sent headers never treated as Kerberos. |
| Kerberos ticket for service A sent to service B | Rejected as evidence for service B. |
| SAML Response issuer mismatches metadata or wrong ACS | SP rejects during SAML validation. |
| SAML assertion copied/replayed after prior use | Blocked by profile and replay protection. |
| Valid OIDC ID Token for client A sent to client B | Client B rejects for wrong audience. |
| ID Token used as bearer token to call an API | API rejects for wrong token purpose/audience. |
| Valid JWT access token for API A sent to API B | API B rejects for wrong audience, not trusting signature alone. |
| OAuth2 `client_credentials` token hits endpoint requiring end-user | Never invents a user; policy denies or requires different delegation. |
| SCIM creates user without a login session | Account exists, not treated as logged in. |
| Token carries email matching another user | Never links accounts without policy-compliant proof/consent. |
| mTLS user cert at proxy while backend sees only proxy cert | Backend does not confuse proxy for end-user; requires verified assertion. |
| Client sends `X-User: admin` header itself | Never grants admin rights or acts as federation. |
| IdP group removed while session has not refreshed | Permissions expire per policy TTL/revalidation. |
| OIDC/SAML issuer renamed or tenant migrated | Links reconciled explicitly; users never auto-merged by username. |
| IdP temporarily unreachable | System fails closed or honors valid sessions/caches per policy; never enables admin bypass. |

Test at the **exact layer**: TLS at the gateway, tokens at the authentication provider/resource server, linking at identity mapping, and resources at authorization. Seeing "the final request returned 200" does not prove every layer is sound.

## 17. Design Flaws and How to Avoid Them

**Flaw 1 — "AD has LDAP, so let's just have the new web app use LDAP."** If the goal is SSO across internal staff and external partners, direct LDAP bind forces the app to handle passwords without native web federation/MFA. Let the IdP talk to AD upstream while web apps speak OIDC/SAML.

**Flaw 2 — "SAML and OIDC only differ by JSON vs. XML."** They differ in roles, profiles, signatures, audience, sessions, redirects/bindings, response validation, and metadata. Translating protocols requires a proper issuer/broker.

**Flaw 3 — "The API accepts any token from the IdP."** Tokens must match the **specific API's** audience, type, scopes, and issuer; wrong-purpose tokens must be rejected even with a valid signature.

**Flaw 4 — "Every valid certificate is a valid employee."** CA trust is only one check; workload certs differ from user certs, and account/role mapping is still required. mTLS with a gateway authenticates the gateway, not the original end-user.

**Flaw 5 — "SCIM provisioning equals SSO."** SCIM creates/updates accounts; login requires a separate protocol/mechanism. Provisioning is not Authentication.

**Flaw 6 — "We have MFA because we use a modern protocol."** You need IdP policies and assurance/step-up verification rather than assuming it from the OIDC/SAML name.

**Flaw 7 — "Just use email as the universal key across protocols."** Emails change or get recycled, and claims vary across issuers. Use stable namespaced identifiers and approved linking workflows.

**Flaw 8 — "The backend trusts proxy headers because the header name includes Verified."** If the backend is reachable directly, header spoofing leads to account takeover. Close bypass paths, verify proxy/assertion trust, and prevent header smuggling/duplication.

**Flaw 9 — "Enabling `saml2Login`, `oauth2Login`, `httpBasic`, `formLogin`, and `jwt` together is flexible."** Multiple auth mechanisms on the same endpoints can trigger downgrades, credential exposure, chain-ordering bugs, and broken fallbacks. Define which route uses which mechanism, whether fallbacks exist, and test the threat model.

**Flaw 10 — "An app can always call downstream APIs using the user's identity."** SPNEGO delegation, OAuth2 delegated access, service accounts, and mTLS workload identity obey distinct rules; never infer user delegation from an authenticated session or acceptor ticket.

## 18. Architectural and Operational Decision Checklist

Before finalizing a solution, explicitly document:

| Question | Concrete Answer Needed |
|---|---|
| Who authenticates the user/workload? | Which IdP, KDC, directory, TLS terminator, app, or gateway? |
| Which system is the trusted issuer? | OIDC issuer URL, SAML entity ID, Kerberos realm, directory namespace, CA trust domain. |
| What role does the application play? | OIDC client, SAML SP, OAuth2 Resource Server, LDAP client, Kerberos service, mTLS server. |
| Which protocols/endpoints are supported? | Discovery, JWK, SAML metadata/ACS, LDAP DN/search, SPN/KDC, certificate profiles. |
| What is the stable identifier? | `iss+sub`, persistent SAML identifier, directory object ID, realm principal, cert SAN. |
| Where do internal permissions come from? | Approved group mapping, policy service, DB, app-specific scopes/audience, row-level rules. |
| Where is MFA/assurance enforced? | IdP/KDC/app, and how assurance levels are requested and checked on sensitive actions. |
| How do provisioning/offboarding work? | SCIM/HRIS/events, disabled accounts, revocation, session invalidation. |
| What are the network/delegation boundaries? | TLS endpoints, gateway provenance, proxy header contracts, mTLS identity, delegation/token exchange. |
| How is the lifecycle operated? | Key rotation, metadata refresh, token TTLs, clock skew, auditing, multi-tenancy, failover, rollback. |

If any row in the table remains "unknown", you lack grounds to treat two protocols as equivalent. Switch protocols only with an end-to-end tested **migration plan for identities, permissions, trust, UX, and operations**.

## 19. Summary

An organization can simultaneously use LDAP for directories, Kerberos for Windows intranets, SAML for legacy SaaS, OIDC for web/mobile, OAuth2 access tokens for APIs, mTLS for workloads, and SCIM for provisioning. That is normal because each protocol owns **different responsibilities**.

A trustworthy model follows: **select the protocol by subject and infrastructure → verify evidence at the right trust boundary → canonicalize namespaced identifiers → link to an internal principal → grant permissions per app policy → manage sessions/tokens and account lifecycles**. When bridging two protocols, an IdP/federation broker must issue fresh evidence with the proper audience and trust contract rather than renaming tokens or forwarding raw username strings.

## References

- [Spring Security — Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/): authentication mechanisms by application role, including OAuth2 Login, SAML2, X.509, and pre-authentication.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): LDAP bind/search in password-based authentication.
- [Spring Security — Kerberos/SPNEGO](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): Kerberos and SPNEGO integration with compatible domain infrastructure.
- [Spring Security — SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/IdP, RelyingPartyRegistration, assertion validation, and ACS.
- [Spring Security — OAuth2 Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/): roles of OAuth2 Client, Resource Server, and Authorization Server.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification, access tokens, and authority mapping.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-final.html): ID Tokens, `iss/sub` claims, and uniqueness limits of attributes like email.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): resource owner/client/authorization server/resource server model.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access tokens for APIs.
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): cross-domain provisioning and management of Users/Groups.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705): OAuth2 mTLS client authentication and certificate-bound tokens.
