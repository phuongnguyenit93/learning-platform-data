# Completing OIDC SSO, ID Token, UserInfo, and Logout

> **Chapter: Practical Labs.** This lab belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, guiding you through completing an OpenID Connect flow usable across multiple web applications. You will configure Spring Authorization Server as an OpenID Provider, sign in from two relying parties, inspect the ID Token, fetch user details via the UserInfo endpoint, and perform RP-Initiated Logout. The exercise connects client management, authorization codes, PKCE, token signing, sessions, and OIDC endpoints into a runnable, testable flow.

The expected outcome is that a user logs in once at the Authorization Server, and can then open the second web application in the same browser without re-entering their password. Each application still maintains its own session; SSO happens because both trust the same OpenID Provider and the browser still holds an active login session at the provider.

## 1. Lab Objectives and Architecture

After completing this lab, you will be able to:

1. Enable OpenID Connect on Spring Authorization Server.
2. Register two confidential web clients using authorization code and PKCE.
3. Issue an ID Token with a stable subject and claims matching granted scopes.
4. Expose a UserInfo endpoint with scope-controlled claim access.
5. Configure Spring Security OAuth2 Login on two relying parties.
6. Distinguish local logout from RP-Initiated Logout.
7. Verify discovery metadata, ID Token signatures, nonce, UserInfo, and logout redirects.

The architecture uses three locally running applications:

| Component | Address | Role |
|---|---|---|
| Spring Authorization Server | `http://localhost:9000` | OpenID Provider, login session, authorization, token, UserInfo, and end-session endpoints |
| Portal A | `http://localhost:8081` | First relying party |
| Portal B | `http://localhost:8082` | Second relying party |

~~~mermaid
flowchart TD
    U[Browser] --> A[Portal A :8081]
    U --> B[Portal B :8082]
    A -->|Authorization Code + PKCE| AS[Authorization Server :9000]
    B -->|Authorization Code + PKCE| AS
    AS --> LOGIN[Spring Security login session]
    AS --> TOK[ID Token + Access Token]
    AS --> UI[UserInfo endpoint]
    A -->|Bearer Access Token| UI
    B -->|Bearer Access Token| UI
    A -->|RP-Initiated Logout| AS
    B -->|RP-Initiated Logout| AS
~~~

The two portals have separate client IDs, secrets, and redirect URIs. They share the same issuer. The browser holds the Authorization Server session cookie on the localhost host; therefore, when Portal B redirects the browser to the issuer, the Authorization Server recognizes that the user is already logged in.

In the lab, repositories and signing keys can run in memory to reduce setup steps. In real deployments, you must use persistent storage, securely managed signing keys, and an appropriate session store. Do not use the lab's temporary key configuration for production.

## 2. Project Preparation

Create three separate Spring Boot applications or three modules in the same workspace:

- `authorization-server`
- `portal-a`
- `portal-b`

Use the same Spring Boot/Spring Security release line compatible with the chosen Spring Authorization Server version. On the Authorization Server, add Spring Authorization Server and Spring Security dependencies. On each portal, add Spring Web, Spring Security, and OAuth2 Client.

Key dependencies:

~~~xml
<!-- Authorization Server -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-oauth2-authorization-server</artifactId>
</dependency>

<!-- Each relying party -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Dependency management must pull versions from the Spring Boot BOM or the official compatibility matrix. Do not arbitrarily mix Spring Security and Spring Authorization Server from incompatible version lines.

## 3. Configuring the OpenID Provider

### 3.1. Enabling OIDC Endpoints

The Authorization Server supports OAuth 2.0 and OpenID Connect. Issuing ID Tokens, discovery metadata, UserInfo, and logout endpoints requires OIDC to be explicitly enabled in the configurer.

Example filter chain configuration using the common Spring Authorization Server configuration API:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper)
            throws Exception {

        OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);

        http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
                .oidc(oidc -> oidc
                        .userInfoEndpoint(userInfo ->
                                userInfo.userInfoMapper(userInfoMapper))
                        .logoutEndpoint(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The first filter chain protects the Authorization Server protocol endpoints and enables OIDC UserInfo/logout. The second filter chain provides the login form for users. If the Spring Authorization Server version you are using introduces a newer DSL or updated configuration API, adjust the configurer initialization according to that version's documentation; the lab's endpoints and security principles remain unchanged.

The Authorization Server's OIDC logout uses `SessionRegistry` to locate authenticated sessions to terminate. Declare the registry and publisher so the registry receives events when HTTP sessions are destroyed:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class OidcSessionRegistryConfiguration {

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

In a multi-instance deployment, an in-memory `SessionRegistryImpl` only tracks sessions on a single instance. You need a compatible distributed session registry/store if browsers can log in on another node or if logout must locate sessions cluster-wide.

OIDC requires the `openid` scope. If a client only requests an OAuth scope like `orders.read` without requesting `openid`, that request is not an OIDC authentication request and an ID Token should not be expected.

### 3.2. Declaring the Issuer

The issuer must be a stable public URL that relying parties use to discover metadata and verify tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration
public class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("http://localhost:9000")
                .build();
    }
}
~~~

All nodes of the same Authorization Server must use the same issuer. When running behind a reverse proxy, configure the issuer using the external URL and only trust forwarded headers from trusted proxies. Do not let each node derive its own issuer from an internal hostname.

### 3.3. Signing Key and JWK Set

An ID Token is a signed JWT. Relying parties use the public key published via JWKS to verify its signature. Lab example generating an RSA key at startup:

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
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Configuration
public class SigningKeyConfiguration {

    @Bean
    JWKSource<SecurityContext> jwkSource() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keyPair = generator.generateKeyPair();

        RSAKey rsaKey = new RSAKey.Builder(
                (RSAPublicKey) keyPair.getPublic())
                .privateKey((RSAPrivateKey) keyPair.getPrivate())
                .keyID(UUID.randomUUID().toString())
                .build();

        JWKSet jwkSet = new JWKSet(rsaKey);
        return (selector, context) -> selector.select(jwkSet);
    }

    @Bean
    JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
        return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
    }
}
~~~

A key regenerated on every restart is only suitable for labs. Old tokens may fail verification against the new public key. Production needs to store private keys in a KMS/HSM or protected secret store, keep `kid` stable, publish public JWKs at the right time, and maintain a rotation process. Do not commit private keys into source control or bake them into container images.

### 3.4. Creating a Lab Login User

To focus on OIDC, the lab uses an in-memory user:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class LabUserConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(passwordEncoder.encode("ChangeMe-OnlyForLab"))
                        .roles("USER")
                        .build());
    }
}
~~~

Log in with `alice` and the lab password above. Do not use this account or password in a real environment. The principal name in the example is `alice`; in a real system, `Authentication.getName()` should return an immutable subject ID that is unique within the issuer, rather than a mutable email or display name.

## 4. Registering the Two Relying Parties

The two portals are confidential web clients running on the server. Each client has its own secret, redirect URI, and post-logout redirect URI.

~~~java
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
public class RegisteredClientConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder) {

        RegisteredClient portalA = createClient(
                "portal-a",
                "http://localhost:8081/login/oauth2/code/auth-server",
                "http://localhost:8081/",
                passwordEncoder);

        RegisteredClient portalB = createClient(
                "portal-b",
                "http://localhost:8082/login/oauth2/code/auth-server",
                "http://localhost:8082/",
                passwordEncoder);

        return new InMemoryRegisteredClientRepository(portalA, portalB);
    }

    private RegisteredClient createClient(
            String clientId,
            String redirectUri,
            String postLogoutRedirectUri,
            PasswordEncoder passwordEncoder) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
                .clientId(clientId)
                .clientSecret(passwordEncoder.encode("LabSecret-" + clientId))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri(redirectUri)
                .postLogoutRedirectUri(postLogoutRedirectUri)
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .scope(OidcScopes.EMAIL)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(false)
                        .build())
                .build();
    }
}
~~~

Both clients require authorization code and PKCE. `requireProofKey(true)` requires the authorization request to include a PKCE challenge. Secrets are encoded with the same PasswordEncoder used by client authentication. `requireAuthorizationConsent(false)` keeps the lab focused on SSO; if consent is enabled, the Authorization Server needs a consent page and a workflow to persist user decisions.

On the relying parties, `OAuth2AuthorizationRequestCustomizers.withPkce()` is attached to the resolver to send code_challenge and code_verifier even when the client is confidential. Because the server requires PKCE, both sides must participate in this step.

The Redirect URI must match the exact callback registered by the portal. `postLogoutRedirectUri` must also match the value registered for the client. In the lab, consistently use `localhost`; do not mix `localhost` with `127.0.0.1` because they are treated as different hosts for redirect URIs and cookies.

## 5. Issuing Claims in the ID Token

### 5.1. What Information Does an ID Token Carry?

An ID Token is an attestation of the user authentication result intended for the OIDC client. Standard claims typically include:

| Claim | Meaning |
|---|---|
| `iss` | Issuer that issued the token |
| `sub` | Stable subject representing the user within the issuer |
| `aud` | Client or audience the token is intended for |
| `exp` | Expiration timestamp |
| `iat` | Issued-at timestamp |
| `auth_time` | Time when the user was authenticated if provided by flow/policy |
| `nonce` | Value binding the request and ID Token if the client sent a nonce |
| `at_hash` / `c_hash` | Hashes linking the access token or authorization code when applicable |

Spring Authorization Server generates protocol claims such as issuer, subject, audience, expiration, and nonce according to the flow. Do not manually override `iss`, `aud`, `exp`, `iat`, `nonce`, `at_hash`, or `c_hash` in a customizer unless there is a specific protocol requirement.

### 5.2. Creating a Profile Source

Separate the user profile from the token customizer so the in-memory source can be replaced with a database or identity service:

~~~java
public record UserProfile(
        String subject,
        String name,
        String preferredUsername,
        String email,
        boolean emailVerified) {
}

public interface UserProfileService {
    UserProfile findBySubject(String subject);
}
~~~

In the lab, create a simple implementation returning a profile for subject `alice`:

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class DemoUserProfileService implements UserProfileService {

    private final Map<String, UserProfile> profiles = Map.of(
            "alice",
            new UserProfile(
                    "alice",
                    "Alice Nguyen",
                    "alice",
                    "alice@example.test",
                    true));

    @Override
    public UserProfile findBySubject(String subject) {
        UserProfile profile = profiles.get(subject);
        if (profile == null) {
            throw new IllegalArgumentException("Unknown subject");
        }
        return profile;
    }
}
~~~

The `subject` value must match `Authentication.getName()` in the lab. In production, map the principal to a stable internal ID; do not use email as `sub` if emails can change or be reassigned.

### 5.3. Adding Claims by Scope

Use `OAuth2TokenCustomizer<JwtEncodingContext>` to add claims to the ID Token. Only add claims when the client has been granted the corresponding scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration
public class IdTokenClaimsConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer(
            UserProfileService profiles) {

        return context -> {
            if (!OidcParameterNames.ID_TOKEN.equals(
                    context.getTokenType().getValue())) {
                return;
            }

            UserProfile profile = profiles.findBySubject(
                    context.getPrincipal().getName());

            if (context.getAuthorizedScopes().contains(OidcScopes.PROFILE)) {
                context.getClaims()
                        .claim("name", profile.name())
                        .claim("preferred_username", profile.preferredUsername());
            }

            if (context.getAuthorizedScopes().contains(OidcScopes.EMAIL)) {
                context.getClaims()
                        .claim("email", profile.email())
                        .claim("email_verified", profile.emailVerified());
            }
        };
    }
}
~~~

The customizer is invoked during JWT token generation; the `ID_TOKEN` check prevents ID Token profile claims from being accidentally added to every access token. The example only issues `name` and `preferred_username` when the `profile` scope is present, and `email`/`email_verified` when the `email` scope is present.

Do not dump every attribute from the user database into the ID Token. Issue only the claims needed by the client, matching granted scopes and consent. The ID Token is sent to the client; unnecessary sensitive information should remain in UserInfo or a separate API with proper authorization.

## 6. Configuring the UserInfo Endpoint

The UserInfo endpoint returns claims about the user when a relying party calls it with a valid access token. This is an OpenID Connect resource endpoint:

- The request uses `Authorization: Bearer <access_token>`.
- The access token must have been issued for the flow/client and still be valid.
- The server only returns claims permitted by the granted scopes/authorization.
- The `sub` claim in UserInfo must match `sub` in the ID Token.
- Do not use an ID Token as the bearer token to call UserInfo.

Create a mapper based on the stored authorization:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

@Configuration
public class UserInfoConfiguration {

    @Bean
    Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
            UserProfileService profiles) {

        return context -> {
            OAuth2Authorization authorization = context.getAuthorization();
            UserProfile profile = profiles.findBySubject(
                    authorization.getPrincipalName());
            Set<String> scopes = authorization.getAuthorizedScopes();

            Map<String, Object> claims = new HashMap<>();
            claims.put(IdTokenClaimNames.SUB, profile.subject());

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.name());
                claims.put("preferred_username", profile.preferredUsername());
            }

            if (scopes.contains(OidcScopes.EMAIL)) {
                claims.put("email", profile.email());
                claims.put("email_verified", profile.emailVerified());
            }

            return new OidcUserInfo(claims);
        };
    }
}
~~~

The mapper uses `OAuth2Authorization` to obtain the principal and authorized scopes. UserInfo always returns `sub`; other claims are restricted by scope. When the profile changes, UserInfo can reflect fresh data from the profile service, whereas an old ID Token still retains the claims from its issuance time. This is one reason not to treat the ID Token as an always-up-to-date profile API.

If using a custom mapper, verify that `sub` matches the subject in the ID Token exactly. Do not return claims for scopes the client has not been granted. Verify that the access token belongs to the right authorization/client rather than relying on query parameters sent by the client.

## 7. Configuring Portal A and Portal B

### 7.1. application.yml

Portal A runs on port 8081 and uses client `portal-a`:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: portal-a
  security:
    oauth2:
      client:
        registration:
          auth-server:
            provider: auth-server
            client-id: portal-a
            client-secret: LabSecret-portal-a
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          auth-server:
            issuer-uri: http://localhost:9000
~~~

Portal B uses a similar configuration, changing:

~~~yaml
server:
  port: 8082

spring:
  application:
    name: portal-b
  security:
    oauth2:
      client:
        registration:
          auth-server:
            provider: auth-server
            client-id: portal-b
            client-secret: LabSecret-portal-b
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          auth-server:
            issuer-uri: http://localhost:9000
~~~

Spring Security OAuth2 Client uses `issuer-uri` to discover OpenID Provider metadata. From the metadata, the client locates the authorization endpoint, token endpoint, JWKS URI, UserInfo endpoint, and end-session endpoint if published by the provider. The redirect URI generated by Spring must match the URI registered on the Authorization Server.

In production, client secrets must be supplied via a secret manager or secure deployment environment. Do not commit lab secrets to public repositories.

### 7.2. SecurityFilterChain for the Relying Parties

Each portal enables OAuth2 Login and configures logout to use OIDC RP-Initiated Logout:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
public class PortalSecurityConfiguration {

    @Bean
    OAuth2AuthorizationRequestResolver pkceAuthorizationRequestResolver(
            ClientRegistrationRepository clientRegistrationRepository) {

        DefaultOAuth2AuthorizationRequestResolver resolver =
                new DefaultOAuth2AuthorizationRequestResolver(
                        clientRegistrationRepository, "/oauth2/authorization");
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());
        return resolver;
    }

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository clientRegistrationRepository) {

        OidcClientInitiatedLogoutSuccessHandler handler =
                new OidcClientInitiatedLogoutSuccessHandler(
                        clientRegistrationRepository);
        handler.setPostLogoutRedirectUri("{baseUrl}/");
        return handler;
    }

    @Bean
    SecurityFilterChain portalSecurityFilterChain(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler,
            OAuth2AuthorizationRequestResolver pkceAuthorizationRequestResolver)
            throws Exception {

        http.authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .authorizationEndpoint(endpoint ->
                                endpoint.authorizationRequestResolver(
                                        pkceAuthorizationRequestResolver)))
                .logout(logout ->
                        logout.logoutSuccessHandler(oidcLogoutSuccessHandler));

        return http.build();
    }
}
~~~

`OidcClientInitiatedLogoutSuccessHandler` constructs a logout request to the end-session endpoint discovered from the provider's metadata. The handler uses the login session's ID Token to send `id_token_hint`, along with `post_logout_redirect_uri`. The post-logout URI must be registered on the client at the Authorization Server.

If the provider does not publish `end_session_endpoint` or does not support RP-Initiated Logout, the handler cannot complete logout at the provider. Check the discovery metadata and Spring Authorization Server version. Default local logout only clears the session at the portal.

### 7.3. Displaying Login Information

The controller receives the `OidcUser` created by Spring Security after verifying the OIDC response. To keep the example concise, the endpoint returns the verified claims as JSON:

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PortalController {

    @GetMapping("/")
    Map<String, Object> home(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "subject", user.getSubject(),
                "issuer", user.getIssuer().toString(),
                "name", user.getFullName() == null ? "" : user.getFullName(),
                "email", user.getEmail() == null ? "" : user.getEmail(),
                "idTokenClaims", user.getIdToken().getClaims(),
                "userInfoClaims", user.getUserInfo() == null
                        ? Map.of()
                        : user.getUserInfo().getClaims());
    }
}
~~~

Do not display raw ID Tokens or access tokens on the page. The lab only returns claims already verified by Spring Security and the received UserInfo. Real applications must control which claims are displayed and avoid leaking PII in the browser, logs, or analytics.

## 8. Running the Lab in Sequence

### Step 1: Start the Authorization Server

Run the application on port 9000. Open the discovery document:

`http://localhost:9000/.well-known/openid-configuration`

Verify the metadata includes:

- `issuer` is `http://localhost:9000`.
- `authorization_endpoint` and `token_endpoint`.
- `jwks_uri`.
- `userinfo_endpoint`.
- `end_session_endpoint` when OIDC logout is enabled in the version in use.

Open the `jwks_uri` retrieved from metadata and confirm it contains a public key with a `kid`. Do not rely on guessing the JWKS path; use the URI published by the provider.

### Step 2: Start Portal A

Run Portal A on port 8081 and visit `http://localhost:8081/`.

1. The portal redirects the browser to the Authorization Server.
2. The Authorization Server displays the login form.
3. Log in with the lab user `alice`.
4. The browser returns to Portal A's callback with an authorization code.
5. Portal A exchanges the code for tokens via a back-channel token request.
6. Spring Security verifies the ID Token and creates a local session.
7. The home page displays subject, issuer, name, email, and UserInfo claims.

On the first attempt, the user may see a consent screen if the client configuration requires consent. The lab configuration sets `requireAuthorizationConsent(false)` to skip that step.

### Step 3: Start Portal B and Test SSO

Run Portal B on port 8082 and visit `http://localhost:8082/` in the same browser:

1. Portal B redirects the browser to the same issuer.
2. The Authorization Server recognizes the login session cookie created when using Portal A.
3. As long as the session is still valid and no policy forces re-authentication, the Authorization Server does not prompt for the password again.
4. The Authorization Server generates an authorization code for client `portal-b`.
5. Portal B exchanges the code, verifies the ID Token, and creates its own local session.

Portal B still has its own authorization transaction and client ID. SSO does not mean Portal A shares its internal session or access token with Portal B. Each relying party executes its own authorization flow with the same OpenID Provider.

### Step 4: Inspect the ID Token

In Portal A or Portal B, check the displayed claims:

| Claim | Expected Result |
|---|---|
| `iss` | `http://localhost:9000` |
| `sub` | Stable subject of the lab user (`alice`) |
| `aud` | Client ID of the corresponding portal |
| `exp` | A future timestamp right after login |
| `iat` | Issued-at timestamp |
| `name` | `Alice Nguyen` when the `profile` scope is granted |
| `email` | `alice@example.test` when the `email` scope is granted |
| `email_verified` | `true` in the lab profile data |

The two portals have different `aud` values because each ID Token is intended for a single client. Do not use Portal A's ID Token as a login token for Portal B. Portal B must receive the ID Token from the authorization flow it initiated itself.

Spring Security OIDC Login verifies the issuer, signature, audience, expiration, and required OIDC checks, including nonce when the request uses a nonce. Do not decode JWTs manually and trust claims while skipping signature verification and validation.

### Step 5: Test UserInfo

After login, the Spring Security OIDC client can call the UserInfo endpoint using the access token if the provider publishes the endpoint and the client has the appropriate scopes. In the home page JSON, compare `userInfoClaims` with `idTokenClaims`.

You can test manually using an HTTP client/Postman:

~~~http
GET /userinfo HTTP/1.1
Host: localhost:9000
Authorization: Bearer PORTAL_ACCESS_TOKEN
Accept: application/json
~~~

The expected result has `sub` matching the subject in the ID Token. The `name`, `preferred_username`, `email`, and `email_verified` claims only appear when the corresponding scopes are granted and the profile service has data.

Do not send an ID Token in the Bearer header to UserInfo. UserInfo is protected by an access token. Do not share real tokens in screenshots, logs, or practice documents.

### Step 6: Test Local Logout

To test local logout separately, temporarily configure Spring Security's default logout in the portal:

~~~java
http.logout(Customizer.withDefaults());
~~~

Local logout only destroys Portal A's session. Open Portal B if it already has a local session; Portal B may still be logged in. If Portal B does not need to log in again after A's local logout, that is expected behavior because the two portals maintain separate sessions.

### Step 7: Test RP-Initiated Logout

After completing the local logout test, restore `OidcClientInitiatedLogoutSuccessHandler` in the portal configuration and verify:

1. The portal sends a logout request via the browser to the end-session endpoint from metadata.
2. The request contains `id_token_hint` and the registered `post_logout_redirect_uri`.
3. The Authorization Server validates the logout details and terminates the SSO session as configured.
4. The browser is redirected back to the valid post-logout URI.
5. When accessing a portal that does not have a local session, the portal redirects to the Authorization Server; the user must log in again because the SSO session has ended.

For a clean test, log out locally from both portals before retrying. If Portal B still holds a local session, it may render the logged-in page without redirecting to the Authorization Server. RP-Initiated Logout at the provider does not automatically clear all local sessions across all relying parties; synchronized multi-app logout requires implementing front-channel or back-channel logout accordingly.

## 9. Distinguishing ID Token, Access Token, and UserInfo

| Component | Purpose | Where Used | Verification / Check Method |
|---|---|---|---|
| ID Token | Attests login result and identity for an OIDC client | Relying party | Verify signature, issuer, audience, exp, nonce, and OIDC checks |
| Access Token | Grants authorization to access resources/APIs | UserInfo endpoint or resource server | Resource server validates token format and policy |
| UserInfo | Provides user claims according to granted scopes | Relying party calling with an access token | Endpoint validates bearer token and returns `sub` matching ID Token |

Do not use an ID Token to call business APIs. Do not treat an access token as proof of user login for a client. Do not consume claims from UserInfo without verifying the access token and subject binding.

## 10. Security Checks to Verify

- **Stable subject:** `sub` must be unique within the issuer and independent of mutable emails or display names.
- **Consistent issuer:** ID Token, discovery metadata, and relying party configurations must use the same issuer.
- **Client-specific audience:** Portal A only accepts ID Tokens intended for Portal A.
- **Nonce:** when the client sends a nonce, the ID Token must carry the matching nonce and the client must verify it.
- **PKCE:** authorization code flow uses S256 challenge/verifier; reject mismatched verifiers.
- **Redirect URI:** exact match against registered URIs; avoid arbitrary wildcards.
- **Scopes and claims:** only return profile/email claims that were granted and permitted to be disclosed.
- **UserInfo subject:** `sub` from UserInfo must match `sub` in the ID Token for the same session.
- **Signing key:** private keys are protected; public JWKs are properly published with a rotation plan.
- **Logout redirect:** only redirect to a registered `post_logout_redirect_uri`.
- **Session cookie:** use Secure, HttpOnly, and appropriate SameSite attributes in HTTPS production.
- **CSRF:** keep CSRF protection for logout forms and session-backed web actions.
- **Token handling:** do not log or display raw ID Tokens or access tokens; store tokens using the application's secure mechanisms.

## 11. Test Matrix

| # | Scenario | Expected Result |
|---|---|---|
| 1 | Discovery document is accessed | Metadata returns the correct issuer and OIDC endpoints |
| 2 | Client does not request `openid` | Request is not processed as OIDC authentication and no ID Token is expected |
| 3 | Portal A first-time login | User is authenticated and gets a local session |
| 4 | Portal B login in the same browser | No password re-entry needed while AS session is still valid |
| 5 | Portal B uses a different client ID | ID Token has Portal B's audience |
| 6 | ID Token has invalid signature | Relying party rejects authentication |
| 7 | ID Token has wrong issuer or audience | Relying party rejects token |
| 8 | ID Token is expired | Relying party rejects token |
| 9 | Mismatched nonce | OIDC login fails |
| 10 | Authorization code reused | Token endpoint rejects already consumed code |
| 11 | Wrong PKCE verifier | Token endpoint rejects token request |
| 12 | Scope contains only `openid` | UserInfo does not return out-of-scope profile/email claims |
| 13 | Scope includes `profile` | UserInfo returns permitted profile claims |
| 14 | Scope includes `email` | UserInfo returns email and verified status per policy |
| 15 | UserInfo called with ID Token as bearer | Request is rejected |
| 16 | UserInfo called with invalid access token | Request is rejected |
| 17 | UserInfo `sub` differs from ID Token `sub` | Relying party must not merge the two identities |
| 18 | Portal A local logout | Session A is cleared; session B and AS session may still exist |
| 19 | RP-Initiated Logout with unregistered redirect URI | Authorization Server rejects invalid redirect |
| 20 | RP-Initiated Logout succeeds | AS SSO session ends as configured |
| 21 | Accessing portal after AS logout and local session cleared | Browser must re-authenticate at AS |
| 22 | Restarting Authorization Server using temporary key | Old tokens may fail verification; this is a lab limitation |

## 12. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No ID Token | Client did not request `openid` or OIDC is not enabled | Check scopes and `.oidc(...)` |
| Discovery missing UserInfo endpoint | OIDC is disabled or endpoint not configured | Check OIDC configurer and metadata |
| Discovery missing end-session endpoint | Logout endpoint not enabled or unsupported version | Check `.logoutEndpoint(...)` and SAS version |
| Portal A logs in but Portal B asks for password | Different issuer/host, AS cookie not sent, or session expired | Use the same issuer/host, check cookies and session |
| Portal B gets redirect_uri error | URI in RegisteredClient does not match callback | Compare scheme, host, port, and path exactly |
| Invalid client at token endpoint | Wrong client_id/secret or mismatched authentication method | Check configuration on both sides and PasswordEncoder |
| ID Token missing name/email | Scope not granted or customizer not adding claims | Check authorized scopes and profile service |
| UserInfo returns 401 | Missing access token, expired token, or wrong bearer token | Send valid access token in Authorization header |
| UserInfo missing expected claims | Mapper filters by scope or profile lacks data | Check authorized scopes and profile mapping |
| UserInfo subject differs from ID Token subject | Unstable principal/subject mapping | Use the same immutable subject across both flows |
| Logout only exits the portal | Portal is using default local logout | Configure the OIDC logout success handler |
| Logout redirect rejected | post_logout_redirect_uri is not registered accurately | Declare the matching URI in RegisteredClient |
| AS logout done but other portal stays logged in | Other portal still has a local session | Locally log out that portal or implement front/back-channel logout |
| Old tokens fail after restart | Lab signing key was regenerated | Use persistent key storage outside the lab environment |

## 13. Extension Exercises

1. Replace `InMemoryUserDetailsManager` with a database-backed user store and use an immutable user ID as `sub`.
2. Replace `DemoUserProfileService` with a tenant-aware profile service.
3. Only emit the `email` claim when the email has been verified.
4. Enable consent and build a consent page for users to choose scopes.
5. Enable refresh token rotation and test replay detection.
6. Migrate `RegisteredClientRepository` and `OAuth2AuthorizationService` to JDBC.
7. Store signing keys in a KMS/HSM and test key rotation with multiple `kid`s.
8. Add front-channel or back-channel logout for relying parties needing synchronized logout.
9. Enforce re-authentication for sensitive operations using `prompt=login` or `max_age` per policy.
10. Add integration tests verifying the ID Token, UserInfo subject binding, and end-session redirect.

## 14. Lab Completion Checklist

- [ ] Authorization Server starts on port 9000.
- [ ] Discovery metadata has the correct issuer.
- [ ] OIDC is enabled and the UserInfo endpoint is published.
- [ ] The logout endpoint is published if supported by the version.
- [ ] JWKS contains the public key matching the ID Token signing key.
- [ ] Both relying parties are registered with their own redirect URIs.
- [ ] Both clients use authorization code and PKCE.
- [ ] Portal A logs in successfully and displays ID Token claims.
- [ ] Portal B achieves SSO in the same browser without prompting for the password again.
- [ ] Audiences of the two ID Tokens match each respective client.
- [ ] UserInfo is called with an access token and `sub` matches the ID Token.
- [ ] Profile/email claims are restricted by scope.
- [ ] Local logout and RP-Initiated Logout are tested separately.
- [ ] Post-logout redirect URI is validated against registered values.
- [ ] Understood that each RP's local session does not vanish solely from AS logout.
- [ ] Noted the limitations of in-memory stores and ephemeral signing keys in the lab.

## 15. Self-Assessment Questions

1. Why does an OIDC authorization request require the `openid` scope?
2. How does an ID Token differ from an access token in purpose and audience?
3. Why should `sub` be a stable subject ID rather than an email?
4. Which claims and attributes in an ID Token must a relying party verify?
5. What kind of flaw does nonce protect an OIDC flow against?
6. How does PKCE protect the authorization code?
7. Which token type does the UserInfo endpoint accept?
8. Why must `sub` in UserInfo match the ID Token?
9. When should claims be placed in the ID Token versus returned via UserInfo?
10. Why must claims be filtered by scope/consent?
11. Which browser state allows SSO to work between Portal A and Portal B?
12. Why do the two portals still maintain separate local sessions?
13. How does local logout differ from RP-Initiated Logout?
14. What roles do `id_token_hint` and `post_logout_redirect_uri` play?
15. Why does logging out at the Authorization Server not automatically delete all local sessions across relying parties?
16. Why is generating a new signing key on each restart only suitable for labs?

## References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authentication request, ID Token, UserInfo, and validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): provider metadata and endpoint discovery.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): logout request, `id_token_hint`, and post-logout redirect.
- [Spring Authorization Server — OpenID Connect 1.0](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html#oidc-user-info): configuring OIDC and the UserInfo endpoint.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent, and persistence services.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): configuring relying parties and OIDC login.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized clients, and token access.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWTs and JWK Sets.
