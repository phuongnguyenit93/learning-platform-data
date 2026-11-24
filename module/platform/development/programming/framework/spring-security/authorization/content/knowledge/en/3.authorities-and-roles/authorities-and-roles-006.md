# Mapping Roles, Groups, and Permissions from Identity Sources

## 1. The big picture: where do identity and access rights come from?

In Spring Security, **authentication** determines who is sending the request; **authorization** decides which action that principal is allowed to perform on which resource. An identity source such as a user database, LDAP/Active Directory, or an Identity Provider (**IdP**) can tell us which groups a user belongs to, which roles they hold, or which scopes they carry. However, the application must still decide which **application permissions** those facts correspond to.

Imagine user An is confirmed by the identity source to belong to group ID `g-finance-reviewers`. The business system wants this group to have permission to read reports and submit approval proposals. Spring Security does not automatically know that `g-finance-reviewers` must become `report:read` or `report:approve`; the application must have an explicit **mapping rule**, backed by trusted data and testable.

Data flow:

```text
[User / service]
         |
         v
[Log in or send access token]
         |
         v
[Trusted identity source / token verification]
         |
         | subject, issuer, groups, roles, scopes, tenant ...
         v
[Controlled mapping]
  - verify source and format
  - normalize group/role codes
  - look up approved mapping table
  - combine application permissions
         |
         v
[Authentication.getAuthorities()]
  [ROLE_REPORT_REVIEWER, report:read, report:approve, SCOPE_reports]
         |
         v
[Spring Security rules + object policy]
  - functional permission?
  - matching tenant?
  - permitted on this record?
  - valid status/workflow?
         |
         v
           ALLOW / DENY
```

The key point is that **a claim existing in a token does not mean it is already a `GrantedAuthority`**. Nor does a valid `GrantedAuthority` by itself prove a user may access every object: tenant, owner, status, sharing relationships, or other policies must still be evaluated.

The goal of this lesson is to understand and correctly implement the chain: **identity source → trusted data → role/group/permission mapping → GrantedAuthority → authorization decision**, and then test the grant and revocation lifecycle.

## 2. Distinguishing easily confused terms

| Concept | Meaning | Example |
| --- | --- | --- |
| Identity / principal | Who is the system recognizing? | User ID `u-1024` |
| Group | A set of users managed by the identity source | Group ID `g-report-approvers` |
| Source role (IdP role) | A role label issued by an IdP or external application | `finance-reviewer` |
| Application role | A permission group by business responsibility | `REPORT_REVIEWER` |
| Permission | Specific operation right inside the application | `report:read`, `report:approve` |
| Scope | Authorization scope issued to a token/client | `reports.read` |
| `GrantedAuthority` | Representation of a permission used by Spring Security | `ROLE_REPORT_REVIEWER`, `report:read` |
| Resource policy | Permission conditions on a specific resource | Same tenant, belongs to assigned group |
| Source of truth | Where a category of data is authoritatively managed | IdP manages groups; app manages approval limits |

For example, a user holding `ROLE_REPORT_REVIEWER` does not mean the application must let them approve every report. The role can act as a **functional prerequisite**, while approving report 123 still requires checking the owning company and creator.

### 2.1. How do `hasAuthority` and `hasRole` match?

In standard Spring Security configurations:

- `hasAuthority("report:read")` checks **exact** authority `report:read`.
- `hasAuthority("ROLE_ADMIN")` checks **exact** authority `ROLE_ADMIN`.
- `hasRole("ADMIN")` normally looks for authority `ROLE_ADMIN`; the default prefix is `ROLE_`.
- `hasAuthority("SCOPE_reports.read")` checks the string `SCOPE_reports.read`, which may be produced by the JWT scope converter.

Therefore, `ADMIN`, `ROLE_ADMIN`, `SCOPE_ADMIN`, and `admin` **are not equivalent**. If a system changes the role prefix via custom configuration, the matching convention must be aligned consistently. Never "quick-fix" by granting all string variants, as that can accidentally widen permissions.

### 2.2. Source role, application role, and permission need not be 1–1

An organizational group can map to multiple permissions:

```text
Group ID: g-report-approvers
       |
       +--> ROLE_REPORT_REVIEWER
       +--> report:read
       +--> report:approve
```

Conversely, permission `report:read` can be granted to multiple groups. One person can belong to multiple groups and receive the combined effective permissions; however, **merging** must follow explicit rules, especially when there are tenant boundaries, deny rules, or conflicting roles.

The mapping table can live in version-controlled configuration or a policy datastore. Clearly document business owners and the change-approval process. Do not treat human-readable group names on screen as immutable identifiers; if the IdP provides stable group IDs, prefer those IDs to avoid breakage when groups are renamed.

## 3. Clearly identify the identity source and trustworthy data

Identity sources provide different kinds of information. There is no universal standard claim forcing every IdP to place groups in `groups`, permissions in `permissions`, or roles in `roles`. Before writing code, verify the **provider**, **data type**, **where data comes from**, and **source verification mechanism**.

| Source | Common information | How data reaches Spring Security | What must be verified |
| --- | --- | --- | --- |
| Application user database | User ID, internal roles/permissions, account status | `UserDetailsService` or custom authentication service | Permissions are active and account is enabled |
| LDAP/Active Directory | User DN/ID, groups, directory attributes | LDAP auth configuration and group/role mapper | Direct/nested groups, DN conventions, data limits |
| OAuth2/OIDC login | User ID, some group/role claims, token scopes | `OAuth2User`/`OidcUser`, user service and authority mapper | Whether claims come from ID token or UserInfo; trusted source/config |
| OAuth2 Resource Server JWT | `iss`, `sub`, `aud`, `scope`/`scp`, custom claims | `JwtDecoder`, `JwtAuthenticationConverter` | Signature, issuer, audience, token validity, claim origin |
| Opaque token | Scopes/data returned by introspection endpoint | OAuth2 introspection and suitable converter | Trusted introspection endpoint, active status, returned data |
| Internal permission store | Tenant-scoped roles, limits, resource grants | Application query or policy service | Admin API protection, data freshness, auditing |

When two different sources exist, define **who governs what**. For example, the IdP owns identities and department groups, while the application owns tenant-scoped transaction approval rights and limits. Never let a generic IdP group arbitrarily turn into global admin rights in the application.

### 3.1. ID token, access token, and claims differ

In OIDC, an **ID token** serves to confirm login information to the client; an **access token** is issued to access resources/APIs for the intended purpose and audience. An API resource server must never accept an ID token as a bearer access token merely because its signature is valid.

Before mapping a JWT into authorities, the server must validate the token using a trusted decoder, including allowed signature/algorithm, validity window, issuer, and audience matching the API. A validly signed JWT issued **for another API** does not grant access to the current API. With multiple issuers, configure an explicit list of trusted sources; never use an unverified `iss` value to trust arbitrary issuers automatically.

### 3.2. Group/role claims can be absent, change format, or exceed size limits

Some providers put groups in `groups`, while others place roles in custom claims or nested objects. Some omit the full group list from the token when a user belongs to too many groups, replacing it with an indicator requiring an extra lookup. If a claim is missing or unreadable, **never guess administrative privileges**. Use an authenticated, properly authorized group-lookup API, or deny per policy when sufficient data is unavailable.

Never identify groups via substring matching:

```text
WRONG:
  if "admin" appears anywhere in group name -> ROLE_ADMIN

BETTER:
  map["approved-group-id"] -> specific authorities,
  other or unknown groups -> no permissions from this mapping
```

Group names, casing, whitespace, and prefixes must be normalized per the IdP contract, never casually normalized into another privileged group.

## 4. Design the mapping table before writing Spring Security code

Suppose a reporting application has three IdP-managed groups and some application-owned permissions:

| Trusted Group ID | Granted app permissions | App role (if used) | Scope/limitation |
| --- | --- | --- | --- |
| `g-report-viewers` | `report:read` | `ROLE_REPORT_VIEWER` | Only reports of tenants the user has access to |
| `g-report-editors` | `report:read`, `report:update` | `ROLE_REPORT_EDITOR` | Assigned projects only |
| `g-report-approvers` | `report:read`, `report:approve` | `ROLE_REPORT_REVIEWER` | No self-approval; may require limits |
| Unapproved group | No app permissions granted | No role granted | Default deny |

This is an **illustrative convention**, not a default schema of Spring Security or any identity provider.

### 4.1. Who is responsible for mapping?

There should be at least three boundaries:

1. **IdP / identity source:** authenticates users, assigns/manages groups, issues trusted claims.
2. **Application mapper:** translates recognized groups/roles/scopes into `GrantedAuthority` sets per approved policy.
3. **Business evaluator:** decides specific actions based on authorities along with tenant, owner, status, expiry, and resource relationships.

Never grant `ROLE_ADMIN` merely because a user belongs to an OS `Administrators` group or a group from another tenant. **Application privileges** require separate approval and must bind to system-verified group/scope IDs.

### 4.2. Are final permissions a union or an intersection?

Many systems take the union of permissions from trusted groups:

```text
app_permissions = union(mapping(groupA), mapping(groupB), ...)
```

Yet that is only the **functional permission set**. The actual decision can be an intersection:

```text
ALLOW =
  has required authority
  AND account is active
  AND belongs to active tenant
  AND permitted on specific resource
  AND satisfies current business rules
```

If a group is defined as a **denial/restriction**, or two roles conflict under separation of duties (SoD), you cannot union permissions and ignore conflicts. Define deny precedence, SoD constraints, and error handling explicitly.

### 4.3. Tenant scope must not be lost when converting to authorities

Consider two organizations A and B sharing the system. Being a report approver in A does not automatically allow approving B's reports. If `ROLE_REPORT_REVIEWER` is a global authority string yet only valid in A, preserve **tenant scope** at the policy layer:

- Use mappings computed for the verified active tenant.
- Or grant general functional authorities and always enforce tenant checks at the service/repository layer.
- Or model explicitly scoped permissions, e.g., permission records carrying a tenant column.

Do not invent ad-hoc names like `ROLE_TENANT_A_REVIEWER` thinking string matching alone suffices: that is still just a convention, and the server must still verify the resource's tenant. A tenant ID chosen in a client header/body must be checked against trusted membership rights.

## 5. Standalone Java 17 example: safe group mapping

Before using Spring Security APIs, test mapping logic in plain Java. This example simulates a **server-verified identity** with trusted group IDs, then maps them via an allowlist. It does not perform JWT cryptographic verification; that step belongs to the real authentication adapter.

Create `IdentityAuthorityMappingDemo.java`:

```java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class IdentityAuthorityMappingDemo {
    private static final String TRUSTED_ISSUER =
        "https://id.example.test";

    private static final Map<String, Set<String>> GROUP_PERMISSIONS =
        Map.of(
            "g-report-viewers",
                Set.of("report:read"),
            "g-report-editors",
                Set.of("report:read", "report:update"),
            "g-report-approvers",
                Set.of("report:read", "report:approve")
        );

    // In real production code, only the trusted auth layer creates
    // this data. Clients must never set tokenValidated=true themselves.
    record IdentityContext(
        String subject,
        String issuer,
        String tenantId,
        Set<String> groupIds,
        boolean active,
        boolean tokenValidated
    ) {}

    static Set<String> mapAuthorities(IdentityContext identity) {
        if (identity == null
                || !identity.tokenValidated()
                || !identity.active()
                || !TRUSTED_ISSUER.equals(identity.issuer())
                || identity.groupIds() == null) {
            return Set.of();
        }

        Set<String> authorities = new HashSet<>();
        for (String groupId : identity.groupIds()) {
            authorities.addAll(
                GROUP_PERMISSIONS.getOrDefault(groupId, Set.of())
            );
        }
        return Set.copyOf(authorities);
    }

    static boolean canReadReport(
            IdentityContext identity,
            String reportTenantId
    ) {
        return identity != null
            && reportTenantId != null
            && reportTenantId.equals(identity.tenantId())
            && mapAuthorities(identity).contains("report:read");
    }

    static void show(String label, Set<String> authorities) {
        System.out.println(label + ": " + new TreeSet<>(authorities));
    }

    public static void main(String[] args) {
        IdentityContext reader = new IdentityContext(
            "u-1", TRUSTED_ISSUER, "tenant-A",
            Set.of("g-report-viewers"), true, true
        );
        IdentityContext editor = new IdentityContext(
            "u-2", TRUSTED_ISSUER, "tenant-A",
            Set.of("g-report-viewers", "g-report-editors"),
            true, true
        );
        IdentityContext unknown = new IdentityContext(
            "u-3", TRUSTED_ISSUER, "tenant-A",
            Set.of("unknown-external-group"), true, true
        );
        IdentityContext inactive = new IdentityContext(
            "u-4", TRUSTED_ISSUER, "tenant-A",
            Set.of("g-report-approvers"), false, true
        );
        IdentityContext untrusted = new IdentityContext(
            "u-5", "https://fake.example.test", "tenant-A",
            Set.of("g-report-approvers"), true, true
        );

        show("reader", mapAuthorities(reader));
        show("editor", mapAuthorities(editor));
        show("unknown", mapAuthorities(unknown));
        show("inactive", mapAuthorities(inactive));
        show("untrusted issuer", mapAuthorities(untrusted));

        System.out.println(
            "same tenant: " + canReadReport(reader, "tenant-A")
        );
        System.out.println(
            "different tenant: " + canReadReport(reader, "tenant-B")
        );
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac IdentityAuthorityMappingDemo.java
java IdentityAuthorityMappingDemo
```

Standard output (stdout):

```text
reader: [report:read]
editor: [report:read, report:update]
unknown: []
inactive: []
untrusted issuer: []
same tenant: true
different tenant: false
```

Because `TreeSet` is used when printing, authority order is deterministic. An unknown group does not escalate to admin; inactive accounts and untrusted issuers receive no permissions; a reader cannot cross tenants despite having `report:read`. Note that `tokenValidated` only **simulates the result of server-side verification**. Never allow clients to send this flag, and never assume comparing an issuer string equals verifying token signatures/audience/validity.

A real mapper can also add role `ROLE_REPORT_VIEWER`; the plain Java example uses permissions so learners see the mechanism more clearly. Final permissions still require resource-level enforcement in the application.

## 6. Mapping in Spring Security: from trusted data to `GrantedAuthority`

Spring Security uses `Authentication` to represent the authenticated principal and associated `GrantedAuthority` instances. How authorities enter this object depends on the **authentication mechanism in use**.

### 6.1. Internal users with `UserDetailsService`

In systems using database-stored accounts, a `UserDetailsService` or equivalent authentication component loads the user, account status, and effective permissions. After verifying login credentials, Spring Security can create a `UsernamePasswordAuthenticationToken` holding authorities from `UserDetails` or from a configured processing step.

Conceptual example:

```text
User row: userId=u-1, active=true
UserGroup rows: (u-1, g-report-editors)
ApplicationPolicy: g-report-editors -> report:read, report:update
UserDetails.getAuthorities():
  SimpleGrantedAuthority("report:read")
  SimpleGrantedAuthority("report:update")
```

For roles, Spring normally uses `ROLE_...` strings. Never take roles from a login form field submitted by the user. When an account is locked or permissions change, session/cache policies are needed so subsequent requests reflect updates as required.

### 6.2. LDAP / Active Directory

LDAP can return DNs, group attributes, or member lists; an `AuthoritiesPopulator`/mapper can convert membership into authorities. Define group DN/ID rules and nested group policies. The same name `Developers` in two different directory branches may not be the same group. Also handle incomplete group lists, circular nested groups, or temporarily unreachable directories.

If membership cannot be resolved when it is mandatory for granting access, never treat "failed to load" as "allowed". Deny access or report an appropriate technical error depending on the authorization mechanism.

### 6.3. JWT Resource Server: default scopes differ from custom groups

With a JWT Resource Server, `JwtDecoder` is responsible for validating tokens per configuration. Then `JwtAuthenticationConverter` converts the `Jwt` into an `Authentication`, and `JwtGrantedAuthoritiesConverter` typically maps values in `scope` or `scp` into authorities prefixed with `SCOPE_`.

Example of a verified token:

```json
{
  "iss": "https://id.example.test",
  "sub": "u-2",
  "aud": ["report-api"],
  "scope": "reports.read",
  "groups": ["g-report-editors"]
}
```

Under common default behavior, scope can become `SCOPE_reports.read`. The `groups` claim **does not automatically** become `report:update` or `ROLE_REPORT_EDITOR` without a custom converter. The illustrative token above also intentionally omits other fields; real applications must validate signatures, expiry, and all required claims.

#### Illustrative configuration with allowlist mapping

The snippet below is **Spring Boot 3 / Spring Security 6 integration configuration**, requiring OAuth2 Resource Server dependencies, a trusted `JwtDecoder`, and an application with concrete data-layer authorization.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ReportAuthorizationConfig {
    // Keys are approved group IDs from a trusted origin.
    private static final Map<String, List<String>> GROUP_TO_AUTHORITIES =
        Map.of(
            "g-report-viewers",
                List.of("report:read", "ROLE_REPORT_VIEWER"),
            "g-report-editors",
                List.of("report:read", "report:update",
                        "ROLE_REPORT_EDITOR"),
            "g-report-approvers",
                List.of("report:read", "report:approve",
                        "ROLE_REPORT_REVIEWER")
        );

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> result = new ArrayList<>();

            // Preserve verified scope permissions, e.g. SCOPE_reports.read.
            Collection<GrantedAuthority> scopeAuthorities =
                scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            // groups is an IdP custom claim with no default mapping;
            // unknown groups grant no extra permissions.
            List<String> groups = jwt.getClaimAsStringList("groups");
            if (groups != null) {
                for (String group : groups) {
                    List<String> mapped =
                        GROUP_TO_AUTHORITIES.getOrDefault(
                            group, List.of()
                        );
                    for (String authority : mapped) {
                        result.add(
                            new SimpleGrantedAuthority(authority)
                        );
                    }
                }
            }
            return result;
        });
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("report:read")
            .requestMatchers(HttpMethod.PATCH, "/api/reports/**")
                .hasAuthority("report:update")
            .requestMatchers(HttpMethod.POST,
                    "/api/reports/*/approve")
                .hasAuthority("report:approve")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth -> oauth
            .jwt(jwt -> jwt.jwtAuthenticationConverter(
                jwtAuthenticationConverter()
            ))
        );
        return http.build();
    }
}
```

Part-by-part explanation:

1. The default scope converter is retained, so `SCOPE_reports.read` can coexist alongside application permissions. They **do not mean the same thing** unless application policy defines them to.
2. The `groups` claim is read from a JWT **already verified** by the resource server. Each group is only looked up in `GROUP_TO_AUTHORITIES`; non-matching groups grant nothing.
3. The converter returns a collection of `GrantedAuthority`. In larger apps, deduplicate authorities and store mappings in a versioned policy store.
4. HTTP matchers guard actions by operation. Reading, updating, or approving reports must still check tenant, owner, and business conditions at the service/data layer.
5. `anyRequest().denyAll()` blocks unreviewed endpoints. The sample config omits interactive login, CSRF, or CORS; choices must match the actual authentication architecture.

**Do not copy the sample while skipping trust policy.** Configure issuer/audience accurately for the API token; distinguish access tokens from ID tokens; verify whether the IdP actually emits group claims on access tokens, and whether group IDs used for mapping are stable and tenant-bounded.

A Spring Boot starter config may use `spring.security.oauth2.resourceserver.jwt.issuer-uri` to set a trusted issuer. **Audience validation** must be configured/verified per API contract and framework version; a valid issuer alone does not prove a token was intended for this resource server. If supporting multiple issuers, maintain per-source trust rules and converters to avoid mixing claims from different issuers.

### 6.4. OIDC login differs from JWT Resource Server

With `oauth2Login()`/OIDC login, Spring Security normally creates an `OAuth2AuthenticationToken` whose principal may be `OidcUser`. Group/role data may live in the ID token or UserInfo, depending on the IdP and requested scopes. Mapping can be performed with a `GrantedAuthoritiesMapper` or a custom `OidcUserService`; do not copy a Resource Server's `JwtAuthenticationConverter` into an OIDC login flow expecting it to run.

Steps to follow when using OIDC login:

1. Identify the issuer/provider, client, and actual claims received in the ID token and UserInfo.
2. Map trusted groups/roles using an allowlist table.
3. Build an `OidcUser`/Authentication with appropriate authorities and verify principal and tenant.
4. Enforce roles at HTTP/method layers and resource policies.
5. Design refresh/revocation for login sessions; permissions snapshotted into a session will not automatically change immediately when the IdP updates membership.

Do not assume `ROLE_ADMIN` exists just because the IdP sends `roles:["admin"]`. Claim names, where claims appear, and mapper rules depend on the provider.

### 6.5. Spring Security only sees the final authorities

After authentication, most rules like `hasAuthority`, `hasAnyAuthority`, `hasRole`, or `@PreAuthorize` use `Authentication.getAuthorities()`. If the mapper omits an authority, users get denied despite having the right IdP group; if it maps too broadly, the app grants excessive access.

A useful diagnostic flow:

```text
Does the IdP have the group/role?
  -> Were the claim or UserDetails extracted properly?
    -> Did the mapper match the group ID?
      -> Did the generated GrantedAuthority have the exact string?
        -> Does the HTTP / method rule match that string?
          -> Does the resource policy allow it?
```

Never "solve" every `403 Forbidden` by replacing `hasAuthority("report:approve")` with `authenticated()`; that hides mapping bugs and over-exposes permissions.

## 7. Policies to prevent privilege leaks from roles and groups

### 7.1. Do not equate external groups with global admins

A group named `Administrators` might only administer one machine, one tenant, or a separate system. Never grant `ROLE_ADMIN` to the application based on display-name comparisons. Mapping must use stable group identifiers, the right issuer, and, where applicable, the group's tenant/realm.

Even when multiple identity sources issue the same group ID, their privileges are not automatically equivalent. The mapping key may need `(issuer, tenant, groupId)` instead of just `groupId`.

### 7.2. Do not trust roles/tenants from the HTTP request

Wrong example:

```text
POST /api/documents/123/approve
X-Role: ADMIN
X-Tenant-Id: tenant-A
```

If the server treats these two headers as permissions, callers grant themselves privileges. Even when a user selects a tenant in the UI, the server must verify membership and permissions for that selected tenant and confirm resource 123 truly belongs to it.

### 7.3. Avoid inferring roles from emails or group names

Rules like "emails ending in @company.com should be ADMIN", "groups containing the word finance can approve", or "every account in the LDAP domain is a manager" are high risk. Identity, attributes, and groups are not assertions of application permission unless **explicitly defined by policy** and **from a truly trusted source**.

Emails can change; some attributes may be unverified; group names can collide or change; nested groups can expand unexpectedly. Rely on stable IDs and audited mappings.

### 7.4. Check role conflicts and separation of duties

Combining permissions from multiple groups can create dangerous combinations: e.g., both request creation and request approval rights. If business rules require separation of duties, check the **effective permission combination** when assigning groups and/or per-record action conditions.

Having `request:approve` does not mean "allowed to self-approve". Even with a correct mapper, the business layer must still enforce different creator, matching tenant, valid status/limits, and approval workflow.

## 8. Permission lifetime, revocation, synchronization, and caching

Correct mapping at login time does not guarantee permissions remain valid later. For example, a user is removed from `g-report-approvers` at 15:00 yet holds an access token containing the old group until 15:30. If the resource server trusts claims in a still-valid token, the permission persists until expiry unless an update/revocation mechanism exists.

### 8.1. Every source has an update lag

| Where permissions live | What updates permissions | Risk |
| --- | --- | --- |
| Database roles queried per request | Updated DB/policy | Slow queries, stale cache, or DB outages |
| Authorities inside session | Session refresh or permission reload | Session still holds old permissions |
| Groups/roles in self-contained JWT | New token, expiry, or extra revocation check | Old token retains pre-revocation permissions |
| LDAP groups queried on schedule or cached | Cache sync/invalidation | Nested membership, stale data |
| Centralized permission lookup API | Policy service returns decision | Infrastructure dependency and latency |

Define **maximum revocation latency** requirements per permission type, especially admin, export, or financial actions. For sensitive operations, consider short-lived tokens, managed sessions, dynamic permission checks, permission versioning, or suitable revocation mechanisms. No single approach fits every system.

### 8.2. Scope caches properly

If decisions depend on issuer, user, tenant, action, resource, time, and permission version, caching solely by `userId` can reuse the wrong result across tenants or resources. Caches must include the proper context key and appropriate TTL/invalidation. When a permission source is unavailable, never permit sensitive actions by default just because "checking is temporarily unavailable".

### 8.3. Re-granting permissions and policy versioning

Changing the mapping of `g-report-viewers` from `report:read` to `report:approve` is an **authorization policy change** even though nobody changed groups in the IdP. It requires code review or equivalent approval, negative permission tests, version history, and deployment/rollback procedures.

Clearly separate identity administration (adding people to groups) from policy administration (turning groups into permissions). Someone controlling both paths without oversight can self-escalate privileges.

## 9. Testing mapping end-to-end from IdP to API

At minimum, test three levels: the mapper itself, Spring Security receiving the right authorities, and actual resource operations bounded properly.

### 9.1. Unit test matrix for the mapper

| Input from source | Expected authority | Reason |
| --- | --- | --- |
| Approved group, right source, active account | Permissions listed in mapping | Valid case |
| Unknown group ID | No app permissions granted from that group | Default deny |
| Group claim missing | No roles/permissions assumed from groups | Never guess |
| Group with admin-like name | No admin granted unless matching approved ID/mapping | Prevent name inference |
| Different issuer with same group ID | No permissions from trusted issuer granted | Prevent cross-source bleed |
| Inactive/locked account | Cannot perform protected actions | Status check |
| User in editor and viewer groups | Functional permissions merged per policy | Multi-group mapping |
| User in two conflicting groups | Follows conflict/SoD rules | No blind union |
| Malformed group claim | Rejected or grants no permissions per policy | No lax parsing |
| Different tenant, same permission | No object access outside tenant | Business-layer scope check |

### 9.2. Separate JWT converter tests from authentication tests

When unit-testing a custom `JwtAuthenticationConverter`, build a `Jwt` object in the test with known claims, invoke the converter, and compare the `GrantedAuthority` set. This test **only proves mapping** and does not check JWT signatures.

Another test must verify that `JwtDecoder`/the resource server rejects tokens with bad signatures, wrong issuers, wrong audiences, expired lifetimes, or tokens not issued for the API. Never mistake **mock tokens in tests** for proof that real authentication config is secure.

With `MockMvc` and `spring-security-test`, you can mock principals/JWTs to test URL permissions; many test helpers bypass the real decoder step. Therefore, keep mapping tests, HTTP authorization tests, and real token-verification integration tests distinct at their respective layers.

### 9.3. End-to-end path testing

Once mapping works, test the same principal reading/editing/approving resources:

- Someone with `report:read` can view valid resources and cannot edit.
- Someone with `report:update` cannot edit reports in another tenant.
- Someone with `report:approve` still cannot self-approve their own report if workflow forbids it.
- Someone removed from a group cannot continue operating after the designed revocation window.
- Undeclared endpoints must be blocked by `denyAll()`.
- Exports, batch jobs, message consumers, and service calls have no bypass around policies.
- When IdP/policy data is missing, the system denies sensitive actions.

Check not only HTTP 200/403/404 status codes; also verify returned data is scoped properly and denied operations neither mutate data nor emit side-effect events. A 403 can also stem from CSRF, so verify the exact cause in tests.

### 9.4. Diagnosing mapping failures

If a user gets 403 despite holding a valid group, inspect in order:

1. **Token/login:** was it verified against the right issuer/audience?
2. **Claim:** is the group in the access token, ID token, or UserInfo? Was the list truncated or key renamed?
3. **Mapping:** does the group ID match the deployed mapping table?
4. **Final authorities:** what strings are in `Authentication.getAuthorities()`? Are there `ROLE_`/`SCOPE_` errors?
5. **Rule:** does `hasRole` or `hasAuthority` expect that exact string?
6. **Object:** do tenant, ownership, status, and business policy allow it?

Never log raw tokens during investigation. You can log correlation IDs, verified issuer, subject per privacy policy, mapping reason codes, and deny outcomes; minimize sensitive group data.

## 10. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `groups` claim becomes `GrantedAuthority` automatically | Has group yet gets 403, or wrong mapper runs | Build converter matching actual auth flow |
| Using `hasRole("ADMIN")` with authority `ADMIN` | Missing `ROLE_` prefix match | Standardize role/authority convention |
| Confusing `scope` with application permissions | Scoped token gets overly broad functions | Map explicitly, verify client/audience |
| Accepting raw `X-Role` or `tenantId` from request | Client can elevate privileges | Use verified principal, claims, and server sources |
| Mapping groups by display name or substring | Renaming/collisions grant unintended permissions | Use stable IDs and allowlists |
| Ignoring issuer/tenant in mapping | Mixes groups across sources or tenants | Bind source and scope |
| Checking only authority on read/edit of resources | Data access bypass by changing IDs | Enforce object policies and scoped queries |
| Caching permissions too long in JWT/session | Revocation fails to take effect promptly | Design TTLs, refresh/revocation/dynamic checks |
| Always unioning permissions from multiple groups | Violates SoD or deny rules | Evaluate effective permission combinations |
| Granting default permissions when IdP data is missing | Infrastructure error becomes open access | Fail closed on protected operations |
| Changing mapping without regression tests | Unintended privilege escalation | Version mappings, test deny cases |
| Testing only with fake JWTs | Misses issuer/audience/signature bugs | Add real token-validation tests |
| Logging full JWTs and excessive identity details | Leaks credentials/data | Log reason codes and minimal identifiers |

## 11. Practice exercises

### Exercise 1 — Distinguish role and group

Given: user U belongs to group `g-report-editors`, token has scope `reports.read`; the application maps this group to `report:update` and `ROLE_REPORT_EDITOR`. List the expected authorities. The answer depends on the specific mapping; in section 6's sample configuration, they may include `SCOPE_reports.read`, `report:read`, `report:update`, and `ROLE_REPORT_EDITOR`. Explain why `SCOPE_reports.read` does not substitute for `report:read` when a rule checks exact strings.

### Exercise 2 — Test mapping with an unknown group

Run `IdentityAuthorityMappingDemo.java` and add a group ID named `g-report-admins-copy` not present in the mapping table. Confirm neither `report:approve` nor admin is granted. Then map an approved group and verify the expected authority strings print correctly.

### Exercise 3 — Cross-tenant resource

Keep `report:read` in Authentication but request a report from another tenant. Design unit tests for the policy and service/repository tests ensuring no data is returned. Question: why is changing token mapping insufficient to fix this vulnerability?

### Exercise 4 — JWT permission expiry

Simulate removing a user from the approvers group while an old access token is still unexpired. Describe how long permissions remain active in a self-contained JWT architecture, and propose a revocation mechanism suited for high-risk requirements. Write tests before and after revocation takes effect.

### Exercise 5 — Controlled mapping change

Suppose you want to grant group `g-report-viewers` the `report:approve` permission. Draft a change plan covering: approver, role conflict checks, negative tests, rollout, monitoring, and rollback. Explain why this is a security change even though the IdP did not alter membership.

## 12. End-of-lesson self-check

1. **Do groups automatically become Spring Security roles?** No. You must define how a mapper turns source facts into `GrantedAuthority` instances.
2. **Which authority does `hasRole("EDITOR")` normally look for?** `ROLE_EDITOR` in default configuration.
3. **Do JWT scopes and application roles mean the same thing?** Not necessarily. Scopes express token authorization scope, whereas application roles/permissions follow their own conventions and policies.
4. **Should you accept a `roles` claim from an unverified token?** No. You must validate the token, issuer, audience, and source constraints.
5. **Do two groups from different issuers with the same ID automatically share permissions?** No. Mapping must account for source/namespace as needed.
6. **Can someone in tenant A's approver group approve tenant B's resources?** No, unless policy truly grants access to B and all conditions are verified.
7. **Does revoking a group in the IdP always strip permissions from an existing JWT immediately?** No. It depends on token lifetime, sessions, and revocation mechanisms.
8. **When mapping is right yet 403 occurs, what should you do?** Check authentication, claims, mapping, final authorities, rules, and object policies in order; never open the whole API with `authenticated()`.

**Remember:** identity sources confirm **who is who** and may supply **which groups/roles they belong to**. The application must **map verified facts into accurate, scoped authorities**, and then enforce **actual resource access conditions**. Mapping is only safe when backed by trusted sources, explicit rule tables, negative permission tests, and timely update/revocation mechanisms.