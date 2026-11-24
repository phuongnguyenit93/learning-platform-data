# Authorization: Who Can Perform Which Action on Which Resource?

## 1. The Nature of Authorization

**Authorization** is the process of deciding whether an identified principal is allowed to perform **a specific action on a specific resource, in the current context**. This decision can be written as:

~~~text
allow = policy(subject, action, resource, context)
~~~

Four components must be clearly separated:

| Component | Question to Answer | Example |
| --- | --- | --- |
| `subject` | **Who** is requesting? | User `alice`, service account, principal extracted from JWT/session |
| `action` | What do they want **to do**? | Read, edit, delete, approve, export report; HTTP GET/POST/DELETE are signals but insufficient to describe business intent |
| `resource` | What is being **acted upon**? | Document `doc-42`, order `order-17`, a sensitive data field |
| `context` | Which conditions must hold? | Tenant, owner, transaction state, access hours, classification level, relationship to the resource |

The typical outcome is `ALLOW` or `DENY`. **Being logged in does not mean having permission**. For the same person and the same action, the result can differ across two resources: Alice may read a document owned by Alice, but may not read Bob's private document.

Example policies in a document system:

- Alice has the `document:read` permission, is in the same tenant, and is the owner of `doc-1` → allowed to read.
- Bob has the `document:read` permission and is in the same tenant, but does not own `doc-1` → denied if the document is private.
- A tenant administrator has `document:delete` and policy allows administrators to delete documents within the tenant → allowed to delete.
- A tenant A administrator is not automatically allowed to read tenant B data.
- An unauthenticated user cannot access private documents, even if they know the exact URL or ID.

This is the core of the question **“who can perform which action on which resource”**: a general permission such as `document:read` may only be a **necessary condition**, not sufficient to grant access to each individual record.

## 2. How Authentication and Authorization Differ

| | Authentication | Authorization |
| --- | --- | --- |
| Question | “Who are you?” | “Are you allowed to do this?” |
| Primary data | Credentials, session, token, identity | Principal, authorities, action, resource, policy |
| Outcome | Establish an authenticated identity or fail | Allow/deny an operation |
| Example | Verify valid password/JWT | Is Alice allowed to delete document `doc-1`? |

In a typical application, authentication runs first to create an `Authentication` representing the principal; next, authorization uses that information alongside the resource and business rules. Public APIs may allow unauthenticated access; private APIs must enforce the corresponding conditions.

**Do not use client-supplied data** such as `userId`, `ownerId`, `role`, or `tenantId` in the body/query as proof that the caller has permission. Identity and permissions must come from a trusted source after authentication; resource identifiers in the URL are only the target to be checked.

## 3. Three Check Axes and Two Protection Layers

An understandable design starts from the triple `(principal, action, resource)`:

1. **Principal**: which user/service? Which verified authorities, roles, and tenant does the system associate with them?
2. **Action**: read, create, update, delete, approve, or export data? Avoid treating all GET operations as identical or all POST operations as identical when their business meanings differ.
3. **Resource**: which resource type and **which specific instance**? Who owns the record, which tenant does it belong to, and does its state allow modification?

In Spring Security, two layers usually must work together:

- **Request-level authorization**: checks the path and HTTP method directly in the security filter chain. For example, GET `/documents/**` requires `document:read`, DELETE `/documents/**` requires `document:delete`.
- **Method/domain-level authorization**: checks the business operation and permission on a **specific record** in the service. For example, only the owner or an authorized user may edit `doc-42`, after checking the tenant.

The URL layer is useful for blocking early, but **does not prove the user has permission for every ID** matching the URL. If the service is called from REST, a scheduler, a message consumer, or another service, checking at the business layer provides consistent protection. Conversely, methods not marked for protection do not automatically get `@PreAuthorize`; request configuration should include a default deny rule.

## 4. Role, Authority, Permission, and Resource Policies

A **Role** groups responsibilities, such as `USER`, `EDITOR`, `ADMIN`. An **Authority/permission** represents a specific capability, such as `document:read`, `document:publish`, `invoice:approve`. With Spring Security defaults:

- `hasRole("ADMIN")` checks the authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` checks the exact string `ROLE_ADMIN`.
- `hasAuthority("document:read")` checks the exact string `document:read`.
- The `ADMIN` role does not automatically “bypass all checks”; the application must explicitly define what this role permits.

Three common models can be combined:

| Model | Rule | Best suited for |
| --- | --- | --- |
| **RBAC** (role-based) | `ADMIN` approves configuration, `EDITOR` edits content | Stable permissions grouped by responsibility |
| **ABAC** (attribute-based) | Only edit order when `status=DRAFT`, same tenant, matching department | Decisions depending on attributes/context |
| **Relationship/ownership** | Owner can read document; project member can view record | Permissions tied to individual resources and relationships |

For example, a realistic policy might be: the user has `document:write` **and** is in the same tenant **and** (is the owner **or** was granted edit access) **and** the document is not locked. If any required condition is missing, the result is deny. In a multi-tenant system, a “tenant A admin” is usually only allowed to administer **scope A**; a system-wide permission, if needed, must be defined separately.

## 5. Practice: Standalone Pure Java 17 Policy Model

The small example below cleanly separates who, action, and resource. It **does not replace Spring Security**, but helps validate decision logic before attaching policies to an API. All records and code are Java 17 compatible.

**File `AuthorizationDecisionDemo.java`:**

~~~java
import java.util.Set;

record Actor(String name, String tenant, Set<String> permissions, boolean admin) {}
record Document(String id, String owner, String tenant) {}

public class AuthorizationDecisionDemo {
    static boolean allow(Actor actor, String action, Document doc) {
        // Fail closed: missing subject/resource or wrong tenant => deny.
        return actor != null && doc != null
                && actor.tenant().equals(doc.tenant())
                && actor.permissions().contains(action)
                && (actor.admin() || actor.name().equals(doc.owner()));
    }

    public static void main(String[] args) {
        Document doc = new Document("doc-1", "alice", "tenant-a");
        Actor alice = new Actor("alice", "tenant-a",
                Set.of("document:read"), false);
        Actor bob = new Actor("bob", "tenant-a",
                Set.of("document:read"), false);
        Actor admin = new Actor("admin", "tenant-a",
                Set.of("document:read", "document:delete"), true);
        Actor otherTenant = new Actor("root", "tenant-b",
                Set.of("document:read", "document:delete"), true);

        System.out.println("alice read: "
                + allow(alice, "document:read", doc));
        System.out.println("bob read: "
                + allow(bob, "document:read", doc));
        System.out.println("admin delete: "
                + allow(admin, "document:delete", doc));
        System.out.println("alice delete: "
                + allow(alice, "document:delete", doc));
        System.out.println("other tenant read: "
                + allow(otherTenant, "document:read", doc));
    }
}
~~~

Run from the directory containing the file, with JDK 17 or later:

~~~bash
javac --release 17 AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
~~~

**Exact stdout:**

~~~text
alice read: true
bob read: false
admin delete: true
alice delete: false
other tenant read: false
~~~

Explanation of each result:

1. Alice has the read permission, matching tenant, and is the document owner → `true`.
2. Bob has the read permission but is not the owner → `false`.
3. Admin has the delete permission, matching tenant, and has the admin flag → `true`.
4. Alice is the owner but **lacks the delete permission** → `false`.
5. An “Admin” belonging to another tenant is blocked **before** evaluating admin privilege → `false`.

The `admin` flag is only a learning model, not trusted proof when sent by a client. In a real application, role/permission/tenant must come from the authenticated identity and server-side permission data. A real delete operation may also require checking document state, approval workflows, and audit logging.

## 6. Applying to Spring Security (Servlet)

In Spring Security, `SecurityContext` holds the `Authentication` of the authenticated request; `Authentication` contains the name/principal and a set of `GrantedAuthority`. `AuthorizationManager` uses this data to make decisions. For Servlet applications, `AuthorizationFilter` typically enforces HTTP policies; Method Security can enforce further checks at Spring bean method invocations.

Example **illustrative configuration** in a Spring Boot application with Spring Web and Spring Security, using Java 17+; this is a configuration class to place in a Spring project, **not a standalone Java program run with `javac`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class AuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/documents/**")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.DELETE, "/documents/**")
                    .hasAuthority("document:delete")
                .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Reading the configuration in order:

- GET public paths matching `/public/**` require no permission; `permitAll()` is an **intentional** exception.
- GET `/documents/123` requires authority `document:read`; DELETE on the same URL requires `document:delete`.
- All remaining requests are rejected by `denyAll()` (default-deny rule).
- **Matcher order matters:** Spring Security picks the first matching rule. Placing `anyRequest()` before specific rules makes the configuration wrong/invalid.
- `@EnableMethodSecurity` enables annotations such as `@PreAuthorize` on Spring-managed beans. Merely adding the Spring Security dependency does not automatically enable all method checks.
- The example focuses on **authorization**; it does not yet configure login mechanisms (HTTP Basic, session/form, JWT/resource server...), user stores, or endpoints. Real integration must configure appropriate authentication.

Example method-level authorization:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public Document readDocument(String documentId) {
    // Business step: load the exact document, check tenant and permissions
    // for documentId (owner, shared users, status...), then return the data.
    // Concrete details are omitted here to focus on the authorization boundary.
}
~~~

The method snippet above is an **illustrative logic outline**, not independently compilable because `Document`/repository and the implementation body are not declared. The `hasAuthority` rule only confirms read permission **at the action level**; the application must check permission **on the requested document**. To put resource conditions into the annotation, you can delegate to a policy bean using SpEL, for example `@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")` where `#p0` is the first parameter and `documentPolicy` is an application-provided bean. This bean must query trusted data/relationships and return the accurate result for the specific resource; do not infer from client-sent IDs.

Another approach is to keep `@PreAuthorize` for the action permission, then check the domain policy in the service and throw `AccessDeniedException` when permissions are insufficient. Either approach must be invoked **before returning data or causing side effects**. For edit/delete operations, the check and state change need an appropriate transaction boundary/update condition to avoid *time-of-check vs time-of-use* race conditions.

### Typical HTTP Decision Flow

~~~text
Client sends request GET /documents/doc-1
    |
    v
Authentication filter checks session/token and builds Authentication
    |
    v
AuthorizationFilter reads HTTP method + path + authorities
    |-- insufficient document:read --> deny
    |
    v
Controller -> Service (may be subject to @PreAuthorize)
    |
    v
Policy loads document, checks tenant, owner/sharing, status
    |-- condition not met --> deny (AccessDeniedException)
    |
    v
Execute business logic and return permitted data
~~~

**A filter-level decision cannot replace a data-level decision.** If an attacker changes `/documents/1` to `/documents/2` and both match the URL, only a check tied to the document prevents unauthorized IDOR/BOLA access.

## 7. Handling Denials and HTTP Semantics

- **Unauthenticated** when an endpoint requires identity: typically an API system returns `401 Unauthorized` with a challenge if a mechanism like HTTP Basic/Bearer is used; a form-login app may redirect to the login page. Exact behavior depends on the authentication entry point.
- **Authenticated but lacking permission**: usually `403 Forbidden`. Spring Security raises/translates the denial through `AccessDeniedException` and handles it in the security exception flow.
- **Resource does not exist**: may return `404 Not Found`; some systems intentionally return 404 to limit leaking resource existence, but the policy must be consistent.
- `permitAll()` means the request is allowed past this rule layer; it **does not guarantee** the business data is allowed to be viewed, nor does it bypass input validation or other protections.
- **CSRF is not authorization.** With browsers/cookies/sessions and state-changing requests, CSRF protection remains important; a role-valid DELETE can be blocked by CSRF if the token is missing. Do not disable CSRF just to make a DELETE example succeed.
- Do not return sensitive details such as internal permission lists, secret owners, or policy structure in error messages to clients; log in a controlled manner to support investigation.

## 8. Testing with a Subject × Action × Resource Matrix

Do not test only valid users. At a minimum, include **denied** cases to detect horizontal authorization flaws (different user with same role) and vertical ones (lower role invoking higher functionality):

| Actor / state | Action and resource | Expected | Decision condition |
| --- | --- | --- | --- |
| Unauthenticated | GET private document | Deny read | Missing identity; handled by auth entry point |
| Alice, has `document:read` | GET Alice's document in tenant A | Allow read | Has permission, matching tenant, matching owner |
| Bob, has `document:read` | GET Alice's private document in tenant A | Deny | Has permission but wrong owner |
| Alice, lacks `document:delete` | DELETE Alice's document | Deny | Owner does not substitute for action permission |
| Tenant A admin | DELETE tenant A document | Allow **if** policy defines it and all other conditions hold | Authority + tenant + admin rule |
| Tenant B admin | GET tenant A document | Deny | Block cross-tenant access |
| Any actor | Undeclared operation | Deny | Deny-by-default |
| Authorized actor | Edit document in locked state | Deny if policy forbids | Business state condition |

In Spring MVC tests, you can use `spring-security-test` and `@WithMockUser(username = "alice", authorities = "document:read")` or `MockMvc` with the corresponding user/token. Verify both **status and actual data**: an endpoint returning 200 while leaking someone else's record is still a bug. For state-changing requests, configure CSRF and the corresponding test helpers; ensure denied operations **cause no side effects**. Prefer unit tests of the service policy with real/mocked resources and integration tests across filter → controller → service to catch missing layers.

## 9. Common Mistakes and How to Fix Them

1. **“Logged in means allowed to view”:** using only `authenticated()` for sensitive endpoints. → Add per-action permissions and object-level permission checks.
2. **Confusing role with authority:** using `hasRole("ADMIN")` when the principal only has `ADMIN`, or manually adding `ROLE_` to parameters incorrectly. → Inspect actual `GrantedAuthority` values; remember the default prefix convention.
3. **Protecting only the URL:** checking GET `/documents/{id}` has `document:read` and skipping owner/tenant verification. → Check the actual ID in service/repository to prevent BOLA/IDOR.
4. **Trusting client parameters:** accepting `?isAdmin=true` or `tenantId` from the client as the basis for granting access. → Obtain principal and tenant from the authenticated source and compare against server-side data.
5. **Checking after exposing data/writing DB:** running the policy after returning a DTO, sending an event, or updating. → Decide before side effects; for concurrent updates, enforce conditions in the transaction/query.
6. **Overly broad default authorization:** `anyRequest().permitAll()`, ambiguous matchers, or wrong ordering. → Specific rules first, `anyRequest().denyAll()` for undeclared paths when appropriate.
7. **Assuming every `@PreAuthorize` runs:** forgetting `@EnableMethodSecurity`, calling an internal method via `this` (self-invocation) bypassing the Spring proxy, or calling an object created manually with `new`. → Place rules on Spring beans and verify the actual call path.
8. **Using broad roles instead of context checks:** tenant A admin reading all tenants, or editor editing locked documents. → Policies must combine tenant + state + owner/sharing + permission.
9. **Only happy-path tests:** missing different owner, different tenant, missing permission cases. → Build an allow/deny matrix and verify both data and side effects.
10. **Confusing 401 with 403:** treating every denial as “unauthenticated”. → Distinguish failed authentication from authenticated but insufficient permissions; check the authentication entry point, access-denied handler, and CSRF separately.

## 10. Process for Designing a New Policy

When adding a feature such as “approve invoice”, answer in sequence:

1. **Who?** `ACCOUNTANT`, `APPROVER`, background service; which permissions are verified from the real identity?
2. **Do what?** `invoice:read`, `invoice:approve`, `invoice:cancel`; clearly distinguish each business action.
3. **On which resource?** Which invoice ID, which tenant, creator/approver, current state?
4. **When is it allowed?** For example, only someone with `invoice:approve`, same tenant, different from the creator, invoice currently `PENDING`.
5. **Where to attach rules?** Block coarse-grained permissions at the request level; enforce data-level permissions in the service; control queries/transactions to prevent leaks or invalid writes.
6. **How to prove correctness?** Write allow/deny tests across actor, action, resource, and context, while verifying no side effects occur on deny.

**Self-check question:** Bob and Alice share the `EDITOR` role. Can Bob edit Alice's document? **You cannot conclude from the role alone.** You must know the policy on ownership/sharing, tenant, state, and edit permission. This is why authorization always requires **who + action + resource + context**.

### Official Reference Documentation

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
