# Conflicting Multi-Layer Policies and Missing Denied-Scenario Tests

## 1. Objectives

In Spring Security, a single request can encounter **multiple authorization layers**: HTTP filter chains, `@PreAuthorize` on services, tenant/owner domain policies, and data queries. Vulnerabilities happen when one layer grants too broadly, combining logic is wrong (OR instead of AND), or the test suite only verifies **200 OK** without testing **denied** scenarios.

This lesson belongs to the **Mistakes and Vulnerabilities** group of the **Spring Security – authorization** module. After practicing, you will:

- Distinguish **HTTP permits yet method denies** from **HTTP denies even though method might permit**.
- Understand **`requestMatchers`** ordering, **`SecurityFilterChain`** selection, and **`@PreAuthorize`** proxy boundaries.
- Write accurate policies following **authentication AND scope AND role AND tenant AND ownership**.
- Independently test each deny branch: anonymous, missing scope, missing role, wrong owner, wrong tenant, non-existent resource, and undeclared URL.
- Verify the method body **does not execute** when blocked by `@PreAuthorize`; test direct service calls.
- Intentionally introduce faulty mutations to prove your test suite catches accidental privilege relaxation.

The example uses **Java 17+, Spring Boot 3.5.7, Spring Security 6.x, Maven, JUnit Jupiter, and MockMvc**, with complete source code for each file. The demo uses GET only; write requests require separate CSRF and policy tests.

## 2. Order and Responsibility of Each Layer

~~~text
Authenticated/anonymous HTTP request
        |
        v
First matching SecurityFilterChain
        |
        v
authorizeHttpRequests: URL + HTTP method + SCOPE_docs.read
        | DENY -> HTTP 401/403
        v
Controller -> Spring-managed DocumentService proxy
        |
        v
@PreAuthorize: ROLE_READER AND @docPolicy.canRead(...)
        | DENY -> AccessDeniedException (service body not yet run)
        v
DocPolicy: member of tenant + document exists + correct owner
        | false -> denied at @PreAuthorize
        v
DocumentService.read(...) -> Repository -> HTTP 200
~~~

**Do not assume layers automatically combine the way you want:**

1. In **`authorizeHttpRequests`**, request matchers are evaluated **in order**. The first matching rule decides access at the URL layer; an overly broad `permitAll` matcher can shadow a narrower `hasAuthority` rule below it.
2. With **multiple `SecurityFilterChain`s**, Spring selects the **first matching chain** per `securityMatcher`/`@Order`, rather than applying all chains like an AND set. A high-priority public chain can block a stricter chain from ever being selected.
3. **`@PreAuthorize`** is proxy-based method security when `@EnableMethodSecurity` is active. Objects created with **`new`**, internal calls **`this.read(...)`**, or direct repository paths can bypass method advice.
4. For requests **that actually pass through both URL and method security**, both must allow. A URL `permitAll` only lets the request proceed and does not turn off `@PreAuthorize`; method allow does not override an earlier HTTP deny.
5. Never assume class/interface policies and method annotations always combine with AND. Check inheritance/overrides and write explicit expressions when multiple conditions are required simultaneously.
6. **`@PreAuthorize`** runs before the service body, making it suitable for protecting operations with side effects. **`@PostAuthorize`** runs after the method returns and does not automatically undo side effects.

### Roles and Authorities

Under default settings:

- **`hasRole('READER')`** requires authority **`ROLE_READER`**.
- **`hasAuthority('SCOPE_docs.read')`** requires the exact authority **`SCOPE_docs.read`**.

OAuth scopes and roles are two independent facts. A test with the role yet missing the scope must be denied at HTTP; a test with the scope yet missing the role must reach the service and be denied by method security.

### Distinguishing 401/403

| Scenario | Demo Result | Why |
| --- | --- | --- |
| Anonymous calls protected API | HTTP **401** | HTTP Basic entry point challenges for authentication |
| Authenticated, missing HTTP scope | HTTP **403** | URL authorization denies |
| Passes HTTP, missing role/owner/tenant | HTTP **403** | Method/domain authorization denies |
| Direct Java service call lacking permission | **AccessDeniedException** | Java call has no HTTP status |

HTTP outcomes depend on `AuthenticationEntryPoint`/`AccessDeniedHandler` configuration and authentication mechanism. This example intentionally uses Basic to demonstrate 401. `@WithMockUser` does not verify JWT signatures, scope mappings, or production IdPs.

## 3. Policy and Test Matrix

Endpoint: **GET /api/{tenant}/documents/{id}**. Policy allows access only when **all** hold:

~~~text
ALLOW =
    authenticated
    AND authority("SCOPE_docs.read")
    AND role("ROLE_READER")
    AND tenantMember(username, tenantId)
    AND exists(tenantId, documentId)
    AND owner(tenantId, documentId) == username
~~~

All other routes hit **`anyRequest().denyAll()`**. The example chooses to deny with **403** even when the document does not exist, because domain policy cannot prove permission; real products may choose 404 yet must document the contract and test consistently.

Data:

| Tenant | Document ID | Owner | Body |
| --- | --- | --- | --- |
| acme | report | alice | ACME report for alice |
| acme | bob-secret | bob | ACME secret for bob |
| beta | report | alice | BETA report for alice |

Membership: **alice ∈ acme**, **bob ∈ acme, beta**. Document **beta/report** is owned by alice yet alice is not a member of beta: this fixture catches the bug of checking owner while forgetting tenant.

| Scenario | Intentionally Failing Condition | Expected |
| --- | --- | --- |
| Anonymous | Not logged in | 401, service did not run |
| Role present, scope missing | HTTP scope | 403, service did not run |
| Scope present, role missing | Method role | 403, service did not run |
| Alice reads `acme/report` | No failing condition | 200, exact body |
| Alice reads `acme/bob-secret` | Owner | 403, service did not run |
| Alice reads `beta/report` | Tenant membership | 403, service did not run |
| Alice reads `acme/missing` | Resource existence | 403 per policy |
| Alice calls `/outside` | Fallback URL | 403 |
| Alice calls `service.read(acme,bob-secret)` | Owner, bypassing HTTP | `AccessDeniedException` |

A good negative test makes **one condition fail while all remaining conditions hold**. If a test lacks both role and scope simultaneously, HTTP blocks first and the test turns green without proving `@PreAuthorize` works.

## 4. Runnable Maven Application

Directory tree:

~~~text
layered-authz/
├── pom.xml
├── src/main/java/com/example/layered/
│   ├── LayeredApplication.java
│   ├── SecurityConfig.java
│   ├── Document.java
│   ├── ResourceKey.java
│   ├── DocumentRepository.java
│   ├── DocPolicy.java
│   ├── DocumentService.java
│   └── DocumentController.java
└── src/test/java/com/example/layered/
    └── LayeredAuthorizationTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>layered-authz</artifactId>
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
~~~

**LayeredApplication.java**: enables method security.

~~~java
package com.example.layered;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class LayeredApplication {
    public static void main(String[] args) {
        SpringApplication.run(LayeredApplication.class, args);
    }
}
~~~

**SecurityConfig.java**: scope required for `GET /api/**`; remaining URLs denied by default. Keeps default CSRF because only GET is tested.

~~~java
package com.example.layered;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/**")
                    .hasAuthority("SCOPE_docs.read")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Document.java**:

~~~java
package com.example.layered;

public record Document(String tenantId, String id, String owner, String body) {
}
~~~

**ResourceKey.java**:

~~~java
package com.example.layered;

record ResourceKey(String tenantId, String documentId) {
}
~~~

**DocumentRepository.java**: includes `tenantId` in the key, so two tenants can share the same document ID.

~~~java
package com.example.layered;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {
    private final Map<ResourceKey, Document> documents = Map.of(
        new ResourceKey("acme", "report"),
            new Document("acme", "report", "alice", "ACME report for alice"),
        new ResourceKey("acme", "bob-secret"),
            new Document("acme", "bob-secret", "bob", "ACME secret for bob"),
        new ResourceKey("beta", "report"),
            new Document("beta", "report", "alice", "BETA report for alice")
    );

    public Optional<Document> find(String tenantId, String id) {
        return Optional.ofNullable(documents.get(new ResourceKey(tenantId, id)));
    }
}
~~~

**DocPolicy.java**: membership, existence, and ownership. Public method so the SpEL expression on the bean can invoke it.

~~~java
package com.example.layered;

import java.util.Map;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("docPolicy")
public class DocPolicy {
    private final DocumentRepository repository;
    private final Map<String, Set<String>> members = Map.of(
        "alice", Set.of("acme"),
        "bob", Set.of("acme", "beta")
    );

    public DocPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication,
                           String tenantId, String documentId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        String username = authentication.getName();
        if (!members.getOrDefault(username, Set.of()).contains(tenantId)) {
            return false;
        }
        return repository.find(tenantId, documentId)
            .map(doc -> doc.owner().equals(username))
            .orElse(false);
    }
}
~~~

Client-sent tenant must be verified against membership/entitlement from a trusted source, never trusting `tenantId` in the URL on its own. In production, the repository/database also needs a tenant condition (`WHERE tenant_id = ...` or row-level security).

**DocumentService.java**: a `@PreAuthorize` expression enforcing role **AND** domain policy; `#p0`/`#p1` are `tenantId` and `documentId` respectively.

~~~java
package com.example.layered;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;
    private final AtomicInteger calls = new AtomicInteger();

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasRole('READER') and @docPolicy.canRead(authentication, #p0, #p1)")
    public Document read(String tenantId, String documentId) {
        calls.incrementAndGet();
        return repository.find(tenantId, documentId)
            .orElseThrow(() -> new IllegalStateException(
                "Resource disappeared after authorization"
            ));
    }

    public int invocationCount() {
        return calls.get();
    }

    public void resetInvocationCount() {
        calls.set(0);
    }
}
~~~

**DocumentController.java**: injects the Spring bean so calls pass through the method-security proxy.

~~~java
package com.example.layered;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/{tenant}/documents/{id}")
    public Document read(@PathVariable String tenant,
                         @PathVariable String id) {
        return service.read(tenant, id);
    }
}
~~~

## 5. Test Suite with 10 Concrete Cases

**LayeredAuthorizationTest.java**: uses `@SpringBootTest` to run real controller, HTTP security, service proxy, and policy. `@AutoConfigureMockMvc` keeps filters enabled. `@WithMockUser` sets user/authorities per test. Counter resets in `@BeforeEach`.

~~~java
package com.example.layered;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LayeredAuthorizationTest {
    @Autowired private MockMvc mvc;
    @Autowired private DocumentService service;

    @BeforeEach
    void reset() {
        service.resetInvocationCount();
    }

    @Test
    void publicHealthIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk());
        assertEquals(0, service.invocationCount());
    }

    @Test
    void anonymousUserIsChallengedAtHttpLayer() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isUnauthorized());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_READER"})
    void readerWithoutScopeCannotPassHttpLayer() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"SCOPE_docs.read"})
    void scopeWithoutRoleCannotPassMethodLayer() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void allLayersAllowCorrectOwnerAndTenant() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("acme"))
            .andExpect(jsonPath("$.id").value("report"))
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.body").value("ACME report for alice"));
        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void bothAuthoritiesStillCannotReadOtherOwner() throws Exception {
        mvc.perform(get("/api/acme/documents/bob-secret"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void bothAuthoritiesStillCannotReadOtherTenant() throws Exception {
        // beta/report has owner alice, yet alice does not belong to beta.
        mvc.perform(get("/api/beta/documents/report"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void unknownResourceDeniedByPolicy() throws Exception {
        mvc.perform(get("/api/acme/documents/missing"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void unmatchedUrlDeniedByDefault() throws Exception {
        mvc.perform(get("/outside"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_READER"})
    void directCallStillEnforcesMethodRule() {
        assertThrows(AccessDeniedException.class,
            () -> service.read("acme", "bob-secret"));
        assertEquals(0, service.invocationCount());
    }
}
~~~

**Evidence provided by each test group:**

- **publicHealthIsAccessibleWithoutLogin** confirms `/health` is intentionally public.
- **anonymousUserIsChallengedAtHttpLayer** verifies unauthenticated gets challenged with 401.
- **readerWithoutScopeCannotPassHttpLayer** proves HTTP scope enforcement works because role and domain are both valid.
- **scopeWithoutRoleCannotPassMethodLayer** proves `@PreAuthorize` works because scope and data are both valid.
- **allLayersAllowCorrectOwnerAndTenant** checks HTTP 200 **plus exact body, tenant, and owner**, avoiding 200 with wrong data.
- **bothAuthoritiesStillCannotReadOtherOwner** catches IDOR/BOLA despite valid role/scope.
- **bothAuthoritiesStillCannotReadOtherTenant** catches missing membership despite matching owner.
- **unknownResourceDeniedByPolicy** and **unmatchedUrlDeniedByDefault** verify fail-closed domain and URL behavior.
- **directCallStillEnforcesMethodRule** confirms Java calls through the Spring proxy remain blocked without HTTP filters.

Each deny branch also checks **`invocationCount() == 0`**, confirming the method body did not run before denial. Asserting only HTTP 403 is insufficient: it can hide a bug where data was already read or side effects already occurred.

### Running and Verifying

~~~bash
java -version
mvn -version
mvn test
~~~

With valid configuration and code, expect **10 tests run, 0 failures, 0 errors**. Spring startup timings/logs may vary. The example needs no database or real HTTP server. `@WithMockUser` tests do not replace real token testing in OAuth2/OIDC.

## 6. Mutation Tests: Intentionally Break Rules, Tests Must Turn Red

Once the baseline suite is green, try **one mutation at a time**, run **`mvn test`**, then restore.

**Mutation A: broad `permitAll` shadows scope rule.**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/health").permitAll()
    .requestMatchers("/api/**").permitAll() // WRONG: broad matcher comes first
    .requestMatchers(HttpMethod.GET, "/api/**")
        .hasAuthority("SCOPE_docs.read")
    .anyRequest().denyAll()
)
~~~

Test **readerWithoutScopeCannotPassHttpLayer** must fail: alice still has valid role and domain, so the result changes from 403 to 200 despite missing scope. This is a **matcher ordering** bug.

**Mutation B: remove `@PreAuthorize` on `DocumentService.read`.** Tests for missing role, wrong owner, wrong tenant, and direct call must fail. The missing ID test may throw `IllegalStateException` because the service body executes; that is still a policy failure, not a valid denial.

**Mutation C: change AND to OR.**

~~~java
@PreAuthorize("hasRole('READER') or @docPolicy.canRead(authentication, #p0, #p1)")
~~~

Anyone with `ROLE_READER` passes the service even with wrong owner/tenant. **bothAuthoritiesStillCannotReadOtherOwner** and **bothAuthoritiesStillCannotReadOtherTenant** must fail.

**Mutation D: remove tenant membership check in `DocPolicy`.** **bothAuthoritiesStillCannotReadOtherTenant** must fail, because `beta/report` has owner alice even though alice does not belong to beta.

**Mutation E: change `anyRequest().denyAll()` to `anyRequest().permitAll()`.** **unmatchedUrlDeniedByDefault** must fail. Never leave new routes accidentally public.

If a dangerous mutation still leaves tests green, check whether your tests properly isolate the layer, whether the service is mocked, or whether another rule denies before reaching the rule under test.

## 7. Common Mistakes and Vulnerabilities

| Mistake | Consequence | How to Check and Fix |
| --- | --- | --- |
| Broad `permitAll` placed before strict matcher | Bypasses HTTP scope | Match narrow first; test with sufficient role yet missing scope |
| Wrong order of multiple `SecurityFilterChain`s | Public chain captures private routes | Constrain `securityMatcher` clearly and test `@Order` of every chain |
| Forgetting `@EnableMethodSecurity` | `@PreAuthorize` becomes inactive | Missing-role/wrong-owner tests must fail when annotation is removed |
| `@WithMockUser` missing both role and scope | Test gets 403 for the wrong reason | Supply every condition except the single one under test |
| Using `new` or `this.securedMethod(...)` | Bypasses proxy advice | Call Spring bean via proxy; test self-invocation paths if any |
| Mocking the protected service itself | Real annotations never run | Keep the real service; mock dependencies if needed |
| `@AutoConfigureMockMvc(addFilters = false)` | Tests bypass HTTP security | Keep filters enabled in URL policy tests |
| Testing only 200 cases | Rules can be deleted and tests stay green | Test every deny branch; use mutations |
| Misusing OR | A single condition suffices to enter | Write truth tables and explicit AND expressions |
| Checking only owner, skipping tenant | Cross-tenant document leaks | Create fixture with matching owner yet wrong tenant |
| Asserting only exception/status | Service may have already executed | Check counters, DB state, audit, or side effects |
| Using `@PostAuthorize` for write actions | Can mutate data before denial | Check beforehand at a trusted boundary |

### Scenarios to Expand in Real Products

Add negative tests for **JWT claim mapping**, role hierarchies, admin overrides, multiple chains, URL aliases/encoded paths, IDOR/BOLA, permissions revoked while caches are warm, queries with tenant predicates, data-writing methods, and errors from `@ControllerAdvice`. For permission caches, test invalidation/permission versioning per contract; `@WithMockUser` does not prove old JWTs are invalidated. For operations with side effects, assert DB/outbox/audit remain unchanged when denied.

## 8. Acceptance Checklist

- [ ] Policy covers authentication, scope, role, tenant membership, existence, and ownership.
- [ ] Request matchers go narrow-before-broad; fallback `denyAll`; multiple chains have clear `securityMatcher`/`@Order`.
- [ ] Tests verify 401 anonymous, 403 missing scope, 403 missing role with all other conditions satisfied.
- [ ] 200 tests verify exact tenant/owner/body data.
- [ ] Deny tests cover wrong owner, wrong tenant, missing ID, and unlisted URLs.
- [ ] Direct service call tests through the Spring bean catch `AccessDeniedException`.
- [ ] Deny tests confirm the service body did not run when policy must block beforehand.
- [ ] Mutations (broad `permitAll`, removing annotation, swapping AND/OR, removing membership) all turn tests red.
- [ ] Corresponding production tests cover JWT, DB, cache, async, and write operations.

## 9. References

- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Java Configuration / Multiple SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — MockMvc Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html

**Remember:** do not merely prove that an authorized user can read a document. Prove that **every failing condition is denied at the exact right layer**, rules are in the right order, and the service never runs outside its permissions; that is how you catch conflicting multi-layer policies before they become vulnerabilities.