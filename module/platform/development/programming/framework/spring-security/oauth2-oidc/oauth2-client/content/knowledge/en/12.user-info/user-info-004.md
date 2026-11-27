# 12.4. User-name-attribute and Choosing the Principal Identifier

## 1. The Problem: Who Should the Application Call the User After OIDC Login?

Suppose an **Employee Portal** application is built with **Spring Boot** and **Spring Security OAuth 2.0 Client**. A user chooses to sign in via the company's OpenID Provider (**OP**). After the Authorization Code Flow completes, the application receives user information:

~~~json
{
  "sub": "a1c9f22b-8b27-41d7-84e1-0cd741df7a60",
  "preferred_username": "minh.nguyen",
  "name": "Nguyễn Văn Minh",
  "email": "minh.nguyen@example.test",
  "email_verified": true
}
~~~

So which value should the application use when calling `Authentication.getName()`, storing in the users table, or displaying in the UI?

- `sub` is the **subject identifier** issued by the OP.
- `preferred_username` is often convenient for display or lookup.
- `email` is a contact address; it can change or be reused depending on policy.
- `name` is the user's display name; it can collide across multiple people.

If you confuse **display name**, **Spring Security principal name**, and the **internal identifier used for account linking**, the system can develop hard-to-detect bugs: duplicate accounts when email changes, two people wrongly merged because of identical names, issued tokens unable to be looked up by principal name, or logins from two IdPs wrongly equated.

In Spring Security, the **`user-name-attribute`** property selects **the attribute used as the principal name** when building `OAuth2User`/`OidcUser`. However, it is **not** a mechanism for automatic identity verification, internal account linking, or authorization.

> Examples use **Java 17+, Spring Boot 3, and Spring Security 6** for a **Servlet/Spring MVC** web application signing in via OIDC. Addresses, IDs, and claims are illustrative data only. For real systems, verify the claims, scopes, and contract of the chosen IdP.

## 2. Distinguishing Four Easily Confused Concepts

| Concept | Example | Role |
|---|---|---|
| **Principal object** | `OidcUser`, `OAuth2User` | Object representing the authenticated user in Spring Security |
| **Principal name** | Result of `Authentication.getName()` | Identifier string that many Spring Security components read for logging or looking up authorized clients |
| **External identity key** | `(iss, sub)` pair | Stable linking key between the OP account and the application account |
| **Display name** | `Nguyễn Văn Minh` or `minh.nguyen` | Information shown in the UI; often mutable |

During an OIDC login, the **principal name** may default to `sub`, while the **display name** is taken from `name` or `preferred_username`. The two values do not need to be the same.

If the Employee Portal has its own database, the application can also assign an **internal user ID**, such as a UUID in the `users` table. That internal ID does not need to match the principal name or the IdP's `sub` either.

~~~text
OIDC Provider
  iss = https://login.example.test/realms/company
  sub = a1c9f22b-8b27-41d7-84e1-0cd741df7a60
           │
           │ identity mapping after authentication
           ▼
Employee Portal
  users.id = 8dc7... (internal UUID)
  display_name = "Nguyễn Văn Minh"
           │
           ▼
Application uses internal user ID for business logic
~~~

**Foundational takeaway:** never use the display name as a substitute for the authentication/identity-linking key.

## 3. OAuth2User, OidcUser, and Authentication.getName()

On the Servlet stack, after Spring Security OAuth2 Login succeeds, the request typically has an `Authentication` of type `OAuth2AuthenticationToken`. This Authentication holds the principal and the registration ID of the OAuth Client used.

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String principalName = authentication.getName();

if (authentication instanceof OAuth2AuthenticationToken oauth) {
    String registrationId = oauth.getAuthorizedClientRegistrationId();
    // For example: "company".
}
~~~

During **OIDC** login, the principal is usually an `OidcUser`, such as `DefaultOidcUser`. During OAuth 2.0 login **without the `openid` scope** using OAuth2-style UserInfo, the principal is usually an `OAuth2User` (such as `DefaultOAuth2User`).

The two principal types have key differences:

| Aspect | `OAuth2User` | `OidcUser` |
|---|---|---|
| Purpose | User model based on OAuth2 provider data | OIDC user model based on ID Token and optional UserInfo |
| Principal name API | `getName()` | `getName()` |
| Attributes | `getAttributes()` | OIDC claims, commonly accessed via `getClaims()` |
| ID Token | Not a required component | Has `getIdToken()` |
| UserInfo | Depends on provider and configuration | May have `getUserInfo()` or `null` |
| Subject | Depends on schema/provider | `sub` is a core claim in the ID Token |
| Default name | Requires a name attribute matching the provider | Typically uses `sub` |

### 3.1. Where Does Authentication.getName() Come From?

In a standard configured OAuth2/OIDC login, `OAuth2AuthenticationToken.getName()` reflects the inner principal's name. For `DefaultOidcUser`, `getName()` relies on the configured name key (`nameAttributeKey`); by default, this is usually `sub`.

That means:

~~~java
String valueA = authentication.getName();
String valueB = ((OidcUser) authentication.getPrincipal()).getName();
~~~

In an Authentication holding an `OidcUser` as above, both values represent the same **principal name**. They are **not automatically an email** and **not automatically a full display name**.

### 3.2. Do Not Treat registrationId as User Identity

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` might return `company`. That is the ID of the **OAuth Client registration**, not the user's `sub` and not the `client_id` registered at the IdP.

Example:

~~~text
registrationId : company
client_id      : employee-portal
issuer         : https://login.example.test/realms/company
subject        : a1c9f22b-8b27-41d7-84e1-0cd741df7a60
~~~

Only the last two values, **issuer** and **subject**, form the external OIDC identity key under a sound trust model.

## 4. Data Sources: ID Token, UserInfo, and Application Profile

In the OIDC Authorization Code Flow, the **ID Token** is a token describing a user authentication event at the OP, with claims validated per OIDC rules. Foundational claims include:

- `iss`: the OP's issuer.
- `sub`: the user's subject identifier at the OP.
- `aud`: the intended audience of the ID Token, typically containing the Portal's client ID.
- `exp`, `iat`: timestamps related to token validity.

Depending on scopes, consent, and provider configuration, the ID Token may also carry profile information; however, do not assume every claim like `email` or `name` is always present in the ID Token.

The **UserInfo endpoint** is the OIDC endpoint for fetching additional user information with an appropriate access token. The UserInfo response typically contains `sub`, and may contain `preferred_username`, `email`, `name`, `picture`, etc., per OP policy.

~~~mermaid
sequenceDiagram
    actor User as User
    participant Browser as Browser
    participant Portal as Spring Security OAuth2 Client
    participant OP as OpenID Provider
    participant DB as Portal User Database

    User->>Browser: Start login
    Browser->>Portal: GET /oauth2/authorization/company
    Portal-->>Browser: Redirect to OP
    Browser->>OP: Authentication/consent
    OP-->>Browser: Callback with authorization code
    Browser->>Portal: GET /login/oauth2/code/company?code=...
    Portal->>OP: Exchange code for tokens
    OP-->>Portal: ID Token, access token, ...
    Portal->>OP: GET UserInfo (when configuration/conditions permit)
    OP-->>Portal: Profile claims
    Portal->>Portal: OidcUser has getName() and getClaims()
    Portal->>DB: Look up external identity by (iss,sub)
    DB-->>Portal: Internal user ID
    Portal-->>Browser: Application login session
~~~

**UserInfo is a profile data source**, not an arbitrary identity table where you pick an email and ignore the ID Token. In OIDC, the `sub` value from UserInfo must be consistent with the ID Token's subject; if they do not match, that response must not be attached to the logged-in user.

### 4.1. When Is UserInfo Absent?

Depending on the provider and configuration, Spring Security may not call UserInfo, or the UserInfo endpoint may not be provided/supported, or scopes/consent may disallow certain claims from appearing. Therefore:

- `OidcUser.getUserInfo()` may be `null`.
- `OidcUser.getIdToken()` is the trusted source for `iss` and `sub` of the verified OIDC transaction.
- `email`, `preferred_username`, or `name` may be absent.

Do not design business data on the assumption that **UserInfo always has an email** or that **email is always verified**.

## 5. Spring Security's user-name-attribute Property

In Spring Boot, provider-specific settings have the path:

~~~text
spring.security.oauth2.client.provider.<provider-id>.user-name-attribute
~~~

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

Meaning of the property:

1. Spring Boot binds that value into the corresponding `ClientRegistration.ProviderDetails.UserInfoEndpoint` metadata.
2. The user service processing user information can use this key when creating `DefaultOAuth2User` or `DefaultOidcUser`.
3. The selected value affects the principal name returned by `getName()`, **and does not turn that claim into an additionally verified identity**.

**Do not confuse this:** `user-name-attribute` is the **key name in the claims/attributes set**, not a fixed literal username value. Declaring `user-name-attribute: preferred_username` means taking the **value of the user's `preferred_username` attribute**, not naming every principal the string `preferred_username`.

### 5.1. Default for OIDC

In OIDC, the default key for `DefaultOidcUser` is typically **`sub`**. Since `sub` is a required claim in the ID Token, this is a sensible default for having a principal name tied to the subject.

If the provider is configured with:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            user-name-attribute: preferred_username
~~~

then the user service can select `preferred_username` as the name attribute **if that claim exists in the principal's claims**. If the provider does not return this claim (or only returns it under a different configuration branch), name resolution may not behave as expected. Do not use this property to force an IdP to emit a new claim: **the property only selects a key, it does not grant scopes/claims**.

### 5.2. Provider ID Is Not Registration ID, Even If They Can Match

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

In the example, the **registration ID** is `portal-company`, and the **provider ID** is `company`. The `user-name-attribute` property is placed under **provider.company**, not `registration.portal-company`.

At login, the URL is typically `/oauth2/authorization/portal-company`. The default callback will include the registration ID if the template uses `{registrationId}`.

## 6. Complete OIDC Client Configuration with sub

A practical configuration for Portal:

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

Here:

- **`openid`** indicates the client performs OIDC login.
- **`profile`** and **`email`** request the corresponding OIDC claim groups; the provider still decides whether to release/include them in UserInfo.
- **`user-name-attribute: sub`** chooses the subject as the principal name.
- **`OIDC_CLIENT_SECRET`** must be supplied from the runtime environment/secret manager, not committed.
- **`issuer-uri`** is the OP's identity for Spring Security to use during discovery and verification per configuration.

Minimal dependencies on Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Basic `SecurityFilterChain`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

This is a **server-side session login** application. The default callback is handled by Spring Security at `/login/oauth2/code/company`. There is no need to write your own controller to exchange the authorization code for an ID Token, and never disable CSRF globally just because federated login is used.

## 7. Reading the Principal Properly in a Controller

Spring Security lets you obtain the authenticated principal via `@AuthenticationPrincipal`. Example of an endpoint restricted to logged-in users:

~~~java
package com.example.portal.web;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(
        @AuthenticationPrincipal OidcUser user
    ) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("principalName", user.getName());
        result.put("subject", user.getSubject());
        result.put("displayName", preferredDisplayName(user));
        return result;
    }

    private String preferredDisplayName(OidcUser user) {
        String fullName = user.getFullName();
        if (fullName != null && !fullName.isBlank()) {
            return fullName;
        }
        String preferred = user.getPreferredUsername();
        if (preferred != null && !preferred.isBlank()) {
            return preferred;
        }
        return "User";
    }
}
~~~

In this illustrative endpoint:

- `user.getName()` is the principal name per Spring Security configuration.
- `user.getSubject()` is the OIDC `sub` claim.
- `user.getFullName()` and `user.getPreferredUsername()` are for **display** only.

Never send all of `user.getClaims()`, the ID Token, or the access token directly to the frontend just to display a user's name. Claims may hold personal data and tokens are sensitive credentials.

### 7.1. Which Identifier Should Be Returned to the Browser?

The `/me` endpoint above intentionally returns `subject` so learners can observe it. In production, if the frontend only needs a display name and internal account info, the API should normally return the **internal user ID**, **display name**, and application-permitted permissions/attributes; it does not necessarily need to expose the IdP's `sub`.

**Do not treat the internal user ID as a secret that replaces authorization.** Even if it is a hard-to-guess UUID, every endpoint must still verify that the caller is authorized to read/modify the resource.

## 8. When Should You Not Switch user-name-attribute to email?

A common change:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            user-name-attribute: email
~~~

The author may want `Authentication.getName()` to be more human-readable. The problem is that email **does not carry the same identity guarantees as `sub`**.

### 8.1. Email Can Change

~~~text
January:
  iss = https://login.example.test/realms/company
  sub = u-10293
  email = minh.nguyen@example.test

June:
  iss = https://login.example.test/realms/company
  sub = u-10293
  email = minh.tran@example.test
~~~

This can still be the **exact same user** at the OP. If the application uses email as the primary key for its account-linking table, it easily treats the later login as a new account or loses previously associated business data.

### 8.2. Email Is Not Always Present or Verified

The provider may not return an email; `email_verified` may be false or absent. Even a verified email does not guarantee it will **never change**, **never be reassigned**, or **always be unique across all IdPs**.

### 8.3. Email Can Collide Across Two Issuers

Two identity systems:

~~~text
IdP A: iss=https://login.company-a.test; sub=4582; email=shared@example.test
IdP B: iss=https://login.company-b.test; sub=9901; email=shared@example.test
~~~

**Never automatically merge accounts** solely because emails match. Linking two external identities to the same internal user requires an ownership-verification workflow and explicit application intent.

### 8.4. Principal Name Affects Technical Storage

Some `OAuth2AuthorizedClientService` implementations store authorized clients keyed by **registration ID and principal name**. If the principal name changes from `sub` to `email` or the email changes, authorized client lookup can change accordingly.

Therefore, changing `user-name-attribute` does not merely alter a display string; it can affect sessions, audit logs, lookup of issued tokens, and anything relying on `Authentication.getName()`.

**Recommended choice:** keep a stable identifier for the principal name whenever possible, and read the human-friendly name from a separate profile claim.

## 9. Choosing an Identifier: sub, preferred_username, email, or name?

| Attribute | Advantages | Limitations | Recommended Role |
|---|---|---|---|
| **sub** | Subject issued by OP; not meant for display; scoped to issuer | Can be hard to read; not globally unique without issuer | Primary component of the external identity key |
| **iss + sub** | Distinguishes users by the exact issuer that minted the identity | Requires consistent issuer management, migrations, and schema | External linking key when using OIDC |
| **preferred_username** | Recognizable, often resembles login username | Can change/collide/be absent depending on provider | Display name or suggested username |
| **email** | Useful for contact, search, and notifications | Can change, be reassigned, or be unverified | Profile attribute; linking only with dedicated verification |
| **name** | User-friendly | Non-unique; language/diacritics/formatting vary | Full name for display |
| **Internal user ID** | Managed by the application, independent of IdP | Requires a mapping table and provisioning workflow | Primary key for business data |

None of the claims in the table automatically become a **role/permission**. Spring Security uses **authorities** and authorization policies for access control; the name attribute only determines **how the principal is named**.

## 10. Why Should the External Key Include Both Issuer and Subject?

In OIDC, `sub` is defined **within the scope of the issuer**. Never assume two different issuers cannot issue the same subject string.

Example:

~~~text
Issuer: https://login.company-a.test
Subject: 123456

Issuer: https://login.company-b.test
Subject: 123456
~~~

These two pairs represent **two distinct external identities**.

Recommended data model:

~~~text
ExternalIdentity
  issuer  = https://login.company-a.test
  subject = 123456
  user_id = 8dc7... (internal user)
~~~

With a relational database, you can define tables like:

~~~sql
CREATE TABLE app_user (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(255),
    email VARCHAR(320),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE external_identity (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_ext_identity_user
        FOREIGN KEY (user_id) REFERENCES app_user(id),
    CONSTRAINT uq_ext_identity_iss_sub
        UNIQUE (issuer, subject)
);
~~~

This is an illustrative model, without imposing a specific SQL dialect or UUID storage type. Key ideas:

1. An **internal user** has its own ID used across business data.
2. The `external_identity` table links each external identity to an internal user.
3. The `UNIQUE (issuer, subject)` constraint prevents one external identity from mapping to two users.
4. If multi-IdP linking is needed, multiple external identity rows can point to one internal user **after ownership verification and applying account-linking policy**.

### 10.1. Preserving Issuer/Subject Values

For values received from a framework-verified ID Token:

- Use the issuer **exactly as the trusted IdP identity**, without replacing it with an authorization endpoint URL or shortened domain.
- Treat `sub` as an **opaque string**: do not parse it into an email/username/numeric ID, change case, or strip whitespace arbitrarily.
- Do not normalize the issuer by removing paths, realms, or altering slashes without an explicit policy.
- If an organization migrates issuers/tenants, perform controlled migration/linking instead of assuming `sub` stays unchanged.

**Pairwise subject:** some OPs emit different `sub` values for the same user across different clients or sector identifiers. Thus **issuer+sub** is a good key for the **identity received by this client**, not a universal human identifier shared across every application regardless of OP configuration.

## 11. Obtaining Trusted Issuer and Subject from OidcUser

In a properly configured OIDC application, `OidcUser` provides access to the ID Token:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ExternalIdentityKey(String issuer, String subject) {

    public static ExternalIdentityKey from(OidcUser user) {
        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getIdToken().getSubject();
        return new ExternalIdentityKey(issuer, subject);
    }
}
~~~

When using `ExternalIdentityKey.from(user)`, the application must ensure `user` genuinely comes from an OIDC login flow verified by Spring Security; never construct `OidcUser` from a JSON body sent by a client.

**Why read from the ID Token?** It holds the issuer and subject belonging to the OIDC authentication result verified by the framework. A direct request from a browser sending `{"iss":"...","sub":"..."}` carries no equivalent authentication proof.

The application can additionally store `email`, `preferred_username`, and `name` on the profile for display and update them after each login; however, never use those mutable fields in place of the external identity key.

### 11.1. Do Not Decode JWTs Yourself with Base64

Avoid this workflow:

~~~text
ID Token JWT
  -> Base64 decode payload
  -> extract sub
  -> immediately trust the user is authenticated
~~~

Base64 decoding **does not verify signatures or security claims**. When using standard `oauth2Login()`, rely on the principal constructed by the framework after completing OIDC authentication, while maintaining proper issuer/client registration configuration and keeping Spring Security patched per process.

## 12. Customizing the Principal Name with OidcUserService

In some products, integration requirements dictate that `Authentication.getName()` use `preferred_username` instead of `sub`. You can use `user-name-attribute` if the provider always supplies the matching claim. When **fallback logic** or dynamic selection rules are needed, you can customize the **OIDC user service**.

Spring Security Servlet provides the hook:

~~~java
http.oauth2Login(login -> login
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService))
);
~~~

Example preserving standard user-loading mechanics while only changing the name attribute when the claim is present:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.util.StringUtils;

@Configuration
class CustomOidcPrincipalConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService() {
        OidcUserService delegate = new OidcUserService();

        return userRequest -> {
            OidcUser loaded = delegate.loadUser(userRequest);
            String username =
                loaded.getClaimAsString("preferred_username");

            if (!StringUtils.hasText(username)) {
                // Keep the default principal instead of assigning an empty name.
                return loaded;
            }

            return new DefaultOidcUser(
                loaded.getAuthorities(),
                loaded.getIdToken(),
                loaded.getUserInfo(),
                "preferred_username"
            );
        };
    }
}
~~~

`SecurityFilterChain` configuration using the bean above:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService
    ) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(customOidcUserService)))
            .build();
    }
}
~~~

**This configuration replaces** the `SecurityFilterChain` in Section 6; it is not a second chain to add verbatim to the same application.

Key points:

- The default `OidcUserService` continues to process OIDC UserInfo and construct the principal per Spring Security policy.
- `DefaultOidcUser` is created with `nameAttributeKey = "preferred_username"` when the claim is present.
- When the claim is absent, the loaded principal is kept unchanged; the common default uses `sub`.
- **The issuer and subject in the ID Token do not change** just because the principal name changes.
- Never trust claims sent by the frontend or grant new authorities in the naming step.

**Architectural note:** the principal-name fallback above is a technical example, and does not mean username should be used as a database storage key. If the requirement is simply **showing a friendly name in the UI**, the simpler and safer approach is keeping `getName()` stable and reading `getFullName()` or `getPreferredUsername()` for the UI as in Section 7.

## 13. user-name-attribute with Non-OIDC OAuth2 Login

Not every OAuth 2.0 provider supports OIDC. An OAuth2 provider may expose its own user-info endpoint with a response like:

~~~json
{
  "id": 98765,
  "login": "minhnguyen",
  "display_name": "Minh Nguyen",
  "email": "minh@example.test"
}
~~~

The response has no `sub`. If the registration uses OAuth2 Login without the `openid` scope, Spring Security can construct a `DefaultOAuth2User` from user attributes; in that case, you must specify which attribute acts as the principal name.

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          partner:
            authorization-uri: https://login.partner.example.test/oauth2/authorize
            token-uri: https://login.partner.example.test/oauth2/token
            user-info-uri: https://api.partner.example.test/v1/profile
            user-name-attribute: id
~~~

This is an **example of a custom OAuth2 provider**, not live metadata for a real service. The IdP/Authorization Server must support the user-info endpoint and the corresponding bearer token transmission method.

With a response `{"id":98765,...}`, Spring can select the `id` field as the principal name. Per `DefaultOAuth2User` behavior, the value is converted to a string when retrieving the name.

**Key difference:**

- **OIDC:** has an **ID Token** with `iss`, `sub`, and standard OIDC validation; use the issuer/subject pair to map external identity.
- **Pure OAuth2:** user-info schema depends on the provider. Fields like `id`, `login`, or `username` only carry meaning per provider documentation and are not automatically elevated into an OIDC `sub` claim.

When integrating pure OAuth2, the application must design the external identity namespace (provider ID, trusted issuer/origin, user identifier) based on the contract and provider mutability. Do not force every provider to share the same identity guarantees as OIDC.

### 13.1. Why Is user-name-attribute Needed in Pure OAuth2?

Suppose the response has `id` while the provider does not declare a default schema name. Without selecting a name attribute, `DefaultOAuth2User` cannot be constructed as expected. For custom providers, `user-name-attribute` is usually a key setting telling Spring Security what `getName()` should return.

Match the key name accurately to the JSON: `id` is not equivalent to `user_id` or `username` if the provider does not supply those fields.

## 14. Multiple OIDC Providers: Avoiding Subject Collisions Across Issuers

Suppose Portal supports:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Two providers are configured:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          company:
            issuer-uri: ${COMPANY_ISSUER_URI}
            user-name-attribute: sub
          partner:
            issuer-uri: ${PARTNER_ISSUER_URI}
            user-name-attribute: sub
~~~

This example **replaces** the single-provider configuration in Section 6; do not paste it into the same YAML file with a duplicate `spring.security.oauth2.client` key.

Two principals can both return `getName() = "12345"`:

~~~text
company: iss=https://login.company.example.test, sub=12345
partner: iss=https://login.partner.example.test, sub=12345
~~~

That does not mean they are the same user. When mapping to an internal database, always use **issuer + subject** rather than `Authentication.getName()` alone.

### 14.1. Is It Safe to Auto-Link Two Providers Using Email?

Not by default. Two IdPs have different email registration/verification policies, and an email can be reassigned or belong to another organization over time.

If the application permits **account linking**, require a user already authenticated under one trusted identity to explicitly confirm linking the second identity, or apply an organization-approved administrative process. You may evaluate **email_verified**, issuer, authentication time, and other risk signals, but never treat matching emails alone as sufficient proof for linking.

## 15. User Provisioning / Mapping Workflow on Successful Login

When OIDC login creates `OidcUser`, the application can use a business service to map the external identity to an internal user.

Workflow:

~~~mermaid
flowchart TD
    A["OIDC login succeeds, OidcUser verified"] --> B["Extract iss and sub from ID Token"]
    B --> C{"external_identity(iss,sub) exists?"}
    C -->|Yes| D["Load linked internal user ID"]
    C -->|No| E{"Policy allows auto-creating users?"}
    E -->|Yes| F["Create internal user and external identity in a transaction"]
    E -->|No| G["Require invitation/admin approval or report unauthorized"]
    D --> H["Update allowed profile attributes"]
    F --> H
    H --> I["Use internal user ID for business logic"]
~~~

**Do not use email as the sole condition** in step C. The lookup key is issuer + subject.

Java service code example:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;

@Service
public class IdentityMappingService {

    private final ExternalIdentityRepository externalIdentities;

    public IdentityMappingService(
        ExternalIdentityRepository externalIdentities
    ) {
        this.externalIdentities = externalIdentities;
    }

    public String requireInternalUserId(OidcUser user) {
        ExternalIdentityKey key = ExternalIdentityKey.from(user);
        return externalIdentities
            .findInternalUserId(key.issuer(), key.subject())
            .orElseThrow(() ->
                new IllegalStateException("Account has not been provisioned"));
    }
}
~~~

In this example, `ExternalIdentityRepository` is an application-defined abstraction for database lookup; Spring Security does not pre-create this business repository. The goal is to illustrate **how to use the identity key**, not to present a complete persistence layer.

If an organization allows auto-provisioning, creating the user and external identity should use a transaction, uniqueness constraints, and conflict handling when two login requests arrive concurrently. Never create duplicate accounts simply because two requests both observed "no user yet" before committing.

### 15.1. Display Information Updates Follow Their Own Rules

After finding the internal user, the application may update:

- `display_name` from `name` or `preferred_username`.
- `email` for contact, along with verification status.
- `picture` if policy allows displaying profile photos.

This information can change on every login. If the application allows users to edit their own profiles, define **which source takes precedence** and which fields are synced from the IdP to avoid overwriting valid user edits.

## 16. Email_verified, Scopes, and Claim Trust Levels

OIDC supports profile claims such as `email` and `email_verified`. When using them:

~~~java
String email = user.getEmail();
Boolean emailVerified = user.getEmailVerified();
~~~

evaluate **`emailVerified`** according to actual data, which may be `null` if the claim is not provided. Never infer that an email is verified merely because OIDC login succeeded.

The `email` scope is a **request to access email claims per provider policy**, not a guarantee that every request will receive an email. Similarly, the `profile` scope does not guarantee `name` or `preferred_username` will always appear.

If a workflow requires a verified email (such as sending sensitive notifications), define a handling policy when `email_verified` is absent or false. **Never use `email_verified` as a substitute for authorization checks** on business resources.

### 16.1. Do Not Turn user-name-attribute into an Access Permission

Unsafe example:

~~~java
// Do not authorize using a mutable username string:
if ("admin@example.test".equals(authentication.getName())) {
    // Allow administrative actions
}
~~~

A principal name can be configured from `email` or `preferred_username`; those values can change and are not authorities.

Instead, the system needs **authorization policies** grounded in roles/permissions established from a trusted source via controlled mapping:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasAuthority("PORTAL_ADMIN")
    .anyRequest().authenticated()
);
~~~

Granting `PORTAL_ADMIN` must be managed separately by the application. Setting `user-name-attribute: email` neither creates nor alters authorities.

## 17. Impact on OAuth2AuthorizedClient and Session

After OAuth2 Login succeeds, the application may store an `OAuth2AuthorizedClient` containing the access token and optional refresh token.

Some authorized client storage mechanisms organize data by:

~~~text
clientRegistrationId + principalName
~~~

Example:

~~~text
company + a1c9f22b-8b27-41d7-84e1-0cd741df7a60
~~~

If `user-name-attribute` is later changed to `email`, the principal name might become `minh.nguyen@example.test`. Data looked up under the old name may no longer be found under the same key.

Consequences depending on storage implementation:

- Previously stored authorized clients may not be looked up under the new principal name.
- Token refresh or retrieval on subsequent requests may behave unexpectedly.
- Logs and audits may show two different principal name values for the same user.
- Application logic using `Authentication.getName()` as a data key may see a spurious "new account".

**Changing the name attribute in a running system has operational impact**, not merely a display-name change. Determine the scope of existing data, plan migrations or re-logins, and test thoroughly.

### 17.1. When Principal Name Is sub Across Multiple Providers

If a system has multiple OIDC issuers, `getName()` from two users can have the same `sub` string. For business data, use `(iss,sub)`. For authorized client storage, understand the registration ID, principal name, and storage schema used by your Spring Security version/deployment.

Do not assume the default principal name is already a **system-wide** identity key.

## 18. Customizing Display Name Without Changing Principal Name

In most applications, the goal is displaying "Hello Minh" rather than altering technical identity. You can write a dedicated service for display names:

~~~java
package com.example.portal.profile;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;

@Service
public class DisplayNameService {

    public String getDisplayName(OidcUser user) {
        String name = user.getFullName();
        if (hasText(name)) {
            return name;
        }

        String username = user.getPreferredUsername();
        if (hasText(username)) {
            return username;
        }

        return "User";
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

With this in place, the application preserves:

~~~text
OidcUser.getName()         -> subject (technical principal name key)
DisplayNameService         -> "Nguyễn Văn Minh"
ExternalIdentityKey        -> (issuer, subject)
App User ID                -> internal UUID
~~~

This is a cleaner **separation of concerns** than changing `user-name-attribute` just to get readable names everywhere.

**UI note:** display names read from claims are untrusted input if constructing HTML manually. Template engines/JSON serializers must escape properly to prevent XSS when rendering custom strings in the browser.

## 19. Testing Principal Name with Spring Security Test

Tests in a Servlet application can use `spring-security-test` to mock an OIDC principal and verify that controllers read the right attributes, without performing a real IdP login in every unit test.

### 19.1. Illustrative Controller for Testing

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/identity")
    Map<String, String> identity(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "principalName", user.getName(),
            "subject", user.getSubject()
        );
    }
}
~~~

### 19.2. MockMvc with oidcLogin()

~~~java
package com.example.portal.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class IdentityControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void principalNameDefaultsToSubject() throws Exception {
        mockMvc.perform(get("/identity")
                .with(oidcLogin().idToken(token -> token
                    .claim("sub", "employee-42")
                    .claim("preferred_username", "minh.nguyen"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("employee-42"))
            .andExpect(jsonPath("$.principalName").value("employee-42"));
    }
}
~~~

The MockMvc example creates a mocked principal to test the controller. When running `@SpringBootTest`, the `test` profile still needs to provide or mock beans/configuration required by Spring Security OAuth2 Client at context startup, such as `ClientRegistrationRepository` and matching provider metadata. `oidcLogin()` **does not itself test metadata discovery, ID Token signatures, or the full callback flow**.

### 19.3. Testing Custom nameAttributeKey Selection

You can unit-test how Spring Security represents the principal using `DefaultOidcUser` directly with a mock ID Token containing claims:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;

Instant now = Instant.now();
OidcIdToken idToken = new OidcIdToken(
    "test-id-token-value",
    now,
    now.plusSeconds(300),
    Map.of(
        "iss", "https://login.example.test",
        "sub", "employee-42",
        "aud", "employee-portal",
        "preferred_username", "minh.nguyen"
    )
);

DefaultOidcUser defaultPrincipal = new DefaultOidcUser(
    Set.of(new SimpleGrantedAuthority("OIDC_USER")),
    idToken
);

DefaultOidcUser friendlyPrincipal = new DefaultOidcUser(
    Set.of(new SimpleGrantedAuthority("OIDC_USER")),
    idToken,
    "preferred_username"
);

System.out.println(defaultPrincipal.getName());  // employee-42
System.out.println(friendlyPrincipal.getName()); // minh.nguyen
System.out.println(friendlyPrincipal.getSubject()); // employee-42
~~~

Here the dummy token is for **unit testing the principal model**, and does not represent a verified ID Token from an OP. Key observation: **changing `nameAttributeKey` only changes `getName()`, not the subject in the ID Token**.

Never build a production flow by accepting a raw JWT from a request and instantiating `DefaultOidcUser` manually. In production, the ID Token must be verified by Spring Security through the OAuth2/OIDC login infrastructure.

## 20. Troubleshooting: getName Not Behaving as Expected

| Symptom | Possible Cause | Approach |
|---|---|---|
| `Authentication.getName()` is a long hard-to-read string | Defaulting to `sub` | Keep as technical identifier; read `name` or `preferred_username` for UI |
| Set `user-name-attribute: email` and login fails | `email` claim is absent in the data used by the user service | Verify provider claim release, scopes, and UserInfo/ID Token per policy |
| `preferred_username` is sometimes null | Provider does not always emit this claim | Use a fallback for display name; do not treat it as a required key |
| System creates a new account when user changes email | Application uses email as external identity key | Map by `iss + sub` with controlled migration |
| Two users from different OPs treated as the same account | Using `sub` or email alone as a global key | Combine issuer+subject and verify account linking |
| Login succeeds yet previously stored authorized client not found | Principal name changed, altering storage key | Check name attribute config and repository/service keys |
| `UserInfo.getSubject()` differs from ID Token `sub` | UserInfo response does not belong to the same user/transaction | Reject mismatched response; inspect provider, token, and validation |
| `OidcUser.getUserInfo()` is null | UserInfo not called / no matching data | Use only available claims; do not assume UserInfo always exists |
| API returns 403 even with right username | Insufficient permissions/authorities | Check authorization, scopes, roles; name does not grant access |
| `getName()` changed after editing property | `user-name-attribute` changed the name key | Assess impact on sessions, audits, and authorized client storage |
| OAuth2 provider returns `id` instead of `sub` | Provider is not OIDC | Use provider-specific `user-name-attribute` and dedicated mapping |

When investigating, log only **the structure or names of present claims** and necessary error codes. Never print full ID Tokens, access tokens, refresh tokens, cookies, or sensitive profile data to logs.

## 21. Common Design Mistakes

**Mistake 1 — Using `email` as the user primary key.** Email can change or be reassigned; you need an internal ID and stable external identity mapping.

**Mistake 2 — Assuming `user-name-attribute` verifies identity.** The property only selects which claim serves as the principal name; authentication belongs to OAuth2/OIDC login and framework/provider validation.

**Mistake 3 — Treating display name as technical username.** `name` can collide, be empty, or contain special languages/characters; unsuitable as a system key.

**Mistake 4 — Assuming `sub` is globally unique across the Internet.** Subject must be interpreted within the issuer namespace; multiple OPs can emit the same `sub` string.

**Mistake 5 — Assuming UserInfo always exists and always includes email.** Claim release depends on the provider, scopes, consent, endpoint, and client configuration.

**Mistake 6 — Treating `email_verified` as authorization.** Email verification only reflects email verification status; authorization must check roles/permissions separately.

**Mistake 7 — Changing the principal name to fix the UI.** If the UI needs a friendly name, use a separate display name. Changing the name attribute can affect authorized client storage.

**Mistake 8 — Merging multi-IdP accounts by matching email.** Requires a controlled identity-linking process rather than automatic inference from profile attributes.

**Mistake 9 — Constructing `OidcUser` from client-submitted JSON.** Never trust `iss/sub` strings sent by the browser; the principal must be built after valid OIDC authentication.

## 22. Practical Scenarios

### 22.1. Scenario A: Employee Changes Last Name and Email

Before change:

~~~text
iss = https://login.example.test/realms/company
sub = emp-0042
preferred_username = minh.nguyen
email = minh.nguyen@example.test
~~~

After change:

~~~text
iss = https://login.example.test/realms/company
sub = emp-0042
preferred_username = minh.tran
email = minh.tran@example.test
~~~

**Question:** should you create a new internal user or keep the existing one?

**Solution:** keep the existing internal user if the **issuer+subject** pair remains identical and there is no other reason to invalidate the link. Update profile attributes per policy. Never use an email change to automatically create a new user.

### 22.2. Scenario B: Two OPs Both Have sub=42

~~~text
company: iss=https://login.company.example.test, sub=42
partner: iss=https://login.partner.example.test, sub=42
~~~

**Question:** can a table use `sub` alone as a unique key?

**Solution:** no. Namespace by issuer and enforce the unique constraint on **issuer + subject**. Having two external identities point to the same internal user, if desired, must go through verified account linking.

### 22.3. Scenario C: Users Request a Readable Name in the Header

The application currently displays:

~~~text
Hello a1c9f22b-8b27-41d7-84e1-0cd741df7a60
~~~

**Question:** do you need to set `user-name-attribute: name`?

**Solution:** not required. Keep `getName()` as the stable identifier and display `getFullName()` or `getPreferredUsername()` with a fallback. That avoids unnecessary side effects on authorized client storage and audits.

### 22.4. Scenario D: OAuth2 Provider Does Not Return an ID Token

The provider returns:

~~~json
{"id": 7744, "login": "partner-user", "name": "Partner User"}
~~~

**Question:** what should `user-name-attribute` be set to?

**Solution:** if `id` is the user identifier committed by the provider per its documentation, you can set `provider.partner.user-name-attribute: id` for `OAuth2User`. Do not call that `id` field an OIDC `sub` if the provider does not support OIDC.

### 22.5. Scenario E: Changing Principal Name in a Running System

The development team changes configuration from:

~~~yaml
user-name-attribute: sub
~~~

to:

~~~yaml
user-name-attribute: preferred_username
~~~

**Question:** what must be evaluated before rollout?

**Solution:** beyond verifying the claim is present, check every component using `Authentication.getName()`, existing sessions, authorized client storage keys, audit logs, user-linking tables, and the transition plan. Do not treat this as a mere UI change.

## 23. User Identity and Profile Design Checklist

| Question | Recommended Direction |
|---|---|
| Is the app using OIDC or pure OAuth2 login? | Distinguish by protocol and principal type; do not conflate schemas |
| What is the default principal name? | For OIDC, usually `sub`; verify each provider's configuration |
| Does `user-name-attribute` really need changing? | Change only when there is a clear functional requirement |
| What is the external OIDC linking key? | **Issuer + subject** of the verified principal |
| Should internal users have their own ID? | Yes, an internal primary key independent of IdPs |
| What are name/email/username used for? | Display, contact, search per policy; never assume they are keys |
| Can claims be absent or change? | Yes; design fallbacks and profile-update workflows |
| Is the email verified? | Check `email_verified` when business logic requires it |
| Can multiple IdPs have colliding sub/email? | Yes; use issuer namespacing and verified account linking |
| Does changing name attribute affect storage? | Check `principalName` in authorized client storage/audits |
| Where do roles come from? | From controlled authority/authorization mapping, not name |
| Should all tokens/claims be returned to the UI? | No; return only information the app needs and is allowed to expose |

## 24. Conclusion

In Spring Security OAuth 2.0/OIDC Client, **`user-name-attribute`** specifies **which attribute name is used as the principal name**, affecting what `getName()` returns. For **OIDC**, the default is typically **`sub`**; for **non-OIDC OAuth2 providers**, you may need to declare a key like `id` or `login` based on the provider's UserInfo schema.

**Principal name is not the same as the database user identity key.** For OIDC, use **`(iss, sub)`** from the verified ID Token to identify the external identity, then map it to the application's **internal user ID**. Claims such as **`name`**, **`preferred_username`**, and **`email`** serve profile/display needs and can change; do not use them as primary keys or authorization criteria.

When the requirement is simply a human-friendly display name, keep the principal name stable and build a separate display-name layer. Customize `user-name-attribute` or `OidcUserService` only when genuinely needed, while evaluating the impact on **authorized client storage, sessions, audits, and account linking**. Separating **authenticated identity**, **internal user keys**, and **profile attributes** keeps the Portal consistent across UserInfo, multiple providers, and user-attribute changes over time.
