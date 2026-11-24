# Testing Reactive method security and Reactor Context

> Spring Security hands-on practice for **method-level authorization** in reactive applications. Tools: Java 17+, Spring Security 6.5/7.x, Spring Test/JUnit Jupiter, Reactor `Mono`/`Flux`, and `StepVerifier`. Focus is on **how Authentication is retrieved from Reactor Context**; examples test a Spring service directly without starting an HTTP server.

## 1. Objectives and differences from synchronous testing

A method may be protected with:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> viewReport() { /* ... */ }
~~~

A valuable test suite must prove:

1. **No logged-in user:** the publisher emits an access error.
2. **Logged-in user with wrong authority:** the publisher still emits an error.
3. **Correct authority:** the publisher emits the expected data and completes.
4. **Context is not lost across scheduler switches:** the service still reads the right username via `ReactiveSecurityContextHolder`.
5. **Each subscriber has its own Context:** reusing the same publisher does not mix identities across two subscriptions.

With `Mono`/`Flux`, security errors are normally emitted as an **`onError` signal upon subscribe**, so they must be verified with `StepVerifier`; calling the method and only using `assertDoesNotThrow(...)` proves virtually nothing about access control. Unlike an HTTP API, method tests check `AccessDeniedException`, not HTTP `401`/`403` statuses.

## 2. Reactor Context and reactive method security mechanism

In synchronous Servlet applications, `SecurityContextHolder` typically binds context to a `ThreadLocal`. WebFlux/Reactor applications can switch threads via `publishOn` or `subscribeOn`, so reactive method security uses **Reactor Context**, bound to the *subscription* rather than pinned to a thread.

Key components to understand:

- `ReactiveSecurityContextHolder.getContext()` returns a `Mono<SecurityContext>` read from the current Reactor Context.
- `ReactiveSecurityContextHolder.withAuthentication(auth)` creates a `reactor.util.context.Context` carrying `Authentication` to attach to a publisher with `contextWrite(...)`.
- `@EnableReactiveMethodSecurity` enables interceptors protecting `@PreAuthorize`/`@PostAuthorize` on Spring beans.
- `@WithMockUser` creates test authentication; `WithSecurityContextTestExecutionListener` and `ReactorContextTestExecutionListener` help propagate that info into reactive tests.
- `StepVerifier.create(publisher)` actually **subscribes** and observes `onNext`, `onError`, and `onComplete`.

~~~text
Test  ->  publisher.contextWrite(withAuthentication(auth))
                      |
                      | subscribe: Context flows upstream
                      v
          @PreAuthorize / reactive interceptor
             |                      |
      Missing privilege       Has privilege
             |                      |
      onError(AccessDenied)     Service reads
                                ReactiveSecurityContextHolder
                                     |
                              onNext -> onComplete
~~~

`contextWrite` must sit in the **same chain** as the protected operation and at the right position so Context propagates upstream. Context continues flowing through standard Reactor operators across scheduler switches, yet does not automatically flow into `new Thread`, standalone `CompletableFuture`, or a detached `subscribe()` call.

**AOP note:** protected reactive methods should return a `Publisher` (`Mono`/`Flux`). Call the bean through the Spring container/proxy; instantiating with `new` or self-invoking `this.securedMethod()` can bypass the interceptor. Enable `@EnableReactiveMethodSecurity`, not Servlet's `@EnableMethodSecurity`.

## 3. Dependencies and configuration

In a Spring Boot Maven project (library versions managed by Boot BOM), ensure you have:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
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
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-security-test` provides `@WithMockUser` and test listeners; `reactor-test` provides `StepVerifier`. Create `src/main/java/com/example/security/MethodSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfig {
}
~~~

In modern Spring Security, `useAuthorizationManager = true` is the default; you can write `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` explicitly. This minimal configuration enables only method security, suitable for testing services without starting an HTTP security filter chain.

## 4. Service with authorization and scheduler switching

Create `src/main/java/com/example/security/ReportService.java`:

~~~java
package com.example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> viewReport() {
        return Mono.just("report")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> ReactiveSecurityContextHolder.getContext()
                        .map(SecurityContext::getAuthentication)
                        .map(Authentication::getName)
                        .map(name -> "report for " + name));
    }
}
~~~

`hasAuthority('report:read')` matches the **exact authority value**; `hasRole('ADMIN')` usually looks for authority `ROLE_ADMIN`. `publishOn` creates an intentional scheduler boundary: identity must come from **Reactor Context** at execution time rather than assuming a `ThreadLocal` exists. Output is a fixed per-user string so it can be verified accurately without depending on a DB or external API.

## 5. Five runnable tests with JUnit Jupiter

Create `src/test/java/com/example/security/ReportServiceMethodSecurityTest.java`:

~~~java
package com.example.security;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = {
        MethodSecurityConfig.class,
        ReportService.class
})
class ReportServiceMethodSecurityTest {

    @Autowired
    ReportService service; // Spring bean wrapped by security interceptor

    @Test
    void unauthenticatedIsDenied() {
        StepVerifier.create(service.viewReport())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:write")
    void wrongAuthorityIsDenied() {
        StepVerifier.create(service.viewReport())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void correctAuthorityCanReadAndSeeUser() {
        StepVerifier.create(service.viewReport())
                .expectNext("report for an")
                .verifyComplete();
    }

    @Test
    void manuallyWrittenContextIsVisibleToService() {
        Mono<String> result = service.viewReport()
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                        authenticatedReader("bao")));

        StepVerifier.create(result)
                .expectNext("report for bao")
                .verifyComplete();
    }

    @Test
    void subscribersHaveIndependentContext() {
        Mono<String> shared = service.viewReport();

        Mono<String> first = shared.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authenticatedReader("an")));

        Mono<String> second = shared.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authenticatedReader("binh")));

        Mono<String> combined = Mono.zip(first, second)
                .map(pair -> pair.getT1() + " | " + pair.getT2());

        StepVerifier.create(combined)
                .expectNext("report for an | report for binh")
                .verifyComplete();
    }

    private static Authentication authenticatedReader(String name) {
        return new UsernamePasswordAuthenticationToken(
                name, "unused",
                List.of(new SimpleGrantedAuthority("report:read"))
        );
    }
}
~~~

Run from the project root with Maven Wrapper:

~~~bash
./mvnw -Dtest=ReportServiceMethodSecurityTest test
~~~

Or Windows PowerShell:

~~~powershell
.\mvnw.cmd -Dtest=ReportServiceMethodSecurityTest test
~~~

**Expected result:** all five tests PASS when dependencies/configuration are right. The tests do not print to `System.out`, so there is no fixed stdout; Maven prints test/build results depending on the plugin and version in use. All Java files above have their own `package`, `import`, and class, running in a Spring Boot project with the dependencies declared above.

| Test | Context/authority | Signal to receive |
| --- | --- | --- |
| `unauthenticatedIsDenied` | No authentication | `onError(AccessDeniedException)` |
| `wrongAuthorityIsDenied` | `an`, only `report:write` | `onError(AccessDeniedException)` |
| `correctAuthorityCanReadAndSeeUser` | `an`, has `report:read` | `onNext("report for an")` + `onComplete` |
| `manuallyWrittenContextIsVisibleToService` | `bao`, authority supplied via `contextWrite` | `onNext("report for bao")` + `onComplete` |
| `subscribersHaveIndependentContext` | Two subscribers `an` and `binh` | Pair of outputs matching each user, no Context mixing |

The last case reuses the same `Mono` from the proxied bean and subscribes twice with two different `Authentication` objects; this directly tests that Reactor Context is per-subscriber data. The `correctAuthority...` case also proves the username is still read properly after `publishOn`.

## 6. @WithMockUser, ReactorContextTestExecutionListener, and authorities

When tests run with `@SpringJUnitConfig`/SpringExtension and `spring-security-test`:

1. `WithSecurityContextTestExecutionListener` builds the test `SecurityContext` from `@WithMockUser`, `@WithAnonymousUser`, or custom `@WithSecurityContext`.
2. `ReactorContextTestExecutionListener` integrates the test context with `ReactiveSecurityContextHolder` for reactive publishers and cleans up state when the test ends.

If custom `@TestExecutionListeners` drops the default listeners, tests annotated with `@WithMockUser` may not be recognized by Reactor. When overriding listeners, preserve both `WithSecurityContextTestExecutionListener` **and** `ReactorContextTestExecutionListener` or use the appropriate merge mode.

Clearly distinguish **role** and **authority**:

~~~java
@WithMockUser(username = "admin", roles = "ADMIN")
// authority created: ROLE_ADMIN
// matches @PreAuthorize("hasRole('ADMIN')")

@WithMockUser(username = "an", authorities = "report:read")
// authority created: report:read
// matches @PreAuthorize("hasAuthority('report:read')")
~~~

`@WithMockUser` does not check passwords, DB accounts, tokens, or real principals. For domains needing a custom principal, use `@WithSecurityContext` + a factory; `@WithUserDetails` applies only when a `UserDetailsService` exists and does not automatically load users via arbitrary `ReactiveUserDetailsService` beans. `@WithAnonymousUser` creates an anonymous context for the test; distinguish anonymous from completely missing `Authentication`.

## 7. Manual Context checks and propagation mistakes

`@WithMockUser` is unnecessary when you want to attach users explicitly per subscription:

~~~java
Authentication auth = new UsernamePasswordAuthenticationToken(
        "chi", "unused",
        List.of(new SimpleGrantedAuthority("report:read")));

Mono<String> pipeline = service.viewReport()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(pipeline)
        .expectNext("report for chi")
        .verifyComplete();
~~~

Place `contextWrite` on **the exact publisher that StepVerifier subscribes to**. Typical mistake:

~~~java
// Wrong: this separate subscription does not supply Context to the next test.
service.viewReport()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
        .subscribe();

// A new subscriber does not automatically inherit Authentication from an earlier subscribe.
StepVerifier.create(service.viewReport())
        .expectNext("report for chi")
        .verifyComplete();
~~~

A detached `subscribe()` creates a separate pipeline; `Context` is not a global variable. To verify Reactor Context exists inside the chain, you can temporarily inspect `ReactiveSecurityContextHolder.getContext().map(SecurityContext::getAuthentication)` in a test; never leak passwords/tokens to logs.

Other pitfalls:

- `StepVerifier.expectError(...)` is right for authorization denial: do not expect `assertThrows` on the call creating the `Mono` before subscribing.
- Do not catch and swallow `AccessDeniedException` via `onErrorResume` inside a policy test itself; if fallback must be tested, test it separately after verifying access blocking.
- Synchronous `SecurityContextHolder.getContext()` inside a reactive operator may see empty values or the wrong thread; use `ReactiveSecurityContextHolder`.
- Be careful with `block()` or synchronous code mixed into a pipeline; `StepVerifier` expresses reactive contracts more clearly.
- Access checks with `@PostAuthorize`/`@PostFilter` depend on publisher results; verify data is not emitted to unauthorized subscribers.

## 8. When is WebTestClient needed?

The suite above verifies **service method security** without an HTTP server. If you also need to test the WebFlux filter chain and HTTP statuses, use `WebTestClient` bound to an application context configured with Spring Security test support:

~~~java
// Snippet inside a WebTestClient test that already has the /reports endpoint.
// Configure the client with .apply(springSecurity()) when using bindToApplicationContext.
// import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

webTestClient
        .mutateWith(mockUser()
                .authorities(new SimpleGrantedAuthority("report:read")))
        .get().uri("/reports")
        .exchange()
        .expectStatus().isOk();
~~~

This snippet assumes a `webTestClient` variable, `/reports` endpoint, and filter chain, so it is **only an illustrative snippet**, not a standalone Java program. For HTTP tests, `401`/`403` outcomes depend on entry points and authorization rules; for method tests, verify exceptions/publisher signals. If a test calls a real server over the network, `@WithMockUser` on the test thread does not automatically send authentication to the server: use real HTTP Basic/Bearer tokens or request-level authentication.

## 9. Troubleshooting table when tests fail

| Symptom | What to check | How to fix |
| --- | --- | --- |
| Anyone can access | `@EnableReactiveMethodSecurity` missing; service called outside proxy; self-invocation | Create bean via Spring, test via `@Autowired` |
| `@WithMockUser` still gets denied | Missing Reactor test listener; wrong role/authority | Check test listeners and `hasRole`/`hasAuthority` |
| Test fails immediately when user is absent | Confusing returning `Mono` with subscribing | Use `StepVerifier.expectError(...)` on subscribe |
| Wrong user after thread switch | Reading `ThreadLocal`, detached `subscribe()` splitting pipeline | Use `ReactiveSecurityContextHolder` in the same Reactor chain |
| Test PASSES without emitting data | Only calling `verifyComplete()` without asserting `onNext` | Use `expectNext(...)` then `verifyComplete()` |
| Two users get mixed | Sharing mutable authentication variable or global state | Use separate `contextWrite` per publisher/subscription |
| `ADMIN` role still blocked | `hasRole('ADMIN')` differs from `hasAuthority('ADMIN')` | Check `ROLE_` prefix and actual authorities |
| Method test PASSES, HTTP API still fails | Web filters, mappings, tokens, or security chain untested | Add WebTestClient/HTTP integration tests |

For resource-based rules (such as viewing only one's own report), add tests with the same role but **a different owner**; tests in this lesson focus on Reactor Context and authorities. For multi-item `Flux`, assert exact emitted values/completion; for infinite fluxes, use `thenCancel()` per test intent.

## 10. Self-check checklist

- [ ] Method security is enabled and the method lives on an AOP-managed Spring bean.
- [ ] Method returns an appropriate `Mono`/`Flux`; subscription is not skipped.
- [ ] `spring-security-test`, `reactor-test`, and JUnit Jupiter/Spring Test are present.
- [ ] Test anonymous, missing authority, valid authority, and reading the right principal.
- [ ] Include tests passing auth via `contextWrite(withAuthentication(...))`.
- [ ] Verify two subscribers keep independent Contexts and Context follows operators across scheduler switches.
- [ ] If using `@WithMockUser`, verify the Reactor test listener is active.
- [ ] Separate service method tests from HTTP/WebFlux filter chain tests.

## Official reference documentation

- [Testing Method Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
- [EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Testing Method Security and test listeners](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Project Reactor — Adding a Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

**Self-practice:** add a `@PreAuthorize("hasRole('ADMIN')")` method returning `Mono<String>` and use `@WithMockUser(roles = "USER")`/`@WithMockUser(roles = "ADMIN")` to verify both blocked and allowed branches.