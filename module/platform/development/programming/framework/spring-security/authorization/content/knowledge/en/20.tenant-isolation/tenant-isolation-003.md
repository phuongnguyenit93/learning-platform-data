# Verifying Tenant in URL, Header, or Input Data — Spring Security Authorization

## 1. The problem: client-requested tenant is not an authorized tenant

In a multi-organization SaaS system, a request can carry a tenant in multiple places:

```http
PUT /api/tenants/t1/documents/101
Authorization: Bearer <access-token>
X-Tenant-Id: t1
Content-Type: application/json

{"tenantId":"t1","title":"New report"}
```

The example above merely illustrates a request, not a real access token. All of `t1` in the **URL**, `X-Tenant-Id` in the **header**, and `tenantId` in the **JSON body** are values the client can modify. They express *the requested tenant*, but **do not prove** the caller has rights in that tenant.

Suppose Alice is a member of tenant `t1` and does not belong to `t2`. If Alice changes every value to `t2`, the backend **must not** accept it automatically. Conversely, if Alice requests `t1` while the document ID belongs to `t2`, the backend must also deny it.

A proper decision must cross-check **three distinct sources of truth**:

1. **Authenticated identity:** `Authentication` provided by Spring Security after verifying credentials/session/JWT with a trusted provider.
2. **Per-tenant membership and roles:** the tenants this identity actually has rights to, managed by a database/IAM or entitlements issued by a trusted issuer.
3. **Canonical tenant of the resource:** `document.tenant_id` read from the server-side data store, not the tenant field in the request.

```text
Request selectors                    Trusted evidence
-----------------                    ----------------
Path /tenants/t1      ──candidate──► Authentication: alice
Header X-Tenant-Id:t1 ──candidate──► Membership(alice,t1) = true
Body tenantId:t1      ──candidate──► Document#101.tenant_id = t1
                                       │
                                       ▼
                           Permission(owner/share/admin, action)
                                       │
                             allow only if ALL pass
```

**Rule:** A tenant from the request is a *scope selection proposal*, not a credential. Every check must **fail-closed** when data is invalid, permissions are missing, or tenant sources conflict.

## 2. Threat model and trust boundary

| Source | Who controls it? | Legitimate role | Must never be used to |
|---|---|---|---|
| `/tenants/{tenantId}` | Client | Select desired tenant | Grant roles, bypass membership |
| `X-Tenant-Id` | Client, except special trusted gateway | Select scope / verify against path | Construct `Authentication` itself |
| JSON `tenantId` | Client | Specify tenant on CREATE, or confirm scope on UPDATE | Mass-assign tenant onto entity |
| Query `?tenant=t2` | Client | Filter data within proven scope | Query across tenants |
| `Host`/subdomain | Can be influenced by client/proxy | Tenant routing after hostname verification | Treat hostname itself as membership proof |
| `X-User`/`X-Role` | Client if no trusted gateway | Do not use for authentication | Spoof principal/authority |
| Verified JWT | Trusted identity provider | Confirm subject, issuer, claims/entitlements | Bypass resource tenant or revocation policy |
| Database membership | Server/IAM | Current tenant permissions | Trust client-modified data |
| `document.tenant_id` | Server data store | Owning tenant of the record | Be altered via arbitrary rename endpoints |

Four critical attack patterns:

- **Horizontal cross-tenant BOLA:** Alice from t1 alters the route to t2 or guesses a t2 document's ID.
- **Header spoofing:** client adds `X-Tenant-Id: t2`, `X-User: manager`, or `X-Role: ROLE_ADMIN` to impersonate.
- **Mass assignment:** JSON update contains `{"tenantId":"t2","owner":"attacker"}`; if a mapper writes the DTO straight onto the entity, it changes scope/owner unlawfully.
- **Confused-deputy routing:** gateway/service A checks path t1 while service B picks a database using an unverified header t2. Two services accidentally operate under **two different tenant contexts**.

Following OWASP's Broken Object Level Authorization guidance, any endpoint receiving an object ID and accessing an object must verify that the user is authorized to perform the action on **that specific object**, not merely verify they are logged in.

### 2.1. Never confuse authentication with authorization

`Authentication.isAuthenticated() == true` only proves the call passed an authentication mechanism; it does not decide which tenant is permitted. Even a validly signed JWT may have had its membership revoked since issuance.

A minimal model:

```text
Authenticated principal
AND request tenant is well-formed
AND serverMembership(principal, requestTenant)
AND record.tenantId == requestTenant
AND actionAllowed(principal, record)
```

Here, the final condition may be ownership, VIEWER/EDITOR sharing, tenant-bound admin, a permission evaluator, or an ACL. **Membership in a tenant does not mean reading every record in that tenant.**

## 3. Defining a contract for URL, header, and body

There is no single mandatory tenant placement for all applications. What matters is choosing a contract and enforcing it consistently.

This article chooses:

- **GET:** `/api/tenants/{tenantId}/documents/{id}`. Path is the requested tenant. Header `X-Tenant-Id` is optional; if sent, it must **match the path exactly**.
- **POST:** `/api/tenants/{tenantId}/documents`. Body `tenantId` is required and must match the path. Header, if present, must also match.
- **PUT:** `/api/tenants/{tenantId}/documents/{id}`. Body `tenantId` must match the path; header, if present, must match; the actual document must belong to that tenant.
- **All methods:** principal must hold server-side membership and action permission on the corresponding data.

| Path | Header | Body | Membership | DB record tenant | Decision |
|---|---|---|---|---|---|
| t1 | omitted | GET | t1 | t1 | Evaluate owner/share/action |
| t1 | t1 | t1 | t1 | t1 | Evaluate owner/share/action |
| t1 | t2 | t1 | t1 | t1 | Deny: header differs from path |
| t1 | t1 | t2 | t1 | t1 | Deny: body differs from path |
| t2 | t2 | t2 | t1 only | t2 | Deny: no membership |
| t1 | t1 | t1 | t1 | t2 | Deny: record belongs to another tenant |
| t1 | t1 | t1 | t1 | t1 | Still must evaluate specific permission |

If sources conflict, **never auto-prefer the header or body**, and never silently pick the last value. The API can return 403 or 404 depending on its existence-hiding policy; the demo uses 403 for authenticated but denied calls.

### 3.1. Tenant IDs must be canonical

Do not compare `t1` with `t10` via `startsWith`; do not treat `t1` and `T1` as identical unless the system explicitly defines that rule. When tenant IDs use UUIDs, slugs, or subdomains, validate format/length and normalization rules in one trusted place.

Duplicate headers or `X-Tenant-Id: t1, t2` must have explicit handling (typically rejecting headers expecting a single value). Never pick an arbitrary element and ignore the rest.

### 3.2. Status 403 vs. 404

When a resource ID exists in another tenant, returning **404** can prevent attackers from probing record existence. **403** fits when you want to explicitly state the user is not permitted. Pick one policy and test it consistently, avoiding leaks through error messages, total counts, query timings, or search APIs. Status codes do not replace authorization.

## 4. Writing policies in Spring Security

### 4.1. Wrong: using tenant input as an authority

```java
// COUNTEREXAMPLE - does not compile standalone.
String tenant = request.getHeader("X-Tenant-Id");
Authentication auth = new UsernamePasswordAuthenticationToken(
    request.getHeader("X-User"), null,
    List.of(new SimpleGrantedAuthority("tenant:" + tenant))
);
SecurityContextHolder.getContext().setAuthentication(auth);
```

Attacker-supplied data is promoted into an authority without proof of membership or identity authentication. That is **privilege escalation**. The backend must never assemble `Authentication` from arbitrary headers.

### 4.2. Architecturally sound: request only selects scope

```text
Spring authentication filter authenticates user
    ↓
Controller extracts tenant candidate from URL/header/body
    ↓
Service policy: Authentication + server membership
    ↓
Query resource by ID AND verified tenant
    ↓
Check owner/share/admin and business state
    ↓
Execute READ/EDIT/CREATE guarded at repository
```

Enable Method Security:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {
    // ...
}
```

Check at the service layer:

```java
@PreAuthorize(
    "@tenantPolicy.canRead(authentication,#tenantId,#id,#headerTenant)"
)
public DocumentView read(
        @P("tenantId") String tenantId,
        @P("id") Long id,
        @P("headerTenant") String headerTenant) {
    // ...
}
```

These are **modeling snippets** requiring a project and supporting classes to run. `@P` binds SpEL parameter names. `@PreAuthorize` intercepts before the target method runs, but callers must invoke through the Spring AOP proxy; self-invoking `this.read(...)` inside the same bean can bypass advice in proxy mode.

An admin role must also be scope-constrained. Never write `hasRole('ADMIN') or @tenantPolicy.canRead(...)` if the admin branch drops the tenant boundary altogether. Prefer binding admin privileges per tenant inside the server-side policy.

## 5. Complete example: Java 17, Spring Boot 3.5.6, Spring Security 6.5.x

The demo stores data in memory to focus on tenant and access verification. It provides REST GET/POST/PUT with tenants in URL, header, and body, `@PreAuthorize`, a server-side membership source, and MockMvc/JUnit integration tests. Production replaces RAM with JDBC/JPA using tenant-qualified queries as shown in section 7.

### 5.1. Structure

```text
tenant-input-verification/
  pom.xml
  src/main/java/com/example/tenant/
    TenantApplication.java
    SecurityConfig.java
    Catalog.java
    TenantPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/tenant/
    TenantVerificationTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>tenant-input-verification</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot manages compatible Spring Security dependencies; avoid forcing a different Security major version. The demo uses HTTP Basic so 401/403 are easy to observe. Tests with `@WithMockUser` build a mock Authentication for **authorization**; they do not verify passwords or JWT signatures.

### 5.3. Main application

**`src/main/java/com/example/tenant/TenantApplication.java`**

```java
package com.example.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantApplication.class, args);
    }
}
```

### 5.4. SecurityConfig

**`src/main/java/com/example/tenant/SecurityConfig.java`**

```java
package com.example.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/tenants/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

The HTTP filter requires authentication on tenant routes without deciding object-level permissions; that logic resides in `TenantPolicy`/`DocumentService`. CSRF remains enabled by default; POST/PUT tests supply `csrf()` so protection is not disabled when running cookie/session-based auth.

### 5.5. Catalog: records, membership, and trusted role binding

**`src/main/java/com/example/tenant/Catalog.java`**

```java
package com.example.tenant;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
public class Catalog {
    public record Document(
            Long id, String tenantId, String owner, String title) {}

    public enum ShareLevel { VIEWER, EDITOR }

    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice", "bob", "manager"),
        "t2", Set.of("carol", "dave")
    );

    private final Set<String> adminBindings = Set.of("t1:manager");

    private final Map<String, ShareLevel> shares = Map.of(
        "101:bob", ShareLevel.VIEWER,
        "102:alice", ShareLevel.EDITOR
    );

    private final ConcurrentMap<Long, Document> docs =
        new ConcurrentHashMap<>();

    private final AtomicLong ids = new AtomicLong(300);

    public Catalog() {
        reset();
    }

    public synchronized void reset() {
        docs.clear();
        ids.set(300);
        docs.put(101L, new Document(
            101L, "t1", "alice", "Alice notes"));
        docs.put(102L, new Document(
            102L, "t1", "bob", "Bob plan"));
        docs.put(103L, new Document(
            103L, "t1", "manager", "Manager private"));
        docs.put(201L, new Document(
            201L, "t2", "carol", "Carol report"));
    }

    public boolean member(String tenant, String username) {
        Set<String> usernames = members.get(tenant);
        return usernames != null && usernames.contains(username);
    }

    public boolean adminBinding(String tenant, String username) {
        return tenant != null && username != null
            && adminBindings.contains(tenant + ":" + username);
    }

    public ShareLevel share(Long id, String username) {
        return id == null || username == null ? null
            : shares.get(id + ":" + username);
    }

    public Document find(Long id) {
        return id == null ? null : docs.get(id);
    }

    public synchronized Document create(
            String tenant, String owner, String title) {
        long id = ids.incrementAndGet();
        Document doc = new Document(id, tenant, owner, title);
        docs.put(id, doc);
        return doc;
    }

    public synchronized Document rename(
            Long id, String tenant, String title) {
        Document previous = find(id);
        if (previous == null
                || !tenant.equals(previous.tenantId())) {
            return null;
        }
        Document updated = new Document(
            id, previous.tenantId(), previous.owner(), title
        );
        docs.put(id, updated);
        return updated;
    }
}
```

Fixture:
- Alice/Bob/manager are members of t1; Carol/Dave belong to t2.
- Manager is admin of t1 **only when also holding** authority `ROLE_TENANT_ADMIN`, and cannot administer t2.
- Document#101 belongs to Alice/t1, shared with Bob as VIEWER.
- Document#102 belongs to Bob/t1, shared with Alice as EDITOR.
- Document#103 belongs to manager/t1, unshared.
- Document#201 belongs to Carol/t2.

This is learning storage, not a real database. In production, use repositories, FK constraints, transactions, and a membership/ACL invalidation strategy.

### 5.6. TenantPolicy: trusts only Authentication and server data

**`src/main/java/com/example/tenant/TenantPolicy.java`**

```java
package com.example.tenant;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {
    private final Catalog data;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public TenantPolicy(Catalog data) {
        this.data = data;
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (required.equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    private boolean context(
            Authentication auth, String tenant, String headerTenant) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)
                || tenant == null || tenant.isBlank()) {
            return false;
        }

        // Header is only a selector. If present, it must match path.
        if (headerTenant != null && !tenant.equals(headerTenant)) {
            return false;
        }

        // Membership proof comes from the server.
        return data.member(tenant, auth.getName());
    }

    private boolean scopedAdmin(Authentication auth, String tenant) {
        return hasAuthority(auth, "ROLE_TENANT_ADMIN")
            && data.adminBinding(tenant, auth.getName());
    }

    public boolean canRead(
            Authentication auth, String tenant, Long docId,
            String headerTenant) {
        if (!context(auth, tenant, headerTenant)) {
            return false;
        }
        Catalog.Document doc = data.find(docId);
        if (doc == null || !tenant.equals(doc.tenantId())) {
            return false;
        }
        String user = auth.getName();
        return doc.owner().equals(user)
            || data.share(docId, user) == Catalog.ShareLevel.VIEWER
            || data.share(docId, user) == Catalog.ShareLevel.EDITOR
            || scopedAdmin(auth, tenant);
    }

    public boolean canEdit(
            Authentication auth, String tenant, Long docId,
            String headerTenant, String bodyTenant) {
        if (!context(auth, tenant, headerTenant)
                || bodyTenant == null
                || !tenant.equals(bodyTenant)) {
            return false;
        }
        Catalog.Document doc = data.find(docId);
        if (doc == null || !tenant.equals(doc.tenantId())) {
            return false;
        }
        String user = auth.getName();
        return doc.owner().equals(user)
            || data.share(docId, user) == Catalog.ShareLevel.EDITOR
            || scopedAdmin(auth, tenant);
    }

    public boolean canCreate(
            Authentication auth, String tenant,
            String headerTenant, String bodyTenant) {
        return context(auth, tenant, headerTenant)
            && bodyTenant != null
            && tenant.equals(bodyTenant)
            && (hasAuthority(auth, "document:create")
                || scopedAdmin(auth, tenant));
    }
}
```

Read the policy in order:
1. Authentication is non-null, authenticated, and not anonymous.
2. Route tenant is valid and header, if present, matches the route.
3. Caller is a member of the right tenant in the server source.
4. READ/EDIT: document must exist and have its canonical tenant matching the route.
5. EDIT/CREATE: body tenant must match the route tenant.
6. Action permission: owner, appropriate share level, or admin holding both the role and tenant binding. CREATE requires `document:create` or scoped admin.

No branch turns headers `X-User`, `X-Role`, or body tenant into roles/authorities. Unknown IDs/tenants and all mismatches return false.

### 5.7. DocumentService: pre-check, never accepts owner from body

**`src/main/java/com/example/tenant/DocumentService.java`**

```java
package com.example.tenant;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(
            Long id, String tenantId, String owner, String title) {}

    private final Catalog data;
    private final TenantPolicy policy;

    public DocumentService(Catalog data, TenantPolicy policy) {
        this.data = data;
        this.policy = policy;
    }

    private static Authentication caller() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    private static DocumentView toView(Catalog.Document doc) {
        return new DocumentView(
            doc.id(), doc.tenantId(), doc.owner(), doc.title());
    }

    @PreAuthorize(
        "@tenantPolicy.canRead(authentication," +
        "#tenantId,#documentId,#headerTenant)"
    )
    public DocumentView read(
            @P("tenantId") String tenantId,
            @P("documentId") Long documentId,
            @P("headerTenant") String headerTenant) {

        if (!policy.canRead(
                caller(), tenantId, documentId, headerTenant)) {
            throw new AccessDeniedException("Permission changed");
        }
        Catalog.Document doc = data.find(documentId);
        if (doc == null || !tenantId.equals(doc.tenantId())) {
            throw new AccessDeniedException("Tenant changed");
        }
        return toView(doc);
    }

    @PreAuthorize(
        "@tenantPolicy.canEdit(authentication," +
        "#tenantId,#documentId,#headerTenant,#bodyTenant)"
    )
    public DocumentView rename(
            @P("tenantId") String tenantId,
            @P("documentId") Long documentId,
            @P("headerTenant") String headerTenant,
            @P("bodyTenant") String bodyTenant,
            String title) {

        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Title required");
        }
        if (!policy.canEdit(
                caller(), tenantId, documentId,
                headerTenant, bodyTenant)) {
            throw new AccessDeniedException("Permission changed");
        }
        Catalog.Document result =
            data.rename(documentId, tenantId, title);
        if (result == null) {
            throw new AccessDeniedException("Tenant changed");
        }
        return toView(result);
    }

    @PreAuthorize(
        "@tenantPolicy.canCreate(authentication," +
        "#tenantId,#headerTenant,#bodyTenant)"
    )
    public DocumentView create(
            @P("tenantId") String tenantId,
            @P("headerTenant") String headerTenant,
            @P("bodyTenant") String bodyTenant,
            String title) {

        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Title required");
        }
        if (!policy.canCreate(
                caller(), tenantId, headerTenant, bodyTenant)) {
            throw new AccessDeniedException("Permission changed");
        }

        // Tenant = verified route; owner = authenticated principal.
        return toView(data.create(
            tenantId, caller().getName(), title));
    }
}
```

`@P` tells SpEL the names of the method parameters. `@PreAuthorize` denies before the target runs. The re-check branches inside the method body reduce the window for state changes, yet **do not replace** transactions/row locks when production updates permissions concurrently.

`rename` only changes the title, keeping tenant and owner intact. If moving a document to another tenant is needed, build a dedicated move use case checking permissions in **both source and target tenants**, data constraints, and all related grants/ACLs.

### 5.8. Controller: passes inputs to service, never self-grants permissions

**`src/main/java/com/example/tenant/DocumentController.java`**

```java
package com.example.tenant;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants")
public class DocumentController {
    public record WriteBody(String tenantId, String title) {}

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{tenantId}/documents/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("documentId") Long documentId,
            @RequestHeader(
                name = "X-Tenant-Id", required = false
            ) String headerTenant) {
        return service.read(tenantId, documentId, headerTenant);
    }

    @PutMapping("/{tenantId}/documents/{documentId}")
    public DocumentService.DocumentView rename(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("documentId") Long documentId,
            @RequestHeader(
                name = "X-Tenant-Id", required = false
            ) String headerTenant,
            @RequestBody WriteBody request) {
        return service.rename(
            tenantId, documentId, headerTenant,
            request.tenantId(), request.title());
    }

    @PostMapping("/{tenantId}/documents")
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentService.DocumentView create(
            @PathVariable("tenantId") String tenantId,
            @RequestHeader(
                name = "X-Tenant-Id", required = false
            ) String headerTenant,
            @RequestBody WriteBody request) {
        return service.create(
            tenantId, headerTenant,
            request.tenantId(), request.title());
    }
}
```

`WriteBody` accepts only the fields used: `tenantId` and `title`. `owner` never comes from the client. If you also want to **reject JSON containing unknown fields** to harden against mass assignment, configure Jackson/Bean Validation accordingly; the demo guarantees it never **uses** a client-declared owner field.

## 6. Integration tests: URL/header/body and real permissions

Use `@SpringBootTest`, `@AutoConfigureMockMvc`, and `@WithMockUser` to traverse the security filter and Method Security proxy. Stateful tests call `catalog.reset()` before each test. Tests attach a CSRF token for POST/PUT; since HTTP Basic + default Spring Security keeps CSRF enabled, omitting the token yields 403 before tenant checks run.

**`src/test/java/com/example/tenant/TenantVerificationTest.java`**

```java
package com.example.tenant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantVerificationTest {
    @Autowired MockMvc mvc;
    @Autowired Catalog catalog;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        catalog.reset();
    }

    private static String doc(String tenant, long id) {
        return "/api/tenants/" + tenant + "/documents/" + id;
    }

    private static String createPath(String tenant) {
        return "/api/tenants/" + tenant + "/documents";
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerReadsWithoutTenantHeader() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("t1"));
    }

    @Test
    @WithMockUser(username = "alice")
    void matchingHeaderIsAccepted() throws Exception {
        mvc.perform(get(doc("t1", 101))
                .header("X-Tenant-Id", "t1"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice")
    void headerTenantMismatchIsDenied() throws Exception {
        mvc.perform(get(doc("t1", 101))
                .header("X-Tenant-Id", "t2"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void routeCannotForgeResourceTenant() throws Exception {
        mvc.perform(get(doc("t1", 201)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void routeCannotGrantTenantMembership() throws Exception {
        mvc.perform(get(doc("t2", 201)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "carol")
    void actualMemberMayReadOwnTenant() throws Exception {
        mvc.perform(get(doc("t2", 201)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerShareCanReadWithinTenant() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob")
    void membershipDoesNotGrantEveryDocument() throws Exception {
        mvc.perform(get(doc("t1", 103)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mallory")
    void forgedTenantHeaderCannotCreateMembership() throws Exception {
        mvc.perform(get(doc("t1", 101))
                .header("X-Tenant-Id", "t1"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void forgedIdentityHeaderDoesNotMakeUserAdmin() throws Exception {
        mvc.perform(get(doc("t1", 103))
                .header("X-User", "manager")
                .header("X-Role", "ROLE_TENANT_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminReadsOwnTenantDocument() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminCannotReadOtherTenant() throws Exception {
        mvc.perform(get(doc("t2", 201)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "TENANT_ADMIN")
    void roleWithoutAdminBindingIsDenied() throws Exception {
        mvc.perform(get(doc("t1", 103)))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestGets401() throws Exception {
        mvc.perform(get(doc("t1", 101)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownRecordIsDenied() throws Exception {
        mvc.perform(get(doc("t1", 999)))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "alice", authorities = "document:create")
    void createUsesVerifiedTenantAndAuthenticatedOwner()
            throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .header("X-Tenant-Id", "t1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"New note\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.tenantId").value("t1"))
            .andExpect(jsonPath("$.owner").value("alice"));
        assertEquals("alice", catalog.find(301L).owner());
    }

    @Test
    @WithMockUser(username = "alice")
    void createWithoutCapabilityIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "alice", authorities = "document:create")
    void createBodyTenantMismatchIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t2\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "alice", authorities = "document:create")
    void createHeaderTenantMismatchIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .header("X-Tenant-Id", "t2")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
        username = "mallory", authorities = "document:create")
    void createAuthorityWithoutMembershipIsDenied() throws Exception {
        mvc.perform(post(createPath("t1"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCanEditWithMatchingSelectors() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .header("X-Tenant-Id", "t1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Revised\"}"))
            .andExpect(status().isOk());
        assertEquals("Revised", catalog.find(101L).title());
    }

    @Test
    @WithMockUser(username = "alice")
    void editBodyTenantMismatchIsDenied() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t2\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
        assertEquals("Alice notes", catalog.find(101L).title());
    }

    @Test
    @WithMockUser(username = "alice")
    void editHeaderTenantMismatchIsDenied() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .header("X-Tenant-Id", "t2")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
        assertEquals("Alice notes", catalog.find(101L).title());
    }

    @Test
    @WithMockUser(username = "bob")
    void viewerCannotEditSharedDocument() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void editorMayEditAnotherOwnerDocument() throws Exception {
        mvc.perform(put(doc("t1", 102))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Edited\"}"))
            .andExpect(status().isOk());
        assertEquals("Edited", catalog.find(102L).title());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminMayEditOwnTenant() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"Managed\"}"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminCannotEditOtherTenant() throws Exception {
        mvc.perform(put(doc("t2", 201))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t2\",\"title\":\"Forbidden\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void csrfProtectsPutEvenForOwner() throws Exception {
        mvc.perform(put(doc("t1", 101))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"t1\",\"title\":\"No CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void serviceMethodRejectsUnauthorizedRead() {
        assertThrows(AccessDeniedException.class,
            () -> service.read("t1", 103L, null));
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn test
```

The test count in the file matches the number of `@Test` methods; all are expected to pass if the project uses the dependencies and configuration above. This is an **expected outcome from reading the source code**, not a claim that Maven was executed. `@WithMockUser` simulates identity to test authorization; real JWTs additionally require tests for signature verification, issuer, audience, expiration, and membership revocation.

Takeaways from the tests:
- Path t2 does not grant membership; header t2 does not override path t1.
- Body tenant t2 cannot move Document#101 out of t1.
- Even though Document#201 exists, Alice cannot reach it through route t1.
- Bob in t1 can only READ Document#101 shared as VIEWER; he cannot EDIT it.
- Manager with role and binding for t1 cannot access t2 records.
- Client-sent `X-User`/`X-Role` headers do not replace Authentication.
- `@PreAuthorize` still blocks direct calls into the Spring-managed service outside HTTP.
- Missing CSRF on PUT is rejected under the current servlet security configuration.

## 7. With a real database: tenant predicates are a mandatory defense layer

### 7.1. READ by ID and verified tenant

```sql
SELECT id, tenant_id, owner_id, title
FROM document
WHERE id = :documentId
  AND tenant_id = :verifiedTenantId;
```

`:verifiedTenantId` is the tenant candidate verified against Membership/Authentication, **not** a direct copy of a raw header. If no record matches, return deny/not-found per policy; never disclose that the ID belongs to another tenant.

With Spring Data JPA:

```java
public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {
    Optional<DocumentEntity> findByIdAndTenantId(
        Long id, String tenantId);
}
```

This is a **repository illustration**, requiring Spring Data JPA, an entity, and a datasource. It is not part of the in-memory project in section 5. Tenant-qualified queries reduce the risk of another method accidentally omitting the tenant filter.

### 7.2. UPDATE must never have `WHERE id=?` alone

```sql
UPDATE document
SET title = :newTitle
WHERE id = :documentId
  AND tenant_id = :verifiedTenantId
  AND (
    owner_id = :authenticatedUserId
    OR EXISTS (
        SELECT 1
        FROM document_share s
        WHERE s.document_id = document.id
          AND s.user_id = :authenticatedUserId
          AND s.access_level = 'EDITOR'
    )
  );
```

This is an illustrative SQL pattern excluding the scoped-admin branch; if added, verify the role binding against the same tenant. After updating, check affected row count = 1. If owner/share rights are revoked concurrently or the document changes tenants, add transactions/isolation, row locks, or optimistic versioning commensurate with risk. `@PreAuthorize` alone does not eliminate **TOCTOU** races.

### 7.3. CREATE must assign tenant/owner server-side

Creating a new record has no pre-existing object ID. Verify `canCreate(authentication,tenant)` and then insert:

```sql
INSERT INTO document(tenant_id, owner_id, title)
VALUES (:verifiedTenantId, :authenticatedUserId, :title);
```

Never write `entity.setTenantId(request.tenantId())` before verifying membership/permission, and never copy `request.ownerId` as owner. In schemas with an organization table, use FKs and tenant constraints for parent resources.

### 7.4. List, search, count, and export must isolate tenants

The same policy must govern:
- `GET /documents` with pagination, sorting, and aggregates.
- File downloads, attachments, reports, and CSV exports.
- Search indexes, background jobs, batch deletes, and webhook/event consumers.
- Cache keys, object storage keys, and presigned URL generation.

Never query across all tenants and filter after pagination: counts, metadata, and results can leak. Pattern:

```sql
SELECT d.id, d.title
FROM document d
WHERE d.tenant_id = :verifiedTenantId
  AND (
      d.owner_id = :authenticatedUserId
      OR EXISTS (
          SELECT 1 FROM document_share s
          WHERE s.document_id = d.id
            AND s.user_id = :authenticatedUserId
      )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

COUNT/facet queries must use the **same tenant/permission predicates**. If your system uses parent/child ACLs, roles, or business workflows, include those conditions before pagination.

## 8. Multi-tenant JWT, proxies, and TenantContext

### 8.1. Trusted issuers, never fetch JWKS from an arbitrary header

Spring Security 6.5 supports `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` for multi-issuer resource servers. A valid JWT must pass signature, issuer, audience, expiry, and configured validator checks. Issuer/JWKS endpoints must come from a **server-managed allowlist/registry**.

Never read `X-Tenant-Id: attacker` and construct `https://attacker/.well-known/jwks.json` to trust an arbitrary public key. Even when using a verified JWT's `tenantId` claim as an entitlement basis, match it against the resource's tenant and define a revocation/membership lookup strategy.

### 8.2. Reverse proxy headers are trusted only when authenticated

A gateway may emit internal headers carrying user/tenant, which is safe only when:
1. The gateway strips all incoming client headers of the same name.
2. The backend cannot be reached directly to bypass the gateway.
3. The backend authenticates the gateway via mTLS/signatures/internal credentials.
4. Tenant/roles in headers are verified by the gateway and tightly scoped.
5. Header spoofing and duplicate headers are covered by tests.

Outside that model, `Host`, `X-Forwarded-Host`, `X-User`, `X-Role`, and `X-Tenant-Id` must be treated as client-controlled data. Never use them to substitute a principal or grant roles.

### 8.3. TenantContext, schema-per-tenant, and database-per-tenant

With shared tables, every query needs a tenant predicate. With schema-per-tenant or database-per-tenant, a `TenantResolver` can pick the schema/DataSource, but **must never pick from a raw header before membership checks**. Require a allowlisted tenant registry and explicit routing, preventing raw input from becoming an arbitrary SQL identifier or DataSource name.

If using `ThreadLocal` to hold the selected tenant for JDBC/Hibernate:

```java
try {
    // Caller is already authenticated and membership verified earlier.
    tenantContext.set(verifiedTenant);
    filterChain.doFilter(request, response);
} finally {
    tenantContext.clear();
}
```

This is **pseudo-code** for a filter, not a standalone class. Never omit `finally`: thread pools can reuse the previous request's tenant. In `@Async`, Reactor, or job/message consumers, SecurityContext/tenant context does not propagate automatically the same way; build a dedicated propagation strategy and verify it.

### 8.4. Caching and auditing

Cache keys must differentiate tenants: `(tenantId, documentId, principal/permission version)` when content depends on permissions. A key `document:101` leaks data if IDs are only unique per tenant. When membership is revoked, stale caches and tokens require an invalidation/TTL plan.

Audit logs should include the authenticated actor, requested tenant, canonical tenant (if any), resource ID, action, outcome, and policy version; avoid logging tokens/secrets or returning distinct messages that reveal another tenant's content.

## 9. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `X-Tenant-Id` automatically becomes an authority | Privilege escalation | Derive membership/roles from trusted sources |
| Body `tenantId` written straight to entity | Unauthorized tenant reassignment | Whitelist DTO fields, server-assign tenant/owner |
| Route `/tenants/t1` yet query uses only `WHERE id=?` | Cross-tenant BOLA | Query with `tenant_id=? AND id=?` |
| Tenant header differs from route and service prefers header | Confused deputy | Reject mismatch |
| `hasRole('ADMIN') or policy(...)` | Admin bypasses tenant boundary | Scope admin binding within the specific tenant |
| JWT without issuer/audience/signature verification | Accepts forged/wrong-audience tokens | Trusted JWT validators |
| Every tenant member can READ everything | Exposes internal records | Add owner/share/action checks |
| Cache key omits tenant | Serves another tenant's data | Include tenant and permission scope in key |
| Tenant ThreadLocal not cleared | Scope leaks across requests | `finally.remove()` |
| Testing only URL, skipping header/body | Misses spoofing/mass assignment | Negative test matrix for every input |
| Filtering list after pagination | Leaks aggregates, wrong page sizes | Apply tenant/permission predicates before paging |
| Protecting only Controllers | Batch/service paths bypass checks | Service-level Method Security |
| `@PostAuthorize` on mutations | Side effects happen before denial | `@PreAuthorize` and guarded updates |
| Client picks JWT issuer/JWKS | Trusts attacker-controlled signer | Issuer allowlist |
| Blindly `trim()/lowercase` all tenant IDs | Collides distinct scopes | Canonicalize per contract |
| Trusting `X-Forwarded-Host` everywhere | Host spoofing | Trust only authenticated proxy chains |

## 10. Code review checklist

- [ ] Tenant in URL/header/query/body/subdomain is treated strictly as a selector needing verification.
- [ ] Authentication comes from verified credentials/session/JWT, never arbitrary `X-User` or `X-Role`.
- [ ] Admin roles are bound per tenant; revoked memberships have a refresh mechanism.
- [ ] Conflicting selectors within the same request are rejected, never silently overridden.
- [ ] Resource IDs have canonical tenants and are queried with tenant-qualified predicates.
- [ ] Read/edit/create/delete permissions are checked in addition to membership.
- [ ] DTOs prevent changing tenant/owner via unauthorized operations.
- [ ] CREATE assigns owner from Authentication and tenant from the verified value.
- [ ] UPDATE/DELETE verify affected rows and concurrency policy.
- [ ] List/count/search/export share the same tenant/permission predicates.
- [ ] Duplicate headers, tenant ID format, Unicode/case, and path encoding are tested.
- [ ] Trusted issuer/JWKS, audience, expiration, and allowed tenants are validated.
- [ ] Gateway strips incoming identity headers, and backend prevents bypass.
- [ ] TenantContext does not leak across threads/async/connection pools; cache keys include tenant.
- [ ] Cross-tenant tests cover URL, header, body, ID, owner/share/admin, and direct service calls.

## 11. Self-check

**Question 1.** Alice belongs to t1; a request sends URL t2, header t2, and body t2. Why is it still denied?

**Answer:** The three values agree, but all three are client-controlled; server membership does not grant t2 access to Alice.

**Question 2.** Alice in t1 calls URL t1 with a document ID belonging to t2; is checking t1 membership enough?

**Answer:** No. You must check the record's canonical tenant via a tenant-predicated query.

**Question 3.** Bob holds `ROLE_TENANT_ADMIN` without an admin binding in t1; can he read Document#103?

**Answer:** No under the demo policy. A role string alone does not define tenant scope; membership/binding and resource permissions are also required.

**Question 4.** Body contains `owner:"mallory"` during CREATE; which owner should the backend assign?

**Answer:** The authenticated principal (e.g., Alice), never the client-supplied field. Under a strict schema, unknown fields can also be rejected.

**Question 5.** `@PreAuthorize` already permits EDIT, so why should SQL still include `WHERE tenant_id=?`?

**Answer:** To protect other code paths and narrow TOCTOU windows. Pre-checks do not guarantee tenant/ACL cannot change between the two steps.

## 12. References

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): HTTP request authorization, matcher order, URI variables, deny-by-default.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and policy beans.
- [Spring Security 6.5 — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html): trusted issuers, tenant resolution, and propagation.
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer, and token validation.
- [OWASP API Security Top 10 (2023) — API1 BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object-level authorization for APIs taking client-supplied IDs.
- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` and authorization decision testing.

**Remember:** A tenant in URL, header, body, or query is an **untrusted input to verify**, not proof of authorization. Permit operations only after verifying **trusted Authentication, per-tenant membership/role binding, the resource's canonical tenant, and the action's permission**. Reject all mismatches, keep tenant predicates in repositories, and test every client-modifiable tenant source individually.