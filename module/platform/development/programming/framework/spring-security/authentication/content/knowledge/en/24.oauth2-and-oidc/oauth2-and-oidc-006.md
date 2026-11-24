# OAuth2UserService, OidcUserService, and Ingesting User Data in Spring Security

## 1. Objectives

When logging in via GitHub, Google, or an enterprise OpenID Provider, a Spring Security application typically needs to **fetch user data from the external system**, identify the corresponding internal account, and assign appropriate access permissions. Two key extension points in **OAuth2 Login on the Servlet stack** are:

- `OAuth2UserService<OAuth2UserRequest, OAuth2User>`: loads user information in non-OIDC OAuth 2.0 login flows.
- `OAuth2UserService<OidcUserRequest, OidcUser>`: loads and adjusts OpenID Connect (OIDC) users, typically via `OidcUserService`.

Understanding these classes lets you customize profile data, link external identities to internal accounts, reject unauthorized users, and inject appropriate `GrantedAuthority` values into `Authentication`. This lesson focuses on **interactive login via `oauth2Login()`**, and does not replace Resource Server validation of Bearer access tokens.

**Core point:** `OAuth2UserService` and `OidcUserService` **do not verify user passwords themselves**; they are invoked during a flow that has already exchanged an authorization code/token with the provider. Never treat an email or display name returned by a provider as a permanent account key.

## 2. Context: From Authorization Code to Application Principal

### 2.1. OAuth 2.0 and OIDC Are Not the Same

OAuth 2.0 is primarily an **authorization protocol** allowing a client to obtain tokens to call protected resources. Spring Security supports logging in through OAuth 2.0 providers that expose a UserInfo endpoint or profile API. OIDC extends OAuth 2.0 with an **identity authentication** layer, including an `ID Token` carrying standard claims.

| Aspect | Standard OAuth2 Login | OpenID Connect Login |
|---|---|---|
| Client registration | Without `openid` scope | Includes `openid` scope |
| Default user loading service | `DefaultOAuth2UserService` | `OidcUserService` |
| Request type | `OAuth2UserRequest` | `OidcUserRequest` (includes ID Token) |
| Principal type | `OAuth2User` | `OidcUser` (also an `OAuth2User`) |
| Identity/profile source | Provider's UserInfo or user API | ID Token; supplemental UserInfo if called/returned |
| Recommended identity key | Provider/registration + provider-stable ID | **`iss` + `sub`** |
| Display name fields | Provider-specific: `login`, `name`, ... | `name`, `preferred_username`, ... |
| Why not use email as the key | Email can be missing, changed, or reused | Email can change; OIDC uses `sub`, stable within an issuer |

Having the `openid` scope in client configuration causes Spring Security to select the OIDC components (such as `OidcUserService`); you cannot turn a plain OAuth2 provider into OIDC simply by casting `OAuth2User`.

### 2.2. Application-Level Login Flow

~~~text
Browser
   |
   | GET /oauth2/authorization/{registrationId}
   v
Spring Security OAuth2 Authorization Request
   |
   | Redirect to Authorization Server / OpenID Provider
   | User signs in / consents at the provider
   v
GET /login/oauth2/code/{registrationId}?code=...&state=...
   |
   v
Spring Security: verify state + exchange code for tokens
   |
   +---------------- Standard OAuth2 ----------------+
   |                                                 |
   | DefaultOAuth2UserService.loadUser(...)          |
   |   calls UserInfo/profile API with access token  |
   |   → OAuth2User(attributes, authorities)         |
   |                                                 |
   +---------------- OIDC ---------------------------+
   |                                                 |
   | Process and validate ID Token per OIDC          |
   | OidcUserService.loadUser(...)                   |
   |   ID Token (+ UserInfo when applicable)         |
   |   → OidcUser(idToken, userInfo, authorities)    |
   |                                                 |
   +------------------+------------------------------+
                      |
                      v
           Custom UserService delegate / mapper
            - look up external identity
            - identify internal account
            - check blocked/disabled
            - load application permissions
                      |
                      v
          OAuth2AuthenticationToken / SecurityContext
                      |
                      v
         authorizeHttpRequests / controller / session
~~~

`OAuth2LoginAuthenticationFilter` completes building the authentication and saves the login state per configuration. A request that already has a valid session **does not necessarily invoke UserService again**: updating permissions, locking internal accounts, and invalidating old sessions must be designed explicitly.

### 2.3. Boundary with Resource Server

- `http.oauth2Login(...)`: the application acts as an **OAuth2 Client** serving browser-logged-in users; uses `OAuth2UserService` / `OidcUserService`.
- `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`: the application validates **Bearer access tokens** sent to APIs; data lives mainly in `Jwt`, `JwtAuthenticationConverter`, or opaque token introspection. Never use `OAuth2UserService` as a substitute for JWT validation.
- A single application can have both, but must define separate security chains, sessions, endpoints, and token audiences.

## 3. `OAuth2UserService`: Fetching User Data for Plain OAuth2

Core interface in Spring Security:

~~~java
public interface OAuth2UserService<R extends OAuth2UserRequest,
                                   U extends OAuth2User> {
    U loadUser(R userRequest) throws OAuth2AuthenticationException;
}
~~~

Meaning:
- `OAuth2UserRequest` provides access to the `ClientRegistration` and newly received `OAuth2AccessToken`; used to know which provider is logging in and which token can call that provider's endpoint.
- `DefaultOAuth2UserService` calls the provider's UserInfo endpoint with the access token, reads attributes, and returns an `OAuth2User`.
- `OAuth2User.getAttributes()` is a `Map<String,Object>` whose structure is **not uniform** across providers. Fields for name, avatar, email, and id may differ or be absent.
- `OAuth2User.getName()` relies on the provider's `userNameAttributeName` (e.g., `id` for GitHub). This is a provider-returned identifier, **not yet an internal user ID**.
- `OAuth2User.getAuthorities()` holds authorities from Spring/the provider, typically including `OAuth2UserAuthority`, `OAUTH2_USER`, and scope authorities like `SCOPE_read:user` depending on configuration/version. A scope granting API access is not synonymous with a business role like `ROLE_ADMIN`.

**Precondition:** A provider without an ID Token must offer a reliable way to fetch user info and a user key from the configured endpoint/API. Without a properly configured name attribute or a well-formed UserInfo response, the service may fail authentication.

### Example Data from a Non-OIDC Provider

~~~json
{
  "id": 123456,
  "login": "alice-dev",
  "name": "Alice Nguyen",
  "email": null,
  "avatar_url": "https://images.example.org/u/123456.png"
}
~~~

Here `id` is more reliable than `login` for linking accounts if the provider guarantees a stable ID. `email=null` is completely valid when the provider does not expose an email. Do not require every provider to supply `email`.

## 4. `OidcUserService`: Combining ID Token and UserInfo Semantically

`OidcUserService` implements `OAuth2UserService<OidcUserRequest, OidcUser>`. `OidcUserRequest` contains client details, access token, and `OidcIdToken`; `OidcUser` extends `OAuth2User`, providing:

- `getIdToken()`: the ID Token already processed/validated by the OIDC flow before being passed to the service.
- `getUserInfo()`: supplemental info from UserInfo **if present**; may not be fetched/returned in some flows or providers.
- `getClaims()` / `getAttributes()`: combined data, potentially including `sub`, `name`, `email`, `email_verified`, etc.
- `getSubject()`: the `sub` value of the authenticated identity.

**OIDC keys identity by the pair `(iss, sub)`**:
- `iss` = the OpenID Provider's issuer, e.g., `https://idp.example.org`.
- `sub` = Subject identifier within that issuer's namespace.
- `email`, `preferred_username`, and `name` are **profile attributes**, not permanent primary keys.

Example validated ID Token:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "user-001",
  "aud": "client-123",
  "exp": 1893456000,
  "iat": 1893452400,
  "name": "Alice Nguyen",
  "email": "alice@example.org",
  "email_verified": true
}
~~~

The `exp`/`iat` numbers only illustrate token data, **not a token usable for testing login**. In reality, signature, key, issuer, audience, timestamps, nonce, and flow bindings must be verified per specification; let Spring Security perform full validation rather than trusting unverified JSON.

### UserInfo Must Share the Same `sub`

OIDC requires the UserInfo Response to contain `sub`. When calling UserInfo, **UserInfo's `sub` must equal the ID Token's `sub`** before accepting UserInfo claims, preventing token substitution. The default `OidcUserService` handles Spring's standard checks; custom services should delegate first before reading data and never bypass this check.

~~~json
{
  "sub": "user-001",
  "name": "Alice Nguyen",
  "picture": "https://images.example.org/u/user-001.png",
  "locale": "vi"
}
~~~

UserInfo provides claims depending on scopes/consent/provider. **Never assume `getUserInfo()` is always non-null**. If profile data arrives from multiple sources, define a clear precedence policy; never overwrite the `iss`/`sub` identity key with email or display fields.

## 5. Comparing and Choosing Extension Points

| Need | Extension Point | Notes |
|---|---|---|
| Standard OAuth2: fetch UserInfo | `DefaultOAuth2UserService` | Usually sufficient for common providers |
| OAuth2: customize headers/REST when calling UserInfo | `setRequestEntityConverter(...)`, `setRestOperations(...)` | Configure secure token/TLS/error handling |
| OAuth2: adjust attributes, link accounts, assign roles | Delegate `OAuth2UserService<OAuth2UserRequest, OAuth2User>` | Return a valid `OAuth2User` |
| OIDC: process profile from ID Token/UserInfo | Delegate `OidcUserService` | Preserve `OidcIdToken` and `OidcUserInfo` |
| OIDC: customize how UserInfo is called | `OidcUserService.setOauth2UserService(...)` | Pass an OAuth2UserService as the UserInfo delegate |
| Only map `GrantedAuthority` after user load | `GrantedAuthoritiesMapper` | Lighter if access token and side effects are not needed |
| API accepting Bearer JWTs | `JwtAuthenticationConverter` or Resource Server | Not OAuth2 Login UserService |

Both `userService(...)` and `oidcUserService(...)` are configured under `http.oauth2Login(oauth2 -> oauth2.userInfoEndpoint(...))`. Their **generic types are not interchangeable**. An app with multiple providers can configure both strategies simultaneously.

## 6. Receiving External Data and Mapping to the Internal Domain

### 6.1. Capture Only the Minimal Required Data

An account record may have fields such as:

| System Field | Source / Strategy | Notes |
|---|---|---|
| `user_id` | Internal DB-generated ID | Independent of provider |
| `provider_type` | `oauth2` / `oidc` | Helps separate namespaces |
| `provider_id` | OAuth2 `registrationId` or OIDC `iss` | OIDC prefers the validated issuer |
| `provider_subject` | OAuth2 provider's stable user id or OIDC `sub` | Never use email |
| `display_name` | `name` / `login` claim | May be missing/mutable |
| `email` | Provider claims if needed | Do not assume verified automatically |
| `email_verified` | OIDC claim when present | Not proof of ownership of an entire account |
| `avatar_url` | `picture` / `avatar_url` | Display only under safe URL policy |
| `account_status` | Application DB | `active`, `disabled`, `pending` per business rules |
| `roles` | Application RBAC | Never infer roles from display email/domain |

Link design:

~~~text
external_identity(
  provider_type,
  provider_id,
  provider_subject,
  internal_user_id,
  linked_at,
  last_login_at
)
UNIQUE(provider_type, provider_id, provider_subject)
~~~

The unique constraint and transactions prevent two concurrent login requests from creating two links for one external identity. An internal user can link multiple providers, yet the **account linking** step must be explicitly authenticated (e.g., the user is already signed into the internal account and then verifies the second provider).

### 6.2. Safe Data Ingestion Pipeline

1. **Provider authentication completes**: let Spring handle code/token, OIDC ID Token, state, and protocol checks.
2. **Delegate user loading**: call `DefaultOAuth2UserService.loadUser` or `OidcUserService.loadUser` instead of accepting arbitrary JSON yourself.
3. **Stable identifier**: for OAuth2, read the provider-specific stable ID from `OAuth2User.getName()` per `userNameAttributeName`; for OIDC, read `iss` + `sub`.
4. **Lookup/link account**: search external identity by composite key. Policy may require an already-linked user or conditional JIT provisioning.
5. **Internal checks**: account is not disabled/blocked, tenant is valid, account mapping is unambiguous, and user is allowed into the app.
6. **Controlled profile updates**: write only allowlisted fields, protect user-managed data; handle conflicts, missing/null values, and PII retention.
7. **Build authorities**: load from application RBAC/roles or verified groups/claims under an approved mapping.
8. **Return principal**: construct a new `DefaultOAuth2User` or `DefaultOidcUser` with appropriate authorities; Spring finalizes `Authentication`.

### 6.3. Why Not Auto-Link Solely by Email?

Suppose two sources both return `email=alice@example.org`. That alone does not prove they represent the same identity; emails can be changed, reused, unverified, or belong to another tenant. Auto-merging by email lets someone logging in via a second provider hijack an internal account created via the first provider.

With OIDC, `email_verified=true` may serve as **one condition** inside a product-defined linking flow, yet it never replaces confirmation of the link approved by the account owner. Always use `iss+sub` when identifying a specific OIDC identity.

### 6.4. Distinguishing OAuth2 Scope Permissions from Application Permissions

`SCOPE_read:user` indicates the access token can be used for the provider's corresponding API permission. It is **not equivalent** to `ROLE_USER`, `ROLE_SUPPORT`, or `ROLE_ADMIN` in your system.

Example:
- Provider returns `SCOPE_email`, `SCOPE_profile`.
- App finds an active internal account with role `ROLE_VIEWER`.
- `authorizeHttpRequests(...hasRole("VIEWER"))` checks the **internal role**.
- App does not infer `ROLE_ADMIN` from the word `admin` in an email or from scopes not designed for internal authorization.

## 7. Spring Boot 3.x + Spring Security 6.x + Java 17 Example

This is a **Maven Spring Boot Servlet example** configuring both standard OAuth2 and OIDC branches. It uses a small in-memory account allowlist to demonstrate that **only linked users can sign in**. The IDs/issuers in the allowlist are illustrative data; when running against real providers, replace them with linked records or a production DB.

### 7.1. Dependencies

In a `pom.xml` already declaring an appropriate Spring Boot parent/BOM:

~~~xml
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
~~~

`spring-boot-starter-oauth2-client` brings in `OAuth2UserService`, `OidcUserService`, and `oauth2Login` support. Do not manually declare a `spring-security-oauth2-client` version that diverges from the BOM.

### 7.2. `application.yml`: One OAuth2 Provider and One OIDC Provider

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
          corp:
            provider: corp
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: https://idp.example.org
~~~

- `github`: standard OAuth2; Spring has a GitHub preset, `DefaultOAuth2UserService` handles UserInfo; default principal name is a provider-specific attribute.
- `corp`: OIDC if the real issuer supports discovery and the `openid` scope; Spring configures OIDC UserService.
- `issuer-uri` is the **exact** issuer published by the provider; never invent arbitrary URLs in real systems.
- Redirect URIs must be strictly allowlisted at the IdP/provider. Apps behind a reverse proxy must safely configure base URL/forwarded headers.
- Credentials come from a secrets manager/environment. Never put real `client-secret` values in Git or logs.

### 7.3. `DemoApplication.java`

File `src/main/java/com/example/login/DemoApplication.java`:

~~~java
package com.example.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. `AccountLinkService.java`: Account Linking and Role Assignment Example

File `src/main/java/com/example/login/AccountLinkService.java`:

~~~java
package com.example.login;

import java.util.Collection;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.stereotype.Service;

@Service
public class AccountLinkService {

    // DEMO data. In production use a DB with a unique constraint
    // on (provider type, provider ID/issuer, stable subject).
    private final Map<ExternalKey, Set<String>> allowed = Map.of(
            new ExternalKey("oauth2:github", "123456"),
                    Set.of("ROLE_VIEWER"),
            new ExternalKey("oidc:https://idp.example.org", "user-001"),
                    Set.of("ROLE_VIEWER")
    );

    public Collection<? extends GrantedAuthority> authoritiesFor(
            String source, String externalSubject) {

        if (source == null || source.isBlank()
                || externalSubject == null || externalSubject.isBlank()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_external_identity"));
        }

        Set<String> roles = allowed.get(
                new ExternalKey(source, externalSubject));

        if (roles == null || roles.isEmpty()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("account_not_linked"));
        }

        return roles.stream()
                .map(SimpleGrantedAuthority::new)
                .collect(Collectors.toUnmodifiableSet());
    }

    private record ExternalKey(String source, String subject) {
    }
}
~~~

The IDs in `allowed` are illustrative fixtures. In practice, this class:
- looks up external identity by unique key;
- verifies account status and tenant;
- returns **application-managed** roles/permissions;
- if unlinked, rejects or performs provisioning per an **explicit policy**, without auto-merging by email;
- runs inside a transaction when modifying the DB, with unique constraints and race handling.

Throwing `OAuth2AuthenticationException` lets the login flow treat this as an authentication failure. Do not expose sensitive details to the frontend about whether an account exists or is locked; log safely for operations.

### 7.5. `SecurityConfiguration.java`: Delegating Both UserServices

File `src/main/java/com/example/login/SecurityConfiguration.java`:

~~~java
package com.example.login;

import java.util.LinkedHashSet;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountLinkService links) throws Exception {

        DefaultOAuth2UserService oauth2Delegate =
                new DefaultOAuth2UserService();
        OidcUserService oidcDelegate = new OidcUserService();

        OAuth2UserService<OAuth2UserRequest, OAuth2User> oauth2Users =
                request -> {
                    OAuth2User user = oauth2Delegate.loadUser(request);

                    String registrationId = request
                            .getClientRegistration().getRegistrationId();
                    String externalSubject = user.getName();
                    String nameKey = request.getClientRegistration()
                            .getProviderDetails()
                            .getUserInfoEndpoint()
                            .getUserNameAttributeName();

                    if (nameKey == null || nameKey.isBlank()) {
                        throw new OAuth2AuthenticationException(
                                new OAuth2Error("missing_name_attribute"));
                    }

                    var authorities =
                            new LinkedHashSet<GrantedAuthority>(
                                    user.getAuthorities());
                    authorities.addAll(links.authoritiesFor(
                            "oauth2:" + registrationId, externalSubject));

                    return new DefaultOAuth2User(
                            authorities, user.getAttributes(), nameKey);
                };

        OAuth2UserService<OidcUserRequest, OidcUser> oidcUsers =
                request -> {
                    OidcUser user = oidcDelegate.loadUser(request);

                    String issuer = Objects.toString(
                            user.getIdToken().getClaims().get("iss"), "");
                    String subject = user.getSubject();

                    if (user.getUserInfo() != null &&
                            !Objects.equals(
                                    subject,
                                    user.getUserInfo()
                                            .getClaims().get("sub"))) {
                        throw new OAuth2AuthenticationException(
                                new OAuth2Error("userinfo_sub_mismatch"));
                    }

                    var authorities =
                            new LinkedHashSet<GrantedAuthority>(
                                    user.getAuthorities());
                    authorities.addAll(links.authoritiesFor(
                            "oidc:" + issuer, subject));

                    return new DefaultOidcUser(
                            authorities,
                            user.getIdToken(),
                            user.getUserInfo(),
                            "sub");
                };

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().hasRole("VIEWER"))
                .oauth2Login(oauth2 -> oauth2
                        .userInfoEndpoint(userInfo -> userInfo
                                .userService(oauth2Users)
                                .oidcUserService(oidcUsers)))
                .build();
    }
}
~~~

**Point-by-point breakdown:**

1. **Delegate first:** both default `loadUser` methods handle fetching and building the provider's principal. Custom code runs only after that step succeeds; never accept raw JSON from the browser as a user.
2. **OAuth2 stable name:** reads `externalSubject=user.getName()`, requiring `userNameAttributeName` to be configured properly for the provider. Do not apply this by default to arbitrary custom APIs without checking their documentation.
3. **OIDC identity:** `issuer` comes from the ID Token's `iss` claim; `subject` is `sub`. This pair looks up the external identity. Checking UserInfo `sub` provides extra protection when the provider supplies UserInfo.
4. **Account allowlist:** `links.authoritiesFor(...)` grants roles only to linked identities; otherwise login fails. The demo does not auto-create new accounts, so unknown identities receive no roles.
5. **Return the right type:** the OAuth2 branch returns `DefaultOAuth2User` preserving attributes/name attribute; the OIDC branch returns `DefaultOidcUser` preserving the ID Token and UserInfo.
6. **Preserve existing authorities:** `LinkedHashSet` retains existing provider authorities (`OAUTH2_USER`, `OIDC_USER`, `SCOPE_...`) and adds the internal role `ROLE_VIEWER`. Scopes are not converted into admin roles.
7. **Authorization:** `hasRole("VIEWER")` checks `ROLE_VIEWER`; replace with fine-grained per-route rules in real applications.
8. **Session/CSRF:** keeps Spring Security's web login defaults. If altering session, CSRF, cookies, proxy, or CORS settings, analyze them for your architecture; never disable protections just to make a demo run.

In the demo, `https://idp.example.org` and the user IDs are illustrative, so real login depends on the corresponding IdP config and account mapping. This is **source code for a Maven project**, not runnable standalone via `javac SecurityConfiguration.java` without dependencies.

### 7.6. Endpoint Inspecting the Received Principal

File `src/main/java/com/example/login/WhoAmIController.java`:

~~~java
package com.example.login;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    Map<String, Object> me(Authentication auth) {
        return Map.of(
                "principalName", auth.getName(),
                "roleViewer", auth.getAuthorities().stream()
                        .anyMatch(a -> "ROLE_VIEWER"
                                .equals(a.getAuthority())));
    }
}
~~~

If a linked account signs in successfully, the response looks like:

~~~json
{
  "principalName": "user-001",
  "roleViewer": true
}
~~~

With GitHub, `principalName` is the provider ID (e.g., `123456`), whereas OIDC uses `sub`. JSON key order is not guaranteed. Endpoints should avoid returning raw `getAttributes()`, ID Tokens, access tokens, or personal claims directly to clients.

Run the project with a Spring Boot parent/BOM and real provider declared using `mvn spring-boot:run` or `mvn package` followed by `java -jar target/<jar-name>.jar`. Login initiation URLs are typically `/oauth2/authorization/github` or `/oauth2/authorization/corp`; default callback is `/login/oauth2/code/{registrationId}`.

## 8. When to Customize `DefaultOAuth2UserService` / `OidcUserService`?

### 8.1. Only Adding Roles: Consider `GrantedAuthoritiesMapper`

If you only convert existing authorities into application authorities without calling additional APIs or updating a DB, you can use:

~~~java
.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(userInfo -> userInfo
                .userAuthoritiesMapper(authorities -> {
                    // Example: keep authorities unchanged.
                    return authorities;
                })))
~~~

This is a **configuration snippet placed inside `HttpSecurity`**, not a standalone Java file; verify mapping policies before replacing `authorities` with other roles. `GrantedAuthoritiesMapper` receives `OAuth2UserAuthority` or `OidcUserAuthority`, but does not receive `OAuth2UserRequest` and the access token the way UserService does; if you must call a protected API to load groups, a UserService delegate is usually a better fit.

### 8.2. Customizing OAuth2 UserInfo Requests

`DefaultOAuth2UserService` provides:
- `setRequestEntityConverter(...)` to customize how the HTTP request to UserInfo is constructed;
- `setRestOperations(...)` to supply a `RestOperations` configured with timeouts/error handling.

Preserve bearer access token transmission and TLS trust; never inadvertently expose tokens in query strings, untrusted redirects, or logs.

### 8.3. Customizing How OIDC Fetches UserInfo

If you only need to change how OIDC retrieves UserInfo while keeping ID Token verification and OIDC principal creation, use:

~~~java
DefaultOAuth2UserService userInfoLoader =
        new DefaultOAuth2UserService();

OidcUserService oidcService = new OidcUserService();
oidcService.setOauth2UserService(userInfoLoader);
~~~

This snippet illustrates the APIs imported from `org.springframework.security.oauth2.client.userinfo` and `...client.oidc.userinfo`. To take effect, register `oidcService` under `.userInfoEndpoint(...).oidcUserService(oidcService)`. A custom `OAuth2UserService` passed to `setOauth2UserService` loads **UserInfo** within OIDC; it does not replace all OIDC login checks.

## 9. Key Rules When Updating User Information

### 9.1. Classifying Data Fields

- **Identity key:** OIDC `iss+sub`, OAuth2 provider registration + stable provider ID. Typically immutable per link; if a provider changes identifiers, apply an authenticated migration/linking procedure.
- **Mutable profile:** `name`, `picture`, `locale`, `nickname`, email. Store intentionally; sync only when the source is marked authoritative and the user consents per policy.
- **Trusted authorization data:** roles from the app DB, or verified groups/claims under an approved contract. An arbitrary string in a response must never become `ROLE_ADMIN` by default.
- **Secrets/tokens:** access token, refresh token, ID Token. Use Spring's `OAuth2AuthorizedClient` / secure storage when calling APIs is required; never store them in profile columns or return them in ordinary JSON.

### 9.2. JIT Provisioning and Linking

Two common policies:

**Linked-only:** accepts only identities already linked to an internal user. Prevents spontaneous account creation; suits enterprises/internal apps.

**Just-in-time provisioning:** after IdP authentication, automatically creates an internal user if belonging to an allowed tenant/org list. Requires strict rules on `iss`, `sub`, `email_verified`, banned users, transactions, unique constraints, rate limiting, and race handling. Never provision `ROLE_ADMIN` based on display name strings or email domains. If the IdP returns an unverified email, never use it to claim ownership of an existing account.

When updating profiles, never overwrite `account_status`, `local_roles`, user-verified internal fields, or critical attributes from untrusted sources. If the provider returns `null`, clear stored values only when policy explicitly requires it, never unconditionally.

### 9.3. Multi-Tenant Contexts

An identity `sub="user-001"` under issuer A is not the same person as `sub="user-001"` under issuer B. In multi-org tenants, check the exact `iss`/tenant, an approved issuer allowlist, audit account linking, and handle tenant changes per policy. Avoid global keys using only `sub`.

### 9.4. Caching, Sessions, and Revoked Permissions

`OAuth2UserService` typically runs at login time, not on every `GET /me`. If an admin locks an account or revokes a role, active sessions may still retain stale authorities. Depending on requirements, apply one or more measures: session invalidation, reauthentication, DB permission checks on sensitive endpoints, bounded session lifetimes, or permission-change event handling. Never assume updating a user in the DB immediately changes the `Authentication` inside active sessions.

## 10. Common Pitfalls

1. **Configuring `.userService(...)` instead of `.oidcUserService(...)` for OIDC login:** the OIDC branch does not use the plain OAuth2 mapper as expected. Check the `openid` scope and configure both services if supporting both provider types.
2. **Using email as the unique ID:** emails change, can be unverified, and are not unique across multiple IdPs. Use `iss+sub` for OIDC and a stable provider ID for OAuth2.
3. **`DefaultOAuth2User` reports missing name attribute:** `userNameAttributeName` is absent from UserInfo. Check the provider schema and `spring.security.oauth2.client.provider.*.user-name-attribute`.
4. **OIDC `getUserInfo() == null` causes NPE:** not every login includes UserInfo; rely on the ID Token for identity and check for null before reading profile fields.
5. **Turning `OidcUser` into `DefaultOAuth2User`:** drops `getIdToken()`, `getUserInfo()`, and OIDC semantics. When changing OIDC authorities, build a `DefaultOidcUser`.
6. **Granting `ROLE_ADMIN` from `email`, `preferred_username`, custom headers, or scopes:** lacks authorization control; map roles from verified sources per app policy.
7. **403 error after login:** login succeeded yet `GrantedAuthority` does not match `hasRole/hasAuthority`; `hasRole("VIEWER")` checks for `ROLE_VIEWER`.
8. **UserInfo returns a `sub` different from the ID Token:** must reject UserInfo and stop merging claims.
9. **Manually calling UserInfo with a browser-supplied token:** bypasses OAuth2 Login validation/trust paths; call via `DefaultOAuth2UserService` or a trusted client with Spring-managed tokens.
10. **JIT provisioning creates duplicate accounts on a race:** requires unique constraints + transactions/idempotency + duplicate handling.
11. **Profile data overwrites internal roles/status:** separate the allowlist of syncable fields from domain fields that IdP profiles cannot modify.
12. **Logging the entire `OidcUser`/`Authentication`:** risks exposing PII and claims; redact logs and never return ID Tokens/access tokens from controllers.
13. **Customizing `RestOperations` breaks TLS or mishandles bearer tokens:** preserve security controls and set timeouts; avoid moving tokens into URLs.
14. **Missing client registration or wrong redirect URI:** errors can occur **before UserService is ever called**; check issuer discovery, client credentials, scopes, callbacks, and reverse proxy config.
15. **Expecting instant role updates:** `Authentication` may remain cached in the session; apply refresh/invalidation policies.
16. **Using Servlet examples in WebFlux:** WebFlux uses `ReactiveOAuth2UserService` and `ServerHttpSecurity` configuration; do not copy Servlet APIs directly.

## 11. Testing the Right Target

### 11.1. Unit Tests for Internal Account Mapping

File `src/test/java/com/example/login/AccountLinkServiceTest.java`:

~~~java
package com.example.login;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import static org.junit.jupiter.api.Assertions.*;

class AccountLinkServiceTest {

    private final AccountLinkService links = new AccountLinkService();

    @Test
    void knownAccountReceivesViewerRole() {
        var roles = links.authoritiesFor("oauth2:github", "123456");
        assertTrue(roles.stream().anyMatch(authority ->
                "ROLE_VIEWER".equals(authority.getAuthority())));
    }

    @Test
    void unknownAccountFailsClosed() {
        assertThrows(OAuth2AuthenticationException.class,
                () -> links.authoritiesFor(
                        "oauth2:github", "unknown-id"));
    }

    @Test
    void sameSubjectAtAnotherIssuerIsNotLinked() {
        assertThrows(OAuth2AuthenticationException.class,
                () -> links.authoritiesFor(
                        "oidc:https://another-idp.example.org",
                        "user-001"));
    }
}
~~~

In a Maven project with all dependencies from section 7, run:

~~~bash
mvn test
~~~

Three tests must PASS with no fixed business stdout; Maven/JUnit prints a summary depending on version. They **only test allowlist logic**, not the OAuth2 flow or token validation with a real IdP.

### 11.2. Testing UserService and the Login Flow

| Test Case | Data / Setup | Expected Result |
|---|---|---|
| OAuth2 provider returns valid linked stable ID | `registrationId`, UserInfo, `getName()` | `OAuth2User` has `ROLE_VIEWER` |
| OAuth2 missing name attribute | Wrong `user-name-attribute` or missing ID | Login fails; does not fall back to email |
| OIDC ID Token with linked `iss+sub` | Valid token, issuer, subject | `OidcUser` preserves ID Token and internal roles |
| OIDC without UserInfo | Only valid ID Token claims | No NPE, identity still keyed by `iss+sub` |
| OIDC UserInfo `sub` mismatch | UserInfo returns another user's subject | Login fails; UserInfo claims discarded |
| Email changes while `iss+sub` stays same | Profile update for same external identity | Does not create a new account |
| Two providers return same email | Different `iss/sub` or stable provider IDs | Does not auto-merge/link accounts |
| `email_verified=false` | UserInfo/ID Token has unverified email | Does not auto-claim another account |
| Account blocked/disabled in DB | Valid external login yet internal policy denies | No authorized session created |
| Provider returns `admin` scope | Scope differs from app role | Does not auto-grant `ROLE_ADMIN` |
| Concurrent logins for one new user | JIT provisioning enabled | Single unique link, atomic/idempotent |
| Invalid state, ID Token signature, audience, or nonce | Stub Authorization Server/IdP | Spring rejects **before** mapping |
| Provider API timeout/error | Slow/failing UserInfo | Login fails safely without bypassing via stale profile |
| Logout, newly revoked permissions | Stale session still exists | Follows session revalidation/invalidation policy |

**Important note:** `SecurityMockMvcRequestPostProcessors.oauth2Login()` and `oidcLogin()` are useful for testing post-login authorization, but they simulate an already logged-in principal; **they do not run code/token exchange or custom UserServices**. To test loading UserInfo/ID Tokens and delegation, unit test your UserService with mocked requests/delegates or run integration tests against an authorization server stub/trusted test IdP.

## 12. Production Deployment Checklist

- [ ] Clearly distinguish OAuth2 Login, OIDC Login, and Resource Server with the right extension points.
- [ ] Provider registrations/issuers and callback URLs are allowlisted; HTTPS is enforced.
- [ ] Keep authorization response `state`, ID Token `iss`/`aud`/`exp`/`nonce`, and signature verification by trusted libraries.
- [ ] When OIDC UserInfo is present, `sub` must match `sub` in the ID Token.
- [ ] Identity linking keys on `iss+sub` or stable provider ID, never email or display name.
- [ ] Request only genuinely needed scopes/claims; secrets/tokens never appear in profile DBs/logs/frontends.
- [ ] `OidcUser.getUserInfo()` may be null; check for missing data and define clear policies.
- [ ] Disabled accounts, tenants, and internal roles fail closed.
- [ ] Account linking/provisioning has unique constraints, transactions, and race tests.
- [ ] Sync only permitted profile fields; separate provider-authoritative fields from user-editable ones.
- [ ] `DefaultOidcUser` preserves ID Token/UserInfo; `DefaultOAuth2User` preserves attributes/name attribute.
- [ ] Monitor login errors, UserInfo timeouts/latency, and safe error codes without leaking account details.
- [ ] Session, role refresh, reauthentication, CSRF, and logout policies fit the application.
- [ ] Unit/integration tests cover existing/non-existing users, multi-provider, changed emails, missing/mismatched UserInfo, wrong roles, and provider outages.

## 13. Takeaways

- `DefaultOAuth2UserService` processes user attributes for **standard OAuth2 Login** from the provider's UserInfo/API.
- `OidcUserService` processes **OIDC Login** with `OidcIdToken` and optional UserInfo.
- Custom services **delegate first**, then map the external identity to an internal account, check status, and assign application authorities.
- OIDC uses **`(iss, sub)`**; other OAuth2 providers use **provider namespace + stable external ID**. Email is merely a profile attribute.
- `SCOPE_...` does not automatically become `ROLE_...`; business permissions require a trusted source.
- Loading data at login does not mean active sessions automatically update when account status or roles change.

## 14. References

1. [Spring Security — OAuth2 Login: Core Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): `ClientRegistration`, provider/UserInfo fields, callbacks, and login configuration.
2. [Spring Security — OAuth2 Login: Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): `userService`, `oidcUserService`, delegation, and `GrantedAuthoritiesMapper`.
3. [Spring Security — OAuth2 (Servlet) Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html): `openid` scope and distinguishing OIDC from OAuth2.
4. [Spring Security API — OAuth2UserService](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/client/userinfo/OAuth2UserService.html): `loadUser` contract.
5. [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): OIDC UserInfo service and delegation.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `sub`, ID Token, and verifying UserInfo `sub` matches ID Token.
7. [Google Identity — OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect): practical guidance against using email as account ID, preferring `sub`.
