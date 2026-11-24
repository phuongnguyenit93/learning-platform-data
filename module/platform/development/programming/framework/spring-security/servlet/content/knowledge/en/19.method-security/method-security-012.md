# Testing Service-Layer Policies Independently of HTTP

> **Context:** Spring Security 6 on the **Servlet stack**, Java 17+, and Spring Boot 3.x. This topic belongs to **Method Security**. The focus is on testing service authorization decisions **without sending HTTP requests**, without depending on URLs, filter chains, MVC, cookies, CSRF, or MockMvc. This lesson distinguishes a **pure policy unit test** from an **integration test calling a Spring-managed service through the method-security proxy**, covers using `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, and `SecurityContextHolder`, and checks `@PreAuthorize` and `@PostAuthorize`, exceptions, negative cases, preventing self-invocation bypasses, and resource state after a denied operation. Includes a complete Gradle/Java project and testing exercises.

## 1. Why test authorization without HTTP?

A controller might call a service:

```text
GET /api/documents/102
       |
       v
SecurityFilterChain  -- HTTP authentication / coarse authorization
       |
       v
DocumentController.get(102)
       |
       v
DocumentService.read(102)
       |
       v
DocumentPolicy.canRead(authentication, 102)
```

If you only test HTTP `GET /api/documents/102`, a **403** result can come from several causes: insufficient user permissions, CSRF (for unsafe methods), missing session/credentials, wrong filter chain, wrong matcher, missing endpoint, or an actual denial from the method interceptor. A pure HTTP test may not distinguish the root cause.

When calling the **Spring bean `DocumentService` directly** in a test (without sending an HTTP request), we place a known `Authentication` into the test security context and focus on verifying:

1. Do the `@PreAuthorize` rules run before the service method?
2. Are the user, resource, role, tenant, and status attributes actually evaluated correctly?
3. Does a denied case throw `AccessDeniedException`?
4. Is the **service body prevented from executing** when pre-authorization fails?
5. Does a `@PostAuthorize` check the returned object properly?
6. Is the Spring-managed service invoked through an **AOP proxy**, or is the test instantiating an object with `new` that has no interceptor?
7. Are the test results independent of Servlet filters, sessions, and controllers?

**Conclusion:** service authorization should be tested as a **business contract**, not merely as an implementation detail of an HTTP endpoint. However, service tests do not replace end-to-end tests for the filter chain, login, request matchers, and CSRF.

## 2. Four testing levels related to security

| Level | Subject under test | Spring context? | HTTP? | What does it prove? |
| --- | --- | --- | --- | --- |
| **Policy unit test** | Pure `DocumentPolicy.canRead/canApprove` | Not required | No | Business conditions on subject/resource/action inputs are computed accurately |
| **Method-security integration test** | `@PreAuthorize`/`@PostAuthorize` on a Spring-managed service | Yes (with method-security config) | **No** | The method interceptor enforces policies when the service is called through a proxy |
| **Web security integration test** | SecurityFilterChain, controller, filters, session, and endpoints | Yes | Can use MockMvc | HTTP rules + method security work together properly |
| **End-to-end test** | Real browser/client, proxy, IdP/DB, and network | Deployed system | Yes | Behavior across layers and real infrastructure |

You should not rely on only one level. Policy unit tests are fast and allow testing many combinations; method-security integration tests prove **wiring**, proxying, and SpEL; HTTP/E2E tests catch gaps caused by filter chains, request matchers, JSON binding, or tokens/cookies.

### What MUST NOT be inferred

- `@WithMockUser` does not prove that passwords were verified by `AuthenticationProvider`.
- A passing method security test does not prove `/admin/**` is properly blocked at the HTTP layer.
- `@PreAuthorize` running when called through a Spring proxy does not prove internal calls via `this` are also blocked.
- Testing that a policy bean returns `false` does not prove the service has method-security annotations attached.
- A MockMvc test returning 403 due to CSRF does not prove roles or resource policies are correct.

## 3. Execution flow of @PreAuthorize when calling the service directly

When `@EnableMethodSecurity` is enabled, Spring Security creates the appropriate method interceptors/advisors. With proxy-based method security, calls from another bean to a Spring-managed service pass through the proxy before running the body.

```text
JUnit test method
   |
   +--> @WithMockUser creates Authentication for SecurityContext
   |
   v
Spring-managed DocumentService bean (AOP proxy)
   |
   v
AuthorizationManagerBeforeMethodInterceptor
   |
   +--> evaluate @PreAuthorize SpEL
   |        |
   |        +--> @documentPolicy.canRead(authentication, #id)
   |
   +--> ALLOW -> invoke DocumentService.read(...)
   |
   +--> DENY  -> AccessDeniedException
                    |
                    +--> service body is NOT invoked
```

This is the conceptual model for default proxy-based method security. Specific class names and call paths can vary depending on the Spring Security version and enabled annotations. The key point is verifying that **the proxy mechanism actually exists** and checking **the authorization outcome** without depending on a Servlet request.

### The HTTP layer and the service layer are different

A Servlet application typically uses:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
```

This is a fragment in `SecurityFilterChain` enforcing HTTP constraints. It does not yet know whether a user owns a specific document ID. In the domain service we have:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public Document read(long id) {
    return repository.require(id);
}
```

The service rule runs whether the method is called from a REST controller, another Spring bean, or a direct test **through the proxy**. As a result, this part of the policy does not depend on how HTTP routes are organized.

## 4. SecurityContextHolder in tests without HTTP

`SecurityContextHolder` holds the `SecurityContext` and `Authentication` in use according to Spring Security's current strategy. For a unit/integration test without an HTTP request, it can still carry the principal/authorities for the method-security interceptor.

Options for populating the context:

- **`@WithMockUser`:** creates a test `Authentication` from the declared username/roles/authorities.
- **`@WithAnonymousUser`:** simulates anonymous authentication created by Spring Security Test.
- **`@WithUserDetails`:** loads `UserDetails` from a `UserDetailsService` bean in the Spring context; suitable when you want to check role mapping from a test user store.
- **`@WithSecurityContext`:** builds a custom security context via a custom test annotation (e.g., custom principal, token claims, tenant context) when the scenario requires it.
- **Manual context setup:** convenient for unit tests using a fake `Authentication` or services without starting a Spring context; requires clearing the context after each test.

**Important point:** every test must have a mechanism to clear the context; test A's principal must never leak into test B.

### 4.1. @WithMockUser

```java
@Test
@WithMockUser(username = "alice", roles = {"READER"})
void example() {
    // The MethodSecurity interceptor sees username "alice"
    // and authority "ROLE_READER".
}
```

`roles = {"READER"}` is converted by Spring Security Test into the `ROLE_READER` authority. When using `authorities={"DOCUMENT_READ"}`, the authority value is kept verbatim without automatically prepending `ROLE_`.

`@WithMockUser` **does not send username/password to a web authentication filter** and does not verify passwords with BCrypt. It explicitly creates a test principal for testing authorization logic.

### 4.2. @WithAnonymousUser

```java
@Test
@WithAnonymousUser
void anonymousMustBeDenied() {
    assertThrows(AccessDeniedException.class,
            () -> documentService.read(101L));
}
```

`@WithAnonymousUser` places an anonymous authentication in the test context. This differs from a **SecurityContext with no Authentication at all**: depending on the interceptor/expression, having no authentication may result in `AuthenticationCredentialsNotFoundException` or another exception. To intentionally test anonymous access, use this annotation instead of assuming an empty context behaves like HTTP anonymous.

### 4.3. @WithUserDetails

```java
@Test
@WithUserDetails("bob")
void permissionsFromUserDetailsService() {
    // Test execution listener loads UserDetails "bob"
    // and creates an Authentication based on this user.
}
```

Requires a `UserDetailsService` bean containing the matching username. It tests the configuration of **test user lookup and authorities from that bean**, while still not performing a real password/HTTP login.

### 4.4. Manual SecurityContext in unit tests

```java
Authentication subject = new UsernamePasswordAuthenticationToken(
        "alice",
        "unused-in-test",
        List.of(new SimpleGrantedAuthority("ROLE_READER")));
```

The constructor taking authorities creates an authenticated token usable for policy unit tests. It does not mean an actual password was verified; the subject is constructed purposefully to test authorization decisions. Do not copy this mock pattern into a production login endpoint.

## 5. Two decision types: @PreAuthorize and @PostAuthorize

### 5.1. @PreAuthorize checks before running the method body

```java
@PreAuthorize("hasRole('EDITOR') and @documentPolicy.canEdit(authentication, #id)")
public String edit(long id, String content) {
    return repository.updateContent(id, content);
}
```

If the user lacks the role or the policy returns false, the method body **is not called**. This is the preferred choice for operations with side effects such as update, approve, delete, money transfer, or sending email.

**Proper test:** do not just assert the exception; also assert that the repository **was not modified** after the denied call.

### 5.2. @PostAuthorize checks the returned object

```java
@PostAuthorize("@documentPolicy.canRead(authentication, returnObject.id())")
public Document inspect(long id) {
    return repository.require(id);
}
```

Spring Security evaluates the `@PostAuthorize` expression **after the method returns the object** and before the caller receives a successful result. For read-only resources, this pattern can be useful to inspect attributes of the loaded object. However, the service body has already run, so **do not use @PostAuthorize as the sole guard for state-changing operations**. For objects that can be null, null handling is needed in the expression/service; for example, using repository `require(id)` to throw an exception when the document does not exist.

### 5.3. @PreFilter and @PostFilter do not replace @PreAuthorize

`@PreFilter` filters input collection elements; `@PostFilter` filters output collections according to a policy. They are not automatically equivalent to blocking side-effecting operations on individual objects. When using filtering, test the resulting collection and control what data is loaded/processed before filtering.

### 5.4. hasRole, hasAuthority, and the ROLE_ prefix

`hasRole('MANAGER')` typically checks the `ROLE_MANAGER` authority. `@WithMockUser(roles="MANAGER")` creates this exact authority. `hasAuthority('DOC_APPROVE')` checks the `DOC_APPROVE` authority verbatim; if a test only grants `ROLE_MANAGER`, it will not match automatically.

**Do not mix role names with authority strings** while assuming a prefix is added automatically across every API.

## 6. Designing tests to catch real policy bugs

If a policy requires the `MANAGER` role, matching tenant, `PENDING` document status, and an approver who is not the owner, a single test with "wrong tenant, wrong role, wrong owner" all at once **does not prove every condition is actually checked**. It only proves the combined request is denied.

You should have **one test per condition**, with all remaining conditions set to valid values:

| Factor to test | Other factors | Expected |
| --- | --- | --- |
| Missing MANAGER role | Valid tenant, non-owner, PENDING, sufficient clearance | DENY |
| Wrong tenant | Has MANAGER, non-owner, PENDING, sufficient clearance | DENY |
| Insufficient clearance | Has MANAGER, valid tenant, non-owner, PENDING | DENY |
| Owner self-approving | Has MANAGER, valid tenant, PENDING, sufficient clearance | DENY |
| Document already APPROVED | Has MANAGER, valid tenant, non-owner, sufficient clearance | DENY |
| All conditions met | All attributes are valid | ALLOW |
| Anonymous | Valid resource | DENY |
| Profile missing from directory | Mocked roles are still complete | DENY |
| Non-existent resource ID | Valid user | DENY |
| User only has read access | No edit permission | DENY, data remains unchanged |

For `@PostAuthorize`, you need tests for both an allowed returned object and an object denied after loading. For a denied object, the caller must never receive unauthorized contents.

## 7. Java 17 / Spring Boot 3 project: service authorization without starting an HTTP server

The project below uses Spring Boot **3.3.5**, Spring Security **6.x** managed by Boot, Gradle **8.5**, JUnit 5, and `spring-security-test`. The module includes the Spring MVC dependency to resemble a real Servlet application, but the test explicitly uses `@SpringBootTest(webEnvironment = NONE)`. **No controller, no MockMvc calls, and no HTTP requests are created.**

Context: employees read, edit, and approve documents across two tenants, `north` and `south`. All document metadata and user profiles come from server-side repositories/directories, not assumed headers sent by clients.

### 7.1. Business rules

**Read `read(id)`:**
- subject is authenticated, not anonymous;
- has a server-side user profile;
- user tenant = document tenant;
- user clearance ≥ document classification level;
- document is not in `ARCHIVED` status.

**Edit `edit(id, content)`:**
- has `ROLE_EDITOR`;
- satisfies the read policy;
- is the owner;
- document is still in `DRAFT`.

**Approve `approve(id)`:**
- has `ROLE_MANAGER`;
- satisfies the read policy;
- document is in `PENDING`;
- approver is **not the owner** (*separation of duties*).

**Inspect via `inspect(id)`:** read-only method that returns the resource and then evaluates `@PostAuthorize`; used to compare against pre-authorization.

### 7.2. Test users and documents

| User | Tenant | Clearance | Roles |
| --- | --- | --- | --- |
| `alice` | north | 1 | READER |
| `bob` | north | 3 | READER, EDITOR |
| `maria` | north | 3 | READER, MANAGER |
| `carol` | south | 2 | READER, MANAGER |

| Doc | Tenant | Owner | Min clearance | Status | Sample content |
| --- | --- | --- | --- | --- | --- |
| 101 | north | alice | 1 | DRAFT | north-public |
| 102 | north | bob | 2 | PENDING | north-approval |
| 103 | south | carol | 1 | PENDING | south-draft |
| 104 | north | maria | 2 | PENDING | manager-owned |
| 105 | north | alice | 1 | ARCHIVED | archived |
| 106 | north | bob | 2 | DRAFT | editable |

These data fixtures are recreated before each method-security test. There is no real database; `ConcurrentHashMap` demonstrates state and lets tests verify that content **is unchanged** after a denied operation.

### 7.3. Directory tree

```text
method-security-service-tests/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    UserProfileDirectory.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
  src/test/java/demo/
    DocumentPolicyUnitTest.java
    DocumentServiceSecurityTest.java
```

### 7.4. settings.gradle

```groovy
rootProject.name = 'method-security-service-tests'
```

### 7.5. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Why is `-parameters` needed?** Spring method-security SpEL often references `#id`. When the Java compiler retains parameter names, the method-security expression resolver can identify `id` by its exact name. Some environments also read metadata via annotations; this demo uses `-parameters` explicitly to avoid argument-name resolution errors.

**Why include `spring-boot-starter-web` if not testing HTTP?** It shows that the service and security config can live inside a real Servlet application. The tests use `WebEnvironment.NONE` so no HTTP server is started; HTTP headers/cookies/MVC do not participate in decisions. If the application is purely a non-web worker/service, `starter-web` can be omitted while still testing method security.

### 7.6. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 7.7. SecurityConfig.java: enabling Method Security

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("study123"))
                .roles("READER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("study123"))
                .roles("READER", "EDITOR")
                .build();
        UserDetails maria = User.withUsername("maria")
                .password(encoder.encode("study123"))
                .roles("READER", "MANAGER")
                .build();
        UserDetails carol = User.withUsername("carol")
                .password(encoder.encode("study123"))
                .roles("READER", "MANAGER")
                .build();
        return new InMemoryUserDetailsManager(alice, bob, maria, carol);
    }
}
```

`@EnableMethodSecurity` registers the infrastructure for `@PreAuthorize` and `@PostAuthorize` using defaults. No Servlet request is needed for the AOP interceptor to run; it operates on Spring-managed service beans.

Local passwords and users are for study purposes only. With `@WithMockUser`, the test does not use these passwords. With `@WithUserDetails`, Spring Security Test loads user details from the bean without performing password-based authentication.

### 7.8. UserProfileDirectory.java: trusted subject attributes

`src/main/java/demo/UserProfileDirectory.java`:

```java
package demo;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class UserProfileDirectory {

    private final Map<String, UserProfile> profiles = Map.of(
            "alice", new UserProfile("north", 1),
            "bob", new UserProfile("north", 3),
            "maria", new UserProfile("north", 3),
            "carol", new UserProfile("south", 2));

    public UserProfile find(String username) {
        return profiles.get(username);
    }
}

record UserProfile(String tenant, int clearance) {}
```

The username must come from the `Authentication` that method security is evaluating; tenant permissions and clearance come from the server-side directory. If a test tries to mock a `ghost` principal with full roles while the directory has no profile for it, the policy must **fail closed**, not grant access just because the mocked role is high.

### 7.9. DocumentRepository.java: server-controlled resource data

`src/main/java/demo/DocumentRepository.java`:

```java
package demo;

import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentRepository {

    private final ConcurrentMap<Long, Document> documents =
            new ConcurrentHashMap<>();

    public DocumentRepository() {
        reset();
    }

    public void reset() {
        documents.clear();
        documents.put(101L, new Document(101L, "north", "alice",
                1, DocumentStatus.DRAFT, "north-public"));
        documents.put(102L, new Document(102L, "north", "bob",
                2, DocumentStatus.PENDING, "north-approval"));
        documents.put(103L, new Document(103L, "south", "carol",
                1, DocumentStatus.PENDING, "south-draft"));
        documents.put(104L, new Document(104L, "north", "maria",
                2, DocumentStatus.PENDING, "manager-owned"));
        documents.put(105L, new Document(105L, "north", "alice",
                1, DocumentStatus.ARCHIVED, "archived"));
        documents.put(106L, new Document(106L, "north", "bob",
                2, DocumentStatus.DRAFT, "editable"));
    }

    public Document find(long id) {
        return documents.get(id);
    }

    public Document require(long id) {
        Document document = find(id);
        if (document == null) {
            throw new NoSuchElementException("Document not found");
        }
        return document;
    }

    public Document updateContent(long id, String newContent) {
        return documents.compute(id, (key, old) -> {
            if (old == null) {
                throw new NoSuchElementException("Document not found");
            }
            return new Document(old.id(), old.tenant(), old.owner(),
                    old.minClearance(), old.status(), newContent);
        });
    }

    public Document approve(long id) {
        return documents.compute(id, (key, old) -> {
            if (old == null) {
                throw new NoSuchElementException("Document not found");
            }
            if (old.status() != DocumentStatus.PENDING) {
                throw new IllegalStateException(
                        "Document is not pending");
            }
            return new Document(old.id(), old.tenant(), old.owner(),
                    old.minClearance(), DocumentStatus.APPROVED,
                    old.content());
        });
    }
}

enum DocumentStatus {
    DRAFT, PENDING, APPROVED, ARCHIVED
}

record Document(
        long id,
        String tenant,
        String owner,
        int minClearance,
        DocumentStatus status,
        String content) {}
```

The repository uses `ConcurrentHashMap` to test state; it **does not replace transactions** in production. `compute` ensures state transitions for the same key are atomic within a single JVM. With a database/multiple nodes, transactions/optimistic locking/conditional updates are needed; authorization and updates must be evaluated for **TOCTOU** risks.

The `reset()` fixture keeps tests independent of execution order, though if JUnit parallel execution is enabled later, the repository should be isolated per test or guarded with a resource lock; never let tests mutate the same map concurrently.

### 7.10. DocumentPolicy.java: web-independent business policy

`src/main/java/demo/DocumentPolicy.java`:

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final UserProfileDirectory directory;
    private final DocumentRepository repository;

    public DocumentPolicy(UserProfileDirectory directory,
                          DocumentRepository repository) {
        this.directory = directory;
        this.repository = repository;
    }

    private UserProfile profile(Authentication auth) {
        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return null;
        }
        return directory.find(auth.getName());
    }

    public boolean canRead(Authentication auth, long id) {
        UserProfile user = profile(auth);
        Document doc = repository.find(id);

        return user != null
                && doc != null
                && user.tenant().equals(doc.tenant())
                && user.clearance() >= doc.minClearance()
                && doc.status() != DocumentStatus.ARCHIVED;
    }

    public boolean canEdit(Authentication auth, long id) {
        if (!canRead(auth, id)) {
            return false;
        }

        Document doc = repository.find(id);
        return doc != null
                && doc.owner().equals(auth.getName())
                && doc.status() == DocumentStatus.DRAFT;
    }

    public boolean canApprove(Authentication auth, long id) {
        if (!canRead(auth, id)) {
            return false;
        }

        Document doc = repository.find(id);
        return doc != null
                && doc.status() == DocumentStatus.PENDING
                && !doc.owner().equals(auth.getName());
    }
}
```

The policy **does not take `HttpServletRequest`** and does not read headers, query parameters, paths, or sessions. Tests can construct an `Authentication` directly. It compares the subject's tenant/clearance against the server's resource tenant/classification/status and applies action-specific checks.

`canEdit` and `canApprove` do not check roles yet: this is intentional. Roles are checked with `hasRole('EDITOR')` and `hasRole('MANAGER')` directly in the service's `@PreAuthorize`. By separating these conditions, tests can independently verify both the **role gate** and the **object-level gate**.

If production prefers a policy bean independent of SpEL role checks, role checks can be moved into the policy. What matters is that **the final combined policy leaves no condition uncovered**.

### 7.11. DocumentService.java: where the interceptor operates

`src/main/java/demo/DocumentService.java`:

```java
package demo;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #id)")
    public Document read(long id) {
        return repository.require(id);
    }

    @PreAuthorize(
            "hasRole('EDITOR') and @documentPolicy.canEdit(authentication, #id)")
    public String edit(long id, String newContent) {
        repository.updateContent(id, newContent);
        return "edited-" + id;
    }

    @PreAuthorize(
            "hasRole('MANAGER') and @documentPolicy.canApprove(authentication, #id)")
    public String approve(long id) {
        repository.approve(id);
        return "approved-" + id;
    }

    @PostAuthorize(
            "@documentPolicy.canRead(authentication, returnObject.id())")
    public Document inspect(long id) {
        return repository.require(id);
    }
}
```

In `read`, the check occurs before `repository.require(id)` runs. In `inspect`, the repository reads the object first, and then `@PostAuthorize` evaluates the returned object. `inspect` is designed to be **read-only**; never use `@PostAuthorize` as the sole safeguard for `edit`/`approve`, because the operation could already mutate state before the interceptor denies access.

`#id` must be resolved from method parameters; the build config added `-parameters`. If the service returns a DTO instead of a record, the SpEL `returnObject.id()` must match the corresponding API/JavaBean getters.

## 8. Unit testing the policy without a Spring context

The first test verifies **pure policy logic** without starting Spring and without using a method-security proxy. Instantiating the repository, directory, and policy with `new` is appropriate **at this unit test level**, because the goal is to test the policy conditions themselves.

`src/test/java/demo/DocumentPolicyUnitTest.java`:

```java
package demo;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPolicyUnitTest {

    private DocumentRepository documents;
    private DocumentPolicy policy;

    @BeforeEach
    void setUp() {
        documents = new DocumentRepository();
        UserProfileDirectory profiles = new UserProfileDirectory();
        policy = new DocumentPolicy(profiles, documents);
    }

    private Authentication subject(String username, String role) {
        return new UsernamePasswordAuthenticationToken(
                username, "unused-test-credential",
                List.of(new SimpleGrantedAuthority("ROLE_" + role)));
    }

    @Test
    void matchingTenantAndClearancePermitsRead() {
        assertTrue(policy.canRead(subject("alice", "READER"), 101L));
        assertTrue(policy.canRead(subject("bob", "READER"), 102L));
    }

    @Test
    void higherClassificationDeniesRead() {
        assertFalse(policy.canRead(subject("alice", "READER"), 102L));
    }

    @Test
    void crossTenantResourceIsDenied() {
        assertFalse(policy.canRead(subject("alice", "READER"), 103L));
        assertTrue(policy.canRead(subject("carol", "READER"), 103L));
    }

    @Test
    void archivedResourceIsDenied() {
        assertFalse(policy.canRead(subject("alice", "READER"), 105L));
    }

    @Test
    void missingProfileOrResourceFailsClosed() {
        assertFalse(policy.canRead(subject("ghost", "MANAGER"), 101L));
        assertFalse(policy.canRead(subject("bob", "READER"), 999L));
        assertFalse(policy.canRead(null, 101L));
    }

    @Test
    void ownerCanEditOnlyOwnDraft() {
        assertTrue(policy.canEdit(subject("bob", "READER"), 106L));
        assertFalse(policy.canEdit(subject("bob", "READER"), 101L));
        assertFalse(policy.canEdit(subject("bob", "READER"), 102L));
    }

    @Test
    void approverPolicyUsesStatusAndOwner() {
        assertTrue(policy.canApprove(subject("maria", "READER"), 102L));
        assertFalse(policy.canApprove(subject("maria", "READER"), 104L));
        assertFalse(policy.canApprove(subject("maria", "READER"), 101L));
    }
}
```

### What does this unit test prove?

- Subject/resource tenant and clearance are compared properly.
- Archived records cannot be read even when the owner matches.
- Missing user profiles or missing resources fail closed.
- Edit applies only to the owner of a DRAFT document.
- Approve requires a non-owner and a PENDING document.

### What does this unit test NOT prove yet?

- Whether `@PreAuthorize` is enabled by Spring.
- Whether `hasRole('MANAGER')`/`hasRole('EDITOR')` actually run on the service.
- Whether calls to `DocumentService` go through an AOP proxy.
- Whether `@PostAuthorize` validates the returned object.
- Whether HTTP filters or Basic login work.

**This is why a second test suite is needed.** Unit testing the policy bean alone is valuable, but it does not replace method-security integration tests.

## 9. Integration testing the Spring-managed service directly, without HTTP

This suite uses:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentServiceSecurityTest {
    @Autowired
    DocumentService service;
}
```

`WebEnvironment.NONE` ensures the test does not start a web application server and does not invoke `DispatcherServlet`. The Spring context still registers `@EnableMethodSecurity` and creates the proxy/authorization infrastructure. The `DocumentService` bean is obtained from the context, **not via `new DocumentService(...)` inside the test**.

### 9.1. Complete test code

`src/test/java/demo/DocumentServiceSecurityTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService service;

    @Autowired
    DocumentRepository documents;

    @BeforeEach
    void reset() {
        documents.reset();
    }

    @Test
    void springServiceIsProxiedForMethodSecurity() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void readerCanReadDocumentInOwnTenant() {
        assertEquals("north-public", service.read(101L).content());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void insufficientClearanceIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(102L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void userCannotReadOtherTenantDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(103L));
    }

    @Test
    @WithMockUser(username = "carol", roles = "READER")
    void legitimateSouthTenantUserCanRead() {
        assertEquals("south-draft", service.read(103L).content());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void archivedDocumentIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(105L));
    }

    @Test
    @WithMockUser(username = "ghost", roles = {"READER", "MANAGER"})
    void unknownProfileFailsClosedDespitePowerfulMockedRole() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void missingDocumentFailsClosed() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(999L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserIsDeniedWithoutHttpRequest() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void ownerWithoutEditorRoleCannotChangeState() {
        String before = documents.require(101L).content();

        assertThrows(AccessDeniedException.class,
                () -> service.edit(101L, "tampered"));

        assertEquals(before, documents.require(101L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void editorCanEditOwnDraft() {
        assertEquals("edited-106",
                service.edit(106L, "new-content"));
        assertEquals("new-content", documents.require(106L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void editorCannotEditAnotherOwnersDraft() {
        String before = documents.require(101L).content();

        assertThrows(AccessDeniedException.class,
                () -> service.edit(101L, "tampered"));

        assertEquals(before, documents.require(101L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void editorCannotEditNonDraftEvenIfOwner() {
        String before = documents.require(102L).content();

        assertThrows(AccessDeniedException.class,
                () -> service.edit(102L, "tampered"));

        assertEquals(before, documents.require(102L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void missingManagerRoleDeniesApprovalEvenIfOtherConditionsMatch() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(104L));
        assertEquals(DocumentStatus.PENDING,
                documents.require(104L).status());
    }

    @Test
    @WithMockUser(username = "maria", roles = {"READER", "MANAGER"})
    void managerCanApproveOtherOwnersPendingDocument() {
        assertEquals("approved-102", service.approve(102L));
        assertEquals(DocumentStatus.APPROVED,
                documents.require(102L).status());
    }

    @Test
    @WithMockUser(username = "maria", roles = {"READER", "MANAGER"})
    void managerCannotApproveOwnDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(104L));
        assertEquals(DocumentStatus.PENDING,
                documents.require(104L).status());
    }

    @Test
    @WithMockUser(username = "carol", roles = {"READER", "MANAGER"})
    void managerFromOtherTenantCannotApprove() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(102L));
        assertEquals(DocumentStatus.PENDING,
                documents.require(102L).status());
    }

    @Test
    @WithMockUser(username = "carol", roles = {"READER", "MANAGER"})
    void managerCannotSelfApproveSouthTenantDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(103L));
    }

    @Test
    @WithMockUser(username = "maria", roles = {"READER", "MANAGER"})
    void alreadyApprovedDocumentCannotBeApprovedAgain() {
        service.approve(102L);

        assertThrows(AccessDeniedException.class,
                () -> service.approve(102L));

        assertEquals(DocumentStatus.APPROVED,
                documents.require(102L).status());
    }

    @Test
    @WithMockUser(username = "maria", roles = "READER")
    void postAuthorizePermitsAllowedReturnObject() {
        Document document = service.inspect(102L);
        assertEquals(102L, document.id());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void postAuthorizeBlocksUnauthorizedReturnObject() {
        assertThrows(AccessDeniedException.class,
                () -> service.inspect(102L));
    }

    @Test
    @WithUserDetails("bob")
    void withUserDetailsLoadsConfiguredUserAuthorities() {
        assertEquals("edited-106",
                service.edit(106L, "from-user-details"));
        assertEquals("from-user-details",
                documents.require(106L).content());
    }
}
```

**Expected result:** All 22 JUnit tests in `DocumentServiceSecurityTest` along with the 7 tests in `DocumentPolicyUnitTest` PASS when using the exact source files and Gradle build above. This is an **expectation based on code analysis**, not a claim that the tests were executed in this lesson.

### 9.2. Key takeaways from the tests

**First, checking the AOP proxy:** testing `AopUtils.isAopProxy(service)` warns when a bean is not protected by a method-security proxy. However, having a proxy alone still does not prove annotations evaluate properly; negative `AccessDeniedException` tests are mandatory.

**Second, authentication without going through HTTP:** `@WithMockUser`/`@WithUserDetails` create authentication in the test security context. Calling `service.read(101L)` goes directly to the Spring bean, with no GET request or mock servlet request.

**Third, each rule has an independent negative case:** tenant, clearance, owner, resource state, and role are not lumped together into a single test. Consequently, if a developer accidentally deletes one condition, the corresponding test fails.

**Fourth, checking side effects:** the unauthorized edit test records `before` and asserts that the content **did not change** after `AccessDeniedException`. The denied approve test also asserts the status remains `PENDING`.

**Fifth, `@PostAuthorize`:** tests both an allowed returned object and an object denied from being returned. With `@PostAuthorize`, the method body has already run before the check; therefore it is only used with read-only methods in the demo.

**Sixth, test isolation:** `@BeforeEach` resets the repository to the same baseline. The Spring Security Test listener automatically sets/clears the security context per test. Avoid placing `@WithMockUser` at the class level when multiple tests need different subjects without method-level overrides.

## 10. Commands to run and how to read the results

From the `method-security-service-tests` project directory, with JDK 17+ and a compatible Gradle version installed:

```bash
gradle test
```

If the Gradle Wrapper is present:

```bash
./gradlew test
```

On Windows PowerShell, if the project has the wrapper:

```powershell
.\gradlew.bat test
```

In the Gradle/JUnit report, the expected outcome is zero failing tests. Tests that intentionally invoke the service without authorization **PASS when `assertThrows(AccessDeniedException.class, ...)` catches the expected exception**, not because the application allowed the request through.

Run tests by class to isolate scope:

```bash
./gradlew test --tests demo.DocumentPolicyUnitTest
./gradlew test --tests demo.DocumentServiceSecurityTest
```

Running `bootRun` is unnecessary for verifying this lesson: the goal is **HTTP-independent method-level authorization**. You can run the app later when integrating controllers, but it is not a step in service testing.

### Why does status 403 not appear?

In these tests, the method-security interceptor throws `AccessDeniedException` to the Java caller. There is no HTTP request or `ExceptionTranslationFilter`/Servlet chain to translate that exception into a 403 response. If you need to verify 403 at an endpoint, you must write **a separate HTTP integration test suite**; do not mock a status code in a service test and treat that as a successful security test.

## 11. Testing mistakes that cause @PreAuthorize to be bypassed

### 11.1. The test manually calls new Service instead of getting the Spring bean

Wrong if the goal is verifying the interceptor:

```java
DocumentService service = new DocumentService(repository);
service.read(101L); // Does not run through the Spring AOP proxy.
```

Instantiating the service with `new` does not register `@EnableMethodSecurity` and has no advice. Even if a method has `@PreAuthorize`, the annotation does not automatically turn into an `if` statement executed by Java. To test method-security wiring, inject the `@Autowired DocumentService service` bean from the Spring context.

**Distinction:** in `DocumentPolicyUnitTest`, using `new DocumentPolicy(...)` is **correct** because the goal is purely unit testing policy logic. What is wrong is using a `new DocumentService(...)` object and claiming the test verifies `@PreAuthorize`.

### 11.2. Forgetting @EnableMethodSecurity

If the configuration is missing:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {}
```

annotations such as `@PreAuthorize` may not be activated. A happy-path `read` test still PASSES because the method body runs, leading to **false confidence**. Negative cases help uncover missing wiring.

With Spring Security 6, `@EnableMethodSecurity` is the corresponding modern mechanism; do not blindly rely on the legacy `@EnableGlobalMethodSecurity` configuration assuming all defaults are identical.

### 11.3. Self-invocation inside the same service

Anti-pattern example:

```java
@Service
public class BadService {

    public String unprotectedEntry(long id) {
        return this.sensitiveAction(id);
    }

    @PreAuthorize("hasRole('MANAGER')")
    public String sensitiveAction(long id) {
        return "processed-" + id;
    }
}
```

Because calling `this.sensitiveAction(id)` does not go through the Spring proxy, advice for `sensitiveAction` may **not run**. Do not treat a test that only calls `service.sensitiveAction(id)` and sees it succeed/fail as sufficient: test all public entry points (`unprotectedEntry`, scheduled jobs, event listeners, message handlers) that can reach the operation.

How to handle it: extract the secured method into another Spring bean and invoke it through the proxy, or place an explicit policy check at a domain boundary guaranteed to execute. Do not "fix" it by assuming AOP will intercept internal calls.

### 11.4. Private/final methods and proxy limitations

Proxy-based method security is not the same as bytecode rewriting across all call sites. Methods that cannot be intercepted by a proxy (e.g., private methods, certain final methods/classes, or internal calls) may not be protected as expected. Prefer public/proxyable methods and verify with integration tests, especially when the project uses Kotlin (final classes by default), multiple interfaces, or additional proxy optimizations.

Do not merely assert `AopUtils.isAopProxy` if the secured method does not actually execute through the proxy. Deny/allow tests are essential additional proof.

### 11.5. Wrong SpEL parameter name

`@PreAuthorize("@policy.canRead(authentication, #id)")` depends on the method argument name `id`. If the Java build does not retain parameter-name metadata or annotation metadata does not match, `#id` can be null/unresolved.

Fix: enable the compiler `-parameters` flag as in the sample project; or use `@P("id")`/`@Param` if the corresponding framework version and resolver support it. Policy unit tests cannot catch SpEL method parameter-name errors; service integration tests through the proxy will catch them.

### 11.6. Wrong bean name in SpEL

`@documentPolicy.canRead(...)` requires a bean named `documentPolicy`. The sample project explicitly declares `@Component("documentPolicy")` for clarity. If a bean name changes and the annotation is forgotten, requests may fail during evaluation instead of being denied under the intended policy.

In tests, distinguish **policy returning DENY** from **exceptions due to broken wiring or SpEL**. Do not catch generic `Exception` and call it "test passed because it was blocked," because a completely different configuration bug could be masked.

## 12. Setting SecurityContextHolder manually

Beyond `spring-security-test`, you can set the context manually in unit tests. This technique is useful for library code that does not use Spring Test listeners or when testing custom authentication objects.

Example **fragment** for a JUnit test:

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContext context =
            SecurityContextHolder.createEmptyContext();

    Authentication auth = new UsernamePasswordAuthenticationToken(
            "alice",
            "unused",
            List.of(new SimpleGrantedAuthority("ROLE_READER")));

    context.setAuthentication(auth);
    SecurityContextHolder.setContext(context);

    // Call the Spring-managed service through the proxy or policy bean.
    // assertion...
} finally {
    SecurityContextHolder.clearContext();
}
```

**Do not** place a `SecurityContext` mutated by someone else into a shared global variable, do not rely on test ordering, and do not allow a ThreadLocal context to leak to the next test thread. If you intentionally enable `MODE_INHERITABLETHREADLOCAL` or a custom strategy, understand how propagation works across threads/executors.

### SecurityContext when tests run asynchronously

A test calling a service via `CompletableFuture`/`@Async` may run on a different thread; by default, the context is not automatically propagated everywhere like a synchronous call. Do not expect `@WithMockUser` on the test thread to automatically exist on a worker thread. For async business logic that needs explicit security context propagation (e.g., `DelegatingSecurityContextExecutor` or a supported context propagation mechanism), include proper cleanup and dedicated tests.

Nor should you enable `MODE_GLOBAL` across a large test suite just to "make async tests pass," because it dangerously shares context across tests/threads.

### Test setup before the context is created

`@WithMockUser` and security test annotations are processed by the Spring Test listener according to its lifecycle. By default, they typically set up the context **before `@BeforeEach`**; you can configure `setupBefore=TEST_EXECUTION` to change that timing. If `@BeforeEach` has logic requiring a specific subject, understand the exact lifecycle/version; preferably keep authorization assertions inside test methods and avoid depending on security context during fixture setup.

## 13. Mockito and what to avoid when mocking dependencies

Mockito can assist unit tests of domain policy and tests verifying "service body is not invoked":

```java
// Illustrates the idea, not a standalone test class.
verify(repository, never()).updateContent(anyLong(), anyString());
```

However, if you replace **the Spring-managed secured service itself** with a regular mock, the proxy/method-security interceptor may not be tested. You can make the method return stubbed values, skipping `@PreAuthorize` annotations and falsely believing the policy permits it.

**Suggested strategy:**

- For policy unit tests, mock the PIP/repository if needed to quickly construct edge-case inputs; or use real in-memory fixtures.
- For method-security integration tests, **keep the real proxied service**, only faking or mocking lower-level dependencies when appropriate.
- Do not mock `AuthorizationManager` and conclude the real policy was evaluated.
- If using `@MockBean` (Boot test) or `@MockitoBean` (in supported Spring Test versions), verify your version and which bean is replaced; avoid accidentally replacing the very secured bean under test.
- Combine exception assertions with `verifyNoInteractions(...)` or asserting unchanged state to catch side effects.

### Why is @WithMockUser not "mocking the method"?

`@WithMockUser` mocks **the identity/authorities in the test security context**; it does not replace the body of `DocumentService`, does not stub `DocumentPolicy`, and does not bypass annotations. The real service is still checked by Spring AOP against configured rules.

## 14. Method Security and @Transactional: ordering, side effects, races

When a service has both `@PreAuthorize` and `@Transactional`, Spring AOP advisors have ordering, so test their interaction under your specific version/config. Regardless of advice order, **do not** assume a policy pre-check alone prevents all races against concurrently changing data.

Example:

```text
T1: policy canApprove(document=102, status=PENDING) -> allow
T2: another request approves document 102 -> status=APPROVED
T1: service update document 102                 -> ?
```

If the update writes unconditionally without checking state, a double transition can occur. The demo `DocumentRepository.approve` re-checks `PENDING` inside `ConcurrentMap.compute`. Production databases need `UPDATE ... WHERE id=? AND status='PENDING'`, optimistic locking, a version column, or appropriate transaction isolation.

### Testing concurrency differs from pure method-security tests

A synchronous `@WithMockUser` test only checks permissions at one point in time. If the business rule requires preventing double approval, dedicated stress/concurrency tests and transactional integration tests are required; do not treat 22 method-security tests as sufficient proof of atomicity on a real DB.

### Side effects even when @PostAuthorize denies

If `@PostAuthorize` is used on a method that sends a notification before returning its result, the caller may receive `AccessDeniedException` **after the email was already sent**. Therefore, tests should cover mutations/side effects if a method uses post-authorization; prefer pre-authorization for state-changing operations.

## 15. Testing custom Authentication, JWT claims, and tenant context

`@WithMockUser` has simple username and authorities, sufficient for sample role/owner cases. For business logic needing richer principal information — tenant memberships, department, MFA, authentication freshness, OAuth2 scopes — you can:

1. Manually create a test `Authentication` with the right principal and authorities shape.
2. Use `@WithSecurityContext` with a `WithSecurityContextFactory` to reuse setup.
3. For JWT resource servers, use `spring-security-test` helpers in HTTP tests to build JWT authentication; for service-only tests, construct an appropriate `JwtAuthenticationToken` if the policy genuinely reads JWT claims.
4. Use `@WithUserDetails` when you want to test authorities from a `UserDetailsService` bean.

**Do not** create a raw `X-Tenant` header and trust it in a service-only test: services normally have no `HttpServletRequest`; tenant context must be **transformed into a verified object** grounded in trusted membership and principal boundaries.

### Example distinguishing trusted vs. untrusted input

```text
Subject from verified Authentication:
    username=alice, allowedTenants=[north], clearance=1

Resource from DocumentRepository:
    docId=103, tenant=south, minClearance=1

Client-selected tenant:
    "south"

Decision:
    DENY, because alice does not belong to south.
```

If the service accepts a tenant selector, it must compare it against the subject's allowed tenants and the document's tenant. Tests can pass the selector as a **method argument**, without needing a real HTTP header, to prove the policy rejects spoofing.

### Do not use @WithMockUser to prove the authentication provider

`@WithMockUser(username="admin", roles="ADMIN")` can synthesize an admin user even when the production user store has no admin at all. That is **valid** for testing authorization ("if this user has role X, what does the policy allow"), but it does not prove registration, password verification, disabled-account checks, OIDC login, or JWT signatures work. Those require separate authentication integration tests.

## 16. Testing services across multiple entry points

A service can be invoked from:

- REST Controller / Servlet HTTP;
- GraphQL resolver;
- scheduled job;
- message consumer;
- batch processor;
- event handler;
- tests or internal beans.

If method security is attached to the service via a proxy, it helps enforce a shared policy, but it **does not automatically create an Authentication for background jobs**. A scheduled job calling a service with no `SecurityContext` may be denied — typically right for user-scoped operations, though a controlled service/system principal is needed for system jobs.

For message-processing systems, never take a `userId` from a payload and impersonate users arbitrarily. To run "on behalf of a user," verify the event, signature, authorization context, expiration, and audit trail. Never "bypass `@PreAuthorize`" for internal code paths by calling `new Service`.

### Test each entry point or only the service?

Method-security tests guarantee the **service boundary**, but if a code path bypasses the proxy (self-invocation, static helper, or direct repository call), it may go unprotected. Add tests at important entry points to confirm the service is invoked in a way that goes through the method interceptor.

## 17. Extended experiments for data and state

After completing the demo, you can extend it in order:

**Exercise 1 — role vs. authority:** replace `hasRole('EDITOR')` with `hasAuthority('DOC_WRITE')`, add tests for `@WithMockUser(authorities="DOC_WRITE")`, and confirm `roles="EDITOR"` no longer matches automatically.

**Exercise 2 — multiple tenants:** change `UserProfile` from a single `tenant` to `Set<String> allowedTenants`. The policy must verify the document's tenant belongs to the allowed set; test that a `north` user cannot read `south` merely by passing a tenant selector as a method argument.

**Exercise 3 — state-based policy:** add `REJECTED` and allow reviewers only to transition `PENDING → REJECTED`. Test denying a request when the document is already `APPROVED`, and assert the state stays unchanged.

**Exercise 4 — data classification:** set document classification above clearance; test every boundary so there are no `>=` vs. `>` bugs.

**Exercise 5 — re-auth/MFA:** allow approval only if the authentication has verified assurance and a sufficiently fresh timestamp. Use an injectable server clock instead of hard-coding `System.currentTimeMillis()` so tests remain deterministic.

**Exercise 6 — audit:** add a repository for audit records without logging raw credentials. Test that unauthorized calls do not emit fake "approved" audit entries, while emitting security-safe denial events when appropriate.

**Exercise 7 — self-invocation:** intentionally create a bean where `outerMethod` calls `this.securedMethod` and write a negative test, then extract a separate bean so both direct and indirect calls are blocked.

**Exercise 8 — mutation testing:** delete each tenant/owner/clearance/status/role condition in the policy one by one and observe which test fails. If a condition is deleted and all tests still PASS, the test suite is not independent enough.

**Exercise 9 — concurrency:** add a repository with optimistic locking and submit two concurrent approve calls so only one transition succeeds.

**Exercise 10 — HTTP integration:** once the service policy is solid, add controller and MockMvc tests to ensure HTTP 401/403, method matchers, CSRF, and service security work together. This is an **additive** phase and must never replace independent service testing.

## 18. QA checklist for a method-security test suite

- [ ] `@EnableMethodSecurity` is enabled in the Spring test context.
- [ ] The service under test is **Spring-injected**, not instantiated directly with `new`.
- [ ] `AopUtils.isAopProxy(service)` is true when proxy-based method security is expected.
- [ ] Allow and deny tests exist for every protected method.
- [ ] Deny tests catch `AccessDeniedException` specifically, not generic `Exception` masking errors.
- [ ] Anonymous token is distinguished from a context with no `Authentication`.
- [ ] `@WithMockUser` uses `roles`/`authorities` and the `ROLE_` prefix accurately.
- [ ] `@WithUserDetails` tests exist if loading roles from the user store matters.
- [ ] Policy unit tests are **separated** from method-interceptor integration tests.
- [ ] User/resource attributes come from trusted fixture data.
- [ ] Tenant/role/owner/status/clearance dimensions are tested independently.
- [ ] Unknown principal/resource fails closed and is denied.
- [ ] Denied edit/approve calls do not alter data state.
- [ ] Post-authorization is used only when the method body has no side effects.
- [ ] Tests reset mutable fixtures and do not rely on execution order or another test's context.
- [ ] `#id` in SpEL resolves cleanly, with compiler `-parameters` or matching metadata.
- [ ] No self-invocation or unproxied entry points bypass policy.
- [ ] The secured service itself is not mocked in tests meant to verify AOP.
- [ ] Java exception outcomes are not confused with HTTP 401/403 statuses.
- [ ] When policies change, regression tests and clear code reviews accompany them.

## 19. Common mistakes and how to resolve them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Unauthorized test still returns data | Method security not enabled, or service bypassed proxy | Enable `@EnableMethodSecurity`, inject Spring bean, add negative tests |
| `@PreAuthorize` checks wrong id | SpEL `#id` fails to resolve due to missing parameter metadata | Enable `-parameters` and check signature |
| Role rule denies even though test sets roles | `ROLE_` prefix confusion or using `hasAuthority` instead of `hasRole` | Compare actual authority against expression |
| Anonymous test throws unexpected error | Empty context differs from `AnonymousAuthenticationToken` | Use `@WithAnonymousUser`, distinguish credential-missing behavior |
| Policy unit tests PASS but method calls are not blocked | Unit tests do not test wiring/proxying | Add `@SpringBootTest(webEnvironment=NONE)` + deny tests |
| Internally called method skips interceptor | Self-invocation via `this` | Extract secured service bean or enforce explicitly |
| Deny test PASSES due to NPE/SpEL parse error | Catching generic `Exception` | Catch `AccessDeniedException` and inspect the cause |
| Tests fail intermittently depending on order | Shared repository/security context not reset | `@BeforeEach` setup, Spring Security Test cleanup, test isolation |
| Denied edit still mutates resource | Check runs too late or method called without proxy | `@PreAuthorize`, assert unchanged state, fix call path |
| `@PostAuthorize` denies after email was sent | Check runs after side effects | Use pre-authorization and transaction-safe operations |
| User missing profile still gets access | Fail-open policy or role-only gate | Check subject directory, fail closed |
| `@WithMockUser` test PASSES while real login fails | Mock auth bypasses authentication mechanism | Test authentication separately with filters/IdP/tokens |
| Testing roles without testing resource ownership | RBAC tests alone do not verify object-level checks | Add ABAC unit and method integration tests |
| Service test throws `AccessDeniedException` instead of 403 | No HTTP layer in the test | Intentional; add a MockMvc/E2E suite if testing HTTP status |
| Async test does not see Authentication | Thread context propagation not configured | Use an appropriate propagation mechanism, test async separately |

## 20. Self-check questions

1. **Why test services independently of HTTP?** To isolate business policy and the method interceptor from controllers/filters/CSRF.
2. **How does a policy unit test differ from a method-security integration test?** A unit test calls `canRead` logic directly; an integration test calls a secured Spring bean through its proxy to exercise `@PreAuthorize`.
3. **Does `@WithMockUser` actually verify passwords?** No. It directly synthesizes a test authentication.
4. **Does `@WithUserDetails` issue an HTTP request?** No. It loads `UserDetails` from a bean and places it into the test context.
5. **Should you call `new DocumentService(...)` when testing `@PreAuthorize`?** No, if you want to test AOP interception; inject the bean instead.
6. **Does a deny from `@PreAuthorize` occur before or after the method body?** Before. Therefore, you should assert that side effects did not occur.
7. **What is the risk of using `@PostAuthorize` for resource updates?** The operation may have already updated data before being denied.
8. **Does a non-HTTP method security test return HTTP status 403?** No; the Java caller receives `AccessDeniedException`.
9. **Why test every condition independently?** To prove the policy truly checks role, tenant, clearance, owner, and status; a test failing multiple conditions at once can mask an omitted check.
10. **What if a user has the `MANAGER` role but violates the tenant policy?** They must be denied; roles do not override tenant constraints.
11. **How does `@WithAnonymousUser` differ from a null context?** It creates an anonymous `Authentication`; a null context may take a different error path.
12. **Does `@EnableMethodSecurity` work on services without a Servlet request?** Yes, with a Spring-managed proxy and an appropriate `Authentication` context.
13. **What is the impact of self-invocation?** An internal `this.securedMethod()` call can bypass AOP proxy advice.
14. **Why is `-parameters` needed?** So SpEL `#id` references map cleanly to the exact method parameter name.
15. **After a denied approve call, what should you assert?** The exception and that the document status has not changed.
16. **Can you drop HTTP integration tests once service tests PASS?** No; HTTP matchers, filters, authentication, and CSRF require separate tests.
17. **What if a JWT token is valid but the user's tenant membership was revoked?** Policy membership freshness/revocation is required; method-level policies must still consult a trusted source.
18. **If a service is replaced by `@MockBean`, are you testing real `@PreAuthorize`?** Likely not; check test wiring and avoid mocking the secured service.
19. **Why not catch any `Exception` to prove denial?** Because an NPE or SpEL/config error would also make the test pass falsely.
20. **How should policy tests handle audit logging?** Log decisions/actor/resource IDs cleanly without putting secrets/tokens or sensitive payloads into logs.

**Takeaway:** **Policy unit tests** verify business conditions, whereas **method-security integration tests** verify that Spring Security actually enforces `@PreAuthorize`/`@PostAuthorize` through the proxy. Use `@SpringBootTest(webEnvironment=NONE)`, inject the **Spring-managed service**, establish principals with `@WithMockUser`/`@WithAnonymousUser`/`@WithUserDetails`, invoke methods directly, assert `AccessDeniedException` when unauthorized, and assert **data remains unchanged** for denied side effects. Test each dimension—role, tenant, owner, clearance, and status—independently. Do not confuse these tests with authentication/filter/HTTP tests; both layers must be verified.
