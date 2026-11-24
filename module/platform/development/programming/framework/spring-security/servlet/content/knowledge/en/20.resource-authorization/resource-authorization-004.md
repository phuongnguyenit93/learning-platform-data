# Multi-Tenancy Authorization and Per-Request Tenant Verification — Spring Security Servlet

In a **multi-tenant** system, successful authentication does not mean permission to view every organization. Alice may log in validly and have permission to read documents in `tenant-a`, yet she must not be allowed to read `tenant-b` documents by altering the URL. Even when Alice is a member of **both organizations**, the path `/tenants/tenant-b/documents/doc-a1` still must not return a document actually belonging to `tenant-a` just because the document ID is guessable.

That is the core of **per-request multi-tenant authorization**: identify the organization the request **wants** to access; verify the caller's identity and membership/permissions for that organization; then query resources **strictly within the permitted tenant scope**. A valid session, JWT access token, opaque token, or API key never automatically grants access across all tenants.

This lesson belongs to **Resource Authorization**, in the **Spring Security – servlet** module. We use Java 17+, Spring Security 6.x, and Spring Boot 3.3.5. The complete hands-on example uses HTTP Basic, Spring MVC, `@EnableMethodSecurity`, `@PreAuthorize`, server-side membership, and an in-memory document store. Database, JWT, and Row-Level Security architectures are additional deployment paths, not default components of the lab.

> **The requested tenant is a request input; the authorized tenant is the result of an authorization decision based on trusted identity and policy. Every resource query must preserve the tenant boundary.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **authentication**, **tenant resolution**, **tenant membership**, **tenant-scoped permission**, and **object-level authorization**.
2. Recognize that `tenantId` from path, host, header, query, session, or JWT claim is unverified input to validate, not an automatic license.
3. Design separate READ/WRITE/ADMIN permissions per tenant for the same user.
4. Protect documents with **two simultaneous conditions**: the user has permission in that tenant and the document actually belongs to that tenant.
5. Prevent IDOR/BOLA, tenant spoofing, cache-key collisions, cross-tenant JOINs, and confused deputy issues.
6. Combine `SecurityFilterChain`, `@PreAuthorize`, a policy bean, and a tenant-scoped repository on the Servlet stack.
7. Write tests covering 401, 403, 404, 201, wrong tenant, wrong action, forged headers, missing CSRF, and reading the wrong resource.
8. Explain revoked permissions, cache staleness, thread context, RLS, auditing, and non-HTTP data paths.

## 2. Five Decision Layers in Multi-Tenancy

### 2.1. Authentication: Who Is the Principal?

Spring Security verifies credentials and creates an `Authentication`. A user may have:

~~~text
principal: alice
authenticated: true
authorities: [ROLE_USER]
~~~

This answers "Who is Alice and are her credentials valid?", **not** which organizations Alice belongs to. `ROLE_USER` is a generic role; it must never be interpreted as access to all tenants.

### 2.2. Tenant Resolution: Which Organization Is Requested?

Example:

~~~http
GET /api/tenants/tenant-a/documents/doc-a1 HTTP/1.1
Authorization: Bearer <access-token>
~~~

`tenant-a` in the URL is the **requested tenant**. It may or may not exist, and the caller can freely change it to `tenant-b`. Parsing it into a path variable does not make the tenant trustworthy.

### 2.3. Membership: Which Tenants Does the User Belong To?

Example relationships managed by the **server**:

| Principal | Tenant | Permissions in Tenant |
| --- | --- | --- |
| Alice | tenant-a | documents.read, documents.write |
| Bob | tenant-b | documents.read, documents.write |
| Auditor | tenant-a | documents.read |
| Auditor | tenant-b | documents.read |
| Alice | tenant-b | No membership |

One person can have the editor role in tenant-a yet only be a viewer in tenant-b. Membership also carries active/suspended status, expiration, invitation workflows, and audit trails.

### 2.4. Action Permission: READ Differs from WRITE

Membership does not imply full control. `GET` on a document may require READ; `POST` or `DELETE` requires WRITE/DELETE. Sensitive documents may also require EXPORT, APPROVE, SHARE, or OWNER.

A system-wide `ROLE_ADMIN` must not be used loosely to represent "tenant admin". Platform admin, tenant admin, resource owner, and technical service account are roles with distinct scopes.

### 2.5. Resource Scope: Which Organization Owns the Data?

Even when an auditor can read both tenant-a and tenant-b, a request under tenant-b still must not return `doc-a1` if the document belongs to tenant-a. Therefore, queries must take the form:

~~~text
document = findByTenantIdAndDocumentId(
    authorizedTenantId, documentId)
~~~

rather than merely:

~~~text
document = findById(documentId)
~~~

After scoping, additional owner/ACL checks, tenant status, legal holds, or other business policies may still apply.

### 2.6. Conceptual Formula

~~~text
ALLOW =
  credentialVerified
  AND tenantExistsAndActive
  AND activeMembership(principal, requestedTenant)
  AND hasPermission(principal, requestedTenant, action)
  AND resourceBelongsToTenant(resourceId, requestedTenant)
  AND resourceAclAllows(principal, resourceId, action)
~~~

Not every endpoint has all conditions, but **applicable business conditions must be enforced from trusted sources**, never inferred from a client sending a valid ID.

## 3. Tenant Verification Flow on Every HTTP Request

~~~text
Client:
  GET /api/tenants/tenant-a/documents/doc-a1
            |
            v
Spring Security Servlet FilterChain
  - Verify credentials: Alice
  - HTTP authorization: /api/tenants/** requires authenticated
            |
            v
Spring MVC Controller
  - Parse requested tenant-a and resource doc-a1
            |
            v
DocumentService Spring AOP proxy
  @PreAuthorize:
  tenantAccess.canRead(authentication, "tenant-a")
       |
       +-- No READ membership -> deny (403)
       +-- Has READ membership -> execute method body
            |
            v
Repository
  SELECT ... WHERE tenant_id='tenant-a'
               AND document_id='doc-a1'
       |
       +-- No document in tenant-a -> 404
       +-- Found -> check other ACLs if applicable -> return data
~~~

**Two critical, independent layers:** a tenant membership check from a server source, combined with a tenant predicate in every data-access query. With only the first layer, an ID leaked from another tenant could still be read via `findById`. With only the second layer, a user could swap `tenantId` to another tenant and retrieve that tenant's data without membership.

### 3.1. "Per-Request Verification" Does Not Require a DB Query Every Time

The policy must be **enforced on every protected access**, while membership data may come from:

- A DB/authorization service lookup at access time.
- A membership cache with controlled TTL and invalidation.
- A token claim with tenant-scoped permissions signed/verified by a trusted issuer with an appropriate lifetime.
- A central policy decision service with suitable SLA/availability.

You must define **revocation latency**: if a user's access is revoked at 14:00, what is the maximum window before subsequent requests are rejected? A 10-minute cache or a 30-minute offline JWT creates a window where old permissions remain valid. Never just say "we check tenant" while ignoring permission freshness.

## 4. Tenant Resolution Patterns and Trust Boundaries

| Source | Example | Value | What Must Be Controlled |
| --- | --- | --- | --- |
| URL path | `/tenants/tenant-a/...` | Clear and easy to test | User can alter the path; verify membership |
| Subdomain | `tenant-a.example.org` | Useful for SaaS/white-label | Trusted Host/proxy mapping, tenant lookup |
| HTTP header | `X-Tenant-Id: tenant-a` | Convenient for internal APIs | Client-controlled header unless verified by a gateway |
| JWT access token claim | `tenant_id=tenant-a` | Can scope tokens to a tenant | Verify signature, iss, aud, exp, token type; stale claims |
| Session selection | User selects an organization in the UI | Good UX | Server checks membership when switching tenants and on use |
| API key record | Key bound to tenant-a | Server-to-server integration | Verified key bound to tenant server-side |
| Query/body | `?tenant=tenant-a` | Convenient for some operations | Never treat as proof of permission |

A product needs **clear precedence/conflict rules**. If the path specifies tenant-a, the token claim specifies tenant-b, and a header specifies tenant-c, never pick whichever grants the client access. Reject conflicts or enforce explicit token scope policies.

### 4.1. Canonical Tenant ID

In real systems, URLs can use a tenant slug like `acme` for usability, but the backend should map it to a stable DB ID rather than relying on mutable display names or email domains. Never allow reused slugs to grant old permissions to a new organization.

Validate slug syntax/length/canonicalization, verify the tenant exists and is active, verify actual membership, and use the internal tenant_id. If accepting UUIDs, never treat an unguessable UUID as a security mechanism.

### 4.2. Tenant Claims and JWTs

Illustrative JWT (unsigned payload, not a real credential):

~~~json
{
  "iss": "https://issuer.example",
  "sub": "alice-stable-id",
  "aud": ["document-api"],
  "exp": 1893456000,
  "tenant_id": "tenant-a",
  "scope": "documents.read"
}
~~~

The Resource Server must verify signature, issuer, audience, expiration, and token purpose **before trusting claims**. Moreover:

- The `tenant_id` claim may represent a **token scope restriction**, not all current memberships.
- If a token is single-tenant for `tenant-a`, requests for tenant-b should generally be rejected even if the user holds tenant-b membership via another session.
- The `scope` claim must clearly specify whether it is platform-wide or scoped to the token's tenant.
- When membership is revoked while a JWT is still valid, apply TTL/denylist/introspection/online policy as required.

Never simply decode the payload or accept `X-User-Id` as identity. With multiple issuers, subjects must be paired with issuer/realm to avoid collisions.

## 5. Security Flaws to Prevent

### 5.1. IDOR/BOLA: Changing an ID Exposes Someone Else's Document

Misconfiguration:

~~~java
@GetMapping("/api/tenants/{tenantId}/documents/{documentId}")
public Document read(
        @PathVariable String tenantId,
        @PathVariable String documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Checking only Authentication in the filter chain and then running a global query is **Broken Object Level Authorization (BOLA)**, commonly seen as **IDOR**. Having `tenantId` in the method signature does nothing if it is not used in authorization and queries.

### 5.2. Tenant Spoofing via Headers

~~~http
GET /api/documents/doc-b1
X-Tenant-Id: tenant-b
Authorization: Bearer token-of-alice
~~~

If the server uses this header to switch schemas or databases without verifying membership, Alice can pick any tenant at will. A header may indicate the **requested tenant**, but authorization decisions must come from trusted identity/membership.

### 5.3. Confused Deputy

A worker/service has a service account with platform-wide read privileges. If a user without tenant-b access submits an export request for tenant-b and the worker uses its own technical privileges to fetch the data, the worker has become a confused deputy.

Distinguish between **actor user**, **service identity**, **delegated authorization**, and **permitted tenant**; log audits and never use a broad backend credential as a substitute for checking the caller's permissions.

### 5.4. Global ROLE_ADMIN vs. Tenant Admin

If `ROLE_ADMIN` was granted because a user is admin of tenant-a, using `hasRole('ADMIN')` to allow edits in tenant-b is a scoping flaw. A proper model defines:

- Platform administrator: special multi-tenant privileges, MFA/step-up, and auditing.
- Tenant administrator: specific tenant only.
- Tenant editor/viewer: action permissions restricted within the tenant.
- Resource owner: permissions on a specific object/ACL.

### 5.5. Only Hiding Tenants in the UI

A user who does not see a tenant-b link in the menu can still alter the URL or call the API directly. **Frontend filtering and hidden buttons are not authorization.** The server must deny requests even when they do not originate from the official UI.

## 6. Spring Security Servlet: Which Layer Should Hold Checks?

### 6.1. HTTP Rules Verify General Identity

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/tenants/**").authenticated()
    .anyRequest().denyAll())
~~~

This configuration requires callers to be authenticated to enter this endpoint group. It **does not grant per-tenant authorization**. With this alone, any logged-in user can pass the HTTP layer for any tenantId value.

### 6.2. Method Security: Checking Tenant and Action

Spring Security 6 can use:

~~~java
@EnableMethodSecurity
~~~

to enable pre/post method annotations, including `@PreAuthorize`. Place it on methods of a **Spring-managed service bean**:

~~~java
@PreAuthorize("@tenantAccess.canRead(authentication, #p0)")
public Document read(String tenantId, String documentId) {
    return repository.findByTenantIdAndId(tenantId, documentId)
        .orElseThrow(/* 404 */);
}
~~~

This snippet is illustrative only. `#p0` is the first parameter (tenantId); `tenantAccess` is a Spring policy bean evaluating Authentication and membership from server sources. When called **through the method-security proxy**, the policy runs before the method body.

**Self-invocation warning:** another method in the same class calling `this.read(...)` directly can **bypass the AOP proxy**. Use controller → injected service bean, separate services, or an access policy at a clear boundary; always keep the tenant constraint in the query as defense in depth. Private/final methods or manually instantiated `new` objects are not reliable interception boundaries in proxy-based mode.

### 6.3. Policy Bean Separate from Long SpEL Expressions

An illustrative interface:

~~~java
@Component("tenantAccess")
class TenantAccess {
    boolean canRead(Authentication principal, String tenantId) {
        // Check active membership, tenant status,
        // READ action, and required conditions.
    }
}
~~~

This is an **architectural fragment**, not a complete implementation. The bean can call a trusted membership/permission store, verify the tenant is active, check tenant-scoped roles, token tenant binding, data residency, account status, and revocation policies.

When checking resource-specific ACLs, you can extend it:

~~~java
@PreAuthorize(
    "@documentPolicy.canRead(authentication, #p0, #p1)")
public Document read(String tenantId, String documentId) { ... }
~~~

The policy must use tenant-scoped data sources; never read documents globally and risk leaking information through logs/errors. Depending on transactions/TOCTOU, business logic must also enforce invariants before mutations.

### 6.4. HTTP and Method Authorization Do Not Replace Each Other

The HTTP layer blocks anonymous access, selects authentication mechanisms, and enforces basic route policies. The method layer handles tenant/action/owner checks based on parameters. The repository/data layer ensures **no other tenant's resources are fetched**.

A request may pass HTTP `authenticated()` yet be rejected by `@PreAuthorize` at the method layer. A request passing the method membership check may still return 404 because the document does not belong to that tenant. All three outcomes are correct.

## 7. Runnable Java 17 Example: Tenant-Aware Documents API

This lab intentionally gives all users the **same ROLE_USER**, because the goal is to demonstrate differing per-tenant permissions from **server-side membership**, not global roles. Components:

- Spring Boot 3.3.5 MVC Servlet + Spring Security + HTTP Basic.
- `@EnableMethodSecurity` and `@PreAuthorize`.
- `TenantAccess` policy bean with Alice/Bob/Auditor memberships.
- `DocumentService` using a composite key (tenantId, documentId).
- GET to read documents, POST to create documents; CSRF remains enabled.
- MockMvc positive/negative tests for isolation.

### 7.1. File Structure

~~~text
tenant-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/tenant/
    │   ├── TenantDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── TenantAccess.java
    │   ├── Document.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/example/tenant/
        └── TenantAuthorizationTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'tenant-security-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Application

File `src/main/java/example/tenant/TenantDemoApplication.java`:

~~~java
package example.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantDemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration

File `src/main/java/example/tenant/SecurityConfiguration.java`:

~~~java
package example.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/tenants/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // Keep CSRF enabled for this example.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();
        UserDetails auditor = User.withUsername("auditor")
            .password(encoder.encode("auditor-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, auditor);
    }
}
~~~

HTTP `authenticated()` cannot distinguish which tenant permissions Alice/Bob/Auditor have; hence a policy bean is required. HTTP Basic is only for local testing, not the recommended protocol for every production app. HTTPS is mandatory for real credentials.

### 7.4. TenantAccess: Server-Side Membership Lookup

File `src/main/java/example/tenant/TenantAccess.java`:

~~~java
package example.tenant;

import java.util.Map;
import java.util.Set;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public class TenantAccess {

    // Demo: server-defined permissions table.
    // Production uses stable user ID + real membership store.
    private static final Map<String, Map<String, Set<String>>> RIGHTS =
        Map.of(
            "alice", Map.of(
                "tenant-a", Set.of("read", "write")),
            "bob", Map.of(
                "tenant-b", Set.of("read", "write")),
            "auditor", Map.of(
                "tenant-a", Set.of("read"),
                "tenant-b", Set.of("read"))
        );

    public boolean canRead(Authentication authentication,
                           String tenantId) {
        return has(authentication, tenantId, "read");
    }

    public boolean canWrite(Authentication authentication,
                            String tenantId) {
        return has(authentication, tenantId, "write");
    }

    private boolean has(Authentication authentication,
                        String tenantId,
                        String action) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || tenantId == null) {
            return false;
        }

        return RIGHTS
            .getOrDefault(authentication.getName(), Map.of())
            .getOrDefault(tenantId, Set.of())
            .contains(action);
    }
}
~~~

Key points to emphasize:

- `authentication.getName()` comes from the verified authentication mechanism.
- The requested `tenantId` comes from the request, while the map decides whether the principal has permission.
- `canRead` and `canWrite` are separate; auditor has READ in both tenants but no WRITE.
- Missing membership/permission → default **false/deny**.
- Never read `X-Tenant-Id`, `X-Role`, or `X-User` from the client to grant access.

In production, never use a mutable username as the primary identity; use a stable subject combined with issuer if multiple IdPs exist. Membership should cover tenant status, suspension, expiry, auditing, policy-driven cache invalidation, and explicit role hierarchy logic.

### 7.5. Document Model

File `src/main/java/example/tenant/Document.java`:

~~~java
package example.tenant;

public record Document(
    String id,
    String tenantId,
    String title
) {}
~~~

The record carries the object's **server-stored** tenantId, not a client-declared field on read. When creating, the service attaches the policy-checked tenantId.

### 7.6. DocumentService: Authorization and Scoped Queries

File `src/main/java/example/tenant/DocumentService.java`:

~~~java
package example.tenant;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private record DocumentKey(String tenantId, String documentId) {}

    private final Map<DocumentKey, Document> documents =
        new ConcurrentHashMap<>();

    private final AtomicLong nextId = new AtomicLong();

    public DocumentService() {
        put(new Document(
            "doc-a1", "tenant-a", "Alpha document"));
        put(new Document(
            "doc-b1", "tenant-b", "Beta document"));
    }

    @PreAuthorize("@tenantAccess.canRead(authentication, #p0)")
    public Document read(String tenantId, String documentId) {
        Document document = documents.get(
            new DocumentKey(tenantId, documentId));

        if (document == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return document;
    }

    @PreAuthorize("@tenantAccess.canWrite(authentication, #p0)")
    public Document create(String tenantId, String title) {
        if (title == null || title.isBlank()
                || title.length() > 120) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Document document = new Document(
            "new-" + nextId.incrementAndGet(),
            tenantId,
            title);

        put(document);
        return document;
    }

    private void put(Document document) {
        documents.put(new DocumentKey(
            document.tenantId(), document.id()), document);
    }
}
~~~

In a call intercepted by the Spring proxy, `@PreAuthorize` checks READ/WRITE membership **before running the method body**. The composite `DocumentKey(tenantId, documentId)` also guarantees that a member of two tenants cannot accidentally read a resource from the other tenant just because resource IDs match or are guessable.

Think about it: auditor has READ in tenant-a and tenant-b. `/tenant-b/documents/doc-a1` passes the tenant-b membership check, yet **still does not return** tenant-a's document because the composite key lookup finds nothing. If replaced with `Map<String, Document>` indexed only by ID or a global `findById`, tenant isolation could be broken.

**Do not use this in-memory code in production.** With a database, you need tenant predicates, foreign keys/composite keys, transaction isolation, and real object ACLs. Methods with side effects must also preserve business invariants if membership changes concurrently.

### 7.7. DocumentController

File `src/main/java/example/tenant/DocumentController.java`:

~~~java
package example.tenant;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {

    public record CreateDocument(String title) {}

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{documentId}")
    public Document read(@PathVariable String tenantId,
                         @PathVariable String documentId) {
        return documents.read(tenantId, documentId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Document create(@PathVariable String tenantId,
                           @RequestBody CreateDocument body) {
        return documents.create(tenantId, body.title());
    }
}
~~~

`CreateDocument` accepts only title, preventing the client from choosing another `tenantId` in the body. If an API requires tenantId in the body, the server must verify it matches the authorized tenant rather than switching the target tenant from the body. The controller injects `DocumentService` from the container so calls pass through the method-security proxy; never `new DocumentService()`.

### 7.8. MockMvc Tests Protecting the Tenant Boundary

File `src/test/java/example/tenant/TenantAuthorizationTests.java`:

~~~java
package example.tenant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantAuthorizationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadTenant() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadTenantA() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"))
            .andExpect(jsonPath("$.id").value("doc-a1"));
    }

    @Test
    void aliceCannotReadTenantB() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadTenantB() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-b"));
    }

    @Test
    void bobCannotReadTenantA() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadBothTenants() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isOk());

        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void dualMembershipStillCannotReadOtherTenantResource()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-a1")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isNotFound());
    }

    @Test
    void forgedTenantHeaderDoesNotGrantAccess()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .header("X-Tenant-Id", "tenant-b")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void headerDoesNotOverrideTenantInPath()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .header("X-Tenant-Id", "tenant-b")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }

    @Test
    void aliceCanCreateTenantADocumentWithCsrf()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New alpha document\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"))
            .andExpect(jsonPath("$.title")
                .value("New alpha document"));
    }

    @Test
    void auditorCannotWriteWithReadPermission()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("auditor", "auditor-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Forbidden write\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotCreateForTenantB() throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-b/documents")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Cross tenant\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validWritePermissionDoesNotBypassCsrf()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Missing csrf\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingDocumentInsideAuthorizedTenantIs404()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/missing")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isNotFound());
    }

    @Test
    void unknownTenantIsNotAutomaticallyAllowed()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/unknown/documents/doc-a1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTitleIs400WhenWriteAuthorized()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unrelatedRouteIsNotOpenForAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

### 7.9. Expected Results and Meaning

| Request / Principal | Decision | Demo Status |
| --- | --- | --- |
| Alice GET tenant-a/doc-a1 | Has READ on tenant-a, resource belongs to tenant | 200 |
| Alice GET tenant-b/doc-b1 | No membership on tenant-b | 403 |
| Bob GET tenant-b/doc-b1 | Has READ on tenant-b | 200 |
| Auditor GET tenant-a/doc-a1 | Has READ on tenant-a | 200 |
| Auditor GET tenant-b/doc-b1 | Has READ on tenant-b | 200 |
| Auditor GET tenant-b/doc-a1 | Valid READ on tenant-b, but document belongs to tenant-a | 404 |
| Alice GET tenant-b + forged header | Header does not grant membership | 403 |
| Alice POST tenant-a + CSRF | Has WRITE on tenant-a | 201 |
| Auditor POST tenant-a + CSRF | Has READ only | 403 |
| Alice POST tenant-a without CSRF | CsrfFilter blocks before method | 403 |
| Anonymous GET tenant-a | HTTP layer requires authenticated | 401 |

The table reflects **expectations based on the lab configuration**, not runtime results executed while authoring. A production API may choose to return 404 instead of 403 for wrong-tenant requests to curb tenant/resource enumeration; keep the policy uniform, avoid leaking sensitive info in error bodies, and log internal audits.

### 7.10. Run Commands

On a machine with Java 17 and a compatible Gradle version:

~~~bash
gradle test
gradle bootRun
~~~

If the project has Gradle Wrapper, prefer `./gradlew test` and `./gradlew bootRun`; on Windows use `gradlew.bat test` / `gradlew.bat bootRun`. Do not run Spring Boot code with bare `javac`/`java` without supplying dependencies.

Localhost call examples:

~~~bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/tenants/tenant-a/documents/doc-a1

curl -i -u alice:alice-pass \
  http://localhost:8080/api/tenants/tenant-b/documents/doc-b1

curl -i -u auditor:auditor-pass \
  http://localhost:8080/api/tenants/tenant-b/documents/doc-b1
~~~

Username/password values here are **for local demo use only**. In real systems, never use plain HTTP without TLS and avoid placing passwords into shell history or process lists; use TLS, a secret manager/IdP, and proper session or token lifecycles. To test POST while keeping CSRF protection, use MockMvc as in the tests or a client that fetches and sends a valid CSRF token.

## 8. Data Isolation: SQL, Composite Keys, and JOINs

When replacing the in-memory map with a database, the tenant predicate must appear on **every data-read and data-modification path**, not just a single read method.

### 8.1. Shared-Database Schema

Illustrative schema:

~~~sql
CREATE TABLE tenants (
    tenant_id VARCHAR(64) PRIMARY KEY,
    active BOOLEAN NOT NULL
);

CREATE TABLE memberships (
    user_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    permission VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (user_id, tenant_id, permission),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE documents (
    tenant_id VARCHAR(64) NOT NULL,
    document_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, document_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
~~~

The permission model can add role hierarchies, owners, membership expiry, invitation status, groups, soft deletion, and auditing. Key constraints should reflect per-tenant uniqueness rather than assuming global uniqueness.

### 8.2. Correct Query

~~~sql
SELECT d.tenant_id, d.document_id, d.title
FROM documents d
WHERE d.tenant_id = :authorized_tenant_id
  AND d.document_id = :document_id;
~~~

`authorized_tenant_id` emphasizes that membership/action has already been checked. The query itself does not authorize anything if the application passes a client-supplied tenantId unchecked.

Wrong:

~~~sql
SELECT d.*
FROM documents d
WHERE d.document_id = :document_id;
~~~

Even if document IDs are globally unique UUIDs, knowing an ID does not prove permission; omitting the tenant/permission check is IDOR/BOLA.

### 8.3. JOINs Must Also Be Tenant-Scoped

If both comments and documents contain `tenant_id`, never JOIN only on `document_id`:

~~~sql
-- Insufficient when document_id can collide across tenants:
SELECT c.*
FROM comments c
JOIN documents d ON d.document_id = c.document_id
WHERE d.tenant_id = :tenant_id;
~~~

Better:

~~~sql
SELECT c.*
FROM comments c
JOIN documents d
  ON d.tenant_id = c.tenant_id
 AND d.document_id = c.document_id
WHERE d.tenant_id = :authorized_tenant_id
  AND d.document_id = :document_id;
~~~

Child table foreign keys should also preserve the tenant identifier. Cross-tenant aggregations, search, and exports require separate permissions, never simply dropping WHERE tenant_id for convenience.

## 9. Row-Level Security and ORM Multi-Tenancy

### 9.1. RLS Is Defense in Depth, Not a Replacement for Membership

PostgreSQL Row-Level Security (RLS) can add row-level tenant policies. However, the DB must be configured properly:

- The app DB role must not arbitrarily bypass RLS; table owners, superusers, and privileged roles have special behavior.
- The tenant setting used by the policy must be set by the **trusted application** after authorization, not from arbitrary headers.
- With connection pools, ensure tenant state never leaks into subsequent requests.
- SELECT/INSERT/UPDATE/DELETE and WITH CHECK all need appropriate policies.
- Background migrations, support tooling, and exports need separately managed permissions.
- RLS does not automatically enforce all business ACLs, action roles, or token issuers.

Illustrative pseudo-SQL fragment, **not a complete production migration**:

~~~sql
-- App sets this setting ONLY AFTER authorizing the tenant.
-- In PostgreSQL, true applies a transaction-local setting.
SELECT set_config(
    'app.tenant_id',
    :authorized_tenant_id,
    true
);

CREATE POLICY documents_tenant_isolation
ON documents
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

Enable RLS on the table, create roles/policies, open transactions properly, and verify connection/session settings. Never use raw user input to set the DB tenant context and assume RLS makes everything safe.

### 9.2. Schema-per-Tenant and Database-per-Tenant

These two models improve storage isolation, but do not turn a requestedTenant into an authorizedTenant. If the client changes the tenant and the system picks a connection/schema from unchecked input, tenant spoofing still occurs. The datastore routing layer must be guarded as an authorization-sensitive operation.

### 9.3. Hibernate Tenant Resolver

An ORM resolver helps supply a tenant identifier to persistence, but it **does not authorize** the caller. Before attaching an identifier to the persistence context, the application must verify principal/membership, and transactions/second-level caches must never mix tenants.

When multiple requests share a thread pool/DB connection pool, ensure tenant context is reset and transaction boundaries stay consistent.

## 10. TenantContext, ThreadLocal, and Asynchronous Work

Many systems build a `TenantContextHolder` over `ThreadLocal`. This can be convenient, but it is not a source of authority.

~~~java
// Illustrative snippet for context lifecycle; not an authz policy.
try {
    TenantContext.set(authorizedTenantId);
    chain.doFilter(request, response);
} finally {
    TenantContext.clear();
}
~~~

Distinguish clearly:

- `requestedTenantId`: suggested by the request.
- `authorizedTenantId`: verified through the tenant membership/action policy.
- `SecurityContextHolder`: holds Authentication; does not prove tenant access on its own.
- `TenantContextHolder`: holds the tenant scope for the request; safe to use only when populated from an authorized state.

**Never set ThreadLocal from an unverified header and let a repository select a tenant schema.** Never use static global variables shared across requests. With async executors, scheduled jobs, and message consumers, context can be lost or erroneously reused; pass tenant/actor/permission context explicitly and validate at trust boundaries.

In critical code, passing `tenantId` explicitly through service/repository methods is easier to audit:

~~~java
documentService.read(authorizedTenantId, documentId);
repository.findByTenantIdAndDocumentId(
    authorizedTenantId, documentId);
~~~

If ThreadLocal is unavoidable, clear it in `finally`, test concurrent requests, error paths, and transaction leaks, and never switch tenants mid-flight within a single operation.

## 11. Caches, Search, Object Storage, and Background Jobs

### 11.1. Cache Keys Must Be Tenant-Aware

Wrong:

~~~text
key = document:doc-42
value = document belonging to tenant-a
~~~

If tenant-b also has doc-42, a cache lookup can wrongly return tenant-a's document. Better:

~~~text
key = document:tenant-a:doc-42
key = document:tenant-b:doc-42
~~~

Use canonical encoding to prevent collisions, proper per-tenant invalidation, and **user/resource ACLs** in cache keys when data is private within the same tenant. Never cache user A's response and serve it to user B just because both belong to the same tenant.

### 11.2. Search Indexes and Aggregations

Full-text search, suggestions, facets, and counts can reveal other organizations' data even when the detail endpoint is protected. Tenant filters must be applied in backend search queries/index routing using the authorized tenant; never fetch all results and hide them only on the frontend.

### 11.3. Object Storage / CDN

A key like `tenant-a/files/doc-42.pdf` is not a security boundary. Issue signed download URLs only after checking identity, tenant membership, and resource ACLs. Signed URLs require appropriate expirations and scopes; CDN cache keys/policies must prevent cross-tenant leakage.

### 11.4. Events, Queues, and Exports

An event may carry:

~~~json
{
  "eventType": "DocumentCreated",
  "tenantId": "tenant-a",
  "documentId": "doc-a1",
  "actorId": "alice"
}
~~~

Fields inside a message do not automatically prove the publisher was allowed to act in tenant-a. Producers must authorize; consumers must trust the producer/source, validate schema/tenant, and never use a privileged service account as a confused deputy for unverified requests.

Exports/batch reports must scope all queries, joins, file storage, notifications, downloadable links, and audits. A background job lacks an HTTP session/ThreadLocal; pass context from a trusted source explicitly.

## 12. Switching Tenants and Revoking Membership

### 12.1. User Switches Organizations in the UI

When a user selects tenant-b:

1. The browser sends only the requested tenant.
2. The backend verifies the user has active membership in tenant-b.
3. Subsequent requests must still check corresponding action/resource scopes.
4. Caches, WebSocket subscriptions, breadcrumbs, and export states must switch tenants consistently.
5. If the session stores the selected tenant, update the session safely and consider CSRF for state-changing switches.

Hiding a tenant from a dropdown does not stop a user from calling another URL manually.

### 12.2. Revoking Access and Staleness Windows

Suppose an admin removes Alice from tenant-a at 14:00. A membership cache with a 5-minute TTL or a JWT with a 30-minute old tenant scope can allow Alice to remain accepted for a window. Define **maximum acceptable staleness** by business risk; for sensitive operations consider online checks, invalidation events, short TTLs, revocation state, and re-authentication/step-up.

Never treat a `tenantId` claim in an old token as permanent proof of membership.

### 12.3. Platform Admin and Impersonation

Platform admins may need multi-organization support, but this must be an explicit permission, preferring MFA/step-up, reason capture, auditing, expiration, and data minimization. Never use a generic `ROLE_ADMIN` or `X-Admin: true` to disable all tenant checks.

When impersonating a user, log the **real actor**, **effective identity**, **target tenant**, **action**, **resource**, and **reason** in the audit trail. Distinguish service identity from user on-behalf-of flows.

## 13. HTTP Status Codes, Anti-Enumeration, and Common Mistakes

| Scenario | Typical Status | Important Note |
| --- | --- | --- |
| Unauthenticated on protected endpoint | 401 in HTTP Basic/Bearer flow | Do not return tenant metadata |
| Authenticated but not a tenant member | 403 or 404 per anti-enumeration policy | Do not leak documents/owners |
| Member lacking WRITE | 403 | READ does not imply WRITE |
| Member of two tenants, ID belongs to other tenant | 404 when scoped lookup finds nothing | No global findById |
| Tenant does not exist | 404/403 per contract | Avoid tenant enumeration |
| POST missing CSRF | May be 403 before authz | Do not misdiagnose as missing role |
| Invalid JWT signature/issuer/audience | 401 in bearer flow | Never trust claims before verification |

The lab chooses 403 for tenant permission denial and 404 for a non-existent document **within an authorized tenant**. Production may choose 404 uniformly to reduce information disclosure; be careful with error bodies, timing, auditing, and caching.

### 13.1. Diagnostic Order

1. Were credentials verified? What are the trusted principal/issuer/authorities?
2. Which path/host/header/token/session provided the requested tenant? Are there conflicting sources?
3. Is the tenant ID canonical and is the tenant active?
4. Does the principal have active membership and the right READ/WRITE/EXPORT permission?
5. Is Spring method security enabled; does the service call pass through a proxy?
6. Does the repository query include a tenant predicate/composite key?
7. Are object ACLs/ownership and business policies checked?
8. Did a CSRF filter or HTTP security block the request before reaching the service?
9. Do caches/search/exports/queues enforce equivalent tenant scoping?
10. Is the membership cache stale; does the token have an appropriate scope/lifetime?
11. Is thread-local or DB connection tenant context leaking across requests?
12. Do errors/logs inadvertently expose user/resource data or secrets?

### 13.2. Typical Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only `authenticated()` | Any logged-in user can access arbitrary tenants | Tenant action policy |
| Trusting `X-Tenant-Id` | Tenant spoofing | Header is only requested tenant |
| Using global admin role | One tenant's privilege escalates platform-wide | Tenant-scoped roles |
| Global `findById` query | IDOR/BOLA | Query by tenant + ID |
| JOIN missing tenant | Data mixed through child tables | Composite tenant join |
| Trusting JWT payload after decoding | Accepts forged/wrong-audience tokens | Verify signature, iss, aud, expiry |
| Proxy self-invocation | Method annotation does not run | Cross-bean proxy boundary |
| TenantContext not cleared | Thread reuse leaks cross-tenant | finally + tests |
| Cache key has only document ID | Cache serves wrong organization | Tenant-aware cache keys |
| Frontend search filtering | Results/facets leak data | Server-side tenant filter |
| Object key prefix treated as auth | URLs guessed/exploited | Check ACL before signed URL |
| Unbounded membership cache | Revocation has no effect | TTL/invalidation |
| Errors returning tenant info | Enumeration and metadata leaks | Error policy/redaction |
| Testing only happy path | Cross-tenant issues go undetected | Negative tests |
| Demo Basic auth over HTTP | Credential exposure | HTTPS and proper IdP |

## 14. Production Checklist

- [ ] Principal/Authentication comes from a verified source, never arbitrary headers.
- [ ] Requested tenant is separated from authorized tenant; conflict policy is clear.
- [ ] Tenant ID is canonical and stable, and tenant state is verified.
- [ ] Active membership and per-tenant/action permissions are decided server-side.
- [ ] Tenant roles are separated from platform roles; special admin access is audited.
- [ ] Every protected request checks tenant and action policies, denying by default.
- [ ] Resource ownership/ACLs are verified when required by business logic.
- [ ] All queries, updates, deletes, JOINs, and exports include tenant predicates or safe routing.
- [ ] Composite keys/foreign keys/uniques reflect tenant isolation.
- [ ] RLS/ORM tenancy acts as defense in depth, not a replacement for authz.
- [ ] TenantContext comes only from authorized state, clears cleanly, and never leaks via thread/connection pools.
- [ ] Caches/search/CDNs/object storage/signed links isolate tenants and user ACLs.
- [ ] Background jobs, events, and batch reporting carry trusted identity/tenant context.
- [ ] Revocation latency, cache invalidation, and token expiry meet business requirements.
- [ ] Session tenant switching cannot exceed user memberships.
- [ ] Error responses reveal nothing about unauthorized tenants or resources.
- [ ] Tests cover 401, 403, 404, 200, 201, wrong tenant, forged header, wrong resource ID, and read-only users.
- [ ] Dedicated CSRF tests cover unsafe HTTP methods.
- [ ] Cross-tenant regression tests run whenever adding endpoints or changing ORM/cache/index layers.
- [ ] Auditing and an incident-response plan exist for tenant breaches.
- [ ] Demo passwords and in-memory memberships never reach production.

## 15. Practice Exercises

1. A JWT has a valid `sub=alice`. Why is that not enough to let Alice read tenant-b?
2. Distinguish requested tenant from authorized tenant using `/tenants/tenant-b/...`.
3. Alice is an editor in tenant-a and a viewer in tenant-b. Write the READ/WRITE action mapping for both tenants.
4. If a service checks tenant-a membership yet still calls `findById("doc-b1")`, what vulnerability remains?
5. Why is a document UUID not a permission?
6. In the lab, Alice sends `X-Tenant-Id: tenant-b`. Why does the header not change the authorization decision?
7. Auditor belongs to both tenants, so what must `GET tenant-b/doc-a1` return? Why?
8. All three demo users have only `ROLE_USER`; which policy distinguishes per-tenant permissions?
9. Why must `@PreAuthorize` be invoked through a Spring-managed proxy?
10. An internal service method calls an annotated method on `this`—what is the self-invocation risk?
11. A valid POST missing CSRF and a POST with CSRF missing WRITE can both return 403. How do you debug which occurred?
12. Design a SQL query and index to look up a document by `(tenant_id, document_id)`.
13. Write a comments/documents JOIN with full tenant constraints, plus a test preventing comment mixing.
14. Why is filtering search results by tenant on the frontend insufficient?
15. Design cache keys for documents with identical IDs across two tenants and separate user ACLs.
16. When switching to schema-per-tenant, why must you still verify membership before selecting the schema?
17. If an RLS setting comes directly from an unauthorized header, what flaw occurs?
18. Membership is revoked while a JWT remains valid for 30 minutes: which policy governs the acceptance window?
19. When a user switches tenants in the UI, how should caches and WebSocket subscriptions be handled?
20. Design an audit record for a platform admin impersonating a user in tenant-b.
21. A queue worker uses a multi-tenant service account: how do you prevent a confused deputy?
22. When do you return 403 vs. 404 for an unauthorized tenant/resource?
23. Add a MockMvc test verifying Bob has WRITE in tenant-b but no READ in tenant-a.
24. Which isolation layers must a multi-table CSV export verify?
25. Build a negative test matrix covering GET/POST/DELETE, anonymous, Alice, Bob, Auditor, and a non-existent tenant.

## 16. Conclusion

**Multi-tenancy is authorization over a triad: principal, tenant, and resource/action.** An authenticated user does not necessarily belong to the requested tenant; a tenant member does not necessarily have WRITE permission; and a user with access in two tenants still cannot use one tenant's URL to read another tenant's resource.

In Spring Security Servlet, a clear implementation flow is: **verify credentials in the filter chain → extract the target tenant from the request → verify membership/permissions from a trusted source via a service policy → query tenant-scoped resources → check additional owner/ACL rules → return data and audit within scope**. Reinforce this with tenant-aware caches, database queries, jobs, and cross-tenant tests so one organization's data never becomes another organization's data.
