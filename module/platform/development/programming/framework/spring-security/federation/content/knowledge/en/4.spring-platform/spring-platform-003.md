# Distinguishing Servlet, WebFlux, and External Extension Support by Protocol

> **Topic:** Spring Security – federation. **Knowledge group:** Spring Platform. This lesson answers the practical question: for a given SSO/federation protocol, does Spring Security support it directly on **Servlet** or **WebFlux**, require an **integration module**, or require an **external library/platform**? The content follows the categorization and APIs presented in Spring Security 7.1 documentation; projects running Spring Security 6.x or other versions must verify against that exact version.

## 1. Three Levels of "Support" to Distinguish

Saying "Spring supports SSO login" can mean three very different things:

1. **Official built-in feature on the matching web stack:** Spring Security provides the authentication components and appropriate DSL, such as `HttpSecurity.oauth2Login()` or `ServerHttpSecurity.oauth2Login()`. Client/IdP registration and network configuration are still required.
2. **Dedicated integration module for Spring Security:** An artifact providing filters, providers, validators, or configuration helpers that still require wiring multiple beans, such as CAS components or Spring Security Kerberos. Having a module does not mean every web stack shares the same DSL.
3. **External to the application's Spring Security:** An Identity Provider (IdP), OpenID Provider (OP), CAS Server, KDC/Active Directory, identity broker, authenticating reverse proxy, or third-party library. Spring Security can **receive/verify** the login result from such a system without implementing the full protocol server itself.

Therefore, you must answer **all four questions**: (1) is the application a **client/SP/RP**, **API Resource Server**, or **IdP/OP/server**; (2) does the application use **Spring MVC/Servlet** or **Spring WebFlux**; (3) which protocol; (4) which Spring Security version and artifacts.

**Distinguishing examples:** `saml2Login()` authenticates users in a **Servlet application acting as a SAML Service Provider (SP)**; it does not turn the application into a SAML Identity Provider. `oauth2ResourceServer().jwt()` validates access tokens for APIs, not OIDC login or a token-issuing server. `spring-security-kerberos-web` adds SPNEGO integration; the KDC remains external.

## 2. Servlet and WebFlux: Two HTTP Protection Architectures

| Criterion | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| HTTP input | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange`, Reactor publishers |
| Security chain | `SecurityFilterChain`, `FilterChainProxy`, and servlet `Filter` | `SecurityWebFilterChain`, `WebFilterChainProxy`, and `WebFilter` |
| Configuration DSL | `HttpSecurity` with `authorizeHttpRequests` | `ServerHttpSecurity` with `authorizeExchange` |
| Principal / context | `SecurityContextHolder` and per-request/thread context per framework mechanism | `ReactiveSecurityContextHolder` in **Reactor Context** |
| OIDC/OAuth2 login | `oauth2Login`, `ClientRegistrationRepository` | `oauth2Login`, `ReactiveClientRegistrationRepository` |
| Bearer JWT API | `JwtDecoder`, `oauth2ResourceServer` | `ReactiveJwtDecoder`, `oauth2ResourceServer` |
| Security testing | `MockMvc` and `spring-security-test` | `WebTestClient` and `spring-security-test` |
| Risk when mixing stack APIs | Servlet `Filter` does not automatically run in a reactive chain | `WebFilter` does not automatically run in a servlet filter chain |

**Important:** Having a method named `oauth2Login` on both stacks does not mean they share every class and extension point. For example, the servlet API uses `AuthenticationSuccessHandler` and servlet filters; reactive uses `ServerAuthenticationSuccessHandler` and `WebFilter`. A CAS filter written for `HttpServletRequest` cannot simply be dropped into `SecurityWebFilterChain`.

Adding the `spring-webflux` dependency just to use **WebClient** inside an MVC application **does not automatically switch** the server side to WebFlux. When both Spring MVC and WebFlux starters are present, Spring Boot normally prioritizes MVC unless configured to change the application type; determine the actual server stack by checking dependencies, application type, and which security chain gets created.

### Version Milestone

Starting with **Spring Security 7**, Spring Authorization Server and Spring Security Kerberos are brought into the main Spring Security ecosystem; they still have their respective functional artifacts and dedicated configuration. For Spring Security **6.x**, consult the 6.x branch documentation because artifacts, APIs, or integration mechanisms may differ. Calling something "official" below follows **Spring Security 7.1 documentation/APIs**, and does not imply every third-party solution is certified across all versions.

## 3. Support Matrix by Protocol and Role

Legend: **Yes** = Spring Security provides official APIs/features for that stack; **Module** = dedicated module exists requiring integration configuration steps; **External/Custom** = requires a broker, reverse proxy, adapter, or custom code, with no equivalent DSL provided by that stack's documentation.

| Protocol / Role | Servlet (Spring MVC) | WebFlux Reactive | External / Responsibility Boundary |
|---|---|---|---|
| **OIDC Login (RP)** | **Yes**: `oauth2Login`; OAuth2 Client | **Yes**: `oauth2Login`; Reactive OAuth2 Client | Requires an OP/IdP issuing ID Tokens; configure issuer, client, redirect URI |
| **OAuth2 Client** calling APIs | **Yes**: `oauth2Client`, authorized-client manager | **Yes**: `oauth2Client`, reactive authorized-client manager | Requires an Authorization Server/token endpoint |
| **OAuth2 Resource Server** JWT/opaque | **Yes**: `oauth2ResourceServer` | **Yes**: `oauth2ResourceServer` | Requires issuer/JWKS or introspection server; this is API token validation |
| **OAuth2/OIDC Authorization Server** | **Dedicated server module/feature** on Servlet | **No equivalent WebFlux branch in current official documentation** | Spring Authorization Server / external OP; do not confuse RP with OP |
| **SAML 2.0 SP (login)** | **Yes**, `spring-security-saml2-service-provider` module, `saml2Login` | **External/Custom**; no equivalent `ServerHttpSecurity.saml2Login` | Requires SAML IdP and metadata/certificates/ACS; broker if WebFlux app |
| **SAML IdP** | Not a feature of Spring Security SP `saml2Login` | No SAML IdP feature from `oauth2Login` | Use an IdP such as Keycloak, AD FS, Entra ID, or Apereo CAS with SAML support |
| **CAS protocol (service)** | **Servlet Module/Integration**: `spring-security-cas` and CAS client ticket validator | **External/Custom**; no equivalent reactive CAS DSL in reference | Requires CAS Server, `service` registration, Service Ticket validation |
| **Kerberos/SPNEGO for web app** | **Module**: Spring Security Kerberos (7.x: `spring-security-kerberos-core/web`) wiring servlet filter/provider | **External/Custom**; no equivalent WebFlux SPNEGO DSL | Requires KDC/AD, SPN, keytab, browser/proxy configuration |
| **AD/LDAP auth via username/password** | Corresponding directory providers/integrations | Can integrate reactive auth/LDAP via supported APIs/approaches | **LDAP is not Kerberos/SSO by default** |
| **Broker bridging SAML/CAS/Kerberos → OIDC** | App acts as **OIDC RP** via `oauth2Login` | App acts as **OIDC RP** via `oauth2Login` | Broker handles upstream protocol and issues OIDC tokens to the app |

**How to read the matrix:** "OIDC on WebFlux is supported" does not imply "native SAML/CAS/Kerberos on WebFlux is supported"; "the SAML module runs in the JVM" does not imply "SAML filters run as a reactive `WebFilter`"; "Spring Security includes Authorization Server" does not imply "an application using `oauth2Login` can issue ID Tokens to other apps".

## 4. OpenID Connect/OAuth2: Supported Across Both Stacks

### 4.1. Distinguishing Three OAuth2/OIDC Roles

- **OIDC Relying Party (RP):** web application that redirects the browser to the OP, receives an authorization code, exchanges tokens, validates the **ID Token**, and creates a user session. Both Servlet and WebFlux have `oauth2Login`.
- **OAuth2 Client:** application that requests/holds access tokens to call another resource server. Both stacks have `oauth2Client`; the APIs/managers are synchronous or reactive respectively.
- **OAuth2 Resource Server:** backend receiving `Authorization: Bearer ...` and **validating the access token** for issuer, signature, audience, expiry, and permissions. Both stacks have `oauth2ResourceServer` with JWT or opaque-token introspection.

`id_token` is identity proof **intended for the RP**; never use it directly as an access token to call APIs. For OIDC Login, use Authorization Code + PKCE where appropriate; verify `state`, registered redirect URIs, ID Token, issuer/audience, and handle sessions/logout cleanly.

### 4.2. Servlet Example — Configuring OIDC and SAML SP

The Java snippet below is **a Spring Security configuration class in a Spring Boot Servlet project**, compilable once appropriate dependencies are added. At minimum it needs `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, and `spring-security-saml2-service-provider` compatible with the current Spring Boot release. Actual login requires configuring valid OIDC client and SAML relying party registrations (see Section 5).

File `src/main/java/com/example/security/ServletSsoSecurity.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSsoSecurity {

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Why this matches the stack:** `HttpSecurity` builds a `SecurityFilterChain` running with Servlet `Filter`s. `oauth2Login` uses OAuth2/OIDC client registrations; `saml2Login` uses SAML relying-party registrations. These are two distinct authentication options that can each produce an `Authentication` for the application to authorize against. Combining both in one application may produce a login selection page; exact behavior depends on registration count and login page setup.

### 4.3. WebFlux Example — OIDC and Bearer JWT API

The snippet below belongs to **a separate WebFlux project**, not combined with the Servlet class above. Typical dependencies are `spring-boot-starter-webflux`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, and `spring-boot-starter-oauth2-resource-server`.

File `src/main/java/com/example/security/ReactiveSsoSecurity.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSsoSecurity {

    @Bean
    SecurityWebFilterChain appSecurity(ServerHttpSecurity http) {
        http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public", "/error").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Why this matches the stack:** `ServerHttpSecurity` configures `SecurityWebFilterChain` instead of Servlet filters. `oauth2Login` protects user requests via the OP; `oauth2ResourceServer().jwt()` validates API Bearer tokens. When sharing paths, verify how `AuthenticationEntryPoint` is chosen (HTML redirect vs HTTP 401) so API clients are not accidentally redirected; usually separate chains are used for `/api/**` and web routes.

Example OIDC client configuration (used for **one** of the two projects; in WebFlux Boot creates a reactive client registration):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: demo-client-id
            client-secret: REPLACE_USING_SECRET_MANAGER
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: https://login.example.org/realms/corp
~~~

To use JWT Resource Server as in the WebFlux example above, add the **API access token** issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/corp
~~~

The two YAML blocks above **are complementary snippets in the same configuration tree**, and must be merged under the `spring.security.oauth2` node if placed in one file. All domains/IDs/secrets are illustrative; store secrets in a secret manager/environment variables, never commit real values. Enforce audience checks for APIs if the default issuer/JWT validation does not verify application-required claims.

Command to run a Maven Boot project with Maven Wrapper (once each project has the right dependencies declared):

~~~bash
./mvnw spring-boot:run
~~~

There is no fixed stdout/identity: real login depends on the OP, client registration, user account, network, and IdP policy. If the app lacks a valid client registration, simply calling `oauth2Login` is insufficient to complete login.

### 4.4. Common Class and Extension Point Differences

| Need | Servlet | WebFlux |
|---|---|---|
| Protection chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Request rule declaration | `authorizeHttpRequests` / `requestMatchers` | `authorizeExchange` / `pathMatchers` |
| OAuth2 registration | `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Authorized client management | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Typical HTTP client | `RestClient` or properly configured `WebClient` | Reactive `WebClient` |
| Context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Extension filter | `OncePerRequestFilter`/Servlet `Filter` | `WebFilter`, reactive authentication manager |

Shared types like `Authentication` or `GrantedAuthority` **do not** prove an integration works cross-stack; HTTP hooks, security context persistence, and async/reactive execution models still differ.

## 5. SAML 2.0: Official SP Support on Servlet

### 5.1. What Spring Security Solves

Spring Security SAML 2.0 targets **Service Provider (SP/Relying Party) for web SSO**. The `spring-security-saml2-service-provider` library provides SAML HTTP-Redirect/POST flows, SAML Response decoding/validation, `RelyingPartyRegistration` management, SP metadata, and login/logout handling when configured.

Recognizable components:

- `HttpSecurity.saml2Login(Customizer.withDefaults())`.
- `RelyingPartyRegistrationRepository` storing SP ↔ IdP configuration.
- `Saml2WebSsoAuthenticationRequestFilter` preparing the `AuthnRequest`.
- `Saml2WebSsoAuthenticationFilter` receiving responses at the ACS.
- OpenSAML integration for XML/signature/assertion processing.

Sample Spring Boot configuration; replace metadata with the real IdP and register the SP there:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-saml:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

Default endpoints may include `/saml2/authenticate/{registrationId}` and `/login/saml2/sso/{registrationId}`; the SP metadata endpoint requires enabling `saml2Metadata` per configuration. Always cross-check ACS URL/entity ID, certificates, and proxy URLs.

### 5.2. What Spring Security Does Not Handle Automatically

- **Not a SAML IdP**: requires an external IdP to authenticate users and sign assertions.
- **Does not blindly trust every IdP**: you must manage metadata, signing keys/certificates, issuer/audience/recipient, assertion validity, replay protection, and key rotation.
- **No equivalent `ServerHttpSecurity.saml2Login()` in WebFlux 7.1 docs**. Adding the SAML service provider JAR to a WebFlux app does not convert the servlet `Saml2WebSsoAuthenticationFilter` into a `WebFilter`.
- **No automatic system-wide single logout**: verify SLO/local/IdP sessions according to both sides' capabilities and configuration.

If a **pure WebFlux web app** must use a partner's SAML IdP, the lower-risk path is usually having a **broker** trust the SAML IdP and issue OIDC to WebFlux, or using a **dedicated Servlet SAML SP application** as the authentication tier issuing verifiable credentials downstream. Writing a reactive SAML SP from scratch requires full XML Security, state, signature/response/cert handling, and SLO; never treat it as a simple filter adapter.

## 6. CAS: Service Ticket Integration on Servlet; CAS Server Is a Separate System

The **CAS protocol** differs from OIDC and SAML: the service receives a **Service Ticket (ST)** on callback; the backend validates the ticket with the CAS Server over HTTPS with the exact `service` URL, and STs are typically single-use.

On Servlet, Spring Security provides CAS integration via modules/components:

- `CasAuthenticationEntryPoint`: redirects the browser to the CAS login page.
- `CasAuthenticationFilter`: receives the callback containing `ticket`.
- `CasAuthenticationProvider`: coordinates `TicketValidator` with the CAS Client library.
- `ServiceProperties`: defines the service URL that must match during validation.
- `Cas20ServiceTicketValidator`/proxy validator from a compatible library when needed.

Basic flow:

~~~text
Servlet app ----redirect----> CAS Server /login?service=...
Browser <---SSO cookie------> CAS Server
CAS Server ----ST---------> Browser ----ticket----> Servlet callback
Servlet backend ----HTTPS validation (ticket + service)---> CAS Server
Servlet app <--------CAS response (user/attributes)---------
Servlet app creates Authentication + its own session
~~~

**WebFlux limitation:** official WebFlux docs have no `casLogin` DSL or equivalent reactive filter. `CasAuthenticationFilter` depends on the servlet request/filter contract; it cannot plug directly into `ServerHttpSecurity`. You may use a third-party adapter **if verified to support WebFlux and the target CAS protocol version**, or have the CAS Server/broker issue OIDC to the reactive app. Modern CAS Servers can expose OIDC/SAML through modules of the **CAS Server itself**; the existence of such a module **does not turn the CAS protocol into OIDC**.

**Checks needed:** exact `service` URL match, non-reusable tickets, TLS, session/logout, CAS proxy tickets if used (allowing only trusted proxies), and authority mapping. An app using only OAuth2 client cannot validate a CAS ST under the CAS protocol.

## 7. Kerberos/SPNEGO: Specialized Module for Servlet and Domain Infrastructure

Kerberos is a ticket-based protocol relying on a **KDC**, TGTs, service tickets, realms, and principals. For HTTP SSO, **SPNEGO/Negotiate** carries Kerberos tokens inside HTTP authorization exchanges. Applications typically receive `Authorization: Negotiate ...`; the server needs a service principal like `HTTP/app.example.org@EXAMPLE.ORG` and a matching key (keytab).

In Spring Security 7.x, Kerberos is part of the Spring Security ecosystem with artifacts:

~~~xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
~~~

Declare versions via a compatible Spring Security/Boot BOM/dependency management. Example integration classes: `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`. These are **Servlet security filter/AuthenticationProvider** classes—you must wire the filter into the chain, configure the service principal/keytab, and connect to a real realm; there is no single "`kerberosLogin()` is enough" switch in the core DSL.

In Spring Security 6.x, Kerberos was an **extension with separate coordinates and release cycle**; when upgrading to 7.x, check the Kerberos migration/introduction sections. Some older doc examples use `.and()` syntax or changed APIs; avoid copying them verbatim into new projects without compiling against locked dependencies.

**WebFlux:** official docs do not provide a `ServerHttpSecurity.kerberosLogin`/reactive SPNEGO filter equivalent. Some architectures terminate the protocol at a reverse proxy/gateway in front of WebFlux and pass identity via protected tokens/claims; or a broker handles Kerberos upstream and issues OIDC. Blindly forwarding an `X-User: alice` header from internet clients into an app **does not count as authentication**: the proxy must strip spoofed client headers, authenticate the upstream connection, sign/bind claims, or use mTLS/appropriate tokens.

Mandatory Kerberos prerequisites live in infrastructure: KDC/AD, DNS, SPN, keytab, encryption types, time synchronization, browser Negotiate permission, and realm trust. Spring Security does not provision a KDC or fix domain configuration for you.

## 8. Beyond Core Libraries: IdP, Authorization Server, Broker, and Third-Party Adapters

### 8.1. Server Role vs Client Role

| Role | Who Is Responsible | Spring Security Contribution |
|---|---|---|
| **SAML IdP** | Dedicated IdP signing assertions and managing SSO sessions | Servlet SAML SP **consumes** verified assertions |
| **OIDC OP / OAuth Authorization Server** | System issuing authorization codes, ID/access tokens, public keys | Servlet has **Spring Security Authorization Server** when building a server, or choose an external OP; both Servlet and WebFlux have client/resource-server |
| **CAS Server** | Issuing/validating tickets, holding TGC/TGT, SSO policy | Servlet CAS integration is a **service consumer** |
| **Kerberos KDC** | Issuing TGTs/service tickets, managing principals | Servlet Kerberos integration **accepts/verifies** Kerberos/SPNEGO when configured |
| **Identity broker** | Mapping upstream SAML/CAS/Kerberos to downstream OIDC/SAML per policy | App uses a downstream protocol supported on its stack |
| **Provisioning / SCIM** | Syncing accounts and lifecycle | Being able to log in does not automatically provision/deprovision accounts on time |

Spring Security Authorization Server provides **Servlet**-based OAuth2/OIDC server capabilities and has its own dependency; do not confuse it with `spring-boot-starter-oauth2-client`, `spring-boot-starter-oauth2-resource-server`, or `spring-security-saml2-service-provider`. A WebFlux app needing an OP can log in against a **separately running Servlet Authorization Server** or external IdP service; the WebFlux app remains an RP.

### 8.2. When to Use an External Library?

An external adapter is only worth choosing after verifying:

1. It supports the **exact framework** (Servlet `Filter` vs WebFlux `WebFilter`) and **exact version** of Spring Framework/Security/Boot.
2. It genuinely supports the **desired role** (SAML SP vs IdP; CAS ticket validator vs CAS Server; Kerberos acceptor vs Kerberos client).
3. It properly validates signatures/certs/nonces/replay/redirects/issuer/audience and integrates with the security context.
4. It supports session, CSRF, logout, MFA, error paths, and logging, with maintained upgrade/patch support.
5. It does not block the event loop with blocking network/disk/JAAS calls inside a reactive chain; if unavoidable, an offload/gateway architecture must be load-tested and timeout-guarded.
6. End-to-end integration tests with a real IdP and negative-path tests exist, not just "it builds".

Never call something "Spring Security native reactive SAML/CAS/Kerberos" merely because a custom starter or third party exposes similarly named classes.

## 9. Three Reference Architectures and How to Choose

### A. Servlet Monolith Using a Partner's SAML

~~~text
Browser -> Spring MVC + SAML SP -> SAML IdP
              |
              +-> HttpSecurity.saml2Login()
              +-> RelyingPartyRegistration/metadata + ACS
              +-> Authentication -> service authorization
~~~

**Choose when:** direct SAML is required, the app is already Spring MVC/Servlet, and ACS/metadata/SLO are needed. **Avoid confusion:** using OpenSAML still requires a trusted SAML IdP.

### B. WebFlux App Using OIDC Directly

~~~text
Browser -> WebFlux app -> OIDC Provider
                 |
                 +-> SecurityWebFilterChain.oauth2Login()
                 +-> ReactiveClientRegistrationRepository
                 +-> Session/security context in reactive flow

HTTP API client -> WebFlux API -> oauth2ResourceServer().jwt()
                                  -> ReactiveJwtDecoder / authorities
~~~

**Choose when:** the IdP supports OIDC, the app is WebFlux, and APIs require Bearer tokens. Separate session-login and Bearer API policies by endpoint so API clients are not redirected to interactive login pages.

### C. Multiple Legacy Protocols Through a Broker

~~~text
Windows workstation --Kerberos/SPNEGO--+
                                      |
Partner SAML IdP -----SAML------------+--> Identity Broker / Gateway
                                      |       |
Legacy CAS Server ----CAS-------------+       +--> OIDC OP endpoints
                                              |
                                              +--> Spring MVC OIDC RP
                                              +--> Spring WebFlux OIDC RP
                                              +--> Resource Server APIs
~~~

**Choose when:** multiple identity sources and multiple apps (especially WebFlux) exist. The broker **issues fresh credentials** with clear issuer/audience/keys/lifetime; never reuse SAML assertions or CAS STs as API Bearer tokens. The gateway must protect downstream services from spoofed headers and preserve trust boundaries, sessions/logout, and auditing.

## 10. Decision Process for a New Application

Start with the **actual protocol offered by the identity provider**, then apply the decision tree:

1. **Is the app an OIDC client or OAuth2 Resource Server?** Both Servlet and WebFlux have official support. Choose based on web architecture, not protocol.
2. **Does the app need to receive SAML Responses directly?** Servlet SP is the documented Spring Security option; WebFlux should prefer a broker/Servlet facade if the organization has a choice.
3. **Is a legacy app forced to accept CAS STs?** Use Servlet CAS integration; WebFlux needs a verified external/bridge approach.
4. **Is HTTP Kerberos Negotiate mandatory?** For Servlet consider the Kerberos module + infrastructure; for WebFlux consider a gateway/IdP broker and trust verification.
5. **Must the app act as a SAML IdP, CAS Server, KDC, or OIDC OP?** Those are **separate server roles**, not implied by having login/client features. Choose a purpose-built IdP/CAS/KDC/Authorization Server.
6. **Can a shared downstream protocol be standardized?** OIDC is usually convenient for both Spring MVC and WebFlux; evaluate customer constraints, security team requirements, and lifecycle governance.

**Do not pick WebFlux just because "SSO is faster"**: browser redirects, OP calls, JWK fetching, backend sessions, and signature verification have their own overhead; network/reactive performance depends on workload. WebFlux fits when the whole application needs reactive I/O and compatible security libraries.

## 11. Common Errors and Fixes

| Symptom | Common Cause | Resolution Path |
|---|---|---|
| `Cannot resolve method saml2Login` on `ServerHttpSecurity` | Using reactive API; SAML login DSL is for Servlet | Use Servlet SP or a SAML→OIDC broker |
| `CasAuthenticationFilter` cannot attach to WebFlux | CAS filter implements Servlet `Filter` | Use Servlet CAS module or a verified reactive adapter/gateway |
| `SpnegoAuthenticationProcessingFilter` does not process `ServerWebExchange` | Kerberos web integration is Servlet-based | Use matching stack integration or handle Negotiate upstream |
| Spring MVC app configures `SecurityWebFilterChain` but nothing runs | Server stack is Servlet | Use `SecurityFilterChain` + `HttpSecurity` |
| WebFlux app declares Servlet `SecurityFilterChain` | Wrong chain type; missing WebFlux route protection | Use `SecurityWebFilterChain` + `ServerHttpSecurity` |
| Added `spring-webflux` and assumed Servlet SAML turned reactive | `WebClient` is an HTTP client library, not a server runtime switch | Check app type/chains at runtime, not single dependencies |
| API accepts OIDC `id_token` as Bearer token | Confusing RP authentication with API authorization | Resource Server validates **access tokens** with valid audience/scopes |
| JWT signature validates yet permissions are wrong | Missing issuer/audience/role mapping validation | Add validators, restrict tenant/scopes and internal authorities |
| CAS ticket is valid yet service validation fails | `service` URL mismatches scheme/host/path or ST was already consumed | Match exact URL, validate ST only once |
| Kerberos loops on 401 Negotiate | Wrong SPN/keytab/KVNO/DNS/realm/browser/clock | Check KDC, tickets, SPN, keytab, trust, and HTTP headers |
| WebFlux stalls/loses throughput during auth | External adapter runs blocking I/O directly on the event loop | Use true reactive integration or offload verification to a gateway/worker pool |
| Logged out of app yet immediately logs back in | Upstream IdP/CAS/Kerberos still holds an active session/ticket | Design local vs provider logout and test across all parties |

## 12. Integration Testing / Evaluation Checklist

### 12.1. Check Dependencies and APIs Before Running

- Record exact versions of **Java, Spring Boot, Spring Framework, Spring Security**, and Maven/Gradle platform.
- Confirm the right chain/HTTP DSL type: `SecurityFilterChain/HttpSecurity` vs `SecurityWebFilterChain/ServerHttpSecurity`.
- Verify artifacts **by role**: OAuth2 client/resource server, SAML service provider, CAS, Kerberos core/web; never copy Spring 6 dependencies into Spring 7 without checking versions.
- Identify who provides the **IdP/OP/CAS Server/KDC** and who manages metadata, issuers, keys/certificates, domains, and account provisioning.
- Do not confuse the `WebClient` client API with a WebFlux server application.

### 12.2. Verify Authentication and Authorization Behavior

- **Happy path:** proper redirect/challenge, authentication at external system, callback with valid state/ticket/response; principal and roles mapped accurately.
- **Error paths:** wrong issuer/audience, expired token/assertion, invalid signature, replay, reused CAS ST, wrong SPN/keytab, mismatched redirect/ACS/service URL must all be rejected.
- **API:** Bearer token with wrong audience/scope returns appropriate 401/403; a web user session does not automatically grant access to every API.
- **Session/logout:** verify local session, IdP SSO session, refresh-token expiry, SAML/CAS logout if used, lingering Windows tickets, and locked accounts.
- **Proxy:** check TLS, trusted forwarded headers, Host/external URL, and reject client-supplied identity headers.
- **WebFlux:** run concurrent load tests and block detection when using external adapters; never execute blocking network I/O on the event loop.

Familiar test tools: `spring-security-test` with `MockMvc` for Servlet and `WebTestClient` for WebFlux. Mock authentication/JWTs help test application rules but **cannot replace real integration tests** against an IdP, SAML metadata, CAS Server, or Kerberos KDC.

## 13. Quick Summary in Three Rules

1. **Identify the stack first:** `HttpSecurity` → Servlet; `ServerHttpSecurity` → WebFlux. Never mix filters, security contexts, or managers across stacks.
2. **Identify the role:** OAuth2 client/Resource Server/Authorization Server are distinct; SAML SP differs from SAML IdP; CAS service differs from CAS Server; Kerberos HTTP acceptor differs from KDC.
3. **Identify the support level:** OIDC/OAuth2 client & resource server exist on both stacks; SAML SP and CAS center on Servlet; Kerberos SPNEGO uses a dedicated servlet module. For WebFlux and legacy protocols, consider a broker/gateway or verified reactive adapter.

## 14. Official Documentation for Verification

Prioritize references matching your **exact version branch** before writing production code:

- Spring Security Reference – Servlet: https://docs.spring.io/spring-security/reference/servlet/index.html
- Spring Security Reference – Reactive/WebFlux: https://docs.spring.io/spring-security/reference/reactive/index.html
- Servlet OAuth2 Client/Login/Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/
- Reactive OAuth2 Client/Login/Resource Server: https://docs.spring.io/spring-security/reference/reactive/oauth2/
- `HttpSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Servlet SAML2: https://docs.spring.io/spring-security/reference/servlet/saml2/index.html
- Servlet CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Servlet Kerberos: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security 7 What's New (Kerberos/Authorization Server modules): https://docs.spring.io/spring-security/reference/7.0/whats-new.html
- Spring Security Authorization Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/getting-started.html

**Timeliness note:** this matrix reflects Spring Security 7.1 APIs/docs at the time of writing. When maintaining or upgrading, check the JavaDoc and reference for the **actually installed version**; support from external adapters is not a guarantee from Spring Security.
