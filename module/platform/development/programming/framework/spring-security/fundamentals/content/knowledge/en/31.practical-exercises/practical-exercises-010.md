# Mapping Product Requirements to Security Controls, Tests, and Operations

> **Capstone practical exercise — Spring Security Fundamentals (Servlet / Spring MVC).** The goal is turning each product requirement into an **enforceable security rule**, one or more **proving tests**, and a **monitoring/operations mechanism**. The exercise uses Java 17+, Spring Boot 3.3.0, and Spring Security 6.x for illustration. These are pinned versions for study examples; real products must choose supported releases and apply patches.

## 1. Why Do We Need a Security Traceability Map?

"Only authorized employees may view documents" is an intention. It cannot be treated as a complete requirement until you answer: who counts as an employee, where permissions come from, which organization owns the document, at which layer the permission is checked, which test proves cross-access is blocked, and who gets alerted when the policy breaks.

A security map connects the layers:

```text
Product need / user story
      ↓ clarify
Actor + Asset + Action + Context + Expected Decision
      ↓ analyze
Threat / trust boundary / abuse case
      ↓ choose
Authentication + Authorization + HTTP defenses + data invariants
      ↓ implement
Filter chain → Controller → Service policy → Repository / IdP
      ↓ test
Allow tests + Deny tests + edge cases + concurrency cases
      ↓ operate
Audit + security events + metrics + alerts + runbook + owner
      ↓ maintain
Version upgrades + revocation + incident handling + release evidence
```

When each team looks only at its own slice, systems end up with backend assuming frontend checks permissions, frontend assuming tokens suffice, and operations having no idea which policy broke after release. A map gives every relationship a name, a test, and an accountable owner.

**Principle:** One requirement may demand multiple controls; one control may serve multiple requirements. For example, `SecurityFilterChain` can guard every API, yet viewing a record by `ownerId` and `tenantId` still needs an application-specific policy.

## 2. Choosing a Concrete Enough Product Problem

Suppose we have a multi-organization **Enterprise Document Vault**. Each document has `id`, `tenantId` (organization), `owner`, and `state` (`DRAFT`/`APPROVED`). Authenticated users may carry authority `ROLE_USER` or `ROLE_APPROVER`. Memberships between users and organizations are managed by the backend.

Assumed rules:

- Anonymous callers may access only the public health endpoint.
- Users may view documents they own while still belonging to the document's tenant.
- Approvers may view and approve documents within **their own tenant**, never crossing organizational boundaries.
- Approval applies only to documents currently in the `DRAFT` state.
- All other APIs are denied by default.
- State-changing requests carry CSRF protection suited to the client type.
- Approval events and denials capture enough data for investigation without logging credentials or document contents.
- Every permission change and Spring Security upgrade re-runs the regression test suite.

This is a **hypothetical product policy**, not something Spring Security infers on its own. The example below stores users and documents in memory so it runs easily; real systems require persistent identity, membership, and data stores.

## 3. Writing Requirements as Testable Contracts

A security requirement should specify `ID`, actor, resource, action, trusted inputs, conditions, default decision, HTTP behavior, log/audit, tests, and owner.

| ID | Product requirement | Allow condition | Result when unmet |
| --- | --- | --- | --- |
| SEC-01 | `GET /public/health` is public | Any caller; returns only `ok` | N/A; never leak sensitive data. |
| SEC-02 | Document APIs require authentication | Valid credentials | With HTTP Basic: 401 if missing/invalid credentials. |
| SEC-03 | Document owner may read their own record | Authenticated; `owner=user`; same-tenant membership | 403; cannot read other documents. |
| SEC-04 | Approver may read documents in their tenant | `ROLE_APPROVER` and same-tenant membership | 403 if cross-tenant or lacking role. |
| SEC-05 | Approver may approve a draft | HTTP POST; `ROLE_APPROVER`; same tenant; `state=DRAFT` | 403 if unauthorized; invalid state must follow defined API behavior. |
| SEC-06 | Unpublished APIs are blocked by default | Only declared rules execute | 403 for authenticated principals. |
| SEC-07 | POST must satisfy the CSRF policy | Valid CSRF token in the demo model | 403 if token is missing or invalid. |
| SEC-08 | Sensitive operations are investigable | Event holds actor, action, resource, time, result, request ID | Alert when audit pipeline fails or behaves abnormally. |
| SEC-09 | Releases must not break policies | CI + staging/canary prove allow/deny cases | Block release if tests/security gates fail. |

**HTTP status is part of the contract.** Under HTTP Basic, unauthenticated is typically 401; authenticated without permission is 403. Form login may redirect with 302. A nonexistent resource may return 404, or intentionally mask existence uniformly with 403/404. State conflicts for authorized callers may return 409. Never assume every 403 comes from roles: CSRF can return 403 too.

### Example: turning a vague requirement into crisp conditions

Initial request: "Managers can view related contracts."

Clarify whether "related" means `createdBy`, `department`, `owner`, `tenant`, `delegation`, or `assignedReviewer`. Example of a clarified rule:

```text
ALLOW READ(document) WHEN
    principal authenticated
    AND membership(principal, document.tenantId) active
    AND (document.owner == principal.name
         OR principal has APPROVER authority for that tenant)
ELSE DENY
```

In real code, `APPROVER` should be organization-scoped or paired with server-side membership. Never trust a browser-supplied `tenantId`, `owner`, or `role` as proof of permission.

## 4. Identifying Assets, Actors, and Trust Boundaries

Before writing `@PreAuthorize`, document:

| Item | Example | Consequence of misplaced trust |
| --- | --- | --- |
| Actors | Alice, Bob, Reviewer, anonymous, machine client | Spoofed user or client using an invalid identity. |
| Assets | Document contents, tenant membership, approval state, audit log | Data leak or unauthorized business action. |
| Network boundary | Browser → gateway → Spring MVC | Bypassing UI and calling the API directly. |
| Identity boundary | Spring Security / IdP → `Authentication` | Trusting unverified roles in request body/headers. |
| Data boundary | Service → database/repository | IDOR/BOLA by swapping IDs in URLs; queries missing tenant filters. |
| Operations boundary | App → log collector / monitoring / audit storage | Logs leaking tokens, or audit events lost/tampered. |

**Threat scenarios worth testing:** anonymous opens protected route; user swaps ID to another user's document; approver crosses tenants; approval POST lacks CSRF; document already moved to `APPROVED` gets approved again; revoked member keeps access via cache/token; new route accidentally lacks a rule; another module calls the service bypassing HTTP filters.

Testing that the UI hides a button does not prove the backend is protected. A malicious client can skip the frontend completely and modify paths, queries, HTTP methods, or send command-line requests.

## 5. Separating Framework Mechanisms from Application Rules

| Layer | Built-in components or extension points | Must be designed per product |
| --- | --- | --- |
| Authentication | `AuthenticationManager`, providers, `UserDetailsService`, `PasswordEncoder`, OAuth2 Resource Server/OIDC client | Account store, identity source, account lifecycle, issuer/audience, MFA policy. |
| HTTP authorization | `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `authenticated`, `hasRole` | Which endpoints are public, which methods need which roles, fallback policy. |
| Object authorization | `@EnableMethodSecurity`, `@PreAuthorize`, `AuthorizationManager` | Owner, tenant, delegation, state transitions, field-level access. |
| HTTP protection | CSRF, security headers, session management, CORS integration | Cookie vs. bearer clients, trusted origins, logout, revocation. |
| Data consistency | Spring transactions, JPA optimistic locking, DB constraints | Prevent mutating documents after revocation; idempotency; audit outbox. |
| Operations | Security events, logging/metrics integration | Event schema, retention, SIEM, alert thresholds, on-call, and runbooks. |

Not every component must be built from scratch: using an IdP, gateway, or library can be safer and more economical. Still, **business policies and integrated verification** remain the system's own responsibility.

### Two matcher layers commonly confused

`http.securityMatcher("/api/**")` defines whether a `SecurityFilterChain` accepts a request at all. `authorizeHttpRequests(auth -> auth.requestMatchers("/api/**")...)` defines rules **inside the chain**. With multiple chains, only the first matching chain runs; requests matching no chain bypass security filters, so explicit fallback coverage is essential.

## 6. Map: Requirement → Mechanism → Test → Evidence

| ID | Enforcement point | Positive test | Negative test | Evidence and owner |
| --- | --- | --- | --- | --- |
| SEC-01 | `permitAll()` for `/public/**` | Anonymous `/public/health` 200 | Public response contains no private data | Synthetic health check, application owner. |
| SEC-02 | Demo HTTP Basic + `authenticated()` | Alice GET document 200 | Anonymous 401; bad credentials 401 | 401 rate, Identity/SRE. |
| SEC-03 | `DocumentPolicy.canRead` in service | Alice reads document 101 | Alice reads 103 same tenant other owner 403; Bob reads 101 cross-tenant 403 | Denied events, domain owner. |
| SEC-04 | Authority + tenant membership | Reviewer reads 101 same tenant | Reviewer reads 102 other tenant 403 | Role grant/revoke audit, IAM owner. |
| SEC-05 | POST matcher + `canApprove` + state update | Reviewer approves 101 → 204 | USER 403; cross-tenant 403; already-approved rejected | Approval audit + reconciliation, domain owner. |
| SEC-06 | `anyRequest().denyAll()` | Declared routes work | `/api/unlisted` 403 | Authorization deny rate, backend owner. |
| SEC-07 | CSRF protection on POST | Valid POST + `csrf()` proceeds | POST missing CSRF 403 | CSRF failure rate, client/security owner. |
| SEC-08 | Product-built audit/outbox/central logging | Audit event after transaction commit | Missing event, duplicate event, secret-in-log tests | Audit pipeline health, Security Ops. |
| SEC-09 | CI/staging/canary and release gates | Passing test evidence | Block merge/deploy on failure | Build evidence, Release/SRE. |

This table must be **maintained like a contract**. Whenever a policy changes, locate the affected tests and alerts. For SEC-08/SEC-09, the Java example below **does not yet implement an audit pipeline or deployment pipeline**; those must be built per production architecture rather than marked passing just because MockMvc exists.

## 7. A Runnable Spring Security App Matching the Requirements

A small example using Java 17, Maven, Spring Boot 3.3.0, and Spring Security 6.x. Users, tenants, and documents stay in memory so learners can run it locally. Authentication uses HTTP Basic so 401/403 codes are easy to observe—not a recommendation to ship demo passwords to production.

### 7.1. Directory layout

```text
security-map-demo/
├── pom.xml
└── src/
    ├── main/java/example/securitymap/
    │   ├── SecurityMapApplication.java
    │   ├── SecurityConfig.java
    │   ├── ActorDirectory.java
    │   ├── DocumentStore.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/example/securitymap/
        └── SecurityMapTest.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>security-map-demo</artifactId>
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

`src/main/java/example/securitymap/SecurityMapApplication.java`:

```java
package example.securitymap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityMapApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityMapApplication.class, args);
    }
}
```

### 7.2. SecurityFilterChain — route authentication and HTTP authorization

`src/main/java/example/securitymap/SecurityConfig.java`:

```java
package example.securitymap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasRole("APPROVER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER").build(),
            User.withUsername("reviewer")
                .password(encoder.encode("reviewer-pass"))
                .roles("APPROVER").build()
        );
    }
}
```

`@EnableMethodSecurity` activates service-layer enforcement. The GET rule ensures authentication, yet does not authorize reading arbitrary IDs. The POST rule requires `ROLE_APPROVER`; with `hasRole("APPROVER")`, Spring Security prepends the `ROLE_` prefix by default.

`anyRequest().denyAll()` keeps unlisted URLs denied. If additional health/readiness endpoints exist, explicitly decide whether they belong in public or protected rules—never open `/actuator/**` wholesale out of habit.

The example deliberately **does not disable CSRF**: Spring Security protects state-changing HTTP methods like POST by default. Authorization POST tests attach `.with(csrf())`, while a separate test proves missing CSRF gets blocked.

### 7.3. Membership comes only from a backend-trusted source

`src/main/java/example/securitymap/ActorDirectory.java`:

```java
package example.securitymap;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class ActorDirectory {
    private final Map<String, String> tenants = Map.of(
        "alice", "org-a",
        "bob", "org-b",
        "reviewer", "org-a"
    );

    public boolean isMember(String username, String tenantId) {
        return tenantId != null
            && tenantId.equals(tenants.get(username));
    }
}
```

This mocks membership data so learners understand the `sameTenant` check. Real systems store it in a DB/IdP with controlled grant, revocation, expiration, and cache invalidation; **never** accept a frontend-supplied `tenantId` as authorization proof.

### 7.4. Documents and state transitions

`src/main/java/example/securitymap/DocumentStore.java`:

```java
package example.securitymap;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentStore {

    public record Document(long id, String tenantId,
                           String owner, String state) {}

    private final Map<Long, Document> records = new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    void reset() {
        records.clear();
        records.put(101L, new Document(101L, "org-a", "alice", "DRAFT"));
        records.put(102L, new Document(102L, "org-b", "bob", "DRAFT"));
        records.put(103L, new Document(103L, "org-a", "carol", "DRAFT"));
    }

    public Optional<Document> find(Long id) {
        return Optional.ofNullable(records.get(id));
    }

    public synchronized void approve(Long id) {
        Document doc = records.get(id);
        if (doc == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        if (!"DRAFT".equals(doc.state())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT, "Already approved");
        }
        records.put(id, new Document(
            doc.id(), doc.tenantId(), doc.owner(), "APPROVED"));
    }
}
```

This synchronization applies only within **a single JVM instance**. Across multiple instances, use database transactions, versioning/optimistic locking, or conditional DB updates, and emit audit records tied to real commits. Never use `ConcurrentHashMap` as a production document store.

### 7.5. Policy checking owner, role, tenant, and state

`src/main/java/example/securitymap/DocumentPolicy.java`:

```java
package example.securitymap;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentStore documents;
    private final ActorDirectory directory;

    public DocumentPolicy(DocumentStore documents, ActorDirectory directory) {
        this.documents = documents;
        this.directory = directory;
    }

    public boolean canRead(Authentication authentication, Long id) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return documents.find(id)
            .filter(doc -> directory.isMember(
                authentication.getName(), doc.tenantId()))
            .filter(doc -> doc.owner().equals(authentication.getName())
                || has(authentication, "ROLE_APPROVER"))
            .isPresent();
    }

    public boolean canApprove(Authentication authentication, Long id) {
        if (authentication == null || !authentication.isAuthenticated()
                || !has(authentication, "ROLE_APPROVER")) {
            return false;
        }

        return documents.find(id)
            .filter(doc -> directory.isMember(
                authentication.getName(), doc.tenantId()))
            .filter(doc -> "DRAFT".equals(doc.state()))
            .isPresent();
    }

    private boolean has(Authentication authentication, String authority) {
        return authentication.getAuthorities().stream()
            .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
```

Alice can read 101 as the owner in org-a, yet **cannot** read Carol's 103 even in the same tenant. Bob in org-b cannot read 101. Reviewer is an org-a approver so they can read and approve 101/103, yet **cannot** do so for document 102 in org-b.

For nonexistent IDs, the policy returns false; authenticated callers receive 403 in this example. That avoids leaking document existence through differences between forbidden and missing IDs, though production APIs must consciously decide whether to standardize on 403 or 404.

### 7.6. Service enforcing method security

`src/main/java/example/securitymap/DocumentService.java`:

```java
package example.securitymap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public DocumentStore.Document read(Long id) {
        return store.find(id).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("@documentPolicy.canApprove(authentication, #p0)")
    public void approve(Long id) {
        store.approve(id);
    }
}
```

`#p0` refers to the first parameter, avoiding reliance on compiler parameter-name retention. `@PreAuthorize` runs when another component calls through the Spring proxy, such as the Controller below. If a method inside the same bean calls another annotated method via `this`, **self-invocation** can bypass the method interceptor. Guard every entry point (HTTP, scheduled jobs, message consumers, batch jobs) appropriately rather than relying solely on controller rules.

### 7.7. Controller

`src/main/java/example/securitymap/DocumentController.java`:

```java
package example.securitymap;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/documents/{id}")
    public DocumentStore.Document read(@PathVariable Long id) {
        return service.read(id);
    }

    @PostMapping("/api/documents/{id}/approve")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void approve(@PathVariable Long id) {
        service.approve(id);
    }
}
```

The demo app returns the Java `record` directly since its scope is illustrative; real products need DTOs, sensitive-field classification, and field-level authorization. Never return password hashes, access tokens, or full account entities to clients.

## 8. MockMvc: Two-Way Testing for Every Permission

Create `src/test/java/example/securitymap/SecurityMapTest.java`:

```java
package example.securitymap;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityMapTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentStore documents;

    @BeforeEach
    void resetState() {
        documents.reset();
    }

    @Test
    void publicHealth_SEC01() throws Exception {
        mvc.perform(get("/public/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void anonymousCannotRead_SEC02() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceOwnDocument_SEC03() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceDifferentOwnerSameTenant_SEC03() throws Exception {
        mvc.perform(get("/api/documents/103")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCannotCrossTenant_SEC03() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reviewerCanReadOwnTenant_SEC04() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("reviewer", "reviewer-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void reviewerCannotReadAnotherTenant_SEC04() throws Exception {
        mvc.perform(get("/api/documents/102")
                .with(httpBasic("reviewer", "reviewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotApprove_SEC05() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void reviewerCannotApproveOtherTenant_SEC05() throws Exception {
        mvc.perform(post("/api/documents/102/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void reviewerApprovesDraft_SEC05() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("APPROVED"));
    }

    @Test
    void repeatedApprovalIsRejected_SEC05() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRouteDenied_SEC06() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfRequiredForPost_SEC07() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invisibleIdDoesNotLeakDocument_SEC03() throws Exception {
        mvc.perform(get("/api/documents/999")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }
}
```

These are **14 test methods** covering SEC-01..SEC-07; all are expected to pass with the presented source. This is not a report of a Maven execution performed while authoring this content. Tests embed requirement IDs in their names to make test output and traceability direct.

**Key point on CSRF:** When testing HTTP POST permissions, tests must supply a valid `.with(csrf())`. Omitting the token causes a 403 from CSRF **before** the policy ever runs, turning a supposed role/tenant test into one that proves nothing about roles or tenants.

The test suite verifies: allow owner, deny other owner, deny cross-tenant, allow same-tenant approver, deny cross-tenant approver, deny lower role, deny missing token, deny undeclared URL, and reject mutation after approval.

### 8.1. Running and observing

In the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
java -version
mvn test
mvn spring-boot:run
```

In another terminal, while the app runs on default port 8080:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/health
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/documents/101
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/api/documents/101
curl -s -o /dev/null -w '%{http_code}\n' -u bob:bob-pass http://localhost:8080/api/documents/101
curl -s -o /dev/null -w '%{http_code}\n' -u reviewer:reviewer-pass http://localhost:8080/api/documents/101
```

Expected stdout for the **five `curl` commands**:

```text
200
401
200
403
200
```

On Windows PowerShell, use `curl.exe` and `NUL` instead of `/dev/null`. The GET examples here need no CSRF token. For POST, use MockMvc tests or a client implementing proper CSRF token retrieval/submission—never send HTTP Basic without a token and assume 403 came from roles.

## 9. Testing the Map Across Layers Outside HTTP

MockMvc proves Spring filters and service policies cooperate inside one application. Real products also need additional tests:

| Test layer | Objective | Example |
| --- | --- | --- |
| Policy unit | `owner/tenant/role/state` rules independent of HTTP | 2 tenants × 3 roles × 2 states matrix; default deny. |
| DB integration | Tenant-scoped queries, locks, transactions, rollback | Reviewer transitions state while a concurrent request arrives; only one approval succeeds. |
| Authentication integration | Real IdP/JWT/session/provider | Expired token, wrong issuer/audience, disabled user, revoked account. |
| API contract | Status/body/headers/redirects match client expectations | 200/401/403/404/409 per contract, `WWW-Authenticate`, JSON errors. |
| Abuse/security | Bypass attempts via URL/method/ID/headers | BOLA, IDOR, field-level access, mass assignment, tenant spoofing. |
| Resilience | When DB, IdP, cache, or audit pipeline fails | System fails closed, raises alerts, never opens demo bypasses. |
| E2E | UI, backend, IdP, gateway all honor policy | Login → access permitted data → approve → audit event. |

For instance, `@PreAuthorize` executes through a Spring proxy, so calling `DocumentPolicy.canRead()` directly in a unit test does not prove the method interceptor is wired up. Testing real controllers/services via MockMvc catches those configuration errors far better.

With multi-tenant data, always test **cross-ID access**; an HTTP `authenticated()` rule will not stop BOLA if services/repositories omit tenant checks. Combine service policies with tenant-scoped queries or row-level controls per architecture.

## 10. Test Map with Both "Allow" and "Deny" Evidence

A strong suite never tests only "valid requests return 200." For every permission, place a negative test right beside the positive test so you detect when a policy opens too wide:

```gherkin
Feature: Tenant-safe document approval

  Scenario: Allowed approval in the same tenant
    Given reviewer has APPROVER authority in org-a
    And document 101 belongs to org-a and is DRAFT
    When reviewer sends POST /api/documents/101/approve with CSRF
    Then the API responds 204
    And document 101 becomes APPROVED

  Scenario: Cross-tenant approval is denied
    Given reviewer has APPROVER authority in org-a
    And document 102 belongs to org-b and is DRAFT
    When reviewer sends POST /api/documents/102/approve with CSRF
    Then the API responds 403
    And document 102 remains DRAFT
```

This is a Gherkin specification for discussing acceptance criteria, not runnable Java code on its own. If using a BDD framework, bind steps to HTTP/test fixtures and assert actual stored state.

Every test must verify **observable behavior**, rather than calling the same implementation `boolean` helper again. For approvals, inspect the resulting state after the request; for denials, assert state **remained unchanged** against the real database/repository in an integration suite.

## 11. Operations: Audit Events and Security Logging

There are three distinct signal categories:

1. **Application logs:** stack traces, dependency timeouts, request latencies; used to troubleshoot technical faults.
2. **Security events:** failed logins, access denials, permission changes, suspected bypasses or CSRF errors; used for security detection and analysis.
3. **Business audit trail:** who approved which document, when, and the final committed outcome after transaction commit; used for investigations, audits, and accountability.

### Defining a minimal event schema

```json
{
  "timestamp": "2026-01-15T09:45:10Z",
  "eventType": "DOCUMENT_APPROVAL",
  "actorId": "user-42",
  "tenantId": "org-a",
  "action": "APPROVE",
  "resourceType": "DOCUMENT",
  "resourceRef": "101",
  "decision": "ALLOW",
  "result": "COMMITTED",
  "requestId": "trace-8f23",
  "policyVersion": "document-policy-v1"
}
```

This is an **illustrative event**, not automatically emitted by the demo code. Never log passwords, `Authorization` headers, access tokens, cookies, document contents, or unnecessary personal data. Attach UTC/offset timestamps and request/trace IDs to correlate across layers.

An event recording `result=COMMITTED` is accurate only if the mutation actually committed. Use a **transactional outbox** to write data + event within the same transaction, then publish to an event processor whose consumers are idempotent. Calling `logger.info` before DB commit **does not** guarantee the audit trail matches final persisted state. Operations must enforce retention, access control, tamper protection, secure transport, and evidence retrieval.

### Metrics and detection

| Metric/event | What might be happening | Further analysis needed |
| --- | --- | --- |
| Spike in 401s | Bad credentials, user store/IdP outage, expired client sessions/tokens | Group by authentication mechanism, endpoint, and release. |
| Spike in 403 authorization | Wrong role/membership, matcher change, new policy | Classify denial reasons; separate from CSRF. |
| Spike in 403 CSRF | SPA/client stopped sending token, cookie/session mismatch | Check HTTP method, CSRF repository, recent client changes. |
| Unusual cross-tenant denials | Client bug, ID enumeration, attack, or stale membership | Inspect via request ID and controlled audit logs. |
| Rising approval conflicts | Races or user retries | Check transactions, optimistic locking, and idempotency. |
| Audit pipeline lag/drops | Evidence delayed or lost | Outbox backlog, retries/dead-letter queues, and alerts. |
| Privilege changes | Roles granted or revoked | Verify approver, reason, effective time, session/token invalidation. |

Avoid arbitrary thresholds like "403 > 10 per minute means an attack" without a baseline; multi-client/multi-tenant systems have varied traffic patterns. Never put usernames or document IDs into high-cardinality metric labels; use route templates, outcome/reason codes, and safe groupings.

## 12. Sample Runbook: 403 Spike After Deployment

1. Identify the app version and deploy timestamp, comparing against baseline 401/403/CSRF rates.
2. Separate 403s caused by CSRF, roles, tenants, policy state, and other errors. Never lump them all together as "bad login."
3. Look up security events by `requestId`; inspect runtime authenticated principal and authorities—never trust raw client data.
4. Verify owner/tenant membership, document state, cache invalidation, revocations, and data sync lag.
5. Re-run synthetic/canary tests for both allow and deny cases; diff matcher configs between old and new versions.
6. If a bypass or data leak is suspected, trigger incident response, preserve logs and audit evidence, and narrow access scopes.
7. If caused by a bad migration, roll back or fix the policy through an approved review—**never** add `permitAll()` just to drive down 403 counts.
8. Add regression tests and update the requirement map so similar errors are caught before the next deploy.

**Fail closed:** When trusted data to determine tenant/owner is missing, never grant access by default. However, a dependency outage can return an appropriate 5xx rather than pretending to be 403. API contracts, retries, availability, and incident responses must be designed explicitly.

## 13. Upgrading Spring Security Without Losing Policy Semantics

The requirement "Bob cannot view Alice's document" is a business invariant. How Spring Security configures it evolves across versions:

- Spring Security 5.x used `WebSecurityConfigurerAdapter` and older `antMatchers`/`mvcMatchers`.
- Spring Security 6.x uses `SecurityFilterChain` beans and `authorizeHttpRequests`/Lambda DSL. The code in this exercise targets this line.
- When preparing for Spring Security 7, check mandatory Lambda DSL, `PathPatternRequestMatcher`, and matcher/extension API changes rather than merely renaming methods.
- If an app mixes Servlet and WebFlux across modules, pick `SecurityFilterChain` vs. `SecurityWebFilterChain` accordingly.

Upgrade checklist: pin exact dependency → read migration guide → identify affected controls → run allow/deny cases → compare CSRF/session/redirect/status behavior → test matchers with path encoding, servlet paths, trailing slashes, and HTTP methods → canary deploy → monitor audit and 401/403 metrics → update evidence.

If migrating from `web.ignoring()` to `permitAll()`, know the difference: `ignoring` bypasses the Spring Security filter chain, whereas `permitAll` keeps filters (security headers, etc.) active. Switch only when you understand the exact impact.

## 14. Gaps That Must Be Closed Before Production

The in-memory example intentionally **does not** fulfill all of SEC-08/09. Never copy a demo to production and mark "security complete." Real systems need:

- **Identity source:** IdP/user store, MFA, hashed passwords, account lifecycle, lock/revocation, and secret management.
- **Membership source:** tenant permission tables, audited grant/revoke, cache invalidation, never trusting client headers.
- **Data authorization:** tenant-scoped database queries, owner checks, sensitive-field controls, and export/batch job guards.
- **Consistency:** transactions, optimistic locking, concurrency tests, idempotent approvals, and valid state transitions.
- **Audit:** post-commit records, outbox/retry/reconciliation, retention, and restricted log access.
- **API trust model:** TLS, session/token lifetimes, client-appropriate CSRF/CORS, JWT issuer/audience validation if using Bearer tokens.
- **Operations:** dashboards, alerts, on-call, runbooks, dependency health, rollbacks, and incident response.
- **Evidence:** real CI runs, staging/canary outputs, and risk-appropriate OWASP ASVS checks.

Each item above must become an owned task. For example, `SEC-08 audit pipeline = NOT IMPLEMENTED` is the honest status for the demo project; marking `PASS` without real events and audit tests violates quality governance.

## 15. YAML Template for Tracking a Security Requirement

```yaml
id: SEC-05
title: "Approve DRAFT document within same tenant"
actor: "authenticated ROLE_APPROVER"
resource: "DOCUMENT"
action: "POST /api/documents/{id}/approve"
policy: "sameTenant AND state == DRAFT AND has ROLE_APPROVER"
decision_inputs:
  - "Authentication.principal"
  - "Authentication.authorities"
  - "document.tenantId"
  - "membership.tenantId"
  - "document.state"
controls:
  - "HTTP POST route requires APPROVER"
  - "DocumentPolicy.canApprove in method security"
  - "CSRF protection appropriate to client"
  - "Transactional state change in database"
positive_tests:
  - "same-tenant approver + DRAFT + CSRF => 204"
negative_tests:
  - "USER => 403"
  - "cross-tenant approver => 403"
  - "POST without CSRF => 403"
  - "not DRAFT => reject by API contract"
operational_evidence:
  - "DOCUMENT_APPROVAL audit event after commit"
  - "denied/failed counts and requestId correlation"
  - "approval conflict dashboard and runbook"
owners:
  policy: "document-domain team"
  identity: "identity team"
  operations: "on-call team"
verification:
  code_review: "link to review in actual project"
  ci_tests: "link to actual CI execution"
  audit_test: "link to actual audit verification"
  status: "pending until evidence is attached"
```

The `owners` and `verification` values are **template placeholders**, not real teams or verified test results. Store this map alongside designs or backlogs, review it whenever permissions/tenants/IdPs change, and link it to live test runs.

## 16. Acceptance Checklist

**Requirements:** Every rule has an ID, actor, asset, action, tenant scope, trusted inputs, expected allow/deny, and API status; ambiguities are resolved with the domain owner.

**Implementation:** `SecurityFilterChain` matches the stack/version; specific rules precede fallback; backend enforces resource permissions; CSRF/session/CORS/TLS fit the threat model; never hardcode client-trusted permissions; handle races and self-invocation.

**Testing:** Includes positive and negative tests; covers anonymous, low role, valid role, cross-tenant, different owner, wrong state, CSRF, unlisted URLs, alternate methods, and revoked users/tokens; test data exposes no real info.

**Operations:** Audit events record actor/action/result/time/requestId; never log secrets; metrics/alerts distinguish 401 from CSRF 403 and authorization 403; runbooks and on-call are assigned; rollback and security incident processes exist.

**Version management:** Pin dependencies/JDK; review Spring Security release notes; run regression/canary tests; attach evidence to every requirement before marking done.

## 17. Learning Resources and Reference Standards

- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — HTTP Basic tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Migration guidance: https://docs.spring.io/spring-security/reference/migration/
- OWASP ASVS 5.0 (especially Authorization and Security Logging sections): https://asvs.owasp.org/

**Target outcome:** when a product manager proposes a new permission or requirement, you can prove the complete chain **Requirement → Threat → Control → Code → Positive/Negative Test → Audit/Metric/Alert → Owner/Release Evidence**. "Spring Security is configured" is only one part of the map; business policies and post-release assurance are the rest.
