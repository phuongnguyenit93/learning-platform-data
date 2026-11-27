# 34.10. Integrating a Self-Hosted Provider in a Local Environment

## 1. Practical Scenario

In typical OAuth 2.0/OIDC Client examples, the application usually logs in through an existing Identity Provider. In this practical lab, we **deploy and operate a local OpenID Provider (OP) ourselves**, then configure a **Spring Security OAuth2/OIDC Client** application to execute the Authorization Code Flow with that provider.

Two separate Spring Boot applications:

~~~text
Browser
  |
  | GET http://127.0.0.1:8080
  v
Portal / Relying Party (:8080)
  |  Spring Security oauth2Login()
  |  ClientRegistration(local-idp)
  |
  | 302 /oauth2/authorize?...state...nonce...PKCE...
  v
Local OpenID Provider (:9000)
  |  Spring Authorization Server
  |  Login form + consent
  |  Authorization Code, Token, ID Token, JWK Set
  |
  | 302 callback with code and state
  v
Portal /login/oauth2/code/local-idp
  |  POST /oauth2/token from backend
  |  Verify ID Token iss/aud/exp/signature/nonce
  v
Portal /me -> authenticated OidcUser
~~~

A **self-hosted provider** here means an application under our control configured with **Spring Authorization Server**, rather than writing the entire OAuth 2.0/OIDC protocol manually using a few REST controllers. The framework provides customizable filters, grant handlers, and token services, reducing the risk of overlooking client authentication, redirect URI, PKCE, state, token signature, and consent.

> Stack: Java 17+, Spring Boot 3.x, Spring Security 6.x, a compatible Spring Authorization Server line, Spring MVC/Servlet. The snippets are based on Spring Authorization Server 1.x APIs suitable for Spring Security 6; verify the exact project BOM/version if using Spring Security 7 or a newer Authorization Server line. All credentials, keys, hosts, and URLs in this lab are for the local environment only.

## 2. Learning Objectives

Upon completing this lab, learners can:

1. Distinguish between an OpenID Provider, Authorization Server, OAuth2 Client, and Resource Server.
2. Run a local OP at `http://127.0.0.1:9000`.
3. Publish the OIDC discovery document and public JWKS.
4. Register a confidential client with `authorization_code`, `refresh_token`, scopes, and a PKCE policy.
5. Create demo users and authorization consent.
6. Sign ID Token JWTs with an RSA test key and understand issuer/audience.
7. Connect the MVC Portal at `http://127.0.0.1:8080` using `issuer-uri`.
8. Use `oauth2Login()`, `OAuth2AuthorizationRequestCustomizers.withPkce()`, and `OidcUser`.
9. Observe state, nonce, callback, session cookie, code exchange, and ID Token validation.
10. Test failure cases for wrong issuer/client ID/secret, redirect URI, PKCE, state, and signature.
11. Distinguish between ID Token, access token, UserInfo, authorized-client storage, and logout.
12. Understand the limitations of an in-memory demo and the changes required before production.

## 3. Roles in the Protocol

| Role | In the lab | Responsibility |
|---|---|---|
| Resource Owner | User `alice` | Authenticates and grants consent |
| Authorization Server | `local-provider` | Issues authorization codes and access tokens |
| OpenID Provider | Also `local-provider` | Issues ID Tokens, UserInfo, and OIDC metadata |
| OAuth2 Client / Relying Party | `portal-client` | Initiates login and validates ID Tokens |
| Resource Server | Optional `orders-api` | Accepts Bearer access tokens and protects APIs |
| RegisteredClient | Record at the OP with `clientId=portal-client` | Client authentication, scopes, redirects |
| ClientRegistration | Record at the Portal with `registrationId=local-idp` | Local metadata of the OAuth2 Client |
| OAuth2AuthorizedClient | Authorization/token for registration + principal | Token lifecycle |

Do not confuse:

~~~text
Provider RegisteredClient.clientId       = portal-client
Portal ClientRegistration.registrationId = local-idp
~~~

`client_id` appears in the OAuth protocol, whereas `registrationId` is Spring Security's internal key for selecting a client configuration.

## 4. Overview of Authorization Code Flow with OIDC and PKCE

~~~mermaid
sequenceDiagram
    actor B as Browser
    participant RP as Portal :8080
    participant OP as Local Provider :9000

    B->>RP: GET /oauth2/authorization/local-idp
    RP-->>B: 302 /oauth2/authorize (client_id, state, nonce, PKCE challenge)
    B->>OP: GET /oauth2/authorize
    OP-->>B: Login page
    B->>OP: Credentials / consent
    OP-->>B: 302 /login/oauth2/code/local-idp?code=...&state=...
    B->>RP: Callback with code/state + Portal session cookie
    RP->>OP: POST /oauth2/token (code, secret, PKCE verifier)
    OP-->>RP: access_token, id_token, optional refresh_token
    RP->>OP: GET /oauth2/jwks as needed
    OP-->>RP: Public RSA JWK
    RP->>RP: Validate ID Token issuer, audience, expiry, signature, nonce
    RP-->>B: Portal authenticated session, redirect /me
    B->>RP: GET /me
    RP-->>B: User summary
~~~

The browser does not receive the client secret; it only passes through top-level redirects. The Portal backend calls the token endpoint and decodes/validates the ID Token.

## 5. Project Structure and Addresses Used

~~~text
oidc-local-lab/
├── local-provider/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/example/provider/
│       │   ├── LocalProviderApplication.java
│       │   └── ProviderSecurityConfig.java
│       └── resources/application.yml
└── portal-client/
    ├── build.gradle.kts
    └── src/main/
        ├── java/com/example/portal/
        │   ├── PortalClientApplication.java
        │   ├── PortalSecurityConfig.java
        │   └── HomeController.java
        └── resources/application.yml
~~~

Use these addresses consistently:

~~~text
Provider issuer : http://127.0.0.1:9000
Portal URL      : http://127.0.0.1:8080
Portal callback : http://127.0.0.1:8080/login/oauth2/code/local-idp
~~~

**Do not mix `localhost` and `127.0.0.1`** across the provider issuer, browser URL, and `ClientRegistration`: the two hostnames may point to the same loopback interface, yet **they are not the same URI/cookie host/trust identity**.

### 5.1. Critical Note: Cookies Are Not Isolated by Port

Two Servlet applications sharing the same hostname on different ports can **overwrite each other's `JSESSIONID`**, because browser cookies are scoped by host/domain and path, **not by port**. Therefore:

~~~text
Provider cookie name: IDPSESSION
Portal cookie name:   PORTALSESSION
~~~

This solution lets the browser maintain **two independent sessions** when both apps use `127.0.0.1` and cookie Path `/`.

## 6. Required Tools

- JDK 17 or newer.
- Gradle/Maven and Spring Boot 3.x compatible with Spring Authorization Server.
- Two terminals, a browser, and `curl` or an HTTP client.
- Ports 9000 and 8080 available.
- No Docker, database, or public IdP needed for the minimal lab.

The snippets only show the necessary dependencies and code; when creating `build.gradle.kts`, use the plugin versions/BOM of an appropriate Spring Boot 3.x release instead of copying placeholder versions into a running build.

## 7. `local-provider`: Dependencies

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation(
        "org.springframework.boot:spring-boot-starter-oauth2-authorization-server"
    )
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Spring Authorization Server lets you implement an OP in a structured way. Starter artifacts and namespaces may change when upgrading major versions; consult the documentation for your project's BOM.

## 8. `local-provider`: `application.yml`

~~~yaml
server:
  port: 9000
  servlet:
    session:
      cookie:
        name: IDPSESSION
        http-only: true

logging:
  level:
    org.springframework.security: INFO
~~~

This is an HTTP **loopback lab**, not a production configuration. In production, use HTTPS, `Secure` cookies, proper signing-key management, and never log raw credentials or tokens.

## 9. `local-provider`: Spring Boot Application

~~~java
package com.example.provider;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocalProviderApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            LocalProviderApplication.class, args);
    }
}
~~~

## 10. `local-provider`: Two `SecurityFilterChain` Beans

File `ProviderSecurityConfig.java`:

~~~java
package com.example.provider;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation
    .web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
    .LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration
public class ProviderSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer
                .authorizationServer();

        http
            .securityMatcher(configurer.getEndpointsMatcher())
            .with(configurer, server -> server
                .oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(resource -> resource
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain formLoginChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

The remaining beans in the following sections are **added to the same `ProviderSecurityConfig`** or placed in a separate `@Configuration` class with proper component scanning; do not create duplicate beans with the same type/name.

### 10.1. OAuth2 Chain Comes First

`@Order(1)` handles the protocol endpoints owned by the configurer. `@Order(2)` acts as the fallback, serving the `/login` form login to authenticate the resource owner.

### 10.2. OIDC Must Be Enabled Explicitly

`.oidc(Customizer.withDefaults())` enables OIDC provider features such as discovery/UserInfo/logout depending on configuration/version. An OAuth Authorization Server without OIDC enabled does not automatically issue ID Tokens just because it has a JWT signing key.

### 10.3. Resource Server JWT Inside the OP Itself

OIDC UserInfo is a Bearer-protected endpoint. `.oauth2ResourceServer(...jwt())` on the provider chain enables access-token validation when the OP handles requests such as UserInfo.

### 10.4. The OP Matcher

`configurer.getEndpointsMatcher()` is the set of endpoints owned by the Authorization Server. Do not replace it with `securityMatcher("/api/**")`, which would leave `/oauth2/token`, discovery, or `/userinfo` outside the chain.

## 11. Registering a Confidential Client at the Provider

The Provider needs to know that the Portal is allowed to use OAuth2/OIDC:

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client
    .InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client
    .RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client
    .RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings
    .ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings
    .TokenSettings;

@Bean
RegisteredClientRepository registeredClients(PasswordEncoder encoder) {
    RegisteredClient portal = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("portal-client")
        .clientSecret(encoder.encode("portal-secret"))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
            AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri(
            "http://127.0.0.1:8080/login/oauth2/code/local-idp")
        .postLogoutRedirectUri("http://127.0.0.1:8080/")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope(OidcScopes.EMAIL)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
            .requireAuthorizationConsent(true)
            .requireProofKey(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .accessTokenTimeToLive(Duration.ofMinutes(5))
            .refreshTokenTimeToLive(Duration.ofMinutes(30))
            .reuseRefreshTokens(false)
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(portal);
}
~~~

| Property | Purpose |
|---|---|
| `clientId=portal-client` | Client identifier sent in the authorization request |
| `clientSecret` | Authenticates the Portal at the token endpoint |
| `client_secret_basic` | HTTP Basic authentication during token exchange |
| `authorization_code` | Server-side browser login |
| `refresh_token` | Allows refresh if the OP actually issues a refresh token |
| `redirectUri` | Callback allowlist |
| `openid` | Enables OIDC/ID Token |
| `orders.read` | Demo scope for the optional API |
| `requireAuthorizationConsent` | User consent mechanism |
| `requireProofKey` | Enforces PKCE |

### 11.1. PKCE on a Confidential Client

The Provider requires PKCE, so **the Portal must send `code_challenge` and `code_verifier`**. For confidential clients, do not assume a given Spring Security version enables PKCE automatically. We will configure `withPkce()` explicitly on the Portal side.

### 11.2. A Refresh Token Is Not Always Issued

Having the `refresh_token` grant on `RegisteredClient` does not guarantee the token endpoint always issues a refresh token; depending on policy, grant, and consent, the response may differ.

### 11.3. In-Memory Repository Is a Lab Limitation

After a restart, client records/consents/authorizations/token stores may change or be lost. Production requires persistent repositories and proper lifecycle management.

## 12. Test Users and `PasswordEncoder`

Add to `ProviderSecurityConfig`:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory
    .PasswordEncoderFactories;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("alice-pass"))
        .roles("USER")
        .build();
    UserDetails admin = User.withUsername("admin")
        .password(encoder.encode("admin-pass"))
        .roles("USER", "ADMIN")
        .build();
    return new InMemoryUserDetailsManager(alice, admin);
}
~~~

Demo credentials:

~~~text
alice / alice-pass
admin / admin-pass
~~~

**Never deploy these credentials to production, and never expose the provider port to a public network.**

### 12.1. Passwords Belong to the Provider, Not the Portal

The browser submits the username/password to the OP on port 9000. The Portal never needs to know Alice's password; it only uses the authorization code and OIDC ID Token response.

### 12.2. Roles at the Provider Do Not Automatically Become `ROLE_ADMIN` at the Portal

`UserDetailsService` serves form authentication at the OP. Role mapping at the Portal depends on the claims the OP actually issues and a verified mapping mechanism; never infer admin privileges from the username `admin`.

## 13. Fixed Issuer

~~~java
import org.springframework.security.oauth2.server.authorization.settings
    .AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("http://127.0.0.1:9000")
        .build();
}
~~~

The issuer is a trust identifier and must match exactly across discovery metadata, the ID Token `iss` claim, and the Portal's `ClientRegistration`. Do not switch back and forth between `http://localhost:9000` and `http://127.0.0.1:9000`.

**A production issuer must be a fixed/trusted HTTPS URL**, not derived arbitrarily from a browser's `Host` or `X-Forwarded-Host` header.

## 14. Signing ID Tokens with RSA and Publishing the JWK Set

The Provider needs an RSA keypair to sign JWTs. Register:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.UUID;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

@Bean
JWKSource<SecurityContext> jwkSource() throws Exception {
    KeyPairGenerator generator =
        KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    KeyPair pair = generator.generateKeyPair();

    RSAKey rsa = new RSAKey.Builder(
        (RSAPublicKey) pair.getPublic())
        .privateKey((RSAPrivateKey) pair.getPrivate())
        .keyID(UUID.randomUUID().toString())
        .build();

    JWKSet keys = new JWKSet(rsa);
    return (selector, context) -> selector.select(keys);
}
~~~

Spring Authorization Server's OIDC features typically require a `JwtDecoder`:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation
    .web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration
        .jwtDecoder(jwkSource);
}
~~~

### 14.1. Public JWKS Must Not Contain Private Keys

`/oauth2/jwks` publishes the public key used for signature verification. The private RSA key remains strictly on the provider side. If writing a public response manually, use `rsa.toPublicJWK()` instead of serializing the private key as well.

### 14.2. Why Use RSA 2048 in the Lab?

It is sufficient for observing JWT signing and verification in tests. Production requires key management, KMS/HSM where appropriate, key IDs, rotation, certificate/JWKS caching, and recovery procedures.

### 14.3. Keys Change After Restart

The lab generates a new key on every startup, so previously issued JWTs may fail verification after a restart. This behavior is **unsuitable for production**, where signing keys must be managed persistently and rotated with an overlap window.

## 15. Adding Claims to the ID Token (Optional)

Example customizer in `ProviderSecurityConfig`:

~~~java
import org.springframework.security.oauth2.core.oidc.endpoint
    .OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token
    .JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token
    .OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> tokenCustomizer() {
    return context -> {
        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            String username =
                context.getPrincipal().getName();
            context.getClaims()
                .claim("preferred_username", username)
                .claim("name", username)
                .claim("email", username + "@example.test");
        }
    };
}
~~~

This mapper is **for lab use only**. Never assume an email is verified, never emit `email_verified=true` without an actual verification process, and never turn an arbitrary claim into admin privileges.

### 15.1. ID Tokens and Access Tokens Have Different Claim Purposes

The ID Token is for the client to authenticate the user. The access token is for the Resource Server. If the access token needs audience/resource claims, create a separate policy/customizer for that token type; do not copy all ID Token claims into the access token.

### 15.2. UserInfo

OIDC UserInfo can return user claims according to scopes, consent, and configuration. If custom UserInfo mapping beyond defaults is needed, use Spring Authorization Server's extension points rather than bypassing access-token authentication.

## 16. Summary of Provider Beans

After assembling the snippets, `ProviderSecurityConfig` or equivalent `@Configuration` classes will contain:

~~~text
@Bean SecurityFilterChain authorizationServerChain(...)
@Bean SecurityFilterChain formLoginChain(...)
@Bean RegisteredClientRepository registeredClients(...)
@Bean PasswordEncoder passwordEncoder()
@Bean UserDetailsService users(...)
@Bean AuthorizationServerSettings authorizationServerSettings()
@Bean JWKSource<SecurityContext> jwkSource()
@Bean JwtDecoder jwtDecoder(...)
@Bean OAuth2TokenCustomizer<JwtEncodingContext> tokenCustomizer()
~~~

The method snippets in this guide are **not standalone classes to be duplicated**, but components to assemble into the configuration.

## 17. Starting `local-provider` and Checking Metadata

Linux/macOS terminal:

~~~bash
cd oidc-local-lab/local-provider
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
cd oidc-local-lab\local-provider
.\gradlew.bat bootRun
~~~

Once the application is listening on port 9000, check discovery:

~~~bash
curl -i http://127.0.0.1:9000/.well-known/openid-configuration
~~~

Expected partial response:

~~~json
{
  "issuer": "http://127.0.0.1:9000",
  "authorization_endpoint": "http://127.0.0.1:9000/oauth2/authorize",
  "token_endpoint": "http://127.0.0.1:9000/oauth2/token",
  "jwks_uri": "http://127.0.0.1:9000/oauth2/jwks"
}
~~~

This is an **excerpt**; the actual discovery document contains much more metadata such as grant types, algorithms, scopes, and UserInfo endpoints.

JWK Set:

~~~bash
curl -i http://127.0.0.1:9000/oauth2/jwks
~~~

Partial response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "<generated-key-id>",
      "n": "<public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Public JWKS must never expose RSA private parameters such as `d`, `p`, `q`.

### 17.1. If Discovery Returns 404

Check the OIDC configurer `.oidc()`, the Authorization Server filter chain/order, and version compatibility. Do not start the Portal until the Provider's discovery endpoint returns the expected issuer, because the Portal uses `issuer-uri` to fetch metadata when building `ClientRegistration`.

## 18. `portal-client`: Dependencies

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

The Portal **does not need** the Authorization Server starter; it only acts as a Relying Party/OAuth2 Client.

## 19. `portal-client`: `application.yml`

~~~yaml
server:
  port: 8080
  servlet:
    session:
      cookie:
        name: PORTALSESSION
        http-only: true

spring:
  security:
    oauth2:
      client:
        registration:
          local-idp:
            provider: local-idp
            client-id: portal-client
            client-secret: portal-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          local-idp:
            issuer-uri: http://127.0.0.1:9000
~~~

| Portal field | Provider must match |
|---|---|
| `client-id: portal-client` | `RegisteredClient.clientId` |
| `client-secret: portal-secret` | Credential hash at OP |
| `client_secret_basic` | Allowed client authentication method |
| `authorization_code` | Allowed grant type |
| `redirect-uri` | Exact registered redirect URI |
| `scope: openid/...` | Registered scopes |
| `issuer-uri` | `AuthorizationServerSettings.issuer` |

### 19.1. Registration ID Is Not Client ID

`local-idp` is used by Spring Client as the key to initiate login:

~~~text
/oauth2/authorization/local-idp
/login/oauth2/code/local-idp
~~~

Meanwhile, `portal-client` is sent to the OP as `client_id`.

### 19.2. This Client Secret Is Local-Only

Production should use `client-secret: ${PORTAL_OIDC_CLIENT_SECRET}` and a secret manager. Never copy the literal `portal-secret` string to a public deployment.

## 20. `portal-client`: Spring Boot Entry Point

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortalClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortalClientApplication.class, args);
    }
}
~~~

## 21. `portal-client`: `SecurityFilterChain` and PKCE

Because the Provider requires PKCE, the Portal must include `code_challenge` in the authorization request even though it is a confidential client.

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
    .DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web
    .OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
        HttpSecurity http,
        ClientRegistrationRepository registrations
    ) throws Exception {
        var requestResolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations,
                "/oauth2/authorization"
            );
        requestResolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce()
        );

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(requestResolver))
                .defaultSuccessUrl("/me", false))
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

### 21.1. `withPkce()`

`OAuth2AuthorizationRequestCustomizers.withPkce()` adds the PKCE challenge and stores the verifier to exchange the code at the token endpoint. Without it, a Provider configured with `requireProofKey(true)` rejects the flow per policy.

### 21.2. PKCE Does Not Replace `state` or `nonce`

PKCE binds the authorization code to the client initiating the request; `state` defends against login CSRF and correlates the request, while `nonce` binds the ID Token to the OIDC authentication request. All three mechanisms complement one another.

### 21.3. Do Not Enable `STATELESS` for Browser OIDC Login

The default `AuthorizationRequestRepository` uses the HTTP session to store `state`/`nonce`/verifier; browser login also requires an authenticated session after the callback. Never apply `SessionCreationPolicy.STATELESS` blindly on the Portal.

### 21.4. CSRF

POST endpoints rely on the session cookie and therefore need proper CSRF protection. Do not disable CSRF on the Portal.

## 22. `portal-client`: `HomeController`

~~~java
package com.example.portal;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HomeController {

    @GetMapping("/")
    public String home() {
        return """
            Local OIDC Portal
            Start login: /oauth2/authorization/local-idp
            After login: /me
            """;
    }

    @GetMapping("/me")
    public Map<String, Object> me(
        @AuthenticationPrincipal OidcUser user
    ) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("subject", user.getSubject());
        result.put("issuer", user.getIssuer().toString());
        String display = user.getFullName();
        if (display == null) {
            display = user.getPreferredUsername();
        }
        result.put("displayName", display);
        result.put("authorities", user.getAuthorities()
            .stream()
            .map(a -> a.getAuthority())
            .toList());
        return result;
    }
}
~~~

Never return raw ID Tokens, access tokens, or refresh tokens in HTTP responses. To verify login, returning subject, issuer, displayName, and selected authorities is sufficient.

### 22.1. Subject Only Has Meaning Within an Issuer Namespace

`sub` can collide across two different issuers; user identity mapping should use `(iss, sub)` or a verified internal mapping rather than assuming email is an immutable key.

### 22.2. `ROLE_ADMIN` Does Not Appear Automatically

Having a user named `admin` on the Provider does not mean the Portal grants `ROLE_ADMIN`. The Portal must map verified claims or tenant memberships according to policy if RBAC is required.

### 22.3. UserInfo Claims May Be Missing

`name` and `email` depend on the provider, scopes, and user consent. The controller should provide a fallback when an optional claim is null.

## 23. Starting the Portal

Once the Provider is running:

~~~bash
cd oidc-local-lab/portal-client
./gradlew bootRun
~~~

Windows:

~~~powershell
cd oidc-local-lab\portal-client
.\gradlew.bat bootRun
~~~

The Portal listens on port 8080 and fetches OIDC discovery metadata from the Provider.

### 23.1. If the Portal Fails to Boot

Check:

~~~text
GET http://127.0.0.1:9000/.well-known/openid-configuration
~~~

If the provider is not running yet or the issuer metadata differs from the configuration, Spring Boot may fail to construct `ClientRegistrationRepository`.

## 24. End-to-End Browser Login

Perform the following steps:

1. Open `http://127.0.0.1:8080/`.
2. Navigate to `http://127.0.0.1:8080/oauth2/authorization/local-idp`.
3. The browser redirects to the Provider at `http://127.0.0.1:9000/oauth2/authorize`.
4. Log in with `alice / alice-pass`.
5. Approve the scopes when the OP prompts for consent.
6. The browser returns to the callback `/login/oauth2/code/local-idp?code=...&state=...` on the Portal.
7. The Portal backend exchanges the code for tokens and validates the ID Token.
8. The Portal stores the authenticated session and sends the browser to `/me`.

Illustrative JSON response:

~~~json
{
  "subject": "alice",
  "issuer": "http://127.0.0.1:9000",
  "displayName": "alice",
  "authorities": [
    "OIDC_USER",
    "SCOPE_openid"
  ]
}
~~~

This is **illustrative**, not a fixed set of authorities: scopes and authority mappings vary by configuration and version.

### 24.1. Browser Network Developer Tools

Observe the requests and redirects:

~~~text
GET :8080/oauth2/authorization/local-idp  -> 302
GET :9000/oauth2/authorize?...            -> login/consent
GET :8080/login/oauth2/code/local-idp?... -> 302 /me
GET :8080/me                              -> 200
~~~

Never share unredacted HAR dumps: URLs contain authorization codes and requests contain session cookies.

## 25. Inspecting the Authorization Request Closely

The redirect to the OP typically contains:

~~~text
response_type=code
client_id=portal-client
redirect_uri=http://127.0.0.1:8080/login/oauth2/code/local-idp
scope=openid profile email orders.read
state=<random-value>
nonce=<random-oidc-nonce>
code_challenge=<S256-derived-value>
code_challenge_method=S256
~~~

### 25.1. `response_type=code`

We are using the Authorization Code Flow. The token endpoint is called from the backend; no client secret is sent to browser JavaScript.

### 25.2. `state`

Binds the callback to the preceding authorization request, helping prevent login CSRF and mix-up attacks. If `state` is tampered with, the callback must be rejected.

### 25.3. `nonce`

Binds the ID Token to the OIDC authentication request. Spring Security verifies the nonce after token exchange.

### 25.4. PKCE

`code_challenge` is derived from `code_verifier`; the verifier is sent when the Portal exchanges the code for tokens. Never send the raw verifier in the browser redirect.

### 25.5. `redirect_uri`

The OP must match the URI against the `RegisteredClient` allowlist. Never use an arbitrary browser-supplied `redirect_uri` to forward the code to an external URL.

## 26. Backend Token Request

The Portal backend sends a POST request:

~~~http
POST /oauth2/token HTTP/1.1
Host: 127.0.0.1:9000
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=authorization_code&
code=<one-time-code>&
redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Flogin%2Foauth2%2Fcode%2Flocal-idp&
code_verifier=<original-verifier>
~~~

Response:

~~~json
{
  "access_token": "<redacted>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email orders.read",
  "id_token": "<signed-jwt>",
  "refresh_token": "<optional>"
}
~~~

The OP verifies client authentication, authorization code, redirect URI, and PKCE. `refresh_token` may be absent depending on grant configuration and OP policy. Never write raw token responses to logs or public JSON endpoints.

## 27. ID Token vs. Access Token

| Token | Intended consumer | Must validate |
|---|---|---|
| ID Token | Relying Party / Portal | `iss`, `aud=portal-client`, expiry, signature, nonce |
| Access Token | Resource Server, UserInfo | Issuer/signature/expiry, scopes, audience/resource policy |
| Refresh Token | OAuth Client and token endpoint | Storage, rotation, revocation, refresh grant |

### 27.1. Do Not Mistake JSON Decoding for Verification

Base64url-decoding a JWT payload does not verify its signature. The Portal must use Spring Security's OIDC decoder with trusted JWKS, validating issuer, audience, expiration, and nonce.

### 27.2. OIDC ID Token Audience Is the OAuth Client ID

The ID Token has `aud=portal-client`, not `orders-api` by default. Access tokens for the Orders API have their own resource audience policy.

### 27.3. Invalid ID Tokens Must Be Rejected

Expired tokens, wrong issuer, missing Portal client ID in audience, or invalid signatures must be rejected. Never "let it pass" just because `email` or `sub` looks valid.

## 28. UserInfo Endpoint

Find it in discovery:

~~~bash
curl -s http://127.0.0.1:9000/.well-known/openid-configuration
~~~

UserInfo is typically published at a URL such as:

~~~text
http://127.0.0.1:9000/userinfo
~~~

Call UserInfo with an access token:

~~~http
GET /userinfo HTTP/1.1
Host: 127.0.0.1:9000
Authorization: Bearer <redacted-access-token>
~~~

### 28.1. Do Not Use an ID Token as a Bearer Token

UserInfo uses the access token, not the ID Token. Resource Servers and APIs likewise enforce access-token policies and must never accept an ID Token merely because it contains `sub`.

### 28.2. Claims Depend on Scopes and Consent

Do not assume `email` is present or verified. The Provider must respect privacy and consent; the Portal must handle optional claims gracefully.

### 28.3. Subject Must Match

OIDC UserInfo `sub` must match the `sub` of the ID Token for the current login. Never merge attributes from another user into the session.

## 29. The Portal's `OAuth2AuthorizedClient`

After login, the Portal holds:

~~~text
OAuth2AuthenticationToken:
  principal = Alice
  registrationId = local-idp

OAuth2AuthorizedClient:
  registrationId = local-idp
  principalName = Alice's stable name
  accessToken = value + scopes + expiration
  refreshToken = optional
~~~

Controller to inspect metadata (without exposing raw tokens):

~~~java
@GetMapping("/token-info")
public Map<String, Object> tokenInfo(
    @RegisteredOAuth2AuthorizedClient("local-idp")
    OAuth2AuthorizedClient client
) {
    return Map.of(
        "registrationId",
        client.getClientRegistration().getRegistrationId(),
        "expiresAt",
        client.getAccessToken().getExpiresAt().toString(),
        "scopes",
        client.getAccessToken().getScopes()
    );
}
~~~

Import `OAuth2AuthorizedClient` and `@RegisteredOAuth2AuthorizedClient` from Spring Security Client. This is a **lab-only endpoint**; production systems do not need to expose token metadata unless there is an explicit use case.

### 29.1. `AuthorizedClient` Is Not the Browser Session

`SecurityContext` holds the authenticated browser principal; `OAuth2AuthorizedClientRepository`/`OAuth2AuthorizedClientService` holds the token grant per registration and principal. They are related, not a single object.

### 29.2. When Multiple Registrations Exist

Do not use a token from registration A to call an API intended for B. Test `registrationId`, principal, scopes, and the outbound `Authorization` header.

## 30. Optional: Adding an Orders Resource Server on Port 8081

To see the access token in action, add an application:

~~~text
Portal :8080
  -> Authorization: Bearer access_token
Orders API :8081
  -> Validate issuer/JWKS/exp/scope/audience
  -> GET /orders
~~~

Orders API dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation(
        "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
    )
}
~~~

`application.yml`:

~~~yaml
server:
  port: 8081

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://127.0.0.1:9000
~~~

`SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/orders")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(server -> server
            .jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

**Note:** Disabling CSRF here only illustrates a Bearer-only stateless API, not a Portal browser session. A production Resource Server also needs **audience/resource validation**; issuer and scopes alone are not always sufficient.

### 30.1. Access-Token Audience

Spring Authorization Server token customization can add an audience claim per Resource Server. The Orders API must use an appropriate validator rather than trusting every JWT signed by the OP for any Resource Server.

## 31. Calling the API from the Portal with `RestClient`

With Spring Security 6.4+, `OAuth2ClientHttpRequestInterceptor` is available:

~~~java
@Bean
RestClient ordersClient(
    RestClient.Builder builder,
    OAuth2AuthorizedClientManager manager
) {
    OAuth2ClientHttpRequestInterceptor oauth =
        new OAuth2ClientHttpRequestInterceptor(manager);

    return builder
        .baseUrl("http://127.0.0.1:8081")
        .requestInterceptor(oauth)
        .build();
}
~~~

Selecting the registration:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver
    .clientRegistrationId;

String orders = restClient.get()
    .uri("/orders")
    .attributes(clientRegistrationId("local-idp"))
    .retrieve()
    .body(String.class);
~~~

This is an integration fragment: it requires an `OAuth2AuthorizedClientManager`/repository matching the Servlet request principal. If using `WebClient`, use `ServletOAuth2AuthorizedClientExchangeFilterFunction`.

### 31.1. Never Forward Tokens to Arbitrary Hosts

Never take an untrusted request parameter such as `?target=https://attacker.example` and attach a Bearer token to it. Destination URLs and registrations must be bound by a trusted allowlist.

### 31.2. Distinguish Downstream 401/403/429/5xx Responses

`401 invalid_token` indicates a token issue; `403 insufficient_scope` is a permissions issue; `429` and `5xx` are rate-limiting or availability errors. Do not retry token refreshes infinitely or log the browser out on every error.

## 32. Logout: Two Different Sessions

After login, the browser holds:

~~~text
PORTALSESSION = session at Portal :8080
IDPSESSION    = session at Provider :9000
~~~

If you log out **only at the Portal**, `IDPSESSION` may remain active. On the next login, the browser redirects to the Provider and may not be prompted for a password again.

### 32.1. Local Logout

Spring Security protects logout POST requests according to CSRF policy. Never turn `/logout` into an unconditional GET endpoint in production.

### 32.2. OIDC RP-Initiated Logout

If the OP publishes a suitable end-session endpoint, the Portal can use `OidcClientInitiatedLogoutSuccessHandler` to redirect the browser to the OP logout flow.

### 32.3. Token Revocation

Local session logout, authorized-client token removal/revocation, and OP SSO session termination are **three distinct lifecycles**. Do not assume one action terminates all three.

## 33. Why Separate Cookie Names Are Mandatory in This Lab

If both Portal and Provider set:

~~~http
Set-Cookie: JSESSIONID=...; Path=/
~~~

on host `127.0.0.1`, the browser does not isolate cookies by port. A response from the Provider can overwrite the Portal's `JSESSIONID`, causing the original `OAuth2AuthorizationRequest` to be lost:

~~~text
GET /oauth2/authorization/local-idp
  -> Portal stores state/nonce in session

Provider login sets same cookie name JSESSIONID
  -> Browser overwrites Portal session cookie

Callback to Portal
  -> Portal cannot find original request
  -> authorization_request_not_found / invalid_state
~~~

Use:

~~~yaml
# Provider
server.servlet.session.cookie.name: IDPSESSION

# Portal
server.servlet.session.cookie.name: PORTALSESSION
~~~

If the browser still holds cookies from an earlier attempt, clear cookies specifically for the local lab origins or use a clean private browsing profile.

### 33.1. Do Not Disable State Validation to Fix Cookie Collisions

State/cookie errors must be resolved at session isolation, hostname, cookie `Path`/`SameSite`/`Secure`, or load-balancing configuration; never disable `state`/`nonce` validation just to let the callback proceed.

## 34. Redirect URI, PKCE, and Session Correlation

The Provider allows:

~~~text
http://127.0.0.1:8080/login/oauth2/code/local-idp
~~~

The Portal constructs this URI from:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

### 34.1. Changing Port 8080 to 8082

If you only change the Portal port, the OP must reject the unregistered redirect URI. Update both sides deliberately; never use wildcard redirects.

### 34.2. Removing the PKCE Customizer

With the Provider enforcing `requireProofKey(true)`, an authorization request without `code_challenge` or a token request without `code_verifier` must be rejected. Restore `withPkce()` rather than disabling the policy to hide the failure.

### 34.3. Double Submit or Multiple Tabs

Authorization codes are single-use. Multiple browser tabs can carry distinct `state`/`nonce` values; the repository/session must maintain proper correlation. Never hard-code a global `state` or `nonce`.

## 35. Automated Testing Model

Do not conflate different testing levels:

| Test type | Purpose |
|---|---|
| Unit test Provider components | Token customizer, authority mapping, `RegisteredClient` policy |
| Discovery/JWKS smoke | OP public metadata and public keys |
| MockMvc `oidcLogin()` | Portal controller receiving a mocked `OidcUser` |
| Fake OP + MockMvc integration | Spring Security code exchange, state/nonce/JWT validation |
| Two real local apps | Browser redirects, cookies, consent, login |
| Resource Server integration | Access token issuer/signature/audience/scope |
| Browser E2E | `SameSite`, redirect chain, actual cookie behavior |

### 35.1. Discovery Smoke Test

~~~java
@Test
void discoveryHasExpectedIssuer() {
    RestClient rest = RestClient.create();
    Map<?, ?> metadata = rest.get()
        .uri("http://127.0.0.1:9000/.well-known/openid-configuration")
        .retrieve()
        .body(Map.class);

    assertThat(metadata.get("issuer"))
        .isEqualTo("http://127.0.0.1:9000");
    assertThat(metadata).containsKey("jwks_uri");
}
~~~

This is a smoke test that depends on a running Provider. In CI, use an ephemeral port and an injected URL/fixture lifecycle.

### 35.2. MockMvc Controller Test Does Not Actually Log In

~~~java
@WebMvcTest(HomeController.class)
class HomeControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void displaysSubject() throws Exception {
        mvc.perform(get("/me")
                .with(oidcLogin().idToken(token ->
                    token.claim("sub", "employee-42"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject")
                .value("employee-42"));
    }
}
~~~

`oidcLogin()` creates a mock `Authentication` without executing the OP, token endpoint, or signature check. To test ID Token validation, issue a real signed JWT from a fake OP and run through the callback.

## 36. Negative Test Matrix

| Action | Expected behavior |
|---|---|
| Provider not running | Discovery/connect error |
| Portal issuer URI differs from OP issuer | Discovery/ID Token validation failure |
| Wrong Portal client ID | Invalid client |
| Wrong Portal client secret | Invalid client at token endpoint |
| Registered redirect URI missing | Authorization request rejected |
| `openid` scope omitted | No longer performs OIDC login / ID Token as expected |
| PKCE `code_challenge` missing | OP rejects when `requireProofKey` is enabled |
| PKCE verifier mismatch | Token exchange rejected |
| Callback `state` tampered | Login rejected; not authenticated |
| Callback without `PORTALSESSION` | Original authorization request missing |
| Fake OP issues ID Token with wrong nonce | Login rejected |
| Fake OP issues expired ID Token | Login rejected |
| Fake OP issues wrong `iss`/`aud` | Login rejected |
| Fake OP signs with untrusted key | Login rejected |
| Consent denied | Controlled OAuth error; not logged in |
| Access token missing `orders.read` | Orders API returns 403 |
| Expired/bad-signature token sent to API | Orders API returns 401 |

**Testing principle:** the valid control must succeed. Each negative case changes only one factor at a time so you know precisely whether the failure stems from issuer, client authentication, PKCE, state, or signature.

## 37. Layered Troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Port 9000 busy | Another process occupies the port | Change port and sync issuer/config |
| Portal boot fails | Discovery unreachable | Start Provider first |
| Discovery 404 | OIDC not enabled | Check `.oidc(...)` |
| JWK Set 404 | `JWKSource`/chain misconfigured | Register key and matcher |
| Provider login form not shown | Form login chain missing | `@Order(2)` + `formLogin` |
| Authorization 400 | `clientId`/scope/redirect | Check `RegisteredClient` settings |
| `invalid_client` | Wrong secret or auth method | Align `client_secret_basic` |
| `invalid_request` PKCE | Missing challenge/verifier | Add `withPkce()` on Portal |
| Repeated consent prompts | In-memory consent lost on restart | Lab limitation / add persistence |
| `authorization_request_not_found` | Session cookie lost | Check `PORTALSESSION` and host/path |
| `invalid_state` | State mismatch with original request | Preserve callback/session |
| `invalid_redirect_uri` | Different port/host/path | Exact `RegisteredClient` redirect URI |
| ID Token invalid issuer | URI differs between OP and RP | Exact issuer match |
| ID Token invalid audience | Different client ID | Correct audience/`clientId` |
| ID Token bad signature | Signing key/JWKS mismatch | Trusted public key/current `kid` |
| ID Token nonce failure | Correlation broken | Never disable nonce validation |
| UserInfo 401 | Invalid/expired access token | Check Bearer auth/OP endpoint |
| Portal logged out but OP still logged in | `IDPSESSION` still active | Use RP-initiated OP logout |
| API returns 401 | Wrong JWT `iss`/`exp`/signature/audience | Check Resource Server decoder |
| API returns 403 | Missing scope/permission | Check consent/policy |
| Provider restart breaks tokens | Ephemeral signing key/store | Test reset; use persistent keys in prod |

## 38. Debugging Decision Tree

~~~text
Cannot complete local OIDC login
  |
  v
Provider discovery http://127.0.0.1:9000/.well-known/openid-configuration?
  |-- No -> fix OP .oidc(), chain and server startup.
  |
  v
Provider public /oauth2/jwks?
  |-- No -> fix JWKSource / JwtDecoder / OP config.
  |
  v
Portal /oauth2/authorization/local-idp redirects?
  |-- No -> ClientRegistration / oauth2Login / filter chain.
  |
  v
Redirect client_id, redirect_uri, scope, state, nonce, PKCE valid?
  |-- No -> fix registration and request resolver.
  |
  v
Provider user login and consent succeed?
  |-- No -> formLogin / user store / scope policy.
  |
  v
Callback same PORTALSESSION and original state?
  |-- No -> browser cookies / host mismatch.
  |
  v
Backend POST /oauth2/token succeeds?
  |-- No -> client secret, code, redirect, PKCE verifier.
  |
  v
ID Token iss/aud/exp/signature/nonce verified?
  |-- No -> issuer/JWKS/token validator.
  |
  v
Portal /me shows principal?
  |-- No -> authenticated session / controller mapping.
~~~

## 39. Limitations of the In-Memory Environment

The sample Provider uses:

~~~text
InMemoryRegisteredClientRepository
InMemoryUserDetailsManager
In-memory authorization/consent support
RSA signing key generated at startup
HTTP loopback
Demo credentials and client secret
~~~

### 39.1. Restart Alters State

Signing keys, authorizations, consents, and sessions may be lost or changed. Tokens issued before a restart may fail verification against the new key. This is a demo limitation, not a production pattern.

### 39.2. Cannot Scale Provider Replicas with Independent Memory Stores

If two instances hold different keys or authorizations, callbacks and token validation become inconsistent. Production requires shared/persistent stores, a stable issuer, and proper signing key management.

## 40. From Lab to Production

| Item | Local | Production |
|---|---|---|
| Issuer | HTTP 127.0.0.1 | Fixed public HTTPS URI |
| Client secret | Plaintext demo value | Managed secret with rotation |
| Client repository | In-memory | Persistent JDBC/custom |
| Consent/authorization store | In-memory demo | Persistent/shared |
| Users | Demo passwords | Real directory/MFA/password policy |
| Signing key | New RSA key on each restart | Managed keys + rotation/JWKS |
| Sessions | Two local cookies | `Secure`/`HttpOnly`/`SameSite` and shared store as needed |
| Scopes | Demo values | Least privilege/consent |
| Audience | Simplified | Explicit resource audience validation |
| Logout | Local-only or optional OP flow | Tested OIDC SSO logout lifecycle |
| Audit | Console | Redacted structured logs/metrics |
| Ingress | Direct loopback | Trusted forwarded headers and proxy |
| Testing | Manual browser smoke | CI protocol/security negative tests |

**Never deploy these demo users/passwords, HTTP issuer, or ephemeral signing keys to the Internet.** A real provider requires threat modeling, secure key storage, account/MFA policy, user lifecycle management, DPoP/mTLS where required by contract, rate limits, monitoring, recovery, and a security review.

## 41. Exercise 1 — Successful Login

Start both apps, visit `/oauth2/authorization/local-idp`, log in as Alice, and navigate to `/me`.

**Question:** Why doesn't the Portal know Alice's password?

**Answer:** The password goes directly to the Provider; the Portal receives an authorization code, exchanges it with the OP on the backend, and verifies the ID Token.

## 42. Exercise 2 — Redirect URI Mismatch

Change the Portal port from 8080 to 8082 while keeping the Provider `RegisteredClient` redirect URI on 8080.

**Expected:** The OP rejects the unregistered redirect URI. Never use a wildcard redirect to "fix" this.

## 43. Exercise 3 — Missing PKCE

Keep `requireProofKey(true)` on the Provider and remove `withPkce()` from the Portal.

**Expected:** The authorization or token request is rejected when the challenge or verifier is missing. Restore the PKCE customizer rather than disabling the policy.

## 44. Exercise 4 — Two `JSESSIONID` Cookies with the Same Name

Try using `JSESSIONID` as the cookie name on both the Provider and the Portal on `127.0.0.1`.

**Expected:** Cookie collision can cause state/session loss. Restore `IDPSESSION` and `PORTALSESSION`.

## 45. Exercise 5 — Adding a Claim to the ID Token

In `OAuth2TokenCustomizer`, add:

~~~java
context.getClaims().claim("department", "engineering");
~~~

**Question:** Does this claim automatically grant permission to view engineering reports?

**Answer:** No. Business authorization still requires trusted membership and authority mapping.

## 46. Exercise 6 — Checking Consent and UserInfo

Log in with different scopes; observe the consent prompt and the UserInfo/ID Token claims.

**Question:** Is it acceptable to emit `email_verified=true` from a demo username?

**Answer:** No. Only emit verified claims when backed by a real verification source.

## 47. Exercise 7 — Refresh Token

Lower the access-token TTL and observe the authorized-client manager when the token expires or is near expiration.

**Question:** Why might no refresh token be present?

**Answer:** A registered grant type does not guarantee a refresh token is issued; it also depends on OP policy, consent, and token lifecycle. The app also needs the right manager, provider, and persistence.

## 48. Exercise 8 — Orders API

Create a Resource Server on `:8081` requiring `SCOPE_orders.read`.

**Expected:**

- No Bearer token: 401.
- Expired token / invalid signature / wrong issuer: 401.
- Valid token missing scope: 403.
- Token with proper authority, issuer, and audience: 200.

**Reminder:** The API must validate the appropriate resource audience, not just issuer and scope.

## 49. Exercise 9 — Adding a Second Registration

Create `RegisteredClient` `portal-admin-client`, `ClientRegistration` `local-admin-idp`, and callback:

~~~text
http://127.0.0.1:8080/login/oauth2/code/local-admin-idp
~~~

**Question:** Can an ID Token with audience `portal-client` be used to log in to the new client?

**Answer:** No. The audience must match the client ID of the target registration.

## 50. Exercise 10 — Logout and Restart

Log out only at the Portal, log in again, and then restart the Provider.

**Observation:** `IDPSESSION` may allow re-login without prompting for a password; restarting may lose the OP session/consent and rotate the RSA signing key.

**Question:** Why does production need persistent keys/authorization stores and an OIDC logout policy?

**Answer:** To ensure token verification continuity, session continuity, safe key rotation, and proper SSO termination per contract.

## 51. Completion Checklist

| Item | Requirement |
|---|---|
| Provider running on :9000 | Yes |
| Portal running on :8080 | Yes |
| Exact issuer `127.0.0.1:9000` | Yes |
| Separate session cookies | IDPSESSION, PORTALSESSION |
| Authorization Server OIDC enabled | Yes |
| Discovery returns correct issuer/JWKS URI | Yes |
| Public JWKS does not leak private key | Yes |
| `RegisteredClient.clientId` | portal-client |
| Client secret and method match Portal | Yes |
| Authorization Code grant | Yes |
| Exact redirect URI | Yes |
| OIDC `openid` scope | Yes |
| Consent handled | Yes |
| Provider requires PKCE | Yes |
| Portal sends PKCE challenge/verifier | Yes |
| Demo users can log in | Yes |
| `state`/`nonce` preserved across callback | Yes |
| ID Token fully validated | Yes |
| Portal `/me` displays safe OIDC principal | Yes |
| Raw tokens/secrets not exposed | Yes |
| `AuthorizedClient` selects correct registration | Yes |
| Resource Server audience/scopes (if added) | Yes |
| Local vs. OP logout distinguished | Yes |
| Impact of restart on ephemeral signing keys understood | Yes |
| Negative tests exercised | Yes |
| No HTTP/demo credentials used in production | Yes |

## 52. Anti-Patterns to Avoid

**1.** Implementing a custom OAuth2/OIDC Provider with a single endpoint returning an arbitrary JWT while skipping grant/protocol checks.

**2.** Using the same `JSESSIONID` cookie name for two Servlet apps on the same hostname across different ports.

**3.** Mixing `localhost` and `127.0.0.1` when issuer/callback requires an exact match.

**4.** Copying HTTP loopback issuer URLs and demo secrets into production.

**5.** Generating a new signing key on every production instance restart without key rotation or persistence.

**6.** Disabling PKCE/`state`/`nonce` because a callback failed.

**7.** Returning raw ID Tokens or access tokens in `/me`.

**8.** Treating access tokens and ID Tokens as having the same audience and purpose.

**9.** Assuming an OP `ADMIN` role automatically grants `ROLE_ADMIN` in the Portal.

**10.** Disabling CSRF for the browser-session Portal.

**11.** Forwarding a Bearer token to whatever URL the browser specifies.

**12.** Running only `oidcLogin()` tests and claiming real OIDC callbacks and JWT signature validation work.

**13.** Skipping resource audience validation just because the JWT signature and issuer are valid.

**14.** Assuming local logout equals OP SSO logout and token revocation.

**15.** Writing keys, authorization codes, or cookies into CI logs unredacted.

## 53. References

- Spring Authorization Server Reference: https://docs.spring.io/spring-authorization-server/reference/
- Spring Authorization Server Getting Started: https://docs.spring.io/spring-authorization-server/reference/getting-started.html
- Spring Security OAuth2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/
- Spring Security OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Code Grant: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 PKCE: https://www.rfc-editor.org/rfc/rfc7636

When applying these snippets to a newer Spring Security or Authorization Server line, verify the dependency starters, configuration classes, and DSL methods against the documentation for that exact major/minor version.

## 54. Summary

We have built a local OpenID Provider using **Spring Authorization Server** and integrated a **Spring Security OAuth2/OIDC Client**:

~~~text
local-provider :9000
  RegisteredClient, demo user, consent
  Authorization Code + PKCE
  OIDC issuer/discovery/ID Token
  RSA signing key + public JWKS

portal-client :8080
  ClientRegistration issuer-uri
  oauth2Login + PKCE request resolver
  OIDC callback + ID Token validation
  authenticated browser session + OidcUser
~~~

The key takeaway is not merely seeing `/me` return 200. Learners must understand **redirects, registered clients and redirect URIs, `state`, `nonce`, PKCE challenge/verifier, the token endpoint, public JWKS, issuer/audience/signature validation, separate session cookies, and the authorized-client lifecycle**.

Spring Authorization Server lets us operate an OP ourselves without re-implementing the protocol from scratch. However, a demo using HTTP loopback, demo passwords/secrets, in-memory stores, and ephemeral RSA signing keys **is not a production architecture**. Going to production requires HTTPS, persistent stores, key/secret management, identity/MFA policies, resource audience validation, rate limits, logout design, monitoring, and security testing.

**Expected outcome achieved:** The Portal logs in via the local provider using Authorization Code + PKCE, properly validates the ID Token, receives the OIDC principal, and maintains a session; invalid issuer/client/redirect/state/PKCE/signature cases must **be rejected**, never "fixed" by disabling validation.
