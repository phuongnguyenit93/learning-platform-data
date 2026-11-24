# Owner- and Organization-Based Authorization at Both HTTP and Service Layers

**Scope:** **Spring Security Servlet / Spring MVC** integrated practice, Java 17+, Spring Boot 3.x, Spring Security 6.x. The goal is to protect data by **owner** and **organization/tenant** at **both boundaries**: HTTP endpoints and service methods. The practice uses a small document-management app with Java code, security configuration, MockMvc/integration tests, IDOR/BOLA attack cases, transaction/TOCTOU notes, multi-tenant operations, and a testing checklist.

**Problem:** user Alice belongs to organization `acme` and created document `doc-a`. Bob also belongs to `acme` but **is not the owner**; Carol belongs to `zen`. Account `auditor` is an auditor for `acme` who can **read** documents of acme members but **cannot edit** documents they do not own. The application must block Bob from reading/editing `doc-a`, block Carol from crossing tenant boundaries, allow Alice to read/edit her own document, and allow the auditor read-only access within their authorized organization. **Never trust** client-supplied owner/organization fields unless verified.

## 1. Why Aren't .authenticated() or .hasRole("USER") Enough?

A `SecurityFilterChain` having only:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/docs/**").authenticated()
    .anyRequest().denyAll()
)
```

blocks unauthenticated users, yet **any authenticated account** can still attempt:

```http
GET /api/docs/doc-a HTTP/1.1
Authorization: Basic ...
```

If the controller calls `repository.findById("doc-a")` and returns the data directly, Bob can read Alice's document even though Bob was never granted access. This is **Broken Object Level Authorization (BOLA)**, commonly called **Insecure Direct Object Reference (IDOR)** when clients swap IDs to access other objects.

Similarly, checking only `ROLE_ADMIN` breaks in a multi-organization app: Alice being an admin of org A **does not** make her an admin of org B. An authority like `ORG_AUDITOR` or `ORG_ADMIN` must be scoped to a **specific org**, not an unscoped "system-wide admin" boolean.

### 1.1 Conditions That Must Hold Simultaneously

For a document **read** request, the example policy is:

```text
Read is allowed if and only if:
    (1) Actor is authenticated
AND (2) Actor is a member of the requested org
AND (3) Document actually belongs to that org
AND (4) (
         Actor is the document owner
         OR Actor holds auditor permission for that exact org
        )
```

For a document **edit** request:

```text
Edit is allowed if and only if:
    (1) Actor is authenticated
AND (2) Actor is a member of the requested org
AND (3) Document actually belongs to that org
AND (4) Actor is the document owner
```

This practice intentionally prevents the auditor from editing others' documents to highlight that **read** and **edit** are distinct permissions. Production may have an org admin role with special edit/approval rights, but that must live in a **defined and tested policy**, not be granted automatically just because a role string contains `ADMIN`.

### 1.2 Expected Decision Table

| Actor | Document | Org in URL | Read | Edit | Reason |
| --- | --- | --- | --- | --- | --- |
| alice | doc-a (owner alice, org acme) | acme | Allow | Allow | Correct organization and owner. |
| bob | doc-a | acme | Deny | Deny | Same organization, but neither owner nor auditor. |
| auditor | doc-a | acme | Allow | Deny | Auditor of acme has read-only access. |
| carol | doc-a | acme | Deny | Deny | Not a member of acme. |
| carol | doc-c (owner carol, org zen) | zen | Allow | Allow | Owner belonging to the matching organization. |
| alice | doc-a | zen | Deny | Deny | URL org differs from the object's real org. |
| auditor | doc-c | zen | Deny | Deny | Holds auditor role in acme only. |
| anonymous | doc-a | acme | Deny | Deny | Unauthenticated. |

**Core point:** both `orgId` and `docId` in the URL are **caller-controlled inputs**, not proof of permission. The server must verify them against the **authoritative data sources** for membership and documents.

## 2. Why Protect Both HTTP and Service Layers?

A request can travel through multiple paths:

```text
Internet / Browser / API client
                 │
                 ▼
Spring Security Servlet FilterChain
  - Authenticate principal via Basic/OIDC/JWT/etc.
  - Validate HTTP method and request path
  - AuthorizationManager: actor + org + document + action
                 │
                 ▼
Spring MVC Controller
  - Parse path/body
  - Never accept role/owner from JSON headers
                 │
                 ▼
Spring Service (Spring-managed proxy)
  - @PreAuthorize + DocumentPolicy
  - Re-verify org, owner, and action
                 │
                 ▼
Repository / Database
  - Query scoped by doc_id + org_id
  - Atomic update/transaction with ownership condition
```

**The HTTP boundary** blocks unauthorized requests **before the controller runs**. It also handles HTTP method, path, unauthenticated errors, and CSRF/session behavior. **The service boundary** protects the same logic when invoked from **a new controller, scheduled job, queue consumer, GraphQL resolver, batch import, or another service** bypassing the secured URL. Checking only at HTTP allows internal calls to bypass owner/tenant rules.

In this practice, **both HTTP and service share `DocumentPolicy`**, keeping read/edit decisions consistent. The trade-off is **reading the repository twice**: once in `AuthorizationManager` and once in `@PreAuthorize`. With real data, consider transactions, caching, or coarse-grained HTTP rules paired with fine-grained service rules for efficiency, **while never dropping object-level checks at the data layer**.

### 2.1 Actor, Resource, Action, and Context

A clear policy model requires:

- **Actor:** identity authenticated by Spring Security (`Authentication.getName()` or an immutable account ID); never trust an arbitrary `X-User` header.
- **Resource:** document loaded from the repository, containing `id`, `orgId`, `ownerId`; these fields must come from the server/database.
- **Action:** `READ` or `EDIT`; never reuse one broad permission for every operation.
- **Context:** active membership, org-scoped auditor/admin role, resource status, tenant access policy, plus optional time and audit conditions.

If a real system has immutable user IDs, use the **account ID** in policies instead of usernames that can change or collide across tenants. The demo uses usernames for brevity and test clarity; **do not** treat usernames as durable production identifiers.

## 3. Data Design and Invariants Before Writing Code

Minimal document model:

| Field | Meaning | Who Has Authority to Set It |
| --- | --- | --- |
| `id` | Non-guessable document ID | Server/repository; unique constraint enforced. |
| `orgId` | Organization that actually owns the data | Backend verified from membership/organization. |
| `ownerId` | Current owner | Backend from verified principal and valid ownership-transfer flow. |
| `body` | Document content | Owner allowed to edit per policy. |
| `status` | Draft/archived/locked if present | Business policy, not role alone. |

A production schema might have `documents(id, org_id, owner_id, body, version, status)` and `organization_memberships(account_id, org_id, status, role)`. Membership can be revoked at any time; policies must use **sufficiently fresh authoritative state**, not just long-lived claims issued in a JWT hours earlier when immediate revocation is required.

**Invariants:**

1. `docId` identifies an object; it **never** grants permission to read that object.
2. `orgId` in the route is only a **filter condition**; it must match the real `document.orgId`.
3. `ownerId` must be verified against the actor by the backend, never taken from an unchecked request body.
4. Auditor/admin roles must have **organization scope**, never extrapolated system-wide.
5. Policy **denies on missing data**: missing actor, org, doc, membership, or unexpected input never grants access.
6. Direct service calls must also be blocked.
7. Production updates must enforce permissions at write time to prevent TOCTOU.

## 4. Creating the Spring Boot 3 Project and Dependencies

Generate a Gradle project via Spring Initializr with Java 17+, Spring Boot 3.x, **Spring Web**, **Spring Security**, and **Spring Boot Starter Test**. Add `spring-security-test`. Place Java files in package `com.example.tenancy`.

**`build.gradle` — dependencies section:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Keep the plugins and repositories generated by Spring Initializr; the Spring Boot BOM manages compatible Spring Security versions. The example uses **HTTP Basic + InMemoryUserDetailsManager** to focus on authorization, **not** production login design. `{noop}` passwords are for demo/testing only. Production requires HTTPS, proper password hashing, sessions/cookies or bearer JWTs per architecture, rate limiting, CSRF, and account lifecycle management.

### 4.1 File Structure

```text
src/main/java/com/example/tenancy/
├── TenancyApplication.java
├── SecurityConfig.java
├── OrgDirectory.java
├── Document.java
├── DocumentRepository.java
├── DocumentPolicy.java
├── DocumentHttpAuthorizationManager.java
├── DocumentService.java
└── DocumentController.java
src/test/java/com/example/tenancy/
└── TenancyAuthorizationTest.java
```

Each public class/record resides in a matching Java file, all in the same package so Spring Boot component scanning finds every bean.

## 5. Backend-Managed Accounts and Memberships

### 5.1 Per-Organization Membership and Roles

**`src/main/java/com/example/tenancy/OrgDirectory.java`**

```java
package com.example.tenancy;

import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Component;

@Component
public class OrgDirectory {

    private final Map<String, Set<String>> memberships = Map.of(
        "alice", Set.of("acme"),
        "bob", Set.of("acme"),
        "carol", Set.of("zen"),
        "auditor", Set.of("acme")
    );

    private final Map<String, Set<String>> auditorRoles = Map.of(
        "auditor", Set.of("acme")
    );

    public boolean isMember(String account, String orgId) {
        return account != null && orgId != null
            && memberships.getOrDefault(account, Set.of())
                          .contains(orgId);
    }

    public boolean isAuditor(String account, String orgId) {
        return account != null && orgId != null
            && auditorRoles.getOrDefault(account, Set.of())
                           .contains(orgId)
            && isMember(account, orgId);
    }
}
```

The `Map.of(...)` maps represent an **internal demo membership source**. Clients cannot add memberships via JSON/headers. Production should use a trusted database/directory, caching with TTL/invalidation policies, and auditing for permission changes.

**Never check `role == "admin"` on an unscoped claim** and grant access across all organizations. In a multi-tenant app, someone may be an auditor in `acme` while being a regular user in `zen`.

### 5.2 Demo Authentication

**`src/main/java/com/example/tenancy/SecurityConfig.java`**

```java
package com.example.tenancy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}alice-demo")
                .authorities("ROLE_USER").build(),
            User.withUsername("bob")
                .password("{noop}bob-demo")
                .authorities("ROLE_USER").build(),
            User.withUsername("carol")
                .password("{noop}carol-demo")
                .authorities("ROLE_USER").build(),
            User.withUsername("auditor")
                .password("{noop}auditor-demo")
                .authorities("ROLE_USER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DocumentPolicy policy) throws Exception {

        var readManager =
            new DocumentHttpAuthorizationManager(policy, false);
        var editManager =
            new DocumentHttpAuthorizationManager(policy, true);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orgs/{orgId}/docs/{docId}"
                ).access(readManager)
                .requestMatchers(
                    HttpMethod.PUT,
                    "/api/orgs/{orgId}/docs/{docId}"
                ).access(editManager)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Explanation:**

- `@EnableMethodSecurity` enables `@PreAuthorize` at the service layer.
- `readManager` and `editManager` verify org/owner before the controller is invoked. Only the explicit **GET** and **PUT** matchers reach the policy; all other requests hit `denyAll`.
- `anyRequest().denyAll()` provides **deny by default**, preventing new routes from accidentally needing only authentication.
- `httpBasic` is just the demo authentication mechanism; it does not determine owner/org.
- CSRF remains enabled by default; in tests, `PUT` requires `csrf()`. When browsers send cookies/sessions or cached HTTP Basic, never disable CSRF just to make PUT "work".
- `ROLE_USER` does not grant Alice access to every document. Org membership and org-scoped roles live in `OrgDirectory`, a separate policy source.

**Matcher order matters:** specific GET/PUT rules precede `anyRequest().denyAll()`. Putting `.requestMatchers("/api/**").authenticated()` earlier can bypass owner/org checks for routes below because **the first matching rule wins**. Regression tests must catch this.

## 6. Documents and Repository: Server-Side Data

### 6.1 Document Record

**`src/main/java/com/example/tenancy/Document.java`**

```java
package com.example.tenancy;

public record Document(
    String id,
    String orgId,
    String ownerId,
    String body
) {}
```

A Java `record` is a concise immutable snapshot for the example. `ownerId` and `orgId` are managed by the backend; users can only update `body` through the sample endpoint.

### 6.2 DocumentRepository

**`src/main/java/com/example/tenancy/DocumentRepository.java`**

```java
package com.example.tenancy;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentRepository {

    private final Map<String, Document> documents =
        new ConcurrentHashMap<>(Map.of(
            "doc-a",
                new Document("doc-a", "acme", "alice", "Alice draft"),
            "doc-b",
                new Document("doc-b", "acme", "bob", "Bob notes"),
            "doc-c",
                new Document("doc-c", "zen", "carol", "Carol plan")
        ));

    public Optional<Document> find(String orgId, String docId) {
        if (orgId == null || docId == null) {
            return Optional.empty();
        }

        return Optional.ofNullable(documents.get(docId))
            .filter(doc -> orgId.equals(doc.orgId()));
    }

    public Document replaceBody(
            String orgId, String docId, String nextBody) {

        return documents.compute(docId, (id, current) -> {
            if (current == null || !orgId.equals(current.orgId())) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found"
                );
            }

            // Never change orgId or ownerId from client input.
            return new Document(
                current.id(),
                current.orgId(),
                current.ownerId(),
                nextBody
            );
        });
    }
}
```

**What the repository gets right:** `find(orgId, docId)` requires **matching org**; `replaceBody` updates only the content while preserving owner/org. No update accepts `ownerId` or `orgId` from a request body. `ConcurrentHashMap.compute` updates a document atomically within a **single JVM**.

**What is not production-ready:** the repository is in-memory, resets on restart, and lacks DB transactions, versioning, SQL tenancy, concurrency control, or an ownership-transfer workflow. `replaceBody` currently checks only the org; owner permission is checked at **HTTP and service layers before calling it**. Production must enforce **authorization conditions inside the write query/transaction itself** to prevent owner/membership changes between check and commit (see the TOCTOU section).

## 7. DocumentPolicy: Single Policy Definition for HTTP and Service

**`src/main/java/com/example/tenancy/DocumentPolicy.java`**

```java
package com.example.tenancy;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final OrgDirectory organizations;
    private final DocumentRepository documents;

    public DocumentPolicy(
            OrgDirectory organizations,
            DocumentRepository documents) {
        this.organizations = organizations;
        this.documents = documents;
    }

    public boolean canRead(
            Authentication auth, String orgId, String docId) {
        return allowed(auth, orgId, docId, false);
    }

    public boolean canEdit(
            Authentication auth, String orgId, String docId) {
        return allowed(auth, orgId, docId, true);
    }

    private boolean allowed(
            Authentication auth,
            String orgId,
            String docId,
            boolean editing) {

        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || orgId == null || docId == null) {
            return false;
        }

        String actor = auth.getName();

        if (!organizations.isMember(actor, orgId)) {
            return false;
        }

        return documents.find(orgId, docId)
            .map(document -> {
                boolean isOwner =
                    actor.equals(document.ownerId());

                if (editing) {
                    return isOwner;
                }

                boolean isOrgAuditor =
                    organizations.isAuditor(actor, orgId);

                return isOwner || isOrgAuditor;
            })
            .orElse(false);
    }
}
```

**Reading the policy in order:**

1. Actor must be an authenticated principal, not an anonymous token.
2. Actor must currently be a member of `orgId`.
3. Document must exist **and** belong to the exact `orgId` specified in the request.
4. For editing: owner only. For reading: owner or auditor of that exact org.
5. If data is missing, the document is not found, or the org mismatches: **false/deny**, never fall through to allow.

**Important:** tenant and owner conditions are not interchangeable alternatives. Someone matching `ownerId` whose **membership was revoked**, or who calls a different org, must still be blocked. An auditor of `acme` cannot read `zen` documents.

### 7.1 Why Not Trust a Global Role?

A `ROLE_AUDITOR` authority (if issued in a JWT) does not specify **which organization** the user may audit. Without org binding, an acme auditor could switch `orgId=zen` and inspect another tenant's data. In the demo, `OrgDirectory.isAuditor(actor, orgId)` checks the **same org**. In production, source org-scoped entitlements from a verifiable store; if using JWT claims, verify signature/issuer/audience/expiry along with synchronization/revocation policies.

### 7.2 When System Administrator Access Is Needed

If a real system has **multi-tenant support superadmins**, policy must explicitly define: who grants access, whether a ticket/justification is required, logging/auditing, whether step-up MFA is required, resource boundaries, and legal-hold/privacy restrictions. **Never** simply add `auth.getAuthorities().contains("ROLE_ADMIN")` to bypass all tenant checks. Even superadmin access may need to operate under controlled break-glass mechanisms.

## 8. HTTP Authorization: Per-Request Document + Org Check

Spring Security 6.x uses `authorizeHttpRequests` with `AuthorizationManager`. When a matcher captures `{orgId}` and `{docId}`, `RequestAuthorizationContext.getVariables()` supplies the matched values so the manager can evaluate the policy.

**`src/main/java/com/example/tenancy/DocumentHttpAuthorizationManager.java`**

```java
package com.example.tenancy;

import java.util.function.Supplier;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class DocumentHttpAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final DocumentPolicy policy;
    private final boolean edit;

    public DocumentHttpAuthorizationManager(
            DocumentPolicy policy, boolean edit) {
        this.policy = policy;
        this.edit = edit;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        String orgId = context.getVariables().get("orgId");
        String docId = context.getVariables().get("docId");

        boolean granted = edit
            ? policy.canEdit(authentication.get(), orgId, docId)
            : policy.canRead(authentication.get(), orgId, docId);

        return new AuthorizationDecision(granted);
    }
}
```

**Explanation:**

- The manager distinguishes actions via the `edit` flag, chosen **by the server when configuring GET/PUT matchers**, never letting the client pass `canEdit=true` in JSON.
- `context.getVariables()` reads the variables extracted by `RequestMatcher`; if the matcher/servlet path fails to supply them or values are invalid, `DocumentPolicy` denies.
- `authentication.get()` retrieves the request's Authentication after Spring Security runs the configured authentication mechanism.
- `AuthorizationDecision(granted)` allows or denies **before the controller**.
- `orgId` and `docId` in the URL are not trust signals; the policy still checks membership/document in the backend.

**Compatibility note:** the snippet uses `AuthorizationManager.check(...)`, standard in Spring Security 6.x; some newer releases prefer the `authorize(...)` API. When dependencies change, match the method signature of the **exact Spring Security version in use** and test behavior. Never substitute an arbitrary "mock Authentication" in production.

**Matcher note:** URI variables can behave differently depending on matcher type (MVC/PathPattern/regex), servlet path, and version. This practice uses Spring MVC and standard string `requestMatchers`. If a project has multiple `DispatcherServlet`s, unusual servlet mappings, or custom matchers, configure an explicit `RequestMatcher`, verify `getVariables()` actually returns `orgId/docId`, and run integration tests. If variables are missing, the policy must **deny**, never fall back to "permit all".

### 8.1 Choosing Coarse HTTP vs. Fine-Grained Service Checks

This example **performs full owner/org checks at both HTTP and service layers** to demonstrate defense-in-depth and catch bypasses at either layer. In large systems, querying the DB from the authorization filter can add overhead and race conditions if the service later re-reads different state. A valid alternative is:

- **HTTP:** verify the request is authenticated, holds org membership, and has basic functional permission; do not resolve object ownership at HTTP.
- **Service:** verify full **owner/org/resource state** inside a transaction with scoped queries.

The coarse/fine split can be faster, but never drop object-level checks in the service. When business requirements genuinely call for **both-layer protection** as shown here, keep tests on each boundary and never loosen URL rules arbitrarily.

## 9. Service: Method Security Cannot Be Bypassed by HTTP-Only Policies

**`src/main/java/com/example/tenancy/DocumentService.java`**

```java
package com.example.tenancy;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #p0, #p1)"
    )
    public Document read(String orgId, String docId) {
        return documents.find(orgId, docId).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"
            )
        );
    }

    @PreAuthorize(
        "@documentPolicy.canEdit(authentication, #p0, #p1)"
    )
    public Document edit(
            String orgId, String docId, String newBody) {
        return documents.replaceBody(orgId, docId, newBody);
    }
}
```

**Why `#p0` and `#p1`?** They reference the first and second parameters in method-security SpEL without depending on whether Java parameter names are preserved via the `-parameters` compiler flag. `authentication` is provided by the method-security expression context. Other projects may use `#orgId`/`#docId` if the build guarantees parameter names are retained.

**Why put `@PreAuthorize` on the service?** HTTP `AuthorizationManager` already guards the two existing routes. However, a new controller could call `DocumentService.read(...)` directly, or a scheduled task/queue consumer could reuse the service. When invoked through a **Spring-managed proxy**, the annotation still enforces the policy. An internal `this.read(...)` call within the **same bean** can bypass the AOP proxy and skip `@PreAuthorize`; avoid self-invocation or design explicit policy checks. Unit/integration tests must invoke the Spring-managed bean, not `new DocumentService(...)`, when testing AOP.

**Do not confuse 403 and 404:** `read` has a 404 branch if the document is missing after authorization. In this design, `canRead(...)` denies nonexistent objects first, so requests typically receive **403**. Production APIs may intentionally return **404 uniformly for both nonexistent objects and unauthorized objects** to curb enumeration; however, that is a separate error-handling/threat-model choice, and one should not claim `@PreAuthorize` returns 404 by default.

### 9.1 Method Security Does Not Replace Transaction Isolation

Between two steps:

```text
T0: DocumentPolicy reads doc-a owned by Alice in org acme -> allow
T1: Another operation transfers owner or revokes membership
T2: DocumentService edits doc-a
```

**time-of-check/time-of-use (TOCTOU)** can occur. The in-memory example keeps owner and org fixed for clarity, whereas production supporting ownership transfer, org moves, or membership revocation needs DB-level transaction/atomic write guards. See Section 12.

## 10. Controller: Accepts Path and Content Only, Never Client-Declared Permissions

**`src/main/java/com/example/tenancy/DocumentController.java`**

```java
package com.example.tenancy;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/api/orgs/{orgId}/docs/{docId}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String read(
            @PathVariable String orgId,
            @PathVariable String docId) {
        return service.read(orgId, docId).body();
    }

    @PutMapping(
        value = "/api/orgs/{orgId}/docs/{docId}",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String edit(
            @PathVariable String orgId,
            @PathVariable String docId,
            @RequestBody String nextBody) {
        return service.edit(orgId, docId, nextBody).body();
    }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
```

Clients have no `ownerId` or `orgId` field in the body to escalate privileges; the path contains `orgId`, yet the server **verifies membership and `document.orgId`**. In a real API, validate body size, content type, data schema, concurrency version, and audit updates.

**`src/main/java/com/example/tenancy/TenancyApplication.java`**

```java
package com.example.tenancy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenancyApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenancyApplication.class, args);
    }
}
```

Place these files in the same package and run with:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If testing HTTP Basic outside localhost, require **HTTPS** to protect credentials from interception in transit; only use `-demo` passwords in learning environments. The `curl` commands below are **illustrative requests**; actual responses depend on the app starting cleanly and the CSRF/session configuration.

## 11. Quick HTTP Checks and Observing 200/401/403

Expected results with the demo and initial data:

```bash
# Anonymous: public health = HTTP 200.
curl -i http://localhost:8080/health

# Alice reads her own document: HTTP 200, body "Alice draft".
curl -i -u alice:alice-demo \
  http://localhost:8080/api/orgs/acme/docs/doc-a

# Bob is in acme too, but not the owner: HTTP 403.
curl -i -u bob:bob-demo \
  http://localhost:8080/api/orgs/acme/docs/doc-a

# Acme auditor reads Alice's document: HTTP 200.
curl -i -u auditor:auditor-demo \
  http://localhost:8080/api/orgs/acme/docs/doc-a

# Acme auditor cannot read zen document: HTTP 403.
curl -i -u auditor:auditor-demo \
  http://localhost:8080/api/orgs/zen/docs/doc-c

# Missing Authorization: protected document typically returns HTTP 401.
curl -i http://localhost:8080/api/orgs/acme/docs/doc-a
```

Note: `curl -u` sends an HTTP Basic `Authorization` header; the demo enables `httpBasic`. Because the controller returns strings, Spring MVC renders plain text. Whether 401 or 403 is returned is determined by `ExceptionTranslationFilter` and the configured authentication entry point; **never equate 403 with being unauthenticated**.

For `PUT`, Spring Security applies CSRF to unsafe methods by default. Knowing username/password in curl **is not enough** for a valid `PUT` when CSRF protection is active:

```bash
# Missing CSRF, expected 403 in the demo configuration:
curl -i -X PUT -u alice:alice-demo \
  -H "Content-Type: text/plain" \
  --data "New Alice draft" \
  http://localhost:8080/api/orgs/acme/docs/doc-a
```

The lesson tests the valid-CSRF branch using `spring-security-test`. In production browsers, implement a proper CSRF token issuance/submission strategy (`HttpSessionCsrfTokenRepository`, `CookieCsrfTokenRepository`, or suitable equivalent) rather than disabling CSRF just so curl succeeds. For stateless bearer-token APIs without ambient browser credentials, evaluate CSRF under that separate architecture.

## 12. Safe Database Updates: Preventing TOCTOU and Cross-Tenant Writes

In-memory code suffices to learn two-layer authorization, **but it is not how secure mutations are committed in production**.

### 12.1 Pushing Tenant + Owner Conditions into SQL

An **owner-only edit** operation can be expressed in parameterized SQL as:

```sql
UPDATE documents
   SET body = :next_body,
       version = version + 1
 WHERE id = :doc_id
   AND org_id = :org_id
   AND owner_id = :actor_id
   AND version = :expected_version;
```

After the update, require **affected rows == 1** to treat it as successful. Zero rows may mean the document does not exist, wrong org, wrong owner, or a version conflict. Choose an appropriate error contract (403/404/409) without leaking object existence to unauthorized callers.

**Important distinction:** the SQL above verifies the owner at write time, yet **does not verify active org membership**. If membership changes must take effect immediately, use a transaction with appropriate isolation/locking, query `EXISTS` against the membership table in the same operation, row-level security, or another consistency-preserving policy mechanism. Do not merely read membership once in Java and assume it cannot be revoked between steps.

Example adding a simplified membership guard in SQL:

```sql
UPDATE documents AS d
   SET body = :next_body,
       version = version + 1
 WHERE d.id = :doc_id
   AND d.org_id = :org_id
   AND d.owner_id = :actor_id
   AND d.version = :expected_version
   AND EXISTS (
        SELECT 1
          FROM organization_memberships AS m
         WHERE m.account_id = :actor_id
           AND m.org_id = d.org_id
           AND m.status = 'ACTIVE'
   );
```

This is **illustrative SQL**; adapt it to your RDBMS, ORM, transaction isolation level, and consistency requirements. Depending on the database and concurrency, locking/transactions or stronger isolation may still be needed to prevent concurrent membership changes under your semantics. Never conclude "having EXISTS completely eliminates races" across all RDBMSs and isolation levels.

### 12.2 Hibernate/JPA and @Transactional

With Spring Data JPA, repository methods should carry explicit tenant scope like `findByIdAndOrgId(...)`, instead of loading by ID alone and hoping every controller remembers to check the org. Still, query method names **are not automatic authorization**: they only filter data. Users who are already org members still need owner/auditor rules.

With `@Transactional` methods, examine the **AOP interceptor ordering between method security and transactions**, as well as when authorization and data loading occur. If a policy inspects a document snapshot, choose an isolation/locking level or conditional update that avoids stale state. If caching is used, invalidate entries on ownership/org transfers, membership changes, role changes, or account locks.

### 12.3 Row-Level Security (RLS) as Defense-in-Depth

Some RDBMSs (such as PostgreSQL) provide Row-Level Security to enforce policies right in the DB. RLS helps multi-tenant designs, provided:

- The org/user context passed to the DB **cannot be spoofed** and is reset across connection pool reuse.
- Regular application read/write connections never run under a database superuser or `BYPASSRLS` role.
- RLS policies cover both tenant/owner and the exact operation; test direct SQL access with the real DB role.
- RLS does not completely replace Spring Security authorization in API/business workflows.

Tenant leaks can still happen in **caches, search indexes, object storage, or queues** even when SQL uses `WHERE org_id = ...`. Audit every storage/search path against the trust model.

## 13. Writing MockMvc Tests Verifying Both Layers

Include Spring Boot test and `spring-security-test` as in `build.gradle` above. The tests below use the **HTTP Basic postprocessor** so requests run through the demo's authentication filter, not just `@WithMockUser`. `@SpringBootTest` + `@AutoConfigureMockMvc` activates the application's Spring Security filters.

**`src/test/java/com/example/tenancy/TenancyAuthorizationTest.java`**

```java
package com.example.tenancy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class TenancyAuthorizationTest {

    @Autowired MockMvc mvc;
    @Autowired DocumentService service;

    @Test
    void anonymousCannotReadPrivateDocument() throws Exception {
        mvc.perform(get("/api/orgs/acme/docs/doc-a"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice draft"));
    }

    @Test
    void sameOrgDifferentOwnerIsDenied() throws Exception {
        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("bob", "bob-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void crossOrgAttemptAndSpoofedOrgPathAreDenied()
            throws Exception {

        // Carol belongs to zen only, not acme.
        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("carol", "carol-demo")))
            .andExpect(status().isForbidden());

        // Alice cannot swap org in the path to cross tenants.
        mvc.perform(get("/api/orgs/zen/docs/doc-a")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadOnlyWithinAssignedOrganization()
            throws Exception {

        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("auditor", "auditor-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice draft"));

        mvc.perform(get("/api/orgs/zen/docs/doc-c")
            .with(httpBasic("auditor", "auditor-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void putRequiresCsrfAndOwnerPermission() throws Exception {
        String route = "/api/orgs/acme/docs/doc-a";

        mvc.perform(put(route)
            .with(httpBasic("alice", "alice-demo"))
            .contentType(MediaType.TEXT_PLAIN)
            .content("Alice updated"))
            .andExpect(status().isForbidden());

        mvc.perform(put(route)
            .with(httpBasic("auditor", "auditor-demo"))
            .with(csrf())
            .contentType(MediaType.TEXT_PLAIN)
            .content("attacker edit"))
            .andExpect(status().isForbidden());

        mvc.perform(put(route)
            .with(httpBasic("bob", "bob-demo"))
            .with(csrf())
            .contentType(MediaType.TEXT_PLAIN)
            .content("Bob edit"))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanEditWithValidCsrf() throws Exception {
        mvc.perform(put("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("alice", "alice-demo"))
            .with(csrf())
            .contentType(MediaType.TEXT_PLAIN)
            .content("Alice updated"))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice updated"));

        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice updated"));
    }

    @Test
    void unknownOperationIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unknown")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void directServiceCallStillEnforcesOwnerPolicy() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read("acme", "doc-a")
        );
        assertThrows(
            AccessDeniedException.class,
            () -> service.edit("acme", "doc-a", "hijacked")
        );
    }

    @Test
    @WithMockUser(username = "carol", roles = "USER")
    void directServiceCallStillEnforcesTenantPolicy() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read("acme", "doc-a")
        );
    }
}
```

**Important note on test isolation:** the demo `DocumentRepository` is an **in-memory singleton** inside the Spring test application context. `ownerCanEditWithValidCsrf` mutates `doc-a` from `Alice draft` to `Alice updated`. If JUnit runs tests in parallel or reuses the context across test classes, another test asserting the fixed body `"Alice draft"` can become **flaky**. For a production-grade regression suite, **reset fixtures before every test** using a transactional test database or a test-only repository reset method rather than relying on JUnit execution order.

Because the snippet runs in a shared context, **do not enable parallel execution** and do not rely on test ordering. To make tests deterministic even when executed sequentially out of order, add the fixture-reset method below and invoke it in `@BeforeEach`:

**Add to `DocumentRepository.java` for demo/test environments:**

```java
public void resetDemoData() {
    documents.clear();
    documents.put("doc-a",
        new Document("doc-a", "acme", "alice", "Alice draft"));
    documents.put("doc-b",
        new Document("doc-b", "acme", "bob", "Bob notes"));
    documents.put("doc-c",
        new Document("doc-c", "zen", "carol", "Carol plan"));
}
```

**Add to `TenancyAuthorizationTest.java`:**

```java
@Autowired DocumentRepository repository;

@BeforeEach
void resetFixtures() {
    repository.resetDemoData();
}
```

Remember to import `org.junit.jupiter.api.BeforeEach`. `resetDemoData` is a **test convenience**, not an operation to expose through a production controller. When multiple tests run concurrently against the same bean context, resetting a global singleton still races; use isolated contexts, transactions, or test databases. In real systems, manage fixtures with migrations/Testcontainers and roll back transactions where appropriate.

### 13.1 Stratifying the Tests Above

| Test | What It Proves | What It Does Not Prove |
| --- | --- | --- |
| GET Alice → 200 | HTTP + service allow the owner to read. | SQL data isolation if the demo is in-memory. |
| GET Bob → 403 | HTTP blocks a same-org non-owner. | Service method security independently if only tested via HTTP. |
| `service.read(...)` under `@WithMockUser("bob")` → AccessDenied | Method security blocks even outside HTTP. | Production authentication provider behavior. |
| GET Carol other org → 403 | HTTP tenant scoping. | That all other endpoints are protected. |
| Auditor read 200 / edit 403 | Read and edit policies differ; role is org-scoped. | Production auditor role grant/revocation workflows. |
| PUT missing CSRF → 403 | CSRF filter blocks unsafe requests. | That production browsers send tokens properly. |
| PUT owner + CSRF → 200 | HTTP + service + demo update work. | DB transactions or TOCTOU mitigation. |
| GET unknown route → 403 | `anyRequest().denyAll()` does not permit unknown routes. | That every chain in a large system is properly configured. |

**You must test direct service calls too.** If you only run MockMvc and every request is rejected by the HTTP manager before the controller, a service **missing `@PreAuthorize`** would still leave the entire HTTP test suite green. Therefore `@WithMockUser` + `service.read/edit` provides independent evidence for the service layer.

### 13.2 Notes on CSRF and HTTP Methods

CSRF is a **separate check** from owner/org authorization. The practice intentionally keeps default CSRF and uses `with(csrf())` on PUT tests. If a tokenless test returns 403, it has not proven the owner policy ran; you must have a **PUT with valid CSRF but wrong actor/owner** to separate the two layers. The test suite includes both auditor and bob supplying valid CSRF and still receiving 403.

## 14. Unit-Testing the Policy Directly: Fast Matrix Coverage

Beyond HTTP/integration tests, write unit tests for `DocumentPolicy` using the demo repository and directory without starting a Servlet container. This verifies the truth table quickly.

**`src/test/java/com/example/tenancy/DocumentPolicyTest.java`**

```java
package com.example.tenancy;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.junit.jupiter.api.Assertions.*;

class DocumentPolicyTest {

    private final OrgDirectory organizations = new OrgDirectory();
    private final DocumentRepository documents = new DocumentRepository();
    private final DocumentPolicy policy =
        new DocumentPolicy(organizations, documents);

    private Authentication auth(String username) {
        return new UsernamePasswordAuthenticationToken(
            username,
            "not-used",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );
    }

    @Test
    void ownerCanReadAndEdit() {
        assertTrue(policy.canRead(auth("alice"), "acme", "doc-a"));
        assertTrue(policy.canEdit(auth("alice"), "acme", "doc-a"));
    }

    @Test
    void sameOrgDoesNotMeanAnyDocument() {
        assertFalse(policy.canRead(auth("bob"), "acme", "doc-a"));
        assertFalse(policy.canEdit(auth("bob"), "acme", "doc-a"));
    }

    @Test
    void auditorIsOrgScopedAndReadOnly() {
        assertTrue(policy.canRead(
            auth("auditor"), "acme", "doc-a"));
        assertFalse(policy.canEdit(
            auth("auditor"), "acme", "doc-a"));
        assertFalse(policy.canRead(
            auth("auditor"), "zen", "doc-c"));
    }

    @Test
    void wrongOrgAndUnknownDocAreDenied() {
        assertFalse(policy.canRead(auth("alice"), "zen", "doc-a"));
        assertFalse(policy.canRead(auth("alice"), "acme", "missing"));
        assertFalse(policy.canRead(null, "acme", "doc-a"));
    }
}
```

In this test class, each test method gets its own instance under default JUnit Jupiter lifecycle, so there is no shared state unless configured otherwise. However, **unit-testing the policy does not prove Spring AOP `@PreAuthorize` works**; pair it with direct service-call tests as in Section 13.

### 14.1 Cases to Add as Business Rules Grow

- Owner left the org or membership is `SUSPENDED`.
- Auditor role is revoked; how do permissions behave while tokens/sessions have not yet expired?
- Document is archived/locked so nobody can edit, not even the owner.
- Owner moves a document to a new org; what happens to old permissions?
- User holds memberships in two orgs, auditor in one and regular user in the other.
- Document has a null owner (system draft) or legacy data with mismatched org.
- Path variables contain Unicode/encoding/case differences where org ID is normalized differently from the DB.
- Client injects `X-Org-Id`/`X-Owner-Id` headers or an ownerId body field to impersonate.
- Standardized 401/403/404 branches to minimize resource-existence leaks.
- Concurrent transactions transferring ownership or revoking membership between authorization and update.

## 15. Common Security Mistakes in Multi-Tenant Design

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| `findById(docId)` and return directly | Any logged-in user can read any doc ID. | Enforce owner/org in both policy and query. |
| `.authenticated()` for all `/api/**` | No object-level authorization. | Enforce per-resource/action checks, deny by default. |
| Trusting `orgId` from URL without checking `document.orgId` | Callers can change URL to enter another tenant. | Query by `docId + orgId` and verify membership. |
| Trusting `ownerId` from JSON | Client declares itself the owner. | Derive owner server-side from verified principal and transfer policy. |
| Global `ROLE_ADMIN` for an org admin | Admin of one tenant views other tenants' data. | Scope roles/permissions per organization. |
| HTTP checks owner while service does not | Internal callers or new endpoints bypass URLs. | Enforce `@PreAuthorize`/policy on service and test directly. |
| Service checks org membership only | Same-org Bob views Alice's document. | Add resource-level owner/auditor rules. |
| `@PreAuthorize` skipped due to self-invocation | Same-bean calls bypass the AOP proxy. | Call through Spring beans and test method security. |
| Using unverified `Jwt claim org_id` | Forged/expired tokens or stale claims not matching current membership. | Validate decoder/issuer/audience and check authoritative policy. |
| Caching by `docId` without tenant/permission scope | Another tenant receives a cached response. | Scope cache keys/authorization properly; never publicly cache sensitive data. |
| Checking owner then updating unconditionally | TOCTOU after ownership transfer. | Use conditional updates, transactions, and row-count checks. |
| Using Internet `X-Tenant` header as authorization | Caller chooses another tenant at will. | Rely only on verified identity/membership and trusted proxy boundaries. |
| Returning different 404/403 based on doc existence | Allows probing doc IDs or org memberships. | Design a consistent error contract per threat model. |
| Background service job with null principal acting as "auto admin" | Background job runs with overly broad, unaudited rights. | Give jobs scoped service identities, explicit authz, and auditing. |
| Protecting GET while omitting DELETE/EXPORT/WebSocket | Unchecked read/write side paths remain exposed. | Inventory every entrypoint/action and test each separately. |
| Storing tenant identity in ThreadLocal without cleanup | Pooled worker thread carries tenant across requests. | Scope/clean up context and test thread reuse. |

### 15.1 Cross-Tenant Leaks Outside the Database

Even when SQL includes `WHERE org_id`, data can still leak via:

- **Redis/cache:** shared key `doc-a` across tenants or caching API responses without user isolation.
- **Search index:** search filters missing `tenant_id`; aggregations returning hits from other orgs.
- **Object storage:** URLs/signed URLs generated without verifying org/resource ownership, or overly long-lived signed URLs.
- **Exports/reporting:** queue jobs accepting `docId` without verifying actor/tenant when fetching the document.
- **Background jobs:** having no HTTP SecurityFilterChain and calling repositories directly.
- **Logs/traces:** accidentally writing document bodies/PII into shared operational telemetry.
- **WebSocket/SSE:** authenticating the handshake without authorizing individual channels/resources.

**Never treat a single `@PreAuthorize` on one method as system-wide insurance.** Inventory every access path, especially direct repository calls outside standard services.

## 16. 401, 403, 404, and Hiding Resource Existence

### 16.1 401 Means Unauthenticated

With the `httpBasic` demo, unauthenticated requests to private documents typically return **401** and `WWW-Authenticate`. This comes from the authentication entry point, not from an owner comparison. With form login, unauthenticated users typically get a **302 redirect** to the login page.

### 16.2 403 Means Insufficient Permission

An authenticated user failing the owner/tenant policy receives **403**. That does not imply the document exists; in this example the policy also denies when the document does not exist.

### 16.3 Using 404 to Avoid Disclosing Existence

Some APIs choose to return **404 whenever a document does not exist or the actor is not allowed to know it exists**. In that case, standardize the behavior across service/filter layers, logging/auditing, and error mapping so endpoint A does not return 403 while endpoint B returns 404 and creates a side channel. Regardless of status code, **never return the document body** before authorization.

The lesson code returns 403 from the policy step to highlight denial clearly. That is a demo choice, not a requirement that every multi-tenant API must expose 403 instead of 404.

## 17. Sessions, OAuth2/JWT, and Binding Real Users

### 17.1 Authentication Is the Actor Source, Never the URL

In the demo, `Authentication.getName()` is `alice`. In production using OIDC/JWT:

- Verify the token (signature, issuer, audience, expiration, algorithm) with the appropriate Spring Security Resource Server / OIDC Client flow.
- Pick a **stable account ID claim** to map to the internal user.
- Never trust a token not issued for this API even if it has `sub=alice`.
- Org memberships/roles from an IdP can be inputs, but require policies on **freshness, tenant binding, and revoked permissions**.
- Never let callers send `X-User-Id`/`X-Org-Id` to override `Authentication`.

**An OIDC ID token** authenticates the user to the client; it is not automatically a valid access token for a resource server API. When using JWT access tokens, enforce clear policies on `aud`/`scope` and org.

### 17.2 Users Belonging to Multiple Organizations

A user may belong to both `acme` and `zen`. When the UI selects the active org:

1. The client sends an org identifier representing **intent**.
2. The server verifies the user is a member **of that org**.
3. For each document, the server checks `document.orgId` matches the org plus owner/auditor rules.
4. Never store one global tenant variable shared across users in `static`.
5. If using per-request/ThreadLocal context, clear it when the request finishes and across thread hops. Never leave tenant A on a pooled worker thread for request B.

Even an `activeOrgId` kept in a controlled session must be re-checked against membership when permissions can change; never turn a session property into an irrevocable grant.

## 18. Practical Testing and Operations Checklist

### 18.1 Pre-Merge Test Matrix

| Boundary | Positive | Negative |
| --- | --- | --- |
| HTTP authentication | Alice valid Basic → policy evaluated. | Anonymous → 401. |
| HTTP owner | Alice GETs doc-a → 200. | Same-org Bob GETs doc-a → 403. |
| HTTP tenant | Carol reads zen doc-c → 200. | Carol reads acme/doc-a → 403. |
| HTTP scoped auditor | Auditor reads acme doc-a → 200. | Auditor reads zen/doc-c → 403. |
| HTTP edit | Owner PUT + CSRF → 200. | Bob/auditor PUT + CSRF → 403. |
| CSRF | PUT with valid token per session contract. | Missing token → 403. |
| Service owner | `service.read` as Alice → allowed. | `service.read` as Bob → AccessDeniedException. |
| Service tenant | Carol reads zen doc-c → allowed. | Carol calls service with acme/doc-a → denied. |
| Repo scope | `find("acme","doc-a")` returns object. | `find("zen","doc-a")` returns empty. |
| Concurrent update | Owner/org/version match at commit. | Owner changed mid-flight → 0 rows updated. |
| Cache/export/background | Authorized actor processed. | Missing current HTTP user or wrong tenant → denied/audited. |
| Unknown route/method | Only declared endpoints allowed. | Unmatched DELETE/GET → denyAll. |

### 18.2 Production Deployment

- Lock down **immutable** account/organization identifiers and per-org membership/role models.
- Use Spring Security **verified principals**; never trust roles/owners in request payloads.
- HTTP allows only declared routes/methods backed by policy; fallback is `denyAll`.
- Attach `@PreAuthorize`/domain policies to services and test **direct method invocation** through Spring beans.
- Scope all repository queries by tenant; guard updates with owner/org/membership/version conditions inside transactions.
- Separate read/edit/delete/share/approve/export; never grant blanket permissions from a generic role name.
- Implement CSRF protection appropriate for browsers/sessions; verify CORS, cookies, and entry points.
- Use sufficiently fresh scoped roles/org memberships, handle revocation/invalidation, and audit events.
- Prevent leaking object existence or PII via 403/404 differences, timing, cache keys, error logs, or unintended search results.
- Prevent TOCTOU with conditional updates, locking/transactions, and row-count checks.
- Maintain regression tests for cross-owner, cross-tenant, internal service bypass, concurrent ownership changes, and unknown routes.
- When deploying multiple HTTP filter chains or Servlet mappings, check `securityMatcher`/`requestMatchers` order; unmatched routes must never bypass security.
- Monitor denial counts, tenant mismatches, IDOR probing anomalies, false positives, and privileged support/admin flows.

## 19. Summary

**Proper authorization must answer four questions simultaneously: who (actor), which organization (org), which document (resource), and which action (read/edit).** Checking only whether a user is logged in or holds a global role is insufficient.

In the Spring Security Servlet example, the **HTTP `AuthorizationManager`** invokes `DocumentPolicy` to verify **exact org + owner or auditor** by path and HTTP method; the **service `@PreAuthorize`** re-evaluates the same policy so internal calls cannot bypass it. The repository scopes lookups by org/doc, and production must enforce ownership/membership inside **transactions or atomic updates** to prevent TOCTOU.

A trustworthy test suite must prove **owner 200**, **same-org non-owner 403**, **cross-org 403**, **auditor read-only**, **PUT requiring CSRF**, and **direct service calls still blocked**. Combining these layers substantially reduces the risk of BOLA/IDOR and cross-organization data leaks.
