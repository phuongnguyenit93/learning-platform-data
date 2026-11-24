# ClientRegistration, provider, and ReactiveClientRegistrationRepository in Spring Security WebFlux

> **Scope:** Spring Security 6.x, Spring WebFlux, Spring Boot 3.3.x, Java 17+, OAuth 2.0 / OpenID Connect (OIDC) login using Authorization Code. This lesson explains three commonly confused components: `ClientRegistration` describes the client configuration, `provider` describes the Authorization Server/Identity Provider, and `ReactiveClientRegistrationRepository` lets WebFlux look up that configuration. The code uses Spring Boot 3.3.13 to illustrate the API; production projects should choose a maintained version with security patches.

## 1. The Real-World Problem

An internal portal wants to let employees sign in using the enterprise Identity Provider (IdP). Before allowing a browser to be redirected to the IdP, the application must know:

1. **Which client is the application at the IdP?** Client ID, client authentication method, redirect URI, scopes.
2. **Which IdP serves the client?** Authorization endpoint, token endpoint, issuer, JWKS, UserInfo endpoint.
3. **Where does Spring Security find that configuration?** Repository lookup by `registrationId`.

```text
Browser                  Spring WebFlux                         OIDC IdP
   |                           |                                  |
   | GET /private/me           |                                  |
   |-------------------------->| no Authentication yet            |
   |<--------------------------| redirect to login flow           |
   |                           |                                  |
   | GET /oauth2/authorization/corporate                          |
   |-------------------------->|                                  |
   |                ReactiveClientRegistrationRepository          |
   |                      findByRegistrationId("corporate")       |
   |                           |                                  |
   |<--------------------------| 302 Location: IdP /authorize     |
   |---------------------------- GET /authorize?client_id=... -->|
   |                           |                             login|
   |<--------------------------- redirect ?code=...&state=... ---|
   | GET /login/oauth2/code/corporate                             |
   |-------------------------->| match state, exchange code/token |
   |                           |------------------------------->  |
   |                           |<-------------------------------  |
   |                           | verify ID token / principal      |
   |<--------------------------| save SecurityContext/session     |
```

**A successfully created `ClientRegistration` does not mean the user is logged in.** It is merely the configuration to initiate an authentication protocol. The IdP must exist, the callback must match, the tokens must be valid, and Spring Security must create the Authentication.

## 2. Foundational Concepts

| Term | Meaning | Not Synonymous With |
|---|---|---|
| **OAuth2 Client** | Your application needing login or to call external APIs | Resource Server receiving bearer tokens |
| **Authorization Server** | System issuing authorization codes and tokens | ClientRegistrationRepository |
| **Identity Provider / OIDC Provider** | Service authenticating end-users per OpenID Connect | User in the application's database |
| **Resource Owner / End-user** | Person performing login/consent | Client application |
| **ClientRegistration** | A configured client in the app: ID, secret, grant, scopes, redirect, endpoints | An issued login session or access token |
| **registrationId** | Internal key chosen by the app to look up a registration | `client_id` issued by the IdP |
| **providerId** | Key for the endpoint/issuer block in `spring.security.oauth2.client.provider` | Must-match with registrationId |
| **clientId** | Application identifier issued by the IdP | `clientSecret` |
| **OAuth2AuthorizedClient** | Authorized client record for a principal, including tokens | Just `ClientRegistration` |
| **OIDC ID Token** | JWT asserting end-user login information to the client | OAuth2 access token authorizing APIs |

OAuth2 provides an **authorization** mechanism. OIDC adds an **end-user authentication** layer based on the ID Token, issuer, subject, and protocol checks. In Spring Security, a `scope` containing `openid` is the key signal that triggers OIDC processing instead of OAuth2 Login using only OAuth2 UserInfo.

Never manually Base64-read an `id_token` and use `sub` as proof of login: the token must have its signature, issuer, audience, expiration, nonce, and other conditions verified per OIDC.

### Three Illustrative Identifiers

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:                       # registrationId
            provider: enterprise-idp       # providerId
            client-id: portal-web-client   # clientId
        provider:
          enterprise-idp:
            issuer-uri: https://login.example.com/realms/enterprise
```

The snippet above **only illustrates the ID relationships** and lacks full deployment credentials. In this example:

- `corporate` creates the start path `/oauth2/authorization/corporate`.
- `enterprise-idp` selects the provider block.
- `portal-web-client` is sent to the IdP as the OAuth2 `client_id` parameter.

Do not change `registrationId` and forget the callback path; and do not assume any one of these three names must match the other two.

## 3. What Information Does ClientRegistration Hold?

`org.springframework.security.oauth2.client.registration.ClientRegistration` is an immutable configuration-level Java object representing **a client registered with a provider**.

| Field | Role | Example |
|---|---|---|
| `getRegistrationId()` | Local registration name | `corporate` |
| `getClientId()` | Assigned Client ID | `portal-client` |
| `getClientSecret()` | Confidential client secret | Secret manager/environment |
| `getClientAuthenticationMethod()` | How the client authenticates at the token endpoint | `client_secret_basic` |
| `getAuthorizationGrantType()` | OAuth2 grant | `authorization_code` |
| `getRedirectUri()` | Callback URI/template | `{baseUrl}/login/oauth2/code/{registrationId}` |
| `getScopes()` | Requested scopes | `openid`, `profile`, `email` |
| `getClientName()` | Display name on the login chooser | `Corporate SSO` |
| `getProviderDetails().getAuthorizationUri()` | Browser is redirected here to log in | `https://idp.example/authorize` |
| `getProviderDetails().getTokenUri()` | Backend exchanges code for tokens here | `https://idp.example/token` |
| `getProviderDetails().getJwkSetUri()` | Public keys for verifying JWTs | `https://idp.example/jwks` |
| `getProviderDetails().getUserInfoEndpoint()` | Metadata about the UserInfo endpoint | `https://idp.example/userinfo` |
| `getProviderDetails().getIssuerUri()` | OIDC/OAuth issuer identifier | `https://idp.example/realms/corp` |

**Never serialize `ClientRegistration` directly to JSON** from a debug endpoint: the object may contain `clientSecret` and sensitive configuration. If a UI needs a list of login providers, expose only an allowlist containing `registrationId` and safe display names.

### Registration for Login vs. Registration for Outbound APIs

A `ClientRegistration` can be used for OAuth2 Login or for an OAuth2 Client calling protected APIs. However:

- **`oauth2Login()`**: logs in the end-user via Authorization Code, creating an authenticated principal/session.
- **`oauth2Client()`**: manages authorized clients and accesses outbound protected APIs with access tokens.
- **`oauth2ResourceServer()`**: protects your inbound API with Bearer JWT/opaque tokens; it does not need a client registration to verify JWTs in a simple setup.

Do not think adding `spring-boot-starter-oauth2-client` automatically turns an API into a resource server, or that adding `oauth2ResourceServer` creates an OIDC browser login page.

## 4. Provider: Issuer, Authorization URI, Token URI, and JWKS

A provider describes **the identity provider side** that a registration will call.

```text
provider "enterprise-idp"
  |
  +-- issuer-uri          -> IdP/issuer identifier used for token validation
  +-- authorization-uri   -> browser 302 destination for login
  +-- token-uri           -> backend POSTs authorization code to obtain tokens
  +-- jwk-set-uri         -> public keys set to verify ID Token/JWT
  +-- user-info-uri       -> endpoint to fetch user info when applicable
  +-- user-name-attribute -> identifying claim from UserInfo, usually "sub"
```

**The issuer does not necessarily match the authorization URI.** For example, the issuer might be `https://login.example.com/realms/acme` while the authorization URI is `https://login.example.com/realms/acme/protocol/openid-connect/auth`.

One provider can serve **multiple** registrations: an admin app, a customer portal app, or clients with different redirects/scopes. When you write `registration.portal.provider: enterprise-idp`, Spring Boot points that registration to the endpoints of provider `enterprise-idp`.

### 4.1 Spring Boot Maps YAML into ClientRegistration

Property prefixes:

```text
spring.security.oauth2.client
  registration
    <registrationId>
      provider
      client-id
      client-secret
      client-name
      client-authentication-method
      authorization-grant-type
      redirect-uri
      scope
  provider
    <providerId>
      issuer-uri
      authorization-uri
      token-uri
      jwk-set-uri
      user-info-uri
      user-info-authentication-method
      user-name-attribute
```

If `provider` is omitted and the registration ID matches a provider key or a default Spring Boot provider name, Boot can infer some settings. For custom providers, explicitly declare `provider: some-id`.

### 4.2 Configuring an IdP Supporting Discovery

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: enterprise-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-name: Corporate SSO
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          enterprise-idp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

This is a template for a **real IdP**: you must provide all three environment variables and register the matching callback at the IdP. With `issuer-uri`, Spring Security/Spring Boot can perform OIDC Provider Metadata/Authorization Server Metadata discovery and retrieve the authorization/token/JWKS/UserInfo endpoints.

**Operational note:** discovery may make an HTTP call to the IdP during bean/configuration creation. If the IdP lacks valid DNS/TLS or suffers an outage, the application may fail to start depending on version and configuration. Do not put a `.invalid` issuer into a real config and assume the network will not be called.

### 4.3 Explicit Endpoint Configuration

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: enterprise-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          enterprise-idp:
            authorization-uri: https://idp.example.com/oauth2/authorize
            token-uri: https://idp.example.com/oauth2/token
            jwk-set-uri: https://idp.example.com/oauth2/jwks
            user-info-uri: https://idp.example.com/userinfo
            user-name-attribute: sub
```

The endpoints above are **example addresses** and must be replaced according to your IdP's documentation. This approach avoids discovery when building the registration, but you are responsible for keeping endpoints up to date and verifying proper issuer/trust metadata. In production OIDC, ensure the ID Token is validated per standard; providing a few URLs is no excuse to skip `iss`, `aud`, or signature/nonce checks.

**Do not configure conflicting metadata/endpoints.** When using issuer discovery, prefer the trusted IdP metadata source; if overriding an endpoint, test token exchange, key rotation, and issuer validation thoroughly.

### 4.4 The ClientRegistrations Helper

`org.springframework.security.oauth2.client.registration.ClientRegistrations` provides helpers:

```java
ClientRegistration registration = ClientRegistrations
    .fromIssuerLocation("https://idp.example.com/realms/acme")
    .registrationId("corporate")
    .clientId(System.getenv("OIDC_CLIENT_ID"))
    .clientSecret(System.getenv("OIDC_CLIENT_SECRET"))
    .build();
```

This is an **illustrative snippet needing imports and a real IdP**, not part of the offline project in section 9. `fromIssuerLocation` uses network metadata discovery and is not an API you should call per HTTP request on the Netty event loop. `fromOidcIssuerLocation` is the variant that prefers OIDC Provider Configuration.

**SSRF warning:** `issuer` URIs must come from trusted configuration/allowlists; never construct a URI from a query/header supplied by an Internet client and pass it to `fromIssuerLocation`. In a multi-tenant system, map tenants to issuers from a trusted database with validation and strict configuration permissions.

## 5. ReactiveClientRegistrationRepository

In Spring Security WebFlux:

```java
package org.springframework.security.oauth2.client.registration;

public interface ReactiveClientRegistrationRepository {
    Mono<ClientRegistration> findByRegistrationId(String registrationId);
}
```

This is a **condensed signature for explanation**; the interface already exists in Spring Security, so do not create a new file with the same name.

- `findByRegistrationId("corporate")` emits the OAuth2/OIDC client configuration.
- The return type is `Mono<ClientRegistration>`, fitting WebFlux.
- With `InMemoryReactiveClientRegistrationRepository`, an unconfigured ID typically produces an **empty-completing** publisher rather than falling back to another client.
- The repository holds client *configuration*, not user sessions, OAuth2 Authorization Codes, or issued access/refresh tokens.

### 5.1 WebFlux vs. Servlet

| Topic | Reactive/WebFlux | Servlet/MVC |
|---|---|---|
| Client registrations | `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` |
| Lookup | `Mono<ClientRegistration>` | Direct `ClientRegistration` return |
| In-memory repository | `InMemoryReactiveClientRegistrationRepository` | `InMemoryClientRegistrationRepository` |
| Security DSL | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Authentication context | Reactor Context and reactive persistence | Servlet SecurityContextHolder/filter |
| Request/response | `ServerWebExchange`/WebFilter | Servlet API |

**Do not** import `InMemoryClientRegistrationRepository` into a reactive security config and expect `oauth2Login` to turn reactive automatically. The names look similar, but they are two different APIs.

### 5.2 Spring Boot Auto-Creates the Bean

With the `spring-boot-starter-oauth2-client` dependency and valid `spring.security.oauth2.client.registration.*` properties, Boot auto-configuration in a reactive app creates a `ReactiveClientRegistrationRepository` (typically `InMemoryReactiveClientRegistrationRepository`) from the bound `ClientRegistration` properties.

If you declare your own repository bean manually, auto-configuration may back off; **do not expect the two client lists to merge automatically**. Choose one mechanism to source clients and test the actual bean.

### 5.3 InMemoryReactiveClientRegistrationRepository and Iterable

`InMemoryReactiveClientRegistrationRepository` also implements `Iterable<ClientRegistration>`. This is useful because the default `/login` page generated by `LoginPageGeneratingWebFilter` can list provider links, for example:

```html
<a href="/oauth2/authorization/corporate">Corporate SSO</a>
```

A custom `ReactiveClientRegistrationRepository` that **only** implements `findByRegistrationId` does not automatically implement `Iterable`; if you need the auto-generated login page to list clients, satisfy `Iterable` or build a safe custom login page.

### 5.4 Reading the Repository in Code

```java
public Mono<String> displayName(String id) {
    return registrations.findByRegistrationId(id)
        .map(ClientRegistration::getClientName)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Unknown registration")));
}
```

This is an illustrative method missing its class/imports/field. In WebFlux, never call `block()` from a request handler to fetch configuration. If a custom repository calls synchronous JDBC/JPA, enforce a bounded `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with timeouts, or use a reactive backend.

## 6. Repositories That Look Similar but Have Different Responsibilities

| Component | What Does It Store/Retrieve? | Is It ClientRegistration? |
|---|---|---|
| `ReactiveClientRegistrationRepository` | List of client and provider configurations | **Yes** |
| `ReactiveOAuth2AuthorizedClientService` | `OAuth2AuthorizedClient` with principal and issued tokens | No |
| `ServerOAuth2AuthorizedClientRepository` | Authorized client in the context of `ServerWebExchange`/principal | No |
| `ServerSecurityContextRepository` | SecurityContext/Authentication, possibly via WebSession | No |
| `ServerAuthorizationRequestRepository` | OAuth2 authorization request/state for callbacks, per flow mechanism | No |
| `ReactiveJwtDecoder` | Validates JWTs when the protocol requires | No |

**`ClientRegistration` does not mean an access token has been received.** `OAuth2AuthorizedClient` appears only after an appropriate flow; it is tied to a registration and principal, and holds sensitive tokens with its own storage/revocation lifecycle.

Never expose `ReactiveOAuth2AuthorizedClientService` or token contents in debug JSON. Those objects can hold access/refresh tokens or credentials granting resource access.

## 7. Default OAuth2/OIDC Login Endpoints

| URL | Role |
|---|---|
| `GET /login` | Login page generated by Spring Security when configured appropriately |
| `GET /oauth2/authorization/{registrationId}` | Initiates the authorization request to the IdP |
| `GET /login/oauth2/code/{registrationId}` | Callback receiving `code` and `state` from the IdP |
| `provider.authorization-uri` | IdP endpoint for browser login/consent |
| `provider.token-uri` | Backend exchanges the code to obtain tokens |
| `provider.jwk-set-uri` | JWKS for verifying token signatures |
| `provider.user-info-uri` | UserInfo claims when used |

### 7.1 Login Initiation Flow

1. User visits a protected route or clicks `/oauth2/authorization/corporate`.
2. Spring looks up `ClientRegistration` by `registrationId` from the reactive repository.
3. Constructs an authorization request with `client_id`, `response_type=code`, `redirect_uri`, `scope`, and an unpredictable `state` value.
4. For OIDC, includes `nonce`; for PKCE, includes `code_challenge` per client settings/flow.
5. Correlation data (`state`, metadata to match) is stored via the repository mechanism, typically requiring WebSession.
6. The browser receives an HTTP 302 to the IdP's authorization endpoint.

**Never send `client_secret` in the authorization URL.** The confidential client secret is used at the token endpoint, not as a URL parameter that could be logged by the browser.

### 7.2 Callback and Token Exchange

1. IdP redirects the browser back to `/login/oauth2/code/corporate?code=...&state=...`.
2. Spring Security compares `state` against the stored authorization request; mismatched state must be rejected.
3. Spring sends the code/token request to the token endpoint with proper client authentication, plus the PKCE verifier if the flow uses it.
4. For OIDC: validates ID Token signature/JWKS, `iss`, `aud`, lifetime, nonce, and protocol conditions; may read UserInfo depending on provider/scopes.
5. Creates an Authentication from the verified principal, saves SecurityContext/session per configuration, and redirects the user back into the app.

**Do not write a manual callback controller that logs users in just because `code` is present.** State and tokens must be validated per protocol; Spring Security provides this flow handling.

### 7.3 state, nonce, and PKCE Are Different

- **state**: binds the authorization response to the initiated request, helping prevent callback/login CSRF.
- **nonce**: especially important in OIDC to bind the ID Token to the authentication request and prevent replay.
- **PKCE**: sends `code_challenge` on the authorization request and `code_verifier` when exchanging the code, preventing certain code interception attacks. Public clients especially need PKCE; confidential clients can also use it where supported by the provider.
- **HTTP CSRF token**: used with forms/cookies to protect the application's unsafe methods. `state` does not replace all CSRF tokens in the application.

In OAuth2 Login configuration, `client_authentication_method=client_secret_basic` specifies **how the application authenticates to the IdP**, not end-user HTTP Basic login to the portal.

## 8. The Role of `openid` and OIDC Claims

`scope: [openid, profile, email]` expresses the intent to log in with OIDC and request additional profile/email scopes. The provider may return claims depending on consent and policy.

- `openid`: distinguishes OIDC Login from plain OAuth2 Login in Spring Security.
- `sub` (subject): an end-user identifier scoped to the issuer; usually combine **issuer + subject** to map to an internal account.
- `email` and `email_verified`: do not infer from a raw email that the user belongs to a specific tenant.
- `groups` or role claims: trustworthy only after verifying the token/issuer and mapping via an explicit policy.
- `id_token`: intended for the client to authenticate the end-user; **not synonymous with an access token accepted by another API**.

In WebFlux, you can obtain `Principal` or `OidcUser` after login. Example OIDC method snippet:

```java
@GetMapping("/me/claims")
public Mono<String> claims(
        @AuthenticationPrincipal OidcUser user) {
    if (user == null) {
        return Mono.error(new ResponseStatusException(
            HttpStatus.UNAUTHORIZED));
    }
    return Mono.just(user.getSubject());
}
```

This is a **code snippet** needing imports/route security, not a complete component. Never dump all claims/ID tokens for debugging on a public endpoint; return only needed fields with valid access permissions.

## 9. Spring Boot 3.3/Java 17+ Demo: Repository Auto-Created from YAML

This lesson uses a **hypothetical** provider with host `idp.example.invalid`, with no live IdP. This lets the project **boot, render the login page, and generate the authorization redirect** without network discovery at startup. **Full login via callback cannot succeed** until replaced with a real IdP where the client is registered.

### 9.1 Structure

```text
reactive-oidc-registration/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/oidc/OidcApplication.java
  src/main/java/example/oidc/SecurityConfiguration.java
  src/main/java/example/oidc/ProfileController.java
  src/test/java/example/oidc/OidcRegistrationTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'reactive-oidc-registration'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.oidc'
version = '1.0.0'

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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add Servlet's `spring-boot-starter-web`. The OAuth2 client Boot starter is required to provide the `ReactiveClientRegistrationRepository` bean in WebFlux. `reactor-test` provides `StepVerifier`; the remaining tests use `WebTestClient`.

### 9.2 application.yml

**src/main/resources/application.yml**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training-idp
            client-id: training-web-demo
            client-secret: training-placeholder-not-a-secret
            client-name: Training Identity Provider
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          training-idp:
            authorization-uri: https://idp.example.invalid/oauth2/authorize
            token-uri: https://idp.example.invalid/oauth2/token
            jwk-set-uri: https://idp.example.invalid/oauth2/jwks
            user-info-uri: https://idp.example.invalid/userinfo
            user-name-attribute: sub
```

- `training` is the `registrationId` used in URL `/oauth2/authorization/training`.
- `training-idp` is the `providerId`.
- `training-web-demo` is a dummy client ID.
- `training-placeholder-not-a-secret` is strictly a **placeholder, not a credential**; for local demo use only.
- Explicit endpoints avoid discovery at startup. With no real IdP at `.invalid`, callback/token exchange **cannot** complete.
- When moving to a real IdP, replace with real issuer/endpoints, client ID/secret managed by a secret manager, registered redirect URI, and HTTPS.

### 9.3 Application

**src/main/java/example/oidc/OidcApplication.java**

```java
package example.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcApplication.class, args);
    }
}
```

### 9.4 SecurityConfiguration

**src/main/java/example/oidc/SecurityConfiguration.java**

```java
package example.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

In this demo, **do not manually declare a `ReactiveClientRegistrationRepository` bean**: Spring Boot creates it from `application.yml`. Adding a bean of the same type just to “make sure there is a repository” can cause auto-configuration to back off, resulting in the `training` registration not being loaded as expected.

`oauth2Login(Customizer.withDefaults())` enables reactive login handling. `anyExchange().authenticated()` protects all URLs except `/public`. WebFilters managed by Spring Security are allowed to handle `/login`, initiate authorization requests, and handle callbacks; you **do not need to write a callback controller**.

Default CSRF remains enabled; the demo only exposes GET. When adding POST/PUT/PATCH/DELETE in a session-cookie app, apply an appropriate CSRF policy rather than disabling it to fix 403 errors.

### 9.5 ProfileController

**src/main/java/example/oidc/ProfileController.java**

```java
package example.oidc;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    @GetMapping(value = "/public",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/private/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> currentUser(Principal principal) {
        return Mono.just("signed in: " + principal.getName());
    }
}
```

The `/private/me` route is callable only after valid authentication. In OIDC login, `Principal.getName()` may be the subject or a configured mapped name; **do not assume it is an internal email/username**. Never use this string directly to determine record ownership without proper identity mapping.

### 9.6 Running with Gradle and curl

```bash
gradle bootRun

# No IdP required:
curl -i http://localhost:8080/public

# Not logged in: inspect redirect
curl -i -H "Accept: text/html" http://localhost:8080/private/me

# Default login page
curl -i -H "Accept: text/html" http://localhost:8080/login

# Start authorization flow, inspect Location only, do not follow
curl -i http://localhost:8080/oauth2/authorization/training
```

If an appropriate Gradle Wrapper is present: `./gradlew bootRun`, or on Windows `gradlew.bat bootRun`. In PowerShell, `curl` may be an alias; use `curl.exe` when needed. Do not use `curl -L` when inspecting 302s because auto-following hides the initial redirect status.

Expected results:

| Request | Key Result |
|---|---|
| `GET /public` | 200, body `public` |
| `GET /private/me` unauthenticated | 3xx redirect initiating login |
| `GET /login` | 200, HTML page with link to `/oauth2/authorization/training` |
| `GET /oauth2/authorization/training` | 302; `Location` starts with `https://idp.example.invalid/oauth2/authorize?...` |
| Browser follows redirect to dummy IdP | Cannot complete login because the provider does not exist |
| After replacing with a real IdP and logging in | Can call `GET /private/me` and receive principal name |

Session/state cookies correlate the authorization request with the callback. **Do not print state, authorization codes, access tokens, session cookies, or client secrets to logs** just to verify the flow.

## 10. Testing with WebTestClient and StepVerifier Without a Real IdP

**src/test/java/example/oidc/OidcRegistrationTest.java**

```java
package example.oidc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OidcRegistrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Test
    void bootCreatesReactiveRegistration() {
        StepVerifier.create(registrations.findByRegistrationId("training"))
            .assertNext(reg -> {
                assertEquals("training", reg.getRegistrationId());
                assertEquals("training-web-demo", reg.getClientId());
                assertEquals("Training Identity Provider",
                    reg.getClientName());
                assertEquals(
                    "https://idp.example.invalid/oauth2/authorize",
                    reg.getProviderDetails().getAuthorizationUri());
                assertTrue(reg.getScopes().contains("openid"));
            })
            .verifyComplete();
    }

    @Test
    void unknownRegistrationIsEmpty() {
        StepVerifier.create(
            registrations.findByRegistrationId("unknown"))
            .verifyComplete();
    }

    @Test
    void publicRouteIsAvailable() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedRouteBeginsLogin() {
        client.get().uri("/private/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void generatedLoginPageOffersRegistrationLink() {
        client.get().uri("/login")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .consumeWith(result -> {
                assertNotNull(result.getResponseBody());
                assertTrue(result.getResponseBody()
                    .contains("/oauth2/authorization/training"));
            });
    }

    @Test
    void authorizationRequestRedirectsToConfiguredIdp() {
        var result = client.get()
            .uri("/oauth2/authorization/training")
            .exchange()
            .expectStatus().isFound()
            .returnResult(Void.class);

        String location = result.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI target = URI.create(location);
        assertEquals("https", target.getScheme());
        assertEquals("idp.example.invalid", target.getHost());
        assertEquals("/oauth2/authorize", target.getPath());
        assertTrue(location.contains("client_id=training-web-demo"));
        assertTrue(location.contains("response_type=code"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("redirect_uri="));
    }
}
```

**6 test methods** verify: the YAML-backed bean, unknown ID, public route, unauthenticated redirect, login page link, and authorization request URL. `StepVerifier` confirms that `Mono<ClientRegistration>` emits/completes properly.

Run:

```bash
gradle test
```

**Testing limitations:** these tests **do not verify** token exchange, JWKS, ID Token validation, UserInfo, or the full callback. To verify those steps, you need a real IdP or an OIDC-compliant mock IdP with an authorization endpoint, token endpoint, JWKS, and properly signed ID Tokens. Testing only the redirect phase does not prove the user has been authenticated.

**No live build was executed** in this Knowledge lesson; statuses and tests reflect expectations from reviewing the code and APIs. When running against different dependency versions, inspect actual stack traces, security chains, and HTTP behavior rather than assuming 302/200 are identical across every configuration.

## 11. Creating the Repository Bean Manually in Java

Instead of Boot property binding, you can declare a bean:

```java
package example.manual;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;

@Configuration(proxyBeanMethods = false)
public class ManualRegistrationConfiguration {

    @Bean
    ReactiveClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration client =
            ClientRegistration.withRegistrationId("corporate")
                .clientId(requiredEnv("OIDC_CLIENT_ID"))
                .clientSecret(requiredEnv("OIDC_CLIENT_SECRET"))
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                    "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .authorizationUri(
                    "https://login.example.com/oauth2/authorize")
                .tokenUri("https://login.example.com/oauth2/token")
                .jwkSetUri("https://login.example.com/oauth2/jwks")
                .userInfoUri("https://login.example.com/userinfo")
                .userNameAttributeName(IdTokenClaimNames.SUB)
                .clientName("Corporate SSO")
                .build();

        return new InMemoryReactiveClientRegistrationRepository(client);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing environment variable: " + key);
        }
        return value;
    }
}
```

**This is an alternative approach**; do not paste this class into the section 9 project alongside YAML registrations. If choosing a manual bean:

- Use real endpoints provided by the IdP; do not use dummy URLs.
- Configure secrets via environment variables/a secret manager.
- Verify issuer/JWK/ID Token validation per protocol when configuring endpoints manually.
- Pass multiple `ClientRegistration` instances to the in-memory repository constructor if there are multiple clients.
- Ensure the class is component-scanned and `SecurityWebFilterChain` includes `oauth2Login`.

The example above uses Java 17+ and still requires a real IdP for final login. For environments using only a static repo, this clearly shows the Builder API. `ClientRegistrations.fromIssuerLocation(...)` is another option when you want to fetch provider details via metadata discovery.

## 12. Multiple Registrations, One Provider or Multiple IdPs

Example of two clients sharing an issuer with two different client IDs:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: corporate
            client-id: ${PORTAL_CLIENT_ID}
            client-secret: ${PORTAL_CLIENT_SECRET}
            scope: [openid, profile, email]
          reporting:
            provider: corporate
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            scope: [openid, profile]
        provider:
          corporate:
            issuer-uri: ${CORPORATE_ISSUER_URI}
```

Corresponding login links:

```text
/oauth2/authorization/portal
/oauth2/authorization/reporting
```

The same provider can grant different scopes per client; each callback must be registered at the IdP. For two different IdPs, use two separate provider blocks. Never create a registration from a user-entered issuer URL during login handling.

### Provider Defaults

Spring Boot provides built-in defaults for several common providers, such as Google, GitHub, Facebook, and Okta. Example:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: [openid, profile, email]
```

Provider defaults only supply endpoint settings; you must still register the client and redirect URI with the provider. Do not assume every custom IdP has built-in defaults.

## 13. Redirect URI, Callback, and Reverse Proxy

A commonly used `redirect-uri`:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

Locally, when a user visits `http://localhost:8080`, the callback becomes:

```text
http://localhost:8080/login/oauth2/code/training
```

In production, behind TLS termination:

```text
https://portal.example.com/login/oauth2/code/corporate
```

This URI must **match the IdP's allowlist**, including scheme/host/path/port per IdP policy. Never let a client supply a redirect URI from an unverified query param and never use uncontrolled wildcards.

### Reverse Proxy

```text
Browser --HTTPS--> Ingress/Load Balancer --HTTP--> WebFlux Pod
                       |
                Forwarded / X-Forwarded-Proto
```

If WebFlux only sees internal HTTP, the `{baseUrl}` template can construct the wrong scheme/host, causing `redirect_uri_mismatch`. When behind a trusted proxy, Spring Boot supports:

```yaml
server:
  forward-headers-strategy: framework
```

**This is a conditional production setting**, not a license to “trust” arbitrary `X-Forwarded-Host` headers from the Internet. The reverse proxy must strip/overwrite user-supplied forwarded headers and restrict trusted hops; otherwise attackers can influence redirect URLs.

When customizing the callback path, keep **registration.redirect-uri**, WebFlux's OAuth2 Login redirection endpoint matcher, and the IdP-allowlisted URI synchronized. Do not use Servlet `HttpSecurity` configuration to adjust callbacks in `ServerHttpSecurity`.

## 14. Security State and Sessions

Authorization Code login generally needs to store `state`/authorization requests until the callback arrives; in WebFlux, WebSession and its related repository are typically used. Key points:

- The `SESSION` cookie is a session reference token; it does not contain the client secret.
- If multiple pods use separate in-memory session stores, the callback might hit a different pod and lose `state`; use a shared WebSession store or an appropriate architecture.
- `state`/`nonce`/PKCE do not replace CSRF protection for POSTs in a cookie-session app.
- Successful login does not automatically make a user an ADMIN; map issuer+subject to an account/tenant.
- Local logout may not log out of the IdP; consider OIDC logout if product requirements call for it.
- Never place access/refresh tokens in URLs, browser localStorage, or logs.
- Protect cookies with HTTPS/Secure/HttpOnly/SameSite per your threat model, and rotate session IDs on privilege elevation per policy/framework.

## 15. Security Considerations When Using a Custom Repository

A custom `ReactiveClientRegistrationRepository` can load metadata from a database or config service:

```java
public Mono<ClientRegistration> findByRegistrationId(String id) {
    return configurationService.findTrustedRegistration(id)
        .map(this::mapToClientRegistration);
}
```

This is pseudocode: `configurationService` must be a trusted backend and `mapToClientRegistration` must validate fields. **Never take `issuer-uri` from an untrusted request** and run discovery immediately, as that can lead to SSRF or credential leakage.

Constraints to enforce:

1. Who can create/edit registrations? Only authorized admins; audit changes.
2. Are provider URIs on an allowlist and using valid TLS?
3. Are secrets fetched via KMS/vault, and never stored in plaintext in logs/public caches?
4. Are cache/timeout/TTL aligned with token/key rotations?
5. Is configuration consistent between authorization request and callback?
6. Non-existent IDs or backend failures must fail closed, never falling back to a random provider.
7. If lookup uses synchronous JDBC/JPA, enforce a blocking boundary with bounded scheduler/concurrency; never block the event loop.
8. If the default login page needs to list providers, ensure the repository implements `Iterable` or use a securely permissioned custom login UI.

`InMemoryReactiveClientRegistrationRepository` handles static registrations well, but it is not a multi-tenant authorization system, credential vault, or authorized-client token store.

## 16. Diagnosing Common Errors

| Symptom | Common Cause | Check/Fix |
|---|---|---|
| Missing `ReactiveClientRegistrationRepository` bean | Missing OAuth2 client starter or invalid YAML | Check classpath, Boot binder, reactive type |
| Servlet `ClientRegistrationRepository` bean | Confusing MVC with WebFlux | Use reactive repository and Security chain |
| `/login` page has no IdP links | Custom repo lacks `Iterable`, custom login page, OAuth2 Login not enabled | Check beans/chain |
| `/oauth2/authorization/corporate` does not redirect | Wrong registrationId or chain/matcher | Check `repository.findByRegistrationId` |
| Redirects to wrong authorization URL | Wrong `provider` ID or provider endpoints | Test `getProviderDetails().getAuthorizationUri()` |
| App fails to start with `issuer-uri` | Discovery network/TLS/DNS failure | Check issuer metadata and trust |
| IdP reports `invalid_client` | Mismatched Client ID/secret/method | Verify with IdP; never log secret |
| IdP reports `redirect_uri_mismatch` | Wrong callback, scheme, or proxy headers | Compare IdP allowlist URL and actual `Location` |
| Callback reports `invalid_state` | Session/cookie/state lost or tampered | Check WebSession/IdP return/correlation |
| ID Token rejected | Bad JWKS/iss/aud/nonce/clock | Verify protocol; never skip signature checks |
| Still 403 after login | Missing role/tenant permission | Map issuer+sub, verify permissions |
| No OIDC principal | Missing `openid` scope or IdP does not support OIDC | Check registration scopes and response |
| Trying to call external API without access token | Confusing registration metadata with authorized client | Use `OAuth2AuthorizedClient` and `oauth2Client` |
| Stateless app only enables Resource Server | OAuth2 Login not configured | Use proper client registration and `oauth2Login` |
| Secret leaked during debugging | Logging or JSON-serializing registration/token | Redact, rotate secret, restrict logs |

Some errors appear **only after** a successful redirect; never conclude “Spring Security OAuth2 works completely” merely because the browser got a 302 to the IdP.

## 17. Integration Test Matrix with a Real or Mock IdP

The tests in section 10 verify **configuration and login initiation**. For security-critical login, also test:

1. Authorization redirect has `response_type=code`, `client_id`, scopes, `state`, and the proper callback.
2. Callback returning a valid code exchanges it at the token endpoint and receives a protocol-compliant response.
3. ID Token signed by a trusted issuer's JWKS with valid `iss`/`aud`/nonce is accepted.
4. Tokens with invalid signature, issuer, audience, nonce, or lifetime are all rejected.
5. Callbacks with missing/invalid `state`, expired/reused codes, or lost session cookies fail closed.
6. Multiple registrations use their exact provider/clientID, preventing issuer/client mix-ups.
7. External HTTPS/proxy callbacks have the right scheme, hostname, and port.
8. JWKS key rotation does not accept arbitrary keys/algorithms; cache refresh is bounded.
9. Logged-in user without admin/tenant roles is still denied on admin/cross-tenant routes.
10. Logout, session expiry, multiple tabs/pods, and IdP outages do not leak tokens or bypass login.
11. Secret rotation fails/recovers cleanly without leaking secrets in HTTP responses/logs.
12. Verify PKCE flow if required by policy; `code_verifier` is never exposed in browser responses.
13. Verify whether `openid`/`profile`/`email` scopes are actually fulfilled by the IdP or may be missing.
14. UserInfo data is fetched safely with the access token when needed; never trust unverified email/roles.
15. Security upgrades do not silently alter endpoint matchers, beans, or session persistence.

You can use a full mock OIDC IdP with an authorization endpoint, token endpoint, JWKS, and test-key-signed JWTs; **never fake a `?code=abc` query param and claim you tested validation**.

## 18. Implementation Checklist

1. Pick the right responsibility: browser OAuth2/OIDC login, outbound OAuth2 client, or JWT resource server.
2. Register the client at the IdP, obtain clientId/secret/method, and set the callback URI allowlist.
3. Keep the three names distinct: `registrationId`, `providerId`, `clientId`; document the YAML mapping clearly.
4. Configure `spring.security.oauth2.client.registration.*` and `provider.*`, preferring discovery if supported by the IdP.
5. Store client secrets in environment variables/a secret manager; never hardcode production secrets.
6. Use `spring-boot-starter-webflux` + `spring-boot-starter-oauth2-client`; verify the reactive repository bean.
7. Enable `oauth2Login(Customizer.withDefaults())` or customize via WebFlux's `ServerHttpSecurity`.
8. Verify the `/oauth2/authorization/{registrationId}` link and `/login/oauth2/code/{registrationId}` callback.
9. Verify external URIs behind HTTPS proxies; never trust spoofed forwarded headers.
10. Keep state, nonce, PKCE, and token validation intact; never remove callback protections.
11. Protect sessions, CSRF, cookies, and OAuth2 authorized-client storage.
12. Map issuer+subject to accounts/tenants and enforce data permissions.
13. Write tests for repository `Mono`, unknown registration, redirect URLs, and end-to-end mock/real IdP flows.
14. For multi-tenant setups, allow only approved providers; prevent SSRF from dynamic issuers.
15. Verify scopes/claims and behavior during provider outages, secret rotation, and JWKS rotation.
16. Upgrade Spring Security when security advisories change; never keep old demo versions in production.

## 19. Practice Exercises

1. Distinguish `registrationId`, `providerId`, and `clientId` in the demo YAML. If one ID changes, which URLs/beans are affected?
2. Use `StepVerifier` to read the `training` registration, then read `unknown`; describe the emitted vs. empty `Mono`.
3. Call `/oauth2/authorization/training` with `curl` **without -L** and inspect `Location`. Why is `clientSecret` absent from the query?
4. Add another registration pointing to the same `training-idp` with different scopes and clientId. Write a test ensuring the two configs are not mixed up.
5. Declare an `InMemoryReactiveClientRegistrationRepository` bean instead of Boot properties; verify that Boot auto-configuration backs off.
6. Replace the dummy endpoints with a real staging IdP's `issuer-uri`; inspect metadata discovery and the key/JWKS endpoint.
7. Configure a non-default callback URL. List every place that must stay synchronized across Spring Security and the IdP.
8. Create a mock callback with invalid `state`, invalid `iss`, invalid `aud`, and invalid nonce; prove no authenticated user is created.
9. Run the app behind an HTTPS reverse proxy; compare the request's `redirect_uri` against the IdP's allowlist.
10. Compare `oauth2Login` with `oauth2Client` and `oauth2ResourceServer`. For an app that only validates inbound JWTs, is a `ClientRegistration` needed?
11. Design a custom tenant-aware repository: trusted tenant mapping, issuer allowlist, timeouts, caching, and secret rotation.
12. After OIDC login, map `issuer+sub` to an internal user ID and verify that a route belonging to another tenant is denied.
13. Check whether the default login page still lists providers when a custom repository does not implement `Iterable`; fix it with a safe custom login chooser.
14. Explain why running metadata discovery against an issuer from user input can cause SSRF.
15. Write a runbook for IdP outages: startup failure, existing sessions, retry/backoff, and token/secret security.

## Summary

**`ClientRegistration`** represents a registered OAuth2/OIDC client, including client credentials, Authorization Code grant, scopes, redirect URI, and provider endpoints. Spring Boot's **`provider`** defines the issuer/discovery or authorization/token/JWKS/UserInfo endpoints. **`ReactiveClientRegistrationRepository`** is the WebFlux API returning `Mono<ClientRegistration>` by `registrationId`; Spring Boot can build `InMemoryReactiveClientRegistrationRepository` from YAML, or the application can supply the bean manually. Together with `ServerHttpSecurity.oauth2Login(...)`, these components initiate the Authorization Code flow and handle callbacks **without granting authorization by themselves**: you still need a real IdP, state/nonce/token validation, secure sessions, and business authorization.

## Official Documentation

1. Spring Security — Reactive OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
2. Spring Security — Reactive OAuth2 Login Advanced Configuration, login page/callback: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
3. Spring Security — Reactive OAuth2 Client Core Interfaces: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
4. Spring Security 6.3.8 Javadoc — InMemoryReactiveClientRegistrationRepository: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/oauth2/client/registration/InMemoryReactiveClientRegistrationRepository.html
5. Spring Security — WebFlux OAuth2 Login and OAuth2 Client: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
6. Spring Boot 3.3 — OAuth2 Client properties, WebFlux Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
7. Spring Security 6.3.8 Javadoc — ClientRegistration: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/oauth2/client/registration/ClientRegistration.html
8. RFC 6749 — OAuth2 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
9. RFC 7636 — Proof Key for Code Exchange: https://www.rfc-editor.org/rfc/rfc7636
10. OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
