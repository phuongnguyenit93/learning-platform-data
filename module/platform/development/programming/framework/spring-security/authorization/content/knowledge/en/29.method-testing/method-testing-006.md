# Testing expressions on parameters, ownership, and input attributes in Spring Security

This hands-on lesson focuses on **method-level access control testing** (method security), where allow or deny decisions depend on method call parameters, **actual resource ownership**, and attributes of input objects. Examples use Java 17, Spring Security 6.x, JUnit 5, and Spring Security Test; the concepts of `@PreAuthorize`, `@PostAuthorize`, and `@EnableMethodSecurity` also apply to Spring Security 7.x.

## 1. Objectives and testing boundary

After this lesson, you will be able to:

- Test SpEL expressions referencing method arguments such as `#username`, `#id`, `#input.title`, combined with `authentication.name` and `hasAuthority(...)`.
- Prove that users can only act on resources **owned by them according to trusted data**, not merely according to an `owner` field declared by the client in the request.
- Test both allowed and blocked cases: valid/invalid parameters, another user's resource, missing authorities, null/invalid input data, and anonymous users.
- Distinguish `@PreAuthorize` (decides **before** method execution) from `@PostAuthorize` (checks **after** a result has been produced).
- Write tests calling a **proxied Spring bean** and confirm that a blocked method produces no data mutations.

Suppose the system has document 10 owned by `alice` and document 20 owned by `bob`. If `alice` sends a request to edit document 20 with `declaredOwner="alice"`, the test must prove the system still **denies** it. This tests against ID-based privilege escalation (IDOR/BOLA).

## 2. How it works and which data is trusted

Enable method protection with `@EnableMethodSecurity` on a Spring configuration. When a call passes through the bean's proxy, Spring Security retrieves `Authentication` from `SecurityContext`, captures the call arguments, evaluates SpEL, and decides whether to let the method body execute.

| Expression component | Source of value | What to test |
| --- | --- | --- |
| `#username`, `#id`, `#input` | Method parameters supplied by the caller | Valid/invalid values, `null`, boundaries, spoofing |
| `authentication.name` | Identity of the logged-in user | Matching against parameter or owner |
| `hasAuthority('DOC_WRITE')` | Authorities on `Authentication` | With and without the specific authority |
| `@docPolicy.isOwner(authentication, #id)` | Policy bean looking up owner from a trusted data store | Own ID, another user's ID, nonexistent ID |
| `#input.declaredOwner`, `#input.title` | Properties on the client-submitted object | Matching/mismatching, blank string, too long |
| `returnObject.owner` | Property on the object already returned by the method | Authorized/unauthorized to view result |

Examples:

~~~java
@PreAuthorize("#username == authentication.name")
public String profile(@P("username") String username) { /* ... */ }

@PreAuthorize("@docPolicy.isOwner(authentication, #id)")
public String read(@P("id") long id) { /* ... */ }

@PreAuthorize("hasAuthority('DOC_WRITE') && " +
              "@docPolicy.isOwner(authentication, #id) && " +
              "#input != null && #input.title != null")
public void update(@P("id") long id, @P("input") EditInput input) { /* ... */ }
~~~

These are **illustrative method fragments**, not three standalone Java classes. `@P` (package `org.springframework.security.access.method`) binds an explicit parameter name for SpEL. When code is compiled with the `-parameters` flag, Spring can also discover parameter names via reflection; `@P` keeps the example independent of compiler settings. For a few simple parameters, SpEL also supports positional access like `#p0`, though meaningful names are easier to maintain.

**Trust principle:** `#input.declaredOwner == authentication.name` only proves the client *claimed* an owner name matching their login name. That does **not** prove the target document actually belongs to the user. A safe rule must check `#id` against the owner stored on the server (or via an equivalent resource-checking policy) before modifying data.

## 3. Runnable example: a minimal Spring context, no HTTP server needed

Create a Maven project with two files:

~~~text
method-expressions-test/
├── pom.xml
└── src/test/java/com/example/security/MethodExpressionsTest.java
~~~

`pom.xml` — uses Spring Boot 3.5.7 to manage compatible library versions, while running tests on a plain Spring Test context without starting a web application:

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
    <artifactId>method-expressions-test</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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
</project>
~~~

`src/test/java/com/example/security/MethodExpressionsTest.java` — all helper classes are placed in the same file so it is easy to run standalone:

~~~java
package com.example.security;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(MethodExpressionsTest.TestConfig.class)
class MethodExpressionsTest {

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class TestConfig {
        @Bean
        DocRepository repository() {
            return new DocRepository();
        }

        @Bean("docPolicy")
        DocPolicy docPolicy(DocRepository repository) {
            return new DocPolicy(repository);
        }

        @Bean
        DocumentService documentService(DocRepository repository) {
            return new DocumentService(repository);
        }
    }

    public static class DocView {
        private final String owner;
        private final String title;

        public DocView(String owner, String title) {
            this.owner = owner;
            this.title = title;
        }

        public String getOwner() { return owner; }
        public String getTitle() { return title; }
    }

    public static class EditInput {
        private final String declaredOwner;
        private final String title;

        public EditInput(String declaredOwner, String title) {
            this.declaredOwner = declaredOwner;
            this.title = title;
        }

        public String getDeclaredOwner() { return declaredOwner; }
        public String getTitle() { return title; }
    }

    public static class DocRepository {
        private final Map<Long, DocView> docs = new HashMap<>();

        public void reset() {
            docs.clear();
            docs.put(10L, new DocView("alice", "Alpha"));
            docs.put(20L, new DocView("bob", "Beta"));
        }

        public DocView find(long id) {
            return docs.get(id);
        }

        public String ownerOf(long id) {
            DocView doc = find(id);
            return doc == null ? null : doc.getOwner();
        }

        public void rename(long id, String title) {
            DocView before = docs.get(id);
            docs.put(id, new DocView(before.getOwner(), title));
        }
    }

    public static class DocPolicy {
        private final DocRepository repository;

        public DocPolicy(DocRepository repository) {
            this.repository = repository;
        }

        public boolean isOwner(Authentication authentication, long id) {
            String owner = repository.ownerOf(id);
            return owner != null
                    && authentication != null
                    && owner.equals(authentication.getName());
        }
    }

    public static class DocumentService {
        private final DocRepository repository;

        public DocumentService(DocRepository repository) {
            this.repository = repository;
        }

        // Authorization based on a parameter compared to the authenticated identity.
        @PreAuthorize("#username == authentication.name")
        public String profile(@P("username") String username) {
            return "profile:" + username;
        }

        // Ownership comes from the repository; caller only supplies ID.
        @PreAuthorize("@docPolicy.isOwner(authentication, #id)")
        public String readTitle(@P("id") long id) {
            return repository.find(id).getTitle();
        }

        // Must have authority + be actual owner + have valid input properties.
        @PreAuthorize("hasAuthority('DOC_WRITE')"
                + " && @docPolicy.isOwner(authentication, #id)"
                + " && #input != null"
                + " && #input.declaredOwner == authentication.name"
                + " && #input.title != null"
                + " && !#input.title.isBlank()"
                + " && #input.title.length() <= 120")
        public void rename(@P("id") long id, @P("input") EditInput input) {
            repository.rename(id, input.getTitle());
        }

        // Use only for queries with no side effects.
        @PostAuthorize("returnObject != null"
                + " && returnObject.owner == authentication.name")
        public DocView viewAfterRead(@P("id") long id) {
            return repository.find(id);
        }
    }

    @Autowired
    DocumentService service; // Spring bean wrapped with a method-security proxy.

    @Autowired
    DocRepository repository;

    @BeforeEach
    void resetFixtures() {
        repository.reset();
    }

    @Test
    @WithMockUser(username = "alice")
    void expressionFromParameterAllowsMatchingIdentityOnly() {
        assertEquals("profile:alice", service.profile("alice"));
        assertThrows(AccessDeniedException.class,
                () -> service.profile("bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownershipComesFromTrustedRepository() {
        assertEquals("Alpha", service.readTitle(10L));
        assertThrows(AccessDeniedException.class,
                () -> service.readTitle(20L));
        assertThrows(AccessDeniedException.class,
                () -> service.readTitle(999L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_WRITE")
    void validOwnerAuthorityAndInputAllowChange() {
        service.rename(10L, new EditInput("alice", "New title"));
        assertEquals("New title", repository.find(10L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_WRITE")
    void forgingOwnerInBodyCannotChangeForeignResource() {
        assertThrows(AccessDeniedException.class,
                () -> service.rename(20L, new EditInput("alice", "Attack")));
        assertEquals("Beta", repository.find(20L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_WRITE")
    void invalidInputIsRejectedBeforeMutation() {
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("bob", "Valid")));
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("alice", " ")));
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("alice", null)));
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, null));
        assertEquals("Alpha", repository.find(10L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerWithoutWriteAuthorityCannotUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> service.rename(10L, new EditInput("alice", "New")));
        assertEquals("Alpha", repository.find(10L).getTitle());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeUsesActualReturnedObject() {
        assertEquals("alice", service.viewAfterRead(10L).getOwner());
        assertThrows(AccessDeniedException.class,
                () -> service.viewAfterRead(20L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserCannotReadOwnedResource() {
        assertThrows(AccessDeniedException.class,
                () -> service.readTitle(10L));
    }
}
~~~

From the directory containing `pom.xml`, with JDK 17+ and Maven installed, run:

~~~bash
mvn test
~~~

**Expected result:** Maven finishes successfully, with 8 `@Test` methods executed and no failed assertions. Maven may print different logs depending on versions/plugins; this lesson does not rely on a fixed stdout string. Spring Security blocks unqualified calls with an exception in the `AccessDeniedException` hierarchy; the tests themselves assert that exception with `assertThrows`.

### Why does this example test real authorization?

1. `@SpringJUnitConfig` creates the ApplicationContext, and `@EnableMethodSecurity` registers the method interceptor. `service` is `@Autowired` from Spring so calls pass through the proxy. If `new DocumentService(repository)` were used to test, the annotations would not be applied and tests could yield false results.
2. `@WithMockUser` creates an `Authentication` per test with the specified `username`/`authorities`. It does not require a real account in a database. Spring Security Test sets up and tears down `SecurityContext` around test execution.
3. `DocPolicy` looks up the owner by `id` from `DocRepository`. The input `declaredOwner` can be spoofed, yet cannot alter the owner value in the repository.
4. `@BeforeEach` restores the initial data; valid update tests do not make subsequent tests depend on execution order.
5. For denied cases, the tests verify both the exception and that document state remains unchanged. Checking only an HTTP status or exception without checking side effects can miss security bugs.

## 4. Detailed analysis of each expression group

### 4.1. Comparing a parameter with the identity

The expression `#username == authentication.name` should be tested at least with a matching string, a different string, and `null`. When `username` differs from the login name, the method must be blocked **before** producing a result. Comparison is case-sensitive unless there is a normalization rule: `"Alice"` and `"alice"` are two different strings. Do not add `toLowerCase()` logic in the expression if the application identity lacks an explicit normalization convention.

For numeric IDs, avoid comparing a `Long` directly against a `String` from the principal when they are not in the same data domain. Retrieve the user ID from an appropriate custom principal or call a policy with typed parameters; do not assume `authentication.name` is a database ID.

### 4.2. Ownership: the source of truth lives on the server

The same user `alice` can call:

- `readTitle(10)`: repository returns `owner="alice"`, so allowed.
- `readTitle(20)`: repository returns `owner="bob"`, so denied.
- `readTitle(999)`: resource does not exist, policy returns `false`, so denied.

True ownership must not be inferred from `EditInput.getDeclaredOwner()` or a query parameter that the caller can alter. The `declaredOwner` field in the example is solely to teach testing input properties; in production design, it is better **not to let the client declare an owner field when unnecessary**. For multi-tenant APIs, add tenant checks to the policy, such as `document.tenantId == currentTenantId`, and write cross-tenant access tests.

If a policy needs a database, you can mock the repository to control different owners in unit tests, yet at least one integration test should verify the real path: security proxy → policy bean → repository → service.

### 4.3. Input object attributes

The expression on `rename` combines multiple conditions with `&&`:

1. The user has authority `DOC_WRITE`.
2. The document looked up by `id` actually belongs to the user.
3. `input` is non-`null`, and the client-declared owner does not conflict with the identity.
4. `title` is non-`null`, not blank, and at most 120 characters long.

SpEL evaluates `&&` with short-circuiting, so `#input != null` must precede accessing `#input.title` to avoid property access on `null`. Testing the `null` case helps detect expressions missing a guard. Even so, **authorization does not replace validation**: length, format, and allowed characters typically belong in Bean Validation and business logic; authorization expressions should contain conditions genuinely related to access rights.

Also test boundary cases, such as a 120-character title allowed and a 121-character title rejected if that rule is chosen. You can expand with `@ParameterizedTest` to avoid test duplication while keeping security and validation expectations distinct.

### 4.4. Role/authority privileges

`@WithMockUser(roles = "ADMIN")` generates the `ROLE_ADMIN` authority. Conversely, `@WithMockUser(authorities = "DOC_WRITE")` generates the exact `DOC_WRITE` authority without adding a `ROLE_` prefix. Thus `hasRole('ADMIN')` differs from `hasAuthority('ADMIN')`, and tests must accurately mirror how the application maps JWTs, sessions, or database users to authorities.

The `ownerWithoutWriteAuthorityCannotUpdate` case is crucial: **owning a resource is not necessarily sufficient to edit it**. A combined condition must deny access if one clause is missing, even when the owner is right and the input is completely valid.

### 4.5. Checking the returned object

`@PostAuthorize("returnObject.owner == authentication.name")` is suited for **read** operations where the owner is known only after fetching the resource. The expression is evaluated after the method body; if it fails, Spring Security prevents the caller from receiving the result and throws a denial exception.

Do not use this as the sole protection layer for **data-mutating** methods: updates or notifications may already have occurred before `@PostAuthorize` blocks the return value. For write operations, check privileges before mutation using `@PreAuthorize` or an in-transaction policy, depending on your data consistency model.

## 5. Required test case matrix

| Actor / authority | Resource or parameter | Input attributes | Expected |
| --- | --- | --- | --- |
| `alice` | `profile("alice")` | — | Allowed |
| `alice` | `profile("bob")` | — | Denied |
| `alice` | Document 10, true owner `alice` | — | Read allowed |
| `alice` | Document 20, true owner `bob` | — | Denied |
| `alice` | Nonexistent ID 999 | — | Not granted |
| `alice` + `DOC_WRITE` | Document 10 | `declaredOwner="alice"`, valid title | Edit allowed |
| `alice` + `DOC_WRITE` | Document 20 | Forged `declaredOwner="alice"` | Denied, data unchanged |
| `alice` without `DOC_WRITE` | Document 10 | Valid title | Denied |
| `alice` + `DOC_WRITE` | Document 10 | `declaredOwner="bob"` | Denied |
| `alice` + `DOC_WRITE` | Document 10 | `input=null` or `title=null` / whitespace only | Denied |
| Anonymous | Document 10 | — | Denied |
| `alice` | `viewAfterRead(20)` | Result has owner `bob` | Denied by `@PostAuthorize` |

These rows test both the **allow path** and the **deny path** for each clause of the expression. A test that only uses `@WithMockUser` and calls a method returning data successfully does not prove that ownership, parameter, or input-attribute conditions are enforced.

## 6. Common pitfalls and how to catch them

**Test bypasses the proxy.** Instantiating the service with `new`, calling the target bean directly, calling a protected method via `this.method()` within the same bean, or calling a private/final method causes proxy advice not to run as expected. Fix this by testing with a Spring context, injecting the bean, and placing protected methods on the proper bean/call boundary. If an unauthorized test still returns data instead of throwing `AccessDeniedException`, check `@EnableMethodSecurity`, the bean proxy, and the call path first.

**Wrong SpEL parameter name.** Writing `#documentId` when the method accepts `id` without `@P("documentId")` or `-parameters` metadata prevents the expression from seeing the expected value. Keep names consistent, declare `@P`, and add an allowed-branch test to detect always-deny binding bugs.

**Trusting only owner from the request.** `@PreAuthorize("#input.owner == authentication.name")` can be bypassed if the client edits `owner` in the payload. Write a counterexample test: user `alice` submits an ID belonging to `bob` while claiming `owner="alice"`. The right rule asks the server for the owner of the **requested ID**.

**Testing only the exception.** If code writes data before privileges are checked, the call may still be denied while the system has already changed state. Add `assertEquals`/`verify(..., never())` for write operations, emitted messages, or modified record counts. Include transactional boundary tests where needed.

**Mocking away the real policy.** Mocking the entire service bearing `@PreAuthorize` and asserting the mock returns 200 does not test service authorization. Mock dependencies behind the service (repositories, policy dependencies) so calls still flow through the proxy and real expression.

**Mismatched principal type.** `@WithMockUser` creates Spring Security's standard principal; if the application uses custom `UserDetails`/JWT claims, such tests may not reflect the real principal. Use `@WithUserDetails` when a `UserDetailsService` exists, or a custom `@WithSecurityContext` to construct the right `Authentication`; supplement with integration tests using the real authentication mechanism.

**Confusing HTTP and method layers.** `MockMvc` can verify 401/403 at the web layer, yet filters or routes do not prove service method security ran. Test the Spring service bean directly to prove SpEL; then use HTTP tests to ensure endpoints map access errors properly. In direct service tests, expect `AccessDeniedException`; HTTP exception handling usually turns authenticated access denials into 403, while missing authentication may lead to 401 depending on configuration.

**Ignoring race conditions.** Owner or tenant can change between the policy check and the update statement. For sensitive operations, add owner/tenant conditions to constrained update statements, locking, or concurrency controls; also test privilege changes mid-operation. An annotation alone does not guarantee atomicity.

## 7. Checklist before accepting tests

- [ ] `@EnableMethodSecurity` is present in the test's Spring context; the service is obtained via dependency injection.
- [ ] At least one **allowed** case and one **denied** case exist for each authorization expression.
- [ ] Ownership is verified against a trusted source, including another user's ID and a nonexistent ID.
- [ ] Owner/tenant spoofing in input data is tested, not only usernames in test annotations.
- [ ] Missing authority as well as `null`/empty/boundary inputs are tested.
- [ ] Blocked cases produce no state changes or side effects.
- [ ] SpEL expressions resolve parameters properly; the difference between `roles` and `authorities` is clear.
- [ ] `@PostAuthorize` is used only where executing the body before checking is acceptable.
- [ ] If custom principals exist, additional tests use a realistic `Authentication` type.
- [ ] Each test is data-independent and does not rely on order or security state from earlier tests.

## 8. Reference documentation

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — `@WithMockUser` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html
- OWASP — Insecure Direct Object Reference Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html

**Target outcome:** A positive case proves the right user with sufficient privileges can execute the method; negative cases prove *changing parameters*, *changing resource ID*, *spoofing input attributes*, or *lacking authorities* cannot bypass the policy. For write methods, verify that data state remains unchanged after every denial.
