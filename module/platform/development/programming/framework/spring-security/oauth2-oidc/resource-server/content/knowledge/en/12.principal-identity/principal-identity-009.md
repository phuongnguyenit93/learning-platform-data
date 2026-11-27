# Distinguishing Data Normalization from Unwarranted Privilege Granting

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, applications commonly convert claims from a verified access token into a **principal** and **authorities** to process requests. An apparently simple rename or type conversion can accidentally elevate access privileges. Clearly distinguish:

- **Data normalization:** converting the representation of *verified information* into a consistent application format **without changing permission semantics**. For example: converting scope `orders.read` issued by the Authorization Server into the authority `SCOPE_orders.read` per Spring Security convention.
- **Creating or granting additional privileges (privilege grant):** adding an authority, role, or scope to `Authentication` that a trusted authorization source **has not proven the subject possesses**. For example: adding `ROLE_ADMIN` because an email address uses a corporate domain.

> **Key principle:** normalization must never expand the set of actions a principal can perform. If a data transformation lets a request pass an authorization check that it previously had no basis to pass, that is a **privilege-granting decision**, not merely renaming a claim.

This lesson explains the boundary between identity and permissions, how Spring Security maps JWT scopes/roles, safe converter examples, privilege escalation risks, tenant checks, and testing strategies.

## 1. Identity and Authorization Are Two Different Questions

~~~text
Client -- Authorization: Bearer <JWT access token> --> Resource Server
                                                       |
                                                JwtDecoder
                                     verify signature + iss/aud/exp/nbf
                                                       |
                                                JwtAuthenticationConverter
                                                  /             \
                                                 v               v
                                         Principal identity   Granted authorities
                                        (who is represented?) (what permissions?)
                                                  \             /
                                                   v           v
                                                   Authentication
                                                        |
                                                        v
                                              Authorization policy
                                           endpoint + tenant + object
                                                        |
                                                    allow / deny
~~~

In this pipeline, **token verification** occurs before converting claims into permissions.

| Concept | Meaning | Example | Cannot Be Inferred Automatically |
|---|---|---|---|
| **Authentication** | Token verified per trust configuration | JWT with valid signature, issuer, audience, and timestamps | Permission to access all APIs |
| **Principal** | Subject represented by the token | `sub=user-42` | That the subject is an administrator |
| **Display name** | Name for UI presentation | `preferred_username=alice` | A unique or immutable identifier |
| **Scope** | OAuth scope granted to the access token | `orders.read` | Reading everyone's orders |
| **Role** | Role from an authoritative permission system | `orders_operator` | Roles in another app carrying the same privilege |
| **Authority** | Permission string checked by Spring Security | `SCOPE_orders.read` | That the string was granted legitimately |
| **Authorization** | Whether a specific request is allowed | `hasAuthority(...)` + ownership check | That the token already holds all business permissions |

**A principal is not a permission.** Changing `Authentication#getName()` to an email or username must never conjure up roles. Conversely, adding a `GrantedAuthority` to a principal can open API access even when JWT signature verification is 100% intact.

## 2. A Signed Claim Still Needs Trusted Semantics

Example access token issued by an Authorization Server:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "preferred_username": "alice",
  "email": "alice@example.com",
  "exp": 2000000300
}
~~~

There are **three levels of trust**:

1. **Unverified:** header/payload can be Base64URL-decoded, yet are merely self-asserted token data.
2. **Verified and validated:** signature, issuer, audience, expiration, and token policy passed; the Resource Server has grounds to trust the AS issued these claims.
3. **Authoritative permission source established:** a specific claim is designated by contract between the AS and API as an **authoritative source for scopes/roles/permissions**.

Level 2 **does not automatically guarantee** Level 3 for every claim. For example, an Authorization Server can sign a `display_name` that the user freely edits in their profile. Having the AS sign it does not turn that display name into an authorization system. If a user renames themselves to “admin” and the app infers `ROLE_ADMIN`, the vulnerability lies in **permission-mapping logic**, not signature verification.

### What Data Can Serve as a Basis for Permissions?

Valid permission sources can include:

- `scope` or `scp` granted by the AS via OAuth 2.0 per the access-token contract.
- Role/permission claims generated by the AS from an **organization-managed entitlement catalog**, targeting this specific Resource Server.
- A controlled API-side authorization service or database linking the principal to specific tenants/resources.
- Evidence-backed business policies such as ownership, membership, and record state.

Never derive permissions from email, username, display name, unverified claims, IP/User-Agent, URL query params, request body, or another application's groups lacking a mapping policy.

## 3. Comparing Normalization vs. Privilege Escalation

| Transformation | Nature | When Is It Acceptable? |
|---|---|---|
| `scope="orders.read orders.write"` → `SCOPE_orders.read` and `SCOPE_orders.write` | Scope normalization | Claim is issued by AS and formatted per contract |
| `scp=["orders.read"]` → `SCOPE_orders.read` | Scope normalization | `scp` is the issuer's official scope source |
| `sub=user-42` → map internal ID via `(iss, sub)` | Identity normalization | Controlled, unambiguous mapping |
| `preferred_username=alice` → display “alice” | Presentation normalization | UI use only; never an authorization key |
| `scope=orders.read` → add `SCOPE_orders.write` | **Adding privileges** | Invalid without a separate write-granting source |
| `email=admin@company.example` → `ROLE_ADMIN` | **Adding privileges** | Unfounded when based solely on email |
| `sub` contains “admin” → `ROLE_ADMIN` | **Adding privileges** | Unfounded |
| `groups=["staff"]` → `ROLE_SUPER_ADMIN` | Privilege-granting policy | Valid only when the group source is attested and mapping is approved |
| Missing roles → unconditionally add `ROLE_USER` | Default privilege-granting policy | Must be an explicit policy decision, not pure normalization |
| Missing scopes → leave scope authorities empty | Fail closed | Never invent permissions when the source provides none |

Quick sanity check: if the input lacks write permission and the output has write permission, the transformation is **not an equivalent normalization**. It added a new capability.

## 4. Principal, `sub`, and Display Name

In Spring Security's JWT Resource Server, the common default behavior is:

- `Authentication#getPrincipal()` returns the `Jwt` object.
- `Authentication#getName()` uses the `sub` claim if present.
- Scopes from `scope` or `scp` are converted into authorities prefixed with `SCOPE_`.

Example:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "preferred_username": "alice",
  "scope": "orders.read"
}
~~~

After authentication under common defaults:

~~~text
Authentication.name        = user-42
Authentication.principal   = Jwt(...)
Authentication.authorities = [SCOPE_orders.read]
~~~

`preferred_username` helps the application display “alice” without replacing the canonical identity.

### 4.1. Only `(iss, sub)` Is Suitable for Multi-Issuer Identification

Suppose two IdPs both emit `sub=user-42`:

~~~text
https://idp-a.example.com  +  user-42  -> Person A
https://idp-b.example.com  +  user-42  -> Person B
~~~

If the system accepts multiple issuers, storing `sub` alone can accidentally merge two people. A controlled identity-mapping design uses the **issuer + subject** pair, and may add tenant/realm per the data model.

Never merge users simply because two tokens share `email`, `name`, or `preferred_username`. Those attributes can change or lack uniqueness across identity domains.

### 4.2. Email and Username Are Not Roles

The following code is wrong:

~~~java
// WRONG: an email domain does not prove admin privileges
if (email.endsWith("@company.example")) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_ADMIN")
    );
}
~~~

Even if `email` sits inside a signed JWT, the AS did not necessarily issue that email from an **admin role-granting workflow**. An `email_verified=true` claim (when present) only reflects email verification status per the issuer contract, never system administration rights.

### 4.3. Client Credentials Do Not Necessarily Have a Human User

An OAuth 2.0 `client_credentials` access token typically represents an application or workload, not an interactive human user. In that case, `sub`, `client_id`, and other claims must be interpreted per token profile.

Never infer:

~~~text
Has sub -> is a user -> add ROLE_USER -> allowed to call all user endpoints
~~~

A machine client must be authorized by its client identity, scopes, and dedicated business policies. Never assign human roles simply because a token carries `sub`.

## 5. Authorities and the `SCOPE_`, `ROLE_` Conventions

Spring Security represents permissions as `GrantedAuthority` strings, such as:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDERS_READER
ROLE_ORDERS_OPERATOR
~~~

These names are technical strings. Any authority appearing in `Authentication` must derive from an **issued entitlement** or a trusted authorization source.

### `hasAuthority` Differs from `hasRole`

In standard default setups:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasRole("ADMIN")
~~~

`hasAuthority` matches the exact string; `hasRole("ADMIN")` checks `ROLE_ADMIN` per the configured role prefix.

Consequently, if a developer sets the prefix for scopes to `ROLE_`, a scope named `admin` could collide with the application's role rules. Spring Security allows changing prefixes, yet **doing so can alter authorization semantics**, not just display formatting.

Endpoint example:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Read scope never grants write permission. Even less is there any basis to convert `orders.read` into `ROLE_ADMIN`.

## 6. Standard Scope Mapping in Spring Security

A verified JWT contains:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

By default, Spring Security maps these scopes to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

This is **data normalization** when the claim genuinely holds AS-issued scopes. The `SCOPE_` prefix does not mean the AS issued two additional scopes.

Some issuers use:

~~~json
{
  "scp": ["orders.read", "orders.write"]
}
~~~

`JwtGrantedAuthoritiesConverter` supports common scope claims and provides APIs to customize claim name, delimiter, and prefix. When an issuer follows a specific contract, specify the source explicitly.

### 6.1. Converter Reading Only the `scp` Claim

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class PrincipalMappingConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter grants =
            new JwtGrantedAuthoritiesConverter();

        // The example AS designates scp as the official scope list.
        grants.setAuthoritiesClaimName("scp");
        grants.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(grants);
        converter.setPrincipalClaimName("sub");
        return converter;
    }
}
~~~

Filter chain using this bean:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter)))
            .build();
    }
}
~~~

This example assumes `spring-boot-starter-oauth2-resource-server` and a trusted `JwtDecoder`, such as auto-configured by Spring Boot via `issuer-uri`. The converter **does not verify the JWT itself**; it runs within the authentication flow managed by Spring Security.

If the issuer already uses standard `scope` or `scp` and the default converter fits, there is no need to write a custom converter. Writing unnecessary privilege-mapping logic increases policy error risk.

## 7. Changing the Principal Name Is Different from Granting Permissions

Spring Security supports:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("preferred_username");
~~~

This is a valid API, yet understand the consequence: `Authentication#getName()` will then use the `preferred_username` claim. If a service uses that name as the order ownership key or internal user mapping, a renamed or colliding username can cause identity bugs.

Good designs typically separate:

- **Canonical ID:** issuer + subject, or a reliably mapped internal user ID.
- **Display name:** `name`, `preferred_username`, or nickname.
- **Authorities:** scopes, roles, and permissions from authoritative sources.

Example controller changing only the **display name** without altering authorities:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();

        String displayName =
            jwt.getClaimAsString("preferred_username");

        if (displayName == null || displayName.isBlank()) {
            displayName = subject;
        }

        return Map.of(
            "subject", subject,
            "displayName", displayName
        );
    }
}
~~~

This example assumes the route is protected and the AS always supplies a non-null `sub`. In real applications, avoid returning unnecessary personal info and do not expose internal identity IDs if security policies forbid it.

The fallback here is **purely for display**. No statement adds `ROLE_USER` or `ROLE_ADMIN` when `preferred_username` is missing.

## 8. Role Mapping: Can Be Valid, Yet Is Not Arbitrary String Rewriting

An AS may emit:

~~~json
{
  "app_roles": ["orders_reader", "orders_operator"]
}
~~~

If the organization has a contract stating `app_roles` is issued by a trusted role system **specifically for `orders-api`**, you can define a mapping:

~~~text
app_roles/orders_reader    -> ROLE_ORDERS_READER
app_roles/orders_operator  -> ROLE_ORDERS_OPERATOR
~~~

However, verify that:

1. The token has valid issuer, audience, token type, and cryptographic verification.
2. The `app_roles` claim is produced by an authoritative entitlement manager, not a user-editable profile field.
3. The roles target **this application**, not another application sharing the same IdP.
4. The mapping is approved and uses an explicit allowlist.
5. Roles are scoped by tenant/resource if required by the contract.
6. Policies exist for lifecycle, revocation, and stale permissions.

Without these conditions, turning arbitrary groups/roles into `ROLE_*` can cause **privilege escalation**.

### 8.1. Role Converter with an Explicit Allowlist

The snippet below illustrates a **grounded role-mapping policy**, to be used only when the issuer is approved as a role source for the application:

~~~java
package com.example.orders.security;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class ApplicationRoleConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter result =
            new JwtAuthenticationConverter();

        result.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(scopes.convert(jwt));

            // app_roles must be an authoritative role claim per contract.
            List<String> roles = jwt.getClaimAsStringList("app_roles");
            if (roles == null) {
                return authorities;
            }

            for (String role : roles) {
                switch (role) {
                    case "orders_reader" -> authorities.add(
                        new SimpleGrantedAuthority("ROLE_ORDERS_READER"));
                    case "orders_operator" -> authorities.add(
                        new SimpleGrantedAuthority("ROLE_ORDERS_OPERATOR"));
                    default -> {
                        // Never convert unknown roles into API permissions.
                    }
                }
            }
            return authorities;
        });

        return result;
    }
}
~~~

This example uses Java 17+ and must be wired into the filter chain and JWT decoder as shown earlier. **The role-mapping branch is an approved delegation decision**, not software guessing at arbitrary role strings.

If the API has no trustworthy role claim, remove the entire role-conversion branch. Keep only scopes and business permissions with clear sources and contracts.

### 8.2. Common Mistake: Turning Every Group into `ROLE_`

~~~java
// WRONG if groups is not an authoritative permission source for this API.
for (String group : jwt.getClaimAsStringList("groups")) {
    authorities.add(new SimpleGrantedAuthority(
        "ROLE_" + group.toUpperCase()
    ));
}
~~~

`groups=["ADMIN"]` might be a group from another application or merely a display label. Blindly creating `ROLE_ADMIN` in the Resource Server crosses trust boundaries.

**The same word “admin” across two systems does not mean both systems grant the same privileges.** Keep role namespaces, contracts, and issuer mappings distinct.

## 9. Never Infer Permissions from These Sources

### 9.1. Email, Username, and Profile Attributes

Rules like the following are dangerous when used directly to grant roles:

~~~text
email endsWith "@company.example" -> ROLE_ADMIN
preferred_username startsWith "admin" -> ROLE_ADMIN
email_verified == true -> ROLE_SUPER_USER
display_name contains "manager" -> ROLE_MANAGER
~~~

They can grant privileges whenever an attribute meant only for identification/display changes. If the business wants a role like “staff allowed to view reports”, use an authoritative membership/entitlement source and narrow permissions—never equate it with an email domain.

### 9.2. ID Tokens Instead of Access Tokens

In OpenID Connect, **ID tokens** are primarily for OIDC Clients; **access tokens** are for Resource Servers. Never extract groups from an ID token and treat them as API access rights when an access token lacks the proper audience and contract.

Even if an ID token is validly signed, its `aud` is typically the client ID, not `orders-api`. Resource Servers must distinguish token types and enforce audience/token-profile validation.

### 9.3. URLs and Request Bodies

Never read roles from query strings or request bodies:

~~~http
GET /api/orders?role=ADMIN HTTP/1.1
Authorization: Bearer <access-token>
~~~

Clients control this input. It may assist resource selection, never become an authority.

### 9.4. Tenant ID

A token containing:

~~~json
{
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

is not enough to conclude the subject has full permissions within that tenant. `tenant_id` is usually **context**, while specific privileges require checking membership, roles, and ownership.

## 10. When Permissions Are Missing, Fail Closed Instead of “Filling Them In for Convenience”

An easy integration mistake:

~~~java
// WRONG: application injects missing scope when users hit 403.
Set<String> scopes = parseScopes(jwt);

if (!scopes.contains("orders.write")) {
    scopes.add("orders.write");
}
~~~

Or:

~~~java
// WRONG: every authenticated request is elevated to operator.
if (authentication.isAuthenticated()) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_ORDERS_OPERATOR")
    );
}
~~~

These snippets might make a feature “work”, yet completely bypass whether the AS or entitlement system actually allowed write/operator access.

The right way to investigate a `403`:

- Did the client request the required scope during the OAuth authorization flow?
- Did the Authorization Server approve granting that scope to this client and subject?
- Does the token have the Resource Server's expected `aud`?
- Is the scope/role claim issued in the expected format and semantics?
- Which claim and prefix is the converter reading?
- Does the `hasAuthority(...)` rule match the actually granted authority?
- Does the business service apply further owner/tenant restrictions?

If the token truly lacks the permission, **adding that permission in a converter is never normalization**. If the token already carries the permission while the converter misread its data format, fixing the converter per contract is valid—so long as the post-conversion permission set is not widened.

## 11. Equivalence Mapping vs. Privilege Expansion

Suppose the trusted entitlement source provides only:

~~~text
scopes = { orders.read }
~~~

Equivalent mapping:

~~~text
orders.read -> SCOPE_orders.read
~~~

Unwarranted privilege expansion:

~~~text
orders.read -> SCOPE_orders.read + SCOPE_orders.write
orders.read -> ROLE_ADMIN
orders.read -> ROLE_ALL_TENANTS
~~~

### 11.1. Renaming Across Two Systems Is Not Automatically Equivalent

AS A uses:

~~~json
{"permissions": ["read:orders"]}
~~~

AS B uses:

~~~json
{"scope": "orders.read"}
~~~

Both strings may look synonymous, yet they can only be unified to `SCOPE_orders.read` if the contract aligns on:

- Which data objects may be read.
- Tenant/organization scope.
- Conditions the client/subject must satisfy.
- What “read” means (own records vs. everyone's records).
- Token type and audience.

If `read:orders` from AS A means “read all orders”, while `orders.read` from AS B means “read only the subject's orders”, merging the names masks a critical privilege difference. **One-to-one string mapping does not equal policy equivalence.**

### 11.2. Keeping Only a Subset of Permissions Can Be Appropriate

A Resource Server managing only orders can ignore unrelated scopes:

~~~text
Token scopes:
  orders.read, profile.read, billing.read

Authorities the application actually cares about:
  SCOPE_orders.read
~~~

Using only the necessary scope follows the principle of least privilege. Conversely, inferring `SCOPE_orders.write` from `billing.read` is an unauthorized privilege grant without justification.

## 12. Namespaces and Role Hierarchies

Generic permission names like:

~~~text
ROLE_ADMIN
ROLE_USER
ROLE_OPERATOR
~~~

easily collide when multiple services or issuers have distinct roles. In larger systems, use specific namespaces:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDERS_READER
ROLE_ORDERS_OPERATOR
~~~

However, namespaces only reduce name collisions—they **do not replace trusted entitlement sources**.

A role hierarchy like:

~~~text
ROLE_ORDERS_ADMIN > ROLE_ORDERS_OPERATOR > ROLE_ORDERS_READER
~~~

can be valid when explicitly governed. Yet it is a **policy deriving lower-tier privileges from higher-tier roles**, not mere name normalization. Never invent a hierarchy from alphabetical order or user group names.

## 13. Missing, Wrongly Typed, or Conflicting Claims

A safe converter must define behavior when input violates the contract.

| Input | Appropriate Behavior |
|---|---|
| Missing `scope` or `scp` | Do not fabricate OAuth scopes |
| `scope=""` | Do not create scope authorities |
| `scp=["orders.read"]` | Map only the permissions present |
| `scp` is an object instead of a valid list/string | Reject or grant no permissions per policy; never guess |
| `app_roles=["unknown"]` | Do not generate privileged roles from unrecognized names |
| Role claim freely editable by user in profile | Never use as an authorization source |
| Missing `sub` on a token requiring a user subject | Handle per contract; never create an admin user |
| No internal identity mapping | Never assign high default privileges |
| Wrong issuer/audience | Reject at the authentication boundary |
| `groups` has unexpected type | Never fall back to full privileges |

Depending on the contract, the application may reject the token for missing a required claim or proceed with empty authorities so authorization rules deny access. Both must **fail closed** against ungrounded privileges.

### `scope` and `scp` Appearing Together

Example token:

~~~json
{
  "scope": "orders.read",
  "scp": ["orders.write"]
}
~~~

Never automatically **union** both sets simply because both names relate to scopes. Determine which claim is authoritative in the issuer's profile. If one claim exists for legacy compatibility, blindly merging them can grant unintended privileges.

## 14. Tenant and Resource Permissions

Suppose a valid JWT contains:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

For `GET /api/tenants/tenant-a/orders/1001`, the application may need to verify:

1. The token has a valid signature, issuer, audience, and timestamps.
2. The token carries `orders.read`.
3. The user/client holds matching membership/entitlement in `tenant-a`.
4. Order `1001` genuinely belongs to tenant A.
5. The principal is allowed to access that specific order per policy.

A converter that turns `tenant_id` into `ROLE_TENANT_ADMIN` is dangerous. **Tenant context does not prove tenant administration rights.**

In particular, even with a valid JWT and `SCOPE_orders.read`, an API remains vulnerable to BOLA/IDOR if it accepts an order ID from the URL and returns any record without checking ownership.

## 15. Granting Permissions from a Database Requires an Authoritative Source

Not every permission lives inside the JWT. A Resource Server can verify the JWT, map `(iss, sub)` to an internal user ID, and consult an authorization service or database:

~~~text
Verified JWT (iss, sub)
          |
          v
Trusted identity mapping
          |
          v
Authorization service / policy database
          |
          +-- membership
          +-- order permissions
          +-- tenant roles
          |
          v
Request allow / deny
~~~

This **can be a valid design**—not arbitrary privilege creation—if the database/service is an official authorization source, identity mapping is unambiguous, permissions are checked on the right resources, and authorization-source errors fail safely.

Conversely, a database that accepts `role=ADMIN` sent by a client and stores it verbatim as an entitlement is not trustworthy merely because it lives server-side.

### Stale Roles in JWTs

A self-contained access token captures roles at issuance time and may not reflect subsequent revocations. For example:

1. 10:00: AS issues JWT with `app_roles=["orders_operator"]`.
2. 10:02: admin revokes the role.
3. 10:03: RS verifying the JWT locally still sees the old unexpired role.

This is an issue of permission lifecycle, token TTL, and revocation—**not a normalization bug**. If real-time permission revocation is required, consider introspection, denylists, short TTLs, or checking current permissions from an authoritative source.

## 16. Caution When Using Claim-Set Converters

Spring Security lets you customize claim-set processing via `MappedJwtClaimSetConverter`. It is helpful for converting data types or normalizing representations per the issuer contract.

However, **never use claim normalization to patch claims that ought to be rejected**:

~~~java
// CONCEPTUALLY WRONG: overwriting a wrong issuer with the expected issuer
claims.put("iss", "https://expected-issuer.example");

// CONCEPTUALLY WRONG: injecting audience to pass validation
claims.putIfAbsent("aud", List.of("orders-api"));

// CONCEPTUALLY WRONG: injecting scope to make an endpoint work
claims.putIfAbsent("scope", "orders.read");
~~~

`iss`, `aud`, `exp`, `nbf`, scopes, and token type govern trust and authorization. When a token carries invalid values, the Resource Server must reject it rather than “beautifying” data to slip past policies.

Legitimate normalization covers contract-compliant claim type conversions, display-name formatting, or one-to-one canonical identity mapping after the token is verified.

## 17. A Purely Converter-Caused Privilege Escalation Example

Validly signed JWT:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "preferred_username": "admin-support"
}
~~~

Converter A maps only scopes:

~~~text
SCOPE_orders.read
~~~

Converter B infers extra privileges:

~~~text
SCOPE_orders.read
ROLE_ADMIN
~~~

Both requests carry **the exact same token and signature**. Yet B elevated privileges solely because the username contained “admin”. Where the API uses `hasRole("ADMIN")`, B allows actions the AS never granted and business policies never approved.

That is **privilege escalation at the authority-mapping layer**, even though cryptographic JWT verification was completely accurate.

### Questions to Answer When Reviewing a Converter

For every line that adds a `GrantedAuthority`:

- Which claim or system **proves** the permission?
- Is the claim emitted by an authoritative role/permission source?
- Does the token match the right issuer, audience, and token type?
- Are the resulting authorities strictly equivalent to the source entitlement?
- Does the mapping cross application or tenant boundaries?
- Can missing, malformed, or unfamiliar claims lead to higher default privileges?
- Who governs the permission mapping and through what change-control process?
- Are there tests ensuring the converter **never produces admin/write privileges** from identity strings?

Failure to answer any of these signals that the mapping should be rejected or redesigned.

## 18. Both JWTs and Opaque Tokens Require This Principle

For JWTs, Spring Security typically uses `JwtAuthenticationConverter` after `JwtDecoder` verifies the token. For opaque tokens, the Resource Server typically relies on introspection and receives an `OAuth2AuthenticatedPrincipal` with attributes/authorities.

Common rules:

- Only trust tokens with a valid authentication outcome.
- Never grant permissions from raw token strings or unattested attributes.
- Separate identity claims from authorization claims.
- Map strictly per the issuer contract and entitlement system.
- Continue enforcing tenant and object ownership checks.

Never cast every principal to `Jwt` if the API supports opaque tokens. Use converters/adapters suited to the actual token mechanism.

## 19. Testing Normalization Without Accidentally Granting Privileges

Unit tests should prove **valid permissions map properly** and **ungrounded permissions never appear**.

### 19.1. Example Testing a Converter That Reads Only `scp`

~~~java
package com.example.orders.security;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AuthoritiesMappingTest {

    @Test
    void normalizesExistingScopeButDoesNotInferAdminFromUsername() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .claim("sub", "user-42")
            .claim("scp", List.of("orders.read"))
            .claim("preferred_username", "admin-support")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        converter.setAuthoritiesClaimName("scp");
        converter.setAuthorityPrefix("SCOPE_");

        Set<String> names = converter.convert(jwt).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(Set.of("SCOPE_orders.read"), names);
    }
}
~~~

This test confirms a username containing “admin” does not yield `ROLE_ADMIN`. `Jwt` in a unit test is purely a mock object; **it does not prove JWS signatures were verified**. Write integration tests using test signing keys and a real decoder to test issuer, audience, and cryptography together.

### 19.2. Essential Negative Tests

| Input | Expectation |
|---|---|
| Only `scope=orders.read` | No write or admin privileges |
| No scopes present | No default scopes invented |
| Username contains “admin” | No `ROLE_ADMIN` |
| Corporate email domain | No operator/admin privileges granted |
| Role claim contains unrecognized value | No internal role created |
| Role claim has wrong type | Fails closed per policy |
| Valid signature JWT with wrong `aud` | Rejected before trusted authorities exist |
| JWT from another issuer | Does not use current issuer's role mapping |
| Machine token | No human user roles assigned |
| Tenant A user accessing Tenant B order | Rejected by object/tenant policy |
| Read scope calling a write endpoint | 403 or appropriate denial |

Spring Security Test's `jwt()` helper can simulate a principal or authorities, yet when tests supply authorities directly they can **bypass the production converter**. Test converters directly and write authentication-pipeline integration tests where needed.

## 20. 401, 403, and Authority-Mapping Errors

| Case | Typical Outcome | Cause Category |
|---|---|---|
| Missing bearer token | `401` | Unauthenticated |
| Invalid signature | `401` | JWT verification failure |
| Wrong issuer, audience, or timestamps | `401` | JWT validation failure |
| Valid token missing `orders.write` on POST | `403` | Missing endpoint permission |
| Token has scope yet converter reads wrong claim | `403` | Mapping/contract mismatch |
| User does not own record | `403` or `404` per policy | Object authorization |
| Username contains admin without admin entitlement | `403` on admin endpoint | Expected behavior |
| Converter adds admin from email | Risk of false allow | Privilege escalation |

Never “fix a 403” by unconditionally adding `SCOPE_orders.write` or `ROLE_ADMIN`. Determine whether the entitlement was truly granted or the converter misunderstood its representation.

## 21. A Minimal and Safe Resource Server Design

Suppose `orders-api` trusts a fixed issuer, accepts access tokens targeting `orders-api`, and uses AS-issued scopes.

`build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`SecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

With standard scopes, Spring Security automatically maps `SCOPE_*` without custom role mapping.

The service layer must enforce ownership/tenant:

~~~java
// Pseudocode for application policy, not a built-in Spring API.
Order order = orderRepository.findById(orderId)
    .orElseThrow(NotFoundException::new);

InternalUser user = identityDirectory.resolve(
    jwt.getIssuer().toString(),
    jwt.getSubject()
);

if (!order.ownerId().equals(user.id())) {
    throw new AccessDeniedException("Not permitted");
}

return order;
~~~

`Order`, `InternalUser`, `identityDirectory`, and `NotFoundException` are illustrative domain components. Real behavior should add tenant, status, or other policies as required by business rules.

This model cleanly separates:

1. **JWT verification:** token was issued by a trusted source and targets this API.
2. **Authority normalization:** issued scopes are represented per Spring conventions.
3. **Canonical identity:** user is identified in a controlled manner.
4. **Business authorization:** resource/tenant checks are enforced properly.
5. **No privilege inference:** arbitrary names, emails, or groups never grant admin roles.

## 22. Common Misconceptions

**“Every claim in a signed JWT can become a role.”** No. Claims must come from an authoritative entitlement source under an explicit contract.

**“Mapping `orders.read` to `SCOPE_orders.read` is granting extra privileges.”** No, provided you only translate an actually issued scope per Spring convention.

**“A corporate email means admin access.”** False. Identity metadata never replaces entitlements.

**“If `preferred_username` contains admin, map it to `ROLE_ADMIN`.”** False. A username never proves a role.

**“`hasRole("ADMIN")` and `hasAuthority("SCOPE_admin")` are identical.”** No. They check different authority strings.

**“If a group name matches a role name, it can be mapped automatically.”** No. You need a contract covering source, application, tenant, and role semantics.

**“If write scope is missing, the converter can add it for better UX.”** False. That is privilege escalation.

**“Having `sub` means it is a human user.”** No. Machine access tokens also carry subject/client identity per contract.

**“`sub` is unique across all issuers.”** No. Across multiple issuers, identify using `(iss, sub)` or a trusted identity mapping.

**“Having `tenant_id` means tenant administrator privileges.”** No. Tenant context and role/membership are separate pieces of data.

**“MockMvc `jwt()` automatically proves production converters and signatures work.”** Not necessarily. Mock JWTs can bypass signatures and inject authorities directly in tests.

## 23. Self-Check Questions

**1.** A JWT has `scope=orders.read`. The converter produces `SCOPE_orders.read`. Is that granting extra privileges?

> No, provided `scope` is the AS-issued entitlement source and mapping preserves its semantics.

**2.** A token has `preferred_username=admin_helpdesk` without any admin entitlement. Should `ROLE_ADMIN` be added?

> No. Username is strictly identity/display data.

**3.** A token has `app_roles=["orders_operator"]`. Should it always map to `ROLE_ORDERS_OPERATOR`?

> Only when the AS and API agree this claim is authoritative, targeted at this application, and backed by an approved mapping. That is a privilege-granting decision.

**4.** Two different issuers both emit `sub=user-42`. Should they be treated as one user?

> Not by default. Use identity mapping keyed by issuer and subject.

**5.** Why should you never fix a 403 error by adding privileges inside a converter?

> Because 403 may indicate the AS never granted the permission or a business policy denied access. Adding permissions bypasses security policies.

**6.** If an application role was revoked yet the JWT still holds the old role, where does the cause lie?

> Token/permission staleness and revocation mechanisms, not normalization.

**7.** Is reading permissions from a database always “unwarranted privilege creation”?

> No. When the database is an authoritative authorization source with verified identity and tenant controls, that can be a valid authorization policy.

**8.** When a roles claim has the wrong type or is absent, what should a converter do?

> Never invent higher privileges; fail closed per the token contract.

## 24. References

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `scope`/`scp` mapping, default principal, and customizing `JwtAuthenticationConverter`.
- [Spring Security — JwtAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): principal claim name and authorities converter.
- [Spring Security — JwtGrantedAuthoritiesConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): claim name, prefix, and scope normalization.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority`, `hasRole`, and access control.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): protecting methods by permissions.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, and claim semantics.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token profile, audience, scope, and client context.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): trust boundaries during JWT verification.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, scopes, and authorization model.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspected attributes for opaque tokens.

What must be protected in Spring Security is not only **verified identity**, but also the **legitimacy of every authority inside `Authentication`**. Data normalization serves consistency; access permissions must come strictly from scopes/roles granted by authoritative sources or trusted business policies—never from guesses based on names, emails, or claim shapes.
