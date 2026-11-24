# Role, Authority, Permission, Scope, and Relationships Between Concepts

> Knowledge lesson under **Spring Security – authorization**, section **Authorization Landscape**.

## 1. Why Distinguish These Four Concepts?

In an invoice management system, a logged-in employee may still be forbidden from reading another organization's invoices; an accountant may be allowed to edit draft invoices but not approve them; a third-party app may receive a read-only access token. These decisions cannot be fully explained by a single `authenticated=true` flag.

- **Authentication**: identifying the requesting subject.
- **Authorization**: what action is that subject allowed to perform on which resource, in which context?

Role, authority, permission, and scope are four ways of expressing different parts of an authorization decision. In Spring Security, they can connect through `Authentication` and `GrantedAuthority`, yet they are **not four synonymous terms**.

Lesson objectives: understand the terminology accurately, master how roles/permissions/OAuth scopes map to authorities, distinguish `hasRole` from `hasAuthority`, and know when to combine resource, tenant, and ownership checks instead of checking authority strings alone.

## 2. Foundational Concepts Table

| Concept | Role in Authorization | Example | Does Not Automatically Guarantee |
|---|---|---|---|
| **Role** | Business-oriented grouping of responsibilities/users | `VIEWER`, `ACCOUNTANT`, `FINANCE_ADMIN` | Does not automatically grant all permissions or access to all records |
| **Permission** | Capability to perform an action on a resource type or object | `invoice:read`, `invoice:approve` | Does not allow crossing tenant/owner boundaries when policy restricts them |
| **Authority (Spring Security)** | Value that Spring Security matches during authorization | `ROLE_ACCOUNTANT`, `invoice:read`, `SCOPE_invoices.read` | Does not self-explain the business meaning of each string |
| **Scope** | OAuth: access granted to a token/client; business: data/context boundary | OAuth `invoices.read`; data `tenant=T1` | Does not automatically equate to a role or ownership |

**Mnemonic:** role answers "which group do they belong to?", permission answers "which action can they perform?", authority answers "what permission string does Spring Security see?", and OAuth scope answers "what range of access was granted to the access token?". When referring to "tenant scope" in business logic, explicitly note that it is a **data constraint**, not an OAuth scope.

## 3. Role: Grouping Responsibilities and the RBAC Model

Roles are typically units administrators easily assign to accounts:

- `VIEWER`: reads invoices within allowed boundaries.
- `ACCOUNTANT`: creates, reads, and edits draft invoices.
- `FINANCE_ADMIN`: approves invoices and manages financial policies.

An application **can define** the following mapping itself:

| Business Role | Granted Permissions |
|---|---|
| `VIEWER` | `invoice:read` |
| `ACCOUNTANT` | `invoice:read`, `invoice:create`, `invoice:update_draft` |
| `FINANCE_ADMIN` | `invoice:read`, `invoice:approve`, `finance:settings:update` |

This is a sample RBAC (*Role-Based Access Control*) design, **not a default rule inferred by Spring Security**. Unless the database or IAM builds a role → permission mapping, someone with `ROLE_ACCOUNTANT` does not automatically possess the `invoice:update_draft` authority. Some systems check roles directly; others aggregate effective permissions from roles; both approaches must be designed and tested consistently.

Roles alone are often not granular enough for per-object data. Two people with the same `ACCOUNTANT` role may manage two different companies; both have permission to edit draft invoices, yet neither may edit across tenants.

### Roles and the `ROLE_` prefix

Under the default convention commonly used in Spring Security:

- `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority.
- `hasAuthority("ROLE_ADMIN")` also checks the exact string `ROLE_ADMIN`.
- `hasAuthority("ADMIN")` only matches when the `ADMIN` authority actually exists.
- With the default prefix, the argument to `hasRole` is `"ADMIN"`, not pre-prefixed with `"ROLE_ADMIN"`.

The role prefix can be customized at the appropriate configuration points; in operation, verify the actual configuration in use. Role hierarchy (e.g., an admin inheriting editor roles) also requires explicit configuration—it **does not emerge automatically from role names**.

## 4. Authority: The Unit Spring Security Actually Matches

After authentication, Spring Security has an `Authentication` containing a principal and a set of `GrantedAuthority` instances. For familiar string-based authorities, `getAuthority()` might return:

~~~text
Principal: user-42
GrantedAuthorities:
  ROLE_ACCOUNTANT
  invoice:read
  invoice:update_draft
  SCOPE_invoices.read
~~~

When `hasAuthority("invoice:read")` is called, the framework checks whether the **matching string** exists in the authority set. It does not automatically know that `invoice:update_draft` implies `invoice:read`, or that `SCOPE_invoices.read` is equivalent to `invoice:read`.

**Authority is a representation format, not necessarily a business "permission".** Strings like `ROLE_*` usually represent roles; `SCOPE_*` usually represent scopes from a token; `invoice:*` strings may be application-defined permissions. They share the `GrantedAuthority` mechanism, yet differ in meaning and origin.

Authorities can come from database accounts, LDAP, an IdP, application-level role → permission mappings, or JWT claims. With username/password authentication, the application can construct `SimpleGrantedAuthority`. With a Resource Server, a converter determines how token claims map to authorities. **Inputs must come from an authenticated/trusted source**—never accept a role or authority self-entered by the client in a request.

## 5. Permission: Action Permissions and Object-Level Permissions

Permissions are commonly named in "resource:action" pairs:

- `invoice:read` — read invoices.
- `invoice:create` — create invoices.
- `invoice:update_draft` — edit draft invoices.
- `invoice:approve` — approve invoices.
- `user:manage` — manage accounts.

There is no Spring Security rule requiring permission names to contain a colon; this is an **application naming convention**. What matters is that names remain stable, appropriately granular, and consistent across database, policies, endpoints, UI, and tests.

You must distinguish:

1. **Action-level permission**: does the caller have `invoice:read`?
2. **Object-level authorization**: does invoice `INV-01` belong to an allowed tenant and owner? Does the invoice's state permit editing?

If an API checks only `invoice:read` and then fetches an invoice by an arbitrary ID, a user can guess IDs to access other users' invoices (IDOR/BOLA). A business permission is typically a **necessary condition**, not a sufficient condition when resource constraints apply.

Spring Security supports `hasPermission(...)` via object-level permission evaluation, usually requiring the application to integrate a suitable `PermissionEvaluator`. Alternatively, you can use a policy bean or custom `AuthorizationManager` to verify tenant, ownership, state, and relationships between the subject and resource.

## 6. Scope: Two Contexts Commonly Confused

### 6.1. OAuth 2.0 scope – scope of an access token

An OAuth Authorization Server may issue an access token with a claim like:

~~~json
{
  "sub": "user-42",
  "scope": "invoices.read invoices.write"
}
~~~

With Spring Security OAuth 2.0 Resource Server JWT, the common default configuration reads scopes from the `scope` or `scp` claim and creates authorities prefixed with `SCOPE_`:

| Scope in Token | Default Authority |
|---|---|
| `invoices.read` | `SCOPE_invoices.read` |
| `invoices.write` | `SCOPE_invoices.write` |

Therefore, to check the invoice-reading scope under default mapping, you can call `hasAuthority("SCOPE_invoices.read")`. Calling `hasAuthority("invoices.read")` will **not** automatically match. If the system defines a custom converter, check the rules actually in effect.

An OAuth scope reflects **the scope granted to the token/client**; it does not prove that the subject is an accountant, owns the invoice, or can access all tenants. The **actually granted** scopes may be fewer than what the client requested. The API must verify the token (signature, expiration, issuer, and related conditions); audience should be validated/configured according to the system's resource model. Never use an ID token in place of an access token to authorize API calls.

### 6.2. Scope in business logic – data/context boundaries

Many business documents use "data scope" to refer to:

- **Tenant/organization:** only view resources belonging to `T1`.
- **Owner:** only view resources owned by oneself.
- **Department/region:** only view assigned units or territories.
- **Status/time:** only edit if `status=DRAFT` and within the allowed timeframe.

These conditions are attributes of the subject/resource/environment; they fall under ABAC (*Attribute-Based Access Control*) or object-level access control. They **do not automatically turn into OAuth scopes**. Store and check fields like `tenantId`, `ownerId`, and `status` separately rather than lumping everything into one ambiguous field named `scope`.

## 7. How These Concepts Connect in a Request

~~~text
User / Service Client
        |
        v
Verify identity or access token
        |
        v
Build Authentication
  - principal
  - effective roles / permissions
  - mapped OAuth scopes
        |
        v
GrantedAuthority:
  ROLE_ACCOUNTANT
  invoice:read
  SCOPE_invoices.read
        |
        v
Check at HTTP or method layer
  hasRole / hasAuthority / custom policy
        |
        v
Check resource and context
  tenant / owner / status / relationship
        |
        v
ALLOW or DENY
~~~

Typical relationships:

~~~text
Role --(application-defined mapping)--> Permission
Role / Permission --(mapping)--> GrantedAuthority
OAuth scope --(JWT converter)--> SCOPE_* GrantedAuthority
Authorities + resource/context rules --> Authorization decision
~~~

**Do not reverse these arbitrarily:** seeing `SCOPE_invoices.read` does not imply `ROLE_ACCOUNTANT`; seeing `ROLE_ACCOUNTANT` does not automatically imply `invoice:read`; seeing `invoice:read` does not imply permission to read invoices belonging to another tenant.

An API policy for reading invoices might require all of the following simultaneously:

~~~text
ALLOW =
  authenticated
  AND token has invoices.read
  AND subject has invoice:read (directly or via role)
  AND invoice.tenantId == caller.tenantId
  AND (invoice.ownerId == caller.id OR has unit-wide view permission)
~~~

This is an **illustrative application-defined policy**, not a universal formula enforced automatically by Spring Security. Applications not using OAuth can omit the token scope condition; exact business requirements dictate how conditions combine.

## 8. Real-World Comparison Scenarios

Given invoice `INV-01` belonging to tenant `T1`, owner `lan`. The API uses an access token with scope `invoices.read`. Someone with `FINANCE_ADMIN` may read invoices of any owner **within their own tenant**, but must still hold the token scope.

| Caller | Business Role/Permission | Token Scope | Tenant | Relationship | Result |
|---|---|---|---|---|---|
| Lan | `invoice:read` | `invoices.read` | T1 | Owner | **Allow** |
| Lan | `invoice:read` | None | T1 | Owner | **Deny:** missing scope |
| Lan | `invoice:read` | `invoices.read` | T2 | Different tenant | **Deny:** wrong tenant |
| Minh | `FINANCE_ADMIN` | `invoices.read` | T1 | Not owner | **Allow** per admin policy |
| An | No read permission | `invoices.read` | T1 | Owner | **Deny:** scope does not replace permission |

Key takeaway: **action permission, token permission, and resource-level permission are separate check dimensions**.

## 9. Java 17 Practice: Modeling an Authorization Decision

This is a **standalone plain Java program** used to understand the relationship among the four concepts. The `FINANCE_ADMIN` role in code is a business name, **not yet** mapped to Spring Security's `ROLE_FINANCE_ADMIN` authority.

Save as `AccessDecisionExample.java`:

~~~java
import java.util.Set;

public class AccessDecisionExample {
    record Caller(
            String id,
            Set<String> roles,
            Set<String> permissions,
            Set<String> tokenScopes,
            String tenantId) {
    }

    record Invoice(String id, String ownerId, String tenantId) {
    }

    static boolean canRead(Caller caller, Invoice invoice) {
        boolean admin = caller.roles().contains("FINANCE_ADMIN");
        boolean hasBusinessPermission =
                admin || caller.permissions().contains("invoice:read");
        boolean tokenAllowsRead =
                caller.tokenScopes().contains("invoices.read");
        boolean sameTenant =
                caller.tenantId().equals(invoice.tenantId());
        boolean allowedObject =
                admin || caller.id().equals(invoice.ownerId());

        return hasBusinessPermission
                && tokenAllowsRead
                && sameTenant
                && allowedObject;
    }

    public static void main(String[] args) {
        Invoice invoice = new Invoice("INV-01", "lan", "T1");

        Caller lan = new Caller(
                "lan", Set.of("VIEWER"), Set.of("invoice:read"),
                Set.of("invoices.read"), "T1");

        Caller missingScope = new Caller(
                "lan", Set.of("VIEWER"), Set.of("invoice:read"),
                Set.of(), "T1");

        Caller wrongTenant = new Caller(
                "lan", Set.of("VIEWER"), Set.of("invoice:read"),
                Set.of("invoices.read"), "T2");

        Caller admin = new Caller(
                "minh", Set.of("FINANCE_ADMIN"), Set.of(),
                Set.of("invoices.read"), "T1");

        System.out.println("lan: " + canRead(lan, invoice));
        System.out.println("missingScope: " + canRead(missingScope, invoice));
        System.out.println("wrongTenant: " + canRead(wrongTenant, invoice));
        System.out.println("admin: " + canRead(admin, invoice));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac AccessDecisionExample.java
java AccessDecisionExample
~~~

Exact stdout:

~~~text
lan: true
missingScope: false
wrongTenant: false
admin: true
~~~

Lan has the required permission, scope, and data constraints. `missingScope` is denied despite being the owner; `wrongTenant` is denied despite having the same ID and permission; admin is allowed by the explicit policy yet remains bounded by tenant/scope. In a real application, roles/permissions must come from the server/IAM, scopes from a verified token, and tenant/owner from trusted sources.

## 10. Implementing the Idea with Spring Security Servlet

### 10.1. Checking at HTTP

The snippet is **a Spring configuration class**, not a standalone Java program. It fits the Spring Boot 3.x / Spring Security 6.x style when a project uses Spring Security Servlet and OAuth 2.0 Resource Server with properly configured/validated JWTs.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.write")
                .requestMatchers("/api/admin/**")
                    .hasRole("FINANCE_ADMIN")
                .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Explanation:

- `hasAuthority("SCOPE_invoices.read")` requires the authority corresponding to the read scope under default JWT mapping.
- `hasRole("FINANCE_ADMIN")` requires `ROLE_FINANCE_ADMIN` when using the default role prefix.
- **The default JWT converter maps scopes to `SCOPE_*`, and does not automatically map custom role claims into `ROLE_FINANCE_ADMIN`.** To use roles issued by an IdP, you must configure a suitable converter and verify which claims are trustworthy.
- `anyRequest().denyAll()` denies URLs without defined rules; in a real project, intentionally declare required public/health endpoints.
- Resource Server/JWT dependencies and configuration (issuer, keys, validation) are required. This snippet does not issue access tokens itself.
- For `GET /api/invoices/{id}`, checking scope at the HTTP layer is **insufficient** to ensure the caller may view that specific invoice; ownership/tenant logic must still run in the business layer.

If you need to check an internal permission such as `invoice:read`, you can use `hasAuthority("invoice:read")` **after** authentication has placed that permission into `GrantedAuthority`. Never swap the string name and assume a mapping already exists.

### 10.2. Checking at method/service

`@EnableMethodSecurity` activates annotation-based checks such as `@PreAuthorize` on Spring-managed methods. For example, the following condition can be placed on a method accepting an `invoiceId` parameter:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoices.read') " +
    "and @invoicePolicy.canRead(authentication, #invoiceId)"
)
~~~

This is an **annotation illustration**, depending on an `invoicePolicy` bean built by the application itself. That bean must verify business permissions and the record's relationship to the caller using trusted data. Spring must resolve the `invoiceId` parameter name (e.g., via `-parameters` or explicit declaration), and the call must go through Spring method security. Self-invocation within the same instance can bypass proxy advice.

You can organize three layers of defense:

1. **HTTP boundary:** authentication, token scopes, and route rules.
2. **Service/use case:** business permissions, tenant, owner, state.
3. **Data access:** queries scoped by tenant/subject where appropriate, avoiding returning the wrong records.

Do not rely on hiding buttons in the frontend: a client can still call the API directly.

## 11. Related Authorization Models

- **RBAC:** assign roles, then allow/block operations based on roles. Easy to operate, though often needs object-level conditions added.
- **Permission-based policy:** check specific capabilities such as `invoice:approve`. Permissions can be aggregated through roles.
- **ABAC:** examine attributes of subject, action, resource, and environment (e.g., tenant, owner, status, time).
- **Object relationships:** owner, shared user, group member, or relationship between resource and subject.

These models can **be combined**. Spring Security provides decision enforcement points and extensions; it does not define all business rules of a specific system by itself.

## 12. Common Mistakes

| Mistake | Consequence and Fix |
|---|---|
| Treating `hasRole("ADMIN")` and `hasAuthority("ADMIN")` as identical | Under the default prefix, the role requires `ROLE_ADMIN`. Check the actual authority name. |
| JWT has `scope=invoices.read` and checking `hasAuthority("invoices.read")` | By default the created authority is `SCOPE_invoices.read`. Check the converter in use. |
| Assuming `ROLE_ACCOUNTANT` automatically grants `invoice:read` | Must have a role → permission mapping or explicit policy; the framework does not infer it. |
| Having an OAuth scope means viewing all records | Must check tenant, owner, and business policies. |
| Accepting self-declared role/tenant from request body/header | Data is easily forged; use trusted server sources or verified tokens. |
| Using only `isAuthenticated()` | Authentication is not equivalent to permission to perform an action. |
| Checking only in UI/controller | Services or APIs may be invoked via other paths; protect at the business layer. |
| Assuming roles inherit automatically | Hierarchy exists only when configured; test effective permissions. |
| Forgetting to enable `@EnableMethodSecurity` | Method annotations may not take effect; also watch out for self-invocation/proxies. |
| Writing overly broad/misordered URL matchers | Rules are evaluated in order; put specific rules first and choose an explicit default deny. |

**401 and 403:** missing authentication or invalid tokens typically lead to `401 Unauthorized`, whereas authenticated callers lacking permission typically receive `403 Forbidden`. Exact responses depend on filter chain, entry point, and access-denied handler configuration.

## 13. Design Checklist for a New Feature

For an "approve invoice" feature, answer all of these completely:

1. **Who calls it?** User or service client, and how are they authenticated?
2. **What action?** Is the exact permission `invoice:approve` or another name?
3. **Which roles?** Which roles receive the permission, and are there exceptions?
4. **Which authority source?** Database, IAM, JWT claims; where is the mapping done?
5. **Which OAuth scope?** Does the access token need `invoices.approve`?
6. **Which resource?** Same tenant? Who is the owner? Valid invoice status?
7. **Which enforcement points?** Request, service, repository; avoid bypass paths.
8. **Which negative tests?** Missing role, missing permission, missing scope, different tenant, different owner, wrong status, expired token.

Always include a test for **right action permission, wrong object**. That is the scenario most likely to leak data when an authorization model relies solely on roles.

## 14. Takeaways and Self-Check Questions

- **Role** is a group of responsibilities, **permission** is the capability to perform an operation, **authority** is the permission representation Spring Security matches, and **OAuth scope** is the access scope granted to a token/client.
- Roles, permissions, and OAuth scopes **can** be represented as authorities after mapping; do not conflate them.
- With the default prefix, `hasRole("X")` usually corresponds to requiring `ROLE_X`; `hasAuthority("X")` requires exact `X`.
- `SCOPE_*` is how Spring Security Resource Server typically represents scopes, and does not replace tenant/ownership constraints.
- Safe authorization decisions must inspect **subject + action + resource + context**, preferring to deny when conditions are missing.

**Self-check:**

1. A JWT only has scope `reports.read`, no roles. Will `hasRole("REPORTER")` pass automatically? **No**, because no `ROLE_REPORTER` has been mapped.
2. A user has `invoice:read` but the invoice belongs to another tenant. Can they read it? **No**, if the tenant policy requires the same organization.
3. Has `hasAuthority("SCOPE_invoices.read")` checked permissions on each individual invoice? **No**, it only checks a single authority.
4. Does the `ADMIN` role inherently grant access to all tenants? **No**; cross-tenant privileges must be explicitly defined by policy, tested, and monitored.

### Official References

- Spring Security – Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 – OAuth 2.0 Resource Server JWT (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html