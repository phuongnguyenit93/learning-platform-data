# Unit-Testing the Evaluator Standalone and Integration-Testing Through the Proxy

> **Topic:** Spring Security – authorization · **Group:** PermissionEvaluator. This lesson distinguishes two testing levels with different purposes: **unit tests** that call `PermissionEvaluator.hasPermission(...)` directly to prove permission rules, and **integration tests** that call a Spring-managed service **through the method-security proxy** to prove `hasPermission(...)` expressions are actually enforced. Examples apply to Spring Boot 3.x, Spring Security 6.x, JUnit Jupiter, MockMvc, and Java 17+; if upgrading to Spring Boot 4 / Spring Security 7, re-verify dependency and test auto-configuration for that version.

## 1. Why are two types of tests needed?

Suppose a service exposes:

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

There are at least **two completely different claims**:

1. Given the right `Authentication`, ID, resource type, and permission, **the evaluator returns the right result**: Alice can read Alice's Document 1, Bob cannot read Document 1; nonexistent IDs, wrong types, and wrong permissions are all denied.
2. When application code calls `service.read(1L)`, Spring **actually intercepts the call via `@PreAuthorize`**, extracts parameter `#p0`, invokes the registered evaluator, and throws `AccessDeniedException` before entering the method body if the caller lacks permission.

A plain Java unit test can prove (1) but **cannot prove (2)**. Only proxy/service integration tests prove (2), while HTTP tests with `MockMvc` add a third question: do the filter chain, authentication, and exception translation produce 401/403/200 responses per the API contract?

### Testing scope table

| Test layer | Target invoked | Key assertion | What does it not prove? |
| --- | --- | --- | --- |
| Evaluator unit | `new DocumentPermissionEvaluator(fakeStore)` | Correct boolean true/false for principal, object, ID/type, permission | Does not prove Spring registered the evaluator or enabled method security |
| Method-security integration | `@Autowired DocumentService` (Spring proxy) | `@PreAuthorize` runs, right overload invoked, method body does not run on deny | Does not verify URL matchers, CSRF, or HTTP status |
| MVC/security integration | `MockMvc` with filters, authenticated user | HTTP route, authentication, service proxy, status/JSON | Does not prove real network or reverse-proxy behavior |
| Out-of-process end-to-end | Real client → real server → DB/external services | Real authentication, deployment config, DB/transactions | Usually slow and does not replace thorough unit tests |

Do not pick just one test layer and call it enough. When permission logic is complex, most cases belong in **evaluator unit tests** because they are fast and isolated; representative cases must go through the **proxy** to catch misconfiguration; add several HTTP tests to confirm the client experience.

## 2. Understanding the exact APIs under test

`PermissionEvaluator` resides in `org.springframework.security.access.PermissionEvaluator` and has **two overloads**:

~~~java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);

boolean hasPermission(
    Authentication authentication,
    Serializable targetId,
    String targetType,
    Object permission
);
~~~

The two corresponding SpEL forms:

~~~java
// Object is already available in the first parameter.
@PreAuthorize("hasPermission(#p0, 'read')")

// Only the object's ID is known; specify type and permission.
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
~~~

When calling directly from a unit test, you **supply `Authentication` yourself**. When the method-security proxy evaluates SpEL, Spring Security **automatically retrieves `Authentication`** from the security context. `#p0` in the annotation is the first method parameter, not the first evaluator parameter. `targetType` is a type name agreed upon by the app or ACL layer; Spring does not automatically look up entities just from the literal `'Document'`.

`PermissionEvaluator` returns a boolean, not an HTTP status. **false** is a denial decision; when a `@PreAuthorize` expression evaluates to false, the method-security interceptor normally throws `AccessDeniedException` (or a subtype) along the protected call path. When passing through the HTTP filter chain, Spring may translate it to 403; for unauthenticated callers, entry points typically return 401 with HTTP Basic. Never assert every failure is 403 while ignoring configuration.

### 2.1. The default evaluator might not be your evaluator

Merely declaring `@Component class MyPermissionEvaluator implements PermissionEvaluator` is **not enough** to guarantee method security expressions use that implementation in every setup. A properly configured `MethodSecurityExpressionHandler` must hold the evaluator. If the handler still uses the deny-all default, unit tests stay green while every valid request gets denied.

When using `@EnableMethodSecurity`, expose the handler using this pattern:

~~~java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        PermissionEvaluator evaluator) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(evaluator);
    return handler;
}
~~~

`static @Bean` publishes the handler early before Spring initializes method security configuration. Integration tests must verify actual execution rather than merely seeing a `PermissionEvaluator` bean in the context.

### 2.2. @WithMockUser does not mark a method as protected

`@WithMockUser` places an authenticated mock `Authentication` into the test thread's `SecurityContextHolder`. It **does not create a proxy**, does not enable `@EnableMethodSecurity`, does not invoke the evaluator, and does not replace request authentication for all end-to-end tests. When real HTTP tests run on separate threads/servers, authenticate requests via Basic/Bearer/cookies as appropriate.

`@WithMockUser(username="alice", authorities={"document:read","tenant:alpha"})` creates exact authority strings. Conversely, `roles={"ADMIN"}` defaults to creating `ROLE_ADMIN`; never write `roles={"document:read"}` and expect `hasAuthority('document:read')` to match.

## 3. Designing policy so unit tests need no Spring

Example document management domain:

~~~text
ID 1: Document tenant=alpha, owner=alice
ID 2: Document tenant=beta,  owner=bob
ID 3: Document tenant=alpha, owner=bob
~~~

`read` rule: the principal must hold the `document:read` authority, hold the matching tenant authority, and own the document loaded from the trusted store. `targetType` must be exactly `Document`, `permission` must be exactly `read`, and ID must be a positive `Long`. Client-created objects with forged owners must not be treated as trusted permission sources.

**Separate policy classes from Spring AOP:** the evaluator receives `DocumentStore` via constructor injection and can be instantiated with `new` in unit tests. Unit tests need no `ApplicationContext`, `SecurityContextHolder`, web server, real database, or `@WithMockUser`.

Invalid input is not “abstain” or “allow.” With `PermissionEvaluator`, return `false` for unsupported types/IDs/permissions per contract. If the store/ACL backend hits an infrastructure failure, handle it safely with proper exceptions/logging; never catch all exceptions and return `true`.

## 4. Sample Spring Boot app shared by both test layers

This is a **complete Spring Boot file in a project that already has dependencies**; it cannot be run with plain JDK `javac` without Spring JARs. Create:

~~~text
src/main/java/example/permissiontest/PermissionTestApplication.java
src/test/java/example/permissiontest/DocumentPermissionEvaluatorUnitTest.java
src/test/java/example/permissiontest/PermissionProxyIntegrationTest.java
~~~

### 4.1. Application code

Save `src/main/java/example/permissiontest/PermissionTestApplication.java`:

~~~java
package example.permissiontest;

import java.io.Serializable;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionTestApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        // URL requires authentication only. ACL is decided by method security.
                        .requestMatchers(HttpMethod.GET, "/api/documents/*")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "tenant:alpha").build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read", "tenant:beta").build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("document:view").build());
    }
}

record Document(long id, String tenant, String owner, String title) {
}

@Component
class DocumentStore {
    private final Map<Long, Document> data = Map.of(
            1L, new Document(1L, "alpha", "alice", "Budget A"),
            2L, new Document(2L, "beta",  "bob",   "Budget B"),
            3L, new Document(3L, "alpha", "bob",   "Budget C"));

    Optional<Document> find(Long id) {
        return Optional.ofNullable(data.get(id));
    }
}

@Component
class DocumentPermissionEvaluator implements PermissionEvaluator {
    private final DocumentStore store;

    DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(Authentication actor,
                                 Object targetDomainObject,
                                 Object permission) {
        if (!(targetDomainObject instanceof Document supplied)) {
            return false;
        }
        // Use only the ID from candidate; DO NOT trust client-declared owner/tenant.
        return store.find(supplied.id())
                .map(saved -> canRead(actor, saved, permission))
                .orElse(false);
    }

    @Override
    public boolean hasPermission(Authentication actor,
                                 Serializable targetId,
                                 String targetType,
                                 Object permission) {
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id) || id <= 0) {
            return false;
        }
        return store.find(id)
                .map(saved -> canRead(actor, saved, permission))
                .orElse(false);
    }

    private boolean canRead(Authentication actor, Document doc,
                            Object permission) {
        if (actor == null || !actor.isAuthenticated()
                || !"read".equals(permission)) {
            return false;
        }

        boolean hasFeature = actor.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));
        boolean hasTenant = actor.getAuthorities().stream()
                .anyMatch(a -> ("tenant:" + doc.tenant())
                        .equals(a.getAuthority()));
        boolean owns = doc.owner().equals(actor.getName());

        return hasFeature && hasTenant && owns;
    }
}

@Service
class DocumentService {
    private final DocumentStore store;
    private final AtomicInteger bodyExecutions = new AtomicInteger();

    DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public Document readById(Long id) {
        bodyExecutions.incrementAndGet();
        return store.find(id).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    @PreAuthorize("hasPermission(#p0, 'read')")
    public Document readLoaded(Document candidate) {
        bodyExecutions.incrementAndGet();
        return store.find(candidate.id()).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    public int bodyExecutions() {
        return bodyExecutions.get();
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Map<String, Object> read(@PathVariable Long id) {
        Document doc = service.readById(id);
        // Return a map so JSON does not depend on internal record visibility.
        return Map.of("id", doc.id(), "owner", doc.owner(),
                      "title", doc.title());
    }
}
~~~

**Demo limitations:** data and tenant authorities are hardcoded in memory; `{noop}` passwords are for learning only. Production must use a secure password encoder, verified identity/tenant, and tenant/ACL-scoped queries. `bodyExecutions` is purely test instrumentation to verify the method body did not run; it is not a business feature.

### 4.2. Gradle dependencies

In a Spring Boot 3.x project (e.g., created from Spring Initializr) with plugins, dependency management, and Java 17+ already configured, declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is only a **`dependencies` snippet** for `build.gradle`, not a standalone build file. Tests run via `./gradlew test` on macOS/Linux or `gradlew.bat test` on Windows. The sample omits database/Redis/JWT to keep the unit under test clear.

## 5. Evaluator unit test: testing one class without a Spring context

Save `src/test/java/example/permissiontest/DocumentPermissionEvaluatorUnitTest.java`:

~~~java
package example.permissiontest;

import java.io.Serializable;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPermissionEvaluatorUnitTest {
    private final DocumentPermissionEvaluator evaluator =
            new DocumentPermissionEvaluator(new DocumentStore());

    static Authentication actor(String username, String... authorities) {
        return new UsernamePasswordAuthenticationToken(
                username, "ignored",
                AuthorityUtils.createAuthorityList(authorities));
    }

    @Test
    void grantsOnlyOwnerInMatchingTenant() {
        Authentication alice = actor(
                "alice", "document:read", "tenant:alpha");
        Authentication bob = actor(
                "bob", "document:read", "tenant:beta");

        assertTrue(evaluator.hasPermission(
                alice, 1L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, 2L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, 3L, "Document", "read"));
        assertTrue(evaluator.hasPermission(
                bob, 2L, "Document", "read"));
    }

    @Test
    void rejectsMissingAuthorityOrTenant() {
        Authentication noFeature = actor("alice", "tenant:alpha");
        Authentication wrongTenant = actor(
                "alice", "document:read", "tenant:beta");

        assertFalse(evaluator.hasPermission(
                noFeature, 1L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                wrongTenant, 1L, "Document", "read"));
    }

    @Test
    void rejectsUnknownTypePermissionOrId() {
        Authentication alice = actor(
                "alice", "document:read", "tenant:alpha");

        assertFalse(evaluator.hasPermission(
                alice, 1L, "Invoice", "read"));
        assertFalse(evaluator.hasPermission(
                alice, 1L, "Document", "write"));
        assertFalse(evaluator.hasPermission(
                alice, 999L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, Integer.valueOf(1), "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, (Serializable) null, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                null, 1L, "Document", "read"));
    }

    @Test
    void objectOverloadDoesNotTrustForgedOwner() {
        Authentication alice = actor(
                "alice", "document:read", "tenant:alpha");
        Document honest = new Document(
                1L, "alpha", "alice", "Client copy");
        Document forged = new Document(
                2L, "alpha", "alice", "Forged owner");

        assertTrue(evaluator.hasPermission(alice, honest, "read"));
        assertFalse(evaluator.hasPermission(alice, forged, "read"));
        assertFalse(evaluator.hasPermission(alice, honest, "delete"));
        assertFalse(evaluator.hasPermission(alice, (Object) null, "read"));
    }
}
~~~

### 5.1. Why is this a true unit test?

- The test constructs `DocumentStore` and `DocumentPermissionEvaluator` directly, without `@SpringBootTest`, `@Autowired`, or `SecurityContextHolder`.
- `Authentication` is built directly using the three-argument `UsernamePasswordAuthenticationToken` and explicit authority list; no real user in `UserDetailsService` is needed.
- Tests exercise **both overloads** of `PermissionEvaluator` with clear inputs.
- Tests assert denial for an `Integer` ID type even when the numeric value equals `Long(1)`, because the sample evaluator's contract expects `Long`.
- The forged-object test for ID 2 proves the evaluator does not trust owner/tenant properties on client-supplied objects.

**Important:** green unit tests only show the implementation returns the right boolean for this fixture. They **do not verify whether `@PreAuthorize` is activated by Spring, whether the handler uses this evaluator, or whether calls go through a real proxy**. That distinction is the central focus of this lesson's title.

### 5.2. Using a mock repository when data is complex

When the evaluator uses a DB-backed repository, you can use Mockito instead of an in-memory fixture. Example (snippet, not a complete class):

~~~java
DocumentStore store = mock(DocumentStore.class);
when(store.find(1L)).thenReturn(Optional.of(
        new Document(1L, "alpha", "alice", "A")));
DocumentPermissionEvaluator evaluator =
        new DocumentPermissionEvaluator(store);
~~~

Corresponding imports: `static org.mockito.Mockito.mock`, `static org.mockito.Mockito.when`, and `java.util.Optional`. Distinguish clearly:
- **Stub the repository** to control owner/tenant/ACL data and test deny/grant branches.
- **Do not mock `PermissionEvaluator` itself** when the goal is testing its real algorithm.
- Only use `verify(...)` to check lookup counts or arguments when meaningful; never replace security decision assertions with “method was called.”

An isolated unit test must not be affected by leftover authentication from another test. Here the evaluator receives `Authentication` directly, so it does not depend on thread-local context.

## 6. Integration tests through the proxy: proving @PreAuthorize executes

Save `src/test/java/example/permissiontest/PermissionProxyIntegrationTest.java`:

~~~java
package example.permissiontest;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionProxyIntegrationTest {
    @Autowired
    DocumentService service;

    @Autowired
    MockMvc mvc;

    @Test
    void serviceBeanIsActuallyProxied() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyGrantsValidDocument() {
        Document doc = service.readById(1L);
        assertEquals("alice", doc.owner());
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyDeniesOtherTenantBeforeBodyRuns() {
        int before = service.bodyExecutions();

        assertThrows(AccessDeniedException.class,
                () -> service.readById(2L));

        assertEquals(before, service.bodyExecutions());
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyDeniesOtherOwnerEvenWithinTenant() {
        assertThrows(AccessDeniedException.class,
                () -> service.readById(3L));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyEvaluatesObjectOverloadUsingTrustedStore() {
        Document forged = new Document(
                2L, "alpha", "alice", "Forged");

        assertThrows(AccessDeniedException.class,
                () -> service.readLoaded(forged));
    }

    @Test
    @WithMockUser(username = "viewer",
                  authorities = {"document:view"})
    void proxyDeniesMissingFeatureAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> service.readById(1L));
    }

    @Test
    @WithAnonymousUser
    void proxyDoesNotGrantAnonymousUser() {
        assertThrows(AccessDeniedException.class,
                () -> service.readById(1L));
    }

    @Test
    void httpBasicAliceCanReadThroughFilterAndProxy() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void httpBasicBobCannotReadAliceDocument() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedHttpRequestRequiresLogin() throws Exception {
        mvc.perform(get("/api/documents/1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownIdIsDeniedByEvaluatorInThisDemo() throws Exception {
        mvc.perform(get("/api/documents/999")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isForbidden());
    }
}
~~~

### 6.1. Reading each test's meaning accurately

`AopUtils.isAopProxy(service)` is a **sanity check**, insufficient on its own to prove the right security advisor is active. The **GRANT** and **DENY** decision tests supply the real proof: when Alice calls through the Spring bean, ID 1 is read; when calling ID 2, `AccessDeniedException` is thrown and `bodyExecutions` does not increment. That proves the policy blocked **before the method body** along the example's real invocation path.

`@WithMockUser` creates a security context for direct service calls on the test thread; `@SpringBootTest` supplies the Spring-managed bean with its proxy/interceptor. For HTTP tests, `MockMvc` runs the filter chain and `httpBasic("alice","demo")` supplies request credentials; never confuse a service unit test using mock users with real HTTP login tests.

**Important:** Spring Security may throw a subtype of `AccessDeniedException`. The tests assert this superclass to avoid brittle coupling to specific exception class names across versions.

### 6.2. A Java syntax note on static imports

Java does not let an `import` be arbitrarily split across two lines around a dot when copied from a renderer if formatting tools behave oddly. The following static imports are equivalent and can be written on single lines for easy copying:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

In the sample file, those imports wrap on whitespace before dots for display; Java syntax allows whitespace between tokens, though single-line imports are most convenient when pasting into an IDE. The `org.springframework.http.HttpStatus` import in the sample test is unused and can be removed by your IDE without affecting the outcome.

### 6.3. Mock-user policy vs. real login

`@WithMockUser(username="alice", authorities={"document:read", "tenant:alpha"})` **never checks a password**, does not confirm Alice exists in a database, and does not exercise the filter chain. By contrast, `httpBasic("alice","demo")` through `MockMvc` exercises the demo `UserDetailsService` and Basic authentication in `SecurityFilterChain`.

A JWT application can use the `jwt()` request post-processor to test claims-based authorization or issue real requests with valid test tokens. If the principal is a custom type and application code casts to it, `@WithMockUser` with its default `User` principal may not represent production; use `@WithUserDetails` or `@WithSecurityContext` to supply the real principal shape. Tests must reflect the real authentication shape.

## 7. False-positive tests that bypass the proxy: anti-patterns

### 7.1. Instantiating the service with new

~~~java
// Anti-pattern: service is not a proxied Spring bean.
DocumentService direct = new DocumentService(new DocumentStore());
Document doc = direct.readById(2L); // Does NOT run @PreAuthorize automatically.
~~~

The method body accesses the store directly and returns Document 2 without checking the caller. In this style of test, even if `@WithMockUser` or `SecurityContextHolder` has Bob/Alice, the annotation **has no effect** because AOP interception is absent. You may do this when intentionally testing **business logic without security**, but it must never count as an authorization integration test.

### 7.2. Self-invocation within one bean

~~~java
@Service
class ExampleService {
    public Document internalCall(Long id) {
        return protectedRead(id); // this.protectedRead() bypasses the proxy.
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public Document protectedRead(Long id) {
        return loadDocument(id);
    }
}
~~~

This is an **illustrative snippet**, omitting `loadDocument` and full imports. When a call originates inside the target bean itself via `this`, standard Spring proxy mode does not intercept `protectedRead`. Fix: move the protected method into **another bean** and call it through that bean, or configure AspectJ mode deliberately and test it; never rely on internal calls via `this`.

### 7.3. Mocking the secured service itself

If a controller test uses:

~~~java
@MockitoBean
DocumentService service;  // Boot 3.4+; older versions used @MockBean
~~~

then `service` may be a mock stub, bypassing the method body, evaluator, and security advisor. That test only proves the controller calls the mock and maps responses. To test method security, use the **real** bean and mock only lower-level dependencies such as repositories or ACL providers when needed. `@MockBean` and `@MockitoBean` vary across Spring Boot/Spring Framework versions; do not mix the two annotations without checking dependencies.

### 7.4. Expecting @WithMockUser to work with plain JUnit

Merely writing:

~~~java
@Test
@WithMockUser(username = "alice")
void wrong() {
    new DocumentService(new DocumentStore()).readById(2L);
}
~~~

does not test enforcement: there is no Spring context or proxy. `@WithMockUser` only populates the security context when Spring Security's Test Execution Listener runs with Spring Test setup; even with a context, it still **cannot turn a `new` instance into a proxy**.

## 8. Recommended test matrix and easily missed cases

| Layer | Input or scenario | Expected result |
| --- | --- | --- |
| Evaluator unit | Alice + Document 1 + type Document + read | true |
| Evaluator unit | Alice + Document 2 tenant beta | false |
| Evaluator unit | Alice + Document 3 same tenant, owner Bob | false |
| Evaluator unit | Alice missing document:read | false |
| Evaluator unit | Alice missing tenant:alpha | false |
| Evaluator unit | Wrong type Invoice | false |
| Evaluator unit | Unsupported permission write | false |
| Evaluator unit | Null ID, Integer ID, nonexistent ID | false |
| Evaluator unit | Object with forged owner Alice for Document 2 | false |
| Proxy integration | Alice calls real Spring-managed service with ID 1 | Allowed and method body runs |
| Proxy integration | Alice calls ID 2 | AccessDeniedException; body does not run |
| Proxy integration | Viewer lacks authority | AccessDeniedException |
| Proxy integration | Anonymous | Not granted access |
| Proxy integration | Object overload called with forged Document | DENY |
| HTTP integration | Alice logs in via Basic, GET Document 1 | 200 and Alice's data |
| HTTP integration | Bob logs in via Basic, GET Document 1 | 403 |
| HTTP integration | Unauthenticated | 401 with sample Basic config |
| HTTP integration | Nonexistent ID | 403 in sample policy (not a mandatory rule) |
| Configuration | Remove @EnableMethodSecurity | Deny/proxy tests must catch it |
| Configuration | Do not register real evaluator | Grant/proxy tests must catch it |
| Regression | Switch call to self-invocation | Security boundary tests must catch it |
| Transaction/ACL | Permission revoked between check and use | Neither returns nor writes unauthorized data |
| Concurrency | Two callers hit same resource, update owner/tenant | Policy stays consistent with data-layer scope |

Keep **at least one grant test and one deny test** through the proxy. Having only deny tests easily causes *false positives*: a misconfigured deny-all evaluator still makes every deny test pass. Having only grant tests is equally risky: inactive annotations still let the method return data. Pairing grant/deny tests with a body-execution counter gives a reliable signal.

### 8.1. Mental mutation testing

Try introducing each defect below one by one and confirm which tests turn red:

- Change `return hasFeature && hasTenant && owns;` to `return hasFeature;` → cross-tenant/other-owner unit tests must fail.
- Change `"Document".equals(targetType)` to `true` → wrong-type unit tests must fail.
- Replace `@PreAuthorize("hasPermission(#p0, 'Document', 'read')")` with `@PreAuthorize("permitAll")` → proxy deny tests must fail.
- Remove `@EnableMethodSecurity` → proxy deny tests or proxy verification tests must fail.
- Skip setting `PermissionEvaluator` on the handler → proxy grant tests must fail.
- Instantiate `new DocumentService(...)` inside a test → proxy assertion must fail.

Mutation-testing mindset catches tests that merely verify an implementation “runs” without verifying critical security invariants.

## 9. Plain Java 17: simulating unit decision and interception boundary

This example uses no real Spring or AOP. It simply separates **policy** from the **permission-checking decorator** so you can see that unit-testing a policy does not equate to protecting service invocations. Save as `PermissionBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class PermissionBoundaryDemo {
    record Actor(String name, String tenant, Set<String> authority) {}
    record Doc(long id, String owner, String tenant) {}

    static final Map<Long, Doc> DATA = Map.of(
            1L, new Doc(1L, "alice", "alpha"),
            2L, new Doc(2L, "bob", "beta"));

    static boolean allow(Actor actor, long id) {
        Doc doc = DATA.get(id);
        return actor != null && doc != null
                && actor.authority().contains("document:read")
                && actor.tenant().equals(doc.tenant())
                && actor.name().equals(doc.owner());
    }

    interface Reader {
        Doc read(long id);
    }

    static final class PlainReader implements Reader {
        public Doc read(long id) {
            return DATA.get(id); // Performs no authorization itself.
        }
    }

    static final class CheckingReader implements Reader {
        private final Actor actor;
        private final Reader target;

        CheckingReader(Actor actor, Reader target) {
            this.actor = actor;
            this.target = target;
        }

        public Doc read(long id) {
            if (!allow(actor, id)) {
                throw new SecurityException("denied");
            }
            return target.read(id);
        }
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", "alpha", Set.of("document:read"));
        Actor bob = new Actor(
                "bob", "beta", Set.of("document:read"));
        Reader plain = new PlainReader();

        System.out.println("unit-alice-id1=" + allow(alice, 1L));
        System.out.println("unit-bob-id1=" + allow(bob, 1L));

        // Bypass decorator: PlainReader by itself has no permission check.
        System.out.println("plain-bob-reads-id1=" +
                (plain.read(1L) != null));

        Reader guarded = new CheckingReader(bob, plain);
        try {
            guarded.read(1L);
            System.out.println("guarded-bob=allowed");
        } catch (SecurityException denied) {
            System.out.println("guarded-bob=denied");
        }

        Reader aliceGuarded = new CheckingReader(alice, plain);
        System.out.println("guarded-alice-id1=" +
                aliceGuarded.read(1L).owner());
    }
}
~~~

Compile with JDK 17:

~~~bash
javac --release 17 PermissionBoundaryDemo.java
java PermissionBoundaryDemo
~~~

**Exact stdout:**

~~~text
unit-alice-id1=true
unit-bob-id1=false
plain-bob-reads-id1=true
guarded-bob=denied
guarded-alice-id1=alice
~~~

Meaning: `allow(bob, 1L)` correctly returned false in the unit check; nevertheless, `PlainReader.read(1)` still returns data if the caller bypasses the decorator. Spring AOP/method-security proxies are how the framework enforces this boundary; unit tests on the policy alone cannot prove every call path goes through the interceptor.

## 10. Test reliability: fixtures, threads, transactions, and exceptions

### 10.1. Handling state between tests

The demo suite uses an immutable `Map.of` and checks only the **delta of the body counter within one test**, never asserting an absolute total across multiple tests. If tests modify permissions, ACLs, the DB, or document state, provide isolated fixtures / transaction rollbacks or reset state. Never let tests depend on execution order or leftover data from a prior test.

A `@Transactional` test transaction can roll back fixture data, yet you must not assume it protects async tasks, external APIs, or other threads. With persistence integration, test isolation, optimistic locking, and query scoping separately.

### 10.2. Failures in unit tests differ from failures at the proxy

`PermissionEvaluator.hasPermission(...)` itself returns `false`. `@PreAuthorize` consumes that result and blocks the call with an exception. Over Servlet HTTP, filters/handlers translate the exception into a response. Observing three different outputs is normal:

~~~text
Unit:        false
Service:     AccessDeniedException (or subtype)
HTTP:        403 / 401 / 404 per security and API policy
~~~

If a test asserts a boolean directly yet expects 403, the test targets the wrong layer. If an HTTP test expects `AccessDeniedException` to escape straight into JUnit, the filter chain may already have converted it into an HTTP response—again, wrong layer.

### 10.3. 401, 403, and 404 need explicit contracts

In the demo, an unknown ID causes the evaluator to return false and the method does not run; HTTP is 403 for authenticated callers. That is not the only way: an anti-enumeration API may intentionally return a uniform 404 for both nonexistent and invisible resources. Tests must follow **the policy chosen by the application**, rather than inferring HTTP status codes solely from the `PermissionEvaluator` interface.

### 10.4. Null, anonymous, and authenticated principals

Unit tests pass a `null Authentication` to check evaluator fail-closed behavior. Spring method-security infrastructure normally manages authentication/anonymous tokens per configuration and may raise a different failure if the security context is invalid. Never assume a unit test with null reproduces the exact HTTP anonymous code path. Write anonymous tests at the integration layer separately.

### 10.5. Performance tests and N+1

A `PermissionEvaluator` may perform an ACL lookup per invocation. With `@PostFilter` over long lists, query counts can grow with the number of items; fast unit tests hide this issue. Add SQL count/pagination and tenant-scoping tests. When permissions are complex, consider batch ACL queries or DB-level filter predicates rather than loading an entire table and filtering afterward.

### 10.6. TOCTOU between permission check and data use

`@PreAuthorize` may check a document at t1; the service runs its query/update at t2; owner or tenant changed in between. Proxy integration tests can still pass even when production has a race. For writes, check permissions against trusted data inside the transaction / conditional update statement with versioning/locking; for reads, enforce tenant/ACL limits at the data layer. Test concurrency at an appropriate system level.

### 10.7. Infrastructure errors are not “user lacks permission”

If the ACL service/DB times out, never catch `Exception` and `return true`. Depending on contract, return a safe deny or throw an exception resulting in a server error while logging safely. Unit tests should cover gateway failure branches; integration tests should confirm **no data is returned** when the gateway fails. Never expose credentials/tokens or internal ACLs in responses.

## 11. A reusable QA workflow

1. **Write the contract first:** who, which resource, which permission, where tenant/owner/ACL come from, and how missing data is handled.
2. **Evaluator unit tests:** table-driven tests covering every grant/deny combination, null, wrong type, wrong ID, unsupported permission, and forged objects.
3. **Method security configuration:** enable `@EnableMethodSecurity`, register `MethodSecurityExpressionHandler` with the real evaluator.
4. **Integration through Spring bean:** `@Autowired` service, verify proxy, one GRANT case, one DENY case, and verify the body does not execute on deny.
5. **HTTP integration:** `MockMvc` with security filters, real request authentication, and 200/401/403 per policy; do not rely solely on filter-less `standaloneSetup`.
6. **Exercise other call paths:** scheduled jobs, message listeners, internal calls, self-invocation, async executors — sensitive services must stay protected regardless of entry point.
7. **Check performance and concurrency:** ACL lookups, N+1, tenant scope, revoked permissions, t1→t2 races, transactions/locking.
8. **Mutation checks:** intentionally break a permission grant or disable annotations to confirm tests catch regressions.

### Self-check questions

**Question 1:** A test calls `new DocumentPermissionEvaluator(new DocumentStore()).hasPermission(...)` and gets false for Bob. Does that prove `@PreAuthorize` on the service works?

**Answer:** No. It only tests the evaluator. You must call the Spring service bean through its proxy with Bob's security context and assert denial.

**Question 2:** An integration suite has only “unauthorized user is denied” cases and no grant cases. What is the risk?

**Answer:** The handler might not be using your custom evaluator yet, and the default deny-all evaluator still makes every deny test pass. Add grant cases on valid resources.

**Question 3:** Are `@WithMockUser` and `httpBasic(...)` in MockMvc equivalent?

**Answer:** Not completely. `@WithMockUser` populates a test authentication directly; `httpBasic(...)` adds a header so the request runs through Basic authentication and user lookup in the filter chain. Choose according to the layer you want to test.

**Question 4:** Is calling `this.readById(...)` from inside the same service bean guaranteed to trigger `@PreAuthorize`?

**Answer:** Not in default proxy mode. Internal calls bypass the Spring proxy; move the secured method to another bean or configure dedicated interception and test it.

**Question 5:** Does MockMvc returning 403 for ID 999 mean ID 999 exists and the user lacks permission?

**Answer:** No. In the demo, the evaluator returns false when the ID does not exist, so `@PreAuthorize` blocks before the method. You cannot infer existence from HTTP 403 alone; API error policies must be designed consistently.

## References

- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, proxies, `PreAuthorizeAuthorizationManager`, customizing `MethodSecurityExpressionHandler`.
- [PermissionEvaluator Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): both overloads and the boolean contract.
- [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): setting up `MockMvc` with Spring Security.
- [Spring Security – HTTP Basic Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html): `httpBasic(...)` request post-processor.
