# Configuring oauth2Login and ClientRegistration for an OIDC Provider

**OpenID Connect (OIDC)** is an identity layer built on top of OAuth 2.0. For a Spring Security Servlet application, `oauth2Login(...)` handles browser-based login via **Authorization Code**, while `ClientRegistration` defines the **OpenID Provider (OP)**, client ID, client authentication, protocol endpoints, scopes, redirect URI, and issuer/JWKS details. An application can also use an **identity broker** as its direct OP while the broker federates multiple upstream IdPs belonging to different organizations.

Key design points to remember: **OAuth2 Login** does not automatically become OIDC if the `openid` scope is missing; an **ID Token** serves user authentication differently from an **Access Token** used to call APIs; and **`registrationId`** is Spring's configuration key, distinct from **`client_id`**, **provider ID**, **issuer**, and the user's **subject**.

This lesson belongs to the **OIDC and Brokering** group, explaining how to configure Spring Boot 3.x/4.x and Spring Security 6.x/7.x, Discovery principles, state/PKCE/nonce flows, multi-provider setups, broker identity boundaries, Java configuration, a standalone Java 17 exercise, and integration tests. All `.example` domains are illustrative only and do not exist in production.

## 1. Roles and Terms to Distinguish

| Component | Role | Spring Component/Value |
| --- | --- | --- |
| **Relying Party (RP)** | Spring application that needs to identify the end-user | `oauth2Login()` |
| **OpenID Provider (OP)** | Authenticates the end-user and issues ID Tokens | `ClientRegistration.providerDetails` |
| **Authorization Server** | Receives authorization requests, issues codes and tokens | `authorizationUri`, `tokenUri` |
| **Resource Server** | API that validates Access Tokens | `oauth2ResourceServer()` (if needed) |
| **Client ID** | The app's ID at the OP | `clientId` |
| **Client Secret** | Credential of a confidential client | `clientSecret`, kept secret |
| **Issuer** | Identifier of the OP issuing tokens | `issuerUri`, `iss` claim |
| **User Subject** | Stable ID within the issuer's namespace | `sub` claim |
| **Client registration key** | Selects the client config in Spring | `registrationId` |
| **Provider configuration key** | Groups OP parameters in Spring Boot | `providerId` |
| **Redirect URI** | RP callback receiving `code`/`state` | `redirectUri` |
| **JWKS URI** | OP public keys used to verify ID Tokens | `jwkSetUri` |
| **UserInfo Endpoint** | Augments claims via the access token | `userInfoUri` |

Enterprise example:

~~~text
Spring RP: https://portal.example.com
OpenID Provider: https://login.corp.example/realms/workforce

registrationId: corp-oidc
providerId: workforce-op
clientId: portal-production
issuerUri: https://login.corp.example/realms/workforce
~~~

`registrationId=corp-oidc` is not the issuer, and `providerId=workforce-op` is not the issuer either. When verifying an ID Token, `iss` must match the **trusted** OP's URI, not an arbitrary configuration label.

**OIDC is not SAML2.** In OIDC, the callback typically receives `code` and `state`, and the backend exchanges the code for tokens. In SAML, the ACS typically receives a `SAMLResponse` containing an Assertion. Use `oauth2Login` for OIDC; do not copy SAML filters/config onto the same endpoint.

## 2. Authorization Code Flow with oauth2Login

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant RP as Spring Security RP
    participant OP as OIDC Provider
    U->>RP: GET /private
    RP-->>U: Redirect to login / provider selection
    U->>RP: GET /oauth2/authorization/corp-oidc
    RP->>RP: Generate state, nonce, and PKCE when applicable
    RP->>RP: Store OAuth2AuthorizationRequest per session
    RP-->>U: 302 to OP authorization endpoint
    U->>OP: GET /authorize?client_id&redirect_uri&scope&state
    OP->>OP: Authenticate / MFA / consent
    OP-->>U: 302 to redirect_uri with code, state
    U->>RP: GET /login/oauth2/code/corp-oidc?code=...&state=...
    RP->>RP: Check state and stored authorization request
    RP->>OP: POST /token: code + client authentication / PKCE verifier
    OP-->>RP: ID Token + Access Token (and Refresh Token if issued)
    RP->>RP: Verify ID Token, build OidcUser/Authentication
    RP-->>U: RP session and redirect
~~~

Spring exposes **two distinct routes**:

| Route at RP | Purpose |
| --- | --- |
| `GET /oauth2/authorization/{registrationId}` | **Initiates** Authorization Code; handled by `OAuth2AuthorizationRequestRedirectFilter` |
| `GET /login/oauth2/code/{registrationId}` | **Default callback** receiving code/state; handled by `OAuth2LoginAuthenticationFilter` |

The Authorization Endpoint and Token Endpoint belong to the **OP**, not the RP. `/oauth2/authorization/corp-oidc` returns a redirect to the OP; it does not mint an ID Token itself. `/login/oauth2/code/corp-oidc` is not a password entry URL.

**An `Authorization Code` is neither an access token nor an ID Token**. It is a short-lived credential exchanged for tokens at the Token Endpoint; the backend must bind it via redirect URI, client authentication, and PKCE when applicable. Never put the client secret in browser URLs.

## 3. Which Components Does Spring Security Require?

For the Servlet stack:

- `HttpSecurity.oauth2Login(...)` configures the filters and login flow.
- `ClientRegistration` describes a client at an OP.
- `ClientRegistrationRepository` looks up a ClientRegistration by registrationId.
- `InMemoryClientRegistrationRepository` fits a small, static set of registrations.
- `OAuth2AuthorizationRequestRedirectFilter` initiates the authorization request.
- `HttpSessionOAuth2AuthorizationRequestRepository` stores the authorization request and `state` prior to callback by default.
- `OAuth2LoginAuthenticationFilter` processes the callback and builds the Authentication.
- `OidcIdTokenDecoderFactory` supports ID Token validation for OIDC login.
- `OidcUserService` extracts identity/claims from the ID Token/UserInfo.
- `OAuth2AuthenticationToken` holds the Authentication result.
- `OidcUser` is the authenticated OIDC principal containing `sub`/claims.
- `OAuth2AuthorizedClientService` or `OAuth2AuthorizedClientRepository` manages authorized clients with issued tokens when the RP calls APIs.

An application may use OAuth2 Login solely to sign users in without calling external APIs; implementing `oauth2ResourceServer` is not required in that case. Conversely, an API accepting bearer access tokens via `oauth2ResourceServer` does not automatically provide browser login redirects.

**Servlet vs. WebFlux:** this lesson uses `SecurityFilterChain` and `HttpSecurity`. In a reactive stack you must use `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveClientRegistrationRepository`; do not copy Servlet APIs into a reactive project.

## 4. Registering the OIDC Client at the OP Before Writing Java

A client registration must be created in OP/broker administration:

1. Create separate applications/clients for staging and production.
2. Choose a confidential web client if the backend can protect a secret; a public client when there is nowhere to keep a secret.
3. Enable **Authorization Code Flow**; avoid Implicit Flow for new applications.
4. Register the **exact redirect URI**, e.g., `https://portal.example.com/login/oauth2/code/corp-oidc`.
5. Store the client ID and secret (if issued) in a vault or secret manager.
6. Confirm the issuer identifier, metadata/JWKS, and authorization/token/userinfo URLs.
7. Request at least the `openid` scope, adding `profile`/`email` if used.
8. Define MFA policy, `acr`, `amr`, conditional access, and user eligibility.
9. Document which claims/groups the OP actually emits and who owns role mapping.
10. Assign an owner and procedures to rotate client secrets, OP keys, and disabled clients.

**The callback must match the exact URI**, including HTTPS, domain, port, context path, and trailing slash according to OP rules. A broad wildcard URI or user-controlled callback easily opens code-leak or open-redirect vulnerabilities.

## 5. Configuring Spring Boot with issuer-uri and Discovery

Example `application.yml` for an OP-approved OIDC client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-oidc:
            provider: workforce-op
            client-id: ${OIDC_CORP_CLIENT_ID}
            client-secret: ${OIDC_CORP_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: "Corporate Login"
        provider:
          workforce-op:
            issuer-uri: "https://login.corp.example/realms/workforce"
~~~

`registration.corp-oidc` defines **registrationId=corp-oidc**. `provider: workforce-op` points to `provider.workforce-op`, which holds `issuer-uri`. The two keys may differ. `client-id` and `client-secret` come from environment variables and should never be hardcoded or committed with real values. `client-authentication-method: client_secret_basic` is a common method, but it must match the OP's requirement (some OPs support other methods).

When the app runs and the public base URL is `https://portal.example.com`, the callback URI expands to:

~~~text
https://portal.example.com/login/oauth2/code/corp-oidc
~~~

**The Issuer URI is not the OP Authorization Endpoint.** It is the official identifier published by the OP; Spring can use it to discover the required endpoints. In many multi-tenant/realm systems, the path portion of the issuer is critical: `/realms/workforce` differs from the root issuer.

### What Does Discovery Return?

A `.well-known/openid-configuration` document may contain:

~~~json
{
  "issuer": "https://login.corp.example/realms/workforce",
  "authorization_endpoint": "https://login.corp.example/realms/workforce/protocol/openid-connect/auth",
  "token_endpoint": "https://login.corp.example/realms/workforce/protocol/openid-connect/token",
  "jwks_uri": "https://login.corp.example/realms/workforce/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://login.corp.example/realms/workforce/protocol/openid-connect/userinfo"
}
~~~

**This is abbreviated illustrative metadata JSON**, not a real OP. The exact Discovery URI must follow OIDC Discovery/RFC 8414 and path-aware issuer rules. `ClientRegistrations.fromIssuerLocation(...)` in modern Spring Security versions probes well-known locations per framework rules; `fromOidcIssuerLocation(...)` targets OIDC endpoints. Never assemble URLs arbitrarily and assume they are correct.

If the OP metadata service, DNS, or TLS is down, discovery during registration creation can fail startup. That is distinct from an error while a user is mid-callback. In HA systems, maintain a controlled cache/pinned metadata or safe initialization process; **never accept an issuer URL from a browser query parameter** to run discovery because of SSRF/issuer mix-up risks.

## 6. Enabling oauth2Login via SecurityFilterChain

In a Spring Boot project with `spring-boot-starter-oauth2-client` and the YAML above:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The code is **Spring JavaConfig** that must reside in an application with valid bean registration; it cannot run standalone with `javac`. Spring configures the OAuth2 Login filters for authorization requests and callbacks. Running the project without a `ClientRegistrationRepository` or valid YAML leaves Spring with no knowledge of any OP.

In a project with multiple `SecurityFilterChain` beans, ensure both `/oauth2/authorization/**` and `/login/oauth2/code/**` route into the chain that enables `oauth2Login`. Never leave `anyRequest().permitAll()` open in production.

**Quick check:** open `https://portal.example.com/oauth2/authorization/corp-oidc` in a browser. With valid configuration, the response normally redirects 302 to the OP authorization endpoint; you must still verify the callback, code exchange, ID Token validation, and user permissions. **An HTTP 302 alone does not prove login succeeded.**

## 7. Maven and Gradle Dependencies

In a project using the Spring Boot parent/BOM for version management, dependencies typically look like:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
  </dependency>
</dependencies>
~~~

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

These are **build fragments**, not complete POM/Gradle projects. For projects not using starters, include compatible Spring Security OAuth2 Client, OAuth2 JOSE, and Web/Security modules. Do not force an isolated `spring-security-oauth2-client` version outside the BOM just to pull newer APIs.

Verify resolved artifacts:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-oauth2-client
~~~

These commands have no fixed stdout; the goal is to verify the actual resolved versions of `spring-security-config`, `oauth2-client`, `oauth2-jose`, Spring Framework/Boot, and the JDK.

## 8. Spring Boot Auto-Configuration vs. Java ClientRegistrationRepository

`ClientRegistrationRepository` is the source of client configurations. When Spring Boot detects `spring.security.oauth2.client.registration.<id>.*` and the required dependencies, it auto-configures an appropriate repository.

If you prefer managing it in Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Configuration
public class CorporateOidcRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration corporate = ClientRegistrations
                .fromIssuerLocation(
                    "https://login.corp.example/realms/workforce")
                .registrationId("corp-oidc")
                .clientId(System.getenv("OIDC_CORP_CLIENT_ID"))
                .clientSecret(System.getenv("OIDC_CORP_CLIENT_SECRET"))
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .build();

        return new InMemoryClientRegistrationRepository(corporate);
    }
}
~~~

This code runs **inside a Spring project** with live OP Discovery and populated environment variables; `.example` hostnames cannot be contacted. `fromIssuerLocation` accesses metadata when building the registration. In production, enforce controlled fail-fast checks on empty/missing secret variables, manage TLS trust, and never log credentials.

**Do not both define a custom repository bean and expect Boot to merge registrations from YAML**. Depending on auto-configuration conditions, defining your own bean suppresses Boot's property-based repository. Pick one configuration source intentionally.

### Building ClientRegistration Manually

If the OP lacks discovery support or the enterprise prefers pinned endpoints, Spring offers `ClientRegistration.withRegistrationId(...)`:

~~~java
ClientRegistration registration = ClientRegistration
        .withRegistrationId("corp-oidc")
        .clientId("client-id-from-secure-config")
        .clientSecret("client-secret-from-secure-config")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .authorizationUri("https://login.corp.example/authorize")
        .tokenUri("https://login.corp.example/token")
        .jwkSetUri("https://login.corp.example/jwks")
        .issuerUri("https://login.corp.example")
        .userInfoUri("https://login.corp.example/userinfo")
        .userNameAttributeName("sub")
        .clientName("Corporate Login")
        .build();
~~~

This is an **API fragment** without imports, secret management, or repository wiring, not standalone Java. The literal clientId/secret strings **represent values that must come from secure configuration**, not usable credentials. For OPs whose issuer includes a realm path, `issuerUri` must match `iss` exactly rather than being guessed from endpoint URLs. Verify the builder API against your resolved Spring Security version.

Manual configuration increases maintenance overhead whenever the OP changes endpoints, JWKS, or algorithms. Using verified discovery whenever possible reduces typos in token/userinfo URIs.

## 9. The openid Scope Is What Identifies OIDC

In Spring Security OIDC Login, **the `openid` scope** indicates that the request uses OIDC Authentication. Example:

~~~yaml
scope:
  - openid
  - profile
  - email
~~~

- `openid`: requests an ID Token / OIDC flow.
- `profile`: requests profile claims per OP policy.
- `email`: requests email-related claims; does not guarantee all fields are populated.
- `offline_access`: if supported by the OP and the app genuinely needs refresh tokens/offline access, a clear policy is required.

**Scope is not role.** An `email` scope does not grant `ROLE_ADMIN`. Nor does `profile` ensure a user may administer a tenant. Authority mapping is the application's responsibility and must rely on issuer/subject/contract, never parsing scope strings to grant business privileges.

Without `openid`, Spring Security may use plain OAuth2-user processing instead of the OIDC-specific `OidcUserService`; never call that a "successful OIDC login" merely because the user received an access token.

## 10. ID Token Differs from Access Token and UserInfo

| Component | Used By | What to Verify |
| --- | --- | --- |
| **Authorization Code** | RP backend to exchange for tokens | Not an identity; short-lived and single-use |
| **ID Token** | **OIDC RP** | JWT issued to the client, containing `iss`, `sub`, `aud`, `exp`, `iat`, and `nonce` when applicable |
| **Access Token** | API/Resource Server | Separate audience/scope; does not replace ID Token |
| **Refresh Token** | RP or authorized client service | Sensitive credential; must be stored safely and rotated/revoked |
| **UserInfo** | RP via access token | Supplementary claims whose `sub` must match the ID Token |
| **RP Session Cookie** | Browser after login | Holds the SecurityContext; distinct from all tokens above |

**Never use a validly signed JWT access token to create an OIDC user session merely because it carries a `sub` claim.** That JWT may have been issued for a different API. Always validate token purpose, issuer, audience, and flow-specific rules.

### ID Token Validation

Per OIDC Core, `OidcIdTokenDecoderFactory` and Spring Security validators must enforce:

1. **Signature/JWS:** keys from the trusted OP's JWKS; reject `alg=none` or arbitrary token-dictated algorithms.
2. **Issuer (`iss`):** must equal the configured issuer URI.
3. **Audience (`aud`):** must include the `client_id` of the active registration.
4. **Authorized party (`azp`):** enforce per OIDC rules when multiple audiences are present.
5. **Expiry and timestamps:** `exp`, `iat`, and bounded clock skew per policy.
6. **Nonce:** if the request sent `nonce`, verify the bound nonce claim.
7. **Subject (`sub`):** non-empty value scoped to the issuer.
8. **UserInfo `sub`:** must not contradict the ID Token `sub`.
9. **`auth_time`, `acr`, `amr`:** enforce policy when the enterprise requires MFA/freshness.
10. **Token audience/purpose:** reject JWTs issued for a different client or API.

In Spring Security, a `JwtDecoder` bean defined for `oauth2ResourceServer().jwt()` is **not automatically used to verify `oauth2Login` ID Tokens**. To customize the OIDC Login decoder, check `JwtDecoderFactory<ClientRegistration>`, `OidcIdTokenDecoderFactory`, and `OidcIdTokenValidator` for your version. Never replace standard validators with signature-only checks.

## 11. state, nonce, and PKCE: Three Separate Layers of Defense

| Mechanism | Where It Appears | Protects Against |
| --- | --- | --- |
| **`state`** | Authorization request/callback query | Authorization response CSRF/mix-up and broken flows |
| **`nonce`** | Authorization request and ID Token | Token replay/substitution, binding ID Token to the flow |
| **PKCE** | `code_challenge` at authorize, `code_verifier` at token exchange | Code interception/injection, binding the authorization code |
| **Client authentication** | Token endpoint | Authenticates the client via secret/private key per mode |
| **Redirect URI validation** | OP and Spring RP | Prevents codes from being sent to unauthorized addresses |

**PKCE does not replace `state`**; `state` does not replace nonce. Confidential clients with a secret should not skip PKCE if required by the OP/policy. An ID Token with a valid signature but wrong nonce or audience must still be rejected.

### Public Clients

For clients unable to keep a secret, Spring Security supports PKCE when `client-authentication-method=none` and the secret is omitted:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          public-oidc:
            provider: workforce-op
            client-id: ${OIDC_PUBLIC_CLIENT_ID}
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          workforce-op:
            issuer-uri: "https://login.corp.example/realms/workforce"
~~~

**This is an example of a public client**, not a reason to convert every web server into a public client. Backends capable of protecting a secret should normally use a confidential client per OP/security policy. If configuring `ClientRegistration.clientSettings.requireProofKey=true` with Authorization Code, Spring Security can enable PKCE per documentation; verify `code_challenge` on the real authorization request and `code_verifier` on token exchange.

**Never put `code_verifier` in browser URLs or logs.** Use S256 as supported by the OP. If an OP does not support PKCE for confidential clients, coordinate configuration rather than disabling other checks.

## 12. AuthorizationRequestRepository and HttpSession

By default, Spring Security uses `HttpSessionOAuth2AuthorizationRequestRepository` to store the `OAuth2AuthorizationRequest` from SSO initiation until callback. This data contains `state` and the context needed to prevent cross-transaction confusion.

If the browser gets a 302 from the OP with `code`/`state` yet the callback lacks the SP's session cookie, the repository cannot retrieve the request. Common causes include:

- Wrong cookie `SameSite`/`Secure`/`Domain`/`Path` or browser blocking third-party context.
- Session TTL expired or session rotated/cleared.
- Multiple nodes without a shared session store.
- User opening multiple login tabs that overwrite flow state depending on repo/app behavior.
- Proxy altering the hostname or callback path.
- Authorization request already consumed and callback replayed.

**Never disable state checking** to fix these errors. If implementing a custom repository replacing `HttpSessionOAuth2AuthorizationRequestRepository`, preserve browser binding, random state, TTL, replay protection, and fail-closed behavior. Storing requests in Redis/cache keyed solely by `state` without browser binding introduces login CSRF/login fixation vulnerabilities.

For the default top-level GET OIDC callback, `SameSite=Lax` cookies are normally sent. When the OP uses `response_mode=form_post` or the RP runs inside an iframe, evaluate SameSite/third-party cookie policies separately; never assume all flows behave identically.

## 13. Multiple Registrations and Identity Brokering

A portal may support both an internal OP and Partner B's OP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-op
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            scope: [openid, profile, email]
          partner-b:
            provider: partner-op
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope: [openid, profile]
        provider:
          corp-op:
            issuer-uri: "https://login.corp.example/realms/employees"
          partner-op:
            issuer-uri: "https://login.partner-b.example/oidc"
~~~

Two start URLs:

~~~text
GET /oauth2/authorization/corp
GET /oauth2/authorization/partner-b
~~~

Two callbacks:

~~~text
GET /login/oauth2/code/corp
GET /login/oauth2/code/partner-b
~~~

The OP must register the exact callback for each client. When an application renders a custom login picker, display only registrations from a server-approved allowlist; never take an unvalidated issuer/discovery URL from a query parameter and make outbound requests.

### Identity Broker with Upstream Entra ID/SAML/OIDC

~~~mermaid
flowchart LR
    USER[User] --> RP[Spring Relying Party]
    RP --> BROKER[OIDC Identity Broker]
    BROKER --> CORP[Upstream Entra ID]
    BROKER --> PARTNER[Upstream SAML IdP]
    BROKER --> EXTERNAL[Upstream OIDC IdP]
    BROKER --> RP
~~~

The Spring RP can have **just one ClientRegistration** pointing to the broker:

~~~text
registrationId = broker
clientId       = portal-rp
issuerUri      = https://broker.example.com/realms/external
~~~

The broker communicates with upstream IdPs yet issues ID Tokens to the RP with the **broker's** issuer:

~~~json
{
  "iss": "https://broker.example.com/realms/external",
  "aud": "portal-rp",
  "sub": "broker-stable-subject"
}
~~~

**Do not change `iss` in the RP to the upstream issuer** just because the user entered their password at Entra ID earlier. `iss` must match the direct OP that the RP registered and trusts. Claims describing the upstream source/subject should be used only under a **broker contract** covering authenticity, stability, and namespaces.

A broker may allow account linking or JIT provisioning. If the broker's `sub` changes when the upstream changes, local identity mapping can break. Never auto-merge accounts by email, even when marked verified; use the `(trustedIssuer, subject)` identity-link key and explicit mapping policies.

**Home realm discovery / IdP hints:** a broker may support proprietary parameters like `idp_hint` or `domain_hint`. These are **not standard OIDC parameters shared by all OPs**. If needed, use an `OAuth2AuthorizationRequestResolver` to attach allowlisted parameters per server-side policy; never accept arbitrary issuer URLs from the browser.

## 14. Customizing the Authorization URL and Callback

By default Spring Security uses:

~~~text
Start:    /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
~~~

To change the initiation base URI:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(authorization ->
        authorization.baseUri("/federation/oidc/start")))
~~~

With the default resolver, URLs follow `/federation/oidc/start/{registrationId}`.

To use callback `/federation/oidc/callback/{registrationId}`:

~~~java
.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(redirection ->
        redirection.baseUri("/federation/oidc/callback/*")))
~~~

At the same time update `ClientRegistration.redirectUri`:

~~~yaml
redirect-uri: "{baseUrl}/federation/oidc/callback/{registrationId}"
~~~

And register the public URI at the OP:

~~~text
https://portal.example.com/federation/oidc/callback/corp-oidc
~~~

**Three places must stay synchronized**: the callback filter matcher, ClientRegistration redirectUri, and the OP allowlist. Changing only one side causes `redirect_uri_mismatch`, 404, or the callback being intercepted by another filter.

### Proxy Public URL

When the app runs internally on `http://app:8080` yet is exposed publicly at `https://portal.example.com/app`, `{baseUrl}` must expand to the real public scheme/host/port/path. Trust `Forwarded`/`X-Forwarded-*` headers only from managed reverse proxies and strip headers supplied by internet clients. Never solve redirect mismatches by enabling wildcard redirects or trusting arbitrary `Host` headers: that increases open-redirect and code-leakage risks.

## 15. OidcUserService and User Permissions

Spring uses `OidcUserService` to create an `OidcUser` from the ID Token and UserInfo (if called). A controller inside a Spring project:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentUserController {
    @GetMapping("/me")
    String me(@AuthenticationPrincipal OidcUser user) {
        return user.getSubject();
    }
}
~~~

This example is suitable only when the endpoint requires an OIDC-authenticated principal. If the app also supports form, SAML, or plain OAuth2 login, the principal may not be an `OidcUser`; code must handle that appropriately. Exposing raw `sub` to the browser also warrants privacy/audit consideration; in real systems, return a local user ID or view model per policy.

### Custom OidcUserService

To look up the local user and map authorities, configure `oauth2Login(...).userInfoEndpoint(...).oidcUserService(...)` per API:

~~~java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

OidcUserService defaultService = new OidcUserService();
OAuth2UserService<OidcUserRequest, OidcUser> service = userRequest -> {
    OidcUser verified = defaultService.loadUser(userRequest);
    // Use issuer + subject to look up the local user and authorities.
    // If the account is inactive or tenant is invalid, deny login.
    return verified;
};
~~~

**This is an extension-point guidance fragment** that must be wired into `userInfoEndpoint.oidcUserService(service)` in security config and supplemented with real local mapping; comments do not map roles automatically. When mapping authorities, `GrantedAuthoritiesMapper` can also be used. When transforming user data, guard claim types, multi-valued attributes, and UserInfo `sub` checks.

**Safety rule:** `ROLE_ADMIN`, tenant membership, and account enabled/disabled state must come from internal policy or approved IdP mappings. `groups=admin` from an external OP does not automatically grant admin privileges. Identify users by `(iss, sub)`, not email as a global key.

## 16. OAuth2AuthorizedClient vs. ClientRegistration

A client may receive an access token and call downstream APIs. In that context:

| Object Type | Contains | Purpose |
| --- | --- | --- |
| `ClientRegistration` | clientId, issuer/endpoints, scopes, redirect URI | Configures an RP client |
| `OAuth2AuthenticationToken` | Authenticated principal and authorities | Session SecurityContext |
| `OidcUser` | ID Token, UserInfo/claims | End-user identity per OIDC |
| `OAuth2AuthorizedClient` | registration, principalName, access/refresh tokens | Calls APIs with issued tokens |
| `OAuth2AuthorizedClientService` | Store of authorized clients | Persists/loads tokens in client context |
| `OAuth2AuthorizedClientManager` | Coordinates authorized clients | Obtains/refreshes tokens when appropriate |

Access and refresh tokens are secrets to protect; never put them in query URLs or logs. If the app only authenticates users without calling external APIs, broad API scopes and refresh flows may not be needed.

**Never use an ID Token to call a resource server** when the API expects an access token. Never treat an API access token as an ID Token to authenticate a browser session.

## 17. OIDC Logout Is Not SAML2 SLO

`oauth2Login()` handles login; it does not perform SAML2 SLO. Local logout in Spring clears the RP session, yet the OP/broker session remains; the next login attempt can silently SSO back in.

If the OP publishes `end_session_endpoint` via Discovery and supports OIDC RP-Initiated Logout, Spring Security Servlet provides `OidcClientInitiatedLogoutSuccessHandler`:

~~~java
OidcClientInitiatedLogoutSuccessHandler handler =
    new OidcClientInitiatedLogoutSuccessHandler(clientRegistrationRepository);
handler.setPostLogoutRedirectUri("{baseUrl}");
~~~

This fragment requires a `ClientRegistrationRepository` bean and wiring into `http.logout(logout -> logout.logoutSuccessHandler(handler))`. The OP must allow the post-logout redirect URI per policy. Never concatenate logout URLs onto the issuer string arbitrarily.

When a broker fronts upstream IdPs, broker logout does not prove all upstream sessions were revoked. Never claim "logged out of all systems" without explicit confirmation and policy support.

## 18. Standalone Java 17: Checking the Registration and Callback Contract

To distinguish configuration mistakes from actual protocol errors, the following program simulates checking **HTTPS issuer**, **`openid` scope**, **`authorization_code` grant**, and **`redirectUri`**. It makes no network calls, does not verify ID Tokens, and does not use Spring. It exists solely to demonstrate avoiding URL mismatches.

Create file `OidcRegistrationContractDemo.java`:

~~~java
import java.net.URI;
import java.util.Set;

public class OidcRegistrationContractDemo {
    record Registration(
            String id,
            String issuer,
            String redirectUri,
            String grant,
            Set<String> scopes) {}

    static String start(Registration r) {
        return "/oauth2/authorization/" + r.id();
    }

    static String callback(Registration r) {
        return "/login/oauth2/code/" + r.id();
    }

    static String check(Registration r, String registeredRedirect) {
        URI issuer = URI.create(r.issuer());
        if (!"https".equalsIgnoreCase(issuer.getScheme())
                || issuer.getHost() == null) {
            return "REJECT: issuer must use HTTPS";
        }
        if (!r.scopes().contains("openid")) {
            return "REJECT: openid scope missing";
        }
        if (!"authorization_code".equals(r.grant())) {
            return "REJECT: incorrect grant";
        }
        if (!r.redirectUri().equals(registeredRedirect)) {
            return "REJECT: redirect URI mismatch";
        }
        return "ACCEPT: registration contract consistent";
    }

    public static void main(String[] args) {
        String allowed =
                "https://portal.example.com/login/oauth2/code/corp";

        Registration correct = new Registration(
                "corp",
                "https://login.corp.example/realms/workforce",
                allowed,
                "authorization_code",
                Set.of("openid", "profile", "email"));

        Registration noOidc = new Registration(
                "corp", correct.issuer(), correct.redirectUri(),
                correct.grant(), Set.of("profile", "email"));

        Registration wrongCallback = new Registration(
                "corp", correct.issuer(),
                "https://portal.example.com/wrong/callback",
                correct.grant(), correct.scopes());

        Registration insecure = new Registration(
                "corp", "http://login.corp.example",
                correct.redirectUri(), correct.grant(), correct.scopes());

        System.out.println("Start: " + start(correct));
        System.out.println("Callback: " + callback(correct));
        System.out.println("Valid: " + check(correct, allowed));
        System.out.println("No OIDC: " + check(noOidc, allowed));
        System.out.println("Wrong callback: "
                + check(wrongCallback, allowed));
        System.out.println("Unsafe issuer: " + check(insecure, allowed));
    }
}
~~~

Run on JDK 17+:

~~~bash
javac OidcRegistrationContractDemo.java
java OidcRegistrationContractDemo
~~~

**Exact stdout:**

~~~text
Start: /oauth2/authorization/corp
Callback: /login/oauth2/code/corp
Valid: ACCEPT: registration contract consistent
No OIDC: REJECT: openid scope missing
Wrong callback: REJECT: redirect URI mismatch
Unsafe issuer: REJECT: issuer must use HTTPS
~~~

**Important limitation:** `Valid: ACCEPT` only means the demo configuration strings are internally consistent. It **does not** prove an OP exists at that URL, that clientId/secret are valid, that Discovery succeeds, that `state`/PKCE work, that ID Token signature/issuer/audience are verified, or that tenant authorization is sound. Do not put this `check` function into a production authentication pipeline.

## 19. Integration Test Matrix with a Real OP

| Scenario | How to Test | Expected Result |
| --- | --- | --- |
| Discovery | App boots with a real issuer | OP metadata/JWKS resolve or clear config error reported |
| Start | GET `/oauth2/authorization/corp` | Redirects to the right allowlisted OP |
| Request parameters | Browser test/proxy lab | `client_id`, `response_type=code`, redirect_uri, state, openid |
| PKCE public client | `none`, empty secret | Valid `code_challenge` and `code_verifier` |
| Callback | OP returns code/state to RP | Handled by `OAuth2LoginAuthenticationFilter` |
| State | Callback state from original request | Accepted; foreign state rejected |
| Token exchange | Backend sends valid code/client auth | Tokens match OP contract |
| ID Token signature | OP signs with right and wrong keys | Only trusted key accepted |
| ID Token issuer | `iss` from a different OP | Rejected |
| ID Token audience | `aud` omits client ID | Rejected |
| Token expired | Past `exp` | Rejected |
| Nonce | Wrong ID Token nonce | Rejected |
| UserInfo | `sub` differs from ID Token | Rejected |
| Local link | Registered `(iss,sub)` | Resolves right local user and tenant |
| Unlinked user | New unapproved subject | Fails closed or follows clear JIT policy |
| Role spoof | Unallowlisted OP group=ADMIN | No `ROLE_ADMIN` granted |
| Callback mismatch | OP URI differs from Spring callback | OP rejects; app receives no code |
| Cookie missing | Callback lacks RP session | Safe rejection, classified by state/repository |
| Multi-OP mix-up | Partner B code/token on corp registration | No user session created |
| Reverse proxy | Internal HTTP, public HTTPS | Accurate redirect_uri and issuer |
| Session logout | Local/OP logout per config | Accurately reports actual logout scope |
| Tenant boundary | User B calls API C | HTTP 403 |

`SecurityMockMvcRequestPostProcessors.oidcLogin()` from `spring-security-test` is helpful for unit-testing a controller given an `OidcUser`/authority, yet it **does not actually test** Discovery, redirects, code exchange, ID Token signatures, or PKCE. Run E2E tests against a lab OP or signed fixtures to verify OIDC integration properly.

## 20. Common Errors and Diagnosis

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Missing `ClientRegistrationRepository` | Missing dependency/config | Check starter and registration properties |
| Startup fails on issuer-uri | DNS/TLS/well-known error or wrong issuer path | Check issuer and metadata from a trusted source |
| Start URL 404 | Missing registrationId or wrong chain matcher | Check repo and `authorizationEndpoint.baseUri` |
| OP returns `redirect_uri_mismatch` | Public callback not registered at OP | Align OP, redirectUri, and proxy settings |
| Callback 404 | `redirectionEndpoint.baseUri` differs from redirectUri | Fix callback matcher |
| `authorization_request_not_found` | Lost session/authorization request | Check `JSESSIONID`/`SESSION` cookie, TTL, and repo |
| `invalid_state` | State mismatch or replay | Reject; do not disable state checking |
| `invalid_client` | Wrong client secret/auth method | Check secret manager and OP app settings |
| `invalid_grant` | Expired/used code or wrong verifier/redirect | Check token exchange, PKCE, and callback |
| ID Token signature failed | Wrong JWKS/key/alg or altered issuer | Refresh trust; never skip verification |
| Wrong issuer/audience | Registration misconfigured OP/client | Compare `iss`/`aud` with issuer/clientId |
| Missing email claim | OP withheld claim per scope/consent | Do not guess or use email as sole key |
| Login succeeds with wrong roles | Local authorities not mapped | Use `OidcUserService`/mapper with policy |
| 403 after login | User lacks resource/tenant permission | Check separate authorization, not OIDC failure |
| Silent re-login right after logout | OP/broker session still active | Review OIDC RP-initiated logout |
| Session works on one node, fails on another | Unsynced session repository/load balancer | Test multi-node and cookies |
| Class/method mismatch | Overridden Spring module versions | Use BOM and check resolved dependency graph |

**Step-by-step investigation:** if failure occurs before the OP redirect, inspect registration/start; if the OP errors, inspect client/redirect/scopes; if the callback fails, inspect state/cookie/token; if 403 occurs after login, inspect role/tenant policy. Never log authorization codes, state, client secrets, tokens, or raw UserInfo PII.

## 21. Brokering and Production Security

- **Pin issuers:** `issuer-uri` must come only from managed configuration, never from unverified queries or email domains.
- **Client secrets:** store in a vault/secret manager; rotate and separate staging/prod.
- **Discovery metadata:** fetch over HTTPS, validate issuer and JWKS per trust policy; prevent SSRF and unintended endpoint swaps.
- **Redirect URIs:** match exact OP-allowed URIs; avoid broad wildcards.
- **state/nonce:** random, correlated with browser session, preventing replay and mix-up.
- **PKCE:** verify code challenge/verifier per client type/policy, preferring S256.
- **ID Token:** check signature, issuer, audience, timestamps, nonce, and purpose.
- **UserInfo:** `sub` must stay consistent with the ID Token.
- **Identity:** key by `(iss,sub)`; if a broker supplies an upstream subject, enforce a separate contract.
- **Authorization:** use local role/tenant policies and service-level authorization; never infer admin rights from OP groups.
- **Session:** `Secure`, `HttpOnly`, and SameSite cookies matching the redirect mode; never disable CSRF globally.
- **Reverse proxy:** trust forwarded headers only from trusted proxies to generate accurate public callbacks.
- **Audit:** record registrationId, localUserId, login timestamp, and rules; never log verbatim tokens/PII.
- **Logout:** distinguish local RP sessions from OP/broker sessions.
- **Offboarding:** disabled accounts and revoked roles require session recheck/revocation policies.
- **Versions:** keep Spring Boot/Security/JDK/OpenID libraries aligned and regression-tested.

## 22. Self-Check Exercises

**A.** `registrationId=corp-oidc` and `providerId=workforce-op`, with issuer `https://login.corp.example/realms/workforce`. The initiation URL must be `/oauth2/authorization/corp-oidc`, and token `iss` must equal the issuer URI, **not** `workforce-op`.

**B.** Scope includes only `profile,email`. You cannot claim this is OIDC Login: without `openid`, an ID Token is not guaranteed.

**C.** IdP B and IdP C both emit `sub=1234`. The two identities are not automatically the same person because their issuer namespaces differ; use `(iss,sub)` and a linking policy.

**D.** The callback filter listens on `/login/oauth2/code/*` yet the OP redirects to `/federation/callback/corp`. Synchronize the callback filter, ClientRegistration redirectUri, and OP allowlist.

**E.** The broker issues an ID Token with `iss=https://broker.example.com/realms/external`, while upstream is Entra ID. Because the Spring RP trusts the broker, it must verify the broker issuer rather than substituting an upstream hint as the issuer.

**F.** The ID Token is valid yet the user lacks `ROLE_ADMIN`. An HTTP 403 on `/admin` can be the expected authorization outcome, not an OAuth2/OIDC login bug.

## 23. Official Documentation

1. [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistrationRepository, redirect URIs, and Spring Boot mappings.
2. [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): DSL, redirectionEndpoint, OidcUserService, and ID Token decoder factory.
3. [Spring Security — Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Authorization Code, PKCE, state repository, and request resolver.
4. [Spring Security — Servlet OAuth2 Overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): OAuth2 Client, OIDC login, and Resource Server differences.
5. [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): registration/provider settings, issuer-uri Discovery.
6. [Javadoc — ClientRegistrations](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistrations.html): fromIssuerLocation/fromOidcIssuerLocation.
7. [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): OidcClientInitiatedLogoutSuccessHandler.
8. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, OIDC Authorization Code, validation/UserInfo.
9. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): well-known metadata and issuer.
10. [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): code_verifier/code_challenge.
11. [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700.html): redirect URI, PKCE, and mix-up defenses.
12. [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth2/OIDC implementation risks.

**Remember:** `oauth2Login` enables Spring's browser login flow; `ClientRegistration` defines a specific **OP/client/trust contract**. `openid` establishes the OIDC goal, `state`/nonce/PKCE protect the authorization request, and the ID Token must pass issuer/audience/signature/time validation. With a broker, the RP directly trusts **the broker's issuer**, not every upstream IdP automatically. When multiple organizations share a portal, only identities scoped by `(issuer,sub)` and approved role mappings keep federation boundaries safe.