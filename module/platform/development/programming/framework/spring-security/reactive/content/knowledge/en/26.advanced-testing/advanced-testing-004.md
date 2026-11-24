# Testing @PreAuthorize, @PostAuthorize, and Invocations Through Spring Proxy in Spring Security Reactive

## Goals and scope

This lesson belongs to **Spring Security – reactive / Advanced Testing**. After this lesson, you will be able to: (1) verify access permissions **before** a method executes using `@PreAuthorize`; (2) verify the **return value** using `@PostAuthorize`; (3) verify that calls genuinely go through the Spring AOP proxy; (4) detect internal `this.method()` calls that bypass advice; and (5) verify `Mono`'s `onNext`, `onError`, and `onComplete` signals with `StepVerifier`, rather than only checking publisher creation.

This covers **WebFlux/reactive method security** testing. Examples use Java 17+, Spring Boot 3.x / Spring Security 6.x, Reactor, and JUnit Jupiter. Do not substitute servlet-side `@EnableMethodSecurity`: the reactive counterpart here is `@EnableReactiveMethodSecurity`.

## 1. Understanding the three check points

| Check point | Timing, condition | What to assert in tests |
| --- | --- | --- |
| `@PreAuthorize("hasRole('EDITOR')")` | Checks permission before allowing the method to run; in reactive pipelines, errors surface on subscribe | Authorized caller receives value; unauthorized caller receives `AccessDeniedException`; sensitive logic does not execute |
| `@PostAuthorize("returnObject.owner == authentication.name")` | Checks the result object before delivering it to the caller | True owner receives result; non-owner gets `AccessDeniedException` and never receives the object |
| Spring AOP proxy | Method security advice runs when the call enters **the bean through the proxy** | Calls from another bean via the injected bean enforce security; `this.securedMethod()` inside the same target can bypass security |

Conceptual flow of a valid call: **caller → Spring proxy → check `@PreAuthorize` → target returns `Mono` → publisher emits data → check `@PostAuthorize` (if present) → subscriber**. With reactive method security, user identity is typically read from **Reactor Context** via `ReactiveSecurityContextHolder`, rather than relying on setting `SecurityContextHolder` on one thread and expecting it to carry across every scheduler.

`hasRole('EDITOR')` matches authority `ROLE_EDITOR` via the default prefix; `hasAuthority('document:read')` matches the authority string directly. `@WithMockUser(roles = "EDITOR")` provides `ROLE_EDITOR`. A user with `ROLE_USER` does not automatically have `ROLE_EDITOR`.

**Specifically for `@PostAuthorize`:** authorization is decided **after the logic producing the result has already run**. Unauthorized values are blocked before reaching the caller, but target queries or side effects may already have executed. Never use `@PostAuthorize` as the sole guard for writes, deletes, or irreversible actions; authorize before mutating state.

## 2. Setting up the test environment

The example uses Gradle in a Spring Boot project with managed dependency versions. Relevant dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-security-test` provides `@WithMockUser` and test execution listeners. `reactor-test` provides `StepVerifier`; `spring-boot-starter-test` provides Spring Test/JUnit. Place the example at `src/test/java/demo/security/ReactiveMethodSecurityTest.java`. This is **one complete Java file** using a small test ApplicationContext with real beans, requiring no HTTP server or database.

Configuration must enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`. This mechanism supports `@PreAuthorize` / `@PostAuthorize` on Spring-managed beans whose reactive methods return `Mono` or `Flux`. Never instantiate `new DocumentService()` as the direct subject under test because manually created objects bypass Spring proxies.

## 3. Complete example: three test types in one test class

~~~java
package demo.security;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ReactiveMethodSecurityTest.TestConfig.class)
class ReactiveMethodSecurityTest {

    @Configuration(proxyBeanMethods = false)
    @EnableReactiveMethodSecurity(useAuthorizationManager = true)
    static class TestConfig {
        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }

        @Bean
        InternalCallService internalCallService() {
            return new InternalCallService();
        }

        @Bean
        DocumentFacade documentFacade(DocumentService documents) {
            return new DocumentFacade(documents);
        }
    }

    public static class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }

    public static class DocumentService {
        private final AtomicInteger published = new AtomicInteger();

        @PreAuthorize("hasRole('EDITOR')")
        public Mono<String> publish(String id) {
            return Mono.defer(() -> {
                published.incrementAndGet();
                return Mono.just("published:" + id);
            });
        }

        @PostAuthorize("returnObject.owner == authentication.name")
        public Mono<Document> findById(String id) {
            String owner = "mine".equals(id) ? "alice" : "bob";
            return Mono.just(new Document(id, owner));
        }

        public int publishedCount() {
            return published.get();
        }

        public void reset() {
            published.set(0);
        }
    }

    // ONLY to expose the self-invocation pitfall; do not copy as a production design.
    public static class InternalCallService {
        @PreAuthorize("hasRole('ADMIN')")
        public Mono<String> secret() {
            return Mono.just("secret");
        }

        public Mono<String> throughThis() {
            return this.secret(); // Bypasses proxy on internal call.
        }
    }

    // Safer pattern: call into another injected Spring bean.
    public static class DocumentFacade {
        private final DocumentService documents;

        public DocumentFacade(DocumentService documents) {
            this.documents = documents;
        }

        public Mono<String> publishThroughBean() {
            return documents.publish("from-facade");
        }
    }

    @Autowired
    DocumentService documents;

    @Autowired
    InternalCallService internalCalls;

    @Autowired
    DocumentFacade facade;

    @BeforeEach
    void resetCounters() {
        documents.reset();
    }

    @Test
    void securedBeanIsReallyProxied() {
        assertTrue(AopUtils.isAopProxy(documents));
        assertTrue(AopUtils.isAopProxy(internalCalls));
    }

    @Test
    void noAuthenticationCannotPublish() {
        StepVerifier.create(documents.publish("doc-1"))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, documents.publishedCount());
    }

    @Test
    @WithMockUser(roles = "USER")
    void wrongRoleIsDeniedBeforeBusinessLogicRuns() {
        StepVerifier.create(documents.publish("doc-1"))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, documents.publishedCount());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void editorCanPublish() {
        StepVerifier.create(documents.publish("doc-1"))
                .expectNext("published:doc-1")
                .verifyComplete();
        assertEquals(1, documents.publishedCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeReturnsDocumentToOwner() {
        StepVerifier.create(documents.findById("mine"))
                .assertNext(doc -> assertEquals("alice", doc.getOwner()))
                .verifyComplete();
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeHidesDocumentFromNonOwner() {
        StepVerifier.create(documents.findById("others"))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(roles = "USER")
    void callingThroughThisBypassesSecurityAdvice() {
        StepVerifier.create(internalCalls.secret())
                .expectError(AccessDeniedException.class)
                .verify();

        // VULNERABLE behavior intentionally documented.
        StepVerifier.create(internalCalls.throughThis())
                .expectNext("secret")
                .verifyComplete();
    }

    @Test
    @WithMockUser(roles = "USER")
    void crossBeanCallStillEnforcesPreAuthorize() {
        StepVerifier.create(facade.publishThroughBean())
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, documents.publishedCount());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void crossBeanCallCanSucceedWithRightRole() {
        StepVerifier.create(facade.publishThroughBean())
                .expectNext("published:from-facade")
                .verifyComplete();
        assertEquals(1, documents.publishedCount());
    }
}
~~~

Run from the Gradle project directory containing the dependencies above:

~~~bash
./gradlew test --tests demo.security.ReactiveMethodSecurityTest
~~~

On Windows you can use `gradlew.bat test --tests demo.security.ReactiveMethodSecurityTest`. When configured properly, the tests must pass; do not depend on exact stdout strings since Gradle messages vary by version and log mode. The test `callingThroughThisBypassesSecurityAdvice` **passes when it proves the vulnerability** — it does not prove that design is safe.

### Why are these assertions meaningful?

- **`wrongRoleIsDeniedBeforeBusinessLogicRuns`**: `expectError` alone is insufficient to prove the target caused no side effects. Checking counter equals 0 verifies non-execution as well. The publish logic is placed inside `Mono.defer` so side effects are tied to subscription time.
- **`editorCanPublish`**: you must subscribe via `StepVerifier` for permissions and data flow to actually evaluate; calling `documents.publish("doc-1")` without subscribing is not a complete test.
- **`postAuthorizeReturnsDocumentToOwner` / `postAuthorizeHidesDocumentFromNonOwner`**: same user `alice`, data with two different owners; verifies `returnObject` is evaluated on the **result object** (`Document`), not just the caller's role.
- **`securedBeanIsReallyProxied`**: locks down the foundational assumption. Using a Mockito mock instead of the service or calling a `new`-created instance may return expected values while annotations never run at all.
- **`callingThroughThisBypassesSecurityAdvice`**: negative control for proxy bypass. Calling public `secret()` through the bean is denied, whereas `throughThis()` invokes `this.secret()` on the target and bypasses advice.
- **`crossBeanCallStillEnforcesPreAuthorize`**: extracting orchestration into another bean and injecting `DocumentService` routes the call back through the proxy. This design is easier to test and relies less on Spring AOP internals.

## 4. Security context and timing in reactive tests

`@WithMockUser` creates a mock user (no real database record needed). Spring Test provides `WithSecurityContextTestExecutionListener`; for reactive method security, `ReactorContextTestExecutionListener` helps populate the security context into Reactor Context. With `@ExtendWith(SpringExtension.class)` and `spring-security-test`, subscribing via `StepVerifier` in the same test simulates authentication for the reactive call.

To control auth per publisher precisely without `@WithMockUser`, you can supply `Authentication` directly into Reactor Context. This is a **snippet added inside a test method**, using the matching imports:

~~~java
Authentication editor = new UsernamePasswordAuthenticationToken(
        "alice", "unused",
        List.of(new SimpleGrantedAuthority("ROLE_EDITOR")));

StepVerifier.create(
        documents.publish("manual")
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(editor)))
        .expectNext("published:manual")
        .verifyComplete();
~~~

Imports for the snippet: `java.util.List`, `org.springframework.security.core.Authentication`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.core.authority.SimpleGrantedAuthority`, and `org.springframework.security.core.context.ReactiveSecurityContextHolder`. Within a single test, do not simultaneously apply `@WithMockUser` and overwrite the context with a different user unless intentionally testing precedence.

**Distinguish two points in time:** calling a reactive method to build a publisher and subscribing to that publisher are two separate actions. Asserting `AccessDeniedException` inside `StepVerifier` tests the actual outcome of the pipeline; using `assertThrows(..., () -> service.method())` out of synchronous-service habit usually fails to test when the reactive flow actually emits errors.

**Do not equate method tests with HTTP tests:** `StepVerifier` here verifies `AccessDeniedException`. HTTP status codes 401/403 depend on the WebFlux security layer, authentication entry point, and exception handling; to assert HTTP statuses, write separate WebFlux tests using `WebTestClient` and attach identity directly to the request (such as `mockUser` in Spring Security test). `@WithMockUser` on a plain test method does not automatically log into a request hitting an HTTP server running on another thread/process.

## 5. Additional cases when real rules are more complex

| Case | Test design needed |
| --- | --- |
| `@PreAuthorize` checks parameters, e.g. `#owner == authentication.name` | Test same role with matching and non-matching owner; if using SpEL parameter names, ensure Spring can resolve parameter names at build time (`-parameters` compiler flag or appropriate parameter annotations) |
| Rule uses `hasAuthority('document:write')` | Use `@WithMockUser(authorities = "document:write")`; do not prepend `ROLE_` |
| `@PostAuthorize` rule depends on data fields | Create two fixtures with the same shape but different owners; verify unauthorized receives no `onNext` |
| Logic returns `Flux` | Verify ordering, count, `onComplete`, and `onError` with `StepVerifier`; before applying post-rules to collections/streams, check the exact semantics of your Spring Security version |
| Business branches return `Mono.empty()` or `Mono.error(...)` | Test empty/error cases separately; never infer empty/error handling rules from a happy-path data test |
| Security expression calls a custom bean (e.g. `@authz.canRead(...)`) | Unit test the expression/bean separately, then integration test with a real Spring context to confirm the interceptor calls that bean |
| Service has `@Transactional` or DB writes | Authorize before side effects, verify data unchanged on denied branch; `@PostAuthorize` alone does not guarantee rollback |
| Calling via interface/JDK proxy or class/CGLIB | Inject by interface when using JDK proxies; test calls through the bean, and note `final` / `private` / non-overridable methods may not be advised by class proxies |
| Multiple subscribers, `publishOn` / `subscribeOn` | Verify Reactor Context stays intact through the chain; avoid storing identity in static/ThreadLocal fields to fake auth |

## 6. Common mistakes and diagnostics

1. **Forgetting to enable reactive method security.** Tests return data for every role because `@PreAuthorize` has no advisor. Check `@EnableReactiveMethodSecurity` on the tested context's `@Configuration`; do not only test web route security.
2. **Testing the wrong object.** `new Service()`, a Mockito mock of the entire service, or calling the target extracted via `AopTestUtils.getTargetObject` can bypass advice. Inject the real bean with `@Autowired`; mock underlying repositories/dependencies if needed.
3. **Self-invoking a method in the same class.** `this.secured()` or omitting `this.` is still self-invocation. Move the secured method to a separate bean and inject that bean; test it like `DocumentFacade`.
4. **Forgetting to subscribe.** A cold `Mono` has not run or checked permissions yet, yet a test "passes" because it only checks the object is non-null. Use `StepVerifier` or an actual subscriber.
5. **Confusing `@PreAuthorize` and `@PostAuthorize`.** Pre checks before logic; post checks on the result. A test "blocked" at post does not prove the database was not modified.
6. **Wrong role/authority.** `hasRole('ADMIN')` requires `ROLE_ADMIN` by default; `hasAuthority('ADMIN')` requires the exact string `ADMIN`. Configure test users to match the rule exactly.
7. **Losing Reactor Context.** Setting authentication in ThreadLocal, subscribing manually outside the test, or splitting flows into mechanisms that drop context makes methods report missing permissions even though the test thought it logged in. Trace context flow and subscriptions within test scope; use `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` where appropriate.
8. **Testing only the happy path.** For each rule, always include missing auth, wrong permission, right permission, and matching/non-matching owner; state expectations clearly for both data and side effects.
9. **Misreading HTTP-layer errors.** Inside method tests it is `AccessDeniedException`; 401/403 are filter/handler decisions and require separate request tests.

When a test fails, check in order: (a) is the bean a proxy; (b) is the annotation on a method called from outside the proxy; (c) is reactive method security enabled in the context; (d) are auth/authorities exact; (e) does the subscriber run under the expected Reactor Context; (f) do errors or emitted values match expectations. This sequence quickly isolates configuration, proxy, identity, and logic bugs.

## 7. Acceptance checklist and references

- Include **at least one allow case and one deny case** per annotation; for `@PostAuthorize`, vary the result owner, not just the role.
- Use a Spring-managed service bean and `StepVerifier` to check terminal signals (`verifyComplete` / `expectError`).
- Denied `@PreAuthorize` tests verify sensitive logic did not run; denied `@PostAuthorize` tests verify data was not exposed to the subscriber.
- Document evidence that self-invocation bypasses advice while calls through a separate bean enforce advice.
- Do not infer safety from a "passing" proxy-bypass test: after fixing the design, convert it into a regression test requiring the extracted bean call to be blocked when unauthorized.

Official documentation to verify behavior for your project's version:

- Spring Security – Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – Testing Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/test/method.html
- Spring Security – Testing Method Security, test execution listeners: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework – AOP Proxying Mechanisms (self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
