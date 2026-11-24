# Distinguishing Service Provider, Relying Party, CAS Service, and Resource Server

> **Context:** Single Sign-On (SSO) protocols and federation in the Spring Security ecosystem. The four terms below describe **an application's role within a specific protocol**, not four server types that must be deployed separately.

## 1. Big Picture

When an application uses a central identity system, it must identify **who authenticates the user**, **what evidence the application receives**, **who the evidence is intended for**, and **what the application does after verifying that evidence**. Standards use different terminology:

| Role | Common protocol/context | Issuing or validating party | Evidence received by application | Primary purpose |
| --- | --- | --- | --- | --- |
| **Service Provider (SP)** | SAML 2.0 Web SSO | Identity Provider (IdP, also called *Asserting Party*) | `SAML Response` containing an `Assertion` | Log users into the application based on identity assertions from the IdP |
| **Relying Party (RP)** | OpenID Connect (OIDC); the term is also used in SAML | OpenID Provider (OP) | `ID Token` and OIDC flow output | Authenticate user identity to create an application login session |
| **CAS service** | Central Authentication Service (CAS) protocol | CAS server | `Service Ticket` (`ST`), requiring verification with the CAS server | Log users into a CAS-integrated application |
| **Resource Server (RS)** | OAuth 2.0 | Authorization Server (AS) issuing `Access Token` | `Access Token`, typically via HTTP `Authorization: Bearer ...` | Protect data/APIs and decide whether to permit resource access |

**Important note on terminology:** `Relying Party` is not exclusive to OIDC. In Spring Security SAML documentation, *Service Provider* and *Relying Party* are two terms used for the same SAML role; hence the class `RelyingPartyRegistration` is used to configure a **SAML Service Provider**. When comparing protocols, people often call a **SAML application an SP** and an **OIDC application an RP** for clarity; that is an expository convention, not an absolute boundary in the terminology.

## 2. Service Provider: The Party Using a SAML Assertion to Log In

In **SAML 2.0**, the SP is the application that needs to know the accessing user has been authenticated. The SP places trust in the IdP per prior configuration: `entityID`, metadata, signing certificates, endpoints, and protocol policies.

Typical **SP-initiated Web SSO** flow:

1. The user visits a login-protected page on the SP.
2. The SP creates an `AuthnRequest` and redirects the browser to the SAML IdP; the request may be signed depending on configuration and IdP requirements.
3. The IdP authenticates the user or uses an existing SSO session, then issues a `SAML Response` containing an `Assertion`.
4. The browser sends the response to the SP's **Assertion Consumer Service (ACS)**, usually via HTTP POST.
5. The SP verifies the signature and issuer, time conditions, `AudienceRestriction`, `Recipient`, `Destination`, `InResponseTo`, and constraints applicable to the flow used, while also preventing replay.
6. When valid, the SP establishes its own application `Authentication`/session and performs **internal authorization**.

A `SAML Assertion` is an identity/attribute statement with a specific context and intended recipient; it is **not automatically an OAuth Access Token** for arbitrary REST APIs. Do not confuse the SP with the IdP: **the IdP authenticates and issues assertions; the SP receives and verifies them**.

**Spring Security indicators:** dependency `spring-security-saml2-service-provider`, configuration `spring.security.saml2.relyingparty.registration`, `RelyingPartyRegistrationRepository`, and `http.saml2Login(...)`. The ACS endpoint typically follows `/login/saml2/sso/{registrationId}` (customizable).

## 3. Relying Party: Application Logging In via OpenID Connect

In **OpenID Connect**, the RP is an **OAuth 2.0 client that adds the OIDC identity authentication layer**. The OP authenticates the user; the RP relies on that result to know who the user is. The RP is typically a website or backend-for-frontend holding browser sessions.

Typical **OIDC Authorization Code** flow:

1. The user chooses to log in; the RP redirects the browser to the OP's authorization endpoint with `client_id`, `redirect_uri`, `scope` containing `openid`, `state`, and appropriate parameters (e.g. `nonce`; using PKCE per client policy).
2. The OP authenticates the user and redirects the browser back to `redirect_uri` with an **authorization code**.
3. The RP checks `state` and exchanges the code at the OP's token endpoint, using the appropriate client authentication/PKCE mechanism.
4. The RP receives an **ID Token** (typically a JWT) and may receive an **Access Token**, verifying signature, `iss`, `aud`, `exp`, `nonce` when used, and other conditions per OIDC.
5. The RP establishes the user's identity (typically based on the `iss` + `sub` pair) and creates an application session. If additional details are needed, the RP can use the Access Token to call the **UserInfo Endpoint** per the specification and OP policy.

**Distinguishing the two tokens received together:** the **ID Token** is issued for the **RP** to report the authentication result; the **Access Token** is issued for the client to call the corresponding **Resource Server**. Do not take the ID Token and send it as a Bearer token to an API just because both can be JWTs. Nor should `email` be treated as an immutable identifier key across systems.

In Spring Security, `oauth2Login(...)` provides OAuth 2.0/OIDC-based login; to act as an **OIDC RP**, the registration needs an OIDC provider and the `openid` scope. Common components: `ClientRegistrationRepository`, `OAuth2AuthorizedClient`, `OidcUser`, `OidcIdToken`, and default callback `/login/oauth2/code/{registrationId}`.

**Do not equate them:** OAuth 2.0 itself defines **resource access authorization**, and does not standardize user identity assertions like OIDC. An OAuth client that does not request `openid` is not necessarily an OIDC RP.

## 4. CAS Service: Application Receiving Service Tickets from a CAS Server

In the **CAS** protocol, a *CAS service* means an **application protected by CAS**, using a CAS client or equivalent integration mechanism. `service` is also the parameter identifying the application's login callback URL/endpoint. It **differs from the CAS server**: the CAS server performs centralized authentication and issues tickets.

Basic CAS flow:

1. The user accesses the application; the CAS service sees no local session.
2. The application redirects the browser to `https://sso.example.org/cas/login?service=<application-URL>` (the `service` URL must be properly URL-encoded).
3. The CAS server authenticates the user or recognizes their SSO session via a **Ticket Granting Cookie (TGC)** linked to a **Ticket Granting Ticket (TGT)**.
4. The CAS server redirects the browser back to the exact `service`, with query parameter `ticket=ST-...`.
5. The CAS service backend sends both `service` **and** `ticket` to the CAS server's validation endpoint, such as `/serviceValidate` or `/p3/serviceValidate`. The CAS server returns the result and identity/attributes if valid.
6. The application establishes its own session and applies its own access permissions. **A Service Ticket is single-use and bound to a specific service**; it must not be treated as an access token reusable across different APIs.

Illustrative exchange example (URLs in the example are hypothetical; `ST-xyz` is not a real ticket):

```http
GET /cas/login?service=https%3A%2F%2Flegacy.example.org%2Flogin%2Fcas HTTP/1.1
Host: sso.example.org

# After authentication, the browser is redirected to:
# https://legacy.example.org/login/cas?ticket=ST-xyz

GET /cas/serviceValidate?service=https%3A%2F%2Flegacy.example.org%2Flogin%2Fcas&ticket=ST-xyz HTTP/1.1
Host: sso.example.org
```

The third part is **the CAS service backend calling the CAS server**, not an API where the end user authenticates directly with an ST. When validation fails, the service must reject the login; never trust `ticket` merely because it appears in the URL.

In Spring, CAS can be integrated via a CAS client and components matching your project's version. Check actual CAS/Spring Security library compatibility; do not use `oauth2Login` or `saml2Login` configuration and casually call it the CAS protocol.

## 5. Resource Server: API Controlling Access with OAuth Access Tokens

In **OAuth 2.0**, a Resource Server is the server hosting/handling requests to **protected resources** (e.g. `GET /api/orders`). The Authorization Server issues Access Tokens to clients, while the Resource Server **validates Access Tokens** before serving data. An RS does not need to provide its own login UI or directly ask for user passwords.

Typical flow:

1. The client obtains an Access Token from the Authorization Server via an appropriate grant.
2. The client calls the API: `Authorization: Bearer <access-token>`.
3. The RS validates the token: for JWTs, typically validating signature via public keys/JWKS, `iss`, `exp`/`nbf` timestamps, and **`aud` intended for this API**; for opaque tokens, it may query the AS's **introspection** endpoint.
4. The RS checks the endpoint's scope/permissions/business context, e.g. `orders.read`; a valid token **does not mean** every operation is permitted.
5. The RS returns the resource, or HTTP `401 Unauthorized` when unauthenticated/invalid, or `403 Forbidden` when authenticated but lacking permission (depending on handler configuration).

Example request:

```http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...
```

**An RS is not an Authorization Server:** the AS issues tokens and defines permissions granted to the client; the RS accepts tokens and protects resources. An RS may not be an IdP/OP. **JWT is a token format, not a login protocol**; you must determine whether it is an ID Token or an Access Token and check the exact `aud`/purpose. When a token is bound to another API, the RS must reject it even if the signature is valid.

In Spring Security, the common configuration pair is `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` for JWTs, or opaque-token introspection; default authorities derived from scopes carry the `SCOPE_` prefix. When protecting an API, declare the issuer, audience, and specific authorization rules.

## 6. Comparison by Trust Flow

```text
SAML:
Browser -> SAML SP -> IdP -> (SAML Response via browser) -> SP/ACS
                                                       -> SP session

OIDC:
Browser -> OIDC RP -> OP -> (authorization code via browser) -> RP
RP -> OP/token endpoint -> ID Token (+ Access Token) -> RP session

CAS:
Browser -> CAS service -> CAS server -> (ticket=ST via browser) -> service
CAS service -> CAS /serviceValidate(service, ST) -> service session

OAuth 2.0 API:
Client -> Authorization Server -> Access Token
Client -> Resource Server (Authorization: Bearer Access Token) -> API response
```

You can remember this via the question **"which evidence, and who must verify it?"**: the SP verifies the **SAML Assertion** per SAML trust; the OIDC RP verifies the **ID Token** from the OP; the CAS service **exchanges/verifies the Service Ticket** with the CAS server; the OAuth Resource Server verifies the **Access Token** meant for its own resources. All four must still enforce authorization according to application needs.

## 7. The Same System Can Hold Multiple Roles

Suppose an enterprise has:

- **HR portal using SAML:** the portal acts as **SP**, and the enterprise identity provider is the **IdP**.
- **Customer site using OIDC:** the site acts as **RP**; the identity provider is the **OP**. The site can simultaneously act as an **OAuth client** when calling APIs.
- **Legacy app using CAS:** the app is a **CAS service**, and the CAS server issues and validates Service Tickets.
- **Orders API:** the backend is an **OAuth Resource Server**, accepting Access Tokens with matching audience/scopes.

A single Spring Boot application can certainly be both an **OIDC RP** for web login and a **Resource Server** for `/api/**`. The two roles serve **two request types** and must use appropriate authentication mechanisms. The illustrative Java 17+ configuration example below is for **a Spring Boot project with Web, Spring Security, OAuth2 Client, OAuth2 Resource Server, and JOSE dependencies**; this is a configuration class inside an application, **not a standalone Java program run with plain `javac`**.

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityRoleConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Corresponding Spring Boot configuration (URIs are illustrative; environment variables must be supplied at runtime):

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: https://login.example.org/realms/corp
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope: [openid, profile, email]
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/corp
          audiences: https://api.example.org/orders
```

**How to read the example:** The filter chain with `@Order(1)` takes precedence for `/api/**`, reads a **Bearer Access Token**, and requires authority `SCOPE_orders.read` for GET order requests. The web chain uses `oauth2Login` for browser sessions and, because the registration includes `openid`, acts as an **OIDC RP**. Having the same `issuer-uri` does not turn the **web's ID Token** into an Access Token for the API; the API still requires the matching `aud`. Disabling CSRF applies only to the stateless Bearer-token API chain; cookie-authenticated web login still requires CSRF protection under appropriate configuration.

If deploying a **SAML SP** instead of an OIDC RP for the website, configuration centers on `RelyingPartyRegistration` and `saml2Login`; that is **a different login protocol**, which cannot be swapped by renaming tokens. If using a **CAS service**, you must validate CAS STs with the CAS server per the CAS protocol rather than treating them as JWT/OAuth bearer tokens.

## 8. Common Misconceptions and Self-Checks

| Common misconception | Accurate understanding |
| --- | --- |
| "Relying Party is definitely OIDC, and SP is definitely not RP." | RP is also a term for SP in SAML contexts; Spring SAML has `RelyingPartyRegistration`. Look at the protocol and evidence type. |
| "CAS service is the CAS server." | The CAS **server** authenticates and issues tickets; a CAS **service** is the protected application that receives an ST and calls the CAS server to validate it. |
| "Resource Server authenticates users with a login screen." | An RS normally authenticates **API requests using Access Tokens**; login screens belong to the client/RP, IdP/OP, or CAS server. |
| "If you have a JWT, reuse it for both login and API calls." | Must distinguish whether a JWT is an **ID Token** or **Access Token**, with the right issuer, audience, scope, and intended purpose. |
| "A valid Access Token can access every endpoint." | The RS needs authorization by scope/authority and business policy; an unexpired token does not imply sufficient permissions. |
| "SSO means all applications share one HTTP session." | SSO shares login state at the identity provider; each SP/RP/CAS service typically maintains its **own application session**. |
| "A SAML assertion or CAS ST can be put in a Bearer header to call an OAuth API." | There is no default equivalence; if needed, use an explicitly designed and controlled token exchange/gateway mechanism. |

**Checklist when designing or reading code:**

1. Identify the running **protocol**: SAML, OIDC, CAS, or OAuth API protection.
2. Identify **who issues/certifies** the evidence and **which application is the intended recipient**.
3. Identify the **artifact type**: SAML Assertion, OIDC ID Token, CAS ST, or OAuth Access Token.
4. Check the corresponding **security constraints**: signature, issuer, audience/service/recipient, timestamps, state/nonce, or replay protection, depending on protocol.
5. Determine whether the application creates a **browser session** or answers **API requests**, and configure authorization separately.

## 9. Reference Documentation

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — cross-check SP/RP terminology and SAML flow.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — RP, OP, ID Token, and verification.
- [Apereo CAS — CAS Protocol](https://github.com/apereo/cas/blob/master/docs/cas-server-documentation/protocol/CAS-Protocol.md) — CAS service, server, TGT/TGC/ST.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749) — client, Authorization Server, and Resource Server roles.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `issuer-uri`, `aud`, and access token validation.
