# Separating Authorization Policy from Controllers and Data-Access Logic in Spring Security Servlet

**Scope:** Java 17+, Spring Boot 3.x / Spring Security 6.x on the Servlet stack. This article belongs to **Authorization Models**. The goal is designing authorization that can be tested, reused, and changed independently of HTTP Controllers and data-access operations—preventing IDOR/BOLA bugs, confusing roles with per-record permissions, and leaving alternative entry points unprotected.

Real systems face questions such as: "May this user view this document?", "May they edit a document belonging to another tenant?", "Managers may view all documents in the same tenant, yet may they edit on the owner's behalf?". These are **authorization business rules**, not HTTP routing details and not mere SELECT/UPDATE statements.

## 1. Why Should Authorization Conditions Not Live Inside Controllers?

Suppose a controller is written like this:

~~~java
@GetMapping("/documents/{id}")
public DocumentDto get(@PathVariable long id, Authentication auth) {
    Document doc = repository.findById(id).orElseThrow();
    if (!doc.ownerUsername().equals(auth.getName())) {
        throw new AccessDeniedException("Not allowed");
    }
    return toDto(doc);
}
~~~

This snippet **illustrates the problem**; it is not a standalone program. It may block one GET route, yet as soon as a PDF export endpoint, GraphQL resolver, batch export, or scheduled job invokes the service, that same rule is easily forgotten or copied inconsistently.

Common consequences:
- Authorization rules scatter across multiple controllers, endpoints, and handlers.
- One controller gets updated while another keeps stale logic.
- Data is fetched before authorization checks and can accidentally be logged or serialized.
- Ownership gets checked against user-supplied parameters instead of server-verified identity.
- Business services get called from other places without going through the controller that holds the check.
- Unit-testing business rules forces constructing HTTP requests just to verify policy.
- Tenant, document state, group, or permission rules cause `if/else` blocks to bloat.

**The goal is not to strip all security concerns from Controllers**, but to separate duties: the Controller handles HTTP and data mapping; the authorization layer defines and evaluates policies; the service guarantees use cases run only when permitted; the repository handles properly scoped data access.

## 2. Distinguishing Authentication, Authorization, Policy, and Enforcement

| Concept | Question | Example |
| --- | --- | --- |
| Authentication | Who is calling? | Spring Security verifies alice via HTTP Basic/session/JWT |
| Identity/principal | Trusted caller identifier | <code>Authentication.getName()</code> |
| GrantedAuthority | Broad roles/privileges granted | <code>ROLE_USER</code>, <code>ROLE_MANAGER</code> |
| Authorization policy | Who may do what on which resource, in what context? | Owner may edit document; manager may only read within same tenant |
| Policy enforcement | Where the policy outcome is enforced | <code>@PreAuthorize</code> on public service methods |
| Data scope | Queries touch only permitted data scope | <code>WHERE tenant_id = :tenantId</code> plus owner/status as needed |
| Audit | Who attempted what, and what was decided? | Document 42: read allowed / edit denied |

In architectural terms, the **Policy Decision Point (PDP)** evaluates allow/deny; the **Policy Enforcement Point (PEP)** blocks execution on deny; the **Policy Information Point (PIP)** provides attributes such as owner, tenant, state, and permissions. All three can be plain classes in the same application; no standalone policy server is required.

~~~text
Client
   |
   v
SecurityFilterChain: authenticate and apply coarse HTTP checks
   |
   v
Controller: parse path/body, return response/DTO
   |
   v
DocumentService: enforce authorization before use case
   |            |
   |            +--> DocumentPolicy: allow/deny
   |                         |
   |                         +--> TenantDirectory (server-trusted)
   |                         +--> DocumentStore (owner, tenant)
   v
Repository / Store: query and update within proper scope
   |
   v
Response DTO: include only permitted fields
~~~

Policy decides **whether access is allowed**; data access decides **which records are read and modified**. Both work together, without collapsing into an ad-hoc controller block.

## 3. A Clear Policy Matrix Before Writing Code

Our practice app manages documents with <code>id</code>, <code>tenantId</code>, <code>ownerUsername</code>, <code>title</code>, and <code>content</code>. Users have server-managed tenants:

| User | Tenant | Authorities |
| --- | --- | --- |
| alice | tenant-a | ROLE_USER |
| bob | tenant-a | ROLE_USER |
| carol | tenant-b | ROLE_USER |
| mia | tenant-a | ROLE_USER, ROLE_MANAGER |

Sample data:

| Document | Owner | Tenant |
| --- | --- | --- |
| 1 | alice | tenant-a |
| 2 | bob | tenant-a |
| 3 | carol | tenant-b |

Desired policy:
1. Unauthenticated: cannot read or edit any document.
2. User in the same tenant **and owner**: may read and edit their own document.
3. Manager in the same tenant: may **read** documents of other owners in that tenant.
4. Manager **may not automatically edit** others' documents; editing is reserved for the owner.
5. All other cases, especially cross-tenant: deny.
6. Nonexistent document ID: denied by policy in the demo so we do not create an oracle distinguishing "exists but unauthorized" from "does not exist".
7. Clients cannot supply `tenantId` or `ownerUsername` when editing content.

Expected decision matrix:

| Caller | GET doc 1 | GET doc 2 | GET doc 3 | PUT doc 1 |
| --- | --- | --- | --- | --- |
| alice | Allow | Deny | Deny | Allow |
| bob | Deny | Allow | Deny | Deny |
| carol | Deny | Deny | Allow | Deny |
| mia (tenant-a manager) | Allow | Allow | Deny | Deny |
| Anonymous | Deny | Deny | Deny | Deny |

A role like <code>ROLE_MANAGER</code> is **not** permission to read every tenant. Tenant is an independent boundary; access is granted only when both tenant scope and business rules pass. This is **RBAC combined with ownership/attribute-based authorization**.

## 4. Separating Responsibilities by Layer

**SecurityFilterChain:** performs authentication, CSRF, and coarse rules like "only logged-in users may access <code>/documents/**</code>". There is no need to encode every owner/tenant case in URL matchers.

**Controller:** extracts <code>id</code> from path, reads body, invokes service, returns DTO/status. Never repeats <code>if (auth.getName().equals(owner))</code> in every endpoint.

**Policy:** a class with a clear name and contract, such as <code>DocumentPolicy.canRead(auth, doc)</code> and <code>canEdit(auth, doc)</code>. Policy understands privileges, tenants, and owners; it never renders JSON or mutates data.

**Service/use case:** entry point enforcing policy before critical operations; can use <code>@PreAuthorize</code>, <code>AuthorizationManager</code>, or explicit policy calls. Never rely solely on an HTTP Controller existing to guard business operations.

**Repository:** executes queries scoped by tenant/owner, plus transactions and locking for concurrent writes. Pre-operation policy checks and SQL data filters reinforce each other; a SELECT before UPDATE alone is insufficient against TOCTOU.

**DTO/serialization:** filters outbound fields. Having permission to view a document does not imply receiving internal fields like password hashes, customer PII, or audit secrets.

## 5. Should You Use @PreAuthorize or Check Inside the Service?

Spring Security supports **method security**:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecuritySetup { }
~~~

On Spring-managed beans with public methods invoked **through a Spring proxy**, <code>@PreAuthorize</code> evaluates an expression before the method executes:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public DocumentView read(@P("docId") Long docId) {
    // Data-fetching logic runs only after policy permits.
}
~~~

In this snippet:
- <code>authentication</code> comes from the Spring Security context, never a client-supplied string.
- <code>@documentPolicy</code> references the policy bean.
- <code>#docId</code> is the method parameter, annotated with <code>@P("docId")</code> so SpEL does not depend on parameter names stripped at compile time.
- If the policy returns false, the method-security interceptor throws <code>AccessDeniedException</code>; the HTTP stack maps status based on authentication/entry point.
- Code inside the method runs only once permitted. The annotation does not automatically protect other repository calls invoked directly elsewhere.

**Placing annotations on the service** lets enforcement be reused whether the service is called from HTTP, a messaging adapter, or another bean. It does not automatically protect internal <code>this.read(...)</code> calls within the same instance because proxy interception may be bypassed; test entry points and bean call boundaries.

Alternatively, the service can invoke the policy directly and throw <code>AccessDeniedException</code>. That fits well when checking privileges on an already-loaded aggregate or inside the same transaction. This demo uses <code>@PreAuthorize</code> to illustrate a clear enforcement point.

## 6. Complete Project: HTTP Basic + Method Security + DocumentPolicy

The example uses **Java 17, Spring Boot 3.3.5, Spring Security 6.x, and Maven**, running in a single process. In-memory repositories and tenant maps are for practice only, not production persistence templates. Hardcoded passwords below are for localhost only.

Structure:

~~~text
document-policy-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/documentpolicy/
    │   ├── DocumentPolicyApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── Document.java
    │   ├── DocumentView.java
    │   ├── DocumentStore.java
    │   ├── TenantDirectory.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/com/example/documentpolicy/
        └── DocumentAuthorizationTest.java
~~~

### 6.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>document-policy-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
~~~

### 6.2. Application Class

Create <code>src/main/java/com/example/documentpolicy/DocumentPolicyApplication.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DocumentPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(DocumentPolicyApplication.class, args);
    }
}
~~~

### 6.3. Domain Record and Output DTO

Create <code>src/main/java/com/example/documentpolicy/Document.java</code>:

~~~java
package com.example.documentpolicy;

public record Document(
        Long id,
        String tenantId,
        String ownerUsername,
        String title,
        String content) {
}
~~~

Record <code>Document</code> carries owner and tenant as **attributes for the policy to evaluate**. Those attributes must come from server-managed storage, never trusted from a client-declared <code>X-Tenant</code>.

Create <code>src/main/java/com/example/documentpolicy/DocumentView.java</code>:

~~~java
package com.example.documentpolicy;

public record DocumentView(Long id, String title, String content) {
    public static DocumentView from(Document doc) {
        return new DocumentView(doc.id(), doc.title(), doc.content());
    }
}
~~~

This DTO intentionally omits <code>tenantId</code> and <code>ownerUsername</code>. When a product needs to display owner or tenant, decide which fields are genuinely needed and allowed; DTOs control outbound data, never replacing service-level authorization.

### 6.4. Demo Repository: Separating CRUD from Access Decisions

Create <code>src/main/java/com/example/documentpolicy/DocumentStore.java</code>:

~~~java
package com.example.documentpolicy;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {

    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>();

    public DocumentStore() {
        documents.put(1L,
            new Document(1L, "tenant-a", "alice",
                "Alice report", "initial-a"));
        documents.put(2L,
            new Document(2L, "tenant-a", "bob",
                "Bob report", "initial-b"));
        documents.put(3L,
            new Document(3L, "tenant-b", "carol",
                "Carol report", "initial-c"));
    }

    public Optional<Document> find(Long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document updateContent(Long id, String newContent) {
        return documents.computeIfPresent(id, (key, old) ->
            new Document(old.id(), old.tenantId(),
                old.ownerUsername(), old.title(), newContent));
    }
}
~~~

The repository only stores and retrieves documents; **it does not decide who may read them**. In the demo, <code>tenantId</code> and <code>ownerUsername</code> remain immutable when updating content: the update method does not accept owner/tenant from the request. With a real database, policy enforcement and UPDATE must jointly enforce tenant/owner constraints inside a transaction or SQL condition to prevent race conditions.

### 6.5. Trusted Server-Side Tenant Source

Create <code>src/main/java/com/example/documentpolicy/TenantDirectory.java</code>:

~~~java
package com.example.documentpolicy;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {

    private final Map<String, String> memberships = Map.of(
        "alice", "tenant-a",
        "bob", "tenant-a",
        "carol", "tenant-b",
        "mia", "tenant-a"
    );

    public String tenantOf(String username) {
        return memberships.get(username);
    }
}
~~~

This is a demo fixture. In production, tenant context must come from server/IdP-verified memberships or a database, with controls for multi-tenant accounts. Headers like <code>X-Tenant</code> or query parameters like <code>tenantId</code> are only tenant-selection requests, **never** proof the user has access to that tenant.

For multi-tenant users, policy must also verify membership in the target/selected tenant and corresponding privileges, rather than assuming a single static mapping as in the demo.

### 6.6. DocumentPolicy: Centralizing Allow/Deny Rules

Create <code>src/main/java/com/example/documentpolicy/DocumentPolicy.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentStore store;
    private final TenantDirectory tenants;

    public DocumentPolicy(DocumentStore store, TenantDirectory tenants) {
        this.store = store;
        this.tenants = tenants;
    }

    public boolean canRead(Authentication auth, Long id) {
        return store.find(id)
            .map(doc -> canReadDocument(auth, doc))
            .orElse(false);
    }

    public boolean canEdit(Authentication auth, Long id) {
        return store.find(id)
            .map(doc -> canEditDocument(auth, doc))
            .orElse(false);
    }

    boolean canReadDocument(Authentication auth, Document doc) {
        if (!sameTenant(auth, doc)) {
            return false;
        }
        return doc.ownerUsername().equals(auth.getName())
            || hasAuthority(auth, "ROLE_MANAGER");
    }

    boolean canEditDocument(Authentication auth, Document doc) {
        return sameTenant(auth, doc)
            && doc.ownerUsername().equals(auth.getName());
    }

    private boolean sameTenant(Authentication auth, Document doc) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        String trustedTenant = tenants.tenantOf(auth.getName());
        return trustedTenant != null
            && trustedTenant.equals(doc.tenantId());
    }

    private boolean hasAuthority(Authentication auth, String authority) {
        for (GrantedAuthority granted : auth.getAuthorities()) {
            if (authority.equals(granted.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
~~~

Why this class is a **policy**:
- It returns a boolean decision—no <code>HttpServletResponse</code>, no JSON serialization, no redirects.
- It does not mutate documents; checking privileges is separate behavior.
- It uses **server-authenticated** principal/authorities, tenants from a **trusted** directory, and owner/tenant from **server-stored** documents.
- When the document is missing or membership is absent, it defaults to false (**deny by default**).
- Managers can read only within the same tenant; MANAGER does not mean system-wide access.
- `canRead`/`canEdit` can be unit-tested directly without running HTTP.

<code>Authentication.isAuthenticated()</code> alone is insufficient to distinguish anonymous tokens in every Spring Security setup. In the demo, anonymous has no directory entry so <code>sameTenant</code> returns false; additionally `SecurityFilterChain` already requires `authenticated` for document routes. In general systems, use an appropriate trust check (such as a trust resolver) and ensure identity/tenant cannot be spoofed by untrusted callers.

More sophisticated policies can also check document status, classification, delegation, time, request origin, or action. Keep those rules inside a cohesive policy rather than copying them across controllers.

### 6.7. DocumentService: Enforcement Point for Use Cases

Create <code>src/main/java/com/example/documentpolicy/DocumentService.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
    public DocumentView read(@P("docId") Long docId) {
        Document doc = store.find(docId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
        return DocumentView.from(doc);
    }

    @PreAuthorize("@documentPolicy.canEdit(authentication, #docId)")
    public DocumentView replaceContent(
            @P("docId") Long docId, String newContent) {

        if (newContent == null || newContent.isBlank()
                || newContent.length() > 1_000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid content");
        }

        Document updated = store.updateContent(docId, newContent);
        if (updated == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        return DocumentView.from(updated);
    }
}
~~~

The service **contains no owner/manager/tenant conditionals**. It simply declares *which policy must pass* to execute the use case, then processes data and returns a DTO.

- <code>@PreAuthorize</code> enforces **before running** `read`/`replaceContent`.
- <code>@P("docId")</code> supplies the parameter name to the Spring Security SpEL expression.
- <code>DocumentStore</code> still exposes update methods unaware of the caller, so the system must enforce that all business entry points go through the protected service. Never inject the store directly into a new controller to bypass the service.
- Content validation runs in the service; the controller does not decide policy.
- In the demo, owner/tenant do not change during updates, so the policy reading a document before the service updates it has no race on authorization attributes. **Production systems with mutable ownership/tenants, databases/transactions, or multiple nodes must prevent races at the data source** as shown later.

<code>@PreAuthorize</code> is proxy-based method security: calls through the Spring bean proxy are intercepted; internal calls like <code>this.replaceContent()</code> on the same instance can bypass the proxy. New methods, scheduled jobs, batch/message consumers, and other services must call the enforced service API or apply equivalent authorization checks.

### 6.8. DocumentController: Thin, Free of Owner/Tenant Rules

Create <code>src/main/java/com/example/documentpolicy/DocumentController.java</code>:

~~~java
package com.example.documentpolicy;

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

    public record UpdateBody(String content) { }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/documents/{id}")
    public DocumentView read(@PathVariable Long id) {
        return service.read(id);
    }

    @PutMapping("/documents/{id}")
    public DocumentView update(
            @PathVariable Long id, @RequestBody UpdateBody body) {
        return service.replaceContent(id, body.content());
    }
}
~~~

The controller only maps HTTP GET/PUT, extracts path/body, and delegates to the service. It never accepts <code>ownerUsername</code> or <code>tenantId</code> from the body for authorization. PUT requests are gated by the service policy (and CSRF at the HTTP layer in this demo configuration).

### 6.9. SecurityConfiguration: Coarse-Grained HTTP and Method Security

Create <code>src/main/java/com/example/documentpolicy/SecurityConfiguration.java</code>:

~~~java
package com.example.documentpolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass-123"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass-123"))
                .roles("USER").build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-pass-123"))
                .roles("USER").build(),
            User.withUsername("mia")
                .password(encoder.encode("mia-pass-123"))
                .roles("USER", "MANAGER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers("/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

<code>@EnableMethodSecurity</code> is essential: without it, <code>@PreAuthorize</code> annotations in the demo may not activate. The HTTP check <code>authenticated()</code> only means "logged in"; it is **not** enough to check owner/tenant. The service layer enforces per-resource policy.

Default CSRF remains enabled. With HTTP Basic in browsers, browsers can resend cached `Authorization` headers automatically, so never assume Basic is immune to CSRF. In this article, PUT tests submit a CSRF token via Spring Security's test helper. Never disable CSRF app-wide just to make curl PUTs easier.

Unknown URLs hit <code>anyRequest().denyAll()</code>. If <code>/documents/export</code> is added later, define its use case and enforcement explicitly; never assume `authenticated` suffices.

## 7. MockMvc Tests: Policy Lives Outside the Controller

Create <code>src/test/java/com/example/documentpolicy/DocumentAuthorizationTest.java</code>:

~~~java
package com.example.documentpolicy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAndAuthenticationBoundary() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        mvc.perform(get("/documents/1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownershipTenantAndManagerPolicy() throws Exception {
        // Owner of document 1 can read it.
        mvc.perform(get("/documents/1")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.content").value("initial-a"));

        // Same tenant, but not owner and lacks manager role.
        mvc.perform(get("/documents/2")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isForbidden());

        // Different tenant is also denied.
        mvc.perform(get("/documents/3")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isForbidden());

        // Manager may view only documents in the same tenant.
        mvc.perform(get("/documents/1")
                .with(httpBasic("mia", "mia-pass-123")))
            .andExpect(status().isOk());

        mvc.perform(get("/documents/2")
                .with(httpBasic("mia", "mia-pass-123")))
            .andExpect(status().isOk());

        mvc.perform(get("/documents/3")
                .with(httpBasic("mia", "mia-pass-123")))
            .andExpect(status().isForbidden());

        // Nonexistent document: policy returns false.
        mvc.perform(get("/documents/999")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void modificationEnforcesOwnerAndCsrf() throws Exception {
        // Missing CSRF: PUT is blocked before the business service.
        mvc.perform(put("/documents/1")
                .with(httpBasic("alice", "alice-pass-123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"changed\"}"))
            .andExpect(status().isForbidden());

        // Valid owner + valid CSRF.
        mvc.perform(put("/documents/1")
                .with(httpBasic("alice", "alice-pass-123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"changed-by-alice\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content").value("changed-by-alice"));

        // Same tenant, but document belongs to Bob.
        mvc.perform(put("/documents/2")
                .with(httpBasic("alice", "alice-pass-123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"forbidden\"}"))
            .andExpect(status().isForbidden());

        // Manager can read, yet cannot edit on owner's behalf.
        mvc.perform(put("/documents/1")
                .with(httpBasic("mia", "mia-pass-123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"forbidden\"}"))
            .andExpect(status().isForbidden());

        // Owner's document retains the updated content.
        mvc.perform(get("/documents/1")
                .with(httpBasic("alice", "alice-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content").value("changed-by-alice"));
    }
}
~~~

These tests verify invariants, not just the happy path:
- Anonymous can read `/health`, cannot read `/documents/1` (401 with HTTP Basic).
- Alice can read document 1, yet cannot read Bob's document 2 despite sharing the same tenant (403).
- Alice cannot read document 3 in another tenant.
- Manager Mia can read docs 1/2 in `tenant-a`, yet cannot read doc 3 in `tenant-b`.
- Right owner without CSRF on PUT still receives 403.
- Owner with permission and CSRF can edit content; Alice cannot edit Bob's.
- Manager does not automatically gain edit rights on other owners' documents.
- For nonexistent IDs, the demo policy denies without leaking existence through unauthorized GETs.

<code>@DirtiesContext</code> isolates the in-memory `DocumentStore` across tests. The suite goes through real HTTP filters and method security rather than mocking a principal and calling the controller directly. In production, add unit tests of the policy covering many role/tenant combinations, repository tests, and database integration tests.

**Note:** the example follows Java/Spring Security 6.x APIs and was statically reviewed for logic and syntax, not executed with Maven here. Run on JDK 17+ to verify actual dependencies and runtime behavior.

## 8. Trying via HTTP and Explaining Status Codes

Start up:

~~~bash
mvn test
mvn spring-boot:run
~~~

Example GET commands:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/documents/1
curl -i -u alice:alice-pass-123 http://localhost:8080/documents/1
curl -i -u alice:alice-pass-123 http://localhost:8080/documents/2
curl -i -u mia:mia-pass-123 http://localhost:8080/documents/1
curl -i -u mia:mia-pass-123 http://localhost:8080/documents/3
~~~

**Expected** results: `/health` = 200; anonymous GET document = 401; Alice GET doc1 = 200; Alice GET doc2 = 403; Mia GET doc1 = 200; Mia GET doc3 = 403. Success bodies are JSON from <code>DocumentView</code> containing only <code>id</code>, <code>title</code>, and <code>content</code>.

For PUT in the demo, Spring Security requires a CSRF token. Running a curl PUT with only HTTP Basic and a JSON body without a CSRF token is expected to return 403 by configuration — **not** proof the owner lacks permission. Use MockMvc <code>.with(csrf())</code> or build a client that fetches and submits the CSRF token properly. Never disable CSRF app-wide as a "fix" without a threat model.

### 401, 403, and 404

- **401:** not properly authenticated (HTTP Basic entry point in the demo).
- **403:** authenticated, yet policy denies access or the request lacks a CSRF token.
- **404:** resource does not exist in APIs that intentionally allow disclosing that fact.

The demo chooses **fail closed with 403** when an ID is absent in the policy. Real products may return 404 for both "missing" and "not allowed" to reduce resource enumeration; the choice must be consistent without accidentally leaking existence via timing or response differences. Never let repository exceptions turn forbidden cases into 500.

## 9. Why Is Controller-Level @PreAuthorize Not Enough?

Putting <code>@PreAuthorize</code> on a Controller still works when Spring method security is active. However, if only the REST endpoint is protected while the business service is unprotected, a Kafka consumer, GraphQL resolver, scheduled job, internal RPC, or second controller can invoke the service and skip the check.

Good pattern:
- HTTP layer blocks anonymous callers and out-of-scope routes.
- Service/use case enforces per-action/resource authorization.
- Policy is a reusable unit across entry points.
- Repository/transaction enforces data scope on queries and updates.

Not every repository needs <code>@PreAuthorize</code>. The repository can remain a pure data layer while the service ensures no public data-access path bypasses policy. In larger organizations, enforce the architecture via code review or architecture tests so Controllers or API adapters never inject repositories directly to skip services.

## 10. Watch Out for Self-Invocation and Spring Proxies

Spring method security typically runs via a Spring AOP proxy. Consider:

~~~java
@Service
class BadDocumentService {
    public void bulkUpdate() {
        this.updateOne(); // Internal call on the same instance.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void updateOne() {
        // Method has annotation, yet this. call can bypass the proxy!
    }
}
~~~

This is an illustrative snippet, **not a runnable standalone class**. If you only test <code>proxy.updateOne()</code>, you can miss that <code>this.updateOne()</code> skips the interceptor. Architectural fix: move the protected method to a separate Spring bean and invoke it via the proxy, or enforce an explicit policy check at the use-case layer before any internal flow.

Other cases to review: non-Spring-managed beans, non-public methods, proxy/final-class settings, manual instantiation via <code>new</code>, or direct repository calls. Never treat a controller annotation as proof that every path to the data is protected.

## 11. TOCTOU: Policy Checks Before SELECT/UPDATE Are Not Always Enough

The demo uses an in-memory `DocumentStore` where owner/tenant never change during content updates. In a real database, owner, tenant, document state, or membership can change **between check time and update time**:

~~~text
t1: Policy reads doc 42: owner = alice
t2: Alice is allowed to edit doc 42
t3: Another transaction transfers doc 42's owner/tenant
t4: Unscoped UPDATE on doc 42 -> wrong edit
~~~

This is a *time-of-check to time-of-use* (TOCTOU) bug. Protections:
1. Read and mutate inside a transaction with appropriate isolation/locking, revalidating policy on write.
2. Optimistic locking with <code>@Version</code> when resources mutate.
3. A conditional UPDATE enforcing owner/tenant/status from server-sourced identity/tenant, checking the affected row count.
4. For complex policies, combine the policy layer with persistence constraints; never let DB queries be broader than the approved scope.

Illustrative SQL, not a runnable Java file:

~~~sql
UPDATE documents
SET content = :newContent
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND owner_username = :authenticatedUsername
  AND status = 'EDITABLE';
~~~

If affected row count = 0, do not report "updated successfully". Reject or handle the conflict per API contract. Owner/tenant predicates on SELECT and UPDATE must be computed on the server and bound to real data. Never trust a tenant ID supplied in a JSON body.

Note: the SQL above fits an owner-edit policy; if policy allows managers to edit under other conditions, design the UPDATE accordingly rather than copying an incomplete `WHERE` clause in place of domain policy.

## 12. Preventing IDOR/BOLA: Being Logged In Is Not Enough for Every ID

A <code>GET /documents/{id}</code> endpoint is vulnerable to **Insecure Direct Object Reference / Broken Object Level Authorization** when it checks only that the caller is logged in:

~~~java
// INSUFFICIENT: authenticated, yet no object authorization.
.requestMatchers("/documents/**").authenticated()
~~~

This rule is a sound coarse barrier in the demo, yet it **does not** answer whether the user has access to a specific ID. You need a policy comparing identity, tenant, owner, role, and resource state.

You cannot rely on hard-to-guess IDs, random UUIDs, or hiding an "Edit" button on the frontend in place of authorization. Attackers can call the API directly, swap IDs in the path, or use another lower-privileged account.

Cases to test:
- Owner vs. non-owner in the same tenant.
- User in another tenant with the same role.
- Manager with read access but no edit access.
- Nonexistent resources.
- Locked user, changed membership, or revoked role.
- Requests attempting to inject self-declared owner/tenant to elevate access.
- Secondary routes such as export, attachments, history, comments, and bulk actions.

## 13. Lists, Search, and Pagination Need Query-Level Policy

<code>canRead(document)</code> works well for a single document, yet a listing endpoint over thousands of documents must not:
1. SELECT all documents across all tenants.
2. Load sensitive data into memory.
3. Then filter in Java streams by owner and role.

That approach risks poor performance, data leaks in logs/caches, broken pagination, leaking total counts, and inconsistency. Instead:
- Derive query scope from verified identity and policy.
- Use <code>WHERE tenant_id = ...</code> with appropriate owner/manager predicates.
- Apply sorting, limit/offset, or cursor pagination **after** narrowing scope.
- Compute total counts using the **same scope**.
- For search/export/batch operations, enforce identical logic or use a controlled specification/query builder.

Illustrative query example:

~~~sql
SELECT id, title, content
FROM documents
WHERE tenant_id = :trustedTenant
  AND (
       owner_username = :authenticatedUsername
       OR :hasManagerRole = TRUE
  )
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

This expresses **the demo's specific read policy**. In a real database, never trust a client-supplied <code>:hasManagerRole</code>; derive it server-side from verified `Authentication`. Test pagination and count outputs so they never leak data from another tenant.

## 14. Data Masking and Field-Level Permissions

Permission to read a document does not imply permission to read every field:
- Users may view title/body, yet not internal audit notes.
- Managers may view team records, yet not personal authentication credentials.
- Auditors may view history, yet not edit content.
- Tenant admins do not automatically administer other tenants.

Use explicit response DTOs and field-level policies when required. Never return raw JPA entities hoping Jackson strips sensitive fields automatically. DTOs bound the payload; service policies guard resources/actions; repository queries prevent fetching beyond authorized scope.

## 15. When Policies Evolve or Depend on an External PDP

In real products, access may depend on groups, workspaces, subscriptions, record status, sessions, time, delegation, or approvals. In that case:
- Policies can be split into small named rules while preserving one decision entry point.
- Membership/permission data needs trusted sources, versioning, and proper cache invalidation.
- When using an external policy engine (OPA, Cedar, or an authorization service), design timeouts, availability, decision caching, minimal request context, and **fail-closed** handling for sensitive data.
- Audit logs should capture actor ID, action, appropriate resource ID, policy version, decision, and correlation ID; never log passwords/access tokens or full document contents.
- When a role is revoked, sessions/JWTs may still hold old authorities. Decide permission freshness, shared-source re-checks, or token lifetimes according to risk.
- Policy versions and tests belong to change management; a role update must never accidentally open cross-tenant access.

You do not need a policy server to achieve separation of concerns. A well-tested, centralized <code>DocumentPolicy</code> Spring bean is already a major improvement over repeated `if/else` blocks in Controllers.

## 16. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix direction |
| --- | --- | --- |
| Checking ownership in every Controller | Rules scatter and drift | Policy bean and enforced service |
| Using only <code>authenticated()</code> for `/documents/{id}` | IDOR/BOLA | Object-level policy |
| Using only <code>hasRole("MANAGER")</code> | Manager sees other tenants' data | Combine with tenant membership |
| Treating request `tenantId` as trusted | Cross-tenant access | Get tenant from server identity/membership |
| Controller injects repository directly | Bypasses service policy | Fix architecture and add tests |
| Forgetting <code>@EnableMethodSecurity</code> | `@PreAuthorize` never runs | Enable method security and test end-to-end |
| Calling <code>this.protectedMethod()</code> | Can bypass proxy | Call through Spring proxy or check policy explicitly |
| Policy grants when resource is missing | Accidental exposure/permit | Deny by default |
| Querying whole DB then filtering in Java | Data exposure, wrong counts/pagination | Enforce scope in DB queries |
| Checking privilege then running unconditional UPDATE | TOCTOU, race conditions | Transaction/lock/conditional UPDATE |
| Letting managers edit just because they can read | Over-permission | Separate READ and EDIT actions |
| Treating DTOs as authorization | Callers still access unauthorized records | Enforce at the service layer |
| Treating hidden URLs/random UUIDs as security | Endpoints still guessed or called directly | Server-side authorization |
| Testing only owner happy path | Misses cross-tenant and bypass flaws | Negative matrix tests |
| Policy only on web, skipping batch/messaging | Alternative entry points bypass checks | Enforce at use cases and services |
| Caching authorities for too long | Revoked privileges persist | Freshness/version/revalidation policy |

## 17. Pre-Implementation Design Checklist

1. Write an actor/action/resource/context matrix before coding.
2. Ensure principals, roles, tenants, and resource attributes come from **trusted sources**.
3. Design a <code>Policy</code> returning explicit decisions, separate from HTTP/serialization/CRUD.
4. Use <code>SecurityFilterChain</code> for authentication and coarse-grained HTTP boundaries.
5. Enforce at the service/use-case layer using <code>@PreAuthorize</code> or explicit authorization checks.
6. Audit bypass paths: self-invocation, non-Spring objects, controllers injecting stores directly, jobs, listeners, GraphQL, batch.
7. Ensure read/update queries are scoped by tenant/owner; handle transactions, optimistic versions, and races as needed.
8. Separate read, edit, delete, export, approve, and admin actions into distinct policy actions.
9. Use DTOs to restrict outbound fields; never expose internal entities arbitrarily.
10. Test owner, same-tenant non-owner, manager, cross-tenant, anonymous, missing resource, CSRF, and bulk/listing endpoints.
11. Test 401/403 and 404 semantics consistently; never leak existence of unauthorized resources.
12. Audit decisions and policy changes without logging secrets; evaluate freshness of caches/claims/tokens.
13. Review policies whenever adding endpoints or changing role/tenant models; default-deny unclassified surface area.

## 18. Self-Check Questions

**Q1:** Why should the Controller not be the only place checking ownership?  
**Answer:** Because business use cases can be invoked from multiple entry points bypassing that controller. Service enforcement paired with a dedicated policy provides centralized control and easier testing.

**Q2:** Is the HTTP rule <code>authenticated()</code> enough to protect `GET /documents/2`?  
**Answer:** No. It only proves the caller is authenticated; you must still verify access to document ID 2, tenant, and the READ action.

**Q3:** May a manager in `tenant-a` read documents in `tenant-b`?  
**Answer:** Not under the demo policy. The MANAGER role applies only within the server-verified tenant boundary.

**Q4:** Does <code>@PreAuthorize</code> on `DocumentService` automatically protect internal calls to <code>this.replaceContent()</code>?  
**Answer:** Do not rely on that. Proxy-based method security normally does not intercept self-invocation; split beans or perform explicit checks.

**Q5:** Why is a policy check before UPDATE not always safe when ownership can change?  
**Answer:** Because of TOCTOU: owner/tenant/status can change between the check and the write. Use transactions/locks, optimistic versioning, or conditional SQL so the update still satisfies conditions at write time.

**Q6:** For listing APIs, should you SELECT all documents and filter privileges in Java?  
**Answer:** No. Apply data scoping in the query first, then compute pagination and counts to reduce data-leak risks and wrong totals.

**Q7:** If a DTO already omits `tenantId`, can service authorization be skipped?  
**Answer:** No. DTOs hide fields, yet do not prevent a user from retrieving the contents of another document they are not permitted to read.

**Key takeaway:** **Controllers receive requests; Policies decide access; Services enforce policies; Repositories protect data scope and consistency; DTOs control outbound payloads.** This separation applies authorization uniformly, supports independent testing, and scales safely across resources, tenants, and entry points.
