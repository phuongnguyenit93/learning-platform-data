# 13.6. GrantedAuthoritiesMapper and Centralized Authority Mapping

## 1. Problem: A User Can Log In, but What Are They Allowed to Do?

In a **Spring Security OAuth 2.0 OIDC Client** application running on Servlet, logging in successfully and being permitted to perform a business action are **two distinct decisions**.

For example, a corporate portal lets employees log in with OpenID Connect (OIDC). The identity provider (*OpenID Provider*, OP) returns an ID Token with subject `employee-123` and a `groups` claim:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "employee-123",
  "aud": "portal-web",
  "groups": ["portal-readers", "portal-report-editors"]
}
~~~

The application wants to enforce its own rules:

- Members of `portal-readers` receive the `ROLE_READER` authority.
- Members of `portal-report-editors` receive the `ROLE_REPORT_EDITOR` authority.
- Only the `portal-admins` group receives `ROLE_ADMIN`.
- Claims not in the approved list do **not automatically** become permissions in the application.

If controllers read `groups` themselves and check strings on every request, authorization rules become scattered, hard to audit, and prone to inconsistencies across endpoints. Spring Security provides **`GrantedAuthoritiesMapper`** to map the `GrantedAuthority` objects created during login into a consistent set of authorities for **`Authentication`**.

The goals of this lesson are to understand:

1. What `GrantedAuthoritiesMapper` is and where it runs in OAuth2/OIDC Login.
2. How to distinguish principal, claim, group, role, and authority.
3. How to build a centralized mapper that maps only from trusted data sources.
4. How to wire the mapper into Servlet `oauth2Login()` and enforce permissions with HTTP endpoints or method security.
5. When a mapper is **not enough**, especially when an Access Token is needed to call an API for groups/permissions.
6. How to avoid over-privileged grants, issuer mismatches, stale permissions over time, or prefix mapping mistakes.

## 2. Distinguishing Authentication, Principal, Claim, and GrantedAuthority

Spring Security places the authentication result inside an `Authentication`, usually retrieved from `SecurityContext`. With OAuth2/OIDC Login, the principal can be `OAuth2User` or `OidcUser`. The principal describes the identity and received attributes; authorities on `Authentication` serve authorization decisions.

| Concept | Example | Role |
| --- | --- | --- |
| **Principal** | `OidcUser` with `sub=employee-123` | User identified after the authentication process |
| **OIDC claim** | `groups: ["portal-admins"]` | Data supplied by the provider in the ID Token or UserInfo |
| **Provider group/role** | `portal-admins`, `finance-team` | How the provider groups users; **not automatically** an application permission |
| **GrantedAuthority** | `ROLE_ADMIN`, `ROLE_READER` | Authority name that Spring Security can evaluate for authorization |
| **Authentication authorities** | Set of `GrantedAuthority` processed by the mapper | Checked by authorization rules like `hasRole` and `hasAuthority` |
| **Application policy** | `/admin/**` requires `ROLE_ADMIN` | Rules protecting business resources/operations |

A principal can contain a `groups` claim without receiving `ROLE_ADMIN` if the mapping policy does not allow it. Conversely, a user holding `ROLE_ADMIN` in the current session may no longer belong to the admin group at the provider hours later if the role was revoked.

### 2.1. Authority Strings and the `ROLE_` Convention

`GrantedAuthority` is the interface supplying the authority name:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority role = new SimpleGrantedAuthority("ROLE_ADMIN");
GrantedAuthority permission =
    new SimpleGrantedAuthority("report:export");
~~~

Spring Security normally interprets:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

as requiring the authority **`ROLE_ADMIN`** (prefixed with `ROLE_` by default).

Meanwhile:

~~~java
.requestMatchers("/admin/**").hasAuthority("ROLE_ADMIN")
~~~

checks the exact authority string. For authorities without a role prefix:

~~~java
.requestMatchers("/reports/export").hasAuthority("report:export")
~~~

Therefore, **`hasRole("ADMIN")` is not `hasAuthority("ADMIN")`**. Agree on an authority naming convention before building the mapper.

### 2.2. ROLE Is Not an OAuth2 Scope

An Access Token with scope `reports.read` does not automatically mean the user has `ROLE_READER` in the web application. Scopes describe delegated resource access in the OAuth2 ecosystem; internal roles/authorities are application policy.

Authorities like `SCOPE_reports.read` often appear in Resource Server scope checks or depending on principal construction. **Never assume every OAuth2 Login principal automatically carries all `SCOPE_*` authorities** or that mapping scopes to roles is always safe.

## 3. Where Does GrantedAuthoritiesMapper Sit in OAuth2/OIDC Login?

In Servlet OAuth2 Login, Spring Security executes the Authorization Code flow, exchanges the code for tokens, loads the identity, and builds initial authorities. Afterward, the mapper can transform the authority set before placing it on the resulting Authentication.

~~~mermaid
flowchart TD
    A["Browser selects /oauth2/authorization/company"] --> B["Authorization Code + token exchange"]
    B --> C{"Which login type?"}
    C -->|OIDC: openid scope| D["ID Token validation, OidcUserService"]
    C -->|Plain OAuth2| E["DefaultOAuth2UserService / custom service"]
    D --> F["OidcUser + initial GrantedAuthorities"]
    E --> G["OAuth2User + initial GrantedAuthorities"]
    F --> H["GrantedAuthoritiesMapper.mapAuthorities(...)"]
    G --> H
    H --> I["OAuth2AuthenticationToken with mapped authorities"]
    I --> J["SecurityContext / session"]
    J --> K["HTTP authorization: hasRole / hasAuthority"]
    J --> L["Method authorization: @PreAuthorize"]
~~~

This is the logical flow for standard OAuth2/OIDC Login. The mapper **does not verify ID Token signatures**, does not issue Access Tokens, and does not itself decide whether an HTTP request is allowed at the moment it runs. It only transforms the authority list after the user service / Authentication Provider handles login.

### 3.1. The GrantedAuthoritiesMapper API

Interface package:

~~~java
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
~~~

Primary method:

~~~java
Collection<? extends GrantedAuthority> mapAuthorities(
    Collection<? extends GrantedAuthority> authorities
);
~~~

Its input is a **collection of `GrantedAuthority`**, not `OAuth2UserRequest`, `OidcUserRequest`, `ClientRegistration`, or `OAuth2AccessToken`.

A simple lambda:

~~~java
GrantedAuthoritiesMapper mapper = inputAuthorities -> {
    Set<GrantedAuthority> result = new LinkedHashSet<>();
    for (GrantedAuthority authority : inputAuthorities) {
        result.add(authority);
    }
    return result;
};
~~~

This example grants no new roles; it only illustrates the interface signature. Real usage requires importing `java.util.Set`, `java.util.LinkedHashSet`, `GrantedAuthority`, and `GrantedAuthoritiesMapper`.

### 3.2. When Does the Mapper Run?

With `oauth2Login()`, the mapper is typically invoked during the **authentication pass** when creating a new Authentication. It does not re-run on every HTTP request, nor does it re-query the provider for updated groups while the user continues using an existing session.

Consequently:

- Changing mapping policies in source code may require **re-logging in** for existing session authorities to update.
- Removing a group at the IdP **does not automatically** revoke authorities in an already-created web session.
- If business requirements demand near-real-time revocation, the application needs server-side permission checks or refresh/invalidation policies rather than relying solely on a login-time mapper.

## 4. Built-In Authorities in OAuth2 Login and OIDC Login

Spring Security includes specialized authorities that carry principal data.

| Authority Type | Typically Attached To | Readable Data |
| --- | --- | --- |
| `OAuth2UserAuthority` | Plain OAuth2 Login | Attributes from UserInfo-like API, `getAttributes()` |
| `OidcUserAuthority` | OIDC Login | ID Token and, if available, UserInfo |
| `SimpleGrantedAuthority` | Role/scope/permission created by app or provider service | Strings like `ROLE_ADMIN` or `report:read` |

Example differentiating them:

~~~java
for (GrantedAuthority authority : authorities) {
    if (authority instanceof OidcUserAuthority oidcAuthority) {
        OidcIdToken idToken = oidcAuthority.getIdToken();
        OidcUserInfo userInfo = oidcAuthority.getUserInfo(); // May be null
        // Map from claims verified by the OIDC flow.
    } else if (authority instanceof OAuth2UserAuthority oauth2Authority) {
        Map<String, Object> attributes = oauth2Authority.getAttributes();
        // Plain OAuth2 provider: schema/trust depends on integration contract.
    }
}
~~~

Corresponding imports:

~~~java
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;
~~~

`OidcUserAuthority` defaults to an authority string like `OIDC_USER`; `OAuth2UserAuthority` similarly defaults to `OAUTH2_USER`. These are **not** admin roles or business permissions. Exact authority sets also depend on Spring Security version, user service, and customization.

### 4.1. Data in the ID Token and UserInfo

Claims may live in different places:

~~~text
OidcUserAuthority
  |
  +-- idToken
  |     iss, sub, aud, exp, nonce, groups? ...
  |
  +-- userInfo (may be absent)
        sub, name, email, groups? ...
~~~

Before building `OidcUser`, Spring Security performs appropriate OIDC validation steps, including validating the ID Token and verifying that UserInfo's `sub` matches the ID Token's `sub` when UserInfo is used.

However, **`groups` is not a mandatory OIDC claim**. A provider might omit groups, place them under another path, or expose them via a separate admin API. Do not force every provider into one schema assumption.

### 4.2. Never Derive Permissions from Unverified Tokens

When an application uses standard OIDC Login, the framework verifies the ID Token before the mapper runs. Even so:

- Do not treat every string in a `groups` claim as an equivalent internal permission.
- Accept only configured and approved issuers, clients, and providers.
- Never use `email`, `name`, or `preferred_username` as "proof" to grant `ROLE_ADMIN`.
- Never decode an Access Token yourself and read `roles` to grant permissions without verifying token type, issuer/audience, and contract.

**Authenticating the right user** and **granting permissions inside the application** are two separate steps.

## 5. Configuring a Servlet Application with an OIDC Provider

Spring Boot 3.x dependencies example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

With Spring Boot 4.x, use the corresponding starters `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client` per your chosen BOM version. Do not manually mix incompatible Spring Security versions with Spring Boot.

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
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
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

The issuer/URL above are illustrative examples. In production, the issuer must match the exact trusted provider, and client secrets must reside in a secret manager or environment variables, never hard-coded in source control.

**The mapper does not request extra scopes or UserInfo claims on its own.** If neither the ID Token nor UserInfo contains a `groups` claim, the mapper cannot invent a group list; configure the provider to release the claim or use another permission-fetching mechanism.

## 6. Building a Centralized GrantedAuthoritiesMapper in Java

Suppose the corporate provider's ID Token contains a `groups` claim as a string array:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "employee-123",
  "aud": "portal-web",
  "groups": ["portal-readers", "portal-report-editors"]
}
~~~

The system only recognizes approved groups:

| Provider Group | Spring Security Authority |
| --- | --- |
| `portal-readers` | `ROLE_READER` |
| `portal-report-editors` | `ROLE_REPORT_EDITOR` |
| `portal-admins` | `ROLE_ADMIN` |
| Other groups | **Do not auto-grant roles** |

### 6.1. `GrantedAuthoritiesMapper` Bean

~~~java
package com.example.security;

import java.net.URI;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;

@Configuration
public class AuthorityMappingConfig {

    // Issuer registered and trusted by the application.
    private static final URI TRUSTED_ISSUER =
        URI.create("https://id.example.com/realms/company");

    // Only groups in this table are mapped to business roles.
    private static final Map<String, String> GROUP_TO_ROLE = Map.of(
        "portal-readers", "ROLE_READER",
        "portal-report-editors", "ROLE_REPORT_EDITOR",
        "portal-admins", "ROLE_ADMIN"
    );

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return authorities -> {
            Set<GrantedAuthority> mapped = new LinkedHashSet<>();

            for (GrantedAuthority authority : authorities) {
                if (authority instanceof OidcUserAuthority oidc) {
                    // Retain the special authority representing the OIDC user.
                    mapped.add(oidc);
                    OidcIdToken idToken = oidc.getIdToken();

                    if (!TRUSTED_ISSUER.equals(idToken.getIssuer())) {
                        // Do not grant roles from an issuer outside policy.
                        continue;
                    }

                    Object claim = idToken.getClaims().get("groups");
                    if (!(claim instanceof Collection<?> groups)) {
                        continue;
                    }

                    for (Object rawGroup : groups) {
                        if (!(rawGroup instanceof String groupName)) {
                            continue;
                        }

                        String role = GROUP_TO_ROLE.get(groupName);
                        if (role != null) {
                            mapped.add(new SimpleGrantedAuthority(role));
                        }
                    }
                } else if (authority instanceof OAuth2UserAuthority oauth2) {
                    // Plain OAuth2 Login: retain identity authority,
                    // do not infer admin roles from attributes.
                    mapped.add(oauth2);
                }
            }

            return mapped;
        };
    }
}
~~~

This is an **example policy for one specific issuer**. It intentionally does not preserve every incoming `SimpleGrantedAuthority` and does not grant roles for plain OAuth2 providers. If your app must keep other authorities (such as internal permissions or vetted scopes), add explicit preservation rules rather than copying every authority unconditionally from uncontrolled sources.

### 6.2. Why Is an Allowlist Needed?

Dangerous pattern:

~~~java
// ANTI-PATTERN: never use to grant administrative privileges directly.
for (String group : groups) {
    mapped.add(new SimpleGrantedAuthority("ROLE_" + group.toUpperCase()));
}
~~~

If the provider returns `admins`, `system-owner`, or a newly created group whose name matches a sensitive role, the app may grant unapproved privileges. With an allowlist, only **group → authority** mappings explicitly reviewed in policy produce permissions.

**Note:** the group ID itself must also come from an authoritative source. If the provider allows end users to create a group named `portal-admins` without membership controls, an allowlist alone still carries privilege escalation risk. Group governance at the IdP is part of the trust model.

### 6.3. Why Check the Issuer?

In an application supporting multiple OIDC providers, two issuers could both return `groups=["portal-admins"]` yet those groups **do not carry the same trust level**. Matching only on group name without checking issuer/client context could let an external provider account gain admin access in your app.

Policy example:

~~~text
https://id.example.com/realms/company
  groups: [portal-admins] -> ROLE_ADMIN

https://login.partner.example.net
  groups: [portal-admins] -> DO NOT auto-grant ROLE_ADMIN
~~~

In standard OIDC Login, the ID Token's `iss` has already been verified against the registration's configured issuer. Checking the issuer in the mapper serves as an **additional policy guardrail** during role mapping; it does not replace Spring Security's ID Token validation.

### 6.4. Mapping from UserInfo Instead of the ID Token

Some providers return groups in UserInfo. `OidcUserAuthority` may provide `getUserInfo()`:

~~~java
OidcUserInfo userInfo = oidcAuthority.getUserInfo();
if (userInfo != null) {
    Object rawGroups = userInfo.getClaims().get("groups");
    // Validate data type, issuer, and allowlist before mapping.
}
~~~

This snippet assumes `oidcAuthority` is already defined and requires importing `OidcUserInfo`. Never assume UserInfo is always present. When relying on UserInfo, use an OIDC service/flow that guarantees **UserInfo `sub` matches ID Token `sub`**, rather than calling an arbitrary API and merging someone else's data into the principal.

If both the ID Token and UserInfo contain groups that differ, application policy must specify which source is authoritative. Do not blindly union both lists to "grant as many permissions as possible".

## 7. Wiring the Mapper into Servlet SecurityFilterChain

The mapper should be plugged into the OAuth2 Login configuration of the **chain handling callbacks**:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            GrantedAuthoritiesMapper userAuthoritiesMapper) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/css/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/edit/**").hasRole("REPORT_EDITOR")
                .requestMatchers("/reports/**").hasAnyRole(
                    "READER", "REPORT_EDITOR", "ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .userAuthoritiesMapper(userAuthoritiesMapper)))
            .build();
    }
}
~~~

Key part:

~~~java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(userAuthoritiesMapper)))
~~~

Depending on configuration, Spring Security may also auto-detect a `GrantedAuthoritiesMapper` bean; **wiring it explicitly in the DSL** makes it immediately clear which mapper applies to OAuth2 Login.

Place **more specific matchers before** broader matchers: `/reports/edit/**` must be evaluated before `/reports/**`. Otherwise the broader rule may match first and allow access unintentionally.

### 7.1. What Happens After the Mapper Returns Authorities?

Example ID Token of a user belonging to `portal-report-editors`:

~~~text
Before mapping:
  OidcUserAuthority("OIDC_USER", idToken, userInfo)

After mapping:
  OidcUserAuthority("OIDC_USER", idToken, userInfo)
  SimpleGrantedAuthority("ROLE_REPORT_EDITOR")

GET /reports/edit/123
  -> hasRole("REPORT_EDITOR")
  -> Authentication has ROLE_REPORT_EDITOR -> allowed
~~~

Suppose the user belongs only to `portal-readers`:

~~~text
After mapping:
  OIDC_USER
  ROLE_READER

GET /reports/edit/123
  -> requires ROLE_REPORT_EDITOR
  -> absent -> denied
~~~

The mapper **does not grant permissions per URL path**: the mapper supplies authorities, while URL/method security configuration decides which request requires which authority.

### 7.2. Inspecting the Authorities Used by Authorization

To observe `Authentication`'s authorities, you can create an internal diagnostic endpoint (in permitted environments):

~~~java
package com.example.web;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me/authorities")
    public Map<String, Object> authorities(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("principalName", authentication.getName());
        result.put("authorities", names);
        return result;
    }
}
~~~

The Java snippet uses `Stream.toList()` (Java 16+). This endpoint is for illustration only; in production, you likely should not expose all authorities/groups to end users as they can reveal internal details. If used for debugging, restrict access and never include tokens or full principal claims in responses.

**Distinction:** `Authentication.getAuthorities()` is the authority set normally evaluated by the authorization engine. The authority set on the `OidcUser` principal object may not match the mapped authorities on `Authentication` in every configuration. When verifying mapping results, inspect **Authentication authorities** rather than assuming `principal.getAuthorities()` always reflects the mapper.

## 8. Applying Centralized Mapping with Method Security

Beyond URL rules, Spring Security can check permissions on service methods. Enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Service example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('REPORT_EDITOR')")
    public void updateReport(long reportId, String content) {
        // Report update logic; must also check ownership/tenant.
    }

    @PreAuthorize("hasAnyRole('READER', 'REPORT_EDITOR', 'ADMIN')")
    public String readReport(long reportId) {
        // Report read logic; example only shows authorization.
        return "report-" + reportId;
    }
}
~~~

Thanks to centralized mapping, `ROLE_REPORT_EDITOR` is applied consistently across:

~~~text
Provider group = portal-report-editors
          |
          v
GrantedAuthoritiesMapper
          |
          v
ROLE_REPORT_EDITOR
    |                   |
    v                   v
HTTP /reports/edit/**   @PreAuthorize("hasRole('REPORT_EDITOR')")
~~~

However, **roles do not replace object-level permission checks**. A user with `ROLE_REPORT_EDITOR` may only be allowed to edit reports belonging to their own tenant or department. The service must also enforce tenant, ownership, or resource-ID policies rather than allowing edits on every report solely because the role matches.

### 8.1. Is RoleHierarchy the Same as GrantedAuthoritiesMapper?

No.

- **GrantedAuthoritiesMapper** transforms authorities during authentication: e.g., mapping group `portal-admins` to `ROLE_ADMIN`.
- **RoleHierarchy** defines inclusion relationships among roles: e.g., `ROLE_ADMIN > ROLE_REPORT_EDITOR > ROLE_READER` when the product genuinely intends admins to inherit editor/reader permissions.
- **AuthorizationManager / @PreAuthorize** enforces rules when a request or method is invoked.

Without a configured role hierarchy, **`ROLE_ADMIN` does not implicitly imply `ROLE_READER`**. The URL rule example earlier used `hasAnyRole(...)` to list allowed roles explicitly rather than relying on an implicit hierarchy.

## 9. When Is GrantedAuthoritiesMapper Not Enough?

The mapper only receives `Collection<? extends GrantedAuthority>`. It **does not receive `OAuth2AccessToken`**, `OidcUserRequest`, or `ClientRegistration` as direct parameters. This is an important limitation:

Suppose the identity provider does not include group lists in the ID Token or UserInfo, and instead requires calling an API:

~~~http
GET /api/v1/user/groups HTTP/1.1
Host: directory.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_GROUP_API
~~~

`GrantedAuthoritiesMapper` has no Access Token available to perform this request. Trying to grab an Access Token from a global variable, reading an unestablished security context, or smuggling tokens inside synthetic authority maps will corrupt the security lifecycle.

The proper solution is a **delegating `OAuth2UserService` / `OidcUserService`**, because those receive the user request containing the Access Token and registration, and return a principal with cleanly managed authorities.

### 9.1. Comparing Extension Approaches

| Extension Approach | Direct Input Data | Best Fit When |
| --- | --- | --- |
| `GrantedAuthoritiesMapper` | Collection of authorities, potentially containing `OidcUserAuthority`/`OAuth2UserAuthority` | Translating groups/claims already present into centralized authorities |
| `OAuth2UserService<OAuth2UserRequest, OAuth2User>` | User request including registration and Access Token | Plain OAuth2 providers needing a custom user/group API call or provider-specific mapping |
| `OAuth2UserService<OidcUserRequest, OidcUser>` | OIDC user request including Access Token and ID Token | Needing extra API calls while constructing the OIDC principal |
| Separate post-login authorization service | Authentication, principal, business context | Permissions change frequently or require resource-level policy checks |

### 9.2. Example Delegating OidcUserService to Attach Additional Roles

The snippet below illustrates **inserting an application policy source after the default service loads the OIDC principal**. Here it does not call an external API yet, instead querying a domain interface to clearly show the extension point:

~~~java
package com.example.security;

import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class DomainOidcUserService {

    private final OidcUserService delegate = new OidcUserService();
    private final InternalRolePolicy rolePolicy;

    public DomainOidcUserService(InternalRolePolicy rolePolicy) {
        this.rolePolicy = rolePolicy;
    }

    public OAuth2UserService<OidcUserRequest, OidcUser> create() {
        return request -> {
            OidcUser user = delegate.loadUser(request);
            String registrationId =
                request.getClientRegistration().getRegistrationId();

            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(user.getAuthorities());

            // Attach role only if approved by internal policy.
            // Production implementations must validate policy sources and handle errors.
            if (rolePolicy.canEditReports(
                    registrationId,
                    user.getIdToken().getIssuer().toString(),
                    user.getSubject())) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_REPORT_EDITOR"));
            }

            return new DefaultOidcUser(
                authorities,
                user.getIdToken(),
                user.getUserInfo(),
                "sub");
        };
    }
}
~~~

In this example, `InternalRolePolicy` is an **application-defined business interface** (without an implementation shown). This illustrates the extension point rather than a complete project; a real implementation could query a database/authorization service keyed by `issuer + subject` or, per contract, call a groups API using `request.getAccessToken()`.

Key points:

1. `delegate.loadUser(request)` preserves the library's OIDC logic, including required UserInfo checks; **do not skip the delegate** merely to fetch extra roles.
2. `request.getAccessToken()` can be used to call provider-authorized APIs; never send the token to endpoints outside a trusted allowlist.
3. Internal permissions must be bound to `issuer + subject` and/or the appropriate registration, not solely email.
4. If real-time role updates are required, looking up roles **only at login time** still risks staleness; design dedicated dynamic checks and revocation strategies.
5. A custom user service returns an `OidcUser` with expanded authorities; if a `GrantedAuthoritiesMapper` is also configured, coordinate both stages so the mapper does not accidentally strip authorities added by the service.

### 9.3. Avoid Combining a Mapper and Custom User Service Unintentionally

Suppose the delegating service adds `ROLE_REPORT_EDITOR`. If the mapper from Section 6 only keeps `OidcUserAuthority`/`OAuth2UserAuthority` and roles derived from `groups`, `ROLE_REPORT_EDITOR` added by the service could be **dropped**.

Three clean strategies:

- **Single mapping source:** the service gathers data, then invokes one shared policy/mapping component to build the final authority set.
- **Conditional preservation in mapper:** retain authorities originating from a trusted, well-defined source (without blindly keeping arbitrary roles from every provider).
- **Clear separation of duties:** the mapper handles OIDC claim groups, the custom service handles other sources, and both obey a unified policy.

**Never add a role in the user service while silently dropping it in the mapper**, causing logins to succeed yet endpoints to fail mysteriously with 403.

## 10. Mapping Authorities Across Multiple Providers and Tenants

Suppose a portal allows login from corporate OIDC and a partner OAuth2 provider. Both may return a `groups` attribute, yet with different semantics:

~~~text
Company OIDC:
  issuer = https://id.example.com/realms/company
  groups = [portal-admins]
  -> Allow ROLE_ADMIN per internal policy.

Partner OAuth2:
  userinfo.groups = [portal-admins]
  -> Do NOT grant ROLE_ADMIN just because the group name matches.
~~~

With OIDC, `issuer` serves as a strong namespace key to distinguish identity sources. With plain OAuth2 providers, a mapper often lacks enough registration context to distinguish providers if looking only at attributes; use a custom `OAuth2UserService` with `userRequest.getClientRegistration()` when provider-aware mapping is needed.

### 10.1. Separate Policy per Issuer

A general policy can be modeled as follows:

| Trusted Issuer | Source Claim | Approved Group | Authority |
| --- | --- | --- | --- |
| `https://id.example.com/realms/company` | `groups` | `portal-admins` | `ROLE_ADMIN` |
| `https://id.example.com/realms/company` | `groups` | `portal-readers` | `ROLE_READER` |
| `https://login.partner.example.net` | `groups` | `partner-readers` | `ROLE_PARTNER_READER` |
| Other issuers | Any | Any | Grant no internal role |

When multiple tenants live inside one OP, the issuer may contain a realm or tenant path. Do not match only on hostname and apply admin privileges globally; two tenants with different issuers must be evaluated under separate trust boundaries.

### 10.2. A Group Is Not Necessarily a Role

A group may represent:

- An organizational unit, department, or project.
- An email distribution list.
- A tenant access group.
- An actual privileged group controlled by IdP administrators.

Only groups explicitly defined in the **application's authorization model** should map to roles. Having `admin` in a group name does not make it an admin permission.

### 10.3. Multi-Tenant Authorization Needs Additional Resource Checks

Even when a user holds `ROLE_REPORT_EDITOR`, editing a report may still be restricted by tenant:

~~~text
Authentication:
  subject = employee-123
  issuer  = company-idp
  role    = ROLE_REPORT_EDITOR

Request:
  PATCH /tenants/tenant-B/reports/100

Policy:
  role matches?              Yes
  user belongs to tenant-B?  No
  report belongs to tenant-B? Must verify

=> Denied despite having the role.
~~~

`GrantedAuthoritiesMapper` supports fairly coarse-grained authority modeling. **ABAC, ownership, and tenant checks** require an authorization layer inside the service/API or your product's policy engine.

## 11. Mapping from Complex Structured Claims

Not every provider returns `groups` as a flat array. Some return:

~~~json
{
  "realm_access": {
    "roles": ["employee", "portal-reader"]
  },
  "resource_access": {
    "portal-web": {
      "roles": ["report-editor"]
    }
  }
}
~~~

This is an **example of a provider-specific structure**, not a universal OIDC standard claim. Consult your provider's token/claim mapping contract before parsing it.

A helper extracting roles from nested structures must perform type checks:

~~~java
import java.util.Collection;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public static Set<String> extractPortalRoles(Map<String, Object> claims) {
    Object resources = claims.get("resource_access");
    if (!(resources instanceof Map<?, ?> resourceMap)) {
        return Set.of();
    }
    Object portal = resourceMap.get("portal-web");
    if (!(portal instanceof Map<?, ?> portalMap)) {
        return Set.of();
    }
    Object roles = portalMap.get("roles");
    if (!(roles instanceof Collection<?> roleList)) {
        return Set.of();
    }
    return roleList.stream()
        .filter(String.class::isInstance)
        .map(String.class::cast)
        .collect(Collectors.toUnmodifiableSet());
}
~~~

Then **map only approved values**:

~~~java
if (extractPortalRoles(idToken.getClaims()).contains("report-editor")) {
    mapped.add(new SimpleGrantedAuthority("ROLE_REPORT_EDITOR"));
}
~~~

Here `idToken` and `mapped` are existing variables in the mapper. Do not convert all of `resource_access.portal-web.roles` directly into authorities. Roles like `manage-account` or roles for other applications should not become portal authorities merely because they appear in the same JWT.

If a claim exists only in an API **Access Token**, it is not automatically a claim meant for the OIDC Client. Distinguish ID Token, Access Token, and UserInfo, choosing the right data source for the application instead of decoding a token not intended for the client.

## 12. Authority Lifecycle and Stale Permissions

A centralized mapper makes role assignment consistent at login time, yet **does not guarantee real-time permission updates**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant OP as OIDC Provider
    participant C as Spring Security Client
    participant DB as Local authorization policy
    U->>C: Start login
    C->>OP: Authorization Code flow
    OP-->>C: Tokens + claims
    C->>C: GrantedAuthoritiesMapper -> ROLE_REPORT_EDITOR
    C-->>U: Logged-in session
    Note over OP: Admin removes user from editor group
    U->>C: PATCH /reports/edit/123 with old session
    C->>C: Authentication still holds ROLE_REPORT_EDITOR
    Note over C: Mapper does not re-run automatically on each HTTP request
~~~

If the application handles sensitive data and requires near-real-time role revocation, consider:

- Reasonable session lifetimes and risk-based reauthentication/reauthorization.
- Checking permissions against an **authorization service** or internal database on sensitive operations.
- Session invalidation mechanisms on revocation events, if infrastructure supports and implements them.
- Re-evaluating tenant/ownership permissions in the service rather than relying solely on login-time roles.
- Managing permission cache TTLs, balancing freshness against latency.

**Access Token expiration does not mean the browser's Authentication/session expires at the same moment.** A browser may hold a valid session while privileges at the IdP have changed. Never assume refreshing an access token automatically re-runs `GrantedAuthoritiesMapper` and updates session authorities.

## 13. Testing the Mapper as a Policy Function

One advantage of `GrantedAuthoritiesMapper` is that you can unit-test the authority transformation independently without running the entire Authorization Code flow.

### 13.1. An Illustrative Unit Test

The JUnit 5 test below verifies an approved group:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

class AuthorityMappingConfigTest {

    private final GrantedAuthoritiesMapper mapper =
        new AuthorityMappingConfig().userAuthoritiesMapper();

    @Test
    void mapsApprovedCompanyGroupToReader() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "TEST_ONLY_TOKEN_VALUE",
            now,
            now.plusSeconds(300),
            Map.of(
                "iss", "https://id.example.com/realms/company",
                "sub", "employee-123",
                "aud", List.of("portal-web"),
                "groups", List.of("portal-readers")
            ));

        OidcUserAuthority oidcAuthority = new OidcUserAuthority(idToken);
        var names = mapper.mapAuthorities(List.of(oidcAuthority)).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertTrue(names.contains("ROLE_READER"));
    }
}
~~~

This is a **policy mapping unit test**, not proof of ID Token verification: the test instantiates `OidcIdToken` directly. End-to-end OIDC login tests must cover authorization requests, token responses, and the corresponding validator.

### 13.2. Scenarios Worth Testing

| Input | Expected Outcome |
| --- | --- |
| Company issuer, `groups=["portal-readers"]` | Produces `ROLE_READER` |
| Company issuer, `groups=["portal-admins"]` | Produces `ROLE_ADMIN` |
| Company issuer, unapproved group | Does not grant any role from that group |
| Partner issuer, `groups=["portal-admins"]` | Does **not** grant company's `ROLE_ADMIN` |
| Missing or `null` `groups` claim | Does not crash, grants no role |
| `groups` claim is a string instead of an array | Does not guess format; handles per contract |
| `groups` claim contains numbers/objects | Does not blindly coerce to String/role |
| Duplicate groups | Authorities are not duplicated noisily |
| Plain provider `OAuth2UserAuthority` | Does not apply company OIDC policy |
| Custom service adds approved role | Mapper clearly preserves or regenerates it per policy |
| Old session after role revoked at IdP | Appropriate authorization invalidation/refresh strategy exists |

### 13.3. Testing Role Enforcement on Endpoints

A mapper unit test proves "group A produces authority B". It is **not enough** to prove "GET/PATCH endpoints are properly protected". With Spring MVC / Spring Security integration tests, verify:

- Unauthenticated: endpoint requires authentication.
- Authenticated with only `ROLE_READER`: cannot edit reports.
- Authenticated with `ROLE_REPORT_EDITOR`: passes role check, yet still enforces ownership/tenant checks.
- With `ROLE_ADMIN`: permitted only on functions admin policy actually allows.

Mocking authentication in controller tests does not verify OIDC token validation. Keep mapping policy tests, authorization tests, and OIDC integration tests distinct.

## 14. Common Implementation Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| User logs in successfully yet always gets 403 | Mapper not wired into the right `SecurityFilterChain`, or `groups` claim missing | Check `userAuthoritiesMapper` DSL, claim source, and Authentication authorities |
| `hasRole("ADMIN")` rejects `ADMIN` | Missing default `ROLE_` prefix | Map to `ROLE_ADMIN` or use `hasAuthority` with exact string |
| Mapper produces the role, yet endpoint still returns 403 | Wrong matcher order, or method security/tenant policy rejects it | Inspect policies across every security layer |
| Every user receives admin role | Mapped all groups indiscriminately or trusted groups from untrusted provider | Enforce allowlist and issuer/client policy |
| `groups` claim is `null` | Provider does not release groups or scope is missing | Handle missing claims; inspect provider mapping |
| `ClassCastException` reading groups | Provider returns object/string instead of `List<String>` | Validate types and match provider schema |
| Permissions from extra API missing in mapper | Mapper does not receive the Access Token | Use a delegating OAuth2/OIDC user service |
| Custom user service adds role, yet post-login role disappears | Mapper stripped the authority added by the service | Unify policy or preserve approved authorities explicitly |
| Old role remains after user removed from group | Mapper runs only at authentication time | Use session invalidation, reauthentication, or dynamic policy |
| Two providers share admin group name and both get access | Mapper ignores trust source / issuer | Separate mapping per issuer/provider |
| `principal.getAuthorities()` differs from `Authentication.getAuthorities()` | Mapping is applied on Authentication, not necessarily rewriting principal | Inspect `Authentication.getAuthorities()` when debugging authorization |
| Using Access Token roles for portal permissions | Confused Resource Server Access Token with client OIDC identity source | Use verified claims / explicit policy sources |
| `ROLE_ADMIN` suffices to view another tenant's data | Missing resource ownership/tenant check | Enforce object-level policy in service/API |

### 14.1. A Clear Diagnostic Flow

~~~text
User login succeeds, yet /admin returns 403
  |
  +-- Is the registration/issuer right?
  |
  +-- Does ID Token/UserInfo include the expected groups claim?
  |
  +-- Is the mapper wired into oauth2Login() on the right chain?
  |
  +-- Does Authentication.getAuthorities() contain ROLE_ADMIN?
  |
  +-- Does the URL rule use hasRole("ADMIN") or another string?
  |
  +-- Does method security or tenant policy impose extra conditions?
  |
  +-- Is the user still on an old session from before role changes?
~~~

When debugging, never log raw ID Tokens, Access Tokens, Refresh Tokens, `client_secret`, or full UserInfo JSON. For analysis, log registration key, trusted issuer, log-safe authority names, correlation IDs, and minimal policy-approved metadata.

## 15. Security Principles for Centralized Authority Mapping

### 15.1. Never Map Roles Directly from Arbitrary Claims

Claims can contain display values, hints, or data meant for another application. `preferred_username=admin`, `email=admin@example.com`, or `groups=["admins"]` are never sufficient by themselves to grant admin access. Require a **claim contract, trusted issuer, and mapping allowlist**.

### 15.2. Apply Least Privilege

Grant no sensitive roles by default; grant only necessary authorities. If no recognized group is present, the user can still log in yet remain limited to authenticated-user features or restricted by application policy.

### 15.3. Separate Identity from Permissions

OIDC delivers identity authentication evidence (`iss`, `sub`, `aud`...). The mapper translates an approved subset of information into application authorities. Resource-level authorization decides which data the user may act upon.

### 15.4. Avoid Open Policies with Multiple Providers

A partner provider must never gain internal admin privileges merely by returning a role with the same name as the corporate IdP. Scope trust by issuer, client registration, and provider onboarding policy. Never rely on similar hostnames or username/email as a trust namespace.

### 15.5. Never Fetch URLs Supplied Inside Claims

If a claim contains `groups_uri` or `profile_url`, never blindly fetch that URL and attach an Access Token to arbitrary hostnames; doing so risks SSRF or token leakage. Only call pre-configured/permitted endpoints and verify matching audience and scopes.

### 15.6. Plan for Permission Revocation

A login-time mapper does not replace workflows for locking users, destroying sessions, or updating permissions when roles are revoked. For sensitive operations, consider a policy service/database and appropriate session lifetimes.

### 15.7. Never Rely Solely on Roles for Tenant/Object Isolation

`ROLE_ADMIN` may mean "admin of **one tenant**", not the entire system. Enforce ownership, tenant, resource state, and dynamic policies in the appropriate layer so a user with a matching role cannot access another tenant's data.

## 16. Scenario Exercises

### Scenario A — Only Mapping OIDC Groups

The corporate provider puts a `groups` claim in the verified ID Token. The app only recognizes three business groups.

**Choice:** `GrantedAuthoritiesMapper` with an allowlist table. No second HTTP call to the IdP is needed. Wire the mapper into `oauth2Login().userInfoEndpoint()` and use `hasRole`/`@PreAuthorize`.

### Scenario B — Groups Live in UserInfo

The ID Token lacks `groups`, while UserInfo was loaded by Spring Security with a matching subject.

**Choice:** inspect `OidcUserAuthority.getUserInfo()` when non-null and map approved groups. Never assume every login has UserInfo or every provider shares the same schema.

### Scenario C — Groups Must Be Fetched from a Separate API

The provider requires calling `/v1/groups` with an Access Token; neither ID Token nor UserInfo carries groups.

**Choice:** delegating `OidcUserService` or `OAuth2UserService`, since the user request holds the Access Token and registration context. Never try to obtain an Access Token inside `GrantedAuthoritiesMapper`.

### Scenario D — Two Providers Both Return "admins"

Both Company IdP and Partner IdP return `groups=["admins"]`.

**Choice:** map per issuer/provider. Never grant company admin rights to a Partner user; use separate allowlists or resolve permissions from an internal system.

### Scenario E — User Has `ROLE_ADMIN` but Must Not Edit Tenant B Reports

An admin of tenant A sends a request targeting a report owned by tenant B.

**Choice:** beyond the role, the service/API must check permissions against the **specific tenant and resource**. The mapper does not solve ownership by itself.

### Scenario F — Permission Granted, Then Admin Removed from Group

The user still holds an active logged-in HTTP session containing `ROLE_ADMIN` from earlier.

**Choice:** implement invalidation, reauthentication, or dynamic authorization policies. Never expect the mapper to re-run automatically just because groups changed in the IdP.

### Scenario G — Mapper Accidentally Strips Scope Permissions

The app previously checked `SCOPE_reports.read`, yet the mapper retained only `OIDC_USER` and roles.

**Choice:** decide which authorities policy actually relies on, then add controlled preservation rules or update the check. Never assume every `SCOPE_*` is automatically trustworthy across all login types.

### Scenario H — API Returns 403 Even Though Portal Has `ROLE_READER`

The app sends an Access Token to a downstream Resource Server and gets rejected.

**Choice:** inspect the Access Token targeted at that API, its audience, scopes, and Resource Server policies. `ROLE_READER` in the web `Authentication` does not grant extra permissions to the Access Token.

## 17. References

- Spring Security — Servlet OAuth2 Login, Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — Servlet OAuth2 Login, Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — GrantedAuthoritiesMapper Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/GrantedAuthoritiesMapper.html
- Spring Security — OidcUserAuthority Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html
- Spring Security — OAuth2UserAuthority Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/user/OAuth2UserAuthority.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

## 18. Summary

`GrantedAuthoritiesMapper` is a **centralized mapping point** translating authorities generated during OAuth2/OIDC Login into authorities the application uses for authorization.

~~~text
OIDC / OAuth2 Login
    |
    v
Authenticate identity and load principal
    |
    +-- OidcUserAuthority
    |      ID Token, UserInfo if present
    |
    +-- OAuth2UserAuthority
           OAuth2 provider attributes
    |
    v
GrantedAuthoritiesMapper
    - Verify issuer/claim source
    - Map only approved groups
    - Apply ROLE_ / authority naming rules
    |
    v
Authentication.getAuthorities()
    |
    +-- HTTP: hasRole("ADMIN"), hasAuthority(...)
    |
    +-- Method: @PreAuthorize(...)
    |
    +-- Additional policy: tenant, ownership, resource state
~~~

Three key principles:

1. **Do not equate provider groups/claims with application permissions.** Map only via controlled policies checking issuer, registration, and trust level.
2. **The mapper does not directly receive an Access Token.** If you must call an API to fetch groups/permissions, use a delegating OAuth2/OIDC user service or an appropriate authorization service.
3. **Authorities attached to Authentication at login can grow stale over time.** For sensitive data, pair them with service-level permission checks and proper update/revocation strategies.

Following these boundaries, centralized authority mapping keeps Servlet `SecurityFilterChain` and method security configurations clear while reducing the risk of conflicting rules or over-privileged access from external data.
