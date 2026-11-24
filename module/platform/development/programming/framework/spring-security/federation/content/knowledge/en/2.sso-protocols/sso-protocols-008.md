# Limits on Using Login Assertions or Tickets to Call APIs

**Key takeaway:** an assertion or ticket in Single Sign-On (SSO) typically proves that a user was authenticated **for a specific service and a specific login flow**. It **does not automatically grant permission to access other APIs**. Putting a raw SAML assertion, CAS service ticket, Kerberos ticket, or OIDC ID token into `Authorization: Bearer` does not turn it into an OAuth 2.0 access token.

When integrating Spring Security, you must cleanly separate: **application login (authentication)**, **API calling authorization (authorization)**, and **application session (session)**. Having a user logged in at the IdP/SSO is only part of the security verification chain.

## 1. Where Do Assertions, Tickets, and Access Tokens Differ?

In an identity federation system, the parties typically include:

- **Identity Provider (IdP) / SSO system:** authenticates the user and issues protocol-specific evidence.
- **Relying Party (RP) / Service Provider (SP):** application that receives and validates evidence to log the user in, and may then create its own session.
- **API-calling client:** component sending HTTP requests to the API; may be a browser, mobile app, or backend.
- **Resource Server / API:** party that validates accepted credentials and enforces resource access permissions.
- **Authorization Server:** party issuing OAuth 2.0 access tokens per grant/policy; may integrate with the IdP, but does not necessarily share the same role.

Before passing a credential to an API, you must ask:

1. **Who was this evidence issued for?** For example, SAML `AudienceRestriction`, CAS `service`, Kerberos service principal, JWT `aud`.
2. **What is the evidence meant to be used for?** Web login, proving client identity, requesting tokens at a token endpoint, or accessing resources?
3. **How many times and for how long can it be used?** CAS ST allows a single validation attempt; SAML assertions have time conditions and replay protection; access tokens have their own lifetimes.
4. **How does the API know how to validate it?** SAML signatures and metadata, CAS validation, Kerberos/SPNEGO, JWT signature/claims, or OAuth introspection.
5. **What are the specific access permissions?** Scope/permission, tenant, object ownership, and business policy are required; successful identity authentication alone is not enough.

### Classification Table

| Credential | Intended purpose | Why it cannot arbitrarily call other APIs |
| --- | --- | --- |
| **SAML 2.0 assertion / Web Browser SSO SAMLResponse** | SP verifies a login event from the IdP | Has audience/recipient and conditions tied to the SP, ACS, and request; does not implicitly represent API scopes |
| **CAS Service Ticket (ST)** | One service receives the ticket and calls CAS once to verify | Strictly scoped to `service`; CAS specifies a single validation attempt whether successful or failed |
| **CAS TGT / TGC** | Maintains the SSO session with CAS | This is CAS session state, not a bearer credential to share with APIs |
| **CAS Proxy Ticket (PT)** | Proxy accesses a `targetService` through a designed CAS proxy flow | Intended only for the target service, not a universal token |
| **Kerberos service ticket** | Authenticates to a specific service principal via Kerberos | The API must be the target service and accept Kerberos/SPNEGO per protocol |
| **OIDC ID token** | RP/client verifies the user was authenticated by the IdP | Audience is typically the client ID, not a resource server; does not replace an access token |
| **OAuth 2.0 access token** | API accepts resource access authorization by audience/resource and scope | Still constrained by issuer, audience, expiry, scope, and token profile |
| **Web app session cookie** | Browser maintains a session with that web app | Standalone APIs cannot independently verify the session; cookies also carry CSRF risks |

**Terminology note:** Both CAS and Kerberos speak of "tickets," yet they are different protocols. A CAS Ticket-Granting Ticket (TGT) relates to CAS SSO; a Kerberos Ticket-Granting Ticket is also abbreviated TGT, yet serves to request Kerberos service tickets. Do not assume tickets are interchangeable.

## 2. Four Critical Limits When Using Login Credentials to Call APIs

### 2.1. Recipient Binding (audience / recipient / service)

A SAML assertion issued by an IdP for SP `urn:corp:portal` is not automatically valid for `orders-api`. A CAS ST issued for `service=https://portal.example.test/callback` is not a ticket for `https://api.example.test/orders`. A Kerberos ticket for the Portal's HTTP service likewise cannot automatically be used with an API having a different service principal.

If an API skips this binding check, a token/ticket from service A can be forwarded to B, causing **token substitution** or **confused deputy** attacks. Sharing the same organization, IdP, or `sub`/email does not substitute for verifying the exact audience.

### 2.2. Authorization Scope and Semantics

A login assertion may carry NameID, email, groups, and MFA timestamp. Those data points do not automatically mean the user is allowed to call `POST /api/payments/approve`. You must determine who granted permissions, which API they apply to, whether they are still valid, and whether they are permitted for the specific record/tenant.

OAuth access tokens typically express scope via `scope` or authorization-server-defined permissions. Even with a valid scope, the API must still enforce **object-level authorization**: for example, a user may only read orders belonging to their own tenant.

### 2.3. Time Limits and Replay Protection

- **SAML Web SSO:** assertions/responses are bound by `NotBefore`, `NotOnOrAfter`, `Recipient`, and `InResponseTo` when applicable, plus signature, request binding, and replay checks.
- **CAS ST:** per specification, valid for only **one validation attempt**; a successful authentication does not mean the ST can be reused to call hundreds of API requests.
- **Kerberos:** the service must validate the ticket and authenticator per protocol, including replay protection; do not treat a Kerberos ticket as an arbitrarily reusable bearer string.
- **OAuth access token:** usually reusable across multiple requests during its validity period, yet still requires protection since anyone possessing a bearer token can use it unless additional sender-constraining mechanisms exist.

Therefore, there is no universal rule that "an SSO ticket works until expiration"; **single-use**, **service-bound**, and **reusable** semantics vary by type.

### 2.4. Validation Method and Format

A Spring Security API using **JWT Resource Server** validates bearer tokens per JWT configuration. A SAMLResponse is a SAML/XML message, a CAS ST is typically an opaque string, and Kerberos performs a ticket/authenticator exchange. They do not become JWT access tokens merely by appearing after an `Authorization: Bearer` header.

An OIDC ID token may have valid JWT structure, yet syntactic validity and signature **do not prove** it is an *access token meant for an API*. An API must check token purpose/profile, issuer, audience, validity, and permissions per its security contract.

## 3. SAML Web Browser SSO: Assertion Used at the SP, Not a Universal Access Token

Typical SAML 2.0 Web Browser SSO model:

~~~text
User -> IdP authenticates
               |
               v
       Browser receives SAMLResponse
               |
               v
       SP / Assertion Consumer Service (ACS)
               |
         Validates SAML response
               |
               v
            SP web session
               |
               v
          SP needs to call Orders API
~~~

At the ACS step, the SP must verify the relevant elements per the profile and binding in use:

| Attribute/Check | Meaning |
| --- | --- |
| `Issuer` and trusted keys/certificates | Proof of issuance from the configured IdP |
| Signature of response/assertion per profile | Ensures integrity and issuing origin |
| `AudienceRestriction` | Assertion is targeted at the intended RP/SP |
| `SubjectConfirmationData.Recipient` | Appropriate recipient, typically the ACS endpoint |
| `InResponseTo` | Links to the login request when a corresponding request exists |
| `NotBefore`, `NotOnOrAfter` | Validity within the permitted time window |
| Request ID correlation, replay, session | Rejects stale messages or messages unrelated to the current flow |

After authentication, the SP can create a web session. However, Orders API **does not automatically become an ACS or valid audience** of that assertion. Forwarding raw `SAMLResponse` to `/api/orders` may be rejected; forcing the API to accept it without a dedicated reception design creates a security gap.

### A SAML Assertion Can Serve as Input to Request an OAuth Access Token

Distinguish **token exchange at an authorization server** from **using an assertion directly at a resource server**:

- **RFC 7522** defines a SAML 2.0 bearer assertion in OAuth 2.0 as an authorization grant and/or client authentication mechanism at the **token endpoint**. The authorization server validates the assertion and decides whether to issue an access token.
- **RFC 8693** defines OAuth 2.0 Token Exchange: a client can present a `subject_token`, token type info, target audience/resource, and desired scope; the authorization server applies policy to issue a security token suited for the target service.

These two flows **only work when the authorization server supports them and trust/policies are configured**. Spring Security `saml2Login` does not automatically mint OAuth access tokens from every SAML assertion. The newly issued access token is what the API can accept via its Resource Server mechanism.

**Bottom line:** a SAML assertion is login evidence that can be *exchanged through a controlled flow*, not a universal API credential.

## 4. CAS: Service Ticket Only for One Service and One Verification

In CAS SSO:

1. The user authenticates at CAS, potentially establishing a CAS SSO session.
2. CAS redirects the browser back to the application with a **Service Ticket (ST)** specifically for `service`.
3. The application sends the ST and `service` to the CAS validation endpoint.
4. CAS returns the result; the application can create its own session.

**CAS specification limit:** an ST is valid only for the exact service identifier used when issuing the ticket and for **only one ticket validation attempt**, even if that attempt fails. Therefore, an ST already consumed in step 3 cannot serve as a multi-use credential for another API. TGT/TGC serve CAS SSO and must never be forwarded to downstream APIs as doing so exposes the login session.

### When CAS Proxy Authentication Is Needed

CAS has its own mechanism:

~~~text
Portal authenticated via CAS ST
     |
     +-- issued a proxy-granting ticket (PGT) by CAS when eligible
                  |
                  +-- requests Proxy Ticket (PT) for targetService = Inventory API
                               |
                               +-- Inventory API validates PT with CAS
~~~

A PT is bound to a **target service**, validated via the appropriate proxy endpoint/flow, and governed by CAS policy. This does not mean every application supports proxy tickets; it requires explicit configuration and trust relationships.

When multiple modern APIs need scopes/audiences and controlled delegation, a system may choose **CAS for login + OAuth for APIs** rather than passing STs between services.

## 5. Kerberos/SPNEGO: APIs Can Use Kerberos If the API Itself Supports It

Kerberos operates via service principals and network authentication mechanisms. Over HTTP, a client can use **Negotiate/SPNEGO** to prove access to a Kerberos-configured service. Unlike OAuth bearer tokens, Kerberos involves tickets, authenticators, service keys, and replay protection.

- **Valid case:** Orders API is configured as a Kerberos acceptor matching its own service principal; the client requests a ticket for that exact service and performs standard SPNEGO negotiation. The API can authenticate via Kerberos and enforce permissions itself.
- **Invalid case:** Taking a Kerberos service ticket issued for Portal and pasting it as `Authorization: Bearer` at Orders API. The ticket is bound to Portal's service principal and is not an OAuth access token.
- **Delegation/constrained delegation:** If a backend must act on a user's behalf toward another backend, proper Kerberos delegation permissions and flows must be configured to obtain a ticket for the **target service**, never by copying Portal's ticket.

The Kerberos V5 specification also requires servers to maintain appropriate replay protection, typically a replay cache unless the application protocol provides equivalent protection. Thus, Kerberos tickets cannot be treated as standalone credentials requiring only an expiration check.

## 6. OIDC ID Token and OAuth Access Token: Both May Be JWTs, Yet Have Different Purposes

This is a very common mistake in Spring Security APIs: because OIDC ID tokens are usually JWTs, development teams assume the API merely needs to decode the JWT.

| Type | Recipient and purpose | Send to a resource server as a bearer token? |
| --- | --- | --- |
| **OIDC ID token** | RP/client learns the user was authenticated; `aud` usually binds to `client_id` | **Do not use in place of an access token** |
| **OAuth access token** | Targeted API/resource server; scope or policy expresses permissions | **Yes**, when type, issuer, audience, and permissions match |
| **OAuth refresh token** | Client uses at token endpoint per refresh grant rules | **No** |
| **Web session cookie** | Issued and controlled by the web app for session state | Not directly usable at other APIs; if an API shares cookies, design CSRF/sessions carefully |

Illustrative example:

~~~text
ID token:
    aud = portal-web-client
    sub = user-123
    purpose = RP confirms the user logged in

Access token:
    aud = orders-api
    sub = user-123
    scope = orders.read
    purpose = access Orders API per granted permissions
~~~

Sharing the same `sub` does not make the two tokens interchangeable. If Orders API only verifies the signature and ignores `aud` and token type, an ID token meant for the portal could be mistakenly accepted at the API: this is the **token confusion** vulnerability.

Access tokens do not have to be JWTs: they can also be opaque tokens, in which case the resource server typically uses **introspection** per an agreed protocol. Systems using JWT access tokens must verify the signature and required claims; where JWT Profile for OAuth 2.0 Access Tokens (RFC 9068) applies, check the corresponding profile/token type.

## 7. Appropriate Architectures for Calling APIs After SSO

### 7.1. Browser/Mobile Client Receives an OAuth Access Token for the API

~~~text
User --SSO at IdP--> Authorization Server
                           |
                 OAuth Authorization Code + PKCE
                           |
                           v
                  Client receives access token
                           |
         Authorization: Bearer (token for Orders API)
                           |
                           v
                   Orders Resource Server
                 verifies aud, scope, data permissions
~~~

The client requests appropriate resources/scopes; the authorization server decides issuance based on grant, consent, and policy. The ID token (if present) serves login into the OIDC client. The API accepts only **access tokens meant for itself**.

### 7.2. Server-Side Web App Uses SAML SSO, Backend Needs to Call an API

~~~text
Browser --SAML SSO--> Portal (SP)
                          |
                     Portal Session
                          |
             Portal Backend needs to call Orders API
                          |
             Request access token via supported flow
             (delegation/token exchange/bridge...)
                          |
                          v
                      Orders API
~~~

Portal does not forward the raw `SAMLResponse` or the IdP's SSO cookie to Orders API. If the API must act **on behalf of the user**, the system needs a permitted mechanism to convey identity/permissions (e.g. SAML bearer grant or OAuth token exchange when supported by all parties). If the API performs work **on behalf of the backend**, OAuth client credentials may fit, though that credential **does not carry end-user permissions or identity**.

A BFF (Backend for Frontend) pattern can keep a session cookie between browser and BFF while the BFF uses access tokens when calling downstream APIs. The BFF still requires CSRF protection on endpoints authenticated via cookies.

### 7.3. CAS Proxy or Kerberos

If the system has standardized on CAS proxy tickets or Kerberos/SPNEGO for the exact backend, apply that protocol with the explicitly declared target service/SPN. This is a conditional architectural exception; never turn a web ST or service ticket into a universal bearer token.

### 7.4. Service-to-Service Without a User

A backend running sync jobs to call APIs can use client credentials or workload identity. Application permissions must stay separate from user permissions. When business logic requires auditing "who requested the change?", a standalone client-credentials token cannot replace user identity and delegation.

## 8. Spring Security: Configuring Resource Server to Accept the Right Access Token

Example of a **Spring Boot 3.x servlet API** on Java 17+ protecting `/api/orders`. The project needs Spring Web, Spring Security, and `spring-boot-starter-oauth2-resource-server` dependencies; the authorization server must issue JWT access tokens with audience `orders-api` and corresponding scopes.

Create `src/main/java/com/example/security/ApiSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/oauth
          audiences:
            - orders-api
~~~

**Explanation:**

1. `oauth2ResourceServer(...jwt(...))` protects the API using **JWT bearer access tokens**. There is no step that treats a SAML assertion or CAS ST as a JWT.
2. `issuer-uri` specifies the trusted issuer for locating verification configuration/keys and checking the issuer; `audiences` requires the JWT to carry the **Orders API** audience. Configuring only the issuer **does not replace** audience validation.
3. Spring Security by default typically maps scopes in the `scope` or `scp` claim to authorities prefixed with `SCOPE_`; the two rules express read and write permissions. The API must still check business permissions per order.
4. `STATELESS` and disabling CSRF in this example **apply only to a pure bearer-token API, not authenticating requests with browser cookies**. If the same application also has `saml2Login`/`oauth2Login`, forms, or session cookies, split `SecurityFilterChain` by path and enforce CSRF protection on cookie-authenticated endpoints.
5. The illustrative `example.test` URL is not a live issuer. In deployment, use the organization's real issuer and audience, along with API controllers, an authorization server, and valid keys.

This is a **configuration class for a Spring Boot project**, not a standalone Java program runnable directly with `javac` and `java`; it produces no fixed stdout. The code is written for Spring Security 6.x and Java 17+, requiring a project with appropriate dependencies declared. If the authorization server issues **opaque tokens**, configure Resource Server introspection instead of a JWT decoder.

Client example calling the API **after obtaining a valid access token** and storing it in the `ACCESS_TOKEN` environment variable:

~~~bash
curl --fail-with-body --header "Authorization: Bearer $ACCESS_TOKEN" "https://api.example.test/api/orders"
~~~

The command above does not log in or mint tokens on its own. The `ACCESS_TOKEN` variable must hold a **valid OAuth access token for Orders API**. Do not substitute an OIDC ID token, SAMLResponse, CAS ticket, Kerberos service ticket, or refresh token.

### Distinguishing the Three Spring Security Feature Groups

- **`saml2Login`:** SP/RP handling SAML Web Browser SSO, authenticating the user and creating an application login context.
- **`oauth2Login`:** client/RP handling OAuth2/OIDC login flows; for OIDC, verifying ID tokens per OIDC rules.
- **`oauth2ResourceServer`:** API receiving and validating bearer access tokens (JWT or opaque per configuration) to protect resources.

An application can use multiple groups, yet each flow has distinct responsibilities and security requirements. **Do not use login configuration to assume an API automatically receives tokens or authorization.**

## 9. When an API Intentionally Accepts Assertions or Tickets: Mandatory Conditions

There is no absolute rule that an API can *never* authenticate with SAML, CAS, or Kerberos. An API may accept a credential under a specific profile if **it was explicitly designed as a valid recipient**. Before implementing, you must have:

1. **Protocol contract:** clearly specify endpoint, credential type, profile/binding, transport method, and verification method; never guess credential type based on whether a string looks like a JWT.
2. **Trusted origin:** trust only configured and verified issuers, certificates, keys, CAS servers, or Kerberos realms/services.
3. **Exact recipient:** audience, recipient, service identifier, or SPN must be the target service; reject tickets issued for other applications.
4. **Validity and replay protection:** lifetimes, request/response binding, one-time ticket validation, and nonces/authenticators when required by the protocol.
5. **Separate authorization:** check roles/permissions/scopes, tenant, ownership, and business rules; avoid confusing login success with API administrative privileges.
6. **Credential protection:** TLS, cookie flags, never logging tokens/assertions or placing them in URLs outside protocol-mandated cases; manage key rotation and verification failures.
7. **Lifecycle:** design expiration, revocation, logout, deprovisioning, and behavior when the IdP/CAS/authorization server experiences an outage.
8. **Genuine support:** if using RFC 7522, RFC 8693, CAS proxy, or Kerberos delegation, the client, server, and token-issuing system must all support it accurately with appropriate issuance policies.

For public APIs or microservices supporting OAuth, **issuing access tokens with appropriate audience/scopes** is usually easier to operate and authorize than teaching every API to accept every type of login evidence.

## 10. Common Integration Errors

| Symptom | Typical cause | Remediation |
| --- | --- | --- |
| SAMLResponse sent in Bearer header, API returns `401` | API does not support SAML assertions; JWT decoder cannot parse SAML | Design an access-token issuance/bridge flow or a valid SAML API profile |
| CAS ST used for login, second validation fails | ST allows only one validation, bound to the exact service | Do not reuse STs; consider CAS PT for the target service |
| API rejects Kerberos ticket | Wrong service principal, key, SPNEGO config, clock skew, or replay | Verify SPN, acceptor, keytab, and delegation policy |
| API receives JWT but returns `401` | Wrong `iss`, `aud`, expired, invalid signature, or wrong token type | Check evidence and configure the API accurately |
| Passing OIDC ID token to API is rejected | Token is for RP/client, not an API access token | Request the right OAuth access token for the target audience/resource |
| API returns `403` after valid token | Missing scope or business permission | Check `SCOPE_` mapping, object/tenant authorization |
| User logs out of Portal yet API token remains valid | Web session and API token have independent lifecycles | Appropriate TTL, revocation/introspection, and logout policies |

**About status codes:** `401 Unauthorized` typically indicates missing or unauthenticated credentials; `403 Forbidden` typically indicates authenticated identity lacking sufficient permissions. Actual error responses depend on Spring Security and endpoint configuration.

### Self-Check Questions

**Question 1:** The IdP issues a SAML assertion for Portal. The assertion includes email and group "admin." Should Orders API accept the raw assertion to approve orders?  
**Answer:** Not by default. It must verify the assertion is intended for that exact API, supported by the API under a valid profile, still valid/replay-protected, and authorized by business rules. Usually a separate access token is needed.

**Question 2:** A CAS ST was successfully validated by Portal. Can that ST be reused to call Inventory API?  
**Answer:** No. The ST was consumed by the validation attempt and is also bound to the original service. CAS proxy requires a PT suited for the target service.

**Question 3:** A JWT has a valid signature and `sub=user-123`, yet `aud=portal-client`; Orders API requires `aud=orders-api`. Should it be accepted?  
**Answer:** No. Valid signature and subject do not compensate for a mismatched audience.

**Question 4:** Can an API authenticate using Kerberos?  
**Answer:** Yes, if the API is the target service configured for Kerberos/SPNEGO and properly validates tickets/authenticators per standard. A ticket from another service must not be reused as a generic bearer token.

**Question 5:** A backend holds an access token from the client-credentials grant. Can the API treat that token as proof that "employee A consented"?  
**Answer:** Not automatically. Client credentials represent application authority; a delegation/on-behalf-of flow is required to act on behalf of a user.

## 11. Design and Testing Checklist

- [ ] Identify the credential type at each hop: SAML assertion, CAS ST/PT, Kerberos, ID token, OAuth access token, or session cookie.
- [ ] Every credential has a valid purpose, issuer, and **service/audience** verified by the receiving party.
- [ ] Separate authentication from authorization by scope, role, tenant, and business object.
- [ ] For OAuth APIs, the client requests tokens for the exact resource; the API verifies signature/introspection, issuer, audience, and lifetime.
- [ ] Never reuse CAS STs; never pass service A's SAML assertion or Kerberos ticket to B.
- [ ] If bridging/delegation is needed, verify all parties genuinely support RFC 7522, RFC 8693, CAS proxy, or Kerberos delegation.
- [ ] Protect tokens, assertions, tickets, and cookies from leakage in logs, URLs, and client storage.
- [ ] Enforce CSRF policies for cookie-based flows; protect API bearer tokens appropriately.
- [ ] Handle `401`/`403` errors, expiration, logout, and permission revocation properly.

## 12. Takeaways

**Valid login evidence is not enough to prove permission to call an API.** Confirm **which recipient** it was issued for, for **what purpose**, **how long/how many times** it can be used, **how** it is validated, and **what permissions** it grants.

In Spring Security applications, keep SAML/OIDC/CAS/Kerberos login and OAuth Resource Server APIs cleanly separated. To call APIs after SSO, request or exchange for the proper access token, or implement a fully agreed specialized API authentication protocol. Never pass raw login assertions/tickets around arbitrarily.

### Official Documentation

- Spring Security 6.5 – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security – SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/
- Spring Boot – OAuth2 Resource Server configuration: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- RFC 7522 – SAML 2.0 Assertion Profile for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc7522
- RFC 8693 – OAuth 2.0 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
- RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- Apereo CAS – CAS Protocol Specification: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- RFC 4120 – Kerberos Network Authentication Service (V5): https://www.rfc-editor.org/rfc/rfc4120
