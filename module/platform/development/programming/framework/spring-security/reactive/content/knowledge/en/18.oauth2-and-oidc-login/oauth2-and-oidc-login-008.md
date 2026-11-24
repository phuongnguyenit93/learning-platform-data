# OAuth2User, OidcUser, and Distinguishing Access Tokens from ID Tokens

## 1. Context: OAuth2/OIDC Login in Spring WebFlux

A Spring Security Reactive application can provide a “Sign in with Google/Keycloak/Okta/Microsoft Entra ID” button. The user leaves the application to go to the identity provider's page, authenticates, and is redirected back to the application. After login, the application needs to know **who logged in**, while certain features also need to **call APIs** on the provider or another resource server.

These two needs use different objects:

- **OAuth2User:** principal containing user information and authorities after OAuth2 Login.
- **OidcUser:** a specialized `OAuth2User` for OpenID Connect (OIDC), adding an ID token and UserInfo data.
- **ID token:** proof of end-user authentication intended for the **OIDC client**, not a standard credential to send to business APIs.
- **Access token:** authorization credential intended for the appropriate **resource server/API**.
- **Refresh token:** optional credential used at the token endpoint to obtain a new access token.
- **OAuth2AuthorizedClient:** Spring object binding `ClientRegistration`, principal name, and access/refresh tokens.
- **OAuth2AuthenticationToken:** the login `Authentication`; not synonymous with `OAuth2AuthorizedClient`.
- **WebSession:** can maintain browser login state, though session lifetime differs from OAuth token lifetimes.

Dangerous example:

~~~java
// DO NOT DO THIS: ID token does not replace access token.
String idTokenValue = oidcUser.getIdToken().getTokenValue();
webClient.get()
        .uri("https://orders-api.example.test/orders")
        .headers(h -> h.setBearerAuth(idTokenValue));
~~~

This is a non-standalone anti-example. An ID token typically has an audience equal to the **login app's `client_id`**, not the audience required by the target API; mistakenly accepting an ID token can introduce a token-substitution vulnerability.

### Learning Objectives

After this lesson, you will be able to:
1. Distinguish OAuth 2.0 from OIDC.
2. Understand the `OidcUser extends OAuth2User` relationship and how to use `@AuthenticationPrincipal`.
3. Understand token type, issuer, audience, subject, scope, expiry, and nonce.
4. Choose the right token for login clients vs. resource servers.
5. Retrieve access tokens via `OAuth2AuthorizedClient` rather than the principal.
6. Map authorities/roles safely.
7. Build a Java 17 Spring Boot WebFlux app and test principals using `WebTestClient`.
8. Identify differences between Reactive and Servlet, mock tests vs. real login, and session/refresh/logout management.

This lesson belongs to the **OAuth2/OIDC Login** section in the Spring Security - reactive module.

## 2. How Does OAuth 2.0 Differ from OpenID Connect?

OAuth 2.0 is an **authorization framework**: a client is authorized to access a resource owner's protected resources within granted scopes. OAuth 2.0 itself does not define a complete end-user identification protocol for clients.

OpenID Connect 1.0 is an **authentication/identity** layer on top of OAuth 2.0. It adds the ID token, standardized claims, the UserInfo endpoint, discovery, and rules for verifying the authentication result.

| Aspect | OAuth 2.0 | OpenID Connect (OIDC) |
| --- | --- | --- |
| Goal | Grant access to protected resources | Authenticate the end-user to the client |
| Typical tokens | Access token; optional refresh token | Access token and ID token; optional refresh token |
| Principal in Spring OAuth2 Login | `OAuth2User` | `OidcUser` (also an `OAuth2User`) |
| User claims | Provider-specific attributes | ID token and UserInfo claims per OIDC |
| Scope indicating OIDC | Does not require `openid` | `openid` in requested scopes |
| Token sent to resource server | Access token with matching audience/scope | Still the **access token** |
| ID token audience | Not applicable | OIDC `client_id` |
| Identity verification | Cannot be inferred from an arbitrary access token | Per OIDC validation (signature, `iss`, `aud`, `exp`, `nonce` when applicable...) |

In Spring Security OAuth2 Login, having `openid` in the client registration's scope triggers OIDC-specific processing with compatible providers. Never assume every provider offering OAuth2 login issues an ID token.

### 2.1. “OAuth2 Login” Is a Product Term, Not a Token Type

A product might loosely call all of these “OAuth login”:
- OAuth2-only social login fetching user info from a protected endpoint;
- OIDC Login with a verified ID token;
- OAuth2 Authorization Code authorizing the client to call other APIs.

When coding, you must know **which flow is actually running**. Never infer that a user is authenticated merely because a string access token was received.

## 3. Authorization Code + OIDC Browser Flow

~~~text
Browser                   Spring WebFlux Client                OIDC Provider
   |                              |                                  |
   | GET /oauth2/authorization/demo                                |
   |----------------------------->|                                  |
   |                              | Prepare client_id, scope=openid  |
   |                              | redirect_uri, state, nonce, PKCE |
   | 302 to /authorize            |                                  |
   |<-----------------------------|                                  |
   | GET /authorize...                                               |
   |---------------------------------------------------------------->|
   |                 User authentication/consent                     |
   | 302 redirect ?code=...&state=...                                |
   |<----------------------------------------------------------------|
   | GET /login/oauth2/code/demo                                     |
   |----------------------------->|                                  |
   |                              | Verify state                     |
   |                              | Exchange code at token endpoint  |
   |                              |--------------------------------->|
   |                              | access_token, id_token           |
   |                              |<---------------------------------|
   |                              | Verify ID token per OIDC         |
   |                              | UserInfo (if used): access token |
   |                              | Create OidcUser, Authentication  |
   |                              | Save OAuth2AuthorizedClient      |
   | Post-login cookie/redirect   |                                  |
   |<-----------------------------|                                  |
   | GET /api/me using login session                                 |
   |----------------------------->|                                  |
   | OIDC principal safe DTO      |                                  |
   |<-----------------------------|                                  |
~~~

Common Spring Security WebFlux endpoints:
- Initiate login: `/oauth2/authorization/{registrationId}`.
- Receive authorization code: `/login/oauth2/code/{registrationId}`.
- Some configurations provide a default login page.

Spring Security uses Authorization Code Grant. `state`, `nonce`, and `PKCE` are distinct mechanisms:
- `state` binds the authorization response to the initiating request.
- `nonce` binds the ID token to the authentication request, reducing replay/mix-up.
- `PKCE` protects the authorization code with a code verifier/challenge, especially critical for public clients and aligned with modern OAuth recommendations.
- Never reuse a static `nonce`/`state` value across all sessions.
- The redirect flow requires HTTPS, registered redirect URIs, and proper reverse proxy controls.

**The ID token never goes to business APIs in the flow above.** When the backend wants to call an API, it uses the access token inside `OAuth2AuthorizedClient`.

## 4. OAuth2User: Principal Data and Authorities

Import:

~~~java
import org.springframework.security.oauth2.core.user.OAuth2User;
~~~

This interface provides:
- `getName()`: principal identifier name per implementation/provider.
- `getAttributes()`: map of attributes.
- `getAttribute(String name)`: attribute value by key.
- `getAuthorities()`: list of `GrantedAuthority` attached by Spring Security after login/mapping.

Example controller snippet:

~~~java
@GetMapping("/api/me")
public Mono<Map<String, Object>> profile(
        @AuthenticationPrincipal OAuth2User user) {
    return Mono.just(Map.of(
            "name", user.getName(),
            "attributeNames", user.getAttributes().keySet()));
}
~~~

This is not a standalone file: it requires a `@RestController` class, imports, and security configuration. Never serialize `user` directly or return all attributes, as they may contain PII or internal properties.

### 4.1. Name Attributes Differ Across Providers

One OAuth2 provider has field `id`, while another has `login` or `user_name`. `DefaultOAuth2User` uses `nameAttributeKey` to determine which field becomes the principal name.

~~~java
// Snippet inside a Java method with appropriate imports:
OAuth2User user = new DefaultOAuth2User(
        List.of(new SimpleGrantedAuthority("OAUTH2_USER")),
        Map.of("provider_id", "42", "display_name", "Learner"),
        "provider_id");

System.out.println(user.getName()); // 42
~~~

Imports: `List`, `Map`, `SimpleGrantedAuthority`, `OAuth2User`, and `DefaultOAuth2User`. This name is not automatically an email, internal username, or global ID.

### 4.2. OAuth2User Is Not an Access-Token Container

`getAttributes()` reflects user attributes; it is **not** the token exchange result. Never call `getAttribute("access_token")` and assume it is a valid OAuth token, and never treat unverified attributes as roles/privileges.

When you need the access token issued to the client, see `OAuth2AuthorizedClient` in section 9.

## 5. OidcUser Is a Specialized OAuth2User

Import:

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
~~~

`OidcUser extends OAuth2User`. It adds:
- `getIdToken()`: returns the login's `OidcIdToken`.
- `getUserInfo()`: returns `OidcUserInfo` when available.
- `getClaims()`: set of OIDC claims combining ID token/UserInfo.
- Standard accessors such as `getSubject()`, `getEmail()`, and `getPreferredUsername()` depending on claims.

A controller accepting `OAuth2User` **can** be injected with an `OidcUser` when the actual login uses OIDC. This follows interface inheritance.

~~~java
if (user instanceof OidcUser oidc) {
    String subject = oidc.getIdToken().getSubject();
    // Use subject as provider identity per policy.
}
~~~

**Never cast `(OidcUser) user` blindly** for every `OAuth2User` if the app supports OAuth2-only providers. Check `instanceof`, use clearly protected OIDC-specific endpoints, or build an internal user-identity adapter.

### 5.1. OidcIdToken

An ID token may contain claims:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-pairwise-42",
  "aud": "web-client-1",
  "iat": 1760000000,
  "exp": 1760003600,
  "nonce": "request-specific-nonce",
  "email": "learner@example.test",
  "email_verified": true
}
~~~

This is merely an **illustrative JSON payload**, not a signed JWT and cannot be used to log in. An OIDC ID token is a JWT whose signature and claims must be verified per OIDC before trusting it.

Key methods:
- `oidc.getIdToken().getTokenValue()`: raw token — **never expose to frontend, logs, or analytics**.
- `oidc.getIdToken().getSubject()`: subject declared by the provider in the token.
- `oidc.getIdToken().getClaims()`: ID token claims, which may contain PII.

In real projects, expose only a minimal DTO with appropriate access permissions.

### 5.2. OidcUserInfo

The OIDC UserInfo endpoint returns claims about the end-user to the OIDC client, typically called with an **access token**. `OidcReactiveOAuth2UserService` can delegate to `DefaultReactiveOAuth2UserService` to load UserInfo.

**Important:** OIDC requires `sub` in the UserInfo response to match `sub` in the ID token; otherwise, the UserInfo data must not be used. This prevents mixing up information between two accounts.

Not every provider returns `email`, `picture`, or `name`. Even `email_verified=true` does not mean the user holds `ADMIN` privileges in your application.

### 5.3. DefaultOidcUser

`DefaultOidcUser` is a common implementation holding authorities, the ID token, UserInfo, and an optional principal name attribute key. Never construct `DefaultOidcUser` from client-submitted JSON and mark the user authenticated. Let Spring Security/the OIDC provider perform validation first.

## 6. Comparison Table of the Three Tokens

| Property | Access token | ID token | Refresh token |
| --- | --- | --- | --- |
| Purpose | Authorizes calling protected resources | Authenticates user to OIDC client | Requests a new access token |
| Intended recipient | Resource server/API | Client (relying party) | Authorization server/token endpoint |
| Where used | `Authorization: Bearer ...` to the right API | OIDC login token response; client validates it | Refresh-token grant at token endpoint |
| Format | Opaque or JWT, per provider | Signed JWT per OIDC | Per provider, typically opaque |
| Contents | Resource audience, scopes, expiry | `iss`, `sub`, `aud`, `exp`, `iat`, `nonce` when applicable | Not a user profile |
| Retrieved in Spring | `OAuth2AuthorizedClient.getAccessToken()` | `OidcUser.getIdToken()` | `OAuth2AuthorizedClient.getRefreshToken()` when present |
| Put in URL/query/logs? | No | No | No |
| Interchangeable? | **No** | **No** | **No** |

**JWT is a format, not a token's purpose.** An access token can be a JWT without becoming an ID token; an ID token having JWT shape is still not a suitable access token for an API to accept.

### 6.1. Access Tokens Carry the API's Audience

Example:
- ID token: `aud = "web-client-1"`.
- Access token: `aud = "orders-api"`, scope `orders.read`.

The backend calls `orders-api` with that access token; the resource server verifies audience/trust/lifetime/scope per policy. If an API accepts an ID token with `aud=web-client-1`, it has bypassed the audience boundary.

### 6.2. Token Expiration Is Not WebSession Timeout

ID token, access token, refresh token, and login session lifetimes can all differ. A still-valid browser session does not automatically keep an expired access token valid; the authorized client manager may refresh the access token per provider/policy. Refresh tokens are never sent to business APIs.

## 7. ID Token Claims You Must Understand

### Issuer — iss

`iss` is the identifier of the OIDC Provider that issued the token. The client must trust only configured providers, never accepting a JWT from an arbitrary issuer just because its structure looks similar.

### Subject — sub

`sub` is the user ID within the issuer's namespace. OIDC supports public and pairwise subjects; never assume it equals an email or can be compared across multiple issuers.

Typical durable account-linking key:

~~~text
Trusted external identity = (issuer, subject)
~~~

Never use email as the sole key because email addresses can change, be missing, or belong to a different account in certain contexts.

### Audience — aud

The ID token `aud` must match the relying party's `client_id`. When `aud` has multiple elements, also follow OIDC rules around `azp`. **This is why another API must not accept the web client's ID token.**

### Expiry and Issued-At — exp, iat

`exp` is the expiration time of token validity; `iat` is when it was issued. The client validates them per OIDC rules, system time, and clock-skew policy. Never just decode the JWT payload and skip validation.

### Nonce — nonce

`nonce` binds the authentication request to the ID token, preventing replay in nonce-enabled flows. When a nonce was sent, verify the returned token carries the matching value per protocol. Never hardcode the same nonce across requests.

### Email, email_verified, acr, amr

- `email` may be absent or change.
- `email_verified` reflects whether the provider verified the email under its own policy; it is **not a role entitlement**.
- `acr` and `amr` can describe authentication level/methods if supported by the provider; using them for step-up requires explicit policy, not blind trust.
- Never rely on optional claims to skip object/tenant authorization.

## 8. Verifying the ID Token: Decoding Is Not Enough

A JWT typically has the form `header.payload.signature`. Base64URL decoding lets you inspect the payload, but it does **not** prove:
- A valid JWS signature.
- A trusted issuer.
- The right client audience.
- Valid `exp`/`iat`.
- Matching `nonce`.
- Policy-compliant signing algorithm.
- Valid key rotation/JWKS.

Spring Security OIDC Login provides components such as `ReactiveOidcIdTokenDecoderFactory` and `ReactiveJwtDecoder` to verify ID tokens alongside proper OIDC logic.

Required flow:
1. Build an authorization request with `state` and client protections.
2. Receive the authorization code callback and verify `state`.
3. Exchange the code at a trusted token endpoint.
4. Verify ID token signature and claims.
5. If using UserInfo, match the subject.
6. Only then create `OidcUser`/`Authentication` and the login session.

Never write custom code that takes `id_token` from browser-submitted JSON and calls `new UsernamePasswordAuthenticationToken(..., authorities)` while skipping OIDC steps. Never disable signature/audience validation to fix a provider configuration error.

## 9. OAuth2AuthenticationToken vs. OAuth2AuthorizedClient

### 9.1. Authentication After Login

`OAuth2AuthenticationToken` holds the principal, authorities, and authorized client registration ID. Snippet example:

~~~java
if (authentication instanceof OAuth2AuthenticationToken oauth) {
    OAuth2User principal = oauth.getPrincipal();
    String registrationId = oauth.getAuthorizedClientRegistrationId();
}
~~~

**It does not provide `getAccessToken()` for you to use like an authorized client.** The registration ID tells you which client/provider was involved in the login.

### 9.2. OAuth2AuthorizedClient

`OAuth2AuthorizedClient` binds:
- `ClientRegistration`.
- Principal name.
- `OAuth2AccessToken`.
- `OAuth2RefreshToken` if issued.

Reactive components managing this:
- `ServerOAuth2AuthorizedClientRepository`: persistence scoped to request/server web context.
- `ReactiveOAuth2AuthorizedClientService`: application-level management of authorized clients.
- `ReactiveOAuth2AuthorizedClientManager`: coordinates authorization, refresh/re-authorization, and persistence.

Never serialize this object as JSON in a profile endpoint because it can contain both the access token and refresh token.

### 9.3. Reading Access Token Metadata in WebFlux

Snippet outside the standalone demo project in section 13:

~~~java
@GetMapping("/api/token-metadata")
public Mono<Map<String, Object>> metadata(
        @RegisteredOAuth2AuthorizedClient("demo")
        OAuth2AuthorizedClient client) {
    OAuth2AccessToken token = client.getAccessToken();
    return Mono.just(Map.of(
            "tokenType", token.getTokenType().getValue(),
            "scopes", token.getScopes(),
            "hasExpiration", token.getExpiresAt() != null));
}
~~~

Requires importing `@RegisteredOAuth2AuthorizedClient`, `OAuth2AuthorizedClient`, `OAuth2AccessToken`, `Map`, `Mono`, and a real authorized client for registration `demo`. **Never return `token.getTokenValue()`**. Even scope metadata should be evaluated before exposing it to the frontend.

### 9.4. Using Access Tokens with WebClient

In the Reactive stack, `ServerOAuth2AuthorizedClientExchangeFilterFunction` attaches access tokens to selected outbound requests:

~~~java
// @Bean snippet requiring a validly configured manager:
@Bean
WebClient securedWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {
    var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
    return WebClient.builder().filter(filter).build();
}
~~~

When calling, provide the appropriate registration ID or `OAuth2AuthorizedClient` for the target API. Never enable `setDefaultOAuth2AuthorizedClient(true)` globally without controlling every remote URL; tokens could be sent to unintended or untrusted endpoints.

Manual snippet only when holding an access token for the right resource:

~~~java
return webClient.get()
        .uri("https://orders-api.example.test/orders")
        .headers(h -> h.setBearerAuth(
                authorizedClient.getAccessToken().getTokenValue()))
        .retrieve()
        .bodyToMono(String.class);
~~~

This is a non-standalone snippet; `authorizedClient` must be issued/managed by the system for the right user, client registration, and API audience.

## 10. OAuth2 Login, OIDC Login, and Resource Server Differ

| Spring Security Feature | Primary Input | Typical Principal/Authentication | Goal |
| --- | --- | --- | --- |
| OAuth2 Login (non-OIDC) | Authorization Code + OAuth2 provider user info | `OAuth2AuthenticationToken` + `OAuth2User` | Log in user |
| OIDC Login | Authorization Code, ID token, UserInfo | `OAuth2AuthenticationToken` + `OidcUser` | Log in with OIDC ID token |
| OAuth2 Resource Server JWT | Incoming Bearer JWT **access token** | `JwtAuthenticationToken` | Protect APIs |
| Resource Server opaque token | Incoming Bearer opaque access token | `BearerTokenAuthentication` or `OAuth2AuthenticatedPrincipal` | Protect APIs |
| OAuth2 Client WebClient | Authorized client / access token | `OAuth2AuthorizedClient` | Call external APIs |

Never use `@AuthenticationPrincipal OidcUser` on an API configured solely as a JWT Resource Server and wonder why the principal is a `Jwt`/different Authentication type. Both paths can be combined in one app, but security chains and route scopes must be clearly separated.

### 10.1. A Resource Server API Must Validate Its Own Access Tokens

Architectural snippet (not part of the runnable project below):

~~~java
return http
        .authorizeExchange(ex -> ex
                .pathMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
        .build();
~~~

Requires `spring-boot-starter-oauth2-resource-server`, issuer/JWKS/audience decoder configuration, and appropriate authorization. An OIDC login client does not replace JWT Resource Server validation.

## 11. Authorities and Scopes Do Not Automatically Become Internal Roles

Spring Security may attach `OAUTH2_USER` or `OIDC_USER` authorities, `SCOPE_...` authorities, and others depending on mapping. `hasRole("ADMIN")` normally checks `ROLE_ADMIN`, which is **not equivalent** to `hasAuthority("ADMIN")`.

~~~java
// Snippet inside authorizeExchange:
.pathMatchers("/api/admin/**").hasRole("ADMIN")
.pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")
~~~

However, OIDC scopes such as `openid`, `email`, and `profile` do not mean the user is allowed to read someone else's reports.

Safe authority mapping approach:
1. Verify the OIDC issuer/subject and obtain the login principal from the validated library.
2. Look up permissions from a **trusted** application database/entitlement service.
3. Assign roles based on tenant/account mapping, never email suffixes.
4. Enforce ownership/tenant checks in services for every resource.
5. Write negative tests for logged-in users lacking permissions.

Anti-pattern:

~~~java
// WRONG: an email belonging to a domain is not sufficient proof of ADMIN privileges.
if (email.endsWith("@company.example.test")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

Emails can be absent, unverified, or unrelated to internal memberships/entitlements. Even `email_verified=true` does not replace security reviews or tenant policies.

Spring Security Reactive provides `GrantedAuthoritiesMapper`, `ReactiveOAuth2UserService`, and `OidcReactiveOAuth2UserService` for authority mapping, while preserving valid permissions after calling UserInfo/entitlement endpoints.

## 12. WebFlux Reactive vs. Servlet

| WebFlux/Reactive | Servlet/MVC | Role |
| --- | --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` | Security configuration |
| `SecurityWebFilterChain` | `SecurityFilterChain` | Filter chain |
| `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` | Client registrations |
| `ReactiveOAuth2AuthorizedClientService` | `OAuth2AuthorizedClientService` | Client token persistence |
| `ServerOAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientRepository` | Per-request authorized clients |
| `ReactiveOAuth2UserService` | `OAuth2UserService` | Load user attributes |
| `DefaultReactiveOAuth2UserService` | `DefaultOAuth2UserService` | Non-OIDC user service |
| `OidcReactiveOAuth2UserService` | `OidcUserService` | OIDC user service |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Servlet WebClient counterpart | Forward access tokens to APIs |

`OAuth2User`, `OidcUser`, and token models are **shared** Spring Security abstractions, while security filters, user services, and authorized-client persistence use the Reactive variants.

In WebFlux, never use `HttpServletRequest` or call `block()` inside a user service. `DefaultReactiveOAuth2UserService` uses `WebClient`; compose `Mono` pipelines when customizing mapping.

## 13. Runnable Java 17+ Project: Observing OAuth2User and OidcUser

This example uses **Java 17, Spring Boot 3.5.7, WebFlux, and Spring Security Reactive**. It has a static OAuth2 client registration pointing to an **illustrative** hostname so the app/tests can bootstrap without contacting OIDC Discovery at startup.

Goals:
- App boots locally with `GET /public/ping`.
- Unauthenticated API calls intentionally return 401.
- `GET /api/me` returns a **selective DTO** for `OAuth2User` or `OidcUser`.
- `GET /api/oidc` demonstrates using OIDC-specific features only for the right principal type.
- `WebTestClient` uses `mockOAuth2Login` / `mockOidcLogin` to test without a real provider.

**Real login cannot be completed with `idp.example.test`!** For real browser login, replace provider URLs/issuer, client ID/secret, and redirect URI with trusted settings. Mock tests are not proof that an ID token was signed and verified.

### 13.1. Structure

~~~text
reactive-oidc-user-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── IdentityController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/demo/
        └── OAuth2OidcPrincipalTest.java
~~~

### 13.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-oidc-user-demo'
~~~

### 13.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-client` is for login/client APIs. `spring-boot-starter-oauth2-resource-server` is a separate dependency for incoming Bearer API access tokens.

### 13.4. application.yml for Local Study

~~~yaml
server:
  port: 8080
  reactive:
    session:
      cookie:
        http-only: true

spring:
  application:
    name: reactive-oidc-user-demo
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: DEMO_CLIENT_ID
            client-secret: DEMO_CLIENT_SECRET
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo:
            authorization-uri: https://idp.example.test/authorize
            token-uri: https://idp.example.test/token
            jwk-set-uri: https://idp.example.test/jwks.json
            user-info-uri: https://idp.example.test/userinfo
            user-name-attribute: sub
~~~

The provider URLs are documentation placeholders with **no live IdP**. `issuer-uri` is omitted in the offline config to avoid an OIDC discovery call to a dummy hostname at startup. **Do not deploy to production** with this config; production requires a trusted provider issuer/JWKS, issuer/audience validation, secure client secrets, and HTTPS.

### 13.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 13.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/me", "/api/oidc")
                                .authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .exceptionHandling(ex -> ex.authenticationEntryPoint(
                        new HttpStatusServerEntryPoint(
                                HttpStatus.UNAUTHORIZED)))
                .build();
    }
}
~~~

- `oauth2Login` enables the OAuth2/OIDC login client.
- `/api/me` and `/api/oidc` require authentication; `anyExchange().denyAll()` blocks undeclared business routes.
- `HttpStatusServerEntryPoint` intentionally returns **401** instead of redirecting API requests to a login page. Interactive login still starts at `/oauth2/authorization/demo`.
- CSRF remains enabled by default and must protect POST/session-based browser flows when added.
- This is a learning configuration; in real apps, test login callbacks, default login pages, logout, and entry points on each security chain.

### 13.7. IdentityController.java

`src/main/java/demo/IdentityController.java`:

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, Object>> me(
            @AuthenticationPrincipal OAuth2User principal) {

        if (principal == null) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "OAuth2 login required"));
        }

        Map<String, Object> view = new LinkedHashMap<>();
        view.put("principalType",
                principal instanceof OidcUser ? "OIDC" : "OAUTH2");
        view.put("principalName", principal.getName());
        view.put("authorities", principal.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList());

        if (principal instanceof OidcUser oidc) {
            view.put("idTokenSubject",
                    oidc.getIdToken().getSubject());
            view.put("hasUserInfo", oidc.getUserInfo() != null);
        }

        // Do not serialize whole principal / raw tokens / PII.
        return Mono.just(view);
    }

    @GetMapping("/api/oidc")
    public Mono<Map<String, Object>> oidcOnly(
            @AuthenticationPrincipal OAuth2User principal) {

        if (!(principal instanceof OidcUser oidc)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "OIDC principal required"));
        }

        return Mono.just(Map.of(
                "principalType", "OIDC",
                "subject", oidc.getIdToken().getSubject(),
                "hasUserInfo", oidc.getUserInfo() != null));
    }
}
~~~

This DTO **intentionally omits** `getIdToken().getTokenValue()`, `OAuth2AuthorizedClient`, access/refresh tokens, and full claims/attributes. `subject`/`principalName` are illustrative identifiers; production requires an appropriate privacy policy because they can still be considered user data.

`/api/oidc` returning 403 when the principal is not an `OidcUser` **only demonstrates type distinction**; it does not imply every business endpoint should check Java types instead of authorization/roles.

The code uses Java 17 pattern matching `instanceof` and does not block the Reactor event loop.

## 14. Running the App and Observable Conditions

In the directory containing `build.gradle`:

~~~bash
gradle test
gradle bootRun
~~~

If using the Gradle Wrapper: `./gradlew` on Linux/macOS or `gradlew.bat` on Windows. These commands are for the learner to run; **do not claim builds/tests have already been executed here**.

### 14.1. Public Ping

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expected HTTP **200**, body:

~~~text
pong
~~~

### 14.2. Unauthenticated

~~~bash
curl -i http://localhost:8080/api/me
~~~

Expected HTTP **401 Unauthorized** per the configured entry point. With standard OIDC login, protected routes may redirect to a login page depending on policy, but this API example explicitly returns 401.

### 14.3. Interactive Login Needs a Real IdP

Starts at:

~~~text
http://localhost:8080/oauth2/authorization/demo
~~~

With the non-existent demo provider `idp.example.test`, the authorization-code callback cannot complete. To run real login, configure a real issuer/credentials/redirect URI as in section 16. The tests below require no network provider because they mock principals.

## 15. WebTestClient: Mocking OAuth2User and OidcUser

Spring Security Test Reactive provides `mockOAuth2Login()` and `mockOidcLogin()`. They populate a mock SecurityContext and principal, **without verifying ID token signatures or calling an IdP**. Thus, they are great for **controller tests**, not a replacement for full OIDC protocol tests.

`src/test/java/demo/OAuth2OidcPrincipalTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OAuth2OidcPrincipalTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicPingWorks() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousUserReceives401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void oauth2LoginHasGenericPrincipal() {
        client.mutateWith(mockOAuth2Login()
                    .attributes(attrs -> attrs.put("sub", "oauth-user-42")))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("OAUTH2")
                .jsonPath("$.principalName").isEqualTo("oauth-user-42")
                .jsonPath("$.idTokenSubject").doesNotExist();
    }

    @Test
    void oidcLoginHasIdTokenSubject() {
        client.mutateWith(mockOidcLogin()
                    .idToken(token -> token.claim("sub", "oidc-user-24")))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("OIDC")
                .jsonPath("$.idTokenSubject").isEqualTo("oidc-user-24");
    }

    @Test
    void oauth2OnlyPrincipalCannotUseOidcDemoEndpoint() {
        client.mutateWith(mockOAuth2Login())
                .get().uri("/api/oidc")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void oidcPrincipalCanUseOidcDemoEndpoint() {
        client.mutateWith(mockOidcLogin()
                    .idToken(token -> token.claim("sub", "oidc-user-99")))
                .get().uri("/api/oidc")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("OIDC")
                .jsonPath("$.subject").isEqualTo("oidc-user-99");
    }

    @Test
    void profileDoesNotReturnTokenValues() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.accessToken").doesNotExist()
                .jsonPath("$.idTokenValue").doesNotExist()
                .jsonPath("$.refreshToken").doesNotExist();
    }
}
~~~

Expected **7 tests** verifying controller responses. The mocked OAuth2-only test produces a different principal type than OIDC; `mockOidcLogin()` supplies an `OidcIdToken` with your declared subject. Tokens in mocks are **not genuinely signed tokens**.

**Do not use these tests to claim issuer/audience/nonce validation is safe.** Add integration tests with an OIDC Provider configured for testing, valid JWKS, and negative cases.

### 15.1. Testing Authority Mapping

Can be extended with:

~~~java
// Snippet inside a test method; requires importing SimpleGrantedAuthority.
client.mutateWith(mockOidcLogin()
        .authorities(new SimpleGrantedAuthority("ROLE_READER")))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
~~~

The goal is simply to build a mock authentication with a specific authority. Never infer from this that a real provider always grants `ROLE_READER`.

### 15.2. Integration Tests Needed with a Real/Mock IdP

- Authorization redirect, state mismatch, nonce mismatch.
- ID token with invalid signature, issuer, audience, `exp`/`iat`.
- JWKS rotation and HTTP/TLS errors.
- UserInfo subject mismatch.
- Multi-tenant/issuer restrictions.
- Access token with wrong audience/scope at resource server.
- Login/logout, expired session, refresh token rotation.
- No token/claim leaks in API responses or logs.

## 16. Switching Config to a Real IdP

Replace the **entire placeholder `provider.demo` group** in `application.yml` with a trusted provider, typically using `issuer-uri` with OIDC Discovery.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: YOUR_CLIENT_ID_FROM_SECRET_MANAGER
            client-secret: YOUR_CLIENT_SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo:
            issuer-uri: https://your-oidc-issuer.example.test
~~~

This is an **illustrative replacement config**, not real credentials. In production use environment variables/a secret manager instead of example strings, HTTPS, and the provider's exact issuer; metadata discovery may access the network at initialization.

Checklist:
1. Create the client registration at the provider; use the right client ID/secret/redirect URI.
2. Enable login/OIDC with scope `openid`.
3. Verify callback URL, TLS/reverse proxy forwarded headers, and Secure/HttpOnly/SameSite session cookies.
4. Keep OIDC issuer/audience/signature/nonce validation enabled.
5. Minimize UserInfo scopes and requested claims.
6. Use audience/resource-specific access tokens for APIs.
7. Never store secrets in Git, logs, query strings, or browser source.
8. Depending on the model, use PKCE and protect state/sessions per provider requirements.
9. Test login across multiple instances, shared session stores, and token persistence.
10. Design application and IdP logout according to specific needs.

## 17. Access Tokens Are for APIs, ID Tokens Are for Clients

If the provider issues:
- `id_token` with `aud=web-client`.
- `access_token` intended for `orders-api` with scope `orders.read`.

When the backend calls the resource server:

~~~http
GET /orders HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <access-token-for-orders-api>
~~~

Do not use:

~~~http
Authorization: Bearer <id-token-for-web-client>
~~~

The resource server must validate tokens according to their semantics. Never accept a JWT merely because the issuer signature is valid while ignoring audience, scope, expiry, or token profile; a signed ID token still grants no API access.

The OIDC UserInfo endpoint is also a protected resource using an **access token**; it does not accept an ID token as a credential per protocol.

## 18. Login Session, Token Expiry, and Logout

Three unsynchronized clocks:

| Component | Lifecycle |
| --- | --- |
| WebSession/login session | Cookie, idle timeout, invalidation/logout; may renew on activity |
| Access token | Expiry, scopes/audience, refresh/re-authorization |
| ID token | `exp` and OIDC validation for authentication at login time |

For example, a user logs in at 10:00, access token TTL is 10 minutes, and WebSession idle timeout is 30 minutes: at 10:12, the browser session may still be active, yet the authorized client must refresh the access token before calling APIs. Never send the ID token to an API in place of an expired access token.

### 18.1. Logging Out of the App Does Not Necessarily Log Out of the IdP

WebFlux session invalidation clears local login state per the active mechanism. The OIDC Provider may still keep an SSO session, so the next login attempt might succeed automatically. If Single Logout is required, evaluate OIDC RP-Initiated Logout and provider support.

Systems must also evaluate revoking access/refresh tokens if the threat model or policy requires it. Deleting a browser cookie does not revoke a previously stolen token.

### 18.2. Protecting Authorized-Client Storage

Access and refresh tokens may be stored in `ServerOAuth2AuthorizedClientRepository`/`ReactiveOAuth2AuthorizedClientService`. Never expose the objects, log tokens, use shared storage without access controls, or place tokens in sessions/URLs in a way that leaks them.

## 19. Common Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Using ID token as Bearer access token | Wrong audience and purpose; token substitution | Fetch access token from `AuthorizedClient` |
| Treating a JWT access token as an ID token | OAuth2 access tokens do not replace authentication protocols | Use OIDC ID token validation |
| Reading `getAttributes()` to find access tokens | The principal is not a token store | Use `AuthorizedClient` repository/manager |
| Returning `OidcUser` or ID token value in JSON | Leaks PII/credentials | Use a minimal DTO |
| Parsing JWT without verifying signature | Accepts forged tokens | Standard decoder/validator |
| Checking signature only, skipping `iss`/`aud` | Accepts tokens from other apps/providers | Validate issuer/audience/time/nonce |
| Using email as unique ID | Emails can change or be unverified | Trusted issuer + subject |
| Granting ADMIN by email domain | Domain is not an entitlement | Look up permissions from trusted source |
| Casting `OAuth2User` to `OidcUser` | OAuth2-only has no ID token | `instanceof` or adapter |
| Sending access token to every `WebClient` URL | Leaks tokens outside trust boundary | Attach tokens selectively |
| Confusing `JwtAuthenticationToken` with `OidcUser` | Resource Server API differs from login client | Separate the two security roles |
| Treating scope `openid` as data-read permission | `openid` activates OIDC, not roles | Separate authorization/ownership |
| Using client secret in frontend | Cannot be kept secret | Server-side secret / PKCE per client |
| Disabling issuer/nonce so login works | Drops anti-replay/trust protections | Fix provider/config |
| Assuming access token TTL = session TTL | Login and API-calling permissions drift | Track each lifecycle separately |
| Treating `mockOidcLogin` as a valid ID token | Mock skips validation/IdP | Separate integration tests |
| Blocking inside Reactive user service | Blocks the event loop | Use `Mono`/`flatMap` |
| Local logout only when SSO logout is needed | IdP session remains | OIDC logout policy |
| Leaving token logs/storage unprotected | Credential leak | Redaction, encryption, ACLs |

## 20. Troubleshooting by Symptom

### 20.1. Principal Returns OAuth2User Instead of OidcUser

- Does the client registration include `openid`?
- Does the provider support OIDC and issue a valid ID token?
- Is the request going through `oauth2Login` rather than Basic/Resource Server?
- Does the app have a custom `ReactiveOAuth2UserService` altering the principal?
- Does the controller inspect the right authentication principal/type?

Never cast blindly to `OidcUser`. If the provider is OAuth2-only, support `OAuth2User`; if OIDC is needed, fix the client/provider flow.

### 20.2. Access Token Calls API A Successfully, but API B Returns 401/403

- Check the token's audience for API B.
- Are the granted scopes/permissions right?
- Is the token expired, revoked, or needing refresh?
- Did the Authorization header accidentally carry an ID token?
- Does Resource Server B have a different issuer/JWKS/token profile?
- Does the `AuthorizedClient` registration belong to the right user?
- Did a `WebClient` filter send client A's token to host B?

Never solve this by disabling audience validation.

### 20.3. Mock Tests PASS, but Browser Login FAILS

- Authorization endpoint/redirect URI/callback code/state.
- Client secret/token endpoint authentication.
- OIDC issuer/JWKS/signature/audience/nonce.
- Session cookie Secure/SameSite, reverse proxy TLS.
- Shared session store if multi-instance.
- Consent/callback errors from provider.
- UserInfo `sub` mismatch.

Mock tests do not execute OAuth code exchange or token validation; test end-to-end with a trusted provider.

### 20.4. User Is Logged In but Lacks Permissions

- `ROLE_ADMIN` differs from `OIDC_USER` and `SCOPE_profile`.
- Were role mappings/tenant entitlements loaded from a trusted source?
- Does the route have the right authorization matcher?
- Are method-level/object-level checks denying access?
- Does POST have a CSRF token?
- Are stale permissions cached in the session?

Never flip 403 to 200 or grant ADMIN to every OIDC-logged-in user.

## 21. Architecture and Testing Checklist

### OIDC Login
- [ ] `openid` scope configured and provider supports OIDC.
- [ ] Uses Authorization Code, `state`, `nonce`/PKCE per flow.
- [ ] Issuer/JWKS/redirect URI come from trusted sources.
- [ ] Verifies signature, `iss`, `aud`, `exp`, `iat`, and `nonce` when applicable.
- [ ] UserInfo `sub` matches ID token.
- [ ] Never trusts email/name as roles or sole identifier keys.
- [ ] Never exposes raw ID tokens/PII in responses/logs.

### OAuth2 Client and Resource Server
- [ ] Access tokens target the exact API/resource audience.
- [ ] Token scopes fit business needs.
- [ ] Tokens retrieved from `OAuth2AuthorizedClient`/manager, never from `OidcUser.getIdToken`.
- [ ] Refresh tokens kept secret, never sent to business APIs.
- [ ] Resource server validates incoming access tokens for right issuer/audience/signature/introspection.
- [ ] Default token propagation is not enabled for all URLs.
- [ ] Does not confuse `JwtAuthenticationToken` with OAuth2 login principals.

### Authorization, Session, Operations
- [ ] Authorities/roles mapped from trusted sources.
- [ ] Object/tenant ownership enforced beyond HTTP matchers.
- [ ] WebSession/logout and token TTLs designed separately.
- [ ] OIDC SSO logout evaluated if required.
- [ ] Cookies use appropriate Secure/HttpOnly/SameSite and HTTPS.
- [ ] OAuth secrets absent from code/frontend/logs.
- [ ] CORS/CSRF evaluated for browser-based login.

### Testing
- [ ] `mockOAuth2Login` and `mockOidcLogin` have dedicated tests.
- [ ] Tests cover anonymous users and wrong principal types.
- [ ] Tests verify ID/access/refresh tokens are not leaked.
- [ ] Tests cover authority mapping and ownership.
- [ ] Tests cover issuer/audience/nonce/signature via IdP/validator integration.
- [ ] Tests cover UserInfo `sub` mismatch.
- [ ] Tests cover refresh/logout/multiple sessions.
- [ ] Does not treat `WebTestClient` mocks as verification of the real OIDC protocol.

## 22. Self-Check Questions

**1. How does OAuth2User differ from OidcUser?**

> `OAuth2User` represents an OAuth2 login principal with attributes/authorities; `OidcUser` extends it with an OIDC ID token, UserInfo, and claims.

**2. Can an OidcUser be passed into an OAuth2User parameter?**

> Yes, because `OidcUser extends OAuth2User`.

**3. What is an access token used for?**

> Used to call protected resources/APIs matching audience, scopes, and authorization policy.

**4. Who is an ID token intended for?**

> Intended for the OIDC client/relying party to confirm the authentication result, not for business APIs.

**5. Is an access token always a JWT?**

> No. It may be opaque or a JWT depending on the provider.

**6. Why is a readable ID token payload not yet trustworthy?**

> Decoding does not verify the signature, issuer, audience, expiry, or nonce.

**7. To call an API after login, is it right to look for the access token inside `OidcUser.getClaims()`?**

> No. Retrieve it from `OAuth2AuthorizedClient` or the Reactive authorized client manager.

**8. Should `id_token` be used as `Authorization: Bearer` when calling UserInfo?**

> No. UserInfo uses the access token.

**9. Does the `openid` scope equal `ROLE_ADMIN`?**

> No. It enables OIDC; internal roles require separate entitlements.

**10. Why should `issuer + sub` be used for account linking?**

> Because `subject` is scoped to the issuer's namespace; emails can change or be absent.

**11. Does `mockOidcLogin()` verify JWT digital signatures?**

> No. It mocks an authenticated principal for controller tests.

**12. Does an expired ID token automatically expire `WebSession` immediately?**

> Not by default; each object has its own lifecycle.

**13. Does logging out of the app automatically end SSO at the IdP?**

> Not by default. Provider logout protocol/config is needed if required.

**14. What principal/Authentication type does a Resource Server API typically have with JWT Bearer tokens?**

> Typically `JwtAuthenticationToken`, not the `OidcUser` from browser login.

**15. Why not call `setDefaultOAuth2AuthorizedClient(true)` for every WebClient call?**

> It can forward tokens to URLs that do not need credentials or are untrusted; attach tokens selectively.

## 23. Summary

In **Spring Security Reactive**:

- **`OAuth2User` / `OidcUser` are principals** after login. `OidcUser` is an `OAuth2User` with OIDC-specific ID token/UserInfo.
- **ID tokens are for the OIDC client**, carrying issuer, subject, audience, expiry, and authentication claims. They are not default authorization tokens for business APIs.
- **Access tokens are for the appropriate resource server** and are managed alongside `OAuth2AuthorizedClient`. When calling downstream APIs, send an access token with the right audience and scope.
- **Refresh tokens** are used strictly for token lifecycle at the authorization server, never sent to business APIs.
- **Authentication does not replace authorization**: roles, tenants, ownership, and API scopes must be verified independently of login.

When implementing, use the proper WebFlux Reactive APIs, keep issuer/audience/signature/nonce validation intact, separate session/token lifetimes, protect credentials, and test both principal mocks and real OIDC flows.

### Official Reference Documentation

- Spring Security — Reactive OAuth2/OIDC Login: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Login Core: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html
- Spring Security — Advanced OAuth2/OIDC Login: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html
- Spring Security — OAuth2 Client Core Interfaces (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security — Authorized Client Features: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security — Testing OAuth2/OIDC in WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security API — OAuth2User: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/core/user/OAuth2User.html
- Spring Security API — OidcUser: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Framework RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth2 JWT Access Token Profile RFC 9068: https://www.rfc-editor.org/rfc/rfc9068
- OAuth 2.0 Security Best Current Practice RFC 9700: https://www.rfc-editor.org/rfc/rfc9700