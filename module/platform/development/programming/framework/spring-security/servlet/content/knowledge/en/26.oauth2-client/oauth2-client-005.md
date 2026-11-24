# OAuth2UserService, OidcUserService, and External Identity Mapping in Spring Security Servlet

## 1. The problem: an external account differs from an internal account

A Spring MVC application allows users to log in with GitHub, an OpenID Connect (OIDC) provider, or an enterprise identity system. After the IdP authenticates the user, the application receives a profile/claims but still must decide **which internal account this person corresponds to and which permissions they are granted**.

Three responsibilities must be clearly separated:

1. **External authentication:** OAuth2/OIDC login completes the redirect, authorization code exchange, required validations, and profile retrieval. Spring Security handles the protocol steps.
2. **Identity mapping:** From a trusted, stable identifier of the IdP, find or create a **local account ID**. Never merge accounts solely by email or name.
3. **Authorization:** Verify the local account is still active, then load roles/permissions from the application's trusted policy. Never automatically turn an external claim named `admin` into `ROLE_ADMIN`.

For example: GitHub returns `id=817263`, `login=hana-dev`; enterprise OIDC returns `iss=https://login.company.example`, `sub=user-492`. These are **two external identities**. They can belong to the same local account after a valid linking flow, but this cannot be inferred merely because `email` or `name` looks the same.

This lesson focuses on two extension points of **Spring Security Servlet**: `OAuth2UserService` and `OidcUserService`, how to choose the external identity key, how to build a principal that retains the local ID, and how to test mapping logic in a **Java 17+ / Spring Boot 3 / Spring Security 6** application.

**Scope distinction:** `oauth2Login()` is an interactive browser login mechanism to establish a session/principal for a user. It is not an **OAuth2 Resource Server** configuration reading bearer tokens on every API request; a resource server's `JwtAuthenticationConverter` does not replace the two OAuth2 Login user services.

## 2. Where user services sit in the Authorization Code flow

A typical login sequence:

~~~text
Browser             Spring Security Servlet                          IdP
   |                           |                                        |
   | GET /oauth2/authorization/{registrationId}                       |
   |-------------------------->|                                        |
   |                           | Build authorization request, state     |
   |<--------------------------|                                        |
   |==========================> IdP login page ========================>|
   |<========================== Redirect code + state ==================|
   | GET /login/oauth2/code/{registrationId}?code=...&state=...        |
   |-------------------------->|                                        |
   |                           | Verify state, exchange code for token  |
   |                           |--------------------------------------->|
   |                           |<---------------------------------------|
   |                           |                                        |
   |                    +------+-----------------------+                |
   |                    | OAuth2 without OIDC          |                |
   |                    | DefaultOAuth2UserService    | -> OAuth2User   |
   |                    +------------------------------+                |
   |                    | With OIDC (openid scope)     |                |
   |                    | OidcUserService             | -> OidcUser    |
   |                    +------+-----------------------+                |
   |                           |                                        |
   |                  Custom mapping from external key                  |
   |                  -> local account + trusted roles                  |
   |                           |                                        |
   |                  Authentication -> SecurityContext                |
   |<--------------------------|                                        |
   | GET /me (with session cookie)                                      |
   |-------------------------->|                                        |
   |               Application authorization                            |
~~~

Spring Security filters/processors handle the OAuth2 authorization redirect, callback, state, and code exchange. For OIDC, the framework also verifies the ID token against issuer, audience, signature, expiration, and relevant OIDC rules (including nonce where applicable). **A custom `OidcUserService` must not be used to skip ID token validation** or trust JSON data submitted directly by the browser.

After login, `Authentication` is typically `OAuth2AuthenticationToken`; the principal is exposed via `Authentication.getPrincipal()` or `@AuthenticationPrincipal`. OAuth2 authorized clients, access tokens/refresh tokens, and their lifecycles are managed separately. Never use an access token or refresh token as the internal user key.

## 3. How does OAuth2UserService differ from OidcUserService?

| Criterion | OAuth2UserService | OidcUserService |
| --- | --- | --- |
| Flow | Non-OIDC OAuth2 login, e.g. GitHub | OpenID Connect login, typically identified by `openid` scope |
| Input | `OAuth2UserRequest` (client registration, access token) | `OidcUserRequest` (client registration, access token, **ID token**) |
| Output | `OAuth2User`: attributes, authorities, name | `OidcUser`: extends OAuth2User, has ID token/claims/UserInfo |
| Default service | `DefaultOAuth2UserService` | `OidcUserService` |
| Identity key | Provider namespace + stable ID per provider contract | **Issuer (`iss`) + subject (`sub`)** from verified ID token |
| Servlet DSL | `oauth2Login().userInfoEndpoint().userService(...)` | `oauth2Login().userInfoEndpoint().oidcUserService(...)` |

Generic types:

~~~java
OAuth2UserService<OAuth2UserRequest, OAuth2User>
OAuth2UserService<OidcUserRequest, OidcUser>
~~~

`OidcUserService` is a class implementing the generic `OAuth2UserService` interface with OIDC input/output types. Do not treat it as a drop-in replacement for every OAuth2 provider. If the application supports GitHub and an OIDC IdP, configure **both branches** with the appropriate types:

~~~java
// Configuration snippet inside a SecurityFilterChain, not a standalone class:
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(info -> info
        .userService(customOAuth2Users)
        .oidcUserService(customOidcUsers)
    )
);
~~~

OIDC login appearing unchanged when only `.userService(...)` is configured is a common mistake: OIDC has its own branch via `.oidcUserService(...)`.

## 4. Attributes, claims, UserInfo, and tokens differ

### 4.1. Non-OIDC OAuth2 login

`DefaultOAuth2UserService` uses the access token to call the UserInfo endpoint per the matching `ClientRegistration`. The returned JSON becomes `OAuth2User.getAttributes()`. The provider defines the identifier field; the client registration has `userNameAttributeName` so Spring knows which attribute to return from `getName()`.

An illustrative GitHub profile JSON:

~~~json
{
  "id": 817263,
  "login": "hana-dev",
  "name": "Hana",
  "email": null,
  "avatar_url": "https://avatars.example.net/profile.png"
}
~~~

In the GitHub example, `id` serves as the account's stable identifier per contract; `login`, `name`, `email`, and `avatar_url` can change or be missing. A private email may be absent from UserInfo even when login succeeds. Other providers do not necessarily have an `id` key or the same data type; write a matching adapter.

`OAuth2User.getAuthorities()` may contain `OAuth2UserAuthority` from the profile and `SCOPE_...` related to API-calling authorization. Those authorities are **not yet** local business roles. `SCOPE_email` does not mean `ROLE_MEMBER` or `ROLE_ADMIN`.

### 4.2. OIDC login

OIDC adds an **ID token**, typically a JWT with claims:

~~~json
{
  "iss": "https://login.company.example",
  "sub": "user-492",
  "aud": "web-client-id",
  "iat": 1979996400,
  "exp": 1980000000,
  "name": "Hana",
  "email": "hana@example.org",
  "email_verified": true
}
~~~

This payload is **illustrative data only**, not a signed token usable for logging in. Only after the framework verifies the ID token as valid against a trusted IdP should `iss` and `sub` be used as the external key.

`OidcUser` provides `getIdToken()`, `getUserInfo()`, `getClaims()`, `getSubject()`, `getName()`, and other standard accessors. `OidcUserService` may load UserInfo based on metadata, scopes, and provider rules; **`getUserInfo()` can be null**. Even if UserInfo lacks email/name, an ID token with valid `iss/sub` still provides the OIDC identity.

- **ID token**: OIDC identity authentication evidence intended for the client, verified per protocol.
- **Access token**: authorizes the client to call corresponding APIs/resources; not a durable local account ID.
- **Refresh token**: obtains new access tokens per provider policy; not profile data and must never be returned to the UI.
- **UserInfo**: supplementary claims about the user; may be omitted or vary by provider.
- **Profile attributes**: display/sync data; do not use username/email as keys when a stable identity key exists.

In a multi-tenant system, verifying an allowed issuer/tenant is a separate condition. The `email_verified=true` claim does not by itself prove ownership of **an existing internal account**.

## 5. Designing the external identity key and link table

Separate federated identity from the internal account:

~~~text
local_account
    id               UUID / primary key
    status           ACTIVE | SUSPENDED | ...
    authorities      application-managed permissions

external_identity_link
    provider_key     OIDC issuer or OAuth2 provider namespace
    subject          external stable subject
    local_account_id FK -> local_account.id
    UNIQUE(provider_key, subject)
~~~

Example:

| provider_key | subject | local_account_id |
| --- | --- | --- |
| `oidc:https://login.a.example` | `user-17` | `L-101` |
| `oidc:https://login.b.example` | `user-17` | `L-209` |
| `oauth2:github` | `817263` | `L-101`, only if validly linked |

Two OIDC providers with `sub=user-17` do **not** refer to the same person. If a GitHub ID and an OIDC identity both point to `L-101`, there must be an authorized account-linking workflow—**never** auto-merge by email.

**Standard OIDC key: `(iss, sub)`.** Read `iss` and `sub` from the **verified ID token**, preserving exact values per contract. Do not lowercase subjects, strip trailing `/` from issuers, or guess issuers from email domains. Some IdPs use **pairwise subjects**, so the same person may have different `sub` values across different clients/sectors.

**Non-OIDC OAuth2:** the namespace must identify the configured provider/registration. For GitHub, `("oauth2:github", id)` is an example. If there are multiple GitHub Enterprise domains/tenants or internal sources, the namespace must separate along trust boundaries. Never blindly pick an `id` field across providers while dropping the namespace.

**Email is not a safe key:** email can be empty, changed, recycled, unverified, or shared across multiple IdPs. Even a verified email should not automatically link to a privileged account. Linking should require an active valid local account session and re-authentication at the new provider or a dedicated approval workflow.

**Provisioning:** when an external key is not yet in the table, you can create a new local account if the system permits self-signup/JIT, or reject and require an invitation/approval if the application is restricted to pre-authorized users. Use a unique constraint + transaction to handle two concurrent logins; never rely on a naive `find` followed by `insert` without race protection. When a local account is locked, a successful IdP login must **not** re-enable internal access.

## 6. Internal roles and identity mapping: security boundary

A proper pipeline:

~~~text
Trusted configured provider
    |
    +--> OAuth2User/OidcUser from default delegate
    |
    +--> Stable external key
    |      OAuth2: provider-specific id + namespace
    |      OIDC: verified issuer + subject
    |
    +--> ExternalIdentityLinkRepository.find(provider, subject)
    |      or transactional self-provisioning policy
    |
    +--> LocalAccount(id, status, tenant, roles)
    |
    +--> Reject if disabled/blocked/invalid tenant
    |
    +--> Principal retains localAccountId and profile
    |
    +--> Local granted authorities -> AuthorizationFilter
~~~

Clearly separate **profile** from **permissions**: `email`, `preferred_username`, `name`, `picture` serve the UI; `sub`, `iss` serve as keys. A claim like `groups=["admins"]` can only be mapped to a local role when there is an **explicit trust contract and policy**, checking issuer, audience/tenant, claim payload, and administrative approval. Never map an `"admin"` string from an arbitrary profile into `ROLE_ADMIN`.

`getName()` is not always the local account ID: OIDC defaults typically rely on `sub`, while OAuth2 providers usually use an attribute configured on the registration. Best practice is having a dedicated `localAccountId` field on the principal or a clear identity-translation layer. Never mutate `sub` in the ID token or fabricate fake tokens just to force `getName()` to be the local ID.

## 7. Runnable example with Java 17, Spring Boot 3.3.5

This example accepts GitHub OAuth2 login and an environment-configured OIDC IdP, uses the **default delegate services**, and then maps the external identity to a local ID. To focus on the mechanism, the local directory uses a `ConcurrentHashMap` and grants `ROLE_MEMBER` to every new identity. This is a **demo-only self-signup policy**: in real use, replace it with a persistent store, account status checks, approved links, and internal role lookups.

Structure:

~~~text
external-login-demo/
  pom.xml
  src/main/java/example/externallogin/ExternalLoginApplication.java
  src/main/resources/application.yml
  src/test/java/example/externallogin/ExternalLoginApplicationTests.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>external-login-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope: read:user
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Spring Boot includes common provider settings for GitHub. For `company`, Spring can discover metadata from the issuer if the IdP supports standard discovery. You must register **redirect URIs** for both providers, typically locally:

~~~text
http://localhost:8080/login/oauth2/code/github
http://localhost:8080/login/oauth2/code/company
~~~

The program requires **valid** client ID, client secret, and issuer environment variables to start. Do not commit client secrets or tokens to Git. If a reverse proxy sits in front of the app, ensure public scheme/host/port are accurate so wrong redirect URIs are not generated. Interactive login requires a browser and IdP-side configuration; unit tests in Section 8 do not require a real IdP.

### 7.3. Application and custom services

**src/main/java/example/externallogin/ExternalLoginApplication.java**

~~~java
package example.externallogin;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExternalLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExternalLoginApplication.class, args);
    }

    @Bean
    InMemoryIdentityDirectory directory() {
        return new InMemoryIdentityDirectory();
    }

    @Bean("mappedOAuth2Users")
    OAuth2UserService<OAuth2UserRequest, OAuth2User> mappedOAuth2Users(
            InMemoryIdentityDirectory directory) {
        DefaultOAuth2UserService delegate = new DefaultOAuth2UserService();

        return request -> {
            String registrationId =
                    request.getClientRegistration().getRegistrationId();

            if (!"github".equals(registrationId)) {
                throw invalidIdentity(); // Adapter for GitHub only
            }

            OAuth2User external = delegate.loadUser(request);
            Object rawId = external.getAttribute("id");
            String subject = rawId == null ? null : rawId.toString();

            String localId = directory.resolve(
                    new ExternalKey("oauth2:github", subject));

            return new LinkedOAuth2User(
                    external, localId, directory.localAuthorities(localId));
        };
    }

    @Bean("mappedOidcUsers")
    OAuth2UserService<OidcUserRequest, OidcUser> mappedOidcUsers(
            InMemoryIdentityDirectory directory) {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser external = delegate.loadUser(request);
            String issuer = request.getIdToken().getClaimAsString("iss");
            String subject = request.getIdToken().getClaimAsString("sub");

            String localId = directory.resolve(
                    new ExternalKey("oidc:" + require(issuer), subject));

            return new LinkedOidcUser(
                    external, localId, directory.localAuthorities(localId));
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Qualifier("mappedOAuth2Users")
            OAuth2UserService<OAuth2UserRequest, OAuth2User> oauth2Users,
            @Qualifier("mappedOidcUsers")
            OAuth2UserService<OidcUserRequest, OidcUser> oidcUsers)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/error", "/login",
                                "/oauth2/authorization/**",
                                "/login/oauth2/code/**"
                        ).permitAll()
                        .anyRequest().hasRole("MEMBER"))
                .oauth2Login(oauth2 -> oauth2
                        .userInfoEndpoint(info -> info
                                .userService(oauth2Users)
                                .oidcUserService(oidcUsers)))
                .build();
    }

    static String require(String value) {
        if (value == null || value.isBlank()) {
            throw invalidIdentity();
        }
        return value;
    }

    static OAuth2AuthenticationException invalidIdentity() {
        return new OAuth2AuthenticationException(
                new OAuth2Error("invalid_external_identity"),
                "Missing or unsupported external identity");
    }

    record ExternalKey(String provider, String subject) {}

    static final class InMemoryIdentityDirectory {
        private final Map<ExternalKey, String> links =
                new ConcurrentHashMap<>();

        String resolve(ExternalKey key) {
            require(key.provider());
            require(key.subject());
            return links.computeIfAbsent(
                    key, ignored -> UUID.randomUUID().toString());
        }

        List<GrantedAuthority> localAuthorities(String localId) {
            require(localId);
            return List.of(new SimpleGrantedAuthority("ROLE_MEMBER"));
        }
    }

    interface LinkedPrincipal extends OAuth2User {
        String localAccountId();
    }

    record LinkedOAuth2User(
            OAuth2User external,
            String localAccountId,
            List<GrantedAuthority> localAuthorities
    ) implements LinkedPrincipal {

        @Override
        public Map<String, Object> getAttributes() {
            return external.getAttributes();
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return localAuthorities;
        }

        @Override
        public String getName() {
            return external.getName();
        }
    }

    record LinkedOidcUser(
            OidcUser external,
            String localAccountId,
            List<GrantedAuthority> localAuthorities
    ) implements LinkedPrincipal, OidcUser {

        @Override
        public Map<String, Object> getAttributes() {
            return external.getAttributes();
        }

        @Override
        public Map<String, Object> getClaims() {
            return external.getClaims();
        }

        @Override
        public OidcIdToken getIdToken() {
            return external.getIdToken();
        }

        @Override
        public OidcUserInfo getUserInfo() {
            return external.getUserInfo();
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return localAuthorities;
        }

        @Override
        public String getName() {
            return external.getName();
        }
    }

    @RestController
    static class WhoAmIController {

        @GetMapping("/")
        String home() {
            return "Visit /oauth2/authorization/github or " +
                    "/oauth2/authorization/company to sign in";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            LinkedPrincipal principal =
                    (LinkedPrincipal) authentication.getPrincipal();

            return Map.of(
                    "localAccountId", principal.localAccountId(),
                    "externalPrincipalName", principal.getName(),
                    "roles", principal.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .toList());
        }
    }
}
~~~

**Explanation of design decisions in the example:**

- Custom `mappedOAuth2Users` calls `DefaultOAuth2UserService.loadUser(request)` before mapping. Custom `mappedOidcUsers` calls `OidcUserService.loadUser(request)`. These services retain default profile/UserInfo logic and framework authentication steps.
- GitHub identity comes from `id` paired with namespace `oauth2:github`; the adapter rejects other OAuth2 registrations instead of guessing they also have an `id` field.
- OIDC identity comes from `iss/sub` of the verified **ID token** in the request, not relying on `email` or `preferred_username`. `require` rejects null/blank values rather than silently creating accounts with missing keys.
- Both wrappers allow `getName()`/attributes/claims to retain provider semantics while adding `localAccountId()`. Do not alter ID token contents or fabricate fake JWTs.
- `getAuthorities()` on the wrappers only returns local `ROLE_MEMBER`. This is a demo policy to avoid accidentally turning external `SCOPE_*` or `groups` into internal permissions. When the app needs scopes for downstream APIs, design authority combination with **clear boundaries and separation**.
- `hasRole("MEMBER")` checks `ROLE_MEMBER`; real apps must also check local account status, tenant, and per-resource permissions. The demo directory auto-creates new accounts so any identity accepted by either provider receives MEMBER; that is **not** suitable for invite-only systems.
- `/me` only prints the local ID, principal name, and roles for illustration, **never** revealing access token/refresh token/ID token.

In production, replace `InMemoryIdentityDirectory` with a repository having transactions/unique constraints and lookups such as `findLinkedAccount(issuer, subject)`, `checkAccountStatus`, and `loadLocalAuthorities`. Never grant roles based on `String subject="admin"` or a provider-supplied display name.

### 7.4. Running with valid credentials

In Bash/Git Bash:

~~~bash
export GITHUB_CLIENT_ID='your-client-id'
export GITHUB_CLIENT_SECRET='your-client-secret'
export OIDC_CLIENT_ID='your-oidc-client-id'
export OIDC_CLIENT_SECRET='your-oidc-client-secret'
export OIDC_ISSUER_URI='https://your-idp.example/issuer'

mvn spring-boot:run
~~~

These are **sample environment variables**: replace them with real values provided by your IdP, and configure the exact callback URI at both GitHub and the OIDC provider. On PowerShell, use `$env:GITHUB_CLIENT_ID='...'` and corresponding variables. The machine requires Java 17+ and Maven.

Open either URL in a browser to start login:

~~~text
http://localhost:8080/oauth2/authorization/github
http://localhost:8080/oauth2/authorization/company
~~~

After the callback succeeds, open `http://localhost:8080/me` in the **same browser session**. Illustrative response (actual UUID and external name are not fixed):

~~~json
{
  "localAccountId": "f432c5af-9770-48c3-bb5d-18ce8f6b72bd",
  "externalPrincipalName": "817263",
  "roles": ["ROLE_MEMBER"]
}
~~~

Within a single JVM run, the same external key yields the same local ID; changing issuer or subject produces a different local ID. Restarting the demo loses data because the directory lives in memory only. In real applications, identity links must survive restarts and be shared across instances.

`curl -i http://localhost:8080/me` without a login session cookie may redirect to `/login`; this is normal authentication behavior, not an identity mapper bug.

## 8. Testing mapping with JUnit 5 without calling the provider

Use directory logic tests to verify invariants around keys and roles. This test **does not start a Spring context**, so it needs no client secrets or real OIDC discovery to run `mvn test`.

**src/test/java/example/externallogin/ExternalLoginApplicationTests.java:**

~~~java
package example.externallogin;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;

import static org.assertj.core.api.Assertions.assertThat;

class ExternalLoginApplicationTests {

    @Test
    void sameExternalKeyMapsToSameLocalAccount() {
        var directory =
                new ExternalLoginApplication.InMemoryIdentityDirectory();

        var a = new ExternalLoginApplication.ExternalKey(
                "oauth2:github", "817263");
        var b = new ExternalLoginApplication.ExternalKey(
                "oauth2:github", "817263");

        assertThat(directory.resolve(a))
                .isEqualTo(directory.resolve(b));
    }

    @Test
    void identicalSubjectUnderTwoIssuersRemainsSeparate() {
        var directory =
                new ExternalLoginApplication.InMemoryIdentityDirectory();

        var a = new ExternalLoginApplication.ExternalKey(
                "oidc:https://issuer-a.example", "user-17");
        var b = new ExternalLoginApplication.ExternalKey(
                "oidc:https://issuer-b.example", "user-17");

        assertThat(directory.resolve(a))
                .isNotEqualTo(directory.resolve(b));
    }

    @Test
    void externalSubjectNamedAdminDoesNotGrantAdmin() {
        var directory =
                new ExternalLoginApplication.InMemoryIdentityDirectory();

        var external = new ExternalLoginApplication.ExternalKey(
                "oauth2:github", "admin");
        String localId = directory.resolve(external);

        assertThat(directory.localAuthorities(localId).stream()
                .map(GrantedAuthority::getAuthority)
                .toList())
                .containsExactly("ROLE_MEMBER");
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These tests verify that: the same key resolves consistently, the same `sub` under different issuers is not merged, and an external string `admin` does not grant admin permissions. The example code has JUnit/AssertJ dependencies from `spring-boot-starter-test`; do **not** conclude these tests cover the entire OAuth2/OIDC login.

To test the custom user services directly, create a mock delegate returning `OAuth2User`/`OidcUser` with expected claims and verify account lookup, missing IDs, suspended accounts, and returned authorities. To test the real flow, use a test IdP/HTTP mocks, callbacks, sessions, and error handling. `spring-security-test` offers `oauth2Login()` and `oidcLogin()` to inject principals in MockMvc; these post-processors **do not invoke** the real `OAuth2UserService`/`OidcUserService`, so a passing GET 200 test with them does not prove the mapper ran.

## 9. OAuth2User, OidcUser, and keeping local identity in the principal

`OAuth2User` declares `getAttributes()`, `getAuthorities()`, and `getName()`. `OidcUser` extends OIDC data with the ID token and claims. There are three common ways to attach local identity:

1. **Principal wrapper** like `LinkedOAuth2User`/`LinkedOidcUser` in the example: preserves the original profile/token and adds `localAccountId()`, cleanly accessible in controllers.
2. **Customizing attributes** in non-OIDC OAuth2 and returning a new `DefaultOAuth2User`: you can add a server-computed `app_user_id`, but beware of name collisions with provider profiles and maintain the principal contract.
3. **Separating the local lookup service** from the principal: requests read external `iss/sub` or registration + stable user ID and call a service to look up local IDs, with proper caching/persistence. Keeps the principal simple, at the cost of lookup/caching and requiring clear session policies.

For OIDC, you can construct a `DefaultOidcUser` with modified authorities, though it mainly wraps the ID token/UserInfo and name key; if a distinct local id is needed, a wrapper usually expresses the intent more clearly than turning `sub` into the local ID. Never overwrite standard claims `sub`/`iss` or forge a new ID token for programming convenience.

In environments using serialized HTTP sessions or distributed sessions, custom principal objects must be designed to be compatible with session serialization strategies, evolution, and data security. The example record retains the original `OAuth2User` to illustrate the mechanism; depending on your stack/session store, you may need a dedicated serializable principal type or store minimally the local ID and reload profile data.

## 10. Other extensions: GrantedAuthoritiesMapper and success handler

| Hook | Use when | What it does not solve |
| --- | --- | --- |
| `OAuth2UserService` | Loading OAuth2 profile, using provider stable id, resolving account | Does not change OIDC flow unless `oidcUserService` is properly configured |
| `OidcUserService` | Using verified OIDC ID token/UserInfo, resolving `iss/sub` | Does not bypass issuer/audience/signature validation |
| `GrantedAuthoritiesMapper` | Transforming authorities after the user is loaded | May lack enough context to safely create/link local accounts |
| Authentication success handler | Post-login redirects, success auditing, UX handling | Should not be used to bypass account lookup/status checks |
| `OAuth2AuthorizedClientService` | Managing authorized clients and access tokens for external API calls | Does not replace the external identity links table |
| `Authentication.getPrincipal()` | Accessing the login session principal | `getName()` is not automatically the local account ID |

Example of a **Java snippet** when you only need to remap roles and already have a trusted authority source:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(info -> info
        .userAuthoritiesMapper(authorities -> {
            // Fixed example only; in practice look up internal permissions.
            return java.util.List.of(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("ROLE_MEMBER")
            );
        })
    )
);
~~~

The mapper above does not link `iss/sub` to a local ID. For identity mapping, user services and directory lookup remain central. If there are multiple security filter chains, ensure the right chain matches login/callback URLs and configures `oauth2Login`; another chain could block or alter behavior.

## 11. Real-world scenarios requiring explicit decisions

**OIDC login does not return email:** As long as `iss/sub` is valid, the system can still identify the external identity. Email may be a required contact field by business rules, but should not be used as a fallback ID when missing.

**Verified email matches an admin account:** Never auto-grant admin or merge. Link only after the user proves ownership of the internal account or via a trusted administrative workflow. `email_verified` helps assess email control at the IdP, not ownership of an existing local account.

**Changing username/avatar:** Update display attributes only per policy; preserve the stable external key. Profiles belong to the provider; local account IDs must remain stable.

**Changing issuer or migrating providers:** `iss/sub` may change. Perform confirmed, audited migration/linking; never transfer links by email domain without proof.

**Multiple clients of the same IdP:** Some IdPs use pairwise subjects, so `sub` is not necessarily identical across clients/sectors. Design controlled linking capabilities.

**No UserInfo endpoint:** OIDC can use the ID token for identification if required claims are present. Never dereference `getUserInfo()` without a null check.

**Locally locked user:** Successful IdP authentication must not automatically unlock a suspended account. The directory must reject it and grant no local roles.

**Two concurrent logins with the same external key:** Use a unique constraint on `(provider_key, subject)` with transactions and safe duplicate error handling; the demo in-memory map does not replace persistence.

**Provider returns groups/roles:** Map to permissions only if the IdP contract and tenant policy are trusted with change controls. Groups can serve as **input** to reviewed internal rules; never use raw claims as admin permissions.

**Login succeeded but POST returns 403:** OAuth2 login uses sessions and cookies in the browser; POST/PUT/DELETE may still require a CSRF token. CSRF, OAuth2 login, and authorization are distinct mechanisms.

## 12. Debugging each stage of login

| Symptom | Check |
| --- | --- |
| `/oauth2/authorization/github` does not redirect | Client registration, endpoint, selected security filter chain, client ID, login config |
| Callback fails with `state` or redirect mismatch | Callback URI, session cookie, reverse proxy forwarded headers, OAuth2 flow CSRF/state |
| Exchanging authorization code for token fails | Client secret, token endpoint, code validity, PKCE if needed, network and provider policy |
| OIDC reports invalid ID token | Issuer, audience, JWK/signature, expiration, clock skew, nonce |
| `DefaultOAuth2UserService` fails to load profile | UserInfo URI, access token, scope, HTTP status, JSON contract |
| `OidcUserService` cannot find claims | ID token/UserInfo metadata, conditions for calling UserInfo, whether issuer/sub are valid |
| Login rejected by custom service | Provider namespace, missing stable ID, local link, suspended local user |
| Logged in, but `/me` lacks local ID | Principal wrapper, cookie/session, whether custom service is configured on the right branch |
| Logged in, but endpoint returns 403 | Local roles, `hasRole` vs `hasAuthority`, tenant/ownership policy, CSRF on unsafe methods |
| Local id changes after restart | Using in-memory map; need persistent identity link DB |

When debugging, log `registrationId`, verified issuer, **policy-sanitized local account ID or external ID**, processing step name, and appropriate error codes. Avoid logging raw access tokens, refresh tokens, ID tokens, authorization codes, cookies, or full PII profiles. A 403 from authorization differs from authentication/OIDC validation failure; inspect exceptions and security filter logs at an appropriate level.

## 13. Self-check questions

**1.** Why is `iss/sub` better than `sub` alone for OIDC?  
Because a subject only has meaning within an issuer's scope; multiple issuers can issue the same `sub` string.

**2.** GitHub `login` changes while `id` stays the same—should a new local account be created?  
No, when mapped using the GitHub namespace and the provider's stable user ID.

**3.** Customized only `OAuth2UserService`, yet OIDC login still shows the default profile. Why?  
OIDC uses the `OidcUserService` branch in `userInfoEndpoint`; customize the right branch.

**4.** `OidcUser.getUserInfo()` is null, but the verified ID token has `iss/sub`. Can we look up the local link?  
Yes, because the canonical OIDC key comes from the ID token; UserInfo can be absent.

**5.** Does external claim `"groups": ["admins"]` automatically permit `hasRole("ADMIN")`?  
No; you need a trusted policy and permission source, never self-elevating from profile claims.

**6.** Is a provider-verified email matching an existing account's email enough to auto-link?  
No. Linking requires workflow-accepted proof and verification of local account ownership.

**7.** Does a passing `MockMvc.with(oidcLogin())` test prove `OidcUserService.loadUser` was called?  
No; the test helper typically injects the principal into the request without running the full login redirect/token exchange.

**8.** Why should you not use the access token as the local account ID?  
Access tokens authorize resource calls, change with expiration/refresh, and are not stable identity keys.

**9.** Two concurrent login requests for the same provider/subject create two different local accounts. How to fix?  
Design a persistent store with a unique constraint, transactions, and race handling; do not use a naive existence check followed by a separate insert.

## 14. Key takeaways and implementation checklist

- Use `OAuth2UserService<OAuth2UserRequest, OAuth2User>` for **non-OIDC** OAuth2 login and `OAuth2UserService<OidcUserRequest, OidcUser>` / `OidcUserService` for OIDC; register them properly via `oauth2Login().userInfoEndpoint()`.
- Delegate to `DefaultOAuth2UserService` or `OidcUserService` to preserve standard handling; never strip OIDC validations.
- Non-OIDC OAuth2: use **provider namespace + stable provider-specific user ID**. OIDC: use **verified issuer + subject** from the ID token.
- Map to a **durable local account ID** with unique external links and controlled signup/link/unlink workflows. Email and username are for profiles, not automatic account linking.
- Internal roles come from trusted permission policies; check local status and tenant. Do not confuse `SCOPE_` with `ROLE_` or auto-elevate from external claims.
- Keep the local account ID accessible on the principal, protect tokens and personal data, and test missing claims, multi-issuer, disabled users, concurrency, session/callbacks, and real IdP interactions.
- The `ConcurrentHashMap` sample is only for learning the mechanism; real systems use a database, transactions, auditing, and account-takeover protections.

**Conclusion:** The IdP and Spring Security verify the **external identity**; `OAuth2UserService`/`OidcUserService` are the extension points to map that identity to the **internal account and permissions** controlled by your application.
