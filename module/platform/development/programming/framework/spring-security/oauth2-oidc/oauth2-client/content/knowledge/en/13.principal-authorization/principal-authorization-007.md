# 13.7. Custom User Services to Add Business Roles

In **Spring Security OAuth 2.0 / OIDC Client**, logging in successfully with an OpenID Provider (OP) mainly answers the question **who the user is**. However, the application also has to decide **what the user is allowed to do**: view reports, approve orders, edit contracts, or manage accounts. These permissions are often managed in an internal database rather than living inside the identity provider's ID Token or UserInfo.

A suitable integration approach on the **Servlet stack** is creating a **custom user service**: use Spring Security's default service to load and verify the principal, look up business roles using the verified identity, add `GrantedAuthority` instances, and return a new principal. Spring Security will then evaluate those authorities in `SecurityFilterChain` and method security.

This lesson implements the approach completely with **`OidcUserService`** for OIDC and contrasts it with **`DefaultOAuth2UserService`** for non-OIDC OAuth2 Login. The content primarily targets **Spring Boot 3.x / Spring Security 6.x**, using Servlet `SecurityFilterChain` syntax; other versions should verify the corresponding APIs.

## 1. Problem: Authenticate via SSO, Authorize by Application

Suppose a company has an internal portal. Users log in via OIDC at an Identity Provider (IdP). After authentication, the OP issues an ID Token containing identity claims:

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "a83ef2b1",
  "aud": "company-portal",
  "preferred_username": "an.nguyen",
  "email": "an@example.test",
  "email_verified": true
}
```

The application stores business roles separately:

| Issuer | Subject | Internal Roles |
| --- | --- | --- |
| `https://id.example.test/realms/company` | `a83ef2b1` | `VIEWER`, `EDITOR` |
| `https://id.example.test/realms/company` | `b29ac004` | `VIEWER` |
| `https://id.example.test/realms/company` | `c014fa91` | `ADMIN` |

Here, the OP proves the logged-in user is subject `a83ef2b1` from a verified issuer. The portal knows this subject holds the `EDITOR` role because internal administrative data defines it that way.

After login, the application wants these authorities:

```text
OIDC_USER                    # Authority created by OIDC login
SCOPE_openid                 # Granted scope, per Spring Security convention
SCOPE_profile
ROLE_VIEWER                  # Business role in the portal
ROLE_EDITOR                  # Business role in the portal
```

This is an **illustrative set of authorities**, not a guarantee every provider returns those exact scopes and authorities. Internal role names and semantics are managed by the application.

### Why Not Rely Entirely on the ID Token?

The ID Token confirms identity and authentication context, whereas roles like `APPROVER` or `BILLING_ADMIN` may need to be granted, revoked, or scoped to departments by portal administrators. OP roles (if any) do not necessarily correspond to business permissions in the application.

A common design:

```mermaid
flowchart LR
    B["Browser"] -->|"OIDC login"| OP["OpenID Provider"]
    OP -->|"ID Token + Access Token"| APP["Spring Security Client"]
    APP -->|"OidcUserService"| PRINCIPAL["Verified OidcUser"]
    PRINCIPAL -->|"iss + sub"| DB["Business role store"]
    DB -->|"VIEWER, EDITOR"| AUTH["GrantedAuthority: ROLE_*"]
    AUTH --> CHECK["SecurityFilterChain / Method Security"]
    CHECK --> API["Business resources"]
```

**Principle:** identity comes from verified OIDC protocol flows; business permission decisions rely on an authoritative permission source trusted by the application and defined internal policies.

## 2. Distinguishing Authentication, Principal, Authority, Role, and Scope

These terms often appear together in Spring Security yet serve distinct purposes.

| Term | Meaning in the Application | Example |
| --- | --- | --- |
| **`Authentication`** | Authentication result held by Spring Security in `SecurityContext` | `OAuth2AuthenticationToken` |
| **Principal** | Object representing the authenticated user | `OidcUser` or `OAuth2User` |
| **`GrantedAuthority`** | A permission that Spring Security can evaluate | `ROLE_EDITOR`, `SCOPE_orders.read` |
| **Role** | Business permission group defined by the system; can map to an authority | `EDITOR` → `ROLE_EDITOR` |
| **OAuth scope** | Permission granted to an OAuth client when accessing resources via token | `openid`, `profile`, `orders.read` |
| **`SecurityContext`** | Context storing `Authentication` for the request/session | Current user and authorities |

### 2.1. `ROLE_` and `SCOPE_` Are Not Equivalent

In typical configurations:

- `hasRole("EDITOR")` checks for the authority `ROLE_EDITOR`.
- `hasAuthority("ROLE_EDITOR")` checks for the exact string `ROLE_EDITOR`.
- `hasAuthority("SCOPE_orders.read")` checks the corresponding scope authority.
- `hasRole("orders.read")` is not the way to check an OAuth scope.

`ROLE_EDITOR` expresses a permission defined by the **application**. `SCOPE_orders.read` expresses a scope granted to the OAuth client and mapped by Spring Security; it does not prove by itself that the user is allowed to approve every order in the portal's database.

### 2.2. Being Able to Log In Does Not Mean Having Business Roles

A user may present a valid ID Token yet hold no roles in the portal. In that case, **authentication can succeed**, while accessing an endpoint requiring `ROLE_EDITOR` is denied.

The system may choose to:

1. Allow login, permitting access only to pages meant for any authenticated user.
2. Reject login completely if business rules require a valid staff record.
3. Attach a minimal baseline role under an explicitly documented and controlled policy.

Never assume every SSO account automatically gets `ROLE_USER` or `ROLE_ADMIN`. That rule must be an explicit application decision.

## 3. Choosing the Right Extension Point in Spring Security

For Servlet OAuth2 Login, Spring Security supports two primary user service types:

| Login Flow | Common Interface / Implementation | DSL Configuration |
| --- | --- | --- |
| **Standard OAuth2 Login** (no `openid` scope) | `OAuth2UserService<OAuth2UserRequest, OAuth2User>`; `DefaultOAuth2UserService` | `oauth2Login().userInfoEndpoint().userService(...)` |
| **OIDC Login** (with `openid` scope) | `OAuth2UserService<OidcUserRequest, OidcUser>`; `OidcUserService` | `oauth2Login().userInfoEndpoint().oidcUserService(...)` |

In modern Java configuration:

```java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)
        .userService(customOAuth2UserService)));
```

The two services have **different inputs and principal types**. If the application performs OIDC login, replacing only `userService(...)` will usually not intercept the `OidcUser` loading branch.

### 3.1. What Does `OidcUserService` Do?

In the standard OIDC pipeline, before the service is called:

1. Authorization Code Flow was initiated and the callback was correlated to the authorization request.
2. The token endpoint issued a token response.
3. The ID Token was validated by the appropriate OIDC authentication components.

`OidcUserService.loadUser(OidcUserRequest)` can call the **UserInfo Endpoint** using the access token when query conditions apply, process UserInfo claims, and build `OidcUser`. It must also ensure UserInfo's `sub` belongs to the same subject as the ID Token whenever UserInfo is used.

**Always delegate to the standard `OidcUserService` before adding roles.** Manually reading ID Tokens, calling UserInfo yourself, and building principals from unverified JSON can miss critical OIDC requirements.

### 3.2. When Is `DefaultOAuth2UserService` Used?

For non-OIDC OAuth2 Login, `DefaultOAuth2UserService` loads user details from the UserInfo endpoint configured for the provider. The returned `OAuth2User` carries attributes and authorities.

For instance, a plain OAuth2 service may return `id` or `username` as an identifier key. Identifying a stable key that is not arbitrarily reassigned within the provider's namespace is the integration configuration's responsibility; do not assume it carries the same guarantees as OIDC's `(iss, sub)`.

### 3.3. `GrantedAuthoritiesMapper` Is Another Option

Spring Security also provides `GrantedAuthoritiesMapper` via `oauth2Login().userInfoEndpoint().userAuthoritiesMapper(...)`. This fits well when mapping existing authorities to internal authorities, e.g., based on a role claim issued by the OP under a trust contract.

However, if you need to **query a database role table using issuer + subject, inspect account status, or run business logic**, a custom `OidcUserService` is often a clearer extension point because it has access to `OidcUserRequest` and the processed OIDC principal.

If you want new authorities to appear consistently on both `Authentication` and `OidcUser.getAuthorities()`, returning a new `DefaultOidcUser` from the custom service is a clean implementation choice.

## 4. Business Role Data Model

An illustrative database table:

```sql
CREATE TABLE account_role_grant (
    issuer      VARCHAR(512) NOT NULL,
    subject     VARCHAR(255) NOT NULL,
    role_code   VARCHAR(40) NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (issuer, subject, role_code)
);
```

Sample data:

```sql
INSERT INTO account_role_grant (issuer, subject, role_code, enabled)
VALUES
  ('https://id.example.test/realms/company', 'a83ef2b1', 'VIEWER', TRUE),
  ('https://id.example.test/realms/company', 'a83ef2b1', 'EDITOR', TRUE),
  ('https://id.example.test/realms/company', 'b29ac004', 'VIEWER', TRUE);
```

This is a simplified model for the lesson. Production databases may include internal user tables, tenants, per-resource permissions, effective/expiration dates, approvers, and audit history.

**Both `issuer` and `subject` columns must preserve exact case-sensitive matching.** Under OIDC, `sub` is a case-sensitive identifier; if a database uses a case-insensitive collation, choose an appropriate column type/collation or unique key strategy to prevent account collisions.

### Why Not Use Email as the Role Lookup Key?

Email can change, be an alias, be unverified, or be recycled. Two OPs can assign the same email address to two different identities, while pairwise OIDC clients receive different `sub` values for the same person across different sectors.

With a verified OIDC principal, the **`(iss, sub)`** pair is a far better basis for identifying external accounts. If the portal supports linking multiple OPs to one internal account, implement an **authenticated account-linking workflow** rather than auto-merging merely on matching emails.

## 5. Designing the Role Lookup Service

Define valid business roles using an `enum` to avoid turning arbitrary strings from the database into privileged authorities.

```java
import java.util.Set;

// Roles accepted by the portal.
enum BusinessRole {
    VIEWER,
    EDITOR,
    ADMIN
}

interface BusinessRoleLookup {
    Set<BusinessRole> findEnabledRoles(String issuer, String subject);
}
```

The service is the boundary between **OP-authenticated identity** and **portal policy**. It can pull data from PostgreSQL, MySQL, an internal authorization service, or another store.

Example implementation with Spring JDBC:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class JdbcBusinessRoleLookup implements BusinessRoleLookup {

    private final JdbcTemplate jdbc;

    JdbcBusinessRoleLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public Set<BusinessRole> findEnabledRoles(String issuer, String subject) {
        List<String> codes = jdbc.queryForList(
            """
            SELECT role_code
            FROM account_role_grant
            WHERE issuer = ?
              AND subject = ?
              AND enabled = TRUE
            """,
            String.class,
            issuer,
            subject
        );

        Set<BusinessRole> result = new LinkedHashSet<>();

        for (String code : codes) {
            // Fail closed if data contains a role outside the allowed enum.
            result.add(BusinessRole.valueOf(code));
        }

        return result;
    }
}
```

With this code, the database must be configured with an appropriate datasource/JDBC driver and `JdbcTemplate`. `BusinessRole.valueOf(code)` throws an exception on undefined role codes; that is a signal to fix bad data/governance, not a reason to grant broader permissions.

**Distinguish "no roles" from "cannot read roles":**

- No matching rows or all rows disabled: `findEnabledRoles(...)` can return `Set.of()`.
- Database error, timeout, or untrusted result: never fall back to granting `ADMIN` or all roles. The design should withhold permissions or fail login according to your chosen policy.
- Disabled account: you may also need to check `account_status` and block login altogether rather than merely returning an empty role set.

## 6. Complete Example: Custom OidcUserService Adding Roles

We keep the standard `OidcUserService` and append authorities from our internal table. From `OidcUser`, we extract the **verified ID Token's issuer and subject**:

```java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
class BusinessOidcUserConfiguration {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> businessOidcUserService(
            BusinessRoleLookup roleLookup) {

        OidcUserService delegate = new OidcUserService();

        return request -> {
            // 1. Let Spring Security process OIDC UserInfo as usual.
            OidcUser user = delegate.loadUser(request);

            // 2. Identity comes from the verified ID Token.
            String issuer = user.getIdToken().getIssuer().toString();
            String subject = user.getIdToken().getSubject();

            // 3. Look up business roles in the internal system.
            Set<BusinessRole> roles =
                    roleLookup.findEnabledRoles(issuer, subject);

            // 4. Preserve existing authorities (OIDC_USER, SCOPE_...).
            Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(user.getAuthorities());

            // 5. Convert only defined enum roles into ROLE_*.
            for (BusinessRole role : roles) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_" + role.name()));
            }

            // 6. Preserve ID Token, UserInfo, and use sub as the principal name.
            return new DefaultOidcUser(
                    authorities,
                    user.getIdToken(),
                    user.getUserInfo(),
                    "sub");
        };
    }
}
```

**Key steps:**

1. `delegate.loadUser(request)` reuses Spring Security's standard pipeline, including fetching UserInfo when applicable and validating that UserInfo's `sub` matches the ID Token.
2. `user.getIdToken().getIssuer()` and `getSubject()` are the OIDC identity verified per the client registration.
3. `roleLookup` queries the internal authorization source. The app maps only roles within `BusinessRole`.
4. `new LinkedHashSet<>(user.getAuthorities())` keeps existing OIDC login authorities instead of wiping them out.
5. `new SimpleGrantedAuthority("ROLE_" + role.name())` formats roles according to Spring Security convention.
6. `DefaultOidcUser` preserves the ID Token and UserInfo with the merged authority set.

**Never inject access tokens or refresh tokens into the new principal via string concatenation or logs.** Token lifecycles are managed by Spring Security through `OAuth2AuthorizedClient` and its repository/service, not through the role list.

### 6.1. Why Preserve Existing Authorities?

During OIDC login, `OidcUser` may contain `OidcUserAuthority` and `SCOPE_*` authorities. Replacing the entire set with only `ROLE_EDITOR` could strip metadata relied upon by other components.

For the goal of **adding** roles, merging is the sensible approach:

```text
Existing authorities
    +
Internal business roles mapped to ROLE_*
    =
New OidcUser authorities
```

If you intentionally want to strip an existing authority for security policy reasons, treat that as a separate, explicitly designed authorization change rather than an accidental side effect of adding roles.

### 6.2. What Should the Principal Name Be?

This example uses `nameAttributeKey = "sub"` so the OIDC principal name stays stable per subject. That fits common setups. If your app has an existing contract for `OidcUser.getName()` or another custom principal name, maintain that contract intentionally.

**Do not replace `subject` with `email` as the identity key merely because email is easier to read.** Display email or display name in the UI, while keeping permission storage anchored to a trusted identifier.

### 6.3. If UserInfo Is Not Queried

`user.getUserInfo()` can be `null`. `DefaultOidcUser`'s constructor supports principals built from an ID Token with an optional UserInfo; the code does not fabricate UserInfo when the provider omits it.

Do not equate "no UserInfo" with "no user": the verified ID Token still provides `iss` and `sub` for internal role lookup.

## 7. Wiring the Custom Service into SecurityFilterChain

Defining a user service bean **is not always enough** for every OAuth2 Login setup to automatically switch to it. The clear, explicit approach is registering it via `userInfoEndpoint().oidcUserService(...)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser>
                    businessOidcUserService) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/edit/**")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers("/reports/**")
                    .hasAnyRole("VIEWER", "EDITOR", "ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(businessOidcUserService)))
            .build();
    }
}
```

This configuration accomplishes two related tasks:

- **Authentication:** `oauth2Login().userInfoEndpoint().oidcUserService(...)` uses the custom service to construct `OidcUser` with business roles.
- **Authorization:** `requestMatchers` enforce the `ROLE_*` authorities attached by the user service.

Matcher order matters: `/reports/edit/**` is placed before `/reports/**` so the stricter edit rule is evaluated first.

Example for a user holding only `ROLE_VIEWER`:

| HTTP Request | Rule | Expected Outcome |
| --- | --- | --- |
| `GET /reports/summary` | `hasAnyRole("VIEWER", "EDITOR", "ADMIN")` | Allowed |
| `POST /reports/edit/42` | `hasAnyRole("EDITOR", "ADMIN")` | Denied without matching role |
| `GET /admin/users` | `hasRole("ADMIN")` | Denied |
| `GET /account` | `authenticated()` | Allowed if logged in |

**Do not treat `anyRequest().authenticated()` as business authorization for every API.** It only requires an authenticated user; sensitive resources need specific matchers or method security.

## 8. Enforcing Permissions in the Service Layer with Method Security

HTTP authorization protects routes, yet business services are often invoked from multiple entry points: REST controllers, batch jobs, schedulers, or other services. Method security lets you enforce authorities directly on methods:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @PreAuthorize("hasRole('VIEWER') or hasRole('EDITOR') or hasRole('ADMIN')")
    public String viewReport(String reportId) {
        return "Report " + reportId;
    }

    @PreAuthorize("hasRole('EDITOR') or hasRole('ADMIN')")
    public void updateReport(String reportId, String content) {
        // Validate data and apply update.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void configureReportAccess(String reportId) {
        // Only ADMIN role can enter this method.
    }
}
```

With `@EnableMethodSecurity`, Spring Security enforces these annotations via proxies/method interceptors. Keep proxy behavior, self-invocation, and intra-bean calls in mind, as calling a method on `this` inside the same bean can bypass the proxy in standard setups.

### 8.1. Roles Do Not Replace Per-Record Permission Checks

`ROLE_EDITOR` may permit editing reports in general, yet it does not mean the user can edit **every report across every tenant**.

A more realistic expression leverages an authorization service:

```java
@PreAuthorize(
    "hasAnyRole('EDITOR', 'ADMIN') " +
    "and @reportPermission.canEdit(authentication, #reportId)")
public void updateReport(String reportId, String content) {
    // ...
}
```

Here `reportPermission` is an application-implemented business bean. It must check ownership, tenant, record status, or related conditions from a trusted source. The snippet illustrates the principle of combining **role + resource permission**, not a built-in Spring Security bean name.

### 8.2. Role Hierarchy If Business Rules Need Inheritance

If `ADMIN` is allowed to do everything `EDITOR` and `VIEWER` can do, there are two options:

- Explicitly list `hasAnyRole("VIEWER","EDITOR","ADMIN")` in your rules.
- Configure a **`RoleHierarchy`** or policy mechanism defining inheritance.

**Never assume Spring Security automatically treats `ROLE_ADMIN` as implying `ROLE_EDITOR`.** Two distinct authority strings have no hierarchy unless you configure one.

## 9. Reading the Principal and Authorities in Controllers

After successful login, controllers can inspect `OidcUser` and authorities:

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/account/me")
    Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        boolean editor = user.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_EDITOR".equals(authority.getAuthority()));

        return Map.of(
            "authenticated", true,
            "displayName", user.getFullName() == null ? "" : user.getFullName(),
            "canEditReports", editor);
    }
}
```

This endpoint only illustrates reading the data. In real applications, **never rely on the `canEditReports` boolean sent to the frontend to decide whether edits are permitted on the backend**. The frontend can hide or show buttons, while the backend must enforce permissions when handling action requests.

If only roles are needed in a service, `Authentication` or method security usually suffices without passing `OidcUser` through multiple layers.

## 10. Version for Non-OIDC OAuth2 Login

Not every provider supports OIDC. For plain OAuth2 Login, Spring Security uses `DefaultOAuth2UserService` and `OAuth2User`.

Suppose `legacy-provider` returns UserInfo JSON with an `id` field as a stable account identifier:

```json
{
  "id": "legacy-219",
  "display_name": "Nguyen An",
  "email": "an@example.test"
}
```

Configuration must specify the user name attribute:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-provider:
            provider: legacy
            client-id: ${LEGACY_CLIENT_ID}
            client-secret: ${LEGACY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: profile

        provider:
          legacy:
            authorization-uri: https://auth.example.test/oauth2/authorize
            token-uri: https://auth.example.test/oauth2/token
            user-info-uri: https://api.example.test/v1/me
            user-name-attribute: id
```

**Note:** this is **non-OIDC OAuth2 Login**. There is no standard OIDC ID Token; the `id` field is part of the provider's contract and must be evaluated to confirm it is stable enough to serve as an external account key.

### 10.1. Custom `OAuth2UserService`

```java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

@Configuration
class LegacyOAuth2UserConfiguration {

    @Bean
    OAuth2UserService<OAuth2UserRequest, OAuth2User> businessOAuth2UserService(
            LegacyRoleLookup roleLookup) {

        DefaultOAuth2UserService delegate = new DefaultOAuth2UserService();

        return request -> {
            OAuth2User user = delegate.loadUser(request);

            String registrationId =
                request.getClientRegistration().getRegistrationId();
            String externalId = user.getName();

            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(user.getAuthorities());

            for (BusinessRole role :
                    roleLookup.findRoles(registrationId, externalId)) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_" + role.name()));
            }

            String nameAttribute =
                request.getClientRegistration()
                    .getProviderDetails()
                    .getUserInfoEndpoint()
                    .getUserNameAttributeName();

            return new DefaultOAuth2User(
                authorities, user.getAttributes(), nameAttribute);
        };
    }
}

interface LegacyRoleLookup {
    Set<BusinessRole> findRoles(
        String registrationId, String externalId);
}
```

With plain OAuth2, this example uses **`registrationId + externalId`** as the role lookup key. That is only safe if the registration points to a provider with reliable, stable external IDs that are never recycled in ways causing account confusion. If the provider has a formal issuer or tenant namespace, include that in the key rather than trusting a bare ID string alone.

### 10.2. Registering the Corresponding Service

```java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userService(businessOAuth2UserService)));
```

**`userService(...)` and `oidcUserService(...)` are not interchangeable.** An application using both plain OAuth2 and OIDC can configure both while keeping identity mapping rules separate to avoid provider mix-ups.

## 11. When the Provider Already Supplies Group/Role Claims

Some OPs include `groups` or `roles` claims in the ID Token/UserInfo, for example:

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "a83ef2b1",
  "groups": ["employees", "finance-approvers"]
}
```

The application can map groups to internal roles once it clearly defines:

1. Which OP is trusted to issue the claims.
2. Whether the claim comes from a verified ID Token or subject-validated UserInfo.
3. Which group values are valid and which role each maps to.
4. Whether that role is permitted to be asserted by the OP.
5. Revocation rules, claim lifetimes, and additional per-tenant permissions.

Allowlist mapping example:

| Group from Verified OP | Portal Role |
| --- | --- |
| `employees` | `ROLE_VIEWER` |
| `finance-approvers` | `ROLE_EDITOR` |
| `security-admins` | May map to `ROLE_ADMIN` if covered by an explicit trust contract/policy |

Do not write:

```java
// Policy flaw: groups from an arbitrary source turn into arbitrary roles.
String authority = "ROLE_" + incomingGroup.toUpperCase();
```

That could synthesize `ROLE_ADMIN` simply from a matching claim string. **Mapped authorities must come from an allowlist and the claim source must be verified.** For sensitive permissions, many organizations still prefer an internal grants table or independent approval workflow.

## 12. Security Ordering: Verify Identity First, Grant Roles Second

A secure flow can be illustrated as:

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant OP as OpenID Provider
    participant S as Spring Security
    participant USER as OidcUserService
    participant ROLE as BusinessRoleLookup
    participant API as Portal API

    U->>B: Select login
    B->>S: GET /oauth2/authorization/company
    S-->>B: Redirect to OP
    B->>OP: Authorization request
    OP->>U: Authenticate / MFA / consent as needed
    OP-->>B: Callback with code and state
    B->>S: Callback
    S->>S: Verify state; exchange code; verify ID Token
    S->>USER: loadUser(OidcUserRequest)
    USER->>OP: UserInfo with access token (if needed)
    OP-->>USER: UserInfo response
    USER->>USER: Verify UserInfo sub matches ID Token
    USER->>ROLE: findEnabledRoles(issuer, subject)
    ROLE-->>USER: Valid internal roles
    USER-->>S: DefaultOidcUser with ROLE_*
    S-->>B: Login succeeds
    B->>API: Call /reports/edit/42
    API->>S: Check ROLE_EDITOR / ROLE_ADMIN
    S-->>API: Allow or deny
```

Never derive roles from `email`, `groups`, or UserInfo JSON **before proving they belong to the identity that just logged in**.

### 12.1. Never Put Role Lookup Results Into the ID Token

The ID Token is issued and signed by the OP. An application cannot alter the ID Token to inject a `roles` claim while keeping the original signature valid. Adding internal roles belongs in the **principal's `GrantedAuthority` set**, in a policy engine, or in the application's authorization context.

### 12.2. Avoid Updating Data Before Verification

If a custom user service calls UserInfo and immediately writes user profile updates to the database before checking that `sub` matches the ID Token, a mismatch can corrupt the wrong account.

Delegating to the default service helps prevent this bug. If writing a service completely from scratch, preserve the `sub` match check and all other OIDC validations before using claims or granting permissions.

## 13. Handling Errors During Business Role Lookup

There are at least four distinct cases:

| Situation | Response to Consider |
| --- | --- |
| User is authenticated yet has no role rows | Allow login with restricted access or reject login per defined policy |
| Internal account is locked/revoked | Block granting roles; optionally reject login and report account status |
| Role lookup database is failing | Never grant roles by default; fail closed or deny login cleanly |
| Role store returns an unrecognized code | Never ignore and grant elevated rights; raise a data/config error for investigation |

### 13.1. Should a Lookup Failure Fail Login?

There is no single answer for every system:

- For an admin portal requiring permission control immediately at login, an unavailable role lookup may cause **controlled login failure**.
- For a portal with areas needing only authentication without business roles, you may allow login with **zero internal roles** and deny all role-protected actions.
- If role lookup calls an external service, enforce timeouts, retry limits, and circuit breakers so login requests do not pile up indefinitely.

Crucially, **never turn an infrastructure failure into broader privileges**. Returning `ROLE_ADMIN` when a service fails is a severe authorization vulnerability.

### 13.2. Avoid Logging Sensitive Data

When role lookup fails, logs can use configuration labels and internal error codes:

```json
{
  "event": "business_role_lookup_failed",
  "provider": "company",
  "reason": "repository_unavailable",
  "environment": "staging",
  "trace_id": "internal-request-trace"
}
```

Never log raw ID Tokens, access tokens, refresh tokens, client secrets, authorization codes, session cookies, full UserInfo payloads, or raw email/subject broadly. If you need to correlate failures to an account, use a governed internal identifier protected under your data retention policy.

## 14. Do Roles Change After the User Logs In?

When a custom user service attaches `ROLE_EDITOR` to `Authentication`, the authority set is typically a **snapshot at login time**. If an admin revokes `EDITOR` in the database, an active logged-in session is **not automatically updated immediately**.

Example:

```text
09:00  User logs in → ROLE_EDITOR loaded from database
09:15  Admin revokes EDITOR from user
09:16  Current session still holds stale Authentication
```

This is an **authorization freshness** problem, not a bug in `OidcUserService`.

Handling strategies depending on requirements:

- **Short sessions / re-login:** limit how long stale permissions remain valid.
- **Session invalidation/revocation:** when sensitive permissions change, invalidate affected sessions.
- **Live backend permission checks:** for critical actions, use an `AuthorizationManager` or policy service querying the latest role source.
- **Permission version/epoch:** compare current permissions against the session's snapshot and force reload or re-login on mismatch.
- **TTL-bounded cache with invalidation:** improve performance while defining a clear staleness bound.

**Refreshing an access token does not mean Spring Security automatically re-invokes `OidcUserService` to refresh business roles.** Refresh tokens belong to the `OAuth2AuthorizedClient` lifecycle; the session's principal/Authentication has its own lifecycle.

### 14.1. When Roles Change Frequently

If order-approval rights must be revocable immediately, loading roles once at login may not suffice. One solution is using Authentication for identity and checking business policy on each sensitive operation, or using an event-invalidated cache.

Avoid firing hundreds of redundant database role queries inside one request when per-request caching and consistent policies can handle it cleanly. Weigh performance trade-offs alongside revocation requirements.

## 15. Multiple Tenants and Multiple Providers

### 15.1. Separate Identity from Tenant Membership

In a SaaS app, the same user may belong to multiple tenants:

```text
Identity:
  issuer = https://id.example.test/realms/company
  subject = a83ef2b1

Membership:
  tenant-A -> VIEWER
  tenant-B -> EDITOR
```

Here, if the user service attaches a flat `ROLE_EDITOR` to the session, the app could accidentally allow `EDITOR` actions **on tenant-A as well**.

Distinguish between:

- **Global application roles** (e.g., `ROLE_SUPPORT_ADMIN` if truly system-wide).
- **Tenant-scoped roles** (e.g., `EDITOR` only inside `tenant-B`).

For tenant-scoped roles, store memberships and check `(identity, tenant, resource)` in an authorization service rather than flattening every tenant permission into a shared `ROLE_*` string.

### 15.2. Never Trust a Request-Supplied Tenant ID Independently

If an API receives:

```http
POST /tenants/tenant-B/reports/42 HTTP/1.1
Host: app.example.test
```

the backend must verify the user belongs to `tenant-B` and has rights on report 42. Never rely solely on a `ROLE_EDITOR` loaded for another tenant or accept a client-declared `X-Tenant-Id` without verifying membership.

### 15.3. Multi-Provider: Avoid `sub` Collisions

When supporting login via Company OP and Partner OP, two issuers can both assign `sub="123"` to two different people.

```text
Company OP: (iss=https://id.company.example.test, sub=123)
Partner OP: (iss=https://id.partner.example.test, sub=123)
```

Therefore, `BusinessRoleLookup` must use `(iss, sub)` or an internal user ID linked via a trusted workflow. Querying `WHERE subject = ?` alone in a multi-provider app can grant someone else's roles.

## 16. Distinguishing Login-Time Role Enrichment from API Scope Checks

An application can use both OIDC Login and call OAuth Resource Servers. Two distinct authorization planes exist:

1. **Web application authorization:** `SecurityContext` holds `OAuth2AuthenticationToken` with an `OidcUser` principal and business authorities.
2. **API authorization on bearer access tokens:** the Resource Server verifies the access token, scopes/audience, and its own API policies.

Adding `ROLE_EDITOR` to the portal session **does not alter the access token** the portal sends to downstream APIs, nor does it grant `ROLE_EDITOR` on an external Resource Server.

Example:

```text
Portal session:
  ROLE_EDITOR = true

Bearer access token sent to Orders API:
  scope = orders.read
```

Orders API can still reject order writes due to lacking the `orders.write` scope or corresponding permissions. Never treat an internal portal role as proof that downstream APIs allow every action.

When downstream services need user privileges, design appropriate **token exchange, delegation, service authorization, or policy sharing**, rather than copying session authorities into an unsigned bearer token.

## 17. When to Choose `GrantedAuthoritiesMapper` Instead of a Custom User Service?

If role mapping depends solely on **already verified authorities/claims with a trusted contract**, `GrantedAuthoritiesMapper` can be simpler.

Conceptual example:

```text
Verified OIDC group claim:  finance-approvers
             |
             v
Allowlisted mapping in GrantedAuthoritiesMapper
             |
             v
ROLE_FINANCE_APPROVER
```

`userAuthoritiesMapper` can be configured via:

```java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(customMapper)));
```

This is **a different extension point**, not `OAuth2UserService`. With a mapper, pay attention to the order in which it applies to Authentication authorities and how the principal is built; if your app needs the custom principal itself to carry the same authority list or needs to query a database by `iss+sub`, a custom `OidcUserService` is usually easier to keep consistent.

In summary, pick the tool based on the data source and when permissions are needed:

| Need | Approach |
| --- | --- |
| Load roles from internal database right after OIDC login | Custom `OidcUserService` delegating and returning `DefaultOidcUser` |
| Load roles from non-OIDC OAuth2 UserInfo/API | Custom `DefaultOAuth2UserService` |
| Quick mapping of trusted authorities/claims to new authorities | `GrantedAuthoritiesMapper` |
| Decisions depending on record, tenant, or live state | `AuthorizationManager` or policy service at request time |
| Immediate permission revocation required | Session invalidation and/or live backend permission checks |

## 18. Common Mistakes When Writing Custom User Services

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| Bean defined, yet roles never appear | Bean not wired into `oauth2Login().userInfoEndpoint().oidcUserService(...)` | Register explicitly in the right `SecurityFilterChain` |
| `ROLE_EDITOR` missing even though DB returns `EDITOR` | Not mapped to `SimpleGrantedAuthority("ROLE_EDITOR")` | Normalize roles with enum and proper prefix |
| `hasRole("ROLE_EDITOR")` fails unexpectedly | `hasRole` adds the `ROLE_` prefix automatically | Use `hasRole("EDITOR")` or `hasAuthority("ROLE_EDITOR")` |
| Only `SCOPE_profile` present, no business roles | Service kept only default authorities | Call role lookup and merge authorities |
| Works for company users, fails for partner users | Role lookup key used subject only or wrong provider/issuer config | Use `(trusted issuer, sub)` matching the transaction |
| UserInfo `sub` mismatch | Custom service read data for another user or wrong OP/provider | Use standard delegate; reject mismatched UserInfo |
| Role appears on principal, yet has no effect on API | Endpoint actually uses a resource-server token or different chain | Inspect `SecurityFilterChain` and separate session roles from bearer-token authorities |
| Admin revoked role, yet user still acts | Authentication authorities remain from earlier login | Implement revalidation/session invalidation |
| Login succeeds, yet `@PreAuthorize` does not run | `@EnableMethodSecurity` missing or proxy bypassed | Verify method-security configuration and bean invocation |
| New user has zero permissions | Role lookup returns empty, no membership granted | Define clear onboarding/role-grant flow; never default to high privileges |
| `/reports/edit/**` opened, yet `VIEWER` still gets in | Matcher order wrong or only `authenticated()` configured | Place specific matchers before broad ones and add method security |
| Login is slow or times out | Synchronous role lookup to slow database/service | Add timeouts, identity indexes, caching, and fail-closed policy |
| Duplicate roles | Merged authorities in a list with duplicates | Use `Set<GrantedAuthority>` as shown |
| `DefaultOidcUser` loses principal data | Built new principal omitting ID Token/UserInfo/name attribute | Preserve token claims and appropriate identity attribute |

### 18.1. Anti-Pattern: Granting `ADMIN` When Role Lookup Fails

```java
// WRONG: database failure grants highest privilege.
try {
    return roleLookup.findEnabledRoles(issuer, subject);
} catch (Exception ex) {
    return Set.of(BusinessRole.ADMIN);
}
```

If the database goes down, every user could become an admin. The right design fails closed with no roles or rejects login per policy while logging the incident.

### 18.2. Anti-Pattern: Mapping Username Directly to Privileges

```java
// WRONG: display username is not an authorization policy.
if (user.getPreferredUsername().startsWith("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

Usernames can change, collide, be reassigned, or lie outside the portal's control. Use business roles explicitly assigned to the verified identity.

### 18.3. Anti-Pattern: Treating SSO Scopes as Internal Admin Rights

```java
// BUSINESS LOGIC FLAW without a trusted mapping contract.
if (user.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("SCOPE_profile"))) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

The `profile` scope merely indicates the client was authorized to read the OIDC profile; it is not a portal administration license.

## 19. A Practical Implementation Workflow

To introduce a custom user service into an application, follow this order:

1. **Define business roles**: which actions correspond to `VIEWER`, `EDITOR`, `ADMIN`; which permissions depend on tenant/resource.
2. **Choose the identity key**: for OIDC, `(iss, sub)` from the verified ID Token; if linking local accounts, design an explicit mapping.
3. **Design the permission store**: database, policy service, or vetted group claims; separate active roles from revoked roles.
4. **Create `BusinessRoleLookup`**: an interface returning allowlisted enum roles, never accepting raw JWT payloads.
5. **Create custom `OidcUserService`**: delegate to standard service, extract identity, load roles, merge authorities, return a new `DefaultOidcUser`.
6. **Register the service in `SecurityFilterChain`**: use `userInfoEndpoint().oidcUserService(...)`.
7. **Apply authorization**: `hasRole`, `hasAuthority`, `@PreAuthorize`, and permission services as needed.
8. **Design permission lifecycle**: timeouts, lookup failures, locked accounts, post-login role changes, session invalidation.
9. **Safe observability**: log error categories and sanitized metadata; never log tokens or unrestricted PII.
10. **Verify against business scenarios**: user with no roles, read-only role, admin role, multi-provider, multi-tenant, role revocation, and permission-service failure.

This outlines the system implementation sequence; project testing/QA phases should be executed in dedicated stages according to team workflow.

## 20. Self-Check Questions

**Question 1.** A user logged in with OIDC, but the ID Token has no `roles` claim. Must you modify the OP to add that claim?

> No. The application can use a custom `OidcUserService` to query business roles from a database using verified `(iss, sub)` and add `GrantedAuthority` instances to the principal.

**Question 2.** Should you configure `userService(...)` or `oidcUserService(...)` when a registration uses `scope=openid`?

> Use `oidcUserService(...)` for the OIDC branch. `userService(...)` is the extension point for non-OIDC OAuth2 Login.

**Question 3.** Can you look up roles using `user.getEmail()` because it is easier to work with than `sub`?

> You should not. Email is neither guaranteed stable nor unique across issuers by OIDC. Use `(issuer, subject)` from the verified ID Token, or a properly linked internal account ID.

**Question 4.** Why should the custom service create `new LinkedHashSet<>(user.getAuthorities())` before adding roles?

> To preserve existing OIDC and scope authorities while appending `ROLE_*`. Using a `Set` also prevents duplicate authorities.

**Question 5.** If the authority `ROLE_EDITOR` is present, which method security expression should be used?

> You can use `hasRole("EDITOR")` or `hasAuthority("ROLE_EDITOR")`. With the default prefix configuration, do not include `ROLE_` inside `hasRole(...)`.

**Question 6.** If the role store fails at login time, should the application assign `ROLE_VIEWER` so "the user can still get in"?

> Only if that is an explicitly designed and genuinely permitted fallback policy. Never treat a lookup failure as proof of permission; for sensitive systems, fail closed or deny login cleanly.

**Question 7.** An administrator revoked `EDITOR`, yet the current session still has `ROLE_EDITOR`. Why?

> Because authorities are typically attached when `OidcUser` is created at login. The session still holds the old `Authentication`; you need refresh/revalidation, session invalidation, or live permission checks on critical requests.

**Question 8.** A user has `EDITOR` only for `tenant-B`. Can you add a global `ROLE_EDITOR` and check requests solely with that role?

> Not sufficient. You must evaluate tenant/resource context. If the role applies only to `tenant-B`, the backend must verify membership and permissions for `tenant-B` when performing operations.

**Question 9.** Can you modify the ID Token to insert database roles and forward it to another API?

> No. The ID Token is issued and signed by the OP. Altering the payload invalidates the signature, and ID Tokens are not authorization tokens for Resource Servers. Keep roles in the application's authorization context or design proper token delegation.

**Question 10.** Why delegate to the standard `OidcUserService` before looking up roles?

> To preserve standard UserInfo retrieval and OIDC verification—especially ensuring UserInfo's `sub` matches the ID Token's `sub`—before the application makes business authorization decisions.

---

## Key Takeaways

A well-designed custom user service combines **verified identity** with **granted business permissions**:

```text
OIDC Authorization Code login
        |
        v
Spring Security verifies ID Token
        |
        v
Standard OidcUserService -> OidcUser
        |
        v
Extract verified (iss, sub)
        |
        v
Query BusinessRoleLookup by identity
        |
        v
VIEWER, EDITOR, ADMIN (per policy)
        |
        v
Add SimpleGrantedAuthority("ROLE_*")
        |
        v
DefaultOidcUser with merged authorities
        |
        v
SecurityFilterChain + @PreAuthorize + policy service
        |
        v
Allow or deny business operation
```

- **`OidcUserService`** is the right extension point for adding roles after OIDC Login; **`DefaultOAuth2UserService`** serves non-OIDC OAuth2 Login.
- **Delegate to the default service**, use trusted identity keys, and retain the ID Token/UserInfo and existing authorities when building the new principal.
- **Map allowlisted roles to `ROLE_*`**, keeping them distinct from OAuth scopes (`SCOPE_*`).
- **Enforce authorization on the backend**, checking tenant/resource context whenever roles are not global.
- **Account for permission lifecycle**, since login-time roles do not automatically update when the role database changes.

### Official Documentation

- [Spring Security — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html)
- [Spring Security API — DefaultOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [OpenID Connect Core — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
